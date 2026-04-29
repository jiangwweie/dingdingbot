#!/usr/bin/env python3
"""
H3a: 入场前可观测特征是否能预测低 MFE / 低 follow-through？

方法：
  1. 跑当前 LONG-only 基线回测，拿到 positions（含 entry_time, entry_price）
  2. 加载多周期 K 线数据（1h, 4h, 1d）
  3. 对每笔交易计算入场前特征（EMA slope, price distance, range, volatility 等）
  4. 对每笔交易计算入场后 MFE/MAE/reach rate（结果标签，非特征）
  5. 按特征分桶统计，判断是否存在稳定区分度

反前瞻保证：
  - 所有入场前特征只使用 entry_time 之前已收盘的 K 线数据
  - 1d K 线使用 close_time <= entry_time（与 H0 v2 修正一致）
  - MFE/MAE/reach rate 是结果标签，不作为特征

严格边界：不改引擎、不改 runtime、不改 live 代码路径。
ADX 标记为 TODO（当前代码未实现），不为此改核心代码。
"""

import asyncio
import json
import math
import statistics
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.application.backtester import Backtester
from src.application.research_control_plane import BASELINE_RUNTIME_OVERRIDES
from src.domain.models import (
    BacktestRequest,
    KlineData,
    OrderStrategy,
    PMSBacktestReport,
    PositionSummary,
    RiskConfig,
)
from src.infrastructure.historical_data_repository import HistoricalDataRepository

# ─── 常量 ───────────────────────────────────────────────────────────────

SYMBOL = "ETH/USDT:USDT"
TIMEFRAME = "1h"
YEARS = [2023, 2024, 2025]
BNB9_SLIPPAGE = Decimal("0.0001")
BNB9_TP_SLIPPAGE = Decimal("0")
BNB9_FEE = Decimal("0.000405")
INITIAL_BALANCE = Decimal("10000")
DAY_MS = 86400000
HOUR_MS = 3600000

RESEARCH_RISK = RiskConfig(
    max_loss_percent=Decimal("0.01"),
    max_leverage=20,
    max_total_exposure=Decimal("2.0"),
    max_position_percent=Decimal("0.2"),
    daily_max_loss=Decimal("0.05"),
    daily_max_trades=50,
    min_balance=Decimal("100"),
)

ORDER_STRATEGY = OrderStrategy(
    id="h3a_feature_check",
    name="H3a feature check",
    tp_levels=2,
    tp_ratios=[Decimal("0.5"), Decimal("0.5")],
    tp_targets=[Decimal("1.0"), Decimal("3.5")],
    initial_stop_loss_rr=Decimal("-1.0"),
    trailing_stop_enabled=False,
    oco_enabled=True,
)

REPORT_DIR = PROJECT_ROOT / "reports" / "research"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
JSON_PATH = REPORT_DIR / "h3a_followthrough_feature_check_2026-04-28.json"
MD_PATH = PROJECT_ROOT / "docs" / "planning" / "2026-04-28-h3a-followthrough-feature-check.md"

# MFE threshold
HIGH_MFE_THRESHOLD = 2.0  # %
VERY_HIGH_MFE_THRESHOLD = 3.0  # %

# EMA periods
EMA_PERIOD_1H = 50
EMA_PERIOD_4H = 50
EMA_PERIOD_1D = 50


# ─── 工具 ────────────────────────────────────────────────────────────────

def year_range_ms(year: int) -> tuple[int, int]:
    start = int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    end = int(datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)
    return start, end


def compute_ema_series(closes: list[float], period: int) -> list[Optional[float]]:
    """Compute EMA series from close prices."""
    if len(closes) < period:
        return [None] * len(closes)
    k = 2.0 / (period + 1)
    ema = [None] * len(closes)
    # Seed with SMA
    seed = sum(closes[:period]) / period
    ema[period - 1] = seed
    for i in range(period, len(closes)):
        ema[i] = closes[i] * k + ema[i - 1] * (1 - k)
    return ema


def compute_ema_slope(ema_values: list[Optional[float]], idx: int, lookback: int = 5) -> Optional[float]:
    """Compute EMA slope as % change over lookback bars."""
    if idx < lookback:
        return None
    current = ema_values[idx]
    past = ema_values[idx - lookback]
    if current is None or past is None or past == 0:
        return None
    return (current - past) / past * 100


# ─── 数据结构 ────────────────────────────────────────────────────────────

