from __future__ import annotations

import json
import sys

from scripts import runtime_fresh_signal_prepare_loop


def _args(tmp_path, **overrides):
    values = {
        "runtime_instance_id": "runtime-1",
        "authorization_id": None,
        "reservation_id": None,
        "closed_review_required": False,
        "protection_blocker": None,
        "env_file": None,
        "api_base": "http://unit",
        "metadata_json": '{"owner":"unit"}',
        "source": "sample",
        "include_exchange": False,
        "symbol": None,
        "side": None,
        "family": None,
        "strategy_family_id": None,
        "carrier_id": None,
        "quantity": None,
        "target_notional_usdt": None,
        "max_notional": None,
        "leverage": None,
        "max_attempts": None,
        "protection_mode": None,
        "review_requirement": None,
        "evaluation_id": None,
        "playbook_id": None,
        "one_hour_limit": 25,
        "four_hour_limit": 25,
        "timeout_seconds": 10.0,
        "allow_prepare_records": False,
        "candidate_id": None,
        "context_id": "context-1",
        "owner_operator_id": "owner",
        "owner_confirmation_reference": "owner-authorized-unit",
        "reason": "unit fresh signal prepare loop",
        "next_attempt_symbol": None,
        "next_attempt_side": None,
        "next_attempt_family": None,
        "next_attempt_strategy_family_id": None,
        "next_attempt_carrier_id": None,
        "output_dir": str(tmp_path / "out"),
        "cycle_id": "cycle-1",
    }
    values.update(overrides)
    return type("Args", (), values)()


