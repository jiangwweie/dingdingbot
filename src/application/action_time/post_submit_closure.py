#!/usr/bin/env python3
"""Materialize PG ticket-bound post-submit closure state.

This is the L7 post-submit boundary:

protected_submit_attempt_id -> reconciliation / settlement / review current state

The materializer is read-only with respect to exchange/order/runtime authority.
It records the first post-submit blocker in PG and never calls FinalGate,
Operation Layer, OrderLifecycle, exchange APIs, or budget mutation paths.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

import sqlalchemy as sa


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.infrastructure.runtime_control_state_repository import (  # noqa: E402
    PgBackedRuntimeControlStateRepository,
    RuntimeControlStateRepositoryError,
)


AUTHORITY_BOUNDARY = (
    "ticket_bound_post_submit_closure; records reconciliation/settlement/review "
    "state only; no exchange/order/runtime authority"
)


def materialize_ticket_bound_post_submit_closure(
    conn: sa.engine.Connection,
    *,
    protected_submit_attempt_id: str,
    now_ms: int | None = None,
) -> dict[str, Any]:
    now_ms = int(now_ms or time.time() * 1000)
    attempt_id = str(protected_submit_attempt_id or "").strip()
    if not attempt_id:
        return _result(
            "blocked",
            now_ms=now_ms,
            blockers=["protected_submit_attempt_id_required"],
            closure={},
            next_action="provide_protected_submit_attempt_id",
        )

    try:
        control_state = PgBackedRuntimeControlStateRepository(conn).read_control_state()
    except RuntimeControlStateRepositoryError as exc:
        return _result(
            "blocked",
            now_ms=now_ms,
            blockers=[f"runtime_control_state_invalid:{exc}"],
            closure={},
            next_action="repair_pg_runtime_control_state",
        )

    existing = _row_by_id(
        control_state,
        "ticket_bound_post_submit_closures",
        "protected_submit_attempt_id",
        attempt_id,
    )
    if existing:
        return _result_from_existing(existing, now_ms=now_ms)

    attempt = _row_by_id(
        control_state,
        "ticket_bound_protected_submit_attempts",
        "protected_submit_attempt_id",
        attempt_id,
    )
    if not attempt:
        return _result(
            "blocked",
            now_ms=now_ms,
            blockers=["protected_submit_attempt_missing"],
            closure={},
            next_action="repair_ticket_bound_protected_submit_attempt",
        )

    blockers = _attempt_blockers(attempt)
    protection_state = _protection_state(attempt)
    if protection_state != "submitted":
        blockers.append(f"post_submit_protection_state:{protection_state}")

    if blockers:
        status = "blocked"
        reconciliation_state = "blocked"
        settlement_state = "blocked"
        review_state = "blocked"
        next_action = "repair_ticket_bound_post_submit_inputs"
    else:
        status = "reconciliation_pending"
        reconciliation_state = "not_checked"
        settlement_state = "blocked"
        review_state = "blocked"
        blockers.append("post_submit_reconciliation_fact_missing")
        next_action = "run_ticket_bound_post_submit_reconciliation"

    closure = _closure_row(
        attempt,
        status=status,
        protection_state=protection_state,
        reconciliation_state=reconciliation_state,
        settlement_state=settlement_state,
        review_state=review_state,
        blockers=_dedupe(blockers),
        next_action=next_action,
        now_ms=now_ms,
    )
    _upsert_row(
        conn,
        "brc_ticket_bound_post_submit_closures",
        "post_submit_closure_id",
        closure,
    )
    return _result(
        status,
        now_ms=now_ms,
        blockers=list(closure["blockers"]),
        closure=closure,
        next_action=next_action,
    )


def materialize_latest_ticket_bound_post_submit_closure(
    conn: sa.engine.Connection,
    *,
    now_ms: int | None = None,
) -> dict[str, Any]:
    now_ms = int(now_ms or time.time() * 1000)
    try:
        control_state = PgBackedRuntimeControlStateRepository(conn).read_control_state()
    except RuntimeControlStateRepositoryError as exc:
        return _result(
            "blocked",
            now_ms=now_ms,
            blockers=[f"runtime_control_state_invalid:{exc}"],
            closure={},
            next_action="repair_pg_runtime_control_state",
        )

    submitted_attempts = [
        dict(row)
        for row in _rows(control_state.get("ticket_bound_protected_submit_attempts"))
        if row.get("status") == "submitted"
    ]
    if not submitted_attempts:
        return _result(
            "not_applicable_no_submitted_attempt",
            now_ms=now_ms,
            blockers=[],
            closure={},
            next_action="wait_for_ticket_bound_protected_submit",
        )

    existing_attempt_ids = {
        str(row.get("protected_submit_attempt_id") or "")
        for row in _rows(control_state.get("ticket_bound_post_submit_closures"))
        if row.get("protected_submit_attempt_id")
    }
    unclosed_submitted = [
        row
        for row in submitted_attempts
        if str(row.get("protected_submit_attempt_id") or "") not in existing_attempt_ids
    ]
    target = max(
        unclosed_submitted or submitted_attempts,
        key=_attempt_sort_key,
    )
    return materialize_ticket_bound_post_submit_closure(
        conn,
        protected_submit_attempt_id=str(target.get("protected_submit_attempt_id") or ""),
        now_ms=now_ms,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument("--require-database-url", action="store_true")
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--protected-submit-attempt-id")
    selector.add_argument("--latest-submitted", action="store_true")
    parser.add_argument("--now-ms", type=int, default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--allow-non-postgres-for-test",
        action="store_true",
        help="Allow SQLite or other SQLAlchemy URLs only for local unit tests.",
    )
    args = parser.parse_args(argv)
    if args.require_database_url and not args.database_url:
        print("ERROR: PG_DATABASE_URL is required for post-submit closure", file=sys.stderr)
        return 2
    if not args.database_url:
        print("ERROR: --database-url or PG_DATABASE_URL is required", file=sys.stderr)
        return 2
    if (
        not args.allow_non_postgres_for_test
        and not args.database_url.startswith(("postgresql://", "postgresql+psycopg://"))
    ):
        print("ERROR: post-submit closure requires PostgreSQL DSN", file=sys.stderr)
        return 2

    engine = sa.create_engine(args.database_url)
    try:
        with engine.begin() as conn:
            if args.latest_submitted:
                report = materialize_latest_ticket_bound_post_submit_closure(
                    conn,
                    now_ms=args.now_ms,
                )
            else:
                report = materialize_ticket_bound_post_submit_closure(
                    conn,
                    protected_submit_attempt_id=args.protected_submit_attempt_id,
                    now_ms=args.now_ms,
                )
    except sa.exc.SQLAlchemyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, default=str))
    else:
        print(report["status"])
    return 1 if report["status"] == "blocked" else 0


def _attempt_sort_key(attempt: dict[str, Any]) -> tuple[int, int, str]:
    return (
        _int_value(attempt.get("updated_at_ms")),
        _int_value(attempt.get("created_at_ms")),
        str(attempt.get("protected_submit_attempt_id") or ""),
    )


def _attempt_blockers(attempt: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if attempt.get("status") != "submitted":
        blockers.append(f"protected_submit_attempt_not_submitted:{attempt.get('status')}")
    if attempt.get("submit_mode") != "real_gateway_action":
        blockers.append(f"protected_submit_attempt_mode_not_real:{attempt.get('submit_mode')}")
    if attempt.get("submit_allowed") is not True:
        blockers.append("protected_submit_attempt_submit_allowed_false")
    for key in (
        "official_operation_layer_submit_called",
        "exchange_write_called",
        "order_created",
        "order_lifecycle_called",
    ):
        if attempt.get(key) is not True:
            blockers.append(f"protected_submit_attempt_flag_false:{key}")
    for key in (
        "withdrawal_or_transfer_created",
        "live_profile_changed",
        "order_sizing_changed",
    ):
        if attempt.get(key) not in {False, None, "", 0}:
            blockers.append(f"protected_submit_attempt_forbidden_effect:{key}")

    submit_result = _as_dict(attempt.get("submit_result"))
    if submit_result.get("status") != "exchange_submit_orders_submitted":
        blockers.append(f"submit_result_not_submitted:{submit_result.get('status')}")
    request_order_ids = {
        str(order.get("local_order_id") or "")
        for order in _as_dict(attempt.get("submit_request")).get("orders", [])
        if order.get("local_order_id")
    }
    submitted_order_ids = {
        str(order.get("local_order_id") or "")
        for order in submit_result.get("submitted_orders", [])
        if order.get("local_order_id")
    }
    if not request_order_ids:
        blockers.append("submit_request_order_ids_missing")
    if not submitted_order_ids:
        blockers.append("submit_result_submitted_order_ids_missing")
    if not submitted_order_ids.issubset(request_order_ids):
        blockers.append("submit_result_order_id_not_in_ticket_request")
    if request_order_ids and submitted_order_ids != request_order_ids:
        blockers.append("submit_result_order_ids_incomplete")
    return _dedupe(blockers)


def _protection_state(attempt: dict[str, Any]) -> str:
    submit_result = _as_dict(attempt.get("submit_result"))
    submitted_orders = [
        dict(item)
        for item in submit_result.get("submitted_orders", [])
        if isinstance(item, dict)
    ]
    if not submitted_orders:
        return "unknown"
    has_sl = any(
        str(order.get("order_role") or "").upper() == "SL"
        and order.get("reduce_only") is True
        and str(order.get("exchange_order_id") or "").strip()
        for order in submitted_orders
    )
    return "submitted" if has_sl else "missing"


def _closure_row(
    attempt: dict[str, Any],
    *,
    status: str,
    protection_state: str,
    reconciliation_state: str,
    settlement_state: str,
    review_state: str,
    blockers: list[str],
    next_action: str,
    now_ms: int,
) -> dict[str, Any]:
    submit_result = _as_dict(attempt.get("submit_result"))
    submitted_order_refs = [
        dict(item)
        for item in submit_result.get("submitted_orders", [])
        if isinstance(item, dict)
    ]
    return {
        "post_submit_closure_id": _stable_id(
            "ticket_post_submit_closure",
            str(attempt.get("protected_submit_attempt_id") or ""),
        ),
        "protected_submit_attempt_id": str(attempt.get("protected_submit_attempt_id") or ""),
        "ticket_id": str(attempt.get("ticket_id") or ""),
        "finalgate_pass_id": str(attempt.get("finalgate_pass_id") or ""),
        "operation_layer_handoff_id": str(attempt.get("operation_layer_handoff_id") or ""),
        "operation_submit_command_id": str(attempt.get("operation_submit_command_id") or ""),
        "runtime_safety_snapshot_id": str(attempt.get("runtime_safety_snapshot_id") or ""),
        "action_time_lane_input_id": str(attempt.get("action_time_lane_input_id") or ""),
        "strategy_group_id": str(attempt.get("strategy_group_id") or ""),
        "symbol": str(attempt.get("symbol") or ""),
        "side": str(attempt.get("side") or ""),
        "status": status,
        "protection_state": protection_state,
        "reconciliation_state": reconciliation_state,
        "settlement_state": settlement_state,
        "review_state": review_state,
        "first_blocker": blockers[0] if blockers else None,
        "blockers": blockers,
        "warnings": [],
        "submitted_order_refs": submitted_order_refs,
        "reconciliation_evidence": {},
        "settlement_evidence": {},
        "review_evidence": {},
        "next_action": next_action,
        "finalgate_called": False,
        "operation_layer_called": False,
        "exchange_write_called": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "withdrawal_or_transfer_created": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
        "runtime_budget_mutated": False,
        "authority_boundary": AUTHORITY_BOUNDARY,
        "created_at_ms": now_ms,
        "updated_at_ms": now_ms,
    }


def _result_from_existing(existing: dict[str, Any], *, now_ms: int) -> dict[str, Any]:
    return _result(
        str(existing.get("status") or "blocked"),
        now_ms=now_ms,
        blockers=list(existing.get("blockers") or []),
        closure=existing,
        next_action=str(existing.get("next_action") or "inspect_existing_post_submit_closure"),
        extra={"idempotent_existing_closure": True},
    )


def _result(
    status: str,
    *,
    now_ms: int,
    blockers: list[str],
    closure: dict[str, Any],
    next_action: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "schema": "brc.ticket_bound_post_submit_closure.v1",
        "status": status,
        "post_submit_closure_id": closure.get("post_submit_closure_id"),
        "protected_submit_attempt_id": closure.get("protected_submit_attempt_id"),
        "ticket_id": closure.get("ticket_id"),
        "operation_submit_command_id": closure.get("operation_submit_command_id"),
        "strategy_group_id": closure.get("strategy_group_id"),
        "symbol": closure.get("symbol"),
        "side": closure.get("side"),
        "protection_state": closure.get("protection_state"),
        "reconciliation_state": closure.get("reconciliation_state"),
        "settlement_state": closure.get("settlement_state"),
        "review_state": closure.get("review_state"),
        "first_blocker": closure.get("first_blocker") or (blockers[0] if blockers else None),
        "blockers": blockers,
        "submitted_order_refs": closure.get("submitted_order_refs", []),
        "next_action": next_action,
        "authority_boundary": closure.get("authority_boundary", AUTHORITY_BOUNDARY),
        "finalgate_called": closure.get("finalgate_called", False),
        "operation_layer_called": closure.get("operation_layer_called", False),
        "exchange_write_called": closure.get("exchange_write_called", False),
        "order_created": closure.get("order_created", False),
        "order_lifecycle_called": closure.get("order_lifecycle_called", False),
        "withdrawal_or_transfer_created": closure.get(
            "withdrawal_or_transfer_created",
            False,
        ),
        "live_profile_changed": closure.get("live_profile_changed", False),
        "order_sizing_changed": closure.get("order_sizing_changed", False),
        "runtime_budget_mutated": closure.get("runtime_budget_mutated", False),
        "observed_at_ms": now_ms,
    }
    if extra:
        payload.update(extra)
    return payload


def _row_by_id(
    control_state: dict[str, Any],
    table_key: str,
    id_key: str,
    id_value: Any,
) -> dict[str, Any]:
    expected = str(id_value or "")
    if not expected:
        return {}
    for row in _rows(control_state.get(table_key)):
        if str(row.get(id_key) or "") == expected:
            return dict(row)
    return {}


def _rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _table(conn: sa.engine.Connection, table_name: str) -> sa.Table:
    return sa.Table(table_name, sa.MetaData(), autoload_with=conn)


def _upsert_row(
    conn: sa.engine.Connection,
    table_name: str,
    pk_name: str,
    row: dict[str, Any],
) -> None:
    table = _table(conn, table_name)
    pk_value = row[pk_name]
    existing = conn.execute(
        sa.select(table.c[pk_name]).where(table.c[pk_name] == pk_value)
    ).first()
    values = {key: value for key, value in row.items() if key in table.c}
    if existing:
        conn.execute(table.update().where(table.c[pk_name] == pk_value).values(**values))
        return
    conn.execute(table.insert().values(**values))


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]
    return f"{prefix}:{digest}"


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = str(item)
        if text not in seen:
            seen.add(text)
            result.append(text)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
