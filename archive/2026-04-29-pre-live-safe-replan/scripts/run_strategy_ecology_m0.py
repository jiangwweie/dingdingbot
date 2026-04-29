#!/usr/bin/env python3
"""
M0: Strategy Ecology Map — Pinbar Baseline 市场状态 × 策略表现诊断
建立市场状态与 Pinbar 表现的映射，判断策略应该补哪个缺口。

约束：
- research-only
- 不改 src 核心代码（standalone proxy）
- 不改 runtime profile
- 不做参数搜索
- 不提交 git
- 报告标注为 proxy result

方法：
1. 独立 Pinbar 检测（复刻 src 逻辑）
2. 独立撮合（复刻 H6a proxy 的 TP/SL 逻辑）
3. 在每个 signal time 计算 10 个 market state features
4. 按 feature tercile 分桶
5. 输出每桶的 trade_count / PnL / WR / avg_pnl / avg_R / MaxDD
"""

import asyncio
import sys
import json
from pathlib import Path
from datetime import datetime
from decimal import Decimal
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any
from collections import defaultdict
import statistics

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.infrastructure.historical_data_repository import HistoricalDataRepository

DB_PATH = "data/v3_dev.db"

# ============================================================
# 配置
# ============================================================
SYMBOL = "ETH/USDT:USDT"
TIMEFRAME = "1h"
HIGHER_TF = "4h"

# Pinbar 参数（复刻 src PinbarConfig）
MIN_WICK_RATIO = Decimal("0.6")
MAX_BODY_RATIO = Decimal("0.3")
BODY_POSITION_TOLERANCE = Decimal("0.1")

# 指标参数
EMA_1H_PERIOD = 50
EMA_4H_PERIOD = 60
ATR_PERIOD = 14
DONCHIAN_PERIOD = 20

# 成本口径 (BNB9)
ENTRY_SLIPPAGE = Decimal("0.0001")
FEE_RATE = Decimal("0.000405")
TP_SLIPPAGE = Decimal("0")

# 止盈参数
TP_RATIOS = [Decimal("0.5"), Decimal("0.5")]
TP_TARGETS = [Decimal("1.0"), Decimal("3.5")]

# 风控
INITIAL_BALANCE = Decimal("10000")
MAX_LOSS_PCT = Decimal("0.01")
MAX_TOTAL_EXPOSURE = Decimal("2.0")


# ============================================================
# 数据结构
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
    idx: int              # 在 klines_1h 中的 index
    timestamp: int
    direction: str        # "LONG" or "SHORT"
    wick_ratio: Decimal
    body_ratio: Decimal
    entry_price: Decimal  # next bar open + slippage
    stop_loss: Decimal
    r_multiple: Decimal
    score: Decimal
    tp1_price: Decimal = Decimal("0")
    tp2_price: Decimal = Decimal("0")


@dataclass
class MarketState:
    """10 个 market state features at signal time"""
    ema_1h_slope: float = 0.0          # EMA50 1h 斜率（%/bar over 5 bars）
    ema_4h_slope: float = 0.0          # EMA60 4h 斜率（%/bar over 3 bars）
    price_dist_ema50: float = 0.0      # (close - EMA50) / EMA50
    atr_percentile: float = 0.0        # ATR14 在过去 500 bars 中的百分位
    recent_24h_return: float = 0.0     # 过去 24 bars 的收益率
    recent_72h_return: float = 0.0     # 过去 72 bars 的收益率
    realized_volatility_24h: float = 0.0  # 过去 24 bars 的 realized vol (std of returns)
    range_compression_24h: float = 0.0 # 过去 24 bars 的 (high-low) 均值 / ATR
    distance_to_donchian_20_high: float = 0.0  # (close - DC20_high) / close
    distance_to_donchian_20_low: float = 0.0   # (DC20_low - close) / close
    # 额外元数据
    year: int = 0
    signal_ts: int = 0


