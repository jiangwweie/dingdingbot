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

from scripts.pg_dsn import is_sync_postgres_dsn, normalize_sync_postgres_dsn  # noqa: E402
from src.infrastructure.runtime_control_state_repository import (  # noqa: E402
    PgBackedRuntimeControlStateRepository,
    RuntimeControlStateRepositoryError,
)

PG_CURRENT_PROJECTION_REPORT_DIR = Path("pg_current_projection")
PG_MONITOR_EVIDENCE_REF = (
    "pg:brc_server_monitor_runs + "
    "pg:brc_server_monitor_notifications + "
    "pg_projection:production_current"
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


def _decision_from_pg_current_state_error(exc: RuntimeControlStateRepositoryError) -> dict[str, Any]:
    reason = f"runtime_data_gap:pg_current_state_invalid:{exc}"
    return {
        "decision": "notify",
        "notify": True,
        "status": "notify_required",
        "reasons": [reason],
        "automation_id": "tokyo-runtime-server-monitor",
        "strategy_group_id": "runtime",
        "symbol": "all",
        "blocker_class": "runtime_data_gap",
        "checkpoint": "pg_current_state_repository",
        "owner_message": "PG current state 校验失败，系统需要修复运行投影",
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


def _notification_title(decision: dict[str, Any]) -> str:
    blocker_class = str(decision.get("blocker_class") or "")
    if blocker_class == "runtime_data_gap":
        return "BRC 生产监控：系统运行数据异常"
    if blocker_class in {
        "hard_safety_stop",
        "policy_scope_missing",
        "budget_gap",
        "recovery_review",
        "strategy_review",
    }:
        return "BRC 生产监控：需要 Owner 介入"
    if blocker_class == "watcher_or_service_failure":
        return "BRC 生产监控：服务器观察链路异常"
    return "BRC 生产监控：系统运行状态提醒"


def _notification_text(decision: dict[str, Any], evidence_ref: str) -> str:
    reasons = ", ".join(str(item) for item in decision.get("reasons") or [])
    return "\n".join(
        [
            _notification_title(decision),
            f"策略组: {decision.get('strategy_group_id')}",
            f"标的: {decision.get('symbol')}",
            f"阻断: {decision.get('blocker_class')}",
            f"检查点: {decision.get('checkpoint')}",
            f"原因: {reasons or '-'}",
            f"证据: {evidence_ref}",
        ]
    )


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
    evidence_ref: str,
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
        notification["message_preview"] = _notification_text(decision, evidence_ref)[:1000]
    else:
        sender = notifier or send_feishu_text
        result = sender(
            webhook_url,
            webhook_secret,
            {"text": _notification_text(decision, evidence_ref)},
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
    if not database_url and pg_conn is None:
        raise ValueError("PG_DATABASE_URL is required for DB-backed server monitor")
    if pg_conn is not None:
        return build_server_monitor_artifact_from_pg(
            args,
            conn=pg_conn,
            notifier=notifier,
            systemd_runner=systemd_runner,
        )
    database_url = normalize_sync_postgres_dsn(database_url)
    if not is_sync_postgres_dsn(database_url) and not getattr(
        args,
        "allow_non_postgres_for_test",
        False,
    ):
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
    systemd = (
        {"checked": False, "ready": True, "rows": [], "blockers": []}
        if args.skip_systemd
        else _systemd_status(list(args.systemd_unit or []), runner=systemd_runner)
    )
    source_errors: dict[str, Any] = {}
    try:
        control_state = repository.read_control_state()
        candidate_pool = build_strategy_live_candidate_pool_from_control_state(control_state)
        goal_status = build_goal_status_artifact_from_control_state(
            control_state=control_state,
        )
        decision = _decision_from_pg_sources(
            goal_status=goal_status,
            candidate_pool=candidate_pool,
            systemd=systemd,
        )
        control_state_watermark = {
            "schema": str(control_state.get("schema") or ""),
            "table_counts": _as_dict(control_state.get("table_counts")),
        }
    except RuntimeControlStateRepositoryError as exc:
        candidate_pool = {}
        goal_status = {}
        decision = _decision_from_pg_current_state_error(exc)
        if not systemd.get("ready"):
            decision["reasons"] = _dedupe(
                [*decision["reasons"], *[str(item) for item in systemd.get("blockers") or []]]
            )
            decision["blocker_class"] = "watcher_or_service_failure"
            decision["checkpoint"] = "systemd"
        source_errors["pg_current_state_repository"] = str(exc)
        control_state_watermark = {
            "schema": "unavailable",
            "table_counts": {},
            "error_class": "RuntimeControlStateRepositoryError",
        }
    webhook_url = args.feishu_webhook_url or _env_value(FEISHU_WEBHOOK_URL_ENV_NAMES)
    webhook_secret = args.feishu_webhook_secret or _env_value(FEISHU_WEBHOOK_SECRET_ENV_NAMES)
    notification, dedupe_state = _apply_pg_notification(
        conn=conn,
        decision=decision,
        evidence_ref=PG_MONITOR_EVIDENCE_REF,
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
        "control_state_watermark": control_state_watermark,
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
        "source_errors": source_errors,
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
            "legacy_file_monitor_used": False,
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
    return artifact


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Tokyo server-side readonly runtime monitor.",
    )
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
        help="Require PG_DATABASE_URL. This is the only production mode.",
    )
    parser.add_argument(
        "--allow-non-postgres-for-test",
        action="store_true",
        help="Allow SQLite/non-PG DSNs only in tests.",
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
