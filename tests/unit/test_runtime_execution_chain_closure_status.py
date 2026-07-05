from __future__ import annotations

import json

from scripts import runtime_dry_run_audit_chain as audit_chain
from scripts import runtime_execution_chain_closure_status as closure_status


def test_closure_status_marks_non_market_chain_ready_but_not_real_submit_ready(tmp_path):
    audit_artifact = audit_chain.build_audit_artifact(tmp_path / "audit")

    artifact = closure_status.build_status_artifact(audit_artifact=audit_artifact)

    assert artifact["scope"] == "runtime_execution_chain_closure_status"
    assert artifact["status"] == "non_market_execution_chain_ready"
    assert artifact["dry_run_chain"]["status"] == "passed"
    assert artifact["dry_run_chain"]["scenario_count"] == 14
    assert artifact["dry_run_chain"]["required_checks_passed"] is True
    assert artifact["dry_run_chain"]["dangerous_effects_absent"] is True
    assert artifact["dry_run_chain"]["projected_checks"] == {
        "fresh_signal_fast_auto_chain_checked": True,
        "required_facts_readiness_checked": True,
        "execution_attempt_rehearsal_prepare_checked": True,
        "disabled_smoke_not_real_execution_proof": True,
        "ticket_bound_operation_layer_handoff_checked": True,
        "scoped_pipeline_operation_layer_submit_projection_checked": True,
        "legacy_authorization_finalgate_ready_retirement_checked": True,
        "legacy_authorization_submit_retirement_checked": True,
        "operation_layer_hard_safety_blocker_matrix_checked": True,
        "operation_layer_blocker_review_policy_checked": True,
        "operation_layer_authorization_chain_guard_checked": True,
        "ticket_bound_protected_submit_boundary_checked": True,
        "selected_strategygroup_dispatch_guard_checked": True,
        "all_selected_strategygroups_reach_finalgate_dispatch_checked": True,
        "shared_runtime_pipeline_checked": True,
        "common_execution_chain_reuse_checked": True,
        "strategygroup_adapter_boundary_checked": True,
        "strategy_intake_no_execution_pipeline_fields_checked": True,
        "runtime_tier_policy_checked": True,
        "only_mpg_tiny_real_order_eligible_checked": True,
        "new_strategygroups_default_observe_only_checked": True,
        "post_submit_closed_loop_evidence_guard_checked": True,
        "post_submit_exit_outcome_matrix_checked": True,
        "reduce_only_recovery_standing_authorization_checked": True,
        "operation_layer_submit_result_identity_guard_checked": True,
        "post_submit_finalize_result_identity_guard_checked": True,
    }
    assert artifact["dry_run_chain"]["missing_or_failed_segments"] == []
    assert artifact["dry_run_chain"]["goal_chain_segments"] == {
        "fresh_or_mock_signal": True,
        "required_facts_readiness": True,
        "candidate_authorization_evidence": True,
        "action_time_finalgate": True,
        "ticket_bound_operation_layer_handoff_projection": True,
        "disabled_dry_run_proof": True,
        "post_submit_exit_outcome_matrix": True,
    }
    assert artifact["dry_run_chain"]["goal_chain_segment_evidence"][
        "fresh_or_mock_signal"
    ] == {
        "required_checks": ["fresh_signal_fast_auto_chain_checked"],
        "scenario_names": ["mock_fresh_signal_dry_run_pass"],
        "scenario_statuses": {"mock_fresh_signal_dry_run_pass": "passed"},
        "checks_passed": True,
        "scenarios_passed": True,
        "ready": True,
    }
    assert artifact["dry_run_chain"]["goal_chain_segment_evidence"][
        "required_facts_readiness"
    ]["scenario_statuses"] == {
        "mock_fresh_signal_dry_run_pass": "passed",
        "required_facts_missing": "passed",
    }
    assert artifact["dry_run_chain"]["goal_chain_segment_evidence"][
        "ticket_bound_operation_layer_handoff_projection"
    ]["scenario_statuses"] == {
        "mock_fresh_signal_dry_run_pass": "passed",
        "scoped_pipeline_operation_layer_submit_projection": "passed",
    }
    assert artifact["dry_run_chain"]["goal_chain_segment_evidence"][
        "disabled_dry_run_proof"
    ]["scenario_statuses"] == {
        "mock_fresh_signal_dry_run_pass": "passed",
        "scoped_pipeline_operation_layer_submit_projection": "passed",
        "legacy_authorization_submit_retired": "passed",
    }
    assert artifact["dry_run_chain"]["goal_chain_segment_evidence"][
        "post_submit_exit_outcome_matrix"
    ]["scenario_statuses"] == {
        "post_submit_closed_loop_evidence_guard": "passed",
    }
    assert artifact["dry_run_chain"]["ready_goal_chain_segments"] == [
        "fresh_or_mock_signal",
        "required_facts_readiness",
        "candidate_authorization_evidence",
        "action_time_finalgate",
        "ticket_bound_operation_layer_handoff_projection",
        "disabled_dry_run_proof",
        "post_submit_exit_outcome_matrix",
    ]
    assert artifact["dry_run_chain"]["missing_or_failed_goal_chain_segments"] == []
    assert {
        "fresh_signal_fast_auto_chain_checked",
        "ticket_bound_operation_layer_handoff_checked",
        "scoped_pipeline_operation_layer_submit_projection_checked",
        "post_submit_closed_loop_evidence_guard_checked",
    }.issubset(set(artifact["dry_run_chain"]["ready_segments"]))
    assert artifact["real_execution"]["status"] == "waiting_for_live_action_time_proof"
    assert artifact["real_execution"]["real_order_allowed"] is False
    assert artifact["real_execution"]["disabled_smoke_is_real_execution_proof"] is False
    assert artifact["real_execution"]["live_closure_cutover_contract_status"] == "ready"
    assert artifact["real_execution"]["live_closure_stage_count"] == 9
    assert artifact["real_execution"]["missing_live_proof_stages"] == [
        "live_fresh_signal",
        "required_facts_ready",
        "candidate_authorization_bound",
        "action_time_finalgate_passed",
        "official_operation_layer_ready",
        "real_exchange_acceptance",
        "exchange_native_protection",
        "post_submit_finalize",
        "reconciliation_settlement_review",
    ]
    assert artifact["real_execution"]["missing_live_proofs"] == [
        "live_watcher_signal_packet_id",
        "required_facts_readiness_artifact_id",
        "candidate_id",
        "runtime_grant_id",
        "fresh_submit_authorization_id",
        "action_time_finalgate_packet_id",
        "operation_layer_submit_authorization_id",
        "exchange_submit_execution_result_id",
        "exchange_native_hard_stop_order_id",
        "runtime_post_submit_finalize_payload_id",
        "post_submit_reconciliation_evidence_id",
        "post_submit_budget_settlement_id",
        "submit_outcome_review_id",
    ]
    assert artifact["real_execution"]["missing_live_evidence_keys"] == artifact[
        "real_execution"
    ]["missing_live_proofs"]
    assert artifact["next_safe_actions"] == [
        "keep_watcher_running",
        "run_dry_run_audit_chain_after_runtime_changes",
        "on_fresh_signal_run_same_run_finalgate_then_official_operation_layer",
    ]
    assert artifact["safety_invariants"] == {
        "calls_tokyo_api": False,
        "exchange_write_called": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "withdrawal_or_transfer_created": False,
        "modifies_secret_or_credentials": False,
        "modifies_live_profile": False,
        "modifies_order_sizing_defaults": False,
        "finalgate_bypassed": False,
        "operation_layer_bypassed": False,
    }


