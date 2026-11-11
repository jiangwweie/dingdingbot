"""The actual Observation MA50 consumer, with raw market rows and local PG."""

from decimal import Decimal

import pytest
import sqlalchemy as sa

from src.trading_kernel.application.exit_regime import check_exit_regime
from src.trading_kernel.application.refresh_exit_regime import refresh_exit_regime
from src.trading_kernel.domain.exit_configuration import MA50_EVENTS
from src.trading_kernel.domain.exit_regime import FOUR_HOURS_MS
from src.trading_kernel.domain.market import ClosedCandle
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RuntimeAuthoritySeedRequest,
    seed_runtime_authority,
)
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION
from tests.trading_kernel.support.exit_configuration import (
    install_approved_exit_configuration,
)

NOW = 200 * FOUR_HOURS_MS + 1000


async def prepare(engine):
    async with PostgresKernelUnitOfWork(engine) as uow:
        await seed_runtime_authority(
            uow,
            RuntimeAuthoritySeedRequest(
                account_id="ma50-refresh",
                runtime_commit="a" * 40,
                schema_revision=CURRENT_SCHEMA_REVISION,
                seeded_at_ms=NOW - 1000,
            ),
        )
    await install_approved_exit_configuration(
        engine, account_id="ma50-refresh", now_ms=NOW
    )
    # Discard only the fixture's independently supplied public-market snapshot.
    async with engine.begin() as connection:
        await connection.execute(sa.text("DELETE FROM brc_btc_ma50_current"))


class Market:
    def __init__(self, *, failing=False):
        self.failing = failing
        self.calls = []

    async def fetch_closed_candles(self, request):
        self.calls.append(request)
        if self.failing:
            raise TimeoutError("public source unavailable")
        latest = request.closed_at_ms
        return tuple(
            ClosedCandle(
                open_time_ms=latest - (50 - i) * FOUR_HOURS_MS,
                close_time_ms=latest - (49 - i) * FOUR_HOURS_MS,
                open=Decimal(101 if i == 49 else 100),
                high=Decimal(101 if i == 49 else 100),
                low=Decimal(101 if i == 49 else 100),
                close=Decimal(101 if i == 49 else 100),
                volume=Decimal(1),
            )
            for i in range(50)
        )


async def refresh(engine, source, now):
    await refresh_exit_regime(
        lambda: PostgresKernelUnitOfWork(engine),
        source,
        now_ms=now,
        timeout_seconds=1,
        runtime_commit="a" * 40,
        schema_revision=CURRENT_SCHEMA_REVISION,
    )


@pytest.mark.asyncio
async def test_actual_consumer_refreshes_closed_window_and_reuses_it(head_template_engine):
    engine = head_template_engine
    await prepare(engine)
    source = Market()
    await refresh(engine, source, NOW)
    await refresh(engine, source, NOW + 1)
    assert len(source.calls) == 1
    request = source.calls[0]
    assert request.timeframe == "4h" and request.limit == 50
    assert request.since_ms == request.closed_at_ms - 50 * FOUR_HOURS_MS
    async with PostgresKernelUnitOfWork(engine) as uow:
        reason, proof = await check_exit_regime(
            uow, venue_id="binance-usdm", account_id="ma50-refresh",
            event_spec_id=MA50_EVENTS[0], now_ms=NOW,
        )
        assert reason is None and proof.snapshot.sma50 == Decimal("100.02")
    boundary = (NOW // FOUR_HOURS_MS + 1) * FOUR_HOURS_MS
    source.failing = True
    await refresh(engine, source, boundary)
    async with PostgresKernelUnitOfWork(engine) as uow:
        reason, _ = await check_exit_regime(
            uow, venue_id="binance-usdm", account_id="ma50-refresh",
            event_spec_id=MA50_EVENTS[0], now_ms=boundary,
        )
        assert reason == "ma50_stale"


@pytest.mark.asyncio
async def test_repeated_unavailable_refresh_is_throttled_without_duplicate_alerts(head_template_engine):
    engine = head_template_engine
    await prepare(engine)
    source = Market(failing=True)
    await refresh(engine, source, NOW)
    async with engine.connect() as connection:
        before = await connection.scalar(sa.text(
            "SELECT count(*) FROM brc_monitor_events WHERE monitor_key='btc-ma50-refresh'"
        ))
    await refresh(engine, source, NOW + 29_999)
    assert len(source.calls) == 1
    await refresh(engine, source, NOW + 30_000)
    assert len(source.calls) == 2
    async with engine.connect() as connection:
        after = await connection.scalar(sa.text(
            "SELECT count(*) FROM brc_monitor_events WHERE monitor_key='btc-ma50-refresh'"
        ))
    assert after == before
    async with PostgresKernelUnitOfWork(engine) as uow:
        assert (await uow.monitors.get("btc-ma50-refresh")).updated_at_ms == NOW + 30_000
        assert await uow.exit_profiles.get_ma50_snapshot() is None
    source.failing = False
    await refresh(engine, source, NOW + 60_000)
    async with PostgresKernelUnitOfWork(engine) as uow:
        assert (await uow.monitors.get("btc-ma50-refresh")).owner_status.value == "running"
        assert (await uow.exit_profiles.get_ma50_snapshot()).allowed_at(NOW + 60_000)
