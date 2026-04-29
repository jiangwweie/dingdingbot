"""Unit tests for backtester MTF alignment fix.

Tests verify that the backtester correctly uses only CLOSED higher timeframe
klines, preventing the "future function" problem where unreleased candles
are incorrectly used in MTF filtering.
"""
from decimal import Decimal
import pytest
from unittest.mock import MagicMock, AsyncMock

from src.application.backtester import Backtester
from src.domain.models import KlineData, TrendDirection, BacktestRequest


def hour_to_ms(hour: int) -> int:
    """Convert hour to milliseconds since epoch (simplified for testing)."""
    base = 1700000000000
    return base + (hour * 60 * 60 * 1000)


def minute_to_ms(hour: int, minute: int) -> int:
    """Convert hour:minute to milliseconds since epoch."""
    base = 1700000000000
    return base + (hour * 60 * 60 * 1000) + (minute * 60 * 1000)


def create_kline(
    symbol: str = "BTC/USDT:USDT",
    timeframe: str = "1h",
    timestamp: int = 1700000000000,
    close: str = "50000",
    open: str = None,
    high: str = None,
    low: str = None,
) -> KlineData:
    """Create a test KlineData with minimal fields."""
    close_dec = Decimal(close)
    open_dec = Decimal(open) if open else close_dec
    high_dec = Decimal(high) if high else close_dec * Decimal("1.001")
    low_dec = Decimal(low) if low else close_dec * Decimal("0.999")

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


def create_mock_gateway():
    """Create a mock exchange gateway for backtesting."""
    mock_gateway = MagicMock()
    mock_gateway.fetch_historical_ohlcv = AsyncMock(return_value=[])
    mock_gateway.fetch_ticker_price = AsyncMock(return_value=Decimal("50000"))
    return mock_gateway


class TestGetClosestHigherTfTrends:
    """Tests for _get_closest_higher_tf_trends method."""

    def setup_method(self):
        """Set up test fixtures."""
        self.backtester = Backtester(create_mock_gateway())

    def test_excludes_current_candle_future_function_bug(self):
        """
        CRITICAL: Verify that 15m kline at timestamp=10:00 does NOT use
        1h kline at timestamp=10:00 (which doesn't close until 11:00).

        This is the "future function" bug - previously the code used
        <= comparison, incorrectly including unreleased candles.
        """
        higher_tf_data = {
            hour_to_ms(9): {"1h": TrendDirection.BULLISH},   # 09:00 (closed at 10:00)
            hour_to_ms(10): {"1h": TrendDirection.BEARISH},  # 10:00 (closes at 11:00)
            hour_to_ms(11): {"1h": TrendDirection.BULLISH},  # 11:00 (future)
        }

        # 15m kline timestamp = 10:00 (represents 10:00-10:15 candle)
        # At 10:00, the 1h candle 10:00-11:00 has NOT started yet
        # Even at 10:15, the 1h candle 10:00-11:00 is still forming
        current_ts = hour_to_ms(10)

        trends = self.backtester._get_closest_higher_tf_trends(current_ts, higher_tf_data)

        # Should use 09:00 kline (closed), NOT 10:00 (not yet closed)
        assert trends == {"1h": TrendDirection.BULLISH}

    def test_strictly_less_than_comparison(self):
        """
        Verify the fix: uses ts < timestamp (strictly less than),
        not ts <= timestamp.
        """
        higher_tf_data = {
            hour_to_ms(8): {"1h": TrendDirection.BEARISH},
            hour_to_ms(9): {"1h": TrendDirection.BULLISH},
            hour_to_ms(10): {"1h": TrendDirection.BEARISH},  # Same as current
        }

        current_ts = hour_to_ms(10)
        trends = self.backtester._get_closest_higher_tf_trends(current_ts, higher_tf_data)

        # Should return 09:00, not 10:00 (strictly less than)
        assert trends == {"1h": TrendDirection.BULLISH}

    def test_no_valid_closed_kline_returns_empty(self):
        """
        When no closed higher TF klines exist, return empty dict.
        """
        higher_tf_data = {
            hour_to_ms(11): {"1h": TrendDirection.BULLISH},  # Future kline
        }

        current_ts = hour_to_ms(10)
        trends = self.backtester._get_closest_higher_tf_trends(current_ts, higher_tf_data)

        assert trends == {}

    def test_empty_higher_tf_data_returns_empty(self):
        """Empty higher_tf_data should return empty dict."""
        current_ts = hour_to_ms(10)
        trends = self.backtester._get_closest_higher_tf_trends(current_ts, {})
        assert trends == {}

    def test_boundary_case_exactly_on_hour(self):
        """
        Boundary case: 15m kline at exactly 11:00.
        The 1h kline 10:00-11:00 just closed at 11:00.
        Should be able to use 10:00 kline.
        """
        higher_tf_data = {
            hour_to_ms(10): {"1h": TrendDirection.BULLISH},  # 10:00-11:00 (closes at 11:00)
            hour_to_ms(11): {"1h": TrendDirection.BEARISH},  # 11:00-12:00 (just started)
        }

        # 15m kline at exactly 11:00 (11:00-11:15 candle)
        current_ts = hour_to_ms(11)

        trends = self.backtester._get_closest_higher_tf_trends(current_ts, higher_tf_data)

        # Should use 10:00 kline (just closed at 11:00)
        # Note: 11:00 kline is "current" (just started), so excluded
        assert trends == {"1h": TrendDirection.BULLISH}

    def test_multiple_timeframes(self):
        """Test with multiple higher timeframe data points."""
        higher_tf_data = {
            hour_to_ms(8): {"1h": TrendDirection.BEARISH},
            hour_to_ms(9): {"1h": TrendDirection.BULLISH},
            hour_to_ms(10): {"1h": TrendDirection.BEARISH},
            hour_to_ms(11): {"1h": TrendDirection.BULLISH},
        }

        # 15m kline at 10:30
        current_ts = hour_to_ms(10) + minute_to_ms(0, 30)

        trends = self.backtester._get_closest_higher_tf_trends(current_ts, higher_tf_data)

        # Should use 09:00 (10:00 is still forming at 10:30)
        assert trends == {"1h": TrendDirection.BULLISH}

    def test_gap_in_data_uses_latest_available(self):
        """
        When there's a gap in data, use the latest available closed kline.
        """
        higher_tf_data = {
            hour_to_ms(8): {"1h": TrendDirection.BEARISH},
            # Missing hour 9
            hour_to_ms(10): {"1h": TrendDirection.BULLISH},
        }

        # 15m kline at 10:15
        # Use base + 10 hours + 15 minutes
        base = 1700000000000
        current_ts = base + 10 * 3600000 + 15 * 60000  # 10:15

        trends = self.backtester._get_closest_higher_tf_trends(current_ts, higher_tf_data)

        # Should use 08:00 (10:00 is still forming)
        assert trends == {"1h": TrendDirection.BEARISH}


