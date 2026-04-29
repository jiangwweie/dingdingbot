#!/usr/bin/env python3
"""LONG-only TP2 邻域稳定性 + 跨年验证"""
import asyncio, sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.infrastructure.historical_data_repository import HistoricalDataRepository
from src.application.backtester import Backtester
from src.domain.models import BacktestRequest, BacktestRuntimeOverrides

DB = "data/v3_dev.db"
SYM = "ETH/USDT:USDT"
TF = "1h"
BAL = Decimal("10000")
SLIP = Decimal("0.001")
TP_SLIP = Decimal("0.0005")
FEE = Decimal("0.0004")

WINDOWS = [
    ("2024", 1704067200000, 1735689599000),
    ("2025", 1735689600000, 1767225599000),
]
TP2S = [Decimal("3.3"), Decimal("3.5"), Decimal("3.7")]

async def run(bt, start, end, tp2):
    req = BacktestRequest(
        symbol=SYM, timeframe=TF, start_time=start, end_time=end,
        mode="v3_pms", initial_balance=BAL,
        slippage_rate=SLIP, tp_slippage_rate=TP_SLIP, fee_rate=FEE,
    )
    ov = BacktestRuntimeOverrides(
        tp_ratios=[Decimal("0.5"), Decimal("0.5")],
        tp_targets=[Decimal("1.0"), tp2],
        breakeven_enabled=False,
        max_atr_ratio=Decimal("0.0059"),
        min_distance_pct=Decimal("0.0080"),
        ema_period=111,
        allowed_directions=["LONG"],
    )
    r = await bt.run_backtest(req, runtime_overrides=ov)
    return {
        "pnl": float(r.total_pnl),
        "trades": r.total_trades,
        "win_rate": float(r.win_rate) / 100 if r.win_rate else 0,
        "max_dd": float(r.max_drawdown) / 100 if r.max_drawdown else 0,
        "sharpe": float(r.sharpe_ratio) if r.sharpe_ratio else 0,
    }

async def main():
    repo = HistoricalDataRepository(DB)
    await repo.initialize()
    bt = Backtester(exchange_gateway=None, data_repository=repo)
    all_results = {}

    try:
        for wname, ws, we in WINDOWS:
            for tp2 in TP2S:
                r = await run(bt, ws, we, tp2)
                all_results[(wname, str(tp2))] = r
    finally:
        await repo.close()

    # 输出表
    for wname, _, _ in WINDOWS:
        print(f"\n{'='*65}")
        print(f"  {wname} LONG-only: 50/50, TP1=1.0R, TP2 sweep")
        print(f"{'='*65}")
        hdr = f"{'TP2':<6} {'trades':>6} {'pnl':>10} {'win_rate':>8} {'max_dd':>8} {'sharpe':>8}"
        print(hdr)
        print("-" * len(hdr))
        for tp2 in TP2S:
            r = all_results[(wname, str(tp2))]
            print(f"{str(tp2)+'R':<6} {r['trades']:>6} {r['pnl']:>+10.2f} {r['win_rate']:>8.2%} {r['max_dd']:>8.2%} {r['sharpe']:>8.4f}")

    # 跨年汇总
    print(f"\n{'='*65}")
    print(f"  跨年汇总")
    print(f"{'='*65}")
    hdr = f"{'TP2':<6} {'2024 pnl':>10} {'2024 sh':>8} {'2025 pnl':>10} {'2025 sh':>8} {'两窗口':>8}"
    print(hdr)
    print("-" * len(hdr))
    for tp2 in TP2S:
        r24 = all_results[("2024", str(tp2))]
        r25 = all_results[("2025", str(tp2))]
        both = "+" if r24["pnl"] > 0 and r25["pnl"] > 0 else ("-" if r24["pnl"] < 0 and r25["pnl"] < 0 else "~")
        print(f"{str(tp2)+'R':<6} {r24['pnl']:>+10.2f} {r24['sharpe']:>8.4f} {r25['pnl']:>+10.2f} {r25['sharpe']:>8.4f} {both:>8}")

    # 三问
    r25s = [all_results[("2025", str(t))] for t in TP2S]
    r24s = [all_results[("2024", str(t))] for t in TP2S]

    print(f"\n{'='*65}")
    all_pos_25 = all(r["pnl"] > 0 for r in r25s)
    all_pos_24 = all(r["pnl"] > 0 for r in r24s)
    spread_25 = max(r["pnl"] for r in r25s) - min(r["pnl"] for r in r25s)
    spread_24 = max(r["pnl"] for r in r24s) - min(r["pnl"] for r in r24s)

    print(f"Q1: 3.5R 附近是否存在稳定区间？")
    print(f"   2025: 3.3R={r25s[0]['pnl']:+.2f}  3.5R={r25s[1]['pnl']:+.2f}  3.7R={r25s[2]['pnl']:+.2f}")
    print(f"   2024: 3.3R={r24s[0]['pnl']:+.2f}  3.5R={r24s[1]['pnl']:+.2f}  3.7R={r24s[2]['pnl']:+.2f}")
    if all_pos_25:
        print(f"   => 是。2025 三组全部正收益，是稳定区间而非单点尖峰。")
    elif sum(1 for r in r25s if r["pnl"] > 0) >= 2:
        print(f"   => 基本稳定。2025 两组以上正收益。")
    else:
        print(f"   => 不稳定。2025 仅单组正收益。")

    print(f"\nQ2: 2024 和 2025 是否都支持这个主线？")
    if all_pos_24 and all_pos_25:
        print(f"   => 是。两年三组均正收益，主线泛化性强。")
    elif sum(1 for r in r24s if r["pnl"] > 0) >= 2 and sum(1 for r in r25s if r["pnl"] > 0) >= 2:
        print(f"   => 大体支持。两年多数方案正收益。")
    else:
        print(f"   => 部分支持。需要更多验证。")

    print(f"\nQ3: 下一步？")
    if all_pos_25 and all_pos_24:
        print(f"   => 固化 LONG-only 基线（50/50, TP1=1R, TP2=3.5R），开始小规模参数微调。")
    elif sum(1 for r in r25s if r["pnl"] > 0) >= 2:
        print(f"   => 选最优 TP2 固化基线，然后小动 entry 参数（ema_period 等）。")
    else:
        print(f"   => 继续只调 exit。")

if __name__ == "__main__":
    asyncio.run(main())
