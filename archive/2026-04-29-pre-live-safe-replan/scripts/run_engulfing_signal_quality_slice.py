#!/usr/bin/env python3
"""
H5a-v2.1: Engulfing Signal Quality Slice
评估 1,458 个 MTF 后信号的后续价格行为质量

约束：
- 不改 src 核心代码
- 不改 runtime profile
- 不做完整撮合
- 只评估后续价格行为
"""
import asyncio
import sys
from pathlib import Path
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
from collections import defaultdict
from dataclasses import dataclass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.domain.models import (
    KlineData, Direction, StrategyDefinition, TrendDirection,
)
from src.domain.logic_tree import (
    LogicNode, TriggerLeaf, FilterLeaf,
    TriggerConfig, FilterConfig,
)
from src.domain.strategy_engine import create_dynamic_runner
from src.infrastructure.historical_data_repository import HistoricalDataRepository
from src.domain.indicators import EMACalculator

# 常量
SYMBOL = "ETH/USDT:USDT"
TIMEFRAME = "1h"
MTF_TIMEFRAME = "4h"
PRIMARY_EMA_PERIOD = 50
MTF_EMA_PERIOD = 60
YEARS = [2023, 2024, 2025]
DB_PATH = "data/v3_dev.db"

# R levels
R_LEVELS = [Decimal("1.0"), Decimal("2.0"), Decimal("3.5")]


@dataclass
class SignalRecord:
    """信号记录"""
    timestamp: int
    direction: Direction
    entry_price: Decimal
    signal_k_high: Decimal
    signal_k_low: Decimal
    prev_k_high: Decimal
    prev_k_low: Decimal
    score: Decimal
    year: int


@dataclass
class PriceBehavior:
    """价格行为统计"""
    mfe_24h: Decimal
    mae_24h: Decimal
    reached_1r: bool
    reached_2r: bool
    reached_35r: bool
    reached_sl_s1: bool  # single-candle stop
    reached_sl_s2: bool  # two-candle structure stop
    first_touch: str  # "1R" or "SL_S1" or "SL_S2"


