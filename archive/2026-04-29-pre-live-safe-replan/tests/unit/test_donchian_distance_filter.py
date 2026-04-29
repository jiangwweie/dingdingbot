"""
Unit tests for Donchian Distance Filter.

Covers:
1. LONG near high filtered
2. LONG far from high passes
3. Current bar excluded (look-ahead prevention)
4. Insufficient history handling
5. Disabled filter behavior
6. SHORT near low behavior
"""
import pytest
from decimal import Decimal
from datetime import datetime, timezone

from src.domain.filter_factory import (
    DonchianDistanceFilterDynamic,
    FilterContext,
    EmaTrendFilterDynamic,
    MtfFilterDynamic
)
from src.domain.models import KlineData, Direction, TrendDirection, PatternResult


def make_kline(
    symbol: str = "ETH/USDT:USDT",
    timeframe: str = "1h",
    close: Decimal = Decimal("100"),
    high: Decimal = Decimal("105"),
    low: Decimal = Decimal("95"),
    timestamp: int = None
) -> KlineData:
    """Helper to create KlineData for testing."""
    if timestamp is None:
        timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
    return KlineData(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=timestamp,
        open=Decimal("100"),
        high=high,
        low=low,
        close=close,
        volume=Decimal("1000"),
        is_closed=True
    )


def make_pattern(direction: Direction = Direction.LONG) -> PatternResult:
    """Helper to create PatternResult for testing."""
    return PatternResult(
        strategy_name="pinbar",
        direction=direction,
        score=Decimal("0.8"),
        details={}
    )


class TestDonchianDistanceFilterBasic:
    """Basic functionality tests."""

    def test_filter_disabled(self):
        """Disabled filter should always pass."""
        filter = DonchianDistanceFilterDynamic(
            lookback=20,
            max_distance_to_high_pct=Decimal("-0.016809"),
            enabled=False
        )

        kline = make_kline()
        pattern = make_pattern(Direction.LONG)
        context = FilterContext(
            higher_tf_trends={},
            current_timeframe="1h",
            kline=kline,
            current_price=kline.close
        )

        result = filter.check(pattern, context)
        assert result.passed is True
        assert result.reason == "filter_disabled"

    def test_insufficient_history(self):
        """Filter should pass when insufficient history (safe degradation)."""
        filter = DonchianDistanceFilterDynamic(
            lookback=20,
            max_distance_to_high_pct=Decimal("-0.016809"),
            enabled=True
        )

        # Only update 10 bars (< lookback+1=21)
        for i in range(10):
            kline = make_kline(close=Decimal(str(100 + i)))
            filter.update_state(kline, "ETH/USDT:USDT", "1h")

        pattern = make_pattern(Direction.LONG)
        context = FilterContext(
            higher_tf_trends={},
            current_timeframe="1h",
            kline=kline,
            current_price=kline.close
        )

        result = filter.check(pattern, context)
        assert result.passed is True
        assert result.reason == "insufficient_history"


class TestDonchianDistanceFilterValidation:
    """Parameter validation tests."""

    def test_lookback_must_be_positive(self):
        """lookback < 1 should raise ValueError."""
        with pytest.raises(ValueError, match="lookback must be >= 1"):
            DonchianDistanceFilterDynamic(lookback=0)

        with pytest.raises(ValueError, match="lookback must be >= 1"):
            DonchianDistanceFilterDynamic(lookback=-1)

    def test_lookback_minimum_valid(self):
        """lookback=1 should be valid."""
        filter = DonchianDistanceFilterDynamic(lookback=1)
        assert filter._lookback == 1

    def test_max_distance_high_must_be_negative_or_zero(self):
        """Positive max_distance_to_high_pct should raise ValueError."""
        with pytest.raises(ValueError, match="max_distance_to_high_pct must be <= 0"):
            DonchianDistanceFilterDynamic(
                lookback=20,
                max_distance_to_high_pct=Decimal("0.01")
            )

    def test_max_distance_low_must_be_negative_or_zero(self):
        """Positive max_distance_to_low_pct should raise ValueError."""
        with pytest.raises(ValueError, match="max_distance_to_low_pct must be <= 0"):
            DonchianDistanceFilterDynamic(
                lookback=20,
                max_distance_to_low_pct=Decimal("0.01")
            )

    def test_zero_distance_threshold_valid(self):
        """Zero distance threshold should be valid (filters exact boundary touches)."""
        filter = DonchianDistanceFilterDynamic(
            lookback=5,
            max_distance_to_high_pct=Decimal("0"),
            enabled=True
        )
        assert filter._max_distance_to_high_pct == Decimal("0")

    def test_negative_distance_threshold_valid(self):
        """Negative distance threshold should be valid."""
        filter = DonchianDistanceFilterDynamic(
            lookback=20,
            max_distance_to_high_pct=Decimal("-0.016809"),
            max_distance_to_low_pct=Decimal("-0.02")
        )
        assert filter._max_distance_to_high_pct == Decimal("-0.016809")
        assert filter._max_distance_to_low_pct == Decimal("-0.02")


