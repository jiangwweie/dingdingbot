from __future__ import annotations

from unittest.mock import Mock

import pytest
import sqlalchemy as sa

from src.trading_kernel.domain.events import EntryAccepted, EntryRejected
from src.trading_kernel.domain.reducer import reduce_event
from src.trading_kernel.infrastructure import pg_unit_of_work as module
from src.trading_kernel.infrastructure.pg_models import trade_aggregates
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.support.command_dispatch import issue, seed_policy, ticket


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["accepted", "rejected", "rolled_back"])
async def test_notice_is_only_scheduled_after_committed_entry_acceptance(
    head_template_engine,
    monkeypatch,
    outcome,
):
    engine = head_template_engine
    t = ticket()
    await seed_policy(engine)
    await issue(engine, t)
    notify = Mock()
    monkeypatch.setattr(module, "notify_entry_accepted", notify)
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
            notify.assert_not_called()
            if outcome == "rolled_back":
                raise RuntimeError("rollback fixture")
    except RuntimeError:
        if outcome != "rolled_back":
            raise
    if outcome == "accepted":
        notify.assert_called_once()
        accepted_ticket, accepted_event = notify.call_args.args
        assert accepted_ticket.identity.ticket_id == t.identity.ticket_id
        assert accepted_event.exchange_order_id == "venue-entry-1"
        async with engine.connect() as c:
            assert (
                await c.scalar(sa.select(trade_aggregates.c.status)) == "entry_accepted"
            )
    else:
        notify.assert_not_called()
