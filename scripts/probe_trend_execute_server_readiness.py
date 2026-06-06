#!/usr/bin/env python3
"""Probe the server API evidence chain for the exact Trend bounded action.

Default mode is evidence-only. It calls GET endpoints for credential preflight,
execution state, execute readiness, and final-gate dry-run. Fresh Owner
authorization metadata can be created only with TREND_EXECUTE_MODE=prepare_authorization
and the exact Owner approval env. The final execute POST is available only when
TREND_EXECUTE_MODE=execute and the exact Owner approval env is present.

The script never prints credentials, cookies, tokens, or request headers.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.interfaces.operator_auth import SESSION_COOKIE, _load_auth_config, _sign_payload


API_BASE_ENV = "TREND_EXECUTE_API_BASE"
API_BASE_FALLBACK_ENV = "OWNER_BOUNDED_API_BASE"
SESSION_COOKIE_ENV = "TREND_EXECUTE_SESSION_COOKIE"
SESSION_COOKIE_FALLBACK_ENV = "OWNER_BOUNDED_SESSION_COOKIE"
MODE_ENV = "TREND_EXECUTE_MODE"
AUTHORIZATION_ID_ENV = "TREND_EXECUTE_AUTHORIZATION_ID"
APPROVAL_ENV = "OWNER_APPROVED_TREND_BOUNDED_EXECUTION"
APPROVAL_VALUE = (
    "TF-001-live-readonly-v0:SOL/USDT:USDT:LONG:0.1:20:1:"
    "max_attempts_1:single_tp_plus_sl"
)

TREND_SCOPE = {
    "carrier_id": "TF-001-live-readonly-v0",
    "symbol": "SOL/USDT:USDT",
    "side": "long",
    "quantity": "0.1",
    "max_notional": "20",
    "leverage": "1",
    "protection_plan_type": "single_tp_plus_sl",
}

REDACT_KEYS = {
    "api_key",
    "api_secret",
    "authorization_header",
    "cookie",
    "password",
    "secret",
    "session",
    "token",
}


def _api_base() -> str:
    base = (os.environ.get(API_BASE_ENV) or os.environ.get(API_BASE_FALLBACK_ENV) or "").strip()
    if not base:
        raise RuntimeError(f"{API_BASE_ENV} or {API_BASE_FALLBACK_ENV} is required")
    return base.rstrip("/")


def _redact(data: Any) -> Any:
    if isinstance(data, dict):
        result: dict[str, Any] = {}
        for key, value in data.items():
            key_text = str(key).lower()
            if (
                key_text in REDACT_KEYS
                or key_text.endswith("_api_key")
                or key_text.endswith("_secret")
                or key_text.endswith("_token")
                or key_text.endswith("_cookie")
                or key_text.endswith("_password")
            ):
                result[key] = "<redacted>"
            else:
                result[key] = _redact(value)
        return result
    if isinstance(data, list):
        return [_redact(item) for item in data]
    return data


def _json(data: Any) -> str:
    return json.dumps(_redact(data), ensure_ascii=False, indent=2, default=str)


def _session_cookie() -> str:
    explicit = (
        os.environ.get(SESSION_COOKIE_ENV)
        or os.environ.get(SESSION_COOKIE_FALLBACK_ENV)
        or ""
    ).strip()
    if explicit:
        if "=" in explicit:
            return explicit
        return f"{SESSION_COOKIE}={explicit}"

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
    return f"{SESSION_COOKIE}={token}"


def _request_json(
    method: str,
    path: str,
    *,
    cookie: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        _api_base() + path,
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "Cookie": cookie,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return {
                "status": response.status,
                "body": json.loads(raw) if raw else None,
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed: Any = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"raw_text_redacted": raw[:500]}
        return {
            "status": exc.code,
            "body": parsed,
        }
    except Exception as exc:
        return {
            "status": "transport_error",
            "body": {
                "error_type": type(exc).__name__,
                "message": str(exc),
            },
        }


def _preflight_path() -> str:
    query = urllib.parse.urlencode({"run": "true", "symbol": TREND_SCOPE["symbol"]})
    return f"/api/brc/owner-trial-flow/exchange-credential-preflight?{query}"


def _authorization_path(authorization_id: str, suffix: str) -> str:
    return f"/api/brc/owner-trial-flow/authorizations/{authorization_id}/{suffix}"


def _current_path() -> str:
    query = urllib.parse.urlencode({"carrier_id": TREND_SCOPE["carrier_id"]})
    return f"/api/brc/owner-trial-flow/current?{query}"


def _passed(response: dict[str, Any]) -> bool:
    if response.get("status") != 200:
        return False
    body = response.get("body") or {}
    if not isinstance(body, dict):
        return False
    result = body.get("result")
    if result in {"passed", "ready"}:
        return True
    if body.get("ready") is True and not body.get("blockers"):
        return True
    final_gate = body.get("final_gate")
    if isinstance(final_gate, dict):
        return (
            body.get("result") == "passed"
            and final_gate.get("final_preflight_result") == "passed"
            and not final_gate.get("hard_blockers")
        )
    return False


def _execution_state_passed(response: dict[str, Any]) -> bool:
    if response.get("status") != 200:
        return False
    body = response.get("body") or {}
    if not isinstance(body, dict):
        return False
    return bool(body.get("retry_allowed")) and not body.get("retry_blockers")


def _execute_guard(mode: str, authorization_id: str | None) -> list[str]:
    if mode not in {"execute", "prepare_authorization"}:
        return []
    blockers: list[str] = []
    if (os.environ.get(APPROVAL_ENV) or "").strip() != APPROVAL_VALUE:
        blockers.append(f"{APPROVAL_ENV}_missing_or_wrong")
    if mode == "execute" and (not authorization_id or not authorization_id.startswith("auth-")):
        blockers.append(f"{AUTHORIZATION_ID_ENV}_missing_or_invalid")
    return blockers


def _http_success(response: dict[str, Any]) -> bool:
    status = response.get("status")
    return isinstance(status, int) and 200 <= status < 400


def _warning_ids(current_body: dict[str, Any]) -> list[str]:
    warnings = current_body.get("strategy_warnings") or []
    return [str(item["warning_id"]) for item in warnings if item.get("warning_id")]


def _prepare_authorization(cookie: str, report: dict[str, Any]) -> None:
    if report.get("execute_guard_blockers") or not _passed(report.get("preflight", {})):
        report["prepare_authorization"] = {
            "status": "blocked_by_probe",
            "body": {
                "blockers": [
                    *report.get("execute_guard_blockers", []),
                    *([] if _passed(report.get("preflight", {})) else ["preflight_not_passed"]),
                ]
            },
        }
        return
    current = _request_json("GET", _current_path(), cookie=cookie)
    report["current"] = current
    if not _http_success(current):
        report["prepare_authorization"] = {
            "status": "blocked_by_probe",
            "body": {"blockers": ["current_authorization_state_unavailable"]},
        }
        return
    warning_ids = _warning_ids(current.get("body") or {})
    if not warning_ids:
        report["prepare_authorization"] = {
            "status": "blocked_by_probe",
            "body": {"blockers": ["strategy_warning_ids_unavailable"]},
        }
        return
    acknowledgement = _request_json(
        "POST",
        "/api/brc/owner-trial-flow/risk-acknowledgement",
        cookie=cookie,
        body={
            "carrier_id": TREND_SCOPE["carrier_id"],
            "acknowledged_warning_codes": warning_ids,
            "acknowledgement_scope": "strategy_trial_warnings",
            "owner_id": "owner",
        },
    )
    report["acknowledgement"] = acknowledgement
    if not _http_success(acknowledgement):
        report["prepare_authorization"] = {
            "status": "blocked_by_probe",
            "body": {"blockers": ["risk_acknowledgement_failed"]},
        }
        return
    draft = _request_json(
        "POST",
        "/api/brc/owner-trial-flow/authorization-draft",
        cookie=cookie,
        body={
            **TREND_SCOPE,
            "linked_acknowledgement_id": acknowledgement["body"]["acknowledgement_id"],
            "owner_id": "owner",
        },
    )
    report["draft"] = draft
    if not _http_success(draft):
        report["prepare_authorization"] = {
            "status": "blocked_by_probe",
            "body": {"blockers": ["authorization_draft_failed"]},
        }
        return
    activation = _request_json(
        "POST",
        f"/api/brc/owner-trial-flow/authorization-draft/{draft['body']['draft_id']}/activate-live-authorization",
        cookie=cookie,
        body={**TREND_SCOPE, "owner_id": "owner"},
    )
    report["activation"] = activation
    report["prepare_authorization"] = {
        "status": "prepared" if _http_success(activation) else "blocked_by_probe",
        "body": (
            {"authorization_id": activation["body"].get("authorization_id")}
            if _http_success(activation) and isinstance(activation.get("body"), dict)
            else {"blockers": ["live_authorization_activation_failed"]}
        ),
    }


def main() -> int:
    mode = (os.environ.get(MODE_ENV) or "evidence").strip().lower()
    if mode not in {"evidence", "prepare_authorization", "execute"}:
        raise RuntimeError(f"unsupported {MODE_ENV}: {mode}")

    authorization_id = (os.environ.get(AUTHORIZATION_ID_ENV) or "").strip() or None
    execute_blockers = _execute_guard(mode, authorization_id)
    cookie = _session_cookie()
    report: dict[str, Any] = {
        "mode": mode,
        "scope": TREND_SCOPE,
        "api_base_present": bool(_api_base()),
        "authorization_id": authorization_id,
        "safety": {
            "prints_secrets": False,
            "default_mode_executes": False,
            "creates_authorization_metadata": mode == "prepare_authorization",
            "creates_execution_intent": False,
            "places_order": False,
            "prepare_authorization_creates_metadata_only": True,
            "execute_requires_exact_owner_approval": True,
        },
        "execute_guard_blockers": execute_blockers,
        "preflight": _request_json("GET", _preflight_path(), cookie=cookie),
    }

    if mode == "prepare_authorization":
        _prepare_authorization(cookie, report)
        print(_json(report))
        return 0 if report.get("prepare_authorization", {}).get("status") == "prepared" else 1

    if authorization_id:
        report["execution_state"] = _request_json(
            "GET",
            _authorization_path(authorization_id, "execution-state"),
            cookie=cookie,
        )
        report["execute_readiness"] = _request_json(
            "GET",
            _authorization_path(authorization_id, "execute-readiness"),
            cookie=cookie,
        )
        report["final_gate_dry_run"] = _request_json(
            "GET",
            _authorization_path(authorization_id, "final-gate-dry-run?run=true"),
            cookie=cookie,
        )

    execute_allowed = (
        mode == "execute"
        and not execute_blockers
        and authorization_id
        and _passed(report["preflight"])
        and _execution_state_passed(report.get("execution_state", {}))
        and _passed(report.get("execute_readiness", {}))
        and _passed(report.get("final_gate_dry_run", {}))
    )
    report["execute_allowed_by_probe"] = bool(execute_allowed)
    if mode == "execute" and not execute_allowed:
        report["execute"] = {
            "status": "blocked_by_probe",
            "body": {
                "blockers": [
                    *execute_blockers,
                    *([] if _passed(report["preflight"]) else ["preflight_not_passed"]),
                    *(
                        []
                        if _execution_state_passed(report.get("execution_state", {}))
                        else ["execution_state_retry_not_allowed"]
                    ),
                    *(
                        []
                        if _passed(report.get("execute_readiness", {}))
                        else ["execute_readiness_not_passed"]
                    ),
                    *(
                        []
                        if _passed(report.get("final_gate_dry_run", {}))
                        else ["final_gate_dry_run_not_passed"]
                    ),
                ]
            },
        }
    elif execute_allowed and authorization_id:
        report["execute"] = _request_json(
            "POST",
            _authorization_path(authorization_id, "execute"),
            cookie=cookie,
        )

    print(_json(report))
    if mode == "execute":
        return 0 if bool(execute_allowed) and _http_success(report.get("execute", {})) else 1
    return 0 if report["preflight"].get("status") == 200 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(_json({"error": type(exc).__name__, "message": str(exc)}))
        raise SystemExit(1)
