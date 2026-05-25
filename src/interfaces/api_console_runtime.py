from __future__ import annotations

import os
import logging
from dataclasses import dataclass
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
from src.application.campaign_state_service import (
    CampaignReplayEvidence,
    CampaignRuntimeState,
)
from src.application.phase5e_rehearsal_feasibility import (
    Phase5EControlledSymbolFeasibility,
    assess_controlled_symbol_feasibility,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/runtime", tags=["Console Runtime"])

RUNTIME_CONTROL_API_ENABLED_ENV = "RUNTIME_CONTROL_API_ENABLED"
RUNTIME_TEST_SIGNAL_INJECTION_ENABLED_ENV = "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED"

_CONTROLLED_ENTRY_EXECUTED: bool = False
_CONTROLLED_CLOSE_EXECUTED: bool = False


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


class StartupTradingGuardBlockRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=512)
    updated_by: str = Field(default="owner", max_length=128)


class CampaignStateResponse(BaseModel):
    scope_key: str
    status: CampaignRuntimeState
    reason: Optional[str] = None
    updated_by: str
    updated_at_ms: int
    active_strategy_contract_id: Optional[str] = None
    active_session_id: Optional[str] = None
    source: str
    live_ready: Literal[False] = False
    access_boundary: str = (
        "Local/internal runtime control only. This endpoint is not a public "
        "internet control plane."
    )
    entry_policy: str = "Only armed campaign state allows new entries."


class CampaignTransitionRecordResponse(BaseModel):
    sequence_number: int
    previous_state: CampaignRuntimeState
    target_state: CampaignRuntimeState
    next_state: CampaignRuntimeState
    trigger: str
    reason: Optional[str] = None
    updated_by: str
    occurred_at_ms: int
    accepted: bool
    rule_reason_code: Optional[str] = None
    rejection_reason: Optional[str] = None
    active_strategy_contract_id: Optional[str] = None
    active_session_id: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class CampaignReplayEvidenceResponse(BaseModel):
    scope_key: str
    initial_state: CampaignRuntimeState
    replay_final_state: CampaignRuntimeState
    snapshot_state: Optional[CampaignRuntimeState] = None
    matches_snapshot: bool
    accepted: bool
    transition_count: int
    rejected_transition_count: int
    rejection_reason: Optional[str] = None
    records: list[CampaignTransitionRecordResponse]
    live_ready: Literal[False] = False
    access_boundary: str = (
        "Read-only local/internal runtime evidence. This endpoint does not "
        "place, cancel, close, resize, or otherwise mutate exchange orders."
    )


class CampaignStateUpdateRequest(BaseModel):
    status: CampaignRuntimeState
    reason: Optional[str] = Field(default=None, max_length=512)
    updated_by: str = Field(default="owner", max_length=128)
    active_strategy_contract_id: Optional[str] = Field(default=None, max_length=128)
    active_session_id: Optional[str] = Field(default=None, max_length=128)


def _load_api_module():
    from src.interfaces import api as api_module

    get_runtime_context = getattr(api_module, "get_runtime_context", None)
    runtime_context = get_runtime_context() if callable(get_runtime_context) else None
    return runtime_context or api_module


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


def _get_campaign_state_service(api_module):
    service = getattr(api_module, "_campaign_state_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Campaign state service not initialized")
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


def _to_campaign_state_response(state) -> CampaignStateResponse:
    return CampaignStateResponse(
        scope_key=state.scope_key,
        status=state.status,
        reason=state.reason,
        updated_by=state.updated_by,
        updated_at_ms=state.updated_at_ms,
        active_strategy_contract_id=state.active_strategy_contract_id,
        active_session_id=state.active_session_id,
        source=state.source,
    )


def _to_campaign_replay_evidence_response(
    evidence: CampaignReplayEvidence,
) -> CampaignReplayEvidenceResponse:
    return CampaignReplayEvidenceResponse(
        scope_key=evidence.scope_key,
        initial_state=evidence.initial_state,
        replay_final_state=evidence.replay_final_state,
        snapshot_state=evidence.snapshot_state,
        matches_snapshot=evidence.matches_snapshot,
        accepted=evidence.accepted,
        transition_count=evidence.transition_count,
        rejected_transition_count=evidence.rejected_transition_count,
        rejection_reason=evidence.rejection_reason,
        records=[
            CampaignTransitionRecordResponse(
                sequence_number=record.sequence_number,
                previous_state=record.previous_state,
                target_state=record.target_state,
                next_state=record.next_state,
                trigger=record.trigger.value,
                reason=record.reason,
                updated_by=record.updated_by,
                occurred_at_ms=record.occurred_at_ms,
                accepted=record.accepted,
                rule_reason_code=record.rule_reason_code,
                rejection_reason=record.rejection_reason,
                active_strategy_contract_id=record.active_strategy_contract_id,
                active_session_id=record.active_session_id,
                metadata=dict(record.metadata),
            )
            for record in evidence.records
        ],
    )


