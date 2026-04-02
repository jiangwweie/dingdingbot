"""
Integration tests for config snapshot API endpoints.
"""
import pytest
import json
import tempfile
import os
import asyncio
from decimal import Decimal

from fastapi.testclient import TestClient

from src.interfaces.api import app, set_dependencies
from src.infrastructure.signal_repository import SignalRepository
from src.application.config_manager import ConfigManager
from src.application.config_snapshot_service import ConfigSnapshotService
from src.infrastructure.config_snapshot_repository import ConfigSnapshotRepository


@pytest.fixture
def temp_config_dir():
    """Create temporary directory with test config files."""
    from pathlib import Path
    import yaml

    tmpdir = tempfile.mkdtemp()
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
            "api_key": "test_api_key_12345",
            "api_secret": "test_api_secret_67890",
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
            "channels": [{"type": "feishu", "webhook_url": "https://example.com/webhook"}],
        },
    }

    with open(config_dir / "user.yaml", "w") as f:
        yaml.dump(user_config, f)

    yield tmpdir

    # Cleanup
    import shutil
    shutil.rmtree(tmpdir)


@pytest.fixture
def test_client(temp_config_dir):
    """Create test client with initialized dependencies."""
    async def setup():
        # Initialize repository
        temp_db = os.path.join(temp_config_dir, "test.db")
        repo = SignalRepository(db_path=temp_db)
        await repo.initialize()

        # Initialize config manager
        config_manager = ConfigManager(config_dir=temp_config_dir)
        config_manager.load_core_config()
        config_manager.load_user_config()
        config_manager.merge_symbols()

        # Initialize snapshot service
        snapshot_repo = ConfigSnapshotRepository(db_path=temp_db)
        await snapshot_repo.initialize()
        snapshot_service = ConfigSnapshotService(snapshot_repo)

        # Set dependencies
        def get_account():
            return None

        set_dependencies(
            repository=repo,
            account_getter=get_account,
            config_manager=config_manager,
            snapshot_service=snapshot_service,
        )

        return repo, snapshot_repo

    async def cleanup(repo, snapshot_repo):
        await repo.close()
        await snapshot_repo.close()

    # Setup
    repo, snapshot_repo = asyncio.run(setup())

    client = TestClient(app)
    yield client

    # Cleanup
    asyncio.run(cleanup(repo, snapshot_repo))


class TestConfigAPI:
    """Test config API endpoints."""

    def test_get_config(self, test_client):
        """Test GET /api/config returns masked config."""
        response = test_client.get("/api/config")
        assert response.status_code == 200

        data = response.json()
        assert "status" in data or "config" in data

        # Config should be in response (either as direct value or under "config" key)
        config = data.get("config", data)

        # Check exchange info exists
        assert "exchange" in config

    def test_update_config(self, test_client):
        """Test PUT /api/config updates configuration."""
        update_data = {
            "risk": {
                "max_loss_percent": 0.02,
                "max_leverage": 5,
            }
        }

        response = test_client.put("/api/config", json=update_data)
        assert response.status_code == 200

        data = response.json()
        # Response should indicate success
        assert data.get("status") == "success" or "message" in data


class TestConfigExportImportAPI:
    """Test config export/import API endpoints."""

    def test_export_config(self, test_client):
        """Test GET /api/config/export returns YAML file."""
        response = test_client.get("/api/config/export")
        assert response.status_code == 200
        assert "application/x-yaml" in response.headers["content-type"]
        assert "attachment" in response.headers["content-disposition"]

        # Verify YAML content
        import yaml
        content = yaml.safe_load(response.content)
        assert "exchange" in content
        assert "risk" in content

    def test_import_config(self, test_client, temp_config_dir):
        """Test POST /api/config/import imports YAML configuration."""
        # Create import data
        import yaml
        import_data = {
            "risk": {
                "max_loss_percent": "0.03",
                "max_leverage": 15,
            },
            "timeframes": ["15m", "1h"],
        }

        # Write to temp file
        temp_file = os.path.join(temp_config_dir, "import_config.yaml")
        with open(temp_file, "w") as f:
            yaml.dump(import_data, f)

        # Import
        with open(temp_file, "rb") as f:
            response = test_client.post(
                "/api/config/import",
                files={"file": ("config.yaml", f, "application/x-yaml")},
                data={"description": "Test import"},
            )

        # Response should be success or contain config
        assert response.status_code == 200
        data = response.json()
        # Accept either success status or config data
        assert data.get("status") == "success" or "config" in data or "message" in data


