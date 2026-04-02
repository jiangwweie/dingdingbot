"""
Configuration Snapshot Repository Unit Tests

Tests for ConfigSnapshotRepository CRUD operations.
Coverage target: >= 85%
"""
import pytest
import json
import tempfile
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from src.infrastructure.signal_repository import SignalRepository


# ============================================================
# Fixtures
# ============================================================
@pytest.fixture
async def repository():
    """Create a SignalRepository with temporary SQLite database."""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_snapshots.db")

    repo = SignalRepository(db_path=db_path)
    await repo.initialize()

    yield repo

    # Cleanup
    await repo.close()
    if os.path.exists(db_path):
        os.remove(db_path)
    if os.path.exists(temp_dir):
        os.rmdir(temp_dir)


@pytest.fixture
def sample_config_json():
    """Sample configuration JSON for testing."""
    return json.dumps({
        "exchange": {
            "name": "binance",
            "api_key": "test_key_1234",
            "api_secret": "test_secret_5678",
            "testnet": True
        },
        "user_symbols": ["BTC/USDT:USDT", "ETH/USDT:USDT"],
        "timeframes": ["15m", "1h", "4h"],
        "strategy": {
            "trend_filter_enabled": True,
            "mtf_validation_enabled": True
        },
        "risk": {
            "max_loss_percent": "0.01",
            "max_leverage": 20
        },
        "notification": {
            "channels": [
                {"type": "feishu", "webhook_url": "https://example.com/hook"}
            ]
        }
    })


# ============================================================
# Test Class: ConfigSnapshotRepository - Basic CRUD
# ============================================================
class TestConfigSnapshotRepositoryBasicCRUD:
    """Test basic Create, Read, Update, Delete operations."""

    @pytest.mark.asyncio
    async def test_create_snapshot_returns_positive_id(self, repository, sample_config_json):
        """Test that creating a snapshot returns a positive integer ID."""
        snapshot_id = await repository.create_config_snapshot(
            version="v1.0.0",
            config_json=sample_config_json,
            description="Initial test snapshot",
            created_by="test_user"
        )

        assert isinstance(snapshot_id, int)
        assert snapshot_id > 0

    @pytest.mark.asyncio
    async def test_create_snapshot_stores_all_fields(self, repository, sample_config_json):
        """Test that all fields are correctly stored."""
        snapshot_id = await repository.create_config_snapshot(
            version="v1.0.0",
            config_json=sample_config_json,
            description="Test description",
            created_by="test_creator"
        )

        # Retrieve and verify
        snapshot = await repository.get_config_snapshot_by_id(snapshot_id)

        assert snapshot is not None
        assert snapshot["version"] == "v1.0.0"
        assert snapshot["config_json"] == sample_config_json
        assert snapshot["description"] == "Test description"
        assert snapshot["created_by"] == "test_creator"
        assert "created_at" in snapshot
        assert snapshot["is_active"] == 1  # SQLite returns 1 for True

    @pytest.mark.asyncio
    async def test_create_snapshot_default_values(self, repository, sample_config_json):
        """Test that default values are applied correctly."""
        snapshot_id = await repository.create_config_snapshot(
            version="v1.0.0",
            config_json=sample_config_json
            # description and created_by use defaults
        )

        snapshot = await repository.get_config_snapshot_by_id(snapshot_id)

        assert snapshot is not None
        assert snapshot["description"] == ""
        assert snapshot["created_by"] == "user"

    @pytest.mark.asyncio
    async def test_get_nonexistent_snapshot_returns_none(self, repository):
        """Test that retrieving a non-existent snapshot returns None."""
        snapshot = await repository.get_config_snapshot_by_id(99999)
        assert snapshot is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_snapshot_returns_false(self, repository):
        """Test that deleting a non-existent snapshot returns False."""
        result = await repository.delete_config_snapshot(99999)
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_existing_snapshot_returns_true(self, repository, sample_config_json):
        """Test that deleting an existing snapshot returns True."""
        snapshot_id = await repository.create_config_snapshot(
            version="v1.0.0",
            config_json=sample_config_json,
            description="To be deleted"
        )

        result = await repository.delete_config_snapshot(snapshot_id)
        assert result is True

        # Verify deleted
        snapshot = await repository.get_config_snapshot_by_id(snapshot_id)
        assert snapshot is None

    @pytest.mark.asyncio
    async def test_cannot_retrieve_deleted_snapshot(self, repository, sample_config_json):
        """Test that deleted snapshots cannot be retrieved."""
        snapshot_id = await repository.create_config_snapshot(
            version="v1.0.0",
            config_json=sample_config_json
        )

        # Delete
        await repository.delete_config_snapshot(snapshot_id)

        # Verify cannot retrieve
        snapshot = await repository.get_config_snapshot_by_id(snapshot_id)
        assert snapshot is None


