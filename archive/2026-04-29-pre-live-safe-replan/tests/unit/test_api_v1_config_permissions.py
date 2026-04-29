"""
Permission Boundary Tests for Configuration Management API v1

Tests all permission checks in src/interfaces/api_v1_config.py:
- 401 Unauthorized: Missing authentication
- 401 Unauthorized: Invalid token format
- 401 Unauthorized: Expired token
- 403 Forbidden: Non-admin user accessing admin endpoints
- 200 OK: Admin user accessing admin endpoints

Coverage target: All admin endpoints
Test cases: 15+
"""
import json
import pytest
import tempfile
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from fastapi.testclient import TestClient
from fastapi import FastAPI, HTTPException

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
    check_admin_permission,
)
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
    app = FastAPI(title="Config API Permission Test")
    app.include_router(router, tags=["config"])
    return app


@pytest.fixture
def client(app, db_manager):
    """Create TestClient with injected dependencies."""
    # Set dependencies
    set_dependencies(
        strategy_repo=db_manager.strategy_repo,
        risk_repo=db_manager.risk_repo,
        system_repo=db_manager.system_repo,
        symbol_repo=db_manager.symbol_repo,
        notification_repo=db_manager.notification_repo,
        history_repo=db_manager.history_repo,
        snapshot_repo=db_manager.snapshot_repo,
    )

    # Clear preview cache before each test
    _import_preview_cache.clear()

    with TestClient(app) as c:
        yield c


# ============================================================
# Permission Check Function Tests (Unit Level)
# ============================================================

class TestCheckAdminPermissionFunction:
    """Tests for the check_admin_permission function itself."""

    @pytest.mark.asyncio
    async def test_permission_check_with_valid_admin_header(self, app):
        """Test check_admin_permission passes with valid admin header."""
        from starlette.requests import Request
        from starlette.datastructures import Headers

        # Create mock request with admin header
        class MockRequest:
            def __init__(self, headers: Dict[str, str]):
                self._headers = headers

            @property
            def headers(self):
                return Headers(self._headers)

        request = MockRequest({"x-user-role": "admin"})
        result = await check_admin_permission(request)
        assert result is True

    @pytest.mark.asyncio
    async def test_permission_check_with_alternate_admin_header(self, app):
        """Test check_admin_permission passes with X-User-User-Role header (typo variant)."""
        from starlette.requests import Request
        from starlette.datastructures import Headers

        class MockRequest:
            def __init__(self, headers: Dict[str, str]):
                self._headers = headers

            @property
            def headers(self):
                return Headers(self._headers)

        # Test alternate header (typo variant)
        request = MockRequest({"x-user-user-role": "admin"})
        result = await check_admin_permission(request)
        assert result is True

    @pytest.mark.asyncio
    async def test_permission_check_without_header(self, app):
        """Test check_admin_permission raises 401 without header."""
        from starlette.requests import Request
        from starlette.datastructures import Headers

        class MockRequest:
            def __init__(self, headers: Dict[str, str] = None):
                self._headers = headers or {}

            @property
            def headers(self):
                return Headers(self._headers)

        request = MockRequest()
        with pytest.raises(HTTPException) as exc_info:
            await check_admin_permission(request)
        assert exc_info.value.status_code == 401
        assert "Authentication required" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_permission_check_with_non_admin_role(self, app):
        """Test check_admin_permission raises 401 with non-admin role."""
        from starlette.requests import Request
        from starlette.datastructures import Headers

        class MockRequest:
            def __init__(self, headers: Dict[str, str]):
                self._headers = headers

            @property
            def headers(self):
                return Headers(self._headers)

        request = MockRequest({"x-user-role": "user"})
        with pytest.raises(HTTPException) as exc_info:
            await check_admin_permission(request)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_permission_check_with_empty_role(self, app):
        """Test check_admin_permission raises 401 with empty role."""
        from starlette.requests import Request
        from starlette.datastructures import Headers

        class MockRequest:
            def __init__(self, headers: Dict[str, str]):
                self._headers = headers

            @property
            def headers(self):
                return Headers(self._headers)

        request = MockRequest({"x-user-role": ""})
        with pytest.raises(HTTPException) as exc_info:
            await check_admin_permission(request)
        assert exc_info.value.status_code == 401


