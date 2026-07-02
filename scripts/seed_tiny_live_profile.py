#!/usr/bin/env python3
"""
Seed the tiny_live_50u_eth runtime profile into PG.

This script is DRY-RUN by default. It prints the profile payload and
SQL statements without writing anything to the database.

To apply for real (after Owner approval):
    APPLY=true python3 scripts/seed_tiny_live_profile.py

Requires:
    PG_DATABASE_URL set in environment or .env.local
"""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


TINY_LIVE_PROFILE = {
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
        "max_leverage": 1,
        "max_total_exposure": "25.0",
        "daily_max_trades": 1,
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


PROFILE_NAME = "tiny_live_50u_eth"
DESCRIPTION = "50U engineering tiny-live rehearsal — ETH LONG-only, 1x leverage, 1 trade/day max"


def print_profile_summary():
    print("=" * 60)
    print(f"Profile: {PROFILE_NAME}")
    print(f"Description: {DESCRIPTION}")
    print("=" * 60)
    print()
    print("Market:")
    print(f"  symbol:     {TINY_LIVE_PROFILE['market']['primary_symbol']}")
    print(f"  timeframe:  {TINY_LIVE_PROFILE['market']['primary_timeframe']}")
    print(f"  mtf:        {TINY_LIVE_PROFILE['market']['mtf_timeframe']}")
    print()
    print("Strategy:")
    print(f"  directions: {TINY_LIVE_PROFILE['strategy']['allowed_directions']}")
    print(f"  trigger:    {TINY_LIVE_PROFILE['strategy']['trigger']['type']}")
    print()
    print("Risk:")
    print(f"  max_leverage:           {TINY_LIVE_PROFILE['risk']['max_leverage']}x")
    print(f"  max_loss_percent:       {TINY_LIVE_PROFILE['risk']['max_loss_percent']} (per trade)")
    print(f"  max_total_exposure:     {TINY_LIVE_PROFILE['risk']['max_total_exposure']} USDT")
    print(f"  daily_max_trades:       {TINY_LIVE_PROFILE['risk']['daily_max_trades']}")
    print(f"  daily_max_loss_percent: {TINY_LIVE_PROFILE['risk']['daily_max_loss_percent']}")
    print()
    print("Execution:")
    print(f"  tp_levels:  {TINY_LIVE_PROFILE['execution']['tp_levels']}")
    print(f"  tp_targets: {TINY_LIVE_PROFILE['execution']['tp_targets']}")
    print(f"  sl_rr:      {TINY_LIVE_PROFILE['execution']['initial_stop_loss_rr']}")
    print()


def print_dry_run_sql():
    payload_json = json.dumps(TINY_LIVE_PROFILE, indent=2)
    print("DRY RUN — SQL that would be executed:")
    print("-" * 60)
    print(f"""
INSERT INTO runtime_profiles (name, description, profile_payload, is_active, is_readonly, version)
VALUES (
    '{PROFILE_NAME}',
    '{DESCRIPTION}',
    '{payload_json}'::jsonb,
    true,
    true,
    1
)
ON CONFLICT (name) DO UPDATE SET
    description = EXCLUDED.description,
    profile_payload = EXCLUDED.profile_payload,
    is_active = EXCLUDED.is_active,
    is_readonly = EXCLUDED.is_readonly,
    version = runtime_profiles.version + 1,
    updated_at = NOW();
""")
    print("-" * 60)


async def apply_profile():
    from src.infrastructure.runtime_profile_repository import RuntimeProfileRepository
    from src.infrastructure.connection_pool import close_all_connections

    db_path = os.getenv("CONFIG_DB_PATH", "data/v3_dev.db")
    repo = RuntimeProfileRepository(db_path=db_path)
    try:
        await repo.initialize()
        profile = await repo.upsert_profile(
            PROFILE_NAME,
            TINY_LIVE_PROFILE,
            description=DESCRIPTION,
            is_active=True,
            is_readonly=True,
        )
    finally:
        await repo.close()
        await close_all_connections()

    print(f"Profile '{PROFILE_NAME}' seeded successfully")
    print(f"  version={profile.version}")
    print(f"  updated_at={profile.updated_at}")


async def main():
    apply = os.getenv("APPLY", "").strip().lower() in {"1", "true", "yes"}

    print_profile_summary()

    if apply:
        pg_url = os.getenv("PG_DATABASE_URL")
        if not pg_url:
            print("ERROR: PG_DATABASE_URL required for APPLY=true")
            sys.exit(1)
        print(f"PG: {pg_url.split('@')[-1] if '@' in pg_url else '(redacted)'}")
        print()
        print("Applying profile to database...")
        await apply_profile()
    else:
        print_dry_run_sql()
        print()
        print("To apply for real: APPLY=true python3 scripts/seed_tiny_live_profile.py")
        print("Requires PG_DATABASE_URL in environment.")


if __name__ == "__main__":
    asyncio.run(main())
