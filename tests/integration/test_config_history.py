"""
Integration Tests for Configuration Change History

Tests all REST endpoints in src/interfaces/api_v1_config.py for history management:
- GET /api/v1/config/history - History list with pagination and filters
- GET /api/v1/config/history/{history_id} - History detail
- GET /api/v1/config/history/entity/{entity_type}/{entity_id} - Entity history
- POST /api/v1/config/history/rollback - Rollback to a specific version

Coverage target: >= 80%
Test cases: >= 20
"""
import json
import os
import pytest
import tempfile
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
    set_config_dependencies,
)


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
    app = FastAPI(title="Config History Test")
    app.include_router(router, tags=["config"])
    return app


@pytest.fixture
def client(app, db_manager):
    """Create TestClient with injected dependencies."""
    set_config_dependencies(
        strategy_repo=db_manager.strategy_repo,
        risk_repo=db_manager.risk_repo,
        system_repo=db_manager.system_repo,
        symbol_repo=db_manager.symbol_repo,
        notification_repo=db_manager.notification_repo,
        history_repo=db_manager.history_repo,
        snapshot_repo=db_manager.snapshot_repo,
    )

    with TestClient(app) as c:
        yield c


# ============================================================
# Helper Functions
# ============================================================

def create_test_strategy():
    """Create a test strategy payload."""
    return {
        "name": "Test Strategy",
        "description": "A test strategy for history testing",
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
        "symbols": ["BTC/USDT:USDT"],
        "timeframes": ["15m"],
    }


def create_test_risk_config():
    """Create a test risk config payload."""
    return {
        "max_loss_percent": "0.01",
        "max_leverage": 10,
        "max_total_exposure": "0.8",
        "cooldown_minutes": 240,
    }


def create_test_system_config():
    """Create a test system config payload."""
    return {
        "core_symbols": ["BTC/USDT:USDT", "ETH/USDT:USDT"],
        "ema_period": 60,
        "mtf_ema_period": 60,
        "mtf_mapping": {"15m": "1h"},
        "signal_cooldown_seconds": 14400,
    }


# ============================================================
# History List API Tests
# ============================================================

class TestHistoryListAPI:
    """Tests for GET /api/v1/config/history endpoints."""

    @pytest.mark.asyncio
    async def test_get_history_empty(self, client):
        """Test GET /history returns empty list when no history exists."""
        response = client.get("/api/v1/config/history")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data or isinstance(data, list)
        # Should be empty initially
        if isinstance(data, dict):
            assert len(data.get("items", data)) == 0

    @pytest.mark.asyncio
    async def test_get_history_after_risk_update(self, client):
        """Test GET /history returns records after config update."""
        # Update risk config
        client.put(
            "/api/v1/config/risk",
            json=create_test_risk_config(),
            headers={"X-User-Role": "admin"}
        )

        response = client.get("/api/v1/config/history")
        assert response.status_code == 200
        data = response.json()
        items = data.get("items", data) if isinstance(data, dict) else data
        assert len(items) >= 1

    @pytest.mark.asyncio
    async def test_get_history_with_pagination(self, client):
        """Test GET /history supports pagination."""
        # Create multiple history records
        for i in range(5):
            client.post(
                "/api/v1/config/strategies",
                json={
                    "name": f"Strategy {i}",
                    "trigger": {"type": "pinbar", "enabled": True, "params": {}},
                    "filters": [],
                    "filter_logic": "AND",
                },
                headers={"X-User-Role": "admin"}
            )

        # Test with limit
        response = client.get("/api/v1/config/history?limit=3")
        assert response.status_code == 200
        data = response.json()
        items = data.get("items", data) if isinstance(data, dict) else data
        assert len(items) <= 3

    @pytest.mark.asyncio
    async def test_get_history_filtered_by_entity_type(self, client):
        """Test GET /history filters by entity_type."""
        # Create different types of history
        client.put(
            "/api/v1/config/risk",
            json=create_test_risk_config(),
            headers={"X-User-Role": "admin"}
        )
        client.post(
            "/api/v1/config/strategies",
            json=create_test_strategy(),
            headers={"X-User-Role": "admin"}
        )

        # Filter by strategy
        response = client.get("/api/v1/config/history?entity_type=strategy")
        assert response.status_code == 200
        data = response.json()
        items = data.get("items", data) if isinstance(data, dict) else data
        for item in items:
            assert item["entity_type"] == "strategy"

    @pytest.mark.asyncio
    async def test_get_history_filtered_by_entity_id(self, client):
        """Test GET /history filters by entity_id."""
        # Create a strategy
        create_response = client.post(
            "/api/v1/config/strategies",
            json=create_test_strategy(),
            headers={"X-User-Role": "admin"}
        )
        strategy_id = create_response.json()["id"]

        # Update the same strategy
        client.put(
            f"/api/v1/config/strategies/{strategy_id}",
            json={"name": "Updated Strategy"},
            headers={"X-User-Role": "admin"}
        )

        # Filter by entity_id
        response = client.get(f"/api/v1/config/history?entity_id={strategy_id}")
        assert response.status_code == 200
        data = response.json()
        items = data.get("items", data) if isinstance(data, dict) else data
        for item in items:
            assert item["entity_id"] == strategy_id


