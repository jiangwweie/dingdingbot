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
import signal
import sys
import time
from typing import Any, Callable

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import runtime_active_observation_monitor as active_monitor  # noqa: E402
from scripts.runtime_active_observation_status import build_status_packet  # noqa: E402


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
        "selected_runtime_instance_ids": list(
            packet.get("selected_runtime_instance_ids") or []
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
        "signal_input_json": _signal_input_json(packet),
        "prepared_authorization_id": _prepared_authorization_id(packet),
        "runtime_signal_summaries": _runtime_signal_summaries(packet),
    }


def _signal_input_json(packet: dict[str, Any]) -> str | None:
    for candidate in (
        packet.get("signal_input_json"),
        _nested_get(packet, ("operator_command_plan", "signal_input_json")),
        _nested_get(packet, ("latest_packet", "signal_input_json")),
        _nested_get(packet, ("latest_packet", "operator_command_plan", "signal_input_json")),
    ):
        text = str(candidate or "").strip()
        if text:
            return text

    for item in packet.get("runtime_summaries") or []:
        if not isinstance(item, dict):
            continue
        for candidate in (
            item.get("signal_input_json"),
            _nested_get(item, ("operator_command_plan", "signal_input_json")),
            _nested_get(item, ("latest_packet", "signal_input_json")),
            _nested_get(item, ("latest_packet", "operator_command_plan", "signal_input_json")),
        ):
            text = str(candidate or "").strip()
            if text:
                return text
    return None


def _prepared_authorization_id(packet: dict[str, Any]) -> str | None:
    plan = packet.get("operator_command_plan")
    if isinstance(plan, dict):
        text = str(plan.get("prepared_authorization_id") or "").strip()
        if text:
            return text

    for item in packet.get("runtime_summaries") or []:
        if not isinstance(item, dict):
            continue
        for candidate in (
            item.get("prepared_authorization_id"),
            _nested_get(item, ("operator_command_plan", "prepared_authorization_id")),
            _nested_get(item, ("latest_packet", "operator_command_plan", "prepared_authorization_id")),
            _nested_get(item, ("latest_packet", "prepare_packet", "operator_command_plan", "prepared_authorization_id")),
            _nested_get(item, ("latest_packet", "prepare_packet", "ids", "authorization_id")),
            _nested_get(item, ("latest_packet", "prepare_packet", "first_real_submit_prepare_report", "ids", "authorization_id")),
        ):
            text = str(candidate or "").strip()
            if text:
                return text
    return None


def _nested_get(value: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = value
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _runtime_signal_summaries(packet: dict[str, Any]) -> list[dict[str, Any]]:
    summaries = packet.get("runtime_summaries")
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

        try:
            packet = _build_cycle_packet_with_timeout(
                builder,
                cycle_args,
                timeout_seconds=float(getattr(args, "cycle_timeout_seconds", 0) or 0),
            )
        except RuntimeError as exc:
            packet = _blocked_cycle_packet(
                reason=str(exc),
                output_json=str(cycle_dir / "active-monitor.json"),
            )
        except Exception as exc:
            packet = _blocked_cycle_packet(
                reason=_cycle_failure_reason(exc),
                output_json=str(cycle_dir / "active-monitor.json"),
            )
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
        should_stop = status in STOP_STATUSES or status != WAITING_STATUS
        if should_stop:
            stop_reason = f"status_changed:{status}"

        if args.loop_output_json:
            interim_stop_reason = stop_reason
            if not should_stop and iteration < max_iterations:
                interim_stop_reason = "running"
            _write_loop_and_status_packets(
                args,
                root=root,
                summaries=summaries,
                packets=packets,
                final_status=final_status,
                stop_reason=interim_stop_reason,
                max_iterations=max_iterations,
            )

        if should_stop:
            break
        if iteration < max_iterations:
            sleeper(float(args.loop_interval_seconds or 0))

    return _loop_packet(
        args,
        root=root,
        summaries=summaries,
        packets=packets,
        final_status=final_status,
        stop_reason=stop_reason,
        max_iterations=max_iterations,
    )


def _write_loop_and_status_packets(
    args: argparse.Namespace,
    *,
    root: Path,
    summaries: list[dict[str, Any]],
    packets: list[dict[str, Any]],
    final_status: str,
    stop_reason: str,
    max_iterations: int,
) -> None:
    _write_json(
        Path(args.loop_output_json).expanduser(),
        _loop_packet(
            args,
            root=root,
            summaries=summaries,
            packets=packets,
            final_status=final_status,
            stop_reason=stop_reason,
            max_iterations=max_iterations,
        ),
    )
    if getattr(args, "status_output_json", None):
        status_packet = build_status_packet(
            root,
            stale_after_seconds=float(
                getattr(args, "status_stale_after_seconds", 900.0) or 900.0
            ),
        )
        _write_json(Path(args.status_output_json).expanduser(), status_packet)


def _build_cycle_packet_with_timeout(
    builder: Callable[[argparse.Namespace], dict[str, Any]],
    cycle_args: argparse.Namespace,
    *,
    timeout_seconds: float,
) -> dict[str, Any]:
    if (
        timeout_seconds <= 0
        or not hasattr(signal, "SIGALRM")
        or not hasattr(signal, "setitimer")
    ):
        return builder(cycle_args)

    def _raise_timeout(signum: int, frame: Any) -> None:
        raise TimeoutError("active_observation_cycle_timeout")

    previous_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, _raise_timeout)
    previous_timer = signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
    try:
        return builder(cycle_args)
    except TimeoutError as exc:
        raise RuntimeError(
            f"active_observation_cycle_timeout:{timeout_seconds:g}s"
        ) from exc
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0] > 0:
            signal.setitimer(signal.ITIMER_REAL, *previous_timer)


