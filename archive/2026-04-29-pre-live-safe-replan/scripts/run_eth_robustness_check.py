#!/usr/bin/env python3
"""
ETH 1h 防过拟合确认 + 小扰动稳健性测试

任务1：防过拟合确认
- 窗口：2023 + 2026Q1
- 对比：ema=60 vs ema=120

任务2：小扰动稳健性
- ema: [55, 60, 65]
- dist: [0.006, 0.007, 0.008]
- 共 9 组合
"""
import asyncio
import sys
from decimal import Decimal
from pathlib import Path
from typing import Dict, Any, List

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.infrastructure.historical_data_repository import HistoricalDataRepository
from src.application.backtester import Backtester
from src.domain.models import BacktestRequest, BacktestRuntimeOverrides

DB_PATH = "data/v3_dev.db"
SYMBOL = "ETH/USDT:USDT"
TIMEFRAME = "1h"
INITIAL_BALANCE = Decimal("10000")
SLIPPAGE_RATE = Decimal("0.001")
TP_SLIPPAGE_RATE = Decimal("0.0005")
FEE_RATE = Decimal("0.0004")

FIXED_PARAMS = {
    "tp_ratios": [Decimal("0.5"), Decimal("0.5")],
    "tp_targets": [Decimal("1.0"), Decimal("3.5")],
    "breakeven_enabled": False,
    "max_atr_ratio": Decimal("0.006"),
}

# 时间窗口
W2023_START = 1672531200000   # 2023-01-01
W2023_END = 1704067199000     # 2023-12-31 23:59:59
W2026Q1_START = 1767225600000 # 2026-01-01
W2026Q1_END = 1775020799000   # 2026-03-31 23:59:59


async def run_backtest(backtester, start, end, ema_period, min_distance_pct) -> Dict[str, Any]:
    request = BacktestRequest(
        symbol=SYMBOL, timeframe=TIMEFRAME,
        start_time=start, end_time=end,
        mode="v3_pms", initial_balance=INITIAL_BALANCE,
        slippage_rate=SLIPPAGE_RATE,
        tp_slippage_rate=TP_SLIPPAGE_RATE,
        fee_rate=FEE_RATE,
    )

    overrides = BacktestRuntimeOverrides(
        tp_ratios=FIXED_PARAMS["tp_ratios"],
        tp_targets=FIXED_PARAMS["tp_targets"],
        breakeven_enabled=FIXED_PARAMS["breakeven_enabled"],
        max_atr_ratio=FIXED_PARAMS["max_atr_ratio"],
        min_distance_pct=Decimal(str(min_distance_pct)),
        ema_period=ema_period,
        allowed_directions=["LONG"],
    )

    result = await backtester.run_backtest(request, runtime_overrides=overrides)

    return {
        "pnl": float(result.total_pnl),
        "trades": result.total_trades,
        "win_rate": float(result.win_rate) / 100 if result.win_rate else 0.0,
        "max_dd": float(result.max_drawdown) if result.max_drawdown else 0.0,
        "sharpe": float(result.sharpe_ratio) if result.sharpe_ratio else 0.0,
    }


