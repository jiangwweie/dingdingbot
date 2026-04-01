"""
Unit tests for Engulfing Strategy with EMA Filter - T3 测试。

测试覆盖:
- T3-1: 趋势匹配 - 多头 (EMA BULLISH, 信号 LONG)
- T3-2: 趋势匹配 - 空头 (EMA BEARISH, 信号 SHORT)
- T3-3: 趋势冲突 - 多头 (EMA BULLISH, 信号 SHORT)
- T3-4: 趋势冲突 - 空头 (EMA BEARISH, 信号 LONG)
"""
import pytest
from decimal import Decimal
from typing import Dict
from src.domain.models import KlineData, Direction, PatternResult, TrendDirection
from src.domain.strategies.engulfing_strategy import EngulfingStrategy
from src.domain.filter_factory import EmaTrendFilterDynamic, FilterContext


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
        low=Decimal("98"), close=Decimal("99"),  # 阴线
        timestamp=1000
    )
    curr = create_kline(
        open=Decimal("98"), high=Decimal("103"),
        low=Decimal("97"), close=Decimal("102"),  # 阳线包覆
        timestamp=2000
    )
    return prev, curr


def create_bearish_engulfing_pair() -> tuple:
    """Create a standard bearish engulfing pattern."""
    prev = create_kline(
        open=Decimal("99"), high=Decimal("102"),
        low=Decimal("98"), close=Decimal("100"),  # 阳线
        timestamp=1000
    )
    curr = create_kline(
        open=Decimal("101"), high=Decimal("103"),
        low=Decimal("97"), close=Decimal("98"),  # 阴线包覆
        timestamp=2000
    )
    return prev, curr


class TestEngulfingWithEmaFilter:
    """T3: Engulfing Strategy with EMA Trend Filter tests."""

    def test_t3_1_bullish_trend_match(self):
        """T3-1: 趋势匹配 - 多头 (EMA BULLISH, 信号 LONG)"""
        ema_filter = EmaTrendFilterDynamic(period=60, enabled=True)

        # Setup EMA state: price > EMA = BULLISH
        ema_filter._ema_calculators["BTC/USDT:USDT:15m"] = type('obj', (object,), {'value': Decimal("95")})()

        prev, curr = create_bullish_engulfing_pair()

        strategy = EngulfingStrategy()
        pattern_result = strategy.detect(curr, prev_kline=prev)

        assert pattern_result is not None
        assert pattern_result.direction == Direction.LONG

        # Run through EMA filter
        context = FilterContext(
            kline=curr,
            current_timeframe="15m",
            higher_tf_trends={},
            current_trend=TrendDirection.BULLISH  # EMA indicates bullish
        )
        event = ema_filter.check(pattern_result, context)

        assert event.passed == True
        assert event.reason == "trend_match"
        assert event.expected == "bullish"
        assert event.actual == "bullish"

    def test_t3_2_bearish_trend_match(self):
        """T3-2: 趋势匹配 - 空头 (EMA BEARISH, 信号 SHORT)"""
        ema_filter = EmaTrendFilterDynamic(period=60, enabled=True)

        # Setup EMA state: price < EMA = BEARISH
        ema_filter._ema_calculators["BTC/USDT:USDT:15m"] = type('obj', (object,), {'value': Decimal("105")})()

        prev, curr = create_bearish_engulfing_pair()

        strategy = EngulfingStrategy()
        pattern_result = strategy.detect(curr, prev_kline=prev)

        assert pattern_result is not None
        assert pattern_result.direction == Direction.SHORT

        # Run through EMA filter
        context = FilterContext(
            kline=curr,
            current_timeframe="15m",
            higher_tf_trends={},
            current_trend=TrendDirection.BEARISH  # EMA indicates bearish
        )
        event = ema_filter.check(pattern_result, context)

        assert event.passed == True
        assert event.reason == "trend_match"
        assert event.expected == "bearish"
        assert event.actual == "bearish"

    def test_t3_3_bullish_trend_blocks_short(self):
        """T3-3: 趋势冲突 - 多头趋势阻止做空信号"""
        ema_filter = EmaTrendFilterDynamic(period=60, enabled=True)

        # Setup EMA state: price > EMA = BULLISH
        ema_filter._ema_calculators["BTC/USDT:USDT:15m"] = type('obj', (object,), {'value': Decimal("95")})()

        prev, curr = create_bearish_engulfing_pair()

        strategy = EngulfingStrategy()
        pattern_result = strategy.detect(curr, prev_kline=prev)

        assert pattern_result is not None
        assert pattern_result.direction == Direction.SHORT

        # Run through EMA filter - should fail
        context = FilterContext(
            kline=curr,
            current_timeframe="15m",
            higher_tf_trends={},
            current_trend=TrendDirection.BULLISH  # EMA bullish, signal bearish
        )
        event = ema_filter.check(pattern_result, context)

        assert event.passed == False
        assert event.reason == "bullish_trend_blocks_short"
        assert event.expected == "bearish"
        assert event.actual == "bullish"

    def test_t3_4_bearish_trend_blocks_short(self):
        """T3-4: 趋势冲突 - 空头趋势阻止做多信号"""
        ema_filter = EmaTrendFilterDynamic(period=60, enabled=True)

        # Setup EMA state: price < EMA = BEARISH
        ema_filter._ema_calculators["BTC/USDT:USDT:15m"] = type('obj', (object,), {'value': Decimal("105")})()

        prev, curr = create_bullish_engulfing_pair()

        strategy = EngulfingStrategy()
        pattern_result = strategy.detect(curr, prev_kline=prev)

        assert pattern_result is not None
        assert pattern_result.direction == Direction.LONG

        # Run through EMA filter - should fail
        context = FilterContext(
            kline=curr,
            current_timeframe="15m",
            higher_tf_trends={},
            current_trend=TrendDirection.BEARISH  # EMA bearish, signal bullish
        )
        event = ema_filter.check(pattern_result, context)

        assert event.passed == False
        assert event.reason == "bearish_trend_blocks_long"
        assert event.expected == "bullish"
        assert event.actual == "bearish"

    def test_ema_data_not_ready(self):
        """Test when EMA data is not ready."""
        ema_filter = EmaTrendFilterDynamic(period=60, enabled=True)

        # No EMA state setup

        prev, curr = create_bullish_engulfing_pair()

        strategy = EngulfingStrategy()
        pattern_result = strategy.detect(curr, prev_kline=prev)

        assert pattern_result is not None

        context = FilterContext(
            kline=curr,
            current_timeframe="15m",
            higher_tf_trends={},
            current_trend=None  # No EMA data
        )
        event = ema_filter.check(pattern_result, context)

        assert event.passed == False
        assert event.reason == "ema_data_not_ready"

    def test_ema_filter_disabled(self):
        """Test EMA filter when disabled."""
        ema_filter = EmaTrendFilterDynamic(period=60, enabled=False)

        prev, curr = create_bullish_engulfing_pair()

        strategy = EngulfingStrategy()
        pattern_result = strategy.detect(curr, prev_kline=prev)

        assert pattern_result is not None

        context = FilterContext(
            kline=curr,
            current_timeframe="15m",
            higher_tf_trends={},
            current_trend=None
        )
        event = ema_filter.check(pattern_result, context)

        assert event.passed == True
        assert event.reason == "filter_disabled"
