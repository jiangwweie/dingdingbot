from types import SimpleNamespace

import pytest

from scripts.trading_kernel import certify_readonly as certification
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RuntimeAuthoritySeedRequest,
    seed_runtime_authority,
)
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION


@pytest.mark.asyncio
async def test_readonly_feed_uses_actual_read_time_not_pre_connection_start(
    head_template_engine, monkeypatch
):
    e = head_template_engine
    async with PostgresKernelUnitOfWork(e) as u:
        await seed_runtime_authority(
            u,
            RuntimeAuthoritySeedRequest(
                account_id="clock-account",
                runtime_commit="a" * 40,
                schema_revision=CURRENT_SCHEMA_REVISION,
                seeded_at_ms=1000,
            ),
        )
        scope = "brc-app-manual-v1:binance-usdm:clock-account"
        await u.management.start_feed(
            scope_key=scope,
            epoch_id="clock-epoch",
            worker_id="receiver",
            runtime_commit="a" * 40,
            now_ms=1500,
        )
        await u.management.persist_stream_batch(
            scope_key=scope,
            epoch_id="clock-epoch",
            events=[],
            connected_at_ms=1500,
            now_ms=1500,
        )
    # The receiver can commit after certifier startup but before its RR snapshot.
    readings = iter([1.0, 2.0])
    monkeypatch.setattr(
        certification, "time", SimpleNamespace(time=lambda: next(readings))
    )
    result = await certification._certify(
        e.url.render_as_string(hide_password=False), require_flat=True
    )
    assert result["management_feed_pass"] is True
    # Explicit replay time keeps strict as-of semantics, including future rejection.
    result = await certification._certify(
        e.url.render_as_string(hide_password=False), require_flat=True, now_ms=1000
    )
    assert result["management_feed_pass"] is False


async def test_integrity_pass_does_not_hide_management_trading_blocker(
    head_template_engine,
):
    e = head_template_engine
    async with PostgresKernelUnitOfWork(e) as u:
        await seed_runtime_authority(
            u,
            RuntimeAuthoritySeedRequest(
                account_id="feed-gap-account",
                runtime_commit="a" * 40,
                schema_revision=CURRENT_SCHEMA_REVISION,
                seeded_at_ms=1000,
            ),
        )
        scope = "brc-app-manual-v1:binance-usdm:feed-gap-account"
        await u.management.start_feed(
            scope_key=scope,
            epoch_id="gap-epoch",
            worker_id="receiver",
            runtime_commit="a" * 40,
            now_ms=1500,
        )
        await u.management.persist_stream_batch(
            scope_key=scope,
            epoch_id="gap-epoch",
            events=[],
            connected_at_ms=1500,
            now_ms=1500,
        )
        await u.management.persist_stream_batch(
            scope_key=scope,
            epoch_id="gap-epoch",
            events=[],
            connected_at_ms=1500,
            now_ms=1600,
            gap_reason="management_stream_protocol_invalid",
        )
    result = await certification._certify(
        e.url.render_as_string(hide_password=False), require_flat=True, now_ms=1700
    )
    assert result["status"] == "pass" and result["database_integrity_pass"]
    assert (
        result["entry_recovery_ready"] is False
        and result["management_feed_pass"] is False
    )
    assert (
        result["management_feed"]["blocker_code"]
        == "management_stream_protocol_invalid"
    )
    assert result["management_feed"]["blocked_since_ms"] == 1600


@pytest.mark.asyncio
async def test_live_gate_samples_after_pg_heartbeat_committed_during_read_wait(head_template_engine):
    from src.trading_kernel.application.management_health import (
        management_feed_is_current,
    )

    e = head_template_engine
    scope = 'brc-app-manual-v1:binance-usdm:read-wait-account'
    async with PostgresKernelUnitOfWork(e) as u:
        await u.management.start_feed(scope_key=scope, epoch_id='clock-race',
            worker_id='receiver', runtime_commit='a' * 40, now_ms=1000)
        await u.management.persist_stream_batch(scope_key=scope, epoch_id='clock-race',
            events=[], connected_at_ms=1000, now_ms=1000)
    # Request took its timestamp at1000. A heartbeat commits before its first read.
    async with PostgresKernelUnitOfWork(e) as writer:
        await writer.management.persist_stream_batch(scope_key=scope, epoch_id='clock-race',
            events=[], connected_at_ms=1000, now_ms=1500)
    async with PostgresKernelUnitOfWork(e) as reader:
        assert not await reader.management.feed_ready(scope, now_ms=1000)
        assert await management_feed_is_current(reader, venue_id='binance-usdm',
            account_id='read-wait-account', runtime_commit='a' * 40,
            now_ms=1000, clock_ms=lambda: 1501)
        future = await reader.management.read_readiness(scope, required=True, now_ms=1000)
        assert future.blocker_code == 'management_receiver_clock_invalid'
        live = await reader.management.read_readiness(scope, required=True,
            now_ms=1000, runtime_commit='a' * 40, clock_ms=lambda: 1501)
        assert live.ready and live.blocked_since_ms is None
        assert not await reader.management.feed_ready(scope, now_ms=1501,
            runtime_commit='b' * 40, clock_ms=lambda: 1501)


