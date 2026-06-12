from __future__ import annotations

import json

from scripts import runtime_current_persisted_source_disabled_smoke_pipeline as script


def test_current_persisted_source_pipeline_reaches_disabled_smoke(tmp_path):
    client = _Client()

    report = script._build_report(
        _args(tmp_path, readiness_evidence_json=str(_write_evidence(tmp_path))),
        client=client,
    )

    assert report["status"] == "ready_current_persisted_source_disabled_smoke"
    assert report["blocked_stage"] is None
    assert report["stage_statuses"] == {
        "intent_draft_source": "persisted_ready_intent_draft",
        "readiness": "ready_for_executable_submit",
        "initial_handoff": "blocked",
        "binding": "created_intent_and_authorization",
        "final_handoff": "ready_for_official_submit_call",
        "disabled_smoke": "disabled_smoke_passed",
    }
    assert report["fresh_submit_authorization_id"] == "auth-rtf061"
    assert report["safety_invariants"]["uses_current_runtime_persisted_source"] is True
    assert report["safety_invariants"]["uses_historical_rtf015_sample_handoff"] is False
    assert report["safety_invariants"]["signal_evaluation_created"] is True
    assert report["safety_invariants"]["order_candidate_created"] is True
    assert report["safety_invariants"]["runtime_execution_intent_draft_created"] is True
    assert report["safety_invariants"]["execution_intent_created"] is True
    assert report["safety_invariants"]["submit_authorization_created"] is True
    assert report["safety_invariants"]["calls_official_submit_endpoint"] is True
    assert report["safety_invariants"]["requests_real_gateway_action"] is False
    assert report["safety_invariants"]["exchange_submit_execution_enabled"] is False
    assert report["safety_invariants"]["exchange_write_called"] is False
    assert report["safety_invariants"]["order_created"] is False
    assert report["safety_invariants"]["order_lifecycle_called"] is False

    paths = [call["path"] for call in client.calls]
    assert any("strategy-signal-intent-draft-sources" in path for path in paths)
    assert any("persisted-draft-source-readiness-previews" in path for path in paths)
    assert any("fresh-authorizations/bind" in path for path in paths)
    assert any(
        "runtime-execution-first-real-submit-actions/authorizations/auth-rtf061"
        in path
        for path in paths
    )
    assert not any("rtf015" in json.dumps(call).lower() for call in client.calls)


def test_final_handoff_uses_fresh_authorization_not_consumed_source(tmp_path):
    client = _Client()

    report = script._build_report(
        _args(tmp_path, readiness_evidence_json=str(_write_evidence(tmp_path))),
        client=client,
    )

    final_packet = report["reports"]["final_handoff"]["packet"]
    assert final_packet["fresh_submit_authorization_id"] == "auth-rtf061"
    assert final_packet["source_consumed_authorization_id"] == (
        "persisted-draft-source:rtf061"
    )
    assert final_packet["fresh_submit_authorization_id"] != (
        final_packet["source_consumed_authorization_id"]
    )
    assert final_packet["official_query"][
        "owner_confirmed_for_first_real_submit_action"
    ] is False


def test_pipeline_blocks_before_readiness_when_trusted_facts_missing(tmp_path):
    client = _Client()

    report = script._build_report(
        _args(tmp_path, auto_readiness_evidence=True),
        client=client,
    )

    assert report["status"] == "blocked_at_readiness_evidence_resolution"
    assert report["blocked_stage"] == "readiness_evidence_resolution"
    assert report["stage_statuses"] == {
        "intent_draft_source": "persisted_ready_intent_draft",
        "readiness_evidence_resolution": "blocked_readiness_evidence_unresolved",
    }
    assert "readiness_evidence_resolution:final_gate_preview_id_missing" in (
        report["blockers"]
    )
    paths = [call["path"] for call in client.calls]
    assert any("strategy-signal-intent-draft-sources" in path for path in paths)
    assert not any("persisted-draft-source-readiness-previews" in path for path in paths)
    assert not any("runtime-execution-first-real-submit-actions" in path for path in paths)


