"""Public Binance USD-M kline source for read-only strategy observations."""

from __future__ import annotations

import json
import time
from decimal import Decimal
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.application.strategy_group_live_readonly_observation import RecentCandle


class BinancePublicKlineMarketSource:
    """Read latest closed Binance USD-M klines through public HTTP only.

    This adapter intentionally has no API key, account, order, leverage,
    transfer, withdrawal, or exchange-gateway dependency. It exposes only the
    closed-candle method required by the observation evaluator.
    """

    source_id = "binance_usdm_public_klines_read_only"
    source_type = "live_market_read_only"
    freshness = "latest_closed_public_kline"
    is_live_read_only = True
    fallback_used = False

    _BASE_URL = "https://fapi.binance.com/fapi/v1/klines"
    _TIMEFRAME_MS = {
        "1h": 60 * 60 * 1000,
        "4h": 4 * 60 * 60 * 1000,
    }

    def __init__(
        self,
        *,
        base_url: str = _BASE_URL,
        timeout_seconds: float = 10.0,
        now_ms: Callable[[], int] | None = None,
        transport: Callable[[str, float], list] | None = None,
    ) -> None:
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds
        self._now_ms = now_ms or (lambda: int(time.time() * 1000))
        self._transport = transport or self._default_transport

    def latest_closed_candles(self, *, symbol: str, timeframe: str, limit: int) -> list[RecentCandle]:
        if limit <= 0:
            return []
        if timeframe not in self._TIMEFRAME_MS:
            raise ValueError(f"unsupported Binance public kline timeframe: {timeframe}")

        binance_symbol = _to_binance_usdm_symbol(symbol)
        # Fetch extra bars because Binance returns the current still-forming
        # candle. We filter by close time and return only fully closed bars.
        query = urlencode({"symbol": binance_symbol, "interval": timeframe, "limit": min(limit + 3, 1500)})
        url = f"{self._base_url}?{query}"
        rows = self._transport(url, self._timeout_seconds)
        now_ms = self._now_ms()
        candles = [_row_to_candle(row) for row in rows]
        closed = [candle for candle in candles if candle.close_time_ms is not None and candle.close_time_ms < now_ms]
        if len(closed) < limit:
            raise ValueError(
                f"insufficient closed Binance public klines for {binance_symbol} {timeframe}: "
                f"{len(closed)} < {limit}"
            )
        return closed[-limit:]

    @staticmethod
    def _default_transport(url: str, timeout_seconds: float) -> list:
        request = Request(url, headers={"User-Agent": "brc-readonly-observation/1.0"})
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - public read-only URL.
            return json.loads(response.read().decode("utf-8"))


def _to_binance_usdm_symbol(symbol: str) -> str:
    if symbol.endswith(":USDT"):
        symbol = symbol[:-5]
    return symbol.replace("/", "").replace("-", "").upper()


def _row_to_candle(row: list) -> RecentCandle:
    return RecentCandle(
        open_time_ms=int(row[0]),
        open=Decimal(str(row[1])),
        high=Decimal(str(row[2])),
        low=Decimal(str(row[3])),
        close=Decimal(str(row[4])),
        volume=Decimal(str(row[5])),
        close_time_ms=int(row[6]),
        is_closed=True,
    )
