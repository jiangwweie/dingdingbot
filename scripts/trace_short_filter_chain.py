#!/usr/bin/env python3
"""
ETH/USDT 1h SHORT 放行链路抽样诊断

直接调用 _run_v3_pms_backtest，通过 monkey-patch 捕获 all_attempts，
提取所有 SIGNAL_FIRED + SHORT 方向的 filter chain。
"""
import asyncio
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.infrastructure.historical_data_repository import HistoricalDataRepository
from src.application.backtester import Backtester
from src.domain.models import (
    BacktestRequest, BacktestRuntimeOverrides, Direction,
)

# ============================================================
# 配置
# ============================================================
SYMBOL = "ETH/USDT:USDT"
TIMEFRAME = "1h"
DB_PATH = "data/v3_dev.db"

START_TIME = 1735689600000   # 2025-01-01 00:00:00 UTC
END_TIME = 1767225599000     # 2025-12-31 23:59:59 UTC

INITIAL_BALANCE = Decimal("10000")
SLIPPAGE_RATE = Decimal("0.001")
TP_SLIPPAGE_RATE = Decimal("0.0005")
FEE_RATE = Decimal("0.0004")

BASELINE_PARAMS = {
    "max_atr_ratio": Decimal("0.0059"),
    "min_distance_pct": Decimal("0.0080"),
    "ema_period": 111,
    "tp_ratios": [Decimal("0.6"), Decimal("0.4")],
    "tp_targets": [Decimal("1.0"), Decimal("2.5")],
    "breakeven_enabled": False,
}


def fmt_ts(ts_ms):
    if ts_ms is None:
        return "N/A"
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


