#!/usr/bin/env python3
"""
验证 LONG-only vs 双向效果（最新主线参数）

使用 ETH 1h 最优配置，对比 LONG-only vs 双向(LONG+SHORT)
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
    Direction,
)
from src.application.backtester import Backtester
from src.infrastructure.exchange_gateway import ExchangeGateway


async def run_single_year(
    gateway,
    year: int,
    direction: str,  # "LONG-only" or "BOTH"
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
        # stress 口径
        slippage_rate=Decimal("0.001"),
        tp_slippage_rate=Decimal("0.0005"),
        fee_rate=Decimal("0.0004"),
        initial_balance=Decimal("10000"),
    )

    # 设置方向
    if direction == "LONG-only":
        allowed_directions = ["LONG"]
    else:
        allowed_directions = None  # 双向

    # 最新主线参数
    runtime_overrides = BacktestRuntimeOverrides(
        ema_period=50,
        min_distance_pct=Decimal("0.005"),
        # ATR 移除（不设置 max_atr_ratio）
        tp_ratios=[Decimal("0.5"), Decimal("0.5")],
        tp_targets=[Decimal("1.0"), Decimal("3.5")],
        breakeven_enabled=False,
        allowed_directions=allowed_directions,
    )

    # 风控配置
    risk_config = RiskConfig(
        max_loss_percent=Decimal("0.01"),
        max_leverage=20,
    )
    request.risk_overrides = risk_config

    # 订单策略
    request.order_strategy = OrderStrategy(
        id="eth_direction_test",
        name="ETH Direction Test",
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
        "direction": direction,
        "pnl": float(report.total_pnl),
        "trades": report.total_trades,
        "win_rate": float(report.win_rate) * 100,
        "sharpe": float(report.sharpe_ratio) if report.sharpe_ratio else 0.0,
        "max_drawdown": float(report.max_drawdown) * 100,
    }


async def main():
    """运行对比测试"""

    print("=" * 80)
    print("LONG-only vs 双向效果验证（最新主线参数）")
    print("=" * 80)
    print("\n固定参数：")
    print("  Symbol: ETH/USDT:USDT")
    print("  Timeframe: 1h")
    print("  Mode: v3_pms")
    print("  口径: stress")
    print("  ema_period: 50")
    print("  min_distance_pct: 0.005")
    print("  tp_ratios: [0.5, 0.5]")
    print("  tp_targets: [1.0, 3.5]")
    print("  breakeven_enabled: False")
    print("  ATR: 移除")
    print("  MTF: system config")
    print("\n对比组：")
    print("  LONG-only vs 双向(LONG+SHORT)")
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

        # 测试 LONG-only
        print("\n" + "=" * 80)
        print("测试组 1: LONG-only")
        print("=" * 80)

        for year in [2023, 2024, 2025]:
            print(f"\n运行 {year} 年回测...")
            result = await run_single_year(gateway, year, direction="LONG-only")
            results.append(result)
            print(f"  PnL: {result['pnl']:.2f} USDT")
            print(f"  Trades: {result['trades']}")
            print(f"  Win Rate: {result['win_rate']:.2f}%")
            print(f"  Sharpe: {result['sharpe']:.2f}")
            print(f"  Max DD: {result['max_drawdown']:.2f}%")

        # 测试双向
        print("\n" + "=" * 80)
        print("测试组 2: 双向(LONG+SHORT)")
        print("=" * 80)

        for year in [2023, 2024, 2025]:
            print(f"\n运行 {year} 年回测...")
            result = await run_single_year(gateway, year, direction="BOTH")
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

        print("\nLONG-only:")
        print("-" * 80)
        print(f"{'年份':<8} {'PnL':>12} {'Trades':>8} {'WinRate':>10} {'Sharpe':>8} {'MaxDD':>10}")
        print("-" * 80)
        for r in [r for r in results if r['direction'] == "LONG-only"]:
            print(f"{r['year']:<8} {r['pnl']:>12.2f} {r['trades']:>8} {r['win_rate']:>9.2f}% {r['sharpe']:>8.2f} {r['max_drawdown']:>9.2f}%")

        long_only_total_pnl = sum(r['pnl'] for r in results if r['direction'] == "LONG-only")
        print("-" * 80)
        print(f"{'总计':<8} {long_only_total_pnl:>12.2f}")

        print("\n双向(LONG+SHORT):")
        print("-" * 80)
        print(f"{'年份':<8} {'PnL':>12} {'Trades':>8} {'WinRate':>10} {'Sharpe':>8} {'MaxDD':>10}")
        print("-" * 80)
        for r in [r for r in results if r['direction'] == "BOTH"]:
            print(f"{r['year']:<8} {r['pnl']:>12.2f} {r['trades']:>8} {r['win_rate']:>9.2f}% {r['sharpe']:>8.2f} {r['max_drawdown']:>9.2f}%")

        both_total_pnl = sum(r['pnl'] for r in results if r['direction'] == "BOTH")
        print("-" * 80)
        print(f"{'总计':<8} {both_total_pnl:>12.2f}")

        # 差异对比
        print("\n" + "=" * 80)
        print("差异对比（LONG-only - 双向）")
        print("=" * 80)
        print(f"{'年份':<8} {'Δ PnL':>12} {'结论':>20}")
        print("-" * 80)

        for year in [2023, 2024, 2025]:
            long_only = next(r for r in results if r['year'] == year and r['direction'] == "LONG-only")
            both = next(r for r in results if r['year'] == year and r['direction'] == "BOTH")
            delta_pnl = long_only['pnl'] - both['pnl']
            conclusion = "LONG-only 更优 ✅" if delta_pnl > 0 else "双向更优 ❌"
            print(f"{year:<8} {delta_pnl:>12.2f} {conclusion:>20}")

        total_delta = long_only_total_pnl - both_total_pnl
        total_conclusion = "LONG-only 更优 ✅" if total_delta > 0 else "双向更优 ❌"
        print("-" * 80)
        print(f"{'总计':<8} {total_delta:>12.2f} {total_conclusion:>20}")

        # 最终结论
        print("\n" + "=" * 80)
        print("最终结论")
        print("=" * 80)

        if total_delta > 0:
            print(f"\n✅ 在新主线下，LONG-only 仍明显优于双向")
            print(f"   3 年总 PnL 改善: +{total_delta:.2f} USDT")
            if both_total_pnl != 0:
                print(f"   改善幅度: {(total_delta / abs(both_total_pnl) * 100):.2f}%")
            else:
                print(f"   改善幅度: ∞%（双向总 PnL 为 0）")
        else:
            print(f"\n❌ 在新主线下，双向优于 LONG-only")
            print(f"   3 年总 PnL 改善: {total_delta:.2f} USDT")

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
