from decimal import Decimal

import pytest

from src.trading_kernel.application.reconcile_ticket import (
    ReconcileTicketRequest,
    reconcile_ticket,
)
from src.trading_kernel.domain.events import ManualTakeoverConfirmed
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.domain.reducer import reduce_event
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.support.lifecycle import (
    reach_position_protected,
    registered_sor_long_ticket,
)


@pytest.mark.asyncio
async def test_manual_missing_stop_marks_account_blocker_in_current_projection(
    head_template_engine,
):
    e = head_template_engine
    t = registered_sor_long_ticket()
    await reach_position_protected(e, t)
    async with PostgresKernelUnitOfWork(e) as u:
        a = await u.aggregates.get(t.identity.ticket_id)
        ev = ManualTakeoverConfirmed(
            event_id="manual",
            ticket_id=t.identity.ticket_id,
            sequence=a.last_event_sequence + 1,
            occurred_at_ms=5000,
            evidence_id="external",
            reason="app",
        )
        await u.commit_reduction(
            event=ev, reduction=reduce_event(a, ev), expected_version=a.version
        )
        await reconcile_ticket(
            u,
            ReconcileTicketRequest(
                ticket_id=t.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=t.identity.netting_domain,
                    quantity=t.quantity,
                    average_entry_price=Decimal(60000),
                    observed_at_ms=6000,
                ),
            ),
        )
        a = await u.aggregates.get(t.identity.ticket_id)
        assert a.manual_risk_reason == "manual_stop_allocation_unproven"
        assert a.management_observed_at_ms == 6000
        assert a.manual_risk_at_stop is None


@pytest.mark.asyncio
async def test_changed_manual_protection_notifies_after_committed_reduction(head_template_engine, monkeypatch):
    import sqlalchemy as sa

    from src.trading_kernel.infrastructure.pg_models import notice_outbox
    e = head_template_engine
    t = registered_sor_long_ticket()
    await reach_position_protected(e, t)
    async with PostgresKernelUnitOfWork(e) as u:
        a = await u.aggregates.get(t.identity.ticket_id)
        ev = ManualTakeoverConfirmed(event_id="manual", ticket_id=t.identity.ticket_id,
            sequence=a.last_event_sequence+1, occurred_at_ms=5000,
            evidence_id="external", reason="app")
        await u.commit_reduction(event=ev, reduction=reduce_event(a, ev), expected_version=a.version)
    async with PostgresKernelUnitOfWork(e) as u:
        await reconcile_ticket(u, ReconcileTicketRequest(ticket_id=t.identity.ticket_id,
            snapshot=PositionSnapshot(netting_domain=t.identity.netting_domain,
                quantity=t.quantity, average_entry_price=Decimal(60000), observed_at_ms=6000)))
    async with e.connect() as c:
        assert await c.scalar(sa.select(sa.func.count()).select_from(notice_outbox).where(notice_outbox.c.kind=="risk")) == 1
