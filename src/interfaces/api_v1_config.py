"""
Configuration Management API v1

Implements RESTful endpoints for configuration management as specified in ADR-2026-004-001.

Endpoints:
    GET     /api/v1/config                        - Get all config summary
    GET     /api/v1/config/risk                   - Get risk config
    PUT     /api/v1/config/risk                   - Update risk config (hot-reload)
    GET     /api/v1/config/system                 - Get system config
    PUT     /api/v1/config/system                 - Update system config (restart required)
    GET     /api/v1/config/strategies             - Get strategy list
    POST    /api/v1/config/strategies             - Create strategy
    GET     /api/v1/config/strategies/{id}        - Get strategy details
    PUT     /api/v1/config/strategies/{id}        - Update strategy (hot-reload)
    DELETE  /api/v1/config/strategies/{id}        - Delete strategy
    POST    /api/v1/config/strategies/{id}/toggle - Toggle strategy
    GET     /api/v1/config/symbols                - Get symbol pool list
    POST    /api/v1/config/symbols                - Add symbol
    PUT     /api/v1/config/symbols/{symbol}       - Update symbol (hot-reload)
    POST    /api/v1/config/symbols/{symbol}/toggle- Toggle symbol
    DELETE  /api/v1/config/symbols/{symbol}       - Delete symbol
    GET     /api/v1/config/notifications          - Get notification channels
    POST    /api/v1/config/notifications          - Add notification channel
    PUT     /api/v1/config/notifications/{id}     - Update notification channel
    DELETE  /api/v1/config/notifications/{id}     - Delete notification channel
    POST    /api/v1/config/notifications/{id}/test- Test notification channel
    POST    /api/v1/config/export                 - Export YAML
    POST    /api/v1/config/import/preview         - Preview import (safe)
    POST    /api/v1/config/import/confirm         - Confirm import
    GET     /api/v1/config/snapshots              - Get snapshots list
    POST    /api/v1/config/snapshots              - Create snapshot
    GET     /api/v1/config/snapshots/{id}         - Get snapshot details
    POST    /api/v1/config/snapshots/{id}/activate- Rollback to snapshot
    DELETE  /api/v1/config/snapshots/{id}         - Delete snapshot
    GET     /api/v1/config/history                - Get history list with pagination
    GET     /api/v1/config/history/{id}           - Get history detail
    GET     /api/v1/config/history/entity/{type}/{id} - Get entity history
    GET     /api/v1/config/history/rollback-candidates - Get rollback candidates
    POST    /api/v1/config/history/rollback       - Rollback to specific version
"""
import json
import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any, Literal

import yaml
import cachetools
from fastapi import APIRouter, Depends, HTTPException, Body, Query, Request
from pydantic import BaseModel, Field, field_validator, model_validator

from src.infrastructure.logger import mask_secret


def _decimal_representer(dumper, data):
    """Represent Decimal as string to preserve precision during YAML serialization."""
    return dumper.represent_scalar('tag:yaml.org,2002:str', str(data))


def _decimal_constructor(loader, node):
    """Construct Decimal from string during YAML deserialization."""
    value = loader.construct_scalar(node)
    return Decimal(value)


# Register Decimal representer and constructor for YAML
# Use custom !decimal tag to avoid hijacking all YAML string parsing.
# Only values explicitly marked as !decimal in YAML will be converted to Decimal.
yaml.add_representer(Decimal, _decimal_representer)
yaml.add_constructor('!decimal', _decimal_constructor)
# Also register on SafeLoader for safe_dump/safe_load compatibility
yaml.add_representer(Decimal, _decimal_representer, Dumper=yaml.SafeDumper)
yaml.add_constructor('!decimal', _decimal_constructor, Loader=yaml.SafeLoader)


