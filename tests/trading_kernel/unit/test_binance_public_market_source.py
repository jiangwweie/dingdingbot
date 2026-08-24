from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from typing import cast

import pytest

from src.trading_kernel.application.market_ports import (
    ClosedCandleRequest,
    SelectionKlineRequest,
)
from src.trading_kernel.infrastructure.binance_public_market_source import (
    CcxtBinancePublicMarketSource,
)


class FakeExchange:
    def __init__(self, rows: list[list[object]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, str, int | None, int]] = []

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since=None,
        limit: int | None = None,
    ) -> list[list[object]]:
        self.calls.append((symbol, timeframe, since, int(limit or 0)))
        return self.rows

    async def close(self) -> None:
        return None


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

    async def close(self) -> None:
        return None


class ProductExchange(FakeExchange):
    def __init__(self) -> None:
        super().__init__([])
        self.product_calls = 0

    def fapiPublicGetExchangeInfo(self, params=None):
        self.product_calls += 1
        return {"symbols": [{"symbol": "AAPLUSDT", "contractType": "TRADIFI_PERPETUAL", "underlyingType": "EQUITY", "marginAsset": "USDT", "status": "TRADING"}]}

    def fapiPublicGetTradingSchedule(self, params=None):
        self.product_calls += 1
        return {"data": [{"symbol": "AAPLUSDT", "tradingSessions": [{"session": "REGULAR", "startTime": 1_799_999_000_000, "endTime": 1_800_010_000_000}]}]}

    def fapiPublicGetPremiumIndex(self, params=None):
        self.product_calls += 1
        return [{"symbol": "AAPLUSDT", "markPrice": "100", "indexPrice": "100", "lastFundingRate": "0"}]

    def fapiPublicGetDepth(self, params=None):
        self.product_calls += 1
        return {"bids": [["99.9", "10"]], "asks": [["100", "9"]]}


class RawKlineExchange(FakeExchange):
    def __init__(self, rows: list[list[object]]) -> None:
        super().__init__([])
        self.raw_rows = rows
        self.raw_calls: list[dict[str, object]] = []

    def fapiPublicGetKlines(self, params=None):
        self.raw_calls.append(dict(params or {}))
        return self.raw_rows


def test_public_market_source_rejects_retired_venue_symbol_map() -> None:
    assert "venue_symbols" not in inspect.signature(
        CcxtBinancePublicMarketSource
    ).parameters

    with pytest.raises(TypeError, match="venue_symbols"):
        cast(Callable[..., CcxtBinancePublicMarketSource], CcxtBinancePublicMarketSource)(
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
    assert exchange.calls == [("ETH/USDT:USDT", "15m", None, 6)]


@pytest.mark.asyncio
async def test_public_source_forwards_frozen_historical_since_bound() -> None:
    exchange = FakeExchange([])
    source = CcxtBinancePublicMarketSource(
        exchange=exchange,
        timeout_seconds=1,
    )

    await source.fetch_closed_candles(
        ClosedCandleRequest(
            exchange_instrument_id="binance-usdm:ETHUSDT:perpetual",
            timeframe="1h",
            limit=24,
            closed_at_ms=90_000_000,
            since_ms=3_600_000,
        )
    )

    assert exchange.calls == [("ETH/USDT:USDT", "1h", 3_600_000, 25)]


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


@pytest.mark.asyncio
async def test_selection_source_uses_raw_quote_volume_not_base_volume() -> None:
    start_ms = 1_704_067_200_000
    rows = [
        [
            start_ms + index * 900_000,
            "100",
            "101",
            "99",
            "100",
            "999999999",  # base volume must not enter Selection activity
            start_ms + (index + 1) * 900_000 - 1,
            str(index + 1),  # quote asset volume
        ]
        for index in range(96)
    ]
    exchange = RawKlineExchange(rows)
    source = CcxtBinancePublicMarketSource(exchange=exchange, timeout_seconds=1)

    klines = await source.fetch_selection_klines(
        SelectionKlineRequest(
            exchange_instrument_id="binance-usdm:ETHUSDT:perpetual",
            input_window_start_ms=start_ms,
            feature_cutoff_at_ms=start_ms + 96 * 900_000,
        )
    )

    assert len(klines) == 96
    assert klines[0].quote_volume == 1
    assert klines[-1].quote_volume == 96
    assert exchange.raw_calls == [
        {
            "symbol": "ETHUSDT",
            "interval": "15m",
            "startTime": start_ms,
            "endTime": start_ms + 96 * 900_000 - 1,
            "limit": 96,
        }
    ]


@pytest.mark.asyncio
async def test_product_snapshot_reuses_exact_same_bar_universe_read() -> None:
    exchange = ProductExchange()
    source = CcxtBinancePublicMarketSource(exchange=exchange, timeout_seconds=1)
    instruments = ("binance-usdm:AAPLUSDT:perpetual",)

    first = await source.fetch_product_sessions(
        instruments,
        observed_at_ms=1_800_000_000_000,
    )
    second = await source.fetch_product_sessions(
        instruments,
        observed_at_ms=1_800_000_000_000,
    )

    assert first == second
    assert exchange.product_calls == 4
