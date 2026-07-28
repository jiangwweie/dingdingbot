"""Install one immutable StrategyUniverse without certification or activation."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, field_validator

from src.trading_kernel.domain.instrument_identity import (
    parse_binance_usdm_instrument_id,
)
from src.trading_kernel.domain.strategy_universe import (
    MAX_UNIVERSE_MEMBERS,
    StrategyUniverseVersion,
)

if TYPE_CHECKING:
    from src.trading_kernel.application.ports import KernelUnitOfWork


class UniverseInstallStatus(StrEnum):
    INSTALLED = "installed"
    ALREADY_WARMING = "already_warming"
    ALREADY_ACTIVE = "already_active"
    WARMING_UNIVERSE_ALREADY_EXISTS = "WARMING_UNIVERSE_ALREADY_EXISTS"


class UniverseInstallRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_spec_id: str
    runtime_profile_id: str
    owner_policy_id: str
    exchange_instrument_ids: tuple[str, ...]
    installed_at_ms: int

    @field_validator(
        "event_spec_id",
        "runtime_profile_id",
        "owner_policy_id",
        mode="before",
    )
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Universe install identities must be non-blank")
        return normalized

    @field_validator("exchange_instrument_ids", mode="before")
    @classmethod
    def _canonical_members(cls, value: object) -> tuple[str, ...]:
        if isinstance(value, (str, bytes)):
            raise ValueError("Universe members must be an identity collection")
        if not isinstance(value, (tuple, list)):
            raise ValueError("Universe members must be an identity collection")
        members: tuple[object, ...] = tuple(value)
        if not 1 <= len(members) <= MAX_UNIVERSE_MEMBERS:
            raise ValueError("Universe install requires between one and ten members")
        if len(set(members)) != len(members):
            raise ValueError("Universe install members must be unique")
        if any(not isinstance(member, str) for member in members):
            raise ValueError("Universe members must use canonical string identities")
        canonical_members = tuple(str(member) for member in members)
        for member in canonical_members:
            parse_binance_usdm_instrument_id(member)
        return tuple(sorted(canonical_members))

    @field_validator("installed_at_ms")
    @classmethod
    def _require_install_time(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Universe install time must be positive")
        return value


class UniverseInstallResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: UniverseInstallStatus
    universe: StrategyUniverseVersion | None
    lifecycle_state: Literal["warming", "active"] | None
    inserted_instrument_count: int
    inserted_version_count: int
    inserted_member_count: int
    inserted_scope_count: int

    @property
    def total_inserted_count(self) -> int:
        return (
            self.inserted_instrument_count
            + self.inserted_version_count
            + self.inserted_member_count
            + self.inserted_scope_count
        )


class UniverseCurrent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_spec_id: str
    universe_version_id: str
    semantic_digest: str
    activation_generation: int
    activated_at_ms: int


async def install_strategy_universe(
    uow: "KernelUnitOfWork",
    request: UniverseInstallRequest,
) -> UniverseInstallResult:
    """Delegate one short transaction's persistence to the Universe repository."""

    return await uow.strategy_universes.install(request)
