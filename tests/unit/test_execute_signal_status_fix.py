"""
P1-1: execute_signal() 状态尾部覆盖修复测试

测试目标：
1. PARTIALLY_FILLED 分支必须 return，不能落到通用尾部
2. CANCELED 分支必须 return，不能落到通用尾部
3. REJECTED 分支必须 return，不能落到通用尾部

验收标准：
- mock place_order() 返回 PARTIALLY_FILLED/CANCELED/REJECTED
- 断言返回的 intent.status != COMPLETED
- failed_reason / 状态语义合理
"""
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.domain.models import (
    SignalResult,
    Order,
    OrderType,
    OrderRole,
    OrderStatus,
    Direction,
    OrderStrategy,
    OrderPlacementResult,
)
from src.domain.execution_intent import ExecutionIntent, ExecutionIntentStatus
from src.application.execution_orchestrator import ExecutionOrchestrator
from src.application.capital_protection import CapitalProtectionManager
from src.application.order_lifecycle_service import OrderLifecycleService
from src.infrastructure.exchange_gateway import ExchangeGateway


@pytest.mark.asyncio
async def test_partially_filled_not_overwritten():
    """
    P1-1 测试：PARTIALLY_FILLED 分支不会被尾部覆盖

    场景：
    1. mock place_order() 返回 PARTIALLY_FILLED
    2. 断言 intent.status == SUBMITTED（不是 COMPLETED）
    """
    # 准备：创建 orchestrator
    capital_protection = MagicMock(spec=CapitalProtectionManager)
    capital_protection.pre_order_check = AsyncMock(return_value=MagicMock(allowed=True))

    order_lifecycle = MagicMock(spec=OrderLifecycleService)
    order_lifecycle.create_order = AsyncMock(return_value=Order(
        id="order_test_001",
        signal_id="sig_test_001",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal("0.1"),
        created_at=int(datetime.now(timezone.utc).timestamp() * 1000),
        updated_at=int(datetime.now(timezone.utc).timestamp() * 1000),
    ))
    order_lifecycle.confirm_order = AsyncMock()
    order_lifecycle.update_order_partially_filled = AsyncMock()

    gateway = MagicMock(spec=ExchangeGateway)
    gateway.place_order = AsyncMock(return_value=OrderPlacementResult(
        order_id="order_test_001",
        exchange_order_id="ex_order_001",
        symbol="BTC/USDT:USDT",
        order_type=OrderType.MARKET,
        direction=Direction.LONG,
        side="buy",
        amount=Decimal("0.1"),
        price=Decimal("50000"),
        status=OrderStatus.PARTIALLY_FILLED,
    ))

    orchestrator = ExecutionOrchestrator(
        capital_protection=capital_protection,
        order_lifecycle=order_lifecycle,
        gateway=gateway,
    )

    # 准备：创建测试信号
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
        tp_levels=1,
        tp_ratios=[Decimal("1.0")],
        tp_targets=[Decimal("1.5")],
        initial_stop_loss_rr=Decimal("-1.0"),
    )

    # 执行：execute_signal
    intent = await orchestrator.execute_signal(signal, strategy)

    # 验证：intent.status == SUBMITTED（不是 COMPLETED）
    assert intent.status == ExecutionIntentStatus.SUBMITTED
    assert intent.order_id == "order_test_001"
    assert intent.exchange_order_id == "ex_order_001"


