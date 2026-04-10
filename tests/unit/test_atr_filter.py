"""
Unit tests for ATR Filter (S6-2-1).

Tests:
1. ATR calculation using Wilder's smoothing method
2. ATR filter check logic (volatility threshold)
3. Integration with FilterFactory
"""
import pytest
from decimal import Decimal
from src.domain.filter_factory import AtrFilterDynamic, FilterFactory, FilterContext, EmaTrendFilterDynamic, MtfFilterDynamic
from src.domain.models import KlineData, TrendDirection, PatternResult, Direction


def create_kline(
    symbol: str = "BTC/USDT:USDT",
    timeframe: str = "15m",
    timestamp: int = 1000000,
    open: Decimal = Decimal("50000"),
    high: Decimal = Decimal("50100"),
    low: Decimal = Decimal("49900"),
    close: Decimal = Decimal("50050"),
    volume: Decimal = Decimal("1000"),
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
        volume=volume,
        is_closed=True,
    )


class TestAtrCalculation:
    """Test ATR calculation using Wilder's smoothing method."""

    def test_atr_initialization(self):
        """Test ATR filter initializes correctly."""
        filter = AtrFilterDynamic(period=14, min_atr_ratio=Decimal("0.5"), enabled=True)
        assert filter.name == "atr_volatility"
        assert filter.is_stateful is True
        assert filter._period == 14
        assert filter._min_atr_ratio == Decimal("0.5")

    def test_atr_first_bar(self):
        """Test ATR calculation for first bar (TR = high - low)."""
        filter = AtrFilterDynamic(period=14, enabled=True)
        kline = create_kline(high=Decimal("50100"), low=Decimal("49900"))

        filter.update_state(kline, kline.symbol, kline.timeframe)
        # First bar: ATR should be None (need period bars)
        assert filter._get_atr(kline.symbol, kline.timeframe) is None

    def test_atr_wilders_smoothing(self):
        """Test ATR calculation using Wilder's smoothing method."""
        period = 5
        filter = AtrFilterDynamic(period=period, enabled=True)

        # Create consistent klines with TR = 100
        for i in range(period + 2):
            kline = create_kline(
                timestamp=i * 1000,
                high=Decimal("50100"),
                low=Decimal("50000"),
                close=Decimal("50050"),
            )
            filter.update_state(kline, kline.symbol, kline.timeframe)

        # After period bars, ATR should be calculated
        atr = filter._get_atr(kline.symbol, kline.timeframe)
        assert atr is not None
        # First ATR = simple average of TR values = 100
        assert atr == Decimal("100")

    def test_atr_needs_warmup(self):
        """Test that ATR needs period bars to be ready."""
        period = 14
        filter = AtrFilterDynamic(period=period, enabled=True)

        # Feed less than period bars
        for i in range(period - 1):
            kline = create_kline(timestamp=i * 1000)
            filter.update_state(kline, kline.symbol, kline.timeframe)

        # ATR should still be None
        assert filter._get_atr(kline.symbol, kline.timeframe) is None

        # Feed one more bar
        kline = create_kline(timestamp=period * 1000)
        filter.update_state(kline, kline.symbol, kline.timeframe)

        # Now ATR should be ready
        atr = filter._get_atr(kline.symbol, kline.timeframe)
        assert atr is not None


class TestAtrFilterCheck:
    """Test ATR filter check logic."""

    def test_filter_disabled(self):
        """Test that disabled filter always passes."""
        filter = AtrFilterDynamic(enabled=False)
        pattern = PatternResult(
            strategy_name="pinbar",
            direction=Direction.LONG,
            score=0.7,
            details={}
        )
        context = FilterContext(
            higher_tf_trends={},
            kline=create_kline()
        )

        event = filter.check(pattern, context)
        assert event.passed is True
        assert event.reason == "filter_disabled"

    def test_filter_kline_missing(self):
        """Test that filter fails when kline is None."""
        filter = AtrFilterDynamic(enabled=True)
        pattern = PatternResult(
            strategy_name="pinbar",
            direction=Direction.LONG,
            score=0.7,
            details={}
        )
        context = FilterContext(
            higher_tf_trends={},
            kline=None
        )

        event = filter.check(pattern, context)
        assert event.passed is False
        assert event.reason == "kline_data_missing"

    def test_filter_atr_not_ready(self):
        """Test that filter fails when ATR data not ready."""
        filter = AtrFilterDynamic(period=14, enabled=True)
        pattern = PatternResult(
            strategy_name="pinbar",
            direction=Direction.LONG,
            score=0.7,
            details={}
        )
        kline = create_kline()
        context = FilterContext(
            higher_tf_trends={},
            kline=kline
        )

        # Only feed 1 bar (need 14)
        filter.update_state(kline, kline.symbol, kline.timeframe)

        event = filter.check(pattern, context)
        assert event.passed is False
        assert event.reason == "atr_data_not_ready"

    def test_filter_passes_high_volatility(self):
        """Test that filter passes when volatility is sufficient."""
        filter = AtrFilterDynamic(period=5, min_atr_ratio=Decimal("0.5"), enabled=True)

        # Feed enough bars for ATR
        for i in range(10):
            kline = create_kline(
                timestamp=i * 1000,
                high=Decimal("50400"),  # High volatility: 400 range
                low=Decimal("50000"),
            )
            filter.update_state(kline, kline.symbol, kline.timeframe)

        # Create pattern with high volatility
        pattern = PatternResult(
            strategy_name="pinbar",
            direction=Direction.LONG,
            score=0.7,
            details={}
        )
        context = FilterContext(
            higher_tf_trends={},
            kline=kline
        )

        event = filter.check(pattern, context)
        assert event.passed is True
        assert event.reason == "volatility_sufficient"
        assert event.metadata.get("volatility_ratio", 0) >= 0.5

    def test_filter_fails_low_volatility(self):
        """Test that filter fails when volatility is insufficient (十字星)."""
        filter = AtrFilterDynamic(period=5, min_atr_ratio=Decimal("0.5"), enabled=True)

        # Feed enough bars with high ATR
        for i in range(5):
            kline = create_kline(
                timestamp=i * 1000,
                high=Decimal("50400"),  # ATR ~= 400
                low=Decimal("50000"),
            )
            filter.update_state(kline, kline.symbol, kline.timeframe)

        # Create a 十字星 pattern with very low range
        doji_kline = create_kline(
            timestamp=5 * 1000,
            high=Decimal("50100"),  # Range = 100, ratio = 100/400 = 0.25 < 0.5
            low=Decimal("50000"),
        )
        filter.update_state(doji_kline, doji_kline.symbol, doji_kline.timeframe)

        pattern = PatternResult(
            strategy_name="pinbar",
            direction=Direction.LONG,
            score=0.7,
            details={}
        )
        context = FilterContext(
            higher_tf_trends={},
            kline=doji_kline
        )

        event = filter.check(pattern, context)
        assert event.passed is False
        assert event.reason == "insufficient_volatility"
        assert event.metadata.get("volatility_ratio", 1) < 0.5


