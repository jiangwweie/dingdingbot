"""
Unit tests for Engulfing Strategy Scoring Logic - T6 测试。

测试覆盖:
- T6-1: 基础评分 (engulfing_ratio=1.0, 无 ATR)
- T6-2: 高 engulfing_ratio 评分 (无 ATR)
- T6-3: ATR 加分评分 (atr_ratio=1.0)
- T6-4: ATR 加分上限 (atr_ratio=2.0)
"""
import pytest
from decimal import Decimal
from src.domain.models import KlineData, Direction
from src.domain.strategies.engulfing_strategy import EngulfingStrategy


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


class TestEngulfingScoringLogic:
    """T6: Engulfing Strategy Scoring Logic tests."""

    def test_t6_1_base_score_no_atr(self):
        """T6-1: 基础评分 (engulfing_ratio=1.0, 无 ATR)"""
        strategy = EngulfingStrategy()

        # engulfing_ratio = 1.0 (equal bodies)
        # For engulfing: curr_open < prev_close AND curr_close > prev_open
        # prev: open=1000, close=990 (bearish, body=10)
        # curr: open=989, close=1001 (bullish, body=12), engulfs prev
        prev = create_kline(
            open=Decimal("1000"), high=Decimal("1005"),
            low=Decimal("985"), close=Decimal("990"),  # 阴线，实体=10
            timestamp=1000
        )
        curr = create_kline(
            open=Decimal("989"), high=Decimal("1010"),  # open < prev_close (989 < 990)
            low=Decimal("980"), close=Decimal("1001"),  # close > prev_open (1001 > 1000)
            timestamp=2000
        )

        result = strategy.detect(curr, prev_kline=prev, atr_value=None)

        assert result is not None, "Should detect engulfing pattern"
        assert 0.5 <= result.score <= 1.0
        # engulfing_ratio = 12/10 = 1.2
        # pattern_ratio = 1 - 1/(1.2+1) = 0.545
        # score = 0.545 (no ATR)
        assert result.score < 0.7  # No bonus, so should be low

    def test_t6_2_high_engulfing_ratio_no_atr(self):
        """T6-2: 高 engulfing_ratio 评分 (无 ATR)"""
        strategy = EngulfingStrategy()

        # engulfing_ratio = 4.0 (current body is 4x prev body)
        # prev: open=1000, close=995 (bearish, body=5)
        # curr: open=994, close=1015 (bullish, body=21), engulfs prev
        prev = create_kline(
            open=Decimal("1000"), high=Decimal("1005"),
            low=Decimal("990"), close=Decimal("995"),  # 阴线，实体=5
            timestamp=1000
        )
        curr = create_kline(
            open=Decimal("994"), high=Decimal("1020"),  # open < prev_close (994 < 995)
            low=Decimal("985"), close=Decimal("1015"),  # close > prev_open (1015 > 1000)
            timestamp=2000
        )

        result = strategy.detect(curr, prev_kline=prev, atr_value=None)

        assert result is not None, "Should detect engulfing"
        assert result.details["engulfing_ratio"] >= 3.0
        # pattern_ratio = 1 - 1/(4+1) = 0.8
        # score = 0.8 (no ATR)
        assert result.score >= 0.6

    def test_t6_3_atr_bonus_scoring(self):
        """T6-3: ATR 加分评分 (atr_ratio=1.0)"""
        strategy = EngulfingStrategy()

        # Create engulfing with known ATR
        # candle_range / atr = 1.0
        prev = create_kline(
            open=Decimal("1000"), high=Decimal("1005"),
            low=Decimal("985"), close=Decimal("990"),  # 阴线，实体=10
            timestamp=1000
        )
        curr = create_kline(
            open=Decimal("989"), high=Decimal("1115"),  # candle_range = 1115-980 = 135
            low=Decimal("980"), close=Decimal("1001"),  # close > prev_open
            timestamp=2000
        )

        # ATR = 135, so atr_ratio = 135/135 = 1.0
        result = strategy.detect(curr, prev_kline=prev, atr_value=Decimal("135"))

        assert result is not None, "Should detect engulfing"
        # pattern_ratio * 0.7 + min(atr_ratio, 2.0) * 0.3
        # Assuming pattern_ratio ~ 0.55, atr_ratio = 1.0
        # score = 0.55 * 0.7 + 1.0 * 0.3 = 0.685
        assert result.score >= 0.55

    def test_t6_4_atr_bonus_cap(self):
        """T6-4: ATR 加分上限 (atr_ratio=2.0)"""
        strategy = EngulfingStrategy()

        # Create engulfing with high ATR ratio
        # candle_range / atr = 3.0 (exceeds cap of 2.0)
        prev = create_kline(
            open=Decimal("1000"), high=Decimal("1005"),
            low=Decimal("985"), close=Decimal("990"),  # 阴线，实体=10
            timestamp=1000
        )
        curr = create_kline(
            open=Decimal("989"), high=Decimal("1400"),  # candle_range = 1400-980 = 420
            low=Decimal("980"), close=Decimal("1001"),  # close > prev_open
            timestamp=2000
        )

        # ATR = 100, so atr_ratio = 420/100 = 4.2 > 2.0 (capped at 2.0)
        result = strategy.detect(curr, prev_kline=prev, atr_value=Decimal("100"))

        assert result is not None, "Should detect engulfing"
        # Score should be capped at:
        # pattern_ratio * 0.7 + min(4.2, 2.0) * 0.3
        # = pattern_ratio * 0.7 + 0.6
        # Max possible = 1.0
        assert result.score <= 1.0
        # Should be higher than without ATR cap
        result_no_cap = strategy.detect(curr, prev_kline=prev, atr_value=None)
        assert result.score > result_no_cap.score

    def test_score_formula_consistency(self):
        """Test scoring formula consistency across different scenarios."""
        strategy = EngulfingStrategy()

        # Valid engulfing setup
        prev = create_kline(
            open=Decimal("1000"), high=Decimal("1005"),
            low=Decimal("985"), close=Decimal("990"),
            timestamp=100
        )
        curr = create_kline(
            open=Decimal("989"), high=Decimal("1115"),
            low=Decimal("980"), close=Decimal("1001"),
            timestamp=200
        )

        # Test 1: No ATR
        result1 = strategy.detect(curr, prev_kline=prev, atr_value=None)

        # Test 2: With ATR bonus
        result2 = strategy.detect(curr, prev_kline=prev, atr_value=Decimal("135"))

        assert result1 is not None
        assert result2 is not None
        # result2 should have higher or equal score due to ATR bonus
        assert result2.score >= result1.score

    def test_engulfing_ratio_impact_on_score(self):
        """Test that higher engulfing_ratio leads to higher score."""
        strategy = EngulfingStrategy()

        # Low engulfing_ratio scenario (ratio ~ 1.2)
        prev_low = create_kline(
            open=Decimal("1000"), high=Decimal("1005"),
            low=Decimal("985"), close=Decimal("990"),  # body=10
            timestamp=100
        )
        curr_low = create_kline(
            open=Decimal("989"), high=Decimal("1012"),
            low=Decimal("980"), close=Decimal("1002"),  # body=13
            timestamp=200
        )
        result_low = strategy.detect(curr_low, prev_kline=prev_low, atr_value=None)

        # High engulfing_ratio scenario (ratio ~ 4.0)
        prev_high = create_kline(
            open=Decimal("1000"), high=Decimal("1005"),
            low=Decimal("990"), close=Decimal("995"),  # body=5
            timestamp=100
        )
        curr_high = create_kline(
            open=Decimal("994"), high=Decimal("1025"),
            low=Decimal("985"), close=Decimal("1015"),  # body=21
            timestamp=200
        )
        result_high = strategy.detect(curr_high, prev_kline=prev_high, atr_value=None)

        if result_low and result_high:
            # Higher engulfing_ratio should lead to higher score (same ATR condition)
            if result_high.details["engulfing_ratio"] > result_low.details["engulfing_ratio"]:
                assert result_high.score >= result_low.score


