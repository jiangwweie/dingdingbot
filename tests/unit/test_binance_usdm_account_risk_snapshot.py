from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from decimal import Decimal
from io import BytesIO
import json
from typing import Any

import pytest

from src.infrastructure.binance_usdm_account_risk_snapshot import (
    BinanceUsdmAccountRiskSnapshotProvider,
)
from src.infrastructure.binance_usdm_streaming_signed_reader import (
    BinanceUsdmStreamingSignedReader,
)


class FakeSignedGet:
    def __init__(self, payloads: dict[str, object]) -> None:
        self.payloads = payloads
        self.calls: list[str] = []

    async def __call__(self, path: str) -> dict[str, Any]:
        self.calls.append(path)
        value = self.payloads[path]
        if isinstance(value, Exception):
            raise value
        return value  # type: ignore[return-value]


@pytest.mark.asyncio
async def test_snapshot_reads_full_account_positions_regular_and_algo_orders() -> None:
    transport = FakeSignedGet(
        {
            "/fapi/v2/account": {
                "canTrade": True,
                "totalWalletBalance": "600",
                "availableBalance": "500",
                "totalInitialMargin": "100",
            },
            "/fapi/v2/positionRisk": [
                {"symbol": "ETHUSDT", "positionAmt": "1", "entryPrice": "100"},
                {"symbol": "OUTSIDEUSDT", "positionAmt": "2", "entryPrice": "50"},
            ],
            "/fapi/v1/openOrders": [{"symbol": "ETHUSDT", "orderId": 1}],
            "/fapi/v1/openAlgoOrders": [{"symbol": "ETHUSDT", "algoId": 2}],
            "/fapi/v1/positionSide/dual": {"dualSidePosition": False},
        }
    )
    provider = BinanceUsdmAccountRiskSnapshotProvider(
        account_id="subaccount-1",
        exchange_id="binance_usdm",
        signed_get=transport,
        now_ms=lambda: 1_752_480_000_000,
    )

    snapshot = await provider.fetch(timeout_seconds=2)

    assert set(transport.calls) == {
        "/fapi/v2/account",
        "/fapi/v2/positionRisk",
        "/fapi/v1/openOrders",
        "/fapi/v1/openAlgoOrders",
        "/fapi/v1/positionSide/dual",
    }
    assert snapshot.snapshot_ready is True
    assert snapshot.symbol_filter_applied is False
    assert snapshot.exchange_write_called is False
    assert {row.exchange_symbol for row in snapshot.positions} == {
        "ETHUSDT",
        "OUTSIDEUSDT",
    }
    assert len(snapshot.regular_open_orders) == 1
    assert len(snapshot.algo_open_orders) == 1
    assert snapshot.position_mode == "one_way"


@pytest.mark.asyncio
async def test_snapshot_fails_closed_when_any_account_surface_is_missing_or_times_out() -> None:
    transport = FakeSignedGet(
        {
            "/fapi/v2/account": asyncio.TimeoutError(),
            "/fapi/v2/positionRisk": [],
            "/fapi/v1/openOrders": [],
            "/fapi/v1/openAlgoOrders": [],
            "/fapi/v1/positionSide/dual": {"dualSidePosition": False},
        }
    )
    provider = BinanceUsdmAccountRiskSnapshotProvider(
        account_id="subaccount-1",
        exchange_id="binance_usdm",
        signed_get=transport,
        now_ms=lambda: 1_752_480_000_000,
    )

    snapshot = await provider.fetch(timeout_seconds=2)

    assert snapshot.snapshot_ready is False
    assert snapshot.failure_code == "account_risk_snapshot_fetch_failed"
    assert snapshot.positions == ()
    assert snapshot.regular_open_orders == ()
    assert snapshot.algo_open_orders == ()


