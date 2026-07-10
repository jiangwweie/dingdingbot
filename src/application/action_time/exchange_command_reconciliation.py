"""Read-only reconciliation for ambiguous ticket-bound exchange commands."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from src.application.action_time.exchange_command import (
    record_exchange_command_outcome,
)
from src.domain.ticket_bound_exchange_command import (
    ExchangeCommandOutcomeClass,
    ExchangeCommandState,
)


VISIBILITY_WINDOW_MS = 30_000
AUTHORITY_BOUNDARY = (
    "ticket_bound_exchange_command_reconciliation; read-only lookup by "
    "persisted client_order_id; no submit, cancel, replace, profile, sizing, "
    "withdrawal, transfer, or file authority"
)


async def reconcile_unknown_exchange_commands(
    conn: sa.engine.Connection,
    *,
    gateway: Any,
    now_ms: int,
    max_commands: int,
) -> dict[str, Any]:
    table = sa.Table(
        "brc_ticket_bound_exchange_commands",
        sa.MetaData(),
        autoload_with=conn,
    )
    rows = list(
        conn.execute(
            sa.select(table)
            .where(table.c.command_state == "outcome_unknown")
            .order_by(table.c.updated_at_ms.asc())
            .limit(max(0, max_commands))
        ).mappings()
    )
    counts = {
        "reconciled_submitted": 0,
        "reconciled_absent": 0,
        "pending_visibility": 0,
        "hard_stopped": 0,
        "lookup_failed": 0,
    }
    results: list[dict[str, Any]] = []
    for raw in rows:
        command = dict(raw)
        try:
            exchange_order = await gateway.find_order_by_client_id(
                str(command["client_order_id"]),
                str(command["gateway_symbol"]),
            )
        except Exception as exc:
            counts["lookup_failed"] += 1
            results.append(
                _item(
                    command,
                    status="lookup_failed",
                    blocker=f"exchange_command_lookup_failed:{type(exc).__name__}",
                )
            )
            continue

        if exchange_order is None:
            visibility_deadline_ms = (
                int(command.get("updated_at_ms") or now_ms)
                + VISIBILITY_WINDOW_MS
            )
            if now_ms < visibility_deadline_ms:
                counts["pending_visibility"] += 1
                results.append(
                    _item(
                        command,
                        status="pending_visibility",
                        blocker="exchange_command_visibility_window_active",
                    )
                )
                continue
            record_exchange_command_outcome(
                conn,
                exchange_command_id=str(command["exchange_command_id"]),
                target_state=ExchangeCommandState.RECONCILED_ABSENT,
                outcome_class=ExchangeCommandOutcomeClass.RECONCILED_ABSENCE,
                exchange_result={},
                now_ms=now_ms,
            )
            counts["reconciled_absent"] += 1
            results.append(
                _item(
                    command,
                    status="reconciled_absent",
                    blocker="new_ticket_and_official_gates_required_for_any_retry",
                )
            )
            continue

        exchange = _mapping(exchange_order)
        exchange_order_id = str(exchange.get("exchange_order_id") or "").strip()
        actual_client_id = str(exchange.get("client_order_id") or "").strip()
        actual_symbol = str(exchange.get("symbol") or "").strip()
        contradictory = (
            not exchange_order_id
            or (
                bool(actual_client_id)
                and actual_client_id != str(command["client_order_id"])
            )
            or (
                bool(actual_symbol)
                and actual_symbol != str(command["gateway_symbol"])
            )
        )
        if contradictory:
            record_exchange_command_outcome(
                conn,
                exchange_command_id=str(command["exchange_command_id"]),
                target_state=ExchangeCommandState.HARD_STOPPED,
                outcome_class=ExchangeCommandOutcomeClass.CONTRADICTORY_TRUTH,
                exchange_result={
                    "exchange_order_id": exchange_order_id or None,
                    "error_message": "reconciled_exchange_identity_contradictory",
                },
                now_ms=now_ms,
            )
            counts["hard_stopped"] += 1
            results.append(
                _item(
                    command,
                    status="hard_stopped",
                    blocker="reconciled_exchange_identity_contradictory",
                )
            )
            continue

        record_exchange_command_outcome(
            conn,
            exchange_command_id=str(command["exchange_command_id"]),
            target_state=ExchangeCommandState.RECONCILED_SUBMITTED,
            outcome_class=ExchangeCommandOutcomeClass.RECONCILED_EXCHANGE_TRUTH,
            exchange_result={"exchange_order_id": exchange_order_id},
            now_ms=now_ms,
        )
        counts["reconciled_submitted"] += 1
        results.append(_item(command, status="reconciled_submitted", blocker=""))

    blockers: list[str] = []
    if counts["hard_stopped"]:
        blockers.append("exchange_command_hard_stopped")
    if counts["lookup_failed"]:
        blockers.append("exchange_command_lookup_failed")
    if counts["pending_visibility"]:
        blockers.append("exchange_command_visibility_window_active")
    return {
        "schema": "brc.ticket_bound_exchange_command_reconciliation.v1",
        "status": "reconciliation_complete" if rows else "no_unknown_commands",
        "selected_count": len(rows),
        **counts,
        "results": results,
        "first_blocker": blockers[0] if blockers else None,
        "blockers": blockers,
        "next_action": (
            "repair_or_continue_unknown_exchange_command_reconciliation"
            if blockers
            else "continue_ticket_bound_lifecycle_from_reconciled_truth"
        ),
        "exchange_read_called": bool(rows),
        "exchange_write_called": False,
        "automatic_resubmit_called": False,
        "authority_boundary": AUTHORITY_BOUNDARY,
    }


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "__dict__"):
        return dict(vars(value))
    return {}


def _item(
    command: dict[str, Any],
    *,
    status: str,
    blocker: str,
) -> dict[str, Any]:
    return {
        "exchange_command_id": command.get("exchange_command_id"),
        "client_order_id": command.get("client_order_id"),
        "status": status,
        "blockers": [blocker] if blocker else [],
    }
