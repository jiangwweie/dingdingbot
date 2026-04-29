"""
E2E Integration Tests for Configuration Import/Export Functionality

Tests:
1. Export returns valid YAML with all config sections
2. Export filename format in Content-Disposition header
3. Import preview shows changes summary
4. Import confirm applies changes
5. Import auto-creates snapshot
6. Import with conflicts shows warnings
7. Rollback after import restores previous state
8. Boundary conditions: invalid YAML, missing file, token expiry

Coverage target: >= 80%
"""
import json
import os
import pytest
import tempfile
import yaml
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, Any

from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.infrastructure.repositories.config_repositories import (
    StrategyConfigRepository,
    RiskConfigRepository,
    SystemConfigRepository,
    SymbolConfigRepository,
    NotificationConfigRepository,
    ConfigHistoryRepository,
    ConfigSnapshotRepositoryExtended,
    ConfigDatabaseManager,
)
from src.interfaces.api_v1_config import (
    router,
    _import_preview_cache,
)
from src.interfaces import api_config_globals


# ============================================================
# Test Fixtures
# ============================================================

@pytest.fixture
def temp_db_path():
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
async def db_manager(temp_db_path):
    """Create and initialize ConfigDatabaseManager."""
    manager = ConfigDatabaseManager(temp_db_path)
    await manager.initialize()
    yield manager
    await manager.close()


@pytest.fixture
def app():
    """Create FastAPI app with config router."""
    app_instance = FastAPI(title="Config Import/Export E2E Test")
    app_instance.include_router(router, tags=["config"])
    return app_instance


@pytest.fixture
def client(app, db_manager):
    """Create TestClient with injected dependencies."""
    # Inject dependencies directly into shared globals
    api_config_globals._strategy_repo = db_manager.strategy_repo
    api_config_globals._risk_repo = db_manager.risk_repo
    api_config_globals._system_repo = db_manager.system_repo
    api_config_globals._symbol_repo = db_manager.symbol_repo
    api_config_globals._notification_repo = db_manager.notification_repo
    api_config_globals._history_repo = db_manager.history_repo
    api_config_globals._snapshot_repo = db_manager.snapshot_repo

    # Clear preview cache before each test
    _import_preview_cache.clear()

    with TestClient(app) as c:
        yield c


@pytest.fixture
def sample_config_yaml():
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
    - SOL/USDT:USDT
  ema_period: 50
  mtf_ema_period: 50
  mtf_mapping:
    "15m": "1h"
    "1h": "4h"
  signal_cooldown_seconds: 7200

strategies:
  - name: Pinbar + EMA Strategy
    description: Pinbar pattern with EMA trend filter
    trigger:
      type: pinbar
      enabled: true
      params:
        min_wick_ratio: 0.6
        max_body_ratio: 0.3
    filters:
      - type: ema
        enabled: true
        params:
          period: 60
      - type: mtf
        enabled: true
        params: {}
    filter_logic: AND
    symbols:
      - BTC/USDT:USDT
      - ETH/USDT:USDT
    timeframes:
      - 15m
      - 1h

symbols:
  - symbol: BTC/USDT:USDT
    is_core: true
    price_precision: 2
  - symbol: ETH/USDT:USDT
    is_core: true
    price_precision: 2
  - symbol: SOL/USDT:USDT
    is_core: false
    price_precision: 3

notifications:
  - channel_type: feishu
    webhook_url: https://open.feishu.cn/open-apis/bot/v2/hook/test123
    is_active: true
    notify_on_signal: true
    notify_on_order: true
