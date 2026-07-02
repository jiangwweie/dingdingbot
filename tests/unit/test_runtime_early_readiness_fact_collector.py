from __future__ import annotations

import json

from scripts import runtime_early_readiness_fact_collector as script


def test_collector_blocks_when_required_early_facts_are_missing(tmp_path):
    report = script._build_report(_args(tmp_path))

    assert report["status"] == "blocked_early_readiness_facts_incomplete"
    assert report["evidence"] is None
    assert "final_gate_preview_id_missing" in report["blockers"]
    assert (
        "runtime_grant_or_owner_real_submit_authorization_id_missing"
        in report["blockers"]
    )
    assert "trusted_submit_fact_snapshot_id_missing" in report["blockers"]
    assert report["safety_invariants"]["does_not_call_exchange"] is True
    assert report["safety_invariants"]["does_not_invent_missing_facts"] is True


def test_collector_extracts_partial_facts_without_claiming_ready(tmp_path):
    report = script._build_report(
        _args(
            tmp_path,
            runtime_grant_authorization_id="grant-rtf024",
            final_gate_preview_json=str(_write_final_gate(tmp_path)),
            trusted_submit_facts_json=str(_write_trusted_facts(tmp_path)),
        )
    )

    assert report["status"] == "blocked_early_readiness_facts_incomplete"
    assert "final_gate_preview_id_missing" not in report["blockers"]
    assert "trusted_submit_fact_snapshot_id_missing" not in report["blockers"]
    assert "account_facts_fresh_missing" not in report["blockers"]
    assert "submit_idempotency_policy_id_missing" in report["blockers"]
    assert report["evidence"] is None


def test_collector_records_legacy_packet_wrapper_without_collecting_facts(tmp_path):
    report = script._build_report(
        _args(
            tmp_path,
            runtime_grant_authorization_id="grant-rtf024",
            final_gate_preview_json=str(
                _write_json(
                    tmp_path,
                    "final-gate-legacy-wrapper.json",
                    {
                        "packet": {
                            "final_gate_preview_id": "fg-legacy-wrapper",
                            "verdict": "PASS",
                            "candidate_snapshot": {
                                "protection_reference_present": True,
                            },
                        },
                    },
                )
            ),
        )
    )

    assert "final_gate_preview_id_missing" in report["blockers"]
    assert "final_gate_preview_json" not in report["collected_source_kinds"]
    assert report["source_wrapper_provenance"] == [
        {
            "source_kind": "final_gate_preview_json",
            "wrapper": "packet",
            "legacy_wrapper": True,
        }
    ]
    assert (
        "legacy_source_wrapper_used:final_gate_preview_json:packet"
        in report["warnings"]
    )


def test_collector_does_not_unwrap_legacy_decision_source_boundary(tmp_path):
    report = script._build_report(
        _args(
            tmp_path,
            runtime_grant_authorization_id="grant-rtf024",
            final_gate_preview_json=str(
                _write_json(
                    tmp_path,
                    "final-gate-decision-wrapper.json",
                    {
                        "decision": {
                            "final_gate_preview_id": "fg-decision-wrapper",
                            "verdict": "PASS",
                        },
                    },
                )
            ),
        )
    )

    assert "final_gate_preview_id_missing" in report["blockers"]
    assert report["source_wrapper_provenance"] == []


def test_collector_does_not_use_legacy_packet_id_as_final_gate_preview_id(tmp_path):
    report = script._build_report(
        _args(
            tmp_path,
            runtime_grant_authorization_id="grant-rtf024",
            final_gate_preview_json=str(
                _write_json(
                    tmp_path,
                    "final-gate-packet-id-only.json",
                    {
                        "packet_id": "legacy-finalgate-packet-id",
                        "verdict": "PASS",
                        "candidate_snapshot": {
                            "protection_reference_present": True,
                        },
                    },
                )
            ),
        )
    )

    assert "final_gate_preview_id_missing" in report["blockers"]
    assert report["evidence"] is None


