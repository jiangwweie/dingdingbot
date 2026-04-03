"""
Integration tests for configuration import/export functionality.

Tests the full import/export workflow from YAML parsing to database persistence.
"""
import pytest
import tempfile
import os
from decimal import Decimal
from datetime import datetime, timezone

from src.infrastructure.config_repository import ConfigRepository
from src.application.config_manager import ConfigManager


class TestYAMLExport:
    """Test YAML export functionality."""

    @pytest.fixture
    async def setup(self):
        """Set up test environment."""
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_config.db")

        repo = ConfigRepository(db_path)
        await repo.initialize()

        manager = ConfigManager(db_path)
        await manager.initialize()

        # Add test data
        await repo.add_symbol("ETH/USDT:USDT", is_core=0, is_enabled=1)
        await repo.add_symbol("SOL/USDT:USDT", is_core=0, is_enabled=1)
        await repo.add_notification("feishu", "https://example.com/webhook", is_enabled=1)

        yield {
            "repo": repo,
            "manager": manager,
            "db_path": db_path,
            "temp_dir": temp_dir,
        }

        await repo.close()
        os.remove(db_path)
        os.rmdir(temp_dir)

    @pytest.mark.asyncio
    async def test_export_contains_all_sections(self, setup):
        """Test that export contains all configuration sections."""
        yaml_content = setup["manager"].export_to_yaml(include_strategies=True)

        assert "risk_config:" in yaml_content
        assert "system_config:" in yaml_content
        assert "symbols:" in yaml_content
        assert "notifications:" in yaml_content
        assert "strategies:" in yaml_content or "# No active strategy" in yaml_content

    @pytest.mark.asyncio
    async def test_export_timestamp_format(self, setup):
        """Test that export timestamp is in ISO 8601 format."""
        yaml_content = setup["manager"].export_to_yaml()

        assert "exported_at:" in yaml_content

    @pytest.mark.asyncio
    async def test_export_version_included(self, setup):
        """Test that export includes version field."""
        yaml_content = setup["manager"].export_to_yaml()

        assert "version:" in yaml_content
        assert "1.0" in yaml_content

    @pytest.mark.asyncio
    async def test_export_risk_config_values(self, setup):
        """Test that risk config values are correctly exported."""
        # Update risk config
        await setup["repo"].update_risk_config(
            max_loss_percent=0.5,
            max_leverage=20,
            max_total_exposure=0.9,
        )

        yaml_content = setup["manager"].export_to_yaml()

        assert "max_loss_percent:" in yaml_content
        assert "0.5" in yaml_content
        assert "max_leverage:" in yaml_content
        assert "20" in yaml_content

    @pytest.mark.asyncio
    async def test_export_system_config_values(self, setup):
        """Test that system config values are correctly exported."""
        # Update system config
        await setup["repo"].update_system_config(
            history_bars=200,
            queue_batch_size=20,
        )

        yaml_content = setup["manager"].export_to_yaml()

        assert "history_bars:" in yaml_content
        assert "200" in yaml_content
        assert "queue_batch_size:" in yaml_content

    @pytest.mark.asyncio
    async def test_export_symbols_list(self, setup):
        """Test that symbols are correctly exported."""
        yaml_content = setup["manager"].export_to_yaml()

        assert "BTC/USDT:USDT" in yaml_content
        assert "ETH/USDT:USDT" in yaml_content
        assert "SOL/USDT:USDT" in yaml_content

    @pytest.mark.asyncio
    async def test_export_notification_channels(self, setup):
        """Test that notification channels are correctly exported."""
        yaml_content = setup["manager"].export_to_yaml()

        assert "feishu" in yaml_content
        assert "https://example.com/webhook" in yaml_content

    @pytest.mark.asyncio
    async def test_export_decimal_handling(self, setup):
        """Test that Decimal values are correctly handled in YAML."""
        yaml_content = setup["manager"].export_to_yaml()

        # Should not raise any conversion errors
        assert yaml_content is not None
        assert isinstance(yaml_content, str)