# ---------------------------------------------------------------
# 001D-1A: Controlled Synthetic Signal Injection
# ---------------------------------------------------------------

_CONTROLLED_SYMBOL = "ETH/USDT:USDT"
_CONTROLLED_AMOUNT_MAX = Decimal("0.01")
_CONTROLLED_PROFILE = "sim1_eth_runtime"
_CONTROLLED_MIN_NOTIONAL_DEFAULT = Decimal("20")
_PHASE5E_PROFILE = "phase5e_btc_eth_testnet_runtime"
_PHASE5E_ALLOWED_SYMBOLS = {"ETH/USDT:USDT", "BTC/USDT:USDT"}
_CONTROLLED_ENTRY_EXECUTED_BY_SYMBOL: dict[str, bool] = {}
_CONTROLLED_CLOSE_EXECUTED_BY_SYMBOL: dict[str, bool] = {}


@dataclass(frozen=True)
class ControlledSymbolSpec:
    symbol: str
    amount_max: Decimal
    profile: str
    min_notional_default: Decimal
    max_notional: Decimal | None = None
    amount_step: Decimal | None = None

    @property
    def lock_key(self) -> str:
        return f"{self.profile}:{self.symbol}"


_LEGACY_CONTROLLED_SPEC = ControlledSymbolSpec(
    symbol=_CONTROLLED_SYMBOL,
    amount_max=_CONTROLLED_AMOUNT_MAX,
    profile=_CONTROLLED_PROFILE,
    min_notional_default=_CONTROLLED_MIN_NOTIONAL_DEFAULT,
)

_PHASE5E_CONTROLLED_SPECS: dict[str, ControlledSymbolSpec] = {
    "eth": ControlledSymbolSpec(
        symbol="ETH/USDT:USDT",
        amount_max=Decimal("0.01"),
        profile=_PHASE5E_PROFILE,
        min_notional_default=Decimal("20"),
        max_notional=Decimal("25"),
        amount_step=Decimal("0.01"),
    ),
    "btc": ControlledSymbolSpec(
        symbol="BTC/USDT:USDT",
        amount_max=Decimal("0.002"),
        profile=_PHASE5E_PROFILE,
        min_notional_default=Decimal("100"),
        max_notional=Decimal("250"),
        amount_step=Decimal("0.001"),
    ),
}


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
    symbol: Optional[str] = None


class ControlledCloseResponse(BaseModel):
    status: str
    signal_id: Optional[str] = None
    close_order_id: Optional[str] = None
    exchange_order_id: Optional[str] = None
    amount: Decimal
    average_exec_price: Optional[Decimal] = None
    terminalized_protection_orders: int = 0
    testnet: Literal[True] = True
    profile: str = _CONTROLLED_PROFILE
    attempt_locked: bool = False
    symbol: Optional[str] = None


class Phase5EInventorySymbolState(BaseModel):
    symbol: str
    exchange_position_count: int
    exchange_normal_open_order_count: int
    exchange_conditional_open_order_count: int
    local_active_position_count: int
    local_open_order_count: int
    flat: bool


class Phase5EInventoryResponse(BaseModel):
    profile: str
    testnet: Literal[True] = True
    symbols: list[Phase5EInventorySymbolState]
    all_flat: bool


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


def _get_controlled_min_notional(
    gateway,
    spec: ControlledSymbolSpec = _LEGACY_CONTROLLED_SPEC,
) -> tuple[Decimal, str]:
    for attr_name in ("get_min_notional", "min_notional_for_symbol"):
        attr = getattr(gateway, attr_name, None)
        if callable(attr):
            try:
                value = _to_decimal(attr(spec.symbol))
            except Exception:
                value = None
            if value is not None:
                return value, attr_name

    markets = getattr(gateway, "markets", None)
    if isinstance(markets, dict):
        value = _extract_min_notional_from_market(markets.get(spec.symbol))
        if value is not None:
            return value, "gateway.markets"

    market_metadata = getattr(gateway, "market_metadata", None)
    if isinstance(market_metadata, dict):
        value = _extract_min_notional_from_market(market_metadata.get(spec.symbol))
        if value is not None:
            return value, "gateway.market_metadata"

    logger.warning(
        "Controlled signal injection using conservative default min_notional=%s for %s",
        spec.min_notional_default,
        spec.symbol,
    )
    return spec.min_notional_default, "default"


