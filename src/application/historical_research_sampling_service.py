"""Historical research sampling service for BRC signal-input construction.

The service builds historical MarketSnapshot and StrategyFamilySignalInput
objects only to classify data coverage. It does not run strategy evaluators,
produce SignalOutput, write TrialTradeIntent rows, or touch live execution.
"""

from __future__ import annotations

from typing import Optional, Protocol

from src.application.historical_signal_input_builder import (
    HistoricalMarketSnapshotBuilder,
    HistoricalStrategyFamilySignalInputBuilder,
)
from src.domain.historical_ohlcv import HistoricalOhlcvBar
from src.domain.historical_research_sampling import (
    HistoricalResearchSamplingPoint,
    HistoricalResearchSamplingPointStatus,
    HistoricalResearchSamplingRun,
    HistoricalResearchSamplingStatus,
    HistoricalResearchSamplingSummary,
    compute_sampling_summary,
)
from src.domain.strategy_family_registry import (
    StrategyFamilyMetadata,
    StrategyFamilyPlaybookMetadata,
)
from src.domain.strategy_family_signal import SignalDataQualityStatus


class HistoricalSamplingRepository(Protocol):
    async def create_sampling_run(
        self,
        run: HistoricalResearchSamplingRun,
    ) -> HistoricalResearchSamplingRun:
        ...

    async def record_sampling_point(
        self,
        point: HistoricalResearchSamplingPoint,
    ) -> HistoricalResearchSamplingPoint:
        ...

    async def complete_sampling_run(
        self,
        *,
        run_id: str,
        summary: HistoricalResearchSamplingSummary,
        updated_at_ms: int,
        status: HistoricalResearchSamplingStatus = HistoricalResearchSamplingStatus.COMPLETED,
    ) -> HistoricalResearchSamplingRun:
        ...


class HistoricalSamplingBarReader(Protocol):
    async def fetch_bars(
        self,
        *,
        symbol: str,
        timeframe: str,
        start_time_ms: int,
        end_time_ms: int,
        limit: int = 5000,
    ) -> list[HistoricalOhlcvBar]:
        ...


