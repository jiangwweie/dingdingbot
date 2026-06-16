from __future__ import annotations

import json
import sys

from scripts import runtime_dry_run_audit_chain as audit_chain


def test_runtime_dry_run_audit_chain_covers_required_scenarios(tmp_path):
    packet = audit_chain.build_audit_chain(tmp_path)

    assert packet["status"] == "passed"
    assert packet["scenario_count"] == 8
    assert packet["checks"]["scenario_count"] == 8
    assert packet["checks"]["all_scenarios_passed"] is True
    assert packet["checks"]["dangerous_effects_absent"] is True
    assert packet["summary"] == {
        "scenario_count": 8,
        "required_checks_present": True,
        "all_scenarios_passed": True,
        "dangerous_effects_absent": True,
        "disabled_smoke_is_real_execution_proof": False,
        "shared_runtime_pipeline_checked": True,
        "selected_strategygroup_dispatch_guard_checked": True,
        "all_selected_strategygroups_reach_finalgate_dispatch_checked": True,
        "operation_layer_hard_safety_blocker_matrix_checked": True,
        "expanded_watcher_scope_execution_guard_checked": True,
    }
    assert packet["required_checks"] == {
        "all_scenarios_passed": True,
        "dangerous_effects_absent": True,
        "disabled_smoke_not_real_execution_proof": True,
        "fresh_signal_fast_auto_chain_checked": True,
        "legacy_local_registration_probe_tolerance_checked": True,
        "mock_operation_layer_closed_loop_checked": True,
        "operation_layer_blocker_review_policy_checked": True,
        "operation_layer_hard_safety_blocker_matrix_checked": True,
        "expanded_watcher_scope_execution_guard_checked": True,
        "operation_layer_evidence_relay_checked": True,
        "required_scenarios_present": True,
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
        "mock_operation_layer_submit_finalize_pass",
        "required_facts_missing",
        "active_position_or_open_order_conflict",
        "operation_layer_blocker_review_matrix",
        "selected_strategygroup_dispatch_guard",
        "expanded_watcher_scope_execution_guard",
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
    assert packet["checks"]["shared_runtime_pipeline_checked"] is True
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
