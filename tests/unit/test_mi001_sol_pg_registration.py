from __future__ import annotations

from pathlib import Path
from typing import Any

from src.domain.brc_admission import (
    AdmissionExecutionMode,
    AdmissionTrialBindingStatus,
    TrialConstraintSnapshotStatus,
    TrialEnv,
    TrialStage,
)
from src.domain.mi001_sol_pg_registration import (
    MI001_CANDIDATE_ID,
    MI001_FAMILY_ID,
    MI001_PLAYBOOK_ID,
    MI001_SIDE,
    MI001_SYMBOL,
    build_mi001_sol_pg_registration_dry_run,
)
from src.domain.strategy_family_signal import FORBIDDEN_EXECUTION_FIELDS, SignalType


def _contains_key(value: Any, key: str) -> bool:
    if isinstance(value, dict):
        return any(str(item_key) == key or _contains_key(item_value, key) for item_key, item_value in value.items())
    if isinstance(value, list):
        return any(_contains_key(item, key) for item in value)
    return False


def test_builds_mi001_strategy_family_and_playbook_without_trial_risk_fields() -> None:
    payload = build_mi001_sol_pg_registration_dry_run(now_ms=1770000000000)

    family = payload.strategy_family_metadata
    playbook = payload.playbook_metadata

    assert family.family_id == MI001_FAMILY_ID
    assert family.version_id == "MI-001-smoke-v0"
    assert family.family_name == "Momentum Impulse"
    assert family.alpha_claim is False
    assert family.supported_symbols == [MI001_SYMBOL]
    assert SignalType.WOULD_ENTER in family.allowed_signal_types
    assert playbook.playbook_id == MI001_PLAYBOOK_ID
    assert playbook.parameter_profile["candidate_id"] == MI001_CANDIDATE_ID
    assert playbook.parameter_profile["allowed_direction"] == MI001_SIDE

    registry_dump = {
        "family": family.model_dump(mode="python"),
        "playbook": playbook.model_dump(mode="python"),
    }
    for forbidden in FORBIDDEN_EXECUTION_FIELDS:
        assert not _contains_key(registry_dump, forbidden)
    assert not _contains_key(registry_dump, "max_leverage")
    assert not _contains_key(registry_dump, "max_notional")


def test_candidate_admission_and_evidence_packet_are_pg_shaped() -> None:
    payload = build_mi001_sol_pg_registration_dry_run(now_ms=1770000000000)

    request = payload.admission_request
    evidence = payload.evidence_packet

    assert request.trial_env == TrialEnv.LIVE
    assert request.trial_stage == TrialStage.FUNDED_VALIDATION
    assert request.requested_execution_mode == AdmissionExecutionMode.OWNER_CONFIRM_EACH_ENTRY
    assert request.playbook_id == MI001_PLAYBOOK_ID
    assert request.account_facts_snapshot_json["real_account_api_called_by_registration"] is False

    summary = evidence.payload_json["broad_smoke_summary"]
    assert evidence.mandatory_complete is True
    assert summary["signal_count"] == 8135
    assert summary["24h_mean_forward_return"] == "0.6373"
    assert summary["72h_mean_forward_return"] == "1.9531"
    assert summary["72h_MFE"] == "10.2580"
    assert summary["72h_MAE"] == "-7.8922"
    assert summary["7d_mean_forward_return"] == "4.7372"
    assert set(evidence.payload_json["limitations"]) == {
        "no costs",
        "no slippage",
        "no funding",
        "no random baseline",
        "no campaign replay",
        "research-only",
    }
    assert evidence.payload_json["not_order"] is True
    assert evidence.payload_json["not_execution_intent"] is True


def test_owner_approval_is_plan_preparation_only() -> None:
    payload = build_mi001_sol_pg_registration_dry_run(now_ms=1770000000000)

    acceptance = payload.owner_risk_acceptance
    disclosure = acceptance.risk_disclosure_snapshot_json

    assert acceptance.trial_env == TrialEnv.LIVE
    assert acceptance.trial_stage == TrialStage.FUNDED_VALIDATION
    assert acceptance.account_facts_snapshot_ref
    assert disclosure["owner_approved_bounded_trial_plan_preparation"] is True
    assert disclosure["owner_has_not_approved_trial_start"] is True
    assert disclosure["owner_has_not_approved_automatic_execution"] is True
    assert acceptance.risk_policy_snapshot_json["max_leverage"] == 5
    assert acceptance.risk_policy_snapshot_json["max_attempts"] == 3


def test_trial_constraints_hold_risk_policy_without_granting_runtime_authority() -> None:
    payload = build_mi001_sol_pg_registration_dry_run(now_ms=1770000000000)

    snapshot = payload.trial_constraint_snapshot
    constraints = snapshot.constraints_json

    assert snapshot.status == TrialConstraintSnapshotStatus.PENDING_RISK_CAPITAL_RESOLUTION
    assert constraints["capital_source"] == "dedicated_subaccount"
    assert constraints["trial_risk_capital_rule"] == "current_dedicated_subaccount_equity"
    assert constraints["max_total_loss_rule"] == "current_dedicated_subaccount_equity"
    assert constraints["max_leverage"] == 5
    assert "current_dedicated_subaccount_equity * 5" in constraints["max_notional_rule"]
    assert constraints["allowed_symbol"] == MI001_SYMBOL
    assert constraints["allowed_side"] == MI001_SIDE
    assert constraints["allowed_candidate"] == MI001_FAMILY_ID
    assert constraints["max_attempts"] == 3
    assert constraints["no_auto_top_up"] is True
    assert constraints["no_transfer"] is True
    assert constraints["no_withdrawal"] is True
    assert constraints["no_symbol_expansion"] is True
    assert constraints["no_side_expansion"] is True
    assert constraints["no_leverage_expansion_above_5x"] is True
    assert constraints["operation_layer_gate_required"] is True
    assert constraints["kill_switch_required"] is True
    assert constraints["trial_start_requires_separate_owner_approval"] is True

    assert payload.safety_assertions["pg_write_performed"] is False
    assert payload.safety_assertions["execution_permission_granted"] is False
    assert payload.safety_assertions["order_capable_record_created"] is False


def test_planned_binding_cannot_imply_campaign_runtime_or_order_capability() -> None:
    payload = build_mi001_sol_pg_registration_dry_run(now_ms=1770000000000)

    binding = payload.trial_binding

    assert binding.binding_status == AdmissionTrialBindingStatus.PLANNED
    assert binding.campaign_id is None
    assert binding.runtime_carrier_id is None
    assert binding.execution_mode == AdmissionExecutionMode.OWNER_CONFIRM_EACH_ENTRY
    assert "fresh cached AccountSnapshot.total_balance" in payload.apply_blockers[0]
    assert payload.source_of_truth_status["trial_start_approval"] == "not_granted"


def test_builder_has_no_execution_order_or_exchange_dependencies() -> None:
    source = Path("src/domain/mi001_sol_pg_registration.py").read_text()

    assert "exchange_gateway" not in source
    assert "ExecutionIntent" not in source
    assert "OrderRepository" not in source
    assert "place_order" not in source
    assert "cancel_order" not in source
    assert "submit_order" not in source
    assert "set_leverage" not in source
    assert "withdraw(" not in source
    assert "transfer(" not in source
