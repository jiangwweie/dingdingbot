#!/usr/bin/env python3
"""Build a position lifecycle / exit-path readiness packet.

RTF-096 consumes existing packet artifacts only:

- RTF-095 next-attempt gate blocker classification
- runtime live-position monitor
- optional runtime position exit plan
- optional post-close follow-up packet

It does not call PG, exchange, OrderLifecycle, or runtime mutation services.
It decides whether the active runtime position should keep being monitored,
whether a reduce-only recovery is ready for standing authorization plus the
official Operation Layer, or whether a flat runtime can move toward closed
review / next-attempt gate.
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
    "order_cancelled",
    "order_amended",
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


def _payload(report: dict[str, Any] | None, key: str) -> dict[str, Any]:
    if not isinstance(report, dict):
        return {}
    value = report.get(key)
    if isinstance(value, dict):
        return value
    return report


def _safety_from(*reports: dict[str, Any] | None) -> dict[str, bool]:
    effects = {key: False for key in FORBIDDEN_EFFECT_KEYS}
    for report in reports:
        if not isinstance(report, dict):
            continue
        safety = report.get("safety_invariants")
        if not isinstance(safety, dict):
            continue
        nested = safety.get("forbidden_effects")
        if isinstance(nested, dict):
            for key in effects:
                effects[key] = effects[key] or bool(nested.get(key))
        for key in effects:
            effects[key] = effects[key] or bool(safety.get(key))
    return effects


def _dedupe(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return output


def _status(
    *,
    classification: dict[str, Any],
    monitor: dict[str, Any],
    exit_plan: dict[str, Any],
    followup: dict[str, Any],
    effects: dict[str, bool],
) -> str:
    if any(effects.values()):
        return "position_lifecycle_blocked_forbidden_effect"
    classification_status = str(classification.get("status") or "")
    if classification_status == "gate_blocker_classification_missing_position_facts":
        return "position_lifecycle_blocked_missing_position_facts"
    if classification_status == "gate_blocked_by_stale_or_unresolved_next_attempt_projection":
        return "position_lifecycle_refresh_reconciliation_or_closed_review"

    active = bool(monitor.get("active_position_present"))
    if active:
        hard_stop = bool(monitor.get("hard_stop_boundary_present"))
        can_hold = bool(monitor.get("can_continue_holding"))
        full_close_ready = bool(exit_plan.get("full_reduce_only_close_feasible"))
        standing_recovery_ready = (
            str(followup.get("status") or "")
            == "ready_for_standing_reduce_only_recovery"
        )
        waiting_close_auth = (
            str(followup.get("status") or "")
            == "waiting_for_owner_close_authorization"
        )
        if hard_stop and can_hold and full_close_ready and standing_recovery_ready:
            return "position_lifecycle_hold_or_standing_recovery_ready"
        if hard_stop and can_hold and full_close_ready and waiting_close_auth:
            return "position_lifecycle_hold_or_owner_close_ready"
        if hard_stop and can_hold:
            return "position_lifecycle_hold_with_hard_stop"
        return "position_lifecycle_repair_or_reduce_unprotected_position"

    followup_status = str(followup.get("status") or "")
    if followup_status == "ready_for_closed_review":
        return "position_lifecycle_ready_for_closed_review"
    if followup_status == "post_close_complete":
        return "position_lifecycle_ready_for_next_attempt_gate"
    if classification_status == "gate_blocker_classification_no_next_attempt_gate_blocker":
        return "position_lifecycle_return_to_live_attempt_readiness"
    return "position_lifecycle_blocked_unknown_state"


def _operator_plan(status: str, followup: dict[str, Any]) -> dict[str, Any]:
    close_ready = status in {
        "position_lifecycle_hold_or_standing_recovery_ready",
        "position_lifecycle_hold_or_owner_close_ready",
    }
    standing_recovery_ready = status == "position_lifecycle_hold_or_standing_recovery_ready"
    if standing_recovery_ready:
        next_step = "continue_monitoring_or_prepare_official_reduce_only_recovery"
    elif status == "position_lifecycle_hold_or_owner_close_ready":
        next_step = "continue_monitoring_or_explicitly_authorize_reduce_only_close"
    elif status == "position_lifecycle_hold_with_hard_stop":
        next_step = "continue_read_only_position_monitoring_until_flat_or_exit_signal"
    elif status == "position_lifecycle_repair_or_reduce_unprotected_position":
        next_step = "repair_protection_or_prepare_owner_reduce_only_close"
    elif status == "position_lifecycle_ready_for_closed_review":
        next_step = "record_closed_trade_review_before_next_attempt_gate"
    elif status == "position_lifecycle_ready_for_next_attempt_gate":
        next_step = "verify_next_attempt_gate"
    elif status == "position_lifecycle_refresh_reconciliation_or_closed_review":
        next_step = "refresh_reconciliation_or_finalize_closed_review"
    elif status == "position_lifecycle_blocked_forbidden_effect":
        next_step = "stop_and_review_forbidden_side_effects"
    else:
        next_step = "inspect_position_lifecycle_facts"
    return {
        "next_step": next_step,
        "not_executed": True,
        "creates_shadow_candidate": False,
        "creates_execution_intent": False,
        "places_order": False,
        "calls_order_lifecycle": False,
        "calls_exchange": False,
        "withdraws_or_transfers_funds": False,
        "allows_new_attempt_now": status
        in {
            "position_lifecycle_ready_for_next_attempt_gate",
            "position_lifecycle_return_to_live_attempt_readiness",
        },
        "reduce_only_close_ready_for_owner_authorization": (
            status == "position_lifecycle_hold_or_owner_close_ready"
        ),
        "reduce_only_recovery_ready_for_standing_authorization": standing_recovery_ready,
        "requires_official_operation_layer": standing_recovery_ready,
        "execute_reduce_only_close_now": False,
        "owner_close_approval_env": followup.get("owner_close_approval_env")
        if close_ready
        else None,
        "owner_close_approval_value": followup.get("owner_close_approval_value")
        if close_ready
        else None,
        "standing_recovery_authorization_scope": followup.get(
            "standing_recovery_authorization_scope"
        )
        if standing_recovery_ready
        else None,
        "required_steps": list(followup.get("required_steps") or []),
        "completed_steps": list(followup.get("completed_steps") or []),
        "uses_legacy_pre_attempt_rehearsal_as_primary_gate": False,
    }


def build_lifecycle_packet(
    *,
    gate_classification: dict[str, Any],
    live_position_monitor: dict[str, Any],
    position_exit_plan: dict[str, Any] | None = None,
    post_close_followup: dict[str, Any] | None = None,
    deployed_head: str | None = None,
    release_name: str | None = None,
    remote_report_path: str | None = None,
) -> dict[str, Any]:
    classification = gate_classification
    monitor = _payload(live_position_monitor, "packet")
    exit_plan = _payload(position_exit_plan, "plan")
    followup = _payload(post_close_followup, "packet")
    effects = _safety_from(
        gate_classification,
        live_position_monitor,
        position_exit_plan,
        post_close_followup,
    )
    status = _status(
        classification=classification,
        monitor=monitor,
        exit_plan=exit_plan,
        followup=followup,
        effects=effects,
    )
    blockers = _dedupe(
        [
            *(classification.get("blockers") or []),
            *(monitor.get("blockers") or []),
            *(exit_plan.get("blockers") or []),
            *(followup.get("blockers") or []),
        ]
    )
    warnings = _dedupe(
        [
            *(classification.get("warnings") or []),
            *(monitor.get("warnings") or []),
            *(exit_plan.get("warnings") or []),
            *(followup.get("warnings") or []),
        ]
    )
    runtime_id = str(
        monitor.get("runtime_instance_id")
        or classification.get("runtime_instance_id")
        or followup.get("runtime_instance_id")
        or ""
    )
    return {
        "scope": "runtime_position_lifecycle_exit_readiness_packet",
        "status": status,
        "runtime_instance_id": runtime_id,
        "symbol": monitor.get("symbol") or classification.get("position_facts", {}).get("symbol"),
        "side": monitor.get("side") or classification.get("position_facts", {}).get("side"),
        "source_statuses": {
            "gate_classification": classification.get("status"),
            "live_position_monitor": monitor.get("status"),
            "position_exit_plan": exit_plan.get("status"),
            "post_close_followup": followup.get("status"),
        },
        "position_facts": {
            "active_position_present": bool(monitor.get("active_position_present")),
            "current_qty": monitor.get("current_qty"),
            "entry_price": monitor.get("entry_price"),
            "mark_price": monitor.get("mark_price"),
            "unrealized_pnl": monitor.get("unrealized_pnl"),
            "local_active_position_count": monitor.get("local_active_position_count"),
            "exchange_active_position_count": monitor.get(
                "exchange_active_position_count"
            ),
            "max_active_positions": monitor.get("max_active_positions"),
            "hard_stop_boundary_present": bool(
                monitor.get("hard_stop_boundary_present")
            ),
            "protection_status": monitor.get("protection_status"),
            "sl_protection_present": bool(monitor.get("sl_protection_present")),
            "tp_protection_present": bool(monitor.get("tp_protection_present")),
            "can_continue_holding": bool(monitor.get("can_continue_holding")),
            "attempts_used": monitor.get("attempts_used"),
            "attempts_remaining": monitor.get("attempts_remaining"),
            "budget_reserved": monitor.get("budget_reserved"),
            "budget_remaining": monitor.get("budget_remaining"),
            "reconciliation_mismatch_types": list(
                monitor.get("reconciliation_mismatch_types") or []
            ),
            "reconciliation_warning_count": monitor.get(
                "reconciliation_warning_count"
            ),
            "reconciliation_severe_count": monitor.get("reconciliation_severe_count"),
        },
        "exit_path": {
            "exit_plan_status": exit_plan.get("status"),
            "recommended_owner_decision": exit_plan.get(
                "recommended_owner_decision"
            ),
            "tp1_quantity_feasible": bool(exit_plan.get("tp1_quantity_feasible")),
            "tp1_price_reference": exit_plan.get("tp1_price_reference"),
            "tp1_quantity_requested": exit_plan.get("tp1_quantity_requested"),
            "tp1_quantity_step_aligned": exit_plan.get(
                "tp1_quantity_step_aligned"
            ),
            "runner_quantity_reference": exit_plan.get("runner_quantity_reference"),
            "runner_preserved": bool(exit_plan.get("runner_preserved", True)),
            "full_reduce_only_close_feasible": bool(
                exit_plan.get("full_reduce_only_close_feasible")
            ),
            "full_reduce_only_close_quantity": exit_plan.get(
                "full_reduce_only_close_quantity"
            ),
            "full_reduce_only_close_notional_reference": exit_plan.get(
                "full_reduce_only_close_notional_reference"
            ),
            "full_reduce_only_close_requires_owner_authorization": bool(
                exit_plan.get(
                    "full_reduce_only_close_requires_owner_authorization",
                    True,
                )
            ),
            "standing_recovery_authorization_scope": followup.get(
                "standing_recovery_authorization_scope"
            ),
            "post_close_followup_status": followup.get("status"),
        },
        "blockers": blockers,
        "warnings": warnings,
        "safety_invariants": {
            "packet_only": True,
            "no_forbidden_live_side_effects": not any(effects.values()),
            "forbidden_effects": effects,
            "pg_called_by_lifecycle_packet": False,
            "exchange_called_by_lifecycle_packet": False,
            "exchange_write_called_by_lifecycle_packet": False,
            "order_lifecycle_called_by_lifecycle_packet": False,
            "runtime_state_mutated_by_lifecycle_packet": False,
            "withdrawal_or_transfer_created_by_lifecycle_packet": False,
        },
        "operator_command_plan": _operator_plan(status, followup),
        "deployment_context": {
            "deployed_head": deployed_head,
            "release_name": release_name,
            "remote_report_path": remote_report_path,
        },
        "right_tail_objective_context": {
            "protected_position_may_be_held_for_right_tail": bool(
                monitor.get("hard_stop_boundary_present")
                and monitor.get("can_continue_holding")
            ),
            "new_attempt_blocked_while_active_slot_occupied": bool(
                monitor.get("active_position_present")
            ),
            "tp1_partial_can_be_infeasible_without_capping_runner": not bool(
                exit_plan.get("tp1_quantity_feasible")
            ),
            "owner_manual_close_is_optional_not_automatic": True,
            "standing_reduce_only_recovery_uses_official_operation_layer": bool(
                followup.get("standing_recovery_authorization_scope")
            ),
            "automatic_withdrawal_assumed": False,
            "automatic_compounding_assumed": False,
        },
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build position lifecycle / exit-path readiness packet.",
    )
    parser.add_argument("--gate-classification-json", required=True)
    parser.add_argument("--live-position-monitor-json", required=True)
    parser.add_argument("--position-exit-plan-json")
    parser.add_argument("--post-close-followup-json")
    parser.add_argument("--deployed-head")
    parser.add_argument("--release-name")
    parser.add_argument("--remote-report-path")
    parser.add_argument("--output-json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    packet = build_lifecycle_packet(
        gate_classification=_load_report(args.gate_classification_json),
        live_position_monitor=_load_report(args.live_position_monitor_json),
        position_exit_plan=(
            _load_report(args.position_exit_plan_json)
            if args.position_exit_plan_json
            else None
        ),
        post_close_followup=(
            _load_report(args.post_close_followup_json)
            if args.post_close_followup_json
            else None
        ),
        deployed_head=args.deployed_head,
        release_name=args.release_name,
        remote_report_path=args.remote_report_path,
    )
    if args.output_json:
        _write_json(args.output_json, packet)
    print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if packet["status"] in {
        "position_lifecycle_hold_or_standing_recovery_ready",
        "position_lifecycle_hold_or_owner_close_ready",
        "position_lifecycle_hold_with_hard_stop",
        "position_lifecycle_ready_for_closed_review",
        "position_lifecycle_ready_for_next_attempt_gate",
        "position_lifecycle_return_to_live_attempt_readiness",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
