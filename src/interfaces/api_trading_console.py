"""Trading Console read-only API namespace."""

from __future__ import annotations

import asyncio
import os
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


@router.get("/dashboard-state", response_model=TradingConsoleReadModelResponse)
async def dashboard_state(
    symbol: Optional[str] = Query(default=None),
    include_exchange: bool = Query(default=False),
) -> TradingConsoleReadModelResponse:
    return await _service(include_exchange=include_exchange).dashboard_state(
        symbol=symbol,
        include_exchange=include_exchange,
    )


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
    risk_tier: Optional[str] = Query(default=None),
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
            "side": side,
            "risk_tier": risk_tier,
            "note": note,
        },
    )


@router.get("/owner-action-flow", response_model=TradingConsoleReadModelResponse)
async def owner_action_flow(
    include_exchange: bool = Query(default=False),
    market_regime: Optional[str] = Query(default=None),
    symbol_preference: Optional[str] = Query(default=None),
    risk_tier: Optional[str] = Query(default=None),
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
            "side": side,
            "risk_tier": risk_tier,
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
    if order_repo is None:
        order_repo = _cached_pg_repo(api_module, "_trading_console_pg_order_repo", _build_pg_order_repo)
    if position_repo is None:
        position_repo = _cached_pg_repo(api_module, "_trading_console_pg_position_repo", _build_pg_position_repo)
    if execution_intent_repo is None:
        execution_intent_repo = _cached_pg_repo(api_module, "_trading_console_pg_execution_intent_repo", _build_pg_execution_intent_repo)
    if execution_recovery_repo is None:
        execution_recovery_repo = _cached_pg_repo(api_module, "_trading_console_pg_execution_recovery_repo", _build_pg_execution_recovery_repo)

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
        owner_trial_flow_service=_owner_trial_flow_service(),
        campaign_state_service=getattr(api_module, "_campaign_state_service", None),
        multi_carrier_budget_authorization_service=_multi_carrier_budget_authorization_service(),
        global_kill_switch_service=getattr(api_module, "_global_kill_switch_service", None),
        startup_trading_guard_service=getattr(api_module, "_startup_trading_guard_service", None),
        startup_reconciliation_summary=getattr(api_module, "_startup_reconciliation_summary", None),
        execution_orchestrator=getattr(api_module, "_execution_orchestrator", None),
    )


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
