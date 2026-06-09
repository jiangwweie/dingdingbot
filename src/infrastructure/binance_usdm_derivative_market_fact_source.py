"""Public Binance USD-M derivative market fact source for B0 semantics."""

from __future__ import annotations

import asyncio
import json
import time
from decimal import Decimal, InvalidOperation
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from src.application.strategy_runtime_fact_overlay_service import (
    StrategyRuntimeMarketFacts,
)


Transport = Callable[[str, float], Any]


class BinanceUsdmDerivativeMarketFactSource:
    """Read funding, open interest, and crowding proxy via public HTTP only.

    This adapter intentionally has no API key, account, order, leverage,
    transfer, withdrawal, or ExchangeGateway dependency. It implements the
    StrategyRuntimeMarketFactSource protocol for the B0 trusted fact overlay.
    """

    source_id = "binance_usdm_derivative_market_facts_read_only"
    source_type = "live_market_read_only"
    is_live_read_only = True
    fallback_used = False

    _BASE_URL = "https://fapi.binance.com"
    _PREMIUM_INDEX_PATH = "/fapi/v1/premiumIndex"
    _OPEN_INTEREST_PATH = "/fapi/v1/openInterest"
    _GLOBAL_LONG_SHORT_RATIO_PATH = "/futures/data/globalLongShortAccountRatio"

    def __init__(
        self,
        *,
        base_url: str = _BASE_URL,
        timeout_seconds: float = 10.0,
        crowding_period: str = "5m",
        funding_max_age_ms: int = 10 * 60 * 1000,
        open_interest_max_age_ms: int = 10 * 60 * 1000,
        crowding_max_age_ms: int = 15 * 60 * 1000,
        now_ms: Callable[[], int] | None = None,
        transport: Transport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._crowding_period = crowding_period
        self._funding_max_age_ms = funding_max_age_ms
        self._open_interest_max_age_ms = open_interest_max_age_ms
        self._crowding_max_age_ms = crowding_max_age_ms
        self._now_ms = now_ms or (lambda: int(time.time() * 1000))
        self._transport = transport or self._default_transport

    async def read_strategy_market_facts(
        self,
        *,
        symbol: str,
        generated_at_ms: int,
    ) -> StrategyRuntimeMarketFacts:
        return await asyncio.to_thread(
            self._read_strategy_market_facts_sync,
            symbol=symbol,
            generated_at_ms=generated_at_ms,
        )

    def _read_strategy_market_facts_sync(
        self,
        *,
        symbol: str,
        generated_at_ms: int,
    ) -> StrategyRuntimeMarketFacts:
        binance_symbol = _to_binance_usdm_symbol(symbol)
        warnings: list[str] = []
        missing_fields: list[str] = []
        stale_fields: list[str] = []
        endpoint_status: dict[str, dict[str, Any]] = {}

        premium = self._safe_read_json(
            "premium_index",
            self._url(self._PREMIUM_INDEX_PATH, {"symbol": binance_symbol}),
            warnings=warnings,
            endpoint_status=endpoint_status,
        )
        funding_rate = _decimal_or_none(_field(premium, "lastFundingRate"))
        next_funding_time_ms = _int_or_none(_field(premium, "nextFundingTime"))
        premium_time_ms = _int_or_none(_field(premium, "time"))
        mark_price = _decimal_or_none(_field(premium, "markPrice"))

        if funding_rate is None:
            missing_fields.append("funding_rate")
        elif _is_stale(premium_time_ms, generated_at_ms, self._funding_max_age_ms):
            stale_fields.append("funding_rate")

        open_interest_payload = self._safe_read_json(
            "open_interest",
            self._url(self._OPEN_INTEREST_PATH, {"symbol": binance_symbol}),
            warnings=warnings,
            endpoint_status=endpoint_status,
        )
        open_interest = _decimal_or_none(_field(open_interest_payload, "openInterest"))
        open_interest_time_ms = _int_or_none(_field(open_interest_payload, "time"))

        if open_interest is None:
            missing_fields.append("open_interest")
        elif _is_stale(open_interest_time_ms, generated_at_ms, self._open_interest_max_age_ms):
            stale_fields.append("open_interest")

        crowding_payload = self._safe_read_json(
            "global_long_short_account_ratio",
            self._url(
                self._GLOBAL_LONG_SHORT_RATIO_PATH,
                {
                    "symbol": binance_symbol,
                    "period": self._crowding_period,
                    "limit": 1,
                },
            ),
            warnings=warnings,
            endpoint_status=endpoint_status,
        )
        crowding_proxy, crowding_time_ms = _crowding_proxy_from_payload(
            crowding_payload,
            source_id=self.source_id,
            period=self._crowding_period,
        )

        if crowding_proxy is None:
            missing_fields.append("crowding_proxy")
        elif _is_stale(crowding_time_ms, generated_at_ms, self._crowding_max_age_ms):
            stale_fields.append("crowding_proxy")

        read_at_ms = self._now_ms()
        fact_timestamps = [
            value
            for value in (premium_time_ms, open_interest_time_ms, crowding_time_ms)
            if value is not None
        ]
        timestamp_ms = max(fact_timestamps) if fact_timestamps else read_at_ms
        open_interest_notional = (
            open_interest * mark_price
            if open_interest is not None and mark_price is not None
            else None
        )
        return StrategyRuntimeMarketFacts(
            source_id=self.source_id,
            timestamp_ms=timestamp_ms,
            freshness="stale" if stale_fields else "partial" if missing_fields else "fresh",
            funding_rate=funding_rate,
            next_funding_time_ms=next_funding_time_ms,
            open_interest=open_interest,
            open_interest_notional=open_interest_notional,
            crowding_proxy=crowding_proxy,
            missing_fields=missing_fields,
            stale_fields=stale_fields,
            warnings=warnings,
            read_only_guarantee=True,
            external_call_type="binance_usdm_public_http_read_only",
            metadata={
                "source_type": self.source_type,
                "binance_symbol": binance_symbol,
                "crowding_period": self._crowding_period,
                "endpoint_status": endpoint_status,
                "read_only_public_http": True,
                "api_key_used": False,
                "exchange_gateway_used": False,
                "fallback_used": self.fallback_used,
                "mark_price": str(mark_price) if mark_price is not None else None,
                "read_at_ms": read_at_ms,
            },
        )

    def _safe_read_json(
        self,
        label: str,
        url: str,
        *,
        warnings: list[str],
        endpoint_status: dict[str, dict[str, Any]],
    ) -> Any:
        try:
            payload = self._transport(url, self._timeout_seconds)
        except HTTPError as exc:
            warnings.append(f"{label}_read_failed:HTTPError:{exc.code}")
            endpoint_status[label] = {
                "status": "read_failed",
                "error_type": "HTTPError",
                "http_status": exc.code,
            }
            return None
        except Exception as exc:
            warnings.append(f"{label}_read_failed:{type(exc).__name__}")
            endpoint_status[label] = {"status": "read_failed", "error_type": type(exc).__name__}
            return None
        endpoint_status[label] = {"status": "available", "url": url}
        return payload

    def _url(self, path: str, query: dict[str, Any]) -> str:
        return f"{self._base_url}{path}?{urlencode(query)}"

    @staticmethod
    def _default_transport(url: str, timeout_seconds: float) -> Any:
        request = Request(url, headers={"User-Agent": "brc-derivative-facts/1.0"})
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - public read-only URL.
            return json.loads(response.read().decode("utf-8"))


def _to_binance_usdm_symbol(symbol: str) -> str:
    if symbol.endswith(":USDT"):
        symbol = symbol[:-5]
    return symbol.replace("/", "").replace("-", "").upper()


def _field(payload: Any, key: str) -> Any:
    if isinstance(payload, dict):
        return payload.get(key)
    if isinstance(payload, list):
        for row in payload:
            if isinstance(row, dict) and key in row:
                return row.get(key)
    return None


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_stale(timestamp_ms: int | None, generated_at_ms: int, max_age_ms: int) -> bool:
    if timestamp_ms is None:
        return False
    return generated_at_ms - timestamp_ms > max_age_ms


def _crowding_proxy_from_payload(
    payload: Any,
    *,
    source_id: str,
    period: str,
) -> tuple[dict[str, Any] | None, int | None]:
    if not isinstance(payload, list) or not payload:
        return None, None
    rows = [row for row in payload if isinstance(row, dict)]
    if not rows:
        return None, None
    latest = max(rows, key=lambda row: _int_or_none(row.get("timestamp")) or -1)
    timestamp_ms = _int_or_none(latest.get("timestamp"))
    ratio = _decimal_or_none(latest.get("longShortRatio"))
    long_account = _decimal_or_none(latest.get("longAccount"))
    short_account = _decimal_or_none(latest.get("shortAccount"))
    if ratio is None or long_account is None or short_account is None:
        return None, timestamp_ms
    return {
        "status": "defined",
        "proxy_type": "global_long_short_account_ratio",
        "definition": "Binance USD-M public global long/short account ratio; account-count crowding proxy, not execution authority.",
        "period": period,
        "long_short_ratio": str(ratio),
        "long_account": str(long_account),
        "short_account": str(short_account),
        "timestamp_ms": timestamp_ms,
        "source_id": source_id,
    }, timestamp_ms
