#!/usr/bin/env python3
"""
H5: ETH 1h LONG-only 基线结构能否迁移到其他品种，形成低相关、不同步失效的候选子策略？

目标：
  1. 用 ETH 固定基线参数跑 BTC/SOL/BNB 回测
  2. 与 ETH 基线对比年度收益相关性
  3. 检验是否存在"ETH 失效时该品种不失效"的候选
  4. 判断是否只是 crypto beta 共振

严格边界：不改引擎、不改 runtime、不改 ETH 基线参数。
"""

import asyncio
import json
import statistics
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.application.backtester import Backtester
from src.application.research_control_plane import BASELINE_RUNTIME_OVERRIDES
from src.domain.models import (
    BacktestRequest,
    OrderStrategy,
    PMSBacktestReport,
    PositionCloseEvent,
    PositionSummary,
    RiskConfig,
)
from src.infrastructure.historical_data_repository import HistoricalDataRepository

# ─── 常量 ───────────────────────────────────────────────────────────────

TIMEFRAME = "1h"
SYMBOLS = ["ETH/USDT:USDT", "BTC/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT"]
BNB9_SLIPPAGE = Decimal("0.0001")
BNB9_TP_SLIPPAGE = Decimal("0")
BNB9_FEE = Decimal("0.000405")
INITIAL_BALANCE = Decimal("10000")

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
    id="h5_multi_symbol",
    name="H5 multi-symbol transfer",
    tp_levels=2,
    tp_ratios=[Decimal("0.5"), Decimal("0.5")],
    tp_targets=[Decimal("1.0"), Decimal("3.5")],
    initial_stop_loss_rr=Decimal("-1.0"),
    trailing_stop_enabled=False,
    oco_enabled=True,
)

REPORT_DIR = PROJECT_ROOT / "reports" / "research"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
JSON_PATH = REPORT_DIR / "multi_symbol_baseline_transfer_2026-04-28.json"
MD_PATH = PROJECT_ROOT / "docs" / "planning" / "2026-04-28-multi-symbol-baseline-transfer.md"

YEARS = [2022, 2023, 2024, 2025]
# 2026 Q1 用 quarter_range_ms
ETH_BASELINE_PNL = {
    2022: 69.30,
    2023: -3924.06,
    2024: 8500.69,
    2025: 4490.24,
}


# ─── 工具 ────────────────────────────────────────────────────────────────

def year_range_ms(year: int) -> tuple[int, int]:
    start = int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    end = int(datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)
    return start, end


def quarter_range_ms(year: int, q: int) -> tuple[int, int]:
    start_month = (q - 1) * 3 + 1
    end_month = q * 3
    start = int(datetime(year, start_month, 1, tzinfo=timezone.utc).timestamp() * 1000)
    if end_month == 12:
        end = int(datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)
    else:
        end = int(datetime(year, end_month + 1, 1, tzinfo=timezone.utc).timestamp() * 1000) - 1
    return start, end


