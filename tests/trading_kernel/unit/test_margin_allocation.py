"""Wallet allocation is stable; live solvency and execution costs are not frozen."""

from decimal import Decimal as D

import pytest

from src.trading_kernel.domain.margin_allocation import (
    MarginAllocation,
    check_entry_margin,
    entry_margin_costs,
)


def check(**changes):
    costs = entry_margin_costs(
        reference_price=D(100),
        best_bid=D(100),
        best_ask=D(100),
        mark_price=D(100),
        position_side="long",
        taker_fee_rate=D(".0005"),
    )
    args = dict(  # noqa: C408 - keyword overrides keep the scenario readable
        allocation=MarginAllocation(
            wallet_balance=D(1500),
            single_margin_fraction=D(".3"),
            single_margin_limit=D(450),
            costs=costs,
        ),
        reference_margin=D(450),
        quantity=D("22.5"),
        leverage=5,
        wallet=D(1500),
        equity=D(1499),
        available=D(1049),
        initial_margin=D(450),
        other_reserved=D(450),
        gross_fraction=D(".9"),
        costs=costs,
    )
    args.update(changes)
    return check_entry_margin(**args)


@pytest.mark.parametrize("equity", [D(1499), D(1500), D(1501)])
def test_floating_equity_cannot_reallocate_single_ticket(equity):
    assert check(equity=equity).reason == "allowed"


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"wallet": D(1499)}, "allocation_wallet_changed"),
        ({"available": D(450)}, "available_margin_insufficient"),
        (
            {
                "initial_margin": D(900),
                "other_reserved": D(900),
                "equity": D(1500),
                "available": D(600),
            },
            "gross_margin_limit",
        ),
        ({"equity": D(900), "available": D(600)}, "available_margin_insufficient"),
    ],
)
def test_real_capital_and_fee_constraints_remain_hard(changes, reason):
    assert check(**changes).reason == reason


def test_latest_quote_and_mark_raise_real_cash_requirement():
    costs = entry_margin_costs(
        reference_price=D(100),
        best_bid=D("100.9"),
        best_ask=D(101),
        mark_price=D("100.9"),
        position_side="long",
        taker_fee_rate=D(".0005"),
    )
    assert (
        check(costs=costs, available=D(454)).reason == "available_margin_insufficient"
    )


def test_internal_reservations_are_not_counted_twice():
    result = check(initial_margin=D(450), other_reserved=D(450))
    assert result.budget.existing_usage == D(450)
    assert result.reason == "allowed"
