"""Atomic PostgreSQL projection for a durable ENTRY command result."""

from __future__ import annotations

from decimal import Decimal
import hashlib
from typing import Any

import sqlalchemy as sa

from src.domain.entry_effect import EntryEffectDecision, classify_entry_effect


AUTHORITY_BOUNDARY = (
    "entry_effect_projection; durable_exchange_command_and_ticket_lifecycle_truth"
)
_IMMEDIATE_LIFECYCLE_STATUSES = {
    "entry_submit_sent",
    "entry_fill_pending",
    "entry_filled",
    "entry_unknown",
}


class EntryEffectProjectionError(RuntimeError):
    """The command result cannot be projected without violating atomic truth."""


def project_entry_effect(
    conn: sa.engine.Connection,
    *,
    command: dict[str, Any],
    now_ms: int,
) -> EntryEffectDecision | None:
    """Project an ENTRY result in the caller's command-result transaction."""

    decision = classify_entry_effect(
        order_role=str(command.get("order_role") or ""),
        command_state=str(command.get("command_state") or ""),
        result_facts_complete=command.get("result_facts_complete") in {True, 1},
        executed_qty=_decimal_or_none(command.get("executed_qty")),
        average_exec_price=_decimal_or_none(command.get("average_exec_price")),
    )
    if decision is None:
        return None
    attempt_id = str(command.get("protected_submit_attempt_id") or "")
    if not attempt_id:
        raise EntryEffectProjectionError(
            "entry_effect_protected_submit_attempt_id_missing"
        )
    attempt_table = _table(conn, "brc_ticket_bound_protected_submit_attempts")
    attempt = conn.execute(
        sa.select(attempt_table).where(
            attempt_table.c.protected_submit_attempt_id == attempt_id
        )
    ).mappings().one()
    attempt_row = dict(attempt)
    _update_attempt(
        conn,
        table=attempt_table,
        attempt=attempt_row,
        decision=decision,
        now_ms=now_ms,
    )
    if not decision.effect_possible:
        if decision.entry_effect_state.value == "rejected":
            _project_authoritative_rejection(
                conn,
                attempt=attempt_row,
                command=command,
                now_ms=now_ms,
            )
        return decision
    _project_ticket_and_handoff(
        conn,
        attempt=attempt_row,
        command=command,
        decision=decision,
        now_ms=now_ms,
    )
    _restore_effect_capacity_if_expiration_won(
        conn,
        attempt=attempt_row,
        command=command,
        now_ms=now_ms,
    )
    _project_lifecycle(
        conn,
        attempt=attempt_row,
        command=command,
        decision=decision,
        now_ms=now_ms,
    )
    return decision


def _restore_effect_capacity_if_expiration_won(
    conn: sa.engine.Connection,
    *,
    attempt: dict[str, Any],
    command: dict[str, Any],
    now_ms: int,
) -> None:
    reservations = _table(conn, "brc_budget_reservations")
    reservation = conn.execute(
        sa.select(reservations).where(
            reservations.c.ticket_id == attempt["ticket_id"]
        )
    ).mappings().one_or_none()
    if reservation is None or str(reservation["status"]) != "released":
        return
    reservation_id = str(reservation["budget_reservation_id"])
    updated = conn.execute(
        reservations.update()
        .where(
            reservations.c.budget_reservation_id == reservation_id,
            reservations.c.status == "released",
        )
        .values(
            status="consumed",
            release_reason=None,
            released_at_ms=None,
            reconciliation_state="pending",
            current_first_blocker=(
                "entry_effect_capacity_revalidation_required"
            ),
        )
        .returning(reservations.c.budget_reservation_id)
    ).first()
    if updated is None:
        return
    events = _table(conn, "brc_budget_reservation_events")
    event_id = _stable_id(
        "budget_reservation_event",
        reservation_id,
        "entry_effect_capacity_repair",
        str(command["exchange_command_id"]),
    )
    if conn.execute(
        sa.select(events.c.budget_reservation_event_id).where(
            events.c.budget_reservation_event_id == event_id
        )
    ).first():
        return
    conn.execute(
        events.insert().values(
            budget_reservation_event_id=event_id,
            budget_reservation_id=reservation_id,
            from_status="released",
            to_status="consumed",
            reason="entry_effect_after_expiration_capacity_repair",
            evidence_ref=str(command["exchange_command_id"]),
            created_at_ms=now_ms,
        )
    )


