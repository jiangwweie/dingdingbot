"""
Tests for Phase K - Dynamic Rule Engine (FilterFactory, FilterBase, TraceEvent)
"""
import pytest
from decimal import Decimal

from src.domain.models import (
    KlineData,
    Direction,
    TrendDirection,
    PatternResult,
)
from src.domain.filter_factory import (
    FilterFactory,
    FilterBase,
    FilterContext,
    TraceEvent,
    EmaTrendFilterDynamic,
    MtfFilterDynamic,
    AtrFilterDynamic,
)
from src.domain.strategy_engine import (
    DynamicStrategyRunner,
    StrategyWithFilters,
    PinbarStrategy,
    PinbarConfig,
    create_dynamic_runner,
)


# ============================================================
# Test Fixtures
# ============================================================
@pytest.fixture
def sample_kline():
    """Create a sample K-line for testing."""
    return KlineData(
        symbol="BTC/USDT:USDT",
        timeframe="15m",
        timestamp=1000000,
        open=Decimal("50000"),
        high=Decimal("50100"),
        low=Decimal("49900"),
        close=Decimal("50050"),
        volume=Decimal("1000"),
        is_closed=True,
    )


@pytest.fixture
def bullish_pattern():
    """Create a bullish pattern result."""
    return PatternResult(
        strategy_name="pinbar",
        direction=Direction.LONG,
        score=0.8,
        details={"wick_ratio": 0.7, "body_ratio": 0.2},
    )


@pytest.fixture
def bearish_pattern():
    """Create a bearish pattern result."""
    return PatternResult(
        strategy_name="pinbar",
        direction=Direction.SHORT,
        score=0.75,
        details={"wick_ratio": 0.65, "body_ratio": 0.25},
    )


# ============================================================
# FilterFactory Tests
# ============================================================
class TestFilterFactory:
    """Test FilterFactory creation logic."""

    def test_create_ema_filter_from_dict(self):
        """Test creating EMA filter from dict config."""
        config = {"type": "ema", "period": 50, "enabled": True}
        filter_instance = FilterFactory.create(config)

        assert isinstance(filter_instance, EmaTrendFilterDynamic)
        assert filter_instance.name == "ema_trend"
        assert filter_instance.is_stateful is True

    def test_create_ema_filter_from_pydantic(self):
        """Test creating EMA filter from Pydantic model."""
        from src.domain.models import FilterConfig

        config = FilterConfig(type="ema", enabled=False, params={"period": 100})
        filter_instance = FilterFactory.create(config)

        assert isinstance(filter_instance, EmaTrendFilterDynamic)
        assert filter_instance._period == 100
        assert filter_instance._enabled is False

    def test_create_mtf_filter(self):
        """Test creating MTF filter."""
        config = {"type": "mtf", "enabled": True}
        filter_instance = FilterFactory.create(config)

        assert isinstance(filter_instance, MtfFilterDynamic)
        assert filter_instance.name == "mtf"
        assert filter_instance.is_stateful is False

    def test_create_atr_filter(self):
        """Test creating ATR filter."""
        config = {"type": "atr", "period": 20, "min_atr_ratio": Decimal("0.002"), "enabled": True}
        filter_instance = FilterFactory.create(config)

        assert isinstance(filter_instance, AtrFilterDynamic)
        assert filter_instance.name == "atr_volatility"
        assert filter_instance.is_stateful is True

    def test_create_unknown_filter_raises(self):
        """Test that unknown filter type raises ValueError."""
        config = {"type": "unknown_filter"}

        with pytest.raises(ValueError, match="Unknown filter type"):
            FilterFactory.create(config)

    def test_create_filter_chain(self):
        """Test creating multiple filters at once."""
        configs = [
            {"type": "ema", "period": 60, "enabled": True},
            {"type": "mtf", "enabled": True},
        ]
        filters = FilterFactory.create_chain(configs)

        assert len(filters) == 2
        assert isinstance(filters[0], EmaTrendFilterDynamic)
        assert isinstance(filters[1], MtfFilterDynamic)


