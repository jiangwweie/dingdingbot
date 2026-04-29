#!/usr/bin/env python3
"""
ETH/USDT 1h 样本外失败归因分析

目标：诊断 2025 OOS + 2026 Q1 Forward 全面亏损的根因
方法：固定最优参数 → 多维度拆解 → 过滤器敏感性对照

分析维度：
A. 多空方向拆解 (LONG vs SHORT)
B. 出场结构拆解 (TP1/TP2/SL hit rate)
C. 信号质量拆解 (SIGNAL_FIRED vs FILTERED)
D. 时间段/市场状态拆解 (月度 PnL)
E. 过滤器敏感性诊断 (去掉 EMA/MTF/放宽 ATR)
"""
import asyncio
import sys
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.domain.models import (
    BacktestRequest,
    BacktestRuntimeOverrides,
    Direction,
)
from src.infrastructure.historical_data_repository import HistoricalDataRepository
from src.application.backtester import Backtester


# ============================================================
# 配置
# ============================================================

SYMBOL = "ETH/USDT:USDT"
TIMEFRAME = "1h"
DB_PATH = "data/v3_dev.db"

# 固定基线参数（四年训练集最优）
BASELINE_PARAMS = {
    "max_atr_ratio": Decimal("0.0059"),
    "min_distance_pct": Decimal("0.0080"),
    "ema_period": 111,
}

# 固定订单策略
TP_RATIOS = [Decimal("0.6"), Decimal("0.4")]
TP_TARGETS = [Decimal("1.0"), Decimal("2.5")]
BREAKEVEN_ENABLED = False

# Stress 成本口径
SLIPPAGE_RATE = Decimal("0.001")
TP_SLIPPAGE_RATE = Decimal("0.0005")
FEE_RATE = Decimal("0.0004")
INITIAL_BALANCE = Decimal("10000")

# 分析区间
OOS_START = 1735689600000   # 2025-01-01
OOS_END = 1767225599000     # 2025-12-31
FWD_START = 1767225600000   # 2026-01-01
FWD_END = 1775087999000     # 2026-03-31


def fmt_ts(ts_ms):
    return datetime.utcfromtimestamp(ts_ms / 1000).strftime("%Y-%m-%d %H:%M UTC")


def fmt_month(ts_ms):
    return datetime.utcfromtimestamp(ts_ms / 1000).strftime("%Y-%m")


def build_overrides(params):
    return BacktestRuntimeOverrides(
        tp_ratios=TP_RATIOS,
        tp_targets=TP_TARGETS,
        breakeven_enabled=BREAKEVEN_ENABLED,
        max_atr_ratio=params.get("max_atr_ratio"),
        min_distance_pct=params.get("min_distance_pct"),
        ema_period=params.get("ema_period"),
    )


async def run_backtest(backtester, start, end, params, mode="v3_pms"):
    request = BacktestRequest(
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        start_time=start,
        end_time=end,
        mode=mode,
        initial_balance=INITIAL_BALANCE,
        slippage_rate=SLIPPAGE_RATE,
        tp_slippage_rate=TP_SLIPPAGE_RATE,
        fee_rate=FEE_RATE,
    )
    overrides = build_overrides(params)
    result = await backtester.run_backtest(request, runtime_overrides=overrides)
    return result


# ============================================================
# 分析函数
# ============================================================

def analyze_direction_split(report):
    """A. 多空方向拆解"""
    stats = {
        Direction.LONG: {"trades": 0, "wins": 0, "pnl": Decimal("0"),
                         "win_pnl": Decimal("0"), "loss_pnl": Decimal("0")},
        Direction.SHORT: {"trades": 0, "wins": 0, "pnl": Decimal("0"),
                          "win_pnl": Decimal("0"), "loss_pnl": Decimal("0")},
    }

    for pos in report.positions:
        if pos.exit_time is None:
            continue
        d = pos.direction
        s = stats[d]
        s["trades"] += 1
        s["pnl"] += pos.realized_pnl
        if pos.realized_pnl > 0:
            s["wins"] += 1
            s["win_pnl"] += pos.realized_pnl
        elif pos.realized_pnl < 0:
            s["loss_pnl"] += pos.realized_pnl

    result = {}
    for direction, s in stats.items():
        wins_count = s["trades"] - s["wins"]
        avg_win = s["win_pnl"] / s["wins"] if s["wins"] > 0 else Decimal("0")
        avg_loss = s["loss_pnl"] / wins_count if wins_count > 0 else Decimal("0")
        profit_factor = abs(s["win_pnl"] / s["loss_pnl"]) if s["loss_pnl"] != 0 else None
        result[direction] = {
            "trades": s["trades"],
            "pnl": float(s["pnl"]),
            "win_rate": s["wins"] / s["trades"] if s["trades"] > 0 else 0,
            "avg_win": float(avg_win),
            "avg_loss": float(avg_loss),
            "profit_factor": float(profit_factor) if profit_factor else None,
        }
    return result


