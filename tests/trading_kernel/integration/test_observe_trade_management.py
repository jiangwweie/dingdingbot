from unittest.mock import AsyncMock

import pytest

from src.trading_kernel.application.observe_trade_management import (
    observe_trade_management,
)
from src.trading_kernel.domain.trade_management import (
    ManagementMode,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.support.lifecycle import (
    reach_position_protected,
    registered_sor_long_ticket,
)
from tests.trading_kernel.support.manual_management import app_evidence


@pytest.mark.asyncio
async def test_unfilled_app_order_causes_atomic_idempotent_takeover(
    head_template_engine,
):
    e = head_template_engine
    t = registered_sor_long_ticket()
    await reach_position_protected(e, t)
    async with PostgresKernelUnitOfWork(e) as uow:
        before = await uow.aggregates.get(t.identity.ticket_id)
        r = await observe_trade_management(
            uow, ticket_id=t.identity.ticket_id, evidence=app_evidence(t), now_ms=5100
        )
        assert r.mode is ManagementMode.MANUAL
    async with PostgresKernelUnitOfWork(e) as uow:
        a = await uow.aggregates.get(t.identity.ticket_id)
        assert a.ticket == before.ticket and a.position_qty == before.position_qty
        count = len(await uow.exchange_commands.list_for_ticket(t.identity.ticket_id))
        again = await observe_trade_management(
            uow, ticket_id=t.identity.ticket_id, evidence=app_evidence(t), now_ms=5200
        )
        assert again == r
        assert (await uow.aggregates.get(t.identity.ticket_id)).version == a.version
        assert (
            len(await uow.exchange_commands.list_for_ticket(t.identity.ticket_id))
            == count
        )


@pytest.mark.asyncio
async def test_other_account_evidence_cannot_take_over(head_template_engine):
    e = head_template_engine
    t = registered_sor_long_ticket()
    await reach_position_protected(e, t)
    async with PostgresKernelUnitOfWork(e) as uow:
        with pytest.raises(ValueError, match="scope"):
            await observe_trade_management(
                uow,
                ticket_id=t.identity.ticket_id,
                evidence=app_evidence(t, account_id="other"),
                now_ms=5100,
            )
        assert (
            await uow.aggregates.get(t.identity.ticket_id)
        ).management_mode is ManagementMode.AUTO


@pytest.mark.asyncio
async def test_takeover_projection_failure_rolls_back(head_template_engine):
    e = head_template_engine
    t = registered_sor_long_ticket()
    await reach_position_protected(e, t)
    with pytest.raises(RuntimeError, match="projection-failed"):
        async with PostgresKernelUnitOfWork(e) as uow:
            uow.monitors.save_if_changed = AsyncMock(
                side_effect=RuntimeError("projection-failed")
            )
            await observe_trade_management(
                uow,
                ticket_id=t.identity.ticket_id,
                evidence=app_evidence(t),
                now_ms=5100,
            )
    async with PostgresKernelUnitOfWork(e) as uow:
        assert (
            await uow.aggregates.get(t.identity.ticket_id)
        ).management_mode is ManagementMode.AUTO


@pytest.mark.asyncio
async def test_takeover_supersedes_prepared_commands_in_same_transaction(
    head_template_engine,
):
    from decimal import Decimal

    from src.trading_kernel.domain.commands import ExchangeCommandStatus
    from src.trading_kernel.domain.events import TakeProfitFilled
    from src.trading_kernel.domain.reducer import reduce_event

    e = head_template_engine
    t = registered_sor_long_ticket()
    await reach_position_protected(e, t)
    async with PostgresKernelUnitOfWork(e) as uow:
        a = await uow.aggregates.get_for_update(t.identity.ticket_id)
        event = TakeProfitFilled(
            event_id="tp-fill",
            ticket_id=t.identity.ticket_id,
            sequence=a.last_event_sequence + 1,
            occurred_at_ms=4000,
            filled_qty=a.tp1_target_qty,
            average_fill_price=Decimal(62000),
            runner_floor_price=Decimal(60100),
        )
        await uow.commit_reduction(
            event=event, reduction=reduce_event(a, event), expected_version=a.version
        )
    async with PostgresKernelUnitOfWork(e) as uow:
        assert any(
            c.status is ExchangeCommandStatus.PREPARED
            for c in await uow.exchange_commands.list_for_ticket(t.identity.ticket_id)
        )
        await observe_trade_management(
            uow, ticket_id=t.identity.ticket_id, evidence=app_evidence(t), now_ms=5100
        )
        assert not any(
            c.status is ExchangeCommandStatus.PREPARED
            for c in await uow.exchange_commands.list_for_ticket(t.identity.ticket_id)
        )


@pytest.mark.asyncio
async def test_takeover_notice_is_after_commit_and_not_repeated(head_template_engine,monkeypatch):
    import sqlalchemy as sa

    from src.trading_kernel.infrastructure.pg_models import notice_outbox
    e=head_template_engine;t=registered_sor_long_ticket();await reach_position_protected(e,t)
    async with PostgresKernelUnitOfWork(e) as u:
        await observe_trade_management(u,ticket_id=t.identity.ticket_id,evidence=app_evidence(t),now_ms=5100)
    async with e.connect() as c:
        assert await c.scalar(sa.select(sa.func.count()).select_from(notice_outbox).where(notice_outbox.c.kind=='takeover'))==1
    async with PostgresKernelUnitOfWork(e) as u:
        await observe_trade_management(u,ticket_id=t.identity.ticket_id,evidence=app_evidence(t),now_ms=5200)
    async with e.connect() as c:
        assert await c.scalar(sa.select(sa.func.count()).select_from(notice_outbox).where(notice_outbox.c.kind=='takeover'))==1


@pytest.mark.asyncio
async def test_flat_external_cancel_is_readonly_not_manual_takeover(head_template_engine):
    from decimal import Decimal

    import sqlalchemy as sa

    from src.trading_kernel.infrastructure.pg_models import trade_aggregates
    e=head_template_engine;t=registered_sor_long_ticket()
    await reach_position_protected(e,t)
    from src.trading_kernel.domain.events import ManagementReviewRequired
    from src.trading_kernel.domain.reducer import reduce_event
    async with PostgresKernelUnitOfWork(e) as u:
        a=await u.aggregates.get_for_update(t.identity.ticket_id)
        event=ManagementReviewRequired(event_id='gap-test',ticket_id=t.identity.ticket_id,
            sequence=a.last_event_sequence+1,occurred_at_ms=4000,evidence_id='gap-test',reason='collector_gap')
        await u.commit_reduction(event=event,reduction=reduce_event(a,event),expected_version=a.version)
    async with e.begin() as c:
        await c.execute(sa.update(trade_aggregates).where(trade_aggregates.c.ticket_id==t.identity.ticket_id).values(position_qty=0,status='reconciliation_pending'))
    from src.trading_kernel.domain.trade_management import OrderAction
    observation=app_evidence(t).model_copy(update={'action':OrderAction.CANCEL})
    async with PostgresKernelUnitOfWork(e) as u:
        before=await u.aggregates.get(t.identity.ticket_id)
        commands=await u.exchange_commands.list_for_ticket(t.identity.ticket_id)
        result=await observe_trade_management(u,ticket_id=t.identity.ticket_id,evidence=observation,now_ms=5100)
        after=await u.aggregates.get(t.identity.ticket_id)
        assert result.mode is ManagementMode.REVIEW_REQUIRED
        assert after.position_qty==Decimal(0) and after.management_mode is ManagementMode.REVIEW_REQUIRED
        assert after.version==before.version
        assert len(await u.exchange_commands.list_for_ticket(t.identity.ticket_id))==len(commands)
        assert await u.management.has_evidence(t.identity.ticket_id,observation.evidence_id)
