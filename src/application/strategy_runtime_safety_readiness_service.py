"""Application service for runtime safety readiness previews."""

from __future__ import annotations

from src.domain.strategy_runtime import StrategyRuntimeInstance
from src.domain.strategy_runtime_safety_readiness import (
    StrategyRuntimeSafetyReadiness,
    evaluate_strategy_runtime_safety_readiness,
)


class StrategyRuntimeSafetyReadinessRuntimePort:
    async def get_runtime(self, runtime_instance_id: str) -> StrategyRuntimeInstance:
        raise NotImplementedError


class StrategyRuntimeSafetyReadinessService:
    """Build non-executing runtime safety readiness previews."""

    def __init__(self, runtime_service: StrategyRuntimeSafetyReadinessRuntimePort) -> None:
        self._runtime_service = runtime_service

    async def preview(self, *, runtime_instance_id: str) -> StrategyRuntimeSafetyReadiness:
        runtime = await self._runtime_service.get_runtime(runtime_instance_id)
        return evaluate_strategy_runtime_safety_readiness(runtime)