class TestDonchianDistanceFilterLong:
    """LONG signal filtering tests."""

    def test_long_near_high_filtered(self):
        """LONG signal too close to Donchian high should be filtered."""
        filter = DonchianDistanceFilterDynamic(
            lookback=5,
            max_distance_to_high_pct=Decimal("-0.016809"),
            enabled=True
        )

        # Build history: 5 bars with highs [100, 101, 102, 103, 104]
        for i in range(5):
            kline = make_kline(high=Decimal(str(100 + i)))
            filter.update_state(kline, "ETH/USDT:USDT", "1h")

        # Current bar: close=103.5, high=105 (new high)
        # Donchian high from previous 5 bars = 104
        # Distance = (103.5 - 104) / 104 = -0.00481
        # Threshold = -0.016809
        # -0.00481 >= -0.016809 → TOO CLOSE → filtered
        current_kline = make_kline(close=Decimal("103.5"), high=Decimal("105"))
        filter.update_state(current_kline, "ETH/USDT:USDT", "1h")

        pattern = make_pattern(Direction.LONG)
        context = FilterContext(
            higher_tf_trends={},
            current_timeframe="1h",
            kline=current_kline,
            current_price=current_kline.close
        )

        result = filter.check(pattern, context)
        assert result.passed is False
        assert result.reason == "too_close_to_donchian_high"
        assert "distance_pct" in result.metadata
        assert result.metadata["donchian_high"] == 104.0

    def test_long_far_from_high_passes(self):
        """LONG signal far from Donchian high should pass."""
        filter = DonchianDistanceFilterDynamic(
            lookback=5,
            max_distance_to_high_pct=Decimal("-0.016809"),
            enabled=True
        )

        # Build history: 5 bars with highs [100, 101, 102, 103, 104]
        for i in range(5):
            kline = make_kline(high=Decimal(str(100 + i)))
            filter.update_state(kline, "ETH/USDT:USDT", "1h")

        # Current bar: close=95, high=105 (new high)
        # Donchian high from previous 5 bars = 104
        # Distance = (95 - 104) / 104 = -0.0865
        # Threshold = -0.016809
        # -0.0865 < -0.016809 → FAR ENOUGH → passes
        current_kline = make_kline(close=Decimal("95"), high=Decimal("105"))
        filter.update_state(current_kline, "ETH/USDT:USDT", "1h")

        pattern = make_pattern(Direction.LONG)
        context = FilterContext(
            higher_tf_trends={},
            current_timeframe="1h",
            kline=current_kline,
            current_price=current_kline.close
        )

        result = filter.check(pattern, context)
        assert result.passed is True
        assert result.reason == "donchian_distance_ok"

    def test_long_exact_threshold_boundary(self):
        """Test boundary condition: distance exactly at threshold."""
        filter = DonchianDistanceFilterDynamic(
            lookback=5,
            max_distance_to_high_pct=Decimal("-0.02"),
            enabled=True
        )

        # Build history: 5 bars with highs [100, 100, 100, 100, 100]
        for i in range(5):
            kline = make_kline(high=Decimal("100"))
            filter.update_state(kline, "ETH/USDT:USDT", "1h")

        # Current bar: close=98, high=105
        # Donchian high = 100
        # Distance = (98 - 100) / 100 = -0.02
        # Threshold = -0.02
        # -0.02 >= -0.02 → AT THRESHOLD → filtered (>= means too close)
        current_kline = make_kline(close=Decimal("98"), high=Decimal("105"))
        filter.update_state(current_kline, "ETH/USDT:USDT", "1h")

        pattern = make_pattern(Direction.LONG)
        context = FilterContext(
            higher_tf_trends={},
            current_timeframe="1h",
            kline=current_kline,
            current_price=current_kline.close
        )

        result = filter.check(pattern, context)
        assert result.passed is False
        assert result.reason == "too_close_to_donchian_high"


