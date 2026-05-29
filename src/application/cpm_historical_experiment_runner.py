"""Bounded CPM-RO-001 historical experiment runner.

The runner is an Owner-facing application entrypoint for historical research
only. It reads registered metadata and historical OHLCV, delegates evaluation
to CPMHistoricalExperimentService, and persists a compact owner report. It does
not write trial-trade-intent evidence, create execution intents, create orders,
or update registry status.
"""

from __future__ import annotations

from hashlib import sha1
from typing import Optional, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.application.historical_signal_evaluation_service import CPMHistoricalExperimentService
from src.domain.cpm_historical_evaluator import CPM_FAMILY_ID
from src.domain.historical_ohlcv import HistoricalOhlcvDatasetMetadata
from src.domain.historical_signal_evaluation import (
    HistoricalForwardOutcome,
    HistoricalSignalEvaluationOwnerReport,
    HistoricalSignalEvaluationRun,
    HistoricalSignalEvaluationSummary,
    HistoricalSignalOutputRecord,
    build_historical_signal_owner_report,
)
from src.domain.strategy_family_registry import (
    StrategyFamilyMetadata,
    StrategyFamilyPlaybookMetadata,
)
from src.domain.strategy_family_signal import reject_forbidden_execution_fields


_ALLOWED_SYMBOLS = {"BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"}
_ALLOWED_PRIMARY_TIMEFRAMES = {"1h"}
_ALLOWED_CONTEXT_TIMEFRAMES = {"4h", "1d"}


class CPMHistoricalExperimentRunnerModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CPMHistoricalExperimentRunRequest(CPMHistoricalExperimentRunnerModel):
    strategy_family_id: str = Field(default=CPM_FAMILY_ID)
    symbols: list[str] = Field(default_factory=lambda: ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"])
    primary_timeframe: str = "1h"
    context_timeframes: list[str] = Field(default_factory=lambda: ["4h", "1d"])
    start_time_ms: int = Field(ge=0)
    end_time_ms: int = Field(ge=0)
    sampling_interval_bars: int = Field(default=24, ge=1)
    sample_limit: int = Field(default=500, ge=1, le=10000)
    run_label: str = Field(default="cpm-ro-001-historical", min_length=1, max_length=64)
    require_registered_datasets: bool = True

    @model_validator(mode="after")
    def _validate_bounds(self) -> "CPMHistoricalExperimentRunRequest":
        if self.strategy_family_id != CPM_FAMILY_ID:
            raise ValueError("CPM historical runner only supports CPM-RO-001")
        if self.end_time_ms < self.start_time_ms:
            raise ValueError("end_time_ms must be >= start_time_ms")
        unknown_symbols = sorted(set(self.symbols) - _ALLOWED_SYMBOLS)
        if unknown_symbols:
            raise ValueError(f"unsupported symbols for bounded CPM run: {unknown_symbols}")
        if self.primary_timeframe not in _ALLOWED_PRIMARY_TIMEFRAMES:
            raise ValueError("CPM historical runner only supports primary_timeframe=1h")
        unknown_context = sorted(set(self.context_timeframes) - _ALLOWED_CONTEXT_TIMEFRAMES)
        if unknown_context:
            raise ValueError(f"unsupported context timeframes for bounded CPM run: {unknown_context}")
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root="cpm_historical_run_request")
        return self


class CPMHistoricalExperimentRunResult(CPMHistoricalExperimentRunnerModel):
    run_id: str
    dataset_ids: list[str]
    summary: HistoricalSignalEvaluationSummary
    owner_report: HistoricalSignalEvaluationOwnerReport


class StrategyFamilyRegistryReader(Protocol):
    async def get_family_metadata(self, family_id: str) -> Optional[StrategyFamilyMetadata]:
        ...

    async def get_playbook_metadata(self, playbook_id: str) -> Optional[StrategyFamilyPlaybookMetadata]:
        ...


class HistoricalDatasetCatalogReader(Protocol):
    async def list_datasets(
        self,
        *,
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None,
    ) -> list[HistoricalOhlcvDatasetMetadata]:
        ...


