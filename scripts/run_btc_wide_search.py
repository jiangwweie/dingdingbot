#!/usr/bin/env python3
"""
BTC 大区间三参数搜索

搜索空间：
- ema_period: [30, 50, 70, 100]
- max_atr_ratio: [0.008, 0.012, 0.018, 0.025]
- min_distance_pct: [0.005, 0.008, 0.012]

组合数：4 × 4 × 3 = 48 组合
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
SYMBOL = "BTC/USDT:USDT"
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

W2023_START = 1672531200000
W2023_END = 1704067199000
W2024_START = 1704067200000
W2024_END = 1735689599000
W2025_START = 1735689600000
W2025_END = 1767225599000

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
    print(f"BTC 大区间三参数搜索")
    print("=" * 70)

    print(f"\nSymbol: {SYMBOL}")
    print(f"搜索空间: ema={EMA_CHOICES}, atr={ATR_CHOICES}, dist={DIST_CHOICES}")
    print(f"总组合数: {len(EMA_CHOICES) * len(ATR_CHOICES) * len(DIST_CHOICES)}")

    repo = HistoricalDataRepository(DB_PATH)
    await repo.initialize()
    bt = Backtester(exchange_gateway=None, data_repository=repo)

    results: List[Dict[str, Any]] = []
    combo = 0
    total = len(EMA_CHOICES) * len(ATR_CHOICES) * len(DIST_CHOICES)

    try:
        for ema in EMA_CHOICES:
            for atr in ATR_CHOICES:
                for dist in DIST_CHOICES:
                    combo += 1
                    print(f"[{combo}/{total}] ema={ema}, atr={atr:.3f}, dist={dist:.3f} ...", end="")

                    r2024 = await run_backtest(bt, W2024_START, W2024_END, ema, atr, dist)
                    r2025 = await run_backtest(bt, W2025_START, W2025_END, ema, atr, dist)

                    feasible = (
                        r2024["pnl"] > 0 and r2025["pnl"] > 0 and
                        r2024["max_dd"] < 0.30 and r2025["max_dd"] < 0.30
                    )

                    if feasible:
                        score = r2024["pnl"] + r2025["pnl"] + 800 * (r2024["sharpe"] + r2025["sharpe"])
                    else:
                        score = -1e9

                    results.append({
                        "ema": ema, "atr": atr, "dist": dist,
                        "pnl_2024": r2024["pnl"], "pnl_2025": r2025["pnl"],
                        "sharpe_2024": r2024["sharpe"], "sharpe_2025": r2025["sharpe"],
                        "max_dd_2024": r2024["max_dd"], "max_dd_2025": r2025["max_dd"],
                        "trades_2024": r2024["trades"], "trades_2025": r2025["trades"],
                        "score": score, "feasible": feasible,
                    })

                    status = "✓" if feasible else "✗"
                    print(f" {status} pnl24={r2024['pnl']:+.0f}, pnl25={r2025['pnl']:+.0f}")

    finally:
        await repo.close()

    feasible_results = [r for r in results if r["feasible"]]
    feasible_results.sort(key=lambda x: x["score"], reverse=True)

    print("\n" + "=" * 70)
    print(f"BTC 结果: 可行解 {len(feasible_results)}/{total}")
    print("=" * 70)

    if not feasible_results:
        print("\n无可行解！显示所有结果（按 2024+2025 PnL 排序）:")
        results.sort(key=lambda x: x["pnl_2024"] + x["pnl_2025"], reverse=True)
        print(f"\n{'ema':>5} {'atr':>6} {'dist':>6} {'pnl24':>10} {'pnl25':>10} {'dd24':>8} {'dd25':>8}")
        print("-" * 65)
        for r in results[:15]:
            print(f"{r['ema']:>5} {r['atr']:>6.3f} {r['dist']:>6.3f} "
                  f"{r['pnl_2024']:>+10.2f} {r['pnl_2025']:>+10.2f} "
                  f"{r['max_dd_2024']:>8.2%} {r['max_dd_2025']:>8.2%}")
    else:
        print(f"\nTop 10:")
        print(f"{'rank':>4} {'ema':>5} {'atr':>6} {'dist':>6} {'pnl24':>10} {'pnl25':>10} {'sh24':>7} {'sh25':>7}")
        print("-" * 70)
        for i, r in enumerate(feasible_results[:10], 1):
            print(f"{i:>4} {r['ema']:>5} {r['atr']:>6.3f} {r['dist']:>6.3f} "
                  f"{r['pnl_2024']:>+10.2f} {r['pnl_2025']:>+10.2f} "
                  f"{r['sharpe_2024']:>7.3f} {r['sharpe_2025']:>7.3f}")

        best = feasible_results[0]
        print(f"\nBest: ema={best['ema']}, atr={best['atr']:.3f}, dist={best['dist']:.3f}")
        print(f"  2024: pnl={best['pnl_2024']:+.2f}, sharpe={best['sharpe_2024']:.4f}, dd={best['max_dd_2024']:.2%}")
        print(f"  2025: pnl={best['pnl_2025']:+.2f}, sharpe={best['sharpe_2025']:.4f}, dd={best['max_dd_2025']:.2%}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
