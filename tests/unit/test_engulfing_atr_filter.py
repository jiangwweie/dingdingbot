"""
Unit tests for Engulfing Strategy with ATR Filter - T2 测试。

测试覆盖:
- T2-1: 高波动通过 (atr_ratio=1.25)
- T2-2: 临界通过 (atr_ratio=0.5)
- T2-3: 低波幅过滤 (atr_ratio=0.25)
- T2-4: 绝对波幅过滤 (candle_range < 0.1)
- T2-5: ATR 数据未就绪 (降级通过)
- T2-6: 十字星 + 低波幅 (双重过滤)
"""
import pytest
from decimal import Decimal
from typing import Dict
from src.domain.models import KlineData, Direction, PatternResult, TrendDirection
from src.domain.strategies.engulfing_strategy import EngulfingStrategy
from src.domain.filter_factory import AtrFilterDynamic, FilterContext


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


def create_filter_context(kline: KlineData, timeframe: str = "15m") -> FilterContext:
    """Helper to create FilterContext."""
    return FilterContext(
        kline=kline,
        current_timeframe=timeframe,
        higher_tf_trends={},
        current_trend=TrendDirection.BULLISH
    )


class TestEngulfingWithAtrFilter:
    """T2: Engulfing Strategy with ATR Filter tests."""

    def test_t2_1_high_volatility_pass(self):
        """T2-1: 高波动通过 (ATR=400, candle_range=500, ratio=1.25)"""
        # Setup ATR filter
        atr_filter = AtrFilterDynamic(
            period=14,
            min_atr_ratio=Decimal("0.5"),
            min_absolute_range=Decimal("0.1"),
            enabled=True
        )

        # Setup ATR state
        atr_filter._atr_state["BTC/USDT:USDT:15m"] = {
            "tr_values": [Decimal("400")] * 14,
            "atr": Decimal("400"),
            "prev_close": Decimal("10000")
        }

        # Create engulfing pattern with high volatility
        # candle_range = 10300 - 9700 = 600, ratio = 600/400 = 1.5
        curr = create_kline(
            open=Decimal("9800"), high=Decimal("10300"),
            low=Decimal("9700"), close=Decimal("10200"),
            timestamp=2000
        )
        prev = create_kline(
            open=Decimal("9900"), high=Decimal("10000"),
            low=Decimal("9800"), close=Decimal("9850"),
            timestamp=1000
        )

        # Detect pattern
        strategy = EngulfingStrategy()
        pattern_result = strategy.detect(curr, prev_kline=prev, atr_value=Decimal("400"))

        assert pattern_result is not None
        assert pattern_result.direction == Direction.LONG

        # Run through ATR filter
        context = create_filter_context(curr)
        event = atr_filter.check(pattern_result, context)

        assert event.passed == True
        assert event.reason == "volatility_sufficient"

    def test_t2_2_critical_volatility_pass(self):
        """T2-2: 临界通过 (ATR=400, candle_range=200, ratio=0.5)"""
        atr_filter = AtrFilterDynamic(
            period=14,
            min_atr_ratio=Decimal("0.5"),
            min_absolute_range=Decimal("0.1"),
            enabled=True
        )

        atr_filter._atr_state["BTC/USDT:USDT:15m"] = {
            "tr_values": [Decimal("400")] * 14,
            "atr": Decimal("400"),
            "prev_close": Decimal("10000")
        }

        # candle_range = 200, ratio = 200/400 = 0.5 (exactly at threshold)
        curr = create_kline(
            open=Decimal("9900"), high=Decimal("10000"),
            low=Decimal("9800"), close=Decimal("9950"),
            timestamp=2000
        )

        pattern_result = PatternResult(
            strategy_name="engulfing",
            direction=Direction.LONG,
            score=0.6,
            details={}
        )

        context = create_filter_context(curr)
        event = atr_filter.check(pattern_result, context)

        assert event.passed == True
        assert event.reason == "volatility_sufficient"
        assert abs(event.metadata["ratio"] - 0.5) < 0.01

    def test_t2_3_low_volatility_filtered(self):
        """T2-3: 低波幅过滤 (ATR=400, candle_range=100, ratio=0.25)"""
        atr_filter = AtrFilterDynamic(
            period=14,
            min_atr_ratio=Decimal("0.5"),
            min_absolute_range=Decimal("0.1"),
            enabled=True
        )

        atr_filter._atr_state["BTC/USDT:USDT:15m"] = {
            "tr_values": [Decimal("400")] * 14,
            "atr": Decimal("400"),
            "prev_close": Decimal("10000")
        }

        # candle_range = 100, ratio = 100/400 = 0.25 < 0.5
        curr = create_kline(
            open=Decimal("9950"), high=Decimal("10000"),
            low=Decimal("9900"), close=Decimal("9970"),
            timestamp=2000
        )

        pattern_result = PatternResult(
            strategy_name="engulfing",
            direction=Direction.LONG,
            score=0.6,
            details={}
        )

        context = create_filter_context(curr)
        event = atr_filter.check(pattern_result, context)

        assert event.passed == False
        assert event.reason == "insufficient_volatility"
        assert abs(event.metadata["ratio"] - 0.25) < 0.01

    def test_t2_4_absolute_range_filtered(self):
        """T2-4: 绝对波幅过滤 (candle_range=0.05 < 0.1)"""
        atr_filter = AtrFilterDynamic(
            period=14,
            min_atr_ratio=Decimal("0.5"),
            min_absolute_range=Decimal("0.1"),
            enabled=True
        )

        atr_filter._atr_state["BTC/USDT:USDT:15m"] = {
            "tr_values": [Decimal("400")] * 14,
            "atr": Decimal("400"),
            "prev_close": Decimal("10000")
        }

        # candle_range = 0.05 < min_absolute_range (0.1)
        curr = create_kline(
            open=Decimal("100"), high=Decimal("100.03"),
            low=Decimal("99.98"), close=Decimal("100.01"),
            timestamp=2000
        )

        pattern_result = PatternResult(
            strategy_name="engulfing",
            direction=Direction.LONG,
            score=0.6,
            details={}
        )

        context = create_filter_context(curr)
        event = atr_filter.check(pattern_result, context)

        assert event.passed == False
        assert event.reason == "insufficient_absolute_volatility"
        assert event.metadata["candle_range"] == 0.05

    def test_t2_5_atr_data_not_ready(self):
        """T2-5: ATR 数据未就绪 (降级通过)"""
        atr_filter = AtrFilterDynamic(
            period=14,
            min_atr_ratio=Decimal("0.5"),
            min_absolute_range=Decimal("0.1"),
            enabled=True
        )

        # No ATR state setup

        curr = create_kline(
            open=Decimal("100"), high=Decimal("102"),
            low=Decimal("98"), close=Decimal("101"),
            timestamp=2000
        )

        pattern_result = PatternResult(
            strategy_name="engulfing",
            direction=Direction.LONG,
            score=0.6,
            details={}
        )

        context = create_filter_context(curr)
        event = atr_filter.check(pattern_result, context)

        assert event.passed == False
        assert event.reason == "atr_data_not_ready"

    def test_t2_6_doji_low_volatility_filtered(self):
        """T2-6: 十字星 + 低波幅 (双重过滤)"""
        atr_filter = AtrFilterDynamic(
            period=14,
            min_atr_ratio=Decimal("0.5"),
            min_absolute_range=Decimal("0.1"),
            enabled=True
        )

        atr_filter._atr_state["BTC/USDT:USDT:15m"] = {
            "tr_values": [Decimal("400")] * 14,
            "atr": Decimal("400"),
            "prev_close": Decimal("10000")
        }

        # Doji-like candle with very small body and range
        curr = create_kline(
            open=Decimal("10000"), high=Decimal("10010"),
            low=Decimal("9990"), close=Decimal("10001"),
            timestamp=2000
        )

        # First check if strategy detects it (should be None due to doji)
        prev = create_kline(
            open=Decimal("10000"), high=Decimal("10020"),
            low=Decimal("9980"), close=Decimal("9990"),
            timestamp=1000
        )

        strategy = EngulfingStrategy()
        pattern_result = strategy.detect(curr, prev_kline=prev, atr_value=Decimal("400"))

        # Should be filtered by strategy itself (doji)
        assert pattern_result is None


class TestEngulfingScoringWithAtr:
    """Test engulfing scoring with ATR adjustment."""

    def test_atr_bonus_scoring(self):
        """Test ATR bonus in scoring formula."""
        strategy = EngulfingStrategy()

        prev, curr = create_bullish_engulfing_pair()

        # With ATR value
        result_with_atr = strategy.detect(curr, prev_kline=prev, atr_value=Decimal("400"))

        assert result_with_atr is not None
        assert 0.5 <= result_with_atr.score <= 1.0
        assert "engulfing_ratio" in result_with_atr.details

    def test_no_atr_fallback_scoring(self):
        """Test fallback to legacy scoring when ATR is None."""
        strategy = EngulfingStrategy()

        prev, curr = create_bullish_engulfing_pair()

        # Without ATR value
        result_no_atr = strategy.detect(curr, prev_kline=prev, atr_value=None)

        assert result_no_atr is not None
        assert result_no_atr.score >= 0.5
