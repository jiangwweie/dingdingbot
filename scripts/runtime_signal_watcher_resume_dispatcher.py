#!/usr/bin/env python3
"""Dispatch the Runtime Signal Watcher resume packet to the next safe step.

The default mode consumes post-signal-resume-pack.json and writes an
Owner/agent-readable dispatch packet without calling the API. With
``--execute-preflight`` it may call the official action-time FinalGate preflight
GET endpoint, or the official fresh-submit-authorization binding endpoint when
the resume pack is parked at that non-executing checkpoint. When FinalGate
passes, it writes the official Operation Layer submit endpoint plan for the next
checkpoint. It never calls Operation Layer, OrderLifecycle, exchange APIs, or
order-submit endpoints.
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
DEFAULT_OPERATION_LAYER_EVIDENCE_JSON = Path(
    "/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/"
    "operation-layer-arm-evidence.json"
)
DEFAULT_API_BASE = "http://127.0.0.1:18080"
READY_STATUS = "ready_for_action_time_final_gate"
FINALGATE_READY_STATUS = "finalgate_ready"
WAITING_STATUS = "waiting_for_market"
FRESH_AUTHORIZATION_STATUSES = {
    "ready_for_fresh_submit_authorization",
    "waiting_for_fresh_authorization",
}
FINALGATE_ACTION = "run_official_action_time_final_gate_preflight"
CONTINUE_ACTION = "continue_watcher_observation"
OPERATION_LAYER_ACTION = "prepare_official_operation_layer_submit"
FRESH_AUTHORIZATION_ACTION = "bind_or_resolve_fresh_submit_authorization"
FRESH_AUTHORIZATION_BINDING_ACTION = "run_official_fresh_submit_authorization_binding"
FRESH_AUTHORIZATION_ALLOWED_ACTIONS = {
    FRESH_AUTHORIZATION_ACTION,
    "bind_or_resolve_fresh_authorization",
    FRESH_AUTHORIZATION_BINDING_ACTION,
}
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
    "prepared_authorization_id",
)
OPERATION_LAYER_REQUIRED_EVIDENCE_IDS = (
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
)
LEGACY_LOCAL_REGISTRATION_PROBE_BLOCKER_FRAGMENTS = (
    "runtimeexecutionorderlifecycleadapterresult_not_found",
    "runtime_execution_order_lifecycle_adapter_result_not_found",
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


def _read_optional_json(path_value: str | None) -> tuple[dict[str, Any] | None, str | None]:
    if not path_value:
        return None, None
    path = Path(path_value).expanduser()
    if not path.exists():
        return None, None
    try:
        return _read_json(path), str(path)
    except Exception as exc:
        return {
            "blockers": [
                f"operation_layer_evidence_report_unreadable:{type(exc).__name__}"
            ],
            "warnings": [],
            "ids": {},
        }, str(path)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dedupe_text(values: Any) -> list[str]:
    items: list[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if text and text not in items:
            items.append(text)
    return items


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
    signal_input_json: str | None,
    shadow_candidate_id: str | None,
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
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json", "Cookie": cookie}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        url,
        method=method,
        data=data,
        headers=headers,
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
    status = str(
        payload.get("status") or payload.get("controlled_submit_plan_status") or ""
    ).lower()
    verdict = str(payload.get("final_gate_verdict") or "").lower()
    return (
        status == "ready_for_controlled_submit_adapter"
        and verdict == "pass"
        and not payload.get("blockers")
    )


def _preflight_blockers(body: Any) -> list[str]:
    payload = _dict(body)
    blockers = [str(item) for item in _list(payload.get("blockers")) if str(item).strip()]
    raw_status = payload.get("status") or payload.get("controlled_submit_plan_status")
    normalized_status = str(raw_status or "").lower()
    if raw_status is not None and normalized_status != "ready_for_controlled_submit_adapter":
        blockers.append(f"preflight_status:{raw_status}")
    verdict = payload.get("final_gate_verdict")
    if verdict is not None and str(verdict).lower() != "pass":
        blockers.append(f"final_gate_verdict:{verdict}")
    return sorted(set(blockers))


def _allowed_auto_actions(
    *,
    resume_pack: dict[str, Any],
    action_time_resume: dict[str, Any],
) -> list[str]:
    actions = [
        str(item)
        for item in _list(action_time_resume.get("allowed_auto_actions"))
        if str(item).strip()
    ]
    if actions:
        return actions
    fallback_sources = (
        action_time_resume.get("next_step"),
        action_time_resume.get("automatic_recovery_action"),
        resume_pack.get("automatic_recovery_action"),
        _dict(resume_pack.get("operator_command_plan")).get("next_step"),
    )
    return [str(item) for item in fallback_sources if str(item or "").strip()]


def _first_text(*values: Any) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _fresh_authorization_handoff_json_path(
    *,
    resume_pack: dict[str, Any],
    action_time_resume: dict[str, Any],
) -> str | None:
    artifact_paths = _dict(resume_pack.get("artifact_paths"))
    action_artifact_paths = _dict(action_time_resume.get("artifact_paths"))
    readiness_bridge = _dict(resume_pack.get("readiness_bridge"))
    bridge_artifact_paths = _dict(readiness_bridge.get("artifact_paths"))
    return _first_text(
        action_time_resume.get("handoff_json"),
        action_time_resume.get("fresh_submit_handoff_json"),
        action_time_resume.get("readiness_handoff_bridge_json"),
        action_artifact_paths.get("readiness_handoff_bridge"),
        action_artifact_paths.get("official_submit_handoff_flow"),
        resume_pack.get("handoff_json"),
        resume_pack.get("fresh_submit_handoff_json"),
        resume_pack.get("readiness_handoff_bridge_json"),
        artifact_paths.get("readiness_handoff_bridge"),
        artifact_paths.get("official_submit_handoff_flow"),
        artifact_paths.get("cycle_executable_submit_handoff"),
        bridge_artifact_paths.get("readiness_handoff_bridge"),
        bridge_artifact_paths.get("official_submit_handoff_flow"),
    )


def _unwrap_handoff_packet(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("handoff_id"):
        return payload
    for key in ("api_payload", "packet"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            return _unwrap_handoff_packet(nested)
    for key in (
        "official_submit_handoff_flow",
        "readiness_handoff_bridge",
        "cycle_executable_submit_handoff",
    ):
        nested = payload.get(key)
        if isinstance(nested, dict):
            return _unwrap_handoff_packet(nested)
    return {}


def _load_handoff_packet(path_value: str) -> tuple[dict[str, Any], str | None]:
    path = Path(path_value).expanduser()
    try:
        payload = _read_json(path)
    except Exception as exc:
        return {}, f"handoff_json_unreadable:{type(exc).__name__}"
    handoff = _unwrap_handoff_packet(payload)
    if not handoff:
        return {}, "handoff_packet_missing_from_json"
    return handoff, None


def _operation_layer_command_plan(*, authorization_id: str) -> dict[str, Any]:
    return {
        "kind": "official_operation_layer_submit_next_checkpoint",
        "status": "pending_required_submit_evidence",
        "next_action": OPERATION_LAYER_ACTION,
        "authorization_id": authorization_id,
        "official_endpoint_method": "POST",
        "official_endpoint_path": (
            "/api/trading-console/"
            "runtime-execution-first-real-submit-actions/authorizations/"
            f"{authorization_id}"
        ),
        "official_query_mode": "real_gateway_action_after_required_evidence",
        "owner_confirmed_for_first_real_submit_action": True,
        "requires_official_operation_layer": True,
        "requires_standing_authorization": True,
        "requires_evidence_ids": list(OPERATION_LAYER_REQUIRED_EVIDENCE_IDS),
        "places_order": False,
        "exchange_write_called": False,
        "order_lifecycle_called": False,
        "automatic_recovery_action": (
            "prepare_official_operation_layer_submit_evidence_from_passed_preflight"
        ),
    }


def _operation_layer_readiness(
    *,
    evidence_report: dict[str, Any] | None,
    evidence_report_path: str | None,
    command_plan: dict[str, Any],
) -> dict[str, Any] | None:
    if evidence_report is None:
        return None
    ids = _operation_layer_ids(evidence_report)
    required_ids = [
        str(item)
        for item in _list(command_plan.get("requires_evidence_ids"))
        if str(item).strip()
    ] or list(OPERATION_LAYER_REQUIRED_EVIDENCE_IDS)
    missing_ids = [name for name in required_ids if not _nonempty(ids.get(name))]
    blockers = _operation_layer_blockers(evidence_report, ids=ids)
    warnings = _operation_layer_warnings(evidence_report, ids=ids)
    ready = not missing_ids and not blockers
    return {
        "status": "ready" if ready else "blocked",
        "blocker_class": "none" if ready else _operation_layer_blocker_class(blockers, missing_ids),
        "source_report": evidence_report_path,
        "required_evidence_ids": required_ids,
        "available_evidence_ids": {
            key: value
            for key, value in ids.items()
            if key in required_ids and _nonempty(value)
        },
        "missing_evidence_ids": missing_ids,
        "blockers": blockers,
        "warnings": warnings,
        "ready_for_official_operation_layer_submit": ready,
        "places_order": False,
        "exchange_write_called": False,
        "order_lifecycle_called": False,
        "owner_state": (
            _owner_state_for_operation_layer_ready()
            if ready
            else _owner_state_for_operation_layer_blocked(
                blocker_class=_operation_layer_blocker_class(blockers, missing_ids),
                blockers=blockers,
                missing_ids=missing_ids,
            )
        ),
    }


def _operation_layer_ids(evidence_report: dict[str, Any]) -> dict[str, str]:
    ids: dict[str, str] = {}
    for source in (
        evidence_report.get("ids"),
        evidence_report.get("available_evidence_ids"),
        evidence_report.get("prepared_evidence_ids"),
    ):
        if isinstance(source, dict):
            for key, value in source.items():
                if _nonempty(value):
                    ids[str(key)] = str(value)
    for step in _list(evidence_report.get("steps")):
        id_summary = _dict(_dict(step).get("id_summary"))
        for key, value in id_summary.items():
            if _nonempty(value):
                ids[str(key)] = str(value)
    return ids


def _operation_layer_raw_blockers(evidence_report: dict[str, Any]) -> list[str]:
    blockers = list(evidence_report.get("blockers") or [])
    for step in _list(evidence_report.get("steps")):
        blockers.extend(_list(_dict(step).get("blockers")))
    return _dedupe_text(blockers)


def _legacy_local_registration_probe_blocker_satisfied(
    blocker: str,
    *,
    ids: dict[str, str],
) -> bool:
    text = blocker.lower()
    if not any(
        fragment in text
        for fragment in LEGACY_LOCAL_REGISTRATION_PROBE_BLOCKER_FRAGMENTS
    ):
        return False
    return _nonempty(ids.get("local_registration_adapter_result_id"))


def _operation_layer_blockers(
    evidence_report: dict[str, Any],
    *,
    ids: dict[str, str],
) -> list[str]:
    return [
        blocker
        for blocker in _operation_layer_raw_blockers(evidence_report)
        if not _legacy_local_registration_probe_blocker_satisfied(
            blocker,
            ids=ids,
        )
    ]


def _operation_layer_warnings(
    evidence_report: dict[str, Any],
    *,
    ids: dict[str, str],
) -> list[str]:
    warnings = list(evidence_report.get("warnings") or [])
    for step in _list(evidence_report.get("steps")):
        warnings.extend(_list(_dict(step).get("warnings")))
    if any(
        _legacy_local_registration_probe_blocker_satisfied(blocker, ids=ids)
        for blocker in _operation_layer_raw_blockers(evidence_report)
    ):
        warnings.append(
            "legacy_prepare_machine_evidence_probe_blocker_satisfied_by_"
            "local_registration_adapter_result"
        )
    return _dedupe_text(warnings)


def _operation_layer_blocker_class(
    blockers: list[str],
    missing_ids: list[str],
) -> str:
    combined = " ".join([*blockers, *missing_ids]).lower()
    if any(token in combined for token in ("withdraw", "transfer", "bypass")):
        return "hard_safety_stop"
    if any(token in combined for token in ("duplicate", "idempotency")):
        return "hard_safety_stop"
    if any(token in combined for token in ("active_position", "open_order_conflict")):
        return "active_position_resolution"
    if "deployment" in combined or "gateway_readiness" in combined:
        return "deployment_issue"
    if "owner_runtime_" in combined and "env_confirmation" in combined:
        return "deployment_issue"
    return "missing_fact"


def _owner_state_for_operation_layer_ready() -> dict[str, Any]:
    return {
        "status": "operation_layer_ready",
        "blocker_class": "none",
        "blocked_at": "none",
        "blocked_reason": "none",
        "next_recover_condition": "official_operation_layer_submit_action_time_recheck",
        "automatic_recovery_action": (
            "rerun_action_time_finalgate_then_use_official_operation_layer"
        ),
        "downgrade_mode": "none",
    }


def _owner_state_for_operation_layer_blocked(
    *,
    blocker_class: str,
    blockers: list[str],
    missing_ids: list[str],
) -> dict[str, Any]:
    reason = blockers[0] if blockers else (
        f"missing_evidence_id:{missing_ids[0]}"
        if missing_ids
        else "operation_layer_evidence_not_ready"
    )
    return {
        "status": "operation_layer_blocked",
        "blocker_class": blocker_class,
        "blocked_at": "OperationLayerEvidence",
        "blocked_reason": reason,
        "next_recover_condition": "required_submit_evidence_ready_and_fresh",
        "automatic_recovery_action": (
            "refresh_operation_layer_evidence_and_rerun_finalgate"
        ),
        "downgrade_mode": "continue_watcher_observation_no_submit",
    }


def _fresh_authorization_binding_command_plan(
    *,
    api_base: str,
    runtime_instance_id: str,
    handoff_json: str,
    requested_fresh_submit_authorization_id: str | None,
) -> dict[str, Any]:
    endpoint = (
        "/api/trading-console/strategy-runtimes/"
        f"{runtime_instance_id}/official-submit-handoff-fresh-authorizations/bind"
    )
    return {
        "kind": "official_fresh_submit_authorization_binding",
        "method": "POST",
        "api_base": api_base.rstrip("/"),
        "path": endpoint,
        "handoff_json": handoff_json,
        "requested_fresh_submit_authorization_id": (
            requested_fresh_submit_authorization_id
        ),
        "requires_operator_session": True,
        "allowed_prepare_evidence_creation": True,
        "calls_official_submit_endpoint": False,
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
    execute_preflight: bool = False,
    preflight_timeout_seconds: int = 120,
    operation_layer_evidence_report: dict[str, Any] | None = None,
    operation_layer_evidence_report_path: str | None = None,
) -> dict[str, Any]:
    action_time_resume = _dict(resume_pack.get("action_time_resume"))
    owner_state = _dict(resume_pack.get("owner_state"))
    top_level_status = str(resume_pack.get("status") or "")
    action_time_status = str(action_time_resume.get("status") or "")
    status = (
        top_level_status
        if top_level_status == FINALGATE_READY_STATUS
        else action_time_status or top_level_status
    )
    allowed_auto_actions = _allowed_auto_actions(
        resume_pack=resume_pack,
        action_time_resume=action_time_resume,
    )
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

    if status in FRESH_AUTHORIZATION_STATUSES:
        if not any(
            action in allowed_auto_actions
            for action in FRESH_AUTHORIZATION_ALLOWED_ACTIONS
        ):
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
                    "allowed_auto_actions_missing_fresh_authorization_binding"
                ],
                command_plan=None,
            )
        handoff_json = _fresh_authorization_handoff_json_path(
            resume_pack=resume_pack,
            action_time_resume=action_time_resume,
        )
        if not handoff_json:
            return _packet(
                label=label,
                source_path=source_path,
                resume_pack=resume_pack,
                action_time_resume=action_time_resume,
                owner_state=_owner_state_for_fresh_authorization(
                    status="blocked",
                    blocker_class="missing_fact",
                    dispatch_status="blocked_by_missing_handoff_json",
                    blockers=["missing_fact:handoff_json"],
                ),
                status="blocked",
                blocker_class="missing_fact",
                dispatch_action=None,
                dispatch_status="blocked_by_missing_handoff_json",
                blockers=base_blockers + ["missing_fact:handoff_json"],
                command_plan=None,
            )
        handoff_packet, handoff_error = _load_handoff_packet(handoff_json)
        if handoff_error:
            return _packet(
                label=label,
                source_path=source_path,
                resume_pack=resume_pack,
                action_time_resume=action_time_resume,
                owner_state=_owner_state_for_fresh_authorization(
                    status="blocked",
                    blocker_class="missing_fact",
                    dispatch_status="blocked_by_invalid_handoff_json",
                    blockers=[handoff_error],
                ),
                status="blocked",
                blocker_class="missing_fact",
                dispatch_action=None,
                dispatch_status="blocked_by_invalid_handoff_json",
                blockers=base_blockers + [handoff_error],
                command_plan=None,
            )
        runtime_instance_id = _first_text(
            handoff_packet.get("runtime_instance_id"),
            resume_pack.get("runtime_instance_id"),
            *list(resume_pack.get("selected_runtime_instance_ids") or []),
        )
        if not runtime_instance_id:
            return _packet(
                label=label,
                source_path=source_path,
                resume_pack=resume_pack,
                action_time_resume=action_time_resume,
                owner_state=_owner_state_for_fresh_authorization(
                    status="blocked",
                    blocker_class="missing_fact",
                    dispatch_status="blocked_by_missing_runtime_instance_id",
                    blockers=["missing_fact:runtime_instance_id"],
                ),
                status="blocked",
                blocker_class="missing_fact",
                dispatch_action=None,
                dispatch_status="blocked_by_missing_runtime_instance_id",
                blockers=base_blockers + ["missing_fact:runtime_instance_id"],
                command_plan=None,
            )
        requested_authorization_id = _first_text(
            action_time_resume.get("requested_fresh_submit_authorization_id"),
            resume_pack.get("requested_fresh_submit_authorization_id"),
        )
        packet = _packet(
            label=label,
            source_path=source_path,
            resume_pack=resume_pack,
            action_time_resume=action_time_resume,
            owner_state=_owner_state_for_fresh_authorization(
                status=status,
                blocker_class="none",
                dispatch_status="official_fresh_authorization_binding_dispatch_ready",
                blockers=[],
            ),
            status=status,
            blocker_class="none",
            dispatch_action=FRESH_AUTHORIZATION_BINDING_ACTION,
            dispatch_status="official_fresh_authorization_binding_dispatch_ready",
            blockers=[],
            command_plan=_fresh_authorization_binding_command_plan(
                api_base=api_base,
                runtime_instance_id=runtime_instance_id,
                handoff_json=handoff_json,
                requested_fresh_submit_authorization_id=requested_authorization_id,
            ),
        )
        if not execute_preflight:
            return packet
        return _execute_fresh_authorization_binding(
            packet=packet,
            handoff_packet=handoff_packet,
            timeout_seconds=preflight_timeout_seconds,
            operation_layer_evidence_report=operation_layer_evidence_report,
            operation_layer_evidence_report_path=operation_layer_evidence_report_path,
        )

    if status == FINALGATE_READY_STATUS:
        operation_layer_command_plan = _dict(
            resume_pack.get("operation_layer_command_plan")
        )
        if not operation_layer_command_plan:
            authorization_id = _first_text(
                action_time_resume.get("prepared_authorization_id"),
                resume_pack.get("prepared_authorization_id"),
                _dict(resume_pack.get("command_plan")).get("prepared_authorization_id"),
                _dict(resume_pack.get("command_plan")).get("authorization_id"),
            )
            if not authorization_id:
                return _packet(
                    label=label,
                    source_path=source_path,
                    resume_pack=resume_pack,
                    action_time_resume=action_time_resume,
                    owner_state=_owner_state_for_operation_layer_blocked(
                        blocker_class="missing_fact",
                        blockers=[],
                        missing_ids=["prepared_authorization_id"],
                    ),
                    status="operation_layer_blocked",
                    blocker_class="missing_fact",
                    dispatch_action=None,
                    dispatch_status="blocked_by_missing_operation_layer_plan",
                    blockers=base_blockers + [
                        "missing_fact:operation_layer_command_plan"
                    ],
                    command_plan=_dict(resume_pack.get("command_plan")) or None,
                    finalgate_preflight_result=_dict(
                        resume_pack.get("finalgate_preflight_result")
                    ) or None,
                    operation_layer_command_plan=None,
                )
            operation_layer_command_plan = _operation_layer_command_plan(
                authorization_id=authorization_id,
            )
        packet = _packet(
            label=label,
            source_path=source_path,
            resume_pack=resume_pack,
            action_time_resume=action_time_resume,
            owner_state=_owner_state_for_preflight(
                status=FINALGATE_READY_STATUS,
                blocker_class="none",
                dispatch_status="official_finalgate_preflight_passed",
                blockers=[],
            ),
            status=FINALGATE_READY_STATUS,
            blocker_class="none",
            dispatch_action=OPERATION_LAYER_ACTION,
            dispatch_status="official_finalgate_preflight_passed",
            blockers=[],
            command_plan=_dict(resume_pack.get("command_plan")) or None,
            finalgate_preflight_result=_dict(
                resume_pack.get("finalgate_preflight_result")
            ) or None,
            operation_layer_command_plan=operation_layer_command_plan,
        )
        return _packet_with_operation_layer_readiness(
            packet=packet,
            evidence_report=operation_layer_evidence_report,
            evidence_report_path=operation_layer_evidence_report_path,
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

        authorization_id = _first_text(
            action_time_resume.get("prepared_authorization_id")
            or resume_pack.get("prepared_authorization_id")
        )
        signal_input_json = _first_text(
            action_time_resume.get("signal_input_json")
            or resume_pack.get("signal_input_json")
        )
        shadow_candidate_id = _first_text(
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
            operation_layer_evidence_report=operation_layer_evidence_report,
            operation_layer_evidence_report_path=operation_layer_evidence_report_path,
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
    operation_layer_evidence_report: dict[str, Any] | None = None,
    operation_layer_evidence_report_path: str | None = None,
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

    operation_layer_command_plan = _operation_layer_command_plan(
        authorization_id=packet["command_plan"]["prepared_authorization_id"],
    )
    result_packet = _packet_from_preflight(
        packet=packet,
        status="finalgate_ready",
        blocker_class="none",
        dispatch_status="official_finalgate_preflight_passed",
        blockers=[],
        preflight_result=preflight_result,
        operation_layer_command_plan=operation_layer_command_plan,
    )
    return _packet_with_operation_layer_readiness(
        packet=result_packet,
        evidence_report=operation_layer_evidence_report,
        evidence_report_path=operation_layer_evidence_report_path,
    )


def _execute_fresh_authorization_binding(
    *,
    packet: dict[str, Any],
    handoff_packet: dict[str, Any],
    timeout_seconds: int,
    operation_layer_evidence_report: dict[str, Any] | None = None,
    operation_layer_evidence_report_path: str | None = None,
) -> dict[str, Any]:
    command_plan = _dict(packet.get("command_plan"))
    if command_plan.get("method") != "POST":
        return _packet_from_fresh_authorization_binding(
            packet=packet,
            status="blocked",
            blocker_class="hard_safety_stop",
            dispatch_status="blocked_by_invalid_fresh_authorization_binding_plan",
            blockers=["invalid_fresh_authorization_binding_plan"],
            binding_result=None,
        )

    cookie, cookie_error = _session_cookie()
    if not cookie:
        return _packet_from_fresh_authorization_binding(
            packet=packet,
            status="blocked",
            blocker_class="deployment_issue",
            dispatch_status="blocked_by_operator_session_unavailable",
            blockers=[cookie_error or "operator_session_unavailable"],
            binding_result={
                "called": False,
                "http_status": None,
                "body": None,
                "error": cookie_error or "operator_session_unavailable",
            },
        )

    url = str(command_plan["api_base"]).rstrip("/") + str(command_plan["path"])
    response = _request_json(
        method="POST",
        url=url,
        cookie=cookie,
        timeout_seconds=timeout_seconds,
        body={
            "handoff_packet": handoff_packet,
            "requested_fresh_submit_authorization_id": (
                command_plan.get("requested_fresh_submit_authorization_id")
            ),
            "allow_create_from_existing_intent": True,
            "allow_create_intent_from_latest_draft": True,
            "metadata": {
                "runtime_signal_watcher_resume_dispatcher": True,
                "automatic_recovery_action": FRESH_AUTHORIZATION_BINDING_ACTION,
            },
            "no_exchange_side_effects": True,
        },
    )
    binding_result = {
        "called": True,
        "method": "POST",
        "path": command_plan["path"],
        "http_status": response.get("http_status"),
        "body": response.get("body"),
        "error": bool(response.get("error")),
        "error_type": response.get("error_type"),
        "error_message": response.get("error_message"),
        "calls_official_submit_endpoint": False,
        "places_order": False,
        "calls_order_lifecycle": False,
        "exchange_write_called": False,
    }
    http_status = response.get("http_status")
    if http_status in {401, 403}:
        return _packet_from_fresh_authorization_binding(
            packet=packet,
            status="blocked",
            blocker_class="deployment_issue",
            dispatch_status="blocked_by_operator_session_http_error",
            blockers=[f"operator_session_http_status:{http_status}"],
            binding_result=binding_result,
        )
    if response.get("error"):
        return _packet_from_fresh_authorization_binding(
            packet=packet,
            status="blocked",
            blocker_class="deployment_issue",
            dispatch_status="blocked_by_fresh_authorization_binding_http_error",
            blockers=[
                f"fresh_authorization_binding_http_status:{http_status or 'unavailable'}"
            ],
            binding_result=binding_result,
        )

    body = _dict(response.get("body"))
    forbidden_effects = _fresh_authorization_binding_forbidden_effects(body)
    if forbidden_effects:
        return _packet_from_fresh_authorization_binding(
            packet=packet,
            status="blocked",
            blocker_class="hard_safety_stop",
            dispatch_status="blocked_by_fresh_authorization_binding_forbidden_effect",
            blockers=forbidden_effects,
            binding_result=binding_result,
        )
    if not _fresh_authorization_binding_ready(body):
        blockers = [
            str(item) for item in _list(body.get("blockers")) if str(item).strip()
        ]
        if body.get("status") not in {
            "bound_existing_authorization",
            "created_authorization",
            "created_intent_and_authorization",
        }:
            blockers.append(f"fresh_authorization_binding_status:{body.get('status')}")
        return _packet_from_fresh_authorization_binding(
            packet=packet,
            status="blocked",
            blocker_class="missing_fact",
            dispatch_status="blocked_by_fresh_authorization_binding",
            blockers=sorted(set(blockers)) or ["fresh_authorization_binding_not_ready"],
            binding_result=binding_result,
        )

    next_command_plan = _bound_fresh_authorization_preflight_plan(
        packet=packet,
        binding_body=body,
    )
    bound_packet = _packet_from_fresh_authorization_binding(
        packet=packet,
        status="fresh_authorization_bound",
        blocker_class="none",
        dispatch_status="official_fresh_authorization_binding_ready",
        blockers=[],
        binding_result=binding_result,
        next_command_plan=next_command_plan,
    )
    if next_command_plan is None:
        return _packet_from_fresh_authorization_binding(
            packet=packet,
            status="blocked",
            blocker_class="missing_fact",
            dispatch_status="blocked_by_missing_bound_fresh_authorization_id",
            blockers=["missing_fact:fresh_submit_authorization_id"],
            binding_result=binding_result,
        )
    return _execute_finalgate_preflight(
        packet=bound_packet,
        timeout_seconds=timeout_seconds,
        operation_layer_evidence_report=operation_layer_evidence_report,
        operation_layer_evidence_report_path=operation_layer_evidence_report_path,
    )


def _fresh_authorization_binding_forbidden_effects(body: dict[str, Any]) -> list[str]:
    checks = {
        "calls_official_submit_endpoint": False,
        "requests_real_gateway_action": False,
        "exchange_write_called": False,
        "exchange_called": False,
        "exchange_order_submitted": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "runtime_budget_mutated": False,
        "withdrawal_or_transfer_created": False,
    }
    effects: list[str] = []
    for name, expected in checks.items():
        if body.get(name) not in {expected, None, "", 0}:
            effects.append(f"fresh_authorization_binding_effect:{name}")
    return effects


def _fresh_authorization_binding_ready(body: dict[str, Any]) -> bool:
    return (
        body.get("status")
        in {
            "bound_existing_authorization",
            "created_authorization",
            "created_intent_and_authorization",
        }
        and bool(body.get("fresh_submit_authorization_id"))
        and not body.get("blockers")
        and body.get("ready_for_fresh_authorization_resolution") is True
    )


def _bound_fresh_authorization_preflight_plan(
    *,
    packet: dict[str, Any],
    binding_body: dict[str, Any],
) -> dict[str, Any] | None:
    fresh_authorization_id = _first_text(
        binding_body.get("fresh_submit_authorization_id")
    )
    if not fresh_authorization_id:
        return None
    command_plan = _dict(packet.get("command_plan"))
    action_time_resume = _dict(packet.get("action_time_resume"))
    authorization_snapshot = _dict(binding_body.get("authorization_snapshot"))
    return _preflight_command_plan(
        api_base=str(command_plan.get("api_base") or DEFAULT_API_BASE),
        authorization_id=fresh_authorization_id,
        signal_input_json=_first_text(
            action_time_resume.get("signal_input_json"),
            packet.get("signal_input_json"),
        ),
        shadow_candidate_id=_first_text(
            action_time_resume.get("shadow_candidate_id"),
            packet.get("shadow_candidate_id"),
            binding_body.get("order_candidate_id"),
            authorization_snapshot.get("order_candidate_id"),
        ),
    )


def _packet_from_fresh_authorization_binding(
    *,
    packet: dict[str, Any],
    status: str,
    blocker_class: str,
    dispatch_status: str,
    blockers: list[str],
    binding_result: dict[str, Any] | None,
    next_command_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = _dict((binding_result or {}).get("body"))
    prepare_evidence_mutated = bool(
        body.get("creates_execution_intent") or body.get("creates_submit_authorization")
    )
    owner_state = _owner_state_for_fresh_authorization(
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
            FINALGATE_ACTION if status == "fresh_authorization_bound" else None
        ),
        "owner_state": owner_state,
        "command_plan": (
            next_command_plan
            if status == "fresh_authorization_bound" and next_command_plan
            else packet.get("command_plan")
        ),
        "fresh_authorization_binding_command_plan": packet.get("command_plan"),
        "fresh_authorization_binding_result": binding_result,
        "fresh_submit_authorization_id": body.get("fresh_submit_authorization_id"),
        "blockers": blockers,
        "safety_invariants": {
            **_dict(packet.get("safety_invariants")),
            "dispatcher_only": False,
            "official_fresh_authorization_binding_called": binding_result is not None
            and bool(binding_result.get("called")),
            "allowed_prepare_evidence_created": status == "fresh_authorization_bound",
            "pg_prepare_evidence_mutated": prepare_evidence_mutated,
            "creates_execution_intent": bool(body.get("creates_execution_intent")),
            "creates_submit_authorization": bool(
                body.get("creates_submit_authorization")
            ),
            "mutates_pg": prepare_evidence_mutated,
            "calls_official_submit_endpoint": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "exchange_write_called": False,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
            "official_operation_layer_submit_called": False,
        },
    }


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
            "mutates_pg": bool(
                _dict(packet.get("safety_invariants")).get("mutates_pg")
            ),
            "pg_prepare_evidence_mutated": bool(
                _dict(packet.get("safety_invariants")).get(
                    "pg_prepare_evidence_mutated"
                )
            ),
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
            "official_operation_layer_submit_called": False,
        },
    }


def _packet_with_operation_layer_readiness(
    *,
    packet: dict[str, Any],
    evidence_report: dict[str, Any] | None,
    evidence_report_path: str | None,
) -> dict[str, Any]:
    command_plan = _dict(packet.get("operation_layer_command_plan"))
    readiness = _operation_layer_readiness(
        evidence_report=evidence_report,
        evidence_report_path=evidence_report_path,
        command_plan=command_plan,
    )
    if readiness is None:
        return packet

    ready = readiness.get("status") == "ready"
    owner_state = _dict(readiness.get("owner_state"))
    blocker_class = str(readiness.get("blocker_class") or "missing_fact")
    blockers = _dedupe_text(
        [
            *list(readiness.get("blockers") or []),
            *[
                f"missing_evidence_id:{item}"
                for item in list(readiness.get("missing_evidence_ids") or [])
            ],
        ]
    )
    return {
        **packet,
        "status": "operation_layer_ready" if ready else "operation_layer_blocked",
        "blocker_class": "none" if ready else blocker_class,
        "dispatch_status": (
            "official_operation_layer_evidence_ready"
            if ready
            else "blocked_by_operation_layer_evidence"
        ),
        "dispatch_action": OPERATION_LAYER_ACTION if ready else None,
        "owner_state": owner_state,
        "operation_layer_readiness": readiness,
        "blockers": [] if ready else blockers,
        "warnings": _dedupe_text(
            [
                *list(packet.get("warnings") or []),
                *list(readiness.get("warnings") or []),
            ]
        ),
        "safety_invariants": {
            **_dict(packet.get("safety_invariants")),
            "official_operation_layer_submit_called": False,
            "operation_layer_evidence_report_read": True,
            "places_order": False,
            "calls_order_lifecycle": False,
            "exchange_write_called": False,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
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


def _owner_state_for_fresh_authorization(
    *,
    status: str,
    blocker_class: str,
    dispatch_status: str,
    blockers: list[str],
) -> dict[str, Any]:
    if status == "fresh_authorization_bound":
        return {
            "status": "fresh_authorization_bound",
            "blocker_class": "none",
            "blocked_at": "none",
            "blocked_reason": "none",
            "next_recover_condition": (
                "readiness_handoff_rebuilt_with_fresh_submit_authorization_id"
            ),
            "automatic_recovery_action": (
                "rerun_readiness_bridge_or_dispatcher_for_action_time_finalgate"
            ),
            "downgrade_mode": "none",
        }
    if blocker_class == "none":
        return {
            "status": "ready_for_fresh_submit_authorization",
            "blocker_class": "none",
            "blocked_at": "fresh_submit_authorization",
            "blocked_reason": "fresh_submit_authorization_not_bound_yet",
            "next_recover_condition": (
                "fresh_submit_authorization_binding_api_returns_ready"
            ),
            "automatic_recovery_action": (
                FRESH_AUTHORIZATION_BINDING_ACTION
            ),
            "downgrade_mode": "armed_observation_no_submit",
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
            "next_recover_condition": "operator_session_available_for_local_binding_api",
            "automatic_recovery_action": "restore_operator_session_or_local_session_signing",
            "downgrade_mode": "continue_watcher_observation_no_submit",
        }
    return {
        "status": "blocked",
        "blocker_class": blocker_class,
        "blocked_at": "fresh_submit_authorization",
        "blocked_reason": blockers[0] if blockers else dispatch_status,
        "next_recover_condition": "fresh_authorization_binding_blocker_resolved",
        "automatic_recovery_action": (
            "retry_official_fresh_submit_authorization_binding_after_repair"
        ),
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
    parser.add_argument(
        "--operation-layer-evidence-json",
        default=str(DEFAULT_OPERATION_LAYER_EVIDENCE_JSON),
        help=(
            "Optional first-real-submit evidence flow report. If present and "
            "FinalGate is ready, the dispatcher translates it into Operation "
            "Layer readiness or blocker state."
        ),
    )
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--label", default="tokyo-runtime-signal-watcher")
    parser.add_argument(
        "--execute-preflight",
        action="store_true",
        help=(
            "Call the official action-time FinalGate preflight when ready, or "
            "the official fresh-authorization binding API when parked at that "
            "non-executing checkpoint."
        ),
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
    operation_layer_evidence_report, operation_layer_evidence_report_path = (
        _read_optional_json(args.operation_layer_evidence_json)
    )
    packet = build_dispatch_packet(
        resume_pack=_read_json(source_path),
        source_path=source_path,
        api_base=args.api_base,
        label=args.label,
        execute_preflight=args.execute_preflight,
        preflight_timeout_seconds=args.preflight_timeout_seconds,
        operation_layer_evidence_report=operation_layer_evidence_report,
        operation_layer_evidence_report_path=operation_layer_evidence_report_path,
    )
    _write_json(Path(args.output_json).expanduser(), packet)
    print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if packet["status"] in {
        WAITING_STATUS,
        READY_STATUS,
        *FRESH_AUTHORIZATION_STATUSES,
        "fresh_authorization_bound",
        "finalgate_ready",
        "operation_layer_ready",
        "operation_layer_blocked",
        "blocked",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
