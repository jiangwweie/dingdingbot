#!/usr/bin/env python3
"""Execute prepared ticket-bound runner mutation commands.

This module is the application execution bridge for TP1 filled -> old SL
cancel -> RUNNER_SL submit. It consumes an already prepared PG command row,
calls an injected gateway, and records the result back to PG. It does not call
FinalGate, create a new ticket, change profile/sizing, or read repo files.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import time
from typing import Any

import sqlalchemy as sa

from src.application.action_time.runner_mutation_command import (
    record_ticket_bound_runner_mutation_result,
)


AUTHORITY_BOUNDARY = (
    "ticket_bound_runner_mutation_executor; requires prepared PG runner "
    "mutation command; calls injected gateway cancel/place only; no FinalGate, "
    "profile, sizing, withdrawal, transfer, or file authority"
)


async def execute_ticket_bound_runner_mutation_command(
    conn: sa.engine.Connection,
    *,
    runner_mutation_command_id: str,
    gateway: Any,
    now_ms: int | None = None,
) -> dict[str, Any]:
    now_ms = int(now_ms or time.time() * 1000)
    command_id = str(runner_mutation_command_id or "").strip()
    if not command_id:
        return _result(
            "blocked",
            now_ms=now_ms,
            command={},
            result_payload={},
            blockers=["runner_mutation_command_id_required"],
            next_action="provide_runner_mutation_command_id",
        )
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
            result_payload={},
            blockers=["runner_mutation_command_missing"],
            next_action="prepare_ticket_bound_runner_mutation_command",
        )
    status = str(command.get("status") or "")
    if status == "result_recorded":
        return _result(
            "result_recorded",
            now_ms=now_ms,
            command=command,
            result_payload=_as_dict(command.get("result_payload")),
            blockers=[],
            next_action="materialize_ticket_bound_runner_protection_adjustment",
            extra={"idempotent_existing_runner_mutation_result": True},
        )
    if status != "prepared":
        return _result(
            "blocked",
            now_ms=now_ms,
            command=command,
            result_payload={},
            blockers=[f"runner_mutation_command_not_prepared:{status or 'missing'}"],
            next_action="repair_runner_mutation_command_status",
        )

    command_plan = _as_dict(command.get("command_plan"))
    blockers = _command_plan_blockers(command=command, command_plan=command_plan)
    if blockers:
        result_payload = _base_result_payload(
            command=command,
            old_sl_cancelled=False,
            runner_sl_submitted=False,
            runner_sl_exchange_order_id="",
            blockers=blockers,
            exchange_write_called=False,
        )
        recorded = record_ticket_bound_runner_mutation_result(
            conn,
            runner_mutation_command_id=command_id,
            result_payload=result_payload,
            now_ms=now_ms,
        )
        return _result(
            "failed",
            now_ms=now_ms,
            command=dict(recorded.get("command") or command),
            result_payload=result_payload,
            blockers=blockers,
            next_action="repair_runner_mutation_or_flatten",
        )

    cancel_plan = _as_dict(command_plan.get("cancel_old_sl"))
    submit_plan = _as_dict(command_plan.get("submit_runner_sl"))
    old_sl_exchange_order_id = str(cancel_plan["exchange_order_id"])
    symbol = str(command["symbol"])
    try:
        cancel_result = await gateway.cancel_order(
            exchange_order_id=old_sl_exchange_order_id,
            symbol=symbol,
        )
    except Exception as exc:
        blockers = [f"old_sl_cancel_failed:{type(exc).__name__}"]
        result_payload = _base_result_payload(
            command=command,
            old_sl_cancelled=False,
            runner_sl_submitted=False,
            runner_sl_exchange_order_id="",
            blockers=blockers,
            exchange_write_called=True,
            extra={"cancel_error": str(exc)},
        )
        recorded = record_ticket_bound_runner_mutation_result(
            conn,
            runner_mutation_command_id=command_id,
            result_payload=result_payload,
            now_ms=now_ms,
        )
        return _result(
            "failed",
            now_ms=now_ms,
            command=dict(recorded.get("command") or command),
            result_payload=result_payload,
            blockers=blockers,
            next_action="repair_runner_mutation_or_flatten",
        )
    if not _operation_succeeded(cancel_result):
        blockers = [
            getattr(cancel_result, "error_message", None)
            or getattr(cancel_result, "error_code", None)
            or "old_sl_cancel_not_confirmed"
        ]
        result_payload = _base_result_payload(
            command=command,
            old_sl_cancelled=False,
            runner_sl_submitted=False,
            runner_sl_exchange_order_id="",
            blockers=blockers,
            exchange_write_called=True,
        )
        recorded = record_ticket_bound_runner_mutation_result(
            conn,
            runner_mutation_command_id=command_id,
            result_payload=result_payload,
            now_ms=now_ms,
        )
        return _result(
            "failed",
            now_ms=now_ms,
            command=dict(recorded.get("command") or command),
            result_payload=result_payload,
            blockers=blockers,
            next_action="repair_runner_mutation_or_flatten",
        )

    client_order_id = _runner_client_order_id(command_id)
    try:
        placement_result = await gateway.place_order(
            symbol=symbol,
            order_type="stop_market",
            side=str(submit_plan["side"]),
            amount=_decimal(submit_plan["qty"]),
            price=None,
            trigger_price=_decimal(submit_plan["trigger_price"]),
            reduce_only=True,
            client_order_id=client_order_id,
        )
    except Exception as exc:
        blockers = [f"runner_sl_submit_failed:{type(exc).__name__}"]
        result_payload = _base_result_payload(
            command=command,
            old_sl_cancelled=True,
            runner_sl_submitted=False,
            runner_sl_exchange_order_id="",
            blockers=blockers,
            exchange_write_called=True,
            extra={
                "old_sl_cancel_exchange_order_id": _exchange_order_id(cancel_result),
                "submit_error": str(exc),
            },
        )
        recorded = record_ticket_bound_runner_mutation_result(
            conn,
            runner_mutation_command_id=command_id,
            result_payload=result_payload,
            now_ms=now_ms,
        )
        return _result(
            "failed",
            now_ms=now_ms,
            command=dict(recorded.get("command") or command),
            result_payload=result_payload,
            blockers=blockers,
            next_action="repair_runner_mutation_or_flatten",
        )
    if not _operation_succeeded(placement_result) or not _exchange_order_id(
        placement_result
    ):
        blockers = [
            getattr(placement_result, "error_message", None)
            or getattr(placement_result, "error_code", None)
            or "runner_sl_submit_not_confirmed"
        ]
        result_payload = _base_result_payload(
            command=command,
            old_sl_cancelled=True,
            runner_sl_submitted=False,
            runner_sl_exchange_order_id="",
            blockers=blockers,
            exchange_write_called=True,
            extra={"old_sl_cancel_exchange_order_id": _exchange_order_id(cancel_result)},
        )
        recorded = record_ticket_bound_runner_mutation_result(
            conn,
            runner_mutation_command_id=command_id,
            result_payload=result_payload,
            now_ms=now_ms,
        )
        return _result(
            "failed",
            now_ms=now_ms,
            command=dict(recorded.get("command") or command),
            result_payload=result_payload,
            blockers=blockers,
            next_action="repair_runner_mutation_or_flatten",
        )

    result_payload = _base_result_payload(
        command=command,
        old_sl_cancelled=True,
        runner_sl_submitted=True,
        runner_sl_exchange_order_id=_exchange_order_id(placement_result),
        blockers=[],
        exchange_write_called=True,
        extra={
            "old_sl_cancel_exchange_order_id": _exchange_order_id(cancel_result)
            or old_sl_exchange_order_id,
            "runner_sl_client_order_id": client_order_id,
            "runner_sl_local_order_id": client_order_id,
        },
    )
    recorded = record_ticket_bound_runner_mutation_result(
        conn,
        runner_mutation_command_id=command_id,
        result_payload=result_payload,
        now_ms=now_ms,
    )
    return _result(
        "result_recorded",
        now_ms=now_ms,
        command=dict(recorded.get("command") or command),
        result_payload=result_payload,
        blockers=[],
        next_action="materialize_ticket_bound_runner_protection_adjustment",
    )


def _command_plan_blockers(
    *,
    command: dict[str, Any],
    command_plan: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    cancel_plan = _as_dict(command_plan.get("cancel_old_sl"))
    submit_plan = _as_dict(command_plan.get("submit_runner_sl"))
    if not cancel_plan:
        blockers.append("runner_mutation_cancel_plan_missing")
    elif not str(cancel_plan.get("exchange_order_id") or "").strip():
        blockers.append("old_sl_exchange_order_id_missing")
    if not submit_plan:
        blockers.append("runner_mutation_submit_plan_missing")
    else:
        if _decimal(submit_plan.get("qty")) <= 0:
            blockers.append("runner_qty_not_positive")
        if _decimal(submit_plan.get("trigger_price")) <= 0:
            blockers.append("runner_sl_trigger_price_missing")
        if str(submit_plan.get("side") or "").strip() not in {"buy", "sell"}:
            blockers.append("runner_sl_side_invalid")
        if submit_plan.get("reduce_only") is not True:
            blockers.append("runner_sl_reduce_only_required")
    if _decimal(command.get("runner_qty")) <= 0:
        blockers.append("runner_qty_not_positive")
    if not str(command.get("symbol") or "").strip():
        blockers.append("symbol_required")
    return _dedupe(blockers)


def _base_result_payload(
    *,
    command: dict[str, Any],
    old_sl_cancelled: bool,
    runner_sl_submitted: bool,
    runner_sl_exchange_order_id: str,
    blockers: list[str],
    exchange_write_called: bool,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "schema": "brc.ticket_bound_runner_mutation_executor_result.v1",
        "runner_mutation_command_id": command.get("runner_mutation_command_id"),
        "exit_protection_set_id": command.get("exit_protection_set_id"),
        "ticket_id": command.get("ticket_id"),
        "old_sl_exchange_order_id": command.get("old_sl_exchange_order_id"),
        "old_sl_cancelled": old_sl_cancelled,
        "runner_sl_submitted": runner_sl_submitted,
        "runner_sl_exchange_order_id": str(runner_sl_exchange_order_id or ""),
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


def _operation_succeeded(result: Any) -> bool:
    is_success = getattr(result, "is_success", None)
    if is_success is False:
        return False
    status = str(getattr(result, "status", "") or "").upper()
    if status in {"REJECTED", "EXPIRED"}:
        return False
    if is_success is None and status not in {
        "CANCELED",
        "CANCELLED",
        "OPEN",
        "SUBMITTED",
        "PENDING",
        "CREATED",
    }:
        return False
    if getattr(result, "error_code", None) or getattr(result, "error_message", None):
        return False
    return True


def _exchange_order_id(result: Any) -> str:
    return str(getattr(result, "exchange_order_id", None) or "").strip()


def _runner_client_order_id(command_id: str) -> str:
    return f"{command_id}:runner-sl"


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
        "schema": "brc.ticket_bound_runner_mutation_executor.v1",
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
        "result_payload": result_payload,
    }
    if extra:
        payload.update(extra)
    return payload


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


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