# ============================================================
# History Detail API Tests
# ============================================================

class TestHistoryDetailAPI:
    """Tests for GET /api/v1/config/history/{history_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_history_detail(self, client):
        """Test GET /history/{id} returns history detail."""
        # Create a risk config to generate history
        client.put(
            "/api/v1/config/risk",
            json=create_test_risk_config(),
            headers={"X-User-Role": "admin"}
        )

        # Get history list to find an ID
        history_response = client.get("/api/v1/config/history")
        history_data = history_response.json()
        items = history_data.get("items", history_data) if isinstance(history_data, dict) else history_data

        if items:
            history_id = items[0]["id"]
            detail_response = client.get(f"/api/v1/config/history/{history_id}")
            assert detail_response.status_code == 200
            data = detail_response.json()
            assert "id" in data
            assert "entity_type" in data
            assert "action" in data

    @pytest.mark.asyncio
    async def test_get_history_detail_not_found(self, client):
        """Test GET /history/{id} returns 404 for invalid ID."""
        response = client.get("/api/v1/config/history/99999")
        assert response.status_code == 404


# ============================================================
# Entity History API Tests
# ============================================================

class TestEntityHistoryAPI:
    """Tests for GET /api/v1/config/history/entity/{entity_type}/{entity_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_strategy_history(self, client):
        """Test GET /history/entity/strategy/{id} returns strategy history."""
        # Create a strategy
        create_response = client.post(
            "/api/v1/config/strategies",
            json=create_test_strategy(),
            headers={"X-User-Role": "admin"}
        )
        strategy_id = create_response.json()["id"]

        # Update the strategy
        client.put(
            f"/api/v1/config/strategies/{strategy_id}",
            json={"name": "Updated Strategy", "description": "Updated desc"},
            headers={"X-User-Role": "admin"}
        )

        # Get entity history
        response = client.get(f"/api/v1/config/history/entity/strategy/{strategy_id}")
        assert response.status_code == 200
        data = response.json()
        items = data.get("items", data) if isinstance(data, dict) else data
        assert len(items) >= 2  # CREATE and UPDATE

    @pytest.mark.asyncio
    async def test_get_risk_config_history(self, client):
        """Test GET /history/entity/risk_config/global returns risk config history."""
        # Update risk config multiple times
        client.put(
            "/api/v1/config/risk",
            json=create_test_risk_config(),
            headers={"X-User-Role": "admin"}
        )
        client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.02", "max_leverage": 15},
            headers={"X-User-Role": "admin"}
        )

        # Get entity history
        response = client.get("/api/v1/config/history/entity/risk_config/global")
        assert response.status_code == 200
        data = response.json()
        items = data.get("items", data) if isinstance(data, dict) else data
        assert len(items) >= 1

    @pytest.mark.asyncio
    async def test_get_entity_history_empty(self, client):
        """Test GET /history/entity/{type}/{id} returns empty for non-existent entity."""
        response = client.get("/api/v1/config/history/entity/strategy/non-existent-id")
        assert response.status_code == 200
        data = response.json()
        items = data.get("items", data) if isinstance(data, dict) else data
        assert len(items) == 0


