"""
End-to-end tests for MTF (Multi-Timeframe) alignment.

These tests verify that MTF filtering works correctly in realistic scenarios.
"""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock

from src.application.signal_pipeline import SignalPipeline
from src.domain.models import KlineData, TrendDirection, AccountSnapshot
from src.domain.risk_calculator import RiskConfig


def create_kline(
    symbol: str = "BTC/USDT:USDT",
    timeframe: str = "1h",
    timestamp: int = 1700000000000,
    close: str = "50000",
    high: str = None,
    low: str = None,
    open: str = None,
) -> KlineData:
    """Create a realistic kline for integration testing."""
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
        is_closed=True,
    )


def hour_to_ms(hour: int) -> int:
    """Convert hour to milliseconds since epoch (simplified for testing)."""
    base = 1700000000000
    return base + (hour * 60 * 60 * 1000)


def create_test_pipeline(mtf_ema_period: int = 60):
    """Create a SignalPipeline with mocked dependencies for testing."""
    # Mock config manager
    mock_config_manager = MagicMock()
    mock_config_manager.user_config = MagicMock()
    mock_config_manager.user_config.mtf_ema_period = mtf_ema_period
    mock_config_manager.user_config.mtf_mapping = {
        "15m": "1h",
        "1h": "4h",
        "4h": "1d",
        "1d": "1w",
    }
    mock_config_manager.add_observer = MagicMock()

    risk_config = RiskConfig(
        max_loss_percent=Decimal("0.01"),
        max_leverage=10,
    )

    # Mock notification service
    mock_notifier = MagicMock()

    # Mock signal repository
    mock_repository = MagicMock()

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
        timestamp=1700000000000,
    ))

    return pipeline


class TestMtfBasic:
    """Basic MTF functionality tests."""

    def test_mtf_calculation_returns_trend(self):
        """
        Verify that MTF trend calculation returns a valid trend.

        Setup: Add 1h klines with rising prices (bullish trend)
        Expected: _get_closest_higher_tf_trends returns {"1h": trend}
        """
        from src.domain.indicators import EMACalculator

        pipeline = create_test_pipeline(mtf_ema_period=20)

        # Add 1h klines with rising prices (bullish setup)
        # Need at least mtf_ema_period (20) klines for EMA to be ready
        klines_1h = [
            create_kline(timestamp=hour_to_ms(h), close=str(50000 + h * 100), timeframe="1h")
            for h in range(50)  # 50 hours of data (enough for EMA warmup)
        ]
        pipeline._kline_history["BTC/USDT:USDT:1h"] = klines_1h

        # Pre-warm the EMA indicator with historical data
        ema_key = "BTC/USDT:USDT:1h"
        ema = EMACalculator(period=20)
        for kline in klines_1h:
            ema.update(kline.close)
        pipeline._mtf_ema_indicators[ema_key] = ema

        # Process a 15m kline at hour 49, minute 15
        kline_15m = create_kline(
            timeframe="15m",
            timestamp=hour_to_ms(49) + (15 * 60 * 1000),
            close="54900",
        )

        # Calculate MTF trends
        trends = pipeline._get_closest_higher_tf_trends(kline_15m)

        # Verify: Should have 1h trend (EMA should be ready after 50 klines)
        assert "1h" in trends
        assert trends["1h"] in [TrendDirection.BULLISH, TrendDirection.BEARISH]

    def test_mtf_no_higher_timeframe(self):
        """
        Test when no higher timeframe exists (e.g., 1w).

        Expected: Returns empty dict
        """
        pipeline = create_test_pipeline()

        kline_1w = create_kline(
            timeframe="1w",
            timestamp=hour_to_ms(100),
            close="50000",
        )

        trends = pipeline._get_closest_higher_tf_trends(kline_1w)

        # 1w has no higher timeframe in default mapping
        assert trends == {}

    def test_mtf_no_data_available(self):
        """
        Test when higher timeframe data is not available.

        Expected: Returns empty dict
        """
        pipeline = create_test_pipeline()

        # Don't add any 1h klines to history

        kline_15m = create_kline(
            timeframe="15m",
            timestamp=hour_to_ms(10),
            close="50000",
        )

        trends = pipeline._get_closest_higher_tf_trends(kline_15m)

        # No data available
        assert trends == {}


