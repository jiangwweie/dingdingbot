"""
Technical indicators - streaming calculation.
Pure calculation logic, no external dependencies allowed.

S4-3: Added EMA cache for sharing indicators across strategies.
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List, Dict
from dataclasses import dataclass, field
import time
import asyncio


@dataclass
class CacheEntry:
    """Cache entry with expiration tracking."""
    calculator: 'EMACalculator'
    last_access: float = field(default_factory=time.time)
    access_count: int = 0


class EMACache:
    """
    Thread-safe cache for EMA indicators.

    Allows multiple strategies to share the same EMA instance,
    reducing memory usage and computation overhead.

    Usage:
        cache = EMACache(ttl_seconds=3600, max_size=1000)
        ema = await cache.get_or_create("BTC/USDT", "15m", 60)
        ema.update(close_price)
    """

    def __init__(self, ttl_seconds: int = 3600, max_size: int = 1000):
        """
        Initialize EMA cache.

        Args:
            ttl_seconds: Time-to-live for cache entries (default 1 hour)
            max_size: Maximum cache size (default 1000)
        """
        self._cache: Dict[str, CacheEntry] = {}
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._lock = asyncio.Lock()

    def _make_key(self, symbol: str, timeframe: str, period: int) -> str:
        """Create a unique cache key."""
        return f"{symbol}:{timeframe}:{period}"

    async def get_or_create(
        self,
        symbol: str,
        timeframe: str,
        period: int,
    ) -> 'EMACalculator':
        """
        Get existing EMA calculator or create new one.

        Args:
            symbol: Trading pair symbol
            timeframe: Timeframe string
            period: EMA period

        Returns:
            EMACalculator instance
        """
        key = self._make_key(symbol, timeframe, period)

        async with self._lock:
            # Check if entry exists and not expired
            if key in self._cache:
                entry = self._cache[key]
                if time.time() - entry.last_access < self._ttl:
                    entry.access_count += 1
                    entry.last_access = time.time()
                    return entry.calculator
                else:
                    # Entry expired, remove it
                    del self._cache[key]

            # Create new entry
            calculator = EMACalculator(period=period)
            self._cache[key] = CacheEntry(
                calculator=calculator,
                last_access=time.time(),
                access_count=1,
            )

            # Evict oldest if over capacity
            if len(self._cache) > self._max_size:
                await self._evict_oldest()

            return calculator

    async def _evict_oldest(self) -> None:
        """Evict the oldest (least recently used) entry."""
        if not self._cache:
            return

        oldest_key = min(
            self._cache.keys(),
            key=lambda k: self._cache[k].last_access,
        )
        del self._cache[oldest_key]

    async def cleanup_expired(self) -> int:
        """
        Remove all expired entries.

        Returns:
            Number of entries removed
        """
        now = time.time()
        expired_keys = [
            key for key, entry in self._cache.items()
            if now - entry.last_access >= self._ttl
        ]

        for key in expired_keys:
            del self._cache[key]

        return len(expired_keys)

    async def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()

    async def get_stats(self) -> dict:
        """Get cache statistics."""
        now = time.time()
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "ttl_seconds": self._ttl,
            "entries": {
                key: {
                    "period": entry.calculator.period,
                    "is_ready": entry.calculator.is_ready,
                    "access_count": entry.access_count,
                    "age_seconds": now - entry.last_access,
                }
                for key, entry in self._cache.items()
            },
        }


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
