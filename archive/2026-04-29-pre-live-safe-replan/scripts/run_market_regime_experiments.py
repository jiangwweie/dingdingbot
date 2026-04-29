#!/usr/bin/env python3
"""
Market Regime E0-E4 实验矩阵执行脚本

研究层外部 gating 实验，不改引擎、不改 runtime。
基于 docs/planning/2026-04-28-market-regime-experiment-assessment.md

实验矩阵：
  E0: 基线对照（无 regime gate）
  E1: daily EMA250 bull-only（1d close > EMA250 才允许 LONG）
  E2: daily EMA250 + slope（1d close > EMA250 AND EMA250 slope > 0）
  E3: daily EMA200 bull-only（1d close > EMA200 才允许 LONG）
  E4: daily EMA250 bull/bear-flat + shadow tracking

反前瞻：regime 状态由 entry 时间戳之前的最后一根已闭合 1d K 线决定。
未知 regime（无足够 1d 数据）单独追踪，不静默合并。

输出：
  reports/research/market_regime_experiments_2026-04-28.json
  docs/planning/2026-04-28-market-regime-experiment-results.md
"""

import asyncio
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.application.backtester import Backtester
from src.application.research_control_plane import BASELINE_RUNTIME_OVERRIDES
from src.domain.models import (
    BacktestRequest,
    BacktestRuntimeOverrides,
    KlineData,
    OrderStrategy,
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
SLOPE_LOOKBACK = 5  # EMA slope: 当前 EMA vs 5 根（天）前的 EMA

# BNB9 风控参数（与基线一致）
RISK_CONFIG = RiskConfig(
    max_loss_percent=Decimal("0.01"),
    max_leverage=20,
    max_total_exposure=Decimal("2.0"),
    max_position_percent=Decimal("0.2"),
    daily_max_loss=Decimal("0.05"),
    daily_max_trades=50,
    min_balance=Decimal("100"),
)

REPORT_DIR = PROJECT_ROOT / "reports" / "research"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
JSON_PATH = REPORT_DIR / "market_regime_experiments_2026-04-28.json"
MD_PATH = PROJECT_ROOT / "docs" / "planning" / "2026-04-28-market-regime-experiment-results.md"


# ─── 数据模型 ───────────────────────────────────────────────────────────

@dataclass
class RegimeState:
    regime: str  # "bull" | "bear" | "unknown"
    close_1d: Optional[float] = None
    ema_value: Optional[float] = None
    ema_slope: Optional[float] = None  # current - lookback_ago
    candle_ts: Optional[int] = None  # the 1d candle used for regime


@dataclass
class ExperimentMetrics:
    experiment: str
    year: int
    pnl: float = 0.0
    trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    sharpe: float = 0.0
    max_dd: float = 0.0
    bull_days: int = 0
    bear_days: int = 0
    unknown_days: int = 0
    total_trading_days: int = 0
    # Shadow tracking (E4 only)
    shadow_pnl: float = 0.0
    shadow_trades: int = 0
    shadow_wins: int = 0
    shadow_win_rate: float = 0.0
    # MFE/MAE/reach rates — TODO (PositionSummary lacks excursion data)
    mfe_avg: Optional[float] = None
    mae_avg: Optional[float] = None
    reach_1r: Optional[float] = None
    reach_2r: Optional[float] = None
    reach_3_5r: Optional[float] = None
    first_touch: Optional[str] = None


# ─── 1d EMA 计算 ────────────────────────────────────────────────────────

def compute_1d_ema_series(klines_1d: list, period: int) -> dict[int, float]:
    """计算 1d EMA 序列，返回 {timestamp_ms: ema_value}。

    使用标准 EMA 公式：EMA_t = close_t * k + EMA_{t-1} * (1-k), k = 2/(period+1)
    前 period 根用 SMA 初始化。
    """
    if not klines_1d:
        return {}

    k = 2.0 / (period + 1)
    ema_series: dict[int, float] = {}

    # 前 period 根用 SMA 初始化
    closes = [float(kl.close) for kl in klines_1d]
    if len(closes) < period:
        # 数据不足，无法初始化 EMA
        return {}

    sma_init = sum(closes[:period]) / period
    ema_val = sma_init
    ema_series[klines_1d[period - 1].timestamp] = ema_val

    for i in range(period, len(closes)):
        ema_val = closes[i] * k + ema_val * (1 - k)
        ema_series[klines_1d[i].timestamp] = ema_val

    return ema_series


def compute_regime_at_entry(
    entry_timestamp_ms: int,
    ema_series: dict[int, float],
    klines_1d: list,
    regime_ema_period: int,
    require_slope: bool = False,
) -> RegimeState:
    """判断 entry 时刻的 regime 状态。

    反前瞻：只使用 entry_timestamp_ms 之前最后一根已闭合的 1d K 线。
    """
    # 找到 entry 之前的最后一根已闭合 1d K 线
    # 1d K 线在当天结束时闭合，即 close 时间戳 = 当天 00:00 UTC + 86400000ms
    # 我们需要找到 timestamp < entry_timestamp_ms 的最后一根
    last_closed_idx = -1
    for i, kl in enumerate(klines_1d):
        if kl.timestamp < entry_timestamp_ms:
            last_closed_idx = i
        else:
            break

    if last_closed_idx < 0:
        return RegimeState(regime="unknown")

    candle = klines_1d[last_closed_idx]
    close_1d = float(candle.close)

    # 查找这根 K 线对应的 EMA 值
    # EMA series 的 key 是 timestamp，我们需要找到 <= candle.timestamp 的最近 EMA
    ema_value = None
    for ts in sorted(ema_series.keys()):
        if ts <= candle.timestamp:
            ema_value = ema_series[ts]
        else:
            break

    if ema_value is None:
        return RegimeState(regime="unknown", close_1d=close_1d, candle_ts=candle.timestamp)

    # 基本判断：close > EMA → bull
    is_bull = close_1d > ema_value

    # EMA slope 判断（如果需要）
    ema_slope = None
    if require_slope:
        # 找 SLOPE_LOOKBACK 根前的 EMA
        # 从 klines_1d 中找到当前 candle 往前数 SLOPE_LOOKBACK 根
        lookback_idx = last_closed_idx - SLOPE_LOOKBACK
        if lookback_idx >= 0:
            lookback_ts = klines_1d[lookback_idx].timestamp
            lookback_ema = None
            for ts in sorted(ema_series.keys()):
                if ts <= lookback_ts:
                    lookback_ema = ema_series[ts]
                else:
                    break
            if lookback_ema is not None:
                ema_slope = ema_value - lookback_ema
                # slope > 0 才算 bull
                if is_bull and ema_slope <= 0:
                    is_bull = False
        else:
            # 无法计算 slope，视为 unknown
            return RegimeState(
                regime="unknown",
                close_1d=close_1d,
                ema_value=ema_value,
                ema_slope=ema_slope,
                candle_ts=candle.timestamp,
            )

    regime = "bull" if is_bull else "bear"
    return RegimeState(
        regime=regime,
        close_1d=close_1d,
        ema_value=ema_value,
        ema_slope=ema_slope,
        candle_ts=candle.timestamp,
    )


# ─── 回测执行 ────────────────────────────────────────────────────────────

def year_range_ms(year: int) -> tuple[int, int]:
    """返回指定年份的起止毫秒时间戳。"""
    start = int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    end = int(datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)
    return start, end


async def run_backtest_for_year(year: int) -> list[PositionSummary]:
    """对指定年份跑基线回测，返回仓位列表。"""
    repo = HistoricalDataRepository()
    backtester = Backtester(exchange_gateway=None, data_repository=repo)

    start_time, end_time = year_range_ms(year)

    request = BacktestRequest(
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        mode="v3_pms",
        start_time=start_time,
        end_time=end_time,
        limit=9000,
        slippage_rate=BNB9_SLIPPAGE,
        tp_slippage_rate=BNB9_TP_SLIPPAGE,
        fee_rate=BNB9_FEE,
        initial_balance=INITIAL_BALANCE,
    )
    request.risk_overrides = RISK_CONFIG
    request.order_strategy = OrderStrategy(
        id="eth_regime_research",
        name="ETH regime research",
        tp_levels=2,
        tp_ratios=[Decimal("0.5"), Decimal("0.5")],
        tp_targets=[Decimal("1.0"), Decimal("3.5")],
        initial_stop_loss_rr=Decimal("-1.0"),
        trailing_stop_enabled=False,
        oco_enabled=True,
    )

    report = await backtester.run_backtest(request, runtime_overrides=BASELINE_RUNTIME_OVERRIDES)
    return report.positions


async def load_1d_klines(year: int) -> list:
    """加载 1d K 线数据，包含前一年数据用于 EMA 预热。"""
    repo = HistoricalDataRepository()
    # 加载前一年 + 当年，确保 EMA 有足够预热
    start_time, _ = year_range_ms(year - 1)
    _, end_time = year_range_ms(year)
    klines = await repo.get_klines(SYMBOL, "1d", start_time, end_time, limit=1000)
    return klines


# ─── 指标计算 ────────────────────────────────────────────────────────────

def compute_proxy_metrics(positions: list[PositionSummary]) -> dict:
    """计算 proxy 指标（仓位级 PnL 累加，非 true equity curve）。"""
    if not positions:
        return {
            "pnl": 0.0, "trades": 0, "wins": 0, "losses": 0,
            "win_rate": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
            "sharpe": 0.0, "max_dd": 0.0,
        }

    pnl_list = [float(p.realized_pnl) for p in positions]
    total_pnl = sum(pnl_list)
    wins = [p for p in pnl_list if p > 0]
    losses = [p for p in pnl_list if p <= 0]
    win_rate = len(wins) / len(pnl_list) if pnl_list else 0.0
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0

    # Proxy Sharpe: mean(pnl_list) / std(pnl_list) * sqrt(trades)
    # 简化：用每笔 PnL 的 mean/std
    import statistics
    if len(pnl_list) >= 2:
        mean_pnl = statistics.mean(pnl_list)
        std_pnl = statistics.stdev(pnl_list)
        sharpe = (mean_pnl / std_pnl) if std_pnl > 0 else 0.0
    else:
        sharpe = 0.0

    # Proxy MaxDD: 累积 PnL 曲线的最大回撤
    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnl_list:
        cumulative += p
        if cumulative > peak:
            peak = cumulative
        dd = peak - cumulative
        if dd > max_dd:
            max_dd = dd

    return {
        "pnl": round(total_pnl, 2),
        "trades": len(positions),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(win_rate, 4),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "sharpe": round(sharpe, 4),
        "max_dd": round(max_dd, 2),
    }


def compute_regime_day_stats(
    klines_1d: list,
    ema_series: dict[int, float],
    year: int,
    require_slope: bool = False,
) -> dict:
    """统计当年 bull/bear/unknown 交易日占比。"""
    bull_days = 0
    bear_days = 0
    unknown_days = 0
    year_start_ms = int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    year_end_ms = int(datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)

    for kl in klines_1d:
        if kl.timestamp < year_start_ms or kl.timestamp > year_end_ms:
            continue

        close_1d = float(kl.close)
        # 找这根 K 线对应的 EMA
        ema_value = None
        for ts in sorted(ema_series.keys()):
            if ts <= kl.timestamp:
                ema_value = ema_series[ts]
            else:
                break

        if ema_value is None:
            unknown_days += 1
            continue

        is_bull = close_1d > ema_value

        if require_slope:
            idx = None
            for i, k in enumerate(klines_1d):
                if k.timestamp == kl.timestamp:
                    idx = i
                    break
            if idx is not None and idx >= SLOPE_LOOKBACK:
                lookback_ts = klines_1d[idx - SLOPE_LOOKBACK].timestamp
                lookback_ema = None
                for ts in sorted(ema_series.keys()):
                    if ts <= lookback_ts:
                        lookback_ema = ema_series[ts]
                    else:
                        break
                if lookback_ema is not None:
                    slope = ema_value - lookback_ema
                    if is_bull and slope <= 0:
                        is_bull = False
                else:
                    unknown_days += 1
                    continue
            else:
                unknown_days += 1
                continue

        if is_bull:
            bull_days += 1
        else:
            bear_days += 1

    total = bull_days + bear_days + unknown_days
    return {
        "bull_days": bull_days,
        "bear_days": bear_days,
        "unknown_days": unknown_days,
        "total_trading_days": total,
        "bull_pct": round(bull_days / total * 100, 1) if total > 0 else 0.0,
        "bear_pct": round(bear_days / total * 100, 1) if total > 0 else 0.0,
    }


# ─── 实验执行 ────────────────────────────────────────────────────────────

async def run_experiment(
    experiment_name: str,
    positions: list[PositionSummary],
    klines_1d: list,
    regime_ema_period: int,
    require_slope: bool = False,
    shadow_tracking: bool = False,
) -> dict:
    """执行单个实验，返回结果字典。"""
    # 计算 EMA 序列
    ema_series = compute_1d_ema_series(klines_1d, regime_ema_period)

    # 对每个仓位判断 regime
    retained = []
    filtered = []
    shadow_positions = []  # E4: bear regime 下被过滤的仓位

    for pos in positions:
        regime_state = compute_regime_at_entry(
            pos.entry_time,
            ema_series,
            klines_1d,
            regime_ema_period,
            require_slope=require_slope,
        )

        if regime_state.regime == "bull":
            retained.append(pos)
        elif regime_state.regime == "bear":
            filtered.append((pos, regime_state))
            if shadow_tracking:
                shadow_positions.append(pos)
        else:  # unknown
            # unknown regime 的仓位不纳入任何统计
            filtered.append((pos, regime_state))

    # 计算 retained 仓位的 proxy metrics
    metrics = compute_proxy_metrics(retained)

    # 计算 regime day stats
    day_stats = compute_regime_day_stats(klines_1d, ema_series, YEARS[0], require_slope)
    # 注意：day_stats 需要按年份计算，这里先占位

    result = {
        "experiment": experiment_name,
        "retained": metrics,
        "filtered_count": len(filtered),
        "unknown_count": sum(1 for _, rs in filtered if rs.regime == "unknown"),
        "day_stats": day_stats,  # 会被外层按年份覆盖
    }

    # Shadow tracking (E4)
    if shadow_tracking and shadow_positions:
        shadow_metrics = compute_proxy_metrics(shadow_positions)
        result["shadow"] = shadow_metrics

    return result


async def run_all_experiments():
    """执行 E0-E4 全部实验。"""
    all_results = {}

    for year in YEARS:
        print(f"\n{'='*60}")
        print(f"  Year {year}: Running baseline backtest...")
        print(f"{'='*60}")

        # 跑基线回测
        positions = await run_backtest_for_year(year)
        print(f"  Baseline positions: {len(positions)}")

        # 加载 1d 数据（含前一年预热）
        klines_1d = await load_1d_klines(year)
        print(f"  1d klines loaded: {len(klines_1d)} (including warmup)")

        year_results = {}

        # E0: 基线对照（无 regime gate）
        print(f"\n  E0: Baseline (no regime gate)")
        e0_metrics = compute_proxy_metrics(positions)
        year_results["E0"] = {"experiment": "E0", "retained": e0_metrics}

        # E1: daily EMA250 bull-only
        print(f"  E1: Daily EMA250 bull-only")
        e1_result = await run_experiment("E1", positions, klines_1d, regime_ema_period=250)
        year_results["E1"] = e1_result

        # E2: daily EMA250 + slope
        print(f"  E2: Daily EMA250 + slope")
        e2_result = await run_experiment("E2", positions, klines_1d, regime_ema_period=250, require_slope=True)
        year_results["E2"] = e2_result

        # E3: daily EMA200 bull-only
        print(f"  E3: Daily EMA200 bull-only")
        e3_result = await run_experiment("E3", positions, klines_1d, regime_ema_period=200)
        year_results["E3"] = e3_result

        # E4: daily EMA250 bull/bear-flat + shadow tracking
        print(f"  E4: Daily EMA250 + shadow tracking")
        e4_result = await run_experiment("E4", positions, klines_1d, regime_ema_period=250, shadow_tracking=True)
        year_results["E4"] = e4_result

        # 为每个实验补充 regime day stats
        for exp_name, exp_result in year_results.items():
            if exp_name == "E0":
                # E0 没有 regime gate，不需要 day stats
                exp_result["day_stats"] = {"bull_days": 0, "bear_days": 0, "unknown_days": 0, "total_trading_days": 0}
                continue

            regime_ema = 250 if exp_name in ("E1", "E2", "E4") else 200
            req_slope = exp_name == "E2"
            ema_series = compute_1d_ema_series(klines_1d, regime_ema)
            day_stats = compute_regime_day_stats(klines_1d, ema_series, year, require_slope=req_slope)
            exp_result["day_stats"] = day_stats

        all_results[year] = year_results

        # 打印年度摘要
        print(f"\n  Year {year} Summary:")
        for exp_name in ["E0", "E1", "E2", "E3", "E4"]:
            r = year_results[exp_name]
            m = r["retained"]
            shadow_str = ""
            if "shadow" in r:
                s = r["shadow"]
                shadow_str = f" | Shadow: PnL={s['pnl']}, Trades={s['trades']}, WR={s['win_rate']:.1%}"
            print(f"    {exp_name}: PnL={m['pnl']:+.2f}, Trades={m['trades']}, WR={m['win_rate']:.1%}, Sharpe={m['sharpe']:.2f}{shadow_str}")

    return all_results


# ─── 报告生成 ────────────────────────────────────────────────────────────

def generate_json_report(results: dict) -> dict:
    """生成 JSON 报告结构。"""
    report = {
        "title": "Market Regime E0-E4 Experiment Results",
        "date": "2026-04-28",
        "methodology": "External gating (research-only, no engine modification)",
        "anti_lookahead": "Regime determined by last closed 1d candle before entry timestamp",
        "baseline": {
            "symbol": SYMBOL,
            "timeframe": TIMEFRAME,
            "direction": "LONG-only",
            "ema_period": 50,
            "min_distance_pct": "0.005",
            "tp_ratios": "[0.5, 0.5]",
            "tp_targets": "[1.0, 3.5]",
            "breakeven": False,
            "cost_profile": "BNB9",
        },
        "experiments": {},
    }

    for year, year_results in results.items():
        report["experiments"][str(year)] = {}
        for exp_name, exp_result in year_results.items():
            report["experiments"][str(year)][exp_name] = {
                "retained_metrics": exp_result["retained"],
                "filtered_count": exp_result.get("filtered_count", 0),
                "unknown_count": exp_result.get("unknown_count", 0),
                "regime_day_stats": exp_result.get("day_stats", {}),
            }
            if "shadow" in exp_result:
                report["experiments"][str(year)][exp_name]["shadow_tracking"] = exp_result["shadow"]

    return report


def generate_markdown_report(results: dict) -> str:
    """生成 Markdown 报告。"""
    lines = []
    lines.append("# Market Regime E0-E4 实验结果报告")
    lines.append("")
    lines.append(f"> **日期**: 2026-04-28")
    lines.append(f"> **方法**: 研究层外部 gating（不改引擎、不改 runtime）")
    lines.append(f"> **反前瞻**: regime 由 entry 时间戳之前的最后一根已闭合 1d K 线决定")
    lines.append(f"> **基线**: ETH 1h LONG-only, EMA50, BNB9 成本")
    lines.append("")

    # Section A: 实验概览
    lines.append("## A. 实验概览")
    lines.append("")
    lines.append("| 编号 | 实验名称 | Regime 定义 | Bull 时 | Bear 时 |")
    lines.append("|------|----------|------------|---------|---------|")
    lines.append("| E0 | 基线对照 | 无 regime gate | LONG-only | LONG-only |")
    lines.append("| E1 | daily EMA250 bull-only | 1d close > EMA(250) | 允许 LONG | 不开仓 |")
    lines.append("| E2 | daily EMA250 + slope | 1d close > EMA(250) AND slope > 0 | 允许 LONG | 不开仓 |")
    lines.append("| E3 | daily EMA200 bull-only | 1d close > EMA(200) | 允许 LONG | 不开仓 |")
    lines.append("| E4 | daily EMA250 + shadow | 1d close > EMA(250) | 允许 LONG | 不开仓（记录虚拟 LONG） |")
    lines.append("")

    # Section B: 核心结果对比
    lines.append("## B. 核心结果对比")
    lines.append("")

    for year in YEARS:
        lines.append(f"### {year}")
        lines.append("")
        lines.append("| 实验 | PnL | Trades | Win Rate | Sharpe | MaxDD | Bull% | Bear% |")
        lines.append("|------|-----|--------|----------|--------|-------|-------|-------|")

        year_data = results.get(year, {})
        for exp_name in ["E0", "E1", "E2", "E3", "E4"]:
            exp = year_data.get(exp_name, {})
            m = exp.get("retained", {})
            ds = exp.get("day_stats", {})
            bull_pct = ds.get("bull_pct", "-")
            bear_pct = ds.get("bear_pct", "-")
            lines.append(
                f"| {exp_name} | {m.get('pnl', 0):+.2f} | {m.get('trades', 0)} | "
                f"{m.get('win_rate', 0):.1%} | {m.get('sharpe', 0):.2f} | "
                f"{m.get('max_dd', 0):.2f} | {bull_pct} | {bear_pct} |"
            )
        lines.append("")

    # Section C: E4 Shadow Tracking
    lines.append("## C. E4 Shadow Tracking（Bear Regime 下 LONG 的实际表现）")
    lines.append("")
    lines.append("| 年份 | Shadow PnL | Shadow Trades | Shadow WR | 基线 PnL | 基线 WR |")
    lines.append("|------|-----------|---------------|-----------|---------|---------|")

    for year in YEARS:
        year_data = results.get(year, {})
        e4 = year_data.get("E4", {})
        shadow = e4.get("shadow", {})
        baseline = year_data.get("E0", {}).get("retained", {})
        if shadow:
            lines.append(
                f"| {year} | {shadow.get('pnl', 0):+.2f} | {shadow.get('trades', 0)} | "
                f"{shadow.get('win_rate', 0):.1%} | {baseline.get('pnl', 0):+.2f} | "
                f"{baseline.get('win_rate', 0):.1%} |"
            )
        else:
            lines.append(f"| {year} | N/A | N/A | N/A | {baseline.get('pnl', 0):+.2f} | {baseline.get('win_rate', 0):.1%} |")
    lines.append("")

    # Section D: Regime 日占比
    lines.append("## D. Regime 交易日占比")
    lines.append("")
    lines.append("| 年份 | 实验 | Bull Days | Bear Days | Unknown | Total | Bull% | Bear% |")
    lines.append("|------|------|-----------|-----------|---------|-------|-------|-------|")

    for year in YEARS:
        year_data = results.get(year, {})
        for exp_name in ["E1", "E2", "E3", "E4"]:
            exp = year_data.get(exp_name, {})
            ds = exp.get("day_stats", {})
            if ds.get("total_trading_days", 0) > 0:
                lines.append(
                    f"| {year} | {exp_name} | {ds.get('bull_days', 0)} | {ds.get('bear_days', 0)} | "
                    f"{ds.get('unknown_days', 0)} | {ds.get('total_trading_days', 0)} | "
                    f"{ds.get('bull_pct', 0)}% | {ds.get('bear_pct', 0)}% |"
                )
    lines.append("")

    # Section E: 2023 改善分析
    lines.append("## E. 2023 改善分析")
    lines.append("")
    year_2023 = results.get(2023, {})
    baseline_pnl = year_2023.get("E0", {}).get("retained", {}).get("pnl", 0)
    lines.append(f"基线 2023 PnL: {baseline_pnl:+.2f}")
    lines.append("")
    lines.append("| 实验 | 2023 PnL | 改善幅度 | 改善% | 判定 |")
    lines.append("|------|---------|---------|-------|------|")

    for exp_name in ["E1", "E2", "E3", "E4"]:
        exp = year_2023.get(exp_name, {})
        pnl = exp.get("retained", {}).get("pnl", 0)
        improvement = pnl - baseline_pnl  # baseline is negative, so improvement is positive if less negative
        improvement_pct = (improvement / abs(baseline_pnl) * 100) if baseline_pnl != 0 else 0
        if improvement_pct > 50:
            verdict = "显著"
        elif improvement_pct < 30:
            verdict = "不显著"
        else:
            verdict = "需更多证据"
        lines.append(f"| {exp_name} | {pnl:+.2f} | {improvement:+.2f} | {improvement_pct:.1f}% | {verdict} |")
    lines.append("")

    # Section F: 2024/2025 代价分析
    lines.append("## F. 2024/2025 代价分析")
    lines.append("")
    lines.append("| 实验 | 2024 PnL | 2024 下降% | 2025 PnL | 2025 下降% | 判定 |")
    lines.append("|------|---------|-----------|---------|-----------|------|")

    for year_label, year_num in [("2024", 2024), ("2025", 2025)]:
        year_data = results.get(year_num, {})
        baseline_pnl_y = year_data.get("E0", {}).get("retained", {}).get("pnl", 0)

    # 合并为一行 per experiment
    for exp_name in ["E1", "E2", "E3", "E4"]:
        y2024 = results.get(2024, {}).get(exp_name, {}).get("retained", {}).get("pnl", 0)
        y2025 = results.get(2025, {}).get(exp_name, {}).get("retained", {}).get("pnl", 0)
        b2024 = results.get(2024, {}).get("E0", {}).get("retained", {}).get("pnl", 0)
        b2025 = results.get(2025, {}).get("E0", {}).get("retained", {}).get("pnl", 0)
        drop_2024 = ((b2024 - y2024) / b2024 * 100) if b2024 > 0 else 0
        drop_2025 = ((b2025 - y2025) / b2025 * 100) if b2025 > 0 else 0
        if drop_2024 > 40 or drop_2025 > 40:
            verdict = "代价过大"
        elif drop_2024 < 20 and drop_2025 < 20:
            verdict = "保住"
        else:
            verdict = "可接受"
        lines.append(
            f"| {exp_name} | {y2024:+.2f} | {drop_2024:.1f}% | {y2025:+.2f} | {drop_2025:.1f}% | {verdict} |"
        )
    lines.append("")

    # Section G: 研究分叉判定
    lines.append("## G. 研究分叉判定")
    lines.append("")
    lines.append("基于实验结果的分叉判定：")
    lines.append("")

    # 判定逻辑
    y2023 = results.get(2023, {})
    y2024 = results.get(2024, {})
    y2025 = results.get(2025, {})

    best_improvement = 0
    best_exp = None
    for exp_name in ["E1", "E2", "E3", "E4"]:
        pnl = y2023.get(exp_name, {}).get("retained", {}).get("pnl", 0)
        baseline = y2023.get("E0", {}).get("retained", {}).get("pnl", 0)
        improvement_pct = ((pnl - baseline) / abs(baseline) * 100) if baseline != 0 else 0
        if improvement_pct > best_improvement:
            best_improvement = improvement_pct
            best_exp = exp_name

    # 检查 2024/2025 代价
    b2024 = y2024.get("E0", {}).get("retained", {}).get("pnl", 0)
    b2025 = y2025.get("E0", {}).get("retained", {}).get("pnl", 0)
    best_2024 = y2024.get(best_exp, {}).get("retained", {}).get("pnl", 0) if best_exp else 0
    best_2025 = y2025.get(best_exp, {}).get("retained", {}).get("pnl", 0) if best_exp else 0
    drop_2024 = ((b2024 - best_2024) / b2024 * 100) if b2024 > 0 else 0
    drop_2025 = ((b2025 - best_2025) / b2025 * 100) if b2025 > 0 else 0

    # E4 shadow tracking
    e4_shadow_wr = None
    e4_shadow = y2023.get("E4", {}).get("shadow", {})
    if e4_shadow:
        e4_shadow_wr = e4_shadow.get("win_rate", 0)

    lines.append(f"- **最佳改善实验**: {best_exp} (2023 改善 {best_improvement:.1f}%)")
    lines.append(f"- **2024/2025 代价**: 2024 下降 {drop_2024:.1f}%, 2025 下降 {drop_2025:.1f}%")
    lines.append("")

    if best_improvement > 50 and drop_2024 < 40 and drop_2025 < 40:
        lines.append("**分叉 A：regime gate 有效 → 进入 regime 正式化**")
        lines.append("- 条件满足：2023 显著改善 + 2024/2025 保住")
        lines.append("- 下一步：将 regime gate 正式纳入回测引擎")
    elif best_improvement < 30:
        lines.append("**分叉 B：regime gate 只是少交易 → 继续探索更精细 regime 定义**")
        lines.append("- 条件满足：所有实验只是减少 trades，win rate / Sharpe 无实质改善")
        lines.append("- 下一步：尝试更精细 regime 定义（EMA slope + ADX + volatility contraction）")
    elif e4_shadow_wr is not None and e4_shadow_wr < 0.20:
        lines.append("**分叉 C：regime gate 有效且 bear regime 下 LONG 确实无效 → 开启 SHORT 独立研究线**")
        lines.append(f"- E4 shadow tracking: bear regime 下 LONG win rate = {e4_shadow_wr:.1%} < 20%")
        lines.append("- 下一步：先完成 regime gate 正式化，再开启 SHORT 独立参数研究")
    elif drop_2024 > 40 or drop_2025 > 40:
        lines.append("**分叉 D：regime gate 无效（2024/2025 代价过大）→ 放弃 regime gate**")
        lines.append("- 条件满足：所有实验导致 2024/2025 PnL 下降 > 40%")
        lines.append("- 下一步：不加 regime gate，接受策略有适用边界，转向策略组合研究")
    else:
        lines.append("**混合判定：需要更多证据**")
        lines.append(f"- 2023 改善 {best_improvement:.1f}%（30-50% 区间）")
        lines.append(f"- 2024/2025 代价：{drop_2024:.1f}% / {drop_2025:.1f}%")
        if e4_shadow_wr is not None:
            lines.append(f"- E4 shadow WR: {e4_shadow_wr:.1%}")
        lines.append("- 建议：尝试更精细 regime 定义或更短 EMA 周期")

    lines.append("")

    # MFE/MAE TODO
    lines.append("---")
    lines.append("")
    lines.append("> **注意**: MFE/MAE/+1R/+2R/+3.5R 可达率、first-touch 等指标标记为 TODO。")
    lines.append("> PositionSummary 不含 excursion 数据，需要后续接入 continuation-ability 分析管道。")

    return "\n".join(lines)


# ─── 主入口 ──────────────────────────────────────────────────────────────

async def main():
    print("=" * 60)
    print("  Market Regime E0-E4 Experiment Matrix")
    print("  Research-only, no engine/runtime modification")
    print("=" * 60)

    results = await run_all_experiments()

    # 生成 JSON 报告
    json_report = generate_json_report(results)
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(json_report, f, indent=2, ensure_ascii=False)
    print(f"\nJSON report saved: {JSON_PATH}")

    # 生成 Markdown 报告
    md_report = generate_markdown_report(results)
    with open(MD_PATH, "w", encoding="utf-8") as f:
        f.write(md_report)
    print(f"Markdown report saved: {MD_PATH}")

    # 全期汇总
    print(f"\n{'='*60}")
    print("  Full Period Summary")
    print(f"{'='*60}")
    for exp_name in ["E0", "E1", "E2", "E3", "E4"]:
        total_pnl = 0
        total_trades = 0
        for year in YEARS:
            m = results.get(year, {}).get(exp_name, {}).get("retained", {})
            total_pnl += m.get("pnl", 0)
            total_trades += m.get("trades", 0)
        print(f"  {exp_name}: Total PnL={total_pnl:+.2f}, Total Trades={total_trades}")


if __name__ == "__main__":
    asyncio.run(main())
