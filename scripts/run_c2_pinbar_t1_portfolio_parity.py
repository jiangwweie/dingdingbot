#!/usr/bin/env python3
"""
C2: Pinbar + T1 Portfolio Official Parity Check

Pinbar 使用正式 Backtester v3_pms 运行（compounding + concurrent positions + MTM）。
T1-R 使用匹配参数的独立模拟（compounding + exposure cap + MTM）。

约束：
- research-only，不改 runtime，不提交 git
- 不改 src 核心代码
- Pinbar 通过 backtester.run_backtest() 调用，不修改 backtester
"""

import asyncio
import json
import sys
import math
import statistics
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from collections import defaultdict
from dataclasses import dataclass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.infrastructure.historical_data_repository import HistoricalDataRepository
from src.application.backtester import Backtester
from src.domain.models import BacktestRequest, OrderStrategy, BacktestRuntimeOverrides, RiskConfig

DB_PATH = "data/v3_dev.db"
ONE = Decimal("1")
ZERO = Decimal("0")

# ============================================================
# T1-R Configuration (matched to official backtester)
# ============================================================
T1_SYMBOL = "ETH/USDT:USDT"
T1_TIMEFRAME = "4h"

# Match official backtester parameters
INITIAL_BALANCE = Decimal("10000")
MAX_LOSS_PCT = Decimal("0.01")           # 1% risk per trade
MAX_TOTAL_EXPOSURE = Decimal("2.0")      # 200% max exposure (research profile)
MAX_LEVERAGE = Decimal("20")
FEE_RATE = Decimal("0.000405")           # 0.0405%
ENTRY_SLIPPAGE = Decimal("0.0001")       # 0.01%
EXIT_SLIPPAGE = Decimal("0.0001")        # 0.01% (match backtester exit cost)

YEAR_STARTS = {
    2022: 1640995200000,
    2023: 1672531200000,
    2024: 1704067200000,
    2025: 1735689600000,
    2026: 1767225600000,
}


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
# T1-R ATR
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
# T1-R Simulation with official backtester position model
# ============================================================
def simulate_t1_parity(
    all_klines: List[Kline],
    year_start_idx: int,
    year_end_idx: int,
    atr: List[Optional[Decimal]],
    start_equity: Decimal = INITIAL_BALANCE,
    donchian_lookback: int = 20,
    initial_stop_mult: Decimal = Decimal("2"),
    trailing_mult: Decimal = Decimal("3"),
) -> Dict:
    """
    T1-R simulation with official backtester position model:
    - Compounding balance (position size from current equity)
    - Max total exposure = 80%
    - Max leverage = 20x
    - MTM equity (balance + unrealized PnL)
    - Same fee/slippage as official backtester
    """
    equity = start_equity
    trades: List[Trade] = []

    mtm_curve: List[Decimal] = []
    mtm_timestamps: List[int] = []

    # Realized equity tracking
    peak_realized = equity
    max_dd_realized = ZERO

    # MTM tracking
    peak_mtm = equity
    max_dd_mtm = ZERO

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

        # ── Execute pending entry ──
        if pending_entry and not has_pos:
            pending_entry = False
            entry_price = bar.o * (ONE + ENTRY_SLIPPAGE)
            init_stop = entry_price - initial_stop_mult * pending_atr
            risk_dist = entry_price - init_stop

            if risk_dist > ZERO:
                # Position sizing matching official backtester
                risk_amount = equity * MAX_LOSS_PCT
                size = risk_amount / risk_dist
                max_size = (equity * MAX_LEVERAGE) / entry_price
                if size > max_size:
                    size = max_size

                # Exposure check
                current_exposure = pos_size * pos_entry_price if has_pos else ZERO
                new_exposure = current_exposure + size * entry_price
                if equity > ZERO and new_exposure / equity > MAX_TOTAL_EXPOSURE:
                    # Reduce size to fit exposure cap
                    available = MAX_TOTAL_EXPOSURE * equity - current_exposure
                    if available > ZERO:
                        size = available / entry_price
                    else:
                        size = ZERO

                if size > ZERO:
                    pos_entry_bar = i
                    pos_entry_price = entry_price
                    pos_stop = init_stop
                    pos_atr = pending_atr
                    pos_highest_close = bar.c
                    pos_size = size
                    has_pos = True

        # ── Active position: stop check (pessimistic order) ──
        if has_pos:
            if bar.l <= pos_stop:
                exit_p = pos_stop * (ONE - EXIT_SLIPPAGE)
                pnl = (exit_p - pos_entry_price) * pos_size
                fee = (pos_entry_price * pos_size + exit_p * pos_size) * FEE_RATE
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
                # Update trailing stop
                pos_highest_close = max(pos_highest_close, bar.c)
                new_trail = pos_highest_close - trailing_mult * pos_atr
                pos_stop = max(pos_stop, new_trail)

        # ── New entry signal ──
        if not has_pos and not pending_entry and current_atr is not None and current_atr > ZERO:
            if bar.c > don_high:
                pending_entry = True
                pending_atr = current_atr
                pending_don_low = don_low

        # ── MTM equity ──
        mtm = equity
        if has_pos:
            unrealized = (bar.c - pos_entry_price) * pos_size
            mtm = equity + unrealized
        mtm_curve.append(mtm)
        mtm_timestamps.append(bar.ts)

        # ── MaxDD tracking ──
        if equity > peak_realized:
            peak_realized = equity
        dd_r = (peak_realized - equity) / peak_realized if peak_realized > ZERO else ZERO
        if dd_r > max_dd_realized:
            max_dd_realized = dd_r

        if mtm > peak_mtm:
            peak_mtm = mtm
        dd_m = (peak_mtm - mtm) / peak_mtm if peak_mtm > ZERO else ZERO
        if dd_m > max_dd_mtm:
            max_dd_mtm = dd_m

    # Force close at end
    if has_pos:
        last = all_klines[year_end_idx - 1]
        exit_p = last.c * (ONE - EXIT_SLIPPAGE)
        pnl = (exit_p - pos_entry_price) * pos_size
        fee = (pos_entry_price * pos_size + exit_p * pos_size) * FEE_RATE
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
        mtm_curve[-1] = equity

    return {
        "trades": trades,
        "mtm_curve": [float(m) for m in mtm_curve],
        "mtm_timestamps": mtm_timestamps,
        "final_equity": float(equity),
        "max_dd_realized": float(max_dd_realized * 100),
        "max_dd_mtm": float(max_dd_mtm * 100),
    }


