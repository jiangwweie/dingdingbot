#!/usr/bin/env python3
"""
R0: Risk / Exposure Upside Scan — Research-Only Proxy

Scan different risk/exposure parameters across Pinbar and T1 strategies,
compute portfolio combinations, and output three profiles (Aggressive/Balanced/Conservative).

Constraints: research-only, 不改 src, 不改 runtime, 不提交 git
"""
import asyncio
import json
import sys
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from src.infrastructure.historical_data_repository import HistoricalDataRepository

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────
SYMBOL = "ETH/USDT:USDT"
TIMEFRAME_1H = "1h"
TIMEFRAME_4H = "4h"
DB_PATH = "data/v3_dev.db"
ONE = Decimal("1")
ZERO = Decimal("0")

INITIAL_BALANCE = Decimal("10000")
FEE_RATE = Decimal("0.000405")
ENTRY_SLIPPAGE = Decimal("0.0001")
EXIT_SLIPPAGE = Decimal("0.0001")

EMA_1H_PERIOD = 50
EMA_4H_PERIOD = 60
ATR_PERIOD = 14
DONCHIAN_LOOKBACK = 20
INITIAL_STOP_ATR_MULT = Decimal("2")
TRAILING_ATR_MULT = Decimal("3")

MIN_WICK_RATIO = Decimal("0.6")
MAX_BODY_RATIO = Decimal("0.3")
BODY_POSITION_TOLERANCE = Decimal("0.1")

TP_TARGETS = [Decimal("1.0"), Decimal("3.5")]
TP_CLOSE_RATIO = Decimal("0.5")  # 50% at TP1, 50% at TP2

YEAR_STARTS = {
    2022: 1640995200000,
    2023: 1672531200000,
    2024: 1704067200000,
    2025: 1735689600000,
    2026: 1767225600000,
}

OUTPUT_JSON = "reports/research/risk_exposure_upside_scan_2026-04-28.json"
OUTPUT_MD = "docs/planning/2026-04-28-risk-exposure-upside-scan.md"

# ──────────────────────────────────────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class Kline:
    idx: int
    ts: int
    o: Decimal; h: Decimal; l: Decimal; c: Decimal; v: Decimal

@dataclass
class Trade:
    entry_bar: int; exit_bar: int
    entry_price: Decimal; exit_price: Decimal; stop_price: Decimal
    size: Decimal; pnl: Decimal; exit_reason: str
    r_multiple: Decimal; hold_bars: int
    uncapped_size: Decimal = ZERO  # size BEFORE exposure cap

# ──────────────────────────────────────────────────────────────────────────────
# Indicators
# ──────────────────────────────────────────────────────────────────────────────
def compute_ema(closes: List[Decimal], period: int) -> List[Optional[Decimal]]:
    """EMA. ema[i] = EMA of closes[0..i]. None if insufficient data."""
    n = len(closes)
    result: List[Optional[Decimal]] = [None] * n
    if n < period:
        return result
    sma = sum(closes[:period]) / Decimal(period)
    result[period - 1] = sma
    k = Decimal(2) / (Decimal(period) + Decimal(1))
    prev = sma
    for i in range(period, n):
        ema = closes[i] * k + prev * (ONE - k)
        result[i] = ema
        prev = ema
    return result

def compute_atr_full(klines: List[Kline], period: int = 14) -> List[Optional[Decimal]]:
    """ATR over FULL dataset. atr[i] uses bars [0..i]. None if insufficient."""
    n = len(klines)
    atr: List[Optional[Decimal]] = [None] * n
    if n < period + 1:
        return atr
    trs = []
    for i in range(1, n):
        tr = max(klines[i].h - klines[i].l,
                 abs(klines[i].h - klines[i - 1].c),
                 abs(klines[i].l - klines[i - 1].c))
        trs.append(tr)
    first_atr = sum(trs[:period]) / Decimal(period)
    atr[period] = first_atr
    for i in range(period + 1, n):
        atr[i] = (atr[i - 1] * Decimal(period - 1) + trs[i - 1]) / Decimal(period)
    return atr

def compute_ema_on_klines(klines: List[Kline], period: int) -> List[Optional[Decimal]]:
    closes = [k.c for k in klines]
    return compute_ema(closes, period)

# ──────────────────────────────────────────────────────────────────────────────
# Pinbar detection
# ──────────────────────────────────────────────────────────────────────────────
def detect_pinbar_long(kline: Kline, atr_val: Optional[Decimal]) -> Optional[Decimal]:
    """Return signal bar's low (stop loss) if LONG pinbar detected, else None."""
    h, l, c, o = kline.h, kline.l, kline.c, kline.o
    candle_range = h - l
    if candle_range <= ZERO:
        return None
    # ATR minimum range check (matches M1)
    if atr_val is not None and atr_val > ZERO:
        min_range = atr_val * Decimal("0.1")
        if candle_range < min_range:
            return None
    body_size = abs(c - o)
    body_ratio = body_size / candle_range
    if body_ratio > MAX_BODY_RATIO:
        return None
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l
    dominant_wick = max(upper_wick, lower_wick)
    wick_ratio = dominant_wick / candle_range
    if wick_ratio < MIN_WICK_RATIO:
        return None
    # LONG: long lower wick, body near top
    if dominant_wick != lower_wick:
        return None
    body_center = (o + c) / Decimal(2)
    body_position = (body_center - l) / candle_range
    if body_position < (ONE - BODY_POSITION_TOLERANCE - body_ratio / 2):
        return None
    return l  # stop loss = signal bar low

