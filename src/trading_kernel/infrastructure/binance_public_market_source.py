"""Timeout-bounded CCXT Binance USD-M closed-candle source."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Mapping
from decimal import Decimal
from typing import Protocol

from src.trading_kernel.application.market_ports import ClosedCandleRequest
from src.trading_kernel.domain.instrument_identity import (
    parse_binance_usdm_instrument_id,
    to_ccxt_symbol,
)
from src.trading_kernel.domain.market import ClosedCandle, Timeframe
from src.trading_kernel.domain.product import ProductSessionSnapshot
from src.trading_kernel.infrastructure.binance_product_snapshot import (
    parse_binance_product_snapshots,
)


class _CcxtPublicExchange(Protocol):
    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: object = None,
        limit: int | None = None,
    ) -> object: ...

    def close(self) -> object: ...

    def fapiPublicGetExchangeInfo(self, params: object = None) -> object: ...

    def fapiPublicGetTradingSchedule(self, params: object = None) -> object: ...

    def fapiPublicGetPremiumIndex(self, params: object = None) -> object: ...

    def fapiPublicGetDepth(self, params: object = None) -> object: ...


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
        timeout_seconds: float,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("public market timeout must be positive")
        self._exchange = exchange
        self._timeout_seconds = timeout_seconds

    async def fetch_closed_candles(
        self,
        request: ClosedCandleRequest,
    ) -> tuple[ClosedCandle, ...]:
        try:
            symbol = to_ccxt_symbol(
                parse_binance_usdm_instrument_id(request.exchange_instrument_id)
            )
        except ValueError as exc:
            raise RuntimeError(
                "canonical instrument has no public venue symbol"
            ) from exc
        response = await asyncio.wait_for(
            self._fetch(symbol, request),
            timeout=self._timeout_seconds,
        )
        if not isinstance(response, list):
            raise TypeError("public OHLCV response is not a list")
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

    async def fetch_product_sessions(
        self,
        exchange_instrument_ids: tuple[str, ...],
        *,
        observed_at_ms: int,
    ) -> tuple[ProductSessionSnapshot, ...]:
        if not 1 <= len(exchange_instrument_ids) <= 10:
            raise ValueError("product refresh requires between one and ten instruments")
        symbols = tuple(
            parse_binance_usdm_instrument_id(item).symbol
            for item in exchange_instrument_ids
        )
        exchange_info, trading_schedule, premium_index = await asyncio.gather(
            self._raw_public(self._exchange.fapiPublicGetExchangeInfo, {}),
            self._raw_public(self._exchange.fapiPublicGetTradingSchedule, {}),
            self._raw_public(self._exchange.fapiPublicGetPremiumIndex, {}),
        )
        depth_results = await asyncio.gather(
            *(
                self._raw_public(
                    self._exchange.fapiPublicGetDepth,
                    {"symbol": symbol, "limit": 5},
                )
                for symbol in symbols
            ),
            return_exceptions=True,
        )
        depth_by_symbol = {
            symbol: result
            for symbol, result in zip(symbols, depth_results, strict=True)
            if not isinstance(result, BaseException)
        }
        return parse_binance_product_snapshots(
            exchange_instrument_ids=exchange_instrument_ids,
            exchange_info=exchange_info,
            trading_schedule=trading_schedule,
            premium_index=premium_index,
            depth_by_symbol=depth_by_symbol,
            observed_at_ms=observed_at_ms,
        )

    async def _fetch(
        self,
        symbol: str,
        request: ClosedCandleRequest,
    ) -> object:
        operation = self._exchange.fetch_ohlcv
        args = (symbol, request.timeframe, request.since_ms, request.limit + 1)
        if inspect.iscoroutinefunction(operation):
            return await operation(*args)
        return await asyncio.to_thread(operation, *args)

    async def _raw_public(self, operation: object, params: object) -> object:
        if not callable(operation):
            raise TypeError("Binance public product operation is unavailable")
        if inspect.iscoroutinefunction(operation):
            return await asyncio.wait_for(
                operation(params),
                timeout=self._timeout_seconds,
            )
        response = await asyncio.wait_for(
            asyncio.to_thread(operation, params),
            timeout=self._timeout_seconds,
        )
        return await response if inspect.isawaitable(response) else response


def _parse_row(row: object, duration_ms: int) -> ClosedCandle:
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
    )