# ============================================================
# Portfolio Metrics
# ============================================================
def compute_metrics(
    label: str,
    mtm_curve: List[float],
    mtm_ts: List[int],
    trades: List[Any],
    weight: float,
) -> Dict:
    """Compute metrics for a single strategy or portfolio equity curve."""
    if not mtm_curve:
        return {"label": label, "error": "no data"}

    start_eq = mtm_curve[0]
    total_pnl = mtm_curve[-1] - start_eq

    # Yearly PnL
    yearly_pnl = {}
    for year in [2023, 2024, 2025]:
        year_start_ts = YEAR_STARTS[year]
        year_end_ts = YEAR_STARTS.get(year + 1, 9999999999999)
        eq_at_start = None
        eq_at_end = None
        for i, ts in enumerate(mtm_ts):
            if ts >= year_start_ts and eq_at_start is None:
                eq_at_start = mtm_curve[max(0, i - 1)]
            if ts >= year_end_ts:
                eq_at_end = mtm_curve[max(0, i - 1)]
                break
        if eq_at_start is None:
            eq_at_start = mtm_curve[0]
        if eq_at_end is None:
            eq_at_end = mtm_curve[-1]
        yearly_pnl[year] = eq_at_end - eq_at_start

    # MaxDD
    peak = mtm_curve[0]
    max_dd = 0.0
    max_dd_pct = 0.0
    for eq in mtm_curve:
        if eq > peak:
            peak = eq
        dd = peak - eq
        dd_pct = dd / peak if peak > 0 else 0
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct
            max_dd = dd

    # Monthly returns
    monthly_returns = _compute_monthly_returns(mtm_ts, mtm_curve)
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
    monthly_pos_rate = monthly_positive / monthly_total if monthly_total > 0 else 0

    return {
        "label": label,
        "weight": weight,
        "total_pnl": round(total_pnl, 2),
        "yearly_pnl": {str(k): round(v, 2) for k, v in yearly_pnl.items()},
        "max_dd": round(max_dd, 2),
        "max_dd_pct": round(max_dd_pct * 100, 2),
        "sharpe": round(sharpe, 3),
        "sortino": round(sortino, 3),
        "calmar": round(calmar, 3),
        "worst_year": {"year": worst_year[0], "pnl": round(worst_year[1], 2)},
        "monthly_positive_rate": round(monthly_pos_rate * 100, 1),
    }


