from __future__ import annotations

import json

from scripts import runtime_scoped_local_order_adapter_boundary_from_evidence as script


def test_sample_rehearsal_blocks_local_registration_by_default(tmp_path):
    evidence_path = _write_evidence(tmp_path)

    report = script._build_report(
        _args(tmp_path, evidence_path=evidence_path, source_kind="sample_rehearsal")
    )

    assert (
        report["status"]
        == "blocked_sample_rehearsal_local_registration_not_allowed"
    )
    assert "sample_rehearsal_local_registration_not_allowed" in report["blockers"]
    assert report["fresh_submit_authorization_id"] == "auth-rtf017"
    assert (
        report["operator_command_preview"]["scope"]
        == "local_registration_only_no_exchange_arm"
    )
    assert report["safety_invariants"]["local_order_registration_called"] is False
    assert report["safety_invariants"]["order_lifecycle_called"] is False
    assert report["safety_invariants"]["exchange_write_called"] is False


def test_scoped_local_registration_proof_can_be_made_ready(tmp_path):
    evidence_path = _write_evidence(tmp_path)

    report = script._build_report(
        _args(
            tmp_path,
            evidence_path=evidence_path,
            source_kind="scoped_local_registration_proof",
            allow_scoped_local_registration_proof=True,
            api_base="http://unit",
            env_file=".env.unit",
        )
    )

    assert report["status"] == "ready_for_scoped_local_registration_proof"
    preview = report["operator_command_preview"]
    assert preview["required_env"] == {
        "OWNER_APPROVED_RUNTIME_LOCAL_REGISTRATION_PREP": (
            "auth-rtf017:attempt-local-registration:no-exchange-submit"
        )
    }
    assert preview["command"] == [
        "python",
        "scripts/runtime_first_real_submit_api_flow.py",
        "--mode",
        "arm",
        "--authorization-id",
        "auth-rtf017",
        "--record-attempt-consumption",
        "--skip-exchange-arm",
        "--api-base",
        "http://unit",
        "--env-file",
        ".env.unit",
    ]


def test_missing_machine_evidence_blocks_boundary(tmp_path):
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(
        json.dumps(
            {
                "status": "prepared_machine_evidence_blocked_before_local_order_adapter",
                "fresh_submit_authorization_id": "auth-rtf017",
                "ids": {
                    "trusted_submit_fact_snapshot_id": "facts-rtf017",
                },
            }
        ),
        encoding="utf-8",
    )

    report = script._build_report(
        _args(
            tmp_path,
            evidence_path=evidence_path,
            source_kind="scoped_local_registration_proof",
            allow_scoped_local_registration_proof=True,
        )
    )

    assert report["status"] == "blocked_required_machine_evidence_missing"
    assert "submit_idempotency_policy_id_missing" in report["blockers"]
    assert "protection_creation_failure_policy_id_missing" in report["blockers"]


def _write_evidence(tmp_path):
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(
        json.dumps(
            {
                "status": "prepared_machine_evidence_blocked_before_local_order_adapter",
                "fresh_submit_authorization_id": "auth-rtf017",
                "ids": {
                    "trusted_submit_fact_snapshot_id": "facts-rtf017",
                    "submit_idempotency_policy_id": "idem-rtf017",
                    "protection_creation_failure_policy_id": "protect-rtf017",
                    "post_submit_budget_settlement_persistence_evidence_id": (
                        "settlement-rtf017"
                    ),
                },
                "warnings": [
                    (
                        "disabled_first_real_submit_action_prerequisite_missing:"
                        "RuntimeExecutionOrderLifecycleAdapterResult not found"
                    )
                ],
            }
        ),
        encoding="utf-8",
    )
    return evidence_path


def _args(tmp_path, *, evidence_path, **overrides):
    values = {
        "evidence_chain_json": str(evidence_path),
        "source_kind": "sample_rehearsal",
        "allow_scoped_local_registration_proof": False,
        "api_base": None,
        "env_file": None,
        "output": None,
    }
    values.update(overrides)
    return type("Args", (), values)()