@dataclass
class TradeFeatures:
    # Identity
    year: int
    position_id: str
    entry_time: int
    entry_price: float
    exit_price: float
    realized_pnl: float
    exit_reason: str

    # ── 入场前特征 ──
    # 1. EMA slopes
    ema_1h_slope: Optional[float] = None
    ema_4h_slope: Optional[float] = None
    ema_1d_slope: Optional[float] = None

    # 2. Price distance to EMA (%)
    price_dist_ema_1h: Optional[float] = None
    price_dist_ema_4h: Optional[float] = None
    price_dist_ema_1d: Optional[float] = None

    # 3. Signal K range
    signal_k_range_pct: Optional[float] = None  # (high - low) / close * 100

    # 4. Recent N bars return
    recent_5bar_return: Optional[float] = None  # % change over last 5 bars
    recent_10bar_return: Optional[float] = None

    # 5. Recent N bars volatility proxy
    recent_5bar_volatility: Optional[float] = None  # stdev of returns * 100
    recent_10bar_volatility: Optional[float] = None

    # 6. MTF trend
    mtf_4h_bullish: Optional[bool] = None  # 4h EMA > 4h EMA[5]
    mtf_1d_bullish: Optional[bool] = None  # 1d EMA > 1d EMA[5]

    # ── 结果标签（非特征）──
    mfe_24h: Optional[float] = None  # %, max favorable excursion in 24 bars
    mae_24h: Optional[float] = None  # %, max adverse excursion in 24 bars
    mfe_full: Optional[float] = None  # %, max favorable excursion until exit
    mae_full: Optional[float] = None  # %, max adverse excursion until exit
    high_follow_through: Optional[bool] = None  # MFE_24h >= 2.0%
    very_high_follow_through: Optional[bool] = None  # MFE_24h >= 3.0%
    reach_1r: Optional[bool] = None  # price reached +1R from entry
    reach_2r: Optional[bool] = None
    reach_3_5r: Optional[bool] = None
    first_touch_bullish: Optional[bool] = None  # first bar after entry closed above entry
    is_win: bool = False


# ─── 基线回测 ────────────────────────────────────────────────────────────

async def run_baseline(year: int) -> list[PositionSummary]:
    repo = HistoricalDataRepository()
    backtester = Backtester(exchange_gateway=None, data_repository=repo)
    start_time, end_time = year_range_ms(year)

    request = BacktestRequest(
        symbol=SYMBOL, timeframe=TIMEFRAME, mode="v3_pms",
        start_time=start_time, end_time=end_time, limit=9000,
        slippage_rate=BNB9_SLIPPAGE, tp_slippage_rate=BNB9_TP_SLIPPAGE,
        fee_rate=BNB9_FEE, initial_balance=INITIAL_BALANCE,
    )
    request.risk_overrides = RESEARCH_RISK
    request.order_strategy = ORDER_STRATEGY

    overrides = BASELINE_RUNTIME_OVERRIDES.model_copy(deep=True)
    overrides.allowed_directions = ["LONG"]

    report = await backtester.run_backtest(request, runtime_overrides=overrides)
    if isinstance(report, PMSBacktestReport):
        return report.positions
    return []


async def load_klines(timeframe: str, year: int) -> list[KlineData]:
    repo = HistoricalDataRepository()
    # Load from previous year for warmup
    start_time, _ = year_range_ms(year - 1)
    _, end_time = year_range_ms(year)
    return await repo.get_klines(SYMBOL, timeframe, start_time, end_time, limit=20000)


# ─── 特征计算 ────────────────────────────────────────────────────────────

def find_kline_idx_before(klines: list[KlineData], timestamp_ms: int, use_close_time: bool = False) -> Optional[int]:
    """
    Find the index of the last kline before timestamp_ms.
    If use_close_time=True, use close_time = timestamp + period_ms for anti-lookahead.
    """
    best_idx = None
    for i, kl in enumerate(klines):
        if use_close_time:
            # Determine period from timeframe
            if hasattr(kl, 'timeframe') and kl.timeframe:
                tf = kl.timeframe
            else:
                tf = "1h"
            period_ms = {"1h": HOUR_MS, "4h": 4 * HOUR_MS, "1d": DAY_MS}.get(tf, HOUR_MS)
            close_time = kl.timestamp + period_ms
            if close_time <= timestamp_ms:
                best_idx = i
        else:
            if kl.timestamp < timestamp_ms:
                best_idx = i
    return best_idx


