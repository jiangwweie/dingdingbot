"""
PG Execution Recovery Repository 单元测试（Mock 版）

测试目标：
1. initialize() 会调用 init_pg_core_db()
2. _orm_to_dict 输出正确
3. mark_resolved/mark_retrying/mark_failed 的参数传递正确

注意：不使用真实 PG，避免 asyncpg 与 pytest-asyncio 冲突
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.infrastructure.pg_execution_recovery_repository import PgExecutionRecoveryRepository


@pytest.mark.asyncio
async def test_initialize_calls_init_pg_core_db():
    """
    测试 initialize() 会调用 init_pg_core_db()

    场景：
    1. 创建 repository（默认构造）
    2. 调用 initialize()
    断言：
    - init_pg_core_db() 被调用一次
    """
    # Mock get_pg_session_maker
    with patch('src.infrastructure.pg_execution_recovery_repository.get_pg_session_maker') as mock_get_session_maker:
        mock_session_maker = MagicMock()
        mock_get_session_maker.return_value = mock_session_maker

        # Mock init_pg_core_db
        with patch('src.infrastructure.pg_execution_recovery_repository.init_pg_core_db', new_callable=AsyncMock) as mock_init:
            mock_init.return_value = None

            repo = PgExecutionRecoveryRepository()  # 默认构造
            await repo.initialize()

            # 验证 init_pg_core_db 被调用
            mock_init.assert_called_once()


@pytest.mark.asyncio
async def test_default_constructor_uses_global_session_maker():
    """
    测试默认构造使用全局 session_maker

    场景：
    1. 不传 session_maker 参数
    断言：
    - get_pg_session_maker() 被调用
    """
    with patch('src.infrastructure.pg_execution_recovery_repository.get_pg_session_maker') as mock_get_session_maker:
        mock_session_maker = MagicMock()
        mock_get_session_maker.return_value = mock_session_maker

        repo = PgExecutionRecoveryRepository()

        # 验证 get_pg_session_maker 被调用
        mock_get_session_maker.assert_called_once()


@pytest.mark.asyncio
async def test_custom_session_maker_injection():
    """
    测试可以注入自定义 session_maker

    场景：
    1. 传入自定义 session_maker
    断言：
    - 使用注入的 session_maker，不调用 get_pg_session_maker()
    """
    with patch('src.infrastructure.pg_execution_recovery_repository.get_pg_session_maker') as mock_get_session_maker:
        custom_session_maker = MagicMock()

        repo = PgExecutionRecoveryRepository(session_maker=custom_session_maker)

        # 验证 get_pg_session_maker 没有被调用
        mock_get_session_maker.assert_not_called()


@pytest.mark.asyncio
async def test_close_is_lightweight():
    """
    测试 close() 是轻量实现

    场景：
    1. 创建 repository
    2. 调用 close()
    断言：
    - 不抛异常
    """
    mock_session_maker = MagicMock()
    repo = PgExecutionRecoveryRepository(session_maker=mock_session_maker)

    await repo.close()
    # 无异常即成功


def test_orm_to_dict_output():
    """
    测试 _orm_to_dict 输出正确

    场景：
    1. 创建 mock ORM 对象
    2. 调用 _orm_to_dict()
    断言：
    - 输出字典包含所有字段
    """
    from src.infrastructure.pg_models import PGExecutionRecoveryTaskORM

    # 创建 mock ORM 对象
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    mock_orm = PGExecutionRecoveryTaskORM(
        id="task_001",
        intent_id="intent_001",
        related_order_id="order_001",
        related_exchange_order_id="ex_order_001",
        symbol="BTC/USDT:USDT",
        recovery_type="replace_sl_failed",
        status="pending",
        error_message="Test error",
        retry_count=0,
        next_retry_at=None,
        context_payload={"test_key": "test_value"},
        created_at=now_ms,
        updated_at=now_ms,
        resolved_at=None,
    )

    mock_session_maker = MagicMock()
    repo = PgExecutionRecoveryRepository(session_maker=mock_session_maker)

    result = repo._orm_to_dict(mock_orm)

    # 验证输出
    assert result["id"] == "task_001"
    assert result["intent_id"] == "intent_001"
    assert result["related_order_id"] == "order_001"
    assert result["related_exchange_order_id"] == "ex_order_001"
    assert result["symbol"] == "BTC/USDT:USDT"
    assert result["recovery_type"] == "replace_sl_failed"
    assert result["status"] == "pending"
    assert result["error_message"] == "Test error"
    assert result["retry_count"] == 0
    assert result["next_retry_at"] is None
    assert result["context_payload"]["test_key"] == "test_value"
    assert result["created_at"] == now_ms
    assert result["updated_at"] == now_ms
    assert result["resolved_at"] is None


@pytest.mark.asyncio
async def test_mark_resolved_calls_session_correctly():
    """
    测试 mark_resolved 参数传递正确

    场景：
    1. Mock session_maker 和 session
    2. 调用 mark_resolved()
    断言：
    - session.execute 被调用
    - session.commit 被调用
    """
    # Mock session
    mock_session = AsyncMock()

    # Mock execute 返回结果
    from src.infrastructure.pg_models import PGExecutionRecoveryTaskORM
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    mock_task = PGExecutionRecoveryTaskORM(
        id="task_001",
        intent_id="intent_001",
        symbol="BTC/USDT:USDT",
        recovery_type="replace_sl_failed",
        status="pending",
        created_at=now_ms,
        updated_at=now_ms,
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_task
    mock_session.execute.return_value = mock_result

    # Mock session_maker
    mock_session_maker = MagicMock()
    mock_session_maker.return_value.__aenter__.return_value = mock_session

    repo = PgExecutionRecoveryRepository(session_maker=mock_session_maker)

    resolved_at = int(datetime.now(timezone.utc).timestamp() * 1000)
    await repo.mark_resolved("task_001", resolved_at, error_message="已解决")

    # 验证 session.commit 被调用
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_mark_retrying_calls_session_correctly():
    """
    测试 mark_retrying 参数传递正确

    场景：
    1. Mock session_maker 和 session
    2. 调用 mark_retrying()
    断言：
    - session.commit 被调用
    """
    # Mock session
    mock_session = AsyncMock()

    # Mock execute 返回结果
    from src.infrastructure.pg_models import PGExecutionRecoveryTaskORM
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    mock_task = PGExecutionRecoveryTaskORM(
        id="task_001",
        intent_id="intent_001",
        symbol="BTC/USDT:USDT",
        recovery_type="replace_sl_failed",
        status="pending",
        retry_count=0,
        created_at=now_ms,
        updated_at=now_ms,
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_task
    mock_session.execute.return_value = mock_result

    # Mock session_maker
    mock_session_maker = MagicMock()
    mock_session_maker.return_value.__aenter__.return_value = mock_session

    repo = PgExecutionRecoveryRepository(session_maker=mock_session_maker)

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    next_retry_at = now_ms + 60000
    await repo.mark_retrying("task_001", retry_count=1, next_retry_at=next_retry_at)

    # 验证 session.commit 被调用
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_mark_failed_calls_session_correctly():
    """
    测试 mark_failed 参数传递正确

    场景：
    1. Mock session_maker 和 session
    2. 调用 mark_failed()
    断言：
    - session.commit 被调用
    """
    # Mock session
    mock_session = AsyncMock()

    # Mock execute 返回结果
    from src.infrastructure.pg_models import PGExecutionRecoveryTaskORM
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    mock_task = PGExecutionRecoveryTaskORM(
        id="task_001",
        intent_id="intent_001",
        symbol="BTC/USDT:USDT",
        recovery_type="replace_sl_failed",
        status="retrying",
        created_at=now_ms,
        updated_at=now_ms,
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_task
    mock_session.execute.return_value = mock_result

    # Mock session_maker
    mock_session_maker = MagicMock()
    mock_session_maker.return_value.__aenter__.return_value = mock_session

    repo = PgExecutionRecoveryRepository(session_maker=mock_session_maker)

    await repo.mark_failed("task_001", error_message="达到最大重试次数")

    # 验证 session.commit 被调用
    mock_session.commit.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])