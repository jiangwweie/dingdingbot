from __future__ import annotations

import pytest
import sqlalchemy as sa

from src.trading_kernel.domain.events import EntryAccepted, EntryRejected
from src.trading_kernel.domain.reducer import reduce_event
from src.trading_kernel.infrastructure.pg_models import notice_outbox, trade_aggregates
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.support.command_dispatch import issue, seed_policy, ticket


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["accepted", "rejected", "rolled_back"])
async def test_entry_acceptance_intermediate_state_does_not_notify_before_protection(
    head_template_engine,
    monkeypatch,
    outcome,
):
    engine = head_template_engine
    t = ticket()
    await seed_policy(engine)
    await issue(engine, t)
    try:
        async with PostgresKernelUnitOfWork(engine) as uow:
            aggregate = await uow.aggregates.get(t.identity.ticket_id)
            common = {
                "event_id": "event:entry-notice",
                "ticket_id": t.identity.ticket_id,
                "sequence": aggregate.last_event_sequence + 1,
                "occurred_at_ms": 2000,
            }
            event = (
                EntryRejected(**common, reason="venue_rejected")
                if outcome == "rejected"
                else EntryAccepted(**common, exchange_order_id="venue-entry-1")
            )
            await uow.commit_reduction(
                event=event,
                reduction=reduce_event(aggregate, event),
                expected_version=aggregate.version,
            )
            if outcome == "rolled_back":
                raise RuntimeError("rollback fixture")
    except RuntimeError:
        if outcome != "rolled_back":
            raise
    async with engine.connect() as c:
        assert (
            await c.scalar(sa.select(sa.func.count()).select_from(notice_outbox)) == 0
        )
        if outcome == "accepted":
            assert (
                await c.scalar(sa.select(trade_aggregates.c.status)) == "entry_accepted"
            )