def compute_metrics(positions: list[PositionSummary], close_events: list[PositionCloseEvent]) -> dict:
    if not positions:
        return {
            "pnl": 0.0, "trades": 0, "wins": 0, "losses": 0,
            "win_rate": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
            "sharpe": 0.0, "max_dd": 0.0, "max_dd_pct": 0.0,
            "tp1_count": 0, "tp2_count": 0, "sl_count": 0,
            "tp1_pct": 0.0, "tp2_pct": 0.0, "sl_pct": 0.0,
            "avg_holding_hours": 0.0,
        }

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

    max_dd_pct = max_dd / 10000.0 if 10000.0 > 0 else 0.0

    tp1_count = tp2_count = sl_count = other_count = 0
    for ev in close_events:
        et = ev.event_type.upper()
        if et == "TP1":
            tp1_count += 1
        elif et == "TP2":
            tp2_count += 1
        elif et == "SL":
            sl_count += 1
        else:
            other_count += 1

    total_exits = tp1_count + tp2_count + sl_count + other_count

    holding_hours_list = []
    for p in positions:
        if p.entry_time and p.exit_time:
            holding_ms = p.exit_time - p.entry_time
            holding_hours_list.append(holding_ms / (1000 * 3600))
    avg_holding_hours = sum(holding_hours_list) / len(holding_hours_list) if holding_hours_list else 0.0

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
        "max_dd_pct": round(max_dd_pct, 4),
        "tp1_count": tp1_count,
        "tp2_count": tp2_count,
        "sl_count": sl_count,
        "other_count": other_count,
        "tp1_pct": round(tp1_count / total_exits * 100, 1) if total_exits > 0 else 0.0,
        "tp2_pct": round(tp2_count / total_exits * 100, 1) if total_exits > 0 else 0.0,
        "sl_pct": round(sl_count / total_exits * 100, 1) if total_exits > 0 else 0.0,
        "avg_holding_hours": round(avg_holding_hours, 1),
    }


def classify_year(metrics: dict) -> str:
    """Classify a year as 'adapted', 'boundary', or 'failed'"""
    pnl = metrics["pnl"]
    wr = metrics["win_rate"]
    sharpe = metrics["sharpe"]

    if pnl > 0 and wr > 0.25 and sharpe > 0:
        return "adapted"
    if pnl < -2000 and (wr < 0.20 or sharpe < -1.0):
        return "failed"
    return "boundary"


# ─── 数据可用性检查 ──────────────────────────────────────────────────────

def check_data_availability(symbol: str, start_time: int, end_time: int) -> int:
    """检查 DB 中是否有足够的 1h kline 数据。返回 kline 数量，0 表示数据不足。"""
    import sqlite3
    db_path = PROJECT_ROOT / "data" / "v3_dev.db"
    if not db_path.exists():
        return 0
    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT COUNT(*) FROM klines WHERE symbol=? AND timeframe=? AND timestamp>=? AND timestamp<=?",
        (symbol, TIMEFRAME, start_time, end_time),
    ).fetchone()
    conn.close()
    return row[0] if row else 0


MIN_BARS_PER_YEAR = 100  # 低于此数量视为数据不足，跳过回测


# ─── 回测执行 ────────────────────────────────────────────────────────────

async def run_backtest(
    symbol: str,
    start_time: int,
    end_time: int,
    risk_config: RiskConfig,
) -> tuple[list[PositionSummary], list[PositionCloseEvent]]:
    repo = HistoricalDataRepository()
    backtester = Backtester(exchange_gateway=None, data_repository=repo)

    request = BacktestRequest(
        symbol=symbol, timeframe=TIMEFRAME, mode="v3_pms",
        start_time=start_time, end_time=end_time, limit=9000,
        slippage_rate=BNB9_SLIPPAGE, tp_slippage_rate=BNB9_TP_SLIPPAGE,
        fee_rate=BNB9_FEE, initial_balance=INITIAL_BALANCE,
    )
    request.risk_overrides = risk_config
    request.order_strategy = ORDER_STRATEGY

    overrides = BASELINE_RUNTIME_OVERRIDES.model_copy(deep=True)
    overrides.allowed_directions = ["LONG"]

    report = await backtester.run_backtest(request, runtime_overrides=overrides)
    if isinstance(report, PMSBacktestReport):
        return report.positions, report.close_events
    return [], []


# ─── 相关性分析 ──────────────────────────────────────────────────────────

def compute_correlation(eth_pnl: list[float], other_pnl: list[float]) -> float:
    """计算两个品种年度 PnL 的相关系数"""
    if len(eth_pnl) < 2 or len(other_pnl) < 2:
        return 0.0

    n = min(len(eth_pnl), len(other_pnl))
    eth = eth_pnl[:n]
    other = other_pnl[:n]

    mean_eth = statistics.mean(eth)
    mean_other = statistics.mean(other)

    cov = sum((e - mean_eth) * (o - mean_other) for e, o in zip(eth, other)) / n
    std_eth = statistics.stdev(eth) if len(eth) > 1 else 0.001
    std_other = statistics.stdev(other) if len(other) > 1 else 0.001

    return cov / (std_eth * std_other)


