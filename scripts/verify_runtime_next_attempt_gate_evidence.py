#!/usr/bin/env python3
"""Build non-executing next-attempt gate evidence for a strategy runtime."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import redirect_stdout
from decimal import Decimal
import json
import os
from pathlib import Path
import sys
import time
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


API_BASE_ENV = "RUNTIME_NEXT_ATTEMPT_GATE_API_BASE"


def _load_env_file(path: str | None) -> None:
    if not path:
        return
    env_path = Path(path).expanduser()
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and not os.environ.get(key):
            os.environ[key] = value


def _json_value(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _json_value(value.model_dump(mode="python"))
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _api_base(args: argparse.Namespace) -> str:
    return (args.api_base or os.environ.get(API_BASE_ENV) or "http://127.0.0.1:18080").rstrip("/")


def _session_cookie() -> str:
    from src.interfaces.operator_auth import (
        SESSION_COOKIE,
        _load_auth_config,
        _sign_payload,
    )

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
    url: str,
    *,
    cookie: str,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        method=method,
        headers={"Content-Type": "application/json", "Cookie": cookie},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8")
            return {
                "http_status": response.status,
                "body": json.loads(raw) if raw else None,
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed: Any = json.loads(raw)
        except json.JSONDecodeError:
            parsed = raw
        return {"http_status": exc.code, "body": parsed, "error": True}


async def _load_runtime_context(runtime_instance_id: str) -> dict[str, Any]:
    from src.infrastructure.connection_pool import close_all_connections
    from src.infrastructure.pg_strategy_runtime_repository import (
        PgStrategyRuntimeRepository,
    )

    repository = PgStrategyRuntimeRepository()
    await repository.initialize()
    try:
        runtime = await repository.get(runtime_instance_id)
        if runtime is None:
            raise RuntimeError(f"strategy runtime not found: {runtime_instance_id}")
        boundary = runtime.boundary
        return {
            "runtime_instance_id": runtime.runtime_instance_id,
            "strategy_family_id": runtime.strategy_family_id,
            "strategy_family_version_id": runtime.strategy_family_version_id,
            "carrier_id": runtime.carrier_id or runtime.strategy_family_version_id,
            "symbol": runtime.symbol,
            "side": runtime.side,
            "status": runtime.status.value,
            "execution_enabled": runtime.execution_enabled,
            "shadow_mode": runtime.shadow_mode,
            "review_requirement": runtime.review_requirement.value,
            "max_attempts": boundary.max_attempts,
            "attempts_used": boundary.attempts_used,
            "attempts_remaining": boundary.attempts_remaining,
            "max_notional": boundary.max_notional_per_attempt,
            "max_leverage": boundary.max_leverage,
            "max_active_positions": boundary.max_active_positions,
            "budget_reserved": boundary.budget_reserved,
            "budget_remaining": boundary.budget_remaining,
            "metadata": dict(runtime.metadata),
        }
    finally:
        await close_all_connections()


def _runtime_scope(args: argparse.Namespace, runtime_context: dict[str, Any]) -> dict[str, Any]:
    scope = {
        "symbol": args.symbol or runtime_context.get("symbol"),
        "side": args.side or runtime_context.get("side"),
        "strategy_family_id": (
            args.strategy_family_id or runtime_context.get("strategy_family_id")
        ),
        "carrier_id": args.carrier_id or runtime_context.get("carrier_id"),
        "max_notional": args.max_notional or runtime_context.get("max_notional"),
        "leverage": args.leverage or runtime_context.get("max_leverage"),
        "max_attempts": args.max_attempts or runtime_context.get("max_attempts"),
        "protection_mode": args.protection_mode,
        "review_requirement": args.review_requirement
        or runtime_context.get("review_requirement"),
    }
    if args.family:
        scope["family"] = args.family
    if args.quantity:
        scope["quantity"] = args.quantity
    if args.target_notional_usdt:
        scope["target_notional_usdt"] = args.target_notional_usdt
    return {
        key: _json_value(value)
        for key, value in scope.items()
        if value not in (None, "")
    }


def _owner_action_flow_url(
    *,
    api_base: str,
    include_exchange: bool,
    scope: dict[str, Any],
) -> str:
    query = urllib.parse.urlencode(
        {
            "include_exchange": "true" if include_exchange else "false",
            **{key: str(value) for key, value in scope.items()},
        }
    )
    return f"{api_base}/api/trading-console/owner-action-flow?{query}"


def _extract_next_attempt_gate(body: dict[str, Any]) -> dict[str, Any]:
    data = body.get("data")
    if isinstance(data, dict):
        post_action = data.get("post_action_state")
        if isinstance(post_action, dict) and isinstance(
            post_action.get("next_attempt_gate"),
            dict,
        ):
            return post_action["next_attempt_gate"]
        flow = data.get("owner_action_flow")
        if isinstance(flow, dict) and isinstance(flow.get("next_attempt_gate"), dict):
            return flow["next_attempt_gate"]
    post_action = body.get("post_action_state")
    if isinstance(post_action, dict) and isinstance(post_action.get("next_attempt_gate"), dict):
        return post_action["next_attempt_gate"]
    gate = body.get("next_attempt_gate")
    return gate if isinstance(gate, dict) else {}


def _extract_jit_audit(body: dict[str, Any]) -> dict[str, Any]:
    data = body.get("data")
    if isinstance(data, dict):
        flow = data.get("owner_action_flow")
        if isinstance(flow, dict) and isinstance(flow.get("just_in_time_lifecycle_audit"), dict):
            return flow["just_in_time_lifecycle_audit"]
    return {}


async def _build_gate_evidence(args: argparse.Namespace) -> dict[str, Any]:
    _load_env_file(args.env_file)
    runtime_context = await _load_runtime_context(args.runtime_instance_id)
    scope = _runtime_scope(args, runtime_context)
    missing = [
        key for key in ("symbol", "side", "strategy_family_id", "carrier_id")
        if not scope.get(key)
    ]
    if missing:
        raise RuntimeError("next-attempt gate scope missing: " + ", ".join(missing))

    api_base = _api_base(args)
    url = _owner_action_flow_url(
        api_base=api_base,
        include_exchange=not args.skip_exchange,
        scope=scope,
    )
    response = _request_json("GET", url, cookie=_session_cookie())
    body = response.get("body") if isinstance(response.get("body"), dict) else {}
    gate = _extract_next_attempt_gate(body)
    jit_audit = _extract_jit_audit(body)
    http_status = int(response.get("http_status") or 0)
    clear = (
        http_status < 300
        and gate.get("status") == "clear_for_preflight"
        and gate.get("next_attempt_allowed_by_lifecycle") is True
        and jit_audit.get("can_execute_live") is not True
    )
    status = "clear_for_next_attempt_preflight" if clear else "blocked"
    blockers = []
    if http_status >= 300:
        blockers.append(
            {
                "id": "NEXT-ATTEMPT-GATE-API-ERROR",
                "evidence": f"owner-action-flow HTTP {http_status}",
            }
        )
    if not gate:
        blockers.append(
            {
                "id": "NEXT-ATTEMPT-GATE-MISSING",
                "evidence": "owner-action-flow response did not include next_attempt_gate",
            }
        )
    blockers.extend(
        item for item in gate.get("blockers") or [] if isinstance(item, dict)
    )
    return {
        "scope": "runtime_next_attempt_gate_evidence",
        "status": status,
        "runtime_instance_id": args.runtime_instance_id,
        "runtime_context": _json_value(runtime_context),
        "owner_action_scope": scope,
        "include_exchange": not args.skip_exchange,
        "owner_action_flow_http_status": http_status,
        "next_attempt_gate": _json_value(gate),
        "just_in_time_lifecycle_audit": _json_value(jit_audit),
        "blockers": _json_value(blockers),
        "warnings": _json_value(gate.get("warnings") or []),
        "required_next_step": (
            "fresh_owner_budget_authorization_and_final_gate_preflight"
            if clear
            else gate.get("required_next_step") or "resolve_next_attempt_gate_blocker"
        ),
        "next_attempt_gate_plan": {
            "scope": "runtime_next_attempt_gate_plan",
            "not_executed": True,
            "next_preflight_allowed": clear,
            "live_submit_allowed": False,
            "requires_fresh_authorization": True,
            "requires_official_final_gate": True,
            "places_order": False,
            "creates_execution_intent": False,
        },
        "safety_invariants": {
            "read_only_api_call": True,
            "exchange_read_only": not args.skip_exchange,
            "exchange_write_called": False,
            "execution_intent_created": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "position_closed": False,
            "runtime_state_mutated": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build non-executing next-attempt gate evidence for a strategy runtime.",
    )
    parser.add_argument("--runtime-instance-id", required=True)
    parser.add_argument("--env-file", help="Optional env file to load.")
    parser.add_argument("--api-base", help="Owner Console API base URL.")
    parser.add_argument("--skip-exchange", action="store_true")
    parser.add_argument("--family")
    parser.add_argument("--strategy-family-id")
    parser.add_argument("--carrier-id")
    parser.add_argument("--symbol")
    parser.add_argument("--side")
    parser.add_argument("--quantity")
    parser.add_argument("--target-notional-usdt")
    parser.add_argument("--max-notional")
    parser.add_argument("--leverage")
    parser.add_argument("--max-attempts", type=int)
    parser.add_argument("--protection-mode")
    parser.add_argument("--review-requirement")
    args = parser.parse_args()
    with redirect_stdout(sys.stderr):
        payload = asyncio.run(_build_gate_evidence(args))
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if payload["status"] == "clear_for_next_attempt_preflight" else 2


if __name__ == "__main__":
    raise SystemExit(main())