class HistoricalResearchSamplingService:
    """Run compact historical input-construction sampling."""

    def __init__(
        self,
        *,
        sampling_repository: HistoricalSamplingRepository,
        ohlcv_repository: HistoricalSamplingBarReader,
        market_snapshot_builder: HistoricalMarketSnapshotBuilder,
        signal_input_builder: HistoricalStrategyFamilySignalInputBuilder,
        now_ms,
    ) -> None:
        self._sampling_repository = sampling_repository
        self._ohlcv_repository = ohlcv_repository
        self._market_snapshot_builder = market_snapshot_builder
        self._signal_input_builder = signal_input_builder
        self._now_ms = now_ms

    async def run_sampling(
        self,
        *,
        run_id: str,
        strategy_family_metadata: StrategyFamilyMetadata,
        playbook_metadata: StrategyFamilyPlaybookMetadata,
        dataset_ids: list[str],
        symbols: list[str],
        primary_timeframe: str,
        context_timeframes: list[str],
        start_time_ms: int,
        end_time_ms: int,
        explicit_timestamps: Optional[list[int]] = None,
        sampling_interval_bars: int = 1,
        sample_limit: int = 100,
        notes: str = "",
    ) -> HistoricalResearchSamplingSummary:
        now = self._now_ms()
        run = HistoricalResearchSamplingRun(
            run_id=run_id,
            strategy_family_id=strategy_family_metadata.family_id,
            strategy_family_version_id=strategy_family_metadata.version_id,
            playbook_id=playbook_metadata.playbook_id,
            dataset_ids=list(dataset_ids),
            symbols=list(symbols),
            primary_timeframe=primary_timeframe,
            context_timeframes=list(context_timeframes),
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
            sampling_method="explicit_timestamps" if explicit_timestamps else "interval_bars",
            sampling_interval_bars=sampling_interval_bars,
            sample_limit=sample_limit,
            status=HistoricalResearchSamplingStatus.RUNNING,
            created_at_ms=now,
            updated_at_ms=now,
            notes=notes,
        )
        await self._sampling_repository.create_sampling_run(run)

        points: list[HistoricalResearchSamplingPoint] = []
        for symbol in symbols:
            timestamps = await self._resolve_timestamps(
                symbol=symbol,
                primary_timeframe=primary_timeframe,
                start_time_ms=start_time_ms,
                end_time_ms=end_time_ms,
                explicit_timestamps=explicit_timestamps,
                sampling_interval_bars=sampling_interval_bars,
                sample_limit=sample_limit,
            )
            for timestamp_ms in timestamps:
                point = await self._sample_point(
                    run_id=run_id,
                    strategy_family_metadata=strategy_family_metadata,
                    playbook_metadata=playbook_metadata,
                    symbol=symbol,
                    timestamp_ms=timestamp_ms,
                    primary_timeframe=primary_timeframe,
                    context_timeframes=context_timeframes,
                )
                points.append(await self._sampling_repository.record_sampling_point(point))

        summary = compute_sampling_summary(
            run_id=run_id,
            points=points,
            notes="compact coverage metadata only; no full input snapshots stored",
        )
        await self._sampling_repository.complete_sampling_run(
            run_id=run_id,
            summary=summary,
            updated_at_ms=self._now_ms(),
        )
        return summary

    async def _resolve_timestamps(
        self,
        *,
        symbol: str,
        primary_timeframe: str,
        start_time_ms: int,
        end_time_ms: int,
        explicit_timestamps: Optional[list[int]],
        sampling_interval_bars: int,
        sample_limit: int,
    ) -> list[int]:
        if explicit_timestamps:
            return [
                timestamp
                for timestamp in explicit_timestamps
                if start_time_ms <= timestamp <= end_time_ms
            ][:sample_limit]
        bars = await self._ohlcv_repository.fetch_bars(
            symbol=symbol,
            timeframe=primary_timeframe,
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
            limit=sample_limit * max(1, sampling_interval_bars),
        )
        selected = bars[::sampling_interval_bars]
        return [bar.open_time_ms for bar in selected[:sample_limit]]

    async def _sample_point(
        self,
        *,
        run_id: str,
        strategy_family_metadata: StrategyFamilyMetadata,
        playbook_metadata: StrategyFamilyPlaybookMetadata,
        symbol: str,
        timestamp_ms: int,
        primary_timeframe: str,
        context_timeframes: list[str],
    ) -> HistoricalResearchSamplingPoint:
        point_id = f"{run_id}:{symbol}:{timestamp_ms}"
        try:
            market_snapshot = await self._market_snapshot_builder.build(
                symbol=symbol,
                timestamp_ms=timestamp_ms,
                primary_timeframe=primary_timeframe,
                context_timeframes=context_timeframes,
            )
            required_context_available = _required_context_available(
                market_snapshot.candle_context,
                primary_timeframe=primary_timeframe,
                context_timeframes=context_timeframes,
            )
            primary_available = bool(market_snapshot.last_price is not None)
            market_status = _market_status(
                primary_available=primary_available,
                required_context_available=required_context_available,
            )
            signal_input = await self._signal_input_builder.build(
                strategy_family_metadata=strategy_family_metadata,
                playbook_metadata=playbook_metadata,
                symbol=symbol,
                timestamp_ms=timestamp_ms,
                primary_timeframe=primary_timeframe,
                context_timeframes=context_timeframes,
                evaluation_id=f"{point_id}:input",
            )
            input_contract_valid = True
            signal_input_status = (
                HistoricalResearchSamplingPointStatus.OK
                if primary_available
                else HistoricalResearchSamplingPointStatus.INVALID
            )
            point_status = _point_status(
                primary_available=primary_available,
                required_context_available=required_context_available,
            )
            failure_reason = None
            missing_fields = sorted(set(market_snapshot.missing_fields + signal_input.input_quality.missing_fields))
            warnings = list(signal_input.input_quality.warnings)
            data_quality = signal_input.input_quality.status
        except Exception as exc:
            return HistoricalResearchSamplingPoint(
                point_id=point_id,
                run_id=run_id,
                symbol=symbol,
                timestamp_ms=timestamp_ms,
                primary_timeframe=primary_timeframe,
                context_timeframes=list(context_timeframes),
                point_status=HistoricalResearchSamplingPointStatus.INVALID,
                market_snapshot_status=HistoricalResearchSamplingPointStatus.INVALID,
                signal_input_status=HistoricalResearchSamplingPointStatus.INVALID,
                data_quality_status=SignalDataQualityStatus.INVALID,
                missing_fields=[],
                stale_fields=[],
                warnings=[],
                atr_available=False,
                candle_context_available=False,
                input_contract_valid=False,
                failure_reason=str(exc),
                created_at_ms=self._now_ms(),
            )

        return HistoricalResearchSamplingPoint(
            point_id=point_id,
            run_id=run_id,
            symbol=symbol,
            timestamp_ms=timestamp_ms,
            primary_timeframe=primary_timeframe,
            context_timeframes=list(context_timeframes),
            point_status=point_status,
            market_snapshot_status=market_status,
            signal_input_status=signal_input_status,
            data_quality_status=data_quality,
            missing_fields=missing_fields,
            stale_fields=[],
            warnings=warnings,
            atr_available=market_snapshot.atr is not None,
            candle_context_available=required_context_available,
            input_contract_valid=input_contract_valid,
            failure_reason=failure_reason,
            created_at_ms=self._now_ms(),
        )


def _required_context_available(
    candle_context: dict,
    *,
    primary_timeframe: str,
    context_timeframes: list[str],
) -> bool:
    windows = dict(candle_context.get("windows") or {})
    required = [primary_timeframe, *context_timeframes]
    return all(bool(windows.get(timeframe)) for timeframe in required)


def _market_status(
    *,
    primary_available: bool,
    required_context_available: bool,
) -> HistoricalResearchSamplingPointStatus:
    if not primary_available:
        return HistoricalResearchSamplingPointStatus.INVALID
    if not required_context_available:
        return HistoricalResearchSamplingPointStatus.DEGRADED
    return HistoricalResearchSamplingPointStatus.OK


def _point_status(
    *,
    primary_available: bool,
    required_context_available: bool,
) -> HistoricalResearchSamplingPointStatus:
    if not primary_available:
        return HistoricalResearchSamplingPointStatus.INVALID
    if not required_context_available:
        return HistoricalResearchSamplingPointStatus.DEGRADED
    return HistoricalResearchSamplingPointStatus.OK
