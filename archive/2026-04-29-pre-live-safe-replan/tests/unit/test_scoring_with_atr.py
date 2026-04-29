"""
Unit tests for S6-2-2: Scoring Formula Optimization with ATR adjustment.

Tests:
1. PatternStrategy.calculate_score() unified formula
2. PinbarStrategy.detect() with ATR parameter
3. EngulfingStrategy.detect() with ATR parameter
4. End-to-end scoring comparison (user scenario)
"""
import pytest
from decimal import Decimal
from src.domain.strategy_engine import PatternStrategy, PinbarStrategy, PinbarConfig
from src.domain.strategies.engulfing_strategy import EngulfingStrategy
from src.domain.models import KlineData, Direction


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


class TestPatternStrategyScoring:
    """Test unified scoring formula in PatternStrategy base class."""

    def test_calculate_score_without_atr(self):
        """Test scoring without ATR (legacy mode)."""
        strategy = PinbarStrategy(PinbarConfig())

        # pattern_ratio only, no ATR adjustment
        score = strategy.calculate_score(Decimal("0.7"))
        assert score == 0.7

    def test_calculate_score_with_atr(self):
        """Test scoring with ATR adjustment."""
        strategy = PinbarStrategy(PinbarConfig())

        # pattern_ratio = 0.7, atr_ratio = 1.0
        # score = 0.7 * 0.7 + min(1.0, 2.0) * 0.3 = 0.49 + 0.3 = 0.79
        score = strategy.calculate_score(Decimal("0.7"), Decimal("1.0"))
        assert abs(score - 0.79) < 0.001

    def test_calculate_score_with_high_atr(self):
        """Test scoring with high ATR (capped at 2.0)."""
        strategy = PinbarStrategy(PinbarConfig())

        # pattern_ratio = 0.7, atr_ratio = 3.0 (capped at 2.0)
        # score = 0.7 * 0.7 + min(3.0, 2.0) * 0.3 = 0.49 + 0.6 = 1.09 -> capped at 1.0
        score = strategy.calculate_score(Decimal("0.7"), Decimal("3.0"))
        assert score == 1.0

    def test_calculate_score_with_low_atr(self):
        """Test scoring with low ATR (below threshold)."""
        strategy = PinbarStrategy(PinbarConfig())

        # pattern_ratio = 0.7, atr_ratio = 0.3 (below 0.5 threshold)
        # score = 0.7 * 0.7 + 0.3 * 0.3 = 0.49 + 0.09 = 0.58
        score = strategy.calculate_score(Decimal("0.7"), Decimal("0.3"))
        assert abs(score - 0.58) < 0.001

    def test_calculate_score_zero_atr(self):
        """Test scoring with zero ATR (fallback to legacy)."""
        strategy = PinbarStrategy(PinbarConfig())

        # atr_ratio = 0, should fallback to legacy
        score = strategy.calculate_score(Decimal("0.7"), Decimal("0"))
        assert score == 0.7


class TestPinbarStrategyWithAtr:
    """Test PinbarStrategy with ATR-adjusted scoring."""

    def test_detect_with_atr(self):
        """Test Pinbar detection with ATR scoring."""
        config = PinbarConfig(
            min_wick_ratio=Decimal("0.6"),
            max_body_ratio=Decimal("0.3"),
            body_position_tolerance=Decimal("0.1"),
        )
        strategy = PinbarStrategy(config)

        # Create a bullish pinbar with long lower wick
        # Body at top, long lower wick
        kline = create_kline(
            open=Decimal("50090"),
            high=Decimal("50100"),
            low=Decimal("49900"),
            close=Decimal("50100"),
        )
        # Range = 200, body = 10, body_ratio = 0.05
        # Lower wick = 90 (from 50000 to 49900)...
        # Actually: open=50090, close=50100, low=49900
        # Lower wick = min(50090, 50100) - 49900 = 50090 - 49900 = 190
        # Upper wick = 50100 - max(50090, 50100) = 50100 - 50100 = 0
        # Dominant wick = 190, wick_ratio = 190/200 = 0.95

        # ATR = 400, candle_range = 200, atr_ratio = 0.5
        atr_value = Decimal("400")

        result = strategy.detect(kline, atr_value)
        assert result is not None
        assert result.direction == Direction.LONG
        # pattern_ratio = 0.95, atr_ratio = 0.5
        # score = 0.95 * 0.7 + min(0.5, 2.0) * 0.3 = 0.665 + 0.15 = 0.815
        assert abs(result.score - 0.815) < 0.05
        assert result.details["wick_ratio"] >= 0.6

    def test_detect_without_atr(self):
        """Test Pinbar detection without ATR (legacy scoring)."""
        config = PinbarConfig(
            min_wick_ratio=Decimal("0.6"),
            max_body_ratio=Decimal("0.3"),
            body_position_tolerance=Decimal("0.1"),
        )
        strategy = PinbarStrategy(config)

        # Same pinbar as above
        kline = create_kline(
            open=Decimal("50090"),
            high=Decimal("50100"),
            low=Decimal("49900"),
            close=Decimal("50100"),
        )

        result = strategy.detect(kline)  # No ATR
        assert result is not None
        assert result.direction == Direction.LONG
        # Legacy scoring: score = wick_ratio (should be ~0.95)
        assert result.score >= 0.9
        assert result.details["wick_ratio"] >= 0.6

    def test_detect_low_atr_cross_star(self):
        """Test that low ATR (十字星) gets lower score."""
        config = PinbarConfig(
            min_wick_ratio=Decimal("0.6"),
            max_body_ratio=Decimal("0.3"),
            body_position_tolerance=Decimal("0.1"),
        )
        strategy = PinbarStrategy(config)

        # Create a valid pinbar with very small range (十字星 style)
        kline = create_kline(
            open=Decimal("50009"),
            high=Decimal("50010"),
            low=Decimal("50000"),
            close=Decimal("50010"),
        )
        # Range = 10, body = 1, body_ratio = 0.1
        # Lower wick = 9, wick_ratio = 0.9 (meets criteria)

        # High ATR = 400, candle_range = 10, atr_ratio = 0.025 (very low)
        atr_value = Decimal("400")

        result = strategy.detect(kline, atr_value)
        # Even if geometric pattern passes, low ATR should result in lower score
        if result is not None:
            # score = 0.9 * 0.7 + 0.025 * 0.3 = 0.63 + 0.0075 = 0.6375
            assert result.score < 0.7  # Lower than high ATR pinbar


