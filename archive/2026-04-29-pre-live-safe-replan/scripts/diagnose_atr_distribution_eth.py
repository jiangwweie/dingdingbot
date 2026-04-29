#!/usr/bin/env python3
"""
诊断 ETH 1h 的 ATR/Price 分布

目标：
1. 检查 ETH 的 ATR/Price 分布
2. 确认 max_atr_ratio=0.008-0.012 是否过于严格
"""
import asyncio
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.infrastructure.historical_data_repository import HistoricalDataRepository


async def diagnose_atr_distribution():
    """诊断 ETH 的 ATR/Price 分布"""

    print("=" * 80)
    print("诊断 ETH 1h ATR/Price 分布")
    print("=" * 80)

    # 数据仓库
    DB_PATH = "data/v3_dev.db"
    data_repo = HistoricalDataRepository(DB_PATH)
    await data_repo.initialize()

    try:
        # 时间范围：2024-01-01 ~ 2024-12-31 (1 年)
        start_ts = int(datetime(2024, 1, 1).timestamp() * 1000)
        end_ts = int(datetime(2024, 12, 31).timestamp() * 1000)

        # 获取 K 线数据
        klines = await data_repo.get_klines(
            symbol="ETH/USDT:USDT",
            timeframe="1h",
            start_time=start_ts,
            limit=10000,
        )

        print(f"\n【数据加载】")
        print(f"  总 K 线数: {len(klines)}")

        # 计算 ATR（14 周期）
        period = 14
        tr_values = []
        atr_values = []
        atr_pct_values = []

        for i, kline in enumerate(klines):
            # 计算 True Range
            if i > 0:
                prev_close = klines[i-1].close
                tr = max(
                    kline.high - kline.low,
                    abs(kline.high - prev_close),
                    abs(kline.low - prev_close)
                )
            else:
                tr = kline.high - kline.low

            tr_values.append(tr)

            # 计算 ATR（Wilder's smoothing）
            if len(tr_values) == period:
                atr = sum(tr_values) / period
                atr_values.append(atr)
                atr_pct = atr / kline.close
                atr_pct_values.append(float(atr_pct))
            elif len(tr_values) > period:
                atr = (atr_values[-1] * (period - 1) + tr) / period
                atr_values.append(atr)
                atr_pct = atr / kline.close
                atr_pct_values.append(float(atr_pct))

        print(f"  ATR 计算完成: {len(atr_values)} 个值")

        # 统计分布
        print(f"\n【ATR/Price 分布统计】")
        print(f"  最小值: {min(atr_pct_values):.4f} ({min(atr_pct_values)*100:.2f}%)")
        print(f"  最大值: {max(atr_pct_values):.4f} ({max(atr_pct_values)*100:.2f}%)")
        print(f"  平均值: {sum(atr_pct_values)/len(atr_pct_values):.4f} ({sum(atr_pct_values)/len(atr_pct_values)*100:.2f}%)")

        # 分位数
        sorted_values = sorted(atr_pct_values)
        p25 = sorted_values[int(len(sorted_values) * 0.25)]
        p50 = sorted_values[int(len(sorted_values) * 0.50)]
        p75 = sorted_values[int(len(sorted_values) * 0.75)]
        p90 = sorted_values[int(len(sorted_values) * 0.90)]
        p95 = sorted_values[int(len(sorted_values) * 0.95)]

        print(f"\n【分位数】")
        print(f"  25%: {p25:.4f} ({p25*100:.2f}%)")
        print(f"  50%: {p50:.4f} ({p50*100:.2f}%)")
        print(f"  75%: {p75:.4f} ({p75*100:.2f}%)")
        print(f"  90%: {p90:.4f} ({p90*100:.2f}%)")
        print(f"  95%: {p95:.4f} ({p95*100:.2f}%)")

        # 检查 Optuna 搜索范围
        print(f"\n【Optuna 搜索范围分析】")
        threshold_008 = 0.008
        threshold_010 = 0.010
        threshold_012 = 0.012

        count_below_008 = sum(1 for v in atr_pct_values if v < threshold_008)
        count_below_010 = sum(1 for v in atr_pct_values if v < threshold_010)
        count_below_012 = sum(1 for v in atr_pct_values if v < threshold_012)

        print(f"  max_atr_ratio < 0.008 (0.8%): {count_below_008}/{len(atr_pct_values)} ({count_below_008/len(atr_pct_values)*100:.1f}%)")
        print(f"  max_atr_ratio < 0.010 (1.0%): {count_below_010}/{len(atr_pct_values)} ({count_below_010/len(atr_pct_values)*100:.1f}%)")
        print(f"  max_atr_ratio < 0.012 (1.2%): {count_below_012}/{len(atr_pct_values)} ({count_below_012/len(atr_pct_values)*100:.1f}%)")

        # 结论
        print(f"\n【诊断结论】")
        if count_below_012 < len(atr_pct_values) * 0.1:
            print(f"  ❌ max_atr_ratio=0.008-0.012 过于严格")
            print(f"     - 只有 {count_below_012/len(atr_pct_values)*100:.1f}% 的 K 线通过过滤")
            print(f"     - 建议：增大 max_atr_ratio 到 {p90:.4f} (90% 分位数)")
        elif count_below_012 < len(atr_pct_values) * 0.3:
            print(f"  ⚠️  max_atr_ratio=0.008-0.012 较为严格")
            print(f"     - 只有 {count_below_012/len(atr_pct_values)*100:.1f}% 的 K 线通过过滤")
            print(f"     - 建议：增大 max_atr_ratio 到 {p75:.4f} (75% 分位数)")
        else:
            print(f"  ✅ max_atr_ratio=0.008-0.012 范围合理")
            print(f"     - {count_below_012/len(atr_pct_values)*100:.1f}% 的 K 线通过过滤")

    finally:
        await data_repo.close()


if __name__ == "__main__":
    try:
        asyncio.run(diagnose_atr_distribution())
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
