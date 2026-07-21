"""Atomic PostgreSQL projection for a durable ENTRY command result."""

from __future__ import annotations

from decimal import Decimal
import hashlib
from typing import Any

import sqlalchemy as sa

from src.application.action_time.exchange_command import (
    record_exchange_command_outcome,
    resize_prepared_protection_command_to_entry_fill,
)
from src.domain.entry_effect import EntryEffectDecision, classify_entry_effect
from src.domain.ticket_bound_exchange_command import (
    ExchangeCommandOutcomeClass,
    ExchangeCommandState,
)
from src.application.runtime_incident_projector import (
    ensure_protection_barrier_hold,
    project_protection_barrier_failure,
    resolve_initial_stop_incident,
    supersede_protection_barrier_generation,
)


AUTHORITY_BOUNDARY = (
    "entry_effect_projection; durable_exchange_command_and_ticket_lifecycle_truth"
)
INITIAL_STOP_SLA_MS = 15_000
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
    attempt = (
        conn.execute(
            sa.select(attempt_table).where(
                attempt_table.c.protected_submit_attempt_id == attempt_id
            )
        )
        .mappings()
        .one()
    )
    attempt_row = dict(attempt)
    attempt_transition = _update_attempt(
        conn,
        table=attempt_table,
        attempt=attempt_row,
        decision=decision,
        now_ms=now_ms,
    )
    if decision.entry_effect_state.value == "accepted_filled":
        updated_attempt = dict(
            conn.execute(
                sa.select(attempt_table).where(
                    attempt_table.c.protected_submit_attempt_id == attempt_id
                )
            ).mappings().one()
        )
        if str(updated_attempt.get("protection_barrier_state") or "") not in {
            "initial_stop_confirmed",
            "degraded",
            "closed",
        }:
            ensure_protection_barrier_hold(
                conn,
                protected_submit_attempt_id=attempt_id,
                protection_barrier_generation=int(
                    updated_attempt.get("protection_barrier_generation") or 1
                ),
                blocker="initial_stop_pending",
                next_action="establish_exact_initial_stop_within_sla",
                now_ms=now_ms,
            )
    _terminalize_non_filled_protection_siblings(
        conn,
        command=command,
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
        attempt_transition=attempt_transition,
        now_ms=now_ms,
    )
    return decision


def project_reconciled_entry_execution(
    conn: sa.engine.Connection,
    *,
    protected_submit_attempt_id: str,
    exchange_order_id: str,
    executed_qty: Decimal,
    average_exec_price: Decimal,
    exchange_observed_at_ms: int | None,
    now_ms: int,
) -> EntryEffectDecision:
    """Conserve monotonic cumulative ENTRY fills from an exchange snapshot.

    The durable exchange command is the result authority.  Reconciliation may
    advance cumulative execution facts, but it may never reduce quantity,
    change exchange-order identity, or create a second ENTRY command.
    """

    commands = _table(conn, "brc_ticket_bound_exchange_commands")
    entry_rows = list(
        conn.execute(
            sa.select(commands).where(
                commands.c.protected_submit_attempt_id
                == protected_submit_attempt_id,
                commands.c.order_role == "ENTRY",
            )
        ).mappings()
    )
    if len(entry_rows) != 1:
        raise EntryEffectProjectionError("entry_command_cardinality_invalid")
    entry = dict(entry_rows[0])
    if str(entry.get("exchange_order_id") or "") != exchange_order_id:
        raise EntryEffectProjectionError("entry_exchange_order_identity_mismatch")
    if str(entry.get("command_state") or "") not in {
        "confirmed_submitted",
        "reconciled_submitted",
    }:
        raise EntryEffectProjectionError("entry_command_not_submitted")
    requested_qty = _decimal_or_none(entry.get("amount"))
    if requested_qty is None or executed_qty <= 0 or executed_qty > requested_qty:
        raise EntryEffectProjectionError("entry_cumulative_executed_qty_invalid")
    if average_exec_price <= 0:
        raise EntryEffectProjectionError("entry_cumulative_average_price_invalid")
    current_qty = _decimal_or_none(entry.get("executed_qty")) or Decimal("0")
    if executed_qty < current_qty:
        raise EntryEffectProjectionError("entry_cumulative_executed_qty_regressed")

    exchange_result = _mapping(entry.get("exchange_result"))
    exchange_result.update(
        {
            "exchange_order_id": exchange_order_id,
            "exchange_order_status": "FILLED",
            "filled_qty": str(executed_qty),
            "average_exec_price": str(average_exec_price),
            "exchange_observed_at_ms": exchange_observed_at_ms or now_ms,
            "reconciliation_source": "post_submit_exchange_snapshot",
        }
    )
    conn.execute(
        commands.update()
        .where(commands.c.exchange_command_id == entry["exchange_command_id"])
        .values(
            command_state="reconciled_submitted",
            outcome_class="reconciled_exchange_truth",
            exchange_order_status="FILLED",
            executed_qty=executed_qty,
            average_exec_price=average_exec_price,
            exchange_observed_at_ms=exchange_observed_at_ms or now_ms,
            result_facts_complete=True,
            exchange_result=exchange_result,
            resolved_at_ms=entry.get("resolved_at_ms") or now_ms,
            updated_at_ms=max(int(entry.get("updated_at_ms") or 0), now_ms),
        )
    )
    updated_entry = dict(
        conn.execute(
            sa.select(commands).where(
                commands.c.exchange_command_id == entry["exchange_command_id"]
            )
        ).mappings().one()
    )
    decision = project_entry_effect(conn, command=updated_entry, now_ms=now_ms)
    if decision is None:
        raise EntryEffectProjectionError("entry_effect_projection_missing")
    return decision


