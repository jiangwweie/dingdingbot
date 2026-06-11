from __future__ import annotations

from argparse import Namespace
import json

from scripts import runtime_active_observation_supervisor


def _args(tmp_path, **overrides):
    values = {
        "output_dir": str(tmp_path / "supervisor"),
        "supervisor_output_json": None,
        "loop_output_json": None,
        "followup_output_json": None,
        "env_file": "readonly.env",
        "api_base": "http://unit",
        "source": "live_market",
        "max_iterations": 2,
        "loop_interval_seconds": 0.0,
        "cycle_timeout_seconds": 180.0,
        "one_hour_limit": 25,
        "four_hour_limit": 25,
        "allow_prepare_records": True,
        "allow_disabled_smoke": True,
        "include_packets": False,
        "skip_disabled_smoke_prerequisite_probe": False,
    }
    values.update(overrides)
    return Namespace(**values)


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_supervisor_runs_loop_then_followup_without_real_submit_flags(tmp_path):
    calls = []

    def runner(command, stdout_path):
        calls.append(command)
        if "runtime_active_observation_loop.py" in command[1]:
            loop_path = tmp_path / "supervisor" / "loop-packet.json"
            _write_json(
                loop_path,
                {
                    "status": "waiting_for_signal",
                    "safety_invariants": {
                        "exchange_write_called": False,
                        "order_created": False,
                        "order_lifecycle_called": False,
                        "attempt_counter_mutated": False,
                        "runtime_budget_mutated": False,
                        "withdrawal_or_transfer_created": False,
                    },
                },
            )
        if "runtime_active_observation_followup.py" in command[1]:
            followup_path = tmp_path / "supervisor" / "followup-packet.json"
            _write_json(
                followup_path,
                {
                    "status": "waiting_for_ready_final_gate_preflight",
                    "safety_invariants": {
                        "exchange_called": False,
                        "exchange_order_submitted": False,
                        "order_lifecycle_submit_called": False,
                        "attempt_counter_mutated": False,
                        "runtime_budget_mutated": False,
                        "withdrawal_or_transfer_created": False,
                    },
                },
            )
        return runtime_active_observation_supervisor.CommandResult(
            command=command,
            stdout_path=str(stdout_path),
            returncode=0,
            stderr_tail="",
        )

    packet = runtime_active_observation_supervisor.build_supervisor_packet(
        _args(tmp_path),
        runner=runner,
    )

    flat_commands = " ".join(" ".join(command) for command in calls)
    assert packet["status"] == "supervisor_completed"
    assert packet["loop_status"] == "waiting_for_signal"
    assert packet["followup_status"] == "waiting_for_ready_final_gate_preflight"
    assert "--allow-prepare-records" in calls[0]
    assert "--allow-disabled-smoke" in calls[1]
    assert "--execute-real-submit" not in flat_commands
    assert "--mode execute" not in flat_commands
    assert "--mode arm" not in flat_commands
    assert packet["safety_invariants"]["real_submit_requested"] is False
    assert packet["safety_invariants"]["exchange_order_requested"] is False


def test_supervisor_writes_running_packet_before_loop_blocks(tmp_path):
    running_snapshots = []

    def runner(command, stdout_path):
        if "runtime_active_observation_loop.py" in command[1]:
            running_path = tmp_path / "supervisor" / "supervisor-packet.json"
            running_snapshots.append(json.loads(running_path.read_text()))
            _write_json(
                tmp_path / "supervisor" / "loop-packet.json",
                {
                    "status": "waiting_for_signal",
                    "safety_invariants": {
                        "exchange_write_called": False,
                        "order_created": False,
                        "order_lifecycle_called": False,
                        "attempt_counter_mutated": False,
                        "runtime_budget_mutated": False,
                        "withdrawal_or_transfer_created": False,
                    },
                },
            )
        if "runtime_active_observation_followup.py" in command[1]:
            _write_json(
                tmp_path / "supervisor" / "followup-packet.json",
                {
                    "status": "waiting_for_ready_final_gate_preflight",
                    "safety_invariants": {},
                },
            )
        return runtime_active_observation_supervisor.CommandResult(
            command=command,
            stdout_path=str(stdout_path),
            returncode=0,
            stderr_tail="",
        )

    packet = runtime_active_observation_supervisor.build_supervisor_packet(
        _args(tmp_path, cycle_timeout_seconds=123.0),
        runner=runner,
    )

    assert running_snapshots
    running = running_snapshots[0]
    assert running["status"] == "supervisor_running"
    assert running["operator_command_plan"]["real_submit_requested"] is False
    assert running["safety_invariants"]["exchange_order_requested"] is False
    loop_command = running["command_results"]["loop"]["command"]
    assert "--cycle-timeout-seconds" in loop_command
    assert "123.0" in loop_command

    final_packet = json.loads(
        (tmp_path / "supervisor" / "supervisor-packet.json").read_text()
    )
    assert final_packet == packet
    assert final_packet["status"] == "supervisor_completed"


def test_supervisor_does_not_run_followup_when_loop_packet_missing(tmp_path):
    calls = []

    def runner(command, stdout_path):
        calls.append(command)
        return runtime_active_observation_supervisor.CommandResult(
            command=command,
            stdout_path=str(stdout_path),
            returncode=1,
            stderr_tail="loop failed",
        )

    packet = runtime_active_observation_supervisor.build_supervisor_packet(
        _args(tmp_path),
        runner=runner,
    )

    assert packet["status"] == "supervisor_blocked"
    assert "loop_command_failed:1" in packet["blockers"]
    assert "loop_packet_missing" in packet["blockers"]
    assert len(calls) == 1


def test_supervisor_blocks_when_child_packets_report_forbidden_effect(tmp_path):
    def runner(command, stdout_path):
        if "runtime_active_observation_loop.py" in command[1]:
            _write_json(
                tmp_path / "supervisor" / "loop-packet.json",
                {
                    "status": "ready_for_final_gate_preflight",
                    "safety_invariants": {
                        "exchange_write_called": False,
                        "order_created": False,
                        "order_lifecycle_called": False,
                        "attempt_counter_mutated": False,
                        "runtime_budget_mutated": False,
                        "withdrawal_or_transfer_created": False,
                    },
                },
            )
        if "runtime_active_observation_followup.py" in command[1]:
            _write_json(
                tmp_path / "supervisor" / "followup-packet.json",
                {
                    "status": "disabled_smoke_blocked",
                    "safety_invariants": {
                        "exchange_order_submitted": True,
                    },
                },
            )
        return runtime_active_observation_supervisor.CommandResult(
            command=command,
            stdout_path=str(stdout_path),
            returncode=0,
            stderr_tail="",
        )

    packet = runtime_active_observation_supervisor.build_supervisor_packet(
        _args(tmp_path),
        runner=runner,
    )

    assert packet["status"] == "supervisor_blocked"
    assert "supervisor_detected_forbidden_effects" in packet["blockers"]
    assert packet["safety_invariants"]["forbidden_effects"] == [
        "followup.exchange_order_submitted"
    ]
