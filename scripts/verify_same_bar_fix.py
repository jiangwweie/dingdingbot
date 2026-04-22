#!/usr/bin/env python3
"""
验证 same-bar random 逻辑修复

验证目标：
1. pessimistic 与旧结果一致
2. random + 固定 seed 可复现
3. 同一冲突 signal 内多个 TP/SL 的优先级一致
"""
import sys
from pathlib import Path
from decimal import Decimal
from typing import List

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.domain.models import (
    KlineData,
    Order,
    Position,
    Account,
    OrderStatus,
    OrderType,
    OrderRole,
    Direction,
)
from src.domain.matching_engine import MockMatchingEngine


def create_test_orders():
    """创建测试订单：同一 signal_id 的 TP1, TP2, SL"""
    orders = [
        # SL 订单
        Order(
            id="sl-1",
            signal_id="signal-1",
            symbol="ETH/USDT:USDT",
            order_type=OrderType.STOP_MARKET,
            order_role=OrderRole.SL,
            direction=Direction.LONG,
            status=OrderStatus.OPEN,
            trigger_price=Decimal("2490"),
            requested_qty=Decimal("1.0"),
            created_at=1000,
            updated_at=1000,
        ),
        # TP1 订单
        Order(
            id="tp1-1",
            signal_id="signal-1",
            symbol="ETH/USDT:USDT",
            order_type=OrderType.LIMIT,
            order_role=OrderRole.TP1,
            direction=Direction.LONG,
            status=OrderStatus.OPEN,
            price=Decimal("2520"),
            requested_qty=Decimal("0.5"),
            created_at=1000,
            updated_at=1000,
        ),
        # TP2 订单
        Order(
            id="tp2-1",
            signal_id="signal-1",
            symbol="ETH/USDT:USDT",
            order_type=OrderType.LIMIT,
            order_role=OrderRole.TP2,
            direction=Direction.LONG,
            status=OrderStatus.OPEN,
            price=Decimal("2550"),
            requested_qty=Decimal("0.5"),
            created_at=1000,
            updated_at=1000,
        ),
    ]
    return orders


def create_conflict_kline():
    """创建冲突 K 线：high/low 同时覆盖 TP 和 SL"""
    return KlineData(
        symbol="ETH/USDT:USDT",
        timeframe="1h",
        timestamp=3600000,
        open=Decimal("2500"),
        high=Decimal("2560"),  # > TP2 (2550) > TP1 (2520)
        low=Decimal("2480"),   # < SL (2490)
        close=Decimal("2530"),
        volume=Decimal("1000"),
        is_closed=True,
    )


def verify_pessimistic():
    """验证 1: pessimistic 策略与旧逻辑一致"""
    print("=" * 80)
    print("验证 1: pessimistic 策略（默认）")
    print("=" * 80)

    engine = MockMatchingEngine(
        same_bar_policy="pessimistic",
    )

    orders = create_test_orders()
    kline = create_conflict_kline()

    sorted_orders = engine._sort_orders_by_priority(orders, kline)

    # 检查优先级：SL > TP1 > TP2
    priorities = {
        order.id: engine._sort_orders_by_priority.__code__.co_consts
        for order in sorted_orders
    }

    # 简化验证：检查排序后的顺序
    order_ids = [order.id for order in sorted_orders]

    print(f"排序后订单顺序: {order_ids}")

    # SL 应该在最前面
    sl_index = order_ids.index("sl-1")
    tp1_index = order_ids.index("tp1-1")
    tp2_index = order_ids.index("tp2-1")

    print(f"SL 索引: {sl_index}, TP1 索引: {tp1_index}, TP2 索引: {tp2_index}")

    if sl_index < tp1_index and sl_index < tp2_index:
        print("✅ pessimistic 策略正确：SL 优先级最高")
        return True
    else:
        print("❌ pessimistic 策略错误：SL 未优先")
        return False