class TestEngulfingStrategyWithAtr:
    """Test EngulfingStrategy with ATR-adjusted scoring."""

    def test_detect_with_atr(self):
        """Test Engulfing detection with ATR scoring."""
        strategy = EngulfingStrategy()

        # Create bullish engulfing pattern
        prev_kline = create_kline(
            timestamp=1000000,
            open=Decimal("50100"),
            close=Decimal("50000"),  # Bearish candle
            high=Decimal("50150"),
            low=Decimal("49950"),
        )
        curr_kline = create_kline(
            timestamp=2000000,
            open=Decimal("49980"),
            close=Decimal("50120"),  # Bullish candle, engulfs previous
            high=Decimal("50200"),
            low=Decimal("49900"),
        )

        # ATR = 300, candle_range = 300, atr_ratio = 1.0
        atr_value = Decimal("300")

        result = strategy.detect(curr_kline, prev_kline, atr_value)
        assert result is not None
        assert result.direction == Direction.LONG
        # Score should be adjusted with ATR
        assert result.score >= 0.5

    def test_detect_without_atr(self):
        """Test Engulfing detection without ATR (legacy scoring)."""
        strategy = EngulfingStrategy()

        prev_kline = create_kline(
            timestamp=1000000,
            open=Decimal("50100"),
            close=Decimal("50000"),
            high=Decimal("50150"),
            low=Decimal("49950"),
        )
        curr_kline = create_kline(
            timestamp=2000000,
            open=Decimal("49980"),
            close=Decimal("50120"),
            high=Decimal("50200"),
            low=Decimal("49900"),
        )

        result = strategy.detect(curr_kline, prev_kline)  # No ATR
        assert result is not None
        # Legacy scoring should still work


class TestEndToEndScenario:
    """End-to-end test simulating user's scenario."""

    def test_high_atr_beats_low_atr(self):
        """
        Test that high ATR pinbar gets higher score than low ATR pinbar
        even with similar geometric ratios.
        """
        config = PinbarConfig(
            min_wick_ratio=Decimal("0.6"),
            max_body_ratio=Decimal("0.3"),
            body_position_tolerance=Decimal("0.1"),
        )
        strategy = PinbarStrategy(config)

        # Create two pinbars with similar geometric ratio but different absolute ranges
        # Pinbar 1: 十字星 (low volatility) - small range
        cross_star = create_kline(
            timestamp=1000000,
            open=Decimal("50009"),
            high=Decimal("50010"),
            low=Decimal("50000"),
            close=Decimal("50010"),
        )
        # Range = 10, body = 1, body_ratio = 0.1, lower wick = 9, wick_ratio = 0.9

        # Pinbar 2: 真突破 (high volatility) - large range
        breakthrough = create_kline(
            timestamp=2000000,
            open=Decimal("50409"),
            high=Decimal("50410"),
            low=Decimal("50000"),
            close=Decimal("50410"),
        )
        # Range = 410, body = 1, body_ratio ~= 0, lower wick = 409, wick_ratio ~= 1.0

        # ATR = 400 (standard)
        atr_value = Decimal("400")

        result1 = strategy.detect(cross_star, atr_value)
        result2 = strategy.detect(breakthrough, atr_value)

        # Both should be detected
        assert result1 is not None, "Cross star should be detected as pinbar"
        assert result2 is not None, "Breakthrough should be detected as pinbar"

        # High ATR pinbar should have higher score
        # cross_star: atr_ratio = 10/400 = 0.025
        # breakthrough: atr_ratio = 410/400 = 1.025
        # Both have similar wick_ratio (~0.9-1.0), but breakthrough gets more ATR bonus
        assert result2.score > result1.score, \
            f"High ATR pinbar (score={result2.score}) should beat low ATR (score={result1.score})"
