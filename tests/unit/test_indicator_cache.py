"""
Unit Tests for EMA Cache (S4-3).

Tests for:
1. Cache entry creation and retrieval
2. Cache entry sharing (same key returns same instance)
3. Cache expiration and cleanup
4. Cache eviction on capacity overflow
5. Concurrent access safety
"""
import pytest
import asyncio
import time
from decimal import Decimal

from src.domain.indicators import EMACache, EMACalculator


# ============================================================
# Test Basic Cache Operations
# ============================================================
class TestEMACacheBasic:
    """Test basic EMA cache functionality."""

    @pytest.mark.asyncio
    async def test_get_or_create_new(self):
        """Test creating a new cache entry."""
        cache = EMACache()
        ema = await cache.get_or_create("BTC/USDT", "15m", 60)

        assert isinstance(ema, EMACalculator)
        assert ema.period == 60

    @pytest.mark.asyncio
    async def test_get_returns_same_instance(self):
        """Test that same key returns same calculator instance."""
        cache = EMACache()

        ema1 = await cache.get_or_create("BTC/USDT", "15m", 60)
        ema2 = await cache.get_or_create("BTC/USDT", "15m", 60)

        assert ema1 is ema2  # Same object

    @pytest.mark.asyncio
    async def test_different_keys_return_different_instances(self):
        """Test that different keys return different instances."""
        cache = EMACache()

        ema1 = await cache.get_or_create("BTC/USDT", "15m", 60)
        ema2 = await cache.get_or_create("BTC/USDT", "1h", 60)

        assert ema1 is not ema2  # Different objects

    @pytest.mark.asyncio
    async def test_different_periods_return_different_instances(self):
        """Test that different periods return different instances."""
        cache = EMACache()

        ema1 = await cache.get_or_create("BTC/USDT", "15m", 60)
        ema2 = await cache.get_or_create("BTC/USDT", "15m", 120)

        assert ema1 is not ema2
        assert ema1.period == 60
        assert ema2.period == 120

    @pytest.mark.asyncio
    async def test_access_count_increments(self):
        """Test that access count increments on reuse."""
        cache = EMACache()

        await cache.get_or_create("BTC/USDT", "15m", 60)
        stats = await cache.get_stats()
        entry_stats = stats["entries"].get("BTC/USDT:15m:60", {})
        assert entry_stats.get("access_count", 0) >= 1

        # Access again
        await cache.get_or_create("BTC/USDT", "15m", 60)
        stats = await cache.get_stats()
        entry_stats = stats["entries"].get("BTC/USDT:15m:60", {})
        assert entry_stats.get("access_count", 0) >= 2


# ============================================================
# Test Cache Expiration
# ============================================================
class TestEMACacheExpiration:
    """Test EMA cache expiration functionality."""

    @pytest.mark.asyncio
    async def test_cache_cleanup_expired(self):
        """Test cleanup of expired entries."""
        cache = EMACache(ttl_seconds=1)  # 1 second TTL

        await cache.get_or_create("BTC/USDT", "15m", 60)
        await asyncio.sleep(1.1)  # Wait for expiration
        removed = await cache.cleanup_expired()

        assert removed == 1
        assert len(cache._cache) == 0

    @pytest.mark.asyncio
    async def test_cache_not_cleanup_active(self):
        """Test that active entries are not cleaned up."""
        cache = EMACache(ttl_seconds=10)  # 10 second TTL

        await cache.get_or_create("BTC/USDT", "15m", 60)
        await asyncio.sleep(0.1)  # Short wait
        removed = await cache.cleanup_expired()

        assert removed == 0
        assert len(cache._cache) == 1

    @pytest.mark.asyncio
    async def test_cache_clear(self):
        """Test clearing all cache entries."""
        cache = EMACache()

        # Add multiple entries
        await cache.get_or_create("BTC/USDT", "15m", 60)
        await cache.get_or_create("ETH/USDT", "15m", 60)
        await cache.get_or_create("BTC/USDT", "1h", 60)

        assert len(cache._cache) == 3

        await cache.clear()

        assert len(cache._cache) == 0


