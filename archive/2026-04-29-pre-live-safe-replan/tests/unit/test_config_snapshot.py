"""
Unit tests for config snapshot feature - configuration version control and rollback.
"""
import pytest
import json
from decimal import Decimal
from datetime import datetime, timezone
from src.domain.models import ConfigSnapshot


class TestConfigSnapshotModel:
    """Test ConfigSnapshot Pydantic model."""

    def test_create_snapshot(self):
        """Test creating a basic config snapshot."""
        snapshot = ConfigSnapshot(
            version="v1.0.0",
            config_json='{"risk": {"max_loss_percent": "0.01"}}',
            description="Initial snapshot",
            created_by="test_user",
        )
        assert snapshot.version == "v1.0.0"
        assert snapshot.description == "Initial snapshot"
        assert snapshot.created_by == "test_user"
        assert snapshot.is_active is False

    def test_json_serialization(self):
        """Test snapshot can be serialized to JSON."""
        snapshot = ConfigSnapshot(
            version="v1.0.0",
            config_json=json.dumps({"test": "data", "nested": {"key": "value"}}),
            description="Test snapshot",
        )
        data = snapshot.model_dump()
        assert "version" in data
        assert "config_json" in data
        assert "is_active" in data
        assert data["version"] == "v1.0.0"

    def test_default_values(self):
        """Test default field values."""
        snapshot = ConfigSnapshot(
            version="v1.0.0",
            config_json="{}",
        )
        assert snapshot.description == ""
        assert snapshot.created_by == "user"
        assert snapshot.is_active is False
        assert snapshot.id is None

    def test_full_snapshot(self):
        """Test creating a complete snapshot with all fields."""
        now = datetime.now(timezone.utc).isoformat()
        snapshot = ConfigSnapshot(
            id=1,
            version="v2.0.0",
            config_json=json.dumps({
                "strategy": {"trend_filter_enabled": True},
                "risk": {"max_loss_percent": "0.02", "max_leverage": 20}
            }),
            description="Updated risk parameters",
            created_at=now,
            created_by="admin",
            is_active=True,
        )
        assert snapshot.id == 1
        assert snapshot.version == "v2.0.0"
        assert snapshot.is_active is True
        assert snapshot.created_by == "admin"

        # Verify config_json can be parsed
        config_data = json.loads(snapshot.config_json)
        assert config_data["risk"]["max_loss_percent"] == "0.02"


