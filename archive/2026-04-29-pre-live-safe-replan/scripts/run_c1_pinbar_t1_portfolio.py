#!/usr/bin/env python3
"""
C1: Pinbar + T1 Portfolio Proxy — 组合价值验证

约束：
- research-only，不改 src，不改 runtime，不提交 git
- 不做参数搜索，不改单策略参数
- Pinbar 使用当前 Research baseline 口径 (E0, M1 proxy params)
- T1-R 使用修正后版本（无 lookahead）

组合方式：
- 基于逐 bar MTM equity curve（mark-to-market，含浮盈浮亏）
- 权重：P100_T0, P80_T20, P70_T30, P60_T40, P50_T50
- Portfolio Equity = w_P × Pinbar_Equity + w_T × T1_Equity

口径标注：
- Pinbar: 1h bar MTM equity, single-position, fixed INITIAL_BALANCE, no partial close
- T1-R: 4h bar MTM equity, single-position, trailing stop
- 组合: 4h bar frequency（对齐到较粗粒度）
"""

import asyncio
import json
import sys
import math
import statistics
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
from collections import defaultdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.infrastructure.historical_data_repository import HistoricalDataRepository

# ============================================================
# T1-R Configuration (unchanged from run_t1r_audit.py)
# ============================================================
T1_SYMBOL = "ETH/USDT:USDT"
T1_TIMEFRAME = "4h"
DB_PATH = "data/v3_dev.db"
ONE = Decimal("1")
ZERO = Decimal("0")

YEAR_STARTS = {
    2022: 1640995200000,
    2023: 1672531200000,
    2024: 1704067200000,
    2025: 1735689600000,
    2026: 1767225600000,
}

# ============================================================
# Pinbar Configuration (unchanged from M1 proxy)
# ============================================================
PB_SYMBOL = "ETH/USDT:USDT"
PB_TIMEFRAME = "1h"
PB_HIGHER_TF = "4h"

MIN_WICK_RATIO = Decimal("0.6")
MAX_BODY_RATIO = Decimal("0.3")
BODY_POSITION_TOLERANCE = Decimal("0.1")

EMA_1H_PERIOD = 50
EMA_4H_PERIOD = 60
ATR_PERIOD = 14
DONCHIAN_PERIOD = 20

ENTRY_SLIPPAGE = Decimal("0.0001")
FEE_RATE = Decimal("0.000405")
TP_SLIPPAGE = Decimal("0")

TP_RATIOS = [Decimal("0.5"), Decimal("0.5")]
TP_TARGETS = [Decimal("1.0"), Decimal("3.5")]

INITIAL_BALANCE_PB = Decimal("10000")
MAX_LOSS_PCT = Decimal("0.01")
MAX_TOTAL_EXPOSURE = Decimal("2.0")


# ============================================================
# T1-R Data Structures
# ============================================================
@dataclass
class Kline:
    idx: int
    ts: int
    o: Decimal
    h: Decimal
    l: Decimal
    c: Decimal
    v: Decimal


@dataclass
class Trade:
    entry_bar: int
    exit_bar: int
    entry_price: Decimal
    exit_price: Decimal
    stop_price: Decimal
    size: Decimal
    pnl: Decimal
    exit_reason: str
    entry_atr: Decimal
    highest_close: Decimal
    entry_ts: int = 0
    exit_ts: int = 0


# ============================================================
# Pinbar Data Structures
# ============================================================
@dataclass
class PinbarKline:
    timestamp: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


@dataclass
class PinbarSignal:
    idx: int
    timestamp: int
    direction: str
    wick_ratio: Decimal
    body_ratio: Decimal
    entry_price: Decimal
    stop_loss: Decimal
    r_multiple: Decimal
    score: Decimal
    tp1_price: Decimal = Decimal("0")
    tp2_price: Decimal = Decimal("0")


@dataclass
class PinbarTrade:
    signal: PinbarSignal
    pnl: Decimal = Decimal("0")
    r_achieved: Decimal = Decimal("0")
    exit_reason: str = ""
    _tp1_hit: bool = False


# ============================================================
# T1-R ATR (Wilder's)
# ============================================================
def compute_atr_full(klines: List[Kline], period: int = 14) -> List[Optional[Decimal]]:
    n = len(klines)
    atr: List[Optional[Decimal]] = [None] * n
    if n < period + 1:
        return atr
    trs = []
    for i in range(1, n):
        tr = max(
            klines[i].h - klines[i].l,
            abs(klines[i].h - klines[i - 1].c),
            abs(klines[i].l - klines[i - 1].c),
        )
        trs.append(tr)
    first_atr = sum(trs[:period]) / Decimal(period)
    atr[period] = first_atr
    for i in range(period + 1, n):
        atr[i] = (atr[i - 1] * Decimal(period - 1) + trs[i - 1]) / Decimal(period)
    return atr


