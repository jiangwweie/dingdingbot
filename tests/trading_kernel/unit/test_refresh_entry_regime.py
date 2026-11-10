from contextlib import asynccontextmanager
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.trading_kernel.application import refresh_entry_regime as module
from src.trading_kernel.domain.entry_regime import FOUR_HOURS_MS, BtcMa50Snapshot
from src.trading_kernel.domain.market import ClosedCandle


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "enabled,certified,cached",
    [(False, True, False), (True, False, False), (True, True, True)],
)
async def test_disabled_uncertified_or_current_regime_does_not_read_network(
    monkeypatch, enabled, certified, cached
):
    now = 51 * FOUR_HOURS_MS + 1000
    repo = SimpleNamespace(
        any_enabled=AsyncMock(return_value=enabled),
        snapshot=AsyncMock(return_value=_snapshot(now) if cached else None),
        save_snapshot=AsyncMock(),
        try_begin_refresh=AsyncMock(return_value=True),
    )

    @asynccontextmanager
    async def factory():
        yield SimpleNamespace(entry_regimes=repo)

    source = SimpleNamespace(fetch_closed_candles=AsyncMock())
    monkeypatch.setattr(
        module, "runtime_writer_is_certified", AsyncMock(return_value=certified)
    )
    await module.refresh_entry_regime(
        factory,
        source,
        now_ms=now,
        timeout_seconds=1,
        runtime_commit="test",
        schema_revision="test",
        worker_id="observation",
    )
    source.fetch_closed_candles.assert_not_awaited()
    repo.save_snapshot.assert_not_awaited()


@pytest.mark.asyncio
async def test_regime_network_read_is_outside_transaction_and_fenced_before_save(
    monkeypatch,
):
    now = 51 * FOUR_HOURS_MS + 1000
    active = 0
    repo = SimpleNamespace(
        any_enabled=AsyncMock(return_value=True),
        snapshot=AsyncMock(return_value=None),
        save_snapshot=AsyncMock(),
        try_begin_refresh=AsyncMock(return_value=True),
    )

    @asynccontextmanager
    async def factory():
        nonlocal active
        active += 1
        try:
            yield SimpleNamespace(entry_regimes=repo)
        finally:
            active -= 1

    async def fetch(request):
        assert active == 0
        assert request.timeframe == "4h" and request.limit == 50
        return _snapshot(now).candles

    source = SimpleNamespace(fetch_closed_candles=fetch)
    fence = AsyncMock(side_effect=[True, False])
    monkeypatch.setattr(module, "runtime_writer_is_certified", fence)
    await module.refresh_entry_regime(
        factory,
        source,
        now_ms=now,
        timeout_seconds=1,
        runtime_commit="test",
        schema_revision="test",
        worker_id="observation",
    )
    assert fence.await_count == 2
    repo.save_snapshot.assert_not_awaited()


def _snapshot(now):
    h = FOUR_HOURS_MS
    return BtcMa50Snapshot(
        candles=tuple(
            ClosedCandle(
                open_time_ms=(i + 1) * h,
                close_time_ms=(i + 2) * h,
                open=Decimal(100),
                high=Decimal(100),
                low=Decimal(100),
                close=Decimal(100),
                volume=Decimal(1),
            )
            for i in range(50)
        ),
        observed_at_ms=now,
    )
