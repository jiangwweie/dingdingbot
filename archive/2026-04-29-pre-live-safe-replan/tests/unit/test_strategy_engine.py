"""
Unit tests for domain/strategy_engine.py - Pinbar detection, EMA filtering, MTF validation.
"""
import pytest
from decimal import Decimal
from src.domain.models import KlineData, Direction, TrendDirection, MtfStatus
from src.domain.strategy_engine import (
    StrategyEngine,
    StrategyConfig,
    PinbarConfig,
    PinbarResult,
)


def create_kline(
    symbol: str = "BTC/USDT:USDT",
    timeframe: str = "15m",
    open: Decimal = Decimal(100),
    high: Decimal = Decimal(100),
    low: Decimal = Decimal(100),
    close: Decimal = Decimal(100),
    volume: Decimal = Decimal(1000),
) -> KlineData:
    """Helper to create KlineData for testing."""
    return KlineData(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=1234567890000,
        open=open,
        high=high,
        low=low,
        close=close,
        volume=volume,
        is_closed=True,
    )


def warmup_ema(engine: StrategyEngine, symbol: str, timeframe: str, prices: list, offset: Decimal = Decimal(0)) -> None:
    """Helper to warm up EMA calculator with given prices."""
    for i, price in enumerate(prices):
        p = price + offset if isinstance(price, int) else price
        kline = create_kline(
            symbol=symbol,
            timeframe=timeframe,
            open=p, high=p + 1, low=p - 1, close=p
        )
        engine.detect_pinbar(kline)
        engine.get_ema_trend(kline, symbol, timeframe)


class TestPinbarConfig:
    """Test PinbarConfig validation."""

    def test_default_values(self):
        """Test default configuration values."""
        cfg = PinbarConfig()
        assert cfg.min_wick_ratio == Decimal("0.6")
        assert cfg.max_body_ratio == Decimal("0.3")
        assert cfg.body_position_tolerance == Decimal("0.1")

    def test_invalid_min_wick_ratio_zero(self):
        """Test that zero min_wick_ratio raises error."""
        with pytest.raises(ValueError):
            PinbarConfig(min_wick_ratio=Decimal(0))

    def test_invalid_min_wick_ratio_greater_than_one(self):
        """Test that min_wick_ratio > 1 raises error."""
        with pytest.raises(ValueError):
            PinbarConfig(min_wick_ratio=Decimal("1.5"))

    def test_invalid_max_body_ratio(self):
        """Test that invalid max_body_ratio raises error."""
        with pytest.raises(ValueError):
            PinbarConfig(max_body_ratio=Decimal(1))
        with pytest.raises(ValueError):
            PinbarConfig(max_body_ratio=Decimal("1.5"))

    def test_invalid_body_position_tolerance(self):
        """Test that invalid body_position_tolerance raises error."""
        with pytest.raises(ValueError):
            PinbarConfig(body_position_tolerance=Decimal("0.5"))


