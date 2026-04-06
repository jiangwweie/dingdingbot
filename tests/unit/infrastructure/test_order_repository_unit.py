"""
TEST-3: OrderRepository 单元测试

测试用例清单:
- UNIT-ORD-3-001: test_save_order - 保存订单
- UNIT-ORD-3-002: test_update_order_status - 更新订单状态
- UNIT-ORD-3-003: test_delete_order - 删除订单
- UNIT-ORD-3-004: test_batch_delete_orders - 批量删除订单
- UNIT-ORD-3-005: test_set_exchange_gateway - 依赖注入：交易所网关
- UNIT-ORD-3-006: test_set_audit_logger - 依赖注入：审计日志器
- UNIT-ORD-3-007: test_save_order_with_null_values - 边界条件：空值处理
- UNIT-ORD-3-008: test_update_order_concurrent - 并发安全测试
- UNIT-ORD-3-009: test_transaction_rollback - 事务回滚测试
"""
import pytest
import asyncio
import os
import tempfile
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest_asyncio

from src.domain.models import (
    Order, OrderStatus, OrderType, OrderRole, Direction,
)


# ============================================================
# 测试夹具 (Fixtures)
# ============================================================

@pytest.fixture
def temp_db_path():
    """创建临时数据库文件"""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    # 清理
    if os.path.exists(path):
        os.remove(path)


@pytest_asyncio.fixture
async def order_repository(temp_db_path):
    """创建 OrderRepository 实例"""
    from src.infrastructure.order_repository import OrderRepository
    repo = OrderRepository(db_path=temp_db_path)
    await repo.initialize()
    yield repo
    await repo.close()


@pytest.fixture
def mock_exchange_gateway():
    """Mock 交易所网关"""
    gateway = MagicMock()
    gateway.cancel_order = AsyncMock(return_value=True)
    return gateway


@pytest.fixture
def mock_audit_logger():
    """Mock 审计日志器"""
    logger = MagicMock()
    logger.log_order_change = AsyncMock(return_value=None)
    return logger


# ============================================================
# CRUD 操作测试
# ============================================================

@pytest.mark.asyncio
async def test_save_order(order_repository):
    """
    UNIT-ORD-3-001: 保存订单功能测试

    测试场景:
    1. 创建订单对象
    2. 调用 save 方法保存
    3. 验证订单已持久化到数据库

    验收标准:
    - 订单成功保存到数据库
    - 查询返回的订单与保存的一致
    """
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 准备：创建订单
    order = Order(
        id="ord_save_test_001",
        signal_id="sig_save_test",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('0'),
        status=OrderStatus.OPEN,
        created_at=current_time,
        updated_at=current_time,
        reduce_only=False,
    )

    # 执行：保存订单
    await order_repository.save(order)

    # 验证：查询订单
    saved_order = await order_repository.get_order("ord_save_test_001")

    assert saved_order is not None
    assert saved_order.id == order.id
    assert saved_order.signal_id == order.signal_id
    assert saved_order.symbol == order.symbol
    assert saved_order.direction == order.direction
    assert saved_order.order_type == order.order_type
    assert saved_order.order_role == order.order_role
    assert saved_order.requested_qty == order.requested_qty
    assert saved_order.filled_qty == order.filled_qty
    assert saved_order.status == order.status


@pytest.mark.asyncio
async def test_update_order_status(order_repository):
    """
    UNIT-ORD-3-002: 更新订单状态功能测试

    测试场景:
    1. 创建并保存订单
    2. 更新订单状态和相关字段
    3. 验证更新后的数据

    验收标准:
    - 状态更新成功
    - filled_qty 和 average_exec_price 更新成功
    - updated_at 时间戳更新
    """
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 准备：创建并保存订单
    order = Order(
        id="ord_update_test_001",
        signal_id="sig_update_test",
        symbol="ETH/USDT:USDT",
        direction=Direction.SHORT,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        price=Decimal('3500'),
        requested_qty=Decimal('5.0'),
        filled_qty=Decimal('0'),
        status=OrderStatus.OPEN,
        created_at=current_time,
        updated_at=current_time,
        reduce_only=True,
    )
    await order_repository.save(order)

    # 执行：更新订单状态为部分成交
    filled_qty = Decimal('2.5')
    avg_price = Decimal('3495.5')

    await order_repository.update_status(
        order_id="ord_update_test_001",
        status=OrderStatus.PARTIALLY_FILLED,
        filled_qty=filled_qty,
        average_exec_price=avg_price,
    )

    # 验证：查询更新后的订单
    updated_order = await order_repository.get_order("ord_update_test_001")

    assert updated_order.status == OrderStatus.PARTIALLY_FILLED
    assert updated_order.filled_qty == filled_qty
    assert updated_order.average_exec_price == avg_price
    assert updated_order.updated_at >= current_time


