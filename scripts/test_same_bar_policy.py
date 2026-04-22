#!/usr/bin/env python3
"""
测试 same-bar 撮合策略可配置性

验证：
1. 默认 pessimistic 策略（SL > TP）
2. random 策略（可配置 TP 优先概率）
3. random_seed 可复现性
"""
import asyncio
import sys
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.domain.models import (
    BacktestRequest,
    BacktestRuntimeOverrides,
)
from src.application.backtester import Backtester
from src.infrastructure.exchange_gateway import ExchangeGateway


async def test_same_bar_policy():
    """测试不同撮合策略"""

    print("=" * 80)
    print("Same-Bar 撮合策略测试")
    print("=" * 80)

    gateway = ExchangeGateway(
        exchange_name="binance",
        api_key=None,
        api_secret=None,
        testnet=False,
    )
    await gateway.initialize()

    try:
        # 测试配置
        start_time = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        end_time = int(datetime(2024, 1, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)

        request = BacktestRequest(
            symbol="ETH/USDT:USDT",
            timeframe="1h",
            start_time=start_time,
            end_time=end_time,
            limit=1000,
            mode="v3_pms",
            slippage_rate=Decimal("0.0001"),
            tp_slippage_rate=Decimal("0"),
            fee_rate=Decimal("0.000405"),
            initial_balance=Decimal("10000"),
        )

        # 测试 1: 默认 pessimistic 策略
        print("\n" + "=" * 80)
        print("测试 1: 默认 pessimistic 策略（SL > TP）")
        print("=" * 80)

        runtime_overrides_1 = BacktestRuntimeOverrides(
            ema_period=50,
            min_distance_pct=Decimal("0.005"),
            tp_ratios=[Decimal("0.5"), Decimal("0.5")],
            tp_targets=[Decimal("1.0"), Decimal("3.5")],
            breakeven_enabled=False,
            allowed_directions=["LONG"],
            same_bar_policy="pessimistic",  # 显式指定
        )

        report_1 = await backtester.run_backtest(
            request,
            runtime_overrides=runtime_overrides_1,
        )

        print(f"PnL: {float(report_1.total_pnl):.2f} USDT")
        print(f"Trades: {report_1.total_trades}")
        print(f"Win Rate: {float(report_1.win_rate) * 100:.2f}%")

        # 测试 2: random 策略（TP 优先概率 0.3）
        print("\n" + "=" * 80)
        print("测试 2: random 策略（TP 优先概率 0.3）")
        print("=" * 80)

        runtime_overrides_2 = BacktestRuntimeOverrides(
            ema_period=50,
            min_distance_pct=Decimal("0.005"),
            tp_ratios=[Decimal("0.5"), Decimal("0.5")],
            tp_targets=[Decimal("1.0"), Decimal("3.5")],
            breakeven_enabled=False,
            allowed_directions=["LONG"],
            same_bar_policy="random",
            same_bar_tp_first_prob=Decimal("0.3"),
            random_seed=42,  # 固定种子
        )

        report_2 = await backtester.run_backtest(
            request,
            runtime_overrides=runtime_overrides_2,
        )

        print(f"PnL: {float(report_2.total_pnl):.2f} USDT")
        print(f"Trades: {report_2.total_trades}")
        print(f"Win Rate: {float(report_2.win_rate) * 100:.2f}%")

        # 测试 3: random 策略（TP 优先概率 0.7）
        print("\n" + "=" * 80)
        print("测试 3: random 策略（TP 优先概率 0.7）")
        print("=" * 80)

        runtime_overrides_3 = BacktestRuntimeOverrides(
            ema_period=50,
            min_distance_pct=Decimal("0.005"),
            tp_ratios=[Decimal("0.5"), Decimal("0.5")],
            tp_targets=[Decimal("1.0"), Decimal("3.5")],
            breakeven_enabled=False,
            allowed_directions=["LONG"],
            same_bar_policy="random",
            same_bar_tp_first_prob=Decimal("0.7"),
            random_seed=42,  # 相同种子
        )

        report_3 = await backtester.run_backtest(
            request,
            runtime_overrides=runtime_overrides_3,
        )

        print(f"PnL: {float(report_3.total_pnl):.2f} USDT")
        print(f"Trades: {report_3.total_trades}")
        print(f"Win Rate: {float(report_3.win_rate) * 100:.2f}%")

        # 测试 4: 验证可复现性（相同种子应产生相同结果）
        print("\n" + "=" * 80)
        print("测试 4: 验证可复现性（相同种子）")
        print("=" * 80)

        runtime_overrides_4 = BacktestRuntimeOverrides(
            ema_period=50,
            min_distance_pct=Decimal("0.005"),
            tp_ratios=[Decimal("0.5"), Decimal("0.5")],
            tp_targets=[Decimal("1.0"), Decimal("3.5")],
            breakeven_enabled=False,
            allowed_directions=["LONG"],
            same_bar_policy="random",
            same_bar_tp_first_prob=Decimal("0.5"),
            random_seed=42,  # 与测试 2 相同种子
        )

        report_4 = await backtester.run_backtest(
            request,
            runtime_overrides=runtime_overrides_4,
        )

        print(f"PnL: {float(report_4.total_pnl):.2f} USDT")
        print(f"Trades: {report_4.total_trades}")
        print(f"Win Rate: {float(report_4.win_rate) * 100:.2f}%")

        # 对比分析
        print("\n" + "=" * 80)
        print("对比分析")
        print("=" * 80)

        print(f"\n测试 1 (pessimistic): PnL = {float(report_1.total_pnl):.2f} USDT")
        print(f"测试 2 (random, TP=0.3): PnL = {float(report_2.total_pnl):.2f} USDT")
        print(f"测试 3 (random, TP=0.7): PnL = {float(report_3.total_pnl):.2f} USDT")
        print(f"测试 4 (random, TP=0.5, seed=42): PnL = {float(report_4.total_pnl):.2f} USDT")

        print("\n结论：")
        if float(report_1.total_pnl) != float(report_2.total_pnl):
            print("✅ random 策略生效（结果不同于 pessimistic）")
        else:
            print("⚠️ random 策略可能未触发 same-bar 冲突")

        if float(report_2.total_pnl) != float(report_3.total_pnl):
            print("✅ TP 优先概率参数生效")
        else:
            print("⚠️ TP 优先概率可能未影响结果")

        if float(report_2.total_pnl) == float(report_4.total_pnl):
            print("✅ 随机种子可复现")
        else:
            print("❌ 随机种子未正确工作")

    finally:
        await gateway.close()


if __name__ == "__main__":
    asyncio.run(test_same_bar_policy())
