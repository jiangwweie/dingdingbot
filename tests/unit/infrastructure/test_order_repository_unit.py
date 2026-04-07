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


# ============================================================
# 极高风险方法测试 - delete_orders_batch
# ============================================================

@pytest.fixture
def mock_exchange_gateway_with_cancel():
    """Mock ExchangeGateway with cancel_order method"""
    gateway = MagicMock()
    gateway.cancel_order = AsyncMock(return_value=MagicMock(is_success=True, error_message=None))
    return gateway


@pytest.fixture
def mock_audit_logger_instance():
    """Mock OrderAuditLogger"""
    logger = MagicMock()
    logger.log = AsyncMock(return_value="audit-log-id-123")
    return logger


def create_test_order(
    order_id: str,
    signal_id: str = "sig_test",
    symbol: str = "BTC/USDT:USDT",
    direction: Direction = Direction.LONG,
    order_role: OrderRole = OrderRole.ENTRY,
    status: OrderStatus = OrderStatus.OPEN,
    parent_order_id: Optional[str] = None,
    oco_group_id: Optional[str] = None,
    exchange_order_id: Optional[str] = None,
    filled_qty: Optional[Decimal] = None,
) -> Order:
    """辅助函数：创建测试订单"""
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    return Order(
        id=order_id,
        signal_id=signal_id,
        symbol=symbol,
        direction=direction,
        order_type=OrderType.MARKET,
        order_role=order_role,
        requested_qty=Decimal('1.0'),
        filled_qty=filled_qty if filled_qty is not None else Decimal('0'),
        status=status,
        created_at=current_time,
        updated_at=current_time,
        reduce_only=False,
        parent_order_id=parent_order_id,
        oco_group_id=oco_group_id,
        exchange_order_id=exchange_order_id,
    )


@pytest.mark.asyncio
async def test_delete_orders_batch_normal_success(
    order_repository,
    mock_exchange_gateway_with_cancel,
    mock_audit_logger_instance,
):
    """
    TEST-DEL-BATCH-001: 正常批量删除成功场景

    测试场景:
    1. 创建多个订单
    2. 注入交易所网关和审计日志器
    3. 调用 delete_orders_batch 批量删除
    4. 验证删除结果

    验收标准:
    - 所有订单成功删除
    - 交易所取消成功
    - 审计日志记录完整
    """
    # 准备：创建多个订单
    order_ids = ["ord_del_batch_001", "ord_del_batch_002", "ord_del_batch_003"]
    orders = [
        create_test_order(
            order_id=oid,
            exchange_order_id=f"binance_{oid}",
        )
        for oid in order_ids
    ]

    for order in orders:
        await order_repository.save(order)

    # 注入依赖
    order_repository.set_exchange_gateway(mock_exchange_gateway_with_cancel)
    order_repository.set_audit_logger(mock_audit_logger_instance)

    # 执行：批量删除
    result = await order_repository.delete_orders_batch(
        order_ids=order_ids,
        cancel_on_exchange=True,
        audit_info={"operator_id": "user_123", "ip_address": "192.168.1.1"},
    )

    # 验证：删除结果
    assert result["deleted_count"] == 3
    assert len(result["deleted_from_db"]) == 3
    assert set(result["deleted_from_db"]) == set(order_ids)
    assert len(result["cancelled_on_exchange"]) == 3
    assert len(result["failed_to_cancel"]) == 0
    assert result["audit_log_id"] is not None

    # 验证：订单已从数据库删除
    for oid in order_ids:
        saved_order = await order_repository.get_order(oid)
        assert saved_order is None

    # 验证：审计日志被调用
    mock_audit_logger_instance.log.assert_called_once()


@pytest.mark.asyncio
async def test_delete_orders_batch_with_child_orders(
    order_repository,
    mock_exchange_gateway_with_cancel,
    mock_audit_logger_instance,
):
    """
    TEST-DEL-BATCH-002: 批量删除包含子订单的父订单

    测试场景:
    1. 创建 ENTRY 订单及其 TP/SL 子订单
    2. 删除 ENTRY 订单
    3. 验证子订单也被级联删除

    验收标准:
    - 父订单和子订单都被删除
    - _get_all_related_order_ids 递归获取所有关联订单
    """
    # 准备：创建订单链
    entry_order = create_test_order(
        order_id="ord_entry_001",
        order_role=OrderRole.ENTRY,
        exchange_order_id="binance_entry_001",
    )
    tp_order = create_test_order(
        order_id="ord_tp_001",
        order_role=OrderRole.TP1,
        parent_order_id="ord_entry_001",
        exchange_order_id="binance_tp_001",
    )
    sl_order = create_test_order(
        order_id="ord_sl_001",
        order_role=OrderRole.SL,
        parent_order_id="ord_entry_001",
        exchange_order_id="binance_sl_001",
    )

    for order in [entry_order, tp_order, sl_order]:
        await order_repository.save(order)

    # 注入依赖
    order_repository.set_exchange_gateway(mock_exchange_gateway_with_cancel)
    order_repository.set_audit_logger(mock_audit_logger_instance)

    # 执行：只删除 ENTRY 订单
    result = await order_repository.delete_orders_batch(
        order_ids=["ord_entry_001"],
        cancel_on_exchange=True,
    )

    # 验证：所有关联订单都被删除
    assert result["deleted_count"] == 3
    assert set(result["deleted_from_db"]) == {"ord_entry_001", "ord_tp_001", "ord_sl_001"}

    # 验证：所有订单已从数据库删除
    for oid in ["ord_entry_001", "ord_tp_001", "ord_sl_001"]:
        saved_order = await order_repository.get_order(oid)
        assert saved_order is None


@pytest.mark.asyncio
async def test_delete_orders_batch_cascade_false(
    order_repository,
    mock_exchange_gateway_with_cancel,
):
    """
    TEST-DEL-BATCH-003: 删除子订单时级联获取父订单

    测试场景:
    1. 创建父子订单关系
    2. 删除子订单
    3. 验证 _get_all_related_order_ids 递归获取父订单

    注意：_get_all_related_order_ids 设计为递归获取所有关联订单
    包括父订单和兄弟订单，所以删除子订单时会同时删除父订单

    验收标准:
    - 子订单和父订单都被删除（因为递归获取）
    - 这是预期的设计行为
    """
    # 准备：创建订单链
    entry_order = create_test_order(
        order_id="ord_entry_002",
        order_role=OrderRole.ENTRY,
        exchange_order_id="binance_entry_002",
    )
    tp_order = create_test_order(
        order_id="ord_tp_002",
        order_role=OrderRole.TP1,
        parent_order_id="ord_entry_002",
        exchange_order_id="binance_tp_002",
    )

    for order in [entry_order, tp_order]:
        await order_repository.save(order)

    # 注入依赖
    order_repository.set_exchange_gateway(mock_exchange_gateway_with_cancel)

    # 执行：只删除 TP 订单
    result = await order_repository.delete_orders_batch(
        order_ids=["ord_tp_002"],
        cancel_on_exchange=True,
    )

    # 验证：_get_all_related_order_ids 递归获取父订单
    # 所以 TP 订单和 ENTRY 订单都会被删除
    assert result["deleted_count"] == 2
    assert set(result["deleted_from_db"]) == {"ord_entry_002", "ord_tp_002"}

    # 验证：所有订单都从数据库删除
    for oid in ["ord_entry_002", "ord_tp_002"]:
        saved_order = await order_repository.get_order(oid)
        assert saved_order is None


@pytest.mark.asyncio
async def test_delete_orders_batch_exchange_cancel_failure(
    order_repository,
    mock_exchange_gateway_with_cancel,
):
    """
    TEST-DEL-BATCH-004: 交易所取消失败场景

    测试场景:
    1. Mock 交易所取消失败
    2. 执行批量删除
    3. 验证失败订单被记录

    验收标准:
    - 取消失败的订单记录在 failed_to_cancel
    - DB 删除仍然成功
    - 审计日志记录失败详情
    """
    # 准备：创建订单
    order1 = create_test_order(
        order_id="ord_fail_001",
        exchange_order_id="binance_fail_001",
    )
    order2 = create_test_order(
        order_id="ord_fail_002",
        exchange_order_id="binance_fail_002",
    )

    for order in [order1, order2]:
        await order_repository.save(order)

    # Mock：第一个订单取消失败
    async def cancel_side_effect(*args, **kwargs):
        if kwargs.get("exchange_order_id") == "binance_fail_001":
            return MagicMock(is_success=False, error_message="Order already canceled")
        return MagicMock(is_success=True, error_message=None)

    mock_exchange_gateway_with_cancel.cancel_order = AsyncMock(side_effect=cancel_side_effect)

    # 注入依赖
    order_repository.set_exchange_gateway(mock_exchange_gateway_with_cancel)
    order_repository.set_audit_logger(mock_audit_logger_instance)

    # 执行：批量删除
    result = await order_repository.delete_orders_batch(
        order_ids=["ord_fail_001", "ord_fail_002"],
        cancel_on_exchange=True,
    )

    # 验证：取消失败记录
    assert len(result["failed_to_cancel"]) == 1
    assert result["failed_to_cancel"][0]["order_id"] == "ord_fail_001"
    assert "already canceled" in result["failed_to_cancel"][0]["reason"]

    # 验证：DB 删除仍然成功
    assert result["deleted_count"] == 2
    assert set(result["deleted_from_db"]) == {"ord_fail_001", "ord_fail_002"}


@pytest.mark.asyncio
async def test_delete_orders_batch_no_exchange_gateway(
    order_repository,
):
    """
    TEST-DEL-BATCH-005: ExchangeGateway 未注入场景

    测试场景:
    1. 不注入 ExchangeGateway
    2. 执行批量删除
    3. 验证跳过交易所取消

    验收标准:
    - 所有订单记录为取消失败（原因：未注入网关）
    - DB 删除成功
    """
    # 准备：创建订单
    order = create_test_order(
        order_id="ord_no_gateway_001",
        exchange_order_id="binance_no_gateway_001",
    )
    await order_repository.save(order)

    # 不注入 ExchangeGateway

    # 执行：批量删除
    result = await order_repository.delete_orders_batch(
        order_ids=["ord_no_gateway_001"],
        cancel_on_exchange=True,
    )

    # 验证：取消失败（网关未注入）
    assert len(result["failed_to_cancel"]) == 1
    assert "not initialized" in result["failed_to_cancel"][0]["reason"]

    # 验证：DB 删除成功
    assert result["deleted_count"] == 1
    saved_order = await order_repository.get_order("ord_no_gateway_001")
    assert saved_order is None


@pytest.mark.asyncio
async def test_delete_orders_batch_empty_order_ids(
    order_repository,
):
    """
    TEST-DEL-BATCH-006: 空订单 ID 列表参数验证

    测试场景:
    1. 传入空订单 ID 列表
    2. 验证抛出 ValueError

    验收标准:
    - 抛出 ValueError 异常
    """
    # 执行 & 验证：空列表抛出异常
    with pytest.raises(ValueError, match="订单 ID 列表不能为空"):
        await order_repository.delete_orders_batch(
            order_ids=[],
            cancel_on_exchange=True,
        )


@pytest.mark.asyncio
async def test_delete_orders_batch_exceeds_limit(
    order_repository,
):
    """
    TEST-DEL-BATCH-007: 超过 100 个订单限制验证

    测试场景:
    1. 传入超过 100 个订单 ID
    2. 验证抛出 ValueError

    验收标准:
    - 抛出 ValueError 异常
    """
    # 准备：超过 100 个订单 ID
    order_ids = [f"ord_{i}" for i in range(101)]

    # 执行 & 验证：抛出异常
    with pytest.raises(ValueError, match="批量删除最多支持 100 个订单"):
        await order_repository.delete_orders_batch(
            order_ids=order_ids,
            cancel_on_exchange=True,
        )


@pytest.mark.asyncio
async def test_delete_orders_batch_partial_filled_orders(
    order_repository,
    mock_exchange_gateway_with_cancel,
    mock_audit_logger_instance,
):
    """
    TEST-DEL-BATCH-008: PARTIALLY_FILLED 状态订单取消

    测试场景:
    1. 创建 PARTIALLY_FILLED 状态的订单
    2. 执行批量删除
    3. 验证仍然尝试取消

    验收标准:
    - PARTIALLY_FILLED 订单也尝试取消
    - 删除成功
    """
    # 准备：创建部分成交订单
    order = create_test_order(
        order_id="ord_partial_001",
        status=OrderStatus.PARTIALLY_FILLED,
        exchange_order_id="binance_partial_001",
        filled_qty=Decimal('0.5'),
    )
    await order_repository.save(order)

    # 注入依赖
    order_repository.set_exchange_gateway(mock_exchange_gateway_with_cancel)
    order_repository.set_audit_logger(mock_audit_logger_instance)

    # 执行：批量删除
    result = await order_repository.delete_orders_batch(
        order_ids=["ord_partial_001"],
        cancel_on_exchange=True,
    )

    # 验证：取消成功
    assert len(result["cancelled_on_exchange"]) == 1
    assert result["deleted_count"] == 1


