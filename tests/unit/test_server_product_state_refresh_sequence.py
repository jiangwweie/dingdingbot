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


@pytest.fixture(autouse=True)
def _isolate_unit_process_dsn(monkeypatch):
    """Keep command-runner unit tests from inheriting a real PG endpoint.

    Production refresh persists its outcome through PG.  These tests replace
    the child command runner with an in-memory double, so inheriting a developer
    shell DSN would accidentally turn the unit boundary into a real connection.
    """

    monkeypatch.delenv("PG_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)


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


def _fresh_signal_trigger(
    *,
    now_ms: int = 1_783_438_000_000,
    strategy_group_id: str = "SOR-001",
    symbol: str = "ETHUSDT",
    side: str = "long",
    signal_event_id: str = "signal:SOR-001:ETHUSDT:long:unit",
) -> dict[str, object]:
    return {
        "status": "triggered",
        "triggered": True,
        "blocker": "",
        "now_ms": now_ms,
        "counts": {
            "fresh_live_signal_events": 1,
            "open_promotion_candidates": 0,
            "open_action_time_lane_inputs": 0,
            "open_action_time_tickets": 0,
            "operation_layer_handoffs_ready_without_protected_submit": 0,
        },
        "trigger_identity": {
            "strategy_group_id": strategy_group_id,
            "symbol": symbol,
            "side": side,
            "signal_event_id": signal_event_id,
        },
    }


def _unit_invocation_starter(*, signal_event_id: str, **_kwargs):
    return {
        "action_time_invocation_id": "action_time_invocation:unit",
        "signal_event_id": signal_event_id,
    }


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
        "scripts/materialize_action_time_ticket_sequence.py",
        "scripts/publish_runtime_control_current_projections.py",
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


def test_production_action_time_never_falls_back_to_stdout_without_invocation(
    tmp_path: Path,
) -> None:
    module = _load_module()
    trigger = {
        "status": "triggered",
        "triggered": True,
        "now_ms": 1_000_000,
        "counts": {"open_action_time_tickets": 1},
        "trigger_identity": {
            "strategy_group_id": "SOR-001",
            "symbol": "BTCUSDT",
            "side": "long",
            "ticket_id": "ticket:missing-invocation",
        },
    }

    report = module.run_server_product_state_refresh_sequence(
        python=sys.executable,
        env_file=tmp_path / "live-readonly.env",
        mode="action_time_if_needed",
        action_time_trigger_state=trigger,
    )

    assert report["status"] == "server_product_state_refresh_sequence_failed"
    assert report["action_time_trigger"]["blocker"] == (
        "action_time_typed_invocation_required"
    )
    assert report["step_results"][0]["command"] == []


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
    assert "scripts/materialize_ticket_bound_protected_submit_attempt.py" not in command_names
    assert "scripts/materialize_ticket_bound_post_submit_closure.py" not in command_names
    assert report["summary"]["current_projection_publish_attempted"] is True
    assert report["safety_invariants"]["calls_ticket_bound_finalgate_preflight"] is False
    assert report["safety_invariants"]["calls_ticket_bound_operation_layer_handoff"] is False
    assert report["safety_invariants"]["calls_ticket_bound_runtime_safety_state"] is False
    assert report["safety_invariants"]["calls_ticket_bound_protected_submit_attempt"] is False
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


def test_server_product_state_refresh_sequence_action_time_mode_continues_existing_ticket_only(
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
    assert "scripts/build_runtime_account_safe_facts.py" not in command_names
    assert "scripts/materialize_action_time_ticket_sequence.py" not in command_names
    assert "scripts/materialize_action_time_fact_snapshots.py" not in command_names
    assert "scripts/materialize_pg_promotion_action_time_lane.py" not in command_names
    assert "scripts/materialize_action_time_ticket.py" not in command_names
    assert "scripts/materialize_action_time_finalgate_preflight.py" in command_names
    assert "scripts/materialize_ticket_bound_runtime_safety_state.py" in command_names
    assert "scripts/materialize_ticket_bound_protected_submit_attempt.py" not in command_names
    assert "scripts/materialize_ticket_bound_post_submit_closure.py" not in command_names
    assert report["safety_invariants"]["calls_ticket_bound_finalgate_preflight"] is True
    assert report["safety_invariants"]["calls_atomic_action_time_ticket_sequence"] is False
    assert report["safety_invariants"]["calls_ticket_bound_protected_submit_attempt"] is False
    assert report["safety_invariants"]["calls_ticket_bound_post_submit_closure"] is False


def test_action_time_refresh_reports_step_and_total_latency_budget(tmp_path: Path):
    module = _load_module()
    durations = iter([100, 200, 300, 400])

    def runner(_command: tuple[str, ...]):
        return module.CommandResult(
            returncode=0,
            stdout="ok",
            stderr="",
            duration_ms=next(durations),
        )

    report = module.run_server_product_state_refresh_sequence(
        python=sys.executable,
        env_file=tmp_path / "live-readonly.env",
        mode="action_time",
        runner=runner,
    )

    assert report["summary"]["total_step_duration_ms"] == 1000
    assert report["summary"]["latency_budget_ms"] == 30_000
    assert report["summary"]["latency_budget_status"] == "within_budget"
    assert [row["duration_ms"] for row in report["step_results"]] == [
        100,
        200,
        300,
        400,
    ]


def test_action_time_deadline_prevents_later_ticket_and_handoff_steps(tmp_path: Path):
    module = _load_module()
    calls: list[str] = []
    durations = iter([1_000, 2_000])

    def runner(command: tuple[str, ...]):
        calls.append(command[1])
        return module.CommandResult(
            returncode=0,
            stdout="ok",
            stderr="",
            duration_ms=next(durations),
        )

    report = module.run_server_product_state_refresh_sequence(
        python=sys.executable,
        env_file=tmp_path / "live-readonly.env",
        mode="action_time_if_needed",
        action_time_trigger_state={
            **_fresh_signal_trigger(now_ms=1_000),
            "expiry_candidates_ms": [2_500],
        },
        action_time_invocation_starter=_unit_invocation_starter,
        runner=runner,
        process_outcome_writer=lambda _payload: None,
    )

    assert report["status"] == "server_product_state_refresh_sequence_business_blocked"
    assert report["summary"]["action_time_deadline_blocker"] == (
        "action_time_deadline_insufficient:materialize_action_time_finalgate_preflight"
    )
    assert calls == [
        "scripts/build_runtime_account_safe_facts.py",
        "scripts/materialize_action_time_ticket_sequence.py",
    ]
    assert report["safety_invariants"]["calls_ticket_bound_operation_layer_handoff"] is False


def test_action_time_refresh_conserves_required_step_timeout_with_lane_lineage(
    tmp_path: Path,
):
    module = _load_module()
    outcomes: list[dict[str, object]] = []

    def runner(command: tuple[str, ...]):
        if command[1] == "scripts/materialize_action_time_finalgate_preflight.py":
            return module.CommandResult(
                returncode=124,
                stdout="",
                stderr=(
                    "step_timeout_after_45s:"
                    "scripts/materialize_action_time_finalgate_preflight.py"
                ),
                duration_ms=45_001,
            )
        return module.CommandResult(
            returncode=0,
            stdout="ok",
            stderr="",
            duration_ms=100,
        )

    report = module.run_server_product_state_refresh_sequence(
        python=sys.executable,
        env_file=tmp_path / "live-readonly.env",
        mode="action_time_if_needed",
        action_time_trigger_state={
            "status": "triggered",
            "triggered": True,
            "now_ms": 1_783_843_277_585,
            "blocker": "",
            "counts": {"open_action_time_tickets": 1},
            "trigger_identity": {
                "strategy_group_id": "CPM-RO-001",
                "symbol": "SUIUSDT",
                "side": "long",
                "signal_event_id": "signal:3b3a9b3f2e47401c38f188701fcd4d66",
                "ticket_id": (
                    "ticket:999fe1c427c105bde3c1c8a2da833c6d"
                    "c8294a3dcb5ad030de39db9f35972331"
                ),
            },
        },
        runner=runner,
        process_outcome_writer=lambda payload: outcomes.append(dict(payload)),
    )

    assert report["status"] == "server_product_state_refresh_sequence_failed"
    assert outcomes == [
        {
            "process_name": "action_time_refresh_sequence",
            "scope_key": "lane:CPM-RO-001:SUIUSDT:long",
            "run_id": "action_time_refresh:1783843277585",
            "result_status": "action_time_refresh_sequence_failed",
            "blockers": [
                "materialize_action_time_finalgate_preflight_timeout"
            ],
            "started_at_ms": 1_783_843_277_585,
            "completed_at_ms": 1_783_843_322_586,
            "source_watermark": (
                "ticket:999fe1c427c105bde3c1c8a2da833c6d"
                "c8294a3dcb5ad030de39db9f35972331"
            ),
        }
    ]
    assert report["process_outcome"]["first_blocker"] == (
        "materialize_action_time_finalgate_preflight_timeout"
    )


def test_action_time_refresh_no_trigger_does_not_write_process_outcome(tmp_path: Path):
    module = _load_module()
    outcomes: list[dict[str, object]] = []

    report = module.run_server_product_state_refresh_sequence(
        python=sys.executable,
        env_file=tmp_path / "live-readonly.env",
        mode="action_time_if_needed",
        action_time_trigger_state={
            "status": "not_triggered",
            "triggered": False,
            "blocker": "",
            "counts": {},
        },
        runner=lambda command: module.CommandResult(
            returncode=0,
            stdout="ok",
            stderr="",
        ),
        process_outcome_writer=lambda payload: outcomes.append(dict(payload)),
    )

    assert report["effective_mode"] == "none"
    assert outcomes == []
    assert "process_outcome" not in report


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
                "operation_layer_handoffs_ready_without_protected_submit": 0,
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
    sequence_now_ms = 1_783_438_000_000

    def runner(command: tuple[str, ...]):
        calls.append(command)
        return module.CommandResult(returncode=0, stdout="ok", stderr="")

    report = module.run_server_product_state_refresh_sequence(
        python=sys.executable,
        env_file=tmp_path / "live-readonly.env",
        mode="action_time_if_needed",
        action_time_trigger_state=_fresh_signal_trigger(now_ms=sequence_now_ms),
        runner=runner,
        action_time_invocation_starter=_unit_invocation_starter,
    )

    command_names = [command[1] for command in calls]
    assert report["status"] == "server_product_state_refresh_sequence_ready"
    assert report["mode"] == "action_time_if_needed"
    assert report["effective_mode"] == "action_time"
    assert report["action_time_sequence_now_ms"] == sequence_now_ms
    assert "scripts/materialize_action_time_ticket_sequence.py" in command_names
    assert command_names.index(
        "scripts/materialize_action_time_ticket_sequence.py"
    ) < command_names.index("scripts/materialize_action_time_finalgate_preflight.py")
    assert "scripts/materialize_action_time_finalgate_preflight.py" in command_names
    assert "scripts/materialize_ticket_bound_runtime_safety_state.py" in command_names
    assert "scripts/materialize_ticket_bound_protected_submit_attempt.py" not in command_names
    assert "scripts/materialize_ticket_bound_post_submit_closure.py" not in command_names
    ticket_command = next(
        command
        for command in calls
        if command[1] == "scripts/materialize_action_time_ticket_sequence.py"
    )
    assert ticket_command[-3:-1] == (
        "--action-time-invocation-id",
        "action_time_invocation:unit",
    )
    assert ticket_command[-1] == "--json"


def test_action_time_refresh_binds_account_collection_to_triggered_invocation(
    tmp_path: Path,
):
    module = _load_module()
    calls: list[tuple[str, ...]] = []
    started: dict[str, object] = {}
    sequence_now_ms = 1_783_438_000_000

    def runner(command: tuple[str, ...]):
        calls.append(command)
        return module.CommandResult(returncode=0, stdout="ok", stderr="")

    def invocation_starter(*, signal_event_id: str, opened_at_ms: int, env):
        started.update(
            {
                "signal_event_id": signal_event_id,
                "opened_at_ms": opened_at_ms,
                "env": dict(env),
            }
        )
        return {
            "action_time_invocation_id": "action_time_invocation:unit",
            "signal_event_id": signal_event_id,
        }

    report = module.run_server_product_state_refresh_sequence(
        python=sys.executable,
        env_file=tmp_path / "live-readonly.env",
        mode="action_time_if_needed",
        action_time_trigger_state={
            "status": "triggered",
            "triggered": True,
            "blocker": "",
            "now_ms": sequence_now_ms,
            "counts": {
                "fresh_live_signal_events": 1,
                "open_promotion_candidates": 0,
                "open_action_time_lane_inputs": 0,
                "open_action_time_tickets": 0,
            },
            "trigger_identity": {
                "strategy_group_id": "SOR-001",
                "symbol": "ETHUSDT",
                "side": "long",
                "signal_event_id": "signal:SOR-001:ETHUSDT:long:unit",
            },
        },
        runner=runner,
        action_time_invocation_starter=invocation_starter,
    )

    account_command = next(
        command
        for command in calls
        if command[1] == "scripts/build_runtime_account_safe_facts.py"
    )
    assert report["status"] == "server_product_state_refresh_sequence_ready"
    assert report["action_time_invocation"]["action_time_invocation_id"] == (
        "action_time_invocation:unit"
    )
    assert started["signal_event_id"] == "signal:SOR-001:ETHUSDT:long:unit"
    assert started["opened_at_ms"] == sequence_now_ms
    assert account_command[-2:] == (
        "--action-time-invocation-id",
        "action_time_invocation:unit",
    )


def test_outer_refresh_preserves_zero_exit_ticket_business_block(
    tmp_path: Path,
):
    module = _load_module()
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]):
        calls.append(command)
        if command[1] == "scripts/materialize_action_time_ticket_sequence.py":
            return module.CommandResult(
                returncode=0,
                stdout=(
                    '{"status":"action_time_ticket_sequence_rolled_back",'
                    '"process_outcome":{"process_state":"business_blocked",'
                    '"business_state":"temporarily_unavailable",'
                    '"first_blocker":"unit_exact_ticket_blocker"}}'
                ),
                stderr="",
            )
        return module.CommandResult(returncode=0, stdout="ok", stderr="")

    report = module.run_server_product_state_refresh_sequence(
        python=sys.executable,
        env_file=tmp_path / "live-readonly.env",
        mode="action_time_if_needed",
        action_time_trigger_state={
            "status": "triggered",
            "triggered": True,
            "blocker": "",
            "now_ms": 1_783_438_000_000,
            "counts": {"fresh_live_signal_events": 1},
            "trigger_identity": {
                "strategy_group_id": "SOR-001",
                "symbol": "ETHUSDT",
                "side": "long",
                "signal_event_id": "signal:SOR-001:ETHUSDT:long:unit",
            },
        },
        action_time_invocation_starter=lambda **_kwargs: {
            "action_time_invocation_id": "action_time_invocation:unit",
            "signal_event_id": "signal:SOR-001:ETHUSDT:long:unit",
        },
        runner=runner,
    )

    command_names = [command[1] for command in calls]
    assert report["status"] == "server_product_state_refresh_sequence_business_blocked"
    assert report["summary"]["business_blocked_by_required_step"] == (
        "materialize_action_time_ticket_sequence"
    )
    assert report["summary"]["business_blocked_first_blocker"] == (
        "unit_exact_ticket_blocker"
    )
    assert "scripts/materialize_action_time_finalgate_preflight.py" not in command_names
    assert "scripts/materialize_action_time_operation_layer_handoff.py" not in command_names
    assert "scripts/materialize_ticket_bound_runtime_safety_state.py" not in command_names
    assert "scripts/publish_runtime_control_current_projections.py" in command_names


