from __future__ import annotations

import json
import sys

import pytest

from scripts import runtime_executable_submit_readiness_api_flow


class _Client:
    def __init__(self, *, http_status: int = 200, body: dict | None = None) -> None:
        self.http_status = http_status
        self.body = body or {
            "status": "ready_for_executable_submit",
            "blockers": [],
            "warnings": ["unit"],
            "executable_submit_ready": True,
        }
        self.calls: list[dict] = []

    def request_json(self, method, path, *, query=None, body=None):
        self.calls.append(
            {
                "method": method,
                "path": path,
                "query": query,
                "body": body,
            }
        )
        return {"http_status": self.http_status, "body": self.body}


def _strategy_artifact():
    return {
        "artifact_id": "strategy-plan-1",
        "runtime_instance_id": "runtime-1",
        "source_authorization_id": "consumed-auth-1",
        "post_submit_finalize_payload_id": "post-submit-1",
        "source_release_evidence_id": "release-1",
        "status": "ready_for_final_gate_preflight",
        "next_attempt_gate_status": "ready_for_fresh_signal",
        "signal_evaluation_id": "signal-eval-1",
        "strategy_family_id": "CPM-001",
        "strategy_family_version_id": "CPM-001-v0",
        "symbol": "BNB/USDT:USDT",
        "order_candidate_id": "order-candidate-1",
        "blockers": [],
        "warnings": [],
        "strategy_planning_plan": {},
        "consumed_authorization_replay_only": True,
        "requires_fresh_strategy_signal": True,
        "requires_fresh_authorization_before_submit": True,
        "old_authorization_submit_retry_allowed": False,
        "pre_submit_rehearsal_retry_allowed": False,
        "execution_intent_created": False,
        "executable_execution_intent_created": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "exchange_called": False,
        "exchange_order_submitted": False,
        "runtime_state_mutated": False,
        "withdrawal_or_transfer_created": False,
        "metadata": {},
    }


def _evidence():
    return {
        "final_gate_preview_id": "final-gate-preview-1",
        "final_gate_passed": True,
        "runtime_grant_authorization_id": "runtime-grant-1",
        "trusted_submit_fact_snapshot_id": "trusted-facts-1",
        "submit_idempotency_policy_id": "idem-1",
        "attempt_outcome_policy_id": "attempt-policy-1",
        "protection_creation_failure_policy_id": "protection-failure-1",
        "local_registration_enablement_decision_id": "local-enable-1",
        "exchange_submit_enablement_decision_id": "exchange-enable-1",
        "exchange_submit_action_authorization_id": "exchange-action-auth-1",
        "order_lifecycle_submit_enablement_id": "ol-submit-enable-1",
        "exchange_submit_adapter_enablement_id": "exchange-adapter-enable-1",
        "deployment_readiness_evidence_id": "deploy-ready-1",
        "protection_required_and_ready": True,
        "active_position_source_trusted": True,
        "account_facts_fresh": True,
        "duplicate_submit_guard_ready": True,
    }


def _write_inputs(tmp_path):
    strategy_path = tmp_path / "strategy.json"
    evidence_path = tmp_path / "evidence.json"
    strategy_path.write_text(json.dumps(_strategy_artifact()), encoding="utf-8")
    evidence_path.write_text(json.dumps(_evidence()), encoding="utf-8")
    return strategy_path, evidence_path


def _args(tmp_path, **overrides):
    strategy_path, evidence_path = _write_inputs(tmp_path)
    values = {
        "runtime_instance_id": "runtime-1",
        "strategy_planning_artifact_json": str(strategy_path),
        "evidence_json": str(evidence_path),
        "first_real_submit_evidence_json": None,
        "additional_warning": None,
        "additional_blocker": None,
        "env_file": None,
        "api_base": "http://unit",
    }
    values.update(overrides)
    return type("Args", (), values)()


def test_executable_submit_readiness_api_flow_posts_readiness_request(tmp_path):
    client = _Client()

    packet = runtime_executable_submit_readiness_api_flow._build_artifact(
        _args(tmp_path),
        client=client,
    )

    assert packet["status"] == "ready_for_executable_submit"
    assert packet["safety_invariants"]["order_lifecycle_called"] is False
    assert packet["safety_invariants"]["exchange_write_called"] is False
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["method"] == "POST"
    assert call["path"] == (
        "/api/trading-console/strategy-runtimes/runtime-1/"
        "executable-submit-readiness-previews"
    )
    assert call["body"]["strategy_planning_artifact"]["artifact_id"] == "strategy-plan-1"
    assert "strategy_planning_packet" not in call["body"]
    assert call["body"]["evidence"]["final_gate_preview_id"] == "final-gate-preview-1"
    assert call["body"]["metadata"][
        "runtime_executable_submit_readiness_api_flow"
    ] is True
    assert call["body"]["non_executing"] is True


def test_executable_submit_readiness_api_flow_keeps_http_errors(tmp_path):
    packet = runtime_executable_submit_readiness_api_flow._build_artifact(
        _args(tmp_path),
        client=_Client(http_status=400, body={"detail": "bad"}),
    )

    assert packet["status"] == "blocked"
    assert packet["blocked_stage"] == "executable_submit_readiness_api"
    assert "executable_submit_readiness_api_http_400" in packet["blockers"]
    assert packet["safety_invariants"]["execution_intent_created"] is False


def test_executable_submit_readiness_api_flow_cli_stdout_is_json_only(
    monkeypatch,
    capsys,
):
    def fake_build_artifact(args):
        print("inner noisy readiness api flow")
        return {"status": "blocked", "ok": True}

    monkeypatch.setattr(
        runtime_executable_submit_readiness_api_flow,
        "_build_artifact",
        fake_build_artifact,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runtime_executable_submit_readiness_api_flow.py",
            "--runtime-instance-id",
            "runtime-1",
            "--strategy-planning-artifact-json",
            "strategy.json",
            "--evidence-json",
            "evidence.json",
        ],
    )

    assert runtime_executable_submit_readiness_api_flow.main() == 0

    captured = capsys.readouterr()
    assert captured.out.startswith("{")
    assert "inner noisy readiness api flow" not in captured.out
    assert "inner noisy readiness api flow" in captured.err


def test_executable_submit_readiness_api_flow_rejects_legacy_packet_cli_alias(
    monkeypatch,
    capsys,
):
    def fake_build_artifact(args):
        return {"status": "blocked", "ok": True}

    monkeypatch.setattr(
        runtime_executable_submit_readiness_api_flow,
        "_build_artifact",
        fake_build_artifact,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runtime_executable_submit_readiness_api_flow.py",
            "--runtime-instance-id",
            "runtime-1",
            "--strategy-planning-packet-json",
            "strategy.json",
            "--evidence-json",
            "evidence.json",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        runtime_executable_submit_readiness_api_flow.main()

    captured = capsys.readouterr()
    assert exc.value.code == 2
    assert captured.out == ""
