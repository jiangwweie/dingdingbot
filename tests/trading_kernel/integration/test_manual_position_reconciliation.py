from decimal import Decimal

import pytest

from src.trading_kernel.application.reconcile_ticket import (
    ExitTicketRequest,
    ReconcileTicketRequest,
    reconcile_ticket,
    request_exit,
)
from src.trading_kernel.application.settle_ticket import (
    RecordTradeReviewRequest,
    SettleTicketRequest,
    record_trade_review,
    settle_ticket,
)
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.events import ManualTakeoverConfirmed
from src.trading_kernel.domain.position import PositionSnapshot, VenueOrderSnapshot
from src.trading_kernel.domain.reducer import reduce_event
from src.trading_kernel.domain.trade_management import ManagementMode
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.support.lifecycle import (
    reach_position_protected,
    registered_sor_long_ticket,
)


async def manual(engine):
    t = registered_sor_long_ticket()
    await reach_position_protected(engine, t)
    async with PostgresKernelUnitOfWork(engine) as u:
        a = await u.aggregates.get_for_update(t.identity.ticket_id)
        ev = ManualTakeoverConfirmed(
            event_id="take",
            ticket_id=t.identity.ticket_id,
            sequence=a.last_event_sequence + 1,
            occurred_at_ms=5000,
            evidence_id="app",
            reason="external_order_amendment",
        )
        await u.commit_reduction(
            event=ev, reduction=reduce_event(a, ev), expected_version=a.version
        )
    return t


def snapshot(t, quantity, orders=()):
    return PositionSnapshot(
        netting_domain=t.identity.netting_domain,
        quantity=quantity,
        average_entry_price=Decimal(60000) if quantity else None,
        open_orders=orders,
        observed_at_ms=6000,
    )


@pytest.mark.asyncio
async def test_manual_partial_exit_updates_quantity_without_commands(
    head_template_engine,
):
    e = head_template_engine
    t = await manual(e)
    async with PostgresKernelUnitOfWork(e) as u:
        before = await u.exchange_commands.list_for_ticket(t.identity.ticket_id)
        await reconcile_ticket(
            u,
            ReconcileTicketRequest(
                ticket_id=t.identity.ticket_id, snapshot=snapshot(t, t.quantity / 2)
            ),
        )
        a = await u.aggregates.get(t.identity.ticket_id)
        assert (
            a.position_qty == t.quantity / 2
            and a.management_mode is ManagementMode.MANUAL
        )
        assert (
            a.protected_qty == 0
        )  # absent order facts must not claim original protection
        assert await u.exchange_commands.list_for_ticket(t.identity.ticket_id) == before


@pytest.mark.asyncio
async def test_manual_flat_residual_order_keeps_hold_then_settles_readonly(
    head_template_engine,
):
    e = head_template_engine
    t = await manual(e)
    order = VenueOrderSnapshot(
        exchange_order_id="app-stop",
        venue_client_order_id="app",
        position_side="long",
        reduce_only=False,
    )
    async with PostgresKernelUnitOfWork(e) as u:
        commands = await u.exchange_commands.list_for_ticket(t.identity.ticket_id)
        await reconcile_ticket(
            u,
            ReconcileTicketRequest(
                ticket_id=t.identity.ticket_id,
                snapshot=snapshot(t, Decimal(0), (order,)),
            ),
        )
        a = await u.aggregates.get(t.identity.ticket_id)
        assert a.status is AggregateStatus.MANUAL_FLAT_PENDING_ORDERS
        assert await u.entry_admission.has_active_ticket_in_domain(
            t.identity.netting_domain.key()
        )
        assert (
            await u.exchange_commands.list_for_ticket(t.identity.ticket_id) == commands
        )
    async with PostgresKernelUnitOfWork(e) as u:
        await reconcile_ticket(
            u,
            ReconcileTicketRequest(
                ticket_id=t.identity.ticket_id,
                snapshot=snapshot(t, Decimal(0)).model_copy(
                    update={"observed_at_ms": 7000}
                ),
            ),
        )
        a = await u.aggregates.get(t.identity.ticket_id)
        assert a.status is AggregateStatus.SETTLEMENT_PENDING
        await settle_ticket(
            u, SettleTicketRequest(ticket_id=t.identity.ticket_id, settled_at_ms=8000)
        )
        await record_trade_review(
            u,
            RecordTradeReviewRequest(
                ticket_id=t.identity.ticket_id,
                review_id="manual-review",
                outcome="closed",
                metrics={"exit_economics": "unavailable"},
                decision_impact={"source": "external"},
                recorded_at_ms=9000,
            ),
        )
        a = await u.aggregates.get(t.identity.ticket_id)
        assert (
            a.status is AggregateStatus.TERMINAL
            and a.management_mode is ManagementMode.MANUAL
        )
        assert not await u.entry_admission.has_active_ticket_in_domain(
            t.identity.netting_domain.key()
        )
        assert (
            await u.exchange_commands.list_for_ticket(t.identity.ticket_id) == commands
        )


@pytest.mark.asyncio
async def test_manual_exit_request_is_explicitly_skipped(head_template_engine):
    e = head_template_engine
    t = await manual(e)
    async with PostgresKernelUnitOfWork(e) as u:
        r = await request_exit(
            u,
            ExitTicketRequest(
                ticket_id=t.identity.ticket_id, requested_at_ms=6000, reason="flatten"
            ),
        )
        assert r.status.value == "manual_management_skipped"


@pytest.mark.asyncio
async def test_incomplete_order_page_never_releases_manual_flat_hold(head_template_engine):
 e=head_template_engine;t=await manual(e)
 async with PostgresKernelUnitOfWork(e) as u:
  snap=snapshot(t,Decimal(0)).model_copy(update={'orders_complete':False})
  await reconcile_ticket(u,ReconcileTicketRequest(ticket_id=t.identity.ticket_id,snapshot=snap))
  a=await u.aggregates.get(t.identity.ticket_id)
  assert a.status is not AggregateStatus.SETTLEMENT_PENDING
  assert await u.entry_admission.has_active_ticket_in_domain(t.identity.netting_domain.key())
  assert a.manual_risk_reason=='manual_order_facts_incomplete'