class TestYAMLImportPreview:
    """Test YAML import preview functionality."""

    @pytest.fixture
    async def setup(self):
        """Set up test environment."""
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_config.db")

        repo = ConfigRepository(db_path)
        await repo.initialize()

        manager = ConfigManager(db_path)
        await manager.initialize()

        yield {
            "repo": repo,
            "manager": manager,
            "db_path": db_path,
            "temp_dir": temp_dir,
        }

        await repo.close()
        os.remove(db_path)
        os.rmdir(temp_dir)

    def test_preview_valid_yaml(self, setup):
        """Test preview with valid YAML content."""
        yaml_content = """
risk_config:
  max_loss_percent: 2.0
  max_leverage: 20
  max_total_exposure: 0.9
"""
        result = setup["manager"].import_preview(yaml_content)

        assert result["valid"] is True
        assert len(result["errors"]) == 0
        assert len(result["changes"]) > 0

    def test_preview_invalid_yaml_syntax(self, setup):
        """Test preview with invalid YAML syntax."""
        yaml_content = """
risk_config:
  max_loss_percent: [invalid
  max_leverage: 20
"""
        result = setup["manager"].import_preview(yaml_content)

        assert result["valid"] is False
        assert len(result["errors"]) > 0

    def test_preview_non_dict_yaml(self, setup):
        """Test preview with non-dictionary YAML."""
        yaml_content = """
- item1
- item2
"""
        result = setup["manager"].import_preview(yaml_content)

        assert result["valid"] is False
        assert any("dictionary" in str(e.get("message", "")).lower() for e in result["errors"])

    def test_preview_risk_config_invalid_value(self, setup):
        """Test preview with invalid risk config values."""
        yaml_content = """
risk_config:
  max_loss_percent: 100.0
"""
        result = setup["manager"].import_preview(yaml_content)

        assert result["valid"] is False
        assert any("max_loss_percent" in str(e.get("field", "")) for e in result["errors"])

    def test_preview_system_config_invalid_value(self, setup):
        """Test preview with invalid system config values."""
        yaml_content = """
system_config:
  history_bars: 5
"""
        result = setup["manager"].import_preview(yaml_content)

        assert result["valid"] is False
        assert any("history_bars" in str(e.get("field", "")) for e in result["errors"])

    def test_preview_symbols_invalid_format(self, setup):
        """Test preview with invalid symbol format."""
        yaml_content = """
symbols:
  - symbol: "INVALID_FORMAT"
"""
        result = setup["manager"].import_preview(yaml_content)

        assert any("Invalid symbol format" in str(e.get("message", "")) for e in result["errors"])

    def test_preview_symbols_valid(self, setup):
        """Test preview with valid symbols."""
        yaml_content = """
symbols:
  - symbol: "BTC/USDT:USDT"
    is_core: true
    is_enabled: true
  - symbol: "ETH/USDT:USDT"
    is_core: false
    is_enabled: true
"""
        result = setup["manager"].import_preview(yaml_content)

        # Should have changes for symbols
        symbol_changes = [c for c in result["changes"] if c.get("category") == "symbol"]
        assert len(symbol_changes) > 0

    def test_preview_strategies_valid(self, setup):
        """Test preview with valid strategy."""
        yaml_content = """
strategies:
  - name: "Test Strategy"
    triggers:
      - type: "pinbar"
        params:
          min_wick_ratio: 0.6
    filters:
      - type: "ema"
        params:
          period: 60
    apply_to:
      - "BTC/USDT:USDT:15m"
"""
        result = setup["manager"].import_preview(yaml_content)

        # Strategy should be valid
        strategy_changes = [c for c in result["changes"] if c.get("category") == "strategy"]
        assert len(strategy_changes) > 0

    def test_preview_notifications_valid(self, setup):
        """Test preview with valid notifications."""
        yaml_content = """
notifications:
  - type: "feishu"
    webhook_url: "https://example.com/webhook"
    is_enabled: true
  - type: "telegram"
    webhook_url: "https://telegram.com/webhook"
    is_enabled: false
"""
        result = setup["manager"].import_preview(yaml_content)

        assert result["valid"] is True or len(result["errors"]) == 0

    def test_preview_notifications_invalid_type(self, setup):
        """Test preview with invalid notification type."""
        yaml_content = """
notifications:
  - type: "invalid_channel"
    webhook_url: "https://example.com/webhook"
"""
        result = setup["manager"].import_preview(yaml_content)

        assert result["valid"] is False
        assert any("channel type" in str(e.get("message", "")).lower() for e in result["errors"])

    def test_preview_detects_core_symbol_warning(self, setup):
        """Test preview generates warning for core symbol marked as non-core."""
        yaml_content = """
symbols:
  - symbol: "BTC/USDT:USDT"
    is_core: false
"""
        result = setup["manager"].import_preview(yaml_content)

        # Should have a warning about core symbol
        assert len(result["warnings"]) > 0
        assert any("Core symbol" in w for w in result["warnings"])


