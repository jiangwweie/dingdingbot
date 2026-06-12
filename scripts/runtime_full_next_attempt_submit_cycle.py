#!/usr/bin/env python3
"""Run one full non-executing next-attempt submit-preparation cycle.

RTF-032 composes the current runtime mainline proof:

post-submit finalize
-> fresh strategy signal planning
-> executable submit readiness
-> optional official submit handoff preview

The script intentionally stops at the earliest honest state. If the fresh
strategy signal is observe-only, it returns ``waiting_for_signal`` and does not
run executable readiness. If readiness is ready but no fresh submit
authorization is supplied, it returns ``ready_for_fresh_submit_authorization``.

It never calls the official submit endpoint, creates local orders, submits
through OrderLifecycle, calls exchange, opens/closes positions, transfers funds,
or creates withdrawals.
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

from scripts import runtime_cycle_executable_submit_handoff as handoff_bridge  # noqa: E402
from scripts import runtime_post_submit_next_attempt_cycle as next_attempt_cycle  # noqa: E402


CycleBuilder = Callable[[argparse.Namespace], dict[str, Any]]
HandoffBridgeBuilder = Callable[[argparse.Namespace], dict[str, Any]]


READY_FOR_FINAL_GATE_PREFLIGHT = "ready_for_final_gate_preflight"
READY_FOR_FRESH_SUBMIT_AUTHORIZATION = "ready_for_fresh_submit_authorization"
READY_FOR_OFFICIAL_SUBMIT_CALL = "ready_for_official_submit_call"
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
        "post_submit_next_attempt_cycle": output_dir
        / f"{cycle_id}-post-submit-next-attempt-cycle.json",
        "cycle_executable_submit_handoff": output_dir
        / f"{cycle_id}-cycle-executable-submit-handoff.json",
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )


def _cycle_args(args: argparse.Namespace, *, output_dir: Path) -> argparse.Namespace:
    metadata = {
        **_load_json_object(args.metadata_json),
        "runtime_full_next_attempt_submit_cycle": True,
        "full_cycle_stage": "post_submit_next_attempt_cycle",
    }
    return argparse.Namespace(
        runtime_instance_id=args.runtime_instance_id,
        reservation_id=args.reservation_id,
        signal_input_json=args.signal_input_json,
        authorization_id=args.authorization_id,
        closed_review_required=args.closed_review_required,
        protection_blocker=args.protection_blocker,
        env_file=args.env_file,
        api_base=args.api_base,
        context_id=args.context_id,
        expires_at_ms=args.expires_at_ms,
        metadata_json=json.dumps(metadata, ensure_ascii=False),
        output_dir=str(output_dir),
        cycle_id=args.cycle_id,
    )


def _load_cycle_packet(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _handoff_args(
    args: argparse.Namespace,
    *,
    cycle_packet_json: Path,
    output_dir: Path,
) -> argparse.Namespace:
    return argparse.Namespace(
        runtime_instance_id=args.runtime_instance_id,
        cycle_packet_json=str(cycle_packet_json),
        evidence_json=args.evidence_json,
        first_real_submit_packet_json=args.first_real_submit_packet_json,
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
        output_dir=str(output_dir),
        flow_id=args.cycle_id,
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
        "execution_intent_created": False,
        "executable_execution_intent_created": False,
        "exchange_write_called": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "attempt_counter_mutated": False,
        "runtime_budget_mutated": False,
        "position_opened": False,
        "position_closed": False,
        "withdrawal_or_transfer_created": False,
    }


def _operator_next_step(status: str) -> str:
    if status == WAITING_FOR_SIGNAL:
        return "observe_or_wait_for_next_strategy_signal"
    if status == READY_FOR_FRESH_SUBMIT_AUTHORIZATION:
        return "bind_or_resolve_fresh_submit_authorization"
    if status == READY_FOR_OFFICIAL_SUBMIT_CALL:
        return "call_official_submit_endpoint_after_action_time_confirmation"
    if status == READY_FOR_FINAL_GATE_PREFLIGHT:
        return "run_executable_readiness_after_evidence_available"
    return "resolve_full_cycle_blocker"


def _build_packet(
    args: argparse.Namespace,
    *,
    cycle_builder: CycleBuilder | None = None,
    handoff_bridge_builder: HandoffBridgeBuilder | None = None,
) -> dict[str, Any]:
    paths = _output_paths(args)
    cycle_output_dir = paths["post_submit_next_attempt_cycle"].parent / "cycle"
    handoff_output_dir = paths["cycle_executable_submit_handoff"].parent / "handoff"
    cycle_builder = cycle_builder or next_attempt_cycle._build_cycle_packet
    handoff_bridge_builder = handoff_bridge_builder or handoff_bridge._build_packet

    cycle_packet = (
        _load_cycle_packet(args.cycle_packet_json)
        if args.cycle_packet_json
        else cycle_builder(
            _cycle_args(args, output_dir=cycle_output_dir),
        )
    )
    _write_json(paths["post_submit_next_attempt_cycle"], cycle_packet)

    cycle_status = str(cycle_packet.get("status") or "")
    if cycle_status != READY_FOR_FINAL_GATE_PREFLIGHT:
        return {
            "scope": "runtime_full_next_attempt_submit_cycle",
            "status": cycle_status if cycle_status else "blocked",
            "blocked_stage": cycle_packet.get("blocked_stage"),
            "runtime_instance_id": args.runtime_instance_id,
            "post_submit_next_attempt_cycle": cycle_packet,
            "cycle_executable_submit_handoff": None,
            "artifact_paths": {k: str(v) for k, v in paths.items()},
            "blockers": list(cycle_packet.get("blockers") or []),
            "warnings": list(cycle_packet.get("warnings") or []),
            "operator_command_plan": {
                "next_step": _operator_next_step(cycle_status),
                "runs_executable_readiness": False,
                "calls_official_submit_endpoint": False,
                "places_order": False,
                "calls_order_lifecycle": False,
            },
            "safety_invariants": _safety(),
        }

    if not args.evidence_json:
        return {
            "scope": "runtime_full_next_attempt_submit_cycle",
            "status": READY_FOR_FINAL_GATE_PREFLIGHT,
            "runtime_instance_id": args.runtime_instance_id,
            "post_submit_next_attempt_cycle": cycle_packet,
            "cycle_executable_submit_handoff": None,
            "artifact_paths": {k: str(v) for k, v in paths.items()},
            "blockers": [],
            "warnings": ["executable_readiness_evidence_json_missing"],
            "operator_command_plan": {
                "next_step": _operator_next_step(READY_FOR_FINAL_GATE_PREFLIGHT),
                "runs_executable_readiness": False,
                "calls_official_submit_endpoint": False,
                "places_order": False,
                "calls_order_lifecycle": False,
                "requires_executable_readiness_evidence": True,
            },
            "safety_invariants": _safety(),
        }

    handoff_packet = handoff_bridge_builder(
        _handoff_args(
            args,
            cycle_packet_json=paths["post_submit_next_attempt_cycle"],
            output_dir=handoff_output_dir,
        )
    )
    _write_json(paths["cycle_executable_submit_handoff"], handoff_packet)
    handoff_status = str(handoff_packet.get("status") or "")
    return {
        "scope": "runtime_full_next_attempt_submit_cycle",
        "status": handoff_status if handoff_status else "blocked",
        "blocked_stage": handoff_packet.get("blocked_stage"),
        "runtime_instance_id": args.runtime_instance_id,
        "post_submit_next_attempt_cycle": cycle_packet,
        "cycle_executable_submit_handoff": handoff_packet,
        "artifact_paths": {k: str(v) for k, v in paths.items()},
        "blockers": list(handoff_packet.get("blockers") or []),
        "warnings": list(cycle_packet.get("warnings") or [])
        + list(handoff_packet.get("warnings") or []),
        "operator_command_plan": {
            "next_step": _operator_next_step(handoff_status),
            "runs_executable_readiness": True,
            "calls_official_submit_endpoint": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "requires_action_time_confirmation": (
                handoff_status == READY_FOR_OFFICIAL_SUBMIT_CALL
            ),
        },
        "safety_invariants": _safety(),
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run one full non-executing runtime next-attempt submit-preparation "
            "cycle."
        ),
    )
    parser.add_argument("--runtime-instance-id", required=True)
    parser.add_argument("--reservation-id")
    parser.add_argument("--signal-input-json", required=True)
    parser.add_argument(
        "--cycle-packet-json",
        help=(
            "Optional existing RTF-030 cycle packet. When supplied, reuse this "
            "artifact instead of rerunning the post-submit next-attempt cycle."
        ),
    )
    parser.add_argument("--authorization-id")
    parser.add_argument("--closed-review-required", action="store_true")
    parser.add_argument("--protection-blocker", action="append")
    parser.add_argument("--evidence-json")
    parser.add_argument("--first-real-submit-packet-json")
    parser.add_argument("--fresh-submit-authorization-id")
    parser.add_argument(
        "--mode",
        choices=("disabled_smoke", "real_gateway_action"),
        default="disabled_smoke",
    )
    parser.add_argument("--owner-confirmed-for-real-submit-action", action="store_true")
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
        default="output/runtime-full-next-attempt-submit-cycle",
    )
    parser.add_argument("--cycle-id")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    with redirect_stdout(sys.stderr):
        packet = _build_packet(args)
    print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if packet["status"] in {
        READY_FOR_FINAL_GATE_PREFLIGHT,
        READY_FOR_FRESH_SUBMIT_AUTHORIZATION,
        READY_FOR_OFFICIAL_SUBMIT_CALL,
        WAITING_FOR_SIGNAL,
        "blocked",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