class TestDetectPinbar:
    """Test Pinbar pattern detection."""

    @pytest.fixture
    def engine(self):
        """Create strategy engine with test configuration."""
        config = StrategyConfig(pinbar_config=PinbarConfig())
        return StrategyEngine(config)

    def test_doji_candle_no_pinbar(self, engine):
        """Test that a doji (no range) is not a pinbar."""
        kline = create_kline(open=Decimal(100), high=Decimal(100), low=Decimal(100), close=Decimal(100))
        result = engine.detect_pinbar(kline)
        assert not result.is_pinbar

    def test_normal_candle_no_pinbar(self, engine):
        """Test that a normal candle is not a pinbar."""
        kline = create_kline(open=Decimal(100), high=Decimal(110), low=Decimal(90), close=Decimal(105))
        result = engine.detect_pinbar(kline)
        assert not result.is_pinbar

    def test_bullish_pinbar_basic(self, engine):
        """Test basic bullish pinbar detection."""
        kline = create_kline(open=Decimal(108), high=Decimal(110), low=Decimal(90), close=Decimal(109))
        result = engine.detect_pinbar(kline)
        assert result.is_pinbar
        assert result.direction == Direction.LONG

    def test_bearish_pinbar_basic(self, engine):
        """Test basic bearish pinbar detection."""
        kline = create_kline(open=Decimal(92), high=Decimal(110), low=Decimal(90), close=Decimal(91))
        result = engine.detect_pinbar(kline)
        assert result.is_pinbar
        assert result.direction == Direction.SHORT

    def test_pinbar_wick_ratio_calculation(self, engine):
        """Test that wick ratio is correctly calculated."""
        kline = create_kline(open=Decimal(99), high=Decimal(100), low=Decimal(80), close=Decimal(100))
        result = engine.detect_pinbar(kline)
        assert result.wick_ratio == Decimal("0.95")

    def test_pinbar_body_ratio_calculation(self, engine):
        """Test that body ratio is correctly calculated."""
        kline = create_kline(open=Decimal(99), high=Decimal(100), low=Decimal(80), close=Decimal(100))
        result = engine.detect_pinbar(kline)
        assert result.body_ratio == Decimal("0.05")

    def test_min_wick_ratio_threshold(self, engine):
        """Test that pinbar requires minimum wick ratio."""
        kline = create_kline(open=Decimal(104), high=Decimal(110), low=Decimal(90), close=Decimal(106))
        result = engine.detect_pinbar(kline)
        assert not result.is_pinbar

    def test_max_body_ratio_threshold(self, engine):
        """Test that pinbar requires maximum body ratio."""
        kline = create_kline(open=Decimal(90), high=Decimal(110), low=Decimal(90), close=Decimal(100))
        result = engine.detect_pinbar(kline)
        assert not result.is_pinbar

    def test_bullish_pinbar_body_position(self, engine):
        """Test bullish pinbar requires body at top."""
        kline = create_kline(open=Decimal(95), high=Decimal(100), low=Decimal(80), close=Decimal(96))
        result = engine.detect_pinbar(kline)
        assert not result.is_pinbar

    def test_bearish_pinbar_body_position(self, engine):
        """Test bearish pinbar requires body at bottom."""
        kline = create_kline(open=Decimal(104), high=Decimal(110), low=Decimal(100), close=Decimal(105))
        result = engine.detect_pinbar(kline)
        assert not result.is_pinbar

    def test_pinbar_color_agnostic_bullish_candle(self, engine):
        """Test that pinbar works on bullish candle (close > open)."""
        kline = create_kline(open=Decimal(108), high=Decimal(110), low=Decimal(90), close=Decimal(109))
        result = engine.detect_pinbar(kline)
        assert result.is_pinbar
        assert result.direction == Direction.LONG

    def test_pinbar_color_agnostic_bearish_candle(self, engine):
        """Test that pinbar works on bearish candle (close < open)."""
        kline = create_kline(open=Decimal(109), high=Decimal(110), low=Decimal(90), close=Decimal(108))
        result = engine.detect_pinbar(kline)
        assert result.is_pinbar
        assert result.direction == Direction.LONG

    def test_bearish_pinbar_bearish_candle(self, engine):
        """Test bearish pinbar on bearish candle (open > close, long upper wick)."""
        # Need long upper wick, small body at bottom
        # high=110, low=90, open=108, close=91
        # range=20, body=17 (too big!)
        # Let's design correctly: open=92, close=91 (bearish candle, close < open)
        # high=110, low=90, open=92, close=91
        # upper_wick = 110 - 92 = 18, lower_wick = 91 - 90 = 1
        # dominant = 18, wick_ratio = 0.9 >= 0.6 ✓
        # body = 1, body_ratio = 0.05 <= 0.3 ✓
        # body_position = (92+91)/2 / 20 = 91.5/20 = 0.4575
        # bearish: need <= 0.1 + 0.025 = 0.125, but 0.4575 > 0.125, FAIL
        # Need body lower: open=91, close=90
        # high=110, low=90, open=91, close=90
        # upper_wick = 110-91=19, lower_wick=90-90=0
        # body_position = (91+90)/2 / 20 = 0.45, still too high
        # Need body at very bottom: open=90.5, close=90 (but we use integers)
        # Let's try: high=100, low=0, open=8, close=7
        # upper_wick = 100-8=92, lower_wick=7-0=7, dominant=92, ratio=0.92
        # body=1, body_ratio=0.01
        # body_position = (8+7)/2 / 100 = 0.075
        # bearish: need <= 0.1 + 0.005 = 0.105, 0.075 <= 0.105 ✓
        kline = create_kline(open=Decimal(8), high=Decimal(100), low=Decimal(0), close=Decimal(7))
        result = engine.detect_pinbar(kline)
        assert result.is_pinbar
        assert result.direction == Direction.SHORT

    def test_bearish_pinbar_bullish_candle(self, engine):
        """Test bearish pinbar on bullish candle (open < close, long upper wick)."""
        kline = create_kline(open=Decimal(91), high=Decimal(110), low=Decimal(90), close=Decimal(92))
        result = engine.detect_pinbar(kline)
        assert result.is_pinbar
        assert result.direction == Direction.SHORT

    def test_wick_ratio_exactly_at_boundary(self, engine):
        """Test pinbar with wick ratio exactly at 0.6 boundary passes."""
        # Range = 100, need wick >= 60
        # Upper wick = 60, lower wick = 0, body = 40
        kline = create_kline(open=Decimal(60), high=Decimal(100), low=Decimal(0), close=Decimal(60))
        result = engine.detect_pinbar(kline)
        # Wick = 40, ratio = 0.4 - actually fails
        # Let me recalculate: high=100, low=0, open=60, close=60
        # range = 100, body = 0, upper_wick = 100-60=40, lower_wick = 60-0=60
        # dominant = 60, ratio = 0.6 - should pass
        assert result.wick_ratio == Decimal("0.6")
        # But body is 0, so body_ratio = 0 <= 0.3, and body_position = 0.5
        # For bullish: need body_position >= 1 - 0.1 - 0/2 = 0.9, but 0.5 < 0.9, so not bullish
        # For bearish: need body_position <= 0.1 + 0/2 = 0.1, but 0.5 > 0.1, so not bearish
        assert not result.is_pinbar

    def test_wick_ratio_just_above_boundary(self, engine):
        """Test pinbar with wick ratio 0.61 passes if body position is correct."""
        # Range = 100, wick = 61, body = small at top
        # high=100, low=0, open=95, close=96
        # upper_wick = 100-96=4, lower_wick = 95-0=95 (dominant)
        # body = 1, body_ratio = 0.01
        kline = create_kline(open=Decimal(95), high=Decimal(100), low=Decimal(0), close=Decimal(96))
        result = engine.detect_pinbar(kline)
        assert result.wick_ratio == Decimal("0.95")
        assert result.body_ratio == Decimal("0.01")
        # body_position = (95+96)/2 / 100 = 0.955
        # bullish: need >= 1 - 0.1 - 0.005 = 0.895, 0.955 > 0.895, PASS
        assert result.is_pinbar
        assert result.direction == Direction.LONG

    def test_body_ratio_exactly_at_boundary(self, engine):
        """Test pinbar with body ratio exactly at 0.3 boundary."""
        # Range = 100, body = 30, need wick >= 60
        # high=100, low=0, open=30, close=60
        # body = 30, body_ratio = 0.3
        # upper_wick = 40, lower_wick = 30, dominant = 40, wick_ratio = 0.4
        kline = create_kline(open=Decimal(30), high=Decimal(100), low=Decimal(0), close=Decimal(60))
        result = engine.detect_pinbar(kline)
        assert result.body_ratio == Decimal("0.3")
        assert result.wick_ratio == Decimal("0.4")  # 40/100
        # wick_ratio 0.4 < 0.6, should fail
        assert not result.is_pinbar

    def test_body_ratio_just_under_boundary(self, engine):
        """Test pinbar with body ratio 0.29 passes if other conditions met."""
        # high=100, low=0, open=71, close=100 (close at high)
        # body = 29, body_ratio = 0.29
        # upper_wick = 0, lower_wick = 71, dominant = 71, wick_ratio = 0.71
        kline = create_kline(open=Decimal(71), high=Decimal(100), low=Decimal(0), close=Decimal(100))
        result = engine.detect_pinbar(kline)
        assert result.body_ratio == Decimal("0.29")
        assert result.wick_ratio == Decimal("0.71")
        # body_position = (71+100)/2 / 100 = 0.855
        # bullish: need >= 1 - 0.1 - 0.145 = 0.755, 0.855 > 0.755, PASS
        assert result.is_pinbar
        assert result.direction == Direction.LONG

    def test_equal_upper_lower_wicks_no_pinbar(self, engine):
        """Test that equal upper and lower wicks does not qualify as pinbar."""
        # high=100, low=0, open=50, close=50 (doji with equal wicks)
        # upper_wick = 50, lower_wick = 50, body = 0
        kline = create_kline(open=Decimal(50), high=Decimal(100), low=Decimal(0), close=Decimal(50))
        result = engine.detect_pinbar(kline)
        assert result.wick_ratio == Decimal("0.5")  # 50/100
        assert result.body_ratio == Decimal("0")
        # wick_ratio 0.5 < 0.6, should fail
        assert not result.is_pinbar

    def test_extreme_pinbar_high_wick_ratio(self, engine):
        """Test extreme pinbar with wick ratio > 0.95."""
        # high=100, low=0, open=98, close=99
        # body = 1, body_ratio = 0.01
        # upper_wick = 1, lower_wick = 98, dominant = 98, wick_ratio = 0.98
        kline = create_kline(open=Decimal(98), high=Decimal(100), low=Decimal(0), close=Decimal(99))
        result = engine.detect_pinbar(kline)
        assert result.wick_ratio == Decimal("0.98")
        assert result.body_ratio == Decimal("0.01")
        assert result.is_pinbar
        assert result.direction == Direction.LONG

    def test_large_body_rejected(self, engine):
        """Test that large body (body_ratio > 0.5) is rejected."""
        # high=100, low=0, open=10, close=90
        # body = 80, body_ratio = 0.8
        kline = create_kline(open=Decimal(10), high=Decimal(100), low=Decimal(0), close=Decimal(90))
        result = engine.detect_pinbar(kline)
        assert result.body_ratio == Decimal("0.8")
        assert not result.is_pinbar

    def test_btc_price_level(self, engine):
        """Test pinbar detection at BTC price level (~100000)."""
        kline = create_kline(
            open=Decimal("108000"), high=Decimal("110000"),
            low=Decimal("90000"), close=Decimal("109000")
        )
        result = engine.detect_pinbar(kline)
        assert result.is_pinbar
        assert result.direction == Direction.LONG

    def test_doge_price_level(self, engine):
        """Test pinbar detection at DOGE price level (~0.1)."""
        kline = create_kline(
            open=Decimal("0.108"), high=Decimal("0.110"),
            low=Decimal("0.090"), close=Decimal("0.109")
        )
        result = engine.detect_pinbar(kline)
        assert result.is_pinbar
        assert result.direction == Direction.LONG

    def test_custom_config_stricter_wick_requirement(self):
        """Test with custom config requiring higher wick ratio."""
        strict_config = PinbarConfig(min_wick_ratio=Decimal("0.8"), max_body_ratio=Decimal("0.2"))
        engine = StrategyEngine(StrategyConfig(pinbar_config=strict_config))
        # Wick ratio 0.71 would pass default but fail strict
        kline = create_kline(open=Decimal(71), high=Decimal(100), low=Decimal(0), close=Decimal(72))
        result = engine.detect_pinbar(kline)
        # wick = 71/100 = 0.71 < 0.8, should fail
        assert not result.is_pinbar

    def test_custom_config_relaxed_wick_requirement(self):
        """Test with custom config allowing lower wick ratio."""
        relaxed_config = PinbarConfig(min_wick_ratio=Decimal("0.5"), max_body_ratio=Decimal("0.4"))
        engine = StrategyEngine(StrategyConfig(pinbar_config=relaxed_config))
        # This would fail default but pass relaxed
        kline = create_kline(open=Decimal(60), high=Decimal(100), low=Decimal(0), close=Decimal(60))
        result = engine.detect_pinbar(kline)
        # wick = 60/100 = 0.6 >= 0.5, body = 0 <= 0.4
        # But body_position = 0.5, for bullish need >= 1-0.1-0=0.9, 0.5 < 0.9
        # for bearish need <= 0.1, 0.5 > 0.1, so neither
        assert not result.is_pinbar


