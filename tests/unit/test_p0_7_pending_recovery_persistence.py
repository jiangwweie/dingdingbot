"""
P0-7: Pending Recovery Persistence 测试

测试目标：
1. orchestrator 记录 pending_recovery 时，repository 中也能查到
2. clear_pending_recovery 后，repository 中已删除
3. manage_execution_recovery.py 可以在独立进程下 list-pending 成功读到真实记录
4. manage_execution_recovery.py 可以 clear-pending 并删除真实记录
"""
import pytest
import asyncio
import subprocess
import sys
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List
from unittest.mock import MagicMock

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
from src.infrastructure.pending_recovery_repository import PendingRecoveryRepository
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
async def test_orchestrator_persists_pending_recovery_to_repository():
    """
    测试 orchestrator 记录 pending_recovery 时，repository 中也能查到

    场景：
    1. orchestrator 有 pending_recovery_repository 注入
    2. cancel 交易所侧旧 SL 失败
    3. 触发 pending_recovery 记录
    断言：
    - repository 中能查到记录
    """
    # 准备：创建 fake repos
    fake_order_repo = FakeOrderRepository()
    fake_intent_repo = FakeExecutionIntentRepository()

    # 准备：创建真实的 PendingRecoveryRepository
    test_db_path = "data/test_pending_recovery.db"
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    pending_recovery_repo = PendingRecoveryRepository(db_path=test_db_path)
    await pending_recovery_repo.initialize()

    # 准备：创建 orchestrator
    capital_protection = MagicMock(spec=CapitalProtectionManager)
    gateway = MagicMock(spec=ExchangeGateway)

    order_lifecycle = OrderLifecycleService(repository=fake_order_repo)

    orchestrator = ExecutionOrchestrator(
        capital_protection=capital_protection,
        order_lifecycle=order_lifecycle,
        gateway=gateway,
        intent_repository=fake_intent_repo,
        pending_recovery_repository=pending_recovery_repo,
    )

    # 准备：创建 ENTRY 和旧 SL 订单
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

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

    old_sl = Order(
        id="sl_test_001",
        signal_id="sig_test_001",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        requested_qty=Decimal("0.05"),
        exchange_order_id="ex_sl_001",
        parent_order_id="entry_test_001",
        status=OrderStatus.OPEN,
        created_at=current_time,
        updated_at=current_time,
    )
    await fake_order_repo.save(old_sl)

    # 准备：创建 ExecutionIntent
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

    # 准备：mock gateway.cancel_order 抛异常
    gateway.cancel_order = MagicMock(side_effect=Exception("交易所撤销订单失败"))

    # 执行：调用 _handle_entry_partially_filled
    await orchestrator._handle_entry_partially_filled(entry_order)

    # 验证：repository 中能查到记录
    record = await pending_recovery_repo.get("sl_test_001")
    assert record is not None
    assert record["order_id"] == "sl_test_001"
    assert record["exchange_order_id"] == "ex_sl_001"
    assert record["symbol"] == "BTC/USDT:USDT"
    assert "交易所撤销订单失败" in record["error"]

    # 清理
    await pending_recovery_repo.close()
    if os.path.exists(test_db_path):
        os.remove(test_db_path)


@pytest.mark.asyncio
async def test_clear_pending_recovery_deletes_from_repository():
    """
    测试 clear_pending_recovery 后，repository 中已删除

    场景：
    1. orchestrator 有 pending_recovery 记录
    2. 调用 clear_pending_recovery_async()
    断言：
    - repository 中记录被删除
    """
    # 准备：创建真实的 PendingRecoveryRepository
    test_db_path = "data/test_pending_recovery.db"
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    pending_recovery_repo = PendingRecoveryRepository(db_path=test_db_path)
    await pending_recovery_repo.initialize()

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
        pending_recovery_repository=pending_recovery_repo,
    )

    # 准备：手动添加 pending_recovery 记录
    await pending_recovery_repo.save({
        "order_id": "order_001",
        "exchange_order_id": "ex_order_001",
        "symbol": "BTC/USDT:USDT",
        "error": "交易所撤销订单失败",
        "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
    })

    # 验证初始状态
    record = await pending_recovery_repo.get("order_001")
    assert record is not None

    # 执行：清除 pending_recovery
    await orchestrator.clear_pending_recovery_async("order_001")

    # 验证：repository 中记录被删除
    record = await pending_recovery_repo.get("order_001")
    assert record is None

    # 清理
    await pending_recovery_repo.close()
    if os.path.exists(test_db_path):
        os.remove(test_db_path)


