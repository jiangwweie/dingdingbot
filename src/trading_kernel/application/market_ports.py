"""Public closed-market data port used by observation only."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, field_validator

from src.trading_kernel.domain.market import ClosedCandle, Timeframe


class ClosedCandleRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_instrument_id: str
    timeframe: Timeframe
    limit: int
    closed_at_ms: int

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


class PublicMarketSource(Protocol):
    async def fetch_closed_candles(
        self,
        request: ClosedCandleRequest,
    ) -> tuple[ClosedCandle, ...]: ...

    async def fetch_closed_candle_page(
        self,
        request: "ClosedCandlePageRequest",
    ) -> "ClosedCandlePage": ...


class ClosedCandlePageRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_instrument_id: str
    timeframe: Timeframe
    page_limit: int
    before_close_time_ms: int

    @field_validator("exchange_instrument_id", mode="before")
    @classmethod
    def _require_page_instrument(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("candle page instrument must be non-blank")
        return normalized

    @field_validator("page_limit")
    @classmethod
    def _require_page_limit(cls, value: int) -> int:
        if value <= 0 or value > 500:
            raise ValueError("candle page limit must be between 1 and 500")
        return value

    @field_validator("before_close_time_ms")
    @classmethod
    def _require_page_boundary(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("candle page boundary must be positive")
        return value


class ClosedCandlePage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_instrument_id: str
    timeframe: Timeframe
    candles: tuple[ClosedCandle, ...]
    next_before_close_time_ms: int | None
