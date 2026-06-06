#!/usr/bin/env python3
"""Secret-safe Binance credential preflight for bounded Owner actions.

Default behavior is DRY-RUN. Set RUN_EXCHANGE_CREDENTIAL_PREFLIGHT=true to
perform read-only Binance checks. The script never places, cancels, replaces,
flattens, or retries orders, and it never prints credential values or raw
exchange error text.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.application.exchange_credential_preflight import run_exchange_credential_preflight
from src.infrastructure.exchange_gateway import ExchangeGateway


RUN_ENV = "RUN_EXCHANGE_CREDENTIAL_PREFLIGHT"
DEFAULT_SYMBOL = "SOL/USDT:USDT"


def _bool_env(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _safe_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


async def main() -> int:
    plan = {
        "mode": "run" if _bool_env(os.getenv(RUN_ENV)) else "dry_run",
        "path": "Exchange credentials -> Binance restrictions -> USDT-M facts -> SOL scoped reads",
        "required_env": {
            "TRADING_ENV": "live",
            "EXCHANGE_TESTNET": "false",
            "EXCHANGE_NAME": "binance",
            "EXCHANGE_API_KEY": "set",
            "EXCHANGE_API_SECRET": "set",
            "RUNTIME_CONTROL_API_ENABLED": "false",
            "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED": "false",
        },
        "safety": {
            "places_order": False,
            "cancels_order": False,
            "replaces_order": False,
            "flattens_position": False,
            "retries_protection": False,
            "prints_secrets": False,
        },
    }
    print(_safe_json(plan))
    run = _bool_env(os.getenv(RUN_ENV))
    if not run:
        print()
        print("DRY RUN - no exchange reads performed.")
        print(f"Set {RUN_ENV}=true only on the server credential-preflight path.")
    print(
        _safe_json(
            await run_exchange_credential_preflight(
                env=os.environ,
                gateway_factory=ExchangeGateway,
                symbol=(os.getenv("EXCHANGE_CREDENTIAL_PREFLIGHT_SYMBOL") or DEFAULT_SYMBOL).strip(),
                run=run,
            )
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
