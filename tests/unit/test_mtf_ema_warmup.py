"""
Unit tests for MTF EMA warmup logic in signal_pipeline.py.

Tests verify that:
1. _mtf_ema_indicators are correctly initialized after warmup
2. EMA is_ready = True after warmup with sufficient K-lines
3. _get_closest_higher_tf_trends returns valid trends after warmup
"""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch, AsyncMock

from src.application.signal_pipeline import SignalPipeline
from src.domain.models import KlineData, Direction, TrendDirection, AccountSnapshot
from src.domain.risk_calculator import RiskConfig
from src.domain.indicators import EMACalculator


def create_kline(
    symbol: str = "BTC/USDT:USDT",
    timeframe: str = "15m",
    timestamp: int = 1234567890000,
    open: Decimal = Decimal("100"),
    high: Decimal = Decimal("100"),
    low: Decimal = Decimal("100"),
    close: Decimal = Decimal("100"),
    volume: Decimal = Decimal("1000"),
    is_closed: bool = True,
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
        is_closed=is_closed,
    )


def create_mock_config_manager():
    """Create a mock ConfigManager for testing."""
    mock_config_manager = MagicMock()

    # Mock user_config with required fields
    mock_user_config = MagicMock()
    mock_user_config.active_strategies = []
    mock_user_config.mtf_ema_period = 60
    mock_user_config.mtf_mapping = {
        "15m": "1h",
        "1h": "4h",
        "4h": "1d",
        "1d": "1w",
    }
    mock_config_manager.user_config = mock_user_config

    # Mock core_config with required fields
    mock_core_config = MagicMock()
    mock_core_config.signal_pipeline.queue.batch_size = 10
    mock_core_config.signal_pipeline.queue.flush_interval = 5.0
    mock_core_config.signal_pipeline.queue.max_queue_size = 1000
    mock_config_manager.core_config = mock_core_config

    # Mock observer registration
    mock_config_manager.add_observer = MagicMock()

    return mock_config_manager