class TestDonchianDistanceFilterShort:
    """SHORT signal filtering tests."""

    def test_short_near_low_filtered(self):
        """SHORT signal too close to Donchian low should be filtered."""
        filter = DonchianDistanceFilterDynamic(
            lookback=5,
            max_distance_to_low_pct=Decimal("-0.02"),
            enabled=True
        )

        # Build history: 5 bars with lows [100, 99, 98, 97, 96]
        for i in range(5):
            kline = make_kline(low=Decimal(str(100 - i)))
            filter.update_state(kline, "ETH/USDT:USDT", "1h")

        # Current bar: close=96.5, low=95 (new low)
        # Donchian low from previous 5 bars = 96
        # Distance = (96 - 96.5) / 96 = -0.00521
        # Threshold = -0.02
        # -0.00521 >= -0.02 → TOO CLOSE → filtered
        current_kline = make_kline(close=Decimal("96.5"), low=Decimal("95"))
        filter.update_state(current_kline, "ETH/USDT:USDT", "1h")

        pattern = make_pattern(Direction.SHORT)
        context = FilterContext(
            higher_tf_trends={},
            current_timeframe="1h",
            kline=current_kline,
            current_price=current_kline.close
        )

        result = filter.check(pattern, context)
        assert result.passed is False
        assert result.reason == "too_close_to_donchian_low"
        assert result.metadata["donchian_low"] == 96.0

    def test_short_far_from_low_passes(self):
        """SHORT signal far from Donchian low should pass."""
        filter = DonchianDistanceFilterDynamic(
            lookback=5,
            max_distance_to_low_pct=Decimal("-0.02"),
            enabled=True
        )

        # Build history: 5 bars with lows [100, 99, 98, 97, 96]
        for i in range(5):
            kline = make_kline(low=Decimal(str(100 - i)))
            filter.update_state(kline, "ETH/USDT:USDT", "1h")

        # Current bar: close=105, low=95 (new low)
        # Donchian low from previous 5 bars = 96
        # Distance = (96 - 105) / 96 = -0.09375
        # Threshold = -0.02
        # -0.09375 < -0.02 → FAR ENOUGH → passes
        current_kline = make_kline(close=Decimal("105"), low=Decimal("95"))
        filter.update_state(current_kline, "ETH/USDT:USDT", "1h")

        pattern = make_pattern(Direction.SHORT)
        context = FilterContext(
            higher_tf_trends={},
            current_timeframe="1h",
            kline=current_kline,
            current_price=current_kline.close
        )

        result = filter.check(pattern, context)
        assert result.passed is True
        assert result.reason == "donchian_distance_ok"

    def test_short_no_threshold_configured(self):
        """SHORT signal should pass if no low threshold configured."""
        filter = DonchianDistanceFilterDynamic(
            lookback=5,
            max_distance_to_high_pct=Decimal("-0.02"),  # Only high threshold
            max_distance_to_low_pct=None,  # No low threshold
            enabled=True
        )

        # Build sufficient history
        for i in range(6):
            kline = make_kline()
            filter.update_state(kline, "ETH/USDT:USDT", "1h")

        pattern = make_pattern(Direction.SHORT)
        context = FilterContext(
            higher_tf_trends={},
            current_timeframe="1h",
            kline=kline,
            current_price=kline.close
        )

        result = filter.check(pattern, context)
        assert result.passed is True
        assert result.reason == "donchian_distance_ok"


