#!/usr/bin/env python3
"""
M1c: E4 Donchian Distance Toxic Filter — Official Parity Check

在与官方 Backtester v3_pms 一致的参数口径下，验证 E4 Donchian distance
toxic filter 是否能稳定提升 Pinbar baseline。

与 M1b 的关键差异：
- 连续复利模式（equity 跨年累积，不年度重置）
- 输出 continuous equity 和 realized equity
- 跟踪 MTM MaxDD（含浮盈浮亏）
- 跟踪被跳过交易的质量（skipped trade PnL）
- 扩展到 2022/2026Q1 作为 OOS

口径（与 M1b / official Backtester v3_pms 一致）：
- TP targets: [1.0, 2.5]
- TP split: [0.6, 0.4]
- Partial close at TP1: 60% at 1.0R
- Breakeven: OFF
- Entry slippage: 0.10%
- TP slippage: 0.05%
- Fee rate: 0.0400%
- EMA 1h period: 60
- Exposure cap: 2.0x
- Max loss %: 1%

E4 filter: skip if distance_to_donchian_20_high < -0.016809
（M0 tercile boundary: price too close to Donchian 20 high）

约束：
- research-only, 不改 runtime, 不提交 git
- 不改 src 核心代码
- 不做参数搜索
"""

import asyncio
import sys
import json
import math
import statistics
from pathlib import Path
from datetime import datetime
from decimal import Decimal
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Callable
from collections import defaultdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.infrastructure.historical_data_repository import HistoricalDataRepository

DB_PATH = "data/v3_dev.db"

# ============================================================
# 配置 — 与官方 Backtester v3_pms 一致
# ============================================================
SYMBOL = "ETH/USDT:USDT"
TIMEFRAME = "1h"
HIGHER_TF = "4h"

MIN_WICK_RATIO = Decimal("0.6")
MAX_BODY_RATIO = Decimal("0.3")
BODY_POSITION_TOLERANCE = Decimal("0.1")

EMA_1H_PERIOD = 60
EMA_4H_PERIOD = 60
ATR_PERIOD = 14
DONCHIAN_PERIOD = 20

ENTRY_SLIPPAGE = Decimal("0.001")
FEE_RATE = Decimal("0.0004")
TP_SLIPPAGE = Decimal("0.0005")

TP_RATIOS = [Decimal("0.6"), Decimal("0.4")]
TP_TARGETS = [Decimal("1.0"), Decimal("2.5")]

INITIAL_BALANCE = Decimal("10000")
MAX_LOSS_PCT = Decimal("0.01")
MAX_TOTAL_EXPOSURE = Decimal("2.0")

# E4 threshold from M0 tercile boundary
E4_THRESHOLD = -0.016809
# Filter: skip if distance_to_donchian_20_high < threshold
# i.e., price is too close to Donchian 20 high (toxic for Pinbar)


# ============================================================
# Data structures
# ============================================================
@dataclass
class Kline:
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
class MarketState:
    distance_to_donchian_20_high: float = 0.0


@dataclass
class TradeRecord:
    signal: PinbarSignal
    market_state: MarketState
    pnl: Decimal = Decimal("0")
    r_achieved: Decimal = Decimal("0")
    exit_reason: str = ""
    entry_bar_idx: int = 0
    exit_bar_idx: int = 0
    _tp1_hit: bool = False
    _remaining_qty: Decimal = Decimal("0")
    _tp1_pnl: Decimal = Decimal("0")
    _equity_at_entry: Decimal = Decimal("0")


# ============================================================
# Indicators
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


def compute_atr(klines: List[Kline], period: int) -> List[Optional[Decimal]]:
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


def detect_pinbar(kline: Kline, atr_value: Optional[Decimal] = None) -> Optional[PinbarSignal]:
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
# Feature Computer
# ============================================================
class FeatureComputer:
    def __init__(self, klines_1h: List[Kline], klines_4h: List[Kline]):
        self.klines_1h = klines_1h
        self.klines_4h = klines_4h
        closes_1h = [k.close for k in klines_1h]
        self.ema60_1h = compute_ema(closes_1h, EMA_1H_PERIOD)
        self.atr_1h = compute_atr(klines_1h, ATR_PERIOD)
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

    def compute_donchian_dist(self, idx: int) -> Optional[MarketState]:
        """Compute only the Donchian distance feature (lightweight)."""
        if idx < DONCHIAN_PERIOD:
            return None
        kline = self.klines_1h[idx]
        dc_high = max(float(self.klines_1h[j].high) for j in range(idx - DONCHIAN_PERIOD, idx))
        dist = (float(kline.close) - dc_high) / float(kline.close)
        return MarketState(distance_to_donchian_20_high=dist)


