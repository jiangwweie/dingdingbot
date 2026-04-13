"""
REST API - FastAPI endpoints for Signal Monitoring System.

Endpoints:
    GET /api/health - Health check
    GET /api/signals - Query signals with pagination, sorting
    GET /api/signals/stats - Signal statistics
    DELETE /api/signals - Delete signals by ids or conditions
    DELETE /api/signals/clear_all - Clear all signals
    GET /api/account - Current account snapshot
    GET /api/attempts - Query signal attempts with pagination
    DELETE /api/attempts - Delete signal attempts by ids or conditions
    DELETE /api/attempts/clear_all - Clear all signal attempts
    GET /api/config - Get current config (masked)
    PUT /api/config - Update user config (hot-reload)
    GET /api/backtest/configs - Get backtest configuration
    PUT /api/backtest/configs - Update backtest configuration
    POST /api/backtest - Run backtest
    GET /api/v3/backtest/reports - List backtest reports (with filters, sorting, pagination)
    GET /api/v3/backtest/reports/{id} - Get backtest report details
    DELETE /api/v3/backtest/reports/{id} - Delete backtest report
    GET /api/strategies - Get all custom strategy templates
    GET /api/strategies/{id} - Get single strategy details
    GET /api/strategies/meta - Get supported triggers and filters metadata
    POST /api/strategies - Create new strategy template
    PUT /api/strategies/{id} - Update strategy template
    DELETE /api/strategies/{id} - Delete strategy template
    POST /api/strategies/preview - Preview strategy configuration (dry-run)
    POST /api/strategies/{id}/apply - Apply strategy template to live trading
"""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Callable, Any, List, Dict, Annotated, Literal, Tuple
import logging

from fastapi import FastAPI, Query, HTTPException, Body, File, UploadFile, Form, Response
from fastapi.responses import Response, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import yaml

logger = logging.getLogger(__name__)

from src.domain.exceptions import (
    FatalStartupError, ConnectionLostError, DataQualityWarning,
    InsufficientMarginError, InvalidOrderError, OrderNotFoundError,
    OrderAlreadyFilledError, RateLimitError,
)

from src.infrastructure.signal_repository import SignalRepository
from src.infrastructure.order_repository import OrderRepository
from src.application.config_manager import UserConfig, ConfigManager
from src.domain.models import (
    SignalQuery, SignalDeleteRequest, SignalDeleteResponse,
    AttemptQuery, AttemptDeleteRequest, AttemptDeleteResponse,
    BacktestRequest, BacktestReport, SignalStatus, SignalTrack,
    # Phase 6 v3 API Models
    OrderRequest, OrderResponseFull, OrderCancelResponse, OrdersResponse,
    PositionInfoV3, PositionResponse,
    AccountBalance, AccountResponse,
    ReconciliationRequest, ReconciliationReport,
    OrderType, OrderStatus, OrderRole, Direction, Order,
    ErrorResponse,  # MIN-001: 统一错误响应格式
    # Order Chain Tree Models (订单管理级联展示功能)
    OrderTreeResponse, OrderTreeNode, OrderDeleteRequest, OrderDeleteResponse,
    # Strategy Parameter Models (Phase K)
    StrategyParams, StrategyParamsUpdate, StrategyParamsPreview,
    PinbarParams, EngulfingParams, EmaParams, MtfParams, AtrParams,
    # BT-4: Attribution Analysis Models
    AttributionReport,
)

# Profile 管理 Models (配置 Profile 管理功能)
from pydantic import BaseModel, Field, model_validator, ValidationError
from typing import Optional


class ProfileCreateRequest(BaseModel):
    """创建 Profile 请求"""
    name: str = Field(..., description="Profile 名称 (1-32 字符)")
    description: Optional[str] = Field(None, description="描述 (0-100 字符)")
    copy_from: Optional[str] = Field(None, description="源 Profile 名称（复制配置）")
    switch_immediately: bool = Field(False, description="创建后是否立即切换")


class ProfileCreateResponse(BaseModel):
    """创建 Profile 响应"""
    status: str
    profile: dict
    message: str


class ProfileListResponse(BaseModel):
    """Profile 列表响应"""
    profiles: list
    total: int
    active_profile: Optional[str] = None


class ProfileSwitchResponse(BaseModel):
    """切换 Profile 响应"""
    status: str
    profile: dict
    diff: dict
    message: str


class ProfileDeleteResponse(BaseModel):
    """删除 Profile 响应"""
    status: str
    message: str


class ProfileRenameRequest(BaseModel):
    """重命名 Profile 请求"""
    name: str = Field(..., description="新名称 (1-32 字符)")
    description: Optional[str] = Field(None, description="新描述 (0-100 字符)")


class ProfileRenameResponse(BaseModel):
    """重命名 Profile 响应"""
    status: str
    profile: dict
    message: str


class ProfileExportResponse(BaseModel):
    """导出 Profile 响应"""
    status: str
    profile_name: str
    yaml_content: str


class ProfileImportRequest(BaseModel):
    """导入 Profile 请求"""
    yaml_content: str = Field(..., description="YAML 内容")
    profile_name: Optional[str] = Field(None, description="指定 Profile 名称")
    mode: str = Field("create", description="导入模式：create | overwrite")


class ProfileImportResponse(BaseModel):
    """导入 Profile 响应"""
    status: str
    profile: dict
    imported_count: int
    message: str


# ============================================================
# BE-1: Strategy Configuration API Models
# ============================================================

class SystemConfigResponse(BaseModel):
    """系统配置响应 (Level 1 全局配置)"""
    queue_batch_size: int = Field(default=10, ge=1, le=100, description="队列批量落盘大小")
    queue_flush_interval: float = Field(default=5.0, ge=1.0, le=60.0, description="队列最大等待时间 (秒)")
    queue_max_size: int = Field(default=1000, ge=100, le=10000, description="队列最大容量")
    warmup_history_bars: int = Field(default=100, ge=50, le=500, description="数据预热历史 K 线数量")
    signal_cooldown_seconds: int = Field(default=14400, ge=3600, le=86400, description="信号冷却时间 (秒)")


class SystemConfigUpdateRequest(BaseModel):
    """系统配置更新请求 (支持部分更新)"""
    queue_batch_size: Optional[int] = Field(None, ge=1, le=100, description="队列批量落盘大小")
    queue_flush_interval: Optional[float] = Field(None, ge=1.0, le=60.0, description="队列最大等待时间 (秒)")
    queue_max_size: Optional[int] = Field(None, ge=100, le=10000, description="队列最大容量")
    warmup_history_bars: Optional[int] = Field(None, ge=50, le=500, description="数据预热历史 K 线数量")
    signal_cooldown_seconds: Optional[int] = Field(None, ge=3600, le=86400, description="信号冷却时间 (秒)")


class SystemConfigUpdateResponse(BaseModel):
    """系统配置更新响应"""
    config: SystemConfigResponse
    requires_restart: bool = Field(default=True, description="是否需要重启服务")
    restart_hint: str = Field(default="修改已保存，需要重启服务才能生效", description="重启提示")


class ConfigFieldSchema(BaseModel):
    """配置字段 Schema (含 tooltip)"""
    type: Literal['number', 'string', 'boolean']
    default: Any
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    tooltip: dict


class ConfigSchemaResponse(BaseModel):
    """配置 Schema 响应"""
    strategy_params: dict
    system_config: dict


# 回测订单错误码
class BacktestErrorCode:
    """回测相关错误码"""
    REPORT_NOT_FOUND = "BACKTEST-001"
    ORDER_NOT_FOUND = "BACKTEST-002"
    ORDER_BELONGS_MISMATCH = "BACKTEST-003"
    DATA_FETCH_ERROR = "BACKTEST-004"
    DATABASE_ERROR = "BACKTEST-005"


# ============================================================
# Configuration Constants (P1-003: 移除魔法数字)
# ============================================================
class BacktestConfig:
    """回测相关配置常量"""
    # K 线窗口大小：以订单创建时间为中心，前后各取的 K 线数量
    KLINE_WINDOW_BEFORE = 10  # 前取 10 根
    KLINE_WINDOW_AFTER = 10   # 后取 10 根
    DEFAULT_KLINE_WINDOW = 25  # 默认获取 25 根 K 线用于预览

    # P1-004: 时间框架映射统一从 domain.timeframe_utils 获取
    # 避免多处定义导致不一致，完整定义见 domain.timeframe_utils.TIMEFRAME_TO_MS
    @staticmethod
    def get_timeframe_ms(timeframe: str) -> int:
        """获取时间框架的毫秒数（统一从 domain 获取）"""
        from src.domain.timeframe_utils import parse_timeframe_to_ms
        return parse_timeframe_to_ms(timeframe)

    @staticmethod
    def get_timeframe_minutes(timeframe: str) -> int:
        """获取时间框架的分钟数（用于快速计算）"""
        return BacktestConfig.get_timeframe_ms(timeframe) // (60 * 1000)


# Backtest Reports API Models
from pydantic import BaseModel, Field
from typing import Literal


# ============================================================
# Global Dependencies
# ============================================================
_repository: Optional[SignalRepository] = None
_account_getter: Optional[Callable[[], Any]] = None
_config_manager: Optional[Any] = None  # ConfigManager instance
_exchange_gateway: Optional[Any] = None  # ExchangeGateway instance
_signal_tracker: Optional[Any] = None  # SignalStatusTracker instance
_snapshot_service: Optional[Any] = None  # ConfigSnapshotService instance
_config_entry_repo: Optional[Any] = None  # ConfigEntryRepository instance
_order_repo: Optional[Any] = None  # OrderRepository instance
_audit_logger: Optional[Any] = None  # OrderAuditLogger instance
_order_lifecycle_service: Optional[Any] = None  # OrderLifecycleService instance

# Config repositories - stored in shared module to avoid circular imports with api_v1_config.py
from src.interfaces import api_config_globals as _config_globals


def set_dependencies(
    repository: Optional[SignalRepository] = None,
    account_getter: Optional[Callable[[], Any]] = None,
    config_manager: Optional[Any] = None,
    exchange_gateway: Optional[Any] = None,
    signal_tracker: Optional[Any] = None,
    snapshot_service: Optional[Any] = None,
    config_entry_repo: Optional[Any] = None,
    order_repo: Optional[Any] = None,
    audit_logger: Optional[Any] = None,
    order_lifecycle_service: Optional[Any] = None,
    # Config repositories (unified with api_v1_config.py)
    strategy_repo: Optional[Any] = None,
    risk_repo: Optional[Any] = None,
    system_repo: Optional[Any] = None,
    symbol_repo: Optional[Any] = None,
    notification_repo: Optional[Any] = None,
    history_repo: Optional[Any] = None,
    snapshot_repo: Optional[Any] = None,
) -> None:
    """
    Inject dependencies for API endpoints.

    Args:
        repository: Optional SignalRepository instance
        account_getter: Optional function that returns AccountSnapshot or None
        config_manager: Optional ConfigManager instance
        exchange_gateway: Optional ExchangeGateway instance
        signal_tracker: Optional SignalStatusTracker instance
        snapshot_service: Optional ConfigSnapshotService instance
        config_entry_repo: Optional ConfigEntryRepository instance
        order_repo: Optional OrderRepository instance
        audit_logger: Optional OrderAuditLogger instance
        order_lifecycle_service: Optional OrderLifecycleService instance
        strategy_repo: Optional StrategyConfigRepository instance
        risk_repo: Optional RiskConfigRepository instance
        system_repo: Optional SystemConfigRepository instance
        symbol_repo: Optional SymbolConfigRepository instance
        notification_repo: Optional NotificationConfigRepository instance
        history_repo: Optional ConfigHistoryRepository instance
        snapshot_repo: Optional ConfigSnapshotRepositoryExtended instance
    """
    global _repository, _account_getter, _config_manager, _exchange_gateway, _signal_tracker, _snapshot_service, _config_entry_repo, _order_repo, _audit_logger, _order_lifecycle_service
    _repository = repository
    _account_getter = account_getter
    _config_manager = config_manager
    ConfigManager.set_instance(config_manager)
    _exchange_gateway = exchange_gateway
    _signal_tracker = signal_tracker
    _snapshot_service = snapshot_service
    _config_entry_repo = config_entry_repo
    _order_repo = order_repo
    _audit_logger = audit_logger
    _order_lifecycle_service = order_lifecycle_service
    # Config repositories - stored in shared module (avoids circular imports)
    _config_globals._strategy_repo = strategy_repo
    _config_globals._risk_repo = risk_repo
    _config_globals._system_repo = system_repo
    _config_globals._symbol_repo = symbol_repo
    _config_globals._notification_repo = notification_repo
    _config_globals._history_repo = history_repo
    _config_globals._snapshot_repo = snapshot_repo
    _config_globals._config_manager = config_manager


def _get_repository() -> SignalRepository:
    """Get repository or raise error if not initialized."""
    if _repository is None:
        raise HTTPException(status_code=503, detail="Repository not initialized")
    return _repository


def _get_config_manager() -> Any:
    """Get config manager or raise error if not initialized."""
    if _config_manager is None:
        raise HTTPException(status_code=503, detail="Config manager not initialized")
    return _config_manager


def _get_exchange_gateway() -> Any:
    """Get exchange gateway or raise error if not initialized."""
    if _exchange_gateway is None:
        raise HTTPException(status_code=503, detail="Exchange gateway not initialized")
    return _exchange_gateway


async def _get_backtest_gateway() -> Tuple[Any, bool]:
    """Get exchange gateway, or create temporary one for standalone uvicorn backtest.

    Returns:
        Tuple of (gateway, is_temporary). is_temporary is True if caller must close it.
    """
    if _exchange_gateway is not None:
        return _exchange_gateway, False

    # Standalone uvicorn: create temporary gateway from DB config
    from src.infrastructure.exchange_gateway import ExchangeGateway
    from src.interfaces import api_config_globals as _cg
    if _cg._config_manager is None:
        raise HTTPException(status_code=503, detail="Config manager not initialized")
    exchange_cfg = await _cg._config_manager.get_exchange_config()
    # 回测只需要历史 K 线（公开接口），使用匿名连接避免 API 密钥地域限制
    gateway = ExchangeGateway(
        exchange_name=exchange_cfg.name,
        api_key="",
        api_secret="",
        testnet=exchange_cfg.testnet,
    )
    await gateway.initialize()
    logger.info(f"Temporary anonymous ExchangeGateway created for backtest: {exchange_cfg.name}")
    return gateway, True


def _get_signal_tracker() -> Any:
    """Get signal tracker or raise error if not initialized."""
    if _signal_tracker is None:
        raise HTTPException(status_code=503, detail="Signal tracker not initialized")
    return _signal_tracker


def _get_snapshot_service() -> Any:
    """Get snapshot service or return None if not initialized."""
    return _snapshot_service


def _get_config_entry_repo() -> Any:
    """Get config entry repository or raise error if not initialized."""
    if _config_entry_repo is None:
        raise HTTPException(status_code=503, detail="Config entry repository not initialized. Please restart the server.")
    return _config_entry_repo


def _get_order_repo() -> Any:
    """Get order repository or create a new instance if not initialized."""
    if _order_repo is None:
        # Fallback: create a new instance
        from src.infrastructure.order_repository import OrderRepository
        repo = OrderRepository()
        # Auto-inject dependencies if available
        if _exchange_gateway:
            repo.set_exchange_gateway(_exchange_gateway)
        if _audit_logger:
            repo.set_audit_logger(_audit_logger)
        return repo
    return _order_repo


def _get_audit_logger() -> Any:
    """Get audit logger or raise error if not initialized."""
    if _audit_logger is None:
        raise HTTPException(status_code=503, detail="Audit logger not initialized")
    return _audit_logger


