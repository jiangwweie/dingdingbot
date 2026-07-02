#!/usr/bin/env python3
"""Run one guarded Budgeted Autonomy v0.1 cycle through official local APIs.

The script does not use exchange or PG write APIs directly. It signs an
operator session cookie from the configured backend auth secret and calls the
same local API routes the Owner Console exposes.
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

from src.interfaces.operator_auth import SESSION_COOKIE, _load_auth_config, _sign_payload


APPROVAL_ENV = "OWNER_APPROVED_BUDGETED_AUTONOMY_V01"
APPROVAL_VALUE = "budgeted-autonomy-v0.1:one-cycle:official-api:bounded"
API_BASE_ENV = "BUDGETED_AUTONOMY_API_BASE"

DEFAULT_SCOPE = {
    "market_regime": "trend",
    "family": "Trend",
    "strategy_family_id": "TF-001-live-readonly-v0",
    "carrier_id": "TF-001-live-readonly-v0",
    "symbol": "SOL/USDT:USDT",
    "side": "long",
    "quantity": "0.1",
    "max_notional": "20",
    "leverage": "1",
    "max_attempts": "1",
    "protection_mode": "single_tp_plus_sl",
    "review_requirement": "post_action_review_required",
}


def main() -> None:
    _guard()
    cookie = _session_cookie()
    scope = _scope_from_env()
    budget_window = _budget_window_from_env()
    result: dict[str, Any] = {
        "generated_from": "budgeted_autonomy_v01_cycle_runner",
        "initial_scope": dict(scope),
        "budget_window": dict(budget_window),
        "scope": scope,
        "safety": _safety_flags(),
        "steps": [],
    }
    flow = _owner_action_flow(cookie, scope, budget_window)
    result["steps"].append({"name": "owner_action_flow", "response": flow})
    if flow["status"] >= 300:
        _finish(result, "blocked_with_retry_condition", "owner_action_flow_failed")
        return
    flow_body = flow["body"]
    autonomy = (
        flow_body.get("data", {})
        .get("owner_action_flow", {})
        .get("budgeted_autonomy_v01", {})
    )
    if autonomy.get("outcome") == "protected_open_review_pending":
        _finish(result, "executed_protected_open", "active_position_already_exists")
        return
    if autonomy.get("selected_candidate") is None:
        _finish(result, "blocked_with_retry_condition", "no_v01_candidate_selected")
        return
    selected_scope = _scope_from_selected_proposal(flow_body, scope)
    result["selected_scope"] = selected_scope
    result["scope"] = selected_scope
    scope = selected_scope

    current = _request_json(
        "GET",
        "/api/brc/owner-trial-flow/current?"
        + urllib.parse.urlencode({"carrier_id": scope["carrier_id"]}),
        cookie=cookie,
    )
    result["steps"].append({"name": "owner_trial_flow_current", "response": current})
    if current["status"] >= 300:
        _finish(result, "blocked_with_retry_condition", "owner_trial_flow_current_failed")
        return
    warning_ids = _warning_ids(current["body"])
    acknowledgement = _request_json(
        "POST",
        "/api/brc/owner-trial-flow/risk-acknowledgement",
        body={
            "carrier_id": scope["carrier_id"],
            "acknowledged_warning_codes": warning_ids,
            "acknowledgement_scope": "budgeted_autonomy_v0_1_strategy_warnings",
            "owner_id": "owner",
        },
        cookie=cookie,
    )
    result["steps"].append({"name": "risk_acknowledgement", "response": acknowledgement})
    if acknowledgement["status"] >= 300:
        _finish(result, "blocked_with_retry_condition", "risk_acknowledgement_failed")
        return
    draft_body = _trial_scope(scope)
    draft = _request_json(
        "POST",
        "/api/brc/owner-trial-flow/authorization-draft",
        body={
            **draft_body,
            "linked_acknowledgement_id": acknowledgement["body"]["acknowledgement_id"],
            "owner_id": "owner",
        },
        cookie=cookie,
    )
    result["steps"].append({"name": "authorization_draft", "response": draft})
    if draft["status"] >= 300:
        _finish(result, "blocked_with_retry_condition", "authorization_draft_failed")
        return
    activation = _request_json(
        "POST",
        f"/api/brc/owner-trial-flow/authorization-draft/{draft['body']['draft_id']}/activate-live-authorization",
        body={**draft_body, "owner_id": "owner"},
        cookie=cookie,
    )
    result["steps"].append({"name": "live_authorization", "response": activation})
    if activation["status"] >= 300:
        _finish(result, "blocked_with_retry_condition", "live_authorization_failed")
        return
    authorization_id = activation["body"]["authorization_id"]
    final_gate = _request_json(
        "GET",
        f"/api/brc/owner-trial-flow/authorizations/{authorization_id}/final-gate-dry-run?run=true",
        cookie=cookie,
    )
    result["steps"].append({"name": "final_gate_dry_run", "response": final_gate})
    blockers = _extract_blockers(final_gate)
    if blockers:
        for clearance_type in _clearance_types_for_blockers(blockers):
            clearance = _request_json(
                "POST",
                f"/api/brc/owner-trial-flow/authorizations/{authorization_id}/runtime-safety-clearance",
                body={
                    "clearance_type": clearance_type,
                    "reason": "budgeted_autonomy_v0_1_scoped_clearance",
                    "owner_id": "owner",
                },
                cookie=cookie,
            )
            result["steps"].append(
                {"name": f"runtime_safety_clearance_{clearance_type}", "response": clearance}
            )
        final_gate = _request_json(
            "GET",
            f"/api/brc/owner-trial-flow/authorizations/{authorization_id}/final-gate-dry-run?run=true",
            cookie=cookie,
        )
        result["steps"].append({"name": "final_gate_dry_run_after_clearance", "response": final_gate})
        blockers = _extract_blockers(final_gate)
    if blockers:
        _finish(result, "blocked_with_retry_condition", "final_gate_blocked", blockers=blockers)
        return
    execute = _request_json(
        "POST",
        f"/api/brc/owner-trial-flow/authorizations/{authorization_id}/execute",
        body={},
        cookie=cookie,
    )
    result["steps"].append({"name": "execute", "response": execute})
    if execute["status"] >= 300:
        _finish(
            result,
            "blocked_with_retry_condition",
            "execute_blocked",
            blockers=_extract_blockers(execute),
        )
        return
    _finish(result, "executed_protected_open", "execute_returned_success")


def _guard() -> None:
    expected = {
        "TRADING_ENV": "live",
        "EXCHANGE_TESTNET": "false",
        "BRC_EXECUTION_PERMISSION_MAX": "order_allowed",
        "RUNTIME_CONTROL_API_ENABLED": "false",
        "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED": "false",
    }
    failures = []
    for key, expected_value in expected.items():
        actual = (os.environ.get(key) or "").strip().lower()
        if actual != expected_value:
            failures.append(f"{key}={actual!r}, expected {expected_value!r}")
    if (os.environ.get(APPROVAL_ENV) or "").strip() != APPROVAL_VALUE:
        failures.append(f"{APPROVAL_ENV} must equal {APPROVAL_VALUE}")
    if failures:
        raise RuntimeError("budgeted autonomy v0.1 runner guard failed: " + "; ".join(failures))


def _scope_from_env() -> dict[str, str]:
    scope = dict(DEFAULT_SCOPE)
    mapping = {
        "BUDGETED_AUTONOMY_MARKET_REGIME": "market_regime",
        "BUDGETED_AUTONOMY_FAMILY": "family",
        "BUDGETED_AUTONOMY_STRATEGY_FAMILY_ID": "strategy_family_id",
        "BUDGETED_AUTONOMY_CARRIER_ID": "carrier_id",
        "BUDGETED_AUTONOMY_SYMBOL": "symbol",
        "BUDGETED_AUTONOMY_SIDE": "side",
        "BUDGETED_AUTONOMY_QUANTITY": "quantity",
        "BUDGETED_AUTONOMY_TARGET_NOTIONAL_USDT": "target_notional_usdt",
        "BUDGETED_AUTONOMY_MAX_NOTIONAL": "max_notional",
        "BUDGETED_AUTONOMY_LEVERAGE": "leverage",
        "BUDGETED_AUTONOMY_MAX_ATTEMPTS": "max_attempts",
    }
    for env_key, key in mapping.items():
        value = os.environ.get(env_key)
        if value:
            scope[key] = value.strip()
    return scope


def _api_base() -> str:
    return (os.environ.get(API_BASE_ENV) or "http://127.0.0.1:18080").rstrip("/")


def _budget_window_from_env() -> dict[str, str]:
    budget_id = (
        os.environ.get("BUDGETED_AUTONOMY_BUDGET_AUTHORIZATION_ID")
        or f"budget-envelope:owner-approved-v01:{int(time.time() * 1000)}"
    )
    approved_at_ms = (
        os.environ.get("BUDGETED_AUTONOMY_BUDGET_APPROVED_AT_MS")
        or str(int(time.time() * 1000))
    )
    return {
        "custom_budget_authorization_id": budget_id,
        "custom_attempt_window_start_ms": approved_at_ms,
    }


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
        headers={"Content-Type": "application/json", "Cookie": cookie},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8")
            return {"status": response.status, "body": json.loads(raw) if raw else None}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed: Any = json.loads(raw)
        except json.JSONDecodeError:
            parsed = raw
        return {"status": exc.code, "body": parsed}


def _owner_action_flow(
    cookie: str,
    scope: dict[str, str],
    budget_window: dict[str, str],
) -> dict[str, Any]:
    query = urllib.parse.urlencode(
        {
            "include_exchange": "true",
            **scope,
            **budget_window,
            "current_price": os.environ.get("BUDGETED_AUTONOMY_CURRENT_PRICE", ""),
            "min_notional": os.environ.get("BUDGETED_AUTONOMY_MIN_NOTIONAL", ""),
            "min_qty": os.environ.get("BUDGETED_AUTONOMY_MIN_QTY", ""),
            "qty_step": os.environ.get("BUDGETED_AUTONOMY_QTY_STEP", ""),
            "price_tick": os.environ.get("BUDGETED_AUTONOMY_PRICE_TICK", ""),
            "risk_tier": os.environ.get("BUDGETED_AUTONOMY_RISK_TIER", ""),
            "custom_total_budget": os.environ.get("BUDGETED_AUTONOMY_CUSTOM_TOTAL_BUDGET", ""),
            "custom_max_notional_per_action": os.environ.get(
                "BUDGETED_AUTONOMY_CUSTOM_MAX_NOTIONAL_PER_ACTION", ""
            ),
            "custom_max_daily_loss": os.environ.get(
                "BUDGETED_AUTONOMY_CUSTOM_MAX_DAILY_LOSS", ""
            ),
            "custom_capacity_fraction": os.environ.get(
                "BUDGETED_AUTONOMY_CUSTOM_CAPACITY_FRACTION", ""
            ),
            "custom_max_active_positions": os.environ.get(
                "BUDGETED_AUTONOMY_CUSTOM_MAX_ACTIVE_POSITIONS", ""
            ),
            "custom_max_attempts": os.environ.get("BUDGETED_AUTONOMY_CUSTOM_MAX_ATTEMPTS", ""),
            "custom_max_leverage": os.environ.get("BUDGETED_AUTONOMY_CUSTOM_MAX_LEVERAGE", ""),
        }
    )
    return _request_json("GET", f"/api/trading-console/owner-action-flow?{query}", cookie=cookie)


def _scope_from_selected_proposal(flow_body: dict[str, Any], fallback: dict[str, str]) -> dict[str, str]:
    proposal = (
        flow_body.get("data", {})
        .get("owner_action_flow", {})
        .get("selected_action_proposal", {})
    )
    if not isinstance(proposal, dict):
        return dict(fallback)
    result = dict(fallback)
    field_map = {
        "family": "family",
        "strategy_family_id": "strategy_family_id",
        "carrier_id": "carrier_id",
        "symbol": "symbol",
        "side": "side",
        "max_notional": "max_notional",
        "leverage": "leverage",
        "max_attempts": "max_attempts",
        "protection_mode": "protection_mode",
        "review_requirement": "review_requirement",
    }
    for source, target in field_map.items():
        value = proposal.get(source)
        if value not in (None, ""):
            result[target] = str(value)
    quantity = (
        proposal.get("computed_quantity")
        or proposal.get("quantity")
        or proposal.get("recommended_quantity")
    )
    if quantity in (None, ""):
        raise RuntimeError("selected proposal does not provide an exact quantity")
    result["quantity"] = str(quantity)
    target_notional = proposal.get("target_notional_usdt")
    if target_notional not in (None, ""):
        result["target_notional_usdt"] = str(target_notional)
    return result


def _warning_ids(current: dict[str, Any]) -> list[str]:
    warnings = current.get("strategy_warnings") or []
    ids = [str(item.get("warning_id")) for item in warnings if item.get("warning_id")]
    if not ids:
        raise RuntimeError("no strategy warning ids available for acknowledgement")
    return ids


def _trial_scope(scope: dict[str, str]) -> dict[str, str]:
    return {
        "carrier_id": scope["carrier_id"],
        "symbol": scope["symbol"],
        "side": scope["side"],
        "max_notional": scope["max_notional"],
        "quantity": scope["quantity"],
        "leverage": scope["leverage"],
        "protection_plan_type": scope["protection_mode"],
    }


def _extract_blockers(response: dict[str, Any]) -> list[str]:
    body = response.get("body")
    if not isinstance(body, dict):
        return []
    detail = body.get("detail")
    if isinstance(detail, dict):
        return [str(item) for item in detail.get("blockers") or []]
    if isinstance(detail, str):
        return [detail]
    final_gate = body.get("final_gate")
    if isinstance(final_gate, dict) and final_gate.get("final_preflight_result") != "passed":
        return [str(item) for item in final_gate.get("hard_blockers") or ["final_gate_blocked"]]
    if body.get("result") == "blocked":
        return [str(item) for item in body.get("blockers") or ["blocked"]]
    return []


def _clearance_types_for_blockers(blockers: list[str]) -> list[str]:
    clearances: list[str] = []
    text = " ".join(blockers).lower()
    if "gks" in text and "gks" not in clearances:
        clearances.append("gks")
    if "startup_guard" in text and "startup_guard" not in clearances:
        clearances.append("startup_guard")
    return clearances


def _finish(
    result: dict[str, Any],
    outcome: str,
    reason: str,
    *,
    blockers: list[str] | None = None,
) -> None:
    result["outcome"] = outcome
    result["reason"] = reason
    result["blockers"] = blockers or []
    result["safety"] = _safety_flags()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


def _safety_flags() -> dict[str, bool]:
    return {
        "uses_official_local_api": True,
        "direct_pg_write": False,
        "direct_exchange_write": False,
        "auto_execution_enabled": False,
        "broad_action_api": False,
    }


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, indent=2))
        sys.exit(1)