def analyze_exit_structure(report):
    """B. 出场结构拆解"""
    event_counts = defaultdict(int)
    event_pnl = defaultdict(lambda: Decimal("0"))

    for ev in report.close_events:
        if ev.event_category != "exit":
            continue
        event_counts[ev.event_type] += 1
        if ev.close_pnl is not None:
            event_pnl[ev.event_type] += ev.close_pnl

    total_positions = len([p for p in report.positions if p.exit_time is not None])
    if total_positions == 0:
        return {}

    result = {}
    for etype in ["TP1", "TP2", "SL", "TRAILING_EXIT"]:
        count = event_counts.get(etype, 0)
        # Note: close_events contain per-fill events; TP1/TP2 are partial fills on the same position
        # So we count unique positions that had this event type
        result[etype] = {
            "hit_count": count,
            "total_pnl": float(event_pnl.get(etype, Decimal("0"))),
        }

    # Calculate unique position-level exit reason counts
    pos_exit_reasons = defaultdict(int)
    for pos in report.positions:
        if pos.exit_reason:
            pos_exit_reasons[pos.exit_reason] += 1
    result["position_exit_reasons"] = dict(pos_exit_reasons)

    return result


def analyze_signal_quality(report):
    """C. 信号质量拆解（从 analysis_dimensions 获取）"""
    dims = report.analysis_dimensions or {}
    agg = report.aggregate_attribution or {}
    return {
        "dimensions": dims,
        "aggregate": agg,
    }


def analyze_monthly_breakdown(report, label):
    """D. 时间段/市场状态拆解"""
    monthly = defaultdict(lambda: {"trades": 0, "pnl": Decimal("0"), "wins": 0, "max_equity": Decimal("0"), "peak_dd": Decimal("0")})

    for pos in report.positions:
        if pos.exit_time is None:
            continue
        month = fmt_month(pos.exit_time)
        m = monthly[month]
        m["trades"] += 1
        m["pnl"] += pos.realized_pnl
        if pos.realized_pnl > 0:
            m["wins"] += 1

    # Calculate running equity for monthly drawdown
    sorted_months = sorted(monthly.keys())
    running_pnl = Decimal("0")
    peak = Decimal("0")
    for month in sorted_months:
        running_pnl += monthly[month]["pnl"]
        if running_pnl > peak:
            peak = running_pnl
        dd = peak - running_pnl
        monthly[month]["cumulative_pnl"] = float(running_pnl)
        monthly[month]["drawdown_from_peak"] = float(dd)

    result = {}
    for month in sorted(monthly):
        m = monthly[month]
        wr = m["wins"] / m["trades"] if m["trades"] > 0 else 0
        result[month] = {
            "trades": m["trades"],
            "pnl": float(m["pnl"]),
            "win_rate": wr,
            "cumulative_pnl": m["cumulative_pnl"],
            "drawdown_from_peak": m["drawdown_from_peak"],
        }
    return result


# ============================================================
# 过滤器敏感性诊断
# ============================================================

FILTER_VARIANTS = {
    "baseline": {
        "desc": "Pinbar + EMA + MTF + ATR (基线)",
        "params": dict(BASELINE_PARAMS),
    },
    "no_ema": {
        "desc": "去掉 EMA (min_distance_pct 极小化)",
        "params": {**BASELINE_PARAMS, "min_distance_pct": Decimal("0.0001")},
    },
    "relaxed_atr": {
        "desc": "放宽 ATR (0.0059 → 0.015)",
        "params": {**BASELINE_PARAMS, "max_atr_ratio": Decimal("0.015")},
    },
    "wide_open": {
        "desc": "全放宽 (EMA极小 + ATR极大)",
        "params": {
            "max_atr_ratio": Decimal("0.020"),
            "min_distance_pct": Decimal("0.0001"),
            "ema_period": BASELINE_PARAMS["ema_period"],
        },
    },
    "tight_only": {
        "desc": "只保留 ATR 过滤 (EMA极小)",
        "params": {
            "max_atr_ratio": Decimal("0.003"),
            "min_distance_pct": Decimal("0.0001"),
            "ema_period": BASELINE_PARAMS["ema_period"],
        },
    },
}


