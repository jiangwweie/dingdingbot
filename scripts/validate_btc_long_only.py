#!/usr/bin/env python3
"""
BTC/USDT 1h LONG-only 验证：2025

最小验证矩阵：BTC 1h 2025
基线口径：v3_pms + stress + LONG-only
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
SYMBOL = "BTC/USDT:USDT"
TIMEFRAME = "1h"
INITIAL_BALANCE = Decimal("10000")
SLIPPAGE_RATE = Decimal("0.001")
TP_SLIPPAGE_RATE = Decimal("0.0005")
FEE_RATE = Decimal("0.0004")

# 与 ETH 脚本保持一致的基线参数
BASELINE = {
    "max_atr_ratio": Decimal("0.0059"),
    "min_distance_pct": Decimal("0.0080"),
    "ema_period": 111,
    "tp_ratios": [Decimal("0.5"), Decimal("0.5")],
    "tp_targets": [Decimal("1.0"), Decimal("3.5")],
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
    dd = float(r.max_drawdown) if r.max_drawdown else 0.0
    sh = float(r.sharpe_ratio) if r.sharpe_ratio else 0.0
    print(f"  total_pnl:     {pnl:+.2f}")
    print(f"  total_trades:  {trades}")
    print(f"  win_rate:      {wr:.2%}")
    print(f"  max_drawdown:  {dd:.2%}")
    print(f"  sharpe:        {sh:.4f}")
    return {"label": label, "pnl": pnl, "trades": trades, "win_rate": wr, "max_dd": dd, "sharpe": sh}


async def main():
    print("=" * 60)
    print("BTC/USDT 1h LONG-only 跨窗口验证")
    print("=" * 60)
    print("\n基线参数:")
    print(f"  symbol:            {SYMBOL}")
    print(f"  timeframe:         {TIMEFRAME}")
    print(f"  mode:              v3_pms")
    print(f"  direction:         LONG-only")
    print(f"  max_atr_ratio:     {BASELINE['max_atr_ratio']}")
    print(f"  min_distance_pct:  {BASELINE['min_distance_pct']}")
    print(f"  ema_period:        {BASELINE['ema_period']}")
    print(f"  tp_ratios:         {BASELINE['tp_ratios']}")
    print(f"  tp_targets:        {BASELINE['tp_targets']}")
    print(f"  breakeven_enabled: {BASELINE['breakeven_enabled']}")
    print(f"\nstress 口径:")
    print(f"  slippage_rate:     {SLIPPAGE_RATE}")
    print(f"  tp_slippage_rate:  {TP_SLIPPAGE_RATE}")
    print(f"  fee_rate:          {FEE_RATE}")

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

    # 判断
    print("\n" + "=" * 60)
    print("判断")
    print("=" * 60)

    r24, r25 = results[0], results[1]
    both_ok = r24["pnl"] > 0 and r25["pnl"] > 0

    if both_ok:
        print(f"\n✅ BTC 跨年正收益: 2024={r24['pnl']:+.2f}, 2025={r25['pnl']:+.2f}")
        print(f"   BTC 可从'强候选先验'升级为'强先验'。")
    elif r24["pnl"] > 0 or r25["pnl"] > 0:
        print(f"\n⚠️ BTC 单年正收益: 2024={r24['pnl']:+.2f}, 2025={r25['pnl']:+.2f}")
        print(f"   BTC 仍为'强候选先验'，需进一步验证。")
    else:
        print(f"\n❌ BTC 两年均亏损: 2024={r24['pnl']:+.2f}, 2025={r25['pnl']:+.2f}")
        print(f"   BTC 不适合作为主线品种。")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
