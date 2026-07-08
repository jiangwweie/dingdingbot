#!/usr/bin/env python3
"""Read-only verifier for the temporary tiny-live submit goal.

TEMPORARY(L2-L9-closure): this verifier exists only while
``temp_tiny_live_protected_submit`` is the narrow live aperture for validating
ENTRY + SL + TP1 exchange behavior. Delete it with the temporary submit mode
after the full real-submit/protection/reconciliation/settlement/review chain is
closed.

The script reads PG only. It does not call FinalGate, Operation Layer, exchange
APIs, OrderLifecycle, live profile mutation, sizing mutation, or any write path.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy import text


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.pg_dsn import is_sync_postgres_dsn, normalize_sync_postgres_dsn  # noqa: E402


TEMP_SUBMIT_MODE = "temp_tiny_live_protected_submit"
LIVE_PROTECTION_SET_STATUSES = {"submitted", "reconciled", "closed"}
LIVE_PROTECTION_ORDER_STATUSES = {
    "submitted",
    "open",
    "partially_filled",
    "filled",
    "replaced",
}


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if not args.database_url:
        print("ERROR: PG_DATABASE_URL or --database-url is required", file=sys.stderr)
        return 2
    database_url = normalize_sync_postgres_dsn(args.database_url)
    if not args.allow_non_postgres_for_test and not is_sync_postgres_dsn(database_url):
        print("ERROR: temporary live submit verifier requires PostgreSQL DSN", file=sys.stderr)
        return 2

    engine = sa.create_engine(database_url)
    try:
        with engine.connect() as conn:
            report = build_temp_tiny_live_submit_goal_report(
                conn,
                protected_submit_attempt_id=args.protected_submit_attempt_id,
            )
    finally:
        engine.dispose()

    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, default=_json_default))
    else:
        print(report["status"])
    return 0 if report["goal_verified"] else 2


def build_temp_tiny_live_submit_goal_report(
    conn: sa.engine.Connection,
    *,
    protected_submit_attempt_id: str | None = None,
) -> dict[str, Any]:
    attempt = _attempt(conn, protected_submit_attempt_id=protected_submit_attempt_id)
    blockers: list[str] = []
    if not attempt:
        blockers.append("temp_tiny_live_submitted_attempt_missing")
        return _report(
            blockers=blockers,
            attempt={},
            protection_set={},
            protection_orders=[],
        )

    blockers.extend(_attempt_blockers(attempt))
    protection_set = _protection_set(conn, str(attempt["protected_submit_attempt_id"]))
    if not protection_set:
        blockers.append("temp_tiny_live_exit_protection_set_missing")
        protection_orders: list[dict[str, Any]] = []
    else:
        blockers.extend(_protection_set_blockers(protection_set))
        protection_orders = _protection_orders(
            conn,
            str(protection_set["exit_protection_set_id"]),
        )
        blockers.extend(_protection_order_blockers(protection_orders))

    return _report(
        blockers=blockers,
        attempt=attempt,
        protection_set=protection_set,
        protection_orders=protection_orders,
    )


def _attempt(
    conn: sa.engine.Connection,
    *,
    protected_submit_attempt_id: str | None,
) -> dict[str, Any]:
    filters = ["submit_mode = :submit_mode"]
    params: dict[str, Any] = {"submit_mode": TEMP_SUBMIT_MODE}
    if protected_submit_attempt_id:
        filters.append("protected_submit_attempt_id = :attempt_id")
        params["attempt_id"] = protected_submit_attempt_id
    row = conn.execute(
        text(
            f"""
            SELECT *
            FROM brc_ticket_bound_protected_submit_attempts
            WHERE {' AND '.join(filters)}
            ORDER BY updated_at_ms DESC, created_at_ms DESC, protected_submit_attempt_id DESC
            LIMIT 1
            """
        ),
        params,
    ).mappings().first()
    return _normalize_row(row)


def _protection_set(conn: sa.engine.Connection, attempt_id: str) -> dict[str, Any]:
    row = conn.execute(
        text(
            """
            SELECT *
            FROM brc_ticket_bound_exit_protection_sets
            WHERE protected_submit_attempt_id = :attempt_id
            ORDER BY updated_at_ms DESC, created_at_ms DESC, exit_protection_set_id DESC
            LIMIT 1
            """
        ),
        {"attempt_id": attempt_id},
    ).mappings().first()
    return _normalize_row(row)


def _protection_orders(conn: sa.engine.Connection, protection_set_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            """
            SELECT *
            FROM brc_ticket_bound_exit_protection_orders
            WHERE exit_protection_set_id = :set_id
            ORDER BY role, updated_at_ms DESC, exit_protection_order_id DESC
            """
        ),
        {"set_id": protection_set_id},
    ).mappings()
    return [_normalize_row(row) for row in rows]


def _attempt_blockers(attempt: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if attempt.get("status") != "submitted":
        blockers.append(f"temp_tiny_live_attempt_not_submitted:{attempt.get('status')}")
    for key in (
        "submit_allowed",
        "official_operation_layer_submit_called",
        "exchange_write_called",
        "order_created",
        "order_lifecycle_called",
    ):
        if not _is_true(attempt.get(key)):
            blockers.append(f"temp_tiny_live_attempt_flag_false:{key}")
    for key in (
        "withdrawal_or_transfer_created",
        "live_profile_changed",
        "order_sizing_changed",
    ):
        if not _is_falseish(attempt.get(key)):
            blockers.append(f"temp_tiny_live_forbidden_effect:{key}")
    submit_result = _as_dict(attempt.get("submit_result"))
    if submit_result.get("status") != "exchange_submit_orders_submitted":
        blockers.append(f"temp_tiny_live_submit_result_status:{submit_result.get('status')}")
    submitted_roles = {
        str(order.get("order_role") or "")
        for order in submit_result.get("submitted_orders", [])
        if isinstance(order, dict)
    }
    missing_roles = {"ENTRY", "SL", "TP1"} - submitted_roles
    for role in sorted(missing_roles):
        blockers.append(f"temp_tiny_live_submit_result_order_missing:{role}")
    return blockers


def _protection_set_blockers(protection_set: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    status = str(protection_set.get("status") or "")
    if status not in LIVE_PROTECTION_SET_STATUSES:
        blockers.append(f"temp_tiny_live_exit_protection_set_status:{status or 'missing'}")
    if not _is_true(protection_set.get("protection_complete")):
        blockers.append("temp_tiny_live_exit_protection_not_complete")
    if not str(protection_set.get("sl_order_id") or "").strip():
        blockers.append("temp_tiny_live_sl_order_id_missing")
    if not str(protection_set.get("tp1_order_id") or "").strip():
        blockers.append("temp_tiny_live_tp1_order_id_missing")
    return blockers


def _protection_order_blockers(orders: list[dict[str, Any]]) -> list[str]:
    blockers: list[str] = []
    by_role = {str(order.get("role") or ""): order for order in orders}
    for role in ("SL", "TP1"):
        order = by_role.get(role)
        if not order:
            blockers.append(f"temp_tiny_live_exit_protection_order_missing:{role}")
            continue
        status = str(order.get("status") or "")
        if status not in LIVE_PROTECTION_ORDER_STATUSES:
            blockers.append(f"temp_tiny_live_exit_protection_order_status:{role}:{status}")
        if not _is_true(order.get("reduce_only")):
            blockers.append(f"temp_tiny_live_exit_protection_reduce_only_missing:{role}")
        if not str(order.get("exchange_order_id") or "").strip():
            blockers.append(f"temp_tiny_live_exit_protection_exchange_order_id_missing:{role}")
        if role == "SL" and _decimal_or_none(order.get("trigger_price")) is None:
            blockers.append("temp_tiny_live_exit_protection_sl_trigger_price_missing")
        if role == "TP1" and _decimal_or_none(order.get("price")) is None:
            blockers.append("temp_tiny_live_exit_protection_tp1_price_missing")
    return blockers


def _report(
    *,
    blockers: list[str],
    attempt: dict[str, Any],
    protection_set: dict[str, Any],
    protection_orders: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema": "brc.temp_tiny_live_submit_goal_verifier.v1",
        "status": "temp_tiny_live_submit_goal_verified" if not blockers else "blocked",
        "goal_verified": not blockers,
        "blockers": blockers,
        "protected_submit_attempt_id": attempt.get("protected_submit_attempt_id"),
        "ticket_id": attempt.get("ticket_id"),
        "operation_submit_command_id": attempt.get("operation_submit_command_id"),
        "strategy_group_id": attempt.get("strategy_group_id"),
        "symbol": attempt.get("symbol"),
        "side": attempt.get("side"),
        "submit_mode": attempt.get("submit_mode"),
        "attempt_status": attempt.get("status"),
        "exchange_write_called": _is_true(attempt.get("exchange_write_called")),
        "order_created": _is_true(attempt.get("order_created")),
        "order_lifecycle_called": _is_true(attempt.get("order_lifecycle_called")),
        "exit_protection_set_id": protection_set.get("exit_protection_set_id"),
        "exit_protection_status": protection_set.get("status"),
        "exit_protection_complete": _is_true(protection_set.get("protection_complete")),
        "exit_protection_order_roles": sorted(
            str(order.get("role") or "") for order in protection_orders
        ),
        "safety_invariants": {
            "finalgate_called_by_verifier": False,
            "operation_layer_called_by_verifier": False,
            "exchange_called_by_verifier": False,
            "order_created_by_verifier": False,
            "order_lifecycle_called_by_verifier": False,
            "remote_files_modified_by_verifier": False,
            "live_profile_changed_by_verifier": False,
            "order_sizing_changed_by_verifier": False,
        },
    }


def _normalize_row(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    return {key: _json_value(value) for key, value in dict(row).items()}


def _json_value(value: Any) -> Any:
    if isinstance(value, str) and value[:1] in {"[", "{"}:
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _as_dict(value: Any) -> dict[str, Any]:
    value = _json_value(value)
    return value if isinstance(value, dict) else {}


def _is_true(value: Any) -> bool:
    return value is True or value == 1


def _is_falseish(value: Any) -> bool:
    return value in {False, None, "", 0}


def _decimal_or_none(value: Any) -> Decimal | None:
    if value in {None, ""}:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument("--protected-submit-attempt-id", default="")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--allow-non-postgres-for-test",
        action="store_true",
        help="Allow SQLite or other SQLAlchemy URLs only for local unit tests.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