def compute_features_for_trade(
    pos: PositionSummary,
    klines_1h: list[KlineData],
    klines_4h: list[KlineData],
    klines_1d: list[KlineData],
    year: int,
) -> Optional[TradeFeatures]:
    """Compute all features and result labels for a single trade."""
    entry_time = pos.entry_time
    entry_price = float(pos.entry_price)

    # ── 找信号 K ──
    # 信号 K = entry 之前最近的 1h K 线
    signal_idx = find_kline_idx_before(klines_1h, entry_time, use_close_time=False)
    if signal_idx is None or signal_idx < 10:
        return None

    signal_kl = klines_1h[signal_idx]

    tf = TradeFeatures(
        year=year,
        position_id=pos.position_id or "",
        entry_time=entry_time,
        entry_price=entry_price,
        exit_price=float(pos.exit_price),
        realized_pnl=float(pos.realized_pnl),
        exit_reason=pos.exit_reason or "unknown",
        is_win=float(pos.realized_pnl) > 0,
    )

    closes_1h = [float(kl.close) for kl in klines_1h]
    closes_4h = [float(kl.close) for kl in klines_4h]
    closes_1d = [float(kl.close) for kl in klines_1d]

    # ── 1. EMA slopes ──
    ema_1h = compute_ema_series(closes_1h, EMA_PERIOD_1H)
    tf.ema_1h_slope = compute_ema_slope(ema_1h, signal_idx, lookback=5)

    # Find 4h kline before entry (anti-lookahead)
    idx_4h = find_kline_idx_before(klines_4h, entry_time, use_close_time=True)
    if idx_4h is not None and idx_4h >= EMA_PERIOD_4H + 5:
        ema_4h = compute_ema_series(closes_4h, EMA_PERIOD_4H)
        tf.ema_4h_slope = compute_ema_slope(ema_4h, idx_4h, lookback=5)
        tf.price_dist_ema_4h = (closes_4h[idx_4h] - ema_4h[idx_4h]) / ema_4h[idx_4h] * 100 if ema_4h[idx_4h] else None

    # Find 1d kline before entry (anti-lookahead)
    idx_1d = find_kline_idx_before(klines_1d, entry_time, use_close_time=True)
    if idx_1d is not None and idx_1d >= EMA_PERIOD_1D + 5:
        ema_1d = compute_ema_series(closes_1d, EMA_PERIOD_1D)
        tf.ema_1d_slope = compute_ema_slope(ema_1d, idx_1d, lookback=5)
        tf.price_dist_ema_1d = (closes_1d[idx_1d] - ema_1d[idx_1d]) / ema_1d[idx_1d] * 100 if ema_1d[idx_1d] else None

    # ── 2. Price distance to 1h EMA ──
    if ema_1h[signal_idx] is not None and ema_1h[signal_idx] > 0:
        tf.price_dist_ema_1h = (closes_1h[signal_idx] - ema_1h[signal_idx]) / ema_1h[signal_idx] * 100

    # ── 3. Signal K range ──
    sig_high = float(signal_kl.high)
    sig_low = float(signal_kl.low)
    sig_close = float(signal_kl.close)
    if sig_close > 0:
        tf.signal_k_range_pct = (sig_high - sig_low) / sig_close * 100

    # ── 4. Recent N bars return ──
    if signal_idx >= 5:
        tf.recent_5bar_return = (closes_1h[signal_idx] - closes_1h[signal_idx - 5]) / closes_1h[signal_idx - 5] * 100
    if signal_idx >= 10:
        tf.recent_10bar_return = (closes_1h[signal_idx] - closes_1h[signal_idx - 10]) / closes_1h[signal_idx - 10] * 100

    # ── 5. Recent N bars volatility ──
    if signal_idx >= 5:
        returns_5 = []
        for j in range(signal_idx - 4, signal_idx + 1):
            if closes_1h[j - 1] > 0:
                returns_5.append((closes_1h[j] - closes_1h[j - 1]) / closes_1h[j - 1] * 100)
        if len(returns_5) >= 2:
            tf.recent_5bar_volatility = statistics.stdev(returns_5)
    if signal_idx >= 10:
        returns_10 = []
        for j in range(signal_idx - 9, signal_idx + 1):
            if closes_1h[j - 1] > 0:
                returns_10.append((closes_1h[j] - closes_1h[j - 1]) / closes_1h[j - 1] * 100)
        if len(returns_10) >= 2:
            tf.recent_10bar_volatility = statistics.stdev(returns_10)

    # ── 6. MTF trend ──
    if idx_4h is not None and idx_4h >= 5:
        ema_4h_full = compute_ema_series(closes_4h, EMA_PERIOD_4H)
        if ema_4h_full[idx_4h] is not None and ema_4h_full[idx_4h - 5] is not None:
            tf.mtf_4h_bullish = ema_4h_full[idx_4h] > ema_4h_full[idx_4h - 5]
    if idx_1d is not None and idx_1d >= 5:
        ema_1d_full = compute_ema_series(closes_1d, EMA_PERIOD_1D)
        if ema_1d_full[idx_1d] is not None and ema_1d_full[idx_1d - 5] is not None:
            tf.mtf_1d_bullish = ema_1d_full[idx_1d] > ema_1d_full[idx_1d - 5]

    # ── 结果标签 ──
    # MFE/MAE: use 1h klines after entry
    subsequent_1h = klines_1h[signal_idx + 1:]  # bars after signal K

    # Stop distance for R calculation
    stop_dist = entry_price - sig_low  # LONG: entry - signal_low
    if stop_dist <= 0:
        stop_dist = entry_price * 0.01  # fallback

    mfe_24h = 0.0
    mae_24h = 0.0
    mfe_full = 0.0
    mae_full = 0.0
    reach_1r = False
    reach_2r = False
    reach_3_5r = False
    first_touch_bullish = None

    for bar_i, kl in enumerate(subsequent_1h):
        k_high = float(kl.high)
        k_low = float(kl.low)

        # MFE (max favorable excursion for LONG = max high above entry)
        favorable = (k_high - entry_price) / entry_price * 100
        if favorable > mfe_full:
            mfe_full = favorable
        if bar_i < 24 and favorable > mfe_24h:
            mfe_24h = favorable

        # MAE (max adverse excursion for LONG = max low below entry)
        adverse = (entry_price - k_low) / entry_price * 100
        if adverse > mae_full:
            mae_full = adverse
        if bar_i < 24 and adverse > mae_24h:
            mae_24h = adverse

        # R reach
        if k_high >= entry_price + 1.0 * stop_dist:
            reach_1r = True
        if k_high >= entry_price + 2.0 * stop_dist:
            reach_2r = True
        if k_high >= entry_price + 3.5 * stop_dist:
            reach_3_5r = True

        # First touch
        if bar_i == 0:
            first_touch_bullish = float(kl.close) > entry_price

    tf.mfe_24h = round(mfe_24h, 4)
    tf.mae_24h = round(mae_24h, 4)
    tf.mfe_full = round(mfe_full, 4)
    tf.mae_full = round(mae_full, 4)
    tf.high_follow_through = mfe_24h >= HIGH_MFE_THRESHOLD
    tf.very_high_follow_through = mfe_24h >= VERY_HIGH_MFE_THRESHOLD
    tf.reach_1r = reach_1r
    tf.reach_2r = reach_2r
    tf.reach_3_5r = reach_3_5r
    tf.first_touch_bullish = first_touch_bullish

    return tf


