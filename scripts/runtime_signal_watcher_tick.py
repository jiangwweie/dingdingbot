#!/usr/bin/env python3
"""Run one read-only runtime signal watcher tick with optional Feishu wake-up.

The watcher is intentionally one-shot so it can be driven by a systemd timer.
It builds runtime status in memory, persists current coverage to PG, emits a
stdout summary, and only sends a notification when owner attention is required.
It never writes recurring JSON/MD reports, submits, places orders, calls
OrderLifecycle, mutates runtime budget, or transfers funds.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import shlex
import sys
import time
from typing import Any, Callable
import urllib.error
import urllib.request

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import runtime_active_observation_monitor as active_monitor  # noqa: E402
from scripts.build_runtime_observation_operator_evidence import (  # noqa: E402
    build_operator_evidence,
)
from scripts.preview_strategy_group_readonly_observation import (  # noqa: E402
    build_preview_artifact,
)
from scripts.build_runtime_observation_wakeup_evidence import (  # noqa: E402
    build_wakeup_evidence,
)
from scripts.pg_dsn import normalize_sync_postgres_dsn  # noqa: E402


OWNER_ATTENTION_STATUSES = {
    "blocked_forbidden_effect",
    "runtime_signal_ready_for_non_executing_prepare",
    "prepared_shadow_evidence_ready_for_owner_review",
    "operator_evidence_needs_review",
}
WAITING_STATUS = "waiting_for_signal"
STOP_STATUSES = {
    "ready_for_prepare",
    "ready_for_final_gate_preflight",
    "blocked",
    "mixed",
    "no_active_runtimes",
}
STATUS_ARTIFACT_ATTENTION_STATUSES = {
    "attention",
    "blocked",
    "blocked_forbidden_effect",
    "stale",
}


Notifier = Callable[[str, str | None, dict[str, Any], float], dict[str, Any]]
SupervisorBuilder = Callable[[argparse.Namespace], dict[str, Any]]
FEISHU_WEBHOOK_URL_ENV_NAMES = (
    "BRC_SIGNAL_WATCHER_FEISHU_WEBHOOK_URL",
    "FEISHU_WEBHOOK_URL",
)
FEISHU_WEBHOOK_SECRET_ENV_NAMES = (
    "BRC_SIGNAL_WATCHER_FEISHU_WEBHOOK_SECRET",
    "FEISHU_WEBHOOK_SECRET",
)
_PROCESS_NOTIFICATION_STATE: dict[str, dict[str, Any]] = {}


def _env_file_values(path_value: str | None, names: tuple[str, ...]) -> dict[str, str]:
    if not path_value:
        return {}
    path = Path(path_value).expanduser()
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if key not in names or key in values:
            continue
        try:
            parsed = shlex.split(raw_value, comments=False, posix=True)
        except ValueError:
            parsed = []
        value = parsed[0] if len(parsed) == 1 else raw_value.strip().strip("\"'")
        if value:
            values[key] = value
    return values


def _first_env_value(
    names: tuple[str, ...],
    *,
    env_file: str | None = None,
) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    env_values = _env_file_values(env_file, names)
    for name in names:
        value = env_values.get(name)
        if value:
            return value
    return None


def _webhook_url(args: argparse.Namespace) -> str | None:
    return (
        args.feishu_webhook_url
        or _first_env_value(FEISHU_WEBHOOK_URL_ENV_NAMES, env_file=args.env_file)
        or None
    )


def _webhook_secret(args: argparse.Namespace) -> str | None:
    return (
        args.feishu_webhook_secret
        or _first_env_value(FEISHU_WEBHOOK_SECRET_ENV_NAMES, env_file=args.env_file)
        or None
    )


def _feishu_signature(timestamp: int, secret: str) -> str:
    key = f"{timestamp}\n{secret}".encode("utf-8")
    digest = hmac.new(key, b"", hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def _feishu_text_body(text: str, *, secret: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "msg_type": "text",
        "content": {"text": text},
    }
    if secret:
        timestamp = int(time.time())
        body["timestamp"] = str(timestamp)
        body["sign"] = _feishu_signature(timestamp, secret)
    return body


def send_feishu_text(
    webhook_url: str,
    webhook_secret: str | None,
    body: dict[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    request_body = _feishu_text_body(body["text"], secret=webhook_secret)
    payload = json.dumps(request_body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            return {
                "sent": 200 <= int(response.status) < 300,
                "status_code": int(response.status),
                "response_body_preview": response_body[:500],
            }
    except urllib.error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        return {
            "sent": False,
            "status_code": int(exc.code),
            "response_body_preview": response_body[:500],
        }
    except Exception as exc:  # pragma: no cover - network dependent
        return {
            "sent": False,
            "status_code": None,
            "error": f"{type(exc).__name__}:{str(exc)[:240]}",
        }


def _event_key(
    *,
    status_artifact: dict[str, Any],
    operator_evidence: dict[str, Any],
    wakeup_evidence: dict[str, Any],
) -> str:
    summary = wakeup_evidence.get("summary") if isinstance(wakeup_evidence.get("summary"), dict) else {}
    parts = [
        str(wakeup_evidence.get("status") or ""),
        str(operator_evidence.get("status") or ""),
        str(status_artifact.get("latest_status") or ""),
        str(summary.get("prepared_authorization_id") or ""),
        str(summary.get("shadow_candidate_id") or ""),
    ]
    return "|".join(parts)


def _notification_required(
    *,
    args: argparse.Namespace,
    status_artifact: dict[str, Any],
    wakeup_evidence: dict[str, Any],
    auto_resume: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    auto_resume_status = str((auto_resume or {}).get("status") or "")
    if auto_resume_status == "waiting_for_market":
        return False, "waiting_for_market_no_owner_attention_needed"
    wakeup_status = str(wakeup_evidence.get("status") or "")
    status_status = str(status_artifact.get("status") or "")
    if args.notify_no_signal and wakeup_status in {
        "owner_sleep_safe_observation_running",
        "observation_window_complete_no_signal",
    }:
        return True, "notify_no_signal_enabled"
    if wakeup_status in OWNER_ATTENTION_STATUSES:
        return True, f"wakeup_status:{wakeup_status}"
    if status_status in STATUS_ARTIFACT_ATTENTION_STATUSES:
        return True, f"status_artifact:{status_status}"
    return False, "no_owner_attention_needed"


def _notification_text(
    *,
    args: argparse.Namespace,
    status_artifact: dict[str, Any],
    operator_evidence: dict[str, Any],
    wakeup_evidence: dict[str, Any],
    paths: dict[str, str],
) -> str:
    summary = wakeup_evidence.get("summary") if isinstance(wakeup_evidence.get("summary"), dict) else {}
    monitored_count = summary.get("monitored_runtime_count")
    active_count = summary.get("active_runtime_count")
    if monitored_count is None:
        runtime_count_line = f"active runtimes: {active_count}"
    elif active_count is not None and active_count != monitored_count:
        runtime_count_line = f"monitored runtimes: {monitored_count} (active total: {active_count})"
    else:
        runtime_count_line = f"monitored runtimes: {monitored_count}"
    operator_plan = operator_evidence.get("operator_review_plan") or {}
    lines = [
        f"BRC runtime signal watcher: {wakeup_evidence.get('status')}",
        f"env: {args.label}",
        f"operator: {operator_evidence.get('status')}",
        runtime_count_line,
        f"ready runtime signals: {summary.get('runtime_ready_signal_count')}",
        f"prepared authorization: {summary.get('prepared_authorization_id') or '-'}",
        f"shadow candidate: {summary.get('shadow_candidate_id') or '-'}",
        f"next: {summary.get('next_step') or operator_plan.get('next_step') or '-'}",
        f"evidence: {paths.get('wakeup_evidence_ref')}",
    ]
    blockers = status_artifact.get("blockers") or operator_evidence.get("blockers") or []
    if blockers:
        lines.append("blockers: " + ", ".join(str(item) for item in blockers[:6]))
    return "\n".join(lines)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _nested_get(value: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = value
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _active_observation_plan_projection(
    artifact: dict[str, Any], preferred_key: str
) -> dict[str, Any]:
    plan = artifact.get(preferred_key)
    return plan if isinstance(plan, dict) else {}


def _active_observation_signal_input_json(artifact: dict[str, Any]) -> str | None:
    for candidate in (
        artifact.get("signal_input_json"),
        _nested_get(artifact, ("observation_monitor_plan", "signal_input_json")),
        _nested_get(artifact, ("latest_artifact", "signal_input_json")),
        _nested_get(
            artifact,
            ("latest_artifact", "observation_cycle_plan", "signal_input_json"),
        ),
    ):
        text = str(candidate or "").strip()
        if text:
            return text

    for item in artifact.get("runtime_summaries") or []:
        if not isinstance(item, dict):
            continue
        for candidate in (
            item.get("signal_input_json"),
            _nested_get(item, ("observation_monitor_plan", "signal_input_json")),
            _nested_get(item, ("latest_artifact", "signal_input_json")),
            _nested_get(
                item,
                ("latest_artifact", "observation_cycle_plan", "signal_input_json"),
            ),
        ):
            text = str(candidate or "").strip()
            if text:
                return text
    return None


def _active_observation_prepared_authorization_id(
    artifact: dict[str, Any],
) -> str | None:
    plan = artifact.get("observation_monitor_plan")
    if isinstance(plan, dict):
        text = str(plan.get("prepared_authorization_id") or "").strip()
        if text:
            return text

    for item in artifact.get("runtime_summaries") or []:
        if not isinstance(item, dict):
            continue
        for candidate in (
            item.get("prepared_authorization_id"),
            _nested_get(item, ("observation_monitor_plan", "prepared_authorization_id")),
            _nested_get(
                item,
                (
                    "latest_artifact",
                    "observation_cycle_plan",
                    "prepared_authorization_id",
                ),
            ),
            _nested_get(
                item,
                ("latest_artifact", "prepare_evidence", "ids", "authorization_id"),
            ),
            _nested_get(
                item,
                (
                    "latest_artifact",
                    "prepare_evidence",
                    "first_real_submit_prepare_report",
                    "ids",
                    "authorization_id",
                ),
            ),
        ):
            text = str(candidate or "").strip()
            if text:
                return text
    return None


def _active_observation_runtime_signal_summaries(
    artifact: dict[str, Any],
) -> list[dict[str, Any]]:
    summaries = artifact.get("runtime_summaries")
    if not isinstance(summaries, list):
        return []
    result: list[dict[str, Any]] = []
    for item in summaries:
        if not isinstance(item, dict):
            continue
        result.append(
            {
                "runtime_instance_id": item.get("runtime_instance_id"),
                "symbol": item.get("symbol"),
                "side": item.get("side"),
                "strategy_family_id": item.get("strategy_family_id"),
                "strategy_family_version_id": item.get(
                    "strategy_family_version_id"
                ),
                "status": item.get("status"),
                "blockers": list(item.get("blockers") or []),
                "signal_input_json": item.get("signal_input_json"),
                "prepared_authorization_id": item.get("prepared_authorization_id"),
                "signal_summary": item.get("signal_summary") or {},
            }
        )
    return result


def _active_observation_summary(
    artifact: dict[str, Any], *, iteration: int, cycle_dir: Path
) -> dict[str, Any]:
    safety = artifact.get("safety_invariants")
    if not isinstance(safety, dict):
        safety = {}
    plan = _active_observation_plan_projection(artifact, "observation_monitor_plan")
    return {
        "iteration": iteration,
        "cycle_dir": str(cycle_dir),
        "status": str(artifact.get("status") or "unknown"),
        "active_runtime_count": artifact.get("active_runtime_count"),
        "monitored_runtime_count": artifact.get("monitored_runtime_count"),
        "selected_runtime_instance_ids": list(
            artifact.get("selected_runtime_instance_ids") or []
        ),
        "prepare_records_created": bool(safety.get("prepare_records_created")),
        "shadow_candidate_created": bool(safety.get("shadow_candidate_created")),
        "runtime_execution_intent_draft_created": bool(
            safety.get("runtime_execution_intent_draft_created")
        ),
        "recorded_execution_intent_created": bool(
            safety.get("recorded_execution_intent_created")
        ),
        "submit_authorization_created": bool(
            safety.get("submit_authorization_created")
        ),
        "protection_plan_created": bool(safety.get("protection_plan_created")),
        "executable_execution_intent_created": bool(
            safety.get("executable_execution_intent_created")
        ),
        "ready_for_final_gate_preflight": (
            artifact.get("status") == "ready_for_final_gate_preflight"
        ),
        "creates_shadow_candidate": bool(plan.get("creates_shadow_candidate")),
        "creates_execution_intent": bool(plan.get("creates_execution_intent")),
        "places_order": bool(plan.get("places_order")),
        "calls_order_lifecycle": bool(plan.get("calls_order_lifecycle")),
        "exchange_write_called": bool(safety.get("exchange_write_called")),
        "order_created": bool(safety.get("order_created")),
        "order_lifecycle_called": bool(safety.get("order_lifecycle_called")),
        "attempt_counter_mutated": bool(safety.get("attempt_counter_mutated")),
        "runtime_budget_mutated": bool(safety.get("runtime_budget_mutated")),
        "withdrawal_or_transfer_created": bool(
            safety.get("withdrawal_or_transfer_created")
        ),
        "blockers": list(artifact.get("blockers") or []),
        "warnings": list(artifact.get("warnings") or []),
        "signal_input_json": _active_observation_signal_input_json(artifact),
        "prepared_authorization_id": _active_observation_prepared_authorization_id(
            artifact
        ),
        "runtime_signal_summaries": _active_observation_runtime_signal_summaries(
            artifact
        ),
        "candidate_universe_coverage": artifact.get("candidate_universe_coverage")
        or {},
    }


def _post_signal_auto_resume_plan(
    *,
    args: argparse.Namespace,
    status_artifact: dict[str, Any],
    operator_evidence: dict[str, Any],
    wakeup_evidence: dict[str, Any],
) -> dict[str, Any]:
    latest_status = str(status_artifact.get("latest_status") or "")
    status_status = str(status_artifact.get("status") or "")
    wakeup_status = str(wakeup_evidence.get("status") or "")
    operator_status = str(operator_evidence.get("status") or "")
    forbidden_effects = list(status_artifact.get("forbidden_effects") or [])
    blockers = [str(item) for item in status_artifact.get("blockers") or []]
    prepared_authorization_id = status_artifact.get("prepared_authorization_id")
    shadow_candidate_id = status_artifact.get("shadow_candidate_id")
    signal_input_json = status_artifact.get("signal_input_json")
    summary = _as_dict(wakeup_evidence.get("summary"))
    prepared_authorization_id = (
        prepared_authorization_id or summary.get("prepared_authorization_id")
    )
    shadow_candidate_id = shadow_candidate_id or summary.get("shadow_candidate_id")
    signal_input_json = signal_input_json or summary.get("signal_input_json")

    base = {
        "source": "runtime_signal_watcher_tick",
        "latest_status": latest_status,
        "watcher_status_evidence_status": status_status,
        "wakeup_status": wakeup_status,
        "operator_status": operator_status,
        "signal_input_json": signal_input_json,
        "prepared_authorization_id": prepared_authorization_id,
        "shadow_candidate_id": shadow_candidate_id,
        "allow_prepare_records": bool(args.allow_prepare_records),
        "requires_action_time_final_gate": True,
        "requires_official_operation_layer": True,
        "places_order": False,
        "calls_order_lifecycle": False,
        "withdrawal_or_transfer_requested": False,
    }

    if forbidden_effects or wakeup_status == "blocked_forbidden_effect":
        return {
            **base,
            "status": "blocked_hard_safety_stop",
            "blocked_at": "watcher_forbidden_effects",
            "blocked_reason": ",".join(forbidden_effects) or wakeup_status,
            "next_recover_condition": "forbidden_effect_flags_are_absent",
            "non_authority_checkpoint": "stop_and_investigate_watcher_evidence",
            "checkpoint_source": "runtime_signal_watcher_tick",
            "downgrade_mode": "manual_review_only",
            "can_continue_without_owner_chat": False,
            "creates_shadow_candidate": False,
            "creates_execution_intent": False,
        }

    if status_status == "stale":
        return {
            **base,
            "status": "blocked_observation_evidence",
            "blocked_at": "active_observation_status",
            "blocked_reason": status_status,
            "next_recover_condition": "fresh_non_forbidden_observation_artifacts_exist",
            "non_authority_checkpoint": "refresh_or_restart_active_observation_status",
            "checkpoint_source": "runtime_signal_watcher_tick",
            "downgrade_mode": "observe_only_no_candidate_prepare",
            "can_continue_without_owner_chat": False,
            "creates_shadow_candidate": False,
            "creates_execution_intent": False,
        }

    if prepared_authorization_id:
        return {
            **base,
            "status": "ready_for_action_time_final_gate",
            "blocked_at": "FinalGate",
            "blocked_reason": "action_time_final_gate_not_run_yet",
            "next_recover_condition": (
                "official_final_gate_preflight_passes_with_current_facts"
            ),
            "non_authority_checkpoint": "run_official_action_time_final_gate_preflight",
            "checkpoint_source": "runtime_signal_watcher_tick",
            "downgrade_mode": "no_real_submit_until_final_gate_pass",
            "can_continue_without_owner_chat": True,
            "creates_shadow_candidate": bool(
                shadow_candidate_id or prepared_authorization_id
            ),
            "creates_execution_intent": False,
        }

    ready_prepare_statuses = {
        "ready_for_prepare",
        "ready_for_prepare_records",
        "runtime_signal_ready_for_non_executing_prepare",
        "prepared_shadow_evidence_ready_for_owner_review",
    }
    if (
        latest_status in ready_prepare_statuses
        or wakeup_status in ready_prepare_statuses
        or bool(signal_input_json)
    ):
        non_authority_checkpoint = (
            "wait_for_prepare_records_then_rebuild_final_gate_status"
            if args.allow_prepare_records
            else "rerun_watcher_tick_with_allow_prepare_records"
        )
        return {
            **base,
            "status": "ready_for_non_executing_prepare",
            "blocked_at": "non_executing_prepare_records",
            "blocked_reason": "fresh_strategy_signal_ready",
            "next_recover_condition": (
                "shadow_candidate_runtime_grant_authorization_evidence_exists"
            ),
            "non_authority_checkpoint": non_authority_checkpoint,
            "checkpoint_source": "runtime_signal_watcher_tick",
            "downgrade_mode": "armed_observation_no_real_submit",
            "can_continue_without_owner_chat": True,
            "creates_shadow_candidate": bool(args.allow_prepare_records),
            "creates_execution_intent": False,
        }

    if status_status == "blocked":
        return {
            **base,
            "status": "blocked_observation_evidence",
            "blocked_at": "active_observation_status",
            "blocked_reason": status_status,
            "next_recover_condition": "fresh_non_forbidden_observation_artifacts_exist",
            "non_authority_checkpoint": "refresh_or_restart_active_observation_status",
            "checkpoint_source": "runtime_signal_watcher_tick",
            "downgrade_mode": "observe_only_no_candidate_prepare",
            "can_continue_without_owner_chat": False,
            "creates_shadow_candidate": False,
            "creates_execution_intent": False,
        }

    no_signal = (
        "strategy_signal_not_ready_for_shadow_candidate_prepare" in ",".join(blockers)
        or status_status
        in {"waiting_for_signal", "observation_window_complete_no_signal", "ok"}
        or wakeup_status
        in {
            "operator_evidence_needs_review",
            "owner_sleep_safe_observation_running",
            "observation_window_complete_no_signal",
        }
    )
    if no_signal:
        return {
            **base,
            "status": "waiting_for_market",
            "blocked_at": "watcher_signal",
            "blocked_reason": "no_fresh_strategy_signal",
            "next_recover_condition": (
                "runtime_signal_watcher_observes_a_fresh_signal_for_selected_scope"
            ),
            "non_authority_checkpoint": "continue_watcher_observation",
            "checkpoint_source": "runtime_signal_watcher_tick",
            "downgrade_mode": "observe_only",
            "can_continue_without_owner_chat": True,
            "creates_shadow_candidate": False,
            "creates_execution_intent": False,
        }

    return {
        **base,
        "status": "blocked_operator_review",
        "blocked_at": "operator_evidence",
        "blocked_reason": wakeup_status or operator_status or "unknown",
        "next_recover_condition": "operator_evidence_maps_to_waiting_or_ready_signal",
        "non_authority_checkpoint": "rebuild_operator_and_wakeup_evidence",
        "checkpoint_source": "runtime_signal_watcher_tick",
        "downgrade_mode": "observe_only_no_candidate_prepare",
        "can_continue_without_owner_chat": False,
        "creates_shadow_candidate": False,
        "creates_execution_intent": False,
    }


def _supervisor_args(args: argparse.Namespace, output_dir: Path) -> argparse.Namespace:
    return argparse.Namespace(
        output_dir=str(output_dir),
        env_file=args.env_file,
        api_base=args.api_base,
        source=args.source,
        runtime_instance_id=list(args.runtime_instance_id or []),
        strategy_family_id=list(args.strategy_family_id or []),
        database_url=normalize_sync_postgres_dsn(getattr(args, "database_url", "")),
        require_database_url=getattr(args, "require_database_url", False),
        allow_non_postgres_for_test=getattr(args, "allow_non_postgres_for_test", False),
        max_iterations=args.max_iterations,
        loop_interval_seconds=args.loop_interval_seconds,
        cycle_timeout_seconds=args.cycle_timeout_seconds,
        status_stale_after_seconds=args.status_stale_after_seconds,
        one_hour_limit=args.one_hour_limit,
        four_hour_limit=args.four_hour_limit,
        allow_prepare_records=args.allow_prepare_records,
        allow_arm_preview=args.allow_arm_preview,
        allow_attempt_policy_prepare=args.allow_attempt_policy_prepare,
        allow_disabled_smoke=args.allow_disabled_smoke,
        allow_standing_operation_layer_evidence_prep=(
            getattr(args, "allow_standing_operation_layer_evidence_prep", False)
        ),
        include_artifacts=args.include_artifacts,
        skip_disabled_smoke_prerequisite_probe=(
            args.skip_disabled_smoke_prerequisite_probe
        ),
    )


def _monitor_args(args: argparse.Namespace, output_dir: Path) -> argparse.Namespace:
    return argparse.Namespace(
        env_file=args.env_file,
        api_base=args.api_base,
        source=args.source,
        include_exchange=False,
        allow_prepare_records=args.allow_prepare_records,
        runtime_instance_id=list(args.runtime_instance_id or []),
        strategy_family_id=list(args.strategy_family_id or []),
        database_url=normalize_sync_postgres_dsn(getattr(args, "database_url", "")),
        require_database_url=getattr(args, "require_database_url", False),
        allow_non_postgres_for_test=getattr(args, "allow_non_postgres_for_test", False),
        max_runtimes=100,
        max_cycles_per_runtime=1,
        interval_seconds=0.0,
        continue_on_blocked=False,
        one_hour_limit=args.one_hour_limit,
        four_hour_limit=args.four_hour_limit,
        timeout_seconds=args.cycle_timeout_seconds,
        playbook_id=None,
        output_dir=str(output_dir),
        write_runtime_artifacts=False,
        include_runtime_artifacts=args.include_artifacts,
        owner_operator_id="owner",
        owner_confirmation_reference=(
            "owner-authorized-runtime-signal-watcher-in-memory-observation"
        ),
        reason="runtime signal watcher in-memory active observation",
    )


def _status_from_loop_artifact(
    *,
    output_dir: Path,
    supervisor_artifact: dict[str, Any],
    loop_artifact: dict[str, Any],
    latest_summary: dict[str, Any],
    stale_after_seconds: float,
) -> dict[str, Any]:
    latest_status = str(loop_artifact.get("status") or latest_summary.get("status") or "")
    stop_reason = str(loop_artifact.get("stop_reason") or "")
    status = "ok"
    if latest_status == "blocked":
        status = "blocked"
    elif latest_status in {
        "ready_for_prepare",
        "ready_for_prepare_records",
        "ready_for_final_gate_preflight",
        "ready_for_disabled_smoke",
        "disabled_smoke_completed",
    }:
        status = "attention"
    elif latest_status == "waiting_for_signal" and stop_reason == "max_iterations_exhausted":
        status = "observation_window_complete_no_signal"
    elif latest_status == "waiting_for_signal":
        status = "waiting_for_signal"

    iterations_requested = int(loop_artifact.get("iterations_requested") or 1)
    iterations_completed = int(loop_artifact.get("iterations_completed") or 1)
    safety = loop_artifact.get("safety_invariants")
    if not isinstance(safety, dict):
        safety = {}
    observed_flags = {
        "prepare_records_created": bool(safety.get("prepare_records_created")),
        "shadow_candidate_created": bool(safety.get("shadow_candidate_created")),
        "runtime_execution_intent_draft_created": bool(
            safety.get("runtime_execution_intent_draft_created")
        ),
        "recorded_execution_intent_created": bool(
            safety.get("recorded_execution_intent_created")
        ),
        "submit_authorization_created": bool(safety.get("submit_authorization_created")),
        "protection_plan_created": bool(safety.get("protection_plan_created")),
    }
    forbidden_effects = [
        name
        for name in (
            "exchange_write_called",
            "order_created",
            "order_lifecycle_called",
            "attempt_counter_mutated",
            "runtime_budget_mutated",
            "withdrawal_or_transfer_created",
        )
        if bool(safety.get(name))
    ]
    blockers = list(loop_artifact.get("blockers") or [])
    if forbidden_effects:
        status = "blocked_forbidden_effect"
        blockers.append("active_observation_forbidden_effects_detected")

    return {
        "scope": "runtime_signal_watcher_in_memory_status",
        "status": status,
        "output_dir": str(output_dir),
        "latest_status": latest_status or None,
        "latest_artifact": "memory:runtime_signal_watcher_in_memory_observation",
        "artifact_sources": [
            {
                "role": "supervisor",
                "artifact_name": "memory:supervisor",
                "source_path": "memory:supervisor",
                "loaded": True,
            },
            {
                "role": "loop",
                "artifact_name": "memory:loop",
                "source_path": "memory:loop",
                "loaded": True,
            },
            {
                "role": "latest_summary",
                "artifact_name": "memory:latest_summary",
                "source_path": "memory:latest_summary",
                "loaded": True,
            },
        ],
        "latest_artifact_age_seconds": 0,
        "stale_after_seconds": float(stale_after_seconds),
        "artifact_stale": False,
        "supervisor_status": supervisor_artifact.get("status"),
        "loop_status": latest_status or None,
        "followup_status": None,
        "iterations_requested": iterations_requested,
        "iterations_completed": iterations_completed,
        "iterations_remaining": max(iterations_requested - iterations_completed, 0),
        "latest_iteration": latest_summary.get("iteration"),
        "stop_reason": stop_reason or None,
        "observation_running": stop_reason == "running",
        "observation_window_complete": stop_reason == "max_iterations_exhausted",
        "active_runtime_count": latest_summary.get("active_runtime_count"),
        "monitored_runtime_count": latest_summary.get("monitored_runtime_count"),
        "selected_runtime_instance_ids": list(
            latest_summary.get("selected_runtime_instance_ids") or []
        ),
        "signal_input_json": latest_summary.get("signal_input_json"),
        "prepared_authorization_id": latest_summary.get("prepared_authorization_id"),
        "shadow_candidate_id": latest_summary.get("shadow_candidate_id"),
        "runtime_signal_summaries": _flatten_runtime_signal_summaries(
            latest_summary.get("runtime_signal_summaries")
        ),
        "candidate_universe_coverage": latest_summary.get("candidate_universe_coverage")
        or {},
        "blockers": blockers,
        "warnings": list(loop_artifact.get("warnings") or []),
        "forbidden_effects": forbidden_effects,
        "allowed_prepare_record_effects": [
            name for name, observed in observed_flags.items() if observed
        ],
        "allowed_operation_layer_evidence_prep_effects": [],
        "observation_plan": {
            "not_execution_authority": True,
            "observation_next_step": (
                "review_non_executing_prepare_or_preview_artifact"
                if status == "attention"
                else "continue_active_observation_loop"
            ),
        },
        "safety_invariants": {
            "read_artifacts_only": False,
            "in_memory_observation_status": True,
            "connects_to_api": False,
            "connects_to_exchange": False,
            "creates_prepare_records": False,
            "observed_prepare_records_created": observed_flags[
                "prepare_records_created"
            ],
            "observed_shadow_candidate_created": observed_flags[
                "shadow_candidate_created"
            ],
            "observed_runtime_execution_intent_draft_created": observed_flags[
                "runtime_execution_intent_draft_created"
            ],
            "observed_recorded_execution_intent_created": observed_flags[
                "recorded_execution_intent_created"
            ],
            "observed_submit_authorization_created": observed_flags[
                "submit_authorization_created"
            ],
            "observed_protection_plan_created": observed_flags[
                "protection_plan_created"
            ],
            "creates_shadow_candidate": False,
            "creates_execution_intent": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "mutates_runtime_budget": False,
            "mutates_attempt_counter": False,
            "withdrawal_or_transfer_created": False,
            "forbidden_effects": forbidden_effects,
            "allowed_operation_layer_evidence_prep_effects": [],
        },
    }


def _flatten_runtime_signal_summaries(rows: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        signal = row.get("signal_summary")
        if not isinstance(signal, dict):
            signal = {}
        result.append(
            {
                "runtime_instance_id": row.get("runtime_instance_id"),
                "strategy_family_id": row.get("strategy_family_id"),
                "strategy_family_version_id": row.get("strategy_family_version_id"),
                "symbol": row.get("symbol"),
                "side": row.get("side"),
                "status": row.get("status"),
                "signal_input_json": row.get("signal_input_json"),
                "prepared_authorization_id": row.get("prepared_authorization_id"),
                "evaluation_status": signal.get("evaluation_status"),
                "signal_type": signal.get("signal_type"),
                "signal_side": signal.get("side"),
                "confidence": signal.get("confidence"),
                "reason_codes": signal.get("reason_codes") or [],
                "human_summary": signal.get("human_summary"),
            }
        )
    return result


def _build_in_memory_supervisor_artifact(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = Path(args.output_dir).expanduser()
    monitor_args = _monitor_args(args, output_dir)
    monitor_artifact = active_monitor._build_monitor_artifact(monitor_args)
    monitor_artifact["pg_watcher_runtime_coverage"] = (
        active_monitor.write_candidate_universe_coverage_to_pg(
            monitor_artifact,
            database_url=str(getattr(monitor_args, "database_url", "") or ""),
            allow_non_postgres_for_test=bool(
                getattr(monitor_args, "allow_non_postgres_for_test", False)
            ),
        )
    )
    status = str(monitor_artifact.get("status") or "unknown")
    latest_summary = _active_observation_summary(
        monitor_artifact,
        iteration=1,
        cycle_dir=Path("memory/runtime-active-observation"),
    )
    should_stop = status in STOP_STATUSES or status != WAITING_STATUS
    stop_reason = (
        f"status_changed:{status}" if should_stop else "max_iterations_exhausted"
    )
    loop_artifact = {
        "scope": "runtime_signal_watcher_in_memory_observation",
        "status": status,
        "stop_reason": stop_reason,
        "iterations_requested": 1,
        "iterations_completed": 1,
        "latest_summary": latest_summary,
        "cycle_summaries": [latest_summary],
        "blockers": list(monitor_artifact.get("blockers") or []),
        "warnings": list(monitor_artifact.get("warnings") or []),
        "operator_review_plan": {
            "not_executed": True,
            "creates_execution_intent": False,
            "places_order": False,
            "calls_order_lifecycle": False,
        },
        "safety_invariants": monitor_artifact.get("safety_invariants") or {},
    }
    artifact = {
        "scope": "runtime_signal_watcher_in_memory_supervisor",
        "status": "supervisor_completed",
        "loop_status": status,
        "followup_status": None,
        "blockers": list(monitor_artifact.get("blockers") or []),
        "warnings": list(monitor_artifact.get("warnings") or []),
        "loop_artifact": loop_artifact,
        "latest_summary": latest_summary,
        "safety_invariants": {
            "supervisor_in_memory": True,
            "exchange_order_requested": False,
            "real_submit_requested": False,
            "forbidden_effects": [],
        },
    }
    artifact["status_artifact"] = _status_from_loop_artifact(
        output_dir=output_dir,
        supervisor_artifact=artifact,
        loop_artifact=loop_artifact,
        latest_summary=latest_summary,
        stale_after_seconds=float(args.status_stale_after_seconds),
    )
    return artifact


def _missing_status_artifact(*, supervisor_artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "scope": "runtime_signal_watcher_in_memory_status",
        "status": "blocked",
        "latest_status": "blocked",
        "latest_artifact": "memory:missing_status_artifact",
        "artifact_sources": [
            {
                "role": "supervisor",
                "artifact_name": "memory:supervisor",
                "source_path": "memory:supervisor",
                "loaded": bool(supervisor_artifact),
            }
        ],
        "artifact_stale": False,
        "blockers": ["in_memory_status_artifact_missing"],
        "warnings": [],
        "forbidden_effects": [],
        "observation_plan": {
            "not_execution_authority": True,
            "observation_next_step": "rebuild_in_memory_supervisor_status_artifact",
        },
        "safety_invariants": {
            "read_artifacts_only": False,
            "in_memory_observation_status": True,
            "connects_to_exchange": False,
            "creates_shadow_candidate": False,
            "creates_execution_intent": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "mutates_runtime_budget": False,
            "withdrawal_or_transfer_created": False,
            "forbidden_effects": [],
        },
    }


def build_watcher_tick_artifact(
    args: argparse.Namespace,
    *,
    supervisor_builder: SupervisorBuilder | None = None,
    notifier: Notifier | None = None,
) -> dict[str, Any]:
    output_dir = Path(args.output_dir).expanduser()
    state_key = f"{args.label}:{output_dir}"
    previous_state = dict(_PROCESS_NOTIFICATION_STATE.get(state_key) or {})

    supervisor_builder = supervisor_builder or _build_in_memory_supervisor_artifact
    supervisor_artifact = supervisor_builder(_supervisor_args(args, output_dir))
    status_artifact = (
        supervisor_artifact.get("status_artifact")
        if isinstance(supervisor_artifact.get("status_artifact"), dict)
        else _missing_status_artifact(supervisor_artifact=supervisor_artifact)
    )

    operator_evidence = build_operator_evidence(
        active_status_artifact=status_artifact,
        strategy_preview_artifact=build_preview_artifact(
            source_name=args.strategy_source,
        ),
    )

    wakeup_evidence = build_wakeup_evidence(operator_evidence)
    auto_resume = _post_signal_auto_resume_plan(
        args=args,
        status_artifact=status_artifact,
        operator_evidence=operator_evidence,
        wakeup_evidence=wakeup_evidence,
    )
    status_safety = status_artifact.get("safety_invariants")
    if not isinstance(status_safety, dict):
        status_safety = {}
    observed_prepare_records_created = bool(
        status_safety.get("observed_prepare_records_created")
    )
    observed_shadow_candidate_created = bool(
        status_safety.get("observed_shadow_candidate_created")
    )
    observed_runtime_execution_intent_draft_created = bool(
        status_safety.get("observed_runtime_execution_intent_draft_created")
    )
    observed_recorded_execution_intent_created = bool(
        status_safety.get("observed_recorded_execution_intent_created")
    )
    observed_submit_authorization_created = bool(
        status_safety.get("observed_submit_authorization_created")
    )
    observed_protection_plan_created = bool(
        status_safety.get("observed_protection_plan_created")
    )

    event_key = _event_key(
        status_artifact=status_artifact,
        operator_evidence=operator_evidence,
        wakeup_evidence=wakeup_evidence,
    )
    required, reason = _notification_required(
        args=args,
        status_artifact=status_artifact,
        wakeup_evidence=wakeup_evidence,
        auto_resume=auto_resume,
    )
    duplicate = previous_state.get("last_notified_event_key") == event_key
    webhook_url = _webhook_url(args)
    webhook_secret = _webhook_secret(args)
    paths = {
        "status_artifact_ref": "memory:runtime_signal_watcher_in_memory_status",
        "operator_evidence_ref": "memory:runtime_observation_operator_evidence",
        "wakeup_evidence_ref": "memory:runtime_observation_wakeup_evidence",
        "watcher_tick_ref": "stdout:runtime_signal_watcher_tick",
    }
    notification = {
        "required": required,
        "reason": reason,
        "duplicate_suppressed": False,
        "configured": bool(webhook_url),
        "secret_configured": bool(webhook_secret),
        "attempted": False,
        "sent": False,
        "skipped_reason": None,
    }
    if not required:
        notification["skipped_reason"] = "no_owner_attention_needed"
    elif duplicate:
        notification["duplicate_suppressed"] = True
        notification["skipped_reason"] = "event_already_notified"
    elif not webhook_url:
        notification["skipped_reason"] = "feishu_webhook_url_missing"
    else:
        message = _notification_text(
            args=args,
            status_artifact=status_artifact,
            operator_evidence=operator_evidence,
            wakeup_evidence=wakeup_evidence,
            paths=paths,
        )
        if args.notification_dry_run:
            notification.update(
                {
                    "attempted": False,
                    "sent": False,
                    "skipped_reason": "notification_dry_run",
                    "message_preview": message[:1000],
                }
            )
        else:
            sender = notifier or send_feishu_text
            result = sender(
                webhook_url,
                webhook_secret,
                {"text": message},
                args.notification_timeout_seconds,
            )
            notification.update({"attempted": True, **result})

    state = {
        "last_event_key": event_key,
        "last_wakeup_status": wakeup_evidence.get("status"),
        "last_operator_status": operator_evidence.get("status"),
        "last_watcher_status_evidence_status": status_artifact.get("status"),
        "last_observed_at_ms": int(time.time() * 1000),
        "last_notified_event_key": (
            event_key if notification.get("sent") else previous_state.get("last_notified_event_key")
        ),
    }
    _PROCESS_NOTIFICATION_STATE[state_key] = state

    artifact = {
        "scope": "runtime_signal_watcher_tick",
        "status": _tick_status(notification, wakeup_evidence, status_artifact),
        "output_dir": str(output_dir),
        "paths": paths,
        "event_key": event_key,
        "supervisor_status": supervisor_artifact.get("status"),
        "watcher_status_evidence_status": status_artifact.get("status"),
        "operator_status": operator_evidence.get("status"),
        "wakeup_status": wakeup_evidence.get("status"),
        "post_signal_auto_resume": auto_resume,
        "notification": notification,
        "blockers": list(status_artifact.get("blockers") or []),
        "warnings": list(status_artifact.get("warnings") or []),
        "watcher_tick_plan": {
            "not_executed": True,
            "non_authority_checkpoint": auto_resume["non_authority_checkpoint"],
            "checkpoint_source": "post_signal_auto_resume",
            "not_execution_authority": True,
            "wakeup_next_step": (wakeup_evidence.get("summary") or {}).get("next_step"),
            "records_observation_only": True,
            "sends_owner_wakeup_only": bool(notification.get("sent")),
            "can_continue_without_owner_chat": bool(
                auto_resume.get("can_continue_without_owner_chat")
            ),
            "creates_prepare_records": observed_prepare_records_created,
            "creates_shadow_candidate": observed_shadow_candidate_created
            or bool(auto_resume.get("creates_shadow_candidate")),
            "creates_execution_intent": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "requires_action_time_final_gate": bool(
                auto_resume.get("requires_action_time_final_gate")
            ),
            "requires_official_operation_layer": bool(
                auto_resume.get("requires_official_operation_layer")
            ),
            "withdrawal_or_transfer_requested": False,
        },
        "safety_invariants": {
            "watcher_tick_only": True,
            "uses_existing_active_observation_loop": True,
            "allow_prepare_records": bool(args.allow_prepare_records),
            "feishu_notification_only": True,
            "post_signal_auto_resume_decision_only": not observed_prepare_records_created,
            "prepare_records_created": observed_prepare_records_created,
            "shadow_candidate_created": observed_shadow_candidate_created,
            "runtime_execution_intent_draft_created": (
                observed_runtime_execution_intent_draft_created
            ),
            "recorded_execution_intent_created": (
                observed_recorded_execution_intent_created
            ),
            "submit_authorization_created": observed_submit_authorization_created,
            "protection_plan_created": observed_protection_plan_created,
            "allowed_prepare_record_effects": list(
                status_artifact.get("allowed_prepare_record_effects") or []
            ),
            "real_submit_requested": False,
            "exchange_order_requested": False,
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "execution_intent_created": False,
            "attempt_counter_mutated": False,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
            "forbidden_effects": list(status_artifact.get("forbidden_effects") or []),
        },
    }
    return artifact


def _tick_status(
    notification: dict[str, Any],
    wakeup_evidence: dict[str, Any],
    status_artifact: dict[str, Any],
) -> str:
    if wakeup_evidence.get("status") == "blocked_forbidden_effect":
        return "blocked_forbidden_effect"
    if status_artifact.get("status") in {"blocked", "blocked_forbidden_effect", "stale"}:
        return "watcher_attention"
    if notification.get("required") and notification.get("sent"):
        return "owner_notified"
    if notification.get("required"):
        return "owner_attention_pending"
    return "watching_no_signal"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one read-only runtime signal watcher tick and optional Feishu notification.",
    )
    parser.set_defaults(output_dir="memory/runtime-signal-watcher")
    parser.add_argument("--env-file")
    parser.add_argument("--api-base", default="http://127.0.0.1:18080")
    parser.add_argument("--source", choices=["live_market", "sample"], default="live_market")
    parser.add_argument(
        "--strategy-source",
        choices=["sample", "local_sqlite_read_only", "live_market"],
        default="live_market",
    )
    parser.add_argument("--runtime-instance-id", action="append", default=[])
    parser.add_argument("--strategy-family-id", action="append", default=[])
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument("--require-database-url", action="store_true")
    parser.add_argument("--allow-non-postgres-for-test", action="store_true")
    parser.add_argument("--max-iterations", type=int, default=1)
    parser.add_argument("--loop-interval-seconds", type=float, default=0.0)
    parser.add_argument("--cycle-timeout-seconds", type=float, default=180.0)
    parser.add_argument("--status-stale-after-seconds", type=float, default=900.0)
    parser.add_argument("--one-hour-limit", type=int, default=25)
    parser.add_argument("--four-hour-limit", type=int, default=25)
    parser.add_argument("--allow-prepare-records", action="store_true")
    parser.add_argument("--allow-arm-preview", action="store_true")
    parser.add_argument("--allow-attempt-policy-prepare", action="store_true")
    parser.add_argument("--allow-disabled-smoke", action="store_true")
    parser.add_argument(
        "--allow-standing-operation-layer-evidence-prep",
        action="store_true",
    )
    parser.add_argument(
        "--skip-disabled-smoke-prerequisite-probe",
        action="store_true",
        default=True,
    )
    parser.add_argument(
        "--run-disabled-smoke-prerequisite-probe",
        action="store_false",
        dest="skip_disabled_smoke_prerequisite_probe",
    )
    parser.add_argument("--include-artifacts", action="store_true")
    parser.add_argument("--notify-no-signal", action="store_true")
    parser.add_argument("--notification-dry-run", action="store_true")
    parser.add_argument("--notification-timeout-seconds", type=float, default=10.0)
    parser.add_argument("--feishu-webhook-url")
    parser.add_argument("--feishu-webhook-secret")
    parser.add_argument("--label", default="tokyo-runtime-signal-watcher")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    artifact = build_watcher_tick_artifact(args)
    print(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if artifact["status"] not in {"blocked_forbidden_effect"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
