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
    POST /api/backtest - Run backtest
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
from typing import Optional, Callable, Any, List, Dict

from fastapi import FastAPI, Query, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware

from src.infrastructure.signal_repository import SignalRepository
from src.domain.models import (
    SignalQuery, SignalDeleteRequest, SignalDeleteResponse,
    AttemptQuery, AttemptDeleteRequest, AttemptDeleteResponse,
    BacktestRequest, BacktestReport, SignalStatus, SignalTrack,
)


# ============================================================
# Global Dependencies
# ============================================================
_repository: Optional[SignalRepository] = None
_account_getter: Optional[Callable[[], Any]] = None
_config_manager: Optional[Any] = None  # ConfigManager instance
_exchange_gateway: Optional[Any] = None  # ExchangeGateway instance
_signal_tracker: Optional[Any] = None  # SignalStatusTracker instance


def set_dependencies(
    repository: SignalRepository,
    account_getter: Callable[[], Any],
    config_manager: Optional[Any] = None,
    exchange_gateway: Optional[Any] = None,
    signal_tracker: Optional[Any] = None,
) -> None:
    """
    Inject dependencies for API endpoints.

    Args:
        repository: SignalRepository instance
        account_getter: Function that returns AccountSnapshot or None
        config_manager: Optional ConfigManager instance
        exchange_gateway: Optional ExchangeGateway instance
        signal_tracker: Optional SignalStatusTracker instance
    """
    global _repository, _account_getter, _config_manager, _exchange_gateway, _signal_tracker
    _repository = repository
    _account_getter = account_getter
    _config_manager = config_manager
    _exchange_gateway = exchange_gateway
    _signal_tracker = signal_tracker


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


def _get_signal_tracker() -> Any:
    """Get signal tracker or raise error if not initialized."""
    if _signal_tracker is None:
        raise HTTPException(status_code=503, detail="Signal tracker not initialized")
    return _signal_tracker


# ============================================================
# Lifespan Manager
# ============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifespan events.
    Initialize and close repository on startup/shutdown.
    """
    # Startup
    yield
    # Shutdown
    if _repository is not None:
        await _repository.close()


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
    direction: Optional[str] = Query(default=None),
    strategy_name: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    start_time: Optional[str] = Query(default=None),
    end_time: Optional[str] = Query(default=None),
    sort_by: str = Query(default="created_at", pattern="^(created_at|pattern_score)$"),
    order: str = Query(default="desc", pattern="^(asc|desc|ASC|DESC)$"),
):
    """
    Query trading signals with pagination and optional filtering.

    Args:
        limit: Maximum number of results (1-200)
        offset: Number of results to skip
        symbol: Optional symbol filter (e.g., "BTC/USDT:USDT")
        direction: Optional direction filter ("long" or "short")
        strategy_name: Optional strategy name filter ("pinbar", "engulfing")
        status: Optional status filter ("PENDING", "WON", "LOST")
        start_time: Optional start time filter (ISO 8601)
        end_time: Optional end time filter (ISO 8601)
        sort_by: Sort field ("created_at" or "pattern_score"), default "created_at"
        order: Sort order ("asc" or "desc"), default "desc"
    """
    try:
        repo = _get_repository()
        result = await repo.get_signals(
            limit=limit,
            offset=offset,
            symbol=symbol,
            direction=direction,
            strategy_name=strategy_name,
            status=status,
            start_time=start_time,
            end_time=end_time,
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
            return {"error": "Legacy signal data without kline_timestamp"}

        # Parse timeframe to milliseconds
        timeframe_map = {
            "1m": 1 * 60 * 1000,
            "5m": 5 * 60 * 1000,
            "15m": 15 * 60 * 1000,
            "30m": 30 * 60 * 1000,
            "1h": 60 * 60 * 1000,
            "4h": 4 * 60 * 60 * 1000,
            "1d": 24 * 60 * 60 * 1000,
            "1w": 7 * 24 * 60 * 60 * 1000,
        }
        timeframe_ms = timeframe_map.get(timeframe, 60 * 60 * 1000)  # Default 1h

        # Calculate since timestamp (go back 25 candles to ensure target is in middle-rear)
        since = kline_timestamp - (25 * timeframe_ms)

        # Fetch K-line data from CCXT
        import ccxt.async_support as ccxt
        exchange = ccxt.binanceusdm({'options': {'defaultType': 'swap'}})
        try:
            ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=50)
        finally:
            await exchange.close()

        return {
            "signal": signal,
            "klines": ohlcv,
        }
    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e)}


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

    Sensitive fields: api_key, api_secret, webhook_url, secret, password, token

    Args:
        data: Dictionary to mask

    Returns:
        Dictionary with sensitive values masked
    """
    sensitive_keys = {"api_key", "api_secret", "webhook_url", "secret", "password", "token"}
    result = {}

    for key, value in data.items():
        if key.lower() in sensitive_keys:
            result[key] = _mask_config_value(value, is_sensitive=True)
        elif isinstance(value, dict):
            result[key] = _deep_mask_config(value)
        elif isinstance(value, list):
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
        user_config = config_manager.user_config

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


