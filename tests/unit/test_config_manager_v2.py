"""
Unit tests for ConfigManager V2 - Database-backed configuration management.
"""
import pytest
import tempfile
import os
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from src.application.config_manager import ConfigManager, SystemConfig, load_all_from_db
from src.domain.exceptions import FatalStartupError
from src.domain.models import StrategyDefinition, TriggerConfig, FilterConfig, RiskConfig


class TestConfigManagerInitialization:
    """Test ConfigManager initialization and loading."""

    @pytest.fixture
    async def config_manager(self):
        """Create a ConfigManager instance with test database."""
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_config.db")

        # Mock environment variables for exchange config
        with patch.dict(os.environ, {
            'EXCHANGE_API_KEY': 'test_key',
            'EXCHANGE_API_SECRET': 'test_secret',
            'EXCHANGE_NAME': 'binance',
        }):
            manager = ConfigManager(db_path)
            await manager.initialize()
            yield manager
            await manager.close()

        os.remove(db_path)
        os.rmdir(temp_dir)

    @pytest.mark.asyncio
    async def test_initialize_creates_repository(self, config_manager):
        """Test that initialize creates ConfigRepository."""
        assert config_manager._repo is not None

    @pytest.mark.asyncio
    async def test_load_all_from_db_loads_defaults(self, config_manager):
        """Test that default configurations are loaded."""
        # Risk config should have defaults
        assert config_manager.risk_config is not None
        assert config_manager.risk_config.max_loss_percent == Decimal("1.0")
        assert config_manager.risk_config.max_leverage == 10

        # System config should have defaults
        assert config_manager.system_config is not None
        assert config_manager.system_config.history_bars == 100
        assert config_manager.system_config.queue_batch_size == 10

    @pytest.mark.asyncio
    async def test_default_strategy_created_if_none(self, config_manager):
        """Test that a default strategy is created if none exists in DB."""
        assert config_manager.active_strategy is not None
        assert config_manager.active_strategy.name == "pinbar"

    @pytest.mark.asyncio
    async def test_default_symbols_created_if_none(self, config_manager):
        """Test that default symbols are created if none exist in DB."""
        assert config_manager.symbols is not None
        assert len(config_manager.symbols) == 4
        assert "BTC/USDT:USDT" in config_manager.symbols
        assert "ETH/USDT:USDT" in config_manager.symbols

    @pytest.mark.asyncio
    async def test_exchange_config_from_env(self, config_manager):
        """Test that exchange config is loaded from environment variables."""
        # The config_manager fixture already has exchange_config loaded
        # Just verify it exists and has the expected values
        assert config_manager.exchange_config is not None
        assert config_manager.exchange_config.name == 'binance'
        assert config_manager.exchange_config.api_key == 'test_key'


class TestConfigManagerAccessors:
    """Test ConfigManager accessor properties."""

    @pytest.fixture
    async def config_manager(self):
        """Create a ConfigManager instance with test database."""
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_config.db")

        with patch.dict(os.environ, {
            'EXCHANGE_API_KEY': 'test_key',
            'EXCHANGE_API_SECRET': 'test_secret',
        }):
            manager = ConfigManager(db_path)
            await manager.initialize()
            yield manager
            await manager.close()

        os.remove(db_path)
        os.rmdir(temp_dir)

    @pytest.mark.asyncio
    async def test_active_strategy_accessor(self, config_manager):
        """Test active_strategy property."""
        strategy = config_manager.active_strategy
        assert strategy is not None
        assert isinstance(strategy, StrategyDefinition)

    @pytest.mark.asyncio
    async def test_risk_config_accessor(self, config_manager):
        """Test risk_config property."""
        risk = config_manager.risk_config
        assert risk is not None
        assert isinstance(risk, RiskConfig)

    @pytest.mark.asyncio
    async def test_system_config_accessor(self, config_manager):
        """Test system_config property."""
        system = config_manager.system_config
        assert system is not None
        assert isinstance(system, SystemConfig)

    @pytest.mark.asyncio
    async def test_symbols_accessor(self, config_manager):
        """Test symbols property."""
        symbols = config_manager.symbols
        assert isinstance(symbols, list)
        assert len(symbols) > 0

    @pytest.mark.asyncio
    async def test_notifications_accessor(self, config_manager):
        """Test notifications property."""
        notifications = config_manager.notifications
        assert isinstance(notifications, list)

    @pytest.mark.asyncio
    async def test_exchange_config_accessor(self, config_manager):
        """Test exchange_config property with mocked env."""
        with patch.dict(os.environ, {
            'EXCHANGE_API_KEY': 'test_key',
            'EXCHANGE_API_SECRET': 'test_secret',
        }):
            manager2 = ConfigManager(config_manager.db_path)
            await manager2.initialize()

            assert manager2.exchange_config is not None
            assert manager2.exchange_config.api_key == 'test_key'

            await manager2.close()

    @pytest.mark.asyncio
    async def test_asset_polling_config_accessor(self, config_manager):
        """Test asset_polling_config property."""
        polling = config_manager.asset_polling_config
        assert polling is not None
        assert polling.interval_seconds == 60


