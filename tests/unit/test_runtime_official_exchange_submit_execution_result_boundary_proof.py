from __future__ import annotations

import json

from scripts import (
    runtime_official_exchange_submit_execution_result_boundary_proof as script,
)


def test_official_exchange_submit_execution_result_boundary_passes(tmp_path):
    report = script.build_proof_report(tmp_path / "rtf086")

    assert (
        report["status"]
        == "official_exchange_submit_execution_result_boundary_passed"
    )
    assert report["order_candidate_id"] == "order-candidate-rtf075-contract"
    assert report["authorization_id"].startswith("runtime-submit-authorization-")
    assert report["exchange_submit_execution_result_id"].startswith(
        "runtime-exchange-submit-execution-result-"
    )
    assert "operator_command_plan" not in report
    assert report["exchange_submit_execution_result_boundary_plan"] == {
        "next_step": "build_controlled_gateway_action_proof",
        "uses_official_fastapi_routes": True,
        "uses_fake_console_api": False,
        "live_submit_allowed": False,
        "exchange_submit_execution_enabled": False,
        "calls_exchange_gateway": False,
        "calls_order_lifecycle_submit": False,
        "executes_real_submit": False,
    }

    checks = report["checks"]
    assert checks["exchange_boundary_artifact_passed"] is True
    assert checks["exchange_adapter_result_armed"] is True
    assert checks["exchange_execution_result_disabled"] is True
    assert checks["exchange_execution_enabled_false"] is True
    assert checks["exchange_execution_mode_disabled"] is True
    assert checks["exchange_execution_result_has_id"] is True
    assert checks["exchange_execution_result_has_no_blockers"] is True
    assert checks["exchange_call_count_zero"] is True
    assert checks["order_lifecycle_submit_call_count_zero"] is True
    assert checks["submitted_local_order_ids_empty"] is True
    assert checks["submitted_exchange_order_ids_empty"] is True
    assert checks["uses_official_fastapi_routes"] is True
    assert checks["uses_fake_console_api"] is False
    assert checks["pg_written"] is False
    assert checks["exchange_write_called"] is False
    assert checks["exchange_order_submitted"] is False
    assert checks["order_lifecycle_submit_called"] is False
    assert checks["execution_intent_status_changed"] is False
    assert checks["withdrawal_or_transfer_created"] is False


def test_official_exchange_submit_execution_result_boundary_outputs_artifact(
    tmp_path,
):
    output_dir = tmp_path / "rtf086"

    report = script.build_proof_report(output_dir)

    expected_files = [
        "contract-report.json",
        "exchange-submit-boundary-artifact.json",
        "exchange-submit-execution-result.json",
        "exchange-submit-execution-result-boundary-artifact.json",
    ]
    for name in expected_files:
        assert (output_dir / name).exists()

    assert json.loads((output_dir / "contract-report.json").read_text())[
        "status"
    ] == report["status"]
    artifact = json.loads(
        (
            output_dir
            / "exchange-submit-execution-result-boundary-artifact.json"
        ).read_text()
    )
    assert artifact["status"] == "exchange_submit_execution_disabled_boundary"
    assert artifact["statuses"]["exchange_submit_adapter_result"] == (
        "exchange_submit_adapter_armed"
    )
    assert artifact["statuses"]["exchange_submit_execution_result"] == (
        "exchange_submit_execution_disabled"
    )
    result = artifact["exchange_submit_execution_result"]
    assert result["status"] == "exchange_submit_execution_disabled"
    assert result["exchange_submit_execution_enabled"] is False
    assert result["execution_mode"] == "disabled"
    assert result["exchange_call_count"] == 0
    assert result["order_lifecycle_submit_call_count"] == 0
    assert result["exchange_called"] is False
    assert result["exchange_order_submitted"] is False
    assert result["real_exchange_submit_adapter_executed"] is False
    assert result["order_lifecycle_submit_called"] is False
    assert result["execution_intent_status_changed"] is False
    assert result["submitted_local_order_ids"] == []
    assert result["submitted_exchange_order_ids"] == []
    assert result["blockers"] == []
    assert artifact["safety_invariants"]["exchange_submit_execution_enabled"] is False
    assert artifact["safety_invariants"]["exchange_write_called"] is False
    assert artifact["safety_invariants"]["order_lifecycle_submit_called"] is False


def test_official_exchange_submit_execution_result_boundary_cli_stdout_is_json_only(
    capsys,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        script.sys,
        "argv",
        [
            "runtime_official_exchange_submit_execution_result_boundary_proof.py",
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    assert script.main() == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert (
        payload["status"]
        == "official_exchange_submit_execution_result_boundary_passed"
    )
    assert captured.err == ""
