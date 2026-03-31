"""
Test Notifier - Message formatting and webhook sending.
"""
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock

from src.infrastructure.notifier import (
    format_signal_message,
    format_system_alert,
    format_cover_signal_message,
    format_opposing_signal_message,
    NotificationService,
    FeishuWebhook,
    WeComWebhook,
)
from src.domain.models import (
    SignalResult,
    Direction,
)


class TestFormatSignalMessage:
    """Test signal message formatting"""

    def test_format_long_signal(self):
        """Test formatting a LONG signal"""
        signal = SignalResult(
            symbol="BTC/USDT:USDT",
            timeframe="1h",
            direction=Direction.LONG,
            entry_price=Decimal("35000.00"),
            suggested_stop_loss=Decimal("34500.00"),
            suggested_position_size=Decimal("1.5"),
            current_leverage=5,
            tags=[{"name": "EMA", "value": "Bullish"}, {"name": "MTF", "value": "Confirmed"}],
            risk_reward_info="Risk 1% = 750 USDT",
        )

        message = format_signal_message(signal)

        assert "BTC/USDT:USDT" in message
        assert "1h" in message
        assert "🟢 多" in message or "🟢 看多" in message
        assert "35000" in message
        assert "34500" in message
        assert "EMA" in message
        assert "MTF" in message

    def test_format_short_signal(self):
        """Test formatting a SHORT signal"""
        signal = SignalResult(
            symbol="ETH/USDT:USDT",
            timeframe="4h",
            direction=Direction.SHORT,
            entry_price=Decimal("2200.00"),
            suggested_stop_loss=Decimal("2250.00"),
            suggested_position_size=Decimal("10.0"),
            current_leverage=3,
            tags=[{"name": "EMA", "value": "Bearish"}],
            risk_reward_info="Risk 1% = 500 USDT",
        )

        message = format_signal_message(signal)

        assert "🔴 空" in message or "🔴 看空" in message
        assert "EMA" in message

    def test_format_mtf_rejected(self):
        """Test formatting with MTF rejected status"""
        signal = SignalResult(
            symbol="SOL/USDT:USDT",
            timeframe="15m",
            direction=Direction.LONG,
            entry_price=Decimal("100.00"),
            suggested_stop_loss=Decimal("98.00"),
            suggested_position_size=Decimal("50.0"),
            current_leverage=2,
            tags=[{"name": "EMA", "value": "Bullish"}, {"name": "MTF", "value": "Rejected"}],
            risk_reward_info="Risk 1% = 100 USDT",
        )

        message = format_signal_message(signal)

        assert "MTF" in message and "拒绝" in message

    def test_format_mtf_disabled(self):
        """Test formatting with MTF disabled"""
        signal = SignalResult(
            symbol="BNB/USDT:USDT",
            timeframe="1d",
            direction=Direction.SHORT,
            entry_price=Decimal("350.00"),
            suggested_stop_loss=Decimal("360.00"),
            suggested_position_size=Decimal("5.0"),
            current_leverage=1,
            tags=[],
            risk_reward_info="Risk 1% = 50 USDT",
        )

        message = format_signal_message(signal)

        assert "无" in message


class TestFormatSystemAlert:
    """Test system alert formatting"""

    def test_format_basic_alert(self):
        """Test formatting basic system alert"""
        message = format_system_alert(
            error_code="C-001",
            error_message="WebSocket connection lost",
        )

        assert "【系统告警】" in message
        assert "C-001" in message
        assert "WebSocket connection lost" in message

    def test_format_alert_with_traceback(self):
        """Test formatting alert with traceback"""
        traceback_str = "Traceback (most recent call last):\n  File \"test.py\", line 10"

        message = format_system_alert(
            error_code="F-001",
            error_message="API Key has trade permission",
            traceback_str=traceback_str,
        )

        assert "堆栈摘要" in message
        assert "Traceback" in message

    def test_format_alert_traceback_truncation(self):
        """Test that long tracebacks are truncated"""
        long_traceback = "A" * 2000  # Very long traceback

        message = format_system_alert(
            error_code="E-001",
            error_message="Error",
            traceback_str=long_traceback,
        )

        assert len(message) < 1500  # Should be truncated
        assert "...(truncated)" in message