def _resolve_phase5e_spec(symbol_key: str) -> ControlledSymbolSpec:
    normalized = symbol_key.strip().lower()
    spec = _PHASE5E_CONTROLLED_SPECS.get(normalized)
    if spec is None:
        raise HTTPException(
            status_code=404,
            detail="Unsupported Phase 5E controlled symbol key; use eth or btc.",
        )
    return spec


def _require_phase5e_runtime_scope(resolved) -> None:
    if resolved.profile_name != _PHASE5E_PROFILE:
        raise HTTPException(
            status_code=403,
            detail=f"Endpoint requires RUNTIME_PROFILE={_PHASE5E_PROFILE}, got {resolved.profile_name}",
        )
    market = getattr(resolved, "market", None)
    symbols = set(getattr(market, "symbols", []) or [])
    if symbols != _PHASE5E_ALLOWED_SYMBOLS:
        raise HTTPException(
            status_code=403,
            detail=(
                "Endpoint requires Phase 5E market symbols exactly "
                f"{sorted(_PHASE5E_ALLOWED_SYMBOLS)}, got {sorted(symbols)}"
            ),
        )


async def _require_no_phase5e_active_positions(api_module, spec: ControlledSymbolSpec) -> None:
    position_repo = getattr(api_module, "_position_repo", None)
    if position_repo is None or not hasattr(position_repo, "list_active"):
        raise HTTPException(status_code=503, detail="Position repository not initialized")
    try:
        active_positions = await position_repo.list_active(symbol=None, limit=10)
    except Exception as exc:
        logger.error("Failed to load active positions for Phase 5E entry: %s", exc, exc_info=True)
        raise HTTPException(status_code=503, detail="Failed to load active positions") from exc
    if active_positions:
        symbols = sorted({str(getattr(position, "symbol", "unknown")) for position in active_positions})
        raise HTTPException(
            status_code=409,
            detail=(
                "BLOCKED: Phase 5E allows at most one sequential active symbol; "
                f"active positions present before {spec.symbol} entry: {symbols}"
            ),
        )


