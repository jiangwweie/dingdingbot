from __future__ import annotations

import json

from scripts import runtime_official_server_prepare_integration_proof as script


def test_official_server_prepare_integration_proof_passes(tmp_path):
    report = script.build_proof_report(tmp_path / "rtf079")

    assert report["status"] == "official_server_prepare_integration_passed"
    assert report["order_candidate_id"] == "order-candidate-rtf075-contract"
    assert report["prepared_authorization_id"].startswith(
        "runtime-submit-authorization-"
    )
    assert "operator_command_plan" not in report
    assert report["server_prepare_integration_plan"] == {
        "next_step": "run_official_final_gate_preflight",
        "uses_official_fastapi_routes": True,
        "uses_official_prepare_wrapper": True,
        "uses_fake_console_api": False,
        "records_prepare_governance_in_memory_only": True,
        "live_submit_allowed": False,
        "places_order": False,
        "calls_order_lifecycle": False,
        "executes_real_submit": False,
    }
    checks = report["checks"]
    assert checks["shadow_contract_passed"] is True
    assert checks["right_tail_runner_preserved"] is True
    assert checks["uses_official_fastapi_routes"] is True
    assert checks["uses_fake_console_api"] is False
    assert checks["official_prepare_wrapper_used"] is True
    assert checks["next_attempt_gate_checked"] is True
    assert checks["order_candidate_usage_checked"] is True
    assert checks["intent_draft_route_called"] is True
    assert checks["execution_intent_route_called"] is True
    assert checks["protection_plan_route_called"] is True
    assert checks["submit_authorization_route_called"] is True
    assert checks["evidence_preparation_route_called"] is True
    assert checks["evidence_preparation_artifact_created"] is True
    assert checks["evidence_preparation_not_dependency_blocked"] is True
    assert checks["evidence_preparation_status_prepared_artifact_blocked"] is True
    assert checks["prepare_ready_for_final_gate_preflight"] is True
    assert checks["trusted_submit_facts_prepared"] is True
    assert checks["submit_idempotency_prepared"] is True
    assert checks["protection_failure_policy_prepared"] is True
    assert checks["pg_written"] is False
    assert checks["exchange_write_called"] is False
    assert checks["order_created"] is False
    assert checks["order_lifecycle_called"] is False
    assert checks["attempt_counter_mutated"] is False
    assert checks["runtime_budget_mutated"] is False
    assert checks["withdrawal_or_transfer_created"] is False


def test_official_server_prepare_integration_outputs_audit_artifacts(tmp_path):
    output_dir = tmp_path / "rtf079"

    report = script.build_proof_report(output_dir)

    contract_path = output_dir / "contract-report.json"
    prepare_report_path = output_dir / "prepare-report.json"
    prepare_artifact_path = output_dir / "prepare-artifact.json"
    shadow_path = output_dir / "shadow-contract-report.json"
    assert contract_path.exists()
    assert prepare_report_path.exists()
    assert prepare_artifact_path.exists()
    assert shadow_path.exists()
    assert json.loads(contract_path.read_text())["status"] == report["status"]
    prepare_artifact = json.loads(prepare_artifact_path.read_text())
    assert prepare_artifact["status"] == "ready_for_final_gate_preflight"
    evidence_preparation = prepare_artifact["evidence_preparation"]
    assert evidence_preparation["status"] == "prepared_evidence_blocked"
    assert evidence_preparation["source_status"] == "blocked"
    assert "packet_status" not in evidence_preparation
    assert evidence_preparation["artifact_created"] is True
    assert evidence_preparation["dependency_blocked"] is False
    assert not any(
        "repository_unavailable" in blocker
        or "service_unavailable" in blocker
        for blocker in evidence_preparation["blockers"]
    )
    assert prepare_artifact["safety_invariants"]["uses_official_fastapi_routes"] is True
    assert prepare_artifact["safety_invariants"]["uses_fake_console_api"] is False
    assert prepare_artifact["safety_invariants"]["pg_written"] is False
    assert prepare_artifact["safety_invariants"]["exchange_write_called"] is False
    assert prepare_artifact["safety_invariants"]["order_lifecycle_called"] is False


def test_official_server_prepare_integration_cli_stdout_is_json_only(capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(
        script.sys,
        "argv",
        [
            "runtime_official_server_prepare_integration_proof.py",
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    assert script.main() == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["status"] == "official_server_prepare_integration_passed"
    assert captured.err == ""
