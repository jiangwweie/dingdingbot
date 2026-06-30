from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.build_strategygroup_runtime_safety_state import (
    build_runtime_safety_state,
    validate_state_snapshot,
)


def _pre_live_ready() -> dict:
    return {
        "status": "pre_live_rehearsal_ready",
        "runtime_readiness_state": {
            "pre_live_rehearsal_ready": True,
            "live_submit_ready": False,
            "live_outcome_calibrated": False,
        },
        "interaction": {"calls_finalgate": False, "calls_operation_layer": False},
        "safety_invariants": {},
    }


def _pre_live_ready_legacy_decision_only() -> dict:
    return {
        "status": "pre_live_rehearsal_ready",
        "decision": {
            "pre_live_rehearsal_ready": True,
            "live_submit_ready": False,
            "real_order_authority": False,
        },
        "interaction": {"calls_finalgate": False, "calls_operation_layer": False},
        "safety_invariants": {},
    }


def _daily(status: str = "waiting_for_market") -> dict:
    return {"status": status}


def _cutover(status: str = "live_cutover_waiting_for_fresh_signal") -> dict:
    return {"status": status}


def _goal(status: str = "waiting_for_market") -> dict:
    return {"status": status}


def _completion(status: str = "not_complete_waiting_for_market") -> dict:
    return {"status": status}


def _ready_fact_sources() -> dict:
    return {
        "trusted_submit_fact_snapshot": {"status": "ready"},
        "account_facts": {"status": "fresh"},
        "position_open_order_conflict": {"status": "clear"},
        "budget_coverage": {"status": "sufficient"},
        "protection_template": {"status": "ready"},
        "submit_idempotency_policy": {"status": "ready"},
        "duplicate_submit_guard": {"status": "ready"},
        "protection_failure_policy": {"status": "ready"},
        "exchange_rules": {"status": "pass"},
    }


def _brf2_candidate_authorization_state() -> dict:
    return {
        "state_source": "brf2_shadow_candidate_evidence_provenance",
        "strategy_group_id": "BRF2-001",
        "status": "candidate_authorization_evidence_pending",
        "primary_judgment_source": False,
        "shadow_candidate_evidence_ready": True,
        "authorization_evidence_created": False,
        "ready_for_finalgate_checkpoint": False,
        "first_blocker_class": (
            "brf2_shadow_candidate_evidence_ready_authorization_evidence_not_created"
        ),
        "next_runtime_step": "prepare_fresh_candidate_authorization_evidence",
        "live_submit_authority": False,
        "operation_layer_authority": False,
        "actionable_now": False,
        "real_order_authority": False,
    }


