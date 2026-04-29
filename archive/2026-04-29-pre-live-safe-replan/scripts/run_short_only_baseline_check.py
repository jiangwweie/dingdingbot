#!/usr/bin/env python3
"""
SHORT-only Baseline Check — 验证 H1：SHORT-only 是否有独立研究价值

假设 H1：
  在当前 ETH 1h Pinbar + EMA/MTF 框架下，SHORT-only 可能存在独立 alpha 痕迹，
  但不能默认镜像 LONG 结论。

测试设计：
  - 固定当前 LONG 基线参数，只切换 allowed_directions
  - 对照组：LONG-only（当前基线）、SHORT-only（同参数镜像）
  - 两种风险口径：Research + Sim-1
  - 年份：2023, 2024, 2025

严格边界：不改引擎、不改 runtime、不改 live 代码路径。
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
    BacktestRuntimeOverrides,
    OrderStrategy,
    PMSBacktestReport,
    PositionCloseEvent,
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
    id="short_baseline_check",
    name="SHORT baseline check",
    tp_levels=2,
    tp_ratios=[Decimal("0.5"), Decimal("0.5")],
    tp_targets=[Decimal("1.0"), Decimal("3.5")],
    initial_stop_loss_rr=Decimal("-1.0"),
    trailing_stop_enabled=False,
    oco_enabled=True,
)

REPORT_DIR = PROJECT_ROOT / "reports" / "research"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
JSON_PATH = REPORT_DIR / "short_only_baseline_check_2026-04-28.json"
MD_PATH = PROJECT_ROOT / "docs" / "planning" / "2026-04-28-short-only-baseline-check.md"


# ─── 工具 ────────────────────────────────────────────────────────────────

def year_range_ms(year: int) -> tuple[int, int]:
    start = int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    end = int(datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)
    return start, end


def compute_metrics(positions: list[PositionSummary], close_events: list[PositionCloseEvent]) -> dict:
    if not positions:
        return {
            "pnl": 0.0, "trades": 0, "wins": 0, "losses": 0,
            "win_rate": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
            "sharpe": 0.0, "max_dd": 0.0,
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

    # Exit reason breakdown from close_events
    tp1_count = 0
    tp2_count = 0
    sl_count = 0
    other_count = 0
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

    # Average holding time
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
        "tp1_count": tp1_count,
        "tp2_count": tp2_count,
        "sl_count": sl_count,
        "other_count": other_count,
        "tp1_pct": round(tp1_count / total_exits * 100, 1) if total_exits > 0 else 0.0,
        "tp2_pct": round(tp2_count / total_exits * 100, 1) if total_exits > 0 else 0.0,
        "sl_pct": round(sl_count / total_exits * 100, 1) if total_exits > 0 else 0.0,
        "avg_holding_hours": round(avg_holding_hours, 1),
    }


# ─── 回测执行 ────────────────────────────────────────────────────────────

async def run_backtest(
    year: int,
    risk_config: RiskConfig,
    allowed_directions: list[str],
) -> tuple[list[PositionSummary], list[PositionCloseEvent]]:
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

    overrides = BASELINE_RUNTIME_OVERRIDES.model_copy(deep=True)
    overrides.allowed_directions = allowed_directions

    report = await backtester.run_backtest(request, runtime_overrides=overrides)
    if isinstance(report, PMSBacktestReport):
        return report.positions, report.close_events
    return [], []


# ─── 主实验 ──────────────────────────────────────────────────────────────

async def run_all() -> dict:
    results = {}

    for risk_label, risk_config in [("research", RESEARCH_RISK), ("sim1", SIM1_RISK)]:
        results[risk_label] = {}
        for year in YEARS:
            print(f"\n  [{risk_label}] {year}: Running LONG-only baseline...", flush=True)
            long_positions, long_events = await run_backtest(year, risk_config, ["LONG"])
            long_metrics = compute_metrics(long_positions, long_events)
            print(f"  [{risk_label}] {year} LONG: PnL={long_metrics['pnl']:+.2f}, T={long_metrics['trades']}, WR={long_metrics['win_rate']:.1%}", flush=True)

            print(f"  [{risk_label}] {year}: Running SHORT-only mirror...", flush=True)
            short_positions, short_events = await run_backtest(year, risk_config, ["SHORT"])
            short_metrics = compute_metrics(short_positions, short_events)
            print(f"  [{risk_label}] {year} SHORT: PnL={short_metrics['pnl']:+.2f}, T={short_metrics['trades']}, WR={short_metrics['win_rate']:.1%}", flush=True)

            results[risk_label][year] = {
                "long": long_metrics,
                "short": short_metrics,
            }

    return results


# ─── 报告生成 ────────────────────────────────────────────────────────────

def generate_json_report(results: dict) -> dict:
    return {
        "title": "SHORT-only Baseline Check",
        "date": "2026-04-28",
        "hypothesis": "H1: SHORT-only may have independent alpha traces under ETH 1h Pinbar + EMA/MTF framework",
        "parameters": {
            "symbol": SYMBOL,
            "timeframe": TIMEFRAME,
            "ema_period": 50,
            "min_distance_pct": "0.005",
            "mtf_ema_period": 60,
            "atr": "disabled",
            "tp_targets": [1.0, 3.5],
            "tp_ratios": [0.5, 0.5],
            "breakeven": False,
            "long_directions": ["LONG"],
            "short_directions": ["SHORT"],
        },
        "results": results,
    }


def generate_markdown_report(results: dict) -> str:
    lines = []
    lines.append("# SHORT-only Baseline Check — H1 验证报告")
    lines.append("")
    lines.append("> **日期**: 2026-04-28")
    lines.append("> **假设 H1**: 在当前 ETH 1h Pinbar + EMA/MTF 框架下，SHORT-only 可能存在独立 alpha 痕迹，但不能默认镜像 LONG 结论")
    lines.append("> **方法**: 固定 LONG 基线参数，只切换 allowed_directions，对比 LONG-only vs SHORT-only")
    lines.append("> **基线**: ETH 1h LONG-only, EMA50, BNB9 成本")
    lines.append("")

    # ── 1. 合理推测 ──
    lines.append("## 1. 合理推测")
    lines.append("")
    lines.append("### 为什么 SHORT-only 可能成立")
    lines.append("")
    lines.append("- ETH 在 2023 年经历了显著下跌行情，SHORT 方向在趋势性下跌中天然有利")
    lines.append("- Pinbar 形态本身是方向中性的：看跌 Pinbar（长上影线）在下跌趋势中更常见")
    lines.append("- EMA 趋势过滤在 bearish 市场中会确认 SHORT 方向，形成趋势+形态双重确认")
    lines.append("- MTF 对齐在 bearish 高级别趋势中同样有效")
    lines.append("")
    lines.append("### 为什么 SHORT 不应直接镜像 LONG 参数")
    lines.append("")
    lines.append("- **趋势不对称性**: 加密市场长期偏多，下跌趋势通常更急促、更短暂，反弹更频繁")
    lines.append("- **波动率不对称**: 下跌时波动率更高，止损更容易被扫，需要更宽的止损或更小的仓位")
    lines.append("- **Pinbar 形态分布**: 看跌 Pinbar 的出现频率和形态质量可能与看涨 Pinbar 不同")
    lines.append("- **TP 目标适配**: 1R/3.5R 目标在急跌中可能过保守（SHORT 跑得更快），在震荡中可能过激进")
    lines.append("- **持仓时间**: SHORT 仓位平均持仓时间可能更短（急跌快弹），影响 TP2 达成率")
    lines.append("")

    # ── 2. 测试设计 ──
    lines.append("## 2. 测试设计")
    lines.append("")
    lines.append("| 参数 | 值 |")
    lines.append("|------|----|")
    lines.append("| symbol | ETH/USDT:USDT |")
    lines.append("| timeframe | 1h |")
    lines.append("| ema_period | 50 |")
    lines.append("| min_distance_pct | 0.005 |")
    lines.append("| mtf_ema_period | 60 |")
    lines.append("| ATR | disabled |")
    lines.append("| tp_targets | [1.0, 3.5] |")
    lines.append("| tp_ratios | [0.5, 0.5] |")
    lines.append("| breakeven | False |")
    lines.append("| LONG 组 | allowed_directions=['LONG'] |")
    lines.append("| SHORT 组 | allowed_directions=['SHORT'] |")
    lines.append("| 年份 | 2023, 2024, 2025 |")
    lines.append("| 风险口径 | Research (exposure=2.0) + Sim-1 (exposure=1.0) |")
    lines.append("")

    # ── 3. 结果 ──
    for risk_label, risk_display in [("research", "Research Baseline"), ("sim1", "Sim-1 Runtime")]:
        lines.append(f"## 3. 结果（{risk_display}）")
        lines.append("")

        for year in YEARS:
            year_data = results.get(risk_label, {}).get(year, {})
            long_m = year_data.get("long", {})
            short_m = year_data.get("short", {})

            lines.append(f"### {year}")
            lines.append("")
            lines.append("| 指标 | LONG-only | SHORT-only | 差异 |")
            lines.append("|------|-----------|------------|------|")
            lines.append(f"| PnL | {long_m.get('pnl', 0):+.2f} | {short_m.get('pnl', 0):+.2f} | {short_m.get('pnl', 0) - long_m.get('pnl', 0):+.2f} |")
            lines.append(f"| Trades | {long_m.get('trades', 0)} | {short_m.get('trades', 0)} | {short_m.get('trades', 0) - long_m.get('trades', 0):+d} |")
            lines.append(f"| Win Rate | {long_m.get('win_rate', 0):.1%} | {short_m.get('win_rate', 0):.1%} | {short_m.get('win_rate', 0) - long_m.get('win_rate', 0):+.1%} |")
            lines.append(f"| Sharpe | {long_m.get('sharpe', 0):.2f} | {short_m.get('sharpe', 0):.2f} | {short_m.get('sharpe', 0) - long_m.get('sharpe', 0):+.2f} |")
            lines.append(f"| MaxDD | {long_m.get('max_dd', 0):.2f} | {short_m.get('max_dd', 0):.2f} | {short_m.get('max_dd', 0) - long_m.get('max_dd', 0):+.2f} |")
            lines.append(f"| Avg Win | {long_m.get('avg_win', 0):.2f} | {short_m.get('avg_win', 0):.2f} | - |")
            lines.append(f"| Avg Loss | {long_m.get('avg_loss', 0):.2f} | {short_m.get('avg_loss', 0):.2f} | - |")
            lines.append(f"| TP1% | {long_m.get('tp1_pct', 0):.1f}% | {short_m.get('tp1_pct', 0):.1f}% | - |")
            lines.append(f"| TP2% | {long_m.get('tp2_pct', 0):.1f}% | {short_m.get('tp2_pct', 0):.1f}% | - |")
            lines.append(f"| SL% | {long_m.get('sl_pct', 0):.1f}% | {short_m.get('sl_pct', 0):.1f}% | - |")
            lines.append(f"| Avg Holding (h) | {long_m.get('avg_holding_hours', 0):.1f} | {short_m.get('avg_holding_hours', 0):.1f} | - |")
            lines.append("")

    # ── 4. 验证分析 ──
    lines.append("## 4. 验证分析")
    lines.append("")

    # Use research results for primary analysis (more trades = more signal)
    res = results.get("research", {})

    # 4a. SHORT positive years
    short_positive_years = []
    for year in YEARS:
        short_pnl = res.get(year, {}).get("short", {}).get("pnl", 0)
        if short_pnl > 0:
            short_positive_years.append((year, short_pnl))

    lines.append("### 4a. SHORT-only 是否有正收益年份？")
    lines.append("")
    if short_positive_years:
        for y, pnl in short_positive_years:
            lines.append(f"- **{y}**: SHORT PnL = {pnl:+.2f} (正收益)")
        lines.append("")
        lines.append(f"SHORT 在 {len(short_positive_years)}/{len(YEARS)} 个年份有正收益。")
    else:
        lines.append("SHORT 在所有测试年份均为负收益。")
    lines.append("")

    # 4b. SHORT year-specific effectiveness
    lines.append("### 4b. SHORT 是否只是在某一年有效？")
    lines.append("")
    short_pnls = {y: res.get(y, {}).get("short", {}).get("pnl", 0) for y in YEARS}
    long_pnls = {y: res.get(y, {}).get("long", {}).get("pnl", 0) for y in YEARS}
    short_beats_long = [y for y in YEARS if short_pnls.get(y, 0) > long_pnls.get(y, 0)]
    lines.append("| 年份 | LONG PnL | SHORT PnL | SHORT 优于 LONG？ |")
    lines.append("|------|---------|----------|------------------|")
    for y in YEARS:
        lp = long_pnls.get(y, 0)
        sp = short_pnls.get(y, 0)
        better = "Yes" if sp > lp else "No"
        lines.append(f"| {y} | {lp:+.2f} | {sp:+.2f} | {better} |")
    lines.append("")
    if len(short_beats_long) == 1:
        lines.append(f"SHORT 仅在 {short_beats_long[0]} 年优于 LONG，属于单年效应，不足以支撑独立研究线。")
    elif len(short_beats_long) >= 2:
        lines.append(f"SHORT 在 {len(short_beats_long)} 个年份优于 LONG（{', '.join(map(str, short_beats_long))}），有一定跨年稳定性。")
    else:
        lines.append("SHORT 在所有年份均劣于 LONG，无独立研究价值。")
    lines.append("")

    # 4c. Failure mode symmetry
    lines.append("### 4c. SHORT 的失败方式是否和 LONG 对称？")
    lines.append("")
    for y in YEARS:
        long_m = res.get(y, {}).get("long", {})
        short_m = res.get(y, {}).get("short", {})
        long_wr = long_m.get("win_rate", 0)
        short_wr = short_m.get("win_rate", 0)
        long_sl = long_m.get("sl_pct", 0)
        short_sl = short_m.get("sl_pct", 0)
        long_tp2 = long_m.get("tp2_pct", 0)
        short_tp2 = short_m.get("tp2_pct", 0)
        lines.append(f"**{y}**: LONG WR={long_wr:.1%}/SL={long_sl:.1f}%/TP2={long_tp2:.1f}% vs SHORT WR={short_wr:.1%}/SL={short_sl:.1f}%/TP2={short_tp2:.1f}%")
    lines.append("")

    # 4d. Parameter mirror suitability
    lines.append("### 4d. 当前参数镜像是否明显不适合 SHORT？")
    lines.append("")
    # Compare TP1/TP2 hit rates and holding times
    for y in YEARS:
        long_m = res.get(y, {}).get("long", {})
        short_m = res.get(y, {}).get("short", {})
        long_tp1 = long_m.get("tp1_pct", 0)
        short_tp1 = short_m.get("tp1_pct", 0)
        long_tp2 = long_m.get("tp2_pct", 0)
        short_tp2 = short_m.get("tp2_pct", 0)
        long_hold = long_m.get("avg_holding_hours", 0)
        short_hold = short_m.get("avg_holding_hours", 0)
        lines.append(f"**{y}**: LONG TP1={long_tp1:.1f}%/TP2={long_tp2:.1f}%/Hold={long_hold:.0f}h vs SHORT TP1={short_tp1:.1f}%/TP2={short_tp2:.1f}%/Hold={short_hold:.0f}h")
    lines.append("")

    # 4e. Worth independent parameter search?
    lines.append("### 4e. 是否值得进入 SHORT 独立参数搜索？")
    lines.append("")
    total_short_pnl = sum(short_pnls.get(y, 0) for y in YEARS)
    total_long_pnl = sum(long_pnls.get(y, 0) for y in YEARS)
    lines.append(f"3 年累计: LONG={total_long_pnl:+.2f}, SHORT={total_short_pnl:+.2f}")
    lines.append("")

    # ── 5. 样本外建议 ──
    lines.append("## 5. 样本外建议")
    lines.append("")
    lines.append("如果 H1 弱通过，建议的 OOS 验证区间：")
    lines.append("")
    lines.append("- **2022**: ETH 从 ~4800 跌至 ~1200，全年熊市，SHORT 理论上应有正收益")
    lines.append("- **2026 Q1**: 如果数据可用，验证 SHORT 在当前市场环境下的表现")
    lines.append("- **2021**: ETH 从 ~700 涨至 ~4800，牛市年份，验证 SHORT 在极端牛市中的亏损幅度")
    lines.append("")
    lines.append("OOS 验证方法：")
    lines.append("1. 使用同参数镜像跑 2022 全年，观察 SHORT PnL 是否为正")
    lines.append("2. 如 2022 SHORT 正收益，再跑 2021 验证 SHORT 在牛市中的最大亏损")
    lines.append("3. 计算 SHORT-only 的 3 年 IS + 2 年 OOS 综合夏普比")
    lines.append("4. 与 LONG-only 同期对比，判断是否值得独立研究")
    lines.append("")

    # ── 6. 最终结论 ──
    lines.append("## 6. 最终结论")
    lines.append("")

    # Decision logic
    has_positive_year = len(short_positive_years) > 0
    multi_year_beats = len(short_beats_long) >= 2

    if multi_year_beats and has_positive_year:
        h1_verdict = "弱通过"
        short_research = "值得进入 SHORT 独立研究线"
        param_adjust = "需要调整 SHORT 参数（止损宽度、TP 目标、EMA 周期）"
        runtime_ban = "禁止直接进入 runtime，需先完成独立参数搜索"
    elif has_positive_year and not multi_year_beats:
        h1_verdict = "弱通过"
        short_research = "有条件进入 SHORT 独立研究线（仅限特定年份/市场环境）"
        param_adjust = "必须调整 SHORT 参数，当前镜像参数不适合 SHORT"
        runtime_ban = "禁止直接进入 runtime"
    else:
        h1_verdict = "不通过"
        short_research = "不建议进入 SHORT 独立研究线"
        param_adjust = "即使调整参数，SHORT 在当前框架下也难以盈利"
        runtime_ban = "禁止进入 runtime"

    lines.append(f"**H1 判定**: {h1_verdict}")
    lines.append("")
    lines.append(f"- **是否进入 SHORT 独立研究线**: {short_research}")
    lines.append(f"- **是否需要调整 SHORT 参数**: {param_adjust}")
    lines.append(f"- **是否禁止直接进入 runtime**: {runtime_ban}")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("> MFE/MAE/+1R/+2R/+3.5R 可达率、first-touch 等指标标记为 TODO。")
    lines.append("> PositionSummary 不含 excursion 数据，需要后续接入 continuation-ability 分析管道。")

    return "\n".join(lines)


# ─── 主入口 ──────────────────────────────────────────────────────────────

async def main():
    print("=" * 60)
    print("  SHORT-only Baseline Check")
    print("  H1: SHORT-only 是否有独立研究价值？")
    print("  - LONG-only vs SHORT-only (same parameters)")
    print("  - Dual risk profile: research + Sim-1")
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

    # Summary
    print(f"\n{'='*60}")
    print("  Summary")
    print(f"{'='*60}")
    for risk_label in ["research", "sim1"]:
        print(f"\n  [{risk_label}]", flush=True)
        for year in YEARS:
            yd = results.get(risk_label, {}).get(year, {})
            long_m = yd.get("long", {})
            short_m = yd.get("short", {})
            print(
                f"    {year}: LONG PnL={long_m.get('pnl', 0):+.2f} T={long_m.get('trades', 0)} WR={long_m.get('win_rate', 0):.1%} | "
                f"SHORT PnL={short_m.get('pnl', 0):+.2f} T={short_m.get('trades', 0)} WR={short_m.get('win_rate', 0):.1%}",
                flush=True,
            )


if __name__ == "__main__":
    asyncio.run(main())