class TestFeishuWebhook:
    """Test Feishu webhook notification"""

    @pytest.mark.asyncio
    async def test_send_success(self):
        """Test successful Feishu message sending"""
        # Mock the response context manager
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)

        # Mock session.post to return the response context manager directly
        mock_session = AsyncMock()
        type(mock_session).closed = False
        # Make post() return the context manager directly (not a coroutine)
        mock_session.post = MagicMock(return_value=mock_resp)

        webhook = FeishuWebhook("https://open.feishu.cn/webhook/test")
        result = await webhook.send("Test message", session=mock_session)

        assert result is True

    @pytest.mark.asyncio
    async def test_send_failure(self):
        """Test Feishu message sending failure"""
        mock_resp = AsyncMock()
        mock_resp.status = 500
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        type(mock_session).closed = False
        # Make post() return the context manager directly (not a coroutine)
        mock_session.post = MagicMock(return_value=mock_resp)

        webhook = FeishuWebhook("https://open.feishu.cn/webhook/test")
        result = await webhook.send("Test message", session=mock_session)

        assert result is False

    @pytest.mark.asyncio
    async def test_send_exception(self):
        """Test Feishu sending with network exception"""
        mock_session = AsyncMock()
        type(mock_session).closed = False
        # Make post() raise exception when used as context manager
        async def raise_exception(*args, **kwargs):
            raise Exception("Network error")
        mock_session.post = raise_exception

        webhook = FeishuWebhook("https://open.feishu.cn/webhook/test")
        result = await webhook.send("Test message", session=mock_session)

        assert result is False


class TestWeComWebhook:
    """Test WeCom webhook notification"""

    @pytest.mark.asyncio
    async def test_send_success(self):
        """Test successful WeCom message sending"""
        # Mock the response context manager
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)

        # Mock session.post to return the response context manager directly
        mock_session = AsyncMock()
        type(mock_session).closed = False
        # Make post() return the context manager directly (not a coroutine)
        mock_session.post = MagicMock(return_value=mock_resp)

        webhook = WeComWebhook("https://qyapi.weixin.qq.com/cgi/webhook/test")
        result = await webhook.send("Test message", session=mock_session)

        assert result is True


