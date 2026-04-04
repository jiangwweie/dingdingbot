"""
Unit tests for database-driven ConfigManager.

Tests cover:
- Database initialization
- Configuration loading/saving
- Hot-reload observer pattern
- Auto-snapshot integration
- YAML backward compatibility
"""
import asyncio
import os
import pytest
from decimal import Decimal
from pathlib import Path
from typing import Dict, Any
import tempfile
import shutil

from src.application.config_manager_db import (
    ConfigManager,
    load_all_configs_async,
    CoreConfig,
    UserConfig,
    ExchangeConfig,
    NotificationConfig,
    NotificationChannel,
)
from src.domain.models import RiskConfig, StrategyDefinition, TriggerConfig, FilterConfig


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def temp_db_path():
    """Create a temporary database path for testing."""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_config.db")
    yield db_path
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
async def config_manager(temp_db_path):
    """Create initialized ConfigManager for testing."""
    manager = ConfigManager(db_path=temp_db_path)
    await manager.initialize_from_db()
    yield manager
    await manager.close()


# ============================================================
# Database Initialization Tests
# ============================================================

class TestDatabaseInitialization:
    """Test database initialization."""

    @pytest.mark.asyncio
    async def test_initialize_from_db(self, temp_db_path):
        """Test database initialization creates tables and default configs."""
        manager = ConfigManager(db_path=temp_db_path)
        await manager.initialize_from_db()

        # Verify database file exists
        assert os.path.exists(temp_db_path)

        # Verify tables exist
        async with manager._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ) as cursor:
            tables = await cursor.fetchall()
            table_names = [t[0] for t in tables]

            assert "system_configs" in table_names
            assert "risk_configs" in table_names
            assert "strategies" in table_names
            assert "symbols" in table_names
            assert "notifications" in table_names
            assert "config_snapshots" in table_names
            assert "config_history" in table_names

        await manager.close()

    @pytest.mark.asyncio
    async def test_initialize_is_idempotent(self, temp_db_path):
        """Test initialization can be called multiple times safely."""
        manager = ConfigManager(db_path=temp_db_path)

        # Initialize twice
        await manager.initialize_from_db()
        await manager.initialize_from_db()

        # Should still work
        core_config = manager.get_core_config()
        assert core_config is not None

        await manager.close()

    @pytest.mark.asyncio
    async def test_default_system_config(self, config_manager):
        """Test default system config is created."""
        core_config = config_manager.get_core_config()

        assert len(core_config.core_symbols) >= 4
        assert "BTC/USDT:USDT" in core_config.core_symbols
        assert core_config.ema.period == 60
        assert core_config.mtf_ema_period == 60

    @pytest.mark.asyncio
    async def test_default_risk_config(self, config_manager):
        """Test default risk config is created."""
        user_config = await config_manager.get_user_config()

        assert user_config.risk.max_loss_percent == Decimal("0.01")
        assert user_config.risk.max_leverage == 10
        assert user_config.risk.max_total_exposure == Decimal("0.8")

    @pytest.mark.asyncio
    async def test_core_symbols_initialized(self, config_manager):
        """Test core symbols are initialized."""
        async with config_manager._db.execute(
            "SELECT symbol FROM symbols WHERE is_core = TRUE"
        ) as cursor:
            rows = await cursor.fetchall()
            symbols = [r[0] for r in rows]

            assert "BTC/USDT:USDT" in symbols
            assert "ETH/USDT:USDT" in symbols
            assert "SOL/USDT:USDT" in symbols
            assert "BNB/USDT:USDT" in symbols


# ============================================================
# Configuration Loading Tests
# ============================================================

class TestConfigurationLoading:
    """Test configuration loading from database."""

    @pytest.mark.asyncio
    async def test_get_core_config(self, config_manager):
        """Test loading core config."""
        core_config = config_manager.get_core_config()

        assert isinstance(core_config, CoreConfig)
        assert len(core_config.core_symbols) > 0
        assert core_config.ema.period > 0

    @pytest.mark.asyncio
    async def test_get_user_config(self, config_manager):
        """Test loading user config."""
        user_config = await config_manager.get_user_config()

        assert isinstance(user_config, UserConfig)
        assert user_config.exchange is not None
        assert user_config.risk is not None
        assert user_config.notification is not None

    @pytest.mark.asyncio
    async def test_get_core_config_async(self, config_manager):
        """Test async core config loading."""
        core_config = await config_manager.get_core_config_async()

        assert isinstance(core_config, CoreConfig)
        assert "BTC/USDT:USDT" in core_config.core_symbols


