#!/usr/bin/env python3
"""
ETH 1h 参数敏感性分析

目标：分析为什么不同参数组产生相同结果

关键问题：
- max_atr_ratio 是 ATR 过滤器的阈值，用于过滤高波动环境
- 如果市场 ATR 普遍较低，可能所有参数组的 max_atr_ratio 都不会触发过滤
- 需要统计实际 ATR 分布，判断参数是否在有效范围内
"""
import asyncio
import sys
from decimal import Decimal
from pathlib import Path
from datetime import datetime, timezone
import statistics

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.domain.models import KlineData
from src.infrastructure.historical_data_repository import HistoricalDataRepository


# ============================================================
# 配置参数
# ============================================================

SYMBOL = "ETH/USDT:USDT"
TIMEFRAME = "1h"

# 2025 年样本外时间范围
START_TIME = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
END_TIME = int(datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)

DB_PATH = "data/v3_dev.db"


def calculate_atr(klines: list, period: int = 14) -> list:
    """计算 ATR 序列"""
    if len(klines) < period + 1:
        return []

    atr_values = []
    for i in range(period, len(klines)):
        # 计算 True Range
        high = klines[i].high
        low = klines[i].low
        close_prev = klines[i-1].close

        tr = max(
            high - low,
            abs(high - close_prev),
            abs(low - close_prev)
        )
        atr_values.append(tr)

    return atr_values


async def main():
    """主函数"""
    print("=" * 80)
    print("ETH 1h 参数敏感性分析")
    print("=" * 80)

    print(f"\n配置:")
    print(f"  Symbol: {SYMBOL}")
    print(f"  Timeframe: {TIMEFRAME}")
    print(f"  时间范围: 2025-01-01 ~ 2025-12-31")

    # 初始化数据仓库
    print("\n初始化数据仓库...")
    data_repo = HistoricalDataRepository(DB_PATH)
    await data_repo.initialize()

    # 加载 K 线数据
    print("加载 K 线数据...")
    klines = await data_repo.get_klines(
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        start_time=START_TIME,
        end_time=END_TIME,
        limit=9000,
    )

    print(f"  加载 {len(klines)} 根 K 线")

    # 计算 ATR 分布
    print("\n计算 ATR 分布...")
    atr_values = calculate_atr(klines, period=14)

    if not atr_values:
        print("  ❌ ATR 计算失败")
        return

    # 转换为 ATR/price 比率
    atr_ratios = []
    for i, atr in enumerate(atr_values):
        idx = i + 14  # 对应的 K 线索引
        if idx < len(klines):
            atr_ratio = float(atr / klines[idx].close)
            atr_ratios.append(atr_ratio)

    # 统计分析
    print(f"\nATR/Price 比率统计:")
    print(f"  样本数: {len(atr_ratios)}")
    print(f"  最小值: {min(atr_ratios):.6f} ({min(atr_ratios)*100:.4f}%)")
    print(f"  最大值: {max(atr_ratios):.6f} ({max(atr_ratios)*100:.4f}%)")
    print(f"  平均值: {statistics.mean(atr_ratios):.6f} ({statistics.mean(atr_ratios)*100:.4f}%)")
    print(f"  中位数: {statistics.median(atr_ratios):.6f} ({statistics.median(atr_ratios)*100:.4f}%)")
    print(f"  标准差: {statistics.stdev(atr_ratios):.6f} ({statistics.stdev(atr_ratios)*100:.4f}%)")

    # 分位数
    sorted_ratios = sorted(atr_ratios)
    p25 = sorted_ratios[int(len(sorted_ratios) * 0.25)]
    p50 = sorted_ratios[int(len(sorted_ratios) * 0.50)]
    p75 = sorted_ratios[int(len(sorted_ratios) * 0.75)]
    p90 = sorted_ratios[int(len(sorted_ratios) * 0.90)]
    p95 = sorted_ratios[int(len(sorted_ratios) * 0.95)]

    print(f"\n分位数:")
    print(f"  25%: {p25:.6f} ({p25*100:.4f}%)")
    print(f"  50%: {p50:.6f} ({p50*100:.4f}%)")
    print(f"  75%: {p75:.6f} ({p75*100:.4f}%)")
    print(f"  90%: {p90:.6f} ({p90*100:.4f}%)")
    print(f"  95%: {p95:.6f} ({p95*100:.4f}%)")

    # 参数组对比
    print("\n" + "=" * 80)
    print("参数组对比分析")
    print("=" * 80)

    param_sets = [
        ("最优参数", 0.0082),
        ("邻近参数 A", 0.0085),
        ("邻近参数 B", 0.0090),
        ("邻近参数 C", 0.0088),
    ]

    for name, max_atr_ratio in param_sets:
        # 统计超过阈值的样本数
        exceed_count = sum(1 for r in atr_ratios if r > max_atr_ratio)
        exceed_pct = exceed_count / len(atr_ratios) * 100

        print(f"\n{name} (max_atr_ratio={max_atr_ratio:.4f}):")
        print(f"  ATR 超过阈值的样本数: {exceed_count}/{len(atr_ratios)} ({exceed_pct:.2f}%)")
        print(f"  ATR 低于阈值的样本数: {len(atr_ratios)-exceed_count}/{len(atr_ratios)} ({100-exceed_pct:.2f}%)")

        if exceed_pct < 5:
            print(f"  ⚠️  阈值过高，几乎不过滤任何样本")
        elif exceed_pct > 50:
            print(f"  ⚠️  阈值过低，过滤掉超过一半的样本")
        else:
            print(f"  ✅ 阈值合理，有效过滤高波动样本")

    # 参数敏感性判断
    print("\n" + "=" * 80)
    print("参数敏感性判断")
    print("=" * 80)

    # 检查参数范围是否在有效区间
    min_param = min(p[1] for p in param_sets)
    max_param = max(p[1] for p in param_sets)

    print(f"\n参数范围: {min_param:.4f} ~ {max_param:.4f}")
    print(f"ATR 分布: {min(atr_ratios):.4f} ~ {max(atr_ratios):.4f}")

    # 判断参数是否在 ATR 分布的有效范围内
    if max_param < p75:
        print("\n❌ 所有参数都低于 ATR 的 75% 分位数")
        print("   这意味着这些参数几乎不会触发 ATR 过滤")
        print("   参数变化对结果影响极小")
    elif min_param > p90:
        print("\n❌ 所有参数都高于 ATR 的 90% 分位数")
        print("   这意味着这些参数会过滤掉大部分样本")
        print("   参数变化对结果影响可能较大")
    else:
        print("\n✅ 参数范围覆盖 ATR 分布的有效区间")
        print("   参数变化应该对结果有影响")

    # 清理资源
    print("\n清理资源...")
    await data_repo.close()
    print("   资源已释放")

    print("\n脚本执行完成")


if __name__ == "__main__":
    asyncio.run(main())
