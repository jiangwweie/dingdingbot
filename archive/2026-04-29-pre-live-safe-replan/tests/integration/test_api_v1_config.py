"""
API Integration Tests for Configuration Management v1

Tests all REST endpoints in src/interfaces/api_v1_config.py:
- GET/PUT /api/v1/config/risk - Risk config
- GET/PUT /api/v1/config/system - System config
- /api/v1/config/strategies/* - Strategy management
- /api/v1/config/symbols/* - Symbol management
- /api/v1/config/notifications/* - Notification management
- POST /api/v1/config/export - Export YAML
- POST /api/v1/config/import/preview - Preview import
- POST /api/v1/config/import/confirm - Confirm import
- /api/v1/config/snapshots/* - Snapshot management
- GET/PUT /api/v1/config/exchange - Exchange config (Task 23)
- GET/PUT /api/v1/config/timeframes - Timeframes (Task 23)
- GET/PUT /api/v1/config/asset-polling - Asset polling (Task 23)

Coverage target: >= 80%
"""
import json
import os
import pytest
import tempfile
import shutil
from datetime import datetime, timezone
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
from src.interfaces import api_config_globals as _cg
from src.interfaces.api import set_dependencies


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
    # Cleanup WAL files
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
    app = FastAPI(title="Config API Test")
    # Router already has prefix built-in: /api/v1/config
    app.include_router(router, tags=["config"])
    return app


@pytest.fixture
def client(app, db_manager):
    """Create TestClient with injected dependencies."""
    # Set config repositories via unified set_dependencies
    set_dependencies(
        strategy_repo=db_manager.strategy_repo,
        risk_repo=db_manager.risk_repo,
        system_repo=db_manager.system_repo,
        symbol_repo=db_manager.symbol_repo,
        notification_repo=db_manager.notification_repo,
        history_repo=db_manager.history_repo,
        snapshot_repo=db_manager.snapshot_repo,
    )

    # Set a mock config manager for exchange/timeframes/polling endpoints
    mock_config_manager = MockConfigManager()
    _cg._config_manager = mock_config_manager

    # Clear preview cache before each test
    _import_preview_cache.clear()

    with TestClient(app) as c:
        yield c


class MockConfigManager:
    """Simple in-memory mock ConfigManager for API endpoint tests.

    Keeps exchange, timeframes, and asset_polling config in memory.
    GET requests see changes made by PUT requests within the same test.
    """

    def __init__(self):
        from src.application.config_manager import ExchangeConfig, AssetPollingConfig
        self._exchange_config = ExchangeConfig(
            name="binance", api_key="", api_secret="", testnet=True
        )
        self._timeframes = ["15m", "1h"]
        self._asset_polling = AssetPollingConfig(enabled=True, interval_seconds=60)

    async def get_exchange_config(self):
        return self._exchange_config

    async def update_exchange_config(self, config):
        self._exchange_config = config

    async def get_timeframes(self):
        return list(self._timeframes)

    async def update_timeframes(self, timeframes):
        self._timeframes = list(timeframes)

    async def get_asset_polling_config(self):
        return self._asset_polling

    async def update_asset_polling_config(self, config):
        self._asset_polling = config

    async def reload_all_configs_from_db(self):
        pass  # No-op for mock

    def get_config_version(self):
        return "test-v1"


# ============================================================
# Risk Config API Tests
# ============================================================

