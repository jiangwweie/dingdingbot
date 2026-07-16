"""Lightweight runtime exchange-gateway construction and safety binding."""

from __future__ import annotations

import os
from typing import Any

from src.domain.runtime_execution_exchange_gateway_readiness import (
    GATEWAY_BINDING_ENABLED_ENV,
    RUNTIME_EXCHANGE_LIFECYCLE_GATEWAY_METHODS,
)


async def bind_runtime_exchange_submit_gateway(
    state_holder: Any,
    *,
    gateway_factory: Any = None,
    lifecycle_readonly: bool = False,
) -> dict[str, Any]:
    """Build the independently gated runtime gateway without API imports."""

    existing = getattr(state_holder, "_runtime_exchange_submit_gateway", None)
    if existing is not None:
        return runtime_exchange_submit_gateway_status(existing)

    blockers = runtime_exchange_submit_gateway_env_blockers()
    if blockers:
        return {"status": "blocked_env", "gateway": None, "blockers": blockers}

    api_key = os.environ.get("EXCHANGE_API_KEY", "").strip()
    api_secret = os.environ.get("EXCHANGE_API_SECRET", "").strip()
    if not api_key or not api_secret:
        return {
            "status": "blocked_credentials_missing",
            "gateway": None,
            "blockers": ["exchange_credentials_missing"],
        }

    exchange_name = os.environ.get("EXCHANGE_NAME", "binance").strip() or "binance"
    if exchange_name.lower() != "binance":
        return {
            "status": "blocked_unsupported_exchange",
            "gateway": None,
            "blockers": [f"unsupported_exchange:{exchange_name}"],
        }

    if gateway_factory is None:
        from src.infrastructure.exchange_gateway import ExchangeGateway

        gateway_factory = ExchangeGateway
    gateway = gateway_factory(
        exchange_name=exchange_name,
        api_key=api_key,
        api_secret=api_secret,
        testnet=False,
    )
    try:
        if lifecycle_readonly:
            lifecycle_initialize = getattr(
                gateway, "initialize_lifecycle_readonly", None
            )
            if not callable(lifecycle_initialize):
                raise RuntimeError(
                    "runtime_gateway_missing_initialize_lifecycle_readonly"
                )
            await lifecycle_initialize()
        else:
            await gateway.initialize()
        permission_check = getattr(gateway, "check_api_key_permissions", None)
        if callable(permission_check):
            await permission_check()
    except Exception as exc:
        close = getattr(gateway, "close", None)
        if callable(close):
            try:
                await close()
            except Exception:
                pass
        error_code = getattr(exc, "error_code", None)
        blockers = [
            f"runtime_exchange_gateway_initialization_failed:{type(exc).__name__}"
        ]
        if error_code:
            blockers.append(
                f"runtime_exchange_gateway_initialization_failed:{error_code}"
            )
        return {
            "status": "blocked_gateway_initialization_failed",
            "gateway": None,
            "blockers": blockers,
            "error_code": error_code,
            "error_type": type(exc).__name__,
        }

    setattr(state_holder, "_runtime_exchange_submit_gateway", gateway)
    return runtime_exchange_submit_gateway_status(gateway)


def runtime_exchange_submit_gateway_env_blockers() -> list[str]:
    expected = {
        "TRADING_ENV": "live",
        "EXCHANGE_TESTNET": "false",
        "BRC_EXECUTION_PERMISSION_MAX": "order_allowed",
        "RUNTIME_CONTROL_API_ENABLED": "false",
        "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED": "false",
        GATEWAY_BINDING_ENABLED_ENV: "true",
    }
    blockers: list[str] = []
    for key, expected_value in expected.items():
        actual = os.environ.get(key, "").strip().lower()
        if actual != expected_value:
            blockers.append(f"{key.lower()}_not_{expected_value}")
    account_id = os.environ.get("BRC_RUNTIME_EXCHANGE_ACCOUNT_ID", "").strip()
    exchange_id = os.environ.get("BRC_RUNTIME_EXCHANGE_ID", "").strip()
    if not account_id:
        blockers.append("brc_runtime_exchange_account_id_missing")
    if not exchange_id:
        blockers.append("brc_runtime_exchange_id_missing")
    elif exchange_id != "binance_usdm":
        blockers.append(f"brc_runtime_exchange_id_unsupported:{exchange_id}")
    return blockers


def runtime_exchange_submit_gateway_status(gateway: Any) -> dict[str, Any]:
    missing = [
        f"runtime_gateway_missing_{name}"
        for name in RUNTIME_EXCHANGE_LIFECYCLE_GATEWAY_METHODS
        if not callable(getattr(gateway, name, None))
    ]
    account_id = os.environ.get("BRC_RUNTIME_EXCHANGE_ACCOUNT_ID", "").strip()
    exchange_id = os.environ.get("BRC_RUNTIME_EXCHANGE_ID", "").strip()
    if not account_id:
        missing.append("brc_runtime_exchange_account_id_missing")
    if not exchange_id:
        missing.append("brc_runtime_exchange_id_missing")
    elif exchange_id != "binance_usdm":
        missing.append(f"brc_runtime_exchange_id_unsupported:{exchange_id}")
    if not missing:
        setattr(gateway, "runtime_account_id", account_id)
        setattr(gateway, "runtime_exchange_id", exchange_id)
    return {
        "status": "ready" if not missing else "blocked_methods_missing",
        "gateway": gateway if not missing else None,
        "blockers": missing,
        "gateway_type": type(gateway).__name__,
        "account_id": account_id,
        "exchange_id": exchange_id,
    }
