"""
Order Lifecycle Service 单元测试

测试覆盖:
1. 订单创建 (CREATED 状态)
2. 订单提交 (SUBMITTED 状态)
3. 订单确认 (OPEN 状态)
4. 订单部分成交 (PARTIALLY_FILLED 状态)
5. 订单完全成交 (FILLED 状态)
6. 订单取消 (CANCELED 状态)
7. 订单拒绝 (REJECTED 状态)
8. 状态机集成
9. 审计日志集成
10. 订单变更回调

依赖:
- OrderStateMachine: 状态转换核心
- OrderRepository: 订单持久化
- OrderAuditLogger: 审计日志记录
"""
import pytest
import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import tempfile
import os

from src.application.order_lifecycle_service import OrderLifecycleService
from src.domain.models import (
    Order,
    OrderStatus,
    OrderType,
    OrderRole,
    Direction,
    OrderStrategy,
)
from src.domain.order_state_machine import OrderStateMachine, InvalidOrderStateTransition
from src.infrastructure.order_repository import OrderRepository
from src.application.order_audit_logger import OrderAuditLogger, OrderAuditEventType, OrderAuditTriggerSource


@pytest.fixture
def temp_db():
    """创建临时数据库"""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    try:
        os.unlink(path)
        # 清理 WAL 和 SHM 文件
        for ext in ['-wal', '-shm']:
            wal_path = path + ext
            if os.path.exists(wal_path):
                os.unlink(wal_path)
    except Exception:
        pass


@pytest.fixture
def sample_strategy():
    """创建示例策略"""
    return OrderStrategy(
        id="test_strategy",
        name="TestStrategy",
        tp_levels=3,
        tp_ratios=[Decimal('0.5'), Decimal('0.3'), Decimal('0.2')],
        tp_targets=[Decimal('1.5'), Decimal('2.0'), Decimal('3.0')],
        initial_stop_loss_rr=Decimal('-1.0'),
        trailing_stop_enabled=True,
        oco_enabled=True,
    )


@pytest.fixture
async def lifecycle_service(temp_db):
    """创建生命周期服务"""
    repository = OrderRepository(db_path=temp_db)
    await repository.initialize()

    service = OrderLifecycleService(repository=repository)
    await service.start()
    yield service
    await service.stop()


@pytest.fixture
async def lifecycle_service_with_audit(temp_db):
    """创建带审计日志的生命周期服务"""
    repository = OrderRepository(db_path=temp_db)
    await repository.initialize()

    # 创建 mock 审计日志器
    audit_logger = AsyncMock(spec=OrderAuditLogger)
    audit_logger.log = AsyncMock()

    service = OrderLifecycleService(repository=repository, audit_logger=audit_logger)
    await service.start()
    yield service, audit_logger
    await service.stop()


class TestOrderLifecycleServiceCreation:
    """测试订单创建"""

    @pytest.mark.asyncio
    async def test_create_order_creates_created_status(self, lifecycle_service, sample_strategy):
        """测试创建订单后状态为 CREATED"""
        order = await lifecycle_service.create_order(
            strategy=sample_strategy,
            signal_id="sig_test_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            total_qty=Decimal('1.0'),
            initial_sl_rr=Decimal('-1.0'),
            tp_targets=[Decimal('1.5'), Decimal('2.0'), Decimal('3.0')],
        )

        assert order is not None
        assert order.status == OrderStatus.CREATED
        assert order.signal_id == "sig_test_001"
        assert order.symbol == "BTC/USDT:USDT"
        assert order.direction == Direction.LONG
        assert order.requested_qty == Decimal('1.0')
        assert order.order_type == OrderType.MARKET
        assert order.order_role == OrderRole.ENTRY

    @pytest.mark.asyncio
    async def test_create_order_with_audit_logger(self, lifecycle_service_with_audit, sample_strategy):
        """测试创建订单时记录审计日志"""
        service, audit_logger = lifecycle_service_with_audit

        order = await service.create_order(
            strategy=sample_strategy,
            signal_id="sig_test_002",
            symbol="ETH/USDT:USDT",
            direction=Direction.SHORT,
            total_qty=Decimal('2.0'),
            initial_sl_rr=Decimal('-1.0'),
            tp_targets=[Decimal('1.5')],
        )

        assert order.status == OrderStatus.CREATED
        # 验证审计日志被调用
        assert audit_logger.log.called


