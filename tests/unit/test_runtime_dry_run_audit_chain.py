from __future__ import annotations

import json
import sys

from scripts import runtime_dry_run_audit_chain as audit_chain


def test_runtime_dry_run_audit_chain_covers_required_scenarios(tmp_path):
    packet = audit_chain.build_audit_chain(tmp_path)

    assert packet["status"] == "passed"
    assert packet["checks"]["scenario_count"] == 6
    assert packet["checks"]["all_scenarios_passed"] is True
    assert packet["checks"]["dangerous_effects_absent"] is True
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
