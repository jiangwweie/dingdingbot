from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


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


def test_server_product_state_refresh_sequence_records_optional_failure(tmp_path: Path):
    module = _load_module()
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]):
        calls.append(command)
        if any(
            item.endswith("refresh_strategygroup_runtime_product_state_artifacts.py")
            for item in command
        ):
            return module.CommandResult(
                returncode=1,
                stdout="",
                stderr="optional refresh failed",
            )
        return module.CommandResult(returncode=0, stdout="ok", stderr="")

    report = module.run_server_product_state_refresh_sequence(
        python=sys.executable,
        report_dir=tmp_path / "reports",
        runtime_monitor_dir=tmp_path / "runtime-monitor",
        env_file=tmp_path / "live-readonly.env",
        output_json=tmp_path / "sequence.json",
        runner=runner,
    )

    assert report["status"] == "server_product_state_refresh_sequence_ready"
    assert report["summary"]["failed_optional_step_count"] == 1
    assert report["summary"]["failed_required_step_count"] == 0
    assert report["summary"]["final_goal_status_attempted"] is True
    assert calls[-1][1] == "scripts/build_strategygroup_runtime_goal_status.py"
    command_names = [command[1] for command in calls]
    assert "scripts/materialize_candidate_pool_action_time_lane.py" not in command_names
    assert "scripts/build_strategygroup_runtime_safety_state.py" not in command_names
    assert "scripts/materialize_pg_promotion_action_time_lane.py" in command_names
    assert "scripts/materialize_action_time_ticket.py" in command_names
    assert "scripts/materialize_action_time_finalgate_preflight.py" in command_names
    assert "scripts/materialize_action_time_operation_layer_handoff.py" in command_names
    assert "scripts/materialize_ticket_bound_runtime_safety_state.py" in command_names
    assert "scripts/materialize_ticket_bound_post_submit_closure.py" in command_names
    assert "scripts/build_runtime_signal_watcher_readiness_pack.py" in command_names
    assert (tmp_path / "sequence.json").exists()


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
        report_dir=tmp_path / "reports",
        runtime_monitor_dir=tmp_path / "runtime-monitor",
        env_file=tmp_path / "live-readonly.env",
        output_json=tmp_path / "sequence.json",
        runner=runner,
    )

    assert report["status"] == "server_product_state_refresh_sequence_ready"
    control_builder_names = {
        "scripts/build_strategy_live_candidate_pool.py",
        "scripts/build_daily_live_enablement_table.py",
        "scripts/build_single_lane_task_packet.py",
        "scripts/materialize_pg_promotion_action_time_lane.py",
        "scripts/build_strategygroup_runtime_goal_status.py",
        "scripts/materialize_action_time_ticket.py",
        "scripts/materialize_action_time_finalgate_preflight.py",
        "scripts/materialize_action_time_operation_layer_handoff.py",
        "scripts/materialize_ticket_bound_runtime_safety_state.py",
        "scripts/materialize_ticket_bound_post_submit_closure.py",
    }
    control_builder_calls = [
        command
        for command in calls
        if len(command) > 1 and command[1] in control_builder_names
    ]
    assert control_builder_calls
    for command in control_builder_calls:
        assert "--require-database-url" in command
        assert "--daily-table-json" not in command
        assert "--candidate-pool-json" not in command
        assert "--runtime-active-monitor-json" not in command
        assert "--live-facts-json" not in command
        if command[1] == "scripts/materialize_ticket_bound_post_submit_closure.py":
            assert "--latest-submitted" in command
    for command in calls:
        assert "--collect-live-facts-before-refresh" not in command
        assert "--live-facts-output" not in command
    assert all(
        "output/runtime-monitor/latest-" not in item
        for command in calls
        for item in command
    )


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