class TestTrendFilter:
    """Test EMA60 trend filtering."""

    @pytest.fixture
    def engine_with_filter(self):
        """Create engine with trend filter enabled."""
        config = StrategyConfig(pinbar_config=PinbarConfig(), trend_filter_enabled=True, mtf_validation_enabled=False)
        return StrategyEngine(config)

    @pytest.fixture
    def engine_without_filter(self):
        """Create engine with trend filter disabled."""
        config = StrategyConfig(pinbar_config=PinbarConfig(), trend_filter_enabled=False, mtf_validation_enabled=False)
        return StrategyEngine(config)

    def test_trend_filter_bullish_allows_long(self, engine_with_filter):
        """Test that bullish trend allows LONG signals."""
        kline = create_kline(open=Decimal(158), high=Decimal(160), low=Decimal(140), close=Decimal(159))
        # Warm up EMA with 60+ rising prices, ending below current price
        warmup_ema(engine_with_filter, kline.symbol, kline.timeframe, range(100, 170))
        trend = engine_with_filter.get_ema_trend(kline, kline.symbol, kline.timeframe)
        assert trend == TrendDirection.BULLISH  # Price 159 > EMA (~135)
        assert engine_with_filter.check_trend_filter(Direction.LONG, trend) is True

    def test_trend_filter_bullish_rejects_short(self, engine_with_filter):
        """Test that bullish trend rejects SHORT signals."""
        trend = TrendDirection.BULLISH
        assert engine_with_filter.check_trend_filter(Direction.SHORT, trend) is False

    def test_trend_filter_bearish_allows_short(self, engine_with_filter):
        """Test that bearish trend allows SHORT signals."""
        trend = TrendDirection.BEARISH
        assert engine_with_filter.check_trend_filter(Direction.SHORT, trend) is True

    def test_trend_filter_bearish_rejects_long(self, engine_with_filter):
        """Test that bearish trend rejects LONG signals."""
        trend = TrendDirection.BEARISH
        assert engine_with_filter.check_trend_filter(Direction.LONG, trend) is False

    def test_filter_disabled_always_passes(self, engine_without_filter):
        """Test that disabled filter always passes."""
        assert engine_without_filter.check_trend_filter(Direction.LONG, TrendDirection.BULLISH) is True
        assert engine_without_filter.check_trend_filter(Direction.SHORT, TrendDirection.BEARISH) is True
        assert engine_without_filter.check_trend_filter(Direction.LONG, TrendDirection.BEARISH) is True