@dataclass
class TradeRecord:
    signal: PinbarSignal
    market_state: MarketState
    pnl: Decimal = Decimal("0")
    r_achieved: Decimal = Decimal("0")  # 实际 R 倍数
    exit_reason: str = ""
    holding_bars: int = 0
    _tp1_hit: bool = False


# ============================================================
# 指标计算
# ============================================================
def compute_ema(prices: List[Decimal], period: int) -> List[Optional[Decimal]]:
    """EMA 序列，前 period-1 个为 None"""
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
    """Wilder's ATR"""
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

    # 初始 SMA
    atr = sum(trs[:period]) / Decimal(period)
    result[period] = atr  # trs[period-1] 对应 klines[period]

    for i in range(period, len(trs)):
        atr = (atr * (Decimal(period) - 1) + trs[i]) / Decimal(period)
        result[i + 1] = atr

    return result


# ============================================================
# Pinbar 检测（复刻 src 逻辑）
# ============================================================
def detect_pinbar(kline: Kline, atr_value: Optional[Decimal] = None) -> Optional[PinbarSignal]:
    """复刻 PinbarStrategy.detect() 的逻辑"""
    high = kline.high
    low = kline.low
    close = kline.close
    open_price = kline.open

    candle_range = high - low
    if candle_range == Decimal(0):
        return None

    # 最小波幅检查
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

    # Score
    pattern_ratio = wick_ratio
    if atr_value and atr_value > 0:
        atr_ratio = candle_range / atr_value
        base_score = pattern_ratio
        atr_bonus = min(atr_ratio, Decimal("2.0")) * Decimal("0.3")
        score = min(base_score * Decimal("0.7") + atr_bonus, Decimal("1.0"))
    else:
        score = pattern_ratio

    # 止损
    if direction == "LONG":
        stop_loss = low
    else:
        stop_loss = high

    return PinbarSignal(
        idx=0,  # 填充由调用方
        timestamp=kline.timestamp,
        direction=direction,
        wick_ratio=wick_ratio,
        body_ratio=body_ratio,
        entry_price=Decimal("0"),  # 填充由撮合引擎
        stop_loss=stop_loss,
        r_multiple=Decimal("0"),
        score=score,
    )


