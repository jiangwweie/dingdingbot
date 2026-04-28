#!/usr/bin/env python3
"""
H6a: Donchian 20-bar Breakout LONG-only Proxy
验证 ETH/USDT:USDT 1h 上 Donchian 20-bar 收盘突破 LONG-only 是否有基础 alpha 痕迹

约束：
- research-only
- 不改 src 核心代码（standalone proxy，不使用 Backtester）
- 不改 runtime profile
- 不新增 DonchianStrategy
- 不做参数搜索（仅 lookback=20）
- 报告标注为 proxy result，不等同正式 backtester result

策略：
- 主周期：1h
- Lookback：20 根已收盘 1h K
- 入场信号：当前 1h K close > 前 20 根 K 的 high
- 入场价格：下一根 K open × (1 + entry_slippage)
- 止损：前 20 根 K 的 low
- 方向：LONG-only
- 过滤器：
  - EMA50 trend：close > EMA50 + min_distance_pct=0.5%
  - MTF 4h EMA60：只允许 4h bullish trend
- 止盈：TP1=1.0R (50%), TP2=3.5R (50%)
- BE=False, trailing=False
- 成本：fee=0.0405%, entry_slippage=0.01%, tp_slippage=0
- 风控：max_loss_percent=1%, max_total_exposure=2.0, initial_balance=10000
"""

import asyncio
import sys
import json
from pathlib import Path
from datetime import datetime
from decimal import Decimal, ROUND_DOWN
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict

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
DONCHIAN_LOOKBACK = 20
EMA_PERIOD = 50
MTF_EMA_PERIOD = 60
MIN_DISTANCE_PCT = Decimal("0.005")  # 0.5%

# 成本口径 (BNB9)
ENTRY_SLIPPAGE = Decimal("0.0001")
FEE_RATE = Decimal("0.000405")
TP_SLIPPAGE = Decimal("0")

# 止盈参数
TP_RATIOS = [Decimal("0.5"), Decimal("0.5")]
TP_TARGETS = [Decimal("1.0"), Decimal("3.5")]  # R multiples

# 风控
INITIAL_BALANCE = Decimal("10000")
MAX_LOSS_PCT = Decimal("0.01")
MAX_TOTAL_EXPOSURE = Decimal("2.0")
DAILY_MAX_TRADES = 50


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
class Trade:
    signal_ts: int
    entry_ts: int
    entry_price: Decimal
    stop_loss: Decimal
    tp1_price: Decimal
    tp2_price: Decimal
    r_multiple: Decimal  # (entry - stop)
    qty: Decimal
    exit_ts: Optional[int] = None
    exit_price: Optional[Decimal] = None
    pnl: Decimal = Decimal("0")
    fees: Decimal = Decimal("0")
    exit_reason: str = ""  # "TP1", "TP2", "SL", "EOD"
    holding_bars: int = 0
    _tp1_hit: bool = False
    partial_pnl: Decimal = Decimal("0")
    partial_fees: Decimal = Decimal("0")


@dataclass
class YearStats:
    year: int
    trades: int = 0
    wins: int = 0
    losses: int = 0
    pnl: Decimal = Decimal("0")
    fees: Decimal = Decimal("0")
    max_dd: Decimal = Decimal("0")
    max_dd_pct: Decimal = Decimal("0")
    peak_balance: Decimal = Decimal("0")
    tp1_count: int = 0
    tp2_count: int = 0
    sl_count: int = 0
    signals_fired: int = 0
    position_rejected: int = 0
    holding_bars: List[int] = field(default_factory=list)
    stop_distances: List[Decimal] = field(default_factory=list)


