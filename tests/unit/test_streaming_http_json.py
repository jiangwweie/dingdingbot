from __future__ import annotations

from io import BytesIO
import json
from urllib.error import HTTPError

import pytest

from src.infrastructure.binance_usdm_streaming_signed_reader import (
    BinanceUsdmStreamingSignedReader,
)
from src.infrastructure.streaming_http_json import (
    iter_json_array_items,
    read_masked_error_excerpt,
)


class _Response(BytesIO):
    def __init__(self, body: bytes, *, reject_unbounded: bool = False) -> None:
        super().__init__(body)
        self.read_sizes: list[int] = []
        self.reject_unbounded = reject_unbounded

    def read(self, size: int = -1) -> bytes:
        if self.reject_unbounded and size <= 0:
            raise AssertionError("transport received unbounded read")
        self.read_sizes.append(size)
        return super().read(size)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def test_large_account_object_streams_required_scalars_without_tree() -> None:
    payload = {
        "totalWalletBalance": "600",
        "availableBalance": "500",
        "totalInitialMargin": "10",
        "canTrade": True,
        "assets": [{"ignored": "x" * 1000} for _ in range(2500)],
        "positions": [{"ignored": "y" * 1000} for _ in range(2500)],
    }
    response = _Response(json.dumps(payload).encode(), reject_unbounded=True)
    reader = _reader(response)

    result = reader.get("/fapi/v2/account")

    assert result == {
        "totalWalletBalance": "600",
        "availableBalance": "500",
        "totalInitialMargin": "10",
        "canTrade": True,
    }
    assert response.read_sizes
    assert max(response.read_sizes) <= 65_536


def test_large_position_and_order_arrays_stream_without_truncation() -> None:
    positions = [
        {
            "symbol": f"S{index}",
            "positionAmt": "0" if index % 2 == 0 else "1",
            "entryPrice": "100",
            "positionSide": "BOTH",
            "ignored": "x" * 1000,
        }
        for index in range(3000)
    ]
    orders = [
        {
            "symbol": f"S{index}",
            "orderId": index,
            "clientOrderId": f"client-{index}",
            "origQty": "1",
            "price": "100",
            "ignored": "y" * 1000,
        }
        for index in range(3000)
    ]

    position_result = _reader(
        _Response(json.dumps(positions).encode(), reject_unbounded=True)
    ).get("/fapi/v2/positionRisk")
    order_result = _reader(
        _Response(json.dumps(orders).encode(), reject_unbounded=True)
    ).get("/fapi/v1/openOrders")

    assert len(position_result) == 1500
    assert len(order_result) == 3000
    assert order_result[-1].client_order_id == "client-2999"


def test_transport_never_calls_unbounded_read() -> None:
    response = _Response(b"[1,2,3]", reject_unbounded=True)
    assert list(iter_json_array_items(response)) == [1, 2, 3]
    assert response.read_sizes
    assert all(0 < size <= 65_536 for size in response.read_sizes)


def test_malformed_or_interrupted_stream_fails_closed() -> None:
    response = _Response(b'[{"symbol":"SOLUSDT","positionAmt":"1"')
    with pytest.raises(Exception):
        _reader(response).get("/fapi/v2/positionRisk")


def test_error_body_keeps_only_masked_64k_excerpt() -> None:
    body = (
        b'{"api_key":"visible-secret","signature":"'
        + b"a" * 80
        + b'","padding":"'
        + b"z" * 100_000
    )
    excerpt = read_masked_error_excerpt(_Response(body), max_bytes=65_536)
    assert len(excerpt.encode()) <= 65_536
    assert "visible-secret" not in excerpt
    assert "a" * 80 not in excerpt

    error = HTTPError(
        url="https://example.invalid",
        code=400,
        msg="bad",
        hdrs=None,
        fp=_Response(body, reject_unbounded=True),
    )
    with pytest.raises(RuntimeError, match=r"http_400") as raised:
        _reader(None, opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(error)).get(
            "/fapi/v2/account"
        )
    assert "visible-secret" not in str(raised.value)


def _reader(
    response: _Response | None,
    *,
    opener=None,
) -> BinanceUsdmStreamingSignedReader:
    actual_opener = opener or (lambda *_args, **_kwargs: response)
    return BinanceUsdmStreamingSignedReader(
        base_url="https://example.invalid",
        api_key="key",
        api_secret="secret",
        timeout_seconds=1,
        opener=actual_opener,
        now_ms=lambda: 1_752_480_000_000,
    )
