"""Unit tests for MTF timeframe utilities."""
from decimal import Decimal
import pytest

from src.domain.timeframe_utils import (
    get_higher_timeframe,
    parse_timeframe_to_ms,
    get_last_closed_kline_index,
    DEFAULT_MTF_MAPPING,
    TIMEFRAME_TO_MS,
)
from src.domain.models import KlineData, TrendDirection


# Helper functions for test timestamp generation
def hour_to_ms(hour: int) -> int:
    """Convert hour to milliseconds since epoch (simplified for testing)."""
    base = 1700000000000  # Arbitrary base timestamp
    return base + (hour * 60 * 60 * 1000)


def minute_to_ms(hour: int, minute: int) -> int:
    """Convert hour:minute to milliseconds since epoch."""
    base = 1700000000000
    return base + (hour * 60 * 60 * 1000) + (minute * 60 * 1000)


def create_kline(timestamp: int, close: str = "50000") -> KlineData:
    """Create a test KlineData with minimal fields."""
    return KlineData(
        symbol="BTC/USDT:USDT",
        timeframe="1h",
        timestamp=timestamp,
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        volume=Decimal("1000"),
        is_closed=True,
    )


class TestGetHigherTimeframe:
    def test_default_mapping_15m_to_1h(self):
        """Test that 15m maps to 1h by default."""
        result = get_higher_timeframe("15m")
        assert result == "1h"

    def test_default_mapping_1h_to_4h(self):
        """Test that 1h maps to 4h by default."""
        result = get_higher_timeframe("1h")
        assert result == "4h"

    def test_default_mapping_4h_to_1d(self):
        """Test that 4h maps to 1d by default."""
        result = get_higher_timeframe("4h")
        assert result == "1d"

    def test_default_mapping_1d_to_1w(self):
        """Test that 1d maps to 1w by default."""
        result = get_higher_timeframe("1d")
        assert result == "1w"

    def test_no_higher_timeframe_for_1w(self):
        """Test that 1w has no higher timeframe in default mapping."""
        result = get_higher_timeframe("1w")
        assert result is None

    def test_custom_mapping(self):
        """Test custom MTF mapping override."""
        custom = {"15m": "4h", "1h": "1d"}
        result = get_higher_timeframe("15m", custom)
        assert result == "4h"

    def test_custom_mapping_partial(self):
        """Test custom mapping with missing key falls back to default."""
        custom = {"15m": "4h"}
        result = get_higher_timeframe("1h", custom)
        assert result == "4h"  # Falls back to default


class TestParseTimeframeToMs:
    def test_standard_15m(self):
        result = parse_timeframe_to_ms("15m")
        assert result == 15 * 60 * 1000

    def test_standard_1h(self):
        result = parse_timeframe_to_ms("1h")
        assert result == 60 * 60 * 1000

    def test_standard_4h(self):
        result = parse_timeframe_to_ms("4h")
        assert result == 4 * 60 * 60 * 1000

    def test_standard_1d(self):
        result = parse_timeframe_to_ms("1d")
        assert result == 24 * 60 * 60 * 1000

    def test_standard_1w(self):
        result = parse_timeframe_to_ms("1w")
        assert result == 7 * 24 * 60 * 60 * 1000

    def test_custom_2h(self):
        result = parse_timeframe_to_ms("2h")
        assert result == 2 * 60 * 60 * 1000

    def test_custom_30m(self):
        result = parse_timeframe_to_ms("30m")
        assert result == 30 * 60 * 1000

    def test_invalid_format(self):
        with pytest.raises(ValueError, match="Invalid timeframe format"):
            parse_timeframe_to_ms("invalid")

    def test_invalid_number(self):
        with pytest.raises(ValueError):
            parse_timeframe_to_ms("abc")


class TestGetLastClosedKlineIndex:
    def test_15m_signal_uses_1h_closed(self):
        """
        15m kline at 10:15 should use 10:00 as last closed 1h kline.
        """
        klines = [
            create_kline(hour_to_ms(9), "50000"),   # 09:00
            create_kline(hour_to_ms(10), "51000"),  # 10:00
            create_kline(hour_to_ms(11), "52000"),  # 11:00
        ]
        # Current 15m kline at 10:15
        current_ts = minute_to_ms(10, 15)

        idx = get_last_closed_kline_index(klines, current_ts, "1h")

        assert idx == 1  # Should return 10:00 kline

    def test_boundary_exactly_on_period(self):
        """
        Current kline exactly on 1h boundary (11:00) should use 10:00.
        """
        klines = [
            create_kline(hour_to_ms(9), "50000"),   # 09:00
            create_kline(hour_to_ms(10), "51000"),  # 10:00
            create_kline(hour_to_ms(11), "52000"),  # 11:00
        ]
        current_ts = hour_to_ms(11)

        idx = get_last_closed_kline_index(klines, current_ts, "1h")

        assert idx == 1  # Should return 10:00 kline, not 11:00

    def test_no_closed_klines(self):
        """
        All klines in the future should return -1.
        """
        klines = [
            create_kline(hour_to_ms(12), "52000"),  # 12:00 (future)
        ]
        current_ts = hour_to_ms(11)  # 11:00

        idx = get_last_closed_kline_index(klines, current_ts, "1h")

        assert idx == -1

    def test_empty_klines(self):
        """Empty kline list should return -1."""
        idx = get_last_closed_kline_index([], hour_to_ms(10), "1h")
        assert idx == -1

    def test_4h_to_1d_alignment(self):
        """
        4h kline at Day 2 00:00 should use Day 1's 1d kline.
        When current timestamp exactly matches a kline's timestamp,
        that kline is considered "current" (just started), so we use previous.
        """
        # Use timestamps aligned to UTC midnight for daily boundaries
        # Day 1: 2023-11-15 00:00:00 UTC
        day1_ts = 1700006400000
        # Day 2: 2023-11-16 00:00:00 UTC
        day2_ts = 1700092800000
        klines = [
            create_kline(day1_ts, "50000"),      # Day 1
            create_kline(day2_ts, "51000"),      # Day 2
        ]
        # 4h kline at exactly Day 2 00:00 (Day 2 just started)
        current_ts = day2_ts

        idx = get_last_closed_kline_index(klines, current_ts, "1d")

        assert idx == 0  # Should return Day 1 kline (Day 2 is current)