# ============================================================
# Risk Config Update Tests
# ============================================================

class TestRiskConfigUpdate:
    """Test risk configuration updates."""

    @pytest.mark.asyncio
    async def test_update_risk_config(self, config_manager):
        """Test updating risk config."""
        new_risk = RiskConfig(
            max_loss_percent=Decimal("0.02"),  # 2%
            max_leverage=20,
            max_total_exposure=Decimal("0.9"),
        )

        await config_manager.update_risk_config(new_risk, changed_by="test")

        # Verify update
        user_config = await config_manager.get_user_config()
        assert user_config.risk.max_loss_percent == Decimal("0.02")
        assert user_config.risk.max_leverage == 20
        assert user_config.risk.max_total_exposure == Decimal("0.9")

    @pytest.mark.asyncio
    async def test_update_risk_config_logs_history(self, config_manager):
        """Test risk config update creates history record."""
        new_risk = RiskConfig(
            max_loss_percent=Decimal("0.015"),
            max_leverage=15,
            max_total_exposure=Decimal("0.85"),
        )

        await config_manager.update_risk_config(new_risk, changed_by="test_user")

        # Check history
        async with config_manager._db.execute(
            "SELECT * FROM config_history WHERE entity_type = 'risk_config' ORDER BY changed_at DESC LIMIT 1"
        ) as cursor:
            row = await cursor.fetchone()
            assert row is not None
            assert row["entity_id"] == "global"
            assert row["action"] == "UPDATE"
            assert row["changed_by"] == "test_user"


# ============================================================
# Strategy Management Tests
# ============================================================

class TestStrategyManagement:
    """Test strategy CRUD operations."""

    @pytest.mark.asyncio
    async def test_save_strategy(self, config_manager):
        """Test saving a new strategy."""
        strategy = StrategyDefinition(
            name="test_pinbar",
            trigger=TriggerConfig(
                type="pinbar",
                enabled=True,
                params={"min_wick_ratio": 0.6},
            ),
            filters=[
                FilterConfig(
                    type="ema",
                    enabled=True,
                    params={"period": 60},
                )
            ],
            filter_logic="AND",
        )

        strategy_id = await config_manager.save_strategy(strategy, changed_by="test")

        assert strategy_id is not None

        # Verify strategy was saved
        async with config_manager._db.execute(
            "SELECT * FROM strategies WHERE id = ?", (strategy_id,)
        ) as cursor:
            row = await cursor.fetchone()
            assert row is not None
            assert row["name"] == "test_pinbar"

    @pytest.mark.asyncio
    async def test_delete_strategy(self, config_manager):
        """Test deleting a strategy."""
        # First create a strategy
        strategy = StrategyDefinition(
            name="to_delete",
            trigger=TriggerConfig(type="pinbar", enabled=True, params={}),
            filters=[],
        )
        strategy_id = await config_manager.save_strategy(strategy)

        # Delete it
        result = await config_manager.delete_strategy(strategy_id)
        assert result is True

        # Verify deletion
        async with config_manager._db.execute(
            "SELECT * FROM strategies WHERE id = ?", (strategy_id,)
        ) as cursor:
            row = await cursor.fetchone()
            assert row is None

    @pytest.mark.asyncio
    async def test_load_strategies(self, config_manager):
        """Test loading strategies from database."""
        # Create test strategies
        strategy1 = StrategyDefinition(
            name="strategy_1",
            trigger=TriggerConfig(type="pinbar", enabled=True, params={}),
            filters=[],
        )
        strategy2 = StrategyDefinition(
            name="strategy_2",
            trigger=TriggerConfig(type="engulfing", enabled=True, params={}),
            filters=[FilterConfig(type="mtf", enabled=True, params={})],
        )

        await config_manager.save_strategy(strategy1)
        await config_manager.save_strategy(strategy2)

        # Load and verify
        user_config = await config_manager.get_user_config()
        assert len(user_config.active_strategies) >= 2


# ============================================================
# Observer Pattern Tests
# ============================================================

