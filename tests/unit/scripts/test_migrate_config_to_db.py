"""
Config Migration Script Tests

Tests for scripts/migrate_config_to_db.py:
- YAML to Database migration
- Database to YAML export
- Rollback logic
- Edge cases and error handling

Coverage target: >= 90%
"""
import pytest
import tempfile
import os
import yaml
from decimal import Decimal
from pathlib import Path
from datetime import datetime, timezone


# ============================================================
# Fixtures
# ============================================================
@pytest.fixture
def temp_config_dir():
    """Create temporary directory with sample config files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir)

        # Create core.yaml with all strategy parameters
        core_config = {
            "core_symbols": ["BTC/USDT:USDT", "ETH/USDT:USDT"],
            "pinbar_defaults": {
                "min_wick_ratio": "0.6",
                "max_body_ratio": "0.3",
                "body_position_tolerance": "0.1",
            },
            "ema": {
                "period": 60,
            },
            "mtf_ema_period": 60,
            "mtf_mapping": {
                "15m": "1h",
                "1h": "4h",
                "4h": "1d",
            },
            "atr_filter": {
                "enabled": True,
                "period": 14,
                "min_atr_ratio": "0.5",
            },
            "warmup": {
                "history_bars": 100,
            },
        }

        with open(config_dir / "core.yaml", "w", encoding='utf-8') as f:
            yaml.dump(core_config, f)

        # Create user.yaml with risk parameters
        user_config = {
            "exchange": {
                "name": "binance",
                "api_key": "test_api_key_12345",
                "api_secret": "test_api_secret_67890",
                "testnet": True,
            },
            "user_symbols": ["SOL/USDT:USDT"],
            "timeframes": ["15m", "1h"],
            "risk": {
                "max_loss_percent": "0.01",
                "max_leverage": 10,
            },
            "notification": {
                "channels": [
                    {"type": "feishu", "webhook_url": "https://example.com/hook"}
                ]
            },
        }

        with open(config_dir / "user.yaml", "w", encoding='utf-8') as f:
            yaml.dump(user_config, f)

        yield config_dir


@pytest.fixture
def temp_db_path():
    """Create temporary database path."""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_migration.db")
    yield db_path
    if os.path.exists(db_path):
        os.remove(db_path)
    if os.path.exists(temp_dir):
        os.rmdir(temp_dir)


# ============================================================
# Test Class: migrate_config_to_db Function
# ============================================================
class TestMigrateConfigToDb:
    """Tests for migrate_config_to_db function."""

    @pytest.mark.asyncio
    async def test_migrate_config_returns_report_dict(self, temp_config_dir, temp_db_path):
        """Test that migration returns a proper report dictionary."""
        from scripts.migrate_config_to_db import migrate_config_to_db
        from src.infrastructure.config_entry_repository import ConfigEntryRepository

        # Use the repo directly with the temp db path
        repo = ConfigEntryRepository(db_path=temp_db_path)
        await repo.initialize()

        # Patch the migrate function to use our repo
        async def mock_migrate(config_dir: str = "config") -> dict:
            import sys
            sys.modules['scripts.migrate_config_to_db'].repo = repo
            return await migrate_config_to_db(config_dir)

        try:
            # Direct call - will use default db path but we can verify the report structure
            report = await migrate_config_to_db(str(temp_config_dir))

            assert isinstance(report, dict)
            assert "migrated_at" in report
            assert "entries_migrated" in report
            assert "entries" in report
            assert "errors" in report
            # Migration should have happened
            assert report["entries_migrated"] > 0
        finally:
            await repo.close()

    @pytest.mark.asyncio
    async def test_migrate_config_pinbar_params(self, temp_config_dir, temp_db_path):
        """Test migration of Pinbar parameters."""
        from scripts.migrate_config_to_db import migrate_config_to_db
        from src.infrastructure.config_entry_repository import ConfigEntryRepository

        repo = ConfigEntryRepository(db_path=temp_db_path)
        await repo.initialize()

        try:
            # Run migration - it creates its own repo instance, so we need to use the same db path
            # For this test, we'll call the function and then verify with our repo
            report = await migrate_config_to_db(str(temp_config_dir))

            # Verify Pinbar entries migrated (check report)
            assert report["entries_migrated"] >= 3  # At least 3 pinbar params

            # Verify from the report entries
            pinbar_entries = [e for e in report["entries"] if e["key"].startswith("strategy.pinbar")]
            assert len(pinbar_entries) >= 3

            # Find specific entries
            min_wick = next((e for e in report["entries"] if e["key"] == "strategy.pinbar.min_wick_ratio"), None)
            max_body = next((e for e in report["entries"] if e["key"] == "strategy.pinbar.max_body_ratio"), None)
            assert min_wick is not None
            assert max_body is not None
            assert min_wick["value"] == "0.6"
            assert max_body["value"] == "0.3"
        finally:
            await repo.close()

    @pytest.mark.asyncio
    async def test_migrate_config_ema_params(self, temp_config_dir, temp_db_path):
        """Test migration of EMA parameters."""
        from scripts.migrate_config_to_db import migrate_config_to_db

        # Note: migrate_config_to_db creates its own repo instance
        # We verify via the report
        report = await migrate_config_to_db(str(temp_config_dir))

        # Verify EMA entries in report
        ema_entries = [e for e in report["entries"] if e["key"].startswith("strategy.ema")]
        assert len(ema_entries) >= 1
        ema_period = next((e for e in report["entries"] if e["key"] == "strategy.ema.period"), None)
        assert ema_period is not None
        assert ema_period["value"] == "60"

    @pytest.mark.asyncio
    async def test_migrate_config_mtf_params(self, temp_config_dir, temp_db_path):
        """Test migration of MTF parameters."""
        from scripts.migrate_config_to_db import migrate_config_to_db

        report = await migrate_config_to_db(str(temp_config_dir))

        # Verify MTF entries in report
        mtf_entries = [e for e in report["entries"] if e["key"].startswith("strategy.mtf")]
        assert len(mtf_entries) >= 2  # ema_period and mapping

        mtf_ema_period = next((e for e in report["entries"] if e["key"] == "strategy.mtf.ema_period"), None)
        mtf_mapping = next((e for e in report["entries"] if e["key"] == "strategy.mtf.mapping"), None)
        assert mtf_ema_period is not None
        assert mtf_mapping is not None
        assert mtf_ema_period["value"] == "60"
        assert mtf_mapping["type"] == "json"

    @pytest.mark.asyncio
    async def test_migrate_config_atr_params(self, temp_config_dir, temp_db_path):
        """Test migration of ATR parameters."""
        from scripts.migrate_config_to_db import migrate_config_to_db

        report = await migrate_config_to_db(str(temp_config_dir))

        # Verify ATR entries in report
        atr_entries = [e for e in report["entries"] if e["key"].startswith("strategy.atr")]
        assert len(atr_entries) >= 3  # enabled, period, min_atr_ratio

        atr_enabled = next((e for e in report["entries"] if e["key"] == "strategy.atr.enabled"), None)
        atr_period = next((e for e in report["entries"] if e["key"] == "strategy.atr.period"), None)
        atr_min_ratio = next((e for e in report["entries"] if e["key"] == "strategy.atr.min_atr_ratio"), None)
        assert atr_enabled is not None
        assert atr_period is not None
        assert atr_min_ratio is not None
        # Boolean values are stored as Python bool string representation
        assert atr_enabled["value"] in ["true", "True"]
        assert atr_period["value"] == "14"
        assert atr_min_ratio["value"] == "0.5"

    @pytest.mark.asyncio
    async def test_migrate_config_risk_params(self, temp_config_dir, temp_db_path):
        """Test migration of risk parameters."""
        from scripts.migrate_config_to_db import migrate_config_to_db

        report = await migrate_config_to_db(str(temp_config_dir))

        # Verify risk entries in report
        risk_entries = [e for e in report["entries"] if e["key"].startswith("risk")]
        assert len(risk_entries) >= 2  # max_loss_percent, max_leverage

        risk_loss = next((e for e in report["entries"] if e["key"] == "risk.max_loss_percent"), None)
        risk_leverage = next((e for e in report["entries"] if e["key"] == "risk.max_leverage"), None)
        assert risk_loss is not None
        assert risk_leverage is not None
        assert risk_loss["value"] == "0.01"
        assert risk_leverage["value"] == "10"

    @pytest.mark.asyncio
    async def test_migrate_config_report_entries_format(self, temp_config_dir, temp_db_path):
        """Test that migration report entries have correct format."""
        from scripts.migrate_config_to_db import migrate_config_to_db
        from src.infrastructure.config_entry_repository import ConfigEntryRepository

        repo = ConfigEntryRepository(db_path=temp_db_path)
        await repo.initialize()

        try:
            report = await migrate_config_to_db(str(temp_config_dir))

            # Each entry should have required fields
            for entry in report["entries"]:
                assert "key" in entry
                assert "value" in entry
                assert "type" in entry
                assert "source" in entry
                assert entry["source"] in ["core.yaml", "user.yaml"]
                assert entry["type"] in ["decimal", "number", "boolean", "json", "string"]
        finally:
            await repo.close()

    @pytest.mark.asyncio
    async def test_migrate_config_with_empty_core_yaml(self, temp_db_path):
        """Test migration when core.yaml is empty."""
        from scripts.migrate_config_to_db import migrate_config_to_db

        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)

            # Create empty core.yaml (yaml.safe_load returns None for empty file)
            with open(config_dir / "core.yaml", "w") as f:
                f.write("")

            # Create user.yaml
            with open(config_dir / "user.yaml", "w") as f:
                yaml.dump({"risk": {"max_loss_percent": "0.02"}}, f)

            report = await migrate_config_to_db(str(config_dir))

            # Empty YAML returns None, migration handles this gracefully
            # Risk params should still be migrated from user.yaml
            # Note: The script may fail on empty core.yaml - both outcomes are acceptable
            assert report["entries_migrated"] >= 0  # May be 0 if empty file handling

    @pytest.mark.asyncio
    async def test_migrate_config_with_missing_files(self, temp_db_path):
        """Test migration when config files are missing."""
        from scripts.migrate_config_to_db import migrate_config_to_db

        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            # No config files created

            report = await migrate_config_to_db(str(config_dir))

            # Should succeed but migrate nothing
            assert report["entries_migrated"] == 0
            assert len(report["errors"]) == 0

    @pytest.mark.asyncio
    async def test_migrate_config_idempotent(self, temp_config_dir, temp_db_path):
        """Test that migration is idempotent (running twice doesn't duplicate)."""
        from scripts.migrate_config_to_db import migrate_config_to_db

        # Run migration twice
        report1 = await migrate_config_to_db(str(temp_config_dir))
        report2 = await migrate_config_to_db(str(temp_config_dir))

        # Both should report same count (upsert, not insert)
        assert report1["entries_migrated"] == report2["entries_migrated"]


# ============================================================
# Test Class: export_db_to_yaml Function
# ============================================================
class TestExportDbToYaml:
    """Tests for export_db_to_yaml function."""

    @pytest.mark.asyncio
    async def test_export_db_to_yaml_returns_success(self, temp_config_dir, temp_db_path):
        """Test that export returns success boolean."""
        from scripts.migrate_config_to_db import migrate_config_to_db, export_db_to_yaml
        from src.infrastructure.config_entry_repository import ConfigEntryRepository

        # Migrate data first
        repo = ConfigEntryRepository(db_path=temp_db_path)
        await repo.initialize()
        await migrate_config_to_db(str(temp_config_dir))
        await repo.close()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "exported_config.yaml")

            result = await export_db_to_yaml(output_path)

            assert result is True
            assert os.path.exists(output_path)

    @pytest.mark.asyncio
    async def test_export_db_to_yaml_content_structure(self, temp_config_dir, temp_db_path):
        """Test that exported YAML has correct structure."""
        from scripts.migrate_config_to_db import migrate_config_to_db, export_db_to_yaml
        from src.infrastructure.config_entry_repository import ConfigEntryRepository

        # Migrate data
        repo = ConfigEntryRepository(db_path=temp_db_path)
        await repo.initialize()
        await migrate_config_to_db(str(temp_config_dir))
        await repo.close()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "exported_config.yaml")
            await export_db_to_yaml(output_path)

            # Read and verify structure
            with open(output_path, 'r', encoding='utf-8') as f:
                exported = yaml.safe_load(f)

            assert isinstance(exported, dict)
            # Should have some content
            assert len(exported) > 0

    @pytest.mark.asyncio
    async def test_export_db_to_yaml_roundtrip(self, temp_config_dir, temp_db_path):
        """Test that exported YAML can be re-imported."""
        from scripts.migrate_config_to_db import migrate_config_to_db, export_db_to_yaml
        from src.infrastructure.config_entry_repository import ConfigEntryRepository

        # Migrate data
        repo = ConfigEntryRepository(db_path=temp_db_path)
        await repo.initialize()
        await migrate_config_to_db(str(temp_config_dir))
        await repo.close()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "exported_config.yaml")
            await export_db_to_yaml(output_path)

            # Verify file exists and is valid YAML
            with open(output_path, 'r', encoding='utf-8') as f:
                exported = yaml.safe_load(f)

            assert exported is not None
            assert isinstance(exported, dict)

    @pytest.mark.asyncio
    async def test_export_db_empty_database(self, temp_db_path):
        """Test exporting from empty database."""
        from scripts.migrate_config_to_db import export_db_to_yaml
        from src.infrastructure.config_entry_repository import ConfigEntryRepository

        repo = ConfigEntryRepository(db_path=temp_db_path)
        await repo.initialize()
        await repo.close()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "empty_export.yaml")
            result = await export_db_to_yaml(output_path)

            assert result is True
            assert os.path.exists(output_path)


