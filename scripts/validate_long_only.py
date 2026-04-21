#!/usr/bin/env python3
"""
ETH/USDT 1h LONG-only 跨窗口验证：2024 vs 2025

验证 LONG-only 是否值得保留为新的最小主线。
"""
import asyncio
import sys
from decimal import Decimal
from pathlib import Path

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

BASELINE = {
    "max_atr_ratio": Decimal("0.0059"),
    "min_distance_pct": Decimal("0.0080"),
    "ema_period": 111,
    "tp_ratios": [Decimal("0.6"), Decimal("0.4")],
    "tp_targets": [Decimal("1.0"), Decimal("2.5")],
    "breakeven_enabled": False,
}

# 2024: 2024-01-01 ~ 2024-12-31
W2024_START = 1704067200000
W2024_END   = 1735689599000

# 2025: 2025-01-01 ~ 2025-12-31
W2025_START = 1735689600000
W2025_END   = 1767225599000


async def run(backtester, start, end):
    request = BacktestRequest(
        symbol=SYMBOL, timeframe=TIMEFRAME,
        start_time=start, end_time=end,
        mode="v3_pms", initial_balance=INITIAL_BALANCE,
        slippage_rate=SLIPPAGE_RATE, tp_slippage_rate=TP_SLIPPAGE_RATE,
        fee_rate=FEE_RATE,
    )
    overrides = BacktestRuntimeOverrides(
        tp_ratios=BASELINE["tp_ratios"], tp_targets=BASELINE["tp_targets"],
        breakeven_enabled=BASELINE["breakeven_enabled"],
        max_atr_ratio=BASELINE["max_atr_ratio"],
        min_distance_pct=BASELINE["min_distance_pct"],
        ema_period=BASELINE["ema_period"],
        allowed_directions=["LONG"],
    )
    return await backtester.run_backtest(request, runtime_overrides=overrides)


def show(label, r):
    pnl = float(r.total_pnl)
    trades = r.total_trades
    wr = float(r.win_rate) / 100 if r.win_rate else 0.0
    dd = float(r.max_drawdown) / 100 if r.max_drawdown else 0.0
    sh = float(r.sharpe_ratio) if r.sharpe_ratio else 0.0
    print(f"  total_pnl:     {pnl:+.2f}")
    print(f"  total_trades:  {trades}")
    print(f"  win_rate:      {wr:.2%}")
    print(f"  max_drawdown:  {dd:.2%}")
    print(f"  sharpe:        {sh:.4f}")
    return {"label": label, "pnl": pnl, "trades": trades, "win_rate": wr, "max_dd": dd, "sharpe": sh}


async def main():
    print("=" * 60)
    print("ETH/USDT 1h LONG-only 跨窗口验证")
    print("=" * 60)

    repo = HistoricalDataRepository(DB_PATH)
    await repo.initialize()
    bt = Backtester(exchange_gateway=None, data_repository=repo)

    results = []
    try:
        print("\n[1/2] 2024 LONG-only")
        r = await run(bt, W2024_START, W2024_END)
        results.append(show("2024", r))

        print("\n[2/2] 2025 LONG-only")
        r = await run(bt, W2025_START, W2025_END)
        results.append(show("2025", r))
    finally:
        await repo.close()

    # 对比表
    print("\n" + "=" * 60)
    print("对比表")
    print("=" * 60)
    print(f"{'窗口':<10} {'trades':>8} {'pnl':>12} {'win_rate':>10} {'max_dd':>10} {'sharpe':>10}")
    print("-" * 60)
    for r in results:
        print(f"{r['label']:<10} {r['trades']:>8} {r['pnl']:>+12.2f} {r['win_rate']:>10.2%} {r['max_dd']:>10.2%} {r['sharpe']:>10.4f}")

    # 三个问题
    r24, r25 = results[0], results[1]

    print("\n" + "=" * 60)
    print("三个问题回答")
    print("=" * 60)

    both_ok = r24["pnl"] > 0 and r25["pnl"] > 0
    both_negative = r24["pnl"] < 0 and r25["pnl"] < 0
    one_ok = r24["pnl"] > 0 or r25["pnl"] > 0

    print(f"\n1. LONG-only 是否值得保留为新的最小主线？")
    if both_ok:
        print(f"   => 是。两年均正收益，LONG-only 可作为主线。")
    elif one_ok:
        print(f"   => 待定。仅单年正收益，需要进一步验证泛化性。")
    else:
        print(f"   => 否。两年均亏损，LONG-only 本身不成立。")

    print(f"\n2. LONG-only 是「接近可优化」还是「本身也不成立」？")
    avg_sharpe = (r24["sharpe"] + r25["sharpe"]) / 2
    max_loss = min(r24["pnl"], r25["pnl"])
    if avg_sharpe > -0.5 and max_loss > -500:
        print(f"   => 接近可优化。avg_sharpe={avg_sharpe:.4f}，最大亏损 {max_loss:.0f}，有优化空间。")
    elif avg_sharpe > -1.0:
        print(f"   => 勉强可优化。avg_sharpe={avg_sharpe:.4f}，但需要较大调整。")
    else:
        print(f"   => 本身不成立。avg_sharpe={avg_sharpe:.4f}，远离可用。")

    print(f"\n3. 下一步更应该？")
    if both_ok or (avg_sharpe > -0.5 and max_loss > -500):
        print(f"   => 继续围绕 LONG-only 微调（参数优化 / 止盈结构调整）")
    elif one_ok:
        print(f"   => 先确认 LONG-only 在不盈利的年份为什么失效，再决定是否投入微调")
    else:
        print(f"   => 直接下调整条策略优先级，LONG-only 也救不了")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