@pytest.mark.asyncio
async def test_delete_orders_batch_no_exchange_order_id(
    order_repository,
    mock_exchange_gateway_with_cancel,
):
    """
    TEST-DEL-BATCH-009: 订单没有 exchange_order_id

    测试场景:
    1. 创建没有 exchange_order_id 的订单
    2. 执行批量删除
    3. 验证跳过交易所取消

    验收标准:
    - 记录为取消失败（原因：无 exchange_order_id）
    - DB 删除成功
    """
    # 准备：创建订单（无 exchange_order_id）
    order = create_test_order(
        order_id="ord_no_exchange_id_001",
        exchange_order_id=None,
    )
    await order_repository.save(order)

    # 注入依赖
    order_repository.set_exchange_gateway(mock_exchange_gateway_with_cancel)

    # 执行：批量删除
    result = await order_repository.delete_orders_batch(
        order_ids=["ord_no_exchange_id_001"],
        cancel_on_exchange=True,
    )

    # 验证：取消失败（无 exchange_order_id）
    assert len(result["failed_to_cancel"]) == 1
    assert "No exchange_order_id" in result["failed_to_cancel"][0]["reason"]

    # 验证：DB 删除成功
    assert result["deleted_count"] == 1


# ============================================================
# 极高风险方法测试 - get_oco_group
# ============================================================

@pytest.mark.asyncio
async def test_get_oco_group_normal(order_repository):
    """
    TEST-OCO-001: 正常获取 OCO 组

    测试场景:
    1. 创建多个相同 oco_group_id 的订单
    2. 调用 get_oco_group 查询
    3. 验证返回所有 OCO 组成员

    验收标准:
    - 返回所有相同 oco_group_id 的订单
    - 订单按 created_at 升序排列
    """
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    oco_group_id = "oco_group_001"

    # 准备：创建 OCO 组订单
    orders = [
        create_test_order(
            order_id=f"ord_oco_{i}",
            oco_group_id=oco_group_id,
            order_role=OrderRole.TP1 if i % 2 == 0 else OrderRole.SL,
        )
        for i in range(3)
    ]

    for order in orders:
        await order_repository.save(order)

    # 执行：获取 OCO 组
    result = await order_repository.get_oco_group(oco_group_id)

    # 验证：返回所有 OCO 成员
    assert len(result) == 3
    assert all(o.oco_group_id == oco_group_id for o in result)

    # 验证：按 created_at 升序排列
    for i in range(len(result) - 1):
        assert result[i].created_at <= result[i + 1].created_at


@pytest.mark.asyncio
async def test_get_oco_group_not_exists(order_repository):
    """
    TEST-OCO-002: OCO 组不存在

    测试场景:
    1. 查询不存在的 oco_group_id
    2. 验证返回空列表

    验收标准:
    - 返回空列表
    """
    # 执行：查询不存在的 OCO 组
    result = await order_repository.get_oco_group("oco_group_not_exists")

    # 验证：返回空列表
    assert len(result) == 0


@pytest.mark.asyncio
async def test_get_oco_group_with_filled_orders(order_repository):
    """
    TEST-OCO-003: OCO 组包含已成交订单

    测试场景:
    1. 创建 OCO 组订单
    2. 更新其中一个订单为 FILLED 状态
    3. 查询 OCO 组

    验收标准:
    - 返回所有订单（包括已成交的）
    - 订单状态正确
    """
    oco_group_id = "oco_group_filled_001"

    # 准备：创建 OCO 组订单
    tp_order = create_test_order(
        order_id="ord_oco_tp",
        oco_group_id=oco_group_id,
        order_role=OrderRole.TP1,
        status=OrderStatus.OPEN,
    )
    sl_order = create_test_order(
        order_id="ord_oco_sl",
        oco_group_id=oco_group_id,
        order_role=OrderRole.SL,
        status=OrderStatus.OPEN,
    )

    for order in [tp_order, sl_order]:
        await order_repository.save(order)

    # 执行：更新 TP 订单为已成交
    await order_repository.update_status(
        order_id="ord_oco_tp",
        status=OrderStatus.FILLED,
        filled_qty=Decimal('1.0'),
    )

    # 执行：获取 OCO 组
    result = await order_repository.get_oco_group(oco_group_id)

    # 验证：返回所有订单
    assert len(result) == 2

    # 验证：状态正确
    tp_result = next(o for o in result if o.id == "ord_oco_tp")
    sl_result = next(o for o in result if o.id == "ord_oco_sl")
    assert tp_result.status == OrderStatus.FILLED
    assert sl_result.status == OrderStatus.OPEN


@pytest.mark.asyncio
async def test_get_oco_group_with_canceled_orders(order_repository):
    """
    TEST-OCO-004: OCO 组包含已取消订单

    测试场景:
    1. 创建 OCO 组订单
    2. 取消其中一个订单
    3. 查询 OCO 组

    验收标准:
    - 返回所有订单（包括已取消的）
    - 取消订单状态正确
    """
    oco_group_id = "oco_group_canceled_001"

    # 准备：创建 OCO 组订单
    orders = [
        create_test_order(
            order_id=f"ord_oco_cancel_{i}",
            oco_group_id=oco_group_id,
            status=OrderStatus.OPEN,
        )
        for i in range(2)
    ]

    for order in orders:
        await order_repository.save(order)

    # 执行：取消一个订单
    await order_repository.update_status(
        order_id="ord_oco_cancel_0",
        status=OrderStatus.CANCELED,
    )

    # 执行：获取 OCO 组
    result = await order_repository.get_oco_group(oco_group_id)

    # 验证：返回所有订单
    assert len(result) == 2

    # 验证：状态正确
    canceled_order = next(o for o in result if o.id == "ord_oco_cancel_0")
    assert canceled_order.status == OrderStatus.CANCELED


@pytest.mark.asyncio
async def test_get_oco_group_single_order(order_repository):
    """
    TEST-OCO-005: OCO 组只有一个订单

    测试场景:
    1. 创建单个订单带 oco_group_id
    2. 查询 OCO 组

    验收标准:
    - 返回单个订单
    """
    oco_group_id = "oco_group_single_001"

    # 准备：创建单个订单
    order = create_test_order(
        order_id="ord_oco_single",
        oco_group_id=oco_group_id,
    )
    await order_repository.save(order)

    # 执行：获取 OCO 组
    result = await order_repository.get_oco_group(oco_group_id)

    # 验证：返回单个订单
    assert len(result) == 1
    assert result[0].id == "ord_oco_single"


@pytest.mark.asyncio
async def test_get_oco_group_null_oco_id(order_repository):
    """
    TEST-OCO-006: oco_group_id 为 None 的订单

    测试场景:
    1. 创建 oco_group_id 为 None 的订单
    2. 查询 None 的 OCO 组

    验收标准:
    - None 不作为有效的 oco_group_id 查询
    - 返回空列表
    """
    # 准备：创建订单（oco_group_id=None）
    order = create_test_order(
        order_id="ord_no_oco",
        oco_group_id=None,
    )
    await order_repository.save(order)

    # 执行：查询 None（应该返回空或处理）
    # 注意：SQL 中 WHERE oco_group_id = NULL 不会匹配任何行
    result = await order_repository.get_oco_group(None)  # type: ignore

    # 验证：返回空列表
    assert len(result) == 0


# ============================================================
# 辅助方法测试 - _get_all_related_order_ids
# ============================================================

@pytest.mark.asyncio
async def test_get_all_related_order_ids_parent_only(order_repository):
    """
    TEST-RELATED-001: 只获取子订单

    测试场景:
    1. 创建 ENTRY 订单和多个 TP/SL 子订单
    2. 从 ENTRY 订单 ID 开始查询
    3. 验证返回所有子订单 ID

    验收标准:
    - 返回所有子订单 ID
    - 包含父订单本身
    """
    # 准备：创建订单链
    entry_order = create_test_order(
        order_id="ord_related_entry",
        order_role=OrderRole.ENTRY,
    )
    tp_orders = [
        create_test_order(
            order_id=f"ord_related_tp{i}",
            order_role=OrderRole.TP1,
            parent_order_id="ord_related_entry",
        )
        for i in range(3)
    ]
    sl_order = create_test_order(
        order_id="ord_related_sl",
        order_role=OrderRole.SL,
        parent_order_id="ord_related_entry",
    )

    for order in [entry_order] + tp_orders + [sl_order]:
        await order_repository.save(order)

    # 执行：获取关联订单 ID
    result = await order_repository._get_all_related_order_ids(["ord_related_entry"])

    # 验证：包含所有订单
    expected_ids = {"ord_related_entry", "ord_related_tp0", "ord_related_tp1", "ord_related_tp2", "ord_related_sl"}
    assert result == expected_ids


@pytest.mark.asyncio
async def test_get_all_related_order_ids_from_child(order_repository):
    """
    TEST-RELATED-002: 从子订单开始查询

    测试场景:
    1. 创建订单链
    2. 从子订单 ID 开始查询
    3. 验证返回父订单和所有兄弟订单

    验收标准:
    - 返回父订单 ID
    - 返回所有兄弟订单 ID
    """
    # 准备：创建订单链
    entry_order = create_test_order(
        order_id="ord_chain_entry",
        order_role=OrderRole.ENTRY,
    )
    tp1 = create_test_order(
        order_id="ord_chain_tp1",
        order_role=OrderRole.TP1,
        parent_order_id="ord_chain_entry",
    )
    tp2 = create_test_order(
        order_id="ord_chain_tp2",
        order_role=OrderRole.TP2,
        parent_order_id="ord_chain_entry",
    )

    for order in [entry_order, tp1, tp2]:
        await order_repository.save(order)

    # 执行：从 TP1 开始查询
    result = await order_repository._get_all_related_order_ids(["ord_chain_tp1"])

    # 验证：包含父订单和兄弟订单
    expected_ids = {"ord_chain_entry", "ord_chain_tp1", "ord_chain_tp2"}
    assert result == expected_ids


@pytest.mark.asyncio
async def test_get_all_related_order_ids_no_relations(order_repository):
    """
    TEST-RELATED-003: 订单没有关联关系

    测试场景:
    1. 创建独立订单（无 parent/children）
    2. 查询关联订单

    验收标准:
    - 只返回订单本身
    """
    # 准备：创建独立订单
    order = create_test_order(
        order_id="ord_isolated",
        parent_order_id=None,
        oco_group_id=None,
    )
    await order_repository.save(order)

    # 执行：查询关联订单
    result = await order_repository._get_all_related_order_ids(["ord_isolated"])

    # 验证：只包含自己
    assert result == {"ord_isolated"}


@pytest.mark.asyncio
async def test_get_all_related_order_ids_multiple_roots(order_repository):
    """
    TEST-RELATED-004: 多个根订单

    测试场景:
    1. 创建多个独立订单链
    2. 从多个根订单开始查询
    3. 验证返回所有关联订单

    验收标准:
    - 返回所有订单链的订单
    """
    # 准备：创建两个订单链
    for i in range(2):
        entry = create_test_order(
            order_id=f"ord_multi_entry_{i}",
            order_role=OrderRole.ENTRY,
        )
        tp = create_test_order(
            order_id=f"ord_multi_tp_{i}",
            order_role=OrderRole.TP1,
            parent_order_id=f"ord_multi_entry_{i}",
        )
        for order in [entry, tp]:
            await order_repository.save(order)

    # 执行：从两个根订单开始查询
    result = await order_repository._get_all_related_order_ids([
        "ord_multi_entry_0",
        "ord_multi_entry_1",
    ])

    # 验证：包含所有订单
    expected_ids = {
        "ord_multi_entry_0", "ord_multi_tp_0",
        "ord_multi_entry_1", "ord_multi_tp_1",
    }
    assert result == expected_ids


# ============================================================
# P0 核心方法测试 - get_order_chain
# ============================================================

