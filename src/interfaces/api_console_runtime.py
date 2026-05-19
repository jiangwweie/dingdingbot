from __future__ import annotations

import os
import logging
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from typing import Literal, Optional

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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/runtime", tags=["Console Runtime"])

RUNTIME_CONTROL_API_ENABLED_ENV = "RUNTIME_CONTROL_API_ENABLED"
RUNTIME_TEST_SIGNAL_INJECTION_ENABLED_ENV = "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED"

_CONTROLLED_ENTRY_EXECUTED: bool = False


class GlobalKillSwitchResponse(BaseModel):
    active: bool
    reason: Optional[str] = None
    updated_by: str
    updated_at_ms: int
    source: str
    live_ready: Literal[False] = False
    access_boundary: str = (
        "Local/internal runtime control only. This endpoint is not a public "
        "internet control plane."
    )
    missing_row_policy: str = "PG row missing blocks new entries fail-closed."


class GlobalKillSwitchToggleRequest(BaseModel):
    active: bool = Field(..., description="True blocks all new entries")
    reason: Optional[str] = Field(default=None, max_length=512)
    updated_by: str = Field(default="owner", max_length=128)


class StartupTradingGuardResponse(BaseModel):
    armed: bool
    reason: Optional[str] = None
    updated_by: str
    updated_at_ms: int
    source: str
    live_ready: Literal[False] = False
    access_boundary: str = (
        "Local/internal runtime control only. This endpoint is not a public "
        "internet control plane."
    )


class StartupTradingGuardArmRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=512)
    updated_by: str = Field(default="owner", max_length=128)


def _load_api_module():
    from src.interfaces import api as api_module

    return api_module


def _require_internal_runtime_control(request: Request) -> None:
    host = request.client.host if request.client else ""
    if host in {"127.0.0.1", "::1", "localhost", "testclient"}:
        return
    raise HTTPException(
        status_code=403,
        detail=(
            "Runtime control is restricted to local/internal runtime "
            "access. It must not be exposed as a public control plane."
        ),
    )


