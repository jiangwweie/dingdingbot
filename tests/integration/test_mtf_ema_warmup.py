"""
Integration tests for MTF EMA warmup in SignalPipeline.

This test verifies that the _build_and_warmup_runner method properly
warms up MTF EMA indicators so they are ready on first use.

Issue: Previously, MTF EMAs were created lazily in _get_closest_higher_tf_trends,
but they needed 60 data points to become ready. The warmup now pre-populates
these EMAs during pipeline initialization.
"""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock

from src.application.signal_pipeline import SignalPipeline
from src.domain.models import KlineData, AccountSnapshot
from src.domain.risk_calculator import RiskConfig
from src.domain.indicators import EMACalculator


def create_kline(
    symbol: str = "BTC/USDT:USDT",
    timeframe: str = "1h",
    timestamp: int = 1700000000000,
    close: str = "50000",
    high: str = None,
    low: str = None,
    open: str = None,
    is_closed: bool = True,
) -> KlineData:
    """Create a realistic kline for testing."""
    close_dec = Decimal(close)
    high_dec = Decimal(high) if high else close_dec * Decimal("1.001")
    low_dec = Decimal(low) if low else close_dec * Decimal("0.999")
    open_dec = Decimal(open) if open else close_dec

    return KlineData(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=timestamp,
        open=open_dec,
        high=high_dec,
        low=low_dec,
        close=close_dec,
        volume=Decimal("1000"),
        is_closed=is_closed,
    )


def create_test_pipeline(mtf_ema_period: int = 60, pre_populate_history: bool = True):
    """Create a SignalPipeline with mocked dependencies for testing."""
    mock_config_manager = MagicMock()
    mock_config_manager.user_config = MagicMock()
    mock_config_manager.user_config.mtf_ema_period = mtf_ema_period
    mock_config_manager.user_config.mtf_mapping = {
        "15m": "1h",
        "1h": "4h",
        "4h": "1d",
        "1d": "1w",
    }
    mock_config_manager.core_config = MagicMock()
    mock_config_manager.core_config.signal_pipeline = MagicMock()
    mock_config_manager.core_config.signal_pipeline.queue = MagicMock()
    mock_config_manager.core_config.signal_pipeline.queue.batch_size = 10
    mock_config_manager.core_config.signal_pipeline.queue.flush_interval = 5.0
    mock_config_manager.core_config.signal_pipeline.queue.max_queue_size = 1000
    mock_config_manager.add_observer = MagicMock()

    risk_config = RiskConfig(
        max_loss_percent=Decimal("0.01"),
        max_leverage=10,
    )

    mock_notifier = MagicMock()
    mock_repository = MagicMock()

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
        timestamp=1700000000000,
    ))

    return pipeline


