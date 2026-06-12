from __future__ import annotations

import json

from scripts.runtime_first_real_submit_api_flow import (
    LOCAL_REGISTRATION_APPROVAL_ENV,
)
from scripts import runtime_scoped_local_registration_proof_from_evidence as script


def test_sample_rehearsal_dry_run_stays_blocked_without_api_calls(tmp_path):
    evidence_path = _write_evidence(tmp_path)
    client = _Client()

    report = script._build_report(
        _args(
            tmp_path,
            evidence_path=evidence_path,
            source_kind="sample_rehearsal",
        ),
        client=client,
    )

    assert report["status"] == "blocked_scoped_local_registration_proof_dry_run"
    assert "sample_rehearsal_execute_not_allowed" in report["blockers"]
    assert client.calls == []
    assert report["safety_invariants"]["local_registration_attempted"] is False
    assert report["safety_invariants"]["exchange_write_called"] is False


def test_execute_blocks_when_local_registration_env_confirmation_missing(tmp_path):
    evidence_path = _write_evidence(tmp_path)
    client = _Client()

    report = script._build_report(
        _args(
            tmp_path,
            evidence_path=evidence_path,
            source_kind="scoped_local_registration_proof",
            allow_scoped_local_registration_proof=True,
            execute_scoped_local_registration_proof=True,
        ),
        client=client,
    )

    assert report["status"] == "blocked_local_registration_env_confirmation_missing"
    assert (
        "owner_runtime_local_registration_env_confirmation_missing"
        in report["blockers"]
    )
    paths = [call["path"] for call in client.calls]
    assert any("runtime-execution-first-real-submit-evidence-preparations" in path for path in paths)
    assert not any("runtime-execution-order-lifecycle-adapter-results" in path for path in paths)
    assert not any("runtime-execution-exchange-submit" in path for path in paths)


def test_execute_records_scoped_local_registration_without_exchange(tmp_path, monkeypatch):
    evidence_path = _write_evidence(tmp_path)
    monkeypatch.setenv(
        LOCAL_REGISTRATION_APPROVAL_ENV,
        "auth-rtf018:attempt-local-registration:no-exchange-submit",
    )
    client = _Client()

    report = script._build_report(
        _args(
            tmp_path,
            evidence_path=evidence_path,
            source_kind="scoped_local_registration_proof",
            allow_scoped_local_registration_proof=True,
            execute_scoped_local_registration_proof=True,
        ),
        client=client,
    )

    assert report["status"] == "scoped_local_registration_proof_recorded"
    assert report["local_registration_adapter_result_id"] == "local-result-rtf018"
    assert report["safety_invariants"]["local_registration_recorded"] is True
    assert report["safety_invariants"]["exchange_arm_enabled"] is False
    assert report["safety_invariants"]["exchange_write_called"] is False
    paths = [call["path"] for call in client.calls]
    assert any("runtime-execution-order-lifecycle-adapter-results" in path for path in paths)
    assert not any("runtime-execution-exchange-submit" in path for path in paths)
    assert not any("runtime-execution-first-real-submit-actions" in path for path in paths)


class _Client:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def request_json(self, method, path, *, query=None, body=None):
        self.calls.append(
            {
                "method": method,
                "path": path,
                "query": dict(query or {}),
                "body": body,
            }
        )
        if "runtime-execution-controlled-submit-plans" in path:
            return {
                "http_status": 200,
                "body": {
                    "execution_intent_id": "intent-rtf018",
                    "runtime_execution_intent_draft_id": "draft-rtf018",
                    "source_id": "candidate-rtf018",
                    "semantic_ids": {
                        "order_candidate_id": "candidate-rtf018",
                        "runtime_instance_id": "runtime-rtf018",
                        "signal_evaluation_id": "signal-rtf018",
                    },
                    "status": "ready_for_controlled_submit_adapter",
                },
            }
        if "runtime-execution-protection-plans" in path:
            return {
                "http_status": 200,
                "body": {
                    "protection_plan_id": "protection-plan-rtf018",
                    "status": "ready_for_submit_adapter",
                },
            }
        if "runtime-execution-first-real-submit-evidence-preparations" in path:
            return {
                "http_status": 200,
                "body": {
                    "status": "prepared_packet_blocked",
                    "available_evidence_ids": {
                        "trusted_submit_fact_snapshot_id": "facts-rtf018",
                        "submit_idempotency_policy_id": "idem-rtf018",
                        "protection_creation_failure_policy_id": (
                            "protect-rtf018"
                        ),
                    },
                    "blockers": [
                        "first_real_submit_packet_unavailable:"
                        "runtimeexecutionorderlifecycleadapterresult_not_found"
                    ],
                },
            }
        if "runtime-execution-attempt-reservations" in path:
            return {
                "http_status": 200,
                "body": {
                    "reservation_id": "reservation-rtf018",
                    "status": "pending_runtime_mutation",
                },
            }
        if "runtime-execution-attempt-mutations" in path:
            return {
                "http_status": 200,
                "body": {
                    "mutation_id": "mutation-rtf018",
                    "status": "applied",
                },
            }
        if "runtime-execution-attempt-outcome-policies" in path:
            return {
                "http_status": 200,
                "body": {
                    "policy_id": "policy-rtf018",
                    "status": "ready_for_attempt_budget_outcome_accounting",
                },
            }
        if "runtime-execution-order-lifecycle-handoff-drafts" in path:
            return {
                "http_status": 200,
                "body": {
                    "handoff_draft_id": "handoff-rtf018",
                    "status": "ready_for_order_lifecycle_adapter",
                    "blockers": [],
                },
            }
        if "runtime-execution-local-registration-action-authorizations" in path:
            return {
                "http_status": 200,
                "body": {
                    "action_authorization_id": "local-action-rtf018",
                    "status": "approved_for_local_registration_action",
                },
            }
        if "runtime-execution-local-registration-enablements" in path:
            return {
                "http_status": 200,
                "body": {
                    "decision_id": "local-enable-rtf018",
                    "status": "ready_for_local_registration_action",
                },
            }
        if "runtime-execution-order-lifecycle-adapter-results" in path:
            return {
                "http_status": 200,
                "body": {
                    "adapter_result_id": "local-result-rtf018",
                    "status": "registered_created_local_orders",
                },
            }
        raise AssertionError(f"unexpected path {path}")


def _write_evidence(tmp_path):
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(
        json.dumps(
            {
                "status": "prepared_machine_evidence_blocked_before_local_order_adapter",
                "fresh_submit_authorization_id": "auth-rtf018",
                "ids": {
                    "trusted_submit_fact_snapshot_id": "facts-rtf018",
                    "submit_idempotency_policy_id": "idem-rtf018",
                    "protection_creation_failure_policy_id": "protect-rtf018",
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
        "source_kind": "current_live_signal",
        "allow_scoped_local_registration_proof": False,
        "allow_sample_local_registration": False,
        "execute_scoped_local_registration_proof": False,
        "api_base": "http://unit",
        "env_file": None,
        "owner_operator_id": "owner",
        "owner_confirmation_reference": "owner-authorized-rtf018",
        "reason": "owner authorized scoped local registration proof",
        "outcome_kind": "entry_filled_protection_creation_failed",
        "skip_next_attempt_gate_check": True,
        "output": None,
    }
    values.update(overrides)
    return type("Args", (), values)()
