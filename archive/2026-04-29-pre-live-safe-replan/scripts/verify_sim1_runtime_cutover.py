#!/usr/bin/env python3
"""
Verify Sim-1 runtime cutover semantics without starting trading.

This script mirrors the non-I/O parts of main.py runtime cutover:
- resolve runtime profile
- build market scope
- build SignalPipeline RiskConfig
- build runtime StrategyDefinition / runner
- build execution OrderStrategy

It does not initialize ExchangeGateway, WebSocket, PG sessions, or the REST API.
"""

import asyncio
import json
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.application.runtime_config import RuntimeConfigProvider, RuntimeConfigResolver
from src.domain.models import Direction
from src.domain.strategy_engine import create_dynamic_runner
from src.infrastructure.connection_pool import close_all_connections
from src.infrastructure.runtime_profile_repository import RuntimeProfileRepository


async def main() -> None:
    db_path = os.getenv("CONFIG_DB_PATH", "data/v3_dev.db")
    profile_name = os.getenv("RUNTIME_PROFILE", "sim1_eth_runtime")

    repo = RuntimeProfileRepository(db_path=db_path)
    await repo.initialize()
    try:
        resolved = await RuntimeConfigResolver(repo).resolve(profile_name)
        provider = RuntimeConfigProvider(resolved)

        market = provider.resolved_config.market
        risk = provider.resolved_config.risk.to_risk_config()
        strategy_module = provider.resolved_config.strategy
        execution = provider.resolved_config.execution.to_order_strategy(
            strategy_id=f"{provider.resolved_config.profile_name}_execution"
        )

        strategy_definition = strategy_module.to_strategy_definition(
            primary_symbol=market.primary_symbol,
            primary_timeframe=market.primary_timeframe,
        )
        runner = create_dynamic_runner([strategy_definition])

        assert market.symbols == ["ETH/USDT:USDT"]
        assert market.timeframes == ["1h", "4h"]
        assert market.warmup_history_bars == 100
        assert market.asset_polling_interval == 60

        assert risk.max_loss_percent == Decimal("0.01")
        assert risk.max_leverage == 20
        assert risk.max_total_exposure == Decimal("1.0")
        assert risk.daily_max_trades == 10

        assert strategy_module.allowed_directions == [Direction.LONG]
        assert strategy_definition.apply_to == ["ETH/USDT:USDT:1h"]
        assert strategy_definition.logic_tree is not None
        assert strategy_module.get_mtf_ema_period() == 60
        assert len(runner._strategies) == 1

        assert execution.tp_levels == 2
        assert execution.tp_ratios == [Decimal("0.5"), Decimal("0.5")]
        assert execution.tp_targets == [Decimal("1.0"), Decimal("3.5")]
        assert execution.initial_stop_loss_rr == Decimal("-1.0")
        assert execution.trailing_stop_enabled is False
        assert execution.oco_enabled is True

        print("✅ Sim-1 runtime cutover semantics verified")
        print(
            json.dumps(
                {
                    "profile": provider.resolved_config.profile_name,
                    "version": provider.resolved_config.version,
                    "config_hash": provider.config_hash,
                    "market": {
                        "symbols": market.symbols,
                        "timeframes": market.timeframes,
                        "warmup_bars": market.warmup_history_bars,
                        "asset_polling_interval": market.asset_polling_interval,
                    },
                    "risk": {
                        "max_loss_percent": str(risk.max_loss_percent),
                        "max_leverage": risk.max_leverage,
                        "max_total_exposure": str(risk.max_total_exposure),
                        "daily_max_trades": risk.daily_max_trades,
                    },
                    "strategy": {
                        "allowed_directions": [d.value for d in strategy_module.allowed_directions],
                        "apply_to": strategy_definition.apply_to,
                        "trigger": strategy_module.trigger.type,
                        "filters": [f.type for f in strategy_module.filters],
                        "mtf_ema_period": strategy_module.get_mtf_ema_period(),
                        "runner_strategy_count": len(runner._strategies),
                    },
                    "execution": {
                        "tp_levels": execution.tp_levels,
                        "tp_ratios": [str(v) for v in execution.tp_ratios],
                        "tp_targets": [str(v) for v in execution.tp_targets],
                        "initial_stop_loss_rr": str(execution.initial_stop_loss_rr),
                        "trailing_stop_enabled": execution.trailing_stop_enabled,
                        "oco_enabled": execution.oco_enabled,
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        await repo.close()
        await close_all_connections()


if __name__ == "__main__":
    asyncio.run(main())
