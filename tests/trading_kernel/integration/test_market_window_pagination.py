from __future__ import annotations

from decimal import Decimal

import pytest

from src.trading_kernel.application.load_closed_candle_window import (
    ClosedCandleWindowRequest,
    ClosedCandleWindowStatus,
    load_closed_candle_window,
)
from src.trading_kernel.infrastructure.binance_public_market_source import (
    CcxtBinancePublicMarketSource,
)


class RecordedShapeExchange:
    def __init__(self, rows: list[list[object]]) -> None:
        self.rows = rows
        self.calls: list[dict[str, object]] = []

    def fapiPublicGetKlines(
        self,
        params: dict[str, object],
    ) -> list[list[object]]:
        self.calls.append(params)
        start = int(params["startTime"])
        end = int(params["endTime"])
        page_limit = int(params["limit"])
        return [
            row
            for row in self.rows
            if start <= int(row[0]) and int(row[6]) <= end
        ][:page_limit]

    def fetch_ohlcv(self, *args: object) -> object:
        raise AssertionError("native Binance klines must carry quote volume")


@pytest.mark.asyncio
async def test_recorded_binance_shape_preserves_quote_volume_across_pages() -> None:
    duration = 3_600_000
    start = 1_700_000_000_000
    rows = [
        [
            start + index * duration,
            "100",
            "101",
            "99",
            "100",
            "10",
            start + (index + 1) * duration - 1,
            str(Decimal("1000") + index),
        ]
        for index in range(744)
    ]
    exchange = RecordedShapeExchange(rows)
    source = CcxtBinancePublicMarketSource(
        exchange=exchange,
        venue_symbols={"binance-usdm:MSTRUSDT:perpetual": "MSTR/USDT:USDT"},
        timeout_seconds=1,
    )

    result = await load_closed_candle_window(
        source,
        ClosedCandleWindowRequest(
            exchange_instrument_id="binance-usdm:MSTRUSDT:perpetual",
            timeframe="1h",
            count=744,
            closed_at_ms=start + 744 * duration,
        ),
    )

    assert result.status is ClosedCandleWindowStatus.AVAILABLE
    assert result.candles[-1].quote_volume == Decimal("1743")
    assert len(exchange.calls) == 2
