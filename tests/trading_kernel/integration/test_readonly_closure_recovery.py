from decimal import Decimal

import pytest

from src.trading_kernel.application.readonly_closure_recovery import (
    recover_readonly_closure,
)
from src.trading_kernel.domain.events import ManagementReviewRequired
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.domain.readonly_closure import (
    ClosureFill,
    ReadonlyClosureProof,
    TerminalOrder,
)
from src.trading_kernel.domain.reducer import reduce_event
from src.trading_kernel.domain.trade_management import OrderAction, OrderEvidence
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.support.lifecycle import (
    reach_position_protected,
    registered_sor_long_ticket,
)
from tests.trading_kernel.support.manual_management import app_order


async def prepare(engine):
    t=registered_sor_long_ticket()
    await reach_position_protected(engine,t)
    async with PostgresKernelUnitOfWork(engine) as u:
        a=await u.aggregates.get_for_update(t.identity.ticket_id)
        ev=ManagementReviewRequired(event_id='gap',ticket_id=t.identity.ticket_id,
            sequence=a.last_event_sequence+1,occurred_at_ms=5000,evidence_id='gap',reason='collector_gap')
        await u.commit_reduction(event=ev,reduction=reduce_event(a,ev),expected_version=a.version)
        rows=await u.management.command_rows(t.identity.ticket_id)
        entry=next(r for r in rows if r['command_kind']=='entry')
        orders=tuple(TerminalOrder(namespace='conditional' if r['command_kind']=='initial_stop' else 'regular',
            order_id=r['result_payload']['exchange_order_id'],status='FILLED' if r['command_kind']=='entry' else 'CANCELED',
            executed_quantity=t.quantity if r['command_kind']=='entry' else Decimal(0)) for r in rows)
    proof=ReadonlyClosureProof(ticket_id=t.identity.ticket_id,domain=t.identity.netting_domain,
        entry_order_id=entry['result_payload']['exchange_order_id'],exit_order_id='app-full-close',
        exit_evidence=OrderEvidence(evidence_id='external-fill',terms=app_order(t,exchange_order_id='app-full-close',order_type='MARKET',price=None,quantity=t.quantity),
            action=OrderAction.TRADE,exchange_event_at_ms=6000,received_at_ms=7000,created_at_ms=6000,executed_quantity=t.quantity,coverage_complete=True,known_command_outcome_pending=False),
        entry_fills=(ClosureFill(trade_id='entry-fill',order_id=entry['result_payload']['exchange_order_id'],
            quantity=t.quantity,price=Decimal(60000),occurred_at_ms=2000),),
        exit_fills=(ClosureFill(trade_id='exit-fill',order_id='app-full-close',quantity=t.quantity,
            price=Decimal(61000),occurred_at_ms=6000),),
        terminal_orders=(*orders,TerminalOrder(namespace='regular',order_id='app-full-close',status='FILLED',executed_quantity=t.quantity)),
        snapshot=PositionSnapshot(netting_domain=t.identity.netting_domain,quantity=Decimal(0),
            average_entry_price=None,open_orders=(),orders_complete=True,observed_at_ms=7000),
        observed_at_ms=7000,valid_until_ms=37000)
    return t,rows,proof


@pytest.mark.asyncio
async def test_proven_external_close_recovers_review_and_releases_once(head_template_engine):
    e=head_template_engine;t,commands,proof=await prepare(e)
    for _ in range(2):
        async with PostgresKernelUnitOfWork(e) as u:
            result=await recover_readonly_closure(u,proof=proof,now_ms=8000)
            assert result=='terminal'
    async with PostgresKernelUnitOfWork(e) as u:
        a=await u.aggregates.get(t.identity.ticket_id)
        assert a.status.value=='terminal' and a.management_mode.value=='MANUAL'
        assert a.position_qty==0 and a.protected_qty==0
        assert not await u.entry_admission.has_active_ticket_in_domain(t.identity.netting_domain.key())
        assert await u.management.command_rows(t.identity.ticket_id)==commands
        review=await u.reviews.get(a.review_id)
        assert review.metrics['gross_realized_pnl_quote']=='1.000'
        assert review.metrics['net_pnl_quote'] is None
        assert review.metrics['unavailable_reason']=='fees_and_funding_not_yet_valued'


@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['expired','wrong_side','insufficient_fill','own_exit'])
async def test_incomplete_or_wrong_closure_proof_cannot_release(head_template_engine,fault):
    e=head_template_engine;t,_commands,proof=await prepare(e)
    if fault=='expired':proof=proof.model_copy(update={'valid_until_ms':7999})
    elif fault=='wrong_side':proof=proof.model_copy(update={'domain':proof.domain.model_copy(update={'position_side':'short'})})
    elif fault=='insufficient_fill':proof=proof.model_copy(update={'exit_fills':(proof.exit_fills[0].model_copy(update={'quantity':t.quantity/2}),)})
    else:proof=proof.model_copy(update={'exit_order_id':proof.entry_order_id})
    with pytest.raises(ValueError):
        async with PostgresKernelUnitOfWork(e) as u:
            await recover_readonly_closure(u,proof=proof,now_ms=8000)
    async with PostgresKernelUnitOfWork(e) as u:
        a=await u.aggregates.get(t.identity.ticket_id)
        assert a.management_mode.value=='REVIEW_REQUIRED' and a.position_qty==t.quantity
        assert await u.entry_admission.has_active_ticket_in_domain(t.identity.netting_domain.key())


@pytest.mark.asyncio
async def test_recovery_preview_rollback_leaves_events_and_budget_untouched(head_template_engine):
    e=head_template_engine;t,_rows,proof=await prepare(e)
    async with PostgresKernelUnitOfWork(e) as u:
        before=await u.aggregates.get(t.identity.ticket_id)
    class PreviewRollback(Exception):
        pass
    with pytest.raises(PreviewRollback):
        async with PostgresKernelUnitOfWork(e) as u:
            await recover_readonly_closure(u,proof=proof,now_ms=8000)
            raise PreviewRollback()
    async with PostgresKernelUnitOfWork(e) as u:
        after=await u.aggregates.get(t.identity.ticket_id)
        assert after==before
        assert await u.entry_admission.has_active_ticket_in_domain(t.identity.netting_domain.key())
