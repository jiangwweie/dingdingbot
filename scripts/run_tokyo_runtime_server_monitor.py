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


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = Path("/home/ubuntu/brc-deploy/reports/runtime-monitor")
DEFAULT_OUTPUT_JSON = DEFAULT_REPORT_DIR / "latest-server-side-runtime-monitor.json"
DEFAULT_DEDUPE_STATE_JSON = DEFAULT_REPORT_DIR / "server-monitor-dedupe-state.json"
DEFAULT_DAILY_TABLE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-daily-live-enablement-table.json"
)
DEFAULT_CANDIDATE_POOL_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-strategy-live-candidate-pool.json"
)
DEFAULT_PUBLIC_FACTS_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-binance-usdm-public-facts.json"
)
DEFAULT_ACCOUNT_SAFE_FACTS_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-account-safe-facts.json"
)
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
        rows.append(
            {
                "unit": unit,
                "active": active,
                "stdout": result.stdout,
                "stderr_preview": result.stderr[:240],
                "returncode": result.returncode,
            }
        )
        if not active:
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
        if blocker in RUNTIME_DATA_GAP_BLOCKERS or readiness_status in {
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


def build_server_monitor_artifact(
    args: argparse.Namespace,
    *,
    notifier: Notifier | None = None,
    systemd_runner: SystemdRunner | None = None,
) -> dict[str, Any]:
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


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Tokyo server-side readonly runtime monitor.",
    )
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--dedupe-state-json", default=str(DEFAULT_DEDUPE_STATE_JSON))
    parser.add_argument("--daily-table-json", default=str(DEFAULT_DAILY_TABLE_JSON))
    parser.add_argument("--candidate-pool-json", default=str(DEFAULT_CANDIDATE_POOL_JSON))
    parser.add_argument("--public-facts-json", default=str(DEFAULT_PUBLIC_FACTS_JSON))
    parser.add_argument(
        "--account-safe-facts-json",
        default=str(DEFAULT_ACCOUNT_SAFE_FACTS_JSON),
    )
    parser.add_argument("--watcher-status-json", default=str(DEFAULT_WATCHER_STATUS_JSON))
    parser.add_argument("--deploy-health-json", default=str(DEFAULT_DEPLOY_HEALTH_JSON))
    parser.add_argument("--systemd-unit", action="append")
    parser.add_argument("--skip-systemd", action="store_true")
    parser.add_argument("--notification-timeout-seconds", type=float, default=10.0)
    parser.add_argument("--notification-dry-run", action="store_true")
    parser.add_argument("--feishu-webhook-url")
    parser.add_argument("--feishu-webhook-secret")
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
