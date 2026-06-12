#!/usr/bin/env python3
"""Build an Owner/operator-readable summary from a supervisor packet.

RTF-071 consumes the RTF-069/070 live signal operator supervisor JSON and
summarizes why the runtime is waiting, blocked, or ready for a review gate. It
is a read-only reporting helper: it does not read exchange state, write PG,
create prepare records, submit orders, call OrderLifecycle, mutate runtime
budget, or move funds.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any


GOOD_SOURCE_STATUSES = {
    "supervisor_waiting_for_signal",
    "supervisor_profile_review_required",
    "supervisor_prepare_review_required",
    "supervisor_final_gate_review_required",
}

FORBIDDEN_EFFECT_KEYS = (
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
)


def build_summary(supervisor_packet: dict[str, Any]) -> dict[str, Any]:
    cycles = _as_list(supervisor_packet.get("cycle_summaries"))
    raw_blockers = [
        *[str(item) for item in _as_list(supervisor_packet.get("blockers"))],
        *_cycle_blockers(cycles),
    ]
    blockers = _dedupe(raw_blockers)
    forbidden_effects = _aggregate_forbidden_effects(supervisor_packet, cycles)
    status = _summary_status(
        supervisor_packet=supervisor_packet,
        blockers=blockers,
        forbidden_effects=forbidden_effects,
    )
    latest_cycle = cycles[-1] if cycles and isinstance(cycles[-1], dict) else {}
    source_status = str(supervisor_packet.get("status") or "")

    return {
        "scope": "runtime_supervisor_operator_summary",
        "status": status,
        "source_supervisor_status": source_status,
        "runtime_instance_id": supervisor_packet.get("runtime_instance_id"),
        "cycles_completed": supervisor_packet.get("cycles_completed", len(cycles)),
        "stop_reason": supervisor_packet.get("stop_reason"),
        "latest_cycle_status": supervisor_packet.get("latest_cycle_status")
        or latest_cycle.get("status"),
        "latest_cycle_path": supervisor_packet.get("latest_cycle_path")
        or latest_cycle.get("cycle_path"),
        "signal_state": _signal_state(cycles=cycles, blockers=raw_blockers),
        "blockers": blockers,
        "warnings": _dedupe([str(item) for item in _as_list(supervisor_packet.get("warnings"))]),
        "operator_command_plan": _operator_command_plan(status=status),
        "safety_invariants": _summary_safety(
            supervisor_packet=supervisor_packet,
            forbidden_effects=forbidden_effects,
        ),
        "right_tail_objective_context": {
            "no_signal_is_not_failure": status == "operator_waiting_for_signal",
            "forcing_entry_without_signal_forbidden": True,
            "small_bounded_losses_allowed_when_signal_ready": True,
            "owner_manual_withdrawal_only": True,
            "automatic_withdrawal_assumed": False,
            "automatic_compounding_assumed": False,
        },
    }


def _summary_status(
    *,
    supervisor_packet: dict[str, Any],
    blockers: list[str],
    forbidden_effects: list[str],
) -> str:
    source_status = str(supervisor_packet.get("status") or "")
    if forbidden_effects or source_status == "supervisor_blocked":
        return "operator_supervisor_blocked"
    if source_status == "supervisor_waiting_for_signal":
        return "operator_waiting_for_signal"
    if source_status == "supervisor_profile_review_required":
        return "operator_profile_review_required"
    if source_status == "supervisor_prepare_review_required":
        return "operator_prepare_review_required"
    if source_status == "supervisor_final_gate_review_required":
        return "operator_final_gate_review_required"
    if blockers:
        return "operator_supervisor_blocked"
    return "operator_summary_needs_review"


def _signal_state(*, cycles: list[Any], blockers: list[str]) -> dict[str, Any]:
    selector_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    blocker_counts: Counter[str] = Counter(blockers)
    for cycle in cycles:
        if not isinstance(cycle, dict):
            continue
        selector = str(cycle.get("routing_source_selector_status") or "missing")
        selector_counts[selector] += 1
        status_counts[str(cycle.get("status") or "missing")] += 1
    no_signal_window = bool(cycles) and all(
        isinstance(cycle, dict)
        and cycle.get("status") == "waiting_for_runtime_compatible_signal"
        and cycle.get("routing_source_selector_status") == "no_would_enter_signal_available"
        for cycle in cycles
    )
    return {
        "no_signal_window": no_signal_window,
        "cycle_status_counts": dict(sorted(status_counts.items())),
        "selector_status_counts": dict(sorted(selector_counts.items())),
        "blocker_counts": dict(sorted(blocker_counts.items())),
    }


def _operator_command_plan(*, status: str) -> dict[str, Any]:
    next_step_by_status = {
        "operator_waiting_for_signal": "continue_live_signal_operator_supervision",
        "operator_profile_review_required": "review_runtime_profile_proposal",
        "operator_prepare_review_required": "review_ready_signal_then_rerun_with_allow_prepare_records",
        "operator_final_gate_review_required": "run_official_final_gate_preview_before_any_submit",
        "operator_supervisor_blocked": "stop_and_review_supervisor_blocker",
    }
    return {
        "next_step": next_step_by_status.get(status, "review_operator_summary"),
        "summary_only": True,
        "not_executed": True,
        "creates_runtime": False,
        "mutates_runtime_profile": False,
        "creates_shadow_candidate": False,
        "creates_execution_intent": False,
        "creates_submit_authorization": False,
        "places_order": False,
        "calls_order_lifecycle": False,
        "executes_real_submit": False,
        "requires_owner_runtime_profile_confirmation": (
            status == "operator_profile_review_required"
        ),
        "requires_prepare_review": status == "operator_prepare_review_required",
        "requires_final_gate_review": status == "operator_final_gate_review_required",
    }


def _summary_safety(
    *,
    supervisor_packet: dict[str, Any],
    forbidden_effects: list[str],
) -> dict[str, Any]:
    source_safety = _as_dict(supervisor_packet.get("safety_invariants"))
    return {
        "summary_only": True,
        "read_packet_only": True,
        "database_write": False,
        "exchange_write_called": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "runtime_budget_mutated": False,
        "withdrawal_or_transfer_created": False,
        "source_supervisor_safety_flags": source_safety,
        "source_forbidden_effects": forbidden_effects,
        "source_has_forbidden_effects": bool(forbidden_effects),
    }


def _aggregate_forbidden_effects(
    supervisor_packet: dict[str, Any],
    cycles: list[Any],
) -> list[str]:
    effects: list[str] = []
    source_safety = _as_dict(supervisor_packet.get("safety_invariants"))
    if source_safety.get("cycles_have_forbidden_effects") is True:
        effects.append("cycles_have_forbidden_effects")
    for key in FORBIDDEN_EFFECT_KEYS:
        if source_safety.get(key) is True:
            effects.append(f"supervisor:{key}")
    for cycle in cycles:
        if not isinstance(cycle, dict):
            continue
        for effect in _as_list(cycle.get("forbidden_effects")):
            effects.append(f"cycle_{cycle.get('cycle_index', 'unknown')}:{effect}")
    return _dedupe(effects)


def _cycle_blockers(cycles: list[Any]) -> list[str]:
    blockers: list[str] = []
    for cycle in cycles:
        if not isinstance(cycle, dict):
            continue
        for blocker in _as_list(cycle.get("blockers")):
            blockers.append(str(blocker))
    return blockers


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = str(item).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("supervisor JSON root must be an object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a read-only operator summary from a supervisor JSON packet.",
    )
    parser.add_argument("--supervisor-json", required=True)
    parser.add_argument("--output-json")
    return parser.parse_args(argv)


def _main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    packet = _read_json(Path(args.supervisor_json).expanduser())
    summary = build_summary(packet)
    if args.output_json:
        _write_json(Path(args.output_json).expanduser(), summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 2 if summary["status"] == "operator_supervisor_blocked" else 0


def main(argv: list[str] | None = None) -> int:
    return _main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