"""


@pytest.fixture
def temp_yaml() -> str:
    """Generate valid YAML configuration string."""
    return yaml.safe_dump({
        "risk": {
            "max_loss_percent": 0.02,
            "max_leverage": 20,
            "cooldown_minutes": 300,
        },
        "system": {
            "core_symbols": ["BTC/USDT:USDT", "ETH/USDT:USDT"],
            "ema_period": 50,
            "mtf_ema_period": 50,
        },
        "strategies": [
            {
                "name": "Test Strategy",
                "trigger": {"type": "pinbar", "enabled": True, "params": {}},
                "filters": [],
                "filter_logic": "AND",
            }
        ],
        "symbols": [
            {"symbol": "BTC/USDT:USDT", "is_core": True, "price_precision": 2},
            {"symbol": "ETH/USDT:USDT", "is_core": True, "price_precision": 2},
        ],
    })


@pytest.fixture
def duplicate_strategy_yaml() -> str:
    """Generate YAML with duplicate strategy names."""
    return yaml.safe_dump({
        "strategies": [
            {
                "name": "Duplicate Strategy",
                "trigger": {"type": "pinbar", "enabled": True, "params": {}},
                "filters": [],
                "filter_logic": "AND",
            },
            {
                "name": "Duplicate Strategy",
                "trigger": {"type": "engulfing", "enabled": True, "params": {}},
                "filters": [],
                "filter_logic": "AND",
            },
        ],
    })


@pytest.fixture
def preview_token(client, temp_yaml) -> str:
    """Create a valid preview token."""
    response = client.post(
        "/api/v1/config/import/preview",
        json={"yaml_content": temp_yaml, "filename": "test.yaml"},
        headers={"X-User-Role": "admin"}
    )
    return response.json()["preview_token"]


# ============================================================
# Test Export Functionality
# ============================================================

class TestConfigExport:
    """Tests for configuration export functionality."""

    @pytest.mark.asyncio
    async def test_export_returns_valid_yaml(self, client):
        """Test that export returns valid YAML with all config sections."""
        # Setup: Create some config first
        client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.015", "max_leverage": 15},
            headers={"X-User-Role": "admin"}
        )
        client.put(
            "/api/v1/config/system",
            json={"ema": {"period": 55}, "mtf_ema_period": 55},
            headers={"X-User-Role": "admin"}
        )
        client.post(
            "/api/v1/config/strategies",
            json={
                "name": "Export Test Strategy",
                "trigger": {"type": "pinbar", "enabled": True, "params": {}},
                "filters": [],
                "filter_logic": "AND",
            },
            headers={"X-User-Role": "admin"}
        )

        # Export all configs
        response = client.post(
            "/api/v1/config/export",
            json={
                "include_risk": True,
                "include_system": True,
                "include_strategies": True,
                "include_symbols": True,
            },
            headers={"X-User-Role": "admin"}
        )

        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "yaml_content" in data

        # Verify YAML is parseable and contains all sections
        yaml_data = yaml.safe_load(data["yaml_content"])
        assert isinstance(yaml_data, dict)
        assert "risk" in yaml_data
        assert "system" in yaml_data
        assert "strategies" in yaml_data

    @pytest.mark.asyncio
    async def test_export_filename_in_header(self, client):
        """Test that export response contains proper filename."""
        response = client.post(
            "/api/v1/config/export",
            json={"include_risk": True},
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 200
        data = response.json()

        # Verify filename format: config_backup_YYYYMMDD_HHMMSS.yaml
        filename = data["filename"]
        assert filename.startswith("config_backup_")
        assert filename.endswith(".yaml")

        import re
        assert re.match(r'config_backup_\d{8}_\d{6}\.yaml', filename), \
            f"Filename should match pattern, got: {filename}"


# ============================================================
# Test Import Preview Functionality
# ============================================================

class TestConfigImport:
    """Tests for configuration import functionality."""

    @pytest.mark.asyncio
    async def test_import_preview_shows_changes(self, client, temp_yaml):
        """Test that import preview shows changes summary."""
        response = client.post(
            "/api/v1/config/import/preview",
            json={"yaml_content": temp_yaml, "filename": "test.yaml"},
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 200
        data = response.json()

        # Verify preview is valid
        assert data["valid"] is True
        assert "preview_token" in data
        assert data["preview_token"] is not None

        # Verify summary contains expected sections
        summary = data["summary"]
        assert "strategies" in summary
        assert "risk" in summary
        assert "symbols" in summary

    @pytest.mark.asyncio
    async def test_import_confirm_applies_changes(self, client, temp_yaml):
        """Test that import confirm applies configuration changes."""
        # Preview first
        preview_response = client.post(
            "/api/v1/config/import/preview",
            json={"yaml_content": temp_yaml, "filename": "test_apply.yaml"},
            headers={"X-User-Role": "admin"}
        )
        preview_token = preview_response.json()["preview_token"]

        # Confirm import
        confirm_response = client.post(
            "/api/v1/config/import/confirm",
            json={"preview_token": preview_token},
            headers={"X-User-Role": "admin"}
        )

        assert confirm_response.status_code == 200
        data = confirm_response.json()
        assert data["status"] == "success"

        # Verify config was applied - check risk config
        risk_response = client.get("/api/v1/config/risk")
        assert risk_response.status_code == 200
        risk_data = risk_response.json()
        # The temp_yaml has max_leverage: 20
        assert risk_data["max_leverage"] == 20

    @pytest.mark.asyncio
    async def test_import_auto_creates_snapshot(self, client, temp_yaml):
        """Test that import confirm auto-creates a snapshot."""
        # Preview
        preview_response = client.post(
            "/api/v1/config/import/preview",
            json={"yaml_content": temp_yaml, "filename": "snapshot_test.yaml"},
            headers={"X-User-Role": "admin"}
        )
        preview_token = preview_response.json()["preview_token"]

        # Confirm import
        confirm_response = client.post(
            "/api/v1/config/import/confirm",
            json={"preview_token": preview_token},
            headers={"X-User-Role": "admin"}
        )

        assert confirm_response.status_code == 200
        data = confirm_response.json()

        # Verify snapshot was created
        assert "snapshot_id" in data
        assert data["snapshot_id"] is not None

        # Verify snapshot exists by getting snapshot details
        snapshot_id = data["snapshot_id"]
        snapshot_response = client.get(f"/api/v1/config/snapshots/{snapshot_id}")
        assert snapshot_response.status_code == 200

    @pytest.mark.asyncio
    async def test_import_with_conflicts_shows_warning(self, client, duplicate_strategy_yaml):
        """Test that import preview detects duplicate strategy names."""
        response = client.post(
            "/api/v1/config/import/preview",
            json={"yaml_content": duplicate_strategy_yaml, "filename": "duplicate.yaml"},
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 200
        data = response.json()

        # YAML is valid but has conflicts
        assert data["valid"] is True
        assert "conflicts" in data
        assert len(data["conflicts"]) > 0

        # Verify conflict message mentions duplicate
        assert any("Duplicate" in c for c in data["conflicts"])


# ============================================================
# Test Rollback Functionality
# ============================================================

class TestConfigRollback:
    """Tests for configuration rollback functionality."""

    @pytest.mark.asyncio
    async def test_rollback_after_import(self, client, temp_yaml):
        """Test that rollback restores config to pre-import state."""
        # Step 1: Set initial config
        client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.01", "max_leverage": 10},
            headers={"X-User-Role": "admin"}
        )

        # Record original state
        before_response = client.get("/api/v1/config/risk")
        original_max_leverage = before_response.json()["max_leverage"]
        assert original_max_leverage == 10

        # Step 2: Create a snapshot manually
        snapshot_response = client.post(
            "/api/v1/config/snapshots",
            json={"name": "pre_import_test", "description": "Snapshot before import test"},
            headers={"X-User-Role": "admin"}
        )
        assert snapshot_response.status_code == 201
        snapshot_id = snapshot_response.json()["id"]

        # Step 3: Import new config with different values
        new_yaml = yaml.safe_dump({
            "risk": {"max_loss_percent": 0.03, "max_leverage": 30},
        })

        preview_response = client.post(
            "/api/v1/config/import/preview",
            json={"yaml_content": new_yaml, "filename": "import_for_rollback.yaml"},
            headers={"X-User-Role": "admin"}
        )
        preview_token = preview_response.json()["preview_token"]

        confirm_response = client.post(
            "/api/v1/config/import/confirm",
            json={"preview_token": preview_token},
            headers={"X-User-Role": "admin"}
        )
        assert confirm_response.status_code == 200

        # Step 4: Verify config changed after import
        after_import_response = client.get("/api/v1/config/risk")
        after_import_data = after_import_response.json()
        assert after_import_data["max_leverage"] == 30

        # Step 5: Rollback to snapshot
        rollback_response = client.post(
            f"/api/v1/config/snapshots/{snapshot_id}/activate",
            headers={"X-User-Role": "admin"}
        )
        assert rollback_response.status_code == 200

        # Step 6: Verify config restored to original state
        restored_response = client.get("/api/v1/config/risk")
        restored_data = restored_response.json()
        assert restored_data["max_leverage"] == original_max_leverage


# ============================================================
# Test Import Boundary Conditions
# ============================================================

class TestImportBoundaryCases:
    """Tests for import boundary conditions and error handling."""

    @pytest.mark.asyncio
    async def test_import_invalid_yaml_returns_400(self, client):
        """Test that importing invalid YAML returns error."""
        invalid_yaml = """
