"""
System Config API v1 - Unit Tests

Tests for system configuration endpoints:
- GET /api/v1/config/system - Get system config (nested format)
- PUT /api/v1/config/system - Update system config (nested format)
- Admin permission bypass (DISABLE_AUTH)
- Flat-to-nested and nested-to-flat conversion helpers
"""
import os
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch


# ============================================================
# Test: Nested Pydantic Models
# ============================================================

class TestEmaConfig:
    """Test EmaConfig nested model"""

    def test_default_values(self):
        from src.interfaces.api_v1_config import EmaConfig
        config = EmaConfig()
        assert config.period == 60

    def test_custom_value(self):
        from src.interfaces.api_v1_config import EmaConfig
        config = EmaConfig(period=120)
        assert config.period == 120

    def test_validation_below_min(self):
        from src.interfaces.api_v1_config import EmaConfig
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            EmaConfig(period=4)

    def test_validation_above_max(self):
        from src.interfaces.api_v1_config import EmaConfig
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            EmaConfig(period=201)


class TestQueueConfig:
    """Test QueueConfig nested model"""

    def test_default_values(self):
        from src.interfaces.api_v1_config import QueueConfig
        config = QueueConfig()
        assert config.batch_size == 10
        assert config.flush_interval == 5.0
        assert config.max_queue_size == 1000

    def test_custom_values(self):
        from src.interfaces.api_v1_config import QueueConfig
        config = QueueConfig(batch_size=20, flush_interval=3.0, max_queue_size=2000)
        assert config.batch_size == 20
        assert config.flush_interval == 3.0
        assert config.max_queue_size == 2000

    def test_validation_batch_size_min(self):
        from src.interfaces.api_v1_config import QueueConfig
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            QueueConfig(batch_size=0)

    def test_validation_flush_interval_min(self):
        from src.interfaces.api_v1_config import QueueConfig
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            QueueConfig(flush_interval=0.05)


class TestSignalPipelineConfig:
    """Test SignalPipelineConfig nested model"""

    def test_default_values(self):
        from src.interfaces.api_v1_config import SignalPipelineConfig
        config = SignalPipelineConfig()
        assert config.cooldown_seconds == 14400
        assert config.queue.batch_size == 10
        assert config.queue.flush_interval == 5.0
        assert config.queue.max_queue_size == 1000

    def test_custom_values(self):
        from src.interfaces.api_v1_config import SignalPipelineConfig, QueueConfig
        config = SignalPipelineConfig(
            cooldown_seconds=7200,
            queue=QueueConfig(batch_size=25, flush_interval=2.0, max_queue_size=5000),
        )
        assert config.cooldown_seconds == 7200
        assert config.queue.batch_size == 25


class TestWarmupConfig:
    """Test WarmupConfig nested model"""

    def test_default_values(self):
        from src.interfaces.api_v1_config import WarmupConfig
        config = WarmupConfig()
        assert config.history_bars == 100

    def test_custom_values(self):
        from src.interfaces.api_v1_config import WarmupConfig
        config = WarmupConfig(history_bars=200)
        assert config.history_bars == 200


class TestSystemConfigResponseNested:
    """Test SystemConfigResponse with nested format"""

    def test_default_values(self):
        from src.interfaces.api_v1_config import SystemConfigResponse
        config = SystemConfigResponse()
        assert config.id == "global"
        assert config.ema.period == 60
        assert config.mtf_ema_period == 60
        assert config.signal_pipeline.cooldown_seconds == 14400
        assert config.signal_pipeline.queue.batch_size == 10
        assert config.signal_pipeline.queue.flush_interval == 5.0
        assert config.signal_pipeline.queue.max_queue_size == 1000
        assert config.warmup.history_bars == 100
        assert config.atr_filter_enabled is True
        assert config.atr_period == 14
        assert config.atr_min_ratio == 0.5
        assert config.restart_required is False
        assert config.updated_at != ""

    def test_nested_structure(self):
        from src.interfaces.api_v1_config import (
            SystemConfigResponse, EmaConfig, SignalPipelineConfig,
            QueueConfig, WarmupConfig,
        )
        config = SystemConfigResponse(
            ema=EmaConfig(period=120),
            mtf_ema_period=120,
            signal_pipeline=SignalPipelineConfig(
                cooldown_seconds=7200,
                queue=QueueConfig(batch_size=20, flush_interval=3.0, max_queue_size=2000),
            ),
            warmup=WarmupConfig(history_bars=200),
            atr_filter_enabled=False,
            atr_period=10,
            atr_min_ratio=0.3,
        )
        assert config.ema.period == 120
        assert config.signal_pipeline.queue.batch_size == 20
        assert config.warmup.history_bars == 200
        assert config.atr_filter_enabled is False

    def test_json_serialization(self):
        from src.interfaces.api_v1_config import SystemConfigResponse
        config = SystemConfigResponse()
        data = config.model_dump()
        assert "ema" in data
        assert data["ema"]["period"] == 60
        assert "signal_pipeline" in data
        assert data["signal_pipeline"]["cooldown_seconds"] == 14400
        assert "warmup" in data
        assert data["warmup"]["history_bars"] == 100


