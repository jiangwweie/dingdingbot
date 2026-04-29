#!/usr/bin/env python3
"""
ATR 参数合理性分析

分析：
1. 回测区间 ETH 价格范围
2. 实际 ATR 值分布
3. max_atr_ratio=0.006 的实际过滤效果
"""
import asyncio
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.infrastructure.historical_data_repository import HistoricalDataRepository

DB_PATH = "data/v3_dev.db"
SYMBOL = "ETH/USDT:USDT"
TIMEFRAME = "1h"

# 时间窗口
W2023_START = 1672531200000   # 2023-01-01
W2023_END = 1704067199000     # 2023-12-31
W2024_START = 1704067200000   # 2024-01-01
W2024_END = 1735689599000     # 2024-12-31
W2025_START = 1735689600000   # 2025-01-01
W2025_END = 1767225599000     # 2025-12-31


def calculate_atr(klines, period=14):
    """计算 ATR"""
    if len(klines) < period + 1:
        return []

    tr_values = []
    for i in range(1, len(klines)):
        high = float(klines[i].high)
        low = float(klines[i].low)
        prev_close = float(klines[i-1].close)

        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close)
        )
        tr_values.append(tr)

    # 计算 ATR（简单移动平均）
    atr_values = []
    for i in range(period - 1, len(tr_values)):
        atr = sum(tr_values[i - period + 1:i + 1]) / period
        atr_values.append(atr)

    return atr_values


async def main():
    print("=" * 70)
    print("ATR 参数合理性分析")
    print("=" * 70)

    repo = HistoricalDataRepository(DB_PATH)
    await repo.initialize()

    windows = [
        ("2023", W2023_START, W2023_END),
        ("2024", W2024_START, W2024_END),
        ("2025", W2025_START, W2025_END),
    ]

    for name, start, end in windows:
        print(f"\n{'='*70}")
        print(f"{name} 年度分析")
        print("=" * 70)

        klines = await repo.get_klines(SYMBOL, TIMEFRAME, start, end)
        if not klines:
            print(f"  无数据")
            continue

        # 价格统计
        prices = [float(k.close) for k in klines]
        min_price = min(prices)
        max_price = max(prices)
        avg_price = sum(prices) / len(prices)

        print(f"\n价格统计:")
        print(f"  K线数: {len(klines)}")
        print(f"  最低价: ${min_price:.2f}")
        print(f"  最高价: ${max_price:.2f}")
        print(f"  平均价: ${avg_price:.2f}")

        # ATR 计算
        atr_values = calculate_atr(klines, period=14)
        if not atr_values:
            continue

        min_atr = min(atr_values)
        max_atr = max(atr_values)
        avg_atr = sum(atr_values) / len(atr_values)
        median_atr = sorted(atr_values)[len(atr_values) // 2]

        print(f"\nATR(14) 统计:")
        print(f"  最小值: ${min_atr:.2f}")
        print(f"  最大值: ${max_atr:.2f}")
        print(f"  平均值: ${avg_atr:.2f}")
        print(f"  中位数: ${median_atr:.2f}")

        # ATR 占价格比例
        atr_ratios = [atr / prices[i+14] for i, atr in enumerate(atr_values)]
        min_ratio = min(atr_ratios)
        max_ratio = max(atr_ratios)
        avg_ratio = sum(atr_ratios) / len(atr_ratios)
        median_ratio = sorted(atr_ratios)[len(atr_ratios) // 2]

        print(f"\nATR/Close 比例:")
        print(f"  最小值: {min_ratio:.4f} ({min_ratio*100:.2f}%)")
        print(f"  最大值: {max_ratio:.4f} ({max_ratio*100:.2f}%)")
        print(f"  平均值: {avg_ratio:.4f} ({avg_ratio*100:.2f}%)")
        print(f"  中位数: {median_ratio:.4f} ({median_ratio*100:.2f}%)")

        # max_atr_ratio=0.006 的过滤效果
        threshold = 0.006
        below_threshold = sum(1 for r in atr_ratios if r <= threshold)
        above_threshold = sum(1 for r in atr_ratios if r > threshold)

        print(f"\nmax_atr_ratio={threshold} 过滤效果:")
        print(f"  通过（ATR <= 0.6%）: {below_threshold} ({below_threshold/len(atr_ratios)*100:.1f}%)")
        print(f"  过滤（ATR > 0.6%）: {above_threshold} ({above_threshold/len(atr_ratios)*100:.1f}%)")

        # 不同阈值的过滤率
        print(f"\n不同阈值的过滤率:")
        for t in [0.004, 0.006, 0.008, 0.010, 0.015, 0.020]:
            filtered = sum(1 for r in atr_ratios if r > t)
            print(f"  {t:.3f} ({t*100:.1f}%): 过滤 {filtered}/{len(atr_ratios)} ({filtered/len(atr_ratios)*100:.1f}%)")

        # ATR 分位数
        sorted_ratios = sorted(atr_ratios)
        percentiles = [10, 25, 50, 75, 90]
        print(f"\nATR/Close 分位数:")
        for p in percentiles:
            idx = int(len(sorted_ratios) * p / 100)
            print(f"  P{p}: {sorted_ratios[idx]:.4f} ({sorted_ratios[idx]*100:.2f}%)")

    await repo.close()
    print("\n" + "=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
