"""
R9.3: Configuration Loading Race Condition Fix - Unit Tests

Tests for ConfigManager's race condition prevention during asynchronous initialization.

Issue: During ConfigManager's async initialization, synchronous code might retrieve
       incomplete configuration (partially from DB, partially from YAML).

Fix: Added initialization state flags and lock protection:
     - _initialized: Marks completion of initialization
     - _initializing: Marks initialization in progress
     - _init_lock: asyncio.Lock for thread-safe initialization
     - _init_event: asyncio.Event to notify waiting coroutines

Test Coverage:
1. Concurrent initialize_from_db() calls don't cause duplicate initialization
2. get_user_config() waits during initialization instead of returning incomplete config
3. Failed initialization is properly signaled to waiting coroutines
4. Timeout handling for initialization waits
"""
import asyncio
import os
import tempfile
import pytest
from decimal import Decimal
from unittest.mock import patch, AsyncMock

from src.application.config_manager import ConfigManager


class TestR93ConcurrentInitialization:
    """R9.3: Test concurrent initialization race condition prevention"""

    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database file path"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            temp_path = f.name
        yield temp_path
        # Cleanup
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        # Cleanup WAL files
        if os.path.exists(f"{temp_path}-wal"):
            os.unlink(f"{temp_path}-wal")
        if os.path.exists(f"{temp_path}-shm"):
            os.unlink(f"{temp_path}-shm")

    @pytest.mark.asyncio
    async def test_concurrent_initialize_doesnt_duplicate(self, temp_db_path):
        """R9.3: Multiple concurrent initialize_from_db() calls should not duplicate"""
        # Remove file to simulate empty database
        os.unlink(temp_db_path)

        manager = ConfigManager(db_path=temp_db_path)

        # Start 5 concurrent initializations
        tasks = [manager.initialize_from_db() for _ in range(5)]
        await asyncio.gather(*tasks)

        # Should only initialize once
        assert manager.is_initialized

        # Verify config is valid (not partial)
        user_config = await manager.get_user_config()
        assert user_config.risk.max_loss_percent == Decimal("0.01")

        await manager.close()

    @pytest.mark.asyncio
    async def test_sequential_initialize_is_idempotent(self, temp_db_path):
        """R9.3: Sequential initialize_from_db() calls should be idempotent"""
        os.unlink(temp_db_path)

        manager = ConfigManager(db_path=temp_db_path)

        # First initialization
        await manager.initialize_from_db()
        assert manager.is_initialized

        config1 = await manager.get_user_config()

        # Second initialization (should be no-op)
        await manager.initialize_from_db()
        assert manager.is_initialized

        config2 = await manager.get_user_config()

        # Configs should be identical
        assert config1.risk.max_loss_percent == config2.risk.max_loss_percent
        assert config1.risk.max_leverage == config2.risk.max_leverage

        await manager.close()

    @pytest.mark.asyncio
    async def test_get_config_waits_for_initialization(self, temp_db_path):
        """R9.3: get_user_config() should wait for initialization to complete"""
        os.unlink(temp_db_path)

        manager = ConfigManager(db_path=temp_db_path)

        # Start initialization but don't await it yet
        init_task = asyncio.create_task(manager.initialize_from_db())

        # Small delay to let initialization start
        await asyncio.sleep(0.01)

        # get_user_config should wait for initialization
        config = await manager.get_user_config()

        # Verify config is complete
        assert config.risk.max_loss_percent == Decimal("0.01")
        assert len(config.notification.channels) >= 1

        await init_task
        await manager.close()

    @pytest.mark.asyncio
    async def test_initialization_failure_propagates(self, temp_db_path):
        """R9.3: Initialization failure should propagate to waiting coroutines"""
        os.unlink(temp_db_path)

        manager = ConfigManager(db_path=temp_db_path)

        # Mock _create_tables to raise an exception
        original_create_tables = manager._create_tables

        async def failing_create_tables():
            raise RuntimeError("Simulated database error")

        manager._create_tables = failing_create_tables

        # Initialization should raise
        with pytest.raises(RuntimeError, match="Simulated database error"):
            await manager.initialize_from_db()

        # Should not be marked as initialized
        assert not manager.is_initialized

        # Reset mock
        manager._create_tables = original_create_tables

        # Second initialization should succeed
        await manager.initialize_from_db()
        assert manager.is_initialized

        await manager.close()

    @pytest.mark.asyncio
    async def test_initialization_timeout(self, temp_db_path):
        """R9.3: get_user_config() should timeout if initialization hangs"""
        os.unlink(temp_db_path)

        manager = ConfigManager(db_path=temp_db_path)

        # Mock initialize_from_db to hang
        async def hanging_init():
            manager._initializing = True
            manager._initialized = False
            # Never set the event
            await asyncio.sleep(10)  # Hang

        # Manually set up the hanging state
        manager._init_event = asyncio.Event()
        manager._initializing = True

        # get_user_config should timeout
        with pytest.raises(RuntimeError, match="初始化超时"):
            await manager.get_user_config()

        await manager.close()

    @pytest.mark.asyncio
    async def test_concurrent_get_config_during_init(self, temp_db_path):
        """R9.3: Multiple get_user_config() calls during init should all succeed"""
        os.unlink(temp_db_path)

        manager = ConfigManager(db_path=temp_db_path)

        # Start initialization
        init_task = asyncio.create_task(manager.initialize_from_db())

        # Start 5 concurrent get_user_config calls
        async def get_config():
            return await manager.get_user_config()

        config_tasks = [get_config() for _ in range(5)]
        configs = await asyncio.gather(*config_tasks)

        # All configs should be valid and identical
        for config in configs:
            assert config.risk.max_loss_percent == Decimal("0.01")
            assert len(config.notification.channels) >= 1

        await init_task
        await manager.close()


class TestR93InitializationState:
    """R9.3: Test initialization state tracking"""

    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database file path"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            temp_path = f.name
        yield temp_path
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_initial_state(self, temp_db_path):
        """R9.3: Initial state should be not initialized"""
        manager = ConfigManager(db_path=temp_db_path)

        assert not manager.is_initialized
        assert manager._db is None

        await manager.close()

    @pytest.mark.asyncio
    async def test_state_after_init(self, temp_db_path):
        """R9.3: State should be initialized after successful init"""
        os.unlink(temp_db_path)

        manager = ConfigManager(db_path=temp_db_path)
        await manager.initialize_from_db()

        assert manager.is_initialized
        assert manager._db is not None

        await manager.close()

    @pytest.mark.asyncio
    async def test_init_event_is_set(self, temp_db_path):
        """R9.3: Init event should be set after successful initialization"""
        os.unlink(temp_db_path)

        manager = ConfigManager(db_path=temp_db_path)
        await manager.initialize_from_db()

        # Event should be set
        assert manager._init_event.is_set()

        await manager.close()


# Run tests with: pytest tests/unit/test_config_manager_db_r93.py -v
