import pytest
import sqlalchemy as sa

from src.trading_kernel.infrastructure.notice_delivery import deliver_one_notice
from src.trading_kernel.infrastructure.pg_models import notice_outbox
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.support.lifecycle import (
    reach_position_protected,
    registered_sor_long_ticket,
)


class Channel:
    def __init__(self, configured=True, fail=False):
        self.configured = configured
        self.fail = fail
        self.messages = []

    async def send(self, message):
        self.messages.append(message)
        if self.fail:
            raise TimeoutError("never expose this secret error")


@pytest.mark.asyncio
async def test_no_channel_preserves_message_and_attempts_then_retry_is_frozen(
    head_template_engine,
):
    e = head_template_engine
    await reach_position_protected(e, registered_sor_long_ticket())
    channel = Channel(configured=False)
    assert (
        await deliver_one_notice(e, channel, now_ms=10000)
    ).status == "channel_missing"
    async with e.connect() as c:
        row = (await c.execute(sa.select(notice_outbox))).mappings().one()
    assert row["attempts"] == 0 and row["status"] == "pending"
    channel.configured = True
    channel.fail = True
    assert (await deliver_one_notice(e, channel, now_ms=10000)).status == "retry"
    channel.fail = False
    assert (await deliver_one_notice(e, channel, now_ms=10001)).status == "no_work"
    assert (await deliver_one_notice(e, channel, now_ms=20000)).status == "accepted"
    assert len(channel.messages) == 2 and channel.messages[0] == channel.messages[1]
    assert (await deliver_one_notice(e, channel, now_ms=30000)).status == "no_work"
    async with e.connect() as c:
        row = (await c.execute(sa.select(notice_outbox))).mappings().one()
    assert row["accepted_at_ms"] >= 20000 and row["attempts"] == 2
    assert "secret" not in str(row)


@pytest.mark.asyncio
async def test_closed_position_suppresses_unsent_opened_notice(head_template_engine):
    from src.trading_kernel.application.reconcile_ticket import (
        ReconcileTicketRequest,
        reconcile_ticket,
    )
    from src.trading_kernel.domain.position import PositionSnapshot

    e = head_template_engine
    t = registered_sor_long_ticket()
    await reach_position_protected(e, t)
    async with PostgresKernelUnitOfWork(e) as u:
        await reconcile_ticket(
            u,
            ReconcileTicketRequest(
                ticket_id=t.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=t.identity.netting_domain,
                    quantity=0,
                    average_entry_price=None,
                    observed_at_ms=7000,
                ),
            ),
        )
    channel = Channel()
    await deliver_one_notice(e, channel, now_ms=10000)
    assert all("开仓已保护" not in m for m in channel.messages)
    async with e.connect() as c:
        assert (
            await c.scalar(
                sa.select(notice_outbox.c.status).where(
                    notice_outbox.c.kind == "opened"
                )
            )
            == "superseded"
        )


@pytest.mark.asyncio
async def test_concurrent_sender_cannot_claim_same_message_and_cancelled_lease_recovers(
    head_template_engine,
):
    import asyncio

    e = head_template_engine
    await reach_position_protected(e, registered_sor_long_ticket())
    started = asyncio.Event()

    class SlowChannel(Channel):
        async def send(self, message):
            self.messages.append(message)
            started.set()
            await asyncio.Event().wait()

    slow = SlowChannel()
    task = asyncio.create_task(deliver_one_notice(e, slow, now_ms=10000))
    await asyncio.wait_for(started.wait(), 2)
    fast = Channel()
    assert (await deliver_one_notice(e, fast, now_ms=10001)).status == "no_work"
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (await deliver_one_notice(e, fast, now_ms=25001)).status == "accepted"
    assert len(fast.messages) == 1


@pytest.mark.asyncio
async def test_retry_exhaustion_stops_after_five_and_keeps_visible_failure(
    head_template_engine,
):
    from src.trading_kernel.infrastructure.pg_models import monitor_current

    e = head_template_engine
    await reach_position_protected(e, registered_sor_long_ticket())
    channel = Channel(fail=True)
    for attempt in range(5):
        result = await deliver_one_notice(e, channel, now_ms=10000 + attempt * 100000)
    assert result.status == "dead" and len(channel.messages) == 5
    assert (await deliver_one_notice(e, channel, now_ms=1000000)).status == "no_work"
    async with e.connect() as c:
        assert (
            await c.scalar(
                sa.select(monitor_current.c.owner_status).where(
                    monitor_current.c.monitor_key == "notification:feishu"
                )
            )
            == "needs_intervention"
        )


@pytest.mark.asyncio
async def test_failed_risk_superseded_by_recovery_is_not_delivered_late(
    head_template_engine,
):
    from src.trading_kernel.application.ports import (
        MonitorOwnerStatus,
        MonitorStateRecord,
    )

    e = head_template_engine
    async with PostgresKernelUnitOfWork(e) as u:
        for status, now in [
            (MonitorOwnerStatus.NEEDS_INTERVENTION, 5000),
            (MonitorOwnerStatus.COMPLETED, 6000),
        ]:
            await u.monitors.save_if_changed(
                MonitorStateRecord(
                    monitor_key="reconciliation:test",
                    owner_status=status,
                    summary="checked",
                    intervention="none",
                    updated_at_ms=now,
                )
            )
    channel = Channel()
    result = await deliver_one_notice(e, channel, now_ms=10000)
    assert result.status == "superseded" and channel.messages == []


@pytest.mark.asyncio
async def test_retry_payload_remains_identical_even_after_delay_threshold(
    head_template_engine,
):
    e = head_template_engine
    await reach_position_protected(e, registered_sor_long_ticket())
    channel = Channel(fail=True)
    await deliver_one_notice(e, channel, now_ms=10000)
    channel.fail = False
    await deliver_one_notice(e, channel, now_ms=200000)
    assert channel.messages[0] == channel.messages[1]


@pytest.mark.asyncio
async def test_owner_can_read_delivery_state_without_mutating_outbox(
    head_template_engine,
):
    from src.trading_kernel.infrastructure.pg_notice_outbox import read_delivery_summary

    e = head_template_engine
    await reach_position_protected(e, registered_sor_long_ticket())
    channel = Channel()
    await deliver_one_notice(e, channel, now_ms=10000)
    async with e.connect() as c:
        before = (await c.execute(sa.select(notice_outbox))).mappings().all()
        summary = await read_delivery_summary(c)
        after = (await c.execute(sa.select(notice_outbox))).mappings().all()
    assert (
        summary.channel_state == "configured"
        and summary.pending_count == 0
        and summary.failed_count == 0
    )
    assert summary.last_accepted_at_ms >= 10000 and before == after


@pytest.mark.asyncio
async def test_delivery_failure_does_not_become_trading_monitor_authority(head_template_engine):
    from src.trading_kernel.application.ports import (
        MonitorOwnerStatus,
        MonitorStateRecord,
    )
    from src.trading_kernel.infrastructure.pg_owner_read_repository import (
        _monitor_rows_query,
    )
    e=head_template_engine
    async with PostgresKernelUnitOfWork(e) as u:
        await u.monitors.save_if_changed(MonitorStateRecord(monitor_key='notification:feishu',owner_status=MonitorOwnerStatus.NEEDS_INTERVENTION,summary='dead messages',intervention='route',updated_at_ms=9000))
    async with e.connect() as c:
        rows=(await c.execute(_monitor_rows_query(venue_id=None,account_id=None))).mappings().all()
    assert not any(row['monitor_key']=='notification:feishu' or row['needs_intervention_monitor_key']=='notification:feishu' for row in rows)
