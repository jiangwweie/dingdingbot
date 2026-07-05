from __future__ import annotations

from argparse import Namespace
import json

import pytest

from scripts import runtime_active_observation_supervisor


def _args(tmp_path, **overrides):
    values = {
        "output_dir": str(tmp_path / "supervisor"),
        "supervisor_output_json": None,
        "loop_output_json": None,
        "followup_output_json": None,
        "status_output_json": None,
        "env_file": "readonly.env",
        "api_base": "http://unit",
        "source": "live_market",
        "runtime_instance_id": [],
        "strategy_family_id": [],
        "database_url": "",
        "require_database_url": False,
        "allow_non_postgres_for_test": False,
        "max_iterations": 2,
        "loop_interval_seconds": 0.0,
        "cycle_timeout_seconds": 180.0,
        "status_stale_after_seconds": 900.0,
        "one_hour_limit": 25,
        "four_hour_limit": 25,
        "allow_prepare_records": True,
        "allow_arm_preview": True,
        "allow_attempt_policy_prepare": False,
        "allow_disabled_smoke": True,
        "include_artifacts": False,
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
            loop_path = tmp_path / "supervisor" / "loop-artifact.json"
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
            followup_path = tmp_path / "supervisor" / "followup-artifact.json"
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

    artifact = runtime_active_observation_supervisor.build_supervisor_artifact(
        _args(tmp_path),
        runner=runner,
    )

    flat_commands = " ".join(" ".join(command) for command in calls)
    assert artifact["status"] == "supervisor_completed"
    assert artifact["loop_status"] == "waiting_for_signal"
    assert artifact["followup_status"] == "waiting_for_ready_final_gate_preflight"
    assert "--allow-prepare-records" in calls[0]
    assert "--status-output-json" in calls[0]
    assert "--allow-arm-preview" in calls[1]
    assert "--allow-disabled-smoke" in calls[1]
    assert "--allow-attempt-policy-prepare" not in calls[1]
    assert "--execute-real-submit" not in flat_commands
    assert "--mode execute" not in flat_commands
    assert "--mode arm" not in flat_commands
    assert "operator_command_plan" not in artifact
    assert artifact["supervisor_plan"]["real_submit_requested"] is False
    assert artifact["safety_invariants"]["real_submit_requested"] is False
    assert artifact["safety_invariants"]["exchange_order_requested"] is False
    status_artifact = json.loads(
        (tmp_path / "supervisor" / "status-artifact.json").read_text()
    )
    assert status_artifact["scope"] == "runtime_active_observation_status"
    assert status_artifact["loop_status"] == "waiting_for_signal"
    assert status_artifact["followup_status"] == "waiting_for_ready_final_gate_preflight"
    assert status_artifact["safety_invariants"]["read_artifacts_only"] is True
    assert status_artifact["safety_invariants"]["connects_to_api"] is False
    assert status_artifact["safety_invariants"]["places_order"] is False
    assert not (tmp_path / "supervisor" / "supervisor-packet.json").exists()


def test_supervisor_passes_strategy_family_filters_to_loop(tmp_path):
    calls = []

    def runner(command, stdout_path):
        calls.append(command)
        if "runtime_active_observation_loop.py" in command[1]:
            _write_json(
                tmp_path / "supervisor" / "loop-artifact.json",
                {
                    "status": "waiting_for_signal",
                    "safety_invariants": {},
                },
            )
        if "runtime_active_observation_followup.py" in command[1]:
            _write_json(
                tmp_path / "supervisor" / "followup-artifact.json",
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

    runtime_active_observation_supervisor.build_supervisor_artifact(
        _args(tmp_path, strategy_family_id=["MPG-001", "TEQ-001"]),
        runner=runner,
    )

    assert "--strategy-family-id" in calls[0]
    assert "MPG-001" in calls[0]
    assert "TEQ-001" in calls[0]


def test_supervisor_passes_pg_candidate_universe_flags_to_loop(tmp_path):
    calls = []

    def runner(command, stdout_path):
        calls.append(command)
        if "runtime_active_observation_loop.py" in command[1]:
            _write_json(
                tmp_path / "supervisor" / "loop-artifact.json",
                {
                    "status": "waiting_for_signal",
                    "safety_invariants": {},
                },
            )
        if "runtime_active_observation_followup.py" in command[1]:
            _write_json(
                tmp_path / "supervisor" / "followup-artifact.json",
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

    runtime_active_observation_supervisor.build_supervisor_artifact(
        _args(
            tmp_path,
            database_url="postgresql://unit/runtime",
            require_database_url=True,
        ),
        runner=runner,
    )

    assert "--database-url" in calls[0]
    assert "postgresql+psycopg://unit/runtime" in calls[0]
    assert "--require-database-url" in calls[0]
    assert "--candidate-universe-json" not in calls[0]
    assert "--allow-local-file-diagnostic" not in calls[0]


def test_supervisor_cli_rejects_candidate_universe_json(tmp_path):
    with pytest.raises(SystemExit) as exc:
        runtime_active_observation_supervisor._parse_args(
            [
                "--output-dir",
                str(tmp_path / "supervisor"),
                "--candidate-universe-json",
                "/tmp/candidate-pool.json",
            ]
        )

    assert exc.value.code == 2


def test_supervisor_cli_rejects_local_file_diagnostic_flag(tmp_path):
    with pytest.raises(SystemExit) as exc:
        runtime_active_observation_supervisor._parse_args(
            [
                "--output-dir",
                str(tmp_path / "supervisor"),
                "--allow-local-file-diagnostic",
            ]
        )

    assert exc.value.code == 2


def test_supervisor_writes_running_packet_before_loop_blocks(tmp_path):
    running_snapshots = []

    def runner(command, stdout_path):
        if "runtime_active_observation_loop.py" in command[1]:
            running_path = tmp_path / "supervisor" / "supervisor-artifact.json"
            running_snapshots.append(json.loads(running_path.read_text()))
            running_status_path = tmp_path / "supervisor" / "status-artifact.json"
            running_status = json.loads(running_status_path.read_text())
            assert running_status["supervisor_status"] == "supervisor_running"
            assert running_status["safety_invariants"]["read_artifacts_only"] is True
            _write_json(
                tmp_path / "supervisor" / "loop-artifact.json",
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
                tmp_path / "supervisor" / "followup-artifact.json",
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

    artifact = runtime_active_observation_supervisor.build_supervisor_artifact(
        _args(tmp_path, cycle_timeout_seconds=123.0),
        runner=runner,
    )

    assert running_snapshots
    running = running_snapshots[0]
    assert running["status"] == "supervisor_running"
    assert "operator_command_plan" not in running
    assert running["supervisor_plan"]["real_submit_requested"] is False
    assert running["safety_invariants"]["allow_arm_preview"] is True
    assert running["safety_invariants"]["exchange_order_requested"] is False
    loop_command = running["command_results"]["loop"]["command"]
    assert "--cycle-timeout-seconds" in loop_command
    assert "123.0" in loop_command
    assert "--status-output-json" in loop_command

    final_artifact = json.loads(
        (tmp_path / "supervisor" / "supervisor-artifact.json").read_text()
    )
    assert final_artifact == artifact
    assert final_artifact["status"] == "supervisor_completed"


def test_supervisor_does_not_run_followup_when_loop_artifact_missing(tmp_path):
    calls = []

    def runner(command, stdout_path):
        calls.append(command)
        return runtime_active_observation_supervisor.CommandResult(
            command=command,
            stdout_path=str(stdout_path),
            returncode=1,
            stderr_tail="loop failed",
        )

    artifact = runtime_active_observation_supervisor.build_supervisor_artifact(
        _args(tmp_path),
        runner=runner,
    )

    assert artifact["status"] == "supervisor_blocked"
    assert "loop_command_failed:1" in artifact["blockers"]
    assert "loop_artifact_missing" in artifact["blockers"]
    assert len(calls) == 1


def test_supervisor_blocks_when_child_packets_report_forbidden_effect(tmp_path):
    def runner(command, stdout_path):
        if "runtime_active_observation_loop.py" in command[1]:
            _write_json(
                tmp_path / "supervisor" / "loop-artifact.json",
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
                tmp_path / "supervisor" / "followup-artifact.json",
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

    artifact = runtime_active_observation_supervisor.build_supervisor_artifact(
        _args(tmp_path),
        runner=runner,
    )

    assert artifact["status"] == "supervisor_blocked"
    assert "supervisor_detected_forbidden_effects" in artifact["blockers"]
    assert artifact["safety_invariants"]["forbidden_effects"] == [
        "followup.exchange_order_submitted"
    ]


def test_supervisor_allows_attempt_policy_preflight_when_flagged(tmp_path):
    calls = []

    def runner(command, stdout_path):
        calls.append(command)
        if "runtime_active_observation_loop.py" in command[1]:
            _write_json(
                tmp_path / "supervisor" / "loop-artifact.json",
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
                tmp_path / "supervisor" / "followup-artifact.json",
                {
                    "status": "disabled_smoke_completed",
                    "safety_invariants": {
                        "exchange_order_submitted": False,
                        "real_submit_requested": False,
                        "attempt_policy_preflight_called": True,
                        "attempt_counter_mutated": False,
                        "runtime_budget_mutated": False,
                        "withdrawal_or_transfer_created": False,
                        "arm_preview_forbidden_effects": [],
                        "disabled_smoke_forbidden_effects": [],
                    },
                },
            )
        return runtime_active_observation_supervisor.CommandResult(
            command=command,
            stdout_path=str(stdout_path),
            returncode=0,
            stderr_tail="",
        )

    artifact = runtime_active_observation_supervisor.build_supervisor_artifact(
        _args(tmp_path, allow_attempt_policy_prepare=True),
        runner=runner,
    )

    assert artifact["status"] == "supervisor_completed"
    assert "--allow-attempt-policy-prepare" in calls[1]
    assert artifact["safety_invariants"]["forbidden_effects"] == []
    assert artifact["safety_invariants"]["allowed_official_attempt_policy_prepare"] is True


def test_supervisor_blocks_attempt_policy_mutation_even_when_flagged(tmp_path):
    def runner(command, stdout_path):
        if "runtime_active_observation_loop.py" in command[1]:
            _write_json(
                tmp_path / "supervisor" / "loop-artifact.json",
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
                tmp_path / "supervisor" / "followup-artifact.json",
                {
                    "status": "disabled_smoke_completed",
                    "safety_invariants": {
                        "exchange_order_submitted": False,
                        "real_submit_requested": False,
                        "attempt_policy_preflight_called": True,
                        "attempt_counter_mutated": True,
                        "runtime_budget_mutated": True,
                        "withdrawal_or_transfer_created": False,
                        "arm_preview_forbidden_effects": [],
                        "disabled_smoke_forbidden_effects": [],
                    },
                },
            )
        return runtime_active_observation_supervisor.CommandResult(
            command=command,
            stdout_path=str(stdout_path),
            returncode=0,
            stderr_tail="",
        )

    artifact = runtime_active_observation_supervisor.build_supervisor_artifact(
        _args(tmp_path, allow_attempt_policy_prepare=True),
        runner=runner,
    )

    assert artifact["status"] == "supervisor_blocked"
    assert "supervisor_detected_forbidden_effects" in artifact["blockers"]
    assert "followup.attempt_counter_mutated" in artifact["safety_invariants"][
        "forbidden_effects"
    ]
    assert "followup.runtime_budget_mutated" in artifact["safety_invariants"][
        "forbidden_effects"
    ]


def test_supervisor_blocks_when_followup_reports_arm_preview_forbidden_effect(tmp_path):
    def runner(command, stdout_path):
        if "runtime_active_observation_loop.py" in command[1]:
            _write_json(
                tmp_path / "supervisor" / "loop-artifact.json",
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
                tmp_path / "supervisor" / "followup-artifact.json",
                {
                    "status": "disabled_smoke_blocked",
                    "safety_invariants": {
                        "exchange_called": False,
                        "exchange_order_submitted": False,
                        "order_lifecycle_submit_called": False,
                        "arm_preview_forbidden_effects": [
                            "handoff:order_lifecycle_adapter_result"
                        ],
                        "disabled_smoke_forbidden_effects": [],
                    },
                },
            )
        return runtime_active_observation_supervisor.CommandResult(
            command=command,
            stdout_path=str(stdout_path),
            returncode=0,
            stderr_tail="",
        )

    artifact = runtime_active_observation_supervisor.build_supervisor_artifact(
        _args(tmp_path),
        runner=runner,
    )

    assert artifact["status"] == "supervisor_blocked"
    assert "supervisor_detected_forbidden_effects" in artifact["blockers"]
    assert artifact["safety_invariants"]["forbidden_effects"] == [
        "followup.arm_preview_forbidden_effect:handoff:order_lifecycle_adapter_result"
    ]


def test_supervisor_blocks_when_child_packet_requests_real_submit(tmp_path):
    def runner(command, stdout_path):
        if "runtime_active_observation_loop.py" in command[1]:
            _write_json(
                tmp_path / "supervisor" / "loop-artifact.json",
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
                tmp_path / "supervisor" / "followup-artifact.json",
                {
                    "status": "disabled_smoke_blocked",
                    "safety_invariants": {
                        "real_submit_requested": True,
                        "creates_execution_intent": True,
                    },
                },
            )
        return runtime_active_observation_supervisor.CommandResult(
            command=command,
            stdout_path=str(stdout_path),
            returncode=0,
            stderr_tail="",
        )

    artifact = runtime_active_observation_supervisor.build_supervisor_artifact(
        _args(tmp_path),
        runner=runner,
    )

    assert artifact["status"] == "supervisor_blocked"
    assert artifact["safety_invariants"]["forbidden_effects"] == [
        "followup.creates_execution_intent",
        "followup.real_submit_requested",
    ]


def test_supervisor_runs_followup_after_ready_preflight_without_submit(tmp_path):
    calls = []

    def runner(command, stdout_path):
        calls.append(command)
        if "runtime_active_observation_loop.py" in command[1]:
            _write_json(
                tmp_path / "supervisor" / "loop-artifact.json",
                {
                    "status": "ready_for_final_gate_preflight",
                    "latest_summary": {
                        "status": "ready_for_final_gate_preflight",
                        "prepared_authorization_id": "auth-ready-1",
                    },
                    "operator_command_plan": {
                        "prepared_authorization_id": "auth-ready-1",
                        "creates_execution_intent": False,
                        "places_order": False,
                        "calls_order_lifecycle": False,
                    },
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
                tmp_path / "supervisor" / "followup-artifact.json",
                {
                    "status": "disabled_smoke_completed",
                    "source_loop_status": "ready_for_final_gate_preflight",
                    "prepared_authorization_id": "auth-ready-1",
                    "operator_command_plan": {
                        "arm_preview_called": True,
                        "disabled_smoke_called": True,
                        "owner_confirmed_for_first_real_submit_action": False,
                    },
                    "safety_invariants": {
                        "exchange_called": False,
                        "exchange_order_submitted": False,
                        "order_created": False,
                        "order_lifecycle_submit_called": False,
                        "attempt_counter_mutated": False,
                        "runtime_budget_mutated": False,
                        "withdrawal_or_transfer_created": False,
                        "loop_forbidden_effects": [],
                        "arm_preview_forbidden_effects": [],
                        "disabled_smoke_forbidden_effects": [],
                    },
                },
            )
        return runtime_active_observation_supervisor.CommandResult(
            command=command,
            stdout_path=str(stdout_path),
            returncode=0,
            stderr_tail="",
        )

    artifact = runtime_active_observation_supervisor.build_supervisor_artifact(
        _args(tmp_path),
        runner=runner,
    )

    flat_commands = " ".join(" ".join(command) for command in calls)
    assert artifact["status"] == "supervisor_completed"
    assert artifact["loop_status"] == "ready_for_final_gate_preflight"
    assert artifact["followup_status"] == "disabled_smoke_completed"
    assert artifact["safety_invariants"]["forbidden_effects"] == []
    assert "--allow-arm-preview" in calls[1]
    assert "--allow-disabled-smoke" in calls[1]
    assert "--execute-real-submit" not in flat_commands
    assert "--mode execute" not in flat_commands

    status_artifact = json.loads(
        (tmp_path / "supervisor" / "status-artifact.json").read_text()
    )
    assert status_artifact["loop_status"] == "ready_for_final_gate_preflight"
    assert status_artifact["followup_status"] == "disabled_smoke_completed"
    assert status_artifact["prepared_authorization_id"] == "auth-ready-1"
    assert status_artifact["safety_invariants"]["places_order"] is False
    assert status_artifact["safety_invariants"]["calls_order_lifecycle"] is False


def test_supervisor_passes_runtime_instance_filters_to_loop(tmp_path):
    calls = []

    def runner(command, stdout_path):
        calls.append(command)
        if "runtime_active_observation_loop.py" in command[1]:
            _write_json(
                tmp_path / "supervisor" / "loop-artifact.json",
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
                tmp_path / "supervisor" / "followup-artifact.json",
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

    artifact = runtime_active_observation_supervisor.build_supervisor_artifact(
        _args(
            tmp_path,
            runtime_instance_id=["runtime-ada", "runtime-avax"],
        ),
        runner=runner,
    )

    loop_command = calls[0]
    assert artifact["status"] == "supervisor_completed"
    assert loop_command.count("--runtime-instance-id") == 2
    assert _argument_values(loop_command, "--runtime-instance-id") == [
        "runtime-ada",
        "runtime-avax",
    ]


def _argument_values(command, option):
    values = []
    for index, item in enumerate(command):
        if item == option:
            values.append(command[index + 1])
    return values
