#!/usr/bin/env python3
"""Summarize active runtime observation packets without side effects."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any


PACKET_NAMES = (
    "supervisor-packet.json",
    "loop-packet.json",
    "followup-packet.json",
    "latest-summary.json",
)

FORBIDDEN_SAFETY_FLAGS = (
    "exchange_write_called",
    "exchange_called",
    "exchange_order_submitted",
    "order_created",
    "order_lifecycle_called",
    "order_lifecycle_submit_called",
    "executable_execution_intent_created",
    "real_submit_requested",
    "exchange_order_requested",
    "attempt_counter_mutated",
    "runtime_budget_mutated",
    "withdrawal_or_transfer_created",
    "withdrawal_or_transfer_requested",
    "withdrawal_instruction_created",
    "transfer_instruction_created",
)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists() or path.stat().st_size == 0:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _packet_mtime_ms(path: Path) -> int | None:
    if not path.exists():
        return None
    return int(path.stat().st_mtime * 1000)


def _latest_packet_path(root: Path) -> Path | None:
    existing = [root / name for name in PACKET_NAMES if (root / name).exists()]
    if not existing:
        return None
    return max(existing, key=lambda path: path.stat().st_mtime)


def _collect_forbidden_effects(*packets: dict[str, Any] | None) -> list[str]:
    effects: list[str] = []
    for packet_name, packet in zip(PACKET_NAMES, packets, strict=False):
        if not packet:
            continue
        safety = packet.get("safety_invariants")
        if not isinstance(safety, dict):
            continue
        for flag in FORBIDDEN_SAFETY_FLAGS:
            if bool(safety.get(flag)):
                effects.append(f"{packet_name}:{flag}")
        for effect in safety.get("forbidden_effects") or []:
            effects.append(f"{packet_name}:{effect}")
        for effect in safety.get("loop_forbidden_effects") or []:
            effects.append(f"{packet_name}:loop:{effect}")
        for effect in safety.get("arm_preview_forbidden_effects") or []:
            effects.append(f"{packet_name}:arm_preview:{effect}")
        for effect in safety.get("disabled_smoke_forbidden_effects") or []:
            effects.append(f"{packet_name}:disabled_smoke:{effect}")
    return effects


def _runtime_signal_summaries(summary: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not summary:
        return []
    rows = summary.get("runtime_signal_summaries")
    if not isinstance(rows, list):
        return []
    result: list[dict[str, Any]] = []
    for row in rows:
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
                "evaluation_status": signal.get("evaluation_status"),
                "signal_type": signal.get("signal_type"),
                "signal_side": signal.get("side"),
                "confidence": signal.get("confidence"),
                "reason_codes": signal.get("reason_codes") or [],
                "human_summary": signal.get("human_summary"),
            }
        )
    return result


def build_status_packet(
    output_dir: str | Path,
    *,
    stale_after_seconds: float = 900.0,
    now_ms: int | None = None,
) -> dict[str, Any]:
    root = Path(output_dir).expanduser()
    now_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)

    supervisor_path = root / "supervisor-packet.json"
    loop_path = root / "loop-packet.json"
    followup_path = root / "followup-packet.json"
    latest_summary_path = root / "latest-summary.json"

    supervisor = _read_json(supervisor_path)
    loop = _read_json(loop_path)
    followup = _read_json(followup_path)
    latest_summary = _read_json(latest_summary_path)
    if latest_summary is None and isinstance(loop, dict):
        maybe_summary = loop.get("latest_summary")
        latest_summary = maybe_summary if isinstance(maybe_summary, dict) else None

    latest_path = _latest_packet_path(root)
    latest_mtime_ms = _packet_mtime_ms(latest_path) if latest_path else None
    latest_age_seconds = (
        max((now_ms - latest_mtime_ms) / 1000, 0)
        if latest_mtime_ms is not None
        else None
    )
    packet_stale = (
        latest_age_seconds is None or latest_age_seconds > float(stale_after_seconds)
    )

    latest_status = None
    for packet in (followup, loop, latest_summary, supervisor):
        if isinstance(packet, dict) and packet.get("status"):
            latest_status = packet.get("status")
            break

    forbidden_effects = _collect_forbidden_effects(
        supervisor,
        loop,
        followup,
        latest_summary,
    )
    blockers: list[str] = []
    warnings: list[str] = []
    for packet in (supervisor, loop, followup, latest_summary):
        if not isinstance(packet, dict):
            continue
        blockers.extend(str(item) for item in packet.get("blockers") or [])
        warnings.extend(str(item) for item in packet.get("warnings") or [])
    if packet_stale:
        blockers.append("active_observation_packets_stale_or_missing")
    if forbidden_effects:
        blockers.append("active_observation_forbidden_effects_detected")

    status = "ok"
    if forbidden_effects:
        status = "blocked_forbidden_effect"
    elif packet_stale:
        status = "stale"
    elif latest_status in {"blocked", "disabled_smoke_blocked", "supervisor_blocked"}:
        status = "blocked"
    elif latest_status in {
        "ready_for_prepare",
        "ready_for_prepare_records",
        "ready_for_final_gate_preflight",
        "ready_for_disabled_smoke",
        "disabled_smoke_completed",
    }:
        status = "attention"
    elif (
        latest_status == "waiting_for_signal"
        and isinstance(loop, dict)
        and loop.get("stop_reason") == "max_iterations_exhausted"
    ):
        status = "observation_window_complete_no_signal"
    elif latest_status == "waiting_for_signal":
        status = "waiting_for_signal"

    latest_summary_operator_plan = (
        latest_summary.get("operator_command_plan")
        if isinstance(latest_summary, dict)
        else None
    )
    loop_operator_plan = loop.get("operator_command_plan") if isinstance(loop, dict) else None
    followup_operator_plan = (
        followup.get("operator_command_plan") if isinstance(followup, dict) else None
    )

    iterations_requested = (
        loop.get("iterations_requested") if isinstance(loop, dict) else None
    )
    iterations_completed = (
        loop.get("iterations_completed") if isinstance(loop, dict) else None
    )
    iterations_remaining = None
    if iterations_requested is not None and iterations_completed is not None:
        iterations_remaining = max(
            int(iterations_requested) - int(iterations_completed),
            0,
        )
    stop_reason = loop.get("stop_reason") if isinstance(loop, dict) else None

    return {
        "scope": "runtime_active_observation_status",
        "status": status,
        "output_dir": str(root),
        "latest_status": latest_status,
        "latest_packet": str(latest_path) if latest_path else None,
        "latest_packet_age_seconds": latest_age_seconds,
        "stale_after_seconds": float(stale_after_seconds),
        "packet_stale": packet_stale,
        "supervisor_status": supervisor.get("status") if isinstance(supervisor, dict) else None,
        "loop_status": loop.get("status") if isinstance(loop, dict) else None,
        "followup_status": followup.get("status") if isinstance(followup, dict) else None,
        "iterations_requested": iterations_requested,
        "iterations_completed": iterations_completed,
        "iterations_remaining": iterations_remaining,
        "latest_iteration": (
            latest_summary.get("iteration")
            if isinstance(latest_summary, dict)
            else None
        ),
        "stop_reason": stop_reason,
        "observation_running": stop_reason == "running",
        "observation_window_complete": stop_reason == "max_iterations_exhausted",
        "active_runtime_count": (
            latest_summary.get("active_runtime_count")
            if isinstance(latest_summary, dict)
            else None
        ),
        "prepared_authorization_id": (
            latest_summary.get("prepared_authorization_id")
            if isinstance(latest_summary, dict)
            else None
        ),
        "shadow_candidate_id": (
            latest_summary.get("shadow_candidate_id")
            if isinstance(latest_summary, dict)
            else None
        ),
        "runtime_signal_summaries": _runtime_signal_summaries(latest_summary),
        "blockers": blockers,
        "warnings": warnings,
        "forbidden_effects": forbidden_effects,
        "operator_command_plan": {
            "not_executed": True,
            "latest_summary_next_step": (
                latest_summary_operator_plan or {}
            ).get("next_step"),
            "loop_next_step": (loop_operator_plan or {}).get("next_step"),
            "followup_next_step": (followup_operator_plan or {}).get("next_step"),
            "observation_next_step": _observation_next_step(
                status=status,
                stop_reason=stop_reason,
            ),
            "creates_execution_intent": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "withdrawal_or_transfer_requested": False,
        },
        "safety_invariants": {
            "read_packets_only": True,
            "connects_to_api": False,
            "connects_to_exchange": False,
            "creates_prepare_records": False,
            "creates_shadow_candidate": False,
            "creates_execution_intent": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "mutates_runtime_budget": False,
            "mutates_attempt_counter": False,
            "withdrawal_or_transfer_created": False,
            "forbidden_effects": forbidden_effects,
        },
    }


def _observation_next_step(*, status: str, stop_reason: str | None) -> str:
    if status == "observation_window_complete_no_signal":
        return "review_no_signal_window_or_start_new_observation"
    if stop_reason == "running":
        return "continue_active_observation_loop"
    if status == "attention":
        return "review_non_executing_prepare_or_preview_packet"
    if status.startswith("blocked"):
        return "resolve_active_observation_status_blocker"
    if status == "stale":
        return "refresh_or_restart_active_observation_status"
    return "review_active_observation_status"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize runtime active observation packet state."
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--output-json")
    parser.add_argument("--stale-after-seconds", type=float, default=900.0)
    args = parser.parse_args()

    packet = build_status_packet(
        args.output_dir,
        stale_after_seconds=args.stale_after_seconds,
    )
    payload = json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output_json:
        path = Path(args.output_json).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