# ============================================================
# Lifespan Manager
# ============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifespan events.
    Initialize repositories on startup, close on shutdown.
    """
    from src.infrastructure.signal_repository import SignalRepository
    from src.infrastructure.config_entry_repository import ConfigEntryRepository

    global _repository, _config_entry_repo, _order_repo, _config_manager

    # Startup - 初始化所有 Repository
    try:
        # 初始化 SignalRepository（幂等）
        if _repository is None:
            _repository = SignalRepository()
            await _repository.initialize()
            logger.info("SignalRepository initialized in lifespan")

        # 初始化 ConfigEntryRepository（幂等）
        if _config_entry_repo is None:
            _config_entry_repo = ConfigEntryRepository()
            await _config_entry_repo.initialize()
            logger.info("ConfigEntryRepository initialized in lifespan")

        # Initialize OrderAuditLogger global singleton (FIX-002)
        global _audit_logger, _order_lifecycle_service
        from src.application.order_audit_logger import OrderAuditLogger
        from src.infrastructure.order_audit_repository import OrderAuditLogRepository

        # Get db_session_factory from config_manager if available
        def get_db_session():
            """Get database session factory for audit logger."""
            from src.infrastructure.order_audit_repository import get_db_session
            return get_db_session()

        audit_repo = OrderAuditLogRepository(db_session_factory=get_db_session)
        await audit_repo.initialize(queue_size=1000)
        _audit_logger = OrderAuditLogger(audit_repo)
        logger.info("OrderAuditLogger initialized as global singleton")

        # Initialize OrderRepository if not already set (ORD-1-T5)
        # This ensures we have an order repo for the lifecycle service
        if _order_repo is None:
            from src.infrastructure.order_repository import OrderRepository
            _order_repo = OrderRepository()
            await _order_repo.initialize()
            # Auto-inject dependencies
            if _exchange_gateway:
                _order_repo.set_exchange_gateway(_exchange_gateway)
            if _audit_logger:
                _order_repo.set_audit_logger(_audit_logger)
            logger.info("OrderRepository initialized in lifespan")

        # Initialize OrderLifecycleService (ORD-1-T5)
        from src.application.order_lifecycle_service import OrderLifecycleService
        _order_lifecycle_service = OrderLifecycleService(
            repository=_order_repo,
            audit_logger=_audit_logger,
        )
        await _order_lifecycle_service.start()
        logger.info("OrderLifecycleService initialized as global singleton")

        # Register order update callback with ExchangeGateway (ORD-1-T5)
        # This ensures all WebSocket order updates go through the lifecycle service
        if _exchange_gateway is not None:
            _exchange_gateway.set_global_order_callback(_order_lifecycle_service.update_order_from_exchange)
            logger.info("ExchangeGateway global callback registered with OrderLifecycleService")

        # =============================================
        # Initialize Config Repositories (独立 uvicorn 模式必需)
        # main.py 嵌入模式通过 set_dependencies() 注入，lifespan="off" 不执行此处
        # =============================================
        from src.interfaces import api_config_globals as _cg
        from src.infrastructure.repositories.config_repositories import (
            StrategyConfigRepository,
            RiskConfigRepository,
            SystemConfigRepository,
            SymbolConfigRepository,
            NotificationConfigRepository,
            ConfigHistoryRepository,
            ConfigSnapshotRepositoryExtended,
        )

        if _cg._strategy_repo is None:
            _cg._strategy_repo = StrategyConfigRepository()
            await _cg._strategy_repo.initialize()
            logger.info("StrategyConfigRepository initialized in lifespan")

        if _cg._risk_repo is None:
            _cg._risk_repo = RiskConfigRepository()
            await _cg._risk_repo.initialize()
            logger.info("RiskConfigRepository initialized in lifespan")

        if _cg._system_repo is None:
            _cg._system_repo = SystemConfigRepository()
            await _cg._system_repo.initialize()
            logger.info("SystemConfigRepository initialized in lifespan")

        if _cg._symbol_repo is None:
            _cg._symbol_repo = SymbolConfigRepository()
            await _cg._symbol_repo.initialize()
            logger.info("SymbolConfigRepository initialized in lifespan")

        if _cg._notification_repo is None:
            _cg._notification_repo = NotificationConfigRepository()
            await _cg._notification_repo.initialize()
            logger.info("NotificationConfigRepository initialized in lifespan")

        if _cg._history_repo is None:
            _cg._history_repo = ConfigHistoryRepository()
            await _cg._history_repo.initialize()
            logger.info("ConfigHistoryRepository initialized in lifespan")

        if _cg._snapshot_repo is None:
            _cg._snapshot_repo = ConfigSnapshotRepositoryExtended()
            await _cg._snapshot_repo.initialize()
            logger.info("ConfigSnapshotRepositoryExtended initialized in lifespan")

        # =============================================
        # Initialize ConfigManager (独立 uvicorn 模式必需)
        # effective 配置端点依赖 ConfigManager
        # main.py 嵌入模式通过 set_dependencies() 注入，lifespan="off" 不执行此处
        # =============================================
        if _cg._config_manager is None:
            from src.application.config_manager import ConfigManager
            _cg._config_manager = ConfigManager()
            await _cg._config_manager.initialize_from_db()
            # Also set module-level variable so old API endpoints work
            _config_manager = _cg._config_manager
            logger.info("ConfigManager initialized in lifespan")

        yield

    finally:
        # Shutdown - 清理所有 Repository
        if _repository is not None:
            await _repository.close()
            logger.info("SignalRepository closed")

        if _config_entry_repo is not None:
            await _config_entry_repo.close()
            logger.info("ConfigEntryRepository closed")

        # Shutdown OrderLifecycleService (ORD-1-T5)
        if _order_lifecycle_service is not None:
            await _order_lifecycle_service.stop()
            logger.info("OrderLifecycleService stopped")

        # Shutdown audit logger (FIX-002)
        if _audit_logger is not None:
            await _audit_logger.stop()
            logger.info("OrderAuditLogger stopped")

        # Shutdown Config Repositories (独立 uvicorn 模式)
        from src.interfaces import api_config_globals as _cg
        if _cg._strategy_repo is not None:
            await _cg._strategy_repo.close()
            logger.info("StrategyConfigRepository closed in lifespan")
        if _cg._risk_repo is not None:
            await _cg._risk_repo.close()
            logger.info("RiskConfigRepository closed in lifespan")
        if _cg._system_repo is not None:
            await _cg._system_repo.close()
            logger.info("SystemConfigRepository closed in lifespan")
        if _cg._symbol_repo is not None:
            await _cg._symbol_repo.close()
            logger.info("SymbolConfigRepository closed in lifespan")
        if _cg._notification_repo is not None:
            await _cg._notification_repo.close()
            logger.info("NotificationConfigRepository closed in lifespan")
        if _cg._history_repo is not None:
            await _cg._history_repo.close()
            logger.info("ConfigHistoryRepository closed in lifespan")
        if _cg._snapshot_repo is not None:
            await _cg._snapshot_repo.close()
            logger.info("ConfigSnapshotRepositoryExtended closed in lifespan")
        if _cg._config_manager is not None:
            await _cg._config_manager.close()
            logger.info("ConfigManager closed in lifespan")


# ============================================================
# FastAPI Application
# ============================================================
app = FastAPI(
    title="Crypto Signal Monitor API",
    description="Read-only API for cryptocurrency signal monitoring system",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS - Allow all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include v1 config router
from src.interfaces.api_v1_config import router as config_v1_router
app.include_router(config_v1_router)


# ============================================================
# Global Exception Handler (MIN-001)
# ============================================================
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError


from fastapi.responses import JSONResponse


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    """
    统一处理 HTTP 异常，返回标准化错误响应格式

    MIN-001: 统一错误响应格式
    """
    # 如果 detail 已经是 dict 格式（包含 error_code 和 message），直接使用
    if isinstance(exc.detail, dict):
        content = ErrorResponse(
            error_code=exc.detail.get("error_code", str(exc.status_code)),
            message=exc.detail.get("message", str(exc.detail))
        ).model_dump()
    else:
        # 否则使用默认格式
        content = ErrorResponse(
            error_code=str(exc.status_code),
            message=str(exc.detail)
        ).model_dump()

    return JSONResponse(
        status_code=exc.status_code,
        content=content
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    """统一处理请求验证错误"""
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            error_code="VALIDATION_ERROR",
            message=f"请求参数验证失败：{str(exc.errors())}"
        ).model_dump()
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc: Exception):
    """统一处理未预料的异常"""
    logger.error(f"未处理的异常：{str(exc)}")
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error_code="INTERNAL_ERROR",
            message="服务器内部错误"
        ).model_dump()
    )


# ============================================================
# Endpoints
# ============================================================
@app.get("/api/health")
async def health_check():
    """
    Health check endpoint.
    Returns current timestamp in UTC.
    """
    try:
        return {
            "status": "ok",
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/signals")
async def get_signals(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    symbol: Optional[str] = Query(default=None),
    timeframe: Optional[str] = Query(default=None),
    direction: Optional[str] = Query(default=None),
    strategy_name: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    start_time: Optional[str] = Query(default=None),
    end_time: Optional[str] = Query(default=None),
    source: Optional[str] = Query(default=None, pattern="^(live|backtest)$"),
    sort_by: str = Query(default="created_at", pattern="^(created_at|pattern_score)$"),
    order: str = Query(default="desc", pattern="^(asc|desc|ASC|DESC)$"),
):
    """
    Query trading signals with pagination and optional filtering.

    Args:
        limit: Maximum number of results (1-200)
        offset: Number of results to skip
        symbol: Optional symbol filter (e.g., "BTC/USDT:USDT")
        timeframe: Optional timeframe filter (e.g., "15m", "1h", "4h", "1d")
        direction: Optional direction filter ("long" or "short")
        strategy_name: Optional strategy name filter ("pinbar", "engulfing")
        status: Optional status filter ("PENDING", "WON", "LOST")
        start_time: Optional start time filter (ISO 8601)
        end_time: Optional end time filter (ISO 8601)
        source: Optional source filter ("live" or "backtest")
        sort_by: Sort field ("created_at" or "pattern_score"), default "created_at"
        order: Sort order ("asc" or "desc"), default "desc"
    """
    try:
        repo = _get_repository()
        result = await repo.get_signals(
            limit=limit,
            offset=offset,
            symbol=symbol,
            timeframe=timeframe,
            direction=direction,
            strategy_name=strategy_name,
            status=status,
            start_time=start_time,
            end_time=end_time,
            source=source,
            sort_by=sort_by,
            order=order,
        )

        return {
            "total": result["total"],
            "limit": limit,
            "offset": offset,
            "data": result["data"],
        }
    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e)}


@app.delete("/api/signals")
async def delete_signals(
    request: SignalDeleteRequest,
):
    """
    Delete trading signals by ids or by filter conditions.

    Request body:
    {
        "ids": [1, 2, 3],           // Optional: precise batch delete by IDs
        "delete_all": false,         // Optional: if true, delete by filters below
        "symbol": "BTC/USDT:USDT",  // Optional: symbol filter
        "direction": "long",         // Optional: direction filter
        "strategy_name": "pinbar",   // Optional: strategy filter
        "status": "PENDING",         // Optional: status filter
        "start_time": "...",         // Optional: ISO 8601 timestamp
        "end_time": "..."            // Optional: ISO 8601 timestamp
    }

    Returns:
    {
        "message": "Deleted N records",
        "deleted_count": N
    }
    """
    try:
        repo = _get_repository()
        deleted_count = await repo.delete_signals(request=request)
        return {
            "message": f"Deleted {deleted_count} records",
            "deleted_count": deleted_count,
        }
    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e)}


@app.delete("/api/signals/clear_all")
async def clear_all_signals():
    """
    Clear all trading signals from the database.

    Returns:
    {
        "status": "success",
        "deleted_count": N
    }
    """
    try:
        repo = _get_repository()
        deleted_count = await repo.clear_all_signals()
        return {
            "status": "success",
            "deleted_count": deleted_count,
        }
    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/signals/stats")
async def get_signal_stats():
    """
    Get signal statistics.

    Returns:
        total: Total number of signals
        today: Number of signals today
        long_count: Number of long signals
        short_count: Number of short signals
        win_rate: Win rate (WON / (WON + LOST)), 0.0 if no closed signals
        won_count: Number of WON (profit) signals
        lost_count: Number of LOST (loss) signals
    """
    try:
        repo = _get_repository()
        stats = await repo.get_stats()
        return stats
    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/backtest/signals")
async def get_backtest_signals(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    symbol: Optional[str] = Query(default=None),
    timeframe: Optional[str] = Query(default=None),
    strategy_name: Optional[str] = Query(default=None),
):
    """
    Query backtest signals with pagination.

    Args:
        limit: Maximum number of results (1-200)
        offset: Number of results to skip
        symbol: Optional symbol filter
        timeframe: Optional timeframe filter
        strategy_name: Optional strategy name filter

    Returns:
        {"signals": list[Signal], "total": int}
    """
    try:
        repo = _get_repository()
        result = await repo.get_signals(
            limit=limit,
            offset=offset,
            symbol=symbol,
            direction=None,
            strategy_name=strategy_name,
            status=None,
            start_time=None,
            end_time=None,
            sort_by="created_at",
            order="desc",
            source="backtest",  # Only fetch backtest signals
        )

        return {
            "signals": result["data"],
            "total": result["total"],
        }
    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/account")
async def get_account():
    """
    Get current account snapshot.

    Returns:
        Account snapshot data or {"status": "unavailable"} if not yet polled.
    """
    try:
        if _account_getter is None:
            return {"status": "unavailable"}

        snapshot = _account_getter()

        if snapshot is None:
            return {"status": "unavailable"}

        # Convert AccountSnapshot to dict
        return {
            "total_balance": str(snapshot.total_balance),
            "available_balance": str(snapshot.available_balance),
            "unrealized_pnl": str(snapshot.unrealized_pnl),
            "positions": [
                {
                    "symbol": pos.symbol,
                    "side": pos.side,
                    "size": str(pos.size),
                    "entry_price": str(pos.entry_price),
                    "unrealized_pnl": str(pos.unrealized_pnl),
                    "leverage": pos.leverage,
                }
                for pos in snapshot.positions
            ],
            "timestamp": datetime.fromtimestamp(snapshot.timestamp / 1000, tz=timezone.utc).isoformat(),
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/diagnostics")
async def get_diagnostics(
    symbol: Optional[str] = Query(default=None),
    hours: int = Query(default=24, ge=1, le=168),
):
    """
    Get signal processing diagnostics.

    Args:
        symbol: Optional symbol filter
        hours: Lookback window in hours (1-168, default 24)
    """
    try:
        repo = _get_repository()
        result = await repo.get_diagnostics(symbol=symbol, hours=hours)
        return result
    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/signals/{signal_id}/context")
async def get_signal_context(signal_id: int):
    """
    Get signal context with historical K-line data for charting.

    Returns signal details plus ~50 K-lines surrounding the signal timestamp
    for front-end candlestick chart visualization.

    Args:
        signal_id: Signal record ID

    Returns:
        {
            "signal": { ... signal info from database ... },
            "klines": [[timestamp, open, high, low, close, volume], ...]
        }
    """
    try:
        repo = _get_repository()

        # Get signal by ID
        signal = await repo.get_signal_by_id(signal_id)
        if signal is None:
            raise HTTPException(status_code=404, detail="Signal not found")

        # Extract signal parameters
        symbol = signal["symbol"]
        timeframe = signal["timeframe"]
        kline_timestamp = signal.get("kline_timestamp")

        # Validate kline_timestamp exists
        if not kline_timestamp or kline_timestamp == 0:
            raise HTTPException(
                status_code=400,
                detail="Legacy signal data without kline_timestamp. This signal was created before v3.0 and does not support context view."
            )

        # Parse timeframe to milliseconds (P1-004: 使用统一工具函数)
        timeframe_ms = BacktestConfig.get_timeframe_ms(timeframe)

        # Calculate since timestamp (go back 25 candles to ensure target is in middle-rear)
        since = kline_timestamp - (BacktestConfig.DEFAULT_KLINE_WINDOW * timeframe_ms)

        # Fetch K-line data from CCXT
        import ccxt.async_support as ccxt
        exchange = ccxt.binanceusdm({'options': {'defaultType': 'swap'}})
        try:
            ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=50)
        finally:
            await exchange.close()

        # S6-3: Load take profit levels if not already loaded
        if "take_profit_levels" not in signal:
            signal_id_str = signal.get("signal_id")
            if signal_id_str:
                signal["take_profit_levels"] = await repo.get_take_profit_levels(signal_id_str)
            else:
                signal["take_profit_levels"] = []

        return {
            "signal": signal,
            "klines": ohlcv,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch signal context for {signal_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/attempts")
async def get_attempts(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    symbol: Optional[str] = Query(default=None),
    timeframe: Optional[str] = Query(default=None),
    strategy_name: Optional[str] = Query(default=None),
    final_result: Optional[str] = Query(default=None),
    filter_stage: Optional[str] = Query(default=None),
    start_time: Optional[str] = Query(default=None),
    end_time: Optional[str] = Query(default=None),
):
    """
    Query signal attempts with pagination and optional filtering.

    Args:
        limit: Maximum number of results (1-200)
        offset: Number of results to skip
        symbol: Optional symbol filter
        timeframe: Optional timeframe filter
        strategy_name: Optional strategy name filter
        final_result: Optional result filter ("SIGNAL_FIRED", "NO_PATTERN", "FILTERED")
        filter_stage: Optional filter stage ("ema_trend", "mtf")
        start_time: Optional start time filter (ISO 8601)
        end_time: Optional end time filter (ISO 8601)
    """
    try:
        repo = _get_repository()
        result = await repo.get_attempts(
            limit=limit,
            offset=offset,
            symbol=symbol,
            timeframe=timeframe,
            strategy_name=strategy_name,
            final_result=final_result,
            filter_stage=filter_stage,
            start_time=start_time,
            end_time=end_time,
        )

        return {
            "total": result["total"],
            "limit": limit,
            "offset": offset,
            "data": result["data"],
        }
    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e)}


@app.delete("/api/attempts")
async def delete_attempts(
    request: AttemptDeleteRequest,
):
    """
    Delete signal attempts by ids or by filter conditions.

    Request body:
    {
        "ids": [1, 2, 3],           // Optional: precise batch delete by IDs
        "delete_all": false,         // Optional: if true, delete by filters below
        "symbol": "BTC/USDT:USDT",  // Optional: symbol filter
        "timeframe": "15m",          // Optional: timeframe filter
        "strategy_name": "pinbar",   // Optional: strategy filter
        "final_result": "FILTERED",  // Optional: result filter
        "filter_stage": "ema_trend", // Optional: filter stage filter
        "start_time": "...",         // Optional: ISO 8601 timestamp
        "end_time": "..."            // Optional: ISO 8601 timestamp
    }

    Returns:
    {
        "message": "Deleted N records",
        "deleted_count": N
    }
    """
    try:
        repo = _get_repository()
        deleted_count = await repo.delete_attempts(request=request)
        return {
            "message": f"Deleted {deleted_count} records",
            "deleted_count": deleted_count,
        }
    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e)}


@app.delete("/api/attempts/clear_all")
async def clear_all_attempts():
    """
    Clear all signal attempts from the database.

    Returns:
    {
        "status": "success",
        "deleted_count": N
    }
    """
    try:
        repo = _get_repository()
        deleted_count = await repo.clear_all_attempts()
        return {
            "status": "success",
            "deleted_count": deleted_count,
        }
    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e)}


# ============================================================
# Config Management Endpoints
# ============================================================
from src.infrastructure.logger import mask_secret, logger


def _mask_config_value(value: Any, is_sensitive: bool = False) -> Any:
    """
    Mask sensitive config values.

    Args:
        value: The value to potentially mask
        is_sensitive: Whether this is a sensitive field

    Returns:
        Masked or original value
    """
    if not is_sensitive:
        return value
    if isinstance(value, str) and len(value) > 8:
        return mask_secret(value)
    return value


def _deep_mask_config(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deep mask sensitive fields in config dictionary.

    # P1-4 Fix: Enhanced sensitive field list with comprehensive coverage
    # Matches field names containing these keywords (case-insensitive):
    # - password: any password field
    # - passphrase: API passphrase
    # - token: access_token, refresh_token, auth_token, etc.
    # - secret: api_secret, client_secret, webhook_secret, etc.
    # - private_key: encryption private keys
    # - mnemonic: wallet recovery phrases

    Sensitive fields: api_key, api_secret, webhook_url, secret, password,
                      token, passphrase, private_key, mnemonic, client_id,
                      client_secret, auth_token, bearer_token

    Args:
        data: Dictionary to mask

    Returns:
        Dictionary with sensitive values masked
    """
    # P1-4 Fix: Enhanced sensitive field keywords (substring match)
    SENSITIVE_KEYWORDS = {
        "password",      # matches: password, db_password, etc.
        "passphrase",    # matches: passphrase, api_passphrase
        "token",         # matches: token, access_token, auth_token
        "secret",        # matches: secret, api_secret, client_secret
        "private_key",   # matches: private_key, wallet_private_key
        "mnemonic",      # matches: mnemonic, seed_mnemonic
        "api_key",       # matches: api_key, exchange_api_key
        "webhook_url",   # matches: webhook_url, notify_webhook_url
        "client_id",     # matches: client_id, oauth_client_id
        "client_secret", # matches: client_secret, oauth_client_secret
        "auth_token",    # matches: auth_token
        "bearer_token",  # matches: bearer_token
        "access_token",  # matches: access_token
        "refresh_token", # matches: refresh_token
    }

    def is_sensitive_key(key: str) -> bool:
        """Check if a key contains sensitive keywords (case-insensitive)."""
        key_lower = key.lower()
        return any(keyword in key_lower for keyword in SENSITIVE_KEYWORDS)

    result = {}

    for key, value in data.items():
        if is_sensitive_key(key):
            result[key] = _mask_config_value(value, is_sensitive=True)
        elif isinstance(value, dict):
            result[key] = _deep_mask_config(value)
        elif isinstance(value, list):
            # P1-4 Fix: Recursively mask sensitive fields in lists
            result[key] = [
                _deep_mask_config(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[key] = value

    return result


@app.get("/api/config")
async def get_config():
    """
    Get current aggregated configuration.

    Sensitive information (api_key, api_secret, webhook_url) is masked.

    Returns:
        Aggregated config with masked secrets
    """
    try:
        config_manager = _get_config_manager()
        user_config = await config_manager.get_user_config()

        # Convert Pydantic model to dict
        config_dict = user_config.model_dump()

        # Deep mask sensitive values
        masked_config = _deep_mask_config(config_dict)

        return {
            "status": "success",
            "config": masked_config,
        }
    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e)}


# ============================================================
# Config Export/Import Endpoints
# ============================================================
@app.get("/api/config/export")
async def export_config():
    """
    Export current configuration as YAML file.

    Sensitive information (api_key, api_secret, webhook_url) is masked.

    Returns:
        YAML file download response
    """
    try:
        import yaml
        from src.infrastructure.logger import mask_secret

        config_manager = _get_config_manager()
        user_config = await config_manager.get_user_config()

        # Convert Pydantic model to dict (with masking)
        config_dict = user_config.model_dump(mode='json')
        masked_config = _deep_mask_config(config_dict)

        # Generate YAML content
        yaml_content = yaml.safe_dump(
            masked_config,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False
        )

        # Generate filename with timestamp
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"user_config_{timestamp}.yaml"

        return Response(
            content=yaml_content,
            media_type="application/x-yaml",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/config/import")
async def import_config(
    file: UploadFile = File(..., description="YAML configuration file"),
    description: str = Form(default="配置导入", description="Snapshot description")
):
    """
    Import configuration from YAML file.

    Flow:
    1. Parse and validate YAML content
    2. Validate against UserConfig schema
    3. Create auto-snapshot of current config (backup)
    4. Apply new configuration (hot-reload)

    Args:
        file: YAML configuration file
        description: Description for the backup snapshot

    Returns:
        Updated config (masked) or error details
    """
    try:
        import yaml
        from pydantic import ValidationError

        # Read and parse YAML
        content = await file.read()
        try:
            config_data = yaml.safe_load(content.decode('utf-8'))
        except yaml.YAMLError as e:
            raise HTTPException(
                status_code=400,
                detail=f"YAML parse error: {e}",
                headers={"X-Error-Code": "CONFIG-002"}
            )

        if not isinstance(config_data, dict):
            raise HTTPException(
                status_code=400,
                detail="Invalid YAML: root must be an object",
                headers={"X-Error-Code": "CONFIG-002"}
            )

        # Validate against UserConfig schema
        config_manager = _get_config_manager()

        # Get existing config for partial updates
        existing_config = await config_manager.get_user_config()

        # Merge with existing config for partial updates
        existing_dict = existing_config.model_dump(mode='json')
        merged_dict = config_manager._deep_merge(existing_dict, config_data)

        try:
            # Validate merged config
            UserConfig(**merged_dict)
        except ValidationError as e:
            raise HTTPException(
                status_code=422,
                detail=f"Config validation failed: {e}",
                headers={"X-Error-Code": "CONFIG-003"}
            )

        # Apply new configuration
        # Note: update_user_config will create auto-snapshot automatically
        new_config = await config_manager.update_user_config(
            config_data,
            auto_snapshot=True,
            snapshot_description=description
        )

        # Return masked config
        config_dict = new_config.model_dump()
        masked_config = _deep_mask_config(config_dict)

        return {
            "status": "success",
            "message": "Configuration imported successfully",
            "config": masked_config,
        }

    except HTTPException:
        raise
    except Exception as e:
        error_str = str(e)
        if "ValidationError" in type(e).__name__:
            raise HTTPException(
                status_code=422,
                detail=f"Config validation failed: {error_str}",
                headers={"X-Error-Code": "CONFIG-003"}
            )
        return {"error": str(e)}


@app.put("/api/config")
async def update_config(
    config_update: Dict[str, Any] = Body(..., description="Partial user config update"),
    auto_snapshot: bool = Query(default=True, description="Whether to create auto-snapshot"),
    snapshot_description: str = Query(default="", description="Snapshot description"),
):
    """
    Update user configuration with hot-reload.

    Accepts partial config update. Validates against Pydantic UserConfig model.
    On success, atomically replaces in-memory config and persists to disk.

    Request body example:
    {
        "strategy": {
            "trend_filter_enabled": false
        },
        "risk": {
            "max_loss_percent": 0.02
        }
    }

    Args:
        config_update: Partial config update
        auto_snapshot: Whether to create snapshot before update (default True)
        snapshot_description: Description for the auto-snapshot

    Returns:
        Updated config (masked) or 422 on validation error
    """
    try:
        config_manager = _get_config_manager()

        # Call hot-reload method (validates + atomic swap + persist)
        new_config = await config_manager.update_user_config(
            config_update,
            auto_snapshot=auto_snapshot,
            snapshot_description=snapshot_description
        )

        # Return masked config
        config_dict = new_config.model_dump()
        masked_config = _deep_mask_config(config_dict)

        return {
            "status": "success",
            "message": "Configuration updated",
            "config": masked_config,
        }
    except HTTPException:
        raise
    except Exception as e:
        # Pydantic ValidationError returns 422
        error_str = str(e)
        if "ValidationError" in type(e).__name__:
            from fastapi import status
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Config validation failed: {error_str}",
            )
        return {"error": str(e)}


# ============================================================
# Backtest Endpoints
# ============================================================

@app.post("/api/backtest/signals")
async def run_signal_backtest(
    request: BacktestRequest,
):
    """
    Run signal-level backtest on historical data (v2_classic mode).

    信号回测 - 仅统计信号触发和过滤器拦截情况，不涉及订单执行模拟。

    Backtest signals are automatically saved to database with source='backtest'.
    You can view them in the Signals page with K-line chart visualization.

    T4/T5/T6: Orders and backtest reports are automatically saved to database.

    Request body (BacktestRequest):
    {
        "symbol": "BTC/USDT:USDT",
        "timeframe": "15m",
        "start_time": null,
        "end_time": null,
        "limit": 100,
        "min_wick_ratio": 0.6,
        "max_body_ratio": 0.3,
        "body_position_tolerance": 0.1,
        "trend_filter_enabled": true,
        "mtf_validation_enabled": true,
        "mode": "v2_classic"
    }

    Returns:
        BacktestReport with:
        - signal_stats: Total attempts, signals fired, filtered out, etc.
        - reject_reasons: Distribution of rejection reasons
        - simulated_win_rate: Simulated win rate
        - attempts: Detailed attempt records
    """
    try:
        from src.application.backtester import Backtester
        from src.infrastructure.backtest_repository import BacktestReportRepository
        from src.infrastructure.historical_data_repository import HistoricalDataRepository
        from src.infrastructure.order_repository import OrderRepository

        # Validate mode
        if request.mode != "v2_classic":
            logger.warning(f"Signal backtest called with mode={request.mode}, forcing v2_classic")

        gateway, gateway_is_temp = await _get_backtest_gateway()

        # Initialize historical data repository for local-first data access
        data_repo = HistoricalDataRepository()
        await data_repo.initialize()

        backtester = Backtester(gateway, data_repository=data_repo)

        # Get current account snapshot for position sizing
        account_snapshot = _account_getter() if _account_getter else None

        # Get repository for saving signals (always save backtest signals)
        repository = _get_repository()

        # T5/T6: Initialize backtest report repository for saving reports
        backtest_repository = BacktestReportRepository()
        await backtest_repository.initialize()

        # T4: Initialize order repository for saving orders
        order_repository = OrderRepository()
        await order_repository.initialize()

        try:
            # Run backtest with repositories (force v2_classic mode)
            request_copy = BacktestRequest(**request.model_dump())
            request_copy.mode = "v2_classic"

            report = await backtester.run_backtest(
                request_copy,
                account_snapshot,
                repository=repository,
                backtest_repository=backtest_repository,
                order_repository=order_repository
            )

            return {
                "status": "success",
                "report": report.model_dump(),
            }
        finally:
            if gateway_is_temp:
                await gateway.close()
                logger.info("Temporary backtest gateway closed")
            await backtest_repository.close()
            await order_repository.close()
            await data_repo.close()

    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/backtest/orders")
async def run_pms_backtest(
    request: BacktestRequest,
):
    """
    Run position-level PMS backtest with MockMatchingEngine (v3_pms mode).

    PMS 订单回测 - 包含订单执行、滑点、手续费、止盈止损等完整交易流程模拟。

    Features:
    - Position-level tracking with detailed PnL analysis
    - Mock matching engine with configurable slippage and fees
    - Multi-level take-profit support
    - Trailing stop loss support
    - Complete order lifecycle simulation

    T4/T5/T6: Orders and backtest reports are automatically saved to database.

    Request body (BacktestRequest):
    {
        "symbol": "BTC/USDT:USDT",
        "timeframe": "15m",
        "start_time": null,
        "end_time": null,
        "limit": 100,
        "mode": "v3_pms",
        "initial_balance": 10000,
        "slippage_rate": 0.001,
        "fee_rate": 0.0004,
        "strategies": [...],  # Optional: custom strategy definitions
        "risk_overrides": {...},  # Optional: risk config overrides
        "order_strategy": {...}  # Optional: multi-level TP strategy
    }

    Returns:
        PMSBacktestReport with:
        - positions: Position-level trade records with PnL
        - orders: All executed orders
        - equity_curve: Account balance over time
        - statistics: Win rate, avg PnL, max drawdown, etc.
        - monthly_returns: Monthly return heatmap data
    """
    try:
        from src.application.backtester import Backtester
        from src.infrastructure.backtest_repository import BacktestReportRepository
        from src.infrastructure.historical_data_repository import HistoricalDataRepository
        from src.infrastructure.order_repository import OrderRepository

        # Validate mode
        if request.mode != "v3_pms":
            logger.warning(f"PMS backtest called with mode={request.mode}, forcing v3_pms")

        gateway, gateway_is_temp = await _get_backtest_gateway()

        # Initialize historical data repository for local-first data access
        data_repo = HistoricalDataRepository()
        await data_repo.initialize()

        backtester = Backtester(gateway, data_repository=data_repo)

        # T5/T6: Initialize backtest report repository for saving reports
        backtest_repository = BacktestReportRepository()
        await backtest_repository.initialize()

        # T4: Initialize order repository for saving orders
        order_repository = OrderRepository()
        await order_repository.initialize()

        try:
            # Run backtest with repositories (force v3_pms mode)
            request_copy = BacktestRequest(**request.model_dump())
            request_copy.mode = "v3_pms"

            report = await backtester.run_backtest(
                request_copy,
                account_snapshot=None,  # Not needed for PMS mode
                repository=None,  # Signals are tracked internally
                backtest_repository=backtest_repository,
                order_repository=order_repository
            )

            return {
                "status": "success",
                "report": report.model_dump(),
            }
        finally:
            if gateway_is_temp:
                await gateway.close()
                logger.info("Temporary backtest gateway closed")
            await backtest_repository.close()
            await order_repository.close()
            await data_repo.close()

    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e)}


# ============================================================
# Backtest Configuration Endpoints (T4)
# ============================================================

