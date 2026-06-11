#!/usr/bin/env python3
"""Create a closed lifecycle review from resolved runtime trade facts.

Default mode is dry-run. With ``--apply`` this script appends one
``brc_live_lifecycle_reviews`` record only. It does not submit, cancel, amend,
or close exchange orders and does not mutate runtime budget.
"""

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

from src.application.reconciliation import ReconciliationService
from src.application.runtime_closed_trade_lifecycle_review_service import (
    RuntimeClosedTradeLifecycleReviewService,
)
from src.infrastructure.connection_pool import close_all_connections
from src.infrastructure.exchange_gateway import ExchangeGateway
from src.infrastructure.pg_live_lifecycle_review_repository import (
    PgLiveLifecycleReviewRepository,
)
from src.infrastructure.pg_order_repository import PgOrderRepository
from src.infrastructure.pg_position_repository import PgPositionRepository
from src.infrastructure.pg_strategy_runtime_repository import PgStrategyRuntimeRepository


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
        if key and key not in os.environ:
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


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    _load_env_file(args.env_file)
    runtime_repository = PgStrategyRuntimeRepository()
    order_repository = PgOrderRepository()
    position_repository = PgPositionRepository()
    review_repository = PgLiveLifecycleReviewRepository()
    await runtime_repository.initialize()
    await order_repository.initialize()
    await position_repository.initialize()
    await review_repository.initialize()

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
        service = RuntimeClosedTradeLifecycleReviewService(
            runtime_repository=runtime_repository,
            order_repository=order_repository,
            position_repository=position_repository,
            live_lifecycle_review_repository=review_repository,
            reconciliation_service=reconciliation_service,
        )
        result = await service.create_closed_trade_review(
            runtime_instance_id=args.runtime_instance_id,
            entry_order_id=args.entry_order_id,
            exit_order_id=args.exit_order_id,
            authorization_id=args.authorization_id,
            review_decision=args.review_decision,
            apply=args.apply,
        )
        return {
            "scope": "runtime_closed_trade_lifecycle_review",
            "status": result.status,
            "result": _json_value(result),
            "safety_invariants": {
                "exchange_read_only": gateway is not None,
                "exchange_write_called": False,
                "order_created": False,
                "order_cancelled": False,
                "order_amended": False,
                "position_closed": False,
                "runtime_budget_mutated": False,
                "execution_intent_created": False,
                "withdrawal_or_transfer_created": False,
                "live_lifecycle_review_written": result.live_lifecycle_review_written,
            },
        }
    finally:
        if gateway is not None:
            await gateway.close()
        await close_all_connections()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a runtime closed lifecycle review record.",
    )
    parser.add_argument("--runtime-instance-id", required=True)
    parser.add_argument("--entry-order-id", required=True)
    parser.add_argument("--exit-order-id", required=True)
    parser.add_argument("--authorization-id")
    parser.add_argument(
        "--review-decision",
        choices=["auto", "promote", "revise", "park"],
        default="auto",
    )
    parser.add_argument(
        "--env-file",
        help="Optional env file to load before reading PG/exchange facts.",
    )
    parser.add_argument(
        "--skip-exchange",
        action="store_true",
        help="Use only local PG facts; reconciliation will be unavailable unless skipped.",
    )
    parser.add_argument(
        "--skip-reconciliation",
        action="store_true",
        help="Skip live reconciliation; review creation will block on missing reconciliation.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Append the closed review record to PG.",
    )
    args = parser.parse_args()
    payload = asyncio.run(_run(args))
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if payload["status"] != "blocked" else 2


if __name__ == "__main__":
    raise SystemExit(main())
