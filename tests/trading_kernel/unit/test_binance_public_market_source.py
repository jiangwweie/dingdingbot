from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from src.trading_kernel.application.market_ports import ClosedCandleRequest
from src.trading_kernel.infrastructure.binance_public_market_source import (
    CcxtBinancePublicMarketSource,
)


class FakeExchange:
    def __init__(self, rows: list[list[object]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, str, int, int]] = []

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since=None,
        limit: int | None = None,
    ) -> list[list[object]]:
        self.calls.append((symbol, timeframe, int(since or 0), int(limit or 0)))
        return self.rows


class SlowExchange:
    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since=None,
        limit: int | None = None,
    ) -> list[list[object]]:
        await asyncio.sleep(0.05)
        return []


class NativeKlineExchange:
    def __init__(self, rows: list[list[object]]) -> None:
        self.rows = rows
        self.params: list[dict[str, object]] = []

    def fapiPublicGetKlines(
        self,
        params: dict[str, object],
    ) -> list[list[object]]:
        self.params.append(params)
        return self.rows

    def fetch_ohlcv(self, *args: object) -> object:
        raise AssertionError("native kline endpoint must carry quote volume")


@pytest.mark.asyncio
async def test_public_source_returns_only_last_requested_closed_candles() -> None:
    duration_ms = 900_000
    closed_at_ms = 10_000_000
    rows = [
        [
            closed_at_ms - (6 - index) * duration_ms,
            "100",
            "110",
            "99",
            str(100 + index),
            "10",
        ]
        for index in range(7)
    ]
    exchange = FakeExchange(rows)
    source = CcxtBinancePublicMarketSource(
        exchange=exchange,
        venue_symbols={"binance-usdm:ETHUSDT:perpetual": "ETH/USDT:USDT"},
        timeout_seconds=1,
    )

    candles = await source.fetch_closed_candles(
        ClosedCandleRequest(
            exchange_instrument_id="binance-usdm:ETHUSDT:perpetual",
            timeframe="15m",
            limit=5,
            closed_at_ms=closed_at_ms,
        )
    )

    assert len(candles) == 5
    assert candles[-1].close_time_ms == closed_at_ms
    assert exchange.calls == [
        ("ETH/USDT:USDT", "15m", closed_at_ms - 6 * duration_ms, 6)
    ]


@pytest.mark.asyncio
async def test_public_source_bounds_exchange_timeout() -> None:
    source = CcxtBinancePublicMarketSource(
        exchange=SlowExchange(),
        venue_symbols={"binance-usdm:ETHUSDT:perpetual": "ETH/USDT:USDT"},
        timeout_seconds=0.001,
    )

    with pytest.raises(TimeoutError):
        await source.fetch_closed_candles(
            ClosedCandleRequest(
                exchange_instrument_id="binance-usdm:ETHUSDT:perpetual",
                timeframe="1h",
                limit=25,
                closed_at_ms=10_000_000,
            )
        )


@pytest.mark.asyncio
async def test_native_kline_endpoint_preserves_quote_volume_and_dynamic_symbol() -> None:
    duration_ms = 3_600_000
    closed_at_ms = 20_000_000
    open_time_ms = closed_at_ms - duration_ms
    exchange = NativeKlineExchange(
        [
            [
                open_time_ms,
                "100",
                "110",
                "99",
                "105",
                "10",
                closed_at_ms - 1,
                "1042.5",
            ]
        ]
    )
    source = CcxtBinancePublicMarketSource(
        exchange=exchange,
        venue_symbols={},
        timeout_seconds=1,
    )

    candles = await source.fetch_closed_candles(
        ClosedCandleRequest(
            exchange_instrument_id="binance-usdm:MSTRUSDT:perpetual",
            timeframe="1h",
            limit=1,
            closed_at_ms=closed_at_ms,
        )
    )

    assert candles[0].quote_volume == Decimal("1042.5")
    assert exchange.params == [
        {
            "symbol": "MSTRUSDT",
            "interval": "1h",
            "startTime": closed_at_ms - 2 * duration_ms,
            "endTime": closed_at_ms - 1,
            "limit": 2,
        }
    ]