class TestSystemConfigUpdateRequestNested:
    """Test SystemConfigUpdateRequest with nested format"""

    def test_empty_request(self):
        from src.interfaces.api_v1_config import SystemConfigUpdateRequest
        request = SystemConfigUpdateRequest()
        assert request.ema is None
        assert request.signal_pipeline is None
        assert request.warmup is None
        assert request.atr_filter_enabled is None

    def test_full_nested_request(self):
        from src.interfaces.api_v1_config import (
            SystemConfigUpdateRequest, EmaConfig, SignalPipelineConfig,
            QueueConfig, WarmupConfig,
        )
        request = SystemConfigUpdateRequest(
            ema=EmaConfig(period=120),
            mtf_ema_period=120,
            signal_pipeline=SignalPipelineConfig(
                cooldown_seconds=7200,
                queue=QueueConfig(batch_size=20, flush_interval=3.0, max_queue_size=2000),
            ),
            warmup=WarmupConfig(history_bars=200),
            atr_filter_enabled=False,
            atr_period=10,
            atr_min_ratio=0.3,
        )
        assert request.ema.period == 120
        assert request.signal_pipeline.queue.batch_size == 20
        assert request.warmup.history_bars == 200

    def test_partial_update(self):
        from src.interfaces.api_v1_config import SystemConfigUpdateRequest, EmaConfig
        # Only update EMA period
        request = SystemConfigUpdateRequest(ema=EmaConfig(period=90))
        assert request.ema.period == 90
        assert request.signal_pipeline is None
        assert request.warmup is None

    def test_json_serialization(self):
        from src.interfaces.api_v1_config import (
            SystemConfigUpdateRequest, EmaConfig, SignalPipelineConfig,
            QueueConfig,
        )
        request = SystemConfigUpdateRequest(
            ema=EmaConfig(period=90),
            signal_pipeline=SignalPipelineConfig(
                cooldown_seconds=18000,
                queue=QueueConfig(batch_size=15),
            ),
        )
        data = request.model_dump(mode='json', exclude_unset=True)
        assert data["ema"]["period"] == 90
        assert data["signal_pipeline"]["cooldown_seconds"] == 18000
        assert data["signal_pipeline"]["queue"]["batch_size"] == 15


# ============================================================
# Test: Flat-to-Nested and Nested-to-Flat Conversion
# ============================================================

class TestFlatToNested:
    """Test _flat_to_nested helper function"""

    def test_full_conversion(self):
        from src.interfaces.api_v1_config import _flat_to_nested
        flat_data = {
            "id": "global",
            "ema_period": 120,
            "mtf_ema_period": 120,
            "signal_cooldown_seconds": 7200,
            "queue_batch_size": 20,
            "queue_flush_interval": Decimal("3.0"),
            "queue_max_size": 2000,
            "warmup_history_bars": 200,
            "atr_filter_enabled": False,
            "atr_period": 10,
            "atr_min_ratio": Decimal("0.3"),
            "restart_required": True,
            "updated_at": "2026-04-10T12:00:00Z",
        }
        nested = _flat_to_nested(flat_data)
        assert nested.id == "global"
        assert nested.ema.period == 120
        assert nested.mtf_ema_period == 120
        assert nested.signal_pipeline.cooldown_seconds == 7200
        assert nested.signal_pipeline.queue.batch_size == 20
        assert nested.signal_pipeline.queue.flush_interval == 3.0
        assert nested.signal_pipeline.queue.max_queue_size == 2000
        assert nested.warmup.history_bars == 200
        assert nested.atr_filter_enabled is False
        assert nested.atr_period == 10
        assert nested.atr_min_ratio == 0.3
        assert nested.restart_required is True
        assert nested.updated_at == "2026-04-10T12:00:00Z"

    def test_partial_data_uses_defaults(self):
        from src.interfaces.api_v1_config import _flat_to_nested
        flat_data = {
            "id": "global",
            "ema_period": 90,
            "updated_at": "2026-04-10T12:00:00Z",
        }
        nested = _flat_to_nested(flat_data)
        assert nested.ema.period == 90
        # Defaults should be used for missing fields
        assert nested.signal_pipeline.cooldown_seconds == 14400
        assert nested.warmup.history_bars == 100