# ============================================================
# T1-R Simulation (anti-lookahead fixed)
# ============================================================
def simulate_t1(
    all_klines: List[Kline],
    year_start_idx: int,
    year_end_idx: int,
    atr: List[Optional[Decimal]],
    donchian_lookback: int = 20,
    initial_stop_mult: Decimal = Decimal("2"),
    trailing_mult: Decimal = Decimal("3"),
    max_loss_pct: Decimal = Decimal("0.01"),
    fee_rate: Decimal = Decimal("0.000405"),
    entry_slippage: Decimal = Decimal("0.0001"),
    exit_slippage: Decimal = Decimal("0.0001"),
) -> Dict:
    """T1-R simulation returning trades, MTM curve, and metrics."""
    warmup = donchian_lookback + 14
    trades: List[Trade] = []
    equity = Decimal("10000")
    peak_equity = equity
    max_dd_realized = Decimal("0")

    mtm_equity_curve: List[Decimal] = []
    mtm_timestamps: List[int] = []
    peak_mtm = equity
    max_dd_mtm = Decimal("0")

    pos_entry_bar = -1
    pos_entry_price = ZERO
    pos_stop = ZERO
    pos_atr = ZERO
    pos_highest_close = ZERO
    pos_size = ZERO
    has_pos = False

    pending_entry = False
    pending_atr = ZERO
    pending_don_low = ZERO

    for i in range(year_start_idx, year_end_idx):
        bar = all_klines[i]
        current_atr = atr[i - 1] if i > 0 else None

        don_high = max(all_klines[j].h for j in range(i - donchian_lookback, i))
        don_low = min(all_klines[j].l for j in range(i - donchian_lookback, i))

        if pending_entry and not has_pos:
            pending_entry = False
            entry_price = bar.o * (ONE + entry_slippage)
            init_stop = entry_price - initial_stop_mult * pending_atr
            risk_dist = entry_price - init_stop
            if risk_dist > ZERO:
                size = (equity * max_loss_pct) / risk_dist
                pos_entry_bar = i
                pos_entry_price = entry_price
                pos_stop = init_stop
                pos_atr = pending_atr
                pos_highest_close = bar.c
                pos_size = size
                has_pos = True

        if has_pos:
            if bar.l <= pos_stop:
                exit_p = pos_stop * (ONE - exit_slippage)
                pnl = (exit_p - pos_entry_price) * pos_size
                fee = (pos_entry_price + exit_p) * pos_size * fee_rate
                net_pnl = pnl - fee
                equity += net_pnl
                trades.append(Trade(
                    entry_bar=pos_entry_bar, exit_bar=i,
                    entry_price=pos_entry_price, exit_price=exit_p,
                    stop_price=pos_stop, size=pos_size,
                    pnl=net_pnl, exit_reason="trailing_stop",
                    entry_atr=pos_atr, highest_close=pos_highest_close,
                    entry_ts=all_klines[pos_entry_bar].ts,
                    exit_ts=bar.ts,
                ))
                has_pos = False
            else:
                pos_highest_close = max(pos_highest_close, bar.c)
                new_trail = pos_highest_close - trailing_mult * pos_atr
                pos_stop = max(pos_stop, new_trail)

        if not has_pos and not pending_entry and current_atr is not None and current_atr > ZERO:
            if bar.c > don_high:
                pending_entry = True
                pending_atr = current_atr
                pending_don_low = don_low

        peak_equity = max(peak_equity, equity)
        dd_r = (peak_equity - equity) / peak_equity if peak_equity > ZERO else ZERO
        max_dd_realized = max(max_dd_realized, dd_r)

        mtm = equity
        if has_pos:
            unrealized = (bar.c - pos_entry_price) * pos_size
            mtm = equity + unrealized
        mtm_equity_curve.append(mtm)
        mtm_timestamps.append(bar.ts)
        peak_mtm = max(peak_mtm, mtm)
        dd_m = (peak_mtm - mtm) / peak_mtm if peak_mtm > ZERO else ZERO
        max_dd_mtm = max(max_dd_mtm, dd_m)

    # Force close at year end
    if has_pos:
        last = all_klines[year_end_idx - 1]
        exit_p = last.c * (ONE - exit_slippage)
        pnl = (exit_p - pos_entry_price) * pos_size
        fee = (pos_entry_price + exit_p) * pos_size * fee_rate
        net_pnl = pnl - fee
        equity += net_pnl
        trades.append(Trade(
            entry_bar=pos_entry_bar, exit_bar=year_end_idx - 1,
            entry_price=pos_entry_price, exit_price=exit_p,
            stop_price=pos_stop, size=pos_size,
            pnl=net_pnl, exit_reason="force_close",
            entry_atr=pos_atr, highest_close=pos_highest_close,
            entry_ts=all_klines[pos_entry_bar].ts,
            exit_ts=last.ts,
        ))
        has_pos = False
        mtm_equity_curve[-1] = equity

    wins = [t for t in trades if t.pnl > ZERO]
    losses = [t for t in trades if t.pnl <= ZERO]
    gross_win = sum(t.pnl for t in wins) if wins else ZERO
    gross_loss = abs(sum(t.pnl for t in losses)) if losses else ZERO
    pf = gross_win / gross_loss if gross_loss > ZERO else Decimal("99")

    return {
        "trades": trades,
        "mtm_curve": [float(m) for m in mtm_equity_curve],
        "mtm_timestamps": mtm_timestamps,
        "pnl": float(equity - Decimal("10000")),
        "trade_count": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "pf": float(pf),
        "max_dd_realized": float(max_dd_realized * 100),
        "max_dd_mtm": float(max_dd_mtm * 100),
    }


# ============================================================
# Pinbar Indicators
# ============================================================
def compute_ema(prices: List[Decimal], period: int) -> List[Optional[Decimal]]:
    if not prices:
        return []
    result: List[Optional[Decimal]] = [None] * len(prices)
    if len(prices) < period:
        return result
    sma = sum(prices[:period]) / Decimal(period)
    result[period - 1] = sma
    k = Decimal(2) / (Decimal(period) + Decimal(1))
    prev = sma
    for i in range(period, len(prices)):
        ema = prices[i] * k + prev * (Decimal(1) - k)
        result[i] = ema
        prev = ema
    return result


def compute_atr_pb(klines: List[PinbarKline], period: int) -> List[Optional[Decimal]]:
    if len(klines) < 2:
        return [None] * len(klines)
    trs: List[Decimal] = []
    for i in range(1, len(klines)):
        tr = max(
            klines[i].high - klines[i].low,
            abs(klines[i].high - klines[i - 1].close),
            abs(klines[i].low - klines[i - 1].close),
        )
        trs.append(tr)
    result: List[Optional[Decimal]] = [None] * len(klines)
    if len(trs) < period:
        return result
    atr = sum(trs[:period]) / Decimal(period)
    result[period] = atr
    for i in range(period, len(trs)):
        atr = (atr * (Decimal(period) - 1) + trs[i]) / Decimal(period)
        result[i + 1] = atr
    return result


def detect_pinbar(kline: PinbarKline, atr_value: Optional[Decimal] = None) -> Optional[PinbarSignal]:
    high = kline.high
    low = kline.low
    close = kline.close
    open_price = kline.open

    candle_range = high - low
    if candle_range == Decimal(0):
        return None

    if atr_value and atr_value > 0:
        min_required_range = atr_value * Decimal("0.1")
    else:
        min_required_range = close * Decimal("0.001")

    if candle_range < min_required_range:
        return None

    body_size = abs(close - open_price)
    body_ratio = body_size / candle_range

    upper_wick = high - max(open_price, close)
    lower_wick = min(open_price, close) - low
    dominant_wick = max(upper_wick, lower_wick)
    wick_ratio = dominant_wick / candle_range

    is_pinbar = (wick_ratio >= MIN_WICK_RATIO and body_ratio <= MAX_BODY_RATIO)
    if not is_pinbar:
        return None

    body_center = (open_price + close) / Decimal(2)
    body_position = (body_center - low) / candle_range

    direction = None
    if dominant_wick == lower_wick:
        if body_position >= (Decimal(1) - BODY_POSITION_TOLERANCE - body_ratio / 2):
            direction = "LONG"
    else:
        if body_position <= (BODY_POSITION_TOLERANCE + body_ratio / 2):
            direction = "SHORT"

    if direction is None:
        return None

    pattern_ratio = wick_ratio
    if atr_value and atr_value > 0:
        atr_ratio = candle_range / atr_value
        base_score = pattern_ratio
        atr_bonus = min(atr_ratio, Decimal("2.0")) * Decimal("0.3")
        score = min(base_score * Decimal("0.7") + atr_bonus, Decimal("1.0"))
    else:
        score = pattern_ratio

    if direction == "LONG":
        stop_loss = low
    else:
        stop_loss = high

    return PinbarSignal(
        idx=0, timestamp=kline.timestamp, direction=direction,
        wick_ratio=wick_ratio, body_ratio=body_ratio,
        entry_price=Decimal("0"), stop_loss=stop_loss,
        r_multiple=Decimal("0"), score=score,
    )


