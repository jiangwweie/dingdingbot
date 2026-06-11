#!/usr/bin/env python3
"""Build a read-only packet that resolves closed-trade review order IDs."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import redirect_stdout
import json
import os
from pathlib import Path
import sys
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


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

    from src.application.runtime_closed_trade_review_facts_service import (
        RuntimeClosedTradeReviewFactsService,
    )
    from src.infrastructure.connection_pool import close_all_connections
    from src.infrastructure.pg_order_repository import PgOrderRepository
    from src.infrastructure.pg_position_repository import PgPositionRepository
    from src.infrastructure.pg_strategy_runtime_repository import (
        PgStrategyRuntimeRepository,
    )

    runtime_repository = PgStrategyRuntimeRepository()
    order_repository = PgOrderRepository()
    position_repository = PgPositionRepository()
    await runtime_repository.initialize()
    await order_repository.initialize()
    await position_repository.initialize()

    try:
        service = RuntimeClosedTradeReviewFactsService(
            runtime_repository=runtime_repository,
            order_repository=order_repository,
            position_repository=position_repository,
        )
        packet = await service.build_packet(
            runtime_instance_id=args.runtime_instance_id,
            order_limit=args.order_limit,
        )
        return {
            "scope": "runtime_closed_trade_review_facts_packet",
            "status": packet.status.value,
            "packet": _json_value(packet),
            "safety_invariants": {
                "packet_only": True,
                "pg_read_only": True,
                "exchange_called": False,
                "exchange_write_called": False,
                "review_record_created": False,
                "order_created": False,
                "order_cancelled": False,
                "order_amended": False,
                "position_closed": False,
                "runtime_state_mutated": False,
                "withdrawal_or_transfer_created": False,
            },
        }
    finally:
        await close_all_connections()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve closed-trade review order IDs for a runtime.",
    )
    parser.add_argument("--runtime-instance-id", required=True)
    parser.add_argument("--env-file", help="Optional env file to load before PG reads.")
    parser.add_argument("--order-limit", type=int, default=100)
    args = parser.parse_args()
    with redirect_stdout(sys.stderr):
        payload = asyncio.run(_build_packet(args))
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if payload["status"] != "blocked" else 2


if __name__ == "__main__":
    raise SystemExit(main())
