from decimal import Decimal as D

import pytest
import sqlalchemy as sa

from src.trading_kernel.application.advance_owner_position_operation import advance_owner_position_operation
from src.trading_kernel.application.owner_operation_facts import OwnerReductionObservation
from src.trading_kernel.domain.commands import ExchangeCommandKind as K
from src.trading_kernel.domain.owner_reduction import OwnerReductionState
from src.trading_kernel.infrastructure.pg_owner_position_operations import PostgresOwnerPositionOperations
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.pg_models import runtime_capabilities_current
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION
from tests.trading_kernel.support.owner_reduction import setup_operation, accept_signed_operation, facts


@pytest.mark.asyncio
async def test_runner_converts_protection_before_cancelling_tp_and_is_restartable(head_template_engine, monkeypatch):
    from unittest.mock import AsyncMock
    monkeypatch.setattr('src.trading_kernel.application.owner_operation_exit.read_original_operation_exit',AsyncMock(return_value=None))
    e = head_template_engine
    t, device, p, key = await setup_operation(e)
    async with e.begin() as c:
        r = PostgresOwnerPositionOperations(c)
        op = await r.create_preview(preview=p, owner_identity='Owner', device_id=device['device_id'], device_epoch=1,
            idempotency_key='reduce-preview', now_ms=6000)
        op, _ = await accept_signed_operation(c, device, key, op, now_ms=6001)
        await c.execute(sa.update(runtime_capabilities_current).where(runtime_capabilities_current.c.capability_key=='exchange_commands').values(certification={'product_id':'brc-app-manual-v1','owner_cooperation':'owner-cooperation-v1'}))
    class Source:
        calls = 0
        async def read_owner_reduction(self, *, aggregate, **kwargs):
            self.calls += 1
            return OwnerReductionObservation(facts=facts(aggregate, observed_at_ms=7000, valid_until_ms=10000,
                reduction_operation_id=op['operation_id']), protection_close_position=False)
    from src.trading_kernel.infrastructure.pg_signal_repository import PostgresSignalRepository
    monkeypatch.setattr(PostgresSignalRepository,'get_instrument_rules',AsyncMock(return_value=object()))
    source = Source()
    factory = lambda: PostgresKernelUnitOfWork(e)
    kwargs = dict(now_ms=7000, timeout_seconds=1, runtime_commit='kernel-test-head', schema_revision=CURRENT_SCHEMA_REVISION)
    assert await advance_owner_position_operation(factory, source, **kwargs) == 'protection_converting'
    async with factory() as u:
        cmds = await u.exchange_commands.list_for_ticket(t.identity.ticket_id)
        own = [c for c in cmds if c.payload.owner_operation_id == op['operation_id']]
        assert len(own) == 1 and own[0].kind is K.REPLACE_PROTECTION
        assert own[0].payload.close_position
        a = await u.aggregates.get(t.identity.ticket_id)
        assert a.protection_return_status.value == 'position_protected'
    assert await advance_owner_position_operation(factory, source, **(kwargs | {'now_ms': 8001})) == 'protection_converting'
    assert source.calls == 2


