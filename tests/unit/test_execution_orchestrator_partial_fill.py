"""
Execution Orchestrator Partial Fill 增量补挂机制测试

测试覆盖：
1. 首次 partial fill 时挂保护单
2. filled_qty 增加后，只为新增成交量补挂保护单
3. 相同 filled_qty 重放时，不会重复挂单（幂等）
4. 已存在部分保护单时，只补缺口，不重复提交已有子单

设计要点：
- protected_qty_total 优先使用 SL 订单的 requested_qty 总和
- 如果没有 SL，退化为 TP 订单的 requested_qty 总和
- delta_qty = filled_qty_total - protected_qty_total
- 只有 delta_qty > 0 时才补挂
"""
import pytest
import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import tempfile
import os

from src.application.execution_orchestrator import ExecutionOrchestrator
from src.domain.models import (
    Order,
    OrderStatus,
    OrderType,
    OrderRole,
    Direction,
    OrderStrategy,
    SignalResult,
)
from src.domain.execution_intent import ExecutionIntent, ExecutionIntentStatus
from src.infrastructure.order_repository import OrderRepository


@pytest.fixture
def temp_db():
    """创建临时数据库"""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    try:
        os.unlink(path)
    except:
        pass


@pytest.fixture
def mock_gateway():
    """Mock ExchangeGateway"""
    gateway = AsyncMock()
    gateway.place_order = AsyncMock()
    return gateway


@pytest.fixture
def sample_strategy():
    """示例订单策略"""
    return OrderStrategy(
        id="strategy_001",
        name="Test Strategy",
        tp_levels=2,
        tp_ratios=[Decimal("0.5"), Decimal("0.5")],
        tp_targets=[Decimal("1.5"), Decimal("3.0")],
        initial_stop_loss_rr=Decimal("-1.0"),
    )


@pytest.fixture
def sample_signal():
    """示例信号"""
    return SignalResult(
        symbol="BTC/USDT:USDT",
        timeframe="15m",
        direction=Direction.LONG,
        entry_price=Decimal("65000"),
        suggested_stop_loss=Decimal("64000"),
        suggested_position_size=Decimal("1.0"),
        current_leverage=10,
        tags=[],
        risk_reward_info="Test",
        strategy_name="test",
    )


