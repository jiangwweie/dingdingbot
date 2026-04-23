"""
P1-4: PG 为主真源时内存为空也能跑的单测

测试目标：
1. repo-first 语义：清空 _intents 后，通过 repo 仍能找到 intent 并推进状态
2. 策略不退化：intent 无 strategy 时不生成保护单

验收标准：
- 测试可跑通（pytest 可选运行）
- 覆盖 P1-2/P1-3 的关键语义
"""
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List
from unittest.mock import AsyncMock, MagicMock

from src.domain.models import (
    SignalResult,
    Order,
    OrderType,
    OrderRole,
    OrderStatus,
    Direction,
    OrderStrategy,
)
from src.domain.execution_intent import ExecutionIntent, ExecutionIntentStatus
from src.application.execution_orchestrator import ExecutionOrchestrator
from src.application.capital_protection import CapitalProtectionManager
from src.application.order_lifecycle_service import OrderLifecycleService
from src.infrastructure.exchange_gateway import ExchangeGateway
from src.infrastructure.repository_ports import ExecutionIntentRepositoryPort


class FakeExecutionIntentRepository(ExecutionIntentRepositoryPort):
    """最小 fake repo（实现 get_by_order_id/save）"""

    def __init__(self):
        self._storage: dict = {}

    async def save(self, intent: ExecutionIntent) -> None:
        """保存执行意图"""
        self._storage[intent.id] = intent
        if intent.order_id:
            self._storage[f"order:{intent.order_id}"] = intent

    async def get(self, intent_id: str) -> Optional[ExecutionIntent]:
        """按 ID 获取"""
        return self._storage.get(intent_id)

    async def get_by_signal_id(self, signal_id: str) -> Optional[ExecutionIntent]:
        """按信号 ID 获取"""
        for intent in self._storage.values():
            if isinstance(intent, ExecutionIntent) and intent.signal_id == signal_id:
                return intent
        return None

    async def get_by_order_id(self, order_id: str) -> Optional[ExecutionIntent]:
        """按订单 ID 获取"""
        return self._storage.get(f"order:{order_id}")

    async def list(self, status: Optional[ExecutionIntentStatus] = None) -> List[ExecutionIntent]:
        """列出执行意图"""
        intents = [i for i in self._storage.values() if isinstance(i, ExecutionIntent)]
        if status:
            intents = [i for i in intents if i.status == status]
        return intents


@pytest.mark.asyncio
async def test_repo_first_semantics():
    """
    P1-2 测试：repo-first 语义

    场景：
    1. 清空 orchestrator._intents
    2. 触发 partial-fill 回调
    3. 通过 repo 仍能找到 intent 并推进状态
    """
    # 准备：创建 fake repo
    fake_repo = FakeExecutionIntentRepository()

    # 准备：创建 orchestrator（注入 fake repo）
    capital_protection = MagicMock(spec=CapitalProtectionManager)
    order_lifecycle = MagicMock(spec=OrderLifecycleService)
    gateway = MagicMock(spec=ExchangeGateway)

    orchestrator = ExecutionOrchestrator(
        capital_protection=capital_protection,
        order_lifecycle=order_lifecycle,
        gateway=gateway,
        intent_repository=fake_repo,
    )

    # 准备：创建测试数据
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
        strategy_name="test",
        score=0.8,
    )

    strategy = OrderStrategy(
        id="test_strategy",
        name="Test Strategy",
        tp_levels=2,
        tp_ratios=[Decimal("0.5"), Decimal("0.5")],
        tp_targets=[Decimal("1.0"), Decimal("2.0")],
        initial_stop_loss_rr=Decimal("-1.0"),
    )

    # 准备：创建 ExecutionIntent 并保存到 repo
    intent = ExecutionIntent(
        id="intent_test_001",
        signal_id="sig_test_001",
        signal=signal,
        status=ExecutionIntentStatus.SUBMITTED,
        strategy=strategy,
        order_id="order_test_001",
    )
    await fake_repo.save(intent)

    # 关键步骤：清空 orchestrator._intents（模拟内存丢失）
    orchestrator._intents.clear()

    # 准备：创建 ENTRY 订单（部分成交）
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    entry_order = Order(
        id="order_test_001",
        signal_id="sig_test_001",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal("0.1"),
        filled_qty=Decimal("0.05"),  # 部分成交
        average_exec_price=Decimal("50000"),
        status=OrderStatus.PARTIALLY_FILLED,
        created_at=current_time,
        updated_at=current_time,
    )

    # 准备：mock order_lifecycle 依赖
    order_lifecycle._repository = MagicMock()
    order_lifecycle._repository.get_orders_by_signal = AsyncMock(return_value=[])

    # 执行：触发 partial-fill 回调
    await orchestrator._handle_entry_partially_filled(entry_order)

    # 验证：intent 状态已推进（通过 repo-first 找到 intent）
    updated_intent = await fake_repo.get("intent_test_001")
    assert updated_intent is not None
    assert updated_intent.status == ExecutionIntentStatus.PARTIALLY_PROTECTED


