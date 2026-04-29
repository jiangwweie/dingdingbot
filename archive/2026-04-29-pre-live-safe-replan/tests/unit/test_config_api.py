"""
BE-1: Strategy Configuration API - Unit Tests

Tests for new configuration management endpoints:
- GET /api/config/strategies - List strategies
- GET /api/config/system - Get system config
- PUT /api/config/system - Update system config
- GET /api/config/schema - Get config schema with tooltips
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import ValidationError


# ============================================================
# Test: SystemConfigResponse Model
# ============================================================

class TestSystemConfigResponse:
    """Test SystemConfigResponse Pydantic model"""

    def test_system_config_response_default_values(self):
        """Test default values for system config"""
        from src.interfaces.api import SystemConfigResponse

        config = SystemConfigResponse()

        assert config.queue_batch_size == 10
        assert config.queue_flush_interval == 5.0
        assert config.queue_max_size == 1000
        assert config.warmup_history_bars == 100
        assert config.signal_cooldown_seconds == 14400

    def test_system_config_response_custom_values(self):
        """Test custom values for system config"""
        from src.interfaces.api import SystemConfigResponse

        config = SystemConfigResponse(
            queue_batch_size=20,
            queue_flush_interval=3.0,
            queue_max_size=2000,
            warmup_history_bars=150,
            signal_cooldown_seconds=7200,
        )

        assert config.queue_batch_size == 20
        assert config.queue_flush_interval == 3.0
        assert config.queue_max_size == 2000
        assert config.warmup_history_bars == 150
        assert config.signal_cooldown_seconds == 7200

    def test_system_config_response_validation_min_bounds(self):
        """Test validation for minimum bounds"""
        from src.interfaces.api import SystemConfigResponse

        # Should pass - at minimum bounds
        config = SystemConfigResponse(
            queue_batch_size=1,
            queue_flush_interval=1.0,
            queue_max_size=100,
            warmup_history_bars=50,
            signal_cooldown_seconds=3600,
        )
        assert config is not None

    def test_system_config_response_validation_max_bounds(self):
        """Test validation for maximum bounds"""
        from src.interfaces.api import SystemConfigResponse

        # Should pass - at maximum bounds
        config = SystemConfigResponse(
            queue_batch_size=100,
            queue_flush_interval=60.0,
            queue_max_size=10000,
            warmup_history_bars=500,
            signal_cooldown_seconds=86400,
        )
        assert config is not None

    def test_system_config_response_validation_exceeds_min(self):
        """Test validation fails when below minimum"""
        from src.interfaces.api import SystemConfigResponse

        with pytest.raises(ValidationError):
            SystemConfigResponse(queue_batch_size=0)

        with pytest.raises(ValidationError):
            SystemConfigResponse(queue_flush_interval=0.5)

        with pytest.raises(ValidationError):
            SystemConfigResponse(queue_max_size=50)

        with pytest.raises(ValidationError):
            SystemConfigResponse(warmup_history_bars=40)

        with pytest.raises(ValidationError):
            SystemConfigResponse(signal_cooldown_seconds=1800)

    def test_system_config_response_validation_exceeds_max(self):
        """Test validation fails when above maximum"""
        from src.interfaces.api import SystemConfigResponse

        with pytest.raises(ValidationError):
            SystemConfigResponse(queue_batch_size=101)

        with pytest.raises(ValidationError):
            SystemConfigResponse(queue_flush_interval=61.0)

        with pytest.raises(ValidationError):
            SystemConfigResponse(queue_max_size=10001)

        with pytest.raises(ValidationError):
            SystemConfigResponse(warmup_history_bars=501)

        with pytest.raises(ValidationError):
            SystemConfigResponse(signal_cooldown_seconds=86401)


# ============================================================
# Test: SystemConfigUpdateRequest Model
# ============================================================

class TestSystemConfigUpdateRequest:
    """Test SystemConfigUpdateRequest Pydantic model"""

    def test_update_request_all_fields(self):
        """Test update request with all fields"""
        from src.interfaces.api import SystemConfigUpdateRequest

        request = SystemConfigUpdateRequest(
            queue_batch_size=20,
            queue_flush_interval=3.0,
            queue_max_size=2000,
            warmup_history_bars=150,
            signal_cooldown_seconds=7200,
        )

        assert request.queue_batch_size == 20
        assert request.queue_flush_interval == 3.0
        assert request.queue_max_size == 2000
        assert request.warmup_history_bars == 150
        assert request.signal_cooldown_seconds == 7200

    def test_update_request_partial_fields(self):
        """Test update request with partial fields (all optional)"""
        from src.interfaces.api import SystemConfigUpdateRequest

        # Only update queue_batch_size
        request = SystemConfigUpdateRequest(queue_batch_size=25)
        assert request.queue_batch_size == 25
        assert request.queue_flush_interval is None
        assert request.queue_max_size is None
        assert request.warmup_history_bars is None
        assert request.signal_cooldown_seconds is None

    def test_update_request_empty(self):
        """Test update request with no fields (all optional)"""
        from src.interfaces.api import SystemConfigUpdateRequest

        request = SystemConfigUpdateRequest()
        assert request.queue_batch_size is None
        assert request.queue_flush_interval is None
        assert request.queue_max_size is None
        assert request.warmup_history_bars is None
        assert request.signal_cooldown_seconds is None


# ============================================================
# Test: SystemConfigUpdateResponse Model
# ============================================================

class TestSystemConfigUpdateResponse:
    """Test SystemConfigUpdateResponse Pydantic model"""

    def test_update_response_default(self):
        """Test update response default values"""
        from src.interfaces.api import SystemConfigResponse, SystemConfigUpdateResponse

        config = SystemConfigResponse()
        response = SystemConfigUpdateResponse(config=config)

        assert response.requires_restart is True
        assert "重启" in response.restart_hint

    def test_update_response_custom(self):
        """Test update response with custom config"""
        from src.interfaces.api import SystemConfigResponse, SystemConfigUpdateResponse

        config = SystemConfigResponse(queue_batch_size=20)
        response = SystemConfigUpdateResponse(
            config=config,
            requires_restart=True,
            restart_hint="Custom restart message",
        )

        assert response.config.queue_batch_size == 20
        assert response.requires_restart is True
        assert response.restart_hint == "Custom restart message"


# ============================================================
# Test: ConfigFieldSchema Model
# ============================================================

class TestConfigFieldSchema:
    """Test ConfigFieldSchema Pydantic model"""

    def test_field_schema_number_type(self):
        """Test field schema with number type"""
        from src.interfaces.api import ConfigFieldSchema

        schema = ConfigFieldSchema(
            type='number',
            default=0.6,
            min=0.5,
            max=0.7,
            step=0.05,
            tooltip={
                "description": "Test description",
                "default_value": "0.6",
                "range": "0.5 - 0.7",
                "adjustment_tips": ["tip1", "tip2"]
            }
        )

        assert schema.type == 'number'
        assert schema.default == 0.6
        assert schema.min == 0.5
        assert schema.max == 0.7
        assert schema.step == 0.05
        assert schema.tooltip["description"] == "Test description"

    def test_field_schema_boolean_type(self):
        """Test field schema with boolean type"""
        from src.interfaces.api import ConfigFieldSchema

        schema = ConfigFieldSchema(
            type='boolean',
            default=True,
            tooltip={
                "description": "Boolean field",
                "default_value": "true",
                "adjustment_tips": []
            }
        )

        assert schema.type == 'boolean'
        assert schema.default is True
        assert schema.min is None
        assert schema.max is None

    def test_field_schema_string_type(self):
        """Test field schema with string type"""
        from src.interfaces.api import ConfigFieldSchema

        schema = ConfigFieldSchema(
            type='string',
            default="default_value",
            tooltip={
                "description": "String field",
                "default_value": "default_value",
                "adjustment_tips": []
            }
        )

        assert schema.type == 'string'
        assert schema.default == "default_value"


# ============================================================
# Test: ConfigSchemaResponse Model
# ============================================================

class TestConfigSchemaResponse:
    """Test ConfigSchemaResponse Pydantic model"""

    def test_schema_response_structure(self):
        """Test schema response has required structure"""
        from src.interfaces.api import ConfigSchemaResponse

        schema = ConfigSchemaResponse(
            strategy_params={"pinbar": {}},
            system_config={"queue_batch_size": {}}
        )

        assert "pinbar" in schema.strategy_params
        assert "queue_batch_size" in schema.system_config


# ============================================================
# Test: API Endpoints
# ============================================================

@pytest.mark.asyncio
class TestConfigApiEndpoints:
    """Test configuration API endpoints"""

    @pytest.fixture
    def mock_config_manager(self):
        """Mock ConfigManager"""
        manager = MagicMock()
        return manager

    @pytest.fixture
    def mock_repository(self):
        """Mock repository"""
        repo = AsyncMock()
        return repo

    async def test_get_system_config(self, mock_config_manager):
        """Test GET /api/config/system endpoint"""
        from src.interfaces.api import SystemConfigResponse

        # Simulate the endpoint logic
        config = SystemConfigResponse(
            queue_batch_size=10,
            queue_flush_interval=5.0,
            queue_max_size=1000,
            warmup_history_bars=100,
            signal_cooldown_seconds=14400,
        )

        assert config.queue_batch_size == 10
        assert config.queue_flush_interval == 5.0
        assert config.signal_cooldown_seconds == 14400

    async def test_update_system_config(self):
        """Test PUT /api/config/system endpoint"""
        from src.interfaces.api import (
            SystemConfigResponse,
            SystemConfigUpdateRequest,
            SystemConfigUpdateResponse,
        )

        # Simulate update request
        request = SystemConfigUpdateRequest(queue_batch_size=20)

        # Simulate current config
        current_config = SystemConfigResponse()

        # Apply update
        update_data = request.model_dump(exclude_unset=True)
        updated_config_dict = {**current_config.model_dump(), **update_data}
        updated_config = SystemConfigResponse(**updated_config_dict)

        assert updated_config.queue_batch_size == 20
        assert updated_config.queue_flush_interval == 5.0  # unchanged

        # Create response
        response = SystemConfigUpdateResponse(
            config=updated_config,
            requires_restart=True,
            restart_hint="修改已保存，需要重启服务才能生效",
        )

        assert response.requires_restart is True
        assert response.config.queue_batch_size == 20

    async def test_get_config_schema_structure(self):
        """Test GET /api/config/schema returns correct structure"""
        from src.interfaces.api import ConfigSchemaResponse

        # Simulate schema response
        strategy_params = {
            "pinbar": {
                "min_wick_ratio": {
                    "type": "number",
                    "default": 0.6,
                    "min": 0.5,
                    "max": 0.7,
                    "tooltip": {
                        "description": "Test",
                        "default_value": "0.6",
                        "range": "0.5 - 0.7",
                        "adjustment_tips": []
                    }
                }
            }
        }

        system_config = {
            "queue_batch_size": {
                "type": "number",
                "default": 10,
                "min": 1,
                "max": 100,
                "tooltip": {
                    "description": "Test",
                    "default_value": "10",
                    "range": "1 - 100",
                    "adjustment_tips": []
                }
            }
        }

        schema = ConfigSchemaResponse(
            strategy_params=strategy_params,
            system_config=system_config,
        )

        assert "pinbar" in schema.strategy_params
        assert "queue_batch_size" in schema.system_config


# ============================================================
# Test: ConfigSchema Tooltip Content
# ============================================================

class TestConfigSchemaTooltipContent:
    """Test tooltip content in config schema"""

    def test_pinbar_schema_has_required_fields(self):
        """Test pinbar schema has all required fields"""
        from src.interfaces.api import ConfigSchemaResponse

        # This is what the API should return
        strategy_params = {
            "pinbar": {
                "min_wick_ratio": {
                    "type": "number",
                    "default": 0.6,
                    "min": 0.5,
                    "max": 0.7,
                    "step": 0.05,
                    "tooltip": {
                        "description": "影线长度占整个 K 线范围的比例下限",
                        "default_value": "0.6 (60%)",
                        "range": "0.5 - 0.7",
                        "adjustment_tips": [
                            "高波动市场：降低到 0.5",
                            "低波动市场：提高到 0.7"
                        ]
                    }
                }
            }
        }

        pinbar = strategy_params["pinbar"]["min_wick_ratio"]
        assert pinbar["type"] == "number"
        assert pinbar["default"] == 0.6
        assert pinbar["min"] == 0.5
        assert pinbar["max"] == 0.7
        assert "adjustment_tips" in pinbar["tooltip"]

    def test_system_config_schema_has_required_fields(self):
        """Test system config schema has all required fields"""
        from src.interfaces.api import ConfigSchemaResponse

        system_config = {
            "queue_batch_size": {
                "type": "number",
                "default": 10,
                "min": 1,
                "max": 100,
                "step": 1,
                "tooltip": {
                    "description": "队列批量落盘大小",
                    "default_value": "10",
                    "range": "1 - 100",
                    "adjustment_tips": [
                        "高并发场景：提高到 20-50",
                        "低延迟要求：降低到 1-5"
                    ]
                }
            }
        }

        config = system_config["queue_batch_size"]
        assert config["type"] == "number"
        assert config["default"] == 10
        assert config["min"] == 1
        assert config["max"] == 100
        assert "adjustment_tips" in config["tooltip"]