def _brf2_shadow_candidate_evidence_ready() -> dict:
    return {
        "status": "brf2_shadow_candidate_evidence_ready",
        "strategy_group_id": "BRF2-001",
        "shadow_candidate_evidence_ready": True,
        "next_runtime_step": "prepare_fresh_candidate_authorization_evidence",
        "checks": {
            "actionable_now": False,
            "real_order_authority": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
    }


def test_no_signal_pre_live_ready_becomes_owner_waiting_without_blockers() -> None:
    state_snapshot = build_runtime_safety_state(
        pre_live_readiness=_pre_live_ready(),
        daily_check=_daily(),
        live_cutover=_cutover(),
        goal_progress=_goal(),
        completion_audit=_completion(),
    )

    assert state_snapshot["status"] == "live_submit_standby_waiting_for_market"
    assert state_snapshot["schema"] == "brc.strategygroup_runtime_safety_state.v1"
    assert state_snapshot["scope"] == "p0_runtime_safety_state"
    assert validate_state_snapshot(state_snapshot) == []
    assert "bridge" not in state_snapshot["schema"]
    assert "bridge" not in state_snapshot["scope"]
    assert "checks" not in state_snapshot
    assert "runtime_consumption" not in state_snapshot
    assert "state_family" not in state_snapshot
    assert state_snapshot["safety_invariants"]["local_runtime_safety_projection_only"] is True
    assert "local_bridge_only" not in state_snapshot["safety_invariants"]
    assert state_snapshot["owner_state"]["owner_intervention_required"] is False
    assert state_snapshot["runtime_safety_state"] == {
        "state_family": "Runtime Safety State",
        "status": "live_submit_standby_waiting_for_market",
        "primary_judgment_source": True,
        "pre_live_rehearsal_ready": True,
        "fresh_signal_state": "none",
        "hard_fact_blockers": [],
        "ready_for_finalgate_checkpoint": False,
        "live_submit_ready": False,
        "live_submit_ready_false_reason": "no_fresh_signal",
        "execution_attempt_required_for_lifecycle_entry": True,
        "readiness_separation": {
            "source": "runtime_safety_state",
            "trial_eligible": False,
            "tiny_live_ready": False,
            "pre_live_rehearsal_ready": True,
            "live_submit_ready": False,
            "ready_for_finalgate_checkpoint": False,
            "fresh_signal_state": "none",
            "live_submit_ready_false_reason": "no_fresh_signal",
            "can_create_execution_attempt": False,
            "execution_attempt_required_for_lifecycle_entry": True,
            "scoped_strategy_group_ids": [],
            "trial_eligible_source": "Strategy Asset State / Owner policy",
            "tiny_live_ready_source": (
                "Tradeability Decision / Runtime Safety State"
            ),
            "pre_live_rehearsal_ready_source": "Runtime Safety rehearsal",
            "live_submit_ready_source": "Runtime Safety action-time chain",
        },
        "source_sections": [
            "pre_live_rehearsal_readiness",
            "daily_check",
            "live_cutover",
            "goal_progress",
            "completion_audit",
            "action_time_required_facts_matrix",
        ],
    }
    assert state_snapshot["owner_state"]["owner_status"] == "waiting_for_opportunity"


def test_legacy_pre_live_decision_shape_does_not_unlock_runtime_safety() -> None:
    state_snapshot = build_runtime_safety_state(
        pre_live_readiness=_pre_live_ready_legacy_decision_only(),
        daily_check=_daily(),
        live_cutover=_cutover(),
        goal_progress=_goal(),
        completion_audit=_completion(),
    )

    assert state_snapshot["runtime_safety_state"]["pre_live_rehearsal_ready"] is False
    assert state_snapshot["runtime_safety_state"]["live_submit_ready"] is False
    assert "actionable_now" not in state_snapshot["runtime_safety_state"]
    assert "real_order_authority" not in state_snapshot["runtime_safety_state"]


def test_runtime_safety_state_can_carry_candidate_authorization_state() -> None:
    state_snapshot = build_runtime_safety_state(
        pre_live_readiness=_pre_live_ready(),
        daily_check=_daily("processing"),
        live_cutover=_cutover(),
        goal_progress=_goal("processing"),
        completion_audit=_completion(),
        fact_sources=_ready_fact_sources(),
        candidate_authorization_state=_brf2_candidate_authorization_state(),
        signal_status_override="fresh",
    )

    candidate_authorization = state_snapshot["runtime_safety_state"][
        "candidate_authorization_state"
    ]
    assert validate_state_snapshot(state_snapshot) == []
    assert candidate_authorization["state_family"] == "Runtime Safety State"
    assert candidate_authorization["state_role"] == "candidate_authorization"
    assert candidate_authorization["strategy_group_id"] == "BRF2-001"
    assert candidate_authorization["status"] == (
        "candidate_authorization_evidence_pending"
    )
    assert candidate_authorization["shadow_candidate_evidence_ready"] is True
    assert candidate_authorization["authorization_evidence_created"] is False
    assert candidate_authorization["ready_for_finalgate_checkpoint"] is False
    assert candidate_authorization["execution_attempt_required_for_lifecycle_entry"] is True
    assert "live_submit_authority" not in candidate_authorization
    assert "operation_layer_authority" not in candidate_authorization
    assert "actionable_now" not in candidate_authorization
    assert "real_order_authority" not in candidate_authorization
    assert "candidate_authorization_state" in (
        state_snapshot["runtime_safety_state"]["source_sections"]
    )


def test_runtime_safety_state_derives_candidate_authorization_from_brf2_evidence() -> None:
    state_snapshot = build_runtime_safety_state(
        pre_live_readiness=_pre_live_ready(),
        daily_check=_daily("processing"),
        live_cutover=_cutover(),
        goal_progress=_goal("processing"),
        completion_audit=_completion(),
        fact_sources=_ready_fact_sources(),
        brf2_shadow_candidate_evidence=(
            _brf2_shadow_candidate_evidence_ready()
        ),
        signal_status_override="fresh",
    )

    candidate_authorization = state_snapshot["runtime_safety_state"][
        "candidate_authorization_state"
    ]
    assert validate_state_snapshot(state_snapshot) == []
    assert candidate_authorization["state_source"] == (
        "brf2_shadow_candidate_evidence"
    )
    assert candidate_authorization["strategy_group_id"] == "BRF2-001"
    assert candidate_authorization["status"] == (
        "candidate_authorization_evidence_pending"
    )
    assert candidate_authorization["shadow_candidate_evidence_ready"] is True
    assert candidate_authorization["authorization_evidence_created"] is False
    assert candidate_authorization["next_runtime_step"] == (
        "prepare_fresh_candidate_authorization_evidence"
    )
    assert candidate_authorization["execution_attempt_required_for_lifecycle_entry"] is True
    assert "live_submit_authority" not in candidate_authorization
    assert "operation_layer_authority" not in candidate_authorization
    assert "actionable_now" not in candidate_authorization
    assert "real_order_authority" not in candidate_authorization


def test_fresh_signal_transitions_to_processing_requiredfacts_chain() -> None:
    state_snapshot = build_runtime_safety_state(
        pre_live_readiness=_pre_live_ready(),
        daily_check=_daily("processing"),
        live_cutover=_cutover(),
        goal_progress=_goal("processing"),
        completion_audit=_completion(),
        fact_sources=_ready_fact_sources(),
        signal_status_override="fresh",
    )

    assert state_snapshot["status"] == "processing_ready_for_finalgate_checkpoint"
    assert state_snapshot["fresh_signal_transition"]["current_state"] == "processing"
    assert state_snapshot["fresh_signal_transition"][
        "developer_audit_next_internal_gate_chain"
    ] == [
        "RequiredFacts",
        "candidate/auth",
        "FinalGate",
        "Operation Layer",
    ]
    assert "next_chain" not in state_snapshot["fresh_signal_transition"]
    assert (
        state_snapshot["fresh_signal_transition"][
            "signal_observation_grade_preempted_on_fresh_signal"
        ]
        is True
    )
    assert "p05_work_preempted_on_fresh_signal" not in (
        state_snapshot["fresh_signal_transition"]
    )
    assert state_snapshot["owner_state"]["owner_status"] == "processing"
    assert state_snapshot["runtime_safety_state"]["ready_for_finalgate_checkpoint"] is True
    assert state_snapshot["runtime_safety_state"]["readiness_separation"][
        "ready_for_finalgate_checkpoint"
    ] is True
    assert state_snapshot["runtime_safety_state"]["readiness_separation"][
        "can_create_execution_attempt"
    ] is False
    assert state_snapshot["runtime_safety_state"]["live_submit_ready_false_reason"] == (
        "awaiting_finalgate_and_operation_layer"
    )
    assert "action_time_submit_readiness_closure" not in state_snapshot
    facts_evidence = state_snapshot["action_time_required_facts_behavior_evidence"]
    assert facts_evidence["status"] == (
        "facts_behavior_ready_for_finalgate_checkpoint"
    )
    assert "live_submit_ready" not in facts_evidence
    assert "live_submit_ready_false_reason" not in facts_evidence
    assert "ready_for_finalgate_checkpoint" not in facts_evidence
    assert facts_evidence["strategy_uncertainty_blocks_engineering_progress"] is False
    assert facts_evidence[
        "owner_scoped_risk_acceptance_cannot_grant_runtime_authority"
    ] is True
    assert "owner_scoped_risk_acceptance_can_set_actionable_now" not in facts_evidence
    assert (
        state_snapshot["runtime_safety_state"]["live_submit_ready_false_reason"]
        == "awaiting_finalgate_and_operation_layer"
    )
    assert "actionable_now" not in state_snapshot["runtime_safety_state"]
    assert "real_order_authority" not in state_snapshot["runtime_safety_state"]


def test_missing_action_time_fact_is_localized_without_owner_evidence_operation() -> None:
    facts = _ready_fact_sources()
    facts["budget_coverage"] = {"status": "insufficient"}
    state_snapshot = build_runtime_safety_state(
        pre_live_readiness=_pre_live_ready(),
        daily_check=_daily("processing"),
        live_cutover=_cutover(),
        goal_progress=_goal("processing"),
        completion_audit=_completion(),
        fact_sources=facts,
        signal_status_override="fresh",
    )

    assert state_snapshot["status"] == "processing_action_time_facts_blocked"
    assert (
        "budget_coverage:insufficient"
        in state_snapshot["runtime_safety_state"]["hard_fact_blockers"]
    )
    assert state_snapshot["runtime_safety_state"]["hard_fact_blockers"] == [
        "budget_coverage:insufficient"
    ]
    assert state_snapshot["runtime_safety_state"]["live_submit_ready_false_reason"] == (
        "action_time_required_facts_not_ready"
    )
    assert state_snapshot["owner_state"]["owner_status"] == "temporarily_unavailable"
    assert (
        state_snapshot["owner_state"]["owner_manual_internal_evidence_review_required"]
        is False
    )
    assert "owner_manual_packet_read_required" not in state_snapshot["owner_state"]
    assert state_snapshot["runtime_safety_state"]["live_submit_ready"] is False


def test_missing_duplicate_submit_guard_blocks_finalgate_checkpoint() -> None:
    facts = _ready_fact_sources()
    facts["duplicate_submit_guard"] = {"status": "missing"}
    state_snapshot = build_runtime_safety_state(
        pre_live_readiness=_pre_live_ready(),
        daily_check=_daily("processing"),
        live_cutover=_cutover(),
        goal_progress=_goal("processing"),
        completion_audit=_completion(),
        fact_sources=facts,
        signal_status_override="fresh",
    )

    assert state_snapshot["status"] == "processing_action_time_facts_blocked"
    assert (
        "duplicate_submit_guard:missing"
        in state_snapshot["runtime_safety_state"]["hard_fact_blockers"]
    )
    assert state_snapshot["runtime_safety_state"]["ready_for_finalgate_checkpoint"] is False
    assert "action_time_submit_readiness_closure" not in state_snapshot
    facts_evidence = state_snapshot["action_time_required_facts_behavior_evidence"]
    assert facts_evidence["status"] == (
        "facts_behavior_gap_localized"
    )
    assert "live_submit_ready" not in facts_evidence
    assert "ready_for_finalgate_checkpoint" not in facts_evidence


def test_stale_trusted_submit_snapshot_and_missing_policy_are_localized() -> None:
    facts = _ready_fact_sources()
    facts["trusted_submit_fact_snapshot"] = {"status": "stale"}
    facts["protection_failure_policy"] = {"status": "missing"}
    state_snapshot = build_runtime_safety_state(
        pre_live_readiness=_pre_live_ready(),
        daily_check=_daily("processing"),
        live_cutover=_cutover(),
        goal_progress=_goal("processing"),
        completion_audit=_completion(),
        fact_sources=facts,
        signal_status_override="fresh",
    )

    blockers = state_snapshot["runtime_safety_state"]["hard_fact_blockers"]
    assert "trusted_submit_fact_snapshot:stale" in blockers
    assert "protection_failure_policy:missing" in blockers
    assert state_snapshot["owner_state"]["owner_status"] == "temporarily_unavailable"
    assert state_snapshot["runtime_safety_state"]["live_submit_ready"] is False


def test_operation_layer_input_shape_evidence_is_nested_under_execution_attempt() -> None:
    state_snapshot = build_runtime_safety_state(
        pre_live_readiness=_pre_live_ready(),
        daily_check=_daily(),
        live_cutover=_cutover(),
        goal_progress=_goal(),
        completion_audit=_completion(),
    )
    assert "operation_layer_input_boundary" not in state_snapshot
    p2 = state_snapshot["execution_attempt_rehearsal_preparation"]
    boundary = p2["operation_layer_input_shape_evidence"]

    assert boundary["input_shape_ready"] is True
    assert boundary["protection_params_shape_ready"] is True
    assert boundary["budget_context_shape_ready"] is True
    assert boundary["idempotency_key_shape_ready"] is True
    assert boundary["recovery_path_shape_ready"] is True
    assert boundary["finalgate_pass_required_before_submit"] is True
    assert boundary["exchange_write_authority_gated"] is True
    assert "live_submit_still_gated" not in boundary
    assert boundary["calls_operation_layer"] is False
    assert boundary["places_order"] is False
    assert boundary["operation_layer_submit_authority_required"] is True
    assert "real_order_authority" not in boundary


def test_p2_p3_p4_are_preparation_only_not_live_acceptance() -> None:
    state_snapshot = build_runtime_safety_state(
        pre_live_readiness=_pre_live_ready(),
        daily_check=_daily(),
        live_cutover=_cutover(),
        goal_progress=_goal(),
        completion_audit=_completion(),
    )

    assert "first_live_submit_closure_preparation" not in state_snapshot
    p2 = state_snapshot["execution_attempt_rehearsal_preparation"]
    assert p2["status"] == "execution_attempt_rehearsal_waiting_for_fresh_signal"
    assert p2["finalgate_checkpoint_input_shape_ready"] is True
    assert p2["operation_layer_input_shape_evidence"]["input_shape_ready"] is True
    assert "operation_layer_input_boundary_ready" not in p2
    assert "real_submit_completed" not in p2
    assert "live_submit_still_gated" not in p2
    assert p2["execution_attempt_required_for_lifecycle_entry"] is True
    assert "real_order_authority" not in p2

    p3 = state_snapshot["live_outcome_calibration_preparation"]
    assert p3["capture_schema_ready"] is True
    assert p3["live_outcome_calibrated"] is False
    assert p3["requires_real_live_outcome"] is True
    assert "realized_pnl" in p3["capture_fields"]

    p4 = state_snapshot["strategygroup_advancement_preparation"]
    assert p4["advancement_engine_ready_for_evidence"] is True
    assert p4["promotion_quality_final"] is False
    assert "actionable_now" not in p4
    assert "grant runtime authority" in p4["strategy_uncertainty_policy"]
    assert "promote" in p4["allowed_decisions"]


def test_negative_actionable_now_true_is_rejected() -> None:
    state_snapshot = build_runtime_safety_state(
        pre_live_readiness=_pre_live_ready(),
        daily_check=_daily(),
        live_cutover=_cutover(),
        goal_progress=_goal(),
        completion_audit=_completion(),
    )
    state_snapshot["runtime_safety_state"]["actionable_now"] = True

    errors = validate_state_snapshot(state_snapshot)

    assert (
        "runtime_safety_state_legacy_authority_mirror_present:actionable_now"
        in errors
    )


def test_negative_strategy_advancement_legacy_authority_mirror_is_rejected() -> None:
    state_snapshot = build_runtime_safety_state(
        pre_live_readiness=_pre_live_ready(),
        daily_check=_daily(),
        live_cutover=_cutover(),
        goal_progress=_goal(),
        completion_audit=_completion(),
    )
    state_snapshot["strategygroup_advancement_preparation"]["actionable_now"] = False

    errors = validate_state_snapshot(state_snapshot)

    assert "p4_legacy_authority_mirror_present:actionable_now" in errors


def test_negative_runtime_safety_state_live_submit_ready_true_is_rejected() -> None:
    state_snapshot = build_runtime_safety_state(
        pre_live_readiness=_pre_live_ready(),
        daily_check=_daily("processing"),
        live_cutover=_cutover(),
        goal_progress=_goal("processing"),
        completion_audit=_completion(),
        fact_sources=_ready_fact_sources(),
        signal_status_override="fresh",
    )
    state_snapshot["runtime_safety_state"]["live_submit_ready"] = True
    state_snapshot["runtime_safety_state"]["actionable_now"] = True
    state_snapshot["runtime_safety_state"]["real_order_authority"] = True

    errors = validate_state_snapshot(state_snapshot)

    assert "runtime_safety_state_live_submit_ready_requires_official_chain" in errors
    assert (
        "runtime_safety_state_legacy_authority_mirror_present:actionable_now"
        in errors
    )
    assert (
        "runtime_safety_state_legacy_authority_mirror_present:real_order_authority"
        in errors
    )


def test_cli_check_mode_passes_after_generation() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/build_strategygroup_runtime_safety_state.py"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    check = subprocess.run(
        [
            sys.executable,
            "scripts/build_strategygroup_runtime_safety_state.py",
            "--check",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert check.returncode == 0, check.stdout + check.stderr
    assert json.loads(check.stdout)["status"] == "passed"


def test_cli_does_not_read_default_brf2_shadow_evidence_without_explicit_input(
    tmp_path: Path,
) -> None:
    output_json = tmp_path / "runtime-safety-state.json"
    output_md = tmp_path / "runtime-safety-state.md"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_strategygroup_runtime_safety_state.py",
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    state_snapshot = json.loads(output_json.read_text(encoding="utf-8"))
    assert "candidate_authorization_state" not in state_snapshot["runtime_safety_state"]


def test_cli_explicit_brf2_shadow_candidate_evidence_input_feeds_runtime_safety(
    tmp_path: Path,
) -> None:
    brf2_shadow_candidate_evidence_json = tmp_path / "brf2-shadow-evidence.json"
    output_json = tmp_path / "runtime-safety-state.json"
    output_md = tmp_path / "runtime-safety-state.md"
    brf2_shadow_candidate_evidence_json.write_text(
        json.dumps(_brf2_shadow_candidate_evidence_ready()),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_strategygroup_runtime_safety_state.py",
            "--brf2-shadow-candidate-evidence-json",
            str(brf2_shadow_candidate_evidence_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    state_snapshot = json.loads(output_json.read_text(encoding="utf-8"))
    candidate_authorization = state_snapshot["runtime_safety_state"][
        "candidate_authorization_state"
    ]
    assert candidate_authorization["state_source"] == (
        "brf2_shadow_candidate_evidence"
    )
    assert candidate_authorization["shadow_candidate_evidence_ready"] is True
    assert candidate_authorization["execution_attempt_required_for_lifecycle_entry"] is True
    assert "actionable_now" not in candidate_authorization
    assert "real_order_authority" not in candidate_authorization
    assert "operation_layer_authority" not in candidate_authorization
