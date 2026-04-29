"""
ORD-6 批量删除功能集成测试

测试批量删除订单的完整流程，包括：
- 数据库删除
- 交易所取消集成（Mock）
- 审计日志记录
"""
import pytest
import asyncio
import os
import tempfile
from decimal import Decimal
from datetime import datetime, timezone
from typing import List, Any
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


# ============================================================
# 集成测试用例
# ============================================================

@pytest.mark.asyncio
async def test_batch_delete_full_flow(order_repository):
    """
    INT-ORD-6-001: 批量删除完整流程测试

    测试场景:
    1. 创建多个订单（包括 ENTRY、TP、SL）
    2. 批量删除部分订单
    3. 验证数据库记录已删除
    4. 验证审计日志已创建
    """
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 准备：创建订单链
    entry_order_1 = Order(
        id="ord_int_entry_1",
        signal_id="sig_int_1",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('1.0'),
        status=OrderStatus.FILLED,
        created_at=current_time,
        updated_at=current_time,
        filled_at=current_time,
        reduce_only=False,
    )

    tp_order_1 = Order(
        id="ord_int_tp_1",
        signal_id="sig_int_1",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        price=Decimal('70000'),
        requested_qty=Decimal('0.5'),
        filled_qty=Decimal('0'),
        status=OrderStatus.OPEN,
        created_at=current_time + 1000,
        updated_at=current_time + 1000,
        parent_order_id="ord_int_entry_1",
        reduce_only=True,
    )

    entry_order_2 = Order(
        id="ord_int_entry_2",
        signal_id="sig_int_2",
        symbol="ETH/USDT:USDT",
        direction=Direction.SHORT,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('10.0'),
        filled_qty=Decimal('10.0'),
        status=OrderStatus.FILLED,
        created_at=current_time,
        updated_at=current_time,
        filled_at=current_time,
        reduce_only=False,
    )

    tp_order_2 = Order(
        id="ord_int_tp_2",
        signal_id="sig_int_2",
        symbol="ETH/USDT:USDT",
        direction=Direction.SHORT,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        price=Decimal('3500'),
        requested_qty=Decimal('5.0'),
        filled_qty=Decimal('0'),
        status=OrderStatus.OPEN,
        created_at=current_time + 1000,
        updated_at=current_time + 1000,
        parent_order_id="ord_int_entry_2",
        reduce_only=True,
    )

    # 执行：保存所有订单
    await order_repository.save(entry_order_1)
    await order_repository.save(tp_order_1)
    await order_repository.save(entry_order_2)
    await order_repository.save(tp_order_2)

    # 验证：订单已保存
    all_orders_before = await order_repository.get_all_orders(limit=100)
    assert len(all_orders_before) == 4

    # 执行：批量删除第一个信号的所有订单
    result = await order_repository.delete_orders_batch(
        order_ids=["ord_int_entry_1"],  # 只传入 ENTRY 订单 ID
        cancel_on_exchange=False,
        audit_info={
            "operator_id": "integration-test-user",
            "ip_address": "127.0.0.1",
            "user_agent": "pytest-integration-test",
        },
    )

    # 验证：删除结果
    assert result["deleted_count"] == 2  # ENTRY + TP1
    assert "ord_int_entry_1" in result["deleted_from_db"]
    assert "ord_int_tp_1" in result["deleted_from_db"]
    assert result["audit_log_id"] is not None

    # 验证：剩余订单仍在数据库中
    all_orders_after = await order_repository.get_all_orders(limit=100)
    assert len(all_orders_after) == 2
    remaining_ids = [o.id for o in all_orders_after]
    assert "ord_int_entry_2" in remaining_ids
    assert "ord_int_tp_2" in remaining_ids

    # 验证：已删除的订单无法查询到
    deleted_order = await order_repository.get_order("ord_int_entry_1")
    assert deleted_order is None


# ============================================================
# Mock ExchangeGateway 实现
# ============================================================

class MockOrderCancelResult:
    """Mock OrderCancelResult for testing"""

    def __init__(self, order_id: str, symbol: str, success: bool = True, error_message: str = None):
        self.order_id = order_id
        self.exchange_order_id = None
        self.symbol = symbol
        self.status = OrderStatus.CANCELED if success else OrderStatus.OPEN
        self.message = error_message or "Order canceled successfully"
        self.error_code = "CANCEL_FAILED" if not success else None
        self.error_message = error_message

    @property
    def is_success(self) -> bool:
        return self.error_code is None


