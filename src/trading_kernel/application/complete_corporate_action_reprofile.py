"""Reactivate one current scope after profile, rules, projection, and warm proof."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator

from src.trading_kernel.application.ports import KernelUnitOfWork


class CompleteCorporateActionReprofileRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    runtime_scope_id: str
    universe_version_id: str
    completed_at_ms: int

    @field_validator(
        "runtime_scope_id",
        "universe_version_id",
        mode="before",
    )
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("reprofile identity must be non-blank")
        return normalized

    @field_validator("completed_at_ms")
    @classmethod
    def _require_time(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("reprofile completion time must be positive")
        return value


async def complete_corporate_action_reprofile(
    uow: KernelUnitOfWork,
    request: CompleteCorporateActionReprofileRequest,
) -> None:
    await uow.strategy_universes.reactivate_reprofiled_scope(
        runtime_scope_id=request.runtime_scope_id,
        universe_version_id=request.universe_version_id,
        reactivated_at_ms=request.completed_at_ms,
    )
