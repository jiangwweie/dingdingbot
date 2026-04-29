"""
Test Configuration Manager - Config loading, merging, and permission checks.
"""
import os
import tempfile
import pytest
from decimal import Decimal
from pathlib import Path

import yaml
import json

from src.application.config_manager import ConfigManager, load_all_configs
from src.domain.exceptions import FatalStartupError


class TestConfigManager:
    """Test configuration loading and merging"""

    @pytest.fixture
    def temp_config_dir(self):
        """Create temporary directory with test config files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)

            # Create core.yaml
            core_config = {
                "core_symbols": [
                    "BTC/USDT:USDT",
                    "ETH/USDT:USDT",
                    "SOL/USDT:USDT",
                    "BNB/USDT:USDT",
                ],
                "pinbar_defaults": {
                    "min_wick_ratio": "0.6",
                    "max_body_ratio": "0.3",
                    "body_position_tolerance": "0.1",
                },
                "ema": {
                    "period": 60,
                },
                "mtf_mapping": {
                    "15m": "1h",
                    "1h": "4h",
                    "4h": "1d",
                    "1d": "1w",
                },
                "warmup": {
                    "history_bars": 100,
                },
            }

            with open(config_dir / "core.yaml", "w") as f:
                yaml.dump(core_config, f)

            # Create user.yaml
            user_config = {
                "exchange": {
                    "name": "binance",
                    "api_key": "test_api_key_12345",
                    "api_secret": "test_api_secret_67890",
                    "testnet": True,
                },
                "user_symbols": [
                    "XRP/USDT:USDT",
                    "DOGE/USDT:USDT",
                ],
                "timeframes": ["15m", "1h", "4h"],
                "strategy": {
                    "trend_filter_enabled": True,
                    "mtf_validation_enabled": True,
                },
                "risk": {
                    "max_loss_percent": "0.01",
                    "max_leverage": 10,
                },
                "asset_polling": {
                    "interval_seconds": 60,
                },
                "notification": {
                    "channels": [
                        {
                            "type": "feishu",
                            "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/test123",
                        }
                    ],
                },
            }

            with open(config_dir / "user.yaml", "w") as f:
                yaml.dump(user_config, f)

            yield config_dir

    def test_load_core_config(self, temp_config_dir):
        """Test loading core configuration"""
        manager = ConfigManager(temp_config_dir)
        core = manager.load_core_config()

        assert core.core_symbols == [
            "BTC/USDT:USDT",
            "ETH/USDT:USDT",
            "SOL/USDT:USDT",
            "BNB/USDT:USDT",
        ]
        assert core.ema.period == 60
        assert core.warmup.history_bars == 100
        assert core.pinbar_defaults.min_wick_ratio == Decimal("0.6")

    def test_load_user_config(self, temp_config_dir):
        """Test loading user configuration"""
        manager = ConfigManager(temp_config_dir)
        user = manager.load_user_config()

        assert user.exchange.name == "binance"
        assert user.exchange.testnet is True
        assert user.timeframes == ["15m", "1h", "4h"]
        assert user.risk.max_loss_percent == Decimal("0.01")
        assert user.risk.max_leverage == 10

    def test_merge_symbols(self, temp_config_dir):
        """Test symbol merging with deduplication"""
        manager = ConfigManager(temp_config_dir)
        manager.load_core_config()
        manager.load_user_config()

        merged = manager.merge_symbols()

        # Core symbols must be included
        assert "BTC/USDT:USDT" in merged
        assert "ETH/USDT:USDT" in merged

        # User symbols must be included
        assert "XRP/USDT:USDT" in merged
        assert "DOGE/USDT:USDT" in merged

        # Core symbols should come first
        assert merged.index("BTC/USDT:USDT") < merged.index("XRP/USDT:USDT")

        # No duplicates
        assert len(merged) == len(set(merged))

    def test_merge_symbols_with_duplicate(self, temp_config_dir):
        """Test that duplicate user symbols are ignored"""
        # Add a duplicate symbol to user config
        with open(temp_config_dir / "user.yaml", "r") as f:
            user_config = yaml.safe_load(f)

        user_config["user_symbols"].append("BTC/USDT:USDT")  # Duplicate

        with open(temp_config_dir / "user.yaml", "w") as f:
            yaml.dump(user_config, f)

        manager = ConfigManager(temp_config_dir)
        manager.load_core_config()
        manager.load_user_config()

        merged = manager.merge_symbols()

        # Should only appear once
        assert merged.count("BTC/USDT:USDT") == 1

    def test_missing_core_config(self):
        """Test error when core.yaml is missing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ConfigManager(tmpdir)

            with pytest.raises(FatalStartupError) as exc_info:
                manager.load_core_config()

            assert exc_info.value.error_code == "F-003"

    def test_missing_user_config(self):
        """Test error when user.yaml is missing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ConfigManager(tmpdir)

            # Create empty core.yaml
            with open(Path(tmpdir) / "core.yaml", "w") as f:
                yaml.dump({"core_symbols": ["BTC/USDT:USDT"]}, f)

            with pytest.raises(FatalStartupError) as exc_info:
                manager.load_user_config()

            assert exc_info.value.error_code == "F-003"

    def test_invalid_core_config_schema(self, temp_config_dir):
        """Test error when core.yaml has invalid schema"""
        # Remove required field
        with open(temp_config_dir / "core.yaml", "w") as f:
            yaml.dump({"core_symbols": ["BTC/USDT:USDT"]}, f)  # Missing other required fields

        manager = ConfigManager(temp_config_dir)

        with pytest.raises(FatalStartupError) as exc_info:
            manager.load_core_config()

        assert exc_info.value.error_code == "F-003"

    def test_invalid_user_config_schema(self, temp_config_dir):
        """Test error when user.yaml has invalid schema"""
        # Remove required field
        with open(temp_config_dir / "user.yaml", "w") as f:
            yaml.dump({"exchange": {"name": "binance"}}, f)  # Missing api_key, api_secret

        manager = ConfigManager(temp_config_dir)
        manager.load_core_config()

        with pytest.raises(FatalStartupError) as exc_info:
            manager.load_user_config()

        assert exc_info.value.error_code == "F-003"

    def test_load_all_configs_convenience(self, temp_config_dir):
        """Test load_all_configs convenience function"""
        manager = load_all_configs(temp_config_dir)

        assert manager.core_config is not None
        assert manager.user_config is not None
        assert len(manager.merged_symbols) == 6  # 4 core + 2 user


class TestSecretMasking:
    """Test secret masking in config manager"""

    @pytest.fixture
    def temp_config_dir(self):
        """Create temporary directory with test config files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)

            # Create minimal core.yaml
            with open(config_dir / "core.yaml", "w") as f:
                yaml.dump({
                    "core_symbols": ["BTC/USDT:USDT"],
                    "pinbar_defaults": {
                        "min_wick_ratio": "0.6",
                        "max_body_ratio": "0.3",
                        "body_position_tolerance": "0.1",
                    },
                    "ema": {"period": 60},
                    "mtf_mapping": {"15m": "1h"},
                    "warmup": {"history_bars": 100},
                }, f)

            # Create user.yaml
            with open(config_dir / "user.yaml", "w") as f:
                yaml.dump({
                    "exchange": {
                        "name": "binance",
                        "api_key": "sk_test_abcdefghijklmnop",
                        "api_secret": "secret_1234567890abcdef",
                        "testnet": True,
                    },
                    "user_symbols": [],
                    "timeframes": ["1h"],
                    "strategy": {
                        "trend_filter_enabled": True,
                        "mtf_validation_enabled": True,
                    },
                    "risk": {
                        "max_loss_percent": "0.01",
                        "max_leverage": 10,
                    },
                    "notification": {
                        "channels": [{
                            "type": "feishu",
                            "webhook_url": "https://hook.test/webhook/abc123",
                        }],
                    },
                }, f)

            yield config_dir

    def test_secrets_registered_on_load(self, temp_config_dir, caplog):
        """Test that secrets are registered for masking"""
        import logging
        logging.getLogger().setLevel(logging.INFO)

        manager = load_all_configs(temp_config_dir)

        # Config should load successfully
        assert manager.user_config.exchange.api_key == "sk_test_abcdefghijklmnop"


