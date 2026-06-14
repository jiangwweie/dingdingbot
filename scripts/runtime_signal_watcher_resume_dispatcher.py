#!/usr/bin/env python3
"""Dispatch the Runtime Signal Watcher resume packet to the next safe step.

The default mode consumes post-signal-resume-pack.json and writes an
Owner/agent-readable dispatch packet without calling the API. With
``--execute-preflight`` it may call the official action-time FinalGate preflight
GET endpoint and persist that preflight result. When FinalGate passes, it writes
the official Operation Layer submit endpoint plan for the next checkpoint. It
never calls Operation Layer, OrderLifecycle, exchange APIs, or order-submit
endpoints.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
from typing import Any
import urllib.error
import urllib.request


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


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
OPERATION_LAYER_ACTION = "prepare_official_operation_layer_submit"
SESSION_COOKIE_ENV = "BRC_OPERATOR_SESSION_COOKIE"
SESSION_COOKIE_FALLBACK_ENV = "OWNER_BOUNDED_SESSION_COOKIE"
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


def _session_cookie() -> tuple[str | None, str | None]:
    explicit = (
        os.environ.get(SESSION_COOKIE_ENV)
        or os.environ.get(SESSION_COOKIE_FALLBACK_ENV)
        or ""
    ).strip()
    if explicit:
        if "=" in explicit:
            return explicit, None
        try:
            from src.interfaces.operator_auth import SESSION_COOKIE
        except Exception as exc:
            return None, f"operator_session_cookie_name_unavailable:{type(exc).__name__}"
        return f"{SESSION_COOKIE}={explicit}", None

    try:
        from src.interfaces.operator_auth import SESSION_COOKIE, _load_auth_config, _sign_payload

        config = _load_auth_config()
        now = int(time.time())
        token = _sign_payload(
            {
                "sub": config.username,
                "iat": now,
                "exp": now + min(config.ttl_seconds, 3600),
                "scope": "brc_operator_console",
            },
            config.session_secret,
        )
        return f"{SESSION_COOKIE}={token}", None
    except Exception as exc:
        return None, f"operator_session_unavailable:{type(exc).__name__}"


def _request_json(
    *,
    method: str,
    url: str,
    cookie: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        method=method,
        headers={"Accept": "application/json", "Cookie": cookie},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
            return {
                "http_status": response.status,
                "body": json.loads(raw) if raw else None,
                "error": False,
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body: Any = json.loads(raw)
        except json.JSONDecodeError:
            body = raw
        return {"http_status": exc.code, "body": body, "error": True}
    except Exception as exc:
        return {
            "http_status": None,
            "body": None,
            "error": True,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }


def _preflight_forbidden_effects(body: Any) -> list[str]:
    payload = _dict(body)
    effects: list[str] = []
    checks = {
        "submit_executed": False,
        "order_created": False,
        "exchange_called": False,
        "owner_bounded_execution_called": False,
        "order_lifecycle_called": False,
    }
    for name, expected in checks.items():
        if payload.get(name) is not expected:
            effects.append(f"preflight_effect:{name}")
    return effects


def _preflight_passed(body: Any) -> bool:
    payload = _dict(body)
    return (
        payload.get("status") == "ready_for_controlled_submit_adapter"
        and payload.get("final_gate_verdict") == "pass"
        and not payload.get("blockers")
    )


def _preflight_blockers(body: Any) -> list[str]:
    payload = _dict(body)
    blockers = [str(item) for item in _list(payload.get("blockers")) if str(item).strip()]
    if payload.get("status") not in {None, "ready_for_controlled_submit_adapter"}:
        blockers.append(f"preflight_status:{payload.get('status')}")
    verdict = payload.get("final_gate_verdict")
    if verdict not in {None, "pass"}:
        blockers.append(f"final_gate_verdict:{verdict}")
    return sorted(set(blockers))


def build_dispatch_packet(
    *,
    resume_pack: dict[str, Any],
    source_path: Path,
    api_base: str = DEFAULT_API_BASE,
    label: str = "tokyo-runtime-signal-watcher",
    execute_preflight: bool = False,
    preflight_timeout_seconds: int = 120,
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
        packet = _packet(
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
        if not execute_preflight:
            return packet
        return _execute_finalgate_preflight(
            packet=packet,
            timeout_seconds=preflight_timeout_seconds,
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
    finalgate_preflight_result: dict[str, Any] | None = None,
    operation_layer_command_plan: dict[str, Any] | None = None,
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
        "finalgate_preflight_result": finalgate_preflight_result,
        "operation_layer_command_plan": operation_layer_command_plan,
        "blockers": blockers,
        "warnings": list(resume_pack.get("warnings") or []),
        "safety_invariants": {
            "dispatcher_only": finalgate_preflight_result is None,
            "official_finalgate_preflight_called": finalgate_preflight_result is not None,
            "places_order": False,
            "calls_order_lifecycle": False,
            "exchange_write_called": False,
            "mutates_pg": False,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
            "official_operation_layer_submit_called": False,
        },
    }


def _execute_finalgate_preflight(
    *,
    packet: dict[str, Any],
    timeout_seconds: int,
) -> dict[str, Any]:
    command_plan = _dict(packet.get("command_plan"))
    if command_plan.get("method") != "GET" or not command_plan.get("curl"):
        return _packet_from_preflight(
            packet=packet,
            status="blocked",
            blocker_class="hard_safety_stop",
            dispatch_status="blocked_by_invalid_preflight_command_plan",
            blockers=["invalid_preflight_command_plan"],
            preflight_result=None,
            operation_layer_command_plan=None,
        )

    cookie, cookie_error = _session_cookie()
    if not cookie:
        return _packet_from_preflight(
            packet=packet,
            status="blocked",
            blocker_class="deployment_issue",
            dispatch_status="blocked_by_operator_session_unavailable",
            blockers=[cookie_error or "operator_session_unavailable"],
            preflight_result={
                "called": False,
                "http_status": None,
                "body": None,
                "error": cookie_error or "operator_session_unavailable",
            },
            operation_layer_command_plan=None,
        )

    url = str(command_plan["api_base"]).rstrip("/") + str(command_plan["path"])
    response = _request_json(
        method="GET",
        url=url,
        cookie=cookie,
        timeout_seconds=timeout_seconds,
    )
    preflight_result = {
        "called": True,
        "method": "GET",
        "path": command_plan["path"],
        "http_status": response.get("http_status"),
        "body": response.get("body"),
        "error": bool(response.get("error")),
        "error_type": response.get("error_type"),
        "error_message": response.get("error_message"),
        "places_order": False,
        "calls_order_lifecycle": False,
        "exchange_write_called": False,
    }

    http_status = response.get("http_status")
    if http_status in {401, 403}:
        return _packet_from_preflight(
            packet=packet,
            status="blocked",
            blocker_class="deployment_issue",
            dispatch_status="blocked_by_operator_session_http_error",
            blockers=[f"operator_session_http_status:{http_status}"],
            preflight_result=preflight_result,
            operation_layer_command_plan=None,
        )
    if response.get("error"):
        blocker_class = "missing_fact" if http_status == 404 else "deployment_issue"
        return _packet_from_preflight(
            packet=packet,
            status="blocked",
            blocker_class=blocker_class,
            dispatch_status="blocked_by_finalgate_preflight_http_error",
            blockers=[f"finalgate_preflight_http_status:{http_status or 'unavailable'}"],
            preflight_result=preflight_result,
            operation_layer_command_plan=None,
        )

    forbidden_effects = _preflight_forbidden_effects(response.get("body"))
    if forbidden_effects:
        return _packet_from_preflight(
            packet=packet,
            status="blocked",
            blocker_class="hard_safety_stop",
            dispatch_status="blocked_by_finalgate_preflight_forbidden_effect",
            blockers=forbidden_effects,
            preflight_result=preflight_result,
            operation_layer_command_plan=None,
        )

    if not _preflight_passed(response.get("body")):
        blockers = _preflight_blockers(response.get("body"))
        return _packet_from_preflight(
            packet=packet,
            status="blocked",
            blocker_class="hard_safety_stop",
            dispatch_status="blocked_by_action_time_finalgate",
            blockers=blockers or ["runtime_final_gate_execution_check_not_passed"],
            preflight_result=preflight_result,
            operation_layer_command_plan=None,
        )

    operation_layer_command_plan = {
        "kind": "official_operation_layer_submit_next_checkpoint",
        "status": "pending_required_submit_evidence",
        "next_action": OPERATION_LAYER_ACTION,
        "authorization_id": packet["command_plan"]["prepared_authorization_id"],
        "official_endpoint_method": "POST",
        "official_endpoint_path": (
            "/api/trading-console/"
            "runtime-execution-first-real-submit-actions/authorizations/"
            f"{packet['command_plan']['prepared_authorization_id']}"
        ),
        "official_query_mode": "real_gateway_action_after_required_evidence",
        "owner_confirmed_for_first_real_submit_action": True,
        "requires_official_operation_layer": True,
        "requires_standing_authorization": True,
        "requires_evidence_ids": [
            "trusted_submit_fact_snapshot_id",
            "submit_idempotency_policy_id",
            "attempt_outcome_policy_id",
            "protection_creation_failure_policy_id",
            "local_registration_enablement_decision_id",
            "owner_real_submit_authorization_id",
            "order_lifecycle_submit_enablement_id",
            "exchange_submit_adapter_enablement_id",
            "exchange_submit_action_authorization_id",
            "deployment_readiness_evidence_id",
        ],
        "places_order": False,
        "exchange_write_called": False,
        "order_lifecycle_called": False,
        "automatic_recovery_action": (
            "prepare_official_operation_layer_submit_evidence_from_passed_preflight"
        ),
    }
    return _packet_from_preflight(
        packet=packet,
        status="finalgate_ready",
        blocker_class="none",
        dispatch_status="official_finalgate_preflight_passed",
        blockers=[],
        preflight_result=preflight_result,
        operation_layer_command_plan=operation_layer_command_plan,
    )


def _packet_from_preflight(
    *,
    packet: dict[str, Any],
    status: str,
    blocker_class: str,
    dispatch_status: str,
    blockers: list[str],
    preflight_result: dict[str, Any] | None,
    operation_layer_command_plan: dict[str, Any] | None,
) -> dict[str, Any]:
    owner_state = _owner_state_for_preflight(
        status=status,
        blocker_class=blocker_class,
        dispatch_status=dispatch_status,
        blockers=blockers,
    )
    return {
        **packet,
        "status": status,
        "blocker_class": blocker_class,
        "dispatch_status": dispatch_status,
        "dispatch_action": (
            OPERATION_LAYER_ACTION if status == "finalgate_ready" else None
        ),
        "owner_state": owner_state,
        "finalgate_preflight_result": preflight_result,
        "operation_layer_command_plan": operation_layer_command_plan,
        "blockers": blockers,
        "safety_invariants": {
            **_dict(packet.get("safety_invariants")),
            "dispatcher_only": False,
            "official_finalgate_preflight_called": preflight_result is not None
            and bool(preflight_result.get("called")),
            "places_order": False,
            "calls_order_lifecycle": False,
            "exchange_write_called": False,
            "mutates_pg": False,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
            "official_operation_layer_submit_called": False,
        },
    }


def _owner_state_for_preflight(
    *,
    status: str,
    blocker_class: str,
    dispatch_status: str,
    blockers: list[str],
) -> dict[str, Any]:
    if status == "finalgate_ready":
        return {
            "status": "finalgate_ready",
            "blocker_class": "none",
            "blocked_at": "none",
            "blocked_reason": "none",
            "next_recover_condition": "official_operation_layer_submit_evidence_is_prepared",
            "automatic_recovery_action": (
                "prepare_official_operation_layer_submit_evidence_from_passed_preflight"
            ),
            "downgrade_mode": "none",
        }
    if dispatch_status in {
        "blocked_by_operator_session_unavailable",
        "blocked_by_operator_session_http_error",
    }:
        return {
            "status": "blocked",
            "blocker_class": blocker_class,
            "blocked_at": "operator_session",
            "blocked_reason": dispatch_status,
            "next_recover_condition": "operator_session_available_for_local_official_preflight",
            "automatic_recovery_action": "restore_operator_session_or_local_session_signing",
            "downgrade_mode": "continue_watcher_observation_no_submit",
        }
    if dispatch_status == "blocked_by_action_time_finalgate":
        return {
            "status": "blocked",
            "blocker_class": blocker_class,
            "blocked_at": "FinalGate",
            "blocked_reason": blockers[0] if blockers else "action_time_finalgate_blocked",
            "next_recover_condition": "fresh_action_time_facts_pass_finalgate",
            "automatic_recovery_action": "refresh_action_time_facts_or_downgrade_to_observation",
            "downgrade_mode": "observe_only_no_submit",
        }
    return {
        "status": "blocked",
        "blocker_class": blocker_class,
        "blocked_at": "FinalGate",
        "blocked_reason": blockers[0] if blockers else dispatch_status,
        "next_recover_condition": "preflight_blocker_resolved",
        "automatic_recovery_action": "retry_official_action_time_finalgate_preflight_after_repair",
        "downgrade_mode": "continue_watcher_observation_no_submit",
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a Runtime Signal Watcher resume dispatch packet, optionally "
            "calling the official action-time FinalGate preflight GET."
        ),
    )
    parser.add_argument("--resume-pack-json", default=str(DEFAULT_RESUME_PACK))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--label", default="tokyo-runtime-signal-watcher")
    parser.add_argument(
        "--execute-preflight",
        action="store_true",
        help="Call the official GET-only action-time FinalGate preflight when ready.",
    )
    parser.add_argument(
        "--preflight-timeout-seconds",
        type=int,
        default=120,
        help="HTTP timeout for --execute-preflight.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    source_path = Path(args.resume_pack_json).expanduser()
    packet = build_dispatch_packet(
        resume_pack=_read_json(source_path),
        source_path=source_path,
        api_base=args.api_base,
        label=args.label,
        execute_preflight=args.execute_preflight,
        preflight_timeout_seconds=args.preflight_timeout_seconds,
    )
    _write_json(Path(args.output_json).expanduser(), packet)
    print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if packet["status"] in {
        WAITING_STATUS,
        READY_STATUS,
        "finalgate_ready",
        "blocked",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
