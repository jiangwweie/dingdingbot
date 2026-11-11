from decimal import Decimal

import pytest
import sqlalchemy as sa

from src.trading_kernel.application.owner_control import (
    ControlMutationRequest,
    _authorization,
)
from src.trading_kernel.application.reconcile_ticket import (
    ReconcileTicketRequest,
    reconcile_ticket,
)
from src.trading_kernel.application.review_enrichment import (
    apply_review_enrichment,
    prepare_review_enrichment,
)
from src.trading_kernel.application.settle_ticket import (
    RecordTradeReviewRequest,
    SettleTicketRequest,
    record_trade_review,
    settle_ticket,
)
from src.trading_kernel.domain.events import ManualTakeoverConfirmed
from src.trading_kernel.domain.fee_valuation import (
    FeeValuationEvidence,
    NativeFee,
    value_native_fee,
)
from src.trading_kernel.domain.order_attribution import ExternalExitOrderReference
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.domain.reducer import reduce_event
from src.trading_kernel.domain.review import ReviewEconomicsFacts, ReviewFill
from src.trading_kernel.domain.trade_management import OrderEvidence
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.support.lifecycle import (
    reach_position_protected,
    registered_sor_long_ticket,
)
from tests.trading_kernel.support.manual_management import app_order


def fee():
    return value_native_fee(native_fee=NativeFee(asset='USDT',amount=Decimal('.1')),
        valuation_evidence=FeeValuationEvidence(method='native_usdt',rate_usdt_per_asset=Decimal(1),
            price_pair=None,observed_at_ms=None,valued_at_ms=9000))


class Source:
    def __init__(self, ticket, failing=False):
        self.ticket=ticket;self.failing=failing

    async def read_review_economics(self, request):
        if self.failing:raise TimeoutError('readonly unavailable')
        external=next(r for r in request.exit_order_references if isinstance(r,ExternalExitOrderReference))
        return ReviewEconomicsFacts(ticket_id=request.ticket_id,
            entry_fills=(ReviewFill(exchange_trade_id='entry-trade',exchange_order_id=request.entry_order_reference.submitted_exchange_order_id,
                command_id=request.entry_order_reference.command_id,role='entry',quantity=self.ticket.quantity,
                price=self.ticket.entry_reference_price,fee=fee(),realized_pnl_quote=Decimal(0),occurred_at_ms=2000),),
            exit_fills=(ReviewFill(exchange_trade_id='app-trade',exchange_order_id=external.submitted_exchange_order_id,
                command_id=None,external_evidence_id=external.evidence_id,role='exit',quantity=self.ticket.quantity,
                price=self.ticket.entry_reference_price+100,fee=fee(),realized_pnl_quote=Decimal(1),occurred_at_ms=6000),),
            funding_quote=Decimal(0),funding_unavailable_reason=None,observed_at_ms=request.observed_at_ms)


async def terminal(engine):
    t=registered_sor_long_ticket();await reach_position_protected(engine,t)
    async with PostgresKernelUnitOfWork(engine) as u:
        a=await u.aggregates.get_for_update(t.identity.ticket_id)
        event=ManualTakeoverConfirmed(event_id='take',ticket_id=t.identity.ticket_id,sequence=a.last_event_sequence+1,
            occurred_at_ms=5000,evidence_id='app',reason='external_exit')
        await u.commit_reduction(event=event,reduction=reduce_event(a,event),expected_version=a.version)
        proof=OrderEvidence(evidence_id='app-exit',terms=app_order(t,exchange_order_id='manual-order',order_type='MARKET',quantity=t.quantity,
            price=None,trigger_price=None),action='trade',created_at_ms=5500,exchange_event_at_ms=6000,received_at_ms=6001,
            executed_quantity=t.quantity,coverage_complete=True,known_command_outcome_pending=False)
        await u.management.save_evidence(t.identity.ticket_id,proof)
        await reconcile_ticket(u,ReconcileTicketRequest(ticket_id=t.identity.ticket_id,snapshot=PositionSnapshot(
            netting_domain=t.identity.netting_domain,quantity=Decimal(0),average_entry_price=None,open_orders=(),observed_at_ms=7000)))
        await settle_ticket(u,SettleTicketRequest(ticket_id=t.identity.ticket_id,settled_at_ms=7500))
        await record_trade_review(u,RecordTradeReviewRequest(ticket_id=t.identity.ticket_id,review_id='old-review',outcome='terminal_flat',
            metrics={'economics_completeness':'external_exit_unavailable'},decision_impact={'status':'missing'},recorded_at_ms=8000))
    return t