# ============================================================
# 指标计算
# ============================================================
def compute_ema(prices: List[Decimal], period: int) -> List[Optional[Decimal]]:
    """计算 EMA 序列，返回与 prices 等长的列表，前 period-1 个为 None"""
    if not prices:
        return []
    result: List[Optional[Decimal]] = [None] * len(prices)
    if len(prices) < period:
        return result

    # 初始 SMA
    sma = sum(prices[:period]) / Decimal(period)
    result[period - 1] = sma

    k = Decimal(2) / (Decimal(period) + Decimal(1))
    prev = sma
    for i in range(period, len(prices)):
        ema = prices[i] * k + prev * (Decimal(1) - k)
        result[i] = ema
        prev = ema

    return result


def compute_donchian_high(klines: List[Kline], idx: int, lookback: int) -> Optional[Decimal]:
    """计算 idx 之前的 lookback 根 K 的最高价（不含 idx 本身）"""
    if idx < lookback:
        return None
    # idx-lookback 到 idx-1 (不含 idx)
    window = klines[idx - lookback: idx]
    if len(window) < lookback:
        return None
    return max(k.high for k in window)


def compute_donchian_low(klines: List[Kline], idx: int, lookback: int) -> Optional[Decimal]:
    """计算 idx 之前的 lookback 根 K 的最低价（不含 idx 本身）"""
    if idx < lookback:
        return None
    window = klines[idx - lookback: idx]
    if len(window) < lookback:
        return None
    return min(k.low for k in window)


# ============================================================
# MTF 对齐
# ============================================================
def build_mtf_ema_map(klines_4h: List[Kline], ema_period: int) -> Dict[int, Decimal]:
    """
    构建 4h K 线时间戳 → EMA 值的映射
    关键：4h K 的 EMA 只在该 K 收盘后才可用
    """
    closes_4h = [k.close for k in klines_4h]
    ema_values = compute_ema(closes_4h, ema_period)

    result = {}
    for i, k in enumerate(klines_4h):
        if ema_values[i] is not None:
            result[k.timestamp] = ema_values[i]
    return result


def get_mtf_trend(
    signal_ts: int,
    klines_4h: List[Kline],
    mtf_ema_map: Dict[int, Decimal],
) -> Optional[bool]:
    """
    获取信号时刻的 4h EMA 趋势
    使用 signal_ts 之前最后一个已收盘的 4h K 的 EMA
    """
    # 找到 signal_ts 之前最后一个 4h K
    last_closed_4h = None
    for k in klines_4h:
        # 4h K 的收盘时间 = timestamp + 4h_ms
        candle_close_time = k.timestamp + 4 * 3600 * 1000
        if candle_close_time <= signal_ts:
            last_closed_4h = k
        else:
            break

    if last_closed_4h is None:
        return None

    ema_val = mtf_ema_map.get(last_closed_4h.timestamp)
    if ema_val is None:
        return None

    return last_closed_4h.close > ema_val  # True = bullish


