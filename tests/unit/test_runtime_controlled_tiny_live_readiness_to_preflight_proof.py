from __future__ import annotations

import json

from scripts import runtime_controlled_tiny_live_readiness_to_preflight_proof as script


def _official_report(**overrides) -> dict:
    report = {
        "scope": "runtime_official_flat_next_attempt_end_to_end_proof",
        "status": "official_flat_next_attempt_end_to_end_passed",
        "runtime_instance_id": "runtime-rtf075-cpm-long",
        "signal_evaluation_id": "eval-rtf075-cpm-long",
        "order_candidate_id": "order-candidate-rtf075-contract",
        "authorization_id": "runtime-submit-authorization-intent_rt_test",
        "controlled_submit_preflight_id": "runtime-controlled-submit-preflight-test",
        "flat_next_attempt_end_to_end_artifact": {
            "scope": "runtime_official_flat_next_attempt_end_to_end_artifact",
            "status": "flat_next_attempt_ready_for_controlled_submit_adapter",
            "final_gate": {"verdict": "PASS", "status": "pass", "blockers": []},
            "controlled_submit_preflight": {
                "status": "ready_for_controlled_submit_adapter",
                "preview_only": True,
                "submit_executed": False,
                "order_created": False,
                "exchange_called": False,
                "order_lifecycle_called": False,
            },
        },
        "checks": {
            "shadow_signal_created": True,
            "shadow_candidate_created": True,
            "fresh_authorization_required_before_submit": True,
            "final_gate_verdict_pass": True,
            "controlled_submit_preflight_ready": True,
            "preflight_preview_only": True,
            "old_authorization_retry_disallowed": True,
            "pre_submit_rehearsal_retry_disallowed": True,
            "right_tail_runner_preserved": True,
        },
        "safety_invariants": {
            "uses_official_fastapi_routes": True,
            "uses_fake_console_api": False,
            "execution_intent_created_for_audit": True,
            "executable_submit_executed": False,
            "local_order_created": False,
            "order_lifecycle_called": False,
            "exchange_called": False,
            "runtime_state_mutated": False,
            "withdrawal_or_transfer_created": False,
        },
    }
    report.update(overrides)
    return report


def test_projection_to_preflight_passes_with_ready_projection_and_official_report(
    tmp_path,
):
    report = script.build_proof_report(
        tmp_path / "rtf101",
        official_preflight_builder=lambda _path: _official_report(),
    )

    assert (
        report["status"]
        == "controlled_tiny_live_readiness_to_official_preflight_passed"
    )
    checks = report["checks"]
    assert checks["waiting_projection_blocks_official_route"] is True
    assert checks["ready_projection_enters_official_prepare"] is True
    assert checks["readiness_projection_uses_legacy_pre_attempt_as_primary_gate"] is False
    assert checks["official_preflight_passed"] is True
    assert checks["official_preflight_current_artifact_present"] is True
    assert checks["official_strategy_signal_created_shadow_evaluation"] is True
    assert checks["official_strategy_signal_created_shadow_candidate"] is True
    assert checks["official_fresh_authorization_required"] is True
    assert checks["official_final_gate_passed"] is True
    assert checks["official_controlled_submit_preflight_ready"] is True
    assert checks["official_preflight_preview_only"] is True
    assert checks["old_authorization_retry_disallowed"] is True
    assert checks["pre_submit_rehearsal_retry_disallowed"] is True
    assert checks["right_tail_runner_preserved"] is True
    assert checks["execution_intent_created_for_audit"] is True
    assert checks["executable_submit_executed"] is False
    assert checks["local_order_created"] is False
    assert checks["order_lifecycle_called"] is False
    assert checks["exchange_called"] is False
    assert checks["runtime_state_mutated"] is False
    assert checks["withdrawal_or_transfer_created"] is False
    safety = report["safety_invariants"]
    assert safety["waiting_projection_only"] is True
    assert safety["ready_projection_only"] is True
    assert "waiting_projection_packet_only" not in safety
    assert "ready_projection_packet_only" not in safety
    waiting = report["readiness_to_official_preflight_artifact"]["waiting_path"]
    assert waiting["selected_action"] == (
        "monitor_position_or_prepare_official_reduce_only_recovery"
    )
    assert "owner_authorize" not in waiting["selected_action"]


def test_projection_to_preflight_outputs_expected_artifacts(tmp_path):
    output_dir = tmp_path / "rtf101"

    report = script.build_proof_report(
        output_dir,
        official_preflight_builder=lambda _path: _official_report(),
    )

    expected_files = [
        "contract-report.json",
        "waiting-refresh.json",
        "ready-refresh.json",
        "waiting-readiness-projection.json",
        "ready-readiness-projection.json",
        "rtf092-official-preflight-report.json",
        "readiness-to-official-preflight-artifact.json",
    ]
    for name in expected_files:
        assert (output_dir / name).exists()

    artifact = json.loads(
        (output_dir / "readiness-to-official-preflight-artifact.json").read_text()
    )
    assert (
        artifact["status"]
        == "readiness_projection_ready_for_official_controlled_submit_preflight"
    )
    assert artifact["waiting_path"]["projection_status"] == (
        "controlled_tiny_live_readiness_projection_waiting_for_ready_selector"
    )
    assert artifact["waiting_path"]["selected_action"] == (
        "monitor_position_or_prepare_official_reduce_only_recovery"
    )
    assert artifact["ready_path"]["projection_status"] == (
        "controlled_tiny_live_readiness_projection_ready_for_official_prepare"
    )
    assert artifact["official_preflight"]["status"] == (
        "official_flat_next_attempt_end_to_end_passed"
    )
    assert artifact["official_preflight"]["source_status"] == (
        "flat_next_attempt_ready_for_controlled_submit_adapter"
    )
    assert "packet_status" not in artifact["official_preflight"]
    assert json.loads((output_dir / "contract-report.json").read_text())[
        "status"
    ] == report["status"]


def test_projection_to_preflight_blocks_when_official_route_fails(tmp_path):
    report = script.build_proof_report(
        tmp_path / "rtf101",
        official_preflight_builder=lambda _path: _official_report(status="blocked"),
    )

    assert report["status"] == "blocked"
    assert report["checks"]["official_preflight_passed"] is False


def test_projection_to_preflight_blocks_legacy_packet_only_official_report(tmp_path):
    legacy_report = _official_report()
    legacy_report["flat_next_attempt_end_to_end_packet"] = legacy_report.pop(
        "flat_next_attempt_end_to_end_artifact"
    )

    report = script.build_proof_report(
        tmp_path / "rtf101",
        official_preflight_builder=lambda _path: legacy_report,
    )

    assert report["status"] == "blocked"
    assert report["checks"]["official_preflight_passed"] is True
    assert report["checks"]["official_preflight_current_artifact_present"] is False
    artifact = report["readiness_to_official_preflight_artifact"]
    assert artifact["official_preflight"]["source_status"] is None
    assert artifact["official_preflight"]["final_gate"] == {}


def test_projection_to_preflight_cli_stdout_is_json_only(capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(
        script.rtf092,
        "build_proof_report",
        lambda _path: _official_report(),
    )
    monkeypatch.setattr(
        script.sys,
        "argv",
        [
            "runtime_controlled_tiny_live_readiness_to_preflight_proof.py",
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    assert script.main() == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert (
        payload["status"]
        == "controlled_tiny_live_readiness_to_official_preflight_passed"
    )
    assert captured.err == ""
