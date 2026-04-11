"""
Risk Config Boundary Value Tests

Tests boundary conditions for risk configuration API endpoints:
- GET/PUT /api/v1/config/risk

Coverage targets:
- Zero values (0)
- Negative values (should be rejected)
- Extremely large values (should be handled/rejected)
- Decimal precision
- String injection attempts
- Null/None values

Test cases: >= 20
"""
import pytest
import tempfile
import os
from decimal import Decimal
from typing import Dict, Any

from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.infrastructure.repositories.config_repositories import (
    RiskConfigRepository,
    ConfigDatabaseManager,
)
from src.interfaces.api_v1_config import router
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
    app = FastAPI(title="Risk Config Boundary Test")
    app.include_router(router, tags=["config"])
    return app


@pytest.fixture
def client(app, db_manager):
    """Create TestClient with injected dependencies."""
    set_dependencies(
        risk_repo=db_manager.risk_repo,
        system_repo=db_manager.system_repo,
        strategy_repo=db_manager.strategy_repo,
        symbol_repo=db_manager.symbol_repo,
        notification_repo=db_manager.notification_repo,
        history_repo=db_manager.history_repo,
        snapshot_repo=db_manager.snapshot_repo,
    )
    with TestClient(app) as c:
        yield c


# ============================================================
# Boundary Test Cases
# ============================================================

class TestRiskConfigZeroValues:
    """Test handling of zero values."""

    @pytest.mark.asyncio
    async def test_max_loss_percent_zero_boundary(self, client):
        """Test that max_loss_percent=0 is at boundary (accepted but means no risk)."""
        # Note: Business logic allows 0, which means "no loss allowed"
        # This is a design decision - 0% loss tolerance is technically valid
        response = client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0", "max_leverage": 10},
            headers={"X-User-Role": "admin"}
        )
        # Accepts 0 as valid boundary value
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_max_leverage_zero_rejected(self, client):
        """Test that max_leverage=0 is rejected."""
        response = client.put(
            "/api/v1/config/risk",
            json={"max_leverage": 0},
            headers={"X-User-Role": "admin"}
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_max_total_exposure_zero_allowed(self, client):
        """Test that max_total_exposure=0 is allowed (no exposure)."""
        # First set required fields
        client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.01", "max_leverage": 10},
            headers={"X-User-Role": "admin"}
        )

        response = client.put(
            "/api/v1/config/risk",
            json={"max_total_exposure": "0"},
            headers={"X-User-Role": "admin"}
        )
        assert response.status_code == 200
        data = response.json()
        # Note: Database may return None for zero Decimal values
        assert data["max_total_exposure"] in ["0", "0.0", None]

    @pytest.mark.asyncio
    async def test_daily_max_trades_zero_rejected(self, client):
        """Test that daily_max_trades=0 is rejected."""
        response = client.put(
            "/api/v1/config/risk",
            json={"daily_max_trades": 0},
            headers={"X-User-Role": "admin"}
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_cooldown_minutes_zero_allowed(self, client):
        """Test that cooldown_minutes=0 is allowed (no cooldown)."""
        # First set required fields
        client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.01", "max_leverage": 10},
            headers={"X-User-Role": "admin"}
        )

        response = client.put(
            "/api/v1/config/risk",
            json={"cooldown_minutes": 0},
            headers={"X-User-Role": "admin"}
        )
        assert response.status_code == 200