@app.put("/api/config")
async def update_config(
    config_update: Dict[str, Any] = Body(..., description="Partial user config update"),
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

    Returns:
        Updated config (masked) or 422 on validation error
    """
    try:
        config_manager = _get_config_manager()

        # Call hot-reload method (validates + atomic swap + persist)
        new_config = await config_manager.update_user_config(config_update)

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
# Backtest Endpoint
# ============================================================
@app.post("/api/backtest")
async def run_backtest(
    request: BacktestRequest,
):
    """
    Run strategy backtest on historical data.

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
        "mtf_validation_enabled": true
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

        gateway = _get_exchange_gateway()
        backtester = Backtester(gateway)

        # Get current account snapshot for position sizing
        account_snapshot = _account_getter() if _account_getter else None

        # Run backtest
        report = await backtester.run_backtest(request, account_snapshot)

        return {
            "status": "success",
            "report": report.model_dump(),
        }
    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e)}


# ============================================================
# Custom Strategies Management Endpoints
# ============================================================

from pydantic import BaseModel, Field
from typing import Optional


class StrategyCreateRequest(BaseModel):
    """Request model for creating a custom strategy template."""
    name: str = Field(..., description="Strategy name")
    description: Optional[str] = Field(default=None, description="Strategy description")
    strategy: Dict[str, Any] = Field(..., description="StrategyDefinition object")


class StrategyUpdateRequest(BaseModel):
    """Request model for updating a custom strategy template."""
    name: Optional[str] = Field(default=None, description="New strategy name")
    description: Optional[str] = Field(default=None, description="New description")
    strategy: Optional[Dict[str, Any]] = Field(default=None, description="New StrategyDefinition object")


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


@app.get("/api/strategies")
async def get_custom_strategies():
    """
    Get all custom strategy templates (list view).

    Returns basic information (id, name, description) for each strategy.
    Use GET /api/strategies/{id} to fetch full strategy details.
    """
    try:
        repo = _get_repository()
        strategies = await repo.get_all_custom_strategies()
        return {"strategies": strategies}
    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/strategies/{strategy_id}")
async def get_custom_strategy(strategy_id: int):
    """
    Get a single custom strategy by ID with full details.

    Args:
        strategy_id: Strategy record ID

    Returns:
        Full strategy definition including strategy_json for frontend hydration.
    """
    try:
        repo = _get_repository()
        strategy = await repo.get_custom_strategy_by_id(strategy_id)

        if strategy is None:
            raise HTTPException(status_code=404, detail="Strategy not found")

        # Parse strategy_json back to dict for frontend
        import json
        strategy_dict = dict(strategy)
        strategy_dict["strategy"] = json.loads(strategy["strategy_json"])
        del strategy_dict["strategy_json"]

        return strategy_dict
    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/strategies")
async def create_custom_strategy(request: StrategyCreateRequest):
    """
    Create a new custom strategy template.

    Request body:
    {
        "name": "My Pinbar Strategy",
        "description": "Optional description",
        "strategy": { ... StrategyDefinition object ... }
    }

    The strategy object will be validated and serialized to JSON for storage.
    """
    try:
        repo = _get_repository()

        # Validate strategy structure
        from src.domain.models import StrategyDefinition
        try:
            strategy_def = StrategyDefinition(**request.strategy)
        except Exception as validation_error:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid strategy definition: {str(validation_error)}"
            )

        # Serialize strategy to JSON
        import json
        strategy_json = strategy_def.model_dump_json()

        # Create in database
        strategy_id = await repo.create_custom_strategy(
            name=request.name,
            description=request.description,
            strategy_json=strategy_json,
        )

        return {
            "id": strategy_id,
            "name": request.name,
            "description": request.description,
        }
    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e)}