# ============================================================
# 代理撮合引擎
# ============================================================
class DonchianProxy:
    """Donchian 20-bar Breakout Proxy 撮合"""

    def __init__(self):
        self.repo: Optional[HistoricalDataRepository] = None

    async def setup(self):
        self.repo = HistoricalDataRepository(DB_PATH)
        await self.repo.initialize()

    async def teardown(self):
        if self.repo:
            await self.repo.close()

    async def fetch_klines(self, start_ts: int, end_ts: int, extra_lookback_ms: int = 0) -> Tuple[List[Kline], List[Kline]]:
        """
        获取 1h 和 4h K 线
        extra_lookback_ms: 额外回看时间（用于 EMA warmup）
        """
        fetch_start = start_ts - extra_lookback_ms

        raw_1h = await self.repo.get_klines(SYMBOL, TIMEFRAME, fetch_start, end_ts, limit=100000)
        raw_4h = await self.repo.get_klines(SYMBOL, HIGHER_TF, fetch_start, end_ts, limit=100000)

        klines_1h = [
            Kline(
                timestamp=k.timestamp,
                open=k.open, high=k.high, low=k.low, close=k.close, volume=k.volume
            )
            for k in raw_1h
        ]
        klines_4h = [
            Kline(
                timestamp=k.timestamp,
                open=k.open, high=k.high, low=k.low, close=k.close, volume=k.volume
            )
            for k in raw_4h
        ]

        return klines_1h, klines_4h

    def run_year(self, year: int, klines_1h: List[Kline], klines_4h: List[Kline]) -> YearStats:
        """运行单年回测"""
        stats = YearStats(year=year)

        # EMA50 on 1h
        closes_1h = [k.close for k in klines_1h]
        ema50 = compute_ema(closes_1h, EMA_PERIOD)

        # MTF EMA60 on 4h
        mtf_ema_map = build_mtf_ema_map(klines_4h, MTF_EMA_PERIOD)

        # 确定该年的起始 idx
        year_start_ts = int(datetime(year, 1, 1).timestamp() * 1000)
        year_start_idx = 0
        for i, k in enumerate(klines_1h):
            if k.timestamp >= year_start_ts:
                year_start_idx = i
                break

        # 最小 warmup: EMA50 需要 50 bars + Donchian 20 bars = 70 bars
        min_warmup = max(EMA_PERIOD, DONCHIAN_LOOKBACK) + 10
        if year_start_idx < min_warmup:
            year_start_idx = min_warmup

        balance = INITIAL_BALANCE
        peak_balance = INITIAL_BALANCE
        active_position: Optional[Trade] = None
        closed_trades: List[Trade] = []
        partial_exits: List[Dict] = []  # 记录每次 partial exit 的 PnL

        for idx in range(year_start_idx, len(klines_1h) - 1):
            kline = klines_1h[idx]
            next_kline = klines_1h[idx + 1]

            # 更新 peak / dd (只在无仓位时检查)
            if active_position is None:
                if balance > peak_balance:
                    peak_balance = balance
                dd = peak_balance - balance
                dd_pct = dd / peak_balance if peak_balance > Decimal("0") else Decimal("0")
                if dd_pct > stats.max_dd_pct:
                    stats.max_dd_pct = dd_pct
                    stats.max_dd = dd

            # ---- 处理活跃仓位 ----
            if active_position is not None:
                pos = active_position
                pos.holding_bars += 1

                # 检查止损
                if kline.low <= pos.stop_loss:
                    exit_price = pos.stop_loss
                    gross_pnl = (exit_price - pos.entry_price) * pos.qty
                    fee = abs(exit_price * pos.qty) * FEE_RATE
                    net_pnl = gross_pnl - fee
                    pos.exit_price = exit_price
                    pos.exit_ts = kline.timestamp
                    pos.pnl += net_pnl  # 累计 PnL（含之前 partial exits）
                    pos.fees += fee
                    pos.exit_reason = "SL"
                    stats.sl_count += 1
                    if net_pnl > Decimal("0"):
                        stats.wins += 1
                    else:
                        stats.losses += 1
                    stats.pnl += net_pnl
                    stats.fees += fee
                    stats.holding_bars.append(pos.holding_bars)
                    balance += net_pnl
                    active_position = None
                    closed_trades.append(pos)
                    continue

                # 检查 TP1（只触发一次）
                if not pos._tp1_hit and kline.high >= pos.tp1_price and pos.qty > Decimal("0"):
                    tp1_qty = pos.qty * TP_RATIOS[0]
                    exit_price_p1 = pos.tp1_price * (Decimal(1) - TP_SLIPPAGE)
                    gross_pnl_p1 = (exit_price_p1 - pos.entry_price) * tp1_qty
                    fee_p1 = abs(exit_price_p1 * tp1_qty) * FEE_RATE
                    net_pnl_p1 = gross_pnl_p1 - fee_p1
                    balance += net_pnl_p1
                    stats.pnl += net_pnl_p1
                    stats.fees += fee_p1
                    stats.tp1_count += 1
                    pos.partial_pnl += net_pnl_p1
                    pos.partial_fees += fee_p1
                    pos.qty -= tp1_qty
                    pos._tp1_hit = True
                    # 移动止损到 entry (breakeven)
                    pos.stop_loss = pos.entry_price

                    if pos.qty <= Decimal("0"):
                        pos.exit_price = exit_price_p1
                        pos.exit_ts = kline.timestamp
                        pos.exit_reason = "TP1_FULL"
                        stats.holding_bars.append(pos.holding_bars)
                        if pos.partial_pnl > Decimal("0"):
                            stats.wins += 1
                        else:
                            stats.losses += 1
                        active_position = None
                        closed_trades.append(pos)
                        continue

                # 检查 TP2
                if pos._tp1_hit and kline.high >= pos.tp2_price and pos.qty > Decimal("0"):
                    exit_price_p2 = pos.tp2_price * (Decimal(1) - TP_SLIPPAGE)
                    gross_pnl_p2 = (exit_price_p2 - pos.entry_price) * pos.qty
                    fee_p2 = abs(exit_price_p2 * pos.qty) * FEE_RATE
                    net_pnl_p2 = gross_pnl_p2 - fee_p2
                    balance += net_pnl_p2
                    stats.pnl += net_pnl_p2
                    stats.fees += fee_p2
                    stats.tp2_count += 1
                    pos.partial_pnl += net_pnl_p2
                    pos.partial_fees += fee_p2
                    pos.exit_price = exit_price_p2
                    pos.exit_ts = kline.timestamp
                    pos.exit_reason = "TP2"
                    stats.holding_bars.append(pos.holding_bars)
                    if pos.partial_pnl > Decimal("0"):
                        stats.wins += 1
                    else:
                        stats.losses += 1
                    active_position = None
                    closed_trades.append(pos)
                    continue

                # 年末强制平仓
                is_year_end = (kline.timestamp >= int(datetime(year, 12, 31, 20, 0, 0).timestamp() * 1000))
                if is_year_end and pos.qty > Decimal("0"):
                    exit_price = kline.close
                    gross_pnl = (exit_price - pos.entry_price) * pos.qty
                    fee = abs(exit_price * pos.qty) * FEE_RATE
                    net_pnl = gross_pnl - fee
                    balance += net_pnl
                    stats.pnl += net_pnl
                    stats.fees += fee
                    pos.partial_pnl += net_pnl
                    pos.partial_fees += fee
                    pos.exit_price = exit_price
                    pos.exit_ts = kline.timestamp
                    pos.exit_reason = "EOD"
                    stats.holding_bars.append(pos.holding_bars)
                    if pos.partial_pnl > Decimal("0"):
                        stats.wins += 1
                    else:
                        stats.losses += 1
                    active_position = None
                    closed_trades.append(pos)
                    continue

            # ---- 信号检测 ----
            if active_position is not None:
                continue  # 已有仓位，不重复开仓

            # Donchian 20-bar high/low
            dc_high = compute_donchian_high(klines_1h, idx, DONCHIAN_LOOKBACK)
            dc_low = compute_donchian_low(klines_1h, idx, DONCHIAN_LOOKBACK)
            if dc_high is None or dc_low is None:
                continue

            # 信号条件：close > N-bar high
            if kline.close <= dc_high:
                continue

            stats.signals_fired += 1

            # Filter: EMA50
            if ema50[idx] is None:
                continue
            ema_distance = (kline.close - ema50[idx]) / ema50[idx]
            if kline.close <= ema50[idx] or ema_distance < MIN_DISTANCE_PCT:
                continue

            # Filter: MTF 4h bullish
            mtf_bullish = get_mtf_trend(kline.timestamp, klines_4h, mtf_ema_map)
            if mtf_bullish is None or not mtf_bullish:
                continue

            # 止损 = N-bar low
            stop_loss = dc_low

            # R multiple
            entry_est = kline.close  # 估算 entry (实际是 next open)
            r_multiple = entry_est - stop_loss
            if r_multiple <= Decimal("0"):
                continue

            # TP prices
            tp1_price = entry_est + r_multiple * TP_TARGETS[0]
            tp2_price = entry_est + r_multiple * TP_TARGETS[1]

            # 仓位计算：risk-based sizing with exposure cap
            risk_amount = balance * MAX_LOSS_PCT
            stop_distance_pct = r_multiple / entry_est
            if stop_distance_pct <= Decimal("0"):
                continue

            qty = risk_amount / stop_distance_pct

            # Exposure cap: 不拒绝，而是截断到最大允许仓位
            notional = qty * entry_est
            max_notional = balance * MAX_TOTAL_EXPOSURE
            if notional > max_notional:
                qty = max_notional / entry_est

            # 检查每日交易次数
            day_trades = sum(1 for t in closed_trades
                           if t.entry_ts and abs(t.entry_ts - kline.timestamp) < 86400000)
            if day_trades >= DAILY_MAX_TRADES:
                continue

            # 入场价格 = 下一根 K open + slippage
            actual_entry = next_kline.open * (Decimal(1) + ENTRY_SLIPPAGE)
            actual_stop = stop_loss
            actual_r = actual_entry - actual_stop
            actual_tp1 = actual_entry + actual_r * TP_TARGETS[0]
            actual_tp2 = actual_entry + actual_r * TP_TARGETS[1]

            # 重新计算 qty 用实际 entry + exposure cap
            actual_risk_pct = actual_r / actual_entry
            if actual_risk_pct <= Decimal("0"):
                continue
            qty = risk_amount / actual_risk_pct
            actual_notional = qty * actual_entry
            if actual_notional > balance * MAX_TOTAL_EXPOSURE:
                qty = (balance * MAX_TOTAL_EXPOSURE) / actual_entry

            active_position = Trade(
                signal_ts=kline.timestamp,
                entry_ts=next_kline.timestamp,
                entry_price=actual_entry,
                stop_loss=actual_stop,
                tp1_price=actual_tp1,
                tp2_price=actual_tp2,
                r_multiple=actual_r,
                qty=qty,
            )

        # 年末未平仓强制平仓
        if active_position is not None and active_position.qty > Decimal("0"):
            last_k = klines_1h[-1]
            exit_price = last_k.close
            gross_pnl = (exit_price - active_position.entry_price) * active_position.qty
            fee = abs(exit_price * active_position.qty) * FEE_RATE
            net_pnl = gross_pnl - fee
            balance += net_pnl
            stats.pnl += net_pnl
            stats.fees += fee
            active_position.partial_pnl += net_pnl
            active_position.partial_fees += fee
            active_position.exit_price = exit_price
            active_position.exit_ts = last_k.timestamp
            active_position.exit_reason = "EOD"
            stats.holding_bars.append(active_position.holding_bars)
            if active_position.partial_pnl > Decimal("0"):
                stats.wins += 1
            else:
                stats.losses += 1
            closed_trades.append(active_position)

        stats.trades = len(closed_trades)
        return stats

    async def run_all_years(self) -> Dict[int, YearStats]:
        """运行 2022-2025 所有年份"""
        # EMA50 warmup 需要约 60 bars = 60h，但为了安全取 200 bars
        warmup_ms = 200 * 3600 * 1000  # 200 小时

        start_ts = int(datetime(2022, 1, 1).timestamp() * 1000) - warmup_ms
        end_ts = int(datetime(2025, 12, 31, 23, 59, 59).timestamp() * 1000)

        print("Fetching 1h klines...")
        raw_1h = await self.repo.get_klines(SYMBOL, TIMEFRAME, start_ts, end_ts, limit=100000)
        klines_1h = [
            Kline(timestamp=k.timestamp, open=k.open, high=k.high, low=k.low, close=k.close, volume=k.volume)
            for k in raw_1h
        ]
        print(f"  Got {len(klines_1h)} 1h klines")

        print("Fetching 4h klines...")
        raw_4h = await self.repo.get_klines(SYMBOL, HIGHER_TF, start_ts, end_ts, limit=100000)
        klines_4h = [
            Kline(timestamp=k.timestamp, open=k.open, high=k.high, low=k.low, close=k.close, volume=k.volume)
            for k in raw_4h
        ]
        print(f"  Got {len(klines_4h)} 4h klines")

        results = {}
        for year in [2022, 2023, 2024, 2025]:
            print(f"\nRunning {year}...")
            stats = self.run_year(year, klines_1h, klines_4h)
            results[year] = stats
            print(f"  Trades: {stats.trades}, PnL: {stats.pnl:.2f}, "
                  f"WR: {100*stats.wins/stats.trades:.1f}%" if stats.trades > 0 else "  No trades")
            if stats.trades > 0:
                print(f"  TP1: {stats.tp1_count}, TP2: {stats.tp2_count}, SL: {stats.sl_count}")
                print(f"  Signals: {stats.signals_fired}, Rejected: {stats.position_rejected}")

        return results


