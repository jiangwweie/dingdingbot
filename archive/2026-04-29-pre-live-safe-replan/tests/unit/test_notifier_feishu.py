"""
Test Feishu Notifier - Phase 5

Tests for src/infrastructure/notifier_feishu.py
Covers 6 alert event types:
1. ORDER_FILLED
2. ORDER_FAILED
3. CAPITAL_PROTECTION_TRIGGERED
4. RECONCILIATION_MISMATCH
5. CONNECTION_LOST
6. DAILY_LOSS_LIMIT
"""
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.infrastructure.notifier_feishu import (
    FeishuNotifier,
    FeishuConfig,
    AlertEventType,
    AlertLevel,
    format_order_filled_message,
    format_order_failed_message,
    format_capital_protection_message,
    format_reconciliation_mismatch_message,
    format_connection_lost_message,
    format_daily_loss_limit_message,
    create_feishu_notifier,
)
from src.domain.models import (
    Order,
    Direction,
    OrderType,
    OrderRole,
    OrderStatus,
    ReconciliationReport,
    PositionMismatch,
    OrderMismatch,
)


# ============================================================
# Test Fixtures
# ============================================================

@pytest.fixture
def sample_order():
    """Create a sample Order for testing"""
    return Order(
        id="order-123",
        signal_id="signal-456",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal("0.1"),
        filled_qty=Decimal("0.1"),
        average_exec_price=Decimal("65000.00"),
        status=OrderStatus.FILLED,
        created_at=int(datetime.now().timestamp() * 1000),
        updated_at=int(datetime.now().timestamp() * 1000),
    )


@pytest.fixture
def sample_reconciliation_report():
    """Create a sample ReconciliationReport for testing"""
    return ReconciliationReport(
        symbol="BTC/USDT:USDT",
        reconciliation_time=int(datetime.now().timestamp() * 1000),
        grace_period_seconds=10,
        position_mismatches=[
            PositionMismatch(
                symbol="BTC/USDT:USDT",
                local_qty=Decimal("0.5"),
                exchange_qty=Decimal("0.52"),
                discrepancy=Decimal("0.02"),
            )
        ],
        missing_positions=[],
        order_mismatches=[
            OrderMismatch(
                order_id="order-789",
                local_status=OrderStatus.OPEN,
                exchange_status="FILLED",
            )
        ],
        orphan_orders=[],
        is_consistent=False,
        total_discrepancies=2,
        requires_attention=True,
        summary="发现 2 笔差异，需要人工介入",
    )


# ============================================================
# Test Message Formatters
# ============================================================

class TestOrderFilledMessage:
    """Test order filled message formatting"""

    def test_format_long_order_filled(self, sample_order):
        """Test formatting a LONG order filled message"""
        pnl = Decimal("150.50")
        message = format_order_filled_message(sample_order, pnl)

        assert message["msg_type"] == "interactive"
        assert message["card"]["header"]["template"] == "blue"
        assert "订单成交通知" in message["card"]["header"]["title"]["content"]
        assert "BTC/USDT:USDT" in str(message["card"]["elements"])
        assert "做多" in str(message["card"]["elements"])
        assert "0.1" in str(message["card"]["elements"])
        assert "65000.00" in str(message["card"]["elements"])

    def test_format_short_order_filled(self, sample_order):
        """Test formatting a SHORT order filled message"""
        sample_order.direction = Direction.SHORT
        pnl = Decimal("-50.00")
        message = format_order_filled_message(sample_order, pnl)

        assert "做空" in str(message["card"]["elements"])

    def test_format_order_filled_positive_pnl(self, sample_order):
        """Test formatting with positive PnL"""
        pnl = Decimal("200.00")
        message = format_order_filled_message(sample_order, pnl)

        elements_str = str(message["card"]["elements"])
        assert "+200.00" in elements_str or "200.00" in elements_str

    def test_format_order_filled_negative_pnl(self, sample_order):
        """Test formatting with negative PnL"""
        pnl = Decimal("-100.00")
        message = format_order_filled_message(sample_order, pnl)

        elements_str = str(message["card"]["elements"])
        assert "-100.00" in elements_str


