"""Independent idempotent Ticket budget settlement from terminal evidence."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from src.application.action_time.budget_reservation_transition import (
    transition_budget_reservation,
)


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
    return None


def _table(conn: sa.engine.Connection, table_name: str) -> sa.Table:
    return sa.Table(table_name, sa.MetaData(), autoload_with=conn)
