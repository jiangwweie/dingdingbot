#!/usr/bin/env python3
"""Materialize ticket-bound runner mutation command records.

This module creates and records the official command intent for replacing the
full-size SL after TP1 fill. It never calls exchange cancel/replace/submit
methods by itself.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import time
from typing import Any

import sqlalchemy as sa


AUTHORITY_BOUNDARY = (
    "ticket_bound_runner_mutation_command; PG command intent/result record only; "
    "no FinalGate, Operation Layer bypass, exchange mutation, profile, sizing, "
    "withdrawal, or transfer authority"
)


def prepare_ticket_bound_runner_mutation_command(
    conn: sa.engine.Connection,
    *,
    exit_protection_set_id: str,
    now_ms: int | None = None,
) -> dict[str, Any]:
    now_ms = int(now_ms or time.time() * 1000)
    set_id = str(exit_protection_set_id or "").strip()
    if not set_id:
        return _result(
            "blocked",
            now_ms=now_ms,
            command={},
            blockers=["exit_protection_set_id_required"],
            next_action="provide_exit_protection_set_id",
        )
    existing = _row_by_id(
        conn,
        "brc_ticket_bound_runner_mutation_commands",
        "exit_protection_set_id",
        set_id,
    )
    if existing:
        return _result(
            str(existing.get("status") or "blocked"),
            now_ms=now_ms,
            command=existing,
            blockers=list(existing.get("blockers") or []),
            next_action="use_existing_runner_mutation_command",
            extra={"idempotent_existing_runner_mutation_command": True},
        )
    protection_set = _row_by_id(
        conn,
        "brc_ticket_bound_exit_protection_sets",
        "exit_protection_set_id",
        set_id,
    )
    if not protection_set:
        return _result(
            "blocked",
            now_ms=now_ms,
            command={},
            blockers=["exit_protection_set_missing"],
            next_action="repair_ticket_bound_exit_protection_set",
        )
    orders = _orders_for_set(conn, set_id)
    sl_order = _role_order(orders, "SL")
    tp1_order = _role_order(orders, "TP1")
    runner_order = _role_order(orders, "RUNNER_SL")
    blockers = _command_blockers(
        protection_set=protection_set,
        sl_order=sl_order,
        tp1_order=tp1_order,
        runner_order=runner_order,
    )
    if blockers:
        return _result(
            "blocked",
            now_ms=now_ms,
            command={},
            blockers=blockers,
            next_action=_next_action(blockers),
        )
    command = _command_row(
        protection_set=protection_set,
        sl_order=sl_order,
        tp1_order=tp1_order,
        now_ms=now_ms,
    )
    _upsert_row(
        conn,
        "brc_ticket_bound_runner_mutation_commands",
        "runner_mutation_command_id",
        command,
    )
    _mark_lifecycle_runner_mutation_pending(
        conn,
        protection_set=protection_set,
        command=command,
        now_ms=now_ms,
    )
    return _result(
        "prepared",
        now_ms=now_ms,
        command=command,
        blockers=[],
        next_action="execute_runner_mutation_through_official_operation_path",
    )


def record_ticket_bound_runner_mutation_result(
    conn: sa.engine.Connection,
    *,
    runner_mutation_command_id: str,
    result_payload: dict[str, Any],
    now_ms: int | None = None,
) -> dict[str, Any]:
    now_ms = int(now_ms or time.time() * 1000)
    command_id = str(runner_mutation_command_id or "").strip()
    command = _row_by_id(
        conn,
        "brc_ticket_bound_runner_mutation_commands",
        "runner_mutation_command_id",
        command_id,
    )
    if not command:
        return _result(
            "blocked",
            now_ms=now_ms,
            command={},
            blockers=["runner_mutation_command_missing"],
            next_action="prepare_ticket_bound_runner_mutation_command",
        )
    blockers = _result_blockers(result_payload)
    updated = {
        **command,
        "status": "failed" if blockers else "result_recorded",
        "first_blocker": blockers[0] if blockers else None,
        "blockers": blockers,
        "result_payload": result_payload,
        "updated_at_ms": now_ms,
    }
    _upsert_row(
        conn,
        "brc_ticket_bound_runner_mutation_commands",
        "runner_mutation_command_id",
        updated,
    )
    return _result(
        str(updated["status"]),
        now_ms=now_ms,
        command=updated,
        blockers=blockers,
        next_action=(
            "materialize_ticket_bound_runner_protection_adjustment"
            if not blockers
            else "repair_runner_mutation_or_flatten"
        ),
    )


def _command_blockers(
    *,
    protection_set: dict[str, Any],
    sl_order: dict[str, Any],
    tp1_order: dict[str, Any],
    runner_order: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if protection_set.get("protection_complete") is not True:
        blockers.append("exit_protection_set_not_complete")
    if not sl_order:
        blockers.append("sl_protection_order_missing")
    elif not str(sl_order.get("exchange_order_id") or ""):
        blockers.append("old_sl_exchange_order_id_missing")
    if not tp1_order:
        blockers.append("tp1_protection_order_missing")
    elif str(tp1_order.get("status") or "").lower() != "filled":
        blockers.append(f"tp1_not_filled:{tp1_order.get('status')}")
    elif not str(tp1_order.get("exchange_order_id") or ""):
        blockers.append("tp1_exchange_order_id_missing")
    if runner_order:
        blockers.append("runner_sl_already_materialized")
    if _decimal(protection_set.get("runner_qty")) <= 0:
        blockers.append("runner_qty_not_positive")
    return _dedupe(blockers)


def _command_row(
    *,
    protection_set: dict[str, Any],
    sl_order: dict[str, Any],
    tp1_order: dict[str, Any],
    now_ms: int,
) -> dict[str, Any]:
    command_id = _stable_id(
        "ticket_runner_mutation_command",
        str(protection_set["exit_protection_set_id"]),
    )
    runner_qty = _decimal(protection_set.get("runner_qty"))
    command_plan = {
        "schema": "brc.ticket_bound_runner_mutation_command_plan.v1",
        "cancel_old_sl": {
            "exchange_order_id": sl_order["exchange_order_id"],
            "local_order_id": sl_order["local_order_id"],
        },
        "submit_runner_sl": {
            "qty": str(runner_qty),
            "trigger_price": str(sl_order.get("trigger_price") or ""),
            "side": str(sl_order.get("side") or ""),
            "reduce_only": True,
            "replaces_exit_protection_order_id": sl_order[
                "exit_protection_order_id"
            ],
        },
    }
    return {
        "runner_mutation_command_id": command_id,
        "exit_protection_set_id": str(protection_set["exit_protection_set_id"]),
        "ticket_id": str(protection_set["ticket_id"]),
        "protected_submit_attempt_id": str(
            protection_set["protected_submit_attempt_id"]
        ),
        "strategy_group_id": str(protection_set["strategy_group_id"]),
        "symbol": str(protection_set["symbol"]),
        "side": str(protection_set["side"]),
        "old_sl_order_id": str(sl_order["local_order_id"]),
        "old_sl_exchange_order_id": str(sl_order["exchange_order_id"]),
        "tp1_order_id": str(tp1_order["local_order_id"]),
        "tp1_exchange_order_id": str(tp1_order["exchange_order_id"]),
        "runner_qty": runner_qty,
        "status": "prepared",
        "first_blocker": None,
        "blockers": [],
        "command_plan": command_plan,
        "result_payload": {},
        "authority_boundary": AUTHORITY_BOUNDARY,
        "created_at_ms": now_ms,
        "updated_at_ms": now_ms,
    }


def _result_blockers(result_payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = [
        str(blocker)
        for blocker in result_payload.get("blockers") or []
        if str(blocker)
    ]
    if result_payload.get("old_sl_cancelled") is not True:
        blockers.append("old_sl_cancel_not_confirmed")
    if not str(result_payload.get("runner_sl_exchange_order_id") or "").strip():
        blockers.append("runner_sl_exchange_order_id_missing")
    if result_payload.get("runner_sl_submitted") is not True:
        blockers.append("runner_sl_submit_not_confirmed")
    if result_payload.get("exchange_write_called") is not True:
        blockers.append("runner_mutation_exchange_write_not_confirmed")
    for key in ("withdrawal_or_transfer_created", "live_profile_changed", "order_sizing_changed"):
        if result_payload.get(key) not in {False, None, "", 0}:
            blockers.append(f"runner_mutation_forbidden_effect:{key}")
    return _dedupe(blockers)


def _mark_lifecycle_runner_mutation_pending(
    conn: sa.engine.Connection,
    *,
    protection_set: dict[str, Any],
    command: dict[str, Any],
    now_ms: int,
) -> None:
    lifecycle = _row_by_id(
        conn,
        "brc_ticket_bound_order_lifecycle_runs",
        "ticket_id",
        str(protection_set.get("ticket_id") or ""),
    )
    if not lifecycle:
        return
    row = {
        **lifecycle,
        "status": "runner_mutation_pending",
        "first_blocker": None,
        "blockers": [],
        "updated_at_ms": now_ms,
    }
    _upsert_row(conn, "brc_ticket_bound_order_lifecycle_runs", "lifecycle_run_id", row)
    event = {
        "lifecycle_event_id": _stable_id(
            "ticket_lifecycle_event",
            str(row["lifecycle_run_id"]),
            "runner_mutation_pending",
            str(now_ms),
        ),
        "lifecycle_run_id": str(row["lifecycle_run_id"]),
        "ticket_id": str(row["ticket_id"]),
        "protected_submit_attempt_id": str(row["protected_submit_attempt_id"]),
        "event_type": "runner_mutation_pending",
        "event_payload": {
            "runner_mutation_command_id": command["runner_mutation_command_id"],
            "next_action": "execute_runner_mutation_through_official_operation_path",
        },
        "created_at_ms": now_ms,
    }
    _upsert_row(conn, "brc_ticket_bound_lifecycle_events", "lifecycle_event_id", event)


def _next_action(blockers: list[str]) -> str:
    if any(blocker.startswith("tp1_not_filled") for blocker in blockers):
        return "wait_for_tp1_fill"
    return "repair_ticket_bound_runner_mutation_inputs"


def _orders_for_set(
    conn: sa.engine.Connection,
    exit_protection_set_id: str,
) -> list[dict[str, Any]]:
    table = _table(conn, "brc_ticket_bound_exit_protection_orders")
    return [
        dict(row)
        for row in conn.execute(
            sa.select(table).where(
                table.c.exit_protection_set_id == exit_protection_set_id
            )
        ).mappings()
    ]


def _role_order(orders: list[dict[str, Any]], role: str) -> dict[str, Any]:
    for order in orders:
        if str(order.get("role") or "").upper() == role.upper():
            return dict(order)
    return {}


def _row_by_id(
    conn: sa.engine.Connection,
    table_name: str,
    id_column: str,
    id_value: str,
) -> dict[str, Any]:
    if not id_value:
        return {}
    table = _table(conn, table_name)
    row = conn.execute(sa.select(table).where(table.c[id_column] == id_value)).mappings().first()
    return dict(row) if row else {}


def _upsert_row(
    conn: sa.engine.Connection,
    table_name: str,
    id_column: str,
    row: dict[str, Any],
) -> None:
    table = _table(conn, table_name)
    values = {
        column.name: row.get(column.name)
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


def _table(conn: sa.engine.Connection, table_name: str) -> sa.Table:
    return sa.Table(table_name, sa.MetaData(), autoload_with=conn)


def _result(
    status: str,
    *,
    now_ms: int,
    command: dict[str, Any],
    blockers: list[str],
    next_action: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "schema": "brc.ticket_bound_runner_mutation_command.v1",
        "status": status,
        "now_ms": now_ms,
        "runner_mutation_command_id": command.get("runner_mutation_command_id"),
        "exit_protection_set_id": command.get("exit_protection_set_id"),
        "ticket_id": command.get("ticket_id"),
        "first_blocker": blockers[0] if blockers else None,
        "blockers": blockers,
        "next_action": next_action,
        "authority_boundary": AUTHORITY_BOUNDARY,
        "command": command,
    }
    if extra:
        payload.update(extra)
    return payload


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]
    return f"{prefix}:{digest}"


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = str(item)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")
