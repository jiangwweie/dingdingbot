from __future__ import annotations

import json
import sys

from scripts import runtime_dry_run_audit_chain as audit_chain


def test_runtime_dry_run_audit_chain_covers_required_scenarios(tmp_path):
    packet = audit_chain.build_audit_chain(tmp_path)

    assert packet["status"] == "passed"
    assert packet["scenario_count"] == 13
    assert packet["checks"]["scenario_count"] == 13
    assert packet["checks"]["all_scenarios_passed"] is True
    assert packet["checks"]["dangerous_effects_absent"] is True
    assert packet["summary"] == {
        "scenario_count": 13,
        "required_checks_present": True,
        "all_scenarios_passed": True,
        "dangerous_effects_absent": True,
        "disabled_smoke_is_real_execution_proof": False,
        "shared_runtime_pipeline_checked": True,
        "common_execution_chain_reuse_checked": True,
        "strategygroup_adapter_boundary_checked": True,
        "strategy_handoff_no_execution_pipeline_fields_checked": True,
        "selected_strategygroup_dispatch_guard_checked": True,
        "all_selected_strategygroups_reach_finalgate_dispatch_checked": True,
        "operation_layer_hard_safety_blocker_matrix_checked": True,
        "expanded_watcher_scope_execution_guard_checked": True,
        "operation_layer_authorization_chain_guard_checked": True,
        "post_submit_closed_loop_evidence_guard_checked": True,
        "operation_layer_submit_result_identity_guard_checked": True,
        "post_submit_finalize_result_identity_guard_checked": True,
        "non_executing_prepare_auto_bridge_checked": True,
    }
    assert packet["required_checks"] == {
        "all_scenarios_passed": True,
        "dangerous_effects_absent": True,
        "disabled_smoke_not_real_execution_proof": True,
        "fresh_signal_fast_auto_chain_checked": True,
        "non_executing_prepare_auto_bridge_checked": True,
        "legacy_local_registration_probe_tolerance_checked": True,
        "mock_operation_layer_closed_loop_checked": True,
        "operation_layer_blocker_review_policy_checked": True,
        "operation_layer_hard_safety_blocker_matrix_checked": True,
        "expanded_watcher_scope_execution_guard_checked": True,
        "operation_layer_authorization_chain_guard_checked": True,
        "post_submit_closed_loop_evidence_guard_checked": True,
        "operation_layer_submit_result_identity_guard_checked": True,
        "post_submit_finalize_result_identity_guard_checked": True,
        "operation_layer_evidence_relay_checked": True,
        "required_scenarios_present": True,
        "common_execution_chain_reuse_checked": True,
        "strategygroup_adapter_boundary_checked": True,
        "strategy_handoff_no_execution_pipeline_fields_checked": True,
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
        "authorization_to_finalgate_dispatch_ready": True,
        "finalgate_to_operation_layer_evidence_ready": True,
        "operation_layer_real_submit_still_not_called": True,
    }
    assert relay_checks == {
        "required_evidence_ids_present": True,
        "no_missing_evidence_ids": True,
        "operation_layer_ready_flag_true": True,
        "operation_layer_official_endpoint_selected": True,
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
    assert packet["checks"]["fresh_signal_fast_auto_chain_checked"] is True
    assert packet["checks"]["non_executing_prepare_auto_bridge_checked"] is True
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
    assert packet["checks"]["selected_strategygroup_dispatch_guard_checked"] is True
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
        "actual_dangerous_effects_absent": True,
    }
    assert set(closed_loop_guard["cases"]) == {
        "missing_budget_settlement",
        "missing_review",
        "next_attempt_gate_not_ready",
    }
    for result in closed_loop_guard["cases"].values():
        assert result["packet"]["status"] == "post_submit_finalize_blocked"
        assert result["packet"]["dispatch_action"] is None
        assert result["packet"]["owner_state"]["downgrade_mode"] == (
            "halt_new_entries_until_post_submit_settled"
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
        "MPG-001",
        "TEQ-001",
        "FBS-001",
        "PMR-001",
        "SOR-001",
    }
    for row in shared["rows"]:
        assert row["passed"] is True
        assert row["checks"]["does_not_authorize_execution_boundary"] is True
        assert row["checks"]["no_execution_pipeline_fields"] is True
        assert row["forbidden_execution_fields_present"] == []
        assert row["checks"]["tiny_risk_boundary"] is True
        assert row["checks"]["uses_standard_signal_status"] is True
        assert row["shared_runtime_pipeline_stages"] == shared[
            "shared_runtime_pipeline_stages"
        ]
        assert "final_gate_input" in row["execution_boundary"]
        assert row["execution_boundary"]["final_gate_input"] is False


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