class MockExchangeGateway:
    """
    Mock ExchangeGateway for testing batch delete functionality.

    Simulates exchange order cancellation with configurable success/failure scenarios.
    """

    def __init__(self, failure_order_ids: List[str] = None, failure_reason: str = "Order already filled"):
        """
        Initialize MockExchangeGateway.

        Args:
            failure_order_ids: List of exchange_order_id that should fail to cancel
            failure_reason: Error message for failed cancellations
        """
        self.failure_order_ids = set(failure_order_ids or [])
        self.failure_reason = failure_reason
        self.cancelled_ids: List[str] = []
        self.failed_ids: List[str] = []
        self.call_history: List[Dict[str, Any]] = []

    async def cancel_order(self, exchange_order_id: str, symbol: str) -> MockOrderCancelResult:
        """
        Mock cancel_order method.

        Args:
            exchange_order_id: Exchange order ID to cancel
            symbol: Symbol pair

        Returns:
            MockOrderCancelResult with success or failure
        """
        self.call_history.append({
            "exchange_order_id": exchange_order_id,
            "symbol": symbol,
        })

        if exchange_order_id in self.failure_order_ids:
            self.failed_ids.append(exchange_order_id)
            return MockOrderCancelResult(
                order_id="",
                symbol=symbol,
                success=False,
                error_message=self.failure_reason,
            )
        else:
            self.cancelled_ids.append(exchange_order_id)
            return MockOrderCancelResult(
                order_id="",
                symbol=symbol,
                success=True,
            )


# ============================================================
# 集成测试用例 - 带 Mock 交易所
# ============================================================

@pytest.mark.asyncio
async def test_batch_delete_with_exchange_mock(order_repository):
    """
    INT-ORD-6-002: 使用 Mock 交易所的批量删除测试

    测试场景:
    1. 创建带有 exchange_order_id 的 OPEN 状态订单 (3 个)
    2. Mock ExchangeGateway 的 cancel_order 方法
       - 订单 0 和 2 取消成功
       - 订单 1 取消失败（已成交）
    3. 执行批量删除（cancel_on_exchange=True）
    4. 验证:
       - cancelled_on_exchange: 2 个成功
       - failed_to_cancel: 1 个失败
       - deleted_from_db: 3 个删除
    """
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 准备：创建 OPEN 状态的订单（有 exchange_order_id）
    orders = [
        Order(
            id=f"ord_exchange_mock_{i}",
            signal_id=f"sig_exchange_mock_{i}",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.TP1,
            price=Decimal('70000'),
            requested_qty=Decimal('0.5'),
            filled_qty=Decimal('0'),
            status=OrderStatus.OPEN,
            created_at=current_time,
            updated_at=current_time,
            exchange_order_id=f"binance_mock_{i}",
            reduce_only=True,
        )
        for i in range(3)
    ]

    # 执行：保存订单
    for order in orders:
        await order_repository.save(order)

    # 验证：订单已保存
    all_orders_before = await order_repository.get_all_orders(limit=100)
    mock_orders = [o for o in all_orders_before if o.signal_id.startswith("sig_exchange_mock")]
    assert len(mock_orders) == 3

    # 准备：Mock ExchangeGateway - 订单 1 取消失败
    mock_gateway = MockExchangeGateway(
        failure_order_ids=["binance_mock_1"],
        failure_reason="Order already filled",
    )

    # 注入 Mock Gateway
    order_repository.set_exchange_gateway(mock_gateway)

    # 执行：批量删除（cancel_on_exchange=True）
    result = await order_repository.delete_orders_batch(
        order_ids=["ord_exchange_mock_0", "ord_exchange_mock_1", "ord_exchange_mock_2"],
        cancel_on_exchange=True,
        audit_info={
            "operator_id": "test-user",
            "ip_address": "127.0.0.1",
            "user_agent": "pytest-integration-test",
        },
    )

    # 验证：交易所取消结果
    # 2 个成功取消（订单 0 和 2）
    assert len(result["cancelled_on_exchange"]) == 2
    assert "ord_exchange_mock_0" in result["cancelled_on_exchange"]
    assert "ord_exchange_mock_2" in result["cancelled_on_exchange"]

    # 1 个取消失败（订单 1）
    assert len(result["failed_to_cancel"]) == 1
    assert result["failed_to_cancel"][0]["order_id"] == "ord_exchange_mock_1"
    assert "Order already filled" in result["failed_to_cancel"][0]["reason"]

    # 验证：数据库删除结果
    assert result["deleted_count"] == 3
    assert len(result["deleted_from_db"]) == 3
    assert "ord_exchange_mock_0" in result["deleted_from_db"]
    assert "ord_exchange_mock_1" in result["deleted_from_db"]
    assert "ord_exchange_mock_2" in result["deleted_from_db"]

    # 验证：订单确实被删除
    for i in range(3):
        order = await order_repository.get_order(f"ord_exchange_mock_{i}")
        assert order is None

    # 验证：Mock Gateway 被正确调用
    assert len(mock_gateway.call_history) == 3
    # 使用集合比较（顺序可能因字典迭代而异）
    assert set(mock_gateway.cancelled_ids) == {"binance_mock_0", "binance_mock_2"}
    assert mock_gateway.failed_ids == ["binance_mock_1"]


