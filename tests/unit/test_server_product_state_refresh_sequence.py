from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_server_product_state_refresh_sequence.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "run_server_product_state_refresh_sequence",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_server_product_state_refresh_sequence_rejects_removed_file_export_modes(
    tmp_path: Path,
):
    module = _load_module()

    for mode in ("diagnostic_full", "control_refresh"):
        with pytest.raises(ValueError, match=f"unsupported refresh mode: {mode}"):
            module.run_server_product_state_refresh_sequence(
                python=sys.executable,
                env_file=tmp_path / "live-readonly.env",
                mode=mode,
                runner=lambda command: module.CommandResult(
                    returncode=0,
                    stdout="ok",
                    stderr="",
                ),
            )


def test_server_product_state_refresh_sequence_uses_pg_control_builders(
    tmp_path: Path,
):
    module = _load_module()
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]):
        calls.append(command)
        return module.CommandResult(returncode=0, stdout="ok", stderr="")

    report = module.run_server_product_state_refresh_sequence(
        python=sys.executable,
        env_file=tmp_path / "live-readonly.env",
        mode="action_time",
        runner=runner,
    )

    assert report["status"] == "server_product_state_refresh_sequence_ready"
    control_builder_names = {
        "scripts/materialize_action_time_fact_snapshots.py",
        "scripts/materialize_pg_promotion_action_time_lane.py",
        "scripts/publish_runtime_control_current_projections.py",
        "scripts/materialize_action_time_ticket.py",
        "scripts/materialize_action_time_finalgate_preflight.py",
        "scripts/materialize_action_time_operation_layer_handoff.py",
        "scripts/materialize_ticket_bound_runtime_safety_state.py",
    }
    control_builder_calls = [
        command
        for command in calls
        if len(command) > 1 and command[1] in control_builder_names
    ]
    assert control_builder_calls
    for command in control_builder_calls:
        assert "--require-database-url" in command
        if command[1] != "scripts/publish_runtime_control_current_projections.py":
            assert "--daily-table-json" not in command
            assert "--candidate-pool-json" not in command
            assert "--goal-status-json" not in command
        assert "--runtime-active-monitor-json" not in command
        assert "--live-facts-json" not in command
        if command[1] == "scripts/materialize_ticket_bound_post_submit_closure.py":
            assert "--latest-submitted" in command
        if command[1] == "scripts/publish_runtime_control_current_projections.py":
            assert "--candidate-pool-json" not in command
            assert "--daily-table-json" not in command
            assert "--goal-status-json" not in command
            assert "--output-json" not in command
            assert "--runtime-monitor-dir" not in command
            assert "--release-manifest" not in command
            assert "--expected-head" not in command
    for command in calls:
        assert "--collect-live-facts-before-refresh" not in command
        assert "--live-facts-output" not in command
    removed_export_builders = {
        "scripts/build_strategy_live_candidate_pool.py",
        "scripts/build_daily_live_enablement_table.py",
        "scripts/build_single_lane_task_packet.py",
        "scripts/build_strategygroup_runtime_goal_status.py",
        "scripts/build_strategy_fresh_signal_action_time_boundary.py",
        "scripts/refresh_strategygroup_runtime_product_state_artifacts.py",
    }
    assert not removed_export_builders.intersection(command[1] for command in calls)
    assert all(
        "output/runtime-monitor/latest-" not in item
        for command in calls
        for item in command
    )


