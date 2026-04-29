#!/usr/bin/env python3
"""
Pinbar 0.382 Limit-Entry Proxy — 验证 H2

假设 H2：
  当前"下一根 K 市价入场"可能存在追价问题；
  改为信号 K 区间 0.382 回撤挂单，等待后续 N 根 K 成交，否则放弃，
  可能改善入场价格、止损距离和收益质量。

方法：
  1. 跑当前 LONG-only 基线回测，拿到 positions（含 entry_time, entry_price, exit_price, exit_reason）
  2. 加载 1h K 线数据，找到每笔交易对应的信号 K
  3. 计算 0.382 limit entry 价格
  4. 从信号 K 下一根开始，向后看 N 根 1h K，判断是否成交
  5. 成交后重新估算 TP/SL 结果
  6. 对比 E0（基线）vs E1（wait=5）vs E2（wait=8）

反前瞻保证：
  - limit_entry 只使用信号 K 的 high/low（已知信息）
  - 成交判断只使用信号 K 后续 K 线（未来信息，但这是合法的等待窗口）
  - 未成交的信号不事后用市场价补入（missed = missed）

严格边界：不改引擎、不改 runtime、不改 live 代码路径。
本脚本输出为 proxy 估算，不是正式引擎级回测。
"""

import asyncio
import json
import statistics
import sys
from dataclasses import dataclass
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
FIB_LEVEL = Decimal("0.382")
HOUR_MS = 3600 * 1000

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
    id="limit_entry_proxy",
    name="Limit entry proxy",
    tp_levels=2,
    tp_ratios=[Decimal("0.5"), Decimal("0.5")],
    tp_targets=[Decimal("1.0"), Decimal("3.5")],
    initial_stop_loss_rr=Decimal("-1.0"),
    trailing_stop_enabled=False,
    oco_enabled=True,
)

REPORT_DIR = PROJECT_ROOT / "reports" / "research"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
JSON_PATH = REPORT_DIR / "pinbar_limit_entry_proxy_2026-04-28.json"
MD_PATH = PROJECT_ROOT / "docs" / "planning" / "2026-04-28-pinbar-limit-entry-proxy.md"


# ─── 工具 ────────────────────────────────────────────────────────────────

def year_range_ms(year: int) -> tuple[int, int]:
    start = int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    end = int(datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)
    return start, end


# ─── 基线回测 ────────────────────────────────────────────────────────────

async def run_baseline(year: int) -> tuple[list[PositionSummary], list]:
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
        return report.positions, report.close_events
    return [], []


async def load_1h_klines(year: int) -> list[KlineData]:
    repo = HistoricalDataRepository()
    # Load from previous year Dec for warmup, through current year
    start_time, _ = year_range_ms(year - 1)
    _, end_time = year_range_ms(year)
    return await repo.get_klines(SYMBOL, "1h", start_time, end_time, limit=20000)


# ─── 信号 K 定位 ────────────────────────────────────────────────────────

def find_signal_kline(entry_time: int, klines: list[KlineData]) -> Optional[KlineData]:
    """
    找到 entry 对应的信号 K。

    当前引擎逻辑：信号在 bar N 产生，entry 在 bar N+1 开盘成交。
    所以 entry_time ≈ bar N+1 的 open timestamp。
    信号 K = bar N = entry_time 之前最近的 1h K 线。
    """
    # Find the kline whose timestamp is just before entry_time
    # The signal K is the bar BEFORE the entry bar
    best = None
    for kl in klines:
        if kl.timestamp < entry_time:
            best = kl
        else:
            break
    return best


# ─── 0.382 Limit Entry 逻辑 ────────────────────────────────────────────

@dataclass
class LimitEntryResult:
    filled: bool
    fill_price: float  # actual fill price (limit_entry if filled)
    fill_bar_idx: int   # which bar after signal K (1-based)
    limit_entry: float  # the 0.382 price
    signal_high: float
    signal_low: float
    stop_loss: float    # signal_low for LONG
    entry_improvement: float  # (baseline_entry - limit_entry) / baseline_entry
    stop_distance_change: float  # (limit_sl_dist - baseline_sl_dist) / baseline_sl_dist


