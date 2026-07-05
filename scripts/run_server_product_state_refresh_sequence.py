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
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PYTHON = "/home/ubuntu/brc-deploy/venvs/brc-bnb-prelive-20260601/bin/python"
DEFAULT_API_BASE = "http://127.0.0.1:18080"
DEFAULT_REPORT_DIR = Path("/home/ubuntu/brc-deploy/reports/runtime-signal-watcher")
DEFAULT_RUNTIME_MONITOR_DIR = Path("/home/ubuntu/brc-deploy/reports/runtime-monitor")
DEFAULT_ENV_FILE = Path("/home/ubuntu/brc-deploy/env/live-readonly.env")
DEFAULT_OUTPUT_JSON = DEFAULT_REPORT_DIR / "server-product-state-refresh-sequence.json"


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
    runner: Runner | None = None,
) -> dict[str, Any]:
    command_runner = runner or _run_command
    started = datetime.now(timezone.utc).isoformat()
    steps = _refresh_steps(
        python=python,
        api_base=api_base,
        report_dir=report_dir,
        runtime_monitor_dir=runtime_monitor_dir,
        env_file=env_file,
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
    report = {
        "schema": "brc.server_product_state_refresh_sequence.v1",
        "scope": "server_product_state_refresh_sequence_non_authority",
        "status": (
            "server_product_state_refresh_sequence_ready"
            if not failed_required
            else "server_product_state_refresh_sequence_failed"
        ),
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
            "calls_ticket_bound_finalgate_preflight": True,
            "calls_ticket_bound_operation_layer_handoff": True,
            "calls_ticket_bound_runtime_safety_state": True,
            "calls_ticket_bound_post_submit_closure": True,
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


def _refresh_steps(
    *,
    python: str,
    api_base: str,
    report_dir: Path,
    runtime_monitor_dir: Path,
    env_file: Path,
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

    return [
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
    ]


def _run_command(command: tuple[str, ...]) -> CommandResult:
    completed = subprocess.run(
        command,
        check=False,
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
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
