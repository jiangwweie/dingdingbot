from __future__ import annotations

import json
import sys

from scripts import runtime_fresh_signal_readiness_fixture as script


def test_ready_signal_fixture_reaches_fresh_authorization_boundary(tmp_path):
    report = script._build_report(_args(tmp_path))

    assert report["status"] == "ready_fresh_signal_readiness_fixture"
    assert report["bridge_status"] == "ready_for_fresh_submit_authorization"
    assert report["planning_call_count"] == 1
    assert report["handoff_call_count"] == 1
    assert report["blockers"] == []
    assert report["bridge_packet"]["next_attempt_strategy_plan_flow"]["status"] == (
        "ready_for_final_gate_preflight"
    )
    assert report["bridge_packet"]["readiness_handoff_bridge"]["status"] == (
        "ready_for_fresh_submit_authorization"
    )
    assert report["bridge_packet"]["operator_command_plan"]["next_step"] == (
        "bind_or_resolve_fresh_submit_authorization"
    )
    assert report["safety_invariants"]["uses_fake_api_builders"] is True
    assert report["safety_invariants"]["does_not_call_server"] is True
    assert report["safety_invariants"]["does_not_call_exchange"] is True
    assert report["safety_invariants"]["bridge_exchange_write_called"] is False
    assert report["safety_invariants"]["bridge_order_created"] is False
    assert report["safety_invariants"]["bridge_order_lifecycle_called"] is False


def test_ready_signal_fixture_can_reach_official_handoff_preview_boundary(tmp_path):
    report = script._build_report(
        _args(tmp_path, include_fresh_submit_authorization=True)
    )

    assert report["status"] == "ready_fresh_signal_readiness_fixture"
    assert report["bridge_status"] == "ready_for_official_submit_call"
    assert report["handoff_calls"][0]["fresh_submit_authorization_id"] == (
        "fresh-submit-auth-rtf058"
    )
    assert report["bridge_packet"]["operator_command_plan"]["next_step"] == (
        "call_official_submit_endpoint_after_action_time_final_gate_and_operation_layer_pass"
    )
    command_plan = report["bridge_packet"]["operator_command_plan"]
    assert command_plan["requires_owner_chat_confirmation"] is False
    assert command_plan["uses_standing_runtime_authorization"] is True
    assert command_plan["requires_action_time_final_gate"] is True
    assert command_plan["requires_official_operation_layer"] is True
    assert command_plan["can_continue_without_owner_chat"] is True
    assert command_plan["requires_action_time_confirmation"] is False
    assert (
        report["bridge_packet"]["readiness_handoff_bridge"][
            "operator_command_plan"
        ]["calls_official_submit_endpoint"]
        is False
    )
    assert report["safety_invariants"]["does_not_call_official_submit_endpoint"] is True


def test_ready_signal_fixture_writes_artifacts_and_output(tmp_path):
    output = tmp_path / "fixture-report.json"

    report = script._build_report(_args(tmp_path, output=str(output)))

    assert output.exists()
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["status"] == "ready_fresh_signal_readiness_fixture"
    fixture_files = report["fixture_files"]
    for path in fixture_files.values():
        assert path
    assert (tmp_path / "artifacts" / "fixture-inputs" / "00-signal-input-ready.json").exists()
    assert (
        tmp_path
        / "artifacts"
        / "fixture-inputs"
        / "01-fresh-signal-readiness-bridge.json"
    ).exists()


def test_ready_signal_fixture_cli_stdout_is_json_only(monkeypatch, capsys):
    def fake_build_report(args):
        print("inner noisy fixture")
        return {"status": "ready_fresh_signal_readiness_fixture", "ok": True}

    monkeypatch.setattr(script, "_build_report", fake_build_report)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runtime_fresh_signal_readiness_fixture.py",
            "--artifact-dir",
            "output/rtf058-fixture",
        ],
    )

    assert script.main() == 0

    captured = capsys.readouterr()
    assert captured.out.startswith("{")
    assert "inner noisy fixture" not in captured.out
    assert "inner noisy fixture" in captured.err


def _args(tmp_path, **overrides):
    values = {
        "runtime_instance_id": "runtime-rtf058",
        "runtime_grant_authorization_id": "grant-rtf058",
        "strategy_family_id": "BTPC-001",
        "strategy_family_version_id": "BTPC-001-v0",
        "symbol": "AVAX/USDT:USDT",
        "side": "short",
        "api_base": "http://fixture",
        "artifact_dir": str(tmp_path / "artifacts"),
        "include_fresh_submit_authorization": False,
        "output": None,
    }
    values.update(overrides)
    return type("Args", (), values)()