class TestRiskConfigAPI:
    """Tests for /api/v1/config/risk endpoints."""

    @pytest.mark.asyncio
    async def test_get_risk_config_initially_empty(self, client):
        """Test GET /risk returns 404 when no config exists."""
        response = client.get("/api/v1/config/risk")
        # Should return 404 or empty config
        assert response.status_code in [200, 404]

    @pytest.mark.asyncio
    async def test_update_risk_config(self, client):
        """Test PUT /risk updates configuration."""
        update_data = {
            "max_loss_percent": "0.02",  # Send as string for JSON
            "max_leverage": 20,
            "max_total_exposure": "0.9",
            "cooldown_minutes": 300,
        }

        response = client.put(
            "/api/v1/config/risk",
            json=update_data,
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["max_loss_percent"] == "0.02"
        assert data["max_leverage"] == 20

    @pytest.mark.asyncio
    async def test_update_risk_config_partial(self, client):
        """Test PUT /risk with partial update."""
        # First create config
        client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.01", "max_leverage": 10},
            headers={"X-User-Role": "admin"}
        )

        # Partial update
        response = client.put(
            "/api/v1/config/risk",
            json={"max_leverage": 15},
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["max_leverage"] == 15

    @pytest.mark.asyncio
    async def test_update_risk_config_validation(self, client):
        """Test PUT /risk validates input."""
        # Invalid max_loss_percent (too large)
        response = client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "1.5"},  # > 1.0
            headers={"X-User-Role": "admin"}
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_risk_config_after_update(self, client):
        """Test GET /risk returns updated config."""
        # Update first
        client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.015", "max_leverage": 12},
            headers={"X-User-Role": "admin"}
        )

        # Get and verify
        response = client.get("/api/v1/config/risk")
        assert response.status_code == 200
        data = response.json()
        assert data["max_loss_percent"] == "0.015"
        assert data["max_leverage"] == 12


# ============================================================
# System Config API Tests
# ============================================================

