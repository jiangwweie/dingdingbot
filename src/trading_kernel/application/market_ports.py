"""Public closed-market data port used by observation only."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.domain.market import ClosedCandle, Timeframe
from src.trading_kernel.domain.product import ProductSessionSnapshot


class ClosedCandleRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_instrument_id: str
    timeframe: Timeframe
    limit: int
    closed_at_ms: int
    since_ms: int | None = None

    @field_validator("exchange_instrument_id", mode="before")
    @classmethod
    def _require_instrument_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("market request instrument must be non-blank")
        return normalized

    @field_validator("limit")
    @classmethod
    def _require_bounded_limit(cls, value: int) -> int:
        if value <= 0 or value > 500:
            raise ValueError("closed candle limit must be between 1 and 500")
        return value

    @field_validator("closed_at_ms")
    @classmethod
    def _require_positive_close_time(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("closed_at_ms must be positive")
        return value

    @field_validator("since_ms")
    @classmethod
    def _require_optional_positive_since(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("since_ms must be positive when supplied")
        return value

    @model_validator(mode="after")
    def _validate_since_window(self) -> ClosedCandleRequest:
        if self.since_ms is not None and self.since_ms >= self.closed_at_ms:
            raise ValueError("since_ms must precede closed_at_ms")
        return self


class PublicMarketSource(Protocol):
    async def fetch_closed_candles(
        self,
        request: ClosedCandleRequest,
    ) -> tuple[ClosedCandle, ...]: ...

    async def fetch_product_sessions(
        self,
        exchange_instrument_ids: tuple[str, ...],
        *,
        observed_at_ms: int,
    ) -> tuple[ProductSessionSnapshot, ...]: ...
