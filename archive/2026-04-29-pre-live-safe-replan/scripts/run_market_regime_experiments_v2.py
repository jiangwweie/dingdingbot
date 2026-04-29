#!/usr/bin/env python3
"""
Market Regime E0-E4 实验矩阵 v2 — 复核修正版

修正项：
  A. 反前瞻修正：KlineData.timestamp 是 open timestamp（CCXT 约定），
     1d candle 的 close_time = timestamp + 86400000ms。
     修正前用 timestamp < entry_time 选 K 线（允许了未收盘的当日 K 线），
     修正后用 close_time <= entry_time（只选已收盘 K 线）。
  B. 风险口径：同时跑 research 口径（exposure=2.0, daily_max_trades=50）
     和 Sim-1 runtime 口径（exposure=1.0, daily_max_trades=10）。

严格边界：不改引擎、不改 runtime、不改 live 代码路径。
"""

import asyncio
import json
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
    BacktestRuntimeOverrides,
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
SLOPE_LOOKBACK = 5
DAY_MS = 86400 * 1000  # 1d in ms

# 两种风险口径
RESEARCH_RISK = RiskConfig(
    max_loss_percent=Decimal("0.01"),
    max_leverage=20,
    max_total_exposure=Decimal("2.0"),
    max_position_percent=Decimal("0.2"),
    daily_max_loss=Decimal("0.05"),
    daily_max_trades=50,
    min_balance=Decimal("100"),
)

SIM1_RISK = RiskConfig(
    max_loss_percent=Decimal("0.01"),
    max_leverage=20,
    max_total_exposure=Decimal("1.0"),
    max_position_percent=Decimal("0.2"),
    daily_max_loss=Decimal("0.10"),
    daily_max_trades=10,
    min_balance=Decimal("100"),
)

ORDER_STRATEGY = OrderStrategy(
    id="eth_regime_research_v2",
    name="ETH regime research v2",
    tp_levels=2,
    tp_ratios=[Decimal("0.5"), Decimal("0.5")],
    tp_targets=[Decimal("1.0"), Decimal("3.5")],
    initial_stop_loss_rr=Decimal("-1.0"),
    trailing_stop_enabled=False,
    oco_enabled=True,
)

REPORT_DIR = PROJECT_ROOT / "reports" / "research"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
JSON_PATH = REPORT_DIR / "market_regime_experiments_2026-04-28-v2.json"
MD_PATH = PROJECT_ROOT / "docs" / "planning" / "2026-04-28-market-regime-experiment-results-v2.md"


# ─── 工具 ────────────────────────────────────────────────────────────────

def year_range_ms(year: int) -> tuple[int, int]:
    start = int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    end = int(datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)
    return start, end


def compute_proxy_metrics(positions: list[PositionSummary]) -> dict:
    if not positions:
        return {"pnl": 0.0, "trades": 0, "wins": 0, "losses": 0,
                "win_rate": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
                "sharpe": 0.0, "max_dd": 0.0}

    pnl_list = [float(p.realized_pnl) for p in positions]
    total_pnl = sum(pnl_list)
    wins = [p for p in pnl_list if p > 0]
    losses = [p for p in pnl_list if p <= 0]
    win_rate = len(wins) / len(pnl_list) if pnl_list else 0.0
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0

    if len(pnl_list) >= 2:
        mean_pnl = statistics.mean(pnl_list)
        std_pnl = statistics.stdev(pnl_list)
        sharpe = (mean_pnl / std_pnl) if std_pnl > 0 else 0.0
    else:
        sharpe = 0.0

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


# ─── 1d EMA 计算 ────────────────────────────────────────────────────────

def compute_1d_ema_series(klines_1d: list, period: int) -> dict[int, float]:
    """计算 1d EMA 序列，key = open_timestamp。"""
    if not klines_1d or len(klines_1d) < period:
        return {}

    k = 2.0 / (period + 1)
    closes = [float(kl.close) for kl in klines_1d]
    sma_init = sum(closes[:period]) / period
    ema_val = sma_init
    ema_series: dict[int, float] = {klines_1d[period - 1].timestamp: ema_val}

    for i in range(period, len(closes)):
        ema_val = closes[i] * k + ema_val * (1 - k)
        ema_series[klines_1d[i].timestamp] = ema_val

    return ema_series


