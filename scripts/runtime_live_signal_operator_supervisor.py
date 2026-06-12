#!/usr/bin/env python3
"""Supervise repeated live-signal operator cycles for one runtime.

RTF-069 runs the RTF-067 operator cycle repeatedly:

waiting -> continue observation
profile proposal -> stop for Owner/Codex review
ready_for_prepare -> stop for operator review
ready_for_final_gate_preflight -> stop for FinalGate review

It does not submit orders, arm local registration, arm exchange submit, call
OrderLifecycle, write to exchange, mutate runtime budget, or move funds.
"""

from __future__ import annotations

import argparse
import asyncio
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

from scripts import runtime_live_signal_operator_cycle as cycle_script  # noqa: E402


CycleBuilder = Callable[[argparse.Namespace], Any]

WAITING_STATUS = cycle_script.WAITING_STATUS
READY_PROFILE_STATUS = cycle_script.READY_PROFILE_STATUS
READY_FOR_PREPARE_STATUS = cycle_script.READY_FOR_PREPARE_STATUS
READY_FOR_FINAL_GATE_PREFLIGHT = cycle_script.READY_FOR_FINAL_GATE_PREFLIGHT


async def build_supervisor_packet(
    args: argparse.Namespace,
    *,
    cycle_builder: CycleBuilder | None = None,
) -> dict[str, Any]:
    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    builder = cycle_builder or cycle_script._build_packet
    cycles: list[dict[str, Any]] = []
    stop_reason = "max_cycles_reached"
    blockers: list[str] = []

    for index in range(max(args.max_cycles, 1)):
        cycle_args = _cycle_args(args, output_dir=output_dir, cycle_index=index + 1)
        packet = await builder(cycle_args)
        cycle_path = output_dir / f"cycle-{index + 1:03d}.json"
        _write_json(cycle_path, packet)
        cycles.append(_cycle_summary(packet, cycle_path=cycle_path, cycle_index=index + 1))

        forbidden = _forbidden_effects(packet)
        if forbidden:
            blockers.extend(f"cycle_{index + 1}:{item}" for item in forbidden)
            stop_reason = "forbidden_effect_detected"
            break

        status = str(packet.get("status") or "")
        if status == WAITING_STATUS:
            if index + 1 < max(args.max_cycles, 1) and args.interval_seconds > 0:
                time.sleep(args.interval_seconds)
            continue
        if status in {
            READY_PROFILE_STATUS,
            READY_FOR_PREPARE_STATUS,
            READY_FOR_FINAL_GATE_PREFLIGHT,
        }:
            stop_reason = f"review_required:{status}"
            break
        blockers.append(f"unexpected_cycle_status:{status or 'missing'}")
        stop_reason = "unexpected_cycle_status"
        break

    status = _supervisor_status(stop_reason=stop_reason, blockers=blockers)
    packet = {
        "scope": "runtime_live_signal_operator_supervisor",
        "status": status,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "runtime_instance_id": args.runtime_instance_id,
        "output_dir": str(output_dir),
        "cycles_requested": max(args.max_cycles, 1),
        "cycles_completed": len(cycles),
        "stop_reason": stop_reason,
        "latest_cycle_status": cycles[-1]["status"] if cycles else None,
        "latest_cycle_path": cycles[-1]["cycle_path"] if cycles else None,
        "cycle_summaries": cycles,
        "blockers": _dedupe(blockers),
        "warnings": [],
        "operator_command_plan": {
            "next_step": _next_step(status=status, stop_reason=stop_reason),
            "allow_prepare_records": bool(args.allow_prepare_records),
            "continue_observation_allowed": status == "supervisor_waiting_for_signal",
            "requires_owner_runtime_profile_confirmation": (
                status == "supervisor_profile_review_required"
            ),
            "requires_prepare_review": status == "supervisor_prepare_review_required",
            "requires_final_gate_review": status == "supervisor_final_gate_review_required",
            "places_order": False,
            "calls_order_lifecycle": False,
            "executes_real_submit": False,
        },
        "safety_invariants": _supervisor_safety(
            allow_prepare_records=args.allow_prepare_records,
            cycles=cycles,
        ),
    }
    if args.output_json:
        _write_json(Path(args.output_json).expanduser(), packet)
    return packet