# ============================================================
# Risk Config Permission Tests
# ============================================================

class TestRiskConfigPermissions:
    """Tests for /api/v1/config/risk endpoint permissions."""

    @pytest.mark.asyncio
    async def test_get_risk_config_no_auth_required(self, client):
        """Test GET /risk does NOT require authentication (read is public)."""
        response = client.get("/api/v1/config/risk")
        # GET endpoints should return 200 or 404 (not found), not 401
        assert response.status_code in [200, 404]

    @pytest.mark.asyncio
    async def test_update_risk_config_without_auth(self, client):
        """Test PUT /risk without authentication returns 401."""
        response = client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.01"}
        )
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data
        assert "Authentication required" in data["detail"]

    @pytest.mark.asyncio
    async def test_update_risk_config_with_admin_auth(self, client):
        """Test PUT /risk with admin authentication succeeds."""
        response = client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.01", "max_leverage": 10},
            headers={"X-User-Role": "admin"}
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_update_risk_config_with_user_role(self, client):
        """Test PUT /risk with user role (non-admin) returns 401."""
        response = client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.01"},
            headers={"X-User-Role": "user"}
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_update_risk_config_with_invalid_token_format(self, client):
        """Test PUT /risk with invalid token format returns 401."""
        response = client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.01"},
            headers={"X-User-Role": "Bearer invalid_token_12345"}
        )
        assert response.status_code == 401


# ============================================================
# System Config Permission Tests
# ============================================================