def test_server_product_state_refresh_sequence_uses_stage_local_time_after_invocation_opening(
    tmp_path: Path,
):
    module = _load_module()
    calls: list[tuple[str, ...]] = []
    sequence_now_ms = 1_783_438_101_132

    def runner(command: tuple[str, ...]):
        calls.append(command)
        return module.CommandResult(returncode=0, stdout="ok", stderr="")

    report = module.run_server_product_state_refresh_sequence(
        python=sys.executable,
        env_file=tmp_path / "live-readonly.env",
        mode="action_time_if_needed",
        action_time_trigger_state=_fresh_signal_trigger(now_ms=sequence_now_ms),
        runner=runner,
        action_time_invocation_starter=_unit_invocation_starter,
    )

    assert report["status"] == "server_product_state_refresh_sequence_ready"
    materializer_names = {
        "scripts/materialize_action_time_ticket_sequence.py",
        "scripts/materialize_action_time_finalgate_preflight.py",
        "scripts/materialize_action_time_operation_layer_handoff.py",
        "scripts/materialize_ticket_bound_runtime_safety_state.py",
    }
    materializer_calls = [
        command for command in calls if command[1] in materializer_names
    ]
    assert len(materializer_calls) == len(materializer_names)
    for command in materializer_calls:
        assert "--now-ms" not in command
    ticket_command = next(
        command
        for command in materializer_calls
        if command[1] == "scripts/materialize_action_time_ticket_sequence.py"
    )
    assert ticket_command[-3:-1] == (
        "--action-time-invocation-id",
        "action_time_invocation:unit",
    )
    assert ticket_command[-1] == "--json"
    assert all("--now-ms" not in command for command in calls)


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
    assert report["summary"]["blocked_required_stdout_tail"] == ""
    assert report["summary"]["blocked_required_stderr_tail"] == "missing_fact:PG_DATABASE_URL"
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
                "operation_layer_handoffs_ready_without_protected_submit": 0,
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
                "operation_layer_handoffs_ready_without_protected_submit": 0,
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
                "operation_layer_handoffs_ready_without_protected_submit": 0,
            }
    finally:
        engine.dispose()