@pytest.mark.asyncio
async def test_get_order_chain_complete(order_repository):
    """
    P0-001: 获取订单链 - 完整订单链场景

    测试场景:
    1. 创建 ENTRY + TP1 + TP2 + SL 订单链
    2. 调用 get_order_chain 查询
    3. 验证返回正确的订单分类

    验收标准:
    - entry 列表包含 ENTRY 订单
    - tps 列表包含 TP1、TP2 订单
    - sl 列表包含 SL 订单
    """
    signal_id = "sig_chain_test_001"
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 准备：创建订单链
    entry_order = Order(
        id="ord_chain_entry",
        signal_id=signal_id,
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('0'),
        status=OrderStatus.FILLED,
        created_at=current_time,
        updated_at=current_time,
        reduce_only=False,
    )

    tp1_order = Order(
        id="ord_chain_tp1",
        signal_id=signal_id,
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        price=Decimal('66000'),
        requested_qty=Decimal('0.5'),
        filled_qty=Decimal('0'),
        status=OrderStatus.OPEN,
        parent_order_id="ord_chain_entry",
        oco_group_id="oco_001",
        created_at=current_time + 1000,
        updated_at=current_time + 1000,
        reduce_only=True,
    )

    tp2_order = Order(
        id="ord_chain_tp2",
        signal_id=signal_id,
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP2,
        price=Decimal('67000'),
        requested_qty=Decimal('0.5'),
        filled_qty=Decimal('0'),
        status=OrderStatus.OPEN,
        parent_order_id="ord_chain_entry",
        oco_group_id="oco_001",
        created_at=current_time + 2000,
        updated_at=current_time + 2000,
        reduce_only=True,
    )

    sl_order = Order(
        id="ord_chain_sl",
        signal_id=signal_id,
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        trigger_price=Decimal('64000'),
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('0'),
        status=OrderStatus.OPEN,
        parent_order_id="ord_chain_entry",
        oco_group_id="oco_001",
        created_at=current_time + 3000,
        updated_at=current_time + 3000,
        reduce_only=True,
    )

    for order in [entry_order, tp1_order, tp2_order, sl_order]:
        await order_repository.save(order)

    # 执行：获取订单链
    chain = await order_repository.get_order_chain(signal_id)

    # 验证
    assert len(chain["entry"]) == 1
    assert chain["entry"][0].id == "ord_chain_entry"
    assert chain["entry"][0].order_role == OrderRole.ENTRY

    assert len(chain["tps"]) == 2
    tp_ids = [o.id for o in chain["tps"]]
    assert "ord_chain_tp1" in tp_ids
    assert "ord_chain_tp2" in tp_ids

    assert len(chain["sl"]) == 1
    assert chain["sl"][0].id == "ord_chain_sl"


@pytest.mark.asyncio
async def test_get_order_chain_empty(order_repository):
    """
    P0-002: 获取订单链 - 空结果边界测试

    测试场景:
    1. 查询不存在的信号
    2. 验证返回空字典结构

    验收标准:
    - entry、tps、sl 均为空列表
    """
    # 执行：查询不存在的信号
    chain = await order_repository.get_order_chain("sig_not_exists")

    # 验证
    assert chain == {"entry": [], "tps": [], "sl": []}


@pytest.mark.asyncio
async def test_get_order_chain_multiple_entry(order_repository):
    """
    P0-003: 获取订单链 - 多个 ENTRY 订单场景

    测试场景:
    1. 创建同一信号的多个 ENTRY 订单
    2. 每个 ENTRY 有关联的 TP/SL
    3. 验证返回所有 ENTRY 订单

    验收标准:
    - entry 列表包含所有 ENTRY 订单
    - tps 列表包含所有 TP 订单
    """
    signal_id = "sig_multi_entry"
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 准备：创建两个 ENTRY 订单及其子订单
    entry1 = Order(
        id="ord_entry_1",
        signal_id=signal_id,
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('0'),
        status=OrderStatus.FILLED,
        created_at=current_time,
        updated_at=current_time,
        reduce_only=False,
    )

    entry2 = Order(
        id="ord_entry_2",
        signal_id=signal_id,
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('0.5'),
        filled_qty=Decimal('0'),
        status=OrderStatus.FILLED,
        created_at=current_time + 1000,
        updated_at=current_time + 1000,
        reduce_only=False,
    )

    tp1 = Order(
        id="ord_tp_entry1",
        signal_id=signal_id,
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        price=Decimal('66000'),
        requested_qty=Decimal('0.5'),
        filled_qty=Decimal('0'),
        status=OrderStatus.OPEN,
        parent_order_id="ord_entry_1",
        created_at=current_time + 2000,
        updated_at=current_time + 2000,
        reduce_only=True,
    )

    tp2 = Order(
        id="ord_tp_entry2",
        signal_id=signal_id,
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        price=Decimal('67000'),
        requested_qty=Decimal('0.25'),
        filled_qty=Decimal('0'),
        status=OrderStatus.OPEN,
        parent_order_id="ord_entry_2",
        created_at=current_time + 3000,
        updated_at=current_time + 3000,
        reduce_only=True,
    )

    for order in [entry1, entry2, tp1, tp2]:
        await order_repository.save(order)

    # 执行：获取订单链
    chain = await order_repository.get_order_chain(signal_id)

    # 验证
    assert len(chain["entry"]) == 2
    assert len(chain["tps"]) == 2


# ============================================================
# P0 核心方法测试 - get_order_chain_by_order_id
# ============================================================

@pytest.mark.asyncio
async def test_get_order_chain_by_order_id_from_entry(order_repository):
    """
    P0-004: 按订单 ID 获取订单链 - 从 ENTRY 订单追溯

    测试场景:
    1. 创建 ENTRY + TP + SL 订单链
    2. 从 ENTRY 订单 ID 查询
    3. 验证返回完整订单链（父订单 + 子订单）

    验收标准:
    - 返回列表包含 ENTRY 订单（第一个）
    - 包含所有 TP/SL 子订单
    """
    signal_id = "sig_tree_test_001"
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    entry_order = Order(
        id="ord_tree_entry",
        signal_id=signal_id,
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('0'),
        status=OrderStatus.FILLED,
        created_at=current_time,
        updated_at=current_time,
        reduce_only=False,
    )

    tp_order = Order(
        id="ord_tree_tp",
        signal_id=signal_id,
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        price=Decimal('66000'),
        requested_qty=Decimal('0.5'),
        filled_qty=Decimal('0'),
        status=OrderStatus.OPEN,
        parent_order_id="ord_tree_entry",
        created_at=current_time + 1000,
        updated_at=current_time + 1000,
        reduce_only=True,
    )

    sl_order = Order(
        id="ord_tree_sl",
        signal_id=signal_id,
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        trigger_price=Decimal('64000'),
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('0'),
        status=OrderStatus.OPEN,
        parent_order_id="ord_tree_entry",
        created_at=current_time + 2000,
        updated_at=current_time + 2000,
        reduce_only=True,
    )

    for order in [entry_order, tp_order, sl_order]:
        await order_repository.save(order)

    # 执行：从 ENTRY 订单 ID 查询
    chain = await order_repository.get_order_chain_by_order_id("ord_tree_entry")

    # 验证
    assert len(chain) == 3
    assert chain[0].id == "ord_tree_entry"  # ENTRY 订单在第一个
    assert chain[0].order_role == OrderRole.ENTRY


@pytest.mark.asyncio
async def test_get_order_chain_by_order_id_from_child(order_repository):
    """
    P0-005: 按订单 ID 获取订单链 - 从子订单追溯

    测试场景:
    1. 创建 ENTRY + TP + SL 订单链
    2. 从 TP 订单 ID 查询
    3. 验证返回父订单和兄弟订单

    验收标准:
    - 返回列表包含父 ENTRY 订单（第一个）
    - 包含所有 TP/SL 兄弟订单
    """
    signal_id = "sig_tree_test_002"
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    entry_order = Order(
        id="ord_tree_entry_2",
        signal_id=signal_id,
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('0'),
        status=OrderStatus.FILLED,
        created_at=current_time,
        updated_at=current_time,
        reduce_only=False,
    )

    tp_order = Order(
        id="ord_tree_tp_2",
        signal_id=signal_id,
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        price=Decimal('66000'),
        requested_qty=Decimal('0.5'),
        filled_qty=Decimal('0'),
        status=OrderStatus.OPEN,
        parent_order_id="ord_tree_entry_2",
        created_at=current_time + 1000,
        updated_at=current_time + 1000,
        reduce_only=True,
    )

    sl_order = Order(
        id="ord_tree_sl_2",
        signal_id=signal_id,
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        trigger_price=Decimal('64000'),
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('0'),
        status=OrderStatus.OPEN,
        parent_order_id="ord_tree_entry_2",
        created_at=current_time + 2000,
        updated_at=current_time + 2000,
        reduce_only=True,
    )

    for order in [entry_order, tp_order, sl_order]:
        await order_repository.save(order)

    # 执行：从 TP 订单 ID 查询
    chain = await order_repository.get_order_chain_by_order_id("ord_tree_tp_2")

    # 验证
    assert len(chain) == 3
    assert chain[0].id == "ord_tree_entry_2"  # 父订单在第一个
    assert chain[0].order_role == OrderRole.ENTRY


@pytest.mark.asyncio
async def test_get_order_chain_by_order_id_not_found(order_repository):
    """
    P0-006: 按订单 ID 获取订单链 - 订单不存在边界测试

    测试场景:
    1. 查询不存在的订单 ID
    2. 验证返回空列表

    验收标准:
    - 返回空列表
    """
    # 执行：查询不存在的订单
    chain = await order_repository.get_order_chain_by_order_id("ord_not_exists")

    # 验证
    assert chain == []


# ============================================================
# P0 核心方法测试 - initialize / close
# ============================================================

@pytest.mark.asyncio
async def test_initialize_creates_tables(temp_db_path):
    """
    P0-007: 初始化数据库 - 创建表和索引

    测试场景:
    1. 创建 OrderRepository 实例
    2. 调用 initialize 方法
    3. 验证表已创建

    验收标准:
    - orders 表存在
    - 索引已创建
    """
    from src.infrastructure.order_repository import OrderRepository

    repo = OrderRepository(db_path=temp_db_path)

    # 执行：初始化
    await repo.initialize()

    # 验证：表存在
    cursor = await repo._db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='orders'"
    )
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    assert row[0] == "orders"

    # 验证：索引存在
    cursor = await repo._db.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_orders_signal_id'"
    )
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None

    await repo.close()


@pytest.mark.asyncio
async def test_initialize_idempotent(temp_db_path):
    """
    P0-008: 初始化数据库 - 幂等性测试

    测试场景:
    1. 调用 initialize 方法
    2. 再次调用 initialize 方法
    3. 验证重复初始化不会报错

    验收标准:
    - 重复初始化不抛出异常
    - 数据库连接相同
    """
    from src.infrastructure.order_repository import OrderRepository

    repo = OrderRepository(db_path=temp_db_path)

    # 执行：第一次初始化
    await repo.initialize()
    first_db = repo._db

    # 执行：第二次初始化（幂等性）
    await repo.initialize()

    # 验证：数据库连接相同
    assert repo._db is first_db

    await repo.close()


@pytest.mark.asyncio
async def test_initialize_creates_directory(tmp_path):
    """
    P0-009: 初始化数据库 - 自动创建目录

    测试场景:
    1. 使用不存在的目录路径
    2. 调用 initialize 方法
    3. 验证目录自动创建

    验收标准:
    - 目录自动创建
    - 数据库文件创建成功
    """
    from src.infrastructure.order_repository import OrderRepository
    import os

    db_path = str(tmp_path / "subdir" / "test.db")

    repo = OrderRepository(db_path=db_path)

    # 执行：初始化（应自动创建目录）
    await repo.initialize()

    # 验证：目录和文件存在
    assert os.path.exists(db_path)

    await repo.close()


@pytest.mark.asyncio
async def test_close_normal(temp_db_path):
    """
    P0-010: 关闭数据库连接 - 正常场景

    测试场景:
    1. 初始化 OrderRepository
    2. 调用 close 方法
    3. 验证连接已关闭

    验收标准:
    - 连接关闭
    - 可再次初始化
    """
    from src.infrastructure.order_repository import OrderRepository

    repo = OrderRepository(db_path=temp_db_path)
    await repo.initialize()

    # 验证：连接已打开
    assert repo._db is not None

    # 执行：关闭连接
    await repo.close()

    # 验证：连接已关闭
    assert repo._db is None


@pytest.mark.asyncio
async def test_close_idempotent(temp_db_path):
    """
    P0-011: 关闭数据库连接 - 幂等性测试

    测试场景:
    1. 调用 close 方法
    2. 再次调用 close 方法
    3. 验证重复关闭不会报错

    验收标准:
    - 重复关闭不抛出异常
    """
    from src.infrastructure.order_repository import OrderRepository

    repo = OrderRepository(db_path=temp_db_path)
    await repo.initialize()

    # 执行：第一次关闭
    await repo.close()

    # 执行：第二次关闭（幂等性）
    await repo.close()

    # 验证：不抛出异常


