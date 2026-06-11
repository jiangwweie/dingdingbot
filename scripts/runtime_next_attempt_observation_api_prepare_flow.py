#!/usr/bin/env python3
"""Bridge runtime next-attempt observation API to the official prepare flow.

Default mode calls the Trading Console observation API and, when a signal is
ready, writes the embedded signal input JSON for operator review. It creates
prepare records only when ``--allow-prepare-records`` is explicitly supplied.

It never arms local registration, never arms exchange submit, never calls
OrderLifecycle, never submits orders, and never moves funds.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.runtime_first_real_submit_api_flow import (  # noqa: E402
    DEFAULT_API_BASE,
    API_BASE_ENV as FIRST_REAL_SUBMIT_API_BASE_ENV,
    UrlLibApiClient,
)
from scripts import runtime_next_attempt_prepare_api_flow as prepare_script  # noqa: E402


API_BASE_ENV = "RUNTIME_NEXT_ATTEMPT_OBSERVATION_API_BASE"


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
        or os.environ.get(prepare_script.API_BASE_ENV)
        or os.environ.get(FIRST_REAL_SUBMIT_API_BASE_ENV)
        or DEFAULT_API_BASE
    )


def _signal_output_path(args: argparse.Namespace) -> Path:
    if args.signal_output_json:
        return Path(args.signal_output_json).expanduser()
    runtime_id = args.runtime_instance_id.replace("/", "_").replace(":", "_")
    return (
        Path(args.output_dir).expanduser()
        / f"{runtime_id}-next-attempt-observation-signal-input.json"
    )


def _observation_body(args: argparse.Namespace) -> dict[str, Any]:
    keys = [
        "source",
        "include_exchange",
        "symbol",
        "side",
        "family",
        "strategy_family_id",
        "carrier_id",
        "quantity",
        "target_notional_usdt",
        "max_notional",
        "leverage",
        "max_attempts",
        "protection_mode",
        "review_requirement",
        "evaluation_id",
        "playbook_id",
        "one_hour_limit",
        "four_hour_limit",
        "timeout_seconds",
    ]
    body = {key: getattr(args, key) for key in keys}
    body["non_executing"] = True
    body["allow_prepare_records"] = False
    return {key: value for key, value in body.items() if value is not None}


def _request_observation(
    *,
    client: Any,
    args: argparse.Namespace,
) -> dict[str, Any]:
    return client.request_json(
        "POST",
        (
            "/api/trading-console/strategy-runtimes/"
            f"{args.runtime_instance_id}/next-attempt-observation-cycle"
        ),
        body=_observation_body(args),
    )


def _write_signal_input(
    *,
    args: argparse.Namespace,
    observation_payload: dict[str, Any],
) -> str | None:
    signal_packet = observation_payload.get("signal_packet")
    if not isinstance(signal_packet, dict):
        return None
    signal_input = signal_packet.get("signal_input")
    if not isinstance(signal_input, dict):
        return None
    output_path = _signal_output_path(args)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(signal_input, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return str(output_path)


def _prepare_args(
    args: argparse.Namespace,
    *,
    signal_input_json: str,
) -> argparse.Namespace:
    return argparse.Namespace(
        env_file=args.env_file,
        api_base=_api_base(args),
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


def _run_prepare_flow(
    args: argparse.Namespace,
    *,
    signal_input_json: str,
) -> dict[str, Any]:
    prepare_args = _prepare_args(args, signal_input_json=signal_input_json)
    config = prepare_script._build_flow_config(prepare_args)
    report = prepare_script.FirstRealSubmitApiFlow(
        client=prepare_script.UrlLibApiClient(api_base=config.api_base),
        config=config,
    ).run()
    return prepare_script._summarize_prepare_report(report)


def _safety(*, allow_prepare_records: bool, prepare_packet: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "uses_official_trading_console_api": True,
        "allow_prepare_records": allow_prepare_records,
        "prepare_records_created": bool(
            prepare_packet
            and prepare_packet.get("status") == "ready_for_final_gate_preflight"
        ),
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


def _build_packet(
    args: argparse.Namespace,
    *,
    client: Any | None = None,
    prepare_runner: Callable[[argparse.Namespace, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    _load_env_file(args.env_file)
    api_client = client or UrlLibApiClient(api_base=_api_base(args))
    observation_response = _request_observation(client=api_client, args=args)
    observation_payload = observation_response.get("body")
    if not isinstance(observation_payload, dict):
        observation_payload = {}

    http_status = int(observation_response.get("http_status") or 0)
    signal_input_json = (
        _write_signal_input(args=args, observation_payload=observation_payload)
        if http_status < 300
        else None
    )
    observation_status = str(observation_payload.get("status") or "unknown")
    if http_status >= 300:
        return {
            "scope": "runtime_next_attempt_observation_api_prepare_flow",
            "status": "blocked",
            "blocked_stage": "observation_api",
            "runtime_instance_id": args.runtime_instance_id,
            "observation_http_status": http_status,
            "observation_payload": observation_payload,
            "signal_input_json": signal_input_json,
            "prepare_packet": None,
            "blockers": [f"observation_api_http_{http_status}"],
            "warnings": [],
            "operator_command_plan": {
                "next_step": "resolve_observation_api_error",
                "not_executed": True,
                "places_order": False,
                "calls_order_lifecycle": False,
            },
            "safety_invariants": _safety(
                allow_prepare_records=args.allow_prepare_records,
                prepare_packet=None,
            ),
        }

    if observation_status != "ready_for_prepare":
        return {
            "scope": "runtime_next_attempt_observation_api_prepare_flow",
            "status": observation_status
            if observation_status in {"waiting_for_signal", "blocked"}
            else "blocked",
            "blocked_stage": observation_payload.get("blocked_stage"),
            "runtime_instance_id": args.runtime_instance_id,
            "observation_http_status": http_status,
            "observation_payload": observation_payload,
            "signal_input_json": signal_input_json,
            "prepare_packet": None,
            "blockers": list(observation_payload.get("blockers") or []),
            "warnings": list(observation_payload.get("warnings") or []),
            "operator_command_plan": {
                "next_step": (
                    (observation_payload.get("operator_command_plan") or {}).get(
                        "next_step"
                    )
                    or "wait_for_ready_signal"
                ),
                "signal_input_json": signal_input_json,
                "not_executed": True,
                "creates_shadow_candidate": False,
                "creates_execution_intent": False,
                "places_order": False,
                "calls_order_lifecycle": False,
            },
            "safety_invariants": _safety(
                allow_prepare_records=args.allow_prepare_records,
                prepare_packet=None,
            ),
        }

    if not signal_input_json:
        return {
            "scope": "runtime_next_attempt_observation_api_prepare_flow",
            "status": "blocked",
            "blocked_stage": "signal_input_json",
            "runtime_instance_id": args.runtime_instance_id,
            "observation_http_status": http_status,
            "observation_payload": observation_payload,
            "signal_input_json": None,
            "prepare_packet": None,
            "blockers": ["ready_observation_signal_input_missing"],
            "warnings": [],
            "operator_command_plan": {
                "next_step": "rerun_observation_until_signal_input_embedded",
                "not_executed": True,
                "places_order": False,
                "calls_order_lifecycle": False,
            },
            "safety_invariants": _safety(
                allow_prepare_records=args.allow_prepare_records,
                prepare_packet=None,
            ),
        }

    if not args.allow_prepare_records:
        return {
            "scope": "runtime_next_attempt_observation_api_prepare_flow",
            "status": "ready_for_prepare",
            "runtime_instance_id": args.runtime_instance_id,
            "observation_http_status": http_status,
            "observation_payload": observation_payload,
            "signal_input_json": signal_input_json,
            "prepare_packet": None,
            "blockers": [],
            "warnings": list(observation_payload.get("warnings") or []),
            "operator_command_plan": {
                "next_step": "rerun_with_allow_prepare_records_after_owner_review",
                "signal_input_json": signal_input_json,
                "not_executed": True,
                "creates_shadow_candidate": False,
                "creates_execution_intent": False,
                "places_order": False,
                "calls_order_lifecycle": False,
                "requires_official_final_gate": True,
                "requires_explicit_owner_real_submit_authorization": True,
            },
            "safety_invariants": _safety(
                allow_prepare_records=False,
                prepare_packet=None,
            ),
        }

    if prepare_runner is not None:
        prepare_packet = prepare_runner(args, signal_input_json)
    else:
        prepare_packet = _run_prepare_flow(args, signal_input_json=signal_input_json)
    return {
        "scope": "runtime_next_attempt_observation_api_prepare_flow",
        "status": prepare_packet.get("status") or "blocked",
        "runtime_instance_id": args.runtime_instance_id,
        "observation_http_status": http_status,
        "observation_payload": observation_payload,
        "signal_input_json": signal_input_json,
        "prepare_packet": prepare_packet,
        "blockers": list(prepare_packet.get("blockers") or []),
        "warnings": list(prepare_packet.get("warnings") or []),
        "operator_command_plan": {
            "next_step": (
                "run_official_final_gate_preflight"
                if prepare_packet.get("status") == "ready_for_final_gate_preflight"
                else "resolve_prepare_blockers"
            ),
            "signal_input_json": signal_input_json,
            "prepared_authorization_id": (
                (prepare_packet.get("operator_command_plan") or {}).get(
                    "prepared_authorization_id"
                )
            ),
            "not_executed": True,
            "places_order": False,
            "calls_order_lifecycle": False,
            "live_submit_allowed": False,
            "requires_official_final_gate": True,
            "requires_explicit_owner_real_submit_authorization": True,
        },
        "safety_invariants": _safety(
            allow_prepare_records=True,
            prepare_packet=prepare_packet,
        ),
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Call the runtime next-attempt observation API and optionally create "
            "official prepare records when the signal is ready."
        ),
    )
    parser.add_argument("--runtime-instance-id", required=True)
    parser.add_argument("--env-file")
    parser.add_argument("--api-base")
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
    parser.add_argument("--four-hour-limit", type=int, default=12)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--signal-output-json")
    parser.add_argument(
        "--output-dir",
        default="output/runtime-next-attempt-observation-api-prepare-flow",
    )
    parser.add_argument("--allow-prepare-records", action="store_true")
    parser.add_argument("--candidate-id")
    parser.add_argument("--context-id")
    parser.add_argument("--owner-operator-id", default="owner")
    parser.add_argument(
        "--owner-confirmation-reference",
        default="owner-authorized-next-attempt-observation-api-prepare",
    )
    parser.add_argument(
        "--reason",
        default="owner reviewed runtime next-attempt observation API prepare",
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
        payload = _build_packet(args)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if payload["status"] in {
        "waiting_for_signal",
        "ready_for_prepare",
        "ready_for_final_gate_preflight",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