@pytest.mark.asyncio
async def test_preview_does_not_mutate_economics_then_exact_owner_approval_appends_once(head_template_engine):
    e=head_template_engine;t=await terminal(e)
    async with e.connect() as c:
        before={name:(await c.execute(sa.text(f'SELECT * FROM {name}'))).mappings().all()
            for name in ['brc_budget_reservations','brc_account_exposure_current','brc_exchange_commands']}
        request=(await c.execute(sa.text('SELECT * FROM brc_review_enrichment_requests'))).mappings().one()
    assert await prepare_review_enrichment(lambda:PostgresKernelUnitOfWork(e),Source(t),now_ms=9000)
    async with PostgresKernelUnitOfWork(e) as u:
        old=await u.reviews.get_for_ticket(t.identity.ticket_id)
        assert old.review_id=='old-review' and old.metrics['economics_completeness']=='external_exit_unavailable'
        record=await u.reviews.get_enrichment(request['request_id'])
        row=record.model_dump(mode='json')
        assert row['state']=='preview_ready'
        assert row['preview']['entry_quantity']==row['preview']['exit_quantity']==str(t.quantity)
    with pytest.raises(ValueError,match='Owner'):
        async with PostgresKernelUnitOfWork(e) as u:
            await apply_review_enrichment(u,request_id=request['request_id'],approved_preview_digest=row['preview_digest'],
                owner_authorization_id='fabricated',now_ms=10000)
    async with PostgresKernelUnitOfWork(e) as u:
        authorization=_authorization(purpose='review_revise',authentication_strength='totp_step_up',
            request=ControlMutationRequest(expected_version=1,reason='reviewed difference',idempotency_key='owner-review',owner_identity='owner',now_ms=10000),
            target_scope={'request_id':request['request_id'],'preview_digest':row['preview_digest'],
                'account_id':t.identity.netting_domain.account_id,'product_id':'brc-app-manual-v1'})
        await u.owner_controls.add_authorization(authorization)
    for now in [10001,10002]:
        async with PostgresKernelUnitOfWork(e) as u:
            await apply_review_enrichment(u,request_id=request['request_id'],approved_preview_digest=row['preview_digest'],
                owner_authorization_id=authorization.authorization_id,now_ms=now)
    async with e.connect() as c:
        assert await c.scalar(sa.text('SELECT count(*) FROM brc_trade_reviews'))==2
        assert await c.scalar(sa.text("SELECT count(*) FROM brc_trade_events WHERE event_type='ReviewRevised'"))==1
        assert before=={name:(await c.execute(sa.text(f'SELECT * FROM {name}'))).mappings().all() for name in before}
    async with PostgresKernelUnitOfWork(e) as u:
        current=await u.reviews.get_for_ticket(t.identity.ticket_id)
        assert current.revision==2 and current.supersedes_review_id=='old-review'
        assert current.metrics['economics_completeness']=='complete'
        assert (await u.aggregates.get(t.identity.ticket_id)).management_mode.value=='MANUAL'


@pytest.mark.asyncio
async def test_missing_readonly_evidence_stays_pending_without_reopening_terminal(head_template_engine):
    e=head_template_engine;t=await terminal(e)
    assert await prepare_review_enrichment(lambda:PostgresKernelUnitOfWork(e),Source(t,True),now_ms=9000)
    async with e.connect() as c:
        row=(await c.execute(sa.text('SELECT * FROM brc_review_enrichment_requests'))).mappings().one()
        assert row['state']=='pending' and row['last_reason']=='TimeoutError'
        assert await c.scalar(sa.text('SELECT count(*) FROM brc_trade_reviews'))==1