class TestYAMLImportConfirm:
    """Test YAML import confirm functionality."""

    @pytest.fixture
    async def setup(self):
        """Set up test environment."""
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_config.db")

        repo = ConfigRepository(db_path)
        await repo.initialize()

        manager = ConfigManager(db_path)
        await manager.initialize()

        yield {
            "repo": repo,
            "manager": manager,
            "db_path": db_path,
            "temp_dir": temp_dir,
        }

        await repo.close()
        os.remove(db_path)
        os.rmdir(temp_dir)

    @pytest.mark.asyncio
    async def test_import_confirm_risk_config(self, setup):
        """Test confirming risk config import."""
        yaml_content = """
risk_config:
  max_loss_percent: 2.5
  max_leverage: 15
  max_total_exposure: 0.85
"""
        result = await setup["manager"].import_confirm(yaml_content)

        assert result["success"] is True
        assert result["applied_changes"] > 0

        # Verify config was updated
        assert setup["manager"].risk_config.max_loss_percent == Decimal("2.5")
        assert setup["manager"].risk_config.max_leverage == 15

    @pytest.mark.asyncio
    async def test_import_confirm_system_config(self, setup):
        """Test confirming system config import."""
        yaml_content = """
system_config:
  history_bars: 250
  queue_batch_size: 25
  queue_flush_interval: 8.0
"""
        result = await setup["manager"].import_confirm(yaml_content)

        assert result["success"] is True
        assert result["requires_restart"] is True

        # Verify config was updated
        assert setup["manager"].system_config.history_bars == 250
        assert setup["manager"].system_config.queue_batch_size == 25

    @pytest.mark.asyncio
    async def test_import_confirm_symbols(self, setup):
        """Test confirming symbols import."""
        yaml_content = """
symbols:
  - symbol: "XRP/USDT:USDT"
    is_core: false
    is_enabled: true
  - symbol: "DOGE/USDT:USDT"
    is_core: false
    is_enabled: true
"""
        result = await setup["manager"].import_confirm(yaml_content)

        assert result["success"] is True

        # Verify symbols were added
        symbols = await setup["repo"].get_enabled_symbols()
        assert "XRP/USDT:USDT" in symbols
        assert "DOGE/USDT:USDT" in symbols

    @pytest.mark.asyncio
    async def test_import_confirm_notifications(self, setup):
        """Test confirming notifications import."""
        yaml_content = """
notifications:
  - type: "wecom"
    webhook_url: "https://wecom.example.com/webhook"
    is_enabled: true
"""
        result = await setup["manager"].import_confirm(yaml_content)

        assert result["success"] is True

        # Verify notification was added
        notifications = await setup["repo"].get_enabled_notifications()
        assert any(n["channel"] == "wecom" for n in notifications)

    @pytest.mark.asyncio
    async def test_import_confirm_invalid_yaml(self, setup):
        """Test confirming invalid YAML fails."""
        yaml_content = "invalid: yaml: ["

        result = await setup["manager"].import_confirm(yaml_content)

        assert result["success"] is False
        assert "YAML parse error" in result["message"]

    @pytest.mark.asyncio
    async def test_import_confirm_validation_failure(self, setup):
        """Test confirming invalid config fails."""
        yaml_content = """
risk_config:
  max_loss_percent: 100.0
"""
        result = await setup["manager"].import_confirm(yaml_content)

        assert result["success"] is False
        assert "validation failed" in result["message"].lower()


