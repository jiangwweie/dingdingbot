from __future__ import annotations

import ast
import inspect
from pathlib import Path

from src.interfaces import api_trading_console
from scripts import run_server_product_state_refresh_sequence as refresh_sequence
from scripts import runtime_signal_watcher_resume_dispatcher as dispatcher


REPO_ROOT = Path(__file__).resolve().parents[2]

PRODUCTION_SYSTEMD_FILES = [
    "deploy/systemd/brc-runtime-signal-watcher.service",
    "deploy/systemd/brc-runtime-signal-watcher.timer",
    "deploy/systemd/brc-runtime-monitor.service",
    "deploy/systemd/brc-runtime-monitor.timer",
    "deploy/systemd/brc-runtime-signal-watcher.service.d/80-product-state-refresh.conf",
    "deploy/systemd/brc-runtime-signal-watcher.service.d/85-action-time-refresh-if-needed.conf",
    "deploy/systemd/brc-runtime-signal-watcher.service.d/90-resume-dispatcher-after-refresh.conf",
]

MATERIALIZER_CLI_SURFACES = {
    "src/application/action_time/fact_snapshots.py": {
        "--database-url",
        "--require-database-url",
        "--allow-non-postgres-for-test",
        "--now-ms",
        "--json",
    },
    "src/application/action_time/promotion_action_time_lane.py": {
        "--database-url",
        "--require-database-url",
        "--allow-non-postgres-for-test",
        "--now-ms",
        "--json",
    },
    "src/application/action_time/action_time_ticket.py": {
        "--database-url",
        "--require-database-url",
        "--allow-non-postgres-for-test",
        "--now-ms",
        "--json",
    },
    "src/application/action_time/finalgate_preflight.py": {
        "--database-url",
        "--require-database-url",
        "--ticket-id",
        "--now-ms",
        "--json",
        "--allow-non-postgres-for-test",
    },
    "src/application/action_time/operation_layer_handoff.py": {
        "--database-url",
        "--require-database-url",
        "--ticket-id",
        "--finalgate-pass-id",
        "--now-ms",
        "--json",
        "--allow-non-postgres-for-test",
    },
    "src/application/action_time/runtime_safety_state.py": {
        "--database-url",
        "--require-database-url",
        "--ticket-id",
        "--operation-layer-handoff-id",
        "--now-ms",
        "--json",
        "--allow-non-postgres-for-test",
    },
    "src/application/action_time/protected_submit_attempt.py": {
        "--database-url",
        "--require-database-url",
        "--ticket-id",
        "--operation-submit-command-id",
        "--submit-mode",
        "--now-ms",
        "--json",
        "--allow-non-postgres-for-test",
    },
    "src/application/action_time/post_submit_closure.py": {
        "--database-url",
        "--require-database-url",
        "--protected-submit-attempt-id",
        "--latest-submitted",
        "--now-ms",
        "--json",
        "--allow-non-postgres-for-test",
    },
}

ACTION_TIME_SCRIPT_WRAPPERS = {
    "scripts/build_runtime_account_safe_facts.py": "src.application.action_time.account_safe_facts",
    "scripts/materialize_action_time_fact_snapshots.py": "src.application.action_time.fact_snapshots",
    "scripts/materialize_pg_promotion_action_time_lane.py": "src.application.action_time.promotion_action_time_lane",
    "scripts/materialize_action_time_ticket.py": "src.application.action_time.action_time_ticket",
    "scripts/materialize_action_time_finalgate_preflight.py": "src.application.action_time.finalgate_preflight",
    "scripts/materialize_action_time_operation_layer_handoff.py": "src.application.action_time.operation_layer_handoff",
    "scripts/materialize_ticket_bound_runtime_safety_state.py": "src.application.action_time.runtime_safety_state",
    "scripts/materialize_ticket_bound_protected_submit_attempt.py": "src.application.action_time.protected_submit_attempt",
    "scripts/materialize_ticket_bound_post_submit_closure.py": "src.application.action_time.post_submit_closure",
}

FORBIDDEN_LOOSE_OR_FILE_ARGS = {
    "--authorization-id",
    "--prepared-authorization-id",
    "--signal-input-json",
    "--strategy-group-id",
    "--strategy-family-id",
    "--symbol",
    "--side",
    "--candidate-pool-json",
    "--daily-table-json",
    "--goal-status-json",
    "--runtime-active-monitor-json",
    "--live-facts-json",
    "--resume-pack-json",
    "--output-json",
    "--report-dir",
    "--runtime-monitor-dir",
}