async def _build_phase5e_feasibility(
    *,
    api_module,
    spec: ControlledSymbolSpec,
) -> Phase5EControlledSymbolFeasibility:
    gateway = _get_gateway(api_module)
    try:
        last_price = await gateway.fetch_ticker_price(spec.symbol)
    except Exception as exc:
        logger.error("Failed to fetch market price for Phase 5E feasibility: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail="Failed to fetch market price") from exc

    min_notional, min_notional_source = _get_controlled_min_notional(gateway, spec)
    return assess_controlled_symbol_feasibility(
        symbol=spec.symbol,
        amount=spec.amount_max,
        price=Decimal(str(last_price)),
        min_notional=min_notional,
        min_notional_source=min_notional_source,
        max_notional=spec.max_notional,
        amount_step=spec.amount_step,
    )


def _position_size_is_nonzero(position) -> bool:
    for attr_name in ("size", "contracts", "current_qty", "quantity"):
        value = getattr(position, attr_name, None)
        if value is None:
            continue
        try:
            return Decimal(str(value)) != Decimal("0")
        except Exception:
            return bool(value)
    return False


async def _fetch_phase5e_exchange_open_orders(gateway, symbol: str, params: Optional[dict] = None) -> list:
    try:
        if params is None:
            return list(await gateway.fetch_open_orders(symbol))
        return list(await gateway.fetch_open_orders(symbol, params=params))
    except TypeError:
        if params is None:
            return list(await gateway.fetch_open_orders(symbol=symbol))
        return list(await gateway.fetch_open_orders(symbol=symbol, params=params))


async def _build_phase5e_inventory(api_module) -> Phase5EInventoryResponse:
    gateway = _get_gateway(api_module)
    position_repo = getattr(api_module, "_position_repo", None)
    order_repo = getattr(api_module, "_order_repo", None)
    if position_repo is None or not hasattr(position_repo, "list_active"):
        raise HTTPException(status_code=503, detail="Position repository not initialized")
    if order_repo is None or not hasattr(order_repo, "get_open_orders"):
        raise HTTPException(status_code=503, detail="Order repository not initialized")

    states: list[Phase5EInventorySymbolState] = []
    for symbol in sorted(_PHASE5E_ALLOWED_SYMBOLS):
        try:
            exchange_positions = await gateway.fetch_positions(symbol=symbol)
            exchange_normal_open_orders = await _fetch_phase5e_exchange_open_orders(gateway, symbol)
            exchange_conditional_open_orders = await _fetch_phase5e_exchange_open_orders(
                gateway,
                symbol,
                params={"stop": True},
            )
            local_active_positions = await position_repo.list_active(symbol=symbol, limit=20)
            local_open_orders = await order_repo.get_open_orders(symbol)
        except Exception as exc:
            logger.error("Phase 5E inventory read failed for %s: %s", symbol, exc, exc_info=True)
            raise HTTPException(status_code=502, detail=f"Phase 5E inventory read failed for {symbol}") from exc

        exchange_position_count = sum(1 for position in exchange_positions if _position_size_is_nonzero(position))
        state = Phase5EInventorySymbolState(
            symbol=symbol,
            exchange_position_count=exchange_position_count,
            exchange_normal_open_order_count=len(exchange_normal_open_orders),
            exchange_conditional_open_order_count=len(exchange_conditional_open_orders),
            local_active_position_count=len(local_active_positions),
            local_open_order_count=len(local_open_orders),
            flat=(
                exchange_position_count == 0
                and len(exchange_normal_open_orders) == 0
                and len(exchange_conditional_open_orders) == 0
                and len(local_active_positions) == 0
                and len(local_open_orders) == 0
            ),
        )
        states.append(state)

    return Phase5EInventoryResponse(
        profile=_PHASE5E_PROFILE,
        symbols=states,
        all_flat=all(state.flat for state in states),
    )


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
        logger.error("Global Kill Switch persistence failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="Global Kill Switch persistence failed",
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


@router.post("/control/startup-trading-guard/block", response_model=StartupTradingGuardResponse)
async def block_startup_trading_guard(
    request: Request,
    body: StartupTradingGuardBlockRequest,
) -> StartupTradingGuardResponse:
    """Block startup trading guard after runtime shutdown or operator reset."""
    _require_internal_runtime_control(request)
    _require_runtime_control_api_enabled()
    api_module = _load_api_module()
    service = _get_startup_trading_guard_service(api_module)
    state = service.block(
        reason=body.reason,
        updated_by=body.updated_by,
        source="manual_block",
    )
    return _to_startup_trading_guard_response(state)


@router.get("/control/campaign-state", response_model=CampaignStateResponse)
async def get_campaign_state(request: Request) -> CampaignStateResponse:
    """Read durable runtime campaign state. Local/internal control surface only."""
    _require_internal_runtime_control(request)
    api_module = _load_api_module()
    service = _get_campaign_state_service(api_module)
    return _to_campaign_state_response(service.get_state())


@router.get(
    "/control/campaign-state/replay-evidence",
    response_model=CampaignReplayEvidenceResponse,
)
async def get_campaign_state_replay_evidence(
    request: Request,
) -> CampaignReplayEvidenceResponse:
    """Read campaign transition ledger replay evidence. No exchange mutation."""
    _require_internal_runtime_control(request)
    api_module = _load_api_module()
    service = _get_campaign_state_service(api_module)
    build_replay_evidence = getattr(service, "build_replay_evidence", None)
    if not callable(build_replay_evidence):
        raise HTTPException(
            status_code=503,
            detail="Campaign replay evidence is unavailable",
        )
    try:
        evidence = await build_replay_evidence()
    except Exception as exc:
        logger.error("Campaign replay evidence failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="Campaign replay evidence failed",
        ) from exc
    return _to_campaign_replay_evidence_response(evidence)


@router.post("/control/campaign-state", response_model=CampaignStateResponse)
async def update_campaign_state(
    request: Request,
    body: CampaignStateUpdateRequest,
) -> CampaignStateResponse:
    """Update durable runtime campaign state. Local/internal control surface only."""
    _require_internal_runtime_control(request)
    _require_runtime_control_api_enabled()
    api_module = _load_api_module()
    service = _get_campaign_state_service(api_module)
    try:
        state = await service.set_state(
            status=body.status.value,
            reason=body.reason,
            updated_by=body.updated_by,
            active_strategy_contract_id=body.active_strategy_contract_id,
            active_session_id=body.active_session_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Campaign state persistence failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="Campaign state persistence failed",
        ) from exc
    return _to_campaign_state_response(state)


# ============================================================
# Second Batch: Positions / Signals / Attempts / Orders / Intents
# ============================================================


@router.get("/positions", response_model=ConsolePositionsResponse)
async def get_runtime_positions(
    symbol: Optional[str] = Query(None),
) -> ConsolePositionsResponse:
    """Get current positions from account snapshot."""
    api_module = _load_api_module()
    account_snapshot = _get_account_snapshot(api_module)
    read_model = RuntimePositionsReadModel()
    return await read_model.build(
        account_snapshot=account_snapshot,
        position_repo=getattr(api_module, "_position_repo", None),
        symbol=symbol,
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
    symbol: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
) -> ConsoleExecutionIntentsResponse:
    """Get execution intents from intent repository."""
    api_module = _load_api_module()
    read_model = RuntimeExecutionIntentsReadModel()
    return await read_model.build(
        intent_repo=getattr(api_module, "_execution_intent_repo", None),
        symbol=symbol,
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
        logger.error("Failed to fetch market price for controlled entry: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=502,
            detail="Failed to fetch market price",
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
        logger.error("Controlled entry execution failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Execution failed",
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


@router.post(
    "/test/smoke/execute-controlled-close",
    response_model=ControlledCloseResponse,
)
async def execute_controlled_close(request: Request) -> ControlledCloseResponse:
    """Runtime-managed reduce-only close for 001D-4 testnet smoke."""
    global _CONTROLLED_CLOSE_EXECUTED

    if not _test_signal_injection_enabled():
        raise HTTPException(
            status_code=403,
            detail=(
                "Controlled signal injection disabled. "
                f"Set {RUNTIME_TEST_SIGNAL_INJECTION_ENABLED_ENV}=true."
            ),
        )
    if not _runtime_control_api_enabled():
        raise HTTPException(
            status_code=403,
            detail=(
                "Runtime control API disabled. "
                f"Set {RUNTIME_CONTROL_API_ENABLED_ENV}=true."
            ),
        )

    _require_internal_runtime_control(request)
    await _reject_controlled_entry_body(request)

    api_module = _load_api_module()
    config_provider = getattr(api_module, "_runtime_config_provider", None)
    resolved = config_provider.resolved_config if config_provider else None
    if resolved is None:
        raise HTTPException(status_code=503, detail="Runtime config not resolved")
    if not resolved.environment.exchange_testnet:
        raise HTTPException(status_code=403, detail="Endpoint requires EXCHANGE_TESTNET=true")
    if resolved.profile_name != _CONTROLLED_PROFILE:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Endpoint requires RUNTIME_PROFILE={_CONTROLLED_PROFILE}, "
                f"got {resolved.profile_name}"
            ),
        )
    if _CONTROLLED_CLOSE_EXECUTED:
        raise HTTPException(
            status_code=409,
            detail="Controlled close already executed in this runtime session",
        )

    position_repo = getattr(api_module, "_position_repo", None)
    if position_repo is None or not hasattr(position_repo, "list_active"):
        raise HTTPException(status_code=503, detail="Position repository not initialized")
    try:
        active_positions = await position_repo.list_active(symbol=_CONTROLLED_SYMBOL, limit=10)
    except Exception as exc:
        logger.error("Failed to load active positions for controlled close: %s", exc, exc_info=True)
        raise HTTPException(status_code=503, detail="Failed to load active positions") from exc

    if len(active_positions) != 1:
        raise HTTPException(
            status_code=409,
            detail=(
                "Controlled close requires exactly one active local position "
                f"for {_CONTROLLED_SYMBOL}; found {len(active_positions)}"
            ),
        )
    position = active_positions[0]
    amount = Decimal(str(getattr(position, "current_qty", "0")))
    if amount <= Decimal("0") or amount > _CONTROLLED_AMOUNT_MAX:
        raise HTTPException(
            status_code=409,
            detail=f"Controlled close amount out of bounds: {amount}",
        )

    orchestrator = _get_orchestrator(api_module)
    _CONTROLLED_CLOSE_EXECUTED = True
    try:
        result = await orchestrator.execute_controlled_close(
            position=position,
            reason="controlled_test_runtime_close",
            max_amount=_CONTROLLED_AMOUNT_MAX,
        )
    except Exception as exc:
        logger.error("Controlled close execution failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Controlled close failed") from exc

    close_order = result["close_order"]
    terminalized = result.get("terminalized_protection_orders") or []

    trace_svc = _get_trace_service(api_module)
    if trace_svc is not None:
        try:
            trace_svc.emit_risk_decision(
                lifecycle_id=close_order.id,
                decision="executed",
                reason="controlled_test_runtime_close",
                metadata={
                    "symbol": _CONTROLLED_SYMBOL,
                    "amount": str(amount),
                    "profile": _CONTROLLED_PROFILE,
                    "testnet": True,
                    "source": "runtime_test_endpoint",
                    "signal_id": close_order.signal_id,
                    "exchange_order_id": close_order.exchange_order_id,
                    "average_exec_price": str(close_order.average_exec_price)
                    if close_order.average_exec_price is not None
                    else None,
                    "terminalized_protection_orders": len(terminalized),
                    "attempt_locked": True,
                },
                event_type="control.test_controlled_close",
            )
        except Exception as exc:
            logger.warning("Controlled close trace emit failed: %s", exc, exc_info=True)

    return ControlledCloseResponse(
        status=close_order.status.value if hasattr(close_order.status, "value") else str(close_order.status),
        signal_id=close_order.signal_id,
        close_order_id=close_order.id,
        exchange_order_id=close_order.exchange_order_id,
        amount=amount,
        average_exec_price=close_order.average_exec_price,
        terminalized_protection_orders=len(terminalized),
        profile=_CONTROLLED_PROFILE,
        attempt_locked=True,
    )


@router.post(
    "/test/phase5e/{symbol_key}/execute-controlled-entry",
    response_model=ControlledEntryResponse,
)
async def execute_phase5e_controlled_entry(
    symbol_key: str,
    request: Request,
) -> ControlledEntryResponse:
    """Phase 5E server-controlled BTC/ETH testnet entry.

    The symbol is selected only from the fixed path keys `eth` or `btc`.
    Amount, side, SL/TP, leverage, and profile remain server-controlled.
    """
    from src.domain.models import Direction, OrderStrategy, SignalResult

    spec = _resolve_phase5e_spec(symbol_key)
    if not _test_signal_injection_enabled():
        raise HTTPException(
            status_code=403,
            detail=(
                "Controlled signal injection disabled. "
                f"Set {RUNTIME_TEST_SIGNAL_INJECTION_ENABLED_ENV}=true."
            ),
        )
    if not _runtime_control_api_enabled():
        raise HTTPException(
            status_code=403,
            detail=(
                "Runtime control API disabled. "
                f"Set {RUNTIME_CONTROL_API_ENABLED_ENV}=true."
            ),
        )

    _require_internal_runtime_control(request)
    await _reject_controlled_entry_body(request)

    api_module = _load_api_module()
    config_provider = getattr(api_module, "_runtime_config_provider", None)
    resolved = config_provider.resolved_config if config_provider else None
    if resolved is None:
        raise HTTPException(status_code=503, detail="Runtime config not resolved")
    if not resolved.environment.exchange_testnet:
        raise HTTPException(status_code=403, detail="Endpoint requires EXCHANGE_TESTNET=true")
    _require_phase5e_runtime_scope(resolved)

    if _CONTROLLED_ENTRY_EXECUTED_BY_SYMBOL.get(spec.lock_key):
        raise HTTPException(
            status_code=409,
            detail=f"Controlled entry already executed for {spec.symbol} in this runtime session",
        )

    orchestrator = _get_orchestrator(api_module)

    guard_svc = getattr(api_module, "_startup_trading_guard_service", None)
    if guard_svc is None or not guard_svc.is_armed():
        raise HTTPException(status_code=409, detail="BLOCKED: startup guard not armed")

    gks_svc = getattr(api_module, "_global_kill_switch_service", None)
    if gks_svc is None:
        raise HTTPException(status_code=503, detail="BLOCKED: GKS_SERVICE_UNAVAILABLE")
    if gks_svc.is_active():
        raise HTTPException(status_code=409, detail="BLOCKED: global kill switch active")

    await _require_no_phase5e_active_positions(api_module, spec)

    blocks = orchestrator.list_protection_health_blocks()
    if spec.symbol in blocks:
        raise HTTPException(
            status_code=409,
            detail=f"BLOCKED: protection-health block active for {spec.symbol}",
        )

    if orchestrator.is_symbol_blocked(spec.symbol):
        raise HTTPException(
            status_code=409,
            detail=f"BLOCKED: circuit breaker active for {spec.symbol}",
        )

    feasibility = await _build_phase5e_feasibility(api_module=api_module, spec=spec)
    entry_price = feasibility.price
    sl_price = entry_price * Decimal("0.99")
    tp1_price = entry_price * Decimal("1.01")
    tp2_price = entry_price * Decimal("1.035")
    amount = feasibility.amount
    if feasibility.reason == "MIN_NOTIONAL_EXCEEDS_CAP":
        raise HTTPException(
            status_code=409,
            detail=(
                "BLOCKED: Phase 5E min_notional exceeds symbol cap "
                f"({feasibility.min_notional} > {feasibility.max_notional})"
            ),
        )
    if feasibility.reason == "NOTIONAL_BELOW_MIN_NOTIONAL":
        raise HTTPException(
            status_code=409,
            detail=(
                "BLOCKED: controlled entry notional below min_notional "
                f"({feasibility.notional} < {feasibility.min_notional}, "
                f"source={feasibility.min_notional_source})"
            ),
        )
    if feasibility.reason == "NOTIONAL_ABOVE_CAP":
        raise HTTPException(
            status_code=409,
            detail=(
                "BLOCKED: controlled entry notional above Phase 5E cap "
                f"({feasibility.notional} > {feasibility.max_notional})"
            ),
        )

    signal = SignalResult(
        symbol=spec.symbol,
        timeframe="1h",
        direction=Direction.LONG,
        entry_price=entry_price,
        suggested_stop_loss=sl_price,
        suggested_position_size=amount,
        current_leverage=1,
        tags=[{"key": "source", "value": "runtime_test_endpoint_phase5e"}],
        risk_reward_info="phase5e_controlled_test_smoke:1h:LONG",
        status="PENDING",
        strategy_name="phase5e_controlled_test_smoke",
        score=1.0,
        take_profit_levels=[
            {"price": str(tp1_price), "ratio": "0.5"},
            {"price": str(tp2_price), "ratio": "0.5"},
        ],
    )

    strategy = OrderStrategy(
        id=f"strat_phase5e_controlled_{symbol_key.lower()}",
        name=f"phase5e_controlled_test_smoke/{spec.profile}/{spec.symbol}",
        tp_levels=2,
        tp_ratios=[Decimal("0.5"), Decimal("0.5")],
        tp_targets=[Decimal("1.0"), Decimal("3.5")],
        initial_stop_loss_rr=Decimal("-1.0"),
        trailing_stop_enabled=False,
        oco_enabled=True,
    )

    _CONTROLLED_ENTRY_EXECUTED_BY_SYMBOL[spec.lock_key] = True
    try:
        intent = await orchestrator.execute_signal(signal, strategy)
    except Exception as exc:
        logger.error("Phase 5E controlled entry execution failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Execution failed") from exc

    trace_svc = _get_trace_service(api_module)
    if trace_svc is not None:
        try:
            trace_svc.emit_risk_decision(
                lifecycle_id=intent.id,
                decision="executed",
                reason="phase5e_controlled_test_signal_injection",
                metadata={
                    "symbol": spec.symbol,
                    "direction": "LONG",
                    "amount": str(amount),
                    "profile": spec.profile,
                    "testnet": True,
                    "source": "runtime_test_endpoint_phase5e",
                    "entry_price": str(entry_price),
                    "stop_loss": str(sl_price),
                    "tp1": str(tp1_price),
                    "tp2": str(tp2_price),
                    "notional": str(feasibility.notional),
                    "min_notional": str(feasibility.min_notional),
                    "min_notional_source": feasibility.min_notional_source,
                    "max_notional": str(spec.max_notional) if spec.max_notional is not None else None,
                    "max_order_submissions_per_symbol": 5,
                    "attempt_locked": True,
                },
                event_type="control.phase5e_test_signal_injection",
            )
        except Exception as exc:
            logger.warning("Phase 5E controlled entry trace emit failed: %s", exc, exc_info=True)

    return ControlledEntryResponse(
        status=intent.status.value if hasattr(intent.status, "value") else str(intent.status),
        intent_id=intent.id,
        signal_id=intent.signal_id,
        entry_price=entry_price,
        stop_loss=sl_price,
        amount=amount,
        profile=spec.profile,
        blocked_reason=getattr(intent, "blocked_reason", None),
        attempt_locked=True,
        notional=feasibility.notional,
        min_notional=feasibility.min_notional,
        symbol=spec.symbol,
    )


@router.get(
    "/test/phase5e/{symbol_key}/feasibility",
    response_model=Phase5EControlledSymbolFeasibility,
)
async def get_phase5e_symbol_feasibility(
    symbol_key: str,
    request: Request,
) -> Phase5EControlledSymbolFeasibility:
    """Read-only Phase 5E fixed cap/min-notional feasibility preflight."""
    spec = _resolve_phase5e_spec(symbol_key)
    _require_internal_runtime_control(request)
    api_module = _load_api_module()
    config_provider = getattr(api_module, "_runtime_config_provider", None)
    resolved = config_provider.resolved_config if config_provider else None
    if resolved is None:
        raise HTTPException(status_code=503, detail="Runtime config not resolved")
    if not resolved.environment.exchange_testnet:
        raise HTTPException(status_code=403, detail="Endpoint requires EXCHANGE_TESTNET=true")
    _require_phase5e_runtime_scope(resolved)
    return await _build_phase5e_feasibility(api_module=api_module, spec=spec)


@router.get(
    "/test/phase5e/inventory",
    response_model=Phase5EInventoryResponse,
)
async def get_phase5e_inventory(
    request: Request,
) -> Phase5EInventoryResponse:
    """Read-only Phase 5E BTC/ETH exchange+PG flatness inventory."""
    _require_internal_runtime_control(request)
    api_module = _load_api_module()
    config_provider = getattr(api_module, "_runtime_config_provider", None)
    resolved = config_provider.resolved_config if config_provider else None
    if resolved is None:
        raise HTTPException(status_code=503, detail="Runtime config not resolved")
    if not resolved.environment.exchange_testnet:
        raise HTTPException(status_code=403, detail="Endpoint requires EXCHANGE_TESTNET=true")
    _require_phase5e_runtime_scope(resolved)
    return await _build_phase5e_inventory(api_module)


@router.post(
    "/test/phase5e/{symbol_key}/execute-controlled-close",
    response_model=ControlledCloseResponse,
)
async def execute_phase5e_controlled_close(
    symbol_key: str,
    request: Request,
) -> ControlledCloseResponse:
    """Phase 5E server-controlled reduce-only close for one fixed symbol."""
    spec = _resolve_phase5e_spec(symbol_key)
    if not _test_signal_injection_enabled():
        raise HTTPException(
            status_code=403,
            detail=(
                "Controlled signal injection disabled. "
                f"Set {RUNTIME_TEST_SIGNAL_INJECTION_ENABLED_ENV}=true."
            ),
        )
    if not _runtime_control_api_enabled():
        raise HTTPException(
            status_code=403,
            detail=(
                "Runtime control API disabled. "
                f"Set {RUNTIME_CONTROL_API_ENABLED_ENV}=true."
            ),
        )

    _require_internal_runtime_control(request)
    await _reject_controlled_entry_body(request)

    api_module = _load_api_module()
    config_provider = getattr(api_module, "_runtime_config_provider", None)
    resolved = config_provider.resolved_config if config_provider else None
    if resolved is None:
        raise HTTPException(status_code=503, detail="Runtime config not resolved")
    if not resolved.environment.exchange_testnet:
        raise HTTPException(status_code=403, detail="Endpoint requires EXCHANGE_TESTNET=true")
    _require_phase5e_runtime_scope(resolved)

    if _CONTROLLED_CLOSE_EXECUTED_BY_SYMBOL.get(spec.lock_key):
        raise HTTPException(
            status_code=409,
            detail=f"Controlled close already executed for {spec.symbol} in this runtime session",
        )

    position_repo = getattr(api_module, "_position_repo", None)
    if position_repo is None or not hasattr(position_repo, "list_active"):
        raise HTTPException(status_code=503, detail="Position repository not initialized")
    try:
        active_positions = await position_repo.list_active(symbol=spec.symbol, limit=10)
    except Exception as exc:
        logger.error("Failed to load active positions for Phase 5E close: %s", exc, exc_info=True)
        raise HTTPException(status_code=503, detail="Failed to load active positions") from exc

    if len(active_positions) != 1:
        raise HTTPException(
            status_code=409,
            detail=(
                "Controlled close requires exactly one active local position "
                f"for {spec.symbol}; found {len(active_positions)}"
            ),
        )
    position = active_positions[0]
    amount = Decimal(str(getattr(position, "current_qty", "0")))
    if amount <= Decimal("0") or amount > spec.amount_max:
        raise HTTPException(status_code=409, detail=f"Controlled close amount out of bounds: {amount}")

    orchestrator = _get_orchestrator(api_module)
    _CONTROLLED_CLOSE_EXECUTED_BY_SYMBOL[spec.lock_key] = True
    try:
        result = await orchestrator.execute_controlled_close(
            position=position,
            reason="phase5e_controlled_test_runtime_close",
            max_amount=spec.amount_max,
        )
    except Exception as exc:
        logger.error("Phase 5E controlled close execution failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Controlled close failed") from exc

    close_order = result["close_order"]
    terminalized = result.get("terminalized_protection_orders") or []

    trace_svc = _get_trace_service(api_module)
    if trace_svc is not None:
        try:
            trace_svc.emit_risk_decision(
                lifecycle_id=close_order.id,
                decision="executed",
                reason="phase5e_controlled_test_runtime_close",
                metadata={
                    "symbol": spec.symbol,
                    "amount": str(amount),
                    "profile": spec.profile,
                    "testnet": True,
                    "source": "runtime_test_endpoint_phase5e",
                    "signal_id": close_order.signal_id,
                    "exchange_order_id": close_order.exchange_order_id,
                    "average_exec_price": str(close_order.average_exec_price)
                    if close_order.average_exec_price is not None
                    else None,
                    "terminalized_protection_orders": len(terminalized),
                    "max_order_submissions_per_symbol": 5,
                    "attempt_locked": True,
                },
                event_type="control.phase5e_test_controlled_close",
            )
        except Exception as exc:
            logger.warning("Phase 5E controlled close trace emit failed: %s", exc, exc_info=True)

    return ControlledCloseResponse(
        status=close_order.status.value if hasattr(close_order.status, "value") else str(close_order.status),
        signal_id=close_order.signal_id,
        close_order_id=close_order.id,
        exchange_order_id=close_order.exchange_order_id,
        amount=amount,
        average_exec_price=close_order.average_exec_price,
        terminalized_protection_orders=len(terminalized),
        profile=spec.profile,
        attempt_locked=True,
        symbol=spec.symbol,
    )
