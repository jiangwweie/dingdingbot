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
    unsafe_flags = [
        name for name in sorted(UNSAFE_FLAGS)
        if safety.get(name) not in {False, None}
    ]
    notification = watcher_tick.get("notification") if isinstance(watcher_tick, dict) else {}
    notification = notification if isinstance(notification, dict) else {}
    wakeup_status = str(watcher_tick.get("wakeup_status") or wakeup_packet.get("status") or "unknown")
    operator_status = str(watcher_tick.get("operator_status") or operator_packet.get("status") or "unknown")
    can_resume_steps_5_8 = wakeup_status in RESUME_READY_STATUSES and not unsafe_flags and not missing

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

    resume_status = "ready_for_steps_5_8" if can_resume_steps_5_8 else "waiting_for_fresh_signal"
    if wakeup_status == "operator_packet_needs_review":
        resume_status = "operator_packet_needs_review"
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
        "warnings": list(watcher_tick.get("warnings") or status_packet.get("warnings") or []),
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