class TestOrderSubmit:
    """测试订单提交"""

    @pytest.mark.asyncio
    async def test_submit_order_changes_to_submitted(self, lifecycle_service, sample_strategy):
        """测试提交订单后状态变为 SUBMITTED"""
        # 创建订单
        order = await lifecycle_service.create_order(
            strategy=sample_strategy,
            signal_id="sig_test_003",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            total_qty=Decimal('0.5'),
            initial_sl_rr=Decimal('-1.0'),
            tp_targets=[Decimal('1.5')],
        )

        # 提交订单
        updated_order = await lifecycle_service.submit_order(
            order_id=order.id,
            exchange_order_id="binance_test_123"
        )

        assert updated_order.status == OrderStatus.SUBMITTED
        assert updated_order.exchange_order_id == "binance_test_123"

    @pytest.mark.asyncio
    async def test_submit_nonexistent_order_raises_error(self, lifecycle_service):
        """测试提交不存在的订单抛出异常"""
        with pytest.raises(ValueError, match="订单不存在"):
            await lifecycle_service.submit_order(
                order_id="nonexistent_order",
                exchange_order_id="binance_test"
            )


class TestOrderConfirm:
    """测试订单确认"""

    @pytest.mark.asyncio
    async def test_confirm_order_changes_to_open(self, lifecycle_service, sample_strategy):
        """测试确认订单后状态变为 OPEN"""
        order = await lifecycle_service.create_order(
            strategy=sample_strategy,
            signal_id="sig_test_004",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            total_qty=Decimal('0.5'),
            initial_sl_rr=Decimal('-1.0'),
            tp_targets=[Decimal('1.5')],
        )

        # 提交订单
        await lifecycle_service.submit_order(order.id, exchange_order_id="binance_test_456")

        # 确认订单
        updated_order = await lifecycle_service.confirm_order(
            order_id=order.id,
            exchange_order_id="binance_test_456"
        )

        assert updated_order.status == OrderStatus.OPEN


class TestOrderFill:
    """测试订单成交"""

    @pytest.mark.asyncio
    async def test_partial_fill_changes_status(self, lifecycle_service, sample_strategy):
        """测试部分成交后状态变为 PARTIALLY_FILLED"""
        order = await lifecycle_service.create_order(
            strategy=sample_strategy,
            signal_id="sig_test_005",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            total_qty=Decimal('1.0'),
            initial_sl_rr=Decimal('-1.0'),
            tp_targets=[Decimal('1.5')],
        )

        await lifecycle_service.submit_order(order.id)
        await lifecycle_service.confirm_order(order.id)

        # 部分成交
        updated_order = await lifecycle_service.update_order_partially_filled(
            order_id=order.id,
            filled_qty=Decimal('0.3'),
            average_exec_price=Decimal('65000'),
        )

        assert updated_order.status == OrderStatus.PARTIALLY_FILLED
        assert updated_order.filled_qty == Decimal('0.3')
        assert updated_order.average_exec_price == Decimal('65000')

    @pytest.mark.asyncio
    async def test_full_fill_changes_status(self, lifecycle_service, sample_strategy):
        """测试完全成交后状态变为 FILLED"""
        order = await lifecycle_service.create_order(
            strategy=sample_strategy,
            signal_id="sig_test_006",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            total_qty=Decimal('1.0'),
            initial_sl_rr=Decimal('-1.0'),
            tp_targets=[Decimal('1.5')],
        )

        await lifecycle_service.submit_order(order.id)
        await lifecycle_service.confirm_order(order.id)

        # 完全成交
        updated_order = await lifecycle_service.update_order_filled(
            order_id=order.id,
            filled_qty=Decimal('1.0'),
            average_exec_price=Decimal('65000'),
        )

        assert updated_order.status == OrderStatus.FILLED
        assert updated_order.filled_qty == Decimal('1.0')


class TestOrderCancel:
    """测试订单取消"""

    @pytest.mark.asyncio
    async def test_cancel_order_changes_to_canceled(self, lifecycle_service, sample_strategy):
        """测试取消订单后状态变为 CANCELED"""
        order = await lifecycle_service.create_order(
            strategy=sample_strategy,
            signal_id="sig_test_007",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            total_qty=Decimal('0.5'),
            initial_sl_rr=Decimal('-1.0'),
            tp_targets=[Decimal('1.5')],
        )

        await lifecycle_service.submit_order(order.id)

        # 取消订单
        updated_order = await lifecycle_service.cancel_order(
            order_id=order.id,
            reason="User requested"
        )

        assert updated_order.status == OrderStatus.CANCELED

    @pytest.mark.asyncio
    async def test_cancel_filled_order_raises_error(self, lifecycle_service, sample_strategy):
        """测试取消已成交订单抛出异常"""
        order = await lifecycle_service.create_order(
            strategy=sample_strategy,
            signal_id="sig_test_008",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            total_qty=Decimal('0.5'),
            initial_sl_rr=Decimal('-1.0'),
            tp_targets=[Decimal('1.5')],
        )

        await lifecycle_service.submit_order(order.id)
        await lifecycle_service.confirm_order(order.id)
        await lifecycle_service.update_order_filled(
            order.id,
            Decimal('0.5'),
            Decimal('65000')
        )

        # 尝试取消已成交订单应该失败
        with pytest.raises(InvalidOrderStateTransition):
            await lifecycle_service.cancel_order(order_id=order.id)