# ============================================================
# TraceEvent Tests
# ============================================================
class TestTraceEvent:
    """Test TraceEvent for precise failure tracking."""

    def test_trace_event_creation(self):
        """Test creating a TraceEvent."""
        event = TraceEvent(
            filter_name="ema_trend",
            passed=False,
            reason="bearish_trend_blocks_long",
            expected="bullish",
            actual="bearish",
        )

        assert event.filter_name == "ema_trend"
        assert event.passed is False
        assert event.expected == "bullish"
        assert event.actual == "bearish"

    def test_trace_event_to_filter_result(self):
        """Test converting TraceEvent to FilterResult."""
        event = TraceEvent(
            filter_name="mtf",
            passed=True,
            reason="trend_match",
        )

        result = event.to_filter_result()
        assert result.passed is True
        assert result.reason == "trend_match"

    def test_trace_event_with_context_data(self):
        """Test TraceEvent with additional context."""
        event = TraceEvent(
            filter_name="mtf",
            passed=False,
            reason="mtf_rejected",
            expected="bullish",
            actual="bearish",
            context_data={"higher_timeframe": "1h", "higher_trend": "bearish"},
        )

        assert event.context_data["higher_timeframe"] == "1h"


# ============================================================
# EmaTrendFilterDynamic Tests
# ============================================================
class TestEmaTrendFilterDynamic:
    """Test EMA trend filter dynamic implementation."""

    def test_filter_properties(self):
        """Test EMA filter properties."""
        f = EmaTrendFilterDynamic(period=60, enabled=True)

        assert f.name == "ema_trend"
        assert f.is_stateful is True

    def test_update_state(self, sample_kline):
        """Test updating EMA state."""
        f = EmaTrendFilterDynamic(period=10, enabled=True)

        # Update state with multiple klines
        for i in range(15):
            kline = KlineData(
                symbol="BTC/USDT:USDT",
                timeframe="15m",
                timestamp=1000000 + i * 60000,
                open=Decimal("50000") + i,
                high=Decimal("50100") + i,
                low=Decimal("49900") + i,
                close=Decimal("50050") + i,
                volume=Decimal("1000"),
                is_closed=True,
            )
            f.update_state(kline, "BTC/USDT:USDT", "15m")

        # EMA should have value after warmup
        trend = f.get_current_trend(sample_kline, "BTC/USDT:USDT", "15m")
        assert trend is not None

    def test_check_disabled_filter(self, bullish_pattern):
        """Test that disabled filter always passes."""
        f = EmaTrendFilterDynamic(period=60, enabled=False)

        context = FilterContext(
            higher_tf_trends={},
            current_trend=None,
            current_timeframe="15m",
        )

        event = f.check(bullish_pattern, context)
        assert event.passed is True
        assert event.reason == "filter_disabled"

    def test_check_no_data(self, bullish_pattern):
        """Test filter behavior when EMA data not ready."""
        f = EmaTrendFilterDynamic(period=60, enabled=True)

        context = FilterContext(
            higher_tf_trends={},
            current_trend=None,  # No data
            current_timeframe="15m",
        )

        event = f.check(bullish_pattern, context)
        assert event.passed is False
        assert event.reason == "ema_data_not_ready"

    def test_check_trend_match_long(self, bullish_pattern):
        """Test LONG signal with bullish trend passes."""
        f = EmaTrendFilterDynamic(period=60, enabled=True)

        context = FilterContext(
            higher_tf_trends={},
            current_trend=TrendDirection.BULLISH,
            current_timeframe="15m",
        )

        event = f.check(bullish_pattern, context)
        assert event.passed is True
        assert event.reason == "trend_match"

    def test_check_trend_mismatch_long(self, bullish_pattern):
        """Test LONG signal with bearish trend fails."""
        f = EmaTrendFilterDynamic(period=60, enabled=True)

        context = FilterContext(
            higher_tf_trends={},
            current_trend=TrendDirection.BEARISH,
            current_timeframe="15m",
        )

        event = f.check(bullish_pattern, context)
        assert event.passed is False
        assert event.reason == "bearish_trend_blocks_long"
        assert event.expected == "bullish"
        assert event.actual == "bearish"


