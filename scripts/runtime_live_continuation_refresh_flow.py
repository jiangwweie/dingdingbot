#!/usr/bin/env python3
"""Refresh live runtime continuation from active-monitor evidence.

RTF-098 is a projection-only orchestration flow:

active runtime observation monitor JSON
-> live-attempt readiness artifact
-> continuation selector projection

Optional per-runtime lifecycle artifacts may be supplied to enrich blocked runtime
decisions, such as the BNB position lifecycle artifact from RTF-096.  The flow
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

from scripts import runtime_live_attempt_readiness_artifact as readiness  # noqa: E402
from scripts import runtime_live_continuation_selector_projection as selector  # noqa: E402


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


def _forbidden_effects(*artifacts: dict[str, Any] | None) -> dict[str, bool]:
    effects = {key: False for key in FORBIDDEN_EFFECT_KEYS}
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        safety = artifact.get("safety_invariants")
        if not isinstance(safety, dict):
            continue
        nested = safety.get("forbidden_effects")
        if isinstance(nested, dict):
            for key in effects:
                effects[key] = effects[key] or bool(nested.get(key))
        for key in effects:
            effects[key] = effects[key] or bool(safety.get(key))
    return effects


def _status(selector_projection: dict[str, Any], effects: dict[str, bool]) -> str:
    if any(effects.values()):
        return "continuation_refresh_blocked_forbidden_effect"
    selector_status = str(selector_projection.get("status") or "")
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


def _refresh_plan(status: str, selector_projection: dict[str, Any]) -> dict[str, Any]:
    selector_plan = selector_projection.get("selector_plan")
    if not isinstance(selector_plan, dict):
        selector_plan = {}
    return {
        "not_execution_authority": True,
        "next_step": selector_plan.get("next_step") or "review_selector_projection",
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


def build_refresh_flow_artifacts(
    *,
    active_monitor_artifact: dict[str, Any],
    lifecycle_artifacts: list[dict[str, Any]] | None = None,
    deployed_head: str | None = None,
    release_name: str | None = None,
    remote_report_path: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    lifecycle_artifacts = list(lifecycle_artifacts or [])
    readiness_artifact = readiness.build_readiness_artifact(
        active_monitor_artifact=active_monitor_artifact,
        deployed_head=deployed_head,
        release_name=release_name,
        remote_report_path=remote_report_path,
    )
    selector_projection = selector.build_selector_projection(
        readiness_artifact=readiness_artifact,
        lifecycle_artifacts=lifecycle_artifacts,
        deployed_head=deployed_head,
        release_name=release_name,
        remote_report_path=remote_report_path,
    )
    effects = _forbidden_effects(
        active_monitor_artifact,
        readiness_artifact,
        selector_projection,
        *lifecycle_artifacts,
    )
    status = _status(selector_projection, effects)
    refresh_artifact = {
        "scope": "runtime_live_continuation_refresh_flow",
        "status": status,
        "source_monitor_status": active_monitor_artifact.get("status"),
        "readiness_status": readiness_artifact.get("status"),
        "selector_status": selector_projection.get("status"),
        "active_runtime_count": readiness_artifact.get("active_runtime_count"),
        "monitored_runtime_count": readiness_artifact.get("monitored_runtime_count"),
        "selected_continuation": selector_projection.get("selected_continuation") or {},
        "runtime_continuation_count": len(
            selector_projection.get("runtime_continuations") or []
        ),
        "blockers": list(selector_projection.get("blockers") or []),
        "warnings": list(selector_projection.get("warnings") or []),
        "safety_invariants": {
            "projection_only": True,
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
        "refresh_plan": _refresh_plan(status, selector_projection),
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
                    selector_projection.get("right_tail_objective_context") or {}
                ).get("bounded_active_position_may_continue")
            ),
            "new_attempt_not_started_by_refresh_flow": True,
            "owner_manual_close_is_optional_not_automatic": True,
            "automatic_withdrawal_assumed": False,
            "automatic_compounding_assumed": False,
        },
    }
    return refresh_artifact, readiness_artifact, selector_projection


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build selector-driven live continuation refresh artifact.",
    )
    parser.add_argument("--active-monitor-json", required=True)
    parser.add_argument(
        "--lifecycle-json",
        action="append",
        default=[],
        help="Optional per-runtime lifecycle artifact. May be repeated.",
    )
    parser.add_argument("--deployed-head")
    parser.add_argument("--release-name")
    parser.add_argument("--remote-report-path")
    parser.add_argument("--output-dir")
    parser.add_argument("--output-json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    refresh_artifact, readiness_artifact, selector_projection = build_refresh_flow_artifacts(
        active_monitor_artifact=_load_report(args.active_monitor_json),
        lifecycle_artifacts=[
            _load_report(path)
            for path in (args.lifecycle_json or [])
        ],
        deployed_head=args.deployed_head,
        release_name=args.release_name,
        remote_report_path=args.remote_report_path,
    )
    if args.output_dir:
        output_dir = Path(args.output_dir).expanduser()
        _write_json(output_dir / "live-attempt-readiness-artifact.json", readiness_artifact)
        _write_json(output_dir / "live-continuation-selector-projection.json", selector_projection)
        _write_json(output_dir / "live-continuation-refresh-flow.json", refresh_artifact)
    if args.output_json:
        _write_json(args.output_json, refresh_artifact)
    print(json.dumps(refresh_artifact, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if refresh_artifact["status"] in {
        "continuation_refresh_monitor_position_or_standing_recovery",
        "continuation_refresh_monitor_position_or_owner_close",
        "continuation_refresh_ready_for_final_gate_review",
        "continuation_refresh_ready_for_prepare",
        "continuation_refresh_waiting_for_strategy_signal",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