def analyze_diversification(all_results: dict) -> dict:
    """分析多品种分散化效果"""
    symbols = list(all_results.keys())
    years = [2022, 2023, 2024, 2025]

    # 提取年度 PnL（按年份对齐）
    pnl_by_symbol = {}
    for sym in symbols:
        pnl_by_symbol[sym] = {str(y): all_results[sym][str(y)]["pnl"] for y in years if str(y) in all_results[sym]}

    # 计算与 ETH 的相关性（仅用两者都有数据的年份）
    correlations = {}
    eth_data = pnl_by_symbol.get("ETH", {})
    for sym in symbols:
        if sym == "ETH":
            continue
        other_data = pnl_by_symbol.get(sym, {})
        common_years = sorted(set(eth_data.keys()) & set(other_data.keys()))
        if len(common_years) >= 2:
            eth_vals = [eth_data[y] for y in common_years]
            other_vals = [other_data[y] for y in common_years]
            corr = compute_correlation(eth_vals, other_vals)
            correlations[sym] = round(corr, 3)
        else:
            correlations[sym] = None  # insufficient overlapping data

    # 检查失效同步性
    # ETH 2023 是失效年，检查其他品种 2023 的表现
    sync_analysis = {}
    for sym in symbols:
        if sym == "ETH":
            continue
        if "2023" in all_results[sym]:
            m = all_results[sym]["2023"]
            eth_2023_pnl = ETH_BASELINE_PNL.get(2023, 0)
            # 如果其他品种 2023 也亏损，则为同步失效
            if m["pnl"] < 0 and eth_2023_pnl < 0:
                sync_analysis[sym] = {
                    "sync_failed": True,
                    "symbol_2023_pnl": m["pnl"],
                    "eth_2023_pnl": eth_2023_pnl,
                    "reason": f"Both ETH and {sym.split('/')[0]} lost money in 2023 — synchronized failure"
                }
            else:
                sync_analysis[sym] = {
                    "sync_failed": False,
                    "symbol_2023_pnl": m["pnl"],
                    "eth_2023_pnl": eth_2023_pnl,
                    "reason": f"{sym.split('/')[0]} did not fail in 2023 (PnL={m['pnl']:+.2f}) — potential diversification benefit"
                }
        else:
            sync_analysis[sym] = {
                "sync_failed": None,
                "symbol_2023_pnl": None,
                "eth_2023_pnl": ETH_BASELINE_PNL.get(2023, 0),
                "reason": f"{sym.split('/')[0]}: 2023 data missing — cannot assess failure synchronization"
            }

    # 判断是否只是 beta 共振
    valid_corrs = [v for v in correlations.values() if v is not None]
    avg_corr = statistics.mean(valid_corrs) if valid_corrs else 0.0
    beta共振 = avg_corr > 0.7

    return {
        "correlations": correlations,
        "sync_analysis": sync_analysis,
        "avg_correlation": round(avg_corr, 3),
        "beta_resonance": beta共振,
        "interpretation": "crypto beta共振" if beta共振 else "存在分散化收益"
    }


# ─── 主实验 ──────────────────────────────────────────────────────────────