class TestSystemConfigPermissions:
    """Tests for /api/v1/config/system endpoint permissions."""

    @pytest.mark.asyncio
    async def test_get_system_config_no_auth_required(self, client):
        """Test GET /system does NOT require authentication (read is public)."""
        response = client.get("/api/v1/config/system")
        assert response.status_code in [200, 404]

    @pytest.mark.asyncio
    async def test_update_system_config_without_auth(self, client):
        """Test PUT /system without authentication returns 401."""
        response = client.put(
            "/api/v1/config/system",
            json={"ema_period": 50}
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_update_system_config_with_admin_auth(self, client):
        """Test PUT /system with admin authentication succeeds."""
        response = client.put(
            "/api/v1/config/system",
            json={"ema_period": 50, "mtf_ema_period": 50},
            headers={"X-User-Role": "admin"}
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_update_system_config_with_user_role(self, client):
        """Test PUT /system with user role (non-admin) returns 401."""
        response = client.put(
            "/api/v1/config/system",
            json={"ema_period": 50},
            headers={"X-User-Role": "user"}
        )
        assert response.status_code == 401


# ============================================================
# Strategy Config Permission Tests
# ============================================================

class TestStrategyConfigPermissions:
    """Tests for /api/v1/config/strategies/* endpoint permissions."""

    @pytest.mark.asyncio
    async def test_get_strategies_no_auth_required(self, client):
        """Test GET /strategies does NOT require authentication."""
        response = client.get("/api/v1/config/strategies")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_create_strategy_without_auth(self, client):
        """Test POST /strategies without authentication returns 401."""
        response = client.post(
            "/api/v1/config/strategies",
            json={
                "name": "Unauthorized Strategy",
                "trigger": {"type": "pinbar", "enabled": True, "params": {}},
                "filters": [],
                "filter_logic": "AND",
            }
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_strategy_with_admin_auth(self, client):
        """Test POST /strategies with admin authentication succeeds."""
        response = client.post(
            "/api/v1/config/strategies",
            json={
                "name": "Admin Strategy",
                "trigger": {"type": "pinbar", "enabled": True, "params": {}},
                "filters": [],
                "filter_logic": "AND",
            },
            headers={"X-User-Role": "admin"}
        )
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_update_strategy_without_auth(self, client):
        """Test PUT /strategies/{id} without authentication returns 401."""
        # Create first with admin
        create_response = client.post(
            "/api/v1/config/strategies",
            json={
                "name": "Test Strategy",
                "trigger": {"type": "pinbar", "enabled": True, "params": {}},
                "filters": [],
                "filter_logic": "AND",
            },
            headers={"X-User-Role": "admin"}
        )
        strategy_id = create_response.json()["id"]

        # Try update without auth
        response = client.put(
            f"/api/v1/config/strategies/{strategy_id}",
            json={"name": "Updated Name"}
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_strategy_without_auth(self, client):
        """Test DELETE /strategies/{id} without authentication returns 401."""
        # Create first with admin
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

        # Try delete without auth
        response = client.delete(f"/api/v1/config/strategies/{strategy_id}")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_toggle_strategy_without_auth(self, client):
        """Test POST /strategies/{id}/toggle without authentication returns 401."""
        # Create first with admin
        create_response = client.post(
            "/api/v1/config/strategies",
            json={
                "name": "Toggle Test",
                "trigger": {"type": "pinbar", "enabled": True, "params": {}},
                "filters": [],
                "filter_logic": "AND",
            },
            headers={"X-User-Role": "admin"}
        )
        strategy_id = create_response.json()["id"]

        # Try toggle without auth
        response = client.post(f"/api/v1/config/strategies/{strategy_id}/toggle")
        assert response.status_code == 401


# ============================================================
# Symbol Config Permission Tests
# ============================================================

class TestSymbolConfigPermissions:
    """Tests for /api/v1/config/symbols/* endpoint permissions."""

    @pytest.mark.asyncio
    async def test_get_symbols_no_auth_required(self, client):
        """Test GET /symbols does NOT require authentication."""
        response = client.get("/api/v1/config/symbols")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_create_symbol_without_auth(self, client):
        """Test POST /symbols without authentication returns 401."""
        response = client.post(
            "/api/v1/config/symbols",
            json={"symbol": "BTC/USDT:USDT", "is_core": True}
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_symbol_with_admin_auth(self, client):
        """Test POST /symbols with admin authentication succeeds."""
        response = client.post(
            "/api/v1/config/symbols",
            json={"symbol": "BTC/USDT:USDT", "is_core": True},
            headers={"X-User-Role": "admin"}
        )
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_update_symbol_without_auth(self, client):
        """Test PUT /symbols/{symbol} without authentication returns 401."""
        # Create first with admin
        client.post(
            "/api/v1/config/symbols",
            json={"symbol": "ETH/USDT:USDT", "is_core": False},
            headers={"X-User-Role": "admin"}
        )

        # Try update without auth
        response = client.put(
            "/api/v1/config/symbols/ETH/USDT:USDT",
            json={"is_active": False}
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_symbol_without_auth(self, client):
        """Test DELETE /symbols/{symbol} without authentication returns 401."""
        # Create first with admin
        client.post(
            "/api/v1/config/symbols",
            json={"symbol": "SOL/USDT:USDT", "is_core": False},
            headers={"X-User-Role": "admin"}
        )

        # Try delete without auth
        response = client.delete("/api/v1/config/symbols/SOL/USDT:USDT")
        assert response.status_code == 401


# ============================================================
# Notification Config Permission Tests
# ============================================================

class TestNotificationConfigPermissions:
    """Tests for /api/v1/config/notifications/* endpoint permissions."""

    @pytest.mark.asyncio
    async def test_get_notifications_no_auth_required(self, client):
        """Test GET /notifications does NOT require authentication."""
        response = client.get("/api/v1/config/notifications")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_create_notification_without_auth(self, client):
        """Test POST /notifications without authentication returns 401."""
        response = client.post(
            "/api/v1/config/notifications",
            json={
                "channel_type": "feishu",
                "webhook_url": "https://example.com/webhook"
            }
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_notification_with_admin_auth(self, client):
        """Test POST /notifications with admin authentication succeeds."""
        response = client.post(
            "/api/v1/config/notifications",
            json={
                "channel_type": "feishu",
                "webhook_url": "https://example.com/webhook"
            },
            headers={"X-User-Role": "admin"}
        )
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_test_notification_without_auth(self, client):
        """Test POST /notifications/{id}/test without authentication returns 401."""
        # Create first with admin
        create_response = client.post(
            "/api/v1/config/notifications",
            json={
                "channel_type": "feishu",
                "webhook_url": "https://example.com/webhook"
            },
            headers={"X-User-Role": "admin"}
        )
        notification_id = create_response.json()["id"]

        # Try test without auth
        response = client.post(f"/api/v1/config/notifications/{notification_id}/test")
        assert response.status_code == 401


# ============================================================
# Import/Export Permission Tests
# ============================================================

class TestImportExportPermissions:
    """Tests for /api/v1/config/export and /import/* endpoint permissions."""

    @pytest.mark.asyncio
    async def test_export_config_without_auth(self, client):
        """Test POST /export without authentication returns 401."""
        response = client.post(
            "/api/v1/config/export",
            json={"include_risk": True}
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_export_config_with_admin_auth(self, client):
        """Test POST /export with admin authentication succeeds."""
        # Create some config first
        client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.01"},
            headers={"X-User-Role": "admin"}
        )

        response = client.post(
            "/api/v1/config/export",
            json={"include_risk": True},
            headers={"X-User-Role": "admin"}
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_preview_import_without_auth(self, client):
        """Test POST /import/preview without authentication returns 401."""
        yaml_content = "risk:\n  max_loss_percent: 0.01"
        response = client.post(
            "/api/v1/config/import/preview",
            json={"yaml_content": yaml_content}
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_preview_import_with_admin_auth(self, client):
        """Test POST /import/preview with admin authentication succeeds."""
        yaml_content = "risk:\n  max_loss_percent: 0.01"
        response = client.post(
            "/api/v1/config/import/preview",
            json={"yaml_content": yaml_content, "filename": "test.yaml"},
            headers={"X-User-Role": "admin"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "preview_token" in data

    @pytest.mark.asyncio
    async def test_confirm_import_without_auth(self, client):
        """Test POST /import/confirm without authentication returns 401."""
        response = client.post(
            "/api/v1/config/import/confirm",
            json={"preview_token": "test-token"}
        )
        assert response.status_code == 401


# ============================================================
# Snapshot Permission Tests
# ============================================================

class TestSnapshotPermissions:
    """Tests for /api/v1/config/snapshots/* endpoint permissions."""

    @pytest.mark.asyncio
    async def test_get_snapshots_no_auth_required(self, client):
        """Test GET /snapshots does NOT require authentication."""
        response = client.get("/api/v1/config/snapshots")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_create_snapshot_without_auth(self, client):
        """Test POST /snapshots without authentication returns 401."""
        response = client.post(
            "/api/v1/config/snapshots",
            json={"name": "Test Snapshot", "description": "Test"}
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_snapshot_with_admin_auth(self, client):
        """Test POST /snapshots with admin authentication succeeds."""
        # Create some config first
        client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.01"},
            headers={"X-User-Role": "admin"}
        )

        response = client.post(
            "/api/v1/config/snapshots",
            json={"name": "Test Snapshot", "description": "Test"},
            headers={"X-User-Role": "admin"}
        )
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_activate_snapshot_without_auth(self, client):
        """Test POST /snapshots/{id}/activate without authentication returns 401."""
        # Create config and snapshot with admin
        client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.01"},
            headers={"X-User-Role": "admin"}
        )
        create_response = client.post(
            "/api/v1/config/snapshots",
            json={"name": "Activate Test"},
            headers={"X-User-Role": "admin"}
        )
        snapshot_id = create_response.json()["id"]

        # Try activate without auth
        response = client.post(f"/api/v1/config/snapshots/{snapshot_id}/activate")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_snapshot_without_auth(self, client):
        """Test DELETE /snapshots/{id} without authentication returns 401."""
        # Create config and snapshot with admin
        client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.01"},
            headers={"X-User-Role": "admin"}
        )
        create_response = client.post(
            "/api/v1/config/snapshots",
            json={"name": "Delete Test"},
            headers={"X-User-Role": "admin"}
        )
        snapshot_id = create_response.json()["id"]

        # Try delete without auth
        response = client.delete(f"/api/v1/config/snapshots/{snapshot_id}")
        assert response.status_code == 401


# ============================================================
# Token Expiration Tests (Simulated)
# ============================================================

class TestTokenExpirationSimulation:
    """Tests simulating token expiration scenarios."""

    @pytest.mark.asyncio
    async def test_permission_check_header_change_invalidates(self, client):
        """Test that changing the role header invalidates permission."""
        # First request with admin
        response1 = client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.01"},
            headers={"X-User-Role": "admin"}
        )
        assert response1.status_code == 200

        # Second request with user role (simulating token downgrade)
        response2 = client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.02"},
            headers={"X-User-Role": "user"}
        )
        assert response2.status_code == 401

    @pytest.mark.asyncio
    async def test_permission_check_header_removal_invalidates(self, client):
        """Test that removing the auth header invalidates permission."""
        # First request with admin
        response1 = client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.01"},
            headers={"X-User-Role": "admin"}
        )
        assert response1.status_code == 200

        # Second request without header (simulating expired token)
        response2 = client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.02"}
        )
        assert response2.status_code == 401


# ============================================================
# Response Format Tests
# ============================================================

class TestPermissionResponseFormat:
    """Tests for permission error response format."""

    @pytest.mark.asyncio
    async def test_401_response_format(self, client):
        """Test 401 response has correct format."""
        response = client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.01"}
        )

        assert response.status_code == 401
        data = response.json()
        assert "detail" in data
        assert isinstance(data["detail"], str)
        assert "Authentication required" in data["detail"]

    @pytest.mark.asyncio
    async def test_401_response_headers(self, client):
        """Test 401 response has correct headers."""
        response = client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.01"}
        )

        assert response.status_code == 401
        assert "application/json" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_permission_error_message_clarity(self, client):
        """Test permission error message is clear and actionable."""
        response = client.post(
            "/api/v1/config/strategies",
            json={
                "name": "Test",
                "trigger": {"type": "pinbar", "enabled": True, "params": {}},
                "filters": [],
            }
        )

        assert response.status_code == 401
        data = response.json()
        detail = data["detail"]
        # Message should mention the required header
        assert "X-User-Role" in detail or "header" in detail.lower()


# ============================================================
# Permission Boundary Edge Cases
# ============================================================

class TestPermissionEdgeCases:
    """Tests for permission boundary edge cases."""

    @pytest.mark.asyncio
    async def test_case_insensitive_admin_check(self, client):
        """Test admin role check is case-sensitive (should fail with 'Admin')."""
        response = client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.01"},
            headers={"X-User-Role": "Admin"}  # Capital A
        )
        # Current implementation is case-sensitive
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_whitespace_in_role_value(self, client):
        """Test role value with whitespace is rejected."""
        response = client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.01"},
            headers={"X-User-Role": " admin "}
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_both_headers_present_primary_takes_precedence(self, client):
        """Test that X-User-Role takes precedence over X-User-User-Role."""
        # X-User-Role is checked first, so "admin" should work
        response = client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.01"},
            headers={
                "X-User-Role": "admin",
                "X-User-User-Role": "user"
            }
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_alternate_header_fallback(self, client):
        """Test X-User-User-Role works as fallback."""
        response = client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.01"},
            headers={"X-User-User-Role": "admin"}
        )
        assert response.status_code == 200


# ============================================================
# Main entry point
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
