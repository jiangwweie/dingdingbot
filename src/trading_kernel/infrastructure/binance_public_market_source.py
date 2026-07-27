"""Timeout-bounded CCXT Binance USD-M closed-candle source."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from decimal import Decimal
import inspect
from typing import Protocol

from src.trading_kernel.application.market_ports import (
    ClosedCandlePage,
    ClosedCandlePageRequest,
    ClosedCandleRequest,
)
from src.trading_kernel.domain.market import ClosedCandle, Timeframe


class _CcxtPublicExchange(Protocol):
    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: object = None,
        limit: int | None = None,
    ) -> object: ...

    def close(self) -> object: ...


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
        page = await self.fetch_closed_candle_page(
            ClosedCandlePageRequest(
                exchange_instrument_id=request.exchange_instrument_id,
                timeframe=request.timeframe,
                page_limit=request.limit,
                before_close_time_ms=request.closed_at_ms,
            )
        )
        return page.candles

    async def fetch_closed_candle_page(
        self,
        request: ClosedCandlePageRequest,
    ) -> ClosedCandlePage:
        symbol = self._symbol_for(request.exchange_instrument_id)
        response, native = await asyncio.wait_for(
            self._fetch_page(symbol, request),
            timeout=self._timeout_seconds,
        )
        if not isinstance(response, list):
            raise RuntimeError("public OHLCV response is not a list")
        duration_ms = _TIMEFRAME_MS[request.timeframe]
        candles = tuple(
            sorted(
                (_parse_row(row, duration_ms, native=native) for row in response),
                key=lambda item: item.open_time_ms,
            )
        )
        closed = tuple(
            item
            for item in candles
            if item.close_time_ms <= request.before_close_time_ms
        )
        selected = closed[-request.page_limit :]
        return ClosedCandlePage(
            exchange_instrument_id=request.exchange_instrument_id,
            timeframe=request.timeframe,
            candles=selected,
            next_before_close_time_ms=(
                None
                if not selected
                else selected[0].close_time_ms - duration_ms
            ),
        )

    async def close(self) -> None:
        operation = getattr(self._exchange, "close", None)
        if not callable(operation):
            return
        if inspect.iscoroutinefunction(operation):
            await operation()
            return
        response = await asyncio.to_thread(operation)
        if inspect.isawaitable(response):
            await response

    async def _fetch_page(
        self,
        symbol: str,
        request: ClosedCandlePageRequest,
    ) -> tuple[object, bool]:
        duration_ms = _TIMEFRAME_MS[request.timeframe]
        since = (
            request.before_close_time_ms
            - (request.page_limit + 1) * duration_ms
        )
        native_operation = getattr(
            self._exchange,
            "fapiPublicGetKlines",
            None,
        )
        if callable(native_operation):
            raw_symbol = symbol.split("/", 1)[0] + "USDT"
            params = {
                "symbol": raw_symbol,
                "interval": request.timeframe,
                "startTime": max(0, since),
                "endTime": request.before_close_time_ms - 1,
                "limit": request.page_limit + 1,
            }
            if inspect.iscoroutinefunction(native_operation):
                return await native_operation(params), True
            return await asyncio.to_thread(native_operation, params), True
        operation = self._exchange.fetch_ohlcv
        args = (symbol, request.timeframe, max(0, since), request.page_limit + 1)
        if inspect.iscoroutinefunction(operation):
            return await operation(*args), False
        return await asyncio.to_thread(operation, *args), False

    def _symbol_for(self, exchange_instrument_id: str) -> str:
        configured = self._venue_symbols.get(exchange_instrument_id)
        if configured:
            return configured
        prefix = "binance-usdm:"
        suffix = ":perpetual"
        if (
            not exchange_instrument_id.startswith(prefix)
            or not exchange_instrument_id.endswith(suffix)
        ):
            raise RuntimeError("canonical instrument has no public venue symbol")
        venue_symbol = exchange_instrument_id[
            len(prefix) : -len(suffix)
        ]
        if not venue_symbol.endswith("USDT") or len(venue_symbol) <= 4:
            raise RuntimeError("canonical instrument has no public venue symbol")
        return f"{venue_symbol[:-4]}/USDT:USDT"


def _parse_row(
    row: object,
    duration_ms: int,
    *,
    native: bool,
) -> ClosedCandle:
    if not isinstance(row, (list, tuple)) or len(row) < 6:
        raise ValueError("public OHLCV row is malformed")
    open_time_ms = int(row[0])
    return ClosedCandle(
        open_time_ms=open_time_ms,
        close_time_ms=open_time_ms + duration_ms,
        open=Decimal(str(row[1])),
        high=Decimal(str(row[2])),
        low=Decimal(str(row[3])),
        close=Decimal(str(row[4])),
        volume=Decimal(str(row[5])),
        quote_volume=(
            Decimal(str(row[7]))
            if native and len(row) >= 8
            else None
        ),
    )
