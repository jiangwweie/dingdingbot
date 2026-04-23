"""
Execution Recovery Task Integration 测试（Mock 版）

测试目标：
1. orchestrator 在 replace_sl_failed 时会调用 create_task()
2. create_task 参数正确

注意：不使用真实 PG，使用 AsyncMock 的 execution_recovery_repository
"""
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock

from src.domain.models import (
    Order,
    OrderType,
    OrderRole,
    OrderStatus,
    Direction,
    SignalResult,
    OrderStrategy,
)
from src.domain.execution_intent import ExecutionIntent, ExecutionIntentStatus
from src.application.execution_orchestrator import ExecutionOrchestrator
from src.application.capital_protection import CapitalProtectionManager
from src.application.order_lifecycle_service import OrderLifecycleService
from src.infrastructure.exchange_gateway import ExchangeGateway


def create_test_intent(intent_id: str, signal_id: str, symbol: str) -> ExecutionIntent:
    """创建测试用的 ExecutionIntent"""
    # 创建策略快照
    strategy = OrderStrategy(
        id="strategy_001",
        name="Test Strategy",
        tp_targets=[Decimal("1.5")],
        initial_stop_loss_rr=Decimal("-1.0"),
    )

    # 创建 SignalResult
    signal = SignalResult(
        symbol=symbol,
        timeframe="15m",
        direction=Direction.LONG,
        entry_price=Decimal("50000"),
        suggested_stop_loss=Decimal("49000"),
        suggested_position_size=Decimal("0.1"),
        current_leverage=10,
        tags=[],
        risk_reward_info="Test RR",
        strategy_name="Test Strategy",
        score=0.8,
    )

    # 创建 ExecutionIntent
    intent = ExecutionIntent(
        id=intent_id,
        signal_id=signal_id,
        signal=signal,
        status=ExecutionIntentStatus.PROTECTING,
        strategy=strategy,
    )

    return intent