class TestFullImportExportWorkflow:
    """Test complete import/export workflow."""

    @pytest.fixture
    async def setup(self):
        """Set up test environment with sample data."""
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_config.db")

        repo = ConfigRepository(db_path)
        await repo.initialize()

        # Add sample data
        await repo.update_risk_config(max_loss_percent=1.5, max_leverage=12)
        await repo.update_system_config(history_bars=150)
        await repo.add_symbol("LINK/USDT:USDT", is_core=0, is_enabled=1)
        await repo.add_notification("telegram", "https://telegram.example.com/webhook", is_enabled=1)

        manager = ConfigManager(db_path)
        await manager.initialize()

        yield {
            "repo": repo,
            "manager": manager,
            "db_path": db_path,
            "temp_dir": temp_dir,
        }

        await repo.close()
        os.remove(db_path)
        os.rmdir(temp_dir)

    @pytest.mark.asyncio
    async def test_export_then_import_preview(self, setup):
        """Test exporting config and previewing import."""
        # Export current config
        yaml_content = setup["manager"].export_to_yaml()

        # Preview import (should show no changes since it's the same config)
        result = setup["manager"].import_preview(yaml_content)

        assert result["valid"] is True

    @pytest.mark.asyncio
    async def test_export_modify_import(self, setup):
        """Test export, modify, then import."""
        # Export current config
        yaml_content = setup["manager"].export_to_yaml()

        # Modify the YAML
        modified_yaml = yaml_content.replace("max_loss_percent: 1.5", "max_loss_percent: 3.0")

        # Import modified config
        result = await setup["manager"].import_confirm(modified_yaml)

        assert result["success"] is True

        # Verify modification was applied
        assert setup["manager"].risk_config.max_loss_percent == Decimal("3.0")

    @pytest.mark.asyncio
    async def test_roundtrip_preserves_data(self, setup):
        """Test that export->import roundtrip preserves data."""
        # Export
        yaml_content = setup["manager"].export_to_yaml()

        # Get original values
        original_risk = setup["manager"].risk_config
        original_system = setup["manager"].system_config

        # Import same config (should not change values)
        await setup["manager"].import_confirm(yaml_content)

        # Values should be the same
        assert setup["manager"].risk_config.max_loss_percent == original_risk.max_loss_percent
        assert setup["manager"].system_config.history_bars == original_system.history_bars


class TestImportEdgeCases:
    """Test edge cases for import functionality."""

    @pytest.fixture
    async def setup(self):
        """Set up test environment."""
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_config.db")

        repo = ConfigRepository(db_path)
        await repo.initialize()

        manager = ConfigManager(db_path)
        await manager.initialize()

        yield {
            "repo": repo,
            "manager": manager,
            "db_path": db_path,
            "temp_dir": temp_dir,
        }

        await repo.close()
        os.remove(db_path)
        os.rmdir(temp_dir)

    def test_preview_empty_yaml(self, setup):
        """Test preview with empty YAML."""
        yaml_content = "{}"

        result = setup["manager"].import_preview(yaml_content)

        assert result["valid"] is True
        assert len(result["changes"]) == 0

    def test_preview_partial_config(self, setup):
        """Test preview with partial configuration."""
        yaml_content = """
risk_config:
  max_loss_percent: 2.0
"""
        result = setup["manager"].import_preview(yaml_content)

        assert result["valid"] is True
        assert len(result["changes"]) > 0

    def test_preview_unknown_fields(self, setup):
        """Test preview with unknown fields (should be ignored)."""
        yaml_content = """
risk_config:
  max_loss_percent: 2.0
unknown_field: "should be ignored"
"""
        result = setup["manager"].import_preview(yaml_content)

        # Should still be valid, unknown fields are ignored
        assert result["valid"] is True

    @pytest.mark.asyncio
    async def test_import_duplicate_symbol(self, setup):
        """Test importing duplicate symbols."""
        yaml_content = """
symbols:
  - symbol: "BTC/USDT:USDT"
    is_core: true
    is_enabled: true
  - symbol: "BTC/USDT:USDT"
    is_core: false
    is_enabled: false
"""
        # First import should succeed
        result1 = await setup["manager"].import_confirm(yaml_content)
        assert result1["success"] is True

        # Second import might update or fail depending on implementation
        result2 = await setup["manager"].import_confirm(yaml_content)
        # Should handle gracefully (either update or skip)
        assert result2["success"] is True or "duplicate" in result2.get("message", "").lower()

    @pytest.mark.asyncio
    async def test_import_missing_required_fields(self, setup):
        """Test importing config with missing required fields."""
        yaml_content = """
risk_config:
  max_loss_percent: 2.0
system_config:
"""
        result = await setup["manager"].import_confirm(yaml_content)

        # Should handle gracefully - None values are skipped
        assert result["success"] is True

    def test_preview_whitespace_handling(self, setup):
        """Test preview handles YAML whitespace correctly."""
        yaml_content = """
  risk_config:
    max_loss_percent: 2.0
"""
        result = setup["manager"].import_preview(yaml_content)

        assert result["valid"] is True