def evaluate_limit_entry(
    signal_kline: KlineData,
    baseline_entry_price: float,
    subsequent_klines: list[KlineData],
    wait_candles: int,
) -> LimitEntryResult:
    """
    评估 0.382 limit entry 是否成交。

    对 LONG bullish pinbar：
      - signal_high = 信号 K high
      - signal_low = 信号 K low
      - limit_entry = signal_low + (signal_high - signal_low) * 0.382
      - stop_loss = signal_low
      - 从信号 K 下一根开始，向后看 N 根 1h K
      - 若任一 K low <= limit_entry，则视为成交
      - 若等待窗口内未触及，则视为 missed signal
    """
    signal_high = float(signal_kline.high)
    signal_low = float(signal_kline.low)
    limit_entry = signal_low + (signal_high - signal_low) * float(FIB_LEVEL)
    stop_loss = signal_low

    # Baseline metrics
    baseline_sl = float(signal_kline.low)  # same as stop_loss
    baseline_sl_dist = abs(baseline_entry_price - baseline_sl)
    limit_sl_dist = abs(limit_entry - stop_loss)

    entry_improvement = (baseline_entry_price - limit_entry) / baseline_entry_price
    stop_distance_change = (limit_sl_dist - baseline_sl_dist) / baseline_sl_dist if baseline_sl_dist > 0 else 0.0

    # Check subsequent klines for fill
    filled = False
    fill_bar_idx = 0
    fill_price = 0.0

    for i, kl in enumerate(subsequent_klines[:wait_candles]):
        if float(kl.low) <= limit_entry:
            filled = True
            fill_bar_idx = i + 1  # 1-based
            fill_price = limit_entry  # filled at limit price
            break

    return LimitEntryResult(
        filled=filled,
        fill_price=fill_price,
        fill_bar_idx=fill_bar_idx,
        limit_entry=limit_entry,
        signal_high=signal_high,
        signal_low=signal_low,
        stop_loss=stop_loss,
        entry_improvement=entry_improvement,
        stop_distance_change=stop_distance_change,
    )


# ─── TP/SL Proxy 估算 ───────────────────────────────────────────────────

@dataclass
class ProxyPosition:
    entry_price: float
    stop_loss: float
    tp1_price: float
    tp2_price: float
    realized_pnl: float
    exit_reason: str  # TP1, TP2, SL, or TIME_EXIT
    is_win: bool