@pytest.mark.asyncio
async def test_pg_recovered_gap_does_not_become_a_new_outage_start(head_template_engine):
    e = head_template_engine
    scope = 'brc-app-manual-v1:binance-usdm:recovered-gap'
    async with PostgresKernelUnitOfWork(e) as u:
        await u.management.start_feed(scope_key=scope, epoch_id='recovered',
            worker_id='receiver', runtime_commit='a' * 40, now_ms=1000)
        await u.management.persist_stream_batch(scope_key=scope, epoch_id='recovered',
            events=[], connected_at_ms=1000, now_ms=1100, backlog_pending=True)
        assert await u.management.current_gap_started_at(scope, 'recovered') is not None
        await u.management.persist_stream_batch(scope_key=scope, epoch_id='recovered',
            events=[], connected_at_ms=1000, now_ms=1200, backlog_pending=False)
    async with PostgresKernelUnitOfWork(e) as u:
        assert await u.management.current_gap_started_at(scope, 'recovered') is None
        expired = await u.management.read_readiness(scope, required=True, now_ms=20000)
        assert not expired.ready
        assert expired.blocker_code == 'management_receiver_lease_expired'
        assert expired.blocked_since_ms == 16200


@pytest.mark.asyncio
async def test_overview_rr_snapshot_wait_does_not_misclassify_a_new_heartbeat(head_template_engine):
    import sqlalchemy as sa
    from sqlalchemy.dialects.postgresql import insert

    from src.trading_kernel.infrastructure.pg_models import (
        runtime_capabilities_current,
        runtime_profiles,
    )
    from src.trading_kernel.infrastructure.pg_owner_read_repository import (
        PostgresOwnerReadRepository,
        owner_read_transaction,
    )
    from tests.trading_kernel.support.lifecycle import (
        reach_runner_protected,
        registered_sor_long_ticket,
    )

    e = head_template_engine
    ticket = registered_sor_long_ticket()
    await reach_runner_protected(e, ticket)
    scope = 'brc-app-manual-v1:binance-usdm:' + ticket.identity.netting_domain.account_id
    async with e.begin() as c:
        await c.execute(sa.update(runtime_capabilities_current).where(
            runtime_capabilities_current.c.capability_key == 'exchange_commands').values(
                certification={'product_id': 'brc-app-manual-v1', 'management_feed_required': True}))
        await c.execute(insert(runtime_profiles).values(
            runtime_profile_id=ticket.identity.runtime.runtime_profile_id, venue_id='binance-usdm',
            account_id=ticket.identity.netting_domain.account_id, environment='live',
            position_mode='independent_sides', status='active', updated_at_ms=6000).on_conflict_do_nothing())
    async with PostgresKernelUnitOfWork(e) as u:
        await u.management.start_feed(scope_key=scope, epoch_id='overview-clock', worker_id='receiver',
            runtime_commit='kernel-test-head', now_ms=7000)
        await u.management.persist_stream_batch(scope_key=scope, epoch_id='overview-clock',
            events=[], connected_at_ms=7000, now_ms=7700)
    async with owner_read_transaction(e) as c:
        repo = PostgresOwnerReadRepository(c)
        # A response timestamp sampled before connection acquisition reproduces the old refusal.
        old = await repo.read_overview_facts(day_start_ms=1, now_ms=7000)
        assert old.management_feed is not None and not old.management_feed.ready
        current = await repo.read_overview_facts(day_start_ms=1, now_ms=7000, clock_ms=lambda: 7800)
        assert current.management_feed is not None and current.management_feed.ready
        assert current.observed_at_ms == 7800
