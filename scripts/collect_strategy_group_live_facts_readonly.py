#!/usr/bin/env python3
"""Collect minimal read-only live facts for explicit StrategyGroup scope.

Only signed Binance USD-M Futures GET endpoints are used. The collector never
submits, cancels, replaces, or transfers anything and never prints API secrets.
"""

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import json
import os
from pathlib import Path
import shlex
import time
from typing import Any, Callable
from urllib.parse import urlencode
import urllib.error
import urllib.request


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = "https://fapi.binance.com"
READ_ONLY_ENDPOINTS = {
    "exchange_info": ("GET", "/fapi/v1/exchangeInfo", False),
    "account": ("GET", "/fapi/v2/account", True),
    "position_risk": ("GET", "/fapi/v2/positionRisk", True),
    "open_orders": ("GET", "/fapi/v1/openOrders", True),
}
UrlOpen = Callable[..., Any]


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        try:
            parts = shlex.split(raw_value, comments=False, posix=True)
        except ValueError:
            parts = []
        value = parts[0] if len(parts) == 1 else raw_value.strip().strip("\"'")
        values[key] = value
    return values


def _env_value(names: tuple[str, ...], *, env_file: Path | None) -> str | None:
    for name in names:
        if os.environ.get(name):
            return os.environ[name]
    values = _parse_env_file(env_file) if env_file else {}
    for name in names:
        if values.get(name):
            return values[name]
    return None


def _request_json(
    *,
    base_url: str,
    path: str,
    api_key: str | None = None,
    api_secret: str | None = None,
    signed: bool = False,
    timeout_seconds: float = 12,
    urlopen: UrlOpen = urllib.request.urlopen,
) -> dict[str, Any]:
    params: dict[str, Any] = {}
    headers: dict[str, str] = {}
    if signed:
        if not api_key or not api_secret:
            raise RuntimeError("exchange_api_key_or_secret_missing")
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = 5000
        query = urlencode(params)
        signature = hmac.new(api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
        params["signature"] = signature
        headers["X-MBX-APIKEY"] = api_key
    url = f"{base_url}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"http_{exc.code}:{body[:160]}") from exc
    if not isinstance(payload, (dict, list)):
        raise RuntimeError("unexpected_json_root")
    return {"payload": payload}


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _exchange_rules(exchange_info: dict[str, Any], symbols: list[str]) -> dict[str, Any]:
    payload = exchange_info.get("payload")
    if not isinstance(payload, dict):
        return {"status": "missing", "symbols": {}}
    by_symbol = {item.get("symbol"): item for item in payload.get("symbols") or [] if isinstance(item, dict)}
    rows: dict[str, Any] = {}
    for symbol in symbols:
        item = by_symbol.get(symbol)
        if not item:
            rows[symbol] = {"status": "missing"}
            continue
        filters = {entry.get("filterType"): entry for entry in item.get("filters") or [] if isinstance(entry, dict)}
        lot = filters.get("LOT_SIZE") or {}
        price = filters.get("PRICE_FILTER") or {}
        notional = filters.get("MIN_NOTIONAL") or filters.get("NOTIONAL") or {}
        rows[symbol] = {
            "status": item.get("status") or "unknown",
            "min_notional": notional.get("notional") or notional.get("minNotional"),
            "qty_step": lot.get("stepSize"),
            "price_tick": price.get("tickSize"),
        }
    return {"status": "ready", "symbols": rows}


def _position_summary(position_risk: dict[str, Any], symbols: list[str]) -> dict[str, Any]:
    payload = position_risk.get("payload")
    if not isinstance(payload, list):
        return {"status": "missing", "active_count": None, "active_symbols": []}
    active: list[str] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or "")
        if symbol not in symbols:
            continue
        amount = str(item.get("positionAmt") or "0")
        try:
            is_active = float(amount) != 0.0
        except ValueError:
            is_active = amount not in {"0", "0.0", "0.000"}
        if is_active:
            active.append(symbol)
    return {
        "status": "no_active_position" if not active else "active_position_present",
        "active_count": len(active),
        "active_symbols": sorted(set(active)),
    }


