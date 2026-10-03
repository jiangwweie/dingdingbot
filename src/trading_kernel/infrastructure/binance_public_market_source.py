"""Timeout-bounded CCXT Binance USD-M closed-candle source."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Mapping
from decimal import Decimal
from typing import Protocol

from ccxt.base import errors as ccxt_errors  # type: ignore[import-untyped]

from src.trading_kernel.application.market_ports import (
    ClosedCandleRequest,
    GenericSelectionKlineRequest,
    SelectionKlineRequest,
)
from src.trading_kernel.domain.generic_selection_jobs import (
    GenericSelectionSourceTemporarilyUnavailable,
)
from src.trading_kernel.domain.generic_selection_source import (
    GenericSelectionCandle,
    GenericSelectionQualification,
)
from src.trading_kernel.domain.instrument_identity import (
    parse_binance_usdm_instrument_id,
    to_ccxt_symbol,
)
from src.trading_kernel.domain.instrument_selection import (
    INTERVAL_MS,
    SelectionKline,
    SelectionSourceIntegrityError,
)
from src.trading_kernel.domain.market import ClosedCandle, Timeframe
from src.trading_kernel.domain.product import (
    InstrumentProductProfile,
    ProductSessionSnapshot,
)
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

    def fapiPublicGetKlines(self, params: object = None) -> object: ...


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
        self._product_cache_key: tuple[tuple[str, ...], int] | None = None
        self._product_cache_value: tuple[ProductSessionSnapshot, ...] = ()

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

    async def fetch_selection_klines(
        self,
        request: SelectionKlineRequest,
    ) -> tuple[SelectionKline, ...]:
        identity = parse_binance_usdm_instrument_id(
            request.exchange_instrument_id
        )
        response = await self._raw_public(
            self._exchange.fapiPublicGetKlines,
            {
                "symbol": identity.symbol,
                "interval": "15m",
                "startTime": request.input_window_start_ms,
                "endTime": request.feature_cutoff_at_ms - 1,
                "limit": request.expected_bars,
            },
        )
        if not isinstance(response, list) or len(response) != request.expected_bars:
            raise SelectionSourceIntegrityError(
                "Binance Selection source returned an incomplete Kline window"
            )
        klines = tuple(_parse_selection_row(row) for row in response)
        expected_times = tuple(
            request.input_window_start_ms + index * INTERVAL_MS
            for index in range(request.expected_bars)
        )
        if tuple(item.open_time_ms for item in klines) != expected_times:
            raise SelectionSourceIntegrityError(
                "Binance Selection source returned duplicate or irregular Klines"
            )
        if klines[-1].close_time_ms != request.feature_cutoff_at_ms:
            raise SelectionSourceIntegrityError(
                "Binance Selection source returned a future or open Kline"
            )
        return klines

    async def fetch_generic_selection_klines(self, request: GenericSelectionKlineRequest) -> tuple[GenericSelectionCandle, ...]:
        request = GenericSelectionKlineRequest.model_validate(request.model_dump())
        identity = parse_binance_usdm_instrument_id(request.exchange_instrument_id)
        try:
            response = await self._raw_public(self._exchange.fapiPublicGetKlines, {
                "symbol": identity.symbol, "interval": "1h", "startTime": request.input_window_start_ms,
                "endTime": request.feature_cutoff_at_ms - 1, "limit": request.expected_bars,
            })
        except ccxt_errors.NetworkError as exc:
            reason = "public_market_rate_limited" if isinstance(exc, ccxt_errors.RateLimitExceeded) else "public_market_network_unavailable"
            raise GenericSelectionSourceTemporarilyUnavailable(reason,
                retry_after_ms=_public_retry_after_ms(exc, self._exchange)) from exc
        if not isinstance(response, list) or len(response) != request.expected_bars:
            raise SelectionSourceIntegrityError("Generic Selection source window is incomplete")
        candles = tuple(_parse_generic_selection_row(row) for row in response)
        if tuple(c.open_time_ms for c in candles) != tuple(request.input_window_start_ms + i * 3600000 for i in range(request.expected_bars)):
            raise SelectionSourceIntegrityError("Generic Selection source has duplicate, future or irregular candles")
        return candles

    async def fetch_generic_selection_qualifications(
        self, *, event_spec_id: str, product_profiles: tuple[InstrumentProductProfile, ...], observed_at_ms: int,
    ) -> tuple[GenericSelectionQualification, ...]:
        if len(product_profiles) != 24 or len({p.exchange_instrument_id for p in product_profiles}) != 24:
            raise SelectionSourceIntegrityError("Generic qualification requires complete Candidate24 profiles")
        try:
            response = await self._raw_public(self._exchange.fapiPublicGetExchangeInfo, {})
        except ccxt_errors.NetworkError as exc:
            reason = "public_market_rate_limited" if isinstance(exc, ccxt_errors.RateLimitExceeded) else "public_market_network_unavailable"
            raise GenericSelectionSourceTemporarilyUnavailable(reason,
                retry_after_ms=_public_retry_after_ms(exc, self._exchange)) from exc
        if not isinstance(response, Mapping) or not isinstance(response.get("symbols"), list):
            raise SelectionSourceIntegrityError("Generic qualification lacks venue product facts")
        requested = {parse_binance_usdm_instrument_id(p.exchange_instrument_id).symbol for p in product_profiles}
        selected = [row for row in response["symbols"] if isinstance(row, Mapping) and row.get("symbol") in requested]
        if len(selected) != 24 or len({row["symbol"] for row in selected}) != 24:
            raise SelectionSourceIntegrityError("Generic qualification has missing or duplicate venue members")
        by_symbol = {row["symbol"]: row for row in selected}
        result = []
        for profile in product_profiles:
            row = by_symbol[parse_binance_usdm_instrument_id(profile.exchange_instrument_id).symbol]
            result.append(GenericSelectionQualification.model_validate({
                "event_spec_id": event_spec_id, "product_profile": profile,
                "venue_contract_type": row.get("contractType"), "venue_margin_asset": row.get("marginAsset"),
                "venue_status": row.get("status"), "observed_at_ms": observed_at_ms,
            }))
        return tuple(result)

    async def fetch_product_sessions(
        self,
        exchange_instrument_ids: tuple[str, ...],
        *,
        observed_at_ms: int,
    ) -> tuple[ProductSessionSnapshot, ...]:
        if not 1 <= len(exchange_instrument_ids) <= 10:
            raise ValueError("product refresh requires between one and ten instruments")
        cache_key = (exchange_instrument_ids, observed_at_ms)
        if cache_key == self._product_cache_key:
            return self._product_cache_value
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
        snapshots = parse_binance_product_snapshots(
            exchange_instrument_ids=exchange_instrument_ids,
            exchange_info=exchange_info,
            trading_schedule=trading_schedule,
            premium_index=premium_index,
            depth_by_symbol=depth_by_symbol,
            observed_at_ms=observed_at_ms,
        )
        self._product_cache_key = cache_key
        self._product_cache_value = snapshots
        return snapshots

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


def _public_retry_after_ms(error: Exception, exchange: _CcxtPublicExchange) -> int | None:
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None)
    if not isinstance(headers, Mapping):
        headers = getattr(exchange, "last_response_headers", None)
    if not isinstance(headers, Mapping):
        return None
    raw = next((value for key, value in headers.items()
        if str(key).lower() == "retry-after"), None)
    try:
        seconds = int(str(raw))
    except (TypeError, ValueError):
        return None
    return seconds * 1000 if 0 <= seconds <= 600 else None


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


def _parse_selection_row(row: object) -> SelectionKline:
    if not isinstance(row, (list, tuple)) or len(row) < 8:
        raise SelectionSourceIntegrityError(
            "Binance raw Selection Kline row is malformed"
        )
    if any(isinstance(row[index], float) for index in (1, 2, 3, 4, 7)):
        raise SelectionSourceIntegrityError(
            "Binance raw Selection numeric values cannot enter through float"
        )
    open_time_ms = int(row[0])
    raw_close_time_ms = int(row[6])
    if raw_close_time_ms != open_time_ms + INTERVAL_MS - 1:
        raise SelectionSourceIntegrityError(
            "Binance raw Selection Kline close boundary is invalid"
        )
    return SelectionKline(
        open_time_ms=open_time_ms,
        close_time_ms=open_time_ms + INTERVAL_MS,
        open=Decimal(row[1]),
        high=Decimal(row[2]),
        low=Decimal(row[3]),
        close=Decimal(row[4]),
        quote_volume=Decimal(row[7]),
    )


def _parse_generic_selection_row(row: object) -> GenericSelectionCandle:
    if not isinstance(row, (list, tuple)) or len(row) < 8:
        raise SelectionSourceIntegrityError("Generic raw Kline row is malformed")
    if any(not isinstance(row[i], str) for i in (1, 2, 3, 4, 5, 7)):
        raise SelectionSourceIntegrityError("Generic raw OHLCV must enter from decimal strings")
    if type(row[0]) is not int or type(row[6]) is not int or row[6] != row[0] + 3600000 - 1:
        raise SelectionSourceIntegrityError("Generic raw Kline close boundary is invalid")
    return GenericSelectionCandle(open_time_ms=row[0], close_time_ms=row[6]+1,
        open=Decimal(row[1]), high=Decimal(row[2]), low=Decimal(row[3]), close=Decimal(row[4]),
        base_volume=Decimal(row[5]), quote_volume=Decimal(row[7]))