# ──────────────────────────────────────────────────────────────────────────────
# EMA 4h lookup helper
# ──────────────────────────────────────────────────────────────────────────────
def get_last_closed_4h_ema(klines_4h: List[Kline], ema60_4h: List[Optional[Decimal]],
                            signal_ts: int) -> Tuple[Optional[Decimal], Optional[Decimal]]:
    """Return (ema60_value, close) of the last closed 4h bar before signal_ts."""
    last_ema = None
    last_close = None
    for i, k in enumerate(klines_4h):
        candle_close_ts = k.ts + 4 * 3600 * 1000
        if candle_close_ts <= signal_ts and ema60_4h[i] is not None:
            last_ema = ema60_4h[i]
            last_close = k.c
        elif candle_close_ts > signal_ts:
            break
    return last_ema, last_close

# ──────────────────────────────────────────────────────────────────────────────
# Pinbar simulation engine
# ──────────────────────────────────────────────────────────────────────────────
def simulate_pinbar(
    klines_1h: List[Kline],
    klines_4h: List[Kline],
    ema50_1h: List[Optional[Decimal]],
    ema60_4h: List[Optional[Decimal]],
    atr_1h: List[Optional[Decimal]],
    year_start_ts: int,
    year_end_ts: int,
    max_loss_pct: Decimal = Decimal("0.01"),
    max_total_exposure: Decimal = Decimal("2.0"),
) -> Dict:
    """
    Pinbar LONG-only proxy with EMA50 (1h) + EMA60 (4h) filters.
    Matching M1 engine behavior:
    - TP1: move SL to BE (NO partial close)
    - TP2: close FULL position
    - Entry at next 1h bar open. SL = signal bar low.
    - Position sizing: fixed INITIAL_BALANCE (matching engine, not dynamic equity)
    """
    n = len(klines_1h)
    start_idx = max(EMA_1H_PERIOD, ATR_PERIOD) + 1
    while start_idx < n and klines_1h[start_idx].ts < year_start_ts:
        start_idx += 1
    end_idx = start_idx
    while end_idx < n and klines_1h[end_idx].ts < year_end_ts:
        end_idx += 1
    if end_idx - start_idx < 10:
        return _empty_result()

    trades: List[Trade] = []
    equity = INITIAL_BALANCE
    mtm_curve: List[Decimal] = []
    peak_mtm = equity
    max_dd_mtm = ZERO
    exposure_rejected = 0

    has_pos = False
    pending_entry = False
    pending_sl = ZERO

    # Active position state
    pos_size = ZERO; pos_uncapped_size = ZERO; pos_entry_price = ZERO
    pos_sl = ZERO; pos_tp1 = ZERO; pos_tp2 = ZERO
    pos_entry_bar = -1; pos_r_mult = ZERO
    tp1_hit = False

    for i in range(start_idx, end_idx):
        bar = klines_1h[i]

        # ── Execute pending entry (entry at NEXT bar open, M1 engine behavior) ──
        if pending_entry and not has_pos:
            pending_entry = False
            entry_price = bar.o * (ONE + ENTRY_SLIPPAGE)  # next bar open
            r_mult = entry_price - pending_sl
            if r_mult > ZERO:
                # Engine-style sizing: fixed INITIAL_BALANCE (not dynamic equity)
                risk_amount = INITIAL_BALANCE * max_loss_pct
                size = risk_amount / r_mult
                max_size = (INITIAL_BALANCE * max_total_exposure) / entry_price
                uncapped_size = size
                if size > max_size:
                    size = max_size
                    exposure_rejected += 1
                if size > ZERO:
                    has_pos = True
                    pos_size = size
                    pos_uncapped_size = uncapped_size
                    pos_entry_price = entry_price
                    pos_sl = pending_sl
                    pos_entry_bar = i
                    pos_r_mult = r_mult
                    pos_tp1 = pos_entry_price + r_mult * TP_TARGETS[0]
                    pos_tp2 = pos_entry_price + r_mult * TP_TARGETS[1]
                    tp1_hit = False

        # ── Active position management (M1 engine order: SL → TP1 → TP2) ──
        if has_pos:
            # SL check first (pessimistic)
            if bar.l <= pos_sl:
                exit_p = pos_sl * (ONE - EXIT_SLIPPAGE)
                gross = (exit_p - pos_entry_price) * pos_size
                fee = (pos_entry_price + exit_p) * pos_size * FEE_RATE
                net = gross - fee
                pnl = net
                equity += net
                trades.append(Trade(
                    entry_bar=pos_entry_bar, exit_bar=i,
                    entry_price=pos_entry_price, exit_price=exit_p,
                    stop_price=pos_sl, size=pos_size, pnl=pnl,
                    exit_reason="TP1_BE_SL" if tp1_hit else "SL",
                    r_multiple=pos_r_mult,
                    hold_bars=i - pos_entry_bar,
                    uncapped_size=pos_uncapped_size,
                ))
                has_pos = False
            else:
                # TP1: move SL to BE (NO partial close, matching M1 engine)
                if not tp1_hit and bar.h >= pos_tp1:
                    tp1_hit = True
                    pos_sl = pos_entry_price  # BE stop

                # TP2: close FULL position (matching M1 engine)
                if tp1_hit and bar.h >= pos_tp2:
                    exit_p = pos_tp2 * (ONE - EXIT_SLIPPAGE)
                    gross = (exit_p - pos_entry_price) * pos_size
                    fee = (pos_entry_price + exit_p) * pos_size * FEE_RATE
                    net = gross - fee
                    pnl = net
                    equity += net
                    trades.append(Trade(
                        entry_bar=pos_entry_bar, exit_bar=i,
                        entry_price=pos_entry_price, exit_price=exit_p,
                        stop_price=pos_sl, size=pos_size, pnl=pnl,
                        exit_reason="TP2", r_multiple=pos_r_mult,
                        hold_bars=i - pos_entry_bar,
                        uncapped_size=pos_uncapped_size,
                    ))
                    has_pos = False

            # Year-end force close
            if has_pos and i == end_idx - 1:
                exit_p = bar.c * (ONE - EXIT_SLIPPAGE)
                gross = (exit_p - pos_entry_price) * pos_size
                fee = (pos_entry_price + exit_p) * pos_size * FEE_RATE
                net = gross - fee
                pnl = net
                equity += net
                trades.append(Trade(
                    entry_bar=pos_entry_bar, exit_bar=i,
                    entry_price=pos_entry_price, exit_price=exit_p,
                    stop_price=pos_sl, size=pos_size, pnl=pnl,
                    exit_reason="EOD", r_multiple=pos_r_mult,
                    hold_bars=i - pos_entry_bar,
                    uncapped_size=pos_uncapped_size,
                ))
                has_pos = False

        # ── Signal detection (only if flat) ──
        if not has_pos and not pending_entry:
            if ema50_1h[i] is not None:
                ema_dist = (bar.c - ema50_1h[i]) / ema50_1h[i]
                if bar.c > ema50_1h[i] and ema_dist >= Decimal("0.005"):
                    ema4h, close4h = get_last_closed_4h_ema(klines_4h, ema60_4h, bar.ts)
                    if ema4h is not None and close4h is not None and close4h > ema4h:
                        atr_val = atr_1h[i] if i < len(atr_1h) else None
                        sl = detect_pinbar_long(bar, atr_val)
                        if sl is not None and sl > ZERO:
                            pending_entry = True
                            pending_sl = sl

        # ── MTM tracking ──
        mtm = equity
        if has_pos:
            unrealized = (bar.c - pos_entry_price) * pos_size
            mtm = equity + unrealized
        mtm_curve.append(mtm)
        peak_mtm = max(peak_mtm, mtm)
        dd = (peak_mtm - mtm) / peak_mtm if peak_mtm > ZERO else ZERO
        max_dd_mtm = max(max_dd_mtm, dd)

    return _build_result(trades, mtm_curve, max_dd_mtm, exposure_rejected)