# ============================================================
# Pinbar Feature Computer (from M1)
# ============================================================
class PinbarFeatureComputer:
    def __init__(self, klines_1h: List[PinbarKline], klines_4h: List[PinbarKline]):
        self.klines_1h = klines_1h
        self.klines_4h = klines_4h
        closes_1h = [k.close for k in klines_1h]
        self.ema50_1h = compute_ema(closes_1h, EMA_1H_PERIOD)
        self.atr_1h = compute_atr_pb(klines_1h, ATR_PERIOD)
        closes_4h = [k.close for k in klines_4h]
        self.ema60_4h = compute_ema(closes_4h, EMA_4H_PERIOD)
        self.ema_4h_map: Dict[int, Decimal] = {}
        for i, k in enumerate(klines_4h):
            if self.ema60_4h[i] is not None:
                self.ema_4h_map[k.timestamp] = self.ema60_4h[i]

    def _get_4h_ema_at(self, signal_ts: int) -> Optional[Decimal]:
        last_closed = None
        for k in self.klines_4h:
            candle_close = k.timestamp + 4 * 3600 * 1000
            if candle_close <= signal_ts:
                last_closed = k
            else:
                break
        if last_closed is None:
            return None
        return self.ema_4h_map.get(last_closed.timestamp)

    def _get_4h_close_at(self, signal_ts: int) -> Optional[Decimal]:
        last_closed = None
        for k in self.klines_4h:
            candle_close = k.timestamp + 4 * 3600 * 1000
            if candle_close <= signal_ts:
                last_closed = k
            else:
                break
        return last_closed.close if last_closed else None


# ============================================================
# Pinbar Simulation with MTM Equity Curve
# ============================================================
def simulate_pinbar(
    klines_1h: List[PinbarKline],
    klines_4h: List[PinbarKline],
    year: int,
    fc: PinbarFeatureComputer,
) -> Dict:
    """
    Run Pinbar baseline (E0, no filter) for one year.
    Returns trades, MTM equity curve, and metrics.
    MTM equity computed at each 1h bar.
    """
    year_start_ts = int(datetime(year, 1, 1).timestamp() * 1000)
    start_idx = 0
    for i in range(max(EMA_1H_PERIOD, ATR_PERIOD, DONCHIAN_PERIOD) + 72, len(klines_1h)):
        if klines_1h[i].timestamp >= year_start_ts:
            start_idx = i
            break

    trades: List[PinbarTrade] = []
    active_trade: Optional[PinbarTrade] = None
    realized_pnl = Decimal("0")

    mtm_curve: List[float] = []
    mtm_timestamps: List[int] = []

    for idx in range(start_idx, len(klines_1h) - 1):
        kline = klines_1h[idx]
        next_kline = klines_1h[idx + 1]

        if datetime.fromtimestamp(kline.timestamp / 1000).year != year:
            if active_trade is not None:
                _close_pinbar(active_trade, kline.close, "EOD", trades)
                realized_pnl += active_trade.pnl
                active_trade = None
            mtm_curve.append(float(INITIAL_BALANCE_PB + realized_pnl))
            mtm_timestamps.append(kline.timestamp)
            continue

        # Process active trade
        if active_trade is not None:
            sig = active_trade.signal

            if sig.direction == "LONG" and kline.low <= sig.stop_loss:
                _close_pinbar(active_trade, sig.stop_loss, "SL", trades)
                realized_pnl += active_trade.pnl
                active_trade = None
            elif sig.direction == "SHORT" and kline.high >= sig.stop_loss:
                _close_pinbar(active_trade, sig.stop_loss, "SL", trades)
                realized_pnl += active_trade.pnl
                active_trade = None

        if active_trade is not None:
            sig = active_trade.signal
            # TP1 → move SL to BE
            if not active_trade._tp1_hit:
                if sig.direction == "LONG" and kline.high >= sig.tp1_price:
                    active_trade._tp1_hit = True
                    active_trade.signal.stop_loss = sig.entry_price
                elif sig.direction == "SHORT" and kline.low <= sig.tp1_price:
                    active_trade._tp1_hit = True
                    active_trade.signal.stop_loss = sig.entry_price

            # TP2
            if active_trade._tp1_hit:
                if sig.direction == "LONG" and kline.high >= sig.tp2_price:
                    _close_pinbar(active_trade, sig.tp2_price, "TP2", trades)
                    realized_pnl += active_trade.pnl
                    active_trade = None
                elif sig.direction == "SHORT" and kline.low <= sig.tp2_price:
                    _close_pinbar(active_trade, sig.tp2_price, "TP2", trades)
                    realized_pnl += active_trade.pnl
                    active_trade = None

        if active_trade is not None:
            is_year_end = kline.timestamp >= int(datetime(year, 12, 31, 20, 0, 0).timestamp() * 1000)
            if is_year_end:
                _close_pinbar(active_trade, kline.close, "EOD", trades)
                realized_pnl += active_trade.pnl
                active_trade = None

        # Compute MTM equity
        mtm = INITIAL_BALANCE_PB + realized_pnl
        if active_trade is not None:
            sig = active_trade.signal
            risk_amount = INITIAL_BALANCE_PB * MAX_LOSS_PCT
            qty = risk_amount * sig.entry_price / sig.r_multiple
            max_qty = INITIAL_BALANCE_PB * MAX_TOTAL_EXPOSURE / sig.entry_price
            if qty > max_qty:
                qty = max_qty
            if sig.direction == "LONG":
                unrealized = (kline.close - sig.entry_price) * qty
            else:
                unrealized = (sig.entry_price - kline.close) * qty
            mtm += unrealized

        mtm_curve.append(float(mtm))
        mtm_timestamps.append(kline.timestamp)

        # Detect new pinbar signal
        if active_trade is not None:
            continue

        atr_val = fc.atr_1h[idx]
        signal = detect_pinbar(kline, atr_val)
        if signal is None:
            continue

        # EMA + MTF filter
        if fc.ema50_1h[idx] is None:
            continue
        ema_dist = (kline.close - fc.ema50_1h[idx]) / fc.ema50_1h[idx]
        if kline.close <= fc.ema50_1h[idx] or ema_dist < Decimal("0.005"):
            continue

        ema4h = fc._get_4h_ema_at(kline.timestamp)
        close4h = fc._get_4h_close_at(kline.timestamp)
        if ema4h is None or close4h is None:
            continue
        if signal.direction == "LONG" and close4h <= ema4h:
            continue
        if signal.direction == "SHORT" and close4h >= ema4h:
            continue

        # Entry
        if signal.direction == "LONG":
            entry_price = next_kline.open * (Decimal(1) + ENTRY_SLIPPAGE)
            r_multiple = entry_price - signal.stop_loss
        else:
            entry_price = next_kline.open * (Decimal(1) - ENTRY_SLIPPAGE)
            r_multiple = signal.stop_loss - entry_price

        if r_multiple <= Decimal("0"):
            continue

        signal.entry_price = entry_price
        signal.r_multiple = r_multiple
        signal.idx = idx

        tp1_price = entry_price + r_multiple * TP_TARGETS[0] if signal.direction == "LONG" else entry_price - r_multiple * TP_TARGETS[0]
        tp2_price = entry_price + r_multiple * TP_TARGETS[1] if signal.direction == "LONG" else entry_price - r_multiple * TP_TARGETS[1]
        signal.tp1_price = tp1_price
        signal.tp2_price = tp2_price

        active_trade = PinbarTrade(signal=signal)

    # Close remaining trade
    if active_trade is not None:
        _close_pinbar(active_trade, klines_1h[-1].close, "EOD", trades)
        realized_pnl += active_trade.pnl

    pnls = [float(t.pnl) for t in trades]
    wins = sum(1 for p in pnls if p > 0)
    total_pnl = sum(pnls)

    return {
        "trades": trades,
        "mtm_curve": mtm_curve,
        "mtm_timestamps": mtm_timestamps,
        "pnl": total_pnl,
        "trade_count": len(trades),
        "wins": wins,
        "losses": len(trades) - wins,
    }


