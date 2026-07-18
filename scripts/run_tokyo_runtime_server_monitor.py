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
import uuid

import sqlalchemy as sa


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.pg_dsn import is_sync_postgres_dsn, normalize_sync_postgres_dsn  # noqa: E402
from src.application.action_time.process_outcome_relevance import (  # noqa: E402
    process_outcome_has_current_blocking_authority,
)
from src.application.action_time.account_risk_policy import (  # noqa: E402
    is_account_risk_policy_blocker,
)
from src.application.owner_notification import (  # noqa: E402
    MAX_INTENTS_PER_RUN,
    OwnerNotificationIntent,
    OwnerNotificationKind,
    OwnerNotificationSeverity,
    owner_notification_delivery_identity,
    normalize_owner_correlation_id,
    owner_notification_dedupe_key,
    project_owner_notification_intents,
    render_owner_notification_card,
    select_owner_notification_delivery_batch,
)
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
    "brc-ticket-lifecycle-maintenance.timer",
    "brc-ticket-lifecycle-maintenance.service",
)
ONESHOT_INACTIVE_OK_UNITS = {
    "brc-runtime-signal-watcher.service",
    "brc-ticket-lifecycle-maintenance.service",
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


def _utc_now_from_args(args: argparse.Namespace) -> str:
    now_ms = getattr(args, "now_ms", None)
    if now_ms is None:
        return _utc_now()
    return datetime.fromtimestamp(int(now_ms) / 1000, tz=timezone.utc).isoformat()


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


def parse_feishu_robot_ack(
    *,
    status_code: int,
    response_body: str,
) -> dict[str, object]:
    """Fail closed unless Feishu confirms both transport and business success."""
    body_preview = str(response_body or "")[:500]
    business_code: int | None = None
    business_message: str | None = None
    try:
        parsed = json.loads(response_body)
    except (TypeError, json.JSONDecodeError):
        parsed = None
    if isinstance(parsed, dict):
        if "code" in parsed:
            code = parsed.get("code")
            message = parsed.get("msg")
        elif "StatusCode" in parsed:
            code = parsed.get("StatusCode")
            message = parsed.get("StatusMessage")
        else:
            code = None
            message = None
        if isinstance(code, int) and not isinstance(code, bool):
            business_code = code
        if message is not None:
            business_message = str(message)[:500]
    return {
        "sent": 200 <= int(status_code) < 300 and business_code == 0,
        "status_code": int(status_code),
        "business_code": business_code,
        "business_message": business_message,
        "response_body_preview": body_preview,
    }


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
            return parse_feishu_robot_ack(
                status_code=int(response.status),
                response_body=response_body,
            )
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


def send_feishu_payload(
    webhook_url: str,
    webhook_secret: str | None,
    body: dict[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    request_body = dict(body)
    if webhook_secret:
        timestamp = int(time.time())
        request_body["timestamp"] = str(timestamp)
        request_body["sign"] = _feishu_signature(timestamp, webhook_secret)
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
            return parse_feishu_robot_ack(
                status_code=int(response.status),
                response_body=response_body,
            )
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


def _recent_pg_chain_event(control_state: dict[str, Any]) -> dict[str, Any]:
    now_ms = int(control_state.get("read_now_ms") or time.time() * 1000)
    process_failure = _runtime_process_failure_event(control_state)
    if process_failure:
        return process_failure
    lifecycle_event = _lifecycle_safety_event(
        _pg_rows(control_state.get("ticket_bound_order_lifecycle_runs")),
        now_ms=now_ms,
    )
    if lifecycle_event:
        return lifecycle_event
    exchange_command_event = _exchange_command_chain_event(
        _pg_rows(control_state.get("ticket_bound_exchange_commands")),
        now_ms=now_ms,
    )
    if exchange_command_event:
        return exchange_command_event
    ticket_by_id = {
        str(row.get("ticket_id") or ""): row
        for row in _pg_rows(control_state.get("action_time_tickets"))
        if str(row.get("ticket_id") or "")
    }
    completed_attempt_ticket_ids: set[str] = set()
    for attempt in _pg_rows(control_state.get("ticket_bound_protected_submit_attempts")):
        blockers = [str(item) for item in _as_list(attempt.get("blockers")) if str(item)]
        status = str(attempt.get("status") or "")
        if blockers or status == "blocked":
            ticket = ticket_by_id.get(str(attempt.get("ticket_id") or ""), {})
            if not _is_current_monitor_ticket(ticket, now_ms):
                continue
            return {
                "event_type": "protected_submit_attempt_blocked",
                "strategy_group_id": attempt.get("strategy_group_id"),
                "symbol": attempt.get("symbol"),
                "side": attempt.get("side"),
                "checkpoint": "ticket_bound_protected_submit_attempt",
                "blocker_class": _first_meaningful_blocker(blockers)
                if blockers
                else "protected_submit_attempt_blocked",
                "reasons": [
                    "protected_submit_attempt_blocked",
                    *blockers,
                    str(attempt.get("protected_submit_attempt_id") or ""),
                ],
            }
        if status in {"disabled_smoke_passed", "submitted"}:
            ticket_id = str(attempt.get("ticket_id") or "")
            if ticket_id:
                completed_attempt_ticket_ids.add(ticket_id)
    completed_signal_ids: set[str] = set()
    completed_lane_ids: set[str] = set()
    completed_promotion_ids: set[str] = set()
    for ticket in _pg_rows(control_state.get("action_time_tickets")):
        if str(ticket.get("ticket_id") or "") not in completed_attempt_ticket_ids:
            continue
        for source_key, target in (
            ("signal_event_id", completed_signal_ids),
            ("action_time_lane_input_id", completed_lane_ids),
            ("promotion_candidate_id", completed_promotion_ids),
        ):
            value = str(ticket.get(source_key) or "")
            if value:
                target.add(value)
    for ticket in _pg_rows(control_state.get("action_time_tickets")):
        if str(ticket.get("ticket_id") or "") in completed_attempt_ticket_ids:
            continue
        status = str(ticket.get("status") or "")
        if status in {"created", "preflight_pending", "finalgate_ready", "handoff_ready"}:
            return {
                "event_type": "action_time_ticket",
                "strategy_group_id": ticket.get("strategy_group_id"),
                "symbol": ticket.get("symbol"),
                "side": ticket.get("side"),
                "checkpoint": "action_time_ticket",
                "blocker_class": "action_time_ticket",
                "reasons": ["action_time_ticket_created", str(ticket.get("ticket_id") or "")],
            }
    for lane in _pg_rows(control_state.get("action_time_lane_inputs")):
        if str(lane.get("action_time_lane_input_id") or "") in completed_lane_ids:
            continue
        if str(lane.get("status") or "") in {"ticket_pending", "active"}:
            return {
                "event_type": "action_time_lane_input",
                "strategy_group_id": lane.get("strategy_group_id"),
                "symbol": lane.get("symbol"),
                "side": lane.get("side"),
                "checkpoint": "action_time_lane_input",
                "blocker_class": "action_time_boundary",
                "reasons": [
                    "action_time_lane_input_present",
                    str(lane.get("action_time_lane_input_id") or ""),
                ],
            }
    for promotion in _pg_rows(control_state.get("promotion_candidates")):
        if str(promotion.get("promotion_candidate_id") or "") in completed_promotion_ids:
            continue
        if str(promotion.get("status") or "") in {
            "eligible",
            "arbitration_pending",
            "arbitration_won",
        }:
            return {
                "event_type": "promotion_candidate",
                "strategy_group_id": promotion.get("strategy_group_id"),
                "symbol": promotion.get("symbol"),
                "side": promotion.get("side"),
                "checkpoint": "promotion_candidate",
                "blocker_class": "fresh_signal",
                "reasons": [
                    "promotion_candidate_present",
                    str(promotion.get("promotion_candidate_id") or ""),
                ],
            }
    for signal in _pg_rows(control_state.get("live_signal_events")):
        if str(signal.get("signal_event_id") or "") in completed_signal_ids:
            continue
        if (
            str(signal.get("source_kind") or "") == "live_market"
            and str(signal.get("status") or "") == "facts_validated"
            and str(signal.get("freshness_state") or "") == "fresh"
            and signal.get("execution_eligible") is True
            and str(signal.get("required_execution_mode") or "") != "observe_only"
        ):
            return {
                "event_type": "fresh_signal",
                "strategy_group_id": signal.get("strategy_group_id"),
                "symbol": signal.get("symbol"),
                "side": signal.get("side"),
                "checkpoint": "live_signal_event",
                "blocker_class": "fresh_signal",
                "reasons": ["fresh_signal_detected", str(signal.get("signal_event_id") or "")],
            }
    return {}


def _runtime_process_failure_event(
    control_state: dict[str, Any],
) -> dict[str, Any]:
    failures = [
        row
        for row in _pg_rows(control_state.get("runtime_process_outcomes"))
        if _runtime_process_outcome_requires_monitor_attention(control_state, row)
    ]
    if not failures:
        return {}
    row = max(failures, key=lambda item: int(item.get("updated_at_ms") or 0))
    hard = str(row.get("process_state") or "") == "hard_failure"
    blocker = str(row.get("first_blocker") or "runtime_process_failure")
    process_name = str(row.get("process_name") or "runtime_process")
    scope_key = str(row.get("scope_key") or "")
    scope_parts = scope_key.split(":")
    if (
        str(row.get("process_state") or "") == "business_blocked"
        and process_name
        in {
            "action_time_ticket_sequence",
            "action_time_ticket_sequence_batch",
            "action_time_refresh_sequence",
        }
    ):
        policy_blocked = is_account_risk_policy_blocker(blocker)
        return {
            "event_type": "action_time_processing_blocked",
            "notify": True,
            "decision_status": (
                "needs_intervention" if policy_blocked else "temporarily_unavailable"
            ),
            "strategy_group_id": str(
                row.get("strategy_group_id")
                or (scope_parts[1] if len(scope_parts) == 4 else "runtime")
            ),
            "symbol": str(
                row.get("symbol")
                or (scope_parts[2] if len(scope_parts) == 4 else "all")
            ),
            "side": str(
                row.get("side")
                or (scope_parts[3] if len(scope_parts) == 4 else "")
            ),
            "checkpoint": process_name,
            "blocker_class": (
                "policy_scope_missing"
                if policy_blocked
                else "action_time_boundary_not_reproduced"
            ),
            "reasons": ["action_time_processing_blocked", blocker],
            "owner_message": (
                "当前交易风险范围尚未配置，本次未交易，需要确认风险策略。"
                if policy_blocked
                else "发现交易机会；系统处理链路未完成，本次未交易，系统正在自动处理。"
            ),
        }
    if (
        process_name == "live_signal_materialization"
        and len(scope_parts) == 4
        and scope_parts[0] == "lane"
    ):
        return {
            "event_type": "signal_identity_gap",
            "notify": True,
            "decision_status": "temporarily_unavailable",
            "strategy_group_id": scope_parts[1],
            "symbol": scope_parts[2],
            "side": scope_parts[3],
            "checkpoint": process_name,
            "blocker_class": "runtime_data_gap",
            "reasons": ["signal_identity_gap", blocker],
            "owner_message": (
                "信号状态不一致，未下单；系统将继续处理，无需操作"
            ),
        }
    return {
        "event_type": "runtime_process_failure",
        "notify": True,
        "decision_status": "needs_intervention"
        if hard
        else "temporarily_unavailable",
        "strategy_group_id": "runtime",
        "symbol": str(row.get("scope_key") or "all"),
        "checkpoint": process_name,
        "blocker_class": "runtime_process_failure",
        "reasons": ["runtime_process_failure", blocker],
        "owner_message": (
            "运行流程发生硬失败，需要介入"
            if hard
            else "运行流程暂时不可用，系统需要恢复"
        ),
    }


def _runtime_process_outcome_requires_monitor_attention(
    control_state: dict[str, Any],
    row: dict[str, Any],
) -> bool:
    process_state = str(row.get("process_state") or "")
    process_name = str(row.get("process_name") or "")
    if process_state in {"retryable_failure", "hard_failure"}:
        return (
            process_name
            not in {"action_time_ticket_sequence", "action_time_ticket_sequence_batch"}
            or process_outcome_has_current_blocking_authority(control_state, row)
        )
    return (
        process_state == "business_blocked"
        and process_name
        in {
            "action_time_ticket_sequence",
            "action_time_ticket_sequence_batch",
            "action_time_refresh_sequence",
        }
        and process_outcome_has_current_blocking_authority(control_state, row)
    )


def _lifecycle_safety_event(
    rows: list[dict[str, Any]],
    *,
    now_ms: int,
) -> dict[str, Any]:
    _ = now_ms
    unprotected_statuses = {
        "entry_filled",
        "entry_unknown",
        "entry_orphaned",
        "entry_partial_fill_unhandled",
        "protection_missing",
        "protection_submit_failed",
        "protection_reconciliation_mismatch",
    }
    unsafe = [
        row
        for row in rows
        if str(row.get("status") or "") in unprotected_statuses
    ]
    if not unsafe:
        return {}
    row = max(unsafe, key=lambda item: int(item.get("updated_at_ms") or 0))
    return {
        "event_type": "submitted_position_unprotected",
        "notify": True,
        "decision_status": "needs_intervention",
        "strategy_group_id": row.get("strategy_group_id"),
        "symbol": row.get("symbol"),
        "side": row.get("side"),
        "checkpoint": "ticket_bound_order_lifecycle",
        "blocker_class": "submitted_position_unprotected",
        "reasons": [
            "submitted_position_unprotected",
            str(row.get("status") or ""),
            str(row.get("lifecycle_run_id") or ""),
        ],
        "owner_message": "已提交仓位缺少已验证保护，需要介入",
    }


def _exchange_command_chain_event(
    commands: list[dict[str, Any]],
    *,
    now_ms: int,
) -> dict[str, Any]:
    unresolved = [
        row
        for row in commands
        if str(row.get("command_state") or "")
        in {"dispatching", "outcome_unknown", "hard_stopped"}
    ]
    if not unresolved:
        return {}

    def event(
        row: dict[str, Any],
        *,
        notify: bool,
        status: str,
        blocker: str,
    ) -> dict[str, Any]:
        return {
            "event_type": "exchange_command_state",
            "notify": notify,
            "decision_status": status,
            "strategy_group_id": row.get("strategy_group_id"),
            "symbol": row.get("symbol"),
            "side": row.get("side"),
            "checkpoint": "ticket_bound_exchange_command",
            "blocker_class": blocker,
            "reasons": [blocker, str(row.get("exchange_command_id") or "")],
            "owner_message": (
                "交易命令结果需要介入核对"
                if notify
                else "交易命令处理中，无需操作"
            ),
        }

    hard_stopped = [
        row
        for row in unresolved
        if str(row.get("command_state") or "") == "hard_stopped"
    ]
    if hard_stopped:
        row = max(hard_stopped, key=lambda item: int(item.get("updated_at_ms") or 0))
        return event(
            row,
            notify=True,
            status="needs_intervention",
            blocker="exchange_command_hard_stopped",
        )

    unknown = [
        row
        for row in unresolved
        if str(row.get("command_state") or "") == "outcome_unknown"
    ]
    overdue_unknown = [
        row
        for row in unknown
        if now_ms - int(row.get("updated_at_ms") or 0) >= 30_000
    ]
    if overdue_unknown:
        row = min(
            overdue_unknown,
            key=lambda item: int(item.get("updated_at_ms") or 0),
        )
        return event(
            row,
            notify=True,
            status="needs_intervention",
            blocker="exchange_command_outcome_unknown",
        )

    dispatching = [
        row
        for row in unresolved
        if str(row.get("command_state") or "") == "dispatching"
    ]
    overdue_dispatching = [
        row
        for row in dispatching
        if now_ms - int(row.get("updated_at_ms") or 0) >= 60_000
    ]
    if overdue_dispatching:
        row = min(
            overdue_dispatching,
            key=lambda item: int(item.get("updated_at_ms") or 0),
        )
        return event(
            row,
            notify=True,
            status="needs_intervention",
            blocker="exchange_command_dispatch_overdue",
        )

    processing = unknown or dispatching
    row = max(processing, key=lambda item: int(item.get("updated_at_ms") or 0))
    return event(
        row,
        notify=False,
        status="processing",
        blocker="exchange_command_processing",
    )


def _is_current_monitor_ticket(ticket: dict[str, Any], now_ms: int) -> bool:
    status = str(ticket.get("status") or "")
    if status == "submitted":
        return True
    if status not in {"created", "preflight_pending", "finalgate_ready"}:
        return False
    return int(ticket.get("expires_at_ms") or 0) > now_ms


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
    control_state: dict[str, Any],
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
    chain_event = _recent_pg_chain_event(control_state)

    if not systemd.get("ready"):
        reasons.extend([str(item) for item in systemd.get("blockers") or []])
        blocker_class = "watcher_or_service_failure"
        checkpoint = "systemd"
    elif chain_event:
        event_side = str(chain_event.get("side") or "")
        event_symbol = str(chain_event.get("symbol") or symbol)
        notify = chain_event.get("notify") is not False
        return {
            "event_type": str(chain_event.get("event_type") or ""),
            "decision": "notify" if notify else "quiet",
            "notify": notify,
            "status": str(
                chain_event.get("decision_status")
                or ("needs_intervention" if notify else "processing")
            ),
            "reasons": _dedupe([str(item) for item in chain_event.get("reasons") or []]),
            "automation_id": "tokyo-runtime-server-monitor",
            "strategy_group_id": str(
                chain_event.get("strategy_group_id") or strategy_group_id
            ),
            "symbol": event_symbol or symbol,
            "side": event_side if event_side in {"long", "short"} else None,
            "blocker_class": str(chain_event.get("blocker_class") or "fresh_signal"),
            "checkpoint": str(chain_event.get("checkpoint") or checkpoint),
            "owner_message": str(
                chain_event.get("owner_message")
                or "检测到交易链路事件，系统已按边界处理"
            ),
        }

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
    elif (
        status == "missing_fact"
        and checks.get("fresh_signal_present") is False
        and goal_status.get("owner_action_required") is not True
        and coverage_complete
        and systemd.get("ready")
    ):
        preserved_blocker = _first_meaningful_blocker(blockers)
        return {
            "decision": "quiet",
            "notify": False,
            "status": "healthy_waiting_quiet",
            "reasons": blockers,
            "automation_id": "tokyo-runtime-server-monitor",
            "strategy_group_id": strategy_group_id,
            "symbol": symbol,
            "blocker_class": preserved_blocker,
            "checkpoint": (
                "certify_current_release_action_time_capability"
                if preserved_blocker == "action_time_boundary_not_reproduced"
                else checkpoint
            ),
            "owner_message": "当前无新信号，前置工程阻断已记录，无需操作",
        }
    elif status == "protected_submit_rehearsal_completed":
        return {
            "decision": "quiet",
            "notify": False,
            "status": "protected_submit_rehearsal_completed_quiet",
            "reasons": [],
            "automation_id": "tokyo-runtime-server-monitor",
            "strategy_group_id": strategy_group_id,
            "symbol": symbol,
            "blocker_class": "none",
            "checkpoint": "ticket_bound_protected_submit",
            "owner_message": "已完成非执行提交演练，无需操作",
        }
    elif status in {
        "fresh_signal_detected",
        "fresh_signal_processing",
        "action_time_finalgate_ready",
        "operation_layer_ready",
        "real_order_submitted",
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
    return f"server_monitor_run:{now_ms}:{digest}:{uuid.uuid4().hex[:12]}"


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


def _resolve_pg_notifications(
    *,
    conn: sa.engine.Connection,
    automation_id: str,
    now_ms: int,
    reason: str,
) -> int:
    table = _table(conn, "brc_server_monitor_notifications")
    result = conn.execute(
        table.update()
        .where(table.c.automation_id == automation_id)
        .where(table.c.notification_state != "resolved")
        .values(
            notification_state="resolved",
            last_error=None,
            feishu_response={
                "resolved": True,
                "resolution_reason": reason,
            },
            updated_at_ms=now_ms,
        )
    )
    return int(result.rowcount or 0)


def _table(conn: sa.engine.Connection, table_name: str) -> sa.Table:
    metadata = sa.MetaData()
    return sa.Table(table_name, metadata, autoload_with=conn)


def _typed_owner_notification_schema_available(
    conn: sa.engine.Connection,
) -> bool:
    if not sa.inspect(conn).has_table("brc_server_monitor_notifications"):
        return False
    columns = {
        item["name"]
        for item in sa.inspect(conn).get_columns("brc_server_monitor_notifications")
    }
    return {
        "notification_kind",
        "severity",
        "correlation_id",
        "template_version",
        "owner_action_required",
        "occurred_at_ms",
        "resolved_at_ms",
    } <= columns


def _monitor_decision_owner_intent(
    decision: dict[str, Any],
    *,
    now_ms: int,
) -> OwnerNotificationIntent | None:
    if not decision.get("notify"):
        return None
    blocker_class = str(decision.get("blocker_class") or "runtime_unavailable")
    if blocker_class == "fresh_signal":
        return None
    strategy_group_id = str(decision.get("strategy_group_id") or "runtime")
    symbol = str(decision.get("symbol") or "all")
    temporary = blocker_class in {
        "runtime_data_gap",
        "watcher_or_service_failure",
        "runtime_process_failure",
    }
    signal_identity_gap = str(decision.get("event_type") or "") == (
        "signal_identity_gap"
    )
    kind = (
        OwnerNotificationKind.SYSTEM_TEMPORARILY_UNAVAILABLE
        if temporary
        else OwnerNotificationKind.INTERVENTION_REQUIRED
    )
    return OwnerNotificationIntent(
        notification_kind=kind,
        severity=(
            OwnerNotificationSeverity.WARNING
            if temporary
            else OwnerNotificationSeverity.CRITICAL
        ),
        correlation_id="monitor:" + _dedupe_identity(decision),
        strategy_group_id=strategy_group_id,
        symbol=symbol,
        side=(
            str(decision.get("side"))
            if str(decision.get("side") or "") in {"long", "short"}
            else None
        ),
        occurred_at_ms=now_ms,
        headline=(
            "信号状态不一致，未下单"
            if signal_identity_gap
            else ("系统暂时不可用" if temporary else "需要你关注运行状态")
        ),
        current_state=(
            "系统没有为这次观察建立正式交易信号"
            if signal_identity_gap
            else "部分自动观察或处理暂时无法继续"
            if temporary
            else "系统已经停止相关的新交易推进"
        ),
        result_summary=("没有下单" if signal_identity_gap else "没有新增交易动作"),
        plain_reason=(
            "市场观察结果和正式交易事实没有成功衔接"
            if signal_identity_gap
            else _plain_monitor_reason(blocker_class)
        ),
        next_system_action=(
            "系统继续核对信号事实并等待下一次有效机会"
            if signal_identity_gap
            else "系统继续进行只读检查，并在恢复后通知你"
        ),
        owner_action_required=not temporary,
        owner_action=("检查服务器或交易所状态" if not temporary else None),
        technical_refs=(
            f"blocker_class:{blocker_class}",
            f"checkpoint:{str(decision.get('checkpoint') or '')}",
        ),
    )


def _plain_monitor_reason(blocker_class: str) -> str:
    if blocker_class == "watcher_or_service_failure":
        return "服务器观察服务没有正常完成"
    if blocker_class in {"runtime_data_gap", "runtime_process_failure"}:
        return "系统暂时无法读取完整、可信的运行数据"
    if blocker_class in {"hard_safety_stop", "exchange_command_outcome_unknown"}:
        return "交易安全检查要求暂停并核对外部事实"
    if blocker_class in {"policy_scope_missing", "budget_gap"}:
        return "当前交易范围或资金条件尚未满足"
    return "最新运行检查要求暂停相关推进"


def _apply_pg_owner_notifications(
    *,
    conn: sa.engine.Connection,
    automation_id: str,
    control_state: dict[str, Any],
    now_ms: int,
    webhook_url: str | None,
    webhook_secret: str | None,
    notification_timeout_seconds: float,
    notification_dry_run: bool,
    notifier: Notifier | None,
    decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    intents = project_owner_notification_intents(control_state, now_ms=now_ms)
    fallback = _monitor_decision_owner_intent(decision or {}, now_ms=now_ms)
    if fallback is not None:
        intents = [
            item
            for item in intents
            if not (
                item.notification_kind is OwnerNotificationKind.INCIDENT_RECOVERED
                and item.correlation_id == fallback.correlation_id
            )
        ]
        if not any(
            item.correlation_id == fallback.correlation_id
            and item.notification_kind is fallback.notification_kind
            for item in intents
        ):
            intents = [fallback, *intents]
    table = _table(conn, "brc_server_monitor_notifications")
    sender = notifier or send_feishu_payload
    results: list[dict[str, Any]] = []
    sent_count = 0
    ledger_rows = _pg_owner_notification_rows(
        conn,
        automation_id=automation_id,
        intents=intents,
    )
    selection = select_owner_notification_delivery_batch(
        intents,
        ledger_rows,
        limit=MAX_INTENTS_PER_RUN,
    )
    for intent in selection.selected:
        delivery_identity = owner_notification_delivery_identity(intent)
        dedupe_key = owner_notification_dedupe_key(automation_id, intent)
        existing = ledger_rows.get(delivery_identity, {})
        attempts = int(existing.get("send_attempts") or 0)
        previous_state = str(existing.get("notification_state") or "")
        reopened = delivery_identity in selection.reopened_dedupe_keys
        if reopened:
            attempts = 0
        attempted = False
        sent = False
        skipped_reason: str | None = None
        response: dict[str, Any] = {}
        if not webhook_url:
            skipped_reason = "feishu_webhook_url_missing"
        elif notification_dry_run:
            skipped_reason = "notification_dry_run"
        else:
            attempted = True
            response = sender(
                webhook_url,
                webhook_secret,
                render_owner_notification_card(intent),
                notification_timeout_seconds,
            )
            attempts += 1
            sent = bool(response.get("sent"))
            if sent:
                sent_count += 1
        state = (
            "sent"
            if sent or previous_state == "sent"
            else "failed"
            if attempted or skipped_reason == "retry_exhausted"
            else "suppressed"
            if skipped_reason == "dedupe_suppressed"
            else "pending"
        )
        values = {
            "notification_id": str(
                existing.get("notification_id")
                or _notification_id_from_identity(dedupe_key)
            ),
            "dedupe_key": dedupe_key,
            "automation_id": automation_id,
            "strategy_group_id": intent.strategy_group_id,
            "symbol": intent.symbol,
            "blocker_class": intent.notification_kind.value,
            "checkpoint": "owner_notification",
            "notification_state": state,
            "first_seen_at_ms": int(existing.get("first_seen_at_ms") or now_ms),
            "last_notified_at_ms": (
                now_ms if sent else existing.get("last_notified_at_ms")
            ),
            "last_seen_at_ms": now_ms,
            "send_attempts": attempts,
            "last_error": response.get("error"),
            "feishu_response": {
                "sent": sent,
                "status_code": response.get("status_code"),
                "business_code": response.get("business_code"),
                "business_message": response.get("business_message"),
                "response_body_preview": response.get("response_body_preview"),
                "skipped_reason": skipped_reason,
            },
            "created_at_ms": int(existing.get("created_at_ms") or now_ms),
            "updated_at_ms": now_ms,
            "notification_kind": intent.notification_kind.value,
            "severity": intent.severity.value,
            "correlation_id": intent.correlation_id,
            "template_version": intent.template_version,
            "owner_action_required": intent.owner_action_required,
            "occurred_at_ms": intent.occurred_at_ms,
            "resolved_at_ms": (
                None if reopened else existing.get("resolved_at_ms")
            ),
        }
        if not notification_dry_run:
            if existing:
                existing_dedupe_key = str(existing.get("dedupe_key") or dedupe_key)
                conn.execute(
                    table.update()
                    .where(table.c.dedupe_key == existing_dedupe_key)
                    .values(**{
                        key: value
                        for key, value in values.items()
                        if key not in {"notification_id", "dedupe_key", "created_at_ms"}
                    })
                )
            else:
                conn.execute(table.insert().values(**values))
            if sent and intent.notification_kind is OwnerNotificationKind.INCIDENT_RECOVERED:
                conn.execute(
                    table.update()
                    .where(table.c.correlation_id == intent.correlation_id)
                    .where(
                        table.c.notification_kind.in_(
                            (
                                OwnerNotificationKind.INTERVENTION_REQUIRED.value,
                                OwnerNotificationKind.SYSTEM_TEMPORARILY_UNAVAILABLE.value,
                            )
                        )
                    )
                    .values(
                        notification_state="resolved",
                        resolved_at_ms=now_ms,
                        updated_at_ms=now_ms,
                    )
                )
        results.append(
            {
                "notification_kind": intent.notification_kind.value,
                "correlation_id": intent.correlation_id,
                "attempted": attempted,
                "sent": sent,
                "skipped_reason": skipped_reason,
                "send_attempts": attempts,
            }
        )
    return {
        "schema": "brc.owner_notification_delivery.v1",
        "required": bool(intents),
        "attempted": any(item["attempted"] for item in results),
        "sent": sent_count > 0,
        "sent_count": sent_count,
        "suppressed_count": selection.suppressed_count,
        "retry_exhausted_count": selection.retry_exhausted_count,
        "reopened_incident_count": selection.reopened_incident_count,
        "intent_count": len(intents),
        "results": results,
        "skipped_reason": (
            str((decision or {}).get("status") or "healthy_waiting_quiet")
            if not intents
            else None
        ),
        "source": "pg:brc_server_monitor_notifications",
    }


def _pg_owner_notification_rows(
    conn: sa.engine.Connection,
    *,
    automation_id: str,
    intents: list[OwnerNotificationIntent],
) -> dict[str, dict[str, Any]]:
    """Resolve exact ledger keys before bounded legacy compatibility rows."""
    if not intents:
        return {}

    unique_intents: dict[str, OwnerNotificationIntent] = {}
    for intent in intents:
        unique_intents.setdefault(owner_notification_delivery_identity(intent), intent)
    candidate_intents = list(unique_intents.values())

    dedupe_keys = [
        owner_notification_dedupe_key(automation_id, intent)
        for intent in candidate_intents
    ]
    exact_rows: list[dict[str, Any]] = []
    for dedupe_key_chunk in _chunks(dedupe_keys, size=500):
        exact_rows.extend(
            dict(row)
            for row in conn.execute(
                sa.text(
                    """
                    SELECT *
                    FROM brc_server_monitor_notifications
                    WHERE dedupe_key IN :dedupe_keys
                    """
                ).bindparams(sa.bindparam("dedupe_keys", expanding=True)),
                {"dedupe_keys": dedupe_key_chunk},
            ).mappings()
        )

    by_dedupe_key = {
        str(row.get("dedupe_key") or ""): row for row in exact_rows
    }
    resolved: dict[str, dict[str, Any]] = {}
    unresolved: list[OwnerNotificationIntent] = []
    for intent in candidate_intents:
        delivery_identity = owner_notification_delivery_identity(intent)
        exact = by_dedupe_key.get(
            owner_notification_dedupe_key(automation_id, intent)
        )
        if exact:
            resolved[delivery_identity] = exact
        else:
            unresolved.append(intent)

    if not unresolved:
        return resolved

    correlations: set[str] = set()
    notification_kinds: set[str] = set()
    for intent in unresolved:
        normalized = normalize_owner_correlation_id(intent.correlation_id)
        correlations.add(normalized)
        notification_kinds.add(intent.notification_kind.value)
        for prefix in ("signal", "ticket"):
            if normalized.startswith(f"{prefix}:"):
                correlations.add(f"{prefix}:{normalized}")

    legacy_rows: list[dict[str, Any]] = []
    for correlation_chunk in _chunks(sorted(correlations), size=500):
        legacy_rows.extend(
            dict(row)
            for row in conn.execute(
                sa.text(
                    """
                    SELECT *
                    FROM brc_server_monitor_notifications
                    WHERE notification_kind IN :notification_kinds
                      AND correlation_id IN :correlation_ids
                    ORDER BY updated_at_ms DESC, created_at_ms DESC, notification_id DESC
                    """
                ).bindparams(
                    sa.bindparam("notification_kinds", expanding=True),
                    sa.bindparam("correlation_ids", expanding=True),
                ),
                {
                    "notification_kinds": sorted(notification_kinds),
                    "correlation_ids": correlation_chunk,
                },
            ).mappings()
        )

    latest_legacy_rows: dict[tuple[str, str], dict[str, Any]] = {}
    for row in legacy_rows:
        identity = (
            str(row.get("notification_kind") or ""),
            normalize_owner_correlation_id(str(row.get("correlation_id") or "")),
        )
        latest_legacy_rows.setdefault(identity, row)

    for intent in unresolved:
        resolved_row = latest_legacy_rows.get(
            (
                intent.notification_kind.value,
                normalize_owner_correlation_id(intent.correlation_id),
            )
        )
        if resolved_row:
            resolved[owner_notification_delivery_identity(intent)] = resolved_row
    return resolved


def _chunks(values: list[str], *, size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


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
        notification["skipped_reason"] = str(
            decision.get("status") or "healthy_waiting_quiet"
        )
        resolved_count = _resolve_pg_notifications(
            conn=conn,
            automation_id=str(decision.get("automation_id") or ""),
            now_ms=now_ms,
            reason=str(decision.get("status") or "quiet"),
        )
        notification["resolved_historical_notification_count"] = resolved_count
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
                "business_code": notification.get("business_code"),
                "business_message": notification.get("business_message"),
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
    from src.application.readmodels.strategy_live_candidate_pool import (  # noqa: PLC0415
        build_strategy_live_candidate_pool_from_control_state,
    )
    from src.application.readmodels.strategygroup_runtime_goal_status import (  # noqa: PLC0415
        build_goal_status_artifact_from_control_state,
    )

    now = _utc_now_from_args(args)
    repository = PgBackedRuntimeControlStateRepository(
        conn,
        now_ms=getattr(args, "now_ms", None),
    )
    systemd = (
        {"checked": False, "ready": True, "rows": [], "blockers": []}
        if args.skip_systemd
        else _systemd_status(list(args.systemd_unit or []), runner=systemd_runner)
    )
    source_errors: dict[str, Any] = {}
    control_state: dict[str, Any] = {}
    try:
        control_state = repository.read_monitor_control_state()
        candidate_pool = build_strategy_live_candidate_pool_from_control_state(control_state)
        goal_status = build_goal_status_artifact_from_control_state(
            control_state=control_state,
        )
        decision = _decision_from_pg_sources(
            control_state=control_state,
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
    if _typed_owner_notification_schema_available(conn):
        notification = _apply_pg_owner_notifications(
            conn=conn,
            automation_id=str(decision.get("automation_id") or "runtime-monitor"),
            control_state=control_state,
            now_ms=_utc_to_ms(now),
            webhook_url=webhook_url,
            webhook_secret=webhook_secret,
            notification_timeout_seconds=args.notification_timeout_seconds,
            notification_dry_run=bool(args.notification_dry_run),
            notifier=notifier,
            decision=decision,
        )
        dedupe_state = {
            "schema": "brc.server_runtime_monitor_dedupe_state.pg.v2",
            "source": "pg:brc_server_monitor_notifications",
            "event_count": conn.execute(
                sa.text("SELECT COUNT(*) FROM brc_server_monitor_notifications")
            ).scalar_one(),
            "trading_authority": False,
        }
    else:
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
    parser.add_argument("--now-ms", type=int, help=argparse.SUPPRESS)
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