class TestOrderFailedMessage:
    """Test order failed message formatting"""

    def test_format_order_failed(self, sample_order):
        """Test formatting order failed message"""
        reason = "保证金不足"
        message = format_order_failed_message(sample_order, reason)

        assert message["card"]["header"]["template"] == "orange"
        assert "订单失败告警" in message["card"]["header"]["title"]["content"]
        assert "order-123" in str(message["card"]["elements"])
        assert "保证金不足" in str(message["card"]["elements"])

    def test_format_order_failed_different_reasons(self, sample_order):
        """Test formatting with different failure reasons"""
        reasons = ["订单参数错误", "API 频率限制", "交易所拒单"]

        for reason in reasons:
            message = format_order_failed_message(sample_order, reason)
            assert reason in str(message["card"]["elements"])


class TestCapitalProtectionMessage:
    """Test capital protection message formatting"""

    def test_format_capital_protection_single_trade_limit(self):
        """Test formatting single trade loss limit"""
        reason = "SINGLE_TRADE_LOSS_LIMIT"
        details = {"message": "预计损失超限"}
        message = format_capital_protection_message(reason, details)

        assert "资金保护触发告警" in message["card"]["header"]["title"]["content"]
        assert "单笔交易损失超限" in str(message["card"]["elements"])

    def test_format_capital_protection_daily_loss_limit(self):
        """Test formatting daily loss limit"""
        reason = "DAILY_LOSS_LIMIT"
        message = format_capital_protection_message(reason)

        assert "每日亏损超限" in str(message["card"]["elements"])

    def test_format_capital_protection_insufficient_balance(self):
        """Test formatting insufficient balance"""
        reason = "INSUFFICIENT_BALANCE"
        message = format_capital_protection_message(reason)

        assert "账户余额不足" in str(message["card"]["elements"])


class TestReconciliationMismatchMessage:
    """Test reconciliation mismatch message formatting"""

    def test_format_reconciliation_mismatch(self, sample_reconciliation_report):
        """Test formatting reconciliation mismatch"""
        message = format_reconciliation_mismatch_message(sample_reconciliation_report)

        assert message["card"]["header"]["template"] == "red"
        assert "对账差异告警" in message["card"]["header"]["title"]["content"]
        assert "BTC/USDT:USDT" in str(message["card"]["elements"])
        assert "仓位不匹配" in str(message["card"]["elements"])
        assert "订单不匹配" in str(message["card"]["elements"])

    def test_format_reconciliation_empty_mismatches(self):
        """Test formatting with no mismatches"""
        report = ReconciliationReport(
            symbol="ETH/USDT:USDT",
            reconciliation_time=int(datetime.now().timestamp() * 1000),
            grace_period_seconds=10,
            position_mismatches=[],
            missing_positions=[],
            order_mismatches=[],
            orphan_orders=[],
            is_consistent=True,
            total_discrepancies=0,
            requires_attention=False,
            summary="对账一致，无差异",
        )
        message = format_reconciliation_mismatch_message(report)

        assert "对账一致" in str(message["card"]["elements"])


class TestConnectionLostMessage:
    """Test connection lost message formatting"""

    def test_format_connection_lost(self):
        """Test formatting connection lost alert"""
        message = format_connection_lost_message(
            reconnect_attempts=5,
            last_error="WebSocket connection timeout"
        )

        assert message["card"]["header"]["template"] == "red"
        assert "WebSocket 断连告警" in message["card"]["header"]["title"]["content"]
        assert "5 次" in str(message["card"]["elements"])
        assert "WebSocket connection timeout" in str(message["card"]["elements"])


class TestDailyLossLimitMessage:
    """Test daily loss limit message formatting"""

    def test_format_daily_loss_limit(self):
        """Test formatting daily loss limit alert"""
        message = format_daily_loss_limit_message(
            daily_pnl=Decimal("-500.00"),
            max_allowed_loss=Decimal("400.00"),
            balance=Decimal("10000.00"),
        )

        assert message["card"]["header"]["template"] == "red"
        assert "每日亏损超限告警" in message["card"]["header"]["title"]["content"]
        assert "-500.00" in str(message["card"]["elements"])
        assert "400.00" in str(message["card"]["elements"])
        assert "5.00%" in str(message["card"]["elements"])


# ============================================================
# Test FeishuConfig
# ============================================================

class TestFeishuConfig:
    """Test FeishuConfig class"""

    def test_default_config(self):
        """Test default configuration"""
        config = FeishuConfig()

        assert config.silent_hours_start is None
        assert config.silent_hours_end is None
        assert config.skip_silent_for_errors is True

    def test_custom_config(self):
        """Test custom configuration"""
        config = FeishuConfig(
            silent_hours_start=2,
            silent_hours_end=8,
            skip_silent_for_errors=False,
        )

        assert config.silent_hours_start == 2
        assert config.silent_hours_end == 8
        assert config.skip_silent_for_errors is False