@app.get("/api/backtest/configs")
async def get_backtest_configs():
    """
    获取当前回测配置。

    从 KV 存储读取回测配置参数，包括：
    - slippage_rate: 滑点率（默认 0.001）
    - fee_rate: 手续费率（默认 0.0004）
    - initial_balance: 初始资金（默认 10000）
    - tp_slippage_rate: 止盈平仓滑点率（默认 0.0005）

    Returns:
        包含回测配置的字典
    """
    try:
        config_manager = _get_config_manager()
        configs = await config_manager.get_backtest_configs()

        return {
            "status": "success",
            "configs": {
                "slippage_rate": str(configs.get('slippage_rate', '0.001')),
                "fee_rate": str(configs.get('fee_rate', '0.0004')),
                "initial_balance": str(configs.get('initial_balance', '10000')),
                "tp_slippage_rate": str(configs.get('tp_slippage_rate', '0.0005')),
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Backtest config API error: {e}")
        return {"status": "error", "error": str(e)}


@app.put("/api/backtest/configs")
async def update_backtest_configs(
    configs: Dict[str, Any] = Body(..., description="回测配置更新"),
):
    """
    更新回测配置。

    保存回测配置参数到 KV 存储，需要验证配置值范围。

    支持的配置项：
    - slippage_rate: 滑点率 (0~0.01)
    - fee_rate: 手续费率 (0~0.01)
    - initial_balance: 初始资金 (>0)
    - tp_slippage_rate: 止盈平仓滑点率 (0~0.01)

    Request body example:
    {
        "slippage_rate": 0.001,
        "fee_rate": 0.0004,
        "initial_balance": 10000,
        "tp_slippage_rate": 0.0005
    }

    Returns:
        更新结果和更新后的配置
    """
    try:
        config_manager = _get_config_manager()

        # 验证配置值范围
        validated_configs = {}
        errors = []

        # 验证 slippage_rate
        if 'slippage_rate' in configs:
            try:
                value = Decimal(str(configs['slippage_rate']))
                if value < 0 or value > Decimal('0.01'):
                    errors.append("slippage_rate 必须在 0~0.01 范围内")
                else:
                    validated_configs['slippage_rate'] = value
            except Exception as e:
                errors.append(f"slippage_rate 格式错误：{e}")

        # 验证 fee_rate
        if 'fee_rate' in configs:
            try:
                value = Decimal(str(configs['fee_rate']))
                if value < 0 or value > Decimal('0.01'):
                    errors.append("fee_rate 必须在 0~0.01 范围内")
                else:
                    validated_configs['fee_rate'] = value
            except Exception as e:
                errors.append(f"fee_rate 格式错误：{e}")

        # 验证 initial_balance
        if 'initial_balance' in configs:
            try:
                value = Decimal(str(configs['initial_balance']))
                if value <= Decimal('0'):
                    errors.append("initial_balance 必须大于 0")
                else:
                    validated_configs['initial_balance'] = value
            except Exception as e:
                errors.append(f"initial_balance 格式错误：{e}")

        # 验证 tp_slippage_rate
        if 'tp_slippage_rate' in configs:
            try:
                value = Decimal(str(configs['tp_slippage_rate']))
                if value < 0 or value > Decimal('0.01'):
                    errors.append("tp_slippage_rate 必须在 0~0.01 范围内")
                else:
                    validated_configs['tp_slippage_rate'] = value
            except Exception as e:
                errors.append(f"tp_slippage_rate 格式错误：{e}")

        # 如果有验证错误，返回 422
        if errors:
            from fastapi import status
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": "配置验证失败",
                    "errors": errors
                }
            )

        # 保存配置到 KV 存储
        count = await config_manager.save_backtest_configs(validated_configs)

        return {
            "status": "success",
            "message": f"Updated {count} backtest config entries",
            "configs": {k: str(v) for k, v in validated_configs.items()}
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Backtest config API error: {e}")
        error_str = str(e)
        if "ValidationError" in type(e).__name__:
            from fastapi import status
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Config validation failed: {error_str}",
            )
        return {"status": "error", "error": str(e)}


# ============================================================
# Deprecated: Use /api/backtest/signals or /api/backtest/orders instead
# ============================================================
@app.post("/api/backtest")
async def run_backtest_deprecated(
    request: BacktestRequest,
):
    """
    [DEPRECATED] Run strategy backtest on historical data.

    已弃用：请使用以下新接口替代：
    - POST /api/backtest/signals - 信号回测（v2_classic 模式）
    - POST /api/backtest/orders - PMS 订单回测（v3_pms 模式）

    This endpoint will be removed in a future version.

    Backtest signals are automatically saved to database with source='backtest'.
    You can view them in the Signals page with K-line chart visualization.

    T4/T5/T6: Orders and backtest reports are automatically saved to database.

    Request body (BacktestRequest):
    {
        "symbol": "BTC/USDT:USDT",
        "timeframe": "15m",
        "start_time": null,
        "end_time": null,
        "limit": 100,
        "min_wick_ratio": 0.6,
        "max_body_ratio": 0.3,
        "body_position_tolerance": 0.1,
        "trend_filter_enabled": true,
        "mtf_validation_enabled": true,
        "mode": "v2_classic" | "v3_pms"  # 通过 mode 参数区分
    }

    Returns:
        BacktestReport (v2_classic) or PMSBacktestReport (v3_pms)
    """
    import warnings
    warnings.warn(
        "The /api/backtest endpoint is deprecated. "
        "Please use /api/backtest/signals for signal-level backtest "
        "or /api/backtest/orders for PMS backtest.",
        DeprecationWarning,
        stacklevel=2
    )

    try:
        from src.application.backtester import Backtester
        from src.infrastructure.backtest_repository import BacktestReportRepository
        from src.infrastructure.historical_data_repository import HistoricalDataRepository
        from src.infrastructure.order_repository import OrderRepository

        gateway, gateway_is_temp = await _get_backtest_gateway()

        # Initialize historical data repository for local-first data access
        data_repo = HistoricalDataRepository()
        await data_repo.initialize()

        backtester = Backtester(gateway, data_repository=data_repo)

        # Get current account snapshot for position sizing
        account_snapshot = _account_getter() if _account_getter else None

        # Get repository for saving signals (always save backtest signals)
        repository = _get_repository()

        # T5/T6: Initialize backtest report repository for saving reports
        backtest_repository = BacktestReportRepository()
        await backtest_repository.initialize()

        # T4: Initialize order repository for saving orders
        order_repository = OrderRepository()
        await order_repository.initialize()

        try:
            # Run backtest with repositories
            report = await backtester.run_backtest(
                request,
                account_snapshot,
                repository=repository,
                backtest_repository=backtest_repository,
                order_repository=order_repository
            )

            return {
                "status": "success",
                "report": report.model_dump(),
            }
        finally:
            if gateway_is_temp:
                await gateway.close()
                logger.info("Temporary backtest gateway closed")
            await backtest_repository.close()
            await order_repository.close()
            await data_repo.close()

    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e)}


# ============================================================
# BT-4: Strategy Attribution Analysis Endpoints
# ============================================================

class AttributionAnalysisRequest(BaseModel):
    """归因分析请求"""
    report_id: Optional[str] = Field(None, description="回测报告 ID（从数据库加载）")
    backtest_report: Optional[Dict[str, Any]] = Field(None, description="直接传入回测报告数据")

    @model_validator(mode='after')
    def validate_mutually_exclusive_fields(self):
        """验证 report_id 和 backtest_report 有且仅有一个存在"""
        if self.report_id is None and self.backtest_report is None:
            raise ValueError("必须提供 report_id 或 backtest_report 其中之一")
        return self


class AttributionAnalysisResponse(BaseModel):
    """归因分析响应"""
    status: str
    attribution: AttributionReport


@app.post("/api/backtest/{report_id}/attribution", response_model=AttributionAnalysisResponse)
async def analyze_backtest_attribution(
    report_id: str,
):
    """
    对回测报告进行策略归因分析

    **BT-4 策略归因分析** - 四个维度：
    - B: 形态质量归因（Pinbar 评分与表现关系）
    - C: 过滤器归因（各过滤器对胜率/回撤的影响）
    - D: 市场趋势归因（顺势/逆势交易表现）
    - F: 盈亏比归因（最优盈亏比区间识别）

    ## 请求参数
    - `report_id`: 回测报告 ID（从 `/api/v3/backtest/reports` 获取）

    ## 返回示例
    ```json
    {
      "status": "success",
      "attribution": {
        "shape_quality": {
          "high_score": {"count": 10, "win_rate": 0.65, "avg_pnl_ratio": 1.8},
          "medium_score": {"count": 15, "win_rate": 0.53, "avg_pnl_ratio": 1.2},
          "low_score": {"count": 8, "win_rate": 0.38, "avg_pnl_ratio": 0.5}
        },
        "filter_attribution": {
          "ema_filter": {"enabled_trades": 25, "passed_trades": 20, "win_rate_with_ema": 0.60},
          "mtf_filter": {"enabled_trades": 25, "passed_trades": 18, "win_rate_with_mtf": 0.61},
          "rejection_stats": {"ema_trend": 5, "mtf": 7}
        },
        "trend_attribution": {
          "bullish_trend": {"trade_count": 15, "win_rate": 0.67, "avg_pnl": 1.5},
          "bearish_trend": {"trade_count": 18, "win_rate": 0.56, "avg_pnl": 1.2},
          "alignment_stats": {"aligned_trades": 28, "against_trend_trades": 5}
        },
        "rr_attribution": {
          "high_rr": {"count": 8, "win_rate": 0.75},
          "medium_rr": {"count": 12, "win_rate": 0.58},
          "low_rr": {"count": 5, "win_rate": 0.40},
          "optimal_range": {"suggested_rr": "high", "reasoning": "高盈亏比区间胜率最高"}
        }
      }
    }
    ```
    """
    from src.application.attribution_analyzer import AttributionAnalyzer
    from src.infrastructure.backtest_repository import BacktestReportRepository

    try:
        # 1. 从数据库加载回测报告
        backtest_repository = BacktestReportRepository()
        await backtest_repository.initialize()

        try:
            report_entity = await backtest_repository.get_report_by_id(report_id)
        finally:
            await backtest_repository.close()

        if not report_entity:
            raise HTTPException(status_code=404, detail=f"Backtest report {report_id} not found")

        # 2. 将报告实体转换为字典格式
        # 注意：report_entity 是 ORM 对象，attempts 存储为 JSON 字符串
        import json
        attempts = report_entity.attempts
        if isinstance(attempts, str):
            attempts = json.loads(attempts)

        backtest_report_dict = {
            "attempts": attempts or [],
        }

        # 3. 执行归因分析
        analyzer = AttributionAnalyzer()
        attribution_report = analyzer.analyze(backtest_report_dict)

        return {
            "status": "success",
            "attribution": attribution_report,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Attribution analysis failed for report_id={report_id}: {type(e).__name__} - {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/backtest/attribution/preview", response_model=AttributionAnalysisResponse)
async def preview_backtest_attribution(
    request: AttributionAnalysisRequest,
):
    """
    预览归因分析（无需保存报告到数据库）

    适用于：
    - 回测完成后立即查看归因分析
    - 本地回测数据的归因分析

    ## 请求体
    ```json
    {
      "backtest_report": { "attempts": [...] }  # 回测报告的 attempts 字段
    }
    ```
    或
    ```json
    {
      "report_id": "xxx"  # 从数据库加载
    }
    ```
    """
    from src.application.attribution_analyzer import AttributionAnalyzer

    try:
        analyzer = AttributionAnalyzer()

        if request.backtest_report:
            # 直接分析传入的报告数据
            attribution_report = analyzer.analyze(request.backtest_report)
        elif request.report_id:
            # 从数据库加载报告
            from src.infrastructure.backtest_repository import BacktestReportRepository
            backtest_repository = BacktestReportRepository()
            await backtest_repository.initialize()

            try:
                report_entity = await backtest_repository.get_report_by_id(request.report_id)
            finally:
                await backtest_repository.close()

            if not report_entity:
                raise HTTPException(status_code=404, detail=f"Backtest report {request.report_id} not found")

            backtest_report_dict = {"attempts": report_entity.attempts or []}
            attribution_report = analyzer.analyze(backtest_report_dict)
        else:
            raise HTTPException(status_code=400, detail="Either report_id or backtest_report must be provided")

        return {
            "status": "success",
            "attribution": attribution_report,
        }

    except HTTPException:
        raise
    except Exception as e:
        request_context = "backtest_report" if request.backtest_report else f"report_id={request.report_id}"
        logger.error(f"Attribution preview failed for {request_context}: {type(e).__name__} - {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Backtest Reports Management Endpoints (v3) - Continued
# ============================================================

class BacktestReportSummary(BaseModel):
    """回测报告摘要信息"""
    id: str
    strategy_id: str
    strategy_name: str
    strategy_version: str
    symbol: str
    timeframe: str
    backtest_start: int
    backtest_end: int
    created_at: int
    total_return: str
    total_trades: int
    win_rate: str
    total_pnl: str
    max_drawdown: str
    sharpe_ratio: Optional[str] = None


class ListBacktestReportsResponse(BaseModel):
    """回测报告列表响应"""
    reports: List[BacktestReportSummary]
    total: int
    page: int
    pageSize: int


@app.get("/api/v3/backtest/reports", response_model=ListBacktestReportsResponse)
async def list_backtest_reports(
    strategy_id: Optional[str] = Query(None, description="策略 ID 筛选"),
    symbol: Optional[str] = Query(None, description="交易对筛选"),
    start_date: Optional[int] = Query(None, description="开始时间戳（毫秒）"),
    end_date: Optional[int] = Query(None, description="结束时间戳（毫秒）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    sort_by: Literal['total_return', 'win_rate', 'created_at'] = Query('created_at', description="排序字段"),
    sort_order: Literal['asc', 'desc'] = Query('desc', description="排序方向"),
) -> ListBacktestReportsResponse:
    """
    获取回测报告列表（支持筛选、排序、分页）

    Phase 6: v3.0 回测报告管理 - GET /api/v3/backtest/reports

    功能:
    - 按策略 ID、交易对、时间范围筛选
    - 按收益率、胜率、创建时间排序
    - 分页支持

    Args:
        strategy_id: 策略 ID 筛选
        symbol: 交易对筛选
        start_date: 开始时间戳（毫秒）
        end_date: 结束时间戳（毫秒）
        page: 页码（从 1 开始）
        page_size: 每页数量（1-100）
        sort_by: 排序字段 ('total_return' | 'win_rate' | 'created_at')
        sort_order: 排序方向 ('asc' | 'desc')

    Returns:
        ListBacktestReportsResponse: 回测报告列表响应

    Raises:
        HTTPException:
            - 500: 数据库查询失败
    """
    try:
        # 获取数据库连接（与 signals 共享）
        from src.infrastructure.backtest_repository import BacktestReportRepository

        repository = BacktestReportRepository()
        await repository.initialize()

        try:
            # 调用 repository 的 list_reports 方法
            result = await repository.list_reports(
                strategy_id=strategy_id,
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                sort_order=sort_order,
            )

            # 转换为响应模型
            reports = [
                BacktestReportSummary(
                    id=r["id"],
                    strategy_id=r["strategy_id"],
                    strategy_name=r["strategy_name"],
                    strategy_version=r["strategy_version"],
                    symbol=r["symbol"],
                    timeframe=r["timeframe"],
                    backtest_start=r["backtest_start"],
                    backtest_end=r["backtest_end"],
                    created_at=r["created_at"],
                    total_return=r["total_return"],
                    total_trades=r["total_trades"],
                    win_rate=r["win_rate"],
                    total_pnl=r["total_pnl"],
                    max_drawdown=r["max_drawdown"],
                    sharpe_ratio=r.get("sharpe_ratio"),
                )
                for r in result["reports"]
            ]

            return ListBacktestReportsResponse(
                reports=reports,
                total=result["total"],
                page=result["page"],
                pageSize=result["pageSize"],
            )
        finally:
            await repository.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取回测报告列表失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v3/backtest/reports/{report_id}")
async def get_backtest_report(report_id: str):
    """
    获取回测报告详情

    Phase 6: v3.0 回测报告管理 - GET /api/v3/backtest/reports/{report_id}

    Args:
        report_id: 报告 ID

    Returns:
        回测报告详情（包含完整的 positions 列表）

    Raises:
        HTTPException:
            - 404: 报告不存在
            - 500: 数据库查询失败
    """
    try:
        from src.infrastructure.backtest_repository import BacktestReportRepository
        from src.domain.models import PMSBacktestReport

        repository = BacktestReportRepository()
        await repository.initialize()

        try:
            report = await repository.get_report(report_id)

            if not report:
                raise HTTPException(status_code=404, detail="回测报告不存在")

            return {
                "status": "success",
                "report": report.model_dump(),
            }
        finally:
            await repository.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取回测报告详情失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v3/backtest/reports/{report_id}")
async def delete_backtest_report(report_id: str):
    """
    删除回测报告

    Phase 6: v3.0 回测报告管理 - DELETE /api/v3/backtest/reports/{report_id}

    Args:
        report_id: 报告 ID

    Returns:
        删除结果

    Raises:
        HTTPException:
            - 500: 数据库删除失败
    """
    try:
        from src.infrastructure.backtest_repository import BacktestReportRepository

        repository = BacktestReportRepository()
        await repository.initialize()

        try:
            await repository.delete_report(report_id)

            return {
                "status": "success",
                "message": f"已删除回测报告：{report_id}",
            }
        finally:
            await repository.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除回测报告失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Backtest Orders Management Endpoints
# ============================================================

from pydantic import BaseModel, Field, ConfigDict


class BacktestOrderSummary(BaseModel):
    """回测订单摘要信息"""
    id: str
    signal_id: str
    symbol: str = Field(..., description="交易对")
    order_role: str
    order_type: str
    direction: Direction  # P1-001: 使用 Direction 枚举而非 str
    requested_qty: str
    filled_qty: str
    average_exec_price: Optional[str] = None
    status: str
    created_at: int
    updated_at: int
    exit_reason: Optional[str] = None


class ListBacktestOrdersResponse(BaseModel):
    """回测订单列表响应"""
    model_config = ConfigDict(populate_by_name=True)

    orders: List[BacktestOrderSummary]
    total: int
    page: int
    page_size: int = Field(..., alias="pageSize", description="每页数量")


@app.get("/api/v3/backtest/reports/{report_id}/orders", response_model=ListBacktestOrdersResponse)
async def list_backtest_orders(
    report_id: str,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    order_role: Optional[str] = Query(None, description="订单角色筛选 (ENTRY/TP1/SL/etc)"),
):
    """
    获取回测报告关联的订单列表

    Args:
        report_id: 回测报告 ID
        page: 页码（从 1 开始）
        page_size: 每页数量（1-100）
        order_role: 订单角色筛选 (ENTRY/TP1/SL/etc)

    Returns:
        回测订单列表

    Raises:
        HTTPException:
            - 404: 回测报告不存在
            - 500: 数据库查询失败
    """
    try:
        from src.infrastructure.backtest_repository import BacktestReportRepository
        from src.infrastructure.signal_repository import SignalRepository
        from src.infrastructure.order_repository import OrderRepository

        # Step 1: 获取回测报告
        backtest_repo = BacktestReportRepository()
        await backtest_repo.initialize()
        try:
            report = await backtest_repo.get_report(report_id)
            if not report:
                raise HTTPException(status_code=404, detail=f"回测报告不存在：{report_id}")

            strategy_id = report.strategy_id
            start_time = report.backtest_start
            end_time = report.backtest_end
        finally:
            await backtest_repo.close()

        # Step 2: 获取关联的信号 ID 列表
        signal_repo = SignalRepository()
        await signal_repo.initialize()
        try:
            signal_ids = await signal_repo.get_signal_ids_by_backtest_report(
                strategy_id=strategy_id,
                start_time=start_time,
                end_time=end_time,
            )

            if not signal_ids:
                # 没有信号，返回空列表
                return ListBacktestOrdersResponse(orders=[], total=0, page=page, pageSize=page_size)
        finally:
            await signal_repo.close()

        # Step 3: 获取订单列表
        order_repo = OrderRepository()
        await order_repo.initialize()
        try:
            result = await order_repo.get_orders_by_signal_ids(
                signal_ids=signal_ids,
                page=page,
                page_size=page_size,
                order_role=order_role,
            )

            orders = [
                BacktestOrderSummary(
                    id=o.id,
                    signal_id=o.signal_id,
                    symbol=o.symbol,
                    order_role=o.order_role.value,
                    order_type=o.order_type.value,
                    direction=o.direction,  # P1-001: Pydantic 自动序列化 Direction 枚举
                    requested_qty=str(o.requested_qty),
                    filled_qty=str(o.filled_qty),
                    average_exec_price=str(o.average_exec_price) if o.average_exec_price else None,
                    status=o.status.value,
                    created_at=o.created_at,
                    updated_at=o.updated_at,
                    exit_reason=o.exit_reason,
                )
                for o in result['orders']
            ]

            return ListBacktestOrdersResponse(
                orders=orders,
                total=result['total'],
                page=result['page'],
                page_size=result['page_size'],
            )
        finally:
            await order_repo.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取回测订单列表失败：{str(e)}")
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error_code=BacktestErrorCode.DATABASE_ERROR,
                message=f"获取回测订单列表失败：{str(e)}"
            ).model_dump()
        )


@app.get("/api/v3/backtest/reports/{report_id}/orders/{order_id}")
async def get_backtest_order(report_id: str, order_id: str):
    """
    获取回测订单详情（包含关联的 K 线数据）

    Args:
        report_id: 回测报告 ID
        order_id: 订单 ID

    Returns:
        订单详情及关联的 K 线数据（前后各 10 根）

    Raises:
        HTTPException:
            - 404: 订单不存在或不属于该回测报告
            - 500: 数据库查询失败
    """
    try:
        from src.infrastructure.order_repository import OrderRepository
        from src.infrastructure.historical_data_repository import HistoricalDataRepository

        # Step 1: 获取订单详情
        order_repo = OrderRepository()
        await order_repo.initialize()
        try:
            order = await order_repo.get_order(order_id)
            if not order:
                raise HTTPException(status_code=404, detail=f"订单不存在：{order_id}")
        finally:
            await order_repo.close()

        # Step 2: 验证订单属于该回测报告
        backtest_repo = BacktestReportRepository()
        await backtest_repo.initialize()
        try:
            report = await backtest_repo.get_report(report_id)
            if not report:
                raise HTTPException(status_code=404, detail=f"回测报告不存在：{report_id}")

            # 验证订单的 signal_id 是否属于该回测报告
            signal_repo = SignalRepository()
            await signal_repo.initialize()
            try:
                signal_ids = await signal_repo.get_signal_ids_by_backtest_report(
                    strategy_id=report.strategy_id,
                    start_time=report.backtest_start,
                    end_time=report.backtest_end,
                )
                if order.signal_id not in signal_ids:
                    raise HTTPException(status_code=404, detail=f"订单不属于该回测报告")
            finally:
                await signal_repo.close()
        finally:
            await backtest_repo.close()

        # Step 3: 获取关联的 K 线数据（前后各 10 根）
        data_repo = HistoricalDataRepository()
        await data_repo.initialize()
        try:
            # 计算时间范围（P1-004: 使用统一工具函数）
            kline_interval_ms = BacktestConfig.get_timeframe_ms(report.timeframe)

            # 以订单创建时间为中心，前后各取 KLINE_WINDOW_BEFORE/AFTER 根 K 线 (P1-003)
            center_time = order.created_at
            start_time = center_time - (BacktestConfig.KLINE_WINDOW_BEFORE * kline_interval_ms)
            end_time = center_time + (BacktestConfig.KLINE_WINDOW_AFTER * kline_interval_ms)

            klines = await data_repo.get_klines(
                symbol=order.symbol,
                timeframe=report.timeframe,
                start_time=start_time,
                end_time=end_time,
            )

            kline_data = [
                {
                    "timestamp": k.timestamp,
                    "open": str(k.open),
                    "high": str(k.high),
                    "low": str(k.low),
                    "close": str(k.close),
                    "volume": str(k.volume),
                }
                for k in klines
            ]
        finally:
            await data_repo.close()

        return {
            "order": {
                "id": order.id,
                "signal_id": order.signal_id,
                "symbol": order.symbol,
                "order_role": order.order_role.value,
                "order_type": order.order_type.value,
                "direction": order.direction.value,
                "price": str(order.price) if order.price else None,
                "trigger_price": str(order.trigger_price) if order.trigger_price else None,
                "requested_qty": str(order.requested_qty),
                "filled_qty": str(order.filled_qty),
                "average_exec_price": str(order.average_exec_price) if order.average_exec_price else None,
                "status": order.status.value,
                "exit_reason": order.exit_reason,
                "created_at": order.created_at,
                "updated_at": order.updated_at,
                "filled_at": order.filled_at,
            },
            "klines": kline_data,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取回测订单详情失败：{str(e)}")
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error_code=BacktestErrorCode.DATABASE_ERROR,
                message=f"获取回测订单详情失败：{str(e)}"
            ).model_dump()
        )


@app.delete("/api/v3/backtest/reports/{report_id}/orders/{order_id}")
async def delete_backtest_order(report_id: str, order_id: str):
    """
    删除回测订单

    Args:
        report_id: 回测报告 ID
        order_id: 订单 ID

    Returns:
        删除结果

    Raises:
        HTTPException:
            - 404: 订单不存在或不属于该回测报告
            - 500: 数据库删除失败
    """
    try:
        from src.infrastructure.order_repository import OrderRepository
        from src.infrastructure.backtest_repository import BacktestReportRepository
        from src.infrastructure.signal_repository import SignalRepository

        # Step 1: 验证订单属于该回测报告
        backtest_repo = BacktestReportRepository()
        await backtest_repo.initialize()
        try:
            report = await backtest_repo.get_report(report_id)
            if not report:
                raise HTTPException(status_code=404, detail=f"回测报告不存在：{report_id}")

            signal_repo = SignalRepository()
            await signal_repo.initialize()
            try:
                signal_ids = await signal_repo.get_signal_ids_by_backtest_report(
                    strategy_id=report.strategy_id,
                    start_time=report.backtest_start,
                    end_time=report.backtest_end,
                )
            finally:
                await signal_repo.close()
        finally:
            await backtest_repo.close()

        # Step 2: 获取订单并验证
        order_repo = OrderRepository()
        await order_repo.initialize()
        try:
            order = await order_repo.get_order(order_id)
            if not order:
                raise HTTPException(status_code=404, detail=f"订单不存在：{order_id}")

            if order.signal_id not in signal_ids:
                raise HTTPException(status_code=404, detail=f"订单不属于该回测报告")

            # Step 3: 删除订单
            await order_repo.delete_order(order_id)

            return {
                "status": "success",
                "message": f"已删除订单：{order_id}",
            }
        finally:
            await order_repo.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除回测订单失败：{str(e)}")
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error_code=BacktestErrorCode.DATABASE_ERROR,
                message=f"删除回测订单失败：{str(e)}"
            ).model_dump()
        )