def _close_pinbar(pos: PinbarTrade, exit_price: Decimal, reason: str, trades: List[PinbarTrade]):
    sig = pos.signal
    risk_amount = INITIAL_BALANCE_PB * MAX_LOSS_PCT
    qty = risk_amount * sig.entry_price / sig.r_multiple
    max_qty = INITIAL_BALANCE_PB * MAX_TOTAL_EXPOSURE / sig.entry_price
    if qty > max_qty:
        qty = max_qty

    if sig.direction == "LONG":
        gross_pnl = (exit_price - sig.entry_price) * qty
    else:
        gross_pnl = (sig.entry_price - exit_price) * qty

    fee = abs(exit_price * qty) * FEE_RATE
    net_pnl = gross_pnl - fee

    pos.pnl = net_pnl
    pos.exit_reason = reason
    if sig.direction == "LONG":
        pos.r_achieved = (exit_price - sig.entry_price) / sig.r_multiple
    else:
        pos.r_achieved = (sig.entry_price - exit_price) / sig.r_multiple

    trades.append(pos)


# ============================================================
# T1-R Continuous Simulation (no year restart)
# ============================================================
def simulate_t1_continuous(
    all_klines: List[Kline],
    year_start_idx: int,
    year_end_idx: int,
    atr: List[Optional[Decimal]],
    start_equity: Decimal = Decimal("10000"),
    donchian_lookback: int = 20,
    initial_stop_mult: Decimal = Decimal("2"),
    trailing_mult: Decimal = Decimal("3"),
    max_loss_pct: Decimal = Decimal("0.01"),
    fee_rate: Decimal = Decimal("0.000405"),
    entry_slippage: Decimal = Decimal("0.0001"),
    exit_slippage: Decimal = Decimal("0.0001"),
) -> Dict:
    """T1-R continuous simulation — equity compounds across the full range."""
    trades: List[Trade] = []
    equity = start_equity
    peak_equity = equity

    mtm_equity_curve: List[Decimal] = []
    mtm_timestamps: List[int] = []

    pos_entry_bar = -1
    pos_entry_price = ZERO
    pos_stop = ZERO
    pos_atr = ZERO
    pos_highest_close = ZERO
    pos_size = ZERO
    has_pos = False

    pending_entry = False
    pending_atr = ZERO
    pending_don_low = ZERO

    for i in range(year_start_idx, year_end_idx):
        bar = all_klines[i]
        current_atr = atr[i - 1] if i > 0 else None
        don_high = max(all_klines[j].h for j in range(i - donchian_lookback, i))
        don_low = min(all_klines[j].l for j in range(i - donchian_lookback, i))

        if pending_entry and not has_pos:
            pending_entry = False
            entry_price = bar.o * (ONE + entry_slippage)
            init_stop = entry_price - initial_stop_mult * pending_atr
            risk_dist = entry_price - init_stop
            if risk_dist > ZERO:
                size = (equity * max_loss_pct) / risk_dist
                pos_entry_bar = i
                pos_entry_price = entry_price
                pos_stop = init_stop
                pos_atr = pending_atr
                pos_highest_close = bar.c
                pos_size = size
                has_pos = True

        if has_pos:
            if bar.l <= pos_stop:
                exit_p = pos_stop * (ONE - exit_slippage)
                pnl = (exit_p - pos_entry_price) * pos_size
                fee = (pos_entry_price + exit_p) * pos_size * fee_rate
                net_pnl = pnl - fee
                equity += net_pnl
                trades.append(Trade(
                    entry_bar=pos_entry_bar, exit_bar=i,
                    entry_price=pos_entry_price, exit_price=exit_p,
                    stop_price=pos_stop, size=pos_size,
                    pnl=net_pnl, exit_reason="trailing_stop",
                    entry_atr=pos_atr, highest_close=pos_highest_close,
                    entry_ts=all_klines[pos_entry_bar].ts, exit_ts=bar.ts,
                ))
                has_pos = False
            else:
                pos_highest_close = max(pos_highest_close, bar.c)
                new_trail = pos_highest_close - trailing_mult * pos_atr
                pos_stop = max(pos_stop, new_trail)

        if not has_pos and not pending_entry and current_atr is not None and current_atr > ZERO:
            if bar.c > don_high:
                pending_entry = True
                pending_atr = current_atr
                pending_don_low = don_low

        mtm = equity
        if has_pos:
            unrealized = (bar.c - pos_entry_price) * pos_size
            mtm = equity + unrealized
        mtm_equity_curve.append(mtm)
        mtm_timestamps.append(bar.ts)

    if has_pos:
        last = all_klines[year_end_idx - 1]
        exit_p = last.c * (ONE - exit_slippage)
        pnl = (exit_p - pos_entry_price) * pos_size
        fee = (pos_entry_price + exit_p) * pos_size * fee_rate
        net_pnl = pnl - fee
        equity += net_pnl
        trades.append(Trade(
            entry_bar=pos_entry_bar, exit_bar=year_end_idx - 1,
            entry_price=pos_entry_price, exit_price=exit_p,
            stop_price=pos_stop, size=pos_size,
            pnl=net_pnl, exit_reason="force_close",
            entry_atr=pos_atr, highest_close=pos_highest_close,
            entry_ts=all_klines[pos_entry_bar].ts, exit_ts=last.ts,
        ))
        has_pos = False
        mtm_equity_curve[-1] = equity

    return {
        "trades": trades,
        "mtm_curve": [float(m) for m in mtm_equity_curve],
        "mtm_timestamps": mtm_timestamps,
        "final_equity": float(equity),
    }


