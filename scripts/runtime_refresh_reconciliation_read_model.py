#!/usr/bin/env python3
"""Refresh a symbol-level reconciliation read model for runtime submit facts.

The script reads local PG projections and exchange read-only position/order
facts, then persists a report-only reconciliation read model. It never places,
cancels, amends, or closes orders.
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

from src.application.periodic_reconciliation import _to_persistence_records
from src.application.reconciliation import ReconciliationService
from src.infrastructure.exchange_gateway import ExchangeGateway
from src.infrastructure.pg_order_repository import PgOrderRepository
from src.infrastructure.pg_position_repository import PgPositionRepository
from src.infrastructure.pg_reconciliation_read_model_repository import (
    PgReconciliationReadModelRepository,
)


def _parse_bool_env(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _json_value(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if hasattr(value, "__dict__"):
        return {
            str(key): _json_value(item)
            for key, item in value.__dict__.items()
            if not str(key).startswith("_")
        }
    return value


def _summarize_result(result: Any, *, persisted: bool) -> dict[str, Any]:
    mismatches = list(getattr(result, "mismatches", []) or [])
    return {
        "symbol": getattr(result, "symbol", None),
        "checked_at_ms": getattr(result, "checked_at", None),
        "is_consistent": bool(getattr(result, "is_consistent", False)),
        "severe_count": int(getattr(result, "severe_count", 0) or 0),
        "warning_count": int(getattr(result, "warning_count", 0) or 0),
        "mismatch_count": len(mismatches),
        "mismatches": [_json_value(item) for item in mismatches],
        "persisted": persisted,
    }


async def _refresh_symbol(symbol: str, *, persist: bool) -> dict[str, Any]:
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
    try:
        service = ReconciliationService(
            gateway=gateway,
            position_mgr=PgPositionRepository(),
            order_repository=PgOrderRepository(),
        )
        result = await service.build_read_model(symbol)
        if persist:
            repository = PgReconciliationReadModelRepository()
            await repository.initialize()
            report, mismatches = _to_persistence_records(result)
            await repository.save_report(report, mismatches)
        return _summarize_result(result, persisted=persist)
    finally:
        await gateway.close()


async def _amain(args: argparse.Namespace) -> int:
    symbols = [item.strip() for item in args.symbol if item.strip()]
    if not symbols:
        raise RuntimeError("at least one --symbol is required")

    results = []
    for symbol in symbols:
        results.append(await _refresh_symbol(symbol, persist=args.persist))

    payload = {
        "scope": "runtime_reconciliation_read_model_refresh",
        "status": (
            "recorded" if args.persist else "dry_run_exchange_read_completed"
        ),
        "results": results,
        "safety_invariants": {
            "exchange_read_only": True,
            "exchange_write_called": False,
            "order_created": False,
            "order_cancelled": False,
            "order_lifecycle_called": False,
            "execution_intent_created": False,
            "runtime_state_mutated": False,
            "withdrawal_or_transfer_created": False,
            "pg_reconciliation_read_model_written": bool(args.persist),
        },
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    print(text)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresh runtime reconciliation read model facts.",
    )
    parser.add_argument(
        "--symbol",
        action="append",
        required=True,
        help="Runtime symbol to reconcile, for example AVAX/USDT:USDT.",
    )
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Persist the report-only read model to PG.",
    )
    args = parser.parse_args()
    return asyncio.run(_amain(args))


if __name__ == "__main__":
    raise SystemExit(main())
