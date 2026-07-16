"""Read-only signed Binance USD-M reader with incremental response parsing."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import time
from typing import Any, BinaryIO
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.infrastructure.binance_usdm_account_risk_snapshot import (
    ExchangeOpenOrderRow,
    ExchangePositionRow,
)
from src.infrastructure.streaming_http_json import (
    DEFAULT_CHUNK_BYTES,
    iter_json_array_items,
    iter_json_events,
    read_masked_error_excerpt,
)


ResponseOpener = Callable[..., BinaryIO]


class BinanceUsdmStreamingSignedReader:
    """Expose only the five complete read-only account surfaces."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        api_secret: str,
        timeout_seconds: float,
        opener: ResponseOpener = urlopen,
        now_ms: Callable[[], int] | None = None,
        chunk_bytes: int = DEFAULT_CHUNK_BYTES,
    ) -> None:
        if not api_key or not api_secret:
            raise ValueError("exchange_api_key_or_secret_missing")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._api_secret = api_secret
        self._timeout_seconds = timeout_seconds
        self._opener = opener
        self._now_ms = now_ms or (lambda: int(time.time() * 1000))
        self._chunk_bytes = chunk_bytes

    def get(self, path: str) -> object:
        request = self._request(path)
        try:
            response = self._opener(request, timeout=self._timeout_seconds)
            with response:
                return self._parse_success(path, response)
        except HTTPError as exc:
            excerpt = read_masked_error_excerpt(exc)
            raise RuntimeError(f"http_{exc.code}:{excerpt}") from exc

    def _request(self, path: str) -> Request:
        params = {"timestamp": self._now_ms(), "recvWindow": 5000}
        unsigned = urlencode(params)
        params["signature"] = hmac.new(
            self._api_secret.encode("utf-8"),
            unsigned.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return Request(
            f"{self._base_url}{path}?{urlencode(params)}",
            headers={"X-MBX-APIKEY": self._api_key},
            method="GET",
        )

    def _parse_success(self, path: str, response: BinaryIO) -> object:
        if path == "/fapi/v2/account":
            return _top_level_scalars(
                response,
                required={
                    "totalWalletBalance",
                    "availableBalance",
                    "totalInitialMargin",
                    "canTrade",
                },
                chunk_bytes=self._chunk_bytes,
            )
        if path == "/fapi/v1/positionSide/dual":
            return _top_level_scalars(
                response,
                required={"dualSidePosition"},
                chunk_bytes=self._chunk_bytes,
            )
        if path == "/fapi/v2/positionRisk":
            rows: list[ExchangePositionRow] = []
            for item in iter_json_array_items(response, chunk_bytes=self._chunk_bytes):
                row = _position_row(item)
                if row.position_qty != 0:
                    rows.append(row)
            return tuple(rows)
        if path in {"/fapi/v1/openOrders", "/fapi/v1/openAlgoOrders"}:
            algo = path.endswith("openAlgoOrders")
            return tuple(
                _order_row(item, algo=algo)
                for item in iter_json_array_items(
                    response,
                    chunk_bytes=self._chunk_bytes,
                )
            )
        raise ValueError("unsupported_account_risk_path")


def _top_level_scalars(
    response: BinaryIO,
    *,
    required: set[str],
    chunk_bytes: int,
) -> dict[str, object]:
    values: dict[str, object] = {}
    scalar_events = {"string", "number", "boolean", "null"}
    for prefix, event, value in iter_json_events(
        response,
        chunk_bytes=chunk_bytes,
    ):
        if prefix in required and "." not in prefix and event in scalar_events:
            values[prefix] = value
    if set(values) != required:
        raise ValueError("required_top_level_account_fields_missing")
    return values


def _position_row(value: object) -> ExchangePositionRow:
    if not isinstance(value, dict):
        raise ValueError("position row is malformed")
    return ExchangePositionRow(
        exchange_symbol=_required_text(value.get("symbol"), "position_symbol"),
        position_qty=_required_decimal(value.get("positionAmt"), "position_qty"),
        entry_price=_required_positive_decimal(
            value.get("entryPrice"),
            "position_entry_price",
        ),
        position_side=str(value.get("positionSide") or "BOTH").upper(),
    )


def _order_row(value: object, *, algo: bool) -> ExchangeOpenOrderRow:
    if not isinstance(value, dict):
        raise ValueError("open order row is malformed")
    return ExchangeOpenOrderRow(
        exchange_symbol=_required_text(value.get("symbol"), "order_symbol"),
        exchange_order_id=str(value.get("orderId") or ""),
        algo_id=str(value.get("algoId") or "") if algo else "",
        client_order_id=str(value.get("clientOrderId") or ""),
        side=str(value.get("side") or "").upper(),
        position_side=str(value.get("positionSide") or "BOTH").upper(),
        reduce_only=(
            value.get("reduceOnly")
            if isinstance(value.get("reduceOnly"), bool)
            else None
        ),
        close_position=(
            value.get("closePosition")
            if isinstance(value.get("closePosition"), bool)
            else None
        ),
        order_type=str(value.get("type") or value.get("algoType") or ""),
        quantity=_optional_decimal(value.get("origQty") or value.get("quantity")),
        price=_optional_decimal(value.get("price")),
        trigger_price=_optional_decimal(
            value.get("stopPrice") or value.get("triggerPrice")
        ),
    )


def _required_text(value: object, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name}_missing")
    return text


def _required_decimal(value: object, name: str) -> Decimal:
    result = _optional_decimal(value)
    if result is None:
        raise ValueError(f"{name}_invalid")
    return result


def _required_positive_decimal(value: object, name: str) -> Decimal:
    result = _required_decimal(value, name)
    if result <= 0:
        raise ValueError(f"{name}_invalid")
    return result


def _optional_decimal(value: object) -> Decimal | None:
    if value in {None, ""}:
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() else None
