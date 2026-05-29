"""Historical OHLCV dataset catalog domain models.

These models describe reusable research data references and historical bars.
They do not implement strategy evaluation, live fetching, execution, orders, or
trial-trade-intent evidence recording.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.strategy_family_signal import reject_forbidden_execution_fields


class HistoricalOhlcvModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HistoricalOhlcvStorageKind(str, Enum):
    PG_TABLE = "pg_table"
    LOCAL_FILE = "local_file"
    EXTERNAL_REF = "external_ref"


class HistoricalDataQualityStatus(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    INVALID = "invalid"
    UNKNOWN = "unknown"


class HistoricalOhlcvDatasetMetadata(HistoricalOhlcvModel):
    dataset_id: str = Field(min_length=1, max_length=128)
    source: str = Field(min_length=1, max_length=128)
    market: str = Field(min_length=1, max_length=128)
    symbol: str = Field(min_length=1, max_length=128)
    timeframe: str = Field(min_length=1, max_length=32)
    start_time_ms: int = Field(ge=0)
    end_time_ms: int = Field(ge=0)
    row_count: int = Field(default=0, ge=0)
    storage_kind: HistoricalOhlcvStorageKind
    storage_ref: str = Field(min_length=1, max_length=512)
    timezone: str = Field(default="UTC", max_length=64)
    data_quality_status: HistoricalDataQualityStatus = HistoricalDataQualityStatus.UNKNOWN
    missing_intervals: list[dict[str, Any]] = Field(default_factory=list)
    created_at_ms: int = Field(ge=0)
    updated_at_ms: int = Field(ge=0)
    notes: str = Field(default="", max_length=4096)

    @model_validator(mode="after")
    def _validate_time_range_and_reject_execution_fields(self) -> "HistoricalOhlcvDatasetMetadata":
        if self.end_time_ms < self.start_time_ms:
            raise ValueError("end_time_ms must be >= start_time_ms")
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root="historical_ohlcv_dataset")
        return self


class HistoricalOhlcvBar(HistoricalOhlcvModel):
    source: str = Field(min_length=1, max_length=128)
    market: str = Field(min_length=1, max_length=128)
    symbol: str = Field(min_length=1, max_length=128)
    timeframe: str = Field(min_length=1, max_length=32)
    open_time_ms: int = Field(ge=0)
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal = Field(ge=Decimal("0"))
    quote_volume: Optional[Decimal] = None
    close_time_ms: Optional[int] = Field(default=None, ge=0)
    created_at_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def _validate_ohlcv(self) -> "HistoricalOhlcvBar":
        if self.open <= 0 or self.high <= 0 or self.low <= 0 or self.close <= 0:
            raise ValueError("OHLC prices must be positive")
        if self.high < self.low:
            raise ValueError("high must be >= low")
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root="historical_ohlcv_bar")
        return self


def historical_dataset_id(
    *,
    source: str,
    market: str,
    symbol: str,
    timeframe: str,
    start_time_ms: int,
    end_time_ms: int,
) -> str:
    normalized_symbol = symbol.replace("/", "").replace(":", "").replace("-", "").upper()
    normalized_timeframe = timeframe.replace("/", "_").lower()
    return f"{source}:{market}:{normalized_symbol}:{normalized_timeframe}:{start_time_ms}:{end_time_ms}"