# ============================================================
# Pinbar Continuous Simulation (no year restart)
# ============================================================
def simulate_pinbar_continuous(
    klines_1h: List[PinbarKline],
    fc: PinbarFeatureComputer,
    start_idx: int,
    end_idx: int,
    start_equity: float = 10000.0,
) -> Dict:
    """
    Pinbar baseline (E0) continuous simulation across the full range.
    Equity compounds; no year-end restart.
    """
    trades: List[PinbarTrade] = []
    active_trade: Optional[PinbarTrade] = None
    realized_pnl = Decimal("0")

    mtm_curve: List[float] = []
    mtm_timestamps: List[int] = []

    for idx in range(start_idx, end_idx):
        kline = klines_1h[idx]
        next_kline = klines_1h[idx + 1] if idx + 1 < len(klines_1h) else kline

        # Process active trade
        if active_trade is not None:
            sig = active_trade.signal

            if sig.direction == "LONG" and kline.low <= sig.stop_loss:
                _close_pinbar(active_trade, sig.stop_loss, "SL", trades)
                realized_pnl += active_trade.pnl
                active_trade = None
            elif sig.direction == "SHORT" and kline.high >= sig.stop_loss:
                _close_pinbar(active_trade, sig.stop_loss, "SL", trades)
                realized_pnl += active_trade.pnl
                active_trade = None

        if active_trade is not None:
            sig = active_trade.signal
            if not active_trade._tp1_hit:
                if sig.direction == "LONG" and kline.high >= sig.tp1_price:
                    active_trade._tp1_hit = True
                    active_trade.signal.stop_loss = sig.entry_price
                elif sig.direction == "SHORT" and kline.low <= sig.tp1_price:
                    active_trade._tp1_hit = True
                    active_trade.signal.stop_loss = sig.entry_price

            if active_trade._tp1_hit:
                if sig.direction == "LONG" and kline.high >= sig.tp2_price:
                    _close_pinbar(active_trade, sig.tp2_price, "TP2", trades)
                    realized_pnl += active_trade.pnl
                    active_trade = None
                elif sig.direction == "SHORT" and kline.low <= sig.tp2_price:
                    _close_pinbar(active_trade, sig.tp2_price, "TP2", trades)
                    realized_pnl += active_trade.pnl
                    active_trade = None

        # Compute MTM
        base = Decimal(str(start_equity))
        mtm = base + realized_pnl
        if active_trade is not None:
            sig = active_trade.signal
            risk_amount = base * MAX_LOSS_PCT
            qty = risk_amount * sig.entry_price / sig.r_multiple
            max_qty = base * MAX_TOTAL_EXPOSURE / sig.entry_price
            if qty > max_qty:
                qty = max_qty
            if sig.direction == "LONG":
                unrealized = (kline.close - sig.entry_price) * qty
            else:
                unrealized = (sig.entry_price - kline.close) * qty
            mtm += unrealized

        mtm_curve.append(float(mtm))
        mtm_timestamps.append(kline.timestamp)

        # Detect new pinbar
        if active_trade is not None:
            continue

        atr_val = fc.atr_1h[idx]
        signal = detect_pinbar(kline, atr_val)
        if signal is None:
            continue

        if fc.ema50_1h[idx] is None:
            continue
        ema_dist = (kline.close - fc.ema50_1h[idx]) / fc.ema50_1h[idx]
        if kline.close <= fc.ema50_1h[idx] or ema_dist < Decimal("0.005"):
            continue

        ema4h = fc._get_4h_ema_at(kline.timestamp)
        close4h = fc._get_4h_close_at(kline.timestamp)
        if ema4h is None or close4h is None:
            continue
        if signal.direction == "LONG" and close4h <= ema4h:
            continue
        if signal.direction == "SHORT" and close4h >= ema4h:
            continue

        if signal.direction == "LONG":
            entry_price = next_kline.open * (Decimal(1) + ENTRY_SLIPPAGE)
            r_multiple = entry_price - signal.stop_loss
        else:
            entry_price = next_kline.open * (Decimal(1) - ENTRY_SLIPPAGE)
            r_multiple = signal.stop_loss - entry_price

        if r_multiple <= Decimal("0"):
            continue

        signal.entry_price = entry_price
        signal.r_multiple = r_multiple
        signal.idx = idx

        tp1_price = entry_price + r_multiple * TP_TARGETS[0] if signal.direction == "LONG" else entry_price - r_multiple * TP_TARGETS[0]
        tp2_price = entry_price + r_multiple * TP_TARGETS[1] if signal.direction == "LONG" else entry_price - r_multiple * TP_TARGETS[1]
        signal.tp1_price = tp1_price
        signal.tp2_price = tp2_price

        active_trade = PinbarTrade(signal=signal)

    if active_trade is not None:
        _close_pinbar(active_trade, klines_1h[end_idx - 1].close, "EOD", trades)
        realized_pnl += active_trade.pnl

    return {
        "trades": trades,
        "mtm_curve": mtm_curve,
        "mtm_timestamps": mtm_timestamps,
        "final_equity": float(Decimal(str(start_equity)) + realized_pnl),
    }


