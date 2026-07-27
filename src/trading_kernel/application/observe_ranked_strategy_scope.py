"""Prepare a ranked RSR/VCB market snapshot for one closed 15m trigger."""

from __future__ import annotations

from src.trading_kernel.application.load_closed_candle_window import (
    ClosedCandleWindowRequest,
    ClosedCandleWindowStatus,
    load_closed_candle_window,
)
from src.trading_kernel.application.market_ports import PublicMarketSource
from src.trading_kernel.application.ports import (
    RuntimeScopeSnapshot,
    UnitOfWorkFactory,
)
from src.trading_kernel.application.project_strategy_universe import (
    project_strategy_universe,
)
from src.trading_kernel.domain.detectors.rsr_vcb import evaluate_rsr_vcb_trigger
from src.trading_kernel.domain.market import MarketSnapshot, RSRVCBContext


async def prepare_ranked_strategy_snapshot(
    uow_factory: UnitOfWorkFactory,
    market_source: PublicMarketSource,
    *,
    scope: RuntimeScopeSnapshot,
    trigger_close_time_ms: int,
) -> MarketSnapshot | None:
    if scope.universe_version_id is None or scope.universe_digest is None:
        raise ValueError("ranked scope lacks Universe lineage")
    projection = await project_strategy_universe(
        uow_factory,
        market_source,
        universe_version_id=scope.universe_version_id,
        trigger_time_ms=trigger_close_time_ms,
        claim_owner=f"scope-projection:{scope.runtime_scope_id}",
    )
    if (
        projection.universe_digest != scope.universe_digest
        or not projection.regime_eligible
    ):
        raise ValueError("ranked projection differs from runtime scope")
    member = next(
        (
            item
            for item in projection.top_two
            if item.exchange_instrument_id == scope.exchange_instrument_id
        ),
        None,
    )
    if member is None:
        return None
    async with uow_factory() as uow:
        armed = await uow.strategy_universes.get_active_armed_structure(
            event_spec_id=scope.event_spec_id,
            universe_version_id=scope.universe_version_id,
            projection_run_id=projection.projection_run_id,
            exchange_instrument_id=scope.exchange_instrument_id,
            now_ms=trigger_close_time_ms,
        )
    if armed is None:
        return None
    fifteen = await load_closed_candle_window(
        market_source,
        ClosedCandleWindowRequest(
            exchange_instrument_id=scope.exchange_instrument_id,
            timeframe="15m",
            count=120,
            closed_at_ms=trigger_close_time_ms,
        ),
    )
    hourly = await load_closed_candle_window(
        market_source,
        ClosedCandleWindowRequest(
            exchange_instrument_id=scope.exchange_instrument_id,
            timeframe="1h",
            count=260,
            closed_at_ms=projection.as_of_close_time_ms,
        ),
    )
    if (
        fifteen.status is not ClosedCandleWindowStatus.AVAILABLE
        or hourly.status is not ClosedCandleWindowStatus.AVAILABLE
    ):
        raise ValueError("ranked trigger market window unavailable")
    trigger = evaluate_rsr_vcb_trigger(
        armed=armed,
        candles_15m=fifteen.candles,
        candles_1h=hourly.candles,
    )
    if trigger is None:
        return None
    context = RSRVCBContext(
        universe_version_id=armed.universe_version_id,
        universe_digest=armed.universe_digest,
        projection_run_id=armed.projection_run_id,
        armed_structure_id=armed.armed_structure_id,
        rsr_rank=armed.rsr_rank,
        relative_strength_24h=armed.relative_strength_24h,
        relative_strength_72h=armed.relative_strength_72h,
        rsr_volume_ratio_24h=armed.rsr_volume_ratio_24h,
        regime_eligible=projection.regime_eligible,
        compression_ratio=armed.compression_ratio,
        breakout_boundary=armed.breakout_boundary,
        armed_at_ms=armed.armed_at_ms,
        trigger_volume_ratio=trigger.trigger_volume_ratio,
        initial_stop_reference=trigger.initial_stop_reference,
    )
    return MarketSnapshot(
        exchange_instrument_id=scope.exchange_instrument_id,
        trigger_candle_close_time_ms=trigger_close_time_ms,
        candles_15m=fifteen.candles,
        candles_1h=hourly.candles,
        rsr_vcb=context,
    )
