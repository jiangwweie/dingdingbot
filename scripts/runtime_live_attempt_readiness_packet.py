#!/usr/bin/env python3
"""Build a live-attempt readiness packet from active runtime observation.

RTF-094 is a summarizer over an already produced
``runtime_active_observation_monitor`` packet.  It does not call the API,
create prepare records, register orders, submit to the exchange, mutate runtime
budget, or move funds.  Its job is to turn the current live observation state
into a compact operator packet for the next tiny-live attempt decision.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


FORBIDDEN_EFFECT_KEYS = (
    "exchange_write_called",
    "order_created",
    "order_lifecycle_called",
    "attempt_counter_mutated",
    "runtime_budget_mutated",
    "withdrawal_or_transfer_created",
    "execute_real_submit",
    "exchange_submit_armed",
    "local_registration_armed",
    "executable_execution_intent_created",
    "position_opened",
    "position_closed",
)

READY_EFFECT_KEYS = (
    "prepare_records_created",
    "shadow_candidate_created",
    "runtime_execution_intent_draft_created",
    "recorded_execution_intent_created",
    "submit_authorization_created",
    "protection_plan_created",
)


def _read_json(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("json_root_must_be_object")
    return payload


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    output_path = Path(path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _bool(value: Any) -> bool:
    return bool(value)


def _runtime_summaries(active_monitor_packet: dict[str, Any]) -> list[dict[str, Any]]:
    summaries = active_monitor_packet.get("runtime_summaries")
    if not isinstance(summaries, list):
        return []
    return [item for item in summaries if isinstance(item, dict)]


def _runtime_id(summary: dict[str, Any]) -> str:
    return str(summary.get("runtime_instance_id") or "unknown-runtime")


def _scoped_blockers(summary: dict[str, Any]) -> list[str]:
    runtime_id = _runtime_id(summary)
    return [f"{runtime_id}:{blocker}" for blocker in summary.get("blockers") or []]


def _forbidden_effects_from_monitor(packet: dict[str, Any]) -> dict[str, bool]:
    safety = packet.get("safety_invariants")
    if not isinstance(safety, dict):
        safety = {}
    return {key: _bool(safety.get(key)) for key in FORBIDDEN_EFFECT_KEYS}


def _ready_effects_from_monitor(packet: dict[str, Any]) -> dict[str, bool]:
    safety = packet.get("safety_invariants")
    if not isinstance(safety, dict):
        safety = {}
    return {key: _bool(safety.get(key)) for key in READY_EFFECT_KEYS}


def _runtime_row(summary: dict[str, Any]) -> dict[str, Any]:
    signal_summary = summary.get("signal_summary")
    if not isinstance(signal_summary, dict):
        signal_summary = {}
    created_records = summary.get("created_records")
    if not isinstance(created_records, dict):
        created_records = {}
    forbidden_effects = summary.get("forbidden_effects")
    if not isinstance(forbidden_effects, dict):
        forbidden_effects = {}
    return {
        "runtime_instance_id": _runtime_id(summary),
        "status": summary.get("status"),
        "symbol": summary.get("symbol"),
        "side": summary.get("side"),
        "strategy_family_id": summary.get("strategy_family_id"),
        "strategy_family_version_id": summary.get("strategy_family_version_id"),
        "ready_for_prepare": _bool(summary.get("ready_for_prepare")),
        "ready_for_final_gate_preflight": _bool(
            summary.get("ready_for_final_gate_preflight")
        ),
        "blockers": list(summary.get("blockers") or []),
        "warnings": list(summary.get("warnings") or []),
        "signal": {
            "evaluation_status": signal_summary.get("evaluation_status"),
            "signal_type": signal_summary.get("signal_type"),
            "required_execution_mode": signal_summary.get(
                "required_execution_mode"
            ),
            "side": signal_summary.get("side"),
            "confidence": signal_summary.get("confidence"),
            "reason_codes": list(signal_summary.get("reason_codes") or []),
            "human_summary": signal_summary.get("human_summary"),
        },
        "created_records": {
            key: _bool(created_records.get(key)) for key in READY_EFFECT_KEYS
        },
        "forbidden_effects": {
            key: _bool(forbidden_effects.get(key)) for key in FORBIDDEN_EFFECT_KEYS
        },
        "report_path": summary.get("report_path"),
        "signal_input_json": summary.get("signal_input_json"),
        "prepared_authorization_id": summary.get("prepared_authorization_id"),
    }


def _counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    waiting_signal = 0
    runtime_gate_blocked = 0
    ready_prepare = 0
    ready_final_gate = 0
    blocked = 0
    for row in rows:
        blockers = set(row.get("blockers") or [])
        if row.get("ready_for_final_gate_preflight"):
            ready_final_gate += 1
        if row.get("ready_for_prepare"):
            ready_prepare += 1
        if "strategy_signal_not_ready_for_shadow_candidate_prepare" in blockers:
            waiting_signal += 1
        if "next_attempt_gate_blocked" in blockers:
            runtime_gate_blocked += 1
        if row.get("status") == "blocked" or blockers:
            blocked += 1
    return {
        "waiting_signal_count": waiting_signal,
        "runtime_gate_blocked_count": runtime_gate_blocked,
        "ready_for_prepare_count": ready_prepare,
        "ready_for_final_gate_preflight_count": ready_final_gate,
        "blocked_or_waiting_count": blocked,
    }


def _status(
    *,
    rows: list[dict[str, Any]],
    forbidden_effects: dict[str, bool],
    counts: dict[str, int],
) -> str:
    if any(forbidden_effects.values()):
        return "live_attempt_blocked_forbidden_effect"
    if not rows:
        return "live_attempt_blocked_no_active_runtime"
    if counts["ready_for_final_gate_preflight_count"] > 0:
        return "live_attempt_ready_for_final_gate_review"
    if counts["ready_for_prepare_count"] > 0:
        return "live_attempt_ready_for_prepare_review"
    if counts["runtime_gate_blocked_count"] > 0:
        return "live_attempt_blocked_by_runtime_or_signal_gate"
    if counts["waiting_signal_count"] == len(rows):
        return "live_attempt_waiting_for_strategy_signal"
    return "live_attempt_blocked_by_runtime_or_signal_gate"


def _operator_plan(status: str) -> dict[str, Any]:
    if status == "live_attempt_ready_for_final_gate_review":
        next_step = "review_official_final_gate_preflight_before_live_submit"
    elif status == "live_attempt_ready_for_prepare_review":
        next_step = "prepare_shadow_candidate_records_after_owner_review"
    elif status == "live_attempt_waiting_for_strategy_signal":
        next_step = "continue_live_read_only_observation_until_strategy_signal_ready"
    elif status == "live_attempt_blocked_no_active_runtime":
        next_step = "start_or_authorize_active_runtime_before_live_attempt"
    elif status == "live_attempt_blocked_forbidden_effect":
        next_step = "stop_and_review_forbidden_side_effects"
    else:
        next_step = "resolve_runtime_gate_blockers_or_wait_for_fresh_signal"
    return {
        "next_step": next_step,
        "not_executed": True,
        "creates_shadow_candidate": False,
        "creates_execution_intent": False,
        "places_order": False,
        "calls_order_lifecycle": False,
        "calls_exchange": False,
        "withdraws_or_transfers_funds": False,
        "requires_fresh_runtime_candidate_action_decision_before_submit": True,
        "uses_legacy_pre_attempt_rehearsal_as_primary_gate": False,
    }


def build_readiness_packet(
    *,
    active_monitor_packet: dict[str, Any],
    deployed_head: str | None = None,
    release_name: str | None = None,
    remote_report_path: str | None = None,
    health_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rows = [_runtime_row(summary) for summary in _runtime_summaries(active_monitor_packet)]
    forbidden_effects = _forbidden_effects_from_monitor(active_monitor_packet)
    ready_effects = _ready_effects_from_monitor(active_monitor_packet)
    counts = _counts(rows)
    status = _status(rows=rows, forbidden_effects=forbidden_effects, counts=counts)
    blockers: list[str] = []
    for row in rows:
        for blocker in row.get("blockers") or []:
            scoped = f"{row['runtime_instance_id']}:{blocker}"
            if scoped not in blockers:
                blockers.append(scoped)
    warnings = list(active_monitor_packet.get("warnings") or [])

    return {
        "scope": "runtime_live_attempt_readiness_packet",
        "status": status,
        "source_monitor_scope": active_monitor_packet.get("scope"),
        "source_monitor_status": active_monitor_packet.get("status"),
        "active_runtime_count": int(active_monitor_packet.get("active_runtime_count") or 0),
        "monitored_runtime_count": int(
            active_monitor_packet.get("monitored_runtime_count") or len(rows)
        ),
        "selected_runtime_instance_ids": list(
            active_monitor_packet.get("selected_runtime_instance_ids") or []
        ),
        "readiness_counts": counts,
        "runtime_readiness": rows,
        "blockers": blockers,
        "warnings": warnings,
        "safety_invariants": {
            "uses_official_trading_console_api": _bool(
                (active_monitor_packet.get("safety_invariants") or {}).get(
                    "uses_official_trading_console_api"
                )
            ),
            "forbidden_effects": forbidden_effects,
            "ready_effects": ready_effects,
            "no_forbidden_live_side_effects": not any(forbidden_effects.values()),
            "no_prepare_records_created_in_this_packet": not any(
                ready_effects.values()
            ),
        },
        "deployment_context": {
            "deployed_head": deployed_head,
            "release_name": release_name,
            "remote_report_path": remote_report_path,
            "health": health_json or {},
            "live_ready": (health_json or {}).get("live_ready"),
        },
        "operator_command_plan": _operator_plan(status),
        "right_tail_objective_context": {
            "small_bounded_losses_allowed_after_runtime_gate": True,
            "strategy_signal_must_be_real_not_faked": True,
            "right_tail_runner_should_not_be_prematurely_capped": True,
            "automatic_compounding_assumed": False,
            "automatic_withdrawal_assumed": False,
            "not_proven_alpha_is_not_semantic_blocker": True,
        },
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a live attempt readiness packet from active monitor JSON.",
    )
    parser.add_argument("--active-monitor-json", required=True)
    parser.add_argument("--health-json")
    parser.add_argument("--deployed-head")
    parser.add_argument("--release-name")
    parser.add_argument("--remote-report-path")
    parser.add_argument("--output-json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    health = _read_json(args.health_json) if args.health_json else None
    packet = build_readiness_packet(
        active_monitor_packet=_read_json(args.active_monitor_json),
        deployed_head=args.deployed_head,
        release_name=args.release_name,
        remote_report_path=args.remote_report_path,
        health_json=health,
    )
    if args.output_json:
        _write_json(args.output_json, packet)
    print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if packet["status"] in {
        "live_attempt_ready_for_final_gate_review",
        "live_attempt_ready_for_prepare_review",
        "live_attempt_waiting_for_strategy_signal",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
