"""
Unit tests for domain/indicators.py - EMA streaming calculation.
"""
import pytest
from decimal import Decimal
from src.domain.indicators import EMACalculator, calculate_ema_series


class TestEMACalculator:
    """Test EMA calculator streaming functionality."""

    def test_initialization_with_default_period(self):
        """Test EMA calculator initializes with default period 60."""
        calc = EMACalculator()
        assert calc.period == 60
        assert calc.value is None
        assert not calc.is_ready

    def test_initialization_with_custom_period(self):
        """Test EMA calculator with custom period."""
        calc = EMACalculator(period=20)
        assert calc.period == 20
        assert calc.value is None

    def test_invalid_period_raises_error(self):
        """Test that invalid period raises ValueError."""
        with pytest.raises(ValueError):
            EMACalculator(period=0)
        with pytest.raises(ValueError):
            EMACalculator(period=-1)

    def test_warmup_period(self):
        """Test that EMA is None during warmup period."""
        calc = EMACalculator(period=5)

        # Feed 4 prices (less than period)
        for i in range(4):
            result = calc.update(Decimal(100 + i))
            assert result is None
            assert not calc.is_ready

    def test_ema_ready_after_warmup(self):
        """Test that EMA becomes ready after warmup period."""
        calc = EMACalculator(period=3)

        # Feed exactly period prices
        calc.update(Decimal(100))
        calc.update(Decimal(102))
        result = calc.update(Decimal(101))

        assert result is not None
        assert calc.is_ready

    def test_ema_initial_value_is_sma(self):
        """Test that initial EMA value equals SMA of first period prices."""
        calc = EMACalculator(period=3)
        prices = [Decimal(100), Decimal(102), Decimal(101)]

        calc.bulk_update(prices)

        # SMA = (100 + 102 + 101) / 3 = 101
        expected_sma = Decimal(101)
        assert calc.value == expected_sma

    def test_ema_update_after_warmup(self):
        """Test EMA updates correctly after warmup."""
        calc = EMACalculator(period=2)

        # Warmup
        calc.update(Decimal(100))
        calc.update(Decimal(100))  # EMA = 100 (SMA)

        # New price higher than EMA
        result = calc.update(Decimal(110))

        # EMA should increase but be less than new price
        assert result > Decimal(100)
        assert result < Decimal(110)

    def test_ema_smoothing_effect(self):
        """Test that EMA smooths price movements."""
        calc = EMACalculator(period=10)
        prices = [Decimal(100)] * 10  # Stable prices

        calc.bulk_update(prices)
        base_ema = calc.value

        # Single price spike
        spike_ema = calc.update(Decimal(150))

        # EMA should move up but not by full 50
        assert spike_ema > base_ema
        assert spike_ema - base_ema < Decimal(50)

    def test_reset_clears_state(self):
        """Test that reset clears all state."""
        calc = EMACalculator(period=3)
        calc.bulk_update([Decimal(100), Decimal(102), Decimal(101)])

        assert calc.is_ready
        assert calc.value is not None

        calc.reset()

        assert not calc.is_ready
        assert calc.value is None

    def test_bulk_update_convenience(self):
        """Test bulk_update processes all prices."""
        calc = EMACalculator(period=3)
        prices = [Decimal(100 + i) for i in range(10)]

        result = calc.bulk_update(prices)

        assert calc.is_ready
        assert result is not None
        assert result == calc.value


class TestCalculateEMASeries:
    """Test EMA series calculation function."""

    def test_series_length_matches_input(self):
        """Test that output series has same length as input."""
        prices = [Decimal(100 + i) for i in range(20)]
        results = calculate_ema_series(prices, period=10)

        assert len(results) == len(prices)

    def test_series_has_none_during_warmup(self):
        """Test that series has None values during warmup."""
        prices = [Decimal(100 + i) for i in range(10)]
        results = calculate_ema_series(prices, period=5)

        # First (period - 1) values should be None
        for i in range(4):
            assert results[i] is None

        # From index 4 (5th element) onwards should have values
        for i in range(4, len(results)):
            assert results[i] is not None

    def test_series_values_increase_with_rising_prices(self):
        """Test that EMA rises when prices consistently increase."""
        prices = [Decimal(100 + i * 10) for i in range(15)]
        results = calculate_ema_series(prices, period=5)

        # Check that EMA values increase (after warmup)
        for i in range(6, len(results)):
            assert results[i] > results[i - 1]

    def test_series_with_constant_prices(self):
        """Test EMA with constant prices equals the constant."""
        prices = [Decimal(100)] * 10
        results = calculate_ema_series(prices, period=5)

        # After warmup, EMA should equal the constant price
        for i in range(5, len(results)):
            assert results[i] == Decimal(100)