def test_server_product_state_refresh_sequence_watcher_tick_summary_is_lightweight(
    tmp_path: Path,
):
    module = _load_module()
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]):
        calls.append(command)
        return module.CommandResult(returncode=0, stdout="ok", stderr="")

    report = module.run_server_product_state_refresh_sequence(
        python=sys.executable,
        env_file=tmp_path / "live-readonly.env",
        mode="watcher_tick_summary",
        runner=runner,
    )

    command_names = [command[1] for command in calls]
    assert report["status"] == "server_product_state_refresh_sequence_ready"
    assert report["mode"] == "watcher_tick_summary"
    assert command_names == [
        "scripts/publish_runtime_control_current_projections.py",
    ]
    assert "scripts/validate_runtime_candidate_universe_coverage.py" not in command_names
    assert "scripts/build_runtime_signal_watcher_readiness_pack.py" not in command_names
    assert "scripts/build_strategy_live_candidate_pool.py" not in command_names
    assert "scripts/materialize_action_time_ticket.py" not in command_names
    assert "scripts/materialize_action_time_finalgate_preflight.py" not in command_names
    assert "scripts/materialize_ticket_bound_post_submit_closure.py" not in command_names
    assert report["summary"]["current_projection_publish_attempted"] is True
    assert report["safety_invariants"]["calls_ticket_bound_finalgate_preflight"] is False
    assert report["safety_invariants"]["calls_ticket_bound_operation_layer_handoff"] is False
    assert report["safety_invariants"]["calls_ticket_bound_runtime_safety_state"] is False
    assert report["safety_invariants"]["calls_ticket_bound_post_submit_closure"] is False
    assert not (tmp_path / "sequence.json").exists()


def test_server_product_state_refresh_sequence_default_mode_is_watcher_tick_summary(
    tmp_path: Path,
):
    module = _load_module()
    calls: list[tuple[str, ...]] = []

    report = module.run_server_product_state_refresh_sequence(
        python=sys.executable,
        env_file=tmp_path / "live-readonly.env",
        runner=lambda command: (
            calls.append(command)
            or module.CommandResult(returncode=0, stdout="ok", stderr="")
        ),
    )

    assert report["mode"] == "watcher_tick_summary"
    assert [command[1] for command in calls] == [
        "scripts/publish_runtime_control_current_projections.py",
    ]


def test_server_product_state_refresh_sequence_action_time_mode_skips_closure(
    tmp_path: Path,
):
    module = _load_module()
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]):
        calls.append(command)
        return module.CommandResult(returncode=0, stdout="ok", stderr="")

    report = module.run_server_product_state_refresh_sequence(
        python=sys.executable,
        env_file=tmp_path / "live-readonly.env",
        mode="action_time",
        runner=runner,
    )

    command_names = [command[1] for command in calls]
    assert report["status"] == "server_product_state_refresh_sequence_ready"
    assert "scripts/build_runtime_account_safe_facts.py" in command_names
    assert "scripts/materialize_action_time_fact_snapshots.py" in command_names
    assert "scripts/materialize_action_time_ticket.py" in command_names
    assert "scripts/materialize_action_time_finalgate_preflight.py" in command_names
    assert "scripts/materialize_ticket_bound_runtime_safety_state.py" in command_names
    assert "scripts/materialize_ticket_bound_post_submit_closure.py" not in command_names
    assert report["safety_invariants"]["calls_ticket_bound_finalgate_preflight"] is True
    assert report["safety_invariants"]["calls_ticket_bound_post_submit_closure"] is False


def test_server_product_state_refresh_sequence_action_time_if_needed_skips_without_pg_trigger(
    tmp_path: Path,
):
    module = _load_module()
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]):
        calls.append(command)
        return module.CommandResult(returncode=0, stdout="ok", stderr="")

    report = module.run_server_product_state_refresh_sequence(
        python=sys.executable,
        env_file=tmp_path / "live-readonly.env",
        mode="action_time_if_needed",
        action_time_trigger_state={
            "status": "not_triggered",
            "triggered": False,
            "blocker": "",
            "counts": {
                "fresh_live_signal_events": 0,
                "open_promotion_candidates": 0,
                "open_action_time_lane_inputs": 0,
                "open_action_time_tickets": 0,
            },
        },
        runner=runner,
    )

    assert report["status"] == "server_product_state_refresh_sequence_ready"
    assert report["mode"] == "action_time_if_needed"
    assert report["effective_mode"] == "none"
    assert report["summary"]["step_count"] == 0
    assert calls == []
    assert report["safety_invariants"]["calls_ticket_bound_finalgate_preflight"] is False


