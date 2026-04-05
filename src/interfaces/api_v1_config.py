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
import tempfile
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any, Literal

import yaml
from fastapi import APIRouter, Depends, HTTPException, Body, Query, Request
from pydantic import BaseModel, Field, field_validator, model_validator

from src.infrastructure.logger import mask_secret


def _decimal_representer(dumper, data):
    """Custom YAML representer for Decimal types."""
    return dumper.represent_scalar('tag:yaml.org,2002:float', float(data))


yaml.add_representer(Decimal, _decimal_representer)


def _convert_decimals_to_float(obj: Any) -> Any:
    """
    Recursively convert all Decimal values in a dict/list to float for JSON/YAML serialization.
    """
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: _convert_decimals_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_decimals_to_float(item) for item in obj]
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
# Global Dependencies (injected at startup)
# ============================================================
_strategy_repo: Optional[StrategyConfigRepository] = None
_risk_repo: Optional[RiskConfigRepository] = None
_system_repo: Optional[SystemConfigRepository] = None
_symbol_repo: Optional[SymbolConfigRepository] = None
_notification_repo: Optional[NotificationConfigRepository] = None
_history_repo: Optional[ConfigHistoryRepository] = None
_snapshot_repo: Optional[ConfigSnapshotRepositoryExtended] = None
_config_manager: Optional[Any] = None  # ConfigManager for hot-reload
_observer: Optional[Any] = None  # Observer for hot-reload notifications


def set_config_dependencies(
    strategy_repo: Optional[StrategyConfigRepository] = None,
    risk_repo: Optional[RiskConfigRepository] = None,
    system_repo: Optional[SystemConfigRepository] = None,
    symbol_repo: Optional[SymbolConfigRepository] = None,
    notification_repo: Optional[NotificationConfigRepository] = None,
    history_repo: Optional[ConfigHistoryRepository] = None,
    snapshot_repo: Optional[ConfigSnapshotRepositoryExtended] = None,
    config_manager: Optional[Any] = None,
    observer: Optional[Any] = None,
):
    """Inject repository and manager dependencies."""
    global _strategy_repo, _risk_repo, _system_repo, _symbol_repo
    global _notification_repo, _history_repo, _snapshot_repo
    global _config_manager, _observer

    _strategy_repo = strategy_repo
    _risk_repo = risk_repo
    _system_repo = system_repo
    _symbol_repo = symbol_repo
    _notification_repo = notification_repo
    _history_repo = history_repo
    _snapshot_repo = snapshot_repo
    _config_manager = config_manager
    _observer = observer


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
class SystemConfigResponse(BaseModel):
    """System configuration response"""
    id: str
    core_symbols: List[str]
    ema_period: int
    mtf_ema_period: int
    mtf_mapping: Dict[str, str]
    signal_cooldown_seconds: int
    queue_batch_size: int
    queue_flush_interval: Decimal
    queue_max_size: int
    warmup_history_bars: int
    atr_filter_enabled: bool
    atr_period: int
    atr_min_ratio: Decimal
    restart_required: bool
    updated_at: str


