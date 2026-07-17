from __future__ import annotations

from decimal import Decimal

from src.domain.account_risk import (
    AccountRiskPolicy,
    compute_directional_risk,
    decide_account_capacity,
)


def _policy() -> AccountRiskPolicy:
    return AccountRiskPolicy(
        risk_policy_version="account-risk-v0-owner-20260714",
        planned_stop_risk_fraction=Decimal("0.025"),
        max_concurrent_positions=2,
        max_portfolio_open_risk_fraction=Decimal("0.06"),
        max_cluster_open_risk_fraction=Decimal("0.04"),
        max_portfolio_initial_margin_fraction=Decimal("0.90"),
        max_leverage=10,
        max_new_action_time_lanes=1,
        automatic_downsize_enabled=True,
        unknown_exposure_policy="global_fail_closed",
        activation_state="active",
    )


def _decision(**overrides: object):
    values: dict[str, object] = {
        "wallet_balance": Decimal("600"),
        "available_balance": Decimal("500"),
        "exchange_initial_margin": Decimal("100"),
        "unreflected_pending_margin": Decimal("0"),
        "existing_portfolio_held_risk": Decimal("15"),
        "existing_cluster_held_risk": Decimal("15"),
        "claimed_position_slots": 1,
        "instrument_already_claimed": False,
        "per_unit_stop_risk": Decimal("3"),
        "entry_reference_price": Decimal("150"),
        "min_qty": Decimal("0.01"),
        "qty_step": Decimal("0.01"),
        "min_notional": Decimal("5"),
        "exchange_max_leverage": 20,
        "policy": _policy(),
    }
    values.update(overrides)
    return decide_account_capacity(**values)


def test_second_same_cluster_ticket_downsizes_to_one_point_five_percent() -> None:
    result = _decision()

    assert result.allowed_risk == Decimal("9")
    assert result.intended_qty == Decimal("3.00")
    assert result.selected_leverage == 2
    assert result.blockers == ()


def test_second_different_cluster_keeps_ticket_risk_limit() -> None:
    result = _decision(existing_cluster_held_risk=Decimal("0"))

    assert result.allowed_risk == Decimal("15")
    assert result.intended_qty == Decimal("5.00")
    assert result.blockers == ()


def test_same_instrument_and_exhausted_slots_are_precise_capacity_blockers() -> None:
    same_instrument = _decision(instrument_already_claimed=True)
    full_slots = _decision(claimed_position_slots=2)

    assert same_instrument.blockers == ("account_instrument_already_claimed",)
    assert full_slots.blockers == ("max_concurrent_positions_reached",)


def test_minimum_quantity_can_be_blocked_by_stop_risk_or_margin_capacity() -> None:
    risk_blocked = _decision(min_qty=Decimal("10"))
    margin_blocked = _decision(
        available_balance=Decimal("1"),
        min_qty=Decimal("1"),
        existing_cluster_held_risk=Decimal("0"),
    )

    assert risk_blocked.blockers == (
        "minimum_executable_quantity_exceeds_available_stop_risk_capacity",
    )
    assert margin_blocked.blockers == (
        "minimum_executable_quantity_exceeds_available_margin_capacity",
    )


def test_directional_risk_uses_confirmed_stop_and_never_counts_locked_profit_as_risk() -> None:
    assert compute_directional_risk(
        side="long",
        actual_average_entry_price=Decimal("100"),
        confirmed_stop_price=Decimal("95"),
        position_qty=Decimal("2"),
    ) == Decimal("10")
    assert compute_directional_risk(
        side="long",
        actual_average_entry_price=Decimal("100"),
        confirmed_stop_price=Decimal("105"),
        position_qty=Decimal("2"),
    ) == Decimal("0")
    assert compute_directional_risk(
        side="short",
        actual_average_entry_price=Decimal("100"),
        confirmed_stop_price=Decimal("105"),
        position_qty=Decimal("2"),
    ) == Decimal("10")
    assert compute_directional_risk(
        side="short",
        actual_average_entry_price=Decimal("100"),
        confirmed_stop_price=Decimal("95"),
        position_qty=Decimal("2"),
    ) == Decimal("0")