def _open_order_summary(open_orders: dict[str, Any], symbols: list[str]) -> dict[str, Any]:
    payload = open_orders.get("payload")
    if not isinstance(payload, list):
        return {"status": "missing", "open_order_count": None, "open_order_symbols": []}
    matched = sorted(
        {
            str(item.get("symbol"))
            for item in payload
            if isinstance(item, dict) and str(item.get("symbol")) in set(symbols)
        }
    )
    return {
        "status": "no_open_orders" if not matched else "open_orders_present",
        "open_order_count": len(matched),
        "open_order_symbols": matched,
    }


def _account_summary(account: dict[str, Any]) -> dict[str, Any]:
    payload = account.get("payload")
    if not isinstance(payload, dict):
        return {"status": "missing"}
    available_balance = _decimal(payload.get("availableBalance"))
    return {
        "status": "fresh",
        "exchange_account_trade_permission": bool(payload.get("canTrade")),
        "fee_tier": payload.get("feeTier"),
        "total_wallet_balance_present": payload.get("totalWalletBalance") is not None,
        "available_balance_present": payload.get("availableBalance") is not None,
        "available_balance_positive": (
            available_balance is not None and available_balance > Decimal("0")
        ),
        "assets_count": len(payload.get("assets") or []),
    }


def _budget_state(
    *,
    account_payload: dict[str, Any],
    handoff_summary: dict[str, Any],
) -> dict[str, Any]:
    payload = account_payload.get("payload")
    if not isinstance(payload, dict):
        return {
            "status": "missing",
            "reason": "signed_account_fact_missing",
        }
    if not payload.get("canTrade"):
        return {
            "status": "blocked",
            "reason": "account_cannot_trade",
        }
    available_balance = _decimal(payload.get("availableBalance"))
    max_notional = _decimal(handoff_summary.get("max_notional_requirement_usdt"))
    if available_balance is None or max_notional is None:
        return {
            "status": "missing",
            "reason": "available_balance_or_handoff_notional_missing",
        }
    if available_balance < max_notional:
        return {
            "status": "blocked",
            "reason": "available_balance_below_strategygroup_tiny_notional",
            "max_notional_requirement_usdt": str(max_notional),
        }
    return {
        "status": "available_for_candidate_specific_reservation",
        "reason": "account_available_balance_covers_strategygroup_tiny_notional",
        "max_notional_requirement_usdt": str(max_notional),
        "reservation_created": False,
    }


def _protection_state(handoff_summary: dict[str, Any]) -> dict[str, Any]:
    if not handoff_summary.get("has_candidate_specific_protection_template"):
        return {
            "status": "missing",
            "reason": "candidate_specific_protection_template_missing",
        }
    return {
        "status": "ready_for_candidate_specific_plan",
        "reason": "handoff_risk_defaults_define_sl_and_exit_plan",
        "protection_plan_created": False,
    }


def _next_attempt_gate_state(
    *,
    position: dict[str, Any],
    open_orders: dict[str, Any],
) -> dict[str, Any]:
    if position.get("status") == "active_position_present":
        return {
            "status": "blocked",
            "reason": "active_position_present",
            "active_symbols": list(position.get("active_symbols") or []),
        }
    if open_orders.get("status") == "open_orders_present":
        return {
            "status": "blocked",
            "reason": "open_orders_present",
            "open_order_symbols": list(open_orders.get("open_order_symbols") or []),
        }
    if position.get("status") == "no_active_position" and open_orders.get("status") == "no_open_orders":
        return {
            "status": "ready_for_strategy_signal",
            "reason": "flat_and_no_open_orders_for_selected_strategygroup_symbols",
        }
    return {
        "status": "missing",
        "reason": "position_or_open_order_fact_missing",
    }