def _terminalize_non_filled_protection_siblings(
    conn: sa.engine.Connection,
    *,
    command: dict[str, Any],
    decision: EntryEffectDecision,
    now_ms: int,
) -> None:
    state = decision.entry_effect_state.value
    if state not in {"accepted_zero_fill", "outcome_unknown"}:
        return
    commands = _table(conn, "brc_ticket_bound_exchange_commands")
    siblings = (
        conn.execute(
            sa.select(commands).where(
                commands.c.protected_submit_attempt_id
                == command.get("protected_submit_attempt_id"),
                commands.c.order_role.in_(("SL", "TP1")),
                commands.c.command_state == "prepared",
            )
        )
        .mappings()
        .all()
    )
    for sibling in siblings:
        role = str(sibling["order_role"])
        hard_stop = state == "outcome_unknown" and role == "SL"
        reason = (
            "entry_filled_qty_missing_or_unknown_blocks_initial_protection"
            if hard_stop
            else "entry_has_no_confirmed_protection_quantity"
        )
        record_exchange_command_outcome(
            conn,
            exchange_command_id=str(sibling["exchange_command_id"]),
            target_state=(
                ExchangeCommandState.HARD_STOPPED
                if hard_stop
                else ExchangeCommandState.RECONCILED_ABSENT
            ),
            outcome_class=(
                ExchangeCommandOutcomeClass.CONTRADICTORY_TRUTH
                if hard_stop
                else ExchangeCommandOutcomeClass.RECONCILED_ABSENCE
            ),
            exchange_result={
                "error_code": (
                    "entry_filled_qty_zero_no_protection_dispatch"
                    if state == "accepted_zero_fill"
                    else reason
                ),
                "error_message": reason,
                "exchange_write_called": False,
            },
            now_ms=now_ms,
        )


