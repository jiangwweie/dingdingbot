from __future__ import annotations

import json
import sys

from scripts import runtime_cycle_executable_submit_handoff


def _strategy_plan():
    return {
        "packet_id": "strategy-plan-1",
        "runtime_instance_id": "runtime-1",
        "source_authorization_id": "consumed-auth-1",
        "post_submit_finalize_packet_id": "post-submit-1",
        "status": "ready_for_final_gate_preflight",
        "next_attempt_gate_status": "ready_for_fresh_signal",
        "signal_evaluation_id": "signal-eval-1",
        "strategy_family_id": "BTPC-001",
        "strategy_family_version_id": "BTPC-001-v0",
        "symbol": "AVAX/USDT:USDT",
        "order_candidate_id": "order-candidate-1",
        "blockers": [],
        "warnings": [],
        "operator_command_plan": {},
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


def _cycle_packet(*, status="ready_for_final_gate_preflight"):
    return {
        "scope": "runtime_post_submit_next_attempt_cycle",
        "status": status,
        "runtime_instance_id": "runtime-1",
        "next_attempt_strategy_plan_flow": {
            "status": status,
            "api_payload": _strategy_plan(),
            "blockers": [] if status == "ready_for_final_gate_preflight" else ["wait"],
        },
        "blockers": [] if status == "ready_for_final_gate_preflight" else ["wait"],
        "warnings": [],
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


def _readiness_flow():
    return {
        "scope": "runtime_executable_submit_readiness_api_flow",
        "status": "ready_for_executable_submit",
        "api_payload": {
            "packet_id": "readiness-1",
            "runtime_instance_id": "runtime-1",
            "source_strategy_planning_packet_id": "strategy-plan-1",
            "source_authorization_id": "consumed-auth-1",
            "status": "ready_for_executable_submit",
            "blockers": [],
            "warnings": [],
            "executable_submit_ready": True,
        },
        "blockers": [],
        "warnings": ["ready"],
    }


def _handoff_flow():
    return {
        "scope": "runtime_official_submit_handoff_api_flow",
        "status": "ready_for_official_submit_call",
        "api_payload": {
            "status": "ready_for_official_submit_call",
            "ready_for_official_submit_call": True,
        },
        "operator_action_preview": {
            "ready_for_call": True,
            "mode": "disabled_smoke",
        },
        "blockers": [],
        "warnings": ["handoff"],
    }


def _write_inputs(tmp_path, *, cycle_status="ready_for_final_gate_preflight"):
    cycle_path = tmp_path / "cycle.json"
    evidence_path = tmp_path / "evidence.json"
    cycle_path.write_text(json.dumps(_cycle_packet(status=cycle_status)), encoding="utf-8")
    evidence_path.write_text(json.dumps(_evidence()), encoding="utf-8")
    return cycle_path, evidence_path


def _args(tmp_path, **overrides):
    cycle_path, evidence_path = _write_inputs(
        tmp_path,
        cycle_status=overrides.pop("cycle_status", "ready_for_final_gate_preflight"),
    )
    values = {
        "runtime_instance_id": "runtime-1",
        "cycle_packet_json": str(cycle_path),
        "evidence_json": str(evidence_path),
        "first_real_submit_packet_json": None,
        "fresh_submit_authorization_id": None,
        "mode": "disabled_smoke",
        "owner_confirmed_for_real_submit_action": False,
        "readiness_warning": None,
        "readiness_blocker": None,
        "handoff_warning": None,
        "handoff_blocker": None,
        "env_file": None,
        "api_base": "http://unit",
        "output_dir": str(tmp_path / "out"),
        "flow_id": "flow-1",
    }
    values.update(overrides)
    return type("Args", (), values)()


def test_blocks_before_readiness_when_cycle_not_ready(tmp_path):
    calls = []

    packet = runtime_cycle_executable_submit_handoff._build_packet(
        _args(tmp_path, cycle_status="waiting_for_signal"),
        readiness_builder=lambda args: calls.append(args),
        handoff_builder=lambda args: calls.append(args),
    )

    assert packet["status"] == "blocked"
    assert packet["blocked_stage"] == "post_submit_next_attempt_cycle"
    assert calls == []
    assert packet["safety_invariants"]["exchange_write_called"] is False


def test_ready_for_fresh_authorization_after_readiness_ready(tmp_path):
    readiness_calls = []
    handoff_calls = []

    def readiness_builder(args):
        readiness_calls.append(args)
        return _readiness_flow()

    packet = runtime_cycle_executable_submit_handoff._build_packet(
        _args(tmp_path),
        readiness_builder=readiness_builder,
        handoff_builder=lambda args: handoff_calls.append(args),
    )

    assert packet["status"] == "ready_for_fresh_submit_authorization"
    assert len(readiness_calls) == 1
    assert handoff_calls == []
    strategy_path = packet["artifact_paths"]["strategy_planning_packet"]
    assert json.loads(open(strategy_path, encoding="utf-8").read())["packet_id"] == "strategy-plan-1"
    assert packet["operator_command_plan"]["requires_fresh_submit_authorization"] is True


def test_calls_handoff_preview_when_fresh_authorization_present(tmp_path):
    packet = runtime_cycle_executable_submit_handoff._build_packet(
        _args(tmp_path, fresh_submit_authorization_id="fresh-auth-1"),
        readiness_builder=lambda args: _readiness_flow(),
        handoff_builder=lambda args: _handoff_flow(),
    )

    assert packet["status"] == "ready_for_official_submit_call"
    assert packet["operator_action_preview"]["ready_for_call"] is True
    assert packet["operator_command_plan"]["calls_official_submit_endpoint"] is False
    assert packet["operator_command_plan"]["requires_owner_chat_confirmation"] is False
    assert packet["operator_command_plan"]["uses_standing_runtime_authorization"] is True
    assert packet["operator_command_plan"]["requires_action_time_final_gate"] is True
    assert packet["operator_command_plan"]["requires_official_operation_layer"] is True
    assert packet["operator_command_plan"]["can_continue_without_owner_chat"] is True
    assert packet["operator_command_plan"]["requires_action_time_confirmation"] is False
    assert packet["safety_invariants"]["order_lifecycle_called"] is False


def test_blocks_when_readiness_blocks(tmp_path):
    def blocked_readiness(args):
        return {
            "status": "blocked",
            "blockers": ["final_gate_not_passed"],
            "warnings": [],
            "api_payload": {"status": "blocked"},
        }

    packet = runtime_cycle_executable_submit_handoff._build_packet(
        _args(tmp_path),
        readiness_builder=blocked_readiness,
        handoff_builder=lambda args: _handoff_flow(),
    )

    assert packet["status"] == "blocked"
    assert packet["blocked_stage"] == "executable_submit_readiness"
    assert "final_gate_not_passed" in packet["blockers"]


def test_cycle_to_handoff_cli_stdout_is_json_only(monkeypatch, capsys):
    def fake_build_packet(args):
        print("inner noisy handoff bridge")
        return {"status": "ready_for_fresh_submit_authorization", "ok": True}

    monkeypatch.setattr(
        runtime_cycle_executable_submit_handoff,
        "_build_packet",
        fake_build_packet,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runtime_cycle_executable_submit_handoff.py",
            "--runtime-instance-id",
            "runtime-1",
            "--cycle-packet-json",
            "cycle.json",
            "--evidence-json",
            "evidence.json",
        ],
    )

    assert runtime_cycle_executable_submit_handoff.main() == 0

    captured = capsys.readouterr()
    assert captured.out.startswith("{")
    assert "inner noisy handoff bridge" not in captured.out
    assert "inner noisy handoff bridge" in captured.err