class TestConfigSnapshotsAPI:
    """Test config snapshot API endpoints."""

    def test_create_snapshot(self, test_client):
        """Test POST /api/config/snapshots creates snapshot."""
        payload = {
            "version": "v1.0.0",
            "description": "Test snapshot",
        }

        response = test_client.post("/api/config/snapshots", json=payload)
        assert response.status_code == 200

        data = response.json()
        assert data["id"] is not None
        assert data["version"] == "v1.0.0"
        assert data["is_active"] is True

    def test_list_snapshots(self, test_client):
        """Test GET /api/config/snapshots lists snapshots."""
        # Create a snapshot first
        test_client.post("/api/config/snapshots", json={
            "version": "v1.0.0",
            "description": "Test",
        })

        response = test_client.get("/api/config/snapshots")
        assert response.status_code == 200

        data = response.json()
        assert "total" in data
        assert "data" in data
        assert data["total"] >= 1

    def test_get_snapshot(self, test_client):
        """Test GET /api/config/snapshots/{id} retrieves snapshot."""
        # Create a snapshot first
        create_response = test_client.post("/api/config/snapshots", json={
            "version": "v1.0.0",
            "description": "Test",
        })
        snapshot_id = create_response.json()["id"]

        # Retrieve
        response = test_client.get(f"/api/config/snapshots/{snapshot_id}")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == snapshot_id
        assert data["version"] == "v1.0.0"

    def test_get_snapshot_not_found(self, test_client):
        """Test GET /api/config/snapshots/{id} returns 404 for non-existent."""
        response = test_client.get("/api/config/snapshots/99999")
        assert response.status_code == 404

    def test_activate_snapshot(self, test_client):
        """Test POST /api/config/snapshots/{id}/activate activates snapshot."""
        # Create two snapshots
        r1 = test_client.post("/api/config/snapshots", json={
            "version": "v1.0.0",
            "description": "First",
        })
        id1 = r1.json()["id"]

        r2 = test_client.post("/api/config/snapshots", json={
            "version": "v2.0.0",
            "description": "Second",
        })
        id2 = r2.json()["id"]

        # Activate first
        response = test_client.post(f"/api/config/snapshots/{id1}/activate")
        assert response.status_code == 200

        # Verify first is active
        r = test_client.get(f"/api/config/snapshots/{id1}")
        assert r.json()["is_active"] is True

        # Verify second is inactive
        r = test_client.get(f"/api/config/snapshots/{id2}")
        assert r.json()["is_active"] is False

    def test_rollback_snapshot(self, test_client):
        """Test POST /api/config/snapshots/{id}/rollback rolls back config."""
        # Create a snapshot
        create_response = test_client.post("/api/config/snapshots", json={
            "version": "v1.0.0",
            "description": "Test rollback",
        })
        snapshot_id = create_response.json()["id"]

        # Rollback
        response = test_client.post(f"/api/config/snapshots/{snapshot_id}/rollback")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "success"
        assert "snapshot" in data

    def test_delete_snapshot(self, test_client):
        """Test DELETE /api/config/snapshots/{id} deletes snapshot."""
        # Create multiple snapshots
        ids = []
        for i in range(6):
            r = test_client.post("/api/config/snapshots", json={
                "version": f"v{i+1}.0.0",
                "description": f"Snapshot {i+1}",
            })
            ids.append(r.json()["id"])

        # Delete oldest (should succeed as it's not in recent 5)
        response = test_client.delete(f"/api/config/snapshots/{ids[0]}")
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_delete_protected_snapshot(self, test_client):
        """Test DELETE /api/config/snapshots/{id} fails for protected snapshot."""
        # Create a snapshot
        r = test_client.post("/api/config/snapshots", json={
            "version": "v1.0.0",
            "description": "Protected",
        })
        snapshot_id = r.json()["id"]

        # Try to delete (should fail as it's in recent 5)
        response = test_client.delete(f"/api/config/snapshots/{snapshot_id}")
        assert response.status_code == 400
