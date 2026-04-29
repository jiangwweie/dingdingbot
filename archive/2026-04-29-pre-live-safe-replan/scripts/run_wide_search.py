#!/usr/bin/env python3
"""
大区间三参数搜索

搜索空间：
- ema_period: [30, 50, 70, 100]
- max_atr_ratio: [0.008, 0.012, 0.018, 0.025]
- min_distance_pct: [0.005, 0.008, 0.012]

组合数：4 × 4 × 3 = 48 组合

测试窗口：2024 + 2025
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
}

# 时间窗口
W2024_START = 1704067200000
W2024_END = 1735689599000
W2025_START = 1735689600000
W2025_END = 1767225599000

# 搜索空间
EMA_CHOICES = [30, 50, 70, 100]
ATR_CHOICES = [0.008, 0.012, 0.018, 0.025]
DIST_CHOICES = [0.005, 0.008, 0.012]


async def run_backtest(backtester, start, end, ema, atr, dist) -> Dict[str, Any]:
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
        max_atr_ratio=Decimal(str(atr)),
        min_distance_pct=Decimal(str(dist)),
        ema_period=ema,
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
    print("大区间三参数搜索")
    print("=" * 70)

    print("\n固定参数:")
    print(f"  tp_ratios:        {FIXED_PARAMS['tp_ratios']}")
    print(f"  tp_targets:       {FIXED_PARAMS['tp_targets']}")
    print(f"  breakeven_enabled: {FIXED_PARAMS['breakeven_enabled']}")
    print(f"  direction:        LONG-only")
    print(f"  mode:             v3_pms (stress)")

    print("\n搜索空间:")
    print(f"  ema_period:       {EMA_CHOICES}")
    print(f"  max_atr_ratio:    {ATR_CHOICES}")
    print(f"  min_distance_pct: {DIST_CHOICES}")

    total_combos = len(EMA_CHOICES) * len(ATR_CHOICES) * len(DIST_CHOICES)
    print(f"\n总组合数: {total_combos}")

    print("\n初始化...")
    repo = HistoricalDataRepository(DB_PATH)
    await repo.initialize()
    bt = Backtester(exchange_gateway=None, data_repository=repo)

    results: List[Dict[str, Any]] = []
    combo = 0

    try:
        for ema in EMA_CHOICES:
            for atr in ATR_CHOICES:
                for dist in DIST_CHOICES:
                    combo += 1
                    print(f"\n[{combo}/{total_combos}] ema={ema}, atr={atr:.3f}, dist={dist:.3f} ...", end="")

                    r2024 = await run_backtest(bt, W2024_START, W2024_END, ema, atr, dist)
                    r2025 = await run_backtest(bt, W2025_START, W2025_END, ema, atr, dist)

                    # 硬约束检查
                    feasible = (
                        r2024["pnl"] > 0 and r2025["pnl"] > 0 and
                        r2024["max_dd"] < 0.30 and r2025["max_dd"] < 0.30
                    )

                    # 计算得分
                    if feasible:
                        score = r2024["pnl"] + r2025["pnl"] + 800 * (r2024["sharpe"] + r2025["sharpe"])
                    else:
                        score = -1e9

                    results.append({
                        "ema": ema,
                        "atr": atr,
                        "dist": dist,
                        "pnl_2024": r2024["pnl"],
                        "pnl_2025": r2025["pnl"],
                        "sharpe_2024": r2024["sharpe"],
                        "sharpe_2025": r2025["sharpe"],
                        "max_dd_2024": r2024["max_dd"],
                        "max_dd_2025": r2025["max_dd"],
                        "trades_2024": r2024["trades"],
                        "trades_2025": r2025["trades"],
                        "win_rate_2024": r2024["win_rate"],
                        "win_rate_2025": r2025["win_rate"],
                        "score": score,
                        "feasible": feasible,
                    })

                    status = "✓" if feasible else "✗"
                    print(f" {status} pnl24={r2024['pnl']:+.0f}, pnl25={r2025['pnl']:+.0f}, score={score:+.0f}")

    finally:
        await repo.close()

    # 排序
    feasible_results = [r for r in results if r["feasible"]]
    feasible_results.sort(key=lambda x: x["score"], reverse=True)

    # 输出结果
    print("\n" + "=" * 70)
    print("搜索结果")
    print("=" * 70)

    print(f"\n可行解: {len(feasible_results)}/{total_combos}")

    if not feasible_results:
        print("\n无可行解！")
        # 显示所有结果
        print("\n所有结果（按 score 排序）:")
        results.sort(key=lambda x: x["score"], reverse=True)
        print(f"\n{'ema':>5} {'atr':>6} {'dist':>6} {'pnl24':>10} {'pnl25':>10} {'dd24':>8} {'dd25':>8} {'feasible':>8}")
        print("-" * 70)
        for r in results[:20]:
            print(f"{r['ema']:>5} {r['atr']:>6.3f} {r['dist']:>6.3f} "
                  f"{r['pnl_2024']:>+10.2f} {r['pnl_2025']:>+10.2f} "
                  f"{r['max_dd_2024']:>8.2%} {r['max_dd_2025']:>8.2%} "
                  f"{'✓' if r['feasible'] else '✗':>8}")
        return

    # Top 20
    print("\n" + "-" * 70)
    print("Top 20 可行解")
    print("-" * 70)
    print(f"{'rank':>4} {'ema':>5} {'atr':>6} {'dist':>6} {'pnl24':>10} {'pnl25':>10} {'sh24':>7} {'sh25':>7} {'dd24':>7} {'dd25':>7} {'tr24':>5} {'tr25':>5}")
    print("-" * 90)

    for i, r in enumerate(feasible_results[:20], 1):
        print(f"{i:>4} {r['ema']:>5} {r['atr']:>6.3f} {r['dist']:>6.3f} "
              f"{r['pnl_2024']:>+10.2f} {r['pnl_2025']:>+10.2f} "
              f"{r['sharpe_2024']:>7.3f} {r['sharpe_2025']:>7.3f} "
              f"{r['max_dd_2024']:>7.2%} {r['max_dd_2025']:>7.2%} "
              f"{r['trades_2024']:>5} {r['trades_2025']:>5}")

    # Best
    best = feasible_results[0]
    print("\n" + "=" * 70)
    print("Best Params")
    print("=" * 70)
    print(f"  ema_period:       {best['ema']}")
    print(f"  max_atr_ratio:    {best['atr']:.4f}")
    print(f"  min_distance_pct: {best['dist']:.4f}")
    print(f"  score:            {best['score']:+.2f}")
    print(f"\n  2024:")
    print(f"    pnl:     {best['pnl_2024']:+.2f}")
    print(f"    sharpe:  {best['sharpe_2024']:.4f}")
    print(f"    max_dd:  {best['max_dd_2024']:.2%}")
    print(f"    trades:  {best['trades_2024']}")
    print(f"  2025:")
    print(f"    pnl:     {best['pnl_2025']:+.2f}")
    print(f"    sharpe:  {best['sharpe_2025']:.4f}")
    print(f"    max_dd:  {best['max_dd_2025']:.2%}")
    print(f"    trades:  {best['trades_2025']}")

    # 参数敏感性分析
    print("\n" + "=" * 70)
    print("参数敏感性分析 (Top 20)")
    print("=" * 70)

    top20 = feasible_results[:20]

    # ema 分布
    ema_counts = {}
    for r in top20:
        ema_counts[r['ema']] = ema_counts.get(r['ema'], 0) + 1
    print(f"\nema_period 分布:")
    for v in sorted(ema_counts.keys()):
        bar = "*" * ema_counts[v]
        print(f"  {v:>3}: {bar} ({ema_counts[v]})")

    # atr 分布
    atr_counts = {}
    for r in top20:
        atr_counts[r['atr']] = atr_counts.get(r['atr'], 0) + 1
    print(f"\nmax_atr_ratio 分布:")
    for v in sorted(atr_counts.keys()):
        bar = "*" * atr_counts[v]
        print(f"  {v:.3f}: {bar} ({atr_counts[v]})")

    # dist 分布
    dist_counts = {}
    for r in top20:
        dist_counts[r['dist']] = dist_counts.get(r['dist'], 0) + 1
    print(f"\nmin_distance_pct 分布:")
    for v in sorted(dist_counts.keys()):
        bar = "*" * dist_counts[v]
        print(f"  {v:.3f}: {bar} ({dist_counts[v]})")

    # 与之前基线对比
    print("\n" + "=" * 70)
    print("与之前基线对比")
    print("=" * 70)
    print(f"\n之前基线: ema=55, atr=0.006, dist=0.007")
    print(f"新基线:   ema={best['ema']}, atr={best['atr']:.3f}, dist={best['dist']:.3f}")
    print(f"\n改善:")
    print(f"  score: {best['score']:+.2f} (之前约 +4000)")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
