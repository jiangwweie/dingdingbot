"""Perform the one allowed terminal exit from a Warming StrategyUniverse."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, field_validator

if TYPE_CHECKING:
    from src.trading_kernel.application.ports import KernelUnitOfWork


class AbandonStrategyUniverseRequest(BaseModel):
    """Exact, audited Warming-only abandonment instruction."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    universe_version_id: str
    reason_code: str
    attempted_at_ms: int

    @field_validator("universe_version_id", mode="before")
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("abandon Universe identity must be non-blank")
        return normalized

    @field_validator("reason_code", mode="before")
    @classmethod
    def _require_stable_reason(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if re.fullmatch(r"[a-z][a-z0-9_]{2,95}", normalized) is None:
            raise ValueError("abandon reason must be a stable lowercase code")
        return normalized

    @field_validator("attempted_at_ms")
    @classmethod
    def _require_attempt_time(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("abandon attempt time must be positive")
        return value


async def abandon_strategy_universe(
    uow: KernelUnitOfWork,
    request: AbandonStrategyUniverseRequest,
) -> None:
    """Delegate a DB-only, exact Warming exit to the repository."""

    await uow.strategy_universes.abandon(request)
