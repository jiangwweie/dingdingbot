"""Timeout-bounded CCXT Binance USD-M closed-candle source."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from decimal import Decimal
import inspect
from typing import Protocol

from src.trading_kernel.application.market_ports import ClosedCandleRequest
from src.trading_kernel.domain.market import ClosedCandle, Timeframe


class _CcxtPublicExchange(Protocol):
    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: object = None,
        limit: int | None = None,
    ) -> object: ...


_TIMEFRAME_MS: Mapping[Timeframe, int] = {
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
}


class CcxtBinancePublicMarketSource:
    def __init__(
        self,
        *,
        exchange: _CcxtPublicExchange,
        venue_symbols: Mapping[str, str],
        timeout_seconds: float,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("public market timeout must be positive")
        self._exchange = exchange
        self._venue_symbols = dict(venue_symbols)
        self._timeout_seconds = timeout_seconds

    async def fetch_closed_candles(
        self,
        request: ClosedCandleRequest,
    ) -> tuple[ClosedCandle, ...]:
        symbol = self._venue_symbols.get(request.exchange_instrument_id)
        if not symbol:
            raise RuntimeError("canonical instrument has no public venue symbol")
        response = await asyncio.wait_for(
            self._fetch(symbol, request),
            timeout=self._timeout_seconds,
        )
        if not isinstance(response, list):
            raise RuntimeError("public OHLCV response is not a list")
        duration_ms = _TIMEFRAME_MS[request.timeframe]
        candles = tuple(
            sorted(
                (_parse_row(row, duration_ms) for row in response),
                key=lambda item: item.open_time_ms,
            )
        )
        closed = tuple(
            item
            for item in candles
            if item.close_time_ms <= request.closed_at_ms
        )
        return closed[-request.limit :]

    async def _fetch(
        self,
        symbol: str,
        request: ClosedCandleRequest,
    ) -> object:
        operation = self._exchange.fetch_ohlcv
        args = (symbol, request.timeframe, None, request.limit + 1)
        if inspect.iscoroutinefunction(operation):
            return await operation(*args)
        return await asyncio.to_thread(operation, *args)


def _parse_row(row: object, duration_ms: int) -> ClosedCandle:
    if not isinstance(row, (list, tuple)) or len(row) < 6:
        raise ValueError("public OHLCV row is malformed")
    open_time_ms = int(row[0])
    return ClosedCandle(
        open_time_ms=open_time_ms,
        close_time_ms=open_time_ms + duration_ms - 1,
        open=Decimal(str(row[1])),
        high=Decimal(str(row[2])),
        low=Decimal(str(row[3])),
        close=Decimal(str(row[4])),
        volume=Decimal(str(row[5])),
    )