class TestFilterFactoryIntegration:
    """Test FilterFactory integration for ATR filter."""

    def test_create_atr_from_dict(self):
        """Test creating ATR filter from dict config."""
        config = {
            "type": "atr",
            "enabled": True,
            "params": {
                "period": 14,
                "min_atr_ratio": Decimal("0.5"),
            }
        }

        filter = FilterFactory.create(config)
        assert isinstance(filter, AtrFilterDynamic)
        assert filter.name == "atr_volatility"
        assert filter._period == 14
        assert filter._min_atr_ratio == Decimal("0.5")
        assert filter._enabled is True

    def test_create_atr_with_defaults(self):
        """Test creating ATR filter with default params."""
        config = {
            "type": "atr",
            "enabled": True,
        }

        filter = FilterFactory.create(config)
        assert isinstance(filter, AtrFilterDynamic)
        assert filter._period == 14  # Default
        assert filter._min_atr_ratio == Decimal("0.001")  # Default

    def test_create_atr_chain(self):
        """Test creating filter chain with ATR."""
        configs = [
            {"type": "ema", "enabled": True, "params": {"period": 60}},
            {"type": "atr", "enabled": True, "params": {"period": 14, "min_atr_ratio": Decimal("0.5")}},
            {"type": "mtf", "enabled": True},
        ]

        filters = FilterFactory.create_chain(configs)
        assert len(filters) == 3
        assert isinstance(filters[0], EmaTrendFilterDynamic)
        assert isinstance(filters[1], AtrFilterDynamic)
        assert isinstance(filters[2], MtfFilterDynamic)


class TestAtrFilterEndToEnd:
    """End-to-end test simulating the user's scenario."""

    def test_cross_star_filtered_high_breakthrough_passes(self):
        """
        Test the user's scenario:
        - 21:00 十字星：Score 0.727, 波幅 116 USDT, ATR 比值 0.29 -> 被过滤
        - 22:00 真突破：Score 0.715, 波幅 527 USDT, ATR 比值 1.32 -> 通过
        """
        # Setup: ATR ~= 400 USDT
        filter = AtrFilterDynamic(period=5, min_atr_ratio=Decimal("0.5"), enabled=True)

        # Warmup with consistent bars to establish ATR ~= 400
        for i in range(10):
            kline = create_kline(
                timestamp=i * 3600000,  # 1h bars
                high=Decimal("50400"),
                low=Decimal("50000"),
            )
            filter.update_state(kline, kline.symbol, kline.timeframe)

        # 21:00 十字星：波幅 116 USDT
        cross_star_kline = create_kline(
            timestamp=21 * 3600000,
            high=Decimal("50116"),  # Range = 116
            low=Decimal("50000"),
            close=Decimal("50058"),
        )
        filter.update_state(cross_star_kline, cross_star_kline.symbol, cross_star_kline.timeframe)

        pattern = PatternResult(
            strategy_name="pinbar",
            direction=Direction.LONG,
            score=0.727,
            details={"wick_ratio": 0.727}
        )
        context = FilterContext(higher_tf_trends={}, kline=cross_star_kline)

        event = filter.check(pattern, context)
        # 十字星 should be filtered: ratio = 116/400 = 0.29 < 0.5
        assert event.passed is False, f"十字星 should be filtered, got {event.reason}"
        assert event.metadata.get("volatility_ratio", 1) < 0.5

        # 22:00 真突破：波幅 527 USDT
        breakthrough_kline = create_kline(
            timestamp=22 * 3600000,
            high=Decimal("50527"),  # Range = 527
            low=Decimal("50000"),
            close=Decimal("50400"),
        )
        filter.update_state(breakthrough_kline, breakthrough_kline.symbol, breakthrough_kline.timeframe)

        pattern2 = PatternResult(
            strategy_name="pinbar",
            direction=Direction.LONG,
            score=0.715,
            details={"wick_ratio": 0.715}
        )
        context2 = FilterContext(higher_tf_trends={}, kline=breakthrough_kline)

        event2 = filter.check(pattern2, context2)
        # 真突破 should pass: ratio = 527/400 = 1.32 > 0.5
        assert event2.passed is True, f"真突破 should pass, got {event2.reason}"
        assert event2.metadata.get("volatility_ratio", 0) > 0.5
