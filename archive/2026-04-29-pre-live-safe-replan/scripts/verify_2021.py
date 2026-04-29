#!/usr/bin/env python3
"""
2021 年度验证

目标：
1. 用最终冻结主线跑 2021 年回测
2. 使用严格口径：2021-01-10 开始（确保 4h EMA60 warmup）
3. 输出关键指标：pnl / trades / win_rate / sharpe / max_drawdown
4. 判断 2021 更接近 2024/2025/2026Q1（适配）还是 2022/2023（失效）

配置（最终冻结主线）：
- ETH/USDT:USDT, 1h, v3_pms, LONG-only
- ema_period=50, min_distance_pct=0.005
- tp_ratios=[0.5, 0.5], tp_targets=[1.0, 3.5]
- breakeven_enabled=False, ATR 移除
- max_loss_percent=1%
- 时间范围：2021-01-10 ~ 2021-12-31（严格口径）
"""
import asyncio
import sys
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.domain.models import BacktestRequest, BacktestRuntimeOverrides
from src.application.backtester import Backtester
from src.infrastructure.exchange_gateway import ExchangeGateway


async def main():
    print("=" * 80)
    print("2021 年度验证")
    print("=" * 80)
    print("\n配置（最终冻结主线）:")
    print("- ETH/USDT:USDT, 1h, v3_pms, LONG-only")
    print("- ema_period=50, min_distance_pct=0.005")
    print("- tp_ratios=[0.5, 0.5], tp_targets=[1.0, 3.5]")
    print("- breakeven_enabled=False, ATR 移除")
    print("- max_loss_percent=1%")
    print("- 时间范围：2021-01-10 ~ 2021-12-31（严格口径，确保 4h EMA60 warmup）")
    print("=" * 80)

    gateway = ExchangeGateway(exchange_name="binance", api_key=None, api_secret=None, testnet=False)
    await gateway.initialize()
    backtester = Backtester(exchange_gateway=gateway)

    try:
        # 运行 2021 年回测（严格口径）
        print("\n运行回测...")

        # 从 2021-01-10 开始，确保 4h EMA60 warmup
        # 4h EMA60 需要 120 根 4h K 线 = 480h = 20 天
        # 从 2021-01-01 开始获取数据，从 2021-01-10 开始评估
        start_time = int(datetime(2021, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        end_time = int(datetime(2021, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)

        # 评估窗口从 2021-01-10 开始
        eval_start_time = int(datetime(2021, 1, 10, tzinfo=timezone.utc).timestamp() * 1000)

        request = BacktestRequest(
            symbol="ETH/USDT:USDT",
            timeframe="1h",
            start_time=start_time,
            end_time=end_time,
            limit=10000,
            mode="v3_pms",
            slippage_rate=Decimal("0.0001"),
            tp_slippage_rate=Decimal("0"),
            fee_rate=Decimal("0.000405"),
            initial_balance=Decimal("10000"),
        )

        runtime_overrides = BacktestRuntimeOverrides(
            ema_period=50,
            min_distance_pct=Decimal("0.005"),
            tp_ratios=[Decimal("0.5"), Decimal("0.5")],
            tp_targets=[Decimal("1.0"), Decimal("3.5")],
            breakeven_enabled=False,
            allowed_directions=["LONG"],
            same_bar_policy="pessimistic",
        )

        report = await backtester.run_backtest(request, runtime_overrides=runtime_overrides)

        # 过滤掉 2021-01-10 之前的交易
        filtered_positions = [
            pos for pos in report.positions
            if pos.entry_time >= eval_start_time
        ]

        # 重新计算指标
        total_pnl = sum(pos.realized_pnl for pos in filtered_positions)
        total_trades = len(filtered_positions)
        winning_trades = sum(1 for pos in filtered_positions if pos.realized_pnl > 0)
        win_rate = winning_trades / total_trades if total_trades > 0 else 0

        # 提取关键指标
        print("\n" + "=" * 80)
        print("2021 年回测结果（严格口径：2021-01-10 ~ 2021-12-31）")
        print("=" * 80)

        print(f"\n【关键指标】")
        print(f"  PnL: {total_pnl:.2f} USDT")
        print(f"  Trades: {total_trades}")
        print(f"  Win Rate: {win_rate * 100:.1f}%")
        print(f"  Sharpe: {report.sharpe_ratio:.3f}")
        print(f"  Max Drawdown (True Equity): {report.max_drawdown * 100:.2f}%")

        # 历史年度对比
        print("\n" + "=" * 80)
        print("历史年度对比")
        print("=" * 80)

        print(f"\n{'年份':<12} {'PnL':<15} {'Trades':<10} {'Win Rate':<12} {'Sharpe':<10} {'Max DD':<12}")
        print("-" * 80)
        print(f"{'2021':<12} {total_pnl:<15.2f} {total_trades:<10} "
              f"{win_rate * 100:<12.1f}% {report.sharpe_ratio:<10.3f} {report.max_drawdown * 100:<12.2f}%")
        print(f"{'2022':<12} {'-348.84':<15} {'61':<10} {'34.4':<12}% {'-0.165':<10} {'11.64':<12}%")
        print(f"{'2023':<12} {'-3032.21':<15} {'56':<10} {'16.1':<12}% {'-1.798':<10} {'49.19':<12}%")
        print(f"{'2024':<12} {'6709.48':<15} {'62':<10} {'32.3':<12}% {'1.534':<10} {'17.39':<12}%")
        print(f"{'2025':<12} {'4980.39':<15} {'60':<10} {'31.7':<12}% {'1.284':<10} {'19.32':<12}%")
        print(f"{'2026 Q1':<12} {'777.17':<15} {'7':<10} {'71.4':<12}% {'2.545':<10} {'2.53':<12}%")

        # 判断 2021 更接近哪一类
        print("\n" + "=" * 80)
        print("相似度分析")
        print("=" * 80)

        # 定义判断标准
        # 2022/2023（失效）：PnL < 0 或 Sharpe < 0
        # 2024/2025/2026Q1（适配）：PnL > 0 且 Sharpe > 0

        is_like_failure = (
            total_pnl < 0 or
            report.sharpe_ratio < 0
        )

        is_like_adapted = (
            total_pnl > 0 and
            report.sharpe_ratio > 0
        )

        print(f"\n【判断标准】")
        print(f"  2022/2023（边界/失效环境）: PnL < 0 或 Sharpe < 0")
        print(f"  2024/2025/2026Q1（主线适配环境）: PnL > 0 且 Sharpe > 0")

        print(f"\n【2021 指标分析】")
        print(f"  PnL: {total_pnl:.2f} USDT ({'✅ 正收益' if total_pnl > 0 else '❌ 负收益'})")
        print(f"  Win Rate: {win_rate * 100:.1f}% ({'✅ > 30%' if win_rate > 0.30 else '❌ < 30%' if win_rate < 0.20 else '⚠️ 20-30%'})")
        print(f"  Sharpe: {report.sharpe_ratio:.3f} ({'✅ > 0' if report.sharpe_ratio > 0 else '❌ < 0'})")
        print(f"  Max DD: {report.max_drawdown * 100:.2f}% ({'✅ < 20%' if report.max_drawdown < 0.20 else '❌ > 40%' if report.max_drawdown > 0.40 else '⚠️ 20-40%'})")

        # 最终答案
        print("\n" + "=" * 80)
        print("最终答案")
        print("=" * 80)

        if is_like_adapted and not is_like_failure:
            print(f"\n✅ 2021 的表现更接近 2024/2025/2026Q1（主线适配环境）。")
            print(f"   理由：")
            print(f"   - PnL 为正：{total_pnl:.2f} USDT")
            print(f"   - Sharpe 为正：{report.sharpe_ratio:.3f}")
            print(f"   - 符合主线适配环境特征")
        elif is_like_failure and not is_like_adapted:
            print(f"\n❌ 2021 的表现更接近 2022/2023（边界/失效环境）。")
            print(f"   理由：")
            if total_pnl < 0:
                print(f"   - PnL 为负：{total_pnl:.2f} USDT")
            if report.sharpe_ratio < 0:
                print(f"   - Sharpe 为负：{report.sharpe_ratio:.3f}")
            print(f"   - 符合失效环境特征")
        else:
            print(f"\n⚠️  2021 的表现介于两类之间，属于过渡状态。")

    finally:
        await gateway.close()


if __name__ == "__main__":
    asyncio.run(main())