def estimate_position_outcome(
    entry_price: float,
    stop_loss: float,
    tp_targets: list[float],
    tp_ratios: list[float],
    subsequent_klines: list[KlineData],
    max_hold_bars: int = 168,  # 7 days = 168 hours
) -> ProxyPosition:
    """
    Proxy 估算：给定入场价和止损，用后续 K 线估算 TP/SL 结果。

    简化假设：
    - TP1/TP2 用 LIMIT 单逻辑（kline.high >= tp_price 触发）
    - SL 用 STOP_MARKET 逻辑（kline.low <= sl_price 触发）
    - 同 bar 冲突：pessimistic（SL 优先）
    - 不考虑部分止盈后的仓位变化（简化为全仓 TP1/TP2/SL 三选一）
    - TP1 达成后，剩余仓位继续看 TP2 或 SL

    返回：最终结果（以 TP2/SL 为主，因为 TP1 只是部分止盈）
    """
    sl_dist = abs(entry_price - stop_loss)
    if sl_dist <= 0:
        return ProxyPosition(
            entry_price=entry_price, stop_loss=stop_loss,
            tp1_price=entry_price, tp2_price=entry_price,
            realized_pnl=0.0, exit_reason="ZERO_SL", is_win=False,
        )

    tp1_price = entry_price + tp_targets[0] * sl_dist
    tp2_price = entry_price + tp_targets[1] * sl_dist

    tp1_hit = False
    tp2_hit = False
    sl_hit = False
    exit_reason = "TIME_EXIT"
    realized_pnl = 0.0

    for kl in subsequent_klines[:max_hold_bars]:
        k_high = float(kl.high)
        k_low = float(kl.low)

        # Check same-bar conflicts (pessimistic: SL wins)
        sl_triggers = k_low <= stop_loss
        tp1_triggers = k_high >= tp1_price
        tp2_triggers = k_high >= tp2_price

        if sl_triggers:
            # SL triggers - pessimistic: SL wins even if TP also triggers
            sl_hit = True
            exit_reason = "SL"
            # PnL: full position at SL
            realized_pnl = (stop_loss - entry_price)  # per unit, negative
            break

        if not tp1_hit and tp1_triggers:
            tp1_hit = True
            # Partial close at TP1: realize tp_ratios[0] of position
            realized_pnl += tp_ratios[0] * (tp1_price - entry_price)
            # Continue holding remaining for TP2 or SL
            # After TP1, SL stays at original stop_loss (BE=False)
            continue

        if tp1_hit and tp2_triggers:
            tp2_hit = True
            exit_reason = "TP2"
            # Close remaining at TP2
            realized_pnl += tp_ratios[1] * (tp2_price - entry_price)
            break

    if not sl_hit and not tp2_hit:
        if tp1_hit:
            # TP1 hit but TP2 not reached within window, SL not hit
            # Assume remaining position closed at last bar close (time exit)
            exit_reason = "TP1+TIME"
            last_close = float(subsequent_klines[min(max_hold_bars - 1, len(subsequent_klines) - 1)].close)
            remaining_pnl = tp_ratios[1] * (last_close - entry_price)
            realized_pnl += remaining_pnl
        else:
            exit_reason = "TIME_EXIT"
            last_close = float(subsequent_klines[min(max_hold_bars - 1, len(subsequent_klines) - 1)].close)
            realized_pnl = last_close - entry_price

    is_win = realized_pnl > 0

    return ProxyPosition(
        entry_price=entry_price,
        stop_loss=stop_loss,
        tp1_price=tp1_price,
        tp2_price=tp2_price,
        realized_pnl=realized_pnl,
        exit_reason=exit_reason,
        is_win=is_win,
    )


# ─── 实验执行 ────────────────────────────────────────────────────────────