def test_server_product_state_refresh_sequence_fails_on_required_step_but_continues(
    tmp_path: Path,
):
    module = _load_module()
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]):
        calls.append(command)
        if any(item.endswith("validate_strategy_live_candidate_pool.py") for item in command):
            return module.CommandResult(
                returncode=1,
                stdout="",
                stderr="candidate pool invalid",
            )
        return module.CommandResult(returncode=0, stdout="ok", stderr="")

    report = module.run_server_product_state_refresh_sequence(
        python=sys.executable,
        report_dir=tmp_path / "reports",
        runtime_monitor_dir=tmp_path / "runtime-monitor",
        env_file=tmp_path / "live-readonly.env",
        output_json=tmp_path / "sequence.json",
        runner=runner,
    )

    assert report["status"] == "server_product_state_refresh_sequence_failed"
    assert report["summary"]["failed_required_step_count"] == 1
    assert report["summary"]["skipped_after_required_failure_count"] > 0
    assert report["summary"]["final_goal_status_attempted"] is False
    assert report["summary"]["final_goal_status_suppressed"] is True
    assert report["summary"]["blocked_by_required_step"] == "validate_candidate_pool"
    assert calls[-1][1] == "scripts/validate_strategy_live_candidate_pool.py"
    skipped_names = [
        step["name"]
        for step in report["step_results"]
        if step["status"] == "skipped_after_required_failure"
    ]
    assert "build_goal_status" in skipped_names


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
        report_dir=tmp_path / "reports",
        runtime_monitor_dir=tmp_path / "runtime-monitor",
        env_file=tmp_path / "live-readonly.env",
        output_json=tmp_path / "sequence.json",
        runner=runner,
    )

    assert report["status"] == "server_product_state_refresh_sequence_ready"
    assert report["summary"]["failed_required_step_count"] == 0
    assert report["summary"]["final_goal_status_attempted"] is True
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
        report_dir=tmp_path / "reports",
        runtime_monitor_dir=tmp_path / "runtime-monitor",
        env_file=tmp_path / "live-readonly.env",
        output_json=tmp_path / "sequence.json",
        runner=runner,
    )

    assert report["status"] == "server_product_state_refresh_sequence_failed"
    assert report["summary"]["failed_required_step_count"] == 1
    assert report["summary"]["final_goal_status_attempted"] is False
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
    assert "build_goal_status" in skipped_names


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
        report_dir=tmp_path / "reports",
        runtime_monitor_dir=tmp_path / "runtime-monitor",
        env_file=tmp_path / "live-readonly.env",
        output_json=tmp_path / "sequence.json",
        runner=runner,
    )

    assert report["status"] == "server_product_state_refresh_sequence_failed"
    assert report["summary"]["failed_required_step_count"] == 1
    assert report["summary"]["final_goal_status_attempted"] is False
    assert report["summary"]["blocked_by_required_step"] == (
        "materialize_action_time_ticket"
    )
    assert calls[-1][1] == "scripts/materialize_action_time_ticket.py"
    skipped_names = [
        step["name"]
        for step in report["step_results"]
        if step["status"] == "skipped_after_required_failure"
    ]
    assert "build_readiness_pack_after_materialization" in skipped_names
    assert "build_goal_status" in skipped_names


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
        report_dir=tmp_path / "reports",
        runtime_monitor_dir=tmp_path / "runtime-monitor",
        env_file=tmp_path / "live-readonly.env",
        output_json=tmp_path / "sequence.json",
        runner=runner,
    )

    assert report["status"] == "server_product_state_refresh_sequence_failed"
    assert report["summary"]["failed_required_step_count"] == 1
    assert report["summary"]["final_goal_status_attempted"] is False
    assert report["summary"]["blocked_by_required_step"] == (
        "materialize_action_time_finalgate_preflight"
    )
    assert calls[-1][1] == "scripts/materialize_action_time_finalgate_preflight.py"
    skipped_names = [
        step["name"]
        for step in report["step_results"]
        if step["status"] == "skipped_after_required_failure"
    ]
    assert "build_readiness_pack_after_materialization" in skipped_names
    assert "build_goal_status" in skipped_names


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
        report_dir=tmp_path / "reports",
        runtime_monitor_dir=tmp_path / "runtime-monitor",
        env_file=tmp_path / "live-readonly.env",
        output_json=tmp_path / "sequence.json",
        runner=runner,
    )

    assert report["status"] == "server_product_state_refresh_sequence_failed"
    assert report["summary"]["failed_required_step_count"] == 1
    assert report["summary"]["final_goal_status_attempted"] is False
    assert report["summary"]["blocked_by_required_step"] == (
        "materialize_action_time_operation_layer_handoff"
    )
    assert calls[-1][1] == "scripts/materialize_action_time_operation_layer_handoff.py"
    skipped_names = [
        step["name"]
        for step in report["step_results"]
        if step["status"] == "skipped_after_required_failure"
    ]
    assert "build_readiness_pack_after_materialization" in skipped_names
    assert "build_goal_status" in skipped_names


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
        report_dir=tmp_path / "reports",
        runtime_monitor_dir=tmp_path / "runtime-monitor",
        env_file=tmp_path / "live-readonly.env",
        output_json=tmp_path / "sequence.json",
        runner=runner,
    )

    assert report["status"] == "server_product_state_refresh_sequence_failed"
    assert report["summary"]["failed_required_step_count"] == 1
    assert report["summary"]["final_goal_status_attempted"] is False
    assert report["summary"]["blocked_by_required_step"] == (
        "materialize_ticket_bound_runtime_safety_state"
    )
    assert calls[-1][1] == "scripts/materialize_ticket_bound_runtime_safety_state.py"
    skipped_names = [
        step["name"]
        for step in report["step_results"]
        if step["status"] == "skipped_after_required_failure"
    ]
    assert "build_readiness_pack_after_materialization" in skipped_names
    assert "build_goal_status" in skipped_names


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
        report_dir=tmp_path / "reports",
        runtime_monitor_dir=tmp_path / "runtime-monitor",
        env_file=tmp_path / "live-readonly.env",
        output_json=tmp_path / "sequence.json",
        runner=runner,
    )

    assert report["status"] == "server_product_state_refresh_sequence_failed"
    assert report["summary"]["failed_required_step_count"] == 1
    assert report["summary"]["final_goal_status_attempted"] is False
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
    assert "build_candidate_pool_after_materialization" in skipped_names
    assert "build_goal_status" in skipped_names


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
        report_dir=tmp_path / "reports",
        runtime_monitor_dir=tmp_path / "runtime-monitor",
        env_file=tmp_path / "live-readonly.env",
        output_json=tmp_path / "sequence.json",
        runner=runner,
    )

    assert report["status"] == "server_product_state_refresh_sequence_failed"
    assert report["summary"]["blocked_by_required_step"] == "build_account_safe_facts"
    assert report["summary"]["final_goal_status_attempted"] is False
    assert calls[-1][1] == "scripts/build_runtime_account_safe_facts.py"
    skipped_names = [
        step["name"]
        for step in report["step_results"]
        if step["status"] == "skipped_after_required_failure"
    ]
    assert "materialize_action_time_ticket" in skipped_names
    assert "build_goal_status" in skipped_names