class TestNestedToFlat:
    """Test _nested_to_flat helper function"""

    def test_full_conversion(self):
        from src.interfaces.api_v1_config import (
            _nested_to_flat, EmaConfig, SignalPipelineConfig,
            QueueConfig, WarmupConfig,
        )
        nested = {
            "ema": {"period": 120},
            "mtf_ema_period": 120,
            "signal_pipeline": {
                "cooldown_seconds": 7200,
                "queue": {
                    "batch_size": 20,
                    "flush_interval": 3.0,
                    "max_queue_size": 2000,
                },
            },
            "warmup": {"history_bars": 200},
            "atr_filter_enabled": False,
            "atr_period": 10,
            "atr_min_ratio": 0.3,
        }
        flat = _nested_to_flat(nested)
        assert flat["ema_period"] == 120
        assert flat["mtf_ema_period"] == 120
        assert flat["signal_cooldown_seconds"] == 7200
        assert flat["queue_batch_size"] == 20
        assert flat["queue_flush_interval"] == Decimal("3.0")
        assert flat["queue_max_size"] == 2000
        assert flat["warmup_history_bars"] == 200
        assert flat["atr_filter_enabled"] is False
        assert flat["atr_period"] == 10
        assert flat["atr_min_ratio"] == Decimal("0.3")

    def test_partial_conversion(self):
        from src.interfaces.api_v1_config import _nested_to_flat
        nested = {
            "ema": {"period": 90},
            "warmup": {"history_bars": 150},
        }
        flat = _nested_to_flat(nested)
        assert flat["ema_period"] == 90
        assert flat["warmup_history_bars"] == 150
        assert "signal_cooldown_seconds" not in flat
        assert "queue_batch_size" not in flat

    def test_empty_conversion(self):
        from src.interfaces.api_v1_config import _nested_to_flat
        flat = _nested_to_flat({})
        assert flat == {}

    def test_with_pydantic_objects(self):
        from src.interfaces.api_v1_config import (
            _nested_to_flat, EmaConfig, SignalPipelineConfig,
            QueueConfig, WarmupConfig,
        )
        nested = {
            "ema": EmaConfig(period=100),
            "signal_pipeline": SignalPipelineConfig(
                cooldown_seconds=10000,
                queue=QueueConfig(batch_size=15, flush_interval=4.0, max_queue_size=1500),
            ),
            "warmup": WarmupConfig(history_bars=180),
        }
        flat = _nested_to_flat(nested)
        assert flat["ema_period"] == 100
        assert flat["signal_cooldown_seconds"] == 10000
        assert flat["queue_batch_size"] == 15
        assert flat["warmup_history_bars"] == 180


# ============================================================
# Test: Admin Permission Bypass
# ============================================================

class TestAdminPermissionBypass:
    """Test check_admin_permission with DISABLE_AUTH bypass"""

    @pytest.mark.asyncio
    async def test_bypass_when_disabled_auth(self):
        """Admin check passes when DISABLE_AUTH=true"""
        from src.interfaces.api_v1_config import check_admin_permission
        mock_request = MagicMock()
        mock_request.headers = {}

        with patch.dict(os.environ, {"DISABLE_AUTH": "true"}):
            result = await check_admin_permission(mock_request)
            assert result is True

    @pytest.mark.asyncio
    async def test_bypass_when_disabled_auth_uppercase(self):
        """Admin check passes when DISABLE_AUTH=TRUE (case insensitive)"""
        from src.interfaces.api_v1_config import check_admin_permission
        mock_request = MagicMock()
        mock_request.headers = {}

        with patch.dict(os.environ, {"DISABLE_AUTH": "TRUE"}):
            result = await check_admin_permission(mock_request)
            assert result is True

    @pytest.mark.asyncio
    async def test_bypass_when_disabled_auth_numeric(self):
        """Admin check passes when DISABLE_AUTH=1"""
        from src.interfaces.api_v1_config import check_admin_permission
        mock_request = MagicMock()
        mock_request.headers = {}

        with patch.dict(os.environ, {"DISABLE_AUTH": "1"}):
            result = await check_admin_permission(mock_request)
            assert result is True

    @pytest.mark.asyncio
    async def test_admin_header_still_works(self):
        """Admin header works regardless of DISABLE_AUTH"""
        from src.interfaces.api_v1_config import check_admin_permission
        mock_request = MagicMock()
        mock_request.headers = {"X-User-Role": "admin"}

        with patch.dict(os.environ, {}, clear=False):
            # Ensure DISABLE_AUTH is not set
            os.environ.pop("DISABLE_AUTH", None)
            result = await check_admin_permission(mock_request)
            assert result is True

    @pytest.mark.asyncio
    async def test_rejects_non_admin(self):
        """Non-admin role is rejected"""
        from src.interfaces.api_v1_config import check_admin_permission
        from fastapi import HTTPException
        mock_request = MagicMock()
        mock_request.headers = {"X-User-Role": "user"}

        os.environ.pop("DISABLE_AUTH", None)

        with pytest.raises(HTTPException) as exc_info:
            await check_admin_permission(mock_request)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_rejects_no_header(self):
        """Missing header is rejected"""
        from src.interfaces.api_v1_config import check_admin_permission
        from fastapi import HTTPException
        mock_request = MagicMock()
        mock_request.headers = {}

        os.environ.pop("DISABLE_AUTH", None)

        with pytest.raises(HTTPException) as exc_info:
            await check_admin_permission(mock_request)
        assert exc_info.value.status_code == 401


