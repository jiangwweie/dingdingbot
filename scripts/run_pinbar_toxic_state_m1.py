#!/usr/bin/env python3
"""
M1: Pinbar Toxic State Avoidance Proxy
验证单个 toxic-state filter 是否能减少 Pinbar 亏损，同时不明显破坏 2024/2025 收益。

约束：
- research-only
- 不改 src 核心代码
- 不改 runtime profile
- 不做参数搜索
- 不提交 git
- 每个实验只应用一个过滤条件，不组合
- 分桶阈值复用 M0 的 tercile boundaries

实验组：
E0：Pinbar baseline（无 filter）
E1：跳过 ema_4h_slope 最高分桶（> 0.215185）
E2：跳过 recent_72h_return 最高分桶（> 0.064538）
E3：跳过 realized_volatility_24h 最高分桶（> 0.007751）
E4：跳过 distance_to_donchian_20_high 最接近顶部（< -0.016809）
"""

import asyncio
import sys
import json
from pathlib import Path
from datetime import datetime
from decimal import Decimal
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any, Callable
from collections import defaultdict
import statistics

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.infrastructure.historical_data_repository import HistoricalDataRepository

DB_PATH = "data/v3_dev.db"

# ============================================================
# 配置（与 M0 完全一致）
# ============================================================
SYMBOL = "ETH/USDT:USDT"
TIMEFRAME = "1h"
HIGHER_TF = "4h"

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

INITIAL_BALANCE = Decimal("10000")
MAX_LOSS_PCT = Decimal("0.01")
MAX_TOTAL_EXPOSURE = Decimal("2.0")

# M0 tercile boundaries（toxic bucket thresholds）
# Each lambda takes a MarketState and returns True if the state is "toxic" (should skip)
TOXIC_THRESHOLDS = {
    "ema_4h_slope": lambda s: s.ema_4h_slope > 0.215185,
    "recent_72h_return": lambda s: s.recent_72h_return > 0.064538,
    "realized_volatility_24h": lambda s: s.realized_volatility_24h > 0.007751,
    "distance_to_donchian_20_high": lambda s: s.distance_to_donchian_20_high < -0.016809,
}


# ============================================================
# 数据结构（复用 M0）
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
    ema_1h_slope: float = 0.0
    ema_4h_slope: float = 0.0
    price_dist_ema50: float = 0.0
    atr_percentile: float = 0.0
    recent_24h_return: float = 0.0
    recent_72h_return: float = 0.0
    realized_volatility_24h: float = 0.0
    range_compression_24h: float = 0.0
    distance_to_donchian_20_high: float = 0.0
    distance_to_donchian_20_low: float = 0.0
    year: int = 0
    signal_ts: int = 0


@dataclass
class TradeRecord:
    signal: PinbarSignal
    market_state: MarketState
    pnl: Decimal = Decimal("0")
    r_achieved: Decimal = Decimal("0")
    exit_reason: str = ""
    holding_bars: int = 0
    _tp1_hit: bool = False


