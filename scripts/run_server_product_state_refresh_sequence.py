#!/usr/bin/env python3
"""Run the server-side product-state refresh sequence after watcher ticks.

The sequence is non-authority from a trading perspective. It refreshes control
read models, may materialize PG fresh signals into one action-time lane,
may materialize a PG Action-Time Ticket when a PG real-submit lane is present,
and may run the ticket-bound non-executing FinalGate preflight and Operation
Layer handoff, then materialize PG Runtime Safety State. It does not materialize
protected submit attempts, call Operation Layer submit, exchange write APIs,
OrderLifecycle, withdrawals, transfers, credential mutation, live profile
changes, or order sizing changes. Ticket-bound protected submit belongs to the
resume dispatcher after PG SubmitModeDecision.
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
import time
from typing import Any, Callable

import sqlalchemy as sa


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.pg_dsn import normalize_sync_postgres_dsn  # noqa: E402
from src.application.action_time.action_time_invocation import (  # noqa: E402
    ActionTimeInvocationBlocked,
    load_action_time_invocation,
    start_action_time_invocation,
)
from src.application.runtime_process_outcome import (  # noqa: E402
    classify_process_outcome,
    materialize_runtime_process_outcome,
)

DEFAULT_PYTHON = "/home/ubuntu/brc-deploy/venvs/brc-bnb-prelive-20260601/bin/python"
DEFAULT_API_BASE = "http://127.0.0.1:18080"
DEFAULT_ENV_FILE = Path("/home/ubuntu/brc-deploy/env/live-readonly.env")
DEFAULT_STEP_TIMEOUT_SECONDS = 45
ACTION_TIME_LATENCY_BUDGET_MS = 30_000
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
    duration_ms: int = 0


Runner = Callable[[tuple[str, ...]], CommandResult]
ProcessOutcomeWriter = Callable[[dict[str, Any]], dict[str, Any] | None]
ActionTimeInvocationStarter = Callable[..., dict[str, Any]]


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
                "effective_mode": report["effective_mode"],
                "failed_required_step_count": report["summary"][
                    "failed_required_step_count"
                ],
                "failed_optional_step_count": report["summary"][
                    "failed_optional_step_count"
                ],
                "blocked_by_required_step": report["summary"][
                    "blocked_by_required_step"
                ],
                "blocked_required_stdout_tail": report["summary"][
                    "blocked_required_stdout_tail"
                ],
                "blocked_required_stderr_tail": report["summary"][
                    "blocked_required_stderr_tail"
                ],
                "total_step_duration_ms": report["summary"][
                    "total_step_duration_ms"
                ],
                "latency_budget_status": report["summary"][
                    "latency_budget_status"
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return (
        0
        if report["status"]
        in {
            "server_product_state_refresh_sequence_ready",
            "server_product_state_refresh_sequence_business_blocked",
        }
        else 1
    )


def run_server_product_state_refresh_sequence(
    *,
    python: str = DEFAULT_PYTHON,
    api_base: str = DEFAULT_API_BASE,
    env_file: Path = DEFAULT_ENV_FILE,
    mode: str = "watcher_tick_summary",
    runner: Runner | None = None,
    action_time_trigger_state: dict[str, Any] | None = None,
    process_outcome_writer: ProcessOutcomeWriter | None = None,
    action_time_invocation_starter: ActionTimeInvocationStarter | None = None,
) -> dict[str, Any]:
    if mode not in REFRESH_MODES:
        raise ValueError(f"unsupported refresh mode: {mode}")
    command_env = _command_env_with_sync_pg_dsn(os.environ)
    command_runner = runner or (lambda command: _run_command(command, env=command_env))
    started = datetime.now(timezone.utc).isoformat()
    effective_mode = mode
    action_time_sequence_now_ms: int | None = None
    trigger_state: dict[str, Any] | None = None
    action_time_invocation: dict[str, Any] | None = None
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
        action_time_sequence_now_ms = int(trigger_state.get("now_ms") or _now_ms())
        effective_mode = "action_time"
    elif mode == "action_time":
        action_time_sequence_now_ms = _now_ms()
        trigger_state = action_time_trigger_state
    if effective_mode == "action_time" and trigger_state is not None:
        existing_invocation_id = _trigger_action_time_invocation_id(trigger_state)
        if existing_invocation_id:
            # A resumed Ticket/lane retains its original causal context.  A
            # watcher tick must never create a second invocation merely to
            # advance a later Ticket-bound stage.
            action_time_invocation = {
                "action_time_invocation_id": existing_invocation_id,
            }
        elif _trigger_requires_new_invocation(trigger_state):
            signal_event_id = _trigger_signal_event_id(trigger_state)
            if not signal_event_id:
                return _action_time_invocation_start_failure_report(
                    mode=mode,
                    started_at_utc=started,
                    trigger_state=trigger_state,
                    blocker="action_time_invocation_trigger_signal_missing",
                )
            invocation_starter = (
                action_time_invocation_starter
                or _start_action_time_invocation_from_trigger
            )
            try:
                action_time_invocation = invocation_starter(
                    signal_event_id=signal_event_id,
                    opened_at_ms=int(action_time_sequence_now_ms or _now_ms()),
                    env=command_env,
                )
            except (
                ActionTimeInvocationBlocked,
                RuntimeError,
                sa.exc.SQLAlchemyError,
            ) as exc:
                return _action_time_invocation_start_failure_report(
                    mode=mode,
                    started_at_utc=started,
                    trigger_state=trigger_state,
                    blocker=(
                        "action_time_invocation_start_failed:"
                        f"{type(exc).__name__}"
                    ),
                )
    steps = _refresh_steps(
        python=python,
        api_base=api_base,
        env_file=env_file,
        mode=effective_mode,
        action_time_sequence_now_ms=action_time_sequence_now_ms,
        action_time_invocation_id=(
            str(action_time_invocation.get("action_time_invocation_id") or "")
            if action_time_invocation is not None
            else None
        ),
    )
    step_results: list[dict[str, Any]] = []
    blocked_by_required_step = ""
    required_stop_kind = ""
    for step in steps:
        allow_projection_after_business_block = (
            required_stop_kind == "business_blocked"
            and step.name
            == "publish_runtime_control_current_projections_after_action_time"
        )
        if blocked_by_required_step and not allow_projection_after_business_block:
            step_results.append(
                {
                    "name": step.name,
                    "required": step.required,
                    "returncode": None,
                    "status": (
                        "skipped_after_business_blocked"
                        if required_stop_kind == "business_blocked"
                        else "skipped_after_required_failure"
                    ),
                    "blocked_by": blocked_by_required_step,
                    "command": list(step.command),
                    "stdout_tail": "",
                    "stderr_tail": "",
                }
            )
            continue
        result = command_runner(step.command)
        child_process_outcome = _structured_child_process_outcome(result.stdout)
        child_business_blocked = (
            result.returncode == 0
            and str(child_process_outcome.get("process_state") or "")
            == "business_blocked"
        )
        step_results.append(
            {
                "name": step.name,
                "required": step.required,
                "returncode": result.returncode,
                "status": (
                    "failed"
                    if result.returncode != 0
                    else "business_blocked"
                    if child_business_blocked
                    else "passed"
                ),
                "command": list(step.command),
                "stdout_tail": _tail(result.stdout),
                "stderr_tail": _tail(result.stderr),
                "duration_ms": int(result.duration_ms),
                "child_process_outcome": child_process_outcome,
            }
        )
        if step.required and result.returncode != 0:
            blocked_by_required_step = step.name
            required_stop_kind = "failure"
        elif step.required and child_business_blocked:
            blocked_by_required_step = step.name
            required_stop_kind = "business_blocked"

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
        if str(result["status"]).startswith("skipped_after_")
    ]
    skipped_after_required_failure = [
        result
        for result in skipped
        if result["status"] == "skipped_after_required_failure"
    ]
    skipped_after_business_blocked = [
        result
        for result in skipped
        if result["status"] == "skipped_after_business_blocked"
    ]
    business_blocked_required = [
        result
        for result in step_results
        if result["required"] and result["status"] == "business_blocked"
    ]
    blocking_required = [*failed_required, *business_blocked_required]
    current_projection_publish_attempted = any(
        str(result["name"]).startswith(
            "publish_runtime_control_current_projections"
        )
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
            if not failed_required and not business_blocked_required
            else "server_product_state_refresh_sequence_business_blocked"
            if business_blocked_required and not failed_required
            else "server_product_state_refresh_sequence_failed"
        ),
        "mode": mode,
        "effective_mode": effective_mode,
        "action_time_sequence_now_ms": action_time_sequence_now_ms,
        "action_time_trigger": trigger_state,
        "action_time_invocation": action_time_invocation,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "started_at_utc": started,
        "summary": {
            "step_count": len(step_results),
            "required_step_count": sum(1 for step in steps if step.required),
            "optional_step_count": sum(1 for step in steps if not step.required),
            "failed_required_step_count": len(failed_required),
            "failed_optional_step_count": len(failed_optional),
            "business_blocked_required_step_count": len(business_blocked_required),
            "skipped_after_required_failure_count": len(
                skipped_after_required_failure
            ),
            "skipped_after_business_blocked_count": len(
                skipped_after_business_blocked
            ),
            "current_projection_publish_attempted": current_projection_publish_attempted,
            "current_projection_publish_suppressed": (
                not current_projection_publish_attempted
            ),
            "blocked_by_required_step": blocked_by_required_step,
            "business_blocked_by_required_step": (
                blocked_by_required_step
                if required_stop_kind == "business_blocked"
                else ""
            ),
            "business_blocked_first_blocker": (
                str(
                    business_blocked_required[0]
                    .get("child_process_outcome", {})
                    .get("first_blocker")
                    or ""
                )
                if business_blocked_required
                else ""
            ),
            "blocked_required_stdout_tail": (
                str(blocking_required[0].get("stdout_tail") or "")
                if blocking_required
                else ""
            ),
            "blocked_required_stderr_tail": (
                str(blocking_required[0].get("stderr_tail") or "")
                if blocking_required
                else ""
            ),
            "total_step_duration_ms": sum(
                int(result.get("duration_ms") or 0)
                for result in step_results
                if result["returncode"] is not None
            ),
            "latency_budget_ms": (
                ACTION_TIME_LATENCY_BUDGET_MS
                if effective_mode == "action_time"
                else None
            ),
            "latency_budget_status": (
                "within_budget"
                if effective_mode == "action_time"
                and sum(
                    int(result.get("duration_ms") or 0)
                    for result in step_results
                    if result["returncode"] is not None
                ) <= ACTION_TIME_LATENCY_BUDGET_MS
                else "exceeded"
                if effective_mode == "action_time"
                else "not_applicable"
            ),
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
            "calls_atomic_action_time_ticket_sequence": (
                "materialize_action_time_ticket_sequence" in attempted_step_names
            ),
            "calls_ticket_bound_operation_layer_handoff": (
                "materialize_action_time_operation_layer_handoff"
                in attempted_step_names
            ),
            "calls_ticket_bound_runtime_safety_state": (
                "materialize_ticket_bound_runtime_safety_state"
                in attempted_step_names
            ),
            "calls_ticket_bound_protected_submit_attempt": (
                "materialize_ticket_bound_protected_submit_attempt"
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
    outcome_payload = _action_time_refresh_process_outcome_payload(report)
    if outcome_payload is not None:
        writer = process_outcome_writer or (
            lambda payload: _persist_action_time_refresh_process_outcome(
                payload,
                env=command_env,
            )
        )
        written = writer(outcome_payload)
        if isinstance(written, Mapping):
            report["process_outcome"] = dict(written)
        else:
            classified = classify_process_outcome(
                process_name=str(outcome_payload["process_name"]),
                result_status=str(outcome_payload["result_status"]),
                blockers=list(outcome_payload["blockers"]),
            )
            report["process_outcome"] = classified.model_dump(mode="json")
    return report


def _action_time_refresh_process_outcome_payload(
    report: Mapping[str, Any],
) -> dict[str, Any] | None:
    if report.get("effective_mode") != "action_time":
        return None
    trigger = report.get("action_time_trigger")
    if not isinstance(trigger, Mapping) or trigger.get("triggered") is not True:
        return None
    identity = trigger.get("trigger_identity")
    if not isinstance(identity, Mapping):
        return None
    strategy_group_id = str(identity.get("strategy_group_id") or "").strip()
    symbol = str(identity.get("symbol") or "").strip()
    side = str(identity.get("side") or "").strip()
    if not all((strategy_group_id, symbol, side)):
        return None

    summary = report.get("summary")
    if not isinstance(summary, Mapping):
        return None
    invocation_payload = report.get("action_time_invocation")
    invocation = (
        dict(invocation_payload)
        if isinstance(invocation_payload, Mapping)
        else {}
    )
    action_time_invocation_id = str(
        invocation.get("action_time_invocation_id")
        or identity.get("action_time_invocation_id")
        or ""
    ).strip()
    lane_identity = invocation.get("lane_identity")
    lane_identity_payload = (
        dict(lane_identity) if isinstance(lane_identity, Mapping) else None
    )
    started_at_ms = int(
        invocation.get("opened_at_ms")
        or report.get("action_time_sequence_now_ms")
        or trigger.get("now_ms")
        or 0
    )
    if started_at_ms <= 0:
        return None
    duration_ms = int(summary.get("total_step_duration_ms") or 0)
    failed_step = str(summary.get("blocked_by_required_step") or "").strip()
    business_blocked_step = str(
        summary.get("business_blocked_by_required_step") or ""
    ).strip()
    if business_blocked_step:
        blockers = [
            str(summary.get("business_blocked_first_blocker") or "").strip()
            or "action_time_refresh_sequence_business_blocked"
        ]
        result_status = "action_time_refresh_sequence_business_blocked"
    elif failed_step:
        blockers = [_refresh_step_failure_blocker(report)]
        result_status = "action_time_refresh_sequence_failed"
    else:
        blockers = []
        result_status = "action_time_refresh_sequence_completed"
    source_watermark = str(invocation.get("source_watermark") or "").strip() or next(
        (
            str(identity.get(key) or "").strip()
            for key in (
                "ticket_id",
                "action_time_lane_input_id",
                "promotion_candidate_id",
                "signal_event_id",
            )
            if str(identity.get(key) or "").strip()
        ),
        f"lane:{strategy_group_id}:{symbol}:{side}",
    )
    payload = {
        "process_name": "action_time_refresh_sequence",
        "scope_key": f"lane:{strategy_group_id}:{symbol}:{side}",
        "run_id": f"action_time_refresh:{started_at_ms}",
        "result_status": result_status,
        "blockers": blockers,
        "started_at_ms": started_at_ms,
        "completed_at_ms": started_at_ms + duration_ms,
        "source_watermark": source_watermark,
    }
    if action_time_invocation_id:
        payload["action_time_invocation_id"] = action_time_invocation_id
    if lane_identity_payload is not None:
        payload["lane_identity"] = lane_identity_payload
    return payload


def _refresh_step_failure_blocker(report: Mapping[str, Any]) -> str:
    summary = report.get("summary")
    if not isinstance(summary, Mapping):
        return "action_time_refresh_sequence_failed"
    step = str(summary.get("blocked_by_required_step") or "").strip()
    stderr = str(summary.get("blocked_required_stderr_tail") or "").strip()
    stdout = str(summary.get("blocked_required_stdout_tail") or "").strip()
    if "step_timeout_after_" in stderr:
        return f"{step}_timeout"
    detail = _structured_first_blocker(stdout)
    if detail:
        return f"{step}_failed:{detail}"
    return f"{step}_failed"


def _structured_first_blocker(stdout: str) -> str:
    outcome = _structured_child_process_outcome(stdout)
    first = str(outcome.get("first_blocker") or "").strip()
    if first:
        return first
    for line in reversed(str(stdout or "").splitlines()):
        try:
            payload = json.loads(line)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(payload, Mapping):
            continue
        process_outcome = payload.get("process_outcome")
        if isinstance(process_outcome, Mapping):
            first = str(process_outcome.get("first_blocker") or "").strip()
            if first:
                return first
        first = str(payload.get("first_blocker") or "").strip()
        if first:
            return first
        blockers = payload.get("blockers")
        if isinstance(blockers, list) and blockers:
            first = str(blockers[0] or "").strip()
            if first:
                return first
    return ""


def _structured_child_process_outcome(stdout: str) -> dict[str, str]:
    """Read the child semantic outcome from its final structured JSON line.

    Safe business stops deliberately exit with code zero.  The parent therefore
    treats the typed outcome as authoritative for process semantics while it
    continues to use the exit code for transport/runtime failure detection.
    """

    for line in reversed(str(stdout or "").splitlines()):
        try:
            payload = json.loads(line)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(payload, Mapping):
            continue
        candidate = payload.get("process_outcome")
        if not isinstance(candidate, Mapping):
            candidate = payload
        process_state = str(candidate.get("process_state") or "").strip()
        business_state = str(candidate.get("business_state") or "").strip()
        first_blocker = str(candidate.get("first_blocker") or "").strip()
        if not first_blocker:
            blockers = candidate.get("blockers")
            if isinstance(blockers, list) and blockers:
                first_blocker = str(blockers[0] or "").strip()
        if process_state or business_state or first_blocker:
            return {
                "process_state": process_state,
                "business_state": business_state,
                "first_blocker": first_blocker,
            }
    return {}


def _persist_action_time_refresh_process_outcome(
    payload: Mapping[str, Any],
    *,
    env: Mapping[str, str],
) -> dict[str, Any] | None:
    database_url = normalize_sync_postgres_dsn(
        env.get("PG_DATABASE_URL") or env.get("DATABASE_URL") or ""
    )
    if not database_url:
        return None
    engine = sa.create_engine(database_url)
    try:
        with engine.begin() as conn:
            invocation_id = str(
                payload.get("action_time_invocation_id") or ""
            ).strip()
            invocation = (
                load_action_time_invocation(
                    conn,
                    action_time_invocation_id=invocation_id,
                )
                if invocation_id
                else None
            )
            if invocation is not None:
                effective_payload = dict(payload)
                effective_payload.update(
                    {
                        "scope_key": (
                            "lane:"
                            f"{invocation.lane_identity.strategy_group_id}:"
                            f"{invocation.lane_identity.symbol}:"
                            f"{invocation.lane_identity.side}"
                        ),
                        "source_watermark": invocation.source_watermark,
                    }
                )
            else:
                effective_payload = _with_current_trigger_identity(
                    payload,
                    _action_time_trigger_identity(
                        conn,
                        now_ms=int(payload["started_at_ms"]),
                    ),
                )
            return dict(
                materialize_runtime_process_outcome(
                    conn,
                    process_name=str(effective_payload["process_name"]),
                    scope_key=str(effective_payload["scope_key"]),
                    run_id=str(effective_payload["run_id"]),
                    result_status=str(effective_payload["result_status"]),
                    blockers=[
                        str(item)
                        for item in effective_payload.get("blockers") or []
                    ],
                    started_at_ms=int(effective_payload["started_at_ms"]),
                    completed_at_ms=int(effective_payload["completed_at_ms"]),
                    runtime_head=str(env.get("BRC_RUNTIME_HEAD") or ""),
                    source_watermark=str(effective_payload["source_watermark"]),
                    projector_owner="server_product_state_refresh_sequence",
                    lane_identity=(
                        invocation.lane_identity if invocation is not None else None
                    ),
                    action_time_invocation_id=(
                        invocation.action_time_invocation_id
                        if invocation is not None
                        else None
                    ),
                )
            )
    finally:
        engine.dispose()


def _with_current_trigger_identity(
    payload: Mapping[str, Any],
    identity: Mapping[str, Any],
) -> dict[str, Any]:
    result = dict(payload)
    strategy_group_id = str(identity.get("strategy_group_id") or "").strip()
    symbol = str(identity.get("symbol") or "").strip()
    side = str(identity.get("side") or "").strip()
    if not all((strategy_group_id, symbol, side)):
        return result
    result["scope_key"] = f"lane:{strategy_group_id}:{symbol}:{side}"
    result["source_watermark"] = next(
        (
            str(identity.get(key) or "").strip()
            for key in (
                "ticket_id",
                "action_time_lane_input_id",
                "promotion_candidate_id",
                "signal_event_id",
            )
            if str(identity.get(key) or "").strip()
        ),
        result.get("source_watermark") or result["scope_key"],
    )
    return result


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
            "business_blocked_required_step_count": 0,
            "skipped_after_required_failure_count": 0,
            "skipped_after_business_blocked_count": 0,
            "current_projection_publish_attempted": False,
            "current_projection_publish_suppressed": True,
            "blocked_by_required_step": (
                "pg_action_time_trigger_state"
                if failed
                else ""
            ),
            "business_blocked_by_required_step": "",
            "business_blocked_first_blocker": "",
            "blocked_required_stdout_tail": (
                str(step_results[0].get("stdout_tail") or "")
                if step_results
                else ""
            ),
            "blocked_required_stderr_tail": (
                str(step_results[0].get("stderr_tail") or "")
                if step_results
                else ""
            ),
            "total_step_duration_ms": 0,
            "latency_budget_ms": (
                ACTION_TIME_LATENCY_BUDGET_MS
                if effective_mode == "action_time"
                else None
            ),
            "latency_budget_status": (
                "within_budget"
                if effective_mode == "action_time"
                else "not_applicable"
            ),
        },
        "step_results": step_results,
        "safety_invariants": _empty_safety_invariants(),
    }


def _action_time_invocation_start_failure_report(
    *,
    mode: str,
    started_at_utc: str,
    trigger_state: dict[str, Any],
    blocker: str,
) -> dict[str, Any]:
    report = _empty_refresh_report(
        mode=mode,
        effective_mode="action_time",
        started_at_utc=started_at_utc,
        status="server_product_state_refresh_sequence_failed",
        action_time_trigger={**trigger_state, "status": "blocked", "blocker": blocker},
    )
    step = report["step_results"][0]
    step["name"] = "start_action_time_invocation"
    report["summary"]["blocked_by_required_step"] = "start_action_time_invocation"
    report["action_time_invocation"] = None
    return report


def _empty_safety_invariants() -> dict[str, bool]:
    return {
        "calls_finalgate": False,
        "calls_action_time_finalgate_preflight": False,
        "calls_finalgate_submit_authority": False,
        "calls_ticket_bound_finalgate_preflight": False,
        "calls_ticket_bound_operation_layer_handoff": False,
        "calls_ticket_bound_runtime_safety_state": False,
        "calls_ticket_bound_protected_submit_attempt": False,
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
        with engine.begin() as conn:
            expiry_counts = _expire_stale_action_time_objects(conn, now_ms=now_ms)
            counts = _action_time_trigger_counts(conn, now_ms=now_ms)
            trigger_identity = _action_time_trigger_identity(conn, now_ms=now_ms)
    except Exception as exc:  # noqa: BLE001 - fail closed on PG current read errors.
        return {
            "status": "blocked",
            "triggered": False,
            "blocker": f"pg_action_time_trigger_read_failed:{type(exc).__name__}",
            "counts": {},
        }
    finally:
        engine.dispose()
    triggered = any(count > 0 for count in counts.values()) or any(
        count > 0 for count in expiry_counts.values()
    )
    return {
        "status": "triggered" if triggered else "not_triggered",
        "triggered": triggered,
        "blocker": "",
        "now_ms": now_ms,
        "counts": counts,
        "expiry_counts": expiry_counts,
        "trigger_identity": trigger_identity,
    }


def _start_action_time_invocation_from_trigger(
    *,
    signal_event_id: str,
    opened_at_ms: int,
    env: Mapping[str, str],
) -> dict[str, Any]:
    database_url = normalize_sync_postgres_dsn(
        env.get("PG_DATABASE_URL") or env.get("DATABASE_URL") or ""
    )
    if not database_url:
        raise RuntimeError("missing_action_time_invocation_database_url")
    engine = sa.create_engine(database_url)
    try:
        with engine.begin() as conn:
            invocation = start_action_time_invocation(
                conn,
                signal_event_id=signal_event_id,
                opened_at_ms=opened_at_ms,
            )
    finally:
        engine.dispose()
    return invocation.model_dump(mode="json")


def _trigger_signal_event_id(trigger_state: Mapping[str, Any]) -> str:
    identity = trigger_state.get("trigger_identity")
    if not isinstance(identity, Mapping):
        return ""
    return str(identity.get("signal_event_id") or "").strip()


def _trigger_action_time_invocation_id(trigger_state: Mapping[str, Any]) -> str:
    identity = trigger_state.get("trigger_identity")
    if not isinstance(identity, Mapping):
        return ""
    return str(identity.get("action_time_invocation_id") or "").strip()


def _trigger_requires_new_invocation(trigger_state: Mapping[str, Any]) -> bool:
    """Return true only for a fresh signal with no pre-existing active lane.

    A refresh can be triggered by a Ticket, lane, promotion, or handoff that
    already exists.  Those are continuation work and must retain their original
    invocation; only the exact fresh-signal branch opens a new causal context.
    """

    counts = trigger_state.get("counts")
    if not isinstance(counts, Mapping):
        return False
    if int(counts.get("fresh_live_signal_events") or 0) <= 0:
        return False
    active_continuation_counts = (
        "open_promotion_candidates",
        "open_action_time_lane_inputs",
        "open_action_time_tickets",
        "operation_layer_handoffs_ready_without_protected_submit",
    )
    return not any(
        int(counts.get(key) or 0) > 0 for key in active_continuation_counts
    )


def _expire_stale_action_time_objects(
    conn: sa.engine.Connection,
    *,
    now_ms: int,
) -> dict[str, int]:
    metadata = sa.MetaData()
    inspector = sa.inspect(conn)
    counts = {
        "expired_live_signal_events": 0,
        "expired_promotion_candidates": 0,
        "expired_action_time_lane_inputs": 0,
        "expired_action_time_tickets": 0,
        "expired_budget_reservations": 0,
    }

    if inspector.has_table("brc_live_signal_events"):
        live_signals = sa.Table(
            "brc_live_signal_events",
            metadata,
            autoload_with=conn,
        )
        result = conn.execute(
            live_signals.update()
            .where(live_signals.c.status == "facts_validated")
            .where(live_signals.c.freshness_state == "fresh")
            .where(live_signals.c.expires_at_ms.is_not(None))
            .where(live_signals.c.expires_at_ms <= now_ms)
            .where(live_signals.c.invalidated_at_ms.is_(None))
            .values(
                status="stale",
                freshness_state="expired",
                invalidated_at_ms=now_ms,
            )
        )
        counts["expired_live_signal_events"] = int(result.rowcount or 0)

    if inspector.has_table("brc_promotion_candidates"):
        promotions = sa.Table(
            "brc_promotion_candidates",
            metadata,
            autoload_with=conn,
        )
        result = conn.execute(
            promotions.update()
            .where(
                promotions.c.status.in_(
                    ["eligible", "arbitration_pending", "arbitration_won"]
                )
            )
            .where(promotions.c.expires_at_ms.is_not(None))
            .where(promotions.c.expires_at_ms <= now_ms)
            .where(promotions.c.closed_at_ms.is_(None))
            .values(status="expired", closed_at_ms=now_ms)
        )
        counts["expired_promotion_candidates"] = int(result.rowcount or 0)

    if inspector.has_table("brc_action_time_lane_inputs"):
        lanes = sa.Table(
            "brc_action_time_lane_inputs",
            metadata,
            autoload_with=conn,
        )
        result = conn.execute(
            lanes.update()
            .where(lanes.c.lane_scope == "real_submit_candidate")
            .where(
                lanes.c.status.in_(
                    ["opened", "facts_refreshing", "ticket_pending", "ticket_created"]
                )
            )
            .where(lanes.c.expires_at_ms.is_not(None))
            .where(lanes.c.expires_at_ms <= now_ms)
            .where(lanes.c.closed_at_ms.is_(None))
            .values(status="expired", closed_at_ms=now_ms)
        )
        counts["expired_action_time_lane_inputs"] = int(result.rowcount or 0)

    if inspector.has_table("brc_action_time_tickets"):
        tickets = sa.Table("brc_action_time_tickets", metadata, autoload_with=conn)
        result = conn.execute(
            tickets.update()
            .where(tickets.c.status.in_(["created", "preflight_pending", "finalgate_ready"]))
            .where(tickets.c.expires_at_ms.is_not(None))
            .where(tickets.c.expires_at_ms <= now_ms)
            .values(status="expired")
        )
        counts["expired_action_time_tickets"] = int(result.rowcount or 0)

    if inspector.has_table("brc_budget_reservations"):
        budget_reservations = sa.Table(
            "brc_budget_reservations",
            metadata,
            autoload_with=conn,
        )
        result = conn.execute(
            budget_reservations.update()
            .where(budget_reservations.c.status == "active")
            .where(budget_reservations.c.expires_at_ms.is_not(None))
            .where(budget_reservations.c.expires_at_ms <= now_ms)
            .values(
                status="expired",
                release_reason="action_time_object_expired",
            )
        )
        counts["expired_budget_reservations"] = int(result.rowcount or 0)

    return counts


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
        "stale_open_promotion_candidates": _count_where(
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
                promotions.c.expires_at_ms.is_not(None),
                promotions.c.expires_at_ms <= now,
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
        "stale_open_action_time_lane_inputs": _count_where(
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
                lanes.c.expires_at_ms.is_not(None),
                lanes.c.expires_at_ms <= now,
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
        "stale_open_action_time_tickets": _count_where(
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
                tickets.c.expires_at_ms.is_not(None),
                tickets.c.expires_at_ms <= now,
            ),
        ),
        "operation_layer_handoffs_ready_without_protected_submit": _ready_handoff_without_protected_submit_count(
            conn,
            now_ms=now,
        ),
    }


def _action_time_trigger_identity(
    conn: sa.engine.Connection,
    *,
    now_ms: int,
) -> dict[str, str]:
    inspector = sa.inspect(conn)
    metadata = sa.MetaData()
    if inspector.has_table("brc_action_time_tickets"):
        tickets = sa.Table(
            "brc_action_time_tickets",
            metadata,
            autoload_with=conn,
        )
        ticket = conn.execute(
            sa.select(tickets)
            .where(
                tickets.c.status.in_(
                    ["created", "preflight_pending", "finalgate_ready"]
                ),
                tickets.c.expires_at_ms > now_ms,
            )
            .order_by(tickets.c.created_at_ms.desc())
            .limit(1)
        ).mappings().first()
        if ticket is not None:
            return _trigger_identity_row(ticket, ticket_id=str(ticket["ticket_id"]))

    if inspector.has_table("brc_action_time_lane_inputs"):
        lanes = sa.Table(
            "brc_action_time_lane_inputs",
            metadata,
            autoload_with=conn,
        )
        lane = conn.execute(
            sa.select(lanes)
            .where(
                lanes.c.lane_scope == "real_submit_candidate",
                lanes.c.status.in_(
                    ["opened", "facts_refreshing", "ticket_pending", "ticket_created"]
                ),
                lanes.c.expires_at_ms > now_ms,
                lanes.c.closed_at_ms.is_(None),
            )
            .order_by(lanes.c.created_at_ms.desc())
            .limit(1)
        ).mappings().first()
        if lane is not None:
            return _trigger_identity_row(
                lane,
                action_time_lane_input_id=str(lane["action_time_lane_input_id"]),
            )

    if inspector.has_table("brc_promotion_candidates"):
        promotions = sa.Table(
            "brc_promotion_candidates",
            metadata,
            autoload_with=conn,
        )
        promotion = conn.execute(
            sa.select(promotions)
            .where(
                promotions.c.status.in_(
                    ["eligible", "arbitration_pending", "arbitration_won"]
                ),
                promotions.c.expires_at_ms > now_ms,
                promotions.c.closed_at_ms.is_(None),
            )
            .order_by(promotions.c.created_at_ms.desc())
            .limit(1)
        ).mappings().first()
        if promotion is not None:
            return _trigger_identity_row(
                promotion,
                promotion_candidate_id=str(promotion["promotion_candidate_id"]),
            )

    if inspector.has_table("brc_live_signal_events"):
        signals = sa.Table(
            "brc_live_signal_events",
            metadata,
            autoload_with=conn,
        )
        signal = conn.execute(
            sa.select(signals)
            .where(
                signals.c.source_kind == "live_market",
                signals.c.status == "facts_validated",
                signals.c.freshness_state == "fresh",
                signals.c.expires_at_ms > now_ms,
                signals.c.invalidated_at_ms.is_(None),
            )
            .order_by(signals.c.observed_at_ms.desc())
            .limit(1)
        ).mappings().first()
        if signal is not None:
            return _trigger_identity_row(
                signal,
                signal_event_id=str(signal["signal_event_id"]),
            )
    return {}


def _trigger_identity_row(
    row: Mapping[str, Any],
    **overrides: str,
) -> dict[str, str]:
    result = {
        "strategy_group_id": str(row.get("strategy_group_id") or ""),
        "symbol": str(row.get("symbol") or ""),
        "side": str(row.get("side") or ""),
        "signal_event_id": str(row.get("signal_event_id") or ""),
        "promotion_candidate_id": str(row.get("promotion_candidate_id") or ""),
        "action_time_lane_input_id": str(
            row.get("action_time_lane_input_id") or ""
        ),
        "action_time_invocation_id": str(
            row.get("action_time_invocation_id") or ""
        ),
        "ticket_id": str(row.get("ticket_id") or ""),
    }
    result.update(overrides)
    return {key: value for key, value in result.items() if value}


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


def _ready_handoff_without_protected_submit_count(
    conn: sa.engine.Connection,
    *,
    now_ms: int,
) -> int:
    metadata = sa.MetaData()
    tickets = sa.Table("brc_action_time_tickets", metadata, autoload_with=conn)
    handoffs = sa.Table("brc_operation_layer_handoffs", metadata, autoload_with=conn)
    attempts = sa.Table(
        "brc_ticket_bound_protected_submit_attempts",
        metadata,
        autoload_with=conn,
    )
    return int(
        conn.execute(
            sa.select(sa.func.count())
            .select_from(
                handoffs.join(
                    tickets,
                    handoffs.c.ticket_id == tickets.c.ticket_id,
                ).outerjoin(
                    attempts,
                    handoffs.c.operation_submit_command_id
                    == attempts.c.operation_submit_command_id,
                )
            )
            .where(
                sa.and_(
                    handoffs.c.status == "handoff_ready",
                    handoffs.c.operation_submit_command_id.is_not(None),
                    tickets.c.status == "finalgate_ready",
                    tickets.c.expires_at_ms > now_ms,
                    attempts.c.operation_submit_command_id.is_(None),
                )
            )
        ).scalar_one()
        or 0
    )


def _refresh_steps(
    *,
    python: str,
    api_base: str,
    env_file: Path,
    mode: str,
    action_time_sequence_now_ms: int | None = None,
    action_time_invocation_id: str | None = None,
) -> list[RefreshStep]:
    pg_required = ("--require-database-url",)
    invocation_args = (
        ("--action-time-invocation-id", str(action_time_invocation_id))
        if action_time_invocation_id
        else ()
    )

    steps = [
        RefreshStep(
            "build_account_safe_facts",
            (
                python,
                "scripts/build_runtime_account_safe_facts.py",
                *pg_required,
                "--env-file",
                str(env_file),
                *invocation_args,
            ),
        ),
        RefreshStep(
            "materialize_action_time_ticket_sequence",
            (
                python,
                "scripts/materialize_action_time_ticket_sequence.py",
                *pg_required,
                *invocation_args,
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
            "publish_runtime_control_current_projections_after_action_time",
            (
                python,
                "scripts/publish_runtime_control_current_projections.py",
                *pg_required,
            ),
        ),
    ]
    selected = _steps_for_mode(steps, mode=mode)
    if not action_time_invocation_id:
        selected = [
            step
            for step in selected
            if step.name
            not in {
                "build_account_safe_facts",
                "materialize_action_time_ticket_sequence",
            }
        ]
    return selected


def _steps_for_mode(steps: list[RefreshStep], *, mode: str) -> list[RefreshStep]:
    names_by_mode = {
        "watcher_tick_summary": {
            "publish_runtime_control_current_projections_after_action_time",
        },
        "action_time": {
            "build_account_safe_facts",
            "materialize_action_time_ticket_sequence",
            "materialize_action_time_finalgate_preflight",
            "materialize_action_time_operation_layer_handoff",
            "materialize_ticket_bound_runtime_safety_state",
            "publish_runtime_control_current_projections_after_action_time",
        },
        "closure": {
            "materialize_ticket_bound_post_submit_closure",
            "publish_runtime_control_current_projections_after_action_time",
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
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            check=False,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=DEFAULT_STEP_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            returncode=124,
            stdout=str(exc.stdout or ""),
            stderr=(
                f"step_timeout_after_{DEFAULT_STEP_TIMEOUT_SECONDS}s:"
                f"{command[1] if len(command) > 1 else command[0]}"
            ),
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
    return CommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        duration_ms=int((time.perf_counter() - started) * 1000),
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