@pytest.mark.asyncio
async def test_strategy_no_fallback():
    """
    P1-3 测试：策略不退化

    场景：
    1. intent 无 strategy
    2. 触发 partial-fill 回调
    3. 不生成保护单（warn + return）
    """
    # 准备：创建 fake repo
    fake_repo = FakeExecutionIntentRepository()

    # 准备：创建 orchestrator（注入 fake repo）
    capital_protection = MagicMock(spec=CapitalProtectionManager)
    order_lifecycle = MagicMock(spec=OrderLifecycleService)
    gateway = MagicMock(spec=ExchangeGateway)

    orchestrator = ExecutionOrchestrator(
        capital_protection=capital_protection,
        order_lifecycle=order_lifecycle,
        gateway=gateway,
        intent_repository=fake_repo,
    )

    # 准备：创建测试数据
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
        strategy_name="test",
        score=0.8,
    )

    # 关键：intent 无 strategy
    intent = ExecutionIntent(
        id="intent_test_002",
        signal_id="sig_test_002",
        signal=signal,
        status=ExecutionIntentStatus.SUBMITTED,
        strategy=None,  # 无策略
        order_id="order_test_002",
    )
    await fake_repo.save(intent)

    # 准备：创建 ENTRY 订单（部分成交）
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    entry_order = Order(
        id="order_test_002",
        signal_id="sig_test_002",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal("0.1"),
        filled_qty=Decimal("0.05"),  # 部分成交
        average_exec_price=Decimal("50000"),
        status=OrderStatus.PARTIALLY_FILLED,
        created_at=current_time,
        updated_at=current_time,
    )

    # 准备：mock order_lifecycle 依赖
    order_lifecycle._repository = MagicMock()
    order_lifecycle._repository.get_orders_by_signal = AsyncMock(return_value=[])

    # 执行：触发 partial-fill 回调
    await orchestrator._handle_entry_partially_filled(entry_order)

    # 验证：intent 状态未推进（未生成保护单）
    updated_intent = await fake_repo.get("intent_test_002")
    assert updated_intent is not None
    assert updated_intent.status == ExecutionIntentStatus.SUBMITTED  # 状态未变化


@pytest.mark.asyncio
async def test_strategy_with_valid_strategy():
    """
    P1-3 测试：有策略时正常生成保护单

    场景：
    1. intent 有 strategy
    2. 触发 partial-fill 回调
    3. 生成 TP1/TP2/SL 符合 strategy
    """
    # 准备：创建 fake repo
    fake_repo = FakeExecutionIntentRepository()

    # 准备：创建 orchestrator（注入 fake repo）
    capital_protection = MagicMock(spec=CapitalProtectionManager)
    order_lifecycle = MagicMock(spec=OrderLifecycleService)
    gateway = MagicMock(spec=ExchangeGateway)

    orchestrator = ExecutionOrchestrator(
        capital_protection=capital_protection,
        order_lifecycle=order_lifecycle,
        gateway=gateway,
        intent_repository=fake_repo,
    )

    # 准备：创建测试数据
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
        strategy_name="test",
        score=0.8,
    )

    strategy = OrderStrategy(
        id="test_strategy",
        name="Test Strategy",
        tp_levels=2,
        tp_ratios=[Decimal("0.5"), Decimal("0.5")],
        tp_targets=[Decimal("1.0"), Decimal("2.0")],
        initial_stop_loss_rr=Decimal("-1.0"),
    )

    # 关键：intent 有 strategy
    intent = ExecutionIntent(
        id="intent_test_003",
        signal_id="sig_test_003",
        signal=signal,
        status=ExecutionIntentStatus.SUBMITTED,
        strategy=strategy,
        order_id="order_test_003",
    )
    await fake_repo.save(intent)

    # 准备：创建 ENTRY 订单（部分成交）
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    entry_order = Order(
        id="order_test_003",
        signal_id="sig_test_003",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal("0.1"),
        filled_qty=Decimal("0.05"),  # 部分成交
        average_exec_price=Decimal("50000"),
        status=OrderStatus.PARTIALLY_FILLED,
        created_at=current_time,
        updated_at=current_time,
    )

    # 准备：mock order_lifecycle 依赖
    order_lifecycle._repository = MagicMock()
    order_lifecycle._repository.get_orders_by_signal = AsyncMock(return_value=[])
    order_lifecycle._repository.save = AsyncMock()
    order_lifecycle._get_or_create_state_machine = MagicMock()
    order_lifecycle.submit_order = AsyncMock()
    order_lifecycle.confirm_order = AsyncMock()

    # 准备：mock gateway
    gateway.place_order = AsyncMock()
    gateway.place_order.return_value = MagicMock(
        is_success=True,
        exchange_order_id="ex_order_001",
        status=OrderStatus.OPEN,
    )

    # 执行：触发 partial-fill 回调
    await orchestrator._handle_entry_partially_filled(entry_order)

    # 验证：intent 状态已推进
    updated_intent = await fake_repo.get("intent_test_003")
    assert updated_intent is not None
    assert updated_intent.status == ExecutionIntentStatus.PARTIALLY_PROTECTED


if __name__ == "__main__":
    # 可直接运行：python tests/unit/test_execution_intent_repo_first.py
    import asyncio

    async def run_tests():
        print("Running test_repo_first_semantics...")
        await test_repo_first_semantics()
        print("✅ test_repo_first_semantics passed\n")

        print("Running test_strategy_no_fallback...")
        await test_strategy_no_fallback()
        print("✅ test_strategy_no_fallback passed\n")

        print("Running test_strategy_with_valid_strategy...")
        await test_strategy_with_valid_strategy()
        print("✅ test_strategy_with_valid_strategy passed\n")

        print("All tests passed! ✅")

    asyncio.run(run_tests())
