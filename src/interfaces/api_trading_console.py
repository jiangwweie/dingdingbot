"""Trading Console read-only API namespace."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from src.application.readmodels.trading_console import (
    TradingConsoleDependencies,
    TradingConsoleReadModelResponse,
    TradingConsoleReadModelService,
)
from src.interfaces.operator_auth import require_operator_session


router = APIRouter(
    prefix="/api/trading-console",
    tags=["Trading Console Read Models"],
    dependencies=[Depends(require_operator_session)],
)


@router.get("/dashboard-state", response_model=TradingConsoleReadModelResponse)
async def dashboard_state(
    symbol: Optional[str] = Query(default=None),
    include_exchange: bool = Query(default=False),
) -> TradingConsoleReadModelResponse:
    return await _service(include_exchange=include_exchange).dashboard_state(
        symbol=symbol,
        include_exchange=include_exchange,
    )


@router.get("/account-risk", response_model=TradingConsoleReadModelResponse)
async def account_risk(
    symbol: Optional[str] = Query(default=None),
    include_exchange: bool = Query(default=False),
) -> TradingConsoleReadModelResponse:
    return await _service(include_exchange=include_exchange).account_risk(
        symbol=symbol,
        include_exchange=include_exchange,
    )


@router.get("/order-ledger", response_model=TradingConsoleReadModelResponse)
async def order_ledger(
    symbol: Optional[str] = Query(default=None),
    include_exchange: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
) -> TradingConsoleReadModelResponse:
    return await _service(include_exchange=include_exchange).order_ledger(
        symbol=symbol,
        include_exchange=include_exchange,
        limit=limit,
    )


@router.get("/protection-health", response_model=TradingConsoleReadModelResponse)
async def protection_health(
    symbol: Optional[str] = Query(default=None),
    include_exchange: bool = Query(default=False),
) -> TradingConsoleReadModelResponse:
    return await _service(include_exchange=include_exchange).protection_health(
        symbol=symbol,
        include_exchange=include_exchange,
    )


@router.get("/recovery-exception-state", response_model=TradingConsoleReadModelResponse)
async def recovery_exception_state(
    symbol: Optional[str] = Query(default=None),
    include_exchange: bool = Query(default=False),
) -> TradingConsoleReadModelResponse:
    return await _service(include_exchange=include_exchange).recovery_exception_state(
        symbol=symbol,
        include_exchange=include_exchange,
    )


@router.get("/authorization-state", response_model=TradingConsoleReadModelResponse)
async def authorization_state(
    symbol: Optional[str] = Query(default=None),
) -> TradingConsoleReadModelResponse:
    return await _service(include_exchange=False).authorization_state(symbol=symbol)


@router.get("/execution-control-state", response_model=TradingConsoleReadModelResponse)
async def execution_control_state(
    symbol: Optional[str] = Query(default=None),
    include_exchange: bool = Query(default=False),
) -> TradingConsoleReadModelResponse:
    return await _service(include_exchange=include_exchange).execution_control_state(
        symbol=symbol,
        include_exchange=include_exchange,
    )


@router.get("/review-state", response_model=TradingConsoleReadModelResponse)
async def review_state(
    symbol: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> TradingConsoleReadModelResponse:
    return await _service(include_exchange=False).review_state(symbol=symbol, limit=limit)


@router.get("/audit-chain", response_model=TradingConsoleReadModelResponse)
async def audit_chain(
    authorization_id: Optional[str] = Query(default=None),
    intent_id: Optional[str] = Query(default=None),
    order_id: Optional[str] = Query(default=None),
    exchange_order_id: Optional[str] = Query(default=None),
    symbol: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> TradingConsoleReadModelResponse:
    return await _service(include_exchange=False).audit_chain(
        authorization_id=authorization_id,
        intent_id=intent_id,
        order_id=order_id,
        exchange_order_id=exchange_order_id,
        symbol=symbol,
        limit=limit,
    )


@router.get("/carrier-availability", response_model=TradingConsoleReadModelResponse)
async def carrier_availability(
    include_exchange: bool = Query(default=False),
) -> TradingConsoleReadModelResponse:
    return await _service(include_exchange=include_exchange).carrier_availability(include_exchange=include_exchange)


@router.get("/signal-marker-feed", response_model=TradingConsoleReadModelResponse)
async def signal_marker_feed(
    symbol: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> TradingConsoleReadModelResponse:
    return await _service(include_exchange=False).signal_marker_feed(symbol=symbol, limit=limit)


@router.get("/api-classification", response_model=TradingConsoleReadModelResponse)
async def api_classification() -> TradingConsoleReadModelResponse:
    return _service(include_exchange=False).api_classification()


def _service(*, include_exchange: bool = False) -> TradingConsoleReadModelService:
    return TradingConsoleReadModelService(_dependencies(include_exchange=include_exchange))


def _dependencies(*, include_exchange: bool = False) -> TradingConsoleDependencies:
    from src.interfaces import api as api_module

    account_snapshot = None
    if include_exchange:
        account_getter = getattr(api_module, "_account_getter", None)
        if callable(account_getter):
            try:
                account_snapshot = account_getter()
            except Exception:
                account_snapshot = None
        if account_snapshot is None:
            gateway = getattr(api_module, "_exchange_gateway", None)
            if gateway is not None and hasattr(gateway, "get_account_snapshot"):
                try:
                    account_snapshot = gateway.get_account_snapshot()
                except Exception:
                    account_snapshot = None

    return TradingConsoleDependencies(
        runtime_bound=bool(api_module.get_runtime_context() is not None),
        runtime_config_provider=getattr(api_module, "_runtime_config_provider", None),
        account_snapshot=account_snapshot,
        exchange_gateway=getattr(api_module, "_exchange_gateway", None),
        order_repo=getattr(api_module, "_order_repo", None),
        position_repo=getattr(api_module, "_position_repo", None),
        execution_intent_repo=getattr(api_module, "_execution_intent_repo", None),
        execution_recovery_repo=getattr(api_module, "_execution_recovery_repo", None),
        audit_logger=getattr(api_module, "_audit_logger", None),
        signal_repo=getattr(api_module, "_signal_repo", None),
        brc_campaign_service=getattr(api_module, "_brc_campaign_service", None),
        owner_trial_flow_service=_owner_trial_flow_service(),
        global_kill_switch_service=getattr(api_module, "_global_kill_switch_service", None),
        startup_trading_guard_service=getattr(api_module, "_startup_trading_guard_service", None),
        startup_reconciliation_summary=getattr(api_module, "_startup_reconciliation_summary", None),
        execution_orchestrator=getattr(api_module, "_execution_orchestrator", None),
    )


def _owner_trial_flow_service() -> Optional[Any]:
    from src.interfaces import api as api_module

    injected = getattr(api_module, "_owner_trial_flow_service", None)
    if injected is not None:
        return injected
    try:
        from src.interfaces.api_brc_console import _owner_trial_flow_service_instance

        return _owner_trial_flow_service_instance()
    except Exception:
        return None