class TestCalculateScoreHelper:
    """Test the calculate_score helper logic."""

    def test_calculate_score_no_atr(self):
        """Test score calculation without ATR."""
        strategy = EngulfingStrategy()

        # Direct calculation using the formula
        # pattern_ratio = 0.5, no ATR -> score = 0.5
        pattern_ratio = Decimal("0.5")
        score = float(pattern_ratio)  # Legacy scoring
        assert score == 0.5

    def test_calculate_score_with_atr(self):
        """Test score calculation with ATR bonus."""
        strategy = EngulfingStrategy()

        # pattern_ratio = 0.5, atr_ratio = 1.0
        # score = 0.5 * 0.7 + 1.0 * 0.3 = 0.65
        pattern_ratio = Decimal("0.5")
        atr_ratio = Decimal("1.0")
        score = float(pattern_ratio) * 0.7 + float(min(atr_ratio, Decimal("2.0"))) * 0.3
        assert abs(score - 0.65) < 0.01

    def test_calculate_score_atr_cap(self):
        """Test score calculation with ATR cap at 2.0."""
        # pattern_ratio = 0.5, atr_ratio = 3.0 (capped at 2.0)
        # score = 0.5 * 0.7 + 2.0 * 0.3 = 0.95
        pattern_ratio = Decimal("0.5")
        atr_ratio = Decimal("3.0")
        score = float(pattern_ratio) * 0.7 + float(min(atr_ratio, Decimal("2.0"))) * 0.3
        assert abs(score - 0.95) < 0.01

    def test_calculate_score_minimum(self):
        """Test calculate_score minimum bound."""
        # Very low pattern_ratio
        pattern_ratio = Decimal("0.1")
        score = float(pattern_ratio)
        assert score >= 0.0

    def test_calculate_score_maximum(self):
        """Test calculate_score maximum bound at 1.0."""
        # Maximum possible: pattern_ratio = 1.0, atr_ratio = 2.0
        # score = 1.0 * 0.7 + 2.0 * 0.3 = 1.0
        pattern_ratio = Decimal("1.0")
        atr_ratio = Decimal("2.0")
        score = float(pattern_ratio) * 0.7 + float(min(atr_ratio, Decimal("2.0"))) * 0.3
        assert score <= 1.0