class TestNotificationService:
    """Test NotificationService orchestration"""

    def test_setup_channels_feishu(self):
        """Test setting up Feishu channel"""
        service = NotificationService()
        service.setup_channels([
            {"type": "feishu", "webhook_url": "https://open.feishu.cn/webhook/test"}
        ])

        assert len(service._channels) == 1
        assert isinstance(service._channels[0], FeishuWebhook)

    def test_setup_channels_wecom(self):
        """Test setting up WeCom channel"""
        service = NotificationService()
        service.setup_channels([
            {"type": "wecom", "webhook_url": "https://qyapi.weixin.qq.com/cgi/webhook/test"}
        ])

        assert len(service._channels) == 1
        assert isinstance(service._channels[0], WeComWebhook)

    def test_setup_channels_multiple(self):
        """Test setting up multiple channels"""
        service = NotificationService()
        service.setup_channels([
            {"type": "feishu", "webhook_url": "https://open.feishu.cn/webhook/test1"},
            {"type": "wecom", "webhook_url": "https://qyapi.weixin.qq.com/cgi/webhook/test2"},
            {"type": "feishu", "webhook_url": "https://open.feishu.cn/webhook/test3"},
        ])

        assert len(service._channels) == 3

    def test_setup_channels_invalid(self, caplog):
        """Test handling of invalid channel config"""
        service = NotificationService()
        service.setup_channels([
            {"type": "invalid_type", "webhook_url": "https://example.com"},
            {"type": "feishu"},  # Missing webhook_url
        ])

        assert len(service._channels) == 0
        assert "Invalid channel config" in caplog.text or "Unknown channel type" in caplog.text

    @pytest.mark.asyncio
    async def test_broadcast_no_channels(self, caplog):
        """Test broadcasting with no channels configured"""
        service = NotificationService()
        await service._broadcast("Test message")

        assert "No notification channels configured" in caplog.text

    @pytest.mark.asyncio
    async def test_send_signal(self):
        """Test sending signal notification"""
        service = NotificationService()

        # Create mock session
        mock_session = AsyncMock()
        mock_session.closed = False
        service._session = mock_session

        # Mock channel
        mock_channel = AsyncMock()
        mock_channel.send.return_value = True
        service._channels = [mock_channel]

        signal = SignalResult(
            symbol="BTC/USDT:USDT",
            timeframe="1h",
            direction=Direction.LONG,
            entry_price=Decimal("35000"),
            suggested_stop_loss=Decimal("34500"),
            suggested_position_size=Decimal("1.0"),
            current_leverage=1,
            tags=[{"name": "EMA", "value": "Bullish"}, {"name": "MTF", "value": "Confirmed"}],
            risk_reward_info="Risk 1% = 500 USDT",
        )

        await service.send_signal(signal)

        # Verify send was called with session parameter
        mock_channel.send.assert_called_once()
        call_args = mock_channel.send.call_args
        assert call_args.kwargs.get('session') == mock_session

    @pytest.mark.asyncio
    async def test_send_system_alert(self):
        """Test sending system alert"""
        service = NotificationService()

        # Create mock session
        mock_session = AsyncMock()
        mock_session.closed = False
        service._session = mock_session

        # Mock channel
        mock_channel = AsyncMock()
        mock_channel.send.return_value = True
        service._channels = [mock_channel]

        await service.send_system_alert(
            error_code="C-001",
            error_message="Connection lost",
        )

        mock_channel.send.assert_called_once()


class TestFormatCoverSignalMessage:
    """Test cover signal message formatting"""

    def test_format_cover_signal_basic(self):
        """Test formatting a cover signal message"""
        signal = SignalResult(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            direction=Direction.LONG,
            entry_price=Decimal("65200.00"),
            suggested_stop_loss=Decimal("64700.00"),
            suggested_position_size=Decimal("0.15"),
            current_leverage=10,
            tags=[{"name": "EMA", "value": "Bullish"}, {"name": "MTF", "value": "Confirmed"}],
            risk_reward_info="Risk 1% = 300 USDT",
            score=0.85,
        )

        superseded_signal = {
            "signal_id": "signal-123",
            "score": 0.72,
        }

        message = format_cover_signal_message(signal, superseded_signal)

        assert "【信号覆盖" in message
        assert "BTC/USDT:USDT" in message
        assert "15m" in message
        assert "🟢 多" in message or "🟢 看多" in message
        assert "65200" in message
        assert "（更新）" in message
        assert "评分" in message
        assert "覆盖原因" in message

    def test_format_cover_signal_score_decrease(self):
        """Test cover signal with different score improvement"""
        signal = SignalResult(
            symbol="ETH/USDT:USDT",
            timeframe="1h",
            direction=Direction.SHORT,
            entry_price=Decimal("2200.00"),
            suggested_stop_loss=Decimal("2250.00"),
            suggested_position_size=Decimal("1.0"),
            current_leverage=5,
            tags=[{"name": "EMA", "value": "Bearish"}],
            risk_reward_info="Risk 1% = 100 USDT",
            score=0.90,
        )

        superseded_signal = {
            "signal_id": "signal-456",
            "score": 0.60,
        }

        message = format_cover_signal_message(signal, superseded_signal)

        assert "评分" in message


