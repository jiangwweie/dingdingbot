"""
Integration Tests for Backtest Configuration API Endpoints

Tests for:
- GET /api/backtest/configs - Retrieve backtest configuration
- PUT /api/backtest/configs - Update backtest configuration with validation

Coverage:
1. GET endpoint returns 4 config items with correct defaults
2. PUT endpoint validates configuration value ranges
3. PUT endpoint saves to KV storage successfully
4. Invalid configurations return 422 validation errors
"""
import pytest
import tempfile
from pathlib import Path
from decimal import Decimal
import yaml
import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock

from fastapi.testclient import TestClient

from src.application.config_manager import ConfigManager
from src.interfaces.api import app, set_dependencies
from src.infrastructure.signal_repository import SignalRepository
from src.infrastructure.config_entry_repository import ConfigEntryRepository


# ============================================================
# Fixtures
# ============================================================
@pytest.fixture
def temp_config_dir():
    """Create temporary directory with valid test config files"""
    with tempfile.TemporaryDirectory() as tmpdir:
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
            "mtf_mapping": {"15m": "1h", "1h": "4h", "4h": "1d"},
            "warmup": {"history_bars": 100},
            "signal_pipeline": {"cooldown_seconds": 14400},
        }

        with open(config_dir / "core.yaml", "w") as f:
            yaml.dump(core_config, f)

        # Create user.yaml
        user_config = {
            "exchange": {
                "name": "binance",
                "api_key": "test_api_key_12345",
                "api_secret": "test_secret_67890",
                "testnet": True,
            },
            "user_symbols": [],
            "timeframes": ["15m", "1h"],
            "strategy": {
                "trend_filter_enabled": True,
                "mtf_validation_enabled": True,
            },
            "risk": {
                "max_loss_percent": "0.01",
                "max_leverage": 10,
            },
            "asset_polling": {"interval_seconds": 60},
            "notification": {
                "channels": [{
                    "type": "feishu",
                    "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/test123",
                }]
            },
        }

        with open(config_dir / "user.yaml", "w") as f:
            yaml.dump(user_config, f)

        yield config_dir


@pytest.fixture
def temp_db_path(temp_config_dir):
    """Return path to temporary database file"""
    return str(Path(temp_config_dir) / "test.db")


@pytest.fixture
def mock_config_manager(temp_config_dir, temp_db_path):
    """Create mock ConfigManager with KV config support"""
    # Create real ConfigManager with YAML config
    manager = ConfigManager(config_dir=str(temp_config_dir), db_path=temp_db_path)

    # Mock config entry repository for KV operations
    mock_config_entry_repo = AsyncMock(spec=ConfigEntryRepository)

    # Mock get_backtest_configs to return default values
    async def mock_get_backtest_configs(profile_name='default'):
        return {
            'slippage_rate': Decimal('0.001'),
            'fee_rate': Decimal('0.0004'),
            'initial_balance': Decimal('10000'),
            'tp_slippage_rate': Decimal('0.0005'),
        }

    # Mock save_backtest_configs to track calls
    saved_configs = {}
    async def mock_save_backtest_configs(configs, profile_name='default', version='v1.0.0'):
        saved_configs.update({f"{profile_name}:{k}": v for k, v in configs.items()})
        return len(configs)

    mock_config_entry_repo.get_backtest_configs = mock_get_backtest_configs
    mock_config_entry_repo.save_backtest_configs = mock_save_backtest_configs
    mock_config_entry_repo.saved_configs = saved_configs

    # Mock _get_current_profile_name to return 'default'
    async def mock_get_current_profile_name():
        return 'default'

    # Mock _log_config_change to do nothing
    async def mock_log_config_change(**kwargs):
        pass

    # Inject mock repository and methods
    manager._config_entry_repo = mock_config_entry_repo
    manager._get_current_profile_name = mock_get_current_profile_name
    manager._log_config_change = mock_log_config_change

    return manager


@pytest.fixture
def test_client(mock_config_manager, temp_db_path):
    """Create FastAPI TestClient with injected dependencies"""
    async def setup():
        # Initialize signal repository
        repo = SignalRepository(db_path=temp_db_path)
        # Skip table creation by mocking _db
        repo._db = MagicMock()
        repo._db.execute = AsyncMock()
        return repo

    async def cleanup(repo):
        pass  # Skip cleanup for mock

    # Setup
    repo = asyncio.run(setup())

    def mock_account_getter():
        return None

    set_dependencies(
        repository=repo,
        account_getter=mock_account_getter,
        config_manager=mock_config_manager,
    )

    client = TestClient(app)
    yield client

    # Cleanup
    asyncio.run(cleanup(repo))


