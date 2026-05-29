"""Historical StrategyFamilySignalOutput experiment service.

This service builds historical signal inputs, evaluates CPM-RO-001, records
compact signal evidence, and records forward outcome review for would-enter
signals. It does not write trial-trade-intent evidence, create execution
intents, create orders, or wire into live runners.
"""

from __future__ import annotations

from typing import Optional, Protocol

from src.application.historical_signal_input_builder import HistoricalStrategyFamilySignalInputBuilder
from src.domain.cpm_historical_evaluator import CPMRO001HistoricalEvaluator
from src.domain.forward_outcome_review import DEFAULT_FORWARD_WINDOWS, calculate_forward_outcomes
from src.domain.historical_ohlcv import HistoricalOhlcvBar
from src.domain.historical_signal_evaluation import (
    HistoricalForwardOutcome,
    HistoricalSignalEvaluationRun,
    HistoricalSignalEvaluationStatus,
    HistoricalSignalEvaluationSummary,
    HistoricalSignalOutputRecord,
    compute_historical_signal_summary,
    signal_output_record_from_output,
)
from src.domain.strategy_family_registry import (
    StrategyFamilyMetadata,
    StrategyFamilyPlaybookMetadata,
)
from src.domain.strategy_family_signal import SignalType


class HistoricalSignalEvaluationRepository(Protocol):
    async def create_evaluation_run(
        self,
        run: HistoricalSignalEvaluationRun,
    ) -> HistoricalSignalEvaluationRun:
        ...

    async def record_signal_output(
        self,
        record: HistoricalSignalOutputRecord,
    ) -> HistoricalSignalOutputRecord:
        ...

    async def record_forward_outcome(
        self,
        outcome: HistoricalForwardOutcome,
    ) -> HistoricalForwardOutcome:
        ...

    async def complete_evaluation_run(
        self,
        *,
        run_id: str,
        summary: HistoricalSignalEvaluationSummary,
        updated_at_ms: int,
        status: HistoricalSignalEvaluationStatus = HistoricalSignalEvaluationStatus.COMPLETED,
    ) -> HistoricalSignalEvaluationRun:
        ...


class HistoricalSignalEvaluationBarReader(Protocol):
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


class CPMHistoricalExperimentService:
    """Run compact CPM-RO-001 historical signal-output experiments."""

    def __init__(
        self,
        *,
        evaluation_repository: HistoricalSignalEvaluationRepository,
        ohlcv_repository: HistoricalSignalEvaluationBarReader,
        signal_input_builder: HistoricalStrategyFamilySignalInputBuilder,
        evaluator: CPMRO001HistoricalEvaluator,
        now_ms,
    ) -> None:
        self._evaluation_repository = evaluation_repository
        self._ohlcv_repository = ohlcv_repository
        self._signal_input_builder = signal_input_builder
        self._evaluator = evaluator
        self._now_ms = now_ms

    async def run_experiment(
        self,
        *,
        run_id: str,
        strategy_family_metadata: StrategyFamilyMetadata,
        playbook_metadata: StrategyFamilyPlaybookMetadata,
        symbols: list[str],
        primary_timeframe: str,
        context_timeframes: list[str],
        start_time_ms: int,
        end_time_ms: int,
        explicit_timestamps: Optional[list[int]] = None,
        sampling_interval_bars: int = 1,
        sample_limit: int = 100,
        notes: str = "",
    ) -> HistoricalSignalEvaluationSummary:
        now = self._now_ms()
        run = HistoricalSignalEvaluationRun(
            run_id=run_id,
            strategy_family_id=strategy_family_metadata.family_id,
            strategy_family_version_id=strategy_family_metadata.version_id,
            playbook_id=playbook_metadata.playbook_id,
            symbols=list(symbols),
            primary_timeframe=primary_timeframe,
            context_timeframes=list(context_timeframes),
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
            sampling_method="explicit_timestamps" if explicit_timestamps else "interval_bars",
            sampling_interval_bars=sampling_interval_bars,
            sample_limit=sample_limit,
            status=HistoricalSignalEvaluationStatus.RUNNING,
            created_at_ms=now,
            updated_at_ms=now,
            notes=notes,
        )
        await self._evaluation_repository.create_evaluation_run(run)

        signal_records: list[HistoricalSignalOutputRecord] = []
        outcomes: list[HistoricalForwardOutcome] = []
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
                signal_input = await self._signal_input_builder.build(
                    strategy_family_metadata=strategy_family_metadata,
                    playbook_metadata=playbook_metadata,
                    symbol=symbol,
                    timestamp_ms=timestamp_ms,
                    primary_timeframe=primary_timeframe,
                    context_timeframes=context_timeframes,
                    evaluation_id=_evaluation_id(run_id, symbol, timestamp_ms),
                )
                output = self._evaluator.evaluate(signal_input)
                record = await self._evaluation_repository.record_signal_output(
                    signal_output_record_from_output(
                        run_id=run_id,
                        output=output,
                        created_at_ms=self._now_ms(),
                    )
                )
                signal_records.append(record)
                if output.signal_type == SignalType.WOULD_ENTER:
                    for outcome in await self._calculate_outcomes(
                        run_id=run_id,
                        output=output,
                        primary_timeframe=primary_timeframe,
                    ):
                        outcomes.append(await self._evaluation_repository.record_forward_outcome(outcome))

        summary = compute_historical_signal_summary(
            run_id=run_id,
            signal_records=signal_records,
            outcomes=outcomes,
            notes="historical CPM experiment only; verdict is advisory and not alpha proof",
        )
        await self._evaluation_repository.complete_evaluation_run(
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
        return [bar.open_time_ms for bar in bars[::sampling_interval_bars][:sample_limit]]

    async def _calculate_outcomes(
        self,
        *,
        run_id: str,
        output,
        primary_timeframe: str,
    ) -> list[HistoricalForwardOutcome]:
        timeframe_ms = _timeframe_ms(primary_timeframe)
        max_bars = max(DEFAULT_FORWARD_WINDOWS.values())
        entry_bars = await self._ohlcv_repository.fetch_bars(
            symbol=output.symbol,
            timeframe=primary_timeframe,
            start_time_ms=output.timestamp_ms,
            end_time_ms=output.timestamp_ms,
            limit=1,
        )
        future_bars = await self._ohlcv_repository.fetch_bars(
            symbol=output.symbol,
            timeframe=primary_timeframe,
            start_time_ms=output.timestamp_ms + timeframe_ms,
            end_time_ms=output.timestamp_ms + timeframe_ms * max_bars,
            limit=max_bars,
        )
        return calculate_forward_outcomes(
            run_id=run_id,
            signal_output=output,
            entry_bar=entry_bars[0] if entry_bars else None,
            future_bars=future_bars,
            created_at_ms=self._now_ms(),
        )


def _evaluation_id(run_id: str, symbol: str, timestamp_ms: int) -> str:
    prefix = run_id[:80]
    return f"{prefix}:{symbol}:{timestamp_ms}"[:128]


def _timeframe_ms(timeframe: str) -> int:
    if timeframe == "1h":
        return 60 * 60 * 1000
    raise ValueError(f"unsupported historical experiment timeframe: {timeframe}")