class TestMTFValidation:
    """Test Multi-Timeframe validation."""

    @pytest.fixture
    def engine_with_mtf(self):
        """Create engine with MTF validation enabled."""
        config = StrategyConfig(pinbar_config=PinbarConfig(), trend_filter_enabled=False, mtf_validation_enabled=True)
        return StrategyEngine(config)

    @pytest.fixture
    def engine_without_mtf(self):
        """Create engine with MTF validation disabled."""
        config = StrategyConfig(pinbar_config=PinbarConfig(), trend_filter_enabled=False, mtf_validation_enabled=False)
        return StrategyEngine(config)

    def test_mtf_mapping_15m_to_1h(self, engine_with_mtf):
        """Test 15m maps to 1h."""
        assert engine_with_mtf.get_higher_timeframe("15m") == "1h"

    def test_mtf_mapping_1h_to_4h(self, engine_with_mtf):
        """Test 1h maps to 4h."""
        assert engine_with_mtf.get_higher_timeframe("1h") == "4h"

    def test_mtf_mapping_4h_to_1d(self, engine_with_mtf):
        """Test 4h maps to 1d."""
        assert engine_with_mtf.get_higher_timeframe("4h") == "1d"

    def test_mtf_mapping_1d_to_1w(self, engine_with_mtf):
        """Test 1d maps to 1w."""
        assert engine_with_mtf.get_higher_timeframe("1d") == "1w"

    def test_mtf_mapping_1w_none(self, engine_with_mtf):
        """Test 1w has no higher timeframe."""
        assert engine_with_mtf.get_higher_timeframe("1w") is None

    def test_mtf_disabled_returns_disabled(self, engine_without_mtf):
        """Test that MTF disabled returns DISABLED status."""
        status = engine_without_mtf.validate_mtf("15m", Direction.LONG, TrendDirection.BULLISH)
        assert status == MtfStatus.DISABLED

    def test_mtf_unavailable_no_trend_data(self, engine_with_mtf):
        """Test MTF returns UNAVAILABLE when no higher TF trend."""
        status = engine_with_mtf.validate_mtf("15m", Direction.LONG, None)
        assert status == MtfStatus.UNAVAILABLE

    def test_mtf_no_higher_timeframe_confirmed(self, engine_with_mtf):
        """Test 1w (no higher TF) returns CONFIRMED."""
        status = engine_with_mtf.validate_mtf("1w", Direction.LONG, None)
        assert status == MtfStatus.CONFIRMED

    def test_mtf_confirmed_bullish(self, engine_with_mtf):
        """Test MTF CONFIRMED for matching bullish direction."""
        status = engine_with_mtf.validate_mtf("15m", Direction.LONG, TrendDirection.BULLISH)
        assert status == MtfStatus.CONFIRMED

    def test_mtf_confirmed_bearish(self, engine_with_mtf):
        """Test MTF CONFIRMED for matching bearish direction."""
        status = engine_with_mtf.validate_mtf("15m", Direction.SHORT, TrendDirection.BEARISH)
        assert status == MtfStatus.CONFIRMED

    def test_mtf_rejected_bullish_signal_bearish_trend(self, engine_with_mtf):
        """Test MTF REJECTED when bullish signal conflicts with bearish higher TF."""
        status = engine_with_mtf.validate_mtf("15m", Direction.LONG, TrendDirection.BEARISH)
        assert status == MtfStatus.REJECTED

    def test_mtf_rejected_bearish_signal_bullish_trend(self, engine_with_mtf):
        """Test MTF REJECTED when bearish signal conflicts with bullish higher TF."""
        status = engine_with_mtf.validate_mtf("15m", Direction.SHORT, TrendDirection.BULLISH)
        assert status == MtfStatus.REJECTED