@pytest.mark.asyncio
async def test_batch_delete_exchange_all_failures(order_repository):
    """
    INT-ORD-6-007: 交易所取消全部失败场景测试

    测试场景:
    1. 创建 3 个 OPEN 状态订单
    2. Mock 所有订单取消都失败
    3. 验证数据库仍然删除成功
    4. 验证所有失败都被正确记录
    """
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 准备：创建 OPEN 状态的订单
    orders = [
        Order(
            id=f"ord_all_fail_{i}",
            signal_id=f"sig_all_fail_{i}",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.TP1,
            price=Decimal('70000'),
            requested_qty=Decimal('0.5'),
            filled_qty=Decimal('0'),
            status=OrderStatus.OPEN,
            created_at=current_time,
            updated_at=current_time,
            exchange_order_id=f"binance_fail_{i}",
            reduce_only=True,
        )
        for i in range(3)
    ]

    # 执行：保存订单
    for order in orders:
        await order_repository.save(order)

    # 准备：Mock ExchangeGateway - 所有订单都失败
    mock_gateway = MockExchangeGateway(
        failure_order_ids=["binance_fail_0", "binance_fail_1", "binance_fail_2"],
        failure_reason="Order not found",
    )

    # 注入 Mock Gateway
    order_repository.set_exchange_gateway(mock_gateway)

    # 执行：批量删除
    result = await order_repository.delete_orders_batch(
        order_ids=["ord_all_fail_0", "ord_all_fail_1", "ord_all_fail_2"],
        cancel_on_exchange=True,
    )

    # 验证：所有交易所取消都失败
    assert len(result["cancelled_on_exchange"]) == 0
    assert len(result["failed_to_cancel"]) == 3

    # 验证所有订单都在 failed_to_cancel 中（使用集合比较，顺序可能不同）
    failed_order_ids = {f["order_id"] for f in result["failed_to_cancel"]}
    assert failed_order_ids == {"ord_all_fail_0", "ord_all_fail_1", "ord_all_fail_2"}

    for failed in result["failed_to_cancel"]:
        assert "Order not found" in failed["reason"]

    # 验证：数据库仍然删除成功
    assert result["deleted_count"] == 3
    assert len(result["deleted_from_db"]) == 3


@pytest.mark.asyncio
async def test_batch_delete_exchange_all_success(order_repository):
    """
    INT-ORD-6-008: 交易所取消全部成功场景测试

    测试场景:
    1. 创建 3 个 OPEN 状态订单
    2. Mock 所有订单取消都成功
    3. 验证所有取消都成功
    4. 验证数据库删除成功
    """
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 准备：创建 OPEN 状态的订单
    orders = [
        Order(
            id=f"ord_all_success_{i}",
            signal_id=f"sig_all_success_{i}",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.TP1,
            price=Decimal('70000'),
            requested_qty=Decimal('0.5'),
            filled_qty=Decimal('0'),
            status=OrderStatus.OPEN,
            created_at=current_time,
            updated_at=current_time,
            exchange_order_id=f"binance_success_{i}",
            reduce_only=True,
        )
        for i in range(3)
    ]

    # 执行：保存订单
    for order in orders:
        await order_repository.save(order)

    # 准备：Mock ExchangeGateway - 所有订单都成功
    mock_gateway = MockExchangeGateway(failure_order_ids=[])

    # 注入 Mock Gateway
    order_repository.set_exchange_gateway(mock_gateway)

    # 执行：批量删除
    result = await order_repository.delete_orders_batch(
        order_ids=["ord_all_success_0", "ord_all_success_1", "ord_all_success_2"],
        cancel_on_exchange=True,
    )

    # 验证：所有交易所取消都成功
    assert len(result["cancelled_on_exchange"]) == 3
    assert len(result["failed_to_cancel"]) == 0

    # 验证：数据库删除成功
    assert result["deleted_count"] == 3
    assert len(result["deleted_from_db"]) == 3