class TestConfigManagerHotReload:
    """Test ConfigManager hot-reload and observer pattern."""

    @pytest.fixture
    async def config_manager(self):
        """Create a ConfigManager instance with test database."""
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_config.db")

        with patch.dict(os.environ, {
            'EXCHANGE_API_KEY': 'test_key',
            'EXCHANGE_API_SECRET': 'test_secret',
        }):
            manager = ConfigManager(db_path)
            await manager.initialize()
            yield manager
            await manager.close()

        os.remove(db_path)
        os.rmdir(temp_dir)

    @pytest.mark.asyncio
    async def test_add_observer(self, config_manager):
        """Test adding an observer callback."""
        called = False

        async def callback():
            nonlocal called
            called = True

        config_manager.add_observer(callback)

        # Reload config to trigger observer
        await config_manager.reload_config()

        assert called is True

    @pytest.mark.asyncio
    async def test_remove_observer(self, config_manager):
        """Test removing an observer callback."""
        called = False

        async def callback():
            nonlocal called
            called = True

        config_manager.add_observer(callback)
        config_manager.remove_observer(callback)

        # Reload should not trigger removed observer
        await config_manager.reload_config()

        assert called is False

    @pytest.mark.asyncio
    async def test_reload_config(self, config_manager):
        """Test hot-reloading configuration."""
        # Update risk config in DB (use valid value: 0.1-5.0%)
        await config_manager._repo.update_risk_config(max_loss_percent=0.5)

        # Reload config
        await config_manager.reload_config()

        # Verify updated
        assert config_manager.risk_config.max_loss_percent == Decimal("0.5")

    @pytest.mark.asyncio
    async def test_reload_with_multiple_observers(self, config_manager):
        """Test reloading with multiple observers."""
        called_count = 0

        async def callback1():
            nonlocal called_count
            called_count += 1

        async def callback2():
            nonlocal called_count
            called_count += 1

        config_manager.add_observer(callback1)
        config_manager.add_observer(callback2)

        await config_manager.reload_config()

        assert called_count == 2

    @pytest.mark.asyncio
    async def test_observer_error_handling(self, config_manager):
        """Test that observer errors are caught and logged."""
        async def failing_callback():
            raise ValueError("Observer error")

        async def success_callback():
            pass

        config_manager.add_observer(failing_callback)
        config_manager.add_observer(success_callback)

        # Should not raise, just log error
        await config_manager.reload_config()

    @pytest.mark.asyncio
    async def test_update_lock_initialization(self, config_manager):
        """Test that update lock is lazily initialized."""
        assert config_manager._update_lock is None

        # Access the lock
        lock = config_manager._get_update_lock()

        # Lock should now exist
        assert lock is not None


class TestConfigManagerExport:
    """Test ConfigManager export functionality."""

    @pytest.fixture
    async def config_manager(self):
        """Create a ConfigManager instance with test database."""
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_config.db")

        with patch.dict(os.environ, {
            'EXCHANGE_API_KEY': 'test_key',
            'EXCHANGE_API_SECRET': 'test_secret',
        }):
            manager = ConfigManager(db_path)
            await manager.initialize()

            # Add some test data
            await manager._repo.add_symbol("ETH/USDT:USDT", is_core=0, is_enabled=1)
            await manager._repo.add_notification("feishu", "https://example.com/webhook", is_enabled=1)

            yield manager
            await manager.close()

        os.remove(db_path)
        os.rmdir(temp_dir)

    def test_get_full_config(self, config_manager):
        """Test get_full_config method."""
        full_config = config_manager.get_full_config()

        assert "strategy" in full_config
        assert "risk" in full_config
        assert "system" in full_config
        assert "symbols" in full_config
        assert "notifications" in full_config

        # Verify risk config values
        assert full_config["risk"]["max_loss_percent"] == 1.0
        assert full_config["risk"]["max_leverage"] == 10

    def test_export_to_yaml(self, config_manager):
        """Test export_to_yaml method."""
        yaml_content = config_manager.export_to_yaml(include_strategies=True)

        assert isinstance(yaml_content, str)
        assert "risk_config" in yaml_content
        assert "system_config" in yaml_content
        assert "symbols" in yaml_content
        assert "exported_at" in yaml_content
        assert "version" in yaml_content

    def test_export_to_yaml_without_strategies(self, config_manager):
        """Test export_to_yaml without strategies."""
        yaml_content = config_manager.export_to_yaml(include_strategies=False)

        assert isinstance(yaml_content, str)
        assert "risk_config" in yaml_content
        assert "system_config" in yaml_content
        assert "symbols" in yaml_content