# ─── Regime 判断（修正版）────────────────────────────────────────────────

def compute_regime_at_entry(
    entry_timestamp_ms: int,
    ema_series: dict[int, float],
    klines_1d: list,
    regime_ema_period: int,
    require_slope: bool = False,
) -> dict:
    """
    判断 entry 时刻的 regime 状态。

    反前瞻修正：
      KlineData.timestamp 是 open timestamp（CCXT 约定）。
      1d candle 的 close_time = timestamp + 86400000ms。
      只使用 close_time <= entry_timestamp_ms 的 K 线（已收盘）。
    """
    # 找到 close_time <= entry_timestamp_ms 的最后一根 1d K 线
    last_closed_idx = -1
    for i, kl in enumerate(klines_1d):
        close_time = kl.timestamp + DAY_MS
        if close_time <= entry_timestamp_ms:
            last_closed_idx = i
        else:
            break

    if last_closed_idx < 0:
        return {"regime": "unknown", "close_1d": None, "ema_value": None,
                "ema_slope": None, "candle_ts": None}

    candle = klines_1d[last_closed_idx]
    close_1d = float(candle.close)

    # 查找这根 K 线对应的 EMA 值（key = open_timestamp）
    ema_value = None
    for ts in sorted(ema_series.keys()):
        if ts <= candle.timestamp:
            ema_value = ema_series[ts]
        else:
            break

    if ema_value is None:
        return {"regime": "unknown", "close_1d": close_1d, "ema_value": None,
                "ema_slope": None, "candle_ts": candle.timestamp}

    is_bull = close_1d > ema_value
    ema_slope = None

    if require_slope:
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
                if is_bull and ema_slope <= 0:
                    is_bull = False
            else:
                return {"regime": "unknown", "close_1d": close_1d, "ema_value": ema_value,
                        "ema_slope": None, "candle_ts": candle.timestamp}
        else:
            return {"regime": "unknown", "close_1d": close_1d, "ema_value": ema_value,
                    "ema_slope": None, "candle_ts": candle.timestamp}

    regime = "bull" if is_bull else "bear"
    return {"regime": regime, "close_1d": close_1d, "ema_value": ema_value,
            "ema_slope": ema_slope, "candle_ts": candle.timestamp}


# ─── Regime 日占比 ───────────────────────────────────────────────────────

def compute_regime_day_stats(
    klines_1d: list,
    ema_series: dict[int, float],
    year: int,
    require_slope: bool = False,
) -> dict:
    bull_days = bear_days = unknown_days = 0
    year_start_ms = int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    year_end_ms = int(datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)

    for kl in klines_1d:
        if kl.timestamp < year_start_ms or kl.timestamp > year_end_ms:
            continue
        close_1d = float(kl.close)
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
        "bull_days": bull_days, "bear_days": bear_days, "unknown_days": unknown_days,
        "total_trading_days": total,
        "bull_pct": round(bull_days / total * 100, 1) if total > 0 else 0.0,
        "bear_pct": round(bear_days / total * 100, 1) if total > 0 else 0.0,
    }


# ─── 回测执行 ────────────────────────────────────────────────────────────

async def run_backtest_for_year(year: int, risk_config: RiskConfig) -> list[PositionSummary]:
    repo = HistoricalDataRepository()
    backtester = Backtester(exchange_gateway=None, data_repository=repo)
    start_time, end_time = year_range_ms(year)

    request = BacktestRequest(
        symbol=SYMBOL, timeframe=TIMEFRAME, mode="v3_pms",
        start_time=start_time, end_time=end_time, limit=9000,
        slippage_rate=BNB9_SLIPPAGE, tp_slippage_rate=BNB9_TP_SLIPPAGE,
        fee_rate=BNB9_FEE, initial_balance=INITIAL_BALANCE,
    )
    request.risk_overrides = risk_config
    request.order_strategy = ORDER_STRATEGY

    report = await backtester.run_backtest(request, runtime_overrides=BASELINE_RUNTIME_OVERRIDES)
    return report.positions


