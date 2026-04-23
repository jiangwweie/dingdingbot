"""
P1-6: partial-fill 增量补挂时，保证"单一 SL 覆盖全仓"且不生成重复 SL

测试目标：
1. 第一次 partial fill：生成 TP + 1 张 SL（qty=filled_qty_total）
2. 第二次 partial fill（filled_qty_total 增加）：新增 TP（delta 部分），SL 仍然只有 1 张，且 qty 更新为新的 filled_qty_total
3. 断言：有效 SL 数量始终为 1

验收标准：
- 测试可跑通（pytest 可选运行）
- 覆盖 P1-6 的关键语义
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
    Position,
)
from src.domain.execution_intent import ExecutionIntent, ExecutionIntentStatus
from src.application.execution_orchestrator import ExecutionOrchestrator
from src.application.capital_protection import CapitalProtectionManager
from src.application.order_lifecycle_service import OrderLifecycleService
from src.infrastructure.exchange_gateway import ExchangeGateway
from src.infrastructure.repository_ports import (
    ExecutionIntentRepositoryPort,
    OrderRepositoryPort,
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


class FakeExecutionIntentRepository(ExecutionIntentRepositoryPort):
    """最小 fake intent repo"""

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
async def test_single_sl_on_first_partial_fill():
    """
    P1-6 测试：第一次 partial fill 生成单一 SL

    场景：
    1. ENTRY 部分成交（filled_qty=0.05）
    2. 生成 TP + 1 张 SL（qty=0.05）
    3. 断言：有效 SL 数量为 1
    """
    # 准备：创建 fake repos
    fake_order_repo = FakeOrderRepository()
    fake_intent_repo = FakeExecutionIntentRepository()

    # 准备：创建 orchestrator（注入 fake repos）
    capital_protection = MagicMock(spec=CapitalProtectionManager)
    gateway = MagicMock(spec=ExchangeGateway)

    order_lifecycle = OrderLifecycleService(repository=fake_order_repo)

    orchestrator = ExecutionOrchestrator(
        capital_protection=capital_protection,
        order_lifecycle=order_lifecycle,
        gateway=gateway,
        intent_repository=fake_intent_repo,
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
    await fake_intent_repo.save(intent)

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
        filled_qty=Decimal("0.05"),  # 第一次部分成交
        average_exec_price=Decimal("50000"),
        status=OrderStatus.PARTIALLY_FILLED,
        created_at=current_time,
        updated_at=current_time,
    )
    await fake_order_repo.save(entry_order)

    # 准备：mock gateway.place_order
    gateway.place_order = AsyncMock()
    gateway.place_order.return_value = MagicMock(
        is_success=True,
        exchange_order_id="ex_order_sl_001",
        status=OrderStatus.OPEN,
    )

    # 执行：触发 partial-fill 回调
    await orchestrator._handle_entry_partially_filled(entry_order)

    # 验证：有效 SL 数量为 1
    all_orders = await fake_order_repo.get_orders_by_signal("sig_test_001")
    sl_orders = [
        o for o in all_orders
        if o.order_role == OrderRole.SL
        and o.status in {
            OrderStatus.SUBMITTED,
            OrderStatus.OPEN,
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
        }
    ]
    assert len(sl_orders) == 1
    assert sl_orders[0].requested_qty == Decimal("0.05")  # 覆盖第一次成交量


@pytest.mark.asyncio
async def test_single_sl_on_second_partial_fill():
    """
    P1-6 测试：第二次 partial fill 调整 SL 数量，不创建新 SL

    场景：
    1. 第一次 partial fill（filled_qty=0.05）：生成 TP + 1 张 SL（qty=0.05）
    2. 第二次 partial fill（filled_qty=0.08）：新增 TP（delta=0.03），SL 数量调整为 0.08
    3. 断言：有效 SL 数量仍为 1，且 qty=0.08
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

    # 准备：创建 ExecutionIntent
    intent = ExecutionIntent(
        id="intent_test_002",
        signal_id="sig_test_002",
        signal=signal,
        status=ExecutionIntentStatus.SUBMITTED,
        strategy=strategy,
        order_id="order_test_002",
    )
    await fake_intent_repo.save(intent)

    # 准备：创建 ENTRY 订单（第二次部分成交）
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    entry_order = Order(
        id="order_test_002",
        signal_id="sig_test_002",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal("0.1"),
        filled_qty=Decimal("0.08"),  # 第二次部分成交（累计）
        average_exec_price=Decimal("50000"),
        status=OrderStatus.PARTIALLY_FILLED,
        created_at=current_time,
        updated_at=current_time,
    )
    await fake_order_repo.save(entry_order)

    # 准备：创建已有的 SL 订单（第一次部分成交时创建）
    existing_sl = Order(
        id="order_sl_002",
        signal_id="sig_test_002",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        requested_qty=Decimal("0.05"),  # 第一次成交量
        parent_order_id="order_test_002",
        status=OrderStatus.OPEN,
        created_at=current_time,
        updated_at=current_time,
    )
    await fake_order_repo.save(existing_sl)

    # 准备：创建已有的 TP1 订单（第一次部分成交时创建）
    existing_tp1 = Order(
        id="order_tp1_002",
        signal_id="sig_test_002",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        requested_qty=Decimal("0.025"),  # 第一次成交量的一半
        parent_order_id="order_test_002",
        status=OrderStatus.OPEN,
        created_at=current_time,
        updated_at=current_time,
    )
    await fake_order_repo.save(existing_tp1)

    # 准备：mock gateway.place_order
    gateway.place_order = AsyncMock()
    gateway.place_order.return_value = MagicMock(
        is_success=True,
        exchange_order_id="ex_order_tp2_002",
        status=OrderStatus.OPEN,
    )

    # 执行：触发第二次 partial-fill 回调
    await orchestrator._handle_entry_partially_filled(entry_order)

    # 验证：有效 SL 数量仍为 1
    all_orders = await fake_order_repo.get_orders_by_signal("sig_test_002")
    sl_orders = [
        o for o in all_orders
        if o.order_role == OrderRole.SL
        and o.status in {
            OrderStatus.SUBMITTED,
            OrderStatus.OPEN,
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
        }
    ]
    assert len(sl_orders) == 1

    # 验证：SL 数量已调整为 0.08（覆盖全仓）
    assert sl_orders[0].requested_qty == Decimal("0.08")

    # 验证：SL 订单 ID 未变（仍是第一次创建的 SL）
    assert sl_orders[0].id == "order_sl_002"