# ============================================================
# 指标计算（复用 M0）
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
# Feature Computer（复用 M0）
# ============================================================
class FeatureComputer:
    def __init__(self, klines_1h: List[Kline], klines_4h: List[Kline]):
        self.klines_1h = klines_1h
        self.klines_4h = klines_4h
        closes_1h = [k.close for k in klines_1h]
        self.ema50_1h = compute_ema(closes_1h, EMA_1H_PERIOD)
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

    def compute(self, idx: int) -> Optional[MarketState]:
        if idx < max(EMA_1H_PERIOD, ATR_PERIOD, DONCHIAN_PERIOD) + 72:
            return None

        kline = self.klines_1h[idx]
        state = MarketState(
            year=datetime.fromtimestamp(kline.timestamp / 1000).year,
            signal_ts=kline.timestamp,
        )

        if self.ema50_1h[idx] is not None and self.ema50_1h[idx - 5] is not None:
            ema_now = float(self.ema50_1h[idx])
            ema_5ago = float(self.ema50_1h[idx - 5])
            state.ema_1h_slope = (ema_now - ema_5ago) / ema_5ago / 5.0 * 100
        else:
            return None

        ema4h_now = self._get_4h_ema_at(kline.timestamp)
        ts_12h_ago = kline.timestamp - 12 * 3600 * 1000
        ema4h_12h = self._get_4h_ema_at(ts_12h_ago)
        if ema4h_now is not None and ema4h_12h is not None:
            state.ema_4h_slope = (float(ema4h_now) - float(ema4h_12h)) / float(ema4h_12h) / 3.0 * 100
        else:
            state.ema_4h_slope = 0.0

        if self.ema50_1h[idx] is not None:
            state.price_dist_ema50 = float((kline.close - self.ema50_1h[idx]) / self.ema50_1h[idx])
        else:
            return None

        if self.atr_1h[idx] is not None:
            window_start = max(0, idx - 500)
            atr_window = [float(self.atr_1h[j]) for j in range(window_start, idx + 1)
                         if self.atr_1h[j] is not None]
            if len(atr_window) > 10:
                state.atr_percentile = sum(1 for a in atr_window if a <= float(self.atr_1h[idx])) / len(atr_window)
            else:
                return None
        else:
            return None

        if idx >= 24:
            state.recent_24h_return = float((kline.close - self.klines_1h[idx - 24].close) / self.klines_1h[idx - 24].close)
        else:
            return None

        if idx >= 72:
            state.recent_72h_return = float((kline.close - self.klines_1h[idx - 72].close) / self.klines_1h[idx - 72].close)
        else:
            return None

        if idx >= 24:
            import math
            returns = []
            for j in range(idx - 23, idx + 1):
                r = float(self.klines_1h[j].close / self.klines_1h[j - 1].close)
                returns.append(math.log(r))
            if len(returns) >= 10:
                state.realized_volatility_24h = statistics.stdev(returns) if len(returns) > 1 else 0.0
            else:
                return None
        else:
            return None

        if idx >= 24 and self.atr_1h[idx] is not None and self.atr_1h[idx] > 0:
            avg_range = sum(float(self.klines_1h[j].high - self.klines_1h[j].low)
                          for j in range(idx - 23, idx + 1)) / 24.0
            state.range_compression_24h = avg_range / float(self.atr_1h[idx])
        else:
            return None

        if idx >= DONCHIAN_PERIOD:
            dc_high = max(float(self.klines_1h[j].high) for j in range(idx - DONCHIAN_PERIOD, idx))
            state.distance_to_donchian_20_high = (float(kline.close) - dc_high) / float(kline.close)
        else:
            return None

        if idx >= DONCHIAN_PERIOD:
            dc_low = min(float(self.klines_1h[j].low) for j in range(idx - DONCHIAN_PERIOD, idx))
            state.distance_to_donchian_20_low = (dc_low - float(kline.close)) / float(kline.close)
        else:
            return None

        return state


