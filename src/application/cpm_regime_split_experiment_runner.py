"""Regime-split CPM-RO-001 historical experiment runner.

This wrapper runs the existing bounded CPM historical runner over explicit
market-structure windows and persists a compact cross-window comparison. It is
research-only and does not create trial intents, execution intents, orders, or
registry status upgrades.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha1
from math import ceil
from typing import Optional, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.application.cpm_historical_experiment_runner import (
    CPMHistoricalExperimentRunRequest,
    CPMHistoricalExperimentRunResult,
    CPMHistoricalExperimentRunner,
)
from src.domain.cpm_historical_evaluator import CPM_FAMILY_ID
from src.domain.historical_signal_evaluation import (
    HistoricalRegimeSplitComparisonReport,
    HistoricalRegimeWindowReport,
    build_regime_split_comparison_report,
)
from src.domain.strategy_family_signal import reject_forbidden_execution_fields


_ALLOWED_SYMBOLS = {"BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"}
_ALLOWED_PRIMARY_TIMEFRAMES = {"1h"}
_ALLOWED_CONTEXT_TIMEFRAMES = {"4h", "1d"}

_START_2021_MS = 1609459200000
_START_2024_MS = 1704067200000
_START_2025_MS = 1735689600000
_END_2023_MS = 1704067199999


@dataclass(frozen=True)
class CPMRegimeWindowSpec:
    window_name: str
    window_role: str
    decision_weight: str
    start_time_ms: int
    end_time_ms: int
    run_label_suffix: str


class CPMRegimeSplitModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CPMRegimeSplitRunRequest(CPMRegimeSplitModel):
    strategy_family_id: str = Field(default=CPM_FAMILY_ID)
    symbols: list[str] = Field(default_factory=lambda: ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"])
    primary_timeframe: str = "1h"
    context_timeframes: list[str] = Field(default_factory=lambda: ["4h", "1d"])
    end_time_ms: int = Field(ge=0)
    sampling_interval_bars: int = Field(default=24, ge=1)
    sample_limit_per_window: int = Field(default=1500, ge=1, le=10000)
    sample_limit_per_symbol: Optional[int] = Field(default=None, ge=1, le=10000)
    max_total_evaluations: int = Field(default=6000, ge=1, le=50000)
    run_label: str = Field(default="cpm_ro001_regime_split_current_structure", min_length=1, max_length=64)
    require_registered_datasets: bool = True

    @model_validator(mode="after")
    def _validate_bounds(self) -> "CPMRegimeSplitRunRequest":
        if self.strategy_family_id != CPM_FAMILY_ID:
            raise ValueError("regime split runner only supports CPM-RO-001")
        if self.end_time_ms < _START_2025_MS:
            raise ValueError("end_time_ms must be >= 2025-01-01 UTC for regime split run")
        unknown_symbols = sorted(set(self.symbols) - _ALLOWED_SYMBOLS)
        if unknown_symbols:
            raise ValueError(f"unsupported symbols for CPM regime split run: {unknown_symbols}")
        if self.primary_timeframe not in _ALLOWED_PRIMARY_TIMEFRAMES:
            raise ValueError("CPM regime split runner only supports primary_timeframe=1h")
        unknown_context = sorted(set(self.context_timeframes) - _ALLOWED_CONTEXT_TIMEFRAMES)
        if unknown_context:
            raise ValueError(f"unsupported context timeframes for CPM regime split run: {unknown_context}")
        per_symbol_limit = _per_symbol_limit(self)
        planned_evaluations = len(build_cpm_regime_windows(self.end_time_ms)) * len(self.symbols) * per_symbol_limit
        if planned_evaluations > self.max_total_evaluations:
            raise ValueError(
                f"planned evaluations {planned_evaluations} exceed max_total_evaluations {self.max_total_evaluations}"
            )
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root="cpm_regime_split_run_request")
        return self


class CPMRegimeSplitRunResult(CPMRegimeSplitModel):
    comparison_id: str
    child_results_by_window_name: dict[str, CPMHistoricalExperimentRunResult]
    comparison_report: HistoricalRegimeSplitComparisonReport


class RegimeSplitReportRepository(Protocol):
    async def save_regime_split_report(
        self,
        report: HistoricalRegimeSplitComparisonReport,
    ) -> HistoricalRegimeSplitComparisonReport:
        ...


class CPMRegimeSplitExperimentRunner:
    """Run CPM-RO-001 across current, recent, legacy, and full diagnostic windows."""

    def __init__(
        self,
        *,
        child_runner: CPMHistoricalExperimentRunner,
        report_repository: RegimeSplitReportRepository,
        now_ms,
    ) -> None:
        self._child_runner = child_runner
        self._report_repository = report_repository
        self._now_ms = now_ms

    async def run(self, request: CPMRegimeSplitRunRequest) -> CPMRegimeSplitRunResult:
        windows = build_cpm_regime_windows(request.end_time_ms)
        per_symbol_limit = _per_symbol_limit(request)
        child_results: dict[str, CPMHistoricalExperimentRunResult] = {}
        window_reports: list[HistoricalRegimeWindowReport] = []

        for window in windows:
            child = await self._child_runner.run(
                CPMHistoricalExperimentRunRequest(
                    symbols=list(request.symbols),
                    primary_timeframe=request.primary_timeframe,
                    context_timeframes=list(request.context_timeframes),
                    start_time_ms=window.start_time_ms,
                    end_time_ms=window.end_time_ms,
                    sampling_interval_bars=request.sampling_interval_bars,
                    sample_limit=per_symbol_limit,
                    run_label=f"{request.run_label}-{window.run_label_suffix}"[:64],
                    require_registered_datasets=request.require_registered_datasets,
                )
            )
            child_results[window.window_name] = child
            window_reports.append(
                HistoricalRegimeWindowReport(
                    window_name=window.window_name,
                    window_role=window.window_role,
                    decision_weight=window.decision_weight,
                    start_time_ms=window.start_time_ms,
                    end_time_ms=window.end_time_ms,
                    run_id=child.run_id,
                    owner_report=child.owner_report,
                )
            )

        comparison = build_regime_split_comparison_report(
            comparison_id=_comparison_id(request, now_ms=self._now_ms()),
            strategy_family_id=request.strategy_family_id,
            window_reports=window_reports,
            created_at_ms=self._now_ms(),
        )
        persisted = await self._report_repository.save_regime_split_report(comparison)
        return CPMRegimeSplitRunResult(
            comparison_id=persisted.comparison_id,
            child_results_by_window_name=child_results,
            comparison_report=persisted,
        )


def build_cpm_regime_windows(end_time_ms: int) -> list[CPMRegimeWindowSpec]:
    return [
        CPMRegimeWindowSpec(
            window_name="primary_current_structure_2024_to_now",
            window_role="primary current-structure window",
            decision_weight="high",
            start_time_ms=_START_2024_MS,
            end_time_ms=end_time_ms,
            run_label_suffix="primary2024",
        ),
        CPMRegimeWindowSpec(
            window_name="recent_current_structure_2025_to_now",
            window_role="recent current-structure window",
            decision_weight="high",
            start_time_ms=_START_2025_MS,
            end_time_ms=end_time_ms,
            run_label_suffix="recent2025",
        ),
        CPMRegimeWindowSpec(
            window_name="legacy_control_2021_to_2023",
            window_role="legacy control stress/contrast window",
            decision_weight="low",
            start_time_ms=_START_2021_MS,
            end_time_ms=_END_2023_MS,
            run_label_suffix="legacy2021",
        ),
        CPMRegimeWindowSpec(
            window_name="full_diagnostic_2021_to_now",
            window_role="full diagnostic contrast window",
            decision_weight="diagnostic_only",
            start_time_ms=_START_2021_MS,
            end_time_ms=end_time_ms,
            run_label_suffix="full2021",
        ),
    ]


def current_utc_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _per_symbol_limit(request: CPMRegimeSplitRunRequest) -> int:
    if request.sample_limit_per_symbol is not None:
        return min(request.sample_limit_per_symbol, request.sample_limit_per_window)
    return max(1, ceil(request.sample_limit_per_window / len(request.symbols)))


def _comparison_id(request: CPMRegimeSplitRunRequest, *, now_ms: int) -> str:
    suffix = sha1(
        "|".join(
            [
                request.strategy_family_id,
                ",".join(request.symbols),
                request.primary_timeframe,
                ",".join(request.context_timeframes),
                str(request.end_time_ms),
                str(request.sampling_interval_bars),
                str(request.sample_limit_per_window),
                str(request.sample_limit_per_symbol),
                str(request.max_total_evaluations),
                str(now_ms),
            ]
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"{request.run_label}-{suffix}"[:128]
