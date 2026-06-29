from __future__ import annotations

import json

from scripts import runtime_official_scoped_local_registration_proof as script


def test_official_scoped_local_registration_proof_passes(tmp_path):
    report = script.build_proof_report(tmp_path / "rtf084")

    assert report["status"] == "official_scoped_local_registration_passed"
    assert report["order_candidate_id"] == "order-candidate-rtf075-contract"
    assert report["authorization_id"].startswith("runtime-submit-authorization-")
    assert report["local_registration_enablement_decision_id"].startswith(
        "runtime-local-registration-enablement-"
    )
    assert report["local_registration_adapter_result_id"].startswith(
        "runtime-order-lifecycle-adapter-result-"
    )
    assert len(report["local_order_ids"]) == 2
    assert "operator_command_plan" not in report
    assert report["scoped_local_registration_plan"] == {
        "next_step": "build_exchange_submit_preview",
        "uses_official_fastapi_routes": True,
        "uses_fake_console_api": False,
        "local_created_orders_registered": True,
        "live_submit_allowed": False,
        "exchange_submit_enabled": False,
        "calls_exchange": False,
        "executes_real_submit": False,
    }

    checks = report["checks"]
    assert checks["shadow_contract_passed"] is True
    assert checks["prepare_authorization_created"] is True
    assert checks["controlled_submit_preflight_ready"] is True
    assert checks["submit_adapter_preview_ready_not_implemented"] is True
    assert checks["attempt_reservation_pending_mutation"] is True
    assert checks["attempt_mutation_applied"] is True
    assert checks["attempt_budget_uses_max_loss_reference"] is True
    assert checks["attempt_outcome_policy_ready"] is True
    assert checks["order_lifecycle_handoff_ready"] is True
    assert checks["order_registration_draft_preview_ready"] is True
    assert checks["local_action_authorization_approved"] is True
    assert checks["local_registration_enablement_ready"] is True
    assert checks["adapter_result_registered_created_orders"] is True
    assert checks["registered_two_local_orders"] is True
    assert checks["registered_one_entry_order"] is True
    assert checks["registered_one_protection_order"] is True
    assert checks["duplicate_submit_lock_acquired"] is True
    assert checks["lifecycle_register_called_for_each_order"] is True
    assert checks["registered_orders_remain_created"] is True
    assert checks["registered_orders_have_no_exchange_id"] is True
    assert checks["uses_official_fastapi_routes"] is True
    assert checks["uses_fake_console_api"] is False
    assert checks["pg_written"] is False
    assert checks["exchange_write_called"] is False
    assert checks["exchange_submit_enabled"] is False
    assert checks["withdrawal_or_transfer_created"] is False


def test_official_scoped_local_registration_outputs_registration_artifact(tmp_path):
    output_dir = tmp_path / "rtf084"

    report = script.build_proof_report(output_dir)

    expected_files = [
        "contract-report.json",
        "local-registration-artifact.json",
        "local-registration-action-authorization.json",
        "local-registration-enablement.json",
        "local-registration-adapter-result.json",
        "attempt-outcome-policy.json",
    ]
    for name in expected_files:
        assert (output_dir / name).exists()

    assert json.loads((output_dir / "contract-report.json").read_text())[
        "status"
    ] == report["status"]
    artifact = json.loads((output_dir / "local-registration-artifact.json").read_text())
    assert artifact["status"] == "local_created_orders_registered"
    assert artifact["statuses"]["local_registration_action_authorization"] == (
        "approved_for_local_registration_action"
    )
    assert artifact["statuses"]["local_registration_enablement"] == (
        "ready_for_local_registration_action"
    )
    assert artifact["statuses"]["adapter_result"] == "registered_created_local_orders"
    assert artifact["local_registration"]["registered_order_count"] == 2
    assert len(artifact["local_registration"]["entry_order_ids"]) == 1
    assert len(artifact["local_registration"]["protection_order_ids"]) == 1
    assert artifact["local_registration"]["duplicate_submit_lock_acquired"] is True
    assert artifact["local_registration"]["order_lifecycle_called"] is True
    assert artifact["local_registration"]["exchange_called"] is False
    assert artifact["lifecycle_observation"]["register_call_count"] == 2
    assert artifact["safety_invariants"]["local_created_orders_registered"] is True
    assert artifact["safety_invariants"]["exchange_submit_enabled"] is False
    assert artifact["safety_invariants"]["exchange_write_called"] is False


def test_official_scoped_local_registration_cli_stdout_is_json_only(
    capsys,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        script.sys,
        "argv",
        [
            "runtime_official_scoped_local_registration_proof.py",
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    assert script.main() == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["status"] == "official_scoped_local_registration_passed"
    assert captured.err == ""
