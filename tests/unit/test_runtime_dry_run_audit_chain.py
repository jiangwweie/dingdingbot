from __future__ import annotations

import json
import sys

from scripts import runtime_dry_run_audit_chain as audit_chain


def test_runtime_dry_run_audit_chain_covers_required_scenarios(tmp_path):
    packet = audit_chain.build_audit_chain(tmp_path)

    assert packet["schema"] == "brc.runtime_dry_run_audit_chain.v1"
    assert packet["scope"] == "runtime_dry_run_audit_chain"
    assert packet["status"] == "passed"
    assert packet["scenario_count"] == 14
    assert packet["checks"]["scenario_count"] == 14
    assert packet["checks"]["all_scenarios_passed"] is True
    assert packet["checks"]["dangerous_effects_absent"] is True
    assert packet["summary"] == {
        "scenario_count": 14,
        "required_checks_present": True,
        "all_scenarios_passed": True,
        "dangerous_effects_absent": True,
        "disabled_smoke_is_real_execution_proof": False,
        "shared_runtime_pipeline_checked": True,
        "common_execution_chain_reuse_checked": True,
        "strategygroup_adapter_boundary_checked": True,
        "allocated_subaccount_profile_boundary_checked": True,
        "strategy_handoff_no_execution_pipeline_fields_checked": True,
        "runtime_replay_lab_checked": True,
        "mpg001_replay_sample_checked": True,
        "mpg001_replay_corpus_checked": True,
        "btpc001_l2_shadow_replay_checked": True,
        "vcb001_l1_observe_replay_checked": True,
        "lsr001_l1_observe_replay_checked": True,
        "synthetic_signal_fixture_set_checked": True,
        "post_submit_simulator_matrix_checked": True,
        "cost_review_skeleton_checked": True,
        "external_replay_adapter_sidecar_only_checked": True,
        "runtime_tier_policy_checked": True,
        "only_mpg_tiny_real_order_eligible_checked": True,
        "new_strategygroups_default_observe_only_checked": True,
        "selected_strategygroup_dispatch_guard_checked": True,
        "all_selected_strategygroups_reach_finalgate_dispatch_checked": True,
        "operation_layer_hard_safety_blocker_matrix_checked": True,
        "expanded_watcher_scope_execution_guard_checked": True,
        "operation_layer_authorization_chain_guard_checked": True,
        "operation_layer_standing_authorization_relay_checked": True,
        "post_submit_closed_loop_evidence_guard_checked": True,
        "post_submit_exit_outcome_matrix_checked": True,
        "reduce_only_recovery_standing_authorization_checked": True,
        "operation_layer_submit_result_identity_guard_checked": True,
        "post_submit_finalize_result_identity_guard_checked": True,
        "non_executing_prepare_auto_bridge_checked": True,
        "required_facts_readiness_checked": True,
        "scoped_pipeline_operation_layer_handoff_checked": True,
    }
    assert packet["required_checks"] == {
        "all_scenarios_passed": True,
        "dangerous_effects_absent": True,
        "disabled_smoke_not_real_execution_proof": True,
        "fresh_signal_fast_auto_chain_checked": True,
        "required_facts_readiness_checked": True,
        "non_executing_prepare_auto_bridge_checked": True,
        "legacy_local_registration_probe_tolerance_checked": True,
        "mock_operation_layer_closed_loop_checked": True,
        "operation_layer_blocker_review_policy_checked": True,
        "operation_layer_hard_safety_blocker_matrix_checked": True,
        "expanded_watcher_scope_execution_guard_checked": True,
        "operation_layer_authorization_chain_guard_checked": True,
        "operation_layer_standing_authorization_relay_checked": True,
        "post_submit_closed_loop_evidence_guard_checked": True,
        "post_submit_exit_outcome_matrix_checked": True,
        "reduce_only_recovery_standing_authorization_checked": True,
        "operation_layer_submit_result_identity_guard_checked": True,
        "post_submit_finalize_result_identity_guard_checked": True,
        "operation_layer_evidence_relay_checked": True,
        "scoped_pipeline_operation_layer_handoff_checked": True,
        "required_scenarios_present": True,
        "common_execution_chain_reuse_checked": True,
        "strategygroup_adapter_boundary_checked": True,
        "allocated_subaccount_profile_boundary_checked": True,
        "strategy_handoff_no_execution_pipeline_fields_checked": True,
        "runtime_replay_lab_checked": True,
        "mpg001_replay_sample_checked": True,
        "mpg001_replay_corpus_checked": True,
        "btpc001_l2_shadow_replay_checked": True,
        "vcb001_l1_observe_replay_checked": True,
        "lsr001_l1_observe_replay_checked": True,
        "synthetic_signal_fixture_set_checked": True,
        "post_submit_simulator_matrix_checked": True,
        "cost_review_skeleton_checked": True,
        "external_replay_adapter_sidecar_only_checked": True,
        "runtime_tier_policy_checked": True,
        "only_mpg_tiny_real_order_eligible_checked": True,
        "new_strategygroups_default_observe_only_checked": True,
        "selected_strategygroup_dispatch_guard_checked": True,
        "all_selected_strategygroups_reach_finalgate_dispatch_checked": True,
        "shared_runtime_pipeline_checked": True,
    }
    assert packet["safety_invariants"]["exchange_write_called"] is False
    assert packet["safety_invariants"]["order_created"] is False
    assert packet["safety_invariants"]["order_lifecycle_called"] is False
    assert packet["safety_invariants"]["withdrawal_or_transfer_created"] is False
    assert packet["safety_invariants"]["disabled_smoke_is_real_execution_proof"] is False

    scenarios = {item["name"]: item for item in packet["scenarios"]}
    assert set(scenarios) == {
        "no_signal",
        "mock_fresh_signal_dry_run_pass",
        "scoped_pipeline_operation_layer_handoff",
        "non_executing_prepare_auto_bridge",
        "mock_operation_layer_submit_finalize_pass",
        "required_facts_missing",
        "active_position_or_open_order_conflict",
        "operation_layer_blocker_review_matrix",
        "selected_strategygroup_dispatch_guard",
        "expanded_watcher_scope_execution_guard",
        "operation_layer_authorization_chain_guard",
        "post_submit_closed_loop_evidence_guard",
        "operation_layer_submit_result_identity_guard",
        "post_submit_finalize_result_identity_guard",
    }
    assert scenarios["no_signal"]["artifacts"]["resume_dispatch"]["command_plan"] is None
    assert (
        scenarios["mock_fresh_signal_dry_run_pass"]["artifacts"][
            "operation_layer_evidence_prep"
        ]["status"]
        == "operation_layer_ready"
    )
    assert (
        scenarios["mock_fresh_signal_dry_run_pass"]["artifacts"][
            "disabled_submit_smoke"
        ]["status"]
        == "disabled_smoke_passed"
    )
    relay_checks = scenarios["mock_fresh_signal_dry_run_pass"]["artifacts"][
        "operation_layer_relay_checks"
    ]
    fast_auto_chain_checks = scenarios["mock_fresh_signal_dry_run_pass"][
        "artifacts"
    ]["fast_auto_chain_checks"]
    assert fast_auto_chain_checks == {
        "fresh_signal_to_authorization_ready": True,
        "fresh_signal_within_freshness_window": True,
        "stale_signal_rejected_by_freshness_window": True,
        "authorization_to_finalgate_dispatch_ready": True,
        "finalgate_to_operation_layer_evidence_ready": True,
        "operation_layer_real_submit_still_not_called": True,
    }
    freshness_checks = scenarios["mock_fresh_signal_dry_run_pass"]["artifacts"][
        "fresh_signal_freshness_checks"
    ]
    assert freshness_checks["status"] == "passed"
    assert freshness_checks["freshness_window_seconds"] == 120
    assert freshness_checks["checks"] == {
        "freshness_window_seconds_matches_pilot": True,
        "signal_timestamp_present": True,
        "fresh_signal_within_window": True,
        "fresh_signal_can_enter_fast_chain": True,
        "stale_signal_rejected_by_window": True,
    }
    assert freshness_checks["safety_invariants"]["exchange_write_called"] is False
    assert relay_checks == {
        "required_evidence_ids_present": True,
        "no_missing_evidence_ids": True,
        "operation_layer_ready_flag_true": True,
        "operation_layer_official_endpoint_selected": True,
        "standing_authorization_bound_for_first_real_submit": True,
        "owner_chat_confirmation_not_required_for_first_real_submit": True,
        "legacy_owner_confirmation_env_not_required": True,
        "same_authorization_chain": True,
        "action_time_finalgate_called": True,
        "action_time_finalgate_passed": True,
        "closed_loop_uses_same_authorization": True,
    }
    legacy_probe = scenarios["mock_fresh_signal_dry_run_pass"]["artifacts"][
        "legacy_local_registration_probe_tolerance"
    ]
    assert legacy_probe["status"] == "operation_layer_ready"
    assert legacy_probe["blockers"] == []
    assert (
        "legacy_prepare_machine_evidence_probe_blocker_satisfied_by_"
        "local_registration_adapter_result"
    ) in legacy_probe["warnings"]
    closed_loop = scenarios["mock_fresh_signal_dry_run_pass"]["artifacts"][
        "closed_loop_shape"
    ]
    assert closed_loop["status"] == "shape_checked"
    assert closed_loop["closed_loop_checks"] == {
        "finalize_shape_present": True,
        "reconciliation_shape_present": True,
        "budget_settlement_shape_present": True,
        "review_record_shape_present": True,
        "next_attempt_gate_shape_present": True,
    }
    assert closed_loop["reconciliation_result"]["status"] == "clean"
    assert closed_loop["budget_settlement_result"]["status"] == "settled"
    assert closed_loop["review_record_result"]["status"] == "recorded"
    operation_closed_loop = scenarios["mock_operation_layer_submit_finalize_pass"][
        "artifacts"
    ]["mock_operation_layer_closed_loop"]
    assert operation_closed_loop["status"] == "passed"
    assert operation_closed_loop["simulated_exchange_effects"] is True
    assert operation_closed_loop["actual_exchange_write_called"] is False
    assert operation_closed_loop["actual_order_created"] is False
    assert operation_closed_loop["actual_order_lifecycle_called"] is False
    assert operation_closed_loop["actual_withdrawal_or_transfer_created"] is False
    assert operation_closed_loop["checks"] == {
        "dispatcher_reached_settled_status": True,
        "submit_endpoint_called_once": True,
        "finalize_endpoint_called_once": True,
        "next_attempt_gate_ready": True,
        "budget_settlement_recorded": True,
        "review_recorded": True,
        "no_withdrawal_or_transfer": True,
    }
    assert operation_closed_loop["dispatcher_packet"]["status"] == "settled"
    assert operation_closed_loop["dispatcher_packet"]["dispatch_status"] == (
        "post_submit_finalize_completed_next_attempt_ready"
    )
    assert scenarios["required_facts_missing"]["artifacts"]["readiness_bridge"][
        "status"
    ] == "ready_for_readiness_evidence"
    assert scenarios["active_position_or_open_order_conflict"]["artifacts"][
        "resume_dispatch"
    ]["blocker_class"] == "active_position_resolution"
    matrix = scenarios["operation_layer_blocker_review_matrix"]["artifacts"][
        "review_matrix"
    ]
    matrix_checks = scenarios["operation_layer_blocker_review_matrix"]["artifacts"][
        "matrix_checks"
    ]
    assert matrix_checks == {
        "expected_blocker_cases_present": True,
        "all_cases_block_real_submit": True,
        "all_cases_avoid_operation_layer_submit": True,
        "all_cases_have_owner_review_state": True,
        "all_cases_have_no_dangerous_effects": True,
    }
    assert set(matrix) == {
        "active_position",
        "open_order",
        "protection_missing",
        "budget_missing",
        "duplicate_submit_risk",
        "symbol_scope_mismatch",
        "side_scope_mismatch",
        "notional_scope_mismatch",
        "leverage_scope_mismatch",
    }
    for case in matrix.values():
        assert all(case["checks"].values())
        assert case["packet"]["status"] == "operation_layer_blocked"
        assert case["packet"]["operation_layer_blocker_review"][
            "project_progress_allowed"
        ] is True
        assert case["packet"]["operation_layer_blocker_review"][
            "continue_observation_allowed"
        ] is True
        assert case["packet"]["operation_layer_blocker_review"][
            "real_submit_allowed"
        ] is False
    assert packet["checks"]["operation_layer_evidence_relay_checked"] is True
    assert (
        packet["checks"]["operation_layer_standing_authorization_relay_checked"]
        is True
    )
    assert packet["checks"]["scoped_pipeline_operation_layer_handoff_checked"] is True
    assert packet["checks"]["fresh_signal_fast_auto_chain_checked"] is True
    assert packet["checks"]["required_facts_readiness_checked"] is True
    assert packet["checks"]["non_executing_prepare_auto_bridge_checked"] is True
    replay_lab = packet["runtime_replay_lab_validation"]
    assert replay_lab["status"] == "passed"
    assert replay_lab["strategy_group_id"] == "MPG-001"
    assert replay_lab["checks"]["mpg001_replay_sample_present"] is True
    assert replay_lab["checks"]["mpg001_replay_corpus_cases_present"] is True
    assert replay_lab["checks"]["btpc001_l2_shadow_replay_cases_present"] is True
    assert replay_lab["checks"]["btpc001_l2_would_enter_review_shape_present"] is True
    assert (
        replay_lab["checks"]["btpc001_l2_blocked_cases_do_not_reach_operation_layer"]
        is True
    )
    assert replay_lab["checks"]["vcb001_l1_observe_replay_cases_present"] is True
    assert replay_lab["checks"]["vcb001_l1_would_enter_review_shape_present"] is True
    assert (
        replay_lab["checks"]["vcb001_l1_cases_do_not_reach_prepare_or_operation_layer"]
        is True
    )
    assert replay_lab["checks"]["lsr001_l1_observe_replay_cases_present"] is True
    assert replay_lab["checks"]["lsr001_l1_would_enter_review_shape_present"] is True
    assert (
        replay_lab["checks"]["lsr001_l1_cases_do_not_reach_prepare_or_operation_layer"]
        is True
    )
    assert replay_lab["checks"]["synthetic_fixture_cases_present"] is True
    assert replay_lab["checks"]["post_submit_simulator_cases_present"] is True
    assert replay_lab["checks"]["cost_review_skeleton_present"] is True
    assert replay_lab["checks"]["external_framework_sidecar_only"] is True
    assert replay_lab["l2_shadow_replay_samples"]
    assert replay_lab["l1_observe_replay_samples"]
    assert replay_lab["post_submit_simulator_matrix"]
    assert replay_lab["safety_invariants"]["exchange_write_called"] is False
    assert replay_lab["safety_invariants"]["real_order_created"] is False
    assert packet["checks"][
        "legacy_local_registration_probe_tolerance_checked"
    ] is True
    assert packet["checks"]["mock_operation_layer_closed_loop_checked"] is True
    assert packet["checks"]["operation_layer_blocker_review_policy_checked"] is True
    assert (
        packet["checks"]["operation_layer_hard_safety_blocker_matrix_checked"]
        is True
    )
    assert packet["checks"]["expanded_watcher_scope_execution_guard_checked"] is True
    assert packet["checks"]["operation_layer_authorization_chain_guard_checked"] is True
    assert packet["checks"]["post_submit_closed_loop_evidence_guard_checked"] is True
    assert packet["checks"]["post_submit_exit_outcome_matrix_checked"] is True
    assert (
        packet["checks"]["operation_layer_submit_result_identity_guard_checked"]
        is True
    )
    assert (
        packet["checks"]["post_submit_finalize_result_identity_guard_checked"]
        is True
    )
    assert packet["checks"]["shared_runtime_pipeline_checked"] is True
    assert packet["checks"]["common_execution_chain_reuse_checked"] is True
    assert packet["checks"]["strategygroup_adapter_boundary_checked"] is True
    assert (
        packet["checks"]["strategy_handoff_no_execution_pipeline_fields_checked"]
        is True
    )
    assert packet["checks"]["runtime_tier_policy_checked"] is True
    assert packet["checks"]["only_mpg_tiny_real_order_eligible_checked"] is True
    assert (
        packet["checks"]["new_strategygroups_default_observe_only_checked"]
        is True
    )
    assert packet["checks"]["selected_strategygroup_dispatch_guard_checked"] is True
    scoped_handoff = scenarios["scoped_pipeline_operation_layer_handoff"][
        "artifacts"
    ]
    assert scoped_handoff["checks"] == {
        "pipeline_reaches_scoped_local_registration_recorded": True,
        "pipeline_reports_operation_layer_evidence_ready": True,
        "dispatcher_accepts_pipeline_evidence": True,
        "operation_layer_readiness_has_no_missing_ids": True,
        "operation_layer_submit_not_called": True,
        "pipeline_does_not_exchange_write": True,
        "scoped_pipeline_disabled_submit_smoke_passed": True,
    }
    assert scoped_handoff["scoped_disabled_submit_checks"] == {
        "handoff_query_uses_pipeline_evidence_ids": True,
        "disabled_smoke_called_official_endpoint": True,
        "disabled_smoke_keeps_owner_real_submit_false": True,
        "disabled_smoke_does_not_exchange_write": True,
        "disabled_smoke_does_not_create_order": True,
        "disabled_smoke_does_not_call_order_lifecycle": True,
        "dispatcher_disabled_smoke_mode_passed": True,
        "dispatcher_disabled_smoke_keeps_real_confirm_false": True,
        "dispatcher_disabled_smoke_does_not_exchange_write": True,
    }
    assert scoped_handoff["scoped_disabled_submit_smoke"]["status"] == (
        "disabled_smoke_passed"
    )
    assert scoped_handoff["scoped_disabled_submit_smoke"]["safety_invariants"][
        "exchange_write_called"
    ] is False
    assert scoped_handoff["dispatcher_disabled_submit_smoke"]["status"] == (
        "operation_layer_disabled_smoke_passed"
    )
    assert scoped_handoff["dispatcher_disabled_submit_smoke"]["safety_invariants"][
        "exchange_write_called"
    ] is False
    assert scoped_handoff["pipeline_report"]["status"] == (
        "scoped_local_registration_proof_recorded"
    )
    assert scoped_handoff["resume_dispatch"]["status"] == "operation_layer_ready"
    assert scoped_handoff["resume_dispatch"]["safety_invariants"][
        "official_operation_layer_submit_called"
    ] is False
    selected_guard = scenarios["selected_strategygroup_dispatch_guard"]["artifacts"]
    assert selected_guard["checks"] == {
        "selected_mpg_dispatch_reaches_finalgate_plan": True,
        "all_selected_strategygroups_reach_finalgate_dispatch": True,
        "out_of_scope_signal_blocked_before_finalgate": True,
        "out_of_scope_signal_does_not_call_operation_layer": True,
        "no_dangerous_effects": True,
    }
    assert set(selected_guard["selected_strategygroup_dispatches"]) == {
        "MPG-001",
        "TEQ-001",
        "FBS-001",
        "SOR-001",
        "PMR-001",
    }
    assert all(selected_guard["selected_strategygroup_dispatch_checks"].values())
    for strategy_group_id, dispatch in selected_guard[
        "selected_strategygroup_dispatches"
    ].items():
        assert dispatch["status"] == "ready_for_action_time_final_gate"
        assert dispatch["dispatch_action"] == (
            "run_official_action_time_final_gate_preflight"
        )
        assert dispatch["selected_strategy_group_id"] == strategy_group_id
    assert selected_guard["selected_mpg_dispatch"]["dispatch_action"] == (
        "run_official_action_time_final_gate_preflight"
    )
    assert selected_guard["out_of_scope_dispatch"]["dispatch_status"] == (
        "blocked_by_selected_strategygroup_scope"
    )
    assert selected_guard["out_of_scope_dispatch"]["command_plan"] is None
    auto_bridge = scenarios["non_executing_prepare_auto_bridge"]["artifacts"]
    assert auto_bridge["checks"] == {
        "prepare_runner_called_once": True,
        "prepare_uses_runtime_and_signal_input": True,
        "prepare_result_ready_for_finalgate": True,
        "dispatcher_reaches_finalgate_ready": True,
        "finalgate_called_once": True,
        "operation_layer_submit_not_called": True,
        "no_dangerous_effects": True,
    }
    assert auto_bridge["resume_dispatch"]["status"] == "finalgate_ready"
    assert auto_bridge["resume_dispatch"]["dispatch_action"] == (
        "prepare_official_operation_layer_submit"
    )
    assert auto_bridge["resume_dispatch"]["safety_invariants"][
        "official_non_executing_prepare_called"
    ] is True
    assert auto_bridge["resume_dispatch"]["safety_invariants"][
        "official_operation_layer_submit_called"
    ] is False
    expanded_guard = scenarios["expanded_watcher_scope_execution_guard"][
        "artifacts"
    ]
    assert expanded_guard["checks"] == {
        "expanded_scope_observation_allowed": True,
        "ambiguous_actionable_scope_blocked": True,
        "out_of_scope_actionable_signal_blocked": True,
        "finalgate_not_called_for_blocked_scope": True,
        "operation_layer_not_called_for_blocked_scope": True,
        "no_dangerous_effects": True,
    }
    assert expanded_guard["expanded_observation"]["dispatch_action"] == (
        "continue_watcher_observation"
    )
    assert expanded_guard["ambiguous_action"]["blockers"] == [
        "missing_fact:selected_strategy_group_id_for_action"
    ]
    assert expanded_guard["out_of_scope_action"]["dispatch_status"] == (
        "blocked_by_selected_strategygroup_scope"
    )
    authorization_guard = scenarios["operation_layer_authorization_chain_guard"][
        "artifacts"
    ]
    assert authorization_guard["checks"] == {
        "stale_authorization_evidence_blocked": True,
        "missing_authorization_evidence_blocked": True,
        "stale_evidence_does_not_call_operation_layer": True,
        "missing_auth_does_not_call_operation_layer": True,
        "no_dangerous_effects": True,
    }
    assert authorization_guard["stale_operation_layer"]["status"] == (
        "operation_layer_submit_blocked"
    )
    assert authorization_guard["missing_auth_operation_layer"]["status"] == (
        "operation_layer_submit_blocked"
    )
    assert authorization_guard["stale_operation_layer"][
        "operation_layer_submit_result"
    ]["called"] is False
    assert authorization_guard["missing_auth_operation_layer"][
        "operation_layer_submit_result"
    ]["called"] is False
    closed_loop_guard = scenarios["post_submit_closed_loop_evidence_guard"][
        "artifacts"
    ]["post_submit_closed_loop_evidence_guard"]
    assert closed_loop_guard["status"] == "passed"
    assert closed_loop_guard["simulated_exchange_effects"] is True
    assert closed_loop_guard["actual_exchange_write_called"] is False
    assert closed_loop_guard["actual_order_created"] is False
    assert closed_loop_guard["actual_order_lifecycle_called"] is False
    assert closed_loop_guard["actual_withdrawal_or_transfer_created"] is False
    assert closed_loop_guard["checks"] == {
        "all_incomplete_closed_loop_cases_block_next_attempt": True,
        "exit_outcome_matrix_expected_cases_present": True,
        "exit_outcome_matrix_all_cases_have_accounting_policy": True,
        "exit_outcome_matrix_all_cases_have_reconciliation_policy": True,
        "exit_outcome_matrix_all_cases_have_next_attempt_gate": True,
        "exit_outcome_matrix_no_dangerous_effects": True,
        "actual_dangerous_effects_absent": True,
    }
    assert set(closed_loop_guard["cases"]) == {
        "missing_reconciliation_evidence",
        "missing_budget_settlement",
        "missing_review",
        "next_attempt_gate_not_ready",
        "finalize_not_complete",
        "reconciliation_not_matched",
        "budget_not_settled",
        "review_not_recorded",
    }
    for result in closed_loop_guard["cases"].values():
        assert result["packet"]["status"] == "post_submit_finalize_blocked"
        assert result["packet"]["dispatch_action"] is None
        assert result["packet"]["owner_state"]["downgrade_mode"] == (
            "halt_new_entries_until_post_submit_settled"
        )
    assert "post_submit_finalize_reconciliation_evidence_id_missing" in (
        closed_loop_guard["cases"]["missing_reconciliation_evidence"]["blockers"]
    )
    assert "post_submit_finalize_not_complete" in (
        closed_loop_guard["cases"]["finalize_not_complete"]["blockers"]
    )
    assert "post_submit_reconciliation_not_matched" in (
        closed_loop_guard["cases"]["reconciliation_not_matched"]["blockers"]
    )
    assert "post_submit_budget_not_settled" in (
        closed_loop_guard["cases"]["budget_not_settled"]["blockers"]
    )
    assert "submit_outcome_review_not_recorded" in (
        closed_loop_guard["cases"]["review_not_recorded"]["blockers"]
    )
    exit_outcome_matrix = closed_loop_guard["exit_outcome_matrix"]
    assert exit_outcome_matrix["status"] == "passed"
    assert exit_outcome_matrix["actual_exchange_write_called"] is False
    assert exit_outcome_matrix["actual_order_created"] is False
    assert exit_outcome_matrix["actual_order_lifecycle_called"] is False
    assert exit_outcome_matrix["actual_withdrawal_or_transfer_created"] is False
    assert exit_outcome_matrix["checks"] == {
        "expected_cases_present": True,
        "all_cases_have_accounting_policy": True,
        "all_cases_have_reconciliation_policy": True,
        "all_cases_have_next_attempt_gate": True,
        "all_cases_have_review_policy": True,
        "protection_failure_enters_reduce_only_recovery": True,
        "protection_failure_recovery_uses_standing_authorization": True,
        "submit_failure_releases_only_after_no_fill_verified": True,
        "active_position_blocks_same_scope_next_attempt": True,
        "closed_position_requires_review_before_fresh_signal": True,
        "no_post_submit_case_requires_owner_chat_confirmation": True,
        "no_dangerous_effects": True,
    }
    assert set(exit_outcome_matrix["cases"]) == {
        "entry_filled_protection_ok",
        "entry_filled_protection_failed",
        "partial_fill",
        "exchange_submit_failed_before_acceptance",
        "active_position_remains_open",
        "position_closed_by_sl_tp_or_reduce_only_recovery",
    }
    assert (
        exit_outcome_matrix["cases"]["entry_filled_protection_ok"][
            "next_attempt_gate"
        ]
        == "blocked_until_position_closed_or_scope_allows"
    )
    assert (
        exit_outcome_matrix["cases"]["entry_filled_protection_failed"][
            "reduce_only_recovery_mode"
        ]
        is True
    )
    assert (
        exit_outcome_matrix["cases"]["entry_filled_protection_failed"][
            "owner_chat_confirmation_required"
        ]
        is False
    )
    assert (
        exit_outcome_matrix["cases"]["partial_fill"]["budget_policy"]
        == "hold_budget_for_filled_or_residual_exposure"
    )
    assert all(
        case["owner_chat_confirmation_required"] is False
        for case in exit_outcome_matrix["cases"].values()
    )
    assert (
        exit_outcome_matrix["cases"][
            "exchange_submit_failed_before_acceptance"
        ]["budget_policy"]
        == "release_reserved_budget_after_no_fill_verified"
    )
    assert (
        exit_outcome_matrix["cases"]["active_position_remains_open"][
            "protection_state"
        ]
        == "exchange_native_hard_stop_required"
    )
    assert (
        exit_outcome_matrix["cases"][
            "position_closed_by_sl_tp_or_reduce_only_recovery"
        ]["review_policy"]
        == "record_closed_trade_review"
    )
    submit_identity_guard = scenarios["operation_layer_submit_result_identity_guard"][
        "artifacts"
    ]["operation_layer_submit_result_identity_guard"]
    assert submit_identity_guard["status"] == "passed"
    assert submit_identity_guard["simulated_exchange_effects"] is True
    assert submit_identity_guard["actual_exchange_write_called"] is False
    assert submit_identity_guard["actual_order_created"] is False
    assert submit_identity_guard["actual_order_lifecycle_called"] is False
    assert (
        submit_identity_guard["actual_withdrawal_or_transfer_created"] is False
    )
    assert submit_identity_guard["checks"] == {
        "all_submit_result_identity_mismatch_cases_block_finalize": True,
        "actual_dangerous_effects_absent": True,
    }
    assert set(submit_identity_guard["cases"]) == {
        "authorization_mismatch",
        "runtime_mismatch",
        "reservation_mismatch",
    }
    for result in submit_identity_guard["cases"].values():
        assert result["packet"]["status"] == "operation_layer_submit_failed"
        assert result["packet"]["dispatch_status"] == (
            "official_operation_layer_submit_result_identity_mismatch"
        )
        assert result["packet"]["dispatch_action"] is None
        assert "post_submit_finalize_result" not in result["packet"]
        assert result["packet"]["owner_state"]["downgrade_mode"] == (
            "halt_new_entries_until_reconciled"
        )
        assert len(
            [
                call
                for call in result["api_calls"]
                if call["url_kind"] == "operation_layer_submit"
            ]
        ) == 1
        assert not [
            call
            for call in result["api_calls"]
            if call["url_kind"] == "post_submit_finalize"
        ]
    finalize_identity_guard = scenarios[
        "post_submit_finalize_result_identity_guard"
    ]["artifacts"]["post_submit_finalize_result_identity_guard"]
    assert finalize_identity_guard["status"] == "passed"
    assert finalize_identity_guard["simulated_exchange_effects"] is True
    assert finalize_identity_guard["actual_exchange_write_called"] is False
    assert finalize_identity_guard["actual_order_created"] is False
    assert finalize_identity_guard["actual_order_lifecycle_called"] is False
    assert (
        finalize_identity_guard["actual_withdrawal_or_transfer_created"] is False
    )
    assert finalize_identity_guard["checks"] == {
        "all_finalize_result_identity_mismatch_cases_block_settled": True,
        "actual_dangerous_effects_absent": True,
    }
    assert set(finalize_identity_guard["cases"]) == {
        "authorization_mismatch",
        "runtime_mismatch",
        "reservation_mismatch",
    }
    for result in finalize_identity_guard["cases"].values():
        assert result["packet"]["status"] == "post_submit_finalize_blocked"
        assert result["packet"]["dispatch_status"] == (
            "post_submit_finalize_result_identity_mismatch"
        )
        assert result["packet"]["dispatch_action"] is None
        assert result["packet"]["owner_state"]["downgrade_mode"] == (
            "halt_new_entries_until_post_submit_settled"
        )
        assert len(
            [
                call
                for call in result["api_calls"]
                if call["url_kind"] == "operation_layer_submit"
            ]
        ) == 1
        assert len(
            [
                call
                for call in result["api_calls"]
                if call["url_kind"] == "post_submit_finalize"
            ]
        ) == 1
    shared = packet["shared_runtime_pipeline_validation"]
    assert shared["status"] == "passed"
    assert shared["judgment"] == {
        "common_runtime_pipe_share": "80%",
        "strategy_group_adapter_share": "20%",
        "meaning": (
            "candidate/auth, FinalGate, Operation Layer, finalize, "
            "reconciliation, settlement, and Owner readmodel are shared; "
            "StrategyGroups provide signal/facts/symbol/side/risk/hard-stop inputs."
        ),
    }
    assert shared["checks"]["common_execution_chain_reused_by_all_strategygroups"] is True
    assert shared["checks"]["strategygroup_adapters_are_input_only"] is True
    assert (
        shared["checks"]["all_strategy_groups_have_no_execution_pipeline_fields"]
        is True
    )
    assert set(shared["strategy_handoff_forbidden_execution_fields"]) == {
        "candidate",
        "authorization",
        "runtime_grant",
        "final_gate",
        "finalgate",
        "operation_layer",
        "order_lifecycle",
        "exchange_gateway",
        "submit_endpoint",
        "post_submit_finalize",
        "reconciliation",
        "budget_settlement",
    }
    assert set(shared["found_strategy_groups"]) == {
        "BTPC-001",
        "MPG-001",
        "TEQ-001",
        "FBS-001",
        "PMR-001",
        "SOR-001",
    }
    assert shared["expansion_observe_only_groups"] == ["BTPC-001"]
    assert shared["unexpected_strategy_groups"] == []
    for row in shared["rows"]:
        assert row["passed"] is True
        assert row["checks"]["does_not_authorize_execution_boundary"] is True
        assert row["checks"]["no_execution_pipeline_fields"] is True
        assert row["forbidden_execution_fields_present"] == []
        assert row["checks"]["allocated_subaccount_profile_boundary"] is True
        assert row["checks"]["uses_standard_signal_status"] is True
        assert row["checks"]["uses_pilot_signal_freshness_window"] is True
        assert row["sample_input_contract"]["freshness_window_seconds"] == 120
        assert row["shared_runtime_pipeline_stages"] == shared[
            "shared_runtime_pipeline_stages"
        ]
        assert "final_gate_input" in row["execution_boundary"]
        assert row["execution_boundary"]["final_gate_input"] is False
    tier_policy = packet["runtime_tier_policy_validation"]
    assert tier_policy["status"] == "passed"
    assert tier_policy["l4_strategy_groups"] == ["MPG-001"]
    assert tier_policy["new_strategy_group_tiers"] == {
        "BRF": "L1",
        "LSR": "L1",
        "RBR": "L1",
        "VCB": "L1",
    }
    assert tier_policy["checks"] == {
        "policy_schema_current": True,
        "policy_not_execution_authority": True,
        "expected_current_strategy_groups_present": True,
        "current_tiers_match_expected_policy": True,
        "only_mpg_is_l4": True,
        "new_strategy_groups_default_to_l1": True,
        "new_strategy_groups_do_not_enter_l4": True,
        "tier_policy_does_not_bypass_runtime_chain": True,
        "l4_real_order_requirements_complete": True,
    }
    assert tier_policy["l4_real_order_requirements"] == [
        "selected_strategygroup_scope",
        "allocated_subaccount_profile_boundary",
        "fresh_signal",
        "required_facts_readiness",
        "candidate_authorization_evidence",
        "action_time_finalgate",
        "official_operation_layer",
        "exchange_native_protection",
        "post_submit_finalize",
        "reconciliation",
        "budget_settlement",
        "review_capture",
    ]
    assert tier_policy["safety_invariants"]["exchange_write_called"] is False
    assert tier_policy["safety_invariants"]["order_created"] is False
    assert tier_policy["safety_invariants"]["modifies_order_sizing_defaults"] is False


def test_runtime_dry_run_audit_chain_cli_writes_packet(tmp_path, monkeypatch, capsys):
    output_json = tmp_path / "runtime-dry-run-audit-chain.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runtime_dry_run_audit_chain.py",
            "--output-dir",
            str(tmp_path),
            "--output-json",
            str(output_json),
        ],
    )

    assert audit_chain.main() == 0

    captured = capsys.readouterr()
    assert captured.out.startswith("{")
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    assert packet["status"] == "passed"
    assert packet["checks"]["required_scenarios_present"] is True
    assert list(tmp_path.glob(".runtime-dry-run-audit-chain.json.*.tmp")) == []
