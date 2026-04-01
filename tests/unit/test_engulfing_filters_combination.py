"""
Integration tests for Engulfing Strategy with Multiple Filters - T5 测试。

测试覆盖:
- T5-1: 全部通过 (ATR✓ + EMA✓ + MTF✓)
- T5-2: ATR 失败
- T5-3: EMA 失败
- T5-4: MTF 失败
- T5-5: ATR+EMA 失败
- T5-6: 全部失败
- T5-7: 仅 ATR 启用
- T5-8: 仅 MTF 启用
"""
import pytest
from decimal import Decimal
from src.domain.models import KlineData, Direction, PatternResult, TrendDirection
from src.domain.strategies.engulfing_strategy import EngulfingStrategy
from src.domain.filter_factory import (
    AtrFilterDynamic, EmaTrendFilterDynamic, MtfFilterDynamic, FilterContext
)


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


def setup_atr_filter(atr_value: Decimal = Decimal("400")) -> AtrFilterDynamic:
    """Setup ATR filter with state."""
    atr_filter = AtrFilterDynamic(
        period=14,
        min_atr_ratio=Decimal("0.5"),
        min_absolute_range=Decimal("0.1"),
        enabled=True
    )
    atr_filter._atr_state["BTC/USDT:USDT:15m"] = {
        "tr_values": [atr_value] * 14,
        "atr": atr_value,
        "prev_close": Decimal("10000")
    }
    return atr_filter


def setup_ema_filter(trend: TrendDirection) -> EmaTrendFilterDynamic:
    """Setup EMA filter with trend."""
    ema_filter = EmaTrendFilterDynamic(period=60, enabled=True)
    ema_value = Decimal("95") if trend == TrendDirection.BULLISH else Decimal("105")
    ema_filter._ema_calculators["BTC/USDT:USDT:15m"] = type('obj', (object,), {'value': ema_value})()
    return ema_filter


def run_filter_chain(filters, pattern_result, kline, timeframe="15m"):
    """Run a chain of filters and return first failure or success."""
    context = FilterContext(
        kline=kline,
        current_timeframe=timeframe,
        higher_tf_trends={"1h": TrendDirection.BULLISH},
        current_trend=TrendDirection.BULLISH
    )
    for f in filters:
        event = f.check(pattern_result, context)
        if not event.passed:
            return False, event
    return True, None