# ============================================================
# 撮合引擎
# ============================================================
class ToxicStateEngine:
    def __init__(self):
        self.repo: Optional[HistoricalDataRepository] = None

    async def setup(self):
        self.repo = HistoricalDataRepository(DB_PATH)
        await self.repo.initialize()

    async def teardown(self):
        if self.repo:
            await self.repo.close()

    async def fetch_klines(self) -> Tuple[List[Kline], List[Kline]]:
        warmup_ms = 700 * 24 * 3600 * 1000
        start_ts = int(datetime(2022, 1, 1).timestamp() * 1000) - warmup_ms
        end_ts = int(datetime(2025, 12, 31, 23, 59, 59).timestamp() * 1000)

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

    def run_year(
        self,
        klines_1h: List[Kline],
        klines_4h: List[Kline],
        year: int,
        feature_computer: FeatureComputer,
        toxic_filter: Optional[Callable[[MarketState], bool]] = None,
    ) -> Tuple[List[TradeRecord], int, int]:
        """
        运行单年撮合。
        toxic_filter: 返回 True 表示该 trade 是 toxic，应跳过。
        返回 (trades, total_signals, filtered_count)
        """
        year_start_ts = int(datetime(year, 1, 1).timestamp() * 1000)
        start_idx = 0
        for i in range(max(EMA_1H_PERIOD, ATR_PERIOD, DONCHIAN_PERIOD) + 72, len(klines_1h)):
            if klines_1h[i].timestamp >= year_start_ts:
                start_idx = i
                break

        trades: List[TradeRecord] = []
        active_trade: Optional[TradeRecord] = None
        total_signals = 0
        filtered_count = 0

        for idx in range(start_idx, len(klines_1h) - 1):
            kline = klines_1h[idx]
            next_kline = klines_1h[idx + 1]

            if datetime.fromtimestamp(kline.timestamp / 1000).year != year:
                if active_trade is not None:
                    self._close_trade_at_price(active_trade, kline.close, "EOD", trades)
                    active_trade = None
                continue

            # 处理活跃仓位
            if active_trade is not None:
                sig = active_trade.signal

                if sig.direction == "LONG" and kline.low <= sig.stop_loss:
                    self._close_trade_at_price(active_trade, sig.stop_loss, "SL", trades)
                    active_trade = None
                    continue
                elif sig.direction == "SHORT" and kline.high >= sig.stop_loss:
                    self._close_trade_at_price(active_trade, sig.stop_loss, "SL", trades)
                    active_trade = None
                    continue

                if not getattr(active_trade, '_tp1_hit', False):
                    if sig.direction == "LONG" and kline.high >= sig.tp1_price:
                        active_trade._tp1_hit = True
                        active_trade.signal.stop_loss = sig.entry_price
                    elif sig.direction == "SHORT" and kline.low <= sig.tp1_price:
                        active_trade._tp1_hit = True
                        active_trade.signal.stop_loss = sig.entry_price

                if getattr(active_trade, '_tp1_hit', False):
                    if sig.direction == "LONG" and kline.high >= sig.tp2_price:
                        self._close_trade_at_price(active_trade, sig.tp2_price, "TP2", trades)
                        active_trade = None
                        continue
                    elif sig.direction == "SHORT" and kline.low <= sig.tp2_price:
                        self._close_trade_at_price(active_trade, sig.tp2_price, "TP2", trades)
                        active_trade = None
                        continue

                is_year_end = kline.timestamp >= int(datetime(year, 12, 31, 20, 0, 0).timestamp() * 1000)
                if is_year_end:
                    self._close_trade_at_price(active_trade, kline.close, "EOD", trades)
                    active_trade = None
                    continue

            # 检测 Pinbar
            atr_val = feature_computer.atr_1h[idx]
            signal = detect_pinbar(kline, atr_val)
            if signal is None:
                continue

            total_signals += 1

            # EMA + MTF 过滤
            if feature_computer.ema50_1h[idx] is None:
                continue
            ema_dist = (kline.close - feature_computer.ema50_1h[idx]) / feature_computer.ema50_1h[idx]
            if kline.close <= feature_computer.ema50_1h[idx] or ema_dist < Decimal("0.005"):
                continue

            ema4h = feature_computer._get_4h_ema_at(kline.timestamp)
            close4h = feature_computer._get_4h_close_at(kline.timestamp)
            if ema4h is None or close4h is None:
                continue
            if signal.direction == "LONG" and close4h <= ema4h:
                continue
            if signal.direction == "SHORT" and close4h >= ema4h:
                continue

            # 计算 market state
            state = feature_computer.compute(idx)
            if state is None:
                continue

            # Toxic filter
            if toxic_filter is not None and toxic_filter(state):
                filtered_count += 1
                continue

            # 入场
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

            pos = TradeRecord(signal=signal, market_state=state)
            pos.signal.tp1_price = tp1_price
            pos.signal.tp2_price = tp2_price
            active_trade = pos

        if active_trade is not None:
            self._close_trade_at_price(active_trade, klines_1h[-1].close, "EOD", trades)

        return trades, total_signals, filtered_count

    def _close_trade_at_price(self, pos: TradeRecord, exit_price: Decimal, reason: str, trades: List[TradeRecord]):
        sig = pos.signal
        risk_amount = INITIAL_BALANCE * MAX_LOSS_PCT
        qty = risk_amount * sig.entry_price / sig.r_multiple
        max_qty = INITIAL_BALANCE * MAX_TOTAL_EXPOSURE / sig.entry_price
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
# 统计计算
# ============================================================
def compute_year_stats(trades: List[TradeRecord], year: int) -> Dict[str, Any]:
    if not trades:
        return {"year": year, "trades": 0, "pnl": 0, "wr": 0, "max_dd_pct": 0}

    pnls = [float(t.pnl) for t in trades]
    wins = sum(1 for p in pnls if p > 0)
    total_pnl = sum(pnls)

    # MaxDD
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    init_bal = float(INITIAL_BALANCE)
    for p in pnls:
        cum += p
        if cum + init_bal > peak:
            peak = cum + init_bal
        dd = peak - (cum + init_bal)
        if dd > max_dd:
            max_dd = dd

    return {
        "year": year,
        "trades": len(trades),
        "pnl": round(total_pnl, 2),
        "wr": round(wins / len(trades), 4),
        "max_dd": round(max_dd, 2),
        "max_dd_pct": round(max_dd / init_bal, 4),
    }