class SystemConfigUpdateRequest(BaseModel):
    """System configuration update request"""
    core_symbols: Optional[List[str]] = None
    ema_period: Optional[int] = Field(None, ge=5, le=200)
    mtf_ema_period: Optional[int] = Field(None, ge=5, le=200)
    mtf_mapping: Optional[Dict[str, str]] = None
    signal_cooldown_seconds: Optional[int] = Field(None, ge=0)
    queue_batch_size: Optional[int] = Field(None, ge=1)
    queue_flush_interval: Optional[Decimal] = Field(None, ge=Decimal("0"))
    queue_max_size: Optional[int] = Field(None, ge=1)
    warmup_history_bars: Optional[int] = Field(None, ge=1)
    atr_filter_enabled: Optional[bool] = None
    atr_period: Optional[int] = Field(None, ge=5, le=50)
    atr_min_ratio: Optional[Decimal] = Field(None, ge=Decimal("0"))


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
    expires_at: str
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
    """
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
    """Notify observer for config hot-reload."""
    if _observer and hasattr(_observer, "notify"):
        await _observer.notify(config_type)
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
    risk_data = await _risk_repo.get_global() if _risk_repo else None
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
    system_data = await _system_repo.get_global() if _system_repo else None
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

    if _strategy_repo:
        _, total = await _strategy_repo.get_list(limit=1, offset=0)
        strategies_count = total

    if _symbol_repo:
        symbols_count = len(await _symbol_repo.get_all())

    if _notification_repo:
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
    if not _risk_repo:
        raise HTTPException(status_code=503, detail="Risk repository not initialized")

    risk_data = await _risk_repo.get_global()
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
    if not _risk_repo:
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

    success = await _risk_repo.update(decimal_update_data)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update risk config")

    # Get updated config
    updated_config = await _risk_repo.get_global()

    # Notify hot-reload
    await notify_hot_reload("risk")

    # Record history (use JSON-serializable update_data)
    if _history_repo:
        await _history_repo.record_change(
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
@router.get("/system", response_model=SystemConfigResponse)
async def get_system_config():
    """获取系统配置"""
    if not _system_repo:
        raise HTTPException(status_code=503, detail="System repository not initialized")

    system_data = await _system_repo.get_global()
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

    return SystemConfigResponse(**system_data)


@router.put("/system", response_model=SystemConfigResponse)
async def update_system_config(
    request: SystemConfigUpdateRequest,
    admin: bool = Depends(check_admin_permission)
):
    """
    更新系统配置（需重启⚠️）

    系统配置变更需要重启系统才能生效。
    """
    if not _system_repo:
        raise HTTPException(status_code=503, detail="System repository not initialized")

    # Build update dict
    update_data = request.model_dump(mode='json', exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Convert string decimals back to Decimal
    for key, value in update_data.items():
        if key in ("queue_flush_interval", "atr_min_ratio"):
            update_data[key] = Decimal(str(value)) if value is not None else None

    # Determine if restart is required
    restart_required_fields = ["core_symbols", "ema_period", "mtf_ema_period", "mtf_mapping",
                               "queue_batch_size", "queue_flush_interval", "queue_max_size"]
    restart_required = any(key in update_data for key in restart_required_fields)

    success = await _system_repo.update(update_data, restart_required=restart_required)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update system config")

    # Get updated config
    updated_config = await _system_repo.get_global()

    # Record history
    if _history_repo:
        await _history_repo.record_change(
            entity_type="system_config",
            entity_id="global",
            action="UPDATE",
            new_values=update_data,
            changed_by="admin",
            change_summary="Updated system config" + (" (restart required)" if restart_required else ""),
        )

    response_data = SystemConfigResponse(**updated_config)

    if restart_required:
        # Log warning
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
    if not _strategy_repo:
        raise HTTPException(status_code=503, detail="Strategy repository not initialized")

    strategies, total = await _strategy_repo.get_list(
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
    if not _strategy_repo:
        raise HTTPException(status_code=503, detail="Strategy repository not initialized")

    try:
        strategy_data = request.model_dump(mode='json')
        strategy_id = await _strategy_repo.create(strategy_data)

        # Record history
        if _history_repo:
            await _history_repo.record_change(
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
    if not _strategy_repo:
        raise HTTPException(status_code=503, detail="Strategy repository not initialized")

    strategy = await _strategy_repo.get_by_id(strategy_id)
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
    if not _strategy_repo:
        raise HTTPException(status_code=503, detail="Strategy repository not initialized")

    # Check if strategy exists
    existing = await _strategy_repo.get_by_id(strategy_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Strategy '{strategy_id}' not found")

    # Build update dict
    update_data = request.model_dump(mode='json', exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        success = await _strategy_repo.update(strategy_id, update_data)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update strategy")

        # Get updated strategy
        updated_strategy = await _strategy_repo.get_by_id(strategy_id)

        # Record history
        if _history_repo:
            await _history_repo.record_change(
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
    if not _strategy_repo:
        raise HTTPException(status_code=503, detail="Strategy repository not initialized")

    # Check if strategy exists
    existing = await _strategy_repo.get_by_id(strategy_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Strategy '{strategy_id}' not found")

    success = await _strategy_repo.delete(strategy_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete strategy")

    # Record history
    if _history_repo:
        await _history_repo.record_change(
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
    if not _strategy_repo:
        raise HTTPException(status_code=503, detail="Strategy repository not initialized")

    # Check if strategy exists
    existing = await _strategy_repo.get_by_id(strategy_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Strategy '{strategy_id}' not found")

    new_status = await _strategy_repo.toggle(strategy_id)
    if new_status is None:
        raise HTTPException(status_code=404, detail=f"Strategy '{strategy_id}' not found")

    # Record history
    if _history_repo:
        await _history_repo.record_change(
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
    if not _symbol_repo:
        raise HTTPException(status_code=503, detail="Symbol repository not initialized")

    if is_active is not None:
        symbols = await _symbol_repo.get_active() if is_active else await _symbol_repo.get_all()
    else:
        symbols = await _symbol_repo.get_all()

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
    if not _symbol_repo:
        raise HTTPException(status_code=503, detail="Symbol repository not initialized")

    try:
        symbol_data = request.model_dump(mode='json')
        # Convert string decimals back to Decimal
        if symbol_data.get("min_quantity"):
            symbol_data["min_quantity"] = Decimal(str(symbol_data["min_quantity"]))

        success = await _symbol_repo.create(symbol_data)

        # Record history
        if _history_repo:
            await _history_repo.record_change(
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
    if not _symbol_repo:
        raise HTTPException(status_code=503, detail="Symbol repository not initialized")

    # Check if symbol exists
    existing = await _symbol_repo.get_by_symbol(symbol)
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

    success = await _symbol_repo.update(symbol, update_data)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update symbol")

    # Get updated symbol
    updated_symbol = await _symbol_repo.get_by_symbol(symbol)

    # Record history
    if _history_repo:
        await _history_repo.record_change(
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
    if not _symbol_repo:
        raise HTTPException(status_code=503, detail="Symbol repository not initialized")

    # Check if symbol exists
    existing = await _symbol_repo.get_by_symbol(symbol)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Symbol '{symbol}' not found")

    new_status = await _symbol_repo.toggle(symbol)
    if new_status is None:
        raise HTTPException(status_code=404, detail=f"Symbol '{symbol}' not found")

    # Record history
    if _history_repo:
        await _history_repo.record_change(
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
    if not _symbol_repo:
        raise HTTPException(status_code=503, detail="Symbol repository not initialized")

    # Check if symbol exists
    existing = await _symbol_repo.get_by_symbol(symbol)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Symbol '{symbol}' not found")

    try:
        success = await _symbol_repo.delete(symbol)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete symbol")

        # Record history
        if _history_repo:
            await _history_repo.record_change(
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
    if not _notification_repo:
        raise HTTPException(status_code=503, detail="Notification repository not initialized")

    # Use get_list method with optional filters
    notifications = await _notification_repo.get_list(is_active=is_active)

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
    if not _notification_repo:
        raise HTTPException(status_code=503, detail="Notification repository not initialized")

    notification_data = request.model_dump(mode='json')
    notification_id = await _notification_repo.create(notification_data)

    # Record history
    if _history_repo:
        await _history_repo.record_change(
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
    if not _notification_repo:
        raise HTTPException(status_code=503, detail="Notification repository not initialized")

    notification = await _notification_repo.get_by_id(notification_id)
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
    if not _notification_repo:
        raise HTTPException(status_code=503, detail="Notification repository not initialized")

    # Check if notification exists
    existing = await _notification_repo.get_by_id(notification_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Notification '{notification_id}' not found")

    # Build update dict
    update_data = request.model_dump(mode='json', exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    success = await _notification_repo.update(notification_id, update_data)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update notification")

    # Get updated notification
    updated_notification = await _notification_repo.get_by_id(notification_id)

    # Record history
    if _history_repo:
        await _history_repo.record_change(
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
    if not _notification_repo:
        raise HTTPException(status_code=503, detail="Notification repository not initialized")

    # Check if notification exists
    existing = await _notification_repo.get_by_id(notification_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Notification '{notification_id}' not found")

    success = await _notification_repo.delete(notification_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete notification")

    # Record history
    if _history_repo:
        await _history_repo.record_change(
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
    if not _notification_repo:
        raise HTTPException(status_code=503, detail="Notification repository not initialized")

    # Check if notification exists
    notification = await _notification_repo.get_by_id(notification_id)
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
# Preview tokens storage (in-memory, expires after 5 minutes)
_import_preview_cache: Dict[str, Dict[str, Any]] = {}


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
    if request.include_risk and _risk_repo:
        risk_data = await _risk_repo.get_global()
        if risk_data:
            export_data["risk"] = risk_data

    # Export system config
    if request.include_system and _system_repo:
        system_data = await _system_repo.get_global()
        if system_data:
            export_data["system"] = system_data

    # Export strategies
    if request.include_strategies and _strategy_repo:
        strategies, _ = await _strategy_repo.get_list(limit=1000, offset=0)
        export_data["strategies"] = strategies

    # Export symbols
    if request.include_symbols and _symbol_repo:
        symbols = await _symbol_repo.get_all()
        export_data["symbols"] = symbols

    # Export notifications
    if request.include_notifications and _notification_repo:
        # TODO: Implement get_all method
        export_data["notifications"] = []

    # Convert Decimals to floats for YAML serialization
    export_data = _convert_decimals_to_float(export_data)

    # Convert to YAML
    yaml_content = yaml.safe_dump(
        export_data,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )

    filename = f"config_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.yaml"

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
                    if _strategy_repo and name:
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
    expires_at = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    expires_at = expires_at.replace(minute=expires_at.minute + 5)  # 5 minutes expiry

    # Store in cache
    _import_preview_cache[preview_token] = {
        "import_data": import_data if valid else None,
        "expires_at": expires_at,
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
        expires_at=expires_at.isoformat(),
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
    # Check preview token
    if request.preview_token not in _import_preview_cache:
        raise HTTPException(status_code=400, detail="Invalid or expired preview token")

    preview_data = _import_preview_cache[request.preview_token]

    # Check expiry
    if datetime.now(timezone.utc) > preview_data["expires_at"]:
        del _import_preview_cache[request.preview_token]
        raise HTTPException(status_code=400, detail="Preview token expired")

    import_data = preview_data.get("import_data")
    if not import_data:
        del _import_preview_cache[request.preview_token]
        raise HTTPException(status_code=400, detail="Preview data not found or invalid")

    snapshot_id = None

    try:
        # Create snapshot before import
        if _snapshot_repo:
            # Convert Decimals to floats for JSON serialization
            import_data_serialized = _convert_decimals_to_float(import_data)
            snapshot = {
                "name": f"Pre-import snapshot ({preview_data['filename']})",
                "description": f"Auto-created before importing {preview_data['filename']}",
                "snapshot_data": import_data_serialized,
                "created_by": "admin",
            }
            snapshot_id = await _snapshot_repo.create(snapshot)

        # Apply import
        # 1. Risk config
        if "risk" in import_data and _risk_repo:
            await _risk_repo.update(import_data["risk"])

        # 2. System config
        if "system" in import_data and _system_repo:
            await _system_repo.update(import_data["system"], restart_required=preview_data["requires_restart"])

        # 3. Strategies
        if "strategies" in import_data and _strategy_repo:
            for strategy in import_data["strategies"]:
                # Convert legacy trigger/filters format to trigger_config/filter_configs
                if "trigger" in strategy and "trigger_config" not in strategy:
                    strategy["trigger_config"] = strategy.pop("trigger")
                if "filters" in strategy and "filter_configs" not in strategy:
                    strategy["filter_configs"] = strategy.pop("filters")
                # Check if exists by name
                # For simplicity, create all as new
                await _strategy_repo.create(strategy)

        # 4. Symbols
        if "symbols" in import_data and _symbol_repo:
            for symbol in import_data["symbols"]:
                try:
                    await _symbol_repo.create(symbol)
                except ConfigConflictError:
                    # Update existing
                    symbol_val = symbol["symbol"]
                    updates = {k: v for k, v in symbol.items() if k != "symbol"}
                    await _symbol_repo.update(symbol_val, updates)

        # 5. Notifications
        if "notifications" in import_data and _notification_repo:
            for notification in import_data["notifications"]:
                await _notification_repo.create(notification)

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
@router.get("/snapshots", response_model=List[SnapshotListItem])
async def get_snapshots(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """获取快照列表"""
    if not _snapshot_repo:
        raise HTTPException(status_code=503, detail="Snapshot repository not initialized")

    # TODO: Implement get_list method in ConfigSnapshotRepository
    # For now, return empty list
    return []


@router.post("/snapshots", status_code=201)
async def create_snapshot(
    request: SnapshotCreateRequest,
    admin: bool = Depends(check_admin_permission)
):
    """创建配置快照"""
    if not _snapshot_repo:
        raise HTTPException(status_code=503, detail="Snapshot repository not initialized")

    # Collect current config
    config_data = {}

    if _risk_repo:
        risk_data = await _risk_repo.get_global()
        if risk_data:
            config_data["risk"] = risk_data

    if _system_repo:
        system_data = await _system_repo.get_global()
        if system_data:
            config_data["system"] = system_data

    if _strategy_repo:
        strategies, _ = await _strategy_repo.get_list(limit=1000, offset=0)
        config_data["strategies"] = strategies

    if _symbol_repo:
        config_data["symbols"] = await _symbol_repo.get_all()

    # Convert Decimals to floats for JSON serialization
    config_data = _convert_decimals_to_float(config_data)

    # Build snapshot dict matching repository signature
    snapshot = {
        "name": request.name,
        "description": request.description,
        "snapshot_data": config_data,
        "created_by": "admin",
    }
    snapshot_id = await _snapshot_repo.create(snapshot)

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
    if not _snapshot_repo:
        raise HTTPException(status_code=503, detail="Snapshot repository not initialized")

    snapshot = await _snapshot_repo.get_by_id(snapshot_id)
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
    if not _snapshot_repo:
        raise HTTPException(status_code=503, detail="Snapshot repository not initialized")

    snapshot = await _snapshot_repo.get_by_id(snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"Snapshot '{snapshot_id}' not found")

    config_data = snapshot.get("config_data", {})
    requires_restart = False

    # Apply config from snapshot
    if "risk" in config_data and _risk_repo:
        await _risk_repo.update(config_data["risk"])

    if "system" in config_data and _system_repo:
        system_config = config_data["system"]
        # Check if restart required
        restart_fields = ["core_symbols", "ema_period", "mtf_ema_period", "mtf_mapping"]
        requires_restart = any(field in system_config for field in restart_fields)
        await _system_repo.update(system_config, restart_required=requires_restart)

    if "strategies" in config_data and _strategy_repo:
        # TODO: Handle strategies restoration
        pass

    if "symbols" in config_data and _symbol_repo:
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
    if not _snapshot_repo:
        raise HTTPException(status_code=503, detail="Snapshot repository not initialized")

    # Check if snapshot exists
    snapshot = await _snapshot_repo.get_by_id(snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"Snapshot '{snapshot_id}' not found")

    success = await _snapshot_repo.delete(snapshot_id)
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
    if not _history_repo:
        raise HTTPException(status_code=503, detail="History repository not initialized")

    # Handle limit=0 case
    if limit == 0:
        return HistoryListResponse(
            items=[],
            total=0,
            limit=limit,
            offset=offset
        )

    items, total = await _history_repo.get_history(
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
    if not _history_repo:
        raise HTTPException(status_code=503, detail="History repository not initialized")

    if not entity_type or not entity_id:
        return []

    candidates = await _history_repo.get_rollback_candidates(
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
    if not _history_repo:
        raise HTTPException(status_code=503, detail="History repository not initialized")

    items = await _history_repo.get_entity_history(
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
    if not _history_repo:
        raise HTTPException(status_code=503, detail="History repository not initialized")

    # Get all history and find the specific one
    # Note: This is inefficient, consider adding get_by_id method to repository
    items, _ = await _history_repo.get_history(limit=1000, offset=0)

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
    if not _history_repo:
        raise HTTPException(status_code=503, detail="History repository not initialized")

    # Get the history record
    items, _ = await _history_repo.get_history(limit=1000, offset=0)
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
        if _risk_repo:
            await _risk_repo.update(values_to_restore)
    elif request.entity_type == "system_config":
        if _system_repo:
            restart_fields = ["core_symbols", "ema_period", "mtf_ema_period", "mtf_mapping"]
            requires_restart = any(field in values_to_restore for field in restart_fields)
            await _system_repo.update(values_to_restore, restart_required=requires_restart)
    elif request.entity_type == "strategy":
        if _strategy_repo:
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
            await _strategy_repo.update(request.entity_id, update_data)
    elif request.entity_type == "symbol":
        if _symbol_repo:
            update_data = {k: v for k, v in values_to_restore.items() if k not in ["symbol", "created_at", "updated_at"]}
            await _symbol_repo.update(request.entity_id, update_data)
    elif request.entity_type == "notification":
        if _notification_repo:
            update_data = {k: v for k, v in values_to_restore.items() if k not in ["id", "created_at", "updated_at"]}
            await _notification_repo.update(request.entity_id, update_data)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported entity type: {request.entity_type}")

    # Record the rollback action in history
    await _history_repo.record_change(
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
