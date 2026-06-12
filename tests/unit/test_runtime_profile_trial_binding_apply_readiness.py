from __future__ import annotations

from decimal import Decimal

from scripts import runtime_non_runtime_signal_profile_proposal as proposal_script
from scripts import runtime_profile_confirmation_apply_packet as apply_script
from scripts import runtime_profile_decision_packet as decision_script
from scripts import runtime_profile_trial_binding_apply_readiness as readiness_script


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


def _bindings(*bindings: dict) -> dict:
    return {"trial_bindings": list(bindings)}


def _binding(
    binding_id: str,
    *,
    version_id: str = "RBR-001-v0",
    status: str = "binding_reserved",
    updated_at_ms: int = 1781283600000,
) -> dict:
    return {
        "binding_id": binding_id,
        "admission_decision_id": f"decision-{binding_id}",
        "owner_risk_acceptance_id": f"risk-{binding_id}",
        "trial_constraint_snapshot_id": f"constraint-{binding_id}",
        "strategy_family_version_id": version_id,
        "playbook_id": "PB-BRC-LIVE-RUNTIME-V1",
        "trial_env": "live",
        "trial_stage": "funded_validation",
        "execution_mode": "auto_within_budget",
        "binding_status": status,
        "campaign_id": None,
        "runtime_carrier_id": None,
        "created_by_operation_id": f"op-{binding_id}",
        "created_by_preflight_id": f"preflight-{binding_id}",
        "created_at_ms": updated_at_ms - 1000,
        "updated_at_ms": updated_at_ms,
        "invalidated_at_ms": None,
        "invalidation_reason": None,
    }


def _owner_confirmation(decision_packet: dict) -> str:
    return apply_script.build_packet(
        decision_packet=decision_packet,
    )["owner_confirmation"]["required_value"]


def test_resolves_matching_trial_binding_but_waits_for_owner_confirmation() -> None:
    decision_packet = _decision_packet()
    packet = readiness_script.build_packet(
        apply_decision_packet=decision_packet,
        trial_bindings_payload=_bindings(_binding("binding-rbr-1")),
    )

    assert packet["status"] == "waiting_for_owner_runtime_profile_confirmation"
    assert packet["selected_trial_binding"]["binding_id"] == "binding-rbr-1"
    assert packet["checks"]["matching_trial_binding_found"] is True
    assert packet["checks"]["owner_confirmation_available"] is False
    assert packet["apply_packet"]["api_apply_plan"] is None
    assert packet["safety_invariants"]["runtime_created"] is False
    assert packet["safety_invariants"]["exchange_write_called"] is False


def test_builds_ready_apply_packet_when_binding_and_confirmation_match() -> None:
    decision_packet = _decision_packet()
    packet = readiness_script.build_packet(
        apply_decision_packet=decision_packet,
        trial_bindings_payload=_bindings(_binding("binding-rbr-1")),
        owner_confirmation_value=_owner_confirmation(decision_packet),
    )

    assert packet["status"] == "ready_for_runtime_profile_apply_with_trial_binding"
    assert packet["checks"]["ready_for_runtime_profile_apply_with_trial_binding"] is True
    assert packet["selected_trial_binding"]["binding_id"] == "binding-rbr-1"
    apply_packet = packet["apply_packet"]
    assert apply_packet["status"] == "ready_for_owner_authorized_runtime_profile_apply"
    assert apply_packet["api_apply_plan"]["ready_to_apply"] is True
    requests = apply_packet["api_apply_plan"]["requests"]
    assert requests[0]["path"] == "/api/brc/strategy-runtime-promotion-confirmations"
    assert requests[1]["path"].endswith("/runtime-drafts")
    assert requests[1]["body"]["trial_binding_id"] == "binding-rbr-1"
    assert requests[1]["body"]["metadata"]["execution_enabled"] is False
    assert requests[1]["body"]["metadata"]["shadow_mode"] is True
    assert packet["safety_invariants"]["order_lifecycle_called"] is False


def test_builds_ready_packet_from_rtf037_waiting_packet() -> None:
    decision_packet = _decision_packet()
    waiting_packet = apply_script.build_packet(decision_packet=decision_packet)

    packet = readiness_script.build_packet(
        apply_decision_packet=waiting_packet,
        trial_bindings_payload=_bindings(_binding("binding-rbr-1")),
        owner_confirmation_value=_owner_confirmation(decision_packet),
    )

    assert packet["status"] == "ready_for_runtime_profile_apply_with_trial_binding"
    assert "input_was_rtf037_apply_packet" in packet["warnings"]
    assert packet["apply_packet"]["api_apply_plan"]["ready_to_apply"] is True
    assert packet["apply_packet"]["api_apply_plan"]["requests"][1]["body"][
        "trial_binding_id"
    ] == "binding-rbr-1"


def test_waits_when_no_matching_trial_binding_exists() -> None:
    packet = readiness_script.build_packet(
        apply_decision_packet=_decision_packet(),
        trial_bindings_payload=_bindings(
            _binding("binding-cpm-1", version_id="CPM-RO-001-v0"),
        ),
    )

    assert packet["status"] == "waiting_for_matching_trial_binding"
    assert packet["selected_trial_binding"] is None
    assert packet["blockers"] == ["matching_trial_binding_not_found"]
    assert packet["candidate_trial_bindings"][0]["eligible"] is False
    assert "strategy_family_version_mismatch" in (
        packet["candidate_trial_bindings"][0]["blockers"]
    )
    assert packet["safety_invariants"]["promotion_confirmation_record_created"] is False


def test_terminal_binding_is_not_selected() -> None:
    packet = readiness_script.build_packet(
        apply_decision_packet=_decision_packet(),
        trial_bindings_payload=_bindings(
            _binding("binding-rbr-old", status="runtime_installed"),
        ),
        owner_confirmation_value=_owner_confirmation(_decision_packet()),
    )

    assert packet["status"] == "waiting_for_matching_trial_binding"
    assert packet["selected_trial_binding"] is None
    assert "trial_binding_invalid_or_terminal" in (
        packet["candidate_trial_bindings"][0]["blockers"]
    )


def test_prefers_most_advanced_eligible_binding() -> None:
    decision_packet = _decision_packet()
    packet = readiness_script.build_packet(
        apply_decision_packet=decision_packet,
        trial_bindings_payload=_bindings(
            _binding("binding-rbr-reserved", status="binding_reserved", updated_at_ms=2),
            _binding(
                "binding-rbr-constraints",
                status="runtime_constraints_installed",
                updated_at_ms=1,
            ),
        ),
        owner_confirmation_value=_owner_confirmation(decision_packet),
    )

    assert packet["selected_trial_binding"]["binding_id"] == "binding-rbr-constraints"
    assert packet["status"] == "ready_for_runtime_profile_apply_with_trial_binding"
