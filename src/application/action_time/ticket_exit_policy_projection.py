"""Single-writer compare-and-set operations for current Ticket exit policy state."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa


class TicketExitPolicyProjectionError(ValueError):
    """Raised when the current projection cannot be updated unambiguously."""


def claim_ticket_exit_market_watermark(
    conn: sa.engine.Connection,
    *,
    ticket_id: str,
    expected_previous_watermark_ms: int | None,
    watermark_ms: int,
    next_evaluation_not_before_ms: int,
    fact_snapshot_id: str,
    now_ms: int,
) -> dict[str, Any]:
    """Claim one strictly newer closed-market watermark using compare-and-set."""

    normalized_ticket_id = str(ticket_id or "").strip()
    if not normalized_ticket_id or watermark_ms <= 0:
        raise TicketExitPolicyProjectionError("exit_market_watermark_identity_invalid")
    if next_evaluation_not_before_ms <= watermark_ms or now_ms <= 0:
        raise TicketExitPolicyProjectionError("exit_market_watermark_cadence_invalid")
    if not str(fact_snapshot_id or "").strip():
        raise TicketExitPolicyProjectionError("exit_market_fact_snapshot_id_missing")
    table = _table(conn)
    current = conn.execute(
        sa.select(table).where(table.c.ticket_id == normalized_ticket_id)
    ).mappings().first()
    if current is None:
        raise TicketExitPolicyProjectionError("ticket_exit_policy_projection_missing")
    current_watermark = _optional_int(current.get("last_evaluated_watermark_ms"))
    if current_watermark is not None and current_watermark >= watermark_ms:
        return {
            "status": "watermark_already_claimed",
            "ticket_id": normalized_ticket_id,
            "watermark_ms": current_watermark,
        }
    if current_watermark != expected_previous_watermark_ms:
        return {
            "status": "watermark_claim_conflict",
            "ticket_id": normalized_ticket_id,
            "watermark_ms": current_watermark,
        }
    predicate = table.c.last_evaluated_watermark_ms.is_(None)
    if expected_previous_watermark_ms is not None:
        predicate = (
            table.c.last_evaluated_watermark_ms == expected_previous_watermark_ms
        )
    updated = conn.execute(
        table.update()
        .where(table.c.ticket_id == normalized_ticket_id, predicate)
        .values(
            last_evaluated_watermark_ms=watermark_ms,
            next_evaluation_not_before_ms=next_evaluation_not_before_ms,
            last_reason_code=str(fact_snapshot_id),
            first_blocker=None,
            updated_at_ms=now_ms,
        )
    )
    if updated.rowcount != 1:
        return {
            "status": "watermark_claim_conflict",
            "ticket_id": normalized_ticket_id,
            "watermark_ms": current_watermark,
        }
    return {
        "status": "watermark_claimed",
        "ticket_id": normalized_ticket_id,
        "watermark_ms": watermark_ms,
        "fact_snapshot_id": str(fact_snapshot_id),
    }


def record_ticket_exit_market_blocker(
    conn: sa.engine.Connection,
    *,
    ticket_id: str,
    blocker: str,
    retry_not_before_ms: int,
    now_ms: int,
) -> dict[str, Any]:
    """Record fact availability failure without changing protection or watermark."""

    normalized_ticket_id = str(ticket_id or "").strip()
    normalized_blocker = str(blocker or "").strip()
    if not normalized_ticket_id or not normalized_blocker:
        raise TicketExitPolicyProjectionError("exit_market_blocker_identity_invalid")
    if retry_not_before_ms <= now_ms or now_ms <= 0:
        raise TicketExitPolicyProjectionError("exit_market_blocker_retry_invalid")
    table = _table(conn)
    updated = conn.execute(
        table.update()
        .where(table.c.ticket_id == normalized_ticket_id)
        .values(
            first_blocker=normalized_blocker,
            next_evaluation_not_before_ms=retry_not_before_ms,
            updated_at_ms=now_ms,
        )
    )
    if updated.rowcount != 1:
        raise TicketExitPolicyProjectionError("ticket_exit_policy_projection_missing")
    return {
        "status": "exit_market_fact_blocked",
        "ticket_id": normalized_ticket_id,
        "blockers": [normalized_blocker],
    }


def _table(conn: sa.engine.Connection) -> sa.Table:
    if not sa.inspect(conn).has_table("brc_ticket_exit_policy_current"):
        raise TicketExitPolicyProjectionError("ticket_exit_policy_projection_missing")
    return sa.Table(
        "brc_ticket_exit_policy_current",
        sa.MetaData(),
        autoload_with=conn,
    )


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise TicketExitPolicyProjectionError(
            "exit_market_projection_watermark_invalid"
        ) from exc