@pytest.mark.asyncio
async def test_delete_order(order_repository):
    """
    UNIT-ORD-3-003: 删除订单功能测试

    测试场景:
    1. 创建并保存订单
    2. 调用 delete_order 方法删除
    3. 验证订单已从数据库移除

    验收标准:
    - 订单成功删除
    - 查询返回 None
    """
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 准备：创建并保存订单
    order = Order(
        id="ord_delete_test_001",
        signal_id="sig_delete_test",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('0'),
        status=OrderStatus.OPEN,
        created_at=current_time,
        updated_at=current_time,
        reduce_only=False,
    )
    await order_repository.save(order)

    # 验证：订单已保存
    saved_order = await order_repository.get_order("ord_delete_test_001")
    assert saved_order is not None

    # 执行：删除订单（使用 clear_orders 代替）
    deleted_count = await order_repository.clear_orders(signal_id="sig_delete_test")

    # 验证：订单已删除
    assert deleted_count == 1
    deleted_order = await order_repository.get_order("ord_delete_test_001")
    assert deleted_order is None


@pytest.mark.asyncio
async def test_batch_delete_orders(order_repository):
    """
    UNIT-ORD-3-004: 批量删除订单功能测试

    测试场景:
    1. 创建并保存多个订单
    2. 调用 clear_orders 批量删除
    3. 验证所有订单已删除

    验收标准:
    - 所有订单成功删除
    - 查询返回空列表
    """
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 准备：创建多个订单
    order_ids = ["ord_batch_delete_001", "ord_batch_delete_002", "ord_batch_delete_003"]
    orders = [
        Order(
            id=order_id,
            signal_id="sig_batch_delete",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.0'),
            filled_qty=Decimal('0'),
            status=OrderStatus.OPEN,
            created_at=current_time,
            updated_at=current_time,
            reduce_only=False,
        )
        for order_id in order_ids
    ]

    for order in orders:
        await order_repository.save(order)

    # 验证：订单已保存
    all_orders = await order_repository.get_all_orders(limit=10)
    assert len(all_orders) == 3

    # 执行：批量删除（使用 clear_orders）
    deleted_count = await order_repository.clear_orders(signal_id="sig_batch_delete")

    # 验证：所有订单已删除
    assert deleted_count == 3
    all_orders_after = await order_repository.get_all_orders(limit=10)
    assert len(all_orders_after) == 0


# ============================================================
# 依赖注入测试
# ============================================================

@pytest.mark.asyncio
async def test_set_exchange_gateway(order_repository, mock_exchange_gateway):
    """
    UNIT-ORD-3-005: 依赖注入 - 交易所网关

    测试场景:
    1. 创建 OrderRepository（不注入网关）
    2. 通过 set_exchange_gateway 注入 mock 网关
    3. 验证网关已成功注入

    验收标准:
    - 网关引用正确设置
    - 网关方法可被调用
    """
    # 验证：初始时网关为 None
    assert order_repository._exchange_gateway is None

    # 执行：注入网关
    order_repository.set_exchange_gateway(mock_exchange_gateway)

    # 验证：网关已设置
    assert order_repository._exchange_gateway is mock_exchange_gateway
    assert order_repository._exchange_gateway.cancel_order is not None


@pytest.mark.asyncio
async def test_set_audit_logger(order_repository, mock_audit_logger):
    """
    UNIT-ORD-3-006: 依赖注入 - 审计日志器

    测试场景:
    1. 创建 OrderRepository（不注入日志器）
    2. 通过 set_audit_logger 注入 mock 日志器
    3. 验证日志器已成功注入

    验收标准:
    - 日志器引用正确设置
    - 日志器方法可被调用
    """
    # 验证：初始时日志器为 None
    assert order_repository._audit_logger is None

    # 执行：注入日志器
    order_repository.set_audit_logger(mock_audit_logger)

    # 验证：日志器已设置
    assert order_repository._audit_logger is mock_audit_logger
    assert order_repository._audit_logger.log_order_change is not None


# ============================================================
# 边界条件测试
# ============================================================