class TestConfigImmutability:
    """Test R3.1: Configuration object immutability to prevent reference issues"""

    @pytest.fixture
    def temp_config_dir(self):
        """Create temporary directory with test config files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)

            # Create core.yaml
            core_config = {
                "core_symbols": ["BTC/USDT:USDT"],
                "pinbar_defaults": {
                    "min_wick_ratio": "0.6",
                    "max_body_ratio": "0.3",
                    "body_position_tolerance": "0.1",
                },
                "ema": {"period": 60},
                "mtf_mapping": {"15m": "1h"},
                "warmup": {"history_bars": 100},
            }

            with open(config_dir / "core.yaml", "w") as f:
                yaml.dump(core_config, f)

            # Create user.yaml
            user_config = {
                "exchange": {
                    "name": "binance",
                    "api_key": "test_api_key",
                    "api_secret": "test_api_secret",
                    "testnet": True,
                },
                "user_symbols": ["ETH/USDT:USDT"],
                "timeframes": ["15m", "1h"],
                "strategy": {
                    "trend_filter_enabled": True,
                    "mtf_validation_enabled": True,
                },
                "risk": {
                    "max_loss_percent": "0.01",
                    "max_leverage": 10,
                },
                "asset_polling": {"interval_seconds": 60},
                "notification": {
                    "channels": [{
                        "type": "feishu",
                        "webhook_url": "https://test.feishu.cn/webhook",
                    }],
                },
            }

            with open(config_dir / "user.yaml", "w") as f:
                yaml.dump(user_config, f)

            yield config_dir

    def test_get_user_config_returns_copy(self, temp_config_dir):
        """Test that get_user_config() returns a copy, not a reference"""
        import asyncio
        from src.application.config_manager_db import ConfigManager

        manager = ConfigManager(config_dir=temp_config_dir)

        # Get config twice
        config1 = asyncio.run(manager.get_user_config())
        config2 = asyncio.run(manager.get_user_config())

        # They should be equal but not the same object
        assert config1 == config2
        assert config1 is not config2

        # Modifying config1 should NOT affect config2 or internal state
        original_max_loss = config1.risk.max_loss_percent
        config1.risk.max_loss_percent = Decimal("0.99")

        # config2 should still have original value
        assert config2.risk.max_loss_percent == original_max_loss

        # Getting config again should return original value
        config3 = asyncio.run(manager.get_user_config())
        assert config3.risk.max_loss_percent == original_max_loss

    def test_get_core_config_returns_copy(self, temp_config_dir):
        """Test that get_core_config() returns a copy, not a reference"""
        from src.application.config_manager_db import ConfigManager

        manager = ConfigManager(config_dir=temp_config_dir)

        # Get config twice
        config1 = manager.get_core_config()
        config2 = manager.get_core_config()

        # They should be equal but not the same object
        assert config1.core_symbols == config2.core_symbols
        assert config1 is not config2

        # Modifying config1 should NOT affect config2 or internal state
        original_symbols = config1.core_symbols.copy()
        config1.core_symbols.append("MODIFIED")

        # config2 should still have original value
        assert "MODIFIED" not in config2.core_symbols
        assert config2.core_symbols == original_symbols

        # Getting config again should return original value
        config3 = manager.get_core_config()
        assert "MODIFIED" not in config3.core_symbols
        assert config3.core_symbols == original_symbols

    def test_external_modification_does_not_affect_internal_state(self, temp_config_dir):
        """Test that external modification does not affect internal state"""
        import asyncio
        from src.application.config_manager_db import ConfigManager

        manager = ConfigManager(config_dir=temp_config_dir)

        # Get config and modify it
        config = asyncio.run(manager.get_user_config())
        original_leverage = config.risk.max_leverage

        # Try to modify the config
        config.risk.max_leverage = 999

        # Get config again - should have original value
        config2 = asyncio.run(manager.get_user_config())
        assert config2.risk.max_leverage == original_leverage
        assert config2.risk.max_leverage != 999


# ============================================================
# Import/Export History Tracking Tests
# ============================================================

class TestImportExportHistoryTracking:
    """Tests for import/export history tracking in ConfigManager."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database file for testing."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        yield path
        # Cleanup
        if os.path.exists(path):
            os.remove(path)
        for suffix in ["-wal", "-shm"]:
            wal_path = path + suffix
            if os.path.exists(wal_path):
                os.remove(wal_path)

    @pytest.fixture
    def sample_yaml_config(self):
        """Sample valid configuration YAML for testing."""
        return """
risk:
  max_loss_percent: 0.02
  max_leverage: 20
  max_total_exposure: 0.9
  cooldown_minutes: 300

system:
  core_symbols:
    - BTC/USDT:USDT
    - ETH/USDT:USDT
  ema_period: 50
  mtf_ema_period: 50
  mtf_mapping:
    "15m": "1h"
    "1h": "4h"
  signal_cooldown_seconds: 7200

strategies:
  - name: Test Strategy
    description: Test strategy for import/export
    trigger:
      type: pinbar
      enabled: true
      params:
        min_wick_ratio: 0.6
    filters: []
    filter_logic: AND
"""

    @pytest.fixture
    def yaml_config_path(self, sample_yaml_config) -> str:
        """Create a temporary YAML config file."""
        fd, path = tempfile.mkstemp(suffix=".yaml")
        os.close(fd)

        with open(path, 'w', encoding='utf-8') as f:
            f.write(sample_yaml_config)

        yield path

        # Cleanup
        if os.path.exists(path):
            os.remove(path)

    @pytest.mark.asyncio
    async def test_import_records_to_history(self, temp_db_path, yaml_config_path):
        """Test that import_from_yaml records operation to config_history table."""
        from src.application.config_manager import ConfigManager

        manager = ConfigManager(db_path=temp_db_path)
        await manager.initialize_from_db()

        # Perform import
        await manager.import_from_yaml(
            yaml_path=yaml_config_path,
            changed_by="test_user"
        )

        # Query history table
        async with manager._db.execute(
            """
            SELECT entity_type, entity_id, action, changed_by, change_summary
            FROM config_history
            WHERE action = 'IMPORT'
            ORDER BY changed_at DESC
            LIMIT 1
            """
        ) as cursor:
            row = await cursor.fetchone()

        assert row is not None, "Import operation should be recorded in config_history"
        assert row[0] == "config_bundle", "Entity type should be 'config_bundle'"
        assert row[1] == "import_export", "Entity ID should be 'import_export'"
        assert row[2] == "IMPORT", "Action should be 'IMPORT'"
        assert row[3] == "test_user", "Changed by should match the operator"
        assert "imported from" in row[4], "Summary should mention import source"

        # Cleanup
        await manager._db.close()

    @pytest.mark.asyncio
    async def test_import_history_new_values_contains_metadata(self, temp_db_path, yaml_config_path):
        """Test that import history new_values contains source path and data keys."""
        from src.application.config_manager import ConfigManager

        manager = ConfigManager(db_path=temp_db_path)
        await manager.initialize_from_db()

        # Perform import
        await manager.import_from_yaml(
            yaml_path=yaml_config_path,
            changed_by="import_tester"
        )

        # Query history table for new_values
        async with manager._db.execute(
            """
            SELECT new_values FROM config_history
            WHERE action = 'IMPORT'
            ORDER BY changed_at DESC
            LIMIT 1
            """
        ) as cursor:
            row = await cursor.fetchone()

        assert row is not None
        new_values = json.loads(row[0])

        assert "source_path" in new_values, "new_values should contain source_path"
        assert yaml_config_path in new_values["source_path"], "source_path should match"
        assert "data_keys" in new_values, "new_values should contain data_keys"
        assert isinstance(new_values["data_keys"], list), "data_keys should be a list"
        # Sample YAML has: risk, system, strategies
        assert len(new_values["data_keys"]) >= 3, "Should have at least 3 top-level keys"

        # Cleanup
        await manager._db.close()

    @pytest.mark.asyncio
    async def test_import_history_default_operator(self, temp_db_path, yaml_config_path):
        """Test that import uses default 'system' operator when not specified."""
        from src.application.config_manager import ConfigManager

        manager = ConfigManager(db_path=temp_db_path)
        await manager.initialize_from_db()

        await manager.import_from_yaml(yaml_path=yaml_config_path)

        # Query history table
        async with manager._db.execute(
            """
            SELECT changed_by FROM config_history
            WHERE action = 'IMPORT'
            ORDER BY changed_at DESC
            LIMIT 1
            """
        ) as cursor:
            row = await cursor.fetchone()

        assert row is not None
        assert row[0] == "system", "Default operator should be 'system'"

        # Cleanup
        await manager._db.close()

    @pytest.mark.asyncio
    async def test_export_records_to_history(self, temp_db_path):
        """Test that export_to_yaml records operation to config_history table."""
        from src.application.config_manager import ConfigManager

        manager = ConfigManager(db_path=temp_db_path)
        await manager.initialize_from_db()

        export_path = temp_db_path.replace(".db", "_export.yaml")

        # Perform export
        await manager.export_to_yaml(
            yaml_path=export_path,
            changed_by="export_user"
        )

        # Query history table
        async with manager._db.execute(
            """
            SELECT entity_type, entity_id, action, changed_by, change_summary
            FROM config_history
            WHERE action = 'EXPORT'
            ORDER BY changed_at DESC
            LIMIT 1
            """
        ) as cursor:
            row = await cursor.fetchone()

        assert row is not None, "Export operation should be recorded in config_history"
        assert row[0] == "config_bundle", "Entity type should be 'config_bundle'"
        assert row[1] == "import_export", "Entity ID should be 'import_export'"
        assert row[2] == "EXPORT", "Action should be 'EXPORT'"
        assert row[3] == "export_user", "Changed by should match the operator"
        assert "exported to" in row[4], "Summary should mention export target"

        # Cleanup
        if os.path.exists(export_path):
            os.remove(export_path)
        await manager._db.close()

    @pytest.mark.asyncio
    async def test_export_history_new_values_contains_target_path(self, temp_db_path):
        """Test that export history new_values contains target path."""
        from src.application.config_manager import ConfigManager

        manager = ConfigManager(db_path=temp_db_path)
        await manager.initialize_from_db()

        export_path = temp_db_path.replace(".db", "_export_test.yaml")

        # Perform export
        await manager.export_to_yaml(
            yaml_path=export_path,
            changed_by="path_tester"
        )

        # Query history table for new_values
        async with manager._db.execute(
            """
            SELECT new_values FROM config_history
            WHERE action = 'EXPORT'
            ORDER BY changed_at DESC
            LIMIT 1
            """
        ) as cursor:
            row = await cursor.fetchone()

        assert row is not None
        new_values = json.loads(row[0])

        assert "target_path" in new_values, "new_values should contain target_path"
        assert export_path in new_values["target_path"], "target_path should match"

        # Cleanup
        if os.path.exists(export_path):
            os.remove(export_path)
        await manager._db.close()

    @pytest.mark.asyncio
    async def test_export_history_default_operator(self, temp_db_path):
        """Test that export uses default 'system' operator when not specified."""
        from src.application.config_manager import ConfigManager

        manager = ConfigManager(db_path=temp_db_path)
        await manager.initialize_from_db()

        export_path = temp_db_path.replace(".db", "_export_default.yaml")

        await manager.export_to_yaml(yaml_path=export_path)

        # Query history table
        async with manager._db.execute(
            """
            SELECT changed_by FROM config_history
            WHERE action = 'EXPORT'
            ORDER BY changed_at DESC
            LIMIT 1
            """
        ) as cursor:
            row = await cursor.fetchone()

        assert row is not None
        assert row[0] == "system", "Default operator should be 'system'"

        # Cleanup
        if os.path.exists(export_path):
            os.remove(export_path)
        await manager._db.close()

    @pytest.mark.asyncio
    async def test_multiple_import_export_operations(self, temp_db_path, yaml_config_path):
        """Test that multiple import/export operations are all recorded."""
        from src.application.config_manager import ConfigManager

        manager = ConfigManager(db_path=temp_db_path)
        await manager.initialize_from_db()

        # Perform multiple operations
        await manager.import_from_yaml(yaml_path=yaml_config_path, changed_by="user1")

        export_path1 = temp_db_path.replace(".db", "_export1.yaml")
        await manager.export_to_yaml(yaml_path=export_path1, changed_by="user2")

        await manager.import_from_yaml(yaml_path=yaml_config_path, changed_by="user3")

        export_path2 = temp_db_path.replace(".db", "_export2.yaml")
        await manager.export_to_yaml(yaml_path=export_path2, changed_by="user4")

        # Query all history records
        async with manager._db.execute(
            """
            SELECT action, changed_by FROM config_history
            WHERE entity_type = 'config_bundle'
            ORDER BY changed_at ASC
            """
        ) as cursor:
            rows = await cursor.fetchall()
            # Convert sqlite3.Row objects to tuples
            rows = [(row[0], row[1]) for row in rows]

        assert len(rows) == 4, "Should have 4 history records (2 imports + 2 exports)"
        assert rows[0] == ("IMPORT", "user1"), f"First record should be (IMPORT, user1), got {rows[0]}"
        assert rows[1] == ("EXPORT", "user2"), f"Second record should be (EXPORT, user2), got {rows[1]}"
        assert rows[2] == ("IMPORT", "user3"), f"Third record should be (IMPORT, user3), got {rows[2]}"
        assert rows[3] == ("EXPORT", "user4"), f"Fourth record should be (EXPORT, user4), got {rows[3]}"

        # Cleanup
        for path in [export_path1, export_path2]:
            if os.path.exists(path):
                os.remove(path)
        await manager._db.close()

    @pytest.mark.asyncio
    async def test_import_nonexistent_file_raises_error_no_history(self, temp_db_path):
        """Test that importing nonexistent file raises error without recording history."""
        from src.application.config_manager import ConfigManager

        manager = ConfigManager(db_path=temp_db_path)
        await manager.initialize_from_db()

        with pytest.raises(FileNotFoundError):
            await manager.import_from_yaml(
                yaml_path="/nonexistent/path/config.yaml",
                changed_by="error_tester"
            )

        # Verify no history was recorded
        async with manager._db.execute(
            """
            SELECT COUNT(*) FROM config_history
            WHERE action = 'IMPORT' AND changed_by = 'error_tester'
            """
        ) as cursor:
            row = await cursor.fetchone()

        assert row[0] == 0, "Should not record history for failed import"

        # Cleanup
        await manager._db.close()


