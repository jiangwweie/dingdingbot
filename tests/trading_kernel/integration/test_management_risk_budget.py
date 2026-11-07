from decimal import Decimal

import pytest

from src.trading_kernel.application.reconcile_ticket import (
    ReconcileTicketRequest,
    reconcile_ticket,
)
from src.trading_kernel.domain.events import ManualTakeoverConfirmed
from src.trading_kernel.domain.position import PositionSnapshot, VenueOrderSnapshot
from src.trading_kernel.domain.reducer import reduce_event
from src.trading_kernel.domain.trade_management import OrderTerms
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.support.lifecycle import (
    reach_position_protected,
    registered_sor_long_ticket,
)


@pytest.mark.asyncio
async def test_manual_risk_overlay_and_release_do_not_leave_budget_debt(
    head_template_engine,
):
    e = head_template_engine
    t = registered_sor_long_ticket()
    await reach_position_protected(e, t)
    d = t.identity.netting_domain
    async with PostgresKernelUnitOfWork(e) as u:
        a = await u.aggregates.get(t.identity.ticket_id)
        ev = ManualTakeoverConfirmed(
            event_id="take",
            ticket_id=t.identity.ticket_id,
            sequence=a.last_event_sequence + 1,
            occurred_at_ms=5000,
            evidence_id="app",
            reason="app",
        )
        await u.commit_reduction(
            event=ev, reduction=reduce_event(a, ev), expected_version=a.version
        )
        terms = OrderTerms(
            venue_id=d.venue_id,
            account_id=d.account_id,
            exchange_instrument_id=d.exchange_instrument_id,
            position_side="long",
            order_namespace="conditional",
            exchange_order_id="app-stop",
            client_order_id="app",
            side="sell",
            order_type="STOP_MARKET",
            quantity=t.quantity,
            price=None,
            trigger_price=Decimal(50000),
            close_position=False,
            reduce_only=False,
            time_in_force="GTC",
            working_type="CONTRACT_PRICE",
            price_protect=False,
            activation_price=None,
            callback_rate=None,
            price_match="NONE",
            self_trade_prevention_mode="NONE",
            good_till_date_ms=0,
        )
        order = VenueOrderSnapshot(
            exchange_order_id="app-stop",
            venue_client_order_id="app",
            position_side="long",
            reduce_only=False,
            terms=terms,
            remaining_quantity=t.quantity,
        )
        await reconcile_ticket(
            u,
            ReconcileTicketRequest(
                ticket_id=t.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=d,
                    quantity=t.quantity,
                    average_entry_price=Decimal(60000),
                    open_orders=(order,),
                    observed_at_ms=6000,
                ),
            ),
        )
        exposure = await u.entry_admission.get_account_exposure(
            d.venue_id, d.account_id
        )
        assert exposure.gross_risk_at_stop > t.risk_at_stop
        assert (
            await u.management.account_blocker(d.venue_id, d.account_id, 6000) is None
        )
    async with PostgresKernelUnitOfWork(e) as u:
        await reconcile_ticket(
            u,
            ReconcileTicketRequest(
                ticket_id=t.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=d,
                    quantity=Decimal(0),
                    average_entry_price=None,
                    observed_at_ms=7000,
                ),
            ),
        )
        exposure = await u.entry_admission.get_account_exposure(
            d.venue_id, d.account_id
        )
        assert exposure.gross_risk_at_stop == 0 and exposure.active_ticket_count == 0