risk:
  max_loss_percent: invalid
  [not valid yaml syntax
"""
        response = client.post(
            "/api/v1/config/import/preview",
            json={"yaml_content": invalid_yaml, "filename": "invalid.yaml"},
            headers={"X-User-Role": "admin"}
        )

        data = response.json()
        assert data["valid"] is False
        assert len(data["errors"]) > 0

    @pytest.mark.asyncio
    async def test_preview_token_expiry(self, client, temp_yaml):
        """Test that preview token expiry is handled correctly."""
        # Get a preview token
        preview_response = client.post(
            "/api/v1/config/import/preview",
            json={"yaml_content": temp_yaml, "filename": "expiry_test.yaml"},
            headers={"X-User-Role": "admin"}
        )
        preview_token = preview_response.json()["preview_token"]

        # Simulate token expiry by removing from cache
        del _import_preview_cache[preview_token]

        # Try to confirm with expired token
        confirm_response = client.post(
            "/api/v1/config/import/confirm",
            json={"preview_token": preview_token},
            headers={"X-User-Role": "admin"}
        )

        assert confirm_response.status_code == 400
        error_data = confirm_response.json()
        assert "detail" in error_data
        assert "expired" in error_data["detail"].lower() or "invalid" in error_data["detail"].lower()

    @pytest.mark.asyncio
    async def test_import_missing_file_returns_400(self, client):
        """Test that import with missing file returns 400."""
        # Send request without yaml_content field
        response = client.post(
            "/api/v1/config/import/preview",
            json={},
            headers={"X-User-Role": "admin"}
        )

        # FastAPI should return 422 for missing required field
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_import_nonexistent_token_returns_400(self, client):
        """Test that using nonexistent preview token returns 400."""
        response = client.post(
            "/api/v1/config/import/confirm",
            json={"preview_token": "nonexistent-token-12345"},
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 400


# ============================================================
# Integration Tests
# ============================================================

class TestImportExportIntegration:
    """Integration tests for complete import/export workflow."""

    @pytest.mark.asyncio
    async def test_full_export_import_cycle(self, client):
        """Test complete export -> modify -> import cycle."""
        # 1. Create initial config
        client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.01", "max_leverage": 10},
            headers={"X-User-Role": "admin"}
        )

        # 2. Export
        export_response = client.post(
            "/api/v1/config/export",
            json={"include_risk": True},
            headers={"X-User-Role": "admin"}
        )
        assert export_response.status_code == 200
        yaml_content = export_response.json()["yaml_content"]

        # 3. Modify exported YAML
        modified_yaml = yaml_content.replace("0.01", "0.03")

        # 4. Preview import
        preview_response = client.post(
            "/api/v1/config/import/preview",
            json={"yaml_content": modified_yaml, "filename": "modified.yaml"},
            headers={"X-User-Role": "admin"}
        )
        assert preview_response.status_code == 200
        preview_token = preview_response.json()["preview_token"]

        # 5. Confirm import
        confirm_response = client.post(
            "/api/v1/config/import/confirm",
            json={"preview_token": preview_token},
            headers={"X-User-Role": "admin"}
        )
        assert confirm_response.status_code == 200

        # 6. Verify config was updated
        get_response = client.get("/api/v1/config/risk")
        data = get_response.json()
        assert data["max_loss_percent"] == "0.03"

    @pytest.mark.asyncio
    async def test_import_preview_cleans_cache_after_confirm(self, client, temp_yaml):
        """Test that preview cache is cleaned after confirm."""
        # Preview
        preview_response = client.post(
            "/api/v1/config/import/preview",
            json={"yaml_content": temp_yaml, "filename": "cleanup_test.yaml"},
            headers={"X-User-Role": "admin"}
        )
        preview_token = preview_response.json()["preview_token"]

        # Verify token is in cache
        assert preview_token in _import_preview_cache

        # Confirm import
        client.post(
            "/api/v1/config/import/confirm",
            json={"preview_token": preview_token},
            headers={"X-User-Role": "admin"}
        )

        # Token should be removed from cache
        assert preview_token not in _import_preview_cache


# ============================================================
# History Recording Tests
# ============================================================

class TestImportExportHistoryRecording:
    """Tests for verifying import/export operations are recorded to history."""

    @pytest.mark.asyncio
    async def test_export_records_to_history(self, client, db_manager):
        """Test that export operation is recorded to config_history table."""
        # Create some config first
        client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.01", "max_leverage": 10},
            headers={"X-User-Role": "admin"}
        )
        client.put(
            "/api/v1/config/system",
            json={"ema": {"period": 50}, "mtf_ema_period": 50},
            headers={"X-User-Role": "admin"}
        )

        # Export config
        response = client.post(
            "/api/v1/config/export",
            json={
                "include_risk": True,
                "include_system": True,
                "include_strategies": False,
            },
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

        # Verify history record was created
        history_records, total = await db_manager.history_repo.get_history(
            entity_type="config_bundle",
            entity_id="export",
            limit=10
        )

        assert total >= 1
        assert len(history_records) >= 1

        # Check the latest record
        latest_record = history_records[0]
        assert latest_record["action"] == "EXPORT"
        assert latest_record["changed_by"] == "admin"

        # Verify new_values contains filename and sections
        new_values = latest_record["new_values"]
        if isinstance(new_values, str):
            new_values = json.loads(new_values)
        assert "filename" in new_values
        assert "sections" in new_values
        assert "risk" in new_values["sections"]
        assert "system" in new_values["sections"]

    @pytest.mark.asyncio
    async def test_import_records_to_history(self, client, db_manager):
        """Test that import operation is recorded to config_history table."""
        yaml_content = """
risk:
  max_loss_percent: 0.025
  max_leverage: 25
  cooldown_minutes: 120
system:
  core_symbols:
    - BTC/USDT:USDT
    - ETH/USDT:USDT
  ema_period: 45
strategies:
  - name: Import Test Strategy
    trigger:
      type: pinbar
      enabled: true
      params: {}
    filters: []
    filter_logic: AND
"""
        # Preview import
        preview_response = client.post(
            "/api/v1/config/import/preview",
            json={"yaml_content": yaml_content, "filename": "test_import.yaml"},
            headers={"X-User-Role": "admin"}
        )

        assert preview_response.status_code == 200
        preview_token = preview_response.json()["preview_token"]

        # Confirm import
        confirm_response = client.post(
            "/api/v1/config/import/confirm",
            json={"preview_token": preview_token},
            headers={"X-User-Role": "admin"}
        )

        assert confirm_response.status_code == 200

        # Verify history record was created
        history_records, total = await db_manager.history_repo.get_history(
            entity_type="config_bundle",
            entity_id="import",
            limit=10
        )

        assert total >= 1
        assert len(history_records) >= 1

        # Check the latest record
        latest_record = history_records[0]
        assert latest_record["action"] == "IMPORT"
        assert latest_record["changed_by"] == "admin"
        assert "test_import.yaml" in latest_record["change_summary"]
        assert "risk" in latest_record["change_summary"]

        # Verify new_values contains filename and snapshot_id
        new_values = latest_record["new_values"]
        if isinstance(new_values, str):
            new_values = json.loads(new_values)
        assert "filename" in new_values
        assert "snapshot_id" in new_values
        assert new_values["filename"] == "test_import.yaml"


# ============================================================
# Main entry point
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