@pytest.mark.asyncio
async def test_malformed_stream_never_publishes_partial_account_snapshot() -> None:
    payloads = {
        "/fapi/v2/account": (
            b'{"canTrade":true,"totalWalletBalance":"600",'
            b'"availableBalance":"500","totalInitialMargin":"100"}'
        ),
        "/fapi/v2/positionRisk": (
            b'[{"symbol":"ETHUSDT","positionAmt":"1","entryPrice":"100"},'
        ),
        "/fapi/v1/openOrders": b"[]",
        "/fapi/v1/openAlgoOrders": b"[]",
        "/fapi/v1/positionSide/dual": b'{"dualSidePosition":false}',
    }

    def opener(request, *, timeout):
        del timeout
        path = next(path for path in payloads if path in request.full_url)
        return BytesIO(payloads[path])

    reader = BinanceUsdmStreamingSignedReader(
        base_url="https://example.invalid",
        api_key="test-key",
        api_secret="test-secret",
        timeout_seconds=2,
        opener=opener,
        now_ms=lambda: 1_752_480_000_000,
    )

    async def signed_get(path: str) -> object:
        return await asyncio.to_thread(reader.get, path)

    provider = BinanceUsdmAccountRiskSnapshotProvider(
        account_id="subaccount-1",
        exchange_id="binance_usdm",
        signed_get=signed_get,
        now_ms=lambda: 1_752_480_000_000,
    )

    snapshot = await provider.fetch(timeout_seconds=2)

    assert snapshot.snapshot_ready is False
    assert snapshot.failure_code == "account_risk_snapshot_fetch_failed"
    assert snapshot.positions == ()
    assert snapshot.regular_open_orders == ()
    assert snapshot.algo_open_orders == ()


@pytest.mark.asyncio
async def test_zero_position_with_zero_entry_price_is_filtered_before_validation() -> None:
    provider = BinanceUsdmAccountRiskSnapshotProvider(
        account_id="subaccount-1",
        exchange_id="binance_usdm",
        signed_get=FakeSignedGet(
            _account_payloads(
                positions=[
                    {"symbol": "BTCUSDT", "positionAmt": "0", "entryPrice": "0"},
                    {"symbol": "ETHUSDT", "positionAmt": "1", "entryPrice": "100"},
                ]
            )
        ),
        now_ms=lambda: 1_752_480_000_000,
    )

    snapshot = await provider.fetch(timeout_seconds=2)

    assert snapshot.snapshot_ready is True
    assert [(row.exchange_symbol, row.position_qty) for row in snapshot.positions] == [
        ("ETHUSDT", Decimal("1")),
    ]


@pytest.mark.asyncio
async def test_algo_order_preserves_client_algo_id() -> None:
    provider = BinanceUsdmAccountRiskSnapshotProvider(
        account_id="subaccount-1",
        exchange_id="binance_usdm",
        signed_get=FakeSignedGet(
            _account_payloads(
                algo_orders=[
                    {
                        "symbol": "ETHUSDT",
                        "orderId": "order-1",
                        "algoId": "algo-1",
                        "clientAlgoId": "client-algo-1",
                        "origQty": "2",
                        "executedQty": "0",
                    }
                ]
            )
        ),
        now_ms=lambda: 1_752_480_000_000,
    )

    snapshot = await provider.fetch(timeout_seconds=2)

    assert snapshot.snapshot_ready is True
    assert snapshot.algo_open_orders[0].exchange_order_id == "order-1"
    assert snapshot.algo_open_orders[0].algo_id == "algo-1"
    assert snapshot.algo_open_orders[0].client_algo_id == "client-algo-1"


