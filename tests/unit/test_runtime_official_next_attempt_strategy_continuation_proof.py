from __future__ import annotations

import json

from scripts import (
    runtime_official_next_attempt_strategy_continuation_proof as script,
)


def test_official_next_attempt_strategy_continuation_passes(tmp_path):
    report = script.build_proof_report(tmp_path / "rtf089")

    assert (
        report["status"]
        == "official_next_attempt_strategy_continuation_passed"
    )
    assert report["runtime_instance_id"] == "runtime-rtf075-cpm-long"
    assert report["order_candidate_id"] == "order-candidate-rtf075-contract"
    assert report["signal_evaluation_id"] == "eval-rtf075-cpm-long"
    assert report["blocked_status"] == "blocked_by_post_submit_gate"
    assert report["ready_status"] == "ready_for_final_gate_preflight"
    assert "operator_command_plan" not in report
    assert report["next_attempt_strategy_continuation_plan"]["places_order"] is False

    checks = report["checks"]
    assert checks["rtf088_prerequisite_passed"] is True
    assert checks["blocked_path_http_ok"] is True
    assert checks["blocked_path_blocked_by_post_submit_gate"] is True
    assert checks["blocked_path_has_active_position_blocker"] is True
    assert checks["blocked_path_created_no_candidate"] is True
    assert checks["ready_path_http_ok"] is True
    assert checks["ready_path_ready_for_final_gate"] is True
    assert checks["ready_path_gate_ready"] is True
    assert checks["ready_path_shadow_candidate_created"] is True
    assert checks["ready_path_shadow_signal_created"] is True
    assert checks["ready_path_requires_final_gate"] is True
    assert checks["fresh_authorization_required_before_submit"] is True
    assert checks["old_authorization_retry_disallowed"] is True
    assert checks["pre_submit_rehearsal_retry_disallowed"] is True
    assert checks["tp1_present"] is True
    assert checks["runner_present"] is True
    assert checks["right_tail_runner_preserved"] is True
    assert checks["uses_official_fastapi_routes"] is True
    assert checks["uses_fake_console_api"] is False
    assert checks["execution_intent_created"] is False
    assert checks["executable_execution_intent_created"] is False
    assert checks["order_created"] is False
    assert checks["order_lifecycle_called"] is False
    assert checks["exchange_called"] is False
    assert checks["withdrawal_or_transfer_created"] is False


def test_official_next_attempt_strategy_continuation_outputs_artifact(tmp_path):
    output_dir = tmp_path / "rtf089"

    report = script.build_proof_report(output_dir)

    expected_files = [
        "contract-report.json",
        "blocked-next-attempt-strategy-plan.json",
        "ready-next-attempt-strategy-plan.json",
        "next-attempt-strategy-continuation-artifact.json",
    ]
    for name in expected_files:
        assert (output_dir / name).exists()

    assert json.loads((output_dir / "contract-report.json").read_text())[
        "status"
    ] == report["status"]
    artifact = json.loads(
        (
            output_dir
            / "next-attempt-strategy-continuation-artifact.json"
        ).read_text()
    )
    assert artifact["status"] == "next_attempt_strategy_continuation_ready_for_final_gate"
    assert artifact["blocked_path"]["status"] == "blocked_by_post_submit_gate"
    assert "runtime_active_position_slot_in_use" in artifact["blocked_path"][
        "blockers"
    ]
    assert artifact["blocked_path"]["order_candidate_id"] is None
    assert artifact["ready_path"]["status"] == "ready_for_final_gate_preflight"
    assert artifact["ready_path"]["next_attempt_gate_status"] == (
        "ready_for_fresh_signal"
    )
    assert artifact["ready_path"]["order_candidate_id"] == (
        "order-candidate-rtf075-contract"
    )
    assert "operator_command_plan" not in artifact["ready_path"]
    assert artifact["ready_path"]["strategy_planning_plan"][
        "requires_official_final_gate"
    ] is True
    assert artifact["ready_post_submit_gate"][
        "old_authorization_submit_retry_allowed"
    ] is False
    assert "packet_id" not in artifact["ready_post_submit_gate"]
    assert artifact["ready_post_submit_gate"]["payload_id"] == (
        "post-submit-rtf075-contract"
    )
    assert artifact["ready_post_submit_gate"][
        "pre_submit_rehearsal_retry_allowed"
    ] is False
    assert artifact["safety_invariants"]["ready_path_shadow_candidate_created"] is True
    assert artifact["safety_invariants"]["execution_intent_created"] is False
    assert artifact["safety_invariants"]["order_lifecycle_called"] is False
    assert artifact["safety_invariants"]["exchange_called"] is False
    assert artifact["safety_invariants"]["withdrawal_or_transfer_created"] is False


def test_official_next_attempt_strategy_continuation_cli_stdout_is_json_only(
    capsys,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        script.sys,
        "argv",
        [
            "runtime_official_next_attempt_strategy_continuation_proof.py",
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    assert script.main() == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert (
        payload["status"]
        == "official_next_attempt_strategy_continuation_passed"
    )
    assert captured.err == ""
