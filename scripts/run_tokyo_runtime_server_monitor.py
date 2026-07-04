#!/usr/bin/env python3
"""Run the Tokyo server-side readonly runtime monitor.

This entrypoint is the production monitor owner described by
docs/current/SERVER_SIDE_RUNTIME_MONITOR_CONTRACT.md. It classifies server-side
runtime facts into quiet / notify and optionally sends a deduped Feishu message.
It is intentionally readonly for trading: no FinalGate, Operation Layer,
exchange write, order creation, profile mutation, sizing mutation, withdrawal,
or transfer path is called.
"""

from __future__ import annotations

import argparse
import base64
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any
import urllib.error
import urllib.request

import sqlalchemy as sa


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.infrastructure.runtime_control_state_repository import (  # noqa: E402
    PgBackedRuntimeControlStateRepository,
)

DEFAULT_REPORT_DIR = Path("/home/ubuntu/brc-deploy/reports/runtime-monitor")
DEFAULT_OUTPUT_JSON = DEFAULT_REPORT_DIR / "latest-server-side-runtime-monitor.json"
DEFAULT_DEDUPE_STATE_JSON = DEFAULT_REPORT_DIR / "server-monitor-dedupe-state.json"
DEFAULT_WATCHER_STATUS_JSON = (
    Path("/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/latest-status.json")
)
DEFAULT_DEPLOY_HEALTH_JSON = (
    Path("/home/ubuntu/brc-deploy/reports/runtime-monitor/latest-deploy-health.json")
)
DEFAULT_SYSTEMD_UNITS = (
    "brc-owner-console-backend.service",
    "brc-runtime-signal-watcher.timer",
    "brc-runtime-signal-watcher.service",
)
ONESHOT_INACTIVE_OK_UNITS = {
    "brc-runtime-signal-watcher.service",
    "brc-runtime-monitor.service",
}
MARKET_BLOCKERS = {
    "computed_not_satisfied",
    "market_wait_validated",
    "fresh_signal_absent",
    "fresh_cpm_long_signal_absent",
    "fresh_sor_session_range_signal_absent",
    "short_squeeze_risk_state_disable_active",
}
RUNTIME_DATA_GAP_BLOCKERS = {
    "watcher_tick_missing",
    "artifact_missing",
    "schema_invalid",
    "detector_not_attached",
}
FEISHU_WEBHOOK_URL_ENV_NAMES = (
    "BRC_RUNTIME_MONITOR_FEISHU_WEBHOOK_URL",
    "BRC_SIGNAL_WATCHER_FEISHU_WEBHOOK_URL",
    "FEISHU_WEBHOOK_URL",
)
FEISHU_WEBHOOK_SECRET_ENV_NAMES = (
    "BRC_RUNTIME_MONITOR_FEISHU_WEBHOOK_SECRET",
    "BRC_SIGNAL_WATCHER_FEISHU_WEBHOOK_SECRET",
    "FEISHU_WEBHOOK_SECRET",
)


Notifier = Callable[[str, str | None, dict[str, Any], float], dict[str, Any]]
SystemdRunner = Callable[[str], "CommandResult"]