@pytest.mark.asyncio
async def test_approved_queue_is_consumed_by_existing_worker_with_owner_control_role(head_template_engine):
    from sqlalchemy.ext.asyncio import create_async_engine

    from tests.trading_kernel.support.owner_roles import apply_owner_control_grants
    e=head_template_engine;t=await terminal(e)
    await prepare_review_enrichment(lambda:PostgresKernelUnitOfWork(e),Source(t),now_ms=9000)
    await apply_owner_control_grants(e)
    control=create_async_engine(e.url)
    import sqlalchemy as sa
    from sqlalchemy import event
    @event.listens_for(control.sync_engine,'connect')
    def set_role(connection, _):
        cursor=connection.cursor();cursor.execute('SET ROLE brc_owner_control');cursor.close()
    try:
        async with control.connect() as c:
            request=(await c.execute(sa.text('SELECT * FROM brc_review_enrichment_requests'))).mappings().one()
        async with PostgresKernelUnitOfWork(control) as u:
            auth=_authorization(purpose='review_revise',authentication_strength='totp_step_up',
                request=ControlMutationRequest(expected_version=1,reason='approve exact preview',idempotency_key='real-role-review',owner_identity='owner',now_ms=10000),
                target_scope={'request_id':request['request_id'],'preview_digest':request['preview_digest'],
                    'account_id':t.identity.netting_domain.account_id,'product_id':'brc-app-manual-v1'})
            await u.owner_controls.add_authorization(auth)
            await u.reviews.approve_enrichment(request['request_id'],digest=request['preview_digest'],authorization_id=auth.authorization_id,now_ms=10000)
        async with PostgresKernelUnitOfWork(e) as u:
            assert (await u.reviews.get_for_ticket(t.identity.ticket_id)).review_id=='old-review'
        assert await prepare_review_enrichment(lambda:PostgresKernelUnitOfWork(e),Source(t),now_ms=10001)
        async with PostgresKernelUnitOfWork(e) as u:
            assert (await u.reviews.get_for_ticket(t.identity.ticket_id)).revision==2
    finally:
        await control.dispose()


@pytest.mark.asyncio
async def test_review_http_requires_real_step_up_and_does_not_apply_in_owner_api(head_template_engine):
    import pyotp
    from argon2 import PasswordHasher
    from httpx import ASGITransport, AsyncClient

    from src.trading_kernel.interfaces.owner_console_http.app import (
        OwnerConsoleSettings,
        create_owner_console_app,
    )
    from src.trading_kernel.interfaces.owner_console_http.auth import OwnerAuthSettings
    e=head_template_engine;t=await terminal(e)
    await prepare_review_enrichment(lambda:PostgresKernelUnitOfWork(e),Source(t),now_ms=9000)
    async with e.connect() as c:
        row=(await c.execute(sa.text('SELECT * FROM brc_review_enrichment_requests'))).mappings().one()
    seed='JBSWY3DPEHPK3PXP';now=1_800_000_000_000
    settings=OwnerConsoleSettings(database_dsn='postgresql+asyncpg://unused',control_database_dsn='postgresql+asyncpg://unused',
        account_id=t.identity.netting_domain.account_id,public_origin='https://owner.example.test',public_host='owner.example.test',
        auth=OwnerAuthSettings(username='owner',password_hash=PasswordHasher(time_cost=3,memory_cost=65536,parallelism=1).hash('test-password'),
            totp_seed=seed,session_signing_key='test-signing-key-with-enough-random-looking-material'))
    class Market:
        async def close(self):pass
    from src.trading_kernel.infrastructure.pg_owner_read_repository import (
        create_owner_read_engine,
    )
    read_engine=create_owner_read_engine(e.url.render_as_string(hide_password=False))
    app=create_owner_console_app(settings,engine=read_engine,control_engine=e,market_data=Market(),clock_ms=lambda:now)
    headers={'origin':'https://owner.example.test','host':'owner.example.test'}
    async with app.router.lifespan_context(app), AsyncClient(transport=ASGITransport(app=app),base_url='https://owner.example.test') as client:
        login=await client.post('/api/owner/v1/auth/login',json={'username':'owner','password':'test-password','totp_code':pyotp.TOTP(seed).at(now//1000)})
        assert login.status_code==204,login.text
        preview=await client.get('/api/owner/v1/controls/review-enrichment/requests/'+row['request_id'])
        assert preview.status_code==200 and preview.json()['preview_digest']==row['preview_digest']
        body={'request_id':row['request_id'],'approved_preview_digest':row['preview_digest'],
            'expected_version':1,'reason':'reviewed exact evidence','idempotency_key':'http-enrichment'}
        missing=await client.post('/api/owner/v1/controls/review-enrichment/apply',json=body,headers=headers)
        assert missing.status_code==403
        for _ in range(2):
            now += 30_000
            approved=await client.post('/api/owner/v1/controls/review-enrichment/apply',json={**body,'totp_code':pyotp.TOTP(seed).at(now//1000)},headers=headers)
            assert approved.status_code==200,approved.text
        async with PostgresKernelUnitOfWork(e) as u:
            assert (await u.reviews.get_for_ticket(t.identity.ticket_id)).revision==1
            assert (await u.reviews.get_enrichment(row['request_id'])).state=='approved'
        assert await prepare_review_enrichment(lambda:PostgresKernelUnitOfWork(e),Source(t),now_ms=now+1)
        async with PostgresKernelUnitOfWork(e) as u:
            assert (await u.reviews.get_for_ticket(t.identity.ticket_id)).revision==2