async def run_all() -> dict:
    results = {}
    missing_data = {}  # {symbol: [years_missing]}

    for symbol in SYMBOLS:
        sym_short = symbol.split("/")[0]
        results[sym_short] = {}
        missing_data[sym_short] = []

        for year in YEARS:
            start, end = year_range_ms(year)
            bar_count = check_data_availability(symbol, start, end)
            if bar_count < MIN_BARS_PER_YEAR:
                print(f"  [{sym_short}] {year}: SKIP — only {bar_count} bars (need >= {MIN_BARS_PER_YEAR})", flush=True)
                missing_data[sym_short].append(str(year))
                continue

            print(f"  [{sym_short}] {year}: Running baseline ({bar_count} bars)...", flush=True)
            positions, close_events = await run_backtest(symbol, start, end, RESEARCH_RISK)
            metrics = compute_metrics(positions, close_events)
            metrics["classification"] = classify_year(metrics)
            results[sym_short][str(year)] = metrics
            print(f"  [{sym_short}] {year}: PnL={metrics['pnl']:+.2f}, T={metrics['trades']}, WR={metrics['win_rate']:.1%}, cls={metrics['classification']}", flush=True)

        # 2026 Q1
        start_q1, end_q1 = quarter_range_ms(2026, 1)
        bar_count = check_data_availability(symbol, start_q1, end_q1)
        if bar_count < 20:  # Q1 ~ 2160 bars expected, need at least 20
            print(f"  [{sym_short}] 2026_Q1: SKIP — only {bar_count} bars", flush=True)
            missing_data[sym_short].append("2026_Q1")
        else:
            print(f"  [{sym_short}] 2026_Q1: Running baseline ({bar_count} bars)...", flush=True)
            positions, close_events = await run_backtest(symbol, start_q1, end_q1, RESEARCH_RISK)
            metrics = compute_metrics(positions, close_events)
            metrics["classification"] = classify_year(metrics)
            results[sym_short]["2026_Q1"] = metrics
            print(f"  [{sym_short}] 2026_Q1: PnL={metrics['pnl']:+.2f}, T={metrics['trades']}, WR={metrics['win_rate']:.1%}", flush=True)

    # Report missing data
    has_missing = any(v for v in missing_data.values())
    if has_missing:
        print("\n⚠️  Missing Data Summary:", flush=True)
        for sym, years in missing_data.items():
            if years:
                print(f"  {sym}: missing {', '.join(years)}", flush=True)

    return results, missing_data


# ─── 报告生成 ────────────────────────────────────────────────────────────

def generate_json_report(results: dict, div_analysis: dict, missing_data: dict = None) -> dict:
    return {
        "title": "Multi-Symbol Baseline Transfer",
        "date": "2026-04-28",
        "hypothesis": "H5: ETH 1h LONG-only baseline can transfer to other symbols with low correlation and non-synchronized failure",
        "method": "Fixed ETH baseline parameters applied to BTC/SOL/BNB",
        "parameters": {
            "symbol": "ETH/USDT:USDT (baseline)",
            "timeframe": "1h",
            "ema_period": 50,
            "min_distance_pct": "0.005",
            "mtf_ema_period": 60,
            "atr": "disabled",
            "tp_targets": [1.0, 3.5],
            "tp_ratios": [0.5, 0.5],
            "breakeven": False,
            "risk_profile": "research (exposure=2.0)",
        },
        "results": results,
        "missing_data": missing_data or {},
        "diversification_analysis": div_analysis,
    }


