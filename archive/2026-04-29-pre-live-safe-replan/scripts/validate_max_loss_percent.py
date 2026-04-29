#!/usr/bin/env python3
"""
验证 max_loss_percent 效果（结构冻结主线）

使用 ETH 1h LONG-only 最优配置，对比 1.0% / 0.75% / 0.5%
"""
import asyncio
import sys
from decimal import Decimal
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.domain.models import (
    BacktestRequest,
    BacktestRuntimeOverrides,
    RiskConfig,
    OrderStrategy,
)
from src.application.backtester import Backtester
from src.infrastructure.exchange_gateway import ExchangeGateway


async def run_single_year(
    gateway,
    year: int,
    max_loss_percent: Decimal,
) -> dict:
    """运行单年回测"""

    start_time = int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    end_time = int(datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)

    request = BacktestRequest(
        symbol="ETH/USDT:USDT",
        timeframe="1h",
        start_time=start_time,
        end_time=end_time,
        limit=9000,
        mode="v3_pms",
        # BNB9 口径成本参数
        slippage_rate=Decimal("0.0001"),
        tp_slippage_rate=Decimal("0"),
        fee_rate=Decimal("0.000405"),
        initial_balance=Decimal("10000"),
    )

    # 结构冻结主线参数
    runtime_overrides = BacktestRuntimeOverrides(
        ema_period=50,
        min_distance_pct=Decimal("0.005"),
        tp_ratios=[Decimal("0.5"), Decimal("0.5")],
        tp_targets=[Decimal("1.0"), Decimal("3.5")],
        breakeven_enabled=False,
        allowed_directions=["LONG"],
    )

    # 风控配置（对比变量）
    risk_config = RiskConfig(
        max_loss_percent=max_loss_percent,
        max_leverage=20,
    )
    request.risk_overrides = risk_config

    # 订单策略
    request.order_strategy = OrderStrategy(
        id="eth_max_loss_test",
        name="ETH Max Loss Test",
        tp_levels=2,
        tp_ratios=[Decimal("0.5"), Decimal("0.5")],
        tp_targets=[Decimal("1.0"), Decimal("3.5")],
        initial_stop_loss_rr=Decimal("-1.0"),
        trailing_stop_enabled=False,
        oco_enabled=True,
    )

    backtester = Backtester(gateway)
    report = await backtester.run_backtest(
        request,
        runtime_overrides=runtime_overrides,
    )

    return {
        "year": year,
        "max_loss_percent": float(max_loss_percent),
        "pnl": float(report.total_pnl),
        "trades": report.total_trades,
        "win_rate": float(report.win_rate) * 100,
        "sharpe": float(report.sharpe_ratio) if report.sharpe_ratio else 0.0,
        "max_drawdown": float(report.max_drawdown) * 100,
    }