def project_protection_result(
    conn: sa.engine.Connection,
    *,
    command: dict[str, Any],
    now_ms: int,
) -> None:
    """Project exact-source initial-stop truth in the result transaction."""

    role = str(command.get("order_role") or "").upper()
    source = str(command.get("command_source") or "")
    if role not in {"SL", "TP1"} or source not in {
        "protected_submit",
        "protection_recovery",
    }:
        return
    attempt_id = str(command.get("protected_submit_attempt_id") or "")
    table = _table(conn, "brc_ticket_bound_protected_submit_attempts")
    attempt = (
        conn.execute(
            sa.select(table).where(table.c.protected_submit_attempt_id == attempt_id)
        )
        .mappings()
        .one()
    )
    generation = _command_protection_barrier_generation(
        conn,
        command=command,
        attempt=dict(attempt),
    )
    state = str(command.get("command_state") or "")
    submitted = state in {"confirmed_submitted", "reconciled_submitted"}
    if role == "TP1":
        if not submitted and str(attempt.get("protection_barrier_state") or "") in {
            "initial_stop_confirmed",
            "degraded",
        }:
            project_protection_barrier_failure(
                conn,
                protected_submit_attempt_id=attempt_id,
                order_role="TP1",
                blocker=_protection_failure_blocker(command, role="TP1"),
                outcome_ambiguous=state == "outcome_unknown",
                protection_barrier_generation=generation,
                trigger_ref=str(command.get("exchange_command_id") or ""),
                now_ms=now_ms,
            )
        return
    _restore_submitted_ticket_for_effect_active_attempt(
        conn,
        attempt=dict(attempt),
        command=command,
        now_ms=now_ms,
    )
    current_barrier = str(attempt.get("protection_barrier_state") or "not_started")
    if submitted and current_barrier in {
        "initial_stop_confirmed",
        "degraded",
        "closed",
    }:
        # A replay cannot strengthen or weaken an already terminal barrier.
        # The transition which established this state already validated the
        # exact ENTRY predecessor and cleared its generation-scoped incident.
        return
    if submitted:
        commands = _table(conn, "brc_ticket_bound_exchange_commands")
        entry = (
            conn.execute(
                sa.select(commands).where(
                    commands.c.protected_submit_attempt_id == attempt_id,
                    commands.c.order_role == "ENTRY",
                )
            )
            .mappings()
            .one()
        )
        blockers = _initial_stop_confirmation_blockers(
            conn=conn,
            command=command,
            attempt=dict(attempt),
            entry=dict(entry),
        )
        if blockers:
            raise EntryEffectProjectionError(blockers[0])
        if current_barrier in {"initial_stop_pending", "hard_stopped"}:
            conn.execute(
                table.update()
                .where(table.c.protected_submit_attempt_id == attempt_id)
                .values(
                    protection_barrier_state="initial_stop_confirmed",
                    initial_stop_confirmed_at_ms=(
                        attempt.get("initial_stop_confirmed_at_ms") or now_ms
                    ),
                    updated_at_ms=max(
                        int(attempt.get("updated_at_ms") or 0),
                        now_ms,
                    ),
                )
            )
        resolve_initial_stop_incident(
            conn,
            protected_submit_attempt_id=attempt_id,
            protection_barrier_generation=generation,
            resolution_source="initial_stop_exchange_command_confirmed",
            now_ms=now_ms,
        )
        return
    if state in {"confirmed_rejected", "outcome_unknown", "hard_stopped"} and (
        current_barrier in {"not_started", "fill_pending", "initial_stop_pending"}
    ):
        conn.execute(
            table.update()
            .where(table.c.protected_submit_attempt_id == attempt_id)
            .values(
                protection_barrier_state="hard_stopped",
                updated_at_ms=max(
                    int(attempt.get("updated_at_ms") or 0),
                    now_ms,
                ),
            )
        )
        if str(attempt.get("entry_effect_state") or "") == "accepted_filled":
            project_protection_barrier_failure(
                conn,
                protected_submit_attempt_id=attempt_id,
                order_role="SL",
                blocker=_protection_failure_blocker(command, role="SL"),
                outcome_ambiguous=state == "outcome_unknown",
                protection_barrier_generation=generation,
                trigger_ref=str(command.get("exchange_command_id") or ""),
                now_ms=now_ms,
            )