class TestDonchianDistanceFilterLookaheadPrevention:
    """P0: Look-ahead prevention tests."""

    def test_current_bar_excluded_from_donchian(self):
        """
        P0: Current bar must NOT affect Donchian calculation.

        Scenario:
        - Previous 5 bars: highs [100, 100, 100, 100, 100]
        - Current bar: high=200 (new extreme high)
        - Donchian high should still be 100 (excluding current bar)
        """
        filter = DonchianDistanceFilterDynamic(
            lookback=5,
            max_distance_to_high_pct=Decimal("-0.5"),
            enabled=True
        )

        # Build history: 5 bars with highs all 100
        for i in range(5):
            kline = make_kline(high=Decimal("100"))
            filter.update_state(kline, "ETH/USDT:USDT", "1h")

        # Current bar: high=200 (new extreme), close=150
        # If look-ahead bug exists: Donchian high = 200
        # Correct (no look-ahead): Donchian high = 100
        current_kline = make_kline(close=Decimal("150"), high=Decimal("200"))
        filter.update_state(current_kline, "ETH/USDT:USDT", "1h")

        pattern = make_pattern(Direction.LONG)
        context = FilterContext(
            higher_tf_trends={},
            current_timeframe="1h",
            kline=current_kline,
            current_price=current_kline.close
        )

        result = filter.check(pattern, context)

        # If Donchian high = 200 (look-ahead bug):
        #   distance = (150 - 200) / 200 = -0.25 → passes (far from high)
        # If Donchian high = 100 (correct):
        #   distance = (150 - 100) / 100 = 0.5 → passes (positive distance, above high)

        # Verify Donchian high is 100 (not 200)
        assert result.metadata["donchian_high"] == 100.0, \
            "Look-ahead bug: current bar affected Donchian calculation"

    def test_window_rolling_correctly(self):
        """Test that rolling window maintains correct size."""
        filter = DonchianDistanceFilterDynamic(
            lookback=3,
            max_distance_to_high_pct=Decimal("-0.02"),
            enabled=True
        )

        # Update 10 bars with highs [100, 101, 102, ..., 109]
        for i in range(10):
            kline = make_kline(high=Decimal(str(100 + i)))
            filter.update_state(kline, "ETH/USDT:USDT", "1h")

        # Window should have lookback+1 = 4 bars
        state = filter._state.get("ETH/USDT:USDT:1h")
        assert state is not None
        assert len(state["highs"]) == 4
        # Should have bars [106, 107, 108, 109] (current=109 + previous 3)
        # Note: i ranges from 0 to 9, so highs are 100+i = [100, 101, ..., 109]
        # Last 4 bars: indices 6,7,8,9 → highs 106,107,108,109
        assert state["highs"] == [Decimal("106"), Decimal("107"), Decimal("108"), Decimal("109")]


class TestDonchianDistanceFilterMultipleSymbols:
    """Multi-symbol state isolation tests."""

    def test_multiple_symbols_independent_state(self):
        """Each symbol:timeframe should maintain independent state."""
        filter = DonchianDistanceFilterDynamic(
            lookback=5,
            max_distance_to_high_pct=Decimal("-0.02"),
            enabled=True
        )

        # ETH: highs [100, 101, 102, 103, 104]
        for i in range(5):
            kline = make_kline(symbol="ETH/USDT:USDT", high=Decimal(str(100 + i)))
            filter.update_state(kline, "ETH/USDT:USDT", "1h")

        # BTC: highs [200, 201, 202, 203, 204]
        for i in range(5):
            kline = make_kline(symbol="BTC/USDT:USDT", high=Decimal(str(200 + i)))
            filter.update_state(kline, "BTC/USDT:USDT", "1h")

        # Check ETH state
        eth_state = filter._state.get("ETH/USDT:USDT:1h")
        assert eth_state is not None
        assert max(eth_state["highs"]) == Decimal("104")

        # Check BTC state
        btc_state = filter._state.get("BTC/USDT:USDT:1h")
        assert btc_state is not None
        assert max(btc_state["highs"]) == Decimal("204")

        # States should be independent
        assert eth_state["highs"] != btc_state["highs"]


