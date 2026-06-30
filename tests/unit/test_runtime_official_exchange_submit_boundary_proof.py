from __future__ import annotations

import json

from scripts import runtime_official_exchange_submit_boundary_proof as script


def test_official_exchange_submit_boundary_proof_passes(tmp_path):
    report = script.build_proof_report(tmp_path / "rtf085")

    assert report["status"] == "official_exchange_submit_boundary_passed"
    assert report["order_candidate_id"] == "order-candidate-rtf075-contract"
    assert report["authorization_id"].startswith("runtime-submit-authorization-")
    assert report["exchange_submit_preview_id"].startswith(
        "runtime-exchange-submit-preview-"
    )
    assert report["exchange_submit_action_authorization_id"].startswith(
        "runtime-exchange-submit-action-authorization-"
    )
    assert report["exchange_submit_enablement_decision_id"].startswith(
        "runtime-exchange-submit-enablement-"
    )
    assert report["exchange_submit_adapter_result_id"].startswith(
        "runtime-exchange-submit-adapter-result-"
    )
    assert "operator_command_plan" not in report
    assert report["exchange_submit_boundary_plan"] == {
        "next_step": "build_exchange_submit_execution_result_boundary",
        "uses_official_fastapi_routes": True,
        "uses_fake_console_api": False,
        "live_submit_allowed": False,
        "exchange_submit_execution_enabled": False,
        "calls_exchange_gateway": False,
        "calls_order_lifecycle_submit": False,
        "executes_real_submit": False,
    }

    checks = report["checks"]
    assert checks["shadow_contract_passed"] is True
    assert checks["prepare_authorization_created"] is True
    assert checks["local_adapter_registered_created_orders"] is True
    assert checks["local_registered_two_orders"] is True
    assert checks["local_orders_available_for_exchange_preview"] is True
    assert checks["local_order_lifecycle_submit_not_called"] is True
    assert checks["exchange_submit_preview_ready"] is True
    assert checks["exchange_preview_has_two_requests"] is True
    assert checks["exchange_preview_has_entry_request"] is True
    assert checks["exchange_preview_has_protection_request"] is True
    assert "exchange_packet_has_two_requests" not in checks
    assert "exchange_packet_has_entry_request" not in checks
    assert "exchange_packet_has_protection_request" not in checks
    assert checks["exchange_submit_preview_only"] is True
    assert checks["exchange_action_authorization_approved"] is True
    assert checks["exchange_enablement_ready"] is True
    assert checks["exchange_adapter_result_armed"] is True
    assert checks["exchange_duplicate_lock_acquired"] is True
    assert checks["exchange_adapter_lock_repo_used"] is True
    assert checks["attempt_budget_uses_max_loss_reference"] is True
    assert checks["uses_official_fastapi_routes"] is True
    assert checks["uses_fake_console_api"] is False
    assert checks["pg_written"] is False
    assert checks["exchange_write_called"] is False
    assert checks["exchange_order_submitted"] is False
    assert checks["order_lifecycle_submit_called"] is False
    assert checks["execution_intent_status_changed"] is False
    assert checks["withdrawal_or_transfer_created"] is False


def test_official_exchange_submit_boundary_outputs_artifact(tmp_path):
    output_dir = tmp_path / "rtf085"

    report = script.build_proof_report(output_dir)

    expected_files = [
        "contract-report.json",
        "exchange-submit-boundary-artifact.json",
        "exchange-submit-preview.json",
        "exchange-submit-action-authorization.json",
        "exchange-submit-enablement.json",
        "exchange-submit-adapter-result.json",
        "local-registration-adapter-result.json",
    ]
    for name in expected_files:
        assert (output_dir / name).exists()

    assert json.loads((output_dir / "contract-report.json").read_text())[
        "status"
    ] == report["status"]
    artifact = json.loads(
        (output_dir / "exchange-submit-boundary-artifact.json").read_text()
    )
    assert artifact["status"] == "exchange_submit_adapter_armed_boundary"
    assert artifact["statuses"]["local_registration_adapter_result"] == (
        "registered_created_local_orders"
    )
    assert artifact["statuses"]["exchange_submit_preview"] == (
        "ready_for_exchange_submit_adapter_design"
    )
    assert artifact["statuses"]["exchange_submit_action_authorization"] == (
        "approved_for_exchange_submit_action"
    )
    assert artifact["statuses"]["exchange_submit_enablement"] == (
        "ready_for_exchange_submit_action"
    )
    assert artifact["statuses"]["exchange_submit_adapter_result"] == (
        "exchange_submit_adapter_armed"
    )
    assert artifact["exchange_submit_preview"]["submit_request_count"] == 2
    assert artifact["exchange_submit_preview"]["entry_submit_request_count"] == 1
    assert artifact["exchange_submit_preview"]["protection_submit_request_count"] == 1
    assert artifact["exchange_submit_preview"]["exchange_payload_created"] is False
    assert artifact["exchange_submit_preview"]["exchange_order_id_assigned"] is False
    assert artifact["exchange_submit_boundary"]["duplicate_submit_lock_acquired"] is True
    assert artifact["exchange_submit_boundary"]["exchange_submit_adapter_enabled"] is True
    assert artifact["exchange_submit_boundary"]["exchange_submit_action_authorized"] is True
    assert artifact["exchange_submit_boundary"]["exchange_submit_adapter_implemented"] is False
    assert artifact["exchange_submit_boundary"]["exchange_called"] is False
    assert artifact["exchange_submit_boundary"]["exchange_order_submitted"] is False
    assert artifact["exchange_submit_boundary"]["order_lifecycle_submit_called"] is False
    assert artifact["safety_invariants"]["exchange_submit_adapter_boundary_armed"] is True
    assert artifact["safety_invariants"]["exchange_submit_execution_enabled"] is False
    assert artifact["safety_invariants"]["exchange_write_called"] is False


def test_official_exchange_submit_boundary_cli_stdout_is_json_only(
    capsys,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        script.sys,
        "argv",
        [
            "runtime_official_exchange_submit_boundary_proof.py",
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    assert script.main() == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["status"] == "official_exchange_submit_boundary_passed"
    assert captured.err == ""
