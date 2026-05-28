"""BRC-first FastAPI composition root.

The execution runtime is still owned by ``src.main``. This module only binds
that runtime context into ``app.state.runtime`` and mounts the current operator
console API surface.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable, Optional
import logging

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

if load_dotenv is not None:
    _repo_root = Path(__file__).resolve().parents[2]
    load_dotenv(_repo_root / ".env")
    load_dotenv(_repo_root / ".env.local", override=True)

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from src.application.runtime_context import RuntimeContext
from src.domain.models import ErrorResponse
from src.infrastructure.connection_pool import close_all_connections
from src.infrastructure.database import close_db
from src.interfaces import api_config_globals as _config_globals
from src.interfaces.api_brc_console import (
    dev_testnet_router,
    operator_router,
    router as brc_router,
    workflow_router,
)
from src.interfaces.api_runtime_safety import router as runtime_safety_router
from src.interfaces.operator_auth import router as auth_router


logger = logging.getLogger(__name__)


_repository: Optional[Any] = None
_account_getter: Optional[Callable[[], Any]] = None
_config_manager: Optional[Any] = None
_exchange_gateway: Optional[Any] = None
_signal_tracker: Optional[Any] = None
_snapshot_service: Optional[Any] = None
_config_entry_repo: Optional[Any] = None
_order_repo: Optional[Any] = None
_execution_intent_repo: Optional[Any] = None
_execution_recovery_repo: Optional[Any] = None
_position_repo: Optional[Any] = None
_signal_repo: Optional[Any] = None
_audit_logger: Optional[Any] = None
_order_lifecycle_service: Optional[Any] = None
_runtime_config_provider: Optional[Any] = None
_global_kill_switch_service: Optional[Any] = None
_startup_trading_guard_service: Optional[Any] = None
_account_risk_service: Optional[Any] = None
_campaign_state_service: Optional[Any] = None
_brc_campaign_service: Optional[Any] = None
_brc_operation_service: Optional[Any] = None
_brc_admission_service: Optional[Any] = None
_trace_service: Optional[Any] = None
_startup_reconciliation_summary: Optional[dict[str, Any]] = None
_runtime_context: Optional[RuntimeContext] = None
_position_manager: Optional[Any] = None
_capital_protection: Optional[Any] = None
_account_service: Optional[Any] = None
_execution_orchestrator: Optional[Any] = None


def get_runtime_context() -> Optional[RuntimeContext]:
    """Return the runtime context bound by ``src.main``."""
    if _runtime_context is not None:
        return _runtime_context
    context = getattr(app.state, "runtime", None) if "app" in globals() else None
    if isinstance(context, RuntimeContext):
        return context
    return None


def clear_runtime_context(target_app: Optional[FastAPI] = None) -> None:
    """Clear process-local runtime globals after shutdown."""
    global _runtime_context
    _runtime_context = None
    if target_app is None and "app" in globals():
        target_app = app
    if target_app is not None and hasattr(target_app.state, "runtime"):
        target_app.state.runtime = None
    set_dependencies()
    set_v3_dependencies()


def bind_runtime_context(
    runtime_context: RuntimeContext,
    target_app: Optional[FastAPI] = None,
) -> None:
    """Bind a main-owned runtime context to API compatibility globals."""
    global _runtime_context
    _runtime_context = runtime_context

    if target_app is None and "app" in globals():
        target_app = app
    if target_app is not None:
        target_app.state.runtime = runtime_context

    set_dependencies(
        repository=runtime_context.signal_repository,
        account_getter=runtime_context.get_account_snapshot,
        config_manager=runtime_context.config_manager,
        exchange_gateway=runtime_context.exchange_gateway,
        signal_tracker=runtime_context.signal_tracker,
        snapshot_service=runtime_context.snapshot_service,
        config_entry_repo=runtime_context.config_entry_repo,
        order_repo=runtime_context.order_repo,
        execution_intent_repo=runtime_context.execution_intent_repo,
        execution_recovery_repo=runtime_context.execution_recovery_repo,
        position_repo=runtime_context.position_repo,
        audit_logger=runtime_context.audit_logger,
        order_lifecycle_service=runtime_context.order_lifecycle_service,
        runtime_config_provider=runtime_context.runtime_config_provider,
        global_kill_switch_service=runtime_context.global_kill_switch_service,
        startup_trading_guard_service=runtime_context.startup_trading_guard_service,
        account_risk_service=runtime_context.account_risk_service,
        campaign_state_service=runtime_context.campaign_state_service,
        brc_campaign_service=runtime_context.brc_campaign_service,
        trace_service=runtime_context.trace_service,
        strategy_repo=runtime_context.strategy_repo,
        risk_repo=runtime_context.risk_repo,
        system_repo=runtime_context.system_repo,
        symbol_repo=runtime_context.symbol_repo,
        notification_repo=runtime_context.notification_repo,
        history_repo=runtime_context.history_repo,
        snapshot_repo=runtime_context.snapshot_repo,
    )
    set_v3_dependencies(
        capital_protection=runtime_context.capital_protection,
        account_service=runtime_context.account_service,
        execution_orchestrator=runtime_context.execution_orchestrator,
        startup_reconciliation_summary=runtime_context.startup_reconciliation_summary,
    )


def set_dependencies(
    repository: Optional[Any] = None,
    account_getter: Optional[Callable[[], Any]] = None,
    config_manager: Optional[Any] = None,
    exchange_gateway: Optional[Any] = None,
    signal_tracker: Optional[Any] = None,
    snapshot_service: Optional[Any] = None,
    config_entry_repo: Optional[Any] = None,
    order_repo: Optional[Any] = None,
    execution_intent_repo: Optional[Any] = None,
    execution_recovery_repo: Optional[Any] = None,
    position_repo: Optional[Any] = None,
    audit_logger: Optional[Any] = None,
    order_lifecycle_service: Optional[Any] = None,
    runtime_config_provider: Optional[Any] = None,
    global_kill_switch_service: Optional[Any] = None,
    startup_trading_guard_service: Optional[Any] = None,
    account_risk_service: Optional[Any] = None,
    campaign_state_service: Optional[Any] = None,
    brc_campaign_service: Optional[Any] = None,
    trace_service: Optional[Any] = None,
    strategy_repo: Optional[Any] = None,
    risk_repo: Optional[Any] = None,
    system_repo: Optional[Any] = None,
    symbol_repo: Optional[Any] = None,
    notification_repo: Optional[Any] = None,
    history_repo: Optional[Any] = None,
    snapshot_repo: Optional[Any] = None,
) -> None:
    """Inject runtime dependencies for BRC console adapters and legacy tests."""
    global _repository, _account_getter, _config_manager, _exchange_gateway
    global _signal_tracker, _snapshot_service, _config_entry_repo, _order_repo
    global _execution_intent_repo, _execution_recovery_repo, _position_repo
    global _signal_repo, _audit_logger, _order_lifecycle_service
    global _runtime_config_provider, _global_kill_switch_service
    global _startup_trading_guard_service, _account_risk_service
    global _campaign_state_service, _brc_campaign_service, _trace_service

    _repository = repository
    _signal_repo = repository
    _account_getter = account_getter
    _config_manager = config_manager
    _exchange_gateway = exchange_gateway
    _signal_tracker = signal_tracker
    _snapshot_service = snapshot_service
    _config_entry_repo = config_entry_repo
    _order_repo = order_repo
    _execution_intent_repo = execution_intent_repo
    _execution_recovery_repo = execution_recovery_repo
    _position_repo = position_repo
    _audit_logger = audit_logger
    _order_lifecycle_service = order_lifecycle_service
    _runtime_config_provider = runtime_config_provider
    _global_kill_switch_service = global_kill_switch_service
    _startup_trading_guard_service = startup_trading_guard_service
    _account_risk_service = account_risk_service
    _campaign_state_service = campaign_state_service
    _brc_campaign_service = brc_campaign_service
    _trace_service = trace_service

    _config_globals._config_manager = config_manager
    _config_globals._strategy_repo = strategy_repo
    _config_globals._risk_repo = risk_repo
    _config_globals._system_repo = system_repo
    _config_globals._symbol_repo = symbol_repo
    _config_globals._notification_repo = notification_repo
    _config_globals._history_repo = history_repo
    _config_globals._snapshot_repo = snapshot_repo


def set_v3_dependencies(
    position_manager: Optional[Any] = None,
    capital_protection: Optional[Any] = None,
    account_service: Optional[Any] = None,
    execution_orchestrator: Optional[Any] = None,
    startup_reconciliation_summary: Optional[dict[str, Any]] = None,
) -> None:
    """Inject execution/runtime services still read by controlled testnet adapters."""
    global _position_manager, _capital_protection, _account_service
    global _execution_orchestrator, _startup_reconciliation_summary
    _position_manager = position_manager
    _capital_protection = capital_protection
    _account_service = account_service
    _execution_orchestrator = execution_orchestrator
    _startup_reconciliation_summary = startup_reconciliation_summary


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        yield
    finally:
        if get_runtime_context() is None:
            await close_db()
            await close_all_connections()


app = FastAPI(
    title="BRC Operator Console API",
    description="Local Bounded Risk Campaign operator API. No real-live, withdrawal, or autonomous strategy execution.",
    version="4.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(runtime_safety_router)
app.include_router(brc_router)
app.include_router(operator_router)
app.include_router(workflow_router)
app.include_router(dev_testnet_router)


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "brc_operator_console",
        "runtime_bound": get_runtime_context() is not None,
        "live_ready": False,
    }


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict):
        content = exc.detail
        if "error_code" not in content:
            content = {"error_code": str(exc.status_code), "message": str(exc.detail)}
    else:
        content = ErrorResponse(error_code=str(exc.status_code), message=str(exc.detail)).model_dump()
    return JSONResponse(status_code=exc.status_code, content=content)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(error_code="VALIDATION_ERROR", message=str(exc)).model_dump(),
    )


@app.exception_handler(ValidationError)
async def pydantic_validation_exception_handler(_request: Request, exc: ValidationError):
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(error_code="VALIDATION_ERROR", message=str(exc)).model_dump(),
    )