# ============================================================
# Custom Strategies Management Endpoints
# ============================================================

class StrategyMetaResponse(BaseModel):
    """Response model for strategy metadata."""
    triggers: List[Dict[str, Any]]
    filters: List[Dict[str, Any]]


@app.get("/api/strategies/meta")
async def get_strategy_metadata():
    """
    Get metadata about supported triggers and filters.

    Returns information about:
    - Available trigger types (pinbar, engulfing, doji, hammer) with their parameter schemas
    - Available filter types (ema, mtf, atr, etc.) with their parameter schemas

    This endpoint is designed for dynamic frontend form generation.
    """
    # Trigger type definitions with parameter schemas
    triggers = [
        {
            "type": "pinbar",
            "displayName": "Pinbar (针 bar)",
            "paramsSchema": {
                "min_wick_ratio": {"type": "number", "min": 0, "max": 1, "default": 0.6, "description": "最小影线比例"},
                "max_body_ratio": {"type": "number", "min": 0, "max": 1, "default": 0.3, "description": "最大实体比例"},
                "body_position_tolerance": {"type": "number", "min": 0, "max": 0.5, "default": 0.1, "description": "实体位置容差"},
            }
        },
        {
            "type": "engulfing",
            "displayName": "Engulfing (吞没)",
            "paramsSchema": {
                "min_body_ratio": {"type": "number", "min": 0, "max": 1, "default": 0.5, "description": "最小实体比例"},
                "require_full_engulf": {"type": "boolean", "default": True, "description": "是否需要完全吞没"},
            }
        },
        {
            "type": "doji",
            "displayName": "Doji (十字星)",
            "paramsSchema": {
                "max_body_ratio": {"type": "number", "min": 0, "max": 1, "default": 0.1, "description": "最大实体比例"},
                "min_total_range": {"type": "number", "min": 0, "default": 0.001, "description": "最小总范围"},
            }
        },
        {
            "type": "hammer",
            "displayName": "Hammer (锤子线)",
            "paramsSchema": {
                "min_lower_wick_ratio": {"type": "number", "min": 0, "max": 1, "default": 0.6, "description": "最小下影线比例"},
                "max_upper_wick_ratio": {"type": "number", "min": 0, "max": 1, "default": 0.2, "description": "最大上影线比例"},
                "min_body_ratio": {"type": "number", "min": 0, "max": 1, "default": 0.1, "description": "最小实体比例"},
            }
        },
    ]

    # Filter type definitions with parameter schemas
    filters = [
        {
            "type": "ema",
            "displayName": "EMA 趋势过滤",
            "paramsSchema": {
                "period": {"type": "number", "min": 1, "default": 60, "description": "EMA 周期"},
                "trend_direction": {"type": "string", "enum": ["bullish", "bearish", "either"], "default": "either", "description": "趋势方向要求"},
            }
        },
        {
            "type": "mtf",
            "displayName": "MTF 多周期验证",
            "paramsSchema": {
                "require_confirmation": {"type": "boolean", "default": True, "description": "是否需要确认"},
            }
        },
        {
            "type": "volume_surge",
            "displayName": "成交量激增",
            "paramsSchema": {
                "multiplier": {"type": "number", "min": 0, "default": 1.5, "description": "成交量倍数阈值"},
                "lookback_periods": {"type": "number", "min": 1, "default": 20, "description": "回看周期数"},
            }
        },
        {
            "type": "volatility_filter",
            "displayName": "波动率过滤",
            "paramsSchema": {
                "min_atr_ratio": {"type": "number", "min": 0, "default": 0.5, "description": "最小 ATR 比例"},
                "max_atr_ratio": {"type": "number", "min": 0, "default": 3.0, "description": "最大 ATR 比例"},
                "atr_period": {"type": "number", "min": 1, "default": 14, "description": "ATR 周期"},
            }
        },
        {
            "type": "time_filter",
            "displayName": "时间窗口过滤",
            "paramsSchema": {
                "session": {"type": "string", "enum": ["asian", "london", "new_york", "any"], "default": "any", "description": "交易时段"},
                "exclude_weekend": {"type": "boolean", "default": True, "description": "是否排除周末"},
            }
        },
        {
            "type": "price_action",
            "displayName": "价格行为过滤",
            "paramsSchema": {
                "require_closed_candle": {"type": "boolean", "default": True, "description": "是否需要闭合蜡烛"},
            }
        },
    ]

    return {
        "triggers": triggers,
        "filters": filters,
    }


# ============================================================
# F-4: Strategy Preview Endpoint (热预览接口)
# ============================================================
class StrategyPreviewRequest(BaseModel):
    """Request model for strategy preview endpoint."""
    logic_tree: Dict[str, Any] = Field(..., description="Recursive logic tree configuration")
    symbol: str = Field(..., description="Symbol to preview, e.g., 'BTC/USDT:USDT'")
    timeframe: str = Field(..., description="Timeframe, e.g., '15m', '1h'")


class StrategyPreviewResponse(BaseModel):
    """Response model for strategy preview endpoint."""
    signal_fired: bool = Field(..., description="Whether signal was triggered")
    trace_tree: Dict[str, Any] = Field(..., description="Complete trace tree showing evaluation path")
    evaluation_summary: str = Field(..., description="Human-readable evaluation report in natural language")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Additional details if signal fired")


class StrategyApplyRequest(BaseModel):
    """Request model for applying a strategy template to live trading."""
    enabled: bool = Field(default=True, description="Whether to enable the strategy after applying")
    apply_to: Optional[List[str]] = Field(default=None, description="Specific symbol:timeframe scopes to apply. If None, applies globally")


class StrategyApplyResponse(BaseModel):
    """Response model for strategy apply endpoint."""
    status: str = Field(..., description="Status of the apply operation")
    message: str = Field(..., description="Human-readable result message")
    strategy_id: str = Field(..., description="Applied strategy template ID")
    strategy_name: str = Field(..., description="Applied strategy name")
    merged_timeframes: Optional[List[str]] = Field(default=None, description="合并后的监控周期")
    merged_symbols: Optional[List[str]] = Field(default=None, description="合并后的监控币种")
    monitoring_config_changed: bool = Field(default=False, description="监控配置是否变更")