def _restore_submitted_ticket_for_effect_active_attempt(
    conn: sa.engine.Connection,
    *,
    attempt: dict[str, Any],
    command: dict[str, Any],
    now_ms: int,
) -> None:
    """Repair an expired pre-submit projection after ENTRY effect is durable."""

    if str(attempt.get("entry_effect_state") or "") not in {
        "accepted_filled",
        "accepted_zero_fill",
        "outcome_unknown",
    }:
        return
    tickets = _table(conn, "brc_action_time_tickets")
    updated_ticket_id = conn.execute(
        tickets.update()
        .where(
            tickets.c.ticket_id == attempt["ticket_id"],
            tickets.c.status == "expired",
        )
        .values(status="submitted")
        .returning(tickets.c.ticket_id)
    ).scalar_one_or_none()
    if updated_ticket_id is None:
        return
    events = _table(conn, "brc_action_time_ticket_events")
    event_id = _stable_id(
        "entry_effect_ticket_repair_event",
        str(attempt["ticket_id"]),
        str(command["exchange_command_id"]),
    )
    if conn.execute(
        sa.select(events.c.ticket_event_id).where(events.c.ticket_event_id == event_id)
    ).first():
        return
    conn.execute(
        events.insert().values(
            ticket_event_id=event_id,
            ticket_id=attempt["ticket_id"],
            action_time_lane_input_id=attempt["action_time_lane_input_id"],
            from_status="expired",
            to_status="submitted",
            transition_reason="entry_effect_prevents_ticket_expiration",
            trigger_ref=str(command["exchange_command_id"]),
            writer="entry_effect_projection",
            event_payload={
                "protected_submit_attempt_id": attempt["protected_submit_attempt_id"],
                "entry_effect_state": attempt["entry_effect_state"],
            },
            occurred_at_ms=now_ms,
            created_at_ms=now_ms,
        )
    )


