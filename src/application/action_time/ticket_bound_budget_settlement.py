"""Independent idempotent Ticket budget settlement from terminal evidence."""

from __future__ import annotations

import json
from typing import Any

import sqlalchemy as sa

from src.application.action_time.budget_reservation_transition import (
    transition_budget_reservation,
)
from src.application.runtime_incident_projector import (
    INITIAL_STOP_INCIDENT_TYPE,
    protection_barrier_incident_id,
)
from src.domain.netting_domain import build_netting_domain_key
from src.domain.ticket_bound_exchange_command import (
    exchange_command_effect_is_terminal,
)


TERMINAL_EXCHANGE_COMMAND_STATES = {
    "confirmed_submitted",
    "confirmed_rejected",
    "reconciled_submitted",
    "reconciled_absent",
    "hard_stopped",
}


def settle_ticket_bound_budget(
    conn: sa.engine.Connection,
    *,
    ticket_id: str,
    settlement_evidence_id: str,
    now_ms: int,
) -> dict[str, Any]:
    table = sa.Table(
        "brc_budget_reservations",
        sa.MetaData(),
        autoload_with=conn,
    )
    row = conn.execute(
        sa.select(table).where(table.c.ticket_id == ticket_id).with_for_update()
    ).mappings().one_or_none()
    if not row:
        return _blocked("ticket_budget_reservation_missing")
    status = str(row.get("status") or "")
    if status == "released":
        return {
            "status": "released",
            "budget_reservation_id": row["budget_reservation_id"],
            "settlement_evidence_id": settlement_evidence_id,
            "runtime_budget_mutated": False,
            "blockers": [],
        }
    if status != "consumed":
        return _blocked(f"ticket_budget_reservation_not_consumed:{status or 'missing'}")
    proof_blocker = _terminal_release_proof_blocker(
        conn,
        ticket_id=ticket_id,
        reservation=dict(row),
    )
    if proof_blocker:
        return _blocked(proof_blocker)
    transition = transition_budget_reservation(
        conn,
        budget_reservation_id=str(row["budget_reservation_id"]),
        to_status="released",
        reason=f"lifecycle_closed:{settlement_evidence_id}",
        evidence_ref=settlement_evidence_id,
        now_ms=now_ms,
    )
    if transition.first_blocker:
        return _blocked(transition.first_blocker)
    return {
        "status": "released",
        "budget_reservation_id": row["budget_reservation_id"],
        "settlement_evidence_id": settlement_evidence_id,
        "settled_at_ms": now_ms,
        "runtime_budget_mutated": transition.transitioned,
        "blockers": [],
    }


def _blocked(blocker: str) -> dict[str, Any]:
    return {
        "status": "blocked",
        "first_blocker": blocker,
        "blockers": [blocker],
        "runtime_budget_mutated": False,
    }


def terminalize_effect_active_attempt_for_flat_settlement(
    conn: sa.engine.Connection,
    *,
    ticket_id: str,
    protected_submit_attempt_id: str,
    now_ms: int,
) -> dict[str, Any]:
    """Close one current barrier only after the finalizer proved a flat exit."""

    reservations = _table(conn, "brc_budget_reservations")
    reservation = conn.execute(
        sa.select(reservations)
        .where(reservations.c.ticket_id == ticket_id)
        .with_for_update()
    ).mappings().one_or_none()
    if reservation is None:
        return _blocked("ticket_budget_reservation_missing")
    if str(reservation.get("status") or "") not in {"consumed", "released"}:
        return _blocked("ticket_budget_reservation_not_consumed")

    attempts = _table(conn, "brc_ticket_bound_protected_submit_attempts")
    attempt = conn.execute(
        sa.select(attempts)
        .where(
            attempts.c.ticket_id == ticket_id,
            attempts.c.protected_submit_attempt_id
            == protected_submit_attempt_id,
        )
        .with_for_update()
    ).mappings().one_or_none()
    if attempt is None:
        return _blocked("ticket_budget_protected_submit_attempt_missing")

    prerelease_blocker = _typed_capacity_release_blocker(
        conn,
        ticket_id=ticket_id,
        ignore_effect_active_attempt=True,
    )
    if prerelease_blocker:
        return _blocked(prerelease_blocker)
    if str(attempt.get("entry_effect_state") or "") != "accepted_filled":
        return {"status": "ready", "runtime_attempt_mutated": False, "blockers": []}
    barrier = str(attempt.get("protection_barrier_state") or "")
    if barrier == "closed":
        return {"status": "ready", "runtime_attempt_mutated": False, "blockers": []}
    if barrier not in {
        "initial_stop_pending",
        "initial_stop_confirmed",
        "degraded",
        "hard_stopped",
    }:
        return _blocked("ticket_budget_effect_barrier_not_closable")
    generation = int(attempt.get("protection_barrier_generation") or 1)
    updated = conn.execute(
        attempts.update()
        .where(
            attempts.c.protected_submit_attempt_id
            == protected_submit_attempt_id,
            attempts.c.ticket_id == ticket_id,
            attempts.c.entry_effect_state == "accepted_filled",
            attempts.c.protection_barrier_generation == generation,
            attempts.c.protection_barrier_state == barrier,
        )
        .values(protection_barrier_state="closed", updated_at_ms=now_ms)
        .returning(attempts.c.protected_submit_attempt_id)
    ).scalar_one_or_none()
    if updated is None:
        return _blocked("ticket_budget_effect_terminalization_cas_failed")
    return {"status": "ready", "runtime_attempt_mutated": True, "blockers": []}


