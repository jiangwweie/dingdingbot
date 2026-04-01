"""
Unit tests for MTF EMA warmup during configuration hot-reload.

Tests the edge case where new symbols added via hot-reload need their
MTF EMA indicators warmed up to prevent higher_tf_data_unavailable errors.
"""

import pytest
from decimal import Decimal
from unittest.mock import Mock, MagicMock, AsyncMock

from src.application.signal_pipeline import SignalPipeline
from src.domain.models import KlineData, Direction
from src.application.config_manager import ConfigManager


def create_kline(symbol: str, timeframe: str, close: float, is_closed: bool = True) -> KlineData:
    """Helper to create test KlineData."""
    return KlineData(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=1000000000,
        open=Decimal(str(close * 0.99)),
        high=Decimal(str(close * 1.01)),
        low=Decimal(str(close * 0.98)),
        close=Decimal(str(close)),
        volume=Decimal("1000"),
        is_closed=is_closed
    )


class TestMtfEmaHotReload:
    """Tests for MTF EMA warmup during hot-reload."""

    @pytest.fixture
    def pipeline(self):
        """Create a SignalPipeline instance with mocked dependencies."""
        config_manager = Mock(spec=ConfigManager)
        config_manager.user_config = Mock()
        config_manager.user_config.active_strategies = []
        config_manager.core_config = Mock()
        config_manager.user_config.mtf_ema_period = 60  # Required for MTF EMA warmup

        notifier = Mock()
        repository = Mock()

        pipeline = SignalPipeline(
            config_manager=config_manager,
            risk_config=Mock(),
            notification_service=notifier,
            signal_repository=repository,
            cooldown_seconds=300
        )

        # Pre-populate _kline_history with initial symbols
        pipeline._kline_history = {
            "BTC/USDT:USDT:1h": [create_kline("BTC/USDT:USDT", "1h", 50000 + i * 100) for i in range(100)],
            "ETH/USDT:USDT:1h": [create_kline("ETH/USDT:USDT", "1h", 3000 + i * 10) for i in range(100)],
        }

        return pipeline

    def test_warmup_initializes_mtf_ema_for_new_symbols(self, pipeline):
        """Test that _warmup_mtf_ema_for_new_symbols initializes EMA for new symbols."""
        # Initial state: no MTF EMA indicators
        assert len(pipeline._mtf_ema_indicators) == 0

        # Call warmup
        pipeline._warmup_mtf_ema_for_new_symbols()

        # Should have initialized MTF EMA for both 1h symbols
        assert len(pipeline._mtf_ema_indicators) == 2
        assert "BTC/USDT:USDT:1h" in pipeline._mtf_ema_indicators
        assert "ETH/USDT:USDT:1h" in pipeline._mtf_ema_indicators

    def test_warmup_skips_already_initialized_symbols(self, pipeline):
        """Test that warmup skips symbols that are already initialized."""
        # Pre-initialize one symbol
        from src.domain.indicators import EMACalculator
        pipeline._mtf_ema_indicators["BTC/USDT:USDT:1h"] = EMACalculator(period=60)

        # Call warmup
        pipeline._warmup_mtf_ema_for_new_symbols()

        # Should only have initialized the new symbol
        assert len(pipeline._mtf_ema_indicators) == 2
        assert "ETH/USDT:USDT:1h" in pipeline._mtf_ema_indicators

    def test_warmup_populates_ema_with_historical_data(self, pipeline):
        """Test that warmup populates EMA with sufficient historical data."""
        # Call warmup
        pipeline._warmup_mtf_ema_for_new_symbols()

        # Check EMA is ready (has enough data points)
        btc_ema = pipeline._mtf_ema_indicators["BTC/USDT:USDT:1h"]
        eth_ema = pipeline._mtf_ema_indicators["ETH/USDT:USDT:1h"]

        assert btc_ema.is_ready, "BTC MTF EMA should be ready after warmup with 100 bars"
        assert eth_ema.is_ready, "ETH MTF EMA should be ready after warmup with 100 bars"

    def test_warmup_excludes_current_running_kline(self, pipeline):
        """Test that warmup excludes the currently running (unclosed) K-line."""
        # Add an unclosed K-line to history for a new symbol
        pipeline._kline_history["SOL/USDT:USDT:1h"] = [
            create_kline("SOL/USDT:USDT", "1h", 200 + i, is_closed=False) for i in range(100)
        ]
        # Make last kline unclosed
        pipeline._kline_history["SOL/USDT:USDT:1h"][-1] = create_kline("SOL/USDT:USDT", "1h", 300, is_closed=False)

        # Call warmup
        pipeline._warmup_mtf_ema_for_new_symbols()

        # SOL should now be in the indicators (new symbol)
        assert "SOL/USDT:USDT:1h" in pipeline._mtf_ema_indicators

        # The unclosed K-line should not have been used for warmup
        sol_ema = pipeline._mtf_ema_indicators["SOL/USDT:USDT:1h"]
        # EMA needs 60 points, we have 100 bars but last one is unclosed
        # So we should have 99 points for warmup, which is enough
        assert sol_ema.is_ready

    def test_warmup_only_higher_timeframes(self, pipeline):
        """Test that warmup only processes higher timeframes (1h, 4h, 1d)."""
        # Add 15m data (should be ignored)
        pipeline._kline_history["BTC/USDT:USDT:15m"] = [
            create_kline("BTC/USDT:USDT", "15m", 50000 + i) for i in range(100)
        ]

        # Call warmup
        pipeline._warmup_mtf_ema_for_new_symbols()

        # 15m should NOT be in MTF EMA indicators (not a higher timeframe)
        assert "BTC/USDT:USDT:15m" not in pipeline._mtf_ema_indicators

        # But 1h should be
        assert "BTC/USDT:USDT:1h" in pipeline._mtf_ema_indicators
        assert "ETH/USDT:USDT:1h" in pipeline._mtf_ema_indicators

    def test_warmup_handles_insufficient_data(self):
        """Test that warmup handles symbols with insufficient historical data."""
        config_manager = Mock(spec=ConfigManager)
        config_manager.user_config = Mock()
        config_manager.user_config.active_strategies = []
        config_manager.core_config = Mock()
        config_manager.user_config.mtf_ema_period = 60  # Required for MTF EMA warmup

        pipeline = SignalPipeline(
            config_manager=config_manager,
            risk_config=Mock(),
            notification_service=Mock(),
            signal_repository=Mock(),
            cooldown_seconds=300
        )

        # Only 30 bars (not enough for EMA-60)
        pipeline._kline_history = {
            "NEW/USDT:USDT:1h": [create_kline("NEW/USDT:USDT", "1h", 100 + i) for i in range(30)]
        }

        # Call warmup
        pipeline._warmup_mtf_ema_for_new_symbols()

        # EMA should be initialized but NOT ready
        assert "NEW/USDT:USDT:1h" in pipeline._mtf_ema_indicators
        new_ema = pipeline._mtf_ema_indicators["NEW/USDT:USDT:1h"]
        assert not new_ema.is_ready, "EMA should not be ready with only 30 bars (needs 60)"

    def test_on_config_updated_calls_mtf_ema_warmup(self, pipeline):
        """Test that on_config_updated calls _warmup_mtf_ema_for_new_symbols."""
        import asyncio

        # Spy on the warmup method
        warmup_called = False
        original_warmup = pipeline._warmup_mtf_ema_for_new_symbols

        def spy_warmup():
            nonlocal warmup_called
            warmup_called = True
            return original_warmup()

        pipeline._warmup_mtf_ema_for_new_symbols = spy_warmup

        # Mock the runner building
        pipeline._runner = Mock()

        # Call on_config_updated
        asyncio.new_event_loop().run_until_complete(pipeline.on_config_updated())

        # Verify warmup was called
        assert warmup_called, "_warmup_mtf_ema_for_new_symbols should be called during hot-reload"
