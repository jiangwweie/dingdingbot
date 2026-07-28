from __future__ import annotations

import asyncio
import inspect

import pytest

from src.trading_kernel.application.market_ports import ClosedCandleRequest
from src.trading_kernel.infrastructure.binance_public_market_source import (
    CcxtBinancePublicMarketSource,
)


class FakeExchange:
    def __init__(self, rows: list[list[object]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, str, int]] = []

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since=None,
        limit: int | None = None,
    ) -> list[list[object]]:
        self.calls.append((symbol, timeframe, int(limit or 0)))
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


def test_public_market_source_rejects_retired_venue_symbol_map() -> None:
    assert "venue_symbols" not in inspect.signature(
        CcxtBinancePublicMarketSource
    ).parameters

    with pytest.raises(TypeError, match="venue_symbols"):
        CcxtBinancePublicMarketSource(
            exchange=FakeExchange([]),
            venue_symbols={},
            timeout_seconds=1,
        )


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
    assert exchange.calls == [("ETH/USDT:USDT", "15m", 6)]


@pytest.mark.asyncio
async def test_public_source_bounds_exchange_timeout() -> None:
    source = CcxtBinancePublicMarketSource(
        exchange=SlowExchange(),
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
