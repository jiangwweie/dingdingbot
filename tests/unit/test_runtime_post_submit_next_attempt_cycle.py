from __future__ import annotations

import json
import sys

from scripts import runtime_post_submit_next_attempt_cycle


def _args(tmp_path, **overrides):
    signal_path = tmp_path / "signal-input.json"
    signal_path.write_text(
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
    values = {
        "runtime_instance_id": "runtime-1",
        "reservation_id": "reservation-1",
        "signal_input_json": str(signal_path),
        "authorization_id": None,
        "closed_review_required": False,
        "protection_blocker": None,
        "env_file": None,
        "api_base": "http://unit",
        "context_id": "context-1",
        "expires_at_ms": None,
        "metadata_json": '{"owner":"unit"}',
        "output_dir": str(tmp_path / "cycle-output"),
        "cycle_id": "cycle-1",
    }
    values.update(overrides)
    return type("Args", (), values)()


def _ready_finalize_packet():
    return {
        "scope": "runtime_post_submit_finalize_api_flow",
        "status": "finalized_ready_for_next_attempt",
        "runtime_instance_id": "runtime-1",
        "authorization_id": "auth-1",
        "post_submit_finalize_packet": {
            "packet_id": "post-submit-1",
            "authorization_id": "auth-1",
            "runtime_instance_id": "runtime-1",
            "status": "finalized_ready_for_next_attempt",
            "next_attempt_gate": {
                "status": "ready_for_fresh_signal",
                "runtime_instance_id": "runtime-1",
                "blockers": [],
                "warnings": [],
            },
            "blockers": [],
            "warnings": [],
        },
        "blockers": [],
        "warnings": [],
    }


def _waiting_plan_packet():
    return {
        "scope": "runtime_next_attempt_strategy_plan_api_flow",
        "status": "waiting_for_signal",
        "api_payload": {
            "status": "waiting_for_signal",
            "signal_evaluation_id": "eval-1",
            "order_candidate_id": None,
        },
        "blockers": ["strategy_signal_not_would_enter"],
        "warnings": [],
    }


def _ready_plan_packet():
    return {
        "scope": "runtime_next_attempt_strategy_plan_api_flow",
        "status": "ready_for_final_gate_preflight",
        "api_payload": {
            "status": "ready_for_final_gate_preflight",
            "signal_evaluation_id": "eval-ready",
            "order_candidate_id": "order-candidate-ready",
            "operator_command_plan": {"creates_shadow_candidate": True},
        },
        "blockers": [],
        "warnings": [],
    }


def test_cycle_waits_when_post_submit_ready_but_signal_observe_only(tmp_path):
    finalize_calls = []
    planning_calls = []

    def planning_builder(args):
        planning_calls.append(args)
        return _waiting_plan_packet()

    packet = runtime_post_submit_next_attempt_cycle._build_cycle_packet(
        _args(tmp_path, reservation_id=None),
        finalize_builder=lambda args: (
            finalize_calls.append(args) or _ready_finalize_packet()
        ),
        planning_builder=planning_builder,
    )

    assert packet["status"] == "waiting_for_signal"
    assert packet["signal_evaluation_id"] == "eval-1"
    assert packet["order_candidate_id"] is None
    assert packet["operator_command_plan"]["creates_shadow_candidate"] is False
    assert packet["operator_command_plan"]["requires_fresh_authorization_before_submit"] is True
    assert packet["safety_invariants"]["exchange_write_called"] is False
    assert packet["safety_invariants"]["order_lifecycle_called"] is False
    assert finalize_calls[0].reservation_id is None
    assert len(planning_calls) == 1
    post_packet_path = packet["artifact_paths"]["post_submit_finalize_packet"]
    assert json.loads(open(post_packet_path, encoding="utf-8").read())["packet_id"] == "post-submit-1"


def test_cycle_blocks_before_planning_when_post_submit_not_ready(tmp_path):
    planning_calls = []

    def blocked_finalize(args):
        return {
            "status": "blocked",
            "blockers": ["runtime_active_position_slot_in_use"],
            "warnings": [],
        }

    packet = runtime_post_submit_next_attempt_cycle._build_cycle_packet(
        _args(tmp_path),
        finalize_builder=blocked_finalize,
        planning_builder=lambda args: planning_calls.append(args),
    )

    assert packet["status"] == "blocked"
    assert packet["blocked_stage"] == "post_submit_finalize"
    assert "runtime_active_position_slot_in_use" in packet["blockers"]
    assert planning_calls == []
    assert packet["operator_command_plan"]["creates_shadow_candidate"] is False


def test_cycle_reaches_final_gate_preflight_when_strategy_planning_ready(tmp_path):
    packet = runtime_post_submit_next_attempt_cycle._build_cycle_packet(
        _args(tmp_path),
        finalize_builder=lambda args: _ready_finalize_packet(),
        planning_builder=lambda args: _ready_plan_packet(),
    )

    assert packet["status"] == "ready_for_final_gate_preflight"
    assert packet["signal_evaluation_id"] == "eval-ready"
    assert packet["order_candidate_id"] == "order-candidate-ready"
    assert packet["operator_command_plan"]["creates_shadow_candidate"] is True
    assert packet["operator_command_plan"]["requires_official_final_gate"] is True
    assert packet["operator_command_plan"]["places_order"] is False


def test_cycle_cli_stdout_is_json_only(monkeypatch, capsys):
    def fake_build_cycle_packet(args):
        print("inner noisy cycle")
        return {"status": "waiting_for_signal", "ok": True}

    monkeypatch.setattr(
        runtime_post_submit_next_attempt_cycle,
        "_build_cycle_packet",
        fake_build_cycle_packet,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runtime_post_submit_next_attempt_cycle.py",
            "--runtime-instance-id",
            "runtime-1",
            "--signal-input-json",
            "signal.json",
        ],
    )

    assert runtime_post_submit_next_attempt_cycle.main() == 0

    captured = capsys.readouterr()
    assert captured.out.startswith("{")
    assert "inner noisy cycle" not in captured.out
    assert "inner noisy cycle" in captured.err
