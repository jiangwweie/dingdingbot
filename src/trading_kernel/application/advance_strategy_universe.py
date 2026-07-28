"""Atomically activate one fully certified and warmed StrategyUniverse."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

if TYPE_CHECKING:
    from src.trading_kernel.application.ports import KernelUnitOfWork


class UniverseActivationStatus(StrEnum):
    ACTIVATED = "activated"
    NOT_READY = "not_ready"
    ALREADY_ACTIVE = "already_active"


class UniverseActivationReadiness(BaseModel):
    """Typed DB facts consumed by the pure activation gate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    target_is_warming: bool
    current_is_complete: bool
    event_is_active: bool
    members_are_complete: bool
    scopes_are_complete: bool
    certifications_are_complete: bool
    certifications_are_eligible: bool
    certifications_are_fresh: bool
    warm_readiness_is_complete: bool
    warm_readiness_is_fresh: bool
    comparative_projection_is_required: bool
    comparative_projection_is_complete: bool


def activation_readiness_blocker(
    readiness: UniverseActivationReadiness,
) -> str | None:
    """Return the first stable fail-closed blocker for one locked snapshot."""

    ordered_checks = (
        (readiness.target_is_warming, "UNIVERSE_NOT_WARMING"),
        (
            readiness.current_is_complete,
            "CURRENT_UNIVERSE_IDENTITY_CONFLICT",
        ),
        (readiness.event_is_active, "EVENT_AUTHORITY_CONFLICT"),
        (
            readiness.members_are_complete,
            "UNIVERSE_MEMBER_IDENTITY_CONFLICT",
        ),
        (
            readiness.scopes_are_complete,
            "WARMING_SCOPE_IDENTITY_CONFLICT",
        ),
        (
            readiness.certifications_are_complete,
            "CERTIFICATION_MISSING",
        ),
        (
            readiness.certifications_are_eligible,
            "CERTIFICATION_NOT_ELIGIBLE",
        ),
        (
            readiness.certifications_are_fresh,
            "CERTIFICATION_STALE",
        ),
        (
            readiness.warm_readiness_is_complete,
            "WARM_READINESS_MISSING",
        ),
        (
            readiness.warm_readiness_is_fresh,
            "WARM_READINESS_STALE",
        ),
    )
    for accepted, reason_code in ordered_checks:
        if not accepted:
            return reason_code
    if (
        readiness.comparative_projection_is_required
        and not readiness.comparative_projection_is_complete
    ):
        return "COMPARATIVE_PROJECTION_INCOMPLETE"
    return None


class UniverseActivationRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    universe_version_id: str
    attempted_at_ms: int

    @field_validator("universe_version_id", mode="before")
    @classmethod
    def _require_universe_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("activation Universe identity must be non-blank")
        return normalized

    @field_validator("attempted_at_ms")
    @classmethod
    def _require_attempt_time(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("activation attempt time must be positive")
        return value


class UniverseActivationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: UniverseActivationStatus
    reason_code: str | None
    event_spec_id: str
    universe_version_id: str
    previous_universe_version_id: str | None
    activation_generation: int | None
    activated_at_ms: int | None

    @model_validator(mode="after")
    def _validate_result_shape(self) -> UniverseActivationResult:
        identities = (self.event_spec_id, self.universe_version_id)
        if any(not item.strip() for item in identities):
            raise ValueError("activation result identities must be non-blank")
        if self.status is UniverseActivationStatus.NOT_READY:
            if (
                self.reason_code is None
                or not self.reason_code.strip()
                or self.activated_at_ms is not None
            ):
                raise ValueError("not-ready activation result shape is invalid")
            return self
        if (
            self.reason_code is not None
            or self.activation_generation is None
            or self.activation_generation <= 0
            or self.activated_at_ms is None
            or self.activated_at_ms <= 0
        ):
            raise ValueError("successful activation result shape is invalid")
        return self


async def advance_strategy_universe(
    uow: KernelUnitOfWork,
    request: UniverseActivationRequest,
) -> UniverseActivationResult:
    """Delegate one DB-only activation attempt to the current UoW."""

    return await uow.strategy_universes.try_activate(request)
