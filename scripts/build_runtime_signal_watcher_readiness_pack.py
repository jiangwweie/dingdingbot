#!/usr/bin/env python3
"""Build Signal Watcher deployment and post-signal resume evidence packs.

The pack builder is read-only. It consumes watcher JSON artifacts and writes
operator evidence packets. It never sends notifications, calls exchange APIs,
creates orders, mutates PG, or advances runtime authorization.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Any


DEFAULT_REPORT_DIR = Path("/home/ubuntu/brc-deploy/reports/runtime-signal-watcher")
RESUME_READY_STATUSES = {
    "runtime_signal_ready_for_non_executing_prepare",
    "prepared_shadow_evidence_ready_for_owner_review",
}
NON_EXECUTING_PREPARE_STATUS = "ready_for_non_executing_prepare"
FRESH_AUTHORIZATION_ACTION = "prepare_fresh_candidate_authorization_evidence"
ACTIONABLE_RUNTIME_SIGNAL_STATUSES = {
    "ready_for_prepare",
    "ready_for_prepare_records",
    "runtime_signal_ready_for_non_executing_prepare",
    "prepared_shadow_evidence_ready_for_owner_review",
    "ready_for_fresh_submit_authorization",
    "waiting_for_fresh_authorization",
    "ready_for_action_time_final_gate",
    "ready_for_final_gate_preflight",
    "finalgate_ready",
}
UNSAFE_FLAGS = {
    "exchange_write_called",
    "order_created",
    "order_lifecycle_called",
    "execution_intent_created",
    "runtime_budget_mutated",
    "withdrawal_or_transfer_created",
}


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


def _mtime_ms(path: Path) -> int | None:
    if not path.exists():
        return None
    return int(path.stat().st_mtime * 1000)


def _file_status(paths: dict[str, Path]) -> dict[str, dict[str, Any]]:
    return {
        name: {
            "path": str(path),
            "present": path.exists(),
            "mtime_ms": _mtime_ms(path),
        }
        for name, path in paths.items()
    }


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value or [] if isinstance(item, dict)]


def _has_actionable_runtime_signal(
    *,
    runtime_signal_summaries: list[dict[str, Any]],
    signal_input_json: Any,
    shadow_candidate_id: Any,
    prepared_authorization_id: Any,
) -> bool:
    if any(
        str(value or "").strip()
        for value in (signal_input_json, shadow_candidate_id, prepared_authorization_id)
    ):
        return True
    return any(
        str(item.get("status") or "").strip() in ACTIONABLE_RUNTIME_SIGNAL_STATUSES
        for item in runtime_signal_summaries
    )


def _waiting_for_market_auto_resume() -> dict[str, Any]:
    return {
        "status": "waiting_for_market",
        "blocked_at": "watcher_signal",
        "blocked_reason": "no_fresh_strategy_signal",
        "next_recover_condition": (
            "runtime_signal_watcher_observes_a_fresh_signal_for_selected_scope"
        ),
        "automatic_recovery_action": "continue_watcher_observation",
        "downgrade_mode": "observe_only",
        "can_continue_without_owner_chat": True,
        "requires_action_time_final_gate": True,
        "requires_official_operation_layer": True,
    }


def _action_time_resume(
    *,
    post_signal_auto_resume: dict[str, Any],
    signal_input_json: Any,
    shadow_candidate_id: Any,
    prepared_authorization_id: Any,
    unsafe_flags: list[str],
    missing: list[str],
) -> dict[str, Any]:
    prepared = bool(str(prepared_authorization_id or "").strip())
    auto_resume_status = str(post_signal_auto_resume.get("status") or "")
    if unsafe_flags or missing:
        status = "blocked"
        next_step = "resolve_watcher_resume_blockers"
        allowed_auto_actions: list[str] = []
    elif prepared:
        status = "ready_for_action_time_final_gate"
        next_step = "run_official_action_time_final_gate_preflight"
        allowed_auto_actions = ["run_official_action_time_final_gate_preflight"]
    elif auto_resume_status == NON_EXECUTING_PREPARE_STATUS:
        status = NON_EXECUTING_PREPARE_STATUS
        next_step = "prepare_fresh_candidate_grant_authorization_evidence"
        allowed_auto_actions = [FRESH_AUTHORIZATION_ACTION]
    else:
        status = "waiting_for_market"
        next_step = (
            post_signal_auto_resume.get("automatic_recovery_action")
            or "continue_watcher_observation"
        )
        allowed_auto_actions = ["continue_watcher_observation"]

    return {
        "status": status,
        "next_step": next_step,
        "signal_input_json": signal_input_json,
        "shadow_candidate_id": shadow_candidate_id,
        "prepared_authorization_id": prepared_authorization_id,
        "allowed_auto_actions": allowed_auto_actions,
        "forbidden_auto_actions_until_final_gate_pass": [
            "official_operation_layer_submit",
            "exchange_order",
            "order_lifecycle_submit",
            "runtime_budget_mutation",
        ],
        "requires_fresh_action_time_facts": prepared,
        "requires_fresh_candidate_authorization_evidence": (
            status == NON_EXECUTING_PREPARE_STATUS
        ),
        "requires_action_time_final_gate": True,
        "requires_official_operation_layer": True,
        "final_gate_status": "not_run" if prepared else "not_reached",
        "operation_layer_status": "not_reached",
        "places_order": False,
        "calls_order_lifecycle": False,
        "exchange_write_called": False,
        "withdrawal_or_transfer_requested": False,
    }


def _owner_state(
    *,
    action_time_resume: dict[str, Any],
    post_signal_auto_resume: dict[str, Any],
) -> dict[str, Any]:
    status = str(action_time_resume.get("status") or "blocked")
    prefer_action_time_resume = status == NON_EXECUTING_PREPARE_STATUS
    if status == "waiting_for_market":
        blocker_class = "waiting_for_market"
        blocked_at = "watcher_signal"
        blocked_reason = "no_fresh_strategy_signal"
        next_recover_condition = (
            "runtime_signal_watcher_observes_a_fresh_signal_for_selected_scope"
        )
        automatic_recovery_action = "continue_watcher_observation"
        downgrade_mode = "observe_only"
    elif status == NON_EXECUTING_PREPARE_STATUS:
        blocker_class = "none"
        blocked_at = "candidate_authorization"
        blocked_reason = "fresh_signal_waiting_for_candidate_authorization_evidence"
        next_recover_condition = (
            "fresh_candidate_runtime_grant_authorization_evidence_exists"
        )
        automatic_recovery_action = FRESH_AUTHORIZATION_ACTION
        downgrade_mode = "no_real_submit_until_candidate_authorization_finalgate"
    elif status == "ready_for_action_time_final_gate":
        blocker_class = "none"
        blocked_at = "FinalGate"
        blocked_reason = "action_time_final_gate_not_run_yet"
        next_recover_condition = (
            "official_final_gate_preflight_passes_with_current_facts"
        )
        automatic_recovery_action = "run_official_action_time_final_gate_preflight"
        downgrade_mode = "no_real_submit_until_final_gate_pass"
    else:
        blocker_class = "hard_safety_stop"
        blocked_at = "watcher_resume"
        blocked_reason = "watcher_resume_blocked"
        next_recover_condition = "watcher_resume_blockers_are_resolved"
        automatic_recovery_action = "resolve_watcher_resume_blockers"
        downgrade_mode = "manual_review_only"

    return {
        "status": status,
        "blocker_class": blocker_class,
        "blocked_at": (
            None
            if prefer_action_time_resume
            else post_signal_auto_resume.get("blocked_at")
        )
        or blocked_at,
        "blocked_reason": (
            None
            if prefer_action_time_resume
            else post_signal_auto_resume.get("blocked_reason")
        )
        or blocked_reason,
        "next_recover_condition": (
            None
            if prefer_action_time_resume
            else post_signal_auto_resume.get("next_recover_condition")
        )
        or next_recover_condition,
        "automatic_recovery_action": (
            None
            if prefer_action_time_resume
            else post_signal_auto_resume.get("automatic_recovery_action")
        )
        or (
            action_time_resume.get("allowed_auto_actions") or [None]
        )[0]
        or (
            action_time_resume.get("next_step")
            or automatic_recovery_action
        ),
        "downgrade_mode": post_signal_auto_resume.get("downgrade_mode")
        or downgrade_mode,
    }


def build_pack(
    *,
    report_dir: Path,
    output_dir: Path,
    stale_after_seconds: int,
    label: str,
) -> dict[str, Any]:
    paths = {
        "watcher_tick": report_dir / "watcher-tick.json",
        "wakeup_packet": report_dir / "wakeup-packet.json",
        "operator_packet": report_dir / "operator-packet.json",
        "status_packet": report_dir / "status-packet.json",
        "notification_state": report_dir / "notification-state.json",
    }
    payloads = {name: _read_json(path) for name, path in paths.items()}
    watcher_tick = payloads["watcher_tick"]
    wakeup_packet = payloads["wakeup_packet"]
    operator_packet = payloads["operator_packet"]
    status_packet = payloads["status_packet"]
    notification_state = payloads["notification_state"]
    files = _file_status(paths)
    generated_at_ms = int(time.time() * 1000)
    latest_mtime_ms = max(
        [int(status["mtime_ms"] or 0) for status in files.values()],
        default=0,
    )
    age_seconds = int((generated_at_ms - latest_mtime_ms) / 1000) if latest_mtime_ms else None
    missing = [name for name, status in files.items() if not status["present"]]
    stale = bool(age_seconds is not None and age_seconds > stale_after_seconds)
    safety = watcher_tick.get("safety_invariants") if isinstance(watcher_tick, dict) else {}
    safety = safety if isinstance(safety, dict) else {}
    post_signal_auto_resume = _dict(watcher_tick.get("post_signal_auto_resume"))
    unsafe_flags = [
        name for name in sorted(UNSAFE_FLAGS)
        if safety.get(name) not in {False, None}
    ]
    notification = watcher_tick.get("notification") if isinstance(watcher_tick, dict) else {}
    notification = notification if isinstance(notification, dict) else {}
    wakeup_status = str(watcher_tick.get("wakeup_status") or wakeup_packet.get("status") or "unknown")
    operator_status = str(watcher_tick.get("operator_status") or operator_packet.get("status") or "unknown")
    runtime_signal_summaries = _items(status_packet.get("runtime_signal_summaries"))
    selected_runtime_instance_ids = [
        str(item)
        for item in (status_packet.get("selected_runtime_instance_ids") or [])
        if str(item).strip()
    ]
    signal_input_json = status_packet.get("signal_input_json")
    prepared_authorization_id = status_packet.get("prepared_authorization_id")
    shadow_candidate_id = status_packet.get("shadow_candidate_id")
    actionable_runtime_signal = _has_actionable_runtime_signal(
        runtime_signal_summaries=runtime_signal_summaries,
        signal_input_json=signal_input_json,
        shadow_candidate_id=shadow_candidate_id,
        prepared_authorization_id=prepared_authorization_id,
    )
    normalized_ready_without_actionable_signal = (
        str(post_signal_auto_resume.get("status") or "")
        == NON_EXECUTING_PREPARE_STATUS
        and not actionable_runtime_signal
    )
    if normalized_ready_without_actionable_signal:
        post_signal_auto_resume = _waiting_for_market_auto_resume()
    action_time_resume = _action_time_resume(
        post_signal_auto_resume=post_signal_auto_resume,
        signal_input_json=signal_input_json,
        shadow_candidate_id=shadow_candidate_id,
        prepared_authorization_id=prepared_authorization_id,
        unsafe_flags=unsafe_flags,
        missing=missing,
    )
    owner_state = _owner_state(
        action_time_resume=action_time_resume,
        post_signal_auto_resume=post_signal_auto_resume,
    )
    can_resume_steps_5_8 = (
        wakeup_status in RESUME_READY_STATUSES
        and actionable_runtime_signal
        and not unsafe_flags
        and not missing
    )

    if missing:
        deployment_status = "evidence_missing"
    elif stale:
        deployment_status = "evidence_stale"
    elif unsafe_flags:
        deployment_status = "unsafe_watcher_effect_detected"
    elif notification.get("configured"):
        deployment_status = "ready"
    else:
        deployment_status = "notification_not_configured"

    resume_status = str(action_time_resume["status"])
    if missing or unsafe_flags:
        resume_status = "blocked"

    deployment_packet = {
        "scope": "runtime_signal_watcher_deployment_readiness",
        "label": label,
        "generated_at_ms": generated_at_ms,
        "status": deployment_status,
        "report_dir": str(report_dir),
        "files": files,
        "latest_evidence_age_seconds": age_seconds,
        "stale_after_seconds": stale_after_seconds,
        "notification": {
            "configured": bool(notification.get("configured")),
            "last_attempted": bool(notification.get("attempted")),
            "last_sent": bool(notification.get("sent")),
            "duplicate_suppression_observed": bool(notification_state.get("last_notified_event_key")),
        },
        "watcher_status": {
            "tick_status": watcher_tick.get("status") or "unknown",
            "wakeup_status": wakeup_status,
            "operator_status": operator_status,
            "status_packet_status": watcher_tick.get("status_packet_status") or status_packet.get("status") or "unknown",
        },
        "post_signal_auto_resume": post_signal_auto_resume,
        "post_signal_resume_normalization": {
            "actionable_runtime_signal": actionable_runtime_signal,
            "normalized_ready_status_without_actionable_signal": (
                normalized_ready_without_actionable_signal
            ),
        },
        "safety_invariants": {
            **{name: bool(safety.get(name)) for name in sorted(UNSAFE_FLAGS)},
            "forbidden_effect_flags": unsafe_flags,
            "pack_builder_only": True,
            "places_order": False,
            "mutates_pg": False,
            "sends_notification": False,
        },
        "blockers": missing + unsafe_flags,
    }

    resume_pack = {
        "scope": "runtime_signal_watcher_post_signal_resume_pack",
        "label": label,
        "generated_at_ms": generated_at_ms,
        "status": resume_status,
        "can_continue_steps_5_8": can_resume_steps_5_8,
        "current_wakeup_status": wakeup_status,
        "current_operator_status": operator_status,
        "current_status_packet_status": (
            watcher_tick.get("status_packet_status")
            or status_packet.get("status")
            or "unknown"
        ),
        "active_runtime_count": status_packet.get("active_runtime_count"),
        "monitored_runtime_count": status_packet.get("monitored_runtime_count"),
        "selected_runtime_instance_ids": selected_runtime_instance_ids,
        "runtime_signal_summaries": runtime_signal_summaries,
        "signal_input_json": signal_input_json,
        "prepared_authorization_id": prepared_authorization_id,
        "shadow_candidate_id": shadow_candidate_id,
        "prepared_evidence": {
            "signal_input_json": signal_input_json,
            "shadow_candidate_id": shadow_candidate_id,
            "prepared_authorization_id": prepared_authorization_id,
            "ready_for_action_time_final_gate": bool(prepared_authorization_id),
        },
        "action_time_resume": action_time_resume,
        "owner_state": owner_state,
        "post_signal_auto_resume": post_signal_auto_resume,
        "post_signal_resume_normalization": {
            "actionable_runtime_signal": actionable_runtime_signal,
            "normalized_ready_status_without_actionable_signal": (
                normalized_ready_without_actionable_signal
            ),
        },
        "automatic_recovery_action": post_signal_auto_resume.get(
            "automatic_recovery_action"
        ),
        "blocked_at": post_signal_auto_resume.get("blocked_at"),
        "blocked_reason": post_signal_auto_resume.get("blocked_reason"),
        "next_recover_condition": post_signal_auto_resume.get(
            "next_recover_condition"
        ),
        "downgrade_mode": post_signal_auto_resume.get("downgrade_mode"),
        "can_continue_without_owner_chat": post_signal_auto_resume.get(
            "can_continue_without_owner_chat"
        ),
        "requires_action_time_final_gate": post_signal_auto_resume.get(
            "requires_action_time_final_gate"
        ),
        "requires_official_operation_layer": post_signal_auto_resume.get(
            "requires_official_operation_layer"
        ),
        "source_paths": {name: str(path) for name, path in paths.items()},
        "required_before_real_submit": [
            "fresh candidate",
            "runtime grant",
            "fresh authorization evidence",
            "action-time FinalGate",
            "official Operation Layer gateway action",
            "post-submit finalize / reconciliation / budget settlement",
        ],
        "hard_stops": [
            "missing watcher evidence",
            "stale watcher evidence",
            "forbidden effect flag",
            "active position or open order blocker",
            "FinalGate failure",
            "Operation Layer bypass",
        ],
        "safety_invariants": deployment_packet["safety_invariants"],
        "blockers": deployment_packet["blockers"]
        + list(watcher_tick.get("blockers") or status_packet.get("blockers") or []),
        "warnings": list(
            watcher_tick.get("warnings") or status_packet.get("warnings") or []
        )
        + (
            ["normalized_ready_status_without_actionable_signal"]
            if normalized_ready_without_actionable_signal
            else []
        ),
    }

    deployment_path = output_dir / "deployment-readiness-packet.json"
    resume_path = output_dir / "post-signal-resume-pack.json"
    _write_json(deployment_path, deployment_packet)
    _write_json(resume_path, resume_pack)
    return {
        "scope": "runtime_signal_watcher_readiness_pack_builder",
        "status": "completed",
        "deployment_readiness_packet": str(deployment_path),
        "post_signal_resume_pack": str(resume_path),
        "deployment_status": deployment_status,
        "resume_status": resume_status,
        "can_continue_steps_5_8": can_resume_steps_5_8,
        "safety_invariants": {
            "places_order": False,
            "mutates_pg": False,
            "sends_notification": False,
        },
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build read-only Runtime Signal Watcher deployment and resume packs.",
    )
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--stale-after-seconds", type=int, default=180)
    parser.add_argument("--label", default="tokyo-runtime-signal-watcher")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    packet = build_pack(
        report_dir=Path(args.report_dir).expanduser(),
        output_dir=Path(args.output_dir).expanduser(),
        stale_after_seconds=args.stale_after_seconds,
        label=args.label,
    )
    print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