def _empty_result():
    return {
        "pnl": ZERO, "trades": 0, "wins": 0, "losses": 0,
        "wr": ZERO, "pf": ZERO, "avg_win": ZERO, "avg_loss": ZERO,
        "aw_al": ZERO, "max_dd_mtm": ZERO, "avg_hold_days": ZERO,
        "top1_pnl": ZERO, "top1_pct": ZERO, "top3_pct": ZERO,
        "exposure_rejected": 0, "mtm_curve": [], "trades_detail": [],
        "r_multiples": [],
    }

def _build_result(trades, mtm_curve, max_dd_mtm, exposure_rejected):
    wins = [t for t in trades if t.pnl > ZERO]
    losses = [t for t in trades if t.pnl <= ZERO]
    gw = sum(t.pnl for t in wins) if wins else ZERO
    gl = abs(sum(t.pnl for t in losses)) if losses else ZERO
    pf = gw / gl if gl > ZERO else Decimal("99")
    aw = gw / Decimal(len(wins)) if wins else ZERO
    al = gl / Decimal(len(losses)) if losses else ZERO
    aw_al = aw / al if al > ZERO else Decimal("99")
    total_pnl = sum(t.pnl for t in trades)
    sorted_t = sorted(trades, key=lambda t: t.pnl, reverse=True)
    top1 = sorted_t[0].pnl if sorted_t else ZERO
    top3 = sum(t.pnl for t in sorted_t[:3]) if len(sorted_t) >= 3 else sum(t.pnl for t in sorted_t)
    top1_pct = (top1 / abs(total_pnl) * 100) if total_pnl != ZERO else ZERO
    top3_pct = (top3 / abs(total_pnl) * 100) if total_pnl != ZERO else ZERO
    avg_hold = (sum(t.hold_bars for t in trades) / len(trades) / 24) if trades else ZERO
    return {
        "pnl": total_pnl, "trades": len(trades),
        "wins": len(wins), "losses": len(losses),
        "wr": (Decimal(len(wins)) / Decimal(len(trades)) * 100) if trades else ZERO,
        "pf": pf, "avg_win": aw, "avg_loss": al, "aw_al": aw_al,
        "max_dd_mtm": max_dd_mtm * 100,
        "avg_hold_days": avg_hold,
        "top1_pnl": top1, "top1_pct": top1_pct, "top3_pct": top3_pct,
        "exposure_rejected": exposure_rejected,
        "mtm_curve": [float(m) for m in mtm_curve],
        "trades_detail": [
            {"entry_bar": t.entry_bar, "exit_bar": t.exit_bar,
             "entry": float(t.entry_price), "exit": float(t.exit_price),
             "pnl": float(t.pnl), "reason": t.exit_reason,
             "r_mult": float(t.r_multiple), "hold": t.hold_bars}
            for t in trades
        ],
        "r_multiples": [float(t.r_multiple) for t in trades if t.r_multiple > ZERO],
    }

