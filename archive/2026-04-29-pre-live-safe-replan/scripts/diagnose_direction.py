#!/usr/bin/env python3
"""
ETH/USDT 1h 方向诊断：baseline vs LONG-only vs SHORT-only

验证修正后 MTF 语义下，是否 SHORT 侧在系统性拖垮整体表现。
"""
import asyncio
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.infrastructure.historical_data_repository import HistoricalDataRepository
from src.application.backtester import Backtester
from src.domain.models import BacktestRequest, BacktestRuntimeOverrides

# ============================================================
# 配置
# ============================================================
SYMBOL = "ETH/USDT:USDT"
TIMEFRAME = "1h"
DB_PATH = "data/v3_dev.db"

START_TIME = 1735689600000   # 2025-01-01 00:00:00 UTC
END_TIME = 1767225599000     # 2025-12-31 23:59:59 UTC

INITIAL_BALANCE = Decimal("10000")

# Stress 成本
SLIPPAGE_RATE = Decimal("0.001")
TP_SLIPPAGE_RATE = Decimal("0.0005")
FEE_RATE = Decimal("0.0004")

# 诊断基线参数
BASELINE_PARAMS = {
    "max_atr_ratio": Decimal("0.0059"),
    "min_distance_pct": Decimal("0.0080"),
    "ema_period": 111,
    "tp_ratios": [Decimal("0.6"), Decimal("0.4")],
    "tp_targets": [Decimal("1.0"), Decimal("2.5")],
    "breakeven_enabled": False,
}


async def run_backtest(backtester, allowed_directions=None):
    """运行单次回测"""
    request = BacktestRequest(
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        start_time=START_TIME,
        end_time=END_TIME,
        mode="v3_pms",
        initial_balance=INITIAL_BALANCE,
        slippage_rate=SLIPPAGE_RATE,
        tp_slippage_rate=TP_SLIPPAGE_RATE,
        fee_rate=FEE_RATE,
    )

    runtime_overrides = BacktestRuntimeOverrides(
        tp_ratios=BASELINE_PARAMS["tp_ratios"],
        tp_targets=BASELINE_PARAMS["tp_targets"],
        breakeven_enabled=BASELINE_PARAMS["breakeven_enabled"],
        max_atr_ratio=BASELINE_PARAMS["max_atr_ratio"],
        min_distance_pct=BASELINE_PARAMS["min_distance_pct"],
        ema_period=BASELINE_PARAMS["ema_period"],
        allowed_directions=allowed_directions,
    )

    result = await backtester.run_backtest(request, runtime_overrides=runtime_overrides)
    return result


def print_result(label, result):
    """打印回测结果"""
    trades = result.total_trades
    pnl = float(result.total_pnl)
    win_rate = float(result.win_rate) / 100 if result.win_rate else 0.0
    max_dd = float(result.max_drawdown) / 100 if result.max_drawdown else 0.0
    sharpe = float(result.sharpe_ratio) if result.sharpe_ratio else 0.0

    print(f"  total_pnl:     {pnl:.2f}")
    print(f"  total_trades:  {trades}")
    print(f"  win_rate:      {win_rate:.2%}")
    print(f"  max_drawdown:  {max_dd:.2%}")
    print(f"  sharpe:        {sharpe:.4f}")

    return {"label": label, "pnl": pnl, "trades": trades, "win_rate": win_rate, "max_dd": max_dd, "sharpe": sharpe}


async def main():
    print("=" * 60)
    print("ETH/USDT 1h 方向诊断 (2025 OOS)")
    print("=" * 60)

    data_repo = HistoricalDataRepository(DB_PATH)
    await data_repo.initialize()
    backtester = Backtester(exchange_gateway=None, data_repository=data_repo)

    results = []
    try:
        # 1. Baseline (LONG + SHORT)
        print("\n[1/3] Baseline (LONG + SHORT)")
        r = await run_backtest(backtester, allowed_directions=None)
        results.append(print_result("baseline", r))

        # 2. LONG-only
        print("\n[2/3] LONG-only")
        r = await run_backtest(backtester, allowed_directions=["LONG"])
        results.append(print_result("long_only", r))

        # 3. SHORT-only
        print("\n[3/3] SHORT-only")
        r = await run_backtest(backtester, allowed_directions=["SHORT"])
        results.append(print_result("short_only", r))

    finally:
        await data_repo.close()

    # 对比表
    print("\n" + "=" * 60)
    print("对比表")
    print("=" * 60)
    print(f"{'组别':<15} {'trades':>8} {'pnl':>12} {'win_rate':>10} {'max_dd':>10} {'sharpe':>10}")
    print("-" * 65)
    for r in results:
        print(f"{r['label']:<15} {r['trades']:>8} {r['pnl']:>12.2f} {r['win_rate']:>10.2%} {r['max_dd']:>10.2%} {r['sharpe']:>10.4f}")

    # 回答三个问题
    base = results[0]
    long_r = results[1]
    short_r = results[2]

    print("\n" + "=" * 60)
    print("三个问题回答")
    print("=" * 60)

    # Q1: 是否确实是 SHORT 侧在拖垮整体
    short_contribution = short_r["pnl"]
    long_contribution = long_r["pnl"]
    print(f"\n1. 是否 SHORT 侧在拖垮整体？")
    print(f"   LONG-only  pnl = {long_contribution:+.2f}")
    print(f"   SHORT-only pnl = {short_contribution:+.2f}")
    print(f"   baseline   pnl = {base['pnl']:+.2f}")
    print(f"   baseline ≈ LONG + SHORT? {abs(base['pnl'] - (long_contribution + short_contribution)) < 50}")
    if short_contribution < 0 and long_contribution > 0:
        print(f"   => 是。SHORT 亏损吃掉 LONG 利润，净拖累 {short_contribution:+.2f}")
    elif short_contribution < long_contribution:
        print(f"   => 是。SHORT 表现显著差于 LONG")
    else:
        print(f"   => 不完全是，两边都有问题")

    # Q2: LONG-only 是否已明显优于 baseline
    print(f"\n2. LONG-only 是否明显优于 baseline？")
    print(f"   baseline sharpe = {base['sharpe']:.4f}")
    print(f"   LONG     sharpe = {long_r['sharpe']:.4f}")
    if long_r['sharpe'] > base['sharpe'] and long_r['pnl'] > base['pnl']:
        print(f"   => 是。LONG-only 在 pnl 和 sharpe 上均优于 baseline")
    elif long_r['pnl'] > base['pnl']:
        print(f"   => 是（pnl 维度）。LONG-only pnl 更高")
    else:
        print(f"   => 否。")

    # Q3: 下一步是否值得沿 "限制/重做 SHORT 逻辑" 去查
    print(f"\n3. 下一步是否值得优先沿 '限制/重做 SHORT 逻辑' 去查？")
    if short_r['pnl'] < long_r['pnl'] and short_r['sharpe'] < 0:
        print(f"   => 是。SHORT 侧 sharpe={short_r['sharpe']:.4f} 明显为负，")
        print(f"      优先修复 SHORT 方向判断或直接禁用 SHORT 是最高效路径")
    else:
        print(f"   => 需要进一步分析")

    print("\n" + "=" * 60)
    print("完成!")


if __name__ == "__main__":
    asyncio.run(main())
