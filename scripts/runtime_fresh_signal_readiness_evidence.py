#!/usr/bin/env python3
"""Project fresh-signal readiness into executable readiness evidence.

RTF-057 starts from an RTF-056 fresh-signal prepare loop artifact:

fresh-signal loop ready signal
-> next-attempt strategy planning API
-> executable submit readiness preview
-> optional official submit handoff preview

The script is deliberately non-executing. It does not call the official submit
endpoint, arm local registration, arm exchange submit, submit through
OrderLifecycle, place exchange orders, open/close positions, transfer funds, or
create withdrawals.
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

from scripts import runtime_cycle_executable_submit_handoff as handoff_projection  # noqa: E402
from scripts import runtime_next_attempt_strategy_plan_api_flow as planning_flow  # noqa: E402


PlanningBuilder = Callable[[argparse.Namespace], dict[str, Any]]
HandoffBuilder = Callable[[argparse.Namespace], dict[str, Any]]


READY_FOR_PREPARE = "ready_for_prepare"
READY_FOR_FINAL_GATE_PREFLIGHT = "ready_for_final_gate_preflight"
WAITING_FOR_SIGNAL = "waiting_for_signal"
READY_FOR_FRESH_SUBMIT_AUTHORIZATION = "ready_for_fresh_submit_authorization"
READY_FOR_OFFICIAL_SUBMIT_CALL = "ready_for_official_submit_call"
READY_FOR_READINESS_EVIDENCE = "ready_for_readiness_evidence"


def _safe_file_id(value: str) -> str:
    return (
        value.replace("/", "_")
        .replace(":", "_")
        .replace(" ", "_")
        .replace("\\", "_")
    )


def _read_json_file(path: str) -> dict[str, Any]:
    payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _output_paths(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    flow_id = args.flow_id or _safe_file_id(args.runtime_instance_id)
    return {
        "post_submit_finalize_payload": output_dir
        / f"{flow_id}-post-submit-finalize-payload.json",
        "signal_input": output_dir / f"{flow_id}-signal-input.json",
        "next_attempt_strategy_plan_flow": output_dir
        / f"{flow_id}-next-attempt-strategy-plan-flow.json",
        "cycle_adapter_artifact": output_dir / f"{flow_id}-cycle-adapter-artifact.json",
        "readiness_handoff_evidence": output_dir
        / f"{flow_id}-readiness-handoff-evidence.json",
    }


def _fresh_loop_status(fresh_loop: dict[str, Any]) -> str:
    return str(fresh_loop.get("status") or "")


def _post_submit_payload(fresh_loop: dict[str, Any]) -> dict[str, Any]:
    direct = fresh_loop.get("post_submit_finalize_payload")
    if isinstance(direct, dict):
        return direct
    flow = fresh_loop.get("post_submit_finalize_flow")
    if not isinstance(flow, dict):
        return {}
    nested = flow.get("post_submit_finalize_payload")
    if isinstance(nested, dict):
        return nested
    payload = flow.get("api_payload")
    return payload if isinstance(payload, dict) else {}


def _signal_input_from_loop(
    fresh_loop: dict[str, Any],
    *,
    output_path: Path,
) -> tuple[dict[str, Any], str | None]:
    path_value = fresh_loop.get("signal_input_json")
    if not path_value:
        observation = fresh_loop.get("observation_prepare_flow")
        if isinstance(observation, dict):
            path_value = observation.get("signal_input_json")
    if path_value:
        signal_path = Path(str(path_value)).expanduser()
        if signal_path.exists():
            return _read_json_file(str(signal_path)), str(signal_path)

    observation = fresh_loop.get("observation_prepare_flow")
    payload = (
        observation.get("observation_payload")
        if isinstance(observation, dict)
        else None
    )
    signal_artifact = (
        payload.get("signal_artifact") if isinstance(payload, dict) else None
    )
    signal_input = (
        signal_artifact.get("signal_input")
        if isinstance(signal_artifact, dict)
        else None
    )
    if isinstance(signal_input, dict):
        _write_json(output_path, signal_input)
        return signal_input, str(output_path)
    return {}, str(path_value) if path_value else None


def _planning_args(
    args: argparse.Namespace,
    *,
    post_submit_finalize_payload_json: Path,
    signal_input_json: str,
) -> argparse.Namespace:
    return argparse.Namespace(
        runtime_instance_id=args.runtime_instance_id,
        post_submit_finalize_payload_json=str(post_submit_finalize_payload_json),
        signal_input_json=signal_input_json,
        env_file=args.env_file,
        api_base=args.api_base,
        context_id=args.context_id,
        expires_at_ms=args.expires_at_ms,
        metadata_json=args.metadata_json,
    )


def _cycle_artifact(
    *,
    args: argparse.Namespace,
    fresh_loop: dict[str, Any],
    planning_artifact: dict[str, Any],
) -> dict[str, Any]:
    status = str(planning_artifact.get("status") or "")
    blockers = list(planning_artifact.get("blockers") or [])
    if status != READY_FOR_FINAL_GATE_PREFLIGHT and not blockers:
        blockers.append("next_attempt_strategy_planning_not_ready")
    return {
        "scope": "runtime_fresh_signal_readiness_evidence_cycle_adapter",
        "status": status if status == READY_FOR_FINAL_GATE_PREFLIGHT else "blocked",
        "blocked_stage": None
        if status == READY_FOR_FINAL_GATE_PREFLIGHT
        else "next_attempt_strategy_planning",
        "runtime_instance_id": args.runtime_instance_id,
        "fresh_signal_prepare_loop": fresh_loop,
        "next_attempt_strategy_plan_flow": planning_artifact,
        "blockers": blockers,
        "warnings": list(fresh_loop.get("warnings") or [])
        + list(planning_artifact.get("warnings") or []),
        "fresh_signal_cycle_adapter_plan": {
            "next_step": "run_executable_submit_readiness",
            "adapter_source": "runtime_fresh_signal_prepare_loop",
            "creates_executable_execution_intent": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "requires_fresh_authorization_before_submit": True,
        },
    }


def _handoff_args(
    args: argparse.Namespace,
    *,
    cycle_artifact_json: Path,
) -> argparse.Namespace:
    return argparse.Namespace(
        runtime_instance_id=args.runtime_instance_id,
        cycle_artifact_json=str(cycle_artifact_json),
        evidence_json=args.evidence_json,
        first_real_submit_evidence_json=args.first_real_submit_evidence_json,
        fresh_submit_authorization_id=args.fresh_submit_authorization_id,
        mode=args.mode,
        owner_confirmed_for_real_submit_action=(
            args.owner_confirmed_for_real_submit_action
        ),
        readiness_warning=args.readiness_warning,
        readiness_blocker=args.readiness_blocker,
        handoff_warning=args.handoff_warning,
        handoff_blocker=args.handoff_blocker,
        env_file=args.env_file,
        api_base=args.api_base,
        output_dir=args.output_dir,
        flow_id=f"{args.flow_id or _safe_file_id(args.runtime_instance_id)}-handoff",
    )


def _safety() -> dict[str, bool]:
    return {
        "uses_official_trading_console_api": True,
        "non_executing": True,
        "calls_official_submit_endpoint": False,
        "pre_submit_rehearsal_called": False,
        "local_registration_armed": False,
        "exchange_submit_armed": False,
        "execute_real_submit": False,
        "pg_write_by_script": False,
        "execution_intent_created_by_script": False,
        "executable_execution_intent_created": False,
        "exchange_write_called": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "attempt_counter_mutated_by_script": False,
        "runtime_budget_mutated_by_script": False,
        "position_opened": False,
        "position_closed": False,
        "withdrawal_or_transfer_created": False,
    }


def _base_evidence(
    *,
    args: argparse.Namespace,
    status: str,
    fresh_loop: dict[str, Any] | None,
    blockers: list[str] | None = None,
    warnings: list[str] | None = None,
    paths: dict[str, Path] | None = None,
    blocked_stage: str | None = None,
    next_step: str,
) -> dict[str, Any]:
    return {
        "scope": "runtime_fresh_signal_readiness_evidence",
        "status": status,
        "blocked_stage": blocked_stage,
        "runtime_instance_id": args.runtime_instance_id,
        "fresh_signal_prepare_loop": fresh_loop,
        "next_attempt_strategy_plan_flow": None,
        "readiness_handoff_evidence": None,
        "artifact_paths": {key: str(value) for key, value in (paths or {}).items()},
        "blockers": blockers or [],
        "warnings": warnings or [],
        "fresh_signal_readiness_plan": {
            "next_step": next_step,
            "creates_executable_execution_intent": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "requires_fresh_authorization_before_submit": True,
        },
        "safety_invariants": _safety(),
    }


def _build_evidence(
    args: argparse.Namespace,
    *,
    planning_builder: PlanningBuilder | None = None,
    handoff_builder: HandoffBuilder | None = None,
) -> dict[str, Any]:
    paths = _output_paths(args)
    fresh_loop = _read_json_file(args.fresh_signal_loop_json)
    fresh_status = _fresh_loop_status(fresh_loop)

    if fresh_status == WAITING_FOR_SIGNAL:
        return _base_evidence(
            args=args,
            status=WAITING_FOR_SIGNAL,
            fresh_loop=fresh_loop,
            blockers=list(fresh_loop.get("blockers") or []),
            warnings=list(fresh_loop.get("warnings") or []),
            paths=paths,
            next_step="continue_observation_until_fresh_runtime_signal",
        )

    if fresh_status not in {READY_FOR_PREPARE, READY_FOR_FINAL_GATE_PREFLIGHT}:
        blockers = list(fresh_loop.get("blockers") or [])
        if not blockers:
            blockers.append("fresh_signal_loop_not_ready_for_readiness_evidence")
        return _base_evidence(
            args=args,
            status="blocked",
            blocked_stage="fresh_signal_prepare_loop",
            fresh_loop=fresh_loop,
            blockers=blockers,
            warnings=list(fresh_loop.get("warnings") or []),
            paths=paths,
            next_step="resolve_fresh_signal_prepare_loop_blocker",
        )

    if not args.evidence_json:
        return _base_evidence(
            args=args,
            status=READY_FOR_READINESS_EVIDENCE,
            fresh_loop=fresh_loop,
            warnings=list(fresh_loop.get("warnings") or []),
            paths=paths,
            next_step="provide_readiness_evidence_json",
        )

    post_submit = _post_submit_payload(fresh_loop)
    if not post_submit:
        return _base_evidence(
            args=args,
            status="blocked",
            blocked_stage="post_submit_finalize_payload",
            fresh_loop=fresh_loop,
            blockers=["post_submit_finalize_payload_missing_from_fresh_signal_loop"],
            warnings=list(fresh_loop.get("warnings") or []),
            paths=paths,
            next_step="rerun_fresh_signal_prepare_loop_with_post_submit_payload",
        )
    _write_json(paths["post_submit_finalize_payload"], post_submit)

    signal_input, signal_input_json = _signal_input_from_loop(
        fresh_loop,
        output_path=paths["signal_input"],
    )
    if not signal_input or not signal_input_json:
        return _base_evidence(
            args=args,
            status="blocked",
            blocked_stage="signal_input",
            fresh_loop=fresh_loop,
            blockers=["signal_input_missing_from_fresh_signal_loop"],
            warnings=list(fresh_loop.get("warnings") or []),
            paths=paths,
            next_step="rerun_fresh_signal_prepare_loop_until_signal_input_is_available",
        )

    planning_builder = planning_builder or planning_flow._build_artifact
    handoff_builder = handoff_builder or handoff_projection._build_artifact
    planning_artifact = planning_builder(
        _planning_args(
            args,
            post_submit_finalize_payload_json=paths["post_submit_finalize_payload"],
            signal_input_json=signal_input_json,
        )
    )
    _write_json(paths["next_attempt_strategy_plan_flow"], planning_artifact)
    planning_status = str(planning_artifact.get("status") or "")
    if planning_status != READY_FOR_FINAL_GATE_PREFLIGHT:
        blockers = list(planning_artifact.get("blockers") or [])
        if not blockers:
            blockers.append("next_attempt_strategy_planning_not_ready")
        return {
            **_base_evidence(
                args=args,
                status="blocked",
                blocked_stage="next_attempt_strategy_planning",
                fresh_loop=fresh_loop,
                blockers=blockers,
                warnings=list(fresh_loop.get("warnings") or [])
                + list(planning_artifact.get("warnings") or []),
                paths=paths,
                next_step="resolve_next_attempt_strategy_planning_blocker",
            ),
            "next_attempt_strategy_plan_flow": planning_artifact,
        }

    cycle_artifact = _cycle_artifact(
        args=args,
        fresh_loop=fresh_loop,
        planning_artifact=planning_artifact,
    )
    _write_json(paths["cycle_adapter_artifact"], cycle_artifact)

    handoff_artifact = handoff_builder(
        _handoff_args(args, cycle_artifact_json=paths["cycle_adapter_artifact"])
    )
    _write_json(paths["readiness_handoff_evidence"], handoff_artifact)
    status = str(handoff_artifact.get("status") or "blocked")
    return {
        "scope": "runtime_fresh_signal_readiness_evidence",
        "status": status,
        "blocked_stage": handoff_artifact.get("blocked_stage"),
        "runtime_instance_id": args.runtime_instance_id,
        "fresh_signal_prepare_loop": fresh_loop,
        "next_attempt_strategy_plan_flow": planning_artifact,
        "cycle_adapter_artifact": cycle_artifact,
        "readiness_handoff_evidence": handoff_artifact,
        "artifact_paths": {key: str(value) for key, value in paths.items()},
        "blockers": list(handoff_artifact.get("blockers") or []),
        "warnings": list(fresh_loop.get("warnings") or [])
        + list(planning_artifact.get("warnings") or [])
        + list(handoff_artifact.get("warnings") or []),
        "operator_action_preview": handoff_artifact.get("operator_action_preview"),
        "fresh_signal_readiness_plan": {
            "next_step": (
                "bind_or_resolve_fresh_submit_authorization"
                if status == READY_FOR_FRESH_SUBMIT_AUTHORIZATION
                else "call_official_submit_endpoint_after_action_time_final_gate_and_operation_layer_pass"
                if status == READY_FOR_OFFICIAL_SUBMIT_CALL
                else "resolve_readiness_evidence_blocker"
            ),
            "creates_executable_execution_intent": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "requires_fresh_authorization_before_submit": True,
            "requires_owner_chat_confirmation": False,
            "uses_standing_runtime_authorization": (
                status == READY_FOR_OFFICIAL_SUBMIT_CALL
            ),
            "requires_action_time_final_gate": (
                status == READY_FOR_OFFICIAL_SUBMIT_CALL
            ),
            "requires_official_operation_layer": (
                status == READY_FOR_OFFICIAL_SUBMIT_CALL
            ),
            "can_continue_without_owner_chat": (
                status == READY_FOR_OFFICIAL_SUBMIT_CALL
            ),
            "requires_action_time_confirmation": False,
        },
        "safety_invariants": _safety(),
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Project a fresh-signal prepare loop artifact into executable "
            "readiness and optional official submit handoff preview."
        ),
    )
    parser.add_argument("--runtime-instance-id", required=True)
    parser.add_argument("--fresh-signal-loop-json", required=True)
    parser.add_argument("--evidence-json")
    parser.add_argument("--first-real-submit-evidence-json")
    parser.add_argument("--fresh-submit-authorization-id")
    parser.add_argument(
        "--mode",
        choices=("disabled_smoke", "real_gateway_action"),
        default="disabled_smoke",
    )
    parser.add_argument(
        "--owner-confirmed-for-real-submit-action",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Standing authorization flag for real_gateway_action handoff "
            "(default: true)."
        ),
    )
    parser.add_argument("--readiness-warning", action="append")
    parser.add_argument("--readiness-blocker", action="append")
    parser.add_argument("--handoff-warning", action="append")
    parser.add_argument("--handoff-blocker", action="append")
    parser.add_argument("--env-file")
    parser.add_argument("--api-base")
    parser.add_argument("--context-id")
    parser.add_argument("--expires-at-ms", type=int)
    parser.add_argument("--metadata-json")
    parser.add_argument(
        "--output-dir",
        default="output/runtime-fresh-signal-readiness-evidence",
    )
    parser.add_argument("--flow-id")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    with redirect_stdout(sys.stderr):
        evidence = _build_evidence(args)
    print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if evidence["status"] in {
        WAITING_FOR_SIGNAL,
        READY_FOR_READINESS_EVIDENCE,
        READY_FOR_FRESH_SUBMIT_AUTHORIZATION,
        READY_FOR_OFFICIAL_SUBMIT_CALL,
        "blocked",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
