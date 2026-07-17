from __future__ import annotations

from src.application.readmodels.account_risk_owner_state import (
    account_risk_owner_state_from_budget,
)


def test_owner_state_says_one_of_two_positions_can_accept_a_different_instrument() -> None:
    state = account_risk_owner_state_from_budget(
        {
            "claimed_position_slots": 1,
            "max_concurrent_positions": 2,
            "new_entry_allowed": True,
            "reconciliation_state": "matched",
        }
    )

    assert state.summary == "当前 1/2 个仓位正在运行；仍可接收一个不同品种机会"
    assert state.owner_action_required is False


def test_owner_state_says_capacity_is_full_without_internal_gate_names() -> None:
    state = account_risk_owner_state_from_budget(
        {
            "claimed_position_slots": 2,
            "max_concurrent_positions": 2,
            "new_entry_allowed": True,
            "reconciliation_state": "matched",
        }
    )

    assert state.summary == "当前 2/2 个仓位正在运行；新机会暂不入场"
    assert "FinalGate" not in state.summary
    assert "CAS" not in state.summary


def test_owner_state_explains_reconciliation_hold_without_exposing_engineering_codes() -> None:
    state = account_risk_owner_state_from_budget(
        {
            "claimed_position_slots": 1,
            "max_concurrent_positions": 2,
            "new_entry_allowed": False,
            "reconciliation_state": "mismatch",
        }
    )

    assert state.summary == "账户事实需要重新对账；系统已停止新开仓，现有保护继续运行"
    assert state.owner_action_required is True