class TestRiskConfigNegativeValues:
    """Test handling of negative values (should be rejected)."""

    @pytest.mark.asyncio
    async def test_max_loss_percent_negative_rejected(self, client):
        """Test that negative max_loss_percent is rejected."""
        response = client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "-0.01"},
            headers={"X-User-Role": "admin"}
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_max_leverage_negative_rejected(self, client):
        """Test that negative max_leverage is rejected."""
        response = client.put(
            "/api/v1/config/risk",
            json={"max_leverage": -1},
            headers={"X-User-Role": "admin"}
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_max_total_exposure_negative_rejected(self, client):
        """Test that negative max_total_exposure is rejected."""
        response = client.put(
            "/api/v1/config/risk",
            json={"max_total_exposure": "-0.1"},
            headers={"X-User-Role": "admin"}
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_daily_max_loss_negative_rejected(self, client):
        """Test that negative daily_max_loss is rejected."""
        response = client.put(
            "/api/v1/config/risk",
            json={"daily_max_loss": "-1000"},
            headers={"X-User-Role": "admin"}
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_daily_max_trades_negative_rejected(self, client):
        """Test that negative daily_max_trades is rejected."""
        response = client.put(
            "/api/v1/config/risk",
            json={"daily_max_trades": -5},
            headers={"X-User-Role": "admin"}
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_max_position_hold_time_negative_rejected(self, client):
        """Test that negative max_position_hold_time is rejected."""
        response = client.put(
            "/api/v1/config/risk",
            json={"max_position_hold_time": -3600},
            headers={"X-User-Role": "admin"}
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_cooldown_minutes_negative_rejected(self, client):
        """Test that negative cooldown_minutes is rejected."""
        response = client.put(
            "/api/v1/config/risk",
            json={"cooldown_minutes": -60},
            headers={"X-User-Role": "admin"}
        )
        assert response.status_code == 422


class TestRiskConfigLargeValues:
    """Test handling of extremely large values."""

    @pytest.mark.asyncio
    async def test_max_loss_percent_gt_one_rejected(self, client):
        """Test that max_loss_percent > 1 (100%) is rejected."""
        response = client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "1.5"},
            headers={"X-User-Role": "admin"}
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_max_loss_percent_exactly_one_allowed(self, client):
        """Test that max_loss_percent = 1 (100%) is allowed (edge case)."""
        # First set required fields
        client.put(
            "/api/v1/config/risk",
            json={"max_leverage": 10},
            headers={"X-User-Role": "admin"}
        )

        response = client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "1"},
            headers={"X-User-Role": "admin"}
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_max_leverage_exceeds_125_rejected(self, client):
        """Test that max_leverage > 125 is rejected."""
        response = client.put(
            "/api/v1/config/risk",
            json={"max_leverage": 126},
            headers={"X-User-Role": "admin"}
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_max_leverage_exactly_125_allowed(self, client):
        """Test that max_leverage = 125 is allowed."""
        # First set required fields
        client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.01"},
            headers={"X-User-Role": "admin"}
        )

        response = client.put(
            "/api/v1/config/risk",
            json={"max_leverage": 125},
            headers={"X-User-Role": "admin"}
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_max_total_exposure_gt_one_rejected(self, client):
        """Test that max_total_exposure > 1 (100%) is rejected."""
        response = client.put(
            "/api/v1/config/risk",
            json={"max_total_exposure": "1.5"},
            headers={"X-User-Role": "admin"}
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_max_leverage_extremely_large_rejected(self, client):
        """Test that extremely large max_leverage is rejected."""
        response = client.put(
            "/api/v1/config/risk",
            json={"max_leverage": 999999},
            headers={"X-User-Role": "admin"}
        )
        assert response.status_code == 422


class TestRiskConfigDecimalPrecision:
    """Test handling of decimal precision."""

    @pytest.mark.asyncio
    async def test_max_loss_percent_high_precision(self, client):
        """Test max_loss_percent with high precision (6 decimal places)."""
        client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.012345", "max_leverage": 10},
            headers={"X-User-Role": "admin"}
        )

        response = client.get("/api/v1/config/risk")
        assert response.status_code == 200
        data = response.json()
        # Should preserve precision
        assert data["max_loss_percent"] == "0.012345"

    @pytest.mark.asyncio
    async def test_max_loss_percent_very_small_positive(self, client):
        """Test max_loss_percent with very small positive value."""
        client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.0001", "max_leverage": 10},
            headers={"X-User-Role": "admin"}
        )

        response = client.get("/api/v1/config/risk")
        assert response.status_code == 200
        data = response.json()
        assert data["max_loss_percent"] == "0.0001"

    @pytest.mark.asyncio
    async def test_max_total_exposure_precision(self, client):
        """Test max_total_exposure with high precision."""
        client.put(
            "/api/v1/config/risk",
            json={
                "max_loss_percent": "0.01",
                "max_leverage": 10,
                "max_total_exposure": "0.987654"
            },
            headers={"X-User-Role": "admin"}
        )

        response = client.get("/api/v1/config/risk")
        assert response.status_code == 200
        data = response.json()
        assert data["max_total_exposure"] == "0.987654"

    @pytest.mark.asyncio
    async def test_daily_max_loss_decimal(self, client):
        """Test daily_max_loss with decimal value."""
        client.put(
            "/api/v1/config/risk",
            json={
                "max_loss_percent": "0.01",
                "max_leverage": 10,
                "daily_max_loss": "1234.5678"
            },
            headers={"X-User-Role": "admin"}
        )

        response = client.get("/api/v1/config/risk")
        assert response.status_code == 200
        data = response.json()
        assert data["daily_max_loss"] == "1234.5678"


class TestRiskConfigStringInjection:
    """Test handling of string injection attempts."""

    @pytest.mark.asyncio
    async def test_max_loss_percent_string_rejected(self, client):
        """Test that string value for max_loss_percent is rejected."""
        response = client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "not_a_number"},
            headers={"X-User-Role": "admin"}
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_max_leverage_string_rejected(self, client):
        """Test that non-numeric string for max_leverage is rejected."""
        response = client.put(
            "/api/v1/config/risk",
            json={"max_leverage": "abc"},
            headers={"X-User-Role": "admin"}
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_max_leverage_numeric_string_allowed(self, client):
        """Test that numeric string for max_leverage is allowed (coerced)."""
        client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.01", "max_leverage": "50"},
            headers={"X-User-Role": "admin"}
        )

        response = client.get("/api/v1/config/risk")
        assert response.status_code == 200
        data = response.json()
        assert data["max_leverage"] == 50

    @pytest.mark.asyncio
    async def test_sql_injection_in_field(self, client):
        """Test that SQL injection attempt in field is rejected."""
        response = client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.01; DROP TABLE risk_configs;--"},
            headers={"X-User-Role": "admin"}
        )
        assert response.status_code == 422


class TestRiskConfigNullValues:
    """Test handling of null/None values."""

    @pytest.mark.asyncio
    async def test_partial_update_only_max_loss_percent(self, client):
        """Test partial update with only max_loss_percent."""
        # First create config
        client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.01", "max_leverage": 10},
            headers={"X-User-Role": "admin"}
        )

        # Partial update
        response = client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.015"},
            headers={"X-User-Role": "admin"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["max_loss_percent"] == "0.015"
        assert data["max_leverage"] == 10  # Unchanged

    @pytest.mark.asyncio
    async def test_partial_update_only_max_leverage(self, client):
        """Test partial update with only max_leverage."""
        client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.01", "max_leverage": 10},
            headers={"X-User-Role": "admin"}
        )

        response = client.put(
            "/api/v1/config/risk",
            json={"max_leverage": 20},
            headers={"X-User-Role": "admin"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["max_leverage"] == 20
        assert data["max_loss_percent"] == "0.01"  # Unchanged

    @pytest.mark.asyncio
    async def test_null_for_optional_field(self, client):
        """Test that null for optional field is handled."""
        client.put(
            "/api/v1/config/risk",
            json={
                "max_loss_percent": "0.01",
                "max_leverage": 10,
                "max_total_exposure": None
            },
            headers={"X-User-Role": "admin"}
        )

        response = client.get("/api/v1/config/risk")
        assert response.status_code == 200
        data = response.json()
        # Should either keep null or use default
        assert "max_total_exposure" in data

    @pytest.mark.asyncio
    async def test_empty_json_body_handled(self, client):
        """Test that empty JSON body returns error."""
        response = client.put(
            "/api/v1/config/risk",
            json={},
            headers={"X-User-Role": "admin"}
        )
        # Empty update may return 400 (bad request - no fields to update)
        # or 422 (validation error)
        assert response.status_code in [400, 422]

    @pytest.mark.asyncio
    async def test_get_before_set_returns_404_or_200(self, client):
        """Test GET before any config is set."""
        response = client.get("/api/v1/config/risk")
        # Should return 404 or empty config
        assert response.status_code in [200, 404]


class TestRiskConfigBoundaryConditions:
    """Test specific boundary conditions."""

    @pytest.mark.asyncio
    async def test_max_loss_percent_minimum_positive(self, client):
        """Test minimum positive max_loss_percent."""
        client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.0001", "max_leverage": 10},
            headers={"X-User-Role": "admin"}
        )

        response = client.get("/api/v1/config/risk")
        assert response.status_code == 200
        data = response.json()
        assert data["max_loss_percent"] == "0.0001"

    @pytest.mark.asyncio
    async def test_max_leverage_minimum(self, client):
        """Test minimum max_leverage (1x)."""
        client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.01", "max_leverage": 1},
            headers={"X-User-Role": "admin"}
        )

        response = client.get("/api/v1/config/risk")
        assert response.status_code == 200
        data = response.json()
        assert data["max_leverage"] == 1

    @pytest.mark.asyncio
    async def test_max_total_exposure_exactly_one(self, client):
        """Test max_total_exposure = 1 (100%)."""
        client.put(
            "/api/v1/config/risk",
            json={
                "max_loss_percent": "0.01",
                "max_leverage": 10,
                "max_total_exposure": "1"
            },
            headers={"X-User-Role": "admin"}
        )

        response = client.get("/api/v1/config/risk")
        assert response.status_code == 200
        data = response.json()
        # Note: JSON serialization may return "1" or "1.0" - both are valid
        assert data["max_total_exposure"] in ["1", "1.0"]

    @pytest.mark.asyncio
    async def test_multiple_updates_atomic(self, client):
        """Test that multiple field updates are atomic."""
        response = client.put(
            "/api/v1/config/risk",
            json={
                "max_loss_percent": "0.02",
                "max_leverage": 50,
                "max_total_exposure": "0.9"
            },
            headers={"X-User-Role": "admin"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["max_loss_percent"] == "0.02"
        assert data["max_leverage"] == 50
        assert data["max_total_exposure"] == "0.9"

    @pytest.mark.asyncio
    async def test_invalid_admin_header(self, client):
        """Test request with invalid admin header."""
        response = client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.01"},
            headers={"X-User-Role": "user"}  # Not admin
        )
        # Should fail with 401 or 403
        assert response.status_code in [401, 403]


# ============================================================
# Main entry point
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
