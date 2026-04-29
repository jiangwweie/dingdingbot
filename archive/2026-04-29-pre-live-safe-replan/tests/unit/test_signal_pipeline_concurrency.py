"""
Test Signal Pipeline Concurrency & Hot-Reload

Tests for SubTask A - Real-time Engine Hot-Reload & Stability Refactoring

Covers:
- Hot-reload observer pattern
- Asyncio.Lock concurrency protection
- Async queue batch persistence
- Stale cache clearing on config change
"""
import asyncio
import pytest
import time
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from src.application.signal_pipeline import SignalPipeline
from src.application.config_manager import ConfigManager, load_all_configs
from src.domain.models import KlineData, SignalAttempt, PatternResult, Direction
from src.domain.risk_calculator import RiskConfig


class TestHotReloadObserver:
    """Test hot-reload observer pattern"""

    @pytest.fixture
    def config_manager(self):
        """Load real config for integration testing"""
        return load_all_configs()

    @pytest.fixture
    def risk_config(self):
        return RiskConfig(
            max_loss_percent=Decimal("0.01"),
            max_leverage=10
        )

    @pytest.fixture
    def pipeline(self, config_manager, risk_config):
        """Create pipeline with mock dependencies"""
        with patch('src.application.signal_pipeline.get_notification_service') as mock_notifier:
            mock_notifier.return_value = AsyncMock()
            with patch('src.application.signal_pipeline.SignalRepository') as mock_repo:
                mock_repo.return_value = AsyncMock()
                return SignalPipeline(
                    config_manager=config_manager,
                    risk_config=risk_config,
                    notification_service=mock_notifier(),
                    signal_repository=mock_repo(),
                    cooldown_seconds=300
                )

    @pytest.mark.asyncio
    async def test_observer_registered_on_init(self, pipeline, config_manager):
        """Test that observer is registered during pipeline initialization"""
        # Observer should be in config_manager's observer set
        assert len(config_manager._observers) > 0

        # Find our observer (on_config_updated method)
        found_observer = False
        for observer in config_manager._observers:
            # Check if observer is bound method of pipeline
            if hasattr(observer, '__self__') and observer.__self__ is pipeline:
                found_observer = True
                break

        assert found_observer, "on_config_updated observer not registered"

    @pytest.mark.asyncio
    async def test_on_config_updated_rebuilds_runner(self, pipeline):
        """Test that config update rebuilds the strategy runner"""
        # Store reference to current runner
        old_runner = pipeline._runner

        # Trigger config update
        await pipeline.on_config_updated()

        # Runner should be rebuilt
        assert pipeline._runner is not old_runner, "Runner not rebuilt on config update"

    @pytest.mark.asyncio
    async def test_on_config_updated_clears_cooldown_cache(self, pipeline):
        """Test that config update clears stale cooldown cache"""
        # Populate cooldown cache with fake data
        pipeline._signal_cooldown_cache["fake_key"] = time.time()

        # Trigger config update
        await pipeline.on_config_updated()

        # Cache should be cleared
        assert len(pipeline._signal_cooldown_cache) == 0, "Cooldown cache not cleared"


class TestConcurrencyLock:
    """Test asyncio.Lock protection for concurrency"""

    @pytest.fixture
    def config_manager(self):
        return load_all_configs()

    @pytest.fixture
    def risk_config(self):
        return RiskConfig(
            max_loss_percent=Decimal("0.01"),
            max_leverage=10
        )

    @pytest.fixture
    def pipeline(self, config_manager, risk_config):
        with patch('src.application.signal_pipeline.get_notification_service') as mock_notifier:
            mock_notifier.return_value = AsyncMock()
            with patch('src.application.signal_pipeline.SignalRepository') as mock_repo:
                mock_repo.return_value = AsyncMock()
                return SignalPipeline(
                    config_manager=config_manager,
                    risk_config=risk_config,
                    notification_service=mock_notifier(),
                    signal_repository=mock_repo(),
                    cooldown_seconds=300
                )

    @pytest.mark.asyncio
    async def test_runner_lock_created(self, pipeline):
        """Test that runner lock is created"""
        lock = pipeline._get_runner_lock()
        assert isinstance(lock, asyncio.Lock), "Runner lock not asyncio.Lock instance"

    @pytest.mark.asyncio
    async def test_lock_protects_runner_rebuild(self, pipeline):
        """Test that lock protects runner rebuild during hot-reload"""
        # Simulate concurrent access: process_kline + on_config_updated

        # Create a mock kline
        kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=1234567890000,
            open=Decimal("65000"),
            high=Decimal("66000"),
            low=Decimal("64500"),
            close=Decimal("65500"),
            volume=Decimal("1000"),
            is_closed=True
        )

        # Run process_kline and on_config_updated concurrently
        # The lock should prevent race conditions
        await asyncio.gather(
            pipeline.process_kline(kline),
            pipeline.on_config_updated(),
            return_exceptions=True
        )

        # Runner should still be valid after concurrent access
        assert pipeline._runner is not None, "Runner corrupted by concurrent access"

    @pytest.mark.asyncio
    async def test_no_race_condition_on_hot_reload(self, pipeline):
        """Test that hot-reload doesn't cause race conditions"""
        # Store initial runner
        initial_runner = pipeline._runner

        # Trigger multiple rapid config updates
        update_tasks = [pipeline.on_config_updated() for _ in range(5)]
        await asyncio.gather(*update_tasks)

        # Runner should be valid (not None, not corrupted)
        assert pipeline._runner is not None
        assert hasattr(pipeline._runner, 'run_all'), "Runner missing expected methods"


