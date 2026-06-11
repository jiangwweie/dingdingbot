from __future__ import annotations

import argparse
import os
import sys

from scripts import runtime_next_attempt_observation_cycle


def _args(**overrides):
    values = {
        "runtime_instance_id": "runtime-1",
        "env_file": None,
        "api_base": "http://127.0.0.1:18080",
        "skip_exchange": False,
        "source": "sample",
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
        "four_hour_limit": 12,
        "timeout_seconds": 10.0,
        "signal_output_json": None,
        "output_dir": "output/runtime-next-attempt-observation-cycle",
        "allow_prepare_records": False,
        "candidate_id": None,
        "context_id": None,
        "owner_operator_id": "owner",
        "owner_confirmation_reference": "owner-authorized-unit",
        "reason": "unit observation cycle",
        "next_attempt_symbol": None,
        "next_attempt_side": None,
        "next_attempt_family": None,
        "next_attempt_strategy_family_id": None,
        "next_attempt_carrier_id": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _clear_gate():
    return {
        "status": "clear_for_next_attempt_preflight",
        "blockers": [],
        "warnings": [],
        "next_attempt_gate": {
            "status": "clear_for_preflight",
            "next_attempt_allowed_by_lifecycle": True,
        },
        "safety_invariants": {"exchange_write_called": False},
    }


def _blocked_gate():
    return {
        "status": "blocked",
        "blockers": [{"id": "NEXT-ATTEMPT-CLOSED-REVIEW-REQUIRED"}],
        "warnings": [],
    }


def _ready_signal(path="signal-input.json"):
    return {
        "status": "ready_for_shadow_candidate_prepare",
        "output_signal_input_json": path,
        "evaluation_result": {"status": "ready_for_semantic_binding"},
        "warnings": [],
        "safety_invariants": {"order_candidate_created": False},
    }


def _observe_signal():
    return {
        "status": "observe_only",
        "output_signal_input_json": None,
        "evaluation_result": {
            "status": "observe_only",
            "blockers": ["strategy_signal_not_would_enter"],
        },
        "warnings": [],
    }


def test_observation_cycle_env_loader_fills_empty_existing_env(monkeypatch, tmp_path):
    env_file = tmp_path / "runtime.env"
    env_file.write_text("RUNTIME_NEXT_ATTEMPT_GATE_API_BASE=http://unit")
    monkeypatch.setenv("RUNTIME_NEXT_ATTEMPT_GATE_API_BASE", "")

    runtime_next_attempt_observation_cycle._load_env_file(str(env_file))

    assert os.environ["RUNTIME_NEXT_ATTEMPT_GATE_API_BASE"] == "http://unit"


def test_observation_cycle_blocks_before_signal_when_gate_blocks(monkeypatch):
    async def fake_gate(args):
        return _blocked_gate()

    async def fake_signal(args, *, output_path):
        raise AssertionError("signal should not run when gate blocks")

    monkeypatch.setattr(runtime_next_attempt_observation_cycle, "_build_gate_packet", fake_gate)
    monkeypatch.setattr(runtime_next_attempt_observation_cycle, "_build_signal_packet", fake_signal)

    payload = __import__("asyncio").run(
        runtime_next_attempt_observation_cycle._build_cycle_packet(_args())
    )

    assert payload["status"] == "blocked"
    assert payload["blocked_stage"] == "next_attempt_gate"
    assert payload["operator_command_plan"]["creates_shadow_candidate"] is False
    assert payload["safety_invariants"]["exchange_write_called"] is False


def test_observation_cycle_waits_when_signal_observe_only(monkeypatch):
    async def fake_gate(args):
        return _clear_gate()

    async def fake_signal(args, *, output_path):
        assert output_path is None
        return _observe_signal()

    monkeypatch.setattr(runtime_next_attempt_observation_cycle, "_build_gate_packet", fake_gate)
    monkeypatch.setattr(runtime_next_attempt_observation_cycle, "_build_signal_packet", fake_signal)

    payload = __import__("asyncio").run(
        runtime_next_attempt_observation_cycle._build_cycle_packet(_args())
    )

    assert payload["status"] == "waiting_for_signal"
    assert payload["blocked_stage"] == "strategy_signal"
    assert payload["operator_command_plan"]["next_step"] == (
        "observe_only_or_wait_for_next_closed_bar"
    )
    assert payload["operator_command_plan"]["creates_execution_intent"] is False
    assert payload["safety_invariants"]["order_lifecycle_called"] is False


def test_observation_cycle_ready_for_prepare_without_mutating_records(monkeypatch, tmp_path):
    signal_path = tmp_path / "signal-input.json"

    async def fake_gate(args):
        return _clear_gate()

    async def fake_signal(args, *, output_path):
        assert output_path == str(signal_path)
        return _ready_signal(path=str(signal_path))

    def fake_prepare(args, *, signal_input_json):
        raise AssertionError("prepare should require explicit allow flag")

    monkeypatch.setattr(runtime_next_attempt_observation_cycle, "_build_gate_packet", fake_gate)
    monkeypatch.setattr(runtime_next_attempt_observation_cycle, "_build_signal_packet", fake_signal)
    monkeypatch.setattr(runtime_next_attempt_observation_cycle, "_run_prepare_flow", fake_prepare)

    payload = __import__("asyncio").run(
        runtime_next_attempt_observation_cycle._build_cycle_packet(
            _args(signal_output_json=str(signal_path))
        )
    )

    assert payload["status"] == "ready_for_prepare"
    assert payload["operator_command_plan"]["signal_input_json"] == str(signal_path)
    assert payload["operator_command_plan"]["creates_shadow_candidate"] is False
    assert payload["operator_command_plan"]["creates_execution_intent"] is False
    assert payload["safety_invariants"]["default_read_only"] is True


def test_observation_cycle_can_prepare_records_only_with_explicit_flag(monkeypatch, tmp_path):
    signal_path = tmp_path / "signal-input.json"

    async def fake_gate(args):
        return _clear_gate()

    async def fake_signal(args, *, output_path):
        assert output_path == str(signal_path)
        return _ready_signal(path=str(signal_path))

    def fake_prepare(args, *, signal_input_json):
        assert signal_input_json == str(signal_path)
        return {
            "status": "ready_for_final_gate_preflight",
            "blockers": [],
            "warnings": [],
            "created_records": {
                "shadow_candidate_created": True,
                "execution_intent_created": True,
            },
        }

    monkeypatch.setattr(runtime_next_attempt_observation_cycle, "_build_gate_packet", fake_gate)
    monkeypatch.setattr(runtime_next_attempt_observation_cycle, "_build_signal_packet", fake_signal)
    monkeypatch.setattr(runtime_next_attempt_observation_cycle, "_run_prepare_flow", fake_prepare)

    payload = __import__("asyncio").run(
        runtime_next_attempt_observation_cycle._build_cycle_packet(
            _args(
                allow_prepare_records=True,
                signal_output_json=str(signal_path),
            )
        )
    )

    assert payload["status"] == "ready_for_final_gate_preflight"
    assert payload["operator_command_plan"]["creates_shadow_candidate"] is True
    assert payload["operator_command_plan"]["creates_execution_intent"] is True
    assert payload["operator_command_plan"]["places_order"] is False
    assert payload["operator_command_plan"]["live_submit_allowed"] is False
    assert payload["safety_invariants"]["exchange_write_called"] is False
    assert payload["safety_invariants"]["order_created"] is False


def test_observation_cycle_cli_stdout_is_json_only(monkeypatch, capsys):
    async def fake_cycle(args):
        print("noisy dependency")
        return {"status": "waiting_for_signal", "ok": True}

    monkeypatch.setattr(runtime_next_attempt_observation_cycle, "_build_cycle_packet", fake_cycle)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runtime_next_attempt_observation_cycle.py",
            "--runtime-instance-id",
            "runtime-1",
        ],
    )

    assert runtime_next_attempt_observation_cycle.main() == 0

    captured = capsys.readouterr()
    assert captured.out.startswith("{")
    assert "noisy dependency" not in captured.out
    assert "noisy dependency" in captured.err
