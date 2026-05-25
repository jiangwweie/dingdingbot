"""Read-only two-symbol exchange rehearsal for PLC Phase 5D.

The rehearsal verifies market/account/order visibility for a bounded symbol
set. It does not place, cancel, modify, or reconcile orders.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class TwoSymbolReadOnlyProbe(BaseModel):
    symbol: str
    ticker_price: Decimal
    position_count: int
    nonzero_position_count: int
    normal_open_order_count: int
    conditional_open_order_count: int
    ok: bool
    warnings: list[str] = Field(default_factory=list)


class TwoSymbolReadOnlyRehearsalReport(BaseModel):
    rehearsal_version: Literal["plc_phase5d_two_symbol_readonly_v1"] = (
        "plc_phase5d_two_symbol_readonly_v1"
    )
    exchange_testnet_required: Literal[True] = True
    read_only: Literal[True] = True
    authority: Literal["exchange_connected_read_only_no_order_authority"] = (
        "exchange_connected_read_only_no_order_authority"
    )
    symbols: list[str]
    probes: list[TwoSymbolReadOnlyProbe]
    passed: bool
    verdict: str
    prohibited_actions: list[str] = Field(
        default_factory=lambda: [
            "order_placement",
            "order_cancellation",
            "order_modification",
            "runtime_profile_change",
            "credential_change",
            "real_live_trading",
        ]
    )


async def run_two_symbol_readonly_rehearsal(
    *,
    gateway: Any,
    symbols: list[str],
) -> TwoSymbolReadOnlyRehearsalReport:
    """Run a read-only exchange-connected visibility probe for each symbol."""

    probes = []
    for symbol in symbols:
        probes.append(await _probe_symbol(gateway=gateway, symbol=symbol))

    passed = all(probe.ok for probe in probes)
    return TwoSymbolReadOnlyRehearsalReport(
        symbols=symbols,
        probes=probes,
        passed=passed,
        verdict=(
            "phase5d_two_symbol_exchange_readonly_passed"
            if passed
            else "phase5d_two_symbol_exchange_readonly_needs_cleanup"
        ),
    )


async def _probe_symbol(*, gateway: Any, symbol: str) -> TwoSymbolReadOnlyProbe:
    warnings: list[str] = []
    ticker_price = await gateway.fetch_ticker_price(symbol)
    if ticker_price <= Decimal("0"):
        warnings.append("ticker_price_non_positive")

    positions = await gateway.fetch_positions(symbol=symbol)
    nonzero_positions = [
        position
        for position in positions
        if Decimal(str(getattr(position, "size", "0"))) != Decimal("0")
    ]
    if nonzero_positions:
        warnings.append("nonzero_position_present")

    normal_open_orders = await _fetch_open_orders(gateway, symbol, params=None)
    if normal_open_orders:
        warnings.append("normal_open_orders_present")

    conditional_open_orders = await _fetch_open_orders(
        gateway,
        symbol,
        params={"stop": True},
    )
    if conditional_open_orders:
        warnings.append("conditional_open_orders_present")

    return TwoSymbolReadOnlyProbe(
        symbol=symbol,
        ticker_price=ticker_price,
        position_count=len(positions),
        nonzero_position_count=len(nonzero_positions),
        normal_open_order_count=len(normal_open_orders),
        conditional_open_order_count=len(conditional_open_orders),
        ok=not warnings,
        warnings=warnings,
    )


async def _fetch_open_orders(
    gateway: Any,
    symbol: str,
    *,
    params: Optional[dict[str, Any]],
) -> list[Any]:
    try:
        if params is None:
            return await gateway.fetch_open_orders(symbol)
        return await gateway.fetch_open_orders(symbol, params=params)
    except TypeError:
        if params is None:
            return await gateway.fetch_open_orders(symbol)
        return []