def collect_live_facts(
    *,
    symbols: list[str],
    max_notional_requirement_usdt: str | None = None,
    has_candidate_specific_protection_template: bool = False,
    strategy_group_count: int | None = None,
    env_file: Path | None,
    base_url: str = DEFAULT_BASE_URL,
    timeout_seconds: float = 12,
    urlopen: UrlOpen = urllib.request.urlopen,
) -> dict[str, Any]:
    scope = {
        "symbols": sorted({str(symbol).upper() for symbol in symbols if str(symbol).strip()}),
        "strategy_group_count": strategy_group_count,
        "max_notional_requirement_usdt": max_notional_requirement_usdt,
        "has_candidate_specific_protection_template": has_candidate_specific_protection_template,
    }
    symbols = list(scope["symbols"])
    api_key = _env_value(("EXCHANGE_API_KEY", "BINANCE_API_KEY", "binance_exchange_key"), env_file=env_file)
    api_secret = _env_value(("EXCHANGE_API_SECRET", "BINANCE_SECRET_KEY", "binance_exchange_secret"), env_file=env_file)
    payloads: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    for name, (_method, path, signed) in READ_ONLY_ENDPOINTS.items():
        try:
            payloads[name] = _request_json(
                base_url=base_url,
                path=path,
                api_key=api_key,
                api_secret=api_secret,
                signed=signed,
                timeout_seconds=timeout_seconds,
                urlopen=urlopen,
            )
        except Exception as exc:
            errors[name] = f"{type(exc).__name__}:{str(exc)[:220]}"
            payloads[name] = {}
    exchange_rules = _exchange_rules(payloads["exchange_info"], symbols)
    position = _position_summary(payloads["position_risk"], symbols)
    open_orders = _open_order_summary(payloads["open_orders"], symbols)
    account = _account_summary(payloads["account"])
    budget = _budget_state(
        account_payload=payloads["account"],
        handoff_summary=scope,
    )
    protection = _protection_state(scope)
    next_attempt_gate = _next_attempt_gate_state(
        position=position,
        open_orders=open_orders,
    )
    return {
        "scope": "strategy_group_live_facts_input",
        "status": "ready" if not errors else "partial",
        "source": "explicit_scope_binance_usdm_futures_readonly_get_endpoints",
        "source_mode": "explicit_runtime_scope",
        "supported_symbol_count": len(symbols),
        "exchange_rules": exchange_rules,
        "account": account,
        "active_position": position,
        "open_orders": open_orders,
        "protection": protection,
        "budget": budget,
        "next_attempt_gate": next_attempt_gate,
        "collector_errors": errors,
        "safety_invariants": {
            "signed_get_only": True,
            "post_delete_put_used": False,
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "execution_intent_created": False,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
            "secrets_printed": False,
        },
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect StrategyGroup read-only live facts.")
    parser.add_argument(
        "--symbols",
        required=True,
        help="Comma-separated runtime scope symbols. Production callers should derive this from PG.",
    )
    parser.add_argument("--max-notional-requirement-usdt")
    parser.add_argument(
        "--has-candidate-specific-protection-template",
        action="store_true",
    )
    parser.add_argument("--strategy-group-count", type=int)
    parser.add_argument("--env-file", default=".env.local")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    artifact = collect_live_facts(
        symbols=[
            item.strip()
            for item in str(args.symbols).split(",")
            if item.strip()
        ],
        max_notional_requirement_usdt=args.max_notional_requirement_usdt,
        has_candidate_specific_protection_template=bool(
            args.has_candidate_specific_protection_template
        ),
        strategy_group_count=args.strategy_group_count,
        env_file=Path(args.env_file).expanduser() if args.env_file else None,
        base_url=args.base_url,
    )
    print(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if artifact["exchange_rules"]["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
