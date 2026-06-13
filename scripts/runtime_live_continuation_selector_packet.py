#!/usr/bin/env python3
"""Build a live runtime continuation selector packet.

RTF-097 combines the current live-attempt readiness packet with optional
per-runtime follow-up packets such as the BNB position lifecycle packet.  It is
packet-only: it does not call APIs, create candidates, close positions, submit
orders, mutate runtime state, call exchange, or move funds.
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
    "runtime_state_mutated",
    "runtime_budget_mutated",
    "withdrawal_or_transfer_created",
    "position_closed",
    "execute_real_submit",
    "exchange_submit_armed",
    "local_registration_armed",
    "executable_execution_intent_created",
)


def _load_report(path: str | Path) -> dict[str, Any]:
    text = Path(path).expanduser().read_text(encoding="utf-8")
    start = text.find("{")
    if start < 0:
        raise ValueError(f"{path} does not contain a JSON object")
    payload = json.loads(text[start:])
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    output_path = Path(path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _dedupe(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _forbidden_effects(*packets: dict[str, Any] | None) -> dict[str, bool]:
    effects = {key: False for key in FORBIDDEN_EFFECT_KEYS}
    for packet in packets:
        if not isinstance(packet, dict):
            continue
        safety = packet.get("safety_invariants")
        if not isinstance(safety, dict):
            continue
        nested = safety.get("forbidden_effects")
        if isinstance(nested, dict):
            for key in effects:
                effects[key] = effects[key] or bool(nested.get(key))
        for key in effects:
            effects[key] = effects[key] or bool(safety.get(key))
    return effects


def _runtime_rows(readiness_packet: dict[str, Any]) -> list[dict[str, Any]]:
    rows = readiness_packet.get("runtime_readiness")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _lifecycle_by_runtime(
    lifecycle_packets: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for packet in lifecycle_packets:
        runtime_id = str(packet.get("runtime_instance_id") or "")
        if runtime_id:
            result[runtime_id] = packet
    return result


def _row_action(row: dict[str, Any], lifecycle: dict[str, Any] | None) -> str:
    if row.get("ready_for_final_gate_preflight"):
        return "review_final_gate_preflight"
    if row.get("ready_for_prepare"):
        return "prepare_shadow_candidate_records"
    if lifecycle:
        lifecycle_status = str(lifecycle.get("status") or "")
        if lifecycle_status == "position_lifecycle_hold_or_owner_close_ready":
            return "monitor_position_or_owner_authorize_reduce_only_close"
        if lifecycle_status == "position_lifecycle_hold_with_hard_stop":
            return "monitor_position_until_flat_or_exit_signal"
        if lifecycle_status == "position_lifecycle_ready_for_closed_review":
            return "record_closed_trade_review"
        if lifecycle_status == "position_lifecycle_ready_for_next_attempt_gate":
            return "verify_next_attempt_gate"
        if lifecycle_status.startswith("position_lifecycle_blocked"):
            return "resolve_position_lifecycle_blocker"
    blockers = set(row.get("blockers") or [])
    if "strategy_signal_not_ready_for_shadow_candidate_prepare" in blockers:
        return "wait_for_strategy_signal"
    if "next_attempt_gate_blocked" in blockers:
        return "classify_or_refresh_next_attempt_gate_blocker"
    if row.get("status") == "waiting_for_signal":
        return "wait_for_strategy_signal"
    return "inspect_runtime_state"


def _priority(action: str) -> int:
    priorities = {
        "review_final_gate_preflight": 100,
        "prepare_shadow_candidate_records": 90,
        "monitor_position_or_owner_authorize_reduce_only_close": 70,
        "monitor_position_until_flat_or_exit_signal": 60,
        "record_closed_trade_review": 55,
        "verify_next_attempt_gate": 50,
        "wait_for_strategy_signal": 40,
        "classify_or_refresh_next_attempt_gate_blocker": 35,
        "resolve_position_lifecycle_blocker": 20,
        "inspect_runtime_state": 10,
    }
    return priorities.get(action, 0)


def _continuation_row(
    row: dict[str, Any], lifecycle: dict[str, Any] | None
) -> dict[str, Any]:
    action = _row_action(row, lifecycle)
    signal = row.get("signal")
    if not isinstance(signal, dict):
        signal = {}
    operator = lifecycle.get("operator_command_plan") if lifecycle else None
    if not isinstance(operator, dict):
        operator = {}
    return {
        "runtime_instance_id": row.get("runtime_instance_id"),
        "symbol": row.get("symbol"),
        "side": row.get("side"),
        "strategy_family_id": row.get("strategy_family_id"),
        "strategy_family_version_id": row.get("strategy_family_version_id"),
        "readiness_status": row.get("status"),
        "ready_for_prepare": bool(row.get("ready_for_prepare")),
        "ready_for_final_gate_preflight": bool(
            row.get("ready_for_final_gate_preflight")
        ),
        "blockers": list(row.get("blockers") or []),
        "warnings": list(row.get("warnings") or []),
        "signal": {
            "evaluation_status": signal.get("evaluation_status"),
            "signal_type": signal.get("signal_type"),
            "required_execution_mode": signal.get("required_execution_mode"),
            "confidence": signal.get("confidence"),
            "reason_codes": list(signal.get("reason_codes") or []),
            "human_summary": signal.get("human_summary"),
        },
        "lifecycle_status": lifecycle.get("status") if lifecycle else None,
        "lifecycle_next_step": operator.get("next_step"),
        "allows_new_attempt_now": bool(operator.get("allows_new_attempt_now")),
        "reduce_only_close_ready_for_owner_authorization": bool(
            operator.get("reduce_only_close_ready_for_owner_authorization")
        ),
        "owner_close_approval_value": operator.get("owner_close_approval_value"),
        "selected_action": action,
        "priority": _priority(action),
    }


def _selector_status(
    rows: list[dict[str, Any]], forbidden_effects: dict[str, bool]
) -> str:
    if any(forbidden_effects.values()):
        return "continuation_blocked_forbidden_effect"
    if not rows:
        return "continuation_blocked_no_active_runtime"
    actions = {str(row.get("selected_action") or "") for row in rows}
    if "review_final_gate_preflight" in actions:
        return "continuation_ready_for_final_gate_review"
    if "prepare_shadow_candidate_records" in actions:
        return "continuation_ready_for_prepare"
    if "monitor_position_or_owner_authorize_reduce_only_close" in actions:
        return "continuation_monitor_position_or_owner_close"
    if actions == {"wait_for_strategy_signal"}:
        return "continuation_waiting_for_strategy_signal"
    if "classify_or_refresh_next_attempt_gate_blocker" in actions:
        return "continuation_needs_gate_blocker_classification"
    if "resolve_position_lifecycle_blocker" in actions:
        return "continuation_blocked_by_position_lifecycle"
    return "continuation_mixed_observation"


def _operator_plan(status: str, selected: dict[str, Any] | None) -> dict[str, Any]:
    if status == "continuation_ready_for_final_gate_review":
        next_step = "review_final_gate_and_controlled_tiny_live_attempt"
    elif status == "continuation_ready_for_prepare":
        next_step = "run_official_prepare_for_ready_strategy_candidate"
    elif status == "continuation_monitor_position_or_owner_close":
        next_step = "continue_position_monitoring_or_owner_authorize_reduce_only_close"
    elif status == "continuation_waiting_for_strategy_signal":
        next_step = "continue_live_read_only_strategy_observation"
    elif status == "continuation_needs_gate_blocker_classification":
        next_step = "classify_next_attempt_gate_blocker_with_position_facts"
    elif status == "continuation_blocked_forbidden_effect":
        next_step = "stop_and_review_forbidden_side_effects"
    else:
        next_step = "inspect_runtime_continuation_state"
    return {
        "next_step": next_step,
        "selected_runtime_instance_id": (
            selected.get("runtime_instance_id") if selected else None
        ),
        "selected_action": selected.get("selected_action") if selected else None,
        "not_executed": True,
        "creates_shadow_candidate": False,
        "creates_execution_intent": False,
        "places_order": False,
        "calls_order_lifecycle": False,
        "calls_exchange": False,
        "withdraws_or_transfers_funds": False,
        "execute_reduce_only_close_now": False,
        "execute_tiny_live_attempt_now": False,
        "requires_fresh_final_gate_before_submit": True,
        "uses_legacy_pre_attempt_rehearsal_as_primary_gate": False,
    }


def build_selector_packet(
    *,
    readiness_packet: dict[str, Any],
    lifecycle_packets: list[dict[str, Any]] | None = None,
    deployed_head: str | None = None,
    release_name: str | None = None,
    remote_report_path: str | None = None,
) -> dict[str, Any]:
    lifecycle_packets = list(lifecycle_packets or [])
    lifecycle_map = _lifecycle_by_runtime(lifecycle_packets)
    rows = [
        _continuation_row(row, lifecycle_map.get(str(row.get("runtime_instance_id") or "")))
        for row in _runtime_rows(readiness_packet)
    ]
    rows.sort(key=lambda item: item.get("priority", 0), reverse=True)
    effects = _forbidden_effects(readiness_packet, *lifecycle_packets)
    status = _selector_status(rows, effects)
    selected = rows[0] if rows else None
    blockers = _dedupe(
        [
            *(readiness_packet.get("blockers") or []),
            *[
                f"{row.get('runtime_instance_id')}:{blocker}"
                for row in rows
                for blocker in row.get("blockers") or []
            ],
        ]
    )
    warnings = _dedupe(
        [
            *(readiness_packet.get("warnings") or []),
            *[
                f"{row.get('runtime_instance_id')}:{warning}"
                for row in rows
                for warning in row.get("warnings") or []
            ],
            *[
                f"{packet.get('runtime_instance_id')}:{warning}"
                for packet in lifecycle_packets
                for warning in packet.get("warnings") or []
            ],
        ]
    )
    return {
        "scope": "runtime_live_continuation_selector_packet",
        "status": status,
        "source_readiness_status": readiness_packet.get("status"),
        "active_runtime_count": readiness_packet.get("active_runtime_count"),
        "monitored_runtime_count": readiness_packet.get("monitored_runtime_count"),
        "runtime_continuations": rows,
        "selected_continuation": selected or {},
        "blockers": blockers,
        "warnings": warnings,
        "safety_invariants": {
            "packet_only": True,
            "no_forbidden_live_side_effects": not any(effects.values()),
            "forbidden_effects": effects,
            "pg_called_by_selector": False,
            "exchange_called_by_selector": False,
            "exchange_write_called_by_selector": False,
            "order_lifecycle_called_by_selector": False,
            "runtime_state_mutated_by_selector": False,
            "withdrawal_or_transfer_created_by_selector": False,
        },
        "operator_command_plan": _operator_plan(status, selected),
        "deployment_context": {
            "deployed_head": deployed_head,
            "release_name": release_name,
            "remote_report_path": remote_report_path,
        },
        "right_tail_objective_context": {
            "bounded_active_position_may_continue": any(
                row.get("selected_action")
                == "monitor_position_or_owner_authorize_reduce_only_close"
                for row in rows
            ),
            "real_strategy_signal_required_before_new_attempt": True,
            "new_attempt_not_started_by_selector": True,
            "owner_manual_close_is_optional_not_automatic": True,
            "automatic_withdrawal_assumed": False,
            "automatic_compounding_assumed": False,
        },
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build live runtime continuation selector packet.",
    )
    parser.add_argument("--readiness-json", required=True)
    parser.add_argument(
        "--lifecycle-json",
        action="append",
        default=[],
        help="Optional per-runtime lifecycle packet. May be repeated.",
    )
    parser.add_argument("--deployed-head")
    parser.add_argument("--release-name")
    parser.add_argument("--remote-report-path")
    parser.add_argument("--output-json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    packet = build_selector_packet(
        readiness_packet=_load_report(args.readiness_json),
        lifecycle_packets=[
            _load_report(path)
            for path in (args.lifecycle_json or [])
        ],
        deployed_head=args.deployed_head,
        release_name=args.release_name,
        remote_report_path=args.remote_report_path,
    )
    if args.output_json:
        _write_json(args.output_json, packet)
    print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if packet["status"] in {
        "continuation_ready_for_final_gate_review",
        "continuation_ready_for_prepare",
        "continuation_monitor_position_or_owner_close",
        "continuation_waiting_for_strategy_signal",
        "continuation_mixed_observation",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
