#!/usr/bin/env python3
"""
验证修复：Engulfing smoke test
确认 backtester 修复后 Engulfing 可以产生 trades
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

async def test_engulfing_smoke():
    """测试 Engulfing 是否产生 trades"""
    repo = HistoricalDataRepository(DB_PATH)
    await repo.initialize()

    backtester = Backtester(None, data_repository=repo)

    # 2024 年测试 - 只测试前 100 根 K 线以加速调试
    start_ts = int(datetime(2024, 1, 1).timestamp() * 1000)
    end_ts = int(datetime(2024, 1, 5).timestamp() * 1000)  # 只测试 5 天

    print("Testing 2024-01-01 to 2024-01-05 (first 5 days for debugging)...")

    strategy_config = [{
        "name": "engulfing_test",
        "triggers": [{"type": "engulfing", "enabled": True, "params": {"max_wick_ratio": 0.6}}],
        "filters": [
            {"type": "ema_trend", "enabled": True, "params": {"period": 50}},
            {"type": "mtf", "enabled": True, "params": {"ema_period": 60}},
        ]
    }]

    request = BacktestRequest(
        symbol="ETH/USDT:USDT",
        timeframe="1h",
        limit=1000,  # 减小 limit
        start_time=start_ts,
        end_time=end_ts,
        strategies=strategy_config,
        order_strategy=OrderStrategy(
            id="dual_tp",
            name="Dual TP",
            tp_levels=2,
            tp_ratios=[Decimal("0.6"), Decimal("0.4")],
            tp_targets=[Decimal("1.0"), Decimal("3.5")],
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
        tp_targets=[Decimal("1.0"), Decimal("3.5")],
        breakeven_enabled=False,
    )

    report = await backtester.run_backtest(request, runtime_overrides=runtime_overrides)

    print("=" * 60)
    print("Engulfing Smoke Test (2024-01-01 to 2024-01-05)")
    print("=" * 60)
    print(f"Total Trades: {report.total_trades}")
    print(f"Win Rate: {report.win_rate * 100:.2f}%")
    print(f"Total PnL: {report.total_pnl:.2f} USDT")
    print(f"Sharpe Ratio: {report.sharpe_ratio:.4f}" if report.sharpe_ratio else "Sharpe Ratio: N/A")
    print(f"Max Drawdown: {report.max_drawdown * 100:.2f}%")

    # Check signal attempts
    if hasattr(report, 'signal_attempts'):
        print(f"\nSignal Attempts: {len(report.signal_attempts)}")
        fired_count = sum(1 for a in report.signal_attempts if a.final_result == "SIGNAL_FIRED")
        no_pattern_count = sum(1 for a in report.signal_attempts if a.final_result == "NO_PATTERN")
        filtered_count = sum(1 for a in report.signal_attempts if a.final_result == "FILTERED")
        print(f"  FIRED: {fired_count}")
        print(f"  NO_PATTERN: {no_pattern_count}")
        print(f"  FILTERED: {filtered_count}")

        # Show first few attempts
        print("\nFirst 5 attempts:")
        for i, attempt in enumerate(report.signal_attempts[:5]):
            print(f"  [{i}] {attempt.strategy_name}: {attempt.final_result}, pattern={attempt.pattern is not None}")

    print("=" * 60)

    await repo.close()

    return report.total_trades, report.total_pnl


if __name__ == "__main__":
    trades, pnl = asyncio.run(test_engulfing_smoke())
    if trades > 0:
        print(f"\n✅ Engulfing 修复成功: {trades} trades, PnL={pnl:.2f}")
    else:
        print(f"\n❌ Engulfing 仍然 0 trades，修复失败")
