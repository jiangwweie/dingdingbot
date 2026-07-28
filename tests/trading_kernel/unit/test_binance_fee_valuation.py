from __future__ import annotations

from decimal import Decimal

import pytest

from src.trading_kernel.infrastructure.binance_fee_valuation import (
    read_bnbusdt_fee_valuation_evidence,
)


class _IndexExchange:
    def __init__(self, rows) -> None:
        self.rows = rows
        self.calls = []

    async def fapiPublicGetIndexPriceKlines(self, params):
        self.calls.append(dict(params))
        return self.rows


@pytest.mark.asyncio
async def test_reads_latest_completed_bnbusdt_one_minute_index_candle() -> None:
    exchange = _IndexExchange(
        [
            [900_000, "590", "610", "580", "600", "0", 959_999],
            [960_000, "600", "620", "590", "610", "0", 1_019_999],
        ]
    )

    evidence = await read_bnbusdt_fee_valuation_evidence(
        exchange=exchange,
        trade_occurred_at_ms=1_000_000,
    )

    assert evidence.rate_usdt_per_asset == Decimal("600")
    assert evidence.candle_open_time_ms == 900_000
    assert evidence.candle_close_time_ms == 959_999
    assert exchange.calls[0]["symbol"] == "BNBUSDT"
    assert exchange.calls[0]["interval"] == "1m"


@pytest.mark.asyncio
async def test_rejects_stale_or_missing_completed_index_candle() -> None:
    exchange = _IndexExchange(
        [[800_000, "590", "610", "580", "600", "0", 859_999]]
    )

    with pytest.raises(RuntimeError, match="stale"):
        await read_bnbusdt_fee_valuation_evidence(
            exchange=exchange,
            trade_occurred_at_ms=1_000_000,
        )
