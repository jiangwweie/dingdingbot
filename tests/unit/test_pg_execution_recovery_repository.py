"""
PG Execution Recovery Repository 测试

测试目标：
1. repository create/get/list_active/mark_resolved 正常
2. retrying/failed 的状态推进逻辑正确
"""
import pytest
import os
from datetime import datetime, timezone
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.infrastructure.pg_models import PGCoreBase
from src.infrastructure.pg_execution_recovery_repository import PgExecutionRecoveryRepository


# 测试数据库配置
TEST_DATABASE_URL = os.getenv(
    "TEST_PG_DATABASE_URL",
    "postgresql+asyncpg://test:test@localhost:5432/test_recovery"
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
async def repo(test_session_maker: async_sessionmaker[AsyncSession]) -> PgExecutionRecoveryRepository:
    """创建 repository 实例。"""
    repo = PgExecutionRecoveryRepository(session_maker=test_session_maker)
    await repo.initialize()
    return repo


@pytest.mark.asyncio
async def test_create_and_get_task(repo: PgExecutionRecoveryRepository):
    """
    测试创建和获取任务

    场景：
    1. 创建一个 recovery task
    2. 通过 get() 获取
    断言：
    - 返回的任务数据正确
    """
    task_id = "test_task_001"
    intent_id = "intent_001"
    symbol = "BTC/USDT:USDT"
    recovery_type = "replace_sl_failed"

    # 创建任务
    await repo.create_task(
        task_id=task_id,
        intent_id=intent_id,
        symbol=symbol,
        recovery_type=recovery_type,
        related_order_id="order_001",
        related_exchange_order_id="ex_order_001",
        error_message="Test error",
        context_payload={"test_key": "test_value"},
    )

    # 获取任务
    task = await repo.get(task_id)

    assert task is not None
    assert task["id"] == task_id
    assert task["intent_id"] == intent_id
    assert task["symbol"] == symbol
    assert task["recovery_type"] == recovery_type
    assert task["status"] == "pending"
    assert task["retry_count"] == 0
    assert task["error_message"] == "Test error"
    assert task["context_payload"]["test_key"] == "test_value"


@pytest.mark.asyncio
async def test_get_by_intent_id(repo: PgExecutionRecoveryRepository):
    """
    测试按 intent_id 获取任务

    场景：
    1. 创建多个任务
    2. 通过 intent_id 查询
    断言：
    - 返回正确的任务
    """
    # 创建任务
    await repo.create_task(
        task_id="task_001",
        intent_id="intent_001",
        symbol="BTC/USDT:USDT",
        recovery_type="replace_sl_failed",
    )

    await repo.create_task(
        task_id="task_002",
        intent_id="intent_002",
        symbol="ETH/USDT:USDT",
        recovery_type="replace_sl_failed",
    )

    # 按 intent_id 查询
    task = await repo.get_by_intent_id("intent_001")

    assert task is not None
    assert task["id"] == "task_001"
    assert task["intent_id"] == "intent_001"


@pytest.mark.asyncio
async def test_list_active(repo: PgExecutionRecoveryRepository):
    """
    测试列出活跃任务

    场景：
    1. 创建多个任务（不同状态）
    2. 调用 list_active()
    断言：
    - 只返回 pending/retrying 且 next_retry_at 符合条件的任务
    """
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 创建 pending 任务
    await repo.create_task(
        task_id="task_pending",
        intent_id="intent_001",
        symbol="BTC/USDT:USDT",
        recovery_type="replace_sl_failed",
    )

    # 创建 retrying 任务（next_retry_at 已过期）
    await repo.create_task(
        task_id="task_retrying",
        intent_id="intent_002",
        symbol="ETH/USDT:USDT",
        recovery_type="replace_sl_failed",
    )
    await repo.mark_retrying("task_retrying", retry_count=1, next_retry_at=now_ms - 1000)

    # 创建 resolved 任务
    await repo.create_task(
        task_id="task_resolved",
        intent_id="intent_003",
        symbol="SOL/USDT:USDT",
        recovery_type="replace_sl_failed",
    )
    await repo.mark_resolved("task_resolved", resolved_at=now_ms)

    # 列出活跃任务
    active_tasks = await repo.list_active(now_ms)

    assert len(active_tasks) == 2
    task_ids = [t["id"] for t in active_tasks]
    assert "task_pending" in task_ids
    assert "task_retrying" in task_ids
    assert "task_resolved" not in task_ids


@pytest.mark.asyncio
async def test_mark_resolved(repo: PgExecutionRecoveryRepository):
    """
    测试标记任务为已解决

    场景：
    1. 创建任务
    2. 标记为 resolved
    断言：
    - 状态变为 resolved
    - resolved_at 正确设置
    """
    await repo.create_task(
        task_id="task_001",
        intent_id="intent_001",
        symbol="BTC/USDT:USDT",
        recovery_type="replace_sl_failed",
    )

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    await repo.mark_resolved("task_001", resolved_at=now_ms, error_message="已自然收敛")

    task = await repo.get("task_001")
    assert task["status"] == "resolved"
    assert task["resolved_at"] == now_ms
    assert task["error_message"] == "已自然收敛"


@pytest.mark.asyncio
async def test_mark_retrying(repo: PgExecutionRecoveryRepository):
    """
    测试标记任务为重试中

    场景：
    1. 创建任务
    2. 标记为 retrying
    断言：
    - 状态变为 retrying
    - retry_count 和 next_retry_at 正确设置
    """
    await repo.create_task(
        task_id="task_001",
        intent_id="intent_001",
        symbol="BTC/USDT:USDT",
        recovery_type="replace_sl_failed",
    )

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    next_retry_at = now_ms + 60000

    await repo.mark_retrying(
        "task_001",
        retry_count=1,
        next_retry_at=next_retry_at,
        error_message="等待重试"
    )

    task = await repo.get("task_001")
    assert task["status"] == "retrying"
    assert task["retry_count"] == 1
    assert task["next_retry_at"] == next_retry_at
    assert task["error_message"] == "等待重试"


@pytest.mark.asyncio
async def test_mark_failed(repo: PgExecutionRecoveryRepository):
    """
    测试标记任务为最终失败

    场景：
    1. 创建任务
    2. 标记为 failed
    断言：
    - 状态变为 failed
    - error_message 正确设置
    """
    await repo.create_task(
        task_id="task_001",
        intent_id="intent_001",
        symbol="BTC/USDT:USDT",
        recovery_type="replace_sl_failed",
    )

    await repo.mark_failed("task_001", error_message="达到最大重试次数")

    task = await repo.get("task_001")
    assert task["status"] == "failed"
    assert task["error_message"] == "达到最大重试次数"


@pytest.mark.asyncio
async def test_delete(repo: PgExecutionRecoveryRepository):
    """
    测试删除任务

    场景：
    1. 创建任务
    2. 删除任务
    断言：
    - 任务不存在
    """
    await repo.create_task(
        task_id="task_001",
        intent_id="intent_001",
        symbol="BTC/USDT:USDT",
        recovery_type="replace_sl_failed",
    )

    await repo.delete("task_001")

    task = await repo.get("task_001")
    assert task is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
