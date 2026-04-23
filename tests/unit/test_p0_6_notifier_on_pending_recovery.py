"""
P0-6: pending_recovery / circuit_breaker 触发时发送告警

测试目标：
1. cancel old SL 失败时 notifier 被调用 1 次
2. 告警消息包含 symbol / order_id / exchange_order_id / circuit breaker 关键词
3. notifier 抛异常不会中断主流程（pending_recovery 和熔断仍然照常记录）
"""
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List
from unittest.mock import AsyncMock, MagicMock

from src.domain.models import (
    Order,
    OrderType,
    OrderRole,
    OrderStatus,
    Direction,
)
from src.application.execution_orchestrator import ExecutionOrchestrator
from src.application.capital_protection import CapitalProtectionManager
from src.application.order_lifecycle_service import OrderLifecycleService
from src.infrastructure.exchange_gateway import ExchangeGateway
from src.infrastructure.repository_ports import (
    OrderRepositoryPort,
    ExecutionIntentRepositoryPort,
)


class FakeOrderRepository(OrderRepositoryPort):
    """最小 fake order repo"""

    def __init__(self):
        self._storage: dict = {}

    async def save(self, order: Order) -> None:
        """保存订单"""
        self._storage[order.id] = order

    async def get_order(self, order_id: str) -> Optional[Order]:
        """获取订单"""
        return self._storage.get(order_id)

    async def get_orders_by_signal(self, signal_id: str) -> List[Order]:
        """获取信号的所有订单"""
        return [o for o in self._storage.values() if o.signal_id == signal_id]

    async def get_order_by_exchange_id(self, exchange_order_id: str) -> Optional[Order]:
        """根据交易所订单 ID 获取订单"""
        for order in self._storage.values():
            if order.exchange_order_id == exchange_order_id:
                return order
        return None

    async def get_orders_by_status(self, status: OrderStatus) -> List[Order]:
        """根据状态获取订单列表"""
        return [o for o in self._storage.values() if o.status == status]


class FakeExecutionIntentRepository(ExecutionIntentRepositoryPort):
    """最小 fake intent repo"""

    def __init__(self):
        self._storage: dict = {}

    async def save(self, intent) -> None:
        """保存执行意图"""
        self._storage[intent.id] = intent
        if intent.order_id:
            self._storage[f"order:{intent.order_id}"] = intent

    async def get(self, intent_id: str):
        """按 ID 获取"""
        return self._storage.get(intent_id)

    async def get_by_signal_id(self, signal_id: str):
        """按信号 ID 获取"""
        for intent in self._storage.values():
            if hasattr(intent, 'signal_id') and intent.signal_id == signal_id:
                return intent
        return None

    async def get_by_order_id(self, order_id: str):
        """按订单 ID 获取"""
        return self._storage.get(f"order:{order_id}")

    async def list(self, status=None):
        """列出执行意图"""
        intents = [i for i in self._storage.values() if hasattr(i, 'id')]
        if status:
            intents = [i for i in intents if hasattr(i, 'status') and i.status == status]
        return intents


