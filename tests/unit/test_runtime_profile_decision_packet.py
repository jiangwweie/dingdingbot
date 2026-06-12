from __future__ import annotations

from decimal import Decimal

from scripts import runtime_non_runtime_signal_profile_proposal as proposal_script
from scripts import runtime_profile_decision_packet as decision_script


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


def test_builds_owner_codex_runtime_profile_decision_packet_for_rbr_short() -> None:
    proposal_packet = proposal_script.build_packet(
        selector_packet=_selector_packet([_rbr_signal()]),
        capital_base=Decimal("30"),
    )
    packet = decision_script.build_packet(
        proposal_packet=proposal_packet,
        created_at_ms=1781283600000,
    )

    assert packet["status"] == "ready_for_owner_codex_runtime_profile_confirmation"
    assert packet["proposal_id"] == (
        "experimental-runtime-profile:RBR-001:RBR-001-v0:ADA/USDT:USDT:short"
    )
    assert packet["symbol"] == "ADA/USDT:USDT"
    assert packet["side"] == "short"
    assert packet["promotion_gate_preview"]["status"] == (
        "ready_for_controlled_runtime_execution_design"
    )
    assert "short_side_conservative_profile_confirmed" in (
        packet["owner_confirmation_keys"]
    )
    template = packet["promotion_confirmation_request_template"]
    assert template["strategy_family_id"] == "RBR-001"
    assert template["strategy_family_version_id"] == "RBR-001-v0"
    assert template["runtime_confirmations"][
        "short_side_conservative_profile_confirmed"
    ] is True
    assert template["runtime_profile_proposal_snapshot"]["total_loss_budget"] == "6.00"
    assert packet["runtime_draft_request_template"]["ready_to_submit"] is False
    assert packet["runtime_draft_request_template"]["execution_enabled"] is False
    assert packet["safety_invariants"]["promotion_confirmation_record_created"] is False
    assert packet["safety_invariants"]["runtime_created"] is False
    assert packet["safety_invariants"]["order_lifecycle_called"] is False
    assert packet["safety_invariants"]["exchange_write_called"] is False


def test_decision_packet_can_include_trial_binding_for_future_runtime_draft() -> None:
    proposal_packet = proposal_script.build_packet(
        selector_packet=_selector_packet([_rbr_signal()]),
        capital_base=Decimal("30"),
    )
    packet = decision_script.build_packet(
        proposal_packet=proposal_packet,
        trial_binding_id="trial-binding-rbr-ada-short-1",
        created_at_ms=1781283600000,
    )

    assert packet["status"] == "ready_for_owner_codex_runtime_profile_confirmation"
    assert packet["runtime_draft_request_template"]["ready_to_submit"] is True
    assert packet["runtime_draft_request_template"]["body"]["trial_binding_id"] == (
        "trial-binding-rbr-ada-short-1"
    )
    assert packet["operator_command_plan"]["this_packet_creates_runtime"] is False


def test_decision_packet_upgrades_legacy_short_proposal_keys() -> None:
    proposal_packet = proposal_script.build_packet(
        selector_packet=_selector_packet([_rbr_signal()]),
        capital_base=Decimal("30"),
    )
    proposal_packet["experimental_runtime_profile_proposal"][
        "owner_confirmation_keys"
    ].remove("short_side_conservative_profile_confirmed")

    packet = decision_script.build_packet(
        proposal_packet=proposal_packet,
        created_at_ms=1781283600000,
    )

    assert packet["status"] == "ready_for_owner_codex_runtime_profile_confirmation"
    assert "short_side_conservative_profile_confirmed" in (
        packet["owner_confirmation_keys"]
    )
    assert "short_side_conservative_profile_confirmed" in (
        packet["promotion_confirmation_request_template"][
            "runtime_profile_proposal_snapshot"
        ]["owner_confirmation_keys"]
    )


def test_decision_packet_blocks_when_profile_proposal_missing() -> None:
    packet = decision_script.build_packet(
        proposal_packet={
            "scope": "runtime_non_runtime_signal_profile_proposal",
            "status": "blocked_no_non_runtime_would_enter_signal",
        },
        created_at_ms=1781283600000,
    )

    assert packet["status"] == "blocked_runtime_profile_decision_packet"
    assert packet["blockers"] == ["runtime_profile_proposal_missing"]
    assert packet["promotion_confirmation_request_template"] is None
    assert packet["safety_invariants"]["runtime_created"] is False


def test_decision_packet_blocks_non_trade_strategy_profile() -> None:
    rmr_signal = {
        **_rbr_signal(),
        "candidate_id": "RMR-001-ADA-LONG",
        "strategy_family_id": "RMR-001",
        "strategy_family_version_id": "RMR-001-v0",
        "side": "long",
    }
    proposal_packet = proposal_script.build_packet(
        selector_packet=_selector_packet([rmr_signal]),
        capital_base=Decimal("30"),
    )
    packet = decision_script.build_packet(
        proposal_packet=proposal_packet,
        created_at_ms=1781283600000,
    )

    assert packet["status"] == "blocked_runtime_profile_decision_packet"
    assert "source_profile_packet_not_ready" in packet["blockers"]
    assert "regime_classifier_not_runtime_trade_strategy" in packet["blockers"]
    assert packet["promotion_confirmation_request_template"] is None
    assert packet["safety_invariants"]["order_created"] is False
