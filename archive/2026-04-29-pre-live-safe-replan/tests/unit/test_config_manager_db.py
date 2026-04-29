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

from src.application.config_manager import (
    ConfigManager,
    load_all_configs_async,
    CoreConfig,
    UserConfig,
    ExchangeConfig,
    NotificationConfig,
    NotificationChannel,
)
from src.domain.models import RiskConfig, StrategyDefinition, TriggerConfig, FilterConfig


@pytest.fixture
def yaml_config_dir():
    """Create temporary YAML config directory for testing."""
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
# Extended Field Parsing Tests (TASK-2)
# ============================================================

class TestRiskConfigExtendedFields:
    """Test RiskConfig extended optional fields parsing."""

    @pytest.mark.asyncio
    async def test_risk_config_with_extended_fields(self, temp_db_path):
        """Test loading RiskConfig with all extended fields from database."""
        manager = ConfigManager(db_path=temp_db_path)
        await manager.initialize_from_db()

        # Update risk config with extended fields
        async with manager._db.execute("""
            UPDATE risk_configs
            SET daily_max_trades = ?,
                daily_max_loss = ?,
                max_position_hold_time = ?,
                updated_at = datetime('now')
            WHERE id = 'global'
        """, (100, "0.05", 480)) as cursor:
            await manager._db.commit()

        # Load and verify
        user_config = await manager.get_user_config()

        assert user_config.risk.daily_max_trades == 100
        assert user_config.risk.daily_max_loss == Decimal("0.05")
        assert user_config.risk.max_position_hold_time == 480

        await manager.close()

    @pytest.mark.asyncio
    async def test_risk_config_with_null_extended_fields(self, config_manager):
        """Test RiskConfig handles None values for extended fields."""
        user_config = await config_manager.get_user_config()

        # Extended fields should be None when not set in database
        assert user_config.risk.daily_max_trades is None
        assert user_config.risk.daily_max_loss is None
        assert user_config.risk.max_position_hold_time is None

        # Core fields should still have values
        assert user_config.risk.max_loss_percent == Decimal("0.01")
        assert user_config.risk.max_leverage == 10
        assert user_config.risk.max_total_exposure == Decimal("0.8")

    @pytest.mark.asyncio
    async def test_risk_config_partial_extended_fields(self, temp_db_path):
        """Test RiskConfig with partial extended fields set."""
        manager = ConfigManager(db_path=temp_db_path)
        await manager.initialize_from_db()

        # Set only daily_max_trades
        async with manager._db.execute("""
            UPDATE risk_configs
            SET daily_max_trades = ?,
                updated_at = datetime('now')
            WHERE id = 'global'
        """, (50,)) as cursor:
            await manager._db.commit()

        user_config = await manager.get_user_config()

        assert user_config.risk.daily_max_trades == 50
        assert user_config.risk.daily_max_loss is None
        assert user_config.risk.max_position_hold_time is None

        await manager.close()


