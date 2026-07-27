"""Atomically make a fully warmed Universe current for new ENTRY."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator

from src.trading_kernel.application.ports import KernelUnitOfWork
from src.trading_kernel.domain.strategy_universe import UniverseActivationRecord


class ActivateStrategyUniverseRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_spec_id: str
    universe_version_id: str
    expected_current_universe_version_id: str | None = None
    activated_at_ms: int

    @field_validator(
        "event_spec_id",
        "universe_version_id",
        "expected_current_universe_version_id",
        mode="before",
    )
    @classmethod
    def _require_identity(cls, value: object, info) -> str | None:
        if (
            info.field_name == "expected_current_universe_version_id"
            and value is None
        ):
            return None
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("universe activation identity must be non-blank")
        return normalized

    @field_validator("activated_at_ms")
    @classmethod
    def _require_time(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("universe activation time must be positive")
        return value


async def activate_strategy_universe(
    uow: KernelUnitOfWork,
    request: ActivateStrategyUniverseRequest,
) -> UniverseActivationRecord:
    return await uow.strategy_universes.activate(
        event_spec_id=request.event_spec_id,
        universe_version_id=request.universe_version_id,
        expected_current_universe_version_id=(
            request.expected_current_universe_version_id
        ),
        activated_at_ms=request.activated_at_ms,
    )