# ============================================================
# Test 1: GET /api/backtest/configs - Retrieve Configuration
# ============================================================
class TestGetBacktestConfigs:
    """Test GET /api/backtest/configs endpoint"""

    def test_get_configs_returns_200(self, test_client):
        """Test that GET endpoint returns HTTP 200"""
        response = test_client.get("/api/backtest/configs")
        assert response.status_code == 200

    def test_get_configs_returns_4_items(self, test_client):
        """Test that GET endpoint returns all 4 config items"""
        response = test_client.get("/api/backtest/configs")
        assert response.status_code == 200

        data = response.json()
        assert "configs" in data

        configs = data["configs"]

        # Must have 4 config items
        assert "slippage_rate" in configs
        assert "fee_rate" in configs
        assert "initial_balance" in configs
        assert "tp_slippage_rate" in configs

    def test_get_configs_returns_string_values(self, test_client):
        """Test that config values are returned as strings"""
        response = test_client.get("/api/backtest/configs")
        assert response.status_code == 200

        data = response.json()
        configs = data["configs"]

        # All values should be strings (Decimal converted to str)
        assert isinstance(configs.get("slippage_rate"), str)
        assert isinstance(configs.get("fee_rate"), str)
        assert isinstance(configs.get("initial_balance"), str)
        assert isinstance(configs.get("tp_slippage_rate"), str)

    def test_get_configs_default_values(self, test_client):
        """Test that default values are correct"""
        response = test_client.get("/api/backtest/configs")
        assert response.status_code == 200

        data = response.json()
        configs = data["configs"]

        # Check default values
        assert configs.get("slippage_rate") == "0.001"
        assert configs.get("fee_rate") == "0.0004"
        assert configs.get("initial_balance") == "10000"
        assert configs.get("tp_slippage_rate") == "0.0005"


# ============================================================
# Test 2: PUT /api/backtest/configs - Update Configuration
# ============================================================
class TestUpdateBacktestConfigs:
    """Test PUT /api/backtest/configs endpoint"""

    def test_update_configs_returns_200(self, test_client):
        """Test that PUT endpoint returns HTTP 200"""
        payload = {
            "slippage_rate": 0.0015,
            "fee_rate": 0.0005,
        }
        response = test_client.put("/api/backtest/configs", json=payload)
        assert response.status_code == 200

    def test_update_configs_all_4_items(self, test_client):
        """Test updating all 4 config items"""
        payload = {
            "slippage_rate": 0.002,
            "fee_rate": 0.0006,
            "initial_balance": 20000,
            "tp_slippage_rate": 0.001,
        }
        response = test_client.put("/api/backtest/configs", json=payload)
        assert response.status_code == 200

        data = response.json()
        assert data.get("status") == "success"
        assert "Updated" in data.get("message", "")

    def test_update_configs_partial_update(self, test_client):
        """Test partial update (only some fields)"""
        payload = {
            "slippage_rate": 0.002,
        }
        response = test_client.put("/api/backtest/configs", json=payload)
        assert response.status_code == 200

        data = response.json()
        # Should indicate only 1 item was updated
        assert "1" in data.get("message", "")

    def test_update_configs_returns_updated_values(self, test_client):
        """Test that response contains updated values"""
        payload = {
            "slippage_rate": 0.0025,
            "fee_rate": 0.0008,
        }
        response = test_client.put("/api/backtest/configs", json=payload)
        assert response.status_code == 200

        data = response.json()
        configs = data.get("configs", {})

        assert configs.get("slippage_rate") == "0.0025"
        assert configs.get("fee_rate") == "0.0008"