async def main():
    print("=" * 70)
    print("SHORT 放行链路抽样诊断 (2025 OOS)")
    print("=" * 70)

    data_repo = HistoricalDataRepository(DB_PATH)
    await data_repo.initialize()
    backtester = Backtester(exchange_gateway=None, data_repository=data_repo)

    # Container to capture all_attempts via monkey-patch
    captured = {"attempts": [], "position_summaries": [], "close_events": [], "signal_sl_map": {}}

    # Save original method
    original_method = backtester._run_v3_pms_backtest

    async def patched_run(request, repository=None, backtest_repository=None,
                          order_repository=None, kv_configs=None, runtime_overrides=None):
        # We need to intercept at the point where all_attempts is populated.
        # Strategy: wrap the method, and after it returns, access the internal
        # all_attempts. But since it's local, we need a different approach.
        # Instead, we'll patch _attempt_to_dict to capture attempts.
        result = await original_method(
            request, repository, backtest_repository, order_repository,
            kv_configs, runtime_overrides,
        )
        return result

    # Better approach: monkey-patch _attempt_to_dict to capture attempt data
    original_attempt_to_dict = backtester._attempt_to_dict

    def capturing_attempt_to_dict(attempt):
        d = original_attempt_to_dict(attempt)
        captured["attempts"].append({
            "direction": d.get("direction"),
            "final_result": d.get("final_result"),
            "kline_timestamp": d.get("kline_timestamp"),
            "pattern_score": d.get("pattern_score"),
            "filter_results": d.get("filter_results", []),
            "pnl_ratio": d.get("pnl_ratio"),
            "exit_reason": d.get("exit_reason"),
            "strategy_name": d.get("strategy_name"),
        })
        return d

    backtester._attempt_to_dict = capturing_attempt_to_dict

    try:
        request = BacktestRequest(
            symbol=SYMBOL,
            timeframe=TIMEFRAME,
            start_time=START_TIME,
            end_time=END_TIME,
            mode="v3_pms",
            initial_balance=INITIAL_BALANCE,
            slippage_rate=SLIPPAGE_RATE,
            tp_slippage_rate=TP_SLIPPAGE_RATE,
            fee_rate=FEE_RATE,
        )

        runtime_overrides = BacktestRuntimeOverrides(
            tp_ratios=BASELINE_PARAMS["tp_ratios"],
            tp_targets=BASELINE_PARAMS["tp_targets"],
            breakeven_enabled=BASELINE_PARAMS["breakeven_enabled"],
            max_atr_ratio=BASELINE_PARAMS["max_atr_ratio"],
            min_distance_pct=BASELINE_PARAMS["min_distance_pct"],
            ema_period=BASELINE_PARAMS["ema_period"],
        )

        result = await backtester.run_backtest(request, runtime_overrides=runtime_overrides)

    finally:
        await data_repo.close()

    # ===== 分析捕获的 attempts =====
    all_fired = [a for a in captured["attempts"] if a["final_result"] == "SIGNAL_FIRED"]
    short_fired = [a for a in all_fired if a["direction"] == "SHORT"]
    long_fired = [a for a in all_fired if a["direction"] == "LONG"]

    print(f"\n总 SIGNAL_FIRED: {len(all_fired)}")
    print(f"  LONG: {len(long_fired)}")
    print(f"  SHORT: {len(short_fired)}")

    # 从 report 中获取 position summaries 来关联盈亏
    pos_map = {}  # {signal_id -> position info} — 但 attempt 里没有 signal_id 在 captured 里
    # 用 pnl_ratio 作为盈亏代理（负=亏损，正=盈利）

    print(f"\nSHORT 信号中带 pnl_ratio 的数量: {len([a for a in short_fired if a['pnl_ratio'] is not None])}")

    # ===== SHORT 信号 filter chain 分析 =====
    print("\n" + "=" * 70)
    print("SHORT 信号 filter chain 逐笔分析")
    print("=" * 70)

    # 按 kline_timestamp 排序
    short_fired_sorted = sorted(short_fired, key=lambda x: x.get("kline_timestamp") or 0)

    # 统计 filter chain 模式
    ema_pass_reasons = {}
    mtf_pass_reasons = {}
    ema_bearish_count = 0
    ema_bullish_count = 0
    mtf_bearish_count = 0
    mtf_bullish_count = 0
    mtf_unavailable_count = 0

    for a in short_fired_sorted:
        for fr in a["filter_results"]:
            fname = fr["filter"]
            reason = fr["reason"]
            if fname == "ema_trend":
                ema_pass_reasons[reason] = ema_pass_reasons.get(reason, 0) + 1
                if "bearish" in reason or "trend_match" in reason:
                    ema_bearish_count += 1
                elif "bullish" in reason:
                    ema_bullish_count += 1
            elif fname == "mtf":
                mtf_pass_reasons[reason] = mtf_pass_reasons.get(reason, 0) + 1
                if "bearish" in reason or "confirmed" in reason:
                    mtf_bearish_count += 1
                elif "bullish" in reason:
                    mtf_bullish_count += 1
                elif "unavailable" in reason:
                    mtf_unavailable_count += 1

    print(f"\nEMA filter 放行原因分布:")
    for reason, count in sorted(ema_pass_reasons.items(), key=lambda x: -x[1]):
        print(f"  {reason}: {count}")

    print(f"\nMTF filter 放行原因分布:")
    for reason, count in sorted(mtf_pass_reasons.items(), key=lambda x: -x[1]):
        print(f"  {reason}: {count}")

    # ===== 抽样 10+ 笔 SHORT =====
    print("\n" + "=" * 70)
    print(f"SHORT 样本表 (共 {len(short_fired_sorted)} 笔，展示前 {min(15, len(short_fired_sorted))} 笔)")
    print("=" * 70)

    sample_count = min(15, len(short_fired_sorted))
    for i, a in enumerate(short_fired_sorted[:sample_count], 1):
        ts = fmt_ts(a.get("kline_timestamp"))
        score = a.get("pattern_score")
        pnl_r = a.get("pnl_ratio")
        exit_r = a.get("exit_reason")

        # Extract EMA trend
        ema_trend = "N/A"
        ema_reason = "N/A"
        mtf_trend = "N/A"
        mtf_reason = "N/A"

        for fr in a["filter_results"]:
            if fr["filter"] == "ema_trend":
                ema_reason = fr["reason"]
                # 从 reason 推断趋势方向
                if "trend_match" in fr["reason"]:
                    ema_trend = "BEARISH (match SHORT)"
                elif "bearish" in fr["reason"]:
                    ema_trend = "BEARISH"
                elif "bullish" in fr["reason"]:
                    ema_trend = "BULLISH"
                elif "disabled" in fr["reason"]:
                    ema_trend = "DISABLED"
            elif fr["filter"] == "mtf":
                mtf_reason = fr["reason"]
                if "bearish" in fr["reason"] or "confirmed" in fr["reason"]:
                    mtf_trend = "4h BEARISH"
                elif "bullish" in fr["reason"]:
                    mtf_trend = "4h BULLISH"
                elif "disabled" in fr["reason"]:
                    mtf_trend = "DISABLED"
                elif "unavailable" in fr["reason"]:
                    mtf_trend = "UNAVAILABLE"

        pnl_str = f"{pnl_r:+.2f}R" if pnl_r is not None else "N/A"
        is_profit = "盈利" if (pnl_r is not None and pnl_r > 0) else ("亏损" if (pnl_r is not None and pnl_r < 0) else "N/A")

        print(f"\n[{i}] {ts} | score={score} | {pnl_str} ({is_profit})")
        print(f"    EMA: {ema_trend} ({ema_reason})")
        print(f"    MTF: {mtf_trend} ({mtf_reason})")
        print(f"    exit: {exit_r}")

    # ===== 汇总判断 =====
    print("\n" + "=" * 70)
    print("SHORT 放行链路汇总")
    print("=" * 70)

    total_short = len(short_fired_sorted)
    winning_short = len([a for a in short_fired_sorted if a.get("pnl_ratio") is not None and a["pnl_ratio"] > 0])
    losing_short = len([a for a in short_fired_sorted if a.get("pnl_ratio") is not None and a["pnl_ratio"] < 0])

    print(f"\nSHORT 总数: {total_short}")
    print(f"  盈利: {winning_short} ({winning_short/max(1,total_short)*100:.1f}%)")
    print(f"  亏损: {losing_short} ({losing_short/max(1,total_short)*100:.1f}%)")

    print(f"\n放行条件统计:")
    print(f"  EMA bearish 放行: {ema_bearish_count}/{total_short} ({ema_bearish_count/max(1,total_short)*100:.1f}%)")
    print(f"  EMA bullish 放行: {ema_bullish_count}/{total_short} ({ema_bullish_count/max(1,total_short)*100:.1f}%)")
    print(f"  MTF bearish 放行: {mtf_bearish_count}/{total_short} ({mtf_bearish_count/max(1,total_short)*100:.1f}%)")
    print(f"  MTF bullish 放行: {mtf_bullish_count}/{total_short} ({mtf_bullish_count/max(1,total_short)*100:.1f}%)")
    print(f"  MTF unavailable: {mtf_unavailable_count}/{total_short}")

    # 盈亏的 SHORT 里 filter chain 差异
    winning_shorts = [a for a in short_fired_sorted if a.get("pnl_ratio") is not None and a["pnl_ratio"] > 0]
    losing_shorts = [a for a in short_fired_sorted if a.get("pnl_ratio") is not None and a["pnl_ratio"] < 0]

    def get_ema_mtf_summary(attempts):
        ema_bearish = sum(1 for a in attempts for fr in a["filter_results"]
                         if fr["filter"] == "ema_trend" and ("trend_match" in fr["reason"] or "bearish" in fr["reason"]))
        mtf_bearish = sum(1 for a in attempts for fr in a["filter_results"]
                         if fr["filter"] == "mtf" and ("bearish" in fr["reason"] or "confirmed" in fr["reason"]))
        return ema_bearish, mtf_bearish

    if winning_shorts:
        w_ema, w_mtf = get_ema_mtf_summary(winning_shorts)
        print(f"\n盈利 SHORT ({len(winning_shorts)}笔):")
        print(f"  EMA bearish: {w_ema}/{len(winning_shorts)}")
        print(f"  MTF bearish: {w_mtf}/{len(winning_shorts)}")

    if losing_shorts:
        l_ema, l_mtf = get_ema_mtf_summary(losing_shorts)
        print(f"\n亏损 SHORT ({len(losing_shorts)}笔):")
        print(f"  EMA bearish: {l_ema}/{len(losing_shorts)}")
        print(f"  MTF bearish: {l_mtf}/{len(losing_shorts)}")

    print("\n" + "=" * 70)
    print("完成!")


if __name__ == "__main__":
    asyncio.run(main())
