"""Release-facing contract for the local dual-position account-risk implementation.

This is deliberately non-executing: it fixes the Owner-approved policy and
the product-level capacity language without creating a policy row, Ticket, or
exchange request.
"""

from __future__ import annotations

from decimal import Decimal

from src.application.readmodels.account_risk_owner_state import (
    account_risk_owner_state_from_budget,
)
from src.domain.account_risk import AccountRiskPolicy, decide_account_capacity


def test_owner_policy_is_the_exact_dual_position_hard_cap_contract() -> None:
    policy = _policy()

    assert policy.planned_stop_risk_fraction == Decimal("0.025")
    assert policy.max_concurrent_positions == 2
    assert policy.max_portfolio_open_risk_fraction == Decimal("0.06")
    assert policy.max_cluster_open_risk_fraction == Decimal("0.04")
    assert policy.max_portfolio_initial_margin_fraction == Decimal("0.90")
    assert policy.max_leverage == 10
    assert policy.max_new_action_time_lanes == 1
    assert policy.automatic_downsize_enabled is True
    assert policy.unknown_exposure_policy == "global_fail_closed"


def test_six_hundred_usdt_capacity_never_turns_two_positions_into_three() -> None:
    common = {
        "wallet_balance": Decimal("600"),
        "available_balance": Decimal("500"),
        "exchange_initial_margin": Decimal("100"),
        "unreflected_pending_margin": Decimal("0"),
        "existing_portfolio_held_risk": Decimal("15"),
        "existing_cluster_held_risk": Decimal("15"),
        "instrument_already_claimed": False,
        "per_unit_stop_risk": Decimal("3"),
        "entry_reference_price": Decimal("150"),
        "min_qty": Decimal("0.01"),
        "qty_step": Decimal("0.01"),
        "min_notional": Decimal("5"),
        "exchange_max_leverage": 20,
        "policy": _policy(),
    }

    same_cluster_second = decide_account_capacity(
        **common,
        claimed_position_slots=1,
    )
    different_cluster_second = decide_account_capacity(
        **{**common, "existing_cluster_held_risk": Decimal("0")},
        claimed_position_slots=1,
    )
    third_position = decide_account_capacity(
        **common,
        claimed_position_slots=2,
    )

    assert same_cluster_second.allowed_risk == Decimal("9")
    assert same_cluster_second.intended_qty == Decimal("3.00")
    assert different_cluster_second.allowed_risk == Decimal("15")
    assert different_cluster_second.intended_qty == Decimal("5.00")
    assert third_position.blockers == ("max_concurrent_positions_reached",)


def test_owner_capacity_language_hides_execution_internals() -> None:
    states = [
        account_risk_owner_state_from_budget(
            {
                "claimed_position_slots": 1,
                "max_concurrent_positions": 2,
                "reconciliation_state": "matched",
                "new_entry_allowed": True,
            }
        ),
        account_risk_owner_state_from_budget(
            {
                "claimed_position_slots": 2,
                "max_concurrent_positions": 2,
                "reconciliation_state": "matched",
                "new_entry_allowed": True,
            }
        ),
        account_risk_owner_state_from_budget(
            {
                "claimed_position_slots": 1,
                "max_concurrent_positions": 2,
                "reconciliation_state": "mismatch",
                "new_entry_allowed": False,
            }
        ),
    ]

    assert [state.summary for state in states] == [
        "当前 1/2 个仓位正在运行；仍可接收一个不同品种机会",
        "当前 2/2 个仓位正在运行；新机会暂不入场",
        "账户事实需要重新对账；系统已停止新开仓，现有保护继续运行",
    ]
    assert all(
        term not in " ".join(state.summary for state in states)
        for term in ("FOR UPDATE", "CAS", "FinalGate", "RequiredFacts")
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
