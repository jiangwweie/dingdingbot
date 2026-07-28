"""Bounded read-only BNB commission valuation from Binance USD-M index candles."""

from __future__ import annotations

import inspect
from collections.abc import Sequence
from decimal import Decimal

from src.trading_kernel.domain.fee_valuation import FeeValuationEvidence


_MAX_CANDLE_STALENESS_MS = 120_000
_ONE_MINUTE_MS = 60_000


async def read_bnbusdt_fee_valuation_evidence(
    *,
    exchange: object,
    trade_occurred_at_ms: int,
) -> FeeValuationEvidence:
    """Read the latest completed BNBUSDT one-minute index candle for one trade."""

    if trade_occurred_at_ms <= 0:
        raise ValueError("trade time must be positive")
    fetch = getattr(exchange, "fapiPublicGetIndexPriceKlines", None)
    if not callable(fetch):
        raise RuntimeError("Binance venue lacks BNBUSDT index kline lookup")
    response = fetch(
        {
            "pair": "BNBUSDT",
            "symbol": "BNBUSDT",
            "interval": "1m",
            "startTime": trade_occurred_at_ms - _MAX_CANDLE_STALENESS_MS - _ONE_MINUTE_MS,
            "endTime": trade_occurred_at_ms,
            "limit": 4,
        }
    )
    if inspect.isawaitable(response):
        response = await response
    if not isinstance(response, Sequence) or isinstance(response, (str, bytes, bytearray)):
        raise RuntimeError("Binance BNBUSDT index kline response is not a list")

    candidates: list[tuple[int, int, Decimal]] = []
    for row in response:
        if not isinstance(row, Sequence) or isinstance(row, (str, bytes, bytearray)):
            raise RuntimeError("Binance index kline row is not a sequence")
        if len(row) < 7:
            raise RuntimeError("Binance index kline row is incomplete")
        open_time_ms = int(row[0])
        close_price = Decimal(str(row[4]))
        close_time_ms = int(row[6])
        if close_price <= 0:
            raise RuntimeError("Binance index kline close is non-positive")
        if open_time_ms <= 0 or close_time_ms <= open_time_ms:
            raise RuntimeError("Binance index kline time window is invalid")
        if close_time_ms <= trade_occurred_at_ms:
            candidates.append((open_time_ms, close_time_ms, close_price))
    if not candidates:
        raise RuntimeError("Binance BNBUSDT has no completed index candle")
    open_time_ms, close_time_ms, close_price = max(candidates, key=lambda item: item[1])
    if trade_occurred_at_ms - close_time_ms > _MAX_CANDLE_STALENESS_MS:
        raise RuntimeError("Binance BNBUSDT completed index candle is stale")
    return FeeValuationEvidence(
        method="binance_usdm_bnbusdt_index_1m_previous_close",
        rate_usdt_per_asset=close_price,
        price_pair="BNBUSDT",
        candle_open_time_ms=open_time_ms,
        candle_close_time_ms=close_time_ms,
        valued_at_ms=trade_occurred_at_ms,
    )
