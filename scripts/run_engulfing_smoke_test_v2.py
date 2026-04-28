#!/usr/bin/env python3
"""
H5a-v2: Engulfing + EMA50 + 4h MTF Signal Smoke Test
补齐 4h MTF trend 数据后，重新评估 Engulfing 的真实 filtered signal density

约束：
- 不改 src 核心代码
- 不改 runtime profile
- 使用本地 HistoricalDataRepository (data/v3_dev.db)
- 自行维护 kline_history
- 自行计算 4h EMA60 trend
- 严格避免前瞻：4h close_time <= 1h signal_time
- 直接调用 DynamicStrategyRunner.run_all(..., kline_history=kline_history, higher_tf_trends=higher_tf_trends)
"""
import asyncio
import sys
from pathlib import Path
from decimal import Decimal
from typing import Dict, List, Optional
from datetime import datetime, timezone
from collections import defaultdict

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
PRIMARY_EMA_PERIOD = 50  # 主周期 EMA 周期（必须是 50）
MTF_EMA_PERIOD = 60  # MTF EMA 周期（必须是 60）
YEARS = [2023, 2024, 2025]
DB_PATH = "data/v3_dev.db"


class EngulfingSmokeTestV2:
    """Engulfing 信号烟测器 v2 - 完整 MTF 支持"""

    def __init__(self):
        self.repo = None

    async def setup(self):
        self.repo = HistoricalDataRepository(DB_PATH)
        await self.repo.initialize()

    async def teardown(self):
        if self.repo:
            await self.repo.close()

    def build_strategy_def(self, allowed_directions: List[str]) -> StrategyDefinition:
        """构建 Engulfing 策略定义（完整配置：EMA50 + MTF EMA60）"""
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
                        params={"period": PRIMARY_EMA_PERIOD}  # 主周期 EMA50
                    )),
                    FilterLeaf(type="filter", id="mtf", config=FilterConfig(
                        type="mtf",
                        params={"ema_period": MTF_EMA_PERIOD}  # MTF EMA60
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
        """
        计算 4h EMA trend map

        Returns:
            Dict[4h_close_timestamp, TrendDirection]
        """
        if len(klines_4h) < ema_period:
            return {}

        # 创建 EMA 指标
        ema = EMACalculator(period=ema_period)

        # 预热 EMA
        for kline in klines_4h[:ema_period]:
            ema.update(kline.close)

        trend_map = {}

        # 计算 trend
        for kline in klines_4h[ema_period:]:
            ema_value = ema.update(kline.close)

            if ema_value is None:
                continue

            # 判断 trend (使用 TrendDirection 枚举)
            if kline.close > ema_value:
                trend = TrendDirection.BULLISH
            elif kline.close < ema_value:
                trend = TrendDirection.BEARISH
            else:
                # 如果价格等于 EMA，使用 BULLISH 作为默认值
                trend = TrendDirection.BULLISH

            # 使用 4h K 线的 close time 作为 key
            # 4h K 线的 close time = timestamp + 4h
            close_time = kline.timestamp + 4 * 60 * 60 * 1000
            trend_map[close_time] = trend

        return trend_map

    def get_4h_trend_for_1h_signal(
        self,
        signal_time_1h: int,
        trend_map_4h: Dict[int, TrendDirection],
    ) -> Optional[TrendDirection]:
        """
        获取 1h 信号时间对应的 4h trend（严格避免前瞻）

        规则：只能使用已经收盘的 4h K 线
        条件：4h close_time <= 1h signal_time

        Args:
            signal_time_1h: 1h K 线的时间戳（毫秒）
            trend_map_4h: 4h trend map {close_time: TrendDirection}

        Returns:
            TrendDirection or None if not available
        """
        # 找到最近的已收盘 4h K 线
        # 4h close_time <= 1h signal_time
        valid_close_times = [
            close_time for close_time in trend_map_4h.keys()
            if close_time <= signal_time_1h
        ]

        if not valid_close_times:
            return None

        # 取最新的已收盘 4h K 线
        latest_close_time = max(valid_close_times)
        return trend_map_4h[latest_close_time]

    def run_smoke_test(
        self,
        klines_1h: List[KlineData],
        klines_4h: List[KlineData],
        strategy_def: StrategyDefinition,
    ) -> Dict:
        """运行烟测（直接调用 DynamicStrategyRunner）"""
        runner = create_dynamic_runner([strategy_def])
        kline_history: List[KlineData] = []

        # 计算 4h trend map
        trend_map_4h = self.compute_4h_trend_map(klines_4h, MTF_EMA_PERIOD)

        stats = {
            "raw_engulfing": 0,
            "ema_passed": 0,
            "mtf_passed": 0,
            "fired": 0,
            "long_count": 0,
            "short_count": 0,
            "scores": [],
            "mtf_block_reasons": defaultdict(int),
            "mtf_available_count": 0,
            "mtf_unavailable_count": 0,
        }

        for kline in klines_1h:
            kline_history.append(kline)
            runner.update_state(kline)

            # 获取当前 1h K 线对应的 4h trend（避免前瞻）
            trend_4h = self.get_4h_trend_for_1h_signal(kline.timestamp, trend_map_4h)

            # 构建 higher_tf_trends dict
            higher_tf_trends = {}
            if trend_4h is not None:
                higher_tf_trends["4h"] = trend_4h
                stats["mtf_available_count"] += 1
            else:
                stats["mtf_unavailable_count"] += 1

            attempts = runner.run_all(
                kline=kline,
                higher_tf_trends=higher_tf_trends,
                kline_history=kline_history[:-1]
            )

            for attempt in attempts:
                # Check if this is an engulfing pattern
                is_engulfing = "engulfing" in attempt.strategy_name.lower()

                if attempt.pattern is not None and is_engulfing:
                    stats["raw_engulfing"] += 1
                    stats["scores"].append(float(attempt.pattern.score))

                    ema_passed = any(
                        name == "ema_trend" and result.passed
                        for name, result in attempt.filter_results
                    )
                    mtf_passed = any(
                        name == "mtf" and result.passed
                        for name, result in attempt.filter_results
                    )

                    if ema_passed:
                        stats["ema_passed"] += 1

                    if mtf_passed:
                        stats["mtf_passed"] += 1

                    # 统计 MTF 拦截原因
                    for name, result in attempt.filter_results:
                        if name == "mtf" and not result.passed:
                            stats["mtf_block_reasons"][result.reason] += 1

                    if attempt.pattern.direction == Direction.LONG:
                        stats["long_count"] += 1
                    else:
                        stats["short_count"] += 1

                if attempt.final_result == "SIGNAL_FIRED":
                    stats["fired"] += 1

        stats["avg_score"] = (
            sum(stats["scores"]) / len(stats["scores"])
            if stats["scores"] else 0.0
        )
        return stats

    async def run_experiment(self, experiment_name: str, allowed_directions: List[str]) -> Dict[int, Dict]:
        print(f"\n{'='*70}")
        print(f"实验: {experiment_name}")
        print(f"{'='*70}")

        strategy_def = self.build_strategy_def(allowed_directions)
        yearly_stats = {}

        for year in YEARS:
            print(f"\n--- {year} ---")

            # 获取 1h 和 4h 数据
            klines_1h = await self.fetch_klines(year, TIMEFRAME)
            klines_4h = await self.fetch_klines(year, MTF_TIMEFRAME)

            print(f"获取 1h K 线: {len(klines_1h)} 根")
            print(f"获取 4h K 线: {len(klines_4h)} 根")

            if len(klines_1h) < 100 or len(klines_4h) < 100:
                print("警告: K 线数量不足，跳过")
                continue

            stats = self.run_smoke_test(klines_1h, klines_4h, strategy_def)
            yearly_stats[year] = stats

            print(f"Raw Engulfing: {stats['raw_engulfing']}")
            print(f"EMA Passed: {stats['ema_passed']}")
            print(f"MTF Passed: {stats['mtf_passed']}")
            print(f"Final FIRED: {stats['fired']}")
            print(f"LONG: {stats['long_count']}, SHORT: {stats['short_count']}")
            print(f"Avg Score: {stats['avg_score']:.3f}")
            print(f"4h Trend 可用率: {stats['mtf_available_count']}/{stats['mtf_available_count']+stats['mtf_unavailable_count']} "
                  f"({100*stats['mtf_available_count']/(stats['mtf_available_count']+stats['mtf_unavailable_count']):.1f}%)")

            if stats['mtf_block_reasons']:
                print(f"MTF 拦截原因:")
                for reason, count in sorted(stats['mtf_block_reasons'].items(), key=lambda x: -x[1]):
                    print(f"  {reason}: {count}")

        return yearly_stats

    def print_summary(self, all_results: Dict[str, Dict[int, Dict]]):
        print("\n" + "="*70)
        print("H5a-v2 Engulfing Signal Smoke Test 汇总")
        print("="*70)

        for exp_name, yearly_stats in all_results.items():
            print(f"\n{'-'*70}")
            print(f"实验: {exp_name}")
            print(f"{'-'*70}")

            total_raw = 0
            total_fired = 0
            total_long = 0
            total_short = 0
            total_mtf_available = 0
            total_mtf_unavailable = 0
            total_mtf_block_reasons = defaultdict(int)

            for year, stats in sorted(yearly_stats.items()):
                total_raw += stats["raw_engulfing"]
                total_fired += stats["fired"]
                total_long += stats["long_count"]
                total_short += stats["short_count"]
                total_mtf_available += stats["mtf_available_count"]
                total_mtf_unavailable += stats["mtf_unavailable_count"]

                for reason, count in stats['mtf_block_reasons'].items():
                    total_mtf_block_reasons[reason] += count

                density = stats["fired"] / 12 if stats["fired"] > 0 else 0

                print(f"{year}: raw={stats['raw_engulfing']:3d}, "
                      f"ema={stats['ema_passed']:3d}, "
                      f"mtf={stats['mtf_passed']:3d}, "
                      f"fired={stats['fired']:3d}, "
                      f"L/S={stats['long_count']}/{stats['short_count']}, "
                      f"avg_score={stats['avg_score']:.3f}, "
                      f"density={density:.1f}/month")

            print(f"\n总计: raw={total_raw}, fired={total_fired}, "
                  f"L/S={total_long}/{total_short}")

            print(f"\n4h Trend 可用率: {total_mtf_available}/{total_mtf_available+total_mtf_unavailable} "
                  f"({100*total_mtf_available/(total_mtf_available+total_mtf_unavailable):.1f}%)")

            if total_mtf_block_reasons:
                print(f"\nMTF 拦截原因分布:")
                for reason, count in sorted(total_mtf_block_reasons.items(), key=lambda x: -x[1]):
                    print(f"  {reason}: {count}")

            print(f"\n决策门评估:")
            if total_fired < 10:
                print(f"❌ 信号过少（{total_fired} < 10），建议关闭 Engulfing 研究")
            elif total_fired > 500:
                print(f"⚠️  信号过密（{total_fired} > 500），需要继续加过滤器假设")
            else:
                print(f"✅ 信号数量健康（{total_fired}），可进入 H5b PnL proxy")


async def main():
    test = EngulfingSmokeTestV2()
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
