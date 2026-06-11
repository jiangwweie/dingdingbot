#!/usr/bin/env python3
"""Build a non-executing Owner packet for runtime reduce-only close review."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import time
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


async def _build_packet(args: argparse.Namespace) -> dict[str, Any]:
    _load_env_file(args.env_file)

    from src.application.reconciliation import ReconciliationService
    from src.application.runtime_position_exit_plan_service import (
        RuntimePositionExitPlanService,
    )
    from src.domain.runtime_reduce_only_close_authorization import (
        build_runtime_reduce_only_close_owner_packet,
    )
    from src.infrastructure.connection_pool import close_all_connections
    from src.infrastructure.exchange_gateway import ExchangeGateway
    from src.infrastructure.pg_order_repository import PgOrderRepository
    from src.infrastructure.pg_position_repository import PgPositionRepository
    from src.infrastructure.pg_strategy_runtime_repository import (
        PgStrategyRuntimeRepository,
    )

    runtime_repository = PgStrategyRuntimeRepository()
    position_repository = PgPositionRepository()
    order_repository = PgOrderRepository()
    await runtime_repository.initialize()
    await position_repository.initialize()
    await order_repository.initialize()

    gateway = None
    if not args.skip_exchange:
        api_key = os.environ.get("EXCHANGE_API_KEY", "").strip()
        api_secret = os.environ.get("EXCHANGE_API_SECRET", "").strip()
        if not api_key or not api_secret:
            raise RuntimeError(
                "EXCHANGE_API_KEY and EXCHANGE_API_SECRET are required unless "
                "--skip-exchange is set"
            )
        gateway = ExchangeGateway(
            os.environ.get("EXCHANGE_NAME", "binance"),
            api_key,
            api_secret,
            testnet=_parse_bool_env(os.environ.get("EXCHANGE_TESTNET")),
        )

    reconciliation_service = None
    if not args.skip_reconciliation and gateway is not None:
        reconciliation_service = ReconciliationService(
            gateway=gateway,
            position_mgr=position_repository,
            order_repository=order_repository,
        )

    try:
        exit_plan_service = RuntimePositionExitPlanService(
            runtime_repository=runtime_repository,
            position_repository=position_repository,
            order_repository=order_repository,
            exchange_gateway=gateway,
            reconciliation_service=reconciliation_service,
        )
        exit_plan = await exit_plan_service.build_exit_plan(
            runtime_instance_id=args.runtime_instance_id,
        )
        packet = build_runtime_reduce_only_close_owner_packet(
            exit_plan=exit_plan,
            now_ms=int(time.time() * 1000),
        )
        return {
            "scope": "runtime_reduce_only_close_owner_packet",
            "status": packet.status.value,
            "packet": _json_value(packet),
            "source_exit_plan": _json_value(exit_plan),
            "safety_invariants": {
                "packet_only": True,
                "exchange_read_only": gateway is not None,
                "exchange_write_called": False,
                "order_created": False,
                "order_cancelled": False,
                "order_amended": False,
                "position_closed": False,
                "runtime_state_mutated": False,
                "withdrawal_or_transfer_created": False,
            },
        }
    finally:
        if gateway is not None:
            await gateway.close()
        await close_all_connections()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a non-executing Owner packet for runtime reduce-only close.",
    )
    parser.add_argument("--runtime-instance-id", required=True)
    parser.add_argument(
        "--env-file",
        help="Optional env file to load before reading PG/exchange facts.",
    )
    parser.add_argument(
        "--skip-exchange",
        action="store_true",
        help="Use only local PG facts; packet may block on missing exchange facts.",
    )
    parser.add_argument(
        "--skip-reconciliation",
        action="store_true",
        help="Skip live reconciliation read-model build.",
    )
    args = parser.parse_args()
    payload = asyncio.run(_build_packet(args))
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if payload["status"] == "ready_for_owner_authorization" else 2


if __name__ == "__main__":
    raise SystemExit(main())
