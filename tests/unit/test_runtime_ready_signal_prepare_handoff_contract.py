from __future__ import annotations

import json
import sys

from scripts import runtime_ready_signal_prepare_handoff_contract as script


def test_ready_signal_prepare_handoff_contract_reaches_preflight(tmp_path):
    report = script.build_contract_report(tmp_path / "rtf077")

    assert report["status"] == "ready_signal_prepare_handoff_contract_passed"
    assert report["order_candidate_id"] == "order-candidate-rtf075-contract"
    assert report["prepared_authorization_id"] == "auth-rtf077-prepare-handoff"
    assert report["runtime_execution_intent_draft_id"] == (
        "draft-rtf077-prepare-handoff"
    )
    assert report["execution_intent_id"] == "intent-rtf077-prepare-handoff"
    assert report["protection_plan_id"] == "protection-rtf077-prepare-handoff"
    checks = report["checks"]
    assert checks["shadow_contract_passed"] is True
    assert checks["shadow_candidate_created"] is True
    assert checks["right_tail_runner_preserved"] is True
    assert checks["prepare_ready_for_final_gate_preflight"] is True
    assert checks["next_attempt_gate_checked"] is True
    assert checks["order_candidate_usage_checked"] is True
    assert checks["runtime_execution_intent_draft_created"] is True
    assert checks["execution_intent_created"] is True
    assert checks["protection_plan_created"] is True
    assert checks["submit_authorization_created"] is True
    assert checks["places_order"] is False
    assert checks["calls_order_lifecycle"] is False
    assert checks["exchange_write_called"] is False
    assert checks["attempt_counter_mutated"] is False
    assert checks["runtime_budget_mutated"] is False
    assert checks["withdrawal_or_transfer_created"] is False


def test_ready_signal_prepare_handoff_contract_outputs_audit_artifacts(tmp_path):
    output_dir = tmp_path / "rtf077"

    report = script.build_contract_report(output_dir)

    contract_path = output_dir / "contract-report.json"
    shadow_path = output_dir / "shadow-contract-report.json"
    prepare_path = output_dir / "prepare-artifact.json"
    nested_shadow_path = output_dir / "shadow-planning" / "contract-report.json"
    assert contract_path.exists()
    assert shadow_path.exists()
    assert prepare_path.exists()
    assert nested_shadow_path.exists()
    assert json.loads(contract_path.read_text())["status"] == report["status"]
    prepare_artifact = json.loads(prepare_path.read_text())
    assert prepare_artifact["status"] == "ready_for_final_gate_preflight"
    assert "operator_command_plan" not in prepare_artifact
    assert prepare_artifact["prepare_artifact_plan"]["places_order"] is False
    assert prepare_artifact["safety_invariants"]["exchange_write_called"] is False
    assert prepare_artifact["safety_invariants"]["order_lifecycle_called"] is False
    assert "prepare_packet" not in report
    assert "operator_command_plan" not in report
    assert report["prepare_handoff_plan"]["places_order"] is False
    assert report["prepare_artifact"]["status"] == "ready_for_final_gate_preflight"


def test_ready_signal_prepare_handoff_contract_cli_stdout_is_json_only(
    monkeypatch,
    capsys,
    tmp_path,
):
    monkeypatch.setattr(
        script.sys,
        "argv",
        [
            "runtime_ready_signal_prepare_handoff_contract.py",
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    assert script.main() == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["status"] == "ready_signal_prepare_handoff_contract_passed"
    assert "prepare_artifact" in payload
    assert "prepare_packet" not in payload
    assert captured.err == ""


def test_ready_signal_prepare_handoff_contract_blocks_without_candidate(monkeypatch, tmp_path):
    monkeypatch.setattr(
        script.shadow_fixture,
        "build_contract_fixture_report",
        lambda output_dir: {
            "scope": "runtime_ready_signal_shadow_planning_contract_fixture",
            "status": "blocked",
            "checks": {},
            "blockers": ["shadow_candidate_missing"],
            "warnings": [],
        },
    )

    try:
        script.build_contract_report(tmp_path / "rtf077")
    except ValueError as exc:
        assert str(exc) == "shadow_candidate_snapshot_missing"
    else:
        raise AssertionError("missing candidate snapshot must block contract")