class TestOrderUpdateFromExchange:
    """测试根据交易所数据更新订单"""

    @pytest.mark.asyncio
    async def test_update_from_exchange_with_open_status(self, lifecycle_service, sample_strategy):
        """测试根据交易所 OPEN 状态更新"""
        order = await lifecycle_service.create_order(
            strategy=sample_strategy,
            signal_id="sig_test_009",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            total_qty=Decimal('0.5'),
            initial_sl_rr=Decimal('-1.0'),
            tp_targets=[Decimal('1.5')],
        )

        await lifecycle_service.submit_order(order.id)

        # 模拟交易所推送 OPEN 状态
        exchange_data = {
            "id": "binance_exchange_789",
            "status": "open",
            "filled": 0,
            "average": None,
        }

        updated_order = await lifecycle_service.update_order_from_exchange(
            order_id=order.id,
            exchange_order_data=exchange_data
        )

        assert updated_order.status == OrderStatus.OPEN
        assert updated_order.exchange_order_id == "binance_exchange_789"

    @pytest.mark.asyncio
    async def test_update_from_exchange_with_partially_filled(self, lifecycle_service, sample_strategy):
        """测试根据交易所部分成交更新"""
        order = await lifecycle_service.create_order(
            strategy=sample_strategy,
            signal_id="sig_test_010",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            total_qty=Decimal('1.0'),
            initial_sl_rr=Decimal('-1.0'),
            tp_targets=[Decimal('1.5')],
        )

        await lifecycle_service.submit_order(order.id)
        await lifecycle_service.confirm_order(order.id)

        # 模拟交易所推送部分成交
        exchange_data = {
            "id": "binance_exchange_012",
            "status": "open",
            "filled": 0.5,
            "average": 65000,
        }

        updated_order = await lifecycle_service.update_order_from_exchange(
            order_id=order.id,
            exchange_order_data=exchange_data
        )

        assert updated_order.status == OrderStatus.PARTIALLY_FILLED
        assert updated_order.filled_qty == Decimal('0.5')


class TestOrderQuery:
    """测试订单查询"""

    @pytest.mark.asyncio
    async def test_get_order_by_id(self, lifecycle_service, sample_strategy):
        """测试根据 ID 获取订单"""
        order = await lifecycle_service.create_order(
            strategy=sample_strategy,
            signal_id="sig_test_011",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            total_qty=Decimal('0.5'),
            initial_sl_rr=Decimal('-1.0'),
            tp_targets=[Decimal('1.5')],
        )

        retrieved = await lifecycle_service.get_order(order.id)
        assert retrieved is not None
        assert retrieved.id == order.id

    @pytest.mark.asyncio
    async def test_get_orders_by_signal(self, lifecycle_service, sample_strategy):
        """测试根据信号 ID 获取订单列表"""
        await lifecycle_service.create_order(
            strategy=sample_strategy,
            signal_id="sig_test_012",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            total_qty=Decimal('0.5'),
            initial_sl_rr=Decimal('-1.0'),
            tp_targets=[Decimal('1.5')],
        )

        orders = await lifecycle_service.get_orders_by_signal("sig_test_012")
        assert len(orders) >= 1

    @pytest.mark.asyncio
    async def test_get_open_orders(self, lifecycle_service, sample_strategy):
        """测试获取未完成订单"""
        # 创建并成交一个订单
        order = await lifecycle_service.create_order(
            strategy=sample_strategy,
            signal_id="sig_test_013",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            total_qty=Decimal('0.5'),
            initial_sl_rr=Decimal('-1.0'),
            tp_targets=[Decimal('1.5')],
        )

        await lifecycle_service.submit_order(order.id)
        await lifecycle_service.confirm_order(order.id)

        # 获取 OPEN 状态订单
        open_orders = await lifecycle_service.get_orders_by_status(OrderStatus.OPEN)
        assert len(open_orders) >= 1


