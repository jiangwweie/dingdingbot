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
DEFAULT_ENV_FILE = Path("/home/ubuntu/brc-deploy/env/live-readonly.env")
REFRESH_MODES = {
    "watcher_tick_summary",
    "action_time_if_needed",
    "action_time",
    "closure",
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
        env_file=Path(args.env_file),
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
    env_file: Path = DEFAULT_ENV_FILE,
    mode: str = "watcher_tick_summary",
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
            return report
        if trigger_state.get("triggered") is not True:
            report = _empty_refresh_report(
                mode=mode,
                effective_mode="none",
                started_at_utc=started,
                status="server_product_state_refresh_sequence_ready",
                action_time_trigger=trigger_state,
            )
            return report
        effective_mode = "action_time"
    steps = _refresh_steps(
        python=python,
        api_base=api_base,
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
    current_projection_publish_attempted = any(
        result["name"] == "publish_runtime_control_current_projections"
        and result["returncode"] is not None
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
            "current_projection_publish_attempted": current_projection_publish_attempted,
            "current_projection_publish_suppressed": (
                not current_projection_publish_attempted
            ),
            "blocked_by_required_step": blocked_by_required_failure,
        },
        "step_results": step_results,
        "safety_invariants": {
            "calls_finalgate": False,
            "calls_action_time_finalgate_preflight": (
                "materialize_action_time_finalgate_preflight"
                in attempted_step_names
            ),
            "calls_finalgate_submit_authority": False,
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
            "calls_operation_layer_handoff": (
                "materialize_action_time_operation_layer_handoff"
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
            "current_projection_publish_attempted": False,
            "current_projection_publish_suppressed": True,
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
        "calls_action_time_finalgate_preflight": False,
        "calls_finalgate_submit_authority": False,
        "calls_ticket_bound_finalgate_preflight": False,
        "calls_ticket_bound_operation_layer_handoff": False,
        "calls_ticket_bound_runtime_safety_state": False,
        "calls_ticket_bound_post_submit_closure": False,
        "calls_operation_layer_handoff": False,
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
    now_ms = _now_ms()
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
            counts = _action_time_trigger_counts(conn, now_ms=now_ms)
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
        "now_ms": now_ms,
        "counts": counts,
    }


def _action_time_trigger_counts(
    conn: sa.engine.Connection,
    *,
    now_ms: int | None = None,
) -> dict[str, int]:
    now = _now_ms() if now_ms is None else int(now_ms)
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
                live_signals.c.source_kind == "live_market",
                live_signals.c.expires_at_ms.is_not(None),
                live_signals.c.expires_at_ms > now,
                live_signals.c.invalidated_at_ms.is_(None),
            ),
        ),
        "open_promotion_candidates": _count_where(
            conn,
            promotions,
            sa.and_(
                promotions.c.status.in_(
                    [
                        "eligible",
                        "arbitration_pending",
                        "arbitration_won",
                    ]
                ),
                promotions.c.expires_at_ms > now,
                promotions.c.closed_at_ms.is_(None),
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
                lanes.c.expires_at_ms > now,
                lanes.c.closed_at_ms.is_(None),
            ),
        ),
        "open_action_time_tickets": _count_where(
            conn,
            tickets,
            sa.and_(
                tickets.c.status.in_(
                    [
                        "created",
                        "preflight_pending",
                        "finalgate_ready",
                    ]
                ),
                tickets.c.expires_at_ms > now,
            ),
        ),
    }


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


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
    env_file: Path,
    mode: str,
) -> list[RefreshStep]:
    pg_required = ("--require-database-url",)

    steps = [
        RefreshStep(
            "build_account_safe_facts",
            (
                python,
                "scripts/build_runtime_account_safe_facts.py",
                *pg_required,
                "--env-file",
                str(env_file),
            ),
        ),
        RefreshStep(
            "materialize_pg_promotion_action_time_lane",
            (
                python,
                "scripts/materialize_pg_promotion_action_time_lane.py",
                *pg_required,
            ),
        ),
        RefreshStep(
            "materialize_action_time_ticket",
            (
                python,
                "scripts/materialize_action_time_ticket.py",
                *pg_required,
            ),
        ),
        RefreshStep(
            "materialize_action_time_finalgate_preflight",
            (
                python,
                "scripts/materialize_action_time_finalgate_preflight.py",
                *pg_required,
            ),
        ),
        RefreshStep(
            "materialize_action_time_operation_layer_handoff",
            (
                python,
                "scripts/materialize_action_time_operation_layer_handoff.py",
                *pg_required,
            ),
        ),
        RefreshStep(
            "materialize_ticket_bound_runtime_safety_state",
            (
                python,
                "scripts/materialize_ticket_bound_runtime_safety_state.py",
                *pg_required,
            ),
        ),
        RefreshStep(
            "materialize_ticket_bound_post_submit_closure",
            (
                python,
                "scripts/materialize_ticket_bound_post_submit_closure.py",
                *pg_required,
                "--latest-submitted",
            ),
        ),
        RefreshStep(
            "publish_runtime_control_current_projections",
            (
                python,
                "scripts/publish_runtime_control_current_projections.py",
                *pg_required,
            ),
        ),
    ]
    return _steps_for_mode(steps, mode=mode)


def _steps_for_mode(steps: list[RefreshStep], *, mode: str) -> list[RefreshStep]:
    names_by_mode = {
        "watcher_tick_summary": {
            "publish_runtime_control_current_projections",
        },
        "action_time": {
            "build_account_safe_facts",
            "materialize_pg_promotion_action_time_lane",
            "materialize_action_time_ticket",
            "materialize_action_time_finalgate_preflight",
            "materialize_action_time_operation_layer_handoff",
            "materialize_ticket_bound_runtime_safety_state",
            "publish_runtime_control_current_projections",
        },
        "closure": {
            "materialize_ticket_bound_post_submit_closure",
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


def _tail(text: str, *, max_chars: int = 500) -> str:
    stripped = text.strip()
    return stripped if len(stripped) <= max_chars else stripped[-max_chars:]


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=DEFAULT_PYTHON)
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE))
    parser.add_argument(
        "--mode",
        choices=sorted(REFRESH_MODES),
        default="watcher_tick_summary",
        help=(
            "Refresh mode. watcher_tick_summary is the normal watcher post-step; "
            "action_time_if_needed checks PG current state before running "
            "ticket/preflight/handoff/safety materializers."
        ),
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
