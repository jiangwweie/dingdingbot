#!/usr/bin/env python3
"""Dispatch the Runtime Signal Watcher resume packet to the next safe step.

The default mode consumes post-signal-resume-pack.json and writes an
Owner/agent-readable dispatch packet without calling the API. With
``--execute-preflight`` it may call the official action-time FinalGate preflight
GET endpoint, or the official fresh-submit-authorization binding endpoint when
the resume pack is parked at that non-executing checkpoint. With
``--execute-operation-layer-submit`` it may call the official Operation Layer
submit endpoint after the same-run FinalGate and evidence checks pass. With
``--execute-post-submit-finalize`` it may then call the official post-submit
finalize endpoint to record reconciliation and budget settlement evidence.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Callable
import urllib.error
import urllib.parse
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
NON_EXECUTING_PREPARE_STATUS = "ready_for_non_executing_prepare"
FRESH_AUTHORIZATION_STATUSES = {
    "ready_for_fresh_submit_authorization",
    "waiting_for_fresh_authorization",
}
FINALGATE_ACTION = "run_official_action_time_final_gate_preflight"
CONTINUE_ACTION = "continue_watcher_observation"
NON_EXECUTING_PREPARE_ACTION = "prepare_fresh_candidate_authorization_evidence"
OPERATION_LAYER_ACTION = "prepare_official_operation_layer_submit"
OPERATION_LAYER_SUBMIT_ACTION = "call_official_operation_layer_submit"
OPERATION_LAYER_SUBMIT_MODE_REAL = "real_gateway_action"
OPERATION_LAYER_SUBMIT_MODE_DISABLED_SMOKE = "disabled_smoke"
OPERATION_LAYER_SUBMIT_MODES = {
    OPERATION_LAYER_SUBMIT_MODE_REAL,
    OPERATION_LAYER_SUBMIT_MODE_DISABLED_SMOKE,
}
POST_SUBMIT_FINALIZE_ACTION = "post_submit_finalize_reconciliation_budget_settlement"
FRESH_AUTHORIZATION_ACTION = "bind_or_resolve_fresh_submit_authorization"
FRESH_AUTHORIZATION_BINDING_ACTION = "run_official_fresh_submit_authorization_binding"
RUNTIME_LIVE_ENABLEMENT_ACTION = "apply_bounded_runtime_live_enablement"
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
POST_SUBMIT_FINALIZE_OPTIONAL_EVIDENCE_IDS = (
    "authorization_id",
    "runtime_instance_id",
    "reservation_id",
    "attempt_reservation_id",
    "attempt_reservation",
)
LEGACY_LOCAL_REGISTRATION_PROBE_BLOCKER_FRAGMENTS = (
    "runtimeexecutionorderlifecycleadapterresult_not_found",
    "runtime_execution_order_lifecycle_adapter_result_not_found",
    "preview_disabled_first_real_submit_action_http_404",
)
SHADOW_RUNTIME_BOUNDARY_BLOCKERS = (
    "runtime_execution_enabled_false_current_shadow_boundary",
    "runtime_shadow_mode_current_boundary",
)
LIVE_ENABLEMENT_HARD_STOP_TOKENS = (
    "withdraw",
    "transfer",
    "bypass",
    "duplicate",
    "idempotency",
    "active_position",
    "open_order",
    "symbol_scope",
    "side_scope",
    "notional_scope",
    "leverage_scope",
    "authorization_id_mismatch",
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


def _action_runtime_instance_ids(
    *,
    resume_pack: dict[str, Any],
    action_time_resume: dict[str, Any],
) -> list[str]:
    ids: list[str] = []
    for value in (
        action_time_resume.get("runtime_instance_id"),
        resume_pack.get("runtime_instance_id"),
        _dict(resume_pack.get("command_plan")).get("runtime_instance_id"),
        _dict(resume_pack.get("operation_layer_command_plan")).get(
            "runtime_instance_id"
        ),
    ):
        text = str(value or "").strip()
        if text and text not in ids:
            ids.append(text)

    selected_ids = [
        str(item or "").strip()
        for item in _list(resume_pack.get("selected_runtime_instance_ids"))
        if str(item or "").strip()
    ]
    if not ids and len(selected_ids) == 1:
        ids.append(selected_ids[0])
    return ids


def _action_strategy_group_ids(
    *,
    resume_pack: dict[str, Any],
    action_time_resume: dict[str, Any],
) -> list[str]:
    runtime_ids = set(
        _action_runtime_instance_ids(
            resume_pack=resume_pack,
            action_time_resume=action_time_resume,
        )
    )
    signal_input_json = _first_text(
        action_time_resume.get("signal_input_json"),
        resume_pack.get("signal_input_json"),
    )
    prepared_authorization_id = _first_text(
        action_time_resume.get("prepared_authorization_id"),
        resume_pack.get("prepared_authorization_id"),
        _dict(resume_pack.get("command_plan")).get("prepared_authorization_id"),
        _dict(resume_pack.get("command_plan")).get("authorization_id"),
    )
    shadow_candidate_id = _first_text(
        action_time_resume.get("shadow_candidate_id"),
        resume_pack.get("shadow_candidate_id"),
    )
    ids: list[str] = []

    def add(value: Any) -> None:
        text = str(value or "").strip()
        if text and text not in ids:
            ids.append(text)

    for source in (action_time_resume, resume_pack):
        add(source.get("strategy_group_id"))
        add(source.get("strategy_family_id"))

    for item in _list(resume_pack.get("runtime_signal_summaries")):
        if not isinstance(item, dict):
            continue
        matches_runtime = (
            bool(runtime_ids)
            and str(item.get("runtime_instance_id") or "").strip() in runtime_ids
        )
        matches_signal = (
            bool(signal_input_json)
            and str(item.get("signal_input_json") or "").strip() == signal_input_json
        )
        matches_authorization = (
            bool(prepared_authorization_id)
            and str(item.get("prepared_authorization_id") or "").strip()
            == prepared_authorization_id
        )
        matches_candidate = (
            bool(shadow_candidate_id)
            and str(item.get("shadow_candidate_id") or "").strip()
            == shadow_candidate_id
        )
        if matches_runtime or matches_signal or matches_authorization or matches_candidate:
            add(item.get("strategy_group_id"))
            add(item.get("strategy_family_id"))
    return ids


def _selected_scope_action_blockers(
    *,
    selected_strategy_group_id: str | None,
    resume_pack: dict[str, Any],
    action_time_resume: dict[str, Any],
) -> list[str]:
    selected = str(selected_strategy_group_id or "").strip()
    if not selected:
        return []
    action_groups = _action_strategy_group_ids(
        resume_pack=resume_pack,
        action_time_resume=action_time_resume,
    )
    return _selected_scope_group_blockers(
        selected_strategy_group_id=selected,
        action_groups=action_groups,
    )


def _selected_scope_group_blockers(
    *,
    selected_strategy_group_id: str | None,
    action_groups: list[str],
) -> list[str]:
    selected = str(selected_strategy_group_id or "").strip()
    if not selected:
        return []
    if not action_groups:
        return ["missing_fact:selected_strategy_group_id_for_action"]
    if selected not in action_groups:
        return [
            "selected_strategy_group_mismatch:"
            f"expected={selected}:actual={','.join(action_groups)}"
        ]
    return []


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


def _operation_layer_submit_url(
    *,
    command_plan: dict[str, Any],
    readiness: dict[str, Any],
    submit_mode: str,
) -> str:
    ids = _dict(readiness.get("available_evidence_ids"))
    params = {
        "owner_confirmed_for_first_real_submit_action": (
            "true" if submit_mode == OPERATION_LAYER_SUBMIT_MODE_REAL else "false"
        ),
    }
    for name in OPERATION_LAYER_REQUIRED_EVIDENCE_IDS:
        params[name] = str(ids.get(name) or "")
    query = urllib.parse.urlencode(params)
    return (
        str(command_plan.get("api_base") or DEFAULT_API_BASE).rstrip("/")
        + str(command_plan.get("official_endpoint_path") or "")
        + "?"
        + query
    )


def _operation_layer_submit_precondition_blockers(packet: dict[str, Any]) -> list[str]:
    readiness = _dict(packet.get("operation_layer_readiness"))
    command_plan = _dict(packet.get("operation_layer_command_plan"))
    finalgate_result = _dict(packet.get("finalgate_preflight_result"))
    blockers: list[str] = []
    if packet.get("status") != "operation_layer_ready":
        blockers.append(f"operation_layer_not_ready:{packet.get('status')}")
    if readiness.get("ready_for_official_operation_layer_submit") is not True:
        blockers.append("operation_layer_readiness_not_ready")
    if command_plan.get("official_endpoint_method") != "POST":
        blockers.append("operation_layer_submit_endpoint_method_not_post")
    if "runtime-execution-first-real-submit-actions/authorizations/" not in str(
        command_plan.get("official_endpoint_path") or ""
    ):
        blockers.append("operation_layer_submit_endpoint_not_official_action")
    if command_plan.get("owner_confirmed_for_first_real_submit_action") is not True:
        blockers.append("standing_authorized_submit_action_not_confirmed")
    if finalgate_result.get("called") is not True:
        blockers.append("action_time_finalgate_preflight_not_called")
    if finalgate_result.get("error") is True:
        blockers.append("action_time_finalgate_preflight_error")
    if finalgate_result and not _preflight_passed(finalgate_result.get("body")):
        blockers.append("action_time_finalgate_preflight_not_passed")
    missing = [
        name
        for name in OPERATION_LAYER_REQUIRED_EVIDENCE_IDS
        if not _nonempty(_dict(readiness.get("available_evidence_ids")).get(name))
    ]
    blockers.extend(f"missing_evidence_id:{name}" for name in missing)
    return _dedupe_text(blockers)


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
    authorization_blockers = _operation_layer_authorization_blockers(
        ids=ids,
        command_plan=command_plan,
    )
    blockers = _dedupe_text([*blockers, *authorization_blockers])
    warnings = _operation_layer_warnings(evidence_report, ids=ids)
    ready = not missing_ids and not blockers
    blocker_class = (
        "none" if ready else _operation_layer_blocker_class(blockers, missing_ids)
    )
    return {
        "status": "ready" if ready else "blocked",
        "blocker_class": blocker_class,
        "source_report": evidence_report_path,
        "required_evidence_ids": required_ids,
        "available_evidence_ids": {
            key: value
            for key, value in ids.items()
            if (
                key in required_ids
                or key in POST_SUBMIT_FINALIZE_OPTIONAL_EVIDENCE_IDS
            )
            and _nonempty(value)
        },
        "missing_evidence_ids": missing_ids,
        "blockers": blockers,
        "warnings": warnings,
        "ready_for_official_operation_layer_submit": ready,
        "blocker_review_policy": _operation_layer_blocker_review_policy(
            blocker_class=blocker_class,
            blockers=blockers,
            missing_ids=missing_ids,
        ),
        "places_order": False,
        "exchange_write_called": False,
        "order_lifecycle_called": False,
        "owner_state": (
            _owner_state_for_operation_layer_ready()
            if ready
            else _owner_state_for_operation_layer_blocked(
                blocker_class=blocker_class,
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


def _operation_layer_authorization_blockers(
    *,
    ids: dict[str, str],
    command_plan: dict[str, Any],
) -> list[str]:
    expected = str(command_plan.get("authorization_id") or "").strip()
    if not expected:
        return []
    actual = str(ids.get("authorization_id") or "").strip()
    if not actual:
        return ["operation_layer_authorization_id_missing"]
    if actual != expected:
        return [
            "operation_layer_authorization_id_mismatch:"
            f"expected={expected}:actual={actual}"
        ]
    return []


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
    if "authorization_id_mismatch" in combined:
        return "hard_safety_stop"
    if "runtime_instance_id_mismatch" in combined:
        return "hard_safety_stop"
    if "reservation_id_mismatch" in combined:
        return "hard_safety_stop"
    if any(token in combined for token in ("duplicate", "idempotency")):
        return "hard_safety_stop"
    if any(token in combined for token in ("active_position", "open_order_conflict")):
        return "active_position_resolution"
    if any(token in combined for token in ("symbol_scope", "side_scope")):
        return "hard_safety_stop"
    if any(token in combined for token in ("notional_scope", "leverage_scope")):
        return "hard_safety_stop"
    if "deployment" in combined or "gateway_readiness" in combined:
        return "deployment_issue"
    if "owner_runtime_" in combined and "env_confirmation" in combined:
        return "deployment_issue"
    return "missing_fact"


def _operation_layer_blocker_review_policy(
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
    if blocker_class == "none":
        return {
            "scope": "operation_layer_blocker_review_policy",
            "status": "ready",
            "project_progress_allowed": True,
            "continue_observation_allowed": True,
            "review_packet_recommended": False,
            "real_submit_allowed": True,
            "owner_console_state": "processing",
            "owner_sentence": "系统自动处理中",
            "reason": "none",
        }
    owner_console_state = (
        "needs_intervention"
        if blocker_class in {"active_position_resolution", "hard_safety_stop"}
        else "temporarily_unavailable"
    )
    owner_sentence_by_class = {
        "active_position_resolution": "有持仓或订单处理中，暂不能使用",
        "deployment_issue": "部署状态不可用，等待系统处理",
        "hard_safety_stop": "安全边界不满足，禁止提交",
        "missing_fact": "事实不可用，暂不能使用",
        "review_only_warning": "需要复核，但不影响观察",
        "waiting_for_market": "等待机会",
    }
    return {
        "scope": "operation_layer_blocker_review_policy",
        "status": "submit_blocked_review_packet_ready",
        "project_progress_allowed": True,
        "continue_observation_allowed": True,
        "review_packet_recommended": True,
        "real_submit_allowed": False,
        "owner_console_state": owner_console_state,
        "owner_sentence": owner_sentence_by_class.get(
            blocker_class,
            "暂不可用，等待系统处理",
        ),
        "reason": reason,
    }


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


def _non_executing_prepare_command_plan(
    *,
    api_base: str,
    resume_pack: dict[str, Any],
    action_time_resume: dict[str, Any],
) -> dict[str, Any]:
    return {
        "kind": "fresh_candidate_authorization_evidence_preparation",
        "method": "POST",
        "api_base": api_base.rstrip("/"),
        "path": (
            "/api/trading-console/strategy-runtimes/{runtime_instance_id}/"
            "official-submit-handoff-fresh-authorizations/bind"
        ),
        "runtime_instance_id": _non_executing_prepare_runtime_instance_id(
            resume_pack=resume_pack,
            action_time_resume=action_time_resume,
        ),
        "requires_runtime_instance_id": True,
        "requires_readiness_handoff_bridge": True,
        "readiness_handoff_bridge": _fresh_authorization_handoff_json_path(
            resume_pack=resume_pack,
            action_time_resume=action_time_resume,
        ),
        "signal_input_json": _non_executing_prepare_signal_input_json(
            resume_pack=resume_pack,
            action_time_resume=action_time_resume,
        ),
        "order_candidate_id": _first_text(
            action_time_resume.get("shadow_candidate_id"),
            resume_pack.get("shadow_candidate_id"),
            action_time_resume.get("order_candidate_id"),
            resume_pack.get("order_candidate_id"),
        ),
        "allowed_prepare_evidence_creation": True,
        "calls_official_submit_endpoint": False,
        "places_order": False,
        "calls_order_lifecycle": False,
        "exchange_write_called": False,
    }


def _non_executing_prepare_runtime_instance_id(
    *,
    resume_pack: dict[str, Any],
    action_time_resume: dict[str, Any],
) -> str | None:
    return _first_text(
        action_time_resume.get("runtime_instance_id"),
        resume_pack.get("runtime_instance_id"),
        *list(resume_pack.get("selected_runtime_instance_ids") or []),
    )


def _non_executing_prepare_signal_input_json(
    *,
    resume_pack: dict[str, Any],
    action_time_resume: dict[str, Any],
) -> str | None:
    return _first_text(
        action_time_resume.get("signal_input_json"),
        resume_pack.get("signal_input_json"),
    )


def _run_non_executing_prepare(
    command_plan: dict[str, Any],
) -> dict[str, Any]:
    from scripts import runtime_next_attempt_prepare_api_flow as prepare_flow  # noqa: WPS433

    args = argparse.Namespace(
        env_file=None,
        api_base=command_plan.get("api_base"),
        runtime_instance_id=command_plan.get("runtime_instance_id"),
        signal_input_json=command_plan.get("signal_input_json"),
        order_candidate_id=command_plan.get("order_candidate_id"),
        candidate_id=None,
        context_id=None,
        owner_operator_id="owner",
        owner_confirmation_reference=(
            "owner-standing-authorization-runtime-signal-watcher-"
            "non-executing-prepare"
        ),
        reason=(
            "runtime signal watcher standing authorization "
            "non-executing candidate authorization evidence prepare"
        ),
        next_attempt_symbol=None,
        next_attempt_side=None,
        next_attempt_family=None,
        next_attempt_strategy_family_id=None,
        next_attempt_carrier_id=None,
    )
    config = prepare_flow._build_flow_config(args)  # noqa: SLF001
    report = prepare_flow.FirstRealSubmitApiFlow(
        client=prepare_flow.UrlLibApiClient(api_base=config.api_base),
        config=config,
    ).run()
    return prepare_flow._summarize_prepare_report(report)  # noqa: SLF001


def _non_executing_prepare_forbidden_effects(
    prepare_packet: dict[str, Any],
) -> list[str]:
    safety = _dict(prepare_packet.get("safety_invariants"))
    checks = {
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
    }
    effects: list[str] = []
    for name, expected in checks.items():
        if safety.get(name) not in {expected, None, "", 0}:
            effects.append(f"non_executing_prepare_effect:{name}")
    return effects


def _non_executing_prepare_authorization_id(
    prepare_packet: dict[str, Any],
) -> str | None:
    return _first_text(
        _dict(prepare_packet.get("ids")).get("authorization_id"),
        _dict(prepare_packet.get("operator_command_plan")).get(
            "prepared_authorization_id"
        ),
    )


def _non_executing_prepare_candidate_id(
    prepare_packet: dict[str, Any],
) -> str | None:
    ids = _dict(prepare_packet.get("ids"))
    return _first_text(
        ids.get("order_candidate_id"),
        ids.get("shadow_candidate_id"),
        ids.get("runtime_execution_intent_draft_id"),
    )


def _non_executing_prepare_ready(
    prepare_packet: dict[str, Any],
) -> bool:
    return (
        prepare_packet.get("status") == "ready_for_final_gate_preflight"
        and bool(_non_executing_prepare_authorization_id(prepare_packet))
        and not _list(prepare_packet.get("blockers"))
    )


def _packet_from_non_executing_prepare(
    *,
    packet: dict[str, Any],
    status: str,
    blocker_class: str,
    dispatch_status: str,
    blockers: list[str],
    prepare_result: dict[str, Any] | None,
    next_command_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    created_records = _dict((prepare_result or {}).get("created_records"))
    prepare_safety = _dict((prepare_result or {}).get("safety_invariants"))
    prepare_evidence_mutated = any(
        bool(created_records.get(name))
        for name in (
            "shadow_candidate_created",
            "runtime_execution_intent_draft_created",
            "execution_intent_created",
            "submit_authorization_created",
            "protection_plan_created",
        )
    )
    return {
        **packet,
        "status": status,
        "blocker_class": blocker_class,
        "dispatch_status": dispatch_status,
        "dispatch_action": FINALGATE_ACTION if status == READY_STATUS else None,
        "owner_state": (
            _owner_state_for_preflight(
                status=READY_STATUS,
                blocker_class="none",
                dispatch_status="non_executing_prepare_ready_for_finalgate",
                blockers=[],
            )
            if status == READY_STATUS
            else {
                "status": "needs_intervention",
                "blocker_class": blocker_class,
                "blocked_at": "non_executing_prepare",
                "blocked_reason": blockers[0] if blockers else dispatch_status,
                "next_recover_condition": (
                    "fresh_candidate_authorization_evidence_ready"
                ),
                "automatic_recovery_action": NON_EXECUTING_PREPARE_ACTION,
                "downgrade_mode": "continue_watcher_observation_no_submit",
            }
        ),
        "command_plan": next_command_plan or packet.get("command_plan"),
        "non_executing_prepare_command_plan": packet.get("command_plan"),
        "non_executing_prepare_result": prepare_result,
        "blockers": blockers,
        "safety_invariants": {
            **_dict(packet.get("safety_invariants")),
            "dispatcher_only": False,
            "official_non_executing_prepare_called": prepare_result is not None,
            "allowed_prepare_evidence_created": status == READY_STATUS,
            "pg_prepare_evidence_mutated": prepare_evidence_mutated,
            "created_records": created_records,
            "prepare_safety_invariants": prepare_safety,
            "calls_official_submit_endpoint": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "exchange_write_called": False,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
            "official_operation_layer_submit_called": False,
        },
    }


def _execute_non_executing_prepare(
    *,
    packet: dict[str, Any],
    timeout_seconds: int,
    prepare_runner: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    operation_layer_evidence_report: dict[str, Any] | None = None,
    operation_layer_evidence_report_path: str | None = None,
    operation_layer_evidence_preparer: Callable[[str, dict[str, Any]], dict[str, Any]]
    | None = None,
    runtime_live_enabler: Callable[..., dict[str, Any]] | None = None,
    execute_operation_layer_submit: bool = False,
    operation_layer_submit_mode: str = OPERATION_LAYER_SUBMIT_MODE_REAL,
    execute_post_submit_finalize: bool = False,
) -> dict[str, Any]:
    command_plan = _dict(packet.get("command_plan"))
    runtime_instance_id = _first_text(command_plan.get("runtime_instance_id"))
    signal_input_json = _first_text(command_plan.get("signal_input_json"))
    missing: list[str] = []
    if not runtime_instance_id:
        missing.append("runtime_instance_id")
    if not signal_input_json and not command_plan.get("order_candidate_id"):
        missing.append("signal_input_json")
    if missing:
        return _packet_from_non_executing_prepare(
            packet=packet,
            status="blocked",
            blocker_class="missing_fact",
            dispatch_status="blocked_by_missing_non_executing_prepare_inputs",
            blockers=[f"missing_fact:{name}" for name in missing],
            prepare_result=None,
        )

    runner = prepare_runner or _run_non_executing_prepare
    prepare_result = runner(command_plan)
    forbidden_effects = _non_executing_prepare_forbidden_effects(prepare_result)
    if forbidden_effects:
        return _packet_from_non_executing_prepare(
            packet=packet,
            status="blocked",
            blocker_class="hard_safety_stop",
            dispatch_status="blocked_by_non_executing_prepare_forbidden_effect",
            blockers=forbidden_effects,
            prepare_result=prepare_result,
        )

    if not _non_executing_prepare_ready(prepare_result):
        blockers = _dedupe_text(prepare_result.get("blockers") or [])
        if prepare_result.get("status") != "ready_for_final_gate_preflight":
            blockers.append(
                f"non_executing_prepare_status:{prepare_result.get('status')}"
            )
        return _packet_from_non_executing_prepare(
            packet=packet,
            status="blocked",
            blocker_class="missing_fact",
            dispatch_status="blocked_by_non_executing_prepare",
            blockers=blockers or ["non_executing_prepare_not_ready"],
            prepare_result=prepare_result,
        )

    authorization_id = _non_executing_prepare_authorization_id(prepare_result)
    next_command_plan = _preflight_command_plan(
        api_base=str(command_plan.get("api_base") or DEFAULT_API_BASE),
        authorization_id=str(authorization_id),
        signal_input_json=signal_input_json,
        shadow_candidate_id=_non_executing_prepare_candidate_id(prepare_result),
    )
    ready_packet = _packet_from_non_executing_prepare(
        packet=packet,
        status=READY_STATUS,
        blocker_class="none",
        dispatch_status="non_executing_prepare_ready_for_finalgate",
        blockers=[],
        prepare_result=prepare_result,
        next_command_plan=next_command_plan,
    )
    return _execute_finalgate_preflight(
        packet=ready_packet,
        timeout_seconds=timeout_seconds,
        operation_layer_evidence_report=operation_layer_evidence_report,
        operation_layer_evidence_report_path=operation_layer_evidence_report_path,
        operation_layer_evidence_preparer=operation_layer_evidence_preparer,
        runtime_live_enabler=runtime_live_enabler,
        execute_operation_layer_submit=execute_operation_layer_submit,
        operation_layer_submit_mode=operation_layer_submit_mode,
        execute_post_submit_finalize=execute_post_submit_finalize,
    )


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
    operation_layer_evidence_preparer: Callable[[str, dict[str, Any]], dict[str, Any]]
    | None = None,
    non_executing_preparer: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    runtime_live_enabler: Callable[..., dict[str, Any]] | None = None,
    execute_operation_layer_submit: bool = False,
    operation_layer_submit_mode: str = OPERATION_LAYER_SUBMIT_MODE_REAL,
    execute_post_submit_finalize: bool = False,
    selected_strategy_group_id: str | None = None,
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
            selected_strategy_group_id=selected_strategy_group_id,
        )

    if status == NON_EXECUTING_PREPARE_STATUS:
        if NON_EXECUTING_PREPARE_ACTION not in allowed_auto_actions:
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
                    "allowed_auto_actions_missing_non_executing_prepare"
                ],
                command_plan=None,
                selected_strategy_group_id=selected_strategy_group_id,
            )
        selected_scope_blockers = _selected_scope_action_blockers(
            selected_strategy_group_id=selected_strategy_group_id,
            resume_pack=resume_pack,
            action_time_resume=action_time_resume,
        )
        if selected_scope_blockers:
            return _packet(
                label=label,
                source_path=source_path,
                resume_pack=resume_pack,
                action_time_resume=action_time_resume,
                owner_state={
                    "status": "needs_intervention",
                    "blocker_class": "hard_safety_stop",
                    "blocked_at": "selected_strategygroup_scope",
                    "blocked_reason": ",".join(selected_scope_blockers),
                    "next_safe_checkpoint": "review_selected_strategygroup_scope",
                    "downgrade_mode": "continue_watcher_observation_no_submit",
                },
                status="blocked",
                blocker_class="hard_safety_stop",
                dispatch_action=None,
                dispatch_status="blocked_by_selected_strategygroup_scope",
                blockers=base_blockers + selected_scope_blockers,
                command_plan=None,
                selected_strategy_group_id=selected_strategy_group_id,
            )
        packet = _packet(
            label=label,
            source_path=source_path,
            resume_pack=resume_pack,
            action_time_resume=action_time_resume,
            owner_state={
                "status": NON_EXECUTING_PREPARE_STATUS,
                "blocker_class": "none",
                "blocked_at": "candidate_authorization",
                "blocked_reason": (
                    "fresh_signal_waiting_for_candidate_authorization_evidence"
                ),
                "next_recover_condition": (
                    "fresh_candidate_runtime_grant_authorization_evidence_exists"
                ),
                "automatic_recovery_action": NON_EXECUTING_PREPARE_ACTION,
                "downgrade_mode": (
                    "no_real_submit_until_candidate_authorization_finalgate"
                ),
            },
            status=NON_EXECUTING_PREPARE_STATUS,
            blocker_class="none",
            dispatch_action=NON_EXECUTING_PREPARE_ACTION,
            dispatch_status="non_executing_prepare_dispatch_ready",
            blockers=[],
            command_plan=_non_executing_prepare_command_plan(
                api_base=api_base,
                resume_pack=resume_pack,
                action_time_resume=action_time_resume,
            ),
            selected_strategy_group_id=selected_strategy_group_id,
        )
        if not execute_preflight:
            return packet
        return _execute_non_executing_prepare(
            packet=packet,
            timeout_seconds=preflight_timeout_seconds,
            prepare_runner=non_executing_preparer,
            operation_layer_evidence_report=operation_layer_evidence_report,
            operation_layer_evidence_report_path=operation_layer_evidence_report_path,
            operation_layer_evidence_preparer=operation_layer_evidence_preparer,
            runtime_live_enabler=runtime_live_enabler,
            execute_operation_layer_submit=execute_operation_layer_submit,
            operation_layer_submit_mode=operation_layer_submit_mode,
            execute_post_submit_finalize=execute_post_submit_finalize,
        )

    selected_scope_blockers = (
        []
        if status in FRESH_AUTHORIZATION_STATUSES
        else _selected_scope_action_blockers(
            selected_strategy_group_id=selected_strategy_group_id,
            resume_pack=resume_pack,
            action_time_resume=action_time_resume,
        )
    )
    if selected_scope_blockers:
        return _packet(
            label=label,
            source_path=source_path,
            resume_pack=resume_pack,
            action_time_resume=action_time_resume,
            owner_state={
                "status": "needs_intervention",
                "blocker_class": "hard_safety_stop",
                "blocked_at": "selected_strategygroup_scope",
                "blocked_reason": ",".join(selected_scope_blockers),
                "next_safe_checkpoint": "review_selected_strategygroup_scope",
                "downgrade_mode": "continue_watcher_observation_no_submit",
            },
            status="blocked",
            blocker_class="hard_safety_stop",
            dispatch_action=None,
            dispatch_status="blocked_by_selected_strategygroup_scope",
            blockers=base_blockers + selected_scope_blockers,
            command_plan=None,
            selected_strategy_group_id=selected_strategy_group_id,
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
                selected_strategy_group_id=selected_strategy_group_id,
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
                selected_strategy_group_id=selected_strategy_group_id,
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
                selected_strategy_group_id=selected_strategy_group_id,
            )
        handoff_groups = _action_strategy_group_ids(
            resume_pack=resume_pack,
            action_time_resume=action_time_resume,
        )
        for value in (
            handoff_packet.get("strategy_group_id"),
            handoff_packet.get("strategy_family_id"),
        ):
            text = str(value or "").strip()
            if text and text not in handoff_groups:
                handoff_groups.append(text)
        selected_scope_blockers = _selected_scope_group_blockers(
            selected_strategy_group_id=selected_strategy_group_id,
            action_groups=handoff_groups,
        )
        if selected_scope_blockers:
            return _packet(
                label=label,
                source_path=source_path,
                resume_pack=resume_pack,
                action_time_resume=action_time_resume,
                owner_state={
                    "status": "needs_intervention",
                    "blocker_class": "hard_safety_stop",
                    "blocked_at": "selected_strategygroup_scope",
                    "blocked_reason": ",".join(selected_scope_blockers),
                    "next_safe_checkpoint": "review_selected_strategygroup_scope",
                    "downgrade_mode": "continue_watcher_observation_no_submit",
                },
                status="blocked",
                blocker_class="hard_safety_stop",
                dispatch_action=None,
                dispatch_status="blocked_by_selected_strategygroup_scope",
                blockers=base_blockers + selected_scope_blockers,
                command_plan=None,
                selected_strategy_group_id=selected_strategy_group_id,
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
                selected_strategy_group_id=selected_strategy_group_id,
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
            selected_strategy_group_id=selected_strategy_group_id,
        )
        if not execute_preflight:
            return packet
        return _execute_fresh_authorization_binding(
            packet=packet,
            handoff_packet=handoff_packet,
            timeout_seconds=preflight_timeout_seconds,
            operation_layer_evidence_report=operation_layer_evidence_report,
            operation_layer_evidence_report_path=operation_layer_evidence_report_path,
            operation_layer_evidence_preparer=operation_layer_evidence_preparer,
            runtime_live_enabler=runtime_live_enabler,
            execute_operation_layer_submit=execute_operation_layer_submit,
            operation_layer_submit_mode=operation_layer_submit_mode,
            execute_post_submit_finalize=execute_post_submit_finalize,
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
                    selected_strategy_group_id=selected_strategy_group_id,
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
            selected_strategy_group_id=selected_strategy_group_id,
        )
        packet = _packet_with_operation_layer_readiness(
            packet=packet,
            evidence_report=operation_layer_evidence_report,
            evidence_report_path=operation_layer_evidence_report_path,
        )
        return _maybe_execute_operation_layer_submit(
            packet=packet,
            execute_operation_layer_submit=execute_operation_layer_submit,
            operation_layer_submit_mode=operation_layer_submit_mode,
            execute_post_submit_finalize=execute_post_submit_finalize,
            timeout_seconds=preflight_timeout_seconds,
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
                selected_strategy_group_id=selected_strategy_group_id,
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
                selected_strategy_group_id=selected_strategy_group_id,
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
            selected_strategy_group_id=selected_strategy_group_id,
        )
        if not execute_preflight:
            return packet
        return _execute_finalgate_preflight(
            packet=packet,
            timeout_seconds=preflight_timeout_seconds,
            operation_layer_evidence_report=operation_layer_evidence_report,
            operation_layer_evidence_report_path=operation_layer_evidence_report_path,
            operation_layer_evidence_preparer=operation_layer_evidence_preparer,
            runtime_live_enabler=runtime_live_enabler,
            execute_operation_layer_submit=execute_operation_layer_submit,
            operation_layer_submit_mode=operation_layer_submit_mode,
            execute_post_submit_finalize=execute_post_submit_finalize,
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
        selected_strategy_group_id=selected_strategy_group_id,
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
    selected_strategy_group_id: str | None = None,
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
        "selected_strategy_group_id": (
            str(selected_strategy_group_id).strip()
            if str(selected_strategy_group_id or "").strip()
            else None
        ),
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


def _operation_layer_evidence_needs_preparation(
    *,
    evidence_report: dict[str, Any] | None,
    command_plan: dict[str, Any],
) -> bool:
    readiness = _operation_layer_readiness(
        evidence_report=evidence_report,
        evidence_report_path=None,
        command_plan=command_plan,
    )
    if readiness is None:
        return True
    if readiness.get("ready_for_official_operation_layer_submit") is True:
        return False
    missing_ids = list(readiness.get("missing_evidence_ids") or [])
    blockers = list(readiness.get("blockers") or [])
    return bool(missing_ids or blockers)


def _maybe_prepare_operation_layer_evidence(
    *,
    authorization_id: str,
    command_plan: dict[str, Any],
    current_report: dict[str, Any] | None,
    current_report_path: str | None,
    execute_operation_layer_submit: bool,
    evidence_preparer: Callable[[str, dict[str, Any]], dict[str, Any]] | None,
) -> dict[str, Any] | None:
    if not execute_operation_layer_submit:
        return current_report
    if not _operation_layer_evidence_needs_preparation(
        evidence_report=current_report,
        command_plan=command_plan,
    ):
        return current_report
    preparer = evidence_preparer or _run_operation_layer_evidence_prep
    report = preparer(authorization_id, command_plan)
    if current_report_path:
        _write_json(Path(current_report_path).expanduser(), report)
    return report


def _shadow_runtime_boundary_blockers(blockers: list[str]) -> list[str]:
    result: list[str] = []
    for blocker in blockers:
        text = str(blocker)
        if any(token in text for token in SHADOW_RUNTIME_BOUNDARY_BLOCKERS):
            result.append(text)
    return _dedupe_text(result)


def _runtime_live_enablement_hard_stops(blockers: list[str]) -> list[str]:
    hard_stops: list[str] = []
    for blocker in blockers:
        text = str(blocker).lower()
        if any(token in text for token in LIVE_ENABLEMENT_HARD_STOP_TOKENS):
            hard_stops.append(str(blocker))
    return _dedupe_text(hard_stops)


def _operation_layer_needs_runtime_live_enablement(
    *,
    evidence_report: dict[str, Any] | None,
    command_plan: dict[str, Any],
) -> bool:
    if evidence_report is None:
        return False
    readiness = _operation_layer_readiness(
        evidence_report=evidence_report,
        evidence_report_path=None,
        command_plan=command_plan,
    )
    if readiness is None or readiness.get("ready_for_official_operation_layer_submit"):
        return False
    blockers = _dedupe_text(readiness.get("blockers") or [])
    if not _shadow_runtime_boundary_blockers(blockers):
        return False
    return not _runtime_live_enablement_hard_stops(blockers)


def _runtime_instance_id_for_live_enablement(
    *,
    packet: dict[str, Any],
    evidence_report: dict[str, Any] | None,
) -> str | None:
    ids = _operation_layer_ids(evidence_report or {})
    selected_runtime_ids = [
        str(item)
        for item in _list(packet.get("selected_runtime_instance_ids"))
        if str(item or "").strip()
    ]
    return _first_text(
        ids.get("runtime_instance_id"),
        selected_runtime_ids[0] if len(selected_runtime_ids) == 1 else None,
        _dict(packet.get("action_time_resume")).get("runtime_instance_id"),
    )


def _standing_live_enablement_authorization_id(
    *,
    runtime_instance_id: str,
    authorization_id: str,
) -> str:
    raw = f"standing-live-enable-{runtime_instance_id}-{authorization_id}"
    return raw[:180]


def _runtime_live_enablement_query(
    *,
    authorization_id: str,
    evidence_report: dict[str, Any] | None,
) -> dict[str, Any]:
    ids = _operation_layer_ids(evidence_report or {})
    return {
        "strategy_family_confirmed": True,
        "implementation_source_confirmed": True,
        "required_facts_confirmed": True,
        "entry_policy_confirmed": True,
        "exit_policy_confirmed": True,
        "protection_policy_confirmed": True,
        "eligible_for_runtime_execution_confirmed": True,
        "right_tail_review_metrics_confirmed": True,
        "runtime_profile_confirmed": True,
        "owner_confirmation_mode_confirmed": True,
        "symbol_side_boundary_confirmed": True,
        "max_loss_budget_confirmed": True,
        "max_notional_boundary_confirmed": True,
        "max_active_positions_boundary_confirmed": True,
        "max_leverage_boundary_confirmed": True,
        "margin_usage_boundary_confirmed": True,
        "liquidation_buffer_boundary_confirmed": True,
        "protection_readiness_source_confirmed": True,
        "stale_fact_behavior_confirmed": True,
        "attempt_consumption_rule_confirmed": True,
        "budget_reservation_rule_confirmed": True,
        "trusted_active_position_source_confirmed": True,
        "trusted_account_fact_source_confirmed": True,
        "short_side_conservative_profile_confirmed": True,
        "budget_release_or_consume_rule_confirmed": True,
        "protection_creation_failure_policy_confirmed": True,
        "duplicate_submit_policy_confirmed": True,
        "deployment_readiness_confirmed": True,
        "explicit_owner_real_submit_authorization": True,
        "current_head_deployed": True,
        "owner_live_runtime_enablement_authorized": True,
        "owner_real_submit_authorization_present": True,
        "submit_technical_rehearsal_passed": True,
        "submit_adapter_implemented": True,
        "staged_submit_chain_available": True,
        "post_submit_budget_settlement_persistence_evidence_id": ids.get(
            "post_submit_budget_settlement_persistence_evidence_id"
        ),
        "attempt_outcome_policy_id": ids.get("attempt_outcome_policy_id"),
        "protection_creation_failure_policy_id": ids.get(
            "protection_creation_failure_policy_id"
        ),
        "submit_idempotency_policy_id": ids.get("submit_idempotency_policy_id"),
        "trusted_submit_fact_snapshot_id": ids.get("trusted_submit_fact_snapshot_id"),
        "local_registration_enablement_decision_id": ids.get(
            "local_registration_enablement_decision_id"
        ),
        "exchange_submit_enablement_decision_id": ids.get(
            "exchange_submit_enablement_decision_id"
        ),
        "exchange_submit_execution_result_id": ids.get(
            "exchange_submit_execution_result_id"
        ),
        "runtime_submit_rehearsal_id": ids.get("runtime_submit_rehearsal_id"),
        "deployment_readiness_evidence_id": ids.get("deployment_readiness_evidence_id"),
        "owner_real_submit_authorization_id": ids.get(
            "owner_real_submit_authorization_id"
        )
        or authorization_id,
        "forbidden_execution_flags": [],
    }


def _clean_query_params(query: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in query.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, list):
            items = [item for item in value if str(item or "").strip()]
            if not items:
                continue
            cleaned[key] = items
            continue
        cleaned[key] = value
    return cleaned


def _runtime_live_enablement_forbidden_effects(body: dict[str, Any]) -> list[str]:
    checks = {
        "execution_intent_created": False,
        "order_created": False,
        "exchange_called": False,
        "owner_bounded_execution_called": False,
        "order_lifecycle_called": False,
        "withdrawal_instruction_created": False,
        "transfer_instruction_created": False,
    }
    effects: list[str] = []
    for name, expected in checks.items():
        if body.get(name) not in {expected, None, "", 0}:
            effects.append(f"runtime_live_enablement_effect:{name}")
    return effects


def _run_runtime_live_enablement(
    *,
    runtime_instance_id: str,
    authorization_id: str,
    command_plan: dict[str, Any],
    evidence_report: dict[str, Any] | None,
    timeout_seconds: int,
) -> dict[str, Any]:
    cookie, cookie_error = _session_cookie()
    if not cookie:
        return {
            "called": False,
            "status": "blocked",
            "blockers": [cookie_error or "operator_session_unavailable"],
            "mutation_applied": False,
            "runtime_state_mutated": False,
            "order_created": False,
            "exchange_called": False,
            "order_lifecycle_called": False,
        }
    api_base = str(command_plan.get("api_base") or DEFAULT_API_BASE).rstrip("/")
    query = _runtime_live_enablement_query(
        authorization_id=authorization_id,
        evidence_report=evidence_report,
    )
    preview_path = (
        "/api/trading-console/strategy-runtimes/"
        f"{urllib.parse.quote(runtime_instance_id, safe='')}/live-enablement-preview"
    )
    preview_url = (
        api_base
        + preview_path
        + "?"
        + urllib.parse.urlencode(_clean_query_params(query), doseq=True)
    )
    preview_response = _request_json(
        method="GET",
        url=preview_url,
        cookie=cookie,
        timeout_seconds=timeout_seconds,
    )
    preview_body = _dict(preview_response.get("body"))
    result: dict[str, Any] = {
        "called": True,
        "preview": {
            "called": True,
            "method": "GET",
            "path": preview_path,
            "http_status": preview_response.get("http_status"),
            "body": preview_response.get("body"),
            "error": bool(preview_response.get("error")),
        },
        "mutation": None,
        "status": "blocked",
        "blockers": [],
        "mutation_applied": False,
        "runtime_state_mutated": False,
        "order_created": False,
        "exchange_called": False,
        "order_lifecycle_called": False,
        "withdrawal_or_transfer_created": False,
    }
    if preview_response.get("error"):
        result["blockers"] = [
            f"runtime_live_enablement_preview_http_status:{preview_response.get('http_status') or 'unavailable'}"
        ]
        return result
    if preview_body.get("status") != "ready_for_live_runtime_enablement_mutation_design":
        result["blockers"] = [
            f"runtime_live_enablement_preview_{item}"
            for item in _list(preview_body.get("blockers"))
        ] or ["runtime_live_enablement_preview_not_ready"]
        return result
    forbidden_effects = _runtime_live_enablement_forbidden_effects(preview_body)
    if forbidden_effects:
        result["blockers"] = forbidden_effects
        return result

    owner_real_submit_authorization_id = str(
        query.get("owner_real_submit_authorization_id") or authorization_id
    )
    owner_live_runtime_enablement_authorization_id = (
        _standing_live_enablement_authorization_id(
            runtime_instance_id=runtime_instance_id,
            authorization_id=authorization_id,
        )
    )
    mutation_path = (
        "/api/trading-console/strategy-runtimes/"
        f"{urllib.parse.quote(runtime_instance_id, safe='')}/live-enablement-mutations"
    )
    mutation_response = _request_json(
        method="POST",
        url=api_base + mutation_path,
        cookie=cookie,
        timeout_seconds=timeout_seconds,
        body={
            "preview": preview_body,
            "owner_live_runtime_enablement_authorization_id": (
                owner_live_runtime_enablement_authorization_id
            ),
            "owner_real_submit_authorization_id": owner_real_submit_authorization_id,
            "actor": "runtime_signal_watcher_resume_dispatcher",
        },
    )
    mutation_body = _dict(mutation_response.get("body"))
    result["mutation"] = {
        "called": True,
        "method": "POST",
        "path": mutation_path,
        "http_status": mutation_response.get("http_status"),
        "body": mutation_response.get("body"),
        "error": bool(mutation_response.get("error")),
    }
    if mutation_response.get("error"):
        result["blockers"] = [
            f"runtime_live_enablement_mutation_http_status:{mutation_response.get('http_status') or 'unavailable'}"
        ]
        return result
    forbidden_effects = _runtime_live_enablement_forbidden_effects(mutation_body)
    if forbidden_effects:
        result["blockers"] = forbidden_effects
        return result
    mutation_applied = mutation_body.get("status") == "applied"
    result.update(
        {
            "status": (
                "live_runtime_enablement_mutation_applied"
                if mutation_applied
                else "blocked"
            ),
            "blockers": _dedupe_text(mutation_body.get("blockers") or [])
            if not mutation_applied
            else [],
            "mutation_applied": mutation_applied,
            "runtime_state_mutated": bool(mutation_body.get("runtime_state_mutated")),
            "order_created": bool(mutation_body.get("order_created")),
            "exchange_called": bool(mutation_body.get("exchange_called")),
            "order_lifecycle_called": bool(mutation_body.get("order_lifecycle_called")),
            "withdrawal_or_transfer_created": bool(
                mutation_body.get("withdrawal_instruction_created")
                or mutation_body.get("transfer_instruction_created")
            ),
        }
    )
    return result


def _maybe_apply_runtime_live_enablement(
    *,
    packet: dict[str, Any],
    command_plan: dict[str, Any],
    evidence_report: dict[str, Any] | None,
    execute_operation_layer_submit: bool,
    timeout_seconds: int,
    live_enabler: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    if not execute_operation_layer_submit:
        return None
    if not _operation_layer_needs_runtime_live_enablement(
        evidence_report=evidence_report,
        command_plan=command_plan,
    ):
        return None
    authorization_id = str(command_plan.get("authorization_id") or "").strip()
    runtime_instance_id = _runtime_instance_id_for_live_enablement(
        packet=packet,
        evidence_report=evidence_report,
    )
    if not authorization_id or not runtime_instance_id:
        return {
            "called": False,
            "status": "blocked",
            "blockers": [
                "runtime_live_enablement_authorization_id_missing"
                if not authorization_id
                else "runtime_live_enablement_runtime_instance_id_missing"
            ],
            "mutation_applied": False,
            "runtime_state_mutated": False,
            "order_created": False,
            "exchange_called": False,
            "order_lifecycle_called": False,
            "withdrawal_or_transfer_created": False,
        }
    runner = live_enabler or _run_runtime_live_enablement
    return runner(
        runtime_instance_id=runtime_instance_id,
        authorization_id=authorization_id,
        command_plan=command_plan,
        evidence_report=evidence_report,
        timeout_seconds=timeout_seconds,
    )


def _run_operation_layer_evidence_prep(
    authorization_id: str,
    command_plan: dict[str, Any],
) -> dict[str, Any]:
    from scripts.runtime_first_real_submit_api_flow import (  # noqa: WPS433
        FirstRealSubmitApiFlow,
        FlowConfig,
        UrlLibApiClient,
    )

    api_base = str(command_plan.get("api_base") or DEFAULT_API_BASE)
    config = FlowConfig(
        api_base=api_base,
        mode="arm",
        authorization_id=authorization_id,
        record_attempt_consumption=True,
        standing_authorized_scoped_evidence_preparation=True,
        preview_disabled_first_real_submit_action=False,
    )
    return FirstRealSubmitApiFlow(
        client=UrlLibApiClient(api_base=config.api_base),
        config=config,
    ).run()


def _execute_finalgate_preflight(
    *,
    packet: dict[str, Any],
    timeout_seconds: int,
    operation_layer_evidence_report: dict[str, Any] | None = None,
    operation_layer_evidence_report_path: str | None = None,
    operation_layer_evidence_preparer: Callable[[str, dict[str, Any]], dict[str, Any]]
    | None = None,
    runtime_live_enabler: Callable[..., dict[str, Any]] | None = None,
    execute_operation_layer_submit: bool = False,
    operation_layer_submit_mode: str = OPERATION_LAYER_SUBMIT_MODE_REAL,
    execute_post_submit_finalize: bool = False,
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
    operation_layer_evidence_report = _maybe_prepare_operation_layer_evidence(
        authorization_id=packet["command_plan"]["prepared_authorization_id"],
        command_plan=operation_layer_command_plan,
        current_report=operation_layer_evidence_report,
        current_report_path=operation_layer_evidence_report_path,
        execute_operation_layer_submit=execute_operation_layer_submit,
        evidence_preparer=operation_layer_evidence_preparer,
    )
    runtime_live_enablement_result = _maybe_apply_runtime_live_enablement(
        packet=packet,
        command_plan=operation_layer_command_plan,
        evidence_report=operation_layer_evidence_report,
        execute_operation_layer_submit=execute_operation_layer_submit,
        timeout_seconds=timeout_seconds,
        live_enabler=runtime_live_enabler,
    )
    if _dict(runtime_live_enablement_result).get("mutation_applied") is True:
        operation_layer_evidence_report = _maybe_prepare_operation_layer_evidence(
            authorization_id=packet["command_plan"]["prepared_authorization_id"],
            command_plan=operation_layer_command_plan,
            current_report=operation_layer_evidence_report,
            current_report_path=operation_layer_evidence_report_path,
            execute_operation_layer_submit=execute_operation_layer_submit,
            evidence_preparer=operation_layer_evidence_preparer,
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
    if runtime_live_enablement_result is not None:
        result_packet = _packet_with_runtime_live_enablement_result(
            packet=result_packet,
            runtime_live_enablement_result=runtime_live_enablement_result,
        )
    result_packet = _packet_with_operation_layer_readiness(
        packet=result_packet,
        evidence_report=operation_layer_evidence_report,
        evidence_report_path=operation_layer_evidence_report_path,
    )
    return _maybe_execute_operation_layer_submit(
        packet=result_packet,
        execute_operation_layer_submit=execute_operation_layer_submit,
        operation_layer_submit_mode=operation_layer_submit_mode,
        execute_post_submit_finalize=execute_post_submit_finalize,
        timeout_seconds=timeout_seconds,
    )


def _execute_fresh_authorization_binding(
    *,
    packet: dict[str, Any],
    handoff_packet: dict[str, Any],
    timeout_seconds: int,
    operation_layer_evidence_report: dict[str, Any] | None = None,
    operation_layer_evidence_report_path: str | None = None,
    operation_layer_evidence_preparer: Callable[[str, dict[str, Any]], dict[str, Any]]
    | None = None,
    runtime_live_enabler: Callable[..., dict[str, Any]] | None = None,
    execute_operation_layer_submit: bool = False,
    operation_layer_submit_mode: str = OPERATION_LAYER_SUBMIT_MODE_REAL,
    execute_post_submit_finalize: bool = False,
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
        operation_layer_evidence_preparer=operation_layer_evidence_preparer,
        runtime_live_enabler=runtime_live_enabler,
        execute_operation_layer_submit=execute_operation_layer_submit,
        operation_layer_submit_mode=operation_layer_submit_mode,
        execute_post_submit_finalize=execute_post_submit_finalize,
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


def _packet_with_runtime_live_enablement_result(
    *,
    packet: dict[str, Any],
    runtime_live_enablement_result: dict[str, Any],
) -> dict[str, Any]:
    result = _dict(runtime_live_enablement_result)
    blockers = _dedupe_text(
        [
            *list(packet.get("blockers") or []),
            *[
                f"runtime_live_enablement:{item}"
                for item in list(result.get("blockers") or [])
            ],
        ]
    )
    mutation_applied = result.get("mutation_applied") is True
    runtime_state_mutated = result.get("runtime_state_mutated") is True
    return {
        **packet,
        "runtime_live_enablement_result": result,
        "dispatch_status": (
            "runtime_live_enablement_applied_after_finalgate"
            if mutation_applied
            else packet.get("dispatch_status")
        ),
        "blockers": blockers,
        "safety_invariants": {
            **_dict(packet.get("safety_invariants")),
            "dispatcher_only": False,
            "runtime_live_enablement_called": bool(result.get("called")),
            "runtime_live_enablement_mutation_applied": mutation_applied,
            "runtime_state_mutated": runtime_state_mutated,
            "mutates_pg": bool(
                runtime_state_mutated
                or _dict(packet.get("safety_invariants")).get("mutates_pg")
            ),
            "places_order": False,
            "calls_order_lifecycle": False,
            "exchange_write_called": False,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": bool(
                result.get("withdrawal_or_transfer_created")
            ),
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
    evidence_safety = _dict((evidence_report or {}).get("safety"))
    evidence_attempt_counter_mutated = (
        evidence_safety.get("attempt_counter_mutated") is True
    )
    evidence_runtime_budget_mutated = (
        evidence_safety.get("runtime_budget_mutated") is True
    )
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
        "operation_layer_blocker_review": _dict(
            readiness.get("blocker_review_policy")
        ),
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
            "operation_layer_evidence_attempt_counter_mutated": (
                evidence_attempt_counter_mutated
            ),
            "operation_layer_evidence_runtime_budget_mutated": (
                evidence_runtime_budget_mutated
            ),
            "places_order": False,
            "calls_order_lifecycle": False,
            "exchange_write_called": False,
            "attempt_counter_mutated": evidence_attempt_counter_mutated,
            "runtime_budget_mutated": evidence_runtime_budget_mutated,
            "withdrawal_or_transfer_created": False,
        },
    }


def _maybe_execute_operation_layer_submit(
    *,
    packet: dict[str, Any],
    execute_operation_layer_submit: bool,
    operation_layer_submit_mode: str,
    execute_post_submit_finalize: bool,
    timeout_seconds: int,
) -> dict[str, Any]:
    if not execute_operation_layer_submit:
        return packet
    if operation_layer_submit_mode not in OPERATION_LAYER_SUBMIT_MODES:
        return _packet_from_operation_layer_submit(
            packet=packet,
            status="operation_layer_submit_blocked",
            blocker_class="hard_safety_stop",
            dispatch_status="blocked_by_invalid_operation_layer_submit_mode",
            blockers=[
                f"invalid_operation_layer_submit_mode:{operation_layer_submit_mode}"
            ],
            submit_result={
                "called": False,
                "http_status": None,
                "body": None,
                "error": "invalid_operation_layer_submit_mode",
            },
        )
    blockers = _operation_layer_submit_precondition_blockers(packet)
    if blockers:
        return _packet_from_operation_layer_submit(
            packet=packet,
            status="operation_layer_submit_blocked",
            blocker_class=_operation_layer_blocker_class(blockers, []),
            dispatch_status="blocked_before_official_operation_layer_submit",
            blockers=blockers,
            submit_result={
                "called": False,
                "http_status": None,
                "body": None,
                "error": "operation_layer_submit_precondition_failed",
            },
        )
    return _execute_operation_layer_submit(
        packet=packet,
        timeout_seconds=timeout_seconds,
        operation_layer_submit_mode=operation_layer_submit_mode,
        execute_post_submit_finalize=execute_post_submit_finalize,
    )


def _execute_operation_layer_submit(
    *,
    packet: dict[str, Any],
    timeout_seconds: int,
    operation_layer_submit_mode: str,
    execute_post_submit_finalize: bool,
) -> dict[str, Any]:
    cookie, cookie_error = _session_cookie()
    if not cookie:
        return _packet_from_operation_layer_submit(
            packet=packet,
            status="operation_layer_submit_blocked",
            blocker_class="deployment_issue",
            dispatch_status="blocked_by_operator_session_unavailable",
            blockers=[cookie_error or "operator_session_unavailable"],
            submit_result={
                "called": False,
                "http_status": None,
                "body": None,
                "error": cookie_error or "operator_session_unavailable",
            },
        )

    command_plan = _dict(packet.get("operation_layer_command_plan"))
    readiness = _dict(packet.get("operation_layer_readiness"))
    url = _operation_layer_submit_url(
        command_plan=command_plan,
        readiness=readiness,
        submit_mode=operation_layer_submit_mode,
    )
    response = _request_json(
        method="POST",
        url=url,
        cookie=cookie,
        timeout_seconds=timeout_seconds,
    )
    body = _dict(response.get("body"))
    submit_result = {
        "called": True,
        "method": "POST",
        "path": command_plan.get("official_endpoint_path"),
        "http_status": response.get("http_status"),
        "body": response.get("body"),
        "error": bool(response.get("error")),
        "error_type": response.get("error_type"),
        "error_message": response.get("error_message"),
        "owner_confirmed_for_first_real_submit_action": (
            operation_layer_submit_mode == OPERATION_LAYER_SUBMIT_MODE_REAL
        ),
        "operation_layer_submit_mode": operation_layer_submit_mode,
        "official_operation_layer_submit_called": True,
        "official_operation_layer_endpoint": True,
    }

    http_status = response.get("http_status")
    if http_status in {401, 403}:
        return _packet_from_operation_layer_submit(
            packet=packet,
            status="operation_layer_submit_blocked",
            blocker_class="deployment_issue",
            dispatch_status="blocked_by_operator_session_http_error",
            blockers=[f"operator_session_http_status:{http_status}"],
            submit_result=submit_result,
        )
    if response.get("error"):
        return _packet_from_operation_layer_submit(
            packet=packet,
            status="operation_layer_submit_blocked",
            blocker_class="deployment_issue",
            dispatch_status="blocked_by_operation_layer_submit_http_error",
            blockers=[
                f"operation_layer_submit_http_status:{http_status or 'unavailable'}"
            ],
            submit_result=submit_result,
        )

    forbidden_effects = _operation_layer_submit_forbidden_effects(body)
    if forbidden_effects:
        return _packet_from_operation_layer_submit(
            packet=packet,
            status="operation_layer_submit_blocked",
            blocker_class="hard_safety_stop",
            dispatch_status="blocked_by_operation_layer_submit_forbidden_effect",
            blockers=forbidden_effects,
            submit_result=submit_result,
        )

    body_status = str(body.get("status") or "")
    body_blockers = _dedupe_text(body.get("blockers") or [])
    if operation_layer_submit_mode == OPERATION_LAYER_SUBMIT_MODE_DISABLED_SMOKE:
        if body_status != "exchange_submit_execution_disabled":
            return _packet_from_operation_layer_submit(
                packet=packet,
                status="operation_layer_submit_blocked",
                blocker_class="hard_safety_stop",
                dispatch_status="blocked_by_disabled_smoke_submit_result",
                blockers=[
                    "disabled_smoke_expected_exchange_submit_execution_disabled:"
                    f"{body_status or 'missing'}"
                ],
                submit_result=submit_result,
            )
        if (
            body.get("exchange_called") is True
            or body.get("exchange_order_submitted") is True
            or body.get("order_lifecycle_submit_called") is True
        ):
            return _packet_from_operation_layer_submit(
                packet=packet,
                status="operation_layer_submit_blocked",
                blocker_class="hard_safety_stop",
                dispatch_status="blocked_by_disabled_smoke_forbidden_effect",
                blockers=["disabled_smoke_reported_submit_side_effect"],
                submit_result=submit_result,
            )
        return _packet_from_operation_layer_submit(
            packet=packet,
            status="operation_layer_disabled_smoke_passed",
            blocker_class="none",
            dispatch_status="official_operation_layer_disabled_smoke_passed",
            blockers=[],
            submit_result=submit_result,
        )
    if operation_layer_submit_mode != OPERATION_LAYER_SUBMIT_MODE_REAL:
        return _packet_from_operation_layer_submit(
            packet=packet,
            status="operation_layer_submit_blocked",
            blocker_class="hard_safety_stop",
            dispatch_status="blocked_by_invalid_operation_layer_submit_mode",
            blockers=[
                f"invalid_operation_layer_submit_mode:{operation_layer_submit_mode}"
            ],
            submit_result=submit_result,
        )
    if body_status == "exchange_submit_orders_submitted":
        identity_blockers = _operation_layer_submit_result_identity_blockers(
            packet=packet,
            body=body,
        )
        if identity_blockers:
            return _packet_from_operation_layer_submit(
                packet=packet,
                status="operation_layer_submit_failed",
                blocker_class=_operation_layer_blocker_class(identity_blockers, []),
                dispatch_status=(
                    "official_operation_layer_submit_result_identity_mismatch"
                ),
                blockers=identity_blockers,
                submit_result=submit_result,
            )
        submit_packet = _packet_from_operation_layer_submit(
            packet=packet,
            status="submitted",
            blocker_class="none",
            dispatch_status="official_operation_layer_submit_completed",
            blockers=[],
            submit_result=submit_result,
        )
        if not execute_post_submit_finalize:
            return submit_packet
        return _execute_post_submit_finalize(
            packet=submit_packet,
            cookie=cookie,
            timeout_seconds=timeout_seconds,
        )
    if body_status in {"entry_submit_failed", "protection_submit_failed"}:
        return _packet_from_operation_layer_submit(
            packet=packet,
            status="operation_layer_submit_failed",
            blocker_class=(
                "active_position_resolution"
                if body_status == "protection_submit_failed"
                else "hard_safety_stop"
            ),
            dispatch_status=f"official_operation_layer_{body_status}",
            blockers=body_blockers or [body_status],
            submit_result=submit_result,
        )

    return _packet_from_operation_layer_submit(
        packet=packet,
        status="operation_layer_submit_blocked",
        blocker_class=_operation_layer_blocker_class(body_blockers, []),
        dispatch_status="blocked_by_operation_layer_submit_result",
        blockers=body_blockers or [f"operation_layer_submit_status:{body_status}"],
        submit_result=submit_result,
    )


def _operation_layer_submit_forbidden_effects(body: dict[str, Any]) -> list[str]:
    effects: list[str] = []
    checks = {
        "withdrawal_or_transfer_created": False,
        "owner_bounded_execution_called": False,
        "execution_intent_status_changed": False,
    }
    for name, expected in checks.items():
        if body.get(name) not in {expected, None, "", 0}:
            effects.append(f"operation_layer_submit_effect:{name}")
    if body.get("status") == "exchange_submit_orders_submitted":
        if body.get("execution_mode") != "real_gateway_action":
            effects.append("operation_layer_submit_not_real_gateway_action")
        if body.get("exchange_order_submitted") is not True:
            effects.append("operation_layer_submit_missing_exchange_order_submitted")
        if body.get("order_lifecycle_submit_called") is not True:
            effects.append("operation_layer_submit_missing_order_lifecycle_submit")
    return effects


def _operation_layer_submit_result_identity_blockers(
    *,
    packet: dict[str, Any],
    body: dict[str, Any],
) -> list[str]:
    command_plan = _dict(packet.get("operation_layer_command_plan"))
    readiness = _dict(packet.get("operation_layer_readiness"))
    ids = _dict(readiness.get("available_evidence_ids"))
    selected_runtime_ids = [
        str(item)
        for item in _list(packet.get("selected_runtime_instance_ids"))
        if str(item or "").strip()
    ]
    expected_authorization_id = _first_text(
        command_plan.get("authorization_id"),
        ids.get("authorization_id"),
    )
    actual_authorization_id = _first_text(body.get("authorization_id"))
    expected_runtime_instance_id = _first_text(
        ids.get("runtime_instance_id"),
        selected_runtime_ids[0] if len(selected_runtime_ids) == 1 else None,
    )
    actual_runtime_instance_id = _first_text(body.get("runtime_instance_id"))
    expected_reservation_id = _first_text(
        ids.get("reservation_id"),
        ids.get("attempt_reservation_id"),
        ids.get("attempt_reservation"),
    )
    actual_reservation_id = _first_text(
        body.get("reservation_id"),
        body.get("attempt_reservation_id"),
        body.get("attempt_reservation"),
    )
    blockers: list[str] = []
    if not actual_authorization_id:
        blockers.append("operation_layer_submit_authorization_id_missing")
    elif expected_authorization_id and actual_authorization_id != expected_authorization_id:
        blockers.append(
            "operation_layer_submit_authorization_id_mismatch:"
            f"expected={expected_authorization_id}:actual={actual_authorization_id}"
        )
    if not actual_runtime_instance_id:
        blockers.append("operation_layer_submit_runtime_instance_id_missing")
    elif expected_runtime_instance_id and actual_runtime_instance_id != expected_runtime_instance_id:
        blockers.append(
            "operation_layer_submit_runtime_instance_id_mismatch:"
            f"expected={expected_runtime_instance_id}:actual={actual_runtime_instance_id}"
        )
    if (
        actual_reservation_id
        and expected_reservation_id
        and actual_reservation_id != expected_reservation_id
    ):
        blockers.append(
            "operation_layer_submit_reservation_id_mismatch:"
            f"expected={expected_reservation_id}:actual={actual_reservation_id}"
        )
    return _dedupe_text(blockers)


def _packet_from_operation_layer_submit(
    *,
    packet: dict[str, Any],
    status: str,
    blocker_class: str,
    dispatch_status: str,
    blockers: list[str],
    submit_result: dict[str, Any],
) -> dict[str, Any]:
    body = _dict(submit_result.get("body"))
    owner_state = _owner_state_for_operation_layer_submit(
        status=status,
        blocker_class=blocker_class,
        dispatch_status=dispatch_status,
        blockers=blockers,
        body=body,
    )
    called = bool(submit_result.get("called"))
    exchange_called = bool(body.get("exchange_called"))
    exchange_order_submitted = bool(body.get("exchange_order_submitted"))
    order_lifecycle_submit_called = bool(body.get("order_lifecycle_submit_called"))
    return {
        **packet,
        "status": status,
        "blocker_class": blocker_class,
        "dispatch_status": dispatch_status,
        "dispatch_action": (
            POST_SUBMIT_FINALIZE_ACTION
            if status == "submitted"
            else (
                CONTINUE_ACTION
                if status == "operation_layer_disabled_smoke_passed"
                else None
            )
        ),
        "owner_state": owner_state,
        "operation_layer_submit_result": submit_result,
        "blockers": blockers,
        "safety_invariants": {
            **_dict(packet.get("safety_invariants")),
            "dispatcher_only": False,
            "official_operation_layer_submit_called": called,
            "official_operation_layer_submit_endpoint": called,
            "official_operation_layer_submit_http_status": submit_result.get(
                "http_status"
            ),
            "mutates_pg": bool(called or _dict(packet.get("safety_invariants")).get("mutates_pg")),
            "pg_submit_evidence_mutated": called,
            "places_order": exchange_order_submitted,
            "calls_order_lifecycle": order_lifecycle_submit_called,
            "exchange_write_called": exchange_called,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": bool(
                body.get("withdrawal_or_transfer_created")
            ),
            "official_post_submit_finalize_called": False,
            "post_submit_budget_settlement_called": False,
        },
    }


def _execute_post_submit_finalize(
    *,
    packet: dict[str, Any],
    cookie: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    context = _post_submit_finalize_context(packet)
    blockers = list(context.get("blockers") or [])
    if blockers:
        return _packet_from_post_submit_finalize(
            packet=packet,
            status="post_submit_finalize_blocked",
            blocker_class=_post_submit_finalize_blocker_class(blockers),
            dispatch_status="blocked_before_post_submit_finalize",
            blockers=blockers,
            finalize_result={
                "called": False,
                "http_status": None,
                "body": None,
                "error": "post_submit_finalize_precondition_failed",
            },
        )

    api_base = str(
        _dict(packet.get("operation_layer_command_plan")).get("api_base")
        or DEFAULT_API_BASE
    ).rstrip("/")
    runtime_instance_id = str(context["runtime_instance_id"])
    authorization_id = str(context["authorization_id"])
    reservation_id = context.get("reservation_id")
    path = (
        "/api/trading-console/strategy-runtimes/"
        f"{urllib.parse.quote(runtime_instance_id, safe='')}"
        "/post-submit-finalize-packets"
    )
    body: dict[str, Any] = {
        "authorization_id": authorization_id,
        "closed_review_required": False,
        "protection_blockers": [],
        "metadata": {
            "runtime_signal_watcher_resume_dispatcher": True,
            "automatic_recovery_action": POST_SUBMIT_FINALIZE_ACTION,
            "operation_layer_submit_dispatch_status": packet.get("dispatch_status"),
        },
        "non_executing": True,
    }
    if reservation_id:
        body["reservation_id"] = str(reservation_id)

    response = _request_json(
        method="POST",
        url=api_base + path,
        cookie=cookie,
        timeout_seconds=timeout_seconds,
        body=body,
    )
    finalize_result = {
        "called": True,
        "method": "POST",
        "path": path,
        "http_status": response.get("http_status"),
        "body": response.get("body"),
        "error": bool(response.get("error")),
        "error_type": response.get("error_type"),
        "error_message": response.get("error_message"),
        "authorization_id": authorization_id,
        "runtime_instance_id": runtime_instance_id,
        "reservation_id": reservation_id,
        "official_post_submit_finalize_endpoint": True,
        "exchange_write_called": False,
        "places_order": False,
        "calls_order_lifecycle": False,
        "withdrawal_or_transfer_created": False,
    }
    http_status = response.get("http_status")
    if http_status in {401, 403}:
        return _packet_from_post_submit_finalize(
            packet=packet,
            status="post_submit_finalize_blocked",
            blocker_class="deployment_issue",
            dispatch_status="blocked_by_operator_session_http_error",
            blockers=[f"operator_session_http_status:{http_status}"],
            finalize_result=finalize_result,
        )
    if response.get("error"):
        return _packet_from_post_submit_finalize(
            packet=packet,
            status="post_submit_finalize_blocked",
            blocker_class="deployment_issue",
            dispatch_status="blocked_by_post_submit_finalize_http_error",
            blockers=[
                f"post_submit_finalize_http_status:{http_status or 'unavailable'}"
            ],
            finalize_result=finalize_result,
        )

    finalize_body = _dict(response.get("body"))
    forbidden_effects = _post_submit_finalize_forbidden_effects(finalize_body)
    if forbidden_effects:
        return _packet_from_post_submit_finalize(
            packet=packet,
            status="post_submit_finalize_blocked",
            blocker_class="hard_safety_stop",
            dispatch_status="blocked_by_post_submit_finalize_forbidden_effect",
            blockers=forbidden_effects,
            finalize_result=finalize_result,
        )

    body_status = str(finalize_body.get("status") or "")
    blockers = _dedupe_text(
        [
            *list(finalize_body.get("blockers") or []),
            *list(_dict(finalize_body.get("next_attempt_gate")).get("blockers") or []),
        ]
    )
    identity_blockers = _post_submit_finalize_result_identity_blockers(
        context=context,
        body=finalize_body,
    )
    if identity_blockers:
        return _packet_from_post_submit_finalize(
            packet=packet,
            status="post_submit_finalize_blocked",
            blocker_class=_post_submit_finalize_blocker_class(identity_blockers),
            dispatch_status="post_submit_finalize_result_identity_mismatch",
            blockers=identity_blockers,
            finalize_result=finalize_result,
        )
    if body_status == "finalized_ready_for_next_attempt":
        closed_loop_blockers = _post_submit_finalize_closed_loop_blockers(
            finalize_body
        )
        if closed_loop_blockers:
            return _packet_from_post_submit_finalize(
                packet=packet,
                status="post_submit_finalize_blocked",
                blocker_class=_post_submit_finalize_blocker_class(
                    closed_loop_blockers
                ),
                dispatch_status=(
                    "blocked_by_post_submit_finalize_incomplete_closed_loop"
                ),
                blockers=closed_loop_blockers,
                finalize_result=finalize_result,
            )
        return _packet_from_post_submit_finalize(
            packet=packet,
            status="settled",
            blocker_class="none",
            dispatch_status="post_submit_finalize_completed_next_attempt_ready",
            blockers=[],
            finalize_result=finalize_result,
        )
    if body_status == "finalized_next_attempt_blocked":
        return _packet_from_post_submit_finalize(
            packet=packet,
            status="post_submit_finalized_next_attempt_blocked",
            blocker_class=_post_submit_finalize_blocker_class(blockers),
            dispatch_status="post_submit_finalize_completed_next_attempt_blocked",
            blockers=blockers or ["next_attempt_gate_blocked"],
            finalize_result=finalize_result,
        )
    return _packet_from_post_submit_finalize(
        packet=packet,
        status="post_submit_finalize_blocked",
        blocker_class=_post_submit_finalize_blocker_class(blockers),
        dispatch_status="blocked_by_post_submit_finalize_result",
        blockers=blockers or [
            f"post_submit_finalize_status:{body_status or 'missing'}"
        ],
        finalize_result=finalize_result,
    )


def _post_submit_finalize_closed_loop_blockers(body: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    required_ids = {
        "exchange_submit_execution_result_id": (
            "post_submit_finalize_exchange_submit_execution_result_id_missing"
        ),
        "post_submit_budget_settlement_id": (
            "post_submit_finalize_budget_settlement_id_missing"
        ),
        "submit_outcome_review_id": "post_submit_finalize_review_id_missing",
    }
    for field, blocker in required_ids.items():
        if not _nonempty(body.get(field)):
            blockers.append(blocker)

    next_attempt_gate = _dict(body.get("next_attempt_gate"))
    next_attempt_status = str(next_attempt_gate.get("status") or "").strip()
    if next_attempt_status != "ready_for_fresh_signal":
        blockers.append(
            "post_submit_finalize_next_attempt_gate_not_ready:"
            f"{next_attempt_status or 'missing'}"
        )
    return _dedupe_text(blockers)


def _post_submit_finalize_result_identity_blockers(
    *,
    context: dict[str, Any],
    body: dict[str, Any],
) -> list[str]:
    expected_authorization_id = _first_text(context.get("authorization_id"))
    actual_authorization_id = _first_text(body.get("authorization_id"))
    expected_runtime_instance_id = _first_text(context.get("runtime_instance_id"))
    actual_runtime_instance_id = _first_text(body.get("runtime_instance_id"))
    expected_reservation_id = _first_text(context.get("reservation_id"))
    actual_reservation_id = _first_text(
        body.get("reservation_id"),
        body.get("attempt_reservation_id"),
        body.get("attempt_reservation"),
    )
    blockers: list[str] = []
    if not actual_authorization_id:
        blockers.append("post_submit_finalize_authorization_id_missing")
    elif expected_authorization_id and actual_authorization_id != expected_authorization_id:
        blockers.append(
            "post_submit_finalize_authorization_id_mismatch:"
            f"expected={expected_authorization_id}:actual={actual_authorization_id}"
        )
    if not actual_runtime_instance_id:
        blockers.append("post_submit_finalize_runtime_instance_id_missing")
    elif expected_runtime_instance_id and actual_runtime_instance_id != expected_runtime_instance_id:
        blockers.append(
            "post_submit_finalize_runtime_instance_id_mismatch:"
            f"expected={expected_runtime_instance_id}:actual={actual_runtime_instance_id}"
        )
    if (
        actual_reservation_id
        and expected_reservation_id
        and actual_reservation_id != expected_reservation_id
    ):
        blockers.append(
            "post_submit_finalize_reservation_id_mismatch:"
            f"expected={expected_reservation_id}:actual={actual_reservation_id}"
        )
    return _dedupe_text(blockers)


def _post_submit_finalize_context(packet: dict[str, Any]) -> dict[str, Any]:
    body = _dict(_dict(packet.get("operation_layer_submit_result")).get("body"))
    command_plan = _dict(packet.get("operation_layer_command_plan"))
    readiness = _dict(packet.get("operation_layer_readiness"))
    ids = _dict(readiness.get("available_evidence_ids"))
    selected_runtime_ids = [
        str(item)
        for item in _list(packet.get("selected_runtime_instance_ids"))
        if str(item or "").strip()
    ]
    authorization_id = _first_text(
        body.get("authorization_id"),
        command_plan.get("authorization_id"),
        ids.get("authorization_id"),
    )
    runtime_instance_id = _first_text(
        body.get("runtime_instance_id"),
        ids.get("runtime_instance_id"),
        selected_runtime_ids[0] if len(selected_runtime_ids) == 1 else None,
    )
    reservation_id = _first_text(
        body.get("reservation_id"),
        ids.get("reservation_id"),
        ids.get("attempt_reservation_id"),
        ids.get("attempt_reservation"),
    )
    blockers: list[str] = []
    if not authorization_id:
        blockers.append("post_submit_finalize_authorization_id_missing")
    if not runtime_instance_id:
        blockers.append("post_submit_finalize_runtime_instance_id_missing")
    body_runtime_id = _first_text(body.get("runtime_instance_id"))
    if body_runtime_id and selected_runtime_ids and body_runtime_id not in selected_runtime_ids:
        blockers.append(
            "post_submit_finalize_runtime_instance_id_mismatch:"
            f"body={body_runtime_id}:selected={','.join(selected_runtime_ids)}"
        )
    return {
        "authorization_id": authorization_id,
        "runtime_instance_id": runtime_instance_id,
        "reservation_id": reservation_id,
        "blockers": blockers,
    }


def _post_submit_finalize_forbidden_effects(body: dict[str, Any]) -> list[str]:
    effects: list[str] = []
    checks = {
        "exchange_called": False,
        "exchange_order_submitted": False,
        "order_lifecycle_called": False,
        "owner_bounded_execution_called": False,
        "withdrawal_or_transfer_created": False,
        "position_closed": False,
        "order_cancelled": False,
        "order_created": False,
    }
    for name, expected in checks.items():
        if body.get(name) not in {expected, None, "", 0}:
            effects.append(f"post_submit_finalize_effect:{name}")
    return effects


def _post_submit_finalize_blocker_class(blockers: list[str]) -> str:
    combined = " ".join(str(item).lower() for item in blockers)
    if any(token in combined for token in ("withdraw", "transfer", "bypass")):
        return "hard_safety_stop"
    if "runtime_instance_id_mismatch" in combined:
        return "hard_safety_stop"
    if any(
        token in combined
        for token in ("active_position", "open_order", "protection")
    ):
        return "active_position_resolution"
    if any(token in combined for token in ("session", "http", "repository", "service")):
        return "deployment_issue"
    return "missing_fact"


def _packet_from_post_submit_finalize(
    *,
    packet: dict[str, Any],
    status: str,
    blocker_class: str,
    dispatch_status: str,
    blockers: list[str],
    finalize_result: dict[str, Any],
) -> dict[str, Any]:
    body = _dict(finalize_result.get("body"))
    owner_state = _owner_state_for_post_submit_finalize(
        status=status,
        blocker_class=blocker_class,
        dispatch_status=dispatch_status,
        blockers=blockers,
        body=body,
    )
    finalize_called = bool(finalize_result.get("called"))
    settlement_called = bool(body.get("post_submit_budget_settlement_id"))
    return {
        **packet,
        "status": status,
        "blocker_class": blocker_class,
        "dispatch_status": dispatch_status,
        "dispatch_action": CONTINUE_ACTION if status == "settled" else None,
        "owner_state": owner_state,
        "post_submit_finalize_result": finalize_result,
        "blockers": blockers,
        "warnings": _dedupe_text(
            [
                *list(packet.get("warnings") or []),
                *list(body.get("warnings") or []),
            ]
        ),
        "safety_invariants": {
            **_dict(packet.get("safety_invariants")),
            "dispatcher_only": False,
            "official_post_submit_finalize_called": finalize_called,
            "official_post_submit_finalize_endpoint": finalize_called,
            "post_submit_budget_settlement_called": settlement_called,
            "runtime_budget_mutated": settlement_called,
            "mutates_pg": bool(
                finalize_called
                or _dict(packet.get("safety_invariants")).get("mutates_pg")
            ),
            "places_order": bool(
                _dict(packet.get("safety_invariants")).get("places_order")
            ),
            "calls_order_lifecycle": bool(
                _dict(packet.get("safety_invariants")).get("calls_order_lifecycle")
            ),
            "exchange_write_called": bool(
                _dict(packet.get("safety_invariants")).get("exchange_write_called")
            ),
            "withdrawal_or_transfer_created": bool(
                body.get("withdrawal_or_transfer_created")
                or _dict(packet.get("safety_invariants")).get(
                    "withdrawal_or_transfer_created"
                )
            ),
        },
    }


def _owner_state_for_operation_layer_submit(
    *,
    status: str,
    blocker_class: str,
    dispatch_status: str,
    blockers: list[str],
    body: dict[str, Any],
) -> dict[str, Any]:
    if status == "submitted":
        return {
            "status": "submitted",
            "blocker_class": "none",
            "blocked_at": "none",
            "blocked_reason": "none",
            "next_recover_condition": "post_submit_finalize_reconciliation_budget_settlement",
            "automatic_recovery_action": POST_SUBMIT_FINALIZE_ACTION,
            "downgrade_mode": "none",
            "exchange_submit_execution_status": body.get("status"),
        }
    if status == "operation_layer_disabled_smoke_passed":
        return {
            "status": status,
            "blocker_class": "none",
            "blocked_at": "none",
            "blocked_reason": "none",
            "next_recover_condition": "fresh_strategy_signal_or_real_gateway_action",
            "automatic_recovery_action": CONTINUE_ACTION,
            "downgrade_mode": "none",
            "exchange_submit_execution_status": body.get("status"),
        }
    if status == "operation_layer_submit_failed":
        return {
            "status": status,
            "blocker_class": blocker_class,
            "blocked_at": "OperationLayerSubmit",
            "blocked_reason": blockers[0] if blockers else dispatch_status,
            "next_recover_condition": (
                "reconcile_exchange_and_local_order_state_then_apply_recovery_policy"
            ),
            "automatic_recovery_action": (
                "run_post_submit_reconciliation_and_protection_failure_policy"
            ),
            "downgrade_mode": "halt_new_entries_until_reconciled",
            "exchange_submit_execution_status": body.get("status"),
        }
    return {
        "status": status,
        "blocker_class": blocker_class,
        "blocked_at": "OperationLayerSubmit",
        "blocked_reason": blockers[0] if blockers else dispatch_status,
        "next_recover_condition": "operation_layer_submit_blocker_resolved",
        "automatic_recovery_action": (
            "refresh_operation_layer_evidence_and_rerun_action_time_finalgate"
        ),
        "downgrade_mode": "continue_watcher_observation_no_submit",
        "exchange_submit_execution_status": body.get("status"),
    }


def _owner_state_for_post_submit_finalize(
    *,
    status: str,
    blocker_class: str,
    dispatch_status: str,
    blockers: list[str],
    body: dict[str, Any],
) -> dict[str, Any]:
    if status == "settled":
        return {
            "status": "settled",
            "blocker_class": "none",
            "blocked_at": "none",
            "blocked_reason": "none",
            "next_recover_condition": "fresh_strategy_signal_for_next_attempt",
            "automatic_recovery_action": CONTINUE_ACTION,
            "downgrade_mode": "none",
            "post_submit_finalize_status": body.get("status"),
            "next_attempt_gate_status": _dict(body.get("next_attempt_gate")).get(
                "status"
            ),
        }
    if status == "post_submit_finalized_next_attempt_blocked":
        return {
            "status": status,
            "blocker_class": blocker_class,
            "blocked_at": "NextAttemptGate",
            "blocked_reason": blockers[0] if blockers else dispatch_status,
            "next_recover_condition": "next_attempt_gate_blocker_resolved",
            "automatic_recovery_action": (
                "resolve_next_attempt_gate_blocker_before_new_signal"
            ),
            "downgrade_mode": "halt_new_entries_until_next_gate_ready",
            "post_submit_finalize_status": body.get("status"),
        }
    return {
        "status": status,
        "blocker_class": blocker_class,
        "blocked_at": "PostSubmitFinalize",
        "blocked_reason": blockers[0] if blockers else dispatch_status,
        "next_recover_condition": "post_submit_finalize_blocker_resolved",
        "automatic_recovery_action": (
            "retry_official_post_submit_finalize_after_repair"
        ),
        "downgrade_mode": "halt_new_entries_until_post_submit_settled",
        "post_submit_finalize_status": body.get("status"),
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
        "--selected-strategy-group-id",
        default=os.environ.get("BRC_SELECTED_STRATEGY_GROUP_ID")
        or os.environ.get("BRC_STRATEGYGROUP_SELECTED_ID"),
        help=(
            "Optional selected StrategyGroup scope. When set, actionable "
            "fresh-authorization, FinalGate, or Operation Layer dispatch is "
            "blocked unless the resume packet proves the action belongs to "
            "that StrategyGroup."
        ),
    )
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
        "--execute-operation-layer-submit",
        action="store_true",
        help=(
            "After official FinalGate preflight passes and Operation Layer "
            "evidence is ready, call the official first-real-submit action "
            "endpoint using standing authorization. This is the only mode in "
            "this dispatcher that can place a real order."
        ),
    )
    parser.add_argument(
        "--operation-layer-submit-mode",
        choices=sorted(OPERATION_LAYER_SUBMIT_MODES),
        default=OPERATION_LAYER_SUBMIT_MODE_REAL,
        help=(
            "Operation Layer submit mode used with "
            "--execute-operation-layer-submit. real_gateway_action keeps the "
            "existing real-order boundary; disabled_smoke calls the same "
            "official endpoint with owner confirmation forced false and "
            "requires exchange_submit_execution_disabled."
        ),
    )
    parser.add_argument(
        "--execute-post-submit-finalize",
        action="store_true",
        help=(
            "After official Operation Layer submit succeeds, call the official "
            "post-submit finalize endpoint to record reconciliation and budget "
            "settlement evidence."
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
        execute_operation_layer_submit=args.execute_operation_layer_submit,
        operation_layer_submit_mode=args.operation_layer_submit_mode,
        execute_post_submit_finalize=args.execute_post_submit_finalize,
        selected_strategy_group_id=args.selected_strategy_group_id,
    )
    _write_json(Path(args.output_json).expanduser(), packet)
    print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if packet["status"] in {
        WAITING_STATUS,
        READY_STATUS,
        *FRESH_AUTHORIZATION_STATUSES,
        NON_EXECUTING_PREPARE_STATUS,
        "fresh_authorization_bound",
        "finalgate_ready",
        "operation_layer_ready",
        "operation_layer_blocked",
        "operation_layer_submit_blocked",
        "operation_layer_submit_failed",
        "submitted",
        "settled",
        "post_submit_finalize_blocked",
        "post_submit_finalized_next_attempt_blocked",
        "blocked",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
