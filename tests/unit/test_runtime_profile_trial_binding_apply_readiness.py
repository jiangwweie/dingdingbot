from __future__ import annotations

from decimal import Decimal

from scripts import runtime_non_runtime_signal_profile_proposal as proposal_script
from scripts import runtime_profile_confirmation_apply_plan as apply_script
from scripts import runtime_profile_confirmation_record as confirmation_record_script
from scripts import runtime_profile_trial_binding_apply_readiness as readiness_script


def _selector_artifact(signals: list[dict]) -> dict:
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


def _confirmation_record() -> dict:
    proposal_artifact = proposal_script.build_profile_proposal_artifact(
        selector_artifact=_selector_artifact([_rbr_signal()]),
        capital_base=Decimal("30"),
    )
    return confirmation_record_script.build_record(
        proposal_artifact=proposal_artifact,
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


def _owner_confirmation(confirmation_record: dict) -> str:
    return apply_script.build_apply_plan(
        confirmation_record=confirmation_record,
    )["owner_confirmation"]["required_value"]


def test_resolves_matching_trial_binding_but_waits_for_owner_confirmation() -> None:
    confirmation_record = _confirmation_record()
    readiness_artifact = readiness_script.build_apply_readiness(
        apply_confirmation_record=confirmation_record,
        trial_bindings_payload=_bindings(_binding("binding-rbr-1")),
    )

    assert readiness_artifact["status"] == "waiting_for_owner_runtime_profile_confirmation"
    assert readiness_artifact["selected_trial_binding"]["binding_id"] == "binding-rbr-1"
    assert readiness_artifact["checks"]["matching_trial_binding_found"] is True
    assert readiness_artifact["checks"]["owner_confirmation_available"] is False
    assert readiness_artifact["apply_plan"]["api_apply_plan"] is None
    assert readiness_artifact["safety_invariants"]["runtime_created"] is False
    assert readiness_artifact["safety_invariants"]["exchange_write_called"] is False


def test_builds_ready_apply_plan_when_binding_and_confirmation_match() -> None:
    confirmation_record = _confirmation_record()
    readiness_artifact = readiness_script.build_apply_readiness(
        apply_confirmation_record=confirmation_record,
        trial_bindings_payload=_bindings(_binding("binding-rbr-1")),
        owner_confirmation_value=_owner_confirmation(confirmation_record),
    )

    assert readiness_artifact["status"] == "ready_for_runtime_profile_apply_with_trial_binding"
    assert readiness_artifact["checks"]["ready_for_runtime_profile_apply_with_trial_binding"] is True
    assert readiness_artifact["selected_trial_binding"]["binding_id"] == "binding-rbr-1"
    apply_plan = readiness_artifact["apply_plan"]
    assert apply_plan["status"] == "ready_for_owner_authorized_runtime_profile_apply"
    assert apply_plan["api_apply_plan"]["ready_to_apply"] is True
    requests = apply_plan["api_apply_plan"]["requests"]
    assert requests[0]["path"] == "/api/brc/strategy-runtime-promotion-confirmations"
    assert requests[1]["path"].endswith("/runtime-drafts")
    assert requests[1]["body"]["trial_binding_id"] == "binding-rbr-1"
    assert requests[1]["body"]["metadata"]["execution_enabled"] is False
    assert requests[1]["body"]["metadata"]["shadow_mode"] is True
    assert readiness_artifact["safety_invariants"]["order_lifecycle_called"] is False


def test_builds_ready_readiness_from_rtf037_waiting_plan() -> None:
    confirmation_record = _confirmation_record()
    waiting_apply_plan_artifact = apply_script.build_apply_plan(
        confirmation_record=confirmation_record
    )

    readiness_artifact = readiness_script.build_apply_readiness(
        apply_confirmation_record=waiting_apply_plan_artifact,
        trial_bindings_payload=_bindings(_binding("binding-rbr-1")),
        owner_confirmation_value=_owner_confirmation(confirmation_record),
    )

    assert readiness_artifact["status"] == "ready_for_runtime_profile_apply_with_trial_binding"
    assert "input_was_rtf037_apply_plan" in readiness_artifact["warnings"]
    assert readiness_artifact["apply_plan"]["api_apply_plan"]["ready_to_apply"] is True
    assert readiness_artifact["apply_plan"]["api_apply_plan"]["requests"][1]["body"][
        "trial_binding_id"
    ] == "binding-rbr-1"


def test_waits_when_no_matching_trial_binding_exists() -> None:
    readiness_artifact = readiness_script.build_apply_readiness(
        apply_confirmation_record=_confirmation_record(),
        trial_bindings_payload=_bindings(
            _binding("binding-cpm-1", version_id="CPM-RO-001-v0"),
        ),
    )

    assert readiness_artifact["status"] == "waiting_for_matching_trial_binding"
    assert readiness_artifact["selected_trial_binding"] is None
    assert readiness_artifact["blockers"] == ["matching_trial_binding_not_found"]
    assert readiness_artifact["candidate_trial_bindings"][0]["eligible"] is False
    assert "strategy_family_version_mismatch" in (
        readiness_artifact["candidate_trial_bindings"][0]["blockers"]
    )
    assert (
        readiness_artifact["safety_invariants"]["promotion_confirmation_record_created"]
        is False
    )


def test_terminal_binding_is_not_selected() -> None:
    readiness_artifact = readiness_script.build_apply_readiness(
        apply_confirmation_record=_confirmation_record(),
        trial_bindings_payload=_bindings(
            _binding("binding-rbr-old", status="runtime_installed"),
        ),
        owner_confirmation_value=_owner_confirmation(_confirmation_record()),
    )

    assert readiness_artifact["status"] == "waiting_for_matching_trial_binding"
    assert readiness_artifact["selected_trial_binding"] is None
    assert "trial_binding_invalid_or_terminal" in (
        readiness_artifact["candidate_trial_bindings"][0]["blockers"]
    )


def test_prefers_most_advanced_eligible_binding() -> None:
    confirmation_record = _confirmation_record()
    readiness_artifact = readiness_script.build_apply_readiness(
        apply_confirmation_record=confirmation_record,
        trial_bindings_payload=_bindings(
            _binding("binding-rbr-reserved", status="binding_reserved", updated_at_ms=2),
            _binding(
                "binding-rbr-constraints",
                status="runtime_constraints_installed",
                updated_at_ms=1,
            ),
        ),
        owner_confirmation_value=_owner_confirmation(confirmation_record),
    )

    assert (
        readiness_artifact["selected_trial_binding"]["binding_id"]
        == "binding-rbr-constraints"
    )
    assert readiness_artifact["status"] == "ready_for_runtime_profile_apply_with_trial_binding"