def generate_markdown(results: dict, div_analysis: dict, missing_data: dict = None) -> str:
    lines = []
    lines.append("# H5: 多品种基线迁移验证")
    lines.append("")
    lines.append("> **日期**: 2026-04-28")
    lines.append("> **假设 H5**: ETH 1h LONG-only 基线能否迁移到其他品种，形成低相关、不同步失效的候选子策略？")
    lines.append("> **方法**: 用 ETH 固定基线参数跑 BTC/SOL/BNB 回测，对比相关性和失效同步性")
    lines.append("> **基线**: 1h, LONG-only, EMA50, TP=[1.0, 3.5], BE=False, BNB9 成本")
    lines.append("> **区间**: 2022-2025 + 2026 Q1")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 1. 各品种年度表现
    lines.append("## 1. 各品种年度表现（Research 口径）")
    lines.append("")

    for sym in ["ETH", "BTC", "SOL", "BNB"]:
        lines.append(f"### {sym}")
        lines.append("")
        lines.append("| 区间 | PnL | Trades | WR | Sharpe | MaxDD% | TP1% | TP2% | SL% | Hold(h) | 分类 |")
        lines.append("|------|-----|--------|-----|--------|--------|------|------|-----|---------|------|")
        for label in ["2022", "2023", "2024", "2025", "2026_Q1"]:
            if label in results[sym]:
                m = results[sym][label]
                cls_display = {"adapted": "适配", "boundary": "边界", "failed": "失效"}.get(m["classification"], m["classification"])
                lines.append(
                    f"| {label} | {m['pnl']:+.2f} | {m['trades']} | {m['win_rate']:.1%} | "
                    f"{m['sharpe']:.3f} | {m['max_dd_pct']:.1%} | {m['tp1_pct']:.1f}% | "
                    f"{m['tp2_pct']:.1f}% | {m['sl_pct']:.1f}% | {m['avg_holding_hours']:.1f} | {cls_display} |"
                )
        lines.append("")

    # 2. 横向对比
    lines.append("## 2. 横向对比（2022-2025 年度 PnL）")
    lines.append("")
    lines.append("| 年份 | ETH | BTC | SOL | BNB |")
    lines.append("|------|-----|-----|-----|-----|")
    for year in [2022, 2023, 2024, 2025]:
        vals = []
        for sym in ["ETH", "BTC", "SOL", "BNB"]:
            if str(year) in results[sym]:
                vals.append(f"{results[sym][str(year)]['pnl']:+.0f}")
            else:
                vals.append("-")
        lines.append(f"| {year} | {' | '.join(vals)} |")
    lines.append("")

    # 3. 分散化分析
    lines.append("## 3. 分散化分析")
    lines.append("")
    lines.append("### 3a. 与 ETH 的年度 PnL 相关性")
    lines.append("")
    lines.append("| 品种 | 相关系数 | 判读 |")
    lines.append("|------|---------|------|")
    for sym, corr in div_analysis["correlations"].items():
        if corr is None:
            interp = "数据不足，无法计算"
            corr_display = "N/A"
        elif corr > 0.8:
            interp = "高相关（beta 共振）"
            corr_display = f"{corr:.3f}"
        elif corr > 0.5:
            interp = "中等相关"
            corr_display = f"{corr:.3f}"
        else:
            interp = "低相关（分散化好）"
            corr_display = f"{corr:.3f}"
        lines.append(f"| {sym} | {corr_display} | {interp} |")
    lines.append(f"| **平均** | **{div_analysis['avg_correlation']:.3f}** | {div_analysis['interpretation']} |")
    lines.append("")

    lines.append("### 3b. 失效同步性分析")
    lines.append("")
    lines.append("**ETH 2023 失效（PnL=-3924）时其他品种表现：**")
    lines.append("")
    lines.append("| 品种 | 2023 PnL | 是否同步失效 | 判读 |")
    lines.append("|------|---------|-------------|------|")
    for sym, analysis in div_analysis["sync_analysis"].items():
        if analysis["sync_failed"] is None:
            sync_display = "N/A"
            interp = "数据缺失，无法评估"
        elif analysis["sync_failed"]:
            sync_display = "是"
            interp = "同步亏损（无分散化）"
        else:
            sync_display = "否"
            interp = "不同步（有分散化价值）"
        pnl_display = f'{analysis["symbol_2023_pnl"]:+.2f}' if analysis["symbol_2023_pnl"] is not None else "N/A"
        lines.append(f"| {sym} | {pnl_display} | {sync_display} | {interp} |")
    lines.append("")

    lines.append("### 3c. 综合判断")
    lines.append("")
    if div_analysis["beta_resonance"]:
        lines.append("**结论: 存在 crypto beta 共振** — 所有品种高度正相关，分散化收益有限。")
    else:
        lines.append("**结论: 存在分散化收益** — 品种间相关性不完全，可考虑组合配置。")
    lines.append("")

    # 4. 候选池
    lines.append("## 4. 候选池评估")
    lines.append("")
    lines.append("| 品种 | 是否进入候选池 | 理由 |")
    lines.append("|------|--------------|------|")

    eth_2023_failed = results["ETH"]["2023"]["classification"] == "failed"
    for sym in ["BTC", "SOL", "BNB"]:
        if sym == "ETH":
            continue
        sym_2023 = results[sym].get("2023", {})
        sym_2023_failed = sym_2023.get("classification") == "failed"

        # 进入候选池的条件：
        # 1. 2023 没有失效（不同步失效）
        # 2. 2024/2025 有适配年份
        # 3. 与 ETH 相关性 < 0.9
        corr = div_analysis["correlations"].get(sym, None)
        adapted_count = sum(1 for y in [2022, 2023, 2024, 2025] if results[sym].get(str(y), {}).get("classification") == "adapted")
        has_2023_data = "2023" in results[sym]

        if corr is None:
            lines.append(f"| {sym} | **无法评估** | 与其他品种共同年份不足 2 年，无法计算相关性 |")
        elif not has_2023_data:
            lines.append(f"| {sym} | **无法评估** | 2023 数据缺失，无法判断失效同步性 |")
        elif not sym_2023_failed and adapted_count >= 2 and corr < 0.9:
            lines.append(f"| {sym} | **是** | 2023 未失效（PnL={sym_2023.get('pnl', 0):+.0f}），适配 {adapted_count}/4 年，相关性={corr:.2f} |")
        elif sym_2023_failed:
            lines.append(f"| {sym} | 否 | 2023 同步失效（PnL={sym_2023.get('pnl', 0):+.0f}） |")
        elif adapted_count < 2:
            lines.append(f"| {sym} | 否 | 适配年份不足（仅 {adapted_count}/4） |")
        else:
            lines.append(f"| {sym} | 否 | 相关性过高（{corr:.2f}） |")
    lines.append("")

    # 5. 最终结论
    lines.append("## 5. 最终结论")
    lines.append("")

    # 计算 H5 判定
    candidates = []
    for sym in ["BTC", "SOL", "BNB"]:
        corr = div_analysis["correlations"].get(sym, None)
        sym_2023 = results[sym].get("2023", {})
        adapted_count = sum(1 for y in [2022, 2023, 2024, 2025] if results[sym].get(str(y), {}).get("classification") == "adapted")
        has_2023_data = "2023" in results[sym]
        if corr is not None and has_2023_data and not sym_2023.get("classification") == "failed" and adapted_count >= 2 and corr < 0.9:
            candidates.append(sym)

    if len(candidates) >= 2:
        h5_verdict = "通过"
    elif len(candidates) == 1:
        h5_verdict = "弱通过"
    else:
        h5_verdict = "不通过"

    lines.append(f"**H5 判定**: **{h5_verdict}**")
    lines.append("")
    lines.append("- **哪些品种值得进入候选池**: " + (", ".join(candidates) if candidates else "无"))
    lines.append("- **是否存在低相关/不同步失效证据**: " + ("是" if not div_analysis["beta_resonance"] else "否（beta 共振）"))
    lines.append("- **是否进入下一轮多周期验证**: " + ("是" if len(candidates) >= 1 else "否"))
    lines.append("- **是否禁止反向污染 sim1_eth_runtime**: 禁止（本轮所有结论均为 research-only）")
    lines.append("")

    # 5b. Missing data
    has_missing = missing_data and any(v for v in missing_data.values())
    if has_missing:
        lines.append("## 5b. 数据缺失说明")
        lines.append("")
        for sym, years in missing_data.items():
            if years:
                lines.append(f"- **{sym}**: 缺少 {', '.join(years)} 的 1h kline 数据（DB 中无记录），已跳过对应回测")
        lines.append("")
        lines.append("> BNB 仅覆盖 2021/2022/2026 Q1，无法评估 2023-2025 表现。")
        lines.append("> BTC/SOL 数据完整（2022-2026 Q1），以下分析以 ETH/BTC/SOL 三品种为主。")
        lines.append("")

    # 6. 全品种汇总
    lines.append("## 6. 全品种汇总")
    lines.append("")
    lines.append("| 品种 | 4yr PnL | 适配年数 | 边界年数 | 失效年数 | 与 ETH 相关性 | 进入候选池 |")
    lines.append("|------|---------|---------|---------|---------|--------------|----------|")
    for sym in ["ETH", "BTC", "SOL", "BNB"]:
        total_pnl = sum(results[sym].get(str(y), {}).get("pnl", 0) for y in [2022, 2023, 2024, 2025])
        adapted = sum(1 for y in [2022, 2023, 2024, 2025] if results[sym].get(str(y), {}).get("classification") == "adapted")
        boundary = sum(1 for y in [2022, 2023, 2024, 2025] if results[sym].get(str(y), {}).get("classification") == "boundary")
        failed = sum(1 for y in [2022, 2023, 2024, 2025] if results[sym].get(str(y), {}).get("classification") == "failed")
        corr = div_analysis["correlations"].get(sym, None)
        if isinstance(corr, (int, float)):
            corr_display = f"{corr:.3f}"
        else:
            corr_display = "baseline" if sym == "ETH" else "N/A"
        in_pool = "是" if sym in candidates else ("基准" if sym == "ETH" else "否")
        lines.append(f"| {sym} | {total_pnl:+.0f} | {adapted} | {boundary} | {failed} | {corr_display} | {in_pool} |")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("> **重要**: 本报告为 research-only 多品种迁移验证，不涉及任何 runtime 修改。")
    lines.append("> 基线参数保持冻结，不因结果修改。")
    lines.append("")
    lines.append("*分析完成时间: 2026-04-28*")
    lines.append("*性质: research-only，不跑引擎级实验，不改代码*")

    return "\n".join(lines)


