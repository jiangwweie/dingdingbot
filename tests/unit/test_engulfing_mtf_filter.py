"""
Unit tests for Engulfing Strategy with MTF Filter - T4 测试。

测试覆盖:
- T4-1: 15m 多头确认 (1h BULLISH, 信号 LONG)
- T4-2: 15m 空头确认 (1h BEARISH, 信号 SHORT)
- T4-3: 15m 多头冲突 (1h BEARISH, 信号 LONG)
- T4-4: 1h 多头确认 (4h BULLISH, 信号 LONG)
- T4-5: 4h 多头确认 (1d BULLISH, 信号 LONG)
- T4-6: 1w 无高周期 (自动通过)
"""
import pytest
from decimal import Decimal
from src.domain.models import KlineData, Direction, PatternResult, TrendDirection
from src.domain.strategies.engulfing_strategy import EngulfingStrategy
from src.domain.filter_factory import MtfFilterDynamic, FilterContext


def create_kline(
    symbol: str = "BTC/USDT:USDT",
    timeframe: str = "15m",
    open: Decimal = Decimal("100"),
    high: Decimal = Decimal("100"),
    low: Decimal = Decimal("100"),
    close: Decimal = Decimal("100"),
    timestamp: int = 1000,
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
        volume=Decimal("1000"),
        is_closed=is_closed,
    )


def create_bullish_engulfing_pair() -> tuple:
    """Create a standard bullish engulfing pattern."""
    prev = create_kline(
        open=Decimal("100"), high=Decimal("102"),
        low=Decimal("98"), close=Decimal("99"),
        timestamp=1000
    )
    curr = create_kline(
        open=Decimal("98"), high=Decimal("103"),
        low=Decimal("97"), close=Decimal("102"),
        timestamp=2000
    )
    return prev, curr


def create_bearish_engulfing_pair() -> tuple:
    """Create a standard bearish engulfing pattern."""
    prev = create_kline(
        open=Decimal("99"), high=Decimal("102"),
        low=Decimal("98"), close=Decimal("100"),
        timestamp=1000
    )
    curr = create_kline(
        open=Decimal("101"), high=Decimal("103"),
        low=Decimal("97"), close=Decimal("98"),
        timestamp=2000
    )
    return prev, curr


