"""
Unit tests for PerformanceTracker.
"""
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from src.domain.models import KlineData
from src.application.performance_tracker import PerformanceTracker


@pytest.fixture
def sample_kline():
    """Create a sample K-line for testing."""
    return KlineData(
        symbol="BTC/USDT:USDT",
        timeframe="1h",
        timestamp=1700000000000,
        open=Decimal("40000"),
        high=Decimal("40500"),
        low=Decimal("39500"),
        close=Decimal("40200"),
        volume=Decimal("1000"),
        is_closed=True,
    )


@pytest.fixture
def repository():
    """Create a mock repository."""
    repo = MagicMock()
    repo.get_pending_signals = AsyncMock()
    repo.update_signal_status = AsyncMock()
    return repo


class TestPerformanceTracker:
    """Test PerformanceTracker class."""

    @pytest.mark.asyncio
    async def test_no_pending_signals(self, repository):
        """Test when there are no PENDING signals."""
        repository.get_pending_signals.return_value = []

        tracker = PerformanceTracker()
        kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="1h",
            timestamp=1700000000000,
            open=Decimal("40000"),
            high=Decimal("40500"),
            low=Decimal("39500"),
            close=Decimal("40200"),
            volume=Decimal("1000"),
            is_closed=True,
        )

        await tracker.check_pending_signals(kline, repository)

        repository.get_pending_signals.assert_called_once_with("BTC/USDT:USDT")
        repository.update_signal_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_long_signal_hits_stop_loss(self, repository):
        """Test LONG signal hits stop-loss."""
        # K-line low = 39500, stop_loss = 39600 -> hits SL
        repository.get_pending_signals.return_value = [
            {
                "id": 1,
                "symbol": "BTC/USDT:USDT",
                "timeframe": "1h",
                "direction": "long",
                "entry_price": Decimal("40000"),
                "stop_loss": Decimal("39600"),
                "take_profit_1": Decimal("41000"),
            }
        ]

        tracker = PerformanceTracker()
        kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="1h",
            timestamp=1700000000000,
            open=Decimal("40000"),
            high=Decimal("40500"),
            low=Decimal("39500"),  # Below stop_loss
            close=Decimal("40200"),
            volume=Decimal("1000"),
            is_closed=True,
        )

        await tracker.check_pending_signals(kline, repository)

        repository.update_signal_status.assert_called_once_with(1, "LOST", Decimal("-1.0"))

    @pytest.mark.asyncio
    async def test_long_signal_hits_take_profit(self, repository):
        """Test LONG signal hits take-profit."""
        # K-line high = 41200, take_profit = 41000 -> hits TP
        repository.get_pending_signals.return_value = [
            {
                "id": 2,
                "symbol": "BTC/USDT:USDT",
                "timeframe": "1h",
                "direction": "long",
                "entry_price": Decimal("40000"),
                "stop_loss": Decimal("39500"),
                "take_profit_1": Decimal("41000"),
            }
        ]

        tracker = PerformanceTracker()
        kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="1h",
            timestamp=1700000000000,
            open=Decimal("40000"),
            high=Decimal("41200"),  # Above take_profit
            low=Decimal("39800"),
            close=Decimal("41000"),
            volume=Decimal("1000"),
            is_closed=True,
        )

        await tracker.check_pending_signals(kline, repository)

        # PnL ratio = (TP - entry) / (entry - SL) = (41000 - 40000) / (40000 - 39500) = 1000 / 500 = 2.0
        repository.update_signal_status.assert_called_once_with(2, "WON", Decimal("2.0"))

    @pytest.mark.asyncio
    async def test_short_signal_hits_stop_loss(self, repository):
        """Test SHORT signal hits stop-loss."""
        # K-line high = 40600, stop_loss = 40500 -> hits SL
        repository.get_pending_signals.return_value = [
            {
                "id": 3,
                "symbol": "BTC/USDT:USDT",
                "timeframe": "1h",
                "direction": "short",
                "entry_price": Decimal("40000"),
                "stop_loss": Decimal("40500"),
                "take_profit_1": Decimal("39000"),
            }
        ]

        tracker = PerformanceTracker()
        kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="1h",
            timestamp=1700000000000,
            open=Decimal("40000"),
            high=Decimal("40600"),  # Above stop_loss
            low=Decimal("39500"),
            close=Decimal("40200"),
            volume=Decimal("1000"),
            is_closed=True,
        )

        await tracker.check_pending_signals(kline, repository)

        repository.update_signal_status.assert_called_once_with(3, "LOST", Decimal("-1.0"))

    @pytest.mark.asyncio
    async def test_short_signal_hits_take_profit(self, repository):
        """Test SHORT signal hits take-profit."""
        # K-line low = 38800, take_profit = 39000 -> hits TP
        repository.get_pending_signals.return_value = [
            {
                "id": 4,
                "symbol": "BTC/USDT:USDT",
                "timeframe": "1h",
                "direction": "short",
                "entry_price": Decimal("40000"),
                "stop_loss": Decimal("40500"),
                "take_profit_1": Decimal("39000"),
            }
        ]

        tracker = PerformanceTracker()
        kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="1h",
            timestamp=1700000000000,
            open=Decimal("40000"),
            high=Decimal("40200"),
            low=Decimal("38800"),  # Below take_profit
            close=Decimal("39000"),
            volume=Decimal("1000"),
            is_closed=True,
        )

        await tracker.check_pending_signals(kline, repository)

        # PnL ratio = (entry - TP) / (SL - entry) = (40000 - 39000) / (40500 - 40000) = 1000 / 500 = 2.0
        repository.update_signal_status.assert_called_once_with(4, "WON", Decimal("2.0"))

    @pytest.mark.asyncio
    async def test_signal_not_hit(self, repository):
        """Test signal where price doesn't hit TP or SL."""
        # K-line high = 40500, low = 39800
        # LONG: SL=39000, TP=41000 -> not hit
        repository.get_pending_signals.return_value = [
            {
                "id": 5,
                "symbol": "BTC/USDT:USDT",
                "timeframe": "1h",
                "direction": "long",
                "entry_price": Decimal("40000"),
                "stop_loss": Decimal("39000"),
                "take_profit_1": Decimal("41000"),
            }
        ]

        tracker = PerformanceTracker()
        kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="1h",
            timestamp=1700000000000,
            open=Decimal("40000"),
            high=Decimal("40500"),
            low=Decimal("39800"),
            close=Decimal("40200"),
            volume=Decimal("1000"),
            is_closed=True,
        )

        await tracker.check_pending_signals(kline, repository)

        repository.update_signal_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_take_profit_level(self, repository):
        """Test signal with no take-profit level set."""
        repository.get_pending_signals.return_value = [
            {
                "id": 6,
                "symbol": "BTC/USDT:USDT",
                "timeframe": "1h",
                "direction": "long",
                "entry_price": Decimal("40000"),
                "stop_loss": Decimal("39000"),
                "take_profit_1": None,
            }
        ]

        tracker = PerformanceTracker()
        kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="1h",
            timestamp=1700000000000,
            open=Decimal("40000"),
            high=Decimal("42000"),
            low=Decimal("38000"),
            close=Decimal("41000"),
            volume=Decimal("1000"),
            is_closed=True,
        )

        await tracker.check_pending_signals(kline, repository)

        repository.update_signal_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_extreme_kline_hits_stop_loss_first(self, repository):
        """Test extreme K-line that hits both SL and TP - SL takes priority (risk-first)."""
        # Extreme long wick: high=41500 (hits TP=41000), low=39400 (hits SL=39500)
        # Risk-first: should be LOST
        repository.get_pending_signals.return_value = [
            {
                "id": 7,
                "symbol": "BTC/USDT:USDT",
                "timeframe": "1h",
                "direction": "long",
                "entry_price": Decimal("40000"),
                "stop_loss": Decimal("39500"),
                "take_profit_1": Decimal("41000"),
            }
        ]

        tracker = PerformanceTracker()
        kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="1h",
            timestamp=1700000000000,
            open=Decimal("40000"),
            high=Decimal("41500"),  # Above TP
            low=Decimal("39400"),   # Below SL - priority
            close=Decimal("40500"),
            volume=Decimal("1000"),
            is_closed=True,
        )

        await tracker.check_pending_signals(kline, repository)

        # Should be LOST because SL is checked first (risk-first principle)
        repository.update_signal_status.assert_called_once_with(7, "LOST", Decimal("-1.0"))

    @pytest.mark.asyncio
    async def test_multiple_pending_signals(self, repository):
        """Test processing multiple pending signals."""
        repository.get_pending_signals.return_value = [
            {
                "id": 8,
                "symbol": "BTC/USDT:USDT",
                "timeframe": "1h",
                "direction": "long",
                "entry_price": Decimal("40000"),
                "stop_loss": Decimal("39000"),
                "take_profit_1": Decimal("42000"),  # Not hit (high=40500)
            },
            {
                "id": 9,
                "symbol": "BTC/USDT:USDT",
                "timeframe": "30m",
                "direction": "short",
                "entry_price": Decimal("40000"),
                "stop_loss": Decimal("41000"),  # Hit (high=40500... wait, not hit)
                "take_profit_1": Decimal("39000"),  # Not hit (low=39800)
            },
        ]

        tracker = PerformanceTracker()
        kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="1h",
            timestamp=1700000000000,
            open=Decimal("40000"),
            high=Decimal("40500"),
            low=Decimal("39800"),
            close=Decimal("40200"),
            volume=Decimal("1000"),
            is_closed=True,
        )

        await tracker.check_pending_signals(kline, repository)

        # Neither signal should be hit
        repository.update_signal_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test error handling in check_pending_signals."""
        repository = MagicMock()
        repository.get_pending_signals = AsyncMock(side_effect=Exception("DB error"))
        repository.update_signal_status = AsyncMock()

        tracker = PerformanceTracker()
        kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="1h",
            timestamp=1700000000000,
            open=Decimal("40000"),
            high=Decimal("40500"),
            low=Decimal("39500"),
            close=Decimal("40200"),
            volume=Decimal("1000"),
            is_closed=True,
        )

        # Should not raise, just log error
        await tracker.check_pending_signals(kline, repository)

        repository.get_pending_signals.assert_called_once()


class TestPerformanceTrackerPnLCalculation:
    """Test PnL ratio calculations for different scenarios."""

    @pytest.mark.asyncio
    async def test_long_pnl_ratio_calculation(self, repository):
        """Test LONG PnL ratio: (TP - entry) / (entry - SL)."""
        repository.get_pending_signals.return_value = [
            {
                "id": 10,
                "symbol": "BTC/USDT:USDT",
                "timeframe": "1h",
                "direction": "long",
                "entry_price": Decimal("50000"),
                "stop_loss": Decimal("48000"),
                "take_profit_1": Decimal("54000"),
            }
        ]

        tracker = PerformanceTracker()
        kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="1h",
            timestamp=1700000000000,
            open=Decimal("50000"),
            high=Decimal("54000"),  # Hits TP
            low=Decimal("49500"),
            close=Decimal("53500"),
            volume=Decimal("1000"),
            is_closed=True,
        )

        await tracker.check_pending_signals(kline, repository)

        # PnL = (54000 - 50000) / (50000 - 48000) = 4000 / 2000 = 2.0
        repository.update_signal_status.assert_called_once_with(10, "WON", Decimal("2.0"))

    @pytest.mark.asyncio
    async def test_short_pnl_ratio_calculation(self, repository):
        """Test SHORT PnL ratio: (entry - TP) / (SL - entry)."""
        repository.get_pending_signals.return_value = [
            {
                "id": 11,
                "symbol": "BTC/USDT:USDT",
                "timeframe": "1h",
                "direction": "short",
                "entry_price": Decimal("50000"),
                "stop_loss": Decimal("52000"),
                "take_profit_1": Decimal("46000"),
            }
        ]

        tracker = PerformanceTracker()
        kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="1h",
            timestamp=1700000000000,
            open=Decimal("50000"),
            high=Decimal("50500"),
            low=Decimal("46000"),  # Hits TP
            close=Decimal("46500"),
            volume=Decimal("1000"),
            is_closed=True,
        )

        await tracker.check_pending_signals(kline, repository)

        # PnL = (50000 - 46000) / (52000 - 50000) = 4000 / 2000 = 2.0
        repository.update_signal_status.assert_called_once_with(11, "WON", Decimal("2.0"))
