"""
P0-7: Execution Recovery Management 测试

测试目标：
1. list_circuit_breaker_symbols() 返回排序列表
2. clear_pending_recovery() 生效
3. clear_circuit_breaker() 生效
4. 脚本在 _execution_orchestrator is None 时返回非 0
"""
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List
from unittest.mock import MagicMock, patch
import subprocess
import sys

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
async def test_list_circuit_breaker_symbols_returns_sorted_list():
    """
    测试 list_circuit_breaker_symbols() 返回排序列表

    场景：
    1. orchestrator 有 3 个熔断 symbol（无序）
    断言：
    - 返回排序列表
    """
    # 准备：创建 orchestrator
    fake_order_repo = FakeOrderRepository()
    fake_intent_repo = FakeExecutionIntentRepository()

    capital_protection = MagicMock(spec=CapitalProtectionManager)
    gateway = MagicMock(spec=ExchangeGateway)

    order_lifecycle = OrderLifecycleService(repository=fake_order_repo)

    orchestrator = ExecutionOrchestrator(
        capital_protection=capital_protection,
        order_lifecycle=order_lifecycle,
        gateway=gateway,
        intent_repository=fake_intent_repo,
    )

    # 手动添加熔断 symbol（无序）
    orchestrator._circuit_breaker_symbols.add("ETH/USDT:USDT")
    orchestrator._circuit_breaker_symbols.add("BTC/USDT:USDT")
    orchestrator._circuit_breaker_symbols.add("SOL/USDT:USDT")

    # 执行：获取熔断列表
    symbols = orchestrator.list_circuit_breaker_symbols()

    # 验证：返回排序列表
    assert len(symbols) == 3
    assert symbols == ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]


@pytest.mark.asyncio
async def test_clear_pending_recovery_takes_effect():
    """
    测试 clear_pending_recovery() 生效

    场景：
    1. orchestrator 有 pending_recovery 记录
    2. 调用 clear_pending_recovery()
    断言：
    - 记录被清除
    """
    # 准备：创建 orchestrator
    fake_order_repo = FakeOrderRepository()
    fake_intent_repo = FakeExecutionIntentRepository()

    capital_protection = MagicMock(spec=CapitalProtectionManager)
    gateway = MagicMock(spec=ExchangeGateway)

    order_lifecycle = OrderLifecycleService(repository=fake_order_repo)

    orchestrator = ExecutionOrchestrator(
        capital_protection=capital_protection,
        order_lifecycle=order_lifecycle,
        gateway=gateway,
        intent_repository=fake_intent_repo,
    )

    # 手动添加 pending_recovery 记录
    orchestrator._pending_recovery["order_001"] = {
        "order_id": "order_001",
        "exchange_order_id": "ex_order_001",
        "symbol": "BTC/USDT:USDT",
        "error": "交易所撤销订单失败",
        "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
    }

    # 验证初始状态
    assert len(orchestrator.list_pending_recovery()) == 1

    # 执行：清除 pending_recovery
    orchestrator.clear_pending_recovery("order_001")

    # 验证：记录被清除
    assert len(orchestrator.list_pending_recovery()) == 0
    assert orchestrator.get_pending_recovery("order_001") is None


@pytest.mark.asyncio
async def test_clear_circuit_breaker_takes_effect():
    """
    测试 clear_circuit_breaker() 生效

    场景：
    1. orchestrator 有熔断 symbol
    2. 调用 clear_circuit_breaker()
    断言：
    - 熔断被清除
    """
    # 准备：创建 orchestrator
    fake_order_repo = FakeOrderRepository()
    fake_intent_repo = FakeExecutionIntentRepository()

    capital_protection = MagicMock(spec=CapitalProtectionManager)
    gateway = MagicMock(spec=ExchangeGateway)

    order_lifecycle = OrderLifecycleService(repository=fake_order_repo)

    orchestrator = ExecutionOrchestrator(
        capital_protection=capital_protection,
        order_lifecycle=order_lifecycle,
        gateway=gateway,
        intent_repository=fake_intent_repo,
    )

    # 手动添加熔断 symbol
    orchestrator._circuit_breaker_symbols.add("BTC/USDT:USDT")

    # 验证初始状态
    assert orchestrator.is_symbol_blocked("BTC/USDT:USDT") is True

    # 执行：清除熔断
    orchestrator.clear_circuit_breaker("BTC/USDT:USDT")

    # 验证：熔断被清除
    assert orchestrator.is_symbol_blocked("BTC/USDT:USDT") is False
    assert len(orchestrator.list_circuit_breaker_symbols()) == 0


def test_script_returns_nonzero_when_orchestrator_not_initialized():
    """
    测试脚本在 _execution_orchestrator is None 时返回非 0

    场景：
    1. _execution_orchestrator 为 None 或无法导入
    断言：
    - 脚本返回非 0 退出码
    - 输出包含明确的错误信息
    """
    # 执行脚本（在独立进程，无法导入 _execution_orchestrator）
    result = subprocess.run(
        [sys.executable, "scripts/manage_execution_recovery.py", "list-pending"],
        capture_output=True,
        text=True,
    )

    # 验证：返回非 0 退出码
    assert result.returncode != 0
    # 验证：输出包含错误信息（可能是"Cannot import"或"not initialized"）
    assert (
        "Cannot import _execution_orchestrator" in result.stdout
        or "ExecutionOrchestrator not initialized" in result.stdout
    )


if __name__ == "__main__":
    # 可直接运行：python tests/unit/test_p0_7_manage_execution_recovery.py
    import asyncio

    async def run_tests():
        print("Running test_list_circuit_breaker_symbols_returns_sorted_list...")
        await test_list_circuit_breaker_symbols_returns_sorted_list()
        print("✅ test_list_circuit_breaker_symbols_returns_sorted_list passed\n")

        print("Running test_clear_pending_recovery_takes_effect...")
        await test_clear_pending_recovery_takes_effect()
        print("✅ test_clear_pending_recovery_takes_effect passed\n")

        print("Running test_clear_circuit_breaker_takes_effect...")
        await test_clear_circuit_breaker_takes_effect()
        print("✅ test_clear_circuit_breaker_takes_effect passed\n")

        print("Running test_script_returns_nonzero_when_orchestrator_not_initialized...")
        test_script_returns_nonzero_when_orchestrator_not_initialized()
        print("✅ test_script_returns_nonzero_when_orchestrator_not_initialized passed\n")

        print("All tests passed! ✅")

    asyncio.run(run_tests())