class TestProcessSignal:
    """Test complete signal processing pipeline."""

    @pytest.fixture
    def full_engine(self):
        """Create fully configured engine."""
        config = StrategyConfig(pinbar_config=PinbarConfig(), trend_filter_enabled=True, mtf_validation_enabled=True)
        return StrategyEngine(config)

    @pytest.fixture
    def engine_no_filters(self):
        """Create engine with all filters disabled."""
        config = StrategyConfig(pinbar_config=PinbarConfig(), trend_filter_enabled=False, mtf_validation_enabled=False)
        return StrategyEngine(config)

    @pytest.fixture
    def engine_trend_only(self):
        """Create engine with only trend filter enabled."""
        config = StrategyConfig(pinbar_config=PinbarConfig(), trend_filter_enabled=True, mtf_validation_enabled=False)
        return StrategyEngine(config)

    @pytest.fixture
    def engine_mtf_only(self):
        """Create engine with only MTF enabled."""
        config = StrategyConfig(pinbar_config=PinbarConfig(), trend_filter_enabled=False, mtf_validation_enabled=True)
        return StrategyEngine(config)

    def test_signal_invalid_no_pinbar(self, full_engine):
        """Test signal is None when no pinbar detected."""
        kline = create_kline(open=Decimal(100), high=Decimal(110), low=Decimal(90), close=Decimal(105))
        warmup_ema(full_engine, kline.symbol, kline.timeframe, range(60), offset=Decimal(90))
        result = full_engine.process_signal(kline)
        assert result is None

    def test_signal_valid_all_conditions_met(self, full_engine):
        """Test valid signal when all conditions are met."""
        # Create bullish pinbar
        kline = create_kline(open=Decimal(158), high=Decimal(160), low=Decimal(140), close=Decimal(159))
        # Warm up EMA with rising prices
        warmup_ema(full_engine, kline.symbol, kline.timeframe, range(60), offset=Decimal(100))
        # Higher TF also bullish
        higher_tf_trends = {"1h": TrendDirection.BULLISH}
        result = full_engine.process_signal(kline, higher_tf_trends)
        assert result == Direction.LONG

    # Issue #6: Truth table tests for 4-combination logic gate
    def test_truth_table_trend_on_mtf_on_all_pass(self, full_engine):
        """trend_filter=ON, mtf=ON, pinbar=OK, trend=OK, mtf=OK -> PASS."""
        kline = create_kline(open=Decimal(158), high=Decimal(160), low=Decimal(140), close=Decimal(159))
        warmup_ema(full_engine, kline.symbol, kline.timeframe, range(60), offset=Decimal(100))
        result = full_engine.process_signal(kline, {"1h": TrendDirection.BULLISH})
        assert result == Direction.LONG

    def test_truth_table_trend_on_mtf_on_trend_fail(self, full_engine):
        """trend_filter=ON, mtf=ON, pinbar=OK, trend=FAIL, mtf=OK -> REJECT."""
        kline = create_kline(open=Decimal(158), high=Decimal(160), low=Decimal(140), close=Decimal(159))
        # Warm up with falling prices (bearish trend) - 60 prices from 200 to 141
        # EMA will be ~170.5, current price 159 is below -> BEARISH trend blocks LONG
        warmup_ema(full_engine, kline.symbol, kline.timeframe, range(200, 140, -1))
        # Higher TF is bullish but trend filter fails
        result = full_engine.process_signal(kline, {"1h": TrendDirection.BULLISH})
        assert result is None

    def test_truth_table_trend_on_mtf_on_mtf_fail(self, full_engine):
        """trend_filter=ON, mtf=ON, pinbar=OK, trend=OK, mtf=FAIL -> REJECT."""
        kline = create_kline(open=Decimal(158), high=Decimal(160), low=Decimal(140), close=Decimal(159))
        warmup_ema(full_engine, kline.symbol, kline.timeframe, range(60), offset=Decimal(100))
        # Higher TF is bearish (conflict)
        result = full_engine.process_signal(kline, {"1h": TrendDirection.BEARISH})
        assert result is None

    def test_truth_table_trend_off_mtf_on_mtf_pass(self, engine_mtf_only):
        """trend_filter=OFF, mtf=ON, pinbar=OK, mtf=OK -> PASS."""
        kline = create_kline(open=Decimal(158), high=Decimal(160), low=Decimal(140), close=Decimal(159))
        warmup_ema(engine_mtf_only, kline.symbol, kline.timeframe, range(60), offset=Decimal(100))
        result = engine_mtf_only.process_signal(kline, {"1h": TrendDirection.BULLISH})
        assert result == Direction.LONG

    def test_truth_table_trend_off_mtf_on_mtf_fail(self, engine_mtf_only):
        """trend_filter=OFF, mtf=ON, pinbar=OK, mtf=FAIL -> REJECT."""
        kline = create_kline(open=Decimal(158), high=Decimal(160), low=Decimal(140), close=Decimal(159))
        warmup_ema(engine_mtf_only, kline.symbol, kline.timeframe, range(60), offset=Decimal(100))
        result = engine_mtf_only.process_signal(kline, {"1h": TrendDirection.BEARISH})
        assert result is None

    def test_truth_table_trend_on_mtf_off_trend_pass(self, engine_trend_only):
        """trend_filter=ON, mtf=OFF, pinbar=OK, trend=OK -> PASS."""
        kline = create_kline(open=Decimal(158), high=Decimal(160), low=Decimal(140), close=Decimal(159))
        warmup_ema(engine_trend_only, kline.symbol, kline.timeframe, range(60), offset=Decimal(100))
        result = engine_trend_only.process_signal(kline, None)
        assert result == Direction.LONG

    def test_truth_table_trend_on_mtf_off_trend_fail(self, engine_trend_only):
        """trend_filter=ON, mtf=OFF, pinbar=OK, trend=FAIL -> REJECT."""
        kline = create_kline(open=Decimal(158), high=Decimal(160), low=Decimal(140), close=Decimal(159))
        # Warm up with falling prices (bearish trend) - 60 prices from 200 to 141
        # EMA will be ~170.5, current price 159 is below -> BEARISH trend blocks LONG
        warmup_ema(engine_trend_only, kline.symbol, kline.timeframe, range(200, 140, -1))
        result = engine_trend_only.process_signal(kline, None)
        assert result is None

    def test_truth_table_trend_off_mtf_off_always_pass(self, engine_no_filters):
        """trend_filter=OFF, mtf=OFF, pinbar=OK -> PASS."""
        kline = create_kline(open=Decimal(158), high=Decimal(160), low=Decimal(140), close=Decimal(159))
        warmup_ema(engine_no_filters, kline.symbol, kline.timeframe, range(60), offset=Decimal(100))
        result = engine_no_filters.process_signal(kline, None)
        assert result == Direction.LONG