@pytest.mark.asyncio
async def test_orchestrator_creates_pg_recovery_task():
    """
    测试 orchestrator 在 replace_sl_failed 时会调用 create_task()

    场景：
    1. ENTRY 部分成交，已有 SL 订单
    2. 撤销交易所旧 SL 失败
    3. orchestrator 应调用 create_task()
    断言：
    - create_task() 被调用一次
    - 参数正确
    """
    # 准备：创建 mock 对象
    capital_protection = MagicMock(spec=CapitalProtectionManager)
    order_lifecycle = MagicMock(spec=OrderLifecycleService)
    gateway = MagicMock(spec=ExchangeGateway)

    # Mock cancel_order 抛出异常
    gateway.cancel_order = AsyncMock(side_effect=Exception("交易所撤销失败"))

    # 准备：创建测试订单
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    entry_order = Order(
        id="entry_001",
        signal_id="signal_001",
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

    existing_sl = Order(
        id="sl_001",
        signal_id="signal_001",
        symbol="BTC/USDT:USDT",
        direction=Direction.SHORT,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        requested_qty=Decimal("0.05"),
        status=OrderStatus.OPEN,
        exchange_order_id="ex_sl_001",
        created_at=current_time,
        updated_at=current_time,
    )

    # 准备：mock order_lifecycle._repository
    mock_order_repo = MagicMock()
    # 返回 entry_order 和 existing_sl（existing_sl 的 parent_order_id 必须是 entry_order.id）
    existing_sl.parent_order_id = entry_order.id  # 关联到 entry_order
    mock_order_repo.get_orders_by_signal = AsyncMock(return_value=[entry_order, existing_sl])
    mock_order_repo.save = AsyncMock(return_value=None)  # Mock save 方法
    order_lifecycle._repository = mock_order_repo

    # 准备：创建 ExecutionIntent
    intent = create_test_intent("intent_001", "signal_001", "BTC/USDT:USDT")
    intent.order_id = "entry_001"  # 关联到 entry_order

    # 准备：Mock execution_recovery_repository
    mock_recovery_repo = AsyncMock()

    # 准备：创建 orchestrator 并注入 intent
    orchestrator = ExecutionOrchestrator(
        capital_protection=capital_protection,
        order_lifecycle=order_lifecycle,
        gateway=gateway,
        execution_recovery_repository=mock_recovery_repo,
    )

    # 手动注入 intent 到内存缓存
    orchestrator._intents["intent_001"] = intent

    # 执行：触发 _handle_entry_partially_filled
    await orchestrator._handle_entry_partially_filled(entry_order)

    # 验证：create_task 被调用一次
    mock_recovery_repo.create_task.assert_called_once()

    # 验证：create_task 参数
    call_args = mock_recovery_repo.create_task.call_args
    assert call_args is not None

    # 提取参数
    kwargs = call_args.kwargs
    assert kwargs["recovery_type"] == "replace_sl_failed"
    assert kwargs["intent_id"] == "intent_001"
    assert kwargs["related_order_id"] == "sl_001"
    assert kwargs["related_exchange_order_id"] == "ex_sl_001"
    assert kwargs["symbol"] == "BTC/USDT:USDT"
    assert kwargs["error_message"] == "交易所撤销失败"

    # 验证 context_payload 包含必要字段
    context = kwargs["context_payload"]
    assert "entry_order_id" in context
    assert "filled_qty_total" in context
    assert "protected_qty_total" in context
    assert "delta_qty" in context
    assert context["entry_order_id"] == "entry_001"
    assert context["existing_sl_order_id"] == "sl_001"
    assert context["existing_sl_exchange_order_id"] == "ex_sl_001"


@pytest.mark.asyncio
async def test_orchestrator_does_not_create_task_if_no_existing_sl():
    """
    测试 orchestrator 在没有已有 SL 时不会调用 create_task()

    场景：
    1. ENTRY 部分成交，没有已有 SL 订单
    2. 不会触发撤销失败
    断言：
    - create_task() 没有被调用
    """
    # 准备：创建 mock 对象
    capital_protection = MagicMock(spec=CapitalProtectionManager)
    order_lifecycle = MagicMock(spec=OrderLifecycleService)
    gateway = MagicMock(spec=ExchangeGateway)

    # 准备：创建测试订单
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    entry_order = Order(
        id="entry_001",
        signal_id="signal_001",
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

    # 准备：mock order_lifecycle._repository（没有 SL 订单）
    mock_order_repo = MagicMock()
    mock_order_repo.get_orders_by_signal = AsyncMock(return_value=[entry_order])
    order_lifecycle._repository = mock_order_repo

    # 准备：创建 ExecutionIntent
    intent = create_test_intent("intent_001", "signal_001", "BTC/USDT:USDT")
    intent.order_id = "entry_001"  # 关联到 entry_order

    # 准备：Mock execution_recovery_repository
    mock_recovery_repo = AsyncMock()

    # 准备：创建 orchestrator 并注入 intent
    orchestrator = ExecutionOrchestrator(
        capital_protection=capital_protection,
        order_lifecycle=order_lifecycle,
        gateway=gateway,
        execution_recovery_repository=mock_recovery_repo,
    )

    # 手动注入 intent 到内存缓存
    orchestrator._intents["intent_001"] = intent

    # 执行：触发 _handle_entry_partially_filled
    await orchestrator._handle_entry_partially_filled(entry_order)

    # 验证：create_task 没有被调用
    mock_recovery_repo.create_task.assert_not_called()


@pytest.mark.asyncio
async def test_orchestrator_does_not_create_task_if_cancel_succeeds():
    """
    测试 orchestrator 在撤销成功时不会调用 create_task()

    场景：
    1. ENTRY 部分成交，已有 SL 订单
    2. 撤销交易所旧 SL 成功
    断言：
    - create_task() 没有被调用
    """
    # 准备：创建 mock 对象
    capital_protection = MagicMock(spec=CapitalProtectionManager)
    order_lifecycle = MagicMock(spec=OrderLifecycleService)
    gateway = MagicMock(spec=ExchangeGateway)

    # Mock cancel_order 成功
    gateway.cancel_order = AsyncMock(return_value=None)

    # 准备：创建测试订单
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    entry_order = Order(
        id="entry_001",
        signal_id="signal_001",
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

    existing_sl = Order(
        id="sl_001",
        signal_id="signal_001",
        symbol="BTC/USDT:USDT",
        direction=Direction.SHORT,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        requested_qty=Decimal("0.05"),
        status=OrderStatus.OPEN,
        exchange_order_id="ex_sl_001",
        created_at=current_time,
        updated_at=current_time,
    )

    # 准备：mock order_lifecycle._repository
    mock_order_repo = MagicMock()
    mock_order_repo.get_orders_by_signal = AsyncMock(return_value=[entry_order, existing_sl])
    order_lifecycle._repository = mock_order_repo

    # Mock cancel_order
    order_lifecycle.cancel_order = AsyncMock(return_value=None)

    # 准备：创建 ExecutionIntent
    intent = create_test_intent("intent_001", "signal_001", "BTC/USDT:USDT")
    intent.order_id = "entry_001"  # 关联到 entry_order

    # 准备：Mock execution_recovery_repository
    mock_recovery_repo = AsyncMock()

    # 准备：创建 orchestrator 并注入 intent
    orchestrator = ExecutionOrchestrator(
        capital_protection=capital_protection,
        order_lifecycle=order_lifecycle,
        gateway=gateway,
        execution_recovery_repository=mock_recovery_repo,
    )

    # 手动注入 intent 到内存缓存
    orchestrator._intents["intent_001"] = intent

    # 执行：触发 _handle_entry_partially_filled
    await orchestrator._handle_entry_partially_filled(entry_order)

    # 验证：create_task 没有被调用（因为 cancel_order 成功）
    mock_recovery_repo.create_task.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])