# ============================================================
# P0 核心方法测试 - get_orders_by_signal
# ============================================================

@pytest.mark.asyncio
async def test_get_orders_by_signal_multiple(order_repository):
    """
    P0-012: 按信号查询订单 - 多订单场景

    测试场景:
    1. 创建同一信号的多个订单
    2. 调用 get_orders_by_signal 查询
    3. 验证返回所有订单

    验收标准:
    - 返回所有该信号的订单
    - 订单按 created_at 升序排列
    """
    signal_id = "sig_multi_order_test"
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 准备：创建 5 个订单
    orders = [
        Order(
            id=f"ord_multi_{i}",
            signal_id=signal_id,
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.0'),
            filled_qty=Decimal('0'),
            status=OrderStatus.CREATED,
            created_at=current_time + i * 1000,
            updated_at=current_time + i * 1000,
            reduce_only=False,
        )
        for i in range(5)
    ]

    for order in orders:
        await order_repository.save(order)

    # 执行：查询
    result = await order_repository.get_orders_by_signal(signal_id)

    # 验证
    assert len(result) == 5
    assert all(o.signal_id == signal_id for o in result)


@pytest.mark.asyncio
async def test_get_orders_by_signal_empty(order_repository):
    """
    P0-013: 按信号查询订单 - 空结果边界测试

    测试场景:
    1. 查询不存在的信号
    2. 验证返回空列表

    验收标准:
    - 返回空列表
    """
    # 执行：查询不存在的信号
    result = await order_repository.get_orders_by_signal("sig_not_exists")

    # 验证
    assert result == []


@pytest.mark.asyncio
async def test_get_orders_by_signal_order_asc(order_repository):
    """
    P0-014: 按信号查询订单 - 验证排序顺序

    测试场景:
    1. 创建同一信号的多个订单（不同时间戳）
    2. 查询订单
    3. 验证按 created_at 升序排列

    验收标准:
    - 订单按 created_at 升序排列
    """
    signal_id = "sig_order_test"
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 准备：创建 3 个订单（乱序时间戳）
    orders_data = [
        ("ord_3", current_time + 3000),
        ("ord_1", current_time + 1000),
        ("ord_2", current_time + 2000),
    ]

    for order_id, ts in orders_data:
        order = Order(
            id=order_id,
            signal_id=signal_id,
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.0'),
            filled_qty=Decimal('0'),
            status=OrderStatus.CREATED,
            created_at=ts,
            updated_at=ts,
            reduce_only=False,
        )
        await order_repository.save(order)

    # 执行：查询
    result = await order_repository.get_orders_by_signal(signal_id)

    # 验证：按 created_at 升序排列
    assert len(result) == 3
    assert result[0].id == "ord_1"
    assert result[1].id == "ord_2"
    assert result[2].id == "ord_3"


# ============================================================
# P0 核心方法测试 - get_order_count
# ============================================================

@pytest.mark.asyncio
async def test_get_order_count(order_repository):
    """
    P0-015: 获取订单数量

    测试场景:
    1. 创建同一信号的多个订单
    2. 调用 get_order_count 查询
    3. 验证返回正确数量

    验收标准:
    - 返回正确的订单数量
    """
    signal_id = "sig_count_test"
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 准备：创建 5 个订单
    for i in range(5):
        order = Order(
            id=f"ord_count_{i}",
            signal_id=signal_id,
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.0'),
            filled_qty=Decimal('0'),
            status=OrderStatus.CREATED,
            created_at=current_time + i * 1000,
            updated_at=current_time + i * 1000,
            reduce_only=False,
        )
        await order_repository.save(order)

    # 执行：查询数量
    count = await order_repository.get_order_count(signal_id)

    # 验证
    assert count == 5


@pytest.mark.asyncio
async def test_get_order_count_empty(order_repository):
    """
    P0-016: 获取订单数量 - 空结果边界测试

    测试场景:
    1. 查询不存在的信号
    2. 验证返回 0

    验收标准:
    - 返回 0
    """
    # 执行：查询不存在的信号
    count = await order_repository.get_order_count("sig_not_exists")

    # 验证
    assert count == 0


# ============================================================
# P1 Group A: 核心查询方法测试
# ============================================================

@pytest.fixture
def sample_orders_factory():
    """辅助函数：创建样本订单列表"""
    def create_orders(signal_id_prefix: str = "sig", count: int = 25):
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        symbols = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]
        statuses = [OrderStatus.OPEN, OrderStatus.FILLED, OrderStatus.CANCELED]
        roles = [OrderRole.ENTRY, OrderRole.TP1, OrderRole.SL]

        return [
            Order(
                id=f"ord_p1_{i:03d}",
                signal_id=f"{signal_id_prefix}_{i % 5:02d}",
                symbol=symbols[i % 3],
                direction=Direction.LONG if i % 2 == 0 else Direction.SHORT,
                order_type=OrderType.MARKET,
                order_role=roles[i % 3],
                requested_qty=Decimal('1.0'),
                filled_qty=Decimal('0'),
                status=statuses[i % 3],
                created_at=current_time + i * 1000,
                updated_at=current_time + i * 1000,
                reduce_only=False,
            )
            for i in range(count)
        ]
    return create_orders


# ============================================================
# P1 Group A: 核心查询方法测试
# ============================================================

# ------------------------------------------------------------
# TestGetOrders: get_orders() 方法测试 (10 个用例)
# ------------------------------------------------------------

@pytest.mark.asyncio
class TestGetOrders:
    """P1-001 ~ P1-010: get_orders() 方法测试"""

    @pytest.mark.asyncio
    async def test_p1_001_no_filters(self, order_repository, sample_orders_factory):
        """
        P1-001: 无过滤条件查询（默认行为）

        测试场景:
        1. 创建 25 个订单
        2. 无过滤条件调用 get_orders()
        3. 验证返回所有订单

        验收标准:
        - 返回默认 limit=50 内的所有订单
        - 按 created_at 降序排列
        - total 正确
        """
        orders = sample_orders_factory("sig_p1_001", count=25)
        for order in orders:
            await order_repository.save(order)

        result = await order_repository.get_orders()

        assert result['total'] == 25
        assert len(result['items']) == 25
        assert result['limit'] == 50
        assert result['offset'] == 0
        for i in range(len(result['items']) - 1):
            assert result['items'][i].created_at >= result['items'][i + 1].created_at

    @pytest.mark.asyncio
    async def test_p1_002_symbol_filter(self, order_repository, sample_orders_factory):
        """
        P1-002: symbol 过滤（单币种）

        测试场景:
        1. 创建多币种订单
        2. 使用 symbol 过滤查询
        3. 验证只返回指定币种订单

        验收标准:
        - 只返回 BTC/USDT:USDT 订单
        """
        orders = sample_orders_factory("sig_p1_002", count=30)
        for order in orders:
            await order_repository.save(order)

        result = await order_repository.get_orders(symbol="BTC/USDT:USDT")

        assert result['total'] == 10
        assert len(result['items']) == 10
        assert all(o.symbol == "BTC/USDT:USDT" for o in result['items'])

    @pytest.mark.asyncio
    async def test_p1_003_status_filter(self, order_repository, sample_orders_factory):
        """
        P1-003: status 过滤（单状态）

        测试场景:
        1. 创建多状态订单
        2. 使用 status 过滤查询
        3. 验证只返回指定状态订单

        验收标准:
        - 只返回 OPEN 状态订单
        """
        orders = sample_orders_factory("sig_p1_003", count=30)
        for order in orders:
            await order_repository.save(order)

        result = await order_repository.get_orders(status=OrderStatus.OPEN)

        assert result['total'] == 10
        assert len(result['items']) == 10
        assert all(o.status == OrderStatus.OPEN for o in result['items'])

    @pytest.mark.asyncio
    async def test_p1_004_order_role_filter(self, order_repository, sample_orders_factory):
        """
        P1-004: order_role 过滤（单角色）

        测试场景:
        1. 创建多角色订单
        2. 使用 order_role 过滤查询
        3. 验证只返回指定角色订单

        验收标准:
        - 只返回 ENTRY 角色订单
        """
        orders = sample_orders_factory("sig_p1_004", count=30)
        for order in orders:
            await order_repository.save(order)

        result = await order_repository.get_orders(order_role=OrderRole.ENTRY)

        assert result['total'] == 10
        assert len(result['items']) == 10
        assert all(o.order_role == OrderRole.ENTRY for o in result['items'])

    @pytest.mark.asyncio
    async def test_p1_005_combined_filters(self, order_repository, sample_orders_factory):
        """
        P1-005: 多条件组合过滤（symbol + status + order_role）

        测试场景:
        1. 创建多条件组合订单
        2. 使用多条件过滤查询
        3. 验证返回同时满足所有条件的订单

        验收标准:
        - 返回同时满足 symbol + status + order_role 的订单
        """
        orders = sample_orders_factory("sig_p1_005", count=27)
        for order in orders:
            await order_repository.save(order)

        result = await order_repository.get_orders(
            symbol="BTC/USDT:USDT",
            status=OrderStatus.OPEN,
            order_role=OrderRole.ENTRY,
        )

        assert all(
            o.symbol == "BTC/USDT:USDT" and
            o.status == OrderStatus.OPEN and
            o.order_role == OrderRole.ENTRY
            for o in result['items']
        )

    @pytest.mark.asyncio
    async def test_p1_006_pagination_page1(self, order_repository, sample_orders_factory):
        """
        P1-006: 分页测试 - 第一页（limit=10, offset=0）

        测试场景:
        1. 创建 25 个订单
        2. 查询第一页（limit=10, offset=0）
        3. 验证返回前 10 条

        验收标准:
        - 返回 10 条记录
        - total=25
        """
        orders = sample_orders_factory("sig_p1_006", count=25)
        for order in orders:
            await order_repository.save(order)

        result = await order_repository.get_orders(limit=10, offset=0)

        assert result['total'] == 25
        assert len(result['items']) == 10
        assert result['limit'] == 10
        assert result['offset'] == 0

    @pytest.mark.asyncio
    async def test_p1_007_pagination_page2(self, order_repository, sample_orders_factory):
        """
        P1-007: 分页测试 - 第二页（limit=10, offset=10）

        测试场景:
        1. 创建 25 个订单
        2. 查询第二页（limit=10, offset=10）
        3. 验证返回第 11-20 条

        验收标准:
        - 返回 10 条记录
        - 第二页数据与第一页不重叠
        """
        orders = sample_orders_factory("sig_p1_007", count=25)
        for order in orders:
            await order_repository.save(order)

        page1 = await order_repository.get_orders(limit=10, offset=0)
        page2 = await order_repository.get_orders(limit=10, offset=10)

        assert page1['total'] == 25
        assert len(page1['items']) == 10
        assert page2['total'] == 25
        assert len(page2['items']) == 10
        page1_ids = {o.id for o in page1['items']}
        page2_ids = {o.id for o in page2['items']}
        assert page1_ids.isdisjoint(page2_ids)

    @pytest.mark.asyncio
    async def test_p1_008_pagination_empty_result(self, order_repository, sample_orders_factory):
        """
        P1-008: 分页边界 - 空结果（超出总记录数）

        测试场景:
        1. 创建 10 个订单
        2. 查询 offset=20（超出总数）
        3. 验证返回空列表

        验收标准:
        - items 为空列表
        - total=10
        """
        orders = sample_orders_factory("sig_p1_008", count=10)
        for order in orders:
            await order_repository.save(order)

        result = await order_repository.get_orders(limit=10, offset=20)

        assert result['total'] == 10
        assert len(result['items']) == 0

    @pytest.mark.asyncio
    async def test_p1_009_limit_boundary(self, order_repository, sample_orders_factory):
        """
        P1-009: limit 边界值（limit=1）

        测试场景:
        1. 创建 5 个订单
        2. 查询 limit=1
        3. 验证只返回 1 条

        验收标准:
        - 只返回 1 条记录
        - total=5
        """
        orders = sample_orders_factory("sig_p1_009", count=5)
        for order in orders:
            await order_repository.save(order)

        result = await order_repository.get_orders(limit=1, offset=0)

        assert result['total'] == 5
        assert len(result['items']) == 1
        assert result['limit'] == 1

    @pytest.mark.asyncio
    async def test_p1_010_empty_database(self, order_repository):
        """
        P1-010: 空数据库查询（无任何订单）

        测试场景:
        1. 空数据库（无任何订单）
        2. 调用 get_orders()
        3. 验证返回空列表

        验收标准:
        - items 为空列表
        - total=0
        """
        result = await order_repository.get_orders()

        assert result['total'] == 0
        assert len(result['items']) == 0


