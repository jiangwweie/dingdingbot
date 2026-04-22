"""
P0 修复验证脚本（第二步） - 验证交易所订单 ID -> 本地订单 ID 映射闭环

关键验证：
1. 本地订单 ID 与交易所订单 ID 不同
2. WS 推送使用交易所订单 ID
3. 状态推进能正确映射到本地订单

验证场景：
1. OPEN → PARTIALLY_FILLED
2. PARTIALLY_FILLED → FILLED
3. OPEN → CANCELED
"""
import asyncio
import tempfile
import os
import uuid
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
    """测试 OPEN → PARTIALLY_FILLED（真实映射场景）"""
    print("\n=== 测试场景 1: OPEN → PARTIALLY_FILLED（真实映射） ===")

    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    try:
        repository = OrderRepository(db_path)
        await repository.initialize()
        service = OrderLifecycleService(repository)
        await service.start()

        # 1. 创建本地订单（生成 UUID 作为 order.id）
        strategy = OrderStrategy(
            id="strategy_001",
            name="test_strategy",
        )

        local_order = await service.create_order(
            strategy=strategy,
            signal_id="sig_test_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            total_qty=Decimal('1.0'),
            initial_sl_rr=Decimal('-1.0'),
            tp_targets=[Decimal('1.5')],
        )

        print(f"✅ 本地订单创建成功:")
        print(f"   本地订单 ID: {local_order.id}")
        print(f"   exchange_order_id: {local_order.exchange_order_id}")

        # 2. 提交订单到交易所（获得 exchange_order_id）
        exchange_order_id = f"binance_{uuid.uuid4().hex[:8]}"  # 模拟交易所订单 ID
        await service.submit_order(local_order.id, exchange_order_id=exchange_order_id)
        await service.confirm_order(local_order.id)

        print(f"✅ 订单已提交到交易所:")
        print(f"   exchange_order_id: {exchange_order_id}")

        # 验证本地订单 ID 与交易所订单 ID 不同
        assert local_order.id != exchange_order_id, "本地订单 ID 与交易所订单 ID 不应相同"

        # 3. 模拟 WS 推送（使用交易所订单 ID，而非本地订单 ID）
        # P0 修复：真实场景中，ExchangeGateway 推送的 Order.id 是交易所订单 ID
        ws_pushed_order = Order(
            id=exchange_order_id,  # ← 交易所订单 ID（不是本地订单 ID）
            signal_id="sig_test_001",
            exchange_order_id=exchange_order_id,
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.0'),
            filled_qty=Decimal('0.5'),
            average_exec_price=Decimal('65000'),
            status=OrderStatus.PARTIALLY_FILLED,
            created_at=local_order.created_at,
            updated_at=local_order.updated_at,
        )

        print(f"\n📥 模拟 WS 推送:")
        print(f"   推送的 Order.id: {ws_pushed_order.id} (交易所订单 ID)")
        print(f"   推送的 exchange_order_id: {ws_pushed_order.exchange_order_id}")

        # 4. 执行状态推进
        updated = await service.update_order_from_exchange(ws_pushed_order)

        print(f"\n✅ 状态推进成功:")
        print(f"   本地订单 ID: {updated.id}")
        print(f"   状态: {updated.status}")
        print(f"   已成交数量: {updated.filled_qty}")

        # 验证
        assert updated.id == local_order.id, f"期望本地订单 ID={local_order.id}，实际={updated.id}"
        assert updated.status == OrderStatus.PARTIALLY_FILLED, f"期望 PARTIALLY_FILLED，实际 {updated.status}"
        assert updated.filled_qty == Decimal('0.5'), f"期望 0.5，实际 {updated.filled_qty}"

        print("✅ 测试通过: OPEN → PARTIALLY_FILLED（真实映射验证成功）")

    finally:
        os.unlink(db_path)


