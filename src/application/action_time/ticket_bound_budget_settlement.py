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
        sa.select(table).where(table.c.ticket_id == ticket_id)
    ).mappings().first()
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