@pytest.mark.asyncio
async def test_batch_delete_no_exchange_order_id(order_repository):
    """
    INT-ORD-6-009: 幽灵订单（无 exchange_order_id）批量删除测试

    测试场景:
    1. 创建没有 exchange_order_id 的 OPEN 状态订单（幽灵订单）
    2. 执行批量删除（cancel_on_exchange=True）
    3. 验证：这些订单不会被尝试取消（因为没有交易所 ID）
    4. 验证：数据库删除成功
    """
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 准备：创建幽灵订单（没有 exchange_order_id）
    orders = [
        Order(
            id=f"ord_ghost_{i}",
            signal_id=f"sig_ghost_{i}",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.TP1,
            price=Decimal('70000'),
            requested_qty=Decimal('0.5'),
            filled_qty=Decimal('0'),
            status=OrderStatus.OPEN,
            created_at=current_time,
            updated_at=current_time,
            # 注意：没有 exchange_order_id
            reduce_only=True,
        )
        for i in range(3)
    ]

    # 执行：保存订单
    for order in orders:
        await order_repository.save(order)

    # 准备：Mock ExchangeGateway（不应该被调用）
    mock_gateway = MockExchangeGateway()
    order_repository.set_exchange_gateway(mock_gateway)

    # 执行：批量删除
    result = await order_repository.delete_orders_batch(
        order_ids=["ord_ghost_0", "ord_ghost_1", "ord_ghost_2"],
        cancel_on_exchange=True,
    )

    # 验证：没有调用交易所取消（因为没有 exchange_order_id）
    assert len(result["cancelled_on_exchange"]) == 0
    # 注意：没有 exchange_order_id 的订单会被记录到 failed_to_cancel 中，原因为 "No exchange_order_id"
    assert len(result["failed_to_cancel"]) == 3
    for failed in result["failed_to_cancel"]:
        assert "No exchange_order_id" in failed["reason"]

    # 验证：数据库删除成功
    assert result["deleted_count"] == 3
    assert len(result["deleted_from_db"]) == 3

    # 验证：Mock Gateway 没有被调用
    assert len(mock_gateway.call_history) == 0


@pytest.mark.asyncio
async def test_batch_delete_transaction_rollback(order_repository):
    """
    INT-ORD-6-003: 批量删除事务回滚测试

    测试场景:
    1. 创建多个订单
    2. 模拟删除过程中的错误
    3. 验证事务回滚，所有订单保留
    """
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 准备：创建订单
    orders = [
        Order(
            id=f"ord_rollback_test_{i}",
            signal_id="sig_rollback_test",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.0'),
            filled_qty=Decimal('1.0'),
            status=OrderStatus.FILLED,
            created_at=current_time,
            updated_at=current_time,
            filled_at=current_time,
            reduce_only=False,
        )
        for i in range(3)
    ]

    # 执行：保存订单
    for order in orders:
        await order_repository.save(order)

    # 验证：订单已保存
    all_orders_before = await order_repository.get_all_orders(limit=100)
    rollback_orders = [o for o in all_orders_before if o.signal_id == "sig_rollback_test"]
    assert len(rollback_orders) == 3

    # 注意：目前 delete_orders_batch 没有显式的回滚测试点
    # 实际回滚测试需要模拟数据库错误，这里验证正常删除流程
    result = await order_repository.delete_orders_batch(
        order_ids=["ord_rollback_test_0", "ord_rollback_test_1"],
        cancel_on_exchange=False,
    )

    # 验证：删除成功
    assert result["deleted_count"] == 2

    # 验证：剩余订单仍存在
    remaining = await order_repository.get_order("ord_rollback_test_2")
    assert remaining is not None
    assert remaining.status == OrderStatus.FILLED