class TestEngulfingWithMtfFilter:
    """T4: Engulfing Strategy with MTF Filter tests."""

    def test_t4_1_15m_bullish_confirmed(self):
        """T4-1: 15m 多头确认 (1h BULLISH, 信号 LONG)"""
        mtf_filter = MtfFilterDynamic(enabled=True)

        prev, curr = create_bullish_engulfing_pair()
        curr = create_kline(timeframe="15m", timestamp=2000,
            open=Decimal("98"), high=Decimal("103"),
            low=Decimal("97"), close=Decimal("102"))

        strategy = EngulfingStrategy()
        pattern_result = strategy.detect(curr, prev_kline=prev)

        assert pattern_result is not None
        assert pattern_result.direction == Direction.LONG

        # MTF: 15m -> 1h, 1h is BULLISH
        context = FilterContext(
            kline=curr,
            current_timeframe="15m",
            higher_tf_trends={"1h": TrendDirection.BULLISH},
            current_trend=None
        )
        event = mtf_filter.check(pattern_result, context)

        assert event.passed == True
        assert event.reason == "mtf_confirmed_bullish"
        assert event.metadata["higher_timeframe"] == "1h"
        assert event.metadata["higher_trend"] == "bullish"

    def test_t4_2_15m_bearish_confirmed(self):
        """T4-2: 15m 空头确认 (1h BEARISH, 信号 SHORT)"""
        mtf_filter = MtfFilterDynamic(enabled=True)

        prev, curr = create_bearish_engulfing_pair()
        curr = create_kline(timeframe="15m", timestamp=2000,
            open=Decimal("101"), high=Decimal("103"),
            low=Decimal("97"), close=Decimal("98"))

        strategy = EngulfingStrategy()
        pattern_result = strategy.detect(curr, prev_kline=prev)

        assert pattern_result is not None
        assert pattern_result.direction == Direction.SHORT

        # MTF: 15m -> 1h, 1h is BEARISH
        context = FilterContext(
            kline=curr,
            current_timeframe="15m",
            higher_tf_trends={"1h": TrendDirection.BEARISH},
            current_trend=None
        )
        event = mtf_filter.check(pattern_result, context)

        assert event.passed == True
        assert event.reason == "mtf_confirmed_bearish"
        assert event.metadata["higher_timeframe"] == "1h"

    def test_t4_3_15m_bullish_rejected(self):
        """T4-3: 15m 多头冲突 (1h BEARISH, 信号 LONG)"""
        mtf_filter = MtfFilterDynamic(enabled=True)

        prev, curr = create_bullish_engulfing_pair()
        curr = create_kline(timeframe="15m", timestamp=2000,
            open=Decimal("98"), high=Decimal("103"),
            low=Decimal("97"), close=Decimal("102"))

        strategy = EngulfingStrategy()
        pattern_result = strategy.detect(curr, prev_kline=prev)

        assert pattern_result is not None
        assert pattern_result.direction == Direction.LONG

        # MTF: 15m -> 1h, 1h is BEARISH (conflict)
        context = FilterContext(
            kline=curr,
            current_timeframe="15m",
            higher_tf_trends={"1h": TrendDirection.BEARISH},
            current_trend=None
        )
        event = mtf_filter.check(pattern_result, context)

        assert event.passed == False
        assert event.reason == "mtf_rejected_bearish_higher_tf"
        assert event.metadata["higher_timeframe"] == "1h"

    def test_t4_4_1h_bullish_confirmed(self):
        """T4-4: 1h 多头确认 (4h BULLISH, 信号 LONG)"""
        mtf_filter = MtfFilterDynamic(enabled=True)

        prev, curr = create_bullish_engulfing_pair()
        curr = create_kline(timeframe="1h", timestamp=2000,
            open=Decimal("98"), high=Decimal("103"),
            low=Decimal("97"), close=Decimal("102"))

        strategy = EngulfingStrategy()
        pattern_result = strategy.detect(curr, prev_kline=prev)

        assert pattern_result is not None

        # MTF: 1h -> 4h, 4h is BULLISH
        context = FilterContext(
            kline=curr,
            current_timeframe="1h",
            higher_tf_trends={"4h": TrendDirection.BULLISH},
            current_trend=None
        )
        event = mtf_filter.check(pattern_result, context)

        assert event.passed == True
        assert event.reason == "mtf_confirmed_bullish"
        assert event.metadata["higher_timeframe"] == "4h"

    def test_t4_5_4h_bullish_confirmed(self):
        """T4-5: 4h 多头确认 (1d BULLISH, 信号 LONG)"""
        mtf_filter = MtfFilterDynamic(enabled=True)

        prev, curr = create_bullish_engulfing_pair()
        curr = create_kline(timeframe="4h", timestamp=2000,
            open=Decimal("98"), high=Decimal("103"),
            low=Decimal("97"), close=Decimal("102"))

        strategy = EngulfingStrategy()
        pattern_result = strategy.detect(curr, prev_kline=prev)

        assert pattern_result is not None

        # MTF: 4h -> 1d, 1d is BULLISH
        context = FilterContext(
            kline=curr,
            current_timeframe="4h",
            higher_tf_trends={"1d": TrendDirection.BULLISH},
            current_trend=None
        )
        event = mtf_filter.check(pattern_result, context)

        assert event.passed == True
        assert event.reason == "mtf_confirmed_bullish"
        assert event.metadata["higher_timeframe"] == "1d"

    def test_t4_6_1w_no_higher_timeframe(self):
        """T4-6: 1w 无高周期 (自动通过)"""
        mtf_filter = MtfFilterDynamic(enabled=True)

        prev, curr = create_bullish_engulfing_pair()
        curr = create_kline(timeframe="1w", timestamp=2000,
            open=Decimal("98"), high=Decimal("103"),
            low=Decimal("97"), close=Decimal("102"))

        strategy = EngulfingStrategy()
        pattern_result = strategy.detect(curr, prev_kline=prev)

        assert pattern_result is not None

        # MTF: 1w -> no higher timeframe
        context = FilterContext(
            kline=curr,
            current_timeframe="1w",
            higher_tf_trends={},
            current_trend=None
        )
        event = mtf_filter.check(pattern_result, context)

        assert event.passed == True
        assert event.reason == "no_higher_timeframe"

    def test_mtf_higher_tf_data_unavailable(self):
        """Test when higher timeframe data is unavailable."""
        mtf_filter = MtfFilterDynamic(enabled=True)

        # Create valid engulfing pair with strict inequality
        prev = create_kline(
            open=Decimal("100"), high=Decimal("102"),
            low=Decimal("98"), close=Decimal("99"),  # 阴线，实体=1
            timeframe="15m", timestamp=1000
        )
        curr = create_kline(
            open=Decimal("98"), high=Decimal("103"),
            low=Decimal("97"), close=Decimal("101"),  # 阳线，实体=3，完全包覆
            timeframe="15m", timestamp=2000
        )

        strategy = EngulfingStrategy()
        pattern_result = strategy.detect(curr, prev_kline=prev)

        assert pattern_result is not None

        # MTF: 15m -> 1h, but 1h data not available
        context = FilterContext(
            kline=curr,
            current_timeframe="15m",
            higher_tf_trends={},  # Empty, no 1h data
            current_trend=None
        )
        event = mtf_filter.check(pattern_result, context)

        assert event.passed == False
        assert event.reason == "higher_tf_data_unavailable"

    def test_mtf_filter_disabled(self):
        """Test MTF filter when disabled."""
        mtf_filter = MtfFilterDynamic(enabled=False)

        # Create valid engulfing pair with strict inequality
        prev = create_kline(
            open=Decimal("100"), high=Decimal("102"),
            low=Decimal("98"), close=Decimal("99"),  # 阴线，实体=1
            timeframe="15m", timestamp=1000
        )
        curr = create_kline(
            open=Decimal("98"), high=Decimal("103"),
            low=Decimal("97"), close=Decimal("101"),  # 阳线，实体=3
            timeframe="15m", timestamp=2000
        )

        strategy = EngulfingStrategy()
        pattern_result = strategy.detect(curr, prev_kline=prev)

        assert pattern_result is not None

        context = FilterContext(
            kline=curr,
            current_timeframe="15m",
            higher_tf_trends={"1h": TrendDirection.BEARISH},  # Would fail if enabled
            current_trend=None
        )
        event = mtf_filter.check(pattern_result, context)

        assert event.passed == True
        assert event.reason == "filter_disabled"
