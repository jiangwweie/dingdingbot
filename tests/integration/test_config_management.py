"""
Integration tests for configuration management API endpoints.

Tests the full stack from API endpoints through ConfigManager to ConfigRepository.
"""
import pytest
import asyncio
import tempfile
import os
import json
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import asynccontextmanager

from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.interfaces.api import app, set_dependencies, _get_config_manager, _get_repository
from src.infrastructure.config_repository import ConfigRepository
from src.infrastructure.signal_repository import SignalRepository
from src.application.config_manager import ConfigManager


class TestConfigAPIIntegration:
    """Integration tests for configuration management API endpoints."""

    @pytest.fixture
    async def api_setup(self):
        """Set up API with test repositories."""
        # Create temporary databases
        config_temp_dir = tempfile.mkdtemp()
        signal_temp_dir = tempfile.mkdtemp()

        config_db_path = os.path.join(config_temp_dir, "test_config.db")
        signal_db_path = os.path.join(signal_temp_dir, "test_signals.db")

        # Initialize repositories
        config_repo = ConfigRepository(config_db_path)
        await config_repo.initialize()

        signal_repo = SignalRepository(signal_db_path)
        await signal_repo.initialize()

        # Initialize config manager
        config_manager = ConfigManager(config_db_path)
        await config_manager.initialize()

        # Create FastAPI app for testing
        test_app = FastAPI(title="Test API")

        # Copy routes from main app
        for route in app.routes:
            test_app.router.routes.append(route)

        # Set dependencies
        def get_account():
            return None

        set_dependencies(
            repository=signal_repo,
            account_getter=get_account,
            config_manager=config_manager,
        )

        yield {
            "app": test_app,
            "config_repo": config_repo,
            "signal_repo": signal_repo,
            "config_manager": config_manager,
            "config_db_path": config_db_path,
            "signal_db_path": signal_db_path,
        }

        # Cleanup
        await config_repo.close()
        await signal_repo.close()

        os.remove(config_db_path)
        os.remove(signal_db_path)
        os.rmdir(config_temp_dir)
        os.rmdir(signal_temp_dir)

    @pytest.mark.asyncio
    async def test_get_all_config_v1(self, api_setup):
        """Test GET /api/v1/config endpoint."""
        client = TestClient(api_setup["app"])

        response = client.get("/api/v1/config")

        assert response.status_code == 200
        data = response.json()

        assert "strategy" in data
        assert "risk" in data
        assert "system" in data
        assert "symbols" in data
        assert "notifications" in data

        # Verify default values
        assert data["risk"]["max_loss_percent"] == 1.0
        assert data["risk"]["max_leverage"] == 10
        assert data["system"]["history_bars"] == 100

    @pytest.mark.asyncio
    async def test_update_risk_config_v1(self, api_setup):
        """Test PUT /api/v1/config/risk endpoint."""
        client = TestClient(api_setup["app"])

        # Update risk config
        response = client.put(
            "/api/v1/config/risk",
            json={
                "max_loss_percent": 2.0,
                "max_leverage": 20,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["requires_restart"] is False

        # Verify update was applied
        config_manager = api_setup["config_manager"]
        assert config_manager.risk_config.max_loss_percent == Decimal("2.0")
        assert config_manager.risk_config.max_leverage == 20

    @pytest.mark.asyncio
    async def test_update_system_config_v1(self, api_setup):
        """Test PUT /api/v1/config/system endpoint."""
        client = TestClient(api_setup["app"])

        # Update system config
        response = client.put(
            "/api/v1/config/system",
            json={
                "history_bars": 200,
                "queue_batch_size": 20,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["requires_restart"] is True  # System config requires restart

        # Verify update was applied
        config_manager = api_setup["config_manager"]
        assert config_manager.system_config.history_bars == 200

    @pytest.mark.asyncio
    async def test_get_symbols_v1(self, api_setup):
        """Test GET /api/v1/config/symbols endpoint."""
        client = TestClient(api_setup["app"])

        # Add a symbol
        await api_setup["config_repo"].add_symbol("ETH/USDT:USDT", is_core=0, is_enabled=1)

        response = client.get("/api/v1/config/symbols")

        assert response.status_code == 200
        data = response.json()
        assert "symbols" in data
        assert len(data["symbols"]) >= 1

    @pytest.mark.asyncio
    async def test_add_symbol_v1(self, api_setup):
        """Test POST /api/v1/config/symbols endpoint."""
        client = TestClient(api_setup["app"])

        # Add a symbol
        response = client.post(
            "/api/v1/config/symbols",
            json={
                "symbol": "DOGE/USDT:USDT",
                "is_core": False,
                "is_enabled": True,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify symbol was added
        symbols = await api_setup["config_repo"].get_enabled_symbols()
        assert "DOGE/USDT:USDT" in symbols

    @pytest.mark.asyncio
    async def test_delete_symbol_v1(self, api_setup):
        """Test DELETE /api/v1/config/symbols/{id} endpoint."""
        client = TestClient(api_setup["app"])

        # Add a non-core symbol
        symbol_id = await api_setup["config_repo"].add_symbol(
            "SHIB/USDT:USDT",
            is_core=0,
            is_enabled=1,
        )

        # Delete the symbol
        response = client.delete(f"/api/v1/config/symbols/{symbol_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify symbol was deleted
        symbol = await api_setup["config_repo"].get_symbol_by_id(symbol_id)
        assert symbol is None

    @pytest.mark.asyncio
    async def test_delete_core_symbol_v1_fails(self, api_setup):
        """Test that DELETE /api/v1/config/symbols/{id} fails for core symbols."""
        client = TestClient(api_setup["app"])

        # Add a core symbol
        symbol_id = await api_setup["config_repo"].add_symbol(
            "TEST/USDT:USDT",
            is_core=1,
            is_enabled=1,
        )

        # Try to delete - should fail
        response = client.delete(f"/api/v1/config/symbols/{symbol_id}")

        assert response.status_code == 400
        data = response.json()
        assert "核心币种不可删除" in data.get("error", "")

    @pytest.mark.asyncio
    async def test_get_notifications_v1(self, api_setup):
        """Test GET /api/v1/config/notifications endpoint."""
        client = TestClient(api_setup["app"])

        # Add a notification
        await api_setup["config_repo"].add_notification(
            "feishu",
            "https://example.com/webhook",
            is_enabled=1,
        )

        response = client.get("/api/v1/config/notifications")

        assert response.status_code == 200
        data = response.json()
        assert "notifications" in data
        assert len(data["notifications"]) >= 1

    @pytest.mark.asyncio
    async def test_add_notification_v1(self, api_setup):
        """Test POST /api/v1/config/notifications endpoint."""
        client = TestClient(api_setup["app"])

        # Add a notification
        response = client.post(
            "/api/v1/config/notifications",
            json={
                "channel": "telegram",
                "webhook_url": "https://telegram.com/webhook",
                "is_enabled": True,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify notification was added
        notifications = await api_setup["config_repo"].get_enabled_notifications()
        assert any(n["channel"] == "telegram" for n in notifications)

    @pytest.mark.asyncio
    async def test_update_notification_v1(self, api_setup):
        """Test PUT /api/v1/config/notifications/{id} endpoint."""
        client = TestClient(api_setup["app"])

        # Add a notification
        notification_id = await api_setup["config_repo"].add_notification(
            "feishu",
            "https://old.com/webhook",
            is_enabled=1,
        )

        # Update the notification
        response = client.put(
            f"/api/v1/config/notifications/{notification_id}",
            json={
                "webhook_url": "https://new.com/webhook",
                "is_enabled": False,
            },
        )

        assert response.status_code == 200

        # Verify update was applied
        notification = await api_setup["config_repo"].get_notification(notification_id)
        assert notification["webhook_url"] == "https://new.com/webhook"
        assert notification["is_enabled"] == 0

    @pytest.mark.asyncio
    async def test_delete_notification_v1(self, api_setup):
        """Test DELETE /api/v1/config/notifications/{id} endpoint."""
        client = TestClient(api_setup["app"])

        # Add a notification
        notification_id = await api_setup["config_repo"].add_notification(
            "wecom",
            "https://wecom.com/webhook",
            is_enabled=1,
        )

        # Delete the notification
        response = client.delete(f"/api/v1/config/notifications/{notification_id}")

        assert response.status_code == 200

        # Verify notification was deleted
        notification = await api_setup["config_repo"].get_notification(notification_id)
        assert notification is None


class TestExportImportAPIIntegration:
    """Integration tests for config export/import API endpoints."""

    @pytest.fixture
    async def api_setup(self):
        """Set up API with test repositories."""
        config_temp_dir = tempfile.mkdtemp()
        signal_temp_dir = tempfile.mkdtemp()

        config_db_path = os.path.join(config_temp_dir, "test_config.db")
        signal_db_path = os.path.join(signal_temp_dir, "test_signals.db")

        config_repo = ConfigRepository(config_db_path)
        await config_repo.initialize()

        signal_repo = SignalRepository(signal_db_path)
        await signal_repo.initialize()

        config_manager = ConfigManager(config_db_path)
        await config_manager.initialize()

        test_app = FastAPI()
        for route in app.routes:
            test_app.router.routes.append(route)

        def get_account():
            return None

        set_dependencies(
            repository=signal_repo,
            account_getter=get_account,
            config_manager=config_manager,
        )

        yield {
            "app": test_app,
            "config_repo": config_repo,
            "signal_repo": signal_repo,
            "config_manager": config_manager,
        }

        await config_repo.close()
        await signal_repo.close()

        os.remove(config_db_path)
        os.remove(signal_db_path)
        os.rmdir(config_temp_dir)
        os.rmdir(signal_temp_dir)

    @pytest.mark.asyncio
    async def test_export_config(self, api_setup):
        """Test POST /api/v1/config/export endpoint."""
        client = TestClient(api_setup["app"])

        response = client.post("/api/v1/config/export")

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "yaml_content" in data
        assert "exported_at" in data

        # Verify YAML content format
        yaml_content = data["yaml_content"]
        assert isinstance(yaml_content, str)
        assert "risk_config:" in yaml_content
        assert "system_config:" in yaml_content

    @pytest.mark.asyncio
    async def test_import_preview(self, api_setup):
        """Test POST /api/v1/config/import/preview endpoint."""
        client = TestClient(api_setup["app"])

        yaml_content = """
risk_config:
  max_loss_percent: 2.0
  max_leverage: 20
system_config:
  history_bars: 200
"""

        response = client.post(
            "/api/v1/config/import/preview",
            json={"yaml_content": yaml_content},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["valid"] is True
        assert "changes" in data
        assert len(data["changes"]) > 0

    @pytest.mark.asyncio
    async def test_import_preview_invalid_yaml(self, api_setup):
        """Test POST /api/v1/config/import/preview with invalid YAML."""
        client = TestClient(api_setup["app"])

        response = client.post(
            "/api/v1/config/import/preview",
            json={"yaml_content": "invalid: yaml: ["},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["valid"] is False
        assert len(data["errors"]) > 0

    @pytest.mark.asyncio
    async def test_import_confirm(self, api_setup):
        """Test POST /api/v1/config/import/confirm endpoint."""
        client = TestClient(api_setup["app"])

        yaml_content = """
risk_config:
  max_loss_percent: 2.5
  max_leverage: 15
"""

        response = client.post(
            "/api/v1/config/import/confirm",
            json={"yaml_content": yaml_content},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert data["applied_changes"] > 0

        # Verify config was updated
        config_manager = api_setup["config_manager"]
        assert config_manager.risk_config.max_loss_percent == Decimal("2.5")


class TestHotReloadIntegration:
    """Integration tests for hot-reload functionality."""

    @pytest.fixture
    async def api_setup(self):
        """Set up API with test repositories."""
        config_temp_dir = tempfile.mkdtemp()
        signal_temp_dir = tempfile.mkdtemp()

        config_db_path = os.path.join(config_temp_dir, "test_config.db")
        signal_db_path = os.path.join(signal_temp_dir, "test_signals.db")

        config_repo = ConfigRepository(config_db_path)
        await config_repo.initialize()

        signal_repo = SignalRepository(signal_db_path)
        await signal_repo.initialize()

        config_manager = ConfigManager(config_db_path)
        await config_manager.initialize()

        # Track observer calls
        observer_calls = []

        async def observer_callback():
            observer_calls.append(True)

        config_manager.add_observer(observer_callback)

        test_app = FastAPI()
        for route in app.routes:
            test_app.router.routes.append(route)

        def get_account():
            return None

        set_dependencies(
            repository=signal_repo,
            account_getter=get_account,
            config_manager=config_manager,
        )

        yield {
            "app": test_app,
            "config_repo": config_repo,
            "signal_repo": signal_repo,
            "config_manager": config_manager,
            "observer_calls": observer_calls,
        }

        await config_repo.close()
        await signal_repo.close()

        os.remove(config_db_path)
        os.remove(signal_db_path)
        os.rmdir(config_temp_dir)
        os.rmdir(signal_temp_dir)

    @pytest.mark.asyncio
    async def test_risk_config_update_triggers_reload(self, api_setup):
        """Test that updating risk config triggers hot-reload."""
        client = TestClient(api_setup["app"])

        # Update risk config via API
        response = client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": 2.0},
        )

        assert response.status_code == 200

        # Give async observer time to execute
        await asyncio.sleep(0.1)

        # Config should be updated
        config_manager = api_setup["config_manager"]
        assert config_manager.risk_config.max_loss_percent == Decimal("2.0")

    @pytest.mark.asyncio
    async def test_system_config_update_requires_restart(self, api_setup):
        """Test that updating system config indicates restart required."""
        client = TestClient(api_setup["app"])

        # Update system config via API
        response = client.put(
            "/api/v1/config/system",
            json={"history_bars": 200},
        )

        assert response.status_code == 200
        data = response.json()

        # Should indicate restart required
        assert data["requires_restart"] is True


class TestSnapshotAPIIntegration:
    """Integration tests for config snapshot API endpoints."""

    @pytest.fixture
    async def api_setup(self):
        """Set up API with test repositories."""
        config_temp_dir = tempfile.mkdtemp()
        signal_temp_dir = tempfile.mkdtemp()

        config_db_path = os.path.join(config_temp_dir, "test_config.db")
        signal_db_path = os.path.join(signal_temp_dir, "test_signals.db")

        config_repo = ConfigRepository(config_db_path)
        await config_repo.initialize()

        signal_repo = SignalRepository(signal_db_path)
        await signal_repo.initialize()

        config_manager = ConfigManager(config_db_path)
        await config_manager.initialize()

        test_app = FastAPI()
        for route in app.routes:
            test_app.router.routes.append(route)

        def get_account():
            return None

        set_dependencies(
            repository=signal_repo,
            account_getter=get_account,
            config_manager=config_manager,
        )

        yield {
            "app": test_app,
            "config_repo": config_repo,
            "signal_repo": signal_repo,
            "config_manager": config_manager,
        }

        await config_repo.close()
        await signal_repo.close()

        os.remove(config_db_path)
        os.remove(signal_db_path)
        os.rmdir(config_temp_dir)
        os.rmdir(signal_temp_dir)

    @pytest.mark.asyncio
    async def test_get_snapshots_empty(self, api_setup):
        """Test GET /api/v1/snapshots with no snapshots."""
        client = TestClient(api_setup["app"])

        response = client.get("/api/v1/snapshots")

        assert response.status_code == 200
        data = response.json()
        assert "snapshots" in data
        assert len(data["snapshots"]) == 0

    @pytest.mark.asyncio
    async def test_create_snapshot(self, api_setup):
        """Test POST /api/v1/snapshots endpoint."""
        client = TestClient(api_setup["app"])

        response = client.post(
            "/api/v1/snapshots",
            json={
                "name": "Test Snapshot",
                "description": "Test snapshot for integration testing",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert "id" in data

    @pytest.mark.asyncio
    async def test_rollback_snapshot(self, api_setup):
        """Test POST /api/v1/snapshots/{id}/rollback endpoint."""
        client = TestClient(api_setup["app"])

        # First update config
        await api_setup["config_repo"].update_risk_config(max_loss_percent=2.0)

        # Create snapshot
        snapshot_response = client.post(
            "/api/v1/snapshots",
            json={
                "name": "Rollback Test",
                "description": "Snapshot for rollback testing",
            },
        )

        assert snapshot_response.status_code == 201
        snapshot_id = snapshot_response.json()["id"]

        # Change config again
        await api_setup["config_repo"].update_risk_config(max_loss_percent=3.0)

        # Verify change
        config_manager = api_setup["config_manager"]
        assert config_manager.risk_config.max_loss_percent == Decimal("3.0")

        # Rollback to snapshot
        rollback_response = client.post(f"/api/v1/snapshots/{snapshot_id}/rollback")

        assert rollback_response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_history(self, api_setup):
        """Test GET /api/v1/history endpoint."""
        client = TestClient(api_setup["app"])

        # Create some history by updating config
        await api_setup["config_repo"].update_risk_config(max_loss_percent=2.0)

        response = client.get("/api/v1/history")

        assert response.status_code == 200
        data = response.json()
        assert "history" in data
        assert len(data["history"]) > 0


class TestStrategyAPIIntegration:
    """Integration tests for strategy configuration API endpoints."""

    @pytest.fixture
    async def api_setup(self):
        """Set up API with test repositories."""
        config_temp_dir = tempfile.mkdtemp()
        signal_temp_dir = tempfile.mkdtemp()

        config_db_path = os.path.join(config_temp_dir, "test_config.db")
        signal_db_path = os.path.join(signal_temp_dir, "test_signals.db")

        config_repo = ConfigRepository(config_db_path)
        await config_repo.initialize()

        signal_repo = SignalRepository(signal_db_path)
        await signal_repo.initialize()

        config_manager = ConfigManager(config_db_path)
        await config_manager.initialize()

        test_app = FastAPI()
        for route in app.routes:
            test_app.router.routes.append(route)

        def get_account():
            return None

        set_dependencies(
            repository=signal_repo,
            account_getter=get_account,
            config_manager=config_manager,
        )

        yield {
            "app": test_app,
            "config_repo": config_repo,
            "signal_repo": signal_repo,
            "config_manager": config_manager,
        }

        await config_repo.close()
        await signal_repo.close()

        os.remove(config_db_path)
        os.remove(signal_db_path)
        os.rmdir(config_temp_dir)
        os.rmdir(signal_temp_dir)

    @pytest.mark.asyncio
    async def test_get_strategies(self, api_setup):
        """Test GET /api/v1/strategies endpoint."""
        client = TestClient(api_setup["app"])

        response = client.get("/api/v1/strategies")

        assert response.status_code == 200
        data = response.json()
        assert "strategies" in data

    @pytest.mark.asyncio
    async def test_create_strategy(self, api_setup):
        """Test POST /api/v1/strategies endpoint."""
        client = TestClient(api_setup["app"])

        strategy_data = {
            "name": "Test Strategy",
            "description": "Test strategy for integration testing",
            "triggers": [
                {"type": "pinbar", "params": {"min_wick_ratio": 0.6}}
            ],
            "filters": [
                {"type": "ema", "params": {"period": 60}}
            ],
            "apply_to": ["BTC/USDT:USDT:15m"],
        }

        response = client.post(
            "/api/v1/strategies",
            json=strategy_data,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert "id" in data

    @pytest.mark.asyncio
    async def test_get_strategy_by_id(self, api_setup):
        """Test GET /api/v1/strategies/{id} endpoint."""
        client = TestClient(api_setup["app"])

        # Create a strategy first
        strategy_data = {
            "name": "Get Test Strategy",
            "triggers": [{"type": "pinbar", "params": {}}],
            "filters": [],
            "apply_to": [],
        }

        create_response = client.post("/api/v1/strategies", json=strategy_data)
        strategy_id = create_response.json()["id"]

        # Get the strategy
        response = client.get(f"/api/v1/strategies/{strategy_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Get Test Strategy"

    @pytest.mark.asyncio
    async def test_update_strategy(self, api_setup):
        """Test PUT /api/v1/strategies/{id} endpoint."""
        client = TestClient(api_setup["app"])

        # Create a strategy
        strategy_data = {
            "name": "Update Test Strategy",
            "triggers": [{"type": "pinbar", "params": {}}],
            "filters": [],
            "apply_to": [],
        }

        create_response = client.post("/api/v1/strategies", json=strategy_data)
        strategy_id = create_response.json()["id"]

        # Update the strategy
        update_data = {
            "name": "Updated Strategy Name",
            "description": "Updated description",
        }

        response = client.put(f"/api/v1/strategies/{strategy_id}", json=update_data)

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_strategy(self, api_setup):
        """Test DELETE /api/v1/strategies/{id} endpoint."""
        client = TestClient(api_setup["app"])

        # Create a strategy
        strategy_data = {
            "name": "Delete Test Strategy",
            "triggers": [{"type": "pinbar", "params": {}}],
            "filters": [],
            "apply_to": [],
        }

        create_response = client.post("/api/v1/strategies", json=strategy_data)
        strategy_id = create_response.json()["id"]

        # Delete the strategy
        response = client.delete(f"/api/v1/strategies/{strategy_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_activate_strategy(self, api_setup):
        """Test POST /api/v1/strategies/{id}/activate endpoint."""
        client = TestClient(api_setup["app"])

        # Create a strategy
        strategy_data = {
            "name": "Activate Test Strategy",
            "triggers": [{"type": "pinbar", "params": {}}],
            "filters": [],
            "apply_to": [],
        }

        create_response = client.post("/api/v1/strategies", json=strategy_data)
        strategy_id = create_response.json()["id"]

        # Activate the strategy
        response = client.post(f"/api/v1/strategies/{strategy_id}/activate")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["requires_restart"] is False
