#!/usr/bin/env python3
"""Prepare and execute ticket-bound orphan protection cleanup commands.

This module handles the case where reconciliation proves the position is flat
while ticket-bound reduce-only protection orders remain live. It only cancels
protection orders already linked to the ticket-bound PG protection set.
Exchange-only unknown orders remain blocked until a stronger identity proof
path exists.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import time
from typing import Any

import sqlalchemy as sa

from src.application.action_time.capital_safety_freeze_projection import (
    resolve_current_scope_freeze,
)


AUTHORITY_BOUNDARY = (
    "ticket_bound_orphan_protection_cleanup_command; requires existing "
    "ticket-bound exit protection set and lifecycle state "
    "position_closed_protection_live; calls injected gateway cancel_order only "
    "for linked reduce-only protection refs; no FinalGate, profile, sizing, "
    "withdrawal, transfer, submit, or file authority"
)


OPEN_PROTECTION_STATUSES = {"submitted", "open", "partially_filled"}


def prepare_ticket_bound_orphan_protection_cleanup_command(
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
            result_payload={},
            blockers=["exit_protection_set_id_required"],
            next_action="provide_exit_protection_set_id",
        )
    existing = _row_by_id(
        conn,
        "brc_ticket_bound_orphan_protection_cleanup_commands",
        "exit_protection_set_id",
        set_id,
    )
    if existing:
        return _result(
            str(existing.get("status") or "blocked"),
            now_ms=now_ms,
            command=existing,
            result_payload=_as_dict(existing.get("result_payload")),
            blockers=_json_list(existing.get("blockers")),
            next_action="use_existing_orphan_protection_cleanup_command",
            extra={"idempotent_existing_orphan_protection_cleanup_command": True},
        )

    protection_set = _row_by_id(
        conn,
        "brc_ticket_bound_exit_protection_sets",
        "exit_protection_set_id",
        set_id,
    )
    lifecycle = _row_by_id(
        conn,
        "brc_ticket_bound_order_lifecycle_runs",
        "ticket_id",
        str(protection_set.get("ticket_id") or ""),
    )
    orders = _orders_for_set(conn, set_id)
    blockers = _prepare_blockers(
        protection_set=protection_set,
        lifecycle=lifecycle,
        orders=orders,
    )
    if blockers:
        return _result(
            "blocked",
            now_ms=now_ms,
            command={},
            result_payload={},
            blockers=blockers,
            next_action="repair_orphan_protection_cleanup_inputs",
        )

    command = _command_row(
        protection_set=protection_set,
        lifecycle=lifecycle,
        cancel_orders=_cancelable_orders(orders),
        now_ms=now_ms,
    )
    _upsert_row(
        conn,
        "brc_ticket_bound_orphan_protection_cleanup_commands",
        "orphan_protection_cleanup_command_id",
        command,
    )
    return _result(
        "prepared",
        now_ms=now_ms,
        command=command,
        result_payload={},
        blockers=[],
        next_action="execute_ticket_bound_orphan_protection_cleanup_command",
    )


async def execute_ticket_bound_orphan_protection_cleanup_command(
    conn: sa.engine.Connection,
    *,
    orphan_protection_cleanup_command_id: str,
    gateway: Any,
    now_ms: int | None = None,
) -> dict[str, Any]:
    now_ms = int(now_ms or time.time() * 1000)
    return _result(
        "blocked",
        now_ms=now_ms,
        command={},
        result_payload={},
        blockers=["legacy_direct_orphan_cleanup_executor_retired"],
        next_action="materialize_durable_orphan_cleanup_exchange_commands",
        extra={"exchange_write_called": False},
    )
    command_id = str(orphan_protection_cleanup_command_id or "").strip()
    if not command_id:
        return _result(
            "blocked",
            now_ms=now_ms,
            command={},
            result_payload={},
            blockers=["orphan_protection_cleanup_command_id_required"],
            next_action="provide_orphan_protection_cleanup_command_id",
        )
    command = _row_by_id(
        conn,
        "brc_ticket_bound_orphan_protection_cleanup_commands",
        "orphan_protection_cleanup_command_id",
        command_id,
    )
    if not command:
        return _result(
            "blocked",
            now_ms=now_ms,
            command={},
            result_payload={},
            blockers=["orphan_protection_cleanup_command_missing"],
            next_action="prepare_ticket_bound_orphan_protection_cleanup_command",
        )
    status = str(command.get("status") or "")
    if status == "result_recorded":
        return _result(
            "result_recorded",
            now_ms=now_ms,
            command=command,
            result_payload=_as_dict(command.get("result_payload")),
            blockers=[],
            next_action="continue_ticket_bound_lifecycle_closure",
            extra={"idempotent_existing_orphan_protection_cleanup_result": True},
        )
    if status != "prepared":
        return _result(
            "blocked",
            now_ms=now_ms,
            command=command,
            result_payload={},
            blockers=[f"orphan_protection_cleanup_command_not_prepared:{status or 'missing'}"],
            next_action="repair_orphan_protection_cleanup_command_status",
        )

    stale_blockers = _pre_execution_state_blockers(conn, command=command)
    if stale_blockers:
        result_payload = _result_payload(
            command=command,
            canceled_orders=[],
            blockers=stale_blockers,
            exchange_write_called=False,
            extra={"status": "orphan_protection_cleanup_pre_execution_blocked"},
        )
        updated = _record_result(
            conn,
            command=command,
            status="failed",
            blockers=stale_blockers,
            result_payload=result_payload,
            now_ms=now_ms,
            update_lifecycle=False,
        )
        return _result(
            "blocked",
            now_ms=now_ms,
            command=updated,
            result_payload=result_payload,
            blockers=stale_blockers,
            next_action="repair_or_reprepare_orphan_protection_cleanup_command",
        )

    command_plan = _as_dict(command.get("command_plan"))
    cancel_orders = [
        dict(order)
        for order in command_plan.get("cancel_orders", [])
        if isinstance(order, dict)
    ]
    blockers = _cancel_order_plan_blockers(cancel_orders)
    if blockers:
        result_payload = _result_payload(
            command=command,
            canceled_orders=[],
            blockers=blockers,
            exchange_write_called=False,
        )
        updated = _record_result(
            conn,
            command=command,
            status="failed",
            blockers=blockers,
            result_payload=result_payload,
            now_ms=now_ms,
        )
        return _result(
            "failed",
            now_ms=now_ms,
            command=updated,
            result_payload=result_payload,
            blockers=blockers,
            next_action="repair_orphan_protection_cleanup_or_manual_recovery",
        )

    canceled_orders: list[dict[str, Any]] = []
    for order in cancel_orders:
        try:
            cancel_result = await _retired_direct_exchange_mutation(
                exchange_order_id=str(order["exchange_order_id"]),
                symbol=str(command["symbol"]),
            )
        except Exception as exc:
            blockers = [
                "orphan_protection_cancel_failed:"
                f"{order.get('role', 'unknown')}:{type(exc).__name__}"
            ]
            result_payload = _result_payload(
                command=command,
                canceled_orders=canceled_orders,
                blockers=blockers,
                exchange_write_called=True,
                extra={"cancel_error": str(exc)},
            )
            updated = _record_result(
                conn,
                command=command,
                status="failed",
                blockers=blockers,
                result_payload=result_payload,
                now_ms=now_ms,
            )
            return _result(
                "failed",
                now_ms=now_ms,
                command=updated,
                result_payload=result_payload,
                blockers=blockers,
                next_action="repair_orphan_protection_cleanup_or_manual_recovery",
            )
        if not _cancel_operation_succeeded(cancel_result):
            blockers = [
                getattr(cancel_result, "error_message", None)
                or getattr(cancel_result, "error_code", None)
                or f"orphan_protection_cancel_not_confirmed:{order.get('role', 'unknown')}"
            ]
            result_payload = _result_payload(
                command=command,
                canceled_orders=canceled_orders,
                blockers=blockers,
                exchange_write_called=True,
            )
            updated = _record_result(
                conn,
                command=command,
                status="failed",
                blockers=blockers,
                result_payload=result_payload,
                now_ms=now_ms,
            )
            return _result(
                "failed",
                now_ms=now_ms,
                command=updated,
                result_payload=result_payload,
                blockers=blockers,
                next_action="repair_orphan_protection_cleanup_or_manual_recovery",
            )
        canceled_orders.append(
            {
                **order,
                "cancel_status": str(getattr(cancel_result, "status", "CANCELED") or "CANCELED"),
            }
        )

    result_payload = _result_payload(
        command=command,
        canceled_orders=canceled_orders,
        blockers=[],
        exchange_write_called=True,
    )
    updated = _record_result(
        conn,
        command=command,
        status="result_recorded",
        blockers=[],
        result_payload=result_payload,
        now_ms=now_ms,
    )
    _apply_successful_cleanup(
        conn,
        command=command,
        canceled_orders=canceled_orders,
        result_payload=result_payload,
        now_ms=now_ms,
    )
    return _result(
        "result_recorded",
        now_ms=now_ms,
        command=updated,
        result_payload=result_payload,
        blockers=[],
        next_action="continue_ticket_bound_lifecycle_closure",
    )


async def _retired_direct_exchange_mutation(**kwargs: Any) -> Any:
    del kwargs
    raise RuntimeError("legacy_direct_orphan_cleanup_executor_retired")


def apply_durable_orphan_cleanup_exchange_commands(
    conn: sa.engine.Connection,
    *,
    orphan_protection_cleanup_command_id: str,
    exchange_commands: list[dict[str, Any]],
    now_ms: int,
) -> dict[str, Any]:
    """Project confirmed durable cancel commands into cleanup state."""

    command = _row_by_id(
        conn,
        "brc_ticket_bound_orphan_protection_cleanup_commands",
        "orphan_protection_cleanup_command_id",
        orphan_protection_cleanup_command_id,
    )
    if not command:
        raise ValueError("orphan_protection_cleanup_command_missing")
    if str(command.get("status") or "") == "result_recorded":
        return command
    canceled_orders: list[dict[str, Any]] = []
    for exchange_command in exchange_commands:
        if str(exchange_command.get("command_state") or "") not in {
            "confirmed_submitted",
            "reconciled_submitted",
        }:
            raise ValueError("orphan_cleanup_exchange_command_not_confirmed")
        canceled_orders.append(
            {
                "exit_protection_order_id": exchange_command.get(
                    "parent_order_id"
                ),
                "role": exchange_command.get("order_role"),
                "exchange_order_id": exchange_command.get(
                    "target_exchange_order_id"
                ),
                "cancel_confirmed": True,
            }
        )
    result_payload = _result_payload(
        command=command,
        canceled_orders=canceled_orders,
        blockers=[],
        exchange_write_called=True,
        extra={"durable_exchange_command_authority": True},
    )
    updated = _record_result(
        conn,
        command=command,
        status="result_recorded",
        blockers=[],
        result_payload=result_payload,
        now_ms=now_ms,
    )
    _apply_successful_cleanup(
        conn,
        command=command,
        canceled_orders=canceled_orders,
        result_payload=result_payload,
        now_ms=now_ms,
    )
    return updated


def _prepare_blockers(
    *,
    protection_set: dict[str, Any],
    lifecycle: dict[str, Any],
    orders: list[dict[str, Any]],
) -> list[str]:
    blockers: list[str] = []
    if not protection_set:
        blockers.append("exit_protection_set_missing")
    if not lifecycle:
        blockers.append("ticket_bound_lifecycle_missing")
    if blockers:
        return blockers
    if str(lifecycle.get("status") or "") != "position_closed_protection_live":
        blockers.append(
            "lifecycle_status_not_cleanup_recoverable:"
            f"{lifecycle.get('status') or 'missing'}"
        )
    if str(protection_set.get("status") or "") != "position_closed_protection_live":
        blockers.append(
            "exit_protection_set_status_not_cleanup_recoverable:"
            f"{protection_set.get('status') or 'missing'}"
        )
    if "position_flat_with_live_protection_orders" not in _json_list(
        lifecycle.get("blockers")
    ):
        blockers.append("position_flat_live_protection_blocker_missing")
    if not _cancelable_orders(orders):
        blockers.append("linked_live_protection_orders_not_found")
    return _dedupe(blockers)


def _pre_execution_state_blockers(
    conn: sa.engine.Connection,
    *,
    command: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    set_id = str(command.get("exit_protection_set_id") or "")
    protection_set = _row_by_id(
        conn,
        "brc_ticket_bound_exit_protection_sets",
        "exit_protection_set_id",
        set_id,
    )
    lifecycle = _row_by_id(
        conn,
        "brc_ticket_bound_order_lifecycle_runs",
        "lifecycle_run_id",
        str(command.get("lifecycle_run_id") or ""),
    )
    orders = _orders_for_set(conn, set_id)
    if not protection_set:
        blockers.append("orphan_cleanup_stale_exit_protection_set_missing")
    if not lifecycle:
        blockers.append("orphan_cleanup_stale_lifecycle_missing")
    if blockers:
        return blockers
    if str(lifecycle.get("status") or "") != "position_closed_protection_live":
        blockers.append(
            "orphan_cleanup_stale_lifecycle_status:"
            f"{lifecycle.get('status') or 'missing'}"
        )
    if str(protection_set.get("status") or "") != "position_closed_protection_live":
        blockers.append(
            "orphan_cleanup_stale_exit_protection_set_status:"
            f"{protection_set.get('status') or 'missing'}"
        )
    planned_ids = _planned_order_ids(command)
    current_ids = {
        str(order.get("exit_protection_order_id") or "")
        for order in _cancelable_orders(orders)
    }
    if not planned_ids:
        blockers.append("orphan_cleanup_cancel_plan_empty")
    elif planned_ids != current_ids:
        blockers.append("orphan_cleanup_stale_cancel_scope_changed")
    for order in _cancelable_orders(orders):
        if order.get("reduce_only") is not True:
            blockers.append(
                f"orphan_cleanup_order_reduce_only_required:{order.get('role')}"
            )
    return _dedupe(blockers)


def _command_row(
    *,
    protection_set: dict[str, Any],
    lifecycle: dict[str, Any],
    cancel_orders: list[dict[str, Any]],
    now_ms: int,
) -> dict[str, Any]:
    command_id = _stable_id(
        "ticket_orphan_protection_cleanup_command",
        str(protection_set["exit_protection_set_id"]),
    )
    command_plan = {
        "schema": "brc.ticket_bound_orphan_protection_cleanup_command_plan.v1",
        "cleanup_action": "cancel_flat_position_live_protection",
        "identity_proof": "linked_ticket_bound_exit_protection_set",
        "cancel_orders": [_cancel_order_plan(order) for order in cancel_orders],
    }
    return {
        "orphan_protection_cleanup_command_id": command_id,
        "exit_protection_set_id": str(protection_set["exit_protection_set_id"]),
        "lifecycle_run_id": str(lifecycle["lifecycle_run_id"]),
        "ticket_id": str(protection_set["ticket_id"]),
        "protected_submit_attempt_id": str(
            protection_set["protected_submit_attempt_id"]
        ),
        "strategy_group_id": str(protection_set["strategy_group_id"]),
        "symbol": str(protection_set["symbol"]),
        "side": str(protection_set["side"]),
        "status": "prepared",
        "cleanup_action": "cancel_flat_position_live_protection",
        "first_blocker": None,
        "blockers": [],
        "command_plan": command_plan,
        "result_payload": {},
        "authority_boundary": AUTHORITY_BOUNDARY,
        "created_at_ms": now_ms,
        "updated_at_ms": now_ms,
    }


def _cancelable_orders(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        dict(order)
        for order in orders
        if str(order.get("role") or "").upper() in {"SL", "TP1", "RUNNER_SL"}
        and str(order.get("status") or "").lower() in OPEN_PROTECTION_STATUSES
        and str(order.get("exchange_order_id") or "").strip()
        and order.get("reduce_only") is True
    ]


def _cancel_order_plan(order: dict[str, Any]) -> dict[str, Any]:
    return {
        "exit_protection_order_id": str(order["exit_protection_order_id"]),
        "role": str(order["role"]),
        "exchange_order_id": str(order["exchange_order_id"]),
        "side": str(order["side"]),
        "qty": str(order["qty"]),
        "reduce_only": order.get("reduce_only") is True,
    }


def _cancel_order_plan_blockers(cancel_orders: list[dict[str, Any]]) -> list[str]:
    blockers: list[str] = []
    if not cancel_orders:
        blockers.append("orphan_cleanup_cancel_orders_empty")
    for order in cancel_orders:
        role = str(order.get("role") or "missing").upper()
        if role not in {"SL", "TP1", "RUNNER_SL"}:
            blockers.append(f"orphan_cleanup_role_invalid:{role}")
        if not str(order.get("exchange_order_id") or "").strip():
            blockers.append(f"orphan_cleanup_exchange_order_id_missing:{role}")
        if order.get("reduce_only") is not True:
            blockers.append(f"orphan_cleanup_reduce_only_required:{role}")
        if _decimal(order.get("qty")) <= 0:
            blockers.append(f"orphan_cleanup_qty_missing:{role}")
    return _dedupe(blockers)


def _planned_order_ids(command: dict[str, Any]) -> set[str]:
    command_plan = _as_dict(command.get("command_plan"))
    return {
        str(order.get("exit_protection_order_id") or "")
        for order in command_plan.get("cancel_orders", [])
        if isinstance(order, dict) and order.get("exit_protection_order_id")
    }


def _record_result(
    conn: sa.engine.Connection,
    *,
    command: dict[str, Any],
    status: str,
    blockers: list[str],
    result_payload: dict[str, Any],
    now_ms: int,
    update_lifecycle: bool = True,
) -> dict[str, Any]:
    updated = {
        **command,
        "status": status,
        "first_blocker": blockers[0] if blockers else None,
        "blockers": blockers,
        "result_payload": result_payload,
        "updated_at_ms": now_ms,
    }
    _upsert_row(
        conn,
        "brc_ticket_bound_orphan_protection_cleanup_commands",
        "orphan_protection_cleanup_command_id",
        updated,
    )
    if status == "failed" and update_lifecycle:
        _mark_cleanup_failed(
            conn,
            command=command,
            blockers=blockers,
            result_payload=result_payload,
            now_ms=now_ms,
        )
    return updated


def _mark_cleanup_failed(
    conn: sa.engine.Connection,
    *,
    command: dict[str, Any],
    blockers: list[str],
    result_payload: dict[str, Any],
    now_ms: int,
) -> None:
    lifecycle = _row_by_id(
        conn,
        "brc_ticket_bound_order_lifecycle_runs",
        "lifecycle_run_id",
        str(command.get("lifecycle_run_id") or ""),
    )
    protection_set = _row_by_id(
        conn,
        "brc_ticket_bound_exit_protection_sets",
        "exit_protection_set_id",
        str(command.get("exit_protection_set_id") or ""),
    )
    first_blocker = blockers[0] if blockers else "orphan_protection_cleanup_failed"
    if protection_set:
        _upsert_row(
            conn,
            "brc_ticket_bound_exit_protection_sets",
            "exit_protection_set_id",
            {
                **protection_set,
                "status": "position_closed_protection_live",
                "reconciled_with_exchange": False,
                "first_blocker": first_blocker,
                "blockers": blockers,
                "updated_at_ms": now_ms,
            },
        )
    if lifecycle:
        lifecycle_update = {
            **lifecycle,
            "status": "position_closed_protection_live",
            "first_blocker": first_blocker,
            "blockers": blockers,
            "updated_at_ms": now_ms,
        }
        _upsert_row(
            conn,
            "brc_ticket_bound_order_lifecycle_runs",
            "lifecycle_run_id",
            lifecycle_update,
        )
        _insert_event(
            conn,
            lifecycle_update,
            "position_closed_protection_live",
            {
                "blockers": blockers,
                "cleanup_result": result_payload,
            },
            now_ms=now_ms,
        )


def _apply_successful_cleanup(
    conn: sa.engine.Connection,
    *,
    command: dict[str, Any],
    canceled_orders: list[dict[str, Any]],
    result_payload: dict[str, Any],
    now_ms: int,
) -> None:
    order_table = _table(conn, "brc_ticket_bound_exit_protection_orders")
    for order in canceled_orders:
        conn.execute(
            order_table.update()
            .where(
                order_table.c.exit_protection_order_id
                == str(order["exit_protection_order_id"])
            )
            .values(status="cancelled", updated_at_ms=now_ms)
        )
    protection_set = _row_by_id(
        conn,
        "brc_ticket_bound_exit_protection_sets",
        "exit_protection_set_id",
        str(command["exit_protection_set_id"]),
    )
    lifecycle = _row_by_id(
        conn,
        "brc_ticket_bound_order_lifecycle_runs",
        "lifecycle_run_id",
        str(command["lifecycle_run_id"]),
    )
    if protection_set:
        _upsert_row(
            conn,
            "brc_ticket_bound_exit_protection_sets",
            "exit_protection_set_id",
            {
                **protection_set,
                "status": "closed",
                "reconciled_with_exchange": True,
                "first_blocker": None,
                "blockers": [],
                "updated_at_ms": now_ms,
            },
        )
    if lifecycle:
        lifecycle_update = {
            **lifecycle,
            "status": "reconciliation_matched",
            "first_blocker": None,
            "blockers": [],
            "updated_at_ms": now_ms,
        }
        _upsert_row(
            conn,
            "brc_ticket_bound_order_lifecycle_runs",
            "lifecycle_run_id",
            lifecycle_update,
        )
        _insert_event(
            conn,
            lifecycle_update,
            "reconciliation_matched",
            {
                "cleanup_command_id": command["orphan_protection_cleanup_command_id"],
                "cleanup_result": result_payload,
            },
            now_ms=now_ms,
        )
    resolve_current_scope_freeze(
        conn,
        strategy_group_id=command.get("strategy_group_id"),
        symbol=command.get("symbol"),
        side=command.get("side"),
        source_kind="orphan_protection_cleanup_command",
        source_id=str(command.get("orphan_protection_cleanup_command_id") or ""),
        now_ms=now_ms,
    )


def _result_payload(
    *,
    command: dict[str, Any],
    canceled_orders: list[dict[str, Any]],
    blockers: list[str],
    exchange_write_called: bool,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "schema": "brc.ticket_bound_orphan_protection_cleanup_result.v1",
        "orphan_protection_cleanup_command_id": command.get(
            "orphan_protection_cleanup_command_id"
        ),
        "exit_protection_set_id": command.get("exit_protection_set_id"),
        "ticket_id": command.get("ticket_id"),
        "cleanup_action": command.get("cleanup_action"),
        "canceled_orders": canceled_orders,
        "exchange_write_called": exchange_write_called,
        "withdrawal_or_transfer_created": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
        "blockers": blockers,
        "authority_boundary": AUTHORITY_BOUNDARY,
    }
    if extra:
        payload.update(extra)
    return payload


def _cancel_operation_succeeded(result: Any) -> bool:
    is_success = getattr(result, "is_success", None)
    if is_success is False:
        return False
    status = str(getattr(result, "status", "") or "").upper()
    allowed_statuses = {"CANCELED", "CANCELLED"}
    if status in {"REJECTED", "EXPIRED", "FAILED"}:
        return False
    if is_success is None and status not in allowed_statuses:
        return False
    if status and status not in allowed_statuses:
        return False
    if getattr(result, "error_code", None) or getattr(result, "error_message", None):
        return False
    return True


def _orders_for_set(
    conn: sa.engine.Connection,
    exit_protection_set_id: str,
) -> list[dict[str, Any]]:
    if not exit_protection_set_id:
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
    _upsert_row(conn, "brc_ticket_bound_lifecycle_events", "lifecycle_event_id", event)


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
    result_payload: dict[str, Any],
    blockers: list[str],
    next_action: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "schema": "brc.ticket_bound_orphan_protection_cleanup_command.v1",
        "status": status,
        "now_ms": now_ms,
        "orphan_protection_cleanup_command_id": command.get(
            "orphan_protection_cleanup_command_id"
        ),
        "exit_protection_set_id": command.get("exit_protection_set_id"),
        "ticket_id": command.get("ticket_id"),
        "first_blocker": blockers[0] if blockers else None,
        "blockers": blockers,
        "next_action": next_action,
        "authority_boundary": AUTHORITY_BOUNDARY,
        "command": command,
        "result_payload": result_payload,
    }
    if extra:
        payload.update(extra)
    return payload


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    return []


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = str(item)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]
    return f"{prefix}:{digest}"


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")