@pytest.mark.asyncio
async def test_real_command_chain_records_reduction_and_releases_operation(head_template_engine,monkeypatch):
    from unittest.mock import AsyncMock
    from src.trading_kernel.domain.owner_reduction_proof import OwnerReductionProof
    from src.trading_kernel.domain.exit_execution import EntryFill
    from tests.trading_kernel.support.command_dispatch import dispatch_for_ticket
    from tests.trading_kernel.support.dispatch_venues import KindAwareAcceptingVenue
    from src.trading_kernel.infrastructure.pg_signal_repository import PostgresSignalRepository
    monkeypatch.setattr('src.trading_kernel.application.owner_operation_exit.read_original_operation_exit',AsyncMock(return_value=None))
    monkeypatch.setattr(PostgresSignalRepository,'get_instrument_rules',AsyncMock(return_value=object()))
    e=head_template_engine
    t,device,p,key=await setup_operation(e)
    async with e.begin() as c:
        r=PostgresOwnerPositionOperations(c)
        op=await r.create_preview(preview=p,owner_identity='Owner',device_id=device['device_id'],device_epoch=1,
            idempotency_key='full-reduction',now_ms=6000)
        op,_=await accept_signed_operation(c,device,key,op,now_ms=6001)
        await c.execute(sa.update(runtime_capabilities_current).where(runtime_capabilities_current.c.capability_key=='exchange_commands').values(certification={'product_id':'brc-app-manual-v1','owner_cooperation':'owner-cooperation-v1'}))
    factory=lambda:PostgresKernelUnitOfWork(e)
    class Source:
        at=7000
        tp_cancelled=False
        executed=False
        async def read_owner_reduction(self,*,aggregate,state,commands,authorization_id,accepted_order_ids):
            a=aggregate
            values=dict(observed_at_ms=self.at,valid_until_ms=self.at+3000,reduction_operation_id=op['operation_id'])
            if self.tp_cancelled:values.update(tp_state='cancelled')
            proof=None
            if self.executed:
                command=next(c for c in commands if c.kind is K.OWNER_REDUCE)
                values.update(position_quantity=p.remaining_quantity,protected_quantity=p.remaining_quantity,
                    reduction_state='terminal',reduction_filled_quantity=p.reduction_quantity)
                proof=OwnerReductionProof(source_stage='pre_tp',source_tp_filled_quantity=0,
                    authorization_id=authorization_id,operation_id=state.operation_id,ticket_id=p.ticket_id,
                    domain=a.identity.netting_domain,command_id=command.command_id,
                    exchange_order_id=accepted_order_ids[command.command_id],venue_client_order_id=command.venue_client_order_id,
                    order_status='FILLED',requested_quantity=p.reduction_quantity,executed_quantity=p.reduction_quantity,
                    source_quantity=p.source_quantity,remaining_quantity=p.remaining_quantity,
                    fills=(EntryFill(trade_id='owner-fill',quantity=p.reduction_quantity,price=D(60000)),),
                    original_tp_order_id=p.cancel_tp_order_id,original_tp_cancelled=True,original_tp_filled_quantity=0,
                    protection_order_id=a.active_stop_exchange_order_id,protection_price=a.active_stop_price,
                    protected_quantity=p.remaining_quantity,observed_at_ms=self.at,valid_until_ms=self.at+3000)
            return OwnerReductionObservation(facts=facts(a,**values),protection_close_position=a.active_stop_close_position,proof=proof)
    source=Source()
    async def tick(at):
        source.at=at
        return await advance_owner_position_operation(factory,source,now_ms=at,timeout_seconds=1,
            runtime_commit='kernel-test-head',schema_revision=CURRENT_SCHEMA_REVISION)
    assert await tick(7000)=='protection_converting'
    await dispatch_for_ticket(e,KindAwareAcceptingVenue(observed_at_ms=7101),p.ticket_id,now_ms=7100)
    await dispatch_for_ticket(e,KindAwareAcceptingVenue(observed_at_ms=7201),p.ticket_id,now_ms=7200)
    assert await tick(8000)=='tp_cancelling'
    await dispatch_for_ticket(e,KindAwareAcceptingVenue(observed_at_ms=8101),p.ticket_id,now_ms=8100)
    source.tp_cancelled=True
    assert await tick(9000)=='reduction_pending'
    await dispatch_for_ticket(e,KindAwareAcceptingVenue(observed_at_ms=9101),p.ticket_id,now_ms=9100)
    source.executed=True
    assert await tick(10000)=='completed'
    async with factory() as u:
        a=await u.aggregates.get(p.ticket_id)
        assert a.position_qty==p.remaining_quantity and a.tp1_filled_qty==0
        assert a.management_mode.value=='AUTO' and a.tp1_exchange_order_id is None
        assert a.owner_reduction_context.original_tp_price==p.tp_trigger_price
        assert await u.owner_position_operations.active_for_ticket(p.ticket_id) is None
        assert len([c for c in await u.exchange_commands.list_for_ticket(p.ticket_id) if c.kind is K.OWNER_REDUCE])==1
    assert await tick(11000) is None
