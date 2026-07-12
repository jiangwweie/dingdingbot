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
from decimal import Decimal, InvalidOperation

import sqlalchemy as sa


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.infrastructure.runtime_control_state_repository import (  # noqa: E402
    PgBackedRuntimeControlStateRepository,
    RuntimeControlStateRepositoryError,
)
from src.application.action_time.lifecycle_safety_core import (  # noqa: E402
    reduce_lifecycle_decision,
)


AUTHORITY_BOUNDARY = (
    "ticket_bound_post_submit_closure; records reconciliation/settlement/review "
    "state only; no exchange/order/runtime authority"
)
PROTECTION_COMPLETE_STATUSES = {"submitted", "reconciled", "runner_protected", "closed"}
FINAL_EXIT_ROLES = {"SL", "RUNNER_SL", "TP1"}
LIVE_PROTECTION_ORDER_STATUSES = {
    "planned",
    "submitted",
    "open",
    "partially_filled",
    "cancel_pending",
    "replace_pending",
}
FINAL_LIFECYCLE_CLOSABLE_STATUSES = {
    "position_protected",
    "tp1_filled",
    "sl_adjust_pending",
    "runner_protected",
    "final_exit_detected",
    "reconciliation_matched",
    "budget_settled",
    "review_recorded",
    "lifecycle_closed",
}


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
    if existing and str(existing.get("status") or "") == "closed":
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
    blockers.extend(_exit_protection_blockers(conn, attempt))
    protection_state = _protection_state(conn, attempt)
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
    if existing:
        closure["created_at_ms"] = int(existing.get("created_at_ms") or now_ms)
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


