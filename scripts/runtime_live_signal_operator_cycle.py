#!/usr/bin/env python3
"""Run one non-executing live-signal operator cycle for a runtime.

RTF-067 composes:

live signal routing
-> wait / profile proposal / current-runtime prepare route
-> optional prepare records when explicitly enabled

Default mode does not create records. With ``--allow-prepare-records`` it may
create the official non-executing prepare records for a ready current-runtime
signal, but it still does not arm local registration, submit orders, call
OrderLifecycle, write to exchange, mutate runtime budget, or move funds.
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import redirect_stdout
import json
from pathlib import Path
import sys
from typing import Any, Callable


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import runtime_live_signal_routing_packet as routing_script  # noqa: E402
from scripts import runtime_next_attempt_prepare_api_flow as prepare_script  # noqa: E402


RoutingBuilder = Callable[[argparse.Namespace], Any]
PrepareRunner = Callable[[argparse.Namespace, str], dict[str, Any]]

WAITING_STATUS = "waiting_for_runtime_compatible_signal"
READY_PROFILE_STATUS = "ready_for_owner_runtime_profile_decision"
READY_FOR_PREPARE_STATUS = "ready_for_prepare"
READY_FOR_FINAL_GATE_PREFLIGHT = "ready_for_final_gate_preflight"


async def _build_packet(
    args: argparse.Namespace,
    *,
    routing_builder: RoutingBuilder | None = None,
    prepare_runner: PrepareRunner | None = None,
) -> dict[str, Any]:
    routing = await _build_routing_packet(args, routing_builder=routing_builder)
    routing_status = str(routing.get("status") or "")
    if routing_status == routing_script.READY_CURRENT_RUNTIME_STATUS:
        return _handle_ready_current_runtime(
            args,
            routing_packet=routing,
            prepare_runner=prepare_runner,
        )
    if routing_status == READY_PROFILE_STATUS:
        return _base_packet(
            args=args,
            status=READY_PROFILE_STATUS,
            routing_packet=routing,
            prepare_packet=None,
            next_step="owner_codex_review_runtime_profile_proposal_before_runtime_creation",
        )
    if routing_status == WAITING_STATUS:
        return _base_packet(
            args=args,
            status=WAITING_STATUS,
            routing_packet=routing,
            prepare_packet=None,
            next_step="continue_live_signal_observation_without_forcing_entry",
        )
    return _base_packet(
        args=args,
        status="blocked",
        routing_packet=routing,
        prepare_packet=None,
        next_step="resolve_live_signal_routing_blocker",
        extra_blockers=list(routing.get("blockers") or []),
    )


async def _build_routing_packet(
    args: argparse.Namespace,
    *,
    routing_builder: RoutingBuilder | None,
) -> dict[str, Any]:
    routing_args = argparse.Namespace(
        runtime_instance_id=args.runtime_instance_id,
        env_file=args.env_file,
        source=args.source,
        output_signal_input_json=args.output_signal_input_json,
        capital_base=args.capital_base,
        signal_index=args.signal_index,
        output_json=None,
    )
    builder = routing_builder or routing_script._build_packet
    return await builder(routing_args)


def _handle_ready_current_runtime(
    args: argparse.Namespace,
    *,
    routing_packet: dict[str, Any],
    prepare_runner: PrepareRunner | None,
) -> dict[str, Any]:
    signal_input_json = routing_packet.get("signal_input_json")
    if not isinstance(signal_input_json, str) or not signal_input_json.strip():
        return _base_packet(
            args=args,
            status="blocked",
            routing_packet=routing_packet,
            prepare_packet=None,
            next_step="rerun_routing_until_signal_input_json_is_available",
            extra_blockers=["ready_current_runtime_signal_input_json_missing"],
        )

    if not args.allow_prepare_records:
        return _base_packet(
            args=args,
            status=READY_FOR_PREPARE_STATUS,
            routing_packet=routing_packet,
            prepare_packet=None,
            next_step="rerun_with_allow_prepare_records_after_operator_review",
        )

    setattr(
        args,
        "routing_runtime_profile",
        routing_packet.get("runtime_profile") or {},
    )
    runner = prepare_runner or _run_prepare_flow
    prepare_packet = runner(args, signal_input_json)
    status = str(prepare_packet.get("status") or "blocked")
    return _base_packet(
        args=args,
        status=status,
        routing_packet=routing_packet,
        prepare_packet=prepare_packet,
        next_step=(
            "run_official_final_gate_preflight"
            if status == READY_FOR_FINAL_GATE_PREFLIGHT
            else "resolve_prepare_blockers"
        ),
    )


def _run_prepare_flow(args: argparse.Namespace, signal_input_json: str) -> dict[str, Any]:
    prepare_args = _prepare_args(args, signal_input_json=signal_input_json)
    config = prepare_script._build_flow_config(prepare_args)
    report = prepare_script.FirstRealSubmitApiFlow(
        client=prepare_script.UrlLibApiClient(api_base=config.api_base),
        config=config,
    ).run()
    return prepare_script._summarize_prepare_report(report)


def _prepare_args(args: argparse.Namespace, *, signal_input_json: str) -> argparse.Namespace:
    profile = args.routing_runtime_profile if hasattr(args, "routing_runtime_profile") else {}
    if not isinstance(profile, dict):
        profile = {}
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
        next_attempt_symbol=args.next_attempt_symbol or profile.get("symbol"),
        next_attempt_side=args.next_attempt_side or profile.get("side"),
        next_attempt_family=args.next_attempt_family,
        next_attempt_strategy_family_id=(
            args.next_attempt_strategy_family_id
            or profile.get("strategy_family_id")
        ),
        next_attempt_carrier_id=(
            args.next_attempt_carrier_id
            or profile.get("strategy_family_version_id")
        ),
    )


def _base_packet(
    *,
    args: argparse.Namespace,
    status: str,
    routing_packet: dict[str, Any],
    prepare_packet: dict[str, Any] | None,
    next_step: str,
    extra_blockers: list[str] | None = None,
) -> dict[str, Any]:
    blockers = [
        *list(extra_blockers or []),
        *list(routing_packet.get("blockers") or []),
    ]
    if isinstance(prepare_packet, dict):
        blockers.extend(f"prepare:{item}" for item in prepare_packet.get("blockers") or [])
    warnings = list(routing_packet.get("warnings") or [])
    if isinstance(prepare_packet, dict):
        warnings.extend(f"prepare:{item}" for item in prepare_packet.get("warnings") or [])
    safety = _safety(
        allow_prepare_records=args.allow_prepare_records,
        routing_packet=routing_packet,
        prepare_packet=prepare_packet,
    )
    return {
        "scope": "runtime_live_signal_operator_cycle",
        "status": status,
        "runtime_instance_id": args.runtime_instance_id,
        "routing_packet": routing_packet,
        "prepare_packet": prepare_packet,
        "signal_input_json": routing_packet.get("signal_input_json"),
        "profile_proposal_packet": routing_packet.get("profile_proposal_packet"),
        "blockers": _dedupe(blockers),
        "warnings": _dedupe(warnings),
        "operator_command_plan": {
            "next_step": next_step,
            "allow_prepare_records": args.allow_prepare_records,
            "current_runtime_prepare_allowed": (
                status in {READY_FOR_PREPARE_STATUS, READY_FOR_FINAL_GATE_PREFLIGHT}
            ),
            "requires_owner_runtime_profile_confirmation": status == READY_PROFILE_STATUS,
            "prepared_authorization_id": (
                (prepare_packet.get("operator_command_plan") or {}).get(
                    "prepared_authorization_id"
                )
                if isinstance(prepare_packet, dict)
                else None
            ),
            "creates_runtime": False,
            "mutates_runtime_profile": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "requires_real_submit_gate": status == READY_FOR_FINAL_GATE_PREFLIGHT,
        },
        "safety_invariants": safety,
    }


def _safety(
    *,
    allow_prepare_records: bool,
    routing_packet: dict[str, Any],
    prepare_packet: dict[str, Any] | None,
) -> dict[str, bool]:
    routing_safety = _as_dict(routing_packet.get("safety_invariants"))
    prepare_safety = (
        _as_dict(prepare_packet.get("safety_invariants"))
        if isinstance(prepare_packet, dict)
        else {}
    )
    created = (
        _as_dict(prepare_packet.get("created_records"))
        if isinstance(prepare_packet, dict)
        else {}
    )

    def flag(name: str) -> bool:
        return bool(routing_safety.get(name) or prepare_safety.get(name))

    return {
        "live_signal_operator_cycle": True,
        "allow_prepare_records": allow_prepare_records,
        "routing_packet_created": True,
        "prepare_flow_called": prepare_packet is not None,
        "prepare_records_created": bool(
            prepare_packet
            and prepare_packet.get("status") == READY_FOR_FINAL_GATE_PREFLIGHT
        ),
        "shadow_candidate_created": bool(created.get("shadow_candidate_created")),
        "runtime_execution_intent_draft_created": bool(
            created.get("runtime_execution_intent_draft_created")
        ),
        "recorded_execution_intent_created": bool(created.get("execution_intent_created")),
        "submit_authorization_created": bool(created.get("submit_authorization_created")),
        "protection_plan_created": bool(created.get("protection_plan_created")),
        "runtime_created": flag("runtime_created"),
        "runtime_profile_mutated": flag("runtime_profile_mutated"),
        "local_registration_armed": flag("local_registration_armed"),
        "exchange_submit_armed": flag("exchange_submit_armed"),
        "execute_real_submit": flag("execute_real_submit"),
        "exchange_write_called": flag("exchange_write_called"),
        "order_created": flag("order_created"),
        "order_lifecycle_called": flag("order_lifecycle_called"),
        "attempt_counter_mutated": flag("attempt_counter_mutated"),
        "runtime_budget_mutated": flag("runtime_budget_mutated"),
        "position_opened": flag("position_opened"),
        "position_closed": flag("position_closed"),
        "withdrawal_or_transfer_created": flag("withdrawal_or_transfer_created"),
    }


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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
        description="Run one live signal operator cycle without submit authority.",
    )
    parser.add_argument("--runtime-instance-id", required=True)
    parser.add_argument("--env-file")
    parser.add_argument("--api-base")
    parser.add_argument(
        "--source",
        choices=["sample", "local_sqlite_fallback", "live_market"],
        default="live_market",
    )
    parser.add_argument("--output-signal-input-json")
    parser.add_argument("--capital-base", default="30")
    parser.add_argument("--signal-index", type=int, default=0)
    parser.add_argument("--allow-prepare-records", action="store_true")
    parser.add_argument("--candidate-id")
    parser.add_argument("--context-id")
    parser.add_argument("--owner-operator-id", default="owner")
    parser.add_argument(
        "--owner-confirmation-reference",
        default="owner-authorized-live-signal-operator-cycle",
    )
    parser.add_argument(
        "--reason",
        default="owner reviewed live signal operator cycle",
    )
    parser.add_argument("--next-attempt-symbol")
    parser.add_argument("--next-attempt-side")
    parser.add_argument("--next-attempt-family")
    parser.add_argument("--next-attempt-strategy-family-id")
    parser.add_argument("--next-attempt-carrier-id")
    parser.add_argument("--output-json")
    return parser.parse_args(argv)


def _main(
    argv: list[str] | None = None,
    *,
    routing_builder: RoutingBuilder | None = None,
    prepare_runner: PrepareRunner | None = None,
) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    with redirect_stdout(sys.stderr):
        packet = asyncio.run(
            _build_packet(
                args,
                routing_builder=routing_builder,
                prepare_runner=prepare_runner,
            )
        )
    payload = json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    if args.output_json:
        output_path = Path(args.output_json).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if packet["status"] in {
        WAITING_STATUS,
        READY_PROFILE_STATUS,
        READY_FOR_PREPARE_STATUS,
        READY_FOR_FINAL_GATE_PREFLIGHT,
    } else 2


def main(argv: list[str] | None = None) -> int:
    return _main(argv)


def main_with_builders_for_test(
    *,
    routing_builder: RoutingBuilder | None = None,
    prepare_runner: PrepareRunner | None = None,
) -> int:
    return _main(routing_builder=routing_builder, prepare_runner=prepare_runner)


if __name__ == "__main__":
    raise SystemExit(main())
