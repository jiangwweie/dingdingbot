from __future__ import annotations

from decimal import Decimal

import pytest

from src.trading_kernel.application.load_closed_candle_window import (
    ClosedCandleWindowRequest,
    ClosedCandleWindowStatus,
    load_closed_candle_window,
)
from src.trading_kernel.application.market_ports import (
    ClosedCandlePage,
    ClosedCandlePageRequest,
)
from src.trading_kernel.domain.market import ClosedCandle


class PagedSource:
    def __init__(self, candles: tuple[ClosedCandle, ...], *, overlap: bool = False) -> None:
        self.candles = candles
        self.overlap = overlap
        self.calls: list[ClosedCandlePageRequest] = []

    async def fetch_closed_candle_page(
        self,
        request: ClosedCandlePageRequest,
    ) -> ClosedCandlePage:
        self.calls.append(request)
        eligible = [
            item
            for item in self.candles
            if item.close_time_ms <= request.before_close_time_ms
        ]
        selected = tuple(eligible[-request.page_limit :])
        if self.overlap and len(self.calls) > 1 and selected:
            selected = (self.candles[min(len(self.candles) - 1, len(selected))], *selected)
        return ClosedCandlePage(
            exchange_instrument_id=request.exchange_instrument_id,
            timeframe=request.timeframe,
            candles=selected,
            next_before_close_time_ms=(
                None
                if not selected
                else min(item.close_time_ms for item in selected) - 3_600_000
            ),
        )


def _candles(count: int, *, gap_at: int | None = None) -> tuple[ClosedCandle, ...]:
    duration = 3_600_000
    candles: list[ClosedCandle] = []
    for index in range(count):
        effective_index = index + (1 if gap_at is not None and index >= gap_at else 0)
        opened = 1_700_000_000_000 + effective_index * duration
        candles.append(
            ClosedCandle(
                open_time_ms=opened,
                close_time_ms=opened + duration,
                open=Decimal("100"),
                high=Decimal("101"),
                low=Decimal("99"),
                close=Decimal("100"),
                volume=Decimal("10"),
                quote_volume=Decimal("1000"),
            )
        )
    return tuple(candles)


@pytest.mark.asyncio
async def test_loads_744_closed_hours_over_multiple_bounded_pages() -> None:
    candles = _candles(744)
    source = PagedSource(candles)

    result = await load_closed_candle_window(
        source,
        ClosedCandleWindowRequest(
            exchange_instrument_id="binance-usdm:MSTRUSDT:perpetual",
            timeframe="1h",
            count=744,
            closed_at_ms=candles[-1].close_time_ms,
            page_limit=500,
        ),
    )

    assert result.status is ClosedCandleWindowStatus.AVAILABLE
    assert result.candles == candles
    assert result.page_count == 2
    assert all(call.page_limit == 500 for call in source.calls)


@pytest.mark.asyncio
async def test_window_fails_closed_for_gap_or_insufficient_history() -> None:
    gapped = _candles(744, gap_at=400)
    gap_result = await load_closed_candle_window(
        PagedSource(gapped),
        ClosedCandleWindowRequest(
            exchange_instrument_id="binance-usdm:MSTRUSDT:perpetual",
            timeframe="1h",
            count=744,
            closed_at_ms=gapped[-1].close_time_ms,
        ),
    )
    short = _candles(100)
    short_result = await load_closed_candle_window(
        PagedSource(short),
        ClosedCandleWindowRequest(
            exchange_instrument_id="binance-usdm:MSTRUSDT:perpetual",
            timeframe="1h",
            count=744,
            closed_at_ms=short[-1].close_time_ms,
        ),
    )

    assert gap_result.reason_code == "candle_window_gap"
    assert short_result.reason_code == "candle_window_incomplete"
