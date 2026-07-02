#!/usr/bin/env python3
"""Build a live-signal shadow planning projection.

RTF-073 consumes an RTF-067 operator cycle or RTF-069 supervisor artifact and only
calls the existing next-attempt strategy planning API flow when the live signal
path has stopped at a current-runtime ``ready_for_prepare`` review point. The
projection does not run prepare records, create ExecutionIntent records, arm submit,
call OrderLifecycle, write exchange state, mutate runtime budget, or move funds.
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


PlanningBuilder = Callable[[argparse.Namespace], dict[str, Any]]

READY_FOR_PREPARE = "ready_for_prepare"
SUPERVISOR_PREPARE_REVIEW = "supervisor_prepare_review_required"
READY_FOR_FINAL_GATE_PREFLIGHT = "ready_for_final_gate_preflight"
SUPERVISOR_FINAL_GATE_REVIEW = "supervisor_final_gate_review_required"
WAITING_CYCLE = "waiting_for_runtime_compatible_signal"
WAITING_SUPERVISOR = "supervisor_waiting_for_signal"
PROFILE_CYCLE = "ready_for_owner_runtime_profile_decision"
PROFILE_SUPERVISOR = "supervisor_profile_review_required"


def _read_json(path: str) -> dict[str, Any]:
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
    flow_id = args.flow_id or _safe_file_id(args.runtime_instance_id)
    return {
        "strategy_planning_flow": output_dir
        / f"{flow_id}-strategy-planning-flow.json",
    }


def _source_evidence_status(source_artifact: dict[str, Any]) -> str:
    return str(source_artifact.get("status") or "")


def _source_evidence_scope(source_artifact: dict[str, Any]) -> str:
    return str(source_artifact.get("scope") or "")


def _latest_cycle(source_artifact: dict[str, Any]) -> dict[str, Any]:
    cycles = source_artifact.get("cycle_summaries")
    if isinstance(cycles, list) and cycles and isinstance(cycles[-1], dict):
        return cycles[-1]
    return {}


def _signal_input_json(source_artifact: dict[str, Any]) -> str | None:
    value = source_artifact.get("signal_input_json")
    if isinstance(value, str) and value.strip():
        return value.strip()
    latest = _latest_cycle(source_artifact)
    value = latest.get("signal_input_json")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _forbidden_effects(source_artifact: dict[str, Any]) -> list[str]:
    effects: list[str] = []
    safety = source_artifact.get("safety_invariants")
    if not isinstance(safety, dict):
        safety = {}
    if safety.get("cycles_have_forbidden_effects") is True:
        effects.append("cycles_have_forbidden_effects")
    for key in (
        "runtime_created",
        "runtime_profile_mutated",
        "local_registration_armed",
        "exchange_submit_armed",
        "execute_real_submit",
        "exchange_write_called",
        "order_created",
        "order_lifecycle_called",
        "attempt_counter_mutated",
        "runtime_budget_mutated",
        "position_opened",
        "position_closed",
        "withdrawal_or_transfer_created",
    ):
        if safety.get(key) is True:
            effects.append(key)
    for effect in _as_list(source_artifact.get("forbidden_effects")):
        effects.append(str(effect))
    latest = _latest_cycle(source_artifact)
    for effect in _as_list(latest.get("forbidden_effects")):
        effects.append(f"latest_cycle:{effect}")
    return _dedupe(effects)


def _planning_args(
    args: argparse.Namespace,
    *,
    signal_input_json: str,
) -> argparse.Namespace:
    metadata = _load_metadata(args.metadata_json)
    metadata.update(
        {
            "runtime_live_signal_shadow_planning_projection": True,
            "source_operator_evidence_json": args.operator_evidence_json,
            "non_executing": True,
        }
    )
    return argparse.Namespace(
        runtime_instance_id=args.runtime_instance_id,
        post_submit_finalize_payload_json=args.post_submit_finalize_artifact_json,
        signal_input_json=signal_input_json,
        env_file=args.env_file,
        api_base=args.api_base,
        context_id=args.context_id,
        expires_at_ms=args.expires_at_ms,
        metadata_json=json.dumps(metadata, ensure_ascii=False),
    )


def _load_metadata(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("--metadata-json must be a JSON object")
    return payload


def _base_artifact(
    *,
    args: argparse.Namespace,
    operator_evidence: dict[str, Any],
    paths: dict[str, Path],
    status: str,
    next_step: str,
    blocked_stage: str | None = None,
    blockers: list[str] | None = None,
    warnings: list[str] | None = None,
    strategy_planning_flow: dict[str, Any] | None = None,
    signal_input_json: str | None = None,
) -> dict[str, Any]:
    planning_payload = (
        strategy_planning_flow.get("api_payload")
        if isinstance(strategy_planning_flow, dict)
        else {}
    )
    if not isinstance(planning_payload, dict):
        planning_payload = {}
    strategy_planning_plan = planning_payload.get("strategy_planning_plan")
    if not isinstance(strategy_planning_plan, dict):
        strategy_planning_plan = {}
    return {
        "scope": "runtime_live_signal_shadow_planning_projection",
        "status": status,
        "blocked_stage": blocked_stage,
        "runtime_instance_id": args.runtime_instance_id,
        "source_operator_evidence_scope": _source_evidence_scope(operator_evidence),
        "source_operator_evidence_status": _source_evidence_status(operator_evidence),
        "signal_input_json": signal_input_json,
        "strategy_planning_flow": strategy_planning_flow,
        "artifact_paths": {key: str(value) for key, value in paths.items()},
        "signal_evaluation_id": planning_payload.get("signal_evaluation_id"),
        "order_candidate_id": planning_payload.get("order_candidate_id"),
        "blockers": _dedupe(blockers or []),
        "warnings": _dedupe(warnings or []),
        "shadow_planning_plan": {
            "not_execution_authority": True,
            "next_step": next_step,
            "creates_shadow_candidate": bool(
            strategy_planning_plan.get("creates_shadow_candidate")
            or planning_payload.get("order_candidate_id")
        ),
            "creates_execution_intent": False,
            "creates_executable_execution_intent": False,
            "creates_submit_authorization": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "executes_real_submit": False,
            "requires_official_final_gate": status == READY_FOR_FINAL_GATE_PREFLIGHT,
            "requires_fresh_authorization_before_submit": (
                status == READY_FOR_FINAL_GATE_PREFLIGHT
            ),
        },
        "right_tail_objective_context": {
            "no_signal_is_not_failure": status == "waiting_for_signal",
            "forcing_entry_without_signal_forbidden": True,
            "small_bounded_losses_allowed_after_runtime_gate": True,
            "automatic_compounding_assumed": False,
            "automatic_withdrawal_assumed": False,
        },
        "safety_invariants": _safety(
            operator_evidence=operator_evidence,
            strategy_planning_flow=strategy_planning_flow,
        ),
    }


def _safety(
    *,
    operator_evidence: dict[str, Any],
    strategy_planning_flow: dict[str, Any] | None,
) -> dict[str, Any]:
    planning_safety = (
        strategy_planning_flow.get("safety_invariants")
        if isinstance(strategy_planning_flow, dict)
        else {}
    )
    if not isinstance(planning_safety, dict):
        planning_safety = {}
    return {
        "uses_official_strategy_planning_api": strategy_planning_flow is not None,
        "non_executing": True,
        "source_forbidden_effects": _forbidden_effects(operator_evidence),
        "prepare_records_created": False,
        "execution_intent_created": False,
        "submit_authorization_created": False,
        "local_registration_armed": False,
        "exchange_submit_armed": False,
        "execute_real_submit": False,
        "exchange_write_called": bool(planning_safety.get("exchange_write_called")),
        "order_created": bool(planning_safety.get("order_created")),
        "order_lifecycle_called": bool(planning_safety.get("order_lifecycle_called")),
        "attempt_counter_mutated": bool(planning_safety.get("attempt_counter_mutated")),
        "runtime_budget_mutated": bool(planning_safety.get("runtime_budget_mutated")),
        "position_opened": bool(planning_safety.get("position_opened")),
        "position_closed": bool(planning_safety.get("position_closed")),
        "withdrawal_or_transfer_created": bool(
            planning_safety.get("withdrawal_or_transfer_created")
        ),
    }


def _build_projection(
    args: argparse.Namespace,
    *,
    planning_builder: PlanningBuilder | None = None,
) -> dict[str, Any]:
    paths = _output_paths(args)
    operator_evidence = _read_json(args.operator_evidence_json)
    operator_status = _source_evidence_status(operator_evidence)
    warnings = list(operator_evidence.get("warnings") or [])
    forbidden = _forbidden_effects(operator_evidence)
    if forbidden or operator_status in {"blocked", "supervisor_blocked"}:
        blockers = list(operator_evidence.get("blockers") or []) + forbidden
        return _base_artifact(
            args=args,
            operator_evidence=operator_evidence,
            paths=paths,
            status="blocked",
            blocked_stage="operator_evidence",
            blockers=blockers,
            warnings=warnings,
            next_step="resolve_live_signal_operator_blocker",
        )

    if operator_status in {WAITING_CYCLE, WAITING_SUPERVISOR}:
        return _base_artifact(
            args=args,
            operator_evidence=operator_evidence,
            paths=paths,
            status="waiting_for_signal",
            blockers=list(operator_evidence.get("blockers") or []),
            warnings=warnings,
            next_step="continue_live_signal_operator_supervision",
        )

    if operator_status in {PROFILE_CYCLE, PROFILE_SUPERVISOR}:
        return _base_artifact(
            args=args,
            operator_evidence=operator_evidence,
            paths=paths,
            status="profile_review_required",
            warnings=warnings,
            next_step="review_runtime_profile_proposal_before_shadow_planning",
        )

    if operator_status in {READY_FOR_FINAL_GATE_PREFLIGHT, SUPERVISOR_FINAL_GATE_REVIEW}:
        return _base_artifact(
            args=args,
            operator_evidence=operator_evidence,
            paths=paths,
            status="ready_for_final_gate_preflight",
            warnings=warnings,
            next_step="continue_with_existing_final_gate_preflight_artifact",
        )

    if operator_status not in {READY_FOR_PREPARE, SUPERVISOR_PREPARE_REVIEW}:
        return _base_artifact(
            args=args,
            operator_evidence=operator_evidence,
            paths=paths,
            status="blocked",
            blocked_stage="operator_evidence_status",
            blockers=[f"unsupported_operator_evidence_status:{operator_status or 'missing'}"],
            warnings=warnings,
            next_step="resolve_live_signal_operator_status_before_shadow_planning",
        )

    signal_input_json = _signal_input_json(operator_evidence)
    if not signal_input_json:
        return _base_artifact(
            args=args,
            operator_evidence=operator_evidence,
            paths=paths,
            status="blocked",
            blocked_stage="signal_input_json",
            blockers=["ready_operator_signal_input_json_missing"],
            warnings=warnings,
            next_step="rerun_live_signal_routing_until_signal_input_json_is_available",
        )

    builder = planning_builder or planning_flow._build_artifact
    with redirect_stdout(sys.stderr):
        planning_artifact = builder(
            _planning_args(args, signal_input_json=signal_input_json)
        )
    _write_json(paths["strategy_planning_flow"], planning_artifact)
    planning_status = str(planning_artifact.get("status") or "")
    planning_blockers = list(planning_artifact.get("blockers") or [])
    if planning_status == READY_FOR_FINAL_GATE_PREFLIGHT:
        return _base_artifact(
            args=args,
            operator_evidence=operator_evidence,
            paths=paths,
            status=READY_FOR_FINAL_GATE_PREFLIGHT,
            strategy_planning_flow=planning_artifact,
            signal_input_json=signal_input_json,
            warnings=warnings + list(planning_artifact.get("warnings") or []),
            next_step="run_official_final_gate_preflight_for_shadow_candidate",
        )
    if planning_status == "waiting_for_signal":
        return _base_artifact(
            args=args,
            operator_evidence=operator_evidence,
            paths=paths,
            status="waiting_for_signal",
            strategy_planning_flow=planning_artifact,
            signal_input_json=signal_input_json,
            blockers=planning_blockers,
            warnings=warnings + list(planning_artifact.get("warnings") or []),
            next_step="observe_or_wait_for_next_strategy_signal",
        )
    return _base_artifact(
        args=args,
        operator_evidence=operator_evidence,
        paths=paths,
        status="blocked",
        blocked_stage="strategy_planning",
        strategy_planning_flow=planning_artifact,
        signal_input_json=signal_input_json,
        blockers=planning_blockers or ["strategy_planning_not_ready"],
        warnings=warnings + list(planning_artifact.get("warnings") or []),
        next_step="resolve_strategy_planning_blocker_before_final_gate",
    )


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = str(item).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Project a ready live-signal operator artifact into non-executing "
            "shadow strategy planning evidence."
        ),
    )
    parser.add_argument("--runtime-instance-id", required=True)
    parser.add_argument("--operator-evidence-json", required=True)
    parser.add_argument("--post-submit-finalize-artifact-json", required=True)
    parser.add_argument("--env-file")
    parser.add_argument("--api-base")
    parser.add_argument("--context-id")
    parser.add_argument("--expires-at-ms", type=int)
    parser.add_argument("--metadata-json")
    parser.add_argument(
        "--output-dir",
        default="output/runtime-live-signal-shadow-planning-projection",
    )
    parser.add_argument("--flow-id")
    parser.add_argument("--output-json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    with redirect_stdout(sys.stderr):
        projection = _build_projection(args)
    payload = json.dumps(projection, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    if args.output_json:
        _write_json(Path(args.output_json).expanduser(), projection)
    print(payload)
    return 0 if projection["status"] in {
        READY_FOR_FINAL_GATE_PREFLIGHT,
        "waiting_for_signal",
        "profile_review_required",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