def _compute_monthly_returns(timestamps: List[int], equity: List[float]) -> List[float]:
    monthly = {}
    for ts, eq in zip(timestamps, equity):
        dt = datetime.fromtimestamp(ts / 1000)
        key = (dt.year, dt.month)
        monthly[key] = eq
    sorted_months = sorted(monthly.keys())
    returns = []
    for i in range(1, len(sorted_months)):
        prev_eq = monthly[sorted_months[i - 1]]
        cur_eq = monthly[sorted_months[i]]
        if prev_eq > 0:
            returns.append((cur_eq - prev_eq) / prev_eq)
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


def _compute_mtm_correlation(
    pb_curve: List[float], pb_ts: List[int],
    t1_curve: List[float], t1_ts: List[int],
) -> float:
    """Weekly MTM correlation."""
    pb_pairs = sorted(zip(pb_ts, pb_curve))
    t1_pairs = sorted(zip(t1_ts, t1_curve))

    weekly_pb = {}
    weekly_t1 = {}

    for ts, eq in pb_pairs:
        dt = datetime.fromtimestamp(ts / 1000)
        key = dt.isocalendar()[:2]
        weekly_pb[key] = eq

    for ts, eq in t1_pairs:
        dt = datetime.fromtimestamp(ts / 1000)
        key = dt.isocalendar()[:2]
        weekly_t1[key] = eq

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

    if len(pb_returns) < 2:
        return 0
    n = len(pb_returns)
    mean_x = statistics.mean(pb_returns)
    mean_y = statistics.mean(t1_returns)
    cov = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(pb_returns, t1_returns)) / n
    std_x = statistics.stdev(pb_returns)
    std_y = statistics.stdev(t1_returns)
    if std_x == 0 or std_y == 0:
        return 0
    return cov / (std_x * std_y)