def test_current_persisted_source_pipeline_writes_artifacts_and_output(tmp_path):
    client = _Client()
    output = tmp_path / "report.json"

    report = script._build_report(
        _args(
            tmp_path,
            readiness_evidence_json=str(_write_evidence(tmp_path)),
            output=str(output),
        ),
        client=client,
    )

    assert output.exists()
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["status"] == "ready_current_persisted_source_disabled_smoke"
    artifact_root = tmp_path / "artifacts"
    assert (artifact_root / "01-intent-draft-source.json").exists()
    assert (artifact_root / "03-readiness.json").exists()
    assert (artifact_root / "04-initial-handoff-needs-fresh-auth.json").exists()
    assert (artifact_root / "05-binding.json").exists()
    assert (artifact_root / "06-final-handoff.json").exists()
    assert (artifact_root / "07-disabled-smoke.json").exists()
    assert report["blockers"] == []


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
        if "strategy-signal-intent-draft-sources" in path:
            return {
                "http_status": 200,
                "body": {
                    "status": "persisted_ready_intent_draft",
                    "runtime_instance_id": "runtime-rtf061",
                    "blockers": [],
                    "warnings": ["unit-source"],
                    "signal_evaluation_id": "signal-rtf061",
                    "order_candidate_id": "candidate-rtf061",
                    "runtime_execution_intent_draft_id": "draft-rtf061",
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
                "body": _readiness_body(),
            }
        if "official-submit-handoff-fresh-authorizations/bind" in path:
            return {
                "http_status": 200,
                "body": {
                    "status": "created_intent_and_authorization",
                    "blockers": [],
                    "warnings": ["unit-binding"],
                    "fresh_submit_authorization_id": "auth-rtf061",
                    "execution_intent_id": "intent-rtf061",
                    "runtime_execution_intent_draft_id": "draft-rtf061",
                    "ready_for_fresh_authorization_resolution": True,
                    "ready_for_disabled_smoke_call": True,
                    "binding_source": "latest_ready_draft",
                    "creates_execution_intent": True,
                    "creates_submit_authorization": True,
                },
            }
        if "runtime-execution-first-real-submit-actions/authorizations/auth-rtf061" in path:
            return {
                "http_status": 200,
                "body": {
                    "status": "exchange_submit_execution_disabled",
                    "exchange_submit_execution_enabled": False,
                    "exchange_submit_execution_mode": "disabled",
                    "execution_result_id": "disabled-smoke-rtf061",
                },
            }
        raise AssertionError(f"unexpected path {path}")


def _readiness_body():
    return {
        "packet_id": "readiness-rtf061",
        "runtime_instance_id": "runtime-rtf061",
        "source_release_packet_id": None,
        "source_strategy_planning_packet_id": "strategy-plan-rtf061",
        "source_authorization_id": "persisted-draft-source:rtf061",
        "signal_evaluation_id": "signal-rtf061",
        "order_candidate_id": "candidate-rtf061",
        "strategy_planning_status": "ready_for_final_gate_preflight",
        "status": "ready_for_executable_submit",
        "evidence": _evidence_payload(),
        "blockers": [],
        "warnings": ["unit-readiness"],
        "executable_submit_ready": True,
        "requires_official_order_lifecycle_path": True,
        "requires_current_final_gate_pass": True,
        "requires_fresh_strategy_candidate": True,
        "legacy_pre_attempt_rehearsal_required": False,
        "consumed_authorization_replay_only": True,
        "not_exchange_submit_execution": True,
        "not_order_lifecycle_authority": True,
        "execution_intent_created": False,
        "executable_execution_intent_created": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "exchange_called": False,
        "exchange_order_submitted": False,
        "runtime_state_mutated": False,
        "withdrawal_or_transfer_created": False,
        "created_at_ms": 1781300000000,
        "metadata": {"unit": True},
    }


def _write_evidence(tmp_path):
    return _write_json(tmp_path, "evidence.json", _evidence_payload())


def _evidence_payload():
    return {
        "final_gate_preview_id": "final-gate-rtf061",
        "final_gate_passed": True,
        "runtime_grant_authorization_id": "grant-rtf061",
        "owner_real_submit_authorization_id": None,
        "trusted_submit_fact_snapshot_id": "facts-rtf061",
        "submit_idempotency_policy_id": "idem-rtf061",
        "attempt_outcome_policy_id": "attempt-rtf061",
        "protection_creation_failure_policy_id": "protect-rtf061",
        "local_registration_enablement_decision_id": "local-enable-rtf061",
        "exchange_submit_enablement_decision_id": "exchange-enable-rtf061",
        "exchange_submit_action_authorization_id": "exchange-action-rtf061",
        "order_lifecycle_submit_enablement_id": "ol-enable-rtf061",
        "exchange_submit_adapter_enablement_id": "adapter-enable-rtf061",
        "deployment_readiness_evidence_id": "deploy-rtf061",
        "protection_required_and_ready": True,
        "active_position_source_trusted": True,
        "account_facts_fresh": True,
        "duplicate_submit_guard_ready": True,
        "legacy_runtime_submit_rehearsal_id": None,
        "durable_exchange_submit_execution_result_id": None,
    }


def _write_json(tmp_path, name, payload):
    path = tmp_path / name
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _write_signal(tmp_path):
    return _write_json(
        tmp_path,
        "signal.json",
        {
            "evaluation_id": "signal-rtf061",
            "strategy_family_id": "BTPC-001",
            "strategy_family_version_id": "BTPC-001-v0",
            "symbol": "AVAX/USDT:USDT",
            "side": "short",
        },
    )


def _args(tmp_path, **overrides):
    values = {
        "runtime_instance_id": "runtime-rtf061",
        "signal_input_json": str(_write_signal(tmp_path)),
        "readiness_evidence_json": None,
        "auto_readiness_evidence": False,
        "final_gate_preview_id": None,
        "final_gate_passed": False,
        "runtime_grant_authorization_id": "grant-rtf061",
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
        "requested_fresh_submit_authorization_id": None,
        "candidate_id": "candidate-rtf061",
        "context_id": "context-rtf061",
        "expires_at_ms": None,
        "active_positions_count": 0,
        "metadata_json": None,
        "env_file": None,
        "api_base": "http://fixture",
        "artifact_dir": str(tmp_path / "artifacts"),
        "output": None,
    }
    values.update(overrides)
    return type("Args", (), values)()