# ============================================================
# Portfolio Metrics (fixed)
# ============================================================
def compute_portfolio_metrics(
    pb_curve: List[float],
    pb_ts: List[int],
    t1_curve: List[float],
    t1_ts: List[int],
    pb_trades: List[Any],
    t1_trades: List[Any],
    weight_pb: float,
    weight_t1: float,
    label: str,
    correlation: float = 0.0,
) -> Dict:
    """Combine equity curves at 4h resolution and compute all metrics."""
    # Build T1 timestamp → equity map
    t1_ts_map = {ts: eq for ts, eq in zip(t1_ts, t1_curve)}

    # Build Pinbar sorted (timestamp, equity) list for lookup
    pb_pairs = sorted(zip(pb_ts, pb_curve))

    combined_ts = []
    combined_eq = []

    for ts in t1_ts:
        if ts not in t1_ts_map:
            continue
        t1_eq = t1_ts_map[ts]
        # Find most recent Pinbar equity at or before this timestamp
        pb_eq = 10000.0
        lo, hi = 0, len(pb_pairs) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            if pb_pairs[mid][0] <= ts:
                pb_eq = pb_pairs[mid][1]
                lo = mid + 1
            else:
                hi = mid - 1

        portfolio_eq = weight_pb * pb_eq + weight_t1 * t1_eq
        combined_ts.append(ts)
        combined_eq.append(portfolio_eq)

    if not combined_eq:
        return {"label": label, "error": "no data"}

    start_eq = combined_eq[0]
    total_pnl = combined_eq[-1] - start_eq

    # Yearly PnL from equity curve
    yearly_pnl = {}
    for year in [2023, 2024, 2025]:
        year_start_ts = YEAR_STARTS[year]
        year_end_ts = YEAR_STARTS.get(year + 1, 9999999999999)
        eq_at_start = None
        eq_at_end = None
        for i, ts in enumerate(combined_ts):
            if ts >= year_start_ts and eq_at_start is None:
                eq_at_start = combined_eq[max(0, i - 1)]
            if ts >= year_end_ts:
                eq_at_end = combined_eq[max(0, i - 1)]
                break
        if eq_at_start is None:
            eq_at_start = combined_eq[0]
        if eq_at_end is None:
            eq_at_end = combined_eq[-1]
        yearly_pnl[year] = eq_at_end - eq_at_start

    # MaxDD
    peak = combined_eq[0]
    max_dd = 0.0
    max_dd_pct = 0.0
    for eq in combined_eq:
        if eq > peak:
            peak = eq
        dd = peak - eq
        dd_pct = dd / peak if peak > 0 else 0
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct
            max_dd = dd

    # Monthly returns
    monthly_returns = _compute_monthly_returns(combined_ts, combined_eq)
    sharpe = _compute_sharpe(monthly_returns)
    sortino = _compute_sortino(monthly_returns)

    # Calmar
    total_return_pct = total_pnl / start_eq if start_eq > 0 else 0
    annualized_return = total_return_pct / 3.0
    calmar = annualized_return / max_dd_pct if max_dd_pct > 0 else float('inf')

    # Worst year
    worst_year = min(yearly_pnl.items(), key=lambda x: x[1]) if yearly_pnl else (0, 0)

    # Monthly positive rate
    monthly_positive = sum(1 for r in monthly_returns if r > 0)
    monthly_total = len(monthly_returns)
    monthly_positive_rate = monthly_positive / monthly_total if monthly_total > 0 else 0

    # T1 top 3 winners
    t1_sorted = sorted(t1_trades, key=lambda t: float(t.pnl), reverse=True)
    t1_top3 = t1_sorted[:3] if len(t1_sorted) >= 3 else t1_sorted
    t1_top3_pnl = sum(float(t.pnl) for t in t1_top3)
    t1_total_pnl = sum(float(t.pnl) for t in t1_trades)
    t1_top3_pct = (t1_top3_pnl / abs(t1_total_pnl) * 100) if t1_total_pnl != 0 else 0

    # Portfolio without T1 top 3
    pb_total_pnl = sum(float(t.pnl) for t in pb_trades)
    t1_pnl_no_top3 = t1_total_pnl - t1_top3_pnl
    portfolio_pnl_no_top3 = weight_pb * pb_total_pnl + weight_t1 * t1_pnl_no_top3

    # Correlation using MTM equity curves (align to weekly, compute returns)
    corr = correlation
    return_std = statistics.stdev(monthly_returns) if len(monthly_returns) > 1 else 0

    return {
        "label": label,
        "weight_pinbar": weight_pb,
        "weight_t1": weight_t1,
        "total_pnl": round(total_pnl, 2),
        "yearly_pnl": {str(k): round(v, 2) for k, v in yearly_pnl.items()},
        "max_dd": round(max_dd, 2),
        "max_dd_pct": round(max_dd_pct * 100, 2),
        "sharpe": round(sharpe, 3),
        "sortino": round(sortino, 3),
        "calmar": round(calmar, 3),
        "worst_year": {"year": worst_year[0], "pnl": round(worst_year[1], 2)},
        "monthly_positive_rate": round(monthly_positive_rate * 100, 1),
        "correlation_pinbar_t1": round(corr, 3),
        "t1_top3_pnl": round(t1_top3_pnl, 2),
        "t1_top3_pct_of_t1": round(t1_top3_pct, 1),
        "portfolio_pnl_no_t1_top3": round(portfolio_pnl_no_top3, 2),
        "return_std_monthly": round(return_std, 4),
    }


def _compute_monthly_returns(timestamps: List[int], equity: List[float]) -> List[float]:
    """Compute monthly returns from equity curve."""
    monthly = {}
    for ts, eq in zip(timestamps, equity):
        dt = datetime.fromtimestamp(ts / 1000)
        key = (dt.year, dt.month)
        monthly[key] = eq  # last value of month

    sorted_months = sorted(monthly.keys())
    returns = []
    for i in range(1, len(sorted_months)):
        prev_eq = monthly[sorted_months[i - 1]]
        cur_eq = monthly[sorted_months[i]]
        if prev_eq > 0:
            returns.append((cur_eq - prev_eq) / prev_eq)
    return returns


def _compute_monthly_returns_from_trades(trades: List[Any], initial_balance: float) -> List[float]:
    """Compute monthly returns from trade list (realized PnL basis)."""
    monthly_pnl = defaultdict(float)
    for t in trades:
        exit_ts = getattr(t, 'exit_ts', None) or getattr(t, 'signal', None)
        if exit_ts and hasattr(exit_ts, 'timestamp'):
            dt = datetime.fromtimestamp(exit_ts.timestamp / 1000)
        elif hasattr(t, 'signal') and hasattr(t.signal, 'timestamp'):
            dt = datetime.fromtimestamp(t.signal.timestamp / 1000)
        else:
            continue
        key = (dt.year, dt.month)
        monthly_pnl[key] += float(t.pnl)

    sorted_months = sorted(monthly_pnl.keys())
    returns = []
    cum = initial_balance
    for m in sorted_months:
        r = monthly_pnl[m] / cum if cum > 0 else 0
        returns.append(r)
        cum += monthly_pnl[m]
    return returns


def _compute_sharpe(returns: List[float], annual_rf: float = 0.05) -> float:
    if len(returns) < 2:
        return 0
    monthly_rf = annual_rf / 12
    excess = [r - monthly_rf for r in returns]
    mean_excess = statistics.mean(excess)
    std = statistics.stdev(returns)
    if std == 0:
        return 0
    return (mean_excess / std) * math.sqrt(12)


def _compute_sortino(returns: List[float], annual_rf: float = 0.05) -> float:
    if len(returns) < 2:
        return 0
    monthly_rf = annual_rf / 12
    excess = [r - monthly_rf for r in returns]
    mean_excess = statistics.mean(excess)
    downside = [min(0, r - monthly_rf) for r in returns]
    downside_var = sum(d ** 2 for d in downside) / len(downside)
    downside_std = math.sqrt(downside_var)
    if downside_std == 0:
        return 0
    return (mean_excess / downside_std) * math.sqrt(12)


def _compute_correlation(x: List[float], y: List[float]) -> float:
    if len(x) < 2 or len(y) < 2:
        return 0
    n = min(len(x), len(y))
    x, y = x[:n], y[:n]
    if len(set(x)) == 0 or len(set(y)) == 0:
        return 0
    try:
        mean_x = statistics.mean(x)
        mean_y = statistics.mean(y)
        cov = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y)) / n
        std_x = statistics.stdev(x)
        std_y = statistics.stdev(y)
        if std_x == 0 or std_y == 0:
            return 0
        return cov / (std_x * std_y)
    except:
        return 0


