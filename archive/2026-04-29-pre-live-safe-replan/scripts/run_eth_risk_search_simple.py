#!/usr/bin/env python3
"""
ETH 风控参数搜索 - 简化版

直接遍历参数组合，不使用 Optuna
"""
import asyncio
import sys
from decimal import Decimal
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.domain.models import (
    BacktestRequest,
    BacktestRuntimeOverrides,
    RiskConfig,
    OrderStrategy,
)
from src.application.backtester import Backtester
from src.infrastructure.exchange_gateway import ExchangeGateway


async def run_single_backtest(
    gateway,
    backtester,
    year: int,
    max_loss_percent: Decimal,
    max_total_exposure: Decimal,
) -> dict:
    """运行单次回测"""

    start_time = int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    end_time = int(datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)

    request = BacktestRequest(
        symbol="ETH/USDT:USDT",
        timeframe="1h",
        start_time=start_time,
        end_time=end_time,
        limit=9000,
        mode="v3_pms",
        slippage_rate=Decimal("0.0001"),
        tp_slippage_rate=Decimal("0"),
        fee_rate=Decimal("0.000405"),
        initial_balance=Decimal("10000"),
    )

    # 策略参数（基准）
    runtime_overrides = BacktestRuntimeOverrides(
        ema_period=50,
        min_distance_pct=Decimal("0.005"),
        tp_ratios=[Decimal("0.5"), Decimal("0.5")],
        tp_targets=[Decimal("1.0"), Decimal("3.5")],
        breakeven_enabled=False,
        allowed_directions=["LONG"],
    )

    # 风控参数（搜索变量）
    risk_config = RiskConfig(
        max_loss_percent=max_loss_percent,
        max_leverage=20,
        max_total_exposure=max_total_exposure,
    )
    request.risk_overrides = risk_config

    # 订单策略
    request.order_strategy = OrderStrategy(
        id="eth_risk_search",
        name="ETH Risk Search",
        tp_levels=2,
        tp_ratios=[Decimal("0.5"), Decimal("0.5")],
        tp_targets=[Decimal("1.0"), Decimal("3.5")],
        initial_stop_loss_rr=Decimal("-1.0"),
        trailing_stop_enabled=False,
        oco_enabled=True,
    )

    report = await backtester.run_backtest(
        request,
        runtime_overrides=runtime_overrides,
    )

    return {
        "year": year,
        "max_loss_pct": float(max_loss_percent) * 100,
        "exposure": float(max_total_exposure),
        "pnl": float(report.total_pnl),
        "trades": report.total_trades,
        "win_rate": float(report.win_rate) * 100,
        "sharpe": float(report.sharpe_ratio) if report.sharpe_ratio else 0.0,
        "max_dd": float(report.max_drawdown) * 100,
    }


async def main():
    """运行风控参数搜索"""

    print("=" * 80)
    print("ETH 风控参数搜索")
    print("=" * 80)

    # 搜索空间
    max_loss_percents = [Decimal("0.015"), Decimal("0.02"), Decimal("0.025"), Decimal("0.03")]
    max_total_exposures = [Decimal("1.0"), Decimal("1.5"), Decimal("2.0"), Decimal("2.5"), Decimal("3.0")]

    print(f"\n搜索空间：")
    print(f"  max_loss_percent: {[float(x)*100 for x in max_loss_percents]}%")
    print(f"  max_total_exposure: {[float(x) for x in max_total_exposures]}")
    print(f"\n总组合数: {len(max_loss_percents) * len(max_total_exposures)} = 20")
    print(f"验证年份: 2024, 2025")
    print("=" * 80)

    gateway = ExchangeGateway(
        exchange_name="binance",
        api_key=None,
        api_secret=None,
        testnet=False,
    )
    await gateway.initialize()
    backtester = Backtester(gateway)

    try:
        results = []

        for year in [2024, 2025]:
            print(f"\n{'='*80}")
            print(f"年份: {year}")
            print(f"{'='*80}")

            year_results = []

            for max_loss in max_loss_percents:
                for exposure in max_total_exposures:
                    print(f"\n运行: max_loss={float(max_loss)*100:.1f}%, exposure={float(exposure):.1f}x...")

                    try:
                        result = await run_single_backtest(
                            gateway, backtester, year, max_loss, exposure
                        )
                        year_results.append(result)

                        print(f"  PnL: {result['pnl']:+.2f}, Trades: {result['trades']}, "
                              f"Sharpe: {result['sharpe']:.2f}, MaxDD: {result['max_dd']:.2f}%")

                    except Exception as e:
                        print(f"  错误: {e}")

            results.extend(year_results)

            # 输出年度最佳
            if year_results:
                best = max(year_results, key=lambda x: x["sharpe"])
                print(f"\n{year} 最佳配置：")
                print(f"  max_loss_percent: {best['max_loss_pct']:.1f}%")
                print(f"  max_total_exposure: {best['exposure']:.1f}x")
                print(f"  Sharpe: {best['sharpe']:.2f}, PnL: {best['pnl']:+.2f}, MaxDD: {best['max_dd']:.2f}%")

        # 输出汇总表格
        print("\n" + "=" * 80)
        print("完整结果汇总")
        print("=" * 80)
        print(f"{'Year':<6} {'Loss%':<8} {'Exp':<6} {'PnL':>12} {'Trades':>7} {'Sharpe':>8} {'MaxDD':>8}")
        print("-" * 80)

        for r in sorted(results, key=lambda x: (x["year"], -x["sharpe"])):
            print(f"{r['year']:<6} {r['max_loss_pct']:<8.1f} {r['exposure']:<6.1f} "
                  f"{r['pnl']:>+12.2f} {r['trades']:>7} {r['sharpe']:>8.2f} {r['max_dd']:>7.2f}%")

        # 找出全局最佳
        best_2024 = max([r for r in results if r["year"] == 2024], key=lambda x: x["sharpe"])
        best_2025 = max([r for r in results if r["year"] == 2025], key=lambda x: x["sharpe"])

        print("\n" + "=" * 80)
        print("推荐配置")
        print("=" * 80)
        print(f"2024 最佳: max_loss={best_2024['max_loss_pct']:.1f}%, exposure={best_2024['exposure']:.1f}x, Sharpe={best_2024['sharpe']:.2f}")
        print(f"2025 最佳: max_loss={best_2025['max_loss_pct']:.1f}%, exposure={best_2025['exposure']:.1f}x, Sharpe={best_2025['sharpe']:.2f}")

    finally:
        await gateway.close()


if __name__ == "__main__":
    asyncio.run(main())