# ============================================================
# Main
# ============================================================
async def main():
    engine = ToxicStateEngine()
    try:
        await engine.setup()
        klines_1h, klines_4h = await engine.fetch_klines()
        feature_computer = FeatureComputer(klines_1h, klines_4h)

        experiments = {
            "E0: Pinbar baseline": None,
            "E1: skip ema_4h_slope high": TOXIC_THRESHOLDS["ema_4h_slope"],
            "E2: skip recent_72h_return high": TOXIC_THRESHOLDS["recent_72h_return"],
            "E3: skip realized_volatility_24h high": TOXIC_THRESHOLDS["realized_volatility_24h"],
            "E4: skip distance_to_donchian_20_high low (near top)": TOXIC_THRESHOLDS["distance_to_donchian_20_high"],
        }

        all_results = {}

        for exp_name, toxic_filter in experiments.items():
            print(f"\n{'='*70}")
            print(f"实验: {exp_name}")
            print(f"{'='*70}")

            yearly_results = {}
            for year in [2023, 2024, 2025]:
                trades, total_signals, filtered = engine.run_year(
                    klines_1h, klines_4h, year, feature_computer, toxic_filter
                )
                stats = compute_year_stats(trades, year)
                stats["total_signals"] = total_signals
                stats["filtered_count"] = filtered
                yearly_results[year] = stats

                print(f"  {year}: trades={stats['trades']}, PnL={stats['pnl']:.2f}, "
                      f"WR={stats['wr']*100:.1f}%, MaxDD={stats['max_dd_pct']*100:.2f}%, "
                      f"filtered={filtered}/{total_signals}")

            # 汇总
            total_trades = sum(s["trades"] for s in yearly_results.values())
            total_pnl = sum(s["pnl"] for s in yearly_results.values())
            total_filtered = sum(s["filtered_count"] for s in yearly_results.values())
            total_signals = sum(s["total_signals"] for s in yearly_results.values())

            print(f"\n  3yr: trades={total_trades}, PnL={total_pnl:.2f}, "
                  f"filtered={total_filtered}/{total_signals}")

            all_results[exp_name] = {
                "yearly": yearly_results,
                "total_trades": total_trades,
                "total_pnl": round(total_pnl, 2),
                "total_filtered": total_filtered,
                "total_signals": total_signals,
            }

        # 对比分析
        print(f"\n{'='*70}")
        print("对比分析")
        print(f"{'='*70}")

        baseline = all_results["E0: Pinbar baseline"]
        bl_pnl = {y: s["pnl"] for y, s in baseline["yearly"].items()}
        bl_trades = {y: s["trades"] for y, s in baseline["yearly"].items()}

        verdicts = {}
        for exp_name in experiments:
            if exp_name == "E0: Pinbar baseline":
                continue

            exp = all_results[exp_name]
            exp_pnl = {y: s["pnl"] for y, s in exp["yearly"].items()}
            exp_trades = {y: s["trades"] for y, s in exp["yearly"].items()}

            # 2023 loss reduction
            bl_2023 = bl_pnl[2023]
            exp_2023 = exp_pnl[2023]
            if bl_2023 < 0:
                # loss_reduction > 0 means filtered has smaller absolute loss (improvement)
                loss_reduction = (abs(bl_2023) - abs(exp_2023)) / abs(bl_2023) * 100
            else:
                loss_reduction = 0

            # 2024+2025 profit retention
            bl_2425 = bl_pnl[2024] + bl_pnl[2025]
            exp_2425 = exp_pnl[2024] + exp_pnl[2025]
            if bl_2425 > 0:
                profit_retention = exp_2425 / bl_2425 * 100
            else:
                profit_retention = 100

            # 3yr PnL delta
            pnl_delta = exp["total_pnl"] - baseline["total_pnl"]

            # trade reduction
            trade_reduction = (baseline["total_trades"] - exp["total_trades"]) / baseline["total_trades"] * 100

            # MaxDD comparison
            bl_maxdd = max(s["max_dd"] for s in baseline["yearly"].values())
            exp_maxdd = max(s["max_dd"] for s in exp["yearly"].values())
            maxdd_improved = exp_maxdd < bl_maxdd

            # Verdict
            pass_checks = []
            fail_checks = []

            if loss_reduction >= 25:
                pass_checks.append(f"2023 loss reduction {loss_reduction:.1f}% >= 25%")
            else:
                fail_checks.append(f"2023 loss reduction {loss_reduction:.1f}% < 25%")

            if profit_retention >= 80:
                pass_checks.append(f"2024+25 profit retention {profit_retention:.1f}% >= 80%")
            else:
                fail_checks.append(f"2024+25 profit retention {profit_retention:.1f}% < 80%")

            if pnl_delta > 0:
                pass_checks.append(f"3yr PnL delta +{pnl_delta:.2f} > 0")
            else:
                fail_checks.append(f"3yr PnL delta {pnl_delta:.2f} <= 0")

            if trade_reduction <= 40:
                pass_checks.append(f"trade reduction {trade_reduction:.1f}% <= 40%")
            else:
                fail_checks.append(f"trade reduction {trade_reduction:.1f}% > 40%")

            if maxdd_improved:
                pass_checks.append("MaxDD improved")
            else:
                fail_checks.append("MaxDD not improved")

            verdict = "PASS" if len(fail_checks) == 0 else "FAIL"

            print(f"\n{exp_name}:")
            print(f"  2023 loss reduction: {loss_reduction:.1f}%")
            print(f"  2024+25 profit retention: {profit_retention:.1f}%")
            print(f"  3yr PnL delta: {pnl_delta:+.2f}")
            print(f"  Trade reduction: {trade_reduction:.1f}%")
            print(f"  MaxDD: {bl_maxdd:.2f} -> {exp_maxdd:.2f}")
            print(f"  Verdict: {verdict}")
            for c in pass_checks:
                print(f"    PASS: {c}")
            for c in fail_checks:
                print(f"    FAIL: {c}")

            verdicts[exp_name] = {
                "verdict": verdict,
                "loss_reduction_pct": round(loss_reduction, 1),
                "profit_retention_pct": round(profit_retention, 1),
                "pnl_delta": round(pnl_delta, 2),
                "trade_reduction_pct": round(trade_reduction, 1),
                "maxdd_before": round(bl_maxdd, 2),
                "maxdd_after": round(exp_maxdd, 2),
                "pass_checks": pass_checks,
                "fail_checks": fail_checks,
            }

        # 保存 JSON
        report = {
            "title": "M1 Pinbar Toxic State Avoidance",
            "date": datetime.now().isoformat()[:10],
            "hypothesis": "M1: 单个 toxic-state filter 能减少 Pinbar 亏损且不破坏 2024/2025 收益",
            "config": {
                "toxic_thresholds": {k: str(v) for k, v in TOXIC_THRESHOLDS.items()},
                "tp_targets": [float(t) for t in TP_TARGETS],
                "fee_rate": float(FEE_RATE),
                "filters": "EMA50 + MTF 4h EMA60 (same as baseline)",
            },
            "baseline_yearly": {str(y): s for y, s in baseline["yearly"].items()},
            "experiments": {},
            "verdicts": verdicts,
            "overall_verdict": "PASS" if any(v["verdict"] == "PASS" for v in verdicts.values()) else "FAIL",
            "proxy_note": "Standalone proxy, not equivalent to official backtester.",
        }

        for exp_name, exp_data in all_results.items():
            report["experiments"][exp_name] = {
                "yearly": {str(y): s for y, s in exp_data["yearly"].items()},
                "total_trades": exp_data["total_trades"],
                "total_pnl": exp_data["total_pnl"],
                "total_filtered": exp_data["total_filtered"],
            }

        reports_dir = PROJECT_ROOT / "reports" / "research"
        reports_dir.mkdir(parents=True, exist_ok=True)
        json_path = reports_dir / "pinbar_toxic_state_m1_2026-04-28.json"
        with open(json_path, "w") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"\nJSON saved: {json_path}")

    finally:
        await engine.teardown()


if __name__ == "__main__":
    asyncio.run(main())
