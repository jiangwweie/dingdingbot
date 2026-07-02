"""Read-only resolver for runtime closed-trade review input facts."""

from __future__ import annotations

import time
from typing import Protocol

from src.domain.models import Order, Position
from src.domain.runtime_closed_trade_review_facts import (
    RuntimeClosedTradeReviewFactsArtifact,
    RuntimeClosedTradeReviewFactsStatus,
    build_runtime_closed_trade_review_facts_artifact,
)
from src.domain.strategy_runtime import StrategyRuntimeInstance


class RuntimeRepositoryPort(Protocol):
    async def get(self, runtime_instance_id: str) -> StrategyRuntimeInstance | None:
        ...


class OrderRepositoryPort(Protocol):
    async def get_orders_by_symbol(self, symbol: str, limit: int = 100) -> list[Order]:
        ...

    async def get_open_orders(self, symbol: str | None = None) -> list[Order]:
        ...


class PositionRepositoryPort(Protocol):
    async def list_active(self, *, symbol: str | None = None, limit: int = 100) -> list[Position]:
        ...


class RuntimeClosedTradeReviewFactsService:
    def __init__(
        self,
        *,
        runtime_repository: RuntimeRepositoryPort,
        order_repository: OrderRepositoryPort,
        position_repository: PositionRepositoryPort,
    ) -> None:
        self._runtime_repository = runtime_repository
        self._order_repository = order_repository
        self._position_repository = position_repository

    async def build_artifact(
        self,
        *,
        runtime_instance_id: str,
        order_limit: int = 100,
        now_ms: int | None = None,
    ) -> RuntimeClosedTradeReviewFactsArtifact:
        now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
        runtime = await self._runtime_repository.get(runtime_instance_id)
        if runtime is None:
            return RuntimeClosedTradeReviewFactsArtifact(
                artifact_id=f"runtime-closed-review-facts-{runtime_instance_id}-{now_ms}",
                status=RuntimeClosedTradeReviewFactsStatus.BLOCKED,
                runtime_instance_id=runtime_instance_id,
                symbol="unknown",
                active_position_count=0,
                open_order_count=0,
                recommended_review_checkpoint="repair_runtime_before_closed_review",
                blockers=["runtime_not_found"],
                created_at_ms=now_ms,
            )

        orders = await self._order_repository.get_orders_by_symbol(
            runtime.symbol,
            limit=order_limit,
        )
        active_positions = await self._position_repository.list_active(
            symbol=runtime.symbol,
            limit=max(runtime.boundary.max_active_positions + 5, 20),
        )
        open_orders = await self._order_repository.get_open_orders(runtime.symbol)
        return build_runtime_closed_trade_review_facts_artifact(
            runtime=runtime,
            orders=orders,
            active_positions=active_positions,
            open_orders=open_orders,
            now_ms=now_ms,
        )