async def run_experiment(year: int, wait_candles: int) -> dict:
    """
    对一年数据运行 0.382 limit entry proxy 实验。
    """
    print(f"  {year}: Running baseline backtest...", flush=True)
    positions, close_events = await run_baseline(year)
    print(f"  {year}: {len(positions)} baseline positions", flush=True)

    print(f"  {year}: Loading 1h klines...", flush=True)
    klines = await load_1h_klines(year)
    print(f"  {year}: {len(klines)} 1h klines loaded", flush=True)

    # Build kline index for fast lookup
    kline_by_ts = {kl.timestamp: kl for kl in klines}
    sorted_ts = sorted(kline_by_ts.keys())

    # Process each position
    filled_positions = []
    missed_positions = []
    baseline_positions = []
    entry_improvements = []
    stop_distance_changes = []
    fill_bar_indices = []

    for pos in positions:
        # Find signal kline
        signal_kl = find_signal_kline(pos.entry_time, klines)
        if signal_kl is None:
            continue

        # Find subsequent klines after signal kline
        signal_idx = None
        for i, ts in enumerate(sorted_ts):
            if ts == signal_kl.timestamp:
                signal_idx = i
                break
        if signal_idx is None:
            continue

        subsequent = klines[signal_idx + 1:]  # klines after signal K

        # Evaluate limit entry
        baseline_entry = float(pos.entry_price)
        result = evaluate_limit_entry(signal_kl, baseline_entry, subsequent, wait_candles)

        # Baseline outcome (from actual backtest)
        baseline_pnl = float(pos.realized_pnl)
        baseline_positions.append({
            "pnl": baseline_pnl,
            "is_win": baseline_pnl > 0,
            "entry_price": baseline_entry,
            "exit_reason": pos.exit_reason or "unknown",
        })

        if result.filled:
            entry_improvements.append(result.entry_improvement)
            stop_distance_changes.append(result.stop_distance_change)
            fill_bar_indices.append(result.fill_bar_idx)

            # Estimate outcome with limit entry price
            tp_targets = [1.0, 3.5]
            tp_ratios = [0.5, 0.5]
            proxy = estimate_position_outcome(
                result.fill_price, result.stop_loss,
                tp_targets, tp_ratios, subsequent,
            )
            filled_positions.append({
                "pnl": proxy.realized_pnl,
                "is_win": proxy.is_win,
                "entry_price": result.fill_price,
                "exit_reason": proxy.exit_reason,
                "fill_bar": result.fill_bar_idx,
                "entry_improvement": result.entry_improvement,
                "stop_distance_change": result.stop_distance_change,
            })
        else:
            missed_positions.append({
                "baseline_pnl": baseline_pnl,
                "baseline_is_win": baseline_pnl > 0,
            })

    # Compute metrics
    total_baseline = len(baseline_positions)
    total_filled = len(filled_positions)
    total_missed = len(missed_positions)
    fill_rate = total_filled / total_baseline if total_baseline > 0 else 0.0

    # Missed winners/losers
    missed_winners = sum(1 for m in missed_positions if m["baseline_is_win"])
    missed_losers = sum(1 for m in missed_positions if not m["baseline_is_win"])

    # Filled PnL
    filled_pnls = [p["pnl"] for p in filled_positions]
    total_pnl = sum(filled_pnls)
    wins = [p for p in filled_pnls if p > 0]
    losses = [p for p in filled_pnls if p <= 0]
    win_rate = len(wins) / len(filled_pnls) if filled_pnls else 0.0

    # Sharpe
    if len(filled_pnls) >= 2:
        sharpe = statistics.mean(filled_pnls) / statistics.stdev(filled_pnls) if statistics.stdev(filled_pnls) > 0 else 0.0
    else:
        sharpe = 0.0

    # MaxDD
    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in filled_pnls:
        cumulative += p
        if cumulative > peak:
            peak = cumulative
        dd = peak - cumulative
        if dd > max_dd:
            max_dd = dd

    # Exit reason breakdown
    tp1_count = sum(1 for p in filled_positions if p["exit_reason"].startswith("TP1"))
    tp2_count = sum(1 for p in filled_positions if p["exit_reason"] == "TP2")
    sl_count = sum(1 for p in filled_positions if p["exit_reason"] == "SL")
    other_count = total_filled - tp1_count - tp2_count - sl_count
    total_exits = total_filled if total_filled > 0 else 1

    # Baseline metrics for comparison
    baseline_pnls = [p["pnl"] for p in baseline_positions]
    baseline_total_pnl = sum(baseline_pnls)
    baseline_wins = [p for p in baseline_pnls if p > 0]
    baseline_win_rate = len(baseline_wins) / len(baseline_pnls) if baseline_pnls else 0.0

    return {
        "year": year,
        "wait_candles": wait_candles,
        "fill_rate": round(fill_rate, 4),
        "total_baseline": total_baseline,
        "total_filled": total_filled,
        "total_missed": total_missed,
        "missed_winners": missed_winners,
        "missed_losers": missed_losers,
        "pnl": round(total_pnl, 2),
        "trades": total_filled,
        "win_rate": round(win_rate, 4),
        "sharpe": round(sharpe, 4),
        "max_dd": round(max_dd, 2),
        "tp1_pct": round(tp1_count / total_exits * 100, 1),
        "tp2_pct": round(tp2_count / total_exits * 100, 1),
        "sl_pct": round(sl_count / total_exits * 100, 1),
        "avg_entry_improvement": round(statistics.mean(entry_improvements) * 100, 4) if entry_improvements else 0.0,
        "avg_stop_distance_change": round(statistics.mean(stop_distance_changes) * 100, 4) if stop_distance_changes else 0.0,
        "avg_fill_bar": round(statistics.mean(fill_bar_indices), 1) if fill_bar_indices else 0.0,
        "median_fill_bar": round(statistics.median(fill_bar_indices), 1) if fill_bar_indices else 0.0,
        "baseline_pnl": round(baseline_total_pnl, 2),
        "baseline_trades": total_baseline,
        "baseline_win_rate": round(baseline_win_rate, 4),
    }


# ─── 主入口 ──────────────────────────────────────────────────────────────