@app.put("/api/strategies/{strategy_id}")
async def update_custom_strategy(strategy_id: int, request: StrategyUpdateRequest):
    """
    Update an existing custom strategy template.

    Request body (all fields optional):
    {
        "name": "New name",
        "description": "New description",
        "strategy": { ... new StrategyDefinition object ... }
    }

    Only provided fields will be updated.
    """
    try:
        repo = _get_repository()

        # Check if strategy exists
        existing = await repo.get_custom_strategy_by_id(strategy_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Strategy not found")

        # Validate and serialize new strategy if provided
        strategy_json = None
        if request.strategy is not None:
            from src.domain.models import StrategyDefinition
            try:
                strategy_def = StrategyDefinition(**request.strategy)
            except Exception as validation_error:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid strategy definition: {str(validation_error)}"
                )
            import json
            strategy_json = strategy_def.model_dump_json()

        # Update in database
        updated = await repo.update_custom_strategy(
            strategy_id=strategy_id,
            name=request.name,
            description=request.description,
            strategy_json=strategy_json,
        )

        if not updated:
            return {"error": "No fields to update"}

        return {"message": "Strategy updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e)}


@app.delete("/api/strategies/{strategy_id}")
async def delete_custom_strategy(strategy_id: int):
    """
    Delete a custom strategy template by ID.

    Args:
        strategy_id: Strategy record ID

    Returns:
        Success message or 404 if not found.
    """
    try:
        repo = _get_repository()

        deleted = await repo.delete_custom_strategy(strategy_id)

        if not deleted:
            raise HTTPException(status_code=404, detail="Strategy not found")

        return {"message": f"Strategy {strategy_id} deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e)}


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
    strategy_id: int = Field(..., description="Applied strategy template ID")
    strategy_name: str = Field(..., description="Applied strategy name")


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
async def apply_strategy(strategy_id: int, request: StrategyApplyRequest = None):
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

        # Get config manager
        config_manager = _get_config_manager()
        repo = _get_repository()

        # Step 1: Load strategy template from database
        strategy_record = await repo.get_custom_strategy_by_id(strategy_id)
        if strategy_record is None:
            raise HTTPException(status_code=404, detail="Strategy template not found")

        # Step 2: Parse and validate strategy definition
        import json
        from src.domain.models import StrategyDefinition

        try:
            strategy_def = StrategyDefinition(**json.loads(strategy_record["strategy_json"]))
        except Exception as validation_error:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid strategy definition: {str(validation_error)}"
            )

        # Step 3: Update strategy definition with apply options (use model_copy for immutability)
        update_dict = {}
        if request.apply_to is not None:
            update_dict["apply_to"] = request.apply_to
            update_dict["is_global"] = False

        if update_dict:
            strategy_def = strategy_def.model_copy(update=update_dict)

        # Step 4: Get current active strategies and add/replace this strategy
        current_config = config_manager.user_config
        active_strategies = list(current_config.active_strategies)

        # Check if strategy with same name already exists
        existing_idx = None
        for i, strat in enumerate(active_strategies):
            if strat.name == strategy_def.name:
                existing_idx = i
                break

        if existing_idx is not None:
            # Replace existing strategy
            active_strategies[existing_idx] = strategy_def
            logger.info(f"Replaced existing strategy '{strategy_def.name}' (id={strategy_id})")
        else:
            # Add new strategy
            active_strategies.append(strategy_def)
            logger.info(f"Added new strategy '{strategy_def.name}' (id={strategy_id})")

        # Step 5: Build config update payload
        config_update = {
            "active_strategies": [s.model_dump(mode='json') for s in active_strategies]
        }

        # Step 6: Call hot-reload method (validates + atomic swap + persist + notify observers)
        try:
            new_config = await config_manager.update_user_config(config_update)
        except ValidationError as e:
            logger.error(f"Config validation failed during apply: {e}")
            raise HTTPException(
                status_code=422,
                detail=f"Config validation failed: {str(e)}"
            )

        logger.info(f"Strategy template {strategy_id} ('{strategy_def.name}') applied successfully")

        return StrategyApplyResponse(
            status="success",
            message=f"Strategy '{strategy_def.name}' applied to live trading",
            strategy_id=strategy_id,
            strategy_name=strategy_def.name,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to apply strategy template {strategy_id}: {e}")
        return {"error": str(e)}


# ============================================================
# Config Snapshots Management Endpoints
# ============================================================

class ConfigSnapshotCreate(BaseModel):
    """Request model for creating a config snapshot."""
    version: str = Field(..., description="Version tag, e.g., 'v1.0.0'")
    config_json: str = Field(..., description="Serialized UserConfig JSON")
    description: str = Field(default="", description="Snapshot description")
    created_by: str = Field(default="user", description="Creator identifier")


class ConfigSnapshotResponse(BaseModel):
    """Response model for config snapshot."""
    id: int
    version: str
    config_json: str
    description: str
    created_at: str
    created_by: str
    is_active: bool


class ConfigSnapshotListResponse(BaseModel):
    """Response model for config snapshot list."""
    total: int
    data: List[ConfigSnapshotResponse]


@app.post("/api/config/snapshots", response_model=ConfigSnapshotResponse)
async def create_snapshot(request: ConfigSnapshotCreate):
    """
    Create a new config snapshot.

    Request body:
    {
        "version": "v1.0.0",
        "config_json": "{...}",
        "description": "Initial config",
        "created_by": "user"
    }

    Returns:
        Created snapshot with is_active=true
    """
    try:
        repo = _get_repository()
        snapshot_id = await repo.create_config_snapshot(
            version=request.version,
            config_json=request.config_json,
            description=request.description,
            created_by=request.created_by,
        )
        return ConfigSnapshotResponse(
            id=snapshot_id,
            version=request.version,
            config_json=request.config_json,
            description=request.description,
            created_at=datetime.now(timezone.utc).isoformat(),
            created_by=request.created_by,
            is_active=True,
        )
    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/config/snapshots", response_model=ConfigSnapshotListResponse)
async def list_snapshots(limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0)):
    """
    List all config snapshots with pagination.

    Args:
        limit: Maximum number of results (1-200)
        offset: Number of results to skip

    Returns:
        Paginated list of snapshots
    """
    try:
        repo = _get_repository()
        result = await repo.get_config_snapshots(limit=limit, offset=offset)
        return ConfigSnapshotListResponse(
            total=result["total"],
            data=[ConfigSnapshotResponse(**item) for item in result["data"]],
        )
    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/config/snapshots/{snapshot_id}", response_model=ConfigSnapshotResponse)
async def get_snapshot(snapshot_id: int):
    """
    Get a single snapshot by ID.

    Args:
        snapshot_id: Snapshot record ID

    Returns:
        Snapshot details
    """
    try:
        repo = _get_repository()
        snapshot = await repo.get_config_snapshot_by_id(snapshot_id)
        if not snapshot:
            raise HTTPException(status_code=404, detail="Snapshot not found")
        return ConfigSnapshotResponse(**snapshot)
    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/config/snapshots/{snapshot_id}/activate")
async def activate_snapshot(snapshot_id: int):
    """
    Activate a config snapshot (rollback to this version).

    Args:
        snapshot_id: Snapshot record ID

    Returns:
        Success message
    """
    try:
        repo = _get_repository()
        snapshot = await repo.get_config_snapshot_by_id(snapshot_id)
        if not snapshot:
            raise HTTPException(status_code=404, detail="Snapshot not found")

        success = await repo.activate_config_snapshot(snapshot_id)
        if success:
            # TODO: Trigger config reload with snapshot config
            return {"message": f"Activated snapshot {snapshot_id}"}
        else:
            raise HTTPException(status_code=500, detail="Failed to activate snapshot")
    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e)}


@app.delete("/api/config/snapshots/{snapshot_id}")
async def delete_snapshot(snapshot_id: int):
    """
    Delete a config snapshot.

    Args:
        snapshot_id: Snapshot record ID

    Returns:
        Success message
    """
    try:
        repo = _get_repository()
        success = await repo.delete_config_snapshot(snapshot_id)
        if not success:
            raise HTTPException(status_code=404, detail="Snapshot not found")
        return {"message": f"Deleted snapshot {snapshot_id}"}
    except HTTPException:
        raise
    except Exception as e:
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