class TestMtfEmaWarmup:
    """Tests for MTF EMA warmup during pipeline initialization."""

    def test_mtf_ema_warmup_populates_indicators(self):
        """
        Verify that _build_and_warmup_runner pre-warms MTF EMAs.

        Setup:
        - Pipeline with 1h, 4h, 1d K-line history (65+ bars each)
        - mtf_ema_period = 60

        Expected:
        - _mtf_ema_indicators contains entries for 1h, 4h, 1d
        - All EMAs have is_ready = True
        """
        pipeline = create_test_pipeline(mtf_ema_period=60)

        # Populate history with 65 bars for each higher timeframe
        for tf in ["1h", "4h", "1d"]:
            pipeline._kline_history[f"BTC/USDT:USDT:{tf}"] = [
                create_kline(
                    timeframe=tf,
                    timestamp=1700000000000 + (i * 3600000),
                    close=str(50000 + i * 10),  # Rising prices
                )
                for i in range(65)
            ]

        # Trigger runner rebuild (which includes warmup)
        pipeline._runner = pipeline._build_and_warmup_runner()

        # Verify: MTF EMAs should be pre-warmed
        assert len(pipeline._mtf_ema_indicators) == 3, "Should have 3 MTF EMAs (1h, 4h, 1d)"

        # Verify each EMA is ready
        for tf in ["1h", "4h", "1d"]:
            ema_key = f"BTC/USDT:USDT:{tf}"
            assert ema_key in pipeline._mtf_ema_indicators, f"Missing EMA for {tf}"
            ema = pipeline._mtf_ema_indicators[ema_key]
            assert ema.is_ready, f"EMA for {tf} should be ready after warmup"
            assert ema.value is not None, f"EMA for {tf} should have a value"

    def test_mtf_ema_warmup_excludes_15m(self):
        """
        Verify that 15m timeframe is NOT warmup (only higher TFs).

        Setup:
        - Pipeline with 15m, 1h K-line history

        Expected:
        - _mtf_ema_indicators contains ONLY 1h (not 15m)
        """
        pipeline = create_test_pipeline(mtf_ema_period=60)

        # Populate history for 15m and 1h
        pipeline._kline_history["BTC/USDT:USDT:15m"] = [
            create_kline(timeframe="15m", timestamp=1700000000000 + (i * 900000))
            for i in range(100)
        ]
        pipeline._kline_history["BTC/USDT:USDT:1h"] = [
            create_kline(timeframe="1h", timestamp=1700000000000 + (i * 3600000))
            for i in range(65)
        ]

        # Trigger runner rebuild
        pipeline._runner = pipeline._build_and_warmup_runner()

        # Verify: Only 1h should be in MTF EMAs (not 15m)
        assert "BTC/USDT:USDT:1h" in pipeline._mtf_ema_indicators
        assert "BTC/USDT:USDT:15m" not in pipeline._mtf_ema_indicators

    def test_mtf_ema_warmup_respects_is_closed(self):
        """
        Verify warmup excludes the currently running (unclosed) K-line.

        Setup:
        - History with 66 bars where last bar is is_closed=False

        Expected:
        - EMA updated with only 65 bars (excluding the unclosed one)
        - EMA should still be ready (65 >= 60)
        """
        pipeline = create_test_pipeline(mtf_ema_period=60)

        # 65 closed + 1 unclosed = 66 total
        klines = [
            create_kline(
                timeframe="1h",
                timestamp=1700000000000 + (i * 3600000),
                close=str(50000 + i * 10),
                is_closed=(i < 65),  # Last bar is unclosed
            )
            for i in range(66)
        ]
        pipeline._kline_history["BTC/USDT:USDT:1h"] = klines

        # Trigger runner rebuild
        pipeline._runner = pipeline._build_and_warmup_runner()

        # Verify EMA is ready (used 65 closed bars)
        ema = pipeline._mtf_ema_indicators["BTC/USDT:USDT:1h"]
        assert ema.is_ready, "EMA should be ready after warming up with 65 closed bars"

    def test_mtf_ema_first_call_returns_valid_trend(self):
        """
        End-to-end test: First call to _get_closest_higher_tf_trends should succeed.

        This test verifies the original issue is fixed:
        - Before fix: First call would return {} because EMA was created lazily
        - After fix: First call returns valid trend because EMA was pre-warmed
        """
        from src.domain.models import TrendDirection

        pipeline = create_test_pipeline(mtf_ema_period=60)

        # Populate history with enough data
        pipeline._kline_history["BTC/USDT:USDT:1h"] = [
            create_kline(
                timeframe="1h",
                timestamp=1700000000000 + (i * 3600000),
                close=str(50000 + i * 100),  # Rising prices -> Bullish
            )
            for i in range(65)
        ]

        # Trigger runner rebuild (includes MTF EMA warmup)
        pipeline._runner = pipeline._build_and_warmup_runner()

        # Now simulate first signal check from a 15m kline
        kline_15m = create_kline(
            timeframe="15m",
            timestamp=1700000000000 + (65 * 3600000) + (15 * 60000),
            close="56500",
        )

        # First call to _get_closest_higher_tf_trends
        trends = pipeline._get_closest_higher_tf_trends(kline_15m)

        # Verify: Should have valid trend (NOT empty dict)
        assert "1h" in trends, "Should have 1h trend on first call"
        assert trends["1h"] == TrendDirection.BULLISH, "Trend should be bullish (rising prices)"

    def test_mtf_ema_warmup_insufficient_data(self):
        """
        Verify graceful handling when insufficient data for warmup.

        Setup:
        - History with only 10 bars (less than mtf_ema_period=60)

        Expected:
        - EMA is created but NOT ready
        - _get_closest_higher_tf_trends returns {} gracefully
        """
        pipeline = create_test_pipeline(mtf_ema_period=60)

        # Only 10 bars - not enough for EMA warmup
        pipeline._kline_history["BTC/USDT:USDT:1h"] = [
            create_kline(
                timeframe="1h",
                timestamp=1700000000000 + (i * 3600000),
                close=str(50000 + i * 100),
            )
            for i in range(10)
        ]

        # Trigger runner rebuild
        pipeline._runner = pipeline._build_and_warmup_runner()

        # Verify: EMA exists but is not ready
        ema = pipeline._mtf_ema_indicators.get("BTC/USDT:USDT:1h")
        assert ema is not None, "EMA should be created"
        assert not ema.is_ready, "EMA should NOT be ready with only 10 bars"

        # First call should gracefully return empty dict
        kline_15m = create_kline(timeframe="15m", timestamp=1700000000000)
        trends = pipeline._get_closest_higher_tf_trends(kline_15m)
        assert trends == {}, "Should return empty dict when EMA not ready"