async def main():
    print("=" * 60)
    print("  Pinbar 0.382 Limit-Entry Proxy")
    print("  H2: 0.382 limit entry 是否改善收益质量？")
    print("  - E0: market entry baseline")
    print("  - E1: 0.382 limit entry, wait 5 candles")
    print("  - E2: 0.382 limit entry, wait 8 candles")
    print("=" * 60, flush=True)

    results = {"E0": {}, "E1": {}, "E2": {}}

    for year in YEARS:
        print(f"\n>>> Year {year}", flush=True)

        # E0: Baseline (market entry)
        # Reuse the baseline data from E1 run (same backtest)
        e1_result = await run_experiment(year, wait_candles=5)
        e2_result = await run_experiment(year, wait_candles=8)

        # E0 from baseline data in e1_result
        e0 = {
            "year": year,
            "pnl": e1_result["baseline_pnl"],
            "trades": e1_result["baseline_trades"],
            "win_rate": e1_result["baseline_win_rate"],
        }

        results["E0"][year] = e0
        results["E1"][year] = e1_result
        results["E2"][year] = e2_result

        # Print summary
        print(f"\n  {year} Summary:", flush=True)
        print(f"    E0: PnL={e0['pnl']:+.2f}, T={e0['trades']}, WR={e0['win_rate']:.1%}", flush=True)
        print(f"    E1: PnL={e1_result['pnl']:+.2f}, T={e1_result['trades']}, WR={e1_result['win_rate']:.1%}, Fill={e1_result['fill_rate']:.1%}, AvgImprove={e1_result['avg_entry_improvement']:.3f}%", flush=True)
        print(f"    E2: PnL={e2_result['pnl']:+.2f}, T={e2_result['trades']}, WR={e2_result['win_rate']:.1%}, Fill={e2_result['fill_rate']:.1%}, AvgImprove={e2_result['avg_entry_improvement']:.3f}%", flush=True)

    # Generate reports
    json_report = generate_json_report(results)
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(json_report, f, indent=2, ensure_ascii=False)
    print(f"\nJSON report saved: {JSON_PATH}", flush=True)

    md_report = generate_markdown_report(results)
    with open(MD_PATH, "w", encoding="utf-8") as f:
        f.write(md_report)
    print(f"Markdown report saved: {MD_PATH}", flush=True)


# ─── JSON 报告 ────────────────────────────────────────────────────────────

def generate_json_report(results: dict) -> dict:
    return {
        "title": "Pinbar 0.382 Limit-Entry Proxy",
        "date": "2026-04-28",
        "hypothesis": "H2: 0.382 limit entry may improve entry price, stop distance, and return quality vs market entry",
        "method": "proxy (not engine-level backtest)",
        "risk_profile": "research baseline (exposure=2.0, daily_max_trades=50)",
        "results": results,
    }


# ─── Markdown 报告 ────────────────────────────────────────────────────────