class TestDonchianDistanceFilterFactory:
    """FilterFactory integration tests."""

    def test_factory_creates_donchian_filter(self):
        """FilterFactory should create DonchianDistanceFilterDynamic."""
        from src.domain.filter_factory import FilterFactory

        config = {
            "type": "donchian_distance",
            "enabled": True,
            "params": {
                "lookback": 20,
                "max_distance_to_high_pct": "-0.016809"
            }
        }

        filter = FilterFactory.create(config)
        assert isinstance(filter, DonchianDistanceFilterDynamic)
        assert filter._lookback == 20
        assert filter._max_distance_to_high_pct == Decimal("-0.016809")
        assert filter._enabled is True

    def test_factory_creates_disabled_filter(self):
        """FilterFactory should respect enabled=False."""
        from src.domain.filter_factory import FilterFactory

        config = {
            "type": "donchian_distance",
            "enabled": False,
            "params": {
                "lookback": 20
            }
        }

        filter = FilterFactory.create(config)
        assert filter._enabled is False

    def test_factory_default_enabled_is_true(self):
        """FilterFactory should default enabled=True following project convention."""
        from src.domain.filter_factory import FilterFactory

        config = {
            "type": "donchian_distance",
            "params": {
                "lookback": 20
            }
        }

        filter = FilterFactory.create(config)
        assert filter._enabled is True


class TestDonchianDistanceFilterIntegration:
    """Integration tests with FilterConfig and StrategyDefinition."""

    def test_filter_config_accepts_donchian_distance(self):
        """FilterConfig should accept type='donchian_distance'."""
        from src.domain.logic_tree import FilterConfig

        config = FilterConfig(
            type="donchian_distance",
            enabled=True,
            params={
                "lookback": 20,
                "max_distance_to_high_pct": "-0.016809"
            }
        )

        assert config.type == "donchian_distance"
        assert config.enabled is True
        assert config.params["lookback"] == 20

    def test_filter_config_default_enabled_is_true(self):
        """FilterConfig should default enabled=True."""
        from src.domain.logic_tree import FilterConfig

        config = FilterConfig(
            type="donchian_distance",
            params={"lookback": 20}
        )

        assert config.enabled is True

    def test_create_chain_from_filter_configs(self):
        """FilterFactory.create_chain should create DonchianDistanceFilterDynamic from FilterConfig."""
        from src.domain.filter_factory import FilterFactory
        from src.domain.logic_tree import FilterConfig

        configs = [
            FilterConfig(type="ema_trend", params={"period": 60}),
            FilterConfig(type="mtf", params={}),
            FilterConfig(
                type="donchian_distance",
                enabled=True,
                params={
                    "lookback": 20,
                    "max_distance_to_high_pct": "-0.016809"
                }
            )
        ]

        filters = FilterFactory.create_chain(configs)

        assert len(filters) == 3
        assert isinstance(filters[0], EmaTrendFilterDynamic)
        assert isinstance(filters[1], MtfFilterDynamic)
        assert isinstance(filters[2], DonchianDistanceFilterDynamic)
        assert filters[2]._lookback == 20
        assert filters[2]._max_distance_to_high_pct == Decimal("-0.016809")
        assert filters[2]._enabled is True

    def test_strategy_definition_with_donchian_filter(self):
        """StrategyDefinition should accept donchian_distance filter in logic_tree."""
        from src.domain.models import StrategyDefinition
        from src.domain.logic_tree import FilterConfig, FilterLeaf, LogicNode

        # Create filter leaf
        donchian_leaf = FilterLeaf(
            id="donchian_filter",
            config=FilterConfig(
                type="donchian_distance",
                enabled=True,
                params={
                    "lookback": 20,
                    "max_distance_to_high_pct": "-0.016809"
                }
            )
        )

        # Create logic tree
        logic_tree = LogicNode(
            gate="AND",
            children=[donchian_leaf]
        )

        # Create strategy definition
        strategy = StrategyDefinition(
            id="test_strategy",
            name="Test Strategy",
            logic_tree=logic_tree,
            apply_to=["ETH/USDT:USDT:1h"]
        )

        # Verify logic tree structure
        assert strategy.logic_tree.gate == "AND"
        assert len(strategy.logic_tree.children) == 1
        assert isinstance(strategy.logic_tree.children[0], FilterLeaf)
        assert strategy.logic_tree.children[0].config.type == "donchian_distance"
