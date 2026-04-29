"""
Circuit Breaker 从 PG Recovery Tasks 重建的单元测试

测试目标：
1. 当 execution_recovery_repository.list_active() 返回两个不同 symbol 的 active tasks 时，_circuit_breaker_symbols 被重建为对应 symbol 集合
2. 当 repo 为 None 时，返回 0 且不报错
3. 当 active tasks 为空时，breaker 集合被清空
"""
import pytest
from unittest.mock import MagicMock, AsyncMock

from src.application.execution_orchestrator import ExecutionOrchestrator
from src.application.capital_protection import CapitalProtectionManager
from src.application.order_lifecycle_service import OrderLifecycleService
from src.infrastructure.exchange_gateway import ExchangeGateway


@pytest.mark.asyncio
async def test_rebuild_circuit_breakers_from_active_tasks():
    """
    测试从 PG 活跃恢复任务重建 circuit breaker

    场景：
    1. list_active() 返回两个不同 symbol 的 active tasks
    断言：
    - _circuit_breaker_symbols 被重建为对应 symbol 集合
    - 返回值为 2
    """
    # 准备：创建 mock 对象
    capital_protection = MagicMock(spec=CapitalProtectionManager)
    order_lifecycle = MagicMock(spec=OrderLifecycleService)
    gateway = MagicMock(spec=ExchangeGateway)

    # Mock execution_recovery_repository
    mock_recovery_repo = AsyncMock()
    mock_recovery_repo.list_active = AsyncMock(return_value=[
        {
            "id": "task_001",
            "intent_id": "intent_001",
            "symbol": "BTC/USDT:USDT",
            "recovery_type": "replace_sl_failed",
            "status": "pending",
        },
        {
            "id": "task_002",
            "intent_id": "intent_002",
            "symbol": "ETH/USDT:USDT",
            "recovery_type": "replace_sl_failed",
            "status": "retrying",
        },
    ])

    # 创建 orchestrator
    orchestrator = ExecutionOrchestrator(
        capital_protection=capital_protection,
        order_lifecycle=order_lifecycle,
        gateway=gateway,
        execution_recovery_repository=mock_recovery_repo,
    )

    # 预设一个旧的熔断 symbol（应该被清除）
    orchestrator._circuit_breaker_symbols.add("OLD/USDT:USDT")

    # 执行：重建 circuit breaker
    count = await orchestrator.rebuild_circuit_breakers_from_recovery_tasks()

    # 验证：返回值为 2
    assert count == 2

    # 验证：breaker 集合被重建为新的 symbol 集合
    assert len(orchestrator._circuit_breaker_symbols) == 2
    assert "BTC/USDT:USDT" in orchestrator._circuit_breaker_symbols
    assert "ETH/USDT:USDT" in orchestrator._circuit_breaker_symbols
    assert "OLD/USDT:USDT" not in orchestrator._circuit_breaker_symbols

    # 验证：list_active 被调用一次
    mock_recovery_repo.list_active.assert_called_once()


@pytest.mark.asyncio
async def test_rebuild_circuit_breakers_when_repo_is_none():
    """
    测试当 repo 为 None 时的行为

    场景：
    1. execution_recovery_repository 为 None
    断言：
    - 返回 0
    - 不抛异常
    - 不调用 list_active()
    """
    # 准备：创建 mock 对象
    capital_protection = MagicMock(spec=CapitalProtectionManager)
    order_lifecycle = MagicMock(spec=OrderLifecycleService)
    gateway = MagicMock(spec=ExchangeGateway)

    # 创建 orchestrator（不注入 recovery repo）
    orchestrator = ExecutionOrchestrator(
        capital_protection=capital_protection,
        order_lifecycle=order_lifecycle,
        gateway=gateway,
        execution_recovery_repository=None,
    )

    # 执行：重建 circuit breaker
    count = await orchestrator.rebuild_circuit_breakers_from_recovery_tasks()

    # 验证：返回 0
    assert count == 0

    # 验证：不抛异常
    # （如果抛异常，测试会失败）


@pytest.mark.asyncio
async def test_rebuild_circuit_breakers_when_no_active_tasks():
    """
    测试当 active tasks 为空时的行为

    场景：
    1. list_active() 返回空列表
    断言：
    - _circuit_breaker_symbols 被清空
    - 返回 0
    """
    # 准备：创建 mock 对象
    capital_protection = MagicMock(spec=CapitalProtectionManager)
    order_lifecycle = MagicMock(spec=OrderLifecycleService)
    gateway = MagicMock(spec=ExchangeGateway)

    # Mock execution_recovery_repository
    mock_recovery_repo = AsyncMock()
    mock_recovery_repo.list_active = AsyncMock(return_value=[])

    # 创建 orchestrator
    orchestrator = ExecutionOrchestrator(
        capital_protection=capital_protection,
        order_lifecycle=order_lifecycle,
        gateway=gateway,
        execution_recovery_repository=mock_recovery_repo,
    )

    # 预设一个旧的熔断 symbol（应该被清除）
    orchestrator._circuit_breaker_symbols.add("OLD/USDT:USDT")

    # 执行：重建 circuit breaker
    count = await orchestrator.rebuild_circuit_breakers_from_recovery_tasks()

    # 验证：返回 0
    assert count == 0

    # 验证：breaker 集合被清空
    assert len(orchestrator._circuit_breaker_symbols) == 0

    # 验证：list_active 被调用一次
    mock_recovery_repo.list_active.assert_called_once()


@pytest.mark.asyncio
async def test_rebuild_circuit_breakers_handles_exception():
    """
    测试异常处理

    场景：
    1. list_active() 抛出异常
    断言：
    - 返回 0
    - 不抛异常
    - 旧的 breaker 集合保持不变
    """
    # 准备：创建 mock 对象
    capital_protection = MagicMock(spec=CapitalProtectionManager)
    order_lifecycle = MagicMock(spec=OrderLifecycleService)
    gateway = MagicMock(spec=ExchangeGateway)

    # Mock execution_recovery_repository
    mock_recovery_repo = AsyncMock()
    mock_recovery_repo.list_active = AsyncMock(side_effect=Exception("数据库连接失败"))

    # 创建 orchestrator
    orchestrator = ExecutionOrchestrator(
        capital_protection=capital_protection,
        order_lifecycle=order_lifecycle,
        gateway=gateway,
        execution_recovery_repository=mock_recovery_repo,
    )

    # 预设一个旧的熔断 symbol（应该保持不变）
    orchestrator._circuit_breaker_symbols.add("OLD/USDT:USDT")

    # 执行：重建 circuit breaker
    count = await orchestrator.rebuild_circuit_breakers_from_recovery_tasks()

    # 验证：返回 0
    assert count == 0

    # 验证：旧的 breaker 集合保持不变
    assert len(orchestrator._circuit_breaker_symbols) == 1
    assert "OLD/USDT:USDT" in orchestrator._circuit_breaker_symbols


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