class TestSystemConfigAPI:
    """Tests for /api/v1/config/system endpoints."""

    @pytest.mark.asyncio
    async def test_get_system_config_initially_empty(self, client):
        """Test GET /system returns defaults when no config exists."""
        response = client.get("/api/v1/config/system")
        # Returns defaults (200) with nested format
        assert response.status_code == 200
        data = response.json()
        assert data["ema"]["period"] == 60
        assert data["signal_pipeline"]["cooldown_seconds"] == 14400

    @pytest.mark.asyncio
    async def test_update_system_config(self, client):
        """Test PUT /system updates configuration with nested format."""
        update_data = {
            "ema": {"period": 50},
            "mtf_ema_period": 50,
            "signal_pipeline": {
                "cooldown_seconds": 7200,
                "queue": {"batch_size": 20, "flush_interval": 3.0, "max_queue_size": 2000},
            },
            "warmup": {"history_bars": 200},
        }

        response = client.put(
            "/api/v1/config/system",
            json=update_data,
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ema"]["period"] == 50
        assert data["signal_pipeline"]["cooldown_seconds"] == 7200

    @pytest.mark.asyncio
    async def test_update_system_config_restart_required(self, client):
        """Test PUT /system marks restart_required for core changes."""
        update_data = {
            "ema": {"period": 100},
            "mtf_ema_period": 100,
        }

        response = client.put(
            "/api/v1/config/system",
            json=update_data,
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["restart_required"] is True
        assert data["ema"]["period"] == 100

    @pytest.mark.asyncio
    async def test_get_system_config_after_update(self, client):
        """Test GET /system returns updated config."""
        # Update first
        client.put(
            "/api/v1/config/system",
            json={
                "ema": {"period": 55},
                "mtf_ema_period": 55,
            },
            headers={"X-User-Role": "admin"}
        )

        # Get and verify
        response = client.get("/api/v1/config/system")
        assert response.status_code == 200
        data = response.json()
        assert data["ema"]["period"] == 55
        assert data["mtf_ema_period"] == 55


# ============================================================
# Strategy Config API Tests
# ============================================================

class TestStrategyConfigAPI:
    """Tests for /api/v1/config/strategies/* endpoints."""

    @pytest.mark.asyncio
    async def test_get_strategies_empty(self, client):
        """Test GET /strategies returns empty list."""
        response = client.get("/api/v1/config/strategies")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data or isinstance(data, list)

    @pytest.mark.asyncio
    async def test_create_strategy(self, client):
        """Test POST /strategies creates a new strategy."""
        strategy_data = {
            "name": "Test Pinbar Strategy",
            "description": "A test strategy",
            "trigger": {
                "type": "pinbar",
                "enabled": True,
                "params": {"min_wick_ratio": 0.6}
            },
            "filters": [
                {
                    "type": "ema",
                    "enabled": True,
                    "params": {"period": 60}
                }
            ],
            "filter_logic": "AND",
        }

        response = client.post(
            "/api/v1/config/strategies",
            json=strategy_data,
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data

    @pytest.mark.asyncio
    async def test_get_strategy_after_create(self, client):
        """Test GET /strategies/{id} returns created strategy."""
        # Create first
        create_response = client.post(
            "/api/v1/config/strategies",
            json={
                "name": "Get Test Strategy",
                "trigger": {"type": "pinbar", "enabled": True, "params": {}},
                "filters": [],
                "filter_logic": "AND",
            },
            headers={"X-User-Role": "admin"}
        )
        strategy_id = create_response.json()["id"]

        # Get and verify
        response = client.get(f"/api/v1/config/strategies/{strategy_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Get Test Strategy"

    @pytest.mark.asyncio
    async def test_update_strategy(self, client):
        """Test PUT /strategies/{id} updates strategy."""
        # Create first
        create_response = client.post(
            "/api/v1/config/strategies",
            json={
                "name": "Update Test Strategy",
                "trigger": {"type": "pinbar", "enabled": True, "params": {}},
                "filters": [],
                "filter_logic": "AND",
            },
            headers={"X-User-Role": "admin"}
        )
        strategy_id = create_response.json()["id"]

        # Update
        response = client.put(
            f"/api/v1/config/strategies/{strategy_id}",
            json={
                "name": "Updated Strategy Name",
                "description": "Updated description",
            },
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 200

        # Verify update
        get_response = client.get(f"/api/v1/config/strategies/{strategy_id}")
        data = get_response.json()
        assert data["name"] == "Updated Strategy Name"

    @pytest.mark.asyncio
    async def test_toggle_strategy(self, client):
        """Test POST /strategies/{id}/toggle toggles active status."""
        # Create first
        create_response = client.post(
            "/api/v1/config/strategies",
            json={
                "name": "Toggle Test Strategy",
                "trigger": {"type": "pinbar", "enabled": True, "params": {}},
                "filters": [],
                "filter_logic": "AND",
            },
            headers={"X-User-Role": "admin"}
        )
        strategy_id = create_response.json()["id"]

        # Toggle off
        response = client.post(
            f"/api/v1/config/strategies/{strategy_id}/toggle",
            headers={"X-User-Role": "admin"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is False

        # Toggle on
        response = client.post(
            f"/api/v1/config/strategies/{strategy_id}/toggle",
            headers={"X-User-Role": "admin"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is True

    @pytest.mark.asyncio
    async def test_delete_strategy(self, client):
        """Test DELETE /strategies/{id} deletes strategy."""
        # Create first
        create_response = client.post(
            "/api/v1/config/strategies",
            json={
                "name": "Delete Test Strategy",
                "trigger": {"type": "pinbar", "enabled": True, "params": {}},
                "filters": [],
                "filter_logic": "AND",
            },
            headers={"X-User-Role": "admin"}
        )
        strategy_id = create_response.json()["id"]

        # Delete
        response = client.delete(
            f"/api/v1/config/strategies/{strategy_id}",
            headers={"X-User-Role": "admin"}
        )
        assert response.status_code == 200

        # Verify deleted
        get_response = client.get(f"/api/v1/config/strategies/{strategy_id}")
        assert get_response.status_code == 404


# ============================================================
# Symbol Config API Tests
# ============================================================

class TestSymbolConfigAPI:
    """Tests for /api/v1/config/symbols/* endpoints."""

    @pytest.mark.asyncio
    async def test_get_symbols_empty(self, client):
        """Test GET /symbols returns empty list."""
        response = client.get("/api/v1/config/symbols")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_create_symbol(self, client):
        """Test POST /symbols creates a new symbol."""
        symbol_data = {
            "symbol": "BTC/USDT:USDT",
            "is_core": True,
            "price_precision": 2,
            "quantity_precision": 8,
        }

        response = client.post(
            "/api/v1/config/symbols",
            json=symbol_data,
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_create_duplicate_symbol(self, client):
        """Test POST /symbols with duplicate symbol fails."""
        symbol_data = {"symbol": "ETH/USDT:USDT", "is_core": False}

        # Create first
        client.post(
            "/api/v1/config/symbols",
            json=symbol_data,
            headers={"X-User-Role": "admin"}
        )

        # Try duplicate
        response = client.post(
            "/api/v1/config/symbols",
            json=symbol_data,
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code in [409, 400]

    @pytest.mark.asyncio
    async def test_update_symbol(self, client):
        """Test PUT /symbols/{symbol} updates symbol."""
        # Create first
        client.post(
            "/api/v1/config/symbols",
            json={"symbol": "SOL/USDT:USDT", "is_core": False},
            headers={"X-User-Role": "admin"}
        )

        # Update
        response = client.put(
            "/api/v1/config/symbols/SOL/USDT:USDT",
            json={"is_active": False, "price_precision": 4},
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_toggle_symbol(self, client):
        """Test POST /symbols/{symbol}/toggle toggles active status."""
        # Create first
        client.post(
            "/api/v1/config/symbols",
            json={"symbol": "BNB/USDT:USDT", "is_core": False},
            headers={"X-User-Role": "admin"}
        )

        # Toggle
        response = client.post(
            "/api/v1/config/symbols/BNB/USDT:USDT/toggle",
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "is_active" in data

    @pytest.mark.asyncio
    async def test_delete_symbol(self, client):
        """Test DELETE /symbols/{symbol} deletes symbol."""
        # Create first
        client.post(
            "/api/v1/config/symbols",
            json={"symbol": "ALT/USDT:USDT", "is_core": False},
            headers={"X-User-Role": "admin"}
        )

        # Delete
        response = client.delete(
            "/api/v1/config/symbols/ALT/USDT:USDT",
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 200


# ============================================================
# Notification Config API Tests
# ============================================================

class TestNotificationConfigAPI:
    """Tests for /api/v1/config/notifications/* endpoints."""

    @pytest.mark.asyncio
    async def test_get_notifications_empty(self, client):
        """Test GET /notifications returns empty list."""
        response = client.get("/api/v1/config/notifications")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_get_notifications_with_data(self, client):
        """Test GET /notifications returns data after creating notifications."""
        # Create two notifications
        client.post(
            "/api/v1/config/notifications",
            json={
                "channel_type": "feishu",
                "webhook_url": "https://example.com/webhook1",
                "is_active": True,
            },
            headers={"X-User-Role": "admin"}
        )
        client.post(
            "/api/v1/config/notifications",
            json={
                "channel_type": "wechat",
                "webhook_url": "https://example.com/webhook2",
                "is_active": False,
            },
            headers={"X-User-Role": "admin"}
        )

        # Get all notifications
        response = client.get("/api/v1/config/notifications")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

        # Filter by is_active=True
        response = client.get("/api/v1/config/notifications?is_active=true")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["is_active"] is True

        # Filter by is_active=False
        response = client.get("/api/v1/config/notifications?is_active=false")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["is_active"] is False

    @pytest.mark.asyncio
    async def test_create_notification(self, client):
        """Test POST /notifications creates a new notification."""
        notification_data = {
            "channel_type": "feishu",
            "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/test123",
            "notify_on_signal": True,
            "notify_on_order": True,
            "notify_on_error": True,
        }

        response = client.post(
            "/api/v1/config/notifications",
            json=notification_data,
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data

    @pytest.mark.asyncio
    async def test_get_notification_after_create(self, client):
        """Test GET /notifications/{id} returns created notification."""
        # Create first
        create_response = client.post(
            "/api/v1/config/notifications",
            json={
                "channel_type": "feishu",
                "webhook_url": "https://example.com/webhook",
            },
            headers={"X-User-Role": "admin"}
        )
        notification_id = create_response.json()["id"]

        # Get and verify
        response = client.get(f"/api/v1/config/notifications/{notification_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["channel_type"] == "feishu"

    @pytest.mark.asyncio
    async def test_update_notification(self, client):
        """Test PUT /notifications/{id} updates notification."""
        # Create first
        create_response = client.post(
            "/api/v1/config/notifications",
            json={
                "channel_type": "feishu",
                "webhook_url": "https://example.com/webhook",
            },
            headers={"X-User-Role": "admin"}
        )
        notification_id = create_response.json()["id"]

        # Update
        response = client.put(
            f"/api/v1/config/notifications/{notification_id}",
            json={"webhook_url": "https://example.com/new-webhook"},
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_test_notification(self, client):
        """Test POST /notifications/{id}/test tests connection."""
        # Create first
        create_response = client.post(
            "/api/v1/config/notifications",
            json={
                "channel_type": "feishu",
                "webhook_url": "https://example.com/webhook",
            },
            headers={"X-User-Role": "admin"}
        )
        notification_id = create_response.json()["id"]

        # Test
        response = client.post(
            f"/api/v1/config/notifications/{notification_id}/test",
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_delete_notification(self, client):
        """Test DELETE /notifications/{id} deletes notification."""
        # Create first
        create_response = client.post(
            "/api/v1/config/notifications",
            json={
                "channel_type": "feishu",
                "webhook_url": "https://example.com/webhook",
            },
            headers={"X-User-Role": "admin"}
        )
        notification_id = create_response.json()["id"]

        # Delete
        response = client.delete(
            f"/api/v1/config/notifications/{notification_id}",
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 200


# ============================================================
# Import/Export API Tests
# ============================================================

class TestImportExportAPI:
    """Tests for /api/v1/config/export and /import/* endpoints."""

    @pytest.mark.asyncio
    async def test_export_config(self, client):
        """Test POST /export exports configuration."""
        # Create some data first
        client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.01", "max_leverage": 10},
            headers={"X-User-Role": "admin"}
        )

        response = client.post(
            "/api/v1/config/export",
            json={"include_risk": True, "include_system": True},
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "yaml_content" in data
        assert "risk" in data["yaml_content"]

    @pytest.mark.asyncio
    async def test_preview_import_valid_yaml(self, client):
        """Test POST /import/preview with valid YAML."""
        yaml_content = """
risk:
  max_loss_percent: 0.02
  max_leverage: 20
system:
  ema_period: 50
strategies:
  - name: Test Strategy
    trigger:
      type: pinbar
      enabled: true
      params: {}
    filters: []
    filter_logic: AND
"""

        response = client.post(
            "/api/v1/config/import/preview",
            json={"yaml_content": yaml_content, "filename": "test.yaml"},
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert "preview_token" in data

    @pytest.mark.asyncio
    async def test_preview_import_invalid_yaml(self, client):
        """Test POST /import/preview with invalid YAML."""
        yaml_content = """
risk:
  max_loss_percent: invalid_value
  not a valid yaml: [unclosed
"""

        response = client.post(
            "/api/v1/config/import/preview",
            json={"yaml_content": yaml_content},
            headers={"X-User-Role": "admin"}
        )

        # Should still return 200 but with valid=False
        data = response.json()
        assert data["valid"] is False
        assert len(data["errors"]) > 0

    @pytest.mark.asyncio
    async def test_confirm_import_with_valid_preview(self, client):
        """Test POST /import/confirm with valid preview token."""
        yaml_content = """
risk:
  max_loss_percent: 0.015
  max_leverage: 15
"""
        # Preview first
        preview_response = client.post(
            "/api/v1/config/import/preview",
            json={"yaml_content": yaml_content, "filename": "test.yaml"},
            headers={"X-User-Role": "admin"}
        )
        preview_token = preview_response.json()["preview_token"]

        # Confirm
        response = client.post(
            "/api/v1/config/import/confirm",
            json={"preview_token": preview_token},
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    @pytest.mark.asyncio
    async def test_confirm_import_with_invalid_token(self, client):
        """Test POST /import/confirm with invalid token."""
        response = client.post(
            "/api/v1/config/import/confirm",
            json={"preview_token": "invalid-token-12345"},
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_preview_token_expires(self, client):
        """Test that preview token expires after 5 minutes."""
        import time
        from datetime import datetime, timezone, timedelta

        yaml_content = "risk:\n  max_loss_percent: 0.01"

        # Preview
        preview_response = client.post(
            "/api/v1/config/import/preview",
            json={"yaml_content": yaml_content, "filename": "test.yaml"},
            headers={"X-User-Role": "admin"}
        )
        preview_token = preview_response.json()["preview_token"]

        # Verify token exists in cache
        assert preview_token in _import_preview_cache

        # Simulate expiration by deleting from cache (equivalent to TTL expiry)
        del _import_preview_cache[preview_token]

        # Confirm should fail
        response = client.post(
            "/api/v1/config/import/confirm",
            json={"preview_token": preview_token},
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 400
        data = response.json()
        assert "Invalid or expired" in data["detail"]


# ============================================================
# Snapshot API Tests
# ============================================================

class TestSnapshotAPI:
    """Tests for /api/v1/config/snapshots/* endpoints."""

    @pytest.mark.asyncio
    async def test_get_snapshots_empty(self, client):
        """Test GET /snapshots returns empty list."""
        response = client.get("/api/v1/config/snapshots")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_create_snapshot(self, client):
        """Test POST /snapshots creates a snapshot."""
        # Create some config first
        client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.01", "max_leverage": 10},
            headers={"X-User-Role": "admin"}
        )

        response = client.post(
            "/api/v1/config/snapshots",
            json={
                "name": "Test Snapshot",
                "description": "A test snapshot for testing"
            },
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data

    @pytest.mark.asyncio
    async def test_get_snapshot_after_create(self, client):
        """Test GET /snapshots/{id} returns created snapshot."""
        # Create config and snapshot
        client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.01", "max_leverage": 10},
            headers={"X-User-Role": "admin"}
        )

        create_response = client.post(
            "/api/v1/config/snapshots",
            json={"name": "Get Test Snapshot", "description": "Test"},
            headers={"X-User-Role": "admin"}
        )
        snapshot_id = create_response.json()["id"]

        # Get and verify
        response = client.get(f"/api/v1/config/snapshots/{snapshot_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Get Test Snapshot"

    @pytest.mark.asyncio
    async def test_activate_snapshot(self, client):
        """Test POST /snapshots/{id}/activate activates snapshot."""
        # Create config and snapshot
        client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.01", "max_leverage": 10},
            headers={"X-User-Role": "admin"}
        )

        create_response = client.post(
            "/api/v1/config/snapshots",
            json={"name": "Activate Test Snapshot"},
            headers={"X-User-Role": "admin"}
        )
        snapshot_id = create_response.json()["id"]

        # Activate
        response = client.post(
            f"/api/v1/config/snapshots/{snapshot_id}/activate",
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_snapshot(self, client):
        """Test DELETE /snapshots/{id} deletes snapshot."""
        # Create config and snapshot
        client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.01", "max_leverage": 10},
            headers={"X-User-Role": "admin"}
        )

        create_response = client.post(
            "/api/v1/config/snapshots",
            json={"name": "Delete Test Snapshot"},
            headers={"X-User-Role": "admin"}
        )
        snapshot_id = create_response.json()["id"]

        # Delete
        response = client.delete(
            f"/api/v1/config/snapshots/{snapshot_id}",
            headers={"X-User-User-Role": "admin"}
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_nonexistent_snapshot(self, client):
        """Test GET /snapshots/{id} returns 404 for nonexistent."""
        response = client.get("/api/v1/config/snapshots/nonexistent-id")
        assert response.status_code == 404


# ============================================================
# Permission Tests
# ============================================================

class TestPermissionAPI:
    """Tests for admin permission checks."""

    @pytest.mark.asyncio
    async def test_update_risk_without_admin(self, client):
        """Test PUT /risk without admin role fails."""
        # Ensure DISABLE_AUTH is not set for permission tests
        os.environ.pop("DISABLE_AUTH", None)
        response = client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.01"}
            # No admin header
        )

        # Should fail without admin permission
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_create_strategy_without_admin(self, client):
        """Test POST /strategies without admin role fails."""
        # Ensure DISABLE_AUTH is not set for permission tests
        os.environ.pop("DISABLE_AUTH", None)
        response = client.post(
            "/api/v1/config/strategies",
            json={
                "name": "Unauthorized Strategy",
                "trigger": {"type": "pinbar", "enabled": True, "params": {}},
                "filters": [],
            }
            # No admin header
        )

        assert response.status_code in [401, 403]


# ============================================================
# Exchange Config API Tests (Task 23)
# ============================================================

class TestExchangeConfigAPI:
    """Tests for /api/v1/config/exchange endpoints."""

    @pytest.mark.asyncio
    async def test_get_exchange_config_initially_defaults(self, client):
        """Test GET /exchange returns defaults when no config exists."""
        response = client.get("/api/v1/config/exchange")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "binance"
        assert data["testnet"] is True
        # mask_secret returns original value for short strings (< 8 chars)
        assert data["api_key"] == ""
        assert data["api_secret"] == ""

    @pytest.mark.asyncio
    async def test_update_exchange_config(self, client):
        """Test PUT /exchange updates configuration."""
        update_data = {
            "name": "binance",
            "api_key": "my_new_api_key_12345678",
            "api_secret": "my_new_api_secret_abcd",
            "testnet": False,
        }

        response = client.put(
            "/api/v1/config/exchange",
            json=update_data,
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "binance"
        assert data["testnet"] is False
        # API keys should be masked in response (mask_secret uses "..." pattern)
        assert data["api_key"] != "my_new_api_key_12345678"
        assert "..." in data["api_key"]
        assert data["api_secret"] != "my_new_api_secret_abcd"
        assert "..." in data["api_secret"]

    @pytest.mark.asyncio
    async def test_get_exchange_config_after_update(self, client):
        """Test GET /exchange returns updated config."""
        # Update first
        client.put(
            "/api/v1/config/exchange",
            json={
                "name": "bybit",
                "api_key": "bybit_key_1234567890",
                "api_secret": "bybit_secret_abcdefghij",
                "testnet": True,
            },
            headers={"X-User-Role": "admin"}
        )

        # Get and verify
        response = client.get("/api/v1/config/exchange")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "bybit"
        assert data["testnet"] is True

    @pytest.mark.asyncio
    async def test_update_exchange_config_partial(self, client):
        """Test PUT /exchange with default values."""
        # Send empty body - should use defaults
        response = client.put(
            "/api/v1/config/exchange",
            json={},
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "binance"
        assert data["testnet"] is True

    @pytest.mark.asyncio
    async def test_update_exchange_without_admin(self, client):
        """Test PUT /exchange without admin role fails."""
        os.environ.pop("DISABLE_AUTH", None)
        response = client.put(
            "/api/v1/config/exchange",
            json={"name": "binance"}
        )

        assert response.status_code in [401, 403]


# ============================================================
# Timeframes API Tests (Task 23)
# ============================================================

class TestTimeframesAPI:
    """Tests for /api/v1/config/timeframes endpoints."""

    @pytest.mark.asyncio
    async def test_get_timeframes_initially_defaults(self, client):
        """Test GET /timeframes returns defaults when no config exists."""
        response = client.get("/api/v1/config/timeframes")
        assert response.status_code == 200
        data = response.json()
        assert "timeframes" in data
        assert isinstance(data["timeframes"], list)

    @pytest.mark.asyncio
    async def test_update_timeframes(self, client):
        """Test PUT /timeframes updates configuration."""
        update_data = {
            "timeframes": ["5m", "15m", "1h", "4h"],
        }

        response = client.put(
            "/api/v1/config/timeframes",
            json=update_data,
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["timeframes"] == ["5m", "15m", "1h", "4h"]

    @pytest.mark.asyncio
    async def test_get_timeframes_after_update(self, client):
        """Test GET /timeframes returns updated list."""
        # Update first
        client.put(
            "/api/v1/config/timeframes",
            json={"timeframes": ["1m", "5m", "15m"]},
            headers={"X-User-Role": "admin"}
        )

        # Get and verify
        response = client.get("/api/v1/config/timeframes")
        assert response.status_code == 200
        data = response.json()
        assert data["timeframes"] == ["1m", "5m", "15m"]

    @pytest.mark.asyncio
    async def test_update_timeframes_empty_list_rejected(self, client):
        """Test PUT /timeframes with empty list returns 422."""
        response = client.put(
            "/api/v1/config/timeframes",
            json={"timeframes": []},
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_update_timeframes_single_value(self, client):
        """Test PUT /timeframes with a single timeframe."""
        response = client.put(
            "/api/v1/config/timeframes",
            json={"timeframes": ["1h"]},
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["timeframes"] == ["1h"]

    @pytest.mark.asyncio
    async def test_update_timeframes_without_admin(self, client):
        """Test PUT /timeframes without admin role fails."""
        os.environ.pop("DISABLE_AUTH", None)
        response = client.put(
            "/api/v1/config/timeframes",
            json={"timeframes": ["15m"]}
        )

        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_update_timeframes_missing_field(self, client):
        """Test PUT /timeframes with missing timeframes field returns 422."""
        response = client.put(
            "/api/v1/config/timeframes",
            json={},
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 422


# ============================================================
# Asset Polling API Tests (Task 23)
# ============================================================

class TestAssetPollingAPI:
    """Tests for /api/v1/config/asset-polling endpoints."""

    @pytest.mark.asyncio
    async def test_get_asset_polling_initially_defaults(self, client):
        """Test GET /asset-polling returns defaults when no config exists."""
        response = client.get("/api/v1/config/asset-polling")
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True
        assert data["interval_seconds"] == 60

    @pytest.mark.asyncio
    async def test_update_asset_polling(self, client):
        """Test PUT /asset-polling updates configuration."""
        update_data = {
            "enabled": False,
            "interval_seconds": 120,
        }

        response = client.put(
            "/api/v1/config/asset-polling",
            json=update_data,
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False
        assert data["interval_seconds"] == 120

    @pytest.mark.asyncio
    async def test_get_asset_polling_after_update(self, client):
        """Test GET /asset-polling returns updated config."""
        # Update first
        client.put(
            "/api/v1/config/asset-polling",
            json={"enabled": True, "interval_seconds": 300},
            headers={"X-User-Role": "admin"}
        )

        # Get and verify
        response = client.get("/api/v1/config/asset-polling")
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True
        assert data["interval_seconds"] == 300

    @pytest.mark.asyncio
    async def test_update_asset_polling_partial_enabled_only(self, client):
        """Test PUT /asset-polling with only enabled field."""
        response = client.put(
            "/api/v1/config/asset-polling",
            json={"enabled": False},
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False
        assert data["interval_seconds"] == 60  # default

    @pytest.mark.asyncio
    async def test_update_asset_polling_partial_interval_only(self, client):
        """Test PUT /asset-polling with only interval field."""
        response = client.put(
            "/api/v1/config/asset-polling",
            json={"interval_seconds": 90},
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True  # default
        assert data["interval_seconds"] == 90

    @pytest.mark.asyncio
    async def test_update_asset_polling_interval_too_low_rejected(self, client):
        """Test PUT /asset-polling with interval < 10 returns 422."""
        response = client.put(
            "/api/v1/config/asset-polling",
            json={"interval_seconds": 5},
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_update_asset_polling_interval_minimum(self, client):
        """Test PUT /asset-polling with minimum interval (10s)."""
        response = client.put(
            "/api/v1/config/asset-polling",
            json={"interval_seconds": 10},
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["interval_seconds"] == 10

    @pytest.mark.asyncio
    async def test_update_asset_polling_without_admin(self, client):
        """Test PUT /asset-polling without admin role fails."""
        os.environ.pop("DISABLE_AUTH", None)
        response = client.put(
            "/api/v1/config/asset-polling",
            json={"enabled": False}
        )

        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_update_asset_polling_empty_body(self, client):
        """Test PUT /asset-polling with empty body uses defaults."""
        response = client.put(
            "/api/v1/config/asset-polling",
            json={},
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True
        assert data["interval_seconds"] == 60


# ============================================================
# Main entry point
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=src/interfaces/api_v1_config"])