FORBIDDEN_PRODUCTION_FILE_AUTHORITY_ARGS = (
    FORBIDDEN_LOOSE_OR_FILE_ARGS - {"--strategy-family-id"}
)

REMOVED_RUNTIME_ARTIFACT_BUILDERS = {
    "build_runtime_signal_watcher_readiness_pack.py",
    "build_strategy_live_candidate_pool.py",
    "build_daily_live_enablement_table.py",
    "build_single_lane_task_packet.py",
    "build_strategygroup_runtime_goal_status.py",
    "build_strategy_fresh_signal_action_time_boundary.py",
    "refresh_strategygroup_runtime_product_state_artifacts.py",
    "materialize_candidate_pool_action_time_lane.py",
}


def test_l2_l7_owner_api_surface_is_ticket_bound_only() -> None:
    api_surface = {
        "finalgate": (
            api_trading_console.runtime_action_time_finalgate_preflight_for_ticket,
            ["ticket_id"],
        ),
        "operation_layer": (
            api_trading_console.runtime_operation_layer_handoff_for_ticket,
            ["ticket_id", "finalgate_pass_id"],
        ),
        "protected_submit": (
            api_trading_console.runtime_ticket_bound_protected_submit_for_ticket,
            ["ticket_id", "operation_submit_command_id", "submit_mode"],
        ),
        "post_submit_closure": (
            api_trading_console.runtime_ticket_bound_post_submit_closure_for_attempt,
            ["protected_submit_attempt_id"],
        ),
    }
    forbidden_names = {
        "authorization_id",
        "prepared_authorization_id",
        "signal_input_json",
        "candidate_pool_json",
        "daily_table_json",
        "goal_status_json",
        "strategy_group_id",
        "symbol",
        "side",
    }

    for _layer, (handler, expected_params) in api_surface.items():
        signature = inspect.signature(handler)
        actual_params = list(signature.parameters)

        assert actual_params == expected_params
        assert not forbidden_names.intersection(actual_params)


def test_l2_l7_materializer_cli_surfaces_do_not_accept_json_or_loose_identity() -> None:
    for rel_path, expected_args in MATERIALIZER_CLI_SURFACES.items():
        source = (REPO_ROOT / rel_path).read_text(encoding="utf-8")
        args = _parser_args(source)

        assert args == expected_args
        assert not FORBIDDEN_LOOSE_OR_FILE_ARGS.intersection(args)


def test_action_time_materializer_scripts_are_thin_application_wrappers() -> None:
    for rel_path, module_name in ACTION_TIME_SCRIPT_WRAPPERS.items():
        source = (REPO_ROOT / rel_path).read_text(encoding="utf-8")

        assert module_name in source
        assert "argparse.ArgumentParser" not in source
        assert "sqlalchemy" not in source
        assert "PgBackedRuntimeControlStateRepository" not in source


def test_l2_l7_production_systemd_has_no_legacy_file_authority_or_builders() -> None:
    for rel_path in PRODUCTION_SYSTEMD_FILES:
        text = (REPO_ROOT / rel_path).read_text(encoding="utf-8")

        for forbidden_arg in FORBIDDEN_PRODUCTION_FILE_AUTHORITY_ARGS:
            assert forbidden_arg not in text, rel_path
        for builder in REMOVED_RUNTIME_ARTIFACT_BUILDERS:
            assert builder not in text, rel_path
        assert "output/runtime-monitor/latest-" not in text
        assert "/home/ubuntu/brc-deploy/reports/runtime-signal-watcher" not in text

    watcher_service = (
        REPO_ROOT / "deploy/systemd/brc-runtime-signal-watcher.service"
    ).read_text(encoding="utf-8")
    for strategy_group_id in {
        "BRF2-001",
        "CPM-RO-001",
        "MI-001",
        "MPG-001",
        "SOR-001",
    }:
        assert f"--strategy-family-id {strategy_group_id}" in watcher_service


