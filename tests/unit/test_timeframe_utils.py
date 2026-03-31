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


def day_to_ms(days_from_base: int) -> int:
    """Convert days from base to milliseconds since epoch."""
    base = 1700000000000  # Arbitrary base timestamp
    return base + (days_from_base * 24 * 60 * 60 * 1000)


def hour4_to_ms(hour: int) -> int:
    """Convert 4h-aligned hour to milliseconds since epoch."""
    base = 1700000000000
    return base + (hour * 60 * 60 * 1000)


class TestGetLastClosedKlineIndex:
    def test_15m_signal_uses_1h_closed(self):
        """
        15m kline at 10:15 should use 09:00 as last closed 1h kline.
        10:00 kline closes at 11:00, which is after 10:15, so it's not closed yet.
        """
        klines = [
            create_kline(hour_to_ms(9), "50000"),   # 09:00 (closes at 10:00) ✓ CLOSED
            create_kline(hour_to_ms(10), "51000"),  # 10:00 (closes at 11:00) ✗ NOT CLOSED
            create_kline(hour_to_ms(11), "52000"),  # 11:00 (closes at 12:00) ✗ FUTURE
        ]
        # Current 15m kline at 10:15
        current_ts = minute_to_ms(10, 15)

        idx = get_last_closed_kline_index(klines, current_ts, "1h")

        assert idx == 0  # Should return 09:00 kline (only closed one)

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

    def test_scenario_1_15m_uses_1h_closed_kline(self):
        """
        场景 1: 15m K 线闭合时用 1h 已闭合 K 线

        当前时间：10:15 (15m K 线闭合)
        1h K 线列表：[09:00, 10:00]
        预期：返回 09:00 (10:00 这根在 11:00 才闭合)
        """
        klines = [
            create_kline(hour_to_ms(9), "50000"),   # 09:00 (closes at 10:00) ✓ CLOSED
            create_kline(hour_to_ms(10), "51000"),  # 10:00 (closes at 11:00) ✗ NOT CLOSED YET
        ]
        current_ts = minute_to_ms(10, 15)  # 10:15

        idx = get_last_closed_kline_index(klines, current_ts, "1h")

        assert idx == 0  # Should return 09:00 kline

    def test_scenario_2_15m_closed_on_hour_boundary(self):
        """
        场景 2: 整点时刻 15m K 线闭合

        当前时间：11:00 (15m K 线闭合)
        1h K 线列表：[09:00, 10:00, 11:00]
        预期：返回 10:00 (11:00 这根刚开始，10:00-11:00 刚闭合)
        """
        klines = [
            create_kline(hour_to_ms(9), "50000"),   # 09:00
            create_kline(hour_to_ms(10), "51000"),  # 10:00
            create_kline(hour_to_ms(11), "52000"),  # 11:00
        ]
        current_ts = hour_to_ms(11)  # 11:00

        idx = get_last_closed_kline_index(klines, current_ts, "1h")

        assert idx == 1  # Should return 10:00 kline, not 11:00

    def test_scenario_3_4h_timeframe_boundary(self):
        """
        场景 3: 4h 周期判断

        当前时间：15:30 (15m K 线闭合)
        4h K 线列表：[08:00, 12:00]
        预期：返回 08:00
        解释：12:00+4h=16:00 > 15:30，所以 12:00 这根还没闭合，返回 08:00
        """
        # 使用统一的基准时间戳
        base = 1700000000000
        klines = [
            create_kline(base + 8 * 60 * 60 * 1000, "50000"),   # 08:00 (closes at 12:00) ✓ CLOSED
            create_kline(base + 12 * 60 * 60 * 1000, "51000"),  # 12:00 (closes at 16:00) ✗ NOT CLOSED YET
        ]
        current_ts = base + 15 * 60 * 60 * 1000 + 30 * 60 * 1000  # 15:30

        idx = get_last_closed_kline_index(klines, current_ts, "4h")

        assert idx == 0  # Should return 08:00 kline

    def test_scenario_5_all_klines_future(self):
        """
        场景 5: 所有 K 线都未闭合（未来数据）

        当前时间：05:00
        1h K 线列表：[06:00, 07:00] (未来数据)
        预期：返回 -1
        """
        klines = [
            create_kline(hour_to_ms(6), "50000"),  # 06:00 (future)
            create_kline(hour_to_ms(7), "51000"),  # 07:00 (future)
        ]
        current_ts = hour_to_ms(5)  # 05:00

        idx = get_last_closed_kline_index(klines, current_ts, "1h")

        assert idx == -1  # No closed klines available

    def test_multiple_closed_klines_returns_last_closed(self):
        """
        多个已闭合 K 线场景，应返回最后一个已闭合的。

        当前时间：14:30
        1h K 线列表：[09:00, 10:00, 11:00, 12:00, 13:00, 14:00]
        预期：返回 13:00 (14:00 这根在 15:00 才闭合)
        """
        klines = [
            create_kline(hour_to_ms(9), "50000"),   # 09:00
            create_kline(hour_to_ms(10), "51000"),  # 10:00
            create_kline(hour_to_ms(11), "52000"),  # 11:00
            create_kline(hour_to_ms(12), "53000"),  # 12:00
            create_kline(hour_to_ms(13), "54000"),  # 13:00
            create_kline(hour_to_ms(14), "55000"),  # 14:00 (closes at 15:00)
        ]
        current_ts = minute_to_ms(14, 30)  # 14:30

        idx = get_last_closed_kline_index(klines, current_ts, "1h")

        assert idx == 4  # Should return 13:00 kline (index 4)

    def test_kline_closes_exactly_at_current_time(self):
        """
        K 线闭合时间恰好等于当前时间的边界场景。

        当前时间：12:00
        1h K 线列表：[10:00, 11:00, 12:00]
        预期：返回 11:00 (11:00-12:00 这根恰好闭合，12:00 这根刚开始)
        """
        klines = [
            create_kline(hour_to_ms(10), "50000"),  # 10:00
            create_kline(hour_to_ms(11), "51000"),  # 11:00 (closes at 12:00)
            create_kline(hour_to_ms(12), "52000"),  # 12:00 (current)
        ]
        current_ts = hour_to_ms(12)  # 12:00

        idx = get_last_closed_kline_index(klines, current_ts, "1h")

        assert idx == 1  # Should return 11:00 kline
