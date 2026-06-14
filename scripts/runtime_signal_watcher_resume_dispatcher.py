#!/usr/bin/env python3
"""Dispatch the Runtime Signal Watcher resume packet to the next safe step.

This dispatcher is deliberately non-executing. It consumes
post-signal-resume-pack.json and writes an Owner/agent-readable dispatch packet.
It does not call FinalGate, Operation Layer, OrderLifecycle, exchange APIs, or
PG. When a fresh prepared authorization is available, it emits the official API
command plan for the action-time controlled-submit preflight.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Any


DEFAULT_RESUME_PACK = Path(
    "/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/"
    "post-signal-resume-pack.json"
)
DEFAULT_OUTPUT_JSON = Path(
    "/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/"
    "resume-dispatch-packet.json"
)
DEFAULT_API_BASE = "http://127.0.0.1:18080"
READY_STATUS = "ready_for_action_time_final_gate"
WAITING_STATUS = "waiting_for_market"
FINALGATE_ACTION = "run_official_action_time_final_gate_preflight"
CONTINUE_ACTION = "continue_watcher_observation"
UNSAFE_TRUE_FLAGS = {
    "places_order",
    "calls_order_lifecycle",
    "exchange_write_called",
    "withdrawal_or_transfer_requested",
    "withdrawal_or_transfer_created",
    "runtime_budget_mutated",
    "mutates_pg",
    "order_created",
}
READY_REQUIRED_FIELDS = (
    "signal_input_json",
    "shadow_candidate_id",
    "prepared_authorization_id",
)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
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


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _nonempty(value: Any) -> bool:
    return bool(str(value or "").strip())


def _unsafe_flags(resume_pack: dict[str, Any]) -> list[str]:
    action_time_resume = _dict(resume_pack.get("action_time_resume"))
    safety = _dict(resume_pack.get("safety_invariants"))
    flags: list[str] = []
    for source in (action_time_resume, safety):
        for name in sorted(UNSAFE_TRUE_FLAGS):
            if source.get(name) not in {False, None, "", 0}:
                flags.append(name)
    for name in _list(safety.get("forbidden_effect_flags")):
        if str(name).strip():
            flags.append(str(name))
    return sorted(set(flags))


def _missing_ready_fields(
    resume_pack: dict[str, Any],
    action_time_resume: dict[str, Any],
) -> list[str]:
    return [
        name
        for name in READY_REQUIRED_FIELDS
        if not _nonempty(action_time_resume.get(name) or resume_pack.get(name))
    ]


def _preflight_command_plan(
    *,
    api_base: str,
    authorization_id: str,
    signal_input_json: str,
    shadow_candidate_id: str,
) -> dict[str, Any]:
    endpoint = (
        "/api/trading-console/"
        f"runtime-execution-controlled-submit-preflights/authorizations/{authorization_id}"
    )
    return {
        "kind": "official_action_time_finalgate_preflight",
        "method": "GET",
        "api_base": api_base.rstrip("/"),
        "path": endpoint,
        "curl": (
            "curl -fsS "
            f"{api_base.rstrip('/')}{endpoint}"
        ),
        "prepared_authorization_id": authorization_id,
        "signal_input_json": signal_input_json,
        "shadow_candidate_id": shadow_candidate_id,
        "requires_operator_session": True,
        "places_order": False,
        "calls_order_lifecycle": False,
        "exchange_write_called": False,
    }


def build_dispatch_packet(
    *,
    resume_pack: dict[str, Any],
    source_path: Path,
    api_base: str = DEFAULT_API_BASE,
    label: str = "tokyo-runtime-signal-watcher",
) -> dict[str, Any]:
    action_time_resume = _dict(resume_pack.get("action_time_resume"))
    owner_state = _dict(resume_pack.get("owner_state"))
    status = str(action_time_resume.get("status") or resume_pack.get("status") or "")
    allowed_auto_actions = [
        str(item)
        for item in _list(action_time_resume.get("allowed_auto_actions"))
        if str(item).strip()
    ]
    unsafe_flags = _unsafe_flags(resume_pack)
    base_blockers = [
        str(item)
        for item in _list(resume_pack.get("blockers"))
        if str(item).strip()
    ]

    if unsafe_flags:
        return _packet(
            label=label,
            source_path=source_path,
            resume_pack=resume_pack,
            action_time_resume=action_time_resume,
            owner_state=owner_state,
            status="blocked",
            blocker_class="hard_safety_stop",
            dispatch_action=None,
            dispatch_status="blocked_by_unsafe_resume_flags",
            blockers=base_blockers + [f"unsafe_flag:{name}" for name in unsafe_flags],
            command_plan=None,
        )

    if status == WAITING_STATUS:
        return _packet(
            label=label,
            source_path=source_path,
            resume_pack=resume_pack,
            action_time_resume=action_time_resume,
            owner_state=owner_state,
            status=WAITING_STATUS,
            blocker_class="waiting_for_market",
            dispatch_action=CONTINUE_ACTION,
            dispatch_status="no_action_continue_observation",
            blockers=[],
            command_plan=None,
        )

    if status == READY_STATUS:
        if FINALGATE_ACTION not in allowed_auto_actions:
            return _packet(
                label=label,
                source_path=source_path,
                resume_pack=resume_pack,
                action_time_resume=action_time_resume,
                owner_state=owner_state,
                status="blocked",
                blocker_class="hard_safety_stop",
                dispatch_action=None,
                dispatch_status="blocked_by_resume_allowed_actions",
                blockers=base_blockers + [
                    "allowed_auto_actions_missing_finalgate_preflight"
                ],
                command_plan=None,
            )
        missing = _missing_ready_fields(resume_pack, action_time_resume)
        if missing:
            return _packet(
                label=label,
                source_path=source_path,
                resume_pack=resume_pack,
                action_time_resume=action_time_resume,
                owner_state=owner_state,
                status="blocked",
                blocker_class="missing_fact",
                dispatch_action=None,
                dispatch_status="blocked_by_missing_preflight_evidence",
                blockers=base_blockers + [f"missing_fact:{name}" for name in missing],
                command_plan=None,
            )

        authorization_id = str(
            action_time_resume.get("prepared_authorization_id")
            or resume_pack.get("prepared_authorization_id")
        )
        signal_input_json = str(
            action_time_resume.get("signal_input_json")
            or resume_pack.get("signal_input_json")
        )
        shadow_candidate_id = str(
            action_time_resume.get("shadow_candidate_id")
            or resume_pack.get("shadow_candidate_id")
        )
        return _packet(
            label=label,
            source_path=source_path,
            resume_pack=resume_pack,
            action_time_resume=action_time_resume,
            owner_state=owner_state,
            status=READY_STATUS,
            blocker_class="none",
            dispatch_action=FINALGATE_ACTION,
            dispatch_status="official_finalgate_preflight_dispatch_ready",
            blockers=[],
            command_plan=_preflight_command_plan(
                api_base=api_base,
                authorization_id=authorization_id,
                signal_input_json=signal_input_json,
                shadow_candidate_id=shadow_candidate_id,
            ),
        )

    return _packet(
        label=label,
        source_path=source_path,
        resume_pack=resume_pack,
        action_time_resume=action_time_resume,
        owner_state=owner_state,
        status="blocked",
        blocker_class="hard_safety_stop",
        dispatch_action=None,
        dispatch_status="blocked_by_unknown_resume_status",
        blockers=base_blockers + [f"unknown_resume_status:{status or 'missing'}"],
        command_plan=None,
    )


def _packet(
    *,
    label: str,
    source_path: Path,
    resume_pack: dict[str, Any],
    action_time_resume: dict[str, Any],
    owner_state: dict[str, Any],
    status: str,
    blocker_class: str,
    dispatch_action: str | None,
    dispatch_status: str,
    blockers: list[str],
    command_plan: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "scope": "runtime_signal_watcher_resume_dispatcher",
        "label": label,
        "generated_at_ms": int(time.time() * 1000),
        "source_resume_pack": str(source_path),
        "status": status,
        "blocker_class": blocker_class,
        "dispatch_status": dispatch_status,
        "dispatch_action": dispatch_action,
        "owner_state": owner_state,
        "selected_runtime_instance_ids": list(
            resume_pack.get("selected_runtime_instance_ids") or []
        ),
        "action_time_resume": action_time_resume,
        "command_plan": command_plan,
        "blockers": blockers,
        "warnings": list(resume_pack.get("warnings") or []),
        "safety_invariants": {
            "dispatcher_only": True,
            "places_order": False,
            "calls_order_lifecycle": False,
            "exchange_write_called": False,
            "mutates_pg": False,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
            "official_operation_layer_submit_called": False,
        },
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a non-executing Runtime Signal Watcher resume dispatch packet.",
    )
    parser.add_argument("--resume-pack-json", default=str(DEFAULT_RESUME_PACK))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--label", default="tokyo-runtime-signal-watcher")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    source_path = Path(args.resume_pack_json).expanduser()
    packet = build_dispatch_packet(
        resume_pack=_read_json(source_path),
        source_path=source_path,
        api_base=args.api_base,
        label=args.label,
    )
    _write_json(Path(args.output_json).expanduser(), packet)
    print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if packet["status"] in {WAITING_STATUS, READY_STATUS, "blocked"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
