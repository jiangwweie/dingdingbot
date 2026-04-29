#!/usr/bin/env python3
"""
BNB9 口径下结构冻结主线总体验证

使用 ETH 1h LONG-only 最优配置，BNB9 成本参数
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
        slippage_rate=Decimal("0.0001"),      # 0.01%
        tp_slippage_rate=Decimal("0"),        # 0%
        fee_rate=Decimal("0.000405"),         # 0.0405%
        initial_balance=Decimal("10000"),
    )

    # 结构冻结主线参数
    runtime_overrides = BacktestRuntimeOverrides(
        ema_period=50,
        min_distance_pct=Decimal("0.005"),
        # ATR 移除（不设置 max_atr_ratio）
        tp_ratios=[Decimal("0.5"), Decimal("0.5")],
        tp_targets=[Decimal("1.0"), Decimal("3.5")],
        breakeven_enabled=False,
        allowed_directions=["LONG"],  # LONG-only
    )

    # 风控配置
    risk_config = RiskConfig(
        max_loss_percent=Decimal("0.01"),
        max_leverage=20,
    )
    request.risk_overrides = risk_config

    # 订单策略
    request.order_strategy = OrderStrategy(
        id="eth_bnb9_final",
        name="ETH BNB9 Final Validation",
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
    """运行总体验证"""

    print("=" * 80)
    print("BNB9 口径下结构冻结主线总体验证")
    print("=" * 80)
    print("\n结构冻结主线参数：")
    print("  Symbol: ETH/USDT:USDT")
    print("  Timeframe: 1h")
    print("  Mode: v3_pms")
    print("  Direction: LONG-only")
    print("  ema_period: 50")
    print("  min_distance_pct: 0.005")
    print("  tp_ratios: [0.5, 0.5]")
    print("  tp_targets: [1.0, 3.5]")
    print("  breakeven_enabled: False")
    print("  ATR: 移除")
    print("  MTF: system config")
    print("\nBNB9 成本参数：")
    print("  slippage_rate: 0.0001 (0.01%)")
    print("  tp_slippage_rate: 0 (0%)")
    print("  fee_rate: 0.000405 (0.0405%)")
    print("\n验证年份: 2023, 2024, 2025")
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
        print("BNB9 口径验证结果")
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

        # 年度分析
        print("\n" + "=" * 80)
        print("年度表现分析")
        print("=" * 80)

        profitable_years = sum(1 for r in results if r['pnl'] > 0)
        print(f"\n盈利年份: {profitable_years}/3 ({profitable_years/3*100:.1f}%)")

        print("\n年度明细：")
        for r in results:
            status = "✅ 盈利" if r['pnl'] > 0 else "❌ 亏损"
            print(f"  {r['year']}: {status} ({r['pnl']:+.2f} USDT)")

        # 风险评估
        print("\n" + "=" * 80)
        print("风险评估")
        print("=" * 80)

        max_dd_list = [r['max_drawdown'] for r in results]
        avg_dd = sum(max_dd_list) / len(max_dd_list)
        max_dd_year = max(results, key=lambda x: x['max_drawdown'])

        print(f"\n平均最大回撤: {avg_dd:.2f}%")
        print(f"最大回撤年份: {max_dd_year['year']} ({max_dd_year['max_drawdown']:.2f}%)")

        # Sharpe 分析
        print("\n" + "=" * 80)
        print("Sharpe 比率分析")
        print("=" * 80)

        sharpe_list = [r['sharpe'] for r in results]
        avg_sharpe = sum(sharpe_list) / len(sharpe_list)
        positive_sharpe_years = sum(1 for s in sharpe_list if s > 0)

        print(f"\n平均 Sharpe: {avg_sharpe:.2f}")
        print(f"正 Sharpe 年份: {positive_sharpe_years}/3")

        # 最终结论
        print("\n" + "=" * 80)
        print("最终结论")
        print("=" * 80)

        if total_pnl > 0:
            print(f"\n✅ 结构冻结主线在 BNB9 口径下成立")
            print(f"   3 年总 PnL: {total_pnl:+.2f} USDT")
            print(f"   盈利年份: {profitable_years}/3")
            print(f"   平均 Sharpe: {avg_sharpe:.2f}")
            print(f"   平均最大回撤: {avg_dd:.2f}%")

            if profitable_years >= 2:
                print(f"\n✅ 跨年稳定性验证通过（{profitable_years}/3 年盈利）")
            else:
                print(f"\n⚠️ 跨年稳定性不足（仅 {profitable_years}/3 年盈利）")

            if avg_sharpe > 0.5:
                print(f"✅ 风险调整后收益良好（Sharpe > 0.5）")
            else:
                print(f"⚠️ 风险调整后收益一般（Sharpe = {avg_sharpe:.2f}）")

            if avg_dd < 30:
                print(f"✅ 回撤控制良好（平均 < 30%）")
            else:
                print(f"⚠️ 回撤偏大（平均 {avg_dd:.2f}%）")

        else:
            print(f"\n❌ 结构冻结主线在 BNB9 口径下不成立")
            print(f"   3 年总 PnL: {total_pnl:.2f} USDT")
            print(f"   盈利年份: {profitable_years}/3")

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