class TestMtfEmaWarmup:
    """Test MTF EMA warmup logic."""

    @pytest.fixture
    def mock_config_manager(self):
        """Create a mock ConfigManager."""
        return create_mock_config_manager()

    @pytest.fixture
    def pipeline(self, mock_config_manager):
        """Create a SignalPipeline with mocked dependencies."""
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

    def test_warmup_initializes_mtf_ema_indicators(self, pipeline, mock_config_manager):
        """
        Test that warmup correctly initializes _mtf_ema_indicators.

        When K-line history is added for higher timeframes (1h, 4h, 1d),
        the warmup process should create EMACalculator instances for each.
        """
        # Simulate adding K-line history for higher timeframes
        # This mimics what happens during real operation

        # Add 1h K-line history (more than EMA period of 60)
        symbol = "BTC/USDT:USDT"
        one_hour_klines = [
            create_kline(
                symbol=symbol,
                timeframe="1h",
                timestamp=1234567890000 + i * 3600000,
                close=Decimal("100") + Decimal(i) * Decimal("0.1"),
            )
            for i in range(70)  # 70 K-lines, enough for EMA warmup
        ]

        # Add 4h K-line history
        four_hour_klines = [
            create_kline(
                symbol=symbol,
                timeframe="4h",
                timestamp=1234567890000 + i * 14400000,
                close=Decimal("100") + Decimal(i) * Decimal("0.2"),
            )
            for i in range(70)
        ]

        # Manually populate _kline_history (simulating real operation)
        pipeline._kline_history[f"{symbol}:1h"] = one_hour_klines
        pipeline._kline_history[f"{symbol}:4h"] = four_hour_klines

        # Trigger warmup by rebuilding the runner
        pipeline._build_and_warmup_runner()

        # Verify _mtf_ema_indicators were initialized for higher timeframes
        assert f"{symbol}:1h" in pipeline._mtf_ema_indicators
        assert f"{symbol}:4h" in pipeline._mtf_ema_indicators

        # Verify they are EMACalculator instances
        assert isinstance(pipeline._mtf_ema_indicators[f"{symbol}:1h"], EMACalculator)
        assert isinstance(pipeline._mtf_ema_indicators[f"{symbol}:4h"], EMACalculator)

        # Verify EMA period is correct (from config)
        assert pipeline._mtf_ema_indicators[f"{symbol}:1h"].period == 60
        assert pipeline._mtf_ema_indicators[f"{symbol}:4h"].period == 60

    def test_mtf_ema_ready_after_warmup(self, pipeline, mock_config_manager):
        """
        Test that EMA is_ready = True after warmup with sufficient K-lines.

        EMACalculator requires `period` number of prices to be ready.
        With period=60 and 70 K-lines, EMA should be ready after warmup.
        """
        symbol = "BTC/USDT:USDT"

        # Add 1h K-line history (more than EMA period of 60)
        one_hour_klines = [
            create_kline(
                symbol=symbol,
                timeframe="1h",
                timestamp=1234567890000 + i * 3600000,
                close=Decimal("100") + Decimal(i) * Decimal("0.1"),
            )
            for i in range(70)
        ]

        # Manually populate _kline_history
        pipeline._kline_history[f"{symbol}:1h"] = one_hour_klines

        # Trigger warmup
        pipeline._build_and_warmup_runner()

        # Verify EMA is ready after warmup
        ema_key = f"{symbol}:1h"
        assert ema_key in pipeline._mtf_ema_indicators
        assert pipeline._mtf_ema_indicators[ema_key].is_ready is True

        # Verify EMA has a valid value
        assert pipeline._mtf_ema_indicators[ema_key].value is not None
        assert isinstance(pipeline._mtf_ema_indicators[ema_key].value, Decimal)

    def test_mtf_ema_not_ready_with_insufficient_data(self, pipeline, mock_config_manager):
        """
        Test that EMA is_ready = False when insufficient K-lines are available.

        With period=60 and only 30 K-lines, EMA should NOT be ready.
        """
        symbol = "BTC/USDT:USDT"

        # Add 1h K-line history (LESS than EMA period of 60)
        one_hour_klines = [
            create_kline(
                symbol=symbol,
                timeframe="1h",
                timestamp=1234567890000 + i * 3600000,
                close=Decimal("100") + Decimal(i) * Decimal("0.1"),
            )
            for i in range(30)  # Only 30 K-lines, not enough for EMA
        ]

        # Manually populate _kline_history
        pipeline._kline_history[f"{symbol}:1h"] = one_hour_klines

        # Trigger warmup
        pipeline._build_and_warmup_runner()

        # Verify EMA is NOT ready
        ema_key = f"{symbol}:1h"
        assert ema_key in pipeline._mtf_ema_indicators
        assert pipeline._mtf_ema_indicators[ema_key].is_ready is False

        # Verify EMA has no value yet
        assert pipeline._mtf_ema_indicators[ema_key].value is None

    def test_get_closest_higher_tf_trends_returns_trend_after_warmup(self, pipeline, mock_config_manager):
        """
        Test that _get_closest_higher_tf_trends returns valid trends after warmup.

        After MTF EMA warmup, calling _get_closest_higher_tf_trends should
        return the calculated trend direction based on price vs EMA.
        """
        symbol = "BTC/USDT:USDT"
        base_timestamp = 1234567890000

        # Setup: Add 15m kline that will trigger the MTF check
        kline_15m = create_kline(
            symbol=symbol,
            timeframe="15m",
            timestamp=base_timestamp,
            close=Decimal("105"),  # Price above EMA will be bullish
        )

        # Add 1h K-line history for MTF analysis
        # Last closed 1h kline should have close price > EMA (bullish)
        one_hour_klines = [
            create_kline(
                symbol=symbol,
                timeframe="1h",
                timestamp=base_timestamp - (70 - i) * 3600000,
                close=Decimal("100") + Decimal(i) * Decimal("0.5"),
            )
            for i in range(70)
        ]

        # Manually populate _kline_history
        pipeline._kline_history[f"{symbol}:1h"] = one_hour_klines

        # Trigger warmup to initialize MTF EMAs
        pipeline._build_and_warmup_runner()

        # Call _get_closest_higher_tf_trends
        higher_tf_trends = pipeline._get_closest_higher_tf_trends(kline_15m)

        # Verify trends are returned
        assert "1h" in higher_tf_trends
        assert isinstance(higher_tf_trends["1h"], TrendDirection)

        # Since price (105) > EMA (should be around 100-103), trend should be BULLISH
        assert higher_tf_trends["1h"] == TrendDirection.BULLISH

    def test_get_closest_higher_tf_trends_bearish(self, pipeline, mock_config_manager):
        """
        Test that _get_closest_higher_tf_trends returns BEARISH when price < EMA.
        """
        symbol = "BTC/USDT:USDT"
        base_timestamp = 1234567890000

        # Setup: Add 15m kline
        kline_15m = create_kline(
            symbol=symbol,
            timeframe="15m",
            timestamp=base_timestamp,
            close=Decimal("95"),  # Price below EMA will be bearish
        )

        # Add 1h K-line history with declining prices
        one_hour_klines = [
            create_kline(
                symbol=symbol,
                timeframe="1h",
                timestamp=base_timestamp - (70 - i) * 3600000,
                close=Decimal("100") - Decimal(i) * Decimal("0.5"),
            )
            for i in range(70)
        ]

        # Manually populate _kline_history
        pipeline._kline_history[f"{symbol}:1h"] = one_hour_klines

        # Trigger warmup
        pipeline._build_and_warmup_runner()

        # Mock get_last_closed_kline_index to return the last kline
        with patch('src.application.signal_pipeline.get_last_closed_kline_index', return_value=69):
            # Call _get_closest_higher_tf_trends
            higher_tf_trends = pipeline._get_closest_higher_tf_trends(kline_15m)

            # Verify trend is BEARISH (price < EMA)
            assert "1h" in higher_tf_trends
            assert higher_tf_trends["1h"] == TrendDirection.BEARISH

    def test_get_closest_higher_tf_trends_no_data(self, pipeline, mock_config_manager):
        """
        Test that _get_closest_higher_tf_trends returns empty dict when no data available.
        """
        symbol = "BTC/USDT:USDT"
        base_timestamp = 1234567890000

        kline_15m = create_kline(
            symbol=symbol,
            timeframe="15m",
            timestamp=base_timestamp,
            close=Decimal("100"),
        )

        # Don't add any 1h history

        # Call _get_closest_higher_tf_trends with empty history
        higher_tf_trends = pipeline._get_closest_higher_tf_trends(kline_15m)

        # Should return empty dict
        assert higher_tf_trends == {}

    def test_warmup_multiple_symbols(self, pipeline, mock_config_manager):
        """
        Test that warmup correctly handles multiple symbols.
        """
        symbols = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]

        # Add K-line history for each symbol
        for sym in symbols:
            one_hour_klines = [
                create_kline(
                    symbol=sym,
                    timeframe="1h",
                    timestamp=1234567890000 + i * 3600000,
                    close=Decimal("100") + Decimal(i) * Decimal("0.1"),
                )
                for i in range(70)
            ]
            pipeline._kline_history[f"{sym}:1h"] = one_hour_klines

        # Trigger warmup
        pipeline._build_and_warmup_runner()

        # Verify all symbols have MTF EMA initialized
        for sym in symbols:
            ema_key = f"{sym}:1h"
            assert ema_key in pipeline._mtf_ema_indicators
            assert pipeline._mtf_ema_indicators[ema_key].is_ready is True

    def test_warmup_excludes_current_kline(self, pipeline, mock_config_manager):
        """
        Test that warmup excludes the currently running (incomplete) kline.

        The warmup logic uses history[:-1] to exclude the current kline,
        ensuring only completed data is used for EMA initialization.
        """
        symbol = "BTC/USDT:USDT"

        # Add 61 K-lines (60 for warmup + 1 current)
        one_hour_klines = [
            create_kline(
                symbol=symbol,
                timeframe="1h",
                timestamp=1234567890000 + i * 3600000,
                close=Decimal("100") + Decimal(i) * Decimal("0.1"),
                is_closed=(i < 60),  # Last one is not closed
            )
            for i in range(61)
        ]

        pipeline._kline_history[f"{symbol}:1h"] = one_hour_klines

        # Trigger warmup (should use history[:-1])
        pipeline._build_and_warmup_runner()

        # Verify EMA is ready (60 closed K-lines should be enough)
        ema_key = f"{symbol}:1h"
        assert pipeline._mtf_ema_indicators[ema_key].is_ready is True

    def test_mtf_ema_indicators_shared_across_calls(self, pipeline, mock_config_manager):
        """
        Test that _mtf_ema_indicators are reused across multiple calls.

        The same EMA instance should be used for efficiency,
        not recreated on every _get_closest_higher_tf_trends call.
        """
        symbol = "BTC/USDT:USDT"

        # Add 1h K-line history
        one_hour_klines = [
            create_kline(
                symbol=symbol,
                timeframe="1h",
                timestamp=1234567890000 + i * 3600000,
                close=Decimal("100") + Decimal(i) * Decimal("0.1"),
            )
            for i in range(70)
        ]
        pipeline._kline_history[f"{symbol}:1h"] = one_hour_klines

        # Trigger warmup
        pipeline._build_and_warmup_runner()

        # Get reference to the EMA instance
        ema_key = f"{symbol}:1h"
        ema_ref1 = pipeline._mtf_ema_indicators[ema_key]

        # Create a new kline and call _get_closest_higher_tf_trends
        kline_15m = create_kline(
            symbol=symbol,
            timeframe="15m",
            timestamp=1234567890000 + 70 * 3600000,
            close=Decimal("105"),
        )

        # Mock get_last_closed_kline_index for consistent results
        with patch('src.application.signal_pipeline.get_last_closed_kline_index', return_value=69):
            pipeline._get_closest_higher_tf_trends(kline_15m)

        # Verify the same EMA instance is used (not recreated)
        ema_ref2 = pipeline._mtf_ema_indicators[ema_key]
        assert ema_ref1 is ema_ref2