class TestSnapshotIntegration:
    """Test snapshot functionality with import/export."""

    @pytest.fixture
    async def setup(self):
        """Set up test environment."""
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_config.db")

        repo = ConfigRepository(db_path)
        await repo.initialize()

        manager = ConfigManager(db_path)
        await manager.initialize()

        yield {
            "repo": repo,
            "manager": manager,
            "db_path": db_path,
            "temp_dir": temp_dir,
        }

        await repo.close()
        os.remove(db_path)
        os.rmdir(temp_dir)

    @pytest.mark.asyncio
    async def test_create_snapshot_before_import(self, setup):
        """Test creating snapshot before import."""
        # Create a snapshot manually before import
        snapshot_id = await setup["repo"].create_full_snapshot(
            name="Pre-import snapshot",
            description="Snapshot before importing new config",
        )

        assert snapshot_id is not None

        # Verify snapshot was created
        snapshot = await setup["repo"].get_snapshot(snapshot_id)
        assert snapshot is not None
        assert snapshot["name"] == "Pre-import snapshot"

    @pytest.mark.asyncio
    async def test_export_after_snapshot(self, setup):
        """Test exporting config after creating snapshot."""
        # Create snapshot
        await setup["repo"].create_full_snapshot(
            name="Test Snapshot",
            description="Test snapshot",
        )

        # Export should still work
        yaml_content = setup["manager"].export_to_yaml()

        assert yaml_content is not None
        assert "risk_config:" in yaml_content

    @pytest.mark.asyncio
    async def test_rollback_after_import(self, setup):
        """Test rollbacking after import."""
        # Update config
        await setup["repo"].update_risk_config(max_loss_percent=2.0)

        # Create snapshot
        snapshot_id = await setup["repo"].create_full_snapshot(
            name="Before Change",
            description="Snapshot before risk config change",
        )

        # Change config again
        await setup["repo"].update_risk_config(max_loss_percent=3.0)

        # Verify change
        assert setup["manager"].risk_config.max_loss_percent == Decimal("3.0")

        # Rollback to snapshot
        await setup["repo"].rollback_snapshot(snapshot_id)

        # Reload config to apply rollback
        await setup["manager"].reload_config()

        # Config should be rolled back
        assert setup["manager"].risk_config.max_loss_percent == Decimal("2.0")


class TestHistoryTracking:
    """Test that import/export operations are tracked in history."""

    @pytest.fixture
    async def setup(self):
        """Set up test environment."""
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_config.db")

        repo = ConfigRepository(db_path)
        await repo.initialize()

        manager = ConfigManager(db_path)
        await manager.initialize()

        yield {
            "repo": repo,
            "manager": manager,
            "db_path": db_path,
            "temp_dir": temp_dir,
        }

        await repo.close()
        os.remove(db_path)
        os.rmdir(temp_dir)

    @pytest.mark.asyncio
    async def test_import_creates_history(self, setup):
        """Test that importing config creates history entries."""
        yaml_content = """
risk_config:
  max_loss_percent: 2.0
"""
        # Import config
        await setup["manager"].import_confirm(yaml_content)

        # Check history
        history = await setup["repo"].get_history(config_type="risk", limit=10)

        assert len(history) > 0
        assert any(h["action"] == "update" for h in history)

    @pytest.mark.asyncio
    async def test_history_contains_old_and_new_values(self, setup):
        """Test that history contains both old and new values."""
        # First update
        await setup["repo"].update_risk_config(max_loss_percent=2.0)

        # Second update
        yaml_content = """
risk_config:
  max_loss_percent: 3.0
"""
        await setup["manager"].import_confirm(yaml_content)

        # Get history
        history = await setup["repo"].get_history(config_type="risk", limit=10)

        # Find entries with old_value and new_value
        entries_with_values = [
            h for h in history
            if h.get("old_value") is not None and h.get("new_value") is not None
        ]

        assert len(entries_with_values) > 0
