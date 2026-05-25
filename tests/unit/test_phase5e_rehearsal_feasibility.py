from __future__ import annotations

from decimal import Decimal

from src.application.phase5e_rehearsal_feasibility import (
    assess_controlled_symbol_feasibility,
)


def test_phase5e_feasibility_passes_when_fixed_notional_is_inside_bounds():
    result = assess_controlled_symbol_feasibility(
        symbol="ETH/USDT:USDT",
        amount=Decimal("0.01"),
        price=Decimal("2100"),
        min_notional=Decimal("20"),
        min_notional_source="default",
        max_notional=Decimal("25"),
        amount_step=Decimal("0.01"),
    )

    assert result.feasible is True
    assert result.reason == "OK"
    assert result.notional == Decimal("21.00")
    assert result.next_viable_amount == Decimal("0.01")
    assert result.next_viable_notional == Decimal("21.00")
    assert result.cap_shortfall is None


def test_phase5e_feasibility_blocks_when_min_notional_exceeds_cap():
    result = assess_controlled_symbol_feasibility(
        symbol="BTC/USDT:USDT",
        amount=Decimal("0.001"),
        price=Decimal("110000"),
        min_notional=Decimal("131"),
        min_notional_source="default",
        max_notional=Decimal("130"),
        amount_step=Decimal("0.001"),
    )

    assert result.feasible is False
    assert result.reason == "MIN_NOTIONAL_EXCEEDS_CAP"
    assert result.next_viable_amount == Decimal("0.002")
    assert result.next_viable_notional == Decimal("220.000")
    assert result.cap_shortfall == Decimal("90.000")


def test_phase5e_feasibility_blocks_when_fixed_amount_is_below_min_notional():
    result = assess_controlled_symbol_feasibility(
        symbol="BTC/USDT:USDT",
        amount=Decimal("0.001"),
        price=Decimal("77550.6"),
        min_notional=Decimal("100"),
        min_notional_source="default",
        max_notional=Decimal("130"),
        amount_step=Decimal("0.001"),
    )

    assert result.feasible is False
    assert result.reason == "NOTIONAL_BELOW_MIN_NOTIONAL"
    assert result.notional == Decimal("77.5506")
    assert result.next_viable_amount == Decimal("0.002")
    assert result.next_viable_notional == Decimal("155.1012")
    assert result.cap_shortfall == Decimal("25.1012")


def test_phase5e_feasibility_blocks_when_fixed_amount_exceeds_cap():
    result = assess_controlled_symbol_feasibility(
        symbol="BTC/USDT:USDT",
        amount=Decimal("0.001"),
        price=Decimal("140000"),
        min_notional=Decimal("100"),
        min_notional_source="default",
        max_notional=Decimal("130"),
        amount_step=Decimal("0.001"),
    )

    assert result.feasible is False
    assert result.reason == "NOTIONAL_ABOVE_CAP"
    assert result.next_viable_amount == Decimal("0.001")
    assert result.next_viable_notional == Decimal("140.000")
    assert result.cap_shortfall == Decimal("10.000")


def test_phase5e_feasibility_can_report_without_exchange_amount_step():
    result = assess_controlled_symbol_feasibility(
        symbol="BTC/USDT:USDT",
        amount=Decimal("0.001"),
        price=Decimal("77550.6"),
        min_notional=Decimal("100"),
        min_notional_source="default",
        max_notional=Decimal("130"),
    )

    assert result.feasible is False
    assert result.reason == "NOTIONAL_BELOW_MIN_NOTIONAL"
    assert result.next_viable_amount is None
    assert result.next_viable_notional is None
    assert result.cap_shortfall is None
