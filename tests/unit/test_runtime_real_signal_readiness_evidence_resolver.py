from __future__ import annotations

import json

from scripts import runtime_real_signal_readiness_evidence_resolver as script


def test_resolver_blocks_missing_trusted_evidence(tmp_path):
    report = script._build_report(
        _args(tmp_path, intent_draft_source_json=str(_write_ready_source(tmp_path)))
    )

    assert report["status"] == "blocked_readiness_evidence_unresolved"
    assert report["evidence"] is None
    assert report["evidence_json_path"] is None
    assert "final_gate_preview_id_missing" in report["blockers"]
    assert (
        "runtime_grant_or_owner_real_submit_authorization_id_missing"
        in report["blockers"]
    )
    assert "trusted_submit_fact_snapshot_id_missing" in report["blockers"]
    assert "final_gate_passed_missing" in report["blockers"]
    assert report["safety_invariants"]["does_not_call_exchange"] is True
    assert report["safety_invariants"]["does_not_invent_trusted_facts"] is True


def test_resolver_writes_evidence_when_explicit_trusted_facts_are_complete(tmp_path):
    report = script._build_report(
        _args(
            tmp_path,
            intent_draft_source_json=str(_write_ready_source(tmp_path)),
            **_complete_evidence(),
        )
    )

    assert report["status"] == "ready_for_readiness_evidence"
    assert report["blockers"] == []
    assert report["evidence"]["final_gate_preview_id"] == "final-gate-rtf022"
    assert report["evidence"]["runtime_grant_authorization_id"] == "grant-rtf022"
    assert report["evidence_json_path"]
    written = json.loads(
        (tmp_path / "artifacts" / "02-auto-readiness-evidence.json").read_text(
            encoding="utf-8"
        )
    )
    assert written["trusted_submit_fact_snapshot_id"] == "facts-rtf022"
    assert written["duplicate_submit_guard_ready"] is True


def test_resolver_blocks_source_that_is_not_ready(tmp_path):
    source = _write_ready_source(tmp_path, status="blocked")

    report = script._build_report(
        _args(
            tmp_path,
            intent_draft_source_json=str(source),
            **_complete_evidence(),
        )
    )

    assert report["status"] == "blocked_readiness_evidence_unresolved"
    assert "intent_draft_source_not_ready_for_readiness_evidence" in report["blockers"]
    assert report["evidence"] is None


def _write_ready_source(tmp_path, *, status="persisted_ready_intent_draft"):
    path = tmp_path / f"source-{status}.json"
    path.write_text(
        json.dumps(
            {
                "status": status,
                "packet_id": f"source-{status}",
                "runtime_instance_id": "runtime-rtf022",
                "signal_evaluation_id": "signal-rtf022",
                "order_candidate_id": "candidate-rtf022",
                "runtime_execution_intent_draft_id": "draft-rtf022",
                "ready_for_official_handoff_source": (
                    status == "persisted_ready_intent_draft"
                ),
            }
        ),
        encoding="utf-8",
    )
    return path


def _complete_evidence():
    return {
        "final_gate_preview_id": "final-gate-rtf022",
        "final_gate_passed": True,
        "runtime_grant_authorization_id": "grant-rtf022",
        "trusted_submit_fact_snapshot_id": "facts-rtf022",
        "submit_idempotency_policy_id": "idem-rtf022",
        "attempt_outcome_policy_id": "attempt-rtf022",
        "protection_creation_failure_policy_id": "protect-rtf022",
        "local_registration_enablement_decision_id": "local-rtf022",
        "exchange_submit_enablement_decision_id": "exchange-enable-rtf022",
        "exchange_submit_action_authorization_id": "exchange-action-rtf022",
        "order_lifecycle_submit_enablement_id": "ol-rtf022",
        "exchange_submit_adapter_enablement_id": "adapter-rtf022",
        "deployment_readiness_evidence_id": "deploy-rtf022",
        "protection_required_and_ready": True,
        "active_position_source_trusted": True,
        "account_facts_fresh": True,
        "duplicate_submit_guard_ready": True,
    }


def _args(tmp_path, **overrides):
    values = {
        "runtime_instance_id": "runtime-rtf022",
        "intent_draft_source_json": str(tmp_path / "missing-source.json"),
        "artifact_dir": str(tmp_path / "artifacts"),
        "output": None,
        "final_gate_preview_id": None,
        "final_gate_passed": False,
        "runtime_grant_authorization_id": None,
        "owner_real_submit_authorization_id": None,
        "trusted_submit_fact_snapshot_id": None,
        "submit_idempotency_policy_id": None,
        "attempt_outcome_policy_id": None,
        "protection_creation_failure_policy_id": None,
        "local_registration_enablement_decision_id": None,
        "exchange_submit_enablement_decision_id": None,
        "exchange_submit_action_authorization_id": None,
        "order_lifecycle_submit_enablement_id": None,
        "exchange_submit_adapter_enablement_id": None,
        "deployment_readiness_evidence_id": None,
        "protection_required_and_ready": False,
        "active_position_source_trusted": False,
        "account_facts_fresh": False,
        "duplicate_submit_guard_ready": False,
        "legacy_runtime_submit_rehearsal_id": None,
        "durable_exchange_submit_execution_result_id": None,
    }
    values.update(overrides)
    return type("Args", (), values)()
