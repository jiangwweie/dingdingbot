#!/usr/bin/env python3
"""Bridge a ready next-attempt cycle into executable readiness and handoff.

RTF-031 starts from an RTF-030 cycle packet:

post-submit next-attempt cycle
-> executable submit readiness preview
-> optional official submit handoff preview

The script is deliberately non-executing. It does not call the official submit
endpoint, create local orders, submit through OrderLifecycle, call exchange,
open/close positions, transfer funds, or create withdrawals.
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

from scripts import runtime_executable_submit_readiness_api_flow as readiness_flow  # noqa: E402
from scripts import runtime_official_submit_handoff_api_flow as handoff_flow  # noqa: E402


ReadinessBuilder = Callable[[argparse.Namespace], dict[str, Any]]
HandoffBuilder = Callable[[argparse.Namespace], dict[str, Any]]


READY_CYCLE_STATUS = "ready_for_final_gate_preflight"
READY_READINESS_STATUS = "ready_for_executable_submit"
READY_HANDOFF_STATUS = "ready_for_official_submit_call"


def _read_json_file(path: str) -> dict[str, Any]:
    payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


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
        "strategy_planning_packet": output_dir
        / f"{flow_id}-strategy-planning-packet.json",
        "executable_readiness_flow": output_dir
        / f"{flow_id}-executable-readiness-flow.json",
        "executable_readiness_packet": output_dir
        / f"{flow_id}-executable-readiness-packet.json",
        "official_submit_handoff_flow": output_dir
        / f"{flow_id}-official-submit-handoff-flow.json",
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )


def _strategy_planning_flow(cycle_packet: dict[str, Any]) -> dict[str, Any]:
    flow = cycle_packet.get("next_attempt_strategy_plan_flow")
    if isinstance(flow, dict):
        return flow
    return {}


def _strategy_planning_packet(cycle_packet: dict[str, Any]) -> dict[str, Any]:
    flow = _strategy_planning_flow(cycle_packet)
    payload = flow.get("api_payload")
    if isinstance(payload, dict):
        return payload
    return flow


def _readiness_args(
    args: argparse.Namespace,
    *,
    strategy_planning_packet_json: Path,
) -> argparse.Namespace:
    return argparse.Namespace(
        runtime_instance_id=args.runtime_instance_id,
        strategy_planning_packet_json=str(strategy_planning_packet_json),
        evidence_json=args.evidence_json,
        first_real_submit_packet_json=args.first_real_submit_packet_json,
        additional_warning=args.readiness_warning,
        additional_blocker=args.readiness_blocker,
        env_file=args.env_file,
        api_base=args.api_base,
    )


def _handoff_args(
    args: argparse.Namespace,
    *,
    readiness_json: Path,
) -> argparse.Namespace:
    return argparse.Namespace(
        runtime_instance_id=args.runtime_instance_id,
        readiness_json=str(readiness_json),
        fresh_submit_authorization_id=args.fresh_submit_authorization_id,
        mode=args.mode,
        owner_confirmed_for_real_submit_action=(
            args.owner_confirmed_for_real_submit_action
        ),
        additional_warning=args.handoff_warning,
        additional_blocker=args.handoff_blocker,
        env_file=args.env_file,
        api_base=args.api_base,
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


def _blocked(
    *,
    args: argparse.Namespace,
    stage: str,
    blockers: list[str],
    warnings: list[str] | None = None,
    paths: dict[str, Path] | None = None,
    cycle_packet: dict[str, Any] | None = None,
    readiness_flow_packet: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "scope": "runtime_cycle_executable_submit_handoff",
        "status": "blocked",
        "blocked_stage": stage,
        "runtime_instance_id": args.runtime_instance_id,
        "cycle_packet": cycle_packet,
        "executable_readiness_flow": readiness_flow_packet,
        "official_submit_handoff_flow": None,
        "artifact_paths": {k: str(v) for k, v in (paths or {}).items()},
        "blockers": blockers,
        "warnings": warnings or [],
        "operator_command_plan": {
            "next_step": "resolve_cycle_readiness_or_handoff_blocker",
            "calls_official_submit_endpoint": False,
            "places_order": False,
            "calls_order_lifecycle": False,
        },
        "safety_invariants": _safety(),
    }


def _build_packet(
    args: argparse.Namespace,
    *,
    readiness_builder: ReadinessBuilder | None = None,
    handoff_builder: HandoffBuilder | None = None,
) -> dict[str, Any]:
    paths = _output_paths(args)
    readiness_builder = readiness_builder or readiness_flow._build_packet
    handoff_builder = handoff_builder or handoff_flow._build_packet

    cycle_packet = _read_json_file(args.cycle_packet_json)
    cycle_status = str(cycle_packet.get("status") or "")
    if cycle_status != READY_CYCLE_STATUS:
        blockers = list(cycle_packet.get("blockers") or [])
        if not blockers:
            blockers.append("cycle_not_ready_for_final_gate_preflight")
        return _blocked(
            args=args,
            stage="post_submit_next_attempt_cycle",
            blockers=blockers,
            warnings=list(cycle_packet.get("warnings") or []),
            paths=paths,
            cycle_packet=cycle_packet,
        )

    strategy_packet = _strategy_planning_packet(cycle_packet)
    if not strategy_packet:
        return _blocked(
            args=args,
            stage="strategy_planning_packet",
            blockers=["strategy_planning_packet_missing_from_cycle"],
            paths=paths,
            cycle_packet=cycle_packet,
        )
    _write_json(paths["strategy_planning_packet"], strategy_packet)

    readiness_packet = readiness_builder(
        _readiness_args(
            args,
            strategy_planning_packet_json=paths["strategy_planning_packet"],
        )
    )
    _write_json(paths["executable_readiness_flow"], readiness_packet)
    readiness_payload = readiness_packet.get("api_payload")
    if not isinstance(readiness_payload, dict):
        readiness_payload = {}
    _write_json(paths["executable_readiness_packet"], readiness_payload)

    readiness_status = str(readiness_packet.get("status") or "")
    if readiness_status != READY_READINESS_STATUS:
        blockers = list(readiness_packet.get("blockers") or [])
        if not blockers:
            blockers.append("executable_readiness_not_ready")
        return _blocked(
            args=args,
            stage="executable_submit_readiness",
            blockers=blockers,
            warnings=list(readiness_packet.get("warnings") or []),
            paths=paths,
            cycle_packet=cycle_packet,
            readiness_flow_packet=readiness_packet,
        )

    if not args.fresh_submit_authorization_id:
        return {
            "scope": "runtime_cycle_executable_submit_handoff",
            "status": "ready_for_fresh_submit_authorization",
            "runtime_instance_id": args.runtime_instance_id,
            "cycle_packet": cycle_packet,
            "executable_readiness_flow": readiness_packet,
            "official_submit_handoff_flow": None,
            "artifact_paths": {k: str(v) for k, v in paths.items()},
            "blockers": [],
            "warnings": list(readiness_packet.get("warnings") or []),
            "operator_command_plan": {
                "next_step": "bind_or_resolve_fresh_submit_authorization",
                "calls_official_submit_endpoint": False,
                "places_order": False,
                "calls_order_lifecycle": False,
                "requires_fresh_submit_authorization": True,
            },
            "safety_invariants": _safety(),
        }

    handoff_packet = handoff_builder(
        _handoff_args(
            args,
            readiness_json=paths["executable_readiness_packet"],
        )
    )
    _write_json(paths["official_submit_handoff_flow"], handoff_packet)
    handoff_status = str(handoff_packet.get("status") or "")
    status = (
        READY_HANDOFF_STATUS
        if handoff_status == READY_HANDOFF_STATUS
        else "blocked"
    )
    return {
        "scope": "runtime_cycle_executable_submit_handoff",
        "status": status,
        "blocked_stage": None if status == READY_HANDOFF_STATUS else "official_submit_handoff",
        "runtime_instance_id": args.runtime_instance_id,
        "cycle_packet": cycle_packet,
        "executable_readiness_flow": readiness_packet,
        "official_submit_handoff_flow": handoff_packet,
        "artifact_paths": {k: str(v) for k, v in paths.items()},
        "blockers": list(handoff_packet.get("blockers") or []),
        "warnings": list(readiness_packet.get("warnings") or [])
        + list(handoff_packet.get("warnings") or []),
        "operator_action_preview": handoff_packet.get("operator_action_preview"),
        "operator_command_plan": {
            "next_step": (
                "call_official_submit_endpoint_after_action_time_final_gate_and_operation_layer_pass"
                if status == READY_HANDOFF_STATUS
                else "resolve_official_submit_handoff_blocker"
            ),
            "calls_official_submit_endpoint": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "requires_owner_chat_confirmation": False,
            "uses_standing_runtime_authorization": status == READY_HANDOFF_STATUS,
            "requires_action_time_final_gate": status == READY_HANDOFF_STATUS,
            "requires_official_operation_layer": status == READY_HANDOFF_STATUS,
            "can_continue_without_owner_chat": status == READY_HANDOFF_STATUS,
            "requires_action_time_confirmation": False,
        },
        "safety_invariants": _safety(),
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Bridge a ready post-submit next-attempt cycle into executable "
            "readiness and optional official submit handoff preview."
        ),
    )
    parser.add_argument("--runtime-instance-id", required=True)
    parser.add_argument("--cycle-packet-json", required=True)
    parser.add_argument("--evidence-json", required=True)
    parser.add_argument("--first-real-submit-packet-json")
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
    parser.add_argument(
        "--output-dir",
        default="output/runtime-cycle-executable-submit-handoff",
    )
    parser.add_argument("--flow-id")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    with redirect_stdout(sys.stderr):
        packet = _build_packet(args)
    print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if packet["status"] in {
        READY_HANDOFF_STATUS,
        "ready_for_fresh_submit_authorization",
        "blocked",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