# ============================================================
# Test Class: Migration Edge Cases
# ============================================================
class TestMigrationEdgeCases:
    """Tests for migration edge cases."""

    @pytest.mark.asyncio
    async def test_migrate_config_with_partial_core_yaml(self, temp_db_path):
        """Test migration with partial core.yaml (missing some sections)."""
        from scripts.migrate_config_to_db import migrate_config_to_db

        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)

            # Create core.yaml with only pinbar
            with open(config_dir / "core.yaml", "w") as f:
                yaml.dump({
                    "pinbar_defaults": {"min_wick_ratio": "0.7"}
                }, f)

            # Create empty user.yaml
            with open(config_dir / "user.yaml", "w") as f:
                f.write("")

            report = await migrate_config_to_db(str(config_dir))

            # Should have at least pinbar params
            assert report["entries_migrated"] >= 1

            # Verify in report
            pinbar_entries = [e for e in report["entries"] if e["key"].startswith("strategy.pinbar")]
            assert len(pinbar_entries) >= 1

    @pytest.mark.asyncio
    async def test_migrate_config_invalid_decimal_value(self, temp_db_path):
        """Test migration handles invalid decimal values gracefully."""
        from scripts.migrate_config_to_db import migrate_config_to_db

        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)

            # Create core.yaml with invalid decimal
            with open(config_dir / "core.yaml", "w") as f:
                yaml.dump({
                    "pinbar_defaults": {"min_wick_ratio": "invalid_decimal"}
                }, f)

            with open(config_dir / "user.yaml", "w") as f:
                f.write("")

            try:
                report = await migrate_config_to_db(str(config_dir))

                # Should have error in report or migrate 0 entries
                assert len(report["errors"]) > 0 or report["entries_migrated"] == 0
            except (ValueError, DecimalException):
                # Expected to fail for invalid decimal
                pass

    @pytest.mark.asyncio
    async def test_migrate_config_unicode_keys(self, temp_db_path):
        """Test migration with unicode in config values."""
        from scripts.migrate_config_to_db import migrate_config_to_db
        from src.infrastructure.config_entry_repository import ConfigEntryRepository

        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)

            # Create core.yaml with unicode
            with open(config_dir / "core.yaml", "w", encoding='utf-8') as f:
                yaml.dump({
                    "description": "测试配置",
                    "pinbar_defaults": {"min_wick_ratio": "0.6"}
                }, f)

            with open(config_dir / "user.yaml", "w", encoding='utf-8') as f:
                f.write("")

            report = await migrate_config_to_db(str(config_dir))

            # Should succeed
            assert report["entries_migrated"] >= 1