def _runtime_control_api_enabled() -> bool:
    return os.getenv(RUNTIME_CONTROL_API_ENABLED_ENV, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _require_runtime_control_api_enabled() -> None:
    if _runtime_control_api_enabled():
        return
    raise HTTPException(
        status_code=403,
        detail=(
            "Runtime control API mutation is disabled. Set "
            f"{RUNTIME_CONTROL_API_ENABLED_ENV}=true to allow this local control action."
        ),
    )


def _get_global_kill_switch_service(api_module):
    service = getattr(api_module, "_global_kill_switch_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Global Kill Switch service not initialized")
    return service


def _get_startup_trading_guard_service(api_module):
    service = getattr(api_module, "_startup_trading_guard_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Startup trading guard service not initialized")
    return service


def _to_global_kill_switch_response(state) -> GlobalKillSwitchResponse:
    return GlobalKillSwitchResponse(
        active=state.active,
        reason=state.reason,
        updated_by=state.updated_by,
        updated_at_ms=state.updated_at_ms,
        source=state.source,
    )


def _to_startup_trading_guard_response(state) -> StartupTradingGuardResponse:
    return StartupTradingGuardResponse(
        armed=state.armed,
        reason=state.reason,
        updated_by=state.updated_by,
        updated_at_ms=state.updated_at_ms,
        source=state.source,
    )


# ---------------------------------------------------------------
# 001D-1A: Controlled Synthetic Signal Injection
# ---------------------------------------------------------------

_CONTROLLED_SYMBOL = "ETH/USDT:USDT"
_CONTROLLED_AMOUNT_MAX = Decimal("0.01")
_CONTROLLED_PROFILE = "sim1_eth_runtime"
_CONTROLLED_MIN_NOTIONAL_DEFAULT = Decimal("20")


def _test_signal_injection_enabled() -> bool:
    return os.getenv(RUNTIME_TEST_SIGNAL_INJECTION_ENABLED_ENV, "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _get_orchestrator(api_module):
    orch = getattr(api_module, "_execution_orchestrator", None)
    if orch is None:
        raise HTTPException(status_code=503, detail="Execution orchestrator not initialized")
    return orch


def _get_gateway(api_module):
    gw = getattr(api_module, "_exchange_gateway", None)
    if gw is None:
        raise HTTPException(status_code=503, detail="Exchange gateway not initialized")
    return gw


def _get_trace_service(api_module):
    return getattr(api_module, "_trace_service", None)


class ControlledEntryResponse(BaseModel):
    status: str
    intent_id: Optional[str] = None
    signal_id: Optional[str] = None
    entry_price: Optional[Decimal] = None
    stop_loss: Optional[Decimal] = None
    testnet: Literal[True] = True
    profile: str = _CONTROLLED_PROFILE
    amount: Decimal
    blocked_reason: Optional[str] = None
    attempt_locked: bool = False
    notional: Optional[Decimal] = None
    min_notional: Optional[Decimal] = None


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


async def _reject_controlled_entry_body(request: Request) -> None:
    body = await request.body()
    if body.strip():
        raise HTTPException(
            status_code=400,
            detail=(
                "Request body is not accepted for controlled signal injection; "
                "symbol, direction, amount, price, SL, and TP are server-controlled."
            ),
        )


def _to_decimal(value) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _extract_min_notional_from_market(market) -> Optional[Decimal]:
    if not isinstance(market, dict):
        return None
    limits = market.get("limits")
    if isinstance(limits, dict):
        cost = limits.get("cost")
        if isinstance(cost, dict):
            value = _to_decimal(cost.get("min"))
            if value is not None:
                return value
    value = _to_decimal(market.get("min_notional") or market.get("minNotional"))
    return value


def _get_controlled_min_notional(gateway) -> tuple[Decimal, str]:
    for attr_name in ("get_min_notional", "min_notional_for_symbol"):
        attr = getattr(gateway, attr_name, None)
        if callable(attr):
            try:
                value = _to_decimal(attr(_CONTROLLED_SYMBOL))
            except Exception:
                value = None
            if value is not None:
                return value, attr_name

    markets = getattr(gateway, "markets", None)
    if isinstance(markets, dict):
        value = _extract_min_notional_from_market(markets.get(_CONTROLLED_SYMBOL))
        if value is not None:
            return value, "gateway.markets"

    market_metadata = getattr(gateway, "market_metadata", None)
    if isinstance(market_metadata, dict):
        value = _extract_min_notional_from_market(market_metadata.get(_CONTROLLED_SYMBOL))
        if value is not None:
            return value, "gateway.market_metadata"

    logger.warning(
        "Controlled signal injection using conservative default min_notional=%s for %s",
        _CONTROLLED_MIN_NOTIONAL_DEFAULT,
        _CONTROLLED_SYMBOL,
    )
    return _CONTROLLED_MIN_NOTIONAL_DEFAULT, "default"


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
        execution_recovery_repo=getattr(api_module, "_execution_recovery_repo", None),
        signal_repo=getattr(api_module, "_signal_repo", None),
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


@router.get("/control/global-kill-switch", response_model=GlobalKillSwitchResponse)
async def get_global_kill_switch(request: Request) -> GlobalKillSwitchResponse:
    """Read GKS-v0 state. Local/internal runtime control surface only."""
    _require_internal_runtime_control(request)
    api_module = _load_api_module()
    service = _get_global_kill_switch_service(api_module)
    return _to_global_kill_switch_response(service.get_state())


@router.post("/control/global-kill-switch", response_model=GlobalKillSwitchResponse)
async def toggle_global_kill_switch(
    request: Request,
    body: GlobalKillSwitchToggleRequest,
) -> GlobalKillSwitchResponse:
    """Toggle GKS-v0. Local/internal runtime control surface only."""
    _require_internal_runtime_control(request)
    _require_runtime_control_api_enabled()
    api_module = _load_api_module()
    service = _get_global_kill_switch_service(api_module)
    try:
        state = await service.set_state(
            active=body.active,
            reason=body.reason,
            updated_by=body.updated_by,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Global Kill Switch persistence failed: {exc}",
        ) from exc
    return _to_global_kill_switch_response(state)


@router.get("/control/startup-trading-guard", response_model=StartupTradingGuardResponse)
async def get_startup_trading_guard(request: Request) -> StartupTradingGuardResponse:
    """Read startup trading guard state. Local/internal runtime control surface only."""
    _require_internal_runtime_control(request)
    api_module = _load_api_module()
    service = _get_startup_trading_guard_service(api_module)
    return _to_startup_trading_guard_response(service.get_state())


@router.post("/control/startup-trading-guard/arm", response_model=StartupTradingGuardResponse)
async def arm_startup_trading_guard(
    request: Request,
    body: StartupTradingGuardArmRequest,
) -> StartupTradingGuardResponse:
    """Manually arm startup trading guard after operator startup checks."""
    _require_internal_runtime_control(request)
    _require_runtime_control_api_enabled()
    api_module = _load_api_module()
    service = _get_startup_trading_guard_service(api_module)
    state = service.manual_arm(reason=body.reason, updated_by=body.updated_by)
    return _to_startup_trading_guard_response(state)


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


@router.post(
    "/test/smoke/execute-controlled-entry",
    response_model=ControlledEntryResponse,
)
async def execute_controlled_entry(request: Request) -> ControlledEntryResponse:
    """Controlled synthetic signal injection for 001D-1 testnet smoke.

    Extremely narrow, testnet-only, env-gated, profile-gated endpoint that
    constructs a fixed controlled signal and feeds it into the execution
    orchestrator. Does NOT modify strategy logic, Direction A, or any
    production trading path.
    """
    global _CONTROLLED_ENTRY_EXECUTED

    from src.domain.models import Direction, OrderStrategy, SignalResult

    # --- Gate 1: env flag ---
    if not _test_signal_injection_enabled():
        raise HTTPException(
            status_code=403,
            detail=(
                "Controlled signal injection disabled. "
                f"Set {RUNTIME_TEST_SIGNAL_INJECTION_ENABLED_ENV}=true."
            ),
        )

    # --- Gate 2: runtime control API ---
    if not _runtime_control_api_enabled():
        raise HTTPException(
            status_code=403,
            detail=(
                "Runtime control API disabled. "
                f"Set {RUNTIME_CONTROL_API_ENABLED_ENV}=true."
            ),
        )

    # --- Localhost only ---
    _require_internal_runtime_control(request)
    await _reject_controlled_entry_body(request)

    api_module = _load_api_module()

    # --- Gate 3: EXCHANGE_TESTNET ---
    config_provider = getattr(api_module, "_runtime_config_provider", None)
    resolved = config_provider.resolved_config if config_provider else None
    if resolved is None:
        raise HTTPException(status_code=503, detail="Runtime config not resolved")
    if not resolved.environment.exchange_testnet:
        raise HTTPException(status_code=403, detail="Endpoint requires EXCHANGE_TESTNET=true")

    # --- Gate 4: profile ---
    if resolved.profile_name != _CONTROLLED_PROFILE:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Endpoint requires RUNTIME_PROFILE={_CONTROLLED_PROFILE}, "
                f"got {resolved.profile_name}"
            ),
        )

    # --- Gate 5: parameter bounds (server-side enforced, no user override) ---
    # All parameters are fixed by the server. No request body accepted.

    # --- Gate 6: once-per-session ---
    if _CONTROLLED_ENTRY_EXECUTED:
        raise HTTPException(
            status_code=409,
            detail="Controlled entry already executed in this runtime session",
        )

    # --- Gate 7: safety gates ---
    orchestrator = _get_orchestrator(api_module)

    # 7a: startup guard armed
    guard_svc = getattr(api_module, "_startup_trading_guard_service", None)
    if guard_svc is None or not guard_svc.is_armed():
        raise HTTPException(
            status_code=409,
            detail="BLOCKED: startup guard not armed",
        )

    # 7b: GKS inactive
    gks_svc = getattr(api_module, "_global_kill_switch_service", None)
    if gks_svc is None:
        raise HTTPException(
            status_code=503,
            detail="BLOCKED: GKS_SERVICE_UNAVAILABLE",
        )
    if gks_svc.is_active():
        raise HTTPException(
            status_code=409,
            detail="BLOCKED: global kill switch active",
        )

    # 7c: no protection-health block for symbol
    blocks = orchestrator.list_protection_health_blocks()
    if _CONTROLLED_SYMBOL in blocks:
        raise HTTPException(
            status_code=409,
            detail=f"BLOCKED: protection-health block active for {_CONTROLLED_SYMBOL}",
        )

    # 7d: no circuit breaker for symbol
    if orchestrator.is_symbol_blocked(_CONTROLLED_SYMBOL):
        raise HTTPException(
            status_code=409,
            detail=f"BLOCKED: circuit breaker active for {_CONTROLLED_SYMBOL}",
        )

    # --- Fetch market price and build controlled signal ---
    gateway = _get_gateway(api_module)
    try:
        last_price = await gateway.fetch_ticker_price(_CONTROLLED_SYMBOL)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch market price: {exc}",
        ) from exc

    entry_price = Decimal(str(last_price))
    sl_price = entry_price * Decimal("0.99")  # ~1% below entry (~-1 RR)
    tp1_price = entry_price * Decimal("1.01")  # ~1% above (~1.0 RR)
    tp2_price = entry_price * Decimal("1.035")  # ~3.5% above (~3.5 RR)
    amount = _CONTROLLED_AMOUNT_MAX
    min_notional, min_notional_source = _get_controlled_min_notional(gateway)
    notional = entry_price * amount
    if notional < min_notional:
        raise HTTPException(
            status_code=409,
            detail=(
                "BLOCKED: controlled entry notional below min_notional "
                f"({notional} < {min_notional}, source={min_notional_source})"
            ),
        )

    signal = SignalResult(
        symbol=_CONTROLLED_SYMBOL,
        timeframe="1h",
        direction=Direction.LONG,
        entry_price=entry_price,
        suggested_stop_loss=sl_price,
        suggested_position_size=amount,
        current_leverage=1,
        tags=[{"key": "source", "value": "runtime_test_endpoint"}],
        risk_reward_info="controlled_test_smoke:1h:LONG",
        status="PENDING",
        strategy_name="controlled_test_smoke",
        score=1.0,
        take_profit_levels=[
            {"price": str(tp1_price), "ratio": "0.5"},
            {"price": str(tp2_price), "ratio": "0.5"},
        ],
    )

    strategy = OrderStrategy(
        id="strat_controlled_smoke",
        name=f"controlled_test_smoke/{_CONTROLLED_PROFILE}",
        tp_levels=2,
        tp_ratios=[Decimal("0.5"), Decimal("0.5")],
        tp_targets=[Decimal("1.0"), Decimal("3.5")],
        initial_stop_loss_rr=Decimal("-1.0"),
        trailing_stop_enabled=False,
        oco_enabled=True,
    )

    # --- Execute ---
    _CONTROLLED_ENTRY_EXECUTED = True
    try:
        intent = await orchestrator.execute_signal(signal, strategy)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Execution failed: {exc}",
        ) from exc

    # --- Gate 8: trace/audit ---
    trace_svc = _get_trace_service(api_module)
    if trace_svc is not None:
        try:
            trace_svc.emit_risk_decision(
                lifecycle_id=intent.id,
                decision="executed",
                reason="controlled_test_signal_injection",
                metadata={
                    "symbol": _CONTROLLED_SYMBOL,
                    "direction": "LONG",
                    "amount": str(amount),
                    "profile": _CONTROLLED_PROFILE,
                    "testnet": True,
                    "source": "runtime_test_endpoint",
                    "entry_price": str(entry_price),
                    "stop_loss": str(sl_price),
                    "tp1": str(tp1_price),
                    "tp2": str(tp2_price),
                    "notional": str(notional),
                    "min_notional": str(min_notional),
                    "min_notional_source": min_notional_source,
                    "attempt_locked": True,
                },
                event_type="control.test_signal_injection",
            )
        except Exception as exc:
            logger.warning(
                "Controlled test signal injection trace emit failed: %s",
                exc,
                exc_info=True,
            )

    return ControlledEntryResponse(
        status=intent.status.value if hasattr(intent.status, "value") else str(intent.status),
        intent_id=intent.id,
        signal_id=intent.signal_id,
        entry_price=entry_price,
        stop_loss=sl_price,
        amount=amount,
        profile=_CONTROLLED_PROFILE,
        blocked_reason=getattr(intent, "blocked_reason", None),
        attempt_locked=True,
        notional=notional,
        min_notional=min_notional,
    )