def _compute_mtm_correlation(
    pb_curve: List[float], pb_ts: List[int],
    t1_curve: List[float], t1_ts: List[int],
) -> float:
    """
    Compute correlation using MTM equity curves aligned to weekly frequency.
    Uses week-ending equity values to compute weekly returns, then correlates.
    """
    # Build sorted pairs
    pb_pairs = sorted(zip(pb_ts, pb_curve))
    t1_pairs = sorted(zip(t1_ts, t1_curve))

    # Get the full time range
    all_ts = sorted(set(pb_ts) | set(t1_ts))
    if not all_ts:
        return 0

    # Group by ISO week (year, week_number)
    weekly_pb = {}
    weekly_t1 = {}

    for ts, eq in pb_pairs:
        dt = datetime.fromtimestamp(ts / 1000)
        key = dt.isocalendar()[:2]  # (year, week)
        weekly_pb[key] = eq

    for ts, eq in t1_pairs:
        dt = datetime.fromtimestamp(ts / 1000)
        key = dt.isocalendar()[:2]
        weekly_t1[key] = eq

    # Compute weekly returns for common weeks
    common_weeks = sorted(set(weekly_pb.keys()) & set(weekly_t1.keys()))
    if len(common_weeks) < 3:
        return 0

    pb_returns = []
    t1_returns = []
    for i in range(1, len(common_weeks)):
        prev_w = common_weeks[i - 1]
        curr_w = common_weeks[i]
        pb_prev = weekly_pb[prev_w]
        pb_curr = weekly_pb[curr_w]
        t1_prev = weekly_t1[prev_w]
        t1_curr = weekly_t1[curr_w]
        if pb_prev > 0 and t1_prev > 0:
            pb_returns.append((pb_curr - pb_prev) / pb_prev)
            t1_returns.append((t1_curr - t1_prev) / t1_prev)

    return _compute_correlation(pb_returns, t1_returns)