def test_server_product_state_refresh_sequence_action_time_if_needed_runs_on_pg_trigger(
    tmp_path: Path,
):
    module = _load_module()
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]):
        calls.append(command)
        return module.CommandResult(returncode=0, stdout="ok", stderr="")

    report = module.run_server_product_state_refresh_sequence(
        python=sys.executable,
        env_file=tmp_path / "live-readonly.env",
        mode="action_time_if_needed",
        action_time_trigger_state={
            "status": "triggered",
            "triggered": True,
            "blocker": "",
            "counts": {
                "fresh_live_signal_events": 1,
                "open_promotion_candidates": 0,
                "open_action_time_lane_inputs": 0,
                "open_action_time_tickets": 0,
            },
        },
        runner=runner,
    )

    command_names = [command[1] for command in calls]
    assert report["status"] == "server_product_state_refresh_sequence_ready"
    assert report["mode"] == "action_time_if_needed"
    assert report["effective_mode"] == "action_time"
    assert "scripts/materialize_action_time_ticket.py" in command_names
    assert command_names.index("scripts/materialize_action_time_fact_snapshots.py") < command_names.index(
        "scripts/publish_runtime_control_current_projections.py"
    )
    assert command_names.index("scripts/publish_runtime_control_current_projections.py") < command_names.index(
        "scripts/materialize_pg_promotion_action_time_lane.py"
    )
    assert "scripts/materialize_action_time_finalgate_preflight.py" in command_names
    assert "scripts/materialize_ticket_bound_post_submit_closure.py" not in command_names


def test_server_product_state_refresh_sequence_action_time_if_needed_fails_closed_on_pg_gap(
    tmp_path: Path,
):
    module = _load_module()

    report = module.run_server_product_state_refresh_sequence(
        python=sys.executable,
        env_file=tmp_path / "live-readonly.env",
        mode="action_time_if_needed",
        action_time_trigger_state={
            "status": "blocked",
            "triggered": False,
            "blocker": "missing_fact:PG_DATABASE_URL",
            "counts": {},
        },
        runner=lambda command: module.CommandResult(returncode=0, stdout="ok", stderr=""),
    )

    assert report["status"] == "server_product_state_refresh_sequence_failed"
    assert report["summary"]["failed_required_step_count"] == 1
    assert report["summary"]["blocked_by_required_step"] == "pg_action_time_trigger_state"
    assert report["step_results"][0]["name"] == "pg_action_time_trigger_state"


def test_action_time_trigger_counts_ignore_expired_closed_and_invalidated_rows():
    module = _load_module()
    engine = _action_time_trigger_engine()
    now_ms = 1_000_000
    try:
        with engine.begin() as conn:
            _insert_action_time_trigger_rows(conn, now_ms=now_ms, expired=True)
            counts = module._action_time_trigger_counts(conn, now_ms=now_ms)
            assert counts == {
                "fresh_live_signal_events": 0,
                "open_promotion_candidates": 0,
                "stale_open_promotion_candidates": 0,
                "open_action_time_lane_inputs": 0,
                "stale_open_action_time_lane_inputs": 0,
                "open_action_time_tickets": 0,
                "stale_open_action_time_tickets": 0,
            }

            _insert_action_time_trigger_rows(conn, now_ms=now_ms, expired=False)
            counts = module._action_time_trigger_counts(conn, now_ms=now_ms)
            assert counts == {
                "fresh_live_signal_events": 1,
                "open_promotion_candidates": 1,
                "stale_open_promotion_candidates": 0,
                "open_action_time_lane_inputs": 1,
                "stale_open_action_time_lane_inputs": 0,
                "open_action_time_tickets": 1,
                "stale_open_action_time_tickets": 0,
            }
    finally:
        engine.dispose()


