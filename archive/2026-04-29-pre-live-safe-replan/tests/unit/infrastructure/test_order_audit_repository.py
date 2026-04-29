"""
Test OrderAuditLogRepository Worker Error Handling - T009

测试审计日志仓库的 Worker 异常处理增强功能：
1. 异常时记录详细错误日志
2. 连续错误计数机制
3. 达到阈值时触发 CRITICAL 告警
4. 成功后重置错误计数
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal

from src.infrastructure.order_audit_repository import OrderAuditLogRepository
from src.domain.models import OrderAuditEventType, OrderAuditTriggerSource


class TestP2_9_WorkerErrorHandling:
    """P2-9: Worker 异常处理增强测试"""

    @pytest.fixture
    def mock_db_session(self):
        """创建模拟数据库会话"""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()

        # 创建上下文管理器模拟
        async def async_context_manager(*args, **kwargs):
            return session
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)

        # 创建 session factory
        session_factory = MagicMock(return_value=session)
        return session_factory

    @pytest.fixture
    def repository(self, mock_db_session):
        """创建审计日志仓库实例"""
        repo = OrderAuditLogRepository(mock_db_session)
        return repo

    @pytest.mark.asyncio
    async def test_worker_logs_error_on_exception(self, repository, caplog):
        """测试异常时记录错误日志"""
        # Arrange
        await repository.initialize(queue_size=10)

        # 模拟 _save_log_entry 抛出异常
        original_save = repository._save_log_entry
        async def mock_save(entry):
            raise Exception("Database connection error")
        repository._save_log_entry = mock_save

        # Act: 入队一个日志条目
        await repository.log(
            order_id="ord_test",
            new_status="FILLED",
            event_type=OrderAuditEventType.ORDER_FILLED,
            triggered_by=OrderAuditTriggerSource.SYSTEM,
        )

        # 等待 Worker 处理
        await asyncio.sleep(0.1)

        # Assert: 应该记录错误日志
        assert "审计日志写入失败" in caplog.text
        assert "Database connection error" in caplog.text
        assert "ERROR" in caplog.text

        # Cleanup
        await repository.close()

    @pytest.mark.asyncio
    async def test_worker_consecutive_error_count(self, repository, caplog):
        """测试连续错误计数"""
        # Arrange
        await repository.initialize(queue_size=10)

        error_count = [0]

        async def mock_save(entry):
            error_count[0] += 1
            raise Exception(f"Error #{error_count[0]}")

        repository._save_log_entry = mock_save

        # Act: 入队多个日志条目，模拟连续失败
        for i in range(5):
            await repository.log(
                order_id=f"ord_test_{i}",
                new_status="FILLED",
                event_type=OrderAuditEventType.ORDER_FILLED,
                triggered_by=OrderAuditTriggerSource.SYSTEM,
            )
            await asyncio.sleep(0.05)

        # Assert: 应该记录多次错误，且错误计数递增
        assert caplog.text.count("审计日志写入失败") >= 3
        assert "错误 1/10" in caplog.text
        assert "错误 2/10" in caplog.text
        assert "错误 3/10" in caplog.text

        # Cleanup
        await repository.close()

    @pytest.mark.asyncio
    async def test_worker_critical_alert_on_max_errors(self, repository, caplog):
        """测试达到阈值时触发 CRITICAL 告警"""
        # Arrange
        await repository.initialize(queue_size=10)

        async def mock_save(entry):
            raise Exception("Persistent error")

        repository._save_log_entry = mock_save

        # Act: 入队多个日志条目，模拟连续失败超过阈值
        for i in range(12):
            await repository.log(
                order_id=f"ord_test_{i}",
                new_status="FILLED",
                event_type=OrderAuditEventType.ORDER_FILLED,
                triggered_by=OrderAuditTriggerSource.SYSTEM,
            )
            await asyncio.sleep(0.05)

        # Assert: 应该记录 CRITICAL 告警
        assert "CRITICAL" in caplog.text
        assert "审计日志 Worker 连续失败" in caplog.text
        assert "可能导致审计数据丢失" in caplog.text

        # Cleanup
        await repository.close()

    @pytest.mark.asyncio
    async def test_worker_resets_count_on_success(self, repository, caplog):
        """测试成功后重置错误计数"""
        # Arrange
        await repository.initialize(queue_size=10)

        error_count = [0]

        async def mock_save(entry):
            error_count[0] += 1
            if error_count[0] <= 2:
                raise Exception("Temporary error")
            # 第 3 次及以后成功

        repository._save_log_entry = mock_save

        # Act: 入队多个日志条目，先失败后成功
        for i in range(5):
            await repository.log(
                order_id=f"ord_test_{i}",
                new_status="FILLED",
                event_type=OrderAuditEventType.ORDER_FILLED,
                triggered_by=OrderAuditTriggerSource.SYSTEM,
            )
            await asyncio.sleep(0.05)

        # Assert: 错误计数应该从 1 开始，不会持续增长
        assert "错误 1/10" in caplog.text
        assert "错误 2/10" in caplog.text
        # 不应该出现错误 3/10 及以后，因为成功后重置了计数
        assert "错误 3/10" not in caplog.text

        # Cleanup
        await repository.close()


class TestP2_9_WorkerCancellation:
    """P2-9: Worker 取消处理测试"""

    @pytest.fixture
    def mock_db_session(self):
        """创建模拟数据库会话"""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()

        async def async_context_manager(*args, **kwargs):
            return session
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)

        session_factory = MagicMock(return_value=session)
        return session_factory

    @pytest.fixture
    def repository(self, mock_db_session):
        """创建审计日志仓库实例"""
        repo = OrderAuditLogRepository(mock_db_session)
        return repo

    @pytest.mark.asyncio
    async def test_worker_handles_cancellation_gracefully(self, repository, caplog):
        """测试 Worker 优雅处理取消信号"""
        # Arrange
        await repository.initialize(queue_size=10)

        # Act: 关闭仓库（会取消 Worker 任务）
        await repository.close()

        # Assert: Worker 应该记录停止信息
        # 注意：实际日志输出可能因 timing 问题不一定捕获，但 Worker 应该正常停止
        assert repository._worker_task is None or repository._worker_task.done()
