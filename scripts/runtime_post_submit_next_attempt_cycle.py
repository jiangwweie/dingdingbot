#!/usr/bin/env python3
"""Run one non-executing post-submit -> next-attempt strategy cycle.

This is the RTF-030 lifecycle proof from the post-submit finalize mainline into the
fresh strategy-signal loop:

runtime latest durable submit result
-> post-submit finalize API
-> ready_for_fresh_signal gate
-> next-attempt strategy planning API

It never creates local orders, submits through OrderLifecycle, calls exchange,
opens or closes positions, transfers funds, or creates withdrawals.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import json
from pathlib import Path
import sys
from typing import Any, Callable

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import runtime_next_attempt_strategy_plan_api_flow as planning_flow  # noqa: E402
from scripts import runtime_post_submit_finalize_api_flow as finalize_flow  # noqa: E402


FinalizeBuilder = Callable[[argparse.Namespace], dict[str, Any]]
PlanningBuilder = Callable[[argparse.Namespace], dict[str, Any]]


READY_POST_SUBMIT_STATUS = "finalized_ready_for_next_attempt"
READY_PLANNING_STATUS = "ready_for_final_gate_preflight"
WAITING_PLANNING_STATUS = "waiting_for_signal"


def _load_json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("--metadata-json must be a JSON object")
    return value


def _safe_file_id(value: str) -> str:
    return (
        value.replace("/", "_")
        .replace(":", "_")
        .replace(" ", "_")
        .replace("\\", "_")
    )


def _output_paths(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    cycle_id = args.cycle_id or _safe_file_id(args.runtime_instance_id)
    return {
        "post_submit_finalize_flow": output_dir
        / f"{cycle_id}-post-submit-finalize-flow.json",
        "post_submit_finalize_payload": output_dir
        / f"{cycle_id}-post-submit-finalize-payload.json",
        "next_attempt_strategy_plan_flow": output_dir
        / f"{cycle_id}-next-attempt-strategy-plan-flow.json",
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )


def _finalize_args(args: argparse.Namespace) -> argparse.Namespace:
    metadata = {
        **_load_json_object(args.metadata_json),
        "runtime_post_submit_next_attempt_cycle": True,
        "cycle_stage": "post_submit_finalize",
    }
    return argparse.Namespace(
        runtime_instance_id=args.runtime_instance_id,
        reservation_id=args.reservation_id,
        authorization_id=args.authorization_id,
        closed_review_required=args.closed_review_required,
        protection_blocker=args.protection_blocker,
        env_file=args.env_file,
        api_base=args.api_base,
        metadata_json=json.dumps(metadata, ensure_ascii=False),
    )


def _planning_args(
    args: argparse.Namespace,
    *,
    post_submit_finalize_payload_json: Path,
) -> argparse.Namespace:
    metadata = {
        **_load_json_object(args.metadata_json),
        "runtime_post_submit_next_attempt_cycle": True,
        "cycle_stage": "next_attempt_strategy_planning",
    }
    return argparse.Namespace(
        runtime_instance_id=args.runtime_instance_id,
        post_submit_finalize_payload_json=str(post_submit_finalize_payload_json),
        signal_input_json=args.signal_input_json,
        env_file=args.env_file,
        api_base=args.api_base,
        context_id=args.context_id,
        expires_at_ms=args.expires_at_ms,
        metadata_json=json.dumps(metadata, ensure_ascii=False),
    )


def _safety() -> dict[str, bool]:
    return {
        "uses_official_trading_console_api": True,
        "non_executing": True,
        "pre_submit_rehearsal_called": False,
        "local_registration_armed": False,
        "exchange_submit_armed": False,
        "execute_real_submit": False,
        "exchange_write_called": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "attempt_counter_mutated_by_script": False,
        "runtime_budget_mutated_by_script": False,
        "position_opened": False,
        "position_closed": False,
        "withdrawal_or_transfer_created": False,
    }


def _status_from_planning(planning_status: str) -> str:
    if planning_status == READY_PLANNING_STATUS:
        return READY_PLANNING_STATUS
    if planning_status == WAITING_PLANNING_STATUS:
        return WAITING_PLANNING_STATUS
    return "blocked"


def _operator_next_step(status: str) -> str:
    if status == READY_PLANNING_STATUS:
        return "run_official_final_gate_preflight"
    if status == WAITING_PLANNING_STATUS:
        return "observe_or_wait_for_next_strategy_signal"
    return "resolve_post_submit_or_strategy_planning_blocker"


def _post_submit_payload(finalize_artifact: dict[str, Any]) -> dict[str, Any]:
    payload = finalize_artifact.get("post_submit_finalize_payload")
    if isinstance(payload, dict):
        return payload
    return {}


def _build_cycle_artifact(
    args: argparse.Namespace,
    *,
    finalize_builder: FinalizeBuilder | None = None,
    planning_builder: PlanningBuilder | None = None,
) -> dict[str, Any]:
    paths = _output_paths(args)
    finalize_builder = finalize_builder or finalize_flow._build_artifact
    planning_builder = planning_builder or planning_flow._build_artifact

    finalize_artifact = finalize_builder(_finalize_args(args))
    _write_json(paths["post_submit_finalize_flow"], finalize_artifact)

    post_submit = _post_submit_payload(finalize_artifact)
    _write_json(paths["post_submit_finalize_payload"], post_submit)

    finalize_status = str(finalize_artifact.get("status") or "")
    if finalize_status != READY_POST_SUBMIT_STATUS:
        blockers = list(finalize_artifact.get("blockers") or [])
        if not blockers:
            blockers.append("post_submit_finalize_not_ready_for_next_attempt")
        return {
            "scope": "runtime_post_submit_next_attempt_cycle",
            "status": "blocked",
            "blocked_stage": "post_submit_finalize",
            "runtime_instance_id": args.runtime_instance_id,
            "post_submit_finalize_flow": finalize_artifact,
            "next_attempt_strategy_plan_flow": None,
            "artifact_paths": {k: str(v) for k, v in paths.items()},
            "blockers": blockers,
            "warnings": list(finalize_artifact.get("warnings") or []),
            "next_attempt_cycle_plan": {
                "next_step": "resolve_post_submit_finalize_blocker",
                "creates_shadow_candidate": False,
                "creates_execution_intent": False,
                "places_order": False,
                "calls_order_lifecycle": False,
            },
            "safety_invariants": _safety(),
        }

    planning_artifact = planning_builder(
        _planning_args(
            args,
            post_submit_finalize_payload_json=paths["post_submit_finalize_payload"],
        )
    )
    _write_json(paths["next_attempt_strategy_plan_flow"], planning_artifact)

    planning_status = str(planning_artifact.get("status") or "")
    status = _status_from_planning(planning_status)
    planning_payload = planning_artifact.get("api_payload") or {}
    if not isinstance(planning_payload, dict):
        planning_payload = {}
    strategy_planning_plan = planning_payload.get("strategy_planning_plan") or {}
    if not isinstance(strategy_planning_plan, dict):
        strategy_planning_plan = {}
    blockers = list(planning_artifact.get("blockers") or [])
    if status == "blocked" and not blockers:
        blockers.append("next_attempt_strategy_planning_not_ready")
    return {
        "scope": "runtime_post_submit_next_attempt_cycle",
        "status": status,
        "blocked_stage": None if status != "blocked" else "next_attempt_strategy_planning",
        "runtime_instance_id": args.runtime_instance_id,
        "post_submit_finalize_flow": finalize_artifact,
        "next_attempt_strategy_plan_flow": planning_artifact,
        "artifact_paths": {k: str(v) for k, v in paths.items()},
        "signal_input_json": args.signal_input_json,
        "signal_evaluation_id": planning_payload.get("signal_evaluation_id"),
        "order_candidate_id": planning_payload.get("order_candidate_id"),
        "blockers": blockers,
        "warnings": list(finalize_artifact.get("warnings") or [])
        + list(planning_artifact.get("warnings") or []),
        "next_attempt_cycle_plan": {
            "next_step": _operator_next_step(status),
            "creates_shadow_candidate": bool(
                strategy_planning_plan.get("creates_shadow_candidate")
                or planning_payload.get("order_candidate_id")
            ),
            "creates_executable_execution_intent": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "requires_official_final_gate": status == READY_PLANNING_STATUS,
            "requires_fresh_authorization_before_submit": True,
        },
        "safety_invariants": _safety(),
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run one non-executing post-submit finalize to next-attempt "
            "strategy planning cycle."
        ),
    )
    parser.add_argument("--runtime-instance-id", required=True)
    parser.add_argument("--reservation-id")
    parser.add_argument("--signal-input-json", required=True)
    parser.add_argument("--authorization-id")
    parser.add_argument("--closed-review-required", action="store_true")
    parser.add_argument("--protection-blocker", action="append")
    parser.add_argument("--env-file")
    parser.add_argument("--api-base")
    parser.add_argument("--context-id")
    parser.add_argument("--expires-at-ms", type=int)
    parser.add_argument("--metadata-json")
    parser.add_argument(
        "--output-dir",
        default="output/runtime-post-submit-next-attempt-cycle",
    )
    parser.add_argument("--cycle-id")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    with redirect_stdout(sys.stderr):
        artifact = _build_cycle_artifact(args)
    print(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    )
    return 0 if artifact["status"] in {
        READY_PLANNING_STATUS,
        WAITING_PLANNING_STATUS,
        "blocked",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
