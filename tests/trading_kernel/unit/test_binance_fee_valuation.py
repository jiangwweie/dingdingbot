from __future__ import annotations

from decimal import Decimal

import pytest

from src.trading_kernel.infrastructure.binance_fee_valuation import (
    read_bnbusdt_fee_valuation_evidence,
)


class _IndexExchange:
    def __init__(self, response) -> None:
        self.response = response
        self.calls = []

    async def fapiPublicGetPremiumIndex(self, params):
        self.calls.append(dict(params))
        return self.response


@pytest.mark.asyncio
async def test_reads_one_bnbusdt_index_snapshot_at_review_time() -> None:
    exchange = _IndexExchange({"symbol": "BNBUSDT", "indexPrice": "600", "time": 1_500_000})

    evidence = await read_bnbusdt_fee_valuation_evidence(
        exchange=exchange,
        review_observed_at_ms=1_500_000,
    )

    assert evidence.rate_usdt_per_asset == Decimal("600")
    assert evidence.observed_at_ms == 1_500_000
    assert exchange.calls[0]["symbol"] == "BNBUSDT"


@pytest.mark.asyncio
async def test_rejects_missing_or_non_positive_review_snapshot() -> None:
    exchange = _IndexExchange({"symbol": "BNBUSDT", "indexPrice": "0", "time": 1_500_000})

    with pytest.raises(RuntimeError, match="non-positive"):
        await read_bnbusdt_fee_valuation_evidence(
            exchange=exchange,
            review_observed_at_ms=1_500_000,
        )