def _cycle_args(
    args: argparse.Namespace,
    *,
    output_dir: Path,
    cycle_index: int,
) -> argparse.Namespace:
    return argparse.Namespace(
        runtime_instance_id=args.runtime_instance_id,
        env_file=args.env_file,
        api_base=args.api_base,
        source=args.source,
        output_signal_input_json=str(output_dir / f"cycle-{cycle_index:03d}-signal-input.json"),
        capital_base=args.capital_base,
        signal_index=args.signal_index,
        allow_prepare_records=args.allow_prepare_records,
        candidate_id=args.candidate_id,
        context_id=args.context_id,
        owner_operator_id=args.owner_operator_id,
        owner_confirmation_reference=args.owner_confirmation_reference,
        reason=args.reason,
        next_attempt_symbol=args.next_attempt_symbol,
        next_attempt_side=args.next_attempt_side,
        next_attempt_family=args.next_attempt_family,
        next_attempt_strategy_family_id=args.next_attempt_strategy_family_id,
        next_attempt_carrier_id=args.next_attempt_carrier_id,
        output_json=None,
    )


def _cycle_summary(
    packet: dict[str, Any],
    *,
    cycle_path: Path,
    cycle_index: int,
) -> dict[str, Any]:
    plan = packet.get("operator_command_plan")
    if not isinstance(plan, dict):
        plan = {}
    safety = packet.get("safety_invariants")
    if not isinstance(safety, dict):
        safety = {}
    routing = packet.get("routing_packet")
    if not isinstance(routing, dict):
        routing = {}
    return {
        "cycle_index": cycle_index,
        "cycle_path": str(cycle_path),
        "status": packet.get("status"),
        "routing_status": routing.get("status"),
        "routing_source_selector_status": routing.get("source_selector_status"),
        "blockers": list(packet.get("blockers") or []),
        "signal_input_json": packet.get("signal_input_json"),
        "next_step": plan.get("next_step"),
        "prepared_authorization_id": plan.get("prepared_authorization_id"),
        "requires_owner_runtime_profile_confirmation": plan.get(
            "requires_owner_runtime_profile_confirmation"
        ),
        "requires_real_submit_gate": plan.get("requires_real_submit_gate"),
        "prepare_flow_called": bool(safety.get("prepare_flow_called")),
        "prepare_records_created": bool(safety.get("prepare_records_created")),
        "shadow_candidate_created": bool(safety.get("shadow_candidate_created")),
        "recorded_execution_intent_created": bool(
            safety.get("recorded_execution_intent_created")
        ),
        "submit_authorization_created": bool(safety.get("submit_authorization_created")),
        "forbidden_effects": _forbidden_effects(packet),
    }


def _forbidden_effects(packet: dict[str, Any]) -> list[str]:
    safety = packet.get("safety_invariants")
    if not isinstance(safety, dict):
        safety = {}
    effects: list[str] = []
    for key in (
        "runtime_created",
        "runtime_profile_mutated",
        "local_registration_armed",
        "exchange_submit_armed",
        "execute_real_submit",
        "exchange_write_called",
        "order_created",
        "order_lifecycle_called",
        "attempt_counter_mutated",
        "runtime_budget_mutated",
        "position_opened",
        "position_closed",
        "withdrawal_or_transfer_created",
    ):
        if safety.get(key) is True:
            effects.append(key)
    return effects


def _supervisor_status(*, stop_reason: str, blockers: list[str]) -> str:
    if blockers:
        return "supervisor_blocked"
    if stop_reason == "max_cycles_reached":
        return "supervisor_waiting_for_signal"
    if stop_reason == f"review_required:{READY_PROFILE_STATUS}":
        return "supervisor_profile_review_required"
    if stop_reason == f"review_required:{READY_FOR_PREPARE_STATUS}":
        return "supervisor_prepare_review_required"
    if stop_reason == f"review_required:{READY_FOR_FINAL_GATE_PREFLIGHT}":
        return "supervisor_final_gate_review_required"
    return "supervisor_blocked"