# ============================================================
# Market State 特征计算
# ============================================================
class FeatureComputer:
    """计算 10 个 market state features"""

    def __init__(self, klines_1h: List[Kline], klines_4h: List[Kline]):
        self.klines_1h = klines_1h
        self.klines_4h = klines_4h

        # 预计算指标
        closes_1h = [k.close for k in klines_1h]
        self.ema50_1h = compute_ema(closes_1h, EMA_1H_PERIOD)
        self.atr_1h = compute_atr(klines_1h, ATR_PERIOD)

        closes_4h = [k.close for k in klines_4h]
        self.ema60_4h = compute_ema(closes_4h, EMA_4H_PERIOD)

        # 预计算 4h EMA 映射
        self.ema_4h_map: Dict[int, Decimal] = {}
        for i, k in enumerate(klines_4h):
            if self.ema60_4h[i] is not None:
                self.ema_4h_map[k.timestamp] = self.ema60_4h[i]

    def _get_4h_ema_at(self, signal_ts: int) -> Optional[Decimal]:
        """获取 signal_ts 之前最后一个已收盘 4h K 的 EMA"""
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
        """获取 signal_ts 之前最后一个已收盘 4h K 的 close"""
        last_closed = None
        for k in self.klines_4h:
            candle_close = k.timestamp + 4 * 3600 * 1000
            if candle_close <= signal_ts:
                last_closed = k
            else:
                break
        return last_closed.close if last_closed else None

    def compute(self, idx: int) -> Optional[MarketState]:
        """计算 idx 位置的 market state features"""
        if idx < max(EMA_1H_PERIOD, ATR_PERIOD, DONCHIAN_PERIOD) + 72:
            return None  # warmup 不足

        kline = self.klines_1h[idx]
        state = MarketState(
            year=datetime.fromtimestamp(kline.timestamp / 1000).year,
            signal_ts=kline.timestamp,
        )

        # 1. ema_1h_slope: EMA50 over last 5 bars (%/bar)
        if self.ema50_1h[idx] is not None and self.ema50_1h[idx - 5] is not None:
            ema_now = float(self.ema50_1h[idx])
            ema_5ago = float(self.ema50_1h[idx - 5])
            state.ema_1h_slope = (ema_now - ema_5ago) / ema_5ago / 5.0 * 100  # % per bar
        else:
            return None

        # 2. ema_4h_slope: EMA60 4h over last 3 bars (%/bar)
        ema4h_now = self._get_4h_ema_at(kline.timestamp)
        # 3 bars ago = 12h ago
        ts_12h_ago = kline.timestamp - 12 * 3600 * 1000
        ema4h_12h = self._get_4h_ema_at(ts_12h_ago)
        if ema4h_now is not None and ema4h_12h is not None:
            state.ema_4h_slope = (float(ema4h_now) - float(ema4h_12h)) / float(ema4h_12h) / 3.0 * 100
        else:
            state.ema_4h_slope = 0.0

        # 3. price_dist_ema50
        if self.ema50_1h[idx] is not None:
            state.price_dist_ema50 = float((kline.close - self.ema50_1h[idx]) / self.ema50_1h[idx])
        else:
            return None

        # 4. atr_percentile: ATR14 在过去 500 bars 中的百分位
        if self.atr_1h[idx] is not None:
            window_start = max(0, idx - 500)
            atr_window = [float(self.atr_1h[j]) for j in range(window_start, idx + 1)
                         if self.atr_1h[j] is not None]
            if len(atr_window) > 10:
                current_atr = float(self.atr_1h[idx])
                state.atr_percentile = sum(1 for a in atr_window if a <= current_atr) / len(atr_window)
            else:
                return None
        else:
            return None

        # 5. recent_24h_return
        if idx >= 24:
            state.recent_24h_return = float((kline.close - self.klines_1h[idx - 24].close) / self.klines_1h[idx - 24].close)
        else:
            return None

        # 6. recent_72h_return
        if idx >= 72:
            state.recent_72h_return = float((kline.close - self.klines_1h[idx - 72].close) / self.klines_1h[idx - 72].close)
        else:
            return None

        # 7. realized_volatility_24h: std of 24h log returns
        if idx >= 24:
            returns = []
            for j in range(idx - 23, idx + 1):
                r = float(self.klines_1h[j].close / self.klines_1h[j - 1].close)
                import math
                returns.append(math.log(r))
            if len(returns) >= 10:
                state.realized_volatility_24h = statistics.stdev(returns) if len(returns) > 1 else 0.0
            else:
                return None
        else:
            return None

        # 8. range_compression_24h: avg range over 24 bars / ATR
        if idx >= 24 and self.atr_1h[idx] is not None and self.atr_1h[idx] > 0:
            avg_range = sum(float(self.klines_1h[j].high - self.klines_1h[j].low)
                          for j in range(idx - 23, idx + 1)) / 24.0
            state.range_compression_24h = avg_range / float(self.atr_1h[idx])
        else:
            return None

        # 9. distance_to_donchian_20_high
        if idx >= DONCHIAN_PERIOD:
            dc_high = max(float(self.klines_1h[j].high) for j in range(idx - DONCHIAN_PERIOD, idx))
            state.distance_to_donchian_20_high = (float(kline.close) - dc_high) / float(kline.close)
        else:
            return None

        # 10. distance_to_donchian_20_low
        if idx >= DONCHIAN_PERIOD:
            dc_low = min(float(self.klines_1h[j].low) for j in range(idx - DONCHIAN_PERIOD, idx))
            state.distance_to_donchian_20_low = (dc_low - float(kline.close)) / float(kline.close)
        else:
            return None

        return state


