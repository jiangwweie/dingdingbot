#!/usr/bin/env python3
"""Build controlled tiny-live bridge readiness from selector refresh output.

RTF-100 consumes a selector-driven refresh packet and decides whether the
runtime can move toward the existing official prepare / FinalGate /
controlled-submit preflight path.  It is packet-only and never creates
candidates, authorizations, ExecutionIntent records, orders, exchange calls,
OrderLifecycle calls, closes, withdrawals, or transfers.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


READY_REFRESH_STATUSES = {
    "continuation_refresh_ready_for_prepare",
    "continuation_refresh_ready_for_final_gate_review",
}

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


def _forbidden_effects(refresh_packet: dict[str, Any]) -> dict[str, bool]:
    effects = {key: False for key in FORBIDDEN_EFFECT_KEYS}
    safety = refresh_packet.get("safety_invariants")
    if not isinstance(safety, dict):
        return effects
    nested = safety.get("forbidden_effects")
    if isinstance(nested, dict):
        for key in effects:
            effects[key] = effects[key] or bool(nested.get(key))
    for key in effects:
        effects[key] = effects[key] or bool(safety.get(key))
    return effects


def _selected(refresh_packet: dict[str, Any]) -> dict[str, Any]:
    selected = refresh_packet.get("selected_continuation")
    return selected if isinstance(selected, dict) else {}


def _status(refresh_packet: dict[str, Any], effects: dict[str, bool]) -> str:
    if any(effects.values()):
        return "controlled_tiny_live_bridge_blocked_forbidden_effect"
    refresh_status = str(refresh_packet.get("status") or "")
    selected = _selected(refresh_packet)
    if refresh_status not in READY_REFRESH_STATUSES:
        return "controlled_tiny_live_bridge_waiting_for_ready_selector"
    if (
        refresh_status == "continuation_refresh_ready_for_final_gate_review"
        and selected.get("ready_for_final_gate_preflight") is True
    ):
        return "controlled_tiny_live_bridge_ready_for_final_gate_review"
    if (
        refresh_status == "continuation_refresh_ready_for_prepare"
        and selected.get("ready_for_prepare") is True
    ):
        return "controlled_tiny_live_bridge_ready_for_official_prepare"
    return "controlled_tiny_live_bridge_blocked_inconsistent_selector"


def _operator_plan(status: str, selected: dict[str, Any]) -> dict[str, Any]:
    if status == "controlled_tiny_live_bridge_ready_for_final_gate_review":
        next_step = "run_official_final_gate_preflight_before_controlled_tiny_live_submit"
    elif status == "controlled_tiny_live_bridge_ready_for_official_prepare":
        next_step = "run_official_prepare_then_final_gate_preflight"
    elif status == "controlled_tiny_live_bridge_blocked_forbidden_effect":
        next_step = "stop_and_review_forbidden_side_effects"
    elif status == "controlled_tiny_live_bridge_blocked_inconsistent_selector":
        next_step = "refresh_selector_before_bridge"
    else:
        next_step = "continue_selector_refresh_until_ready"
    return {
        "next_step": next_step,
        "selected_runtime_instance_id": selected.get("runtime_instance_id"),
        "selected_action": selected.get("selected_action"),
        "symbol": selected.get("symbol"),
        "side": selected.get("side"),
        "strategy_family_id": selected.get("strategy_family_id"),
        "strategy_family_version_id": selected.get("strategy_family_version_id"),
        "not_executed": True,
        "creates_shadow_candidate": False,
        "creates_execution_intent": False,
        "places_order": False,
        "calls_order_lifecycle": False,
        "calls_exchange": False,
        "withdraws_or_transfers_funds": False,
        "execute_tiny_live_attempt_now": False,
        "execute_reduce_only_close_now": False,
        "requires_fresh_final_gate_before_submit": True,
        "requires_controlled_submit_preflight_before_exchange": True,
        "uses_legacy_pre_attempt_rehearsal_as_primary_gate": False,
    }


def build_bridge_readiness_packet(
    *,
    refresh_packet: dict[str, Any],
    deployed_head: str | None = None,
    release_name: str | None = None,
    remote_report_path: str | None = None,
) -> dict[str, Any]:
    selected = _selected(refresh_packet)
    effects = _forbidden_effects(refresh_packet)
    status = _status(refresh_packet, effects)
    blockers: list[str] = []
    if status == "controlled_tiny_live_bridge_waiting_for_ready_selector":
        blockers.append(str(refresh_packet.get("status") or "selector_not_ready"))
    elif status == "controlled_tiny_live_bridge_blocked_inconsistent_selector":
        blockers.append("selector_ready_status_without_matching_selected_flags")
    elif status == "controlled_tiny_live_bridge_blocked_forbidden_effect":
        blockers.append("forbidden_live_side_effect_detected")
    return {
        "scope": "runtime_controlled_tiny_live_bridge_readiness_packet",
        "status": status,
        "source_refresh_status": refresh_packet.get("status"),
        "source_readiness_status": refresh_packet.get("readiness_status"),
        "source_selector_status": refresh_packet.get("selector_status"),
        "selected_continuation": selected,
        "bridge_inputs": {
            "ready_for_prepare": bool(selected.get("ready_for_prepare")),
            "ready_for_final_gate_preflight": bool(
                selected.get("ready_for_final_gate_preflight")
            ),
            "ready_for_controlled_tiny_live_path": bool(
                (refresh_packet.get("operator_command_plan") or {}).get(
                    "ready_for_controlled_tiny_live_path"
                )
            ),
        },
        "blockers": blockers,
        "warnings": list(refresh_packet.get("warnings") or []),
        "safety_invariants": {
            "packet_only": True,
            "no_forbidden_live_side_effects": not any(effects.values()),
            "forbidden_effects": effects,
            "api_called_by_bridge": False,
            "pg_called_by_bridge": False,
            "exchange_called_by_bridge": False,
            "exchange_write_called_by_bridge": False,
            "order_lifecycle_called_by_bridge": False,
            "runtime_state_mutated_by_bridge": False,
            "withdrawal_or_transfer_created_by_bridge": False,
        },
        "operator_command_plan": _operator_plan(status, selected),
        "deployment_context": {
            "deployed_head": deployed_head,
            "release_name": release_name,
            "remote_report_path": remote_report_path,
        },
        "right_tail_objective_context": {
            "small_bounded_losses_allowed_after_final_gate": True,
            "real_strategy_signal_required_before_new_attempt": True,
            "fresh_final_gate_required_before_submit": True,
            "controlled_submit_preflight_required_before_exchange": True,
            "new_attempt_not_started_by_bridge": True,
            "owner_manual_close_is_optional_not_automatic": True,
            "automatic_withdrawal_assumed": False,
            "automatic_compounding_assumed": False,
        },
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build controlled tiny-live bridge readiness packet.",
    )
    parser.add_argument("--refresh-json", required=True)
    parser.add_argument("--deployed-head")
    parser.add_argument("--release-name")
    parser.add_argument("--remote-report-path")
    parser.add_argument("--output-json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    packet = build_bridge_readiness_packet(
        refresh_packet=_load_report(args.refresh_json),
        deployed_head=args.deployed_head,
        release_name=args.release_name,
        remote_report_path=args.remote_report_path,
    )
    if args.output_json:
        _write_json(args.output_json, packet)
    print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if packet["status"] in {
        "controlled_tiny_live_bridge_ready_for_official_prepare",
        "controlled_tiny_live_bridge_ready_for_final_gate_review",
        "controlled_tiny_live_bridge_waiting_for_ready_selector",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
