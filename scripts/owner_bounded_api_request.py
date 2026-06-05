#!/usr/bin/env python3
"""Guarded local API requests for the Owner bounded BNB execution path.

This script never reads passwords or TOTP codes. It signs a short-lived
operator session cookie from the already configured backend session secret, then
calls the local API surface on 127.0.0.1. It is intended for controlled
acceptance evidence where the Owner has explicitly authorized the exact BNB
scope.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any

from src.interfaces.operator_auth import (
    SESSION_COOKIE,
    _load_auth_config,
    _sign_payload,
)


API_BASE_ENV = "OWNER_BOUNDED_API_BASE"
MODE_ENV = "OWNER_BOUNDED_API_MODE"
APPROVAL_ENV = "OWNER_APPROVED_BNB_BOUNDED_EXECUTION"
APPROVAL_VALUE = "BNB/USDT:USDT:LONG:0.01:20:1:max_attempts_1"

BNB_SCOPE = {
    "carrier_id": "MI-001-BNB-LONG",
    "symbol": "BNB/USDT:USDT",
    "side": "long",
    "max_notional": "20",
    "quantity": "0.01",
    "leverage": "1",
    "protection_plan_type": "single_tp_plus_sl",
}


def _api_base() -> str:
    return (os.environ.get(API_BASE_ENV) or "http://127.0.0.1:18080").rstrip("/")


def _session_cookie() -> str:
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
    body: dict[str, Any] | None = None,
    cookie: str,
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
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8")
            return {
                "status": response.status,
                "body": json.loads(raw) if raw else None,
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed: Any = json.loads(raw)
        except json.JSONDecodeError:
            parsed = raw
        return {
            "status": exc.code,
            "body": parsed,
        }


def _scope_guard() -> None:
    failures: list[str] = []
    expected_env = {
        "TRADING_ENV": "live",
        "EXCHANGE_TESTNET": "false",
        "BRC_EXECUTION_PERMISSION_MAX": "read_only",
        "RUNTIME_CONTROL_API_ENABLED": "false",
        "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED": "false",
    }
    for key, expected in expected_env.items():
        actual = (os.environ.get(key) or "").strip().lower()
        if actual != expected:
            failures.append(f"{key}={actual!r}, expected {expected!r}")
    if (os.environ.get(APPROVAL_ENV) or "").strip() != APPROVAL_VALUE:
        failures.append(f"{APPROVAL_ENV} must equal {APPROVAL_VALUE}")
    if failures:
        raise RuntimeError("owner bounded API request guard failed: " + "; ".join(failures))


def _warning_ids(current: dict[str, Any]) -> list[str]:
    warnings = current.get("strategy_warnings") or []
    ids = [str(item.get("warning_id")) for item in warnings if item.get("warning_id")]
    if not ids:
        raise RuntimeError("no strategy warning ids available for acknowledgement")
    return ids


def run_dry_run(cookie: str) -> dict[str, Any]:
    return _request_json(
        "POST",
        "/api/brc/owner-trial-flow/live-execution-bridge/dry-run",
        body=BNB_SCOPE,
        cookie=cookie,
    )


def run_prepare_authorization(cookie: str) -> dict[str, Any]:
    current = _request_json("GET", "/api/brc/owner-trial-flow/current", cookie=cookie)
    if current["status"] != 200:
        return {"current": current}
    acknowledgement = _request_json(
        "POST",
        "/api/brc/owner-trial-flow/risk-acknowledgement",
        body={
            "carrier_id": BNB_SCOPE["carrier_id"],
            "acknowledged_warning_codes": _warning_ids(current["body"]),
            "acknowledgement_scope": "strategy_trial_warnings",
            "owner_id": "owner",
        },
        cookie=cookie,
    )
    if acknowledgement["status"] >= 300:
        return {"current": current, "acknowledgement": acknowledgement}
    draft = _request_json(
        "POST",
        "/api/brc/owner-trial-flow/authorization-draft",
        body={
            **BNB_SCOPE,
            "linked_acknowledgement_id": acknowledgement["body"]["acknowledgement_id"],
            "owner_id": "owner",
        },
        cookie=cookie,
    )
    if draft["status"] >= 300:
        return {"current": current, "acknowledgement": acknowledgement, "draft": draft}
    activation = _request_json(
        "POST",
        f"/api/brc/owner-trial-flow/authorization-draft/{draft['body']['draft_id']}/activate-live-authorization",
        body={**BNB_SCOPE, "owner_id": "owner"},
        cookie=cookie,
    )
    return {
        "current": current,
        "acknowledgement": acknowledgement,
        "draft": draft,
        "activation": activation,
    }


def run_execute(cookie: str, authorization_id: str) -> dict[str, Any]:
    if not authorization_id.startswith("auth-"):
        raise RuntimeError("authorization_id must be an auth-* id")
    return _request_json(
        "POST",
        f"/api/brc/owner-trial-flow/authorizations/{authorization_id}/execute",
        body={},
        cookie=cookie,
    )


def main() -> None:
    _scope_guard()
    mode = (os.environ.get(MODE_ENV) or "dry_run").strip()
    cookie = _session_cookie()
    if mode == "dry_run":
        result = {"mode": mode, "dry_run": run_dry_run(cookie)}
    elif mode == "prepare_authorization":
        result = {"mode": mode, **run_prepare_authorization(cookie)}
    elif mode == "execute":
        authorization_id = (os.environ.get("OWNER_BOUNDED_AUTHORIZATION_ID") or "").strip()
        result = {"mode": mode, "execute": run_execute(cookie, authorization_id)}
    else:
        raise RuntimeError(f"unsupported mode: {mode}")
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, indent=2))
        sys.exit(1)