# ============================================================
# Test: GET /system endpoint
# ============================================================

class TestGetSystemConfig:
    """Test GET /api/v1/config/system endpoint"""

    @pytest.mark.asyncio
    async def test_returns_nested_format(self):
        """GET /system returns nested format matching frontend"""
        from src.interfaces.api_v1_config import (
            get_system_config, _system_repo, _flat_to_nested,
        )
        mock_repo = AsyncMock()
        mock_repo.get_global.return_value = {
            "id": "global",
            "ema_period": 120,
            "mtf_ema_period": 120,
            "signal_cooldown_seconds": 7200,
            "queue_batch_size": 20,
            "queue_flush_interval": Decimal("3.0"),
            "queue_max_size": 2000,
            "warmup_history_bars": 200,
            "atr_filter_enabled": False,
            "atr_period": 10,
            "atr_min_ratio": Decimal("0.3"),
            "restart_required": False,
            "updated_at": "2026-04-10T12:00:00Z",
        }

        with patch("src.interfaces.api_v1_config._system_repo", mock_repo):
            result = await get_system_config()

        assert result.ema.period == 120
        assert result.signal_pipeline.cooldown_seconds == 7200
        assert result.signal_pipeline.queue.batch_size == 20
        assert result.warmup.history_bars == 200
        assert result.atr_filter_enabled is False

    @pytest.mark.asyncio
    async def test_returns_default_when_no_data(self):
        """GET /system returns defaults when repo returns None"""
        from src.interfaces.api_v1_config import get_system_config

        mock_repo = AsyncMock()
        mock_repo.get_global.return_value = None

        with patch("src.interfaces.api_v1_config._system_repo", mock_repo):
            result = await get_system_config()

        assert result.ema.period == 60
        assert result.signal_pipeline.cooldown_seconds == 14400
        assert result.warmup.history_bars == 100

    @pytest.mark.asyncio
    async def test_returns_503_when_repo_not_initialized(self):
        """GET /system returns 503 when repo not initialized"""
        from src.interfaces.api_v1_config import get_system_config
        from fastapi import HTTPException

        with patch("src.interfaces.api_v1_config._system_repo", None):
            with pytest.raises(HTTPException) as exc_info:
                await get_system_config()
            assert exc_info.value.status_code == 503


# ============================================================
# Test: PUT /system endpoint
# ============================================================