class TestOrderCallback:
    """测试订单变更回调"""

    @pytest.mark.asyncio
    async def test_order_changed_callback(self, lifecycle_service, sample_strategy):
        """测试订单变更回调被触发"""
        callback_called = []

        async def callback(order: Order):
            callback_called.append(order)

        lifecycle_service.set_order_changed_callback(callback)

        order = await lifecycle_service.create_order(
            strategy=sample_strategy,
            signal_id="sig_test_014",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            total_qty=Decimal('0.5'),
            initial_sl_rr=Decimal('-1.0'),
            tp_targets=[Decimal('1.5')],
        )

        # 等待回调执行
        await asyncio.sleep(0.1)

        # 至少调用一次（创建时）
        assert len(callback_called) >= 1


class TestStateMachineIntegration:
    """测试状态机集成"""

    @pytest.mark.asyncio
    async def test_state_machine_created_for_order(self, lifecycle_service, sample_strategy):
        """测试订单创建后状态机已创建"""
        order = await lifecycle_service.create_order(
            strategy=sample_strategy,
            signal_id="sig_test_015",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            total_qty=Decimal('0.5'),
            initial_sl_rr=Decimal('-1.0'),
            tp_targets=[Decimal('1.5')],
        )

        state_machine = lifecycle_service.get_state_machine(order.id)
        assert state_machine is not None
        assert state_machine.current_status == OrderStatus.CREATED

    @pytest.mark.asyncio
    async def test_state_machine_tracks_transitions(self, lifecycle_service, sample_strategy):
        """测试状态机追踪状态转换次数"""
        order = await lifecycle_service.create_order(
            strategy=sample_strategy,
            signal_id="sig_test_016",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            total_qty=Decimal('0.5'),
            initial_sl_rr=Decimal('-1.0'),
            tp_targets=[Decimal('1.5')],
        )

        state_machine = lifecycle_service.get_state_machine(order.id)
        initial_count = state_machine.transition_count

        await lifecycle_service.submit_order(order.id)

        assert state_machine.transition_count == initial_count + 1


class TestEdgeCases:
    """测试边界情况"""

    @pytest.mark.asyncio
    async def test_submit_order_without_exchange_id(self, lifecycle_service, sample_strategy):
        """测试提交订单时不提供交易所 ID"""
        order = await lifecycle_service.create_order(
            strategy=sample_strategy,
            signal_id="sig_test_017",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            total_qty=Decimal('0.5'),
            initial_sl_rr=Decimal('-1.0'),
            tp_targets=[Decimal('1.5')],
        )

        # 不提供 exchange_order_id 也应该成功
        updated_order = await lifecycle_service.submit_order(order_id=order.id)
        assert updated_order.status == OrderStatus.SUBMITTED

    @pytest.mark.asyncio
    async def test_cancel_order_from_created_status(self, lifecycle_service, sample_strategy):
        """测试从 CREATED 状态直接取消订单"""
        order = await lifecycle_service.create_order(
            strategy=sample_strategy,
            signal_id="sig_test_018",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            total_qty=Decimal('0.5'),
            initial_sl_rr=Decimal('-1.0'),
            tp_targets=[Decimal('1.5')],
        )

        # 从 CREATED 直接取消
        updated_order = await lifecycle_service.cancel_order(
            order_id=order.id,
            reason="Cancel before submit"
        )

        assert updated_order.status == OrderStatus.CANCELED


class TestCompleteOrderLifecycle:
    """测试完整订单生命周期"""

    @pytest.mark.asyncio
    async def test_complete_order_lifecycle_path(self, lifecycle_service, sample_strategy):
        """测试完整订单生命周期路径"""
        # 1. 创建订单
        order = await lifecycle_service.create_order(
            strategy=sample_strategy,
            signal_id="sig_test_019",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            total_qty=Decimal('1.0'),
            initial_sl_rr=Decimal('-1.0'),
            tp_targets=[Decimal('1.5'), Decimal('2.0'), Decimal('3.0')],
        )
        assert order.status == OrderStatus.CREATED

        # 2. 提交订单
        await lifecycle_service.submit_order(order.id, exchange_order_id="binance_123")
        assert order.status == OrderStatus.SUBMITTED

        # 3. 确认挂单
        await lifecycle_service.confirm_order(order.id)
        assert order.status == OrderStatus.OPEN

        # 4. 部分成交
        await lifecycle_service.update_order_partially_filled(
            order.id,
            Decimal('0.3'),
            Decimal('65000')
        )
        assert order.status == OrderStatus.PARTIALLY_FILLED

        # 5. 完全成交
        await lifecycle_service.update_order_filled(
            order.id,
            Decimal('1.0'),
            Decimal('65500')
        )
        assert order.status == OrderStatus.FILLED

        # 6. 终态不可再转换
        state_machine = lifecycle_service.get_state_machine(order.id)
        assert state_machine.is_terminal is True
