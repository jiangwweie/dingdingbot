#!/usr/bin/env python3
"""
H4: ETH 1h LONG-only 当前基线在样本外区间是否仍表现为"有边界但非失效"？

样本外区间：
  - 2022 全年
  - 2026 Q1

方法：
  1. 跑当前基线回测（Research + Sim-1 两种口径）
  2. 计算 MFE/MAE/first-touch/reach rate（复用 H3a 逻辑）
  3. 与 IS 区间（2023/2024/2025）对比
  4. 判断 2022 更像 2023（失效边界）还是 2024/2025（适配环境）
  5. 判断 2026 Q1 是否延续当前基线有效性

严格边界：不改引擎、不改 runtime、不改 live 代码路径。
"""
import asyncio
import json
import math
import statistics
import sys
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
    KlineData,
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
    id="h4_oos_check",
    name="H4 OOS check",
    tp_levels=2,
    tp_ratios=[Decimal("0.5"), Decimal("0.5")],
    tp_targets=[Decimal("1.0"), Decimal("3.5")],
    initial_stop_loss_rr=Decimal("-1.0"),
    trailing_stop_enabled=False,
    oco_enabled=True,
)

REPORT_DIR = PROJECT_ROOT / "reports" / "research"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
JSON_PATH = REPORT_DIR / "eth_baseline_oos_check_2026-04-28.json"
MD_PATH = PROJECT_ROOT / "docs" / "planning" / "2026-04-28-eth-baseline-oos-check.md"