# ============================================================
# Test FeishuNotifier
# ============================================================

class TestFeishuNotifier:
    """Test FeishuNotifier class"""

    @pytest.mark.asyncio
    async def test_send_alert_basic(self):
        """Test basic alert sending"""
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)
        mock_resp.json = AsyncMock(return_value={"StatusCode": 0})

        mock_session = AsyncMock()
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=mock_resp)

        notifier = FeishuNotifier("https://open.feishu.cn/webhook/test")
        notifier._session = mock_session

        result = await notifier.send_alert(
            event_type=AlertEventType.ORDER_FILLED,
            title="Test Alert",
            message="Test message",
            level=AlertLevel.INFO,
        )

        assert result is True
        mock_session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_alert_failure(self):
        """Test alert sending failure"""
        mock_resp = AsyncMock()
        mock_resp.status = 500
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=mock_resp)

        notifier = FeishuNotifier("https://open.feishu.cn/webhook/test")
        notifier._session = mock_session

        result = await notifier.send_alert(
            event_type=AlertEventType.ORDER_FAILED,
            title="Test Alert",
            message="Test message",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_send_alert_exception(self):
        """Test alert sending with network exception"""
        mock_session = AsyncMock()
        mock_session.closed = False

        # Create a proper async context manager that raises exception
        mock_cm = AsyncMock()
        mock_cm.__aenter__.side_effect = Exception("Network error")
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        mock_session.post = MagicMock(return_value=mock_cm)

        notifier = FeishuNotifier("https://open.feishu.cn/webhook/test")
        notifier._session = mock_session

        result = await notifier.send_alert(
            event_type=AlertEventType.CONNECTION_LOST,
            title="Test Alert",
            message="Test message",
        )

        assert result is False


# ============================================================
# Test Silent Period
# ============================================================

class TestSilentPeriod:
    """Test silent period functionality"""

    def test_no_silent_hours_configured(self):
        """Test when no silent hours configured"""
        config = FeishuConfig()
        notifier = FeishuNotifier("https://webhook.test", config=config)

        assert notifier._is_silent_period() is False

    @patch('src.infrastructure.notifier_feishu.datetime')
    def test_in_silent_period(self, mock_datetime):
        """Test during silent period"""
        # Mock current time to 3:00 AM (within 2:00-8:00)
        mock_datetime.now.return_value.hour = 3

        config = FeishuConfig(silent_hours_start=2, silent_hours_end=8)
        notifier = FeishuNotifier("https://webhook.test", config=config)

        assert notifier._is_silent_period() is True

    @patch('src.infrastructure.notifier_feishu.datetime')
    def test_outside_silent_period(self, mock_datetime):
        """Test outside silent period"""
        # Mock current time to 10:00 AM (outside 2:00-8:00)
        mock_datetime.now.return_value.hour = 10

        config = FeishuConfig(silent_hours_start=2, silent_hours_end=8)
        notifier = FeishuNotifier("https://webhook.test", config=config)

        assert notifier._is_silent_period() is False

    @patch('src.infrastructure.notifier_feishu.datetime')
    def test_cross_midnight_silent_period(self, mock_datetime):
        """Test cross-midnight silent period"""
        # Mock current time to 23:00 (within 22:00-6:00)
        mock_datetime.now.return_value.hour = 23

        config = FeishuConfig(silent_hours_start=22, silent_hours_end=6)
        notifier = FeishuNotifier("https://webhook.test", config=config)

        assert notifier._is_silent_period() is True


# ============================================================
# Test Specific Alert Methods
# ============================================================

class TestSpecificAlertMethods:
    """Test specific alert methods"""

    @pytest.mark.asyncio
    async def test_send_order_filled(self, sample_order):
        """Test send_order_filled method"""
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)
        mock_resp.json = AsyncMock(return_value={"StatusCode": 0})

        mock_session = AsyncMock()
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=mock_resp)

        notifier = FeishuNotifier("https://webhook.test")
        notifier._session = mock_session

        pnl = Decimal("100.00")
        result = await notifier.send_order_filled(sample_order, pnl)

        assert result is True

    @pytest.mark.asyncio
    async def test_send_order_failed(self, sample_order):
        """Test send_order_failed method"""
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)
        mock_resp.json = AsyncMock(return_value={"StatusCode": 0})

        mock_session = AsyncMock()
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=mock_resp)

        notifier = FeishuNotifier("https://webhook.test")
        notifier._session = mock_session

        result = await notifier.send_order_failed(sample_order, "测试失败原因")

        assert result is True

    @pytest.mark.asyncio
    async def test_send_capital_protection_triggered(self):
        """Test send_capital_protection_triggered method"""
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)
        mock_resp.json = AsyncMock(return_value={"StatusCode": 0})

        mock_session = AsyncMock()
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=mock_resp)

        notifier = FeishuNotifier("https://webhook.test")
        notifier._session = mock_session

        result = await notifier.send_capital_protection_triggered(
            reason="SINGLE_TRADE_LOSS_LIMIT",
            details={"message": "测试详情"},
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_send_reconciliation_mismatch(self, sample_reconciliation_report):
        """Test send_reconciliation_mismatch method"""
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)
        mock_resp.json = AsyncMock(return_value={"StatusCode": 0})

        mock_session = AsyncMock()
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=mock_resp)

        notifier = FeishuNotifier("https://webhook.test")
        notifier._session = mock_session

        result = await notifier.send_reconciliation_mismatch(sample_reconciliation_report)

        assert result is True

    @pytest.mark.asyncio
    async def test_send_connection_lost(self):
        """Test send_connection_lost method"""
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)
        mock_resp.json = AsyncMock(return_value={"StatusCode": 0})

        mock_session = AsyncMock()
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=mock_resp)

        notifier = FeishuNotifier("https://webhook.test")
        notifier._session = mock_session

        result = await notifier.send_connection_lost(
            reconnect_attempts=3,
            last_error="Connection timeout",
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_send_daily_loss_limit(self):
        """Test send_daily_loss_limit method"""
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)
        mock_resp.json = AsyncMock(return_value={"StatusCode": 0})

        mock_session = AsyncMock()
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=mock_resp)

        notifier = FeishuNotifier("https://webhook.test")
        notifier._session = mock_session

        result = await notifier.send_daily_loss_limit(
            daily_pnl=Decimal("-500.00"),
            max_allowed_loss=Decimal("400.00"),
            balance=Decimal("10000.00"),
        )

        assert result is True