class TestMtfEmaWarmupIntegration:
    """Integration tests for MTF EMA warmup with process_kline flow."""

    @pytest.fixture
    def pipeline_with_history(self):
        """Create a pipeline with pre-populated K-line history."""
        mock_config_manager = create_mock_config_manager()

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

        # Pre-populate with 1h history
        symbol = "BTC/USDT:USDT"
        one_hour_klines = [
            create_kline(
                symbol=symbol,
                timeframe="1h",
                timestamp=1234567890000 + i * 3600000,
                close=Decimal("100") + Decimal(i) * Decimal("0.1"),
            )
            for i in range(70)
        ]
        pipeline._kline_history[f"{symbol}:1h"] = one_hour_klines

        # Trigger warmup
        pipeline._build_and_warmup_runner()

        return pipeline

    @pytest.mark.asyncio
    async def test_process_kline_mtf_ema_persists(self, pipeline_with_history):
        """
        Test that MTF EMA state persists across multiple process_kline calls.
        """
        symbol = "BTC/USDT:USDT"

        # Verify EMA is ready before processing
        assert pipeline_with_history._mtf_ema_indicators[f"{symbol}:1h"].is_ready is True

        # Get initial EMA value
        initial_ema = pipeline_with_history._mtf_ema_indicators[f"{symbol}:1h"].value

        # Process a new 15m kline (which triggers MTF check)
        kline = create_kline(
            symbol=symbol,
            timeframe="15m",
            timestamp=1234567890000 + 70 * 3600000,
            close=Decimal("105"),
        )

        # Mock _run_strategy to avoid actual strategy execution
        mock_attempt = MagicMock()
        mock_attempt.pattern = None  # No pattern, skip notification

        with patch.object(pipeline_with_history, '_run_strategy', return_value=[mock_attempt]):
            await pipeline_with_history.process_kline(kline)

        # Verify EMA indicator still exists and is ready
        assert f"{symbol}:1h" in pipeline_with_history._mtf_ema_indicators
        assert pipeline_with_history._mtf_ema_indicators[f"{symbol}:1h"].is_ready is True