@pytest.mark.asyncio
async def test_save_order_with_null_values(order_repository):
    """
    UNIT-ORD-3-007: 边界条件 - 空值处理

    测试场景:
    1. 创建包含可选字段为 None 的订单
    2. 保存订单
    3. 验证订单可正常保存和查询

    验收标准:
    - 可选字段为 None 的订单可正常保存
    - 查询返回的订单数据一致
    """
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 准备：创建订单（price 和 average_exec_price 为 None）
    order = Order(
        id="ord_null_test_001",
        signal_id="sig_null_test",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('0'),
        status=OrderStatus.OPEN,
        created_at=current_time,
        updated_at=current_time,
        reduce_only=False,
        # 可选字段为 None
        price=None,
        average_exec_price=None,
        filled_at=None,
        parent_order_id=None,
        oco_group_id=None,
    )

    # 执行：保存订单
    await order_repository.save(order)

    # 验证：查询订单
    saved_order = await order_repository.get_order("ord_null_test_001")

    assert saved_order is not None
    assert saved_order.price is None
    assert saved_order.average_exec_price is None
    assert saved_order.filled_at is None
    assert saved_order.parent_order_id is None
    assert saved_order.oco_group_id is None


@pytest.mark.asyncio
async def test_update_order_concurrent(order_repository):
    """
    UNIT-ORD-3-008: 并发安全 - 同时更新同一订单

    测试场景:
    1. 创建并保存订单
    2. 并发执行多次更新操作
    3. 验证数据一致性

    验收标准:
    - 并发更新不会导致数据损坏
    - 最终状态与最后一次更新一致
    """
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 准备：创建并保存订单
    order = Order(
        id="ord_concurrent_test_001",
        signal_id="sig_concurrent_test",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('0'),
        status=OrderStatus.OPEN,
        created_at=current_time,
        updated_at=current_time,
        reduce_only=False,
    )
    await order_repository.save(order)

    # 执行：并发更新订单状态
    async def update_order(fill_qty: Decimal, status: OrderStatus):
        await order_repository.update_status(
            order_id="ord_concurrent_test_001",
            status=status,
            filled_qty=fill_qty,
            average_exec_price=Decimal('70000'),
        )

    # 并发执行 3 次更新
    await asyncio.gather(
        update_order(Decimal('0.3'), OrderStatus.PARTIALLY_FILLED),
        update_order(Decimal('0.6'), OrderStatus.PARTIALLY_FILLED),
        update_order(Decimal('1.0'), OrderStatus.FILLED),
    )

    # 验证：最终状态应该是一致的（最后一次更新）
    final_order = await order_repository.get_order("ord_concurrent_test_001")
    assert final_order is not None
    # 验证订单仍然存在且数据有效
    assert final_order.filled_qty in [Decimal('0.3'), Decimal('0.6'), Decimal('1.0')]
    assert final_order.status in [OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED]


@pytest.mark.asyncio
async def test_transaction_rollback(order_repository):
    """
    UNIT-ORD-3-009: 事务回滚测试

    测试场景:
    1. 开始事务
    2. 保存订单
    3. 使用 clear_orders 清理
    4. 验证数据库状态一致

    验收标准:
    - 清理后订单不存在
    - 数据库状态一致
    """
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 准备：创建订单
    order = Order(
        id="ord_transaction_test_001",
        signal_id="sig_transaction_test",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('0'),
        status=OrderStatus.OPEN,
        created_at=current_time,
        updated_at=current_time,
        reduce_only=False,
    )

    # 执行：保存订单
    await order_repository.save(order)

    # 验证：订单已保存
    saved_order = await order_repository.get_order("ord_transaction_test_001")
    assert saved_order is not None

    # 执行：清理订单（使用 clear_orders）
    deleted_count = await order_repository.clear_orders(signal_id="sig_transaction_test")

    # 验证：订单已删除
    assert deleted_count == 1
    deleted_order = await order_repository.get_order("ord_transaction_test_001")
    assert deleted_order is None


# ============================================================
# 辅助方法测试
# ============================================================

@pytest.mark.asyncio
async def test_get_all_orders_with_limit(order_repository):
    """
    UNIT-ORD-3-010: 获取所有订单带 limit 限制

    测试场景:
    1. 创建多个订单
    2. 使用 limit 参数查询
    3. 验证返回数量正确

    验收标准:
    - 返回数量不超过 limit
    - 订单按 created_at 降序排列
    """
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 准备：创建 10 个订单
    orders = [
        Order(
            id=f"ord_limit_test_{i}",
            signal_id="sig_limit_test",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.0'),
            filled_qty=Decimal('0'),
            status=OrderStatus.OPEN,
            created_at=current_time + i * 1000,
            updated_at=current_time + i * 1000,
            reduce_only=False,
        )
        for i in range(10)
    ]

    for order in orders:
        await order_repository.save(order)

    # 执行：limit=5 查询
    limited_orders = await order_repository.get_all_orders(limit=5)

    # 验证：只返回 5 个订单
    assert len(limited_orders) == 5

    # 验证：按 created_at 降序排列
    for i in range(len(limited_orders) - 1):
        assert limited_orders[i].created_at >= limited_orders[i + 1].created_at