# ============================================================
# Main
# ============================================================
async def main():
    print("=" * 80)
    print("C1: Pinbar + T1 Portfolio Proxy")
    print("=" * 80)

    # ── Load data ──
    repo = HistoricalDataRepository(DB_PATH)
    await repo.initialize()

    # T1: 4h klines
    print("\nLoading T1 4h klines...")
    raw_t1 = await repo.get_klines(T1_SYMBOL, T1_TIMEFRAME, limit=50000)
    raw_t1.sort(key=lambda k: k.timestamp)
    t1_klines = [
        Kline(idx=i, ts=k.timestamp, o=k.open, h=k.high, l=k.low, c=k.close, v=k.volume)
        for i, k in enumerate(raw_t1)
    ]
    print(f"  {len(t1_klines)} 4h bars")

    # Pinbar: 1h + 4h klines
    print("Loading Pinbar 1h klines...")
    warmup_ms = 700 * 24 * 3600 * 1000
    start_ts = int(datetime(2022, 1, 1).timestamp() * 1000) - warmup_ms
    end_ts = int(datetime(2025, 12, 31, 23, 59, 59).timestamp() * 1000)

    raw_pb_1h = await repo.get_klines(PB_SYMBOL, PB_TIMEFRAME, start_ts, end_ts, limit=100000)
    pb_klines_1h = [PinbarKline(timestamp=k.timestamp, open=k.open, high=k.high,
                                low=k.low, close=k.close, volume=k.volume) for k in raw_pb_1h]
    print(f"  {len(pb_klines_1h)} 1h bars")

    print("Loading Pinbar 4h klines...")
    raw_pb_4h = await repo.get_klines(PB_SYMBOL, PB_HIGHER_TF, start_ts, end_ts, limit=100000)
    pb_klines_4h = [PinbarKline(timestamp=k.timestamp, open=k.open, high=k.high,
                                low=k.low, close=k.close, volume=k.volume) for k in raw_pb_4h]
    print(f"  {len(pb_klines_4h)} 4h bars")

    await repo.close()

    # ── T1-R: Compute ATR + year ranges ──
    print("\nComputing T1 ATR...")
    t1_atr = compute_atr_full(t1_klines, 14)
    t1_n = len(t1_klines)

    # Find T1 start/end indices for 2023-2025
    t1_start = next((k.idx for k in t1_klines if k.ts >= YEAR_STARTS[2023]), t1_n)
    t1_end = next((k.idx for k in t1_klines if k.ts >= YEAR_STARTS[2026]), t1_n)
    print(f"  T1 range: bars [{t1_start}..{t1_end-1}] ({t1_end - t1_start} bars)")

    # ── Run T1-R continuous simulation ──
    print("\nRunning T1-R continuous simulation...")
    t1_result = simulate_t1_continuous(t1_klines, t1_start, t1_end, t1_atr)
    all_t1_trades = t1_result["trades"]
    all_t1_mtm_curve = t1_result["mtm_curve"]
    all_t1_mtm_ts = t1_result["mtm_timestamps"]

    # T1 yearly PnL from trades
    t1_yearly = {}
    for year in [2023, 2024, 2025]:
        year_trades = [t for t in all_t1_trades
                       if t.entry_ts >= YEAR_STARTS[year] and t.entry_ts < YEAR_STARTS[year + 1]]
        year_pnl = sum(float(t.pnl) for t in year_trades)
        t1_yearly[year] = {"trades": len(year_trades), "pnl": round(year_pnl, 2)}

    t1_3yr_pnl = sum(v["pnl"] for v in t1_yearly.values())
    print(f"  T1 trades: {len(all_t1_trades)}, 3yr PnL: {t1_3yr_pnl:.2f}")
    for y, v in t1_yearly.items():
        print(f"    {y}: trades={v['trades']}, PnL={v['pnl']:.2f}")

    # ── Run Pinbar continuous simulation ──
    print("\nRunning Pinbar baseline (E0) continuous simulation...")
    fc = PinbarFeatureComputer(pb_klines_1h, pb_klines_4h)

    # Find Pinbar start/end for 2023-2025
    pb_warmup = max(EMA_1H_PERIOD, ATR_PERIOD, DONCHIAN_PERIOD) + 72
    pb_start = pb_warmup
    for i in range(pb_warmup, len(pb_klines_1h)):
        if pb_klines_1h[i].timestamp >= YEAR_STARTS[2023]:
            pb_start = i
            break
    pb_end = len(pb_klines_1h) - 1
    for i in range(pb_start, len(pb_klines_1h)):
        if pb_klines_1h[i].timestamp >= YEAR_STARTS[2026]:
            pb_end = i
            break

    print(f"  Pinbar range: bars [{pb_start}..{pb_end}] ({pb_end - pb_start} bars)")

    pb_result = simulate_pinbar_continuous(pb_klines_1h, fc, pb_start, pb_end)
    all_pb_trades = pb_result["trades"]
    all_pb_mtm_curve = pb_result["mtm_curve"]
    all_pb_mtm_ts = pb_result["mtm_timestamps"]

    # Pinbar yearly PnL from trades
    pb_yearly = {}
    for year in [2023, 2024, 2025]:
        year_trades = [t for t in all_pb_trades
                       if t.signal.timestamp >= YEAR_STARTS[year] and t.signal.timestamp < YEAR_STARTS[year + 1]]
        year_pnl = sum(float(t.pnl) for t in year_trades)
        pb_yearly[year] = {"trades": len(year_trades), "pnl": round(year_pnl, 2)}

    pb_3yr_pnl = sum(v["pnl"] for v in pb_yearly.values())
    print(f"  Pinbar trades: {len(all_pb_trades)}, 3yr PnL: {pb_3yr_pnl:.2f}")
    for y, v in pb_yearly.items():
        print(f"    {y}: trades={v['trades']}, PnL={v['pnl']:.2f}")

    # ── Compute correlations ──
    print("\nComputing strategy correlation (MTM weekly returns)...")
    corr = _compute_mtm_correlation(all_pb_mtm_curve, all_pb_mtm_ts,
                                     all_t1_mtm_curve, all_t1_mtm_ts)
    print(f"  Correlation (weekly MTM returns): {corr:.3f}")

    # ── T1 concentration analysis ──
    t1_sorted = sorted(all_t1_trades, key=lambda t: float(t.pnl), reverse=True)
    t1_top3 = t1_sorted[:3] if len(t1_sorted) >= 3 else t1_sorted
    t1_top3_pnl = sum(float(t.pnl) for t in t1_top3)
    t1_total_pnl = sum(float(t.pnl) for t in all_t1_trades)
    t1_top3_pct = (t1_top3_pnl / abs(t1_total_pnl) * 100) if t1_total_pnl != 0 else 0
    print(f"  T1 Top 3 winners: {t1_top3_pnl:.2f} ({t1_top3_pct:.1f}% of T1 PnL)")

    # ── Portfolio combinations ──
    weights = [
        ("P100_T0", 1.0, 0.0),
        ("P80_T20", 0.8, 0.2),
        ("P70_T30", 0.7, 0.3),
        ("P60_T40", 0.6, 0.4),
        ("P50_T50", 0.5, 0.5),
    ]

    results = {}
    print(f"\n{'='*80}")
    print("Portfolio Analysis")
    print(f"{'='*80}")

    for label, w_pb, w_t1 in weights:
        metrics = compute_portfolio_metrics(
            all_pb_mtm_curve, all_pb_mtm_ts,
            all_t1_mtm_curve, all_t1_mtm_ts,
            all_pb_trades, all_t1_trades,
            w_pb, w_t1, label,
            correlation=corr,
        )
        results[label] = metrics

        print(f"\n  {label} (Pinbar {w_pb*100:.0f}% / T1 {w_t1*100:.0f}%):")
        print(f"    3yr PnL:    {metrics['total_pnl']:>10.2f}")
        print(f"    2023:       {metrics['yearly_pnl'].get('2023', 0):>10.2f}")
        print(f"    2024:       {metrics['yearly_pnl'].get('2024', 0):>10.2f}")
        print(f"    2025:       {metrics['yearly_pnl'].get('2025', 0):>10.2f}")
        print(f"    MaxDD:      {metrics['max_dd_pct']:>10.2f}%")
        print(f"    Sharpe:     {metrics['sharpe']:>10.3f}")
        print(f"    Sortino:    {metrics['sortino']:>10.3f}")
        print(f"    Calmar:     {metrics['calmar']:>10.3f}")
        print(f"    Worst Year: {metrics['worst_year']['year']} ({metrics['worst_year']['pnl']:.2f})")
        print(f"    Mo. Pos%:   {metrics['monthly_positive_rate']:>10.1f}%")
        if w_t1 > 0:
            print(f"    T1 Top3%:   {metrics['t1_top3_pct_of_t1']:.1f}% of T1 PnL")
            print(f"    No Top3:    {metrics['portfolio_pnl_no_t1_top3']:.2f}")

    # ── Verdict ──
    print(f"\n{'='*80}")
    print("VERDICT")
    print(f"{'='*80}")

    baseline = results["P100_T0"]
    pb_3yr = baseline["total_pnl"]
    pb_dd = baseline["max_dd_pct"]
    pb_2023 = baseline["yearly_pnl"].get("2023", 0)

    best_combo = None
    best_score = -999

    for label in ["P80_T20", "P70_T30", "P60_T40", "P50_T50"]:
        r = results[label]
        pnl_improved = r["total_pnl"] > pb_3yr
        dd_lower = r["max_dd_pct"] < pb_dd
        y2023_improved = r["yearly_pnl"].get("2023", 0) > pb_2023

        score = 0
        if pnl_improved:
            score += 2
        if dd_lower:
            score += 2
        if y2023_improved:
            score += 1
        if r["correlation_pinbar_t1"] < 0:
            score += 1
        if r["portfolio_pnl_no_t1_top3"] > 0:
            score += 1

        # Penalty for fragility
        if r["t1_top3_pct_of_t1"] > 60:
            score -= 2

        if score > best_score:
            best_score = score
            best_combo = label

    print(f"\n  Pinbar baseline: 3yr PnL={pb_3yr:.2f}, MaxDD={pb_dd:.2f}%")
    print(f"  Correlation: {corr:.3f}")
    print(f"  T1 Top3 concentration: {t1_top3_pct:.1f}%")

    for label in ["P80_T20", "P70_T30", "P60_T40", "P50_T50"]:
        r = results[label]
        verdict_parts = []
        if r["total_pnl"] > pb_3yr:
            verdict_parts.append("PnL↑")
        else:
            verdict_parts.append("PnL↓")
        if r["max_dd_pct"] < pb_dd:
            verdict_parts.append("DD↓")
        else:
            verdict_parts.append("DD↑")
        if r["yearly_pnl"].get("2023", 0) > pb_2023:
            verdict_parts.append("2023↑")
        if r["t1_top3_pct_of_t1"] > 60:
            verdict_parts.append("FRAGILE")
        if r["portfolio_pnl_no_t1_top3"] < 0:
            verdict_parts.append("TOP3-DEPENDENT")
        print(f"  {label}: {', '.join(verdict_parts)}")

    print(f"\n  Best combo candidate: {best_combo} (score={best_score})")

    # ── Save results ──
    output = {
        "meta": {
            "date": "2026-04-28",
            "experiment": "C1 Pinbar + T1 Portfolio Proxy",
            "description": "Portfolio combination of Pinbar baseline (E0, M1 proxy) and T1-R (corrected)",
            "caveats": [
                "Proxy result — not official backtester",
                "Realized PnL equity proxy, not true MTM at 1h resolution for portfolio",
                "Both strategies use single-position fixed balance model",
                "T1-R uses corrected anti-lookahead simulation",
                "Pinbar uses M1 proxy params (TP [1.0, 3.5], no partial close, BE=ON)",
            ],
        },
        "strategies": {
            "pinbar": {
                "3yr_pnl": round(pb_3yr, 2),
                "yearly": {str(k): v for k, v in pb_yearly.items()},
                "total_trades": len(all_pb_trades),
                "correlation_with_t1": round(corr, 3),
            },
            "t1": {
                "3yr_pnl": round(t1_3yr_pnl, 2),
                "yearly": {str(k): v for k, v in t1_yearly.items()},
                "total_trades": len(all_t1_trades),
                "top3_pnl": round(t1_top3_pnl, 2),
                "top3_pct": round(t1_top3_pct, 1),
                "fragile": t1_top3_pct > 60,
            },
        },
        "portfolio": results,
        "verdict": {
            "best_candidate": best_combo,
            "best_score": best_score,
            "pinbar_baseline_3yr": round(pb_3yr, 2),
            "pinbar_baseline_maxdd": round(pb_dd, 2),
        },
    }

    out_path = PROJECT_ROOT / "reports/research/c1_pinbar_t1_portfolio_proxy_2026-04-28.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