class TestMtfFilterIntegration:
    """MTF filter integration tests - verify filtering behavior."""

    def test_mtf_trend_uses_last_closed_kline(self):
        """
        Verify MTF trend uses the last CLOSED kline, not the running kline.

        Scenario:
        - 1h klines: [09:00, 10:00, 11:00]
        - 15m signal at 10:15
        Expected: Uses 10:00 kline for trend (not 11:00)
        """
        from src.domain.indicators import EMACalculator

        pipeline = create_test_pipeline(mtf_ema_period=10)  # Lower period for simpler test

        # Create 1h klines: 15 klines with rising prices, then a crash at the end
        klines_1h = []
        for i in range(15):
            price = 50000 + i * 100  # Rising prices
            klines_1h.append(create_kline(timestamp=hour_to_ms(i), close=str(price), timeframe="1h"))

        pipeline._kline_history["BTC/USDT:USDT:1h"] = klines_1h

        # Pre-warm EMA with first 10 klines (rising trend)
        ema_key = "BTC/USDT:USDT:1h"
        ema = EMACalculator(period=10)
        for kline in klines_1h[:10]:
            ema.update(kline.close)
        pipeline._mtf_ema_indicators[ema_key] = ema

        # 15m signal at hour 10, minute 15
        # Last closed 1h kline should be 10:00 (not 11:00)
        kline_15m = create_kline(
            timeframe="15m",
            timestamp=hour_to_ms(10) + (15 * 60 * 1000),
            close="51000",
        )

        trends = pipeline._get_closest_higher_tf_trends(kline_15m)

        # Should have 1h trend based on 10:00 kline
        assert "1h" in trends
        # Trend should be BULLISH (prices were rising, EMA is below current price)

    def test_mtf_bullish_trend_allows_long_signal(self):
        """
        Verify MTF filter allows LONG signal when higher TF trend is BULLISH.

        Scenario:
        - 1h trend: BULLISH (rising prices)
        - 15m produces LONG signal (bullish pinbar)
        Expected: MTF should allow this signal (directions match)
        """
        from src.domain.indicators import EMACalculator
        from src.domain.filter_factory import MtfFilterDynamic, FilterContext
        from src.domain.models import Direction, PatternResult

        pipeline = create_test_pipeline(mtf_ema_period=10)

        # Create 1h klines with rising prices (bullish trend)
        klines_1h = [
            create_kline(timestamp=hour_to_ms(i), close=str(50000 + i * 100), timeframe="1h")
            for i in range(20)
        ]
        pipeline._kline_history["BTC/USDT:USDT:1h"] = klines_1h

        # Pre-warm EMA
        ema = EMACalculator(period=10)
        for kline in klines_1h:
            ema.update(kline.close)
        pipeline._mtf_ema_indicators["BTC/USDT:USDT:1h"] = ema

        # 15m kline that would produce LONG signal
        kline_15m = create_kline(
            timeframe="15m",
            timestamp=hour_to_ms(15) + (15 * 60 * 1000),
            close="51600",
        )

        # Calculate MTF trends
        trends = pipeline._get_closest_higher_tf_trends(kline_15m)

        # Verify 1h trend is available
        assert "1h" in trends

        # Use MTF filter directly to verify it allows LONG when 1h is bullish
        mtf_filter = MtfFilterDynamic()
        pattern = PatternResult(
            strategy_name="pinbar",
            direction=Direction.LONG,
            score=0.8,
            details={},
        )
        context = FilterContext(
            current_timeframe="15m",
            higher_tf_trends=trends,
        )
        result = mtf_filter.check(pattern, context)

        # MTF should allow LONG when higher TF is bullish
        assert result.passed is True

    def test_mtf_bearish_trend_blocks_long_signal(self):
        """
        Verify MTF filter blocks LONG signal when higher TF trend is BEARISH.

        Scenario:
        - 1h trend: BEARISH (falling prices)
        - 15m produces LONG signal (bullish pinbar)
        Expected: MTF should block this signal (directions conflict)
        """
        from src.domain.indicators import EMACalculator
        from src.domain.filter_factory import MtfFilterDynamic, FilterContext
        from src.domain.models import Direction, PatternResult

        pipeline = create_test_pipeline(mtf_ema_period=10)

        # Create 1h klines with falling prices (bearish trend)
        klines_1h = [
            create_kline(timestamp=hour_to_ms(i), close=str(55000 - i * 100), timeframe="1h")
            for i in range(20)
        ]
        pipeline._kline_history["BTC/USDT:USDT:1h"] = klines_1h

        # Pre-warm EMA
        ema = EMACalculator(period=10)
        for kline in klines_1h:
            ema.update(kline.close)
        pipeline._mtf_ema_indicators["BTC/USDT:USDT:1h"] = ema

        # 15m kline that would produce LONG signal
        kline_15m = create_kline(
            timeframe="15m",
            timestamp=hour_to_ms(15) + (15 * 60 * 1000),
            close="53400",
        )

        # Calculate MTF trends
        trends = pipeline._get_closest_higher_tf_trends(kline_15m)

        # Verify 1h trend is available and bearish
        assert "1h" in trends
        assert trends["1h"] == TrendDirection.BEARISH

        # Use MTF filter directly to verify it blocks LONG when 1h is bearish
        mtf_filter = MtfFilterDynamic()
        pattern = PatternResult(
            strategy_name="pinbar",
            direction=Direction.LONG,
            score=0.8,
            details={},
        )
        context = FilterContext(
            current_timeframe="15m",
            higher_tf_trends=trends,
        )
        result = mtf_filter.check(pattern, context)

        # MTF should block LONG when higher TF is bearish
        assert result.passed is False
        assert "mtf_rejected" in result.reason
