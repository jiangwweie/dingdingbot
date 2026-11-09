from decimal import Decimal

import pytest
import sqlalchemy as sa

from src.trading_kernel.application.reconcile_ticket import (
    ReconcileTicketRequest,
    reconcile_ticket,
)
from src.trading_kernel.domain.events import ManualTakeoverConfirmed
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.domain.reducer import reduce_event
from src.trading_kernel.infrastructure.pg_models import notice_outbox
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.support.lifecycle import (
    reach_position_protected,
    registered_sor_long_ticket,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "quantity,rollback",
    [(Decimal(".0005"), False), (Decimal(0), False), (Decimal(".0005"), True)],
)
async def test_notice_uses_transaction_final_observed_position_and_rolls_back(
    head_template_engine, quantity, rollback
):
    e = head_template_engine
    t = registered_sor_long_ticket()
    await reach_position_protected(e, t)
    try:
        async with PostgresKernelUnitOfWork(e) as u:
            a = await u.aggregates.get(t.identity.ticket_id)
            event = ManualTakeoverConfirmed(
                event_id="takeover",
                ticket_id=t.identity.ticket_id,
                sequence=a.last_event_sequence + 1,
                occurred_at_ms=5000,
                evidence_id="external",
                reason="app",
            )
            await u.commit_reduction(
                event=event,
                reduction=reduce_event(a, event),
                expected_version=a.version,
            )
            await reconcile_ticket(
                u,
                ReconcileTicketRequest(
                    ticket_id=t.identity.ticket_id,
                    snapshot=PositionSnapshot(
                        netting_domain=t.identity.netting_domain,
                        quantity=quantity,
                        average_entry_price=Decimal(60000) if quantity else None,
                        observed_at_ms=6000,
                    ),
                ),
            )
            if rollback:
                raise RuntimeError("rollback fixture")
    except RuntimeError:
        if not rollback:
            raise
    async with e.connect() as c:
        rows = (
            (
                await c.execute(
                    sa.select(notice_outbox).where(notice_outbox.c.kind == "takeover")
                )
            )
            .mappings()
            .all()
        )
    if rollback:
        assert rows == []
    else:
        assert len(rows) == 1
        assert Decimal(rows[0]["snapshot"]["quantity"]) == quantity
        assert rows[0]["snapshot"]["facts_at_ms"] == 6000
        assert "Ticket" not in rows[0]["payload"]
        if quantity:
            assert (
                "止损待核实" not in rows[0]["payload"]
            )  # complete facts prove absence
            assert "未覆盖 0.0005" in rows[0]["payload"]
        else:
            assert "余仓 0" in rows[0]["payload"]


@pytest.mark.asyncio
async def test_runtime_fault_and_recovery_notify_once_without_ticket_or_recursive_notice(
    head_template_engine,
):
    from src.trading_kernel.application.ports import (
        MonitorOwnerStatus,
        MonitorStateRecord,
    )

    e = head_template_engine
    async with PostgresKernelUnitOfWork(e) as u:
        for key in ["reconciliation-worker:test", "notification:feishu"]:
            for status, when in [
                (MonitorOwnerStatus.NEEDS_INTERVENTION, 1000),
                (MonitorOwnerStatus.NEEDS_INTERVENTION, 2000),
                (MonitorOwnerStatus.COMPLETED, 3000),
            ]:
                await u.monitors.save_if_changed(
                    MonitorStateRecord(
                        monitor_key=key,
                        owner_status=status,
                        summary="internal:not-for-phone",
                        intervention="none",
                        updated_at_ms=when,
                    )
                )
    async with e.connect() as c:
        rows = (await c.execute(sa.select(notice_outbox))).mappings().all()
    assert len(rows) == 2
    assert all(r["ticket_id"] is None and "internal:" not in r["payload"] for r in rows)
    assert {r["kind"] for r in rows} == {"runtime_fault", "runtime_recovered"}


@pytest.mark.asyncio
async def test_manual_original_tp_fill_notifies_from_new_persisted_evidence_once(
    head_template_engine,
):
    from src.trading_kernel.application.observe_trade_management import (
        observe_trade_management,
    )
    from src.trading_kernel.domain.trade_management import OrderEvidence
    from tests.trading_kernel.support.manual_management import (
        app_evidence,
        app_order,
    )

    e = head_template_engine
    t = registered_sor_long_ticket()
    await reach_position_protected(e, t)
    async with PostgresKernelUnitOfWork(e) as u:
        await observe_trade_management(
            u, ticket_id=t.identity.ticket_id, evidence=app_evidence(t), now_ms=5100
        )
    async with PostgresKernelUnitOfWork(e) as u:
        a = await u.aggregates.get(t.identity.ticket_id)
        fill = OrderEvidence(
            evidence_id="tp-execution",
            terms=app_order(t, exchange_order_id=a.tp1_exchange_order_id),
            action="trade",
            exchange_event_at_ms=5500,
            received_at_ms=5501,
            executed_quantity=Decimal(".0005"),
            coverage_complete=True,
            known_command_outcome_pending=False,
        )
        await observe_trade_management(
            u, ticket_id=t.identity.ticket_id, evidence=fill, now_ms=6000
        )
        await reconcile_ticket(
            u,
            ReconcileTicketRequest(
                ticket_id=t.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=t.identity.netting_domain,
                    quantity=Decimal(".0005"),
                    average_entry_price=Decimal(60000),
                    observed_at_ms=6000,
                ),
            ),
        )
    async with PostgresKernelUnitOfWork(e) as u:
        await observe_trade_management(
            u, ticket_id=t.identity.ticket_id, evidence=fill, now_ms=7000
        )
    async with e.connect() as c:
        rows = (
            (
                await c.execute(
                    sa.select(notice_outbox).where(
                        notice_outbox.c.kind == "manual_fill"
                    )
                )
            )
            .mappings()
            .all()
        )
    assert len(rows) == 1
    assert rows[0]["snapshot"]["fill_quantity"] == "0.0005"
    assert (
        rows[0]["snapshot"]["fill_price"] is None
    )  # limit price is not execution price
    assert "TP1 累计成交 0.0005 BTC" in rows[0]["payload"]
