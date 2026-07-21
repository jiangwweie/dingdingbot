#!/usr/bin/env python3
"""Materialize ticket-bound exit protection from PG submit results.

This is the first post-submit lifecycle owner:

protected submit attempt
-> confirmed filled entry
-> ticket-bound SL + TP1 protection set in PG

The materializer does not call FinalGate, Operation Layer, OrderLifecycle, or
the exchange. It records only the machine-checkable protection set that already
exists in the official ticket-bound submit result.
"""

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
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

from src.application.action_time.lifecycle_safety_core import (  # noqa: E402
    classify_exit_protection_materialization,
)


AUTHORITY_BOUNDARY = (
    "ticket_bound_exit_protection_materializer; PG lifecycle/protection set "
    "only; no FinalGate, Operation Layer, exchange, profile, sizing, "
    "withdrawal, or transfer authority"
)


def materialize_ticket_bound_exit_protection_set(
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
            lifecycle={},
            protection_set={},
            blockers=["protected_submit_attempt_id_required"],
            next_action="provide_protected_submit_attempt_id",
        )

    attempt = _attempt_by_id(conn, attempt_id)
    if not attempt:
        return _result(
            "blocked",
            now_ms=now_ms,
            lifecycle={},
            protection_set={},
            blockers=["protected_submit_attempt_missing"],
            next_action="repair_ticket_bound_protected_submit_attempt",
        )

    existing = _protection_set_by_attempt(conn, attempt_id)
    if existing and existing.get("protection_complete") in {True, 1}:
        lifecycle = _lifecycle_by_ticket(conn, str(existing.get("ticket_id") or ""))
        result = _result(
            str(lifecycle.get("status") or "position_protected"),
            now_ms=now_ms,
            lifecycle=lifecycle,
            protection_set=existing,
            blockers=_json_list(existing.get("blockers")),
            next_action="run_ticket_bound_post_submit_closure",
        )
        result["idempotent_existing_protection_set"] = True
        return result

    existing_lifecycle = _lifecycle_by_ticket(conn, str(attempt.get("ticket_id") or ""))
    blockers = _attempt_blockers(
        attempt,
        existing_lifecycle=existing_lifecycle,
    )
    submit_request = _as_dict(attempt.get("submit_request"))
    entry_request = _order_by_role(submit_request.get("orders", []), "ENTRY")
    current_orders = _typed_exchange_command_orders(conn, attempt_id=attempt_id)
    entry_order = _order_by_role(current_orders, "ENTRY")
    sl_order = _order_by_role(current_orders, "SL")
    tp1_order = _order_by_role(current_orders, "TP1")
    entry_fill = _entry_fill(entry_request=entry_request, entry_order=entry_order)
    blockers.extend(entry_fill["blockers"])
    blockers.extend(_exit_order_blockers(sl_order, role="SL"))
    blockers.extend(_exit_order_blockers(tp1_order, role="TP1"))
    blockers.extend(
        _partial_entry_protection_quantity_blockers(
            entry_fill=entry_fill,
            sl_order=sl_order,
            tp1_order=tp1_order,
        )
    )
    classification = classify_exit_protection_materialization(
        attempt=attempt,
        entry_order=entry_order,
        sl_order=sl_order,
        tp1_order=tp1_order,
        blockers=blockers,
    )

    lifecycle = _lifecycle_row(
        attempt,
        existing_lifecycle=existing_lifecycle,
        status=classification.status,
        first_blocker=classification.first_blocker,
        blockers=list(classification.blockers),
        entry_order=entry_order,
        entry_fill=entry_fill,
        exit_protection_set_id=(
            _stable_id(
                "ticket_exit_protection_set",
                str(attempt["ticket_id"]),
                str(entry_order.get("exchange_order_id") or ""),
            )
            if not blockers
            else None
        ),
        now_ms=now_ms,
    )
    _upsert_row(
        conn,
        "brc_ticket_bound_order_lifecycle_runs",
        "lifecycle_run_id",
        lifecycle,
    )
    _insert_event(
        conn,
        lifecycle,
        classification.event_type,
        (
            {
                "blockers": list(classification.blockers),
                "lifecycle_status": classification.status,
                "next_action": classification.next_action,
            }
            if classification.blockers
            else {
                "entry_order": entry_order,
                "entry_fill": {
                    "exchange_order_id": entry_order.get("exchange_order_id"),
                    "fill_qty": str(entry_fill.get("filled_qty") or ""),
                    "fill_price": str(entry_fill.get("avg_price") or ""),
                    "fee": entry_order.get("fee"),
                    "fill_time_ms": entry_order.get("fill_time_ms") or now_ms,
                },
            }
        ),
        now_ms=now_ms,
    )

    if classification.blockers:
        return _result(
            classification.status,
            now_ms=now_ms,
            lifecycle=lifecycle,
            protection_set={},
            blockers=list(classification.blockers),
            next_action=classification.next_action,
        )

    protection_set = _protection_set_row(
        attempt,
        lifecycle=lifecycle,
        entry_order=entry_order,
        entry_fill=entry_fill,
        sl_order=sl_order,
        tp1_order=tp1_order,
        now_ms=now_ms,
    )
    _upsert_row(
        conn,
        "brc_ticket_bound_exit_protection_sets",
        "exit_protection_set_id",
        protection_set,
    )
    for order in _protection_order_rows(
        protection_set=protection_set,
        sl_order=sl_order,
        tp1_order=tp1_order,
        submit_request=submit_request,
        now_ms=now_ms,
    ):
        _upsert_row(
            conn,
            "brc_ticket_bound_exit_protection_orders",
            "exit_protection_order_id",
            order,
        )
        _insert_event(
            conn,
            lifecycle,
            "sl_submitted" if order["role"] == "SL" else "tp1_submitted",
            {"exit_protection_order_id": order["exit_protection_order_id"]},
            now_ms=now_ms,
        )
    _insert_event(
        conn,
        lifecycle,
        "exit_protection_materialization_started",
        {"exit_protection_set_id": protection_set["exit_protection_set_id"]},
        now_ms=now_ms,
    )

    return _result(
        "position_protected",
        now_ms=now_ms,
        lifecycle=lifecycle,
        protection_set=protection_set,
        blockers=[],
        next_action="run_ticket_bound_post_submit_closure",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument("--require-database-url", action="store_true")
    parser.add_argument("--protected-submit-attempt-id", required=True)
    parser.add_argument("--now-ms", type=int, default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--allow-non-postgres-for-test",
        action="store_true",
        help="Allow SQLite or other SQLAlchemy URLs only for local unit tests.",
    )
    args = parser.parse_args(argv)
    if args.require_database_url and not args.database_url:
        print("ERROR: PG_DATABASE_URL is required for exit protection", file=sys.stderr)
        return 2
    if not args.database_url:
        print("ERROR: --database-url or PG_DATABASE_URL is required", file=sys.stderr)
        return 2
    if (
        not args.allow_non_postgres_for_test
        and not args.database_url.startswith(("postgresql://", "postgresql+psycopg://"))
    ):
        print("ERROR: exit protection materializer requires PostgreSQL DSN", file=sys.stderr)
        return 2

    engine = sa.create_engine(args.database_url)
    try:
        with engine.begin() as conn:
            report = materialize_ticket_bound_exit_protection_set(
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


def _attempt_by_id(conn: sa.engine.Connection, attempt_id: str) -> dict[str, Any]:
    table = _table(conn, "brc_ticket_bound_protected_submit_attempts")
    row = conn.execute(
        sa.select(table).where(table.c.protected_submit_attempt_id == attempt_id)
    ).mappings().first()
    return dict(row) if row else {}


def _protection_set_by_attempt(conn: sa.engine.Connection, attempt_id: str) -> dict[str, Any]:
    table = _table(conn, "brc_ticket_bound_exit_protection_sets")
    row = conn.execute(
        sa.select(table).where(table.c.protected_submit_attempt_id == attempt_id)
    ).mappings().first()
    return dict(row) if row else {}


def _lifecycle_by_ticket(conn: sa.engine.Connection, ticket_id: str) -> dict[str, Any]:
    table = _table(conn, "brc_ticket_bound_order_lifecycle_runs")
    row = conn.execute(sa.select(table).where(table.c.ticket_id == ticket_id)).mappings().first()
    return dict(row) if row else {}


def _typed_exchange_command_orders(
    conn: sa.engine.Connection,
    *,
    attempt_id: str,
) -> list[dict[str, Any]]:
    """Expose typed durable command truth in the legacy order-shaped reducer."""

    table = _table(conn, "brc_ticket_bound_exchange_commands")
    rows = conn.execute(
        sa.select(table)
        .where(table.c.protected_submit_attempt_id == attempt_id)
        .order_by(table.c.command_generation.asc(), table.c.updated_at_ms.asc())
    ).mappings()
    orders: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        role = str(row.get("order_role") or "").upper()
        state = str(row.get("command_state") or "")
        if role in {"SL", "TP1"} and state == "reconciled_absent":
            continue
        executed_qty = row.get("executed_qty")
        status = str(row.get("exchange_order_status") or "")
        if role == "ENTRY" and row.get("result_facts_complete") in {True, 1}:
            status = "FILLED" if _decimal(executed_qty) > 0 else status
        elif state in {"confirmed_submitted", "reconciled_submitted"} and not status:
            status = "OPEN"
        orders.append(
            {
                "exchange_command_id": str(row["exchange_command_id"]),
                "local_order_id": str(row.get("local_order_id") or ""),
                "exchange_order_id": str(row.get("exchange_order_id") or ""),
                "order_role": role,
                "status": status,
                "filled_qty": _decimal_text(executed_qty),
                "average_exec_price": _decimal_text(row.get("average_exec_price")),
                "amount": _decimal_text(row.get("amount")),
                "price": _decimal_text(row.get("price")),
                "trigger_price": _decimal_text(row.get("stop_price")),
                "reduce_only": row.get("reduce_only") in {True, 1},
                "command_state": state,
            }
        )
    return orders


def _decimal_text(value: Any) -> str | None:
    return str(value) if value is not None else None


def _attempt_blockers(
    attempt: dict[str, Any],
    *,
    existing_lifecycle: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    reconciled_entry_authority = _reconciled_entry_fill_authority(
        existing_lifecycle
    )
    if attempt.get("status") != "submitted" and not reconciled_entry_authority:
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
    submit_result = _as_dict(attempt.get("submit_result"))
    if (
        submit_result.get("status") != "exchange_submit_orders_submitted"
        and not reconciled_entry_authority
    ):
        blockers.append(f"submit_result_not_submitted:{submit_result.get('status')}")
    return blockers


def _reconciled_entry_fill_authority(lifecycle: dict[str, Any]) -> bool:
    return (
        str(lifecycle.get("status") or "")
        in {"protection_missing", "protection_degraded", "protection_submit_failed"}
        and lifecycle.get("entry_fill_confirmed") in {True, 1}
        and bool(str(lifecycle.get("entry_exchange_order_id") or "").strip())
        and _decimal(lifecycle.get("entry_filled_qty")) > 0
        and _decimal(lifecycle.get("entry_avg_price")) > 0
    )


def _entry_fill(
    *,
    entry_request: dict[str, Any],
    entry_order: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    requested_qty = _decimal(entry_request.get("amount"))
    filled_qty = _decimal(entry_order.get("filled_qty"))
    avg_price = _decimal(entry_order.get("average_exec_price"))
    status = str(entry_order.get("status") or "").strip().lower()
    if not entry_order:
        blockers.append("entry_order_missing")
    if not str(entry_order.get("exchange_order_id") or "").strip():
        blockers.append("entry_exchange_order_id_missing")
    if requested_qty <= 0:
        blockers.append("entry_requested_qty_missing")
    if status not in {"filled", "partially_filled", "partiallyfilled"}:
        blockers.append(f"entry_status_not_filled:{status or 'missing'}")
    if filled_qty <= 0:
        blockers.append("entry_filled_qty_missing")
    if avg_price <= 0:
        blockers.append("entry_average_exec_price_missing")
    return {
        "blockers": blockers,
        "requested_qty": requested_qty,
        "filled_qty": filled_qty,
        "avg_price": avg_price,
    }


def _partial_entry_protection_quantity_blockers(
    *,
    entry_fill: dict[str, Any],
    sl_order: dict[str, Any],
    tp1_order: dict[str, Any],
) -> list[str]:
    requested_qty = _decimal(entry_fill.get("requested_qty"))
    filled_qty = _decimal(entry_fill.get("filled_qty"))
    if filled_qty <= 0 or requested_qty <= 0 or filled_qty >= requested_qty:
        return []
    blockers: list[str] = []
    sl_qty = _qty(sl_order)
    tp1_qty = _qty(tp1_order)
    if sl_qty != filled_qty:
        blockers.append("partial_entry_sl_qty_not_actual_fill")
    if tp1_qty <= 0 or tp1_qty > filled_qty:
        blockers.append("partial_entry_tp1_qty_not_bounded_by_actual_fill")
    return blockers


def _exit_order_blockers(order: dict[str, Any], *, role: str) -> list[str]:
    blockers: list[str] = []
    if not order:
        return [f"{role.lower()}_exchange_order_missing"]
    if str(order.get("order_role") or "").upper() != role:
        blockers.append(f"{role.lower()}_role_mismatch")
    if order.get("reduce_only") is not True:
        blockers.append(f"{role.lower()}_reduce_only_missing")
    if not str(order.get("exchange_order_id") or "").strip():
        blockers.append(f"{role.lower()}_exchange_order_id_missing")
    if _decimal(order.get("amount")) <= 0 and _decimal(order.get("qty")) <= 0:
        blockers.append(f"{role.lower()}_qty_missing")
    if role == "TP1" and _decimal(order.get("price")) <= 0:
        blockers.append("tp1_price_missing")
    if role == "SL" and _decimal(order.get("trigger_price")) <= 0:
        blockers.append("sl_trigger_price_missing")
    return blockers


def _lifecycle_row(
    attempt: dict[str, Any],
    *,
    existing_lifecycle: dict[str, Any],
    status: str,
    first_blocker: str | None,
    blockers: list[str],
    entry_order: dict[str, Any],
    entry_fill: dict[str, Any],
    exit_protection_set_id: str | None,
    now_ms: int,
) -> dict[str, Any]:
    return {
        "lifecycle_run_id": str(existing_lifecycle.get("lifecycle_run_id") or "")
        or _stable_id("ticket_order_lifecycle", str(attempt["ticket_id"])),
        "ticket_id": str(attempt["ticket_id"]),
        "protected_submit_attempt_id": str(attempt["protected_submit_attempt_id"]),
        "strategy_group_id": str(attempt["strategy_group_id"]),
        "symbol": str(attempt["symbol"]),
        "side": str(attempt["side"]),
        "runtime_profile_id": str(attempt["runtime_profile_id"]),
        "status": status,
        "entry_local_order_id": str(entry_order.get("local_order_id") or "") or None,
        "entry_exchange_order_id": str(entry_order.get("exchange_order_id") or "") or None,
        "entry_fill_confirmed": not entry_fill["blockers"],
        "entry_filled_qty": entry_fill["filled_qty"] if entry_fill["filled_qty"] > 0 else None,
        "entry_avg_price": entry_fill["avg_price"] if entry_fill["avg_price"] > 0 else None,
        "exit_protection_set_id": exit_protection_set_id,
        "first_blocker": first_blocker,
        "blockers": blockers,
        "warnings": [],
        "authority_boundary": AUTHORITY_BOUNDARY,
        "created_at_ms": int(
            existing_lifecycle.get("created_at_ms")
            or attempt.get("created_at_ms")
            or now_ms
        ),
        "updated_at_ms": now_ms,
    }


def _protection_set_row(
    attempt: dict[str, Any],
    *,
    lifecycle: dict[str, Any],
    entry_order: dict[str, Any],
    entry_fill: dict[str, Any],
    sl_order: dict[str, Any],
    tp1_order: dict[str, Any],
    now_ms: int,
) -> dict[str, Any]:
    tp1_qty = _qty(tp1_order)
    runner_qty = max(entry_fill["filled_qty"] - tp1_qty, Decimal("0"))
    return {
        "exit_protection_set_id": str(lifecycle["exit_protection_set_id"]),
        "ticket_id": str(attempt["ticket_id"]),
        "protected_submit_attempt_id": str(attempt["protected_submit_attempt_id"]),
        "entry_local_order_id": str(entry_order["local_order_id"]),
        "entry_exchange_order_id": str(entry_order["exchange_order_id"]),
        "strategy_group_id": str(attempt["strategy_group_id"]),
        "symbol": str(attempt["symbol"]),
        "side": str(attempt["side"]),
        "entry_filled_qty": entry_fill["filled_qty"],
        "entry_avg_price": entry_fill["avg_price"],
        "status": "submitted",
        "sl_order_id": str(sl_order["local_order_id"]),
        "tp1_order_id": str(tp1_order["local_order_id"]),
        "runner_qty": runner_qty,
        "protection_complete": True,
        "reconciled_with_exchange": False,
        "first_blocker": None,
        "blockers": [],
        "warnings": [],
        "authority_boundary": AUTHORITY_BOUNDARY,
        "created_at_ms": now_ms,
        "updated_at_ms": now_ms,
    }


def _protection_order_rows(
    *,
    protection_set: dict[str, Any],
    sl_order: dict[str, Any],
    tp1_order: dict[str, Any],
    submit_request: dict[str, Any],
    now_ms: int,
) -> list[dict[str, Any]]:
    request_orders = submit_request.get("orders", [])
    sl_request = _order_by_role(request_orders, "SL")
    tp1_request = _order_by_role(request_orders, "TP1")
    return [
        _protection_order_row(
            protection_set=protection_set,
            order=sl_order,
            request=sl_request,
            role="SL",
            order_type="STOP_MARKET",
            now_ms=now_ms,
        ),
        _protection_order_row(
            protection_set=protection_set,
            order=tp1_order,
            request=tp1_request,
            role="TP1",
            order_type="LIMIT",
            now_ms=now_ms,
        ),
    ]


def _protection_order_row(
    *,
    protection_set: dict[str, Any],
    order: dict[str, Any],
    request: dict[str, Any],
    role: str,
    order_type: str,
    now_ms: int,
) -> dict[str, Any]:
    local_order_id = str(order.get("local_order_id") or request.get("local_order_id") or "")
    return {
        "exit_protection_order_id": _stable_id(
            "ticket_exit_protection_order",
            str(protection_set["exit_protection_set_id"]),
            role,
            local_order_id,
        ),
        "exit_protection_set_id": str(protection_set["exit_protection_set_id"]),
        "ticket_id": str(protection_set["ticket_id"]),
        "role": role,
        "local_order_id": local_order_id,
        "exchange_order_id": str(order["exchange_order_id"]),
        "status": "submitted",
        "order_type": order_type,
        "side": str(request.get("gateway_side") or ""),
        "qty": _qty(order) or _decimal(request.get("amount")),
        "price": _decimal(request.get("price")) if role == "TP1" else None,
        "trigger_price": _decimal(request.get("trigger_price")) if role == "SL" else None,
        "reduce_only": True,
        "replaces_exit_protection_order_id": None,
        "created_at_ms": now_ms,
        "updated_at_ms": now_ms,
    }


def _insert_event(
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
        "event_payload": payload,
        "created_at_ms": now_ms,
    }
    _upsert_row(
        conn,
        "brc_ticket_bound_lifecycle_events",
        "lifecycle_event_id",
        event,
    )


def _result(
    status: str,
    *,
    now_ms: int,
    lifecycle: dict[str, Any],
    protection_set: dict[str, Any],
    blockers: list[str],
    next_action: str,
) -> dict[str, Any]:
    return {
        "schema": "brc.ticket_bound_exit_protection_materializer.v1",
        "status": status,
        "now_ms": now_ms,
        "ticket_id": lifecycle.get("ticket_id") or protection_set.get("ticket_id"),
        "protected_submit_attempt_id": lifecycle.get("protected_submit_attempt_id")
        or protection_set.get("protected_submit_attempt_id"),
        "lifecycle_run_id": lifecycle.get("lifecycle_run_id"),
        "exit_protection_set_id": protection_set.get("exit_protection_set_id"),
        "protection_complete": protection_set.get("protection_complete") is True,
        "first_blocker": _first(blockers),
        "blockers": _dedupe(blockers),
        "next_action": next_action,
        "authority_boundary": AUTHORITY_BOUNDARY,
        "lifecycle": lifecycle,
        "protection_set": protection_set,
    }


def _order_by_role(orders: Any, role: str) -> dict[str, Any]:
    expected = role.upper()
    for order in orders or []:
        if isinstance(order, dict) and str(order.get("order_role") or "").upper() == expected:
            return dict(order)
    return {}


def _qty(order: dict[str, Any]) -> Decimal:
    return _decimal(order.get("amount") if order.get("amount") is not None else order.get("qty"))


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


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


def _json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    return []


def _upsert_row(
    conn: sa.engine.Connection,
    table_name: str,
    id_column: str,
    row: dict[str, Any],
) -> None:
    table = _table(conn, table_name)
    values = {
        column.name: _sql_value(row.get(column.name))
        for column in table.columns
        if column.name in row
    }
    existing = conn.execute(
        sa.select(table.c[id_column]).where(table.c[id_column] == values[id_column])
    ).first()
    if existing:
        conn.execute(
            table.update().where(table.c[id_column] == values[id_column]).values(**values)
        )
    else:
        conn.execute(table.insert().values(**values))


def _sql_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    return value


def _table(conn: sa.engine.Connection, table_name: str) -> sa.Table:
    return sa.Table(table_name, sa.MetaData(), autoload_with=conn)


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value)
        if text not in seen:
            result.append(text)
            seen.add(text)
    return result


def _first(values: list[str]) -> str | None:
    return _dedupe(values)[0] if values else None


if __name__ == "__main__":
    raise SystemExit(main())