def _terminal_release_proof_blocker(
    conn: sa.engine.Connection,
    *,
    ticket_id: str,
    reservation: dict[str, Any],
) -> str | None:
    """Prove terminal release from durable rows, never a caller-provided ID."""

    required_tables = {
        "brc_action_time_tickets",
        "brc_ticket_bound_order_lifecycle_runs",
        "brc_ticket_bound_reconciliation_ticks",
        "brc_ticket_bound_exit_protection_orders",
        "brc_ticket_bound_protected_submit_attempts",
        "brc_ticket_bound_exchange_commands",
        "brc_runtime_incidents",
        "brc_ticket_bound_scope_freezes",
    }
    if not required_tables <= set(sa.inspect(conn).get_table_names()):
        return "ticket_budget_terminal_release_proof_missing"
    tickets = _table(conn, "brc_action_time_tickets")
    ticket = conn.execute(
        sa.select(tickets).where(tickets.c.ticket_id == ticket_id).limit(2)
    ).mappings().one_or_none()
    if ticket is None or str(ticket.get("budget_reservation_id") or "") != str(
        reservation.get("budget_reservation_id") or ""
    ):
        return "ticket_budget_reservation_lineage_mismatch"
    for column_name in ("exposure_episode_id", "capacity_claim_hash"):
        if column_name in tickets.c and column_name in reservation:
            if str(ticket.get(column_name) or "") != str(
                reservation.get(column_name) or ""
            ):
                return "ticket_budget_reservation_lineage_mismatch"
    lifecycle = _table(conn, "brc_ticket_bound_order_lifecycle_runs")
    lifecycle_row = conn.execute(
        sa.select(lifecycle)
        .where(lifecycle.c.ticket_id == ticket_id)
        .where(lifecycle.c.status.in_(("reconciliation_matched", "budget_settled", "review_recorded", "lifecycle_closed")))
        .limit(2)
    ).mappings().one_or_none()
    if lifecycle_row is None:
        return "ticket_budget_terminal_lifecycle_not_matched"
    ticks = _table(conn, "brc_ticket_bound_reconciliation_ticks")
    flat_tick = conn.execute(
        sa.select(ticks.c.ticket_id)
        .where(ticks.c.ticket_id == ticket_id)
        .where(ticks.c.position_state == "flat")
        .where(ticks.c.status == "matched")
        .limit(1)
    ).first()
    if flat_tick is None:
        return "ticket_budget_terminal_flat_reconciliation_missing"
    protections = _table(conn, "brc_ticket_bound_exit_protection_orders")
    live_protection = conn.execute(
        sa.select(protections.c.ticket_id)
        .where(protections.c.ticket_id == ticket_id)
        .where(
            protections.c.status.in_(
                ("planned", "submitted", "open", "partially_filled", "cancel_pending", "replace_pending")
            )
        )
        .limit(1)
    ).first()
    if live_protection is not None:
        return "ticket_budget_terminal_residual_protection_live"
    capacity_blocker = _typed_capacity_release_blocker(
        conn,
        ticket_id=ticket_id,
    )
    if capacity_blocker:
        return capacity_blocker
    return None


