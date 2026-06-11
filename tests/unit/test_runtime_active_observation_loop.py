from __future__ import annotations

import json

from scripts import runtime_active_observation_loop


def _args(tmp_path, *, max_iterations=3, interval=0.0, include_packets=False):
    monitor_args = type(
        "MonitorArgs",
        (),
        {
            "output_dir": str(tmp_path / "loop"),
            "output_json": None,
        },
    )()
    return type(
        "Args",
        (),
        {
            "max_iterations": max_iterations,
            "loop_interval_seconds": interval,
            "loop_output_json": None,
            "include_packets": include_packets,
            "output_dir": str(tmp_path / "loop"),
            "monitor_args": monitor_args,
        },
    )()


def _packet(status="waiting_for_signal", *, prepare=False):
    return {
        "status": status,
        "active_runtime_count": 2,
        "monitored_runtime_count": 2,
        "blockers": (
            ["strategy_signal_not_ready_for_shadow_candidate_prepare"]
            if status == "waiting_for_signal"
            else []
        ),
        "warnings": [],
        "operator_command_plan": {
            "creates_shadow_candidate": prepare,
            "creates_execution_intent": False,
            "places_order": False,
            "calls_order_lifecycle": False,
        },
        "safety_invariants": {
            "prepare_records_created": prepare,
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "attempt_counter_mutated": False,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def test_active_observation_loop_runs_waiting_cycles_without_side_effects(tmp_path):
    seen = []

    def builder(args):
        seen.append(args.output_dir)
        return _packet()

    packet = runtime_active_observation_loop._build_loop_packet(
        _args(tmp_path, max_iterations=3),
        packet_builder=builder,
        sleeper=lambda seconds: None,
        cycle_name_builder=lambda iteration: f"cycle-{iteration}",
    )

    assert packet["status"] == "waiting_for_signal"
    assert packet["stop_reason"] == "max_iterations_exhausted"
    assert packet["iterations_completed"] == 3
    assert len(seen) == 3
    assert packet["safety_invariants"]["exchange_write_called"] is False
    assert packet["safety_invariants"]["order_lifecycle_called"] is False
    assert packet["operator_command_plan"]["places_order"] is False

    latest = json.loads((tmp_path / "loop" / "latest-summary.json").read_text())
    assert latest["status"] == "waiting_for_signal"
    assert (tmp_path / "loop" / "latest-status.txt").read_text().strip() == (
        "waiting_for_signal"
    )


def test_active_observation_loop_stops_when_prepare_records_are_created(tmp_path):
    calls = []

    def builder(args):
        calls.append(args.output_dir)
        if len(calls) == 1:
            return _packet()
        return _packet("ready_for_final_gate_preflight", prepare=True)

    packet = runtime_active_observation_loop._build_loop_packet(
        _args(tmp_path, max_iterations=5, include_packets=True),
        packet_builder=builder,
        sleeper=lambda seconds: None,
        cycle_name_builder=lambda iteration: f"cycle-{iteration}",
    )

    assert packet["status"] == "ready_for_final_gate_preflight"
    assert packet["stop_reason"] == "status_changed:ready_for_final_gate_preflight"
    assert packet["iterations_completed"] == 2
    assert len(packet["cycle_packets"]) == 2
    assert packet["safety_invariants"]["prepare_records_created"] is True
    assert packet["safety_invariants"]["creates_execution_intent"] is False
    assert packet["safety_invariants"]["places_order"] is False
    assert packet["operator_command_plan"]["next_step"] == (
        "review_prepared_records_then_run_final_gate_preview"
    )


def test_active_observation_loop_cli_writes_aggregate_json(monkeypatch, capsys, tmp_path):
    output_path = tmp_path / "loop-packet.json"

    def fake_build_packet(args):
        return {
            "status": "waiting_for_signal",
            "safety_invariants": {"exchange_write_called": False},
        }

    monkeypatch.setattr(
        runtime_active_observation_loop,
        "_build_loop_packet",
        fake_build_packet,
    )
    monkeypatch.setattr(
        runtime_active_observation_loop.sys,
        "argv",
        [
            "runtime_active_observation_loop.py",
            "--loop-output-json",
            str(output_path),
        ],
    )

    assert runtime_active_observation_loop.main() == 0

    stdout_payload = json.loads(capsys.readouterr().out)
    file_payload = json.loads(output_path.read_text())
    assert file_payload == stdout_payload
    assert file_payload["status"] == "waiting_for_signal"
