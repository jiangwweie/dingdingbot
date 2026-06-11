#!/usr/bin/env python3
"""Recover local runtime submit projection from read-only exchange facts."""

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

from src.application.order_lifecycle_service import OrderLifecycleService
from src.application.position_projection_service import PositionProjectionService
from src.application.runtime_exchange_submit_projection_recovery_service import (
    RuntimeExchangeSubmitProjectionRecoveryRequest,
    RuntimeExchangeSubmitProjectionRecoveryService,
)
from src.infrastructure.connection_pool import close_all_connections
from src.infrastructure.exchange_gateway import ExchangeGateway
from src.infrastructure.pg_order_repository import PgOrderRepository
from src.infrastructure.pg_position_repository import PgPositionRepository


def _parse_bool_env(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _json_value(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "model_dump"):
        return _json_value(value.model_dump(mode="python"))
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


async def _recover(args: argparse.Namespace) -> dict[str, Any]:
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
    service = RuntimeExchangeSubmitProjectionRecoveryService(
        gateway=gateway,
        order_repository=order_repository,
        lifecycle=lifecycle,
        position_projection_service=projection,
    )
    try:
        await order_repository.initialize()
        await position_repository.initialize()
        request = RuntimeExchangeSubmitProjectionRecoveryRequest(
            symbol=args.symbol,
            entry_local_order_id=args.entry_local_order_id,
            entry_exchange_order_id=args.entry_exchange_order_id,
            protection_local_order_id=args.protection_local_order_id,
            protection_exchange_order_id=args.protection_exchange_order_id,
            apply=bool(args.apply),
            operator_reason=args.operator_reason,
        )
        result = await service.recover(request)
        return {
            "scope": "runtime_exchange_submit_projection_recovery",
            "status": result.status.value,
            "result": _json_value(result),
            "safety_invariants": {
                "exchange_read_only": True,
                "exchange_write_called": False,
                "order_created": False,
                "order_cancelled": False,
                "order_amended": False,
                "position_closed": False,
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
            "Repair local runtime order/position projection from read-only "
            "exchange facts for an already accepted submit."
        )
    )
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--entry-local-order-id", required=True)
    parser.add_argument("--entry-exchange-order-id", required=True)
    parser.add_argument("--protection-local-order-id", required=True)
    parser.add_argument("--protection-exchange-order-id", required=True)
    parser.add_argument(
        "--operator-reason",
        default="runtime_exchange_submit_projection_recovery",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the local PG projection repair. Omit for dry-run.",
    )
    args = parser.parse_args()
    payload = asyncio.run(_recover(args))
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