def _initial_stop_confirmation_blockers(
    *,
    conn: sa.engine.Connection,
    command: dict[str, Any],
    attempt: dict[str, Any],
    entry: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    attempt_id = str(attempt.get("protected_submit_attempt_id") or "")
    blockers.extend(
        _protection_source_blockers(
            conn,
            command=command,
            attempt=attempt,
            entry=entry,
        )
    )
    if (
        str(entry.get("source_command_id") or "") != attempt_id
        or str(entry.get("protected_submit_attempt_id") or "") != attempt_id
        or str(entry.get("command_state") or "")
        not in {"confirmed_submitted", "reconciled_submitted"}
        or entry.get("result_facts_complete") not in {True, 1}
    ):
        blockers.append("initial_stop_entry_predecessor_invalid")
    if str(command.get("outcome_class") or "") not in {
        "exchange_accepted",
        "reconciled_exchange_truth",
    } or not str(command.get("exchange_order_id") or ""):
        blockers.append("initial_stop_exchange_acceptance_invalid")
    if str(attempt.get("entry_effect_state") or "") != "accepted_filled":
        blockers.append("initial_stop_entry_effect_not_filled")
    if str(attempt.get("protection_barrier_state") or "") not in {
        "initial_stop_pending",
        "initial_stop_confirmed",
        "degraded",
        "hard_stopped",
        "closed",
    }:
        blockers.append("initial_stop_barrier_phase_invalid")
    if str(command.get("command_kind") or "") != "place_order":
        blockers.append("initial_stop_command_kind_invalid")
    if (
        command.get("reduce_only") not in {True, 1}
        or str(command.get("reduce_intent") or "") != "reduce_position"
    ):
        blockers.append("initial_stop_reduce_intent_invalid")
    expected = _decimal_or_none(attempt.get("protection_quantity"))
    actual = _decimal_or_none(command.get("amount"))
    if expected is None or expected <= 0 or actual != expected:
        blockers.append("initial_stop_protection_quantity_mismatch")
    entry_quantity = _decimal_or_none(entry.get("executed_qty"))
    if entry_quantity != expected:
        blockers.append("initial_stop_entry_quantity_mismatch")
    for field in (
        "ticket_id",
        "account_id",
        "exchange_id",
        "exchange_instrument_id",
        "exposure_episode_id",
        "gateway_symbol",
        "side",
        "position_mode",
        "position_side",
        "position_bucket",
        "netting_domain_key",
    ):
        if entry.get(field) != command.get(field):
            blockers.append(f"initial_stop_entry_identity_mismatch:{field}")
    return blockers


def _command_protection_barrier_generation(
    conn: sa.engine.Connection,
    *,
    command: dict[str, Any],
    attempt: dict[str, Any],
) -> int:
    source = str(command.get("command_source") or "")
    if source == "protected_submit":
        return 1
    if source != "protection_recovery":
        raise EntryEffectProjectionError("initial_stop_command_source_invalid")
    recovery = _row_by_value(
        conn,
        table_name="brc_ticket_bound_protection_recovery_commands",
        column_name="protection_recovery_command_id",
        value=str(command.get("source_command_id") or ""),
    )
    if not recovery:
        raise EntryEffectProjectionError("initial_stop_recovery_source_missing")
    return int(recovery.get("protection_barrier_generation") or 0)


def _protection_source_blockers(
    conn: sa.engine.Connection,
    *,
    command: dict[str, Any],
    attempt: dict[str, Any],
    entry: dict[str, Any],
) -> list[str]:
    attempt_id = str(attempt.get("protected_submit_attempt_id") or "")
    source = str(command.get("command_source") or "")
    if source == "protected_submit":
        return (
            []
            if str(command.get("source_command_id") or "") == attempt_id
            else ["initial_stop_source_attempt_mismatch"]
        )
    if source != "protection_recovery":
        return ["initial_stop_command_source_invalid"]
    recovery = _row_by_value(
        conn,
        table_name="brc_ticket_bound_protection_recovery_commands",
        column_name="protection_recovery_command_id",
        value=str(command.get("source_command_id") or ""),
    )
    if not recovery:
        return ["initial_stop_recovery_source_missing"]
    blockers: list[str] = []
    expected = {
        "protected_submit_attempt_id": attempt_id,
        "ticket_id": str(attempt.get("ticket_id") or ""),
        "exposure_episode_id": str(entry.get("exposure_episode_id") or ""),
        "netting_domain_key": str(entry.get("netting_domain_key") or ""),
        "source_entry_exchange_command_id": str(
            entry.get("exchange_command_id") or ""
        ),
    }
    for field, value in expected.items():
        if str(recovery.get(field) or "") != value:
            blockers.append(f"initial_stop_recovery_identity_mismatch:{field}")
    if int(recovery.get("protection_barrier_generation") or 0) != int(
        attempt.get("protection_barrier_generation") or 1
    ):
        blockers.append("initial_stop_recovery_generation_stale")
    return blockers


def _protection_failure_blocker(command: dict[str, Any], *, role: str) -> str:
    state = str(command.get("command_state") or "")
    if state == "outcome_unknown":
        return f"{role.lower()}_exchange_outcome_unknown"
    if state == "confirmed_rejected":
        return f"{role.lower()}_exchange_rejected"
    return str(command.get("exchange_error_code") or f"{role.lower()}_hard_stopped")


def _restore_effect_capacity_if_expiration_won(
    conn: sa.engine.Connection,
    *,
    attempt: dict[str, Any],
    command: dict[str, Any],
    now_ms: int,
) -> None:
    reservations = _table(conn, "brc_budget_reservations")
    reservation = (
        conn.execute(
            sa.select(reservations).where(
                reservations.c.ticket_id == attempt["ticket_id"]
            )
        )
        .mappings()
        .one_or_none()
    )
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
            current_first_blocker=("entry_effect_capacity_revalidation_required"),
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
    ticket = (
        conn.execute(
            sa.select(ticket_table).where(
                ticket_table.c.ticket_id == attempt["ticket_id"]
            )
        )
        .mappings()
        .one()
    )
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
                "protected_submit_attempt_id": attempt["protected_submit_attempt_id"],
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
) -> dict[str, Any]:
    current_state = str(attempt.get("entry_effect_state") or "not_called")
    late_fill_transition = (
        current_state in {"accepted_zero_fill", "outcome_unknown"}
        and decision.entry_effect_state.value == "accepted_filled"
    )
    reconciled_absence_transition = (
        current_state == "outcome_unknown"
        and decision.entry_effect_state.value == "reconciled_absent"
    )
    prior_quantity = _decimal_or_none(attempt.get("protection_quantity"))
    next_quantity = decision.protection_quantity
    cumulative_fill_increase = (
        current_state == "accepted_filled"
        and decision.entry_effect_state.value == "accepted_filled"
        and prior_quantity is not None
        and next_quantity is not None
        and next_quantity > prior_quantity
    )
    if (
        current_state == "accepted_filled"
        and decision.entry_effect_state.value == "accepted_filled"
        and prior_quantity is not None
        and next_quantity is not None
        and next_quantity < prior_quantity
    ):
        raise EntryEffectProjectionError("entry_cumulative_fill_quantity_regressed")
    if current_state not in {"not_called", decision.entry_effect_state.value} and not (
        late_fill_transition or reconciled_absence_transition
    ):
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
    current_barrier = str(attempt.get("protection_barrier_state") or "not_started")
    protection_dispatch_started = cumulative_fill_increase and _protection_dispatch_started(
        conn,
        protected_submit_attempt_id=str(attempt["protected_submit_attempt_id"]),
    )
    if late_fill_transition:
        values["protection_barrier_generation"] = (
            int(attempt.get("protection_barrier_generation") or 1) + 1
        )
    elif cumulative_fill_increase and protection_dispatch_started:
        values["protection_barrier_generation"] = (
            int(attempt.get("protection_barrier_generation") or 1) + 1
        )
        values["initial_stop_confirmed_at_ms"] = None
    generation_advanced = late_fill_transition or (
        cumulative_fill_increase and protection_dispatch_started
    )
    if generation_advanced:
        supersede_protection_barrier_generation(
            conn,
            protected_submit_attempt_id=str(
                attempt["protected_submit_attempt_id"]
            ),
            protection_barrier_generation=int(
                attempt.get("protection_barrier_generation") or 1
            ),
            now_ms=now_ms,
        )
    if decision.entry_effect_state.value == "accepted_filled" and (
        current_state != "accepted_filled"
        or generation_advanced
        or attempt.get("initial_stop_deadline_at_ms") is None
    ):
        values["initial_stop_deadline_at_ms"] = now_ms + INITIAL_STOP_SLA_MS
    if current_barrier in {
        "not_started",
        "fill_pending",
        "initial_stop_pending",
    } or late_fill_transition or reconciled_absence_transition or cumulative_fill_increase:
        values["protection_barrier_state"] = decision.protection_barrier_state.value
        values["protection_quantity"] = decision.protection_quantity
    conn.execute(
        table.update()
        .where(
            table.c.protected_submit_attempt_id
            == attempt["protected_submit_attempt_id"]
        )
        .values(**values)
    )
    if cumulative_fill_increase and not protection_dispatch_started:
        _resize_undispatched_protection_commands(
            conn,
            protected_submit_attempt_id=str(attempt["protected_submit_attempt_id"]),
            now_ms=now_ms,
        )
    return {
        "cumulative_fill_increase": cumulative_fill_increase,
        "protection_generation_advanced": (
            generation_advanced
        ),
    }


