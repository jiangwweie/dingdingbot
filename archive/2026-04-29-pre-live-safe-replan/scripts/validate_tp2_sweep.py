#!/usr/bin/env python3
"""LONG-only TP2 单变量敏感性验证"""
import asyncio, sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.infrastructure.historical_data_repository import HistoricalDataRepository
from src.application.backtester import Backtester
from src.domain.models import BacktestRequest, BacktestRuntimeOverrides, Direction

DB_PATH = "data/v3_dev.db"
SYMBOL = "ETH/USDT:USDT"
TF = "1h"
BAL = Decimal("10000")
SLIP = Decimal("0.001")
TP_SLIP = Decimal("0.0005")
FEE = Decimal("0.0004")
START = 1735689600000
END   = 1767225599000

TP2_VALUES = [Decimal("2.5"), Decimal("3.0"), Decimal("3.5")]

async def run(bt, tp2):
    req = BacktestRequest(
        symbol=SYMBOL, timeframe=TF, start_time=START, end_time=END,
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
    pos = [p for p in r.positions if p.direction == Direction.LONG]
    wins = [float(p.realized_pnl) for p in pos if p.realized_pnl and p.realized_pnl > 0]
    losses = [float(p.realized_pnl) for p in pos if p.realized_pnl and p.realized_pnl < 0]
    aw = sum(wins)/len(wins) if wins else 0
    al = sum(losses)/len(losses) if losses else 0
    return {
        "tp2": str(tp2),
        "pnl": float(r.total_pnl),
        "trades": r.total_trades,
        "win_rate": float(r.win_rate)/100 if r.win_rate else 0,
        "max_dd": float(r.max_drawdown)/100 if r.max_drawdown else 0,
        "sharpe": float(r.sharpe_ratio) if r.sharpe_ratio else 0,
        "avg_win": aw, "avg_loss": al,
        "wl": abs(aw/al) if al != 0 else 0,
    }

async def main():
    repo = HistoricalDataRepository(DB_PATH)
    await repo.initialize()
    bt = Backtester(exchange_gateway=None, data_repository=repo)
    results = []
    try:
        for tp2 in TP2_VALUES:
            r = await run(bt, tp2)
            results.append(r)
    finally:
        await repo.close()

    hdr = f"{'TP2':<6} {'trades':>6} {'pnl':>10} {'win_rate':>8} {'max_dd':>8} {'sharpe':>8} {'avg_win':>9} {'avg_loss':>9} {'w/l':>6}"
    print(hdr)
    print("-"*len(hdr))
    for r in results:
        print(f"{r['tp2']+'R':<6} {r['trades']:>6} {r['pnl']:>+10.2f} {r['win_rate']:>8.2%} {r['max_dd']:>8.2%} {r['sharpe']:>8.4f} {r['avg_win']:>+9.2f} {r['avg_loss']:>9.2f} {r['wl']:>6.2f}")

    best = max(results, key=lambda x: x["pnl"])
    print(f"\nQ1: TP2 拉高是否继续改善？")
    pnls = [r["pnl"] for r in results]
    if pnls == sorted(pnls):
        print(f"  => 是。TP2 越高，pnl 越好，单调递增。")
    elif pnls[1] > pnls[0] and pnls[2] < pnls[1]:
        print(f" => 先升后降。TP2=3.0R 最优，再拉反而收益递减。")
    else:
        print(f"  => 不明显。三组差距 {max(pnls)-min(pnls):.0f}。")

    print(f"\nQ2: 最接近打平的是 TP2={best['tp2']}R, pnl={best['pnl']:+.2f}, sharpe={best['sharpe']:.4f}")
    if best["pnl"] > 0:
        print(f"  => 已转正。")
    elif best["pnl"] > -100:
        print(f"  => 非常接近打平（差 {abs(best['pnl']):.0f}）。")
    else:
        print(f"  => 离打平还差 {abs(best['pnl']):.0f}。")

    print(f"\nQ3: 下一步？")
    if best["pnl"] > -50:
        print(f"  => 继续沿 LONG-only + exit 微调，已快到盈亏平衡。")
    elif best["pnl"] > -150:
        print(f"  => exit 微调有效但接近瓶颈，可同时小动 entry（如 ema_period）。")
    else:
        print(f"  => exit 调整天花板低，需开始动 entry 参数。")

if __name__ == "__main__":
    asyncio.run(main())