class TestFormatOpposingSignalMessage:
    """Test opposing signal message formatting"""

    def test_format_opposing_signal_basic(self):
        """Test formatting an opposing signal message"""
        signal = SignalResult(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            direction=Direction.SHORT,
            entry_price=Decimal("64800.00"),
            suggested_stop_loss=Decimal("65300.00"),
            suggested_position_size=Decimal("0.15"),
            current_leverage=10,
            tags=[{"name": "EMA", "value": "Bearish"}],
            risk_reward_info="Risk 1% = 300 USDT",
            score=0.78,
        )

        opposing_signal = {
            "direction": "LONG",
            "score": 0.82,
        }

        message = format_opposing_signal_message(signal, opposing_signal)

        assert "反向信号" in message
        assert "空" in message
        assert "相反" in message
        assert "分歧" in message
        assert "当前" in message
        assert "反向" in message

    def test_format_opposing_signal_lower_score(self):
        """Test opposing signal with lower score"""
        signal = SignalResult(
            symbol="ETH/USDT:USDT",
            timeframe="1h",
            direction=Direction.LONG,
            entry_price=Decimal("2200.00"),
            suggested_stop_loss=Decimal("2150.00"),
            suggested_position_size=Decimal("1.0"),
            current_leverage=5,
            tags=[],
            risk_reward_info="Risk 1% = 100 USDT",
            score=0.85,
        )

        opposing_signal = {
            "direction": "SHORT",
            "score": 0.70,
        }

        message = format_opposing_signal_message(signal, opposing_signal)

        assert "多" in message
        assert "当前" in message
        assert "反向" in message


class TestFormatSignalMessageWithOptionalParams:
    """Test format_signal_message with optional parameters"""

    def test_format_signal_standard(self):
        """Test standard signal formatting (no optional params)"""
        signal = SignalResult(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            direction=Direction.LONG,
            entry_price=Decimal("65000.00"),
            suggested_stop_loss=Decimal("64500.00"),
            suggested_position_size=Decimal("0.15"),
            current_leverage=10,
            tags=[{"name": "EMA", "value": "Bullish"}],
            risk_reward_info="Risk 1% = 300 USDT",
            score=0.75,
        )

        message = format_signal_message(signal)

        assert "普通信号" in message or "交易信号" in message
        assert "覆盖" not in message
        assert "反向" not in message

    def test_format_signal_with_superseded(self):
        """Test signal formatting with superseded_signal param"""
        signal = SignalResult(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            direction=Direction.LONG,
            entry_price=Decimal("65200.00"),
            suggested_stop_loss=Decimal("64700.00"),
            suggested_position_size=Decimal("0.15"),
            current_leverage=10,
            tags=[],
            risk_reward_info="Risk 1% = 300 USDT",
            score=0.85,
        )

        superseded_signal = {
            "signal_id": "signal-789",
            "score": 0.70,
        }

        message = format_signal_message(signal, superseded_signal=superseded_signal)

        assert "【信号覆盖" in message
        assert "评分" in message
        assert "覆盖原因" in message

    def test_format_signal_with_opposing(self):
        """Test signal formatting with opposing_signal param"""
        signal = SignalResult(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            direction=Direction.LONG,
            entry_price=Decimal("65000.00"),
            suggested_stop_loss=Decimal("64500.00"),
            suggested_position_size=Decimal("0.15"),
            current_leverage=10,
            tags=[],
            risk_reward_info="Risk 1% = 300 USDT",
            score=0.75,
        )

        opposing_signal = {
            "direction": "SHORT",
            "score": 0.80,
        }

        message = format_signal_message(signal, opposing_signal=opposing_signal)

        assert "反向信号" in message or "反向" in message

    def test_format_signal_with_both(self):
        """Test signal formatting with both superseded and opposing"""
        signal = SignalResult(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            direction=Direction.LONG,
            entry_price=Decimal("65200.00"),
            suggested_stop_loss=Decimal("64700.00"),
            suggested_position_size=Decimal("0.15"),
            current_leverage=10,
            tags=[],
            risk_reward_info="Risk 1% = 300 USDT",
            score=0.85,
        )

        superseded_signal = {
            "signal_id": "signal-old",
            "score": 0.70,
        }

        opposing_signal = {
            "direction": "SHORT",
            "score": 0.80,
        }

        # When both are provided, superseded takes precedence
        message = format_signal_message(signal, superseded_signal=superseded_signal, opposing_signal=opposing_signal)

        assert "【信号覆盖" in message