class TestConfigManagerImportPreview:
    """Test ConfigManager import preview functionality."""

    @pytest.fixture
    async def config_manager(self):
        """Create a ConfigManager instance with test database."""
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_config.db")

        with patch.dict(os.environ, {
            'EXCHANGE_API_KEY': 'test_key',
            'EXCHANGE_API_SECRET': 'test_secret',
        }):
            manager = ConfigManager(db_path)
            await manager.initialize()
            yield manager
            await manager.close()

        os.remove(db_path)
        os.rmdir(temp_dir)

    def test_import_preview_valid_yaml(self, config_manager):
        """Test import_preview with valid YAML."""
        yaml_content = """
risk_config:
  max_loss_percent: 0.02
  max_leverage: 20
system_config:
  history_bars: 200
"""
        result = config_manager.import_preview(yaml_content)

        assert result["valid"] is True
        assert len(result["errors"]) == 0
        assert len(result["changes"]) > 0

    def test_import_preview_invalid_yaml(self, config_manager):
        """Test import_preview with invalid YAML."""
        yaml_content = "invalid: yaml: content: ["

        result = config_manager.import_preview(yaml_content)

        assert result["valid"] is False
        assert len(result["errors"]) > 0

    def test_import_preview_risk_config_validation(self, config_manager):
        """Test risk config validation in preview."""
        yaml_content = """
risk_config:
  max_loss_percent: 10.0
"""
        result = config_manager.import_preview(yaml_content)

        # Should have error for invalid max_loss_percent (> 1)
        assert result["valid"] is False
        assert any("max_loss_percent" in str(e.get("field", "")) for e in result["errors"])

    def test_import_preview_system_config_validation(self, config_manager):
        """Test system config validation in preview."""
        yaml_content = """
system_config:
  history_bars: 5
"""
        result = config_manager.import_preview(yaml_content)

        # Should have error for invalid history_bars (< 10)
        assert result["valid"] is False
        assert any("history_bars" in str(e.get("field", "")) for e in result["errors"])

    def test_import_preview_symbols_validation(self, config_manager):
        """Test symbols validation in preview."""
        yaml_content = """
symbols:
  - symbol: "INVALID"
  - symbol: "BTC/USDT:USDT"
    is_core: true
"""
        result = config_manager.import_preview(yaml_content)

        # Should have error for invalid symbol format
        assert any("Invalid symbol format" in str(e.get("message", "")) for e in result["errors"])

    def test_import_preview_strategies_validation(self, config_manager):
        """Test strategies validation in preview."""
        yaml_content = """
strategies:
  - name: "Test Strategy"
    triggers:
      - type: "pinbar"
        params: {}
    filters:
      - type: "ema"
        period: 60
"""
        result = config_manager.import_preview(yaml_content)

        assert result["valid"] is True or len(result["errors"]) == 0

    def test_import_preview_notifications_validation(self, config_manager):
        """Test notifications validation in preview."""
        yaml_content = """
notifications:
  - type: "feishu"
    webhook_url: "https://example.com/webhook"
"""
        result = config_manager.import_preview(yaml_content)

        assert len(result["changes"]) > 0

    def test_import_preview_non_dict_yaml(self, config_manager):
        """Test import_preview with non-dictionary YAML."""
        yaml_content = "- item1\n- item2\n"

        result = config_manager.import_preview(yaml_content)

        assert result["valid"] is False
        assert any("dictionary" in str(e.get("message", "")).lower() for e in result["errors"])


