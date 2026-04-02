"""
Unit tests for config snapshot service.
"""
import pytest
import json
import tempfile
import os
from decimal import Decimal

from src.infrastructure.config_snapshot_repository import ConfigSnapshotRepository
from src.application.config_snapshot_service import (
    ConfigSnapshotService,
    SnapshotNotFoundError,
    SnapshotValidationError,
    SnapshotProtectedError,
)
from src.application.config_manager import UserConfig


@pytest.fixture
def sample_user_config():
    """Sample UserConfig for testing."""
    return UserConfig(
        exchange={
            "name": "binance",
            "api_key": "test_api_key_12345",
            "api_secret": "test_api_secret_67890",
            "testnet": True,
        },
        user_symbols=["BTC/USDT:USDT", "ETH/USDT:USDT"],
        timeframes=["15m", "1h"],
        risk={
            "max_loss_percent": "0.01",
            "max_leverage": 10,
        },
        notification={
            "channels": [
                {"type": "feishu", "webhook_url": "https://example.com/webhook"}
            ]
        }
    )


@pytest.fixture
async def repository():
    """Create a test repository instance."""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_service.db")

    repo = ConfigSnapshotRepository(db_path=db_path)
    await repo.initialize()

    yield repo

    await repo.close()
    os.remove(db_path)
    os.rmdir(temp_dir)


@pytest.fixture
def service(repository):
    """Create a service instance with test repository."""
    return ConfigSnapshotService(repository, protect_recent_count=3)


class TestConfigSnapshotServiceCreateManualSnapshot:
    """Test create_manual_snapshot method."""

    @pytest.mark.asyncio
    async def test_create_manual_snapshot_success(self, service, sample_user_config):
        """Test creating a manual snapshot with valid data."""
        snapshot_id = await service.create_manual_snapshot(
            version="v1.0.0",
            config=sample_user_config,
            description="Test snapshot",
            created_by="test_user"
        )

        assert snapshot_id is not None
        assert snapshot_id > 0

    @pytest.mark.asyncio
    async def test_create_manual_snapshot_invalid_version(self, service, sample_user_config):
        """Test that invalid version format raises error."""
        with pytest.raises(SnapshotValidationError) as exc_info:
            await service.create_manual_snapshot(
                version="1.0.0",  # Missing 'v' prefix
                config=sample_user_config,
            )
        assert exc_info.value.error_code == "CONFIG-003"

    @pytest.mark.asyncio
    async def test_create_manual_snapshot_default_values(self, service, sample_user_config):
        """Test creating snapshot with default values."""
        snapshot_id = await service.create_manual_snapshot(
            version="v1.0.0",
            config=sample_user_config,
        )

        snapshot = await service.get_snapshot_detail(snapshot_id)
        assert snapshot["description"] == ""
        assert snapshot["created_by"] == "user"

    @pytest.mark.asyncio
    async def test_create_manual_snapshot_masks_secrets(self, service, sample_user_config):
        """Test that secrets are masked in stored config."""
        snapshot_id = await service.create_manual_snapshot(
            version="v1.0.0",
            config=sample_user_config,
        )

        snapshot = await service.get_snapshot_detail(snapshot_id)
        config = snapshot["config"]

        # API key should be masked (format: first4...last4)
        api_key = config["exchange"]["api_key"]
        assert api_key != "test_api_key_12345"
        assert "..." in api_key  # Masked format uses "..."

        # API secret should be masked
        api_secret = config["exchange"]["api_secret"]
        assert api_secret != "test_api_secret_67890"
        assert "..." in api_secret

        # Webhook URL should be masked
        webhook = config["notification"]["channels"][0]["webhook_url"]
        assert webhook != "https://example.com/webhook"
        assert "..." in webhook


class TestConfigSnapshotServiceCreateAutoSnapshot:
    """Test create_auto_snapshot method."""

    @pytest.mark.asyncio
    async def test_create_auto_snapshot_generates_version(self, service, sample_user_config):
        """Test that auto-snapshot generates version from timestamp."""
        snapshot_id = await service.create_auto_snapshot(
            config=sample_user_config,
            description="Auto snapshot"
        )

        assert snapshot_id is not None
        snapshot = await service.get_snapshot_detail(snapshot_id)
        # Version should match pattern vYYYYMMDD.HHMMSS
        assert snapshot["version"].startswith("v")

    @pytest.mark.asyncio
    async def test_create_auto_snapshot_default_description(self, service, sample_user_config):
        """Test auto-snapshot with default description."""
        snapshot_id = await service.create_auto_snapshot(config=sample_user_config)

        snapshot = await service.get_snapshot_detail(snapshot_id)
        assert "配置变更自动快照" in snapshot["description"]


