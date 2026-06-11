#!/usr/bin/env python3
"""Recover local runtime close projection from read-only exchange trade facts."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

def _parse_bool_env(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


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
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


async def _recover(args: argparse.Namespace) -> dict[str, Any]:
    _load_env_file(args.env_file)

    from src.application.order_lifecycle_service import OrderLifecycleService
    from src.application.position_projection_service import PositionProjectionService
    from src.application.runtime_exchange_close_projection_recovery_service import (
        RuntimeExchangeCloseProjectionRecoveryService,
    )
    from src.domain.runtime_exchange_close_projection_recovery import (
        RuntimeExchangeCloseProjectionRecoveryRequest,
    )
    from src.infrastructure.connection_pool import close_all_connections
    from src.infrastructure.exchange_gateway import ExchangeGateway
    from src.infrastructure.pg_order_repository import PgOrderRepository
    from src.infrastructure.pg_position_repository import PgPositionRepository

    api_key = os.environ.get("EXCHANGE_API_KEY", "").strip()
    api_secret = os.environ.get("EXCHANGE_API_SECRET", "").strip()
    if not api_key or not api_secret:
        raise RuntimeError("EXCHANGE_API_KEY and EXCHANGE_API_SECRET are required")

    gateway = ExchangeGateway(
        os.environ.get("EXCHANGE_NAME", "binance"),
        api_key,
        api_secret,
        testnet=_parse_bool_env(os.environ.get("EXCHANGE_TESTNET")),
    )
    order_repository = PgOrderRepository()
    position_repository = PgPositionRepository()
    lifecycle = OrderLifecycleService(order_repository)
    projection = PositionProjectionService(position_repository)
    service = RuntimeExchangeCloseProjectionRecoveryService(
        exchange_trade_source=gateway,
        order_repository=order_repository,
        position_repository=position_repository,
        order_lifecycle=lifecycle,
        position_projection_service=projection,
    )
    try:
        await gateway.initialize()
        await order_repository.initialize()
        await position_repository.initialize()
        request = RuntimeExchangeCloseProjectionRecoveryRequest(
            symbol=args.symbol,
            exit_local_order_id=args.exit_local_order_id,
            exit_exchange_order_id=args.exit_exchange_order_id,
            exit_trade_id=args.exit_trade_id,
            apply=bool(args.apply),
            operator_reason=args.operator_reason,
        )
        result = await service.recover(request)
        return {
            "scope": "runtime_exchange_close_projection_recovery",
            "status": result.status.value,
            "result": _json_value(result),
            "safety_invariants": {
                "exchange_read_only": True,
                "exchange_write_called": False,
                "order_created": False,
                "order_cancelled_on_exchange": False,
                "order_amended_on_exchange": False,
                "position_closed_on_exchange": False,
                "withdrawal_or_transfer_created": False,
                "local_state_mutated": bool(result.local_state_mutated),
            },
        }
    finally:
        await gateway.close()
        await close_all_connections()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Repair local runtime close projection from read-only exchange "
            "trade facts for an already closed position."
        )
    )
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--exit-local-order-id", required=True)
    parser.add_argument("--exit-trade-id", required=True)
    parser.add_argument("--exit-exchange-order-id")
    parser.add_argument(
        "--operator-reason",
        default="runtime_exchange_close_projection_recovery",
    )
    parser.add_argument("--env-file", help="Optional env file to load.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the local PG order/position projection repair.",
    )
    args = parser.parse_args()
    payload = asyncio.run(_recover(args))
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