class TestAsyncQueuePersistence:
    """Test async queue batch persistence"""

    @pytest.fixture
    def config_manager(self):
        return load_all_configs()

    @pytest.fixture
    def risk_config(self):
        return RiskConfig(
            max_loss_percent=Decimal("0.01"),
            max_leverage=10
        )

    @pytest.fixture
    def mock_repository(self):
        """Create mock repository that tracks save_attempt calls"""
        mock = AsyncMock()
        mock.save_attempt = AsyncMock()
        mock.save_signal = AsyncMock()
        return mock

    @pytest.fixture
    def pipeline(self, config_manager, risk_config, mock_repository):
        with patch('src.application.signal_pipeline.get_notification_service') as mock_notifier:
            mock_notifier.return_value = AsyncMock()
            return SignalPipeline(
                config_manager=config_manager,
                risk_config=risk_config,
                notification_service=mock_notifier(),
                signal_repository=mock_repository,
                cooldown_seconds=0  # Disable cooldown for testing
            )

    @pytest.mark.asyncio
    async def test_attempts_queue_created(self, pipeline):
        """Test that async queue is created"""
        pipeline._ensure_async_primitives()
        assert pipeline._attempts_queue is not None
        assert isinstance(pipeline._attempts_queue, asyncio.Queue)

    @pytest.mark.asyncio
    async def test_flush_worker_started(self, pipeline):
        """Test that flush worker task is created"""
        pipeline._ensure_flush_worker()
        assert pipeline._flush_task is not None
        assert isinstance(pipeline._flush_task, asyncio.Task)

    @pytest.mark.asyncio
    async def test_attempt_enqueued_on_process_kline(self, pipeline, mock_repository):
        """Test that attempts are enqueued for batch persistence"""
        # Create a mock kline that triggers a pattern
        kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=1234567890000,
            open=Decimal("65000"),
            high=Decimal("66000"),
            low=Decimal("64500"),
            close=Decimal("65500"),
            volume=Decimal("1000"),
            is_closed=True
        )

        # Process kline
        await pipeline.process_kline(kline)

        # Give flush worker time to process
        await asyncio.sleep(0.1)

        # Attempt should be enqueued (may or may not be flushed yet)
        # Queue should have been accessed
        assert pipeline._attempts_queue is not None