def test_action_time_trigger_counts_include_stale_open_rows():
    module = _load_module()
    engine = _action_time_trigger_engine()
    now_ms = 1_000_000
    try:
        with engine.begin() as conn:
            _insert_stale_open_action_time_trigger_rows(conn, now_ms=now_ms)
            counts = module._action_time_trigger_counts(conn, now_ms=now_ms)
            assert counts == {
                "fresh_live_signal_events": 0,
                "open_promotion_candidates": 0,
                "stale_open_promotion_candidates": 1,
                "open_action_time_lane_inputs": 0,
                "stale_open_action_time_lane_inputs": 1,
                "open_action_time_tickets": 0,
                "stale_open_action_time_tickets": 1,
            }
    finally:
        engine.dispose()


def test_action_time_trigger_counts_ignore_non_live_fresh_signal():
    module = _load_module()
    engine = _action_time_trigger_engine()
    now_ms = 1_000_000
    try:
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO brc_live_signal_events VALUES (
                        'signal-replay',
                        'replay',
                        'fresh',
                        'facts_validated',
                        :expires_at_ms,
                        NULL
                    )
                    """
                ),
                {"expires_at_ms": now_ms + 60_000},
            )
            counts = module._action_time_trigger_counts(conn, now_ms=now_ms)
    finally:
        engine.dispose()

    assert counts == {
        "fresh_live_signal_events": 0,
        "open_promotion_candidates": 0,
        "stale_open_promotion_candidates": 0,
        "open_action_time_lane_inputs": 0,
        "stale_open_action_time_lane_inputs": 0,
        "open_action_time_tickets": 0,
        "stale_open_action_time_tickets": 0,
    }


def test_server_product_state_refresh_sequence_closure_mode_skips_control_rebuild(
    tmp_path: Path,
):
    module = _load_module()
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]):
        calls.append(command)
        return module.CommandResult(returncode=0, stdout="ok", stderr="")

    report = module.run_server_product_state_refresh_sequence(
        python=sys.executable,
        env_file=tmp_path / "live-readonly.env",
        mode="closure",
        runner=runner,
    )

    command_names = [command[1] for command in calls]
    assert report["status"] == "server_product_state_refresh_sequence_ready"
    assert "scripts/materialize_ticket_bound_post_submit_closure.py" in command_names
    assert "scripts/build_strategy_live_candidate_pool.py" not in command_names
    assert "scripts/materialize_action_time_ticket.py" not in command_names
    assert command_names[-1] == "scripts/publish_runtime_control_current_projections.py"
    assert report["safety_invariants"]["calls_ticket_bound_post_submit_closure"] is True


def test_server_product_state_refresh_sequence_normalizes_child_pg_dsn():
    module = _load_module()

    env = module._command_env_with_sync_pg_dsn(
        {
            "PG_DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/brc",
            "DATABASE_URL": "postgresql://user:pass@localhost:5432/brc",
        }
    )

    assert env["PG_DATABASE_URL"] == (
        "postgresql+psycopg://user:pass@localhost:5432/brc"
    )
    assert env["DATABASE_URL"] == (
        "postgresql+psycopg://user:pass@localhost:5432/brc"
    )


def test_server_product_state_refresh_sequence_fails_closed_on_projection_publish_failure(
    tmp_path: Path,
):
    module = _load_module()
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]):
        calls.append(command)
        if any(
            item.endswith("publish_runtime_control_current_projections.py")
            for item in command
        ):
            return module.CommandResult(
                returncode=1,
                stdout="",
                stderr="current projection publish failed",
            )
        return module.CommandResult(returncode=0, stdout="ok", stderr="")

    report = module.run_server_product_state_refresh_sequence(
        python=sys.executable,
        env_file=tmp_path / "live-readonly.env",
        mode="action_time",
        runner=runner,
    )

    assert report["status"] == "server_product_state_refresh_sequence_failed"
    assert report["summary"]["failed_required_step_count"] == 1
    assert report["summary"]["current_projection_publish_attempted"] is True
    assert report["summary"]["blocked_by_required_step"] == (
        "publish_runtime_control_current_projections_before_lane"
    )
    assert calls[-1][1] == "scripts/publish_runtime_control_current_projections.py"


def test_server_product_state_refresh_sequence_fails_closed_on_action_time_fact_failure(
    tmp_path: Path,
):
    module = _load_module()
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]):
        calls.append(command)
        if any(
            item.endswith("materialize_action_time_fact_snapshots.py")
            for item in command
        ):
            return module.CommandResult(
                returncode=1,
                stdout="",
                stderr="action-time fact materialization failed",
            )
        return module.CommandResult(returncode=0, stdout="ok", stderr="")

    report = module.run_server_product_state_refresh_sequence(
        python=sys.executable,
        env_file=tmp_path / "live-readonly.env",
        mode="action_time",
        runner=runner,
    )

    assert report["status"] == "server_product_state_refresh_sequence_failed"
    assert report["summary"]["failed_required_step_count"] == 1
    assert report["summary"]["current_projection_publish_attempted"] is False
    assert report["summary"]["blocked_by_required_step"] == (
        "materialize_action_time_fact_snapshots"
    )
    assert calls[-1][1] == "scripts/materialize_action_time_fact_snapshots.py"
    skipped_names = [
        step["name"]
        for step in report["step_results"]
        if step["status"] == "skipped_after_required_failure"
    ]
    assert "publish_runtime_control_current_projections_before_lane" in skipped_names
    assert "materialize_pg_promotion_action_time_lane" in skipped_names
    assert "materialize_action_time_ticket" in skipped_names


def test_server_product_state_refresh_sequence_omits_legacy_candidate_pool_materializer(
    tmp_path: Path,
):
    module = _load_module()
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]):
        calls.append(command)
        if any(
            item.endswith("materialize_candidate_pool_action_time_lane.py")
            for item in command
        ):
            return module.CommandResult(
                returncode=1,
                stdout="",
                stderr="legacy candidate-pool materializer must not run",
            )
        return module.CommandResult(returncode=0, stdout="ok", stderr="")

    report = module.run_server_product_state_refresh_sequence(
        python=sys.executable,
        env_file=tmp_path / "live-readonly.env",
        mode="action_time",
        runner=runner,
    )

    assert report["status"] == "server_product_state_refresh_sequence_ready"
    assert report["summary"]["failed_required_step_count"] == 0
    assert report["summary"]["current_projection_publish_attempted"] is True
    assert all(
        "scripts/materialize_candidate_pool_action_time_lane.py" not in command
        for command in calls
    )


def test_server_product_state_refresh_sequence_fails_closed_on_pg_lane_materializer_failure(
    tmp_path: Path,
):
    module = _load_module()
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]):
        calls.append(command)
        if any(
            item.endswith("materialize_pg_promotion_action_time_lane.py")
            for item in command
        ):
            return module.CommandResult(
                returncode=1,
                stdout="",
                stderr="pg promotion/action-time materialization failed",
            )
        return module.CommandResult(returncode=0, stdout="ok", stderr="")

    report = module.run_server_product_state_refresh_sequence(
        python=sys.executable,
        env_file=tmp_path / "live-readonly.env",
        mode="action_time",
        runner=runner,
    )

    assert report["status"] == "server_product_state_refresh_sequence_failed"
    assert report["summary"]["failed_required_step_count"] == 1
    assert report["summary"]["current_projection_publish_attempted"] is True
    assert report["summary"]["blocked_by_required_step"] == (
        "materialize_pg_promotion_action_time_lane"
    )
    assert calls[-1][1] == "scripts/materialize_pg_promotion_action_time_lane.py"
    skipped_names = [
        step["name"]
        for step in report["step_results"]
        if step["status"] == "skipped_after_required_failure"
    ]
    assert "materialize_action_time_ticket" in skipped_names
    assert "publish_runtime_control_current_projections_after_action_time" in skipped_names


def test_server_product_state_refresh_sequence_fails_closed_on_ticket_failure(
    tmp_path: Path,
):
    module = _load_module()
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]):
        calls.append(command)
        if any(item.endswith("materialize_action_time_ticket.py") for item in command):
            return module.CommandResult(
                returncode=1,
                stdout="",
                stderr="action-time ticket materialization failed",
            )
        return module.CommandResult(returncode=0, stdout="ok", stderr="")

    report = module.run_server_product_state_refresh_sequence(
        python=sys.executable,
        env_file=tmp_path / "live-readonly.env",
        mode="action_time",
        runner=runner,
    )

    assert report["status"] == "server_product_state_refresh_sequence_failed"
    assert report["summary"]["failed_required_step_count"] == 1
    assert report["summary"]["current_projection_publish_attempted"] is True
    assert report["summary"]["blocked_by_required_step"] == (
        "materialize_action_time_ticket"
    )
    assert calls[-1][1] == "scripts/materialize_action_time_ticket.py"
    skipped_names = [
        step["name"]
        for step in report["step_results"]
        if step["status"] == "skipped_after_required_failure"
    ]
    assert "publish_runtime_control_current_projections_after_action_time" in skipped_names


def test_server_product_state_refresh_sequence_fails_closed_on_finalgate_failure(
    tmp_path: Path,
):
    module = _load_module()
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]):
        calls.append(command)
        if any(
            item.endswith("materialize_action_time_finalgate_preflight.py")
            for item in command
        ):
            return module.CommandResult(
                returncode=1,
                stdout="",
                stderr="ticket-bound finalgate preflight failed",
            )
        return module.CommandResult(returncode=0, stdout="ok", stderr="")

    report = module.run_server_product_state_refresh_sequence(
        python=sys.executable,
        env_file=tmp_path / "live-readonly.env",
        mode="action_time",
        runner=runner,
    )

    assert report["status"] == "server_product_state_refresh_sequence_failed"
    assert report["summary"]["failed_required_step_count"] == 1
    assert report["summary"]["current_projection_publish_attempted"] is True
    assert report["summary"]["blocked_by_required_step"] == (
        "materialize_action_time_finalgate_preflight"
    )
    assert calls[-1][1] == "scripts/materialize_action_time_finalgate_preflight.py"
    skipped_names = [
        step["name"]
        for step in report["step_results"]
        if step["status"] == "skipped_after_required_failure"
    ]
    assert "publish_runtime_control_current_projections_after_action_time" in skipped_names


def test_server_product_state_refresh_sequence_fails_closed_on_operation_handoff_failure(
    tmp_path: Path,
):
    module = _load_module()
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]):
        calls.append(command)
        if any(
            item.endswith("materialize_action_time_operation_layer_handoff.py")
            for item in command
        ):
            return module.CommandResult(
                returncode=1,
                stdout="",
                stderr="operation layer handoff failed",
            )
        return module.CommandResult(returncode=0, stdout="ok", stderr="")

    report = module.run_server_product_state_refresh_sequence(
        python=sys.executable,
        env_file=tmp_path / "live-readonly.env",
        mode="action_time",
        runner=runner,
    )

    assert report["status"] == "server_product_state_refresh_sequence_failed"
    assert report["summary"]["failed_required_step_count"] == 1
    assert report["summary"]["current_projection_publish_attempted"] is True
    assert report["summary"]["blocked_by_required_step"] == (
        "materialize_action_time_operation_layer_handoff"
    )
    assert calls[-1][1] == "scripts/materialize_action_time_operation_layer_handoff.py"
    skipped_names = [
        step["name"]
        for step in report["step_results"]
        if step["status"] == "skipped_after_required_failure"
    ]
    assert "publish_runtime_control_current_projections_after_action_time" in skipped_names


def test_server_product_state_refresh_sequence_fails_closed_on_runtime_safety_failure(
    tmp_path: Path,
):
    module = _load_module()
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]):
        calls.append(command)
        if any(
            item.endswith("materialize_ticket_bound_runtime_safety_state.py")
            for item in command
        ):
            return module.CommandResult(
                returncode=1,
                stdout="",
                stderr="ticket-bound runtime safety state failed",
            )
        return module.CommandResult(returncode=0, stdout="ok", stderr="")

    report = module.run_server_product_state_refresh_sequence(
        python=sys.executable,
        env_file=tmp_path / "live-readonly.env",
        mode="action_time",
        runner=runner,
    )

    assert report["status"] == "server_product_state_refresh_sequence_failed"
    assert report["summary"]["failed_required_step_count"] == 1
    assert report["summary"]["current_projection_publish_attempted"] is True
    assert report["summary"]["blocked_by_required_step"] == (
        "materialize_ticket_bound_runtime_safety_state"
    )
    assert calls[-1][1] == "scripts/materialize_ticket_bound_runtime_safety_state.py"
    skipped_names = [
        step["name"]
        for step in report["step_results"]
        if step["status"] == "skipped_after_required_failure"
    ]
    assert "publish_runtime_control_current_projections_after_action_time" in skipped_names


def test_server_product_state_refresh_sequence_fails_closed_on_post_submit_closure_failure(
    tmp_path: Path,
):
    module = _load_module()
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]):
        calls.append(command)
        if any(
            item.endswith("materialize_ticket_bound_post_submit_closure.py")
            for item in command
        ):
            return module.CommandResult(
                returncode=1,
                stdout="",
                stderr="ticket-bound post-submit closure failed",
            )
        return module.CommandResult(returncode=0, stdout="ok", stderr="")

    report = module.run_server_product_state_refresh_sequence(
        python=sys.executable,
        env_file=tmp_path / "live-readonly.env",
        mode="closure",
        runner=runner,
    )

    assert report["status"] == "server_product_state_refresh_sequence_failed"
    assert report["summary"]["failed_required_step_count"] == 1
    assert report["summary"]["current_projection_publish_attempted"] is False
    assert report["summary"]["blocked_by_required_step"] == (
        "materialize_ticket_bound_post_submit_closure"
    )
    assert calls[-1][1] == "scripts/materialize_ticket_bound_post_submit_closure.py"
    assert "--latest-submitted" in calls[-1]
    skipped_names = [
        step["name"]
        for step in report["step_results"]
        if step["status"] == "skipped_after_required_failure"
    ]
    assert "publish_runtime_control_current_projections_after_action_time" in skipped_names


def test_server_product_state_refresh_sequence_requires_account_safe_facts(
    tmp_path: Path,
):
    module = _load_module()
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]):
        calls.append(command)
        if any(
            item.endswith("build_runtime_account_safe_facts.py")
            for item in command
        ):
            return module.CommandResult(
                returncode=1,
                stdout="",
                stderr="account facts unavailable",
            )
        return module.CommandResult(returncode=0, stdout="ok", stderr="")

    report = module.run_server_product_state_refresh_sequence(
        python=sys.executable,
        env_file=tmp_path / "live-readonly.env",
        mode="action_time",
        runner=runner,
    )

    assert report["status"] == "server_product_state_refresh_sequence_failed"
    assert report["summary"]["blocked_by_required_step"] == "build_account_safe_facts"
    assert report["summary"]["current_projection_publish_attempted"] is False
    assert calls[-1][1] == "scripts/build_runtime_account_safe_facts.py"
    skipped_names = [
        step["name"]
        for step in report["step_results"]
        if step["status"] == "skipped_after_required_failure"
    ]
    assert "materialize_action_time_ticket" in skipped_names
    assert "publish_runtime_control_current_projections_before_lane" in skipped_names
    assert "publish_runtime_control_current_projections_after_action_time" in skipped_names


def _action_time_trigger_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                CREATE TABLE brc_live_signal_events (
                    signal_event_id TEXT PRIMARY KEY,
                    source_kind TEXT,
                    freshness_state TEXT,
                    status TEXT,
                    expires_at_ms INTEGER,
                    invalidated_at_ms INTEGER
                )
                """
            )
        )
        conn.execute(
            sa.text(
                """
                CREATE TABLE brc_promotion_candidates (
                    promotion_candidate_id TEXT PRIMARY KEY,
                    status TEXT,
                    expires_at_ms INTEGER,
                    closed_at_ms INTEGER
                )
                """
            )
        )
        conn.execute(
            sa.text(
                """
                CREATE TABLE brc_action_time_lane_inputs (
                    action_time_lane_input_id TEXT PRIMARY KEY,
                    lane_scope TEXT,
                    status TEXT,
                    expires_at_ms INTEGER,
                    closed_at_ms INTEGER
                )
                """
            )
        )
        conn.execute(
            sa.text(
                """
                CREATE TABLE brc_action_time_tickets (
                    ticket_id TEXT PRIMARY KEY,
                    status TEXT,
                    expires_at_ms INTEGER
                )
                """
            )
        )
    return engine


