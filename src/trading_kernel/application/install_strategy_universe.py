"""Install one immutable Strategy Universe without making it current."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from src.trading_kernel.application.ports import KernelUnitOfWork
from src.trading_kernel.domain.strategy_universe import (
    StrategyUniverseVersion,
    UniverseInstallCounts,
    UniverseLifecycle,
)


class InstallStrategyUniverseRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    universe: StrategyUniverseVersion
    position_side: Literal["long", "short"]
    installed_at_ms: int

    @field_validator("installed_at_ms")
    @classmethod
    def _require_time(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Universe install time must be positive")
        return value


async def install_strategy_universe(
    uow: KernelUnitOfWork,
    request: InstallStrategyUniverseRequest,
) -> UniverseInstallCounts:
    return await uow.strategy_universes.install_exact(
        request.universe,
        position_side=request.position_side,
        initial_lifecycle=UniverseLifecycle.WARMING,
        installed_at_ms=request.installed_at_ms,
    )