# ============================================================
# 报告生成
# ============================================================
def format_year_stats(s: YearStats) -> Dict:
    avg_hold = sum(s.holding_bars) / len(s.holding_bars) if s.holding_bars else 0
    avg_stop = sum(s.stop_distances) / len(s.stop_distances) if s.stop_distances else 0
    wr = s.wins / s.trades if s.trades > 0 else 0

    return {
        "year": s.year,
        "pnl": float(s.pnl),
        "trades": s.trades,
        "wins": s.wins,
        "losses": s.losses,
        "win_rate": round(wr, 4),
        "max_dd_pct": round(float(s.max_dd_pct), 4),
        "tp1_count": s.tp1_count,
        "tp2_count": s.tp2_count,
        "sl_count": s.sl_count,
        "tp1_pct": round(100 * s.tp1_count / s.trades, 1) if s.trades > 0 else 0,
        "tp2_pct": round(100 * s.tp2_count / s.trades, 1) if s.trades > 0 else 0,
        "sl_pct": round(100 * s.sl_count / s.trades, 1) if s.trades > 0 else 0,
        "signals_fired": s.signals_fired,
        "position_rejected": s.position_rejected,
        "avg_holding_bars": round(avg_hold, 1),
        "avg_holding_hours": round(avg_hold, 1),
        "avg_stop_r_multiple": round(float(avg_stop), 4),
        "fees": float(s.fees),
    }


