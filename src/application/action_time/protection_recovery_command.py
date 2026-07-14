#!/usr/bin/env python3
"""Prepare and execute ticket-bound protection recovery commands.

This module handles the post-submit abnormal case where ENTRY filled but SL
and/or TP1 did not become valid exchange refs. It creates one PG recovery
command and executes missing reduce-only protection orders through an injected
gateway. The successful result repairs the original protected submit attempt so
the existing exit protection materializer can create the PG proof set.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
import time
from typing import Any

import sqlalchemy as sa

from src.application.action_time.lifecycle_safety_core import (
    LifecycleDecision,
    reduce_lifecycle_decision,
)


AUTHORITY_BOUNDARY = (
    "ticket_bound_protection_recovery_command; requires existing ticket-bound "
    "protected submit attempt and lifecycle hard blocker; calls injected "
    "gateway place_order only for missing reduce-only SL/TP1; no FinalGate, "
    "profile, sizing, withdrawal, transfer, or file authority"
)
MAX_EXECUTION_ATTEMPTS = 3


def prepare_ticket_bound_protection_recovery_command(
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
            command={},
            blockers=["protected_submit_attempt_id_required"],
            next_action="provide_protected_submit_attempt_id",
        )
    existing = _row_by_id(
        conn,
        "brc_ticket_bound_protection_recovery_commands",
        "protected_submit_attempt_id",
        attempt_id,
    )
    if existing:
        existing_status = str(existing.get("status") or "blocked")
        if existing.get("scope_frozen") in {True, 1}:
            return _result(
                "blocked",
                now_ms=now_ms,
                command=existing,
                blockers=_json_list(existing.get("blockers"))
                or ["protection_recovery_scope_frozen"],
                next_action="freeze_new_submits_for_scope",
                extra={"scope_frozen": True},
            )
        if existing_status == "failed":
            if int(existing.get("execution_attempt_count") or 0) >= int(
                existing.get("max_execution_attempts") or MAX_EXECUTION_ATTEMPTS
            ):
                frozen = _freeze_recovery_scope(
                    conn,
                    command=existing,
                    blockers=["protection_recovery_retry_limit_exhausted"],
                    now_ms=now_ms,
                )
                return _result(
                    "blocked",
                    now_ms=now_ms,
                    command=frozen,
                    blockers=["protection_recovery_retry_limit_exhausted"],
                    next_action="freeze_new_submits_for_scope",
                    extra={"scope_frozen": True},
                )
            refreshed = _refresh_failed_recovery_command(
                conn,
                existing=existing,
                now_ms=now_ms,
            )
            if refreshed:
                return refreshed
        return _result(
            existing_status,
            now_ms=now_ms,
            command=existing,
            blockers=_json_list(existing.get("blockers")),
            next_action="use_existing_protection_recovery_command",
            extra={"idempotent_existing_protection_recovery_command": True},
        )
    attempt = _row_by_id(
        conn,
        "brc_ticket_bound_protected_submit_attempts",
        "protected_submit_attempt_id",
        attempt_id,
    )
    lifecycle = _row_by_id(
        conn,
        "brc_ticket_bound_order_lifecycle_runs",
        "protected_submit_attempt_id",
        attempt_id,
    )
    blockers = _prepare_blockers(attempt=attempt, lifecycle=lifecycle)
    if blockers:
        return _result(
            "blocked",
            now_ms=now_ms,
            command={},
            blockers=blockers,
            next_action="repair_protection_recovery_inputs",
        )
    missing_orders = _missing_protection_orders(attempt, lifecycle=lifecycle)
    blockers = _missing_order_blockers(missing_orders)
    if blockers:
        return _result(
            "blocked",
            now_ms=now_ms,
            command={},
            blockers=blockers,
            next_action="repair_ticket_bound_submit_request_before_recovery",
        )
    command = _command_row(
        attempt=attempt,
        lifecycle=lifecycle,
        missing_orders=missing_orders,
        now_ms=now_ms,
    )
    _upsert_row(
        conn,
        "brc_ticket_bound_protection_recovery_commands",
        "protection_recovery_command_id",
        command,
    )
    return _result(
        "prepared",
        now_ms=now_ms,
        command=command,
        blockers=[],
        next_action="execute_ticket_bound_protection_recovery_command",
    )


async def execute_ticket_bound_protection_recovery_command(
    conn: sa.engine.Connection,
    *,
    protection_recovery_command_id: str,
    gateway: Any,
    now_ms: int | None = None,
) -> dict[str, Any]:
    now_ms = int(now_ms or time.time() * 1000)
    return _result(
        "blocked",
        now_ms=now_ms,
        command={},
        blockers=["legacy_direct_protection_recovery_executor_retired"],
        next_action="materialize_durable_protection_recovery_exchange_commands",
        extra={"exchange_write_called": False},
    )
    command_id = str(protection_recovery_command_id or "").strip()
    if not command_id:
        return _result(
            "blocked",
            now_ms=now_ms,
            command={},
            blockers=["protection_recovery_command_id_required"],
            next_action="provide_protection_recovery_command_id",
        )
    command = _row_by_id(
        conn,
        "brc_ticket_bound_protection_recovery_commands",
        "protection_recovery_command_id",
        command_id,
    )
    if not command:
        return _result(
            "blocked",
            now_ms=now_ms,
            command={},
            blockers=["protection_recovery_command_missing"],
            next_action="prepare_ticket_bound_protection_recovery_command",
        )
    status = str(command.get("status") or "")
    if status == "result_recorded":
        return _result(
            "result_recorded",
            now_ms=now_ms,
            command=command,
            blockers=[],
            next_action="materialize_ticket_bound_exit_protection_set",
            extra={"idempotent_existing_protection_recovery_result": True},
        )
    if status != "prepared":
        return _result(
            "blocked",
            now_ms=now_ms,
            command=command,
            blockers=[f"protection_recovery_command_not_prepared:{status or 'missing'}"],
            next_action="repair_protection_recovery_command_status",
        )
    if command.get("scope_frozen") in {True, 1}:
        return _result(
            "blocked",
            now_ms=now_ms,
            command=command,
            blockers=_json_list(command.get("blockers"))
            or ["protection_recovery_scope_frozen"],
            next_action="freeze_new_submits_for_scope",
            extra={"scope_frozen": True},
        )
    if int(command.get("execution_attempt_count") or 0) >= int(
        command.get("max_execution_attempts") or MAX_EXECUTION_ATTEMPTS
    ):
        frozen = _freeze_recovery_scope(
            conn,
            command=command,
            blockers=["protection_recovery_retry_limit_exhausted"],
            now_ms=now_ms,
        )
        return _result(
            "blocked",
            now_ms=now_ms,
            command=frozen,
            blockers=["protection_recovery_retry_limit_exhausted"],
            next_action="freeze_new_submits_for_scope",
            extra={"scope_frozen": True},
        )
    command = _increment_execution_attempt_count(conn, command=command, now_ms=now_ms)
    stale_blockers = _pre_execution_state_blockers(conn, command=command)
    if stale_blockers:
        result_payload = _result_payload(
            command=command,
            submitted_orders=[],
            blockers=stale_blockers,
            exchange_write_called=False,
            extra={"status": "protection_recovery_pre_execution_blocked"},
        )
        updated = _mark_command_failed_only(
            conn,
            command=command,
            blockers=stale_blockers,
            result_payload=result_payload,
            now_ms=now_ms,
        )
        return _result(
            "blocked",
            now_ms=now_ms,
            command=updated,
            blockers=stale_blockers,
            next_action="repair_or_reprepare_protection_recovery_command",
        )
    command_plan = _as_dict(command.get("command_plan"))
    missing_orders = [
        dict(order)
        for order in command_plan.get("submit_missing_orders", [])
        if isinstance(order, dict)
    ]
    blockers = _missing_order_blockers(missing_orders)
    if blockers:
        updated = _record_result(
            conn,
            command=command,
            status="failed",
            blockers=blockers,
            result_payload=_result_payload(
                command=command,
                submitted_orders=[],
                blockers=blockers,
                exchange_write_called=False,
            ),
            now_ms=now_ms,
        )
        return _result(
            "failed",
            now_ms=now_ms,
            command=updated,
            blockers=blockers,
            next_action="repair_protection_recovery_or_flatten",
        )

    submitted_orders: list[dict[str, Any]] = []
    for order_request in missing_orders:
        try:
            placement_result = await _retired_direct_exchange_mutation(
                symbol=str(order_request.get("symbol") or command["symbol"]),
                order_type=str(order_request["gateway_order_type"]),
                side=str(order_request["gateway_side"]),
                amount=_decimal(order_request["amount"]),
                price=_optional_decimal(order_request.get("price")),
                trigger_price=_optional_decimal(order_request.get("trigger_price")),
                reduce_only=True,
                client_order_id=str(
                    order_request.get("client_order_id")
                    or order_request.get("local_order_id")
                    or ""
                ),
            )
        except Exception as exc:
            blockers = [
                "protection_recovery_submit_failed:"
                f"{order_request.get('order_role', 'unknown')}:{type(exc).__name__}"
            ]
            result_payload = _result_payload(
                command=command,
                submitted_orders=submitted_orders,
                blockers=blockers,
                exchange_write_called=True,
                extra={"submit_error": str(exc)},
            )
            updated = _record_result(
                conn,
                command=command,
                status="failed",
                blockers=blockers,
                result_payload=result_payload,
                now_ms=now_ms,
            )
            if submitted_orders:
                _merge_partial_recovered_orders_into_attempt(
                    conn,
                    command=command,
                    recovered_orders=submitted_orders,
                    blockers=blockers,
                    result_payload=result_payload,
                    now_ms=now_ms,
                )
            return _result(
                "failed",
                now_ms=now_ms,
                command=updated,
                blockers=blockers,
                next_action="repair_protection_recovery_or_flatten",
            )
        if not _place_operation_succeeded(placement_result) or not _exchange_order_id(
            placement_result
        ):
            blockers = [
                getattr(placement_result, "error_message", None)
                or getattr(placement_result, "error_code", None)
                or (
                    "protection_recovery_submit_not_confirmed:"
                    f"{order_request.get('order_role', 'unknown')}"
                )
            ]
            result_payload = _result_payload(
                command=command,
                submitted_orders=submitted_orders,
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
            if submitted_orders:
                _merge_partial_recovered_orders_into_attempt(
                    conn,
                    command=command,
                    recovered_orders=submitted_orders,
                    blockers=blockers,
                    result_payload=result_payload,
                    now_ms=now_ms,
                )
            return _result(
                "failed",
                now_ms=now_ms,
                command=updated,
                blockers=blockers,
                next_action="repair_protection_recovery_or_flatten",
            )
        submitted_orders.append(
            {
                **order_request,
                "exchange_order_id": _exchange_order_id(placement_result),
                "status": str(getattr(placement_result, "status", "OPEN") or "OPEN"),
            }
        )

    result_payload = _result_payload(
        command=command,
        submitted_orders=submitted_orders,
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
    _merge_recovered_orders_into_attempt(
        conn,
        command=command,
        recovered_orders=submitted_orders,
        result_payload=result_payload,
        now_ms=now_ms,
    )
    return _result(
        "result_recorded",
        now_ms=now_ms,
        command=updated,
        blockers=[],
        next_action="materialize_ticket_bound_exit_protection_set",
    )


async def _retired_direct_exchange_mutation(**kwargs: Any) -> Any:
    del kwargs
    raise RuntimeError("legacy_direct_protection_recovery_executor_retired")


def apply_durable_protection_recovery_exchange_commands(
    conn: sa.engine.Connection,
    *,
    protection_recovery_command_id: str,
    exchange_commands: list[dict[str, Any]],
    now_ms: int,
) -> dict[str, Any]:
    """Project confirmed durable place commands into the recovery plan."""

    command = _row_by_id(
        conn,
        "brc_ticket_bound_protection_recovery_commands",
        "protection_recovery_command_id",
        protection_recovery_command_id,
    )
    if not command:
        raise ValueError("protection_recovery_command_missing")
    if str(command.get("status") or "") == "result_recorded":
        return command
    submitted_orders: list[dict[str, Any]] = []
    for exchange_command in exchange_commands:
        if str(exchange_command.get("command_state") or "") not in {
            "confirmed_submitted",
            "reconciled_submitted",
        }:
            raise ValueError("protection_recovery_exchange_command_not_confirmed")
        submitted_orders.append(
            {
                "local_order_id": exchange_command.get("local_order_id"),
                "exchange_order_id": exchange_command.get("exchange_order_id"),
                "client_order_id": exchange_command.get("client_order_id"),
                "order_role": exchange_command.get("order_role"),
                "gateway_side": exchange_command.get("gateway_side"),
                "amount": str(exchange_command.get("amount") or ""),
                "price": (
                    str(exchange_command.get("price"))
                    if exchange_command.get("price") is not None
                    else None
                ),
                "trigger_price": (
                    str(exchange_command.get("stop_price"))
                    if exchange_command.get("stop_price") is not None
                    else None
                ),
                "reduce_only": True,
                "status": "NEW",
            }
        )
    result_payload = _result_payload(
        command=command,
        submitted_orders=submitted_orders,
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
    _merge_recovered_orders_into_attempt(
        conn,
        command=command,
        recovered_orders=submitted_orders,
        result_payload=result_payload,
        now_ms=now_ms,
    )
    _supersede_original_prepared_protection_commands(
        conn,
        protected_submit_attempt_id=str(command["protected_submit_attempt_id"]),
        recovery_command_id=protection_recovery_command_id,
        now_ms=now_ms,
    )
    return updated


def _supersede_original_prepared_protection_commands(
    conn: sa.engine.Connection,
    *,
    protected_submit_attempt_id: str,
    recovery_command_id: str,
    now_ms: int,
) -> None:
    if not sa.inspect(conn).has_table("brc_ticket_bound_exchange_commands"):
        return
    table = _table(conn, "brc_ticket_bound_exchange_commands")
    rows = list(
        conn.execute(
            sa.select(table).where(
                table.c.protected_submit_attempt_id
                == protected_submit_attempt_id,
                table.c.command_source == "protected_submit",
                table.c.order_role.in_(("SL", "TP1")),
                table.c.command_state == "prepared",
            )
        ).mappings()
    )
    for row in rows:
        conn.execute(
            table.update()
            .where(table.c.exchange_command_id == row["exchange_command_id"])
            .values(
                command_state="reconciled_absent",
                outcome_class="reconciled_absence",
                exchange_error_code="superseded_by_protection_recovery",
                exchange_error_message=(
                    "Protection was submitted by durable recovery command "
                    f"{recovery_command_id}"
                ),
                exchange_result={
                    "status": "superseded_by_protection_recovery",
                    "protection_recovery_command_id": recovery_command_id,
                    "exchange_write_called": False,
                },
                resolved_at_ms=now_ms,
                updated_at_ms=now_ms,
            )
        )


def _prepare_blockers(
    *,
    attempt: dict[str, Any],
    lifecycle: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if not attempt:
        blockers.append("protected_submit_attempt_missing")
    if not lifecycle:
        blockers.append("ticket_bound_lifecycle_missing")
    if blockers:
        return blockers
    if str(lifecycle.get("status") or "") not in {
        "protection_missing",
        "protection_degraded",
        "protection_submit_failed",
    }:
        blockers.append(
            f"lifecycle_status_not_recoverable:{lifecycle.get('status') or 'missing'}"
        )
    if lifecycle.get("entry_fill_confirmed") not in {True, 1}:
        blockers.append("entry_fill_not_confirmed_for_protection_recovery")
    if not str(lifecycle.get("entry_exchange_order_id") or "").strip():
        blockers.append("entry_exchange_order_id_missing_for_protection_recovery")
    if str(attempt.get("submit_mode") or "") != "real_gateway_action":
        blockers.append(f"attempt_mode_not_real:{attempt.get('submit_mode')}")
    if attempt.get("exchange_write_called") is not True:
        blockers.append("attempt_exchange_write_not_called")
    if attempt.get("withdrawal_or_transfer_created") not in {False, None, "", 0}:
        blockers.append("attempt_forbidden_effect:withdrawal_or_transfer_created")
    if attempt.get("live_profile_changed") not in {False, None, "", 0}:
        blockers.append("attempt_forbidden_effect:live_profile_changed")
    if attempt.get("order_sizing_changed") not in {False, None, "", 0}:
        blockers.append("attempt_forbidden_effect:order_sizing_changed")
    if not _missing_protection_orders(attempt, lifecycle=lifecycle):
        blockers.append("missing_protection_orders_not_found")
    return _dedupe(blockers)


def _pre_execution_state_blockers(
    conn: sa.engine.Connection,
    *,
    command: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    attempt = _row_by_id(
        conn,
        "brc_ticket_bound_protected_submit_attempts",
        "protected_submit_attempt_id",
        str(command.get("protected_submit_attempt_id") or ""),
    )
    lifecycle = _row_by_id(
        conn,
        "brc_ticket_bound_order_lifecycle_runs",
        "lifecycle_run_id",
        str(command.get("lifecycle_run_id") or ""),
    )
    if not attempt:
        blockers.append("protection_recovery_stale_attempt_missing")
    if not lifecycle:
        blockers.append("protection_recovery_stale_lifecycle_missing")
    if blockers:
        return blockers
    if str(lifecycle.get("status") or "") not in {
        "protection_missing",
        "protection_degraded",
        "protection_submit_failed",
    }:
        blockers.append(
            "protection_recovery_stale_lifecycle_status:"
            f"{lifecycle.get('status') or 'missing'}"
        )
    if lifecycle.get("entry_fill_confirmed") not in {True, 1}:
        blockers.append("protection_recovery_stale_entry_fill_not_confirmed")
    if str(attempt.get("submit_mode") or "") != "real_gateway_action":
        blockers.append(f"protection_recovery_stale_attempt_mode:{attempt.get('submit_mode')}")
    if attempt.get("exchange_write_called") is not True:
        blockers.append("protection_recovery_stale_attempt_exchange_write_not_called")
    current_missing = _missing_protection_orders(attempt, lifecycle=lifecycle)
    if not current_missing:
        blockers.append("protection_recovery_stale_missing_protection_orders_not_found")
    elif _missing_order_roles(current_missing) != _command_missing_order_roles(command):
        blockers.append("protection_recovery_stale_missing_order_scope_changed")
    return _dedupe(blockers)


def _missing_protection_orders(
    attempt: dict[str, Any],
    *,
    lifecycle: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    submit_request = _as_dict(attempt.get("submit_request"))
    submit_result = _as_dict(attempt.get("submit_result"))
    request_orders = [
        dict(order)
        for order in submit_request.get("orders", [])
        if isinstance(order, dict)
    ]
    submitted_orders = [
        dict(order)
        for order in submit_result.get("submitted_orders", [])
        if isinstance(order, dict)
    ]
    submitted_roles = {
        str(order.get("order_role") or "").upper()
        for order in submitted_orders
        if str(order.get("exchange_order_id") or "").strip()
    }
    forced_missing_roles = _forced_missing_roles_from_lifecycle(lifecycle or {})
    missing: list[dict[str, Any]] = []
    for role in ("SL", "TP1"):
        if role in submitted_roles and role not in forced_missing_roles:
            continue
        request = _order_by_role(request_orders, role)
        if request:
            missing.append(dict(request))
    return missing


def _forced_missing_roles_from_lifecycle(lifecycle: dict[str, Any]) -> set[str]:
    blockers = _json_list(lifecycle.get("blockers"))
    first_blocker = str(lifecycle.get("first_blocker") or "").strip()
    if first_blocker:
        blockers.append(first_blocker)
    roles: set[str] = set()
    if any(blocker.startswith("sl_") for blocker in blockers):
        roles.add("SL")
    if any(blocker.startswith("tp1_") for blocker in blockers):
        roles.add("TP1")
    return roles


def _missing_order_roles(orders: list[dict[str, Any]]) -> set[str]:
    return {
        str(order.get("order_role") or "").upper()
        for order in orders
        if str(order.get("order_role") or "")
    }


def _command_missing_order_roles(command: dict[str, Any]) -> set[str]:
    command_plan = _as_dict(command.get("command_plan"))
    return _missing_order_roles(
        [
            dict(order)
            for order in command_plan.get("submit_missing_orders", [])
            if isinstance(order, dict)
        ]
    )


def _missing_order_blockers(missing_orders: list[dict[str, Any]]) -> list[str]:
    blockers: list[str] = []
    if not missing_orders:
        blockers.append("missing_protection_orders_empty")
    for order in missing_orders:
        role = str(order.get("order_role") or "").upper()
        if role not in {"SL", "TP1"}:
            blockers.append(f"recovery_order_role_invalid:{role or 'missing'}")
        if order.get("reduce_only") is not True:
            blockers.append(f"recovery_order_reduce_only_required:{role or 'missing'}")
        if str(order.get("gateway_side") or "") not in {"buy", "sell"}:
            blockers.append(f"recovery_order_side_invalid:{role or 'missing'}")
        if _decimal(order.get("amount")) <= 0:
            blockers.append(f"recovery_order_amount_missing:{role or 'missing'}")
        if role == "SL" and _decimal(order.get("trigger_price")) <= 0:
            blockers.append("recovery_sl_trigger_price_missing")
        if role == "TP1" and _decimal(order.get("price")) <= 0:
            blockers.append("recovery_tp1_price_missing")
    return _dedupe(blockers)


def _command_row(
    *,
    attempt: dict[str, Any],
    lifecycle: dict[str, Any],
    missing_orders: list[dict[str, Any]],
    now_ms: int,
) -> dict[str, Any]:
    command_id = _stable_id(
        "ticket_protection_recovery_command",
        str(attempt["protected_submit_attempt_id"]),
    )
    command_plan = {
        "schema": "brc.ticket_bound_protection_recovery_command_plan.v1",
        "recovery_action": "submit_missing_protection",
        "submit_missing_orders": missing_orders,
        "entry_exchange_order_id": lifecycle.get("entry_exchange_order_id"),
    }
    return {
        "protection_recovery_command_id": command_id,
        "protected_submit_attempt_id": str(attempt["protected_submit_attempt_id"]),
        "lifecycle_run_id": str(lifecycle["lifecycle_run_id"]),
        "ticket_id": str(attempt["ticket_id"]),
        "strategy_group_id": str(attempt["strategy_group_id"]),
        "symbol": str(attempt["symbol"]),
        "side": str(attempt["side"]),
        "status": "prepared",
        "recovery_action": "submit_missing_protection",
        "first_blocker": None,
        "blockers": [],
        "command_plan": command_plan,
        "result_payload": {},
        "execution_attempt_count": 0,
        "max_execution_attempts": MAX_EXECUTION_ATTEMPTS,
        "scope_frozen": False,
        "freeze_scope": {},
        "authority_boundary": AUTHORITY_BOUNDARY,
        "created_at_ms": now_ms,
        "updated_at_ms": now_ms,
    }


def _refresh_failed_recovery_command(
    conn: sa.engine.Connection,
    *,
    existing: dict[str, Any],
    now_ms: int,
) -> dict[str, Any] | None:
    attempt = _row_by_id(
        conn,
        "brc_ticket_bound_protected_submit_attempts",
        "protected_submit_attempt_id",
        str(existing.get("protected_submit_attempt_id") or ""),
    )
    lifecycle = _row_by_id(
        conn,
        "brc_ticket_bound_order_lifecycle_runs",
        "protected_submit_attempt_id",
        str(existing.get("protected_submit_attempt_id") or ""),
    )
    blockers = _prepare_blockers(attempt=attempt, lifecycle=lifecycle)
    if blockers:
        return _result(
            "blocked",
            now_ms=now_ms,
            command=existing,
            blockers=blockers,
            next_action="repair_protection_recovery_inputs",
        )
    missing_orders = _missing_protection_orders(attempt, lifecycle=lifecycle)
    blockers = _missing_order_blockers(missing_orders)
    if blockers:
        return _result(
            "blocked",
            now_ms=now_ms,
            command=existing,
            blockers=blockers,
            next_action="repair_ticket_bound_submit_request_before_recovery",
        )
    refreshed = {
        **_command_row(
            attempt=attempt,
            lifecycle=lifecycle,
            missing_orders=missing_orders,
            now_ms=now_ms,
        ),
        "protection_recovery_command_id": existing["protection_recovery_command_id"],
        "created_at_ms": existing.get("created_at_ms") or now_ms,
        "execution_attempt_count": int(existing.get("execution_attempt_count") or 0),
        "max_execution_attempts": int(
            existing.get("max_execution_attempts") or MAX_EXECUTION_ATTEMPTS
        ),
        "scope_frozen": existing.get("scope_frozen") in {True, 1},
        "freeze_scope": _as_dict(existing.get("freeze_scope")),
    }
    _upsert_row(
        conn,
        "brc_ticket_bound_protection_recovery_commands",
        "protection_recovery_command_id",
        refreshed,
    )
    return _result(
        "prepared",
        now_ms=now_ms,
        command=refreshed,
        blockers=[],
        next_action="execute_ticket_bound_protection_recovery_command",
        extra={"refreshed_failed_protection_recovery_command": True},
    )


def _record_result(
    conn: sa.engine.Connection,
    *,
    command: dict[str, Any],
    status: str,
    blockers: list[str],
    result_payload: dict[str, Any],
    now_ms: int,
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
        "brc_ticket_bound_protection_recovery_commands",
        "protection_recovery_command_id",
        updated,
    )
    if status == "failed":
        _mark_recovery_failed_without_partial_orders(
            conn,
            command=command,
            blockers=blockers,
            result_payload=result_payload,
            now_ms=now_ms,
        )
        if int(updated.get("execution_attempt_count") or 0) >= int(
            updated.get("max_execution_attempts") or MAX_EXECUTION_ATTEMPTS
        ):
            updated = _freeze_recovery_scope(
                conn,
                command=updated,
                blockers=["protection_recovery_retry_limit_exhausted"],
                now_ms=now_ms,
            )
    return updated


def _increment_execution_attempt_count(
    conn: sa.engine.Connection,
    *,
    command: dict[str, Any],
    now_ms: int,
) -> dict[str, Any]:
    updated = {
        **command,
        "execution_attempt_count": int(command.get("execution_attempt_count") or 0) + 1,
        "max_execution_attempts": int(
            command.get("max_execution_attempts") or MAX_EXECUTION_ATTEMPTS
        ),
        "updated_at_ms": now_ms,
    }
    _upsert_row(
        conn,
        "brc_ticket_bound_protection_recovery_commands",
        "protection_recovery_command_id",
        updated,
    )
    if int(updated.get("execution_attempt_count") or 0) >= int(
        updated.get("max_execution_attempts") or MAX_EXECUTION_ATTEMPTS
    ):
        return _freeze_recovery_scope(
            conn,
            command=updated,
            blockers=["protection_recovery_retry_limit_exhausted"],
            now_ms=now_ms,
        )
    return updated


def _freeze_recovery_scope(
    conn: sa.engine.Connection,
    *,
    command: dict[str, Any],
    blockers: list[str],
    now_ms: int,
) -> dict[str, Any]:
    freeze_scope = {
        "strategy_group_id": str(command["strategy_group_id"]),
        "symbol": str(command["symbol"]),
        "side": str(command["side"]),
    }
    updated = {
        **command,
        "status": "blocked",
        "first_blocker": blockers[0],
        "blockers": blockers,
        "scope_frozen": True,
        "freeze_scope": freeze_scope,
        "updated_at_ms": now_ms,
    }
    _upsert_row(
        conn,
        "brc_ticket_bound_protection_recovery_commands",
        "protection_recovery_command_id",
        updated,
    )
    freeze_row = {
        "scope_freeze_id": _stable_id(
            "ticket_scope_freeze",
            freeze_scope["strategy_group_id"],
            freeze_scope["symbol"],
            freeze_scope["side"],
            "active",
        ),
        **freeze_scope,
        "status": "active",
        "source_kind": "protection_recovery_command",
        "source_id": str(command["protection_recovery_command_id"]),
        "first_blocker": blockers[0],
        "blockers": blockers,
        "freeze_scope": freeze_scope,
        "next_action": "notify_owner_and_reconcile_recovery_failure",
        "authority_boundary": AUTHORITY_BOUNDARY,
        "created_at_ms": now_ms,
        "updated_at_ms": now_ms,
    }
    _upsert_row(conn, "brc_ticket_bound_scope_freezes", "scope_freeze_id", freeze_row)
    return updated


def _mark_command_failed_only(
    conn: sa.engine.Connection,
    *,
    command: dict[str, Any],
    blockers: list[str],
    result_payload: dict[str, Any],
    now_ms: int,
) -> dict[str, Any]:
    updated = {
        **command,
        "status": "failed",
        "first_blocker": blockers[0] if blockers else "protection_recovery_failed",
        "blockers": blockers,
        "result_payload": result_payload,
        "updated_at_ms": now_ms,
    }
    _upsert_row(
        conn,
        "brc_ticket_bound_protection_recovery_commands",
        "protection_recovery_command_id",
        updated,
    )
    return updated


def _merge_recovered_orders_into_attempt(
    conn: sa.engine.Connection,
    *,
    command: dict[str, Any],
    recovered_orders: list[dict[str, Any]],
    result_payload: dict[str, Any],
    now_ms: int,
) -> None:
    attempt = _row_by_id(
        conn,
        "brc_ticket_bound_protected_submit_attempts",
        "protected_submit_attempt_id",
        str(command["protected_submit_attempt_id"]),
    )
    submit_result = _as_dict(attempt.get("submit_result"))
    existing_orders = [
        dict(order)
        for order in submit_result.get("submitted_orders", [])
        if isinstance(order, dict)
    ]
    merged = _merge_orders(existing_orders, recovered_orders)
    repaired_submit_result = {
        **submit_result,
        "schema": "brc.ticket_bound_protected_submit_result.v1",
        "status": "exchange_submit_orders_submitted",
        "ticket_id": attempt.get("ticket_id"),
        "operation_submit_command_id": attempt.get("operation_submit_command_id"),
        "strategy_group_id": attempt.get("strategy_group_id"),
        "symbol": attempt.get("symbol"),
        "side": attempt.get("side"),
        "exchange_write_called": True,
        "order_created": True,
        "order_lifecycle_called": True,
        "withdrawal_or_transfer_created": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
        "submitted_orders": merged,
        "protection_recovery_result": result_payload,
    }
    updated_attempt = {
        **attempt,
        "status": "submitted",
        "blockers": [],
        "warnings": _dedupe(
            _json_list(attempt.get("warnings"))
            + ["protection_recovered_after_submit_failure"]
        ),
        "submit_result": repaired_submit_result,
        "official_operation_layer_submit_called": True,
        "exchange_write_called": True,
        "order_created": True,
        "order_lifecycle_called": True,
        "withdrawal_or_transfer_created": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
        "updated_at_ms": now_ms,
    }
    _upsert_row(
        conn,
        "brc_ticket_bound_protected_submit_attempts",
        "protected_submit_attempt_id",
        updated_attempt,
    )


def _merge_partial_recovered_orders_into_attempt(
    conn: sa.engine.Connection,
    *,
    command: dict[str, Any],
    recovered_orders: list[dict[str, Any]],
    blockers: list[str],
    result_payload: dict[str, Any],
    now_ms: int,
) -> None:
    attempt = _row_by_id(
        conn,
        "brc_ticket_bound_protected_submit_attempts",
        "protected_submit_attempt_id",
        str(command["protected_submit_attempt_id"]),
    )
    submit_result = _as_dict(attempt.get("submit_result"))
    existing_orders = [
        dict(order)
        for order in submit_result.get("submitted_orders", [])
        if isinstance(order, dict)
    ]
    merged = _merge_orders(existing_orders, recovered_orders)
    partial_submit_result = {
        **submit_result,
        "schema": "brc.ticket_bound_protected_submit_result.v1",
        "status": "protection_recovery_failed",
        "ticket_id": attempt.get("ticket_id"),
        "operation_submit_command_id": attempt.get("operation_submit_command_id"),
        "strategy_group_id": attempt.get("strategy_group_id"),
        "symbol": attempt.get("symbol"),
        "side": attempt.get("side"),
        "exchange_write_called": True,
        "order_created": True,
        "order_lifecycle_called": True,
        "withdrawal_or_transfer_created": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
        "submitted_orders": merged,
        "protection_recovery_result": result_payload,
    }
    updated_attempt = {
        **attempt,
        "status": "submit_failed",
        "blockers": blockers,
        "warnings": _dedupe(
            _json_list(attempt.get("warnings"))
            + ["partial_protection_recovery_recorded"]
        ),
        "submit_result": partial_submit_result,
        "official_operation_layer_submit_called": True,
        "exchange_write_called": True,
        "order_created": True,
        "order_lifecycle_called": True,
        "withdrawal_or_transfer_created": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
        "updated_at_ms": now_ms,
    }
    _upsert_row(
        conn,
        "brc_ticket_bound_protected_submit_attempts",
        "protected_submit_attempt_id",
        updated_attempt,
    )
    _update_lifecycle_after_partial_recovery(
        conn,
        command=command,
        submitted_orders=merged,
        blockers=blockers,
        now_ms=now_ms,
    )


def _mark_recovery_failed_without_partial_orders(
    conn: sa.engine.Connection,
    *,
    command: dict[str, Any],
    blockers: list[str],
    result_payload: dict[str, Any],
    now_ms: int,
) -> None:
    submitted_orders = [
        dict(order)
        for order in result_payload.get("submitted_orders", [])
        if isinstance(order, dict)
    ]
    if submitted_orders:
        return
    attempt = _row_by_id(
        conn,
        "brc_ticket_bound_protected_submit_attempts",
        "protected_submit_attempt_id",
        str(command["protected_submit_attempt_id"]),
    )
    if attempt:
        submit_result = _as_dict(attempt.get("submit_result"))
        updated_attempt = {
            **attempt,
            "status": "submit_failed",
            "blockers": blockers,
            "warnings": _dedupe(
                _json_list(attempt.get("warnings"))
                + ["protection_recovery_failed_without_partial_orders"]
            ),
            "submit_result": {
                **submit_result,
                "status": "protection_recovery_failed",
                "protection_recovery_result": result_payload,
            },
            "updated_at_ms": now_ms,
        }
        _upsert_row(
            conn,
            "brc_ticket_bound_protected_submit_attempts",
            "protected_submit_attempt_id",
            updated_attempt,
        )
    lifecycle = _row_by_id(
        conn,
        "brc_ticket_bound_order_lifecycle_runs",
        "lifecycle_run_id",
        str(command["lifecycle_run_id"]),
    )
    if lifecycle:
        decision = _recovery_failed_lifecycle_decision(
            lifecycle,
            blockers=blockers,
        )
        updated_lifecycle = {
            **lifecycle,
            "status": decision.status,
            "first_blocker": decision.first_blocker,
            "blockers": list(decision.blockers),
            "updated_at_ms": now_ms,
        }
        _upsert_row(
            conn,
            "brc_ticket_bound_order_lifecycle_runs",
            "lifecycle_run_id",
            updated_lifecycle,
        )


def _update_lifecycle_after_partial_recovery(
    conn: sa.engine.Connection,
    *,
    command: dict[str, Any],
    submitted_orders: list[dict[str, Any]],
    blockers: list[str],
    now_ms: int,
) -> None:
    lifecycle = _row_by_id(
        conn,
        "brc_ticket_bound_order_lifecycle_runs",
        "lifecycle_run_id",
        str(command["lifecycle_run_id"]),
    )
    decision = _partial_recovery_lifecycle_decision(
        current_status=str(lifecycle.get("status") or ""),
        submitted_orders=submitted_orders,
        blockers=blockers,
    )
    updated = {
        **lifecycle,
        "status": decision.status,
        "first_blocker": decision.first_blocker,
        "blockers": list(decision.blockers),
        "updated_at_ms": now_ms,
    }
    _upsert_row(
        conn,
        "brc_ticket_bound_order_lifecycle_runs",
        "lifecycle_run_id",
        updated,
    )


def _recovery_failed_lifecycle_decision(
    lifecycle: dict[str, Any],
    *,
    blockers: list[str],
) -> LifecycleDecision:
    current = str(lifecycle.get("status") or "")
    if current in {"protection_missing", "protection_degraded", "protection_submit_failed"}:
        target = current
    else:
        target = "protection_degraded"
    return reduce_lifecycle_decision(
        current_status=current,
        target_status=target,
        blockers=blockers,
    )


def _partial_recovery_lifecycle_decision(
    *,
    current_status: str,
    submitted_orders: list[dict[str, Any]],
    blockers: list[str],
) -> LifecycleDecision:
    roles = {
        str(order.get("order_role") or "").upper()
        for order in submitted_orders
        if str(order.get("exchange_order_id") or "").strip()
    }
    target = "protection_degraded" if "SL" in roles else "protection_missing"
    return reduce_lifecycle_decision(
        current_status=current_status,
        target_status=target,
        blockers=blockers,
    )


def _merge_orders(
    existing_orders: list[dict[str, Any]],
    recovered_orders: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_role = {
        str(order.get("order_role") or "").upper(): dict(order)
        for order in existing_orders
        if str(order.get("order_role") or "")
    }
    for order in recovered_orders:
        by_role[str(order.get("order_role") or "").upper()] = dict(order)
    return [by_role[role] for role in ("ENTRY", "SL", "TP1") if role in by_role]


def _result_payload(
    *,
    command: dict[str, Any],
    submitted_orders: list[dict[str, Any]],
    blockers: list[str],
    exchange_write_called: bool,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "schema": "brc.ticket_bound_protection_recovery_result.v1",
        "protection_recovery_command_id": command.get(
            "protection_recovery_command_id"
        ),
        "protected_submit_attempt_id": command.get("protected_submit_attempt_id"),
        "ticket_id": command.get("ticket_id"),
        "status": "protection_recovery_failed" if blockers else "protection_recovered",
        "exchange_write_called": exchange_write_called,
        "order_created": bool(submitted_orders),
        "order_lifecycle_called": False,
        "withdrawal_or_transfer_created": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
        "submitted_orders": submitted_orders,
        "blockers": blockers,
        "authority_boundary": AUTHORITY_BOUNDARY,
    }
    if extra:
        payload.update(extra)
    return payload


def _place_operation_succeeded(result: Any) -> bool:
    if getattr(result, "is_success", None) is False:
        return False
    status = str(getattr(result, "status", "") or "").upper()
    if status in {"REJECTED", "EXPIRED", "CANCELED", "CANCELLED", "FAILED"}:
        return False
    if status and status not in {"OPEN", "SUBMITTED", "PENDING", "CREATED", "NEW", "ACCEPTED"}:
        return False
    if getattr(result, "error_code", None) or getattr(result, "error_message", None):
        return False
    return True


def _exchange_order_id(result: Any) -> str:
    return str(getattr(result, "exchange_order_id", None) or "").strip()


def _optional_decimal(value: Any) -> Decimal | None:
    decimal = _decimal(value)
    return decimal if decimal > 0 else None


def _order_by_role(orders: list[dict[str, Any]], role: str) -> dict[str, Any]:
    expected = role.upper()
    for order in orders:
        if str(order.get("order_role") or "").upper() == expected:
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
        "schema": "brc.ticket_bound_protection_recovery_command.v1",
        "status": status,
        "now_ms": now_ms,
        "protection_recovery_command_id": command.get(
            "protection_recovery_command_id"
        ),
        "protected_submit_attempt_id": command.get("protected_submit_attempt_id"),
        "lifecycle_run_id": command.get("lifecycle_run_id"),
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


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = str(item)
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]
    return f"{prefix}:{digest}"
