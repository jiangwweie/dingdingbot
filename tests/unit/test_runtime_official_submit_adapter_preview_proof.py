from __future__ import annotations

import json

from scripts import runtime_official_submit_adapter_preview_proof as script


def test_official_submit_adapter_preview_proof_passes(tmp_path):
    report = script.build_proof_report(tmp_path / "rtf083")

    assert report["status"] == "official_submit_adapter_preview_passed"
    assert report["order_candidate_id"] == "order-candidate-rtf075-contract"
    assert report["authorization_id"].startswith("runtime-submit-authorization-")
    assert report["submit_adapter_preview_id"].startswith(
        "runtime-submit-adapter-preview-"
    )
    assert report["order_registration_draft_preview_id"].startswith(
        "runtime-order-registration-draft-preview-"
    )
    assert "operator_command_plan" not in report
    assert report["submit_adapter_preview_plan"] == {
        "next_step": "build_scoped_local_registration_enablement",
        "uses_official_fastapi_routes": True,
        "uses_fake_console_api": False,
        "live_submit_allowed": False,
        "local_registration_enabled": False,
        "places_order": False,
        "calls_order_lifecycle": False,
        "executes_real_submit": False,
    }

    checks = report["checks"]
    assert checks["shadow_contract_passed"] is True
    assert checks["right_tail_runner_preserved"] is True
    assert checks["prepare_authorization_created"] is True
    assert checks["final_gate_verdict_pass"] is True
    assert checks["controlled_submit_preflight_ready"] is True
    assert checks["submit_adapter_preview_route_called"] is True
    assert checks["submit_adapter_preview_ready_not_implemented"] is True
    assert checks["submit_adapter_preview_preview_only"] is True
    assert checks["attempt_reservation_preview_ready"] is True
    assert checks["attempt_reservation_recorded_pending_mutation"] is True
    assert checks["attempt_mutation_applied_in_memory"] is True
    assert checks["budget_reservation_prefers_max_loss_reference"] is True
    assert checks["order_lifecycle_handoff_ready"] is True
    assert checks["order_lifecycle_adapter_preview_ready"] is True
    assert checks["order_registration_draft_preview_ready"] is True
    assert checks["registration_has_entry_draft"] is True
    assert checks["registration_has_protection_draft"] is True
    assert checks["local_registration_not_enabled"] is True
    assert checks["uses_official_fastapi_routes"] is True
    assert checks["uses_fake_console_api"] is False
    assert checks["pg_written"] is False
    assert checks["exchange_write_called"] is False
    assert checks["order_created"] is False
    assert checks["order_lifecycle_called"] is False
    assert checks["withdrawal_or_transfer_created"] is False


def test_official_submit_adapter_preview_outputs_boundary_artifact(tmp_path):
    output_dir = tmp_path / "rtf083"

    report = script.build_proof_report(output_dir)

    expected_files = [
        "contract-report.json",
        "submit-adapter-boundary-artifact.json",
        "submit-adapter-preview.json",
        "attempt-reservation-preview.json",
        "attempt-reservation.json",
        "attempt-mutation.json",
        "order-lifecycle-handoff.json",
        "order-lifecycle-adapter-preview.json",
        "order-registration-draft-preview.json",
    ]
    for name in expected_files:
        assert (output_dir / name).exists()

    assert json.loads((output_dir / "contract-report.json").read_text())[
        "status"
    ] == report["status"]
    artifact = json.loads(
        (output_dir / "submit-adapter-boundary-artifact.json").read_text()
    )
    assert artifact["status"] == "ready_for_local_registration_boundary_review"
    assert artifact["statuses"]["submit_adapter_preview"] == (
        "inputs_ready_adapter_not_implemented"
    )
    assert artifact["statuses"]["attempt_mutation"] == "applied"
    assert artifact["statuses"]["order_lifecycle_handoff"] == (
        "ready_for_order_lifecycle_adapter"
    )
    assert artifact["statuses"]["order_registration_draft_preview"] == (
        "inputs_ready_registration_draft_only"
    )
    assert artifact["local_registration_boundary"]["registration_draft_count"] == 2
    assert artifact["local_registration_boundary"][
        "local_order_registration_enabled"
    ] is False
    assert artifact["runtime_attempt_budget_boundary"][
        "budget_reservation_basis"
    ] == "max_loss_reference"
    assert artifact["runtime_attempt_budget_boundary"][
        "budget_reservation_amount"
    ] == "0.44145873"
    assert artifact["safety_invariants"]["order_created"] is False
    assert artifact["safety_invariants"]["order_lifecycle_called"] is False
    assert artifact["safety_invariants"]["exchange_write_called"] is False


def test_official_submit_adapter_preview_cli_stdout_is_json_only(
    capsys,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        script.sys,
        "argv",
        [
            "runtime_official_submit_adapter_preview_proof.py",
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    assert script.main() == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["status"] == "official_submit_adapter_preview_passed"
    assert captured.err == ""
