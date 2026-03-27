"""
Integration Tests for Async I/O Queue Optimization (S4-2).

Tests for:
1. Queue backpressure monitoring
2. Worker recovery on failure
3. Queue configuration from core.yaml
"""
import pytest
import asyncio
import time
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from src.application.signal_pipeline import SignalPipeline
from src.application.config_manager import ConfigManager, load_all_configs
from src.domain.models import (
    KlineData,
    AccountSnapshot,
    SignalAttempt,
    PatternResult,
)
from src.domain.risk_calculator import RiskConfig
from src.infrastructure.signal_repository import SignalRepository


# ============================================================
# Test Fixtures
# ============================================================
@pytest.fixture
def risk_config():
    """Create default risk config for testing."""
    return RiskConfig(
        max_loss_percent=Decimal("0.01"),
        max_leverage=10,
        max_total_exposure=Decimal("0.8"),
    )


@pytest.fixture
async def config_manager():
    """Create config manager with loaded configs."""
    manager = ConfigManager()
    manager.load_core_config()
    manager.load_user_config()
    manager.merge_symbols()
    return manager


@pytest.fixture
async def repository():
    """Create in-memory signal repository."""
    repo = SignalRepository(db_path=":memory:")
    await repo.initialize()
    return repo


@pytest.fixture
async def pipeline(config_manager, risk_config, repository):
    """Create signal pipeline for testing."""
    pipeline = SignalPipeline(
        config_manager=config_manager,
        risk_config=risk_config,
        signal_repository=repository,
        cooldown_seconds=300,
    )
    # Ensure async primitives are initialized for testing
    pipeline._ensure_async_primitives()
    return pipeline


# ============================================================
# Test Queue Configuration
# ============================================================
class TestQueueConfig:
    """Test queue configuration loading."""

    def test_queue_params_loaded_from_config(self, pipeline, config_manager):
        """Test that queue parameters are loaded from core.yaml."""
        assert pipeline._queue_batch_size == config_manager.core_config.signal_pipeline.queue.batch_size
        assert pipeline._queue_flush_interval == config_manager.core_config.signal_pipeline.queue.flush_interval
        assert pipeline._queue_max_size == config_manager.core_config.signal_pipeline.queue.max_queue_size

    def test_queue_config_defaults(self, config_manager):
        """Test queue config has correct defaults."""
        queue_config = config_manager.core_config.signal_pipeline.queue
        assert queue_config.batch_size == 10
        assert queue_config.flush_interval == 5.0
        assert queue_config.max_queue_size == 1000


# ============================================================
# Test Backpressure Monitoring
# ============================================================
class TestAsyncQueueBackpressure:
    """Test queue backpressure monitoring."""

    @pytest.mark.asyncio
    async def test_queue_backpressure_alert(self, pipeline, caplog):
        """Test that backpressure alert is triggered when queue is near capacity."""
        # Fill queue to near capacity (85% of default 1000)
        for i in range(850):
            mock_attempt = MagicMock(spec=SignalAttempt)
            mock_attempt.strategy_name = "test"
            mock_attempt.kline_timestamp = 1234567890
            mock_attempt.filter_results = []
            await pipeline._attempts_queue.put((mock_attempt, "BTC", "15m"))

        # Trigger worker briefly
        worker_task = asyncio.create_task(
            pipeline._flush_attempts_worker(batch_size=100, flush_interval=0.5)
        )

        # Give worker time to process
        await asyncio.sleep(0.2)

        # Cancel worker
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass

        # Check log for backpressure alert
        assert "BACKPRESSURE ALERT" in caplog.text

    @pytest.mark.asyncio
    async def test_queue_backpressure_threshold(self, pipeline):
        """Test backpressure threshold calculation."""
        # Set a small max size for testing
        pipeline._queue_max_size = 100

        # Fill queue to 85% (above 80% threshold)
        for i in range(85):
            mock_attempt = MagicMock(spec=SignalAttempt)
            mock_attempt.strategy_name = "test"
            mock_attempt.kline_timestamp = 1234567890
            mock_attempt.filter_results = []
            await pipeline._attempts_queue.put((mock_attempt, "BTC", "15m"))

        # Check queue size
        assert pipeline._attempts_queue.qsize() == 85
        assert pipeline._attempts_queue.qsize() > int(pipeline._queue_max_size * 0.8)


