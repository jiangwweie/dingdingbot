from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    REPO_ROOT
    / "scripts"
    / "build_runtime_first_real_submit_local_registration_authorization_packet.py"
)
AUTHORIZATION_ID = "auth-1"
APPROVAL_VALUE = (
    f"{AUTHORIZATION_ID}:attempt-local-registration:no-exchange-submit"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_runtime_first_real_submit_local_registration_authorization_packet",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_local_registration_packet_waits_for_owner_confirmation():
    module = _load_module()

    packet = module.build_local_registration_authorization_packet(
        disabled_smoke_report=_disabled_smoke_report(),
    )

    assert packet["status"] == "waiting_for_owner_local_registration_authorization"
    assert packet["checks"]["ready_for_owner_local_registration_authorization"] is True
    assert packet["checks"]["action_authorized"] is False
    assert packet["authorization_id"] == AUTHORIZATION_ID
    assert packet["owner_confirmation"]["required_value"] == APPROVAL_VALUE
    assert packet["operator_command_plan"]["authorized_local_registration_command"] is None
    assert packet["operator_command_plan"]["preview_command"][-3:] == [
        "--authorization-id",
        AUTHORIZATION_ID,
        "--skip-exchange-arm",
    ]
    assert packet["safety_invariants"]["api_called"] is False
    assert packet["safety_invariants"]["attempt_counter_mutated"] is False
    assert packet["safety_invariants"]["exchange_called"] is False


def test_local_registration_packet_exposes_mutating_command_after_exact_confirmation():
    module = _load_module()

    packet = module.build_local_registration_authorization_packet(
        disabled_smoke_report=_disabled_smoke_report(),
        owner_confirmation_value=APPROVAL_VALUE,
    )

    command = packet["operator_command_plan"]["authorized_local_registration_command"]
    assert packet["status"] == "owner_local_registration_authorization_packet_ready"
    assert packet["checks"]["action_authorized"] is True
    assert command[0] == (
        "OWNER_APPROVED_RUNTIME_LOCAL_REGISTRATION_PREP="
        f"{APPROVAL_VALUE}"
    )
    assert "--record-attempt-consumption" in command
    assert "--skip-exchange-arm" in command
    assert "--execute-real-submit" not in command


def test_local_registration_packet_blocks_without_evidence_probe():
    module = _load_module()
    report = _disabled_smoke_report()
    report["steps"] = report["steps"][:1]

    packet = module.build_local_registration_authorization_packet(
        disabled_smoke_report=report,
    )

    assert packet["status"] == "blocked_before_local_registration_authorization"
    assert "prepare_machine_evidence_probe_missing" in packet["checks"]["blockers"]
    assert packet["operator_command_plan"]["authorized_local_registration_command"] is None


def test_local_registration_packet_blocks_mismatched_confirmation():
    module = _load_module()

    packet = module.build_local_registration_authorization_packet(
        disabled_smoke_report=_disabled_smoke_report(),
        owner_confirmation_value="wrong",
    )

    assert packet["status"] == "blocked_before_local_registration_authorization"
    assert packet["checks"]["action_authorized"] is False
    assert "owner_confirmation_value_mismatch" in packet["checks"]["blockers"]


def test_local_registration_packet_cli_reads_json(tmp_path: Path, capsys):
    module = _load_module()
    smoke_path = tmp_path / "disabled-smoke.json"
    output_path = tmp_path / "local-registration-auth.json"
    smoke_path.write_text(json.dumps(_disabled_smoke_report()))

    exit_code = module.main(
        [
            "--json",
            "--disabled-smoke-report-path",
            str(smoke_path),
            "--owner-confirmation-value",
            APPROVAL_VALUE,
            "--output-json",
            str(output_path),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["checks"]["action_authorized"] is True
    assert json.loads(output_path.read_text())["status"] == (
        "owner_local_registration_authorization_packet_ready"
    )


def _disabled_smoke_report():
    return {
        "script": "runtime_first_real_submit_api_flow",
        "mode": "disabled-smoke",
        "ready_for_real_submit_action": False,
        "blockers": ["preview_disabled_first_real_submit_action_http_404"],
        "warnings": [
            (
                "disabled_first_real_submit_action_prerequisite_missing:"
                "RuntimeExecutionOrderLifecycleAdapterResult not found"
            )
        ],
        "ids": {
            "authorization_id": AUTHORIZATION_ID,
            "trusted_submit_fact_snapshot_id": "facts-1",
            "submit_idempotency_policy_id": "idem-1",
            "protection_creation_failure_policy_id": "protect-fail-1",
            "post_submit_budget_settlement_persistence_evidence_id": "settle-1",
        },
        "steps": [
            {
                "name": "preview_disabled_first_real_submit_action",
                "http_status": 404,
                "detail": "RuntimeExecutionOrderLifecycleAdapterResult not found",
                "blockers": [],
            },
            {
                "name": "prepare_machine_evidence",
                "http_status": 200,
                "status": "blocked_before_packet",
                "blockers": [
                    (
                        "first_real_submit_packet_unavailable:"
                        "runtimeexecutionorderlifecycleadapterresult_not_found"
                    )
                ],
            },
        ],
        "safety": {
            "owner_authorization_required_for_real_submit": True,
            "no_withdrawal_or_transfer": True,
        },
    }