# ──────────────────────────────────────────────────────────────────────────────
# T1 simulation (adapted from T1-R audit with max_total_exposure)
# ──────────────────────────────────────────────────────────────────────────────
def simulate_t1(
    all_klines: List[Kline],
    year_start_idx: int,
    year_end_idx: int,
    atr: List[Optional[Decimal]],
    max_loss_pct: Decimal = Decimal("0.01"),
    max_total_exposure: Decimal = Decimal("2.0"),
    donchian_lookback: int = DONCHIAN_LOOKBACK,
    initial_stop_mult: Decimal = INITIAL_STOP_ATR_MULT,
    trailing_mult: Decimal = TRAILING_ATR_MULT,
) -> Dict:
    """T1 simulation with max_total_exposure cap. Anti-lookahead verified."""
    warmup = donchian_lookback + 14
    if year_start_idx < warmup:
        year_start_idx = warmup

    trades: List[Trade] = []
    equity = INITIAL_BALANCE
    mtm_curve: List[Decimal] = []
    peak_mtm = equity
    max_dd_mtm = ZERO
    exposure_rejected = 0

    has_pos = False
    pending_entry = False
    pending_atr = ZERO

    pos_entry_bar = -1; pos_entry_price = ZERO; pos_stop = ZERO
    pos_atr = ZERO; pos_highest_close = ZERO; pos_size = ZERO
    pos_uncapped_size = ZERO

    for i in range(year_start_idx, year_end_idx):
        bar = all_klines[i]
        current_atr = atr[i - 1] if i > 0 else None

        # Donchian from global klines [i-LB, i-1] (signal bar excluded)
        don_high = max(all_klines[j].h for j in range(i - donchian_lookback, i))

        # Execute pending entry (from PREVIOUS bar's signal)
        if pending_entry and not has_pos:
            pending_entry = False
            entry_price = bar.o * (ONE + ENTRY_SLIPPAGE)
            init_stop = entry_price - initial_stop_mult * pending_atr
            risk_dist = entry_price - init_stop
            if risk_dist > ZERO:
                size = (equity * max_loss_pct) / risk_dist
                max_size = (equity * max_total_exposure) / entry_price
                uncapped_size = size
                if size > max_size:
                    size = max_size
                    exposure_rejected += 1
                if size > ZERO:
                    has_pos = True
                    pos_entry_bar = i; pos_entry_price = entry_price
                    pos_stop = init_stop; pos_atr = pending_atr
                    pos_highest_close = bar.c; pos_size = size
                    pos_uncapped_size = uncapped_size

        # Active position: check stop THEN update trailing
        if has_pos:
            if bar.l <= pos_stop:
                exit_p = pos_stop * (ONE - EXIT_SLIPPAGE)
                pnl = (exit_p - pos_entry_price) * pos_size
                fee = (pos_entry_price + exit_p) * pos_size * FEE_RATE
                net = pnl - fee
                equity += net
                r_mult = pos_entry_price - pos_stop + pos_atr * initial_stop_mult  # approx R
                trades.append(Trade(
                    entry_bar=pos_entry_bar, exit_bar=i,
                    entry_price=pos_entry_price, exit_price=exit_p,
                    stop_price=pos_stop, size=pos_size, pnl=net,
                    exit_reason="trailing_stop", r_multiple=pos_atr * initial_stop_mult,
                    hold_bars=i - pos_entry_bar, uncapped_size=pos_uncapped_size,
                ))
                has_pos = False
            else:
                pos_highest_close = max(pos_highest_close, bar.c)
                new_trail = pos_highest_close - trailing_mult * pos_atr
                pos_stop = max(pos_stop, new_trail)

        # New entry signal (only if flat)
        if not has_pos and not pending_entry and current_atr is not None and current_atr > ZERO:
            if bar.c > don_high:
                pending_entry = True
                pending_atr = current_atr

        # MTM tracking
        mtm = equity
        if has_pos:
            unrealized = (bar.c - pos_entry_price) * pos_size
            mtm = equity + unrealized
        mtm_curve.append(mtm)
        peak_mtm = max(peak_mtm, mtm)
        dd = (peak_mtm - mtm) / peak_mtm if peak_mtm > ZERO else ZERO
        max_dd_mtm = max(max_dd_mtm, dd)

    # Force close open position
    if has_pos:
        last = all_klines[year_end_idx - 1]
        exit_p = last.c * (ONE - EXIT_SLIPPAGE)
        pnl = (exit_p - pos_entry_price) * pos_size
        fee = (pos_entry_price + exit_p) * pos_size * FEE_RATE
        net = pnl - fee
        equity += net
        trades.append(Trade(
            entry_bar=pos_entry_bar, exit_bar=year_end_idx - 1,
            entry_price=pos_entry_price, exit_price=exit_p,
            stop_price=pos_stop, size=pos_size, pnl=net,
            exit_reason="force_close", r_multiple=pos_atr * initial_stop_mult,
            hold_bars=year_end_idx - 1 - pos_entry_bar,
            uncapped_size=pos_uncapped_size,
        ))
        mtm_curve[-1] = equity

    return _build_result(trades, mtm_curve, max_dd_mtm, exposure_rejected)