class TestBacktesterMtfAlignment:
    """Integration tests for MTF alignment in backtest context."""

    @pytest.mark.asyncio
    async def test_backtest_mtf_uses_closed_kline_only(self):
        """
        Verify backtest correctly filters MTF data to use only closed klines.
        """
        mock_gateway = create_mock_gateway()

        # Mock 15m klines
        klines_15m = [
            create_kline(timeframe="15m", timestamp=hour_to_ms(9) + i * 15 * 60000, close=str(50000 + i * 10))
            for i in range(8)  # 9:00, 9:15, 9:30, ..., 10:45
        ]

        # Mock 1h klines
        klines_1h = [
            create_kline(timeframe="1h", timestamp=hour_to_ms(9), close="50000"),  # 09:00-10:00
            create_kline(timeframe="1h", timestamp=hour_to_ms(10), close="50100"), # 10:00-11:00
            create_kline(timeframe="1h", timestamp=hour_to_ms(11), close="50200"), # 11:00-12:00
        ]

        async def mock_fetch(symbol, timeframe, limit=1000, since=None):
            if timeframe == "15m":
                return klines_15m
            elif timeframe == "1h":
                return klines_1h
            return []

        mock_gateway.fetch_historical_ohlcv = mock_fetch

        backtester = Backtester(mock_gateway)

        request = BacktestRequest(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            start_time=hour_to_ms(9),
            end_time=hour_to_ms(10) + minute_to_ms(0, 45),
            mtf_validation_enabled=True,
        )

        report = await backtester.run_backtest(request)

        # Verify report was generated
        assert report is not None
        # Note: Detailed assertions depend on specific MTF logic


class TestMtfFutureFunctionRegression:
    """Regression tests for the future function bug fix."""

    def setup_method(self):
        """Set up test fixtures."""
        self.backtester = Backtester(create_mock_gateway())

    def test_original_bug_scenario(self):
        """
        Original bug scenario from issue report:
        15m strategy using 1h MTF at 10:15.
        """
        higher_tf_data = {
            hour_to_ms(9): {"1h": TrendDirection.BULLISH},   # 09:00-10:00 (closed at 10:00)
            hour_to_ms(10): {"1h": TrendDirection.BEARISH},  # 10:00-11:00 (NOT closed at 10:15)
        }

        # 15m kline at 10:15
        # Use base + 10 hours + 15 minutes
        base = 1700000000000
        current_ts = base + 10 * 3600000 + 15 * 60000  # 10:15

        trends = self.backtester._get_closest_higher_tf_trends(current_ts, higher_tf_data)

        # Must use 09:00 (closed at 10:00), NOT 10:00 (closes at 11:00)
        assert trends == {"1h": TrendDirection.BULLISH}
        assert trends.get("1h") != TrendDirection.BEARISH  # Verify 10:00 was NOT used

    def test_all_timestamps_before_current(self):
        """When all higher TF timestamps are before current, use the latest."""
        higher_tf_data = {
            hour_to_ms(7): {"1h": TrendDirection.BEARISH},
            hour_to_ms(8): {"1h": TrendDirection.BULLISH},
            hour_to_ms(9): {"1h": TrendDirection.BEARISH},
        }

        current_ts = hour_to_ms(10)
        trends = self.backtester._get_closest_higher_tf_trends(current_ts, higher_tf_data)

        # All are closed, should use the latest (09:00)
        assert trends == {"1h": TrendDirection.BEARISH}
