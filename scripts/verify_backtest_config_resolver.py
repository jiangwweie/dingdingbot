#!/usr/bin/env python3
"""
Verify the backtest config resolver without exchange, PG, or historical data.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.application.backtest_config import (
    BacktestConfigResolver,
    DEFAULT_BACKTEST_PROFILE_PROVIDER,
    list_backtest_injectable_params,
)


async def main() -> None:
    resolver = BacktestConfigResolver(DEFAULT_BACKTEST_PROFILE_PROVIDER)
    resolved = await resolver.resolve("backtest_eth_baseline")
    request = resolved.to_backtest_request()

    print("✅ Backtest config resolver verified")
    print(f"   profile={resolved.profile_name}@v{resolved.profile_version}")
    print(f"   config_hash={resolved.config_hash}")
    print(f"   market={request.symbol} {request.timeframe} limit={request.limit}")
    print(f"   directions={resolved.params.allowed_directions}")
    print(f"   tp_ratios={resolved.params.tp_ratios}")
    print(f"   tp_targets={resolved.params.tp_targets}")
    print(f"   risk=max_loss_percent:{resolved.risk_config.max_loss_percent}, max_leverage:{resolved.risk_config.max_leverage}")
    print(f"   injectable_params={len(list_backtest_injectable_params())}")


if __name__ == "__main__":
    asyncio.run(main())
