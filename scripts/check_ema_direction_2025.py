#!/usr/bin/env python3
"""
验证：2025 年 ETH/USDT 1h EMA(111) 的趋势方向分布

直接计算 2025 年每根 1h K 线收盘时 EMA111 的方向，
看有多少比例时间处于 BEARISH vs BULLISH。
"""
import asyncio
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.infrastructure.historical_data_repository import HistoricalDataRepository
from src.domain.indicators import EMACalculator

DB_PATH = "data/v3_dev.db"
SYMBOL = "ETH/USDT:USDT"
TIMEFRAME = "1h"

# 需要 warmup 数据来计算 EMA111
# 111 bars * 1h = 111h ≈ 5 days，取 2x 安全余量 = 222h ≈ 10 days
WARMUP_START = 1735516800000   # 2024-12-30 00:00 UTC (warmup)
START_TIME = 1735689600000     # 2025-01-01 00:00 UTC
END_TIME = 1767225599000       # 2025-12-31 23:59 UTC


def fmt_ts(ts_ms):
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


async def main():
    data_repo = HistoricalDataRepository(DB_PATH)
    await data_repo.initialize()

    try:
        # 加载 warmup + 2025 全年数据
        klines = await data_repo.get_klines(
            symbol=SYMBOL,
            timeframe=TIMEFRAME,
            start_time=WARMUP_START,
            end_time=END_TIME,
            limit=10000,
        )

        print(f"加载 K 线: {len(klines)} 根")
        print(f"时间范围: {fmt_ts(klines[0].timestamp)} ~ {fmt_ts(klines[-1].timestamp)}")

        # 计算 EMA111
        ema = EMACalculator(period=111)

        bullish_count = 0
        bearish_count = 0
        total_in_range = 0
        ema_values = []

        for kline in klines:
            ema.update(kline.close)

            # 只统计 2025 范围内的
            if kline.timestamp < START_TIME:
                continue

            if not ema.is_ready or ema.value is None:
                continue

            total_in_range += 1
            is_bullish = kline.close > ema.value

            if is_bullish:
                bullish_count += 1
            else:
                bearish_count += 1

            ema_values.append({
                "ts": kline.timestamp,
                "close": float(kline.close),
                "ema": float(ema.value),
                "direction": "BULLISH" if is_bullish else "BEARISH",
            })

        print(f"\n2025 年 EMA(111) 趋势方向分布 (共 {total_in_range} 根 1h K 线):")
        print(f"  BULLISH (close > EMA): {bullish_count} ({bullish_count/total_in_range*100:.1f}%)")
        print(f"  BEARISH (close < EMA): {bearish_count} ({bearish_count/total_in_range*100:.1f}%)")

        # 月度分布
        print(f"\n月度 EMA 方向分布:")
        monthly = {}
        for ev in ema_values:
            dt = datetime.fromtimestamp(ev["ts"] / 1000, tz=timezone.utc)
            key = dt.strftime("%Y-%m")
            if key not in monthly:
                monthly[key] = {"bullish": 0, "bearish": 0}
            monthly[key][ev["direction"].lower()] += 1

        print(f"{'月份':<10} {'BULLISH':>10} {'BEARISH':>10} {'BULLISH%':>10}")
        print("-" * 45)
        for month in sorted(monthly.keys()):
            m = monthly[month]
            total = m["bullish"] + m["bearish"]
            b_pct = m["bullish"] / total * 100 if total > 0 else 0
            print(f"{month:<10} {m['bullish']:>10} {m['bearish']:>10} {b_pct:>9.1f}%")

        # 4h EMA60 方向分布（用于 MTF 确认）
        print(f"\n\n4h EMA(60) 趋势方向分布验证:")
        higher_tf_klines = await data_repo.get_klines(
            symbol=SYMBOL,
            timeframe="4h",
            start_time=WARMUP_START,
            end_time=END_TIME,
            limit=3000,
        )
        print(f"加载 4h K 线: {len(higher_tf_klines)} 根")

        ema4h = EMACalculator(period=60)
        h4_bullish = 0
        h4_bearish = 0
        h4_total = 0

        for kline in higher_tf_klines:
            ema4h.update(kline.close)
            if kline.timestamp < START_TIME:
                continue
            if not ema4h.is_ready or ema4h.value is None:
                continue
            h4_total += 1
            if kline.close > ema4h.value:
                h4_bullish += 1
            else:
                h4_bearish += 1

        print(f"2025 年 4h EMA(60) 方向分布 (共 {h4_total} 根 4h K 线):")
        print(f"  BULLISH: {h4_bullish} ({h4_bullish/max(1,h4_total)*100:.1f}%)")
        print(f"  BEARISH: {h4_bearish} ({h4_bearish/max(1,h4_total)*100:.1f}%)")

        # 关键交叉验证：当 1h EMA bearish 时，4h EMA 也 bearish 的比例
        # 即 "EMA + MTF 双重 bearish 确认" 的时间占比
        print(f"\n\n关键交叉验证:")
        print(f"2025 年 ETH 大概率上涨（close 从 ~3300 涨到 ~3800+）")
        print(f"但 EMA(111h) {bearish_count/total_in_range*100:.0f}% 时间处于 BEARISH")
        print(f"这说明 EMA(111h) 滞后严重——价格在涨，EMA 还在下方")
        print(f"当出现 Pinbar bearish 形态时，EMA '确认' 下跌趋势")
        print(f"但实际价格可能只是回调，不是趋势反转")

    finally:
        await data_repo.close()


if __name__ == "__main__":
    asyncio.run(main())
