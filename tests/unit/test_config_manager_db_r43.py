"""
R4.3: Empty Database Startup Fix - Unit Tests

Tests for ConfigManager's ability to start with empty database
by applying hard-coded default configurations.

Issue: When database tables are empty, UserConfig required fields are missing,
       causing Pydantic validation failure and system crash.

Fix: Added _validate_and_apply_default_configs() method that:
     1. Detects empty/incomplete database configuration
     2. Logs WARNING message to inform user
     3. Inserts hard-coded default configurations
     4. Ensures system can start safely
"""
import asyncio
import os
import tempfile
import pytest
from decimal import Decimal

from src.application.config_manager_db import ConfigManager


class TestR43EmptyDatabaseStartup:
    """R4.3: Test empty database startup with default configuration fallback"""

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
    async def test_empty_db_creates_default_configs(self, temp_db_path):
        """R4.3: Empty database should create default configurations"""
        # Remove file to simulate empty database
        os.unlink(temp_db_path)

        manager = ConfigManager(db_path=temp_db_path)
        await manager.initialize_from_db()

        # Verify core config
        core_config = manager.get_core_config()
        assert len(core_config.core_symbols) >= 4
        assert "BTC/USDT:USDT" in core_config.core_symbols

        # Verify user config
        user_config = await manager.get_user_config()
        assert user_config.timeframes is not None
        assert len(user_config.timeframes) > 0
        assert user_config.risk.max_loss_percent == Decimal("0.01")
        assert len(user_config.notification.channels) >= 1

        await manager.close()

    @pytest.mark.asyncio
    async def test_empty_db_logs_warning(self, temp_db_path, caplog):
        """R4.3: Empty database should log WARNING message"""
        import logging
        logging.getLogger().setLevel(logging.DEBUG)

        # Remove file to simulate empty database
        os.unlink(temp_db_path)

        manager = ConfigManager(db_path=temp_db_path)
        await manager.initialize_from_db()

        # Verify warning log
        assert "数据库配置为空或不完全" in caplog.text

        await manager.close()

    @pytest.mark.asyncio
    async def test_default_risk_config_values(self, temp_db_path):
        """R4.3: Verify default risk config values"""
        os.unlink(temp_db_path)

        manager = ConfigManager(db_path=temp_db_path)
        await manager.initialize_from_db()

        user_config = await manager.get_user_config()

        # Verify risk config
        assert user_config.risk.max_loss_percent == Decimal("0.01")
        assert user_config.risk.max_leverage == 10
        assert user_config.risk.max_total_exposure == Decimal("0.8")

        await manager.close()

    @pytest.mark.asyncio
    async def test_default_notification_config(self, temp_db_path):
        """R4.3: Verify default notification config"""
        os.unlink(temp_db_path)

        manager = ConfigManager(db_path=temp_db_path)
        await manager.initialize_from_db()

        user_config = await manager.get_user_config()

        # Verify notification config exists
        assert len(user_config.notification.channels) >= 1
        channel = user_config.notification.channels[0]
        assert channel.type in ("feishu", "wecom")
        assert channel.webhook_url.startswith("https://")

        await manager.close()

    @pytest.mark.asyncio
    async def test_default_system_config(self, temp_db_path):
        """R4.3: Verify default system config values"""
        os.unlink(temp_db_path)

        manager = ConfigManager(db_path=temp_db_path)
        await manager.initialize_from_db()

        core_config = manager.get_core_config()

        # Verify core symbols
        assert "BTC/USDT:USDT" in core_config.core_symbols
        assert "ETH/USDT:USDT" in core_config.core_symbols
        assert "SOL/USDT:USDT" in core_config.core_symbols
        assert "BNB/USDT:USDT" in core_config.core_symbols

        # Verify MTF mapping
        assert core_config.mtf_ema_period == 60

        await manager.close()

    @pytest.mark.asyncio
    async def test_idempotent_initialization(self, temp_db_path):
        """R4.3: Multiple initialize_from_db() calls should be idempotent"""
        os.unlink(temp_db_path)

        manager = ConfigManager(db_path=temp_db_path)

        # First initialization
        await manager.initialize_from_db()
        config1 = await manager.get_user_config()

        # Second initialization (should be no-op)
        await manager.initialize_from_db()
        config2 = await manager.get_user_config()

        # Configs should be identical
        assert config1.risk.max_loss_percent == config2.risk.max_loss_percent
        assert len(config1.notification.channels) == len(config2.notification.channels)

        await manager.close()

    @pytest.mark.asyncio
    async def test_user_config_validation_fallback(self, temp_db_path):
        """R4.3: ValidationError should trigger default config fallback"""
        from pydantic import ValidationError

        os.unlink(temp_db_path)

        manager = ConfigManager(db_path=temp_db_path)
        await manager.initialize_from_db()

        # get_user_config should never raise ValidationError
        # because _create_default_user_config() is the fallback
        user_config = await manager.get_user_config()
        assert user_config is not None
        assert isinstance(user_config.exchange.api_key, str)

        await manager.close()


class TestR43ConfigurationIntegrity:
    """R4.3: Test configuration integrity checks"""

    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database file path"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            temp_path = f.name
        yield temp_path
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_is_empty_config_with_no_data(self, temp_db_path):
        """R4.3: _is_empty_config returns True for empty database"""
        os.unlink(temp_db_path)

        manager = ConfigManager(db_path=temp_db_path)
        await manager.initialize_from_db()

        # After initialization, config should NOT be empty
        # (because _initialize_default_configs creates them)
        is_empty = await manager._is_empty_config()
        assert is_empty == False

        await manager.close()

    @pytest.mark.asyncio
    async def test_apply_hardcoded_defaults(self, temp_db_path):
        """R4.3: _apply_hardcoded_defaults inserts minimum configs"""
        os.unlink(temp_db_path)

        manager = ConfigManager(db_path=temp_db_path)
        await manager.initialize_from_db()

        # Verify _apply_hardcoded_defaults was called indirectly
        # by checking configs exist
        user_config = await manager.get_user_config()
        assert user_config.risk is not None
        assert user_config.notification is not None

        await manager.close()


# Run tests with: pytest tests/unit/test_config_manager_db_r43.py -v