# ============================================================
# 撮合引擎
# ============================================================
class PinbarEcologyEngine:
    """Pinbar 信号检测 + 撮合 + 特征提取"""

    def __init__(self):
        self.repo: Optional[HistoricalDataRepository] = None

    async def setup(self):
        self.repo = HistoricalDataRepository(DB_PATH)
        await self.repo.initialize()

    async def teardown(self):
        if self.repo:
            await self.repo.close()

    async def fetch_klines(self) -> Tuple[List[Kline], List[Kline]]:
        """获取 2022-2025 全部数据 + warmup"""
        warmup_ms = 700 * 24 * 3600 * 1000  # ~700 天 warmup (足够 EMA + 500-bar ATR window)
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

    def run(
        self,
        klines_1h: List[Kline],
        klines_4h: List[Kline],
        year: Optional[int] = None,
    ) -> List[TradeRecord]:
        """
        运行 Pinbar 检测 + 撮合 + 特征提取
        year=None 表示全部年份
        """
        feature_computer = FeatureComputer(klines_1h, klines_4h)

        # 确定起始 idx
        min_warmup = max(EMA_1H_PERIOD, ATR_PERIOD, DONCHIAN_PERIOD) + 72
        start_idx = min_warmup

        if year is not None:
            year_start_ts = int(datetime(year, 1, 1).timestamp() * 1000)
            for i in range(min_warmup, len(klines_1h)):
                if klines_1h[i].timestamp >= year_start_ts:
                    start_idx = i
                    break

        trades: List[TradeRecord] = []
        active_trade: Optional[TradeRecord] = None

        for idx in range(start_idx, len(klines_1h) - 1):
            kline = klines_1h[idx]
            next_kline = klines_1h[idx + 1]

            # 如果有年份过滤，跳过超出范围的
            if year is not None:
                if datetime.fromtimestamp(kline.timestamp / 1000).year != year:
                    # 但要处理年末未平仓
                    if active_trade is not None:
                        self._close_trade(active_trade, kline, "EOD", trades)
                        active_trade = None
                    continue

            # 处理活跃仓位
            if active_trade is not None:
                sig = active_trade.signal
                pos = active_trade

                # 止损
                if sig.direction == "LONG" and kline.low <= sig.stop_loss:
                    self._close_trade_at_price(pos, sig.stop_loss, "SL", trades)
                    active_trade = None
                    continue
                elif sig.direction == "SHORT" and kline.high >= sig.stop_loss:
                    self._close_trade_at_price(pos, sig.stop_loss, "SL", trades)
                    active_trade = None
                    continue

                # TP1
                if not getattr(pos, '_tp1_hit', False):
                    if sig.direction == "LONG" and kline.high >= sig.tp1_price:
                        pos._tp1_hit = True
                        pos.signal.stop_loss = sig.entry_price  # move to BE
                    elif sig.direction == "SHORT" and kline.low <= sig.tp1_price:
                        pos._tp1_hit = True
                        pos.signal.stop_loss = sig.entry_price

                # TP2
                if getattr(pos, '_tp1_hit', False):
                    if sig.direction == "LONG" and kline.high >= sig.tp2_price:
                        self._close_trade_at_price(pos, sig.tp2_price, "TP2", trades)
                        active_trade = None
                        continue
                    elif sig.direction == "SHORT" and kline.low <= sig.tp2_price:
                        self._close_trade_at_price(pos, sig.tp2_price, "TP2", trades)
                        active_trade = None
                        continue

                # 年末平仓
                if year is not None:
                    is_year_end = kline.timestamp >= int(datetime(year, 12, 31, 20, 0, 0).timestamp() * 1000)
                    if is_year_end:
                        self._close_trade_at_price(pos, kline.close, "EOD", trades)
                        active_trade = None
                        continue

            # 检测 Pinbar
            atr_val = feature_computer.atr_1h[idx]
            signal = detect_pinbar(kline, atr_val)
            if signal is None:
                continue

            # 应用 EMA + MTF 过滤（复刻 baseline）
            if feature_computer.ema50_1h[idx] is None:
                continue
            ema_dist = (kline.close - feature_computer.ema50_1h[idx]) / feature_computer.ema50_1h[idx]
            if kline.close <= feature_computer.ema50_1h[idx] or ema_dist < Decimal("0.005"):
                continue

            # MTF 4h filter
            ema4h = feature_computer._get_4h_ema_at(kline.timestamp)
            close4h = feature_computer._get_4h_close_at(kline.timestamp)
            if ema4h is None or close4h is None:
                continue
            if signal.direction == "LONG" and close4h <= ema4h:
                continue
            if signal.direction == "SHORT" and close4h >= ema4h:
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

            # 计算 market state
            state = feature_computer.compute(idx)
            if state is None:
                continue

            # 创建 trade
            pos = TradeRecord(signal=signal, market_state=state)
            pos.signal.tp1_price = tp1_price
            pos.signal.tp2_price = tp2_price
            active_trade = pos

        # 年末未平仓
        if active_trade is not None:
            self._close_trade_at_price(active_trade, klines_1h[-1].close, "EOD", trades)

        return trades

    def _close_trade_at_price(self, pos: TradeRecord, exit_price: Decimal, reason: str, trades: List[TradeRecord]):
        """以指定价格平仓"""
        sig = pos.signal
        risk_amount = INITIAL_BALANCE * MAX_LOSS_PCT  # 100 USDT
        # qty = risk_amount / (r_multiple / entry_price) = risk_amount * entry_price / r_multiple
        qty = risk_amount * sig.entry_price / sig.r_multiple

        # Exposure cap: 截断到 2.0x
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
        # 计算实际 R 倍数
        if sig.direction == "LONG":
            pos.r_achieved = (exit_price - sig.entry_price) / sig.r_multiple
        else:
            pos.r_achieved = (sig.entry_price - exit_price) / sig.r_multiple

        trades.append(pos)

    def _close_trade(self, pos: TradeRecord, kline: Kline, reason: str, trades: List[TradeRecord]):
        self._close_trade_at_price(pos, kline.close, reason, trades)