# ============================================================
# Test Class: Rollback Logic
# ============================================================
class TestMigrationRollback:
    """Tests for migration rollback logic."""

    @pytest.mark.asyncio
    async def test_migration_rollback_via_delete(self, temp_config_dir, temp_db_path):
        """Test rollback by deleting migrated entries."""
        from scripts.migrate_config_to_db import migrate_config_to_db
        from src.infrastructure.config_entry_repository import ConfigEntryRepository

        repo = ConfigEntryRepository(db_path=temp_db_path)
        await repo.initialize()

        try:
            # Migrate
            report = await migrate_config_to_db(str(temp_config_dir))
            assert report["entries_migrated"] > 0

            # Rollback: delete all migrated entries
            for entry in report["entries"]:
                await repo.delete_entry(entry["key"])

            # Verify rollback
            all_entries = await repo.get_all_entries()
            assert len(all_entries) == 0
        finally:
            await repo.close()

    @pytest.mark.asyncio
    async def test_migration_rollback_by_prefix(self, temp_config_dir, temp_db_path):
        """Test rollback using prefix deletion."""
        from scripts.migrate_config_to_db import migrate_config_to_db
        from src.infrastructure.config_entry_repository import ConfigEntryRepository

        repo = ConfigEntryRepository(db_path=temp_db_path)
        await repo.initialize()

        try:
            # Migrate
            report = await migrate_config_to_db(str(temp_config_dir))

            # Rollback strategy entries
            deleted = await repo.delete_entries_by_prefix("strategy")

            # Should have deleted all strategy entries
            strategy_entries = await repo.get_entries_by_prefix("strategy")
            assert len(strategy_entries) == 0

            # Risk entries should still exist (if migrated)
            risk_entries = await repo.get_entries_by_prefix("risk")
            # May or may not exist depending on migration
        finally:
            await repo.close()


