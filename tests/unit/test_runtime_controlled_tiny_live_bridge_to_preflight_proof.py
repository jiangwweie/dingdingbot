from __future__ import annotations

import json

from scripts import runtime_controlled_tiny_live_bridge_to_preflight_proof as script


def _official_report(**overrides) -> dict:
    report = {
        "scope": "runtime_official_flat_next_attempt_end_to_end_proof",
        "status": "official_flat_next_attempt_end_to_end_passed",
        "runtime_instance_id": "runtime-rtf075-cpm-long",
        "signal_evaluation_id": "eval-rtf075-cpm-long",
        "order_candidate_id": "order-candidate-rtf075-contract",
        "authorization_id": "runtime-submit-authorization-intent_rt_test",
        "controlled_submit_preflight_id": "runtime-controlled-submit-preflight-test",
        "flat_next_attempt_end_to_end_packet": {
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


def test_bridge_to_preflight_passes_with_ready_bridge_and_official_report(tmp_path):
    report = script.build_proof_report(
        tmp_path / "rtf101",
        official_preflight_builder=lambda _path: _official_report(),
    )

    assert (
        report["status"]
        == "controlled_tiny_live_bridge_to_official_preflight_passed"
    )
    checks = report["checks"]
    assert checks["waiting_bridge_blocks_official_route"] is True
    assert checks["ready_bridge_enters_official_prepare"] is True
    assert checks["bridge_uses_legacy_pre_attempt_as_primary_gate"] is False
    assert checks["official_preflight_passed"] is True
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
    waiting = report["bridge_to_official_preflight_packet"]["waiting_path"]
    assert waiting["selected_action"] == (
        "monitor_position_or_prepare_official_reduce_only_recovery"
    )
    assert "owner_authorize" not in waiting["selected_action"]


def test_bridge_to_preflight_outputs_expected_artifacts(tmp_path):
    output_dir = tmp_path / "rtf101"

    report = script.build_proof_report(
        output_dir,
        official_preflight_builder=lambda _path: _official_report(),
    )

    expected_files = [
        "contract-report.json",
        "waiting-refresh.json",
        "ready-refresh.json",
        "waiting-bridge-readiness.json",
        "ready-bridge-readiness.json",
        "rtf092-official-preflight-report.json",
        "bridge-to-official-preflight-packet.json",
    ]
    for name in expected_files:
        assert (output_dir / name).exists()

    packet = json.loads(
        (output_dir / "bridge-to-official-preflight-packet.json").read_text()
    )
    assert packet["status"] == "bridge_ready_for_official_controlled_submit_preflight"
    assert packet["waiting_path"]["bridge_status"] == (
        "controlled_tiny_live_bridge_waiting_for_ready_selector"
    )
    assert packet["waiting_path"]["selected_action"] == (
        "monitor_position_or_prepare_official_reduce_only_recovery"
    )
    assert packet["ready_path"]["bridge_status"] == (
        "controlled_tiny_live_bridge_ready_for_official_prepare"
    )
    assert packet["official_preflight"]["status"] == (
        "official_flat_next_attempt_end_to_end_passed"
    )
    assert json.loads((output_dir / "contract-report.json").read_text())[
        "status"
    ] == report["status"]


def test_bridge_to_preflight_blocks_when_official_route_fails(tmp_path):
    report = script.build_proof_report(
        tmp_path / "rtf101",
        official_preflight_builder=lambda _path: _official_report(status="blocked"),
    )

    assert report["status"] == "blocked"
    assert report["checks"]["official_preflight_passed"] is False


def test_bridge_to_preflight_cli_stdout_is_json_only(capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(
        script.rtf092,
        "build_proof_report",
        lambda _path: _official_report(),
    )
    monkeypatch.setattr(
        script.sys,
        "argv",
        [
            "runtime_controlled_tiny_live_bridge_to_preflight_proof.py",
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    assert script.main() == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert (
        payload["status"]
        == "controlled_tiny_live_bridge_to_official_preflight_passed"
    )
    assert captured.err == ""
