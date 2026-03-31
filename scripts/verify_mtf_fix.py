#!/usr/bin/env python3
"""
验证脚本：演示 MTF K 线闭合判断 Bug 的修复效果

场景：
- 当前时间：20:15（15m K 线闭合触发信号）
- 需要 1h 趋势数据
- _kline_history 有 [16:00, 17:00, 18:00, 19:00, 20:00] 五根 1h K 线

修复前行为：
- 错误地返回索引 4（20:00 K 线），但这根 K 线还没闭合！
- 导致 MTF 过滤器使用错误数据

修复后行为：
- 正确返回索引 3（19:00 K 线），这根 K 线已在 20:00 闭合
- MTF 过滤器使用正确的已闭合数据
"""

import sys
from decimal import Decimal
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.domain.timeframe_utils import get_last_closed_kline_index, parse_timeframe_to_ms
from src.domain.models import KlineData, TrendDirection


def hour_to_ms(hour: int) -> int:
    """将小时转换为毫秒时间戳（简化测试用）。"""
    base = 1700000000000  # 任意基准时间戳
    return base + (hour * 60 * 60 * 1000)


def minute_to_ms(hour: int, minute: int) -> int:
    """将小时：分钟转换为毫秒时间戳。"""
    base = 1700000000000
    return base + (hour * 60 * 60 * 1000) + (minute * 60 * 1000)


def create_kline(timestamp: int, close: str = "50000") -> KlineData:
    """创建测试 K 线数据。"""
    return KlineData(
        symbol="BTC/USDT:USDT",
        timeframe="1h",
        timestamp=timestamp,
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        volume=Decimal("1000"),
        is_closed=True,
    )


def print_kline_info(klines: list, idx: int, label: str):
    """打印 K 线信息。"""
    if idx < 0:
        print(f"  {label}: 无可用数据 (idx=-1)")
        return

    if idx >= len(klines):
        print(f"  {label}: 索引越界 (idx={idx})")
        return

    kline = klines[idx]
    hour = (kline.timestamp - 1700000000000) // (60 * 60 * 1000)
    end_hour = hour + 1
    print(f"  {label}: idx={idx}, 时间={hour:02d}:00, 闭合时间={end_hour:02d}:00")


def main():
    print("=" * 70)
    print("MTF K 线闭合判断 Bug 验证脚本")
    print("=" * 70)

    # 场景：20:15 触发 15m 信号
    current_ts = minute_to_ms(20, 15)
    current_hour = (current_ts - 1700000000000) // (60 * 60 * 1000)
    current_min = ((current_ts - 1700000000000) % (60 * 60 * 1000)) // (60 * 1000)

    print(f"\n场景设置:")
    print(f"  当前时间：{current_hour:02d}:{current_min:02d} (15m K 线闭合)")
    print(f"  需要数据：1h 趋势 (MTF)")

    # 准备 1h K 线数据：[16:00, 17:00, 18:00, 19:00, 20:00]
    klines = [
        create_kline(hour_to_ms(16), "50000"),  # 16:00, 闭合于 17:00
        create_kline(hour_to_ms(17), "51000"),  # 17:00, 闭合于 18:00
        create_kline(hour_to_ms(18), "52000"),  # 18:00, 闭合于 19:00
        create_kline(hour_to_ms(19), "53000"),  # 19:00, 闭合于 20:00
        create_kline(hour_to_ms(20), "54000"),  # 20:00, 闭合于 21:00 (未闭合!)
    ]

    print(f"\n  1h K 线数据:")
    for i, k in enumerate(klines):
        hour = (k.timestamp - 1700000000000) // (60 * 60 * 1000)
        status = "未闭合!" if hour == 20 else "已闭合"
        print(f"    [{i}] {hour:02d}:00 (闭合于 {hour+1:02d}:00) - {status}")

    # 计算应返回的索引
    period_ms = parse_timeframe_to_ms("1h")

    print(f"\n分析逻辑:")
    print(f"  1h 周期 = {period_ms / 1000 / 60 / 60} 小时")
    print(f"  20:00 K 线闭合时间 = 21:00")
    print(f"  当前时间 20:15 < 21:00，所以 20:00 K 线未闭合")
    print(f"  19:00 K 线闭合时间 = 20:00")
    print(f"  当前时间 20:15 >= 20:00，所以 19:00 K 线已闭合")

    # 调用修复后的函数
    idx = get_last_closed_kline_index(klines, current_ts, "1h")

    print(f"\n修复后结果:")
    print_kline_info(klines, idx, "返回索引")

    # 验证
    print(f"\n验证:")
    if idx == 3:
        print(f"  正确！返回索引 3 (19:00 K 线)，这根 K 线已在 20:00 闭合")
        print(f"  MTF 过滤器可以正确使用这根 K 线计算趋势")
        return 0
    elif idx == 4:
        print(f"  错误！返回索引 4 (20:00 K 线)，但这根 K 线还没闭合!")
        print(f"  这会导致 MTF 过滤器报告 higher_tf_data_unavailable")
        return 1
    else:
        print(f"  意外结果！idx={idx}")
        return 1


def show_old_bug_behavior():
    """演示旧代码的错误行为。"""
    print("\n" + "=" * 70)
    print("旧代码错误行为演示")
    print("=" * 70)

    # 旧代码逻辑（简化版）
    def old_get_last_closed_kline_index(klines, current_timestamp, timeframe):
        period_ms = parse_timeframe_to_ms(timeframe)
        current_period = current_timestamp // period_ms

        best_index = -1
        for i, kline in enumerate(klines):
            kline_period = kline.timestamp // period_ms

            if kline_period < current_period:
                best_index = i
            elif kline_period == current_period:
                if kline.timestamp == current_timestamp:
                    break
                else:
                    # 错误！没有检查是否已闭合
                    best_index = i
                    break
            else:
                break
        return best_index

    current_ts = minute_to_ms(20, 15)
    klines = [
        create_kline(hour_to_ms(16), "50000"),
        create_kline(hour_to_ms(17), "51000"),
        create_kline(hour_to_ms(18), "52000"),
        create_kline(hour_to_ms(19), "53000"),
        create_kline(hour_to_ms(20), "54000"),
    ]

    old_idx = old_get_last_closed_kline_index(klines, current_ts, "1h")
    print(f"旧代码返回：idx={old_idx}")
    print_kline_info(klines, old_idx, "错误地返回")
    print(f"\n问题：20:00 开始的 K 线在 20:15 时还没闭合，但旧代码错误地认为它可用!")


if __name__ == "__main__":
    show_old_bug_behavior()
    print()
    exit_code = main()
    print("\n" + "=" * 70)
    if exit_code == 0:
        print("修复验证通过!")
    else:
        print("修复验证失败!")
    print("=" * 70)
    sys.exit(exit_code)