class TestConfigSnapshotRepository:
    """Test config snapshot repository methods."""

    @pytest.fixture
    async def repository(self):
        """Create a test repository instance."""
        from src.infrastructure.signal_repository import SignalRepository
        import tempfile
        import os

        # Create temporary database file
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_signals.db")

        repo = SignalRepository(db_path=db_path)
        await repo.initialize()

        yield repo

        # Cleanup
        await repo.close()
        os.remove(db_path)
        os.rmdir(temp_dir)

    @pytest.mark.asyncio
    async def test_create_and_retrieve_snapshot(self, repository):
        """Test creating and retrieving a config snapshot."""
        # Create snapshot
        snapshot_id = await repository.create_config_snapshot(
            version="v1.0.0",
            config_json='{"test": "config"}',
            description="Test snapshot",
            created_by="tester",
        )

        assert snapshot_id is not None
        assert snapshot_id > 0

        # Retrieve by ID
        snapshot = await repository.get_config_snapshot_by_id(snapshot_id)
        assert snapshot is not None
        assert snapshot["version"] == "v1.0.0"
        assert snapshot["config_json"] == '{"test": "config"}'
        assert snapshot["description"] == "Test snapshot"
        assert snapshot["is_active"] == 1  # SQLite returns integer for boolean

    @pytest.mark.asyncio
    async def test_create_snapshot_deactivates_others(self, repository):
        """Test that creating a new snapshot deactivates existing ones."""
        # Create first snapshot
        id1 = await repository.create_config_snapshot(
            version="v1.0.0",
            config_json='{"v": 1}',
            description="First snapshot",
        )

        # Verify first is active
        snapshot1 = await repository.get_config_snapshot_by_id(id1)
        assert snapshot1["is_active"] == 1

        # Create second snapshot
        id2 = await repository.create_config_snapshot(
            version="v2.0.0",
            config_json='{"v": 2}',
            description="Second snapshot",
        )

        # Verify first is now inactive
        snapshot1 = await repository.get_config_snapshot_by_id(id1)
        assert snapshot1["is_active"] == 0

        # Verify second is active
        snapshot2 = await repository.get_config_snapshot_by_id(id2)
        assert snapshot2["is_active"] == 1

    @pytest.mark.asyncio
    async def test_get_all_snapshots_with_pagination(self, repository):
        """Test retrieving all snapshots with pagination."""
        # Create multiple snapshots
        for i in range(5):
            await repository.create_config_snapshot(
                version=f"v{i+1}.0.0",
                config_json=f'{{"v": {i+1}}}',
                description=f"Snapshot {i+1}",
            )

        # Get all with default pagination
        result = await repository.get_config_snapshots(limit=50, offset=0)
        assert result["total"] == 5
        assert len(result["data"]) == 5

        # Get with pagination
        result = await repository.get_config_snapshots(limit=2, offset=0)
        assert result["total"] == 5
        assert len(result["data"]) == 2

        # Get second page
        result = await repository.get_config_snapshots(limit=2, offset=2)
        assert len(result["data"]) == 2

    @pytest.mark.asyncio
    async def test_get_active_snapshot(self, repository):
        """Test retrieving the active snapshot."""
        # Create snapshots
        id1 = await repository.create_config_snapshot(
            version="v1.0.0",
            config_json='{"v": 1}',
            description="First",
        )
        id2 = await repository.create_config_snapshot(
            version="v2.0.0",
            config_json='{"v": 2}',
            description="Second",
        )

        # Get active snapshot (should be the latest one)
        active = await repository.get_active_config_snapshot()
        assert active is not None
        assert active["id"] == id2
        assert active["is_active"] == 1

    @pytest.mark.asyncio
    async def test_activate_snapshot(self, repository):
        """Test activating a specific snapshot."""
        # Create snapshots
        id1 = await repository.create_config_snapshot(
            version="v1.0.0",
            config_json='{"v": 1}',
            description="First",
        )
        id2 = await repository.create_config_snapshot(
            version="v2.0.0",
            config_json='{"v": 2}',
            description="Second",
        )

        # Activate first snapshot
        success = await repository.activate_config_snapshot(id1)
        assert success is True

        # Verify first is now active
        snapshot1 = await repository.get_config_snapshot_by_id(id1)
        assert snapshot1["is_active"] == 1

        # Verify second is now inactive
        snapshot2 = await repository.get_config_snapshot_by_id(id2)
        assert snapshot2["is_active"] == 0

    @pytest.mark.asyncio
    async def test_activate_nonexistent_snapshot(self, repository):
        """Test activating a non-existent snapshot."""
        success = await repository.activate_config_snapshot(999)
        assert success is False

    @pytest.mark.asyncio
    async def test_delete_snapshot(self, repository):
        """Test deleting a config snapshot."""
        # Create snapshot
        snapshot_id = await repository.create_config_snapshot(
            version="v1.0.0",
            config_json='{"v": 1}',
            description="To delete",
        )

        # Delete snapshot
        success = await repository.delete_config_snapshot(snapshot_id)
        assert success is True

        # Verify deleted
        snapshot = await repository.get_config_snapshot_by_id(snapshot_id)
        assert snapshot is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_snapshot(self, repository):
        """Test deleting a non-existent snapshot."""
        success = await repository.delete_config_snapshot(999)
        assert success is False

    @pytest.mark.asyncio
    async def test_snapshots_ordered_by_created_at(self, repository):
        """Test that snapshots are returned in descending order of creation."""
        import asyncio

        # Create snapshots with small delays to ensure different timestamps
        ids = []
        for i in range(3):
            snapshot_id = await repository.create_config_snapshot(
                version=f"v{i+1}.0.0",
                config_json=f'{{"v": {i+1}}}',
                description=f"Snapshot {i+1}",
            )
            ids.append(snapshot_id)
            await asyncio.sleep(0.01)  # Small delay

        # Get all snapshots
        result = await repository.get_config_snapshots(limit=10, offset=0)

        # Verify order (newest first)
        assert result["data"][0]["id"] == ids[-1]
        assert result["data"][-1]["id"] == ids[0]


class TestConfigSnapshotIntegration:
    """Integration tests for config snapshot feature."""

    @pytest.fixture
    async def repository(self):
        """Create a test repository instance."""
        from src.infrastructure.signal_repository import SignalRepository
        import tempfile
        import os

        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_signals.db")

        repo = SignalRepository(db_path=db_path)
        await repo.initialize()

        yield repo

        await repo.close()
        os.remove(db_path)
        os.rmdir(temp_dir)

    @pytest.mark.asyncio
    async def test_full_snapshot_lifecycle(self, repository):
        """Test complete snapshot lifecycle."""
        # Create initial config snapshot
        config_data = {
            "strategy": {
                "trend_filter_enabled": True,
                "mtf_validation_enabled": True,
            },
            "risk": {
                "max_loss_percent": "0.01",
                "max_leverage": 20,
            }
        }

        snapshot_id = await repository.create_config_snapshot(
            version="v1.0.0",
            config_json=json.dumps(config_data),
            description="Initial production config",
            created_by="admin",
        )

        # Retrieve and verify
        snapshot = await repository.get_config_snapshot_by_id(snapshot_id)
        assert snapshot["version"] == "v1.0.0"
        assert json.loads(snapshot["config_json"]) == config_data

        # Create updated config
        updated_config = {
            "strategy": {
                "trend_filter_enabled": False,
                "mtf_validation_enabled": True,
            },
            "risk": {
                "max_loss_percent": "0.02",
                "max_leverage": 10,
            }
        }

        updated_id = await repository.create_config_snapshot(
            version="v2.0.0",
            config_json=json.dumps(updated_config),
            description="Reduced leverage",
            created_by="trader",
        )

        # Verify v1 is now inactive
        v1 = await repository.get_config_snapshot_by_id(snapshot_id)
        assert v1["is_active"] == 0

        # Verify v2 is active
        v2 = await repository.get_config_snapshot_by_id(updated_id)
        assert v2["is_active"] == 1

        # Rollback to v1
        await repository.activate_config_snapshot(snapshot_id)

        # Verify v1 is active again
        v1 = await repository.get_config_snapshot_by_id(snapshot_id)
        assert v1["is_active"] == 1
        v2 = await repository.get_config_snapshot_by_id(updated_id)
        assert v2["is_active"] == 0
