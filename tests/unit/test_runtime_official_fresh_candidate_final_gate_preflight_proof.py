from __future__ import annotations

import json

from scripts import (
    runtime_official_fresh_candidate_final_gate_preflight_proof as script,
)


def test_official_fresh_candidate_final_gate_preflight_passes(tmp_path):
    report = script.build_proof_report(tmp_path / "rtf090")

    assert (
        report["status"]
        == "official_fresh_candidate_final_gate_preflight_passed"
    )
    assert report["runtime_instance_id"] == "runtime-rtf075-cpm-long"
    assert report["signal_evaluation_id"] == "eval-rtf075-cpm-long"
    assert report["order_candidate_id"] == "order-candidate-rtf075-contract"
    assert report["authorization_id"].startswith("runtime-submit-authorization-")
    assert report["controlled_submit_preflight_id"].startswith(
        "runtime-controlled-submit-preflight-"
    )
    assert "operator_command_plan" not in report
    assert report["fresh_candidate_preflight_plan"]["places_order"] is False

    checks = report["checks"]
    assert checks["rtf089_prerequisite_passed"] is True
    assert checks["rtf081_final_gate_preflight_passed"] is True
    assert checks["fresh_candidate_ready_for_final_gate"] is True
    assert checks["candidate_ids_match"] is True
    assert checks["signal_evaluation_present"] is True
    assert checks["ready_path_shadow_candidate_created"] is True
    assert checks["ready_path_requires_final_gate"] is True
    assert checks["fresh_authorization_required_before_submit"] is True
    assert checks["old_authorization_retry_disallowed"] is True
    assert checks["pre_submit_rehearsal_retry_disallowed"] is True
    assert checks["final_gate_verdict_pass"] is True
    assert checks["controlled_submit_preflight_ready"] is True
    assert checks["preflight_preview_only"] is True
    assert checks["prepare_authorization_created"] is True
    assert checks["right_tail_runner_preserved"] is True
    assert checks["uses_official_fastapi_routes"] is True
    assert checks["uses_fake_console_api"] is False
    assert checks["execution_intent_created_in_continuation"] is False
    assert checks["executable_execution_intent_created"] is False
    assert checks["local_order_created"] is False
    assert checks["order_lifecycle_called"] is False
    assert checks["exchange_called"] is False
    assert checks["exchange_order_submitted"] is False
    assert checks["runtime_state_mutated"] is False
    assert checks["withdrawal_or_transfer_created"] is False


def test_official_fresh_candidate_final_gate_preflight_outputs_artifact(tmp_path):
    output_dir = tmp_path / "rtf090"

    report = script.build_proof_report(output_dir)

    expected_files = [
        "contract-report.json",
        "rtf089-prerequisite-report.json",
        "rtf081-final-gate-preflight-report.json",
        "fresh-candidate-final-gate-preflight-artifact.json",
    ]
    for name in expected_files:
        assert (output_dir / name).exists()

    assert json.loads((output_dir / "contract-report.json").read_text())[
        "status"
    ] == report["status"]
    artifact = json.loads(
        (
            output_dir / "fresh-candidate-final-gate-preflight-artifact.json"
        ).read_text()
    )
    assert artifact["status"] == (
        "fresh_candidate_ready_for_controlled_submit_adapter"
    )
    assert artifact["candidate_handoff"]["candidate_ids_match"] is True
    assert artifact["candidate_handoff"]["fresh_ready_status"] == (
        "ready_for_final_gate_preflight"
    )
    assert (
        artifact["authorization"]["fresh_authorization_required_before_submit"] is True
    )
    assert artifact["final_gate"]["verdict"] == "PASS"
    assert artifact["controlled_submit_preflight"]["status"] == (
        "ready_for_controlled_submit_adapter"
    )
    assert artifact["controlled_submit_preflight"]["preview_only"] is True
    assert artifact["safety_invariants"]["ready_path_shadow_candidate_created"] is True
    assert artifact["safety_invariants"]["local_order_created"] is False
    assert artifact["safety_invariants"]["order_lifecycle_called"] is False
    assert artifact["safety_invariants"]["exchange_called"] is False
    assert artifact["safety_invariants"]["exchange_order_submitted"] is False
    assert artifact["safety_invariants"]["withdrawal_or_transfer_created"] is False


def test_official_fresh_candidate_final_gate_preflight_cli_stdout_is_json_only(
    capsys,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        script.sys,
        "argv",
        [
            "runtime_official_fresh_candidate_final_gate_preflight_proof.py",
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    assert script.main() == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert (
        payload["status"]
        == "official_fresh_candidate_final_gate_preflight_passed"
    )
    assert captured.err == ""