# ============================================================
# Test 3: Validation - Invalid Configurations
# ============================================================
class TestUpdateConfigsValidation:
    """Test PUT /api/backtest/configs validation"""

    def test_update_slippage_rate_negative_returns_422(self, test_client):
        """Test that negative slippage_rate returns 422"""
        payload = {
            "slippage_rate": -0.001,
        }
        response = test_client.put("/api/backtest/configs", json=payload)
        assert response.status_code == 422

    def test_update_slippage_rate_exceeds_max_returns_422(self, test_client):
        """Test that slippage_rate > 0.01 returns 422"""
        payload = {
            "slippage_rate": 0.02,  # 2%, exceeds 1% max
        }
        response = test_client.put("/api/backtest/configs", json=payload)
        assert response.status_code == 422

    def test_update_fee_rate_negative_returns_422(self, test_client):
        """Test that negative fee_rate returns 422"""
        payload = {
            "fee_rate": -0.0001,
        }
        response = test_client.put("/api/backtest/configs", json=payload)
        assert response.status_code == 422

    def test_update_fee_rate_exceeds_max_returns_422(self, test_client):
        """Test that fee_rate > 0.01 returns 422"""
        payload = {
            "fee_rate": 0.015,  # 1.5%, exceeds 1% max
        }
        response = test_client.put("/api/backtest/configs", json=payload)
        assert response.status_code == 422

    def test_update_initial_balance_zero_returns_422(self, test_client):
        """Test that initial_balance = 0 returns 422"""
        payload = {
            "initial_balance": 0,
        }
        response = test_client.put("/api/backtest/configs", json=payload)
        assert response.status_code == 422

    def test_update_initial_balance_negative_returns_422(self, test_client):
        """Test that negative initial_balance returns 422"""
        payload = {
            "initial_balance": -1000,
        }
        response = test_client.put("/api/backtest/configs", json=payload)
        assert response.status_code == 422

    def test_update_tp_slippage_rate_negative_returns_422(self, test_client):
        """Test that negative tp_slippage_rate returns 422"""
        payload = {
            "tp_slippage_rate": -0.0001,
        }
        response = test_client.put("/api/backtest/configs", json=payload)
        assert response.status_code == 422

    def test_update_tp_slippage_rate_exceeds_max_returns_422(self, test_client):
        """Test that tp_slippage_rate > 0.01 returns 422"""
        payload = {
            "tp_slippage_rate": 0.02,
        }
        response = test_client.put("/api/backtest/configs", json=payload)
        assert response.status_code == 422

    def test_update_invalid_type_returns_422(self, test_client):
        """Test that invalid type returns 422"""
        payload = {
            "slippage_rate": "not_a_number",
        }
        response = test_client.put("/api/backtest/configs", json=payload)
        assert response.status_code == 422

    def test_update_multiple_invalid_values_returns_all_errors(self, test_client):
        """Test that multiple invalid values return all error messages"""
        payload = {
            "slippage_rate": -0.001,
            "fee_rate": 0.02,
        }
        response = test_client.put("/api/backtest/configs", json=payload)
        assert response.status_code == 422

        data = response.json()
        # Response format: {'error_code': '422', 'message': "{'error': '...', 'errors': [...]}"}
        message = data.get("message", "")
        # Check that error messages contain both validation errors
        assert "slippage_rate" in message or "slippage" in message.lower()
        assert "fee_rate" in message or "fee" in message.lower()


# ============================================================
# Test 4: Edge Cases
# ============================================================
class TestEdgeCases:
    """Test edge cases and boundary values"""

    def test_update_slippage_rate_boundary_zero(self, test_client):
        """Test slippage_rate = 0 is valid (boundary)"""
        payload = {
            "slippage_rate": 0,
        }
        response = test_client.put("/api/backtest/configs", json=payload)
        assert response.status_code == 200

    def test_update_slippage_rate_boundary_max(self, test_client):
        """Test slippage_rate = 0.01 is valid (boundary)"""
        payload = {
            "slippage_rate": 0.01,
        }
        response = test_client.put("/api/backtest/configs", json=payload)
        assert response.status_code == 200

    def test_update_very_small_values(self, test_client):
        """Test very small but valid values"""
        payload = {
            "slippage_rate": 0.00001,
            "fee_rate": 0.00001,
            "tp_slippage_rate": 0.00001,
        }
        response = test_client.put("/api/backtest/configs", json=payload)
        assert response.status_code == 200

    def test_update_large_initial_balance(self, test_client):
        """Test large initial_balance value"""
        payload = {
            "initial_balance": 1000000,  # 1 million
        }
        response = test_client.put("/api/backtest/configs", json=payload)
        assert response.status_code == 200

    def test_update_with_decimal_strings(self, test_client):
        """Test that string numbers are accepted"""
        payload = {
            "slippage_rate": "0.0015",
            "fee_rate": "0.0005",
            "initial_balance": "15000",
        }
        response = test_client.put("/api/backtest/configs", json=payload)
        assert response.status_code == 200

    def test_update_empty_payload_returns_200(self, test_client):
        """Test empty payload (no fields) returns 200"""
        payload = {}
        response = test_client.put("/api/backtest/configs", json=payload)
        assert response.status_code == 200

        data = response.json()
        # Should indicate 0 items updated
        assert "0" in data.get("message", "")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
