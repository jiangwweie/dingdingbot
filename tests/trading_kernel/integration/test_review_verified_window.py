"""Verified closure endpoint reaches persistent enrichment without editing old Review."""

from decimal import Decimal as D

import pytest
import sqlalchemy as sa

from src.trading_kernel.application.review_enrichment import prepare_review_enrichment
from src.trading_kernel.application.settle_ticket import (
    RecordTradeReviewRequest,
    SettleTicketRequest,
    record_trade_review,
    settle_ticket,
)
from src.trading_kernel.application.verified_exit_closure import record_verified_exit
from src.trading_kernel.domain.events import ExitRequested, PositionFlatConfirmed
from src.trading_kernel.domain.fee_valuation import (
    FeeValuationEvidence,
    NativeFee,
    value_native_fee,
)
from src.trading_kernel.domain.reducer import reduce_event
from src.trading_kernel.domain.review import ReviewEconomicsFacts, ReviewFill
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.support.verified_exit import protected_proof


@pytest.mark.asyncio
@pytest.mark.parametrize('early_flat', [False, True])
async def test_verified_economics_uses_real_exit_and_only_prepares_owner_preview(head_template_engine, early_flat):
    e = head_template_engine
    ticket, proof = await protected_proof(e, review=False)
    factory = lambda: PostgresKernelUnitOfWork(e)
    if early_flat:
        async with factory() as u:
            a = await u.aggregates.get_for_update(ticket.identity.ticket_id)
            for kind, at, extra in [(ExitRequested, 4500, {'reason': 'observed_exit'}),
                                    (PositionFlatConfirmed, 5000, {})]:
                event = kind(event_id='before-proof:' + str(at), ticket_id=ticket.identity.ticket_id,
                    sequence=a.last_event_sequence + 1, occurred_at_ms=at, **extra)
                result = reduce_event(a, event)
                await u.commit_reduction(event=event, reduction=result, expected_version=a.version)
                a = result.aggregate
            for command in await u.exchange_commands.list_for_ticket(ticket.identity.ticket_id):
                if command.status.value == 'prepared':
                    await u.exchange_commands.mark_prepared_superseded(command_id=command.command_id,
                        observed_at_ms=7000, reason='verified_unsent_in_disposable_test')
            proof = proof.model_copy(update={'expected_version': a.version})
    async with factory() as u:
        await record_verified_exit(u, proof=proof, now_ms=7001)
        await settle_ticket(u, SettleTicketRequest(ticket_id=ticket.identity.ticket_id, settled_at_ms=7500))
        await record_trade_review(u, RecordTradeReviewRequest(ticket_id=ticket.identity.ticket_id,
            review_id='original-review', outcome='initial_stop_triggered',
            metrics={'economics_completeness': 'external_exit_unavailable'},
            decision_impact={'status': 'missing'}, recorded_at_ms=8000))
    async with e.connect() as c:
        before = {name: (await c.execute(sa.text('SELECT * FROM ' + name))).mappings().all()
            for name in ['brc_budget_reservations', 'brc_account_exposure_current', 'brc_exchange_commands', 'brc_trade_reviews']}

    class Source:
        seen = None
        async def read_review_economics(self, request):
            self.seen = request
            assert request.exit_time_ms == proof.exit_time_ms == 6000
            fee = value_native_fee(native_fee=NativeFee(asset='USDT', amount=D('.01')),
                valuation_evidence=FeeValuationEvidence(method='native_usdt', rate_usdt_per_asset=D(1),
                    price_pair=None, observed_at_ms=None, valued_at_ms=9000))
            refs = {r.submitted_exchange_order_id: r for r in
                (request.entry_order_reference, *request.exit_order_references)}
            def fill(item, role):
                assert request.entry_time_ms <= item.occurred_at_ms <= request.exit_time_ms
                order = next(o for o in proof.orders if o.executable_id == item.order_id)
                ref = refs[order.reference.submitted_exchange_order_id]
                return ReviewFill(exchange_trade_id=item.trade_id, exchange_order_id=item.order_id,
                    command_id=ref.command_id, role=role, quantity=item.quantity, price=item.price,
                    fee=fee, realized_pnl_quote=D(0), occurred_at_ms=item.occurred_at_ms)
            return ReviewEconomicsFacts(ticket_id=request.ticket_id,
                entry_fills=tuple(fill(f, 'entry') for f in proof.entry_fills),
                exit_fills=tuple(fill(f, 'exit') for f in proof.exit_fills),
                funding_quote=D(0), funding_unavailable_reason=None, observed_at_ms=request.observed_at_ms)
    source = Source()
    assert await prepare_review_enrichment(factory, source, now_ms=9000)
    assert source.seen is not None
    async with e.connect() as c:
        row = (await c.execute(sa.text('SELECT * FROM brc_review_enrichment_requests'))).mappings().one()
        assert row['state'] == 'preview_ready', row['last_reason']
        for name, rows in before.items():
            assert rows == (await c.execute(sa.text('SELECT * FROM ' + name))).mappings().all()