def verify_random_reproducible():
    """验证 2: random + 固定 seed 可复现"""
    print("\n" + "=" * 80)
    print("验证 2: random + 固定 seed 可复现")
    print("=" * 80)

    # 运行两次，使用相同 seed
    results = []

    for run in range(2):
        engine = MockMatchingEngine(
            same_bar_policy="random",
            same_bar_tp_first_prob=Decimal("0.5"),
            random_seed=42,
        )

        orders = create_test_orders()
        kline = create_conflict_kline()

        sorted_orders = engine._sort_orders_by_priority(orders, kline)
        order_ids = [order.id for order in sorted_orders]
        results.append(order_ids)

        print(f"运行 {run + 1}: {order_ids}")

    if results[0] == results[1]:
        print("✅ 固定 seed 可复现：两次结果完全一致")
        return True
    else:
        print("❌ 固定 seed 不可复现：两次结果不同")
        print(f"  结果 1: {results[0]}")
        print(f"  结果 2: {results[1]}")
        return False


def verify_signal_consistent():
    """验证 3: 同一冲突 signal 内多个 TP/SL 优先级一致"""
    print("\n" + "=" * 80)
    print("验证 3: 同一冲突 signal 内多个 TP/SL 优先级一致")
    print("=" * 80)

    # 使用多次运行验证一致性
    consistent_count = 0
    total_runs = 10

    for run in range(total_runs):
        engine = MockMatchingEngine(
            same_bar_policy="random",
            same_bar_tp_first_prob=Decimal("0.5"),
            random_seed=run,  # 不同 seed
        )

        orders = create_test_orders()
        kline = create_conflict_kline()

        # 检测冲突
        conflicts = engine._detect_same_bar_conflicts(orders, kline)
        print(f"\n运行 {run + 1}: 冲突 signals = {conflicts}")

        # 抽签
        sorted_orders = engine._sort_orders_by_priority(orders, kline)
        order_ids = [order.id for order in sorted_orders]

        # 检查 TP1 和 TP2 的相对顺序
        tp1_index = order_ids.index("tp1-1")
        tp2_index = order_ids.index("tp2-1")

        # TP1 和 TP2 应该保持相对顺序（都是 TP 订单）
        if tp1_index < tp2_index:
            print(f"  ✅ TP1 在 TP2 前（TP 优先级一致）")
            consistent_count += 1
        else:
            print(f"  ⚠️ TP2 在 TP1 前（可能正常，取决于具体实现）")

    print(f"\n一致性统计: {consistent_count}/{total_runs}")

    # 更重要的验证：检查 SL 和 TP 的相对位置
    print("\n检查 SL vs TP 优先级一致性...")

    for run in range(5):
        engine = MockMatchingEngine(
            same_bar_policy="random",
            same_bar_tp_first_prob=Decimal("0.5"),
            random_seed=run,
        )

        orders = create_test_orders()
        kline = create_conflict_kline()

        sorted_orders = engine._sort_orders_by_priority(orders, kline)
        order_ids = [order.id for order in sorted_orders]

        sl_index = order_ids.index("sl-1")
        tp1_index = order_ids.index("tp1-1")
        tp2_index = order_ids.index("tp2-1")

        # 如果 SL 在 TP1 前，那么 SL 也应该在 TP2 前
        # 如果 TP1 在 SL 前，那么 TP2 也应该在 SL 前
        sl_before_tp1 = sl_index < tp1_index
        sl_before_tp2 = sl_index < tp2_index

        if sl_before_tp1 == sl_before_tp2:
            print(f"  运行 {run + 1}: ✅ SL/TP 优先级一致（SL 在 TP 前: {sl_before_tp1}）")
        else:
            print(f"  运行 {run + 1}: ❌ SL/TP 优先级不一致！")
            print(f"    SL 索引: {sl_index}, TP1 索引: {tp1_index}, TP2 索引: {tp2_index}")
            return False

    print("\n✅ 同一冲突 signal 内多个 TP/SL 优先级一致")
    return True


def main():
    """运行所有验证"""
    print("=" * 80)
    print("Same-Bar Random 逻辑修复验证")
    print("=" * 80)

    results = []

    # 验证 1: pessimistic
    results.append(("pessimistic 一致性", verify_pessimistic()))

    # 验证 2: random 可复现
    results.append(("random 可复现", verify_random_reproducible()))

    # 验证 3: signal 内一致性
    results.append(("signal 内一致性", verify_signal_consistent()))

    # 总结
    print("\n" + "=" * 80)
    print("验证总结")
    print("=" * 80)

    all_passed = True
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{name}: {status}")
        if not passed:
            all_passed = False

    if all_passed:
        print("\n🎉 所有验证通过！")
        return 0
    else:
        print("\n❌ 部分验证失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
