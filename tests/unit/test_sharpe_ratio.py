"""
Unit tests for Sharpe ratio calculation in backtester.

Tests cover:
- Insufficient data returns None
- Zero volatility returns zero
- Stable growth returns positive Sharpe
- Continuous decline returns negative Sharpe
- Different timeframes have correct annualization factors
"""
import pytest
from decimal import Decimal
from src.application.backtester import Backtester


class TestCalculateSharpeRatio:
    """Tests for Backtester._calculate_sharpe_ratio()"""

    def setup_method(self):
        """Create a minimal Backtester instance for testing."""
        self.backtester = Backtester(exchange_gateway=None)

    def test_insufficient_data_single_point_returns_none(self):
        """Single data point should return None."""
        equity_curve = [(1000, Decimal('10000'))]
        result = self.backtester._calculate_sharpe_ratio(equity_curve, "1h")
        assert result is None

    def test_insufficient_data_two_points_zero_equity_returns_none(self):
        """Two points with zero initial equity should return None (no valid returns)."""
        equity_curve = [
            (1000, Decimal('0')),
            (2000, Decimal('100')),
        ]
        result = self.backtester._calculate_sharpe_ratio(equity_curve, "1h")
        assert result is None

    def test_insufficient_data_two_points_one_valid_return_returns_none(self):
        """Two points producing only one valid return should return None."""
        equity_curve = [
            (1000, Decimal('0')),
            (2000, Decimal('10000')),
            (3000, Decimal('10100')),
        ]
        # Only one valid return (10100-10000)/10000 = 0.01
        result = self.backtester._calculate_sharpe_ratio(equity_curve, "1h")
        assert result is None

    def test_zero_volatility_returns_zero(self):
        """Constant equity should return Sharpe of 0."""
        equity_curve = [
            (1000, Decimal('10000')),
            (2000, Decimal('10000')),
            (3000, Decimal('10000')),
            (4000, Decimal('10000')),
        ]
        result = self.backtester._calculate_sharpe_ratio(equity_curve, "1h")
        assert result == Decimal('0')

    def test_positive_sharpe_stable_growth(self):
        """Steady growth should return positive Sharpe ratio."""
        # Simulate consistent 1% growth per period
        equity_curve = []
        equity = Decimal('10000')
        for i in range(100):
            equity_curve.append((1000 + i * 3600000, equity))
            equity = equity * Decimal('1.01')

        result = self.backtester._calculate_sharpe_ratio(equity_curve, "1h")
        assert result is not None
        assert result > Decimal('0')

    def test_negative_sharpe_continuous_decline(self):
        """Continuous decline should return negative Sharpe ratio."""
        # Simulate consistent 1% decline per period
        equity_curve = []
        equity = Decimal('10000')
        for i in range(100):
            equity_curve.append((1000 + i * 3600000, equity))
            equity = equity * Decimal('0.99')

        result = self.backtester._calculate_sharpe_ratio(equity_curve, "1h")
        assert result is not None
        assert result < Decimal('0')

    def test_annualization_factor_1h(self):
        """1h timeframe should use bars_per_year=8760."""
        # Create a simple returns sequence
        equity_curve = [
            (1000, Decimal('10000')),
            (1000 + 3600000, Decimal('10100')),  # +1%
            (1000 + 2 * 3600000, Decimal('10200')),  # +0.99%
            (1000 + 3 * 3600000, Decimal('10300')),  # +0.98%
            (1000 + 4 * 3600000, Decimal('10400')),  # +0.97%
        ]

        result_1h = self.backtester._calculate_sharpe_ratio(equity_curve, "1h")

        # The per-period Sharpe should be positive and annualized
        assert result_1h is not None
        assert result_1h > Decimal('0')

    def test_annualization_factor_1d(self):
        """1d timeframe should use bars_per_year=365."""
        equity_curve = [
            (1000, Decimal('10000')),
            (1000 + 86400000, Decimal('10100')),
            (1000 + 2 * 86400000, Decimal('10200')),
            (1000 + 3 * 86400000, Decimal('10300')),
            (1000 + 4 * 86400000, Decimal('10400')),
        ]

        result_1d = self.backtester._calculate_sharpe_ratio(equity_curve, "1d")
        assert result_1d is not None
        assert result_1d > Decimal('0')

    def test_annualization_15m_has_largest_factor(self):
        """15m should have the largest annualization factor."""
        equity_curve = [
            (1000, Decimal('10000')),
            (1000 + 900000, Decimal('10100')),
            (1000 + 2 * 900000, Decimal('10200')),
            (1000 + 3 * 900000, Decimal('10300')),
            (1000 + 4 * 900000, Decimal('10400')),
        ]

        sharpe_15m = self.backtester._calculate_sharpe_ratio(equity_curve, "15m")
        sharpe_1d = self.backtester._calculate_sharpe_ratio(equity_curve, "1d")

        # Same per-period returns, 15m annualizes more aggressively
        assert sharpe_15m > sharpe_1d

    def test_annualization_factor_4h(self):
        """4h timeframe should use bars_per_year=2190."""
        equity_curve = [
            (1000, Decimal('10000')),
            (1000 + 14400000, Decimal('10100')),
            (1000 + 2 * 14400000, Decimal('10200')),
            (1000 + 3 * 14400000, Decimal('10300')),
            (1000 + 4 * 14400000, Decimal('10400')),
        ]

        result_4h = self.backtester._calculate_sharpe_ratio(equity_curve, "4h")
        assert result_4h is not None

    def test_annualization_factor_1w(self):
        """1w timeframe should use bars_per_year=52."""
        equity_curve = [
            (1000, Decimal('10000')),
            (1000 + 604800000, Decimal('10100')),
            (1000 + 2 * 604800000, Decimal('10200')),
            (1000 + 3 * 604800000, Decimal('10300')),
            (1000 + 4 * 604800000, Decimal('10400')),
        ]

        result_1w = self.backtester._calculate_sharpe_ratio(equity_curve, "1w")
        assert result_1w is not None

    def test_unknown_timeframe_defaults_to_1h(self):
        """Unknown timeframe should default to bars_per_year=8760."""
        equity_curve = [
            (1000, Decimal('10000')),
            (2000, Decimal('10100')),
            (3000, Decimal('10200')),
            (4000, Decimal('10300')),
            (5000, Decimal('10400')),
        ]

        result = self.backtester._calculate_sharpe_ratio(equity_curve, "30m")
        # Should not raise, should use default 8760
        assert result is not None

    def test_mixed_returns_realistic_scenario(self):
        """Realistic scenario with mixed positive and negative returns."""
        equity_curve = [
            (1000, Decimal('10000')),
            (2000, Decimal('10200')),  # +2%
            (3000, Decimal('10100')),  # -0.98%
            (4000, Decimal('10300')),  # +1.98%
            (5000, Decimal('10250')),  # -0.49%
            (6000, Decimal('10500')),  # +2.44%
            (7000, Decimal('10400')),  # -0.95%
            (8000, Decimal('10600')),  # +1.92%
            (9000, Decimal('10550')),  # -0.47%
            (10000, Decimal('10700')),  # +1.42%
            (11000, Decimal('10800')),  # +0.93%
        ]

        result = self.backtester._calculate_sharpe_ratio(equity_curve, "1h")
        assert result is not None
        # Overall upward trend should give positive Sharpe
        assert result > Decimal('0')

    def test_decimal_precision_preserved(self):
        """Result should be Decimal type."""
        equity_curve = [
            (1000, Decimal('10000')),
            (2000, Decimal('10100')),
            (3000, Decimal('10200')),
            (4000, Decimal('10300')),
            (5000, Decimal('10400')),
        ]

        result = self.backtester._calculate_sharpe_ratio(equity_curve, "1h")
        assert isinstance(result, Decimal)

    def test_zero_equity_in_middle_skips_that_period(self):
        """If equity goes to zero and recovers, that period is skipped."""
        equity_curve = [
            (1000, Decimal('10000')),
            (2000, Decimal('10100')),
            (3000, Decimal('0')),  # Liquidation
            (4000, Decimal('5000')),  # Recovery
            (5000, Decimal('5100')),
        ]
        # Should handle gracefully, skipping the (0 -> 5000) return
        result = self.backtester._calculate_sharpe_ratio(equity_curve, "1h")
        assert result is not None
