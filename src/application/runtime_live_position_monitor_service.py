"""Application service for runtime-native live position monitoring."""

from __future__ import annotations

import time
from typing import Any, Protocol

from src.domain.runtime_live_position_monitor import (
    RuntimeLivePositionMonitorPacket,
    build_runtime_live_position_monitor_packet,
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


class ReconciliationServicePort(Protocol):
    async def build_read_model(self, symbol: str) -> Any:
        ...


class RuntimeLivePositionMonitorService:
    """Build post-submit runtime monitor packets from read-only facts.

    This service is read-only with respect to execution: it may call repository
    reads and exchange read endpoints, but it never creates/cancels/amends
    orders, closes positions, writes runtime state, or submits anything.
    """

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

    async def build_monitor_packet(
        self,
        *,
        runtime_instance_id: str,
        now_ms: int | None = None,
    ) -> RuntimeLivePositionMonitorPacket:
        now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
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
        exchange_available = self._exchange_gateway is not None
        if self._exchange_gateway is not None:
            exchange_positions = list(
                await self._exchange_gateway.fetch_positions(symbol=runtime.symbol)
            )
            exchange_open_stop_orders = list(
                await self._exchange_gateway.fetch_open_orders(
                    runtime.symbol,
                    params={"stop": True},
                )
            )

        reconciliation_result = None
        if self._reconciliation_service is not None:
            reconciliation_result = await self._reconciliation_service.build_read_model(
                runtime.symbol
            )

        return build_runtime_live_position_monitor_packet(
            runtime=runtime,
            local_positions=list(local_positions),
            local_open_orders=list(local_open_orders),
            exchange_positions=exchange_positions,
            exchange_open_stop_orders=exchange_open_stop_orders,
            reconciliation_result=reconciliation_result,
            now_ms=now_ms,
            exchange_facts_available=exchange_available,
        )
