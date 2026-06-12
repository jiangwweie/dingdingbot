from __future__ import annotations

import json

from scripts import runtime_real_signal_scoped_local_registration_pipeline as script


def test_pipeline_blocks_at_strategy_signal_source_without_rehearsal_fallback(tmp_path):
    client = _Client(source_status="blocked")

    report = script._build_report(
        _args(tmp_path),
        client=client,
    )

    assert report["status"] == "blocked_at_strategy_signal_intent_draft_source"
    assert report["blocked_stage"] == "strategy_signal_intent_draft_source"
    assert report["stage_statuses"] == {"intent_draft_source": "blocked"}
    assert "intent_draft_source:strategy_signal_not_would_enter" in report["blockers"]
    assert report["safety_invariants"]["sample_rehearsal_used"] is False
    assert report["safety_invariants"]["exchange_write_called"] is False
    assert [call["path"] for call in client.calls] == [
        (
            "/api/trading-console/strategy-runtimes/runtime-rtf020/"
            "strategy-signal-intent-draft-sources"
        )
    ]


def test_pipeline_reaches_scoped_local_registration_dry_run_from_real_signal(tmp_path):
    client = _Client()

    report = script._build_report(
        _args(tmp_path, readiness_evidence_json=str(_write_evidence(tmp_path))),
        client=client,
    )

    assert report["status"] == "ready_for_real_signal_scoped_local_registration_proof"
    assert report["blocked_stage"] is None
    assert report["stage_statuses"] == {
        "intent_draft_source": "persisted_ready_intent_draft",
        "readiness": "ready_for_executable_submit",
        "handoff": "ready_for_official_submit_call",
        "binding": "created_intent_and_authorization",
        "evidence_chain": "prepared_machine_evidence_blocked_before_local_order_adapter",
        "scoped_local_registration_proof": (
            "ready_for_scoped_local_registration_proof_dry_run"
        ),
    }
    assert report["safety_invariants"]["sample_rehearsal_used"] is False
    assert report["safety_invariants"]["local_registration_attempted"] is False
    assert report["safety_invariants"]["first_real_submit_action_called"] is False
    assert report["safety_invariants"]["exchange_write_called"] is False
    paths = [call["path"] for call in client.calls]
    assert any("strategy-signal-intent-draft-sources" in path for path in paths)
    assert any("persisted-draft-source-readiness-previews" in path for path in paths)
    assert any("official-submit-handoff-previews" in path for path in paths)
    assert any("fresh-authorizations/bind" in path for path in paths)
    assert any("runtime-execution-first-real-submit-actions" in path for path in paths)
    assert any("runtime-execution-first-real-submit-evidence-preparations" in path for path in paths)
    assert not any("runtime-execution-order-lifecycle-adapter-results" in path for path in paths)
    assert not any("runtime-execution-exchange-submit" in path for path in paths)