# ============================================================
# 主流程
# ============================================================

async def main():
    print("=" * 70)
    print("ETH/USDT 1h 样本外失败归因分析")
    print("=" * 70)

    print(f"\n基线参数: {BASELINE_PARAMS}")
    print(f"OOS: {fmt_ts(OOS_START)} ~ {fmt_ts(OOS_END)}")
    print(f"Forward: {fmt_ts(FWD_START)} ~ {fmt_ts(FWD_END)}")

    data_repo = HistoricalDataRepository(DB_PATH)
    await data_repo.initialize()
    backtester = Backtester(exchange_gateway=None, data_repository=data_repo)

    try:
        # ============================================================
        # 任务 1: 基线回测 (OOS + Forward)
        # ============================================================
        print("\n" + "=" * 70)
        print("任务 1: 基线回测 (固定最优参数)")
        print("=" * 70)

        results = {}
        for label, start, end in [("OOS_2025", OOS_START, OOS_END), ("FWD_2026Q1", FWD_START, FWD_END)]:
            print(f"\n--- {label}: {fmt_ts(start)} ~ {fmt_ts(end)} ---")
            report = await run_backtest(backtester, start, end, BASELINE_PARAMS)
            results[label] = report

            trades = report.total_trades
            pnl = float(report.total_pnl)
            wr = float(report.win_rate)
            dd = float(report.max_drawdown)
            sharpe = float(report.sharpe_ratio) if report.sharpe_ratio else 0.0

            print(f"  trades: {trades}, pnl: {pnl:.2f}, win_rate: {wr:.1f}%, max_dd: {dd:.1f}%, sharpe: {sharpe:.4f}")

        # ============================================================
        # 任务 2: 失败归因拆解
        # ============================================================
        for label, report in results.items():
            print("\n" + "=" * 70)
            print(f"任务 2: 失败归因拆解 — {label}")
            print("=" * 70)

            # A. 多空方向拆解
            print(f"\n--- A. 多空方向拆解 ---")
            dir_split = analyze_direction_split(report)
            for direction, s in dir_split.items():
                dname = direction.value if hasattr(direction, 'value') else str(direction)
                print(f"  {dname}:")
                print(f"    trades: {s['trades']}")
                print(f"    pnl: {s['pnl']:.2f}")
                print(f"    win_rate: {s['win_rate']:.1%}")
                print(f"    avg_win: {s['avg_win']:.2f}")
                print(f"    avg_loss: {s['avg_loss']:.2f}")
                print(f"    profit_factor: {s['profit_factor']:.2f}" if s['profit_factor'] else "    profit_factor: N/A")

            # B. 出场结构拆解
            print(f"\n--- B. 出场结构拆解 ---")
            exit_struct = analyze_exit_structure(report)
            for etype, data in exit_struct.items():
                if etype == "position_exit_reasons":
                    print(f"  Position exit reasons: {data}")
                else:
                    print(f"  {etype}: hits={data['hit_count']}, pnl={data['total_pnl']:.2f}")

            # 基于 positions 计算 TP1/TP2 命中率
            pos_events = defaultdict(set)
            for ev in report.close_events:
                if ev.event_category == "exit":
                    pos_events[ev.position_id].add(ev.event_type)

            tp1_count = sum(1 for pe in pos_events.values() if "TP1" in pe)
            tp2_count = sum(1 for pe in pos_events.values() if "TP2" in pe)
            sl_only = sum(1 for pe in pos_events.values() if "SL" in pe and "TP1" not in pe)
            total_closed = len([p for p in report.positions if p.exit_time is not None])

            if total_closed > 0:
                print(f"\n  Position-level exit breakdown ({total_closed} positions):")
                print(f"    TP1 hit: {tp1_count} ({tp1_count/total_closed:.1%})")
                print(f"    TP2 hit: {tp2_count} ({tp2_count/total_closed:.1%})")
                print(f"    SL only (no TP): {sl_only} ({sl_only/total_closed:.1%})")

                # Avg win vs avg loss per position
                wins = [float(p.realized_pnl) for p in report.positions if p.exit_time and p.realized_pnl > 0]
                losses = [float(p.realized_pnl) for p in report.positions if p.exit_time and p.realized_pnl <= 0]
                if wins:
                    print(f"    avg winning trade: {sum(wins)/len(wins):.2f}")
                if losses:
                    print(f"    avg losing trade: {sum(losses)/len(losses):.2f}")
                if wins and losses:
                    print(f"    raw win/loss ratio: {abs(sum(wins)/len(wins) / (sum(losses)/len(losses))):.2f}")

            # C. 信号质量（归因维度）
            print(f"\n--- C. 信号质量归因 (analysis_dimensions) ---")
            sig_quality = analyze_signal_quality(report)
            dims = sig_quality.get("dimensions", {})
            if dims:
                for dim_name, dim_data in dims.items():
                    print(f"  {dim_name}:")
                    if isinstance(dim_data, dict):
                        for k, v in dim_data.items():
                            if isinstance(v, dict):
                                print(f"    {k}: {v}")
                            else:
                                print(f"    {k}: {v}")
                    else:
                        print(f"    {dim_data}")
            else:
                print("  (无归因数据)")

            agg = sig_quality.get("aggregate", {})
            if agg:
                print(f"\n  Aggregate attribution:")
                for k, v in agg.items():
                    print(f"    {k}: {v}")

            # D. 月度拆解
            print(f"\n--- D. 月度拆解 ---")
            monthly = analyze_monthly_breakdown(report, label)
            for month, m in monthly.items():
                print(f"  {month}: trades={m['trades']}, pnl={m['pnl']:.2f}, "
                      f"win_rate={m['win_rate']:.1%}, cum_pnl={m['cumulative_pnl']:.2f}, "
                      f"dd={m['drawdown_from_peak']:.2f}")

        # ============================================================
        # 任务 3: 过滤器敏感性诊断
        # ============================================================
        print("\n" + "=" * 70)
        print("任务 3: 过滤器敏感性诊断 (2025 OOS)")
        print("=" * 70)

        sensitivity_results = []
        for variant_name, variant in FILTER_VARIANTS.items():
            print(f"\n--- {variant_name}: {variant['desc']} ---")
            params = variant["params"]
            print(f"  params: atr={params['max_atr_ratio']}, dist={params['min_distance_pct']}, ema={params['ema_period']}")

            try:
                report = await run_backtest(backtester, OOS_START, OOS_END, params)
                trades = report.total_trades
                pnl = float(report.total_pnl)
                wr = float(report.win_rate)
                dd = float(report.max_drawdown)
                sharpe = float(report.sharpe_ratio) if report.sharpe_ratio else 0.0

                print(f"  trades: {trades}, pnl: {pnl:.2f}, win_rate: {wr:.1f}%, max_dd: {dd:.1f}%, sharpe: {sharpe:.4f}")

                sensitivity_results.append({
                    "name": variant_name,
                    "desc": variant["desc"],
                    "trades": trades,
                    "pnl": pnl,
                    "win_rate": wr,
                    "max_dd": dd,
                    "sharpe": sharpe,
                })
            except Exception as e:
                print(f"  ERROR: {e}")
                sensitivity_results.append({
                    "name": variant_name,
                    "desc": variant["desc"],
                    "error": str(e),
                })

        # ============================================================
        # 任务 4: 结论
        # ============================================================
        print("\n" + "=" * 70)
        print("任务 4: 归因结论")
        print("=" * 70)

        oos_report = results.get("OOS_2025")
        if oos_report:
            dir_split = analyze_direction_split(oos_report)
            long_s = dir_split.get(Direction.LONG, {})
            short_s = dir_split.get(Direction.SHORT, {})

            print("\n1. 多空方向判断:")
            print(f"   LONG: trades={long_s.get('trades',0)}, pnl={long_s.get('pnl',0):.2f}, "
                  f"wr={long_s.get('win_rate',0):.1%}, pf={long_s.get('profit_factor','N/A')}")
            print(f"   SHORT: trades={short_s.get('trades',0)}, pnl={short_s.get('pnl',0):.2f}, "
                  f"wr={short_s.get('win_rate',0):.1%}, pf={short_s.get('profit_factor','N/A')}")

            long_pnl = long_s.get("pnl", 0)
            short_pnl = short_s.get("pnl", 0)
            if isinstance(long_pnl, Decimal):
                long_pnl = float(long_pnl)
            if isinstance(short_pnl, Decimal):
                short_pnl = float(short_pnl)

            if long_pnl < 0 and short_pnl < 0:
                print("   → 双边亏损，但 ", end="")
                if long_pnl < short_pnl:
                    print("LONG 侧亏损更严重")
                else:
                    print("SHORT 侧亏损更严重")
            elif long_pnl < 0:
                print("   → 主要是 LONG 侧失效")
            elif short_pnl < 0:
                print("   → 主要是 SHORT 侧失效")

        print("\n2. 过滤器敏感性判断:")
        if sensitivity_results:
            best = max(sensitivity_results, key=lambda x: x.get("pnl", float("-inf")))
            worst = min(sensitivity_results, key=lambda x: x.get("pnl", float("-inf")))
            print(f"   最好变体: {best['name']} ({best['desc']})")
            print(f"     trades={best.get('trades',0)}, pnl={best.get('pnl',0):.2f}, sharpe={best.get('sharpe',0):.4f}")
            print(f"   最差变体: {worst['name']} ({worst['desc']})")
            print(f"     trades={worst.get('trades',0)}, pnl={worst.get('pnl',0):.2f}, sharpe={worst.get('sharpe',0):.4f}")

            # Compare baseline vs relaxed
            baseline = next((r for r in sensitivity_results if r["name"] == "baseline"), None)
            no_ema = next((r for r in sensitivity_results if r["name"] == "no_ema"), None)
            relaxed_atr = next((r for r in sensitivity_results if r["name"] == "relaxed_atr"), None)

            if baseline and no_ema and "error" not in baseline and "error" not in no_ema:
                pnl_delta = no_ema.get("pnl", 0) - baseline.get("pnl", 0)
                trades_delta = no_ema.get("trades", 0) - baseline.get("trades", 0)
                print(f"\n   去掉 EMA 影响: trades {trades_delta:+d}, pnl {pnl_delta:+.2f}")
                if pnl_delta > 0 and trades_delta > 0:
                    print("   → EMA 过滤在样本外过度限制，去掉后改善")
                elif pnl_delta > 0 and trades_delta <= 0:
                    print("   → EMA 去掉后 pnl 改善但交易数未增，说明 EMA 在样本外选错了方向")
                else:
                    print("   → EMA 去掉后无改善或更差，问题不在 EMA")

            if baseline and relaxed_atr and "error" not in baseline and "error" not in relaxed_atr:
                pnl_delta = relaxed_atr.get("pnl", 0) - baseline.get("pnl", 0)
                trades_delta = relaxed_atr.get("trades", 0) - baseline.get("trades", 0)
                print(f"\n   放宽 ATR 影响: trades {trades_delta:+d}, pnl {pnl_delta:+.2f}")
                if pnl_delta > 0:
                    print("   → ATR 过滤在样本外过度限制，放宽后改善")
                else:
                    print("   → ATR 放宽后无改善，问题不在 ATR")

        print("\n3. 最可能的失效根因:")
        # Auto-diagnosis based on data
        if oos_report and oos_report.total_trades > 0:
            dir_split = analyze_direction_split(oos_report)
            long_wr = dir_split.get(Direction.LONG, {}).get("win_rate", 0)
            short_wr = dir_split.get(Direction.SHORT, {}).get("win_rate", 0)

            tp1_count_pct = tp1_count / total_closed if total_closed > 0 else 0
            sl_only_pct = sl_only / total_closed if total_closed > 0 else 0

            if sl_only_pct > 0.6:
                print(f"   → SL 直接命中率 {sl_only_pct:.0%}，entry 质量是主要问题")
                print("     建议优先改造：entry 条件（Pinbar 形态阈值或形态类型扩展）")
            elif long_wr < 0.4 and short_wr < 0.4:
                print(f"   → 双边胜率均低于 40%，filter 筛选逻辑失效")
                print("     建议优先改造：重新评估 EMA/MTF 方向判断在 2025+ 市场环境的适用性")
            elif tp1_count_pct < 0.3:
                print(f"   → TP1 命中率仅 {tp1_count_pct:.0%}，止盈目标设置不当")
                print("     建议优先改造：动态止盈目标（基于 ATR 或波动率调整 TP targets）")
            else:
                print("   → 多因素叠加：entry/filter/exit 均有退化")
                print("     建议优先改造：引入 regime detection，区分趋势/震荡市场")

        print("\n4. 下一步最值得做的策略改造方向:")
        print("   1) 引入市场状态识别（趋势/震荡 regime detection）")
        print("   2) EMA 方向判断改为动态 EMA（自适应周期）")
        print("   3) Pinbar 形态质量阈值引入自适应（基于近期波动率）")
        print("   4) 止盈目标动态化（基于 ATR 或支撑阻力位）")

    finally:
        await data_repo.close()
        print("\n\n分析完成!")


if __name__ == "__main__":
    asyncio.run(main())
