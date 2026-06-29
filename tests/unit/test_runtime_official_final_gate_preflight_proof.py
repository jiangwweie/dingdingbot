from __future__ import annotations

import json

from scripts import runtime_official_final_gate_preflight_proof as script


def test_official_final_gate_preflight_proof_passes(tmp_path):
    report = script.build_proof_report(tmp_path / "rtf081")

    assert report["status"] == "official_final_gate_preflight_passed"
    assert report["order_candidate_id"] == "order-candidate-rtf075-contract"
    assert report["authorization_id"].startswith("runtime-submit-authorization-")
    assert report["controlled_submit_preflight_id"].startswith(
        "runtime-controlled-submit-preflight-"
    )
    assert "operator_command_plan" not in report
    assert report["final_gate_preflight_plan"] == {
        "next_step": "build_non_executing_submit_adapter_preview",
        "uses_official_fastapi_routes": True,
        "uses_fake_console_api": False,
        "live_submit_allowed": False,
        "places_order": False,
        "calls_order_lifecycle": False,
        "executes_real_submit": False,
    }

    checks = report["checks"]
    assert checks["shadow_contract_passed"] is True
    assert checks["right_tail_runner_preserved"] is True
    assert checks["prepare_authorization_created"] is True
    assert checks["final_gate_preview_route_called"] is True
    assert checks["final_gate_verdict_pass"] is True
    assert checks["final_gate_no_blockers"] is True
    assert checks["controlled_submit_plan_route_called"] is True
    assert checks["controlled_submit_plan_ready"] is True
    assert checks["controlled_submit_preflight_route_called"] is True
    assert checks["controlled_submit_preflight_ready"] is True
    assert checks["preflight_final_gate_verdict_pass"] is True
    assert checks["preflight_preview_only"] is True
    assert checks["preflight_no_blockers"] is True
    assert checks["uses_official_fastapi_routes"] is True
    assert checks["uses_fake_console_api"] is False
    assert checks["pg_written"] is False
    assert checks["exchange_write_called"] is False
    assert checks["order_created"] is False
    assert checks["order_lifecycle_called"] is False
    assert checks["attempt_counter_mutated"] is False
    assert checks["runtime_budget_mutated"] is False
    assert checks["withdrawal_or_transfer_created"] is False


def test_official_final_gate_preflight_outputs_audit_artifacts(tmp_path):
    output_dir = tmp_path / "rtf081"

    report = script.build_proof_report(output_dir)

    contract_path = output_dir / "contract-report.json"
    preflight_artifact_path = output_dir / "preflight-artifact.json"
    final_gate_path = output_dir / "final-gate-preview.json"
    controlled_plan_path = output_dir / "controlled-submit-plan.json"
    controlled_preflight_path = output_dir / "controlled-submit-preflight.json"
    assert contract_path.exists()
    assert preflight_artifact_path.exists()
    assert final_gate_path.exists()
    assert controlled_plan_path.exists()
    assert controlled_preflight_path.exists()

    assert json.loads(contract_path.read_text())["status"] == report["status"]
    artifact = json.loads(preflight_artifact_path.read_text())
    assert artifact["status"] == "ready_for_controlled_submit_adapter"
    assert artifact["final_gate"]["verdict"] == "PASS"
    assert artifact["controlled_submit_plan"]["status"] == (
        "ready_for_controlled_submit_adapter"
    )
    assert artifact["controlled_submit_preflight"]["status"] == (
        "ready_for_controlled_submit_adapter"
    )
    assert artifact["controlled_submit_preflight"]["preview_only"] is True
    assert artifact["safety_invariants"]["exchange_write_called"] is False
    assert artifact["safety_invariants"]["order_lifecycle_called"] is False
    assert artifact["safety_invariants"]["order_created"] is False


def test_official_final_gate_preflight_cli_stdout_is_json_only(
    capsys,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        script.sys,
        "argv",
        [
            "runtime_official_final_gate_preflight_proof.py",
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    assert script.main() == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["status"] == "official_final_gate_preflight_passed"
    assert captured.err == ""
