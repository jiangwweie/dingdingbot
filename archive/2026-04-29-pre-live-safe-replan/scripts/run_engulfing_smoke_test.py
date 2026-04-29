#!/usr/bin/env python3
"""
H5a: Engulfing Signal Smoke Test
验证 Engulfing 在 research-only loop 中能否产生合理信号

约束：
- 不改 src 核心代码
- 不改 runtime profile
- 使用本地 HistoricalDataRepository (data/v3_dev.db)
- 自行维护 kline_history
- 直接调用 DynamicStrategyRunner.run_all(..., kline_history=kline_history)
"""
import asyncio
import sys
from pathlib import Path
from decimal import Decimal
from typing import Dict, List
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.domain.models import (
    KlineData, Direction, StrategyDefinition,
)
from src.domain.logic_tree import (
    LogicNode, TriggerLeaf, FilterLeaf,
    TriggerConfig, FilterConfig,
)
from src.domain.strategy_engine import create_dynamic_runner
from src.infrastructure.historical_data_repository import HistoricalDataRepository

# 常量
SYMBOL = "ETH/USDT:USDT"
TIMEFRAME = "1h"
MTF_EMA_PERIOD = 60  # MTF EMA 周期（必须是 60）
YEARS = [2023, 2024, 2025]
DB_PATH = "data/v3_dev.db"


class EngulfingSmokeTest:
    """Engulfing 信号烟测器"""

    def __init__(self):
        self.repo = None

    async def setup(self):
        self.repo = HistoricalDataRepository(DB_PATH)
        await self.repo.initialize()

    async def teardown(self):
        if self.repo:
            await self.repo.close()

    def build_strategy_def(self, allowed_directions: List[str]) -> StrategyDefinition:
        """构建 Engulfing 策略定义（无 MTF，仅 EMA50）"""
        return StrategyDefinition(
            id=f"engulfing_{'_'.join(allowed_directions).lower()}_no_mtf",
            name=f"Engulfing {'/'.join(allowed_directions)} (no MTF)",
            logic_tree=LogicNode(
                gate="AND",
                children=[
                    TriggerLeaf(type="trigger", id="engulfing", config=TriggerConfig(
                        type="engulfing",
                        params={"max_wick_ratio": 0.6}
                    )),
                    FilterLeaf(type="filter", id="ema", config=FilterConfig(
                        type="ema_trend",
                        params={"period": 50}  # 主周期 EMA50
                    )),
                    # MTF filter removed for smoke test
                ]
            ),
            apply_to=[f"{SYMBOL}:{TIMEFRAME}"]
        )

    async def fetch_klines(self, year: int) -> List[KlineData]:
        """获取指定年份的 K 线数据"""
        start_time = int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        end_time = int(datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)

        klines = await self.repo.get_klines(
            symbol=SYMBOL,
            timeframe=TIMEFRAME,
            start_time=start_time,
            end_time=end_time,
            limit=10000,
        )
        return klines

    def run_smoke_test(
        self,
        klines: List[KlineData],
        strategy_def: StrategyDefinition,
    ) -> Dict:
        """运行烟测（直接调用 DynamicStrategyRunner）"""
        runner = create_dynamic_runner([strategy_def])
        kline_history: List[KlineData] = []

        stats = {
            "raw_engulfing": 0,
            "ema_passed": 0,
            "fired": 0,
            "long_count": 0,
            "short_count": 0,
            "scores": [],
        }

        for idx, kline in enumerate(klines):
            kline_history.append(kline)
            runner.update_state(kline)

            # 简化：不验证 MTF（需要 4h 数据）
            higher_tf_trends = {}

            attempts = runner.run_all(
                kline=kline,
                higher_tf_trends=higher_tf_trends,
                kline_history=kline_history[:-1]
            )

            for attempt in attempts:
                # Check if this is an engulfing pattern (strategy name contains "engulfing")
                is_engulfing = "engulfing" in attempt.strategy_name.lower()

                if attempt.pattern is not None and is_engulfing:
                    stats["raw_engulfing"] += 1
                    stats["scores"].append(float(attempt.pattern.score))

                    ema_passed = any(
                        name == "ema_trend" and result.passed
                        for name, result in attempt.filter_results
                    )

                    if ema_passed:
                        stats["ema_passed"] += 1

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
            klines = await self.fetch_klines(year)
            print(f"获取 K 线: {len(klines)} 根")

            if len(klines) < 100:
                print("警告: K 线数量不足，跳过")
                continue

            stats = self.run_smoke_test(klines, strategy_def)
            yearly_stats[year] = stats

            print(f"Raw Engulfing: {stats['raw_engulfing']}")
            print(f"EMA Passed: {stats['ema_passed']}")
            print(f"Final FIRED: {stats['fired']}")
            print(f"LONG: {stats['long_count']}, SHORT: {stats['short_count']}")
            print(f"Avg Score: {stats['avg_score']:.3f}")

        return yearly_stats

    def print_summary(self, all_results: Dict[str, Dict[int, Dict]]):
        print("\n" + "="*70)
        print("H5a Engulfing Signal Smoke Test 汇总")
        print("="*70)

        for exp_name, yearly_stats in all_results.items():
            print(f"\n{'-'*70}")
            print(f"实验: {exp_name}")
            print(f"{'-'*70}")

            total_raw = 0
            total_fired = 0
            total_long = 0
            total_short = 0

            for year, stats in sorted(yearly_stats.items()):
                total_raw += stats["raw_engulfing"]
                total_fired += stats["fired"]
                total_long += stats["long_count"]
                total_short += stats["short_count"]
                density = stats["fired"] / 12 if stats["fired"] > 0 else 0

                print(f"{year}: raw={stats['raw_engulfing']:3d}, "
                      f"ema={stats['ema_passed']:3d}, "
                      f"fired={stats['fired']:3d}, "
                      f"L/S={stats['long_count']}/{stats['short_count']}, "
                      f"avg_score={stats['avg_score']:.3f}, "
                      f"density={density:.1f}/month")

            print(f"\n总计: raw={total_raw}, fired={total_fired}, "
                  f"L/S={total_long}/{total_short}")

            print(f"\n决策门评估:")
            if total_fired < 10:
                print("❌ 信号过少（<10），建议关闭 Engulfing 研究")
            elif total_fired > 500:
                print("⚠️  信号过密（>500），可能需要加强过滤")
            else:
                print(f"✅ 信号数量健康（{total_fired}），可进入 H5b PnL proxy")


async def main():
    test = EngulfingSmokeTest()
    try:
        await test.setup()
        results = {}

        results["E1: LONG-only"] = await test.run_experiment(
            "E1: Engulfing + EMA50 (no MTF) + LONG-only",
            allowed_directions=["LONG"]
        )

        results["E2: SHORT-only"] = await test.run_experiment(
            "E2: Engulfing + EMA50 (no MTF) + SHORT-only shadow",
            allowed_directions=["SHORT"]
        )

        results["E3: LONG/SHORT"] = await test.run_experiment(
            "E3: Engulfing + EMA50 (no MTF) + LONG/SHORT shadow",
            allowed_directions=["LONG", "SHORT"]
        )

        test.print_summary(results)
    finally:
        await test.teardown()


if __name__ == "__main__":
    asyncio.run(main())
