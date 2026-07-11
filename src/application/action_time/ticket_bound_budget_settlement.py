"""Independent idempotent Ticket budget settlement from terminal evidence."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa


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
    conn.execute(
        table.update()
        .where(table.c.budget_reservation_id == row["budget_reservation_id"])
        .values(
            status="released",
            release_reason=f"lifecycle_closed:{settlement_evidence_id}",
        )
    )
    return {
        "status": "released",
        "budget_reservation_id": row["budget_reservation_id"],
        "settlement_evidence_id": settlement_evidence_id,
        "settled_at_ms": now_ms,
        "runtime_budget_mutated": True,
        "blockers": [],
    }


def _blocked(blocker: str) -> dict[str, Any]:
    return {
        "status": "blocked",
        "first_blocker": blocker,
        "blockers": [blocker],
        "runtime_budget_mutated": False,
    }
