#!/usr/bin/env python3
"""Run bounded active-runtime observation cycles without live submit.

This loop is the durable version of the overnight operator wrapper: it invokes
``runtime_active_observation_monitor`` repeatedly, writes one auditable packet
per cycle, updates a latest summary, and stops as soon as a runtime leaves the
plain waiting-for-signal state.
"""

from __future__ import annotations

import argparse
import copy
from contextlib import redirect_stdout
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from typing import Any, Callable

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import runtime_active_observation_monitor as active_monitor  # noqa: E402


WAITING_STATUS = "waiting_for_signal"
STOP_STATUSES = {
    "ready_for_prepare",
    "ready_for_final_gate_preflight",
    "blocked",
    "mixed",
    "no_active_runtimes",
}


def _utc_cycle_name(*, iteration: int) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-iter-{iteration:03d}"


def _summary(packet: dict[str, Any], *, iteration: int, cycle_dir: Path) -> dict[str, Any]:
    safety = packet.get("safety_invariants")
    if not isinstance(safety, dict):
        safety = {}
    plan = packet.get("operator_command_plan")
    if not isinstance(plan, dict):
        plan = {}
    return {
        "iteration": iteration,
        "cycle_dir": str(cycle_dir),
        "status": str(packet.get("status") or "unknown"),
        "active_runtime_count": packet.get("active_runtime_count"),
        "monitored_runtime_count": packet.get("monitored_runtime_count"),
        "prepare_records_created": bool(safety.get("prepare_records_created")),
        "ready_for_final_gate_preflight": (
            packet.get("status") == "ready_for_final_gate_preflight"
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
        "blockers": list(packet.get("blockers") or []),
        "warnings": list(packet.get("warnings") or []),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _build_loop_packet(
    args: argparse.Namespace,
    *,
    packet_builder: Callable[[argparse.Namespace], dict[str, Any]] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    cycle_name_builder: Callable[[int], str] | None = None,
) -> dict[str, Any]:
    builder = packet_builder or active_monitor._build_packet
    cycle_name = cycle_name_builder or (lambda iteration: _utc_cycle_name(iteration=iteration))
    max_iterations = max(int(args.max_iterations or 1), 1)
    root = Path(args.output_dir).expanduser()
    summaries: list[dict[str, Any]] = []
    packets: list[dict[str, Any]] = []

    final_status = "not_started"
    stop_reason = "max_iterations_exhausted"
    for iteration in range(1, max_iterations + 1):
        cycle_dir = root / cycle_name(iteration)
        cycle_args = copy.copy(args.monitor_args)
        cycle_args.output_dir = str(cycle_dir)
        cycle_args.output_json = str(cycle_dir / "active-monitor.json")

        packet = builder(cycle_args)
        status = str(packet.get("status") or "unknown")
        summary = _summary(packet, iteration=iteration, cycle_dir=cycle_dir)
        _write_json(cycle_dir / "active-monitor.json", packet)
        _write_json(cycle_dir / "summary.json", summary)
        _write_json(root / "latest-summary.json", summary)
        (root / "latest-status.txt").write_text(status + "\n", encoding="utf-8")

        summaries.append(summary)
        if args.include_packets:
            packets.append(packet)

        final_status = status
        if status in STOP_STATUSES or status != WAITING_STATUS:
            stop_reason = f"status_changed:{status}"
            break
        if iteration < max_iterations:
            sleeper(float(args.loop_interval_seconds or 0))

    return {
        "scope": "runtime_active_observation_loop",
        "status": final_status,
        "stop_reason": stop_reason,
        "iterations_requested": max_iterations,
        "iterations_completed": len(summaries),
        "loop_interval_seconds": float(args.loop_interval_seconds or 0),
        "output_dir": str(root),
        "latest_summary": summaries[-1] if summaries else {},
        "cycle_summaries": summaries,
        "cycle_packets": packets,
        "operator_command_plan": {
            "not_executed": True,
            "next_step": _next_step(final_status),
            "creates_execution_intent": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "requires_operator_review_after_non_waiting_status": (
                final_status != WAITING_STATUS
            ),
        },
        "safety_invariants": _loop_safety(summaries),
    }


def _loop_safety(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    def any_flag(name: str) -> bool:
        return any(bool(summary.get(name)) for summary in summaries)

    return {
        "monitor_loop_only": True,
        "prepare_records_created": any_flag("prepare_records_created"),
        "creates_execution_intent": any_flag("creates_execution_intent"),
        "places_order": any_flag("places_order"),
        "calls_order_lifecycle": any_flag("calls_order_lifecycle"),
        "exchange_write_called": any_flag("exchange_write_called"),
        "order_created": any_flag("order_created"),
        "order_lifecycle_called": any_flag("order_lifecycle_called"),
        "attempt_counter_mutated": any_flag("attempt_counter_mutated"),
        "runtime_budget_mutated": any_flag("runtime_budget_mutated"),
        "withdrawal_or_transfer_created": any_flag(
            "withdrawal_or_transfer_created"
        ),
    }


def _next_step(status: str) -> str:
    if status == "ready_for_final_gate_preflight":
        return "review_prepared_records_then_run_final_gate_preview"
    if status == "ready_for_prepare":
        return "review_ready_signal_then_rerun_with_prepare_records_enabled"
    if status == "blocked":
        return "resolve_active_observation_loop_blocker"
    if status == "no_active_runtimes":
        return "start_or_authorize_runtime_before_looping"
    return "continue_waiting_for_strategy_signal"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    loop_parser = argparse.ArgumentParser(
        description="Run bounded ACTIVE runtime observation monitor cycles.",
        add_help=False,
    )
    loop_parser.add_argument("--max-iterations", type=int, default=1)
    loop_parser.add_argument("--loop-interval-seconds", type=float, default=0.0)
    loop_parser.add_argument(
        "--loop-output-json",
        help="Optional path for the aggregate loop packet. Stdout remains JSON.",
    )
    loop_parser.add_argument("--include-packets", action="store_true", default=False)
    loop_args, monitor_argv = loop_parser.parse_known_args(argv)
    monitor_args = active_monitor._parse_args(monitor_argv)
    return argparse.Namespace(
        max_iterations=loop_args.max_iterations,
        loop_interval_seconds=loop_args.loop_interval_seconds,
        loop_output_json=loop_args.loop_output_json,
        include_packets=loop_args.include_packets,
        output_dir=monitor_args.output_dir,
        monitor_args=monitor_args,
    )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    with redirect_stdout(sys.stderr):
        packet = _build_loop_packet(args)
    output = json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    if args.loop_output_json:
        _write_json(Path(args.loop_output_json).expanduser(), packet)
    print(output)
    return 0 if packet["status"] in {
        "waiting_for_signal",
        "ready_for_prepare",
        "ready_for_final_gate_preflight",
        "no_active_runtimes",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