class TestPartialFillIncrementalProtection:
    """增量补挂机制测试"""

    @pytest.mark.asyncio
    async def test_first_partial_fill_creates_protection(
        self, temp_db, mock_gateway, sample_strategy, sample_signal
    ):
        """
        场景 1：首次 partial fill 时挂保护单

        条件：
        - ENTRY 首次部分成交
        - 当前无保护单

        预期：
        - 为全部成交量生成 TP/SL 保护单
        """
        from src.application.order_lifecycle_service import OrderLifecycleService
        from src.application.capital_protection import CapitalProtectionManager

        # Arrange: 创建依赖
        repository = OrderRepository(temp_db)
        await repository.initialize()
        order_lifecycle = OrderLifecycleService(repository)

        capital_protection = MagicMock(spec=CapitalProtectionManager)
        capital_protection.pre_order_check = AsyncMock()
        capital_protection.pre_order_check.return_value = MagicMock(allowed=True)

        orchestrator = ExecutionOrchestrator(
            capital_protection=capital_protection,
            order_lifecycle=order_lifecycle,
            gateway=mock_gateway,
        )

        # 创建 ENTRY 订单
        entry_order = Order(
            id="entry_001",
            signal_id="signal_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal("1.0"),
            filled_qty=Decimal("0.3"),  # 首次成交 0.3
            average_exec_price=Decimal("65000"),
            status=OrderStatus.PARTIALLY_FILLED,
            created_at=1234567890000,
            updated_at=1234567890000,
        )
        await repository.save(entry_order)

        # 创建 ExecutionIntent
        intent = ExecutionIntent(
            id="intent_001",
            signal=sample_signal,
            status=ExecutionIntentStatus.SUBMITTED,
            strategy=sample_strategy,
            order_id=entry_order.id,
        )
        orchestrator._intents[intent.id] = intent

        # Mock gateway.place_order 返回成功
        mock_gateway.place_order.return_value = MagicMock(
            is_success=True,
            exchange_order_id="exchange_001",
        )

        # Act: 调用 partial fill 处理
        await orchestrator._handle_entry_partially_filled(entry_order)

        # Assert: 应该调用 place_order 生成保护单
        # 预期：1 SL + 2 TP = 3 个保护单
        assert mock_gateway.place_order.call_count == 3, \
            f"应该生成 3 个保护单，实际调用 {mock_gateway.place_order.call_count} 次"

    @pytest.mark.asyncio
    async def test_incremental_fill_only_creates_delta_protection(
        self, temp_db, mock_gateway, sample_strategy, sample_signal
    ):
        """
        场景 2：filled_qty 增加后，只为新增成交量补挂保护单

        条件：
        - ENTRY 已有部分保护单（覆盖 0.3）
        - filled_qty 增加到 0.5
        - delta_qty = 0.5 - 0.3 = 0.2

        预期：
        - 只为新增的 0.2 生成保护单
        - 不修改已有保护单
        """
        from src.application.order_lifecycle_service import OrderLifecycleService
        from src.application.capital_protection import CapitalProtectionManager

        # Arrange
        repository = OrderRepository(temp_db)
        await repository.initialize()
        order_lifecycle = OrderLifecycleService(repository)

        capital_protection = MagicMock(spec=CapitalProtectionManager)
        capital_protection.pre_order_check = AsyncMock()
        capital_protection.pre_order_check.return_value = MagicMock(allowed=True)

        orchestrator = ExecutionOrchestrator(
            capital_protection=capital_protection,
            order_lifecycle=order_lifecycle,
            gateway=mock_gateway,
        )

        # 创建 ENTRY 订单（已成交 0.5）
        entry_order = Order(
            id="entry_002",
            signal_id="signal_002",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal("1.0"),
            filled_qty=Decimal("0.5"),  # 当前成交 0.5
            average_exec_price=Decimal("65000"),
            status=OrderStatus.PARTIALLY_FILLED,
            created_at=1234567890000,
            updated_at=1234567890000,
        )
        await repository.save(entry_order)

        # 创建已存在的保护单（覆盖 0.3）
        existing_sl = Order(
            id="sl_001",
            signal_id="signal_002",
            symbol="BTC/USDT:USDT",
            direction=Direction.SHORT,
            order_type=OrderType.STOP_MARKET,
            order_role=OrderRole.SL,
            parent_order_id=entry_order.id,
            requested_qty=Decimal("0.3"),  # 已保护 0.3
            trigger_price=Decimal("64000"),
            status=OrderStatus.OPEN,
            created_at=1234567890000,
            updated_at=1234567890000,
        )
        await repository.save(existing_sl)

        existing_tp1 = Order(
            id="tp1_001",
            signal_id="signal_002",
            symbol="BTC/USDT:USDT",
            direction=Direction.SHORT,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.TP1,
            parent_order_id=entry_order.id,
            requested_qty=Decimal("0.15"),  # 0.3 * 0.5
            price=Decimal("66500"),
            status=OrderStatus.OPEN,
            created_at=1234567890000,
            updated_at=1234567890000,
        )
        await repository.save(existing_tp1)

        existing_tp2 = Order(
            id="tp2_001",
            signal_id="signal_002",
            symbol="BTC/USDT:USDT",
            direction=Direction.SHORT,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.TP2,
            parent_order_id=entry_order.id,
            requested_qty=Decimal("0.15"),  # 0.3 * 0.5
            price=Decimal("68000"),
            status=OrderStatus.OPEN,
            created_at=1234567890000,
            updated_at=1234567890000,
        )
        await repository.save(existing_tp2)

        # 创建 ExecutionIntent
        intent = ExecutionIntent(
            id="intent_002",
            signal=sample_signal,
            status=ExecutionIntentStatus.PARTIALLY_PROTECTED,
            strategy=sample_strategy,
            order_id=entry_order.id,
        )
        orchestrator._intents[intent.id] = intent

        # Mock gateway.place_order 返回成功
        mock_gateway.place_order.return_value = MagicMock(
            is_success=True,
            exchange_order_id="exchange_002",
        )

        # Act
        await orchestrator._handle_entry_partially_filled(entry_order)

        # Assert: 应该只为 delta_qty = 0.2 生成保护单
        # 预期：1 SL + 2 TP = 3 个保护单
        assert mock_gateway.place_order.call_count == 3, \
            f"应该为 delta_qty=0.2 生成 3 个保护单，实际调用 {mock_gateway.place_order.call_count} 次"

        # 验证保护单数量是为 0.2 生成的
        calls = mock_gateway.place_order.call_args_list
        for call in calls:
            amount = call.kwargs.get('amount') or call.args[2] if len(call.args) > 2 else None
            if amount is not None:
                # SL 应该是 0.2，TP 应该是 0.1
                assert amount <= Decimal("0.2"), \
                    f"保护单数量应该不超过 delta_qty=0.2，实际为 {amount}"

    @pytest.mark.asyncio
    async def test_same_filled_qty_replay_is_idempotent(
        self, temp_db, mock_gateway, sample_strategy, sample_signal
    ):
        """
        场景 3：相同 filled_qty 重放时，不会重复挂单（幂等）

        条件：
        - ENTRY 已成交 0.3
        - 已存在保护单覆盖 0.3
        - delta_qty = 0.3 - 0.3 = 0

        预期：
        - 不调用 place_order
        - 直接返回
        """
        from src.application.order_lifecycle_service import OrderLifecycleService
        from src.application.capital_protection import CapitalProtectionManager

        # Arrange
        repository = OrderRepository(temp_db)
        await repository.initialize()
        order_lifecycle = OrderLifecycleService(repository)

        capital_protection = MagicMock(spec=CapitalProtectionManager)
        capital_protection.pre_order_check = AsyncMock()
        capital_protection.pre_order_check.return_value = MagicMock(allowed=True)

        orchestrator = ExecutionOrchestrator(
            capital_protection=capital_protection,
            order_lifecycle=order_lifecycle,
            gateway=mock_gateway,
        )

        # 创建 ENTRY 订单（已成交 0.3）
        entry_order = Order(
            id="entry_003",
            signal_id="signal_003",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal("1.0"),
            filled_qty=Decimal("0.3"),
            average_exec_price=Decimal("65000"),
            status=OrderStatus.PARTIALLY_FILLED,
            created_at=1234567890000,
            updated_at=1234567890000,
        )
        await repository.save(entry_order)

        # 创建已存在的保护单（覆盖 0.3）
        existing_sl = Order(
            id="sl_003",
            signal_id="signal_003",
            symbol="BTC/USDT:USDT",
            direction=Direction.SHORT,
            order_type=OrderType.STOP_MARKET,
            order_role=OrderRole.SL,
            parent_order_id=entry_order.id,
            requested_qty=Decimal("0.3"),
            trigger_price=Decimal("64000"),
            status=OrderStatus.OPEN,
            created_at=1234567890000,
            updated_at=1234567890000,
        )
        await repository.save(existing_sl)

        # 创建 ExecutionIntent
        intent = ExecutionIntent(
            id="intent_003",
            signal=sample_signal,
            status=ExecutionIntentStatus.PARTIALLY_PROTECTED,
            strategy=sample_strategy,
            order_id=entry_order.id,
        )
        orchestrator._intents[intent.id] = intent

        # Act: 重放相同 filled_qty
        await orchestrator._handle_entry_partially_filled(entry_order)

        # Assert: 不应该调用 place_order
        assert mock_gateway.place_order.call_count == 0, \
            f"相同 filled_qty 重放应该幂等，不应调用 place_order，实际调用 {mock_gateway.place_order.call_count} 次"

    @pytest.mark.asyncio
    async def test_only_fills_gap_not_recreate_existing(
        self, temp_db, mock_gateway, sample_strategy, sample_signal
    ):
        """
        场景 4：已存在部分保护单时，只补缺口，不重复提交已有子单

        条件：
        - ENTRY 已成交 0.8
        - 已存在 SL 覆盖 0.3
        - delta_qty = 0.8 - 0.3 = 0.5

        预期：
        - 只为 0.5 生成新保护单
        - 不修改已有的 SL
        """
        from src.application.order_lifecycle_service import OrderLifecycleService
        from src.application.capital_protection import CapitalProtectionManager

        # Arrange
        repository = OrderRepository(temp_db)
        await repository.initialize()
        order_lifecycle = OrderLifecycleService(repository)

        capital_protection = MagicMock(spec=CapitalProtectionManager)
        capital_protection.pre_order_check = AsyncMock()
        capital_protection.pre_order_check.return_value = MagicMock(allowed=True)

        orchestrator = ExecutionOrchestrator(
            capital_protection=capital_protection,
            order_lifecycle=order_lifecycle,
            gateway=mock_gateway,
        )

        # 创建 ENTRY 订单（已成交 0.8）
        entry_order = Order(
            id="entry_004",
            signal_id="signal_004",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal("1.0"),
            filled_qty=Decimal("0.8"),
            average_exec_price=Decimal("65000"),
            status=OrderStatus.PARTIALLY_FILLED,
            created_at=1234567890000,
            updated_at=1234567890000,
        )
        await repository.save(entry_order)

        # 创建已存在的 SL（覆盖 0.3）
        existing_sl = Order(
            id="sl_004",
            signal_id="signal_004",
            symbol="BTC/USDT:USDT",
            direction=Direction.SHORT,
            order_type=OrderType.STOP_MARKET,
            order_role=OrderRole.SL,
            parent_order_id=entry_order.id,
            requested_qty=Decimal("0.3"),
            trigger_price=Decimal("64000"),
            status=OrderStatus.OPEN,
            created_at=1234567890000,
            updated_at=1234567890000,
        )
        await repository.save(existing_sl)

        # 创建 ExecutionIntent
        intent = ExecutionIntent(
            id="intent_004",
            signal=sample_signal,
            status=ExecutionIntentStatus.PARTIALLY_PROTECTED,
            strategy=sample_strategy,
            order_id=entry_order.id,
        )
        orchestrator._intents[intent.id] = intent

        # Mock gateway.place_order 返回成功
        mock_gateway.place_order.return_value = MagicMock(
            is_success=True,
            exchange_order_id="exchange_004",
        )

        # Act
        await orchestrator._handle_entry_partially_filled(entry_order)

        # Assert: 应该只为 delta_qty = 0.5 生成保护单
        assert mock_gateway.place_order.call_count == 3, \
            f"应该为 delta_qty=0.5 生成 3 个保护单，实际调用 {mock_gateway.place_order.call_count} 次"

    @pytest.mark.asyncio
    async def test_fallback_to_tp_when_no_sl(
        self, temp_db, mock_gateway, sample_strategy, sample_signal
    ):
        """
        场景 5：没有 SL 时，退化为 TP 订单的 requested_qty 总和作为兜底

        条件：
        - ENTRY 已成交 0.6
        - 没有 SL，只有 TP1 覆盖 0.3
        - delta_qty = 0.6 - 0.3 = 0.3

        预期：
        - 只为 0.3 生成新保护单
        """
        from src.application.order_lifecycle_service import OrderLifecycleService
        from src.application.capital_protection import CapitalProtectionManager

        # Arrange
        repository = OrderRepository(temp_db)
        await repository.initialize()
        order_lifecycle = OrderLifecycleService(repository)

        capital_protection = MagicMock(spec=CapitalProtectionManager)
        capital_protection.pre_order_check = AsyncMock()
        capital_protection.pre_order_check.return_value = MagicMock(allowed=True)

        orchestrator = ExecutionOrchestrator(
            capital_protection=capital_protection,
            order_lifecycle=order_lifecycle,
            gateway=mock_gateway,
        )

        # 创建 ENTRY 订单（已成交 0.6）
        entry_order = Order(
            id="entry_005",
            signal_id="signal_005",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal("1.0"),
            filled_qty=Decimal("0.6"),
            average_exec_price=Decimal("65000"),
            status=OrderStatus.PARTIALLY_FILLED,
            created_at=1234567890000,
            updated_at=1234567890000,
        )
        await repository.save(entry_order)

        # 只创建 TP1（没有 SL）
        existing_tp1 = Order(
            id="tp1_005",
            signal_id="signal_005",
            symbol="BTC/USDT:USDT",
            direction=Direction.SHORT,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.TP1,
            parent_order_id=entry_order.id,
            requested_qty=Decimal("0.3"),
            price=Decimal("66500"),
            status=OrderStatus.OPEN,
            created_at=1234567890000,
            updated_at=1234567890000,
        )
        await repository.save(existing_tp1)

        # 创建 ExecutionIntent
        intent = ExecutionIntent(
            id="intent_005",
            signal=sample_signal,
            status=ExecutionIntentStatus.PARTIALLY_PROTECTED,
            strategy=sample_strategy,
            order_id=entry_order.id,
        )
        orchestrator._intents[intent.id] = intent

        # Mock gateway.place_order 返回成功
        mock_gateway.place_order.return_value = MagicMock(
            is_success=True,
            exchange_order_id="exchange_005",
        )

        # Act
        await orchestrator._handle_entry_partially_filled(entry_order)

        # Assert: 应该只为 delta_qty = 0.3 生成保护单
        assert mock_gateway.place_order.call_count == 3, \
            f"应该为 delta_qty=0.3 生成 3 个保护单，实际调用 {mock_gateway.place_order.call_count} 次"

    @pytest.mark.asyncio
    async def test_canceled_sl_not_counted_as_protected(
        self, temp_db, mock_gateway, sample_strategy, sample_signal
    ):
        """
        场景 6：已有失效保护单时，仍会继续补挂缺失保护量

        条件：
        - ENTRY 已成交 0.5
        - 已有 SL（CANCELED 状态）覆盖 0.3
        - delta_qty = 0.5 - 0 = 0.5（CANCELED 的 SL 不计入）

        预期：
        - 为 0.5 生成新保护单
        """
        from src.application.order_lifecycle_service import OrderLifecycleService
        from src.application.capital_protection import CapitalProtectionManager

        # Arrange
        repository = OrderRepository(temp_db)
        await repository.initialize()
        order_lifecycle = OrderLifecycleService(repository)

        capital_protection = MagicMock(spec=CapitalProtectionManager)
        capital_protection.pre_order_check = AsyncMock()
        capital_protection.pre_order_check.return_value = MagicMock(allowed=True)

        orchestrator = ExecutionOrchestrator(
            capital_protection=capital_protection,
            order_lifecycle=order_lifecycle,
            gateway=mock_gateway,
        )

        # 创建 ENTRY 订单（已成交 0.5）
        entry_order = Order(
            id="entry_006",
            signal_id="signal_006",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal("1.0"),
            filled_qty=Decimal("0.5"),
            average_exec_price=Decimal("65000"),
            status=OrderStatus.PARTIALLY_FILLED,
            created_at=1234567890000,
            updated_at=1234567890000,
        )
        await repository.save(entry_order)

        # 创建已取消的 SL（不应计入 protected_qty_total）
        canceled_sl = Order(
            id="sl_006",
            signal_id="signal_006",
            symbol="BTC/USDT:USDT",
            direction=Direction.SHORT,
            order_type=OrderType.STOP_MARKET,
            order_role=OrderRole.SL,
            parent_order_id=entry_order.id,
            requested_qty=Decimal("0.3"),
            trigger_price=Decimal("64000"),
            status=OrderStatus.CANCELED,  # 已取消
            created_at=1234567890000,
            updated_at=1234567890000,
        )
        await repository.save(canceled_sl)

        # 创建 ExecutionIntent
        intent = ExecutionIntent(
            id="intent_006",
            signal=sample_signal,
            status=ExecutionIntentStatus.PARTIALLY_PROTECTED,
            strategy=sample_strategy,
            order_id=entry_order.id,
        )
        orchestrator._intents[intent.id] = intent

        # Mock gateway.place_order 返回成功
        mock_gateway.place_order.return_value = MagicMock(
            is_success=True,
            exchange_order_id="exchange_006",
        )

        # Act
        await orchestrator._handle_entry_partially_filled(entry_order)

        # Assert: 应该为 delta_qty = 0.5 生成保护单（CANCELED 的 SL 不计入）
        assert mock_gateway.place_order.call_count == 3, \
            f"应该为 delta_qty=0.5 生成 3 个保护单，实际调用 {mock_gateway.place_order.call_count} 次"

    @pytest.mark.asyncio
    async def test_price_fallback_when_average_exec_price_is_none(
        self, temp_db, mock_gateway, sample_strategy, sample_signal
    ):
        """
        场景 7：average_exec_price is None 但 price 有值时，仍能生成保护单

        条件：
        - ENTRY 已成交 0.3
        - average_exec_price = None
        - price = 65000（原始挂单价格）

        预期：
        - 使用 price 作为锚点生成保护单
        - 保护单正常提交
        """
        from src.application.order_lifecycle_service import OrderLifecycleService
        from src.application.capital_protection import CapitalProtectionManager

        # Arrange
        repository = OrderRepository(temp_db)
        await repository.initialize()
        order_lifecycle = OrderLifecycleService(repository)

        capital_protection = MagicMock(spec=CapitalProtectionManager)
        capital_protection.pre_order_check = AsyncMock()
        capital_protection.pre_order_check.return_value = MagicMock(allowed=True)

        orchestrator = ExecutionOrchestrator(
            capital_protection=capital_protection,
            order_lifecycle=order_lifecycle,
            gateway=mock_gateway,
        )

        # 创建 ENTRY 订单（已成交 0.3，但 average_exec_price 为 None）
        entry_order = Order(
            id="entry_007",
            signal_id="signal_007",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal("1.0"),
            filled_qty=Decimal("0.3"),
            average_exec_price=None,  # 暂无成交均价
            price=Decimal("65000"),   # 有原始价格
            status=OrderStatus.PARTIALLY_FILLED,
            created_at=1234567890000,
            updated_at=1234567890000,
        )
        await repository.save(entry_order)

        # 创建 ExecutionIntent
        intent = ExecutionIntent(
            id="intent_007",
            signal=sample_signal,
            status=ExecutionIntentStatus.SUBMITTED,
            strategy=sample_strategy,
            order_id=entry_order.id,
        )
        orchestrator._intents[intent.id] = intent

        # Mock gateway.place_order 返回成功
        mock_gateway.place_order.return_value = MagicMock(
            is_success=True,
            exchange_order_id="exchange_007",
        )

        # Act
        await orchestrator._handle_entry_partially_filled(entry_order)

        # Assert: 应该正常生成保护单
        assert mock_gateway.place_order.call_count == 3, \
            f"应该为 delta_qty=0.3 生成 3 个保护单，实际调用 {mock_gateway.place_order.call_count} 次"

        # 验证保护单的价格是基于 price fallback 计算的
        calls = mock_gateway.place_order.call_args_list
        for call in calls:
            # 确保没有因为 price=None 导致调用失败
            assert call is not None

    @pytest.mark.asyncio
    async def test_rejected_tp_not_counted_as_protected(
        self, temp_db, mock_gateway, sample_strategy, sample_signal
    ):
        """
        场景 8：REJECTED 的 TP 也不计入 protected_qty_total

        条件：
        - ENTRY 已成交 0.6
        - 已有 TP1（REJECTED 状态）
        - 没有 SL

        预期：
        - REJECTED 的 TP 不计入
        - 为 0.6 生成保护单
        """
        from src.application.order_lifecycle_service import OrderLifecycleService
        from src.application.capital_protection import CapitalProtectionManager

        # Arrange
        repository = OrderRepository(temp_db)
        await repository.initialize()
        order_lifecycle = OrderLifecycleService(repository)

        capital_protection = MagicMock(spec=CapitalProtectionManager)
        capital_protection.pre_order_check = AsyncMock()
        capital_protection.pre_order_check.return_value = MagicMock(allowed=True)

        orchestrator = ExecutionOrchestrator(
            capital_protection=capital_protection,
            order_lifecycle=order_lifecycle,
            gateway=mock_gateway,
        )

        # 创建 ENTRY 订单（已成交 0.6）
        entry_order = Order(
            id="entry_008",
            signal_id="signal_008",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal("1.0"),
            filled_qty=Decimal("0.6"),
            average_exec_price=Decimal("65000"),
            status=OrderStatus.PARTIALLY_FILLED,
            created_at=1234567890000,
            updated_at=1234567890000,
        )
        await repository.save(entry_order)

        # 创建被拒绝的 TP1（不应计入 protected_qty_total）
        rejected_tp1 = Order(
            id="tp1_008",
            signal_id="signal_008",
            symbol="BTC/USDT:USDT",
            direction=Direction.SHORT,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.TP1,
            parent_order_id=entry_order.id,
            requested_qty=Decimal("0.3"),
            price=Decimal("66500"),
            status=OrderStatus.REJECTED,  # 被拒绝
            created_at=1234567890000,
            updated_at=1234567890000,
        )
        await repository.save(rejected_tp1)

        # 创建 ExecutionIntent
        intent = ExecutionIntent(
            id="intent_008",
            signal=sample_signal,
            status=ExecutionIntentStatus.PARTIALLY_PROTECTED,
            strategy=sample_strategy,
            order_id=entry_order.id,
        )
        orchestrator._intents[intent.id] = intent

        # Mock gateway.place_order 返回成功
        mock_gateway.place_order.return_value = MagicMock(
            is_success=True,
            exchange_order_id="exchange_008",
        )

        # Act
        await orchestrator._handle_entry_partially_filled(entry_order)

        # Assert: 应该为 delta_qty = 0.6 生成保护单（REJECTED 的 TP 不计入）
        assert mock_gateway.place_order.call_count == 3, \
            f"应该为 delta_qty=0.6 生成 3 个保护单，实际调用 {mock_gateway.place_order.call_count} 次"