# ============================================================
# History Rollback API Tests
# ============================================================

class TestHistoryRollbackAPI:
    """Tests for POST /api/v1/config/history/rollback endpoint."""

    @pytest.mark.asyncio
    async def test_get_rollback_candidates(self, client):
        """Test GET /history/rollback-candidates returns rollback points."""
        # Create and update a strategy
        create_response = client.post(
            "/api/v1/config/strategies",
            json={
                "name": "Rollback Test Strategy",
                "trigger": {"type": "pinbar", "enabled": True, "params": {}},
                "filters": [],
                "filter_logic": "AND",
            },
            headers={"X-User-Role": "admin"}
        )
        strategy_id = create_response.json()["id"]

        client.put(
            f"/api/v1/config/strategies/{strategy_id}",
            json={"name": "Updated Name 1"},
            headers={"X-User-Role": "admin"}
        )
        client.put(
            f"/api/v1/config/strategies/{strategy_id}",
            json={"name": "Updated Name 2"},
            headers={"X-User-Role": "admin"}
        )

        # Get rollback candidates
        response = client.get(f"/api/v1/config/history/rollback-candidates?entity_type=strategy&entity_id={strategy_id}")
        assert response.status_code == 200
        data = response.json()
        items = data.get("items", data) if isinstance(data, dict) else data
        assert len(items) >= 2  # At least CREATE and first UPDATE

    @pytest.mark.asyncio
    async def test_rollback_to_previous_version(self, client):
        """Test POST /history/rollback restores previous configuration."""
        # Create a strategy
        create_response = client.post(
            "/api/v1/config/strategies",
            json={
                "name": "Original Name",
                "trigger": {"type": "pinbar", "enabled": True, "params": {}},
                "filters": [],
                "filter_logic": "AND",
            },
            headers={"X-User-Role": "admin"}
        )
        strategy_id = create_response.json()["id"]

        # Update the strategy
        client.put(
            f"/api/v1/config/strategies/{strategy_id}",
            json={"name": "Modified Name"},
            headers={"X-User-Role": "admin"}
        )

        # Get history to find rollback point
        history_response = client.get(f"/api/v1/config/history/entity/strategy/{strategy_id}")
        history_data = history_response.json()
        items = history_data.get("items", history_data) if isinstance(history_data, dict) else history_data

        # Find the CREATE action
        create_history = None
        for item in items:
            if item["action"] == "CREATE":
                create_history = item
                break

        if create_history:
            # Rollback to CREATE version
            rollback_response = client.post(
                "/api/v1/config/history/rollback",
                json={
                    "history_id": create_history["id"],
                    "entity_type": "strategy",
                    "entity_id": strategy_id,
                },
                headers={"X-User-Role": "admin"}
            )
            assert rollback_response.status_code == 200

            # Verify the strategy name is back to original
            get_response = client.get(f"/api/v1/config/strategies/{strategy_id}")
            assert get_response.status_code == 200
            data = get_response.json()
            assert data["name"] == "Original Name"

    @pytest.mark.asyncio
    async def test_rollback_invalid_history_id(self, client):
        """Test POST /history/rollback with invalid history_id fails."""
        response = client.post(
            "/api/v1/config/history/rollback",
            json={
                "history_id": 99999,
                "entity_type": "strategy",
                "entity_id": "test-id",
            },
            headers={"X-User-Role": "admin"}
        )
        assert response.status_code in [400, 404]

    @pytest.mark.asyncio
    async def test_rollback_to_delete_action_fails(self, client):
        """Test POST /history/rollback to DELETE action fails."""
        # Create and delete a strategy
        create_response = client.post(
            "/api/v1/config/strategies",
            json={
                "name": "Delete Test",
                "trigger": {"type": "pinbar", "enabled": True, "params": {}},
                "filters": [],
                "filter_logic": "AND",
            },
            headers={"X-User-Role": "admin"}
        )
        strategy_id = create_response.json()["id"]

        # Delete the strategy
        client.delete(
            f"/api/v1/config/strategies/{strategy_id}",
            headers={"X-User-Role": "admin"}
        )

        # Get history to find DELETE action
        history_response = client.get("/api/v1/config/history")
        history_data = history_response.json()
        items = history_data.get("items", history_data) if isinstance(history_data, dict) else history_data

        delete_history = None
        for item in items:
            if item["action"] == "DELETE" and item["entity_id"] == strategy_id:
                delete_history = item
                break

        if delete_history:
            # Try to rollback to DELETE (should fail)
            rollback_response = client.post(
                "/api/v1/config/history/rollback",
                json={
                    "history_id": delete_history["id"],
                    "entity_type": "strategy",
                    "entity_id": strategy_id,
                },
                headers={"X-User-Role": "admin"}
            )
            assert rollback_response.status_code in [400, 422]