def test_expire_stale_action_time_objects_closes_pg_current_rows():
    module = _load_module()
    engine = _action_time_trigger_engine()
    now_ms = 1_000_000
    try:
        with engine.begin() as conn:
            _insert_stale_open_action_time_trigger_rows(conn, now_ms=now_ms)

            expiry_counts = module._expire_stale_action_time_objects(
                conn,
                now_ms=now_ms,
            )
            counts = module._action_time_trigger_counts(conn, now_ms=now_ms)

            assert expiry_counts == {
                "expired_live_signal_events": 1,
                "expired_promotion_candidates": 1,
                "expired_action_time_lane_inputs": 1,
                "expired_action_time_tickets": 1,
                "expired_budget_reservations": 0,
            }
            assert counts == {
                "fresh_live_signal_events": 0,
                "open_promotion_candidates": 0,
                "stale_open_promotion_candidates": 0,
                "open_action_time_lane_inputs": 0,
                "stale_open_action_time_lane_inputs": 0,
                "open_action_time_tickets": 0,
                "stale_open_action_time_tickets": 0,
                "operation_layer_handoffs_ready_without_protected_submit": 0,
            }
            assert conn.execute(
                sa.text(
                    "SELECT status, freshness_state, invalidated_at_ms "
                    "FROM brc_live_signal_events"
                )
            ).first() == ("stale", "expired", now_ms)
            assert conn.execute(
                sa.text("SELECT status, closed_at_ms FROM brc_promotion_candidates")
            ).first() == ("expired", now_ms)
            assert conn.execute(
                sa.text("SELECT status, closed_at_ms FROM brc_action_time_lane_inputs")
            ).first() == ("expired", now_ms)
            assert conn.execute(
                sa.text("SELECT status FROM brc_action_time_tickets")
            ).scalar_one() == "expired"
            assert conn.execute(
                sa.text("SELECT status FROM brc_budget_reservations")
            ).scalar_one() == "consumed"
            assert conn.execute(
                sa.text(
                    "SELECT from_status, to_status, reason "
                    "FROM brc_budget_reservation_events"
                )
            ).first() is None
    finally:
        engine.dispose()