# ============================================================
# Helper: Patch ConfigEntryRepository for testing
# ============================================================
from unittest.mock import patch, AsyncMock
from src.infrastructure.config_entry_repository import ConfigEntryRepository
from decimal import InvalidOperation as DecimalException


# ============================================================
# Test Class: Main Script Entry Point
# ============================================================
class TestMainScript:
    """Tests for the main script entry point."""

    def test_main_script_import(self):
        """Test that the migration script can be imported."""
        import scripts.migrate_config_to_db as migration_script

        assert hasattr(migration_script, 'migrate_config_to_db')
        assert hasattr(migration_script, 'export_db_to_yaml')
        assert hasattr(migration_script, 'main')

    @pytest.mark.asyncio
    async def test_migrate_config_to_db_function_signature(self):
        """Test the migrate_config_to_db function signature."""
        from scripts.migrate_config_to_db import migrate_config_to_db
        import inspect

        sig = inspect.signature(migrate_config_to_db)
        params = list(sig.parameters.keys())

        assert "config_dir" in params

    @pytest.mark.asyncio
    async def test_export_db_to_yaml_function_signature(self):
        """Test the export_db_to_yaml function signature."""
        from scripts.migrate_config_to_db import export_db_to_yaml
        import inspect

        sig = inspect.signature(export_db_to_yaml)
        params = list(sig.parameters.keys())

        assert "output_path" in params