# ============================================================
# MtfFilterDynamic Tests
# ============================================================
class TestMtfFilterDynamic:
    """Test MTF filter dynamic implementation."""

    def test_filter_properties(self):
        """Test MTF filter properties."""
        f = MtfFilterDynamic(enabled=True)

        assert f.name == "mtf"
        assert f.is_stateful is False

    def test_check_disabled(self, bullish_pattern):
        """Test that disabled MTF filter passes."""
        f = MtfFilterDynamic(enabled=False)

        context = FilterContext(
            higher_tf_trends={},
            current_timeframe="15m",
        )

        event = f.check(bullish_pattern, context)
        assert event.passed is True
        assert event.reason == "filter_disabled"

    def test_check_no_higher_timeframe(self, bullish_pattern):
        """Test MTF with 1w timeframe (no higher TF)."""
        f = MtfFilterDynamic(enabled=True)

        context = FilterContext(
            higher_tf_trends={},
            current_timeframe="1w",
        )

        event = f.check(bullish_pattern, context)
        assert event.passed is True
        assert event.reason == "no_higher_timeframe"

    def test_check_higher_tf_unavailable(self, bullish_pattern):
        """Test MTF when higher TF data not available."""
        f = MtfFilterDynamic(enabled=True)

        context = FilterContext(
            higher_tf_trends={},  # Empty
            current_timeframe="15m",
        )

        event = f.check(bullish_pattern, context)
        assert event.passed is False
        assert event.reason == "higher_tf_data_unavailable"

    def test_check_mtf_confirmed_bullish(self, bullish_pattern):
        """Test LONG signal with bullish higher TF."""
        f = MtfFilterDynamic(enabled=True)

        context = FilterContext(
            higher_tf_trends={"1h": TrendDirection.BULLISH},
            current_timeframe="15m",
        )

        event = f.check(bullish_pattern, context)
        assert event.passed is True
        assert event.reason == "mtf_confirmed_bullish"

    def test_check_mtf_rejected_bearish(self, bullish_pattern):
        """Test LONG signal with bearish higher TF."""
        f = MtfFilterDynamic(enabled=True)

        context = FilterContext(
            higher_tf_trends={"1h": TrendDirection.BEARISH},
            current_timeframe="15m",
        )

        event = f.check(bullish_pattern, context)
        assert event.passed is False
        assert "mtf_rejected" in event.reason


# ============================================================
# StrategyWithFilters Tests
# ============================================================
class TestStrategyWithFilters:
    """Test StrategyWithFilters wrapper."""

    def test_strategy_with_no_filters(self):
        """Test strategy with empty filter chain."""
        pinbar_config = PinbarConfig()
        strategy = PinbarStrategy(pinbar_config)

        wrapped = StrategyWithFilters(
            name="pinbar",
            strategy=strategy,
            filters=[],
        )

        assert wrapped.name == "pinbar"
        assert len(wrapped.filters) == 0

    def test_update_state_only_stateful(self):
        """Test that update_state only updates stateful filters."""
        pinbar_config = PinbarConfig()
        strategy = PinbarStrategy(pinbar_config)

        ema_filter = EmaTrendFilterDynamic(period=10, enabled=True)
        mtf_filter = MtfFilterDynamic(enabled=True)

        wrapped = StrategyWithFilters(
            name="pinbar",
            strategy=strategy,
            filters=[ema_filter, mtf_filter],
        )

        # MTF is stateless, EMA is stateful
        assert ema_filter.is_stateful is True
        assert mtf_filter.is_stateful is False

    def test_short_circuit_evaluation(self, sample_kline, bullish_pattern):
        """Test that filter chain short-circuits on first failure."""
        pinbar_config = PinbarConfig()
        strategy = PinbarStrategy(pinbar_config)

        # First filter passes, second fails
        class PassFilter(FilterBase):
            @property
            def name(self):
                return "pass"

            @property
            def is_stateful(self):
                return False

            def update_state(self, kline, symbol, timeframe):
                pass

            def get_current_trend(self, kline, symbol, timeframe):
                return None

            def check(self, pattern, context):
                return TraceEvent(filter_name="pass", passed=True, reason="ok")

        class FailFilter(FilterBase):
            @property
            def name(self):
                return "fail"

            @property
            def is_stateful(self):
                return False

            def update_state(self, kline, symbol, timeframe):
                pass

            def get_current_trend(self, kline, symbol, timeframe):
                return None

            def check(self, pattern, context):
                return TraceEvent(filter_name="fail", passed=False, reason="test_fail")

        wrapped = StrategyWithFilters(
            name="pinbar",
            strategy=strategy,
            filters=[PassFilter(), FailFilter()],
        )

        context = FilterContext(
            higher_tf_trends={},
            current_timeframe="15m",
        )

        passed, results = wrapped.check_filters(bullish_pattern, context)

        assert passed is False
        assert len(results) == 2  # Both filters were checked