def test_action_time_trigger_counts_include_unattempted_handoff_ready():
    module = _load_module()
    engine = _action_time_trigger_engine()
    now_ms = 1_000_000
    try:
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO brc_action_time_tickets VALUES (
                        'ticket-1',
                        'finalgate_ready',
                        :expires_at_ms
                    )
                    """
                ),
                {"expires_at_ms": now_ms + 60_000},
            )
            conn.execute(
                sa.text(
                    """
                    INSERT INTO brc_operation_layer_handoffs VALUES (
                        'handoff-1',
                        'ticket-1',
                        'operation-submit-1',
                        'handoff_ready'
                    )
                    """
                )
            )
            counts = module._action_time_trigger_counts(conn, now_ms=now_ms)
            assert counts["open_action_time_tickets"] == 1
            assert counts["operation_layer_handoffs_ready_without_protected_submit"] == 1

            conn.execute(
                sa.text(
                    """
                    INSERT INTO brc_ticket_bound_protected_submit_attempts (
                        protected_submit_attempt_id,
                        operation_submit_command_id
                    ) VALUES ('protected-submit-1', 'operation-submit-1')
                    """
                )
            )
            counts = module._action_time_trigger_counts(conn, now_ms=now_ms)
            assert counts["operation_layer_handoffs_ready_without_protected_submit"] == 0
    finally:
        engine.dispose()


def test_action_time_trigger_counts_ignore_expired_handoff_ready_ticket():
    module = _load_module()
    engine = _action_time_trigger_engine()
    now_ms = 1_000_000
    try:
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO brc_action_time_tickets VALUES (
                        'ticket-expired',
                        'finalgate_ready',
                        :expires_at_ms
                    )
                    """
                ),
                {"expires_at_ms": now_ms - 1},
            )
            conn.execute(
                sa.text(
                    """
                    INSERT INTO brc_operation_layer_handoffs VALUES (
                        'handoff-expired',
                        'ticket-expired',
                        'operation-submit-expired',
                        'handoff_ready'
                    )
                    """
                )
            )

            counts = module._action_time_trigger_counts(conn, now_ms=now_ms)

    finally:
        engine.dispose()

    assert counts["operation_layer_handoffs_ready_without_protected_submit"] == 0