# ============================================================
# Test Cache Eviction
# ============================================================
class TestEMACacheEviction:
    """Test EMA cache eviction on capacity overflow."""

    @pytest.mark.asyncio
    async def test_cache_evict_over_capacity(self):
        """Test eviction when over max capacity."""
        cache = EMACache(max_size=3)

        await cache.get_or_create("BTC/USDT", "15m", 60)
        await cache.get_or_create("BTC/USDT", "1h", 60)
        await cache.get_or_create("BTC/USDT", "4h", 60)
        await cache.get_or_create("BTC/USDT", "1d", 60)  # Should trigger eviction

        assert len(cache._cache) <= 3

    @pytest.mark.asyncio
    async def test_cache_evict_oldest(self):
        """Test that oldest entry is evicted."""
        cache = EMACache(max_size=2)

        # Add entries with delays to establish order
        await cache.get_or_create("A", "15m", 60)
        await asyncio.sleep(0.01)
        await cache.get_or_create("B", "15m", 60)

        # Access A to make it recently used
        await cache.get_or_create("A", "15m", 60)

        # Add new entry, should evict B (oldest by last_access)
        await cache.get_or_create("C", "15m", 60)

        assert len(cache._cache) == 2
        # A should still exist (recently accessed)
        assert "A:15m:60" in cache._cache


# ============================================================
# Test Cache Statistics
# ============================================================
class TestEMACacheStats:
    """Test EMA cache statistics."""

    @pytest.mark.asyncio
    async def test_get_stats(self):
        """Test cache statistics."""
        cache = EMACache()

        await cache.get_or_create("BTC/USDT", "15m", 60)
        stats = await cache.get_stats()

        assert stats["size"] == 1
        assert stats["max_size"] == 1000
        assert stats["ttl_seconds"] == 3600
        assert "BTC/USDT:15m:60" in stats["entries"]

        entry = stats["entries"]["BTC/USDT:15m:60"]
        assert entry["period"] == 60
        assert entry["is_ready"] is False  # New calculator not initialized


# ============================================================
# Test Cache Concurrency
# ============================================================
class TestEMACacheConcurrency:
    """Test cache concurrency safety."""

    @pytest.mark.asyncio
    async def test_concurrent_get_or_create(self):
        """Test concurrent access returns same instance."""
        cache = EMACache()

        async def get_ema():
            return await cache.get_or_create("BTC/USDT", "15m", 60)

        # Run concurrent requests
        results = await asyncio.gather(*[get_ema() for _ in range(10)])

        # All should be the same instance
        assert all(r is results[0] for r in results)

    @pytest.mark.asyncio
    async def test_concurrent_different_keys(self):
        """Test concurrent access with different keys."""
        cache = EMACache()

        async def get_ema(symbol, timeframe):
            return await cache.get_or_create(symbol, timeframe, 60)

        # Run concurrent requests with different keys
        tasks = [
            get_ema("BTC/USDT", "15m"),
            get_ema("BTC/USDT", "1h"),
            get_ema("ETH/USDT", "15m"),
            get_ema("ETH/USDT", "1h"),
        ]
        results = await asyncio.gather(*tasks)

        # All should be different instances
        for i in range(len(results)):
            for j in range(i + 1, len(results)):
                assert results[i] is not results[j]


# ============================================================
# Test Calculator State Sharing
# ============================================================
class TestCalculatorStateSharing:
    """Test that calculator state is properly shared."""

    @pytest.mark.asyncio
    async def test_shared_calculator_state(self):
        """Test that updates to shared calculator are visible."""
        cache = EMACache()

        # Get calculator and update state
        ema1 = await cache.get_or_create("BTC/USDT", "15m", 60)
        prices = [Decimal(f"{i}.0") for i in range(60, 120)]
        ema1.bulk_update(prices)

        # Get same calculator again
        ema2 = await cache.get_or_create("BTC/USDT", "15m", 60)

        # State should be preserved
        assert ema2.is_ready is True
        assert ema2.value is not None
        assert ema1.value == ema2.value  # Same object, same value
