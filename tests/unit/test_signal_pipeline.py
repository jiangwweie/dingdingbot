"""
Unit tests for signal_pipeline.py - Signal deduplication mechanism and dynamic tags.
"""
import pytest
import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from src.application.signal_pipeline import SignalPipeline
from src.domain.models import KlineData, Direction, TrendDirection, MtfStatus, AccountSnapshot, SignalResult
from src.domain.risk_calculator import RiskConfig
from src.domain.strategy_engine import PinbarConfig, SignalAttempt, PatternResult, FilterResult


def create_kline(
    symbol: str = "BTC/USDT:USDT",
    timeframe: str = "15m",
    timestamp: int = 1234567890000,
    open: Decimal = Decimal(100),
    high: Decimal = Decimal(100),
    low: Decimal = Decimal(100),
    close: Decimal = Decimal(100),
    volume: Decimal = Decimal(1000),
) -> KlineData:
    """Helper to create KlineData for testing."""
    return KlineData(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=timestamp,
        open=open,
        high=high,
        low=low,
        close=close,
        volume=volume,
        is_closed=True,
    )


class TestSignalDeduplication:
    """Test signal deduplication mechanism."""

    @pytest.fixture
    def pipeline(self):
        """Create a signal pipeline with mocked dependencies."""
        # Mock config manager
        mock_config_manager = MagicMock()
        mock_config_manager.user_config = MagicMock()
        mock_config_manager.user_config.active_strategies = []
        mock_config_manager.core_config = MagicMock()
        mock_config_manager.add_observer = MagicMock()

        risk_config = RiskConfig(
            max_loss_percent=Decimal("0.01"),
            max_leverage=10,
        )

        # Mock notification service
        mock_notifier = MagicMock()
        mock_notifier.send_signal = AsyncMock()

        # Mock signal repository
        mock_repository = MagicMock()
        mock_repository.save_signal = AsyncMock()
        mock_repository.save_attempt = AsyncMock()

        pipeline = SignalPipeline(
            config_manager=mock_config_manager,
            risk_config=risk_config,
            notification_service=mock_notifier,
            signal_repository=mock_repository,
        )

        # Set account snapshot for risk calculation
        pipeline.update_account_snapshot(AccountSnapshot(
            total_balance=Decimal("10000"),
            available_balance=Decimal("10000"),
            unrealized_pnl=Decimal("0"),
            positions=[],
            timestamp=1234567890000,
        ))

        return pipeline

    async def _force_signal(self, pipeline, kline, direction=Direction.LONG):
        """
        Force a signal to fire by mocking the strategy engine.
        This bypasses actual pinbar detection for testing deduplication logic.
        """
        from src.domain.strategy_engine import SignalAttempt, PatternResult

        mock_attempt = SignalAttempt(
            strategy_name="pinbar",
            pattern=PatternResult(
                strategy_name="pinbar",
                direction=direction,
                score=0.8,
                details={},
            ),
            filter_results=[],
            final_result="SIGNAL_FIRED",
        )

        # Mock _run_strategy to return a list with our forced signal
        with patch.object(pipeline, '_run_strategy', return_value=[mock_attempt]):
            await pipeline.process_kline(kline)

    @pytest.mark.asyncio
    async def test_signal_dedup_within_cooldown(self, pipeline):
        """
        Test that signals within cooldown period are deduplicated.
        First signal should be sent, second identical signal should be skipped.
        """
        kline1 = create_kline(close=Decimal("150"))
        kline2 = create_kline(close=Decimal("151"), timestamp=1234567890000 + 60000)  # 1 minute later

        # First signal should succeed
        await self._force_signal(pipeline, kline1, Direction.LONG)
        assert pipeline._notification_service.send_signal.call_count == 1

        # Second signal within cooldown should be deduplicated
        await self._force_signal(pipeline, kline2, Direction.LONG)
        assert pipeline._notification_service.send_signal.call_count == 1  # Still 1, not 2

    @pytest.mark.asyncio
    async def test_signal_dedup_different_direction(self, pipeline):
        """
        Test that LONG and SHORT signals have separate dedup keys.
        A LONG signal should not affect SHORT signal deduplication.
        """
        kline_long = create_kline(close=Decimal("150"))
        kline_short = create_kline(close=Decimal("149"))

        # LONG signal
        await self._force_signal(pipeline, kline_long, Direction.LONG)
        assert pipeline._notification_service.send_signal.call_count == 1

        # SHORT signal should NOT be deduplicated (different direction)
        await self._force_signal(pipeline, kline_short, Direction.SHORT)
        assert pipeline._notification_service.send_signal.call_count == 2

    @pytest.mark.asyncio
    async def test_signal_dedup_expires_after_cooldown(self, pipeline):
        """
        Test that signals expire after cooldown period.
        Signal fired 5 hours ago should allow new signal.
        """
        # Set cooldown to a short period for testing
        pipeline._cooldown_seconds = 60  # 1 minute

        kline1 = create_kline(close=Decimal("150"), timestamp=1234567890000)
        kline2 = create_kline(close=Decimal("151"), timestamp=1234567890000 + 120000)  # 2 minutes later

        # First signal
        await self._force_signal(pipeline, kline1, Direction.LONG)
        assert pipeline._notification_service.send_signal.call_count == 1

        # Manually set the cache to expire (simulate time passage)
        dedup_key = f"{kline1.symbol}:{kline1.timeframe}:{Direction.LONG.value}:pinbar"
        pipeline._signal_cooldown_cache[dedup_key] = 0  # Force expiry

        # Second signal after cooldown expiry should succeed
        await self._force_signal(pipeline, kline2, Direction.LONG)
        assert pipeline._notification_service.send_signal.call_count == 2

    @pytest.mark.asyncio
    async def test_signal_dedup_different_symbol(self, pipeline):
        """
        Test that different symbols have separate dedup keys.
        """
        kline_btc = create_kline(symbol="BTC/USDT:USDT", close=Decimal("150"))
        kline_eth = create_kline(symbol="ETH/USDT:USDT", close=Decimal("2200"))

        # BTC signal
        await self._force_signal(pipeline, kline_btc, Direction.LONG)
        assert pipeline._notification_service.send_signal.call_count == 1

        # ETH signal should NOT be deduplicated (different symbol)
        await self._force_signal(pipeline, kline_eth, Direction.LONG)
        assert pipeline._notification_service.send_signal.call_count == 2

    @pytest.mark.asyncio
    async def test_signal_dedup_different_timeframe(self, pipeline):
        """
        Test that different timeframes have separate dedup keys.
        """
        kline_15m = create_kline(timeframe="15m", close=Decimal("150"))
        kline_1h = create_kline(timeframe="1h", close=Decimal("151"))

        # 15m signal
        await self._force_signal(pipeline, kline_15m, Direction.LONG)
        assert pipeline._notification_service.send_signal.call_count == 1

        # 1h signal should NOT be deduplicated (different timeframe)
        await self._force_signal(pipeline, kline_1h, Direction.LONG)
        assert pipeline._notification_service.send_signal.call_count == 2

    @pytest.mark.asyncio
    async def test_dedup_key_format(self, pipeline):
        """
        Test that dedup key uses correct format: symbol:timeframe:direction:strategy_name
        """
        kline = create_kline(symbol="BTC/USDT:USDT", timeframe="15m", close=Decimal("150"))

        await self._force_signal(pipeline, kline, Direction.LONG)

        expected_key = "BTC/USDT:USDT:15m:long:pinbar"
        assert expected_key in pipeline._signal_cooldown_cache


