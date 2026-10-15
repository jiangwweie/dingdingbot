"""Readonly Signal price-path evidence joined to exact real execution lineage."""
from __future__ import annotations

from decimal import Decimal

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncEngine

from src.trading_kernel.infrastructure.pg_models import (
    admission_decisions,
    shadow_outcomes_current,
    signal_events,
    trade_aggregates,
    trade_reviews,
    trade_tickets,
)


class SignalPathResearchView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    signal_event_id: str
    shadow_outcome_id: str
    strategy_group_id: str | None
    strategy_version_id: str | None
    event_spec_id: str | None
    reference_at_ms: int | None
    horizon_end_ms: int
    path_reference_price: Decimal | None
    path_initial_stop_price: Decimal | None
    path_status: str
    attempt_count: int
    next_attempt_at_ms: int | None
    retry_deadline_ms: int | None
    completion_reason: str | None
    evaluation_kind: str
    price_basis: str | None
    source_runtime_commit: str | None
    path_spec_digest: str | None
    path_initial_risk_per_unit: Decimal | None
    mfe_r: Decimal | None
    mae_r: Decimal | None
    path_metrics: dict[str, object] | None
    admission_status: str | None
    admission_blocker: str | None
    ticket_id: str | None
    ticket_initial_stop_price: Decimal | None
    ticket_entry_reference_price: Decimal | None
    ticket_frozen_stop_risk: Decimal | None
    review_id: str | None
    review_revision: int | None
    review_metrics: dict[str, object] | None


async def read_signal_path(engine: AsyncEngine, *, signal_event_id: str) -> SignalPathResearchView | None:
    """Exact-key current pointer reads; no simulated fill or historical scan."""
    if not signal_event_id.strip():
        raise ValueError("Signal identity must be nonblank")
    s=shadow_outcomes_current
    e=signal_events
    a=admission_decisions
    t=trade_tickets
    g=trade_aggregates
    r=trade_reviews
    statement=(sa.select(
        s.c.signal_event_id,s.c.shadow_outcome_id,s.c.attempt_count,s.c.next_attempt_at_ms,
        s.c.retry_deadline_ms,s.c.completion_reason,e.c.strategy_group_id,e.c.strategy_version_id,e.c.event_spec_id,
        s.c.reference_at_ms,s.c.horizon_end_ms,s.c.entry_reference_price.label("path_reference_price"),
        s.c.initial_stop_price.label("path_initial_stop_price"),s.c.status.label("path_status"),s.c.evaluation_kind,
        s.c.price_basis,s.c.source_runtime_commit,s.c.path_spec_digest,s.c.initial_risk_per_unit.label("path_initial_risk_per_unit"),
        s.c.mfe_r,s.c.mae_r,s.c.path_metrics,a.c.decision_status.label("admission_status"),
        a.c.first_blocker.label("admission_blocker"),t.c.ticket_id,
        t.c.initial_stop_price.label("ticket_initial_stop_price"),
        t.c.entry_reference_price.label("ticket_entry_reference_price"),
        t.c.risk_at_stop.label("ticket_frozen_stop_risk"),
        r.c.review_id,r.c.revision.label("review_revision"),r.c.metrics.label("review_metrics"))
        .select_from(s.outerjoin(e,e.c.signal_event_id==s.c.signal_event_id)
            .outerjoin(a,a.c.signal_event_id==s.c.signal_event_id)
            .outerjoin(t,sa.and_(t.c.ticket_id==a.c.ticket_id,t.c.signal_event_id==s.c.signal_event_id))
            .outerjoin(g,g.c.ticket_id==t.c.ticket_id)
            .outerjoin(r,sa.and_(r.c.review_id==g.c.review_id,r.c.ticket_id==t.c.ticket_id)))
        .where(s.c.signal_event_id==signal_event_id))
    async with engine.connect() as connection:
        await connection.execute(sa.text("SET TRANSACTION READ ONLY"))
        row=(await connection.execute(statement)).mappings().one_or_none()
        await connection.rollback()
    return None if row is None else SignalPathResearchView.model_validate(row)