async def test_partially_filled_to_filled():
    """测试 PARTIALLY_FILLED → FILLED（真实映射场景）"""
    print("\n=== 测试场景 2: PARTIALLY_FILLED → FILLED（真实映射） ===")

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

        local_order = await service.create_order(
            strategy=strategy,
            signal_id="sig_test_002",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            total_qty=Decimal('1.0'),
            initial_sl_rr=Decimal('-1.0'),
            tp_targets=[Decimal('1.5')],
        )

        exchange_order_id = f"binance_{uuid.uuid4().hex[:8]}"
        await service.submit_order(local_order.id, exchange_order_id=exchange_order_id)
        await service.confirm_order(local_order.id)

        print(f"✅ 本地订单 ID: {local_order.id}")
        print(f"✅ 交易所订单 ID: {exchange_order_id}")

        # 先部分成交
        partial_order = Order(
            id=exchange_order_id,  # ← 交易所订单 ID
            signal_id="sig_test_002",
            exchange_order_id=exchange_order_id,
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.0'),
            filled_qty=Decimal('0.5'),
            average_exec_price=Decimal('65000'),
            status=OrderStatus.PARTIALLY_FILLED,
            created_at=local_order.created_at,
            updated_at=local_order.updated_at,
        )

        updated = await service.update_order_from_exchange(partial_order)
        print(f"✅ 部分成交状态: {updated.status}")

        # 完全成交
        filled_order = Order(
            id=exchange_order_id,  # ← 交易所订单 ID
            signal_id="sig_test_002",
            exchange_order_id=exchange_order_id,
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.0'),
            filled_qty=Decimal('1.0'),
            average_exec_price=Decimal('65000'),
            status=OrderStatus.FILLED,
            created_at=local_order.created_at,
            updated_at=local_order.updated_at,
        )

        updated = await service.update_order_from_exchange(filled_order)

        print(f"✅ 完全成交状态: {updated.status}")
        print(f"✅ 已成交数量: {updated.filled_qty}")

        assert updated.id == local_order.id
        assert updated.status == OrderStatus.FILLED, f"期望 FILLED，实际 {updated.status}"
        assert updated.filled_qty == Decimal('1.0'), f"期望 1.0，实际 {updated.filled_qty}"

        print("✅ 测试通过: PARTIALLY_FILLED → FILLED（真实映射验证成功）")

    finally:
        os.unlink(db_path)


async def test_open_to_canceled():
    """测试 OPEN → CANCELED（真实映射场景）"""
    print("\n=== 测试场景 3: OPEN → CANCELED（真实映射） ===")

    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    try:
        repository = OrderRepository(db_path)
        await repository.initialize()
        service = OrderLifecycleService(repository)
        await service.start()

        strategy = OrderStrategy(
            id="strategy_003",
            name="test_strategy",
        )

        local_order = await service.create_order(
            strategy=strategy,
            signal_id="sig_test_003",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            total_qty=Decimal('1.0'),
            initial_sl_rr=Decimal('-1.0'),
            tp_targets=[Decimal('1.5')],
        )

        exchange_order_id = f"binance_{uuid.uuid4().hex[:8]}"
        await service.submit_order(local_order.id, exchange_order_id=exchange_order_id)
        await service.confirm_order(local_order.id)

        print(f"✅ 本地订单 ID: {local_order.id}")
        print(f"✅ 交易所订单 ID: {exchange_order_id}")

        # 模拟交易所推送取消
        canceled_order = Order(
            id=exchange_order_id,  # ← 交易所订单 ID
            signal_id="sig_test_003",
            exchange_order_id=exchange_order_id,
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.0'),
            filled_qty=Decimal('0'),
            status=OrderStatus.CANCELED,
            created_at=local_order.created_at,
            updated_at=local_order.updated_at,
        )

        updated = await service.update_order_from_exchange(canceled_order)

        print(f"✅ 取消状态: {updated.status}")

        assert updated.id == local_order.id
        assert updated.status == OrderStatus.CANCELED, f"期望 CANCELED，实际 {updated.status}"

        print("✅ 测试通过: OPEN → CANCELED（真实映射验证成功）")

    finally:
        os.unlink(db_path)


async def test_exchange_order_id_not_found():
    """测试交易所订单 ID 不存在的情况"""
    print("\n=== 测试场景 4: 交易所订单 ID 不存在 ===")

    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    try:
        repository = OrderRepository(db_path)
        await repository.initialize()
        service = OrderLifecycleService(repository)
        await service.start()

        # 模拟 WS 推送一个不存在的交易所订单 ID
        fake_exchange_order_id = f"binance_nonexistent_{uuid.uuid4().hex[:8]}"

        ws_pushed_order = Order(
            id=fake_exchange_order_id,
            signal_id="sig_fake",
            exchange_order_id=fake_exchange_order_id,
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.0'),
            filled_qty=Decimal('0'),
            status=OrderStatus.OPEN,
            created_at=int(asyncio.get_event_loop().time() * 1000),
            updated_at=int(asyncio.get_event_loop().time() * 1000),
        )

        print(f"📥 模拟 WS 推送不存在的交易所订单 ID: {fake_exchange_order_id}")

        try:
            await service.update_order_from_exchange(ws_pushed_order)
            print("❌ 测试失败：应该抛出 ValueError")
            assert False, "应该抛出 ValueError"
        except ValueError as e:
            print(f"✅ 正确抛出异常: {e}")
            assert "订单不存在" in str(e)
            print("✅ 测试通过: 交易所订单 ID 不存在时正确处理")

    finally:
        os.unlink(db_path)


async def main():
    """运行所有验证测试"""
    print("=" * 70)
    print("P0 修复验证（第二步） - 交易所订单 ID -> 本地订单 ID 映射闭环")
    print("=" * 70)

    try:
        await test_open_to_partially_filled()
        await test_partially_filled_to_filled()
        await test_open_to_canceled()
        await test_exchange_order_id_not_found()

        print("\n" + "=" * 70)
        print("✅ 所有测试通过！交易所订单 ID -> 本地订单 ID 映射闭环成功")
        print("=" * 70)

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