class TestDynamicTags:
    """Test dynamic tag generation from filter results."""

    @pytest.fixture
    def pipeline(self):
        """Create a signal pipeline with mocked dependencies."""
        mock_config_manager = MagicMock()
        mock_config_manager.user_config = MagicMock()
        mock_config_manager.user_config.active_strategies = []
        mock_config_manager.core_config = MagicMock()
        mock_config_manager.add_observer = MagicMock()

        risk_config = RiskConfig(
            max_loss_percent=Decimal("0.01"),
            max_leverage=10,
        )

        mock_notifier = MagicMock()
        mock_notifier.send_signal = AsyncMock()

        mock_repository = MagicMock()
        mock_repository.save_signal = AsyncMock()
        mock_repository.save_attempt = AsyncMock()

        pipeline = SignalPipeline(
            config_manager=mock_config_manager,
            risk_config=risk_config,
            notification_service=mock_notifier,
            signal_repository=mock_repository,
        )

        pipeline.update_account_snapshot(AccountSnapshot(
            total_balance=Decimal("10000"),
            available_balance=Decimal("10000"),
            unrealized_pnl=Decimal("0"),
            positions=[],
            timestamp=1234567890000,
        ))

        return pipeline

    def test_generate_tags_from_filters_ema(self, pipeline):
        """Test EMA filter generates correct tag."""
        filter_results = [
            ("ema", FilterResult(passed=True, reason="Price is above EMA - bullish trend")),
        ]
        tags = pipeline._generate_tags_from_filters(filter_results)
        assert len(tags) == 1
        assert tags[0] == {"name": "EMA", "value": "Bullish"}

    def test_generate_tags_from_filters_ema_bearish(self, pipeline):
        """Test EMA bearish filter generates correct tag."""
        filter_results = [
            ("ema", FilterResult(passed=True, reason="Price is below EMA - bearish trend")),
        ]
        tags = pipeline._generate_tags_from_filters(filter_results)
        assert len(tags) == 1
        assert tags[0] == {"name": "EMA", "value": "Bearish"}

    def test_generate_tags_from_filters_mtf(self, pipeline):
        """Test MTF filter generates correct tag."""
        filter_results = [
            ("mtf", FilterResult(passed=True, reason="Higher timeframe confirms trend")),
        ]
        tags = pipeline._generate_tags_from_filters(filter_results)
        assert len(tags) == 1
        assert tags[0] == {"name": "MTF", "value": "Confirmed"}

    def test_generate_tags_from_filters_volume_surge(self, pipeline):
        """Test Volume Surge filter generates correct tag."""
        filter_results = [
            ("volume_surge", FilterResult(passed=True, reason="Volume surge detected")),
        ]
        tags = pipeline._generate_tags_from_filters(filter_results)
        assert len(tags) == 1
        assert tags[0] == {"name": "Volume", "value": "Surge"}

    def test_generate_tags_from_filters_multiple(self, pipeline):
        """Test multiple filters generate multiple tags."""
        filter_results = [
            ("ema", FilterResult(passed=True, reason="Price is above EMA - bullish trend")),
            ("mtf", FilterResult(passed=True, reason="Higher timeframe confirms trend")),
            ("volume_surge", FilterResult(passed=True, reason="Volume surge detected")),
        ]
        tags = pipeline._generate_tags_from_filters(filter_results)
        assert len(tags) == 3
        assert tags[0] == {"name": "EMA", "value": "Bullish"}
        assert tags[1] == {"name": "MTF", "value": "Confirmed"}
        assert tags[2] == {"name": "Volume", "value": "Surge"}

    def test_generate_tags_only_passed(self, pipeline):
        """Test that only passed filters generate tags."""
        filter_results = [
            ("ema", FilterResult(passed=True, reason="Price is above EMA - bullish trend")),
            ("mtf", FilterResult(passed=False, reason="Higher timeframe conflicts")),
        ]
        tags = pipeline._generate_tags_from_filters(filter_results)
        assert len(tags) == 1
        assert tags[0] == {"name": "EMA", "value": "Bullish"}

    def test_signal_result_contains_tags(self, pipeline):
        """Test that SignalResult contains dynamic tags."""
        kline = create_kline(close=Decimal("150"))

        # Create attempt with filter results
        mock_attempt = SignalAttempt(
            strategy_name="pinbar",
            pattern=PatternResult(
                strategy_name="pinbar",
                direction=Direction.LONG,
                score=0.8,
                details={},
            ),
            filter_results=[
                ("ema", FilterResult(passed=True, reason="Price is above EMA - bullish trend")),
                ("mtf", FilterResult(passed=True, reason="Higher timeframe confirms trend")),
            ],
            final_result="SIGNAL_FIRED",
        )

        # Manually call _calculate_risk to get SignalResult
        signal = pipeline._calculate_risk(kline, Direction.LONG, mock_attempt, "pinbar", 0.8)

        assert isinstance(signal, SignalResult)
        assert len(signal.tags) == 2
        assert {"name": "EMA", "value": "Bullish"} in signal.tags
        assert {"name": "MTF", "value": "Confirmed"} in signal.tags