# ─── 入口 ────────────────────────────────────────────────────────────────

async def main():
    print("=" * 80)
    print("H5: Multi-Symbol Baseline Transfer")
    print("=" * 80)
    print("\n配置:")
    print("- ETH 固定基线参数迁移到 BTC/SOL/BNB")
    print("- 1h, LONG-only, EMA50, TP=[1.0, 3.5], BE=False")
    print("- 区间: 2022-2025 + 2026 Q1")
    print("=" * 80)

    results, missing_data = await run_all()
    div_analysis = analyze_diversification(results)

    # Save JSON
    json_report = generate_json_report(results, div_analysis, missing_data)
    with open(JSON_PATH, "w") as f:
        json.dump(json_report, f, indent=2, ensure_ascii=False)
    print(f"\nJSON saved: {JSON_PATH}")

    # Save Markdown
    md_content = generate_markdown(results, div_analysis, missing_data)
    with open(MD_PATH, "w") as f:
        f.write(md_content)
    print(f"Markdown saved: {MD_PATH}")

    # Print summary
    print(f"\n{'=' * 80}")
    print("多品种迁移结果汇总")
    print(f"{'=' * 80}")
    for sym in ["BTC", "SOL", "BNB"]:
        total_pnl = sum(results[sym].get(str(y), {}).get("pnl", 0) for y in [2022, 2023, 2024, 2025])
        print(f"{sym}: 4yr PnL={total_pnl:+.0f}")
    print(f"\n与 ETH 相关性: {div_analysis['correlations']}")
    print(f"Beta共振: {div_analysis['beta_resonance']}")
    if any(v for v in missing_data.values()):
        print(f"\n缺失数据: {missing_data}")


if __name__ == "__main__":
    asyncio.run(main())
