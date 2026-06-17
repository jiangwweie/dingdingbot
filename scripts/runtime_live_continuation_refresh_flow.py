#!/usr/bin/env python3
"""Refresh live runtime continuation from active-monitor evidence.

RTF-098 is a packet-only orchestration flow:

active runtime observation monitor JSON
-> live-attempt readiness packet
-> continuation selector packet

Optional per-runtime lifecycle packets may be supplied to enrich blocked runtime
decisions, such as the BNB position lifecycle packet from RTF-096.  The flow
does not call APIs, PG, exchange, OrderLifecycle, order registration, close
flows, withdrawal, or transfer services.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import runtime_live_attempt_readiness_packet as readiness  # noqa: E402
from scripts import runtime_live_continuation_selector_packet as selector  # noqa: E402


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


def _status(selector_packet: dict[str, Any], effects: dict[str, bool]) -> str:
    if any(effects.values()):
        return "continuation_refresh_blocked_forbidden_effect"
    selector_status = str(selector_packet.get("status") or "")
    if selector_status == "continuation_monitor_position_or_standing_recovery":
        return "continuation_refresh_monitor_position_or_standing_recovery"
    if selector_status == "continuation_monitor_position_or_owner_close":
        return "continuation_refresh_monitor_position_or_owner_close"
    if selector_status == "continuation_ready_for_final_gate_review":
        return "continuation_refresh_ready_for_final_gate_review"
    if selector_status == "continuation_ready_for_prepare":
        return "continuation_refresh_ready_for_prepare"
    if selector_status == "continuation_waiting_for_strategy_signal":
        return "continuation_refresh_waiting_for_strategy_signal"
    if selector_status == "continuation_needs_gate_blocker_classification":
        return "continuation_refresh_needs_gate_blocker_classification"
    return "continuation_refresh_mixed_or_blocked"


def _operator_plan(status: str, selector_packet: dict[str, Any]) -> dict[str, Any]:
    selector_plan = selector_packet.get("operator_command_plan")
    if not isinstance(selector_plan, dict):
        selector_plan = {}
    return {
        "next_step": selector_plan.get("next_step") or "review_selector_packet",
        "selected_runtime_instance_id": selector_plan.get(
            "selected_runtime_instance_id"
        ),
        "selected_action": selector_plan.get("selected_action"),
        "not_executed": True,
        "creates_shadow_candidate": False,
        "creates_execution_intent": False,
        "places_order": False,
        "calls_order_lifecycle": False,
        "calls_exchange": False,
        "withdraws_or_transfers_funds": False,
        "execute_reduce_only_close_now": False,
        "execute_tiny_live_attempt_now": False,
        "ready_for_controlled_tiny_live_path": status
        in {
            "continuation_refresh_ready_for_final_gate_review",
            "continuation_refresh_ready_for_prepare",
        },
        "uses_legacy_pre_attempt_rehearsal_as_primary_gate": False,
    }


def build_refresh_flow_packet(
    *,
    active_monitor_packet: dict[str, Any],
    lifecycle_packets: list[dict[str, Any]] | None = None,
    deployed_head: str | None = None,
    release_name: str | None = None,
    remote_report_path: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    lifecycle_packets = list(lifecycle_packets or [])
    readiness_packet = readiness.build_readiness_packet(
        active_monitor_packet=active_monitor_packet,
        deployed_head=deployed_head,
        release_name=release_name,
        remote_report_path=remote_report_path,
    )
    selector_packet = selector.build_selector_packet(
        readiness_packet=readiness_packet,
        lifecycle_packets=lifecycle_packets,
        deployed_head=deployed_head,
        release_name=release_name,
        remote_report_path=remote_report_path,
    )
    effects = _forbidden_effects(
        active_monitor_packet,
        readiness_packet,
        selector_packet,
        *lifecycle_packets,
    )
    status = _status(selector_packet, effects)
    refresh_packet = {
        "scope": "runtime_live_continuation_refresh_flow",
        "status": status,
        "source_monitor_status": active_monitor_packet.get("status"),
        "readiness_status": readiness_packet.get("status"),
        "selector_status": selector_packet.get("status"),
        "active_runtime_count": readiness_packet.get("active_runtime_count"),
        "monitored_runtime_count": readiness_packet.get("monitored_runtime_count"),
        "selected_continuation": selector_packet.get("selected_continuation") or {},
        "runtime_continuation_count": len(
            selector_packet.get("runtime_continuations") or []
        ),
        "blockers": list(selector_packet.get("blockers") or []),
        "warnings": list(selector_packet.get("warnings") or []),
        "safety_invariants": {
            "packet_only": True,
            "no_forbidden_live_side_effects": not any(effects.values()),
            "forbidden_effects": effects,
            "api_called_by_refresh_flow": False,
            "pg_called_by_refresh_flow": False,
            "exchange_called_by_refresh_flow": False,
            "exchange_write_called_by_refresh_flow": False,
            "order_lifecycle_called_by_refresh_flow": False,
            "runtime_state_mutated_by_refresh_flow": False,
            "withdrawal_or_transfer_created_by_refresh_flow": False,
        },
        "operator_command_plan": _operator_plan(status, selector_packet),
        "deployment_context": {
            "deployed_head": deployed_head,
            "release_name": release_name,
            "remote_report_path": remote_report_path,
        },
        "right_tail_objective_context": {
            "refreshes_live_facts_before_action": True,
            "real_strategy_signal_required_before_new_attempt": True,
            "bounded_active_position_may_continue": bool(
                (
                    selector_packet.get("right_tail_objective_context") or {}
                ).get("bounded_active_position_may_continue")
            ),
            "new_attempt_not_started_by_refresh_flow": True,
            "owner_manual_close_is_optional_not_automatic": True,
            "automatic_withdrawal_assumed": False,
            "automatic_compounding_assumed": False,
        },
    }
    return refresh_packet, readiness_packet, selector_packet


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build selector-driven live continuation refresh packet.",
    )
    parser.add_argument("--active-monitor-json", required=True)
    parser.add_argument(
        "--lifecycle-json",
        action="append",
        default=[],
        help="Optional per-runtime lifecycle packet. May be repeated.",
    )
    parser.add_argument("--deployed-head")
    parser.add_argument("--release-name")
    parser.add_argument("--remote-report-path")
    parser.add_argument("--output-dir")
    parser.add_argument("--output-json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    refresh_packet, readiness_packet, selector_packet = build_refresh_flow_packet(
        active_monitor_packet=_load_report(args.active_monitor_json),
        lifecycle_packets=[
            _load_report(path)
            for path in (args.lifecycle_json or [])
        ],
        deployed_head=args.deployed_head,
        release_name=args.release_name,
        remote_report_path=args.remote_report_path,
    )
    if args.output_dir:
        output_dir = Path(args.output_dir).expanduser()
        _write_json(output_dir / "live-attempt-readiness-packet.json", readiness_packet)
        _write_json(output_dir / "live-continuation-selector.json", selector_packet)
        _write_json(output_dir / "live-continuation-refresh-flow.json", refresh_packet)
    if args.output_json:
        _write_json(args.output_json, refresh_packet)
    print(json.dumps(refresh_packet, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if refresh_packet["status"] in {
        "continuation_refresh_monitor_position_or_standing_recovery",
        "continuation_refresh_monitor_position_or_owner_close",
        "continuation_refresh_ready_for_final_gate_review",
        "continuation_refresh_ready_for_prepare",
        "continuation_refresh_waiting_for_strategy_signal",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