class TestObserverPattern:
    """Test hot-reload observer pattern."""

    @pytest.mark.asyncio
    async def test_add_observer(self, config_manager):
        """Test adding an observer."""
        called = False

        async def observer():
            nonlocal called
            called = True

        config_manager.add_observer(observer)

        # Trigger update
        new_risk = RiskConfig(
            max_loss_percent=Decimal("0.01"),
            max_leverage=10,
            max_total_exposure=Decimal("0.8"),
        )
        await config_manager.update_risk_config(new_risk)

        # Verify observer was called
        assert called is True

    @pytest.mark.asyncio
    async def test_remove_observer(self, config_manager):
        """Test removing an observer."""
        called = False

        async def observer():
            nonlocal called
            called = True

        config_manager.add_observer(observer)
        config_manager.remove_observer(observer)

        # Trigger update
        new_risk = RiskConfig(
            max_loss_percent=Decimal("0.01"),
            max_leverage=10,
            max_total_exposure=Decimal("0.8"),
        )
        await config_manager.update_risk_config(new_risk)

        # Wait a bit for async execution
        await asyncio.sleep(0.1)

        # Verify observer was NOT called
        assert called is False

    @pytest.mark.asyncio
    async def test_observer_failure_does_not_block(self, config_manager):
        """Test that observer failure doesn't block config update."""
        async def failing_observer():
            raise Exception("Observer failed!")

        config_manager.add_observer(failing_observer)

        # This should not raise
        new_risk = RiskConfig(
            max_loss_percent=Decimal("0.01"),
            max_leverage=10,
            max_total_exposure=Decimal("0.8"),
        )
        await config_manager.update_risk_config(new_risk)

        # Config should still be updated
        user_config = await config_manager.get_user_config()
        assert user_config.risk.max_loss_percent == Decimal("0.01")


# ============================================================
# YAML Backward Compatibility Tests
# ============================================================

class TestYamlBackwardCompatibility:
    """Test YAML backward compatibility."""

    @pytest.fixture
    def yaml_config_dir(self):
        """Create temporary YAML config directory."""
        temp_dir = tempfile.mkdtemp()

        # Create core.yaml
        core_yaml = """
core_symbols:
  - BTC/USDT:USDT
  - ETH/USDT:USDT
pinbar_defaults:
  min_wick_ratio: 0.6
  max_body_ratio: 0.3
  body_position_tolerance: 0.1
ema:
  period: 60
mtf_mapping:
  15m: 1h
  1h: 4h
mtf_ema_period: 60
warmup:
  history_bars: 100
signal_pipeline:
  cooldown_seconds: 14400
"""
        with open(os.path.join(temp_dir, "core.yaml"), "w") as f:
            f.write(core_yaml)

        # Create user.yaml
        user_yaml = """
exchange:
  name: binance
  api_key: test_api_key
  api_secret: test_api_secret
  testnet: true
user_symbols: []
timeframes:
  - 15m
  - 1h
risk:
  max_loss_percent: 0.01
  max_leverage: 10
  max_total_exposure: 0.8
asset_polling:
  interval_seconds: 60
notification:
  channels:
    - type: feishu
      webhook_url: https://test.feishu.cn/webhook
"""
        with open(os.path.join(temp_dir, "user.yaml"), "w") as f:
            f.write(user_yaml)

        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_load_from_yaml_fallback(self, yaml_config_dir):
        """Test loading config from YAML when DB not initialized."""
        manager = ConfigManager(config_dir=yaml_config_dir)
        # Don't initialize from DB

        # Should load from YAML
        core_config = manager.get_core_config()
        assert core_config.ema.period == 60
        assert "BTC/USDT:USDT" in core_config.core_symbols

    @pytest.mark.asyncio
    async def test_yaml_fallback_when_db_not_initialized(self, yaml_config_dir):
        """Test YAML fallback when database is not initialized."""
        manager = ConfigManager(config_dir=yaml_config_dir)

        # Get config without DB initialization
        core_config = manager.get_core_config()
        assert isinstance(core_config, CoreConfig)


# ============================================================
# Convenience Function Tests
# ============================================================

class TestConvenienceFunctions:
    """Test convenience functions."""

    @pytest.mark.asyncio
    async def test_load_all_configs_async(self, temp_db_path):
        """Test async config loader."""
        manager = await load_all_configs_async(db_path=temp_db_path)

        try:
            core_config = manager.get_core_config()
            assert core_config is not None
            assert "BTC/USDT:USDT" in core_config.core_symbols
        finally:
            await manager.close()


# ============================================================
# Entry Point
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=src/application/config_manager_db"])