def test_action_time_continuation_identity_prefers_exact_open_ticket_lineage():
    module = _load_module()
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    now_ms = 1_000_000
    try:
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    """
                    CREATE TABLE brc_action_time_tickets (
                        ticket_id TEXT PRIMARY KEY,
                        action_time_lane_input_id TEXT,
                        promotion_candidate_id TEXT,
                        signal_event_id TEXT,
                        strategy_group_id TEXT,
                        symbol TEXT,
                        side TEXT,
                        status TEXT,
                        expires_at_ms INTEGER,
                        created_at_ms INTEGER
                    )
                    """
                )
            )
            conn.execute(
                sa.text(
                    """
                    INSERT INTO brc_action_time_tickets VALUES (
                        'ticket:exact', 'lane:exact', 'promotion:exact',
                        'signal:exact', 'CPM-RO-001', 'ETHUSDT', 'long',
                        'preflight_pending', :expires_at_ms, :created_at_ms
                    )
                    """
                ),
                {
                    "expires_at_ms": now_ms + 60_000,
                    "created_at_ms": now_ms - 1_000,
                },
            )

            identity = module._action_time_continuation_identity(conn, now_ms=now_ms)
    finally:
        engine.dispose()

    assert identity == {
        "strategy_group_id": "CPM-RO-001",
        "symbol": "ETHUSDT",
        "side": "long",
        "signal_event_id": "signal:exact",
        "promotion_candidate_id": "promotion:exact",
        "action_time_lane_input_id": "lane:exact",
        "ticket_id": "ticket:exact",
    }


