#!/usr/bin/env python3
"""
Seed the Sim-1 ETH runtime profile into SQLite.

This script writes non-secret runtime business config only. Secrets remain in
.env / shell environment variables.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.infrastructure.runtime_profile_repository import RuntimeProfileRepository
from src.infrastructure.connection_pool import close_all_connections


SIM1_ETH_RUNTIME_PROFILE = {
    "market": {
        "primary_symbol": "ETH/USDT:USDT",
        "primary_timeframe": "1h",
        "mtf_timeframe": "4h",
        "warmup_history_bars": 100,
        "asset_polling_interval": 60,
    },
    "strategy": {
        "allowed_directions": ["LONG"],
        "trigger": {
            "type": "pinbar",
            "enabled": True,
            "params": {
                "min_wick_ratio": "0.6",
                "max_body_ratio": "0.3",
                "body_position_tolerance": "0.1",
            },
        },
        "filters": [
            {
                "type": "ema",
                "enabled": True,
                "params": {
                    "period": 50,
                    "min_distance_pct": "0.005",
                },
            },
            {
                "type": "mtf",
                "enabled": True,
                "params": {
                    "source_timeframe": "4h",
                    "ema_period": 60,
                },
            },
            {
                "type": "atr",
                "enabled": False,
                "params": {},
            },
        ],
        "atr_enabled": False,
    },
    "risk": {
        "max_loss_percent": "0.01",
        "max_leverage": 20,
        "max_total_exposure": "1.0",
        "daily_max_trades": 10,
        "daily_max_loss_percent": "0.10",
    },
    "execution": {
        "tp_levels": 2,
        "tp_ratios": ["0.5", "0.5"],
        "tp_targets": ["1.0", "3.5"],
        "initial_stop_loss_rr": "-1.0",
        "breakeven_enabled": False,
        "trailing_stop_enabled": False,
        "oco_enabled": True,
    },
}


async def main() -> None:
    db_path = os.getenv("CONFIG_DB_PATH", "data/v3_dev.db")
    repo = RuntimeProfileRepository(db_path=db_path)
    try:
        await repo.initialize()
        profile = await repo.upsert_profile(
            "sim1_eth_runtime",
            SIM1_ETH_RUNTIME_PROFILE,
            description="Sim-1 ETH 1h LONG-only frozen runtime profile",
            is_active=True,
            is_readonly=True,
            allow_readonly_update=True,
        )
    finally:
        await repo.close()
        await close_all_connections()

    print("✅ sim1_eth_runtime profile seeded")
    print(f"   db_path={db_path}")
    print(f"   version={profile.version}")
    print(f"   updated_at={profile.updated_at}")


if __name__ == "__main__":
    asyncio.run(main())