# ============================================================
# Test Factory Function
# ============================================================

class TestFactoryFunction:
    """Test create_feishu_notifier factory function"""

    def test_create_feishu_notifier_basic(self):
        """Test basic notifier creation"""
        notifier = create_feishu_notifier("https://webhook.test")

        assert isinstance(notifier, FeishuNotifier)
        assert notifier._webhook_url == "https://webhook.test"
        assert notifier._config.silent_hours_start is None

    def test_create_feishu_notifier_with_silent_hours(self):
        """Test notifier creation with silent hours"""
        notifier = create_feishu_notifier(
            "https://webhook.test",
            silent_hours_start=2,
            silent_hours_end=8,
        )

        assert notifier._config.silent_hours_start == 2
        assert notifier._config.silent_hours_end == 8


# ============================================================
# Test Pending Alerts Flush
# ============================================================

class TestPendingAlertsFlush:
    """Test pending alerts flush functionality"""

    @pytest.mark.asyncio
    async def test_flush_pending_alerts(self):
        """Test flushing pending alerts"""
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)
        mock_resp.json = AsyncMock(return_value={"StatusCode": 0})

        mock_session = AsyncMock()
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=mock_resp)

        notifier = FeishuNotifier("https://webhook.test")
        notifier._session = mock_session
        notifier._pending_alerts = [
            {
                "event_type": AlertEventType.ORDER_FILLED,
                "title": "Test Alert 1",
                "message": "Message 1",
                "level": AlertLevel.INFO,
                "queued_at": 1234567890,
            },
            {
                "event_type": AlertEventType.ORDER_FAILED,
                "title": "Test Alert 2",
                "message": "Message 2",
                "level": AlertLevel.WARNING,
                "queued_at": 1234567891,
            },
        ]

        count = await notifier.flush_pending_alerts()

        assert count == 2
        assert len(notifier._pending_alerts) == 0

    @pytest.mark.asyncio
    async def test_flush_empty_pending_alerts(self):
        """Test flushing empty pending alerts"""
        notifier = FeishuNotifier("https://webhook.test")

        count = await notifier.flush_pending_alerts()

        assert count == 0