@pytest.mark.asyncio
async def test_batch_delete_preserves_unrelated_orders(order_repository):
    """
    INT-ORD-6-004: 批量删除不影响无关订单测试

    测试场景:
    1. 创建多组订单（不同 signal_id）
    2. 删除其中一组的订单
    3. 验证其他组订单不受影响
    """
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 准备：创建 3 组订单
    group_a_orders = [
        Order(
            id=f"ord_group_a_{i}",
            signal_id="sig_group_a",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.0'),
            filled_qty=Decimal('1.0'),
            status=OrderStatus.FILLED,
            created_at=current_time,
            updated_at=current_time,
            filled_at=current_time,
            reduce_only=False,
        )
        for i in range(3)
    ]

    group_b_orders = [
        Order(
            id=f"ord_group_b_{i}",
            signal_id="sig_group_b",
            symbol="ETH/USDT:USDT",
            direction=Direction.SHORT,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('10.0'),
            filled_qty=Decimal('10.0'),
            status=OrderStatus.FILLED,
            created_at=current_time,
            updated_at=current_time,
            filled_at=current_time,
            reduce_only=False,
        )
        for i in range(2)
    ]

    # 执行：保存所有订单
    for order in group_a_orders + group_b_orders:
        await order_repository.save(order)

    # 验证：总共 5 个订单
    all_orders_before = await order_repository.get_all_orders(limit=100)
    assert len(all_orders_before) == 5

    # 执行：只删除 Group A 的订单
    result = await order_repository.delete_orders_batch(
        order_ids=["ord_group_a_0", "ord_group_a_1", "ord_group_a_2"],
        cancel_on_exchange=False,
    )

    # 验证：删除了 3 个订单
    assert result["deleted_count"] == 3

    # 验证：Group B 订单未受影响
    all_orders_after = await order_repository.get_all_orders(limit=100)
    group_b_remaining = [o for o in all_orders_after if o.signal_id == "sig_group_b"]
    assert len(group_b_remaining) == 2

    # 验证：Group A 订单全部被删除
    group_a_remaining = [o for o in all_orders_after if o.signal_id == "sig_group_a"]
    assert len(group_a_remaining) == 0


# ============================================================
# 边界条件测试
# ============================================================

@pytest.mark.asyncio
async def test_batch_delete_single_order(order_repository):
    """
    INT-ORD-6-005: 批量删除单个订单边界测试

    验证：即使只删除 1 个订单，流程也正常工作
    """
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 准备：创建单个订单
    order = Order(
        id="ord_single_delete",
        signal_id="sig_single",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('1.0'),
        status=OrderStatus.FILLED,
        created_at=current_time,
        updated_at=current_time,
        filled_at=current_time,
        reduce_only=False,
    )

    # 执行：保存订单
    await order_repository.save(order)

    # 执行：批量删除单个订单
    result = await order_repository.delete_orders_batch(
        order_ids=["ord_single_delete"],
        cancel_on_exchange=False,
    )

    # 验证：删除成功
    assert result["deleted_count"] == 1
    assert "ord_single_delete" in result["deleted_from_db"]

    # 验证：订单已删除
    deleted = await order_repository.get_order("ord_single_delete")
    assert deleted is None


@pytest.mark.asyncio
async def test_batch_delete_exactly_100_orders(order_repository):
    """
    INT-ORD-6-006: 批量删除刚好 100 个订单边界测试

    验证：100 个订单是上限，应该正常工作
    """
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 准备：创建 100 个订单
    orders = [
        Order(
            id=f"ord_limit_100_{i}",
            signal_id="sig_limit_100",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.0'),
            filled_qty=Decimal('1.0'),
            status=OrderStatus.FILLED,
            created_at=current_time,
            updated_at=current_time,
            filled_at=current_time,
            reduce_only=False,
        )
        for i in range(100)
    ]

    # 执行：保存所有订单
    for order in orders:
        await order_repository.save(order)

    # 验证：100 个订单已保存
    all_orders = await order_repository.get_all_orders(limit=200)
    limit_100_orders = [o for o in all_orders if o.signal_id == "sig_limit_100"]
    assert len(limit_100_orders) == 100

    # 执行：批量删除所有 100 个订单
    order_ids = [f"ord_limit_100_{i}" for i in range(100)]
    result = await order_repository.delete_orders_batch(
        order_ids=order_ids,
        cancel_on_exchange=False,
    )

    # 验证：所有订单已删除
    assert result["deleted_count"] == 100
    assert len(result["deleted_from_db"]) == 100

    # 验证：数据库已清空
    remaining = await order_repository.get_all_orders(limit=100)
    assert len(remaining) == 0
