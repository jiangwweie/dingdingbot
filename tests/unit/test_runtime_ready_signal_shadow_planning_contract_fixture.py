from __future__ import annotations

import inspect
import json

from scripts import runtime_ready_signal_shadow_planning_contract_fixture as script


def test_ready_signal_contract_fixture_reaches_shadow_candidate_planning(tmp_path):
    report = script.build_contract_fixture_report(tmp_path / "rtf075")

    assert report["status"] == "ready_signal_shadow_planning_contract_passed"
    assert report["projection_status"] == "ready_for_final_gate_preflight"
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
    projection_path = output_dir / "projection-report.json"
    planning_path = (
        output_dir
        / "projection-artifacts"
        / "rtf075-ready-signal-strategy-planning-flow.json"
    )
    assert contract_path.exists()
    assert projection_path.exists()
    assert planning_path.exists()
    assert json.loads(contract_path.read_text())["status"] == report["status"]
    projection_artifact = json.loads(projection_path.read_text())
    planning_artifact = json.loads(planning_path.read_text())
    assert "operator_command_plan" not in projection_artifact
    assert projection_artifact["shadow_planning_plan"]["creates_shadow_candidate"] is True
    assert projection_artifact["shadow_planning_plan"]["places_order"] is False
    assert planning_artifact["api_payload"]["candidate_planning_result"]["proposal"][
        "stop_source"
    ] == "cpm_pullback_low"
    assert planning_artifact["api_payload"]["execution_intent_created"] is False
    assert planning_artifact["api_payload"]["order_created"] is False


def test_ready_signal_contract_fixture_source_uses_artifact_boundary_wording():
    assert "ready operator packet" not in (script.__doc__ or "")
    assert "ready operator artifact" in (script.__doc__ or "")
    source = inspect.getsource(script._post_submit_finalize_payload)
    assert "runtime_state_mutated_by_packet" not in source


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
