#!/usr/bin/env python3
"""
2022 年度验证

目标：
1. 用最终冻结主线跑 2022 年回测
2. 输出关键指标：pnl / trades / win_rate / sharpe / max_drawdown
3. 判断 2022 更接近 2023（失效）还是 2024/2025（适配）

配置（最终冻结主线）：
- ETH/USDT:USDT, 1h, v3_pms, LONG-only
- ema_period=50, min_distance_pct=0.005
- tp_ratios=[0.5, 0.5], tp_targets=[1.0, 3.5]
- breakeven_enabled=False, ATR 移除
- max_loss_percent=1%
- 时间范围：2022-01-01 ~ 2022-12-31
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
    print("2022 年度验证")
    print("=" * 80)
    print("\n配置（最终冻结主线）:")
    print("- ETH/USDT:USDT, 1h, v3_pms, LONG-only")
    print("- ema_period=50, min_distance_pct=0.005")
    print("- tp_ratios=[0.5, 0.5], tp_targets=[1.0, 3.5]")
    print("- breakeven_enabled=False, ATR 移除")
    print("- max_loss_percent=1%")
    print("- 时间范围：2022-01-01 ~ 2022-12-31")
    print("=" * 80)

    gateway = ExchangeGateway(exchange_name="binance", api_key=None, api_secret=None, testnet=False)
    await gateway.initialize()
    backtester = Backtester(exchange_gateway=gateway)

    try:
        # 运行 2022 年回测
        print("\n运行回测...")

        start_time = int(datetime(2022, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        end_time = int(datetime(2022, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)

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

        # 提取关键指标
        print("\n" + "=" * 80)
        print("2022 年回测结果")
        print("=" * 80)

        print(f"\n【关键指标】")
        print(f"  PnL: {report.total_pnl:.2f} USDT")
        print(f"  Trades: {report.total_trades}")
        print(f"  Win Rate: {report.win_rate * 100:.1f}%")
        print(f"  Sharpe: {report.sharpe_ratio:.3f}")
        print(f"  Max Drawdown (True Equity): {report.max_drawdown * 100:.2f}%")

        # 历史年度对比
        print("\n" + "=" * 80)
        print("历史年度对比")
        print("=" * 80)

        print(f"\n{'年份':<8} {'PnL':<15} {'Trades':<10} {'Win Rate':<12} {'Sharpe':<10} {'Max DD':<12}")
        print("-" * 80)
        print(f"{'2022':<8} {report.total_pnl:<15.2f} {report.total_trades:<10} "
              f"{report.win_rate * 100:<12.1f}% {report.sharpe_ratio:<10.3f} {report.max_drawdown * 100:<12.2f}%")
        print(f"{'2023':<8} {'-3032.21':<15} {'56':<10} {'16.1':<12}% {'-1.798':<10} {'49.19':<12}%")
        print(f"{'2024':<8} {'6709.48':<15} {'62':<10} {'32.3':<12}% {'1.534':<10} {'17.39':<12}%")
        print(f"{'2025':<8} {'4980.39':<15} {'60':<10} {'31.7':<12}% {'1.284':<10} {'19.32':<12}%")

        # 判断 2022 更接近哪一年
        print("\n" + "=" * 80)
        print("相似度分析")
        print("=" * 80)

        # 定义判断标准
        # 2023（失效）：PnL < 0, Win Rate < 20%, Sharpe < 0, Max DD > 40%
        # 2024/2025（适配）：PnL > 0, Win Rate > 30%, Sharpe > 1, Max DD < 20%

        is_like_2023 = (
            report.total_pnl < 0 or
            report.win_rate < 0.20 or
            report.sharpe_ratio < 0 or
            report.max_drawdown > 0.40
        )

        is_like_2024_2025 = (
            report.total_pnl > 0 and
            report.win_rate > 0.30 and
            report.sharpe_ratio > 1.0 and
            report.max_drawdown < 0.20
        )

        print(f"\n【判断标准】")
        print(f"  2023（失效边界）: PnL < 0 或 Win Rate < 20% 或 Sharpe < 0 或 Max DD > 40%")
        print(f"  2024/2025（适配环境）: PnL > 0 且 Win Rate > 30% 且 Sharpe > 1 且 Max DD < 20%")

        print(f"\n【2022 指标分析】")
        print(f"  PnL: {report.total_pnl:.2f} USDT ({'✅ 正收益' if report.total_pnl > 0 else '❌ 负收益'})")
        print(f"  Win Rate: {report.win_rate * 100:.1f}% ({'✅ > 30%' if report.win_rate > 0.30 else '❌ < 30%' if report.win_rate < 0.20 else '⚠️ 20-30%'})")
        print(f"  Sharpe: {report.sharpe_ratio:.3f} ({'✅ > 1' if report.sharpe_ratio > 1.0 else '❌ < 0' if report.sharpe_ratio < 0 else '⚠️ 0-1'})")
        print(f"  Max DD: {report.max_drawdown * 100:.2f}% ({'✅ < 20%' if report.max_drawdown < 0.20 else '❌ > 40%' if report.max_drawdown > 0.40 else '⚠️ 20-40%'})")

        # 最终答案
        print("\n" + "=" * 80)
        print("最终答案")
        print("=" * 80)

        if is_like_2023 and not is_like_2024_2025:
            print(f"\n❌ 2022 的表现更接近 2023（失效边界）。")
            print(f"   理由：")
            if report.total_pnl < 0:
                print(f"   - PnL 为负：{report.total_pnl:.2f} USDT")
            if report.win_rate < 0.20:
                print(f"   - Win Rate 过低：{report.win_rate * 100:.1f}%")
            if report.sharpe_ratio < 0:
                print(f"   - Sharpe 为负：{report.sharpe_ratio:.3f}")
            if report.max_drawdown > 0.40:
                print(f"   - Max DD 过高：{report.max_drawdown * 100:.2f}%")
        elif is_like_2024_2025 and not is_like_2023:
            print(f"\n✅ 2022 的表现更接近 2024/2025（主线适配环境）。")
            print(f"   理由：")
            print(f"   - PnL 为正：{report.total_pnl:.2f} USDT")
            print(f"   - Win Rate 健康：{report.win_rate * 100:.1f}%")
            print(f"   - Sharpe 优秀：{report.sharpe_ratio:.3f}")
            print(f"   - Max DD 可控：{report.max_drawdown * 100:.2f}%")
        else:
            print(f"\n⚠️  2022 的表现介于 2023 和 2024/2025 之间，属于过渡状态。")
            print(f"   理由：部分指标接近 2023，部分指标接近 2024/2025")

    finally:
        await gateway.close()


if __name__ == "__main__":
    asyncio.run(main())
