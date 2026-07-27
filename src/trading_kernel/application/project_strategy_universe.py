"""Build one shared deterministic RSR projection outside PostgreSQL transactions."""

from __future__ import annotations

import asyncio

from src.trading_kernel.application.load_closed_candle_window import (
    ClosedCandleWindowRequest,
    ClosedCandleWindowStatus,
    load_closed_candle_window,
)
from src.trading_kernel.application.market_ports import PublicMarketSource
from src.trading_kernel.application.ports import UnitOfWorkFactory
from src.trading_kernel.domain.detectors.rsr_vcb import (
    VCBArmedStructure,
    build_vcb_armed_structure,
)
from src.trading_kernel.domain.market import ClosedCandle, Timeframe
from src.trading_kernel.domain.strategy_universe import (
    StrategyUniverseVersion,
    UniverseLifecycle,
)
from src.trading_kernel.domain.universe_projection import (
    RSRUniverseProjection,
    build_rsr_projection,
)


_HOUR_MS = 3_600_000
_FOUR_HOURS_MS = 14_400_000


async def project_strategy_universe(
    uow_factory: UnitOfWorkFactory,
    market_source: PublicMarketSource,
    *,
    universe_version_id: str,
    trigger_time_ms: int,
    claim_owner: str | None = None,
) -> RSRUniverseProjection:
    if trigger_time_ms <= 0:
        raise ValueError("projection trigger time must be positive")
    as_of_1h_ms = trigger_time_ms - trigger_time_ms % _HOUR_MS
    as_of_4h_ms = trigger_time_ms - trigger_time_ms % _FOUR_HOURS_MS
    normalized_claim_owner = str(claim_owner or "").strip()
    if not normalized_claim_owner:
        normalized_claim_owner = (
            f"projection-worker:task:{id(asyncio.current_task())}"
        )
    async with uow_factory() as uow:
        stored = await uow.strategy_universes.get(universe_version_id)
        if stored is None:
            raise ValueError("projection Universe does not exist")
        universe, lifecycle = stored
        if lifecycle not in {UniverseLifecycle.WARMING, UniverseLifecycle.ACTIVE}:
            raise ValueError("projection Universe is not observable")
        existing = await uow.strategy_universes.get_latest_projection(
            event_spec_id=universe.event_spec_id,
            universe_version_id=universe.universe_version_id,
            at_or_before_close_time_ms=as_of_1h_ms,
        )
        if existing is not None and existing.as_of_close_time_ms == as_of_1h_ms:
            return existing
        claim_status = await uow.strategy_universes.claim_projection(
            event_spec_id=universe.event_spec_id,
            universe_version_id=universe.universe_version_id,
            as_of_close_time_ms=as_of_1h_ms,
            claim_owner=normalized_claim_owner,
            now_ms=trigger_time_ms,
            lease_until_ms=trigger_time_ms + 300_000,
        )
        if claim_status == "completed":
            completed = await uow.strategy_universes.get_latest_projection(
                event_spec_id=universe.event_spec_id,
                universe_version_id=universe.universe_version_id,
                at_or_before_close_time_ms=as_of_1h_ms,
            )
            if (
                completed is None
                or completed.as_of_close_time_ms != as_of_1h_ms
            ):
                raise ValueError("completed projection claim has no projection")
            return completed
        if claim_status == "busy":
            raise RuntimeError("projection lease is held by another worker")

    try:
        projection, armed = await _calculate_projection(
            market_source,
            universe=universe,
            as_of_1h_ms=as_of_1h_ms,
            as_of_4h_ms=as_of_4h_ms,
        )
    except Exception as exc:
        async with uow_factory() as uow:
            await uow.strategy_universes.fail_projection_claim(
                event_spec_id=universe.event_spec_id,
                universe_version_id=universe.universe_version_id,
                as_of_close_time_ms=as_of_1h_ms,
                claim_owner=normalized_claim_owner,
                failure_reason=type(exc).__name__,
                failed_at_ms=trigger_time_ms,
            )
        raise
    async with uow_factory() as uow:
        await uow.strategy_universes.save_projection(
            projection,
            persisted_at_ms=max(trigger_time_ms, projection.as_of_close_time_ms),
        )
        for structure in armed:
            await uow.strategy_universes.save_armed_structure(structure)
        await uow.strategy_universes.complete_projection_claim(
            event_spec_id=universe.event_spec_id,
            universe_version_id=universe.universe_version_id,
            as_of_close_time_ms=as_of_1h_ms,
            claim_owner=normalized_claim_owner,
            completed_at_ms=max(
                trigger_time_ms,
                projection.as_of_close_time_ms,
            ),
        )
    return projection


async def _calculate_projection(
    market_source: PublicMarketSource,
    *,
    universe: StrategyUniverseVersion,
    as_of_1h_ms: int,
    as_of_4h_ms: int,
) -> tuple[RSRUniverseProjection, tuple[VCBArmedStructure, ...]]:
    one_hour_ids = tuple(
        member.exchange_instrument_id for member in universe.members
    )
    one_hour_windows = await _load_many(
        market_source,
        instrument_ids=one_hour_ids,
        timeframe="1h",
        count=744,
        closed_at_ms=as_of_1h_ms,
    )
    reference_ids = tuple(
        member.exchange_instrument_id for member in universe.reference_members
    )
    four_hour_windows = await _load_many(
        market_source,
        instrument_ids=reference_ids,
        timeframe="4h",
        count=200,
        closed_at_ms=as_of_4h_ms,
    )
    candidate_ids = {
        member.exchange_instrument_id for member in universe.candidate_members
    }
    projection = build_rsr_projection(
        universe=universe,
        candidate_candles_1h={
            instrument_id: candles
            for instrument_id, candles in one_hour_windows.items()
            if instrument_id in candidate_ids
        },
        reference_candles_1h={
            instrument_id: candles
            for instrument_id, candles in one_hour_windows.items()
            if instrument_id in set(reference_ids)
        },
        reference_candles_4h=four_hour_windows,
    )
    armed = tuple(
        structure
        for member in projection.top_two
        if (
            structure := build_vcb_armed_structure(
                projection=projection,
                member=member,
                candles_1h=one_hour_windows[member.exchange_instrument_id],
            )
        )
        is not None
    )
    return projection, armed


async def _load_many(
    market_source: PublicMarketSource,
    *,
    instrument_ids: tuple[str, ...],
    timeframe: Timeframe,
    count: int,
    closed_at_ms: int,
) -> dict[str, tuple[ClosedCandle, ...]]:
    results = await asyncio.gather(
        *(
            load_closed_candle_window(
                market_source,
                ClosedCandleWindowRequest(
                    exchange_instrument_id=instrument_id,
                    timeframe=timeframe,
                    count=count,
                    closed_at_ms=closed_at_ms,
                ),
            )
            for instrument_id in instrument_ids
        )
    )
    unavailable = [
        result.reason_code
        for result in results
        if result.status is not ClosedCandleWindowStatus.AVAILABLE
    ]
    if unavailable:
        raise ValueError(f"projection market window unavailable: {unavailable[0]}")
    return {
        instrument_id: result.candles
        for instrument_id, result in zip(instrument_ids, results, strict=True)
    }


def projection_universe_is_us_equity(
    universe: StrategyUniverseVersion,
) -> bool:
    return universe.asset_class == "us_equity" and len(universe.reference_members) == 2