class TestConfigSnapshotServiceGetSnapshotList:
    """Test get_snapshot_list method."""

    @pytest.mark.asyncio
    async def test_get_snapshot_list_pagination(self, service, sample_user_config):
        """Test pagination in snapshot list."""
        # Create 5 snapshots
        for i in range(5):
            await service.create_manual_snapshot(
                version=f"v{i+1}.0.0",
                config=sample_user_config,
            )

        # Get first page
        data, total = await service.get_snapshot_list(limit=2, offset=0)
        assert total == 5
        assert len(data) == 2

        # Get second page
        data, total = await service.get_snapshot_list(limit=2, offset=2)
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_get_snapshot_list_filter_by_created_by(self, service, sample_user_config):
        """Test filtering by creator."""
        await service.create_manual_snapshot(
            version="v1.0.0",
            config=sample_user_config,
            created_by="user_a"
        )
        await service.create_manual_snapshot(
            version="v2.0.0",
            config=sample_user_config,
            created_by="user_b"
        )

        data, total = await service.get_snapshot_list(created_by="user_a")
        assert total == 1
        assert data[0]["created_by"] == "user_a"


class TestConfigSnapshotServiceGetSnapshotDetail:
    """Test get_snapshot_detail method."""

    @pytest.mark.asyncio
    async def test_get_snapshot_detail_success(self, service, sample_user_config):
        """Test retrieving snapshot detail."""
        snapshot_id = await service.create_manual_snapshot(
            version="v1.0.0",
            config=sample_user_config,
            description="Test detail"
        )

        detail = await service.get_snapshot_detail(snapshot_id)

        assert detail["id"] == snapshot_id
        assert detail["version"] == "v1.0.0"
        assert detail["description"] == "Test detail"
        assert "config" in detail
        assert "config_json" in detail

    @pytest.mark.asyncio
    async def test_get_snapshot_detail_not_found(self, service):
        """Test retrieving non-existent snapshot."""
        with pytest.raises(SnapshotNotFoundError) as exc_info:
            await service.get_snapshot_detail(999)
        assert exc_info.value.error_code == "CONFIG-004"


class TestConfigSnapshotServiceRollback:
    """Test rollback_to_snapshot method."""

    @pytest.mark.asyncio
    async def test_rollback_success(self, service, sample_user_config):
        """Test successful rollback."""
        snapshot_id = await service.create_manual_snapshot(
            version="v1.0.0",
            config=sample_user_config,
        )

        result = await service.rollback_to_snapshot(snapshot_id)

        assert result["is_active"] is True
        assert result["version"] == "v1.0.0"

    @pytest.mark.asyncio
    async def test_rollback_invalid_config_json(self, repository):
        """Test rollback with invalid config JSON."""
        service = ConfigSnapshotService(repository)

        # Create snapshot with invalid JSON directly in DB
        import sqlite3
        async with repository._db.execute(
            """
            INSERT INTO config_snapshots (version, config_json, description, created_at, created_by, is_active)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            ("v1.0.0", "not valid json", "Invalid", "2024-01-01T00:00:00Z", "test")
        ) as cursor:
            await repository._db.commit()
            snapshot_id = cursor.lastrowid

        with pytest.raises(SnapshotValidationError):
            await service.rollback_to_snapshot(snapshot_id)

    @pytest.mark.asyncio
    async def test_rollback_not_found(self, service):
        """Test rollback non-existent snapshot."""
        with pytest.raises(SnapshotNotFoundError):
            await service.rollback_to_snapshot(999)


class TestConfigSnapshotServiceDelete:
    """Test delete_snapshot method."""

    @pytest.mark.asyncio
    async def test_delete_success(self, repository, sample_user_config):
        """Test successful deletion."""
        # Create more than protect_count snapshots
        service = ConfigSnapshotService(repository, protect_recent_count=2)

        ids = []
        for i in range(5):
            snapshot_id = await service.create_manual_snapshot(
                version=f"v{i+1}.0.0",
                config=sample_user_config,
            )
            ids.append(snapshot_id)

        # Delete oldest (should succeed)
        result = await service.delete_snapshot(ids[0])
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_protected_snapshot(self, service, sample_user_config):
        """Test deleting protected snapshot raises error."""
        # Create 3 snapshots (all protected with protect_recent_count=3)
        ids = []
        for i in range(3):
            snapshot_id = await service.create_manual_snapshot(
                version=f"v{i+1}.0.0",
                config=sample_user_config,
            )
            ids.append(snapshot_id)

        # Try to delete any of them (all protected)
        with pytest.raises(SnapshotProtectedError) as exc_info:
            await service.delete_snapshot(ids[0])
        assert exc_info.value.error_code == "CONFIG-006"

    @pytest.mark.asyncio
    async def test_delete_not_found(self, service):
        """Test deleting non-existent snapshot."""
        with pytest.raises(SnapshotNotFoundError):
            await service.delete_snapshot(999)


class TestConfigSnapshotServiceGetActiveSnapshot:
    """Test get_active_snapshot method."""

    @pytest.mark.asyncio
    async def test_get_active_snapshot_success(self, service, sample_user_config):
        """Test retrieving active snapshot."""
        await service.create_manual_snapshot(
            version="v1.0.0",
            config=sample_user_config,
        )

        active = await service.get_active_snapshot()

        assert active is not None
        assert active["is_active"] is True

    @pytest.mark.asyncio
    async def test_get_active_snapshot_none_when_empty(self, repository):
        """Test get_active_snapshot returns None when no snapshots."""
        service = ConfigSnapshotService(repository)
        active = await service.get_active_snapshot()
        assert active is None