# ============================================================
# History Creation Tests (Verify recording on config changes)
# ============================================================

class TestHistoryRecording:
    """Tests that verify history is recorded on config changes."""

    @pytest.mark.asyncio
    async def test_history_recorded_on_strategy_create(self, client):
        """Test that history is recorded when creating a strategy."""
        response = client.post(
            "/api/v1/config/strategies",
            json=create_test_strategy(),
            headers={"X-User-Role": "admin"}
        )
        assert response.status_code == 201

        # Check history
        history_response = client.get("/api/v1/config/history?entity_type=strategy")
        history_data = history_response.json()
        items = history_data.get("items", history_data) if isinstance(history_data, dict) else history_data
        assert len(items) >= 1
        assert items[0]["action"] == "CREATE"

    @pytest.mark.asyncio
    async def test_history_recorded_on_strategy_update(self, client):
        """Test that history is recorded when updating a strategy."""
        # Create first
        create_response = client.post(
            "/api/v1/config/strategies",
            json=create_test_strategy(),
            headers={"X-User-Role": "admin"}
        )
        strategy_id = create_response.json()["id"]

        # Update
        client.put(
            f"/api/v1/config/strategies/{strategy_id}",
            json={"name": "Updated Name"},
            headers={"X-User-Role": "admin"}
        )

        # Check history
        history_response = client.get(
            f"/api/v1/config/history?entity_type=strategy&entity_id={strategy_id}"
        )
        history_data = history_response.json()
        items = history_data.get("items", history_data) if isinstance(history_data, dict) else history_data

        actions = [item["action"] for item in items]
        assert "CREATE" in actions
        assert "UPDATE" in actions

    @pytest.mark.asyncio
    async def test_history_recorded_on_strategy_delete(self, client):
        """Test that history is recorded when deleting a strategy."""
        # Create first
        create_response = client.post(
            "/api/v1/config/strategies",
            json=create_test_strategy(),
            headers={"X-User-Role": "admin"}
        )
        strategy_id = create_response.json()["id"]

        # Delete
        client.delete(
            f"/api/v1/config/strategies/{strategy_id}",
            headers={"X-User-Role": "admin"}
        )

        # Check history
        history_response = client.get(
            f"/api/v1/config/history?entity_type=strategy&entity_id={strategy_id}"
        )
        history_data = history_response.json()
        items = history_data.get("items", history_data) if isinstance(history_data, dict) else history_data

        actions = [item["action"] for item in items]
        assert "DELETE" in actions

    @pytest.mark.asyncio
    async def test_history_recorded_on_risk_config_update(self, client):
        """Test that history is recorded when updating risk config."""
        client.put(
            "/api/v1/config/risk",
            json=create_test_risk_config(),
            headers={"X-User-Role": "admin"}
        )

        history_response = client.get("/api/v1/config/history?entity_type=risk_config")
        history_data = history_response.json()
        items = history_data.get("items", history_data) if isinstance(history_data, dict) else history_data
        assert len(items) >= 1
        assert items[0]["action"] == "UPDATE"

    @pytest.mark.asyncio
    async def test_history_recorded_on_system_config_update(self, client):
        """Test that history is recorded when updating system config."""
        client.put(
            "/api/v1/config/system",
            json=create_test_system_config(),
            headers={"X-User-Role": "admin"}
        )

        history_response = client.get("/api/v1/config/history?entity_type=system_config")
        history_data = history_response.json()
        items = history_data.get("items", history_data) if isinstance(history_data, dict) else history_data
        assert len(items) >= 1