def _project_authoritative_rejection(
    conn: sa.engine.Connection,
    *,
    attempt: dict[str, Any],
    command: dict[str, Any],
    now_ms: int,
) -> None:
    attempt_table = _table(conn, "brc_ticket_bound_protected_submit_attempts")
    conn.execute(
        attempt_table.update()
        .where(
            attempt_table.c.protected_submit_attempt_id
            == attempt["protected_submit_attempt_id"]
        )
        .values(
            status="submit_failed",
            blockers=[
                str(
                    command.get("exchange_error_message")
                    or "entry_authoritatively_rejected"
                )
            ],
            updated_at_ms=now_ms,
        )
    )
    ticket_table = _table(conn, "brc_action_time_tickets")
    ticket = conn.execute(
        sa.select(ticket_table).where(ticket_table.c.ticket_id == attempt["ticket_id"])
    ).mappings().one()
    prior_status = str(ticket["status"])
    if prior_status in {"finalgate_ready", "expired"}:
        conn.execute(
            ticket_table.update()
            .where(
                ticket_table.c.ticket_id == attempt["ticket_id"],
                ticket_table.c.status == prior_status,
            )
            .values(status="invalidated")
        )
    elif prior_status != "invalidated":
        raise EntryEffectProjectionError(
            f"entry_rejection_ticket_state_invalid:{prior_status}"
        )
    handoff_table = _table(conn, "brc_operation_layer_handoffs")
    conn.execute(
        handoff_table.update()
        .where(
            handoff_table.c.operation_layer_handoff_id
            == attempt["operation_layer_handoff_id"]
        )
        .values(status="invalidated", updated_at_ms=now_ms)
    )
    event_table = _table(conn, "brc_action_time_ticket_events")
    event_id = _stable_id(
        "entry_rejection_ticket_event",
        str(attempt["ticket_id"]),
        str(command["exchange_command_id"]),
    )
    if conn.execute(
        sa.select(event_table.c.ticket_event_id).where(
            event_table.c.ticket_event_id == event_id
        )
    ).first():
        return
    if prior_status == "invalidated":
        return
    conn.execute(
        event_table.insert().values(
            ticket_event_id=event_id,
            ticket_id=attempt["ticket_id"],
            action_time_lane_input_id=attempt["action_time_lane_input_id"],
            from_status=prior_status,
            to_status="invalidated",
            transition_reason="entry_authoritatively_rejected",
            trigger_ref=str(command["exchange_command_id"]),
            writer="entry_effect_projection",
            event_payload={
                "protected_submit_attempt_id": attempt[
                    "protected_submit_attempt_id"
                ],
                "entry_effect_state": "rejected",
            },
            occurred_at_ms=now_ms,
            created_at_ms=now_ms,
        )
    )


def _update_attempt(
    conn: sa.engine.Connection,
    *,
    table: sa.Table,
    attempt: dict[str, Any],
    decision: EntryEffectDecision,
    now_ms: int,
) -> None:
    current_state = str(attempt.get("entry_effect_state") or "not_called")
    if current_state not in {"not_called", decision.entry_effect_state.value}:
        raise EntryEffectProjectionError(
            "entry_effect_state_conflict:"
            f"{current_state}:{decision.entry_effect_state.value}"
        )
    observed_at = attempt.get("entry_effect_observed_at_ms") or now_ms
    values: dict[str, Any] = {
        "entry_effect_state": decision.entry_effect_state.value,
        "entry_effect_observed_at_ms": observed_at,
        "exchange_write_called": True,
        "updated_at_ms": max(int(attempt.get("updated_at_ms") or 0), now_ms),
    }
    current_barrier = str(
        attempt.get("protection_barrier_state") or "not_started"
    )
    if current_barrier in {
        "not_started",
        "fill_pending",
        "initial_stop_pending",
    }:
        values["protection_barrier_state"] = (
            decision.protection_barrier_state.value
        )
        values["protection_quantity"] = decision.protection_quantity
    conn.execute(
        table.update()
        .where(table.c.protected_submit_attempt_id == attempt["protected_submit_attempt_id"])
        .values(**values)
    )


def _project_ticket_and_handoff(
    conn: sa.engine.Connection,
    *,
    attempt: dict[str, Any],
    command: dict[str, Any],
    decision: EntryEffectDecision,
    now_ms: int,
) -> None:
    ticket_table = _table(conn, "brc_action_time_tickets")
    ticket = conn.execute(
        sa.select(ticket_table).where(ticket_table.c.ticket_id == attempt["ticket_id"])
    ).mappings().one()
    prior_status = str(ticket["status"])
    if prior_status not in {"finalgate_ready", "expired", "submitted"}:
        raise EntryEffectProjectionError(
            f"entry_effect_ticket_state_invalid:{prior_status}"
        )
    if prior_status in {"finalgate_ready", "expired"}:
        conn.execute(
            ticket_table.update()
            .where(
                ticket_table.c.ticket_id == attempt["ticket_id"],
                ticket_table.c.status == prior_status,
            )
            .values(status="submitted")
        )
    handoff_table = _table(conn, "brc_operation_layer_handoffs")
    conn.execute(
        handoff_table.update()
        .where(
            handoff_table.c.operation_layer_handoff_id
            == attempt["operation_layer_handoff_id"]
        )
        .values(status="submitted", updated_at_ms=now_ms)
    )
    event_table = _table(conn, "brc_action_time_ticket_events")
    event_id = _stable_id(
        "entry_effect_ticket_event",
        str(attempt["ticket_id"]),
        str(command["exchange_command_id"]),
    )
    if conn.execute(
        sa.select(event_table.c.ticket_event_id).where(
            event_table.c.ticket_event_id == event_id
        )
    ).first():
        return
    conn.execute(
        event_table.insert().values(
            ticket_event_id=event_id,
            ticket_id=attempt["ticket_id"],
            action_time_lane_input_id=attempt["action_time_lane_input_id"],
            from_status=prior_status,
            to_status="submitted",
            transition_reason="entry_exchange_effect_committed",
            trigger_ref=str(command["exchange_command_id"]),
            writer="entry_effect_projection",
            event_payload={
                "protected_submit_attempt_id": attempt[
                    "protected_submit_attempt_id"
                ],
                "entry_effect_state": decision.entry_effect_state.value,
            },
            occurred_at_ms=now_ms,
            created_at_ms=now_ms,
        )
    )