def print_report(results: Dict[int, YearStats], baseline: Dict):
    """打印对比报告"""
    print("\n" + "=" * 80)
    print("H6a Donchian 20-bar Breakout LONG-only Proxy — 结果汇总")
    print("=" * 80)

    total_pnl = Decimal("0")
    total_trades = 0
    total_wins = 0

    for year in [2022, 2023, 2024, 2025]:
        s = results[year]
        total_pnl += s.pnl
        total_trades += s.trades
        total_wins += s.wins

        b = baseline.get(str(year), {})
        b_pnl = b.get("pnl", 0)
        b_trades = b.get("trades", 0)
        b_wr = b.get("win_rate", 0)

        wr = s.wins / s.trades * 100 if s.trades > 0 else 0
        b_wr_pct = b_wr * 100

        print(f"\n{year}:")
        print(f"  Donchian: PnL={s.pnl:8.2f}  Trades={s.trades:3d}  WR={wr:5.1f}%  MaxDD={s.max_dd_pct*100:5.2f}%")
        print(f"  Pinbar:   PnL={b_pnl:8.2f}  Trades={b_trades:3d}  WR={b_wr_pct:5.1f}%")
        print(f"  TP1={s.tp1_count}({s.tp1_count/s.trades*100:.0f}%) TP2={s.tp2_count}({s.tp2_count/s.trades*100:.0f}%) SL={s.sl_count}({s.sl_count/s.trades*100:.0f}%)" if s.trades > 0 else "  No trades")
        print(f"  Signals={s.signals_fired}  Position_Rejected={s.position_rejected}")

    avg_wr = total_wins / total_trades * 100 if total_trades > 0 else 0

    print(f"\n{'='*80}")
    print(f"3yr (2023-2025) Donchian: PnL={float(total_pnl):.2f}, Trades={total_trades}, WR={avg_wr:.1f}%")

    # Baseline 3yr
    b_total = sum(baseline.get(str(y), {}).get("pnl", 0) for y in [2023, 2024, 2025])
    b_trades_total = sum(baseline.get(str(y), {}).get("trades", 0) for y in [2023, 2024, 2025])
    print(f"3yr (2023-2025) Pinbar:   PnL={b_total:.2f}, Trades={b_trades_total}")

    # 判定
    print(f"\n{'='*80}")
    print("判定:")
    pnl_3yr = float(total_pnl)
    non_negative_years = sum(1 for y in [2023, 2024, 2025] if results[y].pnl >= Decimal("0"))

    if pnl_3yr > 0 and non_negative_years >= 2:
        print(f"  PASS: 3yr PnL={pnl_3yr:.2f} > 0, {non_negative_years}/3 年非负 → 进入 H6b OOS / SHORT shadow")
    elif pnl_3yr < -1000:
        print(f"  CLOSE: 3yr PnL={pnl_3yr:.2f} < -1000 → 关闭 Donchian 20 LONG，不进入参数搜索")
    elif total_trades < 10:
        print(f"  INSUFFICIENT: trades={total_trades} < 10 → 样本不足，不判定 alpha")
    else:
        max_dd = max(results[y].max_dd_pct for y in [2023, 2024, 2025])
        if max_dd > Decimal("0.50"):
            print(f"  RISK: MaxDD={max_dd*100:.2f}% > 50% → 不得进 runtime，进入风险结构复核")
        else:
            print(f"  NEUTRAL: 3yr PnL={pnl_3yr:.2f}, 需进一步分析")