def generate_markdown_report(results: dict) -> str:
    lines = []
    lines.append("# Pinbar 0.382 Limit-Entry Proxy — H2 验证报告")
    lines.append("")
    lines.append("> **日期**: 2026-04-28")
    lines.append("> **假设 H2**: 当前[下一根 K 市价入场]可能存在追价问题；改为信号 K 区间 0.382 回撤挂单可能改善入场价格、止损距离和收益质量")
    lines.append("> **方法**: research-only proxy 脚本（不改引擎），用基线回测结果 + K 线数据重新估算")
    lines.append("> **基线**: ETH 1h LONG-only, EMA50, BNB9 成本, Research 口径")
    lines.append("> **风险**: 本报告为 proxy 估算，不是正式引擎级回测")
    lines.append("")

    # ── 1. 支持度审计 ──
    lines.append("## 1. 支持度审计")
    lines.append("")
    lines.append("### 1a. 当前 entry 如何产生？")
    lines.append("")
    lines.append("信号 K 上检测到 Pinbar → `RiskCalculator.calculate_stop_loss()` 用信号 K 的 low 作为 SL → `OrderManager.create_order_chain()` 创建 MARKET 入场单 → 放入 `pending_entry_orders` → 下一根 K 开盘时撮合，成交价 = `next_kline.open ± slippage`")
    lines.append("")
    lines.append("### 1b. 当前是否支持 pending limit entry？")
    lines.append("")
    lines.append("**不支持**。`OrderType.MARKET + OrderRole.ENTRY` 是唯一路径。`pending_entry_orders` 只是 T+1 延迟，不是 limit order book。")
    lines.append("")
    lines.append("### 1c. 当前 stop loss 基于什么？")
    lines.append("")
    lines.append("两阶段：")
    lines.append("- 信号阶段：`RiskCalculator.calculate_stop_loss()` → 信号 K 的 low（LONG）")
    lines.append("- 成交后：`OrderManager._calculate_stop_loss_price()` → 用实际成交价和 RR 倍数（默认 -1.0 = 1%）重新计算")
    lines.append("")
    lines.append("### 1d. 不改核心引擎，能否用 proxy 脚本模拟？")
    lines.append("")
    lines.append("**可以**。跑基线回测拿到 positions → 每笔交易有 entry_time → 找到信号 K → 用后续 K 线判断 0.382 回撤是否成交 → 重新估算 TP/SL。")
    lines.append("")

    # ── 2. 实验设计 ──
    lines.append("## 2. 实验设计")
    lines.append("")
    lines.append("| 参数 | 值 |")
    lines.append("|------|----|")
    lines.append("| symbol | ETH/USDT:USDT |")
    lines.append("| timeframe | 1h |")
    lines.append("| direction | LONG-only |")
    lines.append("| ema_period | 50 |")
    lines.append("| min_distance_pct | 0.005 |")
    lines.append("| ATR | disabled |")
    lines.append("| tp_targets | [1.0, 3.5] |")
    lines.append("| tp_ratios | [0.5, 0.5] |")
    lines.append("| breakeven | False |")
    lines.append("| fib_level | 0.382 |")
    lines.append("| E0 | market entry baseline |")
    lines.append("| E1 | 0.382 limit entry, wait 5 candles |")
    lines.append("| E2 | 0.382 limit entry, wait 8 candles |")
    lines.append("| 风险口径 | Research (exposure=2.0) |")
    lines.append("")
    lines.append("### 0.382 Limit Entry 规则")
    lines.append("")
    lines.append("对 LONG bullish pinbar：")
    lines.append("- signal_high = 信号 K high")
    lines.append("- signal_low = 信号 K low")
    lines.append("- limit_entry = signal_low + (signal_high - signal_low) * 0.382")
    lines.append("- stop_loss = signal_low")
    lines.append("- 从信号 K 下一根开始，向后看 N 根 1h K")
    lines.append("- 若任一 K low <= limit_entry，则视为成交")
    lines.append("- 若等待窗口内未触及，则视为 missed signal（不补入）")
    lines.append("")

    # ── 3. 结果 ──
    lines.append("## 3. 结果")
    lines.append("")

    for year in YEARS:
        e0 = results["E0"].get(year, {})
        e1 = results["E1"].get(year, {})
        e2 = results["E2"].get(year, {})

        lines.append(f"### {year}")
        lines.append("")
        lines.append("| 指标 | E0 基线 | E1 wait=5 | E2 wait=8 |")
        lines.append("|------|---------|-----------|-----------|")
        lines.append(f"| PnL | {e0.get('pnl', 0):+.2f} | {e1.get('pnl', 0):+.2f} | {e2.get('pnl', 0):+.2f} |")
        lines.append(f"| Trades | {e0.get('trades', 0)} | {e1.get('trades', 0)} | {e2.get('trades', 0)} |")
        lines.append(f"| Win Rate | {e0.get('win_rate', 0):.1%} | {e1.get('win_rate', 0):.1%} | {e2.get('win_rate', 0):.1%} |")
        lines.append(f"| Sharpe | - | {e1.get('sharpe', 0):.2f} | {e2.get('sharpe', 0):.2f} |")
        lines.append(f"| MaxDD | - | {e1.get('max_dd', 0):.2f} | {e2.get('max_dd', 0):.2f} |")
        lines.append(f"| Fill Rate | - | {e1.get('fill_rate', 0):.1%} | {e2.get('fill_rate', 0):.1%} |")
        lines.append(f"| Missed Trades | - | {e1.get('total_missed', 0)} | {e2.get('total_missed', 0)} |")
        lines.append(f"| Missed Winners | - | {e1.get('missed_winners', 0)} | {e2.get('missed_winners', 0)} |")
        lines.append(f"| Missed Losers | - | {e1.get('missed_losers', 0)} | {e2.get('missed_losers', 0)} |")
        lines.append(f"| Avg Entry Improve | - | {e1.get('avg_entry_improvement', 0):.3f}% | {e2.get('avg_entry_improvement', 0):.3f}% |")
        lines.append(f"| Avg Stop Dist Change | - | {e1.get('avg_stop_distance_change', 0):.3f}% | {e2.get('avg_stop_distance_change', 0):.3f}% |")
        lines.append(f"| Avg Fill Bar | - | {e1.get('avg_fill_bar', 0):.1f} | {e2.get('avg_fill_bar', 0):.1f} |")
        lines.append(f"| TP1% | - | {e1.get('tp1_pct', 0):.1f}% | {e2.get('tp1_pct', 0):.1f}% |")
        lines.append(f"| TP2% | - | {e1.get('tp2_pct', 0):.1f}% | {e2.get('tp2_pct', 0):.1f}% |")
        lines.append(f"| SL% | - | {e1.get('sl_pct', 0):.1f}% | {e2.get('sl_pct', 0):.1f}% |")
        lines.append("")

    # ── 4. 验证分析 ──
    lines.append("## 4. 验证分析")
    lines.append("")

    # Aggregate across years
    total_e0_pnl = sum(results["E0"].get(y, {}).get("pnl", 0) for y in YEARS)
    total_e1_pnl = sum(results["E1"].get(y, {}).get("pnl", 0) for y in YEARS)
    total_e2_pnl = sum(results["E2"].get(y, {}).get("pnl", 0) for y in YEARS)
    total_e0_trades = sum(results["E0"].get(y, {}).get("trades", 0) for y in YEARS)
    total_e1_trades = sum(results["E1"].get(y, {}).get("trades", 0) for y in YEARS)
    total_e2_trades = sum(results["E2"].get(y, {}).get("trades", 0) for y in YEARS)

    e1_fill_rates = [results["E1"].get(y, {}).get("fill_rate", 0) for y in YEARS]
    e2_fill_rates = [results["E2"].get(y, {}).get("fill_rate", 0) for y in YEARS]
    avg_e1_fill = sum(e1_fill_rates) / len(e1_fill_rates) if e1_fill_rates else 0
    avg_e2_fill = sum(e2_fill_rates) / len(e2_fill_rates) if e2_fill_rates else 0

    e1_improvements = [results["E1"].get(y, {}).get("avg_entry_improvement", 0) for y in YEARS]
    e2_improvements = [results["E2"].get(y, {}).get("avg_entry_improvement", 0) for y in YEARS]
    avg_e1_imp = sum(e1_improvements) / len(e1_improvements) if e1_improvements else 0
    avg_e2_imp = sum(e2_improvements) / len(e2_improvements) if e2_improvements else 0

    lines.append("### 4a. 3 年汇总")
    lines.append("")
    lines.append(f"| 指标 | E0 基线 | E1 wait=5 | E2 wait=8 |")
    lines.append(f"|------|---------|-----------|-----------|")
    lines.append(f"| 总 PnL | {total_e0_pnl:+.2f} | {total_e1_pnl:+.2f} | {total_e2_pnl:+.2f} |")
    lines.append(f"| 总 Trades | {total_e0_trades} | {total_e1_trades} | {total_e2_trades} |")
    lines.append(f"| 平均 Fill Rate | 100% | {avg_e1_fill:.1%} | {avg_e2_fill:.1%} |")
    lines.append(f"| 平均 Entry Improve | 0% | {avg_e1_imp:.3f}% | {avg_e2_imp:.3f}% |")
    lines.append("")

    lines.append("### 4b. 0.382 limit-entry 是否提升收益质量？")
    lines.append("")
    if total_e1_pnl > total_e0_pnl or total_e2_pnl > total_e0_pnl:
        best = "E1" if total_e1_pnl > total_e2_pnl else "E2"
        best_pnl = max(total_e1_pnl, total_e2_pnl)
        improvement = (best_pnl - total_e0_pnl) / abs(total_e0_pnl) * 100 if total_e0_pnl != 0 else 0
        lines.append(f"{best} 总 PnL ({best_pnl:+.2f}) 优于 E0 ({total_e0_pnl:+.2f})，改善 {improvement:+.1f}%。")
    else:
        lines.append(f"E1 ({total_e1_pnl:+.2f}) 和 E2 ({total_e2_pnl:+.2f}) 均劣于 E0 ({total_e0_pnl:+.2f})。")
    lines.append("")

    lines.append("### 4c. 是否只是减少交易？")
    lines.append("")
    if total_e1_trades < total_e0_trades or total_e2_trades < total_e0_trades:
        lines.append(f"E1 trades={total_e1_trades} vs E0={total_e0_trades}（减少 {total_e0_trades - total_e1_trades}）")
        lines.append(f"E2 trades={total_e2_trades} vs E0={total_e0_trades}（减少 {total_e0_trades - total_e2_trades}）")
        lines.append("Limit entry 确实减少了交易次数（未成交的信号被放弃）。")
    else:
        lines.append("Limit entry 未显著减少交易次数。")
    lines.append("")

    lines.append("### 4d. Missed signals 分析")
    lines.append("")
    for year in YEARS:
        e1 = results["E1"].get(year, {})
        e2 = results["E2"].get(year, {})
        mw1 = e1.get("missed_winners", 0)
        ml1 = e1.get("missed_losers", 0)
        mw2 = e2.get("missed_winners", 0)
        ml2 = e2.get("missed_losers", 0)
        lines.append(f"**{year}**: E1 missed {mw1} winners / {ml1} losers; E2 missed {mw2} winners / {ml2} losers")
    lines.append("")

    # ── 5. 最终结论 ──
    lines.append("## 5. 最终结论")
    lines.append("")

    # Decision logic
    pnl_improves = total_e1_pnl > total_e0_pnl or total_e2_pnl > total_e0_pnl
    quality_improves = False
    for y in YEARS:
        e1 = results["E1"].get(y, {})
        e0_wr = results["E0"].get(y, {}).get("win_rate", 0)
        e1_wr = e1.get("win_rate", 0)
        if e1_wr > e0_wr and e1.get("fill_rate", 0) > 0.5:
            quality_improves = True

    if pnl_improves and quality_improves:
        h2_verdict = "弱通过"
        engine_design = "值得进入引擎级 pending limit entry 设计"
    elif pnl_improves and not quality_improves:
        h2_verdict = "弱通过"
        engine_design = "有条件进入引擎级设计（PnL 改善但收益质量未提升）"
    elif quality_improves and not pnl_improves:
        h2_verdict = "弱通过"
        engine_design = "有条件进入引擎级设计（收益质量提升但 PnL 未改善）"
    else:
        h2_verdict = "不通过"
        engine_design = "不建议进入引擎级设计"

    lines.append(f"**H2 判定**: {h2_verdict}")
    lines.append("")
    lines.append(f"- **0.382 limit-entry 是否提升收益质量**: {'是' if quality_improves else '否'}")
    lines.append(f"- **是否只是减少交易**: {'是' if (total_e1_trades < total_e0_trades * 0.9) else '否'}")
    lines.append(f"- **是否值得进入引擎级 pending limit entry 设计**: {engine_design}")
    lines.append(f"- **是否禁止直接进入 runtime**: 禁止直接进入 runtime（proxy 结果需引擎级验证）")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("> **重要**: 本报告为 proxy 估算，不是正式引擎级回测。")
    lines.append("> Proxy 简化了部分止盈后的仓位管理和同 bar 冲突处理。")
    lines.append("> 若 H2 弱通过，需在引擎级实现 pending limit entry 后重新验证。")
    lines.append("> MFE/MAE/+1R/+2R/+3.5R 可达率、first-touch 等指标标记为 TODO。")

    return "\n".join(lines)


if __name__ == "__main__":
    asyncio.run(main())