@pytest.mark.asyncio
async def test_notifier_called_on_pending_recovery_and_circuit_breaker():
    """
    P0-6 测试：cancel old SL 失败时 notifier 被调用

    场景：
    1. orchestrator 有 notifier 注入
    2. cancel 交易所侧旧 SL 失败
    3. 触发 pending_recovery + circuit_breaker
    断言：
    - notifier 被调用 1 次
    - 消息包含 symbol / order_id / exchange_order_id / circuit_breaker_triggered
    - pending_recovery 和 circuit_breaker 正常记录
    """
    # 准备：创建 fake repos
    fake_order_repo = FakeOrderRepository()
    fake_intent_repo = FakeExecutionIntentRepository()

    # 准备：创建 orchestrator
    capital_protection = MagicMock(spec=CapitalProtectionManager)
    gateway = MagicMock(spec=ExchangeGateway)

    order_lifecycle = OrderLifecycleService(repository=fake_order_repo)

    # P0-6：创建 mock notifier
    mock_notifier = AsyncMock()

    orchestrator = ExecutionOrchestrator(
        capital_protection=capital_protection,
        order_lifecycle=order_lifecycle,
        gateway=gateway,
        intent_repository=fake_intent_repo,
        notifier=mock_notifier,  # P0-6: 注入 mock notifier
    )

    # 准备：创建本地订单
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 先创建 ENTRY 订单
    entry_order = Order(
        id="entry_test_001",
        signal_id="sig_test_001",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal("0.1"),
        filled_qty=Decimal("0.1"),
        average_exec_price=Decimal("50000"),
        status=OrderStatus.FILLED,
        created_at=current_time,
        updated_at=current_time,
    )
    await fake_order_repo.save(entry_order)

    # 创建旧 SL 订单（parent_order_id 指向 ENTRY，状态 OPEN）
    local_order = Order(
        id="order_test_001",
        signal_id="sig_test_001",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        requested_qty=Decimal("0.05"),
        exchange_order_id="ex_order_001",
        parent_order_id="entry_test_001",  # 关键：关联到 ENTRY
        status=OrderStatus.OPEN,  # 关键：状态为 OPEN（会被识别为有效 SL）
        created_at=current_time,
        updated_at=current_time,
    )
    await fake_order_repo.save(local_order)

    # 准备：mock gateway.cancel_order 抛异常
    gateway.cancel_order = AsyncMock(side_effect=Exception("交易所撤销订单失败"))

    # 创建 ExecutionIntent（包含 strategy）
    from src.domain.execution_intent import ExecutionIntent, ExecutionIntentStatus
    from src.domain.models import OrderStrategy, SignalResult

    strategy = OrderStrategy(
        id="test_strategy_001",
        name="Test Strategy",
        tp_levels=1,
        tp_ratios=[Decimal("1.0")],
        tp_targets=[Decimal("1.0")],
        initial_stop_loss_rr=Decimal("-1.0"),
    )

    # 创建真实的 SignalResult
    signal = SignalResult(
        symbol="BTC/USDT:USDT",
        timeframe="15m",
        direction=Direction.LONG,
        entry_price=Decimal("50000"),
        suggested_stop_loss=Decimal("48000"),
        suggested_position_size=Decimal("0.1"),
        current_leverage=1,
        tags=[],
        risk_reward_info="1R",
        strategy_name="test_strategy",
        score=0.85,
    )

    intent = ExecutionIntent(
        id="intent_test_001",
        signal_id="sig_test_001",
        signal=signal,
        status=ExecutionIntentStatus.SUBMITTED,
        strategy=strategy,
        order_id="entry_test_001",
    )
    await fake_intent_repo.save(intent)

    # 执行：调用 _handle_entry_partially_filled
    await orchestrator._handle_entry_partially_filled(entry_order)

    # P0-6 验证：notifier 被调用 1 次
    assert mock_notifier.call_count == 1

    # P0-6 验证：消息内容正确
    call_args = mock_notifier.call_args
    title = call_args[0][0]
    message = call_args[0][1]

    assert title == "[P0] Pending Recovery Triggered"
    assert "symbol=BTC/USDT:USDT" in message
    assert "order_id=order_test_001" in message
    assert "exchange_order_id=ex_order_001" in message
    assert "error=交易所撤销订单失败" in message
    assert "action=circuit_breaker_triggered" in message

    # P0-6 验证：pending_recovery 和 circuit_breaker 正常记录
    assert len(orchestrator.list_pending_recovery()) == 1
    assert orchestrator.is_symbol_blocked("BTC/USDT:USDT") is True