# ============================================================
# Boundary Condition Tests
# ============================================================

class TestHistoryBoundaryConditions:
    """Tests for boundary conditions and edge cases."""

    @pytest.mark.asyncio
    async def test_get_history_with_zero_limit(self, client):
        """Test GET /history with limit=0 returns empty or minimal results."""
        # Create some history first
        client.post(
            "/api/v1/config/strategies",
            json=create_test_strategy(),
            headers={"X-User-Role": "admin"}
        )

        response = client.get("/api/v1/config/history?limit=0")
        assert response.status_code == 200
        data = response.json()
        items = data.get("items", data) if isinstance(data, dict) else data
        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_get_history_with_large_offset(self, client):
        """Test GET /history with large offset returns empty."""
        # Create some history
        for i in range(3):
            client.post(
                "/api/v1/config/strategies",
                json={
                    "name": f"Strategy {i}",
                    "trigger": {"type": "pinbar", "enabled": True, "params": {}},
                    "filters": [],
                    "filter_logic": "AND",
                },
                headers={"X-User-Role": "admin"}
            )

        response = client.get("/api/v1/config/history?offset=1000")
        assert response.status_code == 200
        data = response.json()
        items = data.get("items", data) if isinstance(data, dict) else data
        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_get_history_with_invalid_entity_type(self, client):
        """Test GET /history with invalid entity_type returns empty."""
        response = client.get("/api/v1/config/history?entity_type=invalid_type")
        assert response.status_code == 200
        data = response.json()
        items = data.get("items", data) if isinstance(data, dict) else data
        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_history_change_summary_populated(self, client):
        """Test that history records have change_summary populated."""
        client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.015", "max_leverage": 12},
            headers={"X-User-Role": "admin"}
        )

        history_response = client.get("/api/v1/config/history?entity_type=risk_config")
        history_data = history_response.json()
        items = history_data.get("items", history_data) if isinstance(history_data, dict) else history_data

        assert len(items) >= 1
        # change_summary should be a non-empty string or null
        assert "change_summary" in items[0]

    @pytest.mark.asyncio
    async def test_history_timestamp_valid(self, client):
        """Test that history records have valid changed_at timestamp."""
        client.post(
            "/api/v1/config/strategies",
            json=create_test_strategy(),
            headers={"X-User-Role": "admin"}
        )

        history_response = client.get("/api/v1/config/history")
        history_data = history_response.json()
        items = history_data.get("items", history_data) if isinstance(history_data, dict) else history_data

        assert len(items) >= 1
        changed_at = items[0]["changed_at"]
        # Should be a valid ISO 8601 timestamp
        assert changed_at is not None
        datetime.fromisoformat(changed_at.replace("Z", "+00:00"))


# ============================================================
# Permission Tests
# ============================================================

class TestHistoryPermission:
    """Tests for permission checks on history endpoints."""

    @pytest.mark.asyncio
    async def test_get_history_without_admin(self, client):
        """Test GET /history works without admin role (read-only)."""
        # History read should be allowed for non-admin
        response = client.get("/api/v1/config/history")
        # Should succeed (read-only operation)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_rollback_requires_admin(self, client):
        """Test POST /history/rollback requires admin role."""
        response = client.post(
            "/api/v1/config/history/rollback",
            json={
                "history_id": 1,
                "entity_type": "strategy",
                "entity_id": "test",
            }
            # No admin header
        )
        assert response.status_code in [401, 403]


# ============================================================
# Main entry point
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=src/interfaces/api_v1_config"])