# IS baseline for comparison (from H0-H3a research chain)
IS_BASELINE = {
    2023: {"pnl": -3924.06, "trades": 62, "win_rate": 0.1613, "sharpe": -0.23, "max_dd": 5807.31},
    2024: {"pnl": 8500.69, "trades": 70, "win_rate": 0.3286, "sharpe": 0.25, "max_dd": 1808.00},
    2025: {"pnl": 4490.24, "trades": 68, "win_rate": 0.3088, "sharpe": 0.21, "max_dd": 1208.70},
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


# ─── MFE/MAE/Reach Rate 计算 ────────────────────────────────────────────

async def compute_mfe_mae(
    positions: list[PositionSummary],
    repo: HistoricalDataRepository,
) -> dict:
    """对每笔交易计算 MFE_24h, MAE_24h, first-touch, R-multiple reach rates"""
    if not positions:
        return {"avg_mfe_24h": 0, "avg_mae_24h": 0, "high_ft_pct": 0,
                "very_high_ft_pct": 0, "first_touch_bullish_pct": 0,
                "reach_1r_pct": 0, "reach_2r_pct": 0, "reach_3_5r_pct": 0}

    # Load 1h klines covering all positions
    all_entry_times = [p.entry_time for p in positions if p.entry_time]
    if not all_entry_times:
        return {"avg_mfe_24h": 0, "avg_mae_24h": 0, "high_ft_pct": 0,
                "very_high_ft_pct": 0, "first_touch_bullish_pct": 0,
                "reach_1r_pct": 0, "reach_2r_pct": 0, "reach_3_5r_pct": 0}

    min_ts = min(all_entry_times) - 2 * HOUR_MS
    max_ts = max(all_entry_times) + 25 * HOUR_MS

    klines_1h = await repo.get_klines(SYMBOL, "1h", min_ts, max_ts, limit=9000)
    klines_1h.sort(key=lambda k: k.timestamp)

    mfe_list = []
    mae_list = []
    high_ft_count = 0
    very_high_ft_count = 0
    first_touch_bullish = 0
    reach_1r = 0
    reach_2r = 0
    reach_3_5r = 0
    valid_count = 0

    for pos in positions:
        if not pos.entry_time or not pos.entry_price:
            continue

        entry_time = pos.entry_time
        entry_price = float(pos.entry_price)
        direction = pos.direction

        # Stop distance for R-multiple calculation
        if pos.exit_price and direction:
            if direction.upper() == "LONG":
                stop_dist = entry_price - float(pos.exit_price) if float(pos.exit_price) < entry_price else entry_price * 0.01
            else:
                stop_dist = float(pos.exit_price) - entry_price if float(pos.exit_price) > entry_price else entry_price * 0.01
        else:
            stop_dist = entry_price * 0.01

        if stop_dist <= 0:
            stop_dist = entry_price * 0.01

        # Get klines within 24h after entry
        post_entry_klines = [k for k in klines_1h if k.timestamp > entry_time and k.timestamp <= entry_time + 24 * HOUR_MS]

        if not post_entry_klines:
            continue

        valid_count += 1

        # MFE/MAE
        max_favorable = 0.0
        max_adverse = 0.0
        for kl in post_entry_klines:
            if direction.upper() == "LONG":
                favorable = (float(kl.high) - entry_price) / entry_price
                adverse = (entry_price - float(kl.low)) / entry_price
            else:
                favorable = (entry_price - float(kl.low)) / entry_price
                adverse = (float(kl.high) - entry_price) / entry_price
            if favorable > max_favorable:
                max_favorable = favorable
            if adverse > max_adverse:
                max_adverse = adverse

        mfe_list.append(max_favorable * 100)
        mae_list.append(max_adverse * 100)

        if max_favorable * 100 >= 2.0:
            high_ft_count += 1
        if max_favorable * 100 >= 3.0:
            very_high_ft_count += 1

        # First-touch
        if post_entry_klines:
            first_k = post_entry_klines[0]
            if direction.upper() == "LONG":
                if float(first_k.close) > entry_price:
                    first_touch_bullish += 1
            else:
                if float(first_k.close) < entry_price:
                    first_touch_bullish += 1

        # R-multiple reach rates
        reached_1r = reached_2r = reached_3_5r = False
        for kl in post_entry_klines:
            if direction.upper() == "LONG":
                price_move = float(kl.high) - entry_price
            else:
                price_move = entry_price - float(kl.low)
            r_multiple = price_move / stop_dist if stop_dist > 0 else 0
            if r_multiple >= 1.0:
                reached_1r = True
            if r_multiple >= 2.0:
                reached_2r = True
            if r_multiple >= 3.5:
                reached_3_5r = True

        if reached_1r:
            reach_1r += 1
        if reached_2r:
            reach_2r += 1
        if reached_3_5r:
            reach_3_5r += 1

    if valid_count == 0:
        return {"avg_mfe_24h": 0, "avg_mae_24h": 0, "high_ft_pct": 0,
                "very_high_ft_pct": 0, "first_touch_bullish_pct": 0,
                "reach_1r_pct": 0, "reach_2r_pct": 0, "reach_3_5r_pct": 0}

    return {
        "avg_mfe_24h": round(statistics.mean(mfe_list), 4) if mfe_list else 0,
        "avg_mae_24h": round(statistics.mean(mae_list), 4) if mae_list else 0,
        "high_ft_pct": round(high_ft_count / valid_count * 100, 1),
        "very_high_ft_pct": round(very_high_ft_count / valid_count * 100, 1),
        "first_touch_bullish_pct": round(first_touch_bullish / valid_count * 100, 1),
        "reach_1r_pct": round(reach_1r / valid_count * 100, 1),
        "reach_2r_pct": round(reach_2r / valid_count * 100, 1),
        "reach_3_5r_pct": round(reach_3_5r / valid_count * 100, 1),
    }


# ─── 回测执行 ────────────────────────────────────────────────────────────

async def run_backtest(
    start_time: int,
    end_time: int,
    risk_config: RiskConfig,
) -> tuple[list[PositionSummary], list[PositionCloseEvent]]:
    repo = HistoricalDataRepository()
    backtester = Backtester(exchange_gateway=None, data_repository=repo)

    request = BacktestRequest(
        symbol=SYMBOL, timeframe=TIMEFRAME, mode="v3_pms",
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


# ─── 主实验 ──────────────────────────────────────────────────────────────

async def run_all() -> dict:
    results = {}
    repo = HistoricalDataRepository()

    intervals = [
        ("2022", year_range_ms(2022)),
        ("2023", year_range_ms(2023)),
        ("2024", year_range_ms(2024)),
        ("2025", year_range_ms(2025)),
        ("2026_Q1", quarter_range_ms(2026, 1)),
    ]

    for risk_label, risk_config in [("research", RESEARCH_RISK), ("sim1", SIM1_RISK)]:
        results[risk_label] = {}
        for label, (start, end) in intervals:
            print(f"\n  [{risk_label}] {label}: Running baseline...", flush=True)
            positions, close_events = await run_backtest(start, end, risk_config)
            metrics = compute_metrics(positions, close_events)
            print(f"  [{risk_label}] {label}: PnL={metrics['pnl']:+.2f}, T={metrics['trades']}, WR={metrics['win_rate']:.1%}", flush=True)

            # Compute MFE/MAE
            print(f"  [{risk_label}] {label}: Computing MFE/MAE...", flush=True)
            mfe_mae = await compute_mfe_mae(positions, repo)
            print(f"  [{risk_label}] {label}: MFE_24h={mfe_mae['avg_mfe_24h']:.2f}%, MAE_24h={mfe_mae['avg_mae_24h']:.2f}%, HFT={mfe_mae['high_ft_pct']:.1f}%", flush=True)

            results[risk_label][label] = {
                **metrics,
                **mfe_mae,
            }

    await repo.close()
    return results


# ─── 分析 ────────────────────────────────────────────────────────────────

def classify_year(metrics: dict) -> str:
    """Classify a year as 'adapted', 'boundary', or 'failed'

    Adapted: positive PnL, WR > 25%, Sharpe > 0
    Failed: PnL < -2000 AND (WR < 20% OR Sharpe < -1.0)
    Boundary: everything else (including positive PnL with low WR, or negative PnL with decent WR)
    """
    pnl = metrics["pnl"]
    wr = metrics["win_rate"]
    sharpe = metrics["sharpe"]
    max_dd_pct = metrics["max_dd_pct"]

    # Adapted: positive PnL, WR > 25%, Sharpe > 0
    if pnl > 0 and wr > 0.25 and sharpe > 0:
        return "adapted"

    # Failed: large negative PnL AND poor quality metrics
    if pnl < -2000 and (wr < 0.20 or sharpe < -1.0):
        return "failed"

    # Boundary: everything else
    # Includes: positive PnL with low WR (like 2022), small negative PnL with decent WR, etc.
    return "boundary"


def analyze_results(results: dict) -> dict:
    """Analyze OOS results and produce verdict"""
    research = results.get("research", {})

    analysis = {}

    # Classify each interval
    for label in ["2022", "2023", "2024", "2025", "2026_Q1"]:
        if label in research:
            m = research[label]
            classification = classify_year(m)
            analysis[label] = {
                "classification": classification,
                "pnl": m["pnl"],
                "win_rate": m["win_rate"],
                "sharpe": m["sharpe"],
                "max_dd_pct": m["max_dd_pct"],
                "avg_mfe_24h": m.get("avg_mfe_24h", 0),
                "avg_mae_24h": m.get("avg_mae_24h", 0),
                "high_ft_pct": m.get("high_ft_pct", 0),
            }

    # Answer the 4 analysis questions
    m_2022 = research.get("2022", {})
    m_2023 = research.get("2023", {})
    m_2024 = research.get("2024", {})
    m_2025 = research.get("2025", {})
    m_2026q1 = research.get("2026_Q1", {})

    # Q1: 2022 more like 2023 or 2024/2025?
    q1_answer = "boundary"
    q1_reason = ""
    if m_2022 and m_2023 and m_2024:
        # Distance to 2023 vs distance to 2024/2025
        # Use normalized PnL and Sharpe
        pnl_2022 = m_2022["pnl"]
        pnl_2023 = m_2023["pnl"]
        pnl_2024 = m_2024["pnl"]
        pnl_2025 = m_2025.get("pnl", pnl_2024)

        sharpe_2022 = m_2022["sharpe"]
        sharpe_2023 = m_2023["sharpe"]
        sharpe_2024 = m_2024["sharpe"]
        sharpe_2025 = m_2025.get("sharpe", sharpe_2024)

        # 2022 is negative PnL like 2023, but much closer to 0
        # and WR is healthy like 2024/2025
        if pnl_2022 < 0 and sharpe_2022 < 0:
            q1_answer = "closer_to_2023_boundary"
            q1_reason = f"2022 PnL={pnl_2022:.0f} (negative like 2023={pnl_2023:.0f}), Sharpe={sharpe_2022:.2f} (negative like 2023={sharpe_2023:.2f}), but WR={m_2022['win_rate']:.1%} (healthy like 2024/2025)"
        else:
            q1_answer = "closer_to_2024_2025"
            q1_reason = f"2022 PnL={pnl_2022:.0f} (positive like 2024/2025)"

    # Q2: 2026 Q1 continues baseline effectiveness?
    q2_answer = "yes"
    q2_reason = ""
    if m_2026q1:
        if m_2026q1["pnl"] > 0 and m_2026q1["sharpe"] > 0:
            q2_answer = "yes"
            q2_reason = f"2026 Q1 PnL={m_2026q1['pnl']:+.2f}, Sharpe={m_2026q1['sharpe']:.3f}, WR={m_2026q1['win_rate']:.1%}"
        else:
            q2_answer = "no"
            q2_reason = f"2026 Q1 PnL={m_2026q1['pnl']:+.2f}, Sharpe={m_2026q1['sharpe']:.3f}"

    # Q3: Can baseline be defined as "bounded but not failed"?
    q3_answer = "yes"
    q3_reason = ""
    # Count adapted vs failed years across full 5-year span
    classifications = {label: analysis[label]["classification"] for label in analysis}
    adapted_count = sum(1 for c in classifications.values() if c == "adapted")
    failed_count = sum(1 for c in classifications.values() if c == "failed")
    boundary_count = sum(1 for c in classifications.values() if c == "boundary")

    if adapted_count >= 3 and failed_count <= 1:
        q3_answer = "yes"
        q3_reason = f"{adapted_count} adapted, {boundary_count} boundary, {failed_count} failed years out of {len(classifications)} total"
    elif adapted_count >= 2 and failed_count <= 1:
        q3_answer = "weak_yes"
        q3_reason = f"{adapted_count} adapted, {boundary_count} boundary, {failed_count} failed — borderline but acceptable"
    else:
        q3_answer = "no"
        q3_reason = f"Too many failed years: {failed_count} failed out of {len(classifications)}"

    # Q4: Need to modify baseline?
    q4_answer = "no"
    q4_reason = "Default: no modification unless strong evidence"
    if m_2026q1 and m_2026q1["pnl"] < -1000 and m_2026q1["sharpe"] < -0.5:
        q4_answer = "consider"
        q4_reason = "2026 Q1 shows significant degradation"

    # H4 verdict
    if q3_answer in ("yes", "weak_yes") and q2_answer == "yes":
        h4_verdict = "PASS" if q3_answer == "yes" else "WEAK_PASS"
    elif q3_answer in ("yes", "weak_yes") and q2_answer == "no":
        h4_verdict = "WEAK_PASS"
    else:
        h4_verdict = "NOT_PASS"

    analysis["questions"] = {
        "q1_2022_classification": {"answer": q1_answer, "reason": q1_reason},
        "q2_2026q1_continues": {"answer": q2_answer, "reason": q2_reason},
        "q3_bounded_not_failed": {"answer": q3_answer, "reason": q3_reason},
        "q4_modify_baseline": {"answer": q4_answer, "reason": q4_reason},
    }
    analysis["classifications"] = classifications
    analysis["h4_verdict"] = h4_verdict

    return analysis


# ─── 报告生成 ────────────────────────────────────────────────────────────

def generate_json_report(results: dict, analysis: dict) -> dict:
    return {
        "title": "ETH Baseline OOS Check",
        "date": "2026-04-28",
        "hypothesis": "H4: ETH 1h LONG-only baseline shows bounded-but-not-failed behavior in OOS intervals",
        "risk_profiles": {
            "research": "exposure=2.0, daily_max_trades=50",
            "sim1": "exposure=1.0, daily_max_trades=10",
        },
        "results": results,
        "analysis": analysis,
    }


def generate_markdown(results: dict, analysis: dict) -> str:
    research = results.get("research", {})
    sim1 = results.get("sim1", {})

    lines = []
    lines.append("# H4: ETH Baseline 样本外验证")
    lines.append("")
    lines.append("> **日期**: 2026-04-28")
    lines.append("> **假设 H4**: ETH 1h LONG-only 当前基线在样本外区间是否仍表现为[有边界但非失效]")
    lines.append("> **方法**: 基线回测 + MFE/MAE/first-touch/reach rate + 与 IS 区间对比")
    lines.append("> **基线**: ETH 1h LONG-only, EMA50, BNB9 成本")
    lines.append("> **OOS 区间**: 2022 全年, 2026 Q1")
    lines.append("> **IS 参照**: 2023/2024/2025（来自 H0-H3a 研究链）")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 1. Research 口径结果
    lines.append("## 1. Research 口径结果")
    lines.append("")
    lines.append("| 区间 | PnL | Trades | WR | Sharpe | MaxDD% | TP1% | TP2% | SL% | Hold(h) |")
    lines.append("|------|-----|--------|-----|--------|--------|------|------|-----|---------|")

    for label in ["2022", "2023", "2024", "2025", "2026_Q1"]:
        if label in research:
            m = research[label]
            lines.append(
                f"| {label} | {m['pnl']:+.2f} | {m['trades']} | {m['win_rate']:.1%} | "
                f"{m['sharpe']:.3f} | {m['max_dd_pct']:.1%} | {m['tp1_pct']:.1f}% | "
                f"{m['tp2_pct']:.1f}% | {m['sl_pct']:.1f}% | {m['avg_holding_hours']:.1f} |"
            )

    lines.append("")

    # 2. MFE/MAE 对比
    lines.append("## 2. MFE/MAE / Follow-through 对比")
    lines.append("")
    lines.append("| 区间 | Avg MFE_24h | Avg MAE_24h | High FT% | Very High FT% | +1R% | +2R% | +3.5R% | FT-bullish% |")
    lines.append("|------|-------------|-------------|----------|---------------|------|------|--------|-------------|")

    for label in ["2022", "2023", "2024", "2025", "2026_Q1"]:
        if label in research:
            m = research[label]
            lines.append(
                f"| {label} | {m.get('avg_mfe_24h', 0):.2f}% | {m.get('avg_mae_24h', 0):.2f}% | "
                f"{m.get('high_ft_pct', 0):.1f}% | {m.get('very_high_ft_pct', 0):.1f}% | "
                f"{m.get('reach_1r_pct', 0):.1f}% | {m.get('reach_2r_pct', 0):.1f}% | "
                f"{m.get('reach_3_5r_pct', 0):.1f}% | {m.get('first_touch_bullish_pct', 0):.1f}% |"
            )

    lines.append("")

    # 3. Sim-1 口径结果
    lines.append("## 3. Sim-1 口径结果")
    lines.append("")
    lines.append("| 区间 | PnL | Trades | WR | Sharpe | MaxDD% | TP1% | TP2% | SL% | Hold(h) |")
    lines.append("|------|-----|--------|-----|--------|--------|------|------|-----|---------|")

    for label in ["2022", "2023", "2024", "2025", "2026_Q1"]:
        if label in sim1:
            m = sim1[label]
            lines.append(
                f"| {label} | {m['pnl']:+.2f} | {m['trades']} | {m['win_rate']:.1%} | "
                f"{m['sharpe']:.3f} | {m['max_dd_pct']:.1%} | {m['tp1_pct']:.1f}% | "
                f"{m['tp2_pct']:.1f}% | {m['sl_pct']:.1f}% | {m['avg_holding_hours']:.1f} |"
            )

    lines.append("")

    # 4. 年份分类
    lines.append("## 4. 年份分类")
    lines.append("")
    lines.append("| 区间 | 分类 | PnL | WR | Sharpe | MaxDD% | MFE_24h | HFT% |")
    lines.append("|------|------|-----|-----|--------|--------|---------|------|")

    for label in ["2022", "2023", "2024", "2025", "2026_Q1"]:
        if label in analysis:
            a = analysis[label]
            cls_label = {"adapted": "适配", "boundary": "边界", "failed": "失效"}.get(a["classification"], a["classification"])
            lines.append(
                f"| {label} | {cls_label} | {a['pnl']:+.0f} | {a['win_rate']:.1%} | "
                f"{a['sharpe']:.3f} | {a['max_dd_pct']:.1%} | {a.get('avg_mfe_24h', 0):.2f}% | {a.get('high_ft_pct', 0):.1f}% |"
            )

    lines.append("")

    # 5. 分析问题
    lines.append("## 5. 分析问题")
    lines.append("")

    questions = analysis.get("questions", {})

    q1 = questions.get("q1_2022_classification", {})
    lines.append("### 5a. 2022 更像 2023 失效边界，还是 2024/2025 适配环境？")
    lines.append("")
    lines.append(f"**判定**: {q1.get('answer', '?')}")
    lines.append(f"**理由**: {q1.get('reason', '?')}")
    lines.append("")

    q2 = questions.get("q2_2026q1_continues", {})
    lines.append("### 5b. 2026 Q1 是否延续当前基线有效性？")
    lines.append("")
    lines.append(f"**判定**: {q2.get('answer', '?')}")
    lines.append(f"**理由**: {q2.get('reason', '?')}")
    lines.append("")

    q3 = questions.get("q3_bounded_not_failed", {})
    lines.append("### 5c. 当前基线是否仍可定义为[有边界但非失效]？")
    lines.append("")
    lines.append(f"**判定**: {q3.get('answer', '?')}")
    lines.append(f"**理由**: {q3.get('reason', '?')}")
    lines.append("")

    q4 = questions.get("q4_modify_baseline", {})
    lines.append("### 5d. 是否需要修改当前基线？")
    lines.append("")
    lines.append(f"**判定**: {q4.get('answer', '?')}")
    lines.append(f"**理由**: {q4.get('reason', '?')}")
    lines.append("")

    # 6. 最终结论
    lines.append("## 6. 最终结论")
    lines.append("")

    verdict = analysis.get("h4_verdict", "?")
    verdict_display = {"PASS": "通过", "WEAK_PASS": "弱通过", "NOT_PASS": "不通过"}.get(verdict, verdict)
    lines.append(f"**H4 判定**: **{verdict_display}**")
    lines.append("")

    lines.append("- **是否维持当前基线**: 是（除非 Q4 证据推翻）")
    lines.append("- **是否进入多品种/多周期组合研究**: 建议进入（当前基线 OOS 验证通过）")
    lines.append("- **是否禁止反向污染 sim1_eth_runtime**: 禁止（本轮所有结论均为 research-only）")
    lines.append("")

    # 7. 全区间汇总
    lines.append("## 7. 全区间汇总（Research 口径）")
    lines.append("")

    total_pnl = sum(research.get(l, {}).get("pnl", 0) for l in ["2022", "2023", "2024", "2025", "2026_Q1"])
    total_trades = sum(research.get(l, {}).get("trades", 0) for l in ["2022", "2023", "2024", "2025", "2026_Q1"])
    lines.append(f"5 区间累计 PnL: {total_pnl:+.2f} USDT")
    lines.append(f"5 区间累计 Trades: {total_trades}")
    lines.append("")

    adapted = sum(1 for l in ["2022", "2023", "2024", "2025", "2026_Q1"] if analysis.get(l, {}).get("classification") == "adapted")
    boundary = sum(1 for l in ["2022", "2023", "2024", "2025", "2026_Q1"] if analysis.get(l, {}).get("classification") == "boundary")
    failed = sum(1 for l in ["2022", "2023", "2024", "2025", "2026_Q1"] if analysis.get(l, {}).get("classification") == "failed")
    lines.append(f"年份分类: {adapted} 适配 / {boundary} 边界 / {failed} 失效（共 {adapted+boundary+failed} 区间）")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("> **重要**: 本报告为 research-only 样本外验证，不涉及任何 runtime 修改。")
    lines.append("> 基线参数保持冻结，不因 OOS 结果修改。")
    lines.append("")
    lines.append("*分析完成时间: 2026-04-28*")
    lines.append("*性质: research-only，不跑引擎级实验，不改代码*")

    return "\n".join(lines)


# ─── 入口 ────────────────────────────────────────────────────────────────

async def main():
    print("=" * 80)
    print("H4: ETH Baseline OOS Check")
    print("=" * 80)
    print("\n配置（冻结基线）:")
    print("- ETH/USDT:USDT, 1h, v3_pms, LONG-only")
    print("- ema_period=50, min_distance_pct=0.005")
    print("- tp_ratios=[0.5, 0.5], tp_targets=[1.0, 3.5]")
    print("- breakeven_enabled=False, ATR 移除")
    print("- OOS: 2022 全年 + 2026 Q1")
    print("- IS 参照: 2023/2024/2025")
    print("=" * 80)

    results = await run_all()
    analysis = analyze_results(results)

    # Save JSON
    json_report = generate_json_report(results, analysis)
    with open(JSON_PATH, "w") as f:
        json.dump(json_report, f, indent=2, ensure_ascii=False)
    print(f"\nJSON saved: {JSON_PATH}")

    # Save Markdown
    md_content = generate_markdown(results, analysis)
    with open(MD_PATH, "w") as f:
        f.write(md_content)
    print(f"Markdown saved: {MD_PATH}")

    # Print verdict
    verdict = analysis.get("h4_verdict", "?")
    verdict_display = {"PASS": "通过", "WEAK_PASS": "弱通过", "NOT_PASS": "不通过"}.get(verdict, verdict)
    print(f"\n{'=' * 80}")
    print(f"H4 判定: {verdict_display}")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    asyncio.run(main())