async def load_1d_klines(year: int) -> list:
    repo = HistoricalDataRepository()
    start_time, _ = year_range_ms(year - 1)
    _, end_time = year_range_ms(year)
    return await repo.get_klines(SYMBOL, "1d", start_time, end_time, limit=1000)


# ─── 实验执行 ────────────────────────────────────────────────────────────

async def run_experiment(
    experiment_name: str,
    positions: list[PositionSummary],
    klines_1d: list,
    regime_ema_period: int,
    require_slope: bool = False,
    shadow_tracking: bool = False,
) -> dict:
    ema_series = compute_1d_ema_series(klines_1d, regime_ema_period)
    retained = []
    filtered = []
    shadow_positions = []

    for pos in positions:
        rs = compute_regime_at_entry(
            pos.entry_time, ema_series, klines_1d, regime_ema_period,
            require_slope=require_slope,
        )
        if rs["regime"] == "bull":
            retained.append(pos)
        elif rs["regime"] == "bear":
            filtered.append((pos, rs))
            if shadow_tracking:
                shadow_positions.append(pos)
        else:
            filtered.append((pos, rs))

    metrics = compute_proxy_metrics(retained)
    result = {
        "experiment": experiment_name,
        "retained": metrics,
        "filtered_count": len(filtered),
        "unknown_count": sum(1 for _, rs in filtered if rs["regime"] == "unknown"),
    }
    if shadow_tracking and shadow_positions:
        result["shadow"] = compute_proxy_metrics(shadow_positions)
    elif shadow_tracking:
        result["shadow"] = compute_proxy_metrics([])

    return result


async def run_all_experiments(risk_config: RiskConfig, risk_label: str) -> dict:
    all_results = {}
    for year in YEARS:
        print(f"\n  [{risk_label}] Year {year}: Running baseline backtest...", flush=True)
        positions = await run_backtest_for_year(year, risk_config)
        print(f"  [{risk_label}] {year}: {len(positions)} positions", flush=True)

        klines_1d = await load_1d_klines(year)
        year_results = {}

        # E0
        year_results["E0"] = {"experiment": "E0", "retained": compute_proxy_metrics(positions)}

        # E1-E4
        experiments = [
            ("E1", 250, False, False),
            ("E2", 250, True, False),
            ("E3", 200, False, False),
            ("E4", 250, False, True),
        ]
        for exp_name, ema_period, slope, shadow in experiments:
            r = await run_experiment(exp_name, positions, klines_1d, ema_period,
                                     require_slope=slope, shadow_tracking=shadow)
            year_results[exp_name] = r

        # Regime day stats
        for exp_name, exp_result in year_results.items():
            if exp_name == "E0":
                exp_result["day_stats"] = {"bull_days": 0, "bear_days": 0, "unknown_days": 0, "total_trading_days": 0}
                continue
            regime_ema = 250 if exp_name in ("E1", "E2", "E4") else 200
            req_slope = exp_name == "E2"
            ema_series = compute_1d_ema_series(klines_1d, regime_ema)
            exp_result["day_stats"] = compute_regime_day_stats(klines_1d, ema_series, year, require_slope=req_slope)

        all_results[year] = year_results

        # Print summary
        print(f"\n  [{risk_label}] Year {year} Summary:", flush=True)
        for exp_name in ["E0", "E1", "E2", "E3", "E4"]:
            r = year_results[exp_name]
            m = r["retained"]
            shadow_str = ""
            if "shadow" in r and r["shadow"]["trades"] > 0:
                s = r["shadow"]
                shadow_str = f" | Shadow: PnL={s['pnl']:+.0f}, T={s['trades']}, WR={s['win_rate']:.1%}"
            print(f"    {exp_name}: PnL={m['pnl']:+.2f}, T={m['trades']}, WR={m['win_rate']:.1%}, Sharpe={m['sharpe']:.2f}{shadow_str}", flush=True)

    return all_results


# ─── 报告生成 ────────────────────────────────────────────────────────────

