"""
Technical indicators - streaming calculation.
Pure calculation logic, no external dependencies allowed.
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List


class EMACalculator:
    """
    Exponential Moving Average calculator with streaming updates.

    Uses the standard EMA formula:
    EMA = (Close - EMA_prev) * Multiplier + EMA_prev
    where Multiplier = 2 / (period + 1)

    Thread-safe and supports multiple timeframes.
    """

    def __init__(self, period: int = 60):
        """
        Initialize EMA calculator.

        Args:
            period: EMA period (default 60 for EMA60)
        """
        if period < 1:
            raise ValueError(f"EMA period must be >= 1, got {period}")

        self._period = period
        self._multiplier = Decimal(2) / Decimal(period + 1)
        self._ema_value: Optional[Decimal] = None
        self._initialized = False
        self._price_buffer: List[Decimal] = []

    @property
    def period(self) -> int:
        return self._period

    @property
    def value(self) -> Optional[Decimal]:
        """Current EMA value, None if not initialized."""
        return self._ema_value

    @property
    def is_ready(self) -> bool:
        """Whether EMA has enough data to produce valid values."""
        return self._initialized

    def update(self, close_price: Decimal) -> Optional[Decimal]:
        """
        Update EMA with new close price.

        Args:
            close_price: Latest close price

        Returns:
            Updated EMA value, or None if still warming up
        """
        if not self._initialized:
            self._price_buffer.append(close_price)
            if len(self._price_buffer) >= self._period:
                self._initialized = True
                self._ema_value = self._calculate_initial_ema()
            return self._ema_value

        if self._ema_value is None:
            return None

        close_dec = Decimal(close_price)
        self._ema_value = (close_dec - self._ema_value) * self._multiplier + self._ema_value
        return self._ema_value

    def _calculate_initial_ema(self) -> Decimal:
        """
        Calculate initial EMA using SMA of first `period` prices.

        Returns:
            Simple moving average of the price buffer
        """
        if len(self._price_buffer) < self._period:
            raise ValueError(
                f"Not enough data for initial EMA: "
                f"have {len(self._price_buffer)}, need {self._period}"
            )

        total = sum(self._price_buffer[-self._period:])
        return total / Decimal(self._period)

    def reset(self) -> None:
        """Reset calculator state."""
        self._ema_value = None
        self._initialized = False
        self._price_buffer.clear()

    def bulk_update(self, prices: List[Decimal]) -> Optional[Decimal]:
        """
        Update EMA with a batch of historical prices (for warmup).

        Args:
            prices: List of close prices in chronological order

        Returns:
            Final EMA value after processing all prices
        """
        for price in prices:
            self.update(price)
        return self._ema_value


def calculate_ema_series(prices: List[Decimal], period: int = 60) -> List[Optional[Decimal]]:
    """
    Calculate EMA for a series of prices.

    Args:
        prices: List of close prices in chronological order
        period: EMA period

    Returns:
        List of EMA values (None for warmup period)
    """
    calc = EMACalculator(period=period)
    results: List[Optional[Decimal]] = []

    for price in prices:
        ema = calc.update(price)
        results.append(ema)

    return results
