from __future__ import annotations

from fastapi import APIRouter, Query
from typing import Optional

from src.application.readmodels.console_models import (
    ConsoleAttemptsResponse,
    ConsoleEventsResponse,
    ConsoleExecutionIntentsResponse,
    ConsoleOrdersResponse,
    ConsolePositionsResponse,
    ConsoleSignalsResponse,
    RuntimeHealthResponse,
    RuntimeOverviewResponse,
    RuntimePortfolioResponse,
)
from src.application.readmodels.runtime_attempts import RuntimeAttemptsReadModel
from src.application.readmodels.runtime_events import RuntimeEventsReadModel
from src.application.readmodels.runtime_execution_intents import RuntimeExecutionIntentsReadModel
from src.application.readmodels.runtime_health import RuntimeHealthReadModel
from src.application.readmodels.runtime_orders import RuntimeOrdersReadModel
from src.application.readmodels.runtime_overview import RuntimeOverviewReadModel
from src.application.readmodels.runtime_portfolio import RuntimePortfolioReadModel
from src.application.readmodels.runtime_positions import RuntimePositionsReadModel
from src.application.readmodels.runtime_signals import RuntimeSignalsReadModel

router = APIRouter(prefix="/api/runtime", tags=["Console Runtime"])


def _load_api_module():
    from src.interfaces import api as api_module

    return api_module


def _get_account_snapshot(api_module):
    if getattr(api_module, "_account_getter", None):
        return api_module._account_getter()

    gateway = getattr(api_module, "_exchange_gateway", None)
    if gateway is not None and hasattr(gateway, "get_account_snapshot"):
        try:
            return gateway.get_account_snapshot()
        except Exception:
            return None
    return None


@router.get("/overview", response_model=RuntimeOverviewResponse)
async def get_runtime_overview() -> RuntimeOverviewResponse:
    api_module = _load_api_module()
    account_snapshot = _get_account_snapshot(api_module)
    read_model = RuntimeOverviewReadModel()
    return await read_model.build(
        runtime_config_provider=getattr(api_module, "_runtime_config_provider", None),
        account_snapshot=account_snapshot,
        exchange_gateway=getattr(api_module, "_exchange_gateway", None),
        execution_orchestrator=getattr(api_module, "_execution_orchestrator", None),
        startup_reconciliation_summary=getattr(api_module, "_startup_reconciliation_summary", None),
        order_repo=getattr(api_module, "_order_repo", None),
        position_repo=getattr(api_module, "_position_repo", None),
        execution_intent_repo=getattr(api_module, "_execution_intent_repo", None),
    )


@router.get("/portfolio", response_model=RuntimePortfolioResponse)
async def get_runtime_portfolio() -> RuntimePortfolioResponse:
    api_module = _load_api_module()
    account_snapshot = _get_account_snapshot(api_module)
    read_model = RuntimePortfolioReadModel()
    return await read_model.build(
        runtime_config_provider=getattr(api_module, "_runtime_config_provider", None),
        capital_protection=getattr(api_module, "_capital_protection", None),
        account_snapshot=account_snapshot,
    )


@router.get("/health", response_model=RuntimeHealthResponse)
async def get_runtime_health() -> RuntimeHealthResponse:
    api_module = _load_api_module()
    account_snapshot = _get_account_snapshot(api_module)
    read_model = RuntimeHealthReadModel()
    return await read_model.build(
        runtime_config_provider=getattr(api_module, "_runtime_config_provider", None),
        exchange_gateway=getattr(api_module, "_exchange_gateway", None),
        execution_orchestrator=getattr(api_module, "_execution_orchestrator", None),
        execution_recovery_repo=getattr(api_module, "_execution_recovery_repo", None),
        startup_reconciliation_summary=getattr(api_module, "_startup_reconciliation_summary", None),
        account_snapshot=account_snapshot,
    )


# ============================================================
# Second Batch: Positions / Signals / Attempts / Orders / Intents
# ============================================================


@router.get("/positions", response_model=ConsolePositionsResponse)
async def get_runtime_positions() -> ConsolePositionsResponse:
    """Get current positions from account snapshot."""
    api_module = _load_api_module()
    account_snapshot = _get_account_snapshot(api_module)
    read_model = RuntimePositionsReadModel()
    return await read_model.build(
        account_snapshot=account_snapshot,
        position_repo=getattr(api_module, "_position_repo", None),
    )


@router.get("/signals", response_model=ConsoleSignalsResponse)
async def get_runtime_signals(
    symbol: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
) -> ConsoleSignalsResponse:
    """Get recent signals from signal repository."""
    api_module = _load_api_module()
    read_model = RuntimeSignalsReadModel()
    return await read_model.build(
        signal_repo=getattr(api_module, "_signal_repo", None),
        symbol=symbol,
        limit=limit,
    )


@router.get("/attempts", response_model=ConsoleAttemptsResponse)
async def get_runtime_attempts(
    symbol: Optional[str] = Query(None),
    timeframe: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
) -> ConsoleAttemptsResponse:
    """Get recent attempts from signal repository."""
    api_module = _load_api_module()
    read_model = RuntimeAttemptsReadModel()
    return await read_model.build(
        signal_repo=getattr(api_module, "_signal_repo", None),
        symbol=symbol,
        timeframe=timeframe,
        limit=limit,
    )


@router.get("/execution/orders", response_model=ConsoleOrdersResponse)
async def get_runtime_orders(
    symbol: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
) -> ConsoleOrdersResponse:
    """Get recent orders from order repository."""
    api_module = _load_api_module()
    read_model = RuntimeOrdersReadModel()
    return await read_model.build(
        order_repo=getattr(api_module, "_order_repo", None),
        symbol=symbol,
        status=status,
        limit=limit,
    )


@router.get("/execution/intents", response_model=ConsoleExecutionIntentsResponse)
async def get_runtime_execution_intents(
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
) -> ConsoleExecutionIntentsResponse:
    """Get execution intents from intent repository."""
    api_module = _load_api_module()
    read_model = RuntimeExecutionIntentsReadModel()
    return await read_model.build(
        intent_repo=getattr(api_module, "_execution_intent_repo", None),
        status=status,
        limit=limit,
    )


@router.get("/events", response_model=ConsoleEventsResponse)
async def get_runtime_events(limit: int = Query(100, ge=1, le=500)) -> ConsoleEventsResponse:
    """Runtime event timeline aggregated from signals, orders, startup, breakers, recovery."""
    api_module = _load_api_module()
    readmodel = RuntimeEventsReadModel()
    return await readmodel.build(
        signal_repo=getattr(api_module, "_signal_repo", None),
        audit_logger=getattr(api_module, "_audit_logger", None),
        execution_orchestrator=getattr(api_module, "_execution_orchestrator", None),
        startup_reconciliation_summary=getattr(api_module, "_startup_reconciliation_summary", None),
        execution_recovery_repo=getattr(api_module, "_execution_recovery_repo", None),
        limit=limit,
    )