async def main():
    print("=" * 70)
    print("ETH 1h 防过拟合确认 + 小扰动稳健性测试")
    print("=" * 70)

    print("\n固定参数:")
    print(f"  max_atr_ratio:    {FIXED_PARAMS['max_atr_ratio']}")
    print(f"  tp_ratios:        {FIXED_PARAMS['tp_ratios']}")
    print(f"  tp_targets:       {FIXED_PARAMS['tp_targets']}")
    print(f"  breakeven_enabled: {FIXED_PARAMS['breakeven_enabled']}")
    print(f"  direction:        LONG-only")
    print(f"  mode:             v3_pms")
    print(f"  cost_mode:        stress")

    print("\n初始化...")
    repo = HistoricalDataRepository(DB_PATH)
    await repo.initialize()
    bt = Backtester(exchange_gateway=None, data_repository=repo)

    results = []

    try:
        # ============================================================
        # 任务1：防过拟合确认 (2023 + 2026Q1)
        # ============================================================
        print("\n" + "=" * 70)
        print("任务1：防过拟合确认 (2023 + 2026Q1)")
        print("=" * 70)

        print("\n[1/4] 2023 + ema=60 + dist=0.007")
        r2023_60 = await run_backtest(bt, W2023_START, W2023_END, 60, 0.007)
        print(f"  pnl={r2023_60['pnl']:+.2f}, sharpe={r2023_60['sharpe']:.4f}, dd={r2023_60['max_dd']:.2%}, trades={r2023_60['trades']}")

        print("\n[2/4] 2023 + ema=120 + dist=0.007")
        r2023_120 = await run_backtest(bt, W2023_START, W2023_END, 120, 0.007)
        print(f"  pnl={r2023_120['pnl']:+.2f}, sharpe={r2023_120['sharpe']:.4f}, dd={r2023_120['max_dd']:.2%}, trades={r2023_120['trades']}")

        print("\n[3/4] 2026Q1 + ema=60 + dist=0.007")
        r2026q1_60 = await run_backtest(bt, W2026Q1_START, W2026Q1_END, 60, 0.007)
        print(f"  pnl={r2026q1_60['pnl']:+.2f}, sharpe={r2026q1_60['sharpe']:.4f}, dd={r2026q1_60['max_dd']:.2%}, trades={r2026q1_60['trades']}")

        print("\n[4/4] 2026Q1 + ema=120 + dist=0.007")
        r2026q1_120 = await run_backtest(bt, W2026Q1_START, W2026Q1_END, 120, 0.007)
        print(f"  pnl={r2026q1_120['pnl']:+.2f}, sharpe={r2026q1_120['sharpe']:.4f}, dd={r2026q1_120['max_dd']:.2%}, trades={r2026q1_120['trades']}")

        # 汇总
        print("\n" + "-" * 70)
        print("防过拟合确认结果")
        print("-" * 70)
        print(f"{'窗口':<10} {'ema':>5} {'pnl':>12} {'sharpe':>10} {'max_dd':>10} {'trades':>8}")
        print("-" * 70)
        print(f"{'2023':<10} {'60':>5} {r2023_60['pnl']:>+12.2f} {r2023_60['sharpe']:>10.4f} {r2023_60['max_dd']:>10.2%} {r2023_60['trades']:>8}")
        print(f"{'2023':<10} {'120':>5} {r2023_120['pnl']:>+12.2f} {r2023_120['sharpe']:>10.4f} {r2023_120['max_dd']:>10.2%} {r2023_120['trades']:>8}")
        print(f"{'2026Q1':<10} {'60':>5} {r2026q1_60['pnl']:>+12.2f} {r2026q1_60['sharpe']:>10.4f} {r2026q1_60['max_dd']:>10.2%} {r2026q1_60['trades']:>8}")
        print(f"{'2026Q1':<10} {'120':>5} {r2026q1_120['pnl']:>+12.2f} {r2026q1_120['sharpe']:>10.4f} {r2026q1_120['max_dd']:>10.2%} {r2026q1_120['trades']:>8}")

        # 判断
        print("\n" + "-" * 70)
        print("判断")
        print("-" * 70)

        ema60_wins = 0
        ema120_wins = 0

        # 2023
        if r2023_60['pnl'] > r2023_120['pnl']:
            ema60_wins += 1
        else:
            ema120_wins += 1

        # 2026Q1
        if r2026q1_60['pnl'] > r2026q1_120['pnl']:
            ema60_wins += 1
        else:
            ema120_wins += 1

        if ema60_wins == 2:
            print(f"✅ ema=60 在两个新窗口均占优，防过拟合确认通过")
        elif ema60_wins == 1:
            print(f"⚠️ ema=60 仅在 1/2 窗口占优，需进一步验证")
        else:
            print(f"❌ ema=60 在新窗口不占优，可能存在过拟合")

        # ============================================================
        # 任务2：小扰动稳健性测试
        # ============================================================
        print("\n" + "=" * 70)
        print("任务2：小扰动稳健性测试")
        print("=" * 70)

        ema_values = [55, 60, 65]
        dist_values = [0.006, 0.007, 0.008]

        # 使用 2024 窗口测试
        W2024_START = 1704067200000
        W2024_END = 1735689599000

        print(f"\n测试窗口: 2024")
        print(f"ema: {ema_values}")
        print(f"dist: {dist_values}")

        grid_results = []

        for ema in ema_values:
            for dist in dist_values:
                print(f"\n  ema={ema}, dist={dist:.3f} ...", end="")
                r = await run_backtest(bt, W2024_START, W2024_END, ema, dist)
                grid_results.append({
                    "ema": ema,
                    "dist": dist,
                    "pnl": r["pnl"],
                    "sharpe": r["sharpe"],
                    "max_dd": r["max_dd"],
                    "trades": r["trades"],
                })
                print(f" pnl={r['pnl']:+.2f}, sh={r['sharpe']:.4f}")

        # 汇总
        print("\n" + "-" * 70)
        print("小扰动稳健性结果")
        print("-" * 70)
        print(f"{'ema':>5} {'dist':>7} {'pnl':>12} {'sharpe':>10} {'max_dd':>10} {'trades':>8}")
        print("-" * 70)

        for r in grid_results:
            print(f"{r['ema']:>5} {r['dist']:>7.3f} {r['pnl']:>+12.2f} {r['sharpe']:>10.4f} {r['max_dd']:>10.2%} {r['trades']:>8}")

        # 分析
        print("\n" + "-" * 70)
        print("稳健性分析")
        print("-" * 70)

        # 找最优
        best = max(grid_results, key=lambda x: x["pnl"])
        print(f"\n最优组合: ema={best['ema']}, dist={best['dist']:.3f}, pnl={best['pnl']:+.2f}")

        # 检查是否是尖点解
        # 如果 ema=60, dist=0.007 是最优，检查周围是否有显著下降
        center = [r for r in grid_results if r["ema"] == 60 and r["dist"] == 0.007][0]

        # 计算相邻点的差异
        neighbors = []
        for r in grid_results:
            if r["ema"] == 60 and r["dist"] != 0.007:
                neighbors.append(r)
            elif r["dist"] == 0.007 and r["ema"] != 60:
                neighbors.append(r)

        if neighbors:
            avg_neighbor_pnl = sum(r["pnl"] for r in neighbors) / len(neighbors)
            drop_pct = (center["pnl"] - avg_neighbor_pnl) / abs(center["pnl"]) * 100 if center["pnl"] != 0 else 0

            print(f"\n中心点 (ema=60, dist=0.007): pnl={center['pnl']:+.2f}")
            print(f"相邻点平均 pnl: {avg_neighbor_pnl:+.2f}")
            print(f"相对下降: {drop_pct:.1f}%")

            if drop_pct < 5:
                print(f"✅ 不是尖点解，相邻点表现接近")
            elif drop_pct < 15:
                print(f"⚠️ 存在轻微敏感性，但仍可接受")
            else:
                print(f"❌ 可能是尖点解，需谨慎")

        # ema 方向性
        print("\nema 方向性:")
        ema_55_avg = sum(r["pnl"] for r in grid_results if r["ema"] == 55) / 3
        ema_60_avg = sum(r["pnl"] for r in grid_results if r["ema"] == 60) / 3
        ema_65_avg = sum(r["pnl"] for r in grid_results if r["ema"] == 65) / 3
        print(f"  ema=55 avg: {ema_55_avg:+.2f}")
        print(f"  ema=60 avg: {ema_60_avg:+.2f}")
        print(f"  ema=65 avg: {ema_65_avg:+.2f}")

        if ema_60_avg >= ema_55_avg and ema_60_avg >= ema_65_avg:
            print(f"  => ema=60 是局部最优")
        elif ema_55_avg > ema_60_avg:
            print(f"  => 建议继续向下探索 ema<60")
        else:
            print(f"  => ema=60 不是最优，需重新评估")

        # dist 方向性
        print("\ndist 方向性:")
        dist_006_avg = sum(r["pnl"] for r in grid_results if r["dist"] == 0.006) / 3
        dist_007_avg = sum(r["pnl"] for r in grid_results if r["dist"] == 0.007) / 3
        dist_008_avg = sum(r["pnl"] for r in grid_results if r["dist"] == 0.008) / 3
        print(f"  dist=0.006 avg: {dist_006_avg:+.2f}")
        print(f"  dist=0.007 avg: {dist_007_avg:+.2f}")
        print(f"  dist=0.008 avg: {dist_008_avg:+.2f}")

        if dist_007_avg >= dist_006_avg and dist_007_avg >= dist_008_avg:
            print(f"  => dist=0.007 是局部最优")
        else:
            print(f"  => dist=0.007 不是最优，需重新评估")

        # 最终结论
        print("\n" + "=" * 70)
        print("最终结论")
        print("=" * 70)

        all_pass = True

        # 防过拟合
        if ema60_wins == 2:
            print(f"1. 防过拟合: ✅ 通过")
        else:
            print(f"1. 防过拟合: ⚠️ 部分通过 ({ema60_wins}/2)")
            all_pass = False

        # 稳健性
        if drop_pct < 15:
            print(f"2. 小扰动稳健性: ✅ 通过 (下降 {drop_pct:.1f}%)")
        else:
            print(f"2. 小扰动稳健性: ❌ 未通过 (下降 {drop_pct:.1f}%)")
            all_pass = False

        if all_pass:
            print(f"\n✅ 冻结基线确认: ema=60, dist=0.007")
        else:
            print(f"\n⚠️ 需要进一步验证")

    finally:
        await repo.close()

    print("\n" + "=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
