#!/usr/bin/env python3
"""Prepare the next runtime attempt through the official Console API.

This is a small semantic wrapper around ``runtime_first_real_submit_api_flow``
prepare mode. It may create the pre-submit governance records needed for the
next attempt, but it never arms submit, mutates attempt counters, calls
OrderLifecycle, places exchange orders, or moves funds.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import json
import os
from pathlib import Path
import sys
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.runtime_first_real_submit_api_flow import (  # noqa: E402
    DEFAULT_API_BASE,
    API_BASE_ENV as FIRST_REAL_SUBMIT_API_BASE_ENV,
    FirstRealSubmitApiFlow,
    FlowConfig,
    UrlLibApiClient,
)


API_BASE_ENV = "RUNTIME_NEXT_ATTEMPT_PREPARE_API_BASE"


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


def _api_base(args: argparse.Namespace) -> str:
    return (
        args.api_base
        or os.environ.get(API_BASE_ENV)
        or os.environ.get(FIRST_REAL_SUBMIT_API_BASE_ENV)
        or DEFAULT_API_BASE
    )


def _build_flow_config(args: argparse.Namespace) -> FlowConfig:
    return FlowConfig(
        api_base=_api_base(args),
        mode="prepare",
        order_candidate_id=args.order_candidate_id,
        signal_input_path=args.signal_input_json,
        runtime_instance_id=args.runtime_instance_id,
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
        skip_next_attempt_gate_check=False,
        skip_order_candidate_usage_check=False,
        enable_local_registration=False,
        arm_exchange_submit_adapter=False,
        record_gateway_readiness=False,
        execute_real_submit=False,
        record_post_submit_accounting=False,
    )


def _summarize_prepare_report(report: dict[str, Any]) -> dict[str, Any]:
    ids = dict(report.get("ids") or {})
    steps = list(report.get("steps") or [])
    blockers = list(report.get("blockers") or [])
    ready = (
        not blockers
        and bool(ids.get("authorization_id"))
        and bool(ids.get("execution_intent_id"))
        and bool(ids.get("runtime_execution_intent_draft_id"))
    )
    step_names = [str(item.get("name") or "") for item in steps if isinstance(item, dict)]
    return {
        "scope": "runtime_next_attempt_prepare_packet",
        "status": "ready_for_final_gate_preflight" if ready else "blocked",
        "first_real_submit_prepare_report": report,
        "ids": ids,
        "next_attempt_gate": report.get("next_attempt_gate") or {},
        "blockers": blockers,
        "warnings": list(report.get("warnings") or []),
        "operator_command_plan": {
            "scope": "runtime_next_attempt_prepare_operator_command_plan",
            "next_step": (
                "run_official_final_gate_preflight"
                if ready
                else "resolve_prepare_blockers"
            ),
            "prepared_authorization_id": ids.get("authorization_id"),
            "not_executed": True,
            "live_submit_allowed": False,
            "requires_official_final_gate": True,
            "requires_explicit_owner_real_submit_authorization": True,
            "places_order": False,
            "calls_order_lifecycle": False,
        },
        "created_records": {
            "shadow_candidate_created": "create_shadow_candidate_from_signal_input" in step_names,
            "runtime_execution_intent_draft_created": bool(
                ids.get("runtime_execution_intent_draft_id")
            ),
            "execution_intent_created": bool(ids.get("execution_intent_id")),
            "submit_authorization_created": bool(ids.get("authorization_id")),
            "protection_plan_created": bool(ids.get("protection_plan_id")),
            "attempt_reservation_created": False,
            "attempt_mutation_created": False,
            "order_lifecycle_handoff_created": False,
        },
        "safety_invariants": {
            "uses_official_trading_console_api": True,
            "next_attempt_gate_checked": bool(report.get("next_attempt_gate")),
            "local_registration_armed": False,
            "exchange_submit_armed": False,
            "execute_real_submit": False,
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "attempt_counter_mutated": False,
            "runtime_budget_mutated": False,
            "position_opened": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare the next runtime attempt without submit authority.",
    )
    parser.add_argument("--env-file")
    parser.add_argument("--api-base")
    parser.add_argument("--runtime-instance-id")
    parser.add_argument("--signal-input-json")
    parser.add_argument("--order-candidate-id")
    parser.add_argument("--candidate-id")
    parser.add_argument("--context-id")
    parser.add_argument("--owner-operator-id", default="owner")
    parser.add_argument(
        "--owner-confirmation-reference",
        default="owner-authorized-next-attempt-prepare",
    )
    parser.add_argument(
        "--reason",
        default="owner reviewed next runtime attempt prepare",
    )
    parser.add_argument("--next-attempt-symbol")
    parser.add_argument("--next-attempt-side")
    parser.add_argument("--next-attempt-family")
    parser.add_argument("--next-attempt-strategy-family-id")
    parser.add_argument("--next-attempt-carrier-id")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    _load_env_file(args.env_file)
    if not args.order_candidate_id and not args.signal_input_json:
        payload = {
            "scope": "runtime_next_attempt_prepare_packet",
            "status": "blocked",
            "blockers": ["order_candidate_id_or_signal_input_json_required"],
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "withdrawal_or_transfer_created": False,
            },
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 2

    config = _build_flow_config(args)
    with redirect_stdout(sys.stderr):
        report = FirstRealSubmitApiFlow(
            client=UrlLibApiClient(api_base=config.api_base),
            config=config,
        ).run()
    payload = _summarize_prepare_report(report)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if payload["status"] == "ready_for_final_gate_preflight" else 1


if __name__ == "__main__":
    raise SystemExit(main())