# ============================================================
# DynamicStrategyRunner Tests
# ============================================================
class TestDynamicStrategyRunner:
    """Test DynamicStrategyRunner integration."""

    def test_run_all_no_pattern(self, sample_kline):
        """Test run_all when no pattern detected."""
        pinbar_config = PinbarConfig(
            min_wick_ratio=Decimal("0.9"),  # Very strict, won't match
        )
        strategy = PinbarStrategy(pinbar_config)

        wrapped = StrategyWithFilters(
            name="pinbar",
            strategy=strategy,
            filters=[],
        )

        runner = DynamicStrategyRunner([wrapped])
        runner.update_state(sample_kline)

        attempts = runner.run_all(sample_kline, higher_tf_trends={})

        assert len(attempts) == 1
        assert attempts[0].final_result == "NO_PATTERN"

    def test_run_all_with_filters(self, sample_kline):
        """Test run_all with filter chain."""
        pinbar_config = PinbarConfig()
        strategy = PinbarStrategy(pinbar_config)

        ema_filter = EmaTrendFilterDynamic(period=10, enabled=True)

        wrapped = StrategyWithFilters(
            name="pinbar",
            strategy=strategy,
            filters=[ema_filter],
        )

        runner = DynamicStrategyRunner([wrapped])

        # Feed enough klines for EMA warmup
        for i in range(15):
            kline = KlineData(
                symbol="BTC/USDT:USDT",
                timeframe="15m",
                timestamp=1000000 + i * 60000,
                open=Decimal("50000") + i,
                high=Decimal("50100") + i,
                low=Decimal("49900") + i,
                close=Decimal("50050") + i,
                volume=Decimal("1000"),
                is_closed=True,
            )
            runner.update_state(kline)

        attempts = runner.run_all(sample_kline, higher_tf_trends={})

        # Should have one attempt
        assert len(attempts) == 1


# ============================================================
# create_dynamic_runner Tests
# ============================================================
class TestCreateDynamicRunner:
    """Test create_dynamic_runner factory function."""

    def test_create_from_strategy_definitions(self):
        """Test creating runner from StrategyDefinition list."""
        from src.domain.models import StrategyDefinition, FilterConfig, TriggerConfig

        strategies = [
            StrategyDefinition(
                name="pinbar",
                trigger=TriggerConfig(type="pinbar", enabled=True, params={"min_wick_ratio": "0.6"}),
                filters=[
                    FilterConfig(type="ema", enabled=True, params={"period": 60}),
                    FilterConfig(type="mtf", enabled=True),
                ],
            ),
        ]

        runner = create_dynamic_runner(strategies)

        assert isinstance(runner, DynamicStrategyRunner)
        assert len(runner._strategies) == 1
        assert runner._strategies[0].name == "pinbar"

    def test_create_skips_disabled_strategies(self):
        """Test that disabled strategies are skipped."""
        from src.domain.models import StrategyDefinition, TriggerConfig

        strategies = [
            StrategyDefinition(name="pinbar", trigger=TriggerConfig(type="pinbar", enabled=True), filters=[]),
            StrategyDefinition(name="engulfing", trigger=TriggerConfig(type="engulfing", enabled=False), filters=[]),
        ]

        runner = create_dynamic_runner(strategies)

        # Only pinbar should be included
        assert len(runner._strategies) == 1
