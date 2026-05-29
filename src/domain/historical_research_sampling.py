"""Historical research sampling run domain models.

Sampling runs validate whether historical OHLCV data can construct BRC signal
input contracts. They do not evaluate strategies, produce SignalOutput, write
trial-trade-intent evidence, create execution intents, or create orders.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.strategy_family_signal import (
    SignalDataQualityStatus,
    reject_forbidden_execution_fields,
)


class HistoricalResearchSamplingModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HistoricalResearchSamplingStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class HistoricalResearchSamplingPointStatus(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    INVALID = "invalid"


class HistoricalResearchSamplingRun(HistoricalResearchSamplingModel):
    run_id: str = Field(min_length=1, max_length=128)
    strategy_family_id: str = Field(min_length=1, max_length=128)
    strategy_family_version_id: str = Field(min_length=1, max_length=128)
    playbook_id: Optional[str] = Field(default=None, max_length=128)
    dataset_ids: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)
    primary_timeframe: str = Field(min_length=1, max_length=32)
    context_timeframes: list[str] = Field(default_factory=list)
    start_time_ms: int = Field(ge=0)
    end_time_ms: int = Field(ge=0)
    sampling_method: str = Field(default="explicit_timestamps", max_length=64)
    sampling_interval_bars: int = Field(default=1, ge=1)
    sample_limit: int = Field(default=100, ge=1)
    status: HistoricalResearchSamplingStatus = HistoricalResearchSamplingStatus.PENDING
    summary_json: dict[str, Any] = Field(default_factory=dict)
    created_at_ms: int = Field(ge=0)
    updated_at_ms: int = Field(ge=0)
    notes: str = Field(default="", max_length=4096)

    @model_validator(mode="after")
    def _validate_range_and_reject_execution_fields(self) -> "HistoricalResearchSamplingRun":
        if self.end_time_ms < self.start_time_ms:
            raise ValueError("end_time_ms must be >= start_time_ms")
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root="historical_sampling_run")
        return self


class HistoricalResearchSamplingPoint(HistoricalResearchSamplingModel):
    point_id: str = Field(min_length=1, max_length=192)
    run_id: str = Field(min_length=1, max_length=128)
    symbol: str = Field(min_length=1, max_length=128)
    timestamp_ms: int = Field(ge=0)
    primary_timeframe: str = Field(min_length=1, max_length=32)
    context_timeframes: list[str] = Field(default_factory=list)
    point_status: HistoricalResearchSamplingPointStatus
    market_snapshot_status: HistoricalResearchSamplingPointStatus
    signal_input_status: HistoricalResearchSamplingPointStatus
    data_quality_status: SignalDataQualityStatus
    missing_fields: list[str] = Field(default_factory=list)
    stale_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    atr_available: bool = False
    candle_context_available: bool = False
    input_contract_valid: bool = False
    failure_reason: Optional[str] = Field(default=None, max_length=2048)
    created_at_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "HistoricalResearchSamplingPoint":
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root="historical_sampling_point")
        return self


class HistoricalResearchSamplingSummary(HistoricalResearchSamplingModel):
    run_id: str = Field(min_length=1, max_length=128)
    total_points: int = Field(ge=0)
    valid_points: int = Field(ge=0)
    degraded_points: int = Field(ge=0)
    invalid_points: int = Field(ge=0)
    by_symbol: dict[str, dict[str, int]] = Field(default_factory=dict)
    common_missing_fields: dict[str, int] = Field(default_factory=dict)
    atr_available_ratio: float = Field(ge=0, le=1)
    candle_context_available_ratio: float = Field(ge=0, le=1)
    input_contract_valid_ratio: float = Field(ge=0, le=1)
    notes: str = Field(default="", max_length=4096)

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "HistoricalResearchSamplingSummary":
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root="historical_sampling_summary")
        return self


def compute_sampling_summary(
    *,
    run_id: str,
    points: list[HistoricalResearchSamplingPoint],
    notes: str = "",
) -> HistoricalResearchSamplingSummary:
    total = len(points)
    valid = sum(1 for point in points if point.point_status == HistoricalResearchSamplingPointStatus.OK)
    degraded = sum(
        1 for point in points if point.point_status == HistoricalResearchSamplingPointStatus.DEGRADED
    )
    invalid = sum(
        1 for point in points if point.point_status == HistoricalResearchSamplingPointStatus.INVALID
    )
    by_symbol: dict[str, dict[str, int]] = {}
    missing_counts: dict[str, int] = {}
    for point in points:
        symbol_counts = by_symbol.setdefault(point.symbol, {"ok": 0, "degraded": 0, "invalid": 0})
        symbol_counts[point.point_status.value] += 1
        for field in point.missing_fields:
            missing_counts[field] = missing_counts.get(field, 0) + 1

    denominator = total or 1
    return HistoricalResearchSamplingSummary(
        run_id=run_id,
        total_points=total,
        valid_points=valid,
        degraded_points=degraded,
        invalid_points=invalid,
        by_symbol=by_symbol,
        common_missing_fields=dict(sorted(missing_counts.items())),
        atr_available_ratio=sum(1 for point in points if point.atr_available) / denominator,
        candle_context_available_ratio=sum(
            1 for point in points if point.candle_context_available
        )
        / denominator,
        input_contract_valid_ratio=sum(1 for point in points if point.input_contract_valid) / denominator,
        notes=notes,
    )
