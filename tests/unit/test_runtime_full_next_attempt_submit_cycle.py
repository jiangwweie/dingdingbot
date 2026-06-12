from __future__ import annotations

import json
import sys

from scripts import runtime_full_next_attempt_submit_cycle


def _signal_path(tmp_path):
    path = tmp_path / "signal.json"
    path.write_text(
        json.dumps(
            {
                "evaluation_id": "eval-1",
                "strategy_family_id": "BTPC-001",
                "strategy_family_version_id": "BTPC-001-v0",
                "symbol": "AVAX/USDT:USDT",
            }
        ),
        encoding="utf-8",
    )
    return path


def _evidence_path(tmp_path):
    path = tmp_path / "evidence.json"
    path.write_text(
        json.dumps(
            {
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
        ),
        encoding="utf-8",
    )
    return path


def _args(tmp_path, **overrides):
    values = {
        "runtime_instance_id": "runtime-1",
        "reservation_id": "reservation-1",
        "signal_input_json": str(_signal_path(tmp_path)),
        "cycle_packet_json": None,
        "authorization_id": None,
        "closed_review_required": False,
        "protection_blocker": None,
        "evidence_json": str(_evidence_path(tmp_path)),
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
        "cycle_id": "cycle-1",
    }
    values.update(overrides)
    return type("Args", (), values)()


def _cycle_packet(status: str):
    return {
        "scope": "runtime_post_submit_next_attempt_cycle",
        "status": status,
        "blocked_stage": None if status == "ready_for_final_gate_preflight" else "strategy_signal",
        "runtime_instance_id": "runtime-1",
        "next_attempt_strategy_plan_flow": {
            "status": status,
            "api_payload": {
                "packet_id": "strategy-plan-1",
                "runtime_instance_id": "runtime-1",
                "status": status,
                "order_candidate_id": (
                    "order-candidate-1"
                    if status == "ready_for_final_gate_preflight"
                    else None
                ),
            },
        },
        "blockers": [] if status == "ready_for_final_gate_preflight" else ["strategy_signal_not_would_enter"],
        "warnings": [],
    }


def _handoff_packet(status: str):
    return {
        "scope": "runtime_cycle_executable_submit_handoff",
        "status": status,
        "blocked_stage": None,
        "blockers": [],
        "warnings": ["handoff"],
        "operator_command_plan": {
            "calls_official_submit_endpoint": False,
        },
    }


def test_full_cycle_waits_without_running_readiness_when_signal_not_ready(tmp_path):
    handoff_calls = []

    packet = runtime_full_next_attempt_submit_cycle._build_packet(
        _args(tmp_path),
        cycle_builder=lambda args: _cycle_packet("waiting_for_signal"),
        handoff_bridge_builder=lambda args: handoff_calls.append(args),
    )

    assert packet["status"] == "waiting_for_signal"
    assert packet["blocked_stage"] == "strategy_signal"
    assert handoff_calls == []
    assert packet["operator_command_plan"]["runs_executable_readiness"] is False
    assert packet["safety_invariants"]["exchange_write_called"] is False


def test_full_cycle_stops_at_final_gate_preflight_when_evidence_missing(tmp_path):
    packet = runtime_full_next_attempt_submit_cycle._build_packet(
        _args(tmp_path, evidence_json=None),
        cycle_builder=lambda args: _cycle_packet("ready_for_final_gate_preflight"),
        handoff_bridge_builder=lambda args: _handoff_packet("ready_for_official_submit_call"),
    )

    assert packet["status"] == "ready_for_final_gate_preflight"
    assert "executable_readiness_evidence_json_missing" in packet["warnings"]
    assert packet["operator_command_plan"]["runs_executable_readiness"] is False


def test_full_cycle_runs_handoff_bridge_when_cycle_ready_and_evidence_present(tmp_path):
    packet = runtime_full_next_attempt_submit_cycle._build_packet(
        _args(tmp_path, fresh_submit_authorization_id="fresh-auth-1"),
        cycle_builder=lambda args: _cycle_packet("ready_for_final_gate_preflight"),
        handoff_bridge_builder=lambda args: _handoff_packet("ready_for_official_submit_call"),
    )

    assert packet["status"] == "ready_for_official_submit_call"
    assert packet["operator_command_plan"]["runs_executable_readiness"] is True
    assert packet["operator_command_plan"]["calls_official_submit_endpoint"] is False
    assert packet["operator_command_plan"]["requires_action_time_confirmation"] is True
    assert packet["safety_invariants"]["order_lifecycle_called"] is False


def test_full_cycle_can_resume_from_existing_cycle_artifact(tmp_path):
    cycle_path = tmp_path / "existing-cycle.json"
    cycle_path.write_text(
        json.dumps(_cycle_packet("waiting_for_signal")),
        encoding="utf-8",
    )
    calls = []

    packet = runtime_full_next_attempt_submit_cycle._build_packet(
        _args(tmp_path, cycle_packet_json=str(cycle_path)),
        cycle_builder=lambda args: calls.append(args),
        handoff_bridge_builder=lambda args: calls.append(args),
    )

    assert packet["status"] == "waiting_for_signal"
    assert calls == []
    assert packet["operator_command_plan"]["runs_executable_readiness"] is False


def test_full_cycle_returns_ready_for_fresh_authorization_from_bridge(tmp_path):
    packet = runtime_full_next_attempt_submit_cycle._build_packet(
        _args(tmp_path),
        cycle_builder=lambda args: _cycle_packet("ready_for_final_gate_preflight"),
        handoff_bridge_builder=lambda args: _handoff_packet(
            "ready_for_fresh_submit_authorization"
        ),
    )

    assert packet["status"] == "ready_for_fresh_submit_authorization"
    assert packet["operator_command_plan"]["next_step"] == (
        "bind_or_resolve_fresh_submit_authorization"
    )


def test_full_cycle_cli_stdout_is_json_only(monkeypatch, capsys):
    def fake_build_packet(args):
        print("inner noisy full cycle")
        return {"status": "waiting_for_signal", "ok": True}

    monkeypatch.setattr(
        runtime_full_next_attempt_submit_cycle,
        "_build_packet",
        fake_build_packet,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runtime_full_next_attempt_submit_cycle.py",
            "--runtime-instance-id",
            "runtime-1",
            "--signal-input-json",
            "signal.json",
        ],
    )

    assert runtime_full_next_attempt_submit_cycle.main() == 0

    captured = capsys.readouterr()
    assert captured.out.startswith("{")
    assert "inner noisy full cycle" not in captured.out
    assert "inner noisy full cycle" in captured.err