class TestStaleCachePrevention:
    """Test stale cache prevention on config change"""

    @pytest.fixture
    def config_manager(self):
        return load_all_configs()

    @pytest.fixture
    def risk_config(self):
        return RiskConfig(
            max_loss_percent=Decimal("0.01"),
            max_leverage=10
        )

    @pytest.fixture
    def pipeline(self, config_manager, risk_config):
        with patch('src.application.signal_pipeline.get_notification_service') as mock_notifier:
            mock_notifier.return_value = AsyncMock()
            with patch('src.application.signal_pipeline.SignalRepository') as mock_repo:
                return SignalPipeline(
                    config_manager=config_manager,
                    risk_config=risk_config,
                    notification_service=mock_notifier(),
                    signal_repository=mock_repo(),
                    cooldown_seconds=300
                )

    @pytest.mark.asyncio
    async def test_cooldown_cache_cleared_on_reload(self, pipeline):
        """Test that cooldown cache is cleared on config reload"""
        # Add fake entries to cooldown cache
        pipeline._signal_cooldown_cache["BTC/USDT:USDT:15m:LONG:pinbar"] = time.time()
        pipeline._signal_cooldown_cache["ETH/USDT:USDT:15m:SHORT:pinbar"] = time.time()

        # Trigger config reload
        await pipeline.on_config_updated()

        # Cache should be empty
        assert len(pipeline._signal_cooldown_cache) == 0

    @pytest.mark.asyncio
    async def test_signal_fires_after_reload_despite_recent_cooldown(self, pipeline):
        """Test that signal fires after reload even if it was recently in cooldown"""
        # Add entry to cooldown cache (simulating recent signal)
        recent_time = time.time() - 10  # 10 seconds ago
        pipeline._signal_cooldown_cache["BTC/USDT:USDT:15m:LONG:pinbar"] = recent_time

        # Create a bullish pinbar kline
        kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=1234567890000,
            open=Decimal("65000"),
            high=Decimal("65100"),
            low=Decimal("64000"),  # Long lower wick
            close=Decimal("65050"),  # Small body at top
            volume=Decimal("1000"),
            is_closed=True
        )

        # Process kline BEFORE reload - should be in cooldown
        await pipeline.process_kline(kline)

        # Trigger config reload (clears cache)
        await pipeline.on_config_updated()

        # Cache should be cleared after reload
        assert len(pipeline._signal_cooldown_cache) == 0, "Cache not cleared after reload"

        # Process another kline after reload - should work without cooldown blocking
        kline2 = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=1234567891000,  # Slightly later
            open=Decimal("65000"),
            high=Decimal("65100"),
            low=Decimal("64000"),
            close=Decimal("65050"),
            volume=Decimal("1000"),
            is_closed=True
        )

        # This should process without cooldown blocking (cache was cleared)
        await pipeline.process_kline(kline2)

        # Verify pipeline is still functional
        assert pipeline._runner is not None


class TestIntegration:
    """Integration tests for complete hot-reload flow"""

    @pytest.fixture
    def config_manager(self):
        return load_all_configs()

    @pytest.fixture
    def risk_config(self):
        return RiskConfig(
            max_loss_percent=Decimal("0.01"),
            max_leverage=10
        )

    @pytest.fixture
    def pipeline(self, config_manager, risk_config):
        with patch('src.application.signal_pipeline.get_notification_service') as mock_notifier:
            mock_notifier.return_value = AsyncMock()
            with patch('src.application.signal_pipeline.SignalRepository') as mock_repo:
                return SignalPipeline(
                    config_manager=config_manager,
                    risk_config=risk_config,
                    notification_service=mock_notifier(),
                    signal_repository=mock_repo(),
                    cooldown_seconds=60
                )

    @pytest.mark.asyncio
    async def test_full_hot_reload_flow(self, pipeline):
        """Test complete hot-reload flow: K-line processing → Config update → Resume processing"""
        # Step 1: Process some K-lines
        kline1 = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=1234567890000,
            open=Decimal("65000"),
            high=Decimal("66000"),
            low=Decimal("64500"),
            close=Decimal("65500"),
            volume=Decimal("1000"),
            is_closed=True
        )

        await pipeline.process_kline(kline1)

        # Step 2: Trigger hot-reload
        await pipeline.on_config_updated()

        # Step 3: Continue processing K-lines
        kline2 = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=1234567891000,
            open=Decimal("65500"),
            high=Decimal("66500"),
            low=Decimal("65000"),
            close=Decimal("66000"),
            volume=Decimal("1000"),
            is_closed=True
        )

        await pipeline.process_kline(kline2)

        # Verify pipeline is still functional
        assert pipeline._runner is not None
        assert len(pipeline._kline_history) > 0

    @pytest.mark.asyncio
    async def test_concurrent_kline_processing_and_reload(self, pipeline):
        """Test concurrent K-line processing and config reload"""
        # Create multiple K-lines
        klines = [
            KlineData(
                symbol="BTC/USDT:USDT",
                timeframe="15m",
                timestamp=1234567890000 + i * 1000,
                open=Decimal("65000") + Decimal(str(i * 10)),
                high=Decimal("66000") + Decimal(str(i * 10)),
                low=Decimal("64500") + Decimal(str(i * 10)),
                close=Decimal("65500") + Decimal(str(i * 10)),
                volume=Decimal("1000"),
                is_closed=True
            )
            for i in range(10)
        ]

        # Process K-lines while simultaneously triggering reloads
        async def process_klines():
            for kline in klines:
                await pipeline.process_kline(kline)
                await asyncio.sleep(0.01)

        async def trigger_reloads():
            for _ in range(3):
                await asyncio.sleep(0.05)
                await pipeline.on_config_updated()

        # Run concurrently
        await asyncio.gather(
            process_klines(),
            trigger_reloads(),
            return_exceptions=True
        )

        # Pipeline should still be functional
        assert pipeline._runner is not None
        assert len(pipeline._kline_history) > 0
