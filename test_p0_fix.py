"""
P0 修复验证脚本 - 验证订单状态推进契约统一

验证场景：
1. OPEN → PARTIALLY_FILLED
2. PARTIALLY_FILLED → FILLED
3. OPEN/PARTIALLY_FILLED → CANCELED
"""
import asyncio
import tempfile
import os
from decimal import Decimal

from src.application.order_lifecycle_service import OrderLifecycleService
from src.domain.models import (
    Order,
    OrderStatus,
    OrderType,
    OrderRole,
    Direction,
    OrderStrategy,
)
from src.infrastructure.order_repository import OrderRepository


async def test_open_to_partially_filled():
    """测试 OPEN → PARTIALLY_FILLED"""
    print("\n=== 测试场景 1: OPEN → PARTIALLY_FILLED ===")

    # 创建临时数据库
    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    try:
        # 初始化服务
        repository = OrderRepository(db_path)
        await repository.initialize()
        service = OrderLifecycleService(repository)
        await service.start()

        # 创建订单
        strategy = OrderStrategy(
            id="strategy_001",
            name="test_strategy",
        )

        order = await service.create_order(
            strategy=strategy,
            signal_id="sig_test_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            total_qty=Decimal('1.0'),
            initial_sl_rr=Decimal('-1.0'),
            tp_targets=[Decimal('1.5')],
        )

        # 提交并确认
        await service.submit_order(order.id)
        await service.confirm_order(order.id)

        print(f"初始状态: {order.status}")

        # 模拟交易所推送部分成交（P0 修复：使用 Order 对象）
        exchange_order = Order(
            id=order.id,
            signal_id=order.signal_id,
            exchange_order_id="binance_123",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.0'),
            filled_qty=Decimal('0.5'),
            average_exec_price=Decimal('65000'),
            status=OrderStatus.PARTIALLY_FILLED,
            created_at=order.created_at,
            updated_at=order.updated_at,
        )

        updated = await service.update_order_from_exchange(exchange_order)

        print(f"更新后状态: {updated.status}")
        print(f"已成交数量: {updated.filled_qty}")

        assert updated.status == OrderStatus.PARTIALLY_FILLED, f"期望 PARTIALLY_FILLED，实际 {updated.status}"
        assert updated.filled_qty == Decimal('0.5'), f"期望 0.5，实际 {updated.filled_qty}"

        print("✅ 测试通过: OPEN → PARTIALLY_FILLED")

    finally:
        os.unlink(db_path)


async def test_partially_filled_to_filled():
    """测试 PARTIALLY_FILLED → FILLED"""
    print("\n=== 测试场景 2: PARTIALLY_FILLED → FILLED ===")

    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    try:
        repository = OrderRepository(db_path)
        await repository.initialize()
        service = OrderLifecycleService(repository)
        await service.start()

        strategy = OrderStrategy(
            id="strategy_002",
            name="test_strategy",
        )

        order = await service.create_order(
            strategy=strategy,
            signal_id="sig_test_002",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            total_qty=Decimal('1.0'),
            initial_sl_rr=Decimal('-1.0'),
            tp_targets=[Decimal('1.5')],
        )

        await service.submit_order(order.id)
        await service.confirm_order(order.id)

        # 先部分成交
        partial_order = Order(
            id=order.id,
            signal_id=order.signal_id,
            exchange_order_id="binance_456",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.0'),
            filled_qty=Decimal('0.5'),
            average_exec_price=Decimal('65000'),
            status=OrderStatus.PARTIALLY_FILLED,
            created_at=order.created_at,
            updated_at=order.updated_at,
        )

        updated = await service.update_order_from_exchange(partial_order)
        print(f"部分成交状态: {updated.status}")

        # 完全成交
        filled_order = Order(
            id=order.id,
            signal_id=order.signal_id,
            exchange_order_id="binance_456",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.0'),
            filled_qty=Decimal('1.0'),
            average_exec_price=Decimal('65000'),
            status=OrderStatus.FILLED,
            created_at=order.created_at,
            updated_at=order.updated_at,
        )

        updated = await service.update_order_from_exchange(filled_order)

        print(f"更新后状态: {updated.status}")
        print(f"已成交数量: {updated.filled_qty}")

        assert updated.status == OrderStatus.FILLED, f"期望 FILLED，实际 {updated.status}"
        assert updated.filled_qty == Decimal('1.0'), f"期望 1.0，实际 {updated.filled_qty}"

        print("✅ 测试通过: PARTIALLY_FILLED → FILLED")

    finally:
        os.unlink(db_path)


async def test_open_to_canceled():
    """测试 OPEN → CANCELED"""
    print("\n=== 测试场景 3: OPEN → CANCELED ===")

    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    try:
        repository = OrderRepository(db_path)
        await repository.initialize()
        service = OrderLifecycleService(repository)
        await service.start()

        strategy = OrderStrategy(
            id="strategy_002",
            name="test_strategy",
        )

        order = await service.create_order(
            strategy=strategy,
            signal_id="sig_test_003",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            total_qty=Decimal('1.0'),
            initial_sl_rr=Decimal('-1.0'),
            tp_targets=[Decimal('1.5')],
        )

        await service.submit_order(order.id)
        await service.confirm_order(order.id)

        print(f"初始状态: {order.status}")

        # 模拟交易所推送取消
        canceled_order = Order(
            id=order.id,
            signal_id=order.signal_id,
            exchange_order_id="binance_789",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.0'),
            filled_qty=Decimal('0'),
            status=OrderStatus.CANCELED,
            created_at=order.created_at,
            updated_at=order.updated_at,
        )

        updated = await service.update_order_from_exchange(canceled_order)

        print(f"更新后状态: {updated.status}")

        assert updated.status == OrderStatus.CANCELED, f"期望 CANCELED，实际 {updated.status}"

        print("✅ 测试通过: OPEN → CANCELED")

    finally:
        os.unlink(db_path)


async def main():
    """运行所有验证测试"""
    print("=" * 60)
    print("P0 修复验证 - 订单状态推进契约统一")
    print("=" * 60)

    try:
        await test_open_to_partially_filled()
        await test_partially_filled_to_filled()
        await test_open_to_canceled()

        print("\n" + "=" * 60)
        print("✅ 所有测试通过！契约统一修复成功")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