def _typed_capacity_release_blocker(
    conn: sa.engine.Connection,
    *,
    ticket_id: str,
    ignore_effect_active_attempt: bool = False,
) -> str | None:
    """Reject release while any exact typed exchange effect remains unresolved."""

    attempts = _table(conn, "brc_ticket_bound_protected_submit_attempts")
    attempt_rows = list(
        conn.execute(
            sa.select(attempts)
            .where(attempts.c.ticket_id == ticket_id)
            .order_by(attempts.c.created_at_ms.desc())
            .limit(2)
        ).mappings()
    )
    if len(attempt_rows) != 1:
        return "ticket_budget_protected_submit_attempt_cardinality_invalid"
    attempt = dict(attempt_rows[0])
    if (
        not ignore_effect_active_attempt
        and
        str(attempt.get("entry_effect_state") or "") == "accepted_filled"
        and str(attempt.get("protection_barrier_state") or "") != "closed"
    ):
        return "ticket_budget_effect_active_attempt"

    commands = _table(conn, "brc_ticket_bound_exchange_commands")
    command_rows = list(
        conn.execute(
            sa.select(commands)
            .where(commands.c.ticket_id == ticket_id)
            .order_by(commands.c.order_role, commands.c.command_generation)
        ).mappings()
    )
    entry_rows = [row for row in command_rows if str(row.get("order_role")) == "ENTRY"]
    if len(entry_rows) != 1:
        return "ticket_budget_entry_command_cardinality_invalid"
    entry = dict(entry_rows[0])
    if (
        str(entry.get("protected_submit_attempt_id") or "")
        != str(attempt.get("protected_submit_attempt_id") or "")
        or str(entry.get("source_command_id") or "")
        != str(attempt.get("protected_submit_attempt_id") or "")
        or str(entry.get("ticket_id") or "") != ticket_id
        or str(entry.get("command_source") or "") != "protected_submit"
    ):
        return "ticket_budget_entry_command_lineage_invalid:source_attempt"
    tickets = _table(conn, "brc_action_time_tickets")
    ticket = conn.execute(
        sa.select(tickets).where(tickets.c.ticket_id == ticket_id).limit(1)
    ).mappings().one()
    if str(entry.get("exposure_episode_id") or "") != str(
        ticket.get("exposure_episode_id") or ""
    ):
        return "ticket_budget_entry_command_lineage_invalid:exposure_episode_id"
    submit_request = _mapping(attempt.get("submit_request"))
    if (
        str(submit_request.get("account_id") or "")
        != str(entry.get("account_id") or "")
        or str(submit_request.get("exchange_instrument_id") or "")
        != str(entry.get("exchange_instrument_id") or "")
    ):
        return "ticket_budget_entry_command_lineage_invalid:attempt_scope"
    expected_netting_domain_key = build_netting_domain_key(
        account_id=str(entry.get("account_id") or ""),
        exchange_instrument_id=str(entry.get("exchange_instrument_id") or ""),
        position_mode=str(entry.get("position_mode") or ""),
        position_bucket=str(entry.get("position_bucket") or ""),
    )
    if str(entry.get("netting_domain_key") or "") != expected_netting_domain_key:
        return "ticket_budget_entry_command_lineage_invalid:netting_domain_key"
    entry_state = str(entry.get("command_state") or "")
    if entry_state not in TERMINAL_EXCHANGE_COMMAND_STATES:
        return "ticket_budget_entry_command_unresolved"
    if not exchange_command_effect_is_terminal(
        command_state=entry_state,
        exchange_order_status=entry.get("exchange_order_status"),
        result_facts_complete=entry.get("result_facts_complete") in {True, 1},
    ):
        return "ticket_budget_entry_command_unresolved"

    incidents = _table(conn, "brc_runtime_incidents")
    incident_id = protection_barrier_incident_id(
        ticket_id=ticket_id,
        exposure_episode_id=str(entry.get("exposure_episode_id") or ""),
        protection_barrier_generation=int(
            attempt.get("protection_barrier_generation") or 1
        ),
    )
    active_incident = conn.execute(
        sa.select(incidents.c.incident_id)
        .where(
            incidents.c.incident_id == incident_id,
            incidents.c.incident_type == INITIAL_STOP_INCIDENT_TYPE,
            incidents.c.status.in_(("open", "investigating", "recovering")),
        )
        .limit(1)
    ).first()
    if active_incident is not None:
        return "ticket_budget_protection_incident_active"

    holds = _table(conn, "brc_ticket_bound_scope_freezes")
    active_hold = conn.execute(
        sa.select(holds.c.scope_freeze_id)
        .where(
            holds.c.source_ticket_id == ticket_id,
            holds.c.source_kind == "protection_barrier",
            holds.c.status == "active",
        )
        .limit(1)
    ).first()
    if active_hold is not None:
        return "ticket_budget_protection_barrier_hold_active"

    if any(
        str(command.get("command_state") or "")
        not in TERMINAL_EXCHANGE_COMMAND_STATES
        for command in command_rows
    ):
        return "ticket_budget_exchange_command_not_terminal"
    if any(
        not exchange_command_effect_is_terminal(
            command_state=str(command.get("command_state") or ""),
            exchange_order_status=command.get("exchange_order_status"),
            result_facts_complete=command.get("result_facts_complete")
            in {True, 1},
        )
        for command in command_rows
    ):
        return "ticket_budget_exchange_command_effect_not_terminal"
    return None


def _table(conn: sa.engine.Connection, table_name: str) -> sa.Table:
    return sa.Table(table_name, sa.MetaData(), autoload_with=conn)


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        parsed = json.loads(value)
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}
