#!/usr/bin/env python3
"""
ETH 敞口调整回测

参数调整：
- max_total_exposure: 0.8 → 2.5 (250%)
- max_loss_percent: 1% → 5%
其余基准参数不变
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
        # ATR 移除
        tp_ratios=[Decimal("0.5"), Decimal("0.5")],
        tp_targets=[Decimal("1.0"), Decimal("3.5")],
        breakeven_enabled=False,
        allowed_directions=["LONG"],  # LONG-only
    )

    # 风控配置（调整后）
    risk_config = RiskConfig(
        max_loss_percent=Decimal("0.02"),      # 2%（原 1%）
        max_leverage=20,
        max_total_exposure=Decimal("2.5"),     # 250%（原 80%）
    )
    request.risk_overrides = risk_config

    # 订单策略
    request.order_strategy = OrderStrategy(
        id="eth_exposure_test_2pct",
        name="ETH Exposure Test",
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
    """运行回测"""

    print("=" * 80)
    print("ETH 敞口调整回测")
    print("=" * 80)
    print("\n基准参数（不变）：")
    print("  Symbol: ETH/USDT:USDT")
    print("  Timeframe: 1h")
    print("  Mode: v3_pms")
    print("  Direction: LONG-only")
    print("  ema_period: 50")
    print("  min_distance_pct: 0.005")
    print("  tp_ratios: [0.5, 0.5]")
    print("  tp_targets: [1.0, 3.5]")
    print("  breakeven_enabled: False")
    print("\n调整参数：")
    print("  max_loss_percent: 2% (原 1%)")
    print("  max_total_exposure: 250% (原 80%)")
    print("\nBNB9 成本参数：")
    print("  slippage_rate: 0.0001 (0.01%)")
    print("  tp_slippage_rate: 0 (0%)")
    print("  fee_rate: 0.000405 (0.0405%)")
    print("\n验证年份: 2024, 2025")
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

        for year in [2024, 2025]:
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
        print("回测结果对比")
        print("=" * 80)
        print(f"{'年份':<8} {'PnL':>12} {'Trades':>8} {'WinRate':>10} {'Sharpe':>8} {'MaxDD':>10}")
        print("-" * 80)
        for r in results:
            print(f"{r['year']:<8} {r['pnl']:>12.2f} {r['trades']:>8} {r['win_rate']:>9.2f}% {r['sharpe']:>8.2f} {r['max_drawdown']:>9.2f}%")

        # 对比基准（来自 backtest-parameters.md）
        print("\n" + "-" * 80)
        print("基准对比（max_loss=1%, exposure=80%）：")
        print("  2024: PnL +5952, Trades 80, WinRate 32.3%, Sharpe 1.91, MaxDD 15.75%")
        print("  2025: PnL +4399, Trades 77, WinRate 31.7%, Sharpe 2.01, MaxDD 11.56%")
        print("=" * 80)

    finally:
        await gateway.close()


if __name__ == "__main__":
    asyncio.run(main())
