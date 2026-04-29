"""
Test OrderAuditLogger Type Validation - T006

测试审计日志器的类型校验功能：
1. 有效枚举类型传入
2. 字符串自动转换为枚举
3. 无效 event_type 抛出异常
4. 无效 triggered_by 抛出异常
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal

from src.application.order_audit_logger import OrderAuditLogger
from src.domain.models import (
    OrderAuditEventType,
    OrderAuditTriggerSource,
)


class TestOrderAuditLoggerTypeValidation:
    """测试 OrderAuditLogger 类型校验功能"""

    @pytest.fixture
    def mock_repository(self):
        """创建模拟仓库"""
        repo = MagicMock()
        repo.log = AsyncMock(return_value="audit_test123")
        repo.log_status_change = AsyncMock(return_value="audit_test123")
        return repo

    @pytest.fixture
    def audit_logger(self, mock_repository):
        """创建审计日志器实例"""
        return OrderAuditLogger(mock_repository)

    @pytest.mark.asyncio
    async def test_valid_enum_types(self, audit_logger, mock_repository):
        """测试传入有效枚举类型"""
        # Arrange
        order_id = "order_123"
        signal_id = "signal_456"
        old_status = "CREATED"
        new_status = "SUBMITTED"
        event_type = OrderAuditEventType.ORDER_SUBMITTED
        triggered_by = OrderAuditTriggerSource.SYSTEM

        # Act
        result = await audit_logger.log(
            order_id=order_id,
            new_status=new_status,
            event_type=event_type,
            triggered_by=triggered_by,
            signal_id=signal_id,
            old_status=old_status,
        )

        # Assert
        assert result == "audit_test123"
        mock_repository.log.assert_called_once()
        call_args = mock_repository.log.call_args
        assert call_args.kwargs["event_type"] == OrderAuditEventType.ORDER_SUBMITTED
        assert call_args.kwargs["triggered_by"] == OrderAuditTriggerSource.SYSTEM

    @pytest.mark.asyncio
    async def test_string_to_enum_conversion(self, audit_logger, mock_repository):
        """测试字符串自动转换为枚举"""
        # Arrange
        order_id = "order_123"
        signal_id = "signal_456"
        old_status = "CREATED"
        new_status = "SUBMITTED"
        # 传入字符串而非枚举
        event_type = "ORDER_SUBMITTED"
        triggered_by = "SYSTEM"

        # Act
        result = await audit_logger.log(
            order_id=order_id,
            new_status=new_status,
            event_type=event_type,
            triggered_by=triggered_by,
            signal_id=signal_id,
            old_status=old_status,
        )

        # Assert
        assert result == "audit_test123"
        mock_repository.log.assert_called_once()
        call_args = mock_repository.log.call_args
        # 验证字符串已被转换为枚举
        assert call_args.kwargs["event_type"] == OrderAuditEventType.ORDER_SUBMITTED
        assert call_args.kwargs["triggered_by"] == OrderAuditTriggerSource.SYSTEM

    @pytest.mark.asyncio
    async def test_invalid_event_type(self, audit_logger, mock_repository):
        """测试无效 event_type 抛出异常"""
        # Arrange
        order_id = "order_123"
        new_status = "SUBMITTED"
        # 无效的 event_type
        event_type = "INVALID_EVENT_TYPE"
        triggered_by = OrderAuditTriggerSource.SYSTEM

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            await audit_logger.log(
                order_id=order_id,
                new_status=new_status,
                event_type=event_type,
                triggered_by=triggered_by,
            )

        assert "Invalid event_type" in str(exc_info.value)
        assert "INVALID_EVENT_TYPE" in str(exc_info.value)
        # 验证 repository 未被调用
        mock_repository.log.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_triggered_by(self, audit_logger, mock_repository):
        """测试无效 triggered_by 抛出异常"""
        # Arrange
        order_id = "order_123"
        new_status = "SUBMITTED"
        event_type = OrderAuditEventType.ORDER_SUBMITTED
        # 无效的 triggered_by
        triggered_by = "INVALID_TRIGGER_SOURCE"

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            await audit_logger.log(
                order_id=order_id,
                new_status=new_status,
                event_type=event_type,
                triggered_by=triggered_by,
            )

        assert "Invalid triggered_by" in str(exc_info.value)
        assert "INVALID_TRIGGER_SOURCE" in str(exc_info.value)
        # 验证 repository 未被调用
        mock_repository.log.assert_not_called()


class TestOrderAuditLoggerLogStatusChange:
    """测试 log_status_change 方法的类型校验"""

    @pytest.fixture
    def mock_repository(self):
        """创建模拟仓库"""
        repo = MagicMock()
        repo.log = AsyncMock(return_value="audit_test123")
        repo.log_status_change = AsyncMock(return_value="audit_test123")
        return repo

    @pytest.fixture
    def audit_logger(self, mock_repository):
        """创建审计日志器实例"""
        return OrderAuditLogger(mock_repository)

    @pytest.mark.asyncio
    async def test_log_status_change_valid_enums(self, audit_logger, mock_repository):
        """测试 log_status_change 传入有效枚举"""
        # Arrange
        order_id = "order_123"
        signal_id = "signal_456"
        old_status = "CREATED"
        new_status = "SUBMITTED"
        event_type = OrderAuditEventType.ORDER_SUBMITTED
        triggered_by = OrderAuditTriggerSource.SYSTEM

        # Act
        result = await audit_logger.log_status_change(
            order_id=order_id,
            signal_id=signal_id,
            old_status=old_status,
            new_status=new_status,
            event_type=event_type,
            triggered_by=triggered_by,
        )

        # Assert
        assert result == "audit_test123"

    @pytest.mark.asyncio
    async def test_log_status_change_string_conversion(self, audit_logger, mock_repository):
        """测试 log_status_change 字符串自动转换"""
        # Arrange
        order_id = "order_123"
        signal_id = "signal_456"
        old_status = "CREATED"
        new_status = "SUBMITTED"
        # 传入字符串
        event_type = "ORDER_SUBMITTED"
        triggered_by = "SYSTEM"

        # Act
        result = await audit_logger.log_status_change(
            order_id=order_id,
            signal_id=signal_id,
            old_status=old_status,
            new_status=new_status,
            event_type=event_type,
            triggered_by=triggered_by,
        )

        # Assert
        assert result == "audit_test123"

    @pytest.mark.asyncio
    async def test_log_status_change_invalid_event_type(self, audit_logger, mock_repository):
        """测试 log_status_change 无效 event_type"""
        # Arrange
        order_id = "order_123"
        signal_id = "signal_456"
        old_status = "CREATED"
        new_status = "SUBMITTED"
        event_type = "INVALID_EVENT"
        triggered_by = OrderAuditTriggerSource.SYSTEM

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            await audit_logger.log_status_change(
                order_id=order_id,
                signal_id=signal_id,
                old_status=old_status,
                new_status=new_status,
                event_type=event_type,
                triggered_by=triggered_by,
            )

        assert "Invalid event_type" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_log_status_change_invalid_triggered_by(self, audit_logger, mock_repository):
        """测试 log_status_change 无效 triggered_by"""
        # Arrange
        order_id = "order_123"
        signal_id = "signal_456"
        old_status = "CREATED"
        new_status = "SUBMITTED"
        event_type = OrderAuditEventType.ORDER_SUBMITTED
        triggered_by = "INVALID_SOURCE"

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            await audit_logger.log_status_change(
                order_id=order_id,
                signal_id=signal_id,
                old_status=old_status,
                new_status=new_status,
                event_type=event_type,
                triggered_by=triggered_by,
            )

        assert "Invalid triggered_by" in str(exc_info.value)


class TestOrderAuditLoggerHelperMethods:
    """测试类型校验辅助方法"""

    @pytest.fixture
    def mock_repository(self):
        """创建模拟仓库"""
        repo = MagicMock()
        repo.log = AsyncMock(return_value="audit_test123")
        return repo

    @pytest.fixture
    def audit_logger(self, mock_repository):
        """创建审计日志器实例"""
        return OrderAuditLogger(mock_repository)

    def test_validate_event_type_already_enum(self, audit_logger):
        """测试传入已是枚举类型的情况"""
        # Arrange
        event_type = OrderAuditEventType.ORDER_CREATED

        # Act
        result = audit_logger._validate_event_type(event_type)

        # Assert
        assert result == OrderAuditEventType.ORDER_CREATED
        assert isinstance(result, OrderAuditEventType)

    def test_validate_event_type_string_valid(self, audit_logger):
        """测试传入有效字符串"""
        # Arrange
        event_type = "ORDER_CREATED"

        # Act
        result = audit_logger._validate_event_type(event_type)

        # Assert
        assert result == OrderAuditEventType.ORDER_CREATED
        assert isinstance(result, OrderAuditEventType)

    def test_validate_event_type_string_invalid(self, audit_logger):
        """测试传入无效字符串"""
        # Arrange
        event_type = "NOT_A_REAL_EVENT"

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            audit_logger._validate_event_type(event_type)

        assert "Invalid event_type" in str(exc_info.value)

    def test_validate_trigger_source_already_enum(self, audit_logger):
        """测试传入已是枚举类型的触发来源"""
        # Arrange
        triggered_by = OrderAuditTriggerSource.USER

        # Act
        result = audit_logger._validate_trigger_source(triggered_by)

        # Assert
        assert result == OrderAuditTriggerSource.USER
        assert isinstance(result, OrderAuditTriggerSource)

    def test_validate_trigger_source_string_valid(self, audit_logger):
        """测试传入有效字符串触发来源"""
        # Arrange
        triggered_by = "USER"

        # Act
        result = audit_logger._validate_trigger_source(triggered_by)

        # Assert
        assert result == OrderAuditTriggerSource.USER
        assert isinstance(result, OrderAuditTriggerSource)

    def test_validate_trigger_source_string_invalid(self, audit_logger):
        """测试传入无效字符串触发来源"""
        # Arrange
        triggered_by = "NOT_A_REAL_SOURCE"

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            audit_logger._validate_trigger_source(triggered_by)

        assert "Invalid triggered_by" in str(exc_info.value)

    def test_validate_event_type_none(self, audit_logger):
        """测试传入 None 值"""
        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            audit_logger._validate_event_type(None)

        assert "Invalid event_type" in str(exc_info.value)

    def test_validate_trigger_source_none(self, audit_logger):
        """测试传入 None 值"""
        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            audit_logger._validate_trigger_source(None)

        assert "Invalid triggered_by" in str(exc_info.value)
