from __future__ import annotations

import argparse
import json
import sys

from scripts import runtime_next_attempt_observation_monitor


def _args(**overrides):
    values = {
        "runtime_instance_id": "runtime-1",
        "max_cycles": 1,
        "interval_seconds": 0.0,
        "continue_on_blocked": False,
        "allow_prepare_records": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _waiting_packet():
    return {
        "status": "waiting_for_signal",
        "blocked_stage": "strategy_signal",
        "blockers": ["strategy_signal_not_ready_for_shadow_candidate_prepare"],
        "warnings": [],
        "signal_input_json": "/tmp/signal.json",
        "observation_cycle_plan": {
            "next_step": "observe_only_or_wait_for_next_closed_bar",
        },
        "safety_invariants": {
            "prepare_records_created": False,
            "exchange_write_called": False,
            "order_created": False,
        },
    }


def _ready_packet():
    return {
        "status": "ready_for_prepare",
        "blockers": [],
        "warnings": [],
        "signal_input_json": "/tmp/ready-signal.json",
        "observation_cycle_plan": {
            "next_step": "rerun_with_allow_prepare_records_after_owner_review",
        },
        "safety_invariants": {
            "prepare_records_created": False,
            "exchange_write_called": False,
            "order_created": False,
        },
    }


def _blocked_packet():
    return {
        "status": "blocked",
        "blocked_stage": "trusted_facts",
        "blockers": ["trusted_submit_fact_snapshot_not_ready"],
        "warnings": [],
        "observation_cycle_plan": {
            "next_step": "resolve_trusted_fact_blocker",
        },
        "safety_invariants": {
            "exchange_write_called": False,
            "order_created": False,
        },
    }


def test_monitor_waiting_signal_runs_requested_cycles_without_side_effects():
    calls = []

    def builder(args):
        calls.append(args.runtime_instance_id)
        return _waiting_packet()

    payload = runtime_next_attempt_observation_monitor._build_monitor_artifact(
        _args(max_cycles=3),
        artifact_builder=builder,
        sleeper=lambda seconds: None,
    )

    assert calls == ["runtime-1", "runtime-1", "runtime-1"]
    assert payload["status"] == "waiting_for_signal"
    assert payload["cycles_completed"] == 3
    assert payload["observation_monitor_plan"]["next_step"] == "wait_for_next_observation_cycle"
    assert payload["safety_invariants"]["monitor_only"] is True
    assert payload["safety_invariants"]["exchange_write_called"] is False
    assert payload["safety_invariants"]["order_lifecycle_called"] is False


def test_monitor_stops_when_ready_for_prepare():
    packets = [_waiting_packet(), _ready_packet(), _waiting_packet()]

    def builder(args):
        return packets.pop(0)

    payload = runtime_next_attempt_observation_monitor._build_monitor_artifact(
        _args(max_cycles=5),
        artifact_builder=builder,
        sleeper=lambda seconds: None,
    )

    assert payload["status"] == "ready_for_prepare"
    assert payload["cycles_completed"] == 2
    assert payload["ready_for_prepare"] is True
    assert payload["observation_monitor_plan"]["signal_input_json"] == "/tmp/ready-signal.json"
    assert payload["observation_monitor_plan"]["places_order"] is False


def test_monitor_stops_on_blocked_by_default():
    calls = []

    def builder(args):
        calls.append(True)
        return _blocked_packet()

    payload = runtime_next_attempt_observation_monitor._build_monitor_artifact(
        _args(max_cycles=3),
        artifact_builder=builder,
        sleeper=lambda seconds: None,
    )

    assert len(calls) == 1
    assert payload["status"] == "blocked"
    assert payload["observation_monitor_plan"]["next_step"] == "resolve_latest_observation_blocker"
    assert payload["blockers"] == ["trusted_submit_fact_snapshot_not_ready"]


def test_monitor_returns_blocked_json_when_cycle_raises():
    def builder(args):
        raise RuntimeError("auth config missing")

    payload = runtime_next_attempt_observation_monitor._build_monitor_artifact(
        _args(max_cycles=2),
        artifact_builder=builder,
        sleeper=lambda seconds: None,
    )

    assert payload["status"] == "blocked"
    assert payload["cycles_completed"] == 1
    assert payload["blockers"] == ["observation_cycle_exception:RuntimeError"]
    assert payload["latest_artifact"]["exception"]["message"] == "auth config missing"
    assert payload["safety_invariants"]["exchange_write_called"] is False


def test_monitor_cli_stdout_is_json_only(monkeypatch, capsys):
    def fake_build_monitor_artifact(args):
        print("inner noisy monitor")
        return {"status": "waiting_for_signal", "ok": True}

    monkeypatch.setattr(
        runtime_next_attempt_observation_monitor,
        "_build_monitor_artifact",
        fake_build_monitor_artifact,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runtime_next_attempt_observation_monitor.py",
            "--runtime-instance-id",
            "runtime-1",
            "--max-cycles",
            "2",
        ],
    )

    assert runtime_next_attempt_observation_monitor.main() == 0

    captured = capsys.readouterr()
    assert json.loads(captured.out)["status"] == "waiting_for_signal"
    assert "inner noisy monitor" not in captured.out
    assert "inner noisy monitor" in captured.err


def test_monitor_cli_can_write_output_json(monkeypatch, capsys, tmp_path):
    output_path = tmp_path / "nested" / "monitor.json"

    def fake_build_monitor_artifact(args):
        return {
            "status": "ready_for_prepare",
            "runtime_instance_id": args.runtime_instance_id,
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
            },
        }

    monkeypatch.setattr(
        runtime_next_attempt_observation_monitor,
        "_build_monitor_artifact",
        fake_build_monitor_artifact,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runtime_next_attempt_observation_monitor.py",
            "--runtime-instance-id",
            "runtime-1",
            "--output-json",
            str(output_path),
        ],
    )

    assert runtime_next_attempt_observation_monitor.main() == 0

    captured = capsys.readouterr()
    stdout_payload = json.loads(captured.out)
    file_payload = json.loads(output_path.read_text())
    assert stdout_payload["status"] == "ready_for_prepare"
    assert file_payload == stdout_payload
    assert file_payload["safety_invariants"]["exchange_write_called"] is False
