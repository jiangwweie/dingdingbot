#!/usr/bin/env python3
"""Reset only the BNB strategy-trial testnet daily trade counter.

This script refuses live mode, non-testnet exchange mode, missing profile, and
the broad runtime:default daily-risk scope. It does not place orders, create
execution intents, or grant execution permission.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except Exception:
        return
    load_dotenv(REPO_ROOT / ".env")
    load_dotenv(REPO_ROOT / ".env.local", override=True)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default=os.getenv("RUNTIME_PROFILE"))
    parser.add_argument("--symbol", default="BNB/USDT:USDT")
    parser.add_argument("--carrier-id", default="MI-001-BNB-LONG")
    parser.add_argument(
        "--stats-date",
        default=datetime.now(timezone.utc).date().isoformat(),
        help="UTC risk date to reset, default: today",
    )
    return parser.parse_args()


async def _main() -> int:
    _load_env()
    args = _parse_args()

    from src.application.testnet_daily_gate_reset import (
        DailyGateResetRequest,
        build_bnb_testnet_daily_gate_reset_plan,
    )
    from src.infrastructure.pg_testnet_daily_gate_reset import (
        PgTestnetDailyGateResetRepository,
    )

    request = DailyGateResetRequest(
        profile_name=args.profile,
        trading_env=os.getenv("TRADING_ENV"),
        exchange_testnet=(os.getenv("EXCHANGE_TESTNET", "").strip().lower() in {"1", "true", "yes", "on"}),
        symbol=args.symbol,
        carrier_id=args.carrier_id,
        stats_date=datetime.fromisoformat(args.stats_date).date(),
    )
    plan = build_bnb_testnet_daily_gate_reset_plan(request)
    result = await PgTestnetDailyGateResetRepository().reset_trade_count(plan)
    print(
        json.dumps(
            {
                "status": "completed",
                "scope_classification": plan.scope_classification,
                "scope_key": result.scope_key,
                "stats_date": result.stats_date,
                "profile_name": result.profile_name,
                "symbol": result.symbol,
                "carrier_id": result.carrier_id,
                "row_found": result.row_found,
                "trade_count_before": result.trade_count_before,
                "trade_count_after": result.trade_count_after,
                "realized_pnl_before": str(result.realized_pnl_before)
                if result.realized_pnl_before is not None
                else None,
                "realized_pnl_after": str(result.realized_pnl_after)
                if result.realized_pnl_after is not None
                else None,
                "live_ready": result.live_ready,
                "execution_permission_granted": result.execution_permission_granted,
                "order_permission_granted": result.order_permission_granted,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
