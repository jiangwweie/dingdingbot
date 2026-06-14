#!/usr/bin/env python3
"""Collect minimal read-only live facts for StrategyGroup readiness.

Only signed Binance USD-M Futures GET endpoints are used. The collector never
submits, cancels, replaces, or transfers anything and never prints API secrets.
"""

from __future__ import annotations

import argparse
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
DEFAULT_HANDOFF_DIR = PROJECT_ROOT / "docs/current/strategy-group-handoffs"
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


def _handoff_symbols(handoff_dir: Path) -> list[str]:
    symbols: set[str] = set()
    for path in sorted(handoff_dir.expanduser().glob("*/handoff.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for symbol in data.get("supported_symbols") or []:
            symbols.add(str(symbol))
    return sorted(symbols)


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
    return {
        "status": "fresh",
        "can_trade": bool(payload.get("canTrade")),
        "fee_tier": payload.get("feeTier"),
        "total_wallet_balance_present": payload.get("totalWalletBalance") is not None,
        "available_balance_present": payload.get("availableBalance") is not None,
        "assets_count": len(payload.get("assets") or []),
    }


def collect_live_facts(
    *,
    handoff_dir: Path,
    env_file: Path | None,
    base_url: str = DEFAULT_BASE_URL,
    timeout_seconds: float = 12,
    urlopen: UrlOpen = urllib.request.urlopen,
) -> dict[str, Any]:
    symbols = _handoff_symbols(handoff_dir)
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
    return {
        "scope": "strategy_group_live_facts_input",
        "status": "ready" if not errors else "partial",
        "source": "binance_usdm_futures_readonly_get_endpoints",
        "supported_symbol_count": len(symbols),
        "exchange_rules": exchange_rules,
        "account": account,
        "active_position": position,
        "open_orders": open_orders,
        "protection": {"status": "missing", "reason": "requires_candidate_specific_protection_plan"},
        "budget": {"status": "missing", "reason": "requires_runtime_budget_or_budget_authorization_read_model"},
        "next_attempt_gate": {"status": "missing", "reason": "requires_runtime_next_attempt_gate_packet"},
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
    parser.add_argument("--handoff-dir", default=str(DEFAULT_HANDOFF_DIR))
    parser.add_argument("--env-file", default=".env.local")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--output-json", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    packet = collect_live_facts(
        handoff_dir=Path(args.handoff_dir),
        env_file=Path(args.env_file).expanduser() if args.env_file else None,
        base_url=args.base_url,
    )
    output_path = Path(args.output_json).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if packet["exchange_rules"]["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
