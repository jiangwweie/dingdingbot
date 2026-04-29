#!/usr/bin/env python3
"""
T1: 4h Donchian 20-bar Breakout + ATR Trailing Exit — Research-Only Proxy

策略:
  - Entry: 4h close > max(high[-20:]), 下一根 4h open 入场
  - Initial Stop: entry - 2 × ATR(14, 4h)
  - Trailing Stop: max(prev_stop, highest_close_since_entry - 3 × ATR(14))
  - No fixed TP
  - Exit: trailing stop hit

反前瞻:
  - Donchian high/low 不含 signal bar
  - ATR 只用 signal bar 及之前已收盘数据
  - Entry 用下一根 open
  - Trailing stop 只用已收盘 K 的 close 更新

约束: 不改 src, 不改 runtime, 不提交 git
"""
import asyncio
import json
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import List, Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.infrastructure.historical_data_repository import HistoricalDataRepository

# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────
SYMBOL = "ETH/USDT:USDT"
TIMEFRAME = "4h"
DONCHIAN_LOOKBACK = 20
ATR_PERIOD = 14
INITIAL_STOP_ATR_MULT = Decimal("2")    # initial stop = entry - 2×ATR
TRAILING_ATR_MULT     = Decimal("3")    # trailing = highest_close - 3×ATR
MAX_LOSS_PCT          = Decimal("0.01") # 1% risk per trade
MAX_TOTAL_EXPOSURE    = Decimal("2.0")
FEE_RATE              = Decimal("0.000405")
ENTRY_SLIPPAGE        = Decimal("0.0001")
DB_PATH               = "data/v3_dev.db"
OUTPUT_JSON           = "reports/research/t1_donchian_4h_proxy_2026-04-28.json"

# Year boundaries (ms) — first bar whose timestamp >= boundary belongs to that year
YEAR_STARTS = {
    2022: 1640995200000,   # 2022-01-01 00:00 UTC
    2023: 1672531200000,   # 2023-01-01 00:00 UTC
    2024: 1704067200000,   # 2024-01-01 00:00 UTC
    2025: 1735689600000,   # 2025-01-01 00:00 UTC
    2026: 1767225600000,   # 2026-01-01 00:00 UTC
}

# ──────────────────────────────────────────────────────────────────────────────
# Data types
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Kline:
    ts: int
    o: Decimal; h: Decimal; l: Decimal; c: Decimal; v: Decimal

@dataclass
class Trade:
    entry_bar: int; exit_bar: int
    entry_price: Decimal; exit_price: Decimal; stop_price: Decimal
    size: Decimal; pnl: Decimal; exit_reason: str

@dataclass
class Position:
    entry_bar: int; entry_price: Decimal; stop: Decimal
    atr: Decimal; highest_close: Decimal; size: Decimal

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def compute_atr(klines: List[Kline], period: int = ATR_PERIOD) -> List[Optional[Decimal]]:
    """Wilder's ATR. atr[i] uses klines[0..i] (inclusive). None if insufficient data."""
    n = len(klines)
    atr: List[Optional[Decimal]] = [None] * n
    if n < period + 1:
        return atr

    trs: List[Decimal] = []
    for i in range(1, n):
        tr = max(
            klines[i].h - klines[i].l,
            abs(klines[i].h - klines[i - 1].c),
            abs(klines[i].l - klines[i - 1].c),
        )
        trs.append(tr)

    # Wilder's: first ATR = SMA of first `period` TRs
    first_atr = sum(trs[:period]) / Decimal(period)
    atr[period] = first_atr  # atr at bar index `period` (0-based; needs period+1 bars total)

    for i in range(period + 1, n):
        atr[i] = (atr[i - 1] * Decimal(period - 1) + trs[i - 1]) / Decimal(period)

    return atr


