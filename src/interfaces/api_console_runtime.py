from __future__ import annotations

from fastapi import APIRouter

from src.application.readmodels.console_models import (
    RuntimeHealthResponse,
    RuntimeOverviewResponse,
    RuntimePortfolioResponse,
)
from src.application.readmodels.runtime_health import RuntimeHealthReadModel
from src.application.readmodels.runtime_overview import RuntimeOverviewReadModel
from src.application.readmodels.runtime_portfolio import RuntimePortfolioReadModel

router = APIRouter(prefix="/api/runtime", tags=["Console Runtime"])


def _load_api_module():
    from src.interfaces import api as api_module

    return api_module


@router.get("/overview", response_model=RuntimeOverviewResponse)
async def get_runtime_overview() -> RuntimeOverviewResponse:
    api_module = _load_api_module()
    account_snapshot = api_module._account_getter() if api_module._account_getter else None
    read_model = RuntimeOverviewReadModel()
    return await read_model.build(
        runtime_config_provider=getattr(api_module, "_runtime_config_provider", None),
        account_snapshot=account_snapshot,
        exchange_gateway=getattr(api_module, "_exchange_gateway", None),
        execution_orchestrator=getattr(api_module, "_execution_orchestrator", None),
        startup_reconciliation_summary=getattr(api_module, "_startup_reconciliation_summary", None),
    )


@router.get("/portfolio", response_model=RuntimePortfolioResponse)
async def get_runtime_portfolio() -> RuntimePortfolioResponse:
    api_module = _load_api_module()
    account_snapshot = api_module._account_getter() if api_module._account_getter else None
    read_model = RuntimePortfolioReadModel()
    return await read_model.build(
        runtime_config_provider=getattr(api_module, "_runtime_config_provider", None),
        capital_protection=getattr(api_module, "_capital_protection", None),
        account_snapshot=account_snapshot,
    )


@router.get("/health", response_model=RuntimeHealthResponse)
async def get_runtime_health() -> RuntimeHealthResponse:
    api_module = _load_api_module()
    account_snapshot = api_module._account_getter() if api_module._account_getter else None
    read_model = RuntimeHealthReadModel()
    return await read_model.build(
        runtime_config_provider=getattr(api_module, "_runtime_config_provider", None),
        exchange_gateway=getattr(api_module, "_exchange_gateway", None),
        execution_orchestrator=getattr(api_module, "_execution_orchestrator", None),
        execution_recovery_repo=getattr(api_module, "_execution_recovery_repo", None),
        startup_reconciliation_summary=getattr(api_module, "_startup_reconciliation_summary", None),
        account_snapshot=account_snapshot,
    )