def _convert_decimals_to_str(obj: Any) -> Any:
    """
    Recursively convert all Decimal values in a dict/list to string for JSON/YAML serialization.
    This preserves full precision without float conversion errors.
    """
    if isinstance(obj, Decimal):
        return str(obj)
    elif isinstance(obj, dict):
        return {k: _convert_decimals_to_str(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_decimals_to_str(item) for item in obj]
    return obj

from src.infrastructure.repositories.config_repositories import (
    StrategyConfigRepository,
    RiskConfigRepository,
    SystemConfigRepository,
    SymbolConfigRepository,
    NotificationConfigRepository,
    ConfigHistoryRepository,
    ConfigSnapshotRepositoryExtended,
    ConfigNotFoundError,
    ConfigConflictError,
    ConfigValidationError,
)
from src.domain.exceptions import CryptoMonitorError

logger = logging.getLogger(__name__)


class ConfigImportError(CryptoMonitorError):
    """Configuration import failed"""
    pass

# ============================================================
# Shared config globals (single source of truth with api.py)
# ============================================================
from src.interfaces import api_config_globals as _cg


# ============================================================
# Pydantic Models - Risk Config
# ============================================================
class RiskConfigResponse(BaseModel):
    """Risk configuration response"""
    id: str
    max_loss_percent: Decimal
    max_leverage: int
    max_total_exposure: Optional[Decimal] = None
    daily_max_trades: Optional[int] = None
    daily_max_loss: Optional[Decimal] = None
    max_position_hold_time: Optional[int] = None
    cooldown_minutes: int
    updated_at: str
    version: int


class RiskConfigUpdateRequest(BaseModel):
    """Risk configuration update request"""
    max_loss_percent: Optional[Decimal] = Field(None, ge=Decimal("0"), le=Decimal("1"))
    max_leverage: Optional[int] = Field(None, ge=1, le=125)
    max_total_exposure: Optional[Decimal] = Field(None, ge=Decimal("0"), le=Decimal("1"))
    daily_max_trades: Optional[int] = Field(None, ge=1)
    daily_max_loss: Optional[Decimal] = Field(None, ge=Decimal("0"))
    max_position_hold_time: Optional[int] = Field(None, ge=1)
    cooldown_minutes: Optional[int] = Field(None, ge=0)


# ============================================================
# Pydantic Models - System Config
# ============================================================

# Nested sub-models matching frontend SystemConfigResponse format
class EmaConfig(BaseModel):
    """EMA configuration nested model"""
    period: int = Field(default=60, ge=5, le=200)


class QueueConfig(BaseModel):
    """Queue configuration nested model"""
    batch_size: int = Field(default=10, ge=1, le=100)
    flush_interval: float = Field(default=5.0, ge=0.1, le=60.0)
    max_queue_size: int = Field(default=1000, ge=100, le=10000)


class SignalPipelineConfig(BaseModel):
    """Signal pipeline configuration nested model"""
    cooldown_seconds: int = Field(default=14400, ge=3600, le=86400)
    queue: QueueConfig = Field(default_factory=QueueConfig)


class WarmupConfig(BaseModel):
    """Warmup configuration nested model"""
    history_bars: int = Field(default=100, ge=50, le=500)


class SystemConfigResponse(BaseModel):
    """System configuration response - matches frontend SystemConfigResponse format"""
    # Core identity (backend internal)
    id: str = "global"
    updated_at: str = ""

    # EMA config (nested to match frontend)
    ema: EmaConfig = Field(default_factory=EmaConfig)
    mtf_ema_period: int = Field(default=60, ge=5, le=200)

    # Signal pipeline (nested to match frontend)
    signal_pipeline: SignalPipelineConfig = Field(default_factory=SignalPipelineConfig)

    # Warmup (nested to match frontend)
    warmup: WarmupConfig = Field(default_factory=WarmupConfig)

    # ATR filter
    atr_filter_enabled: bool = True
    atr_period: int = Field(default=14, ge=5, le=50)
    atr_min_ratio: float = Field(default=0.5, ge=0.0)

    # Restart flag
    restart_required: bool = False

    def model_post_init(self, __context):
        """Set default updated_at if not provided"""
        if not self.updated_at:
            self.updated_at = datetime.now(timezone.utc).isoformat()


class SystemConfigUpdateRequest(BaseModel):
    """System configuration update request - matches frontend SystemConfigUpdateRequest format"""
    ema: Optional[EmaConfig] = None
    mtf_ema_period: Optional[int] = Field(None, ge=5, le=200)
    signal_pipeline: Optional[SignalPipelineConfig] = None
    warmup: Optional[WarmupConfig] = None
    atr_filter_enabled: Optional[bool] = None
    atr_period: Optional[int] = Field(None, ge=5, le=50)
    atr_min_ratio: Optional[float] = Field(None, ge=0.0)


# ============================================================
# Pydantic Models - Strategy Config
# ============================================================
class StrategyListItem(BaseModel):
    """Strategy list item"""
    id: str
    name: str
    description: Optional[str] = None
    is_active: bool
    symbols: List[str]
    timeframes: List[str]
    updated_at: str
    version: int


class StrategyDetailResponse(BaseModel):
    """Strategy detail response"""
    id: str
    name: str
    description: Optional[str] = None
    is_active: bool
    trigger_config: Dict[str, Any]
    filter_configs: List[Dict[str, Any]]
    filter_logic: Literal["AND", "OR"]
    symbols: List[str]
    timeframes: List[str]
    created_at: str
    updated_at: str
    version: int


class StrategyCreateRequest(BaseModel):
    """Strategy create request"""
    name: str = Field(..., min_length=1, max_length=64)
    description: Optional[str] = Field(None, max_length=256)
    trigger_config: Optional[Dict[str, Any]] = None
    filter_configs: Optional[List[Dict[str, Any]]] = None
    filter_logic: Literal["AND", "OR"] = "AND"
    symbols: List[str] = Field(default_factory=list)
    timeframes: List[str] = Field(default_factory=list)
    # Aliases for backwards compatibility (test format)
    trigger: Optional[Dict[str, Any]] = None
    filters: Optional[List[Dict[str, Any]]] = None

    @model_validator(mode='after')
    def normalize_trigger_and_filters(self):
        """Normalize trigger/trigger_config and filters/filter_configs fields."""
        # Handle trigger_config (prefer explicit field, fallback to alias)
        if self.trigger_config is None and self.trigger is not None:
            self.trigger_config = self.trigger
        elif self.trigger_config is None:
            raise ValueError("Either trigger_config or trigger must be provided")

        # Handle filter_configs (prefer explicit field, fallback to alias)
        if self.filter_configs is None and self.filters is not None:
            self.filter_configs = self.filters
        elif self.filter_configs is None:
            self.filter_configs = []

        return self


class StrategyUpdateRequest(BaseModel):
    """Strategy update request"""
    name: Optional[str] = Field(None, min_length=1, max_length=64)
    description: Optional[str] = Field(None, max_length=256)
    is_active: Optional[bool] = None
    trigger_config: Optional[Dict[str, Any]] = None
    filter_configs: Optional[List[Dict[str, Any]]] = None
    filter_logic: Optional[Literal["AND", "OR"]] = None
    symbols: Optional[List[str]] = None
    timeframes: Optional[List[str]] = None


class StrategyToggleResponse(BaseModel):
    """Strategy toggle response"""
    id: str
    is_active: bool
    message: str


# ============================================================
# Pydantic Models - Symbol Config
# ============================================================
class SymbolListItem(BaseModel):
    """Symbol list item"""
    symbol: str
    is_active: bool
    is_core: bool
    min_quantity: Optional[Decimal] = None
    price_precision: Optional[int] = None
    quantity_precision: Optional[int] = None
    updated_at: str


class SymbolDetailResponse(BaseModel):
    """Symbol detail response"""
    symbol: str
    is_active: bool
    is_core: bool
    min_quantity: Optional[Decimal] = None
    price_precision: Optional[int] = None
    quantity_precision: Optional[int] = None
    created_at: str
    updated_at: str


class SymbolCreateRequest(BaseModel):
    """Symbol create request"""
    symbol: str = Field(..., min_length=1)
    is_active: bool = True
    is_core: bool = False
    min_quantity: Optional[Decimal] = None
    price_precision: Optional[int] = None
    quantity_precision: Optional[int] = None


class SymbolUpdateRequest(BaseModel):
    """Symbol update request"""
    is_active: Optional[bool] = None
    is_core: Optional[bool] = None
    min_quantity: Optional[Decimal] = None
    price_precision: Optional[int] = None
    quantity_precision: Optional[int] = None


class SymbolToggleResponse(BaseModel):
    """Symbol toggle response"""
    symbol: str
    is_active: bool
    message: str


# ============================================================
# Pydantic Models - Notification Config
# ============================================================
class NotificationListItem(BaseModel):
    """Notification channel list item"""
    id: str
    channel_type: str
    webhook_url_masked: str
    is_active: bool
    notify_on_signal: bool
    notify_on_order: bool
    notify_on_error: bool
    updated_at: str


class NotificationDetailResponse(BaseModel):
    """Notification channel detail response"""
    id: str
    channel_type: str
    webhook_url_masked: str  # 脱敏后的 webhook URL，防止敏感信息泄露
    is_active: bool
    notify_on_signal: bool
    notify_on_order: bool
    notify_on_error: bool
    created_at: str
    updated_at: str


class NotificationCreateRequest(BaseModel):
    """Notification channel create request"""
    channel_type: Literal["feishu", "wechat", "telegram", "slack"]
    webhook_url: str = Field(..., min_length=1)
    is_active: bool = True
    notify_on_signal: bool = True
    notify_on_order: bool = True
    notify_on_error: bool = True


class NotificationUpdateRequest(BaseModel):
    """Notification channel update request"""
    channel_type: Optional[Literal["feishu", "wechat", "telegram", "slack"]] = None
    webhook_url: Optional[str] = Field(None, min_length=1)
    is_active: Optional[bool] = None
    notify_on_signal: Optional[bool] = None
    notify_on_order: Optional[bool] = None
    notify_on_error: Optional[bool] = None


class NotificationTestRequest(BaseModel):
    """Notification channel test request"""
    message: str = "Test notification from 盯盘狗"


class NotificationTestResponse(BaseModel):
    """Notification channel test response"""
    id: str
    channel_type: str
    success: bool
    message: str


# ============================================================
# Pydantic Models - Global Config Summary
# ============================================================
class GlobalConfigSummary(BaseModel):
    """Global configuration summary"""
    risk: RiskConfigResponse
    system: SystemConfigResponse
    strategies_count: int
    symbols_count: int
    notifications_count: int
    last_updated: str


# ============================================================
# Pydantic Models - Import/Export
# ============================================================
class ImportPreviewRequest(BaseModel):
    """Import preview request"""
    yaml_content: str = Field(..., description="YAML content to import")
    filename: Optional[str] = None


class ImportPreviewResult(BaseModel):
    """Import preview result"""
    valid: bool
    preview_token: str
    summary: Dict[str, Any]
    conflicts: List[str]
    requires_restart: bool
    errors: List[str] = Field(default_factory=list)
    preview_data: Dict[str, Any] = Field(default_factory=dict)


class ImportConfirmRequest(BaseModel):
    """Import confirm request"""
    preview_token: str = Field(..., description="Preview token from preview response")


class ImportConfirmResponse(BaseModel):
    """Import confirm response"""
    status: str
    snapshot_id: Optional[str]
    message: str
    summary: Dict[str, Any]


class ExportRequest(BaseModel):
    """Export request"""
    include_strategies: bool = True
    include_risk: bool = True
    include_system: bool = True
    include_symbols: bool = True
    include_notifications: bool = True


class ExportResponse(BaseModel):
    """Export response"""
    status: str
    filename: str
    yaml_content: str
    created_at: str


# ============================================================
# Pydantic Models - Snapshot Management
# ============================================================
class SnapshotListItem(BaseModel):
    """Snapshot list item"""
    id: str
    name: str
    description: Optional[str] = None
    created_at: str
    created_by: str
    config_types: List[str]


class SnapshotDetailResponse(BaseModel):
    """Snapshot detail response"""
    id: str
    name: str
    description: Optional[str] = None
    config_data: Dict[str, Any]
    created_at: str
    updated_at: str
    created_by: str


class SnapshotCreateRequest(BaseModel):
    """Snapshot create request"""
    name: str = Field(..., min_length=1, max_length=64)
    description: Optional[str] = Field(None, max_length=256)


class SnapshotActivateResponse(BaseModel):
    """Snapshot activate response"""
    id: str
    name: str
    message: str
    requires_restart: bool


# ============================================================
# Pydantic Models - History Management
# ============================================================
class HistoryListItem(BaseModel):
    """History list item"""
    id: int
    entity_type: str
    entity_id: str
    action: str
    changed_by: Optional[str] = None
    changed_at: str
    change_summary: Optional[str] = None


class HistoryDetailResponse(BaseModel):
    """History detail response"""
    id: int
    entity_type: str
    entity_id: str
    action: str
    old_values: Optional[Dict[str, Any]] = None
    new_values: Optional[Dict[str, Any]] = None
    changed_by: Optional[str] = None
    changed_at: str
    change_summary: Optional[str] = None


class HistoryListResponse(BaseModel):
    """History list response with pagination"""
    items: List[HistoryListItem]
    total: int
    limit: int
    offset: int


class RollbackCandidateResponse(BaseModel):
    """Rollback candidate response"""
    id: int
    entity_type: str
    entity_id: str
    action: str
    changed_at: str
    change_summary: Optional[str] = None
    new_values: Optional[Dict[str, Any]] = None


class RollbackRequest(BaseModel):
    """Rollback request"""
    history_id: int = Field(..., description="History record ID to rollback to")
    entity_type: str = Field(..., description="Entity type")
    entity_id: str = Field(..., description="Entity ID")


class RollbackResponse(BaseModel):
    """Rollback response"""
    status: str
    message: str
    history_id: int
    entity_type: str
    entity_id: str


# ============================================================
# Helper Functions
# ============================================================
def mask_webhook_url(url: str, visible_chars: int = 4) -> str:
    """Mask webhook URL for security"""
    if len(url) <= visible_chars * 2:
        return "*" * len(url)
    return url[:visible_chars] + "*" * (len(url) - visible_chars * 2) + url[-visible_chars:]


async def check_admin_permission(request: Request):
    """Check if user has admin permission.

    Checks for X-User-Role header with value 'admin'.
    When full auth system is ready, this will integrate with the auth module.

    Local Development Bypass:
    Set DISABLE_AUTH=True environment variable to skip admin check.
    This is ONLY for local development and should NEVER be used in production.
    """
    # Local development bypass
    if os.environ.get("DISABLE_AUTH", "").lower() in ("true", "1", "yes"):
        logger.warning("[DEV_MODE] Admin permission check bypassed (DISABLE_AUTH=True)")
        return True

    # Check for admin role header (used in tests and simple deployments)
    # Support both X-User-Role and X-User-User-Role (typo in some tests)
    user_role = request.headers.get("X-User-Role") or request.headers.get("X-User-User-Role")
    if user_role != "admin":
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please provide X-User-Role: admin header."
        )
    return True


async def notify_hot_reload(config_type: str):
    """Notify observer for config hot-reload and refresh ConfigManager caches."""
    # 1. Refresh ConfigManager internal caches (fix: cache not being invalidated)
    if _cg._config_manager and hasattr(_cg._config_manager, "reload_all_configs_from_db"):
        try:
            await _cg._config_manager.reload_all_configs_from_db()
            logger.info(f"ConfigManager caches refreshed for config_type={config_type}")
        except Exception as e:
            logger.warning(f"ConfigManager cache refresh failed: {e}")

    # 2. Notify Observer (SignalPipeline, etc.)
    if _cg._observer and hasattr(_cg._observer, "notify"):
        await _cg._observer.notify(config_type)
        logger.info(f"Hot-reload notification sent for {config_type}")


# ============================================================
# API Router
# ============================================================
router = APIRouter(prefix="/api/v1/config", tags=["配置管理"])


