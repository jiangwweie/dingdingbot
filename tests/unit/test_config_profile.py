"""
Tests for Config Profile Repository and Service.

配置 Profile 管理单元测试
"""
import pytest
import asyncio
import os
from pathlib import Path
from datetime import datetime, timezone

from src.infrastructure.config_profile_repository import ConfigProfileRepository, ProfileInfo
from src.infrastructure.config_entry_repository import ConfigEntryRepository
from src.application.config_profile_service import ConfigProfileService, ProfileDiff


# Test database paths
TEST_DB_PATH = "data/test_profiles.db"
TEST_CONFIG_DB_PATH = "data/test_config_entries.db"


@pytest.fixture
async def profile_repo():
    """Fixture: Create and initialize profile repository"""
    from src.infrastructure.connection_pool import close_all_connections

    # Ensure test directory exists
    Path("data").mkdir(exist_ok=True)

    await close_all_connections()

    # Remove test database if exists
    for path in [TEST_DB_PATH, TEST_DB_PATH + "-wal", TEST_DB_PATH + "-shm"]:
        if os.path.exists(path):
            os.remove(path)

    repo = ConfigProfileRepository(db_path=TEST_DB_PATH)

    # Manually create tables for testing
    import aiosqlite
    async with aiosqlite.connect(TEST_DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")

        # Create config_profiles table
        await db.execute("""
            CREATE TABLE config_profiles (
                name            TEXT PRIMARY KEY,
                description     TEXT,
                is_active       BOOLEAN NOT NULL DEFAULT FALSE,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL,
                created_from    TEXT
            )
        """)

        # Create config_entries_v2 table with profile_name
        # Note: UNIQUE constraint is on (profile_name, config_key) combination, not config_key alone
        await db.execute("""
            CREATE TABLE config_entries_v2 (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                config_key    VARCHAR(128) NOT NULL,
                config_value  TEXT NOT NULL,
                value_type    VARCHAR(16) NOT NULL,
                version       VARCHAR(32) NOT NULL DEFAULT 'v1.0.0',
                updated_at    BIGINT NOT NULL,
                profile_name  TEXT NOT NULL DEFAULT 'default'
            )
        """)

        # Create composite unique index
        await db.execute("""
            CREATE UNIQUE INDEX idx_config_profile_key
            ON config_entries_v2(profile_name, config_key)
        """)

        # Insert default profile
        now = datetime.now(timezone.utc).isoformat()
        await db.execute("""
            INSERT INTO config_profiles (name, description, is_active, created_at, updated_at, created_from)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("default", "默认配置档案", True, now, now, "system"))

        await db.commit()

    await repo.initialize()
    yield repo
    await repo.close()
    await close_all_connections()

    # Cleanup
    for path in [TEST_DB_PATH, TEST_DB_PATH + "-wal", TEST_DB_PATH + "-shm"]:
        if os.path.exists(path):
            os.remove(path)


@pytest.fixture
async def config_entry_repo():
    """Fixture: Create and initialize config entry repository with profile support"""
    from src.infrastructure.connection_pool import close_all_connections

    Path("data").mkdir(exist_ok=True)

    await close_all_connections()

    # Use separate DB for config entries
    for path in [TEST_CONFIG_DB_PATH, TEST_CONFIG_DB_PATH + "-wal", TEST_CONFIG_DB_PATH + "-shm"]:
        if os.path.exists(path):
            os.remove(path)

    repo = ConfigEntryRepository(db_path=TEST_CONFIG_DB_PATH)
    await repo.initialize()

    # Add profile_name column and composite index (for testing)
    import aiosqlite
    async with aiosqlite.connect(TEST_CONFIG_DB_PATH) as db:
        # Remove the original unique index on config_key
        await db.execute("DROP INDEX IF EXISTS idx_config_entries_v2_key")
        # Add profile_name column if not exists
        try:
            await db.execute("ALTER TABLE config_entries_v2 ADD COLUMN profile_name TEXT NOT NULL DEFAULT 'default'")
        except Exception:
            pass  # Column might already exist
        # Create composite unique index
        await db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_config_profile_key
            ON config_entries_v2(profile_name, config_key)
        """)
        await db.commit()

    yield repo
    await repo.close()
    await close_all_connections()

    # Cleanup
    for path in [TEST_CONFIG_DB_PATH, TEST_CONFIG_DB_PATH + "-wal", TEST_CONFIG_DB_PATH + "-shm"]:
        if os.path.exists(path):
            os.remove(path)


@pytest.fixture
async def profile_service(profile_repo):
    """Fixture: Create profile service

    Note: We use the same database for both profile_repo and config_entry_repo
    """
    # Create config repo using the same database
    config_repo = ConfigEntryRepository(db_path=TEST_DB_PATH)

    # Drop the existing table and recreate with correct schema
    import aiosqlite
    async with aiosqlite.connect(TEST_DB_PATH) as db:
        # Drop the original unique index on config_key
        await db.execute("DROP INDEX IF EXISTS idx_config_entries_v2_key")
        # Create composite unique index if not exists
        await db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_config_profile_key
            ON config_entries_v2(profile_name, config_key)
        """)
        await db.commit()

    await config_repo.initialize()

    service = ConfigProfileService(profile_repo, config_repo)
    yield service

    await config_repo.close()
    from src.infrastructure.connection_pool import close_all_connections

    await close_all_connections()


# ============================================================
# ConfigProfileRepository Tests
# ============================================================

class TestConfigProfileRepository:
    """Tests for ConfigProfileRepository"""

    @pytest.mark.asyncio
    async def test_list_profiles_initial(self, profile_repo):
        """Test listing profiles - should have default profile"""
        profiles = await profile_repo.list_profiles()

        assert len(profiles) == 1
        assert profiles[0].name == "default"
        assert profiles[0].is_active is True
        assert profiles[0].config_count == 0

    @pytest.mark.asyncio
    async def test_create_profile(self, profile_repo):
        """Test creating a new profile"""
        profile = await profile_repo.create_profile(
            name="conservative",
            description="保守型配置"
        )

        assert profile.name == "conservative"
        assert profile.description == "保守型配置"
        assert profile.is_active is False

        # Verify in list
        profiles = await profile_repo.list_profiles()
        assert len(profiles) == 2

    @pytest.mark.asyncio
    async def test_create_profile_duplicate_name(self, profile_repo):
        """Test creating profile with duplicate name raises error"""
        await profile_repo.create_profile(name="test", description="Test profile")

        with pytest.raises(ValueError, match="已存在"):
            await profile_repo.create_profile(name="test", description="Duplicate")

    @pytest.mark.asyncio
    async def test_create_profile_copy_from(self, profile_repo):
        """Test creating profile by copying from another"""
        # First, add some config to default profile directly via SQL
        import aiosqlite
        now = int(datetime.now(timezone.utc).timestamp() * 1000)
        async with aiosqlite.connect(TEST_DB_PATH) as db:
            await db.execute("""
                INSERT INTO config_entries_v2 (config_key, config_value, value_type, version, updated_at, profile_name)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ("strategy.pinbar.min_wick_ratio", "0.6", "decimal", "v1.0.0", now, "default"))
            await db.execute("""
                INSERT INTO config_entries_v2 (config_key, config_value, value_type, version, updated_at, profile_name)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ("risk.max_loss_percent", "1.0", "decimal", "v1.0.0", now, "default"))
            await db.commit()

        # Create profile copying from default
        profile = await profile_repo.create_profile(
            name="copy_test",
            description="Copied profile",
            copy_from="default"
        )

        # Verify configs were copied
        configs = await profile_repo.get_profile_configs("copy_test")
        assert len(configs) == 2
        assert float(configs["strategy.pinbar.min_wick_ratio"]) == 0.6
        assert float(configs["risk.max_loss_percent"]) == 1.0

    @pytest.mark.asyncio
    async def test_activate_profile(self, profile_repo):
        """Test activating a profile"""
        # Create new profile
        await profile_repo.create_profile(name="active_test", description="Test")

        # Activate it
        await profile_repo.activate_profile("active_test")

        # Verify active profile
        active = await profile_repo.get_active_profile()
        assert active.name == "active_test"
        assert active.is_active is True

        # Verify default is no longer active
        profiles = await profile_repo.list_profiles()
        default_profile = [p for p in profiles if p.name == "default"][0]
        assert default_profile.is_active is False

    @pytest.mark.asyncio
    async def test_activate_nonexistent_profile(self, profile_repo):
        """Test activating non-existent profile raises error"""
        with pytest.raises(ValueError, match="不存在"):
            await profile_repo.activate_profile("nonexistent")

    @pytest.mark.asyncio
    async def test_delete_profile(self, profile_repo):
        """Test deleting a profile"""
        # Create profile
        await profile_repo.create_profile(name="to_delete", description="To delete")

        # Delete it
        success = await profile_repo.delete_profile("to_delete")
        assert success is True

        # Verify deleted
        profiles = await profile_repo.list_profiles()
        assert len(profiles) == 1  # Only default remains

    @pytest.mark.asyncio
    async def test_delete_default_profile_forbidden(self, profile_repo):
        """Test deleting default profile is forbidden"""
        with pytest.raises(ValueError, match="不能删除 default"):
            await profile_repo.delete_profile("default")

    @pytest.mark.asyncio
    async def test_delete_active_profile_forbidden(self, profile_repo):
        """Test deleting active profile is forbidden"""
        # Create and activate profile
        await profile_repo.create_profile(name="active_to_delete", description="Test")
        await profile_repo.activate_profile("active_to_delete")

        # Try to delete
        with pytest.raises(ValueError, match="不能删除当前激活"):
            await profile_repo.delete_profile("active_to_delete")

    @pytest.mark.asyncio
    async def test_get_profile_configs(self, profile_repo):
        """Test getting profile configurations"""
        # Add configs directly via SQL
        import aiosqlite
        now = int(datetime.now(timezone.utc).timestamp() * 1000)
        async with aiosqlite.connect(TEST_DB_PATH) as db:
            await db.execute("""
                INSERT INTO config_entries_v2 (config_key, config_value, value_type, version, updated_at, profile_name)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ("strategy.ema.period", "50", "number", "v1.0.0", now, "default"))
            await db.execute("""
                INSERT INTO config_entries_v2 (config_key, config_value, value_type, version, updated_at, profile_name)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ("risk.max_loss_percent", "1.0", "decimal", "v1.0.0", now, "default"))
            await db.commit()

        configs = await profile_repo.get_profile_configs("default")
        assert len(configs) == 2
        assert configs["strategy.ema.period"] == 50


# ============================================================
# ConfigProfileService Tests
# ============================================================

class TestConfigProfileService:
    """Tests for ConfigProfileService"""

    @pytest.mark.asyncio
    async def test_list_profiles(self, profile_service):
        """Test listing profiles via service"""
        profiles = await profile_service.list_profiles()

        assert len(profiles) == 1
        assert profiles[0].name == "default"

    @pytest.mark.asyncio
    async def test_create_profile(self, profile_service):
        """Test creating profile via service"""
        profile = await profile_service.create_profile(
            name="service_test",
            description="Created via service"
        )

        assert profile.name == "service_test"
        assert profile.description == "Created via service"

    @pytest.mark.asyncio
    async def test_create_and_switch(self, profile_service):
        """Test creating profile and switching immediately"""
        profile = await profile_service.create_profile(
            name="switch_test",
            description="Switch test",
            switch_immediately=True
        )

        active = await profile_service.get_active_profile()
        assert active.name == "switch_test"

    @pytest.mark.asyncio
    async def test_switch_profile_returns_diff(self, profile_service, profile_repo):
        """Test switching profile returns configuration diff"""
        # Add config to default via SQL
        import aiosqlite
        now = int(datetime.now(timezone.utc).timestamp() * 1000)
        async with aiosqlite.connect(TEST_DB_PATH) as db:
            await db.execute("""
                INSERT INTO config_entries_v2 (config_key, config_value, value_type, version, updated_at, profile_name)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ("strategy.pinbar.min_wick_ratio", "0.6", "decimal", "v1.0.0", now, "default"))
            await db.execute("""
                INSERT INTO config_entries_v2 (config_key, config_value, value_type, version, updated_at, profile_name)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ("risk.max_loss_percent", "1.0", "decimal", "v1.0.0", now, "default"))
            await db.commit()

        # Create new profile with different config
        await profile_repo.create_profile(name="diff_test", description="Diff test")

        # Add different configs for diff_test
        async with aiosqlite.connect(TEST_DB_PATH) as db:
            await db.execute("""
                INSERT INTO config_entries_v2 (config_key, config_value, value_type, version, updated_at, profile_name)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ("strategy.pinbar.min_wick_ratio", "0.5", "decimal", "v1.0.0", now, "diff_test"))
            await db.execute("""
                INSERT INTO config_entries_v2 (config_key, config_value, value_type, version, updated_at, profile_name)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ("risk.max_loss_percent", "2.0", "decimal", "v1.0.0", now, "diff_test"))
            await db.commit()

        # Switch and get diff
        diff = await profile_service.switch_profile("diff_test")

        assert isinstance(diff, ProfileDiff)
        assert diff.from_profile == "default"
        assert diff.to_profile == "diff_test"
        assert diff.total_changes == 2

    @pytest.mark.asyncio
    async def test_export_profile_yaml(self, profile_service, profile_repo):
        """Test exporting profile to YAML"""
        # Add configs via SQL
        import aiosqlite
        now = int(datetime.now(timezone.utc).timestamp() * 1000)
        async with aiosqlite.connect(TEST_DB_PATH) as db:
            await db.execute("""
                INSERT INTO config_entries_v2 (config_key, config_value, value_type, version, updated_at, profile_name)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ("strategy.pinbar.min_wick_ratio", "0.6", "decimal", "v1.0.0", now, "default"))
            await db.execute("""
                INSERT INTO config_entries_v2 (config_key, config_value, value_type, version, updated_at, profile_name)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ("risk.max_loss_percent", "1.0", "decimal", "v1.0.0", now, "default"))
            await db.commit()

        yaml_content = await profile_service.export_profile_yaml("default")

        assert "profile:" in yaml_content
        assert "pinbar" in yaml_content or "0.6" in yaml_content

    @pytest.mark.asyncio
    async def test_import_profile_yaml(self, profile_service):
        """Test importing profile from YAML"""
        yaml_content = """
profile:
  name: imported_test
  description: Imported from YAML

strategy:
  pinbar:
    min_wick_ratio: 0.65
    max_body_ratio: 0.25

risk:
  max_loss_percent: 1.5
"""
        profile, count = await profile_service.import_profile_yaml(
            yaml_content=yaml_content,
            mode="create"
        )

        assert profile.name == "imported_test"
        assert count >= 2  # At least 2 config entries

    @pytest.mark.asyncio
    async def test_delete_profile(self, profile_service, profile_repo):
        """Test deleting profile via service"""
        # Create profile
        await profile_repo.create_profile(name="service_delete", description="Test")

        # Delete via service
        success = await profile_service.delete_profile("service_delete")
        assert success is True

        # Verify deleted
        profiles = await profile_service.list_profiles()
        assert len(profiles) == 1  # Only default


# ============================================================
# Rename Profile Tests (Phase 2 - P1)
# ============================================================

class TestRenameProfile:
    """Tests for rename profile functionality"""

    @pytest.mark.asyncio
    async def test_rename_profile_basic(self, profile_service, profile_repo):
        """Test basic rename functionality"""
        # Create profile
        await profile_repo.create_profile(name="old_name", description="Test profile")

        # Rename
        updated = await profile_service.rename_profile(
            old_name="old_name",
            new_name="new_name",
            description="Renamed profile"
        )

        assert updated.name == "new_name"
        assert updated.description == "Renamed profile"

        # Verify old name doesn't exist
        old_profile = await profile_service.get_profile("old_name")
        assert old_profile is None

        # Verify new name exists
        new_profile = await profile_service.get_profile("new_name")
        assert new_profile is not None
        assert new_profile.name == "new_name"

    @pytest.mark.asyncio
    async def test_rename_profile_duplicate_name(self, profile_service, profile_repo):
        """Test rename with duplicate name raises error"""
        # Create two profiles
        await profile_repo.create_profile(name="source", description="Source profile")
        await profile_repo.create_profile(name="target", description="Target profile")

        # Try to rename source to target (should fail)
        with pytest.raises(ValueError, match="已存在"):
            await profile_service.rename_profile(
                old_name="source",
                new_name="target",
                description=None
            )

    @pytest.mark.asyncio
    async def test_rename_profile_to_default(self, profile_service, profile_repo):
        """Test rename to 'default' name raises error"""
        await profile_repo.create_profile(name="test_rename", description="Test")

        # Try to rename to 'default' (should fail)
        with pytest.raises(ValueError, match="不能重命名为"):
            await profile_service.rename_profile(
                old_name="test_rename",
                new_name="default",
                description=None
            )

    @pytest.mark.asyncio
    async def test_rename_profile_nonexistent(self, profile_service):
        """Test rename non-existent profile raises error"""
        with pytest.raises(ValueError, match="不存在"):
            await profile_service.rename_profile(
                old_name="nonexistent",
                new_name="new_name",
                description=None
            )

    @pytest.mark.asyncio
    async def test_rename_profile_preserves_configs(self, profile_service, profile_repo):
        """Test that rename preserves configuration entries"""
        import aiosqlite
        now = int(datetime.now(timezone.utc).timestamp() * 1000)

        # Create profile
        await profile_repo.create_profile(name="config_test", description="Test with configs")

        # Add config entries
        async with aiosqlite.connect(TEST_DB_PATH) as db:
            await db.execute("""
                INSERT INTO config_entries_v2 (config_key, config_value, value_type, version, updated_at, profile_name)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ("test.key1", "value1", "string", "v1.0.0", now, "config_test"))
            await db.execute("""
                INSERT INTO config_entries_v2 (config_key, config_value, value_type, version, updated_at, profile_name)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ("test.key2", "value2", "string", "v1.0.0", now, "config_test"))
            await db.commit()

        # Rename profile
        await profile_service.rename_profile(
            old_name="config_test",
            new_name="renamed_config_test",
            description="Renamed"
        )

        # Verify config entries are now under new profile name
        new_profile = await profile_service.get_profile("renamed_config_test")
        assert new_profile is not None
        assert new_profile.config_count == 2

        # Verify old profile doesn't exist
        old_profile = await profile_service.get_profile("config_test")
        assert old_profile is None


# ============================================================
# ProfileDiff Tests
# ============================================================

class TestProfileDiff:
    """Tests for ProfileDiff class"""

    def test_profile_diff_to_dict(self):
        """Test ProfileDiff to_dict method"""
        diff = ProfileDiff(
            from_profile="default",
            to_profile="test",
            diff={"strategy": {"key": {"old": "a", "new": "b"}}},
            total_changes=1
        )

        result = diff.to_dict()

        assert result["from_profile"] == "default"
        assert result["to_profile"] == "test"
        assert result["total_changes"] == 1
        assert "strategy" in result["diff"]


# ============================================================
# Profile Switch Cache Refresh Tests (R1.1 Fix)
# ============================================================

class TestProfileSwitchCacheRefresh:
    """Tests for Profile switch cache refresh (R1.1 bug fix)"""

    @pytest.mark.asyncio
    async def test_switch_profile_calls_config_manager_reload(self, profile_repo):
        """Test that switch_profile() calls ConfigManager.reload_all_configs_from_db()"""
        from unittest.mock import AsyncMock, MagicMock

        # Create config repo
        config_repo = ConfigEntryRepository(db_path=TEST_DB_PATH)
        await config_repo.initialize()

        # Create mock ConfigManager
        mock_config_manager = AsyncMock()
        mock_config_manager.reload_all_configs_from_db = AsyncMock()

        # Create service with ConfigManager
        service = ConfigProfileService(profile_repo, config_repo, mock_config_manager)

        # Create a test profile
        await profile_repo.create_profile(name="test_profile", description="Test")

        # Switch profile
        diff = await service.switch_profile("test_profile")

        # Verify ConfigManager was called
        mock_config_manager.reload_all_configs_from_db.assert_called_once()

        await config_repo.close()

    @pytest.mark.asyncio
    async def test_switch_profile_without_config_manager(self, profile_repo):
        """Test that switch_profile() works without ConfigManager (backward compatible)"""
        # Create config repo
        config_repo = ConfigEntryRepository(db_path=TEST_DB_PATH)
        await config_repo.initialize()

        # Create service WITHOUT ConfigManager
        service = ConfigProfileService(profile_repo, config_repo, config_manager=None)

        # Create a test profile
        await profile_repo.create_profile(name="test_profile", description="Test")

        # Switch profile - should NOT raise error
        diff = await service.switch_profile("test_profile")

        assert diff is not None
        assert diff.from_profile == "default"
        assert diff.to_profile == "test_profile"

        await config_repo.close()

    @pytest.mark.asyncio
    async def test_switch_profile_cache_refresh_logs_error(self, profile_repo):
        """Test that ConfigManager reload error is logged but doesn't break switch"""
        from unittest.mock import AsyncMock

        # Create config repo
        config_repo = ConfigEntryRepository(db_path=TEST_DB_PATH)
        await config_repo.initialize()

        # Create mock ConfigManager that raises error
        mock_config_manager = AsyncMock()
        mock_config_manager.reload_all_configs_from_db = AsyncMock(side_effect=Exception("DB error"))

        # Create service with failing ConfigManager
        service = ConfigProfileService(profile_repo, config_repo, mock_config_manager)

        # Create a test profile
        await profile_repo.create_profile(name="test_profile", description="Test")

        # Switch profile - should NOT raise error even if ConfigManager fails
        diff = await service.switch_profile("test_profile")

        # Verify switch still succeeded
        assert diff is not None

        # Verify ConfigManager was still called
        mock_config_manager.reload_all_configs_from_db.assert_called_once()

        await config_repo.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
