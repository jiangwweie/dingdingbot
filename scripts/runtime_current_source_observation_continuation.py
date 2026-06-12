#!/usr/bin/env python3
"""Continue runtime observation into the current-source disabled-smoke path.

RTF-063 composes the current runtime loop without replaying historical samples:

post-submit finalize / fresh signal prepare loop
-> wait if the strategy signal is not ready
-> require readiness evidence when a signal is ready
-> current persisted source disabled-smoke pipeline

The script never submits orders, calls OrderLifecycle, writes to exchange,
opens/closes positions, or moves funds. Depending on flags supplied to the
underlying prepare loop and current-source pipeline, it may create non-executing
shadow/persisted records and a fresh submit authorization only after a genuine
runtime-compatible signal is ready.
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

from scripts import runtime_current_persisted_source_disabled_smoke_pipeline as current_pipeline  # noqa: E402
from scripts import runtime_fresh_signal_prepare_loop as fresh_loop  # noqa: E402


FreshLoopBuilder = Callable[[argparse.Namespace], dict[str, Any]]
CurrentPipelineBuilder = Callable[[argparse.Namespace], dict[str, Any]]

READY_FOR_FINAL_GATE_PREFLIGHT = "ready_for_final_gate_preflight"
READY_FOR_PREPARE = "ready_for_prepare"
WAITING_FOR_SIGNAL = "waiting_for_signal"
READY_FOR_EVIDENCE = "ready_for_current_source_pipeline_evidence"


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
        "fresh_loop": output_dir / f"{flow_id}-fresh-signal-prepare-loop.json",
        "current_pipeline": output_dir / f"{flow_id}-current-source-pipeline.json",
    }


def _fresh_loop_args(args: argparse.Namespace) -> argparse.Namespace:
    loop_output_dir = str(Path(args.output_dir).expanduser() / "fresh-loop")
    return argparse.Namespace(
        runtime_instance_id=args.runtime_instance_id,
        authorization_id=args.authorization_id,
        reservation_id=args.reservation_id,
        closed_review_required=args.closed_review_required,
        protection_blocker=args.protection_blocker,
        env_file=args.env_file,
        api_base=args.api_base,
        metadata_json=args.metadata_json,
        source=args.source,
        include_exchange=args.include_exchange,
        symbol=args.symbol,
        side=args.side,
        family=args.family,
        strategy_family_id=args.strategy_family_id,
        carrier_id=args.carrier_id,
        quantity=args.quantity,
        target_notional_usdt=args.target_notional_usdt,
        max_notional=args.max_notional,
        leverage=args.leverage,
        max_attempts=args.max_attempts,
        protection_mode=args.protection_mode,
        review_requirement=args.review_requirement,
        evaluation_id=args.evaluation_id,
        playbook_id=args.playbook_id,
        one_hour_limit=args.one_hour_limit,
        four_hour_limit=args.four_hour_limit,
        timeout_seconds=args.timeout_seconds,
        allow_prepare_records=args.allow_prepare_records,
        candidate_id=args.candidate_id,
        context_id=args.context_id,
        owner_operator_id=args.owner_operator_id,
        owner_confirmation_reference=args.owner_confirmation_reference,
        reason=args.reason,
        next_attempt_symbol=args.next_attempt_symbol,
        next_attempt_side=args.next_attempt_side,
        next_attempt_family=args.next_attempt_family,
        next_attempt_strategy_family_id=args.next_attempt_strategy_family_id,
        next_attempt_carrier_id=args.next_attempt_carrier_id,
        output_dir=loop_output_dir,
        cycle_id=args.flow_id or _safe_file_id(args.runtime_instance_id),
    )


def _current_pipeline_args(
    args: argparse.Namespace,
    *,
    signal_input_json: str,
    artifact_dir: Path,
) -> argparse.Namespace:
    return argparse.Namespace(
        runtime_instance_id=args.runtime_instance_id,
        signal_input_json=signal_input_json,
        readiness_evidence_json=args.readiness_evidence_json,
        auto_readiness_evidence=args.auto_readiness_evidence,
        final_gate_preview_id=args.final_gate_preview_id,
        final_gate_passed=args.final_gate_passed,
        runtime_grant_authorization_id=args.runtime_grant_authorization_id,
        owner_real_submit_authorization_id=args.owner_real_submit_authorization_id,
        trusted_submit_fact_snapshot_id=args.trusted_submit_fact_snapshot_id,
        submit_idempotency_policy_id=args.submit_idempotency_policy_id,
        attempt_outcome_policy_id=args.attempt_outcome_policy_id,
        protection_creation_failure_policy_id=(
            args.protection_creation_failure_policy_id
        ),
        local_registration_enablement_decision_id=(
            args.local_registration_enablement_decision_id
        ),
        exchange_submit_enablement_decision_id=(
            args.exchange_submit_enablement_decision_id
        ),
        exchange_submit_action_authorization_id=(
            args.exchange_submit_action_authorization_id
        ),
        order_lifecycle_submit_enablement_id=(
            args.order_lifecycle_submit_enablement_id
        ),
        exchange_submit_adapter_enablement_id=(
            args.exchange_submit_adapter_enablement_id
        ),
        deployment_readiness_evidence_id=args.deployment_readiness_evidence_id,
        protection_required_and_ready=args.protection_required_and_ready,
        active_position_source_trusted=args.active_position_source_trusted,
        account_facts_fresh=args.account_facts_fresh,
        duplicate_submit_guard_ready=args.duplicate_submit_guard_ready,
        legacy_runtime_submit_rehearsal_id=args.legacy_runtime_submit_rehearsal_id,
        durable_exchange_submit_execution_result_id=(
            args.durable_exchange_submit_execution_result_id
        ),
        final_gate_preview_json=args.final_gate_preview_json,
        trusted_submit_facts_json=args.trusted_submit_facts_json,
        submit_idempotency_json=args.submit_idempotency_json,
        attempt_outcome_policy_json=args.attempt_outcome_policy_json,
        protection_failure_policy_json=args.protection_failure_policy_json,
        local_registration_enablement_json=args.local_registration_enablement_json,
        exchange_submit_enablement_json=args.exchange_submit_enablement_json,
        exchange_action_authorization_json=args.exchange_action_authorization_json,
        order_lifecycle_submit_enablement_json=(
            args.order_lifecycle_submit_enablement_json
        ),
        exchange_adapter_enablement_json=args.exchange_adapter_enablement_json,
        deployment_readiness_json=args.deployment_readiness_json,
        requested_fresh_submit_authorization_id=(
            args.requested_fresh_submit_authorization_id
        ),
        candidate_id=args.candidate_id,
        context_id=args.context_id,
        expires_at_ms=args.expires_at_ms,
        active_positions_count=args.active_positions_count,
        metadata_json=args.metadata_json,
        env_file=args.env_file,
        api_base=args.api_base,
        artifact_dir=str(artifact_dir),
        output=None,
    )


def _signal_input_json(loop_packet: dict[str, Any]) -> str | None:
    value = loop_packet.get("signal_input_json")
    if isinstance(value, str) and value.strip():
        return value.strip()
    observation = loop_packet.get("observation_prepare_flow")
    if isinstance(observation, dict):
        value = observation.get("signal_input_json")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _safety(
    *,
    loop_packet: dict[str, Any] | None = None,
    pipeline_packet: dict[str, Any] | None = None,
) -> dict[str, bool]:
    loop_safety = (
        loop_packet.get("safety_invariants") if isinstance(loop_packet, dict) else {}
    )
    pipeline_safety = (
        pipeline_packet.get("safety_invariants")
        if isinstance(pipeline_packet, dict)
        else {}
    )
    if not isinstance(loop_safety, dict):
        loop_safety = {}
    if not isinstance(pipeline_safety, dict):
        pipeline_safety = {}

    def flag(name: str) -> bool:
        return bool(loop_safety.get(name) or pipeline_safety.get(name))

    return {
        "uses_current_runtime_observation": True,
        "uses_historical_rtf015_sample_handoff": False,
        "non_executing_until_disabled_smoke": True,
        "prepare_records_created": flag("prepare_records_created"),
        "shadow_candidate_created": flag("shadow_candidate_created"),
        "runtime_execution_intent_draft_created": flag(
            "runtime_execution_intent_draft_created"
        ),
        "execution_intent_created": flag("execution_intent_created")
        or flag("recorded_execution_intent_created"),
        "submit_authorization_created": flag("submit_authorization_created"),
        "calls_official_submit_endpoint": flag("calls_official_submit_endpoint"),
        "requests_real_gateway_action": flag("requests_real_gateway_action"),
        "owner_confirmed_for_first_real_submit_action": flag(
            "owner_confirmed_for_first_real_submit_action"
        ),
        "exchange_submit_execution_enabled": flag(
            "exchange_submit_execution_enabled"
        ),
        "local_registration_armed": flag("local_registration_armed"),
        "exchange_submit_armed": flag("exchange_submit_armed"),
        "execute_real_submit": flag("execute_real_submit"),
        "exchange_write_called": flag("exchange_write_called"),
        "order_created": flag("order_created"),
        "order_lifecycle_called": flag("order_lifecycle_called"),
        "runtime_budget_mutated": flag("runtime_budget_mutated")
        or flag("runtime_budget_mutated_by_script"),
        "position_opened": flag("position_opened"),
        "position_closed": flag("position_closed"),
        "withdrawal_or_transfer_created": flag("withdrawal_or_transfer_created"),
    }


def _build_packet(
    args: argparse.Namespace,
    *,
    fresh_loop_builder: FreshLoopBuilder | None = None,
    current_pipeline_builder: CurrentPipelineBuilder | None = None,
) -> dict[str, Any]:
    paths = _output_paths(args)
    loop_builder = fresh_loop_builder or fresh_loop._build_packet
    pipeline_builder = current_pipeline_builder or current_pipeline._build_report

    loop_packet = loop_builder(_fresh_loop_args(args))
    _write_json(paths["fresh_loop"], loop_packet)
    loop_status = str(loop_packet.get("status") or "")
    if loop_status in {WAITING_FOR_SIGNAL, READY_FOR_PREPARE}:
        return _base_packet(
            args=args,
            paths=paths,
            status=loop_status,
            blocked_stage=None,
            fresh_loop_packet=loop_packet,
            current_pipeline_packet=None,
            next_step=(
                "continue_observation_until_genuine_would_enter"
                if loop_status == WAITING_FOR_SIGNAL
                else "provide_readiness_evidence_before_current_source_pipeline"
            ),
        )
    if loop_status != READY_FOR_FINAL_GATE_PREFLIGHT:
        return _base_packet(
            args=args,
            paths=paths,
            status="blocked",
            blocked_stage="fresh_signal_prepare_loop",
            fresh_loop_packet=loop_packet,
            current_pipeline_packet=None,
            next_step="resolve_fresh_signal_prepare_loop_blocker",
        )

    signal_input_json = _signal_input_json(loop_packet)
    if not signal_input_json:
        return _base_packet(
            args=args,
            paths=paths,
            status="blocked",
            blocked_stage="signal_input_json",
            fresh_loop_packet=loop_packet,
            current_pipeline_packet=None,
            extra_blockers=["ready_fresh_signal_missing_signal_input_json"],
            next_step="rerun_fresh_signal_prepare_loop_until_signal_input_is_available",
        )

    has_evidence = bool(args.readiness_evidence_json or args.auto_readiness_evidence)
    if not has_evidence:
        return _base_packet(
            args=args,
            paths=paths,
            status=READY_FOR_EVIDENCE,
            blocked_stage=None,
            fresh_loop_packet=loop_packet,
            current_pipeline_packet=None,
            next_step="provide_readiness_evidence_before_current_source_pipeline",
        )

    current_packet = pipeline_builder(
        _current_pipeline_args(
            args,
            signal_input_json=signal_input_json,
            artifact_dir=paths["current_pipeline"].with_suffix(""),
        )
    )
    _write_json(paths["current_pipeline"], current_packet)
    status = str(current_packet.get("status") or "blocked")
    blocked_stage = current_packet.get("blocked_stage")
    return _base_packet(
        args=args,
        paths=paths,
        status=status,
        blocked_stage=blocked_stage,
        fresh_loop_packet=loop_packet,
        current_pipeline_packet=current_packet,
        next_step=(
            "await_real_submit_gate_after_disabled_smoke"
            if status == current_pipeline.READY_STATUS
            else "resolve_current_source_pipeline_blocker"
        ),
    )


def _base_packet(
    *,
    args: argparse.Namespace,
    paths: dict[str, Path],
    status: str,
    blocked_stage: str | None,
    fresh_loop_packet: dict[str, Any],
    current_pipeline_packet: dict[str, Any] | None,
    next_step: str,
    extra_blockers: list[str] | None = None,
) -> dict[str, Any]:
    blockers = list(extra_blockers or [])
    blockers.extend(str(item) for item in fresh_loop_packet.get("blockers") or [])
    if isinstance(current_pipeline_packet, dict):
        blockers.extend(
            f"current_source_pipeline:{item}"
            for item in current_pipeline_packet.get("blockers") or []
        )
    warnings = [str(item) for item in fresh_loop_packet.get("warnings") or []]
    if isinstance(current_pipeline_packet, dict):
        warnings.extend(
            f"current_source_pipeline:{item}"
            for item in current_pipeline_packet.get("warnings") or []
        )
    return {
        "scope": "runtime_current_source_observation_continuation",
        "status": status,
        "blocked_stage": blocked_stage,
        "runtime_instance_id": args.runtime_instance_id,
        "artifact_paths": {key: str(value) for key, value in paths.items()},
        "fresh_signal_prepare_loop": fresh_loop_packet,
        "current_source_pipeline": current_pipeline_packet,
        "signal_input_json": _signal_input_json(fresh_loop_packet),
        "blockers": _dedupe(blockers),
        "warnings": _dedupe(warnings),
        "operator_command_plan": {
            "next_step": next_step,
            "creates_shadow_candidate": bool(
                _safety(
                    loop_packet=fresh_loop_packet,
                    pipeline_packet=current_pipeline_packet,
                ).get("shadow_candidate_created")
            ),
            "creates_execution_intent": bool(
                _safety(
                    loop_packet=fresh_loop_packet,
                    pipeline_packet=current_pipeline_packet,
                ).get("execution_intent_created")
            ),
            "places_order": False,
            "calls_order_lifecycle": False,
            "requires_readiness_evidence": status == READY_FOR_EVIDENCE,
            "requires_real_submit_gate": status == current_pipeline.READY_STATUS,
        },
        "safety_invariants": _safety(
            loop_packet=fresh_loop_packet,
            pipeline_packet=current_pipeline_packet,
        ),
    }


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
            "Continue runtime observation into current-source disabled-smoke "
            "without historical sample replay."
        ),
    )
    parser.add_argument("--runtime-instance-id", required=True)
    parser.add_argument("--authorization-id")
    parser.add_argument("--reservation-id")
    parser.add_argument("--closed-review-required", action="store_true")
    parser.add_argument("--protection-blocker", action="append")
    parser.add_argument("--env-file")
    parser.add_argument("--api-base")
    parser.add_argument("--metadata-json")
    parser.add_argument("--source", choices=["live_market", "sample"], default="live_market")
    parser.add_argument("--include-exchange", action="store_true", default=False)
    parser.add_argument("--symbol")
    parser.add_argument("--side")
    parser.add_argument("--family")
    parser.add_argument("--strategy-family-id")
    parser.add_argument("--carrier-id")
    parser.add_argument("--quantity")
    parser.add_argument("--target-notional-usdt")
    parser.add_argument("--max-notional")
    parser.add_argument("--leverage")
    parser.add_argument("--max-attempts", type=int)
    parser.add_argument("--protection-mode")
    parser.add_argument("--review-requirement")
    parser.add_argument("--evaluation-id")
    parser.add_argument("--playbook-id")
    parser.add_argument("--one-hour-limit", type=int, default=25)
    parser.add_argument("--four-hour-limit", type=int, default=25)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--allow-prepare-records", action="store_true", default=False)
    parser.add_argument("--candidate-id")
    parser.add_argument("--context-id")
    parser.add_argument("--owner-operator-id", default="owner")
    parser.add_argument(
        "--owner-confirmation-reference",
        default="owner-authorized-current-source-observation-continuation",
    )
    parser.add_argument(
        "--reason",
        default="owner authorized current source observation continuation",
    )
    parser.add_argument("--next-attempt-symbol")
    parser.add_argument("--next-attempt-side")
    parser.add_argument("--next-attempt-family")
    parser.add_argument("--next-attempt-strategy-family-id")
    parser.add_argument("--next-attempt-carrier-id")
    parser.add_argument("--readiness-evidence-json")
    parser.add_argument("--auto-readiness-evidence", action="store_true")
    parser.add_argument("--final-gate-preview-id")
    parser.add_argument("--final-gate-passed", action="store_true")
    parser.add_argument("--runtime-grant-authorization-id")
    parser.add_argument("--owner-real-submit-authorization-id")
    parser.add_argument("--trusted-submit-fact-snapshot-id")
    parser.add_argument("--submit-idempotency-policy-id")
    parser.add_argument("--attempt-outcome-policy-id")
    parser.add_argument("--protection-creation-failure-policy-id")
    parser.add_argument("--local-registration-enablement-decision-id")
    parser.add_argument("--exchange-submit-enablement-decision-id")
    parser.add_argument("--exchange-submit-action-authorization-id")
    parser.add_argument("--order-lifecycle-submit-enablement-id")
    parser.add_argument("--exchange-submit-adapter-enablement-id")
    parser.add_argument("--deployment-readiness-evidence-id")
    parser.add_argument("--protection-required-and-ready", action="store_true")
    parser.add_argument("--active-position-source-trusted", action="store_true")
    parser.add_argument("--account-facts-fresh", action="store_true")
    parser.add_argument("--duplicate-submit-guard-ready", action="store_true")
    parser.add_argument("--legacy-runtime-submit-rehearsal-id")
    parser.add_argument("--durable-exchange-submit-execution-result-id")
    parser.add_argument("--final-gate-preview-json")
    parser.add_argument("--trusted-submit-facts-json")
    parser.add_argument("--submit-idempotency-json")
    parser.add_argument("--attempt-outcome-policy-json")
    parser.add_argument("--protection-failure-policy-json")
    parser.add_argument("--local-registration-enablement-json")
    parser.add_argument("--exchange-submit-enablement-json")
    parser.add_argument("--exchange-action-authorization-json")
    parser.add_argument("--order-lifecycle-submit-enablement-json")
    parser.add_argument("--exchange-adapter-enablement-json")
    parser.add_argument("--deployment-readiness-json")
    parser.add_argument("--requested-fresh-submit-authorization-id")
    parser.add_argument("--expires-at-ms", type=int)
    parser.add_argument("--active-positions-count", type=int)
    parser.add_argument(
        "--output-dir",
        default="output/runtime-current-source-observation-continuation",
    )
    parser.add_argument("--flow-id")
    parser.add_argument("--output-json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    with redirect_stdout(sys.stderr):
        packet = _build_packet(args)
    output = json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    if args.output_json:
        _write_json(Path(args.output_json).expanduser(), packet)
    print(output)
    return 0 if packet["status"] in {
        WAITING_FOR_SIGNAL,
        READY_FOR_PREPARE,
        READY_FOR_EVIDENCE,
        current_pipeline.READY_STATUS,
        "blocked",
        "blocked_at_strategy_signal_intent_draft_source",
        "blocked_at_persisted_draft_source_readiness",
        "blocked_at_fresh_submit_authorization_binding",
        "blocked_at_final_official_submit_handoff",
        "blocked_at_disabled_smoke",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