@dataclass(frozen=True)
class CommandResult:
    stdout: str
    stderr: str
    returncode: int


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> tuple[dict[str, Any], str | None]:
    try:
        if not path.exists():
            return {}, "missing"
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {}, f"unreadable:{type(exc).__name__}:{str(exc)[:160]}"
    if not isinstance(payload, dict):
        return {}, "invalid_json_shape"
    return payload, None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _safe_status(payload: dict[str, Any]) -> str:
    return str(payload.get("status") or "")


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _feishu_signature(timestamp: int, secret: str) -> str:
    key = f"{timestamp}\n{secret}".encode("utf-8")
    digest = hmac.new(key, b"", hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def _feishu_text_body(text: str, *, secret: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"msg_type": "text", "content": {"text": text}}
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
    request_body = _feishu_text_body(str(body.get("text") or ""), secret=webhook_secret)
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


def _env_value(names: tuple[str, ...]) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def _run_systemctl(unit: str) -> CommandResult:
    result = subprocess.run(
        ["systemctl", "is-active", unit],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return CommandResult(
        stdout=result.stdout.strip(),
        stderr=result.stderr.strip(),
        returncode=int(result.returncode),
    )


def _systemd_status(
    units: list[str],
    *,
    runner: SystemdRunner | None = None,
) -> dict[str, Any]:
    run = runner or _run_systemctl
    rows: list[dict[str, Any]] = []
    blockers: list[str] = []
    for unit in units:
        result = run(unit)
        active = result.returncode == 0 and result.stdout == "active"
        inactive_success = (
            unit in ONESHOT_INACTIVE_OK_UNITS
            and result.returncode != 0
            and result.stdout == "inactive"
        )
        transient_active = (
            unit in ONESHOT_INACTIVE_OK_UNITS
            and result.stdout == "activating"
        )
        ready = active or inactive_success or transient_active
        rows.append(
            {
                "unit": unit,
                "active": active,
                "inactive_success": inactive_success,
                "transient_active": transient_active,
                "ready": ready,
                "stdout": result.stdout,
                "stderr_preview": result.stderr[:240],
                "returncode": result.returncode,
            }
        )
        if not ready:
            blockers.append(f"systemd_unit_not_active:{unit}:{result.stdout or result.returncode}")
    return {
        "checked": bool(units),
        "rows": rows,
        "ready": not blockers,
        "blockers": blockers,
    }


def _public_facts_ready(payload: dict[str, Any]) -> bool:
    checks = _as_dict(payload.get("checks"))
    if "public_facts_ready" in checks:
        return checks.get("public_facts_ready") is True
    return _safe_status(payload) in {
        "binance_usdm_public_facts_ready",
        "binance_usdm_public_facts_ready_from_fallback",
    }


def _account_safe_facts_ready(payload: dict[str, Any]) -> bool:
    checks = _as_dict(payload.get("checks"))
    if "account_safe_facts_ready" in checks:
        return checks.get("account_safe_facts_ready") is True
    if "account_safe" in checks:
        return checks.get("account_safe") is True
    return _safe_status(payload) in {
        "account_safe_facts_ready",
        "runtime_account_safe_facts_ready",
        "ready",
    }


def _deploy_health_ready(payload: dict[str, Any]) -> bool:
    if not payload:
        return False
    checks = _as_dict(payload.get("checks"))
    if "ready" in checks:
        return checks.get("ready") is True
    if "postdeploy_acceptance_passed" in checks:
        return checks.get("postdeploy_acceptance_passed") is True
    return _safe_status(payload) in {
        "ready",
        "postdeploy_acceptance_passed",
        "deploy_health_ready",
    }


def _watcher_ready(payload: dict[str, Any]) -> bool:
    if not payload:
        return False
    status = _safe_status(payload)
    latest = str(payload.get("latest_status") or "")
    return status in {"ok", "watching_no_signal", "owner_notified"} or latest in {
        "waiting_for_signal",
        "owner_sleep_safe_observation_running",
        "observation_window_complete_no_signal",
    }


def _daily_table_has_non_market_blocker(daily_table: dict[str, Any]) -> dict[str, Any] | None:
    for row in _as_list(daily_table.get("rows")):
        row_dict = _as_dict(row)
        blocker = str(row_dict.get("first_blocker") or "")
        if blocker and blocker not in MARKET_BLOCKERS:
            return row_dict
    return None


def _candidate_pool_fresh_or_action_time(candidate_pool: dict[str, Any]) -> dict[str, Any] | None:
    lane_inputs = _as_list(candidate_pool.get("action_time_lane_inputs"))
    if lane_inputs:
        row = dict(_as_dict(lane_inputs[0]) or {"status": "action_time_lane_input_present"})
        row["_server_monitor_event_type"] = "action_time_lane_input"
        return row
    promotion_candidates = _as_list(candidate_pool.get("promotion_candidates"))
    if promotion_candidates:
        row = dict(_as_dict(promotion_candidates[0]) or {"status": "promotion_candidate_present"})
        row["_server_monitor_event_type"] = "promotion_candidate"
        return row
    for row in _as_list(candidate_pool.get("symbol_readiness_rows")):
        row_dict = _as_dict(row)
        if str(row_dict.get("signal_state") or "") == "fresh":
            row_copy = dict(row_dict)
            row_copy["_server_monitor_event_type"] = "fresh_signal"
            return row_copy
    for row in _as_list(candidate_pool.get("candidate_rows")):
        row_dict = _as_dict(row)
        readiness = _as_dict(row_dict.get("action_time_readiness"))
        if (
            row_dict.get("fresh_signal_present") is True
            or readiness.get("fresh_signal_present") is True
            or readiness.get("action_time_path_ready") is True
            or str(readiness.get("status") or "") in {
                "action_time_ready",
                "ready_for_action_time_boundary",
                "fresh_signal_ready",
            }
        ):
            row_copy = dict(row_dict)
            row_copy["_server_monitor_event_type"] = "legacy_fresh_signal"
            return row_copy
    return None


def _runtime_data_gap_from_candidate_pool(candidate_pool: dict[str, Any]) -> dict[str, Any] | None:
    for row in _as_list(candidate_pool.get("symbol_readiness_rows")):
        row_dict = _as_dict(row)
        blocker = str(row_dict.get("first_blocker") or "")
        if blocker in RUNTIME_DATA_GAP_BLOCKERS:
            return row_dict
    for row in _as_list(candidate_pool.get("candidate_rows")):
        row_dict = _as_dict(row)
        blocker = str(row_dict.get("first_blocker") or "")
        readiness = _as_dict(row_dict.get("action_time_readiness"))
        readiness_status = str(readiness.get("status") or "")
        if blocker in RUNTIME_DATA_GAP_BLOCKERS:
            return row_dict
        if blocker not in MARKET_BLOCKERS and readiness_status in {
            "blocked_public_facts",
            "blocked_account_safe_facts",
            "blocked_watcher_tick",
        }:
            return row_dict
    return None


def _decision_from_sources(
    *,
    daily_table: dict[str, Any],
    candidate_pool: dict[str, Any],
    public_facts: dict[str, Any],
    account_safe_facts: dict[str, Any],
    watcher_status: dict[str, Any],
    deploy_health: dict[str, Any],
    source_errors: dict[str, str | None],
    systemd: dict[str, Any],
) -> dict[str, Any]:
    reasons: list[str] = []
    blocker_class = "none"
    strategy_group_id = "runtime"
    symbol = "all"
    checkpoint = "server_runtime_monitor"
    fresh_or_action_time = _candidate_pool_fresh_or_action_time(candidate_pool)
    account_safe_required = fresh_or_action_time is not None

    missing_or_bad_sources = [
        name
        for name, error in source_errors.items()
        if error
        and name != "deploy_health"
        and (name != "account_safe_facts" or account_safe_required)
    ]
    if missing_or_bad_sources:
        reasons.append("runtime_data_gap:" + ",".join(missing_or_bad_sources))
        blocker_class = "runtime_data_gap"
        checkpoint = "server_source_readiness"

    if not _public_facts_ready(public_facts):
        reasons.append("runtime_data_gap:public_facts")
        blocker_class = "runtime_data_gap"
        checkpoint = "public_facts"

    if account_safe_required and not _account_safe_facts_ready(account_safe_facts):
        reasons.append("runtime_data_gap:account_safe_facts")
        blocker_class = "runtime_data_gap"
        checkpoint = "account_safe_facts"

    if not _watcher_ready(watcher_status):
        reasons.append("watcher_status_not_ready")
        blocker_class = "watcher_or_service_failure"
        checkpoint = "watcher_status"

    if source_errors.get("deploy_health") or not _deploy_health_ready(deploy_health):
        reasons.append("deploy_or_readiness_health_not_ready")
        blocker_class = "deploy_or_readiness_failure"
        checkpoint = "deploy_readiness_health"

    if not systemd.get("ready"):
        reasons.extend([str(item) for item in systemd.get("blockers") or []])
        blocker_class = "watcher_or_service_failure"
        checkpoint = "systemd"

    if fresh_or_action_time:
        strategy_group_id = str(
            fresh_or_action_time.get("strategy_group_id")
            or fresh_or_action_time.get("strategy")
            or "runtime"
        )
        symbol = str(
            fresh_or_action_time.get("selected_symbol")
            or fresh_or_action_time.get("symbol")
            or "unknown"
        )
        event_type = str(fresh_or_action_time.get("_server_monitor_event_type") or "")
        first_blocker = str(fresh_or_action_time.get("first_blocker") or "")
        if blocker_class != "none":
            reasons.append("fresh_or_action_time_blocked_by:" + blocker_class)
        elif event_type == "action_time_lane_input":
            reasons.append("action_time_lane_input_present")
            if (
                str(fresh_or_action_time.get("scope_state") or "")
                == "conditional_action_time_rehearsal_allowed"
            ):
                reasons.append("conditional_action_time_rehearsal_only")
                blocker_class = "conditional_action_time_rehearsal"
                checkpoint = "conditional_action_time_rehearsal"
            else:
                blocker_class = "action_time_boundary"
                checkpoint = "fresh_signal_action_time_boundary"
        elif event_type == "promotion_candidate":
            reasons.append("promotion_candidate_present")
            blocker_class = "promotion_candidate"
            checkpoint = "fresh_signal_promotion"
        elif first_blocker and first_blocker not in MARKET_BLOCKERS:
            reasons.append("fresh_signal_blocked_by_non_market_blocker:" + first_blocker)
            blocker_class = first_blocker
            checkpoint = "fresh_signal_promotion"
        else:
            reasons.append("fresh_signal_present")
            blocker_class = "fresh_signal"
            checkpoint = "fresh_signal_promotion"

    data_gap_row = _runtime_data_gap_from_candidate_pool(candidate_pool)
    if data_gap_row and blocker_class == "none":
        strategy_group_id = str(data_gap_row.get("strategy_group_id") or "runtime")
        symbol = str(data_gap_row.get("selected_symbol") or data_gap_row.get("symbol") or "unknown")
        reasons.append("runtime_data_gap:watcher_or_public_facts")
        blocker_class = "runtime_data_gap"
        checkpoint = "candidate_pool_readiness"

    non_market_row = _daily_table_has_non_market_blocker(daily_table)
    if non_market_row and blocker_class == "none":
        strategy_group_id = str(non_market_row.get("strategy_group_id") or "runtime")
        symbol = str(non_market_row.get("symbol") or "unknown")
        blocker_class = str(non_market_row.get("first_blocker") or "non_market_blocker")
        reasons.append("non_market_blocker:" + blocker_class)
        checkpoint = "daily_live_enablement_table"

    notify = bool(reasons)
    return {
        "decision": "notify" if notify else "quiet",
        "notify": notify,
        "status": "notify_required" if notify else "healthy_waiting_quiet",
        "reasons": _dedupe(reasons),
        "automation_id": "tokyo-runtime-server-monitor",
        "strategy_group_id": strategy_group_id,
        "symbol": symbol,
        "blocker_class": blocker_class,
        "checkpoint": checkpoint,
        "owner_message": "需要介入" if notify else "等待机会，无需操作",
    }


def _pg_rows(value: Any) -> list[dict[str, Any]]:
    return [_as_dict(item) for item in _as_list(value) if isinstance(item, dict)]


def _candidate_pool_runtime_coverage_complete(candidate_pool: dict[str, Any]) -> bool:
    coverage = _as_dict(candidate_pool.get("server_runtime_coverage"))
    if coverage.get("status") != "complete":
        return False
    expected = coverage.get("expected_row_count")
    active = coverage.get("active_matched_row_count")
    missing = coverage.get("missing_row_count")
    return isinstance(expected, int) and expected > 0 and active == expected and missing == 0


def _first_pg_focus_row(candidate_pool: dict[str, Any]) -> dict[str, Any]:
    for key in ("action_time_lane_inputs", "promotion_candidates"):
        rows = _pg_rows(candidate_pool.get(key))
        if rows:
            return rows[0]
    row = _candidate_pool_fresh_or_action_time(candidate_pool)
    return _as_dict(row)


def _first_meaningful_blocker(blockers: list[Any]) -> str:
    for blocker in blockers:
        text = str(blocker or "")
        if text.startswith("action_time_ticket_missing:"):
            return "action_time_ticket_missing"
        if text.startswith("candidate_pool_blocker:"):
            parts = text.split(":")
            if len(parts) >= 2:
                return parts[1]
        if text:
            return text.split(":", 1)[0]
    return "none"


def _decision_from_pg_sources(
    *,
    goal_status: dict[str, Any],
    candidate_pool: dict[str, Any],
    systemd: dict[str, Any],
) -> dict[str, Any]:
    reasons: list[str] = []
    status = str(goal_status.get("status") or "")
    blockers = [str(item) for item in _as_list(goal_status.get("blockers")) if str(item)]
    checks = _as_dict(goal_status.get("checks"))
    focus_row = _first_pg_focus_row(candidate_pool)
    strategy_group_id = str(
        focus_row.get("strategy_group_id")
        or goal_status.get("strategy_group_id")
        or "runtime"
    )
    symbol = str(
        focus_row.get("selected_symbol")
        or focus_row.get("symbol")
        or goal_status.get("symbol")
        or "all"
    )
    checkpoint = str(
        goal_status.get("non_authority_checkpoint")
        or "server_runtime_monitor"
    )
    blocker_class = _first_meaningful_blocker(blockers)
    coverage_complete = _candidate_pool_runtime_coverage_complete(candidate_pool)

    if not systemd.get("ready"):
        reasons.extend([str(item) for item in systemd.get("blockers") or []])
        blocker_class = "watcher_or_service_failure"
        checkpoint = "systemd"

    if status == "waiting_for_signal":
        if checks.get("watcher_liveness_healthy") is False or not coverage_complete:
            reasons.append("runtime_data_gap:pg_runtime_coverage")
            blocker_class = "runtime_data_gap"
            checkpoint = "pg_runtime_coverage"
        elif blockers:
            reasons.extend(blockers)
            if blocker_class == "none":
                blocker_class = "runtime_data_gap"
        elif systemd.get("ready"):
            return {
                "decision": "quiet",
                "notify": False,
                "status": "healthy_waiting_quiet",
                "reasons": [],
                "automation_id": "tokyo-runtime-server-monitor",
                "strategy_group_id": strategy_group_id,
                "symbol": symbol,
                "blocker_class": "none",
                "checkpoint": "server_runtime_monitor",
                "owner_message": "等待机会，无需操作",
            }
    elif status in {
        "fresh_signal_detected",
        "fresh_signal_processing",
        "action_time_finalgate_ready",
        "operation_layer_ready",
    }:
        reasons.append(status)
        if blockers:
            reasons.extend(blockers)
        if blocker_class == "none":
            blocker_class = (
                "action_time_boundary"
                if status in {"action_time_finalgate_ready", "operation_layer_ready"}
                else "fresh_signal"
            )
    elif status:
        reasons.append(status)
        if blockers:
            reasons.extend(blockers)
        if blocker_class == "none":
            blocker_class = status
    else:
        reasons.append("runtime_data_gap:goal_status_missing")
        blocker_class = "runtime_data_gap"
        checkpoint = "pg_goal_status"

    return {
        "decision": "notify",
        "notify": True,
        "status": "notify_required",
        "reasons": _dedupe(reasons),
        "automation_id": "tokyo-runtime-server-monitor",
        "strategy_group_id": strategy_group_id,
        "symbol": symbol,
        "blocker_class": blocker_class,
        "checkpoint": checkpoint,
        "owner_message": "需要介入",
    }


def _dedupe_identity(decision: dict[str, Any]) -> str:
    parts = [
        str(decision.get("automation_id") or ""),
        str(decision.get("strategy_group_id") or ""),
        str(decision.get("symbol") or ""),
        str(decision.get("blocker_class") or ""),
        str(decision.get("checkpoint") or ""),
    ]
    return "|".join(parts)


def _load_dedupe_state(path: Path) -> dict[str, Any]:
    payload, error = _read_json(path)
    if error:
        return {"schema": "brc.server_runtime_monitor_dedupe_state.v1", "events": {}}
    if not isinstance(payload.get("events"), dict):
        payload["events"] = {}
    return payload


def _notification_text(decision: dict[str, Any], artifact_path: Path) -> str:
    reasons = ", ".join(str(item) for item in decision.get("reasons") or [])
    return "\n".join(
        [
            "BRC 生产监控：需要介入",
            f"策略组: {decision.get('strategy_group_id')}",
            f"标的: {decision.get('symbol')}",
            f"阻断: {decision.get('blocker_class')}",
            f"检查点: {decision.get('checkpoint')}",
            f"原因: {reasons or '-'}",
            f"证据: {artifact_path}",
        ]
    )


def _apply_notification(
    *,
    decision: dict[str, Any],
    dedupe_state_path: Path,
    output_json: Path,
    webhook_url: str | None,
    webhook_secret: str | None,
    notification_timeout_seconds: float,
    notification_dry_run: bool,
    notifier: Notifier | None,
    now_utc: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    state = _load_dedupe_state(dedupe_state_path)
    events = _as_dict(state.get("events"))
    identity = _dedupe_identity(decision)
    existing = _as_dict(events.get(identity))
    first_seen_at = str(existing.get("first_seen_at") or now_utc)
    last_notified_at = existing.get("last_notified_at")
    previous_sent = bool(existing.get("last_send_succeeded"))
    previous_failed = bool(existing.get("last_send_failed"))
    notification = {
        "required": bool(decision.get("notify")),
        "attempted": False,
        "sent": False,
        "duplicate_suppressed": False,
        "configured": bool(webhook_url),
        "secret_configured": bool(webhook_secret),
        "skipped_reason": None,
        "dedupe_key": {
            "automation_id": decision.get("automation_id"),
            "strategy_group_id": decision.get("strategy_group_id"),
            "symbol": decision.get("symbol"),
            "blocker_class": decision.get("blocker_class"),
            "checkpoint": decision.get("checkpoint"),
            "first_seen_at": first_seen_at,
            "last_notified_at": last_notified_at,
        },
        "retry_pending": previous_failed,
    }
    if not decision.get("notify"):
        notification["skipped_reason"] = "healthy_waiting_quiet"
    elif previous_sent and not previous_failed:
        notification["duplicate_suppressed"] = True
        notification["skipped_reason"] = "dedupe_suppressed"
    elif not webhook_url:
        notification["skipped_reason"] = "feishu_webhook_url_missing"
    elif notification_dry_run:
        notification["skipped_reason"] = "notification_dry_run"
        notification["message_preview"] = _notification_text(decision, output_json)[:1000]
    else:
        sender = notifier or send_feishu_text
        result = sender(
            webhook_url,
            webhook_secret,
            {"text": _notification_text(decision, output_json)},
            notification_timeout_seconds,
        )
        notification.update({"attempted": True, **result})

    if decision.get("notify"):
        sent = bool(notification.get("sent"))
        event = {
            "automation_id": decision.get("automation_id"),
            "strategy_group_id": decision.get("strategy_group_id"),
            "symbol": decision.get("symbol"),
            "blocker_class": decision.get("blocker_class"),
            "checkpoint": decision.get("checkpoint"),
            "first_seen_at": first_seen_at,
            "last_seen_at": now_utc,
            "last_notified_at": now_utc if sent else last_notified_at,
            "last_send_attempted_at": (
                now_utc if notification.get("attempted") else existing.get("last_send_attempted_at")
            ),
            "last_send_succeeded": sent or (previous_sent and not previous_failed),
            "last_send_failed": bool(notification.get("attempted")) and not sent,
            "last_error": notification.get("error"),
        }
        events[identity] = event
        notification["dedupe_key"]["last_notified_at"] = event["last_notified_at"]

    state.update(
        {
            "schema": "brc.server_runtime_monitor_dedupe_state.v1",
            "updated_at_utc": now_utc,
            "events": events,
        }
    )
    _write_json(dedupe_state_path, state)
    return notification, state


def _utc_to_ms(value: str) -> int:
    try:
        return int(datetime.fromisoformat(value).timestamp() * 1000)
    except ValueError:
        return int(time.time() * 1000)


def _notification_id_from_identity(identity: str) -> str:
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]
    return f"server_monitor_notification:{digest}"


def _monitor_run_id(now_ms: int, decision: dict[str, Any]) -> str:
    digest = hashlib.sha256(
        json.dumps(decision, ensure_ascii=False, sort_keys=True, default=str).encode(
            "utf-8"
        )
    ).hexdigest()[:16]
    return f"server_monitor_run:{now_ms}:{digest}"


def _pg_notification_row(
    conn: sa.engine.Connection,
    identity: str,
) -> dict[str, Any]:
    row = conn.execute(
        sa.text(
            """
            SELECT *
            FROM brc_server_monitor_notifications
            WHERE dedupe_key = :dedupe_key
            LIMIT 1
            """
        ),
        {"dedupe_key": identity},
    ).mappings().first()
    return dict(row) if row else {}


def _table(conn: sa.engine.Connection, table_name: str) -> sa.Table:
    metadata = sa.MetaData()
    return sa.Table(table_name, metadata, autoload_with=conn)


def _apply_pg_notification(
    *,
    conn: sa.engine.Connection,
    decision: dict[str, Any],
    output_json: Path,
    webhook_url: str | None,
    webhook_secret: str | None,
    notification_timeout_seconds: float,
    notification_dry_run: bool,
    notifier: Notifier | None,
    now_utc: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    identity = _dedupe_identity(decision)
    now_ms = _utc_to_ms(now_utc)
    existing = _pg_notification_row(conn, identity)
    first_seen_ms = int(existing.get("first_seen_at_ms") or now_ms)
    last_notified_ms = existing.get("last_notified_at_ms")
    previous_sent = existing.get("notification_state") == "sent"
    previous_failed = existing.get("notification_state") in {"failed", "retrying"}
    send_attempts = int(existing.get("send_attempts") or 0)
    notification = {
        "required": bool(decision.get("notify")),
        "attempted": False,
        "sent": False,
        "duplicate_suppressed": False,
        "configured": bool(webhook_url),
        "secret_configured": bool(webhook_secret),
        "skipped_reason": None,
        "dedupe_key": {
            "automation_id": decision.get("automation_id"),
            "strategy_group_id": decision.get("strategy_group_id"),
            "symbol": decision.get("symbol"),
            "blocker_class": decision.get("blocker_class"),
            "checkpoint": decision.get("checkpoint"),
            "first_seen_at": first_seen_ms,
            "last_notified_at": last_notified_ms,
        },
        "retry_pending": previous_failed,
        "source": "pg:brc_server_monitor_notifications",
    }
    if not decision.get("notify"):
        notification["skipped_reason"] = "healthy_waiting_quiet"
    elif previous_sent and not previous_failed:
        notification["duplicate_suppressed"] = True
        notification["skipped_reason"] = "dedupe_suppressed"
    elif not webhook_url:
        notification["skipped_reason"] = "feishu_webhook_url_missing"
    elif notification_dry_run:
        notification["skipped_reason"] = "notification_dry_run"
        notification["message_preview"] = _notification_text(decision, output_json)[:1000]
    else:
        sender = notifier or send_feishu_text
        result = sender(
            webhook_url,
            webhook_secret,
            {"text": _notification_text(decision, output_json)},
            notification_timeout_seconds,
        )
        notification.update({"attempted": True, **result})

    if decision.get("notify"):
        attempted = bool(notification.get("attempted"))
        sent = bool(notification.get("sent"))
        if attempted:
            send_attempts += 1
        state = (
            "sent"
            if sent or (previous_sent and not previous_failed and not attempted)
            else "failed"
            if attempted
            else "suppressed"
            if notification.get("duplicate_suppressed")
            else "pending"
        )
        values = {
            "notification_id": str(existing.get("notification_id") or _notification_id_from_identity(identity)),
            "dedupe_key": identity,
            "automation_id": str(decision.get("automation_id") or ""),
            "strategy_group_id": str(decision.get("strategy_group_id") or ""),
            "symbol": str(decision.get("symbol") or ""),
            "blocker_class": str(decision.get("blocker_class") or ""),
            "checkpoint": str(decision.get("checkpoint") or ""),
            "notification_state": state,
            "first_seen_at_ms": first_seen_ms,
            "last_notified_at_ms": now_ms if sent else last_notified_ms,
            "last_seen_at_ms": now_ms,
            "send_attempts": send_attempts,
            "last_error": notification.get("error"),
            "feishu_response": {
                "sent": sent,
                "status_code": notification.get("status_code"),
                "response_body_preview": notification.get("response_body_preview"),
                "skipped_reason": notification.get("skipped_reason"),
            },
            "created_at_ms": int(existing.get("created_at_ms") or now_ms),
            "updated_at_ms": now_ms,
        }
        table = _table(conn, "brc_server_monitor_notifications")
        if existing:
            conn.execute(
                table.update()
                .where(table.c.dedupe_key == identity)
                .values(
                    notification_state=values["notification_state"],
                    last_notified_at_ms=values["last_notified_at_ms"],
                    last_seen_at_ms=values["last_seen_at_ms"],
                    send_attempts=values["send_attempts"],
                    last_error=values["last_error"],
                    feishu_response=values["feishu_response"],
                    updated_at_ms=values["updated_at_ms"],
                )
            )
        else:
            conn.execute(table.insert().values(**values))
        notification["dedupe_key"]["last_notified_at"] = values["last_notified_at_ms"]

    state = {
        "schema": "brc.server_runtime_monitor_dedupe_state.pg.v1",
        "source": "pg:brc_server_monitor_notifications",
        "event_count": conn.execute(
            sa.text("SELECT COUNT(*) FROM brc_server_monitor_notifications")
        ).scalar_one(),
        "trading_authority": False,
    }
    return notification, state


def _record_pg_monitor_run(
    *,
    conn: sa.engine.Connection,
    decision: dict[str, Any],
    systemd: dict[str, Any],
    source_refs: dict[str, Any],
    now_utc: str,
) -> None:
    now_ms = _utc_to_ms(now_utc)
    status = "notify" if decision.get("notify") else "quiet"
    table = _table(conn, "brc_server_monitor_runs")
    conn.execute(
        table.insert().values(
            monitor_run_id=_monitor_run_id(now_ms, decision),
            automation_id=str(decision.get("automation_id") or ""),
            runtime_head=None,
            started_at_ms=now_ms,
            finished_at_ms=now_ms,
            status=status,
            quiet_reason=(
                ",".join(str(item) for item in decision.get("reasons") or [])
                if not decision.get("notify")
                else None
            ),
            notify_reason=(
                ",".join(str(item) for item in decision.get("reasons") or [])
                if decision.get("notify")
                else None
            ),
            blocker_classes=[str(decision.get("blocker_class") or "")],
            systemd_status=systemd,
            source_refs=source_refs,
            forbidden_effects={
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "order_created": False,
                "live_profile_changed": False,
                "order_sizing_changed": False,
            },
            created_at_ms=now_ms,
        )
    )


def build_server_monitor_artifact(
    args: argparse.Namespace,
    *,
    notifier: Notifier | None = None,
    systemd_runner: SystemdRunner | None = None,
    pg_conn: sa.engine.Connection | None = None,
) -> dict[str, Any]:
    database_url = str(getattr(args, "database_url", "") or "")
    if getattr(args, "require_database_url", False) and not database_url and pg_conn is None:
        raise ValueError("PG_DATABASE_URL is required for DB-backed server monitor")
    if database_url or pg_conn is not None:
        if pg_conn is not None:
            return build_server_monitor_artifact_from_pg(
                args,
                conn=pg_conn,
                notifier=notifier,
                systemd_runner=systemd_runner,
            )
        if not database_url.startswith(
            ("postgresql://", "postgresql+psycopg://")
        ) and not getattr(args, "allow_non_postgres_for_test", False):
            raise ValueError("DB-backed server monitor requires PostgreSQL DSN")
        engine = sa.create_engine(database_url)
        try:
            with engine.begin() as conn:
                return build_server_monitor_artifact_from_pg(
                    args,
                    conn=conn,
                    notifier=notifier,
                    systemd_runner=systemd_runner,
                )
        finally:
            engine.dispose()

    if not getattr(args, "allow_local_file_diagnostic", False):
        raise ValueError(
            "PG_DATABASE_URL is required for DB-backed server monitor; "
            "use --allow-local-file-diagnostic only for explicit local diagnostics"
        )
    required_local_inputs = {
        "--daily-table-json": getattr(args, "daily_table_json", None),
        "--candidate-pool-json": getattr(args, "candidate_pool_json", None),
        "--public-facts-json": getattr(args, "public_facts_json", None),
        "--account-safe-facts-json": getattr(args, "account_safe_facts_json", None),
    }
    missing_local_inputs = [
        flag for flag, value in required_local_inputs.items() if not value
    ]
    if missing_local_inputs:
        raise ValueError(
            "explicit local diagnostic inputs required: "
            + ", ".join(missing_local_inputs)
        )

    now = _utc_now()
    sources: dict[str, dict[str, Any]] = {}
    source_errors: dict[str, str | None] = {}
    source_paths = {
        "daily_table": Path(args.daily_table_json),
        "candidate_pool": Path(args.candidate_pool_json),
        "public_facts": Path(args.public_facts_json),
        "account_safe_facts": Path(args.account_safe_facts_json),
        "watcher_status": Path(args.watcher_status_json),
        "deploy_health": Path(args.deploy_health_json),
    }
    for name, path in source_paths.items():
        payload, error = _read_json(path)
        sources[name] = payload
        source_errors[name] = error

    systemd = (
        {"checked": False, "ready": True, "rows": [], "blockers": []}
        if args.skip_systemd
        else _systemd_status(list(args.systemd_unit or []), runner=systemd_runner)
    )
    decision = _decision_from_sources(
        daily_table=sources["daily_table"],
        candidate_pool=sources["candidate_pool"],
        public_facts=sources["public_facts"],
        account_safe_facts=sources["account_safe_facts"],
        watcher_status=sources["watcher_status"],
        deploy_health=sources["deploy_health"],
        source_errors=source_errors,
        systemd=systemd,
    )
    output_json = Path(args.output_json)
    webhook_url = args.feishu_webhook_url or _env_value(FEISHU_WEBHOOK_URL_ENV_NAMES)
    webhook_secret = args.feishu_webhook_secret or _env_value(FEISHU_WEBHOOK_SECRET_ENV_NAMES)
    notification, dedupe_state = _apply_notification(
        decision=decision,
        dedupe_state_path=Path(args.dedupe_state_json),
        output_json=output_json,
        webhook_url=webhook_url,
        webhook_secret=webhook_secret,
        notification_timeout_seconds=args.notification_timeout_seconds,
        notification_dry_run=bool(args.notification_dry_run),
        notifier=notifier,
        now_utc=now,
    )
    artifact = {
        "schema": "brc.tokyo_runtime_server_monitor.v1",
        "status": decision["status"],
        "scope": "tokyo_server_side_readonly_runtime_monitor",
        "generated_at_utc": now,
        "decision": decision,
        "notification": notification,
        "dedupe_state": {
            "path": str(Path(args.dedupe_state_json)),
            "event_count": len(_as_dict(dedupe_state.get("events"))),
            "trading_authority": False,
        },
        "source_paths": {name: str(path) for name, path in source_paths.items()},
        "source_errors": source_errors,
        "source_statuses": {
            name: _safe_status(payload) for name, payload in sources.items()
        },
        "systemd": systemd,
        "interaction": {
            "level": "L1_tokyo_server_readonly_monitor",
            "remote_interaction_count": 0,
            "mutates_remote_files": False,
            "approaches_real_order": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
        "safety_invariants": {
            "server_side_monitor": True,
            "local_monitor_sequence_used": False,
            "local_cache_as_production_truth": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
            "order_created": False,
            "withdrawal_or_transfer_created": False,
            "credentials_or_secrets_mutated": False,
            "live_profile_changed": False,
            "order_sizing_changed": False,
            "notification_state_is_trading_authority": False,
            "replay_or_synthetic_used_as_live_required_facts": False,
        },
    }
    _write_json(output_json, artifact)
    return artifact


def build_server_monitor_artifact_from_pg(
    args: argparse.Namespace,
    *,
    conn: sa.engine.Connection,
    notifier: Notifier | None = None,
    systemd_runner: SystemdRunner | None = None,
) -> dict[str, Any]:
    from scripts.build_strategy_live_candidate_pool import (  # noqa: PLC0415
        build_strategy_live_candidate_pool_from_control_state,
    )
    from scripts.build_strategygroup_runtime_goal_status import (  # noqa: PLC0415
        build_goal_status_artifact_from_control_state,
    )

    now = _utc_now()
    repository = PgBackedRuntimeControlStateRepository(conn)
    control_state = repository.read_control_state()
    candidate_pool = build_strategy_live_candidate_pool_from_control_state(control_state)
    report_dir = Path(args.output_json).parent
    goal_status = build_goal_status_artifact_from_control_state(
        control_state=control_state,
        report_dir=report_dir,
    )
    systemd = (
        {"checked": False, "ready": True, "rows": [], "blockers": []}
        if args.skip_systemd
        else _systemd_status(list(args.systemd_unit or []), runner=systemd_runner)
    )
    decision = _decision_from_pg_sources(
        goal_status=goal_status,
        candidate_pool=candidate_pool,
        systemd=systemd,
    )
    output_json = Path(args.output_json)
    webhook_url = args.feishu_webhook_url or _env_value(FEISHU_WEBHOOK_URL_ENV_NAMES)
    webhook_secret = args.feishu_webhook_secret or _env_value(FEISHU_WEBHOOK_SECRET_ENV_NAMES)
    notification, dedupe_state = _apply_pg_notification(
        conn=conn,
        decision=decision,
        output_json=output_json,
        webhook_url=webhook_url,
        webhook_secret=webhook_secret,
        notification_timeout_seconds=args.notification_timeout_seconds,
        notification_dry_run=bool(args.notification_dry_run),
        notifier=notifier,
        now_utc=now,
    )
    source_refs = {
        "source_mode": "db_backed",
        "projection_target": "production_current",
        "candidate_pool": "pg_projection:strategy_live_candidate_pool",
        "goal_status": "pg_projection:strategygroup_runtime_goal_status",
        "server_monitor_runs": "pg:brc_server_monitor_runs",
        "server_monitor_notifications": "pg:brc_server_monitor_notifications",
        "control_state_watermark": {
            "schema": str(control_state.get("schema") or ""),
            "table_counts": _as_dict(control_state.get("table_counts")),
        },
    }
    _record_pg_monitor_run(
        conn=conn,
        decision=decision,
        systemd=systemd,
        source_refs=source_refs,
        now_utc=now,
    )
    artifact = {
        "schema": "brc.tokyo_runtime_server_monitor.v1",
        "status": decision["status"],
        "scope": "tokyo_server_side_readonly_runtime_monitor",
        "generated_at_utc": now,
        "source_mode": "db_backed",
        "projection_target": "production_current",
        "decision": decision,
        "notification": notification,
        "dedupe_state": dedupe_state,
        "source_paths": {},
        "source_errors": {},
        "source_statuses": {
            "candidate_pool": str(candidate_pool.get("status") or ""),
            "goal_status": str(goal_status.get("status") or ""),
        },
        "source_refs": source_refs,
        "systemd": systemd,
        "interaction": {
            "level": "L1_tokyo_server_readonly_monitor",
            "remote_interaction_count": 0,
            "mutates_remote_files": False,
            "approaches_real_order": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
        "safety_invariants": {
            "server_side_monitor": True,
            "local_monitor_sequence_used": False,
            "local_cache_as_production_truth": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
            "order_created": False,
            "withdrawal_or_transfer_created": False,
            "credentials_or_secrets_mutated": False,
            "live_profile_changed": False,
            "order_sizing_changed": False,
            "notification_state_is_trading_authority": False,
            "replay_or_synthetic_used_as_live_required_facts": False,
        },
    }
    _write_json(output_json, artifact)
    return artifact


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Tokyo server-side readonly runtime monitor.",
    )
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--dedupe-state-json", default=str(DEFAULT_DEDUPE_STATE_JSON))
    parser.add_argument("--daily-table-json")
    parser.add_argument("--candidate-pool-json")
    parser.add_argument("--public-facts-json")
    parser.add_argument("--account-safe-facts-json")
    parser.add_argument("--watcher-status-json", default=str(DEFAULT_WATCHER_STATUS_JSON))
    parser.add_argument("--deploy-health-json", default=str(DEFAULT_DEPLOY_HEALTH_JSON))
    parser.add_argument("--systemd-unit", action="append")
    parser.add_argument("--skip-systemd", action="store_true")
    parser.add_argument("--notification-timeout-seconds", type=float, default=10.0)
    parser.add_argument("--notification-dry-run", action="store_true")
    parser.add_argument("--feishu-webhook-url")
    parser.add_argument("--feishu-webhook-secret")
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument(
        "--require-database-url",
        action="store_true",
        help="Fail instead of falling back to legacy JSON inputs when PG_DATABASE_URL is absent.",
    )
    parser.add_argument(
        "--allow-non-postgres-for-test",
        action="store_true",
        help="Allow SQLite/non-PG DSNs only in tests.",
    )
    parser.add_argument(
        "--allow-local-file-diagnostic",
        action="store_true",
        help=(
            "Allow explicit local JSON inputs for monitor diagnostics only. "
            "Production server monitor must use PG current state."
        ),
    )
    args = parser.parse_args(argv)
    if not args.systemd_unit:
        args.systemd_unit = list(DEFAULT_SYSTEMD_UNITS)
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    artifact = build_server_monitor_artifact(args)
    print(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