class TestUpdateSystemConfig:
    """Test PUT /api/v1/config/system endpoint"""

    @pytest.mark.asyncio
    async def test_updates_with_nested_format(self):
        """PUT /system accepts nested format and converts to flat for DB"""
        from src.interfaces.api_v1_config import (
            update_system_config, SystemConfigUpdateRequest,
            EmaConfig, SignalPipelineConfig, QueueConfig, WarmupConfig,
        )

        mock_request = SystemConfigUpdateRequest(
            ema=EmaConfig(period=120),
            signal_pipeline=SignalPipelineConfig(
                cooldown_seconds=7200,
                queue=QueueConfig(batch_size=20, flush_interval=3.0, max_queue_size=2000),
            ),
            warmup=WarmupConfig(history_bars=200),
        )
        mock_admin = True

        mock_repo = AsyncMock()
        mock_repo.update.return_value = True
        mock_repo.get_global.return_value = {
            "id": "global",
            "ema_period": 120,
            "mtf_ema_period": 60,
            "signal_cooldown_seconds": 7200,
            "queue_batch_size": 20,
            "queue_flush_interval": Decimal("3.0"),
            "queue_max_size": 2000,
            "warmup_history_bars": 200,
            "atr_filter_enabled": True,
            "atr_period": 14,
            "atr_min_ratio": Decimal("0.5"),
            "restart_required": True,
            "updated_at": "2026-04-10T12:00:00Z",
        }

        mock_history = AsyncMock()
        mock_hot_reload = AsyncMock()

        with patch("src.interfaces.api_v1_config._system_repo", mock_repo), \
             patch("src.interfaces.api_v1_config._history_repo", mock_history), \
             patch("src.interfaces.api_v1_config.notify_hot_reload", mock_hot_reload):
            result = await update_system_config(mock_request, mock_admin)

        # Verify repo received flat format
        mock_repo.update.assert_called_once()
        call_args = mock_repo.update.call_args
        flat_data = call_args[0][0]
        assert flat_data["ema_period"] == 120
        assert flat_data["signal_cooldown_seconds"] == 7200
        assert flat_data["queue_batch_size"] == 20
        assert flat_data["warmup_history_bars"] == 200

        # Verify restart flag passed
        assert call_args[1]["restart_required"] is True

        # Verify result is nested format
        assert result.ema.period == 120
        assert result.signal_pipeline.cooldown_seconds == 7200

        # Verify hot-reload notification was sent
        mock_hot_reload.assert_called_once_with("system")

        # Verify history was recorded
        mock_history.record_change.assert_called_once()

    @pytest.mark.asyncio
    async def test_rejects_empty_update(self):
        """PUT /system rejects empty update"""
        from src.interfaces.api_v1_config import (
            update_system_config, SystemConfigUpdateRequest,
        )
        from fastapi import HTTPException

        mock_request = SystemConfigUpdateRequest()
        mock_admin = True
        mock_repo = AsyncMock()

        with patch("src.interfaces.api_v1_config._system_repo", mock_repo):
            with pytest.raises(HTTPException) as exc_info:
                await update_system_config(mock_request, mock_admin)
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_partial_update(self):
        """PUT /system handles partial update (only EMA period)"""
        from src.interfaces.api_v1_config import (
            update_system_config, SystemConfigUpdateRequest, EmaConfig,
        )

        mock_request = SystemConfigUpdateRequest(ema=EmaConfig(period=90))
        mock_admin = True

        mock_repo = AsyncMock()
        mock_repo.update.return_value = True
        mock_repo.get_global.return_value = {
            "id": "global",
            "ema_period": 90,
            "mtf_ema_period": 60,
            "signal_cooldown_seconds": 14400,
            "queue_batch_size": 10,
            "queue_flush_interval": Decimal("5.0"),
            "queue_max_size": 1000,
            "warmup_history_bars": 100,
            "atr_filter_enabled": True,
            "atr_period": 14,
            "atr_min_ratio": Decimal("0.5"),
            "restart_required": True,
            "updated_at": "2026-04-10T12:00:00Z",
        }

        with patch("src.interfaces.api_v1_config._system_repo", mock_repo), \
             patch("src.interfaces.api_v1_config._history_repo", None), \
             patch("src.interfaces.api_v1_config.notify_hot_reload", AsyncMock()):
            result = await update_system_config(mock_request, mock_admin)

        # Verify only ema_period was sent to DB
        call_args = mock_repo.update.call_args
        flat_data = call_args[0][0]
        assert "ema_period" in flat_data
        assert flat_data["ema_period"] == 90
        assert "queue_batch_size" not in flat_data

        assert result.ema.period == 90

    @pytest.mark.asyncio
    async def test_returns_503_when_repo_not_initialized(self):
        """PUT /system returns 503 when repo not initialized"""
        from src.interfaces.api_v1_config import (
            update_system_config, SystemConfigUpdateRequest, EmaConfig,
        )
        from fastapi import HTTPException

        mock_request = SystemConfigUpdateRequest(ema=EmaConfig(period=90))
        mock_admin = True

        with patch("src.interfaces.api_v1_config._system_repo", None):
            with pytest.raises(HTTPException) as exc_info:
                await update_system_config(mock_request, mock_admin)
            assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_returns_500_when_update_fails(self):
        """PUT /system returns 500 when repo update fails"""
        from src.interfaces.api_v1_config import (
            update_system_config, SystemConfigUpdateRequest, EmaConfig,
        )
        from fastapi import HTTPException

        mock_request = SystemConfigUpdateRequest(ema=EmaConfig(period=90))
        mock_admin = True

        mock_repo = AsyncMock()
        mock_repo.update.return_value = False

        with patch("src.interfaces.api_v1_config._system_repo", mock_repo):
            with pytest.raises(HTTPException) as exc_info:
                await update_system_config(mock_request, mock_admin)
            assert exc_info.value.status_code == 500