# ──────────────────────────────────────────────────────────────────────────────
# Metrics & profiles
# ──────────────────────────────────────────────────────────────────────────────
def compute_portfolio_yearly(
    pinbar_yearly: Dict, t1_yearly: Dict, w_pb: float, w_t1: float
) -> Dict:
    """Combine two strategy yearly results with portfolio weights."""
    result = {}
    for y in pinbar_yearly:
        if y not in t1_yearly:
            continue
        pb = pinbar_yearly[y]
        t1 = t1_yearly[y]
        combined_pnl = float(pb["pnl"]) * w_pb + float(t1["pnl"]) * w_t1
        combined_trades = pb["trades"] + t1["trades"]
        combined_mtm = _combine_mtm_curves(
            pb.get("mtm_curve", []), t1.get("mtm_curve", []),
            w_pb, w_t1
        )
        # MaxDD from combined curve
        peak = float(INITIAL_BALANCE)
        max_dd = 0.0
        for m in combined_mtm:
            if m > peak:
                peak = m
            dd = (peak - m) / peak if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
        result[y] = {
            "pnl": combined_pnl,
            "trades": combined_trades,
            "max_dd_mtm": max_dd * 100,
            "mtm_curve": combined_mtm,
        }
    return result

def _combine_mtm_curves(pb_curve, t1_curve, w_pb, w_t1):
    """Combine two MTM curves with portfolio weights."""
    if not pb_curve and not t1_curve:
        return []
    maxlen = max(len(pb_curve), len(t1_curve))
    combined = []
    for i in range(maxlen):
        m_pb = pb_curve[i] * w_pb if i < len(pb_curve) else float(INITIAL_BALANCE) * w_pb
        m_t1 = t1_curve[i] * w_t1 if i < len(t1_curve) else float(INITIAL_BALANCE) * w_t1
        combined.append(m_pb + m_t1)
    return combined

def compute_annual_returns(yearly: Dict) -> List[float]:
    returns = []
    for y in sorted(yearly):
        pnl = float(yearly[y]["pnl"])
        returns.append(pnl / 10000.0)
    return returns

def sharpe_ratio(returns: List[float]) -> float:
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    std = var ** 0.5
    return mean / std if std > 0 else 0.0

def sortino_ratio(returns: List[float]) -> float:
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    downside = [r for r in returns if r < 0]
    if not downside:
        return float('inf') if mean > 0 else 0.0
    var = sum(r ** 2 for r in downside) / len(downside)
    std = var ** 0.5
    return mean / std if std > 0 else 0.0

def compute_max_losing_streak(trades_detail: List[Dict]) -> int:
    streak = 0
    max_streak = 0
    for t in trades_detail:
        if t["pnl"] <= 0:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    return max_streak

