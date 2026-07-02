"""Secret-safe exchange credential preflight helpers."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Callable


CANONICAL_KEY_ENV = "EXCHANGE_API_KEY"
CANONICAL_SECRET_ENV = "EXCHANGE_API_SECRET"
BINANCE_ALIAS_KEY_ENV = "BINANCE_API_KEY"
BINANCE_ALIAS_SECRET_ENV = "BINANCE_SECRET_KEY"
GATEWAY_BINDING_ENV = "RUNTIME_EXCHANGE_SUBMIT_GATEWAY_BINDING_ENABLED"
SUPPORTED_PREFLIGHT_SYMBOLS = frozenset(
    {
        "SOL/USDT:USDT",
        "ETH/USDT:USDT",
    }
)


def exchange_credential_env_status(env: Mapping[str, str]) -> dict[str, Any]:
    """Return env status without exposing secret values."""

    key_present = bool(str(env.get(CANONICAL_KEY_ENV, "")).strip())
    secret_present = bool(str(env.get(CANONICAL_SECRET_ENV, "")).strip())
    alias_key_present = bool(str(env.get(BINANCE_ALIAS_KEY_ENV, "")).strip())
    alias_secret_present = bool(str(env.get(BINANCE_ALIAS_SECRET_ENV, "")).strip())
    return {
        "exchange_name": str(env.get("EXCHANGE_NAME", "binance") or "binance").strip(),
        "trading_env": str(env.get("TRADING_ENV", "")).strip().lower() or "unset",
        "exchange_testnet": str(env.get("EXCHANGE_TESTNET", "")).strip().lower() or "unset",
        "brc_execution_permission_max": str(
            env.get("BRC_EXECUTION_PERMISSION_MAX", "read_only")
        ).strip().lower()
        or "read_only",
        "runtime_control_api_enabled": str(
            env.get("RUNTIME_CONTROL_API_ENABLED", "")
        ).strip().lower()
        or "unset",
        "runtime_test_signal_injection_enabled": str(
            env.get("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "")
        ).strip().lower()
        or "unset",
        "runtime_exchange_submit_gateway_binding_enabled": str(
            env.get(GATEWAY_BINDING_ENV, "")
        ).strip().lower()
        or "unset",
        "exchange_api_key_present": key_present,
        "exchange_api_secret_present": secret_present,
        "binance_alias_key_present": alias_key_present,
        "binance_alias_secret_present": alias_secret_present,
        "canonical_credentials_present": key_present and secret_present,
        "binance_alias_credentials_ignored_by_mainline": alias_key_present
        or alias_secret_present,
    }


def credential_preflight_env_blockers(status: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if status.get("exchange_name") != "binance":
        blockers.append(f"unsupported_exchange:{status.get('exchange_name')}")
    if status.get("trading_env") != "live":
        blockers.append("trading_env_not_live")
    if status.get("exchange_testnet") != "false":
        blockers.append("exchange_testnet_not_false")
    if status.get("brc_execution_permission_max") != "order_allowed":
        blockers.append("brc_execution_permission_max_not_order_allowed")
    if status.get("runtime_control_api_enabled") != "false":
        blockers.append("runtime_control_api_enabled_not_false")
    if status.get("runtime_test_signal_injection_enabled") != "false":
        blockers.append("runtime_test_signal_injection_enabled_not_false")
    if status.get("runtime_exchange_submit_gateway_binding_enabled") not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        blockers.append("runtime_exchange_submit_gateway_binding_not_enabled")
    if not status.get("exchange_api_key_present"):
        blockers.append("exchange_api_key_missing")
    if not status.get("exchange_api_secret_present"):
        blockers.append("exchange_api_secret_missing")
    return blockers


def exchange_error_code_from_message(message: str) -> str | None:
    match = re.search(r'"code"\s*:\s*(-?\d+)', message)
    if match:
        return match.group(1)
    match = re.search(r"\bcode\s*[=:]\s*(-?\d+)", message, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def classify_exchange_credential_error(error: BaseException | str) -> dict[str, Any]:
    """Classify credential failures without returning raw exchange text."""

    message = str(error)
    code = exchange_error_code_from_message(message)
    lower = message.lower()
    category = "exchange_credential_or_permission_error"
    if code == "-2008" or "invalid api-key id" in lower or "invalid api key id" in lower:
        category = "invalid_api_key_id"
    elif code == "-1022" or "signature" in lower:
        category = "secret_mismatch_or_invalid_signature"
    elif code == "-2014":
        category = "invalid_api_key_format"
    elif code == "-2015":
        category = "invalid_api_key_ip_or_permissions"
    elif "ip" in lower and "whitelist" in lower:
        category = "ip_whitelist_incompatible"
    elif "futures" in lower and ("permission" in lower or "not enabled" in lower):
        category = "missing_futures_permission"
    elif "testnet" in lower:
        category = "wrong_exchange_environment"
    return {
        "category": category,
        "exchange_error_code": code,
        "error_type": type(error).__name__ if not isinstance(error, str) else "str",
    }


def binance_api_restriction_summary(restrictions: Mapping[str, Any]) -> dict[str, Any]:
    """Sanitize Binance API restriction payload to permission booleans only."""

    reading_enabled = bool(
        restrictions.get("enableReading") or restrictions.get("enable_reading")
    )
    futures_enabled = bool(
        restrictions.get("enableFutures") or restrictions.get("enable_futures")
    )
    withdrawals_enabled = bool(
        restrictions.get("enableWithdrawals")
        or restrictions.get("enable_withdrawals")
        or restrictions.get("enableWithdrawalsSwitch")
    )
    return {
        "reading_enabled": reading_enabled,
        "futures_enabled": futures_enabled,
        "read_only_permission_present": reading_enabled,
        "futures_trade_permission_present": futures_enabled,
        "order_permission_distinguished_from_read_only": True,
        "spot_margin_trading_enabled": bool(
            restrictions.get("enableSpotAndMarginTrading")
            or restrictions.get("enable_spot_and_margin_trading")
        ),
        "withdrawals_enabled": withdrawals_enabled,
        "ip_restricted": bool(
            restrictions.get("ipRestrict") or restrictions.get("ip_restrict")
        ),
    }


async def run_exchange_credential_preflight(
    *,
    env: Mapping[str, str],
    gateway_factory: Callable[..., Any],
    symbol: str = "SOL/USDT:USDT",
    run: bool = False,
) -> dict[str, Any]:
    """Run a secret-safe credential preflight.

    ``run=False`` is a dry-run plan. ``run=True`` may perform read-only
    exchange requests through the provided gateway factory. The returned
    payload contains only booleans, counts, sanitized categories, and exchange
    error codes.
    """

    env_status = exchange_credential_env_status(env)
    safety = {
        "places_order": False,
        "cancels_order": False,
        "replaces_order": False,
        "flattens_position": False,
        "retries_protection": False,
        "prints_secrets": False,
    }
    result: dict[str, Any] = {
        "mode": "run" if run else "dry_run",
        "result": "dry_run" if not run else "ready_to_run",
        "path": "Exchange credentials -> Binance restrictions -> USDT-M facts -> scoped reads",
        "symbol": symbol,
        "env_status": env_status,
        "env_blockers": credential_preflight_env_blockers(env_status),
        "safety": safety,
        "checks": [],
    }
    if not run:
        return result
    if symbol not in SUPPORTED_PREFLIGHT_SYMBOLS:
        result["result"] = "blocked"
        result["hard_blockers"] = ["unsupported_preflight_symbol"]
        return result
    if result["env_blockers"]:
        result["result"] = "blocked"
        result["hard_blockers"] = list(result["env_blockers"])
        return result

    gateway = gateway_factory(
        exchange_name=str(env_status["exchange_name"]),
        api_key=str(env.get(CANONICAL_KEY_ENV, "")).strip(),
        api_secret=str(env.get(CANONICAL_SECRET_ENV, "")).strip(),
        testnet=False,
    )
    checks: list[dict[str, Any]] = result["checks"]
    try:
        await _record_check(checks, "load_usdt_m_futures_markets", lambda: _load_markets(gateway))
        if checks[-1].get("status") != "passed":
            return _block_result_from_check(result, checks[-1])
        await _record_check(checks, "binance_api_restrictions", lambda: _read_restrictions(gateway))
        if checks[-1].get("status") != "passed":
            return _block_result_from_check(result, checks[-1])
        await _record_check(checks, "usdt_m_futures_account_read", lambda: _read_futures_account(gateway))
        if checks[-1].get("status") != "passed":
            return _block_result_from_check(result, checks[-1])
        await _record_check(checks, "scoped_position_read", lambda: _read_positions(gateway, symbol))
        await _record_check(checks, "scoped_open_order_read", lambda: _read_open_orders(gateway, symbol))
        await _record_check(
            checks,
            "scoped_stop_order_read",
            lambda: _read_open_orders(gateway, symbol, params={"stop": True}),
        )
        await _record_check(checks, "scoped_market_metadata_read", lambda: _read_market_info(gateway, symbol))
    finally:
        close = getattr(gateway, "close", None)
        if callable(close):
            maybe = close()
            if hasattr(maybe, "__await__"):
                await maybe

    failed = [check for check in checks if check.get("status") != "passed"]
    withdrawal_enabled = any(
        check.get("permissions", {}).get("withdrawals_enabled") is True
        for check in checks
    )
    if withdrawal_enabled:
        result["result"] = "blocked"
        result["hard_blockers"] = ["withdraw_permission_enabled"]
    elif failed:
        result["result"] = "blocked"
        result["hard_blockers"] = [_check_blocker(check) for check in failed]
    else:
        result["result"] = "passed"
        result["hard_blockers"] = []
    return result


def _check_blocker(check: Mapping[str, Any]) -> str:
    return f"{check['name']}:{check.get('error', {}).get('category', 'failed')}"


def _block_result_from_check(
    result: dict[str, Any],
    check: Mapping[str, Any],
) -> dict[str, Any]:
    result["result"] = "blocked"
    result["hard_blockers"] = [_check_blocker(check)]
    return result


async def _record_check(
    checks: list[dict[str, Any]],
    name: str,
    action: Callable[[], Any],
) -> None:
    try:
        payload = action()
        if hasattr(payload, "__await__"):
            payload = await payload
    except Exception as exc:
        payload = {
            "status": "blocked",
            "error": classify_exchange_credential_error(exc),
        }
    checks.append({"name": name, **payload})


async def _load_markets(gateway: Any) -> dict[str, Any]:
    await gateway.initialize()
    return {
        "status": "passed",
        "market_count": len(getattr(getattr(gateway, "rest_exchange", None), "symbols", []) or []),
    }


async def _read_restrictions(gateway: Any) -> dict[str, Any]:
    restrictions = await gateway.rest_exchange.sapi_get_account_apirestrictions()
    return {
        "status": "passed",
        "permissions": binance_api_restriction_summary(restrictions or {}),
    }


async def _read_futures_account(gateway: Any) -> dict[str, Any]:
    balance = await gateway.rest_exchange.fetch_balance({"type": "future"})
    total = balance.get("total") or {}
    return {
        "status": "passed",
        "asset_count": len(total) if isinstance(total, dict) else 0,
    }


async def _read_positions(gateway: Any, symbol: str) -> dict[str, Any]:
    positions = await gateway.fetch_positions(symbol=symbol)
    return {
        "status": "passed",
        "active_position_count": len(positions),
    }


async def _read_open_orders(
    gateway: Any,
    symbol: str,
    *,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    orders = await gateway.fetch_open_orders(symbol, params=params)
    return {
        "status": "passed",
        "open_order_count": len(orders),
    }


async def _read_market_info(gateway: Any, symbol: str) -> dict[str, Any]:
    info = await gateway.get_market_info(symbol)
    return {
        "status": "passed",
        "market": {
            "min_quantity": str(info.get("min_quantity")),
            "step_size": str(info.get("step_size")),
            "min_notional": str(info.get("min_notional")),
            "price_precision": info.get("price_precision"),
        },
    }