def test_closure_status_blocks_when_required_dry_run_check_fails(tmp_path):
    audit_artifact = audit_chain.build_audit_artifact(tmp_path / "audit")
    audit_artifact["required_checks"]["fresh_signal_fast_auto_chain_checked"] = False

    artifact = closure_status.build_status_artifact(audit_artifact=audit_artifact)

    assert artifact["status"] == "non_market_execution_chain_blocked"
    assert artifact["dry_run_chain"]["status"] == "blocked"
    assert artifact["dry_run_chain"]["failed_required_checks"] == [
        "fresh_signal_fast_auto_chain_checked"
    ]
    assert artifact["dry_run_chain"]["projected_checks"][
        "fresh_signal_fast_auto_chain_checked"
    ] is False
    assert artifact["dry_run_chain"]["missing_or_failed_segments"] == [
        "fresh_signal_fast_auto_chain_checked"
    ]
    assert artifact["dry_run_chain"]["goal_chain_segments"][
        "fresh_or_mock_signal"
    ] is False
    assert artifact["dry_run_chain"]["goal_chain_segment_evidence"][
        "fresh_or_mock_signal"
    ]["checks_passed"] is False
    assert artifact["dry_run_chain"]["goal_chain_segment_evidence"][
        "fresh_or_mock_signal"
    ]["scenarios_passed"] is True
    assert artifact["dry_run_chain"]["missing_or_failed_goal_chain_segments"] == [
        "fresh_or_mock_signal",
        "candidate_authorization_evidence",
        "action_time_finalgate",
    ]
    assert artifact["real_execution"]["real_order_allowed"] is False
    assert artifact["next_safe_actions"] == [
        "repair_failed_dry_run_checks_before_waiting_for_market",
        "do_not_call_real_operation_layer",
    ]


def test_closure_status_cli_writes_artifact_atomically(tmp_path, capsys):
    audit_artifact = audit_chain.build_audit_artifact(tmp_path / "audit")
    audit_json = tmp_path / "runtime-dry-run-audit-chain.json"
    output_json = tmp_path / "runtime-execution-chain-closure-status.json"
    audit_json.write_text(json.dumps(audit_artifact), encoding="utf-8")

    assert closure_status.main(
        [
            "--audit-json",
            str(audit_json),
            "--output-json",
            str(output_json),
        ]
    ) == 0

    captured = capsys.readouterr()
    assert captured.out.startswith("{")
    artifact = json.loads(output_json.read_text(encoding="utf-8"))
    assert artifact["status"] == "non_market_execution_chain_ready"
    assert list(
        tmp_path.glob(".runtime-execution-chain-closure-status.json.*.tmp")
    ) == []