def _insert_action_time_trigger_rows(
    conn: sa.engine.Connection,
    *,
    now_ms: int,
    expired: bool,
) -> None:
    suffix = "expired" if expired else "active"
    expires_at_ms = now_ms - 1 if expired else now_ms + 60_000
    closed_at_ms = now_ms - 1 if expired else None
    invalidated_at_ms = now_ms - 1 if expired else None
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_live_signal_events VALUES (
                :id,
                'live_market',
                'fresh',
                'facts_validated',
                :expires_at_ms,
                :invalidated_at_ms
            )
            """
        ),
        {
            "id": f"signal-{suffix}",
            "expires_at_ms": expires_at_ms,
            "invalidated_at_ms": invalidated_at_ms,
        },
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_promotion_candidates VALUES (
                :id,
                'eligible',
                :expires_at_ms,
                :closed_at_ms
            )
            """
        ),
        {
            "id": f"promotion-{suffix}",
            "expires_at_ms": expires_at_ms,
            "closed_at_ms": closed_at_ms,
        },
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_action_time_lane_inputs VALUES (
                :id,
                'real_submit_candidate',
                'ticket_pending',
                :expires_at_ms,
                :closed_at_ms
            )
            """
        ),
        {
            "id": f"lane-{suffix}",
            "expires_at_ms": expires_at_ms,
            "closed_at_ms": closed_at_ms,
        },
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_action_time_tickets VALUES (
                :id,
                :status,
                :expires_at_ms
            )
            """
        ),
        {
            "id": f"ticket-{suffix}",
            "status": "expired" if expired else "created",
            "expires_at_ms": expires_at_ms,
        },
    )


def _insert_stale_open_action_time_trigger_rows(
    conn: sa.engine.Connection,
    *,
    now_ms: int,
) -> None:
    expires_at_ms = now_ms - 1
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_live_signal_events VALUES (
                'stale-open-signal',
                'live_market',
                'fresh',
                'facts_validated',
                :expires_at_ms,
                NULL
            )
            """
        ),
        {"expires_at_ms": expires_at_ms},
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_promotion_candidates VALUES (
                'stale-open-promotion',
                'arbitration_won',
                :expires_at_ms,
                NULL
            )
            """
        ),
        {"expires_at_ms": expires_at_ms},
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_action_time_lane_inputs VALUES (
                'stale-open-lane',
                'real_submit_candidate',
                'ticket_pending',
                :expires_at_ms,
                NULL
            )
            """
        ),
        {"expires_at_ms": expires_at_ms},
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_action_time_tickets VALUES (
                'stale-open-ticket',
                'finalgate_ready',
                :expires_at_ms
            )
            """
        ),
        {"expires_at_ms": expires_at_ms},
    )