@pytest.mark.asyncio
async def test_partial_fill_preserves_orig_executed_and_remaining_qty() -> None:
    provider = BinanceUsdmAccountRiskSnapshotProvider(
        account_id="subaccount-1",
        exchange_id="binance_usdm",
        signed_get=FakeSignedGet(
            _account_payloads(
                regular_orders=[
                    {
                        "symbol": "ETHUSDT",
                        "orderId": "order-1",
                        "origQty": "1.25",
                        "executedQty": "0.25",
                    }
                ]
            )
        ),
        now_ms=lambda: 1_752_480_000_000,
    )

    snapshot = await provider.fetch(timeout_seconds=2)

    assert snapshot.snapshot_ready is True
    order = snapshot.regular_open_orders[0]
    assert order.original_qty == Decimal("1.25")
    assert order.executed_qty == Decimal("0.25")
    assert order.remaining_qty == Decimal("1.00")
    assert order.quantity == Decimal("1.00")


@pytest.mark.asyncio
async def test_streaming_and_non_streaming_normalized_snapshots_are_identical() -> None:
    payloads = _account_payloads(
        positions=[
            {"symbol": "BTCUSDT", "positionAmt": "0", "entryPrice": "0"},
            {"symbol": "ETHUSDT", "positionAmt": "1", "entryPrice": "100"},
        ],
        regular_orders=[
            {
                "symbol": "ETHUSDT",
                "orderId": "order-1",
                "clientOrderId": "client-order-1",
                "origQty": "2",
                "executedQty": "0.5",
            }
        ],
        algo_orders=[
            {
                "symbol": "ETHUSDT",
                "orderId": "order-2",
                "algoId": "algo-2",
                "clientAlgoId": "client-algo-2",
                "origQty": "1",
                "executedQty": "0",
            }
        ],
    )
    non_streaming = BinanceUsdmAccountRiskSnapshotProvider(
        account_id="subaccount-1",
        exchange_id="binance_usdm",
        signed_get=FakeSignedGet(payloads),
        now_ms=lambda: 1_752_480_000_000,
    )

    def opener(request, *, timeout):
        del timeout
        path = next(path for path in payloads if path in request.full_url)
        return BytesIO(json.dumps(payloads[path]).encode())

    reader = BinanceUsdmStreamingSignedReader(
        base_url="https://example.invalid",
        api_key="test-key",
        api_secret="test-secret",
        timeout_seconds=2,
        opener=opener,
        now_ms=lambda: 1_752_480_000_000,
    )

    async def streaming_signed_get(path: str) -> object:
        return await asyncio.to_thread(reader.get, path)

    streaming = BinanceUsdmAccountRiskSnapshotProvider(
        account_id="subaccount-1",
        exchange_id="binance_usdm",
        signed_get=streaming_signed_get,
        now_ms=lambda: 1_752_480_000_000,
    )

    assert await streaming.fetch(timeout_seconds=2) == await non_streaming.fetch(timeout_seconds=2)


@pytest.mark.asyncio
async def test_negative_remaining_quantity_fails_closed() -> None:
    provider = BinanceUsdmAccountRiskSnapshotProvider(
        account_id="subaccount-1",
        exchange_id="binance_usdm",
        signed_get=FakeSignedGet(
            _account_payloads(
                regular_orders=[
                    {
                        "symbol": "ETHUSDT",
                        "orderId": "order-1",
                        "origQty": "1",
                        "executedQty": "1.1",
                    }
                ]
            )
        ),
        now_ms=lambda: 1_752_480_000_000,
    )

    snapshot = await provider.fetch(timeout_seconds=2)

    assert snapshot.snapshot_ready is False
    assert snapshot.failure_code == "account_risk_snapshot_fetch_failed"


def _account_payloads(
    *,
    positions: list[dict[str, object]] | None = None,
    regular_orders: list[dict[str, object]] | None = None,
    algo_orders: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "/fapi/v2/account": {
            "canTrade": True,
            "totalWalletBalance": "600",
            "availableBalance": "500",
            "totalInitialMargin": "100",
        },
        "/fapi/v2/positionRisk": positions or [],
        "/fapi/v1/openOrders": regular_orders or [],
        "/fapi/v1/openAlgoOrders": algo_orders or [],
        "/fapi/v1/positionSide/dual": {"dualSidePosition": False},
    }
