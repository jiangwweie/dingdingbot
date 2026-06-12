from __future__ import annotations

from decimal import Decimal

from scripts import runtime_non_runtime_signal_profile_proposal as proposal_script


def _selector_packet(signals: list[dict]) -> dict:
    return {
        "scope": "runtime_live_strategy_signal_selector",
        "status": "would_enter_available_but_not_runtime_compatible",
        "blockers": ["would_enter_signals_not_runtime_compatible"],
        "non_runtime_would_enter_signals": signals,
    }


def _rbr_signal() -> dict:
    return {
        "candidate_id": "RBR-001-ADA-SHORT",
        "strategy_family_id": "RBR-001",
        "strategy_family_version_id": "RBR-001-v0",
        "symbol": "ADA/USDT:USDT",
        "side": "short",
        "signal_type": "would_enter",
        "confidence": "0.57",
        "reason_codes": ["rbr_range_context", "rbr_boundary_rejection_confirmed"],
        "runtime_compatibility_blockers": [
            "runtime_strategy_family_mismatch",
            "runtime_strategy_family_version_mismatch",
            "runtime_symbol_mismatch",
        ],
        "runtime_compatible": False,
        "not_order": True,
        "not_execution_intent": True,
    }


def test_builds_ready_profile_proposal_from_non_runtime_rbr_signal() -> None:
    packet = proposal_script.build_packet(
        selector_packet=_selector_packet([_rbr_signal()]),
        capital_base=Decimal("30"),
    )

    assert packet["status"] == "ready_for_owner_runtime_profile_decision"
    proposal = packet["experimental_runtime_profile_proposal"]
    assert proposal["strategy_family_id"] == "RBR-001"
    assert proposal["strategy_family_version_id"] == "RBR-001-v0"
    assert proposal["symbol"] == "ADA/USDT:USDT"
    assert proposal["side"] == "short"
    assert proposal["status"] == "ready_for_owner_codex_confirmation"
    assert proposal["total_loss_budget"] == "6.00"
    assert proposal["max_loss_per_attempt"] == "2.00"
    assert proposal["max_notional_per_attempt"] == "8.00"
    assert proposal["max_attempts"] == 3
    assert proposal["max_leverage"] == "1"
    assert packet["runtime_boundary_preview"]["allowed_symbols"] == ["ADA/USDT:USDT"]
    assert packet["runtime_boundary_preview"]["allowed_sides"] == ["short"]
    assert packet["operator_command_plan"]["creates_runtime"] is False
    assert packet["operator_command_plan"]["requires_owner_runtime_profile_confirmation"] is True
    assert packet["safety_invariants"]["runtime_profile_mutated"] is False
    assert packet["safety_invariants"]["exchange_write_called"] is False


def test_blocks_when_selector_has_no_non_runtime_signal() -> None:
    packet = proposal_script.build_packet(
        selector_packet=_selector_packet([]),
        capital_base=Decimal("30"),
    )

    assert packet["status"] == "blocked_no_non_runtime_would_enter_signal"
    assert packet["blockers"] == ["non_runtime_would_enter_signal_missing"]
    assert packet["experimental_runtime_profile_proposal"] is None
    assert packet["operator_command_plan"]["creates_runtime"] is False
    assert packet["safety_invariants"]["order_created"] is False


def test_blocks_profile_proposal_for_non_candidate_strategy() -> None:
    rmr_signal = {
        **_rbr_signal(),
        "candidate_id": "RMR-001-ADA-LONG",
        "strategy_family_id": "RMR-001",
        "strategy_family_version_id": "RMR-001-v0",
        "side": "long",
    }
    packet = proposal_script.build_packet(
        selector_packet=_selector_packet([rmr_signal]),
        capital_base=Decimal("30"),
    )

    assert packet["status"] == "blocked_profile_proposal_not_ready"
    assert "strategy_binding_not_trade_candidate" in packet["blockers"]
    assert "regime_classifier_not_runtime_trade_strategy" in packet["blockers"]
    assert packet["operator_command_plan"]["creates_runtime"] is False
    assert packet["safety_invariants"]["execution_intent_created"] is False