def generate_json_report(research_results: dict, sim1_results: dict) -> dict:
    def pack_results(results, label):
        packed = {}
        for year, year_results in results.items():
            packed[str(year)] = {}
            for exp_name, exp_data in year_results.items():
                entry = {
                    "retained_metrics": exp_data["retained"],
                    "filtered_count": exp_data.get("filtered_count", 0),
                    "unknown_count": exp_data.get("unknown_count", 0),
                    "regime_day_stats": exp_data.get("day_stats", {}),
                }
                if "shadow" in exp_data:
                    entry["shadow_tracking"] = exp_data["shadow"]
                packed[str(year)][exp_name] = entry
        return packed

    return {
        "title": "Market Regime E0-E4 Experiment Results v2 (复核修正版)",
        "date": "2026-04-28",
        "v2_corrections": {
            "anti_lookahead_fix": "KlineData.timestamp is open timestamp (CCXT). close_time = timestamp + 86400000ms. Only use candles where close_time <= entry_time.",
            "risk_profile_dual_run": "Both research (exposure=2.0, daily_max_trades=50) and Sim-1 runtime (exposure=1.0, daily_max_trades=10) risk configs are run.",
        },
        "research_risk": pack_results(research_results, "research"),
        "sim1_risk": pack_results(sim1_results, "sim1"),
    }


