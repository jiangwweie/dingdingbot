"""Bounded, non-sensitive Strategy Universe operational status."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

if TYPE_CHECKING:
    from src.trading_kernel.application.ports import KernelUnitOfWork


CertificationDisplayStatus = Literal[
    "missing",
    "eligible",
    "owner_action_required",
    "temporarily_unavailable",
]
MonitorDisplayStatus = Literal["running", "needs_intervention"]


class StrategyUniverseStatusRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    runtime_profile_id: str
    event_id: str | None = None

    @field_validator("runtime_profile_id", mode="before")
    @classmethod
    def _require_runtime_profile(cls, value: object) -> str:
        if not isinstance(value, str) or not value or value != value.strip():
            raise ValueError("status runtime profile identity must be exact")
        return value

    @field_validator("event_id", mode="before")
    @classmethod
    def _require_event(cls, value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or not value or value != value.strip():
            raise ValueError("status Event identity must be exact")
        return value


class StrategyUniverseMemberStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_instrument_id: str
    certification_status: CertificationDisplayStatus
    warm_ready: bool
    monitor_status: MonitorDisplayStatus | None
    blocker_code: str | None


class StrategyUniverseVersionStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str
    event_spec_id: str
    universe_version_id: str
    semantic_digest: str
    lifecycle_state: Literal["warming", "active"]
    current_generation: int | None
    members: tuple[StrategyUniverseMemberStatus, ...]

    @model_validator(mode="after")
    def _validate_bounded_current_status(self) -> "StrategyUniverseVersionStatus":
        if not 1 <= len(self.members) <= 10:
            raise ValueError("status Universe must contain between one and ten members")
        member_ids = tuple(member.exchange_instrument_id for member in self.members)
        if member_ids != tuple(sorted(set(member_ids))):
            raise ValueError("status Universe members must be sorted and unique")
        if self.lifecycle_state == "active":
            if self.current_generation is None or self.current_generation <= 0:
                raise ValueError("active status requires current generation")
        elif self.current_generation is not None:
            raise ValueError("warming status cannot expose current generation")
        return self


class StrategyUniverseStatusResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    runtime_profile_id: str
    universes: tuple[StrategyUniverseVersionStatus, ...]

    @field_validator("universes")
    @classmethod
    def _bound_universes(
        cls,
        value: tuple[StrategyUniverseVersionStatus, ...],
    ) -> tuple[StrategyUniverseVersionStatus, ...]:
        if len(value) > 7:
            raise ValueError("status result exceeds active plus warming bound")
        return value


async def read_strategy_universe_status(
    uow: "KernelUnitOfWork",
    request: StrategyUniverseStatusRequest,
) -> StrategyUniverseStatusResult:
    """Read current/warming authority through the application repository port."""

    return await uow.strategy_universes.read_status(request)
