from __future__ import annotations

import json

from scripts import (
    runtime_official_fresh_candidate_runtime_cycle_handoff_proof as script,
)


def test_official_fresh_candidate_runtime_cycle_handoff_passes(tmp_path):
    report = script.build_proof_report(tmp_path / "rtf091")

    assert (
        report["status"]
        == "official_fresh_candidate_runtime_cycle_handoff_passed"
    )
    assert report["runtime_instance_id"] == "runtime-rtf075-cpm-long"
    assert report["signal_evaluation_id"] == "eval-rtf075-cpm-long"
    assert report["order_candidate_id"] == "order-candidate-rtf075-contract"
    assert report["preflight_authorization_id"].startswith(
        "runtime-submit-authorization-"
    )
    assert report["post_submit_authorization_id"].startswith(
        "runtime-submit-authorization-"
    )
    assert report["exchange_submit_execution_result_id"].startswith(
        "runtime-exchange-submit-execution-result-"
    )
    assert report["submit_outcome_review_id"].startswith(
        "runtime-submit-outcome-review-"
    )
    assert report["post_submit_budget_settlement_id"].startswith(
        "runtime-post-submit-budget-settlement-"
    )
    assert "operator_command_plan" not in report
    assert report["fresh_candidate_runtime_cycle_handoff_plan"] == {
        "next_step": "prove_repeatable_runtime_cycle_with_flat_next_attempt_gate",
        "uses_official_fastapi_routes": True,
        "uses_fake_console_api": False,
        "controlled_execution_mode": "in_memory_simulation",
        "calls_live_exchange": False,
        "next_attempt_requires_fresh_signal": True,
        "next_attempt_requires_fresh_authorization": True,
    }

    checks = report["checks"]
    assert checks["rtf090_prerequisite_passed"] is True
    assert checks["rtf088_post_submit_finalize_passed"] is True
    assert checks["candidate_ids_match"] is True
    assert checks["runtime_ids_match"] is True
    assert checks["fresh_preflight_ready"] is True
    assert checks["final_gate_passed"] is True
    assert checks["controlled_submit_preflight_ready"] is True
    assert checks["fresh_authorization_required_before_submit"] is True
    assert checks["controlled_gateway_action_passed"] is True
    assert checks["exchange_execution_result_submitted"] is True
    assert checks["durable_execution_result_reused"] is True
    assert checks["post_submit_finalize_completed"] is True
    assert checks["next_attempt_gate_blocked_by_active_position"] is True
    assert checks["next_attempt_requires_fresh_signal"] is True
    assert checks["next_attempt_requires_fresh_authorization"] is True
    assert checks["old_authorization_retry_disallowed"] is True
    assert checks["pre_submit_rehearsal_retry_disallowed"] is True
    assert checks["local_created_order_requirement_retired"] is True
    assert checks["submit_outcome_review_created"] is True
    assert checks["post_submit_budget_settlement_created"] is True
    assert checks["right_tail_runner_preserved"] is True
    assert checks["uses_official_fastapi_routes"] is True
    assert checks["uses_fake_console_api"] is False
    assert checks["live_exchange_called"] is False
    assert checks["pg_written"] is False
    assert checks["withdrawal_or_transfer_created"] is False


def test_official_fresh_candidate_runtime_cycle_handoff_outputs_artifact(tmp_path):
    output_dir = tmp_path / "rtf091"

    report = script.build_proof_report(output_dir)

    expected_files = [
        "contract-report.json",
        "rtf090-prerequisite-report.json",
        "rtf088-post-submit-finalize-report.json",
        "fresh-candidate-runtime-cycle-artifact.json",
    ]
    for name in expected_files:
        assert (output_dir / name).exists()

    assert json.loads((output_dir / "contract-report.json").read_text())[
        "status"
    ] == report["status"]
    artifact = json.loads(
        (output_dir / "fresh-candidate-runtime-cycle-artifact.json").read_text()
    )
    assert artifact["status"] == "fresh_candidate_cycle_handoff_completed"
    assert artifact["candidate_handoff"]["candidate_ids_match"] is True
    assert artifact["pre_submit_side"]["fresh_preflight_status"] == (
        "fresh_candidate_ready_for_controlled_submit_adapter"
    )
    assert artifact["pre_submit_side"]["final_gate_verdict"] == "PASS"
    assert artifact["pre_submit_side"]["controlled_submit_preflight_status"] == (
        "ready_for_controlled_submit_adapter"
    )
    assert artifact["controlled_action_side"][
        "exchange_submit_execution_result_status"
    ] == "exchange_submit_orders_submitted"
    assert artifact["controlled_action_side"]["execution_mode"] == (
        "in_memory_simulation"
    )
    assert artifact["post_submit_side"]["finalize_status"] == (
        "finalized_next_attempt_blocked"
    )
    assert artifact["post_submit_side"]["next_attempt_gate_status"] == "blocked"
    assert "runtime_active_position_slot_in_use" in artifact["post_submit_side"][
        "next_attempt_gate_blockers"
    ]
    assert artifact["safety_invariants"][
        "controlled_in_memory_execution_result_recorded"
    ] is True
    assert artifact["safety_invariants"]["live_exchange_called"] is False
    assert artifact["safety_invariants"]["pg_written"] is False
    assert artifact["safety_invariants"]["withdrawal_or_transfer_created"] is False


def test_official_fresh_candidate_runtime_cycle_handoff_cli_stdout_is_json_only(
    capsys,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        script.sys,
        "argv",
        [
            "runtime_official_fresh_candidate_runtime_cycle_handoff_proof.py",
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    assert script.main() == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert (
        payload["status"]
        == "official_fresh_candidate_runtime_cycle_handoff_passed"
    )
    assert captured.err == ""