def compute_profile(yearly: Dict, strategy_label: str, exposure: float, risk: float) -> Dict:
    """Compute a single configuration's metrics."""
    years = sorted(yearly.keys())
    if not years:
        return {}
    total_pnl = sum(float(yearly[y]["pnl"]) for y in years)
    total_trades = sum(yearly[y].get("trades", 0) for y in years)
    returns = compute_annual_returns(yearly)

    # CAGR
    n_years = len(years)
    final_equity = 10000.0 + total_pnl
    cagr = (final_equity / 10000.0) ** (1.0 / n_years) - 1.0 if n_years > 0 and final_equity > 0 else -1.0

    # MaxDD across years (from combined MTM curve)
    all_mtm = []
    for y in years:
        all_mtm.extend(yearly[y].get("mtm_curve", []))
    peak = 10000.0
    max_dd_pct = 0.0
    for m in all_mtm:
        if m > peak:
            peak = m
        dd = (peak - m) / peak if peak > 0 else 0
        if dd > max_dd_pct:
            max_dd_pct = dd

    # Yearly MaxDD (max of yearly)
    yearly_dd = max((float(yearly[y].get("max_dd_mtm", 0)) for y in years), default=0)

    calmar = total_pnl / (max_dd_pct * 10000) if max_dd_pct > 0 else 99.0
    worst_year_pnl = min(float(yearly[y]["pnl"]) for y in years)
    worst_year = [y for y in years if float(yearly[y]["pnl"]) == worst_year_pnl][0]

    # Collect all trades detail
    all_trades = []
    for y in years:
        all_trades.extend(yearly[y].get("trades_detail", []))
    max_streak = compute_max_losing_streak(all_trades)
    all_trades_sorted = sorted(all_trades, key=lambda t: t["pnl"], reverse=True)
    top1 = all_trades_sorted[0]["pnl"] if all_trades_sorted else 0
    top3 = sum(t["pnl"] for t in all_trades_sorted[:3])
    top1_pct = (top1 / abs(total_pnl) * 100) if total_pnl != 0 else 0
    top3_pct = (top3 / abs(total_pnl) * 100) if total_pnl != 0 else 0
    fragile = top1_pct > 30

    return {
        "strategy": strategy_label,
        "exposure": exposure, "risk_pct": risk,
        "total_pnl": round(total_pnl, 2),
        "cagr": round(cagr * 100, 2),
        "max_dd_pct": round(max_dd_pct * 100, 2),
        "calmar": round(calmar, 2),
        "sharpe": round(sharpe_ratio(returns), 2),
        "sortino": round(sortino_ratio(returns), 2),
        "total_trades": total_trades,
        "worst_year": worst_year, "worst_year_pnl": round(worst_year_pnl, 2),
        "max_losing_streak": max_streak,
        "top1_pct": round(top1_pct, 1), "top3_pct": round(top3_pct, 1),
        "fragile": fragile,
        "yearly_pnl": {y: round(float(yearly[y]["pnl"]), 2) for y in years},
        "exposure_rejected_total": sum(yearly[y].get("exposure_rejected", 0) for y in years),
    }

# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────
async def main():
    print("=" * 80)
    print("R0: RISK / EXPOSURE UPSIDE SCAN")
    print("=" * 80)

    # ── Load data ──
    repo = HistoricalDataRepository(DB_PATH)
    await repo.initialize()

    raw_1h = await repo.get_klines(symbol=SYMBOL, timeframe=TIMEFRAME_1H, limit=100000)
    raw_1h.sort(key=lambda k: k.timestamp)
    raw_4h = await repo.get_klines(symbol=SYMBOL, timeframe=TIMEFRAME_4H, limit=50000)
    raw_4h.sort(key=lambda k: k.timestamp)
    print(f"Loaded: {len(raw_1h)} 1h bars, {len(raw_4h)} 4h bars")

    # Convert to Kline with global indices
    klines_1h = [Kline(idx=i, ts=k.timestamp, o=k.open, h=k.high, l=k.low, c=k.close, v=k.volume)
                 for i, k in enumerate(raw_1h)]
    klines_4h = [Kline(idx=i, ts=k.timestamp, o=k.open, h=k.high, l=k.low, c=k.close, v=k.volume)
                 for i, k in enumerate(raw_4h)]

    # Year boundaries
    years = [2022, 2023, 2024, 2025, 2026]
    year_ts = {y: YEAR_STARTS[y] for y in years}
    year_idx_4h = {}
    for y in years:
        idx = next((k.idx for k in klines_4h if k.ts >= YEAR_STARTS[y]), len(klines_4h))
        year_idx_4h[y] = idx
    year_idx_4h_end = {}
    for y in years:
        next_y = y + 1
        if next_y in YEAR_STARTS:
            end_idx = next((k.idx for k in klines_4h if k.ts >= YEAR_STARTS[next_y]), len(klines_4h))
        else:
            end_idx = len(klines_4h)
        year_idx_4h_end[y] = end_idx
    print("Year ranges (4h):", {y: f"[{year_idx_4h[y]}..{year_idx_4h_end[y]-1}] ({year_idx_4h_end[y]-year_idx_4h[y]} bars)" for y in years})

    # ── Pre-compute indicators ──
    print("Computing indicators...")
    ema50_1h = compute_ema_on_klines(klines_1h, EMA_1H_PERIOD)
    ema60_4h = compute_ema_on_klines(klines_4h, EMA_4H_PERIOD)
    atr_1h = compute_atr_full(klines_1h, ATR_PERIOD)
    atr_4h = compute_atr_full(klines_4h, ATR_PERIOD)
    print("  Done.")

    # ── Scan grid ──
    exposure_levels = [1.0, 1.5, 2.0, 2.5, 3.0]
    risk_levels = [0.005, 0.01, 0.015, 0.02]
    portfolio_weights = [(1.0, 0.0), (0.8, 0.2), (0.7, 0.3), (0.6, 0.4), (0.5, 0.5)]
    scan_years = [2023, 2024, 2025]

    all_configs = []  # List of profile dicts
    pb_cache: Dict[Tuple[float, float], Dict] = {}
    t1_cache: Dict[Tuple[float, float], Dict] = {}

    total_runs = len(exposure_levels) * len(risk_levels) * 2  # Pinbar + T1
    print(f"\nRunning {total_runs} simulation configurations...")

    run_count = 0
    for exp in exposure_levels:
        for risk in risk_levels:
            exp_d = Decimal(str(exp))
            risk_d = Decimal(str(risk))
            run_count += 1

            # Pinbar
            pb_yearly = {}
            for y in scan_years:
                r = simulate_pinbar(
                    klines_1h, klines_4h, ema50_1h, ema60_4h, atr_1h,
                    year_ts[y], year_ts.get(y + 1, year_ts[2026]),
                    max_loss_pct=risk_d, max_total_exposure=exp_d,
                )
                pb_yearly[str(y)] = r
            pb_cache[(exp, risk)] = pb_yearly

            # T1
            t1_yearly = {}
            for y in scan_years:
                s_idx = year_idx_4h[y]
                e_idx = year_idx_4h_end[y]
                r = simulate_t1(
                    klines_4h, s_idx, e_idx, atr_4h,
                    max_loss_pct=risk_d, max_total_exposure=exp_d,
                )
                t1_yearly[str(y)] = r
            t1_cache[(exp, risk)] = t1_yearly

            # Print progress
            pb_pnl = sum(float(pb_yearly[y]["pnl"]) for y in pb_yearly)
            t1_pnl = sum(float(t1_yearly[y]["pnl"]) for y in t1_yearly)
            print(f"  [{run_count}/{len(exposure_levels)*len(risk_levels)}] "
                  f"exp={exp:.1f} risk={risk*100:.1f}% → "
                  f"Pinbar={pb_pnl:+.0f} T1={t1_pnl:+.0f}")

    # ── Build all configuration profiles ──
    print("\nBuilding configuration profiles...")
    for exp in exposure_levels:
        for risk in risk_levels:
            pb_yearly = pb_cache[(exp, risk)]
            t1_yearly = t1_cache[(exp, risk)]

            # Pinbar standalone
            all_configs.append(compute_profile(pb_yearly, "Pinbar", exp, risk))
            # T1 standalone
            all_configs.append(compute_profile(t1_yearly, "T1", exp, risk))

            # Portfolio combinations
            for w_pb, w_t1 in portfolio_weights:
                if w_pb == 1.0:  # Already handled as Pinbar standalone
                    continue
                if w_t1 == 1.0:  # Already handled as T1 standalone
                    continue
                combo_yearly = compute_portfolio_yearly(pb_yearly, t1_yearly, w_pb, w_t1)
                label = f"Portfolio {int(w_pb*100)}/{int(w_t1*100)}"
                all_configs.append(compute_profile(combo_yearly, label, exp, risk))

    print(f"Total configurations: {len(all_configs)}")

    # ── Select 3 profiles ──
    print("\nSelecting profiles...")
    valid = [c for c in all_configs if c.get("total_pnl", 0) > 0]
    if not valid:
        print("  WARNING: No profitable configurations found!")
        profiles = {"aggressive": {}, "balanced": {}, "conservative": {}}
    else:
        # Aggressive: highest PnL
        aggressive = max(valid, key=lambda c: c["total_pnl"])
        # Balanced: best Calmar (PnL / MaxDD)
        balanced = max(valid, key=lambda c: c.get("calmar", 0))
        # Conservative: MaxDD < 10%, highest PnL
        conservative_candidates = [c for c in valid if c.get("max_dd_pct", 100) < 10.0]
        if conservative_candidates:
            conservative = max(conservative_candidates, key=lambda c: c["total_pnl"])
        else:
            conservative = min(valid, key=lambda c: c.get("max_dd_pct", 100))
        profiles = {"aggressive": aggressive, "balanced": balanced, "conservative": conservative}

    for name, p in profiles.items():
        if p:
            print(f"  {name}: {p['strategy']} exp={p['exposure']} risk={p['risk_pct']*100:.1f}% "
                  f"PnL={p['total_pnl']:+.0f} MaxDD={p['max_dd_pct']:.1f}% Calmar={p.get('calmar',0):.1f}")

    # ── Pinbar proxy verification ──
    # Compare baseline (exp=2.0, risk=0.01) with known engine results
    pb_base = pb_cache.get((2.0, 0.01))
    t1_base = t1_cache.get((2.0, 0.01))
    verification = {}
    if pb_base:
        verification["pinbar_proxy"] = {y: round(float(pb_base[y]["pnl"]), 2) for y in pb_base}
        verification["pinbar_engine_ref"] = {"2023": -3924, "2024": 8501, "2025": 4490}
        print("\n  Pinbar proxy vs engine reference:")
        for y in sorted(pb_base):
            proxy_pnl = float(pb_base[y]["pnl"])
            ref = verification["pinbar_engine_ref"].get(y, 0)
            print(f"    {y}: proxy={proxy_pnl:+.0f}  engine={ref:+.0f}  Δ={proxy_pnl-ref:+.0f}")
    if t1_base:
        verification["t1_proxy"] = {y: round(float(t1_base[y]["pnl"]), 2) for y in t1_base}
        verification["t1_audit_ref"] = {"2023": 1358, "2024": 335, "2025": 256}
        print("\n  T1 proxy vs audit reference:")
        for y in sorted(t1_base):
            proxy_pnl = float(t1_base[y]["pnl"])
            ref = verification["t1_audit_ref"].get(y, 0)
            print(f"    {y}: proxy={proxy_pnl:+.0f}  audit={ref:+.0f}  Δ={proxy_pnl-ref:+.0f}")

    # ── Leverage analysis (from baseline R-multiples) ──
    print("\nLeverage analysis (from baseline R-multiples):")
    for label, cache in [("Pinbar", pb_base), ("T1", t1_base)]:
        if not cache:
            continue
        all_r = []
        for y in cache:
            all_r.extend(cache[y].get("r_multiples", []))
        if not all_r:
            continue
        all_r.sort()
        n = len(all_r)
        p50_r = all_r[n // 2]
        p90_r = all_r[int(n * 0.9)]
        max_r = all_r[-1]
        # Leverage at 1% risk: lev = 0.01 * entry_price / R
        # Approximate entry_price ~ 2000 (ETH)
        entry_approx = 2000.0
        risk_ref = 0.01
        lev_p50 = risk_ref * entry_approx / p50_r if p50_r > 0 else 0
        lev_p90 = risk_ref * entry_approx / p90_r if p90_r > 0 else 0
        lev_max = risk_ref * entry_approx / max_r if max_r > 0 else 0
        print(f"  {label}: R-multiple p50={p50_r:.2f} p90={p90_r:.2f} max={max_r:.2f}")
        print(f"    Required leverage @ 1% risk: p50={lev_p50:.1f}x p90={lev_p90:.1f}x max={lev_max:.1f}x")
        over_5x = sum(1 for r in all_r if risk_ref * entry_approx / r > 5.0)
        print(f"    Trades requiring >5x leverage: {over_5x}/{n} ({over_5x/n*100:.0f}%)")

    # ── Save JSON ──
    out_path = PROJECT_ROOT / OUTPUT_JSON
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Top 20 configs by PnL
    top20 = sorted(all_configs, key=lambda c: c.get("total_pnl", 0), reverse=True)[:20]
    # All Pinbar standalone configs
    pb_configs = [c for c in all_configs if c["strategy"] == "Pinbar"]
    t1_configs = [c for c in all_configs if c["strategy"] == "T1"]
    portfolio_configs = [c for c in all_configs if "Portfolio" in c.get("strategy", "")]

    payload = {
        "meta": {
            "scan": "R0 Risk/Exposure Upside Scan",
            "date": "2026-04-28",
            "symbol": SYMBOL,
            "years": [str(y) for y in scan_years],
            "exposure_levels": exposure_levels,
            "risk_levels_pct": [r * 100 for r in risk_levels],
            "portfolio_weights": [(f"{int(w[0]*100)}/{int(w[1]*100)}") for w in portfolio_weights],
            "initial_balance": str(INITIAL_BALANCE),
            "note": "Motivational ceiling scan. Not for live deployment. Use scaling approximation for MaxDD.",
        },
        "verification": verification,
        "profiles": profiles,
        "top20_by_pnl": top20,
        "pinbar_grid": pb_configs,
        "t1_grid": t1_configs,
        "portfolio_grid": portfolio_configs,
    }
    out_path.write_text(json.dumps(payload, indent=2, default=str))
    print(f"\nSaved: {out_path}")

    await repo.close()
    print("\nDone.")
    return profiles, all_configs, verification

if __name__ == "__main__":
    asyncio.run(main())