# ============================================================
# Main
# ============================================================
async def main():
    proxy = DonchianProxy()
    try:
        await proxy.setup()
        results = await proxy.run_all_years()

        # 格式化输出
        report_data = {
            "title": "H6a Donchian 20-bar Breakout LONG-only Proxy",
            "date": datetime.now().isoformat()[:10],
            "hypothesis": "H6a: Donchian 20-bar 收盘突破 LONG-only 在 ETH 1h 上有基础 alpha 痕迹",
            "config": {
                "lookback": DONCHIAN_LOOKBACK,
                "ema_period": EMA_PERIOD,
                "mtf_ema_period": MTF_EMA_PERIOD,
                "min_distance_pct": float(MIN_DISTANCE_PCT),
                "tp_targets": [float(t) for t in TP_TARGETS],
                "tp_ratios": [float(r) for r in TP_RATIOS],
                "entry_slippage": float(ENTRY_SLIPPAGE),
                "fee_rate": float(FEE_RATE),
                "initial_balance": float(INITIAL_BALANCE),
                "max_loss_percent": float(MAX_LOSS_PCT),
                "max_total_exposure": float(MAX_TOTAL_EXPOSURE),
            },
            "results": {str(y): format_year_stats(s) for y, s in results.items()},
            "proxy_note": "This is a proxy result, not equivalent to official backtester result. Standalone撮合，不经过 Backtester v3_pms.",
        }

        # 保存 JSON
        reports_dir = PROJECT_ROOT / "reports" / "research"
        reports_dir.mkdir(parents=True, exist_ok=True)
        json_path = reports_dir / "donchian_h6a_proxy_2026-04-28.json"
        with open(json_path, "w") as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
        print(f"\nJSON saved: {json_path}")

        # 加载 baseline 对比
        baseline_path = reports_dir / "eth_baseline_oos_check_2026-04-28.json"
        baseline = {}
        if baseline_path.exists():
            with open(baseline_path) as f:
                baseline_data = json.load(f)
            baseline = baseline_data.get("results", {}).get("research", {})

        # 打印报告
        print_report(results, baseline)

    finally:
        await proxy.teardown()


if __name__ == "__main__":
    asyncio.run(main())