# ============================================================
# 分桶与统计
# ============================================================
FEATURE_NAMES = [
    "ema_1h_slope",
    "ema_4h_slope",
    "price_dist_ema50",
    "atr_percentile",
    "recent_24h_return",
    "recent_72h_return",
    "realized_volatility_24h",
    "range_compression_24h",
    "distance_to_donchian_20_high",
    "distance_to_donchian_20_low",
]


def tercile_split(values: List[float]) -> Tuple[float, float]:
    """返回 (T1 边界, T2 边界)"""
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    t1 = sorted_vals[n // 3]
    t2 = sorted_vals[2 * n // 3]
    return t1, t2


def bucket_label(val: float, t1: float, t2: float) -> str:
    if val <= t1:
        return "low"
    elif val <= t2:
        return "mid"
    else:
        return "high"


def compute_bucket_stats(trades: List[TradeRecord], feature_name: str) -> Dict[str, Any]:
    """按单个 feature 分桶，计算每桶统计"""
    values = [getattr(t.market_state, feature_name) for t in trades]
    if len(values) < 30:
        return {"error": "insufficient trades"}

    t1, t2 = tercile_split(values)

    buckets = {"low": [], "mid": [], "high": []}
    for t in trades:
        val = getattr(t.market_state, feature_name)
        label = bucket_label(val, t1, t2)
        buckets[label].append(t)

    result = {}
    for label, bucket_trades in buckets.items():
        if not bucket_trades:
            result[label] = {"trade_count": 0}
            continue

        pnls = [float(t.pnl) for t in bucket_trades]
        r_vals = [float(t.r_achieved) for t in bucket_trades]
        wins = sum(1 for p in pnls if p > 0)

        # MaxDD
        cum = 0.0
        peak = 0.0
        max_dd = 0.0
        for p in pnls:
            cum += p
            if cum > peak:
                peak = cum
            dd = peak - cum
            if dd > max_dd:
                max_dd = dd

        result[label] = {
            "trade_count": len(bucket_trades),
            "pnl": round(sum(pnls), 2),
            "wr": round(wins / len(bucket_trades), 4),
            "avg_pnl": round(statistics.mean(pnls), 2),
            "avg_r": round(statistics.mean(r_vals), 4) if r_vals else 0,
            "max_dd": round(max_dd, 2),
            "tercile_boundary_low": round(t1, 6),
            "tercile_boundary_high": round(t2, 6),
        }

    # PnL spread
    pnl_vals = {k: v.get("pnl", 0) for k, v in result.items() if isinstance(v, dict) and "pnl" in v}
    if pnl_vals:
        result["spread_pnl"] = round(max(pnl_vals.values()) - min(pnl_vals.values()), 2)
        result["best_bucket"] = max(pnl_vals, key=pnl_vals.get)
        result["worst_bucket"] = min(pnl_vals, key=pnl_vals.get)

    return result


def compute_year_distribution(trades: List[TradeRecord]) -> Dict[int, Dict]:
    """每年的 market state 分布"""
    year_trades = defaultdict(list)
    for t in trades:
        year_trades[t.market_state.year].append(t)

    result = {}
    for year, ytrades in sorted(year_trades.items()):
        states = [t.market_state for t in ytrades]
        result[year] = {
            "trade_count": len(ytrades),
            "pnl": round(sum(float(t.pnl) for t in ytrades), 2),
            "wr": round(sum(1 for t in ytrades if t.pnl > 0) / len(ytrades), 4),
            "features": {}
        }
        for fname in FEATURE_NAMES:
            vals = [getattr(s, fname) for s in states]
            if vals:
                result[year]["features"][fname] = {
                    "mean": round(statistics.mean(vals), 6),
                    "median": round(statistics.median(vals), 6),
                    "std": round(statistics.stdev(vals), 6) if len(vals) > 1 else 0,
                }

    return result


def compute_profitability_profile(trades: List[TradeRecord]) -> Dict[str, Any]:
    """Pinbar 盈利/亏损 profile"""
    winners = [t for t in trades if t.pnl > 0]
    losers = [t for t in trades if t.pnl <= 0]

    def profile(subset: List[TradeRecord]) -> Dict:
        if not subset:
            return {"count": 0}
        states = [t.market_state for t in subset]
        result = {"count": len(subset)}
        for fname in FEATURE_NAMES:
            vals = [getattr(s, fname) for s in states]
            if vals:
                result[fname] = {
                    "mean": round(statistics.mean(vals), 6),
                    "median": round(statistics.median(vals), 6),
                }
        return result

    return {
        "winners": profile(winners),
        "losers": profile(losers),
        "total": len(trades),
        "win_rate": round(len(winners) / len(trades), 4) if trades else 0,
    }


# ============================================================
# Main
# ============================================================
async def main():
    engine = PinbarEcologyEngine()
    try:
        await engine.setup()
        klines_1h, klines_4h = await engine.fetch_klines()

        # 运行全部年份
        print("\nRunning Pinbar detection + trade simulation...")
        all_trades = engine.run(klines_1h, klines_4h, year=None)
        print(f"Total trades: {len(all_trades)}")

        if not all_trades:
            print("No trades found. Aborting.")
            return

        # 1. 年度总览
        year_dist = compute_year_distribution(all_trades)
        print("\n=== Year Distribution ===")
        for year, stats in sorted(year_dist.items()):
            print(f"  {year}: trades={stats['trade_count']}, PnL={stats['pnl']:.2f}, WR={stats['wr']*100:.1f}%")

        # 2. 单特征分桶
        feature_bucket_results = {}
        print("\n=== Feature Bucket Analysis ===")
        for fname in FEATURE_NAMES:
            stats = compute_bucket_stats(all_trades, fname)
            feature_bucket_results[fname] = stats
            if "error" not in stats:
                spread = stats.get("spread_pnl", 0)
                best = stats.get("best_bucket", "?")
                worst = stats.get("worst_bucket", "?")
                print(f"  {fname}: spread={spread:.2f}, best={best}, worst={worst}")
                for bucket in ["low", "mid", "high"]:
                    b = stats.get(bucket, {})
                    if b.get("trade_count", 0) > 0:
                        print(f"    {bucket}: n={b['trade_count']}, PnL={b['pnl']:.2f}, WR={b['wr']*100:.1f}%")

        # 3. 盈利/亏损 profile
        prof = compute_profitability_profile(all_trades)
        print(f"\n=== Profitability Profile ===")
        print(f"  Winners: {prof['winners']['count']}, Losers: {prof['losers']['count']}, WR={prof['win_rate']*100:.1f}%")

        # 4. 诊断：哪些特征有解释力
        print("\n=== Diagnostic: Feature Explanatory Power ===")
        interpretable = []
        for fname in FEATURE_NAMES:
            stats = feature_bucket_results.get(fname, {})
            if "error" in stats:
                continue
            spread = abs(stats.get("spread_pnl", 0))
            if spread > 500:  # 500 USDT spread = 有意义
                interpretable.append((fname, spread, stats.get("best_bucket"), stats.get("worst_bucket")))
        interpretable.sort(key=lambda x: x[1], reverse=True)

        if interpretable:
            print(f"  Features with explanatory power (spread > 500):")
            for fname, spread, best, worst in interpretable:
                print(f"    {fname}: spread={spread:.2f}, best={best}, worst={worst}")
        else:
            print("  No features with significant explanatory power (spread < 500)")

        # 5. 2023 vs 2024/2025 差异
        print("\n=== 2023 vs 2024/2025 State Difference ===")
        for fname in FEATURE_NAMES:
            vals_2023 = [getattr(t.market_state, fname) for t in all_trades if t.market_state.year == 2023]
            vals_2425 = [getattr(t.market_state, fname) for t in all_trades if t.market_state.year in (2024, 2025)]
            if vals_2023 and vals_2425:
                m2023 = statistics.mean(vals_2023)
                m2425 = statistics.mean(vals_2425)
                diff = m2023 - m2425
                if abs(diff) > 0.01:
                    print(f"  {fname}: 2023={m2023:.4f}, 2024/25={m2425:.4f}, diff={diff:.4f}")

        # 保存 JSON
        report = {
            "title": "M0 Strategy Ecology Map — Pinbar Baseline",
            "date": datetime.now().isoformat()[:10],
            "hypothesis": "M0: 市场状态特征能区分 Pinbar 盈利/亏损状态",
            "config": {
                "pinbar_min_wick_ratio": float(MIN_WICK_RATIO),
                "pinbar_max_body_ratio": float(MAX_BODY_RATIO),
                "ema_1h_period": EMA_1H_PERIOD,
                "ema_4h_period": EMA_4H_PERIOD,
                "atr_period": ATR_PERIOD,
                "donchian_period": DONCHIAN_PERIOD,
                "tp_targets": [float(t) for t in TP_TARGETS],
                "tp_ratios": [float(r) for r in TP_RATIOS],
                "fee_rate": float(FEE_RATE),
                "entry_slippage": float(ENTRY_SLIPPAGE),
                "filters": "EMA50 + MTF 4h EMA60 (same as baseline)",
            },
            "total_trades": len(all_trades),
            "year_distribution": year_dist,
            "feature_buckets": feature_bucket_results,
            "profitability_profile": prof,
            "diagnostic": {
                "interpretable_features": [
                    {"feature": f, "spread_pnl": round(s, 2), "best_bucket": b, "worst_bucket": w}
                    for f, s, b, w in interpretable
                ],
                "verdict": "PASS" if len(interpretable) >= 2 else "FAIL",
                "reason": f"{len(interpretable)} features with spread > 500 USDT" if interpretable else "No features with significant explanatory power",
            },
            "proxy_note": "Standalone proxy, not equivalent to official backtester. Pinbar detection replicates src logic.",
        }

        reports_dir = PROJECT_ROOT / "reports" / "research"
        reports_dir.mkdir(parents=True, exist_ok=True)
        json_path = reports_dir / "strategy_ecology_m0_2026-04-28.json"
        with open(json_path, "w") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"\nJSON saved: {json_path}")

    finally:
        await engine.teardown()


if __name__ == "__main__":
    asyncio.run(main())