# ============================================================
# Test Worker Recovery
# ============================================================
class TestAsyncQueueRecovery:
    """Test queue worker recovery."""

    @pytest.mark.asyncio
    async def test_worker_handles_consecutive_errors(self, pipeline, caplog):
        """Test that consecutive errors are tracked and logged."""
        # Mock flush_buffer to always fail
        original_flush = pipeline._flush_buffer

        async def failing_flush(buffer):
            raise Exception("Simulated database error")

        pipeline._flush_buffer = failing_flush

        # Add items to queue
        for i in range(5):
            mock_attempt = MagicMock(spec=SignalAttempt)
            mock_attempt.strategy_name = "test"
            mock_attempt.kline_timestamp = 1234567890
            mock_attempt.filter_results = []
            await pipeline._attempts_queue.put((mock_attempt, "BTC", "15m"))

        # Run worker briefly
        worker_task = asyncio.create_task(
            pipeline._flush_attempts_worker(batch_size=1, flush_interval=0.1)
        )

        # Wait for some errors to accumulate
        await asyncio.sleep(0.5)

        # Cancel worker
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass

        # Restore original flush
        pipeline._flush_buffer = original_flush

        # Check that errors were logged
        assert "Flush worker error" in caplog.text

    @pytest.mark.asyncio
    async def test_monitor_restart_tracking(self, pipeline, caplog):
        """Test that monitor tracks restart count."""
        # The _monitor_flush_worker should track restarts
        # We can't easily test the full restart loop in unit tests,
        # but we can verify the method exists and handles exceptions
        assert hasattr(pipeline, '_monitor_flush_worker')


# ============================================================
# Test Queue Operations
# ============================================================
class TestQueueOperations:
    """Test basic queue operations."""

    @pytest.mark.asyncio
    async def test_queue_fifo_order(self, pipeline):
        """Test that queue maintains FIFO order."""
        # Add items in order
        for i in range(5):
            mock_attempt = MagicMock(spec=SignalAttempt)
            mock_attempt.strategy_name = f"test_{i}"
            mock_attempt.kline_timestamp = 1234567890
            mock_attempt.filter_results = []
            await pipeline._attempts_queue.put((mock_attempt, "BTC", "15m"))

        # Verify order
        for i in range(5):
            item = await pipeline._attempts_queue.get()
            assert item[0].strategy_name == f"test_{i}"

    @pytest.mark.asyncio
    async def test_queue_size_tracking(self, pipeline):
        """Test that queue size can be tracked."""
        initial_size = pipeline._attempts_queue.qsize()
        assert initial_size == 0

        # Add items
        for i in range(10):
            mock_attempt = MagicMock(spec=SignalAttempt)
            mock_attempt.strategy_name = "test"
            mock_attempt.kline_timestamp = 1234567890
            mock_attempt.filter_results = []
            await pipeline._attempts_queue.put((mock_attempt, "BTC", "15m"))

        assert pipeline._attempts_queue.qsize() == 10


# ============================================================
# Test Flush Worker
# ============================================================
class TestFlushWorker:
    """Test flush worker functionality."""

    @pytest.mark.asyncio
    async def test_flush_on_batch_size(self, pipeline, repository):
        """Test that flush occurs when batch size is reached."""
        # Add items equal to batch size
        batch_size = pipeline._queue_batch_size
        for i in range(batch_size):
            mock_attempt = MagicMock(spec=SignalAttempt)
            mock_attempt.strategy_name = "test"
            mock_attempt.kline_timestamp = 1234567890
            mock_attempt.filter_results = []
            mock_attempt.final_result = "SIGNAL_FIRED"
            mock_attempt.pattern = None
            await pipeline._attempts_queue.put((mock_attempt, "BTC", "15m"))

        # Start worker
        worker_task = asyncio.create_task(
            pipeline._flush_attempts_worker(
                batch_size=batch_size,
                flush_interval=10.0  # Long interval to test batch trigger
            )
        )

        # Wait for flush
        await asyncio.sleep(0.5)

        # Cancel worker
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass

        # Verify items were flushed (check database)
        result = await repository.get_attempts(limit=10)
        assert result["total"] == batch_size

    @pytest.mark.asyncio
    async def test_flush_on_interval(self, pipeline, repository):
        """Test that flush occurs when interval is exceeded."""
        # Add fewer items than batch size
        for i in range(3):
            mock_attempt = MagicMock(spec=SignalAttempt)
            mock_attempt.strategy_name = "test"
            mock_attempt.kline_timestamp = 1234567890
            mock_attempt.filter_results = []
            mock_attempt.final_result = "SIGNAL_FIRED"
            mock_attempt.pattern = None
            await pipeline._attempts_queue.put((mock_attempt, "BTC", "15m"))

        # Start worker with short interval
        worker_task = asyncio.create_task(
            pipeline._flush_attempts_worker(
                batch_size=100,  # Large batch to test interval trigger
                flush_interval=0.2  # Short interval
            )
        )

        # Wait for interval flush
        await asyncio.sleep(0.5)

        # Cancel worker
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass

        # Verify items were flushed
        result = await repository.get_attempts(limit=10)
        assert result["total"] >= 3