class TestSystemConfigExtendedFields:
    """Test SystemConfig extended optional fields parsing."""

    @pytest.mark.asyncio
    async def test_system_config_with_queue_fields(self, temp_db_path):
        """Test loading SystemConfig with queue configuration fields."""
        manager = ConfigManager(db_path=temp_db_path)
        await manager.initialize_from_db()

        # Update queue fields
        async with manager._db.execute("""
            UPDATE system_configs
            SET queue_batch_size = ?,
                queue_flush_interval = ?,
                queue_max_size = ?,
                updated_at = datetime('now')
            WHERE id = 'global'
        """, (20, "10.5", 2000)) as cursor:
            await manager._db.commit()

        # Reload and verify queue fields
        await manager.reload_all_configs_from_db()
        core_config = manager.get_core_config()

        # Note: CoreConfig may not expose these fields directly
        # Verify they can be loaded from database
        async with manager._db.execute(
            "SELECT queue_batch_size, queue_flush_interval, queue_max_size FROM system_configs WHERE id = 'global'"
        ) as cursor:
            row = await cursor.fetchone()
            assert row["queue_batch_size"] == 20
            assert Decimal(str(row["queue_flush_interval"])) == Decimal("10.5")
            assert row["queue_max_size"] == 2000

        await manager.close()

    @pytest.mark.asyncio
    async def test_system_config_with_warmup_field(self, temp_db_path):
        """Test loading SystemConfig with warmup_history_bars field."""
        manager = ConfigManager(db_path=temp_db_path)
        await manager.initialize_from_db()

        # Update warmup field
        async with manager._db.execute("""
            UPDATE system_configs
            SET warmup_history_bars = ?,
                updated_at = datetime('now')
            WHERE id = 'global'
        """, (200,)) as cursor:
            await manager._db.commit()

        # Verify database value
        async with manager._db.execute(
            "SELECT warmup_history_bars FROM system_configs WHERE id = 'global'"
        ) as cursor:
            row = await cursor.fetchone()
            assert row["warmup_history_bars"] == 200

        await manager.close()

    @pytest.mark.asyncio
    async def test_system_config_with_atr_fields(self, temp_db_path):
        """Test loading SystemConfig with ATR filter configuration fields."""
        manager = ConfigManager(db_path=temp_db_path)
        await manager.initialize_from_db()

        # Update ATR fields
        async with manager._db.execute("""
            UPDATE system_configs
            SET atr_filter_enabled = ?,
                atr_period = ?,
                atr_min_ratio = ?,
                updated_at = datetime('now')
            WHERE id = 'global'
        """, (False, 21, "0.8")) as cursor:
            await manager._db.commit()

        # Verify database values
        async with manager._db.execute(
            "SELECT atr_filter_enabled, atr_period, atr_min_ratio FROM system_configs WHERE id = 'global'"
        ) as cursor:
            row = await cursor.fetchone()
            assert row["atr_filter_enabled"] == False
            assert row["atr_period"] == 21
            assert Decimal(str(row["atr_min_ratio"])) == Decimal("0.8")

        await manager.close()

    @pytest.mark.asyncio
    async def test_system_config_with_all_extended_fields(self, temp_db_path):
        """Test loading SystemConfig with all extended fields at once."""
        manager = ConfigManager(db_path=temp_db_path)
        await manager.initialize_from_db()

        # Update all extended fields
        async with manager._db.execute("""
            UPDATE system_configs
            SET queue_batch_size = ?,
                queue_flush_interval = ?,
                queue_max_size = ?,
                warmup_history_bars = ?,
                atr_filter_enabled = ?,
                atr_period = ?,
                atr_min_ratio = ?,
                updated_at = datetime('now')
            WHERE id = 'global'
        """, (15, "8.0", 1500, 150, True, 18, "0.6")) as cursor:
            await manager._db.commit()

        # Verify all fields in database
        async with manager._db.execute(
            "SELECT * FROM system_configs WHERE id = 'global'"
        ) as cursor:
            row = await cursor.fetchone()
            assert row["queue_batch_size"] == 15
            assert Decimal(str(row["queue_flush_interval"])) == Decimal("8.0")
            assert row["queue_max_size"] == 1500
            assert row["warmup_history_bars"] == 150
            assert row["atr_filter_enabled"] == True
            assert row["atr_period"] == 18
            assert Decimal(str(row["atr_min_ratio"])) == Decimal("0.6")

        await manager.close()

    @pytest.mark.asyncio
    async def test_system_config_null_extended_fields(self, config_manager):
        """Test SystemConfig handles None values for extended fields."""
        # Verify database has default values or NULL
        async with config_manager._db.execute(
            "SELECT queue_batch_size, warmup_history_bars, atr_period FROM system_configs WHERE id = 'global'"
        ) as cursor:
            row = await cursor.fetchone()
            # Should have defaults from table creation
            assert row["queue_batch_size"] == 10
            assert row["warmup_history_bars"] == 100
            assert row["atr_period"] == 14


# ============================================================
# CoreConfig ATR Object Tests (TASK-2)
# ============================================================

class TestCoreConfigAtrObject:
    """Test CoreConfig.atr nested object loading."""

    @pytest.mark.asyncio
    async def test_core_config_atr_default_values(self, config_manager):
        """Test CoreConfig.atr has correct default values."""
        core_config = config_manager.get_core_config()

        assert hasattr(core_config, 'atr')
        assert core_config.atr.enabled is True
        assert core_config.atr.period == 14
        assert core_config.atr.min_ratio == Decimal("0.5")

    @pytest.mark.asyncio
    async def test_core_config_atr_from_database(self, temp_db_path):
        """Test CoreConfig.atr loads correctly from database."""
        manager = ConfigManager(db_path=temp_db_path)
        await manager.initialize_from_db()

        # Update ATR fields in database
        async with manager._db.execute("""
            UPDATE system_configs
            SET atr_filter_enabled = ?,
                atr_period = ?,
                atr_min_ratio = ?,
                updated_at = datetime('now')
            WHERE id = 'global'
        """, (False, 21, "0.8")) as cursor:
            await manager._db.commit()

        # Reload and verify CoreConfig.atr
        await manager.reload_all_configs_from_db()
        core_config = manager.get_core_config()

        assert core_config.atr.enabled is False
        assert core_config.atr.period == 21
        assert core_config.atr.min_ratio == Decimal("0.8")

        await manager.close()

    @pytest.mark.asyncio
    async def test_core_config_warmup_history_bars(self, temp_db_path):
        """Test CoreConfig.warmup.history_bars loads from database."""
        manager = ConfigManager(db_path=temp_db_path)
        await manager.initialize_from_db()

        # Update warmup_history_bars
        async with manager._db.execute("""
            UPDATE system_configs
            SET warmup_history_bars = ?,
                updated_at = datetime('now')
            WHERE id = 'global'
        """, (250,)) as cursor:
            await manager._db.commit()

        # Reload and verify
        await manager.reload_all_configs_from_db()
        core_config = manager.get_core_config()

        assert core_config.warmup.history_bars == 250

        await manager.close()