@pytest.mark.asyncio
async def test_canceled_not_overwritten():
    """
    P1-1 测试：CANCELED 分支不会被尾部覆盖

    场景：
    1. mock place_order() 返回 CANCELED
    2. 断言 intent.status == FAILED（不是 COMPLETED）
    3. failed_reason 包含"交易所取消订单"
    """
    # 准备：创建 orchestrator
    capital_protection = MagicMock(spec=CapitalProtectionManager)
    capital_protection.pre_order_check = AsyncMock(return_value=MagicMock(allowed=True))

    order_lifecycle = MagicMock(spec=OrderLifecycleService)
    order_lifecycle.create_order = AsyncMock(return_value=Order(
        id="order_test_002",
        signal_id="sig_test_002",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal("0.1"),
        created_at=int(datetime.now(timezone.utc).timestamp() * 1000),
        updated_at=int(datetime.now(timezone.utc).timestamp() * 1000),
    ))
    order_lifecycle.cancel_order = AsyncMock()

    gateway = MagicMock(spec=ExchangeGateway)
    gateway.place_order = AsyncMock(return_value=OrderPlacementResult(
        order_id="order_test_002",
        exchange_order_id="ex_order_002",
        symbol="BTC/USDT:USDT",
        order_type=OrderType.MARKET,
        direction=Direction.LONG,
        side="buy",
        amount=Decimal("0.1"),
        status=OrderStatus.CANCELED,
    ))

    orchestrator = ExecutionOrchestrator(
        capital_protection=capital_protection,
        order_lifecycle=order_lifecycle,
        gateway=gateway,
    )

    # 准备：创建测试信号
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
        tp_levels=1,
        tp_ratios=[Decimal("1.0")],
        tp_targets=[Decimal("1.5")],
        initial_stop_loss_rr=Decimal("-1.0"),
    )

    # 执行：execute_signal
    intent = await orchestrator.execute_signal(signal, strategy)

    # 验证：intent.status == FAILED（不是 COMPLETED）
    assert intent.status == ExecutionIntentStatus.FAILED
    assert intent.order_id == "order_test_002"
    assert intent.failed_reason == "交易所取消订单"


@pytest.mark.asyncio
async def test_rejected_not_overwritten():
    """
    P1-1 测试：REJECTED 分支不会被尾部覆盖

    场景：
    1. mock place_order() 返回 REJECTED
    2. 断言 intent.status == FAILED（不是 COMPLETED）
    3. failed_reason 包含"交易所拒绝订单"
    """
    # 准备：创建 orchestrator
    capital_protection = MagicMock(spec=CapitalProtectionManager)
    capital_protection.pre_order_check = AsyncMock(return_value=MagicMock(allowed=True))

    order_lifecycle = MagicMock(spec=OrderLifecycleService)
    order_lifecycle.create_order = AsyncMock(return_value=Order(
        id="order_test_003",
        signal_id="sig_test_003",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal("0.1"),
        created_at=int(datetime.now(timezone.utc).timestamp() * 1000),
        updated_at=int(datetime.now(timezone.utc).timestamp() * 1000),
    ))

    gateway = MagicMock(spec=ExchangeGateway)
    gateway.place_order = AsyncMock(return_value=OrderPlacementResult(
        order_id="order_test_003",
        exchange_order_id="ex_order_003",
        symbol="BTC/USDT:USDT",
        order_type=OrderType.MARKET,
        direction=Direction.LONG,
        side="buy",
        amount=Decimal("0.1"),
        status=OrderStatus.REJECTED,
    ))

    orchestrator = ExecutionOrchestrator(
        capital_protection=capital_protection,
        order_lifecycle=order_lifecycle,
        gateway=gateway,
    )

    # 准备：创建测试信号
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
        tp_levels=1,
        tp_ratios=[Decimal("1.0")],
        tp_targets=[Decimal("1.5")],
        initial_stop_loss_rr=Decimal("-1.0"),
    )

    # 执行：execute_signal
    intent = await orchestrator.execute_signal(signal, strategy)

    # 验证：intent.status == FAILED（不是 COMPLETED）
    assert intent.status == ExecutionIntentStatus.FAILED
    assert intent.order_id == "order_test_003"
    assert intent.failed_reason == "交易所拒绝订单"


if __name__ == "__main__":
    # 可直接运行：python tests/unit/test_execute_signal_status_fix.py
    import asyncio

    async def run_tests():
        print("Running test_partially_filled_not_overwritten...")
        await test_partially_filled_not_overwritten()
        print("✅ test_partially_filled_not_overwritten passed\n")

        print("Running test_canceled_not_overwritten...")
        await test_canceled_not_overwritten()
        print("✅ test_canceled_not_overwritten passed\n")

        print("Running test_rejected_not_overwritten...")
        await test_rejected_not_overwritten()
        print("✅ test_rejected_not_overwritten passed\n")

        print("All tests passed! ✅")

    asyncio.run(run_tests())