def test_l2_l7_refresh_sequence_preserves_state_machine_order_and_light_tick() -> None:
    action_time_steps = [
        step.name
        for step in refresh_sequence._refresh_steps(
            python="python",
            api_base="http://127.0.0.1:18080",
            env_file=Path("/tmp/live-readonly.env"),
            mode="action_time",
        )
    ]

    assert action_time_steps == [
        "build_account_safe_facts",
        "materialize_action_time_fact_snapshots",
        "publish_runtime_control_current_projections_before_lane",
        "materialize_pg_promotion_action_time_lane",
        "materialize_action_time_ticket",
        "materialize_action_time_finalgate_preflight",
        "materialize_action_time_operation_layer_handoff",
        "materialize_ticket_bound_runtime_safety_state",
        "materialize_ticket_bound_protected_submit_attempt",
        "publish_runtime_control_current_projections_after_action_time",
    ]
    assert "materialize_ticket_bound_post_submit_closure" not in action_time_steps

    watcher_tick_steps = [
        step.name
        for step in refresh_sequence._refresh_steps(
            python="python",
            api_base="http://127.0.0.1:18080",
            env_file=Path("/tmp/live-readonly.env"),
            mode="watcher_tick_summary",
        )
    ]
    assert watcher_tick_steps == [
        "publish_runtime_control_current_projections_after_action_time",
    ]


def test_l2_l7_action_time_if_needed_does_not_run_heavy_steps_without_pg_trigger() -> None:
    calls: list[tuple[str, ...]] = []

    report = refresh_sequence.run_server_product_state_refresh_sequence(
        python="python",
        api_base="http://127.0.0.1:18080",
        env_file=Path("/tmp/live-readonly.env"),
        mode="action_time_if_needed",
        action_time_trigger_state={
            "status": "not_triggered",
            "triggered": False,
            "blocker": "",
            "counts": {
                "fresh_live_signal_events": 0,
                "open_promotion_candidates": 0,
                "stale_open_promotion_candidates": 0,
                "open_action_time_lane_inputs": 0,
                "stale_open_action_time_lane_inputs": 0,
                "open_action_time_tickets": 0,
                "stale_open_action_time_tickets": 0,
                "operation_layer_handoffs_ready_without_protected_submit": 0,
            },
        },
        runner=lambda command: (
            calls.append(command)
            or refresh_sequence.CommandResult(returncode=0, stdout="ok", stderr="")
        ),
    )

    assert report["status"] == "server_product_state_refresh_sequence_ready"
    assert report["effective_mode"] == "none"
    assert report["summary"]["step_count"] == 0
    assert report["summary"]["current_projection_publish_attempted"] is False
    assert report["summary"]["current_projection_publish_suppressed"] is True
    assert calls == []
    assert report["safety_invariants"] == refresh_sequence._empty_safety_invariants()


def test_l2_l7_production_systemd_keeps_broad_watcher_non_submit_authority() -> None:
    watcher_service = (
        REPO_ROOT / "deploy/systemd/brc-runtime-signal-watcher.service"
    ).read_text(encoding="utf-8")
    dispatcher_dropin = (
        REPO_ROOT
        / "deploy/systemd/brc-runtime-signal-watcher.service.d/90-resume-dispatcher-after-refresh.conf"
    ).read_text(encoding="utf-8")
    action_time_dropin = (
        REPO_ROOT
        / "deploy/systemd/brc-runtime-signal-watcher.service.d/85-action-time-refresh-if-needed.conf"
    ).read_text(encoding="utf-8")

    assert "--identity-source pg_ticket" in dispatcher_dropin
    assert "--execute-preflight" in dispatcher_dropin
    assert "--execute-operation-layer-submit" not in dispatcher_dropin
    assert "--operation-layer-submit-mode real_gateway_action" not in dispatcher_dropin
    assert "--resume-pack-json" not in dispatcher_dropin
    assert "--output-json" not in dispatcher_dropin
    assert "--report-dir" not in watcher_service + dispatcher_dropin + action_time_dropin
    assert "--mode action_time_if_needed" in action_time_dropin


def test_l2_l7_resume_dispatcher_parser_has_only_pg_ticket_identity_source() -> None:
    parsed = dispatcher._parse_args([])

    assert parsed.identity_source == "pg_ticket"
    assert parsed.execute_operation_layer_submit is False
    assert parsed.operation_layer_submit_mode == dispatcher.OPERATION_LAYER_SUBMIT_MODE_REAL

    dispatcher_source = (
        REPO_ROOT / "scripts/runtime_signal_watcher_resume_dispatcher.py"
    ).read_text(encoding="utf-8")
    assert "choices=(\"pg_ticket\",)" in dispatcher_source
    assert "--resume-pack-json" not in _parser_args(dispatcher_source)
    assert "--output-json" not in _parser_args(dispatcher_source)