def _project_lifecycle(
    conn: sa.engine.Connection,
    *,
    attempt: dict[str, Any],
    command: dict[str, Any],
    decision: EntryEffectDecision,
    now_ms: int,
) -> None:
    if decision.lifecycle_status is None or decision.lifecycle_event_type is None:
        return
    table = _table(conn, "brc_ticket_bound_order_lifecycle_runs")
    run_id = _stable_id("ticket_order_lifecycle", str(attempt["ticket_id"]))
    existing = conn.execute(
        sa.select(table).where(table.c.lifecycle_run_id == run_id)
    ).mappings().first()
    row = {
        "lifecycle_run_id": run_id,
        "ticket_id": str(attempt["ticket_id"]),
        "protected_submit_attempt_id": str(attempt["protected_submit_attempt_id"]),
        "strategy_group_id": str(attempt["strategy_group_id"]),
        "symbol": str(attempt["symbol"]),
        "side": str(attempt["side"]),
        "runtime_profile_id": str(attempt["runtime_profile_id"]),
        "status": decision.lifecycle_status,
        "entry_local_order_id": str(command.get("local_order_id") or "") or None,
        "entry_exchange_order_id": str(command.get("exchange_order_id") or "") or None,
        "entry_fill_confirmed": decision.protection_quantity is not None,
        "entry_filled_qty": decision.protection_quantity,
        "entry_avg_price": (
            _decimal_or_none(command.get("average_exec_price"))
            if decision.protection_quantity is not None
            else None
        ),
        "exit_protection_set_id": None,
        "first_blocker": (
            "entry_exchange_outcome_unknown"
            if decision.lifecycle_status == "entry_unknown"
            else None
        ),
        "blockers": (
            ["entry_exchange_outcome_unknown"]
            if decision.lifecycle_status == "entry_unknown"
            else []
        ),
        "warnings": [],
        "authority_boundary": AUTHORITY_BOUNDARY,
        "created_at_ms": int(attempt.get("created_at_ms") or now_ms),
        "updated_at_ms": now_ms,
    }
    if existing is None:
        conn.execute(table.insert().values(**row))
    elif str(existing["status"]) in _IMMEDIATE_LIFECYCLE_STATUSES:
        conn.execute(
            table.update()
            .where(table.c.lifecycle_run_id == run_id)
            .values(**{key: value for key, value in row.items() if key != "created_at_ms"})
        )
    event_table = _table(conn, "brc_ticket_bound_lifecycle_events")
    event_id = _stable_id(
        "entry_effect_lifecycle_event",
        run_id,
        str(command["exchange_command_id"]),
        decision.entry_effect_state.value,
    )
    if conn.execute(
        sa.select(event_table.c.lifecycle_event_id).where(
            event_table.c.lifecycle_event_id == event_id
        )
    ).first():
        return
    conn.execute(
        event_table.insert().values(
            lifecycle_event_id=event_id,
            lifecycle_run_id=run_id,
            ticket_id=str(attempt["ticket_id"]),
            protected_submit_attempt_id=str(attempt["protected_submit_attempt_id"]),
            event_type=decision.lifecycle_event_type,
            event_payload={
                "exchange_command_id": command["exchange_command_id"],
                "entry_effect_state": decision.entry_effect_state.value,
                "executed_qty": (
                    str(decision.protection_quantity)
                    if decision.protection_quantity is not None
                    else None
                ),
                "average_exec_price": (
                    str(command.get("average_exec_price"))
                    if command.get("average_exec_price") is not None
                    else None
                ),
            },
            created_at_ms=now_ms,
        )
    )


def _table(conn: sa.engine.Connection, name: str) -> sa.Table:
    return sa.Table(name, sa.MetaData(), autoload_with=conn)


def _decimal_or_none(value: Any) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:32]
    return f"{prefix}:{digest}"
