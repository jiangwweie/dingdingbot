#!/usr/bin/env python3
"""
Pinbar A/B 对照测试
验证 kline_history 参数是否影响 Pinbar 结果
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime
from decimal import Decimal

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.infrastructure.historical_data_repository import HistoricalDataRepository
from src.application.backtester import Backtester
from src.domain.models import BacktestRequest, OrderStrategy, BacktestRuntimeOverrides

DB_PATH = "data/v3_dev.db"


async def test_pinbar_baseline():
    """测试 Pinbar baseline"""
    repo = HistoricalDataRepository(DB_PATH)
    await repo.initialize()

    backtester = Backtester(None, data_repository=repo)

    # 2024 年测试
    start_ts = int(datetime(2024, 1, 1).timestamp() * 1000)
    end_ts = int(datetime(2024, 12, 31, 23, 59, 59).timestamp() * 1000)

    strategy_config = [{
        "name": "pinbar",
        "triggers": [{"type": "pinbar", "enabled": True}],
        "filters": [
            {"type": "ema_trend", "enabled": True, "params": {"period": 50}},
            {"type": "mtf", "enabled": True, "params": {"ema_period": 60}},
            {"type": "atr", "enabled": True, "params": {"max_atr_ratio": Decimal("0.01")}},
        ]
    }]

    request = BacktestRequest(
        symbol="ETH/USDT:USDT",
        timeframe="1h",
        limit=10000,
        start_time=start_ts,
        end_time=end_ts,
        strategies=strategy_config,
        order_strategy=OrderStrategy(
            id="dual_tp",
            name="Dual TP",
            tp_levels=2,
            tp_ratios=[Decimal("0.6"), Decimal("0.4")],
            tp_targets=[Decimal("1.0"), Decimal("2.5")],
            initial_stop_loss_rr=Decimal("-1.0"),
            trailing_stop_enabled=False,
            oco_enabled=True,
        ),
        mode="v3_pms",
        slippage_rate=Decimal("0.0001"),
        tp_slippage_rate=Decimal("0"),
        fee_rate=Decimal("0.000405"),
        initial_balance=Decimal("10000"),
    )

    runtime_overrides = BacktestRuntimeOverrides(
        tp_ratios=[Decimal("0.6"), Decimal("0.4")],
        tp_targets=[Decimal("1.0"), Decimal("2.5")],
        breakeven_enabled=False,
        max_atr_ratio=Decimal("0.01"),
    )

    report = await backtester.run_backtest(request, runtime_overrides=runtime_overrides)

    print("=" * 60)
    print("Pinbar Baseline (2024)")
    print("=" * 60)
    print(f"Total Trades: {report.total_trades}")
    print(f"Win Rate: {report.win_rate * 100:.2f}%")
    print(f"Total PnL: {report.total_pnl:.2f} USDT")
    print("=" * 60)

    await repo.close()

    return report.total_trades, report.total_pnl


if __name__ == "__main__":
    trades, pnl = asyncio.run(test_pinbar_baseline())
    print(f"\n✅ Pinbar baseline: {trades} trades, PnL={pnl:.2f}")