def test_action_time_continuation_identity_fails_closed_for_multiple_tickets():
    module = _load_module()
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    now_ms = 1_000_000
    try:
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    """
                    CREATE TABLE brc_action_time_tickets (
                        ticket_id TEXT PRIMARY KEY,
                        action_time_lane_input_id TEXT,
                        promotion_candidate_id TEXT,
                        signal_event_id TEXT,
                        strategy_group_id TEXT,
                        symbol TEXT,
                        side TEXT,
                        status TEXT,
                        expires_at_ms INTEGER,
                        created_at_ms INTEGER
                    )
                    """
                )
            )
            for ticket_id, symbol in (("ticket:btc", "BTCUSDT"), ("ticket:eth", "ETHUSDT")):
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO brc_action_time_tickets VALUES (
                          :ticket_id, :lane_id, :promotion_id, :signal_id,
                          'SOR-001', :symbol, 'long', 'preflight_pending',
                          :expires_at_ms, :created_at_ms
                        )
                        """
                    ),
                    {
                        "ticket_id": ticket_id,
                        "lane_id": f"lane:{symbol}",
                        "promotion_id": f"promotion:{symbol}",
                        "signal_id": f"signal:{symbol}",
                        "symbol": symbol,
                        "expires_at_ms": now_ms + 60_000,
                        "created_at_ms": now_ms,
                    },
                )
            with pytest.raises(
                RuntimeError,
                match="multiple_current_action_time_ticket_continuations",
            ):
                module._action_time_continuation_identity(conn, now_ms=now_ms)
    finally:
        engine.dispose()


def test_refresh_outcome_rebinds_to_post_sequence_ticket_identity():
    module = _load_module()
    payload = {
        "process_name": "action_time_refresh_sequence",
        "scope_key": "lane:CPM-RO-001:ETHUSDT:long",
        "run_id": "action_time_refresh:1000000",
        "result_status": "action_time_refresh_sequence_failed",
        "blockers": ["materialize_action_time_finalgate_preflight_timeout"],
        "started_at_ms": 1_000_000,
        "completed_at_ms": 1_045_000,
        "source_watermark": "signal:before-ticket",
    }

    rebound = module._with_current_trigger_identity(
        payload,
        {
            "strategy_group_id": "CPM-RO-001",
            "symbol": "SUIUSDT",
            "side": "long",
            "signal_event_id": "signal:before-ticket",
            "action_time_lane_input_id": "lane:after-sequence",
            "ticket_id": "ticket:after-sequence",
        },
    )

    assert rebound["scope_key"] == "lane:CPM-RO-001:SUIUSDT:long"
    assert rebound["source_watermark"] == "ticket:after-sequence"


def test_refresh_failure_conserves_structured_blocker_without_raw_stderr():
    module = _load_module()
    report = {
        "summary": {
            "blocked_by_required_step": "materialize_action_time_ticket_sequence",
            "blocked_required_stdout_tail": (
                '{"process_outcome":{"first_blocker":'
                '"runtime_control_state_invalid:connection_lost"}}'
            ),
            "blocked_required_stderr_tail": "database_url=secret-value",
        }
    }

    blocker = module._refresh_step_failure_blocker(report)

    assert blocker == (
        "materialize_action_time_ticket_sequence_failed:"
        "runtime_control_state_invalid:connection_lost"
    )
    assert "secret-value" not in blocker


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
        "operation_layer_handoffs_ready_without_protected_submit": 0,
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
    assert "scripts/materialize_action_time_ticket_sequence.py" not in command_names
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


def test_server_product_state_refresh_sequence_bounds_each_subprocess(
    monkeypatch,
):
    module = _load_module()

    def timed_out(command, **kwargs):
        assert kwargs["timeout"] == module.DEFAULT_STEP_TIMEOUT_SECONDS
        raise module.subprocess.TimeoutExpired(
            command,
            kwargs["timeout"],
            output="partial",
        )

    monkeypatch.setattr(module.subprocess, "run", timed_out)

    result = module._run_command((sys.executable, "scripts/unit-step.py"))

    assert result.returncode == 124
    assert result.stdout == "partial"
    assert result.stderr == "step_timeout_after_45s:scripts/unit-step.py"


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
        mode="action_time_if_needed",
        action_time_trigger_state=_fresh_signal_trigger(),
        action_time_invocation_starter=_unit_invocation_starter,
        runner=runner,
    )

    assert report["status"] == "server_product_state_refresh_sequence_failed"
    assert report["summary"]["failed_required_step_count"] == 1
    assert report["summary"]["current_projection_publish_attempted"] is True
    assert report["summary"]["blocked_by_required_step"] == (
        "publish_runtime_control_current_projections_after_action_time"
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
            item.endswith("materialize_action_time_ticket_sequence.py")
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
        mode="action_time_if_needed",
        action_time_trigger_state=_fresh_signal_trigger(),
        action_time_invocation_starter=_unit_invocation_starter,
        runner=runner,
    )

    assert report["status"] == "server_product_state_refresh_sequence_failed"
    assert report["summary"]["failed_required_step_count"] == 1
    assert report["summary"]["current_projection_publish_attempted"] is False
    assert report["summary"]["blocked_by_required_step"] == (
        "materialize_action_time_ticket_sequence"
    )
    assert calls[-1][1] == "scripts/materialize_action_time_ticket_sequence.py"
    skipped_names = [
        step["name"]
        for step in report["step_results"]
        if step["status"] == "skipped_after_required_failure"
    ]
    assert "materialize_action_time_finalgate_preflight" in skipped_names
    assert "materialize_action_time_operation_layer_handoff" in skipped_names
    assert "materialize_ticket_bound_runtime_safety_state" in skipped_names


def test_action_time_ticket_sequence_uses_structured_json_for_exact_blocker(
    tmp_path: Path,
):
    module = _load_module()

    def runner(command: tuple[str, ...]):
        if command[1] == "scripts/materialize_action_time_ticket_sequence.py":
            assert "--json" in command
            return module.CommandResult(
                returncode=1,
                stdout=(
                    '{"status":"action_time_ticket_sequence_rolled_back",'
                    '"process_outcome":{"process_state":"hard_failure",'
                    '"business_state":"needs_intervention",'
                    '"first_blocker":"runtime_lane_identity_mismatch:coverage_typed_identity"}}'
                ),
                stderr="",
            )
        return module.CommandResult(returncode=0, stdout="ok", stderr="")

    report = module.run_server_product_state_refresh_sequence(
        python=sys.executable,
        env_file=tmp_path / "live-readonly.env",
        mode="action_time_if_needed",
        action_time_trigger_state=_fresh_signal_trigger(),
        action_time_invocation_starter=_unit_invocation_starter,
        runner=runner,
    )

    assert report["status"] == "server_product_state_refresh_sequence_failed"
    assert report["process_outcome"]["first_blocker"] == (
        "materialize_action_time_ticket_sequence_failed:"
        "runtime_lane_identity_mismatch:coverage_typed_identity"
    )


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
        mode="action_time_if_needed",
        action_time_trigger_state=_fresh_signal_trigger(),
        action_time_invocation_starter=_unit_invocation_starter,
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
            item.endswith("materialize_action_time_ticket_sequence.py")
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
        mode="action_time_if_needed",
        action_time_trigger_state=_fresh_signal_trigger(),
        action_time_invocation_starter=_unit_invocation_starter,
        runner=runner,
    )

    assert report["status"] == "server_product_state_refresh_sequence_failed"
    assert report["summary"]["failed_required_step_count"] == 1
    assert report["summary"]["current_projection_publish_attempted"] is False
    assert report["summary"]["blocked_by_required_step"] == (
        "materialize_action_time_ticket_sequence"
    )
    assert calls[-1][1] == "scripts/materialize_action_time_ticket_sequence.py"
    skipped_names = [
        step["name"]
        for step in report["step_results"]
        if step["status"] == "skipped_after_required_failure"
    ]
    assert "materialize_action_time_finalgate_preflight" in skipped_names
    assert "publish_runtime_control_current_projections_after_action_time" in skipped_names


def test_server_product_state_refresh_sequence_fails_closed_on_ticket_failure(
    tmp_path: Path,
):
    module = _load_module()
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]):
        calls.append(command)
        if any(
            item.endswith("materialize_action_time_ticket_sequence.py")
            for item in command
        ):
            return module.CommandResult(
                returncode=1,
                stdout="",
                stderr="action-time ticket materialization failed",
            )
        return module.CommandResult(returncode=0, stdout="ok", stderr="")

    report = module.run_server_product_state_refresh_sequence(
        python=sys.executable,
        env_file=tmp_path / "live-readonly.env",
        mode="action_time_if_needed",
        action_time_trigger_state=_fresh_signal_trigger(),
        action_time_invocation_starter=_unit_invocation_starter,
        runner=runner,
    )

    assert report["status"] == "server_product_state_refresh_sequence_failed"
    assert report["summary"]["failed_required_step_count"] == 1
    assert report["summary"]["current_projection_publish_attempted"] is False
    assert report["summary"]["blocked_by_required_step"] == (
        "materialize_action_time_ticket_sequence"
    )
    assert calls[-1][1] == "scripts/materialize_action_time_ticket_sequence.py"
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
        mode="action_time_if_needed",
        action_time_trigger_state=_fresh_signal_trigger(),
        action_time_invocation_starter=_unit_invocation_starter,
        runner=runner,
    )

    assert report["status"] == "server_product_state_refresh_sequence_failed"
    assert report["summary"]["failed_required_step_count"] == 1
    assert report["summary"]["current_projection_publish_attempted"] is False
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
        mode="action_time_if_needed",
        action_time_trigger_state=_fresh_signal_trigger(),
        action_time_invocation_starter=_unit_invocation_starter,
        runner=runner,
    )

    assert report["status"] == "server_product_state_refresh_sequence_failed"
    assert report["summary"]["failed_required_step_count"] == 1
    assert report["summary"]["current_projection_publish_attempted"] is False
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
        mode="action_time_if_needed",
        action_time_trigger_state=_fresh_signal_trigger(),
        action_time_invocation_starter=_unit_invocation_starter,
        runner=runner,
    )

    assert report["status"] == "server_product_state_refresh_sequence_failed"
    assert report["summary"]["failed_required_step_count"] == 1
    assert report["summary"]["current_projection_publish_attempted"] is False
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


def test_server_product_state_refresh_sequence_does_not_call_protected_submit_in_action_time(
    tmp_path: Path,
):
    module = _load_module()
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...]):
        calls.append(command)
        if any(
            item.endswith("materialize_ticket_bound_protected_submit_attempt.py")
            for item in command
        ):
            raise AssertionError("protected submit must be dispatcher-owned")
        return module.CommandResult(returncode=0, stdout="ok", stderr="")

    report = module.run_server_product_state_refresh_sequence(
        python=sys.executable,
        env_file=tmp_path / "live-readonly.env",
        mode="action_time_if_needed",
        action_time_trigger_state=_fresh_signal_trigger(),
        action_time_invocation_starter=_unit_invocation_starter,
        runner=runner,
    )

    assert report["status"] == "server_product_state_refresh_sequence_ready"
    assert report["summary"]["failed_required_step_count"] == 0
    assert report["summary"]["current_projection_publish_attempted"] is True
    assert all(
        command[1] != "scripts/materialize_ticket_bound_protected_submit_attempt.py"
        for command in calls
    )


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
        mode="action_time_if_needed",
        action_time_trigger_state=_fresh_signal_trigger(),
        action_time_invocation_starter=_unit_invocation_starter,
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
    assert "materialize_action_time_ticket_sequence" in skipped_names
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
        conn.execute(
            sa.text(
                """
                CREATE TABLE brc_operation_layer_handoffs (
                    operation_layer_handoff_id TEXT PRIMARY KEY,
                    ticket_id TEXT,
                    operation_submit_command_id TEXT,
                    status TEXT
                )
                """
            )
        )
        conn.execute(
            sa.text(
                """
                CREATE TABLE brc_ticket_bound_protected_submit_attempts (
                    protected_submit_attempt_id TEXT PRIMARY KEY,
                    ticket_id TEXT,
                    operation_submit_command_id TEXT
                    , exchange_write_called BOOLEAN
                )
                """
            )
        )
        conn.execute(
            sa.text(
                """
                CREATE TABLE brc_ticket_bound_exchange_commands (
                    ticket_id TEXT,
                    command_state TEXT,
                    dispatch_started_at_ms INTEGER,
                    exchange_order_id TEXT
                )
                """
            )
        )
        conn.execute(
            sa.text(
                """
                CREATE TABLE brc_account_exposure_current (
                    owner_ticket_id TEXT,
                    position_slot_claimed BOOLEAN
                )
                """
            )
        )
        conn.execute(
            sa.text(
                """
                CREATE TABLE brc_budget_reservations (
                    budget_reservation_id TEXT PRIMARY KEY,
                    ticket_id TEXT,
                    status TEXT,
                    release_reason TEXT,
                    expires_at_ms INTEGER
                )
                """
            )
        )
        conn.execute(
            sa.text(
                """
                CREATE TABLE brc_budget_reservation_events (
                    budget_reservation_event_id TEXT PRIMARY KEY,
                    budget_reservation_id TEXT,
                    from_status TEXT,
                    to_status TEXT,
                    reason TEXT,
                    evidence_ref TEXT,
                    created_at_ms INTEGER
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
            INSERT INTO brc_budget_reservations VALUES (
                'stale-open-budget', 'stale-open-ticket', 'consumed', NULL, :expires_at_ms
            )
            """,
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
