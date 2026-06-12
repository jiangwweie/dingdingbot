from __future__ import annotations

import json

from scripts import runtime_ready_signal_shadow_planning_contract_fixture as script


def test_ready_signal_contract_fixture_reaches_shadow_candidate_planning(tmp_path):
    report = script.build_contract_fixture_report(tmp_path / "rtf075")

    assert report["status"] == "ready_signal_shadow_planning_contract_passed"
    assert report["bridge_status"] == "ready_for_final_gate_preflight"
    assert report["order_candidate_id"] == "order-candidate-rtf075-contract"
    checks = report["checks"]
    assert checks["shadow_signal_evaluation_created"] is True
    assert checks["shadow_order_candidate_created"] is True
    assert checks["entry_price_reference_present"] is True
    assert checks["stop_price_reference_present"] is True
    assert checks["tp1_present"] is True
    assert checks["runner_present"] is True
    assert checks["right_tail_runner_preserved"] is True
    assert checks["notional_present"] is True
    assert checks["leverage_present"] is True
    assert checks["execution_intent_created"] is False
    assert checks["submit_authorization_created"] is False
    assert checks["order_created"] is False
    assert checks["exchange_write_called"] is False


def test_ready_signal_contract_fixture_outputs_audit_artifacts(tmp_path):
    output_dir = tmp_path / "rtf075"

    report = script.build_contract_fixture_report(output_dir)

    contract_path = output_dir / "contract-report.json"
    bridge_path = output_dir / "bridge-report.json"
    planning_path = (
        output_dir
        / "bridge-artifacts"
        / "rtf075-ready-signal-strategy-planning-flow.json"
    )
    assert contract_path.exists()
    assert bridge_path.exists()
    assert planning_path.exists()
    assert json.loads(contract_path.read_text())["status"] == report["status"]
    bridge_packet = json.loads(bridge_path.read_text())
    planning_packet = json.loads(planning_path.read_text())
    assert bridge_packet["operator_command_plan"]["creates_shadow_candidate"] is True
    assert bridge_packet["operator_command_plan"]["places_order"] is False
    assert planning_packet["api_payload"]["candidate_planning_result"]["proposal"][
        "stop_source"
    ] == "cpm_pullback_low"
    assert planning_packet["api_payload"]["execution_intent_created"] is False
    assert planning_packet["api_payload"]["order_created"] is False


def test_ready_signal_contract_fixture_cli_stdout_is_json_only(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(
        script,
        "build_contract_fixture_report",
        lambda output_dir: {
            "scope": "runtime_ready_signal_shadow_planning_contract_fixture",
            "status": "ready_signal_shadow_planning_contract_passed",
        },
    )
    monkeypatch.setattr(
        script.sys,
        "argv",
        [
            "runtime_ready_signal_shadow_planning_contract_fixture.py",
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    assert script.main() == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["status"] == (
        "ready_signal_shadow_planning_contract_passed"
    )