# ============================================================
# Global Config Endpoint
# ============================================================
@router.get("", response_model=GlobalConfigSummary)
async def get_global_config():
    """
    获取全部配置摘要

    返回所有配置类型的摘要信息，用于概览。
    """
    # Get risk config
    risk_data = await _cg._risk_repo.get_global() if _cg._risk_repo else None
    if not risk_data:
        # Return default
        risk_data = {
            "id": "global",
            "max_loss_percent": Decimal("0.01"),
            "max_leverage": 10,
            "max_total_exposure": Decimal("0.8"),
            "cooldown_minutes": 240,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "version": 1,
        }

    # Get system config
    system_data = await _cg._system_repo.get_global() if _cg._system_repo else None
    if not system_data:
        # Return default
        system_data = {
            "id": "global",
            "core_symbols": ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT"],
            "ema_period": 60,
            "mtf_ema_period": 60,
            "mtf_mapping": {"15m": "1h", "1h": "4h", "4h": "1d"},
            "signal_cooldown_seconds": 14400,
            "queue_batch_size": 10,
            "queue_flush_interval": Decimal("5.0"),
            "queue_max_size": 1000,
            "warmup_history_bars": 100,
            "atr_filter_enabled": True,
            "atr_period": 14,
            "atr_min_ratio": Decimal("0.5"),
            "restart_required": False,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    # Get counts
    strategies_count = 0
    symbols_count = 0
    notifications_count = 0

    if _cg._strategy_repo:
        _, total = await _cg._strategy_repo.get_list(limit=1, offset=0)
        strategies_count = total

    if _cg._symbol_repo:
        symbols_count = len(await _cg._symbol_repo.get_all())

    if _cg._notification_repo:
        # Count notifications
        pass  # TODO: Add count method to repository

    # Find last updated
    last_updated = max(
        risk_data.get("updated_at", ""),
        system_data.get("updated_at", "")
    )

    return GlobalConfigSummary(
        risk=RiskConfigResponse(**risk_data),
        system=SystemConfigResponse(**system_data),
        strategies_count=strategies_count,
        symbols_count=symbols_count,
        notifications_count=notifications_count,
        last_updated=last_updated,
    )


# ============================================================
# Risk Config Endpoints
# ============================================================
@router.get("/risk", response_model=RiskConfigResponse)
async def get_risk_config():
    """获取风控配置"""
    if not _cg._risk_repo:
        raise HTTPException(status_code=503, detail="Risk repository not initialized")

    risk_data = await _cg._risk_repo.get_global()
    if not risk_data:
        # Return default
        risk_data = {
            "id": "global",
            "max_loss_percent": Decimal("0.01"),
            "max_leverage": 10,
            "max_total_exposure": Decimal("0.8"),
            "cooldown_minutes": 240,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "version": 1,
        }

    return RiskConfigResponse(**risk_data)


@router.put("/risk", response_model=RiskConfigResponse)
async def update_risk_config(
    request: RiskConfigUpdateRequest,
    admin: bool = Depends(check_admin_permission)
):
    """
    更新风控配置（热重载✅）

    风控配置变更会立即生效，无需重启系统。
    """
    if not _cg._risk_repo:
        raise HTTPException(status_code=503, detail="Risk repository not initialized")

    # Build update dict
    update_data = request.model_dump(mode='json', exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Convert string decimals back to Decimal for repository
    decimal_update_data = {}
    for key, value in update_data.items():
        if key in ("max_loss_percent", "max_total_exposure", "daily_max_loss"):
            decimal_update_data[key] = Decimal(str(value)) if value is not None else None
        else:
            decimal_update_data[key] = value

    success = await _cg._risk_repo.update(decimal_update_data)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update risk config")

    # Get updated config
    updated_config = await _cg._risk_repo.get_global()

    # Notify hot-reload
    await notify_hot_reload("risk")

    # Record history (use JSON-serializable update_data)
    if _cg._history_repo:
        await _cg._history_repo.record_change(
            entity_type="risk_config",
            entity_id="global",
            action="UPDATE",
            new_values=update_data,
            changed_by="admin",
            change_summary="Updated risk config",
        )

    return RiskConfigResponse(**updated_config)


# ============================================================
# System Config Endpoints
# ============================================================

def _flat_to_nested(system_data: Dict[str, Any]) -> SystemConfigResponse:
    """Convert flat database format to nested frontend format.

    DB format: {ema_period, signal_cooldown_seconds, queue_batch_size, queue_flush_interval, ...}
    Frontend format: {ema: {period}, signal_pipeline: {cooldown_seconds, queue: {...}}, ...}
    """
    return SystemConfigResponse(
        id=system_data.get("id", "global"),
        updated_at=system_data.get("updated_at", ""),
        ema=EmaConfig(period=system_data.get("ema_period", 60)),
        mtf_ema_period=system_data.get("mtf_ema_period", 60),
        signal_pipeline=SignalPipelineConfig(
            cooldown_seconds=system_data.get("signal_cooldown_seconds", 14400),
            queue=QueueConfig(
                batch_size=system_data.get("queue_batch_size", 10),
                flush_interval=float(system_data.get("queue_flush_interval", 5.0)),
                max_queue_size=system_data.get("queue_max_size", 1000),
            ),
        ),
        warmup=WarmupConfig(history_bars=system_data.get("warmup_history_bars", 100)),
        atr_filter_enabled=system_data.get("atr_filter_enabled", True),
        atr_period=system_data.get("atr_period", 14),
        atr_min_ratio=float(system_data.get("atr_min_ratio", 0.5)),
        restart_required=system_data.get("restart_required", False),
    )


def _nested_to_flat(update_data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert nested frontend update format to flat database format.

    Frontend: {ema: {period}, signal_pipeline: {cooldown_seconds, queue: {...}}, ...}
    DB: {ema_period, signal_cooldown_seconds, queue_batch_size, queue_flush_interval, ...}
    """
    flat = {}

    # ema.period -> ema_period
    if "ema" in update_data and update_data["ema"]:
        ema = update_data["ema"]
        if isinstance(ema, dict):
            if "period" in ema:
                flat["ema_period"] = ema["period"]
        elif hasattr(ema, "period"):
            flat["ema_period"] = ema.period

    # mtf_ema_period -> mtf_ema_period
    if "mtf_ema_period" in update_data and update_data["mtf_ema_period"] is not None:
        flat["mtf_ema_period"] = update_data["mtf_ema_period"]

    # signal_pipeline -> signal_cooldown_seconds, queue_*
    if "signal_pipeline" in update_data and update_data["signal_pipeline"]:
        sp = update_data["signal_pipeline"]
        if isinstance(sp, dict):
            if "cooldown_seconds" in sp:
                flat["signal_cooldown_seconds"] = sp["cooldown_seconds"]
            if "queue" in sp and sp["queue"]:
                queue = sp["queue"]
                if isinstance(queue, dict):
                    if "batch_size" in queue:
                        flat["queue_batch_size"] = queue["batch_size"]
                    if "flush_interval" in queue:
                        flat["queue_flush_interval"] = float(queue["flush_interval"])
                    if "max_queue_size" in queue:
                        flat["queue_max_size"] = queue["max_queue_size"]
                elif hasattr(queue, "batch_size"):
                    flat["queue_batch_size"] = queue.batch_size
                    flat["queue_flush_interval"] = float(queue.flush_interval)
                    flat["queue_max_size"] = queue.max_queue_size
        elif hasattr(sp, "cooldown_seconds"):
            flat["signal_cooldown_seconds"] = sp.cooldown_seconds
            if hasattr(sp, "queue"):
                flat["queue_batch_size"] = sp.queue.batch_size
                flat["queue_flush_interval"] = float(sp.queue.flush_interval)
                flat["queue_max_size"] = sp.queue.max_queue_size

    # warmup.history_bars -> warmup_history_bars
    if "warmup" in update_data and update_data["warmup"]:
        warmup = update_data["warmup"]
        if isinstance(warmup, dict):
            if "history_bars" in warmup:
                flat["warmup_history_bars"] = warmup["history_bars"]
        elif hasattr(warmup, "history_bars"):
            flat["warmup_history_bars"] = warmup.history_bars

    # Direct fields
    if "atr_filter_enabled" in update_data and update_data["atr_filter_enabled"] is not None:
        flat["atr_filter_enabled"] = update_data["atr_filter_enabled"]
    if "atr_period" in update_data and update_data["atr_period"] is not None:
        flat["atr_period"] = update_data["atr_period"]
    if "atr_min_ratio" in update_data and update_data["atr_min_ratio"] is not None:
        flat["atr_min_ratio"] = float(update_data["atr_min_ratio"])

    return flat


@router.get("/system", response_model=SystemConfigResponse)
async def get_system_config():
    """
    获取系统配置

    Returns system config in nested format matching frontend SystemConfigResponse.
    No admin permission required (read-only endpoint).
    """
    if not _cg._system_repo:
        raise HTTPException(status_code=503, detail="System repository not initialized")

    system_data = await _cg._system_repo.get_global()
    if not system_data:
        # Return default in nested format
        return SystemConfigResponse()

    return _flat_to_nested(system_data)


@router.put("/system", response_model=SystemConfigResponse)
async def update_system_config(
    request: SystemConfigUpdateRequest,
    admin: bool = Depends(check_admin_permission)
):
    """
    更新系统配置（需重启⚠️）

    系统配置变更需要重启系统才能生效。
    Accepts nested format matching frontend SystemConfigUpdateRequest.
    Sends hot-reload notification after successful update.
    """
    if not _cg._system_repo:
        raise HTTPException(status_code=503, detail="System repository not initialized")

    # Convert nested request to flat database format
    update_data = request.model_dump(mode='json', exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    flat_data = _nested_to_flat(update_data)
    if not flat_data:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    # Determine if restart is required (most system config changes require restart)
    restart_required_fields = [
        "ema_period", "mtf_ema_period",
        "signal_cooldown_seconds", "queue_batch_size", "queue_flush_interval", "queue_max_size",
        "warmup_history_bars", "atr_filter_enabled", "atr_period", "atr_min_ratio",
    ]
    restart_required = any(key in flat_data for key in restart_required_fields)

    success = await _cg._system_repo.update(flat_data, restart_required=restart_required)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update system config")

    # Get updated config
    updated_config = await _cg._system_repo.get_global()

    # Record history (use the nested update_data for audit trail)
    if _cg._history_repo:
        await _cg._history_repo.record_change(
            entity_type="system_config",
            entity_id="global",
            action="UPDATE",
            new_values=update_data,
            changed_by="admin",
            change_summary="Updated system config" + (" (restart required)" if restart_required else ""),
        )

    # Send hot-reload notification (observer can decide whether to apply immediately)
    await notify_hot_reload("system")

    response_data = _flat_to_nested(updated_config)

    if restart_required:
        logger.warning("System config updated - restart required for changes to take effect")

    return response_data


# ============================================================
# Strategy Management Endpoints
# ============================================================
@router.get("/strategies", response_model=List[StrategyListItem])
async def get_strategies(
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0)
):
    """获取策略列表"""
    if not _cg._strategy_repo:
        raise HTTPException(status_code=503, detail="Strategy repository not initialized")

    strategies, total = await _cg._strategy_repo.get_list(
        is_active=is_active,
        limit=limit,
        offset=offset
    )

    return [
        StrategyListItem(
            id=s["id"],
            name=s["name"],
            description=s["description"],
            is_active=s["is_active"],
            symbols=s["symbols"],
            timeframes=s["timeframes"],
            updated_at=s["updated_at"],
            version=s["version"],
        )
        for s in strategies
    ]


@router.post("/strategies", status_code=201)
async def create_strategy(
    request: StrategyCreateRequest,
    admin: bool = Depends(check_admin_permission)
):
    """创建策略"""
    if not _cg._strategy_repo:
        raise HTTPException(status_code=503, detail="Strategy repository not initialized")

    try:
        strategy_data = request.model_dump(mode='json')
        strategy_id = await _cg._strategy_repo.create(strategy_data)

        # Record history
        if _cg._history_repo:
            await _cg._history_repo.record_change(
                entity_type="strategy",
                entity_id=strategy_id,
                action="CREATE",
                new_values=strategy_data,
                changed_by="admin",
                change_summary=f"Created strategy '{request.name}'",
            )

        # Notify hot-reload
        await notify_hot_reload("strategy")

        return {
            "status": "created",
            "id": strategy_id,
            "message": f"Strategy '{request.name}' created successfully"
        }
    except ConfigConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/strategies/{strategy_id}", response_model=StrategyDetailResponse)
async def get_strategy(
    strategy_id: str,
):
    """获取策略详情"""
    if not _cg._strategy_repo:
        raise HTTPException(status_code=503, detail="Strategy repository not initialized")

    strategy = await _cg._strategy_repo.get_by_id(strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail=f"Strategy '{strategy_id}' not found")

    return StrategyDetailResponse(**strategy)


@router.put("/strategies/{strategy_id}", response_model=StrategyDetailResponse)
async def update_strategy(
    strategy_id: str,
    request: StrategyUpdateRequest,
    admin: bool = Depends(check_admin_permission)
):
    """
    更新策略（热重载✅）

    策略配置变更会立即生效，无需重启系统。
    """
    if not _cg._strategy_repo:
        raise HTTPException(status_code=503, detail="Strategy repository not initialized")

    # Check if strategy exists
    existing = await _cg._strategy_repo.get_by_id(strategy_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Strategy '{strategy_id}' not found")

    # Build update dict
    update_data = request.model_dump(mode='json', exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        success = await _cg._strategy_repo.update(strategy_id, update_data)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update strategy")

        # Get updated strategy
        updated_strategy = await _cg._strategy_repo.get_by_id(strategy_id)

        # Record history
        if _cg._history_repo:
            await _cg._history_repo.record_change(
                entity_type="strategy",
                entity_id=strategy_id,
                action="UPDATE",
                old_values=existing,
                new_values=update_data,
                changed_by="admin",
                change_summary=f"Updated strategy '{updated_strategy.get('name', strategy_id)}'",
            )

        # Notify hot-reload
        await notify_hot_reload("strategy")

        return StrategyDetailResponse(**updated_strategy)
    except ConfigConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.delete("/strategies/{strategy_id}")
async def delete_strategy(
    strategy_id: str,
    admin: bool = Depends(check_admin_permission)
):
    """删除策略"""
    if not _cg._strategy_repo:
        raise HTTPException(status_code=503, detail="Strategy repository not initialized")

    # Check if strategy exists
    existing = await _cg._strategy_repo.get_by_id(strategy_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Strategy '{strategy_id}' not found")

    success = await _cg._strategy_repo.delete(strategy_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete strategy")

    # Record history
    if _cg._history_repo:
        await _cg._history_repo.record_change(
            entity_type="strategy",
            entity_id=strategy_id,
            action="DELETE",
            old_values=existing,
            changed_by="admin",
            change_summary=f"Deleted strategy '{existing['name']}'",
        )

    # Notify hot-reload
    await notify_hot_reload("strategy")

    return {
        "status": "deleted",
        "id": strategy_id,
        "message": f"Strategy '{existing['name']}' deleted successfully"
    }


@router.post("/strategies/{strategy_id}/toggle", response_model=StrategyToggleResponse)
async def toggle_strategy(
    strategy_id: str,
    admin: bool = Depends(check_admin_permission)
):
    """启用/禁用策略"""
    if not _cg._strategy_repo:
        raise HTTPException(status_code=503, detail="Strategy repository not initialized")

    # Check if strategy exists
    existing = await _cg._strategy_repo.get_by_id(strategy_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Strategy '{strategy_id}' not found")

    new_status = await _cg._strategy_repo.toggle(strategy_id)
    if new_status is None:
        raise HTTPException(status_code=404, detail=f"Strategy '{strategy_id}' not found")

    # Record history
    if _cg._history_repo:
        await _cg._history_repo.record_change(
            entity_type="strategy",
            entity_id=strategy_id,
            action="UPDATE",
            old_values={"is_active": not new_status},
            new_values={"is_active": new_status},
            changed_by="admin",
            change_summary=f"Toggled strategy '{existing['name']}' to {'active' if new_status else 'inactive'}",
        )

    # Notify hot-reload
    await notify_hot_reload("strategy")

    return StrategyToggleResponse(
        id=strategy_id,
        is_active=new_status,
        message="enabled" if new_status else "disabled",
    )


# ============================================================
# Symbol Pool Management Endpoints
# ============================================================
@router.get("/symbols", response_model=List[SymbolListItem])
async def get_symbols(
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
):
    """获取币池列表"""
    if not _cg._symbol_repo:
        raise HTTPException(status_code=503, detail="Symbol repository not initialized")

    if is_active is not None:
        symbols = await _cg._symbol_repo.get_active() if is_active else await _cg._symbol_repo.get_all()
    else:
        symbols = await _cg._symbol_repo.get_all()

    return [
        SymbolListItem(
            symbol=s["symbol"],
            is_active=s["is_active"],
            is_core=s["is_core"],
            min_quantity=s["min_quantity"],
            price_precision=s["price_precision"],
            quantity_precision=s["quantity_precision"],
            updated_at=s["updated_at"],
        )
        for s in symbols
    ]


@router.post("/symbols", status_code=201)
async def create_symbol(
    request: SymbolCreateRequest,
    admin: bool = Depends(check_admin_permission)
):
    """添加币种"""
    if not _cg._symbol_repo:
        raise HTTPException(status_code=503, detail="Symbol repository not initialized")

    try:
        symbol_data = request.model_dump(mode='json')
        # Convert string decimals back to Decimal
        if symbol_data.get("min_quantity"):
            symbol_data["min_quantity"] = Decimal(str(symbol_data["min_quantity"]))

        success = await _cg._symbol_repo.create(symbol_data)

        # Record history
        if _cg._history_repo:
            await _cg._history_repo.record_change(
                entity_type="symbol",
                entity_id=request.symbol,
                action="CREATE",
                new_values=symbol_data,
                changed_by="admin",
                change_summary=f"Added symbol '{request.symbol}'",
            )

        # Notify hot-reload
        await notify_hot_reload("symbol")

        return {
            "status": "created",
            "symbol": request.symbol,
            "message": f"Symbol '{request.symbol}' added successfully"
        }
    except ConfigConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.put("/symbols/{symbol:path}", response_model=SymbolDetailResponse)
async def update_symbol(
    symbol: str,
    request: SymbolUpdateRequest,
    admin: bool = Depends(check_admin_permission)
):
    """
    更新币种（热重载✅）

    币池配置变更会立即生效，无需重启系统。
    """
    if not _cg._symbol_repo:
        raise HTTPException(status_code=503, detail="Symbol repository not initialized")

    # Check if symbol exists
    existing = await _cg._symbol_repo.get_by_symbol(symbol)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Symbol '{symbol}' not found")

    # Build update dict
    update_data = request.model_dump(mode='json', exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Convert string decimals back to Decimal
    for key, value in update_data.items():
        if key == "min_quantity" and value is not None:
            update_data[key] = Decimal(str(value))

    success = await _cg._symbol_repo.update(symbol, update_data)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update symbol")

    # Get updated symbol
    updated_symbol = await _cg._symbol_repo.get_by_symbol(symbol)

    # Record history
    if _cg._history_repo:
        await _cg._history_repo.record_change(
            entity_type="symbol",
            entity_id=symbol,
            action="UPDATE",
            old_values=existing,
            new_values=update_data,
            changed_by="admin",
            change_summary=f"Updated symbol '{symbol}'",
        )

    # Notify hot-reload
    await notify_hot_reload("symbol")

    return SymbolDetailResponse(**updated_symbol)


@router.post("/symbols/{symbol:path}/toggle", response_model=SymbolToggleResponse)
async def toggle_symbol(
    symbol: str,
    admin: bool = Depends(check_admin_permission)
):
    """启用/禁用币种"""
    if not _cg._symbol_repo:
        raise HTTPException(status_code=503, detail="Symbol repository not initialized")

    # Check if symbol exists
    existing = await _cg._symbol_repo.get_by_symbol(symbol)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Symbol '{symbol}' not found")

    new_status = await _cg._symbol_repo.toggle(symbol)
    if new_status is None:
        raise HTTPException(status_code=404, detail=f"Symbol '{symbol}' not found")

    # Record history
    if _cg._history_repo:
        await _cg._history_repo.record_change(
            entity_type="symbol",
            entity_id=symbol,
            action="UPDATE",
            old_values={"is_active": not new_status},
            new_values={"is_active": new_status},
            changed_by="admin",
            change_summary=f"Toggled symbol '{symbol}' to {'active' if new_status else 'inactive'}",
        )

    # Notify hot-reload
    await notify_hot_reload("symbol")

    return SymbolToggleResponse(
        symbol=symbol,
        is_active=new_status,
        message="enabled" if new_status else "disabled",
    )


@router.delete("/symbols/{symbol:path}")
async def delete_symbol(
    symbol: str,
    admin: bool = Depends(check_admin_permission)
):
    """删除币种"""
    if not _cg._symbol_repo:
        raise HTTPException(status_code=503, detail="Symbol repository not initialized")

    # Check if symbol exists
    existing = await _cg._symbol_repo.get_by_symbol(symbol)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Symbol '{symbol}' not found")

    try:
        success = await _cg._symbol_repo.delete(symbol)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete symbol")

        # Record history
        if _cg._history_repo:
            await _cg._history_repo.record_change(
                entity_type="symbol",
                entity_id=symbol,
                action="DELETE",
                old_values=existing,
                changed_by="admin",
                change_summary=f"Deleted symbol '{symbol}'",
            )

        # Notify hot-reload
        await notify_hot_reload("symbol")

        return {
            "status": "deleted",
            "symbol": symbol,
            "message": f"Symbol '{symbol}' deleted successfully"
        }
    except ConfigValidationError as e:
        raise HTTPException(status_code=403, detail=str(e))


# ============================================================
# Notification Config Endpoints
# ============================================================
@router.get("/notifications", response_model=List[NotificationListItem])
async def get_notifications(
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
):
    """获取通知渠道列表"""
    if not _cg._notification_repo:
        raise HTTPException(status_code=503, detail="Notification repository not initialized")

    # Use get_list method with optional filters
    notifications = await _cg._notification_repo.get_list(is_active=is_active)

    # Mask webhook URLs for security
    result = []
    for notification in notifications:
        notification_data = dict(notification)
        notification_data["webhook_url_masked"] = mask_secret(
            notification.get("webhook_url", ""), visible_chars=4
        )
        result.append(NotificationListItem(**notification_data))

    return result


@router.post("/notifications", status_code=201)
async def create_notification(
    request: NotificationCreateRequest,
    admin: bool = Depends(check_admin_permission)
):
    """添加通知渠道"""
    if not _cg._notification_repo:
        raise HTTPException(status_code=503, detail="Notification repository not initialized")

    notification_data = request.model_dump(mode='json')
    notification_id = await _cg._notification_repo.create(notification_data)

    # Record history
    if _cg._history_repo:
        await _cg._history_repo.record_change(
            entity_type="notification",
            entity_id=notification_id,
            action="CREATE",
            new_values=notification_data,
            changed_by="admin",
            change_summary=f"Created notification channel '{request.channel_type}'",
        )

    return {
        "status": "created",
        "id": notification_id,
        "message": f"Notification channel '{request.channel_type}' added successfully"
    }


@router.get("/notifications/{notification_id}", response_model=NotificationDetailResponse)
async def get_notification(
    notification_id: str,
):
    """获取通知渠道详情"""
    if not _cg._notification_repo:
        raise HTTPException(status_code=503, detail="Notification repository not initialized")

    notification = await _cg._notification_repo.get_by_id(notification_id)
    if not notification:
        raise HTTPException(status_code=404, detail=f"Notification '{notification_id}' not found")

    # 对 webhook_url 进行脱敏处理
    notification_data = dict(notification)
    notification_data["webhook_url_masked"] = mask_secret(notification.get("webhook_url", ""), visible_chars=4)

    return NotificationDetailResponse(**notification_data)


@router.put("/notifications/{notification_id}", response_model=NotificationDetailResponse)
async def update_notification(
    notification_id: str,
    request: NotificationUpdateRequest,
    admin: bool = Depends(check_admin_permission)
):
    """更新通知渠道"""
    if not _cg._notification_repo:
        raise HTTPException(status_code=503, detail="Notification repository not initialized")

    # Check if notification exists
    existing = await _cg._notification_repo.get_by_id(notification_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Notification '{notification_id}' not found")

    # Build update dict
    update_data = request.model_dump(mode='json', exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    success = await _cg._notification_repo.update(notification_id, update_data)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update notification")

    # Get updated notification
    updated_notification = await _cg._notification_repo.get_by_id(notification_id)

    # Record history
    if _cg._history_repo:
        await _cg._history_repo.record_change(
            entity_type="notification",
            entity_id=notification_id,
            action="UPDATE",
            old_values=existing,
            new_values=update_data,
            changed_by="admin",
            change_summary=f"Updated notification channel '{notification_id}'",
        )

    # 对 webhook_url 进行脱敏处理
    updated_notification_data = dict(updated_notification)
    updated_notification_data["webhook_url_masked"] = mask_secret(updated_notification.get("webhook_url", ""), visible_chars=4)

    return NotificationDetailResponse(**updated_notification_data)


@router.delete("/notifications/{notification_id}")
async def delete_notification(
    notification_id: str,
    admin: bool = Depends(check_admin_permission)
):
    """删除通知渠道"""
    if not _cg._notification_repo:
        raise HTTPException(status_code=503, detail="Notification repository not initialized")

    # Check if notification exists
    existing = await _cg._notification_repo.get_by_id(notification_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Notification '{notification_id}' not found")

    success = await _cg._notification_repo.delete(notification_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete notification")

    # Record history
    if _cg._history_repo:
        await _cg._history_repo.record_change(
            entity_type="notification",
            entity_id=notification_id,
            action="DELETE",
            old_values=existing,
            changed_by="admin",
            change_summary=f"Deleted notification channel '{notification_id}'",
        )

    return {
        "status": "deleted",
        "id": notification_id,
        "message": f"Notification channel deleted successfully"
    }


@router.post("/notifications/{notification_id}/test", response_model=NotificationTestResponse)
async def test_notification(
    notification_id: str,
    request: Optional[NotificationTestRequest] = None,
    admin: bool = Depends(check_admin_permission)
):
    """测试通知渠道"""
    if not _cg._notification_repo:
        raise HTTPException(status_code=503, detail="Notification repository not initialized")

    # Check if notification exists
    notification = await _cg._notification_repo.get_by_id(notification_id)
    if not notification:
        raise HTTPException(status_code=404, detail=f"Notification '{notification_id}' not found")

    # TODO: Implement actual notification test using Notifier service
    # For now, return mock success
    return NotificationTestResponse(
        id=notification_id,
        channel_type=notification["channel_type"],
        success=True,
        message="Test notification sent successfully (mock)",
    )


# ============================================================
# Import/Export Endpoints
# ============================================================
# Preview tokens storage with TTL (5 minutes expiry, max 100 entries)
_import_preview_cache: cachetools.TTLCache = cachetools.TTLCache(maxsize=100, ttl=300)


@router.post("/export", response_model=ExportResponse)
async def export_config(
    request: ExportRequest = Body(default=ExportRequest()),
    admin: bool = Depends(check_admin_permission)
):
    """
    导出配置为 YAML

    导出当前系统的所有配置，用于备份或迁移。
    """
    export_data = {"version": "1.0", "exported_at": datetime.now(timezone.utc).isoformat()}

    # Export risk config
    if request.include_risk and _cg._risk_repo:
        risk_data = await _cg._risk_repo.get_global()
        if risk_data:
            export_data["risk"] = risk_data

    # Export system config
    if request.include_system and _cg._system_repo:
        system_data = await _cg._system_repo.get_global()
        if system_data:
            export_data["system"] = system_data

    # Export strategies
    if request.include_strategies and _cg._strategy_repo:
        strategies, _ = await _cg._strategy_repo.get_list(limit=1000, offset=0)
        export_data["strategies"] = strategies

    # Export symbols
    if request.include_symbols and _cg._symbol_repo:
        symbols = await _cg._symbol_repo.get_all()
        export_data["symbols"] = symbols

    # Export notifications
    if request.include_notifications and _cg._notification_repo:
        # TODO: Implement get_all method
        export_data["notifications"] = []

    # Convert Decimals to strings for YAML serialization (preserve precision)
    export_data = _convert_decimals_to_str(export_data)

    # Convert to YAML
    yaml_content = yaml.safe_dump(
        export_data,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )

    filename = f"config_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.yaml"

    # Record export operation to history
    if _cg._history_repo:
        # Build change summary
        exported_sections = []
        if request.include_risk and "risk" in export_data:
            exported_sections.append("risk")
        if request.include_system and "system" in export_data:
            exported_sections.append("system")
        if request.include_strategies and "strategies" in export_data:
            exported_sections.append(f"{len(export_data['strategies'])} strategies")
        if request.include_symbols and "symbols" in export_data:
            exported_sections.append(f"{len(export_data['symbols'])} symbols")
        if request.include_notifications:
            exported_sections.append("notifications")

        change_summary = f"Exported config: {', '.join(exported_sections)}"

        await _cg._history_repo.record_change(
            entity_type="config_bundle",
            entity_id="export",
            action="EXPORT",
            new_values={"filename": filename, "sections": exported_sections},
            changed_by="admin",
            change_summary=change_summary,
        )

    return ExportResponse(
        status="success",
        filename=filename,
        yaml_content=yaml_content,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


@router.post("/import/preview", response_model=ImportPreviewResult)
async def preview_import(
    request: ImportPreviewRequest,
    admin: bool = Depends(check_admin_permission)
):
    """
    预览导入配置（安全）

    解析 YAML 并验证，返回变更预览，不修改任何数据。
    """
    errors = []
    conflicts = []
    summary = {
        "strategies": {"added": 0, "modified": 0, "deleted": 0},
        "risk": {"modified": False},
        "symbols": {"added": 0},
        "notifications": {"added": 0},
    }
    requires_restart = False

    try:
        # Parse YAML
        import_data = yaml.safe_load(request.yaml_content)
        if not isinstance(import_data, dict):
            raise ConfigValidationError("Invalid YAML format: root must be a mapping", "C-200")

        # Validate risk config
        if "risk" in import_data:
            risk_data = import_data["risk"]
            if not isinstance(risk_data, dict):
                errors.append("risk: must be a mapping")
            else:
                summary["risk"]["modified"] = True

        # Validate system config
        if "system" in import_data:
            system_data = import_data["system"]
            if not isinstance(system_data, dict):
                errors.append("system: must be a mapping")
            else:
                # Check if restart required
                restart_fields = ["core_symbols", "ema_period", "mtf_ema_period", "mtf_mapping"]
                if any(field in system_data for field in restart_fields):
                    requires_restart = True

        # Validate strategies
        if "strategies" in import_data:
            strategies = import_data["strategies"]
            if not isinstance(strategies, list):
                errors.append("strategies: must be a list")
            else:
                # Check for duplicates and conflicts
                strategy_names = set()
                for s in strategies:
                    if not isinstance(s, dict):
                        errors.append("strategies: each item must be a mapping")
                        continue
                    name = s.get("name")
                    if name in strategy_names:
                        conflicts.append(f"Duplicate strategy name: {name}")
                    strategy_names.add(name)

                    # Check existing strategies for name conflicts
                    if _cg._strategy_repo and name:
                        # TODO: Check existing strategies by name
                        pass

                summary["strategies"]["added"] = len(strategies)

        # Validate symbols
        if "symbols" in import_data:
            symbols = import_data["symbols"]
            if not isinstance(symbols, list):
                errors.append("symbols: must be a list")
            else:
                summary["symbols"]["added"] = len(symbols)

        # Validate notifications
        if "notifications" in import_data:
            notifications = import_data["notifications"]
            if not isinstance(notifications, list):
                errors.append("notifications: must be a list")
            else:
                summary["notifications"]["added"] = len(notifications)

    except yaml.YAMLError as e:
        errors.append(f"YAML parsing error: {str(e)}")
    except ConfigValidationError as e:
        errors.append(str(e))

    valid = len(errors) == 0

    # Generate preview token
    preview_token = str(uuid.uuid4())

    # Store in TTL cache (auto-expires after 5 minutes)
    _import_preview_cache[preview_token] = {
        "import_data": import_data if valid else None,
        "summary": summary,
        "conflicts": conflicts,
        "requires_restart": requires_restart,
        "filename": request.filename or "import.yaml",
    }

    # Build preview_data for frontend display
    preview_data_dict = {
        "strategies": import_data.get("strategies", []) if valid and import_data else [],
        "risk": import_data.get("risk", {}) if valid and import_data else {},
        "symbols": import_data.get("symbols", []) if valid and import_data else [],
        "notifications": import_data.get("notifications", []) if valid and import_data else [],
    }

    return ImportPreviewResult(
        valid=valid,
        preview_token=preview_token,
        summary=summary,
        conflicts=conflicts,
        requires_restart=requires_restart,
        errors=errors,
        preview_data=preview_data_dict,
    )


@router.post("/import/confirm", response_model=ImportConfirmResponse)
async def confirm_import(
    request: ImportConfirmRequest,
    admin: bool = Depends(check_admin_permission)
):
    """
    确认导入配置

    使用预览 token 确认导入，实际写入数据库并创建快照。
    """
    # Check preview token (TTLCache auto-expires after 5 minutes)
    if request.preview_token not in _import_preview_cache:
        raise HTTPException(status_code=400, detail="Invalid or expired preview token")

    preview_data = _import_preview_cache[request.preview_token]

    import_data = preview_data.get("import_data")
    if not import_data:
        del _import_preview_cache[request.preview_token]
        raise HTTPException(status_code=400, detail="Preview data not found or invalid")

    snapshot_id = None

    try:
        # Create snapshot before import
        if _cg._snapshot_repo:
            # Convert Decimals to strings for JSON serialization (preserve precision)
            import_data_serialized = _convert_decimals_to_str(import_data)
            snapshot = {
                "name": f"Pre-import snapshot ({preview_data['filename']})",
                "description": f"Auto-created before importing {preview_data['filename']}",
                "snapshot_data": import_data_serialized,
                "created_by": "admin",
            }
            snapshot_id = await _cg._snapshot_repo.create(snapshot)

        # Apply import
        # 1. Risk config
        if "risk" in import_data and _cg._risk_repo:
            await _cg._risk_repo.update(import_data["risk"])

        # 2. System config
        if "system" in import_data and _cg._system_repo:
            await _cg._system_repo.update(import_data["system"], restart_required=preview_data["requires_restart"])

        # 3. Strategies
        if "strategies" in import_data and _cg._strategy_repo:
            for strategy in import_data["strategies"]:
                # Convert legacy trigger/filters format to trigger_config/filter_configs
                if "trigger" in strategy and "trigger_config" not in strategy:
                    strategy["trigger_config"] = strategy.pop("trigger")
                if "filters" in strategy and "filter_configs" not in strategy:
                    strategy["filter_configs"] = strategy.pop("filters")
                # Check if exists by name
                # For simplicity, create all as new
                await _cg._strategy_repo.create(strategy)

        # 4. Symbols
        if "symbols" in import_data and _cg._symbol_repo:
            for symbol in import_data["symbols"]:
                try:
                    await _cg._symbol_repo.create(symbol)
                except ConfigConflictError:
                    # Update existing
                    symbol_val = symbol["symbol"]
                    updates = {k: v for k, v in symbol.items() if k != "symbol"}
                    await _cg._symbol_repo.update(symbol_val, updates)

        # 5. Notifications
        if "notifications" in import_data and _cg._notification_repo:
            for notification in import_data["notifications"]:
                await _cg._notification_repo.create(notification)

        # Record import operation to history
        if _cg._history_repo:
            summary = preview_data.get("summary", {})
            imported_sections = []
            if "risk" in import_data:
                imported_sections.append("risk")
            if "system" in import_data:
                imported_sections.append("system")
            if "strategies" in import_data:
                imported_sections.append(f"{len(import_data['strategies'])} strategies")
            if "symbols" in import_data:
                imported_sections.append(f"{len(import_data['symbols'])} symbols")
            if "notifications" in import_data:
                imported_sections.append(f"{len(import_data['notifications'])} notifications")

            change_summary = f"Imported config from {preview_data['filename']}: {', '.join(imported_sections)}"

            await _cg._history_repo.record_change(
                entity_type="config_bundle",
                entity_id="import",
                action="IMPORT",
                new_values={"filename": preview_data['filename'], "sections": imported_sections, "snapshot_id": snapshot_id},
                changed_by="admin",
                change_summary=change_summary,
            )

        # Clean up preview cache
        del _import_preview_cache[request.preview_token]

        # Notify hot-reload
        await notify_hot_reload("import")

        return ImportConfirmResponse(
            status="success",
            snapshot_id=snapshot_id,
            message="Configuration imported successfully",
            summary=preview_data["summary"],
        )

    except Exception as e:
        logger.error(f"Import failed: {e}")
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")


# ============================================================
# Snapshot Management Endpoints
# ============================================================


def extract_config_types(config_data: Dict[str, Any]) -> List[str]:
    """从快照数据中提取配置类型列表

    Args:
        config_data: 快照配置数据字典

    Returns:
        配置类型名称列表，如 ["risk", "system", "strategies"]
    """
    if not config_data:
        return []

    types = []
    if "risk" in config_data:
        types.append("risk")
    if "system" in config_data:
        types.append("system")
    if "strategies" in config_data:
        types.append("strategies")
    if "symbols" in config_data:
        types.append("symbols")
    if "notifications" in config_data:
        types.append("notifications")
    return types


@router.get("/snapshots", response_model=List[SnapshotListItem])
async def get_snapshots(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """获取快照列表

    Args:
        limit: 每页数量 (1-500)
        offset: 偏移量

    Returns:
        快照列表，包含 id, name, description, created_at, created_by, config_types
    """
    if not _cg._snapshot_repo:
        raise HTTPException(status_code=503, detail="Snapshot repository not initialized")

    # 调用 repository 获取数据
    snapshots, total = await _cg._snapshot_repo.get_list(limit=limit, offset=offset)

    # 转换为响应模型
    result = []
    for snap in snapshots:
        result.append(SnapshotListItem(
            id=snap["id"],
            name=snap["name"],
            description=snap.get("description"),
            created_at=snap["created_at"],
            created_by=snap.get("created_by", "unknown"),
            config_types=extract_config_types(snap.get("config_data", {}))
        ))

    logger.info(f"[SNAPSHOT_LIST] fetched {len(result)} snapshots (total={total}, limit={limit}, offset={offset})")

    return result


@router.post("/snapshots", status_code=201)
async def create_snapshot(
    request: SnapshotCreateRequest,
    admin: bool = Depends(check_admin_permission)
):
    """创建配置快照"""
    if not _cg._snapshot_repo:
        raise HTTPException(status_code=503, detail="Snapshot repository not initialized")

    # Collect current config
    config_data = {}

    if _cg._risk_repo:
        risk_data = await _cg._risk_repo.get_global()
        if risk_data:
            config_data["risk"] = risk_data

    if _cg._system_repo:
        system_data = await _cg._system_repo.get_global()
        if system_data:
            config_data["system"] = system_data

    if _cg._strategy_repo:
        strategies, _ = await _cg._strategy_repo.get_list(limit=1000, offset=0)
        config_data["strategies"] = strategies

    if _cg._symbol_repo:
        config_data["symbols"] = await _cg._symbol_repo.get_all()

    # Convert Decimals to strings for JSON serialization (preserve precision)
    config_data = _convert_decimals_to_str(config_data)

    # Build snapshot dict matching repository signature
    snapshot = {
        "name": request.name,
        "description": request.description,
        "snapshot_data": config_data,
        "created_by": "admin",
    }
    snapshot_id = await _cg._snapshot_repo.create(snapshot)

    return {
        "status": "created",
        "id": snapshot_id,
        "message": f"Snapshot '{request.name}' created successfully"
    }


@router.get("/snapshots/{snapshot_id}", response_model=SnapshotDetailResponse)
async def get_snapshot(
    snapshot_id: str,
):
    """获取快照详情"""
    if not _cg._snapshot_repo:
        raise HTTPException(status_code=503, detail="Snapshot repository not initialized")

    snapshot = await _cg._snapshot_repo.get_by_id(snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"Snapshot '{snapshot_id}' not found")

    return SnapshotDetailResponse(**snapshot)


@router.post("/snapshots/{snapshot_id}/activate", response_model=SnapshotActivateResponse)
async def activate_snapshot(
    snapshot_id: str,
    admin: bool = Depends(check_admin_permission)
):
    """
    回滚到快照

    恢复配置到快照时的状态。
    """
    if not _cg._snapshot_repo:
        raise HTTPException(status_code=503, detail="Snapshot repository not initialized")

    snapshot = await _cg._snapshot_repo.get_by_id(snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"Snapshot '{snapshot_id}' not found")

    config_data = snapshot.get("config_data", {})
    requires_restart = False

    # Apply config from snapshot
    if "risk" in config_data and _cg._risk_repo:
        await _cg._risk_repo.update(config_data["risk"])

    if "system" in config_data and _cg._system_repo:
        system_config = config_data["system"]
        # Check if restart required
        restart_fields = ["core_symbols", "ema_period", "mtf_ema_period", "mtf_mapping"]
        requires_restart = any(field in system_config for field in restart_fields)
        await _cg._system_repo.update(system_config, restart_required=requires_restart)

    if "strategies" in config_data and _cg._strategy_repo:
        # TODO: Handle strategies restoration
        pass

    if "symbols" in config_data and _cg._symbol_repo:
        # TODO: Handle symbols restoration
        pass

    # Notify hot-reload
    await notify_hot_reload("snapshot_activate")

    return SnapshotActivateResponse(
        id=snapshot_id,
        name=snapshot["name"],
        message="Snapshot activated successfully",
        requires_restart=requires_restart,
    )


@router.delete("/snapshots/{snapshot_id}")
async def delete_snapshot(
    snapshot_id: str,
    admin: bool = Depends(check_admin_permission)
):
    """删除快照"""
    if not _cg._snapshot_repo:
        raise HTTPException(status_code=503, detail="Snapshot repository not initialized")

    # Check if snapshot exists
    snapshot = await _cg._snapshot_repo.get_by_id(snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"Snapshot '{snapshot_id}' not found")

    success = await _cg._snapshot_repo.delete(snapshot_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete snapshot")

    return {
        "status": "deleted",
        "id": snapshot_id,
        "message": f"Snapshot '{snapshot['name']}' deleted successfully"
    }


# ============================================================
# History Management Endpoints
# ============================================================
@router.get("/history", response_model=HistoryListResponse)
async def get_history_list(
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    entity_id: Optional[str] = Query(None, description="Filter by entity ID"),
    limit: int = Query(default=50, ge=0, le=500, description="Maximum number of results"),
    offset: int = Query(default=0, ge=0, description="Number of results to skip"),
):
    """
    Get configuration change history with pagination and filters.

    - **entity_type**: Optional filter by entity type (strategy, risk_config, system_config, symbol, notification)
    - **entity_id**: Optional filter by entity ID
    - **limit**: Maximum number of results (0-500, 0 returns empty list)
    - **offset**: Number of results to skip
    """
    if not _cg._history_repo:
        raise HTTPException(status_code=503, detail="History repository not initialized")

    # Handle limit=0 case
    if limit == 0:
        return HistoryListResponse(
            items=[],
            total=0,
            limit=limit,
            offset=offset
        )

    items, total = await _cg._history_repo.get_history(
        entity_type=entity_type,
        entity_id=entity_id,
        limit=limit,
        offset=offset
    )

    # Convert to list items
    list_items = [
        HistoryListItem(
            id=item["id"],
            entity_type=item["entity_type"],
            entity_id=item["entity_id"],
            action=item["action"],
            changed_by=item.get("changed_by"),
            changed_at=item["changed_at"],
            change_summary=item.get("change_summary"),
        )
        for item in items
    ]

    return HistoryListResponse(
        items=list_items,
        total=total,
        limit=limit,
        offset=offset
    )


@router.get("/history/rollback-candidates", response_model=List[RollbackCandidateResponse])
async def get_rollback_candidates(
    entity_type: Optional[str] = Query(None, description="Entity type"),
    entity_id: Optional[str] = Query(None, description="Entity ID"),
):
    """
    Get potential rollback points for an entity.

    - **entity_type**: Entity type (strategy, risk_config, system_config, symbol, notification)
    - **entity_id**: Entity ID

    Note: Returns empty list if entity_type or entity_id is not provided.
    """
    if not _cg._history_repo:
        raise HTTPException(status_code=503, detail="History repository not initialized")

    if not entity_type or not entity_id:
        return []

    candidates = await _cg._history_repo.get_rollback_candidates(
        entity_type=entity_type,
        entity_id=entity_id
    )

    return [
        RollbackCandidateResponse(
            id=item["id"],
            entity_type=item["entity_type"],
            entity_id=item["entity_id"],
            action=item["action"],
            changed_at=item["changed_at"],
            change_summary=item.get("change_summary"),
            new_values=item.get("new_values"),
        )
        for item in candidates
    ]


@router.get("/history/entity/{entity_type}/{entity_id}", response_model=HistoryListResponse)
async def get_entity_history(
    entity_type: str,
    entity_id: str,
    limit: int = Query(default=20, ge=1, le=100, description="Maximum number of results"),
    action: Optional[str] = Query(default=None, description="Filter by action type (CREATE/UPDATE/DELETE/ROLLBACK)"),  # R10.1
    start_date: Optional[str] = Query(default=None, description="Filter by start date (ISO format)"),  # R10.1
    end_date: Optional[str] = Query(default=None, description="Filter by end date (ISO format)"),  # R10.1
):
    """
    Get complete history for a specific entity.

    - **entity_type**: Entity type (strategy, risk_config, system_config, symbol, notification)
    - **entity_id**: Entity ID
    - **limit**: Maximum number of results (1-100)
    - **action**: Filter by action type (CREATE/UPDATE/DELETE/ROLLBACK) - R10.1
    - **start_date**: Filter by start date (ISO format) - R10.1
    - **end_date**: Filter by end date (ISO format) - R10.1
    """
    if not _cg._history_repo:
        raise HTTPException(status_code=503, detail="History repository not initialized")

    items = await _cg._history_repo.get_entity_history(
        entity_type=entity_type,
        entity_id=entity_id,
        limit=limit,
        action=action,
        start_date=start_date,
        end_date=end_date,
    )

    list_items = [
        HistoryListItem(
            id=item["id"],
            entity_type=item["entity_type"],
            entity_id=item["entity_id"],
            action=item["action"],
            changed_by=item.get("changed_by"),
            changed_at=item["changed_at"],
            change_summary=item.get("change_summary"),
        )
        for item in items
    ]

    return HistoryListResponse(
        items=list_items,
        total=len(items),
        limit=limit,
        offset=0
    )


@router.get("/history/{history_id}", response_model=HistoryDetailResponse)
async def get_history_detail(
    history_id: int,
):
    """
    Get detailed information about a specific history record.

    - **history_id**: History record ID
    """
    if not _cg._history_repo:
        raise HTTPException(status_code=503, detail="History repository not initialized")

    # Get all history and find the specific one
    # Note: This is inefficient, consider adding get_by_id method to repository
    items, _ = await _cg._history_repo.get_history(limit=1000, offset=0)

    for item in items:
        if item["id"] == history_id:
            return HistoryDetailResponse(
                id=item["id"],
                entity_type=item["entity_type"],
                entity_id=item["entity_id"],
                action=item["action"],
                old_values=item.get("old_values"),
                new_values=item.get("new_values"),
                changed_by=item.get("changed_by"),
                changed_at=item["changed_at"],
                change_summary=item.get("change_summary"),
            )

    raise HTTPException(status_code=404, detail=f"History record '{history_id}' not found")


@router.post("/history/rollback", response_model=RollbackResponse)
async def rollback_to_version(
    request: RollbackRequest,
    admin: bool = Depends(check_admin_permission)
):
    """
    Rollback configuration to a specific version.

    - **history_id**: History record ID to rollback to
    - **entity_type**: Entity type
    - **entity_id**: Entity ID
    """
    if not _cg._history_repo:
        raise HTTPException(status_code=503, detail="History repository not initialized")

    # Get the history record
    items, _ = await _cg._history_repo.get_history(limit=1000, offset=0)
    target_history = None
    for item in items:
        if item["id"] == request.history_id:
            target_history = item
            break

    if not target_history:
        raise HTTPException(status_code=404, detail=f"History record '{request.history_id}' not found")

    # Verify entity matches
    if target_history["entity_type"] != request.entity_type or target_history["entity_id"] != request.entity_id:
        raise HTTPException(status_code=400, detail="Entity type or ID mismatch")

    # Cannot rollback to DELETE action
    if target_history["action"] == "DELETE":
        raise HTTPException(status_code=400, detail="Cannot rollback to DELETE action")

    # Get the values to rollback to
    if target_history["action"] == "CREATE":
        values_to_restore = target_history.get("new_values")
    elif target_history["action"] == "UPDATE":
        values_to_restore = target_history.get("old_values")
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported action type: {target_history['action']}")

    if not values_to_restore:
        raise HTTPException(status_code=400, detail="No values to restore")

    # Apply the rollback based on entity type
    requires_restart = False

    if request.entity_type == "risk_config":
        if _cg._risk_repo:
            await _cg._risk_repo.update(values_to_restore)
    elif request.entity_type == "system_config":
        if _cg._system_repo:
            restart_fields = ["core_symbols", "ema_period", "mtf_ema_period", "mtf_mapping"]
            requires_restart = any(field in values_to_restore for field in restart_fields)
            await _cg._system_repo.update(values_to_restore, restart_required=requires_restart)
    elif request.entity_type == "strategy":
        if _cg._strategy_repo:
            # Map API field names to database field names
            update_data = {}
            for k, v in values_to_restore.items():
                if k in ["id", "created_at", "updated_at", "version"]:
                    continue
                # Map API field names to DB field names
                if k == "trigger":
                    update_data["trigger_config"] = v
                elif k == "filters":
                    update_data["filter_configs"] = v
                else:
                    update_data[k] = v
            await _cg._strategy_repo.update(request.entity_id, update_data)
    elif request.entity_type == "symbol":
        if _cg._symbol_repo:
            update_data = {k: v for k, v in values_to_restore.items() if k not in ["symbol", "created_at", "updated_at"]}
            await _cg._symbol_repo.update(request.entity_id, update_data)
    elif request.entity_type == "notification":
        if _cg._notification_repo:
            update_data = {k: v for k, v in values_to_restore.items() if k not in ["id", "created_at", "updated_at"]}
            await _cg._notification_repo.update(request.entity_id, update_data)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported entity type: {request.entity_type}")

    # Record the rollback action in history
    await _cg._history_repo.record_change(
        entity_type=request.entity_type,
        entity_id=request.entity_id,
        action="ROLLBACK",
        old_values=None,
        new_values=values_to_restore,
        changed_by="admin",
        change_summary=f"Rolled back to version {request.history_id}"
    )

    # Notify hot-reload
    await notify_hot_reload("rollback")

    return RollbackResponse(
        status="success",
        message=f"Successfully rolled back to version {request.history_id}",
        history_id=request.history_id,
        entity_type=request.entity_type,
        entity_id=request.entity_id,
    )


# ============================================================
# Pydantic Models - Exchange Config (Task A-4)
# ============================================================
class ExchangeConfigResponse(BaseModel):
    """Exchange configuration response (api_key/api_secret masked)"""
    name: str
    api_key: str  # masked
    api_secret: str = Field(default="****", description="API Secret (masked)")
    testnet: bool


class ExchangeConfigUpdateRequest(BaseModel):
    """Exchange configuration update request"""
    name: str = Field(default="binance", description="Exchange name (ccxt id)")
    api_key: str = Field(default="", description="API Key")
    api_secret: str = Field(default="", description="API Secret")
    testnet: bool = Field(default=True, description="Use testnet")


# ============================================================
# Pydantic Models - Timeframes (Task A-4)
# ============================================================
class TimeframesResponse(BaseModel):
    """Timeframes list response"""
    timeframes: List[str]


class TimeframesUpdateRequest(BaseModel):
    """Timeframes update request"""
    timeframes: List[str] = Field(..., min_length=1, description="List of timeframes (e.g., ['15m', '1h', '4h'])")


# ============================================================
# Pydantic Models - Migration Status (Task A-4)
# ============================================================
class MigrationStatus(BaseModel):
    """YAML migration status"""
    yaml_fully_migrated: bool = False
    one_time_import_done: bool = False
    import_version: str = "v1"


# ============================================================
# Pydantic Models - Effective Config (Task A-4)
# ============================================================
class AssetPollingSummary(BaseModel):
    """Asset polling config summary"""
    enabled: bool = True
    interval_seconds: int = 60


class SystemSummary(BaseModel):
    """System config summary for effective config"""
    core_symbols: List[str] = Field(default_factory=list)
    ema_period: int = 60
    mtf_ema_period: int = 60
    mtf_mapping: Dict[str, str] = Field(default_factory=dict)
    signal_cooldown_seconds: int = 14400
    timeframes: List[str] = Field(default_factory=list)
    atr_filter_enabled: bool = True
    atr_period: int = 14
    atr_min_ratio: str = "0.5"


class RiskSummary(BaseModel):
    """Risk config summary for effective config"""
    max_loss_percent: str = "0.01"
    max_leverage: int = 10
    max_total_exposure: str = "0.8"
    daily_max_trades: Optional[int] = None
    daily_max_loss: Optional[str] = None
    cooldown_minutes: int = 240


class NotificationSummary(BaseModel):
    """Notification config summary for effective config"""
    channels: List[Dict[str, Any]] = Field(default_factory=list)


class StrategySummary(BaseModel):
    """Strategy summary for effective config"""
    id: str
    name: str
    is_active: bool
    trigger_type: str
    filter_count: int
    symbols: List[str] = Field(default_factory=list)
    timeframes: List[str] = Field(default_factory=list)


class SymbolSummary(BaseModel):
    """Symbol summary for effective config"""
    symbol: str
    is_core: bool
    is_active: bool


class EffectiveConfigResponse(BaseModel):
    """Complete merged runtime configuration"""
    exchange: ExchangeConfigResponse
    system: SystemSummary
    risk: RiskSummary
    notification: NotificationSummary
    strategies: List[StrategySummary] = Field(default_factory=list)
    symbols: List[SymbolSummary] = Field(default_factory=list)
    asset_polling: AssetPollingSummary
    migration_status: MigrationStatus
    config_version: int = 0
    created_at: str


# ============================================================
# Exchange Config Endpoints (Task A-4)
# ============================================================
@router.get("/exchange", response_model=ExchangeConfigResponse)
async def get_exchange_config():
    """
    获取交易所连接配置

    API Key 经过脱敏处理。
    """
    if not _cg._config_manager:
        raise HTTPException(status_code=503, detail="Config manager not initialized")

    exchange = await _cg._config_manager.get_exchange_config()

    return ExchangeConfigResponse(
        name=exchange.name,
        api_key=mask_secret(exchange.api_key),
        api_secret=mask_secret(exchange.api_secret),
        testnet=exchange.testnet,
    )


@router.put("/exchange", response_model=ExchangeConfigResponse)
async def update_exchange_config(
    request: ExchangeConfigUpdateRequest,
    admin: bool = Depends(check_admin_permission)
):
    """
    更新交易所连接配置（热重载）

    更新后会触发 ExchangeGateway 重连。
    """
    if not _cg._config_manager:
        raise HTTPException(status_code=503, detail="Config manager not initialized")

    from src.application.config_manager import ExchangeConfig

    config = ExchangeConfig(
        name=request.name,
        api_key=request.api_key,
        api_secret=request.api_secret,
        testnet=request.testnet,
    )

    await _cg._config_manager.update_exchange_config(config)

    # Notify hot-reload for exchange reconnection
    await notify_hot_reload("exchange")

    return ExchangeConfigResponse(
        name=config.name,
        api_key=mask_secret(config.api_key),
        api_secret=mask_secret(config.api_secret),
        testnet=config.testnet,
    )


# ============================================================
# Timeframes Endpoints (Task A-4)
# ============================================================
@router.get("/timeframes", response_model=TimeframesResponse)
async def get_timeframes():
    """获取监控时间周期列表"""
    if not _cg._config_manager:
        raise HTTPException(status_code=503, detail="Config manager not initialized")

    timeframes = await _cg._config_manager.get_timeframes()
    return TimeframesResponse(timeframes=timeframes)


@router.put("/timeframes", response_model=TimeframesResponse)
async def update_timeframes(
    request: TimeframesUpdateRequest,
    admin: bool = Depends(check_admin_permission)
):
    """
    更新监控时间周期列表（热重载）
    """
    if not _cg._config_manager:
        raise HTTPException(status_code=503, detail="Config manager not initialized")

    from src.application.config_manager import AssetPollingConfig

    await _cg._config_manager.update_timeframes(request.timeframes)

    await notify_hot_reload("timeframes")

    return TimeframesResponse(timeframes=request.timeframes)


# ============================================================
# Asset Polling Endpoint (Task A-4)
# ============================================================
class AssetPollingResponse(BaseModel):
    """Asset polling config response"""
    enabled: bool
    interval_seconds: int


class AssetPollingUpdateRequest(BaseModel):
    """Asset polling update request"""
    enabled: bool = True
    interval_seconds: int = Field(default=60, ge=10)


@router.get("/asset-polling", response_model=AssetPollingResponse)
async def get_asset_polling():
    """获取资产轮询配置"""
    if not _cg._config_manager:
        raise HTTPException(status_code=503, detail="Config manager not initialized")

    polling = await _cg._config_manager.get_asset_polling_config()
    return AssetPollingResponse(
        enabled=polling.enabled,
        interval_seconds=polling.interval_seconds,
    )


@router.put("/asset-polling", response_model=AssetPollingResponse)
async def update_asset_polling(
    request: AssetPollingUpdateRequest,
    admin: bool = Depends(check_admin_permission)
):
    """
    更新资产轮询配置（热重载）
    """
    if not _cg._config_manager:
        raise HTTPException(status_code=503, detail="Config manager not initialized")

    from src.application.config_manager import AssetPollingConfig

    config = AssetPollingConfig(
        enabled=request.enabled,
        interval_seconds=request.interval_seconds,
    )

    await _cg._config_manager.update_asset_polling_config(config)

    await notify_hot_reload("asset_polling")

    return AssetPollingResponse(
        enabled=config.enabled,
        interval_seconds=config.interval_seconds,
    )


# ============================================================
# Effective Config Endpoint (Task A-4)
# ============================================================
@router.get("/effective", response_model=EffectiveConfigResponse)
async def get_effective_config():
    """
    获取完整合并后的运行时配置总览

    返回所有配置的合并视图，敏感字段已脱敏。
    """
    if not _cg._config_manager:
        raise HTTPException(status_code=503, detail="Config manager not initialized")

    # Build response sections
    exchange = await _cg._config_manager.get_exchange_config()
    system_data = await _cg._config_manager.get_system_config()
    risk_config = await _cg._config_manager.get_risk_config()
    notification_config = await _cg._config_manager._build_notification_config()
    polling = await _cg._config_manager.get_asset_polling_config()
    migration = {"yaml_fully_migrated": True, "one_time_import_done": True, "import_version": "v1"}

    # Strategies summary
    strategies = await _cg._config_manager._load_strategies_from_db()
    strategy_summaries = []
    for s in strategies:
        strategy_summaries.append(StrategySummary(
            id=s.id,
            name=s.name,
            is_active=getattr(s, 'enabled', True),
            trigger_type=s.trigger.type if s.trigger else "pinbar",
            filter_count=len(s.filters),
            symbols=getattr(s, 'apply_to', []) or [],
            timeframes=[],
        ))

    # Symbols summary
    symbols_list = []
    if _cg._symbol_repo:
        symbols = await _cg._symbol_repo.get_all()
        symbols_list = [
            SymbolSummary(
                symbol=s["symbol"],
                is_core=s.get("is_core", False),
                is_active=s.get("is_active", True),
            )
            for s in symbols
        ]

    return EffectiveConfigResponse(
        exchange=ExchangeConfigResponse(
            name=exchange.name,
            api_key=mask_secret(exchange.api_key),
            api_secret=mask_secret(exchange.api_secret),
            testnet=exchange.testnet,
        ),
        system=SystemSummary(
            core_symbols=system_data.get("core_symbols", []),
            ema_period=system_data.get("ema_period", 60),
            mtf_ema_period=system_data.get("mtf_ema_period", 60),
            mtf_mapping=system_data.get("mtf_mapping", {}),
            signal_cooldown_seconds=system_data.get("signal_cooldown_seconds", 14400),
            timeframes=system_data.get("timeframes", ["15m", "1h"]),
            atr_filter_enabled=system_data.get("atr_filter_enabled", True),
            atr_period=system_data.get("atr_period", 14),
            atr_min_ratio=str(system_data.get("atr_min_ratio", "0.5")),
        ),
        risk=RiskSummary(
            max_loss_percent=str(risk_config.max_loss_percent),
            max_leverage=risk_config.max_leverage,
            max_total_exposure=str(risk_config.max_total_exposure),
            daily_max_trades=risk_config.daily_max_trades,
            daily_max_loss=str(risk_config.daily_max_loss) if risk_config.daily_max_loss else None,
            cooldown_minutes=240,
        ),
        notification=NotificationSummary(
            channels=[
                {
                    "type": c.type,
                    "webhook_url": mask_secret(c.webhook_url),
                    "is_active": True,
                }
                for c in notification_config.channels
            ],
        ),
        strategies=strategy_summaries,
        symbols=symbols_list,
        asset_polling=AssetPollingSummary(
            enabled=polling.enabled,
            interval_seconds=polling.interval_seconds,
        ),
        migration_status=MigrationStatus(
            yaml_fully_migrated=migration.get("yaml_fully_migrated", True),
            one_time_import_done=migration.get("one_time_import_done", True),
            import_version=migration.get("import_version", "v1"),
        ),
        config_version=_cg._config_manager.get_config_version(),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