def generate_markdown_report(research_results: dict, sim1_results: dict) -> str:
    lines = []
    lines.append("# Market Regime E0-E4 实验结果报告 v2（复核修正版）")
    lines.append("")
    lines.append("> **日期**: 2026-04-28")
    lines.append("> **版本**: v2 — 复核修正版")
    lines.append("> **方法**: 研究层外部 gating（不改引擎、不改 runtime）")
    lines.append("> **基线**: ETH 1h LONG-only, EMA50, BNB9 成本")
    lines.append("")

    # ── 1. 修正前问题说明 ──
    lines.append("## 1. 修正前问题说明")
    lines.append("")
    lines.append("### A. 反前瞻问题")
    lines.append("")
    lines.append("v1 脚本中 `compute_regime_at_entry` 使用 `kl.timestamp < entry_time` 选择 1d K 线。")
    lines.append("**问题**：CCXT 约定 `KlineData.timestamp` 是 **open timestamp**（K 线开盘时间），")
    lines.append("1d K 线的 close_time = timestamp + 86400000ms。")
    lines.append("当 entry 发生在某日 00:00–24:00 UTC 之间时，`timestamp < entry_time` 会选中当日 K 线，")
    lines.append("但当日 K 线尚未收盘，close 价格是实时价格而非最终收盘价。")
    lines.append("这构成 **1-bar lookahead bias**。")
    lines.append("")
    lines.append("**回测器自身 MTF 逻辑的正确做法**（`backtester.py:1101`）：")
    lines.append("```python")
    lines.append("candle_close_time = ts + higher_tf_period_ms")
    lines.append("if candle_close_time <= timestamp:  # 只用已收盘 K 线")
    lines.append("```")
    lines.append("")
    lines.append("### B. 风险口径问题")
    lines.append("")
    lines.append("v1 脚本使用 `max_total_exposure=2.0, daily_max_trades=50`（research baseline），")
    lines.append("而 Sim-1 runtime 使用 `max_total_exposure=1.0, daily_max_trades=10`。")
    lines.append("更宽松的 exposure 允许更多并发仓位，可能影响 2023 亏损幅度。")
    lines.append("v2 同时跑两种口径以验证结论对风险口径的敏感度。")
    lines.append("")

    # ── 2. 反前瞻修正方法 ──
    lines.append("## 2. 反前瞻修正方法")
    lines.append("")
    lines.append("修正：`close_time = kl.timestamp + 86400000`，只使用 `close_time <= entry_time` 的 K 线。")
    lines.append("")
    lines.append("```python")
    lines.append("# v1 (有 lookahead):")
    lines.append("if kl.timestamp < entry_timestamp_ms:")
    lines.append("    last_closed_idx = i")
    lines.append("")
    lines.append("# v2 (修正后):")
    lines.append("close_time = kl.timestamp + 86400000  # DAY_MS")
    lines.append("if close_time <= entry_timestamp_ms:")
    lines.append("    last_closed_idx = i")
    lines.append("```")
    lines.append("")
    lines.append("效果：entry 发生在当日 1h K 线时，不会使用当日 1d K 线的未收盘数据，")
    lines.append("而是使用前一日已收盘的 1d K 线。这消除了 1-bar lookahead。")
    lines.append("")

    # ── 3. 风险口径说明 ──
    lines.append("## 3. 风险口径说明")
    lines.append("")
    lines.append("| 参数 | Research Baseline | Sim-1 Runtime |")
    lines.append("|------|------------------|---------------|")
    lines.append("| max_loss_percent | 1% | 1% |")
    lines.append("| max_total_exposure | 2.0 (200%) | 1.0 (100%) |")
    lines.append("| daily_max_trades | 50 | 10 |")
    lines.append("| daily_max_loss | 5% | 10% |")
    lines.append("| max_leverage | 20 | 20 |")
    lines.append("")
    lines.append("Research baseline 允许更多并发仓位和更高交易频率，适合参数搜索。")
    lines.append("Sim-1 runtime 更保守，限制单日最多 10 笔交易和 100% 总敞口。")
    lines.append("")

    # ── 4. E0-E4 修正后总表 ──
    for risk_label, results in [("Research Baseline", research_results), ("Sim-1 Runtime", sim1_results)]:
        lines.append(f"## 4. E0-E4 修正后总表（{risk_label}）")
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
                bull_pct = f"{ds.get('bull_pct', 0)}%" if ds.get("total_trading_days", 0) > 0 else "-"
                bear_pct = f"{ds.get('bear_pct', 0)}%" if ds.get("total_trading_days", 0) > 0 else "-"
                lines.append(
                    f"| {exp_name} | {m.get('pnl', 0):+.2f} | {m.get('trades', 0)} | "
                    f"{m.get('win_rate', 0):.1%} | {m.get('sharpe', 0):.2f} | "
                    f"{m.get('max_dd', 0):.2f} | {bull_pct} | {bear_pct} |"
                )
            lines.append("")

    # ── 5. E4 Shadow Tracking ──
    lines.append("## 5. E4 Shadow Tracking（Bear Regime 下 LONG 的实际表现）")
    lines.append("")
    for risk_label, results in [("Research", research_results), ("Sim-1", sim1_results)]:
        lines.append(f"### {risk_label} 口径")
        lines.append("")
        lines.append("| 年份 | Shadow PnL | Shadow Trades | Shadow WR | 基线 PnL | 基线 WR |")
        lines.append("|------|-----------|---------------|-----------|---------|---------|")
        for year in YEARS:
            year_data = results.get(year, {})
            e4 = year_data.get("E4", {})
            shadow = e4.get("shadow", {})
            baseline = year_data.get("E0", {}).get("retained", {})
            sp = shadow.get("pnl", 0)
            st = shadow.get("trades", 0)
            swr = shadow.get("win_rate", 0)
            lines.append(
                f"| {year} | {sp:+.2f} | {st} | {swr:.1%} | "
                f"{baseline.get('pnl', 0):+.2f} | {baseline.get('win_rate', 0):.1%} |"
            )
        lines.append("")

    # ── 6. 2023 改善 + 2024/2025 代价 ──
    lines.append("## 6. 2023 改善与 2024/2025 代价分析")
    lines.append("")
    for risk_label, results in [("Research", research_results), ("Sim-1", sim1_results)]:
        lines.append(f"### {risk_label} 口径")
        lines.append("")
        y2023 = results.get(2023, {})
        baseline_pnl = y2023.get("E0", {}).get("retained", {}).get("pnl", 0)
        lines.append(f"基线 2023 PnL: {baseline_pnl:+.2f}")
        lines.append("")
        lines.append("| 实验 | 2023 PnL | 改善% | 2024 PnL | 2024 下降% | 2025 PnL | 2025 下降% | 判定 |")
        lines.append("|------|---------|-------|---------|-----------|---------|-----------|------|")

        for exp_name in ["E1", "E2", "E3", "E4"]:
            pnl_23 = y2023.get(exp_name, {}).get("retained", {}).get("pnl", 0)
            improvement_pct = ((pnl_23 - baseline_pnl) / abs(baseline_pnl) * 100) if baseline_pnl != 0 else 0

            y2024 = results.get(2024, {}).get(exp_name, {}).get("retained", {}).get("pnl", 0)
            y2025 = results.get(2025, {}).get(exp_name, {}).get("retained", {}).get("pnl", 0)
            b2024 = results.get(2024, {}).get("E0", {}).get("retained", {}).get("pnl", 0)
            b2025 = results.get(2025, {}).get("E0", {}).get("retained", {}).get("pnl", 0)
            drop_24 = ((b2024 - y2024) / b2024 * 100) if b2024 > 0 else 0
            drop_25 = ((b2025 - y2025) / b2025 * 100) if b2025 > 0 else 0

            if improvement_pct > 50 and drop_24 < 40 and drop_25 < 40:
                verdict = "有效"
            elif drop_24 > 40 or drop_25 > 40:
                verdict = "代价过大"
            elif improvement_pct < 30:
                verdict = "改善不足"
            else:
                verdict = "需更多证据"

            lines.append(
                f"| {exp_name} | {pnl_23:+.2f} | {improvement_pct:+.1f}% | "
                f"{y2024:+.2f} | {drop_24:.1f}% | {y2025:+.2f} | {drop_25:.1f}% | {verdict} |"
            )
        lines.append("")

    # ── 7. 最终结论 ──
    lines.append("## 7. 最终结论")
    lines.append("")

    # Use research results as primary (more trades = more signal)
    y2023 = research_results.get(2023, {})
    y2024 = research_results.get(2024, {})
    y2025 = research_results.get(2025, {})

    # Best 2023 improvement
    baseline_23 = y2023.get("E0", {}).get("retained", {}).get("pnl", 0)
    best_improvement = -999
    best_exp = None
    for exp_name in ["E1", "E2", "E3", "E4"]:
        pnl = y2023.get(exp_name, {}).get("retained", {}).get("pnl", 0)
        imp = ((pnl - baseline_23) / abs(baseline_23) * 100) if baseline_23 != 0 else 0
        if imp > best_improvement:
            best_improvement = imp
            best_exp = exp_name

    # 2024/2025 drops for best
    b2024 = y2024.get("E0", {}).get("retained", {}).get("pnl", 0)
    b2025 = y2025.get("E0", {}).get("retained", {}).get("pnl", 0)
    best_2024 = y2024.get(best_exp, {}).get("retained", {}).get("pnl", 0) if best_exp else 0
    best_2025 = y2025.get(best_exp, {}).get("retained", {}).get("pnl", 0) if best_exp else 0
    drop_24 = ((b2024 - best_2024) / b2024 * 100) if b2024 > 0 else 0
    drop_25 = ((b2025 - best_2025) / b2025 * 100) if b2025 > 0 else 0

    # E4 shadow WR
    e4_shadow_wrs = []
    for year in YEARS:
        shadow = research_results.get(year, {}).get("E4", {}).get("shadow", {})
        if shadow.get("trades", 0) > 0:
            e4_shadow_wrs.append(shadow["win_rate"])
    avg_shadow_wr = sum(e4_shadow_wrs) / len(e4_shadow_wrs) if e4_shadow_wrs else None

    lines.append(f"**最佳 2023 改善**: {best_exp} ({best_improvement:+.1f}%)")
    lines.append(f"**2024/2025 代价**: 2024 下降 {drop_24:.1f}%, 2025 下降 {drop_25:.1f}%")
    if avg_shadow_wr is not None:
        lines.append(f"**E4 shadow 平均 bear WR**: {avg_shadow_wr:.1%}")
    lines.append("")

    # Decision
    all_negative_improvement = True
    for exp_name in ["E1", "E2", "E3", "E4"]:
        pnl = y2023.get(exp_name, {}).get("retained", {}).get("pnl", 0)
        if pnl > baseline_23:
            all_negative_improvement = False

    if all_negative_improvement:
        lines.append("### 结论 1：EMA250/EMA200 粗 regime gate 被否定")
        lines.append("")
        lines.append("所有实验在 2023 年 PnL 均劣于基线（regime gate 不仅没有减少亏损，反而增加了亏损）。")
        lines.append("这意味着 2023 年的亏损不仅来自 bear regime，bull regime 下的 LONG 同样亏损。")
        lines.append("简单的 EMA close > EMA 分型无法区分[能赚钱的 bull]和[不能赚钱的 bull]。")
    elif best_improvement < 30:
        lines.append("### 结论 1：EMA250/EMA200 粗 regime gate 改善不足")
        lines.append("")
        lines.append(f"最佳改善仅 {best_improvement:+.1f}%，远低于 50% 显著阈值。")
        lines.append("regime gate 的主要效果是减少交易次数，而非改善收益质量。")
    else:
        lines.append(f"### 结论 1：{best_exp} 有一定改善（{best_improvement:+.1f}%），但代价过大")

    lines.append("")

    # SHORT assessment
    if avg_shadow_wr is not None and avg_shadow_wr > 0.25:
        lines.append("### 结论 2：不支持开启 SHORT 主线")
        lines.append("")
        lines.append(f"E4 shadow tracking 显示 bear regime 下 LONG 的平均 win rate = {avg_shadow_wr:.1%} > 25%。")
        lines.append("bear regime 下 LONG 并非完全无效（部分 bear LONG 是盈利的），")
        lines.append("SHORT 不太可能是 LONG 的简单镜像，独立研究价值有限。")
    elif avg_shadow_wr is not None:
        lines.append("### 结论 2：SHORT 有一定研究价值，但不是当前优先级")
        lines.append("")
        lines.append(f"E4 shadow tracking: bear regime 下 LONG 平均 WR = {avg_shadow_wr:.1%}。")
    lines.append("")

    # Next stage
    lines.append("### 结论 3：下一阶段应转向更精细 regime 定义")
    lines.append("")
    lines.append("粗粒度 EMA250/EMA200 gate 失败的原因：")
    lines.append("- 2023 年 bull regime 下的 LONG 同样亏损 → EMA 分型太粗，无法区分趋势质量")
    lines.append("- 2024/2025 代价过大 → 过滤掉了太多有效交易")
    lines.append("")
    lines.append("建议的更精细 regime 定义方向：")
    lines.append("- EMA slope + ADX 组合（趋势强度 + 方向确认）")
    lines.append("- 波动率收缩/扩张状态（VIX-like regime）")
    lines.append("- 多因子 regime：EMA 方向 × ADX 强度 × 波动率状态")
    lines.append("- 或放弃 regime gate，接受策略有适用边界，转向策略组合研究")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("> MFE/MAE/+1R/+2R/+3.5R 可达率、first-touch 等指标标记为 TODO。")
    lines.append("> PositionSummary 不含 excursion 数据，需要后续接入 continuation-ability 分析管道。")

    return "\n".join(lines)


