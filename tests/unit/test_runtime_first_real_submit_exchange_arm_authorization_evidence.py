from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    REPO_ROOT
    / "scripts"
    / "build_runtime_first_real_submit_exchange_arm_authorization_evidence.py"
)
AUTHORIZATION_ID = "auth-1"
LOCAL_REGISTRATION_VALUE = (
    f"{AUTHORIZATION_ID}:attempt-local-registration:no-exchange-submit"
)
EXCHANGE_ARM_VALUE = f"{AUTHORIZATION_ID}:exchange-arm:no-real-submit"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_runtime_first_real_submit_exchange_arm_authorization_evidence",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_exchange_arm_evidence_waits_for_owner_confirmation():
    module = _load_module()

    evidence = module.build_exchange_arm_authorization_evidence(
        local_registration_report=_local_registration_report(),
    )

    assert evidence["status"] == "waiting_for_owner_exchange_arm_authorization"
    assert evidence["checks"]["ready_for_owner_exchange_arm_authorization"] is True
    assert evidence["checks"]["action_authorized"] is False
    assert evidence["authorization_id"] == AUTHORIZATION_ID
    assert evidence["owner_confirmation"]["required_value"] == EXCHANGE_ARM_VALUE
    assert "operator_command_plan" not in evidence
    assert (
        evidence["exchange_arm_authorization_plan"]["authorized_exchange_arm_command"]
        is None
    )
    assert evidence["safety_invariants"]["api_called"] is False
    assert evidence["safety_invariants"]["exchange_called"] is False


def test_exchange_arm_evidence_exposes_command_after_exact_confirmation():
    module = _load_module()

    evidence = module.build_exchange_arm_authorization_evidence(
        local_registration_report=_local_registration_report(),
        owner_confirmation_value=EXCHANGE_ARM_VALUE,
    )

    command = evidence["exchange_arm_authorization_plan"][
        "authorized_exchange_arm_command"
    ]
    assert evidence["status"] == "owner_exchange_arm_authorization_evidence_ready"
    assert evidence["checks"]["action_authorized"] is True
    assert command[0] == (
        "OWNER_APPROVED_RUNTIME_LOCAL_REGISTRATION_PREP="
        f"{LOCAL_REGISTRATION_VALUE}"
    )
    assert command[1] == (
        "OWNER_APPROVED_RUNTIME_EXCHANGE_ARM_PREP="
        f"{EXCHANGE_ARM_VALUE}"
    )
    assert "--record-attempt-consumption" not in command
    assert "--skip-exchange-arm" not in command
    assert "--execute-real-submit" not in command
    assert (
        evidence["exchange_arm_authorization_plan"][
            "authorized_command_records_attempt_consumption"
        ]
        is False
    )
    assert (
        evidence["exchange_arm_authorization_plan"][
            "authorized_command_non_mutating_arm_only"
        ]
        is True
    )


def test_exchange_arm_evidence_blocks_without_local_registration_result():
    module = _load_module()
    report = _local_registration_report()
    report["ids"].pop("local_registration_adapter_result_id")

    evidence = module.build_exchange_arm_authorization_evidence(
        local_registration_report=report,
    )

    assert evidence["status"] == "blocked_before_exchange_arm_authorization"
    assert "local_registration_evidence_ids_missing" in evidence["checks"]["blockers"]
    assert (
        evidence["exchange_arm_authorization_plan"]["authorized_exchange_arm_command"]
        is None
    )


def test_exchange_arm_evidence_blocks_when_exchange_already_armed():
    module = _load_module()
    report = _local_registration_report()
    report["ids"]["exchange_submit_adapter_result_id"] = "exchange-adapter-1"

    evidence = module.build_exchange_arm_authorization_evidence(
        local_registration_report=report,
    )

    assert evidence["status"] == "blocked_before_exchange_arm_authorization"
    assert "exchange_or_submit_evidence_already_present" in evidence["checks"]["blockers"]


def test_exchange_arm_evidence_blocks_mismatched_confirmation():
    module = _load_module()

    evidence = module.build_exchange_arm_authorization_evidence(
        local_registration_report=_local_registration_report(),
        owner_confirmation_value="wrong",
    )

    assert evidence["status"] == "blocked_before_exchange_arm_authorization"
    assert "owner_confirmation_value_mismatch" in evidence["checks"]["blockers"]


def test_exchange_arm_evidence_cli_reads_json(tmp_path: Path, capsys):
    module = _load_module()
    report_path = tmp_path / "local-registration-report.json"
    output_path = tmp_path / "exchange-arm-auth.json"
    report_path.write_text(json.dumps(_local_registration_report()))

    exit_code = module.main(
        [
            "--json",
            "--local-registration-report-path",
            str(report_path),
            "--owner-confirmation-value",
            EXCHANGE_ARM_VALUE,
            "--output-json",
            str(output_path),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["checks"]["action_authorized"] is True
    assert json.loads(output_path.read_text())["status"] == (
        "owner_exchange_arm_authorization_evidence_ready"
    )


def _local_registration_report():
    return {
        "script": "runtime_first_real_submit_api_flow",
        "mode": "arm",
        "blockers": [
            "owner_runtime_exchange_arm_env_confirmation_missing",
            (
                "expected_OWNER_APPROVED_RUNTIME_EXCHANGE_ARM_PREP="
                f"{EXCHANGE_ARM_VALUE}"
            ),
        ],
        "warnings": [],
        "ids": {
            "authorization_id": AUTHORIZATION_ID,
            "attempt_outcome_policy_id": "policy-1",
            "local_registration_action_authorization_id": "local-action-1",
            "local_registration_enablement_decision_id": "local-enable-1",
            "local_registration_adapter_result_id": "local-result-1",
            "trusted_submit_fact_snapshot_id": "facts-1",
            "submit_idempotency_policy_id": "idem-1",
            "protection_creation_failure_policy_id": "protect-fail-1",
        },
        "steps": [
            {"name": "hydrate_controlled_submit_plan", "http_status": 200},
            {"name": "record_protection_plan", "http_status": 200},
            {"name": "prepare_machine_evidence", "http_status": 200},
            {"name": "record_attempt_reservation", "http_status": 200},
            {"name": "apply_attempt_mutation", "http_status": 200},
            {"name": "record_attempt_outcome_policy", "http_status": 200},
            {"name": "record_order_lifecycle_handoff_draft", "http_status": 200},
            {
                "name": "record_local_registration_action_authorization",
                "http_status": 200,
            },
            {"name": "preview_local_registration_enablement", "http_status": 200},
            {"name": "record_local_order_registration_result", "http_status": 200},
        ],
        "safety": {
            "exchange_arm_requires_env_confirmation": True,
            "no_withdrawal_or_transfer": True,
        },
    }