async def main():
    """运行对比测试"""

    print("=" * 80)
    print("max_loss_percent 效果验证（结构冻结主线）")
    print("=" * 80)
    print("\n固定参数：")
    print("  Symbol: ETH/USDT:USDT")
    print("  Timeframe: 1h")
    print("  Mode: v3_pms")
    print("  口径: BNB9")
    print("  Direction: LONG-only")
    print("  ema_period: 50")
    print("  min_distance_pct: 0.005")
    print("  tp_ratios: [0.5, 0.5]")
    print("  tp_targets: [1.0, 3.5]")
    print("  breakeven_enabled: False")
    print("  ATR: 移除")
    print("  MTF: system config")
    print("\n对比变量：")
    print("  max_loss_percent: 1.0% / 0.75% / 0.5%")
    print("  年份: 2023, 2024, 2025")
    print("=" * 80)

    gateway = ExchangeGateway(
        exchange_name="binance",
        api_key=None,
        api_secret=None,
        testnet=False,
    )
    await gateway.initialize()

    try:
        results = []

        # 测试三档 max_loss_percent
        for max_loss_pct in [Decimal("0.01"), Decimal("0.0075"), Decimal("0.005")]:
            max_loss_pct_str = f"{float(max_loss_pct)*100:.2f}%"

            print("\n" + "=" * 80)
            print(f"测试组: max_loss_percent={max_loss_pct_str}")
            print("=" * 80)

            for year in [2023, 2024, 2025]:
                print(f"\n运行 {year} 年回测...")
                result = await run_single_year(gateway, year, max_loss_pct)
                results.append(result)
                print(f"  PnL: {result['pnl']:.2f} USDT")
                print(f"  Trades: {result['trades']}")
                print(f"  Win Rate: {result['win_rate']:.2f}%")
                print(f"  Sharpe: {result['sharpe']:.2f}")
                print(f"  Max DD: {result['max_drawdown']:.2f}%")

        # 输出对比表格
        print("\n" + "=" * 80)
        print("对比结果汇总")
        print("=" * 80)

        for max_loss_pct in [1.0, 0.75, 0.5]:
            print(f"\nmax_loss_percent={max_loss_pct:.2f}%:")
            print("-" * 80)
            print(f"{'年份':<8} {'PnL':>12} {'Trades':>8} {'WinRate':>10} {'Sharpe':>8} {'MaxDD':>10}")
            print("-" * 80)

            group_results = [r for r in results if r['max_loss_percent'] == max_loss_pct/100]
            for r in group_results:
                print(f"{r['year']:<8} {r['pnl']:>12.2f} {r['trades']:>8} {r['win_rate']:>9.2f}% {r['sharpe']:>8.2f} {r['max_drawdown']:>9.2f}%")

            total_pnl = sum(r['pnl'] for r in group_results)
            avg_sharpe = sum(r['sharpe'] for r in group_results) / len(group_results)
            max_dd = max(r['max_drawdown'] for r in group_results)

            print("-" * 80)
            print(f"{'总计':<8} {total_pnl:>12.2f} {'':>8} {'Avg Sharpe':>10} {avg_sharpe:>8.2f} {'Max DD':>10}")
            print(f"{'':<8} {'':>12} {'':>8} {'':>19} {max_dd:>9.2f}%")

        # 详细对比分析
        print("\n" + "=" * 80)
        print("详细对比分析")
        print("=" * 80)

        for max_loss_pct in [1.0, 0.75, 0.5]:
            group_results = [r for r in results if r['max_loss_percent'] == max_loss_pct/100]

            total_pnl = sum(r['pnl'] for r in group_results)
            avg_sharpe = sum(r['sharpe'] for r in group_results) / len(group_results)
            max_dd = max(r['max_drawdown'] for r in group_results)

            pnl_2024 = next(r['pnl'] for r in group_results if r['year'] == 2024)
            pnl_2025 = next(r['pnl'] for r in group_results if r['year'] == 2025)
            pnl_2023 = next(r['pnl'] for r in group_results if r['year'] == 2023)
            dd_2023 = next(r['max_drawdown'] for r in group_results if r['year'] == 2023)

            print(f"\nmax_loss_percent={max_loss_pct:.2f}%:")
            print(f"  总 PnL: {total_pnl:+.2f} USDT")
            print(f"  平均 Sharpe: {avg_sharpe:.2f}")
            print(f"  最大回撤: {max_dd:.2f}%")
            print(f"  2024/2025 盈利: {pnl_2024:+.2f} / {pnl_2025:+.2f} USDT")
            print(f"  2023 亏损/回撤: {pnl_2023:.2f} USDT / {dd_2023:.2f}%")

        # 平衡性评分
        print("\n" + "=" * 80)
        print("平衡性评分（保留盈利 vs 压低回撤）")
        print("=" * 80)

        scores = []
        for max_loss_pct in [1.0, 0.75, 0.5]:
            group_results = [r for r in results if r['max_loss_percent'] == max_loss_pct/100]

            pnl_2024 = next(r['pnl'] for r in group_results if r['year'] == 2024)
            pnl_2025 = next(r['pnl'] for r in group_results if r['year'] == 2025)
            dd_2023 = next(r['max_drawdown'] for r in group_results if r['year'] == 2023)

            # 评分标准：
            # 1. 2024/2025 盈利保留（越高越好）
            # 2. 2023 回撤压低（越低越好）
            profit_score = (pnl_2024 + pnl_2025) / 10000  # 归一化
            dd_score = (50 - dd_2023) / 50  # 回撤越低分数越高

            # 综合评分（权重：盈利 60%，回撤 40%）
            balance_score = profit_score * 0.6 + dd_score * 0.4

            scores.append({
                'max_loss_pct': max_loss_pct,
                'profit_score': profit_score,
                'dd_score': dd_score,
                'balance_score': balance_score,
                'pnl_2024_2025': pnl_2024 + pnl_2025,
                'dd_2023': dd_2023,
            })

            print(f"\nmax_loss_percent={max_loss_pct:.2f}%:")
            print(f"  2024/2025 盈利: {pnl_2024 + pnl_2025:+.2f} USDT")
            print(f"  2023 回撤: {dd_2023:.2f}%")
            print(f"  盈利评分: {profit_score:.3f}")
            print(f"  回撤评分: {dd_score:.3f}")
            print(f"  综合评分: {balance_score:.3f}")

        # 找出最优配置
        best = max(scores, key=lambda x: x['balance_score'])

        print("\n" + "=" * 80)
        print("最终结论")
        print("=" * 80)

        print(f"\n✅ 最平衡配置: max_loss_percent={best['max_loss_pct']:.2f}%")
        print(f"   综合评分: {best['balance_score']:.3f}")
        print(f"   2024/2025 盈利: {best['pnl_2024_2025']:+.2f} USDT")
        print(f"   2023 回撤: {best['dd_2023']:.2f}%")

        # 排序展示
        print("\n排序（按综合评分）：")
        for i, s in enumerate(sorted(scores, key=lambda x: x['balance_score'], reverse=True), 1):
            print(f"  {i}. max_loss_percent={s['max_loss_pct']:.2f}%: 评分={s['balance_score']:.3f}")

        print("\n" + "=" * 80)

    finally:
        await gateway.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n回测中断")
        sys.exit(0)
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