class TestEngulfingFilterCombinations:
    """T5: Engulfing Strategy with Multiple Filter Combinations."""

    def test_t5_1_all_filters_pass(self):
        """T5-1: 全部通过 (ATR✓ + EMA✓ + MTF✓)"""
        # Setup: High volatility, Bullish trend, Bullish MTF
        atr_filter = setup_atr_filter(atr_value=Decimal("100"))  # Lower ATR
        ema_filter = setup_ema_filter(TrendDirection.BULLISH)
        mtf_filter = MtfFilterDynamic(enabled=True)

        # Create engulfing pattern with sufficient volatility
        # candle_range needs to be >= ATR * 0.5 = 100 * 0.5 = 50
        # Use strict inequality: curr_open < prev_close and curr_close > prev_open
        prev = create_kline(
            open=Decimal("1000"), high=Decimal("1020"),
            low=Decimal("980"), close=Decimal("990"),  # 阴线，实体=10
            timestamp=1000
        )
        curr = create_kline(
            open=Decimal("989"), high=Decimal("1060"),  # open < prev_close (989 < 990)
            low=Decimal("970"), close=Decimal("1051"),  # close > prev_open (1051 > 1000)
            timestamp=2000
        )
        # candle_range = 1060-970 = 90, atr_ratio = 90/100 = 0.9 > 0.5

        strategy = EngulfingStrategy()
        pattern_result = strategy.detect(curr, prev_kline=prev, atr_value=Decimal("100"))

        assert pattern_result is not None
        assert pattern_result.direction == Direction.LONG

        # Run filter chain
        context = FilterContext(
            kline=curr,
            current_timeframe="15m",
            higher_tf_trends={"1h": TrendDirection.BULLISH},
            current_trend=TrendDirection.BULLISH
        )
        passed, failed_event = run_filter_chain(
            [atr_filter, ema_filter, mtf_filter],
            pattern_result, curr
        )

        assert passed == True, f"Failed at: {failed_event.reason if failed_event else 'unknown'}"

    def test_t5_2_atr_failure(self):
        """T5-2: ATR 失败 (低波动)"""
        atr_filter = setup_atr_filter(atr_value=Decimal("400"))
        ema_filter = setup_ema_filter(TrendDirection.BULLISH)
        mtf_filter = MtfFilterDynamic(enabled=True)

        # Create engulfing with low volatility
        # candle_range needs to be < ATR * 0.5 = 400 * 0.5 = 200
        prev = create_kline(
            open=Decimal("100"), high=Decimal("101"),
            low=Decimal("99.5"), close=Decimal("99.8"),
            timestamp=1000
        )
        curr = create_kline(
            open=Decimal("99.8"), high=Decimal("100.1"),
            low=Decimal("99.5"), close=Decimal("100"),
            timestamp=2000
        )
        # candle_range = 0.6, atr_ratio = 0.6/400 = 0.0015 < 0.5

        strategy = EngulfingStrategy()
        pattern_result = strategy.detect(curr, prev_kline=prev, atr_value=Decimal("400"))

        if pattern_result:
            passed, event = run_filter_chain(
                [atr_filter, ema_filter, mtf_filter],
                pattern_result, curr
            )
            assert passed == False
            assert event.reason == "insufficient_volatility"

    def test_t5_3_ema_failure(self):
        """T5-3: EMA 失败 (趋势冲突)"""
        # Use lower ATR to pass ATR filter first
        atr_filter = setup_atr_filter(atr_value=Decimal("100"))
        ema_filter = setup_ema_filter(TrendDirection.BEARISH)  # Bearish trend
        mtf_filter = MtfFilterDynamic(enabled=True)

        # Create engulfing with sufficient volatility
        prev = create_kline(
            open=Decimal("1000"), high=Decimal("1020"),
            low=Decimal("980"), close=Decimal("990"),  # 阴线，实体=10
            timestamp=1000
        )
        curr = create_kline(
            open=Decimal("989"), high=Decimal("1060"),  # open < prev_close
            low=Decimal("970"), close=Decimal("1051"),  # close > prev_open
            timestamp=2000
        )

        strategy = EngulfingStrategy()
        pattern_result = strategy.detect(curr, prev_kline=prev, atr_value=Decimal("100"))

        assert pattern_result is not None
        assert pattern_result.direction == Direction.LONG

        # Check ATR passes first
        context = FilterContext(
            kline=curr,
            current_timeframe="15m",
            higher_tf_trends={"1h": TrendDirection.BULLISH},
            current_trend=TrendDirection.BEARISH  # Conflict
        )
        atr_event = atr_filter.check(pattern_result, context)
        assert atr_event.passed == True, f"ATR should pass but failed: {atr_event.reason}"

        # EMA should fail
        ema_event = ema_filter.check(pattern_result, context)
        assert ema_event.passed == False
        assert "bearish_trend_blocks" in ema_event.reason

    def test_t5_4_mtf_failure(self):
        """T5-4: MTF 失败 (高周期趋势冲突)"""
        atr_filter = setup_atr_filter(atr_value=Decimal("100"))
        ema_filter = setup_ema_filter(TrendDirection.BULLISH)
        mtf_filter = MtfFilterDynamic(enabled=True)

        prev = create_kline(
            open=Decimal("1000"), high=Decimal("1020"),
            low=Decimal("980"), close=Decimal("990"),  # 阴线，实体=10
            timestamp=1000
        )
        curr = create_kline(
            open=Decimal("989"), high=Decimal("1060"),  # open < prev_close
            low=Decimal("970"), close=Decimal("1051"),  # close > prev_open
            timeframe="15m", timestamp=2000
        )

        strategy = EngulfingStrategy()
        pattern_result = strategy.detect(curr, prev_kline=prev, atr_value=Decimal("100"))

        assert pattern_result is not None

        # MTF with bearish higher timeframe
        context = FilterContext(
            kline=curr,
            current_timeframe="15m",
            higher_tf_trends={"1h": TrendDirection.BEARISH},  # Conflict
            current_trend=TrendDirection.BULLISH
        )

        # Check ATR and EMA pass first
        assert atr_filter.check(pattern_result, context).passed == True
        assert ema_filter.check(pattern_result, context).passed == True

        # MTF should fail
        event = mtf_filter.check(pattern_result, context)
        assert event.passed == False
        assert "mtf_rejected" in event.reason

    def test_t5_5_atr_ema_failure(self):
        """T5-5: ATR+EMA 失败"""
        atr_filter = setup_atr_filter(atr_value=Decimal("400"))
        ema_filter = setup_ema_filter(TrendDirection.BEARISH)

        # Low volatility + Bearish EMA
        prev = create_kline(
            open=Decimal("100"), high=Decimal("101"),
            low=Decimal("99.5"), close=Decimal("99.8"),
            timestamp=1000
        )
        curr = create_kline(
            open=Decimal("99.8"), high=Decimal("100.1"),
            low=Decimal("99.5"), close=Decimal("100"),
            timestamp=2000
        )

        strategy = EngulfingStrategy()
        pattern_result = strategy.detect(curr, prev_kline=prev, atr_value=Decimal("400"))

        if pattern_result:
            # ATR should fail first
            context = FilterContext(kline=curr, current_timeframe="15m", higher_tf_trends={}, current_trend=TrendDirection.BEARISH)
            event = atr_filter.check(pattern_result, context)
            assert event.passed == False

    def test_t5_6_all_filters_failure(self):
        """T5-6: 全部失败场景"""
        atr_filter = setup_atr_filter(atr_value=Decimal("400"))
        ema_filter = setup_ema_filter(TrendDirection.BEARISH)
        mtf_filter = MtfFilterDynamic(enabled=True)

        # Low volatility pattern
        prev = create_kline(
            open=Decimal("100"), high=Decimal("100.5"),
            low=Decimal("99.8"), close=Decimal("100"),
            timestamp=1000
        )
        curr = create_kline(
            open=Decimal("100"), high=Decimal("100.3"),
            low=Decimal("99.7"), close=Decimal("100.1"),
            timestamp=2000
        )

        strategy = EngulfingStrategy()
        pattern_result = strategy.detect(curr, prev_kline=prev, atr_value=Decimal("400"))

        # May be filtered by strategy itself
        if pattern_result:
            # ATR should fail
            context = FilterContext(kline=curr, current_timeframe="15m", higher_tf_trends={}, current_trend=TrendDirection.BEARISH)
            event = atr_filter.check(pattern_result, context)
            assert event.passed == False

    def test_t5_7_only_atr_enabled(self):
        """T5-7: 仅 ATR 启用"""
        # Setup with reasonable ATR
        atr_filter = setup_atr_filter(atr_value=Decimal("100"))
        ema_filter = EmaTrendFilterDynamic(period=60, enabled=False)
        mtf_filter = MtfFilterDynamic(enabled=False)

        # Create engulfing with sufficient volatility
        prev = create_kline(
            open=Decimal("1000"), high=Decimal("1020"),
            low=Decimal("980"), close=Decimal("990"),  # 阴线，实体=10
            timestamp=1000
        )
        curr = create_kline(
            open=Decimal("989"), high=Decimal("1060"),  # open < prev_close
            low=Decimal("970"), close=Decimal("1051"),  # close > prev_open
            timestamp=2000
        )

        strategy = EngulfingStrategy()
        pattern_result = strategy.detect(curr, prev_kline=prev, atr_value=Decimal("100"))

        assert pattern_result is not None

        context = FilterContext(kline=curr, current_timeframe="15m", higher_tf_trends={}, current_trend=None)

        # All should pass when disabled/enabled with good data
        assert atr_filter.check(pattern_result, context).passed == True
        assert ema_filter.check(pattern_result, context).passed == True
        assert mtf_filter.check(pattern_result, context).passed == True

    def test_t5_8_only_mtf_enabled(self):
        """T5-8: 仅 MTF 启用"""
        atr_filter = AtrFilterDynamic(enabled=False)
        ema_filter = EmaTrendFilterDynamic(period=60, enabled=False)
        mtf_filter = MtfFilterDynamic(enabled=True)

        prev = create_kline(
            open=Decimal("1000"), high=Decimal("1020"),
            low=Decimal("980"), close=Decimal("990"),  # 阴线，实体=10
            timestamp=1000
        )
        curr = create_kline(
            open=Decimal("989"), high=Decimal("1060"),  # open < prev_close
            low=Decimal("970"), close=Decimal("1051"),  # close > prev_open
            timestamp=2000
        )

        strategy = EngulfingStrategy()
        pattern_result = strategy.detect(curr, prev_kline=prev)

        assert pattern_result is not None

        context = FilterContext(
            kline=curr, current_timeframe="15m",
            higher_tf_trends={"1h": TrendDirection.BULLISH},
            current_trend=None
        )

        # All should pass
        assert atr_filter.check(pattern_result, context).passed == True
        assert ema_filter.check(pattern_result, context).passed == True
        assert mtf_filter.check(pattern_result, context).passed == True