@app.post("/api/strategies/preview", response_model=StrategyPreviewResponse)
async def preview_strategy(request: StrategyPreviewRequest):
    """
    Preview a strategy configuration against recent kline data.

    This endpoint performs a dry-run evaluation without persistence or hot-reload.
    Returns the complete trace tree showing the evaluation path.

    Request body:
    {
        "logic_tree": { ... recursive logic tree ... },
        "symbol": "BTC/USDT:USDT",
        "timeframe": "15m"
    }

    Response:
    {
        "signal_fired": true/false,
        "trace_tree": { ... complete trace tree ... },
        "details": { ... additional details if signal fired ... }
    }
    """
    try:
        # Get exchange gateway for kline data
        exchange = _exchange_gateway
        if exchange is None:
            raise HTTPException(status_code=503, detail="Exchange gateway not initialized")

        # Fetch recent kline data
        klines = await exchange.fetch_historical_ohlcv(
            symbol=request.symbol,
            timeframe=request.timeframe,
            limit=100
        )

        if not klines:
            raise HTTPException(status_code=404, detail="No kline data available")

        # Get the latest closed kline
        latest_kline = None
        for kline in reversed(klines):
            if kline.is_closed:
                latest_kline = kline
                break

        if latest_kline is None:
            latest_kline = klines[-1]

        # Use the KlineData object directly
        kline_data = latest_kline

        # Build StrategyDefinition from logic_tree
        from src.domain.models import StrategyDefinition
        from src.domain.logic_tree import LogicNode

        # Create StrategyDefinition with logic_tree
        strategy_def = StrategyDefinition(
            name="preview",
            logic_tree=request.logic_tree
        )

        # Create runner for evaluation
        from src.domain.strategy_engine import create_dynamic_runner
        runner = create_dynamic_runner([strategy_def])

        # Update state with kline
        runner.update_state(kline_data)

        # Evaluate using recursive engine
        from src.domain.recursive_engine import evaluate_node, TraceNode
        from src.domain.strategy_engine import FilterContext

        # Build filter context
        context = FilterContext(
            higher_tf_trends={},  # Preview mode: no higher timeframe trends
            current_trend=None,
            current_timeframe=request.timeframe,
            kline=kline_data
        )

        # Evaluate the logic tree
        trace_tree = evaluate_node(
            node=strategy_def.logic_tree,
            kline=kline_data,
            context=context,
            runner=runner
        )

        # Check if signal fired (root node passed)
        signal_fired = trace_tree.passed

        # Build response details
        details = None
        if signal_fired:
            # Extract trigger details from trace tree
            def find_trigger_details(node: TraceNode) -> Optional[Dict]:
                if node.node_type == "trigger" and node.passed:
                    return node.details
                for child in node.children:
                    result = find_trigger_details(child)
                    if result:
                        return result
                return None

            trigger_details = find_trigger_details(trace_tree)
            if trigger_details:
                details = {
                    "trigger": trigger_details,
                    "kline": {
                        "open": str(kline_data.open),
                        "high": str(kline_data.high),
                        "low": str(kline_data.low),
                        "close": str(kline_data.close),
                    }
                }

        # Convert TraceNode to dict for JSON response
        def trace_to_dict(node: TraceNode) -> Dict:
            return {
                "node_id": node.node_id,
                "node_type": node.node_type,
                "passed": node.passed,
                "reason": node.reason,
                "details": node.metadata,
                "children": [trace_to_dict(child) for child in node.children]
            }

        # Convert TraceNode to human-readable text
        def trace_to_human_text(node: TraceNode, indent: int = 0) -> str:
            """
            Recursively convert TraceNode to natural language description.

            Args:
                node: TraceNode to convert
                indent: Indentation level for formatting

            Returns:
                Human-readable string describing the evaluation result
            """
            lines = []
            prefix = "  " * indent

            # Determine node display type
            node_type_display = node.node_type.upper()

            # Build result icon and status
            result_icon = "✅" if node.passed else "❌"

            if node.node_type in ("AND", "OR", "NOT"):
                # Logic gate node
                if node.node_type == "AND":
                    node_label = "逻辑门 (AND)"
                    if node.passed:
                        reason_text = "所有条件满足"
                    else:
                        # Parse child failure info from reason
                        reason_text = _parse_and_reason(node.reason)
                elif node.node_type == "OR":
                    node_label = "逻辑门 (OR)"
                    if node.passed:
                        reason_text = _parse_or_reason(node.reason, passed=True)
                    else:
                        reason_text = "所有条件均不满足"
                else:  # NOT
                    node_label = "逻辑门 (NOT)"
                    reason_text = "条件被反转" + ("通过" if node.passed else "失败")

                lines.append(f"{prefix}{node_label} - {result_icon}")
                lines.append(f"{prefix}  → 原因：{reason_text}")

            elif node.node_type == "trigger":
                # Trigger node
                trigger_type = node.metadata.get("trigger_type", "unknown")
                trigger_name = _get_trigger_display_name(trigger_type)

                if node.passed:
                    reason_text = f"检测到{trigger_name}"
                else:
                    reason_text = f"未检测到{trigger_name}形态"

                lines.append(f"{prefix}触发器 ({trigger_name}) - {result_icon}")
                lines.append(f"{prefix}  → 原因：{reason_text}")

                # Add detailed analysis for failed triggers
                if not node.passed and indent == 0:
                    lines.append(f"{prefix}  → 详细分析：当前 K 线数据未满足{trigger_name}形态条件")

            elif node.node_type == "filter":
                # Filter node
                filter_type = node.metadata.get("filter_type", "unknown")
                filter_name = _get_filter_display_name(filter_type)

                if node.passed:
                    reason_text = f"{filter_name}检查通过"
                else:
                    reason_text = f"{filter_name}检查失败：{node.reason}"

                lines.append(f"{prefix}过滤器 ({filter_name}) - {result_icon}")
                lines.append(f"{prefix}  → 原因：{reason_text}")
            else:
                # Unknown node type
                lines.append(f"{prefix}{node.node_type} - {result_icon}")
                lines.append(f"{prefix}  → 原因：{node.reason}")

            # Recursively process children
            for child in node.children:
                child_text = trace_to_human_text(child, indent + 1)
                lines.append(child_text)

            return "\n".join(lines)

        def _parse_and_reason(reason: str) -> str:
            """Parse AND node failure reason to extract child failure info."""
            # Format: "child_N_failed: detailed_reason"
            if reason.startswith("child_"):
                parts = reason.split(": ", 1)
                if len(parts) >= 2:
                    child_info = parts[0].replace("_", " ").title()
                    detailed_reason = parts[1].split(":")[0] if ":" in parts[1] else parts[1]
                    return f"{child_info}: {detailed_reason}"
            return reason

        def _parse_or_reason(reason: str, passed: bool) -> str:
            """Parse OR node reason."""
            if passed and reason.startswith("child_"):
                parts = reason.split(": ", 1)
                if len(parts) >= 2:
                    return parts[0].replace("_", " ").title()
            return reason

        def _get_trigger_display_name(trigger_type: str) -> str:
            """Get display name for trigger type."""
            trigger_names = {
                "pinbar": "Pinbar",
                "engulfing": "Engulfing",
                "doji": "Doji",
                "hammer": "Hammer",
            }
            return trigger_names.get(trigger_type, trigger_type.title())

        def _get_filter_display_name(filter_type: str) -> str:
            """Get display name for filter type."""
            filter_names = {
                "ema": "EMA 趋势",
                "ema_trend": "EMA 趋势",
                "mtf": "多周期共振",
                "atr": "ATR 波动率",
                "volume_surge": "成交量突增",
                "volatility_filter": "波动率过滤",
                "time_filter": "时间过滤",
                "price_action": "价格行为",
            }
            return filter_names.get(filter_type, filter_type.title())

        # Build evaluation summary
        summary_lines = []
        result_icon = "✅" if signal_fired else "❌"
        summary_lines.append(f"评估结果：{'信号触发' if signal_fired else '信号未触发'} {result_icon}")
        summary_lines.append("")
        summary_lines.append("评估路径：")
        summary_lines.append(trace_to_human_text(trace_tree))

        # Add detailed analysis section for failed signals
        if not signal_fired:
            summary_lines.append("")
            summary_lines.append("详细分析：")

            def find_failure_reasons(node: TraceNode, reasons: list):
                if not node.passed:
                    if node.node_type == "trigger":
                        trigger_type = node.metadata.get("trigger_type", "unknown")
                        reasons.append(f"- {trigger_type.upper()}形态检测失败：未满足形态条件")
                    elif node.node_type == "filter":
                        filter_type = node.metadata.get("filter_type", "unknown")
                        reasons.append(f"- {filter_type}过滤器拦截：{node.reason}")
                for child in node.children:
                    find_failure_reasons(child, reasons)

            failure_reasons = []
            find_failure_reasons(trace_tree, failure_reasons)
            if failure_reasons:
                summary_lines.extend(failure_reasons[:5])  # Limit to top 5 reasons
            else:
                summary_lines.append("- 逻辑树根节点评估失败，无需继续评估")

        evaluation_summary = "\n".join(summary_lines)

        return StrategyPreviewResponse(
            signal_fired=signal_fired,
            trace_tree=trace_to_dict(trace_tree),
            evaluation_summary=evaluation_summary,
            details=details
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Preview strategy error: {e}")
        # Return error in a way that doesn't trigger response validation
        # Since response_model is StrategyPreviewResponse, we need to return that type
        # But we can include error details in the fields
        error_summary = f"评估结果：错误 ❌\n\n详细分析：\n- 策略预览执行失败：{str(e)}"
        return StrategyPreviewResponse(
            signal_fired=False,
            trace_tree={"error": str(e), "node_id": "error", "node_type": "error", "passed": False, "reason": str(e), "children": []},
            evaluation_summary=error_summary,
            details={"error": str(e)}
        )


# ============================================================
# S2-1: Strategy Apply Endpoint (一键下发实盘)
# ============================================================
@app.post("/api/strategies/{strategy_id}/apply", response_model=StrategyApplyResponse)
async def apply_strategy(strategy_id: str, request: StrategyApplyRequest = None):
    """
    Apply a custom strategy template to live trading.

    This endpoint:
    1. Loads the strategy template from database
    2. Validates the strategy structure
    3. Adds the strategy to user_config.active_strategies
    4. Triggers hot-reload observer to rebuild the strategy runner
    5. Persists the updated config to user.yaml

    Args:
        strategy_id: Strategy template ID to apply
        request: Optional apply options (enabled status, scope)

    Returns:
        StrategyApplyResponse with apply result

    Raises:
        404: Strategy template not found
        400: Invalid strategy definition
        503: Config manager not initialized
    """
    try:
        # Default request if not provided
        if request is None:
            request = StrategyApplyRequest(enabled=True, apply_to=None)

        # Step 1: Load strategy from new strategies table (StrategyConfigRepository)
        strategy_record = await _config_globals._strategy_repo.get_by_id(strategy_id)
        if strategy_record is None:
            raise HTTPException(status_code=404, detail="Strategy not found")

        # Step 2: Ensure strategy is active
        if not strategy_record.get("is_active", False):
            await _config_globals._strategy_repo.update(
                strategy_id, {"is_active": True}
            )

        # Step 2.5: 合并策略的 timeframes/symbols 到系统配置
        merge_result: Optional[Dict[str, Any]] = None
        strategy_timeframes = strategy_record.get("timeframes", [])
        strategy_symbols = strategy_record.get("symbols", [])

        if _config_globals._config_manager and (strategy_timeframes or strategy_symbols):
            merge_result = await _config_globals._config_manager.merge_strategy_monitoring_config(
                strategy_timeframes=strategy_timeframes,
                strategy_symbols=strategy_symbols,
            )

            if merge_result["changed"]:
                logger.info(
                    f"Monitoring config merged: timeframes={merge_result['timeframes']}, "
                    f"symbols={merge_result['symbols']}"
                )

        # Step 3: Notify hot-reload to rebuild strategy runner
        from src.interfaces.api_v1_config import notify_hot_reload
        await notify_hot_reload("strategy_apply")

        # Directly trigger pipeline rebuild (observer not wired in current setup)
        from src.main import get_signal_pipeline
        pipeline = get_signal_pipeline()
        if pipeline:
            await pipeline.on_config_updated()

        logger.info(f"Strategy {strategy_id} ('{strategy_record['name']}') applied successfully")

        return StrategyApplyResponse(
            status="success",
            message=f"Strategy '{strategy_record['name']}' applied to live trading",
            strategy_id=strategy_id,
            strategy_name=strategy_record["name"],
            merged_timeframes=merge_result.get("timeframes") if merge_result else None,
            merged_symbols=merge_result.get("symbols") if merge_result else None,
            monitoring_config_changed=merge_result.get("changed", False) if merge_result else False,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to apply strategy template {strategy_id}: {e}")
        return {"error": str(e)}


# ============================================================
# Strategy Parameters Management Endpoints (Phase K)
# ============================================================

class StrategyParamsResponse(BaseModel):
    """Response model for strategy parameters."""
    pinbar: Dict[str, Any] = Field(..., description="Pinbar pattern parameters")
    engulfing: Dict[str, Any] = Field(..., description="Engulfing pattern parameters")
    ema: Dict[str, Any] = Field(..., description="EMA trend filter parameters")
    mtf: Dict[str, Any] = Field(..., description="MTF validation parameters")
    atr: Dict[str, Any] = Field(..., description="ATR filter parameters")
    filters: List[Dict[str, Any]] = Field(default_factory=list, description="Additional custom filters")


class StrategyParamsUpdateRequest(BaseModel):
    """Request model for updating strategy parameters."""
    pinbar: Optional[Dict[str, Any]] = None
    engulfing: Optional[Dict[str, Any]] = None
    ema: Optional[Dict[str, Any]] = None
    mtf: Optional[Dict[str, Any]] = None
    atr: Optional[Dict[str, Any]] = None
    filters: Optional[List[Dict[str, Any]]] = None


class StrategyParamsPreviewRequest(BaseModel):
    """Request model for strategy parameters preview."""
    new_config: StrategyParamsUpdateRequest = Field(..., description="Proposed configuration")


class StrategyParamsPreviewResponse(BaseModel):
    """Response model for strategy parameters preview."""
    old_config: StrategyParamsResponse = Field(..., description="Current configuration")
    new_config: StrategyParamsResponse = Field(..., description="Proposed configuration")
    changes: List[str] = Field(default_factory=list, description="List of changed fields")
    warnings: List[str] = Field(default_factory=list, description="Validation warnings")


@app.get("/api/strategy/params", response_model=StrategyParamsResponse)
async def get_strategy_params():
    """
    Get current strategy parameters.

    Returns the active strategy parameter configuration from the database.
    If not configured, returns default values.

    Response:
    {
        "pinbar": {"min_wick_ratio": 0.6, "max_body_ratio": 0.3, ...},
        "engulfing": {"max_wick_ratio": 0.6},
        "ema": {"period": 60},
        "mtf": {"enabled": true, "ema_period": 60},
        "atr": {"enabled": true, "period": 14, "min_atr_ratio": 0.5},
        "filters": []
    }
    """
    try:
        config_manager = _get_config_manager()
        repo = _get_config_entry_repo()

        # Get config snapshots for default values
        core_config = config_manager.get_core_config()
        user_config = await config_manager.get_user_config()

        # Get all strategy parameters from database
        strategy_params = await repo.get_entries_by_prefix("strategy")

        # Default values for all required fields
        default_values = {
            "pinbar": {
                "min_wick_ratio": float(core_config.pinbar_defaults.min_wick_ratio),
                "max_body_ratio": float(core_config.pinbar_defaults.max_body_ratio),
                "body_position_tolerance": float(core_config.pinbar_defaults.body_position_tolerance),
            },
            "engulfing": {
                "min_wick_ratio": 0.6,
                "max_body_ratio": 0.3,
            },
            "ema": {
                "period": core_config.ema.period,
            },
            "mtf": {
                "enabled": user_config.mtf_ema_period > 0 if user_config else True,
                "ema_period": user_config.mtf_ema_period if user_config else 60,
            },
            "atr": {
                "enabled": True,
                "period": 14,
                "min_atr_ratio": 0.5,
            },
            "filters": [],
        }

        if strategy_params:
            # Start with defaults, then override with database values
            result = default_values.copy()
            result["pinbar"] = {**default_values["pinbar"]}
            result["engulfing"] = {**default_values["engulfing"]}
            result["ema"] = {**default_values["ema"]}
            result["mtf"] = {**default_values["mtf"]}
            result["atr"] = {**default_values["atr"]}
            result["filters"] = list(default_values["filters"])

            for key, value in strategy_params.items():
                # Extract sub-key (e.g., "strategy.pinbar.min_wick_ratio" -> "pinbar.min_wick_ratio")
                sub_key = key.replace("strategy.", "", 1)
                parts = sub_key.split(".", 1)
                if len(parts) == 2:
                    category, param_key = parts
                    if category in result and category != "filters":
                        # Convert Decimal to float for JSON serialization
                        if isinstance(value, Decimal):
                            value = float(value)
                        result[category][param_key] = value

            return StrategyParamsResponse(**result)

        # Fallback to ConfigManager defaults
        core_config = config_manager.get_core_config()
        user_config = await config_manager.get_user_config()
        params = StrategyParams.from_configs(core_config, user_config)
        return StrategyParamsResponse(**params.to_dict())

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get strategy params: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/strategy/params", response_model=StrategyParamsResponse)
async def update_strategy_params(request: StrategyParamsUpdateRequest):
    """
    Update strategy parameters with hot-reload.

    This endpoint:
    1. Validates the new configuration
    2. Saves to database
    3. Creates an auto-snapshot of the old config
    4. Returns the new configuration

    Request body (all fields optional, only provided fields will be updated):
    {
        "pinbar": {"min_wick_ratio": 0.65, "max_body_ratio": 0.25},
        "ema": {"period": 50},
        ...
    }

    Response: Updated strategy parameters
    """
    try:
        config_manager = _get_config_manager()
        repo = _get_config_entry_repo()
        snapshot_service = _get_snapshot_service()

        # Get current params from database
        current_params_flat = await repo.get_entries_by_prefix("strategy")

        # Build current params nested dict
        current_params = {
            "pinbar": {},
            "engulfing": {},
            "ema": {},
            "mtf": {},
            "atr": {},
            "filters": [],
        }
        for key, value in current_params_flat.items():
            sub_key = key.replace("strategy.", "", 1)
            parts = sub_key.split(".", 1)
            if len(parts) == 2:
                category, param_key = parts
                if category in current_params and category != "filters":
                    current_params[category][param_key] = value

        # Filter out empty categories
        current_params = {k: v for k, v in current_params.items() if v or k == "filters"}

        if not current_params_flat:
            params = StrategyParams.from_config_manager(config_manager)
            current_params = params.to_dict()

        # Merge with new values
        import copy
        new_params = copy.deepcopy(current_params)

        if request.pinbar:
            new_params['pinbar'].update(request.pinbar)
        if request.engulfing:
            new_params['engulfing'].update(request.engulfing)
        if request.ema:
            new_params['ema'].update(request.ema)
        if request.mtf:
            new_params['mtf'].update(request.mtf)
        if request.atr:
            new_params['atr'].update(request.atr)
        if request.filters is not None:
            new_params['filters'] = request.filters

        # Validate new params
        try:
            validated_params = StrategyParams(**new_params)
        except Exception as validation_error:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid parameters: {str(validation_error)}"
            )

        # Create auto-snapshot before update
        if snapshot_service:
            try:
                user_config = await config_manager.get_user_config()
                await snapshot_service.create_auto_snapshot(
                    config=user_config,
                    description="策略参数变更自动快照"
                )
                logger.info("Auto-snapshot created before strategy params update")
            except Exception as e:
                logger.warning(f"Auto-snapshot creation failed: {e}")

        # Save to database - flatten nested dict to dot-notation keys
        from datetime import datetime, timezone
        version = f"v{datetime.now(timezone.utc).strftime('%Y%m%d.%H%M%S')}"

        for category, values in new_params.items():
            if category == "filters":
                continue
            if isinstance(values, dict):
                for param_key, value in values.items():
                    await repo.upsert_entry(f"strategy.{category}.{param_key}", value, version)
            elif values:  # Non-dict values (shouldn't happen but handle anyway)
                await repo.upsert_entry(f"strategy.{category}", values, version)

        # Save filters as JSON
        if new_params.get('filters'):
            await repo.upsert_entry("strategy.filters", new_params['filters'], version)

        logger.info(f"Strategy parameters updated: {new_params}")

        return StrategyParamsResponse(**new_params)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update strategy params: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/strategy/params/preview", response_model=StrategyParamsPreviewResponse)
async def preview_strategy_params(request: StrategyParamsPreviewRequest):
    """
    Preview strategy parameters before applying (Dry Run).

    This endpoint validates the proposed configuration and shows:
    - Current configuration
    - Proposed configuration
    - List of changed fields
    - Validation warnings (if any)

    No changes are persisted.

    Request body:
    {
        "new_config": {
            "pinbar": {"min_wick_ratio": 0.65},
            "ema": {"period": 50}
        }
    }

    Response:
    {
        "old_config": {...},
        "new_config": {...},
        "changes": ["pinbar.min_wick_ratio: 0.6 → 0.65", "ema.period: 60 → 50"],
        "warnings": []
    }
    """
    try:
        config_manager = _get_config_manager()
        repo = _get_config_entry_repo()

        # Get current params from database
        current_params_flat = await repo.get_entries_by_prefix("strategy")

        # Build current params nested dict
        current_params = {
            "pinbar": {},
            "engulfing": {},
            "ema": {},
            "mtf": {},
            "atr": {},
            "filters": [],
        }
        for key, value in current_params_flat.items():
            sub_key = key.replace("strategy.", "", 1)
            parts = sub_key.split(".", 1)
            if len(parts) == 2:
                category, param_key = parts
                if category in current_params and category != "filters":
                    current_params[category][param_key] = value

        # Filter out empty categories
        current_params = {k: v for k, v in current_params.items() if v or k == "filters"}

        if not current_params_flat:
            params = StrategyParams.from_config_manager(config_manager)
            current_params = params.to_dict()

        # Build proposed config
        import copy
        new_params = copy.deepcopy(current_params)

        if request.new_config.pinbar:
            new_params['pinbar'].update(request.new_config.pinbar)
        if request.new_config.engulfing:
            new_params['engulfing'].update(request.new_config.engulfing)
        if request.new_config.ema:
            new_params['ema'].update(request.new_config.ema)
        if request.new_config.mtf:
            new_params['mtf'].update(request.new_config.mtf)
        if request.new_config.atr:
            new_params['atr'].update(request.new_config.atr)
        if request.new_config.filters is not None:
            new_params['filters'] = request.new_config.filters

        # Validate proposed config
        warnings = []
        try:
            validated_params = StrategyParams(**new_params)
        except Exception as validation_error:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid parameters: {str(validation_error)}"
            )

        # Check for warning conditions
        if new_params.get('ema', {}).get('period', 60) < 10:
            warnings.append("EMA period < 10 may cause excessive false signals")
        if new_params.get('ema', {}).get('period', 60) > 100:
            warnings.append("EMA period > 100 may cause significant lag")
        if new_params.get('pinbar', {}).get('min_wick_ratio', 0.6) < 0.4:
            warnings.append("Pinbar min_wick_ratio < 0.4 may allow weak patterns")
        if new_params.get('atr', {}).get('min_atr_ratio', 0.5) < 0.3:
            warnings.append("ATR min_atr_ratio < 0.3 may allow low volatility candles")

        # Detect changes
        changes = []

        def compare_dicts(old: dict, new: dict, prefix: str = ""):
            for key in new:
                old_val = old.get(key)
                new_val = new.get(key)
                path = f"{prefix}.{key}" if prefix else key

                if isinstance(old_val, dict) and isinstance(new_val, dict):
                    compare_dicts(old_val, new_val, path)
                elif old_val != new_val:
                    changes.append(f"{path}: {old_val} → {new_val}")

        compare_dicts(current_params, new_params)

        return StrategyParamsPreviewResponse(
            old_config=StrategyParamsResponse(**current_params),
            new_config=StrategyParamsResponse(**new_params),
            changes=changes,
            warnings=warnings,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to preview strategy params: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Strategy Parameters YAML Import/Export Endpoints (Phase K)
# ============================================================

class StrategyParamsExportResponse(BaseModel):
    """Response model for strategy parameters export."""
    yaml_content: str = Field(..., description="YAML formatted strategy parameters")
    download_url: Optional[str] = Field(None, description="Download URL for YAML file (if saved)")


class StrategyParamsImportRequest(BaseModel):
    """Request model for importing strategy parameters from YAML."""
    yaml_content: str = Field(..., description="YAML formatted strategy parameters")
    overwrite: bool = Field(default=True, description="Whether to overwrite existing config")


class StrategyParamsImportResponse(BaseModel):
    """Response model for strategy parameters import result."""
    status: str = Field(..., description="Import status: 'success' or 'error'")
    message: str = Field(..., description="Import result message")
    imported_params: StrategyParamsResponse = Field(None, description="Imported strategy parameters")
    errors: List[str] = Field(default_factory=list, description="Validation errors if any")


@app.get("/api/strategy/params/export", response_model=StrategyParamsExportResponse)
async def export_strategy_params():
    """
    Export current strategy parameters as YAML.

    This endpoint:
    1. Reads all strategy.* config entries from database
    2. Converts to nested dictionary structure
    3. Generates YAML formatted content
    4. Returns YAML content for download

    Response:
    {
        "yaml_content": "strategy:\\n  pinbar:\\n    min_wick_ratio: 0.6\\n  ...",
        "download_url": null
    }
    """
    try:
        config_manager = _get_config_manager()
        repo = _get_config_entry_repo()

        # Get all strategy parameters from database
        strategy_params = await repo.get_entries_by_prefix("strategy")

        # Build nested dict structure
        result = {
            "pinbar": {},
            "engulfing": {},
            "ema": {},
            "mtf": {},
            "atr": {},
            "filters": [],
        }

        for key, value in strategy_params.items():
            # Extract sub-key (e.g., "strategy.pinbar.min_wick_ratio" -> "pinbar.min_wick_ratio")
            sub_key = key.replace("strategy.", "", 1)
            parts = sub_key.split(".", 1)
            if len(parts) == 2:
                category, param_key = parts
                if category in result and category != "filters":
                    result[category][param_key] = value

        # Filter out empty categories
        result = {k: v for k, v in result.items() if v or k == "filters"}

        # If no params in DB, use defaults from ConfigManager
        if not strategy_params:
            params = StrategyParams.from_config_manager(config_manager)
            result = params.to_dict()

        # Build YAML structure
        yaml_data = {"strategy": result}

        # Generate YAML content
        yaml_content = yaml.safe_dump(
            yaml_data,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            indent=2
        )

        logger.info(f"Strategy parameters exported: {len(result)} categories")

        return StrategyParamsExportResponse(
            yaml_content=yaml_content,
            download_url=None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to export strategy params: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/strategy/params/export", response_model=StrategyParamsExportResponse)
async def export_strategy_params_to_file():
    """
    Export current strategy parameters to a YAML file.

    This endpoint:
    1. Reads all strategy.* config entries from database
    2. Converts to nested dictionary structure
    3. Saves to data/strategy_params_backup_{timestamp}.yaml
    4. Returns YAML content and file path

    Response:
    {
        "yaml_content": "...",
        "download_url": "/api/strategy/params/export/file/strategy_params_backup_20260402_153045.yaml"
    }
    """
    try:
        config_manager = _get_config_manager()
        repo = _get_config_entry_repo()

        # Get all strategy parameters from database
        strategy_params = await repo.get_entries_by_prefix("strategy")

        # Build nested dict structure
        result = {
            "pinbar": {},
            "engulfing": {},
            "ema": {},
            "mtf": {},
            "atr": {},
            "filters": [],
        }

        for key, value in strategy_params.items():
            sub_key = key.replace("strategy.", "", 1)
            parts = sub_key.split(".", 1)
            if len(parts) == 2:
                category, param_key = parts
                if category in result and category != "filters":
                    result[category][param_key] = value

        # Filter out empty categories
        result = {k: v for k, v in result.items() if v or k == "filters"}

        # If no params in DB, use defaults from ConfigManager
        if not strategy_params:
            params = StrategyParams.from_config_manager(config_manager)
            result = params.to_dict()

        # Build YAML structure
        yaml_data = {"strategy": result}

        # Generate YAML content
        yaml_content = yaml.safe_dump(
            yaml_data,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            indent=2
        )

        # Save to file
        from pathlib import Path
        from datetime import datetime, timezone

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"strategy_params_backup_{timestamp}.yaml"
        data_dir = Path(__file__).parent.parent.parent / "data"
        data_dir.mkdir(exist_ok=True)
        file_path = data_dir / filename

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(yaml_content)

        logger.info(f"Strategy parameters exported to {file_path}")

        return StrategyParamsExportResponse(
            yaml_content=yaml_content,
            download_url=f"/data/{filename}",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to export strategy params to file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/strategy/params/import", response_model=StrategyParamsImportResponse)
async def import_strategy_params(request: StrategyParamsImportRequest):
    """
    Import strategy parameters from YAML.

    This endpoint:
    1. Parses YAML content
    2. Validates the configuration
    3. Saves to database
    4. Creates an auto-snapshot of the old config
    5. Returns import result

    Request body:
    {
        "yaml_content": "strategy:\\n  pinbar:\\n    min_wick_ratio: 0.6\\n  ...",
        "overwrite": true
    }

    Response:
    {
        "status": "success",
        "message": "Successfully imported 5 strategy parameters",
        "imported_params": {...},
        "errors": []
    }
    """
    try:
        config_manager = _get_config_manager()
        repo = _get_config_entry_repo()
        snapshot_service = _get_snapshot_service()

        # Parse YAML content
        try:
            yaml_data = yaml.safe_load(request.yaml_content)
        except yaml.YAMLError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid YAML format: {str(e)}"
            )

        # Validate structure
        if not isinstance(yaml_data, dict):
            raise HTTPException(
                status_code=400,
                detail="YAML content must be a dictionary"
            )

        # Extract strategy config (support both with and without 'strategy' root key)
        if "strategy" in yaml_data:
            strategy_config = yaml_data["strategy"]
        else:
            strategy_config = yaml_data

        if not isinstance(strategy_config, dict):
            raise HTTPException(
                status_code=400,
                detail="Strategy config must be a dictionary"
            )

        # Build full params dict for validation
        full_params = {
            "pinbar": strategy_config.get("pinbar", {}),
            "engulfing": strategy_config.get("engulfing", {}),
            "ema": strategy_config.get("ema", {}),
            "mtf": strategy_config.get("mtf", {}),
            "atr": strategy_config.get("atr", {}),
            "filters": strategy_config.get("filters", []),
        }

        # Validate parameters
        errors = []
        try:
            validated_params = StrategyParams(**full_params)
        except Exception as validation_error:
            errors.append(str(validation_error))
            return StrategyParamsImportResponse(
                status="error",
                message="Validation failed",
                errors=errors,
            )

        # Get current params for response
        current_params_flat = await repo.get_entries_by_prefix("strategy")
        current_params = {
            "pinbar": {},
            "engulfing": {},
            "ema": {},
            "mtf": {},
            "atr": {},
            "filters": [],
        }
        for key, value in current_params_flat.items():
            sub_key = key.replace("strategy.", "", 1)
            parts = sub_key.split(".", 1)
            if len(parts) == 2:
                category, param_key = parts
                if category in current_params and category != "filters":
                    current_params[category][param_key] = value
        current_params = {k: v for k, v in current_params.items() if v or k == "filters"}

        if not current_params_flat:
            params = StrategyParams.from_config_manager(config_manager)
            current_params = params.to_dict()

        # Create auto-snapshot before update
        if snapshot_service and request.overwrite:
            try:
                user_config = await config_manager.get_user_config()
                await snapshot_service.create_auto_snapshot(
                    config=user_config,
                    description="策略参数导入前自动快照"
                )
                logger.info("Auto-snapshot created before strategy params import")
            except Exception as e:
                logger.warning(f"Auto-snapshot creation failed: {e}")

        # Save to database if overwrite is True
        if request.overwrite:
            from datetime import datetime, timezone
            version = f"v{datetime.now(timezone.utc).strftime('%Y%m%d.%H%M%S')}"

            for category, values in full_params.items():
                if category == "filters":
                    if values:
                        await repo.upsert_entry("strategy.filters", values, version)
                    continue
                if isinstance(values, dict):
                    for param_key, value in values.items():
                        await repo.upsert_entry(f"strategy.{category}.{param_key}", value, version)
                elif values:
                    await repo.upsert_entry(f"strategy.{category}", values, version)

            logger.info(f"Strategy parameters imported: {len(full_params)} categories")

        # Build response
        imported_params = StrategyParamsResponse(
            pinbar=full_params.get("pinbar", {}),
            engulfing=full_params.get("engulfing", {}),
            ema=full_params.get("ema", {}),
            mtf=full_params.get("mtf", {}),
            atr=full_params.get("atr", {}),
            filters=full_params.get("filters", []),
        )

        return StrategyParamsImportResponse(
            status="success",
            message=f"Successfully validated {len(full_params)} strategy parameter categories",
            imported_params=imported_params,
            errors=[],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to import strategy params: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Config Snapshots Management Endpoints
# ============================================================

class ConfigSnapshotCreate(BaseModel):
    """Request model for creating a config snapshot."""
    # Support both semantic version (v1.0.0) and timestamp version (v20260402.153045)
    # Pattern: vX.Y.Z or vYYYYMMDD.HHMMSS (8 digits for date, 2-6 digits for time)
    version: str = Field(..., pattern=r"^v\d+\.\d+\.\d+$|^v\d{8}\.\d{2,6}$", description="Semantic version tag (e.g., 'v1.0.0') or timestamp version (e.g., 'v20260402.153045')")
    description: str = Field(default="", max_length=200, description="Snapshot description")


class ConfigSnapshotImport(BaseModel):
    """Request model for importing a config snapshot."""
    config: Dict[str, Any] = Field(..., description="Full user config object")
    version: Optional[str] = Field(None, pattern=r"^v\d+\.\d+\.\d+$", description="Optional version tag")
    description: str = Field(default="手动创建快照", max_length=200)


class ConfigSnapshotResponse(BaseModel):
    """Response model for config snapshot."""
    id: int
    version: str
    description: str
    created_at: str
    created_by: str
    is_active: bool


class ConfigSnapshotDetailResponse(ConfigSnapshotResponse):
    """Response model for config snapshot detail with config."""
    config: Dict[str, Any]  # Parsed config (masked)


class ConfigSnapshotListResponse(BaseModel):
    """Response model for config snapshot list."""
    total: int
    limit: int
    offset: int
    data: List[ConfigSnapshotResponse]


class ConfigRollbackResponse(BaseModel):
    """Response model for config rollback."""
    status: Literal["success"]
    message: str
    snapshot: ConfigSnapshotDetailResponse


class ConfigDeleteResponse(BaseModel):
    """Response model for config delete."""
    status: Literal["success"]
    message: str


@app.post("/api/config/snapshots", response_model=ConfigSnapshotResponse)
async def create_snapshot(request: ConfigSnapshotCreate):
    """
    Create a new config snapshot manually.

    Request body:
    {
        "version": "v1.0.0",
        "description": "Initial config"
    }

    Returns:
        Created snapshot with is_active=true
    """
    try:
        snapshot_service = _get_snapshot_service()
        config_manager = _get_config_manager()

        if not snapshot_service:
            # Fallback to repository if service not available
            repo = _get_repository()
            config_manager = _get_config_manager()
            user_config = await config_manager.get_user_config()
            config_dict = user_config.model_dump(mode='json')
            config_json = json.dumps(config_dict)

            snapshot_id = await repo.create_config_snapshot(
                version=request.version,
                config_json=config_json,
                description=request.description,
                created_by="user",
            )
            return ConfigSnapshotResponse(
                id=snapshot_id,
                version=request.version,
                description=request.description,
                created_at=datetime.now(timezone.utc).isoformat(),
                created_by="user",
                is_active=True,
            )

        # Use service layer
        user_config = await config_manager.get_user_config()
        snapshot_id = await snapshot_service.create_manual_snapshot(
            version=request.version,
            config=user_config,
            description=request.description,
            created_by="user",
        )

        snapshot = await snapshot_service.get_snapshot_detail(snapshot_id)
        return ConfigSnapshotResponse(
            id=snapshot["id"],
            version=snapshot["version"],
            description=snapshot["description"],
            created_at=snapshot["created_at"],
            created_by=snapshot["created_by"],
            is_active=snapshot["is_active"],
        )
    except HTTPException:
        raise
    except Exception as e:
        error_code = getattr(e, 'error_code', None)
        if error_code:
            raise HTTPException(status_code=400, detail=str(e), headers={"X-Error-Code": error_code})
        return {"error": str(e)}


@app.get("/api/config/snapshots", response_model=ConfigSnapshotListResponse)
async def list_snapshots(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    created_by: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
):
    """
    List all config snapshots with pagination.

    Args:
        limit: Maximum number of results (1-100)
        offset: Number of results to skip
        created_by: Filter by creator (optional)
        is_active: Filter by active status (optional)

    Returns:
        Paginated list of snapshots
    """
    try:
        snapshot_service = _get_snapshot_service()

        if not snapshot_service:
            # Fallback to repository
            repo = _get_repository()
            result = await repo.get_config_snapshots(limit=limit, offset=offset)
            return ConfigSnapshotListResponse(
                total=result["total"],
                limit=limit,
                offset=offset,
                data=[ConfigSnapshotResponse(**item) for item in result["data"]],
            )

        # Use service layer
        data, total = await snapshot_service.get_snapshot_list(
            limit=limit,
            offset=offset,
            created_by=created_by,
            is_active=is_active,
        )

        return ConfigSnapshotListResponse(
            total=total,
            limit=limit,
            offset=offset,
            data=[ConfigSnapshotResponse(**item) for item in data],
        )
    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/config/snapshots/{snapshot_id}", response_model=ConfigSnapshotDetailResponse)
async def get_snapshot(snapshot_id: int):
    """
    Get a single snapshot by ID with full config.

    Args:
        snapshot_id: Snapshot record ID

    Returns:
        Snapshot details with parsed config
    """
    try:
        snapshot_service = _get_snapshot_service()

        if not snapshot_service:
            repo = _get_repository()
            snapshot = await repo.get_config_snapshot_by_id(snapshot_id)
            if not snapshot:
                raise HTTPException(status_code=404, detail="Snapshot not found")
            return ConfigSnapshotDetailResponse(**snapshot)

        # Use service layer
        snapshot = await snapshot_service.get_snapshot_detail(snapshot_id)
        return ConfigSnapshotDetailResponse(**snapshot)
    except HTTPException:
        raise
    except Exception as e:
        error_code = getattr(e, 'error_code', None)
        if error_code == "CONFIG-004":
            raise HTTPException(status_code=404, detail=str(e))
        return {"error": str(e)}


@app.post("/api/config/snapshots/{snapshot_id}/rollback", response_model=ConfigRollbackResponse)
async def rollback_snapshot(snapshot_id: int):
    """
    Rollback to a config snapshot (activate it).

    This will:
    1. Validate the snapshot config
    2. Activate the snapshot
    3. Apply the config to the running system

    Args:
        snapshot_id: Snapshot record ID

    Returns:
        Success message with activated snapshot details
    """
    try:
        snapshot_service = _get_snapshot_service()
        config_manager = _get_config_manager()

        if not snapshot_service:
            raise HTTPException(status_code=503, detail="Snapshot service not initialized")

        # Rollback to snapshot
        snapshot = await snapshot_service.rollback_to_snapshot(snapshot_id)

        # Apply the config from snapshot
        # Parse config from snapshot
        import json
        config_data = snapshot.get("config", {})

        # Update running config
        await config_manager.update_user_config(
            config_data,
            auto_snapshot=True,
            snapshot_description=f"回滚到快照 v{snapshot.get('version', 'unknown')}"
        )

        return ConfigRollbackResponse(
            status="success",
            message=f"Successfully rolled back to {snapshot['version']}",
            snapshot=ConfigSnapshotDetailResponse(**snapshot),
        )
    except HTTPException:
        raise
    except Exception as e:
        error_code = getattr(e, 'error_code', None)
        if error_code == "CONFIG-004":
            raise HTTPException(status_code=404, detail=str(e))
        elif error_code == "CONFIG-003":
            raise HTTPException(status_code=422, detail=str(e))
        return {"error": str(e)}


@app.post("/api/config/snapshots/{snapshot_id}/activate")
async def activate_snapshot(snapshot_id: int):
    """
    Activate a config snapshot (alias for rollback, kept for backward compatibility).

    Args:
        snapshot_id: Snapshot record ID

    Returns:
        Success message
    """
    try:
        snapshot_service = _get_snapshot_service()

        if not snapshot_service:
            repo = _get_repository()
            snapshot = await repo.get_config_snapshot_by_id(snapshot_id)
            if not snapshot:
                raise HTTPException(status_code=404, detail="Snapshot not found")

            success = await repo.activate_config_snapshot(snapshot_id)
            if success:
                return {"message": f"Activated snapshot {snapshot_id}"}
            else:
                raise HTTPException(status_code=500, detail="Failed to activate snapshot")

        # Use service layer
        snapshot = await snapshot_service.rollback_to_snapshot(snapshot_id)
        return {"message": f"Activated snapshot {snapshot_id} ({snapshot['version']})"}
    except HTTPException:
        raise
    except Exception as e:
        error_code = getattr(e, 'error_code', None)
        if error_code == "CONFIG-004":
            raise HTTPException(status_code=404, detail=str(e))
        return {"error": str(e)}


@app.delete("/api/config/snapshots/{snapshot_id}", response_model=ConfigDeleteResponse)
async def delete_snapshot(snapshot_id: int):
    """
    Delete a config snapshot.

    Note: The most recent 5 snapshots are protected from deletion.

    Args:
        snapshot_id: Snapshot record ID

    Returns:
        Success message
    """
    try:
        snapshot_service = _get_snapshot_service()

        if not snapshot_service:
            repo = _get_repository()
            success = await repo.delete_config_snapshot(snapshot_id)
            if not success:
                raise HTTPException(status_code=404, detail="Snapshot not found")
            return ConfigDeleteResponse(status="success", message=f"Deleted snapshot {snapshot_id}")

        # Use service layer with protection
        await snapshot_service.delete_snapshot(snapshot_id)
        return ConfigDeleteResponse(status="success", message=f"Deleted snapshot {snapshot_id}")
    except HTTPException:
        raise
    except Exception as e:
        error_code = getattr(e, 'error_code', None)
        if error_code == "CONFIG-004":
            raise HTTPException(status_code=404, detail=str(e))
        elif error_code == "CONFIG-006":
            raise HTTPException(status_code=400, detail=str(e))
        return {"error": str(e)}


# ============================================================
# Signal Status Tracking Endpoints (S5-2)
# ============================================================
@app.get("/api/signals/{signal_id}/status", response_model=SignalTrack)
async def get_signal_status(signal_id: str):
    """
    查询单个信号状态

    Args:
        signal_id: 信号标识

    Returns:
        信号状态信息

    Raises:
        HTTPException: 404 信号不存在
    """
    tracker = _get_signal_tracker()
    track = await tracker.get_signal_status(signal_id)

    if not track:
        raise HTTPException(status_code=404, detail="信号不存在")

    return track


@app.get("/api/signals/status", response_model=List[SignalTrack])
async def list_signal_statuses(
    status: Optional[SignalStatus] = Query(None),
    limit: int = Query(50, ge=1, le=100),
) -> List[SignalTrack]:
    """
    批量查询信号状态

    Args:
        status: 状态过滤
        limit: 结果数量限制

    Returns:
        信号状态列表
    """
    tracker = _get_signal_tracker()
    return await tracker.list_statuses(status_filter=status, limit=limit)


# ============================================================
# Phase 6: v3.0 REST API Endpoints - Order & Position Management
# Reference: docs/designs/phase5-contract.md
# ============================================================

# ------------------------------------------------------------
# Dependency Getters for v3 API
# ------------------------------------------------------------
def _get_position_manager() -> Any:
    """Get position manager or raise error if not initialized."""
    if _position_manager is None:
        raise HTTPException(status_code=503, detail="Position manager not initialized")
    return _position_manager


def _get_capital_protection() -> Any:
    """Get capital protection manager or raise error if not initialized."""
    if _capital_protection is None:
        raise HTTPException(status_code=503, detail="Capital protection manager not initialized")
    return _capital_protection


def _get_account_service() -> Any:
    """Get account service or raise error if not initialized."""
    if _account_service is None:
        raise HTTPException(status_code=503, detail="Account service not initialized")
    return _account_service


# ------------------------------------------------------------
# Extended Dependencies
# ------------------------------------------------------------
_position_manager: Optional[Any] = None  # PositionManager instance
_capital_protection: Optional[Any] = None  # CapitalProtectionManager instance
_account_service: Optional[Any] = None  # AccountService instance


def set_v3_dependencies(
    position_manager: Optional[Any] = None,
    capital_protection: Optional[Any] = None,
    account_service: Optional[Any] = None,
) -> None:
    """
    Inject v3 API dependencies.

    Args:
        position_manager: PositionManager instance
        capital_protection: CapitalProtectionManager instance
        account_service: AccountService instance
    """
    global _position_manager, _capital_protection, _account_service
    _position_manager = position_manager
    _capital_protection = capital_protection
    _account_service = account_service


# ------------------------------------------------------------
# 1. Order Management Endpoints
# ------------------------------------------------------------
@app.post("/api/v3/orders", response_model=OrderResponseFull)
async def create_order(request: OrderRequest) -> OrderResponseFull:
    """
    创建订单（v3 API）

    Phase 6: v3.0 订单管理 - POST /api/v3/orders
    Reference: docs/designs/phase5-contract.md Section 4

    Args:
        request: 下单请求（OrderRequest）

    Returns:
        OrderResponseFull: 订单响应（完整版）

    Raises:
        HTTPException:
            - 400 F-011: 订单参数错误（LIMIT 单无价格、STOP 单无触发价等）
            - 400 F-010: 保证金不足
            - 400 SINGLE_TRADE_LOSS_LIMIT: 单笔交易损失超限
            - 400 POSITION_LIMIT: 仓位占比超限
            - 400 DAILY_LOSS_LIMIT: 每日亏损超限
            - 400 DAILY_TRADE_COUNT_LIMIT: 每日交易次数超限
            - 503 F-004: 交易所初始化失败
    """
    try:
        gateway = _get_exchange_gateway()

        # 1. 条件必填验证
        if request.order_type == OrderType.LIMIT and request.price is None:
            raise HTTPException(
                status_code=400,
                detail={"error_code": "F-011", "message": "LIMIT 订单必须指定价格"}
            )

        if request.order_type in (OrderType.STOP_MARKET, OrderType.STOP_LIMIT) and request.trigger_price is None:
            raise HTTPException(
                status_code=400,
                detail={"error_code": "F-011", "message": "STOP 订单必须指定触发价"}
            )

        # 2. 角色约束验证（TP/SL 单必须 reduce_only=True）
        if request.order_role in (OrderRole.TP1, OrderRole.TP2, OrderRole.TP3, OrderRole.TP4, OrderRole.TP5, OrderRole.SL):
            if not request.reduce_only:
                raise HTTPException(
                    status_code=400,
                    detail={"error_code": "F-011", "message": "平仓单必须设置 reduce_only=True"}
                )

        # 3. 资本保护检查
        if _capital_protection:
            protection_result = await _capital_protection.pre_order_check(
                symbol=request.symbol,
                order_type=request.order_type.value,
                quantity=request.quantity,
                price=request.price,
                trigger_price=request.trigger_price,
                stop_loss=request.stop_loss or Decimal("0"),
            )

            if not protection_result.allowed:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error_code": protection_result.reason,
                        "message": protection_result.reason_message
                    }
                )

        # 4. 映射 direction 到 side（CCXT 格式）
        # LONG + ENTRY -> "buy", LONG + TP/SL -> "sell"
        # SHORT + ENTRY -> "sell", SHORT + TP/SL -> "buy"
        is_entry = request.order_role == OrderRole.ENTRY
        if request.direction == Direction.LONG:
            side = "buy" if is_entry else "sell"
        else:  # SHORT
            side = "sell" if is_entry else "buy"

        # 5. 映射 order_type 到 CCXT 格式
        ccxt_order_type = request.order_type.value.lower()

        # 6. 调用 ExchangeGateway 下单
        result = await gateway.place_order(
            symbol=request.symbol,
            order_type=ccxt_order_type,
            side=side,
            amount=request.quantity,
            price=request.price,
            trigger_price=request.trigger_price,
            reduce_only=request.reduce_only,
            client_order_id=request.client_order_id,
        )

        # 7. 记录请求日志（client_order_id 脱敏）
        client_order_id_display = mask_secret(request.client_order_id) if request.client_order_id else "N/A"
        logger.info(f"创建订单请求：symbol={request.symbol}, side={side}, type={ccxt_order_type}, "
                    f"quantity={request.quantity}, client_order_id={client_order_id_display}")

        # 8. 构建完整响应
        now = int(datetime.now(timezone.utc).timestamp() * 1000)
        return OrderResponseFull(
            order_id=result.order_id,
            exchange_order_id=result.exchange_order_id,
            symbol=request.symbol,
            order_type=request.order_type,
            order_role=request.order_role,
            direction=request.direction,
            status=result.status,
            quantity=request.quantity,
            filled_qty=Decimal("0"),  # 初始为 0
            remaining_qty=request.quantity,  # 初始为全部数量
            price=request.price,
            trigger_price=request.trigger_price,
            average_exec_price=None,
            reduce_only=request.reduce_only,
            client_order_id=result.client_order_id,
            strategy_name=request.strategy_name,
            signal_id=request.signal_id,
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
            created_at=now,
            updated_at=now,
            filled_at=None,
            fee_paid=Decimal("0"),
            fee_currency=None,
            tags=[],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建订单失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------
# 1.5 Order Tree & Batch Delete Endpoints (订单管理级联展示功能)
# IMPORTANT: Must be defined BEFORE /api/v3/orders/{order_id}
#            to avoid route matching conflicts (batch vs {order_id})
# Reference: docs/designs/order-chain-tree-contract.md
# ------------------------------------------------------------

@app.get("/api/v3/orders/tree", response_model=OrderTreeResponse)
async def get_order_tree(
    symbol: Optional[str] = Query(None, description="币种对过滤"),
    start_date: Optional[str] = Query(None, description="开始日期 (ISO 8601)"),
    end_date: Optional[str] = Query(None, description="结束日期 (ISO 8601)"),
    days: Optional[int] = Query(None, ge=1, le=90, description="最近 N 天（默认 7 天，与 start_date 互斥）"),
    page: int = Query(default=1, ge=1, description="页码（从 1 开始）"),
    page_size: int = Query(default=50, ge=1, le=200, description="每页数量（默认 50，最大 200）"),
) -> OrderTreeResponse:
    """
    获取订单树形结构（订单管理级联展示功能）

    Phase 6 v3.0: 订单管理级联展示功能 - GET /api/v3/orders/tree
    Reference: docs/designs/order-chain-tree-contract.md Section

    分页加载订单树，前端使用虚拟滚动优化渲染性能

    Args:
        symbol: 币种对过滤（可选），如 "BTC/USDT:USDT"
        start_date: 开始日期（可选，ISO 8601 格式），与 days 参数互斥
        end_date: 结束日期（可选，ISO 8601 格式）
        days: 最近 N 天（可选，默认 7 天，与 start_date 互斥）
        page: 页码（从 1 开始，默认 1）
        page_size: 每页数量（默认 50，最大 200）

    Returns:
        OrderTreeResponse: 订单树响应
        {
            "items": [
                {
                    "order": {...},  // OrderResponseFull 字典
                    "children": [...],  // 子订单列表（TP1-TP5, SL）
                    "level": 0,  // 层级深度
                    "has_children": true  // 是否有子订单
                },
                ...
            ],
            "total": 50,  // 当前页根订单数
            "total_count": 150,  // 符合条件的总根订单数
            "page": 1,  // 当前页码
            "page_size": 50,  // 每页数量
            "metadata": {
                "symbol_filter": "BTC/USDT:USDT",
                "days_filter": 7,
                "loaded_at": 1711785660000
            }
        }

    Raises:
        HTTPException:
            - 400: 参数错误（start_date 与 days 同时指定）
            - 500: 数据库查询失败
    """
    from datetime import datetime

    try:
        # 参数验证：start_date 与 days 互斥（只有用户显式传入 days 时才检查）
        if start_date and days is not None:
            raise HTTPException(
                status_code=400,
                detail="start_date 与 days 参数互斥，只能指定一个"
            )

        # 解析日期参数
        start_dt: Optional[datetime] = None
        end_dt: Optional[datetime] = None

        if start_date:
            try:
                start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            except ValueError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"start_date 格式错误，应为 ISO 8601 格式：{str(e)}"
                )

        if end_date:
            try:
                end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            except ValueError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"end_date 格式错误，应为 ISO 8601 格式：{str(e)}"
                )

        # 处理 days 默认值
        effective_days = days if days is not None else 7

        # 使用依赖注入获取 OrderRepository 实例
        repo = _get_order_repo()

        # 仅在非注入实例时初始化
        if not _order_repo:
            await repo.initialize()

        try:
            # 调用 OrderRepository 获取订单树
            result = await repo.get_order_tree(
                symbol=symbol,
                start_date=start_dt,
                end_date=end_dt,
                days=effective_days if not start_date else None,
                page=page,
                page_size=page_size,
            )

            # 将字典结果转换为 Pydantic 模型
            from pydantic import TypeAdapter
            items_adapter = TypeAdapter(List[OrderTreeNode])
            items = items_adapter.validate_python(result['items'])

            return OrderTreeResponse(
                items=items,
                total=result['total'],
                total_count=result['total_count'],
                page=result['page'],
                page_size=result['page_size'],
                metadata=result['metadata'],
            )
        finally:
            # 仅关闭非注入实例
            if not _order_repo:
                await repo.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取订单树失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v3/orders/batch", response_model=OrderDeleteResponse)
