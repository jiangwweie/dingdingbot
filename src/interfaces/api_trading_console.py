"""Trading Console Owner action-entry and non-mutating product API namespace."""

from __future__ import annotations

import asyncio
import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.application.readmodels.trading_console import (
    TradingConsoleDependencies,
    TradingConsoleReadModelResponse,
    TradingConsoleReadModelService,
)
from src.domain.signal_evaluation import (
    OrderCandidate,
    OrderCandidateStatus,
    SignalEvaluation,
    SignalEvaluationStatus,
)
from src.domain.strategy_runtime import StrategyRuntimeInstance, StrategyRuntimeInstanceStatus
from src.interfaces.operator_auth import require_operator_session


router = APIRouter(
    prefix="/api/trading-console",
    tags=["Trading Console"],
    dependencies=[Depends(require_operator_session)],
)


class _TradingConsoleLiveReadOnlyGateway:
    """Lazy, per-event-loop read-only exchange adapter for Trading Console GETs."""

    def __init__(self) -> None:
        self._gateway: Optional[Any] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def _gateway_for_current_loop(self) -> Any:
        loop = asyncio.get_running_loop()
        if self._gateway is not None and self._loop is loop and not loop.is_closed():
            return self._gateway
        if self._gateway is not None:
            await self.close()

        if not _live_read_only_exchange_env_safe():
            raise RuntimeError("trading_console_live_read_only_env_not_safe")

        from src.infrastructure.exchange_gateway import ExchangeGateway

        gateway = ExchangeGateway(
            os.environ.get("EXCHANGE_NAME", "binance"),
            os.environ["EXCHANGE_API_KEY"],
            os.environ["EXCHANGE_API_SECRET"],
            testnet=False,
        )
        await gateway.initialize()
        await gateway.check_api_key_permissions()
        self._gateway = gateway
        self._loop = loop
        return gateway

    def get_account_snapshot(self) -> Optional[Any]:
        if self._gateway is None:
            return None
        return self._gateway.get_account_snapshot()

    async def fetch_account_balance(self) -> Optional[Any]:
        gateway = await self._gateway_for_current_loop()
        return await gateway.fetch_account_balance()

    async def fetch_positions(self, symbol: Optional[str] = None) -> list[Any]:
        gateway = await self._gateway_for_current_loop()
        return await gateway.fetch_positions(symbol)

    async def fetch_open_orders(self, symbol: str, params: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
        gateway = await self._gateway_for_current_loop()
        return await gateway.fetch_open_orders(symbol, params=params)

    async def close(self) -> None:
        gateway = self._gateway
        self._gateway = None
        self._loop = None
        if gateway is not None:
            await gateway.close()


def _live_read_only_exchange_env_safe() -> bool:
    permission_max = os.environ.get("BRC_EXECUTION_PERMISSION_MAX", "").strip().lower()
    return (
        os.environ.get("TRADING_ENV") == "live"
        and os.environ.get("EXCHANGE_TESTNET", "").lower() == "false"
        and permission_max in {"read_only", "order_allowed"}
        and os.environ.get("RUNTIME_CONTROL_API_ENABLED", "").lower() == "false"
        and os.environ.get("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "").lower() == "false"
        and bool(os.environ.get("EXCHANGE_API_KEY"))
        and bool(os.environ.get("EXCHANGE_API_SECRET"))
    )


class StrategyRuntimeBoundaryView(BaseModel):
    max_attempts: int
    attempts_used: int
    attempts_remaining: int
    max_active_positions: int
    max_notional_per_attempt: str | None = None
    total_budget: str | None = None
    budget_remaining: str | None = None
    allowed_symbols: list[str] = Field(default_factory=list)
    allowed_sides: list[str] = Field(default_factory=list)
    max_leverage: str | None = None
    requires_protection: bool
    requires_review: bool


class StrategyRuntimeInspectionView(BaseModel):
    runtime_instance_id: str
    trial_binding_id: str
    admission_decision_id: str
    strategy_family_id: str
    strategy_family_version_id: str
    signal_evaluation_id: str | None = None
    order_candidate_id: str | None = None
    owner_risk_acceptance_id: str | None = None
    carrier_id: str | None = None
    symbol: str
    side: str
    status: StrategyRuntimeInstanceStatus
    boundary: StrategyRuntimeBoundaryView
    policy_snapshot: dict[str, Any] = Field(default_factory=dict)
    review_requirement: str
    execution_enabled: bool
    execution_mode: str
    shadow_mode: bool
    created_at_ms: int
    updated_at_ms: int
    activated_at_ms: int | None = None
    expires_at_ms: int | None = None
    revoked_at_ms: int | None = None
    closed_at_ms: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SignalEvaluationInspectionView(BaseModel):
    signal_evaluation_id: str
    runtime_instance_id: str | None = None
    trial_binding_id: str | None = None
    strategy_family_id: str | None = None
    strategy_family_version_id: str | None = None
    source_signal_id: str | None = None
    symbol: str
    side: str
    status: SignalEvaluationStatus
    decision: str
    reason_codes: list[str] = Field(default_factory=list)
    rationale: str
    evidence_snapshot: dict[str, Any] = Field(default_factory=dict)
    policy_snapshot: dict[str, Any] = Field(default_factory=dict)
    evaluated_at_ms: int
    expires_at_ms: int | None = None
    shadow_mode: bool
    execution_enabled: bool
    not_order: bool
    not_execution_intent: bool
    created_at_ms: int
    updated_at_ms: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class OrderCandidateInspectionView(BaseModel):
    order_candidate_id: str
    signal_evaluation_id: str
    runtime_instance_id: str | None = None
    trial_binding_id: str | None = None
    strategy_family_id: str | None = None
    strategy_family_version_id: str | None = None
    symbol: str
    side: str
    status: OrderCandidateStatus
    candidate_order_type: str
    proposed_quantity: str | None = None
    intended_notional: str | None = None
    entry_price_reference: str | None = None
    risk_preview: dict[str, Any] = Field(default_factory=dict)
    protection_preview: dict[str, Any] = Field(default_factory=dict)
    rationale: str
    evidence_refs: list[str] = Field(default_factory=list)
    shadow_mode: bool
    execution_enabled: bool
    candidate_executable: bool
    not_order: bool
    not_execution_intent: bool
    created_at_ms: int
    updated_at_ms: int
    expires_at_ms: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.get("/dashboard-state", response_model=TradingConsoleReadModelResponse)
async def dashboard_state(
    symbol: Optional[str] = Query(default=None),
    include_exchange: bool = Query(default=False),
) -> TradingConsoleReadModelResponse:
    return await _service(include_exchange=include_exchange).dashboard_state(
        symbol=symbol,
        include_exchange=include_exchange,
    )


@router.get(
    "/strategy-runtimes",
    response_model=list[StrategyRuntimeInspectionView],
)
async def list_strategy_runtimes(
    status: Optional[StrategyRuntimeInstanceStatus] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[StrategyRuntimeInspectionView]:
    service = await _strategy_runtime_service()
    runtimes = await service.list_runtimes(status=status, limit=limit)
    return [_runtime_view(runtime) for runtime in runtimes]


@router.get(
    "/strategy-runtimes/{runtime_instance_id}",
    response_model=StrategyRuntimeInspectionView,
)
async def get_strategy_runtime(
    runtime_instance_id: str,
) -> StrategyRuntimeInspectionView:
    service = await _strategy_runtime_service()
    try:
        return _runtime_view(await service.get_runtime(runtime_instance_id))
    except Exception as exc:
        message = str(exc)
        if "not found" in message:
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.get(
    "/signal-evaluations",
    response_model=list[SignalEvaluationInspectionView],
)
async def list_signal_evaluations(
    runtime_instance_id: Optional[str] = Query(default=None),
    trial_binding_id: Optional[str] = Query(default=None),
    strategy_family_id: Optional[str] = Query(default=None),
    strategy_family_version_id: Optional[str] = Query(default=None),
    status: Optional[SignalEvaluationStatus] = Query(default=None),
    symbol: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[SignalEvaluationInspectionView]:
    service = await _signal_evaluation_shadow_service()
    evaluations = await service.list_signal_evaluations(
        runtime_instance_id=runtime_instance_id,
        trial_binding_id=trial_binding_id,
        strategy_family_id=strategy_family_id,
        strategy_family_version_id=strategy_family_version_id,
        status=status,
        symbol=symbol,
        limit=limit,
    )
    return [_signal_evaluation_view(item) for item in evaluations]


@router.get(
    "/signal-evaluations/{signal_evaluation_id}",
    response_model=SignalEvaluationInspectionView,
)
async def get_signal_evaluation(
    signal_evaluation_id: str,
) -> SignalEvaluationInspectionView:
    service = await _signal_evaluation_shadow_service()
    try:
        return _signal_evaluation_view(await service.get_signal_evaluation(signal_evaluation_id))
    except Exception as exc:
        message = str(exc)
        if "not found" in message:
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.get(
    "/order-candidates",
    response_model=list[OrderCandidateInspectionView],
)
async def list_order_candidates(
    runtime_instance_id: Optional[str] = Query(default=None),
    trial_binding_id: Optional[str] = Query(default=None),
    strategy_family_id: Optional[str] = Query(default=None),
    strategy_family_version_id: Optional[str] = Query(default=None),
    signal_evaluation_id: Optional[str] = Query(default=None),
    status: Optional[OrderCandidateStatus] = Query(default=None),
    symbol: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[OrderCandidateInspectionView]:
    service = await _signal_evaluation_shadow_service()
    candidates = await service.list_order_candidates(
        runtime_instance_id=runtime_instance_id,
        trial_binding_id=trial_binding_id,
        strategy_family_id=strategy_family_id,
        strategy_family_version_id=strategy_family_version_id,
        signal_evaluation_id=signal_evaluation_id,
        status=status,
        symbol=symbol,
        limit=limit,
    )
    return [_order_candidate_view(item) for item in candidates]


@router.get(
    "/order-candidates/{order_candidate_id}",
    response_model=OrderCandidateInspectionView,
)
async def get_order_candidate(
    order_candidate_id: str,
) -> OrderCandidateInspectionView:
    service = await _signal_evaluation_shadow_service()
    try:
        return _order_candidate_view(await service.get_order_candidate(order_candidate_id))
    except Exception as exc:
        message = str(exc)
        if "not found" in message:
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.get("/operations-cockpit", response_model=TradingConsoleReadModelResponse)
async def operations_cockpit(
    symbol: Optional[str] = Query(default=None),
    include_exchange: bool = Query(default=True),
) -> TradingConsoleReadModelResponse:
    return await _service(include_exchange=include_exchange).operations_cockpit(
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
    runtime_instance_id: Optional[str] = Query(default=None),
    trial_binding_id: Optional[str] = Query(default=None),
    strategy_family_id: Optional[str] = Query(default=None),
    strategy_family_version_id: Optional[str] = Query(default=None),
    signal_evaluation_id: Optional[str] = Query(default=None),
    order_candidate_id: Optional[str] = Query(default=None),
    intent_id: Optional[str] = Query(default=None),
    order_id: Optional[str] = Query(default=None),
    exchange_order_id: Optional[str] = Query(default=None),
    symbol: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> TradingConsoleReadModelResponse:
    return await _service(include_exchange=False).audit_chain(
        authorization_id=authorization_id,
        runtime_instance_id=runtime_instance_id,
        trial_binding_id=trial_binding_id,
        strategy_family_id=strategy_family_id,
        strategy_family_version_id=strategy_family_version_id,
        signal_evaluation_id=signal_evaluation_id,
        order_candidate_id=order_candidate_id,
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


@router.get("/strategy-family-admission-state", response_model=TradingConsoleReadModelResponse)
async def strategy_family_admission_state(
    family: Optional[str] = Query(default=None),
    strategy_family_id: Optional[str] = Query(default=None),
    carrier_id: Optional[str] = Query(default=None),
    symbol: Optional[str] = Query(default=None),
    side: Optional[str] = Query(default=None),
    quantity: Optional[str] = Query(default=None),
    target_notional_usdt: Optional[str] = Query(default=None),
    current_price: Optional[str] = Query(default=None),
    min_notional: Optional[str] = Query(default=None),
    min_qty: Optional[str] = Query(default=None),
    qty_step: Optional[str] = Query(default=None),
    price_tick: Optional[str] = Query(default=None),
    max_notional: Optional[str] = Query(default=None),
    leverage: Optional[str] = Query(default=None),
    max_attempts: Optional[int] = Query(default=None, ge=1, le=10),
    protection_mode: Optional[str] = Query(default=None),
    review_requirement: Optional[str] = Query(default=None),
) -> TradingConsoleReadModelResponse:
    return await _service(include_exchange=False).strategy_family_admission_state(
        owner_scope={
            "family": family,
            "strategy_family_id": strategy_family_id,
            "carrier_id": carrier_id,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "target_notional_usdt": target_notional_usdt,
            "current_price": current_price,
            "min_notional": min_notional,
            "min_qty": min_qty,
            "qty_step": qty_step,
            "price_tick": price_tick,
            "max_notional": max_notional,
            "leverage": leverage,
            "max_attempts": max_attempts,
            "protection_mode": protection_mode,
            "review_requirement": review_requirement,
        }
    )


@router.get("/action-entry-readiness", response_model=TradingConsoleReadModelResponse)
async def action_entry_readiness(
    market_regime: Optional[str] = Query(default=None),
    symbol_preference: Optional[str] = Query(default=None),
    preferred_strategy_family: Optional[str] = Query(default=None),
    risk_tier: Optional[str] = Query(default=None),
    owner_risk_acceptance: Optional[str] = Query(default=None),
    note: Optional[str] = Query(default=None),
    family: Optional[str] = Query(default=None),
    strategy_family_id: Optional[str] = Query(default=None),
    carrier_id: Optional[str] = Query(default=None),
    symbol: Optional[str] = Query(default=None),
    side: Optional[str] = Query(default=None),
    quantity: Optional[str] = Query(default=None),
    target_notional_usdt: Optional[str] = Query(default=None),
    current_price: Optional[str] = Query(default=None),
    min_notional: Optional[str] = Query(default=None),
    min_qty: Optional[str] = Query(default=None),
    qty_step: Optional[str] = Query(default=None),
    price_tick: Optional[str] = Query(default=None),
    max_notional: Optional[str] = Query(default=None),
    leverage: Optional[str] = Query(default=None),
    max_attempts: Optional[int] = Query(default=None, ge=1, le=10),
    protection_mode: Optional[str] = Query(default=None),
    review_requirement: Optional[str] = Query(default=None),
) -> TradingConsoleReadModelResponse:
    return await _service(include_exchange=False).action_entry_readiness(
        owner_scope={
            "family": family,
            "strategy_family_id": strategy_family_id,
            "carrier_id": carrier_id,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "target_notional_usdt": target_notional_usdt,
            "current_price": current_price,
            "min_notional": min_notional,
            "min_qty": min_qty,
            "qty_step": qty_step,
            "price_tick": price_tick,
            "max_notional": max_notional,
            "leverage": leverage,
            "max_attempts": max_attempts,
            "protection_mode": protection_mode,
            "review_requirement": review_requirement,
        },
        market_input={
            "regime": market_regime,
            "symbol_preference": symbol_preference,
            "preferred_strategy_family": preferred_strategy_family,
            "side": side,
            "risk_tier": risk_tier,
            "owner_risk_acceptance": owner_risk_acceptance,
            "note": note,
        },
    )


@router.get("/owner-action-flow", response_model=TradingConsoleReadModelResponse)
async def owner_action_flow(
    include_exchange: bool = Query(default=False),
    market_regime: Optional[str] = Query(default=None),
    symbol_preference: Optional[str] = Query(default=None),
    preferred_strategy_family: Optional[str] = Query(default=None),
    risk_tier: Optional[str] = Query(default=None),
    owner_risk_acceptance: Optional[str] = Query(default=None),
    note: Optional[str] = Query(default=None),
    family: Optional[str] = Query(default=None),
    strategy_family_id: Optional[str] = Query(default=None),
    carrier_id: Optional[str] = Query(default=None),
    symbol: Optional[str] = Query(default=None),
    side: Optional[str] = Query(default=None),
    quantity: Optional[str] = Query(default=None),
    target_notional_usdt: Optional[str] = Query(default=None),
    current_price: Optional[str] = Query(default=None),
    min_notional: Optional[str] = Query(default=None),
    min_qty: Optional[str] = Query(default=None),
    qty_step: Optional[str] = Query(default=None),
    price_tick: Optional[str] = Query(default=None),
    max_notional: Optional[str] = Query(default=None),
    leverage: Optional[str] = Query(default=None),
    max_attempts: Optional[int] = Query(default=None, ge=1, le=10),
    protection_mode: Optional[str] = Query(default=None),
    review_requirement: Optional[str] = Query(default=None),
    custom_total_budget: Optional[str] = Query(default=None),
    custom_max_notional_per_action: Optional[str] = Query(default=None),
    custom_max_daily_loss: Optional[str] = Query(default=None),
    custom_capacity_fraction: Optional[str] = Query(default=None),
    custom_max_active_positions: Optional[int] = Query(default=None, ge=1, le=3),
    custom_max_attempts: Optional[int] = Query(default=None, ge=1, le=3),
    custom_max_leverage: Optional[str] = Query(default=None),
    custom_budget_authorization_id: Optional[str] = Query(default=None),
    custom_attempt_window_start_ms: Optional[int] = Query(default=None, ge=0),
) -> TradingConsoleReadModelResponse:
    return await _service(include_exchange=include_exchange).owner_action_flow(
        owner_scope={
            "family": family,
            "strategy_family_id": strategy_family_id,
            "carrier_id": carrier_id,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "target_notional_usdt": target_notional_usdt,
            "current_price": current_price,
            "min_notional": min_notional,
            "min_qty": min_qty,
            "qty_step": qty_step,
            "price_tick": price_tick,
            "max_notional": max_notional,
            "leverage": leverage,
            "max_attempts": max_attempts,
            "protection_mode": protection_mode,
            "review_requirement": review_requirement,
        },
        market_input={
            "regime": market_regime,
            "symbol_preference": symbol_preference,
            "preferred_strategy_family": preferred_strategy_family,
            "side": side,
            "risk_tier": risk_tier,
            "owner_risk_acceptance": owner_risk_acceptance,
            "note": note,
        },
        custom_budget={
            "total_budget": custom_total_budget,
            "max_notional_per_action": custom_max_notional_per_action,
            "max_daily_loss": custom_max_daily_loss,
            "capacity_fraction": custom_capacity_fraction,
            "max_active_positions": custom_max_active_positions,
            "max_attempts": custom_max_attempts,
            "max_leverage": custom_max_leverage,
            "budget_authorization_id": custom_budget_authorization_id,
            "attempt_window_start_ms": custom_attempt_window_start_ms,
        },
        include_exchange=include_exchange,
    )


@router.get("/budget-recommendation", response_model=TradingConsoleReadModelResponse)
async def budget_recommendation(
    include_exchange: bool = Query(default=False),
    risk_tier: str = Query(default="tiny"),
    symbol_preference: Optional[str] = Query(default=None),
    symbol: Optional[str] = Query(default=None),
    side: Optional[str] = Query(default=None),
    quantity: Optional[str] = Query(default=None),
    target_notional_usdt: Optional[str] = Query(default=None),
    current_price: Optional[str] = Query(default=None),
    min_notional: Optional[str] = Query(default=None),
    min_qty: Optional[str] = Query(default=None),
    qty_step: Optional[str] = Query(default=None),
    price_tick: Optional[str] = Query(default=None),
    max_notional: Optional[str] = Query(default=None),
    leverage: Optional[str] = Query(default=None),
    max_attempts: Optional[int] = Query(default=None, ge=1, le=10),
    protection_mode: Optional[str] = Query(default=None),
    review_requirement: Optional[str] = Query(default=None),
    custom_total_budget: Optional[str] = Query(default=None),
    custom_max_notional_per_action: Optional[str] = Query(default=None),
    custom_max_daily_loss: Optional[str] = Query(default=None),
    custom_capacity_fraction: Optional[str] = Query(default=None),
    custom_max_active_positions: Optional[int] = Query(default=None, ge=1, le=3),
    custom_max_attempts: Optional[int] = Query(default=None, ge=1, le=3),
    custom_max_leverage: Optional[str] = Query(default=None),
    custom_budget_authorization_id: Optional[str] = Query(default=None),
    custom_attempt_window_start_ms: Optional[int] = Query(default=None, ge=0),
) -> TradingConsoleReadModelResponse:
    return await _service(include_exchange=include_exchange).budget_recommendation(
        include_exchange=include_exchange,
        risk_tier=risk_tier,
        custom={
            "total_budget": custom_total_budget,
            "max_notional_per_action": custom_max_notional_per_action,
            "max_daily_loss": custom_max_daily_loss,
            "capacity_fraction": custom_capacity_fraction,
            "max_active_positions": custom_max_active_positions,
            "max_attempts": custom_max_attempts,
            "max_leverage": custom_max_leverage,
            "budget_authorization_id": custom_budget_authorization_id,
            "attempt_window_start_ms": custom_attempt_window_start_ms,
        },
        owner_selection={
            "symbol": symbol,
            "symbol_preference": symbol_preference,
            "side": side,
            "quantity": quantity,
            "target_notional_usdt": target_notional_usdt,
            "current_price": current_price,
            "min_notional": min_notional,
            "min_qty": min_qty,
            "qty_step": qty_step,
            "price_tick": price_tick,
            "max_notional": max_notional,
            "leverage": leverage,
            "max_attempts": max_attempts,
            "protection_mode": protection_mode,
            "review_requirement": review_requirement,
        },
    )


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
    read_only_gateway = getattr(api_module, "_trading_console_read_only_exchange_gateway", None)
    if include_exchange and read_only_gateway is None and getattr(api_module, "_exchange_gateway", None) is None:
        read_only_gateway = _TradingConsoleLiveReadOnlyGateway()
        setattr(api_module, "_trading_console_read_only_exchange_gateway", read_only_gateway)
    if include_exchange:
        account_getter = getattr(api_module, "_account_getter", None)
        if callable(account_getter):
            try:
                account_snapshot = account_getter()
            except Exception:
                account_snapshot = None
        if account_snapshot is None:
            gateway = getattr(api_module, "_exchange_gateway", None)
            if gateway is None:
                gateway = read_only_gateway
            if gateway is not None and hasattr(gateway, "get_account_snapshot"):
                try:
                    account_snapshot = gateway.get_account_snapshot()
                except Exception:
                    account_snapshot = None

    order_repo = getattr(api_module, "_order_repo", None)
    position_repo = getattr(api_module, "_position_repo", None)
    execution_intent_repo = getattr(api_module, "_execution_intent_repo", None)
    execution_recovery_repo = getattr(api_module, "_execution_recovery_repo", None)
    live_lifecycle_review_repo = getattr(api_module, "_live_lifecycle_review_repo", None)
    if order_repo is None:
        order_repo = _cached_pg_repo(api_module, "_trading_console_pg_order_repo", _build_pg_order_repo)
    if position_repo is None:
        position_repo = _cached_pg_repo(api_module, "_trading_console_pg_position_repo", _build_pg_position_repo)
    if execution_intent_repo is None:
        execution_intent_repo = _cached_pg_repo(api_module, "_trading_console_pg_execution_intent_repo", _build_pg_execution_intent_repo)
    if execution_recovery_repo is None:
        execution_recovery_repo = _cached_pg_repo(api_module, "_trading_console_pg_execution_recovery_repo", _build_pg_execution_recovery_repo)
    if live_lifecycle_review_repo is None:
        live_lifecycle_review_repo = _cached_pg_repo(api_module, "_trading_console_pg_live_lifecycle_review_repo", _build_pg_live_lifecycle_review_repo)

    return TradingConsoleDependencies(
        runtime_bound=bool(api_module.get_runtime_context() is not None),
        runtime_config_provider=getattr(api_module, "_runtime_config_provider", None),
        account_snapshot=account_snapshot,
        exchange_gateway=(
            getattr(api_module, "_exchange_gateway", None)
            or read_only_gateway
        ),
        order_repo=order_repo,
        position_repo=position_repo,
        execution_intent_repo=execution_intent_repo,
        execution_recovery_repo=execution_recovery_repo,
        audit_logger=getattr(api_module, "_audit_logger", None),
        signal_repo=getattr(api_module, "_signal_repo", None),
        brc_campaign_service=getattr(api_module, "_brc_campaign_service", None),
        live_lifecycle_review_repo=live_lifecycle_review_repo,
        owner_trial_flow_service=_owner_trial_flow_service(),
        campaign_state_service=getattr(api_module, "_campaign_state_service", None),
        multi_carrier_budget_authorization_service=_multi_carrier_budget_authorization_service(),
        global_kill_switch_service=getattr(api_module, "_global_kill_switch_service", None),
        startup_trading_guard_service=getattr(api_module, "_startup_trading_guard_service", None),
        startup_reconciliation_summary=getattr(api_module, "_startup_reconciliation_summary", None),
        execution_orchestrator=getattr(api_module, "_execution_orchestrator", None),
    )


async def _strategy_runtime_service() -> Any:
    from src.interfaces import api as api_module

    injected = getattr(api_module, "_strategy_runtime_service", None)
    if injected is not None:
        return injected
    try:
        from src.application.strategy_runtime_service import StrategyRuntimeInstanceService
        from src.infrastructure.pg_brc_admission_repository import PgBrcAdmissionRepository
        from src.infrastructure.pg_strategy_runtime_repository import (
            PgStrategyRuntimeRepository,
        )

        service = StrategyRuntimeInstanceService(
            runtime_repository=PgStrategyRuntimeRepository(),
            admission_repository=PgBrcAdmissionRepository(),
        )
        await service.initialize()
    except Exception as exc:  # pragma: no cover - configuration-specific fail-closed path
        raise HTTPException(
            status_code=503,
            detail="Strategy runtime repository unavailable; persistent PG facts are required.",
        ) from exc
    setattr(api_module, "_strategy_runtime_service", service)
    return service


async def _signal_evaluation_shadow_service() -> Any:
    from src.interfaces import api as api_module

    injected = getattr(api_module, "_signal_evaluation_shadow_service", None)
    if injected is not None:
        return injected
    try:
        from src.application.signal_evaluation_shadow_service import (
            SignalEvaluationShadowService,
        )
        from src.infrastructure.pg_signal_evaluation_repository import (
            PgSignalEvaluationRepository,
        )

        service = SignalEvaluationShadowService(
            repository=PgSignalEvaluationRepository(),
        )
        await service.initialize()
    except Exception as exc:  # pragma: no cover - configuration-specific fail-closed path
        raise HTTPException(
            status_code=503,
            detail="Signal evaluation repository unavailable; persistent PG facts are required.",
        ) from exc
    setattr(api_module, "_signal_evaluation_shadow_service", service)
    return service


def _runtime_view(runtime: StrategyRuntimeInstance) -> StrategyRuntimeInspectionView:
    boundary = runtime.boundary
    return StrategyRuntimeInspectionView(
        runtime_instance_id=runtime.runtime_instance_id,
        trial_binding_id=runtime.trial_binding_id,
        admission_decision_id=runtime.admission_decision_id,
        strategy_family_id=runtime.strategy_family_id,
        strategy_family_version_id=runtime.strategy_family_version_id,
        signal_evaluation_id=None,
        order_candidate_id=None,
        owner_risk_acceptance_id=runtime.owner_risk_acceptance_id,
        carrier_id=runtime.carrier_id,
        symbol=runtime.symbol,
        side=runtime.side,
        status=runtime.status,
        boundary=StrategyRuntimeBoundaryView(
            max_attempts=boundary.max_attempts,
            attempts_used=boundary.attempts_used,
            attempts_remaining=boundary.attempts_remaining,
            max_active_positions=boundary.max_active_positions,
            max_notional_per_attempt=_decimal_string(boundary.max_notional_per_attempt),
            total_budget=_decimal_string(boundary.total_budget),
            budget_remaining=_decimal_string(boundary.budget_remaining),
            allowed_symbols=list(boundary.allowed_symbols),
            allowed_sides=list(boundary.allowed_sides),
            max_leverage=_decimal_string(boundary.max_leverage),
            requires_protection=boundary.requires_protection,
            requires_review=boundary.requires_review,
        ),
        policy_snapshot=runtime.policy_snapshot.model_dump(mode="json"),
        review_requirement=runtime.review_requirement.value,
        execution_enabled=runtime.execution_enabled,
        execution_mode="shadow_disabled",
        shadow_mode=runtime.shadow_mode,
        created_at_ms=runtime.created_at_ms,
        updated_at_ms=runtime.updated_at_ms,
        activated_at_ms=runtime.activated_at_ms,
        expires_at_ms=runtime.expires_at_ms,
        revoked_at_ms=runtime.revoked_at_ms,
        closed_at_ms=runtime.closed_at_ms,
        metadata=dict(runtime.metadata),
    )


def _signal_evaluation_view(evaluation: SignalEvaluation) -> SignalEvaluationInspectionView:
    return SignalEvaluationInspectionView(
        signal_evaluation_id=evaluation.signal_evaluation_id,
        runtime_instance_id=evaluation.runtime_instance_id,
        trial_binding_id=evaluation.trial_binding_id,
        strategy_family_id=evaluation.strategy_family_id,
        strategy_family_version_id=evaluation.strategy_family_version_id,
        source_signal_id=evaluation.source_signal_id,
        symbol=evaluation.symbol,
        side=evaluation.side,
        status=evaluation.status,
        decision=evaluation.decision.value,
        reason_codes=list(evaluation.reason_codes),
        rationale=evaluation.rationale,
        evidence_snapshot=dict(evaluation.evidence_snapshot),
        policy_snapshot=dict(evaluation.policy_snapshot),
        evaluated_at_ms=evaluation.evaluated_at_ms,
        expires_at_ms=evaluation.expires_at_ms,
        shadow_mode=evaluation.shadow_mode,
        execution_enabled=evaluation.execution_enabled,
        not_order=evaluation.not_order,
        not_execution_intent=evaluation.not_execution_intent,
        created_at_ms=evaluation.created_at_ms,
        updated_at_ms=evaluation.updated_at_ms,
        metadata=dict(evaluation.metadata),
    )


def _order_candidate_view(candidate: OrderCandidate) -> OrderCandidateInspectionView:
    return OrderCandidateInspectionView(
        order_candidate_id=candidate.order_candidate_id,
        signal_evaluation_id=candidate.signal_evaluation_id,
        runtime_instance_id=candidate.runtime_instance_id,
        trial_binding_id=candidate.trial_binding_id,
        strategy_family_id=candidate.strategy_family_id,
        strategy_family_version_id=candidate.strategy_family_version_id,
        symbol=candidate.symbol,
        side=candidate.side,
        status=candidate.status,
        candidate_order_type=candidate.candidate_order_type,
        proposed_quantity=_decimal_string(candidate.proposed_quantity),
        intended_notional=_decimal_string(candidate.intended_notional),
        entry_price_reference=_decimal_string(candidate.entry_price_reference),
        risk_preview=candidate.risk_preview.model_dump(mode="json"),
        protection_preview=candidate.protection_preview.model_dump(mode="json"),
        rationale=candidate.rationale,
        evidence_refs=list(candidate.evidence_refs),
        shadow_mode=candidate.shadow_mode,
        execution_enabled=candidate.execution_enabled,
        candidate_executable=candidate.candidate_executable,
        not_order=candidate.not_order,
        not_execution_intent=candidate.not_execution_intent,
        created_at_ms=candidate.created_at_ms,
        updated_at_ms=candidate.updated_at_ms,
        expires_at_ms=candidate.expires_at_ms,
        metadata=dict(candidate.metadata),
    )


def _decimal_string(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _cached_pg_repo(api_module: Any, attr_name: str, factory: Any) -> Optional[Any]:
    repo = getattr(api_module, attr_name, None)
    if repo is not None:
        return repo
    try:
        repo = factory()
    except Exception:
        return None
    setattr(api_module, attr_name, repo)
    return repo


def _build_pg_order_repo() -> Any:
    from src.infrastructure.pg_order_repository import PgOrderRepository

    return PgOrderRepository()


def _build_pg_position_repo() -> Any:
    from src.infrastructure.pg_position_repository import PgPositionRepository

    return PgPositionRepository()


def _build_pg_execution_intent_repo() -> Any:
    from src.infrastructure.pg_execution_intent_repository import PgExecutionIntentRepository

    return PgExecutionIntentRepository()


def _build_pg_execution_recovery_repo() -> Any:
    from src.infrastructure.pg_execution_recovery_repository import PgExecutionRecoveryRepository

    return PgExecutionRecoveryRepository()


def _build_pg_live_lifecycle_review_repo() -> Any:
    from src.infrastructure.pg_live_lifecycle_review_repository import PgLiveLifecycleReviewRepository

    return PgLiveLifecycleReviewRepository()


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


def _multi_carrier_budget_authorization_service() -> Optional[Any]:
    from src.interfaces import api as api_module

    injected = getattr(api_module, "_multi_carrier_budget_authorization_service", None)
    if injected is not None:
        return injected
    try:
        from src.interfaces.api_brc_console import _multi_carrier_budget_authorization_service_instance

        return _multi_carrier_budget_authorization_service_instance()
    except Exception:
        return None


async def close_trading_console_read_only_exchange_gateway() -> None:
    from src.interfaces import api as api_module

    gateway = getattr(api_module, "_trading_console_read_only_exchange_gateway", None)
    setattr(api_module, "_trading_console_read_only_exchange_gateway", None)
    if gateway is not None and hasattr(gateway, "close"):
        await gateway.close()