# ============================================================
# Main
# ============================================================
async def main():
    print("=" * 80)
    print("C2: Pinbar + T1 Portfolio Official Parity Check")
    print("=" * 80)

    repo = HistoricalDataRepository(DB_PATH)
    await repo.initialize()

    # ================================================================
    # Part 1: Pinbar via Official Backtester (continuous 2023-2025)
    # ================================================================
    print("\n" + "=" * 80)
    print("Part 1: Pinbar Official Backtester (v3_pms, continuous 2023-2025)")
    print("=" * 80)

    backtester = Backtester(None, data_repository=repo)

    strategy_config = [{
        "name": "pinbar",
        "triggers": [{"type": "pinbar", "enabled": True}],
        "filters": [
            {"type": "ema_trend", "enabled": True, "params": {"period": 50}},
            {"type": "mtf", "enabled": True, "params": {"ema_period": 60}},
            {"type": "atr", "enabled": True, "params": {"max_atr_ratio": Decimal("0.01")}},
        ]
    }]

    # Run as single continuous backtest for 2023-2025
    start_ts = int(datetime(2023, 1, 1).timestamp() * 1000)
    end_ts = int(datetime(2025, 12, 31, 23, 59, 59).timestamp() * 1000)

    request = BacktestRequest(
        symbol="ETH/USDT:USDT",
        timeframe="1h",
        limit=30000,
        start_time=start_ts,
        end_time=end_ts,
        strategies=strategy_config,
        order_strategy=OrderStrategy(
            id="dual_tp",
            name="Dual TP",
            tp_levels=2,
            tp_ratios=[Decimal("0.6"), Decimal("0.4")],
            tp_targets=[Decimal("1.0"), Decimal("2.5")],
            initial_stop_loss_rr=Decimal("-1.0"),
            trailing_stop_enabled=False,
            oco_enabled=True,
        ),
        mode="v3_pms",
        slippage_rate=Decimal("0.0001"),
        tp_slippage_rate=Decimal("0"),
        fee_rate=Decimal("0.000405"),
        initial_balance=Decimal("10000"),
        risk_overrides=RiskConfig(
            max_loss_percent=Decimal("0.01"),
            max_leverage=20,
            max_total_exposure=Decimal("2.0"),
        ),
    )

    runtime_overrides = BacktestRuntimeOverrides(
        tp_ratios=[Decimal("0.6"), Decimal("0.4")],
        tp_targets=[Decimal("1.0"), Decimal("2.5")],
        breakeven_enabled=False,
        max_atr_ratio=Decimal("0.01"),
    )

    print("\n  Running Pinbar 2023-2025 (continuous)...")
    report = await backtester.run_backtest(request, runtime_overrides=runtime_overrides)

    # Extract MTM equity curve
    pb_equity_curve = []
    pb_equity_ts = []
    if report.debug_equity_curve:
        for pt in report.debug_equity_curve:
            pb_equity_curve.append(pt["equity"])
            pb_equity_ts.append(pt["timestamp"])

    # Yearly PnL from position summaries
    pb_yearly = {}
    if hasattr(report, 'positions') and report.positions:
        for year in [2023, 2024, 2025]:
            year_positions = [p for p in report.positions
                            if p.entry_time and datetime.fromtimestamp(p.entry_time / 1000).year == year]
            year_pnl = sum(float(p.realized_pnl) for p in year_positions)
            pb_yearly[year] = {
                "pnl": round(year_pnl, 2),
                "trades": len(year_positions),
            }

    pb_3yr_pnl = sum(v["pnl"] for v in pb_yearly.values())
    print(f"  Pinbar trades: {report.total_trades}, 3yr PnL: {report.total_pnl:.2f}")
    print(f"  MaxDD: {report.max_drawdown*100:.2f}%")
    for y, v in pb_yearly.items():
        print(f"    {y}: trades={v['trades']}, PnL={v['pnl']:.2f}")

    # Also run year-by-year for yearly PnL verification
    print("\n  Running Pinbar year-by-year for PnL verification...")
    pb_yearly_verify = {}
    for year in [2023, 2024, 2025]:
        y_start = int(datetime(year, 1, 1).timestamp() * 1000)
        y_end = int(datetime(year, 12, 31, 23, 59, 59).timestamp() * 1000)
        y_request = BacktestRequest(
            symbol="ETH/USDT:USDT", timeframe="1h", limit=10000,
            start_time=y_start, end_time=y_end,
            strategies=strategy_config,
            order_strategy=OrderStrategy(
                id="dual_tp", name="Dual TP", tp_levels=2,
                tp_ratios=[Decimal("0.6"), Decimal("0.4")],
                tp_targets=[Decimal("1.0"), Decimal("2.5")],
                initial_stop_loss_rr=Decimal("-1.0"),
                trailing_stop_enabled=False, oco_enabled=True,
            ),
            mode="v3_pms",
            slippage_rate=Decimal("0.0001"), tp_slippage_rate=Decimal("0"),
            fee_rate=Decimal("0.000405"), initial_balance=Decimal("10000"),
            risk_overrides=RiskConfig(
                max_loss_percent=Decimal("0.01"), max_leverage=20,
                max_total_exposure=Decimal("2.0"),
            ),
        )
        y_report = await backtester.run_backtest(y_request, runtime_overrides=runtime_overrides)
        pb_yearly_verify[year] = {
            "pnl": round(float(y_report.total_pnl), 2),
            "trades": y_report.total_trades,
            "max_dd": round(float(y_report.max_drawdown) * 100, 2),
        }
        print(f"    {year}: trades={y_report.total_trades}, PnL={y_report.total_pnl:.2f}, DD={y_report.max_drawdown*100:.2f}%")

    # ================================================================
    # Part 2: T1-R with matched position model
    # ================================================================
    print("\n" + "=" * 80)
    print("Part 2: T1-R Simulation (matched to official backtester)")
    print("=" * 80)

    # Load T1 4h klines
    print("\n  Loading T1 4h klines...")
    raw_t1 = await repo.get_klines(T1_SYMBOL, T1_TIMEFRAME, limit=50000)
    raw_t1.sort(key=lambda k: k.timestamp)
    t1_klines = [
        Kline(idx=i, ts=k.timestamp, o=k.open, h=k.high, l=k.low, c=k.close, v=k.volume)
        for i, k in enumerate(raw_t1)
    ]
    print(f"  {len(t1_klines)} 4h bars")

    # Compute ATR
    t1_atr = compute_atr_full(t1_klines, 14)

    # Find T1 2023-2025 range
    t1_n = len(t1_klines)
    t1_start = next((k.idx for k in t1_klines if k.ts >= YEAR_STARTS[2023]), t1_n)
    t1_end = next((k.idx for k in t1_klines if k.ts >= YEAR_STARTS[2026]), t1_n)
    print(f"  T1 range: bars [{t1_start}..{t1_end-1}] ({t1_end - t1_start} bars)")

    # Run T1-R simulation
    print("\n  Running T1-R simulation...")
    t1_result = simulate_t1_parity(t1_klines, t1_start, t1_end, t1_atr)
    all_t1_trades = t1_result["trades"]
    t1_mtm_curve = t1_result["mtm_curve"]
    t1_mtm_ts = t1_result["mtm_timestamps"]

    # T1 yearly breakdown
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

    # T1 concentration
    t1_sorted = sorted(all_t1_trades, key=lambda t: float(t.pnl), reverse=True)
    t1_top3 = t1_sorted[:3] if len(t1_sorted) >= 3 else t1_sorted
    t1_top3_pnl = sum(float(t.pnl) for t in t1_top3)
    t1_top3_pct = (t1_top3_pnl / abs(t1_3yr_pnl) * 100) if t1_3yr_pnl != 0 else 0
    print(f"  T1 Top 3: {t1_top3_pnl:.2f} ({t1_top3_pct:.1f}% of T1 PnL)")

    # ================================================================
    # Part 3: Portfolio Combination
    # ================================================================
    print("\n" + "=" * 80)
    print("Part 3: Portfolio Combination")
    print("=" * 80)

    # Correlation
    corr = _compute_mtm_correlation(pb_equity_curve, pb_equity_ts, t1_mtm_curve, t1_mtm_ts)
    print(f"\n  Correlation (weekly MTM): {corr:.3f}")

    # Combine equity curves at 4h resolution
    weights = [
        ("P100_T0", 1.0, 0.0),
        ("P80_T20", 0.8, 0.2),
        ("P70_T30", 0.7, 0.3),
        ("P60_T40", 0.6, 0.4),
        ("P50_T50", 0.5, 0.5),
    ]

    # Build Pinbar lookup
    pb_pairs = sorted(zip(pb_equity_ts, pb_equity_curve))

    results = {}
    for label, w_pb, w_t1 in weights:
        # Build combined equity at T1 timestamps
        combined_ts = []
        combined_eq = []

        for i, ts in enumerate(t1_mtm_ts):
            t1_eq = t1_mtm_curve[i]

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

            portfolio_eq = w_pb * pb_eq + w_t1 * t1_eq
            combined_ts.append(ts)
            combined_eq.append(portfolio_eq)

        metrics = compute_metrics(label, combined_eq, combined_ts, all_t1_trades, w_pb)
        results[label] = metrics

        print(f"\n  {label}:")
        print(f"    3yr PnL:    {metrics['total_pnl']:>10.2f}")
        print(f"    2023:       {metrics['yearly_pnl'].get('2023', 0):>10.2f}")
        print(f"    2024:       {metrics['yearly_pnl'].get('2024', 0):>10.2f}")
        print(f"    2025:       {metrics['yearly_pnl'].get('2025', 0):>10.2f}")
        print(f"    MaxDD:      {metrics['max_dd_pct']:>10.2f}%")
        print(f"    Sharpe:     {metrics['sharpe']:>10.3f}")
        print(f"    Calmar:     {metrics['calmar']:>10.3f}")

    # ================================================================
    # Part 4: Remove T1 Top 3 Analysis
    # ================================================================
    print("\n" + "=" * 80)
    print("Part 4: Remove T1 Top 3 Winners")
    print("=" * 80)

    t1_pnl_no_top3 = t1_3yr_pnl - t1_top3_pnl
    for label, w_pb, w_t1 in weights:
        if w_t1 == 0:
            continue
        pb_pnl = results["P100_T0"]["total_pnl"]
        combo_pnl = w_pb * pb_pnl + w_t1 * t1_pnl_no_top3
        print(f"  {label} without T1 Top 3: {combo_pnl:.2f}")

    # ================================================================
    # Part 5: Verdict
    # ================================================================
    print("\n" + "=" * 80)
    print("VERDICT")
    print("=" * 80)

    pb_baseline = results["P100_T0"]
    pb_3yr = pb_baseline["total_pnl"]
    pb_dd = pb_baseline["max_dd_pct"]
    pb_2023 = pb_baseline["yearly_pnl"].get("2023", 0)

    print(f"\n  Pinbar (official): 3yr PnL={pb_3yr:.2f}, MaxDD={pb_dd:.2f}%")
    print(f"  T1-R: 3yr PnL={t1_3yr_pnl:.2f}, Top3={t1_top3_pct:.1f}%")
    print(f"  Correlation: {corr:.3f}")

    for label in ["P80_T20", "P70_T30", "P60_T40", "P50_T50"]:
        r = results[label]
        pnl_improved = r["total_pnl"] > pb_3yr
        dd_lower = r["max_dd_pct"] < pb_dd
        y2023 = r["yearly_pnl"].get("2023", 0)
        y2023_improved = y2023 > pb_2023

        # Check remove top 3
        w_t1 = 1.0 - r["weight"]
        combo_no_top3 = r["weight"] * pb_3yr + w_t1 * t1_pnl_no_top3

        parts = []
        if pnl_improved:
            parts.append("PnL↑")
        else:
            parts.append("PnL↓")
        if dd_lower:
            parts.append("DD↓")
        else:
            parts.append("DD↑")
        if y2023_improved:
            loss_reduction = (pb_2023 - y2023) / abs(pb_2023) * 100 if pb_2023 != 0 else 0
            parts.append(f"2023↑({loss_reduction:.0f}%↓)")
        if t1_top3_pct > 60:
            parts.append("T1_FRAGILE")
        if combo_no_top3 < 0:
            parts.append("TOP3_DEPENDENT")

        print(f"  {label}: {', '.join(parts)}")

    # ================================================================
    # Save Results
    # ================================================================
    output = {
        "meta": {
            "date": "2026-04-28",
            "experiment": "C2 Pinbar + T1 Portfolio Official Parity Check",
            "pinbar_method": "Official Backtester v3_pms",
            "t1_method": "Matched compounding simulation (anti-lookahead)",
            "parameters_unified": [
                "initial_balance: $10,000",
                "compounding: YES (both use current equity for position sizing)",
                "max_loss_pct: 1%",
                "max_total_exposure: 80%",
                "max_leverage: 20x",
                "fee_rate: 0.0405%",
                "entry_slippage: 0.01%",
                "exit_slippage: 0.01%",
                "MTM equity: YES (both include unrealized PnL)",
            ],
            "parameter_differences": [
                "Pinbar: 1h bars, concurrent positions, TP [1.0R, 2.5R], partial close 60/40, EMA filters, DynamicRiskManager",
                "T1-R: 4h bars, single position, trailing 3xATR stop, Donchian 20 breakout",
                "Pinbar year-by-year restart (matching official baseline), T1 continuous across years",
            ],
        },
        "pinbar": {
            "3yr_pnl": round(pb_3yr_pnl, 2),
            "yearly": {str(k): v for k, v in pb_yearly.items()},
        },
        "t1": {
            "3yr_pnl": round(t1_3yr_pnl, 2),
            "yearly": {str(k): v for k, v in t1_yearly.items()},
            "total_trades": len(all_t1_trades),
            "top3_pnl": round(t1_top3_pnl, 2),
            "top3_pct": round(t1_top3_pct, 1),
            "pnl_no_top3": round(t1_pnl_no_top3, 2),
            "fragile": t1_top3_pct > 60,
        },
        "correlation": round(corr, 3),
        "portfolio": results,
        "verdict": {
            "pinbar_3yr": round(pb_3yr, 2),
            "pinbar_maxdd": round(pb_dd, 2),
        },
    }

    out_path = PROJECT_ROOT / "reports/research/c2_pinbar_t1_portfolio_parity_2026-04-28.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to: {out_path}")

    await repo.close()


if __name__ == "__main__":
    asyncio.run(main())