@pytest.mark.asyncio
async def test_notifier_exception_does_not_interrupt_main_flow():
    """
    P0-6 测试：notifier 抛异常不会中断主流程

    场景：
    1. orchestrator 有 notifier 注入（会抛异常）
    2. cancel 交易所侧旧 SL 失败
    断言：
    - notifier 被调用
    - notifier 抛异常后主流程继续
    - pending_recovery 和 circuit_breaker 仍然正常记录
    """
    # 准备：创建 fake repos
    fake_order_repo = FakeOrderRepository()
    fake_intent_repo = FakeExecutionIntentRepository()

    # 准备：创建 orchestrator
    capital_protection = MagicMock(spec=CapitalProtectionManager)
    gateway = MagicMock(spec=ExchangeGateway)

    order_lifecycle = OrderLifecycleService(repository=fake_order_repo)

    # P0-6：创建会抛异常的 mock notifier
    mock_notifier = AsyncMock(side_effect=Exception("飞书 webhook 失败"))

    orchestrator = ExecutionOrchestrator(
        capital_protection=capital_protection,
        order_lifecycle=order_lifecycle,
        gateway=gateway,
        intent_repository=fake_intent_repo,
        notifier=mock_notifier,
    )

    # 准备：创建本地订单
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 先创建 ENTRY 订单
    entry_order = Order(
        id="entry_test_002",
        signal_id="sig_test_002",
        symbol="ETH/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal("0.1"),
        filled_qty=Decimal("0.1"),
        average_exec_price=Decimal("3000"),
        status=OrderStatus.FILLED,
        created_at=current_time,
        updated_at=current_time,
    )
    await fake_order_repo.save(entry_order)

    # 创建旧 SL 订单（parent_order_id 指向 ENTRY，状态 OPEN）
    local_order = Order(
        id="order_test_002",
        signal_id="sig_test_002",
        symbol="ETH/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        requested_qty=Decimal("0.05"),
        exchange_order_id="ex_order_002",
        parent_order_id="entry_test_002",  # 关键：关联到 ENTRY
        status=OrderStatus.OPEN,  # 关键：状态为 OPEN（会被识别为有效 SL）
        created_at=current_time,
        updated_at=current_time,
    )
    await fake_order_repo.save(local_order)

    # 准备：mock gateway.cancel_order 抛异常
    gateway.cancel_order = AsyncMock(side_effect=Exception("交易所撤销订单失败"))

    # 创建 ExecutionIntent
    from src.domain.execution_intent import ExecutionIntent, ExecutionIntentStatus
    from src.domain.models import OrderStrategy, SignalResult

    strategy = OrderStrategy(
        id="test_strategy_002",
        name="Test Strategy",
        tp_levels=1,
        tp_ratios=[Decimal("1.0")],
        tp_targets=[Decimal("1.0")],
        initial_stop_loss_rr=Decimal("-1.0"),
    )

    # 创建真实的 SignalResult
    signal = SignalResult(
        symbol="ETH/USDT:USDT",
        timeframe="15m",
        direction=Direction.LONG,
        entry_price=Decimal("3000"),
        suggested_stop_loss=Decimal("2800"),
        suggested_position_size=Decimal("0.1"),
        current_leverage=1,
        tags=[],
        risk_reward_info="1R",
        strategy_name="test_strategy",
        score=0.85,
    )

    intent = ExecutionIntent(
        id="intent_test_002",
        signal_id="sig_test_002",
        signal=signal,
        status=ExecutionIntentStatus.SUBMITTED,
        strategy=strategy,
        order_id="entry_test_002",
    )
    await fake_intent_repo.save(intent)

    # 执行：调用 _handle_entry_partially_filled
    await orchestrator._handle_entry_partially_filled(entry_order)

    # P0-6 验证：notifier 被调用（虽然抛异常）
    assert mock_notifier.call_count == 1

    # P0-6 验证：主流程继续，pending_recovery 和 circuit_breaker 正常记录
    assert len(orchestrator.list_pending_recovery()) == 1
    assert orchestrator.is_symbol_blocked("ETH/USDT:USDT") is True


if __name__ == "__main__":
    # 可直接运行：python tests/unit/test_p0_6_notifier_on_pending_recovery.py
    import asyncio

    async def run_tests():
        print("Running test_notifier_called_on_pending_recovery_and_circuit_breaker...")
        await test_notifier_called_on_pending_recovery_and_circuit_breaker()
        print("✅ test_notifier_called_on_pending_recovery_and_circuit_breaker passed\n")

        print("Running test_notifier_exception_does_not_interrupt_main_flow...")
        await test_notifier_exception_does_not_interrupt_main_flow()
        print("✅ test_notifier_exception_does_not_interrupt_main_flow passed\n")

        print("All tests passed! ✅")

    asyncio.run(run_tests())
