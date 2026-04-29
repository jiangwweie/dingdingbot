#!/usr/bin/env python3
"""
ETH/USDT 1h LONG-only exit 结构敏感性验证

3 组 exit 对照：baseline / A / B
"""
import asyncio
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.infrastructure.historical_data_repository import HistoricalDataRepository
from src.application.backtester import Backtester
from src.domain.models import BacktestRequest, BacktestRuntimeOverrides, Direction

DB_PATH = "data/v3_dev.db"
SYMBOL = "ETH/USDT:USDT"
TIMEFRAME = "1h"
INITIAL_BALANCE = Decimal("10000")
SLIPPAGE_RATE = Decimal("0.001")
TP_SLIPPAGE_RATE = Decimal("0.0005")
FEE_RATE = Decimal("0.0004")

START = 1735689600000   # 2025-01-01
END   = 1767225599000   # 2025-12-31

# 固定策略参数
STRAT = {
    "max_atr_ratio": Decimal("0.0059"),
    "min_distance_pct": Decimal("0.0080"),
    "ema_period": 111,
    "breakeven_enabled": False,
}

# 3 组 exit 方案
EXIT_CONFIGS = {
    "baseline": {
        "tp_ratios": [Decimal("0.6"), Decimal("0.4")],
        "tp_targets": [Decimal("1.0"), Decimal("2.5")],
    },
    "A_5050_R3": {
        "tp_ratios": [Decimal("0.5"), Decimal("0.5")],
        "tp_targets": [Decimal("1.0"), Decimal("3.0")],
    },
    "B_7030_R2": {
        "tp_ratios": [Decimal("0.7"), Decimal("0.3")],
        "tp_targets": [Decimal("1.0"), Decimal("2.0")],
    },
}


def calc_avg_win_loss(positions):
    """从 PositionSummary 计算 avg_win 和 avg_loss"""
    wins = [float(p.realized_pnl) for p in positions
            if p.realized_pnl is not None and p.realized_pnl > 0]
    losses = [float(p.realized_pnl) for p in positions
              if p.realized_pnl is not None and p.realized_pnl < 0]
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    return avg_win, avg_loss, len(wins), len(losses)


async def run_one(backtester, name, exit_cfg):
    request = BacktestRequest(
        symbol=SYMBOL, timeframe=TIMEFRAME,
        start_time=START, end_time=END,
        mode="v3_pms", initial_balance=INITIAL_BALANCE,
        slippage_rate=SLIPPAGE_RATE, tp_slippage_rate=TP_SLIPPAGE_RATE,
        fee_rate=FEE_RATE,
    )
    overrides = BacktestRuntimeOverrides(
        tp_ratios=exit_cfg["tp_ratios"],
        tp_targets=exit_cfg["tp_targets"],
        breakeven_enabled=STRAT["breakeven_enabled"],
        max_atr_ratio=STRAT["max_atr_ratio"],
        min_distance_pct=STRAT["min_distance_pct"],
        ema_period=STRAT["ema_period"],
        allowed_directions=["LONG"],
    )
    result = await backtester.run_backtest(request, runtime_overrides=overrides)

    # 从 positions 提取 avg_win / avg_loss
    long_positions = [p for p in result.positions if p.direction == Direction.LONG]
    avg_win, avg_loss, n_win, n_loss = calc_avg_win_loss(long_positions)

    pnl = float(result.total_pnl)
    trades = result.total_trades
    wr = float(result.win_rate) / 100 if result.win_rate else 0.0
    dd = float(result.max_drawdown) / 100 if result.max_drawdown else 0.0
    sh = float(result.sharpe_ratio) if result.sharpe_ratio else 0.0

    print(f"\n  total_pnl:     {pnl:+.2f}")
    print(f"  total_trades:  {trades}")
    print(f"  win_rate:      {wr:.2%}")
    print(f"  max_drawdown:  {dd:.2%}")
    print(f"  sharpe:        {sh:.4f}")
    print(f"  avg_win:       {avg_win:+.2f}")
    print(f"  avg_loss:       {avg_loss:.2f}")
    print(f"  win/loss ratio: {abs(avg_win / avg_loss):.2f}" if avg_loss != 0 else "")

    return {
        "name": name,
        "tp_ratios": [str(x) for x in exit_cfg["tp_ratios"]],
        "tp_targets": [str(x) for x in exit_cfg["tp_targets"]],
        "pnl": pnl, "trades": trades, "win_rate": wr,
        "max_dd": dd, "sharpe": sh,
        "avg_win": avg_win, "avg_loss": avg_loss,
    }