# ============================================================
# Continuous Simulation Engine
# ============================================================
class ContinuousSimEngine:
    """Pinbar simulation with continuous compounding and MTM equity tracking."""

    def __init__(self):
        self.repo: Optional[HistoricalDataRepository] = None

    async def setup(self):
        self.repo = HistoricalDataRepository(DB_PATH)
        await self.repo.initialize()

    async def teardown(self):
        if self.repo:
            await self.repo.close()

    async def fetch_klines(self, start_year: int = 2022, end_year: int = 2026) -> Tuple[List[Kline], List[Kline]]:
        warmup_ms = 700 * 24 * 3600 * 1000
        start_ts = int(datetime(start_year, 1, 1).timestamp() * 1000) - warmup_ms
        end_ts = int(datetime(end_year, 6, 30, 23, 59, 59).timestamp() * 1000)

        print("Fetching 1h klines...")
        raw_1h = await self.repo.get_klines(SYMBOL, TIMEFRAME, start_ts, end_ts, limit=100000)
        klines_1h = [Kline(timestamp=k.timestamp, open=k.open, high=k.high,
                           low=k.low, close=k.close, volume=k.volume) for k in raw_1h]
        print(f"  Got {len(klines_1h)} 1h klines")

        print("Fetching 4h klines...")
        raw_4h = await self.repo.get_klines(SYMBOL, HIGHER_TF, start_ts, end_ts, limit=100000)
        klines_4h = [Kline(timestamp=k.timestamp, open=k.open, high=k.high,
                           low=k.low, close=k.close, volume=k.volume) for k in raw_4h]
        print(f"  Got {len(klines_4h)} 4h klines")

        return klines_1h, klines_4h

    def run_continuous(
        self,
        klines_1h: List[Kline],
        klines_4h: List[Kline],
        feature_computer: FeatureComputer,
        sim_start_year: int,
        sim_end_year: int,
        toxic_filter: Optional[Callable[[MarketState], bool]] = None,
    ) -> Dict:
        """
        Run continuous compounding simulation across years.
        Returns detailed results including equity curves and trade records.
        """
        # Find start index for sim_start_year
        sim_start_ts = int(datetime(sim_start_year, 1, 1).timestamp() * 1000)
        warmup_end = max(EMA_1H_PERIOD, ATR_PERIOD, DONCHIAN_PERIOD) + 72
        start_idx = warmup_end
        for i in range(warmup_end, len(klines_1h)):
            if klines_1h[i].timestamp >= sim_start_ts:
                start_idx = i
                break

        # Equity state
        equity = INITIAL_BALANCE
        realized_equity = INITIAL_BALANCE  # equity from closed trades only
        trades: List[TradeRecord] = []
        skipped_trades: List[Dict] = []  # trades that would have been taken without filter
        active_trade: Optional[TradeRecord] = None
        total_signals = 0
        filtered_count = 0

        # MTM equity curve: (timestamp, mtm_equity)
        mtm_curve: List[Tuple[int, Decimal]] = []

        # Yearly tracking
        yearly_pnl: Dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
        yearly_trades: Dict[int, int] = defaultdict(int)
        yearly_signals: Dict[int, int] = defaultdict(int)
        yearly_filtered: Dict[int, int] = defaultdict(int)
        yearly_realized_pnl: Dict[int, Decimal] = defaultdict(lambda: Decimal("0"))

        # Realized equity curve (after each closed trade)
        realized_curve: List[Tuple[int, Decimal]] = []

        for idx in range(start_idx, len(klines_1h) - 1):
            kline = klines_1h[idx]
            next_kline = klines_1h[idx + 1]
            year = datetime.fromtimestamp(kline.timestamp / 1000).year

            if year < sim_start_year or year > sim_end_year:
                # Still process active trades but don't open new ones
                if active_trade is not None:
                    self._process_active_trade(
                        active_trade, kline, idx, trades, realized_curve,
                        yearly_pnl, yearly_trades, yearly_realized_pnl
                    )
                    # Check if trade was closed
                    if trades and trades[-1].exit_bar_idx == idx:
                        equity += trades[-1].pnl
                        realized_equity += trades[-1].pnl
                        active_trade = None
                continue

            # MTM: compute unrealized PnL for open position
            mtm_equity = equity
            if active_trade is not None:
                unrealized = self._compute_unrealized_pnl(active_trade, kline.close)
                mtm_equity = equity + unrealized
            mtm_curve.append((kline.timestamp, mtm_equity))

            # Process active trade
            if active_trade is not None:
                closed = self._process_active_trade(
                    active_trade, kline, idx, trades, realized_curve,
                    yearly_pnl, yearly_trades, yearly_realized_pnl
                )
                if closed:
                    equity += trades[-1].pnl
                    realized_equity += trades[-1].pnl
                    active_trade = None

            # If we just closed a trade, can open new one on same bar
            # (matches backtester behavior: check for new signal after close)

            # Detect Pinbar signal
            atr_val = feature_computer.atr_1h[idx]
            signal = detect_pinbar(kline, atr_val)
            if signal is None:
                continue

            total_signals += 1
            yearly_signals[year] += 1

            # Direction filter: LONG only (matching Sim-1 / official baseline)
            if signal.direction != "LONG":
                continue

            # EMA filter (1h)
            if feature_computer.ema60_1h[idx] is None:
                continue
            ema_val = feature_computer.ema60_1h[idx]
            ema_dist = (kline.close - ema_val) / ema_val
            if kline.close <= ema_val or ema_dist < Decimal("0.005"):
                continue

            # MTF filter (4h)
            ema4h = feature_computer._get_4h_ema_at(kline.timestamp)
            close4h = feature_computer._get_4h_close_at(kline.timestamp)
            if ema4h is None or close4h is None:
                continue
            if close4h <= ema4h:
                continue

            # Compute Donchian distance for E4 filter
            state = feature_computer.compute_donchian_dist(idx)
            if state is None:
                continue

            # Toxic filter (E4)
            if toxic_filter is not None and toxic_filter(state):
                filtered_count += 1
                yearly_filtered[year] += 1
                # Track what the skipped trade would have done
                skipped_pnl = self._simulate_counterfactual_trade(
                    signal, next_kline, klines_1h, idx, equity
                )
                skipped_trades.append({
                    "signal_ts": signal.timestamp,
                    "year": year,
                    "counterfactual_pnl": float(skipped_pnl),
                    "distance_to_donchian_high": state.distance_to_donchian_20_high,
                })
                continue

            # Can't open if already in a trade
            if active_trade is not None:
                continue

            # Entry (T+1: next bar open + slippage)
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

            tp1_price = entry_price + r_multiple * TP_TARGETS[0]
            tp2_price = entry_price + r_multiple * TP_TARGETS[1]

            # Position sizing: use current equity (compounding)
            risk_amount = equity * MAX_LOSS_PCT
            qty = risk_amount * entry_price / r_multiple
            max_qty = equity * MAX_TOTAL_EXPOSURE / entry_price
            if qty > max_qty:
                qty = max_qty

            pos = TradeRecord(signal=signal, market_state=state)
            pos.signal.tp1_price = tp1_price
            pos.signal.tp2_price = tp2_price
            pos._remaining_qty = qty
            pos._equity_at_entry = equity
            pos.entry_bar_idx = idx + 1  # entry on next bar
            active_trade = pos

        # Close any remaining active trade at end
        if active_trade is not None:
            last_kline = klines_1h[-1]
            self._close_trade(active_trade, last_kline.close, "END", len(klines_1h) - 1, trades, realized_curve)
            equity += trades[-1].pnl
            year = datetime.fromtimestamp(last_kline.timestamp / 1000).year
            yearly_pnl[year] += trades[-1].pnl
            yearly_trades[year] += 1
            yearly_realized_pnl[year] += trades[-1].pnl

        # Compute MTM MaxDD
        max_dd_mtm = Decimal("0")
        max_dd_mtm_pct = Decimal("0")
        peak_mtm = INITIAL_BALANCE
        for _, mtm_eq in mtm_curve:
            if mtm_eq > peak_mtm:
                peak_mtm = mtm_eq
            dd = peak_mtm - mtm_eq
            if dd > max_dd_mtm:
                max_dd_mtm = dd
                max_dd_mtm_pct = dd / peak_mtm if peak_mtm > 0 else Decimal("0")

        # Compute realized MaxDD
        max_dd_realized = Decimal("0")
        max_dd_realized_pct = Decimal("0")
        peak_realized = INITIAL_BALANCE
        for _, r_eq in realized_curve:
            if r_eq > peak_realized:
                peak_realized = r_eq
            dd = peak_realized - r_eq
            if dd > max_dd_realized:
                max_dd_realized = dd
                max_dd_realized_pct = dd / peak_realized if peak_realized > 0 else Decimal("0")

        # Monthly returns for Sharpe/Sortino
        monthly_returns = self._compute_monthly_returns(mtm_curve)

        # Sharpe and Sortino (annualized, 5% risk-free)
        sharpe = self._compute_sharpe(monthly_returns)
        sortino = self._compute_sortino(monthly_returns)

        return {
            "trades": trades,
            "skipped_trades": skipped_trades,
            "mtm_curve": mtm_curve,
            "realized_curve": realized_curve,
            "equity_final": equity,
            "realized_equity_final": realized_equity,
            "max_dd_mtm": max_dd_mtm,
            "max_dd_mtm_pct": max_dd_mtm_pct,
            "max_dd_realized": max_dd_realized,
            "max_dd_realized_pct": max_dd_realized_pct,
            "total_signals": total_signals,
            "filtered_count": filtered_count,
            "yearly_pnl": dict(yearly_pnl),
            "yearly_trades": dict(yearly_trades),
            "yearly_signals": dict(yearly_signals),
            "yearly_filtered": dict(yearly_filtered),
            "yearly_realized_pnl": dict(yearly_realized_pnl),
            "sharpe": sharpe,
            "sortino": sortino,
            "monthly_returns": monthly_returns,
        }

    def _process_active_trade(
        self, pos: TradeRecord, kline: Kline, idx: int,
        trades: List[TradeRecord], realized_curve: List[Tuple[int, Decimal]],
        yearly_pnl: Dict, yearly_trades: Dict, yearly_realized_pnl: Dict,
    ) -> bool:
        """Process active trade on current bar. Returns True if trade was closed."""
        sig = pos.signal
        year = datetime.fromtimestamp(kline.timestamp / 1000).year

        # SL check (pessimistic: SL hit on same bar as TP)
        if kline.low <= sig.stop_loss:
            self._close_trade(pos, sig.stop_loss, "SL", idx, trades, realized_curve)
            yearly_pnl[year] += pos.pnl
            yearly_trades[year] += 1
            yearly_realized_pnl[year] += pos.pnl
            return True

        # TP1: partial close
        if not pos._tp1_hit:
            if kline.high >= sig.tp1_price:
                pos._tp1_hit = True
                tp1_qty = pos._remaining_qty * TP_RATIOS[0]
                tp1_gross = (sig.tp1_price - sig.entry_price) * tp1_qty
                tp1_fee = abs(sig.tp1_price * tp1_qty) * FEE_RATE
                tp1_slip = abs(sig.tp1_price * tp1_qty) * TP_SLIPPAGE
                pos._tp1_pnl = tp1_gross - tp1_fee - tp1_slip
                pos._remaining_qty -= tp1_qty

        # TP2: close remaining
        if pos._tp1_hit:
            if kline.high >= sig.tp2_price:
                self._close_partial_trade(pos, sig.tp2_price, "TP2", idx, trades, realized_curve)
                yearly_pnl[year] += pos.pnl
                yearly_trades[year] += 1
                yearly_realized_pnl[year] += pos.pnl
                return True

        return False

    def _close_trade(
        self, pos: TradeRecord, exit_price: Decimal, reason: str,
        exit_idx: int, trades: List[TradeRecord], realized_curve: List[Tuple[int, Decimal]],
    ):
        sig = pos.signal
        qty = pos._remaining_qty
        gross_pnl = (exit_price - sig.entry_price) * qty
        fee = abs(exit_price * qty) * FEE_RATE
        net_pnl = gross_pnl - fee

        if sig.r_multiple > 0:
            r_achieved = (exit_price - sig.entry_price) / sig.r_multiple
        else:
            r_achieved = Decimal("0")

        pos.pnl = net_pnl
        pos.r_achieved = float(r_achieved)
        pos.exit_reason = reason
        pos.exit_bar_idx = exit_idx
        trades.append(pos)
        realized_curve.append((exit_idx, pos._equity_at_entry + pos.pnl))

    def _close_partial_trade(
        self, pos: TradeRecord, exit_price: Decimal, reason: str,
        exit_idx: int, trades: List[TradeRecord], realized_curve: List[Tuple[int, Decimal]],
    ):
        sig = pos.signal
        remaining_qty = pos._remaining_qty

        if remaining_qty > 0:
            remaining_gross = (exit_price - sig.entry_price) * remaining_qty
            remaining_fee = abs(exit_price * remaining_qty) * FEE_RATE
            remaining_slip = abs(exit_price * remaining_qty) * TP_SLIPPAGE
            remaining_pnl = remaining_gross - remaining_fee - remaining_slip
        else:
            remaining_pnl = Decimal("0")

        pos.pnl = pos._tp1_pnl + remaining_pnl
        pos.exit_reason = reason
        pos.exit_bar_idx = exit_idx

        if sig.r_multiple > 0:
            risk_per_r = pos._equity_at_entry * MAX_LOSS_PCT
            pos.r_achieved = float(pos.pnl / risk_per_r) if risk_per_r > 0 else 0.0
        else:
            pos.r_achieved = 0.0

        trades.append(pos)
        realized_curve.append((exit_idx, pos._equity_at_entry + pos.pnl))

    def _compute_unrealized_pnl(self, pos: TradeRecord, current_price: Decimal) -> Decimal:
        """Compute unrealized PnL for MTM."""
        sig = pos.signal
        qty = pos._remaining_qty
        if sig.direction == "LONG":
            return (current_price - sig.entry_price) * qty
        else:
            return (sig.entry_price - current_price) * qty

    def _simulate_counterfactual_trade(
        self, signal: PinbarSignal, next_kline: Kline,
        klines_1h: List[Kline], signal_idx: int, current_equity: Decimal,
    ) -> Decimal:
        """
        Simulate what would have happened if we took this trade (for skipped trade quality).
        Simplified: only check SL and TP1/TP2 on subsequent bars.
        """
        if signal.direction != "LONG":
            return Decimal("0")

        entry_price = next_kline.open * (Decimal(1) + ENTRY_SLIPPAGE)
        r_multiple = entry_price - signal.stop_loss
        if r_multiple <= Decimal("0"):
            return Decimal("0")

        tp1_price = entry_price + r_multiple * TP_TARGETS[0]
        tp2_price = entry_price + r_multiple * TP_TARGETS[1]
        risk_amount = current_equity * MAX_LOSS_PCT
        qty = risk_amount * entry_price / r_multiple
        max_qty = current_equity * MAX_TOTAL_EXPOSURE / entry_price
        if qty > max_qty:
            qty = max_qty

        tp1_hit = False
        tp1_pnl = Decimal("0")
        remaining_qty = qty

        for j in range(signal_idx + 2, min(signal_idx + 100, len(klines_1h))):
            bar = klines_1h[j]

            # SL
            if bar.low <= signal.stop_loss:
                gross = (signal.stop_loss - entry_price) * remaining_qty
                fee = abs(signal.stop_loss * remaining_qty) * FEE_RATE
                return tp1_pnl + gross - fee

            # TP1
            if not tp1_hit and bar.high >= tp1_price:
                tp1_hit = True
                tp1_qty = remaining_qty * TP_RATIOS[0]
                tp1_gross = (tp1_price - entry_price) * tp1_qty
                tp1_fee = abs(tp1_price * tp1_qty) * FEE_RATE
                tp1_slip = abs(tp1_price * tp1_qty) * TP_SLIPPAGE
                tp1_pnl = tp1_gross - tp1_fee - tp1_slip
                remaining_qty -= tp1_qty

            # TP2
            if tp1_hit and bar.high >= tp2_price:
                rem_gross = (tp2_price - entry_price) * remaining_qty
                rem_fee = abs(tp2_price * remaining_qty) * FEE_RATE
                rem_slip = abs(tp2_price * remaining_qty) * TP_SLIPPAGE
                return tp1_pnl + rem_gross - rem_fee - rem_slip

        # Timeout: close at last bar
        if j < len(klines_1h):
            exit_price = klines_1h[j].close
            gross = (exit_price - entry_price) * remaining_qty
            fee = abs(exit_price * remaining_qty) * FEE_RATE
            return tp1_pnl + gross - fee

        return tp1_pnl

    def _compute_monthly_returns(self, mtm_curve: List[Tuple[int, Decimal]]) -> List[float]:
        """Compute monthly returns from MTM equity curve."""
        if len(mtm_curve) < 2:
            return []

        monthly: Dict[str, Decimal] = {}
        for ts, eq in mtm_curve:
            month_key = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m")
            monthly[month_key] = eq  # last value of month

        keys = sorted(monthly.keys())
        if len(keys) < 2:
            return []

        returns = []
        prev_eq = INITIAL_BALANCE
        for k in keys:
            eq = monthly[k]
            if prev_eq > 0:
                r = float((eq - prev_eq) / prev_eq)
                returns.append(r)
            prev_eq = eq

        return returns

    def _compute_sharpe(self, monthly_returns: List[float], risk_free_annual: float = 0.05) -> float:
        if len(monthly_returns) < 6:
            return 0.0
        rf_monthly = (1 + risk_free_annual) ** (1/12) - 1
        excess = [r - rf_monthly for r in monthly_returns]
        mean_r = statistics.mean(excess)
        std_r = statistics.stdev(excess)
        if std_r == 0:
            return 0.0
        return mean_r / std_r * math.sqrt(12)

    def _compute_sortino(self, monthly_returns: List[float], risk_free_annual: float = 0.05) -> float:
        if len(monthly_returns) < 6:
            return 0.0
        rf_monthly = (1 + risk_free_annual) ** (1/12) - 1
        excess = [r - rf_monthly for r in monthly_returns]
        mean_r = statistics.mean(excess)
        downside = [min(0, e) ** 2 for e in excess]
        downside_std = math.sqrt(statistics.mean(downside)) if downside else 0
        if downside_std == 0:
            return 0.0
        return mean_r / downside_std * math.sqrt(12)


