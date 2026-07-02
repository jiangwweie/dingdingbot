#!/usr/bin/env python3
"""Run one non-executing runtime next-attempt observation cycle.

Default mode checks the next-attempt gate and evaluates fresh strategy signal
input only. It does not create shadow candidates or intent records unless
``--allow-prepare-records`` is explicitly supplied.
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import redirect_stdout
import json
import os
from pathlib import Path
import sys
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import build_runtime_strategy_signal_input_artifact as signal_script  # noqa: E402
from scripts import runtime_next_attempt_prepare_api_flow as prepare_script  # noqa: E402
from scripts import verify_runtime_next_attempt_gate_evidence as gate_script  # noqa: E402


def _load_env_file(path: str | None) -> None:
    if not path:
        return
    env_path = Path(path).expanduser()
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and not os.environ.get(key):
            os.environ[key] = value


def _signal_output_path(args: argparse.Namespace) -> str | None:
    if args.signal_output_json:
        return str(Path(args.signal_output_json).expanduser())
    if not args.allow_prepare_records:
        return None
    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    runtime_id = args.runtime_instance_id.replace("/", "_").replace(":", "_")
    return str(output_dir / f"{runtime_id}-signal-input.json")


def _gate_args(args: argparse.Namespace) -> argparse.Namespace:
    return argparse.Namespace(
        runtime_instance_id=args.runtime_instance_id,
        env_file=args.env_file,
        api_base=args.api_base,
        skip_exchange=args.skip_exchange,
        family=args.family,
        strategy_family_id=args.strategy_family_id,
        carrier_id=args.carrier_id,
        symbol=args.symbol,
        side=args.side,
        quantity=args.quantity,
        target_notional_usdt=args.target_notional_usdt,
        max_notional=args.max_notional,
        leverage=args.leverage,
        max_attempts=args.max_attempts,
        protection_mode=args.protection_mode,
        review_requirement=args.review_requirement,
    )


def _signal_args(args: argparse.Namespace, output_path: str | None) -> argparse.Namespace:
    return argparse.Namespace(
        runtime_instance_id=args.runtime_instance_id,
        env_file=args.env_file,
        source=args.source,
        symbol=args.symbol,
        evaluation_id=args.evaluation_id,
        playbook_id=args.playbook_id,
        one_hour_limit=args.one_hour_limit,
        four_hour_limit=args.four_hour_limit,
        timeout_seconds=args.timeout_seconds,
        output_signal_input_json=output_path,
    )


def _prepare_args(
    args: argparse.Namespace,
    *,
    signal_input_json: str,
) -> argparse.Namespace:
    return argparse.Namespace(
        env_file=args.env_file,
        api_base=args.api_base,
        runtime_instance_id=args.runtime_instance_id,
        signal_input_json=signal_input_json,
        order_candidate_id=None,
        candidate_id=args.candidate_id,
        context_id=args.context_id,
        owner_operator_id=args.owner_operator_id,
        owner_confirmation_reference=args.owner_confirmation_reference,
        reason=args.reason,
        next_attempt_symbol=args.next_attempt_symbol or args.symbol,
        next_attempt_side=args.next_attempt_side or args.side,
        next_attempt_family=args.next_attempt_family or args.family,
        next_attempt_strategy_family_id=(
            args.next_attempt_strategy_family_id or args.strategy_family_id
        ),
        next_attempt_carrier_id=args.next_attempt_carrier_id or args.carrier_id,
    )


def _signal_is_ready(artifact: dict[str, Any]) -> bool:
    return artifact.get("status") == "ready_for_shadow_candidate_prepare"


async def _build_gate_artifact(args: argparse.Namespace) -> dict[str, Any]:
    return await gate_script._build_gate_evidence(_gate_args(args))


async def _build_signal_artifact(
    args: argparse.Namespace,
    *,
    output_path: str | None,
) -> dict[str, Any]:
    return await signal_script._build_artifact(_signal_args(args, output_path))


def _run_prepare_flow(
    args: argparse.Namespace,
    *,
    signal_input_json: str,
) -> dict[str, Any]:
    prepare_args = _prepare_args(args, signal_input_json=signal_input_json)
    prepare_script._load_env_file(prepare_args.env_file)
    config = prepare_script._build_flow_config(prepare_args)
    report = prepare_script.FirstRealSubmitApiFlow(
        client=prepare_script.UrlLibApiClient(api_base=config.api_base),
        config=config,
    ).run()
    return prepare_script._summarize_prepare_report(report)


def _base_safety(*, allow_prepare_records: bool) -> dict[str, Any]:
    return {
        "default_read_only": not allow_prepare_records,
        "allow_prepare_records": allow_prepare_records,
        "local_registration_armed": False,
        "exchange_submit_armed": False,
        "execute_real_submit": False,
        "exchange_write_called": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "attempt_counter_mutated": False,
        "runtime_budget_mutated": False,
        "position_opened": False,
        "position_closed": False,
        "withdrawal_or_transfer_created": False,
    }


async def _build_cycle_artifact(args: argparse.Namespace) -> dict[str, Any]:
    _load_env_file(args.env_file)
    signal_output_path = _signal_output_path(args)

    gate_artifact = await _build_gate_artifact(args)
    if gate_artifact.get("status") != "clear_for_next_attempt_preflight":
        return {
            "scope": "runtime_next_attempt_observation_cycle",
            "status": "blocked",
            "blocked_stage": "next_attempt_gate",
            "runtime_instance_id": args.runtime_instance_id,
            "gate_artifact": gate_artifact,
            "signal_artifact": None,
            "prepare_artifact": None,
            "blockers": gate_artifact.get("blockers") or ["next_attempt_gate_blocked"],
            "warnings": gate_artifact.get("warnings") or [],
            "observation_cycle_plan": {
                "next_step": "resolve_next_attempt_gate_blocker",
                "not_executed": True,
                "creates_shadow_candidate": False,
                "creates_execution_intent": False,
                "places_order": False,
                "calls_order_lifecycle": False,
            },
            "safety_invariants": _base_safety(
                allow_prepare_records=args.allow_prepare_records
            ),
        }

    signal_artifact = await _build_signal_artifact(args, output_path=signal_output_path)
    if not _signal_is_ready(signal_artifact):
        return {
            "scope": "runtime_next_attempt_observation_cycle",
            "status": "waiting_for_signal",
            "blocked_stage": "strategy_signal",
            "runtime_instance_id": args.runtime_instance_id,
            "gate_artifact": gate_artifact,
            "signal_artifact": signal_artifact,
            "prepare_artifact": None,
            "blockers": ["strategy_signal_not_ready_for_shadow_candidate_prepare"],
            "warnings": signal_artifact.get("warnings") or [],
            "observation_cycle_plan": {
                "next_step": "observe_only_or_wait_for_next_closed_bar",
                "signal_input_json": signal_artifact.get("output_signal_input_json"),
                "not_executed": True,
                "creates_shadow_candidate": False,
                "creates_execution_intent": False,
                "places_order": False,
                "calls_order_lifecycle": False,
            },
            "safety_invariants": _base_safety(
                allow_prepare_records=args.allow_prepare_records
            ),
        }

    resolved_signal_path = signal_artifact.get("output_signal_input_json") or signal_output_path
    if not resolved_signal_path:
        return {
            "scope": "runtime_next_attempt_observation_cycle",
            "status": "ready_for_prepare",
            "runtime_instance_id": args.runtime_instance_id,
            "gate_artifact": gate_artifact,
            "signal_artifact": signal_artifact,
            "prepare_artifact": None,
            "blockers": [],
            "warnings": [
                "signal_input_json_not_written; rerun with --signal-output-json before prepare"
            ],
            "observation_cycle_plan": {
                "next_step": "run_runtime_next_attempt_prepare_with_signal_input_json",
                "signal_input_json": None,
                "not_executed": True,
                "creates_shadow_candidate": False,
                "creates_execution_intent": False,
                "places_order": False,
                "calls_order_lifecycle": False,
            },
            "safety_invariants": _base_safety(
                allow_prepare_records=args.allow_prepare_records
            ),
        }

    if not args.allow_prepare_records:
        return {
            "scope": "runtime_next_attempt_observation_cycle",
            "status": "ready_for_prepare",
            "runtime_instance_id": args.runtime_instance_id,
            "gate_artifact": gate_artifact,
            "signal_artifact": signal_artifact,
            "prepare_artifact": None,
            "blockers": [],
            "warnings": signal_artifact.get("warnings") or [],
            "observation_cycle_plan": {
                "next_step": "rerun_with_allow_prepare_records_after_owner_review",
                "signal_input_json": resolved_signal_path,
                "not_executed": True,
                "creates_shadow_candidate": False,
                "creates_execution_intent": False,
                "places_order": False,
                "calls_order_lifecycle": False,
            },
            "safety_invariants": _base_safety(
                allow_prepare_records=args.allow_prepare_records
            ),
        }

    prepare_artifact = _run_prepare_flow(args, signal_input_json=resolved_signal_path)
    ready = prepare_artifact.get("status") == "ready_for_final_gate_preflight"
    return {
        "scope": "runtime_next_attempt_observation_cycle",
        "status": "ready_for_final_gate_preflight" if ready else "blocked",
        "blocked_stage": None if ready else "prepare_records",
        "runtime_instance_id": args.runtime_instance_id,
        "gate_artifact": gate_artifact,
        "signal_artifact": signal_artifact,
        "prepare_artifact": prepare_artifact,
        "blockers": prepare_artifact.get("blockers") or [],
        "warnings": prepare_artifact.get("warnings") or [],
        "observation_cycle_plan": {
            "next_step": (
                "run_official_final_gate_preflight"
                if ready
                else "resolve_prepare_blockers"
            ),
            "signal_input_json": resolved_signal_path,
            "not_executed": True,
            "creates_shadow_candidate": bool(
                (prepare_artifact.get("created_records") or {}).get(
                    "shadow_candidate_created"
                )
            ),
            "creates_execution_intent": bool(
                (prepare_artifact.get("created_records") or {}).get(
                    "execution_intent_created"
                )
            ),
            "places_order": False,
            "calls_order_lifecycle": False,
            "live_submit_allowed": False,
            "requires_official_final_gate": True,
            "uses_standing_runtime_authorization": True,
            "requires_explicit_owner_real_submit_authorization": False,
            "requires_official_operation_layer": True,
        },
        "safety_invariants": {
            **_base_safety(allow_prepare_records=True),
            "prepare_records_created": ready,
            "shadow_candidate_created": bool(
                (prepare_artifact.get("created_records") or {}).get(
                    "shadow_candidate_created"
                )
            ),
            "execution_intent_created": bool(
                (prepare_artifact.get("created_records") or {}).get(
                    "execution_intent_created"
                )
            ),
        },
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run one runtime next-attempt observation cycle. Default mode is "
            "read-only and non-mutating."
        ),
    )
    parser.add_argument("--runtime-instance-id", required=True)
    parser.add_argument("--env-file")
    parser.add_argument("--api-base")
    parser.add_argument("--skip-exchange", action="store_true")
    parser.add_argument("--source", choices=["live_market", "sample"], default="live_market")
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
    parser.add_argument("--signal-output-json")
    parser.add_argument(
        "--output-dir",
        default="output/runtime-next-attempt-observation-cycle",
    )
    parser.add_argument(
        "--allow-prepare-records",
        action="store_true",
        help=(
            "Allow official API prepare records after gate clear and signal ready. "
            "Still never submits an order."
        ),
    )
    parser.add_argument("--candidate-id")
    parser.add_argument("--context-id")
    parser.add_argument("--owner-operator-id", default="owner")
    parser.add_argument(
        "--owner-confirmation-reference",
        default="owner-authorized-next-attempt-observation-cycle-prepare",
    )
    parser.add_argument(
        "--reason",
        default="owner reviewed runtime next-attempt observation cycle prepare",
    )
    parser.add_argument("--next-attempt-symbol")
    parser.add_argument("--next-attempt-side")
    parser.add_argument("--next-attempt-family")
    parser.add_argument("--next-attempt-strategy-family-id")
    parser.add_argument("--next-attempt-carrier-id")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    with redirect_stdout(sys.stderr):
        payload = asyncio.run(_build_cycle_artifact(args))
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if payload["status"] in {
        "waiting_for_signal",
        "ready_for_prepare",
        "ready_for_final_gate_preflight",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
