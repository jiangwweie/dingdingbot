#!/usr/bin/env python3
"""Seed the MI-001 BNB strategy-trial testnet runtime profile.

Default behavior is DRY-RUN. The profile contains only non-secret runtime
business configuration. API keys and testnet/live switches remain in .env.

To apply after Owner authorization:
    APPLY=true python3 scripts/seed_strategy_trial_bnb_profile.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


PROFILE_NAME = "strategy_trial_bnb_testnet_runtime"
DESCRIPTION = (
    "MI-001 BNB owner-confirmed controlled Binance testnet strategy-trial carrier; "
    "single-symbol bounded rehearsal only"
)

BNB_STRATEGY_TRIAL_PROFILE = {
    "market": {
        "primary_symbol": "BNB/USDT:USDT",
        "symbols": ["BNB/USDT:USDT"],
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
        "max_total_exposure": "10",
        "daily_max_trades": 1,
        "daily_max_loss_percent": "0.01",
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
        "controlled_playbook_id": "PB-STRATEGY-TRIAL-MI001-BNB-TESTNET",
        "carrier_id": "MI-001-BNB-LONG",
        "symbol_sequence": ["BNB/USDT:USDT"],
        "max_attempts": 1,
        "max_simultaneous_positions": 1,
        "program_withdrawal_enabled": False,
        "mock_pnl_accounting_only": False,
        "fixed_caps": {
            "BNB/USDT:USDT": {
                "amount": "0.01",
                "max_notional": "20",
                "leverage": 1,
            }
        },
        "non_permissions": {
            "live_ready": False,
            "auto_execution_ready": False,
            "no_arbitrary_symbol": True,
            "no_arbitrary_side": True,
            "no_arbitrary_leverage": True,
        },
    },
}


def print_profile_summary() -> None:
    print("=" * 72)
    print(f"Profile: {PROFILE_NAME}")
    print(f"Description: {DESCRIPTION}")
    print("=" * 72)
    print("Market:")
    print("  primary_symbol: BNB/USDT:USDT")
    print("  symbols:        ['BNB/USDT:USDT']")
    print("Controls:")
    print("  BNB cap:        0.01 BNB / 20 USDT")
    print("  leverage:       1x")
    print("  max attempts:   1")
    print("  profile state:  readonly inactive by default")
    print("  live ready:     false")
    print()


def print_dry_run_sql() -> None:
    payload_json = json.dumps(BNB_STRATEGY_TRIAL_PROFILE, indent=2)
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
            BNB_STRATEGY_TRIAL_PROFILE,
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
    print("  symbols=['BNB/USDT:USDT']")


async def main() -> None:
    apply = os.getenv("APPLY", "").strip().lower() in {"1", "true", "yes", "on"}
    print_profile_summary()
    if apply:
        print("Applying BNB strategy-trial profile...")
        await apply_profile()
    else:
        print_dry_run_sql()
        print()
        print("To apply after authorization: APPLY=true python3 scripts/seed_strategy_trial_bnb_profile.py")


if __name__ == "__main__":
    asyncio.run(main())