class EngulfingSignalQualitySlice:
    """Engulfing 信号质量切片分析"""

    def __init__(self):
        self.repo = None

    async def setup(self):
        self.repo = HistoricalDataRepository(DB_PATH)
        await self.repo.initialize()

    async def teardown(self):
        if self.repo:
            await self.repo.close()

    def build_strategy_def(self, allowed_directions: List[str]) -> StrategyDefinition:
        """构建 Engulfing 策略定义"""
        return StrategyDefinition(
            id=f"engulfing_{'_'.join(allowed_directions).lower()}_mtf",
            name=f"Engulfing {'/'.join(allowed_directions)}",
            logic_tree=LogicNode(
                gate="AND",
                children=[
                    TriggerLeaf(type="trigger", id="engulfing", config=TriggerConfig(
                        type="engulfing",
                        params={"max_wick_ratio": 0.6}
                    )),
                    FilterLeaf(type="filter", id="ema", config=FilterConfig(
                        type="ema_trend",
                        params={"period": PRIMARY_EMA_PERIOD}
                    )),
                    FilterLeaf(type="filter", id="mtf", config=FilterConfig(
                        type="mtf",
                        params={"ema_period": MTF_EMA_PERIOD}
                    )),
                ]
            ),
            apply_to=[f"{SYMBOL}:{TIMEFRAME}"]
        )

    async def fetch_klines(self, year: int, timeframe: str) -> List[KlineData]:
        """获取指定年份和时间周期的 K 线数据"""
        start_time = int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        end_time = int(datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)

        klines = await self.repo.get_klines(
            symbol=SYMBOL,
            timeframe=timeframe,
            start_time=start_time,
            end_time=end_time,
            limit=10000,
        )
        return klines

    def compute_4h_trend_map(
        self,
        klines_4h: List[KlineData],
        ema_period: int = 60,
    ) -> Dict[int, TrendDirection]:
        """计算 4h EMA trend map"""
        if len(klines_4h) < ema_period:
            return {}

        ema = EMACalculator(period=ema_period)

        for kline in klines_4h[:ema_period]:
            ema.update(kline.close)

        trend_map = {}

        for kline in klines_4h[ema_period:]:
            ema_value = ema.update(kline.close)

            if ema_value is None:
                continue

            if kline.close > ema_value:
                trend = TrendDirection.BULLISH
            elif kline.close < ema_value:
                trend = TrendDirection.BEARISH
            else:
                trend = TrendDirection.BULLISH

            close_time = kline.timestamp + 4 * 60 * 60 * 1000
            trend_map[close_time] = trend

        return trend_map

    def get_4h_trend_for_1h_signal(
        self,
        signal_time_1h: int,
        trend_map_4h: Dict[int, TrendDirection],
    ) -> Optional[TrendDirection]:
        """获取 1h 信号时间对应的 4h trend（避免前瞻）"""
        valid_close_times = [
            close_time for close_time in trend_map_4h.keys()
            if close_time <= signal_time_1h
        ]

        if not valid_close_times:
            return None

        latest_close_time = max(valid_close_times)
        return trend_map_4h[latest_close_time]

    def calculate_price_behavior(
        self,
        signal: SignalRecord,
        future_klines: List[KlineData],
    ) -> PriceBehavior:
        """
        计算信号后续价格行为

        Args:
            signal: 信号记录
            future_klines: 后续 24h 的 K 线数据

        Returns:
            PriceBehavior 统计结果
        """
        if not future_klines:
            return PriceBehavior(
                mfe_24h=Decimal("0"),
                mae_24h=Decimal("0"),
                reached_1r=False,
                reached_2r=False,
                reached_35r=False,
                reached_sl_s1=False,
                reached_sl_s2=False,
                first_touch="none",
            )

        # 计算止损距离（S1 和 S2）
        if signal.direction == Direction.LONG:
            # LONG: stop below signal
            stop_distance_s1 = signal.entry_price - signal.signal_k_low
            stop_distance_s2 = signal.entry_price - min(signal.signal_k_low, signal.prev_k_low)

            # R levels above entry
            r1_price = signal.entry_price + stop_distance_s1 * R_LEVELS[0]
            r2_price = signal.entry_price + stop_distance_s1 * R_LEVELS[1]
            r35_price = signal.entry_price + stop_distance_s1 * R_LEVELS[2]

            # Stop prices
            sl_s1_price = signal.signal_k_low
            sl_s2_price = min(signal.signal_k_low, signal.prev_k_low)
        else:
            # SHORT: stop above signal
            stop_distance_s1 = signal.signal_k_high - signal.entry_price
            stop_distance_s2 = max(signal.signal_k_high, signal.prev_k_high) - signal.entry_price

            # R levels below entry
            r1_price = signal.entry_price - stop_distance_s1 * R_LEVELS[0]
            r2_price = signal.entry_price - stop_distance_s1 * R_LEVELS[1]
            r35_price = signal.entry_price - stop_distance_s1 * R_LEVELS[2]

            # Stop prices
            sl_s1_price = signal.signal_k_high
            sl_s2_price = max(signal.signal_k_high, signal.prev_k_high)

        # 统计后续价格行为
        max_favorable = Decimal("0")
        max_adverse = Decimal("0")
        reached_1r = False
        reached_2r = False
        reached_35r = False
        reached_sl_s1 = False
        reached_sl_s2 = False
        first_touch = "none"

        for kline in future_klines:
            if signal.direction == Direction.LONG:
                # MFE: highest price above entry
                favorable = kline.high - signal.entry_price
                if favorable > max_favorable:
                    max_favorable = favorable

                # MAE: lowest price below entry
                adverse = signal.entry_price - kline.low
                if adverse > max_adverse:
                    max_adverse = adverse

                # Check R levels
                if kline.high >= r1_price and not reached_1r:
                    reached_1r = True
                    if first_touch == "none":
                        first_touch = "1R"

                if kline.high >= r2_price:
                    reached_2r = True

                if kline.high >= r35_price:
                    reached_35r = True

                # Check stop losses
                if kline.low <= sl_s1_price and not reached_sl_s1:
                    reached_sl_s1 = True
                    if first_touch == "none":
                        first_touch = "SL_S1"

                if kline.low <= sl_s2_price and not reached_sl_s2:
                    reached_sl_s2 = True
                    if first_touch == "none":
                        first_touch = "SL_S2"

            else:  # SHORT
                # MFE: lowest price below entry
                favorable = signal.entry_price - kline.low
                if favorable > max_favorable:
                    max_favorable = favorable

                # MAE: highest price above entry
                adverse = kline.high - signal.entry_price
                if adverse > max_adverse:
                    max_adverse = adverse

                # Check R levels
                if kline.low <= r1_price and not reached_1r:
                    reached_1r = True
                    if first_touch == "none":
                        first_touch = "1R"

                if kline.low <= r2_price:
                    reached_2r = True

                if kline.low <= r35_price:
                    reached_35r = True

                # Check stop losses
                if kline.high >= sl_s1_price and not reached_sl_s1:
                    reached_sl_s1 = True
                    if first_touch == "none":
                        first_touch = "SL_S1"

                if kline.high >= sl_s2_price and not reached_sl_s2:
                    reached_sl_s2 = True
                    if first_touch == "none":
                        first_touch = "SL_S2"

        # Convert to percentage
        mfe_pct = (max_favorable / signal.entry_price) * Decimal("100") if signal.entry_price > 0 else Decimal("0")
        mae_pct = (max_adverse / signal.entry_price) * Decimal("100") if signal.entry_price > 0 else Decimal("0")

        return PriceBehavior(
            mfe_24h=mfe_pct,
            mae_24h=mae_pct,
            reached_1r=reached_1r,
            reached_2r=reached_2r,
            reached_35r=reached_35r,
            reached_sl_s1=reached_sl_s1,
            reached_sl_s2=reached_sl_s2,
            first_touch=first_touch,
        )

    def run_quality_analysis(
        self,
        klines_1h: List[KlineData],
        klines_4h: List[KlineData],
        strategy_def: StrategyDefinition,
    ) -> Dict:
        """运行信号质量分析"""
        runner = create_dynamic_runner([strategy_def])
        kline_history: List[KlineData] = []

        trend_map_4h = self.compute_4h_trend_map(klines_4h, MTF_EMA_PERIOD)

        # 收集所有 FIRED 信号
        signals: List[SignalRecord] = []

        for idx, kline in enumerate(klines_1h):
            kline_history.append(kline)
            runner.update_state(kline)

            trend_4h = self.get_4h_trend_for_1h_signal(kline.timestamp, trend_map_4h)

            higher_tf_trends = {}
            if trend_4h is not None:
                higher_tf_trends["4h"] = trend_4h

            attempts = runner.run_all(
                kline=kline,
                higher_tf_trends=higher_tf_trends,
                kline_history=kline_history[:-1]
            )

            for attempt in attempts:
                is_engulfing = "engulfing" in attempt.strategy_name.lower()

                if attempt.pattern is not None and is_engulfing and attempt.final_result == "SIGNAL_FIRED":
                    # 获取 prev_kline
                    prev_kline = kline_history[-1] if kline_history else kline

                    signal = SignalRecord(
                        timestamp=kline.timestamp,
                        direction=attempt.pattern.direction,
                        entry_price=kline.close,
                        signal_k_high=kline.high,
                        signal_k_low=kline.low,
                        prev_k_high=prev_kline.high,
                        prev_k_low=prev_kline.low,
                        score=attempt.pattern.score,
                        year=datetime.fromtimestamp(kline.timestamp / 1000, tz=timezone.utc).year,
                    )
                    signals.append(signal)

        # 分析每个信号的后续价格行为
        stats = {
            "total_signals": len(signals),
            "long_count": sum(1 for s in signals if s.direction == Direction.LONG),
            "short_count": sum(1 for s in signals if s.direction == Direction.SHORT),
            "yearly_stats": defaultdict(lambda: {
                "long": {"count": 0, "mfe": [], "mae": [], "reach_1r": 0, "reach_2r": 0, "reach_35r": 0,
                         "sl_s1": 0, "sl_s2": 0, "first_1r": 0, "first_sl_s1": 0, "first_sl_s2": 0},
                "short": {"count": 0, "mfe": [], "mae": [], "reach_1r": 0, "reach_2r": 0, "reach_35r": 0,
                          "sl_s1": 0, "sl_s2": 0, "first_1r": 0, "first_sl_s1": 0, "first_sl_s2": 0},
            }),
        }

        for signal in signals:
            # 获取后续 24h K 线
            signal_idx = next((i for i, k in enumerate(klines_1h) if k.timestamp == signal.timestamp), None)

            if signal_idx is None:
                continue

            future_klines = klines_1h[signal_idx + 1:signal_idx + 25]  # 24h = 24 bars

            behavior = self.calculate_price_behavior(signal, future_klines)

            # 统计
            direction_key = "long" if signal.direction == Direction.LONG else "short"
            year_stats = stats["yearly_stats"][signal.year][direction_key]

            year_stats["count"] += 1
            year_stats["mfe"].append(float(behavior.mfe_24h))
            year_stats["mae"].append(float(behavior.mae_24h))

            if behavior.reached_1r:
                year_stats["reach_1r"] += 1
            if behavior.reached_2r:
                year_stats["reach_2r"] += 1
            if behavior.reached_35r:
                year_stats["reach_35r"] += 1
            if behavior.reached_sl_s1:
                year_stats["sl_s1"] += 1
            if behavior.reached_sl_s2:
                year_stats["sl_s2"] += 1
            if behavior.first_touch == "1R":
                year_stats["first_1r"] += 1
            elif behavior.first_touch == "SL_S1":
                year_stats["first_sl_s1"] += 1
            elif behavior.first_touch == "SL_S2":
                year_stats["first_sl_s2"] += 1

        return stats

    async def run_experiment(self, experiment_name: str, allowed_directions: List[str]) -> Dict:
        print(f"\n{'='*70}")
        print(f"实验: {experiment_name}")
        print(f"{'='*70}")

        strategy_def = self.build_strategy_def(allowed_directions)
        yearly_stats = {}

        for year in YEARS:
            print(f"\n--- {year} ---")

            klines_1h = await self.fetch_klines(year, TIMEFRAME)
            klines_4h = await self.fetch_klines(year, MTF_TIMEFRAME)

            print(f"获取 1h K 线: {len(klines_1h)} 根")
            print(f"获取 4h K 线: {len(klines_4h)} 根")

            if len(klines_1h) < 100 or len(klines_4h) < 100:
                print("警告: K 线数量不足，跳过")
                continue

            stats = self.run_quality_analysis(klines_1h, klines_4h, strategy_def)
            yearly_stats[year] = stats

            print(f"Total Signals: {stats['total_signals']}")
            print(f"LONG: {stats['long_count']}, SHORT: {stats['short_count']}")

            for direction in ["long", "short"]:
                dir_stats = stats["yearly_stats"][year][direction]
                if dir_stats["count"] > 0:
                    avg_mfe = sum(dir_stats["mfe"]) / len(dir_stats["mfe"])
                    avg_mae = sum(dir_stats["mae"]) / len(dir_stats["mae"])
                    reach_1r_pct = 100 * dir_stats["reach_1r"] / dir_stats["count"]
                    reach_2r_pct = 100 * dir_stats["reach_2r"] / dir_stats["count"]
                    reach_35r_pct = 100 * dir_stats["reach_35r"] / dir_stats["count"]
                    sl_s1_pct = 100 * dir_stats["sl_s1"] / dir_stats["count"]
                    sl_s2_pct = 100 * dir_stats["sl_s2"] / dir_stats["count"]

                    print(f"\n{direction.upper()} ({dir_stats['count']} signals):")
                    print(f"  Avg MFE 24h: {avg_mfe:.2f}%, Avg MAE 24h: {avg_mae:.2f}%")
                    print(f"  +1R reach: {reach_1r_pct:.1f}% ({dir_stats['reach_1r']}/{dir_stats['count']})")
                    print(f"  +2R reach: {reach_2r_pct:.1f}% ({dir_stats['reach_2r']}/{dir_stats['count']})")
                    print(f"  +3.5R reach: {reach_35r_pct:.1f}% ({dir_stats['reach_35r']}/{dir_stats['count']})")
                    print(f"  SL S1 reach: {sl_s1_pct:.1f}% ({dir_stats['sl_s1']}/{dir_stats['count']})")
                    print(f"  SL S2 reach: {sl_s2_pct:.1f}% ({dir_stats['sl_s2']}/{dir_stats['count']})")
                    print(f"  First touch: 1R={dir_stats['first_1r']}, SL_S1={dir_stats['first_sl_s1']}, SL_S2={dir_stats['first_sl_s2']}")

        return yearly_stats

    def print_summary(self, all_results: Dict[str, Dict[int, Dict]]):
        print("\n" + "="*70)
        print("H5a-v2.1 Engulfing Signal Quality Slice 汇总")
        print("="*70)

        for exp_name, yearly_stats in all_results.items():
            print(f"\n{'-'*70}")
            print(f"实验: {exp_name}")
            print(f"{'-'*70}")

            # 汇总所有年份
            total_long = {"count": 0, "mfe": [], "mae": [], "reach_1r": 0, "reach_2r": 0, "reach_35r": 0,
                          "sl_s1": 0, "sl_s2": 0, "first_1r": 0, "first_sl_s1": 0, "first_sl_s2": 0}
            total_short = {"count": 0, "mfe": [], "mae": [], "reach_1r": 0, "reach_2r": 0, "reach_35r": 0,
                           "sl_s1": 0, "sl_s2": 0, "first_1r": 0, "first_sl_s1": 0, "first_sl_s2": 0}

            for year, stats in sorted(yearly_stats.items()):
                for direction in ["long", "short"]:
                    dir_stats = stats["yearly_stats"][year][direction]
                    target = total_long if direction == "long" else total_short

                    target["count"] += dir_stats["count"]
                    target["mfe"].extend(dir_stats["mfe"])
                    target["mae"].extend(dir_stats["mae"])
                    target["reach_1r"] += dir_stats["reach_1r"]
                    target["reach_2r"] += dir_stats["reach_2r"]
                    target["reach_35r"] += dir_stats["reach_35r"]
                    target["sl_s1"] += dir_stats["sl_s1"]
                    target["sl_s2"] += dir_stats["sl_s2"]
                    target["first_1r"] += dir_stats["first_1r"]
                    target["first_sl_s1"] += dir_stats["first_sl_s1"]
                    target["first_sl_s2"] += dir_stats["first_sl_s2"]

            # 打印汇总
            for direction, total in [("LONG", total_long), ("SHORT", total_short)]:
                if total["count"] > 0:
                    avg_mfe = sum(total["mfe"]) / len(total["mfe"])
                    avg_mae = sum(total["mae"]) / len(total["mae"])
                    reach_1r_pct = 100 * total["reach_1r"] / total["count"]
                    reach_2r_pct = 100 * total["reach_2r"] / total["count"]
                    reach_35r_pct = 100 * total["reach_35r"] / total["count"]
                    sl_s1_pct = 100 * total["sl_s1"] / total["count"]
                    sl_s2_pct = 100 * total["sl_s2"] / total["count"]

                    print(f"\n{direction} (总计 {total['count']} signals):")
                    print(f"  Avg MFE 24h: {avg_mfe:.2f}%, Avg MAE 24h: {avg_mae:.2f}%")
                    print(f"  +1R reach: {reach_1r_pct:.1f}% ({total['reach_1r']}/{total['count']})")
                    print(f"  +2R reach: {reach_2r_pct:.1f}% ({total['reach_2r']}/{total['count']})")
                    print(f"  +3.5R reach: {reach_35r_pct:.1f}% ({total['reach_35r']}/{total['count']})")
                    print(f"  SL S1 reach: {sl_s1_pct:.1f}% ({total['sl_s1']}/{total['count']})")
                    print(f"  SL S2 reach: {sl_s2_pct:.1f}% ({total['sl_s2']}/{total['count']})")
                    print(f"  First touch: 1R={total['first_1r']}, SL_S1={total['first_sl_s1']}, SL_S2={total['first_sl_s2']}")

            # 决策判定
            print(f"\n{'='*70}")
            print("决策判定:")
            print(f"{'='*70}")

            # 判定 1: +1R reach rate
            total_signals = total_long["count"] + total_short["count"]
            total_reach_1r = total_long["reach_1r"] + total_short["reach_1r"]
            reach_1r_pct = 100 * total_reach_1r / total_signals if total_signals > 0 else 0

            print(f"\n1. +1R reach rate: {reach_1r_pct:.1f}%")
            if reach_1r_pct < 30:
                print("   ❌ +1R reach rate 很低 (<30%)，建议关闭 Engulfing")
            else:
                print(f"   ✅ +1R reach rate 可接受 (≥30%)")

            # 判定 2: +3.5R reach rate
            total_reach_35r = total_long["reach_35r"] + total_short["reach_35r"]
            reach_35r_pct = 100 * total_reach_35r / total_signals if total_signals > 0 else 0

            print(f"\n2. +3.5R reach rate: {reach_35r_pct:.1f}%")
            if reach_35r_pct < 10:
                print("   ⚠️  +3.5R reach rate 很低 (<10%)，不适合趋势结构，可研究短 TP / mean-reversion")
            else:
                print(f"   ✅ +3.5R reach rate 可接受 (≥10%)")

            # 判定 3: LONG vs SHORT
            long_reach_1r_pct = 100 * total_long["reach_1r"] / total_long["count"] if total_long["count"] > 0 else 0
            short_reach_1r_pct = 100 * total_short["reach_1r"] / total_short["count"] if total_short["count"] > 0 else 0

            print(f"\n3. LONG vs SHORT +1R reach rate:")
            print(f"   LONG: {long_reach_1r_pct:.1f}%")
            print(f"   SHORT: {short_reach_1r_pct:.1f}%")

            if abs(long_reach_1r_pct - short_reach_1r_pct) > 15:
                better = "LONG" if long_reach_1r_pct > short_reach_1r_pct else "SHORT"
                print(f"   ⚠️  {better} 明显优于另一方（差距 >15%），建议只研究 {better}")
            else:
                print("   ✅ LONG/SHORT 表现接近，可同时研究")

            # 判定 4: S1 vs S2
            total_sl_s1 = total_long["sl_s1"] + total_short["sl_s1"]
            total_sl_s2 = total_long["sl_s2"] + total_short["sl_s2"]
            sl_s1_pct = 100 * total_sl_s1 / total_signals if total_signals > 0 else 0
            sl_s2_pct = 100 * total_sl_s2 / total_signals if total_signals > 0 else 0

            print(f"\n4. Stop Loss 口径:")
            print(f"   S1 (single-candle): {sl_s1_pct:.1f}%")
            print(f"   S2 (two-candle): {sl_s2_pct:.1f}%")

            if sl_s2_pct < sl_s1_pct - 10:
                print("   ⚠️  S2 明显优于 S1（触发率低 >10%），建议使用 Engulfing 专属 two-candle structure stop")
            else:
                print("   ✅ S1/S2 差异不大，可使用标准 single-candle stop")


async def main():
    test = EngulfingSignalQualitySlice()
    try:
        await test.setup()
        results = {}

        results["E1: LONG-only"] = await test.run_experiment(
            "E1: Engulfing + EMA50 + 4h MTF EMA60 + LONG-only",
            allowed_directions=["LONG"]
        )

        results["E2: SHORT-only"] = await test.run_experiment(
            "E2: Engulfing + EMA50 + 4h MTF EMA60 + SHORT-only shadow",
            allowed_directions=["SHORT"]
        )

        results["E3: LONG/SHORT"] = await test.run_experiment(
            "E3: Engulfing + EMA50 + 4h MTF EMA60 + LONG/SHORT shadow",
            allowed_directions=["LONG", "SHORT"]
        )

        test.print_summary(results)
    finally:
        await test.teardown()


if __name__ == "__main__":
    asyncio.run(main())