def _ready_post_submit():
    return {
        "scope": "runtime_post_submit_finalize_api_flow",
        "status": "finalized_ready_for_next_attempt",
        "authorization_id": "auth-1",
        "blockers": [],
        "warnings": ["post-submit"],
        "safety_invariants": {
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "attempt_counter_mutated_by_script": False,
            "runtime_budget_mutated_by_script": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _waiting_observation():
    return {
        "scope": "runtime_next_attempt_observation_api_prepare_flow",
        "status": "waiting_for_signal",
        "signal_input_json": "/tmp/signal.json",
        "blockers": ["strategy_signal_not_ready_for_shadow_candidate_prepare"],
        "warnings": ["observe"],
        "operator_command_plan": {
            "creates_shadow_candidate": False,
        },
        "safety_invariants": {
            "allow_prepare_records": False,
            "prepare_records_created": False,
            "shadow_candidate_created": False,
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
        },
    }


def _ready_observation_without_records():
    return {
        "scope": "runtime_next_attempt_observation_api_prepare_flow",
        "status": "ready_for_prepare",
        "signal_input_json": "/tmp/ready-signal.json",
        "blockers": [],
        "warnings": [],
        "operator_command_plan": {
            "next_step": "rerun_with_allow_prepare_records_after_owner_review",
            "creates_shadow_candidate": False,
        },
        "safety_invariants": {
            "allow_prepare_records": False,
            "prepare_records_created": False,
            "shadow_candidate_created": False,
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
        },
    }


def _prepared_observation():
    return {
        "scope": "runtime_next_attempt_observation_api_prepare_flow",
        "status": "ready_for_final_gate_preflight",
        "signal_input_json": "/tmp/ready-signal.json",
        "prepare_packet": {
            "operator_command_plan": {
                "prepared_authorization_id": "auth-prepared-1",
            },
        },
        "blockers": [],
        "warnings": [],
        "operator_command_plan": {
            "prepared_authorization_id": "auth-prepared-1",
            "creates_shadow_candidate": True,
        },
        "safety_invariants": {
            "allow_prepare_records": True,
            "prepare_records_created": True,
            "shadow_candidate_created": True,
            "runtime_execution_intent_draft_created": True,
            "recorded_execution_intent_created": True,
            "submit_authorization_created": True,
            "protection_plan_created": True,
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
        },
    }


def test_fresh_signal_loop_blocks_before_observation_when_post_submit_not_ready(tmp_path):
    observation_calls = []

    packet = runtime_fresh_signal_prepare_loop._build_packet(
        _args(tmp_path),
        finalize_builder=lambda args: {
            "status": "finalized_next_attempt_blocked",
            "blockers": ["runtime_active_position_slot_in_use"],
            "warnings": [],
            "safety_invariants": {"exchange_write_called": False},
        },
        observation_builder=lambda args: observation_calls.append(args),
    )

    assert packet["status"] == "blocked"
    assert packet["blocked_stage"] == "post_submit_finalize"
    assert packet["blockers"] == ["runtime_active_position_slot_in_use"]
    assert observation_calls == []
    assert packet["operator_command_plan"]["places_order"] is False
    assert packet["safety_invariants"]["exchange_write_called"] is False


def test_fresh_signal_loop_waits_after_post_submit_ready(tmp_path):
    finalize_calls = []
    observation_calls = []

    packet = runtime_fresh_signal_prepare_loop._build_packet(
        _args(tmp_path),
        finalize_builder=lambda args: finalize_calls.append(args) or _ready_post_submit(),
        observation_builder=lambda args: observation_calls.append(args)
        or _waiting_observation(),
    )

    assert packet["status"] == "waiting_for_signal"
    assert packet["blockers"] == [
        "strategy_signal_not_ready_for_shadow_candidate_prepare"
    ]
    assert finalize_calls[0].reservation_id is None
    assert observation_calls[0].allow_prepare_records is False
    assert packet["operator_command_plan"]["next_step"] == (
        "continue_observation_until_fresh_runtime_signal"
    )
    assert packet["safety_invariants"]["prepare_records_created"] is False
    assert packet["safety_invariants"]["order_lifecycle_called"] is False


def test_fresh_signal_loop_reports_ready_without_creating_records(tmp_path):
    packet = runtime_fresh_signal_prepare_loop._build_packet(
        _args(tmp_path),
        finalize_builder=lambda args: _ready_post_submit(),
        observation_builder=lambda args: _ready_observation_without_records(),
    )

    assert packet["status"] == "ready_for_prepare"
    assert packet["signal_input_json"] == "/tmp/ready-signal.json"
    assert packet["operator_command_plan"]["creates_shadow_candidate"] is False
    assert packet["operator_command_plan"]["places_order"] is False
    assert packet["safety_invariants"]["prepare_records_created"] is False


def test_fresh_signal_loop_can_create_prepare_records_only_when_allowed(tmp_path):
    observation_calls = []

    packet = runtime_fresh_signal_prepare_loop._build_packet(
        _args(tmp_path, allow_prepare_records=True),
        finalize_builder=lambda args: _ready_post_submit(),
        observation_builder=lambda args: observation_calls.append(args)
        or _prepared_observation(),
    )

    assert observation_calls[0].allow_prepare_records is True
    assert packet["status"] == "ready_for_final_gate_preflight"
    assert packet["prepared_authorization_id"] == "auth-prepared-1"
    assert packet["operator_command_plan"]["requires_official_final_gate"] is True
    assert packet["operator_command_plan"]["creates_executable_execution_intent"] is False
    assert packet["safety_invariants"]["prepare_records_created"] is True
    assert packet["safety_invariants"]["shadow_candidate_created"] is True
    assert packet["safety_invariants"]["exchange_write_called"] is False
    assert packet["safety_invariants"]["order_created"] is False


def test_fresh_signal_loop_cli_stdout_is_json_only(monkeypatch, capsys):
    def fake_build_packet(args):
        print("inner noisy loop")
        return {"status": "waiting_for_signal", "ok": True}

    monkeypatch.setattr(
        runtime_fresh_signal_prepare_loop,
        "_build_packet",
        fake_build_packet,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runtime_fresh_signal_prepare_loop.py",
            "--runtime-instance-id",
            "runtime-1",
        ],
    )

    assert runtime_fresh_signal_prepare_loop.main() == 0

    captured = capsys.readouterr()
    assert json.loads(captured.out)["status"] == "waiting_for_signal"
    assert "inner noisy loop" not in captured.out
    assert "inner noisy loop" in captured.err
