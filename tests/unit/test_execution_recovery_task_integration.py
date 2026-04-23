"""
Execution Recovery Task Integration 测试

测试目标：
1. orchestrator 在 replace_sl_failed 时会创建 PG recovery task
2. startup reconciliation 能把终态任务 mark_resolved
"""
import pytest
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import AsyncGenerator
from unittest.mock import MagicMock, AsyncMock

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

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
from src.infrastructure.pg_models import PGCoreBase
from src.infrastructure.pg_execution_recovery_repository import PgExecutionRecoveryRepository


# 测试数据库配置
TEST_DATABASE_URL = os.getenv(
    "TEST_PG_DATABASE_URL",
    "postgresql+asyncpg://test:test@localhost:5432/test_recovery_integration"
)


@pytest.fixture
async def test_session_maker() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """创建测试数据库 session maker。"""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    # 创建表
    async with engine.begin() as conn:
        await conn.run_sync(PGCoreBase.metadata.create_all)

    yield session_maker

    # 清理表
    async with engine.begin() as conn:
        await conn.run_sync(PGCoreBase.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
async def recovery_repo(test_session_maker: async_sessionmaker[AsyncSession]) -> PgExecutionRecoveryRepository:
    """创建 recovery repository 实例。"""
    repo = PgExecutionRecoveryRepository(session_maker=test_session_maker)
    await repo.initialize()
    return repo


@pytest.mark.asyncio
async def test_orchestrator_creates_pg_recovery_task(recovery_repo: PgExecutionRecoveryRepository):
    """
    测试 orchestrator 在 replace_sl_failed 时会创建 PG recovery task

    场景：
    1. ENTRY 部分成交，已有 SL 订单
    2. 撤销交易所旧 SL 失败
    3. orchestrator 应创建 PG recovery task
    断言：
    - PG 中有对应的 recovery task
    - task 的字段正确
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
    mock_order_repo.get_orders_by_signal = AsyncMock(return_value=[entry_order, existing_sl])
    order_lifecycle._repository = mock_order_repo

    # 准备：创建 ExecutionIntent
    from src.domain.execution_intent import ExecutionIntent, ExecutionIntentStatus
    from src.domain.models import SignalResult, OrderStrategy

    # 创建策略快照
    strategy = OrderStrategy(
        stop_loss=Decimal("49000"),
        tp_targets=[Decimal("51000")],
    )

    intent = ExecutionIntent(
        id="intent_001",
        signal_id="signal_001",
        symbol="BTC/USDT:USDT",
        status=ExecutionIntentStatus.PROTECTING,
        strategy=strategy,
    )

    # 准备：创建 orchestrator 并注入 intent
    orchestrator = ExecutionOrchestrator(
        capital_protection=capital_protection,
        order_lifecycle=order_lifecycle,
        gateway=gateway,
        execution_recovery_repository=recovery_repo,
    )

    # 手动注入 intent 到内存缓存
    orchestrator._intents["intent_001"] = intent

    # 执行：触发 _handle_entry_partially_filled
    await orchestrator._handle_entry_partially_filled(entry_order)

    # 验证：检查 PG 中是否有 recovery task
    tasks = await recovery_repo.list_active()
    assert len(tasks) == 1

    task = tasks[0]
    assert task["recovery_type"] == "replace_sl_failed"
    assert task["intent_id"] == "intent_001"
    assert task["related_order_id"] == "sl_001"
    assert task["related_exchange_order_id"] == "ex_sl_001"
    assert task["symbol"] == "BTC/USDT:USDT"
    assert task["status"] == "pending"

    # 验证 context_payload 包含必要字段
    context = task["context_payload"]
    assert "entry_order_id" in context
    assert "filled_qty_total" in context
    assert "protected_qty_total" in context
    assert "delta_qty" in context
    assert context["entry_order_id"] == "entry_001"
    assert context["existing_sl_order_id"] == "sl_001"
    assert context["existing_sl_exchange_order_id"] == "ex_sl_001"


@pytest.mark.asyncio
async def test_startup_reconciliation_marks_resolved(recovery_repo: PgExecutionRecoveryRepository):
    """
    测试 startup reconciliation 能把终态任务 mark_resolved

    场景：
    1. 创建一个 pending recovery task
    2. 对应订单已终态（FILLED）
    3. 启动对账扫描
    断言：
    - task 被标记为 resolved
    """
    # 准备：创建 recovery task
    task_id = "recovery_001"
    intent_id = "intent_001"
    symbol = "BTC/USDT:USDT"

    await recovery_repo.create_task(
        task_id=task_id,
        intent_id=intent_id,
        symbol=symbol,
        recovery_type="replace_sl_failed",
        related_order_id="order_001",
        related_exchange_order_id="ex_order_001",
        error_message="交易所撤销失败",
    )

    # 准备：创建 mock order repository
    # 返回一个终态订单
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    filled_order = Order(
        id="order_001",
        signal_id="signal_001",
        symbol=symbol,
        direction=Direction.SHORT,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        requested_qty=Decimal("0.1"),
        filled_qty=Decimal("0.1"),
        status=OrderStatus.FILLED,  # 终态
        created_at=current_time,
        updated_at=current_time,
    )

    mock_order_repo = MagicMock()
    mock_order_repo.get_order = AsyncMock(return_value=filled_order)

    # 准备：创建 startup reconciliation service
    from src.application.startup_reconciliation_service import StartupReconciliationService

    mock_gateway = MagicMock(spec=ExchangeGateway)
    mock_lifecycle = MagicMock()

    reconciliation_service = StartupReconciliationService(
        gateway=mock_gateway,
        repository=mock_order_repo,
        lifecycle=mock_lifecycle,
        orchestrator=None,
        execution_recovery_repository=recovery_repo,
    )

    # 执行：运行对账
    summary = await reconciliation_service.run_startup_reconciliation()

    # 验证：task 被标记为 resolved
    task = await recovery_repo.get(task_id)
    assert task["status"] == "resolved"
    assert task["resolved_at"] is not None

    # 验证：summary 包含 PG recovery 统计
    assert summary["pg_recovery_resolved_count"] == 1


@pytest.mark.asyncio
async def test_startup_reconciliation_marks_retrying(recovery_repo: PgExecutionRecoveryRepository):
    """
    测试 startup reconciliation 对非终态任务标记 retrying

    场景：
    1. 创建一个 pending recovery task
    2. 对应订单未终态（OPEN）
    3. 启动对账扫描
    断言：
    - task 被标记为 retrying
    - retry_count = 1
    - next_retry_at 正确设置
    """
    # 准备：创建 recovery task
    task_id = "recovery_001"
    intent_id = "intent_001"
    symbol = "BTC/USDT:USDT"

    await recovery_repo.create_task(
        task_id=task_id,
        intent_id=intent_id,
        symbol=symbol,
        recovery_type="replace_sl_failed",
        related_order_id="order_001",
        related_exchange_order_id="ex_order_001",
        error_message="交易所撤销失败",
    )

    # 准备：创建 mock order repository
    # 返回一个非终态订单
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    open_order = Order(
        id="order_001",
        signal_id="signal_001",
        symbol=symbol,
        direction=Direction.SHORT,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        requested_qty=Decimal("0.1"),
        filled_qty=Decimal("0"),
        status=OrderStatus.OPEN,  # 非终态
        created_at=current_time,
        updated_at=current_time,
    )

    mock_order_repo = MagicMock()
    mock_order_repo.get_order = AsyncMock(return_value=open_order)

    # 准备：创建 startup reconciliation service
    from src.application.startup_reconciliation_service import StartupReconciliationService

    mock_gateway = MagicMock(spec=ExchangeGateway)
    mock_lifecycle = MagicMock()

    reconciliation_service = StartupReconciliationService(
        gateway=mock_gateway,
        repository=mock_order_repo,
        lifecycle=mock_lifecycle,
        orchestrator=None,
        execution_recovery_repository=recovery_repo,
    )

    # 执行：运行对账
    summary = await reconciliation_service.run_startup_reconciliation()

    # 验证：task 被标记为 retrying
    task = await recovery_repo.get(task_id)
    assert task["status"] == "retrying"
    assert task["retry_count"] == 1
    assert task["next_retry_at"] is not None

    # 验证：summary 包含 PG recovery 统计
    assert summary["pg_recovery_retrying_count"] == 1


@pytest.mark.asyncio
async def test_startup_reconciliation_marks_failed_after_max_retries(recovery_repo: PgExecutionRecoveryRepository):
    """
    测试 startup reconciliation 对达到最大重试次数的任务标记 failed

    场景：
    1. 创建一个 retrying recovery task（retry_count=3）
    2. 对应订单未终态（OPEN）
    3. 启动对账扫描
    断言：
    - task 被标记为 failed
    """
    # 准备：创建 recovery task 并标记为 retrying（retry_count=3）
    task_id = "recovery_001"
    intent_id = "intent_001"
    symbol = "BTC/USDT:USDT"

    await recovery_repo.create_task(
        task_id=task_id,
        intent_id=intent_id,
        symbol=symbol,
        recovery_type="replace_sl_failed",
        related_order_id="order_001",
        related_exchange_order_id="ex_order_001",
        error_message="交易所撤销失败",
    )

    # 手动设置 retry_count=3
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    await recovery_repo.mark_retrying(task_id, retry_count=3, next_retry_at=now_ms + 60000)

    # 准备：创建 mock order repository
    # 返回一个非终态订单
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    open_order = Order(
        id="order_001",
        signal_id="signal_001",
        symbol=symbol,
        direction=Direction.SHORT,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        requested_qty=Decimal("0.1"),
        filled_qty=Decimal("0"),
        status=OrderStatus.OPEN,  # 非终态
        created_at=current_time,
        updated_at=current_time,
    )

    mock_order_repo = MagicMock()
    mock_order_repo.get_order = AsyncMock(return_value=open_order)

    # 准备：创建 startup reconciliation service
    from src.application.startup_reconciliation_service import StartupReconciliationService

    mock_gateway = MagicMock(spec=ExchangeGateway)
    mock_lifecycle = MagicMock()

    reconciliation_service = StartupReconciliationService(
        gateway=mock_gateway,
        repository=mock_order_repo,
        lifecycle=mock_lifecycle,
        orchestrator=None,
        execution_recovery_repository=recovery_repo,
    )

    # 执行：运行对账
    summary = await reconciliation_service.run_startup_reconciliation()

    # 验证：task 被标记为 failed
    task = await recovery_repo.get(task_id)
    assert task["status"] == "failed"
    assert "最大重试次数" in task["error_message"]

    # 验证：summary 包含 PG recovery 统计
    assert summary["pg_recovery_failed_count"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
