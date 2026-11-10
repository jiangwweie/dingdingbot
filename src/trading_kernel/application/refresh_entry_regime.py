"""Refresh one bounded public BTC window outside every PostgreSQL transaction."""

import asyncio

from src.trading_kernel.application.market_ports import (
    ClosedCandleRequest,
    PublicMarketSource,
)
from src.trading_kernel.application.ports import UnitOfWorkFactory
from src.trading_kernel.application.runtime_fence import runtime_writer_is_certified
from src.trading_kernel.domain.entry_regime import (
    BTC_REGIME_INSTRUMENT,
    FOUR_HOURS_MS,
    BtcMa50Snapshot,
)


async def refresh_entry_regime(
    uow_factory: UnitOfWorkFactory,
    source: PublicMarketSource,
    *,
    now_ms: int,
    timeout_seconds: float,
    runtime_commit: str,
    schema_revision: str,
    worker_id: str,
) -> None:
    if not await runtime_writer_is_certified(
        uow_factory,
        worker_id=worker_id,
        runtime_commit=runtime_commit,
        schema_revision=schema_revision,
        observed_at_ms=now_ms,
    ):
        return
    latest = now_ms // FOUR_HOURS_MS * FOUR_HOURS_MS
    async with uow_factory() as uow:
        if not await uow.entry_regimes.any_enabled():
            return
        snapshot = await uow.entry_regimes.snapshot()
        if snapshot is not None and snapshot.latest_close_ms == latest:
            return
        if not await uow.entry_regimes.try_begin_refresh(
            now_ms=now_ms, retry_interval_ms=max(30_000, int(timeout_seconds * 3000))
        ):
            return
    bars = await asyncio.wait_for(
        source.fetch_closed_candles(
            ClosedCandleRequest(
                exchange_instrument_id=BTC_REGIME_INSTRUMENT,
                timeframe="4h",
                limit=50,
                closed_at_ms=latest,
            )
        ),
        timeout=timeout_seconds,
    )
    snapshot = BtcMa50Snapshot(candles=tuple(bars), observed_at_ms=now_ms)
    if not await runtime_writer_is_certified(
        uow_factory,
        worker_id=worker_id,
        runtime_commit=runtime_commit,
        schema_revision=schema_revision,
        observed_at_ms=now_ms,
    ):
        return
    async with uow_factory() as uow:
        await uow.entry_regimes.save_snapshot(snapshot)
