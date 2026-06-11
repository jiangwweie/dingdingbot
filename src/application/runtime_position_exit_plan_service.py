"""Read-only runtime active-position exit plan service."""

from __future__ import annotations

import time
from typing import Any, Protocol

from src.domain.runtime_live_position_monitor import (
    build_runtime_live_position_monitor_packet,
)
from src.domain.runtime_position_exit_plan import (
    RuntimePositionExitPlan,
    build_runtime_position_exit_plan,
)
from src.domain.strategy_runtime import StrategyRuntimeInstance


class RuntimeRepositoryPort(Protocol):
    async def get(self, runtime_instance_id: str) -> StrategyRuntimeInstance | None:
        ...


class PositionRepositoryPort(Protocol):
    async def list_active(self, *, symbol: str | None = None, limit: int = 100) -> list[Any]:
        ...


class OrderRepositoryPort(Protocol):
    async def get_open_orders(self, symbol: str | None = None) -> list[Any]:
        ...


class ExchangeGatewayReadPort(Protocol):
    async def fetch_positions(self, symbol: str | None = None) -> list[Any]:
        ...

    async def fetch_open_orders(
        self,
        symbol: str,
        params: dict[str, Any] | None = None,
    ) -> list[Any]:
        ...

    async def get_market_info(self, symbol: str) -> dict[str, Any]:
        ...


class ReconciliationServicePort(Protocol):
    async def build_read_model(self, symbol: str) -> Any:
        ...


class RuntimePositionExitPlanService:
    """Build non-executing TP1/runner plans for active runtime positions."""

    def __init__(
        self,
        *,
        runtime_repository: RuntimeRepositoryPort,
        position_repository: PositionRepositoryPort,
        order_repository: OrderRepositoryPort,
        exchange_gateway: ExchangeGatewayReadPort | None = None,
        reconciliation_service: ReconciliationServicePort | None = None,
    ) -> None:
        self._runtime_repository = runtime_repository
        self._position_repository = position_repository
        self._order_repository = order_repository
        self._exchange_gateway = exchange_gateway
        self._reconciliation_service = reconciliation_service

    async def build_exit_plan(
        self,
        *,
        runtime_instance_id: str,
        now_ms: int | None = None,
    ) -> RuntimePositionExitPlan:
        now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
        get_runtime = getattr(self._runtime_repository, "get_runtime", None)
        if callable(get_runtime):
            runtime = await get_runtime(runtime_instance_id)
        else:
            runtime = await self._runtime_repository.get(runtime_instance_id)
        if runtime is None:
            raise ValueError(f"strategy runtime not found: {runtime_instance_id}")

        local_positions = await self._position_repository.list_active(
            symbol=runtime.symbol,
            limit=max(runtime.boundary.max_active_positions + 5, 20),
        )
        local_open_orders = await self._order_repository.get_open_orders(runtime.symbol)

        exchange_positions: list[Any] = []
        exchange_open_stop_orders: list[Any] = []
        market_rule: dict[str, Any] | None = None
        exchange_available = self._exchange_gateway is not None
        if self._exchange_gateway is not None:
            try:
                exchange_positions = list(
                    await self._exchange_gateway.fetch_positions(symbol=runtime.symbol)
                )
                exchange_open_stop_orders = list(
                    await self._exchange_gateway.fetch_open_orders(
                        runtime.symbol,
                        params={"stop": True},
                    )
                )
                get_market_info = getattr(self._exchange_gateway, "get_market_info", None)
                if callable(get_market_info):
                    market_rule = dict(await get_market_info(runtime.symbol))
            except Exception:
                exchange_positions = []
                exchange_open_stop_orders = []
                market_rule = None
                exchange_available = False

        reconciliation_result = None
        if self._reconciliation_service is not None:
            try:
                reconciliation_result = await self._reconciliation_service.build_read_model(
                    runtime.symbol
                )
            except Exception:
                reconciliation_result = None

        monitor = build_runtime_live_position_monitor_packet(
            runtime=runtime,
            local_positions=list(local_positions),
            local_open_orders=list(local_open_orders),
            exchange_positions=exchange_positions,
            exchange_open_stop_orders=exchange_open_stop_orders,
            reconciliation_result=reconciliation_result,
            now_ms=now_ms,
            exchange_facts_available=exchange_available,
        )
        return build_runtime_position_exit_plan(
            runtime=runtime,
            monitor=monitor,
            local_open_orders=list(local_open_orders),
            exchange_open_stop_orders=exchange_open_stop_orders,
            market_rule=market_rule,
            now_ms=now_ms,
        )
