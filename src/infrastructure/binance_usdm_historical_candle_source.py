"""Bounded read-only Binance USD-M public historical candle source."""

from __future__ import annotations

import json
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_URL = "https://fapi.binance.com/fapi/v1/klines"
TIMEFRAME_MS = {
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
}

Requester = Callable[[str, float], Any]


class BinanceUsdMPublicHistoricalCandleSource:
    """Fetch only public closed klines; never touches account or order APIs."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 15,
        page_limit: int = 1000,
        max_pages: int = 1000,
        requester: Requester | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("positive_timeout_required")
        if page_limit < 1 or page_limit > 1500:
            raise ValueError("binance_page_limit_out_of_range")
        if max_pages < 1:
            raise ValueError("positive_max_pages_required")
        self._timeout_seconds = float(timeout_seconds)
        self._page_limit = int(page_limit)
        self._max_pages = int(max_pages)
        self._requester = requester or _request_json

    def fetch_closed_candles(
        self,
        *,
        symbol: str,
        timeframe: str,
        start_time_ms: int,
        end_time_ms: int,
    ) -> list[dict[str, Any]]:
        interval_ms = TIMEFRAME_MS.get(timeframe)
        if interval_ms is None:
            raise ValueError(f"unsupported_binance_timeframe:{timeframe}")
        normalized_symbol = str(symbol or "").strip().upper()
        if not normalized_symbol.endswith("USDT") or not normalized_symbol.isalnum():
            raise ValueError("invalid_binance_usdm_symbol")
        if start_time_ms < 0 or end_time_ms < start_time_ms:
            raise ValueError("invalid_historical_candle_window")

        cursor = int(start_time_ms)
        by_open_time: dict[int, dict[str, Any]] = {}
        for _ in range(self._max_pages):
            url = BASE_URL + "?" + urlencode(
                {
                    "symbol": normalized_symbol,
                    "interval": timeframe,
                    "startTime": cursor,
                    "endTime": int(end_time_ms),
                    "limit": self._page_limit,
                }
            )
            payload = self._requester(url, self._timeout_seconds)
            if not isinstance(payload, list):
                raise RuntimeError("binance_historical_candle_payload_invalid")
            if not payload:
                break
            last_open_time_ms: int | None = None
            for raw in payload:
                row = _normalize_row(raw)
                last_open_time_ms = int(row["open_time_ms"])
                if int(row["close_time_ms"]) <= end_time_ms:
                    by_open_time[last_open_time_ms] = row
            if last_open_time_ms is None:
                raise RuntimeError("binance_historical_candle_page_empty_rows")
            next_cursor = last_open_time_ms + interval_ms
            if next_cursor <= cursor:
                raise RuntimeError("binance_historical_candle_cursor_not_advancing")
            if len(payload) < self._page_limit or last_open_time_ms >= end_time_ms:
                break
            cursor = next_cursor
        else:
            raise RuntimeError("binance_historical_candle_max_pages_exceeded")
        return [by_open_time[key] for key in sorted(by_open_time)]


def _normalize_row(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, (list, tuple)) or len(raw) < 7:
        raise RuntimeError("binance_historical_candle_row_invalid")
    return {
        "open_time_ms": int(raw[0]),
        "open": str(raw[1]),
        "high": str(raw[2]),
        "low": str(raw[3]),
        "close": str(raw[4]),
        "volume": str(raw[5]),
        "close_time_ms": int(raw[6]),
    }


def _request_json(url: str, timeout_seconds: float) -> Any:
    request = Request(
        url,
        headers={"User-Agent": "brc-ofc-historical-replay/1.0"},
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))