# ============================================================
# Test Class: ConfigSnapshotRepository - Activation Logic
# ============================================================
class TestConfigSnapshotRepositoryActivation:
    """Test snapshot activation and deactivation logic."""

    @pytest.mark.asyncio
    async def test_new_snapshot_is_active(self, repository, sample_config_json):
        """Test that newly created snapshots are active."""
        snapshot_id = await repository.create_config_snapshot(
            version="v1.0.0",
            config_json=sample_config_json
        )

        snapshot = await repository.get_config_snapshot_by_id(snapshot_id)
        assert snapshot["is_active"] == 1

    @pytest.mark.asyncio
    async def test_creating_new_snapshot_deactivates_previous(self, repository, sample_config_json):
        """Test that creating a new snapshot deactivates the previous one."""
        # Create first snapshot
        id1 = await repository.create_config_snapshot(
            version="v1.0.0",
            config_json=sample_config_json,
            description="First"
        )

        # Create second snapshot
        id2 = await repository.create_config_snapshot(
            version="v2.0.0",
            config_json=sample_config_json,
            description="Second"
        )

        # Verify first is inactive
        snapshot1 = await repository.get_config_snapshot_by_id(id1)
        assert snapshot1["is_active"] == 0

        # Verify second is active
        snapshot2 = await repository.get_config_snapshot_by_id(id2)
        assert snapshot2["is_active"] == 1

    @pytest.mark.asyncio
    async def test_activate_snapshot_success(self, repository, sample_config_json):
        """Test successful activation of a snapshot."""
        # Create two snapshots
        id1 = await repository.create_config_snapshot(
            version="v1.0.0",
            config_json=sample_config_json,
            description="First"
        )
        id2 = await repository.create_config_snapshot(
            version="v2.0.0",
            config_json=sample_config_json,
            description="Second"
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
    async def test_activate_nonexistent_snapshot_returns_false(self, repository):
        """Test that activating a non-existent snapshot returns False."""
        result = await repository.activate_config_snapshot(99999)
        assert result is False

    @pytest.mark.asyncio
    async def test_get_active_snapshot_returns_latest(self, repository, sample_config_json):
        """Test that get_active_config_snapshot returns the most recent active snapshot."""
        # Create snapshots with small delay
        id1 = await repository.create_config_snapshot(
            version="v1.0.0",
            config_json=sample_config_json
        )
        await asyncio.sleep(0.01)
        id2 = await repository.create_config_snapshot(
            version="v2.0.0",
            config_json=sample_config_json
        )

        # Get active snapshot
        active = await repository.get_active_config_snapshot()

        assert active is not None
        assert active["id"] == id2
        assert active["is_active"] == 1

    @pytest.mark.asyncio
    async def test_get_active_snapshot_none_when_no_snapshots(self, repository):
        """Test that get_active_config_snapshot returns None when no snapshots exist."""
        active = await repository.get_active_config_snapshot()
        assert active is None


# ============================================================
# Test Class: ConfigSnapshotRepository - Pagination
# ============================================================
class TestConfigSnapshotRepositoryPagination:
    """Test pagination functionality."""

    @pytest.mark.asyncio
    async def test_get_snapshots_with_pagination(self, repository, sample_config_json):
        """Test retrieving snapshots with pagination."""
        # Create 10 snapshots
        ids = []
        for i in range(10):
            snapshot_id = await repository.create_config_snapshot(
                version=f"v{i+1}.0.0",
                config_json=sample_config_json,
                description=f"Snapshot {i+1}"
            )
            ids.append(snapshot_id)

        # Get first page (limit=3, offset=0)
        result = await repository.get_config_snapshots(limit=3, offset=0)

        assert "total" in result
        assert "data" in result
        assert result["total"] == 10
        assert len(result["data"]) == 3

        # Get second page (limit=3, offset=3)
        result = await repository.get_config_snapshots(limit=3, offset=3)
        assert len(result["data"]) == 3

        # Get last page (limit=3, offset=9)
        result = await repository.get_config_snapshots(limit=3, offset=9)
        assert len(result["data"]) == 1

    @pytest.mark.asyncio
    async def test_get_snapshots_default_pagination(self, repository, sample_config_json):
        """Test default pagination values."""
        # Create 5 snapshots
        for i in range(5):
            await repository.create_config_snapshot(
                version=f"v{i+1}.0.0",
                config_json=sample_config_json
            )

        # Use default pagination
        result = await repository.get_config_snapshots()

        assert result["total"] == 5
        assert len(result["data"]) == 5

    @pytest.mark.asyncio
    async def test_get_snapshots_order_by_created_at_desc(self, repository, sample_config_json):
        """Test that snapshots are ordered by created_at descending."""
        import asyncio

        ids = []
        for i in range(5):
            snapshot_id = await repository.create_config_snapshot(
                version=f"v{i+1}.0.0",
                config_json=sample_config_json,
                description=f"Snapshot {i+1}"
            )
            ids.append(snapshot_id)
            await asyncio.sleep(0.01)  # Ensure different timestamps

        result = await repository.get_config_snapshots(limit=10, offset=0)

        # First item should be the latest created
        assert result["data"][0]["id"] == ids[-1]
        # Last item should be the first created
        assert result["data"][-1]["id"] == ids[0]


# ============================================================
# Test Class: ConfigSnapshotRepository - Version Uniqueness
# ============================================================
class TestConfigSnapshotRepositoryVersionUniqueness:
    """Test version uniqueness constraint."""

    @pytest.mark.asyncio
    async def test_duplicate_version_raises_error(self, repository, sample_config_json):
        """Test that creating a snapshot with duplicate version raises an error."""
        # Create first snapshot
        await repository.create_config_snapshot(
            version="v1.0.0",
            config_json=sample_config_json,
            description="First"
        )

        # Try to create second snapshot with same version
        import sqlite3
        with pytest.raises(sqlite3.IntegrityError):
            await repository.create_config_snapshot(
                version="v1.0.0",
                config_json=sample_config_json,
                description="Duplicate"
            )

    @pytest.mark.asyncio
    async def test_different_versions_succeed(self, repository, sample_config_json):
        """Test that creating snapshots with different versions succeeds."""
        id1 = await repository.create_config_snapshot(
            version="v1.0.0",
            config_json=sample_config_json
        )

        id2 = await repository.create_config_snapshot(
            version="v1.1.0",
            config_json=sample_config_json
        )

        assert id1 > 0
        assert id2 > 0
        assert id1 != id2


# ============================================================
# Test Class: ConfigSnapshotRepository - Config JSON Validation
# ============================================================
class TestConfigSnapshotRepositoryConfigJSON:
    """Test config JSON storage and retrieval."""

    @pytest.mark.asyncio
    async def test_complex_nested_config_stored_correctly(self, repository):
        """Test that complex nested configuration is stored correctly."""
        complex_config = json.dumps({
            "exchange": {
                "name": "binance",
                "credentials": {
                    "api_key": "key123",
                    "api_secret": "secret456",
                    "nested": {
                        "deep": {
                            "value": "test"
                        }
                    }
                }
            },
            "strategies": [
                {"id": "pinbar", "enabled": True},
                {"id": "engulfing", "enabled": False}
            ],
            "risk": {
                "max_loss_percent": "0.01",
                "take_profit_levels": [
                    {"ratio": 0.3, "reduce_ratio": 0.5},
                    {"ratio": 0.6, "reduce_ratio": 0.3}
                ]
            }
        })

        snapshot_id = await repository.create_config_snapshot(
            version="v1.0.0",
            config_json=complex_config,
            description="Complex nested config"
        )

        snapshot = await repository.get_config_snapshot_by_id(snapshot_id)
        assert snapshot is not None

        # Verify JSON can be parsed back
        config_data = json.loads(snapshot["config_json"])
        assert config_data["exchange"]["credentials"]["nested"]["deep"]["value"] == "test"
        assert len(config_data["strategies"]) == 2
        assert len(config_data["risk"]["take_profit_levels"]) == 2

    @pytest.mark.asyncio
    async def test_empty_config_json_stored_correctly(self, repository):
        """Test that empty config JSON is stored correctly."""
        snapshot_id = await repository.create_config_snapshot(
            version="v1.0.0",
            config_json="{}",
            description="Empty config"
        )

        snapshot = await repository.get_config_snapshot_by_id(snapshot_id)
        assert snapshot is not None
        assert snapshot["config_json"] == "{}"


# ============================================================
# Test Class: ConfigSnapshotRepository - Edge Cases
# ============================================================
class TestConfigSnapshotRepositoryEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_very_long_description(self, repository, sample_config_json):
        """Test storing a snapshot with a very long description."""
        long_description = "A" * 1000  # 1000 character description

        snapshot_id = await repository.create_config_snapshot(
            version="v1.0.0",
            config_json=sample_config_json,
            description=long_description
        )

        snapshot = await repository.get_config_snapshot_by_id(snapshot_id)
        assert snapshot["description"] == long_description

    @pytest.mark.asyncio
    async def test_special_characters_in_description(self, repository, sample_config_json):
        """Test storing a snapshot with special characters in description."""
        special_description = "Test with special chars: \n\t\r\"'&<>\u00e9\u00e8\u00ea"

        snapshot_id = await repository.create_config_snapshot(
            version="v1.0.0",
            config_json=sample_config_json,
            description=special_description
        )

        snapshot = await repository.get_config_snapshot_by_id(snapshot_id)
        assert snapshot["description"] == special_description

    @pytest.mark.asyncio
    async def test_unicode_version_tag(self, repository, sample_config_json):
        """Test storing a snapshot with unicode version tag."""
        snapshot_id = await repository.create_config_snapshot(
            version="v1.0.0-\u7248\u672c",  # "version" in Chinese
            config_json=sample_config_json
        )

        snapshot = await repository.get_config_snapshot_by_id(snapshot_id)
        assert snapshot["version"] == "v1.0.0-\u7248\u672c"

    @pytest.mark.asyncio
    async def test_rapid_consecutive_snapshot_creation(self, repository, sample_config_json):
        """Test creating snapshots in rapid succession."""
        ids = []
        for i in range(20):
            snapshot_id = await repository.create_config_snapshot(
                version=f"v{i+1}.0.0",
                config_json=sample_config_json
            )
            ids.append(snapshot_id)

        # Verify all created successfully
        result = await repository.get_config_snapshots(limit=50, offset=0)
        assert result["total"] == 20

    @pytest.mark.asyncio
    async def test_activate_then_delete(self, repository, sample_config_json):
        """Test activating a snapshot then deleting it."""
        id1 = await repository.create_config_snapshot(
            version="v1.0.0",
            config_json=sample_config_json
        )
        id2 = await repository.create_config_snapshot(
            version="v2.0.0",
            config_json=sample_config_json
        )

        # Activate first
        await repository.activate_config_snapshot(id1)

        # Delete active snapshot
        result = await repository.delete_config_snapshot(id1)
        assert result is True

        # Verify deleted
        snapshot = await repository.get_config_snapshot_by_id(id1)
        assert snapshot is None

    @pytest.mark.asyncio
    async def test_multiple_activations_same_snapshot(self, repository, sample_config_json):
        """Test activating the same snapshot multiple times."""
        snapshot_id = await repository.create_config_snapshot(
            version="v1.0.0",
            config_json=sample_config_json
        )

        # Activate multiple times
        result1 = await repository.activate_config_snapshot(snapshot_id)
        result2 = await repository.activate_config_snapshot(snapshot_id)
        result3 = await repository.activate_config_snapshot(snapshot_id)

        assert result1 is True
        assert result2 is True
        assert result3 is True

        # Verify still active
        snapshot = await repository.get_config_snapshot_by_id(snapshot_id)
        assert snapshot["is_active"] == 1


# Import asyncio for tests that need it
import asyncio
