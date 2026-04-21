#!/usr/bin/env python3
"""
诊断 MTF 数据传递

目标：
1. 检查 higher_tf_data 是否正确加载
2. 检查 _get_closest_higher_tf_trends 是否正确返回趋势
"""
import asyncio
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.infrastructure.historical_data_repository import HistoricalDataRepository


async def diagnose_mtf_data():
    """诊断 MTF 数据传递"""

    print("=" * 80)
    print("诊断 MTF 数据传递")
    print("=" * 80)

    # 数据仓库
    DB_PATH = "data/v3_dev.db"
    data_repo = HistoricalDataRepository(DB_PATH)
    await data_repo.initialize()

    try:
        # 时间范围：2024-01-01 ~ 2024-01-31 (1 个月，加快验证)
        start_ts = int(datetime(2024, 1, 1).timestamp() * 1000)
        end_ts = int(datetime(2024, 1, 31, 23, 59, 59).timestamp() * 1000)

        # 获取 1h K 线数据
        klines_1h = await data_repo.get_klines(
            symbol="ETH/USDT:USDT",
            timeframe="1h",
            start_time=start_ts,
            limit=1000,
        )

        print(f"\n【1h K 线数据】")
        print(f"  总数: {len(klines_1h)}")
        print(f"  时间范围: {datetime.fromtimestamp(klines_1h[0].timestamp/1000)} ~ {datetime.fromtimestamp(klines_1h[-1].timestamp/1000)}")

        # 获取 4h K 线数据
        klines_4h = await data_repo.get_klines(
            symbol="ETH/USDT:USDT",
            timeframe="4h",
            start_time=start_ts,
            limit=1000,
        )

        print(f"\n【4h K 线数据】")
        print(f"  总数: {len(klines_4h)}")
        print(f"  时间范围: {datetime.fromtimestamp(klines_4h[0].timestamp/1000)} ~ {datetime.fromtimestamp(klines_4h[-1].timestamp/1000)}")

        # 构建 higher_tf_data（模拟 backtester 的逻辑）
        from src.domain.models import TrendDirection

        higher_tf_data = {}
        for kline in klines_4h:
            higher_tf_data[kline.timestamp] = {
                "4h": TrendDirection.BULLISH if kline.close > kline.open else TrendDirection.BEARISH
            }

        print(f"\n【higher_tf_data 构建】")
        print(f"  总数: {len(higher_tf_data)}")

        # 模拟 _get_closest_higher_tf_trends
        def _parse_timeframe(timeframe: str) -> int:
            mapping = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440, "1w": 10080}
            return mapping.get(timeframe, 15)

        def _get_closest_higher_tf_trends(timestamp, higher_tf_data):
            if not higher_tf_data:
                return {}

            first_entry = next(iter(higher_tf_data.values()))
            higher_tf = next(iter(first_entry.keys())) if first_entry else None

            if higher_tf is None:
                return {}

            higher_tf_period_ms = _parse_timeframe(higher_tf) * 60 * 1000

            closest_ts = None
            for ts, trends in higher_tf_data.items():
                candle_close_time = ts + higher_tf_period_ms
                if candle_close_time <= timestamp:
                    if closest_ts is None or ts > closest_ts:
                        closest_ts = ts

            if closest_ts is None:
                return {}

            return higher_tf_data.get(closest_ts, {})

        # 测试几个时间戳
        test_timestamps = [
            klines_1h[100].timestamp,
            klines_1h[200].timestamp,
            klines_1h[300].timestamp,
        ]

        print(f"\n【MTF 趋势查询测试】")
        for ts in test_timestamps:
            trends = _get_closest_higher_tf_trends(ts, higher_tf_data)
            dt = datetime.fromtimestamp(ts/1000)
            if trends:
                print(f"  {dt}: {trends}")
            else:
                print(f"  {dt}: ❌ 无 MTF 数据")

        # 统计有多少 1h K 线能找到 MTF 数据
        count_with_mtf = 0
        count_without_mtf = 0

        for kline in klines_1h:
            trends = _get_closest_higher_tf_trends(kline.timestamp, higher_tf_data)
            if trends:
                count_with_mtf += 1
            else:
                count_without_mtf += 1

        print(f"\n【MTF 数据覆盖率】")
        print(f"  有 MTF 数据: {count_with_mtf}/{len(klines_1h)} ({count_with_mtf/len(klines_1h)*100:.1f}%)")
        print(f"  无 MTF 数据: {count_without_mtf}/{len(klines_1h)} ({count_without_mtf/len(klines_1h)*100:.1f}%)")

        if count_without_mtf > len(klines_1h) * 0.5:
            print(f"\n❌ MTF 数据覆盖率过低")
            print(f"   可能原因：")
            print(f"   1. 4h 数据不足")
            print(f"   2. 时间范围不匹配")
            print(f"   3. _get_closest_higher_tf_trends 逻辑问题")
        else:
            print(f"\n✅ MTF 数据覆盖率正常")

    finally:
        await data_repo.close()


if __name__ == "__main__":
    try:
        asyncio.run(diagnose_mtf_data())
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