# ============================================================
# Test ConfigManager Singleton (Backtest Data Loading Fixes)
# ============================================================

class TestConfigManagerSingleton:
    """Tests for ConfigManager get_instance/set_instance class methods"""

    @pytest.fixture
    def temp_config_dir(self):
        """Create temporary directory with test config files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)

            core_config = {
                "core_symbols": ["BTC/USDT:USDT"],
                "pinbar_defaults": {
                    "min_wick_ratio": "0.6",
                    "max_body_ratio": "0.3",
                    "body_position_tolerance": "0.1",
                },
                "ema": {"period": 60},
                "mtf_mapping": {"15m": "1h"},
                "warmup": {"history_bars": 100},
            }
            with open(config_dir / "core.yaml", "w") as f:
                yaml.dump(core_config, f)

            user_config = {
                "exchange": {
                    "name": "binance",
                    "api_key": "test_api_key",
                    "api_secret": "test_api_secret",
                    "testnet": True,
                },
                "user_symbols": ["ETH/USDT:USDT"],
                "timeframes": ["15m", "1h"],
                "strategy": {
                    "trend_filter_enabled": True,
                    "mtf_validation_enabled": True,
                },
                "risk": {
                    "max_loss_percent": "0.01",
                    "max_leverage": 10,
                },
                "asset_polling": {"interval_seconds": 60},
                "notification": {
                    "channels": [{
                        "type": "feishu",
                        "webhook_url": "https://test.feishu.cn/webhook",
                    }],
                },
            }
            with open(config_dir / "user.yaml", "w") as f:
                yaml.dump(user_config, f)

            yield config_dir

    def test_singleton_get_set(self):
        """Test basic singleton get/set lifecycle"""
        # Initially None
        assert ConfigManager.get_instance() is None

        # Set an instance
        cm = ConfigManager.__new__(ConfigManager)  # Create without __init__ to avoid DB init
        ConfigManager.set_instance(cm)
        assert ConfigManager.get_instance() is cm

        # Clear it
        ConfigManager.set_instance(None)
        assert ConfigManager.get_instance() is None

    def test_singleton_returns_same_instance(self, temp_config_dir):
        """Test that set/get returns the exact same object reference"""
        manager = ConfigManager(temp_config_dir)
        manager.load_core_config()
        manager.load_user_config()

        ConfigManager.set_instance(manager)
        retrieved = ConfigManager.get_instance()

        assert retrieved is manager
        assert retrieved.merged_symbols == manager.merged_symbols

        # Cleanup
        ConfigManager.set_instance(None)

    def test_singleton_isolation_between_instances(self, temp_config_dir):
        """Test that singleton tracks only one instance at a time"""
        manager1 = ConfigManager(temp_config_dir)
        manager2 = ConfigManager(temp_config_dir)

        ConfigManager.set_instance(manager1)
        assert ConfigManager.get_instance() is manager1

        ConfigManager.set_instance(manager2)
        assert ConfigManager.get_instance() is manager2
        assert ConfigManager.get_instance() is not manager1

        # Cleanup
        ConfigManager.set_instance(None)