class TestConfigManagerImportConfirm:
    """Test ConfigManager import confirm functionality."""

    @pytest.fixture
    async def config_manager(self):
        """Create a ConfigManager instance with test database."""
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_config.db")

        with patch.dict(os.environ, {
            'EXCHANGE_API_KEY': 'test_key',
            'EXCHANGE_API_SECRET': 'test_secret',
        }):
            manager = ConfigManager(db_path)
            await manager.initialize()
            yield manager
            await manager.close()

        os.remove(db_path)
        os.rmdir(temp_dir)

    @pytest.mark.asyncio
    async def test_import_confirm_invalid_preview(self, config_manager):
        """Test import_confirm with invalid preview."""
        yaml_content = "invalid: yaml: content: ["

        result = await config_manager.import_confirm(yaml_content)

        assert result["success"] is False
        assert "validation failed" in result["message"].lower() or "YAML parse error" in result["message"]

    @pytest.mark.asyncio
    async def test_import_confirm_risk_config(self, config_manager):
        """Test importing risk config."""
        yaml_content = """
risk_config:
  max_loss_percent: 0.5
  max_leverage: 20
"""
        result = await config_manager.import_confirm(yaml_content)

        assert result["success"] is True
        assert result["applied_changes"] > 0

        # Verify config was updated
        assert config_manager.risk_config.max_loss_percent == Decimal("0.5")
        assert config_manager.risk_config.max_leverage == 20

    @pytest.mark.asyncio
    async def test_import_confirm_system_config(self, config_manager):
        """Test importing system config."""
        yaml_content = """
system_config:
  history_bars: 200
  queue_batch_size: 20
"""
        result = await config_manager.import_confirm(yaml_content)

        assert result["success"] is True
        assert result["requires_restart"] is True  # System config requires restart

        # Verify config was updated
        assert config_manager.system_config.history_bars == 200

    @pytest.mark.asyncio
    async def test_import_confirm_symbols(self, config_manager):
        """Test importing symbols."""
        yaml_content = """
symbols:
  - symbol: "ETH/USDT:USDT"
    is_core: false
    is_enabled: true
"""
        result = await config_manager.import_confirm(yaml_content)

        assert result["success"] is True
        assert "ETH/USDT:USDT" in config_manager.symbols

    @pytest.mark.asyncio
    async def test_import_confirm_notifications(self, config_manager):
        """Test importing notifications."""
        yaml_content = """
notifications:
  - type: "feishu"
    webhook_url: "https://example.com/webhook"
    is_enabled: true
"""
        result = await config_manager.import_confirm(yaml_content)

        assert result["success"] is True
        assert len(config_manager.notifications) > 0


class TestConfigManagerEdgeCases:
    """Test ConfigManager edge cases and error handling."""

    @pytest.fixture
    async def config_manager(self):
        """Create a ConfigManager instance with test database."""
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_config.db")

        with patch.dict(os.environ, {
            'EXCHANGE_API_KEY': 'test_key',
            'EXCHANGE_API_SECRET': 'test_secret',
        }):
            manager = ConfigManager(db_path)
            await manager.initialize()
            yield manager
            await manager.close()

        os.remove(db_path)
        os.rmdir(temp_dir)

    @pytest.mark.asyncio
    async def test_reload_without_repo(self):
        """Test reload_config without initialized repository."""
        manager = ConfigManager()

        with pytest.raises(FatalStartupError):
            await manager.reload_config()

    @pytest.mark.asyncio
    async def test_load_all_without_repo(self):
        """Test load_all_from_db without initialized repository."""
        manager = ConfigManager()

        with pytest.raises(FatalStartupError):
            await manager.load_all_from_db()

    @pytest.mark.asyncio
    async def test_close_without_initialize(self):
        """Test close without initialize."""
        manager = ConfigManager()

        # Should not raise
        await manager.close()

    def test_get_full_config_without_data(self, config_manager):
        """Test get_full_config when data exists."""
        # This should work even with empty database
        full_config = config_manager.get_full_config()

        assert "strategy" in full_config
        assert "risk" in full_config


class TestLoadAllFromDb:
    """Test the load_all_from_db convenience function."""

    @pytest.mark.asyncio
    async def test_load_all_from_db_function(self):
        """Test the load_all_from_db convenience function."""
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_config.db")

        try:
            with patch.dict(os.environ, {
                'EXCHANGE_API_KEY': 'test_key',
                'EXCHANGE_API_SECRET': 'test_secret',
            }):
                with patch.object(ConfigManager, 'print_startup_info'):
                    manager = await load_all_from_db(db_path)

                assert manager is not None
                assert manager.risk_config is not None
                assert manager.system_config is not None

                await manager.close()
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)
            os.rmdir(temp_dir)


class TestSystemConfigModel:
    """Test SystemConfig Pydantic model."""

    def test_system_config_defaults(self):
        """Test SystemConfig default values."""
        config = SystemConfig()

        assert config.history_bars == 100
        assert config.queue_batch_size == 10
        assert config.queue_flush_interval == 5.0
        assert config.mtf_ema_period == 60
        assert config.cooldown_seconds == 14400

    def test_system_config_validation(self):
        """Test SystemConfig validation."""
        # Valid config
        config = SystemConfig(
            history_bars=200,
            queue_batch_size=20,
            queue_flush_interval=10.0,
        )
        assert config.history_bars == 200

        # Invalid history_bars (too low)
        with pytest.raises(Exception):
            SystemConfig(history_bars=10)

        # Invalid history_bars (too high)
        with pytest.raises(Exception):
            SystemConfig(history_bars=2000)

    def test_system_config_mtf_ema_period(self):
        """Test MTF EMA period config."""
        config = SystemConfig(mtf_ema_period=100)
        assert config.mtf_ema_period == 100

        # Invalid mtf_ema_period
        with pytest.raises(Exception):
            SystemConfig(mtf_ema_period=1)
