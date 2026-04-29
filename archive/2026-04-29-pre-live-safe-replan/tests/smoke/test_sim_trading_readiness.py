"""
模拟盘准入冒烟验证

验证目标：
- 确认当前执行恢复主链已具备进入模拟盘的最小条件
- 覆盖 4 个关键场景：正常链路、异常链路、启动恢复、熔断拦截

验证标准：
- 可运行：正常链路能跑通
- 可恢复：异常链路能安全停住并创建恢复任务
- 可拦截：熔断生效后拒绝新信号
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
)
from src.domain.execution_intent import ExecutionIntent, ExecutionIntentStatus
from src.application.execution_orchestrator import ExecutionOrchestrator
from src.application.capital_protection import CapitalProtectionManager
from src.application.order_lifecycle_service import OrderLifecycleService
from src.application.startup_reconciliation_service import StartupReconciliationService
from src.infrastructure.exchange_gateway import ExchangeGateway


# ============================================
# 辅助函数
# ============================================

def create_test_signal(symbol: str = "BTC/USDT:USDT") -> SignalResult:
    """创建测试信号"""
    return SignalResult(
        symbol=symbol,
        timeframe="15m",
        direction=Direction.LONG,
        entry_price=Decimal("50000"),
        suggested_stop_loss=Decimal("48000"),
        suggested_position_size=Decimal("0.1"),
        current_leverage=1,
        tags=[],
        risk_reward_info="2R",
        strategy_name="Test Strategy",
        score=0.8,
    )


def create_test_strategy() -> OrderStrategy:
    """创建测试策略"""
    return OrderStrategy(
        id="test_strategy",
        name="Test Strategy",
        tp_levels=1,
        tp_ratios=[Decimal("1.0")],
        tp_targets=[Decimal("2.0")],
        initial_stop_loss_rr=Decimal("-1.0"),
    )


# ============================================
# 场景 A：正常链路冒烟
# ============================================

@pytest.mark.asyncio
async def test_scenario_a_normal_execution_path():
    """
    场景 A：正常链路冒烟

    验证点：
    1. execute_signal() 能创建 intent
    2. breaker 未触发
    3. 基本流程可运行
    """
    # 准备：创建 mock 对象
    capital_protection = MagicMock(spec=CapitalProtectionManager)
    capital_protection.check_pre_execution = AsyncMock(return_value=(True, None))

    gateway = MagicMock(spec=ExchangeGateway)
    gateway.place_order = AsyncMock(return_value=MagicMock(
        id="ex_entry_001",
        status=OrderStatus.SUBMITTED,
        amount=Decimal("0.1"),
        price=Decimal("50000"),
    ))

    order_lifecycle = MagicMock(spec=OrderLifecycleService)
    order_lifecycle.create_order = AsyncMock()

    # 准备：创建 orchestrator
    orchestrator = ExecutionOrchestrator(
        capital_protection=capital_protection,
        order_lifecycle=order_lifecycle,
        gateway=gateway,
    )

    # 执行：执行信号
    signal = create_test_signal()
    strategy = create_test_strategy()
    intent = await orchestrator.execute_signal(signal, strategy)

    # 验证：intent 创建成功
    assert intent is not None
    assert intent.id.startswith("intent_")

    # 验证：没有触发 breaker
    assert not orchestrator.is_symbol_blocked(signal.symbol)


# ============================================
# 场景 B：异常链路冒烟（replace_sl_failed）
# ============================================

@pytest.mark.asyncio
async def test_scenario_b_replace_sl_failed_recovery():
    """
    场景 B：异常链路冒烟（replace_sl_failed）

    验证点：
    1. 触发 replace_sl_failed
    2. 创建 1 条 PG execution_recovery_tasks
    3. 对应 symbol breaker 生效
    4. 飞书 notifier 路径被调用
    5. 系统停止继续动作，不再创建新 SL
    """
    # 准备：创建 mock 对象
    capital_protection = MagicMock(spec=CapitalProtectionManager)
    gateway = MagicMock(spec=ExchangeGateway)

    # Mock cancel_order 抛异常（触发 replace_sl_failed）
    gateway.cancel_order = AsyncMock(side_effect=Exception("交易所撤销失败"))

    order_lifecycle = MagicMock(spec=OrderLifecycleService)
    order_lifecycle._repository = MagicMock()
    order_lifecycle._repository.get_orders_by_signal = AsyncMock(return_value=[])
    order_lifecycle.cancel_order = AsyncMock()

    # Mock notifier
    notifier = AsyncMock()

    # Mock execution_recovery_repository
    mock_recovery_repo = AsyncMock()

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
        parent_order_id="entry_001",
        exchange_order_id="ex_sl_001",
        status=OrderStatus.OPEN,
        created_at=current_time,
        updated_at=current_time,
    )

    order_lifecycle._repository.get_orders_by_signal = AsyncMock(
        return_value=[entry_order, existing_sl]
    )

    # 准备：创建 intent
    signal = create_test_signal()
    strategy = create_test_strategy()
    intent = ExecutionIntent(
        id="intent_001",
        signal_id="signal_001",
        signal=signal,
        status=ExecutionIntentStatus.PROTECTING,
        strategy=strategy,
        order_id="entry_001",
    )

    # 准备：创建 orchestrator
    orchestrator = ExecutionOrchestrator(
        capital_protection=capital_protection,
        order_lifecycle=order_lifecycle,
        gateway=gateway,
        notifier=notifier,
        execution_recovery_repository=mock_recovery_repo,
    )
    orchestrator._intents["intent_001"] = intent

    # 执行：触发 partial-fill 回调
    await orchestrator._handle_entry_partially_filled(entry_order)

    # 验证：创建 PG recovery task
    mock_recovery_repo.create_task.assert_called_once()
    call_kwargs = mock_recovery_repo.create_task.call_args.kwargs
    assert call_kwargs["recovery_type"] == "replace_sl_failed"
    assert call_kwargs["symbol"] == "BTC/USDT:USDT"

    # 验证：breaker 生效
    assert orchestrator.is_symbol_blocked("BTC/USDT:USDT")

    # 验证：notifier 被调用
    notifier.assert_called_once()

    # 验证：停止继续动作（place_order 未被调用）
    gateway.place_order.assert_not_called()


# ============================================
# 场景 C：启动恢复冒烟
# ============================================

@pytest.mark.asyncio
async def test_scenario_c_startup_recovery():
    """
    场景 C：启动恢复冒烟

    验证点：
    1. StartupReconciliationService 能扫描 active recovery tasks
    2. 可自然收敛的任务能推进为 resolved
    3. Phase 4.4 breaker 重建能根据 active tasks 重建内存 breaker
    4. 日志摘要字段一致，不报 KeyError
    """
    # 准备：创建 mock 对象
    gateway = MagicMock(spec=ExchangeGateway)
    gateway.get_pending_recovery_orders = MagicMock(return_value={})

    order_repo = MagicMock()
    order_repo.get_orders_by_status = AsyncMock(return_value=[])

    order_lifecycle = MagicMock(spec=OrderLifecycleService)

    # Mock execution_recovery_repository
    mock_recovery_repo = AsyncMock()

    # 准备：创建一个可自然收敛的 recovery task
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    active_task = {
        "id": "task_001",
        "intent_id": "intent_001",
        "related_order_id": "order_001",
        "symbol": "BTC/USDT:USDT",
        "recovery_type": "replace_sl_failed",
        "status": "pending",
        "retry_count": 0,
    }

    # list_active 第一次返回活跃任务，第二次返回空（已 resolved）
    call_count = [0]
    async def list_active_side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return [active_task]
        else:
            return []  # 第二次调用时任务已 resolved

    mock_recovery_repo.list_active = AsyncMock(side_effect=list_active_side_effect)

    # 准备：创建已终态的订单
    terminal_order = Order(
        id="order_001",
        signal_id="signal_001",
        symbol="BTC/USDT:USDT",
        direction=Direction.SHORT,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        requested_qty=Decimal("0.05"),
        status=OrderStatus.FILLED,  # 终态
        created_at=now_ms,
        updated_at=now_ms,
    )
    order_repo.get_order = AsyncMock(return_value=terminal_order)

    # 准备：创建 orchestrator
    orchestrator = ExecutionOrchestrator(
        capital_protection=MagicMock(spec=CapitalProtectionManager),
        order_lifecycle=order_lifecycle,
        gateway=gateway,
        execution_recovery_repository=mock_recovery_repo,
    )

    # 准备：创建 StartupReconciliationService
    reconciliation_service = StartupReconciliationService(
        gateway=gateway,
        repository=order_repo,
        lifecycle=order_lifecycle,
        orchestrator=orchestrator,
        execution_recovery_repository=mock_recovery_repo,
    )

    # 执行：运行启动对账
    summary = await reconciliation_service.run_startup_reconciliation()

    # 验证：摘要字段完整，无 KeyError
    assert "total_candidates" in summary
    assert "success_count" in summary
    assert "failure_count" in summary
    assert "recovery_cleared_count" in summary
    assert "pg_recovery_resolved_count" in summary
    assert "pg_recovery_retrying_count" in summary
    assert "pg_recovery_failed_count" in summary
    assert "duration_ms" in summary

    # 验证：任务被标记为 resolved
    mock_recovery_repo.mark_resolved.assert_called_once()
    assert summary["pg_recovery_resolved_count"] == 1

    # 执行：Phase 4.4 breaker 重建
    breaker_count = await orchestrator.rebuild_circuit_breakers_from_recovery_tasks()

    # 验证：breaker 重建成功
    assert breaker_count == 0  # 已 resolved，无 active tasks


# ============================================
# 场景 D：熔断拦截冒烟
# ============================================

@pytest.mark.asyncio
async def test_scenario_d_circuit_breaker_blocks_signal():
    """
    场景 D：熔断拦截冒烟

    验证点：
    1. breaker 集合中存在目标 symbol
    2. execute_signal() 直接返回 BLOCKED
    3. 不触发 gateway.place_order()
    4. blocked_reason 为 CIRCUIT_BREAKER
    """
    # 准备：创建 mock 对象
    capital_protection = MagicMock(spec=CapitalProtectionManager)
    gateway = MagicMock(spec=ExchangeGateway)
    order_lifecycle = MagicMock(spec=OrderLifecycleService)

    # 准备：创建 orchestrator
    orchestrator = ExecutionOrchestrator(
        capital_protection=capital_protection,
        order_lifecycle=order_lifecycle,
        gateway=gateway,
    )

    # 准备：手动触发 breaker
    orchestrator._circuit_breaker_symbols.add("BTC/USDT:USDT")

    # 验证：breaker 生效
    assert orchestrator.is_symbol_blocked("BTC/USDT:USDT")

    # 执行：尝试执行信号
    signal = create_test_signal("BTC/USDT:USDT")
    strategy = create_test_strategy()
    intent = await orchestrator.execute_signal(signal, strategy)

    # 验证：intent 被阻塞
    assert intent.status == ExecutionIntentStatus.BLOCKED
    assert intent.blocked_reason == "CIRCUIT_BREAKER"
    assert "熔断" in intent.blocked_message

    # 验证：place_order 未被调用
    gateway.place_order.assert_not_called()


# ============================================
# 主函数
# ============================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