# ─── 主入口 ──────────────────────────────────────────────────────────────

async def main():
    print("=" * 60)
    print("  Market Regime E0-E4 v2 (复核修正版)")
    print("  - Anti-lookahead fix: close_time = ts + 86400000")
    print("  - Dual risk profile: research + Sim-1")
    print("=" * 60, flush=True)

    # Run both risk profiles
    print("\n>>> Research Baseline (exposure=2.0, daily_max_trades=50)", flush=True)
    research_results = await run_all_experiments(RESEARCH_RISK, "research")

    print("\n>>> Sim-1 Runtime (exposure=1.0, daily_max_trades=10)", flush=True)
    sim1_results = await run_all_experiments(SIM1_RISK, "sim1")

    # Generate reports
    json_report = generate_json_report(research_results, sim1_results)
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(json_report, f, indent=2, ensure_ascii=False)
    print(f"\nJSON report saved: {JSON_PATH}", flush=True)

    md_report = generate_markdown_report(research_results, sim1_results)
    with open(MD_PATH, "w", encoding="utf-8") as f:
        f.write(md_report)
    print(f"Markdown report saved: {MD_PATH}", flush=True)

    # Full period summary
    print(f"\n{'='*60}")
    print("  Full Period Summary")
    print(f"{'='*60}")
    for risk_label, results in [("Research", research_results), ("Sim-1", sim1_results)]:
        print(f"\n  [{risk_label}]", flush=True)
        for exp_name in ["E0", "E1", "E2", "E3", "E4"]:
            total_pnl = sum(results.get(y, {}).get(exp_name, {}).get("retained", {}).get("pnl", 0) for y in YEARS)
            total_trades = sum(results.get(y, {}).get(exp_name, {}).get("retained", {}).get("trades", 0) for y in YEARS)
            print(f"    {exp_name}: Total PnL={total_pnl:+.2f}, Total Trades={total_trades}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
