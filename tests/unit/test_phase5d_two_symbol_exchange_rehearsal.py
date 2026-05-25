from __future__ import annotations

from decimal import Decimal

import pytest

from src.application.two_symbol_exchange_rehearsal import (
    run_two_symbol_readonly_rehearsal,
)


ETH = "ETH/USDT:USDT"
BTC = "BTC/USDT:USDT"


class _Position:
    def __init__(self, size: str) -> None:
        self.size = Decimal(size)


class _Gateway:
    def __init__(self, *, positions=None, normal_orders=None, stop_orders=None) -> None:
        self.positions = positions or {}
        self.normal_orders = normal_orders or {}
        self.stop_orders = stop_orders or {}
        self.calls: list[tuple[str, str, dict | None]] = []

    async def fetch_ticker_price(self, symbol: str):
        self.calls.append(("ticker", symbol, None))
        return Decimal("100")

    async def fetch_positions(self, symbol: str):
        self.calls.append(("positions", symbol, None))
        return self.positions.get(symbol, [])

    async def fetch_open_orders(self, symbol: str, params=None):
        self.calls.append(("open_orders", symbol, params))
        if params == {"stop": True}:
            return self.stop_orders.get(symbol, [])
        return self.normal_orders.get(symbol, [])


@pytest.mark.asyncio
async def test_two_symbol_readonly_rehearsal_passes_when_flat_and_no_orders():
    gateway = _Gateway()

    report = await run_two_symbol_readonly_rehearsal(
        gateway=gateway,
        symbols=[ETH, BTC],
    )

    assert report.read_only is True
    assert report.authority == "exchange_connected_read_only_no_order_authority"
    assert report.passed is True
    assert report.verdict == "phase5d_two_symbol_exchange_readonly_passed"
    assert {probe.symbol for probe in report.probes} == {ETH, BTC}
    assert "order_placement" in report.prohibited_actions
    assert ("open_orders", ETH, {"stop": True}) in gateway.calls
    assert ("open_orders", BTC, {"stop": True}) in gateway.calls


@pytest.mark.asyncio
async def test_two_symbol_readonly_rehearsal_blocks_on_nonzero_position_or_orders():
    gateway = _Gateway(
        positions={ETH: [_Position("0.1")]},
        normal_orders={BTC: [{"id": "btc-open"}]},
        stop_orders={ETH: [{"id": "eth-stop"}]},
    )

    report = await run_two_symbol_readonly_rehearsal(
        gateway=gateway,
        symbols=[ETH, BTC],
    )

    assert report.passed is False
    eth_probe = next(probe for probe in report.probes if probe.symbol == ETH)
    btc_probe = next(probe for probe in report.probes if probe.symbol == BTC)
    assert eth_probe.nonzero_position_count == 1
    assert "nonzero_position_present" in eth_probe.warnings
    assert "conditional_open_orders_present" in eth_probe.warnings
    assert btc_probe.normal_open_order_count == 1
    assert "normal_open_orders_present" in btc_probe.warnings
