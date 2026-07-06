#!/usr/bin/env python3
"""Run the server-side product-state refresh sequence after watcher ticks.

The sequence is non-authority from a trading perspective. It refreshes control
read models, may materialize PG fresh signals into one action-time lane,
may materialize a PG Action-Time Ticket when a PG real-submit lane is present,
and may run the ticket-bound non-executing FinalGate preflight and Operation
Layer handoff, then materialize PG Runtime Safety State and ticket-bound
post-submit closure state. It does not call
Operation Layer submit, exchange write APIs, OrderLifecycle, withdrawals,
transfers, credential mutation, live profile changes, or order sizing changes.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable

import sqlalchemy as sa


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.pg_dsn import normalize_sync_postgres_dsn  # noqa: E402

DEFAULT_PYTHON = "/home/ubuntu/brc-deploy/venvs/brc-bnb-prelive-20260601/bin/python"
DEFAULT_API_BASE = "http://127.0.0.1:18080"
DEFAULT_REPORT_DIR = Path("/home/ubuntu/brc-deploy/reports/runtime-signal-watcher")
DEFAULT_RUNTIME_MONITOR_DIR = Path("/home/ubuntu/brc-deploy/reports/runtime-monitor")
DEFAULT_ENV_FILE = Path("/home/ubuntu/brc-deploy/env/live-readonly.env")
DEFAULT_OUTPUT_JSON = DEFAULT_REPORT_DIR / "server-product-state-refresh-sequence.json"
REFRESH_MODES = {
    "watcher_tick_summary",
    "action_time_if_needed",
    "control_refresh",
    "action_time",
    "closure",
    "diagnostic_full",
}


@dataclass(frozen=True)
class RefreshStep:
    name: str
    command: tuple[str, ...]
    required: bool = True


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


Runner = Callable[[tuple[str, ...]], CommandResult]


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    report = run_server_product_state_refresh_sequence(
        python=args.python,
        api_base=args.api_base,
        report_dir=Path(args.report_dir),
        runtime_monitor_dir=Path(args.runtime_monitor_dir),
        env_file=Path(args.env_file),
        output_json=Path(args.output_json),
        mode=args.mode,
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "failed_required_step_count": report["summary"][
                    "failed_required_step_count"
                ],
                "failed_optional_step_count": report["summary"][
                    "failed_optional_step_count"
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if report["status"] == "server_product_state_refresh_sequence_ready" else 1


def run_server_product_state_refresh_sequence(
    *,
    python: str = DEFAULT_PYTHON,
    api_base: str = DEFAULT_API_BASE,
    report_dir: Path = DEFAULT_REPORT_DIR,
    runtime_monitor_dir: Path = DEFAULT_RUNTIME_MONITOR_DIR,
    env_file: Path = DEFAULT_ENV_FILE,
    output_json: Path = DEFAULT_OUTPUT_JSON,
    mode: str = "diagnostic_full",
    runner: Runner | None = None,
    action_time_trigger_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if mode not in REFRESH_MODES:
        raise ValueError(f"unsupported refresh mode: {mode}")
    command_env = _command_env_with_sync_pg_dsn(os.environ)
    command_runner = runner or (lambda command: _run_command(command, env=command_env))
    started = datetime.now(timezone.utc).isoformat()
    effective_mode = mode
    trigger_state: dict[str, Any] | None = None
    if mode == "action_time_if_needed":
        trigger_state = (
            action_time_trigger_state
            if action_time_trigger_state is not None
            else _action_time_trigger_state(command_env)
        )
        if trigger_state.get("status") == "blocked":
            report = _empty_refresh_report(
                mode=mode,
                effective_mode="none",
                started_at_utc=started,
                status="server_product_state_refresh_sequence_failed",
                action_time_trigger=trigger_state,
            )
            _write_json(output_json, report)
            return report
        if trigger_state.get("triggered") is not True:
            report = _empty_refresh_report(
                mode=mode,
                effective_mode="none",
                started_at_utc=started,
                status="server_product_state_refresh_sequence_ready",
                action_time_trigger=trigger_state,
            )
            _write_json(output_json, report)
            return report
        effective_mode = "action_time"
    steps = _refresh_steps(
        python=python,
        api_base=api_base,
        report_dir=report_dir,
        runtime_monitor_dir=runtime_monitor_dir,
        env_file=env_file,
        mode=effective_mode,
    )
    step_results: list[dict[str, Any]] = []
    blocked_by_required_failure = ""
    for step in steps:
        if blocked_by_required_failure:
            step_results.append(
                {
                    "name": step.name,
                    "required": step.required,
                    "returncode": None,
                    "status": "skipped_after_required_failure",
                    "blocked_by": blocked_by_required_failure,
                    "command": list(step.command),
                    "stdout_tail": "",
                    "stderr_tail": "",
                }
            )
            continue
        result = command_runner(step.command)
        step_results.append(
            {
                "name": step.name,
                "required": step.required,
                "returncode": result.returncode,
                "status": "passed" if result.returncode == 0 else "failed",
                "command": list(step.command),
                "stdout_tail": _tail(result.stdout),
                "stderr_tail": _tail(result.stderr),
            }
        )
        if step.required and result.returncode != 0:
            blocked_by_required_failure = step.name

    failed_required = [
        result
        for result in step_results
        if result["required"]
        and result["returncode"] is not None
        and result["returncode"] != 0
    ]
    failed_optional = [
        result
        for result in step_results
        if not result["required"]
        and result["returncode"] is not None
        and result["returncode"] != 0
    ]
    skipped = [
        result
        for result in step_results
        if result["status"] == "skipped_after_required_failure"
    ]
    goal_status_attempted = any(
        result["name"] == "build_goal_status" and result["returncode"] is not None
        for result in step_results
    )
    attempted_step_names = {
        str(result["name"])
        for result in step_results
        if result["returncode"] is not None
    }
    report = {
        "schema": "brc.server_product_state_refresh_sequence.v1",
        "scope": "server_product_state_refresh_sequence_non_authority",
        "status": (
            "server_product_state_refresh_sequence_ready"
            if not failed_required
            else "server_product_state_refresh_sequence_failed"
        ),
        "mode": mode,
        "effective_mode": effective_mode,
        "action_time_trigger": trigger_state,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "started_at_utc": started,
        "summary": {
            "step_count": len(step_results),
            "required_step_count": sum(1 for step in steps if step.required),
            "optional_step_count": sum(1 for step in steps if not step.required),
            "failed_required_step_count": len(failed_required),
            "failed_optional_step_count": len(failed_optional),
            "skipped_after_required_failure_count": len(skipped),
            "final_goal_status_attempted": goal_status_attempted,
            "final_goal_status_suppressed": not goal_status_attempted,
            "blocked_by_required_step": blocked_by_required_failure,
        },
        "step_results": step_results,
        "safety_invariants": {
            "calls_finalgate": False,
            "calls_ticket_bound_finalgate_preflight": (
                "materialize_action_time_finalgate_preflight"
                in attempted_step_names
            ),
            "calls_ticket_bound_operation_layer_handoff": (
                "materialize_action_time_operation_layer_handoff"
                in attempted_step_names
            ),
            "calls_ticket_bound_runtime_safety_state": (
                "materialize_ticket_bound_runtime_safety_state"
                in attempted_step_names
            ),
            "calls_ticket_bound_post_submit_closure": (
                "materialize_ticket_bound_post_submit_closure"
                in attempted_step_names
            ),
            "calls_operation_layer_submit": False,
            "calls_exchange_write": False,
            "places_order": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "withdrawal_or_transfer_created": False,
            "credential_or_secret_mutation": False,
            "live_profile_changed": False,
            "order_sizing_changed": False,
        },
    }
    _write_json(output_json, report)
    return report


def _empty_refresh_report(
    *,
    mode: str,
    effective_mode: str,
    started_at_utc: str,
    status: str,
    action_time_trigger: dict[str, Any],
) -> dict[str, Any]:
    failed = not status.endswith("_ready")
    step_results = (
        [
            {
                "name": "pg_action_time_trigger_state",
                "required": True,
                "returncode": 1,
                "status": "failed",
                "command": [],
                "stdout_tail": "",
                "stderr_tail": str(action_time_trigger.get("blocker") or ""),
            }
        ]
        if failed
        else []
    )
    return {
        "schema": "brc.server_product_state_refresh_sequence.v1",
        "scope": "server_product_state_refresh_sequence_non_authority",
        "status": status,
        "mode": mode,
        "effective_mode": effective_mode,
        "action_time_trigger": action_time_trigger,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "started_at_utc": started_at_utc,
        "summary": {
            "step_count": len(step_results),
            "required_step_count": len(step_results),
            "optional_step_count": 0,
            "failed_required_step_count": len(step_results),
            "failed_optional_step_count": 0,
            "skipped_after_required_failure_count": 0,
            "final_goal_status_attempted": False,
            "final_goal_status_suppressed": True,
            "blocked_by_required_step": (
                "pg_action_time_trigger_state"
                if failed
                else ""
            ),
        },
        "step_results": step_results,
        "safety_invariants": _empty_safety_invariants(),
    }


def _empty_safety_invariants() -> dict[str, bool]:
    return {
        "calls_finalgate": False,
        "calls_ticket_bound_finalgate_preflight": False,
        "calls_ticket_bound_operation_layer_handoff": False,
        "calls_ticket_bound_runtime_safety_state": False,
        "calls_ticket_bound_post_submit_closure": False,
        "calls_operation_layer_submit": False,
        "calls_exchange_write": False,
        "places_order": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "withdrawal_or_transfer_created": False,
        "credential_or_secret_mutation": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
    }


def _action_time_trigger_state(env: Mapping[str, str]) -> dict[str, Any]:
    database_url = normalize_sync_postgres_dsn(
        env.get("PG_DATABASE_URL") or env.get("DATABASE_URL") or ""
    )
    if not database_url:
        return {
            "status": "blocked",
            "triggered": False,
            "blocker": "missing_fact:PG_DATABASE_URL",
            "counts": {},
        }
    engine = sa.create_engine(database_url)
    try:
        with engine.connect() as conn:
            counts = _action_time_trigger_counts(conn)
    except Exception as exc:  # noqa: BLE001 - fail closed on PG current read errors.
        return {
            "status": "blocked",
            "triggered": False,
            "blocker": f"pg_action_time_trigger_read_failed:{type(exc).__name__}",
            "counts": {},
        }
    finally:
        engine.dispose()
    triggered = any(count > 0 for count in counts.values())
    return {
        "status": "triggered" if triggered else "not_triggered",
        "triggered": triggered,
        "blocker": "",
        "counts": counts,
    }


def _action_time_trigger_counts(conn: sa.engine.Connection) -> dict[str, int]:
    metadata = sa.MetaData()
    live_signals = sa.Table("brc_live_signal_events", metadata, autoload_with=conn)
    promotions = sa.Table("brc_promotion_candidates", metadata, autoload_with=conn)
    lanes = sa.Table("brc_action_time_lane_inputs", metadata, autoload_with=conn)
    tickets = sa.Table("brc_action_time_tickets", metadata, autoload_with=conn)
    return {
        "fresh_live_signal_events": _count_where(
            conn,
            live_signals,
            sa.and_(
                live_signals.c.freshness_state == "fresh",
                live_signals.c.status == "facts_validated",
            ),
        ),
        "open_promotion_candidates": _count_where(
            conn,
            promotions,
            promotions.c.status.in_(
                [
                    "eligible",
                    "arbitration_pending",
                    "arbitration_won",
                ]
            ),
        ),
        "open_action_time_lane_inputs": _count_where(
            conn,
            lanes,
            sa.and_(
                lanes.c.lane_scope == "real_submit_candidate",
                lanes.c.status.in_(
                    [
                        "opened",
                        "facts_refreshing",
                        "ticket_pending",
                        "ticket_created",
                    ]
                ),
            ),
        ),
        "open_action_time_tickets": _count_where(
            conn,
            tickets,
            tickets.c.status.in_(
                [
                    "created",
                    "preflight_pending",
                    "finalgate_ready",
                ]
            ),
        ),
    }


def _count_where(
    conn: sa.engine.Connection,
    table: sa.Table,
    predicate: Any,
) -> int:
    return int(
        conn.execute(sa.select(sa.func.count()).select_from(table).where(predicate))
        .scalar_one()
        or 0
    )


def _refresh_steps(
    *,
    python: str,
    api_base: str,
    report_dir: Path,
    runtime_monitor_dir: Path,
    env_file: Path,
    mode: str,
) -> list[RefreshStep]:
    status = report_dir / "latest-status.json"
    public = runtime_monitor_dir / "latest-binance-usdm-public-facts.json"
    public_md = runtime_monitor_dir / "latest-binance-usdm-public-facts.md"
    account = runtime_monitor_dir / "latest-account-safe-facts.json"
    goal = report_dir / "strategygroup-runtime-goal-status.json"
    candidate_pool = runtime_monitor_dir / "latest-strategy-live-candidate-pool.json"
    candidate_pool_md = runtime_monitor_dir / "latest-strategy-live-candidate-pool.md"
    daily_table = runtime_monitor_dir / "latest-daily-live-enablement-table.json"
    daily_table_md = runtime_monitor_dir / "latest-daily-live-enablement-table.md"
    single_lane = runtime_monitor_dir / "latest-single-lane-task-packet.json"
    single_lane_md = runtime_monitor_dir / "latest-single-lane-task-packet.md"
    action_time_boundary = (
        runtime_monitor_dir / "latest-strategy-fresh-signal-action-time-boundary.json"
    )
    action_time_boundary_md = (
        runtime_monitor_dir / "latest-strategy-fresh-signal-action-time-boundary.md"
    )
    sor_detector_dir = runtime_monitor_dir
    mi_trial = runtime_monitor_dir / "latest-mi-trial-admission-decision.json"
    mi_trial_md = runtime_monitor_dir / "latest-mi-trial-admission-decision.md"
    brf2_facts = runtime_monitor_dir / "latest-brf2-runtime-signal-facts.json"
    brf2_facts_md = runtime_monitor_dir / "latest-brf2-runtime-signal-facts.md"
    release_manifest = Path("/home/ubuntu/brc-deploy/app/current/.brc-release-manifest.json")

    pg_required = ("--require-database-url",)
    action_time_boundary_inputs = (
        *pg_required,
        "--output-json",
        str(action_time_boundary),
        "--output-owner-progress",
        str(action_time_boundary_md),
    )

    steps = [
        RefreshStep(
            "fetch_public_facts",
            (
                python,
                "scripts/fetch_binance_usdm_public_facts.py",
                "--symbols",
                "BTCUSDT",
                "ETHUSDT",
                "SOLUSDT",
                "AVAXUSDT",
                "SUIUSDT",
                "OPUSDT",
                *pg_required,
                "--output-json",
                str(public),
                "--output-owner-progress",
                str(public_md),
            ),
        ),
        RefreshStep(
            "build_sor_detector",
            (
                python,
                "scripts/build_sor_session_scope_detector.py",
                *pg_required,
                "--output-dir",
                str(sor_detector_dir),
            ),
        ),
        RefreshStep(
            "build_action_time_boundary_public",
            (
                python,
                "scripts/build_strategy_fresh_signal_action_time_boundary.py",
                *action_time_boundary_inputs,
            ),
        ),
        RefreshStep(
            "build_mi_trial_admission",
            (
                python,
                "scripts/build_mi_trial_admission_decision.py",
                "--replay-json",
                str(runtime_monitor_dir / "latest-four-candidate-recent-live-submit-replay.json"),
                *pg_required,
                "--output-json",
                str(mi_trial),
                "--output-owner-progress",
                str(mi_trial_md),
            ),
        ),
        RefreshStep(
            "build_brf2_runtime_signal_facts",
            (
                python,
                "scripts/build_brf2_runtime_signal_facts.py",
                "--strategy-source",
                "live_market",
                *pg_required,
                "--output-json",
                str(brf2_facts),
                "--output-owner-progress",
                str(brf2_facts_md),
            ),
        ),
        RefreshStep("validate_runtime_coverage", (python, "scripts/validate_runtime_candidate_universe_coverage.py", str(status))),
        RefreshStep(
            "build_candidate_pool",
            (
                python,
                "scripts/build_strategy_live_candidate_pool.py",
                *pg_required,
                "--output-json",
                str(candidate_pool),
                "--output-owner-progress",
                str(candidate_pool_md),
            ),
        ),
        RefreshStep("validate_candidate_pool", (python, "scripts/validate_strategy_live_candidate_pool.py", str(candidate_pool))),
        RefreshStep(
            "build_daily_table",
            (
                python,
                "scripts/build_daily_live_enablement_table.py",
                *pg_required,
                "--output-json",
                str(daily_table),
                "--output-owner-progress",
                str(daily_table_md),
            ),
        ),
        RefreshStep("validate_daily_table", (python, "scripts/validate_daily_live_enablement_table.py", str(daily_table))),
        RefreshStep(
            "build_single_lane_task_packet",
            (
                python,
                "scripts/build_single_lane_task_packet.py",
                *pg_required,
                "--output-json",
                str(single_lane),
                "--output-owner-progress",
                str(single_lane_md),
            ),
        ),
        RefreshStep("validate_single_lane_task_packet", (python, "scripts/validate_single_lane_task_packet.py", str(single_lane))),
        RefreshStep(
            "refresh_product_state_artifacts",
            (
                python,
                "scripts/refresh_strategygroup_runtime_product_state_artifacts.py",
                "--api-base",
                api_base,
                "--output-dir",
                str(report_dir),
                "--output-json",
                str(report_dir / "product-state-refresh-packet.json"),
                "--refresh-chain-closure-status",
                "--chain-closure-output-json",
                str(report_dir / "runtime-execution-chain-closure-status.json"),
                "--refresh-live-closure-evidence",
                "--live-closure-evidence-report-dir",
                str(report_dir),
                "--live-closure-evidence-output-json",
                str(report_dir / "runtime-live-closure-evidence.json"),
                "--live-closure-evidence-verification-output-json",
                str(report_dir / "runtime-live-closure-evidence-verification.json"),
                "--live-closure-evidence-refresh-output-json",
                str(report_dir / "runtime-live-closure-evidence-refresh.json"),
                "--label",
                "tokyo-runtime-signal-watcher",
            ),
            required=False,
        ),
        RefreshStep(
            "build_account_safe_facts",
            (
                python,
                "scripts/build_runtime_account_safe_facts.py",
                *pg_required,
                "--env-file",
                str(env_file),
                "--output-json",
                str(account),
            ),
        ),
        RefreshStep(
            "build_action_time_boundary_account",
            (
                python,
                "scripts/build_strategy_fresh_signal_action_time_boundary.py",
                *action_time_boundary_inputs,
            ),
        ),
        RefreshStep(
            "build_candidate_pool_after_account",
            (
                python,
                "scripts/build_strategy_live_candidate_pool.py",
                *pg_required,
                "--output-json",
                str(candidate_pool),
                "--output-owner-progress",
                str(candidate_pool_md),
            ),
        ),
        RefreshStep("validate_candidate_pool_after_account", (python, "scripts/validate_strategy_live_candidate_pool.py", str(candidate_pool))),
        RefreshStep(
            "materialize_pg_promotion_action_time_lane",
            (
                python,
                "scripts/materialize_pg_promotion_action_time_lane.py",
                *pg_required,
                "--output-json",
                str(report_dir / "pg-promotion-action-time-lane-materialization.json"),
            ),
        ),
        RefreshStep(
            "materialize_action_time_ticket",
            (
                python,
                "scripts/materialize_action_time_ticket.py",
                *pg_required,
                "--output-json",
                str(report_dir / "action-time-ticket-materialization.json"),
            ),
        ),
        RefreshStep(
            "materialize_action_time_finalgate_preflight",
            (
                python,
                "scripts/materialize_action_time_finalgate_preflight.py",
                *pg_required,
                "--output-json",
                str(report_dir / "action-time-finalgate-preflight.json"),
            ),
        ),
        RefreshStep(
            "materialize_action_time_operation_layer_handoff",
            (
                python,
                "scripts/materialize_action_time_operation_layer_handoff.py",
                *pg_required,
                "--output-json",
                str(report_dir / "operation-layer-handoff.json"),
            ),
        ),
        RefreshStep(
            "materialize_ticket_bound_runtime_safety_state",
            (
                python,
                "scripts/materialize_ticket_bound_runtime_safety_state.py",
                *pg_required,
                "--output-json",
                str(report_dir / "ticket-bound-runtime-safety-state.json"),
            ),
        ),
        RefreshStep(
            "materialize_ticket_bound_post_submit_closure",
            (
                python,
                "scripts/materialize_ticket_bound_post_submit_closure.py",
                *pg_required,
                "--latest-submitted",
                "--output-json",
                str(report_dir / "ticket-bound-post-submit-closure.json"),
            ),
        ),
        RefreshStep(
            "build_candidate_pool_after_materialization",
            (
                python,
                "scripts/build_strategy_live_candidate_pool.py",
                *pg_required,
                "--output-json",
                str(candidate_pool),
                "--output-owner-progress",
                str(candidate_pool_md),
            ),
        ),
        RefreshStep("validate_candidate_pool_after_materialization", (python, "scripts/validate_strategy_live_candidate_pool.py", str(candidate_pool))),
        RefreshStep(
            "build_readiness_pack_after_materialization",
            (
                python,
                "scripts/build_runtime_signal_watcher_readiness_pack.py",
                "--report-dir",
                str(report_dir),
                "--output-dir",
                str(report_dir),
                "--stale-after-seconds",
                "180",
                "--label",
                "tokyo-runtime-signal-watcher",
            ),
        ),
        RefreshStep(
            "build_daily_table_after_account",
            (
                python,
                "scripts/build_daily_live_enablement_table.py",
                *pg_required,
                "--output-json",
                str(daily_table),
                "--output-owner-progress",
                str(daily_table_md),
            ),
        ),
        RefreshStep("validate_daily_table_after_account", (python, "scripts/validate_daily_live_enablement_table.py", str(daily_table))),
        RefreshStep(
            "build_single_lane_task_packet_after_account",
            (
                python,
                "scripts/build_single_lane_task_packet.py",
                *pg_required,
                "--output-json",
                str(single_lane),
                "--output-owner-progress",
                str(single_lane_md),
            ),
        ),
        RefreshStep("validate_single_lane_task_packet_after_account", (python, "scripts/validate_single_lane_task_packet.py", str(single_lane))),
        RefreshStep(
            "build_goal_status",
            (
                python,
                "scripts/build_strategygroup_runtime_goal_status.py",
                "--report-dir",
                str(report_dir),
                "--release-manifest",
                str(release_manifest),
                *pg_required,
                "--output-json",
                str(goal),
            ),
        ),
        RefreshStep(
            "publish_runtime_control_current_projections",
            (
                python,
                "scripts/publish_runtime_control_current_projections.py",
                *pg_required,
                "--candidate-pool-json",
                str(candidate_pool),
                "--daily-table-json",
                str(daily_table),
                "--goal-status-json",
                str(goal),
                "--report-dir",
                str(report_dir),
                "--runtime-monitor-dir",
                str(runtime_monitor_dir),
                "--release-manifest",
                str(release_manifest),
                "--output-json",
                str(report_dir / "runtime-control-current-projection-publish.json"),
            ),
        ),
    ]
    return _steps_for_mode(steps, mode=mode)


def _steps_for_mode(steps: list[RefreshStep], *, mode: str) -> list[RefreshStep]:
    if mode == "diagnostic_full":
        return steps
    names_by_mode = {
        "watcher_tick_summary": {
            "validate_runtime_coverage",
            "build_readiness_pack_after_materialization",
        },
        "control_refresh": {
            "fetch_public_facts",
            "build_sor_detector",
            "build_action_time_boundary_public",
            "build_mi_trial_admission",
            "build_brf2_runtime_signal_facts",
            "validate_runtime_coverage",
            "build_candidate_pool",
            "validate_candidate_pool",
            "build_daily_table",
            "validate_daily_table",
            "build_single_lane_task_packet",
            "validate_single_lane_task_packet",
            "build_goal_status",
            "publish_runtime_control_current_projections",
        },
        "action_time": {
            "build_account_safe_facts",
            "build_action_time_boundary_account",
            "build_candidate_pool_after_account",
            "validate_candidate_pool_after_account",
            "materialize_pg_promotion_action_time_lane",
            "materialize_action_time_ticket",
            "materialize_action_time_finalgate_preflight",
            "materialize_action_time_operation_layer_handoff",
            "materialize_ticket_bound_runtime_safety_state",
            "build_candidate_pool_after_materialization",
            "validate_candidate_pool_after_materialization",
            "build_readiness_pack_after_materialization",
            "build_daily_table_after_account",
            "validate_daily_table_after_account",
            "build_single_lane_task_packet_after_account",
            "validate_single_lane_task_packet_after_account",
            "build_goal_status",
            "publish_runtime_control_current_projections",
        },
        "closure": {
            "materialize_ticket_bound_post_submit_closure",
            "build_goal_status",
            "publish_runtime_control_current_projections",
        },
    }
    allowed_names = names_by_mode[mode]
    return [step for step in steps if step.name in allowed_names]


def _command_env_with_sync_pg_dsn(base_env: Mapping[str, str]) -> dict[str, str]:
    env = dict(base_env)
    for key in ("PG_DATABASE_URL", "DATABASE_URL"):
        if env.get(key):
            env[key] = normalize_sync_postgres_dsn(env[key])
    return env


def _run_command(
    command: tuple[str, ...],
    *,
    env: dict[str, str] | None = None,
) -> CommandResult:
    completed = subprocess.run(
        command,
        check=False,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return CommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(path)


def _tail(text: str, *, max_chars: int = 500) -> str:
    stripped = text.strip()
    return stripped if len(stripped) <= max_chars else stripped[-max_chars:]


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=DEFAULT_PYTHON)
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    parser.add_argument("--runtime-monitor-dir", default=str(DEFAULT_RUNTIME_MONITOR_DIR))
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument(
        "--mode",
        choices=sorted(REFRESH_MODES),
        default="diagnostic_full",
        help=(
            "Refresh mode. watcher_tick_summary is the normal watcher post-step; "
            "diagnostic_full preserves the legacy full diagnostic sequence."
        ),
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