def get_year(ts: int) -> Optional[int]:
    if ts < YEAR_STARTS[2022]:
        return None
    if ts >= YEAR_STARTS[2026]:
        return 2026
    for y in [2025, 2024, 2023, 2022]:
        if ts >= YEAR_STARTS[y]:
            return y
    return None

# ──────────────────────────────────────────────────────────────────────────────
# Core simulation
# ──────────────────────────────────────────────────────────────────────────────

def simulate(klines: List[Kline], year_label: str) -> Dict:
    """
    Bar-by-bar simulation with strict anti-lookahead.

    Timeline for a trade:
      bar N (closed): signal detected (close > donchian_high)
      bar N+1 (open): entry at open; initial_stop = entry - 2×ATR[N]
      bar N+2..M:     trailing stop = max(prev_stop, highest_close - 3×ATR[N])
                      exit when bar.low <= trailing_stop
    """
    n = len(klines)
    atr = compute_atr(klines, ATR_PERIOD)
    warmup = DONCHIAN_LOOKBACK + ATR_PERIOD  # need this many bars before first signal

    trades: List[Trade] = []
    pos: Optional[Position] = None
    equity = Decimal("10000")
    peak_equity = equity
    max_dd = Decimal("0")
    equity_curve = [equity]

    for i in range(warmup, n):
        bar = klines[i]

        # ── Donchian channel from CLOSED bars [i-20, i-1] ──
        don_high = max(k.h for k in klines[i - DONCHIAN_LOOKBACK : i])
        don_low  = min(k.l for k in klines[i - DONCHIAN_LOOKBACK : i])

        # ── ATR from bars [0..i-1] (all closed) ──
        current_atr = atr[i - 1]

        # ── Active position: check stop ──
        if pos is not None:
            if bar.l <= pos.stop:
                # EXIT at stop price (pessimistic: low hits first)
                exit_p = pos.stop * (ONE - ENTRY_SLIPPAGE)
                pnl = (exit_p - pos.entry_price) * pos.size
                fee = (pos.entry_price + exit_p) * pos.size * FEE_RATE
                net_pnl = pnl - fee
                equity += net_pnl
                trades.append(Trade(
                    entry_bar=pos.entry_bar, exit_bar=i,
                    entry_price=pos.entry_price, exit_price=exit_p,
                    stop_price=pos.stop, size=pos.size,
                    pnl=net_pnl, exit_reason="trailing_stop",
                ))
                pos = None
            else:
                # UPDATE trailing stop using bar's close (bar is now closed)
                pos.highest_close = max(pos.highest_close, bar.c)
                new_trail = pos.highest_close - TRAILING_ATR_MULT * pos.atr
                pos.stop = max(pos.stop, new_trail)

        # ── New entry check (only if flat and signal fires) ──
        if pos is None and current_atr is not None and current_atr > ZERO:
            if bar.c > don_high:
                entry_price = bar.o * (ONE + ENTRY_SLIPPAGE)
                init_stop   = entry_price - INITIAL_STOP_ATR_MULT * current_atr
                risk_dist   = entry_price - init_stop
                if risk_dist > ZERO:
                    size = (equity * MAX_LOSS_PCT) / risk_dist
                    pos = Position(
                        entry_bar=i, entry_price=entry_price,
                        stop=init_stop, atr=current_atr,
                        highest_close=bar.c, size=size,
                    )

        # ── Equity tracking ──
        peak_equity = max(peak_equity, equity)
        dd = (peak_equity - equity) / peak_equity if peak_equity > ZERO else ZERO
        max_dd = max(max_dd, dd)
        equity_curve.append(equity)

    # Force close any open position at last bar
    if pos is not None:
        last = klines[-1]
        exit_p = last.c * (ONE - ENTRY_SLIPPAGE)
        pnl = (exit_p - pos.entry_price) * pos.size
        fee = (pos.entry_price + exit_p) * pos.size * FEE_RATE
        net_pnl = pnl - fee
        equity += net_pnl
        trades.append(Trade(
            entry_bar=pos.entry_bar, exit_bar=n - 1,
            entry_price=pos.entry_price, exit_price=exit_p,
            stop_price=pos.stop, size=pos.size,
            pnl=net_pnl, exit_reason="force_close",
        ))
        equity_curve[-1] = equity

    # ── Compute metrics ──
    wins   = [t for t in trades if t.pnl > ZERO]
    losses = [t for t in trades if t.pnl <= ZERO]
    gross_win  = sum(t.pnl for t in wins)  if wins   else ZERO
    gross_loss = abs(sum(t.pnl for t in losses)) if losses else ZERO
    pf = gross_win / gross_loss if gross_loss > ZERO else Decimal("99")

    avg_win  = gross_win  / Decimal(len(wins))   if wins   else ZERO
    avg_loss = gross_loss / Decimal(len(losses)) if losses else ZERO
    aw_al    = avg_win / avg_loss if avg_loss > ZERO else Decimal("99")

    # Avg holding (in 4h bars → days)
    hold_bars = [(t.exit_bar - t.entry_bar) for t in trades] if trades else [0]
    avg_hold_days = (sum(hold_bars) / len(hold_bars) * 4) / 24

    # Largest winner
    largest = max((t.pnl for t in trades), default=ZERO)
    total_pnl = sum(t.pnl for t in trades)
    largest_pct = (largest / abs(total_pnl) * 100) if total_pnl != ZERO else ZERO

    return {
        "year": year_label,
        "pnl": total_pnl,
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "wr": (len(wins) / len(trades) * 100) if trades else ZERO,
        "pf": pf,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "aw_al": aw_al,
        "max_dd": max_dd * 100,
        "avg_hold_days": avg_hold_days,
        "largest_winner": largest,
        "largest_pct": largest_pct,
        "equity_curve": [float(e) for e in equity_curve],
        "trades_detail": [
            {"entry_bar": t.entry_bar, "exit_bar": t.exit_bar,
             "entry": float(t.entry_price), "exit": float(t.exit_price),
             "pnl": float(t.pnl), "reason": t.exit_reason}
            for t in trades
        ],
    }

# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

ONE = Decimal("1")
ZERO = Decimal("0")

async def main():
    print("=" * 80)
    print("T1: 4h Donchian 20-bar Breakout + ATR Trailing Exit — Research Proxy")
    print("=" * 80)

    # ── Load data ──
    repo = HistoricalDataRepository(DB_PATH)
    await repo.initialize()
    all_klines = await repo.get_klines(symbol=SYMBOL, timeframe=TIMEFRAME, limit=50000)
    all_klines.sort(key=lambda k: k.timestamp)
    print(f"Loaded {len(all_klines)} {TIMEFRAME} bars for {SYMBOL}")

    # ── Convert to Kline ──
    klines = [
        Kline(ts=k.timestamp, o=k.open, h=k.high, l=k.low, c=k.close, v=k.volume)
        for k in all_klines
    ]

    # ── Split by year ──
    year_klines: Dict[int, List[Kline]] = {y: [] for y in [2022, 2023, 2024, 2025, 2026]}
    for k in klines:
        y = get_year(k.ts)
        if y is not None and y in year_klines:
            year_klines[y].append(k)
    for y in sorted(year_klines):
        print(f"  {y}: {len(year_klines[y])} bars")

    # ── Run simulation per year ──
    results = {}
    for y in sorted(year_klines):
        bars = year_klines[y]
        if len(bars) < DONCHIAN_LOOKBACK + ATR_PERIOD + 5:
            print(f"\n  {y}: insufficient data, skipping")
            continue
        print(f"\n  Simulating {y} ({len(bars)} bars) ...")
        r = simulate(bars, str(y))
        results[str(y)] = r
        print(f"    PnL={r['pnl']:>10.2f}  Trades={r['trades']:>3}  "
              f"WR={r['wr']:.1f}%  PF={r['pf']:.2f}  "
              f"MaxDD={r['max_dd']:.1f}%  Hold={r['avg_hold_days']:.1f}d")

    # ── 3yr summary (2023-2025) ──
    t3 = [results[y] for y in ["2023", "2024", "2025"] if y in results]
    t3_pnl   = sum(r["pnl"]   for r in t3)
    t3_trades = sum(r["trades"] for r in t3)
    t3_wins  = sum(r["wins"]   for r in t3)
    t3_gross_w = sum(r["avg_win"]  * r["wins"]   for r in t3)
    t3_gross_l = sum(r["avg_loss"] * r["losses"] for r in t3)
    t3_pf    = t3_gross_w / t3_gross_l if t3_gross_l > ZERO else Decimal("99")
    t3_wr    = t3_wins / t3_trades * 100 if t3_trades else ZERO

    # ── All-years summary ──
    all_results = list(results.values())
    all_pnl    = sum(r["pnl"]    for r in all_results)
    all_trades = sum(r["trades"] for r in all_results)
    all_wins   = sum(r["wins"]   for r in all_results)
    all_gross_w = sum(r["avg_win"]  * r["wins"]   for r in all_results)
    all_gross_l = sum(r["avg_loss"] * r["losses"] for r in all_results)
    all_pf     = all_gross_w / all_gross_l if all_gross_l > ZERO else Decimal("99")
    all_wr     = all_wins / all_trades * 100 if all_trades else ZERO

    # Largest single winner (across all years)
    biggest = max(
        (t for r in all_results for t in r["trades_detail"]),
        key=lambda t: t["pnl"], default=None,
    )
    biggest_pnl = Decimal(str(biggest["pnl"])) if biggest else ZERO
    biggest_pct = (biggest_pnl / abs(all_pnl) * 100) if all_pnl != ZERO else ZERO

    # ── Print results ──
    print("\n" + "=" * 80)
    print("RESULTS")
    print("=" * 80)

    hdr = f"{'Year':<8} {'PnL':>10} {'Trades':>6} {'WR':>6} {'PF':>6} " \
          f"{'AvgWin':>10} {'AvgLoss':>10} {'W/L':>5} {'MaxDD':>7} {'Hold(d)':>7}"
    print(hdr)
    print("-" * len(hdr))
    for y in sorted(results):
        r = results[y]
        print(f"{r['year']:<8} {r['pnl']:>10.2f} {r['trades']:>6} "
              f"{r['wr']:>5.1f}% {r['pf']:>6.2f} "
              f"{r['avg_win']:>10.2f} {r['avg_loss']:>10.2f} "
              f"{r['aw_al']:>5.2f} {r['max_dd']:>6.1f}% {r['avg_hold_days']:>7.1f}")

    print(f"\n{'3yr':<8} {t3_pnl:>10.2f} {t3_trades:>6} "
          f"{t3_wr:>5.1f}% {t3_pf:>6.2f}")
    print(f"{'All':<8} {all_pnl:>10.2f} {all_trades:>6} "
          f"{all_wr:>5.1f}% {all_pf:>6.2f}")

    print(f"\nLargest single winner: {biggest_pnl:.2f} ({biggest_pct:.1f}% of total PnL)")

    # ── Pinbar comparison ──
    pinbar = {
        "2022": {"pnl": 69.30,       "wr": 19.6, "trades": 51,  "maxdd": 9.3},
        "2023": {"pnl": -3924.06,    "wr": 16.1, "trades": 62,  "maxdd": 58.1},
        "2024": {"pnl": 8500.69,     "wr": 32.9, "trades": 70,  "maxdd": 18.1},
        "2025": {"pnl": 4490.24,     "wr": 30.9, "trades": 68,  "maxdd": 12.1},
        "2026Q1": {"pnl": 820.56,    "wr": 50.0, "trades": 4,   "maxdd": 0.2},
    }
    print("\n" + "=" * 80)
    print("VS PINBAR BASELINE")
    print("=" * 80)
    hdr2 = f"{'Year':<8} {'T1 PnL':>10} {'Pinbar':>10} {'Delta':>10} {'T1 WR':>7} {'Pinbar':>7}"
    print(hdr2)
    print("-" * len(hdr2))
    for y in sorted(results):
        r = results[y]
        pb = pinbar.get(y, pinbar.get(y.replace(".0", ""), {}))
        pb_pnl = pb.get("pnl", 0)
        pb_wr  = pb.get("wr",  0)
        delta  = r["pnl"] - Decimal(str(pb_pnl))
        print(f"{r['year']:<8} {r['pnl']:>10.2f} {pb_pnl:>10.2f} {delta:>+10.2f} "
              f"{r['wr']:>6.1f}% {pb_wr:>6.1f}%")

    # ── Yearly correlation (Pearson on PnL) ──
    common = sorted(set(results.keys()) & set(pinbar.keys()))
    if len(common) >= 2:
        x = [float(results[y]["pnl"]) for y in common]
        yv = [float(pinbar[y]["pnl"]) for y in common]
        mx = sum(x) / len(x)
        my = sum(yv) / len(yv)
        cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, yv))
        sx = sum((xi - mx) ** 2 for xi in x) ** 0.5
        sy = sum((yi - my) ** 2 for yi in yv) ** 0.5
        corr = cov / (sx * sy) if sx > 0 and sy > 0 else 0
        print(f"\nYearly PnL correlation vs Pinbar: {corr:.3f}")
    else:
        corr = 0
        print("\nInsufficient common years for correlation")

    # ── Judgment ──
    print("\n" + "=" * 80)
    print("JUDGMENT")
    print("=" * 80)
    checks = [
        ("3yr PnL > 0",              t3_pnl > 0),
        ("PF > 1.0",                 t3_pf > 1),
        ("AvgWin/AvgLoss > 1.5",     any(
            r["aw_al"] > Decimal("1.5") for r in t3
        ) if t3 else False),
        ("2023 loss > Pinbar -3924",  results.get("2023", {}).get("pnl", Decimal("-99999")) > Decimal("-3924")),
    ]
    for label, ok in checks:
        print(f"  {'✅' if ok else '❌'} {label}")
    passed = all(ok for _, ok in checks)
    print(f"\n  VERDICT: {'✅ T1 PASSED' if passed else '❌ T1 FAILED — check details above'}")

    # ── Save JSON ──
    out_path = PROJECT_ROOT / OUTPUT_JSON
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {
            "strategy": "T1 Donchian 4h 20-bar + ATR trailing",
            "symbol": SYMBOL, "timeframe": TIMEFRAME,
            "lookback": DONCHIAN_LOOKBACK, "atr_period": ATR_PERIOD,
            "initial_stop_mult": str(INITIAL_STOP_ATR_MULT),
            "trailing_mult": str(TRAILING_ATR_MULT),
            "risk_pct": str(MAX_LOSS_PCT),
            "fee": str(FEE_RATE), "slippage": str(ENTRY_SLIPPAGE),
        },
        "yearly": {y: {k: v for k, v in r.items() if k != "equity_curve" and k != "trades_detail"}
                   for y, r in results.items()},
        "summary": {
            "t3_pnl": str(t3_pnl), "t3_pf": str(t3_pf), "t3_wr": str(t3_wr),
            "all_pnl": str(all_pnl), "all_pf": str(all_pf),
            "yearly_corr_vs_pinbar": corr,
        },
        "equity_curves": {y: r["equity_curve"] for y, r in results.items()},
        "trades": {y: r["trades_detail"] for y, r in results.items()},
    }
    out_path.write_text(json.dumps(payload, indent=2, default=str))
    print(f"\n  Saved: {out_path}")

    await repo.close()


if __name__ == "__main__":
    asyncio.run(main())