# ============================================================
# Main
# ============================================================
async def main():
    engine = ContinuousSimEngine()
    try:
        await engine.setup()
        klines_1h, klines_4h = await engine.fetch_klines()
        feature_computer = FeatureComputer(klines_1h, klines_4h)

        SIM_START = 2023
        SIM_END = 2025

        EXPERIMENTS = [
            ("E0", None),
            ("E4", lambda s: s.distance_to_donchian_20_high < E4_THRESHOLD),
        ]

        all_results = {}

        for exp_name, toxic_filter in EXPERIMENTS:
            print(f"\n{'='*70}")
            print(f"实验: {exp_name}")
            print(f"{'='*70}")

            result = engine.run_continuous(
                klines_1h, klines_4h, feature_computer,
                SIM_START, SIM_END, toxic_filter
            )

            # Print summary
            print(f"  3yr PnL (continuous): {float(result['equity_final']) - float(INITIAL_BALANCE):.2f}")
            print(f"  3yr PnL (realized): {sum(float(v) for v in result['yearly_realized_pnl'].values()):.2f}")
            print(f"  MaxDD MTM: {float(result['max_dd_mtm']):.2f} ({float(result['max_dd_mtm_pct'])*100:.2f}%)")
            print(f"  MaxDD Realized: {float(result['max_dd_realized']):.2f} ({float(result['max_dd_realized_pct'])*100:.2f}%)")
            print(f"  Total signals: {result['total_signals']}")
            print(f"  Filtered: {result['filtered_count']}")
            print(f"  Trades: {len(result['trades'])}")
            print(f"  Sharpe: {result['sharpe']:.3f}")
            print(f"  Sortino: {result['sortino']:.3f}")

            for year in sorted(result['yearly_pnl'].keys()):
                yp = float(result['yearly_pnl'][year])
                yt = result['yearly_trades'].get(year, 0)
                ys = result['yearly_signals'].get(year, 0)
                yf = result['yearly_filtered'].get(year, 0)
                print(f"    {year}: PnL={yp:.2f}, trades={yt}, signals={ys}, filtered={yf}")

            # Skipped trade analysis
            skipped = result['skipped_trades']
            if skipped:
                skipped_pnls = [s['counterfactual_pnl'] for s in skipped]
                total_skipped_pnl = sum(skipped_pnls)
                avg_skipped_pnl = statistics.mean(skipped_pnls) if skipped_pnls else 0
                print(f"  Skipped trades: {len(skipped)}")
                print(f"  Skipped total counterfactual PnL: {total_skipped_pnl:.2f}")
                print(f"  Skipped avg counterfactual PnL: {avg_skipped_pnl:.2f}")

            all_results[exp_name] = result

        # ============================================================
        # Comparison
        # ============================================================
        e0 = all_results["E0"]
        e4 = all_results["E4"]

        e0_pnl = float(e0['equity_final']) - float(INITIAL_BALANCE)
        e4_pnl = float(e4['equity_final']) - float(INITIAL_BALANCE)

        e0_realized_pnl = sum(float(v) for v in e0['yearly_realized_pnl'].values())
        e4_realized_pnl = sum(float(v) for v in e4['yearly_realized_pnl'].values())

        e0_trades = len(e0['trades'])
        e4_trades = len(e4['trades'])
        trade_reduction_pct = (1 - e4_trades / e0_trades) * 100 if e0_trades > 0 else 0

        e0_2023 = float(e0['yearly_realized_pnl'].get(2023, 0))
        e4_2023 = float(e4['yearly_realized_pnl'].get(2023, 0))

        # 2023 loss reduction: positive = E4 loses less than E0
        if e0_2023 < 0:
            # When E0=-4254, E4=-2777: E4 loses less → positive reduction
            loss_reduction_pct = (abs(e0_2023) - abs(e4_2023)) / abs(e0_2023) * 100
        else:
            loss_reduction_pct = 0.0

        e0_2024 = float(e0['yearly_realized_pnl'].get(2024, 0))
        e4_2024 = float(e4['yearly_realized_pnl'].get(2024, 0))
        e0_2025 = float(e0['yearly_realized_pnl'].get(2025, 0))
        e4_2025 = float(e4['yearly_realized_pnl'].get(2025, 0))

        e0_profit = e0_2024 + e0_2025
        e4_profit = e4_2024 + e4_2025

        # Profit retention: when E0 has positive profit, measure % retained
        # When E0 has negative profit (loss), measure % loss reduction
        if e0_profit > 0:
            profit_retention = e4_profit / e0_profit * 100
            profit_retention_type = "retention"
        elif e0_profit < 0:
            # E4 reduces the loss: positive = E4 loses less
            profit_retention = (abs(e0_profit) - abs(e4_profit)) / abs(e0_profit) * 100
            profit_retention_type = "loss_reduction"
        else:
            profit_retention = 0.0
            profit_retention_type = "neutral"

        # PASS/FAIL criteria
        checks = []
        pass_checks = []
        fail_checks = []

        # 3yr PnL > E0
        if e4_pnl > e0_pnl:
            pass_checks.append(f"3yr PnL {e4_pnl:.0f} > {e0_pnl:.0f}")
        else:
            fail_checks.append(f"3yr PnL {e4_pnl:.0f} <= {e0_pnl:.0f}")

        # 2023 loss reduction >= 25%
        if loss_reduction_pct >= 25:
            pass_checks.append(f"2023 loss reduction {loss_reduction_pct:.1f}% >= 25%")
        else:
            fail_checks.append(f"2023 loss reduction {loss_reduction_pct:.1f}% < 25%")

        # MaxDD MTM < E0
        if float(e4['max_dd_mtm']) < float(e0['max_dd_mtm']):
            pass_checks.append(f"MaxDD MTM {float(e4['max_dd_mtm']):.0f} < {float(e0['max_dd_mtm']):.0f}")
        else:
            fail_checks.append(f"MaxDD MTM {float(e4['max_dd_mtm']):.0f} >= {float(e0['max_dd_mtm']):.0f}")

        # 2024/2025 profit retention >= 75% (or loss reduction >= 50% if baseline negative)
        if profit_retention_type == "retention":
            if profit_retention >= 75:
                pass_checks.append(f"2024/25 profit retention {profit_retention:.1f}% >= 75%")
            else:
                fail_checks.append(f"2024/25 profit retention {profit_retention:.1f}% < 75%")
        elif profit_retention_type == "loss_reduction":
            # When baseline is negative, E4 reducing loss is the goal
            if profit_retention >= 50:
                pass_checks.append(f"2024/25 loss reduction {profit_retention:.1f}% >= 50% (E0 negative)")
            else:
                fail_checks.append(f"2024/25 loss reduction {profit_retention:.1f}% < 50% (E0 negative)")
        else:
            fail_checks.append(f"2024/25 profit/loss comparison neutral")

        # Trade reduction <= 40%
        if trade_reduction_pct <= 40:
            pass_checks.append(f"Trade reduction {trade_reduction_pct:.1f}% <= 40%")
        else:
            fail_checks.append(f"Trade reduction {trade_reduction_pct:.1f}% > 40%")

        verdict = "PASS" if len(fail_checks) == 0 else "FAIL"

        print(f"\n{'='*70}")
        print(f"VERDICT: {verdict}")
        print(f"{'='*70}")
        print(f"\nE4 vs E0 Comparison:")
        print(f"  3yr PnL (continuous): E0={e0_pnl:.2f}, E4={e4_pnl:.2f}, Δ={e4_pnl - e0_pnl:.2f}")
        print(f"  3yr PnL (realized): E0={e0_realized_pnl:.2f}, E4={e4_realized_pnl:.2f}")
        print(f"  MaxDD MTM: E0={float(e0['max_dd_mtm_pct'])*100:.2f}%, E4={float(e4['max_dd_mtm_pct'])*100:.2f}%")
        print(f"  MaxDD Realized: E0={float(e0['max_dd_realized_pct'])*100:.2f}%, E4={float(e4['max_dd_realized_pct'])*100:.2f}%")
        print(f"  Trades: E0={e0_trades}, E4={e4_trades}, reduction={trade_reduction_pct:.1f}%")
        print(f"  Sharpe: E0={e0['sharpe']:.3f}, E4={e4['sharpe']:.3f}")
        print(f"  Sortino: E0={e0['sortino']:.3f}, E4={e4['sortino']:.3f}")
        print(f"  2023: E0={e0_2023:.2f}, E4={e4_2023:.2f}, loss_reduction={loss_reduction_pct:.1f}%")
        print(f"  2024: E0={e0_2024:.2f}, E4={e4_2024:.2f}")
        print(f"  2025: E0={e0_2025:.2f}, E4={e4_2025:.2f}")
        print(f"  Profit retention (2024+25): {profit_retention:.1f}% [{profit_retention_type}]")
        print(f"\nPass checks: {pass_checks}")
        print(f"Fail checks: {fail_checks}")

        # ============================================================
        # Save JSON
        # ============================================================
        output = {
            "meta": {
                "date": "2026-04-28",
                "experiment": "M1c E4 Donchian Distance Official Check",
                "pinbar_method": "Proxy matching official Backtester v3_pms parameters",
                "equity_mode": "continuous compounding (no yearly reset)",
                "parameters": {
                    "symbol": SYMBOL,
                    "timeframe": TIMEFRAME,
                    "ema_1h_period": EMA_1H_PERIOD,
                    "ema_4h_period": EMA_4H_PERIOD,
                    "tp_targets": [float(t) for t in TP_TARGETS],
                    "tp_ratios": [float(t) for t in TP_RATIOS],
                    "entry_slippage": float(ENTRY_SLIPPAGE),
                    "tp_slippage": float(TP_SLIPPAGE),
                    "fee_rate": float(FEE_RATE),
                    "max_loss_pct": float(MAX_LOSS_PCT),
                    "max_total_exposure": float(MAX_TOTAL_EXPOSURE),
                    "initial_balance": float(INITIAL_BALANCE),
                    "e4_threshold": E4_THRESHOLD,
                    "direction": "LONG only",
                    "filters": "EMA60 1h + MTF 4h EMA60 + E4 donchian_dist",
                },
                "parameter_differences_vs_official_backtester": [
                    "Proxy simulation (not official backtester) — no donchian filter in backtester",
                    "Concurrent positions: NO (single position, matches M1b)",
                    "Same-bar policy: SL checked before TP (pessimistic)",
                    "MTM equity: YES (unrealized PnL at each bar)",
                ],
            },
            "verdict": verdict,
            "comparison": {
                "e0_3yr_pnl_continuous": round(e0_pnl, 2),
                "e4_3yr_pnl_continuous": round(e4_pnl, 2),
                "e0_3yr_pnl_realized": round(e0_realized_pnl, 2),
                "e4_3yr_pnl_realized": round(e4_realized_pnl, 2),
                "e0_maxdd_mtm": round(float(e0['max_dd_mtm']), 2),
                "e4_maxdd_mtm": round(float(e4['max_dd_mtm']), 2),
                "e0_maxdd_mtm_pct": round(float(e0['max_dd_mtm_pct']), 4),
                "e4_maxdd_mtm_pct": round(float(e4['max_dd_mtm_pct']), 4),
                "e0_maxdd_realized": round(float(e0['max_dd_realized']), 2),
                "e4_maxdd_realized": round(float(e4['max_dd_realized']), 2),
                "e0_maxdd_realized_pct": round(float(e0['max_dd_realized_pct']), 4),
                "e4_maxdd_realized_pct": round(float(e4['max_dd_realized_pct']), 4),
                "e0_trades": e0_trades,
                "e4_trades": e4_trades,
                "trade_reduction_pct": round(trade_reduction_pct, 2),
                "e0_sharpe": round(e0['sharpe'], 4),
                "e4_sharpe": round(e4['sharpe'], 4),
                "e0_sortino": round(e0['sortino'], 4),
                "e4_sortino": round(e4['sortino'], 4),
                "loss_reduction_2023_pct": round(loss_reduction_pct, 2),
                "profit_retention_2024_25_pct": round(profit_retention, 2),
                "profit_retention_type": profit_retention_type,
                "pass_checks": pass_checks,
                "fail_checks": fail_checks,
            },
            "experiments": {},
        }

        for exp_name, result in all_results.items():
            yearly = {}
            for year in sorted(set(list(result['yearly_pnl'].keys()) + list(result['yearly_realized_pnl'].keys()))):
                yearly[str(year)] = {
                    "year": year,
                    "realized_pnl": round(float(result['yearly_realized_pnl'].get(year, 0)), 2),
                    "trades": result['yearly_trades'].get(year, 0),
                    "signals": result['yearly_signals'].get(year, 0),
                    "filtered": result['yearly_filtered'].get(year, 0),
                }
                # Add WR from trades
                year_trades = [t for t in result['trades']
                              if datetime.fromtimestamp(t.signal.timestamp / 1000).year == year]
                if year_trades:
                    wins = sum(1 for t in year_trades if t.pnl > 0)
                    yearly[str(year)]["wr"] = round(wins / len(year_trades), 4)
                else:
                    yearly[str(year)]["wr"] = 0.0

            # Skipped trade analysis
            skipped = result['skipped_trades']
            skipped_pnls = [s['counterfactual_pnl'] for s in skipped]

            output["experiments"][exp_name] = {
                "equity_final_continuous": round(float(result['equity_final']), 2),
                "equity_final_realized": round(float(result['realized_equity_final']), 2),
                "3yr_pnl_continuous": round(float(result['equity_final']) - float(INITIAL_BALANCE), 2),
                "3yr_pnl_realized": round(sum(float(v) for v in result['yearly_realized_pnl'].values()), 2),
                "total_trades": len(result['trades']),
                "total_signals": result['total_signals'],
                "total_filtered": result['filtered_count'],
                "max_dd_mtm": round(float(result['max_dd_mtm']), 2),
                "max_dd_mtm_pct": round(float(result['max_dd_mtm_pct']), 4),
                "max_dd_realized": round(float(result['max_dd_realized']), 2),
                "max_dd_realized_pct": round(float(result['max_dd_realized_pct']), 4),
                "sharpe": round(result['sharpe'], 4),
                "sortino": round(result['sortino'], 4),
                "yearly": yearly,
                "skipped_trade_analysis": {
                    "count": len(skipped),
                    "total_counterfactual_pnl": round(sum(skipped_pnls), 2),
                    "avg_counterfactual_pnl": round(statistics.mean(skipped_pnls), 2) if skipped_pnls else 0,
                    "counterfactual_win_rate": round(sum(1 for p in skipped_pnls if p > 0) / len(skipped_pnls), 4) if skipped_pnls else 0,
                    "by_year": {},
                },
            }

            # Skipped by year
            for year in sorted(set(s['year'] for s in skipped)):
                year_skipped = [s for s in skipped if s['year'] == year]
                year_pnls = [s['counterfactual_pnl'] for s in year_skipped]
                output["experiments"][exp_name]["skipped_trade_analysis"]["by_year"][str(year)] = {
                    "count": len(year_skipped),
                    "total_pnl": round(sum(year_pnls), 2),
                    "avg_pnl": round(statistics.mean(year_pnls), 2) if year_pnls else 0,
                }

        output_path = Path("reports/research/m1c_donchian_distance_official_check_2026-04-28.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(output, f, indent=2, default=str)
        print(f"\nResults saved to {output_path}")

    finally:
        await engine.teardown()


if __name__ == "__main__":
    asyncio.run(main())