@pytest.mark.asyncio
async def test_multiple_sl_error_handling():
    """
    P1-6 测试：检测到多张有效 SL 时，报错并返回

    场景：
    1. ENTRY 部分成交
    2. 已存在 2 张有效 SL（脏数据）
    3. 断言：不生成新订单，直接返回
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

    # 准备：创建 ExecutionIntent
    intent = ExecutionIntent(
        id="intent_test_003",
        signal_id="sig_test_003",
        signal=signal,
        status=ExecutionIntentStatus.SUBMITTED,
        strategy=strategy,
        order_id="order_test_003",
    )
    await fake_intent_repo.save(intent)

    # 准备：创建 ENTRY 订单
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    entry_order = Order(
        id="order_test_003",
        signal_id="sig_test_003",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal("0.1"),
        filled_qty=Decimal("0.05"),
        average_exec_price=Decimal("50000"),
        status=OrderStatus.PARTIALLY_FILLED,
        created_at=current_time,
        updated_at=current_time,
    )
    await fake_order_repo.save(entry_order)

    # 准备：创建 2 张有效 SL（脏数据）
    sl1 = Order(
        id="order_sl_003_1",
        signal_id="sig_test_003",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        requested_qty=Decimal("0.03"),
        parent_order_id="order_test_003",
        status=OrderStatus.OPEN,
        created_at=current_time,
        updated_at=current_time,
    )
    await fake_order_repo.save(sl1)

    sl2 = Order(
        id="order_sl_003_2",
        signal_id="sig_test_003",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        requested_qty=Decimal("0.02"),
        parent_order_id="order_test_003",
        status=OrderStatus.OPEN,
        created_at=current_time,
        updated_at=current_time,
    )
    await fake_order_repo.save(sl2)

    # 准备：mock gateway.place_order
    gateway.place_order = AsyncMock()

    # 执行：触发 partial-fill 回调
    await orchestrator._handle_entry_partially_filled(entry_order)

    # 验证：没有调用 place_order（直接返回）
    gateway.place_order.assert_not_called()


if __name__ == "__main__":
    # 可直接运行：python tests/unit/test_partial_fill_single_sl.py
    import asyncio

    async def run_tests():
        print("Running test_single_sl_on_first_partial_fill...")
        await test_single_sl_on_first_partial_fill()
        print("✅ test_single_sl_on_first_partial_fill passed\n")

        print("Running test_single_sl_on_second_partial_fill...")
        await test_single_sl_on_second_partial_fill()
        print("✅ test_single_sl_on_second_partial_fill passed\n")

        print("Running test_multiple_sl_error_handling...")
        await test_multiple_sl_error_handling()
        print("✅ test_multiple_sl_error_handling passed\n")

        print("All tests passed! ✅")

    asyncio.run(run_tests())
