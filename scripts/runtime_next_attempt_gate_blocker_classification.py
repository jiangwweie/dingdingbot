#!/usr/bin/env python3
"""Classify a live next-attempt gate blocker from existing evidence.

RTF-095 consumes the RTF-094 live-attempt readiness evidence plus an optional
read-only live-position monitor projection. It never calls PG, exchange,
OrderLifecycle, or runtime mutation services.  Its purpose is to decide whether
``next_attempt_gate_blocked`` is a real active-position slot, a stale/unknown
projection issue, or a missing-facts problem.
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


def _runtime_row(
    readiness_artifact: dict[str, Any], runtime_instance_id: str
) -> dict[str, Any] | None:
    rows = readiness_artifact.get("runtime_readiness")
    if not isinstance(rows, list):
        return None
    for row in rows:
        if (
            isinstance(row, dict)
            and str(row.get("runtime_instance_id") or "") == runtime_instance_id
        ):
            return row
    return None


def _position_artifact(live_position_monitor: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(live_position_monitor, dict):
        return {}
    artifact = live_position_monitor.get("artifact")
    if isinstance(artifact, dict):
        return artifact
    return live_position_monitor


def _forbidden_effects(
    readiness_artifact: dict[str, Any],
    live_position_monitor: dict[str, Any] | None,
) -> dict[str, bool]:
    effects: dict[str, bool] = {key: False for key in FORBIDDEN_EFFECT_KEYS}
    safety = readiness_artifact.get("safety_invariants")
    if isinstance(safety, dict):
        nested = safety.get("forbidden_effects")
        if isinstance(nested, dict):
            for key in effects:
                effects[key] = effects[key] or bool(nested.get(key))
    monitor_safety = (
        live_position_monitor.get("safety_invariants")
        if isinstance(live_position_monitor, dict)
        else None
    )
    if isinstance(monitor_safety, dict):
        for key in effects:
            effects[key] = effects[key] or bool(monitor_safety.get(key))
    return effects


def _int_value(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _has_next_attempt_gate_blocker(row: dict[str, Any] | None) -> bool:
    if row is None:
        return False
    return "next_attempt_gate_blocked" in set(row.get("blockers") or [])


def _active_slot_in_use(position_artifact: dict[str, Any]) -> bool:
    if bool(position_artifact.get("active_position_present")):
        return True
    blockers = set(position_artifact.get("blockers") or [])
    if "runtime_max_active_positions_in_use" in blockers:
        return True
    local_count = _int_value(position_artifact.get("local_active_position_count"))
    exchange_count = _int_value(
        position_artifact.get("exchange_active_position_count")
    )
    max_active = _int_value(position_artifact.get("max_active_positions"))
    if max_active is None:
        max_active = 1
    return bool(
        (local_count is not None and local_count >= max_active)
        or (exchange_count is not None and exchange_count >= max_active)
    )


def _flat_position(position_artifact: dict[str, Any]) -> bool:
    if bool(position_artifact.get("active_position_present")):
        return False
    local_count = _int_value(position_artifact.get("local_active_position_count"))
    exchange_count = _int_value(
        position_artifact.get("exchange_active_position_count")
    )
    return local_count == 0 and exchange_count == 0


def _classification_status(
    *,
    row: dict[str, Any] | None,
    position_artifact: dict[str, Any],
    forbidden_effects: dict[str, bool],
) -> str:
    if any(forbidden_effects.values()):
        return "gate_blocker_classification_forbidden_effect"
    if row is None:
        return "gate_blocker_classification_runtime_not_monitored"
    if not _has_next_attempt_gate_blocker(row):
        return "gate_blocker_classification_no_next_attempt_gate_blocker"
    if not position_artifact:
        return "gate_blocker_classification_missing_position_facts"
    if _active_slot_in_use(position_artifact):
        return "gate_blocked_by_active_position_slot"
    if _flat_position(position_artifact):
        return "gate_blocked_by_stale_or_unresolved_next_attempt_projection"
    return "gate_blocked_by_unknown_position_state"


def _operator_plan(status: str, position_artifact: dict[str, Any]) -> dict[str, Any]:
    hard_stop = bool(position_artifact.get("hard_stop_boundary_present"))
    can_continue = bool(position_artifact.get("can_continue_holding"))
    if status == "gate_blocked_by_active_position_slot":
        if hard_stop and can_continue:
            next_step = "continue_read_only_position_monitoring_until_flat_or_signal_exit"
        elif not hard_stop:
            next_step = "repair_or_reduce_unprotected_position_before_next_attempt"
        else:
            next_step = "review_active_position_resolution_before_next_attempt"
    elif status == "gate_blocked_by_stale_or_unresolved_next_attempt_projection":
        next_step = "refresh_reconciliation_or_finalize_closed_review_before_next_attempt"
    elif status == "gate_blocker_classification_no_next_attempt_gate_blocker":
        next_step = "return_to_live_attempt_readiness_flow"
    elif status == "gate_blocker_classification_missing_position_facts":
        next_step = "collect_trusted_position_and_protection_facts"
    elif status == "gate_blocker_classification_forbidden_effect":
        next_step = "stop_and_review_forbidden_side_effects"
    else:
        next_step = "inspect_runtime_gate_facts_before_live_attempt"
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
        == "gate_blocker_classification_no_next_attempt_gate_blocker",
        "requires_owner_close_authorization_now": bool(
            status == "gate_blocked_by_active_position_slot"
            and not hard_stop
        ),
        "uses_legacy_pre_attempt_rehearsal_as_primary_gate": False,
    }


def build_classification_artifact(
    *,
    readiness_artifact: dict[str, Any],
    runtime_instance_id: str,
    live_position_monitor: dict[str, Any] | None = None,
    deployed_head: str | None = None,
    release_name: str | None = None,
    remote_report_path: str | None = None,
) -> dict[str, Any]:
    row = _runtime_row(readiness_artifact, runtime_instance_id)
    position = _position_artifact(live_position_monitor)
    effects = _forbidden_effects(readiness_artifact, live_position_monitor)
    status = _classification_status(
        row=row,
        position_artifact=position,
        forbidden_effects=effects,
    )
    warnings = []
    if row is not None:
        warnings.extend(row.get("warnings") or [])
    warnings.extend(position.get("warnings") or [])
    blockers = []
    if row is not None:
        blockers.extend(row.get("blockers") or [])
    blockers.extend(position.get("blockers") or [])

    return {
        "scope": "runtime_next_attempt_gate_blocker_classification",
        "status": status,
        "runtime_instance_id": runtime_instance_id,
        "source_readiness_status": readiness_artifact.get("status"),
        "source_runtime_status": row.get("status") if row else None,
        "has_next_attempt_gate_blocker": _has_next_attempt_gate_blocker(row),
        "blockers": blockers,
        "warnings": warnings,
        "runtime_readiness_row": row or {},
        "position_facts": {
            "status": position.get("status"),
            "active_position_present": bool(position.get("active_position_present")),
            "symbol": position.get("symbol"),
            "side": position.get("side"),
            "current_qty": position.get("current_qty"),
            "entry_price": position.get("entry_price"),
            "mark_price": position.get("mark_price"),
            "unrealized_pnl": position.get("unrealized_pnl"),
            "local_active_position_count": position.get(
                "local_active_position_count"
            ),
            "exchange_active_position_count": position.get(
                "exchange_active_position_count"
            ),
            "max_active_positions": position.get("max_active_positions"),
            "local_open_order_count": position.get("local_open_order_count"),
            "exchange_open_stop_order_count": position.get(
                "exchange_open_stop_order_count"
            ),
            "protection_status": position.get("protection_status"),
            "sl_protection_present": bool(position.get("sl_protection_present")),
            "tp_protection_present": bool(position.get("tp_protection_present")),
            "hard_stop_boundary_present": bool(
                position.get("hard_stop_boundary_present")
            ),
            "can_continue_holding": bool(position.get("can_continue_holding")),
            "attempts_used": position.get("attempts_used"),
            "attempts_remaining": position.get("attempts_remaining"),
            "budget_reserved": position.get("budget_reserved"),
            "budget_remaining": position.get("budget_remaining"),
            "reconciliation_mismatch_types": list(
                position.get("reconciliation_mismatch_types") or []
            ),
            "reconciliation_warning_count": position.get(
                "reconciliation_warning_count"
            ),
            "reconciliation_severe_count": position.get(
                "reconciliation_severe_count"
            ),
        },
        "safety_invariants": {
            "gate_blocker_classification_projection_only": True,
            "no_forbidden_live_side_effects": not any(effects.values()),
            "forbidden_effects": effects,
            "pg_called_by_classifier": False,
            "exchange_called_by_classifier": False,
            "exchange_write_called_by_classifier": False,
            "order_lifecycle_called_by_classifier": False,
            "runtime_state_mutated_by_classifier": False,
            "withdrawal_or_transfer_created_by_classifier": False,
        },
        "next_attempt_gate_blocker_plan": _operator_plan(status, position),
        "deployment_context": {
            "deployed_head": deployed_head,
            "release_name": release_name,
            "remote_report_path": remote_report_path,
        },
        "right_tail_objective_context": {
            "active_position_slot_blocks_new_attempt_not_current_hold": True,
            "hard_stop_only_is_warning_not_runaway_if_boundary_present": bool(
                position.get("hard_stop_boundary_present")
                and not position.get("tp_protection_present")
            ),
            "small_bounded_losses_allowed_after_runtime_gate": True,
            "automatic_withdrawal_assumed": False,
            "automatic_compounding_assumed": False,
        },
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify next-attempt gate blocker from readiness evidence.",
    )
    parser.add_argument("--readiness-json", required=True)
    parser.add_argument("--runtime-instance-id", required=True)
    parser.add_argument("--live-position-monitor-json")
    parser.add_argument("--deployed-head")
    parser.add_argument("--release-name")
    parser.add_argument("--remote-report-path")
    parser.add_argument("--output-json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    artifact = build_classification_artifact(
        readiness_artifact=_read_json(args.readiness_json),
        runtime_instance_id=args.runtime_instance_id,
        live_position_monitor=(
            _read_json(args.live_position_monitor_json)
            if args.live_position_monitor_json
            else None
        ),
        deployed_head=args.deployed_head,
        release_name=args.release_name,
        remote_report_path=args.remote_report_path,
    )
    if args.output_json:
        _write_json(args.output_json, artifact)
    print(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if artifact["status"] in {
        "gate_blocker_classification_no_next_attempt_gate_blocker",
        "gate_blocked_by_active_position_slot",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
