#!/usr/bin/env python3
"""
验证 max_loss_percent=2.0% 效果

使用 ETH 1h LONG-only 最优配置，BNB9 口径
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

    # 风控配置（2.0%）
    risk_config = RiskConfig(
        max_loss_percent=Decimal("0.02"),  # 2.0%
        max_leverage=20,
    )
    request.risk_overrides = risk_config

    # 订单策略
    request.order_strategy = OrderStrategy(
        id="eth_2pct_test",
        name="ETH 2% Test",
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
        "pnl": float(report.total_pnl),
        "trades": report.total_trades,
        "win_rate": float(report.win_rate) * 100,
        "sharpe": float(report.sharpe_ratio) if report.sharpe_ratio else 0.0,
        "max_drawdown": float(report.max_drawdown) * 100,
    }


async def main():
    """运行验证"""

    print("=" * 80)
    print("max_loss_percent=2.0% 验证")
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
    print("\n测试变量：")
    print("  max_loss_percent: 2.0%")
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

        print("\n" + "=" * 80)
        print("开始回测")
        print("=" * 80)

        for year in [2023, 2024, 2025]:
            print(f"\n运行 {year} 年回测...")
            result = await run_single_year(gateway, year)
            results.append(result)
            print(f"  PnL: {result['pnl']:.2f} USDT")
            print(f"  Trades: {result['trades']}")
            print(f"  Win Rate: {result['win_rate']:.2f}%")
            print(f"  Sharpe: {result['sharpe']:.2f}")
            print(f"  Max DD: {result['max_drawdown']:.2f}%")

        # 输出汇总表格
        print("\n" + "=" * 80)
        print("max_loss_percent=2.0% 结果")
        print("=" * 80)
        print(f"{'年份':<8} {'PnL':>12} {'Trades':>8} {'WinRate':>10} {'Sharpe':>8} {'MaxDD':>10}")
        print("-" * 80)

        total_pnl = 0
        total_trades = 0
        for r in results:
            print(f"{r['year']:<8} {r['pnl']:>12.2f} {r['trades']:>8} {r['win_rate']:>9.2f}% {r['sharpe']:>8.2f} {r['max_drawdown']:>9.2f}%")
            total_pnl += r['pnl']
            total_trades += r['trades']

        print("-" * 80)
        print(f"{'总计':<8} {total_pnl:>12.2f} {total_trades:>8}")

        # 计算平均 Sharpe 和最大回撤
        avg_sharpe = sum(r['sharpe'] for r in results) / len(results)
        max_dd = max(r['max_drawdown'] for r in results)

        print(f"\n平均 Sharpe: {avg_sharpe:.2f}")
        print(f"最大回撤: {max_dd:.2f}%")

        # 与 1.0% 对比
        print("\n" + "=" * 80)
        print("与 max_loss_percent=1.0% 对比")
        print("=" * 80)

        # 1.0% 的数据（从之前的验证结果）
        baseline = {
            2023: {"pnl": -3582.63, "dd": 49.19},
            2024: {"pnl": 5951.81, "dd": 15.75},
            2025: {"pnl": 4398.73, "dd": 11.56},
            "total": 6767.91,
            "avg_sharpe": 0.71,
        }

        print(f"\n{'年份':<8} {'2.0% PnL':>12} {'1.0% PnL':>12} {'差异':>12} {'2.0% DD':>10} {'1.0% DD':>10}")
        print("-" * 80)

        for r in results:
            year = r['year']
            pnl_diff = r['pnl'] - baseline[year]['pnl']
            print(f"{year:<8} {r['pnl']:>12.2f} {baseline[year]['pnl']:>12.2f} {pnl_diff:>+12.2f} {r['max_drawdown']:>9.2f}% {baseline[year]['dd']:>9.2f}%")

        total_diff = total_pnl - baseline['total']
        print("-" * 80)
        print(f"{'总计':<8} {total_pnl:>12.2f} {baseline['total']:>12.2f} {total_diff:>+12.2f}")

        print("\n" + "=" * 80)
        print("结论")
        print("=" * 80)

        if total_pnl > baseline['total']:
            print(f"\n✅ 2.0% 优于 1.0%")
            print(f"   总 PnL 增加: +{total_diff:.2f} USDT")
        else:
            print(f"\n❌ 1.0% 优于 2.0%")
            print(f"   总 PnL 减少: {total_diff:.2f} USDT")

        print(f"\n平均 Sharpe 对比：")
        print(f"  2.0%: {avg_sharpe:.2f}")
        print(f"  1.0%: {baseline['avg_sharpe']:.2f}")

        print(f"\n最大回撤对比：")
        print(f"  2.0%: {max_dd:.2f}%")
        print(f"  1.0%: {max([baseline[2023]['dd'], baseline[2024]['dd'], baseline[2025]['dd']]):.2f}%")

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