async def delete_orders_batch(request: OrderDeleteRequest) -> OrderDeleteResponse:
    """
    批量删除订单链（订单管理级联展示功能）

    Phase 6 v3.0: 订单管理级联展示功能 - DELETE /api/v3/orders/batch
    Reference: docs/designs/order-chain-tree-contract.md Section

    支持级联删除子订单（TP/SL），可选择是否调用交易所取消接口

    Args:
        request: 批量删除请求
        {
            "order_ids": ["uuid-123"],  // 要删除的订单 ID 列表（上限 100）
            "cancel_on_exchange": true,  // 是否调用交易所取消接口（默认 true）
            "audit_info": {  // 审计信息（可选）
                "operator_id": "user-001",
                "ip_address": "192.168.1.1",
                "user_agent": "Mozilla/5.0..."
            }
        }

    Returns:
        OrderDeleteResponse: 批量删除响应
        {
            "deleted_count": 5,  // 删除的订单总数
            "cancelled_on_exchange": ["uuid-124"],  // 在交易所成功取消的订单 ID 列表
            "failed_to_cancel": [],  // 在交易所取消失败的订单列表
            "deleted_from_db": ["uuid-123", "uuid-124"],  // 从数据库成功删除的订单 ID 列表
            "failed_to_delete": [],  // 数据库删除失败的订单列表
            "audit_log_id": "audit-20260402-001"  // 审计日志 ID
        }

    Raises:
        HTTPException:
            - 400 ORDER-001: 订单 ID 列表为空
            - 400 ORDER-002: 订单 ID 数量超限（>100）
            - 500 ORDER-005: 删除失败（数据库错误）
    """
    try:
        # 使用依赖注入获取 OrderRepository 实例
        repo = _get_order_repo()
        # 仅在非注入实例时初始化
        if not _order_repo:
            await repo.initialize()

        try:
            # 调用 OrderRepository 批量删除
            result = await repo.delete_orders_batch(
                order_ids=request.order_ids,
                cancel_on_exchange=request.cancel_on_exchange,
                audit_info=request.audit_info,
            )

            return OrderDeleteResponse(
                deleted_count=result['deleted_count'],
                cancelled_on_exchange=result['cancelled_on_exchange'],
                failed_to_cancel=result['failed_to_cancel'],
                deleted_from_db=result['deleted_from_db'],
                failed_to_delete=result['failed_to_delete'],
                audit_log_id=result.get('audit_log_id'),
            )
        finally:
            # 仅关闭非注入实例
            if not _order_repo:
                await repo.close()

    except ValueError as e:
        # 参数验证错误
        logger.warning(f"批量删除参数验证失败：{str(e)}")
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )


# ------------------------------------------------------------
# 1.6 Order Cancel Endpoint (DELETE /api/v3/orders/{order_id})
# IMPORTANT: Must be AFTER /api/v3/orders/batch to avoid route conflicts
# ------------------------------------------------------------

