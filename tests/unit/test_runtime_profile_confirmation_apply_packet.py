from __future__ import annotations

from decimal import Decimal

from scripts import runtime_non_runtime_signal_profile_proposal as proposal_script
from scripts import runtime_profile_confirmation_apply_packet as apply_script
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


def _decision_packet() -> dict:
    proposal_packet = proposal_script.build_packet(
        selector_packet=_selector_packet([_rbr_signal()]),
        capital_base=Decimal("30"),
    )
    return decision_script.build_packet(
        proposal_packet=proposal_packet,
        created_at_ms=1781283600000,
    )


def test_apply_packet_waits_for_exact_owner_confirmation() -> None:
    packet = apply_script.build_packet(decision_packet=_decision_packet())

    assert packet["status"] == "waiting_for_owner_runtime_profile_confirmation"
    required = packet["owner_confirmation"]["required_value"]
    assert required == (
        "runtime-profile-confirm:RBR-001:RBR-001-v0:ADA/USDT:USDT:short:"
        "budget=6.00:notional=8.00:attempts=3:owner-authorized"
    )
    assert packet["owner_confirmation"]["provided"] is False
    assert packet["checks"]["ready_for_owner_authorized_runtime_profile_apply"] is False
    assert packet["source_decision_packet"]["status"] == (
        "ready_for_owner_codex_runtime_profile_confirmation"
    )
    assert packet["api_apply_plan"] is None
    assert packet["safety_invariants"]["runtime_created"] is False
    assert packet["safety_invariants"]["exchange_write_called"] is False


def test_apply_packet_rejects_confirmation_mismatch_without_api_plan() -> None:
    packet = apply_script.build_packet(
        decision_packet=_decision_packet(),
        owner_confirmation_value="wrong",
    )

    assert packet["status"] == "waiting_for_owner_runtime_profile_confirmation"
    assert packet["owner_confirmation"]["provided"] is True
    assert packet["owner_confirmation"]["matches"] is False
    assert packet["blockers"] == ["owner_runtime_profile_confirmation_mismatch"]
    assert packet["api_apply_plan"] is None
    assert packet["safety_invariants"]["promotion_confirmation_record_created"] is False


def test_apply_packet_blocks_without_trial_binding_after_confirmation() -> None:
    decision_packet = _decision_packet()
    required = apply_script.build_packet(
        decision_packet=decision_packet
    )["owner_confirmation"]["required_value"]

    packet = apply_script.build_packet(
        decision_packet=decision_packet,
        owner_confirmation_value=required,
    )

    assert packet["status"] == "blocked_runtime_profile_confirmation_apply_packet"
    assert packet["owner_confirmation"]["matches"] is True
    assert packet["blockers"] == ["trial_binding_id_required_for_runtime_draft"]
    assert packet["api_apply_plan"] is None
    assert packet["safety_invariants"]["runtime_created"] is False


def test_apply_packet_builds_two_step_api_plan_when_confirmed_and_bound() -> None:
    decision_packet = _decision_packet()
    required = apply_script.build_packet(
        decision_packet=decision_packet
    )["owner_confirmation"]["required_value"]

    packet = apply_script.build_packet(
        decision_packet=decision_packet,
        trial_binding_id="trial-binding-rbr-ada-short-1",
        owner_confirmation_value=required,
    )

    assert packet["status"] == "ready_for_owner_authorized_runtime_profile_apply"
    assert packet["checks"]["ready_for_owner_authorized_runtime_profile_apply"] is True
    assert packet["trial_binding_id"] == "trial-binding-rbr-ada-short-1"
    assert packet["source_decision_packet"]["proposal_id"] == (
        "experimental-runtime-profile:RBR-001:RBR-001-v0:ADA/USDT:USDT:short"
    )
    plan = packet["api_apply_plan"]
    assert plan["ready_to_apply"] is True
    assert plan["creates_promotion_confirmation_record_when_applied"] is True
    assert plan["creates_shadow_runtime_draft_when_applied"] is True
    assert plan["execution_enabled_after_apply"] is False
    assert plan["places_order_when_applied"] is False
    assert plan["calls_exchange_when_applied"] is False
    requests = plan["requests"]
    assert requests[0]["path"] == "/api/brc/strategy-runtime-promotion-confirmations"
    assert requests[0]["body"]["runtime_confirmations"][
        "short_side_conservative_profile_confirmed"
    ] is True
    assert "owner-confirmation://runtime-profile-confirm" in (
        requests[0]["body"]["evidence_refs"][-1]
    )
    assert requests[1]["path"].endswith("/runtime-drafts")
    assert requests[1]["body"]["trial_binding_id"] == (
        "trial-binding-rbr-ada-short-1"
    )
    assert requests[1]["body"]["metadata"]["execution_enabled"] is False
    assert requests[1]["body"]["metadata"]["shadow_mode"] is True
    assert packet["safety_invariants"]["runtime_created"] is False
    assert packet["safety_invariants"]["order_lifecycle_called"] is False


def test_apply_packet_blocks_source_decision_packet_not_ready() -> None:
    packet = apply_script.build_packet(
        decision_packet={
            "scope": "runtime_profile_decision_packet",
            "status": "blocked_runtime_profile_decision_packet",
            "strategy_family_id": "RMR-001",
            "strategy_family_version_id": "RMR-001-v0",
            "symbol": "ADA/USDT:USDT",
            "side": "long",
        }
    )

    assert packet["status"] == "blocked_runtime_profile_confirmation_apply_packet"
    assert "runtime_profile_decision_packet_not_ready" in packet["blockers"]
    assert "promotion_confirmation_request_template_missing" in packet["blockers"]
    assert packet["api_apply_plan"] is None
