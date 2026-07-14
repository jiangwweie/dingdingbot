"""Projection helpers for ticket-bound capital-safety scope freezes."""

from __future__ import annotations

import time
from typing import Any

import sqlalchemy as sa


RESOLVED_NO_CURRENT_RISK_BLOCKER = "scope_cleanup_pending_no_current_risk"


def resolve_current_scope_freeze(
    conn: sa.engine.Connection,
    *,
    strategy_group_id: Any,
    symbol: Any,
    side: Any,
    source_kind: str,
    source_id: str,
    now_ms: int | None = None,
) -> int:
    """Resolve active freezes after current exchange truth disproves risk.

    This does not grant submit authority. It only prevents stale local freeze
    rows from blocking future valid opportunities after reconciliation or
    cleanup proves that no current capital risk remains for the exact scope.
    """

    now_ms = int(now_ms or time.time() * 1000)
    strategy_group_id = str(strategy_group_id or "").strip()
    symbol = str(symbol or "").strip()
    side = str(side or "").strip()
    if not strategy_group_id or not symbol or not side:
        return 0
    if not sa.inspect(conn).has_table("brc_ticket_bound_scope_freezes"):
        return 0

    table = sa.Table("brc_ticket_bound_scope_freezes", sa.MetaData(), autoload_with=conn)
    rows = list(
        conn.execute(
            sa.select(table)
            .where(table.c.strategy_group_id == strategy_group_id)
            .where(table.c.symbol == symbol)
            .where(table.c.side == side)
            .where(table.c.status == "active")
        ).mappings()
    )
    resolved_count = 0
    for row in rows:
        conn.execute(
            table.update()
            .where(table.c.scope_freeze_id == row["scope_freeze_id"])
            .values(
                status="resolved",
                source_kind=source_kind,
                source_id=source_id,
                first_blocker=RESOLVED_NO_CURRENT_RISK_BLOCKER,
                blockers=[RESOLVED_NO_CURRENT_RISK_BLOCKER],
                next_action="continue_new_trade_scope_if_other_gates_clear",
                updated_at_ms=now_ms,
            )
        )
        resolved_count += 1
    return resolved_count