def _blocked_cycle_packet(*, reason: str, output_json: str) -> dict[str, Any]:
    return {
        "scope": "runtime_active_observation_monitor",
        "status": "blocked",
        "active_runtime_count": None,
        "monitored_runtime_count": 0,
        "runtime_summaries": [],
        "runtime_packets": [],
        "blockers": [reason],
        "warnings": [],
        "output_json": output_json,
        "operator_command_plan": {
            "next_step": "inspect_active_observation_cycle_timeout",
            "not_executed": True,
            "creates_shadow_candidate": False,
            "creates_execution_intent": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "requires_official_final_gate": True,
            "uses_standing_runtime_authorization": True,
            "requires_explicit_owner_real_submit_authorization": False,
            "requires_official_operation_layer": True,
        },
        "safety_invariants": {
            "uses_official_trading_console_api": True,
            "monitors_active_runtimes": True,
            "prepare_records_created": False,
            "shadow_candidate_created": False,
            "runtime_execution_intent_draft_created": False,
            "recorded_execution_intent_created": False,
            "submit_authorization_created": False,
            "protection_plan_created": False,
            "executable_execution_intent_created": False,
            "local_registration_armed": False,
            "exchange_submit_armed": False,
            "execute_real_submit": False,
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "attempt_counter_mutated": False,
            "runtime_budget_mutated": False,
            "position_opened": False,
            "position_closed": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _cycle_failure_reason(exc: Exception) -> str:
    message = str(exc).replace("\n", " ").strip()
    if len(message) > 240:
        message = message[:237] + "..."
    return f"active_observation_cycle_failed:{type(exc).__name__}:{message}"


def _loop_packet(
    args: argparse.Namespace,
    *,
    root: Path,
    summaries: list[dict[str, Any]],
    packets: list[dict[str, Any]],
    final_status: str,
    stop_reason: str,
    max_iterations: int,
) -> dict[str, Any]:
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
        "shadow_candidate_created": any_flag("shadow_candidate_created"),
        "runtime_execution_intent_draft_created": any_flag(
            "runtime_execution_intent_draft_created"
        ),
        "recorded_execution_intent_created": any_flag(
            "recorded_execution_intent_created"
        ),
        "submit_authorization_created": any_flag("submit_authorization_created"),
        "protection_plan_created": any_flag("protection_plan_created"),
        "executable_execution_intent_created": any_flag(
            "executable_execution_intent_created"
        ),
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
    loop_parser.add_argument("--cycle-timeout-seconds", type=float, default=180.0)
    loop_parser.add_argument(
        "--loop-output-json",
        help="Optional path for the aggregate loop packet. Stdout remains JSON.",
    )
    loop_parser.add_argument(
        "--status-output-json",
        help="Optional path for a refreshed read-only status packet.",
    )
    loop_parser.add_argument("--status-stale-after-seconds", type=float, default=900.0)
    loop_parser.add_argument("--include-packets", action="store_true", default=False)
    loop_args, monitor_argv = loop_parser.parse_known_args(argv)
    monitor_args = active_monitor._parse_args(monitor_argv)
    return argparse.Namespace(
        max_iterations=loop_args.max_iterations,
        loop_interval_seconds=loop_args.loop_interval_seconds,
        cycle_timeout_seconds=loop_args.cycle_timeout_seconds,
        loop_output_json=loop_args.loop_output_json,
        status_output_json=loop_args.status_output_json,
        status_stale_after_seconds=loop_args.status_stale_after_seconds,
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
