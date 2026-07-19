"""Minimal Binance USD-M signed/public GET source for instrument rules."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import time
from typing import Any, Callable
from urllib.parse import urlencode
import urllib.error
import urllib.request


DEFAULT_BASE_URL = "https://fapi.binance.com"
UrlOpen = Callable[..., Any]


@dataclass(frozen=True)
class BinanceUsdmRuleSourcePayload:
    exchange_info: dict[str, Any]
    leverage_brackets: list[dict[str, Any]]
    observed_at_ms: int
    source_ref: str


def fetch_binance_usdm_rule_source(
    *,
    api_key: str,
    api_secret: str,
    base_url: str = DEFAULT_BASE_URL,
    timeout_seconds: float = 12,
    urlopen: UrlOpen = urllib.request.urlopen,
) -> BinanceUsdmRuleSourcePayload:
    """Fetch exactly two GET endpoints with a bounded total timeout budget."""

    if not api_key or not api_secret:
        raise RuntimeError("exchange_api_key_or_secret_missing")
    if timeout_seconds <= 0 or timeout_seconds > 14:
        raise ValueError("timeout_seconds must be in (0, 14]")
    exchange_info, exchange_observed = _request_json(
        base_url=base_url,
        path="/fapi/v1/exchangeInfo",
        timeout_seconds=timeout_seconds,
        urlopen=urlopen,
    )
    leverage, leverage_observed = _request_json(
        base_url=base_url,
        path="/fapi/v1/leverageBracket",
        api_key=api_key,
        api_secret=api_secret,
        signed=True,
        timeout_seconds=timeout_seconds,
        urlopen=urlopen,
    )
    if not isinstance(exchange_info, dict) or not isinstance(leverage, list):
        raise RuntimeError("instrument_rule_source_payload_shape_invalid")
    observed_at_ms = max(exchange_observed, leverage_observed)
    return BinanceUsdmRuleSourcePayload(
        exchange_info=exchange_info,
        leverage_brackets=[item for item in leverage if isinstance(item, dict)],
        observed_at_ms=observed_at_ms,
        source_ref=(
            "binance_usdm_readonly_get:"
            "/fapi/v1/exchangeInfo+/fapi/v1/leverageBracket:"
            f"{observed_at_ms}"
        ),
    )


def _request_json(
    *,
    base_url: str,
    path: str,
    timeout_seconds: float,
    urlopen: UrlOpen,
    api_key: str | None = None,
    api_secret: str | None = None,
    signed: bool = False,
) -> tuple[object, int]:
    params: dict[str, object] = {}
    headers: dict[str, str] = {}
    if signed:
        if not api_key or not api_secret:
            raise RuntimeError("exchange_api_key_or_secret_missing")
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = 5000
        query = urlencode(params)
        params["signature"] = hmac.new(
            api_secret.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        headers["X-MBX-APIKEY"] = api_key
    url = f"{base_url.rstrip('/')}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"http_{exc.code}:{body[:160]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"instrument_rule_source_unreachable:{exc.reason}") from exc
    if not isinstance(payload, (dict, list)):
        raise RuntimeError("instrument_rule_source_json_root_invalid")
    return payload, int(time.time() * 1000)
