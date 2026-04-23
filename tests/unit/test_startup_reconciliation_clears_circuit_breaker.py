"""
P0-4: 启动对账清除 pending_recovery 和熔断

测试目标：
1. 启动对账能够处理 orchestrator 的 pending_recovery 记录
2. 对账成功后清除 pending_recovery 记录
3. 该 symbol 无剩余 pending_recovery 时清除熔断

验收标准：
- 测试可跑通（pytest 可选运行）
- 覆盖 P0-4 的关键语义
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
from src.application.startup_reconciliation_service import StartupReconciliationService
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
async def test_startup_reconciliation_clears_pending_recovery_and_circuit_breaker():
    """
    P0-4 测试：启动对账清除 pending_recovery 和熔断

    场景：
    1. orchestrator 有 pending_recovery 记录（order_id/exchange_order_id/symbol）
    2. symbol 已被熔断
    3. mock gateway.fetch_order 返回 FILLED 状态
    4. 运行 StartupReconciliationService.run_startup_reconciliation()
    断言：
    - pending_recovery 被清除
    - symbol 熔断被清除
    - update_order_from_exchange 被调用（本地订单状态被推进）
    """
    # 准备：创建 fake repos
    fake_order_repo = FakeOrderRepository()
    fake_intent_repo = FakeExecutionIntentRepository()

    # 准备：创建 orchestrator
    capital_protection = MagicMock(spec=CapitalProtectionManager)
    gateway = MagicMock(spec=ExchangeGateway)

    order_lifecycle = OrderLifecycleService(repository=fake_order_repo)

    orchestrator = ExecutionOrchestrator(
        capital_protection=capital_protection,
        order_lifecycle=order_lifecycle,
        gateway=gateway,
        intent_repository=fake_intent_repo,
    )

    # 准备：创建本地订单
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    local_order = Order(
        id="order_test_001",
        signal_id="sig_test_001",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        requested_qty=Decimal("0.05"),
        exchange_order_id="ex_order_001",
        status=OrderStatus.OPEN,
        created_at=current_time,
        updated_at=current_time,
    )
    await fake_order_repo.save(local_order)

    # P0-2：手动添加 pending_recovery 记录
    orchestrator._pending_recovery["order_test_001"] = {
        "order_id": "order_test_001",
        "exchange_order_id": "ex_order_001",
        "symbol": "BTC/USDT:USDT",
        "error": "交易所撤销订单失败",
    }

    # P0-2：手动触发熔断
    orchestrator._circuit_breaker_symbols.add("BTC/USDT:USDT")

    # 验证初始状态
    assert len(orchestrator.list_pending_recovery()) == 1
    assert orchestrator.is_symbol_blocked("BTC/USDT:USDT") is True

    # 准备：mock gateway.fetch_order 返回 FILLED 状态
    fetch_result = MagicMock()
    fetch_result.amount = Decimal("0.05")
    fetch_result.price = Decimal("50000")
    fetch_result.status = OrderStatus.FILLED
    gateway.fetch_order = AsyncMock(return_value=fetch_result)

    # 准备：创建 StartupReconciliationService（注入 orchestrator）
    reconciliation_service = StartupReconciliationService(
        gateway=gateway,
        repository=fake_order_repo,
        lifecycle=order_lifecycle,
        orchestrator=orchestrator,
    )

    # 执行：运行启动对账
    summary = await reconciliation_service.run_startup_reconciliation()

    # P0-4 验证：pending_recovery 被清除
    assert len(orchestrator.list_pending_recovery()) == 0
    assert summary["orchestrator_recovery_cleared_count"] == 1

    # P0-4 验证：symbol 熔断被清除
    assert orchestrator.is_symbol_blocked("BTC/USDT:USDT") is False
    assert summary["orchestrator_circuit_breaker_cleared_count"] == 1

    # P0-4 验证：本地订单状态被推进
    updated_order = await fake_order_repo.get_order("order_test_001")
    assert updated_order.status == OrderStatus.FILLED


@pytest.mark.asyncio
async def test_startup_reconciliation_keeps_circuit_breaker_if_pending_recovery_remains():
    """
    P0-4 测试：如果 symbol 还有剩余 pending_recovery，熔断不会被清除

    场景：
    1. orchestrator 有 2 条 pending_recovery 记录（同一个 symbol）
    2. symbol 已被熔断
    3. 第一条对账成功，第二条对账失败
    断言：
    - 第一条 pending_recovery 被清除
    - 第二条 pending_recovery 仍存在
    - symbol 熔断仍存在（因为还有剩余 pending_recovery）
    """
    # 准备：创建 fake repos
    fake_order_repo = FakeOrderRepository()
    fake_intent_repo = FakeExecutionIntentRepository()

    # 准备：创建 orchestrator
    capital_protection = MagicMock(spec=CapitalProtectionManager)
    gateway = MagicMock(spec=ExchangeGateway)

    order_lifecycle = OrderLifecycleService(repository=fake_order_repo)

    orchestrator = ExecutionOrchestrator(
        capital_protection=capital_protection,
        order_lifecycle=order_lifecycle,
        gateway=gateway,
        intent_repository=fake_intent_repo,
    )

    # 准备：创建 2 个本地订单
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    order1 = Order(
        id="order_test_001",
        signal_id="sig_test_001",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        requested_qty=Decimal("0.05"),
        exchange_order_id="ex_order_001",
        status=OrderStatus.OPEN,
        created_at=current_time,
        updated_at=current_time,
    )
    await fake_order_repo.save(order1)

    order2 = Order(
        id="order_test_002",
        signal_id="sig_test_002",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        requested_qty=Decimal("0.03"),
        exchange_order_id="ex_order_002",
        status=OrderStatus.OPEN,
        created_at=current_time,
        updated_at=current_time,
    )
    await fake_order_repo.save(order2)

    # P0-2：手动添加 2 条 pending_recovery 记录（同一个 symbol）
    orchestrator._pending_recovery["order_test_001"] = {
        "order_id": "order_test_001",
        "exchange_order_id": "ex_order_001",
        "symbol": "BTC/USDT:USDT",
        "error": "交易所撤销订单失败",
    }

    orchestrator._pending_recovery["order_test_002"] = {
        "order_id": "order_test_002",
        "exchange_order_id": "ex_order_002",
        "symbol": "BTC/USDT:USDT",
        "error": "交易所撤销订单失败",
    }

    # P0-2：手动触发熔断
    orchestrator._circuit_breaker_symbols.add("BTC/USDT:USDT")

    # 验证初始状态
    assert len(orchestrator.list_pending_recovery()) == 2
    assert orchestrator.is_symbol_blocked("BTC/USDT:USDT") is True

    # 准备：mock gateway.fetch_order
    # 第一次调用成功，第二次调用失败
    fetch_result_success = MagicMock()
    fetch_result_success.amount = Decimal("0.05")
    fetch_result_success.price = Decimal("50000")
    fetch_result_success.status = OrderStatus.FILLED

    gateway.fetch_order = AsyncMock()
    gateway.fetch_order.side_effect = [
        fetch_result_success,  # 第一次调用成功
        Exception("交易所查询失败"),  # 第二次调用失败
    ]

    # 准备：创建 StartupReconciliationService
    reconciliation_service = StartupReconciliationService(
        gateway=gateway,
        repository=fake_order_repo,
        lifecycle=order_lifecycle,
        orchestrator=orchestrator,
    )

    # 执行：运行启动对账
    summary = await reconciliation_service.run_startup_reconciliation()

    # P0-4 验证：一条 pending_recovery 被清除，一条仍存在
    remaining_pending = orchestrator.list_pending_recovery()
    assert len(remaining_pending) == 1
    # 不检查具体是哪个订单（迭代顺序不确定），只检查数量

    # P0-4 验证：symbol 熔断仍存在（因为还有剩余 pending_recovery）
    assert orchestrator.is_symbol_blocked("BTC/USDT:USDT") is True
    assert summary["orchestrator_circuit_breaker_cleared_count"] == 0


if __name__ == "__main__":
    # 可直接运行：python tests/unit/test_startup_reconciliation_clears_circuit_breaker.py
    import asyncio

    async def run_tests():
        print("Running test_startup_reconciliation_clears_pending_recovery_and_circuit_breaker...")
        await test_startup_reconciliation_clears_pending_recovery_and_circuit_breaker()
        print("✅ test_startup_reconciliation_clears_pending_recovery_and_circuit_breaker passed\n")

        print("Running test_startup_reconciliation_keeps_circuit_breaker_if_pending_recovery_remains...")
        await test_startup_reconciliation_keeps_circuit_breaker_if_pending_recovery_remains()
        print("✅ test_startup_reconciliation_keeps_circuit_breaker_if_pending_recovery_remains passed\n")

        print("Running test_startup_reconciliation_does_not_clear_pending_or_breaker_when_open...")
        await test_startup_reconciliation_does_not_clear_pending_or_breaker_when_open()
        print("✅ test_startup_reconciliation_does_not_clear_pending_or_breaker_when_open passed\n")

        print("All tests passed! ✅")

    asyncio.run(run_tests())


@pytest.mark.asyncio
async def test_startup_reconciliation_does_not_clear_pending_or_breaker_when_open():
    """
    P0-4.1 测试：交易所返回 OPEN 状态时，不清除 pending_recovery 和熔断

    场景：
    1. orchestrator 有 pending_recovery 记录
    2. symbol 已被熔断
    3. mock gateway.fetch_order 返回 OPEN 状态（非终态）
    断言：
    - pending_recovery 仍存在
    - symbol 熔断仍存在
    - summary 的 orchestrator_recovery_cleared_count 为 0
    """
    # 准备：创建 fake repos
    fake_order_repo = FakeOrderRepository()
    fake_intent_repo = FakeExecutionIntentRepository()

    # 准备：创建 orchestrator
    capital_protection = MagicMock(spec=CapitalProtectionManager)
    gateway = MagicMock(spec=ExchangeGateway)

    order_lifecycle = OrderLifecycleService(repository=fake_order_repo)

    orchestrator = ExecutionOrchestrator(
        capital_protection=capital_protection,
        order_lifecycle=order_lifecycle,
        gateway=gateway,
        intent_repository=fake_intent_repo,
    )

    # 准备：创建本地订单
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    local_order = Order(
        id="order_test_001",
        signal_id="sig_test_001",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        requested_qty=Decimal("0.05"),
        exchange_order_id="ex_order_001",
        status=OrderStatus.OPEN,
        created_at=current_time,
        updated_at=current_time,
    )
    await fake_order_repo.save(local_order)

    # P0-2：手动添加 pending_recovery 记录
    orchestrator._pending_recovery["order_test_001"] = {
        "order_id": "order_test_001",
        "exchange_order_id": "ex_order_001",
        "symbol": "BTC/USDT:USDT",
        "error": "交易所撤销订单失败",
    }

    # P0-2：手动触发熔断
    orchestrator._circuit_breaker_symbols.add("BTC/USDT:USDT")

    # 验证初始状态
    assert len(orchestrator.list_pending_recovery()) == 1
    assert orchestrator.is_symbol_blocked("BTC/USDT:USDT") is True

    # 准备：mock gateway.fetch_order 返回 OPEN 状态（非终态）
    fetch_result = MagicMock()
    fetch_result.amount = Decimal("0.05")
    fetch_result.price = Decimal("50000")
    fetch_result.status = OrderStatus.OPEN  # 非终态
    gateway.fetch_order = AsyncMock(return_value=fetch_result)

    # 准备：创建 StartupReconciliationService（注入 orchestrator）
    reconciliation_service = StartupReconciliationService(
        gateway=gateway,
        repository=fake_order_repo,
        lifecycle=order_lifecycle,
        orchestrator=orchestrator,
    )

    # 执行：运行启动对账
    summary = await reconciliation_service.run_startup_reconciliation()

    # P0-4.1 验证：pending_recovery 仍存在（未清除）
    assert len(orchestrator.list_pending_recovery()) == 1
    assert summary["orchestrator_recovery_cleared_count"] == 0

    # P0-4.1 验证：symbol 熔断仍存在（未清除）
    assert orchestrator.is_symbol_blocked("BTC/USDT:USDT") is True
    assert summary["orchestrator_circuit_breaker_cleared_count"] == 0

    # P0-4.1 验证：本地订单状态未变化（仍是 OPEN）
    updated_order = await fake_order_repo.get_order("order_test_001")
    assert updated_order.status == OrderStatus.OPEN