async def main():
    print("=" * 60)
    print("ETH/USDT 1h LONG-only exit 结构敏感性验证 (2025)")
    print("=" * 60)

    repo = HistoricalDataRepository(DB_PATH)
    await repo.initialize()
    bt = Backtester(exchange_gateway=None, data_repository=repo)

    results = []
    try:
        for name, cfg in EXIT_CONFIGS.items():
            print(f"\n--- {name} ---")
            print(f"  tp_ratios={cfg['tp_ratios']}, tp_targets={cfg['tp_targets']}")
            r = await run_one(bt, name, cfg)
            results.append(r)
    finally:
        await repo.close()

    # 对比表
    print("\n" + "=" * 70)
    print("三组 exit 对比表")
    print("=" * 70)
    header = f"{'方案':<15} {'TP结构':<16} {'trades':>6} {'pnl':>10} {'win_rate':>8} {'max_dd':>8} {'sharpe':>8} {'avg_win':>9} {'avg_loss':>9} {'w/l':>6}"
    print(header)
    print("-" * len(header))
    for r in results:
        tp_str = f"[{','.join(r['tp_targets'])}]"
        wl = abs(r['avg_win'] / r['avg_loss']) if r['avg_loss'] != 0 else 0
        print(f"{r['name']:<15} {tp_str:<16} {r['trades']:>6} {r['pnl']:>+10.2f} {r['win_rate']:>8.2%} {r['max_dd']:>8.2%} {r['sharpe']:>8.4f} {r['avg_win']:>+9.2f} {r['avg_loss']:>9.2f} {wl:>6.2f}")

    # 三个问题
    print("\n" + "=" * 60)
    print("三个问题回答")
    print("=" * 60)

    pnls = [r["pnl"] for r in results]
    sharps = [r["sharpe"] for r in results]
    best_idx = pnls.index(max(pnls))
    best = results[best_idx]
    base = results[0]

    spread = max(pnls) - min(pnls)

    print(f"\n1. exit 结构对 LONG-only 2025 有明显影响吗？")
    print(f"   三组 pnl 跨度: {spread:.2f} ({min(pnls):.2f} ~ {max(pnls):.2f})")
    if spread > 200:
        print(f"   => 有明显影响。pnl 跨度 > 200，exit 结构显著改变结果。")
    elif spread > 50:
        print(f"   => 有一定影响。pnl 跨度 ~{spread:.0f}，exit 结构有调节作用。")
    else:
        print(f"   => 影响不大。pnl 跨度仅 {spread:.0f}，exit 不是主要变量。")

    print(f"\n2. 哪组更接近把 2025 从小亏拉回打平/转正？")
    for r in results:
        tag = " ★" if r["name"] == best["name"] else ""
        print(f"   {r['name']}: pnl={r['pnl']:+.2f}, sharpe={r['sharpe']:.4f}{tag}")
    if best["pnl"] > 0:
        print(f"   => {best['name']} 已转正。")
    elif best["pnl"] > base["pnl"]:
        print(f"   => {best['name']} 优于 baseline {best['pnl'] - base['pnl']:+.2f}。")
    else:
        print(f"   => 三组均未转正，baseline 最好或差距很小。")

    print(f"\n3. 下一步是否值得继续沿 LONG-only + exit 微调？")
    if best["pnl"] > 0 or (best["pnl"] > -100 and best["sharpe"] > base["sharpe"]):
        print(f"   => 是。最优方案接近打平或已转正，exit 微调有效，值得继续。")
    elif spread > 100:
        print(f"   => 是。exit 结构有显著影响，但需结合其他变量（如 ema_period）。")
    else:
        print(f"   => 否。exit 调整无法解决核心问题，需回到参数或策略逻辑。")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
