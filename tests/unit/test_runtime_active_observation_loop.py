from __future__ import annotations

import json
import time

from scripts import runtime_active_observation_loop


def _args(
    tmp_path,
    *,
    max_iterations=3,
    interval=0.0,
    cycle_timeout_seconds=0.0,
    include_artifacts=False,
    loop_output_json=None,
    status_output_json=None,
):
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
            "cycle_timeout_seconds": cycle_timeout_seconds,
            "loop_output_json": loop_output_json,
            "status_output_json": status_output_json,
            "status_stale_after_seconds": 900.0,
            "include_artifacts": include_artifacts,
            "output_dir": str(tmp_path / "loop"),
            "monitor_args": monitor_args,
        },
    )()


def _artifact(status="waiting_for_signal", *, prepare=False, nested_authorization=False):
    prepared_authorization_id = "auth-ready-1" if prepare else None
    signal_input_json = "/tmp/signal-input-ready.json" if prepare else None
    runtime_summary_extra = {}
    if nested_authorization:
        runtime_summary_extra = {
            "prepared_authorization_id": prepared_authorization_id,
            "signal_input_json": signal_input_json,
            "latest_artifact": {
                "signal_input_json": signal_input_json,
                "prepare_evidence": {
                    "ids": {
                        "authorization_id": prepared_authorization_id,
                    },
                },
            },
        }
    return {
        "status": status,
        "active_runtime_count": 2,
        "monitored_runtime_count": 2,
        "selected_runtime_instance_ids": ["runtime-1", "runtime-2"],
        "blockers": (
            ["strategy_signal_not_ready_for_shadow_candidate_prepare"]
            if status == "waiting_for_signal"
            else []
        ),
        "warnings": [],
        "runtime_summaries": [
            {
                "runtime_instance_id": "runtime-1",
                "symbol": "BNB/USDT:USDT",
                "side": "long",
                "strategy_family_id": "CPM-001",
                "strategy_family_version_id": "CPM-001-v0",
                "status": status,
                "blockers": (
                    ["strategy_signal_not_ready_for_shadow_candidate_prepare"]
                    if status == "waiting_for_signal"
                    else []
                ),
                "signal_summary": {
                    "evaluation_status": "observe_only",
                    "signal_type": "no_action",
                    "reason_codes": ["cpm_no_action_trend_ambiguous"],
                    "human_summary": "4h trend is ambiguous under CPM v0.",
                },
                "signal_input_json": signal_input_json,
                "prepared_authorization_id": prepared_authorization_id,
                **runtime_summary_extra,
            }
        ],
        "observation_monitor_plan": {
            "signal_input_json": signal_input_json,
            "prepared_authorization_id": prepared_authorization_id,
            "creates_shadow_candidate": prepare,
            "creates_execution_intent": False,
            "places_order": False,
            "calls_order_lifecycle": False,
        },
        "safety_invariants": {
            "prepare_records_created": prepare,
            "shadow_candidate_created": prepare,
            "runtime_execution_intent_draft_created": prepare,
            "recorded_execution_intent_created": prepare,
            "submit_authorization_created": prepare,
            "protection_plan_created": prepare,
            "executable_execution_intent_created": False,
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
        return _artifact()

    artifact = runtime_active_observation_loop._build_loop_artifact(
        _args(tmp_path, max_iterations=3),
        artifact_builder=builder,
        sleeper=lambda seconds: None,
        cycle_name_builder=lambda iteration: f"cycle-{iteration}",
    )

    assert artifact["status"] == "waiting_for_signal"
    assert artifact["stop_reason"] == "max_iterations_exhausted"
    assert artifact["iterations_completed"] == 3
    assert len(seen) == 3
    assert artifact["safety_invariants"]["exchange_write_called"] is False
    assert artifact["safety_invariants"]["order_lifecycle_called"] is False
    assert artifact["observation_loop_plan"]["places_order"] is False

    latest = json.loads((tmp_path / "loop" / "latest-summary.json").read_text())
    assert latest["status"] == "waiting_for_signal"
    assert latest["selected_runtime_instance_ids"] == ["runtime-1", "runtime-2"]
    assert latest["runtime_signal_summaries"][0]["signal_summary"]["reason_codes"] == [
        "cpm_no_action_trend_ambiguous"
    ]
    assert (tmp_path / "loop" / "latest-status.txt").read_text().strip() == (
        "waiting_for_signal"
    )


def test_active_observation_loop_writes_pg_coverage_after_cycle(tmp_path, monkeypatch):
    calls = []

    def fake_write_pg(artifact, *, database_url, allow_non_postgres_for_test):
        calls.append(
            {
                "database_url": database_url,
                "allow_non_postgres_for_test": allow_non_postgres_for_test,
                "coverage": artifact["candidate_universe_coverage"],
            }
        )
        return {
            "status": "pg_watcher_runtime_coverage_written",
            "written_count": 1,
        }

    monkeypatch.setattr(
        runtime_active_observation_loop.active_monitor,
        "write_candidate_universe_coverage_to_pg",
        fake_write_pg,
    )

    def builder(args):
        return {
            **_artifact(),
            "candidate_universe_coverage": {
                "rows": [
                    {
                        "strategy_group_id": "MPG-001",
                        "symbol": "OPUSDT",
                        "side": "long",
                        "state": "active_watcher_scope",
                    }
                ]
            },
        }

    args = _args(tmp_path, max_iterations=1)
    args.monitor_args.database_url = "postgresql://unit/runtime"
    args.monitor_args.allow_non_postgres_for_test = False

    artifact = runtime_active_observation_loop._build_loop_artifact(
        args,
        artifact_builder=builder,
        sleeper=lambda seconds: None,
        cycle_name_builder=lambda iteration: f"cycle-{iteration}",
    )

    assert artifact["status"] == "waiting_for_signal"
    assert calls == [
        {
            "database_url": "postgresql://unit/runtime",
            "allow_non_postgres_for_test": False,
            "coverage": {
                "rows": [
                    {
                        "strategy_group_id": "MPG-001",
                        "symbol": "OPUSDT",
                        "side": "long",
                        "state": "active_watcher_scope",
                    }
                ]
            },
        }
    ]
    active_monitor_artifact = json.loads(
        (tmp_path / "loop" / "cycle-1" / "active-monitor.json").read_text()
    )
    assert active_monitor_artifact["pg_watcher_runtime_coverage"] == {
        "status": "pg_watcher_runtime_coverage_written",
        "written_count": 1,
    }


def test_active_observation_loop_refreshes_aggregate_packet_each_cycle(tmp_path):
    output_path = tmp_path / "loop" / "loop-artifact.json"
    status_path = tmp_path / "loop" / "status-artifact.json"
    snapshots = []
    status_snapshots = []

    def builder(args):
        return _artifact()

    def sleeper(seconds):
        assert seconds == 10.0
        snapshots.append(json.loads(output_path.read_text()))
        status_snapshots.append(json.loads(status_path.read_text()))

    artifact = runtime_active_observation_loop._build_loop_artifact(
        _args(
            tmp_path,
            max_iterations=2,
            interval=10.0,
            loop_output_json=str(output_path),
            status_output_json=str(status_path),
        ),
        artifact_builder=builder,
        sleeper=sleeper,
        cycle_name_builder=lambda iteration: f"cycle-{iteration}",
    )

    assert len(snapshots) == 1
    assert snapshots[0]["status"] == "waiting_for_signal"
    assert snapshots[0]["stop_reason"] == "running"
    assert snapshots[0]["iterations_completed"] == 1
    assert status_snapshots[0]["status"] == "waiting_for_signal"
    assert status_snapshots[0]["loop_status"] == "waiting_for_signal"
    assert status_snapshots[0]["iterations_completed"] == 1
    assert status_snapshots[0]["safety_invariants"]["read_artifacts_only"] is True

    latest_file = json.loads(output_path.read_text())
    latest_status_file = json.loads(status_path.read_text())
    assert latest_file["stop_reason"] == "max_iterations_exhausted"
    assert latest_file["iterations_completed"] == 2
    assert latest_file == artifact
    assert latest_status_file["iterations_completed"] == 2
    assert latest_status_file["loop_status"] == "waiting_for_signal"


def test_active_observation_loop_stops_when_prepare_records_are_created(tmp_path):
    calls = []

    def builder(args):
        calls.append(args.output_dir)
        if len(calls) == 1:
            return _artifact()
        return _artifact("ready_for_final_gate_preflight", prepare=True)

    artifact = runtime_active_observation_loop._build_loop_artifact(
        _args(tmp_path, max_iterations=5, include_artifacts=True),
        artifact_builder=builder,
        sleeper=lambda seconds: None,
        cycle_name_builder=lambda iteration: f"cycle-{iteration}",
    )

    assert artifact["status"] == "ready_for_final_gate_preflight"
    assert artifact["stop_reason"] == "status_changed:ready_for_final_gate_preflight"
    assert artifact["iterations_completed"] == 2
    assert len(artifact["cycle_artifacts"]) == 2
    assert artifact["safety_invariants"]["prepare_records_created"] is True
    assert artifact["safety_invariants"]["shadow_candidate_created"] is True
    assert artifact["safety_invariants"]["recorded_execution_intent_created"] is True
    assert artifact["safety_invariants"]["executable_execution_intent_created"] is False
    assert artifact["safety_invariants"]["creates_execution_intent"] is False
    assert artifact["safety_invariants"]["places_order"] is False
    assert artifact["observation_loop_plan"]["next_step"] == (
        "review_prepared_records_then_run_final_gate_preview"
    )
    latest = json.loads((tmp_path / "loop" / "latest-summary.json").read_text())
    assert latest["shadow_candidate_created"] is True
    assert latest["recorded_execution_intent_created"] is True
    assert latest["executable_execution_intent_created"] is False


def test_active_observation_loop_summarizes_nested_prepared_authorization_id(tmp_path):
    def builder(args):
        return _artifact(
            "ready_for_final_gate_preflight",
            prepare=True,
            nested_authorization=True,
        )

    artifact = runtime_active_observation_loop._build_loop_artifact(
        _args(tmp_path, max_iterations=1, include_artifacts=True),
        artifact_builder=builder,
        sleeper=lambda seconds: None,
        cycle_name_builder=lambda iteration: f"cycle-{iteration}",
    )

    assert artifact["status"] == "ready_for_final_gate_preflight"
    assert artifact["latest_summary"]["prepared_authorization_id"] == "auth-ready-1"
    assert artifact["latest_summary"]["signal_input_json"] == (
        "/tmp/signal-input-ready.json"
    )
    assert artifact["latest_summary"]["runtime_signal_summaries"][0][
        "prepared_authorization_id"
    ] == "auth-ready-1"
    assert artifact["latest_summary"]["runtime_signal_summaries"][0][
        "signal_input_json"
    ] == "/tmp/signal-input-ready.json"
    latest = json.loads((tmp_path / "loop" / "latest-summary.json").read_text())
    assert latest["prepared_authorization_id"] == "auth-ready-1"
    assert latest["signal_input_json"] == "/tmp/signal-input-ready.json"


def test_active_observation_loop_ignores_legacy_prepare_packet_authorization(tmp_path):
    def builder(args):
        return {
            **_artifact("ready_for_final_gate_preflight"),
            "runtime_summaries": [
                {
                    "runtime_instance_id": "runtime-1",
                    "symbol": "BNB/USDT:USDT",
                    "side": "long",
                    "strategy_family_id": "CPM-001",
                    "strategy_family_version_id": "CPM-001-v0",
                    "status": "ready_for_final_gate_preflight",
                    "latest_artifact": {
                        "prepare_packet": {
                            "ids": {"authorization_id": "auth-legacy-packet"}
                        }
                    },
                }
            ],
            "observation_monitor_plan": {
                "creates_shadow_candidate": True,
                "creates_execution_intent": False,
                "places_order": False,
                "calls_order_lifecycle": False,
            },
        }

    artifact = runtime_active_observation_loop._build_loop_artifact(
        _args(tmp_path, max_iterations=1, include_artifacts=True),
        artifact_builder=builder,
        sleeper=lambda seconds: None,
        cycle_name_builder=lambda iteration: f"cycle-{iteration}",
    )

    assert artifact["status"] == "ready_for_final_gate_preflight"
    assert artifact["latest_summary"]["prepared_authorization_id"] is None
    assert artifact["latest_summary"]["runtime_signal_summaries"][0][
        "prepared_authorization_id"
    ] is None


def test_active_observation_loop_ignores_legacy_operator_command_plan_sources(tmp_path):
    def builder(args):
        return {
            **_artifact("ready_for_final_gate_preflight"),
            "operator_command_plan": {
                "signal_input_json": "/tmp/legacy-signal-input.json",
                "prepared_authorization_id": "auth-legacy-root",
            },
            "runtime_summaries": [
                {
                    "runtime_instance_id": "runtime-1",
                    "symbol": "BNB/USDT:USDT",
                    "side": "long",
                    "strategy_family_id": "CPM-001",
                    "strategy_family_version_id": "CPM-001-v0",
                    "status": "ready_for_final_gate_preflight",
                    "operator_command_plan": {
                        "signal_input_json": "/tmp/legacy-runtime-signal.json",
                        "prepared_authorization_id": "auth-legacy-runtime",
                    },
                }
            ],
        }

    artifact = runtime_active_observation_loop._build_loop_artifact(
        _args(tmp_path, max_iterations=1, include_artifacts=True),
        artifact_builder=builder,
        sleeper=lambda seconds: None,
        cycle_name_builder=lambda iteration: f"cycle-{iteration}",
    )

    assert artifact["status"] == "ready_for_final_gate_preflight"
    assert artifact["latest_summary"]["signal_input_json"] is None
    assert artifact["latest_summary"]["prepared_authorization_id"] is None
    assert artifact["latest_summary"]["runtime_signal_summaries"][0][
        "signal_input_json"
    ] is None
    assert artifact["latest_summary"]["runtime_signal_summaries"][0][
        "prepared_authorization_id"
    ] is None


def test_active_observation_loop_blocks_and_writes_audit_packet_on_cycle_timeout(tmp_path):
    def builder(args):
        time.sleep(0.05)
        return _artifact()

    output_path = tmp_path / "loop-artifact.json"
    artifact = runtime_active_observation_loop._build_loop_artifact(
        _args(
            tmp_path,
            max_iterations=2,
            cycle_timeout_seconds=0.01,
            loop_output_json=str(output_path),
        ),
        artifact_builder=builder,
        sleeper=lambda seconds: None,
        cycle_name_builder=lambda iteration: f"cycle-{iteration}",
    )

    assert artifact["status"] == "blocked"
    assert artifact["stop_reason"] == "status_changed:blocked"
    assert artifact["iterations_completed"] == 1
    assert artifact["latest_summary"]["blockers"] == [
        "active_observation_cycle_timeout:0.01s"
    ]
    assert artifact["safety_invariants"]["exchange_write_called"] is False
    assert artifact["safety_invariants"]["order_lifecycle_called"] is False
    assert artifact["safety_invariants"]["attempt_counter_mutated"] is False

    file_artifact = json.loads(output_path.read_text())
    assert file_artifact == artifact
    blocked_cycle = json.loads(
        (tmp_path / "loop" / "cycle-1" / "active-monitor.json").read_text()
    )
    assert blocked_cycle["status"] == "blocked"
    assert blocked_cycle["observation_monitor_plan"]["places_order"] is False


def test_active_observation_loop_blocks_and_writes_audit_artifact_on_cycle_error(tmp_path):
    def builder(args):
        raise ValueError("boom")

    output_path = tmp_path / "loop-artifact.json"
    artifact = runtime_active_observation_loop._build_loop_artifact(
        _args(
            tmp_path,
            max_iterations=2,
            loop_output_json=str(output_path),
        ),
        artifact_builder=builder,
        sleeper=lambda seconds: None,
        cycle_name_builder=lambda iteration: f"cycle-{iteration}",
    )

    assert artifact["status"] == "blocked"
    assert artifact["iterations_completed"] == 1
    assert artifact["latest_summary"]["blockers"] == [
        "active_observation_cycle_failed:ValueError:boom"
    ]
    assert artifact["safety_invariants"]["exchange_write_called"] is False
    assert artifact["safety_invariants"]["places_order"] is False
    assert json.loads(output_path.read_text()) == artifact


def test_active_observation_loop_cli_writes_aggregate_json(monkeypatch, capsys, tmp_path):
    output_path = tmp_path / "loop-artifact.json"

    def fake_build_artifact(args):
        return {
            "status": "waiting_for_signal",
            "safety_invariants": {"exchange_write_called": False},
        }

    monkeypatch.setattr(
        runtime_active_observation_loop,
        "_build_loop_artifact",
        fake_build_artifact,
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
