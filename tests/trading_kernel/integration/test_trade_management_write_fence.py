from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.trading_kernel.application.dispatch_exchange_command import (
    DispatchCommandRequest,
    dispatch_one_command,
)
from src.trading_kernel.domain.events import (
    ManagementReviewRequired,
    ManualTakeoverConfirmed,
    TakeProfitFilled,
)
from src.trading_kernel.domain.reducer import reduce_event
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.support.dispatch_venues import KindAwareAcceptingVenue
from tests.trading_kernel.support.lifecycle import (
    reach_position_protected,
    registered_sor_long_ticket,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("expired_claim", [False, True])
@pytest.mark.parametrize("review_only", [False, True])
async def test_prepared_runner_command_never_dispatched_after_takeover(head_template_engine, review_only, expired_claim):
    engine=head_template_engine;t=registered_sor_long_ticket()
    await reach_position_protected(engine,t)
    async with PostgresKernelUnitOfWork(engine) as uow:
        a=await uow.aggregates.get_for_update(t.identity.ticket_id)
        fill=TakeProfitFilled(event_id='tp1-real',ticket_id=t.identity.ticket_id,sequence=a.last_event_sequence+1,
            occurred_at_ms=5000,filled_qty=a.tp1_target_qty,average_fill_price=Decimal(62000),runner_floor_price=Decimal(60100))
        await uow.commit_reduction(event=fill,reduction=reduce_event(a,fill),expected_version=a.version)
    async with PostgresKernelUnitOfWork(engine) as uow:
        a=await uow.aggregates.get_for_update(t.identity.ticket_id)
        if expired_claim:
            claimed=await uow.exchange_commands.claim_one_prepared(worker_id='old-worker',now_ms=5100,lease_until_ms=5500,ticket_id=t.identity.ticket_id,command_kinds=())
            assert claimed is not None
        event_type=ManagementReviewRequired if review_only else ManualTakeoverConfirmed
        takeover=event_type(event_id='manual',ticket_id=t.identity.ticket_id,
            sequence=a.last_event_sequence+1,occurred_at_ms=6000,evidence_id='app-stop-change',reason='external_order_amendment')
        await uow.commit_reduction(event=takeover,reduction=reduce_event(a,takeover),expected_version=a.version)
    venue=KindAwareAcceptingVenue()
    venue.execute=AsyncMock(wraps=venue.execute)
    result=await dispatch_one_command(lambda:PostgresKernelUnitOfWork(engine),venue,
        DispatchCommandRequest(worker_id='test',now_ms=7000,lease_until_ms=8000,timeout_seconds=1,ticket_id=t.identity.ticket_id))
    assert result.status.value==('outcome_unknown' if expired_claim else 'no_command' if review_only else 'superseded')
    venue.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_management_outcome_event_has_no_runner_effects(head_template_engine):
    from src.trading_kernel.domain.events import ManagedCommandOutcomeObserved
    e=head_template_engine;t=registered_sor_long_ticket();await reach_position_protected(e,t)
    async with PostgresKernelUnitOfWork(e) as uow:
        a=await uow.aggregates.get_for_update(t.identity.ticket_id)
        take=ManualTakeoverConfirmed(event_id='take',ticket_id=t.identity.ticket_id,
            sequence=a.last_event_sequence+1,occurred_at_ms=6000,evidence_id='app',reason='external_order_amendment')
        r=reduce_event(a,take)
        await uow.commit_reduction(event=take,reduction=r,expected_version=a.version)
        a=r.aggregate
        event=ManagedCommandOutcomeObserved(event_id='known-result',ticket_id=t.identity.ticket_id,
            sequence=a.last_event_sequence+1,occurred_at_ms=7000,command_id='old-replace',outcome={'status':'accepted','exchange_order_id':'new-stop'})
        r=reduce_event(a,event)
        assert r.effects==() and r.aggregate.management_mode==a.management_mode
        assert r.aggregate.active_stop_exchange_order_id==a.active_stop_exchange_order_id


@pytest.mark.asyncio
async def test_feed_loss_defers_prepared_runner_without_unknown_or_venue_write(head_template_engine):
    import sqlalchemy as sa

    from src.trading_kernel.infrastructure.pg_models import runtime_capabilities_current
    e=head_template_engine;t=registered_sor_long_ticket();await reach_position_protected(e,t)
    async with PostgresKernelUnitOfWork(e) as u:
        a=await u.aggregates.get_for_update(t.identity.ticket_id)
        fill=TakeProfitFilled(event_id='tp1-real',ticket_id=t.identity.ticket_id,sequence=a.last_event_sequence+1,
            occurred_at_ms=5000,filled_qty=a.tp1_target_qty,average_fill_price=Decimal(62000),runner_floor_price=Decimal(60100))
        await u.commit_reduction(event=fill,reduction=reduce_event(a,fill),expected_version=a.version)
    async with e.begin() as c:
        await c.execute(sa.update(runtime_capabilities_current).values(certification={'product_id':'brc-app-manual-v1','management_feed_required':True}))
    venue=KindAwareAcceptingVenue();venue.execute=AsyncMock(wraps=venue.execute)
    result=await dispatch_one_command(lambda:PostgresKernelUnitOfWork(e),venue,
        DispatchCommandRequest(worker_id='test',now_ms=6000,lease_until_ms=8000,timeout_seconds=1,ticket_id=t.identity.ticket_id,
            runtime_commit='kernel-test-head'),clock_ms=lambda:6000)
    assert result.status.value=='deferred'
    venue.execute.assert_not_awaited()
    async with PostgresKernelUnitOfWork(e) as u:
        rows=await u.management.command_rows(t.identity.ticket_id)
        runner=next(r for r in rows if r['command_kind']=='replace_protection')
        assert runner['status']=='prepared' and runner['claim_owner'] is None and runner['lease_until_ms'] is None
