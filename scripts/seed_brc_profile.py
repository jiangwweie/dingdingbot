#!/usr/bin/env python3
"""Seed the BRC BTC/ETH testnet runtime profile.

Default behavior is DRY-RUN. It prints the profile payload without writing to
the database.

To apply after Owner authorization:
    APPLY=true python3 scripts/seed_brc_profile.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


PROFILE_NAME = "brc_btc_eth_testnet_runtime"
DESCRIPTION = (
    "Bounded Risk Campaign controlled BTC/ETH Binance testnet runtime rehearsal; "
    "sequential one-symbol exposure, mock campaign PnL only"
)

BRC_PROFILE = {
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
        "daily_max_trades": 20,
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
    "brc": {
        "controlled_playbook_id": "PB-004-BRC-CONTROLLED-TESTNET",
        "symbol_sequence": ["ETH/USDT:USDT", "BTC/USDT:USDT"],
        "max_attempts": 2,
        "max_simultaneous_positions": 1,
        "program_withdrawal_enabled": False,
        "mock_pnl_accounting_only": True,
        "fixed_caps": {
            "ETH/USDT:USDT": {"amount": "0.01", "max_notional": "25"},
            "BTC/USDT:USDT": {"amount": "0.002", "max_notional": "250"},
        },
    },
}


def print_profile_summary() -> None:
    print("=" * 72)
    print(f"Profile: {PROFILE_NAME}")
    print(f"Description: {DESCRIPTION}")
    print("=" * 72)
    print("Market:")
    print(f"  primary_symbol: {BRC_PROFILE['market']['primary_symbol']}")
    print(f"  symbols:        {BRC_PROFILE['market']['symbols']}")
    print("Controls:")
    print("  ETH cap:        0.01 ETH / 25 USDT")
    print("  BTC cap:        0.002 BTC / 250 USDT")
    print("  leverage:       1x")
    print("  daily trades:   20")
    print("  max attempts:   2")
    print("  withdrawal:     disabled in program")
    print("  profile state:  readonly inactive by default")
    print()


def print_dry_run_sql() -> None:
    payload_json = json.dumps(BRC_PROFILE, indent=2)
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
            BRC_PROFILE,
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
        print("Applying BRC profile...")
        await apply_profile()
    else:
        print_dry_run_sql()
        print()
        print("To apply after authorization: APPLY=true python3 scripts/seed_brc_profile.py")


if __name__ == "__main__":
    asyncio.run(main())