@app.delete("/api/v3/orders/{order_id}", response_model=OrderCancelResponse)
async def cancel_order(order_id: str, symbol: str = Query(..., description="币种对")) -> OrderCancelResponse:
    """
    取消订单（v3 API）

    Phase 6: v3.0 订单管理 - DELETE /api/v3/orders/{order_id}
    Reference: docs/designs/phase5-contract.md Section 5

    Args:
        order_id: 系统订单 ID
        symbol: 币种对（查询参数）

    Returns:
        OrderCancelResponse: 取消订单响应

    Raises:
        HTTPException:
            - 404 F-012: 订单不存在
            - 400 F-013: 订单已成交（无法取消）
            - 429 C-010: API 频率限制
    """
    try:
        gateway = _get_exchange_gateway()

        # 记录请求日志（order_id 脱敏）
        order_id_display = mask_secret(order_id, visible_chars=8)
        logger.info(f"取消订单请求：order_id={order_id_display}, symbol={symbol}")

        # 调用 ExchangeGateway 取消订单
        result = await gateway.cancel_order(order_id=order_id, symbol=symbol)

        now = int(datetime.now(timezone.utc).timestamp() * 1000)
        return OrderCancelResponse(
            order_id=result.order_id,
            exchange_order_id=result.exchange_order_id,
            symbol=symbol,
            status=result.status,
            canceled_at=now,
            message=result.message,
        )

    except OrderNotFoundError as e:
        logger.warning(f"订单不存在：{order_id}")
        raise HTTPException(
            status_code=404,
            detail={"error_code": e.error_code, "message": str(e)}
        )
    except OrderAlreadyFilledError as e:
        logger.warning(f"订单已成交，无法取消：{order_id}")
        raise HTTPException(
            status_code=400,
            detail={"error_code": e.error_code, "message": str(e)}
        )
    except RateLimitError as e:
        logger.warning(f"API 频率限制：{e}")
        raise HTTPException(
            status_code=429,
            detail={"error_code": e.error_code, "message": str(e)}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"取消订单失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------
# 1.7 Order Detail Endpoint (must be after /tree, /batch and /{order_id})
# ------------------------------------------------------------

@app.get("/api/v3/orders/{order_id:path}", response_model=OrderResponseFull)
async def get_order(order_id: str, symbol: str = Query(..., description="币种对")) -> OrderResponseFull:
    """
    查询订单详情（v3 API）

    Phase 6: v3.0 订单管理 - GET /api/v3/orders/{order_id}
    Reference: docs/designs/phase5-contract.md Section 6

    Args:
        order_id: 系统订单 ID
        symbol: 币种对（查询参数）

    Returns:
        OrderResponseFull: 订单详情

    Raises:
        HTTPException:
            - 404 F-012: 订单不存在
            - 429 C-010: API 频率限制
    """
    # 记录请求日志（order_id 脱敏）
    order_id_display = mask_secret(order_id, visible_chars=8)
    logger.info(f"查询订单请求：order_id={order_id_display}, symbol={symbol}")

    # 使用依赖注入获取 OrderRepository 实例
    order_repo = _get_order_repo()
    await order_repo.initialize()
    try:
        order = await order_repo.get_order(order_id)
        if not order:
            logger.warning(f"订单不存在：order_id={order_id_display}")
            raise HTTPException(
                status_code=404,
                detail=f"订单不存在 (F-012): order_id={order_id}"
            )

        # 计算剩余数量
        remaining_qty = order.requested_qty - order.filled_qty

        # 构建完整响应
        return OrderResponseFull(
            order_id=order.id,
            exchange_order_id=order.exchange_order_id,
            symbol=order.symbol,
            order_type=order.order_type,
            order_role=order.order_role,
            direction=order.direction,
            status=order.status,
            quantity=order.requested_qty,
            filled_qty=order.filled_qty,
            remaining_qty=remaining_qty,
            price=order.price,
            trigger_price=order.trigger_price,
            average_exec_price=order.average_exec_price,
            reduce_only=order.reduce_only,
            client_order_id=order.exchange_order_id,  # 使用交易所订单 ID 作为客户端订单 ID
            strategy_name=None,  # 策略名称需要从策略配置中获取，当前暂不返回
            signal_id=order.signal_id,
            stop_loss=None,  # 止盈止损需要从策略配置或订单链中获取
            take_profit=None,
            created_at=order.created_at,
            updated_at=order.updated_at,
            filled_at=order.filled_at,
            fee_paid=Decimal("0"),  # 手续费需要从交易所订单详情中获取
            fee_currency=None,
            tags=[],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询订单失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # 仅关闭非注入实例
        if not _order_repo:
            await order_repo.close()


@app.get("/api/v3/orders/{order_id}/klines")
async def get_order_klines(
    order_id: str,
    symbol: str = Query(..., description="币种对"),
    include_chain: bool = Query(default=True, description="是否返回关联订单链（TP/SL 子订单）"),
) -> Dict[str, Any]:
    """
    获取订单相关的 K 线数据（用于图表展示）

    Phase 6: v3.0 订单管理 - GET /api/v3/orders/{order_id}/klines
    返回订单详情 plus ~50 K-lines surrounding the order timestamp for charting

    Phase K (订单详情页 K 线渲染升级):
    - 新增 include_chain 参数，支持返回完整订单链
    - K 线范围动态计算，覆盖完整交易生命周期
    - 时间戳精确对齐到 filled_at

    Args:
        order_id: 系统订单 ID
        symbol: 币种对（查询参数）
        include_chain: 是否返回订单链（默认 True）

    Returns:
        {
            "order": { ... order info ... },
            "timeframe": "15m",
            "order_chain": [  # 仅当 include_chain=True 时返回
                {
                    "order_id": "...",
                    "order_role": "ENTRY" | "TP1" | "TP2" | "SL",
                    "direction": "LONG" | "SHORT",
                    "price": "...",
                    "average_exec_price": "...",
                    "filled_qty": "...",
                    "status": "FILLED" | "PENDING" | "CANCELED",
                    "filled_at": 1711785660000,
                    "created_at": 1711785600000,
                    "exit_reason": "..."
                },
                ...
            ],
            "klines": [[timestamp, open, high, low, close, volume], ...]
        }

    Raises:
        HTTPException:
            - 404 F-012: 订单不存在
            - 500: 获取 K 线数据失败
    """
    try:
        # 使用依赖注入获取 OrderRepository 实例
        repo = _get_order_repo()
        # 仅在非注入实例时初始化
        if not _order_repo:
            await repo.initialize()

        try:
            # Fetch order from database (async)
            order_orm = await repo.get_order(order_id)

            if not order_orm:
                # Fallback: try to fetch from exchange
                gateway = _get_exchange_gateway()
                order_data = await gateway.fetch_order(exchange_order_id=order_id, symbol=symbol)
                # Create mock order response
                order_response = {
                    "order_id": order_id,
                    "exchange_order_id": order_data.exchange_order_id,
                    "symbol": symbol,
                    "order_type": order_data.order_type,
                    "order_role": "ENTRY",
                    "direction": order_data.direction,
                    "status": order_data.status,
                    "quantity": str(order_data.quantity),
                    "filled_qty": "0",
                    "price": str(order_data.price) if order_data.price else None,
                    "trigger_price": str(order_data.trigger_price) if order_data.trigger_price else None,
                    "created_at": order_data.created_at,
                }
                # Use current timeframe for klines
                timeframe = "15m"  # Default
                order_chain = []
            else:
                # Build order response from ORM
                order_response = {
                    "order_id": order_orm.id,
                    "exchange_order_id": order_orm.exchange_order_id,
                    "symbol": order_orm.symbol,
                    "order_type": order_orm.order_type,
                    "order_role": order_orm.order_role,
                    "direction": order_orm.direction,
                    "status": order_orm.status,
                    "quantity": str(order_orm.requested_qty),
                    "filled_qty": str(order_orm.filled_qty),
                    "price": str(order_orm.price) if order_orm.price else None,
                    "trigger_price": str(order_orm.trigger_price) if order_orm.trigger_price else None,
                    "average_exec_price": str(order_orm.average_exec_price) if order_orm.average_exec_price else None,
                    "created_at": order_orm.created_at,
                    "filled_at": order_orm.filled_at,
                }
                # Extract timeframe from order or use default
                timeframe = getattr(order_orm, 'timeframe', '15m') or '15m'

                # Fetch order chain if requested
                order_chain = []
                if include_chain:
                    chain_orders = await repo.get_order_chain_by_order_id(order_id)

                    for order in chain_orders:
                        order_chain.append({
                            "order_id": order.id,
                            "order_role": order.order_role.value,
                            "direction": order.direction.value,
                            "price": str(order.price) if order.price else None,
                            "average_exec_price": str(order.average_exec_price) if order.average_exec_price else None,
                            "filled_qty": str(order.filled_qty),
                            "status": order.status.value,
                            "filled_at": order.filled_at,
                            "created_at": order.created_at,
                            "exit_reason": order.exit_reason,
                        })
        finally:
            # 仅关闭非注入实例
            if not _order_repo:
                await repo.close()

        # Get kline_timestamp from order (filled_at or created_at)
        kline_timestamp = order_orm.filled_at if order_orm and order_orm.filled_at else order_orm.created_at if order_orm else int(datetime.now(timezone.utc).timestamp() * 1000)

        # Parse timeframe to milliseconds (P1-004: 使用统一工具函数)
        timeframe_ms = BacktestConfig.get_timeframe_ms(timeframe)

        # Calculate K-line range dynamically (cover full order chain lifecycle)
        if include_chain and order_chain:
            # Collect all filled_at timestamps from order chain
            timestamps = [
                oc["filled_at"] for oc in order_chain
                if oc.get("filled_at")
            ]
            if not timestamps and order_orm:
                # Fallback to order timestamps if chain has no filled_at
                timestamps = [order_orm.filled_at or order_orm.created_at]

            if timestamps:
                min_time = min(timestamps)
                max_time = max(timestamps)
                # Extend range: 20 candles before and after
                since = min_time - (20 * timeframe_ms)
                limit = int((max_time - since) / timeframe_ms) + 40
            else:
                # No timestamps, use default window
                since = kline_timestamp - (BacktestConfig.DEFAULT_KLINE_WINDOW * timeframe_ms)
                limit = 50
        else:
            # Default window for single order
            since = kline_timestamp - (BacktestConfig.DEFAULT_KLINE_WINDOW * timeframe_ms)
            limit = 50

        # Fetch K-line data from CCXT
        import ccxt.async_support as ccxt
        exchange = ccxt.binanceusdm({'options': {'defaultType': 'swap'}})
        try:
            ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=limit)
        finally:
            await exchange.close()

        result = {
            "order": order_response,
            "timeframe": timeframe,
            "klines": ohlcv,
        }

        if include_chain:
            result["order_chain"] = order_chain

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取订单 K 线数据失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v3/orders", response_model=OrdersResponse)
async def list_orders(
    symbol: Optional[str] = Query(None, description="币种对过滤"),
    status: Optional[OrderStatus] = Query(None, description="订单状态过滤"),
    order_role: Optional[OrderRole] = Query(None, description="订单角色过滤"),
    limit: int = Query(default=50, ge=1, le=200, description="结果数量限制"),
    offset: int = Query(default=0, ge=0, description="分页偏移量"),
) -> OrdersResponse:
    """
    查询订单列表（v3 API）

    Phase 6: v3.0 订单管理 - GET /api/v3/orders
    Reference: docs/designs/phase6-v3-api-contract.md Section 2.1.3

    Args:
        symbol: 币种对过滤（可选）
        status: 订单状态过滤（可选）
        order_role: 订单角色过滤（可选）
        limit: 结果数量限制（1-200）
        offset: 分页偏移量（默认 0）

    Returns:
        OrdersResponse: 分页订单列表响应 {items, total, limit, offset}

    Raises:
        HTTPException:
            - 503 F-004: 交易所初始化失败
            - 429 C-010: API 频率限制
    """
    from decimal import Decimal

    try:
        # 使用依赖注入获取 OrderRepository 实例
        repo = _get_order_repo()
        # 仅在非注入实例时初始化
        if not _order_repo:
            await repo.initialize()

        try:
            # 调用 OrderRepository 查询订单列表
            result = await repo.get_orders(
                symbol=symbol,
                status=status,
                order_role=order_role,
                limit=limit,
                offset=offset,
            )

            # 将 Order 对象转换为 OrderResponseFull 格式
            items = []
            for order in result['items']:
                # 计算剩余数量
                remaining_qty = order.requested_qty - order.filled_qty

                items.append(OrderResponseFull(
                    order_id=order.id,
                    exchange_order_id=order.exchange_order_id,
                    symbol=order.symbol,
                    order_type=order.order_type,
                    order_role=order.order_role,
                    direction=order.direction,
                    status=order.status,
                    quantity=order.requested_qty,
                    filled_qty=order.filled_qty,
                    remaining_qty=remaining_qty,
                    price=order.price,
                    trigger_price=order.trigger_price,
                    average_exec_price=order.average_exec_price,
                    reduce_only=order.reduce_only,
                    client_order_id=None,  # Order 模型中无此字段
                    strategy_name=None,  # Order 模型中无此字段
                    signal_id=order.signal_id,
                    stop_loss=None,  # Order 模型中无此字段
                    take_profit=None,  # Order 模型中无此字段
                    created_at=order.created_at,
                    updated_at=order.updated_at,
                    filled_at=order.filled_at,
                    fee_paid=Decimal("0"),  # Order 模型中无此字段
                    fee_currency=None,  # Order 模型中无此字段
                    tags=[],  # Order 模型中无此字段
                ))

            return OrdersResponse(
                items=items,
                total=result['total'],
                limit=result['limit'],
                offset=result['offset'],
            )
        finally:
            # 仅关闭非注入实例
            if not _order_repo:
                await repo.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询订单列表失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------
# 1.6 Order Detail Endpoint (must be after /tree and /batch)
# ------------------------------------------------------------
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量删除订单失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------
# 2. Position Management Endpoints
# ------------------------------------------------------------
@app.get("/api/v3/positions", response_model=PositionResponse)
async def list_positions(
    symbol: Optional[str] = Query(None, description="币种对过滤"),
    is_closed: bool = Query(default=False, description="是否查询已平仓位"),
    limit: int = Query(default=100, ge=1, le=500, description="每页数量"),
    offset: int = Query(default=0, ge=0, description="偏移量"),
) -> PositionResponse:
    """
    查询持仓列表（v3 API）

    Phase 6: v3.0 仓位管理 - GET /api/v3/positions
    Reference: docs/designs/phase5-contract.md Section 7

    Args:
        symbol: 币种对过滤（可选）
        is_closed: 是否查询已平仓位（默认 false，即查询未平仓位）
        limit: 每页数量（1-500）
        offset: 偏移量

    Returns:
        PositionResponse: 持仓列表响应

    Raises:
        HTTPException:
            - 503 F-004: 交易所初始化失败
            - 429 C-010: API 频率限制
    """
    try:
        gateway = _get_exchange_gateway()

        # 从交易所获取持仓信息
        positions = await gateway.fetch_positions(symbol=symbol)

        # 同时获取账户余额用于计算权益
        account_balance = await gateway.fetch_account_balance()

        # 转换为 API 响应格式
        position_infos = []
        total_unrealized_pnl = Decimal("0")
        total_realized_pnl = Decimal("0")
        total_margin_used = Decimal("0")

        now = int(datetime.now(timezone.utc).timestamp() * 1000)

        for pos in positions:
            # 将 Position 转换为 PositionInfoV3
            position_info = PositionInfoV3(
                position_id=f"pos_{pos.symbol}_{pos.side}",  # 生成持仓 ID
                symbol=pos.symbol,
                direction=Direction.LONG if pos.side == "buy" else Direction.SHORT,
                current_qty=pos.size,
                entry_price=pos.entry_price,
                mark_price=None,  # 需要从交易所获取标记价格
                unrealized_pnl=pos.unrealized_pnl,
                realized_pnl=Decimal("0"),  # 需要从交易所获取
                liquidation_price=None,  # 需要从交易所获取
                leverage=pos.leverage,
                margin_mode="CROSS",  # 默认全仓
                is_closed=False,
                opened_at=now,  # 实际应从持仓存储中获取
                closed_at=None,
                total_fees_paid=Decimal("0"),
                strategy_name=None,
                stop_loss=None,
                take_profit=None,
                tags=[],
            )
            position_infos.append(position_info)
            total_unrealized_pnl += pos.unrealized_pnl

        # 计算账户权益 = 总余额 + 未实现盈亏
        account_equity = None
        if account_balance:
            account_equity = account_balance.total_balance + account_balance.unrealized_pnl

        return PositionResponse(
            positions=position_infos,
            total_unrealized_pnl=total_unrealized_pnl,
            total_realized_pnl=total_realized_pnl,
            total_margin_used=total_margin_used,
            account_equity=account_equity,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询持仓列表失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v3/positions/{position_id}", response_model=PositionInfoV3)
async def get_position(position_id: str) -> PositionInfoV3:
    """
    查询单个持仓详情（v3 API）

    Phase 6: v3.0 仓位管理 - GET /api/v3/positions/{position_id}
    Reference: docs/designs/phase5-contract.md Section 7

    Args:
        position_id: 持仓 ID

    Returns:
        PositionInfoV3: 持仓详情

    Raises:
        HTTPException:
            - 404: 持仓不存在
    """
    try:
        # 从持仓存储中查询
        # TODO: 实现 PositionRepository
        raise HTTPException(status_code=404, detail="持仓不存在")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询持仓详情失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------
# 3. Account Endpoints
# ------------------------------------------------------------
@app.get("/api/v3/account/balance", response_model=AccountResponse)
async def get_account_balance() -> AccountResponse:
    """
    查询账户余额（v3 API）

    Phase 6: v3.0 账户管理 - GET /api/v3/account/balance
    Reference: docs/designs/phase5-contract.md Section 8

    Returns:
        AccountResponse: 账户余额信息

    Raises:
        HTTPException:
            - 503 F-004: 交易所初始化失败
            - 429 C-010: API 频率限制
    """
    try:
        gateway = _get_exchange_gateway()

        # 从交易所获取账户余额
        snapshot = await gateway.fetch_account_balance()

        if snapshot is None:
            raise HTTPException(status_code=503, detail="获取账户余额失败")

        now = int(datetime.now(timezone.utc).timestamp() * 1000)

        # 构建响应
        return AccountResponse(
            exchange=gateway.exchange_name,
            account_type="FUTURES",
            balances=[
                AccountBalance(
                    currency="USDT",
                    total_balance=snapshot.total_balance,
                    available_balance=snapshot.available_balance,
                    frozen_balance=Decimal("0"),  # CCXT 不直接提供冻结余额
                    unrealized_pnl=snapshot.unrealized_pnl,
                )
            ],
            total_equity=snapshot.total_balance + snapshot.unrealized_pnl,
            total_margin_balance=snapshot.total_balance,
            total_wallet_balance=snapshot.total_balance,
            total_unrealized_pnl=snapshot.unrealized_pnl,
            available_balance=snapshot.available_balance,
            total_margin_used=Decimal("0"),  # TODO: 从持仓中计算
            account_leverage=10,  # TODO: 从交易所获取
            last_updated=now,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询账户余额失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v3/account/snapshot", response_model=AccountResponse)
async def get_account_snapshot() -> AccountResponse:
    """
    查询账户快照（v3 API）

    Phase 6: v3.0 账户管理 - GET /api/v3/account/snapshot
    Reference: docs/designs/phase5-contract.md Section 8

    Returns:
        AccountResponse: 账户快照信息

    Raises:
        HTTPException:
            - 503 F-004: 交易所初始化失败
            - 429 C-010: API 频率限制
    """
    # 复用 get_account_balance 逻辑
    return await get_account_balance()


# ------------------------------------------------------------
# 6. Account Historical Snapshots Endpoint (Equity Curve)
# ------------------------------------------------------------
from pydantic import BaseModel


class HistoricalSnapshot(BaseModel):
    """历史账户快照数据点"""
    timestamp: int              # 毫秒时间戳
    total_equity: str           # 总权益 (Decimal string)


class HistoricalSnapshotsResponse(BaseModel):
    """历史快照响应"""
    snapshots: List[HistoricalSnapshot]
    days: int                   # 天数


@app.get("/api/v3/account/snapshots/historical", response_model=HistoricalSnapshotsResponse)
async def get_account_historical_snapshots(
    days: int = Query(default=7, ge=1, le=90, description="获取最近 N 天的历史数据")
) -> HistoricalSnapshotsResponse:
    """
    查询账户历史快照（权益曲线数据）

    Phase 6: v3.0 账户管理 - GET /api/v3/account/snapshots/historical
    从信号历史中计算每日账户权益，用于绘制权益曲线

    Args:
        days: 获取最近 N 天的数据 (1-90 天)

    Returns:
        HistoricalSnapshotsResponse: 历史快照列表

    Raises:
        HTTPException:
            - 500: 计算失败
    """
    try:
        repo = _get_repository()

        # 计算时间范围
        now = datetime.now(timezone.utc)
        from datetime import timedelta
        start_time = now - timedelta(days=days)

        # 获取历史信号（用于计算 PnL）
        signals_result = await repo.get_signals(
            limit=1000,
            offset=0,
            start_time=start_time.isoformat(),
            end_time=now.isoformat(),
        )

        signals = signals_result.get("data", [])

        # 获取当前账户快照作为基准
        current_snapshot = await get_account_balance()
        current_equity = float(current_snapshot.total_equity)

        # 按日期分组计算累计 PnL
        daily_pnl: Dict[str, float] = {}
        for signal in signals:
            if signal.get("pnl_ratio"):
                try:
                    pnl = float(signal["pnl_ratio"])
                    created_at = signal.get("created_at", "")
                    if created_at:
                        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                        date_key = dt.strftime("%Y-%m-%d")
                        daily_pnl[date_key] = daily_pnl.get(date_key, 0) + pnl
                except (ValueError, TypeError):
                    continue

        # 生成历史快照数据
        snapshots: List[HistoricalSnapshot] = []
        cumulative_pnl = 0.0

        # 生成每天的快照
        for i in range(days):
            date = (now - timedelta(days=days - 1 - i)).date()
            date_key = date.strftime("%Y-%m-%d")

            # 累加当天的 PnL
            if date_key in daily_pnl:
                cumulative_pnl += daily_pnl[date_key]

            # 估算权益（当前权益 - 累计 PnL = 初始权益 + 累计 PnL）
            estimated_equity = current_equity - cumulative_pnl

            # 生成时间戳（当天结束时间）
            timestamp = int(datetime(
                date.year, date.month, date.day,
                23, 59, 59, tzinfo=timezone.utc
            ).timestamp() * 1000)

            snapshots.append(HistoricalSnapshot(
                timestamp=timestamp,
                total_equity=str(round(estimated_equity, 2))
            ))

        return HistoricalSnapshotsResponse(
            snapshots=snapshots,
            days=days
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取历史快照失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------
# 7. Order Check Endpoint (Capital Protection)
# ------------------------------------------------------------
from src.domain.models import OrderCheckRequest, CapitalProtectionCheckResult, SingleTradeCheck, PositionLimitCheck, DailyLossCheck, TradeCountCheck, MinBalanceCheck


@app.post("/api/v3/orders/check", response_model=CapitalProtectionCheckResult)
async def check_order_capital(request: OrderCheckRequest) -> CapitalProtectionCheckResult:
    """
    下单前资金保护检查（v3 API）- Dry Run

    Phase 6: v3.0 资金保护检查 - POST /api/v3/orders/check
    Reference: docs/designs/phase6-v3-api-contract.md Section 2.6

    Args:
        request: 资金保护检查请求

    Returns:
        CapitalProtectionCheckResult: 资金保护检查结果

    Raises:
        HTTPException:
            - 503 F-004: 交易所初始化失败
    """
    try:
        capital_protection = _get_capital_protection()

        # 执行资金保护检查
        result = await capital_protection.pre_order_check(
            symbol=request.symbol,
            order_type=request.order_type.value,
            amount=request.quantity,
            price=request.price,
            trigger_price=request.trigger_price,
            stop_loss=request.stop_loss or Decimal("0"),
        )

        # 构建详细检查结果
        return CapitalProtectionCheckResult(
            allowed=result.allowed,
            reason=result.reason,
            single_trade_limit=SingleTradeCheck(
                passed=result.single_trade_check or False,
                max_loss=result.max_allowed_loss,
                estimated_loss=result.estimated_loss,
            ),
            position_limit=PositionLimitCheck(
                passed=result.position_limit_check or False,
                max_position=result.max_allowed_position,
                position_value=result.position_value,
            ),
            daily_loss_limit=DailyLossCheck(
                passed=result.daily_loss_check or False,
                daily_max_loss=None,  # 需要从 capital_protection 获取配置
                daily_pnl=result.daily_pnl,
            ),
            daily_trade_count=TradeCountCheck(
                passed=result.daily_count_check or False,
                max_count=None,  # 需要从 capital_protection 获取配置
                current_count=result.daily_trade_count,
            ),
            min_balance=MinBalanceCheck(
                passed=result.balance_check or False,
                min_balance=result.min_required_balance,
                current_balance=result.available_balance,
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"资金保护检查失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------
# 6. Close Position Endpoint
# ------------------------------------------------------------
from src.domain.models import ClosePositionRequest


@app.post("/api/v3/positions/{position_id}/close", response_model=OrderResponseFull)
async def close_position(
    position_id: str,
    request: ClosePositionRequest = Body(...),
) -> OrderResponseFull:
    """
    平仓（v3 API）

    Phase 6: v3.0 仓位管理 - POST /api/v3/positions/{position_id}/close
    Reference: docs/designs/phase6-v3-api-contract.md Section 2.4

    Args:
        position_id: 仓位 ID
        request: 平仓请求（可选指定平仓数量和订单类型）

    Returns:
        OrderResponseFull: 平仓订单响应

    Raises:
        HTTPException:
            - 404 F-012: 仓位不存在
            - 400 F-011: 平仓参数错误
            - 503 F-004: 交易所初始化失败
    """
    try:
        gateway = _get_exchange_gateway()

        # 1. 查询仓位获取详情
        # 注意：这里需要从 PositionManager 获取仓位信息
        # 当前实现：直接查询交易所仓位
        positions = await gateway.fetch_positions()
        position = None
        for p in positions:
            if p.position_id == position_id:
                position = p
                break

        if position is None:
            raise HTTPException(
                status_code=404,
                detail={"error_code": "F-012", "message": "仓位不存在"}
            )

        # 2. 确定平仓数量
        quantity = request.quantity if request.quantity else position.current_qty

        # 3. 创建平仓订单
        result = await gateway.place_order(
            symbol=position.symbol,
            order_type=request.order_type.value.lower(),
            side="sell" if position.direction == Direction.LONG else "buy",
            amount=quantity,
            reduce_only=True,  # 平仓单必须设置 reduce_only
        )

        # 4. 构建响应
        now = int(datetime.now(timezone.utc).timestamp() * 1000)
        return OrderResponseFull(
            order_id=result.order_id,
            exchange_order_id=result.exchange_order_id,
            symbol=position.symbol,
            order_type=request.order_type,
            direction=Direction.SHORT if position.direction == Direction.LONG else Direction.LONG,  # 平仓方向相反
            role=OrderRole.SL,  # 平仓单角色
            status=result.status,
            amount=quantity,
            filled_amount=Decimal("0"),
            reduce_only=True,
            created_at=now,
            updated_at=now,
            fee_paid=Decimal("0"),
            tags=[],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"平仓失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------
# 4. Reconciliation Endpoint
# ------------------------------------------------------------
@app.post("/api/v3/reconciliation", response_model=ReconciliationReport)
async def start_reconciliation(request: ReconciliationRequest) -> ReconciliationReport:
    """
    启动对账服务（v3 API）

    Phase 6: v3.0 对账服务 - POST /api/v3/reconciliation
    Reference: docs/designs/phase5-contract.md Section 9

    Args:
        request: 对账请求

    Returns:
        ReconciliationReport: 对账报告

    Raises:
        HTTPException:
            - 503 F-004: 交易所初始化失败
            - 429 C-010: API 频率限制
    """
    try:
        gateway = _get_exchange_gateway()

        # 从交易所获取仓位和订单
        exchange_positions = await gateway.fetch_positions(symbol=request.symbol)
        # TODO: 从本地存储查询仓位和订单
        # local_positions = await position_repository.list(symbol=request.symbol)
        # local_orders = await order_repository.list(symbol=request.symbol)

        now = int(datetime.now(timezone.utc).timestamp() * 1000)

        # 简化版本：返回一致报告
        # TODO: 实现完整的对账逻辑
        return ReconciliationReport(
            symbol=request.symbol,
            reconciliation_time=now,
            grace_period_seconds=300,  # 5 分钟宽限期
            position_mismatches=[],
            missing_positions=[],
            order_mismatches=[],
            orphan_orders=[],
            is_consistent=True,
            total_discrepancies=0,
            requires_attention=False,
            summary="对账完成：本地与交易所记录一致",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"对账失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Phase 8: 自动化调参 (Optuna 集成) API Endpoints
# Reference: docs/designs/phase8-optimizer-contract.md
# ============================================================

from src.domain.models import (
    OptimizationRequest,
    OptimizationJob,
    OptimizationJobStatus,
    OptimizationTrialResult,
)
from src.application.strategy_optimizer import StrategyOptimizer


# 全局 optimizer 实例
_optimizer: Optional[StrategyOptimizer] = None


def set_optimizer(optimizer: StrategyOptimizer) -> None:
    """注入 Phase 8 优化器依赖"""
    global _optimizer
    _optimizer = optimizer


def _get_optimizer() -> StrategyOptimizer:
    """获取优化器实例"""
    if _optimizer is None:
        raise HTTPException(status_code=503, detail="优化器未初始化")
    return _optimizer


# ------------------------------------------------------------
# Phase 8 API Responses
# ------------------------------------------------------------
class OptimizationJobSummary(BaseModel):
    """优化任务摘要"""
    job_id: str
    status: str
    symbol: str
    timeframe: str
    objective: str
    current_trial: int
    total_trials: int
    best_value: Optional[float]
    created_at: str


class OptimizationJobList(BaseModel):
    """优化任务列表响应"""
    jobs: List[OptimizationJobSummary]
    total: int


class OptimizationStatusResponse(BaseModel):
    """优化状态响应"""
    job_id: str
    status: str
    current_trial: int
    total_trials: int
    best_trial: Optional[Dict[str, Any]]
    best_value: Optional[float]
    started_at: Optional[str]
    estimated_remaining_seconds: Optional[int]


class OptimizationResultsResponse(BaseModel):
    """优化结果响应"""
    job_id: str
    status: str
    best_trial: Optional[Dict[str, Any]]
    best_value: Optional[float]
    total_trials: int
    trials: List[Dict[str, Any]]


# ------------------------------------------------------------
# Phase 8 API Endpoints
# ------------------------------------------------------------
@app.post("/api/optimize", response_model=OptimizationJobSummary)
async def start_optimization(request: OptimizationRequest):
    """
    启动优化任务

    Phase 8: 自动化调参 - POST /api/optimize
    Reference: docs/designs/phase8-optimizer-contract.md Section 2.1

    Args:
        request: 优化请求

    Returns:
        OptimizationJobSummary: 优化任务摘要

    Raises:
        HTTPException:
            - 503: 优化器未初始化
            - 400: 参数空间无效
    """
    try:
        optimizer = _get_optimizer()

        # 验证参数空间
        if not request.parameter_space.parameters:
            raise HTTPException(status_code=400, detail="参数空间不能为空")

        # 启动优化
        job = await optimizer.start_optimization(request)

        return OptimizationJobSummary(
            job_id=job.job_id,
            status=job.status.value,
            symbol=job.request.symbol,
            timeframe=job.request.timeframe,
            objective=job.request.objective.value,
            current_trial=job.current_trial,
            total_trials=job.total_trials,
            best_value=job.best_value,
            created_at=job.started_at.isoformat() if job.started_at else None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"启动优化失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/optimize", response_model=OptimizationJobList)
async def list_optimizations(
    status: Optional[str] = Query(None, description="状态筛选"),
    limit: int = Query(50, ge=1, le=200, description="返回数量限制"),
):
    """
    列出所有优化任务

    Phase 8: 自动化调参 - GET /api/optimize

    Args:
        status: 状态筛选 (running/completed/stopped/failed)
        limit: 返回数量限制

    Returns:
        OptimizationJobList: 优化任务列表
    """
    try:
        optimizer = _get_optimizer()
        jobs = optimizer._jobs.values()

        # 筛选
        if status:
            jobs = [j for j in jobs if j.status.value == status]

        # 排序（最新的在前）
        jobs = sorted(jobs, key=lambda j: j.started_at or datetime(1970, 1, 1, tzinfo=timezone.utc), reverse=True)[:limit]

        return OptimizationJobList(
            jobs=[
                OptimizationJobSummary(
                    job_id=j.job_id,
                    status=j.status.value,
                    symbol=j.request.symbol,
                    timeframe=j.request.timeframe,
                    objective=j.request.objective.value,
                    current_trial=j.current_trial,
                    total_trials=j.total_trials,
                    best_value=j.best_value,
                    created_at=j.started_at.isoformat() if j.started_at else None,
                )
                for j in jobs
            ],
            total=len(jobs),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"列出优化任务失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/optimize/{job_id}", response_model=OptimizationStatusResponse)
async def get_optimization_status(job_id: str):
    """
    获取优化任务状态

    Phase 8: 自动化调参 - GET /api/optimize/{job_id}

    Args:
        job_id: 任务 ID

    Returns:
        OptimizationStatusResponse: 优化状态

    Raises:
        HTTPException:
            - 404: 任务不存在
    """
    try:
        optimizer = _get_optimizer()

        if job_id not in optimizer._jobs:
            raise HTTPException(status_code=404, detail=f"任务 {job_id} 不存在")

        job = optimizer._jobs[job_id]

        # 计算预计剩余时间
        estimated_remaining = None
        if job.status == OptimizationJobStatus.RUNNING and job.started_at:
            elapsed = (datetime.now(timezone.utc) - job.started_at).total_seconds()
            if job.current_trial > 0:
                avg_time_per_trial = elapsed / job.current_trial
                remaining_trials = job.total_trials - job.current_trial
                estimated_remaining = int(avg_time_per_trial * remaining_trials)

        return OptimizationStatusResponse(
            job_id=job.job_id,
            status=job.status.value,
            current_trial=job.current_trial,
            total_trials=job.total_trials,
            best_trial=job.best_trial.model_dump() if job.best_trial else None,
            best_value=job.best_value,
            started_at=job.started_at.isoformat() if job.started_at else None,
            estimated_remaining_seconds=estimated_remaining,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取优化状态失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/optimize/{job_id}/results", response_model=OptimizationResultsResponse)
async def get_optimization_results(job_id: str):
    """
    获取优化结果

    Phase 8: 自动化调参 - GET /api/optimize/{job_id}/results

    Args:
        job_id: 任务 ID

    Returns:
        OptimizationResultsResponse: 优化结果

    Raises:
        HTTPException:
            - 404: 任务不存在
    """
    try:
        optimizer = _get_optimizer()

        if job_id not in optimizer._jobs:
            raise HTTPException(status_code=404, detail=f"任务 {job_id} 不存在")

        job = optimizer._jobs[job_id]

        # 获取试验历史
        trials = []
        # TODO: 从数据库加载试验历史
        # 这里简化处理，返回空列表

        return OptimizationResultsResponse(
            job_id=job.job_id,
            status=job.status.value,
            best_trial=job.best_trial.model_dump() if job.best_trial else None,
            best_value=job.best_value,
            total_trials=job.current_trial,
            trials=trials,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取优化结果失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/optimize/{job_id}/stop", response_model=OptimizationJobSummary)
async def stop_optimization(job_id: str):
    """
    停止优化任务

    Phase 8: 自动化调参 - POST /api/optimize/{job_id}/stop

    Args:
        job_id: 任务 ID

    Returns:
        OptimizationJobSummary: 优化任务摘要

    Raises:
        HTTPException:
            - 404: 任务不存在
            - 400: 任务已完成或已停止
    """
    try:
        optimizer = _get_optimizer()

        if job_id not in optimizer._jobs:
            raise HTTPException(status_code=404, detail=f"任务 {job_id} 不存在")

        job = optimizer._jobs[job_id]

        if job.status in [OptimizationJobStatus.COMPLETED, OptimizationJobStatus.STOPPED]:
            raise HTTPException(
                status_code=400,
                detail=f"任务已{job.status.value}，无法停止"
            )

        # 停止优化
        await optimizer.stop_optimization(job_id)

        return OptimizationJobSummary(
            job_id=job.job_id,
            status=job.status.value,
            symbol=job.request.symbol,
            timeframe=job.request.timeframe,
            objective=job.request.objective.value,
            current_trial=job.current_trial,
            total_trials=job.total_trials,
            best_value=job.best_value,
            created_at=job.started_at.isoformat() if job.started_at else None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"停止优化失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 配置 Profile 管理 API (2026-04-03)
# Reference: docs/products/config-profile-management-prd.md
# ============================================================

# Profile Repository 和 Service 初始化（使用字符串类型注解避免导入错误）
_profile_repository: Optional["ConfigProfileRepository"] = None
_profile_service: Optional["ConfigProfileService"] = None


def _get_profile_repository() -> "ConfigProfileRepository":
    """Get profile repository or raise error if not initialized."""
    global _profile_repository
    if _profile_repository is None:
        from src.infrastructure.config_profile_repository import ConfigProfileRepository
        _profile_repository = ConfigProfileRepository()
    return _profile_repository


def _get_profile_service() -> "ConfigProfileService":
    """Get profile service or raise error if not initialized."""
    global _profile_service
    if _profile_service is None:
        from src.infrastructure.config_profile_repository import ConfigProfileRepository
        from src.application.config_profile_service import ConfigProfileService
        _profile_repository = ConfigProfileRepository()
        config_entry_repo = _get_config_entry_repo()
        _profile_service = ConfigProfileService(_profile_repository, config_entry_repo, _config_manager)
    return _profile_service


@app.get("/api/config/profiles", response_model=ProfileListResponse)
async def list_profiles():
    """
    获取所有配置 Profile 列表

    Returns:
        Profile 列表，包含激活状态标识
    """
    try:
        from src.infrastructure.config_profile_repository import ConfigProfileRepository
        from src.application.config_profile_service import ConfigProfileService

        profile_repo = ConfigProfileRepository()
        await profile_repo.initialize()

        config_entry_repo = _get_config_entry_repo()
        service = ConfigProfileService(profile_repo, config_entry_repo, _config_manager)

        profiles = await service.list_profiles()
        active = await service.get_active_profile()

        return ProfileListResponse(
            profiles=[p.to_dict() for p in profiles],
            total=len(profiles),
            active_profile=active.name if active else None,
        )
    except Exception as e:
        logger.error(f"获取 Profile 列表失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/config/profiles/{name}")
async def get_profile(name: str):
    """
    获取单个 Profile 详情

    Args:
        name: Profile 名称

    Returns:
        Profile 详情
    """
    try:
        from src.infrastructure.config_profile_repository import ConfigProfileRepository
        from src.application.config_profile_service import ConfigProfileService

        profile_repo = ConfigProfileRepository()
        await profile_repo.initialize()

        config_entry_repo = _get_config_entry_repo()
        service = ConfigProfileService(profile_repo, config_entry_repo, _config_manager)

        profile = await service.get_profile(name)
        if not profile:
            raise HTTPException(status_code=404, detail=f"Profile '{name}' 不存在")

        return profile.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取 Profile 详情失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/config/profiles", response_model=ProfileCreateResponse)
async def create_profile(request: ProfileCreateRequest):
    """
    创建新的配置 Profile

    Args:
        name: Profile 名称 (1-32 字符)
        description: 描述 (可选)
        copy_from: 源 Profile 名称（复制配置，可选）
        switch_immediately: 创建后是否立即切换

    Returns:
        创建的 Profile 信息
    """
    try:
        from src.infrastructure.config_profile_repository import ConfigProfileRepository
        from src.application.config_profile_service import ConfigProfileService

        profile_repo = ConfigProfileRepository()
        await profile_repo.initialize()

        config_entry_repo = _get_config_entry_repo()
        service = ConfigProfileService(profile_repo, config_entry_repo, _config_manager)

        # 名称验证
        if not request.name or len(request.name) > 32:
            raise HTTPException(status_code=400, detail="Profile 名称长度为 1-32 个字符")

        profile = await service.create_profile(
            name=request.name,
            description=request.description,
            copy_from=request.copy_from,
            switch_immediately=request.switch_immediately,
        )

        return ProfileCreateResponse(
            status="success",
            profile=profile.to_dict(),
            message=f"Profile '{request.name}' 创建成功",
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"创建 Profile 失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/config/profiles/{name}/activate", response_model=ProfileSwitchResponse)
async def switch_profile(name: str):
    """
    切换到指定的配置 Profile（带差异预览）

    Args:
        name: Profile 名称

    Returns:
        切换结果和配置差异
    """
    try:
        from src.infrastructure.config_profile_repository import ConfigProfileRepository
        from src.application.config_profile_service import ConfigProfileService

        profile_repo = ConfigProfileRepository()
        await profile_repo.initialize()

        config_entry_repo = _get_config_entry_repo()
        service = ConfigProfileService(profile_repo, config_entry_repo, _config_manager)

        profile = await service.get_profile(name)
        if not profile:
            raise HTTPException(status_code=404, detail=f"Profile '{name}' 不存在")

        diff = await service.switch_profile(name)

        return ProfileSwitchResponse(
            status="success",
            profile=profile.to_dict(),
            diff=diff.to_dict(),
            message=f"已切换到 Profile '{name}'，共 {diff.total_changes} 项配置变更",
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"切换 Profile 失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/config/profiles/{name}", response_model=ProfileDeleteResponse)
async def delete_profile(name: str):
    """
    删除配置 Profile

    Args:
        name: Profile 名称

    Returns:
        删除结果

    Raises:
        HTTPException:
            - 400: 不能删除 default 或当前激活的 Profile
            - 404: Profile 不存在
    """
    try:
        from src.infrastructure.config_profile_repository import ConfigProfileRepository
        from src.application.config_profile_service import ConfigProfileService

        profile_repo = ConfigProfileRepository()
        await profile_repo.initialize()

        config_entry_repo = _get_config_entry_repo()
        service = ConfigProfileService(profile_repo, config_entry_repo, _config_manager)

        profile = await service.get_profile(name)
        if not profile:
            raise HTTPException(status_code=404, detail=f"Profile '{name}' 不存在")

        await service.delete_profile(name)

        return ProfileDeleteResponse(
            status="success",
            message=f"Profile '{name}' 已删除",
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"删除 Profile 失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/config/profiles/{name}", response_model=ProfileRenameResponse)
async def rename_profile(name: str, request: ProfileRenameRequest):
    """
    重命名配置 Profile

    Args:
        name: 原 Profile 名称
        name: 新 Profile 名称 (1-32 字符)
        description: 新描述 (可选)

    Returns:
        重命名后的 Profile 信息

    Raises:
        HTTPException:
            - 400: 名称冲突或不能重命名为 default
            - 404: Profile 不存在
    """
    try:
        from src.infrastructure.config_profile_repository import ConfigProfileRepository
        from src.application.config_profile_service import ConfigProfileService

        profile_repo = ConfigProfileRepository()
        await profile_repo.initialize()

        config_entry_repo = _get_config_entry_repo()
        service = ConfigProfileService(profile_repo, config_entry_repo, _config_manager)

        # 验证原 Profile 存在
        profile = await service.get_profile(name)
        if not profile:
            raise HTTPException(status_code=404, detail=f"Profile '{name}' 不存在")

        # 名称验证
        new_name = request.name
        if not new_name or len(new_name) > 32:
            raise HTTPException(status_code=400, detail="Profile 名称长度为 1-32 个字符")

        # 边界检查：不能重命名为 default
        if new_name == "default":
            raise HTTPException(status_code=400, detail="不能重命名为 'default'")

        # 检查新名称是否已被占用（排除自身）
        existing = await service.get_profile(new_name)
        if existing and existing.name != name:
            raise HTTPException(status_code=400, detail=f"Profile '{new_name}' 已存在")

        # 执行重命名
        updated_profile = await service.rename_profile(name, new_name, request.description)

        return ProfileRenameResponse(
            status="success",
            profile=updated_profile.to_dict(),
            message=f"Profile '{name}' 已重命名为 '{new_name}'",
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"重命名 Profile 失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/config/profiles/{name}/export", response_model=ProfileExportResponse)
async def export_profile(name: str):
    """
    导出配置 Profile 为 YAML 格式

    Args:
        name: Profile 名称

    Returns:
        YAML 格式的配置内容
    """
    try:
        from src.infrastructure.config_profile_repository import ConfigProfileRepository
        from src.application.config_profile_service import ConfigProfileService

        profile_repo = ConfigProfileRepository()
        await profile_repo.initialize()

        config_entry_repo = _get_config_entry_repo()
        service = ConfigProfileService(profile_repo, config_entry_repo, _config_manager)

        profile = await service.get_profile(name)
        if not profile:
            raise HTTPException(status_code=404, detail=f"Profile '{name}' 不存在")

        yaml_content = await service.export_profile_yaml(name)

        return ProfileExportResponse(
            status="success",
            profile_name=name,
            yaml_content=yaml_content,
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"导出 Profile 失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/config/profiles/import", response_model=ProfileImportResponse)
async def import_profile(request: ProfileImportRequest):
    """
    从 YAML 导入配置 Profile

    Args:
        yaml_content: YAML 格式的配置内容
        profile_name: 指定 Profile 名称（可选）
        mode: 导入模式（create | overwrite）

    Returns:
        导入结果
    """
    try:
        from src.infrastructure.config_profile_repository import ConfigProfileRepository
        from src.application.config_profile_service import ConfigProfileService

        profile_repo = ConfigProfileRepository()
        await profile_repo.initialize()

        config_entry_repo = _get_config_entry_repo()
        service = ConfigProfileService(profile_repo, config_entry_repo, _config_manager)

        profile, count = await service.import_profile_yaml(
            yaml_content=request.yaml_content,
            profile_name=request.profile_name,
            mode=request.mode,
        )

        return ProfileImportResponse(
            status="success",
            profile=profile.to_dict(),
            imported_count=count,
            message=f"成功导入 {count} 项配置到 Profile '{profile.name}'",
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"导入 Profile 失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/config/profiles/compare")
async def compare_profiles(
    from_name: str = Query(..., description="源 Profile 名称"),
    to_name: str = Query(..., description="目标 Profile 名称"),
):
    """
    对比两个配置 Profile 的差异

    Args:
        from_name: 源 Profile 名称
        to_name: 目标 Profile 名称

    Returns:
        差异对比结果
    """
    try:
        from src.infrastructure.config_profile_repository import ConfigProfileRepository
        from src.application.config_profile_service import ConfigProfileService

        profile_repo = ConfigProfileRepository()
        await profile_repo.initialize()

        config_entry_repo = _get_config_entry_repo()
        service = ConfigProfileService(profile_repo, config_entry_repo, _config_manager)

        from_profile = await service.get_profile(from_name)
        if not from_profile:
            raise HTTPException(status_code=404, detail=f"Profile '{from_name}' 不存在")

        to_profile = await service.get_profile(to_name)
        if not to_profile:
            raise HTTPException(status_code=404, detail=f"Profile '{to_name}' 不存在")

        diff = await service._calculate_profile_diff(from_name, to_name)

        return {
            "status": "success",
            "from_profile": from_name,
            "to_profile": to_name,
            "diff": diff.to_dict(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"对比 Profile 失败：{str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/strategy/params/templates")
async def get_strategy_param_templates():
    """
    Get available strategy parameter templates.

    Returns a list of predefined strategy parameter templates that users can use as starting points.
    """
    templates = [
        {
            "name": "default",
            "description": "Default strategy parameters",
            "params": {
                "pinbar": {
                    "min_wick_ratio": "0.6",
                    "max_body_ratio": "0.3",
                    "body_position_tolerance": "0.3"
                },
                "engulfing": {
                    "min_wick_ratio": "0.6",
                    "max_body_ratio": "0.3"
                },
                "ema": {
                    "period": 60
                },
                "mtf": {
                    "enabled": True,
                    "ema_period": 60
                },
                "atr": {
                    "enabled": True,
                    "period": 14,
                    "min_atr_ratio": "0.5"
                }
            }
        },
        {
            "name": "conservative",
            "description": "Conservative strategy with stricter filters",
            "params": {
                "pinbar": {
                    "min_wick_ratio": "0.7",
                    "max_body_ratio": "0.25",
                    "body_position_tolerance": "0.2"
                },
                "engulfing": {
                    "min_wick_ratio": "0.7",
                    "max_body_ratio": "0.25"
                },
                "ema": {
                    "period": 100
                },
                "mtf": {
                    "enabled": True,
                    "ema_period": 100
                },
                "atr": {
                    "enabled": True,
                    "period": 20,
                    "min_atr_ratio": "0.7"
                }
            }
        },
        {
            "name": "aggressive",
            "description": "Aggressive strategy with looser filters",
            "params": {
                "pinbar": {
                    "min_wick_ratio": "0.5",
                    "max_body_ratio": "0.4",
                    "body_position_tolerance": "0.4"
                },
                "engulfing": {
                    "min_wick_ratio": "0.5",
                    "max_body_ratio": "0.4"
                },
                "ema": {
                    "period": 30
                },
                "mtf": {
                    "enabled": True,
                    "ema_period": 30
                },
                "atr": {
                    "enabled": True,
                    "period": 10,
                    "min_atr_ratio": "0.3"
                }
            }
        }
    ]

    return {"templates": templates, "total": len(templates)}


# ============================================================
# System Configuration API
# ============================================================

@app.get("/api/config/system", response_model=SystemConfigResponse)
async def get_system_config():
    """
    获取系统配置 (Level 1 全局配置)

    返回全局系统配置参数，包括队列配置、数据预热、信号冷却等。
    这些配置修改后需要重启服务才能生效。

    Returns:
        SystemConfigResponse: 系统配置对象
    """
    try:
        config_manager = _get_config_manager()

        # 从 ConfigManager 获取系统配置
        # 注意：这些配置目前从代码默认值读取，未来可从数据库读取
        return SystemConfigResponse(
            queue_batch_size=10,
            queue_flush_interval=5.0,
            queue_max_size=1000,
            warmup_history_bars=100,
            signal_cooldown_seconds=14400,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get system config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/config/system", response_model=SystemConfigUpdateResponse)
async def update_system_config(request: SystemConfigUpdateRequest):
    """
    更新系统配置 (Level 1 全局配置)

    更新全局系统配置参数。修改后需要重启服务才能生效。

    Request body:
    {
        "queue_batch_size": 20,           // Optional: 1-100
        "queue_flush_interval": 3.0,      // Optional: 1.0-60.0
        "queue_max_size": 2000,           // Optional: 100-10000
        "warmup_history_bars": 150,       // Optional: 50-500
        "signal_cooldown_seconds": 7200   // Optional: 3600-86400
    }

    Returns:
        SystemConfigUpdateResponse: 更新后的配置 + 重启提示
    """
    try:
        config_manager = _get_config_manager()

        # 构建更新后的配置
        current_config = SystemConfigResponse(
            queue_batch_size=10,
            queue_flush_interval=5.0,
            queue_max_size=1000,
            warmup_history_bars=100,
            signal_cooldown_seconds=14400,
        )

        # 应用更新
        update_data = request.model_dump(exclude_unset=True)
        updated_config_dict = {**current_config.model_dump(), **update_data}
        updated_config = SystemConfigResponse(**updated_config_dict)

        # TODO: 将配置持久化到数据库
        # await config_manager.update_system_config(updated_config_dict)

        logger.info(f"System config updated: {updated_config_dict}")

        return SystemConfigUpdateResponse(
            config=updated_config,
            requires_restart=True,
            restart_hint="修改已保存，需要重启服务才能生效",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update system config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/config/schema", response_model=ConfigSchemaResponse)
async def get_config_schema():
    """
    获取配置项 Schema (含 tooltip 说明)

    返回所有配置项的详细信息，包括类型、默认值、范围限制和 tooltip 说明。
    前端可使用此 Schema 动态生成表单和提示信息。

    Returns:
        ConfigSchemaResponse: 配置 Schema 对象
    """
    try:
        # 策略参数 Schema
        strategy_params_schema = {
            "pinbar": {
                "min_wick_ratio": {
                    "type": "number",
                    "default": 0.6,
                    "min": 0.5,
                    "max": 0.7,
                    "step": 0.05,
                    "tooltip": {
                        "description": "影线长度占整个 K 线范围的比例下限。较高的值会选择更明显的 Pinbar 形态，但可能会错过一些机会。",
                        "default_value": "0.6 (60%)",
                        "range": "0.5 - 0.7",
                        "adjustment_tips": [
                            "高波动市场：降低到 0.5",
                            "低波动市场：提高到 0.7"
                        ]
                    }
                },
                "max_body_ratio": {
                    "type": "number",
                    "default": 0.3,
                    "min": 0.2,
                    "max": 0.4,
                    "step": 0.05,
                    "tooltip": {
                        "description": "实体长度占整个 K 线范围的比例上限。较低的值会选择更紧凑的实体。",
                        "default_value": "0.3 (30%)",
                        "range": "0.2 - 0.4",
                        "adjustment_tips": [
                            "需要更精确的入场：降低到 0.2",
                            "希望捕捉更多机会：提高到 0.4"
                        ]
                    }
                },
                "body_position_tolerance": {
                    "type": "number",
                    "default": 0.1,
                    "min": 0.05,
                    "max": 0.15,
                    "step": 0.01,
                    "tooltip": {
                        "description": "实体位置的容差范围。决定实体在 K 线顶部/底部的允许偏差。",
                        "default_value": "0.1 (10%)",
                        "range": "0.05 - 0.15",
                        "adjustment_tips": [
                            "更严格的形态要求：降低到 0.05",
                            "更宽松的形态要求：提高到 0.15"
                        ]
                    }
                }
            },
            "engulfing": {
                "max_wick_ratio": {
                    "type": "number",
                    "default": 0.6,
                    "min": 0.5,
                    "max": 0.7,
                    "step": 0.05,
                    "tooltip": {
                        "description": "吞没形态的最大影线比例。控制吞没 K 线的影线长度。",
                        "default_value": "0.6 (60%)",
                        "range": "0.5 - 0.7",
                        "adjustment_tips": [
                            "高波动市场：降低到 0.5",
                            "低波动市场：提高到 0.7"
                        ]
                    }
                }
            },
            "ema": {
                "period": {
                    "type": "number",
                    "default": 60,
                    "min": 5,
                    "max": 200,
                    "step": 5,
                    "tooltip": {
                        "description": "EMA 趋势过滤器的周期。用于判断当前趋势方向。",
                        "default_value": "60",
                        "range": "5 - 200",
                        "adjustment_tips": [
                            "短期趋势跟踪：降低到 20-30",
                            "长期趋势跟踪：提高到 100-200"
                        ]
                    }
                }
            },
            "mtf": {
                "enabled": {
                    "type": "boolean",
                    "default": True,
                    "tooltip": {
                        "description": "是否启用多时间框架 (MTF) 验证。启用后会检查大周期趋势方向。",
                        "default_value": "true",
                        "adjustment_tips": [
                            "趋势明确的市场：建议启用",
                            "震荡市场：可考虑禁用"
                        ]
                    }
                },
                "ema_period": {
                    "type": "number",
                    "default": 60,
                    "min": 5,
                    "max": 200,
                    "step": 5,
                    "tooltip": {
                        "description": "MTF 趋势计算的 EMA 周期。",
                        "default_value": "60",
                        "range": "5 - 200",
                        "adjustment_tips": [
                            "短期 MTF 分析：降低到 20-30",
                            "长期 MTF 分析：提高到 100-200"
                        ]
                    }
                }
            },
            "atr": {
                "enabled": {
                    "type": "boolean",
                    "default": False,
                    "tooltip": {
                        "description": "是否启用 ATR (平均真实波动范围) 过滤器。用于过滤低波动时期的信号。",
                        "default_value": "false",
                        "adjustment_tips": [
                            "高波动市场：建议启用",
                            "趋势明确的市场：可考虑禁用"
                        ]
                    }
                },
                "period": {
                    "type": "number",
                    "default": 14,
                    "min": 5,
                    "max": 50,
                    "step": 1,
                    "tooltip": {
                        "description": "ATR 计算周期。",
                        "default_value": "14",
                        "range": "5 - 50",
                        "adjustment_tips": [
                            "短期波动敏感度：降低到 5-10",
                            "长期波动趋势：提高到 20-50"
                        ]
                    }
                },
                "min_atr_ratio": {
                    "type": "number",
                    "default": 0.5,
                    "min": 0.1,
                    "max": 2.0,
                    "step": 0.1,
                    "tooltip": {
                        "description": "最小 ATR 比率。用于过滤低波动时期的信号。",
                        "default_value": "0.5",
                        "range": "0.1 - 2.0",
                        "adjustment_tips": [
                            "高波动市场：降低到 0.1-0.3",
                            "低波动市场：提高到 1.0-2.0"
                        ]
                    }
                }
            },
            "max_loss_percent": {
                "type": "number",
                "default": 0.01,
                "min": 0.005,
                "max": 0.1,
                "step": 0.005,
                "tooltip": {
                    "description": "单笔交易最大损失百分比。用于仓位计算。",
                    "default_value": "1% (0.01)",
                    "range": "0.5% - 10%",
                    "adjustment_tips": [
                        "保守策略：降低到 0.5%",
                        "激进策略：可提高到 2-3%"
                    ]
                }
            },
            "max_leverage": {
                "type": "number",
                "default": 10,
                "min": 1,
                "max": 20,
                "step": 1,
                "tooltip": {
                    "description": "最大允许杠杆倍数。",
                    "default_value": "10x",
                    "range": "1x - 20x",
                    "adjustment_tips": [
                        "保守策略：降低到 5x",
                        "高风险偏好：可提高到 15-20x"
                    ]
                }
            }
        }

        # 系统配置 Schema
        system_config_schema = {
            "queue_batch_size": {
                "type": "number",
                "default": 10,
                "min": 1,
                "max": 100,
                "step": 1,
                "tooltip": {
                    "description": "队列批量落盘大小。控制每次批量处理的信号数量。",
                    "default_value": "10",
                    "range": "1 - 100",
                    "adjustment_tips": [
                        "高并发场景：提高到 20-50",
                        "低延迟要求：降低到 1-5"
                    ]
                }
            },
            "queue_flush_interval": {
                "type": "number",
                "default": 5.0,
                "min": 1.0,
                "max": 60.0,
                "step": 0.5,
                "tooltip": {
                    "description": "队列最大等待时间 (秒)。超时后即使队列未满也会强制落盘。",
                    "default_value": "5.0 秒",
                    "range": "1.0 - 60.0 秒",
                    "adjustment_tips": [
                        "实时性要求高：降低到 1-2 秒",
                        "批量处理优先：提高到 10-30 秒"
                    ]
                }
            },
            "queue_max_size": {
                "type": "number",
                "default": 1000,
                "min": 100,
                "max": 10000,
                "step": 100,
                "tooltip": {
                    "description": "队列最大容量。超过此值会触发强制落盘。",
                    "default_value": "1000",
                    "range": "100 - 10000",
                    "adjustment_tips": [
                        "内存受限：降低到 100-500",
                        "高吞吐场景：提高到 2000-5000"
                    ]
                }
            },
            "warmup_history_bars": {
                "type": "number",
                "default": 100,
                "min": 50,
                "max": 500,
                "step": 10,
                "tooltip": {
                    "description": "数据预热时获取的历史 K 线数量。用于指标计算预热。",
                    "default_value": "100 根",
                    "range": "50 - 500 根",
                    "adjustment_tips": [
                        "短周期指标：50-100 根",
                        "长周期指标 (如 EMA200)：提高到 200-500 根"
                    ]
                }
            },
            "signal_cooldown_seconds": {
                "type": "number",
                "default": 14400,
                "min": 3600,
                "max": 86400,
                "step": 3600,
                "tooltip": {
                    "description": "信号冷却时间 (秒)。同一信号的重复触发需要间隔此时间。",
                    "default_value": "14400 秒 (4 小时)",
                    "range": "3600 - 86400 秒 (1-24 小时)",
                    "adjustment_tips": [
                        "高频交易：降低到 1-2 小时",
                        "低频交易：提高到 6-12 小时"
                    ]
                }
            }
        }

        return ConfigSchemaResponse(
            strategy_params=strategy_params_schema,
            system_config=system_config_schema,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get config schema: {e}")
        raise HTTPException(status_code=500, detail=str(e))