def _protection_dispatch_started(
    conn: sa.engine.Connection,
    *,
    protected_submit_attempt_id: str,
) -> bool:
    commands = _table(conn, "brc_ticket_bound_exchange_commands")
    row = conn.execute(
        sa.select(commands.c.exchange_command_id)
        .where(
            commands.c.protected_submit_attempt_id == protected_submit_attempt_id,
            commands.c.order_role.in_(("SL", "TP1")),
            sa.or_(
                commands.c.dispatch_started_at_ms.is_not(None),
                commands.c.exchange_order_id.is_not(None),
                commands.c.command_state.in_(
                    (
                        "dispatching",
                        "confirmed_submitted",
                        "reconciled_submitted",
                        "outcome_unknown",
                        "confirmed_rejected",
                    )
                ),
            ),
        )
        .limit(1)
    ).first()
    return row is not None


def _resize_undispatched_protection_commands(
    conn: sa.engine.Connection,
    *,
    protected_submit_attempt_id: str,
    now_ms: int,
) -> None:
    commands = _table(conn, "brc_ticket_bound_exchange_commands")
    command_ids = conn.execute(
        sa.select(commands.c.exchange_command_id).where(
            commands.c.protected_submit_attempt_id == protected_submit_attempt_id,
            commands.c.order_role.in_(("SL", "TP1")),
            commands.c.command_state == "prepared",
        )
    ).scalars()
    for command_id in command_ids:
        resize_prepared_protection_command_to_entry_fill(
            conn,
            exchange_command_id=str(command_id),
            now_ms=now_ms,
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
    ticket = (
        conn.execute(
            sa.select(ticket_table).where(
                ticket_table.c.ticket_id == attempt["ticket_id"]
            )
        )
        .mappings()
        .one()
    )
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
    if prior_status == "submitted":
        return
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
                "protected_submit_attempt_id": attempt["protected_submit_attempt_id"],
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
    attempt_transition: dict[str, Any],
    now_ms: int,
) -> None:
    if decision.lifecycle_status is None or decision.lifecycle_event_type is None:
        return
    table = _table(conn, "brc_ticket_bound_order_lifecycle_runs")
    run_id = _stable_id("ticket_order_lifecycle", str(attempt["ticket_id"]))
    existing = (
        conn.execute(
            sa.select(table).where(table.c.ticket_id == str(attempt["ticket_id"]))
        )
        .mappings()
        .first()
    )
    if existing is not None:
        run_id = str(existing["lifecycle_run_id"])
    generation_advanced = attempt_transition.get("protection_generation_advanced") is True
    lifecycle_status = (
        "protection_missing" if generation_advanced else decision.lifecycle_status
    )
    lifecycle_blockers = (
        ["sl_protection_quantity_mismatch"]
        if generation_advanced
        else (
            ["entry_exchange_outcome_unknown"]
            if decision.lifecycle_status == "entry_unknown"
            else []
        )
    )
    row = {
        "lifecycle_run_id": run_id,
        "ticket_id": str(attempt["ticket_id"]),
        "protected_submit_attempt_id": str(attempt["protected_submit_attempt_id"]),
        "strategy_group_id": str(attempt["strategy_group_id"]),
        "symbol": str(attempt["symbol"]),
        "side": str(attempt["side"]),
        "runtime_profile_id": str(attempt["runtime_profile_id"]),
        "status": lifecycle_status,
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
        "first_blocker": lifecycle_blockers[0] if lifecycle_blockers else None,
        "blockers": lifecycle_blockers,
        "warnings": [],
        "authority_boundary": AUTHORITY_BOUNDARY,
        "created_at_ms": int(attempt.get("created_at_ms") or now_ms),
        "updated_at_ms": now_ms,
    }
    if existing is None:
        conn.execute(table.insert().values(**row))
    elif generation_advanced or str(existing["status"]) in _IMMEDIATE_LIFECYCLE_STATUSES:
        conn.execute(
            table.update()
            .where(table.c.lifecycle_run_id == run_id)
            .values(
                **{key: value for key, value in row.items() if key != "created_at_ms"}
            )
        )
    event_table = _table(conn, "brc_ticket_bound_lifecycle_events")
    event_id = _stable_id(
        "entry_effect_lifecycle_event",
        run_id,
        str(command["exchange_command_id"]),
        decision.entry_effect_state.value,
        _canonical_decimal(decision.protection_quantity),
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


def _row_by_value(
    conn: sa.engine.Connection,
    *,
    table_name: str,
    column_name: str,
    value: str,
) -> dict[str, Any]:
    if not value:
        return {}
    table = _table(conn, table_name)
    row = conn.execute(
        sa.select(table).where(table.c[column_name] == value)
    ).mappings().one_or_none()
    return dict(row) if row else {}


def _decimal_or_none(value: Any) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


def _canonical_decimal(value: Decimal | None) -> str:
    """Return a scale-independent identity component for a decimal fact."""

    if value is None:
        return ""
    return format(value.normalize(), "f")


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        import json

        parsed = json.loads(value)
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:32]
    return f"{prefix}:{digest}"
