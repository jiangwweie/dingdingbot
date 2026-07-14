from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from src.infrastructure.binance_usdm_account_risk_snapshot import (
    BinanceUsdmAccountRiskSnapshotProvider,
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
