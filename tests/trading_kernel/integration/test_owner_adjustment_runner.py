import pytest
import sqlalchemy as sa
from decimal import Decimal as D

from src.trading_kernel.domain.owner_position_operation import preview_position_operation
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.pg_owner_position_operations import PostgresOwnerPositionOperations
from src.trading_kernel.infrastructure.pg_models import runtime_capabilities_current
from src.trading_kernel.application.advance_owner_adjustment import advance_owner_adjustment
from tests.trading_kernel.support.owner_reduction import setup_operation,accept_signed_operation,facts
from tests.trading_kernel.support.owner_operation_source import OwnerOperationSource,OwnerOperationVenue
from tests.trading_kernel.support.command_dispatch import dispatch_for_ticket


@pytest.mark.asyncio
@pytest.mark.parametrize('kind,params',[
    ('protection_tighten',{'price':D(59500)}),('manual_tp_set',{'price':D(63000),'quantity':D('.0002')}),('position_close',{})])
async def test_adjustment_runner_uses_real_commands_and_finishes_or_hands_off_closure(head_template_engine,kind,params):
    e=head_template_engine;t,b,_p,key=await setup_operation(e)
    factory=lambda:PostgresKernelUnitOfWork(e)
    async with factory() as u:
        a=await u.aggregates.get(t.identity.ticket_id)
        p=preview_position_operation(aggregate=a,facts=facts(a,observed_at_ms=6000,valid_until_ms=9000),kind=kind,
            quantity_step=D('.0001'),price_tick=D('.1'),minimum_quantity=D('.0001'),minimum_notional=D(1),now_ms=6000,**params)
    async with e.begin() as c:
        await c.execute(sa.update(runtime_capabilities_current).where(runtime_capabilities_current.c.capability_key=='exchange_commands').values(certification={'product_id':'brc-app-manual-v1','owner_cooperation':'owner-cooperation-v1'}))
        r=PostgresOwnerPositionOperations(c)
        op=await r.create_preview(preview=p,owner_identity='Owner',device_id=b['device_id'],device_epoch=1,idempotency_key='adjust',now_ms=6000)
        op,_=await accept_signed_operation(c,b,key,op,now_ms=6001)
    source=OwnerOperationSource();venue=OwnerOperationVenue()
    for at in range(7000,15000,1000):
        source.at=at
        async with factory() as u:op=await u.owner_position_operations.get(op['operation_id'])
        state=await advance_owner_adjustment(factory,source,op,now_ms=at,timeout_seconds=1)
        async with factory() as u:
            commands=await u.exchange_commands.list_for_ticket(t.identity.ticket_id)
            pending=[c for c in commands if c.status.value=='prepared']
        for _ in pending:
            await dispatch_for_ticket(e,venue,t.identity.ticket_id,now_ms=at+100)
        if state in {'completed','closure_pending'}:break
    async with factory() as u:
        a=await u.aggregates.get(t.identity.ticket_id)
        if kind=='position_close':
            assert a.status.value=='exit_accepted' and state=='closure_pending'
            assert await u.owner_position_operations.active_for_ticket(p.ticket_id) is not None
        else:
            assert state=='completed'
            assert a.status.value=='position_protected' and a.management_mode.value=='AUTO'
            assert await u.owner_position_operations.active_for_ticket(p.ticket_id) is None
            if kind=='protection_tighten':assert a.active_stop_price==D(59500) and a.tp1_exchange_order_id is not None
            else:assert a.manual_profit_plan.price==D(63000) and a.active_stop_close_position

    if kind=='manual_tp_set':
        async with factory() as u:
            a=await u.aggregates.get(p.ticket_id)
        for iteration,follow_kind in enumerate(['manual_tp_set','manual_tp_cancel']):
            start=16000+iteration*5000
            values={'price':D(64000),'quantity':D('.0001')} if follow_kind=='manual_tp_set' else {}
            preview=preview_position_operation(aggregate=a,facts=facts(a,observed_at_ms=start,valid_until_ms=start+3000),
                kind=follow_kind,quantity_step=D('.0001'),price_tick=D('.1'),minimum_quantity=D('.0001'),minimum_notional=D(1),now_ms=start,**values)
            async with e.begin() as c:
                r=PostgresOwnerPositionOperations(c)
                op=await r.create_preview(preview=preview,owner_identity='Owner',device_id=b['device_id'],device_epoch=1,
                    idempotency_key='follow-preview-'+str(iteration),now_ms=start)
                op,_=await accept_signed_operation(c,b,key,op,now_ms=start+1,idempotency_key='follow-submit-'+str(iteration))
            for at in range(start+1000,start+5000,1000):
                source.at=at
                async with factory() as u:op=await u.owner_position_operations.get(op['operation_id'])
                result=await advance_owner_adjustment(factory,source,op,now_ms=at,timeout_seconds=1)
                async with factory() as u:pending=[c for c in await u.exchange_commands.list_for_ticket(p.ticket_id) if c.status.value=='prepared']
                for _ in pending:await dispatch_for_ticket(e,venue,p.ticket_id,now_ms=at+100)
                if result=='completed':break
            async with factory() as u:
                a=await u.aggregates.get(p.ticket_id)
                assert result=='completed' and await u.owner_position_operations.active_for_ticket(p.ticket_id) is None
                if follow_kind=='manual_tp_cancel':
                    assert a.manual_profit_plan.cancelled and a.tp1_exchange_order_id is None
                else:assert a.manual_profit_plan.price==D(64000)