def _next_step(*, status: str, stop_reason: str) -> str:
    if status == "supervisor_waiting_for_signal":
        return "continue_live_signal_operator_supervision"
    if status == "supervisor_profile_review_required":
        return "owner_codex_review_runtime_profile_proposal"
    if status == "supervisor_prepare_review_required":
        return "review_ready_signal_then_rerun_with_allow_prepare_records"
    if status == "supervisor_final_gate_review_required":
        return "run_official_final_gate_preview_before_any_submit"
    if stop_reason == "forbidden_effect_detected":
        return "stop_and_review_forbidden_effect"
    return "resolve_operator_supervisor_blocker"


def _supervisor_safety(
    *,
    allow_prepare_records: bool,
    cycles: list[dict[str, Any]],
) -> dict[str, bool]:
    return {
        "runtime_live_signal_operator_supervisor": True,
        "allow_prepare_records": bool(allow_prepare_records),
        "cycles_have_forbidden_effects": any(
            bool(cycle.get("forbidden_effects")) for cycle in cycles
        ),
        "prepare_flow_called": any(bool(cycle.get("prepare_flow_called")) for cycle in cycles),
        "prepare_records_created": any(
            bool(cycle.get("prepare_records_created")) for cycle in cycles
        ),
        "shadow_candidate_created": any(
            bool(cycle.get("shadow_candidate_created")) for cycle in cycles
        ),
        "recorded_execution_intent_created": any(
            bool(cycle.get("recorded_execution_intent_created")) for cycle in cycles
        ),
        "submit_authorization_created": any(
            bool(cycle.get("submit_authorization_created")) for cycle in cycles
        ),
        "places_order": False,
        "calls_order_lifecycle": False,
        "executes_real_submit": False,
        "exchange_write_called": False,
        "runtime_budget_mutated": False,
        "position_opened": False,
        "position_closed": False,
        "withdrawal_or_transfer_created": False,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = str(item).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Supervise repeated live signal operator cycles without submit authority.",
    )
    parser.add_argument("--runtime-instance-id", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--output-json")
    parser.add_argument("--env-file")
    parser.add_argument("--api-base")
    parser.add_argument(
        "--source",
        choices=["sample", "local_sqlite_fallback", "live_market"],
        default="live_market",
    )
    parser.add_argument("--capital-base", default="30")
    parser.add_argument("--signal-index", type=int, default=0)
    parser.add_argument("--max-cycles", type=int, default=3)
    parser.add_argument("--interval-seconds", type=float, default=0.0)
    parser.add_argument("--allow-prepare-records", action="store_true")
    parser.add_argument("--candidate-id")
    parser.add_argument("--context-id")
    parser.add_argument("--owner-operator-id", default="owner")
    parser.add_argument(
        "--owner-confirmation-reference",
        default="owner-authorized-live-signal-operator-supervisor",
    )
    parser.add_argument(
        "--reason",
        default="owner reviewed live signal operator supervisor",
    )
    parser.add_argument("--next-attempt-symbol")
    parser.add_argument("--next-attempt-side")
    parser.add_argument("--next-attempt-family")
    parser.add_argument("--next-attempt-strategy-family-id")
    parser.add_argument("--next-attempt-carrier-id")
    return parser.parse_args(argv)


def _main(
    argv: list[str] | None = None,
    *,
    cycle_builder: CycleBuilder | None = None,
) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    with redirect_stdout(sys.stderr):
        packet = asyncio.run(build_supervisor_packet(args, cycle_builder=cycle_builder))
    print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if packet["status"] in {
        "supervisor_waiting_for_signal",
        "supervisor_profile_review_required",
        "supervisor_prepare_review_required",
        "supervisor_final_gate_review_required",
    } else 2


def main(argv: list[str] | None = None) -> int:
    return _main(argv)


def main_with_builder_for_test(cycle_builder: CycleBuilder) -> int:
    return _main(cycle_builder=cycle_builder)


if __name__ == "__main__":
    raise SystemExit(main())
