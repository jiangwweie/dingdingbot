"""Load and validate one exact bounded closed-candle window."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator

from src.trading_kernel.application.market_ports import (
    ClosedCandlePageRequest,
    PublicMarketSource,
)
from src.trading_kernel.domain.market import ClosedCandle, Timeframe


_TIMEFRAME_MS: dict[Timeframe, int] = {
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
}


class ClosedCandleWindowStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class ClosedCandleWindowRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_instrument_id: str
    timeframe: Timeframe
    count: int
    closed_at_ms: int
    page_limit: int = 500

    @field_validator("count")
    @classmethod
    def _require_count(cls, value: int) -> int:
        if value <= 0 or value > 2_000:
            raise ValueError("candle window count must be between 1 and 2000")
        return value

    @field_validator("page_limit")
    @classmethod
    def _require_page_limit(cls, value: int) -> int:
        if value <= 0 or value > 500:
            raise ValueError("candle window page limit must be between 1 and 500")
        return value


class ClosedCandleWindowResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ClosedCandleWindowStatus
    reason_code: str
    candles: tuple[ClosedCandle, ...] = ()
    page_count: int


async def load_closed_candle_window(
    source: PublicMarketSource,
    request: ClosedCandleWindowRequest,
) -> ClosedCandleWindowResult:
    duration_ms = _TIMEFRAME_MS[request.timeframe]
    by_open_time: dict[int, ClosedCandle] = {}
    before_ms = request.closed_at_ms
    page_count = 0
    max_pages = (request.count + request.page_limit - 1) // request.page_limit + 2
    while len(by_open_time) < request.count and page_count < max_pages:
        page = await source.fetch_closed_candle_page(
            ClosedCandlePageRequest(
                exchange_instrument_id=request.exchange_instrument_id,
                timeframe=request.timeframe,
                page_limit=min(request.page_limit, request.count),
                before_close_time_ms=before_ms,
            )
        )
        page_count += 1
        if (
            page.exchange_instrument_id != request.exchange_instrument_id
            or page.timeframe != request.timeframe
        ):
            return _unavailable("candle_page_identity_mismatch", page_count)
        for candle in page.candles:
            if candle.close_time_ms <= request.closed_at_ms:
                existing = by_open_time.get(candle.open_time_ms)
                if existing is not None and existing != candle:
                    return _unavailable("candle_duplicate_conflict", page_count)
                by_open_time[candle.open_time_ms] = candle
        if not page.candles or page.next_before_close_time_ms is None:
            break
        if page.next_before_close_time_ms >= before_ms:
            return _unavailable("candle_pagination_not_progressing", page_count)
        before_ms = page.next_before_close_time_ms

    ordered = tuple(sorted(by_open_time.values(), key=lambda item: item.open_time_ms))
    if len(ordered) < request.count:
        return _unavailable("candle_window_incomplete", page_count)
    selected = ordered[-request.count :]
    if selected[-1].close_time_ms != request.closed_at_ms:
        return _unavailable("candle_window_latest_close_mismatch", page_count)
    if any(
        candle.close_time_ms - candle.open_time_ms != duration_ms
        for candle in selected
    ):
        return _unavailable("candle_duration_mismatch", page_count)
    if any(
        current.open_time_ms != previous.close_time_ms
        for previous, current in zip(selected[:-1], selected[1:], strict=True)
    ):
        return _unavailable("candle_window_gap", page_count)
    return ClosedCandleWindowResult(
        status=ClosedCandleWindowStatus.AVAILABLE,
        reason_code="closed_candle_window_available",
        candles=selected,
        page_count=page_count,
    )


def _unavailable(reason: str, page_count: int) -> ClosedCandleWindowResult:
    return ClosedCandleWindowResult(
        status=ClosedCandleWindowStatus.UNAVAILABLE,
        reason_code=reason,
        page_count=page_count,
    )