class HistoricalEvaluationReportRepository(Protocol):
    async def get_evaluation_run(self, run_id: str) -> Optional[HistoricalSignalEvaluationRun]:
        ...

    async def list_signal_outputs(self, run_id: str) -> list[HistoricalSignalOutputRecord]:
        ...

    async def list_forward_outcomes(self, run_id: str) -> list[HistoricalForwardOutcome]:
        ...

    async def save_owner_review_report(
        self,
        *,
        run_id: str,
        report: HistoricalSignalEvaluationOwnerReport,
        updated_at_ms: int,
    ) -> HistoricalSignalEvaluationOwnerReport:
        ...


class CPMHistoricalExperimentRunner:
    """Bounded command object for CPM-RO-001 historical experiments."""

    def __init__(
        self,
        *,
        registry_repository: StrategyFamilyRegistryReader,
        dataset_repository: HistoricalDatasetCatalogReader,
        evaluation_repository: HistoricalEvaluationReportRepository,
        experiment_service: CPMHistoricalExperimentService,
        now_ms,
    ) -> None:
        self._registry_repository = registry_repository
        self._dataset_repository = dataset_repository
        self._evaluation_repository = evaluation_repository
        self._experiment_service = experiment_service
        self._now_ms = now_ms

    async def run(self, request: CPMHistoricalExperimentRunRequest) -> CPMHistoricalExperimentRunResult:
        family = await self._registry_repository.get_family_metadata(request.strategy_family_id)
        if family is None:
            raise ValueError(f"strategy family metadata not found: {request.strategy_family_id}")
        playbook = await self._registry_repository.get_playbook_metadata(request.strategy_family_id)
        if playbook is None:
            raise ValueError(f"strategy family playbook metadata not found: {request.strategy_family_id}")

        dataset_ids = await self._resolve_dataset_ids(request)
        run_id = _run_id(request, now_ms=self._now_ms())
        summary = await self._experiment_service.run_experiment(
            run_id=run_id,
            strategy_family_metadata=family,
            playbook_metadata=playbook,
            symbols=list(request.symbols),
            primary_timeframe=request.primary_timeframe,
            context_timeframes=list(request.context_timeframes),
            start_time_ms=request.start_time_ms,
            end_time_ms=request.end_time_ms,
            sampling_interval_bars=request.sampling_interval_bars,
            sample_limit=request.sample_limit,
            notes=(
                "Bounded CPM-RO-001 historical research run. "
                "Advisory only; not alpha proof and not a live candidate upgrade."
            ),
        )
        run = await self._evaluation_repository.get_evaluation_run(run_id)
        if run is None:
            raise ValueError(f"historical evaluation run was not persisted: {run_id}")
        signal_records = await self._evaluation_repository.list_signal_outputs(run_id)
        outcomes = await self._evaluation_repository.list_forward_outcomes(run_id)
        report = build_historical_signal_owner_report(
            run=run,
            signal_records=signal_records,
            outcomes=outcomes,
            summary=summary,
            notes=(
                "PG-backed compact Owner review report. Positive results remain research "
                "evidence only and do not imply alpha proof."
            ),
        )
        persisted_report = await self._evaluation_repository.save_owner_review_report(
            run_id=run_id,
            report=report,
            updated_at_ms=self._now_ms(),
        )
        return CPMHistoricalExperimentRunResult(
            run_id=run_id,
            dataset_ids=dataset_ids,
            summary=summary,
            owner_report=persisted_report,
        )

    async def _resolve_dataset_ids(self, request: CPMHistoricalExperimentRunRequest) -> list[str]:
        dataset_ids: list[str] = []
        missing: list[str] = []
        for symbol in request.symbols:
            for timeframe in [request.primary_timeframe, *request.context_timeframes]:
                datasets = await self._dataset_repository.list_datasets(
                    symbol=symbol,
                    timeframe=timeframe,
                )
                if not datasets:
                    missing.append(f"{symbol}:{timeframe}")
                    continue
                dataset_ids.extend(dataset.dataset_id for dataset in datasets)
        if missing and request.require_registered_datasets:
            raise ValueError(f"registered historical datasets missing: {', '.join(sorted(missing))}")
        return sorted(set(dataset_ids))


def _run_id(request: CPMHistoricalExperimentRunRequest, *, now_ms: int) -> str:
    suffix = sha1(
        "|".join(
            [
                request.strategy_family_id,
                ",".join(request.symbols),
                request.primary_timeframe,
                ",".join(request.context_timeframes),
                str(request.start_time_ms),
                str(request.end_time_ms),
                str(request.sampling_interval_bars),
                str(request.sample_limit),
                str(now_ms),
            ]
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"{request.run_label}-{suffix}"[:128]
