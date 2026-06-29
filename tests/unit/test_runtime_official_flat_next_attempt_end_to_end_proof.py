from __future__ import annotations

import json

from scripts import runtime_official_flat_next_attempt_end_to_end_proof as script


def test_official_flat_next_attempt_end_to_end_passes(tmp_path):
    report = script.build_proof_report(tmp_path / "rtf092")

    assert report["status"] == "official_flat_next_attempt_end_to_end_passed"
    assert report["runtime_instance_id"] == "runtime-rtf075-cpm-long"
    assert report["signal_evaluation_id"] == "eval-rtf075-cpm-long"
    assert report["order_candidate_id"] == "order-candidate-rtf075-contract"
    assert report["authorization_id"].startswith("runtime-submit-authorization-")
    assert report["runtime_execution_intent_draft_id"].startswith(
        "runtime-intent-draft-"
    )
    assert report["execution_intent_id"].startswith("intent_rt_")
    assert report["controlled_submit_preflight_id"].startswith(
        "runtime-controlled-submit-preflight-"
    )
    assert "operator_command_plan" not in report
    assert report["flat_next_attempt_plan"]["executes_submit"] is False

    checks = report["checks"]
    assert checks["ready_post_submit_gate_flat"] is True
    assert checks["old_authorization_retry_disallowed"] is True
    assert checks["pre_submit_rehearsal_retry_disallowed"] is True
    assert checks["strategy_plan_route_called"] is True
    assert checks["strategy_plan_http_ok"] is True
    assert checks["strategy_plan_gate_ready"] is True
    assert checks["shadow_signal_created"] is True
    assert checks["shadow_candidate_created"] is True
    assert checks["strategy_requires_official_final_gate"] is True
    assert checks["fresh_authorization_required_before_submit"] is True
    assert checks["tp1_present"] is True
    assert checks["runner_present"] is True
    assert checks["right_tail_runner_preserved"] is True
    assert checks["prepare_authorization_created"] is True
    assert checks["prepare_intent_created_for_audit"] is True
    assert checks["final_gate_route_called"] is True
    assert checks["final_gate_verdict_pass"] is True
    assert checks["final_gate_no_blockers"] is True
    assert checks["controlled_submit_plan_route_called"] is True
    assert checks["controlled_submit_plan_ready"] is True
    assert checks["controlled_submit_preflight_route_called"] is True
    assert checks["controlled_submit_preflight_ready"] is True
    assert checks["preflight_preview_only"] is True
    assert checks["preflight_submit_not_executed"] is True
    assert checks["preflight_no_order_created"] is True
    assert checks["preflight_no_exchange_called"] is True
    assert checks["preflight_no_order_lifecycle_called"] is True
    assert checks["uses_official_fastapi_routes"] is True
    assert checks["uses_fake_console_api"] is False
    assert checks["runtime_state_mutated"] is False
    assert checks["withdrawal_or_transfer_created"] is False


def test_official_flat_next_attempt_end_to_end_outputs_artifact(tmp_path):
    output_dir = tmp_path / "rtf092"

    report = script.build_proof_report(output_dir)

    expected_files = [
        "contract-report.json",
        "ready-post-submit-finalize.json",
        "next-attempt-strategy-plan.json",
        "shadow-signal-evaluation.json",
        "shadow-order-candidate.json",
        "prepare-report.json",
        "final-gate-preview.json",
        "controlled-submit-plan.json",
        "controlled-submit-preflight.json",
        "flat-next-attempt-end-to-end-artifact.json",
    ]
    for name in expected_files:
        assert (output_dir / name).exists()

    assert json.loads((output_dir / "contract-report.json").read_text())[
        "status"
    ] == report["status"]
    artifact = json.loads(
        (output_dir / "flat-next-attempt-end-to-end-artifact.json").read_text()
    )
    assert artifact["status"] == "flat_next_attempt_ready_for_controlled_submit_adapter"
    assert artifact["ready_post_submit_gate"]["next_attempt_gate_status"] == (
        "ready_for_fresh_signal"
    )
    assert artifact["ready_post_submit_gate"]["active_positions_count"] == 0
    assert artifact["strategy_plan"]["status"] == "ready_for_final_gate_preflight"
    assert artifact["strategy_plan"]["order_candidate_id"] == (
        "order-candidate-rtf075-contract"
    )
    assert artifact["strategy_plan"]["strategy_planning_plan"][
        "requires_official_final_gate"
    ] is True
    assert artifact["final_gate"]["verdict"] == "PASS"
    assert artifact["controlled_submit_preflight"]["status"] == (
        "ready_for_controlled_submit_adapter"
    )
    assert artifact["controlled_submit_preflight"]["preview_only"] is True
    assert artifact["safety_invariants"]["execution_intent_created_for_audit"] is True
    assert artifact["safety_invariants"]["executable_submit_executed"] is False
    assert artifact["safety_invariants"]["local_order_created"] is False
    assert artifact["safety_invariants"]["order_lifecycle_called"] is False
    assert artifact["safety_invariants"]["exchange_called"] is False
    assert artifact["safety_invariants"]["runtime_state_mutated"] is False
    assert artifact["safety_invariants"]["withdrawal_or_transfer_created"] is False
    classification = report["official_runtime_artifact_boundary_classification"]
    assert classification["evidence_only_outputs"] == [
        "runtime_official_flat_next_attempt_end_to_end_artifact"
    ]
    assert classification["protected_lifecycle_payload_contracts"] == [
        "post_submit_finalize_payload"
    ]
    assert "RuntimeOfficialSubmitHandoffArtifact" in (
        classification["typed_submit_handoff_contracts"]
    )
    assert classification["judgment_authorities"] == [
        "Strategy Asset State",
        "Tradeability Decision",
        "Runtime Safety State",
        "Review Outcome State",
        "Execution Attempt",
    ]


def test_official_flat_next_attempt_end_to_end_cli_stdout_is_json_only(
    capsys,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        script.sys,
        "argv",
        [
            "runtime_official_flat_next_attempt_end_to_end_proof.py",
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    assert script.main() == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["status"] == "official_flat_next_attempt_end_to_end_passed"
    assert captured.err == ""