def materialize_ticket_bound_lifecycle_closure(
    conn: sa.engine.Connection,
    *,
    protected_submit_attempt_id: str,
    final_exit_exchange_order_id: str,
    final_position_flat_confirmed: bool,
    reconciliation_evidence_id: str,
    settlement_evidence_id: str,
    review_evidence_id: str,
    final_exit_role: str = "RUNNER_SL",
    realized_pnl: str | Decimal | None = None,
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

    materialize_ticket_bound_post_submit_closure(
        conn,
        protected_submit_attempt_id=attempt_id,
        now_ms=now_ms,
    )
    attempt = _attempt_by_id(conn, attempt_id)
    closure = _post_submit_closure_for_attempt(conn, attempt_id)
    if not attempt:
        return _result(
            "blocked",
            now_ms=now_ms,
            blockers=["protected_submit_attempt_missing"],
            closure=closure,
            next_action="repair_ticket_bound_protected_submit_attempt",
        )

    protection_set = _exit_protection_set_for_attempt(conn, attempt)
    lifecycle = _lifecycle_by_ticket(conn, str(attempt.get("ticket_id") or ""))
    if (
        closure.get("status") == "closed"
        and lifecycle.get("status") == "lifecycle_closed"
        and protection_set.get("status") == "closed"
    ):
        return _result(
            "closed",
            now_ms=now_ms,
            blockers=[],
            closure=closure,
            next_action="lifecycle_closed",
            extra={"idempotent_existing_lifecycle_closure": True},
        )
    protection_orders = _exit_protection_orders_for_set(
        conn, str(protection_set.get("exit_protection_set_id") or "")
    )
    final_exit_role = str(final_exit_role or "").strip().upper()
    final_exit_exchange_order_id = str(final_exit_exchange_order_id or "").strip()
    reconciliation_evidence_id = str(reconciliation_evidence_id or "").strip()
    settlement_evidence_id = str(settlement_evidence_id or "").strip()
    review_evidence_id = str(review_evidence_id or "").strip()
    realized_pnl_decimal = _decimal_or_none(realized_pnl)

    blockers = _attempt_blockers(attempt)
    blockers.extend(_exit_protection_blockers(conn, attempt))
    blockers.extend(
        _lifecycle_closure_blockers(
            conn,
            lifecycle=lifecycle,
            protection_orders=protection_orders,
            final_exit_role=final_exit_role,
            final_exit_exchange_order_id=final_exit_exchange_order_id,
            final_position_flat_confirmed=final_position_flat_confirmed,
            reconciliation_evidence_id=reconciliation_evidence_id,
            settlement_evidence_id=settlement_evidence_id,
            review_evidence_id=review_evidence_id,
        )
    )
    blockers = _dedupe(blockers)
    if blockers:
        closure_update = {
            **closure,
            "status": "blocked",
            "protection_state": _protection_state(conn, attempt),
            "reconciliation_state": "blocked",
            "settlement_state": "blocked",
            "review_state": "blocked",
            "first_blocker": blockers[0],
            "blockers": blockers,
            "next_action": "repair_ticket_bound_lifecycle_closure_inputs",
            "updated_at_ms": now_ms,
        }
        _upsert_row(
            conn,
            "brc_ticket_bound_post_submit_closures",
            "post_submit_closure_id",
            closure_update,
        )
        return _result(
            "blocked",
            now_ms=now_ms,
            blockers=blockers,
            closure=closure_update,
            next_action="repair_ticket_bound_lifecycle_closure_inputs",
        )

    final_order = _protection_order_by_role_and_exchange_id(
        protection_orders,
        role=final_exit_role,
        exchange_order_id=final_exit_exchange_order_id,
    )
    _mark_protection_order_status(conn, final_order, status="filled", now_ms=now_ms)
    protection_update = {
        **protection_set,
        "status": "closed",
        "reconciled_with_exchange": True,
        "first_blocker": None,
        "blockers": [],
        "updated_at_ms": now_ms,
    }
    _upsert_row(
        conn,
        "brc_ticket_bound_exit_protection_sets",
        "exit_protection_set_id",
        protection_update,
    )
    closure_update = {
        **closure,
        "status": "closed",
        "protection_state": "submitted",
        "reconciliation_state": "matched",
        "settlement_state": "released",
        "review_state": "recorded",
        "first_blocker": None,
        "blockers": [],
        "warnings": [],
        "reconciliation_evidence": {
            "reconciliation_evidence_id": reconciliation_evidence_id,
            "final_exit_exchange_order_id": final_exit_exchange_order_id,
            "final_exit_role": final_exit_role,
            "final_position_flat_confirmed": True,
        },
        "settlement_evidence": {
            "settlement_evidence_id": settlement_evidence_id,
            "realized_pnl": str(realized_pnl_decimal)
            if realized_pnl_decimal is not None
            else None,
        },
        "review_evidence": {"review_evidence_id": review_evidence_id},
        "next_action": "lifecycle_closed",
        "updated_at_ms": now_ms,
    }
    _upsert_row(
        conn,
        "brc_ticket_bound_post_submit_closures",
        "post_submit_closure_id",
        closure_update,
    )
    lifecycle_decision = reduce_lifecycle_decision(
        current_status=str(lifecycle.get("status") or ""),
        target_status="lifecycle_closed",
        event_type="lifecycle_closed",
    )
    lifecycle_update = {
        **lifecycle,
        "status": lifecycle_decision.status,
        "first_blocker": lifecycle_decision.first_blocker,
        "blockers": list(lifecycle_decision.blockers),
        "updated_at_ms": now_ms,
    }
    _upsert_row(
        conn,
        "brc_ticket_bound_order_lifecycle_runs",
        "lifecycle_run_id",
        lifecycle_update,
    )
    event_payload = {
        "post_submit_closure_id": closure_update["post_submit_closure_id"],
        "final_exit_exchange_order_id": final_exit_exchange_order_id,
        "final_exit_role": final_exit_role,
        "reconciliation_evidence_id": reconciliation_evidence_id,
        "settlement_evidence_id": settlement_evidence_id,
        "review_evidence_id": review_evidence_id,
        "realized_pnl": str(realized_pnl_decimal)
        if realized_pnl_decimal is not None
        else None,
    }
    for event_type in ("final_exit_detected", lifecycle_decision.event_type):
        _insert_lifecycle_event(
            conn,
            lifecycle_update,
            event_type,
            event_payload,
            now_ms=now_ms,
        )
    return _result(
        "closed",
        now_ms=now_ms,
        blockers=[],
        closure=closure_update,
        next_action=lifecycle_decision.next_action,
        extra={"lifecycle_decision": lifecycle_decision.to_dict()},
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument("--require-database-url", action="store_true")
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--protected-submit-attempt-id")
    selector.add_argument("--latest-submitted", action="store_true")
    parser.add_argument("--close-lifecycle", action="store_true")
    parser.add_argument("--final-exit-exchange-order-id", default="")
    parser.add_argument("--final-exit-role", default="RUNNER_SL")
    parser.add_argument("--final-position-flat-confirmed", action="store_true")
    parser.add_argument("--reconciliation-evidence-id", default="")
    parser.add_argument("--settlement-evidence-id", default="")
    parser.add_argument("--review-evidence-id", default="")
    parser.add_argument("--realized-pnl", default=None)
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
            if args.close_lifecycle:
                if not args.protected_submit_attempt_id:
                    print(
                        "ERROR: --close-lifecycle requires --protected-submit-attempt-id",
                        file=sys.stderr,
                    )
                    return 2
                report = materialize_ticket_bound_lifecycle_closure(
                    conn,
                    protected_submit_attempt_id=args.protected_submit_attempt_id,
                    final_exit_exchange_order_id=args.final_exit_exchange_order_id,
                    final_exit_role=args.final_exit_role,
                    final_position_flat_confirmed=args.final_position_flat_confirmed,
                    reconciliation_evidence_id=args.reconciliation_evidence_id,
                    settlement_evidence_id=args.settlement_evidence_id,
                    review_evidence_id=args.review_evidence_id,
                    realized_pnl=args.realized_pnl,
                    now_ms=args.now_ms,
                )
            elif args.latest_submitted:
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
    if not _entry_fill_confirmed(attempt):
        blockers.append("entry_fill_not_confirmed")
    if not _submitted_reduce_only_role(submit_result, "SL"):
        blockers.append("sl_reduce_only_exchange_order_missing")
    if not _submitted_reduce_only_role(submit_result, "TP1"):
        blockers.append("tp1_reduce_only_exchange_order_missing")
    return _dedupe(blockers)


def _exit_protection_blockers(
    conn: sa.engine.Connection,
    attempt: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    protection_set = _exit_protection_set_for_attempt(conn, attempt)
    if not protection_set:
        return ["ticket_bound_exit_protection_set_missing"]
    if protection_set.get("status") not in PROTECTION_COMPLETE_STATUSES:
        blockers.append(f"exit_protection_set_status:{protection_set.get('status')}")
    if protection_set.get("protection_complete") is not True:
        blockers.append("exit_protection_set_not_complete")
    if str(protection_set.get("sl_order_id") or "").strip() == "":
        blockers.append("exit_protection_set_sl_missing")
    if str(protection_set.get("tp1_order_id") or "").strip() == "":
        blockers.append("exit_protection_set_tp1_missing")
    return blockers


def _protection_state(conn: sa.engine.Connection, attempt: dict[str, Any]) -> str:
    protection_set = _exit_protection_set_for_attempt(conn, attempt)
    if not protection_set:
        return "missing"
    return (
        "submitted"
        if protection_set.get("status") in PROTECTION_COMPLETE_STATUSES
        and protection_set.get("protection_complete") is True
        else "missing"
    )


def _attempt_by_id(conn: sa.engine.Connection, attempt_id: str) -> dict[str, Any]:
    if not sa.inspect(conn).has_table("brc_ticket_bound_protected_submit_attempts"):
        return {}
    table = _table(conn, "brc_ticket_bound_protected_submit_attempts")
    row = conn.execute(
        sa.select(table).where(table.c.protected_submit_attempt_id == attempt_id)
    ).mappings().first()
    return dict(row) if row else {}


def _post_submit_closure_for_attempt(
    conn: sa.engine.Connection,
    attempt_id: str,
) -> dict[str, Any]:
    if not sa.inspect(conn).has_table("brc_ticket_bound_post_submit_closures"):
        return {}
    table = _table(conn, "brc_ticket_bound_post_submit_closures")
    row = conn.execute(
        sa.select(table).where(table.c.protected_submit_attempt_id == attempt_id)
    ).mappings().first()
    return dict(row) if row else {}


def _lifecycle_by_ticket(conn: sa.engine.Connection, ticket_id: str) -> dict[str, Any]:
    if not sa.inspect(conn).has_table("brc_ticket_bound_order_lifecycle_runs"):
        return {}
    table = _table(conn, "brc_ticket_bound_order_lifecycle_runs")
    row = conn.execute(
        sa.select(table).where(table.c.ticket_id == ticket_id)
    ).mappings().first()
    return dict(row) if row else {}


def _exit_protection_orders_for_set(
    conn: sa.engine.Connection,
    exit_protection_set_id: str,
) -> list[dict[str, Any]]:
    if not exit_protection_set_id:
        return []
    if not sa.inspect(conn).has_table("brc_ticket_bound_exit_protection_orders"):
        return []
    table = _table(conn, "brc_ticket_bound_exit_protection_orders")
    return [
        dict(row)
        for row in conn.execute(
            sa.select(table).where(
                table.c.exit_protection_set_id == exit_protection_set_id
            )
        ).mappings()
    ]


def _lifecycle_closure_blockers(
    conn: sa.engine.Connection,
    *,
    lifecycle: dict[str, Any],
    protection_orders: list[dict[str, Any]],
    final_exit_role: str,
    final_exit_exchange_order_id: str,
    final_position_flat_confirmed: bool,
    reconciliation_evidence_id: str,
    settlement_evidence_id: str,
    review_evidence_id: str,
) -> list[str]:
    blockers: list[str] = []
    if not lifecycle:
        blockers.append("ticket_bound_lifecycle_run_missing")
    elif lifecycle.get("status") not in FINAL_LIFECYCLE_CLOSABLE_STATUSES:
        blockers.append(f"lifecycle_status_not_closable:{lifecycle.get('status')}")
    if final_exit_role not in FINAL_EXIT_ROLES:
        blockers.append(f"final_exit_role_invalid:{final_exit_role or 'missing'}")
    if not final_exit_exchange_order_id:
        blockers.append("final_exit_exchange_order_id_required")
    if not final_position_flat_confirmed:
        blockers.append("final_position_flat_not_confirmed")
    if not reconciliation_evidence_id:
        blockers.append("reconciliation_evidence_id_required")
    if not settlement_evidence_id:
        blockers.append("settlement_evidence_id_required")
    if not review_evidence_id:
        blockers.append("review_evidence_id_required")
    if lifecycle:
        blockers.extend(
            _closure_evidence_event_blockers(
                conn,
                lifecycle=lifecycle,
                final_exit_role=final_exit_role,
                final_exit_exchange_order_id=final_exit_exchange_order_id,
                final_position_flat_confirmed=final_position_flat_confirmed,
                reconciliation_evidence_id=reconciliation_evidence_id,
                settlement_evidence_id=settlement_evidence_id,
                review_evidence_id=review_evidence_id,
            )
        )
    if final_exit_role == "RUNNER_SL" and lifecycle.get("status") not in {
        "runner_protected",
        "final_exit_detected",
        "reconciliation_matched",
        "budget_settled",
        "review_recorded",
        "lifecycle_closed",
    }:
        blockers.append("runner_sl_not_protected_before_final_exit")
    if final_exit_exchange_order_id and final_exit_role in FINAL_EXIT_ROLES:
        final_order = _protection_order_by_role_and_exchange_id(
            protection_orders,
            role=final_exit_role,
            exchange_order_id=final_exit_exchange_order_id,
        )
        if not final_order:
            blockers.append("final_exit_order_not_in_ticket_protection_set")
        elif final_order.get("reduce_only") is not True:
            blockers.append("final_exit_order_reduce_only_missing")
    if final_position_flat_confirmed:
        blockers.extend(
            _live_protection_order_blockers_after_flat(
                protection_orders,
                final_exit_role=final_exit_role,
                final_exit_exchange_order_id=final_exit_exchange_order_id,
            )
        )
    return _dedupe(blockers)


def _closure_evidence_event_blockers(
    conn: sa.engine.Connection,
    *,
    lifecycle: dict[str, Any],
    final_exit_role: str,
    final_exit_exchange_order_id: str,
    final_position_flat_confirmed: bool,
    reconciliation_evidence_id: str,
    settlement_evidence_id: str,
    review_evidence_id: str,
) -> list[str]:
    blockers: list[str] = []
    specs = (
        (
            "reconciliation_matched",
            "reconciliation_evidence_id",
            reconciliation_evidence_id,
            "reconciliation_evidence_event_missing",
        ),
        (
            "budget_settled",
            "settlement_evidence_id",
            settlement_evidence_id,
            "settlement_evidence_event_missing",
        ),
        (
            "review_recorded",
            "review_evidence_id",
            review_evidence_id,
            "review_evidence_event_missing",
        ),
    )
    for event_type, payload_key, evidence_id, blocker in specs:
        if not evidence_id:
            continue
        if not _lifecycle_event_with_payload(
            conn,
            lifecycle=lifecycle,
            event_type=event_type,
            expected_payload={payload_key: evidence_id},
        ):
            blockers.append(blocker)
    if final_position_flat_confirmed:
        if not _lifecycle_event_with_payload(
            conn,
            lifecycle=lifecycle,
            event_type="reconciliation_matched",
            expected_payload={
                "reconciliation_evidence_id": reconciliation_evidence_id,
                "final_exit_exchange_order_id": final_exit_exchange_order_id,
                "final_exit_role": final_exit_role,
                "final_position_flat_confirmed": True,
            },
        ):
            blockers.append("final_position_flat_evidence_event_missing")
    return blockers


def _lifecycle_event_with_payload(
    conn: sa.engine.Connection,
    *,
    lifecycle: dict[str, Any],
    event_type: str,
    expected_payload: dict[str, Any],
) -> bool:
    if not sa.inspect(conn).has_table("brc_ticket_bound_lifecycle_events"):
        return False
    table = _table(conn, "brc_ticket_bound_lifecycle_events")
    rows = conn.execute(
        sa.select(table).where(
            table.c.lifecycle_run_id == str(lifecycle.get("lifecycle_run_id") or ""),
            table.c.ticket_id == str(lifecycle.get("ticket_id") or ""),
            table.c.protected_submit_attempt_id
            == str(lifecycle.get("protected_submit_attempt_id") or ""),
            table.c.event_type == event_type,
        )
    ).mappings()
    for row in rows:
        payload = _as_dict(row.get("event_payload"))
        if _payload_matches(payload, expected_payload):
            return True
    return False


def _payload_matches(payload: dict[str, Any], expected_payload: dict[str, Any]) -> bool:
    for key, expected_value in expected_payload.items():
        actual = payload.get(key)
        if isinstance(expected_value, bool):
            if actual is not expected_value:
                return False
            continue
        if str(actual or "") != str(expected_value or ""):
            return False
    return True


def _protection_order_by_role_and_exchange_id(
    protection_orders: list[dict[str, Any]],
    *,
    role: str,
    exchange_order_id: str,
) -> dict[str, Any]:
    for order in protection_orders:
        if str(order.get("role") or "").upper() != role:
            continue
        if str(order.get("exchange_order_id") or "") != exchange_order_id:
            continue
        return dict(order)
    return {}


def _live_protection_order_blockers_after_flat(
    protection_orders: list[dict[str, Any]],
    *,
    final_exit_role: str,
    final_exit_exchange_order_id: str,
) -> list[str]:
    blockers: list[str] = []
    for order in protection_orders:
        role = str(order.get("role") or "").upper()
        exchange_order_id = str(order.get("exchange_order_id") or "")
        if role == final_exit_role and exchange_order_id == final_exit_exchange_order_id:
            continue
        status = str(order.get("status") or "").strip().lower()
        if status in LIVE_PROTECTION_ORDER_STATUSES:
            blockers.append(f"position_closed_protection_live:{role or 'unknown'}")
    return blockers


def _mark_protection_order_status(
    conn: sa.engine.Connection,
    order: dict[str, Any],
    *,
    status: str,
    now_ms: int,
) -> None:
    row = {**order, "status": status, "updated_at_ms": now_ms}
    _upsert_row(
        conn,
        "brc_ticket_bound_exit_protection_orders",
        "exit_protection_order_id",
        row,
    )


def _insert_lifecycle_event(
    conn: sa.engine.Connection,
    lifecycle: dict[str, Any],
    event_type: str,
    payload: dict[str, Any],
    *,
    now_ms: int,
) -> None:
    event = {
        "lifecycle_event_id": _stable_id(
            "ticket_lifecycle_event",
            str(lifecycle["lifecycle_run_id"]),
            event_type,
            str(now_ms),
        ),
        "lifecycle_run_id": str(lifecycle["lifecycle_run_id"]),
        "ticket_id": str(lifecycle["ticket_id"]),
        "protected_submit_attempt_id": str(lifecycle["protected_submit_attempt_id"]),
        "event_type": event_type,
        "event_payload": _json_safe(payload),
        "created_at_ms": now_ms,
    }
    _upsert_row(conn, "brc_ticket_bound_lifecycle_events", "lifecycle_event_id", event)


def _exit_protection_set_for_attempt(
    conn: sa.engine.Connection,
    attempt: dict[str, Any],
) -> dict[str, Any]:
    if not sa.inspect(conn).has_table("brc_ticket_bound_exit_protection_sets"):
        return {}
    table = _table(conn, "brc_ticket_bound_exit_protection_sets")
    row = conn.execute(
        sa.select(table).where(
            table.c.protected_submit_attempt_id
            == str(attempt.get("protected_submit_attempt_id") or "")
        )
    ).mappings().first()
    return dict(row) if row else {}


def _entry_fill_confirmed(attempt: dict[str, Any]) -> bool:
    submit_request = _as_dict(attempt.get("submit_request"))
    submit_result = _as_dict(attempt.get("submit_result"))
    entry_request = _order_by_role(submit_request.get("orders", []), "ENTRY")
    entry_order = _order_by_role(submit_result.get("submitted_orders", []), "ENTRY")
    if not entry_request or not entry_order:
        return False
    if not str(entry_order.get("exchange_order_id") or "").strip():
        return False
    if str(entry_order.get("status") or "").strip().lower() != "filled":
        return False
    try:
        requested_qty = Decimal(str(entry_request.get("amount") or "0"))
        filled_qty = Decimal(str(entry_order.get("filled_qty") or "0"))
        average_exec_price = Decimal(str(entry_order.get("average_exec_price") or "0"))
    except (InvalidOperation, ValueError):
        return False
    return requested_qty > 0 and filled_qty >= requested_qty and average_exec_price > 0


def _order_by_role(orders: Any, role: str) -> dict[str, Any]:
    expected = role.upper()
    for order in orders or []:
        if isinstance(order, dict) and str(order.get("order_role") or "").upper() == expected:
            return dict(order)
    return {}


def _submitted_reduce_only_role(submit_result: dict[str, Any], role: str) -> bool:
    expected = role.upper()
    for order in submit_result.get("submitted_orders", []):
        if not isinstance(order, dict):
            continue
        if str(order.get("order_role") or "").upper() != expected:
            continue
        if order.get("reduce_only") is not True:
            continue
        if str(order.get("exchange_order_id") or "").strip():
            return True
    return False


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
        "reconciliation_evidence": closure.get("reconciliation_evidence", {}),
        "settlement_evidence": closure.get("settlement_evidence", {}),
        "review_evidence": closure.get("review_evidence", {}),
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
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


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