# ============================================================
# Risk Config Update Tests
# ============================================================

class TestRiskConfigUpdate:
    """Test risk configuration updates."""

    @pytest.mark.asyncio
    async def test_update_risk_config_with_extended_fields(self, config_manager):
        """Test updating risk config with extended fields."""
        new_risk = RiskConfig(
            max_loss_percent=Decimal("0.02"),  # 2%
            max_leverage=20,
            max_total_exposure=Decimal("0.9"),
            daily_max_trades=100,
            daily_max_loss=Decimal("0.05"),
            max_position_hold_time=480,
        )

        await config_manager.update_risk_config(new_risk, changed_by="test")

        # Verify update
        user_config = await config_manager.get_user_config()
        assert user_config.risk.max_loss_percent == Decimal("0.02")
        assert user_config.risk.max_leverage == 20
        assert user_config.risk.max_total_exposure == Decimal("0.9")
        assert user_config.risk.daily_max_trades == 100
        assert user_config.risk.daily_max_loss == Decimal("0.05")
        assert user_config.risk.max_position_hold_time == 480

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
# Configuration Corruption Degradation Tests (R5.2)
# ============================================================

class TestConfigCorruptionDegradation:
    """Test configuration corruption degradation handling (R5.2)."""

    @pytest.mark.asyncio
    async def test_corrupted_json_returns_none(self, temp_db_path):
        """Test that corrupted JSON returns None instead of crashing."""
        from src.infrastructure.config_entry_repository import ConfigEntryRepository

        repo = ConfigEntryRepository(db_path=temp_db_path)
        await repo.initialize()

        # Insert corrupted JSON data
        corrupted_json = "{ invalid json }"
        await repo.upsert_entry("test.corrupted_key", corrupted_json, version="v1.0.0")

        # Manually update the value_type to 'json' to simulate corrupted data
        async with repo._db.execute(
            "UPDATE config_entries_v2 SET config_value = ?, value_type = 'json' WHERE config_key = ?",
            (corrupted_json, "test.corrupted_key")
        ) as cursor:
            await repo._db.commit()

        # Try to get the entry - should not crash
        entry = await repo.get_entry("test.corrupted_key")

        # Should return None for corrupted data
        assert entry is None or entry.get("config_value") is None

        await repo.close()

    @pytest.mark.asyncio
    async def test_system_config_corruption_uses_default(self, temp_db_path):
        """Test that corrupted system config uses default values."""
        manager = ConfigManager(db_path=temp_db_path)
        await manager.initialize_from_db()

        # Corrupt system config by injecting invalid JSON
        async with manager._db.execute(
            "UPDATE system_configs SET mtf_mapping = ? WHERE id = 'global'",
            ("{ invalid json }",)
        ) as cursor:
            await manager._db.commit()

        # Should still return valid config (using defaults for corrupted fields)
        core_config = manager.get_core_config()
        assert core_config is not None
        assert core_config.mtf_mapping is not None

        await manager.close()

    @pytest.mark.asyncio
    async def test_user_config_validation_error_uses_default(self, temp_db_path):
        """Test that UserConfig validation error falls back to default config."""
        manager = ConfigManager(db_path=temp_db_path)
        await manager.initialize_from_db()

        # Get user config should not crash even with potential validation issues
        user_config = await manager.get_user_config()

        # Should return valid config
        assert user_config is not None
        assert user_config.exchange is not None
        assert user_config.risk is not None

        await manager.close()

    @pytest.mark.asyncio
    async def test_corrupted_strategy_json_skipped(self, temp_db_path):
        """Test that corrupted strategy JSON is skipped."""
        manager = ConfigManager(db_path=temp_db_path)
        await manager.initialize_from_db()

        # Insert corrupted strategy directly into database
        async with manager._db.execute("""
            INSERT INTO strategies (id, name, is_active, trigger_config, filter_configs, filter_logic, symbols, timeframes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "corrupted_strategy",
            "Corrupted Strategy",
            True,
            "{ invalid json }",  # Corrupted trigger_config
            "also invalid json",  # Corrupted filter_configs
            "AND",
            "[]",
            "[]",
        )) as cursor:
            await manager._db.commit()

        # Load user config - should skip corrupted strategy
        user_config = await manager.get_user_config()
        assert user_config is not None

        # Corrupted strategy should be skipped
        strategy_ids = [s.id for s in user_config.active_strategies]
        assert "corrupted_strategy" not in strategy_ids

        await manager.close()

    @pytest.mark.asyncio
    async def test_corrupted_strategy_name_field_skipped(self, temp_db_path):
        """Test that strategy with empty trigger_config is handled gracefully."""
        manager = ConfigManager(db_path=temp_db_path)
        await manager.initialize_from_db()

        # Insert strategy with empty trigger_config (NOT NULL constraint)
        async with manager._db.execute("""
            INSERT INTO strategies (id, name, is_active, trigger_config, filter_configs, filter_logic, symbols, timeframes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "empty_trigger_strategy",
            "Empty Trigger Strategy",
            True,
            "",  # Empty string instead of NULL
            "[]",
            "AND",
            "[]",
            "[]",
        )) as cursor:
            await manager._db.commit()

        # Load user config - should handle empty string gracefully
        user_config = await manager.get_user_config()
        assert user_config is not None

        await manager.close()

    @pytest.mark.asyncio
    async def test_create_default_user_config(self, temp_db_path):
        """Test _create_default_user_config method."""
        manager = ConfigManager(db_path=temp_db_path)
        await manager.initialize_from_db()

        default_config = manager._create_default_user_config()

        assert default_config is not None
        assert default_config.exchange.name == "binance"
        assert default_config.risk.max_loss_percent == Decimal("0.01")
        assert default_config.risk.max_leverage == 10

        await manager.close()

    @pytest.mark.asyncio
    async def test_yaml_corruption_uses_default(self, temp_db_path, yaml_config_dir):
        """Test that corrupted YAML uses default config."""
        # Corrupt user.yaml with invalid YAML
        with open(os.path.join(yaml_config_dir, "user.yaml"), "w") as f:
            f.write("invalid: yaml: content: { broken")

        manager = ConfigManager(db_path=temp_db_path, config_dir=yaml_config_dir)
        await manager.initialize_from_db()

        # Should fall back to default config instead of crashing
        user_config = await manager.get_user_config()
        assert user_config is not None
        assert user_config.exchange is not None

        await manager.close()