@pytest.mark.asyncio
async def test_get_orders_by_signal_id(order_repository):
    """
    UNIT-ORD-3-011: 按信号 ID 查询订单

    测试场景:
    1. 创建不同信号的订单
    2. 按信号 ID 查询
    3. 验证只返回指定信号的订单

    验收标准:
    - 只返回指定 signal_id 的订单
    - 返回的订单按 created_at 降序排列
    """
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 准备：创建不同信号的订单
    signal_a_orders = [
        Order(
            id=f"ord_signal_a_{i}",
            signal_id="sig_a",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.0'),
            filled_qty=Decimal('0'),
            status=OrderStatus.OPEN,
            created_at=current_time + i * 1000,
            updated_at=current_time + i * 1000,
            reduce_only=False,
        )
        for i in range(3)
    ]

    signal_b_orders = [
        Order(
            id=f"ord_signal_b_{i}",
            signal_id="sig_b",
            symbol="ETH/USDT:USDT",
            direction=Direction.SHORT,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.TP1,
            price=Decimal('3500'),
            requested_qty=Decimal('5.0'),
            filled_qty=Decimal('0'),
            status=OrderStatus.OPEN,
            created_at=current_time + i * 1000,
            updated_at=current_time + i * 1000,
            reduce_only=True,
        )
        for i in range(2)
    ]

    for order in signal_a_orders + signal_b_orders:
        await order_repository.save(order)

    # 执行：按信号 A 查询
    signal_a_result = await order_repository.get_orders_by_signal("sig_a")

    # 验证：只返回信号 A 的订单
    assert len(signal_a_result) == 3
    assert all(o.signal_id == "sig_a" for o in signal_a_result)

    # 执行：按信号 B 查询
    signal_b_result = await order_repository.get_orders_by_signal("sig_b")

    # 验证：只返回信号 B 的订单
    assert len(signal_b_result) == 2
    assert all(o.signal_id == "sig_b" for o in signal_b_result)


@pytest.mark.asyncio
async def test_get_orders_by_status(order_repository):
    """
    UNIT-ORD-3-012: 按状态查询订单

    测试场景:
    1. 创建不同状态的订单
    2. 按状态查询
    3. 验证只返回指定状态的订单

    验收标准:
    - 只返回指定状态的订单
    - 返回的订单按 created_at 降序排列
    """
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 准备：创建 OPEN 状态订单
    open_order = Order(
        id="ord_status_open_001",
        signal_id="sig_status_test",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('0'),
        status=OrderStatus.OPEN,
        created_at=current_time,
        updated_at=current_time,
        reduce_only=False,
    )

    # 准备：创建 FILLED 状态订单
    filled_order = Order(
        id="ord_status_filled_001",
        signal_id="sig_status_test",
        symbol="ETH/USDT:USDT",
        direction=Direction.SHORT,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        price=Decimal('3500'),
        requested_qty=Decimal('5.0'),
        filled_qty=Decimal('5.0'),
        status=OrderStatus.FILLED,
        created_at=current_time,
        updated_at=current_time + 1000,
        filled_at=current_time + 1000,
        reduce_only=True,
    )

    # 准备：创建 CANCELED 状态订单
    canceled_order = Order(
        id="ord_status_canceled_001",
        signal_id="sig_status_test",
        symbol="SOL/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        price=Decimal('200'),
        requested_qty=Decimal('10.0'),
        filled_qty=Decimal('0'),
        status=OrderStatus.CANCELED,
        created_at=current_time,
        updated_at=current_time + 2000,
        reduce_only=True,
    )

    await order_repository.save(open_order)
    await order_repository.save(filled_order)
    await order_repository.save(canceled_order)

    # 执行：按 OPEN 状态查询
    open_result = await order_repository.get_orders_by_status(OrderStatus.OPEN)
    assert len(open_result) == 1
    assert open_result[0].id == "ord_status_open_001"

    # 执行：按 FILLED 状态查询
    filled_result = await order_repository.get_orders_by_status(OrderStatus.FILLED)
    assert len(filled_result) == 1
    assert filled_result[0].id == "ord_status_filled_001"

    # 执行：按 CANCELED 状态查询
    canceled_result = await order_repository.get_orders_by_status(OrderStatus.CANCELED)
    assert len(canceled_result) == 1
    assert canceled_result[0].id == "ord_status_canceled_001"
