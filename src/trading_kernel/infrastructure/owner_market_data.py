"""Bounded credential-free public candles for Owner Console display only."""

from __future__ import annotations

from typing import Protocol

from pydantic import ValidationError

from src.trading_kernel.application.market_ports import ClosedCandleRequest
from src.trading_kernel.application.owner_console.models import (
    CandleQuery,
    CandleSeries,
    CandleView,
)
from src.trading_kernel.domain.market import ClosedCandle
from src.trading_kernel.domain.product import ProductSessionSnapshot


class _ClosedCandleSource(Protocol):
    async def fetch_closed_candles(
        self,
        request: ClosedCandleRequest,
    ) -> tuple[ClosedCandle, ...]: ...

    async def close(self) -> None: ...

    async def fetch_product_sessions(
        self,
        exchange_instrument_ids: tuple[str, ...],
        *,
        observed_at_ms: int,
    ) -> tuple[ProductSessionSnapshot, ...]: ...


class OwnerMarketData:
    """Expose one bounded public candle query without runtime authority."""

    def __init__(self, source: _ClosedCandleSource) -> None:
        self._source = source
        self._closed = False

    async def read_candles(self, request: CandleQuery) -> CandleSeries:
        candles = await self._source.fetch_closed_candles(
            ClosedCandleRequest(
                exchange_instrument_id=request.exchange_instrument_id,
                timeframe=request.timeframe,
                limit=request.limit,
                closed_at_ms=request.closed_at_ms,
            )
        )
        return CandleSeries(
            candles=tuple(
                _to_candle_view(candle, closed_at_ms=request.closed_at_ms)
                for candle in candles
            )
        )

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._source.close()

    async def read_product_sessions(
        self,
        exchange_instrument_ids: tuple[str, ...],
        *,
        observed_at_ms: int,
    ) -> tuple[ProductSessionSnapshot, ...]:
        snapshots = await self._source.fetch_product_sessions(
            exchange_instrument_ids,
            observed_at_ms=observed_at_ms,
        )
        if tuple(item.exchange_instrument_id for item in snapshots) != (
            exchange_instrument_ids
        ):
            raise ValueError("public product snapshots changed requested identity order")
        return tuple(
            ProductSessionSnapshot.model_validate(item.model_dump())
            for item in snapshots
        )


def _to_candle_view(candle: ClosedCandle, *, closed_at_ms: int) -> CandleView:
    try:
        if not isinstance(candle, ClosedCandle):
            raise TypeError("public candle row has an invalid type")
        verified = ClosedCandle.model_validate(candle.model_dump())
    except (TypeError, ValidationError, ValueError) as exc:
        raise ValueError("public candle row is malformed") from exc
    if verified.close_time_ms > closed_at_ms:
        raise ValueError("public candle row closes after requested closed_at_ms")
    return CandleView(
        open_time_ms=verified.open_time_ms,
        close_time_ms=verified.close_time_ms,
        open=str(verified.open),
        high=str(verified.high),
        low=str(verified.low),
        close=str(verified.close),
        volume=str(verified.volume),
    )