def test_collector_writes_readiness_evidence_when_reports_are_complete(tmp_path):
    report = script._build_report(
        _args(
            tmp_path,
            runtime_grant_authorization_id="grant-rtf024",
            final_gate_preview_json=str(_write_final_gate(tmp_path)),
            trusted_submit_facts_json=str(_write_trusted_facts(tmp_path)),
            submit_idempotency_json=str(_write_idempotency(tmp_path)),
            attempt_outcome_policy_json=str(
                _write_json(tmp_path, "attempt.json", {"policy_id": "attempt-rtf024"})
            ),
            protection_failure_policy_json=str(
                _write_json(tmp_path, "protection.json", {"policy_id": "protect-rtf024"})
            ),
            local_registration_enablement_json=str(
                _write_json(
                    tmp_path,
                    "local-enable.json",
                    {
                        "status": "ready_for_local_registration_action",
                        "decision_id": "local-enable-rtf024",
                    },
                )
            ),
            exchange_submit_enablement_json=str(
                _write_json(
                    tmp_path,
                    "exchange-enable.json",
                    {
                        "status": "ready_for_exchange_submit_action",
                        "decision_id": "exchange-enable-rtf024",
                    },
                )
            ),
            exchange_action_authorization_json=str(
                _write_json(
                    tmp_path,
                    "exchange-action.json",
                    {"authorization_id": "exchange-action-rtf024"},
                )
            ),
            order_lifecycle_submit_enablement_json=str(
                _write_json(
                    tmp_path,
                    "ol-enable.json",
                    {"enablement_id": "ol-enable-rtf024"},
                )
            ),
            exchange_adapter_enablement_json=str(
                _write_json(
                    tmp_path,
                    "adapter-enable.json",
                    {"enablement_id": "adapter-enable-rtf024"},
                )
            ),
            deployment_readiness_json=str(
                _write_json(
                    tmp_path,
                    "deploy.json",
                    {
                        "status": "ready_for_manual_gateway_binding",
                        "readiness_id": "deploy-rtf024",
                    },
                )
            ),
        )
    )

    assert report["status"] == "ready_for_readiness_evidence_resolution"
    assert report["blockers"] == []
    assert report["evidence"]["final_gate_preview_id"] == "fg-rtf024"
    assert report["evidence"]["trusted_submit_fact_snapshot_id"] == "facts-rtf024"
    assert report["evidence"]["duplicate_submit_guard_ready"] is True
    assert report["evidence_json_path"]
    written = json.loads(
        (tmp_path / "artifacts" / "02-collected-readiness-evidence.json").read_text(
            encoding="utf-8"
        )
    )
    assert written["exchange_submit_adapter_enablement_id"] == "adapter-enable-rtf024"
    assert written["deployment_readiness_evidence_id"] == "deploy-rtf024"


def _write_final_gate(tmp_path):
    return _write_json(
        tmp_path,
        "final-gate.json",
        {
            "final_gate_preview_id": "fg-rtf024",
            "verdict": "PASS",
            "candidate_snapshot": {"protection_reference_present": True},
        },
    )


def _write_trusted_facts(tmp_path):
    source = {"trusted": True, "freshness": "fresh"}
    return _write_json(
        tmp_path,
        "trusted-facts.json",
        {
            "status": "ready_for_first_real_submit_confirmation",
            "trusted_submit_fact_snapshot_id": "facts-rtf024",
            "facts_fresh_enough": True,
            "account_fact_source": source,
            "active_position_source": source,
            "protection_state_source": source,
        },
    )


def _write_idempotency(tmp_path):
    return _write_json(
        tmp_path,
        "idempotency.json",
        {
            "status": "ready_for_non_executing_policy_confirmation",
            "submit_idempotency_policy_id": "idem-rtf024",
            "blocks_concurrent_submit_without_lock": True,
            "replay_existing_result_on_duplicate": True,
        },
    )


def _write_json(tmp_path, name, payload):
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _args(tmp_path, **overrides):
    values = {
        "runtime_instance_id": "runtime-rtf024",
        "runtime_grant_authorization_id": None,
        "owner_real_submit_authorization_id": None,
        "final_gate_preview_json": None,
        "trusted_submit_facts_json": None,
        "submit_idempotency_json": None,
        "attempt_outcome_policy_json": None,
        "protection_failure_policy_json": None,
        "local_registration_enablement_json": None,
        "exchange_submit_enablement_json": None,
        "exchange_action_authorization_json": None,
        "order_lifecycle_submit_enablement_json": None,
        "exchange_adapter_enablement_json": None,
        "deployment_readiness_json": None,
        "legacy_runtime_submit_rehearsal_id": None,
        "durable_exchange_submit_execution_result_id": None,
        "artifact_dir": str(tmp_path / "artifacts"),
        "output": None,
    }
    values.update(overrides)
    return type("Args", (), values)()
