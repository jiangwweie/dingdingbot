#!/usr/bin/env python3
"""
Seed the Phase 5E BTC/ETH testnet runtime profile.

Default behavior is DRY-RUN. It prints the profile payload and SQL-like
summary without writing to the database.

To apply after Owner authorization:
    APPLY=true python3 scripts/seed_phase5e_profile.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


PROFILE_NAME = "phase5e_btc_eth_testnet_runtime"
DESCRIPTION = (
    "Phase 5E controlled BTC/ETH Binance testnet runtime rehearsal; "
    "sequential one-symbol exposure only"
)

PHASE5E_PROFILE = {
    "market": {
        "primary_symbol": "ETH/USDT:USDT",
        "symbols": ["ETH/USDT:USDT", "BTC/USDT:USDT"],
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
        "max_leverage": 1,
        "max_total_exposure": "0.13",
        "daily_max_trades": 10,
        "daily_max_loss_percent": "0.03",
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


def print_profile_summary() -> None:
    print("=" * 72)
    print(f"Profile: {PROFILE_NAME}")
    print(f"Description: {DESCRIPTION}")
    print("=" * 72)
    print()
    print("Market:")
    print(f"  primary_symbol: {PHASE5E_PROFILE['market']['primary_symbol']}")
    print(f"  symbols:        {PHASE5E_PROFILE['market']['symbols']}")
    print(f"  timeframes:     1h, 4h")
    print()
    print("Risk:")
    print("  leverage:       1x")
    print("  daily trades:   10")
    print("  exposure field: max_total_exposure=0.13 balance multiple")
    print("  fixed caps:     enforced by controlled endpoints")
    print()
    print("Controls:")
    print("  ETH cap:        0.01 ETH / 25 USDT")
    print("  BTC cap:        0.002 BTC / 250 USDT")
    print("  BTC blocker:    feasibility still reports cap/min-notional status")
    print("  exposure mode:  sequential, max one active symbol")
    print()


def print_dry_run_sql() -> None:
    payload_json = json.dumps(PHASE5E_PROFILE, indent=2)
    print("DRY RUN - SQL-like statement that would be applied:")
    print("-" * 72)
    print(
        f"""
UPSERT runtime_profiles
  name={PROFILE_NAME}
  description={DESCRIPTION}
  is_active=false
  is_readonly=true
  profile_payload={payload_json}
"""
    )
    print("-" * 72)


async def apply_profile() -> None:
    from src.infrastructure.connection_pool import close_all_connections
    from src.infrastructure.runtime_profile_repository import RuntimeProfileRepository

    repo = RuntimeProfileRepository()
    try:
        await repo.initialize()
        profile = await repo.upsert_profile(
            PROFILE_NAME,
            PHASE5E_PROFILE,
            description=DESCRIPTION,
            is_active=False,
            is_readonly=True,
            allow_readonly_update=True,
        )
    finally:
        await repo.close()
        await close_all_connections()

    print(f"Profile '{PROFILE_NAME}' seeded successfully")
    print(f"  version={profile.version}")
    print(f"  active={profile.is_active}")
    print(f"  readonly={profile.is_readonly}")


async def main() -> None:
    apply = os.getenv("APPLY", "").strip().lower() in {"1", "true", "yes", "on"}
    print_profile_summary()
    if apply:
        print("Applying Phase 5E profile...")
        await apply_profile()
    else:
        print_dry_run_sql()
        print()
        print("To apply after authorization: APPLY=true python3 scripts/seed_phase5e_profile.py")


if __name__ == "__main__":
    asyncio.run(main())
