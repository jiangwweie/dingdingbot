"""Receiver readiness must preserve strict clocks and distinguish recovered gaps."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.trading_kernel.infrastructure.pg_management_feed import PostgresManagementFeed
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION


def feed(**changes):
    values = {'scope_key': 's', 'epoch_id': 'epoch', 'connection_state': 'ready',
        'health_reason': None, 'lease_until_ms': 17000, 'persisted_watermark': 24,
        'applied_watermark': 24, 'last_successful_at_ms': 2000, 'connected_at_ms': 1000,
        'schema_revision': CURRENT_SCHEMA_REVISION, 'runtime_commit': 'a' * 40}
    return values | changes


@pytest.mark.asyncio
async def test_unready_due_to_future_heartbeat_does_not_reuse_an_old_recovered_gap():
    repo = PostgresManagementFeed(SimpleNamespace(begin_nested=lambda: None))
    repo.get_feed = AsyncMock(return_value=feed())
    repo.received_epoch = AsyncMock(return_value=None)
    repo.next_received_epoch = AsyncMock(return_value=None)
    repo.current_gap_started_at = AsyncMock(return_value=1000)
    result = await repo.read_readiness('s', required=True, now_ms=1900)
    assert not result.ready
    assert result.blocker_code == 'management_receiver_clock_invalid'
    assert result.blocked_since_ms is None


@pytest.mark.asyncio
async def test_readiness_reads_exactly_one_feed_row():
    repo = PostgresManagementFeed(SimpleNamespace(begin_nested=lambda: None))
    repo.get_feed = AsyncMock(side_effect=[feed(), feed()])
    repo.received_epoch = AsyncMock(return_value=None)
    repo.next_received_epoch = AsyncMock(return_value=None)
    assert (await repo.read_readiness('s', required=True, now_ms=2100)).ready
    assert repo.get_feed.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('clock,expected', [(2100, True), (1900, False), (18000, False)])
async def test_live_read_samples_after_row_without_relaxing_future_or_expired_checks(clock, expected):
    repo = PostgresManagementFeed(SimpleNamespace(begin_nested=lambda: None))
    repo.get_feed = AsyncMock(return_value=feed())
    repo.received_epoch = AsyncMock(return_value=None)
    repo.next_received_epoch = AsyncMock(return_value=None)
    assert await repo.feed_ready('s', now_ms=1000, clock_ms=lambda: clock) is expected
    # Replay/as-of calls keep their original strict time semantics.
    assert not await repo.feed_ready('s', now_ms=1000)


@pytest.mark.asyncio
async def test_lease_expiring_during_receipt_reads_does_not_authorize_send():
    repo = PostgresManagementFeed(SimpleNamespace(begin_nested=lambda: None))
    repo.get_feed = AsyncMock(return_value=feed())
    repo.received_epoch = AsyncMock(return_value=None)
    repo.next_received_epoch = AsyncMock(return_value=None)
    readings = iter([2100, 18000])
    assert not await repo.feed_ready('s', now_ms=1000, clock_ms=lambda: next(readings))


@pytest.mark.asyncio
async def test_readiness_and_reason_use_the_same_final_clock():
    repo = PostgresManagementFeed(SimpleNamespace(begin_nested=lambda: None))
    repo.get_feed = AsyncMock(return_value=feed())
    repo.received_epoch = AsyncMock(return_value=None)
    repo.next_received_epoch = AsyncMock(return_value=None)
    readings = iter([2100, 2100, 18000])
    result = await repo.read_readiness('s', required=True, now_ms=1000,
        clock_ms=lambda: next(readings))
    assert not result.ready
    assert result.blocker_code == 'management_receiver_lease_expired'


@pytest.mark.asyncio
@pytest.mark.parametrize('change', [
    {'connection_state': 'gap'}, {'health_reason': 'protocol_invalid'},
    {'persisted_watermark': 25}, {'schema_revision': 'wrong'},
    {'runtime_commit': 'b' * 40}, {'last_successful_at_ms': 2200},
    {'connected_at_ms': 2200}, {'last_successful_at_ms': 1, 'lease_until_ms': 40000},
])
async def test_live_clock_does_not_bypass_other_readiness_gates(change):
    repo = PostgresManagementFeed(SimpleNamespace(begin_nested=lambda: None))
    repo.get_feed = AsyncMock(return_value=feed(**change))
    repo.received_epoch = AsyncMock(return_value=None)
    repo.next_received_epoch = AsyncMock(return_value=None)
    assert not await repo.feed_ready('s', now_ms=1000, runtime_commit='a' * 40,
        clock_ms=lambda: 20000 if change.get('last_successful_at_ms') == 1 else 2100)


@pytest.mark.asyncio
@pytest.mark.parametrize('kind,expected', [('connected', None), ('gap', 1200), ('epoch_started', 1200), ('epoch_closed', None)])
async def test_recovered_gap_is_not_a_current_outage(kind, expected):
    result = SimpleNamespace(mappings=lambda: SimpleNamespace(one_or_none=lambda: {'kind': kind, 'occurred_at_ms': 1200}))
    repo = PostgresManagementFeed(SimpleNamespace(begin_nested=lambda: None, execute=AsyncMock(return_value=result)))
    assert await repo.current_gap_started_at('s', 'epoch') == expected


@pytest.mark.asyncio
async def test_overview_route_samples_clock_after_snapshot_is_available(monkeypatch):
    import src.trading_kernel.interfaces.owner_console_http.routes.overview as route

    clock = [1000]
    seen = {}

    class Repository:
        async def read_overview_facts(self, day_start_ms, now_ms, **kwargs):
            # The read snapshot was acquired after connection-pool waiting.
            clock[0] = 2000
            seen['clock'] = kwargs.get('clock_ms', lambda: now_ms)()
            return SimpleNamespace(observed_at_ms=seen['clock'], runtime_freshness='fresh')

    async def read_page(_request, operation):
        return await operation(Repository())

    monkeypatch.setattr(route, 'get_clock_ms', lambda request: clock[0])
    monkeypatch.setattr(route, 'read_page_facts', read_page)
    monkeypatch.setattr(route, 'build_owner_overview', lambda facts, now_ms: facts)
    monkeypatch.setattr(route, '_source_watermark', lambda facts: None)
    monkeypatch.setattr(route, 'envelope', lambda data, **kwargs: {'observed': data.observed_at_ms, **kwargs})
    result = await route.overview(SimpleNamespace())
    assert seen['clock'] == 2000
    assert result['now_ms'] == 2000