def test_owner_console_runtime_projection_reads_pg_snapshots_not_script_builders() -> None:
    source = (
        REPO_ROOT / "src/application/readmodels/trading_console.py"
    ).read_text(encoding="utf-8")

    assert "brc_control_read_model_snapshots" in source
    assert "build_strategy_live_candidate_pool_from_control_state" not in source
    assert "build_goal_status_artifact_from_control_state" not in source
    assert "from scripts.build_strategy_live_candidate_pool" not in source
    assert "from scripts.build_strategygroup_runtime_goal_status" not in source


def test_pg_current_projectors_use_application_readmodel_builders_not_script_builders() -> None:
    checked_paths = [
        "scripts/publish_runtime_control_current_projections.py",
        "scripts/run_tokyo_runtime_server_monitor.py",
        "src/application/readmodels/daily_live_enablement_table.py",
        "src/application/readmodels/strategy_live_candidate_pool.py",
        "src/application/readmodels/strategygroup_runtime_goal_status.py",
    ]

    for rel_path in checked_paths:
        source = (REPO_ROOT / rel_path).read_text(encoding="utf-8")

        assert "from scripts.build_strategy_live_candidate_pool" not in source, rel_path
        assert "from scripts.build_daily_live_enablement_table" not in source, rel_path
        assert "from scripts.build_strategygroup_runtime_goal_status" not in source, rel_path

    publisher = (
        REPO_ROOT / "scripts/publish_runtime_control_current_projections.py"
    ).read_text(encoding="utf-8")
    monitor = (REPO_ROOT / "scripts/run_tokyo_runtime_server_monitor.py").read_text(
        encoding="utf-8"
    )

    assert "from src.application.readmodels.strategy_live_candidate_pool" in publisher
    assert "from src.application.readmodels.daily_live_enablement_table" in publisher
    assert "from src.application.readmodels.strategygroup_runtime_goal_status" in publisher
    assert "from src.application.readmodels.strategy_live_candidate_pool" in monitor
    assert "from src.application.readmodels.strategygroup_runtime_goal_status" in monitor


def test_api_observation_cycle_uses_application_signal_input_helper_not_script() -> None:
    source = (REPO_ROOT / "src/interfaces/api_trading_console.py").read_text(
        encoding="utf-8"
    )

    assert "build_runtime_strategy_signal_input_artifact" not in source
    assert "from scripts import" not in source
    assert "from src.application.readmodels import runtime_strategy_signal_input" in source


def test_owner_console_status_readmodels_do_not_import_artifact_scripts() -> None:
    source = (REPO_ROOT / "src/application/readmodels/trading_console.py").read_text(
        encoding="utf-8"
    )

    assert "build_strategy_group_live_facts_readiness_artifact" not in source
    assert "build_strategygroup_runtime_pilot_status" not in source
    assert "from scripts import" not in source
    assert "from src.application.readmodels.strategy_group_live_facts_readiness" in source
    assert "from src.application.readmodels.strategygroup_runtime_pilot_status" in source


def test_l2_l7_current_sources_do_not_reintroduce_retired_authority_key() -> None:
    forbidden_key = "down" + "grade_mode"
    forbidden_word = "down" + "grade_to_observation"
    checked_roots = [
        REPO_ROOT / "scripts",
        REPO_ROOT / "src/application/readmodels",
        REPO_ROOT / "deploy/systemd",
        REPO_ROOT / "docs/current",
    ]
    skipped_suffixes = {".pyc", ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".gz"}

    for root in checked_roots:
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix in skipped_suffixes:
                continue
            rel_path = path.relative_to(REPO_ROOT).as_posix()
            text = path.read_text(encoding="utf-8", errors="ignore")
            assert forbidden_key not in text, rel_path
            assert forbidden_word not in text, rel_path


def test_ticket_bound_api_imports_application_action_time_services_not_scripts() -> None:
    source = (REPO_ROOT / "src/interfaces/api_trading_console.py").read_text(
        encoding="utf-8"
    )

    assert "from scripts.materialize_action_time_finalgate_preflight" not in source
    assert "from scripts.materialize_action_time_operation_layer_handoff" not in source
    assert "from scripts.materialize_ticket_bound_protected_submit_attempt" not in source
    assert "from scripts.materialize_ticket_bound_post_submit_closure" not in source
    assert "from src.application.action_time.finalgate_preflight" in source
    assert "from src.application.action_time.operation_layer_handoff" in source
    assert "from src.application.action_time.protected_submit_attempt" in source
    assert "from src.application.action_time.post_submit_closure" in source


def _parser_args(source: str) -> set[str]:
    tree = ast.parse(source)
    args: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "add_argument":
            continue
        if not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            args.add(first.value)
    return {arg for arg in args if arg.startswith("--")}
