"""
R7.1: Startup Order Dependency Check - Unit Tests

Tests for ConfigManager's initialization state tracking and dependency checks.

Issue: ConfigManager must be initialized before other modules use it,
       but there's no explicit dependency declaration or check.

Fix: Added initialization state flags and assert_initialized() method:
     - _initialized: Marks completion of initialization
     - _initializing: Marks initialization in progress
     - assert_initialized(): Raises DependencyNotReadyError if not ready

Test Coverage:
1. assert_initialized() passes after successful initialization
2. assert_initialized() raises error when not initialized
3. assert_initialized() raises error when still initializing
4. Error messages are clear and actionable
"""
import asyncio
import os
import tempfile
import pytest
from pathlib import Path

from src.application.config_manager_db import ConfigManager
from src.domain.exceptions import DependencyNotReadyError


class TestR71InitializationCheck:
    """R7.1: Test startup order dependency checks"""

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
    async def test_assert_initialized_passes_after_init(self, temp_db_path):
        """R7.1: assert_initialized() should pass after successful initialization"""
        os.unlink(temp_db_path)

        manager = ConfigManager(db_path=temp_db_path)
        await manager.initialize_from_db()

        # Should not raise
        manager.assert_initialized()

        await manager.close()

    @pytest.mark.asyncio
    async def test_assert_initialized_raises_when_not_initialized(self, temp_db_path):
        """R7.1: assert_initialized() should raise when not initialized"""
        os.unlink(temp_db_path)

        manager = ConfigManager(db_path=temp_db_path)
        # Don't initialize

        with pytest.raises(DependencyNotReadyError) as exc_info:
            manager.assert_initialized()

        assert exc_info.value.error_code == "F-003"
        assert "ConfigManager 未初始化" in str(exc_info.value)
        assert "initialize_from_db()" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_assert_initialized_raises_when_initializing(self, temp_db_path):
        """R7.1: assert_initialized() should raise when still initializing"""
        os.unlink(temp_db_path)

        manager = ConfigManager(db_path=temp_db_path)

        # Manually set initializing state (simulating concurrent initialization)
        manager._initializing = True
        manager._initialized = False

        with pytest.raises(DependencyNotReadyError) as exc_info:
            manager.assert_initialized()

        assert exc_info.value.error_code == "F-003"
        assert "正在初始化中" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_error_message_is_actionable(self, temp_db_path):
        """R7.1: Error message should provide clear guidance"""
        os.unlink(temp_db_path)

        manager = ConfigManager(db_path=temp_db_path)

        with pytest.raises(DependencyNotReadyError) as exc_info:
            manager.assert_initialized()

        error_message = str(exc_info.value)
        # Message should mention the fix
        assert "main.py" in error_message
        assert "initialize_from_db()" in error_message

    @pytest.mark.asyncio
    async def test_double_init_is_idempotent(self, temp_db_path):
        """R7.1: Calling initialize_from_db twice should be safe"""
        os.unlink(temp_db_path)

        manager = ConfigManager(db_path=temp_db_path)

        # First initialization
        await manager.initialize_from_db()
        assert manager._initialized

        # Second initialization should be no-op
        await manager.initialize_from_db()
        assert manager._initialized

        # assert_initialized should still pass
        manager.assert_initialized()

        await manager.close()


class TestR71DependencyPattern:
    """R7.1: Test dependency check pattern in real-world scenario"""

    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database file path"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            temp_path = f.name
        yield temp_path
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        if os.path.exists(f"{temp_path}-wal"):
            os.unlink(f"{temp_path}-wal")
        if os.path.exists(f"{temp_path}-shm"):
            os.unlink(f"{temp_path}-shm")

    @pytest.mark.asyncio
    async def test_module_can_safely_use_config_after_init(self, temp_db_path):
        """R7.1: Module can safely use config after initialization check"""
        os.unlink(temp_db_path)

        manager = ConfigManager(db_path=temp_db_path)
        await manager.initialize_from_db()

        # Simulate a module that depends on ConfigManager
        class DependentModule:
            def __init__(self, config_manager: ConfigManager):
                self.config_manager = config_manager
                # Check dependency before using
                self.config_manager.assert_initialized()

            def get_config(self):
                return self.config_manager.get_core_config()

        module = DependentModule(manager)
        config = module.get_config()

        assert config is not None
        assert len(config.core_symbols) > 0

        await manager.close()

    @pytest.mark.asyncio
    async def test_module_fails_gracefully_without_init(self, temp_db_path):
        """R7.1: Module fails gracefully with clear error if not initialized"""
        os.unlink(temp_db_path)

        manager = ConfigManager(db_path=temp_db_path)
        # Don't initialize

        # Simulate a module that depends on ConfigManager
        class DependentModule:
            def __init__(self, config_manager: ConfigManager):
                self.config_manager = config_manager
                # Check dependency before using - this should raise
                self.config_manager.assert_initialized()

        with pytest.raises(DependencyNotReadyError) as exc_info:
            DependentModule(manager)

        assert exc_info.value.error_code == "F-003"


# Run tests with: pytest tests/unit/test_config_manager_r71.py -v
