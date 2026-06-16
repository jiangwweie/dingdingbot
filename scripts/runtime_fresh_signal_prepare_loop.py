#!/usr/bin/env python3
"""Run post-submit finalize before fresh-signal prepare observation.

RTF-056 composes the current runtime mainline into one non-executing operator
entry:

latest durable submit result
-> post-submit finalize API
-> fresh strategy signal observation
-> optional prepare records when a signal is ready and explicitly allowed

The script never arms local registration, never arms exchange submit, never
calls OrderLifecycle, never submits orders, and never moves funds.
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

from scripts import runtime_next_attempt_observation_api_prepare_flow as observation_flow  # noqa: E402
from scripts import runtime_post_submit_finalize_api_flow as finalize_flow  # noqa: E402


FinalizeBuilder = Callable[[argparse.Namespace], dict[str, Any]]
ObservationBuilder = Callable[[argparse.Namespace], dict[str, Any]]

READY_POST_SUBMIT_STATUS = "finalized_ready_for_next_attempt"
READY_FOR_PREPARE = "ready_for_prepare"
READY_FOR_FINAL_GATE_PREFLIGHT = "ready_for_final_gate_preflight"
WAITING_FOR_SIGNAL = "waiting_for_signal"


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
        "post_submit_finalize": output_dir / f"{cycle_id}-post-submit-finalize.json",
        "observation_prepare": output_dir / f"{cycle_id}-observation-prepare.json",
        "signal_input": output_dir / f"{cycle_id}-signal-input.json",
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _finalize_args(args: argparse.Namespace) -> argparse.Namespace:
    metadata = {
        **_load_json_object(args.metadata_json),
        "runtime_fresh_signal_prepare_loop": True,
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


def _observation_args(
    args: argparse.Namespace,
    *,
    signal_output_json: Path,
) -> argparse.Namespace:
    return argparse.Namespace(
        runtime_instance_id=args.runtime_instance_id,
        env_file=args.env_file,
        api_base=args.api_base,
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
        signal_output_json=str(signal_output_json),
        output_dir=args.output_dir,
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
    )


def _safety(
    *,
    post_submit: dict[str, Any] | None = None,
    observation: dict[str, Any] | None = None,
) -> dict[str, bool]:
    def flag(packet: dict[str, Any] | None, name: str) -> bool:
        if not isinstance(packet, dict):
            return False
        safety = packet.get("safety_invariants")
        return bool(safety.get(name)) if isinstance(safety, dict) else False

    return {
        "uses_official_trading_console_api": True,
        "post_submit_finalize_required_first": True,
        "allow_prepare_records": flag(observation, "allow_prepare_records"),
        "prepare_records_created": flag(observation, "prepare_records_created"),
        "shadow_candidate_created": flag(observation, "shadow_candidate_created"),
        "runtime_execution_intent_draft_created": flag(
            observation,
            "runtime_execution_intent_draft_created",
        ),
        "recorded_execution_intent_created": flag(
            observation,
            "recorded_execution_intent_created",
        ),
        "submit_authorization_created": flag(observation, "submit_authorization_created"),
        "protection_plan_created": flag(observation, "protection_plan_created"),
        "local_registration_armed": False,
        "exchange_submit_armed": False,
        "execute_real_submit": False,
        "exchange_write_called": flag(post_submit, "exchange_write_called")
        or flag(observation, "exchange_write_called"),
        "order_created": flag(post_submit, "order_created")
        or flag(observation, "order_created"),
        "order_lifecycle_called": flag(post_submit, "order_lifecycle_called")
        or flag(observation, "order_lifecycle_called"),
        "attempt_counter_mutated_by_script": flag(
            post_submit,
            "attempt_counter_mutated_by_script",
        ),
        "runtime_budget_mutated_by_script": flag(
            post_submit,
            "runtime_budget_mutated_by_script",
        ),
        "position_opened": flag(post_submit, "position_opened")
        or flag(observation, "position_opened"),
        "position_closed": flag(post_submit, "position_closed")
        or flag(observation, "position_closed"),
        "withdrawal_or_transfer_created": flag(
            post_submit,
            "withdrawal_or_transfer_created",
        )
        or flag(observation, "withdrawal_or_transfer_created"),
    }


def _operator_next_step(status: str) -> str:
    if status == READY_FOR_FINAL_GATE_PREFLIGHT:
        return "run_official_final_gate_preflight"
    if status == READY_FOR_PREPARE:
        return "rerun_with_allow_prepare_records_under_standing_authorization"
    if status == WAITING_FOR_SIGNAL:
        return "continue_observation_until_fresh_runtime_signal"
    return "resolve_post_submit_or_prepare_loop_blocker"


def _build_packet(
    args: argparse.Namespace,
    *,
    finalize_builder: FinalizeBuilder | None = None,
    observation_builder: ObservationBuilder | None = None,
) -> dict[str, Any]:
    paths = _output_paths(args)
    finalize_builder = finalize_builder or finalize_flow._build_packet
    observation_builder = observation_builder or observation_flow._build_packet

    post_submit = finalize_builder(_finalize_args(args))
    _write_json(paths["post_submit_finalize"], post_submit)

    post_submit_status = str(post_submit.get("status") or "")
    if post_submit_status != READY_POST_SUBMIT_STATUS:
        blockers = list(post_submit.get("blockers") or [])
        if not blockers:
            blockers.append("post_submit_finalize_not_ready_for_fresh_signal_prepare")
        return {
            "scope": "runtime_fresh_signal_prepare_loop",
            "status": "blocked",
            "blocked_stage": "post_submit_finalize",
            "runtime_instance_id": args.runtime_instance_id,
            "post_submit_finalize_flow": post_submit,
            "observation_prepare_flow": None,
            "artifact_paths": {key: str(value) for key, value in paths.items()},
            "blockers": blockers,
            "warnings": list(post_submit.get("warnings") or []),
            "operator_command_plan": {
                "next_step": "resolve_post_submit_finalize_blocker",
                "creates_shadow_candidate": False,
                "creates_execution_intent": False,
                "places_order": False,
                "calls_order_lifecycle": False,
            },
            "safety_invariants": _safety(post_submit=post_submit),
        }

    observation = observation_builder(
        _observation_args(args, signal_output_json=paths["signal_input"])
    )
    _write_json(paths["observation_prepare"], observation)

    observation_status = str(observation.get("status") or "")
    status = (
        observation_status
        if observation_status
        in {READY_FOR_PREPARE, READY_FOR_FINAL_GATE_PREFLIGHT, WAITING_FOR_SIGNAL}
        else "blocked"
    )
    blockers = list(observation.get("blockers") or [])
    if status == "blocked" and not blockers:
        blockers.append("observation_prepare_not_ready")
    observation_plan = observation.get("operator_command_plan")
    if not isinstance(observation_plan, dict):
        observation_plan = {}
    prepare_packet = observation.get("prepare_packet")
    if not isinstance(prepare_packet, dict):
        prepare_packet = {}
    prepare_plan = prepare_packet.get("operator_command_plan")
    if not isinstance(prepare_plan, dict):
        prepare_plan = {}

    return {
        "scope": "runtime_fresh_signal_prepare_loop",
        "status": status,
        "blocked_stage": None if status != "blocked" else "observation_prepare",
        "runtime_instance_id": args.runtime_instance_id,
        "post_submit_finalize_flow": post_submit,
        "observation_prepare_flow": observation,
        "artifact_paths": {key: str(value) for key, value in paths.items()},
        "signal_input_json": observation.get("signal_input_json"),
        "prepared_authorization_id": (
            observation_plan.get("prepared_authorization_id")
            or prepare_plan.get("prepared_authorization_id")
        ),
        "blockers": blockers,
        "warnings": list(post_submit.get("warnings") or [])
        + list(observation.get("warnings") or []),
        "operator_command_plan": {
            "next_step": _operator_next_step(status),
            "creates_shadow_candidate": bool(
                observation_plan.get("creates_shadow_candidate")
                or observation.get("safety_invariants", {}).get(
                    "shadow_candidate_created"
                )
            ),
            "creates_execution_intent": False,
            "creates_executable_execution_intent": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "requires_official_final_gate": status
            == READY_FOR_FINAL_GATE_PREFLIGHT,
            "requires_fresh_authorization_before_submit": True,
        },
        "safety_invariants": _safety(
            post_submit=post_submit,
            observation=observation,
        ),
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run post-submit finalize then fresh-signal prepare observation "
            "without submit authority."
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
        default="owner-authorized-fresh-signal-prepare-loop",
    )
    parser.add_argument(
        "--reason",
        default="owner authorized fresh signal prepare loop",
    )
    parser.add_argument("--next-attempt-symbol")
    parser.add_argument("--next-attempt-side")
    parser.add_argument("--next-attempt-family")
    parser.add_argument("--next-attempt-strategy-family-id")
    parser.add_argument("--next-attempt-carrier-id")
    parser.add_argument(
        "--output-dir",
        default="output/runtime-fresh-signal-prepare-loop",
    )
    parser.add_argument("--cycle-id")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    with redirect_stdout(sys.stderr):
        packet = _build_packet(args)
    print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if packet["status"] in {
        WAITING_FOR_SIGNAL,
        READY_FOR_PREPARE,
        READY_FOR_FINAL_GATE_PREFLIGHT,
        "blocked",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
