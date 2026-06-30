#!/usr/bin/env python3
"""Monitor runtime next-attempt observation readiness without submitting orders.

The monitor wraps ``runtime_next_attempt_observation_api_prepare_flow`` and is
intended for the flat-after-close waiting period: keep checking for a fresh
strategy signal, then stop with a clear operator artifact when the official
prepare flow can be run. By default it does not create prepare records.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import copy
import json
from pathlib import Path
import sys
import time
from typing import Any, Callable

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import runtime_next_attempt_observation_api_prepare_flow as observation_flow  # noqa: E402


READY_STATUSES = {"ready_for_prepare", "ready_for_final_gate_preflight"}
CONTINUE_STATUSES = {"waiting_for_signal"}


def _safety(artifact: dict[str, Any] | None = None) -> dict[str, Any]:
    inner = artifact.get("safety_invariants") if isinstance(artifact, dict) else None
    if isinstance(inner, dict):
        safety = dict(inner)
    else:
        safety = {}
    safety.update(
        {
            "monitor_only": True,
            "local_registration_armed": False,
            "exchange_submit_armed": False,
            "execute_real_submit": False,
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "position_opened": False,
            "withdrawal_or_transfer_created": False,
        }
    )
    return safety


def _cycle_summary(*, cycle_index: int, artifact: dict[str, Any]) -> dict[str, Any]:
    observation_plan = artifact.get("observation_cycle_plan")
    if not isinstance(observation_plan, dict):
        observation_plan = {}
    return {
        "cycle_index": cycle_index,
        "status": artifact.get("status") or "unknown",
        "blocked_stage": artifact.get("blocked_stage"),
        "blockers": list(artifact.get("blockers") or []),
        "warnings": list(artifact.get("warnings") or []),
        "signal_input_json": artifact.get("signal_input_json"),
        "next_step": observation_plan.get("next_step"),
        "prepared_authorization_id": observation_plan.get("prepared_authorization_id"),
    }


def _blocked_exception_artifact(*, error: Exception) -> dict[str, Any]:
    error_name = type(error).__name__
    return {
        "status": "blocked",
        "blocked_stage": "observation_cycle_exception",
        "blockers": [f"observation_cycle_exception:{error_name}"],
        "warnings": [],
        "observation_cycle_plan": {
            "next_step": "resolve_observation_cycle_exception",
            "not_executed": True,
            "creates_shadow_candidate": False,
            "creates_execution_intent": False,
            "places_order": False,
            "calls_order_lifecycle": False,
        },
        "safety_invariants": _safety(),
        "exception": {
            "type": error_name,
            "message": str(error),
        },
    }


def _build_monitor_artifact(
    args: argparse.Namespace,
    *,
    artifact_builder: Callable[[argparse.Namespace], dict[str, Any]] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    builder = artifact_builder or observation_flow._build_artifact
    max_cycles = max(int(args.max_cycles or 1), 1)
    cycle_artifacts: list[dict[str, Any]] = []
    cycle_summaries: list[dict[str, Any]] = []

    for index in range(max_cycles):
        cycle_args = copy.copy(args)
        try:
            artifact = builder(cycle_args)
        except Exception as exc:
            artifact = _blocked_exception_artifact(error=exc)
        cycle_artifacts.append(artifact)
        cycle_summaries.append(_cycle_summary(cycle_index=index + 1, artifact=artifact))

        status = str(artifact.get("status") or "unknown")
        if status in READY_STATUSES:
            break
        if not args.continue_on_blocked and status not in CONTINUE_STATUSES:
            break
        if index + 1 < max_cycles:
            sleeper(float(args.interval_seconds or 0))

    latest = cycle_artifacts[-1] if cycle_artifacts else {}
    latest_status = str(latest.get("status") or "unknown")
    ready = latest_status in READY_STATUSES
    exhausted_wait = (
        latest_status in CONTINUE_STATUSES and len(cycle_artifacts) >= max_cycles
    )
    status = latest_status
    if exhausted_wait:
        status = "waiting_for_signal"

    observation_monitor_plan = {
        "next_step": "wait_for_next_observation_cycle",
        "not_executed": True,
        "creates_shadow_candidate": False,
        "creates_execution_intent": False,
        "places_order": False,
        "calls_order_lifecycle": False,
        "requires_official_final_gate": True,
        "uses_standing_runtime_authorization": True,
        "requires_explicit_owner_real_submit_authorization": False,
        "requires_official_operation_layer": True,
    }
    if ready:
        latest_plan = latest.get("observation_cycle_plan")
        if not isinstance(latest_plan, dict):
            latest_plan = {}
        observation_monitor_plan.update(
            {
                "next_step": latest_plan.get("next_step")
                or "review_ready_observation_and_run_official_prepare_flow",
                "signal_input_json": latest.get("signal_input_json"),
                "prepared_authorization_id": latest_plan.get(
                    "prepared_authorization_id"
                ),
                "creates_shadow_candidate": bool(
                    latest.get("safety_invariants", {}).get("prepare_records_created")
                ),
            }
        )
    elif latest_status not in CONTINUE_STATUSES:
        observation_monitor_plan["next_step"] = "resolve_latest_observation_blocker"

    return {
        "scope": "runtime_next_attempt_observation_monitor",
        "status": status,
        "runtime_instance_id": args.runtime_instance_id,
        "cycles_requested": max_cycles,
        "cycles_completed": len(cycle_artifacts),
        "interval_seconds": float(args.interval_seconds or 0),
        "ready_for_prepare": latest_status == "ready_for_prepare",
        "ready_for_final_gate_preflight": latest_status
        == "ready_for_final_gate_preflight",
        "latest_artifact": latest,
        "cycle_summaries": cycle_summaries,
        "blockers": list(latest.get("blockers") or []),
        "warnings": list(latest.get("warnings") or []),
        "observation_monitor_plan": observation_monitor_plan,
        "safety_invariants": _safety(latest),
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Monitor runtime next-attempt observation readiness without live submit."
        ),
        add_help=False,
    )
    parser.add_argument("--max-cycles", type=int, default=1)
    parser.add_argument("--interval-seconds", type=float, default=0.0)
    parser.add_argument("--continue-on-blocked", action="store_true", default=False)
    parser.add_argument(
        "--output-json",
        help="Optional path for the monitor artifact. Stdout remains JSON.",
    )

    monitor, base_argv = parser.parse_known_args(argv)
    base = observation_flow._parse_args(base_argv)
    for key, value in vars(monitor).items():
        setattr(base, key, value)
    return base


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    with redirect_stdout(sys.stderr):
        payload = _build_monitor_artifact(args)
    output = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    if args.output_json:
        output_path = Path(args.output_json).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0 if payload["status"] in {
        "waiting_for_signal",
        "ready_for_prepare",
        "ready_for_final_gate_preflight",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
