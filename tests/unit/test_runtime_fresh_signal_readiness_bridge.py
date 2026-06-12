from __future__ import annotations

import json
import sys

from scripts import runtime_fresh_signal_readiness_bridge


def _strategy_plan():
    return {
        "packet_id": "strategy-plan-rtf057",
        "runtime_instance_id": "runtime-1",
        "source_authorization_id": "post-submit-auth-1",
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


def _planning_flow(status="ready_for_final_gate_preflight"):
    return {
        "scope": "runtime_next_attempt_strategy_plan_api_flow",
        "status": status,
        "api_payload": _strategy_plan()
        if status == "ready_for_final_gate_preflight"
        else {"status": status, "blockers": ["planning_blocked"]},
        "blockers": [] if status == "ready_for_final_gate_preflight" else ["planning_blocked"],
        "warnings": ["planning"],
    }


def _handoff_flow():
    return {
        "scope": "runtime_cycle_executable_submit_handoff",
        "status": "ready_for_fresh_submit_authorization",
        "runtime_instance_id": "runtime-1",
        "blockers": [],
        "warnings": ["handoff"],
        "operator_command_plan": {
            "requires_fresh_submit_authorization": True,
            "places_order": False,
            "calls_order_lifecycle": False,
        },
    }


def _post_submit_packet():
    return {
        "packet_id": "post-submit-1",
        "authorization_id": "consumed-auth-1",
        "runtime_instance_id": "runtime-1",
        "status": "finalized_ready_for_next_attempt",
        "next_attempt_gate": {
            "status": "ready_for_fresh_signal",
            "runtime_instance_id": "runtime-1",
            "attempts_remaining": 2,
            "budget_remaining": "30",
            "active_positions_count": 0,
            "blockers": [],
            "warnings": [],
        },
        "blockers": [],
        "warnings": [],
    }


def _write_evidence(tmp_path):
    evidence = {
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
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")
    return path


def _write_fresh_loop(tmp_path, *, status, with_signal=True):
    signal_path = tmp_path / "signal.json"
    if with_signal:
        signal_path.write_text(
            json.dumps(
                {
                    "evaluation_id": "signal-eval-1",
                    "strategy_family_id": "BTPC-001",
                    "strategy_family_version_id": "BTPC-001-v0",
                    "symbol": "AVAX/USDT:USDT",
                    "timestamp_ms": 1781000000000,
                }
            ),
            encoding="utf-8",
        )
    packet = {
        "scope": "runtime_fresh_signal_prepare_loop",
        "status": status,
        "runtime_instance_id": "runtime-1",
        "post_submit_finalize_flow": {
            "status": "finalized_ready_for_next_attempt",
            "post_submit_finalize_packet": _post_submit_packet(),
        },
        "observation_prepare_flow": {
            "status": status,
            "signal_input_json": str(signal_path),
        },
        "signal_input_json": str(signal_path),
        "blockers": []
        if status != "waiting_for_signal"
        else ["strategy_signal_not_ready_for_shadow_candidate_prepare"],
        "warnings": ["fresh-loop"],
        "safety_invariants": {
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
        },
    }
    path = tmp_path / "fresh-loop.json"
    path.write_text(json.dumps(packet), encoding="utf-8")
    return path


def _args(tmp_path, **overrides):
    fresh_loop_path = overrides.pop("fresh_loop_path", None)
    if fresh_loop_path is None:
        fresh_loop_path = _write_fresh_loop(tmp_path, status="ready_for_prepare")
    values = {
        "runtime_instance_id": "runtime-1",
        "fresh_signal_loop_json": str(fresh_loop_path),
        "evidence_json": str(_write_evidence(tmp_path)),
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
        "context_id": "context-1",
        "expires_at_ms": None,
        "metadata_json": '{"owner":"unit"}',
        "output_dir": str(tmp_path / "out"),
        "flow_id": "flow-1",
    }
    values.update(overrides)
    return type("Args", (), values)()


def test_fresh_signal_readiness_bridge_waits_without_strategy_planning(tmp_path):
    fresh_loop_path = _write_fresh_loop(tmp_path, status="waiting_for_signal")
    planning_calls = []
    handoff_calls = []

    packet = runtime_fresh_signal_readiness_bridge._build_packet(
        _args(tmp_path, fresh_loop_path=fresh_loop_path, evidence_json=None),
        planning_builder=lambda args: planning_calls.append(args),
        handoff_builder=lambda args: handoff_calls.append(args),
    )

    assert packet["status"] == "waiting_for_signal"
    assert packet["blockers"] == [
        "strategy_signal_not_ready_for_shadow_candidate_prepare"
    ]
    assert planning_calls == []
    assert handoff_calls == []
    assert packet["safety_invariants"]["exchange_write_called"] is False


def test_fresh_signal_readiness_bridge_requires_evidence_before_planning(tmp_path):
    fresh_loop_path = _write_fresh_loop(tmp_path, status="ready_for_prepare")
    planning_calls = []

    packet = runtime_fresh_signal_readiness_bridge._build_packet(
        _args(tmp_path, fresh_loop_path=fresh_loop_path, evidence_json=None),
        planning_builder=lambda args: planning_calls.append(args),
        handoff_builder=lambda args: _handoff_flow(),
    )

    assert packet["status"] == "ready_for_readiness_evidence"
    assert packet["operator_command_plan"]["next_step"] == (
        "provide_readiness_evidence_json"
    )
    assert planning_calls == []
    assert packet["safety_invariants"]["order_lifecycle_called"] is False


def test_fresh_signal_readiness_bridge_runs_planning_then_handoff(tmp_path):
    fresh_loop_path = _write_fresh_loop(
        tmp_path,
        status="ready_for_final_gate_preflight",
    )
    planning_calls = []
    handoff_calls = []

    def planning_builder(args):
        planning_calls.append(args)
        return _planning_flow()

    def handoff_builder(args):
        handoff_calls.append(args)
        cycle = json.loads(open(args.cycle_packet_json, encoding="utf-8").read())
        assert cycle["status"] == "ready_for_final_gate_preflight"
        assert cycle["next_attempt_strategy_plan_flow"]["api_payload"]["packet_id"] == (
            "strategy-plan-rtf057"
        )
        return _handoff_flow()

    packet = runtime_fresh_signal_readiness_bridge._build_packet(
        _args(tmp_path, fresh_loop_path=fresh_loop_path),
        planning_builder=planning_builder,
        handoff_builder=handoff_builder,
    )

    assert packet["status"] == "ready_for_fresh_submit_authorization"
    assert len(planning_calls) == 1
    assert len(handoff_calls) == 1
    assert packet["next_attempt_strategy_plan_flow"]["status"] == (
        "ready_for_final_gate_preflight"
    )
    assert packet["operator_command_plan"]["places_order"] is False
    assert packet["safety_invariants"]["order_created"] is False


def test_fresh_signal_readiness_bridge_blocks_when_planning_blocks(tmp_path):
    fresh_loop_path = _write_fresh_loop(tmp_path, status="ready_for_prepare")
    handoff_calls = []

    packet = runtime_fresh_signal_readiness_bridge._build_packet(
        _args(tmp_path, fresh_loop_path=fresh_loop_path),
        planning_builder=lambda args: _planning_flow(status="blocked"),
        handoff_builder=lambda args: handoff_calls.append(args),
    )

    assert packet["status"] == "blocked"
    assert packet["blocked_stage"] == "next_attempt_strategy_planning"
    assert "planning_blocked" in packet["blockers"]
    assert handoff_calls == []


def test_fresh_signal_readiness_bridge_cli_stdout_is_json_only(monkeypatch, capsys):
    def fake_build_packet(args):
        print("inner noisy readiness bridge")
        return {"status": "waiting_for_signal", "ok": True}

    monkeypatch.setattr(
        runtime_fresh_signal_readiness_bridge,
        "_build_packet",
        fake_build_packet,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runtime_fresh_signal_readiness_bridge.py",
            "--runtime-instance-id",
            "runtime-1",
            "--fresh-signal-loop-json",
            "fresh-loop.json",
        ],
    )

    assert runtime_fresh_signal_readiness_bridge.main() == 0

    captured = capsys.readouterr()
    assert captured.out.startswith("{")
    assert "inner noisy readiness bridge" not in captured.out
    assert "inner noisy readiness bridge" in captured.err