# ─── 分桶统计 ────────────────────────────────────────────────────────────

def bucketize(values: list[Optional[float]], n_buckets: int = 3) -> list[Optional[int]]:
    """Assign values to buckets (1..n_buckets). None stays None."""
    valid = [(i, v) for i, v in enumerate(values) if v is not None]
    if not valid:
        return [None] * len(values)
    sorted_vals = sorted(valid, key=lambda x: x[1])
    result = [None] * len(values)
    for rank, (orig_idx, _) in enumerate(sorted_vals):
        bucket = min(rank * n_buckets // len(sorted_vals) + 1, n_buckets)
        result[orig_idx] = bucket
    return result


def compute_bucket_stats(trades: list[TradeFeatures], bucket_values: list[Optional[int]], n_buckets: int = 3) -> dict:
    """Compute stats per bucket."""
    buckets = {}
    for b in range(1, n_buckets + 1):
        bucket_trades = [t for t, bv in zip(trades, bucket_values) if bv == b]
        if not bucket_trades:
            buckets[b] = {"count": 0}
            continue

        mfe_24h_vals = [t.mfe_24h for t in bucket_trades if t.mfe_24h is not None]
        mae_24h_vals = [t.mae_24h for t in bucket_trades if t.mae_24h is not None]
        pnls = [t.realized_pnl for t in bucket_trades]
        wins = [t for t in bucket_trades if t.is_win]
        high_ft = [t for t in bucket_trades if t.high_follow_through]
        very_high_ft = [t for t in bucket_trades if t.very_high_follow_through]
        reach_1r = [t for t in bucket_trades if t.reach_1r]
        reach_2r = [t for t in bucket_trades if t.reach_2r]
        reach_3_5r = [t for t in bucket_trades if t.reach_3_5r]

        buckets[b] = {
            "count": len(bucket_trades),
            "avg_mfe_24h": round(statistics.mean(mfe_24h_vals), 4) if mfe_24h_vals else None,
            "avg_mae_24h": round(statistics.mean(mae_24h_vals), 4) if mae_24h_vals else None,
            "win_rate": round(len(wins) / len(bucket_trades), 4),
            "pnl": round(sum(pnls), 2),
            "high_ft_pct": round(len(high_ft) / len(bucket_trades) * 100, 1),
            "very_high_ft_pct": round(len(very_high_ft) / len(bucket_trades) * 100, 1),
            "reach_1r_pct": round(len(reach_1r) / len(bucket_trades) * 100, 1),
            "reach_2r_pct": round(len(reach_2r) / len(bucket_trades) * 100, 1),
            "reach_3_5r_pct": round(len(reach_3_5r) / len(bucket_trades) * 100, 1),
        }

    return buckets


def compute_boolean_stats(trades: list[TradeFeatures], bool_values: list[Optional[bool]]) -> dict:
    """Compute stats for boolean features (True vs False)."""
    result = {}
    for label, val in [("true", True), ("false", False)]:
        bucket_trades = [t for t, bv in zip(trades, bool_values) if bv == val]
        if not bucket_trades:
            result[label] = {"count": 0}
            continue

        mfe_24h_vals = [t.mfe_24h for t in bucket_trades if t.mfe_24h is not None]
        mae_24h_vals = [t.mae_24h for t in bucket_trades if t.mae_24h is not None]
        pnls = [t.realized_pnl for t in bucket_trades]
        wins = [t for t in bucket_trades if t.is_win]
        high_ft = [t for t in bucket_trades if t.high_follow_through]
        very_high_ft = [t for t in bucket_trades if t.very_high_follow_through]
        reach_1r = [t for t in bucket_trades if t.reach_1r]
        reach_2r = [t for t in bucket_trades if t.reach_2r]
        reach_3_5r = [t for t in bucket_trades if t.reach_3_5r]

        result[label] = {
            "count": len(bucket_trades),
            "avg_mfe_24h": round(statistics.mean(mfe_24h_vals), 4) if mfe_24h_vals else None,
            "avg_mae_24h": round(statistics.mean(mae_24h_vals), 4) if mae_24h_vals else None,
            "win_rate": round(len(wins) / len(bucket_trades), 4),
            "pnl": round(sum(pnls), 2),
            "high_ft_pct": round(len(high_ft) / len(bucket_trades) * 100, 1),
            "very_high_ft_pct": round(len(very_high_ft) / len(bucket_trades) * 100, 1),
            "reach_1r_pct": round(len(reach_1r) / len(bucket_trades) * 100, 1),
            "reach_2r_pct": round(len(reach_2r) / len(bucket_trades) * 100, 1),
            "reach_3_5r_pct": round(len(reach_3_5r) / len(bucket_trades) * 100, 1),
        }

    return result


# ─── 主实验 ──────────────────────────────────────────────────────────────

async def run_all() -> dict:
    all_trades: list[TradeFeatures] = []

    for year in YEARS:
        print(f"\n>>> Year {year}", flush=True)

        # Run baseline
        print(f"  {year}: Running baseline backtest...", flush=True)
        positions = await run_baseline(year)
        print(f"  {year}: {len(positions)} positions", flush=True)

        # Load klines
        print(f"  {year}: Loading klines...", flush=True)
        klines_1h = await load_klines("1h", year)
        klines_4h = await load_klines("4h", year)
        klines_1d = await load_klines("1d", year)
        print(f"  {year}: 1h={len(klines_1h)} 4h={len(klines_4h)} 1d={len(klines_1d)}", flush=True)

        # Compute features for each trade
        year_trades = []
        for pos in positions:
            tf = compute_features_for_trade(pos, klines_1h, klines_4h, klines_1d, year)
            if tf is not None:
                year_trades.append(tf)
                all_trades.append(tf)

        print(f"  {year}: {len(year_trades)} trades with features", flush=True)

    # ── 分桶分析 ──
    feature_analysis = {}

    # Continuous features → 3-bucket
    continuous_features = [
        ("ema_1h_slope", lambda t: t.ema_1h_slope),
        ("ema_4h_slope", lambda t: t.ema_4h_slope),
        ("ema_1d_slope", lambda t: t.ema_1d_slope),
        ("price_dist_ema_1h", lambda t: t.price_dist_ema_1h),
        ("price_dist_ema_4h", lambda t: t.price_dist_ema_4h),
        ("price_dist_ema_1d", lambda t: t.price_dist_ema_1d),
        ("signal_k_range_pct", lambda t: t.signal_k_range_pct),
        ("recent_5bar_return", lambda t: t.recent_5bar_return),
        ("recent_10bar_return", lambda t: t.recent_10bar_return),
        ("recent_5bar_volatility", lambda t: t.recent_5bar_volatility),
        ("recent_10bar_volatility", lambda t: t.recent_10bar_volatility),
    ]

    for feat_name, feat_fn in continuous_features:
        values = [feat_fn(t) for t in all_trades]
        bucket_values = bucketize(values, n_buckets=3)

        # Per-year analysis
        yearly = {}
        for year in YEARS:
            year_trades = [t for t in all_trades if t.year == year]
            year_values = [feat_fn(t) for t in year_trades]
            year_buckets = bucketize(year_values, n_buckets=3)
            yearly[year] = compute_bucket_stats(year_trades, year_buckets)

        # Overall
        overall = compute_bucket_stats(all_trades, bucket_values)

        # Compute bucket boundaries for interpretability
        valid_vals = [v for v in values if v is not None]
        if valid_vals:
            sorted_v = sorted(valid_vals)
            n = len(sorted_v)
            boundaries = {
                "bucket1_max": round(sorted_v[n // 3 - 1], 4) if n >= 3 else None,
                "bucket2_max": round(sorted_v[2 * n // 3 - 1], 4) if n >= 3 else None,
            }
        else:
            boundaries = {}

        feature_analysis[feat_name] = {
            "type": "continuous",
            "overall": overall,
            "yearly": yearly,
            "boundaries": boundaries,
        }

    # Boolean features
    boolean_features = [
        ("mtf_4h_bullish", lambda t: t.mtf_4h_bullish),
        ("mtf_1d_bullish", lambda t: t.mtf_1d_bullish),
    ]

    for feat_name, feat_fn in boolean_features:
        values = [feat_fn(t) for t in all_trades]

        yearly = {}
        for year in YEARS:
            year_trades = [t for t in all_trades if t.year == year]
            year_values = [feat_fn(t) for t in year_trades]
            yearly[year] = compute_boolean_stats(year_trades, year_values)

        overall = compute_boolean_stats(all_trades, values)

        feature_analysis[feat_name] = {
            "type": "boolean",
            "overall": overall,
            "yearly": yearly,
        }

    # ── Follow-through 概览 ──
    ft_overview = {}
    for year in YEARS:
        year_trades = [t for t in all_trades if t.year == year]
        if not year_trades:
            continue
        ft_overview[year] = {
            "total": len(year_trades),
            "high_ft_count": sum(1 for t in year_trades if t.high_follow_through),
            "high_ft_pct": round(sum(1 for t in year_trades if t.high_follow_through) / len(year_trades) * 100, 1),
            "very_high_ft_count": sum(1 for t in year_trades if t.very_high_follow_through),
            "very_high_ft_pct": round(sum(1 for t in year_trades if t.very_high_follow_through) / len(year_trades) * 100, 1),
            "avg_mfe_24h": round(statistics.mean([t.mfe_24h for t in year_trades if t.mfe_24h is not None]), 4),
            "avg_mae_24h": round(statistics.mean([t.mae_24h for t in year_trades if t.mae_24h is not None]), 4),
            "reach_1r_pct": round(sum(1 for t in year_trades if t.reach_1r) / len(year_trades) * 100, 1),
            "reach_2r_pct": round(sum(1 for t in year_trades if t.reach_2r) / len(year_trades) * 100, 1),
            "reach_3_5r_pct": round(sum(1 for t in year_trades if t.reach_3_5r) / len(year_trades) * 100, 1),
            "first_touch_bullish_pct": round(sum(1 for t in year_trades if t.first_touch_bullish) / len(year_trades) * 100, 1),
        }

    return {
        "follow_through_overview": ft_overview,
        "feature_analysis": feature_analysis,
        "total_trades": len(all_trades),
    }


# ─── 报告生成 ────────────────────────────────────────────────────────────

def generate_json_report(results: dict) -> dict:
    return {
        "title": "H3a Follow-through Feature Check",
        "date": "2026-04-28",
        "hypothesis": "H3a: Can pre-entry observable features predict low MFE / low follow-through?",
        "risk_profile": "research baseline (exposure=2.0, daily_max_trades=50)",
        "mfe_thresholds": {"high": HIGH_MFE_THRESHOLD, "very_high": VERY_HIGH_MFE_THRESHOLD},
        "adx_status": "TODO - not implemented in current codebase",
        "results": results,
    }


def generate_markdown_report(results: dict) -> str:
    lines = []
    lines.append("# H3a: 入场前特征预测 follow-through 能力验证")
    lines.append("")
    lines.append("> **日期**: 2026-04-28")
    lines.append("> **假设 H3a**: 入场前可观测特征是否能预测低 MFE / 低 follow-through？")
    lines.append("> **方法**: 基线回测 + 多周期 K 线特征计算 + 分桶统计")
    lines.append("> **基线**: ETH 1h LONG-only, EMA50, BNB9 成本, Research 口径")
    lines.append("> **MFE 阈值**: high_follow_through = MFE_24h >= 2.0%, very_high = MFE_24h >= 3.0%")
    lines.append("> **ADX**: 标记为 TODO（当前代码未实现），不为此改核心代码")
    lines.append("")

    # ── 1. Follow-through 概览 ──
    lines.append("## 1. Follow-through 概览")
    lines.append("")
    ft = results["follow_through_overview"]
    lines.append("| 年份 | Trades | High FT% | Very High FT% | Avg MFE_24h | Avg MAE_24h | +1R% | +2R% | +3.5R% | First-touch bullish% |")
    lines.append("|------|--------|----------|---------------|-------------|-------------|------|------|--------|---------------------|")
    for year in YEARS:
        yd = ft.get(year, {})
        lines.append(
            f"| {year} | {yd.get('total', 0)} | {yd.get('high_ft_pct', 0):.1f}% | {yd.get('very_high_ft_pct', 0):.1f}% "
            f"| {yd.get('avg_mfe_24h', 0):.2f}% | {yd.get('avg_mae_24h', 0):.2f}% "
            f"| {yd.get('reach_1r_pct', 0):.1f}% | {yd.get('reach_2r_pct', 0):.1f}% | {yd.get('reach_3_5r_pct', 0):.1f}% "
            f"| {yd.get('first_touch_bullish_pct', 0):.1f}% |"
        )
    lines.append("")

    # ── 2. 特征分桶分析 ──
    lines.append("## 2. 特征分桶分析")
    lines.append("")

    fa = results["feature_analysis"]

    # Sort features by discriminability (high_ft_pct spread between buckets)
    feature_discriminability = []
    for feat_name, feat_data in fa.items():
        overall = feat_data.get("overall", {})
        if feat_data["type"] == "continuous":
            ft_pcts = [overall.get(b, {}).get("high_ft_pct", 0) for b in [1, 2, 3]]
            spread = max(ft_pcts) - min(ft_pcts) if all(overall.get(b, {}).get("count", 0) > 0 for b in [1, 2, 3]) else 0
        else:
            ft_pcts = [overall.get("true", {}).get("high_ft_pct", 0), overall.get("false", {}).get("high_ft_pct", 0)]
            spread = abs(ft_pcts[0] - ft_pcts[1]) if overall.get("true", {}).get("count", 0) > 0 and overall.get("false", {}).get("count", 0) > 0 else 0
        feature_discriminability.append((feat_name, spread, feat_data))

    feature_discriminability.sort(key=lambda x: x[1], reverse=True)

    for feat_name, spread, feat_data in feature_discriminability:
        lines.append(f"### {feat_name} (区分度: {spread:.1f}pp)")
        lines.append("")

        overall = feat_data.get("overall", {})
        boundaries = feat_data.get("boundaries", {})

        if feat_data["type"] == "continuous":
            if boundaries:
                lines.append(f"分桶边界: B1 <= {boundaries.get('bucket1_max', '?')}, B2 <= {boundaries.get('bucket2_max', '?')}, B3 > {boundaries.get('bucket2_max', '?')}")
                lines.append("")

            lines.append("| 桶 | Count | Avg MFE_24h | Avg MAE_24h | WR | PnL | High FT% | +1R% | +2R% | +3.5R% |")
            lines.append("|-----|-------|-------------|-------------|-----|-----|----------|------|------|--------|")
            for b in [1, 2, 3]:
                bd = overall.get(b, {})
                if bd.get("count", 0) == 0:
                    continue
                lines.append(
                    f"| B{b} | {bd.get('count', 0)} | {bd.get('avg_mfe_24h', 0):.2f}% | {bd.get('avg_mae_24h', 0):.2f}% "
                    f"| {bd.get('win_rate', 0):.1%} | {bd.get('pnl', 0):+.2f} "
                    f"| {bd.get('high_ft_pct', 0):.1f}% | {bd.get('reach_1r_pct', 0):.1f}% "
                    f"| {bd.get('reach_2r_pct', 0):.1f}% | {bd.get('reach_3_5r_pct', 0):.1f}% |"
                )
            lines.append("")

            # Per-year stability check
            lines.append(f"**跨年稳定性**:")
            yearly = feat_data.get("yearly", {})
            for year in YEARS:
                yd = yearly.get(year, {})
                ft_pcts = [yd.get(b, {}).get("high_ft_pct", 0) for b in [1, 2, 3]]
                counts = [yd.get(b, {}).get("count", 0) for b in [1, 2, 3]]
                lines.append(f"- {year}: B1={ft_pcts[0]:.1f}%({counts[0]}) B2={ft_pcts[1]:.1f}%({counts[1]}) B3={ft_pcts[2]:.1f}%({counts[2]})")
            lines.append("")

        else:  # boolean
            lines.append("| 值 | Count | Avg MFE_24h | Avg MAE_24h | WR | PnL | High FT% | +1R% | +2R% | +3.5R% |")
            lines.append("|-----|-------|-------------|-------------|-----|-----|----------|------|------|--------|")
            for label in ["true", "false"]:
                bd = overall.get(label, {})
                if bd.get("count", 0) == 0:
                    continue
                lines.append(
                    f"| {label} | {bd.get('count', 0)} | {bd.get('avg_mfe_24h', 0):.2f}% | {bd.get('avg_mae_24h', 0):.2f}% "
                    f"| {bd.get('win_rate', 0):.1%} | {bd.get('pnl', 0):+.2f} "
                    f"| {bd.get('high_ft_pct', 0):.1f}% | {bd.get('reach_1r_pct', 0):.1f}% "
                    f"| {bd.get('reach_2r_pct', 0):.1f}% | {bd.get('reach_3_5r_pct', 0):.1f}% |"
                )
            lines.append("")

            # Per-year stability
            lines.append(f"**跨年稳定性**:")
            yearly = feat_data.get("yearly", {})
            for year in YEARS:
                yd = yearly.get(year, {})
                true_ft = yd.get("true", {}).get("high_ft_pct", 0)
                false_ft = yd.get("false", {}).get("high_ft_pct", 0)
                true_n = yd.get("true", {}).get("count", 0)
                false_n = yd.get("false", {}).get("count", 0)
                lines.append(f"- {year}: true={true_ft:.1f}%({true_n}) false={false_ft:.1f}%({false_n}) diff={true_ft - false_ft:+.1f}pp")
            lines.append("")

    # ── 3. 区分度排名 ──
    lines.append("## 3. 区分度排名")
    lines.append("")
    lines.append("| 排名 | 特征 | 区分度 (pp) | 跨年稳定？ |")
    lines.append("|------|------|------------|----------|")

    for rank, (feat_name, spread, feat_data) in enumerate(feature_discriminability, 1):
        # Check cross-year stability
        yearly = feat_data.get("yearly", {})
        stable = True
        if feat_data["type"] == "continuous":
            # Check if direction is consistent across years
            year_directions = []
            for year in YEARS:
                yd = yearly.get(year, {})
                ft_pcts = [yd.get(b, {}).get("high_ft_pct", 0) for b in [1, 2, 3]]
                if all(yd.get(b, {}).get("count", 0) >= 3 for b in [1, 2, 3]):
                    direction = ft_pcts[2] - ft_pcts[0]  # B3 - B1
                    year_directions.append(direction)
            if year_directions:
                # Stable if all directions have same sign
                stable = all(d * year_directions[0] >= 0 for d in year_directions)
            else:
                stable = False
        else:
            year_diffs = []
            for year in YEARS:
                yd = yearly.get(year, {})
                true_ft = yd.get("true", {}).get("high_ft_pct", 0)
                false_ft = yd.get("false", {}).get("high_ft_pct", 0)
                if yd.get("true", {}).get("count", 0) >= 3 and yd.get("false", {}).get("count", 0) >= 3:
                    year_diffs.append(true_ft - false_ft)
            if year_diffs:
                stable = all(d * year_diffs[0] >= 0 for d in year_diffs)
            else:
                stable = False

        lines.append(f"| {rank} | {feat_name} | {spread:.1f} | {'Yes' if stable else 'No'} |")
    lines.append("")

    # ── 4. 验证分析 ──
    lines.append("## 4. 验证分析")
    lines.append("")

    # Find top features
    top_features = [(fn, sp, fd) for fn, sp, fd in feature_discriminability[:5]]
    lines.append("### 4a. 是否存在入场前可解释特征能预测 low follow-through？")
    lines.append("")
    for feat_name, spread, feat_data in top_features:
        overall = feat_data.get("overall", {})
        if feat_data["type"] == "continuous":
            b1_ft = overall.get(1, {}).get("high_ft_pct", 0)
            b3_ft = overall.get(3, {}).get("high_ft_pct", 0)
            lines.append(f"- **{feat_name}**: B1 high_ft={b1_ft:.1f}% vs B3={b3_ft:.1f}% (spread={spread:.1f}pp)")
        else:
            true_ft = overall.get("true", {}).get("high_ft_pct", 0)
            false_ft = overall.get("false", {}).get("high_ft_pct", 0)
            lines.append(f"- **{feat_name}**: true={true_ft:.1f}% vs false={false_ft:.1f}% (spread={spread:.1f}pp)")
    lines.append("")

    # 4b. Cross-year stability
    lines.append("### 4b. 区分度是否跨年稳定？")
    lines.append("")
    for feat_name, spread, feat_data in top_features[:3]:
        yearly = feat_data.get("yearly", {})
        lines.append(f"**{feat_name}**:")
        for year in YEARS:
            yd = yearly.get(year, {})
            if feat_data["type"] == "continuous":
                ft_pcts = [yd.get(b, {}).get("high_ft_pct", 0) for b in [1, 2, 3]]
                lines.append(f"  {year}: B1={ft_pcts[0]:.1f}% B2={ft_pcts[1]:.1f}% B3={ft_pcts[2]:.1f}%")
            else:
                true_ft = yd.get("true", {}).get("high_ft_pct", 0)
                false_ft = yd.get("false", {}).get("high_ft_pct", 0)
                lines.append(f"  {year}: true={true_ft:.1f}% false={false_ft:.1f}%")
        lines.append("")

    # ── 5. 最终结论 ──
    lines.append("## 5. 最终结论")
    lines.append("")

    # Decision logic
    has_stable_predictor = False
    for feat_name, spread, feat_data in feature_discriminability:
        if spread < 10:  # less than 10pp spread is not meaningful
            continue
        yearly = feat_data.get("yearly", {})
        stable = True
        if feat_data["type"] == "continuous":
            year_directions = []
            for year in YEARS:
                yd = yearly.get(year, {})
                ft_pcts = [yd.get(b, {}).get("high_ft_pct", 0) for b in [1, 2, 3]]
                if all(yd.get(b, {}).get("count", 0) >= 3 for b in [1, 2, 3]):
                    direction = ft_pcts[2] - ft_pcts[0]
                    year_directions.append(direction)
            if year_directions:
                stable = all(d * year_directions[0] >= 0 for d in year_directions)
            else:
                stable = False
        else:
            year_diffs = []
            for year in YEARS:
                yd = yearly.get(year, {})
                true_ft = yd.get("true", {}).get("high_ft_pct", 0)
                false_ft = yd.get("false", {}).get("high_ft_pct", 0)
                if yd.get("true", {}).get("count", 0) >= 3 and yd.get("false", {}).get("count", 0) >= 3:
                    year_diffs.append(true_ft - false_ft)
            if year_diffs:
                stable = all(d * year_diffs[0] >= 0 for d in year_diffs)
            else:
                stable = False

        if stable and spread >= 10:
            has_stable_predictor = True
            break

    if has_stable_predictor:
        h3a_verdict = "弱通过"
        h3b_recommendation = "值得进入 H3b 动态 TP2 proxy 实验"
        stop_h3 = "否"
    elif any(sp >= 10 for _, sp, _ in feature_discriminability):
        h3a_verdict = "弱通过"
        h3b_recommendation = "有条件进入 H3b（区分度存在但不跨年稳定，需谨慎）"
        stop_h3 = "否"
    else:
        h3a_verdict = "不通过"
        h3b_recommendation = "不建议进入 H3b"
        stop_h3 = "是，应停止 H3 动态退出方向"

    lines.append(f"**H3a 判定**: {h3a_verdict}")
    lines.append("")
    lines.append(f"- **是否存在入场前可解释特征能预测 low follow-through**: {'是' if has_stable_predictor else '否/不稳定'}")
    lines.append(f"- **是否值得进入 H3b 动态 TP2 proxy**: {h3b_recommendation}")
    lines.append(f"- **如果没有预测力，是否停止 H3 动态退出方向**: {stop_h3}")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("> **重要**: 本报告为 research-only 特征分析，不涉及任何 runtime 修改。")
    lines.append("> ADX 标记为 TODO（当前代码未实现），不为此改核心代码。")
    lines.append("> first-touch 仅作为结果标签输出，不作为入场前特征。")

    return "\n".join(lines)


# ─── 主入口 ──────────────────────────────────────────────────────────────

async def main():
    print("=" * 60)
    print("  H3a: Follow-through Feature Check")
    print("  入场前可观测特征是否能预测低 MFE / 低 follow-through？")
    print("=" * 60, flush=True)

    results = await run_all()

    # Generate JSON report
    json_report = generate_json_report(results)
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(json_report, f, indent=2, ensure_ascii=False)
    print(f"\nJSON report saved: {JSON_PATH}", flush=True)

    # Generate Markdown report
    md_report = generate_markdown_report(results)
    with open(MD_PATH, "w", encoding="utf-8") as f:
        f.write(md_report)
    print(f"Markdown report saved: {MD_PATH}", flush=True)

    # Quick summary
    ft = results["follow_through_overview"]
    print(f"\n{'='*60}")
    print("  Follow-through Overview")
    print(f"{'='*60}")
    for year in YEARS:
        yd = ft.get(year, {})
        print(
            f"  {year}: T={yd.get('total', 0)} HighFT={yd.get('high_ft_pct', 0):.1f}% "
            f"AvgMFE={yd.get('avg_mfe_24h', 0):.2f}% +1R={yd.get('reach_1r_pct', 0):.1f}% +2R={yd.get('reach_2r_pct', 0):.1f}% +3.5R={yd.get('reach_3_5r_pct', 0):.1f}%",
            flush=True,
        )

    # Top discriminative features
    fa = results["feature_analysis"]
    feature_spreads = []
    for fn, fd in fa.items():
        overall = fd.get("overall", {})
        if fd["type"] == "continuous":
            ft_pcts = [overall.get(b, {}).get("high_ft_pct", 0) for b in [1, 2, 3]]
            spread = max(ft_pcts) - min(ft_pcts)
        else:
            true_ft = overall.get("true", {}).get("high_ft_pct", 0)
            false_ft = overall.get("false", {}).get("high_ft_pct", 0)
            spread = abs(true_ft - false_ft)
        feature_spreads.append((fn, spread))

    feature_spreads.sort(key=lambda x: x[1], reverse=True)
    print(f"\n  Top discriminative features:")
    for fn, sp in feature_spreads[:5]:
        print(f"    {fn}: {sp:.1f}pp", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