@pytest.mark.asyncio
async def test_script_list_pending_reads_real_records():
    """
    测试 manage_execution_recovery.py 可以在独立进程下 list-pending 成功读到真实记录

    场景：
    1. SQLite 中有真实的 pending_recovery 记录
    2. 运行脚本 list-pending
    断言：
    - 脚本返回 0
    - 输出包含记录信息
    """
    # 准备：创建真实的 PendingRecoveryRepository 并写入记录
    test_db_path = "data/pending_recovery.db"  # 脚本默认路径
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    pending_recovery_repo = PendingRecoveryRepository(db_path=test_db_path)
    await pending_recovery_repo.initialize()

    await pending_recovery_repo.save({
        "order_id": "order_script_test",
        "exchange_order_id": "ex_order_script_test",
        "symbol": "BTC/USDT:USDT",
        "error": "交易所撤销订单失败",
        "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
    })

    await pending_recovery_repo.close()

    # 执行：运行脚本
    result = subprocess.run(
        [sys.executable, "scripts/manage_execution_recovery.py", "list-pending"],
        capture_output=True,
        text=True,
    )

    # 验证：脚本返回 0
    assert result.returncode == 0
    # 验证：输出包含记录信息
    assert "order_script_test" in result.stdout
    assert "BTC/USDT:USDT" in result.stdout

    # 清理
    if os.path.exists(test_db_path):
        os.remove(test_db_path)


@pytest.mark.asyncio
async def test_script_clear_pending_deletes_real_records():
    """
    测试 manage_execution_recovery.py 可以 clear-pending 并删除真实记录

    场景：
    1. SQLite 中有真实的 pending_recovery 记录
    2. 运行脚本 clear-pending
    断言：
    - 脚本返回 0
    - SQLite 中记录被删除
    """
    # 准备：创建真实的 PendingRecoveryRepository 并写入记录
    test_db_path = "data/pending_recovery.db"
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    pending_recovery_repo = PendingRecoveryRepository(db_path=test_db_path)
    await pending_recovery_repo.initialize()

    await pending_recovery_repo.save({
        "order_id": "order_clear_test",
        "exchange_order_id": "ex_order_clear_test",
        "symbol": "ETH/USDT:USDT",
        "error": "交易所撤销订单失败",
        "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
    })

    await pending_recovery_repo.close()

    # 执行：运行脚本
    result = subprocess.run(
        [sys.executable, "scripts/manage_execution_recovery.py", "clear-pending", "--order-id", "order_clear_test"],
        capture_output=True,
        text=True,
    )

    # 验证：脚本返回 0
    assert result.returncode == 0
    assert "order_clear_test" in result.stdout

    # 验证：SQLite 中记录被删除
    pending_recovery_repo = PendingRecoveryRepository(db_path=test_db_path)
    await pending_recovery_repo.initialize()
    record = await pending_recovery_repo.get("order_clear_test")
    await pending_recovery_repo.close()

    assert record is None

    # 清理
    if os.path.exists(test_db_path):
        os.remove(test_db_path)


if __name__ == "__main__":
    # 可直接运行：python tests/unit/test_p0_7_pending_recovery_persistence.py
    import asyncio

    async def run_tests():
        print("Running test_orchestrator_persists_pending_recovery_to_repository...")
        await test_orchestrator_persists_pending_recovery_to_repository()
        print("✅ test_orchestrator_persists_pending_recovery_to_repository passed\n")

        print("Running test_clear_pending_recovery_deletes_from_repository...")
        await test_clear_pending_recovery_deletes_from_repository()
        print("✅ test_clear_pending_recovery_deletes_from_repository passed\n")

        print("Running test_script_list_pending_reads_real_records...")
        await test_script_list_pending_reads_real_records()
        print("✅ test_script_list_pending_reads_real_records passed\n")

        print("Running test_script_clear_pending_deletes_real_records...")
        await test_script_clear_pending_deletes_real_records()
        print("✅ test_script_clear_pending_deletes_real_records passed\n")

        print("All tests passed! ✅")

    asyncio.run(run_tests())
