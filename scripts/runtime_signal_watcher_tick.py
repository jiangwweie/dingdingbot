#!/usr/bin/env python3
"""Run one read-only runtime signal watcher tick with optional Feishu wake-up.

The watcher is intentionally one-shot so it can be driven by a systemd timer.
It reuses the active observation supervisor, writes auditable JSON packets, and
only sends a notification when owner attention is required. It never submits,
places orders, calls OrderLifecycle, mutates runtime budget, or transfers funds.
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

from scripts import runtime_active_observation_supervisor as supervisor  # noqa: E402
from scripts.build_runtime_observation_operator_packet import (  # noqa: E402
    build_operator_packet_from_path,
)
from scripts.build_runtime_observation_wakeup_packet import (  # noqa: E402
    build_wakeup_packet,
)
from scripts.runtime_active_observation_status import build_status_packet  # noqa: E402


OWNER_ATTENTION_STATUSES = {
    "blocked_forbidden_effect",
    "runtime_signal_ready_for_non_executing_prepare",
    "prepared_shadow_evidence_ready_for_owner_review",
    "operator_packet_needs_review",
}
STATUS_PACKET_ATTENTION_STATUSES = {"attention", "blocked", "blocked_forbidden_effect", "stale"}


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


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _state_path(output_dir: Path, value: str | None) -> Path:
    return Path(value).expanduser() if value else output_dir / "notification-state.json"


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
    status_packet: dict[str, Any],
    operator_packet: dict[str, Any],
    wakeup_packet: dict[str, Any],
) -> str:
    summary = wakeup_packet.get("summary") if isinstance(wakeup_packet.get("summary"), dict) else {}
    parts = [
        str(wakeup_packet.get("status") or ""),
        str(operator_packet.get("status") or ""),
        str(status_packet.get("latest_status") or ""),
        str(summary.get("prepared_authorization_id") or ""),
        str(summary.get("shadow_candidate_id") or ""),
    ]
    return "|".join(parts)


def _notification_required(
    *,
    args: argparse.Namespace,
    status_packet: dict[str, Any],
    wakeup_packet: dict[str, Any],
    auto_resume: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    auto_resume_status = str((auto_resume or {}).get("status") or "")
    if auto_resume_status == "waiting_for_market":
        return False, "waiting_for_market_no_owner_attention_needed"
    wakeup_status = str(wakeup_packet.get("status") or "")
    status_status = str(status_packet.get("status") or "")
    if args.notify_no_signal and wakeup_status in {
        "owner_sleep_safe_observation_running",
        "observation_window_complete_no_signal",
    }:
        return True, "notify_no_signal_enabled"
    if wakeup_status in OWNER_ATTENTION_STATUSES:
        return True, f"wakeup_status:{wakeup_status}"
    if status_status in STATUS_PACKET_ATTENTION_STATUSES:
        return True, f"status_packet:{status_status}"
    return False, "no_owner_attention_needed"


def _notification_text(
    *,
    args: argparse.Namespace,
    status_packet: dict[str, Any],
    operator_packet: dict[str, Any],
    wakeup_packet: dict[str, Any],
    paths: dict[str, str],
) -> str:
    summary = wakeup_packet.get("summary") if isinstance(wakeup_packet.get("summary"), dict) else {}
    monitored_count = summary.get("monitored_runtime_count")
    active_count = summary.get("active_runtime_count")
    if monitored_count is None:
        runtime_count_line = f"active runtimes: {active_count}"
    elif active_count is not None and active_count != monitored_count:
        runtime_count_line = f"monitored runtimes: {monitored_count} (active total: {active_count})"
    else:
        runtime_count_line = f"monitored runtimes: {monitored_count}"
    lines = [
        f"BRC runtime signal watcher: {wakeup_packet.get('status')}",
        f"env: {args.label}",
        f"operator: {operator_packet.get('status')}",
        runtime_count_line,
        f"ready runtime signals: {summary.get('runtime_ready_signal_count')}",
        f"prepared authorization: {summary.get('prepared_authorization_id') or '-'}",
        f"shadow candidate: {summary.get('shadow_candidate_id') or '-'}",
        f"next: {summary.get('next_step') or (operator_packet.get('operator_command_plan') or {}).get('next_step') or '-'}",
        f"evidence: {paths.get('wakeup_packet_json')}",
    ]
    blockers = status_packet.get("blockers") or operator_packet.get("blockers") or []
    if blockers:
        lines.append("blockers: " + ", ".join(str(item) for item in blockers[:6]))
    return "\n".join(lines)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _post_signal_auto_resume_plan(
    *,
    args: argparse.Namespace,
    status_packet: dict[str, Any],
    operator_packet: dict[str, Any],
    wakeup_packet: dict[str, Any],
) -> dict[str, Any]:
    latest_status = str(status_packet.get("latest_status") or "")
    status_status = str(status_packet.get("status") or "")
    wakeup_status = str(wakeup_packet.get("status") or "")
    operator_status = str(operator_packet.get("status") or "")
    forbidden_effects = list(status_packet.get("forbidden_effects") or [])
    blockers = [str(item) for item in status_packet.get("blockers") or []]
    prepared_authorization_id = status_packet.get("prepared_authorization_id")
    shadow_candidate_id = status_packet.get("shadow_candidate_id")
    summary = _as_dict(wakeup_packet.get("summary"))
    prepared_authorization_id = (
        prepared_authorization_id or summary.get("prepared_authorization_id")
    )
    shadow_candidate_id = shadow_candidate_id or summary.get("shadow_candidate_id")

    base = {
        "source": "runtime_signal_watcher_tick",
        "latest_status": latest_status,
        "status_packet_status": status_status,
        "wakeup_status": wakeup_status,
        "operator_status": operator_status,
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
            "automatic_recovery_action": "stop_and_investigate_watcher_evidence",
            "downgrade_mode": "manual_review_only",
            "can_continue_without_owner_chat": False,
            "creates_shadow_candidate": False,
            "creates_execution_intent": False,
        }

    if status_status in {"blocked", "stale"}:
        return {
            **base,
            "status": "blocked_observation_evidence",
            "blocked_at": "active_observation_status",
            "blocked_reason": status_status,
            "next_recover_condition": "fresh_non_forbidden_observation_packets_exist",
            "automatic_recovery_action": "refresh_or_restart_active_observation_status",
            "downgrade_mode": "observe_only_no_candidate_prepare",
            "can_continue_without_owner_chat": False,
            "creates_shadow_candidate": False,
            "creates_execution_intent": False,
        }

    if latest_status in {
        "ready_for_final_gate_preflight",
        "ready_for_disabled_smoke",
        "disabled_smoke_completed",
    } or prepared_authorization_id:
        return {
            **base,
            "status": "ready_for_action_time_final_gate",
            "blocked_at": "FinalGate",
            "blocked_reason": "action_time_final_gate_not_run_yet",
            "next_recover_condition": (
                "official_final_gate_preflight_passes_with_current_facts"
            ),
            "automatic_recovery_action": "run_official_action_time_final_gate_preflight",
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
    if latest_status in ready_prepare_statuses or wakeup_status in ready_prepare_statuses:
        automatic_recovery_action = (
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
            "automatic_recovery_action": automatic_recovery_action,
            "downgrade_mode": "armed_observation_no_real_submit",
            "can_continue_without_owner_chat": True,
            "creates_shadow_candidate": bool(args.allow_prepare_records),
            "creates_execution_intent": False,
        }

    no_signal = (
        "strategy_signal_not_ready_for_shadow_candidate_prepare" in ",".join(blockers)
        or status_status
        in {"waiting_for_signal", "observation_window_complete_no_signal", "ok"}
        or wakeup_status
        in {
            "operator_packet_needs_review",
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
            "automatic_recovery_action": "continue_watcher_observation",
            "downgrade_mode": "observe_only",
            "can_continue_without_owner_chat": True,
            "creates_shadow_candidate": False,
            "creates_execution_intent": False,
        }

    return {
        **base,
        "status": "blocked_operator_review",
        "blocked_at": "operator_packet",
        "blocked_reason": wakeup_status or operator_status or "unknown",
        "next_recover_condition": "operator_packet_maps_to_waiting_or_ready_signal",
        "automatic_recovery_action": "rebuild_operator_and_wakeup_packets",
        "downgrade_mode": "observe_only_no_candidate_prepare",
        "can_continue_without_owner_chat": False,
        "creates_shadow_candidate": False,
        "creates_execution_intent": False,
    }


def _supervisor_args(args: argparse.Namespace, output_dir: Path) -> argparse.Namespace:
    return argparse.Namespace(
        output_dir=str(output_dir),
        supervisor_output_json=str(output_dir / "supervisor-packet.json"),
        loop_output_json=str(output_dir / "loop-packet.json"),
        followup_output_json=str(output_dir / "followup-packet.json"),
        status_output_json=str(output_dir / "status-packet.json"),
        env_file=args.env_file,
        api_base=args.api_base,
        source=args.source,
        runtime_instance_id=list(args.runtime_instance_id or []),
        strategy_family_id=list(args.strategy_family_id or []),
        max_iterations=args.max_iterations,
        loop_interval_seconds=args.loop_interval_seconds,
        cycle_timeout_seconds=args.cycle_timeout_seconds,
        status_stale_after_seconds=args.status_stale_after_seconds,
        one_hour_limit=args.one_hour_limit,
        four_hour_limit=args.four_hour_limit,
        allow_prepare_records=args.allow_prepare_records,
        allow_arm_preview=False,
        allow_disabled_smoke=False,
        include_packets=args.include_packets,
        skip_disabled_smoke_prerequisite_probe=True,
    )


def build_watcher_tick_packet(
    args: argparse.Namespace,
    *,
    supervisor_builder: SupervisorBuilder | None = None,
    notifier: Notifier | None = None,
) -> dict[str, Any]:
    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    state_file = _state_path(output_dir, args.state_json)
    previous_state = _read_json(state_file)

    supervisor_builder = supervisor_builder or supervisor.build_supervisor_packet
    supervisor_packet = supervisor_builder(_supervisor_args(args, output_dir))
    _write_json(output_dir / "supervisor-packet.json", supervisor_packet)

    status_packet = build_status_packet(
        output_dir,
        stale_after_seconds=args.status_stale_after_seconds,
    )
    _write_json(output_dir / "status-packet.json", status_packet)
    _write_json(output_dir / "latest-status.json", status_packet)

    operator_packet = build_operator_packet_from_path(
        status_packet_json=output_dir / "status-packet.json",
        strategy_source=args.strategy_source,
    )
    _write_json(output_dir / "operator-packet.json", operator_packet)

    wakeup_packet = build_wakeup_packet(operator_packet)
    _write_json(output_dir / "wakeup-packet.json", wakeup_packet)
    auto_resume = _post_signal_auto_resume_plan(
        args=args,
        status_packet=status_packet,
        operator_packet=operator_packet,
        wakeup_packet=wakeup_packet,
    )
    status_safety = status_packet.get("safety_invariants")
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
        status_packet=status_packet,
        operator_packet=operator_packet,
        wakeup_packet=wakeup_packet,
    )
    required, reason = _notification_required(
        args=args,
        status_packet=status_packet,
        wakeup_packet=wakeup_packet,
        auto_resume=auto_resume,
    )
    duplicate = previous_state.get("last_notified_event_key") == event_key
    webhook_url = _webhook_url(args)
    webhook_secret = _webhook_secret(args)
    paths = {
        "status_packet_json": str(output_dir / "status-packet.json"),
        "operator_packet_json": str(output_dir / "operator-packet.json"),
        "wakeup_packet_json": str(output_dir / "wakeup-packet.json"),
        "watcher_tick_json": str(output_dir / "watcher-tick.json"),
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
            status_packet=status_packet,
            operator_packet=operator_packet,
            wakeup_packet=wakeup_packet,
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
        "last_wakeup_status": wakeup_packet.get("status"),
        "last_operator_status": operator_packet.get("status"),
        "last_status_packet_status": status_packet.get("status"),
        "last_observed_at_ms": int(time.time() * 1000),
        "last_notified_event_key": (
            event_key if notification.get("sent") else previous_state.get("last_notified_event_key")
        ),
    }
    _write_json(state_file, state)

    packet = {
        "scope": "runtime_signal_watcher_tick",
        "status": _tick_status(notification, wakeup_packet, status_packet),
        "output_dir": str(output_dir),
        "paths": paths,
        "event_key": event_key,
        "supervisor_status": supervisor_packet.get("status"),
        "status_packet_status": status_packet.get("status"),
        "operator_status": operator_packet.get("status"),
        "wakeup_status": wakeup_packet.get("status"),
        "post_signal_auto_resume": auto_resume,
        "notification": notification,
        "blockers": list(status_packet.get("blockers") or []),
        "warnings": list(status_packet.get("warnings") or []),
        "operator_command_plan": {
            "not_executed": True,
            "next_step": auto_resume["automatic_recovery_action"],
            "wakeup_next_step": (wakeup_packet.get("summary") or {}).get("next_step"),
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
                status_packet.get("allowed_prepare_record_effects") or []
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
            "forbidden_effects": list(status_packet.get("forbidden_effects") or []),
        },
    }
    _write_json(output_dir / "watcher-tick.json", packet)
    return packet


def _tick_status(
    notification: dict[str, Any],
    wakeup_packet: dict[str, Any],
    status_packet: dict[str, Any],
) -> str:
    if wakeup_packet.get("status") == "blocked_forbidden_effect":
        return "blocked_forbidden_effect"
    if status_packet.get("status") in {"blocked", "blocked_forbidden_effect", "stale"}:
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
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--state-json")
    parser.add_argument("--env-file")
    parser.add_argument("--api-base", default="http://127.0.0.1:18080")
    parser.add_argument("--source", choices=["live_market", "sample"], default="live_market")
    parser.add_argument(
        "--strategy-source",
        choices=["sample", "local_sqlite_fallback", "live_market"],
        default="live_market",
    )
    parser.add_argument("--runtime-instance-id", action="append", default=[])
    parser.add_argument("--strategy-family-id", action="append", default=[])
    parser.add_argument("--max-iterations", type=int, default=1)
    parser.add_argument("--loop-interval-seconds", type=float, default=0.0)
    parser.add_argument("--cycle-timeout-seconds", type=float, default=180.0)
    parser.add_argument("--status-stale-after-seconds", type=float, default=900.0)
    parser.add_argument("--one-hour-limit", type=int, default=25)
    parser.add_argument("--four-hour-limit", type=int, default=25)
    parser.add_argument("--allow-prepare-records", action="store_true")
    parser.add_argument("--include-packets", action="store_true")
    parser.add_argument("--notify-no-signal", action="store_true")
    parser.add_argument("--notification-dry-run", action="store_true")
    parser.add_argument("--notification-timeout-seconds", type=float, default=10.0)
    parser.add_argument("--feishu-webhook-url")
    parser.add_argument("--feishu-webhook-secret")
    parser.add_argument("--label", default="tokyo-runtime-signal-watcher")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    packet = build_watcher_tick_packet(args)
    print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if packet["status"] not in {"blocked_forbidden_effect"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
