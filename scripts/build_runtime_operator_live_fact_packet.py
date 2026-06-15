#!/usr/bin/env python3
"""Build an operator live-fact packet from read-only runtime reports.

The builder only reads JSON files that were produced by other read-only probes.
It does not connect to PG, call exchange, create orders, call OrderLifecycle,
mutate runtime state, or create withdrawal / transfer instructions.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any


FORBIDDEN_TRUE_KEYS = {
    "attempt_counter_mutated",
    "attempt_counter_mutated_by_script",
    "exchange_called",
    "exchange_called_by_classifier",
    "exchange_order_submitted",
    "exchange_submit_armed",
    "exchange_write_called",
    "exchange_write_called_by_classifier",
    "execute_real_submit",
    "execution_intent_created",
    "local_registration_armed",
    "order_cancelled",
    "order_created",
    "order_lifecycle_called",
    "order_lifecycle_called_by_classifier",
    "order_lifecycle_submit_called",
    "position_closed",
    "position_opened",
    "real_exchange_submit_adapter_executed",
    "runtime_budget_mutated",
    "runtime_budget_mutated_by_script",
    "runtime_state_mutated",
    "runtime_state_mutated_by_classifier",
    "withdrawal_or_transfer_created",
    "withdrawal_or_transfer_created_by_classifier",
}


def _read_json(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    text = Path(path).expanduser().read_text(encoding="utf-8")
    start = text.find("{")
    if start < 0:
        raise ValueError(f"{path} does not contain a JSON object")
    value = json.loads(text[start:])
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    output_path = Path(path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _packet(report: dict[str, Any] | None, *keys: str) -> dict[str, Any]:
    if not isinstance(report, dict):
        return {}
    for key in keys:
        value = report.get(key)
        if isinstance(value, dict):
            return value
    return report


def _path_get(value: Any, *path: str) -> Any:
    current = value
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _truthy_forbidden_effects(value: Any, prefix: str = "") -> list[str]:
    effects: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            name = f"{prefix}.{key}" if prefix else str(key)
            if key == "forbidden_effects":
                if isinstance(item, dict):
                    effects.extend(
                        f"{name}.{effect_key}"
                        for effect_key, enabled in item.items()
                        if bool(enabled)
                    )
                elif isinstance(item, list):
                    effects.extend(f"{name}.{entry}" for entry in item if entry)
                continue
            if key in FORBIDDEN_TRUE_KEYS and bool(item):
                effects.append(name)
            effects.extend(_truthy_forbidden_effects(item, name))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            effects.extend(_truthy_forbidden_effects(item, f"{prefix}[{index}]"))
    return sorted(set(effects))


def _list_values(*values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        if isinstance(value, list):
            result.extend(str(item) for item in value if item is not None)
        elif value:
            result.append(str(value))
    return result


def _fact_coverage(
    *,
    runtime_instance_id: str,
    account_facts: dict[str, Any],
    monitor_packet: dict[str, Any],
    finalize_packet: dict[str, Any],
    release_packet: dict[str, Any],
    gate_packet: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    active_count = (
        _int_or_none(monitor_packet.get("local_active_position_count"))
        if monitor_packet
        else None
    )
    exchange_count = _int_or_none(monitor_packet.get("exchange_active_position_count"))
    open_order_count = _int_or_none(monitor_packet.get("local_open_order_count"))
    exchange_stop_count = _int_or_none(
        monitor_packet.get("exchange_open_stop_order_count")
    )
    attempts_remaining = _path_get(
        finalize_packet,
        "next_attempt_gate",
        "attempts_remaining",
    )
    budget_remaining = _path_get(
        finalize_packet,
        "next_attempt_gate",
        "budget_remaining",
    )
    if attempts_remaining is None:
        attempts_remaining = gate_packet.get("attempts_remaining")
    if budget_remaining is None:
        budget_remaining = gate_packet.get("budget_remaining")
    if attempts_remaining is None:
        attempts_remaining = monitor_packet.get("attempts_remaining")
    if budget_remaining is None:
        budget_remaining = monitor_packet.get("budget_remaining")

    return {
        "runtime": {
            "status": "present" if runtime_instance_id else "missing",
            "runtime_instance_id": runtime_instance_id,
        },
        "account": {
            "status": "present" if account_facts else "missing",
            "source": account_facts.get("source") or account_facts.get("scope"),
            "as_of": account_facts.get("as_of") or account_facts.get("timestamp_ms"),
        },
        "position": {
            "status": "present" if monitor_packet else "missing",
            "active_position_present": bool(
                monitor_packet.get("active_position_present")
            ),
            "local_active_position_count": active_count,
            "exchange_active_position_count": exchange_count,
            "symbol": monitor_packet.get("symbol"),
            "side": monitor_packet.get("side"),
        },
        "open_order": {
            "status": "present" if monitor_packet else "missing",
            "local_open_order_count": open_order_count,
            "exchange_open_stop_order_count": exchange_stop_count,
        },
        "protection": {
            "status": "present" if monitor_packet else "missing",
            "protection_status": monitor_packet.get("protection_status"),
            "sl_protection_present": bool(monitor_packet.get("sl_protection_present")),
            "tp_protection_present": bool(monitor_packet.get("tp_protection_present")),
            "hard_stop_boundary_present": bool(
                monitor_packet.get("hard_stop_boundary_present")
            ),
        },
        "budget": {
            "status": "present"
            if attempts_remaining is not None or budget_remaining is not None
            else "missing",
            "attempts_remaining": attempts_remaining,
            "budget_remaining": budget_remaining,
            "budget_reserved": gate_packet.get("budget_reserved")
            or monitor_packet.get("budget_reserved"),
        },
        "next_attempt_gate": {
            "status": "present"
            if finalize_packet or release_packet or gate_packet
            else "missing",
            "finalize_gate_status": _path_get(
                finalize_packet, "next_attempt_gate", "status"
            ),
            "release_status": release_packet.get("status"),
            "gate_classification_status": gate_packet.get("status"),
        },
    }


def _missing_coverage(coverage: dict[str, dict[str, Any]]) -> list[str]:
    return [
        key
        for key, value in coverage.items()
        if value.get("status") in {"missing", "unknown"}
    ]


def _next_attempt_status(
    *,
    coverage: dict[str, dict[str, Any]],
    release_packet: dict[str, Any],
    gate_packet: dict[str, Any],
    finalize_packet: dict[str, Any],
    blockers: list[str],
    missing: list[str],
    forbidden_effects: list[str],
) -> str:
    if forbidden_effects:
        return "blocked_forbidden_effect"
    if missing:
        return "incomplete_live_fact_packet"

    gate_status = str(gate_packet.get("status") or "")
    release_status = str(release_packet.get("status") or "")
    finalize_gate_status = str(_path_get(finalize_packet, "next_attempt_gate", "status") or "")

    if gate_status == "gate_blocked_by_active_position_slot":
        return "waiting_for_position_resolution"
    if release_status == "waiting_for_position_resolution":
        return "waiting_for_position_resolution"
    has_active_position = bool(
        coverage.get("position", {}).get("active_position_present")
    )
    active_slot_blocker = any(
        str(blocker).endswith("runtime_max_active_positions_in_use")
        or str(blocker).endswith("next_attempt_gate_blocked")
        for blocker in blockers
    )
    if has_active_position and active_slot_blocker:
        return "waiting_for_position_resolution"
    if release_status == "ready_for_strategy_signal":
        return "ready_for_strategy_signal"
    if gate_status == "gate_blocker_classification_no_next_attempt_gate_blocker":
        return "ready_for_strategy_signal"
    if finalize_gate_status in {"ready_for_fresh_signal", "ready_for_next_attempt"}:
        return "ready_for_strategy_signal"
    if gate_status or release_status or finalize_gate_status:
        return "blocked"
    return "operator_review"


def build_operator_live_fact_packet(
    *,
    runtime_instance_id: str,
    account_facts: dict[str, Any] | None = None,
    live_position_monitor: dict[str, Any] | None = None,
    post_submit_finalize: dict[str, Any] | None = None,
    active_position_resolution: dict[str, Any] | None = None,
    next_attempt_release: dict[str, Any] | None = None,
    next_attempt_gate_classification: dict[str, Any] | None = None,
    observation_operator: dict[str, Any] | None = None,
    deployed_head: str | None = None,
    release_name: str | None = None,
    remote_report_path: str | None = None,
    generated_at_ms: int | None = None,
) -> dict[str, Any]:
    monitor_packet = _packet(live_position_monitor, "packet")
    finalize_packet = _packet(post_submit_finalize, "post_submit_finalize_packet")
    resolution_packet = _packet(active_position_resolution, "packet")
    release_packet = _packet(next_attempt_release, "packet")
    gate_packet = _packet(next_attempt_gate_classification)
    observation_packet = _packet(observation_operator)
    account_packet = _packet(account_facts)

    coverage = _fact_coverage(
        runtime_instance_id=runtime_instance_id,
        account_facts=account_packet,
        monitor_packet=monitor_packet,
        finalize_packet=finalize_packet,
        release_packet=release_packet,
        gate_packet=gate_packet,
    )
    missing = _missing_coverage(coverage)
    forbidden_effects = _truthy_forbidden_effects(
        {
            "account_facts": account_facts or {},
            "live_position_monitor": live_position_monitor or {},
            "post_submit_finalize": post_submit_finalize or {},
            "active_position_resolution": active_position_resolution or {},
            "next_attempt_release": next_attempt_release or {},
            "next_attempt_gate_classification": next_attempt_gate_classification or {},
            "observation_operator": observation_operator or {},
        }
    )
    blockers = []
    if missing:
        blockers.extend(f"{item}_facts_missing" for item in missing)
    blockers.extend(
        _list_values(
            live_position_monitor.get("blockers") if live_position_monitor else [],
            post_submit_finalize.get("blockers") if post_submit_finalize else [],
            active_position_resolution.get("blockers") if active_position_resolution else [],
            next_attempt_release.get("blockers") if next_attempt_release else [],
            next_attempt_gate_classification.get("blockers")
            if next_attempt_gate_classification
            else [],
            observation_operator.get("blockers") if observation_operator else [],
        )
    )
    status = _next_attempt_status(
        coverage=coverage,
        release_packet=release_packet,
        gate_packet=gate_packet,
        finalize_packet=finalize_packet,
        blockers=blockers,
        missing=missing,
        forbidden_effects=forbidden_effects,
    )
    warnings = _list_values(
        live_position_monitor.get("warnings") if live_position_monitor else [],
        post_submit_finalize.get("warnings") if post_submit_finalize else [],
        active_position_resolution.get("warnings") if active_position_resolution else [],
        next_attempt_release.get("warnings") if next_attempt_release else [],
        next_attempt_gate_classification.get("warnings")
        if next_attempt_gate_classification
        else [],
        observation_operator.get("warnings") if observation_operator else [],
    )
    return {
        "scope": "runtime_operator_live_fact_packet",
        "status": status,
        "runtime_instance_id": runtime_instance_id,
        "generated_at_ms": generated_at_ms if generated_at_ms is not None else int(time.time() * 1000),
        "deployment_context": {
            "deployed_head": deployed_head,
            "release_name": release_name,
            "remote_report_path": remote_report_path,
        },
        "fact_coverage": coverage,
        "missing_required_fact_groups": missing,
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "next_attempt_gate_state": {
            "status": status,
            "finalize_gate_status": coverage["next_attempt_gate"].get(
                "finalize_gate_status"
            ),
            "release_status": coverage["next_attempt_gate"].get("release_status"),
            "gate_classification_status": coverage["next_attempt_gate"].get(
                "gate_classification_status"
            ),
            "requires_fresh_strategy_signal": True,
            "requires_fresh_authorization_before_submit": True,
            "legacy_authorization_replay_allowed": False,
            "executable_submit_allowed_by_packet": False,
        },
        "active_position_resolution": {
            "status": resolution_packet.get("status"),
            "recommended_next_action": resolution_packet.get(
                "recommended_next_action"
            ),
            "can_continue_holding": bool(
                monitor_packet.get("can_continue_holding")
            ),
        },
        "observation_state": {
            "status": observation_packet.get("status"),
            "watch_status": observation_packet.get("watch_status"),
            "diagnostic_status": observation_packet.get("diagnostic_status"),
        },
        "operator_command_plan": {
            "not_executed": True,
            "next_step": _operator_next_step(status),
            "creates_shadow_candidate": False,
            "creates_execution_intent": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "calls_exchange_write": False,
            "requires_owner_close_authorization_now": status
            == "waiting_for_position_resolution"
            and not bool(monitor_packet.get("hard_stop_boundary_present")),
        },
        "safety_invariants": {
            "packet_only": True,
            "reads_json_reports_only": True,
            "pg_called_by_builder": False,
            "exchange_called_by_builder": False,
            "exchange_write_called_by_builder": False,
            "order_lifecycle_called_by_builder": False,
            "runtime_state_mutated_by_builder": False,
            "withdrawal_or_transfer_created_by_builder": False,
            "no_forbidden_live_side_effects": not forbidden_effects,
            "forbidden_effects": forbidden_effects,
        },
    }


def _operator_next_step(status: str) -> str:
    if status == "ready_for_strategy_signal":
        return "start_fresh_strategy_signal_observation"
    if status == "waiting_for_position_resolution":
        return "continue_read_only_position_monitoring_until_flat_or_reviewed"
    if status == "incomplete_live_fact_packet":
        return "collect_missing_read_only_live_fact_groups"
    if status == "blocked_forbidden_effect":
        return "stop_and_review_forbidden_side_effects"
    if status == "blocked":
        return "resolve_next_attempt_gate_blockers"
    return "operator_review_live_fact_packet"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a P0-A read-only runtime operator live-fact packet.",
    )
    parser.add_argument("--runtime-instance-id", required=True)
    parser.add_argument("--account-facts-json")
    parser.add_argument("--live-position-monitor-json")
    parser.add_argument("--post-submit-finalize-json")
    parser.add_argument("--active-position-resolution-json")
    parser.add_argument("--next-attempt-release-json")
    parser.add_argument("--next-attempt-gate-classification-json")
    parser.add_argument("--observation-operator-json")
    parser.add_argument("--deployed-head")
    parser.add_argument("--release-name")
    parser.add_argument("--remote-report-path")
    parser.add_argument("--generated-at-ms", type=int)
    parser.add_argument("--output-json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    packet = build_operator_live_fact_packet(
        runtime_instance_id=args.runtime_instance_id,
        account_facts=_read_json(args.account_facts_json),
        live_position_monitor=_read_json(args.live_position_monitor_json),
        post_submit_finalize=_read_json(args.post_submit_finalize_json),
        active_position_resolution=_read_json(args.active_position_resolution_json),
        next_attempt_release=_read_json(args.next_attempt_release_json),
        next_attempt_gate_classification=_read_json(
            args.next_attempt_gate_classification_json
        ),
        observation_operator=_read_json(args.observation_operator_json),
        deployed_head=args.deployed_head,
        release_name=args.release_name,
        remote_report_path=args.remote_report_path,
        generated_at_ms=args.generated_at_ms,
    )
    if args.output_json:
        _write_json(args.output_json, packet)
    print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if packet["status"] in {
        "ready_for_strategy_signal",
        "waiting_for_position_resolution",
        "incomplete_live_fact_packet",
        "blocked",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
