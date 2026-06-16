#!/usr/bin/env python3
"""Supervise active runtime observation and authorized non-executing follow-up."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.runtime_active_observation_status import build_status_packet  # noqa: E402

DEFAULT_API_BASE = "http://127.0.0.1:18080"


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    stdout_path: str
    returncode: int
    stderr_tail: str


Runner = Callable[[list[str], Path], CommandResult]


def _json_or_none(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _loop_command(
    args: argparse.Namespace,
    loop_packet_path: Path,
    status_packet_path: Path,
) -> list[str]:
    command = [
        sys.executable,
        str(ROOT_DIR / "scripts" / "runtime_active_observation_loop.py"),
        "--max-iterations",
        str(args.max_iterations),
        "--loop-interval-seconds",
        str(args.loop_interval_seconds),
        "--cycle-timeout-seconds",
        str(args.cycle_timeout_seconds),
        "--api-base",
        args.api_base,
        "--source",
        args.source,
        "--output-dir",
        str(Path(args.output_dir).expanduser()),
        "--loop-output-json",
        str(loop_packet_path),
        "--status-output-json",
        str(status_packet_path),
        "--status-stale-after-seconds",
        str(args.status_stale_after_seconds),
        "--one-hour-limit",
        str(args.one_hour_limit),
        "--four-hour-limit",
        str(args.four_hour_limit),
    ]
    if args.env_file:
        command.extend(["--env-file", args.env_file])
    for runtime_instance_id in args.runtime_instance_id or []:
        command.extend(["--runtime-instance-id", runtime_instance_id])
    for strategy_family_id in args.strategy_family_id or []:
        command.extend(["--strategy-family-id", strategy_family_id])
    if args.allow_prepare_records:
        command.append("--allow-prepare-records")
    if args.include_packets:
        command.append("--include-packets")
    return command


def _followup_command(args: argparse.Namespace, loop_packet_path: Path, followup_path: Path) -> list[str]:
    command = [
        sys.executable,
        str(ROOT_DIR / "scripts" / "runtime_active_observation_followup.py"),
        "--loop-packet-json",
        str(loop_packet_path),
        "--api-base",
        args.api_base,
        "--output-json",
        str(followup_path),
    ]
    if args.env_file:
        command.extend(["--env-file", args.env_file])
    if args.allow_arm_preview:
        command.append("--allow-arm-preview")
    if args.allow_attempt_policy_prepare:
        command.append("--allow-attempt-policy-prepare")
    if args.allow_disabled_smoke:
        command.append("--allow-disabled-smoke")
    if getattr(args, "allow_standing_operation_layer_evidence_prep", False):
        command.append("--allow-standing-operation-layer-evidence-prep")
    if args.skip_disabled_smoke_prerequisite_probe:
        command.append("--skip-disabled-smoke-prerequisite-probe")
    return command


def _run_subprocess(command: list[str], stdout_path: Path) -> CommandResult:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    with stdout_path.open("w", encoding="utf-8") as stdout:
        completed = subprocess.run(
            command,
            check=False,
            text=True,
            stdout=stdout,
            stderr=subprocess.PIPE,
        )
    return CommandResult(
        command=command,
        stdout_path=str(stdout_path),
        returncode=completed.returncode,
        stderr_tail=(completed.stderr or "")[-4000:],
    )


def _forbidden_effects(
    loop_packet: dict[str, Any] | None,
    followup_packet: dict[str, Any] | None,
    *,
    allow_attempt_policy_prepare: bool = False,
    allow_standing_operation_layer_evidence_prep: bool = False,
) -> list[str]:
    effects: list[str] = []
    for source_name, packet in (
        ("loop", loop_packet),
        ("followup", followup_packet),
    ):
        if not isinstance(packet, dict):
            continue
        safety = packet.get("safety_invariants")
        if not isinstance(safety, dict):
            continue
        forbidden_keys = [
            "exchange_write_called",
            "exchange_called",
            "exchange_order_submitted",
            "executable_execution_intent_created",
            "real_submit_requested",
            "creates_execution_intent",
            "places_order",
            "calls_order_lifecycle",
            "order_created",
            "order_lifecycle_called",
            "order_lifecycle_submit_called",
            "withdrawal_or_transfer_created",
        ]
        forbidden_keys.extend(
            [
                "attempt_counter_mutated",
                "runtime_budget_mutated",
            ]
        )
        if (
            source_name == "followup"
            and allow_standing_operation_layer_evidence_prep
            and safety.get("standing_authorized_operation_layer_evidence_prep_called")
            is True
        ):
            forbidden_keys = [
                key
                for key in forbidden_keys
                if key
                not in {
                    "attempt_counter_mutated",
                    "runtime_budget_mutated",
                }
            ]
        for key in forbidden_keys:
            if safety.get(key) is True:
                effects.append(f"{source_name}.{key}")
        for item in safety.get("loop_forbidden_effects") or []:
            effects.append(f"{source_name}.loop_forbidden_effect:{item}")
        for item in safety.get("arm_preview_forbidden_effects") or []:
            effects.append(f"{source_name}.arm_preview_forbidden_effect:{item}")
        for item in safety.get("disabled_smoke_forbidden_effects") or []:
            effects.append(f"{source_name}.disabled_smoke_forbidden_effect:{item}")
    return sorted(set(effects))


def build_supervisor_packet(
    args: argparse.Namespace,
    *,
    runner: Runner | None = None,
) -> dict[str, Any]:
    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    loop_packet_path = Path(args.loop_output_json).expanduser() if args.loop_output_json else output_dir / "loop-packet.json"
    followup_path = Path(args.followup_output_json).expanduser() if args.followup_output_json else output_dir / "followup-packet.json"
    supervisor_packet_path = (
        Path(args.supervisor_output_json).expanduser()
        if args.supervisor_output_json
        else output_dir / "supervisor-packet.json"
    )
    status_packet_path = (
        Path(args.status_output_json).expanduser()
        if args.status_output_json
        else output_dir / "status-packet.json"
    )
    loop_stdout_path = output_dir / "loop-final-stdout.json"
    followup_stdout_path = output_dir / "followup-stdout.json"

    command_runner = runner or _run_subprocess
    loop_command = _loop_command(args, loop_packet_path, status_packet_path)
    _write_json(
        supervisor_packet_path,
        _running_supervisor_packet(
            args,
            output_dir=output_dir,
            loop_packet_path=loop_packet_path,
            followup_path=followup_path,
            status_packet_path=status_packet_path,
            loop_command=loop_command,
        ),
    )
    _write_status_packet(
        output_dir=output_dir,
        status_packet_path=status_packet_path,
        stale_after_seconds=args.status_stale_after_seconds,
    )
    loop_result = command_runner(loop_command, loop_stdout_path)
    loop_packet = _json_or_none(loop_packet_path)

    followup_result: CommandResult | None = None
    followup_packet: dict[str, Any] | None = None
    if loop_packet is not None:
        followup_result = command_runner(
            _followup_command(args, loop_packet_path, followup_path),
            followup_stdout_path,
        )
        followup_packet = _json_or_none(followup_path)

    blockers: list[str] = []
    if loop_result.returncode != 0:
        blockers.append(f"loop_command_failed:{loop_result.returncode}")
    if loop_packet is None:
        blockers.append("loop_packet_missing")
    if followup_result and followup_result.returncode != 0:
        blockers.append(f"followup_command_failed:{followup_result.returncode}")
    if loop_packet is not None and followup_result is None:
        blockers.append("followup_command_not_run")
    if followup_result and followup_packet is None:
        blockers.append("followup_packet_missing")
    forbidden_effects = _forbidden_effects(
        loop_packet,
        followup_packet,
        allow_attempt_policy_prepare=args.allow_attempt_policy_prepare,
        allow_standing_operation_layer_evidence_prep=bool(
            getattr(args, "allow_standing_operation_layer_evidence_prep", False)
        ),
    )
    if forbidden_effects:
        blockers.append("supervisor_detected_forbidden_effects")

    packet = {
        "scope": "runtime_active_observation_supervisor",
        "status": "supervisor_completed" if not blockers else "supervisor_blocked",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "output_dir": str(output_dir),
        "loop_packet_json": str(loop_packet_path),
        "followup_packet_json": str(followup_path),
        "status_packet_json": str(status_packet_path),
        "loop_status": (loop_packet or {}).get("status") if loop_packet else None,
        "followup_status": (
            (followup_packet or {}).get("status") if followup_packet else None
        ),
        "command_results": {
            "loop": loop_result.__dict__,
            "followup": followup_result.__dict__ if followup_result else None,
        },
        "blockers": blockers,
        "warnings": [],
        "operator_command_plan": {
            "not_executed": True,
            "uses_existing_loop_and_followup_scripts": True,
            "real_submit_requested": False,
            "exchange_order_requested": False,
            "next_step": (
                "review_loop_and_followup_packets"
                if not blockers
                else "resolve_supervisor_blockers"
            ),
        },
        "safety_invariants": {
            "supervisor_only": True,
            "allow_prepare_records": bool(args.allow_prepare_records),
            "allow_arm_preview": bool(args.allow_arm_preview),
            "allow_attempt_policy_prepare": bool(args.allow_attempt_policy_prepare),
            "allow_disabled_smoke": bool(args.allow_disabled_smoke),
            "allow_standing_operation_layer_evidence_prep": bool(
                getattr(args, "allow_standing_operation_layer_evidence_prep", False)
            ),
            "real_submit_requested": False,
            "exchange_order_requested": False,
            "order_lifecycle_submit_requested": False,
            "withdrawal_or_transfer_requested": False,
            "forbidden_effects": forbidden_effects,
            "allowed_official_attempt_policy_prepare": bool(
                args.allow_attempt_policy_prepare
                and (followup_packet or {})
                .get("safety_invariants", {})
                .get("attempt_policy_preflight_called")
                is True
                and (followup_packet or {})
                .get("safety_invariants", {})
                .get("attempt_counter_mutated")
                is not True
            ),
        },
    }
    _write_json(supervisor_packet_path, packet)
    _write_status_packet(
        output_dir=output_dir,
        status_packet_path=status_packet_path,
        stale_after_seconds=args.status_stale_after_seconds,
    )
    return packet


def _running_supervisor_packet(
    args: argparse.Namespace,
    *,
    output_dir: Path,
    loop_packet_path: Path,
    followup_path: Path,
    status_packet_path: Path,
    loop_command: list[str],
) -> dict[str, Any]:
    return {
        "scope": "runtime_active_observation_supervisor",
        "status": "supervisor_running",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "output_dir": str(output_dir),
        "loop_packet_json": str(loop_packet_path),
        "followup_packet_json": str(followup_path),
        "status_packet_json": str(status_packet_path),
        "loop_status": None,
        "followup_status": None,
        "command_results": {
            "loop": {
                "command": loop_command,
                "stdout_path": str(output_dir / "loop-final-stdout.json"),
                "returncode": None,
                "stderr_tail": "",
            },
            "followup": None,
        },
        "blockers": [],
        "warnings": [],
        "operator_command_plan": {
            "not_executed": True,
            "uses_existing_loop_and_followup_scripts": True,
            "real_submit_requested": False,
            "exchange_order_requested": False,
            "next_step": "wait_for_loop_packet_or_supervisor_completion",
        },
        "safety_invariants": {
            "supervisor_only": True,
            "allow_prepare_records": bool(args.allow_prepare_records),
            "allow_arm_preview": bool(args.allow_arm_preview),
            "allow_attempt_policy_prepare": bool(args.allow_attempt_policy_prepare),
            "allow_disabled_smoke": bool(args.allow_disabled_smoke),
            "real_submit_requested": False,
            "exchange_order_requested": False,
            "order_lifecycle_submit_requested": False,
            "withdrawal_or_transfer_requested": False,
            "forbidden_effects": [],
        },
    }


def _write_status_packet(
    *,
    output_dir: Path,
    status_packet_path: Path,
    stale_after_seconds: float,
) -> None:
    packet = build_status_packet(
        output_dir,
        stale_after_seconds=stale_after_seconds,
    )
    _write_json(status_packet_path, packet)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run active runtime observation loop and non-executing follow-up.",
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--supervisor-output-json")
    parser.add_argument("--loop-output-json")
    parser.add_argument("--followup-output-json")
    parser.add_argument("--status-output-json")
    parser.add_argument("--env-file")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--source", choices=["live_market", "sample"], default="live_market")
    parser.add_argument(
        "--runtime-instance-id",
        action="append",
        default=[],
        help=(
            "Limit the active observation loop to the given ACTIVE runtime "
            "instance. May be repeated."
        ),
    )
    parser.add_argument(
        "--strategy-family-id",
        action="append",
        default=[],
        help=(
            "Limit the active observation loop to ACTIVE runtimes belonging "
            "to this strategy family. May be repeated."
        ),
    )
    parser.add_argument("--max-iterations", type=int, default=1)
    parser.add_argument("--loop-interval-seconds", type=float, default=0.0)
    parser.add_argument("--cycle-timeout-seconds", type=float, default=180.0)
    parser.add_argument("--status-stale-after-seconds", type=float, default=900.0)
    parser.add_argument("--one-hour-limit", type=int, default=25)
    parser.add_argument("--four-hour-limit", type=int, default=25)
    parser.add_argument("--allow-prepare-records", action="store_true")
    parser.add_argument("--allow-arm-preview", action="store_true")
    parser.add_argument("--allow-attempt-policy-prepare", action="store_true")
    parser.add_argument("--allow-disabled-smoke", action="store_true")
    parser.add_argument(
        "--allow-standing-operation-layer-evidence-prep",
        action="store_true",
    )
    parser.add_argument("--include-packets", action="store_true")
    parser.add_argument("--skip-disabled-smoke-prerequisite-probe", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    packet = build_supervisor_packet(args)
    output_path = (
        Path(args.supervisor_output_json).expanduser()
        if args.supervisor_output_json
        else Path(args.output_dir).expanduser() / "supervisor-packet.json"
    )
    _write_json(output_path, packet)
    print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if packet["status"] == "supervisor_completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