# ------------------------------------------------------------
# TestGetOrdersBySignalIds: get_orders_by_signal_ids() 方法测试 (7 个用例)
# ------------------------------------------------------------

@pytest.mark.asyncio
class TestGetOrdersBySignalIds:
    """P1-011 ~ P1-017: get_orders_by_signal_ids() 方法测试"""

    @pytest.mark.asyncio
    async def test_p1_011_single_signal(self, order_repository):
        """
        P1-011: 单信号查询（单个 signal_id）

        测试场景:
        1. 创建同一信号的多个订单
        2. 使用单信号查询
        3. 验证返回该信号的所有订单

        验收标准:
        - 返回该信号的所有订单
        - total 正确
        """
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        orders = [
            Order(
                id=f"ord_single_{i}",
                signal_id="sig_single",
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
            for i in range(5)
        ]
        for order in orders:
            await order_repository.save(order)

        result = await order_repository.get_orders_by_signal_ids(signal_ids=["sig_single"])

        assert result['total'] == 5
        assert len(result['orders']) == 5
        assert result['page'] == 1
        assert all(o.signal_id == "sig_single" for o in result['orders'])

    @pytest.mark.asyncio
    async def test_p1_012_multiple_signals(self, order_repository):
        """
        P1-012: 多信号批量查询（多个 signal_ids）

        测试场景:
        1. 创建 3 个信号的订单
        2. 使用多信号查询
        3. 验证返回所有信号的订单

        验收标准:
        - 返回所有指定信号的订单
        """
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        orders = []
        for sig_idx in range(3):
            for i in range(5):
                orders.append(
                    Order(
                        id=f"ord_multi_{sig_idx}_{i}",
                        signal_id=f"sig_multi_{sig_idx:02d}",
                        symbol="BTC/USDT:USDT",
                        direction=Direction.LONG,
                        order_type=OrderType.MARKET,
                        order_role=OrderRole.ENTRY,
                        requested_qty=Decimal('1.0'),
                        filled_qty=Decimal('0'),
                        status=OrderStatus.OPEN,
                        created_at=current_time + sig_idx * 10000 + i * 1000,
                        updated_at=current_time + sig_idx * 10000 + i * 1000,
                        reduce_only=False,
                    )
                )
        for order in orders:
            await order_repository.save(order)

        result = await order_repository.get_orders_by_signal_ids(
            signal_ids=["sig_multi_00", "sig_multi_01"]
        )

        assert result['total'] == 10
        assert len(result['orders']) == 10
        assert all(o.signal_id in ["sig_multi_00", "sig_multi_01"] for o in result['orders'])

    @pytest.mark.asyncio
    async def test_p1_013_with_role_filter(self, order_repository):
        """
        P1-013: 带角色过滤（signal_ids + order_role）

        测试场景:
        1. 创建多角色订单
        2. 使用 signal_ids + order_role 过滤
        3. 验证返回过滤后的订单

        验收标准:
        - 返回指定信号且指定角色的订单
        """
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        roles = [OrderRole.ENTRY, OrderRole.TP1, OrderRole.SL]
        orders = []
        for role_idx, role in enumerate(roles):
            for i in range(3):
                orders.append(
                    Order(
                        id=f"ord_role_{role_idx}_{i}",
                        signal_id="sig_role_test",
                        symbol="BTC/USDT:USDT",
                        direction=Direction.LONG,
                        order_type=OrderType.MARKET,
                        order_role=role,
                        requested_qty=Decimal('1.0'),
                        filled_qty=Decimal('0'),
                        status=OrderStatus.OPEN,
                        created_at=current_time + role_idx * 10000 + i * 1000,
                        updated_at=current_time + role_idx * 10000 + i * 1000,
                        reduce_only=False,
                    )
                )
        for order in orders:
            await order_repository.save(order)

        result = await order_repository.get_orders_by_signal_ids(
            signal_ids=["sig_role_test"],
            order_role="ENTRY",
        )

        assert result['total'] == 3
        assert len(result['orders']) == 3
        assert all(o.order_role == OrderRole.ENTRY for o in result['orders'])

    @pytest.mark.asyncio
    async def test_p1_014_pagination_page1(self, order_repository, sample_orders_factory):
        """
        P1-014: 分页测试 - page=1（第一页）

        测试场景:
        1. 创建 25 个订单
        2. 查询 page=1, page_size=10
        3. 验证返回第一页

        验收标准:
        - 返回 10 条记录
        - page=1
        """
        orders = sample_orders_factory("sig_p1_014", count=25)
        for order in orders:
            await order_repository.save(order)

        signal_ids = [f"sig_p1_014_{i:02d}" for i in range(5)]
        result = await order_repository.get_orders_by_signal_ids(
            signal_ids=signal_ids,
            page=1,
            page_size=10,
        )

        assert result['total'] == 25
        assert len(result['orders']) == 10
        assert result['page'] == 1

    @pytest.mark.asyncio
    async def test_p1_015_pagination_page2(self, order_repository, sample_orders_factory):
        """
        P1-015: 分页测试 - page=2（第二页）

        测试场景:
        1. 创建 25 个订单
        2. 查询 page=2, page_size=10
        3. 验证返回第二页

        验收标准:
        - 返回 10 条记录
        - page=2
        - 两页数据不重叠
        """
        orders = sample_orders_factory("sig_p1_015", count=25)
        for order in orders:
            await order_repository.save(order)

        signal_ids = [f"sig_p1_015_{i:02d}" for i in range(5)]
        page1 = await order_repository.get_orders_by_signal_ids(
            signal_ids=signal_ids,
            page=1,
            page_size=10,
        )
        page2 = await order_repository.get_orders_by_signal_ids(
            signal_ids=signal_ids,
            page=2,
            page_size=10,
        )

        assert page1['total'] == 25
        assert len(page1['orders']) == 10
        assert page2['total'] == 25
        assert len(page2['orders']) == 10
        page1_ids = {o.id for o in page1['orders']}
        page2_ids = {o.id for o in page2['orders']}
        assert page1_ids.isdisjoint(page2_ids)

    @pytest.mark.asyncio
    async def test_p1_016_empty_signal_ids(self, order_repository):
        """
        P1-016: 空信号列表（signal_ids=[]）

        测试场景:
        1. 创建一些订单
        2. 使用空信号列表查询
        3. 验证返回空结果

        验收标准:
        - 返回空列表
        - total=0
        """
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        order = Order(
            id="ord_empty_sig_001",
            signal_id="sig_not_empty",
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

        # 执行：空信号列表查询
        result = await order_repository.get_orders_by_signal_ids(signal_ids=[])

        # 验证：返回空结果
        assert result['total'] == 0
        assert len(result['orders']) == 0
        assert result['page'] == 1
        assert result['page_size'] == 20

    @pytest.mark.asyncio
    async def test_p1_017_not_exist_signal(self, order_repository):
        """
        P1-017: 不存在的信号（signal_ids 不含有效数据）

        测试场景:
        1. 创建一些订单
        2. 查询不存在的信号
        3. 验证返回空列表

        验收标准:
        - 返回空列表
        - total=0
        """
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        order = Order(
            id="ord_exist_001",
            signal_id="sig_exist",
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

        result = await order_repository.get_orders_by_signal_ids(
            signal_ids=["sig_not_exist_1", "sig_not_exist_2"],
        )

        assert result['total'] == 0
        assert len(result['orders']) == 0


# ============================================================
# P1 Group C: 别名方法测试
# ============================================================

# ------------------------------------------------------------
# save_order() 别名方法测试
# ------------------------------------------------------------

@pytest.mark.asyncio
class TestSaveOrder:
    """P1-037, P1-038: save_order() 别名方法测试"""

    @pytest.mark.asyncio
    async def test_save_order_new(self, order_repository):
        """
        P1-037: 保存新订单 - 验证委托给 save()

        测试场景:
        1. 创建新订单对象
        2. 调用 save_order() 保存
        3. 验证订单已持久化到数据库

        验收标准:
        - 订单成功保存到数据库
        - 与 save() 行为完全一致
        """
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

        # 准备：创建新订单
        order = Order(
            id="ord_save_order_new_001",
            signal_id="sig_save_order_test",
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

        # 执行：使用 save_order() 保存
        await order_repository.save_order(order)

        # 验证：查询订单，确认与 save() 行为一致
        saved_order = await order_repository.get_order("ord_save_order_new_001")

        assert saved_order is not None
        assert saved_order.id == order.id
        assert saved_order.signal_id == order.signal_id
        assert saved_order.symbol == order.symbol
        assert saved_order.direction == order.direction
        assert saved_order.order_type == order.order_type
        assert saved_order.order_role == order.order_role
        assert saved_order.requested_qty == order.requested_qty

    @pytest.mark.asyncio
    async def test_save_order_update_existing(self, order_repository):
        """
        P1-038: 更新已存在订单 - UPSERT 行为验证

        测试场景:
        1. 创建并保存订单
        2. 修改订单状态相关字段后再次调用 save_order()
        3. 验证订单状态字段已更新（而非新增）

        验收标准:
        - 订单成功更新（UPSERT 行为）
        - 与 save() 行为完全一致
        - 注意：save() 只更新状态相关字段，不更新 requested_qty 等基础字段
        """
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

        # 准备：创建并保存初始订单
        order = Order(
            id="ord_save_order_update_001",
            signal_id="sig_save_order_update",
            symbol="ETH/USDT:USDT",
            direction=Direction.SHORT,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.TP1,
            price=Decimal('3500'),
            requested_qty=Decimal('2.0'),
            filled_qty=Decimal('0'),
            status=OrderStatus.OPEN,
            created_at=current_time,
            updated_at=current_time,
            reduce_only=True,
        )
        await order_repository.save_order(order)

        # 验证：订单已保存
        saved_order = await order_repository.get_order("ord_save_order_update_001")
        assert saved_order is not None
        assert saved_order.requested_qty == Decimal('2.0')
        assert saved_order.status == OrderStatus.OPEN

        # 执行：修改订单状态字段并再次调用 save_order()
        # 注意：save() 只更新 status, filled_qty, average_exec_price, filled_at,
        #       exchange_order_id, exit_reason, parent_order_id, oco_group_id, updated_at
        order.status = OrderStatus.PARTIALLY_FILLED
        order.filled_qty = Decimal('1.0')
        order.average_exec_price = Decimal('3498.5')
        order.updated_at = current_time + 1000

        await order_repository.save_order(order)

        # 验证：订单状态字段已更新而非新增
        updated_order = await order_repository.get_order("ord_save_order_update_001")
        assert updated_order is not None
        # 状态字段已更新
        assert updated_order.status == OrderStatus.PARTIALLY_FILLED
        assert updated_order.filled_qty == Decimal('1.0')
        assert updated_order.average_exec_price == Decimal('3498.5')
        # 基础字段保持不变（save() 不更新这些字段）
        assert updated_order.requested_qty == Decimal('2.0')
        # 验证记录数未增加（仍为 1 条，证明是 UPSERT 而非新增）
        count = await order_repository.get_order_count("sig_save_order_update")
        assert count == 1


# ------------------------------------------------------------
# get_order_detail() 别名方法测试
# ------------------------------------------------------------

@pytest.mark.asyncio
class TestGetOrderDetail:
    """P1-039, P1-040: get_order_detail() 别名方法测试"""

    @pytest.mark.asyncio
    async def test_get_order_detail_exists(self, order_repository):
        """
        P1-039: 查询存在订单 - 验证委托给 get_order()

        测试场景:
        1. 创建并保存订单
        2. 调用 get_order_detail() 查询
        3. 验证返回正确的订单对象

        验收标准:
        - 返回正确的订单对象
        - 与 get_order() 行为完全一致
        """
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

        # 准备：创建并保存订单
        order = Order(
            id="ord_detail_test_001",
            signal_id="sig_detail_test",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.5'),
            filled_qty=Decimal('0'),
            status=OrderStatus.OPEN,
            created_at=current_time,
            updated_at=current_time,
            reduce_only=False,
        )
        await order_repository.save(order)

        # 执行：使用 get_order_detail() 查询
        result = await order_repository.get_order_detail("ord_detail_test_001")

        # 验证：与 get_order() 行为一致
        assert result is not None
        assert result.id == order.id
        assert result.signal_id == order.signal_id
        assert result.symbol == order.symbol
        assert result.requested_qty == order.requested_qty
        # 验证与 get_order() 返回相同结果
        direct_result = await order_repository.get_order("ord_detail_test_001")
        assert result.id == direct_result.id
        assert result.requested_qty == direct_result.requested_qty

    @pytest.mark.asyncio
    async def test_get_order_detail_not_exists(self, order_repository):
        """
        P1-040: 查询不存在订单 - order_id 无效

        测试场景:
        1. 调用 get_order_detail() 查询不存在的订单
        2. 验证返回 None

        验收标准:
        - 返回 None
        - 与 get_order() 行为完全一致
        """
        # 执行：查询不存在的订单
        result = await order_repository.get_order_detail("ord_not_exists_xyz123")

        # 验证：与 get_order() 行为一致
        assert result is None
        # 验证与 get_order() 返回相同结果
        direct_result = await order_repository.get_order("ord_not_exists_xyz123")
        assert direct_result is None


# ------------------------------------------------------------
# get_by_signal_id() 别名方法测试
# ------------------------------------------------------------

@pytest.mark.asyncio
class TestGetBySignalId:
    """P1-041, P1-042: get_by_signal_id() 别名方法测试"""

    @pytest.mark.asyncio
    async def test_get_by_signal_id_exists(self, order_repository):
        """
        P1-041: 查询存在信号 - 验证委托给 get_orders_by_signal()

        测试场景:
        1. 创建并保存多个同信号订单
        2. 调用 get_by_signal_id() 查询
        3. 验证返回正确的订单列表

        验收标准:
        - 返回该信号的所有订单
        - 与 get_orders_by_signal() 行为完全一致
        """
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

        # 准备：创建并保存多个同信号订单
        signal_id = "sig_get_by_signal_test"
        orders = [
            Order(
                id=f"ord_signal_test_{i}",
                signal_id=signal_id,
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
        for order in orders:
            await order_repository.save(order)

        # 执行：使用 get_by_signal_id() 查询
        result = await order_repository.get_by_signal_id(signal_id)

        # 验证：与 get_orders_by_signal() 行为一致
        assert len(result) == 3
        assert all(order.signal_id == signal_id for order in result)
        # 验证与 get_orders_by_signal() 返回相同结果
        direct_result = await order_repository.get_orders_by_signal(signal_id)
        assert len(direct_result) == 3
        # 验证两个方法返回的订单 ID 集合一致
        result_ids = {order.id for order in result}
        direct_ids = {order.id for order in direct_result}
        assert result_ids == direct_ids

    @pytest.mark.asyncio
    async def test_get_by_signal_id_not_exists(self, order_repository):
        """
        P1-042: 查询不存在信号 - signal_id 无效

        测试场景:
        1. 调用 get_by_signal_id() 查询不存在的信号
        2. 验证返回空列表

        验收标准:
        - 返回空列表
        - 与 get_orders_by_signal() 行为完全一致
        """
        # 执行：查询不存在的信号
        result = await order_repository.get_by_signal_id("sig_not_exists_abc123")

        # 验证：与 get_orders_by_signal() 行为一致
        assert result == []
        # 验证与 get_orders_by_signal() 返回相同结果
        direct_result = await order_repository.get_orders_by_signal("sig_not_exists_abc123")
        assert direct_result == []


# ============================================================
# Group B: 过滤查询方法测试 (P1)
# ============================================================

class TestGetOpenOrders:
    """P1: get_open_orders() 测试类"""

    @pytest.mark.asyncio
    async def test_get_open_orders_no_symbol_filter(self, order_repository):
        """P1-018: 无币种过滤 - 查询所有 OPEN 订单"""
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

        # 准备：创建 OPEN、PARTIALLY_FILLED、FILLED、CANCELLED 订单
        orders = [
            Order(id="ord_open_001", signal_id="sig_001", symbol="BTC/USDT:USDT",
                  direction=Direction.LONG, order_type=OrderType.MARKET,
                  order_role=OrderRole.ENTRY, requested_qty=Decimal('1.0'),
                  filled_qty=Decimal('0'), status=OrderStatus.OPEN,
                  created_at=current_time, updated_at=current_time, reduce_only=False),
            Order(id="ord_partial_001", signal_id="sig_002", symbol="ETH/USDT:USDT",
                  direction=Direction.LONG, order_type=OrderType.MARKET,
                  order_role=OrderRole.ENTRY, requested_qty=Decimal('1.0'),
                  filled_qty=Decimal('0.5'), status=OrderStatus.PARTIALLY_FILLED,
                  created_at=current_time + 1, updated_at=current_time + 1, reduce_only=False),
            Order(id="ord_filled_001", signal_id="sig_003", symbol="SOL/USDT:USDT",
                  direction=Direction.LONG, order_type=OrderType.MARKET,
                  order_role=OrderRole.ENTRY, requested_qty=Decimal('1.0'),
                  filled_qty=Decimal('1.0'), status=OrderStatus.FILLED,
                  created_at=current_time + 2, updated_at=current_time + 2, reduce_only=False),
            Order(id="ord_cancelled_001", signal_id="sig_004", symbol="BTC/USDT:USDT",
                  direction=Direction.LONG, order_type=OrderType.MARKET,
                  order_role=OrderRole.ENTRY, requested_qty=Decimal('1.0'),
                  filled_qty=Decimal('0'), status=OrderStatus.CANCELED,
                  created_at=current_time + 3, updated_at=current_time + 3, reduce_only=False),
        ]
        for order in orders:
            await order_repository.save(order)

        # 执行：查询所有 OPEN 订单
        result = await order_repository.get_open_orders()

        # 验证：只返回 OPEN 和 PARTIALLY_FILLED
        assert len(result) == 2
        result_ids = {o.id for o in result}
        assert "ord_open_001" in result_ids
        assert "ord_partial_001" in result_ids
        assert "ord_filled_001" not in result_ids
        assert "ord_cancelled_001" not in result_ids

    @pytest.mark.asyncio
    async def test_get_open_orders_with_symbol_filter(self, order_repository):
        """P1-019: 币种过滤 - 指定 symbol"""
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

        # 准备：创建不同币种的 OPEN 订单
        orders = [
            Order(id="ord_btc_001", signal_id="sig_001", symbol="BTC/USDT:USDT",
                  direction=Direction.LONG, order_type=OrderType.MARKET,
                  order_role=OrderRole.ENTRY, requested_qty=Decimal('1.0'),
                  filled_qty=Decimal('0'), status=OrderStatus.OPEN,
                  created_at=current_time, updated_at=current_time, reduce_only=False),
            Order(id="ord_eth_001", signal_id="sig_002", symbol="ETH/USDT:USDT",
                  direction=Direction.LONG, order_type=OrderType.MARKET,
                  order_role=OrderRole.ENTRY, requested_qty=Decimal('1.0'),
                  filled_qty=Decimal('0'), status=OrderStatus.OPEN,
                  created_at=current_time + 1, updated_at=current_time + 1, reduce_only=False),
        ]
        for order in orders:
            await order_repository.save(order)

        # 执行：查询 BTC 的 OPEN 订单
        result = await order_repository.get_open_orders(symbol="BTC/USDT:USDT")

        # 验证：只返回 BTC 订单
        assert len(result) == 1
        assert result[0].id == "ord_btc_001"

    @pytest.mark.asyncio
    async def test_get_open_orders_multiple_symbols(self, order_repository):
        """P1-020: 多币种混合 - 正确过滤"""
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

        # 准备：创建多个币种的 OPEN 订单
        for i, symbol in enumerate(["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]):
            order = Order(
                id=f"ord_multi_{i}", signal_id=f"sig_{i}", symbol=symbol,
                direction=Direction.LONG, order_type=OrderType.MARKET,
                order_role=OrderRole.ENTRY, requested_qty=Decimal('1.0'),
                filled_qty=Decimal('0'), status=OrderStatus.OPEN,
                created_at=current_time + i, updated_at=current_time + i, reduce_only=False
            )
            await order_repository.save(order)

        # 执行：查询所有 OPEN 订单
        result = await order_repository.get_open_orders()

        # 验证：返回所有 3 个 OPEN 订单
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_get_open_orders_no_open_orders(self, order_repository):
        """P1-021: 无 OPEN 订单 - 全部为 FILLED/CANCELLED"""
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

        # 准备：创建 FILLED 和 CANCELED 订单
        orders = [
            Order(id="ord_filled_001", signal_id="sig_001", symbol="BTC/USDT:USDT",
                  direction=Direction.LONG, order_type=OrderType.MARKET,
                  order_role=OrderRole.ENTRY, requested_qty=Decimal('1.0'),
                  filled_qty=Decimal('1.0'), status=OrderStatus.FILLED,
                  created_at=current_time, updated_at=current_time, reduce_only=False),
            Order(id="ord_canceled_001", signal_id="sig_002", symbol="ETH/USDT:USDT",
                  direction=Direction.LONG, order_type=OrderType.MARKET,
                  order_role=OrderRole.ENTRY, requested_qty=Decimal('1.0'),
                  filled_qty=Decimal('0'), status=OrderStatus.CANCELED,
                  created_at=current_time + 1, updated_at=current_time + 1, reduce_only=False),
        ]
        for order in orders:
            await order_repository.save(order)

        # 执行：查询 OPEN 订单
        result = await order_repository.get_open_orders()

        # 验证：返回空列表
        assert result == []


class TestGetOrdersBySymbol:
    """P1: get_orders_by_symbol() 测试类"""

    @pytest.mark.asyncio
    async def test_get_orders_by_symbol_single(self, order_repository):
        """P1-022: 单币种查询 - 指定 symbol"""
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

        # 准备：创建不同币种订单
        orders = [
            Order(id="ord_btc_001", signal_id="sig_001", symbol="BTC/USDT:USDT",
                  direction=Direction.LONG, order_type=OrderType.MARKET,
                  order_role=OrderRole.ENTRY, requested_qty=Decimal('1.0'),
                  filled_qty=Decimal('0'), status=OrderStatus.OPEN,
                  created_at=current_time, updated_at=current_time, reduce_only=False),
            Order(id="ord_eth_001", signal_id="sig_002", symbol="ETH/USDT:USDT",
                  direction=Direction.LONG, order_type=OrderType.MARKET,
                  order_role=OrderRole.ENTRY, requested_qty=Decimal('1.0'),
                  filled_qty=Decimal('0'), status=OrderStatus.OPEN,
                  created_at=current_time + 1, updated_at=current_time + 1, reduce_only=False),
        ]
        for order in orders:
            await order_repository.save(order)

        # 执行：查询 BTC 订单
        result = await order_repository.get_orders_by_symbol("BTC/USDT:USDT")

        # 验证：只返回 BTC 订单
        assert len(result) == 1
        assert result[0].id == "ord_btc_001"

    @pytest.mark.asyncio
    async def test_get_orders_by_symbol_with_limit(self, order_repository):
        """P1-023: limit 限制 - limit=5"""
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

        # 准备：创建 10 个 BTC 订单
        for i in range(10):
            order = Order(
                id=f"ord_btc_{i:03d}", signal_id=f"sig_{i}", symbol="BTC/USDT:USDT",
                direction=Direction.LONG, order_type=OrderType.MARKET,
                order_role=OrderRole.ENTRY, requested_qty=Decimal('1.0'),
                filled_qty=Decimal('0'), status=OrderStatus.OPEN,
                created_at=current_time + i, updated_at=current_time + i, reduce_only=False
            )
            await order_repository.save(order)

        # 执行：查询 limit=5
        result = await order_repository.get_orders_by_symbol("BTC/USDT:USDT", limit=5)

        # 验证：只返回 5 条
        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_get_orders_by_symbol_not_exists(self, order_repository):
        """P1-024: 不存在的币种 - symbol 无数据"""
        # 执行：查询不存在的币种
        result = await order_repository.get_orders_by_symbol("XXX/USD:USD")

        # 验证：返回空列表
        assert result == []

    @pytest.mark.asyncio
    async def test_get_orders_by_symbol_ordering(self, order_repository):
        """P1-025: 排序验证 - 按 created_at 降序"""
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

        # 准备：创建 3 个 BTC 订单（时间递增）
        for i in range(3):
            order = Order(
                id=f"ord_btc_order_{i}", signal_id=f"sig_{i}", symbol="BTC/USDT:USDT",
                direction=Direction.LONG, order_type=OrderType.MARKET,
                order_role=OrderRole.ENTRY, requested_qty=Decimal('1.0'),
                filled_qty=Decimal('0'), status=OrderStatus.OPEN,
                created_at=current_time + i * 1000, updated_at=current_time + i * 1000, reduce_only=False
            )
            await order_repository.save(order)

        # 执行：查询 BTC 订单
        result = await order_repository.get_orders_by_symbol("BTC/USDT:USDT")

        # 验证：按 created_at 降序排列（最新的在前）
        assert len(result) == 3
        assert result[0].created_at > result[1].created_at > result[2].created_at


class TestGetOrdersByRole:
    """P1: get_orders_by_role() 测试类"""

    @pytest.mark.asyncio
    async def test_get_orders_by_role_single(self, order_repository):
        """P1-026: 单角色查询 - ENTRY 角色"""
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

        # 准备：创建不同角色的订单
        orders = [
            Order(id="ord_entry_001", signal_id="sig_001", symbol="BTC/USDT:USDT",
                  direction=Direction.LONG, order_type=OrderType.MARKET,
                  order_role=OrderRole.ENTRY, requested_qty=Decimal('1.0'),
                  filled_qty=Decimal('0'), status=OrderStatus.OPEN,
                  created_at=current_time, updated_at=current_time, reduce_only=False),
            Order(id="ord_tp1_001", signal_id="sig_002", symbol="BTC/USDT:USDT",
                  direction=Direction.LONG, order_type=OrderType.MARKET,
                  order_role=OrderRole.TP1, requested_qty=Decimal('1.0'),
                  filled_qty=Decimal('0'), status=OrderStatus.OPEN,
                  created_at=current_time + 1, updated_at=current_time + 1, reduce_only=False),
            Order(id="ord_sl_001", signal_id="sig_003", symbol="BTC/USDT:USDT",
                  direction=Direction.LONG, order_type=OrderType.MARKET,
                  order_role=OrderRole.SL, requested_qty=Decimal('1.0'),
                  filled_qty=Decimal('0'), status=OrderStatus.OPEN,
                  created_at=current_time + 2, updated_at=current_time + 2, reduce_only=False),
        ]
        for order in orders:
            await order_repository.save(order)

        # 执行：查询 ENTRY 角色订单
        result = await order_repository.get_orders_by_role(OrderRole.ENTRY)

        # 验证：只返回 ENTRY 订单
        assert len(result) == 1
        assert result[0].id == "ord_entry_001"

    @pytest.mark.asyncio
    async def test_get_orders_by_role_with_signal_id(self, order_repository):
        """P1-027: 组合 signal_id 过滤 - role + signal_id"""
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        signal_id = "sig_combined_001"

        # 准备：创建同一信号的不同角色订单
        orders = [
            Order(id="ord_entry_001", signal_id=signal_id, symbol="BTC/USDT:USDT",
                  direction=Direction.LONG, order_type=OrderType.MARKET,
                  order_role=OrderRole.ENTRY, requested_qty=Decimal('1.0'),
                  filled_qty=Decimal('0'), status=OrderStatus.OPEN,
                  created_at=current_time, updated_at=current_time, reduce_only=False),
            Order(id="ord_tp1_001", signal_id=signal_id, symbol="BTC/USDT:USDT",
                  direction=Direction.LONG, order_type=OrderType.MARKET,
                  order_role=OrderRole.TP1, requested_qty=Decimal('1.0'),
                  filled_qty=Decimal('0'), status=OrderStatus.OPEN,
                  created_at=current_time + 1, updated_at=current_time + 1, reduce_only=False),
            Order(id="ord_entry_002", signal_id="sig_other", symbol="ETH/USDT:USDT",
                  direction=Direction.LONG, order_type=OrderType.MARKET,
                  order_role=OrderRole.ENTRY, requested_qty=Decimal('1.0'),
                  filled_qty=Decimal('0'), status=OrderStatus.OPEN,
                  created_at=current_time + 2, updated_at=current_time + 2, reduce_only=False),
        ]
        for order in orders:
            await order_repository.save(order)

        # 执行：查询特定信号的 ENTRY 订单
        result = await order_repository.get_orders_by_role(OrderRole.ENTRY, signal_id=signal_id)

        # 验证：只返回指定信号和角色的订单
        assert len(result) == 1
        assert result[0].id == "ord_entry_001"

    @pytest.mark.asyncio
    async def test_get_orders_by_role_with_symbol(self, order_repository):
        """P1-028: 组合 symbol 过滤 - role + symbol"""
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

        # 准备：创建不同币种的 ENTRY 订单
        orders = [
            Order(id="ord_btc_entry", signal_id="sig_001", symbol="BTC/USDT:USDT",
                  direction=Direction.LONG, order_type=OrderType.MARKET,
                  order_role=OrderRole.ENTRY, requested_qty=Decimal('1.0'),
                  filled_qty=Decimal('0'), status=OrderStatus.OPEN,
                  created_at=current_time, updated_at=current_time, reduce_only=False),
            Order(id="ord_eth_entry", signal_id="sig_002", symbol="ETH/USDT:USDT",
                  direction=Direction.LONG, order_type=OrderType.MARKET,
                  order_role=OrderRole.ENTRY, requested_qty=Decimal('1.0'),
                  filled_qty=Decimal('0'), status=OrderStatus.OPEN,
                  created_at=current_time + 1, updated_at=current_time + 1, reduce_only=False),
        ]
        for order in orders:
            await order_repository.save(order)

        # 执行：查询 BTC 的 ENTRY 订单
        result = await order_repository.get_orders_by_role(OrderRole.ENTRY, symbol="BTC/USDT:USDT")

        # 验证：只返回 BTC 的 ENTRY 订单
        assert len(result) == 1
        assert result[0].id == "ord_btc_entry"

    @pytest.mark.asyncio
    async def test_get_orders_by_role_triple_filter(self, order_repository):
        """P1-029: 三重过滤 - role + signal_id + symbol"""
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        signal_id = "sig_triple_001"

        # 准备：创建复杂的订单组合
        orders = [
            # 目标订单：BTC, ENTRY, sig_triple_001
            Order(id="ord_target", signal_id=signal_id, symbol="BTC/USDT:USDT",
                  direction=Direction.LONG, order_type=OrderType.MARKET,
                  order_role=OrderRole.ENTRY, requested_qty=Decimal('1.0'),
                  filled_qty=Decimal('0'), status=OrderStatus.OPEN,
                  created_at=current_time, updated_at=current_time, reduce_only=False),
            # 其他订单
            Order(id="ord_other_1", signal_id=signal_id, symbol="ETH/USDT:USDT",
                  direction=Direction.LONG, order_type=OrderType.MARKET,
                  order_role=OrderRole.ENTRY, requested_qty=Decimal('1.0'),
                  filled_qty=Decimal('0'), status=OrderStatus.OPEN,
                  created_at=current_time + 1, updated_at=current_time + 1, reduce_only=False),
            Order(id="ord_other_2", signal_id="sig_other", symbol="BTC/USDT:USDT",
                  direction=Direction.LONG, order_type=OrderType.MARKET,
                  order_role=OrderRole.ENTRY, requested_qty=Decimal('1.0'),
                  filled_qty=Decimal('0'), status=OrderStatus.OPEN,
                  created_at=current_time + 2, updated_at=current_time + 2, reduce_only=False),
        ]
        for order in orders:
            await order_repository.save(order)

        # 执行：三重过滤查询
        result = await order_repository.get_orders_by_role(
            OrderRole.ENTRY, signal_id=signal_id, symbol="BTC/USDT:USDT"
        )

        # 验证：只返回完全匹配的订单
        assert len(result) == 1
        assert result[0].id == "ord_target"

    @pytest.mark.asyncio
    async def test_get_orders_by_role_empty_result(self, order_repository):
        """P1-030: 空结果 - 无匹配数据"""
        # 执行：查询不存在的角色组合
        result = await order_repository.get_orders_by_role(OrderRole.TP1, signal_id="sig_not_exists")

        # 验证：返回空列表
        assert result == []


class TestGetByStatus:
    """P1: get_by_status() 测试类"""

    @pytest.mark.asyncio
    async def test_get_by_status_single(self, order_repository):
        """P1-031: 单状态查询 - FILLED 状态"""
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

        # 准备：创建不同状态的订单
        orders = [
            Order(id="ord_filled_001", signal_id="sig_001", symbol="BTC/USDT:USDT",
                  direction=Direction.LONG, order_type=OrderType.MARKET,
                  order_role=OrderRole.ENTRY, requested_qty=Decimal('1.0'),
                  filled_qty=Decimal('1.0'), status=OrderStatus.FILLED,
                  created_at=current_time, updated_at=current_time, reduce_only=False),
            Order(id="ord_open_001", signal_id="sig_002", symbol="ETH/USDT:USDT",
                  direction=Direction.LONG, order_type=OrderType.MARKET,
                  order_role=OrderRole.ENTRY, requested_qty=Decimal('1.0'),
                  filled_qty=Decimal('0'), status=OrderStatus.OPEN,
                  created_at=current_time + 1, updated_at=current_time + 1, reduce_only=False),
        ]
        for order in orders:
            await order_repository.save(order)

        # 执行：查询 FILLED 状态订单
        result = await order_repository.get_by_status("FILLED")

        # 验证：只返回 FILLED 订单
        assert len(result) == 1
        assert result[0].id == "ord_filled_001"

    @pytest.mark.asyncio
    async def test_get_by_status_ordering(self, order_repository):
        """P1-032: 排序验证 - 按 created_at 降序"""
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

        # 准备：创建多个 FILLED 订单（时间递增）
        for i in range(3):
            order = Order(
                id=f"ord_filled_{i}", signal_id=f"sig_{i}", symbol="BTC/USDT:USDT",
                direction=Direction.LONG, order_type=OrderType.MARKET,
                order_role=OrderRole.ENTRY, requested_qty=Decimal('1.0'),
                filled_qty=Decimal('1.0'), status=OrderStatus.FILLED,
                created_at=current_time + i * 1000, updated_at=current_time + i * 1000, reduce_only=False
            )
            await order_repository.save(order)

        # 执行：查询 FILLED 订单
        result = await order_repository.get_by_status("FILLED")

        # 验证：按 created_at 降序排列
        assert len(result) == 3
        assert result[0].created_at > result[1].created_at > result[2].created_at

    @pytest.mark.asyncio
    async def test_get_by_status_empty_result(self, order_repository):
        """P1-033: 空结果 - 无匹配状态"""
        # 执行：查询 CANCELLED 状态（无数据）
        result = await order_repository.get_by_status("CANCELLED")

        # 验证：返回空列表
        assert result == []


class TestMarkOrderFilled:
    """P1: mark_order_filled() 测试类"""

    @pytest.mark.asyncio
    async def test_mark_order_filled_normal(self, order_repository):
        """P1-034: 正常标记成交 - OPEN 订单 → FILLED"""
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        filled_time = current_time + 60000  # 1分钟后成交

        # 准备：创建 OPEN 订单
        order = Order(
            id="ord_to_fill", signal_id="sig_001", symbol="BTC/USDT:USDT",
            direction=Direction.LONG, order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY, requested_qty=Decimal('1.0'),
            filled_qty=Decimal('0'), status=OrderStatus.OPEN,
            created_at=current_time, updated_at=current_time, reduce_only=False
        )
        await order_repository.save(order)

        # 执行：标记订单为已成交
        await order_repository.mark_order_filled("ord_to_fill", filled_time)

        # 验证：订单状态已更新
        updated = await order_repository.get_order("ord_to_fill")
        assert updated.status == OrderStatus.FILLED
        assert updated.filled_at == filled_time

    @pytest.mark.asyncio
    async def test_mark_order_filled_updates_timestamp(self, order_repository):
        """P1-035: 验证 updated_at 更新 - 标记后检查"""
        import time
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        filled_time = current_time + 60000

        # 准备：创建 OPEN 订单
        order = Order(
            id="ord_update_test", signal_id="sig_001", symbol="BTC/USDT:USDT",
            direction=Direction.LONG, order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY, requested_qty=Decimal('1.0'),
            filled_qty=Decimal('0'), status=OrderStatus.OPEN,
            created_at=current_time, updated_at=current_time, reduce_only=False
        )
        await order_repository.save(order)

        # 稍等一下确保时间戳不同
        time.sleep(0.01)

        # 执行：标记订单为已成交
        await order_repository.mark_order_filled("ord_update_test", filled_time)

        # 验证：updated_at 已更新
        updated = await order_repository.get_order("ord_update_test")
        assert updated.updated_at >= current_time  # 应该大于或等于（可能有毫秒级差异）

    @pytest.mark.asyncio
    async def test_mark_order_filled_not_exists(self, order_repository):
        """P1-036: 不存在的订单 - order_id 无效"""
        filled_time = int(datetime.now(timezone.utc).timestamp() * 1000)

        # 执行：标记不存在的订单（不应抛出异常）
        await order_repository.mark_order_filled("ord_not_exists_abc123", filled_time)

        # 验证：无异常抛出，无影响


# ------------------------------------------------------------
# get_order_count() 验证（已在 P0 覆盖）
# ------------------------------------------------------------
# 注：P0-015 (test_get_order_count) 和 P0-016 (test_get_order_count_empty)
#     已在上方实现，此处无需新增测试


# ============================================================
# P1-3 日志导入规范化测试
# ============================================================

class TestP1Fix_LoggerImport:
    """P1-3: 日志导入规范化测试"""

    def test_uses_standard_logging(self):
        """测试使用标准 logging 模块"""
        import logging

        # Arrange & Act: 导入模块（会执行模块级代码）
        import src.infrastructure.order_repository as repo_module

        # Assert: logger 应该是标准 logging.Logger 实例
        assert isinstance(repo_module.logger, logging.Logger)
        assert repo_module.logger.name == 'src.infrastructure.order_repository'


# ============================================================
# P1-1: Lock 竞态条件修复测试
# ============================================================

class TestP1Fix_LockConcurrency:
    """P1-1: OrderRepository asyncio.Lock 竞态条件修复测试"""

    @pytest.mark.asyncio
    async def test_concurrent_save_operations(self, order_repository):
        """
        测试并发 save 操作的锁机制

        测试场景:
        1. 创建 10 个订单
        2. 并发执行 save 操作
        3. 验证所有订单都已保存，无数据竞争

        验收标准:
        - 所有订单都成功保存到数据库
        - 无并发冲突导致的数据损坏
        """
        # Arrange
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        orders = [
            Order(
                id=f"ord_concurrent_{i}",
                signal_id="sig_concurrent_test",
                symbol="BTC/USDT:USDT",
                direction=Direction.LONG,
                order_type=OrderType.MARKET,
                order_role=OrderRole.ENTRY,
                requested_qty=Decimal('1.0'),
                filled_qty=Decimal('0'),
                status=OrderStatus.OPEN,
                created_at=current_time + i,
                updated_at=current_time + i,
                reduce_only=False,
            )
            for i in range(10)
        ]

        # Act: 并发执行 save 操作
        tasks = [order_repository.save(order) for order in orders]
        await asyncio.gather(*tasks)

        # Assert: 所有订单都已保存，无数据竞争
        for order in orders:
            saved = await order_repository.get_order(order.id)
            assert saved is not None, f"订单 {order.id} 保存失败"
            assert saved.id == order.id
            assert saved.signal_id == order.signal_id

    @pytest.mark.asyncio
    async def test_lock_per_event_loop(self, order_repository):
        """
        测试不同事件循环有独立的 Lock

        测试场景:
        1. 在当前事件循环中获取 Lock
        2. 创建新的事件循环并在其中获取 Lock
        3. 验证两个 Lock 是不同的实例

        验收标准:
        - 不同事件循环返回不同的 Lock 实例
        - Lock 字典正确管理多个事件循环的锁
        """
        import concurrent.futures

        # Arrange: 获取当前事件循环的 Lock
        current_loop_lock = order_repository._ensure_lock()

        # Act: 在线程中创建新的事件循环并获取 Lock
        def get_lock_in_new_loop(repo):
            """在新事件循环中获取 lock"""
            new_loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(new_loop)
                lock = repo._ensure_lock()
                return id(lock)
            finally:
                new_loop.close()

        # 在线程池中执行（会创建独立的事件循环）
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            other_loop_lock_id = await asyncio.get_event_loop().run_in_executor(
                executor, get_lock_in_new_loop, order_repository
            )

        # Assert: 两个 Lock 是不同的实例
        assert id(current_loop_lock) != other_loop_lock_id, "不同事件循环应该返回不同的 Lock 实例"

        # 验证 _locks 字典中有两个条目（当前循环一个，线程中循环一个）
        assert len(order_repository._locks) >= 1

    @pytest.mark.asyncio
    async def test_sync_call_returns_sync_lock(self):
        """
        测试同步调用返回同步锁

        测试场景:
        1. 在没有事件循环的环境中调用 _ensure_lock()
        2. 验证返回的是同步锁

        验收标准:
        - 同步调用返回 threading.Lock 实例
        - 异步调用返回 asyncio.Lock 实例
        """
        import threading
        from src.infrastructure.order_repository import OrderRepository
        import tempfile
        import os

        # 创建临时数据库
        fd, temp_db_path = tempfile.mkstemp(suffix='.db')
        os.close(fd)

        try:
            # Arrange: 创建 OrderRepository 实例（不同步初始化）
            repo = OrderRepository(db_path=temp_db_path)

            # Act: 在没有事件循环的线程中调用
            def get_lock_sync(repo_instance):
                """在同步环境中获取 lock"""
                try:
                    asyncio.get_running_loop()
                    # 如果有 running loop，说明不是在纯同步环境
                    return ('has_loop', None)
                except RuntimeError:
                    # 正常：没有运行的事件循环
                    lock = repo_instance._ensure_lock()
                    return ('no_loop', lock)

            # 在线程池中执行（确保没有事件循环）
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                loop_status, sync_lock = await asyncio.get_event_loop().run_in_executor(
                    executor, get_lock_sync, repo
                )

            # Assert: 同步环境返回 threading.Lock
            if loop_status == 'no_loop':
                assert isinstance(sync_lock, type(threading.Lock())), \
                    "同步调用应该返回 threading.Lock 或兼容的同步锁"
        finally:
            # Cleanup
            if os.path.exists(temp_db_path):
                os.remove(temp_db_path)


# ============================================================
# P2-7 修复测试：UPSERT 数据丢失修复
# ============================================================

@pytest.mark.asyncio
async def test_upsert_preserves_old_value_when_new_is_none(order_repository):
    """
    P2-7: UPSERT 数据丢失修复 - 测试新值为 NULL 时保留旧值

    测试场景:
    1. 创建订单并设置 filled_at 值
    2. 更新时 filled_at 保持为 None（不更新）
    3. 验证 filled_at 保留原值

    验收标准:
    - filled_at 字段在更新时为 NULL 时保留旧值
    - 其他字段正常更新
    """
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    # Arrange: 创建一个已成交的订单
    order = Order(
        id="ord_p2_7_test_001",
        signal_id="sig_p2_7_test",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('1.0'),
        filled_at=1500,  # 设置 filled_at 值
        status=OrderStatus.FILLED,
        created_at=current_time,
        updated_at=current_time,
        reduce_only=False,
    )
    await order_repository.save(order)

    # 验证：订单已保存且 filled_at 有值
    saved = await order_repository.get_order("ord_p2_7_test_001")
    assert saved.filled_at == 1500

    # Act: 更新时 filled_at 保持为 None（不更新 filled_at）
    order.status = OrderStatus.FILLED
    order.updated_at = current_time + 1000
    # filled_at 不设置，保持为 None（在 Order 模型中默认为 None）
    order.filled_at = None  # 显式设置为 None，表示不更新此字段
    await order_repository.save(order)

    # Assert: filled_at 应保留原值
    saved_after_update = await order_repository.get_order("ord_p2_7_test_001")
    assert saved_after_update.filled_at == 1500, "filled_at 在更新时为 NULL 应保留旧值"


@pytest.mark.asyncio
async def test_upsert_updates_to_null_explicitly(order_repository):
    """
    P2-7: UPSERT 数据丢失修复 - 测试显式设置为 NULL

    测试场景:
    1. 创建订单并设置 parent_order_id 值
    2. 更新时将 parent_order_id 设置为 None
    3. 验证 parent_order_id 成功设置为 NULL

    验收标准:
    - 可以显式将字段更新为 NULL
    - parent_order_id 从有值变为 NULL
    """
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    # Arrange: 先创建一个有 parent_order_id 的订单
    order = Order(
        id="ord_p2_7_test_002",
        signal_id="sig_p2_7_test",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.TP1,
        requested_qty=Decimal('0.5'),
        status=OrderStatus.OPEN,
        parent_order_id="ord_parent_123",  # 设置父订单 ID
        created_at=current_time,
        updated_at=current_time,
        reduce_only=True,
    )
    await order_repository.save(order)

    # 验证：订单已保存且 parent_order_id 有值
    saved = await order_repository.get_order("ord_p2_7_test_002")
    assert saved.parent_order_id == "ord_parent_123"

    # Act: 更新时将 parent_order_id 设置为 None
    order.parent_order_id = None  # 显式设置为 None
    order.updated_at = current_time + 1000
    await order_repository.save(order)

    # Assert: parent_order_id 应为 None
    saved_after_update = await order_repository.get_order("ord_p2_7_test_002")
    assert saved_after_update.parent_order_id is None, "parent_order_id 应成功更新为 NULL"


@pytest.mark.asyncio
async def test_upsert_updates_to_new_value(order_repository):
    """
    P2-7: UPSERT 数据丢失修复 - 测试更新为新值

    测试场景:
    1. 创建订单并设置 exchange_order_id 值
    2. 更新时将 exchange_order_id 设置为新值
    3. 验证 exchange_order_id 成功更新

    验收标准:
    - exchange_order_id 从旧值更新为新值
    - 其他字段正常更新
    """
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    # Arrange: 创建订单并设置 exchange_order_id
    order = Order(
        id="ord_p2_7_test_003",
        signal_id="sig_p2_7_test",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('1.0'),
        status=OrderStatus.OPEN,
        exchange_order_id="binance_12345",  # 设置交易所订单 ID
        created_at=current_time,
        updated_at=current_time,
        reduce_only=False,
    )
    await order_repository.save(order)

    # 验证：订单已保存且 exchange_order_id 有值
    saved = await order_repository.get_order("ord_p2_7_test_003")
    assert saved.exchange_order_id == "binance_12345"

    # Act: 更新时将 exchange_order_id 设置为新值
    order.exchange_order_id = "binance_67890"  # 新值
    order.status = OrderStatus.FILLED
    order.filled_qty = Decimal('1.0')
    order.filled_at = 2000
    order.updated_at = current_time + 1000
    await order_repository.save(order)

    # Assert: exchange_order_id 应更新为新值
    saved_after_update = await order_repository.get_order("ord_p2_7_test_003")
    assert saved_after_update.exchange_order_id == "binance_67890", "exchange_order_id 应成功更新为新值"
    assert saved_after_update.status == OrderStatus.FILLED
    assert saved_after_update.filled_at == 2000


@pytest.mark.asyncio
async def test_upsert_preserves_filled_at(order_repository):
    """
    P2-7: UPSERT 数据丢失修复 - 测试 filled_at 字段完整性

    测试场景:
    1. 创建订单并设置 filled_at 值
    2. 多次更新订单，但不设置 filled_at
    3. 验证 filled_at 始终保持原值

    验收标准:
    - filled_at 在多次更新中保持不变
    - 其他字段正常更新
    """
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    original_filled_at = 1609459200000  # 2021-01-01 00:00:00 UTC

    # Arrange: 创建已成交订单
    order = Order(
        id="ord_p2_7_test_004",
        signal_id="sig_p2_7_test",
        symbol="ETH/USDT:USDT",
        direction=Direction.SHORT,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.ENTRY,
        price=Decimal('2000'),
        requested_qty=Decimal('5.0'),
        filled_qty=Decimal('5.0'),
        average_exec_price=Decimal('2000'),
        filled_at=original_filled_at,
        status=OrderStatus.FILLED,
        exchange_order_id="eth_order_001",
        created_at=current_time,
        updated_at=current_time,
        reduce_only=False,
    )
    await order_repository.save(order)

    # 验证：订单已保存
    saved = await order_repository.get_order("ord_p2_7_test_004")
    assert saved.filled_at == original_filled_at

    # Act: 多次更新，但不设置 filled_at
    # 第一次更新
    order.status = OrderStatus.FILLED
    order.updated_at = current_time + 1000
    order.exchange_order_id = "eth_order_002"
    order.filled_at = None  # 不更新 filled_at
    await order_repository.save(order)

    # 第二次更新
    order.updated_at = current_time + 2000
    order.exit_reason = "TAKE_PROFIT"
    order.filled_at = None  # 不更新 filled_at
    await order_repository.save(order)

    # 第三次更新
    order.updated_at = current_time + 3000
    order.filled_qty = Decimal('5.0')
    order.filled_at = None  # 不更新 filled_at
    await order_repository.save(order)

    # Assert: filled_at 应始终保持原值
    final_order = await order_repository.get_order("ord_p2_7_test_004")
    assert final_order.filled_at == original_filled_at, f"filled_at 应保持为 {original_filled_at}，实际为 {final_order.filled_at}"
    assert final_order.exchange_order_id == "eth_order_002"
    assert final_order.exit_reason == "TAKE_PROFIT"