class _Client:
    def __init__(self, *, source_status: str = "persisted_ready_intent_draft") -> None:
        self.source_status = source_status
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
        if "strategy-signal-intent-draft-sources" in path:
            if self.source_status == "blocked":
                return {
                    "http_status": 200,
                    "body": {
                        "status": "blocked",
                        "blockers": ["strategy_signal_not_would_enter"],
                        "warnings": [],
                        "signal_evaluation_created": False,
                        "order_candidate_created": False,
                        "runtime_execution_intent_draft_created": False,
                    },
                }
            return {
                "http_status": 200,
                "body": {
                    "status": "persisted_ready_intent_draft",
                    "blockers": [],
                    "warnings": ["unit-source"],
                    "signal_evaluation_id": "signal-rtf020",
                    "order_candidate_id": "candidate-rtf020",
                    "runtime_execution_intent_draft_id": "draft-rtf020",
                    "draft_status": "ready_for_intent_creation",
                    "ready_for_official_handoff_source": True,
                    "signal_evaluation_created": True,
                    "order_candidate_created": True,
                    "runtime_execution_intent_draft_created": True,
                },
            }
        if "persisted-draft-source-readiness-previews" in path:
            return {
                "http_status": 200,
                "body": {
                    "status": "ready_for_executable_submit",
                    "packet_id": "readiness-rtf020",
                    "source_strategy_planning_packet_id": "strategy-plan-rtf020",
                    "source_authorization_id": "persisted-draft-source:rtf020",
                    "signal_evaluation_id": "signal-rtf020",
                    "order_candidate_id": "candidate-rtf020",
                    "executable_submit_ready": True,
                    "blockers": [],
                    "warnings": ["unit-readiness"],
                },
            }
        if "official-submit-handoff-previews" in path:
            return {
                "http_status": 200,
                "body": {
                    "status": "ready_for_official_submit_call",
                    "blockers": [],
                    "warnings": ["unit-handoff"],
                    "ready_for_official_submit_call": True,
                    "official_endpoint_method": "POST",
                    "official_endpoint_path": (
                        "/api/trading-console/"
                        "runtime-execution-first-real-submit-actions/"
                        "authorizations/requested-fresh-submit-authorization-rtf020"
                    ),
                    "official_query": {
                        "owner_confirmed_for_first_real_submit_action": False,
                    },
                    "mode": "disabled_smoke",
                },
            }
        if "fresh-authorizations/bind" in path:
            return {
                "http_status": 200,
                "body": {
                    "status": "created_intent_and_authorization",
                    "blockers": [],
                    "warnings": ["unit-binding"],
                    "fresh_submit_authorization_id": "auth-rtf020",
                    "execution_intent_id": "intent-rtf020",
                    "runtime_execution_intent_draft_id": "draft-rtf020",
                    "ready_for_fresh_authorization_resolution": True,
                    "ready_for_disabled_smoke_call": True,
                    "binding_source": "latest_ready_draft",
                    "creates_execution_intent": True,
                    "creates_submit_authorization": True,
                },
            }
        if "runtime-execution-first-real-submit-actions" in path:
            return {
                "http_status": 404,
                "body": {
                    "message": "RuntimeExecutionOrderLifecycleAdapterResult not found",
                },
                "error": True,
            }
        if "runtime-execution-first-real-submit-evidence-preparations" in path:
            return {
                "http_status": 200,
                "body": {
                    "status": "prepared_packet_blocked",
                    "available_evidence_ids": {
                        "trusted_submit_fact_snapshot_id": "facts-rtf020",
                        "submit_idempotency_policy_id": "idem-rtf020",
                        "protection_creation_failure_policy_id": "protect-rtf020",
                        "post_submit_budget_settlement_persistence_evidence_id": (
                            "settlement-rtf020"
                        ),
                    },
                    "blockers": [
                        "first_real_submit_packet_unavailable:"
                        "runtimeexecutionorderlifecycleadapterresult_not_found"
                    ],
                },
            }
        raise AssertionError(f"unexpected path {path}")


def _write_signal(tmp_path):
    path = tmp_path / "signal.json"
    path.write_text(
        json.dumps(
            {
                "evaluation_id": "signal-rtf020",
                "strategy_family_id": "BTPC-001",
                "strategy_family_version_id": "BTPC-001-v0",
                "symbol": "AVAX/USDT:USDT",
            }
        ),
        encoding="utf-8",
    )
    return path


def _write_evidence(tmp_path):
    path = tmp_path / "readiness-evidence.json"
    path.write_text(
        json.dumps(
            {
                "final_gate_preview_id": "final-gate-rtf020",
                "final_gate_passed": True,
                "runtime_grant_authorization_id": "runtime-grant-rtf020",
                "trusted_submit_fact_snapshot_id": "facts-rtf020",
                "submit_idempotency_policy_id": "idem-rtf020",
                "attempt_outcome_policy_id": "attempt-policy-rtf020",
                "protection_creation_failure_policy_id": "protect-rtf020",
                "local_registration_enablement_decision_id": "local-enable-rtf020",
                "exchange_submit_enablement_decision_id": "exchange-enable-rtf020",
                "exchange_submit_action_authorization_id": "exchange-action-rtf020",
                "order_lifecycle_submit_enablement_id": "ol-enable-rtf020",
                "exchange_submit_adapter_enablement_id": "exchange-adapter-rtf020",
                "deployment_readiness_evidence_id": "deploy-ready-rtf020",
                "protection_required_and_ready": True,
                "active_position_source_trusted": True,
                "account_facts_fresh": True,
                "duplicate_submit_guard_ready": True,
            }
        ),
        encoding="utf-8",
    )
    return path


def _args(tmp_path, **overrides):
    values = {
        "runtime_instance_id": "runtime-rtf020",
        "signal_input_json": str(_write_signal(tmp_path)),
        "readiness_evidence_json": None,
        "candidate_id": "BTPC-001",
        "context_id": "context-rtf020",
        "expires_at_ms": None,
        "active_positions_count": 0,
        "metadata_json": None,
        "execute_scoped_local_registration_proof": False,
        "owner_operator_id": "owner",
        "owner_confirmation_reference": "owner-authorized-rtf020",
        "reason": "owner authorized real signal scoped local registration proof",
        "outcome_kind": "entry_filled_protection_creation_failed",
        "skip_next_attempt_gate_check": True,
        "env_file": None,
        "api_base": "http://unit",
        "artifact_dir": str(tmp_path / "artifacts"),
        "output": None,
    }
    values.update(overrides)
    return type("Args", (), values)()