# ============================================================
# Profile Switch Cache Refresh Tests (R1.1)
# ============================================================

class TestProfileSwitchCacheRefresh:
    """Test cache refresh functionality for Profile switch (R1.1 fix)."""

    @pytest.mark.asyncio
    async def test_reload_all_configs_from_db(self, config_manager):
        """Test reloading all configs from database."""
        # Get initial config
        initial_core = config_manager.get_core_config()
        initial_ema_period = initial_core.ema.period

        # Modify config in database directly
        await config_manager._db.execute("""
            UPDATE system_configs
            SET ema_period = ?, updated_at = datetime('now')
            WHERE id = 'global'
        """, (999,))
        await config_manager._db.commit()

        # Verify cache still has old value
        cached_core = config_manager.get_core_config()
        assert cached_core.ema.period == initial_ema_period

        # Reload from database
        await config_manager.reload_all_configs_from_db()

        # Verify cache is updated
        reloaded_core = config_manager.get_core_config()
        assert reloaded_core.ema.period == 999

    @pytest.mark.asyncio
    async def test_reload_all_configs_from_db_notifies_observers(self, config_manager):
        """Test that reload_all_configs_from_db notifies observers."""
        called = False

        async def observer():
            nonlocal called
            called = True

        config_manager.add_observer(observer)

        # Reload configs
        await config_manager.reload_all_configs_from_db()

        # Verify observer was called
        assert called is True

    @pytest.mark.asyncio
    async def test_reload_all_configs_from_db_handles_uninitialized(self):
        """Test that reload handles uninitialized database gracefully."""
        manager = ConfigManager()
        # Don't initialize database

        # Should not raise error
        await manager.reload_all_configs_from_db()


# ============================================================
# Entry Point
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=src/application/config_manager_db"])
