"""Install one immutable StrategyUniverse without certification or activation."""

from __future__ import annotations

import json
from enum import StrEnum
from hashlib import sha256
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, JsonValue, field_validator

from src.trading_kernel.domain.instrument_identity import (
    parse_binance_usdm_instrument_id,
)
from src.trading_kernel.domain.owner_control import OwnerAuthorization
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


class UniverseControlConflict(RuntimeError):
    """The submitted Universe edit no longer matches current authority."""


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
            raise ValueError(  # noqa: TRY004 - Pydantic must surface a ValidationError.
                "Universe members must be an identity collection"
            )
        if not isinstance(value, (tuple, list)):
            raise ValueError(  # noqa: TRY004 - Pydantic must surface a ValidationError.
                "Universe members must be an identity collection"
            )
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


class UniverseConfigurationRequest(BaseModel):
    """Owner-facing install request before PostgreSQL resolves canonical authority."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    runtime_profile_id: str
    event_id: str
    exchange_instrument_ids: tuple[str, ...]
    installed_at_ms: int

    @field_validator("runtime_profile_id", "event_id", mode="before")
    @classmethod
    def _require_exact_identity(cls, value: object) -> str:
        if not isinstance(value, str) or not value or value != value.strip():
            raise ValueError("Universe configuration identities must be exact")
        return value

    @field_validator("exchange_instrument_ids", mode="before")
    @classmethod
    def _canonical_members(cls, value: object) -> tuple[str, ...]:
        return UniverseInstallRequest._canonical_members(value)

    @field_validator("installed_at_ms")
    @classmethod
    def _require_install_time(cls, value: int) -> int:
        return UniverseInstallRequest._require_install_time(value)


class OwnerUniverseConfigurationRequest(UniverseConfigurationRequest):
    """One TOTP-authorized Owner edit against an exact Active Universe base."""

    expected_base_universe_version_id: str | None
    reason: str
    idempotency_key: str
    owner_identity: str

    @field_validator("expected_base_universe_version_id", mode="before")
    @classmethod
    def _require_optional_base_identity(cls, value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or not value or value != value.strip():
            raise ValueError("Universe base identity must be exact")
        return value

    @field_validator("reason", "idempotency_key", "owner_identity", mode="before")
    @classmethod
    def _require_owner_text(cls, value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Universe Owner request text must be non-blank")
        return value.strip()


class UniverseInstallContext(BaseModel):
    """Exact current Event and Owner Policy selected for one configuration."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_spec_id: str
    owner_policy_id: str

    @field_validator("event_spec_id", "owner_policy_id", mode="before")
    @classmethod
    def _require_exact_identity(cls, value: object) -> str:
        if not isinstance(value, str) or not value or value != value.strip():
            raise ValueError("Universe install context identities must be exact")
        return value


class UniverseInstallPolicyScope(BaseModel):
    """Exact Owner Policy shape consumed by Universe installation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    runtime_profile_id: str
    allowed_event_spec_ids: tuple[str, ...]
    owner_console_primary: bool | None = None

    @field_validator("runtime_profile_id", mode="before")
    @classmethod
    def _require_runtime_profile_id(cls, value: object) -> str:
        if not isinstance(value, str) or not value or value != value.strip():
            raise ValueError("Policy scope runtime profile id must be exact")
        return value

    @field_validator("allowed_event_spec_ids", mode="before")
    @classmethod
    def _require_canonical_event_ids(cls, value: object) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError(  # noqa: TRY004 - Pydantic must surface a ValidationError.
                "Policy scope Event ids must be a list or tuple"
            )
        event_ids: tuple[object, ...] = tuple(value)
        if not event_ids or any(
            not isinstance(event_id, str)
            or not event_id
            or event_id != event_id.strip()
            or not event_id.startswith("event_spec:")
            for event_id in event_ids
        ):
            raise ValueError("Policy scope Event ids must be exact identities")
        canonical_event_ids = tuple(str(event_id) for event_id in event_ids)
        if canonical_event_ids != tuple(sorted(set(canonical_event_ids))):
            raise ValueError("Policy scope Event ids must be sorted and unique")
        return canonical_event_ids


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
    uow: KernelUnitOfWork,
    request: UniverseInstallRequest,
) -> UniverseInstallResult:
    """Delegate one short transaction's persistence to the Universe repository."""

    return await uow.strategy_universes.install(request)


async def configure_strategy_universe(
    uow: KernelUnitOfWork,
    request: UniverseConfigurationRequest,
) -> UniverseInstallResult:
    """Resolve current PostgreSQL authority, then use the canonical installer."""

    context = await uow.strategy_universes.resolve_install_context(
        runtime_profile_id=request.runtime_profile_id,
        event_id=request.event_id,
    )
    return await install_strategy_universe(
        uow,
        UniverseInstallRequest(
            event_spec_id=context.event_spec_id,
            runtime_profile_id=request.runtime_profile_id,
            owner_policy_id=context.owner_policy_id,
            exchange_instrument_ids=request.exchange_instrument_ids,
            installed_at_ms=request.installed_at_ms,
        ),
    )


async def configure_strategy_universe_by_owner(
    uow: KernelUnitOfWork,
    request: OwnerUniverseConfigurationRequest,
) -> UniverseInstallResult:
    """Create only a Warming Universe under one durable Owner authorization."""

    context = await uow.strategy_universes.resolve_install_context(
        runtime_profile_id=request.runtime_profile_id,
        event_id=request.event_id,
    )
    current = await uow.strategy_universes.get_current(context.event_spec_id)
    current_version_id = None if current is None else current.universe_version_id
    if current_version_id != request.expected_base_universe_version_id:
        raise UniverseControlConflict("universe_base_changed")

    target_scope: dict[str, JsonValue] = {
        "runtime_profile_id": request.runtime_profile_id,
        "event_id": request.event_id,
        "event_spec_id": context.event_spec_id,
        "owner_policy_id": context.owner_policy_id,
        "expected_base_universe_version_id": (
            request.expected_base_universe_version_id
        ),
        "exchange_instrument_ids": list(request.exchange_instrument_ids),
    }
    existing = await uow.owner_controls.get_authorization_by_idempotency_key(
        request.idempotency_key
    )
    if existing is not None:
        _require_matching_universe_authorization(
            existing,
            request=request,
            target_scope=target_scope,
        )

    result = await install_strategy_universe(
        uow,
        UniverseInstallRequest(
            event_spec_id=context.event_spec_id,
            runtime_profile_id=request.runtime_profile_id,
            owner_policy_id=context.owner_policy_id,
            exchange_instrument_ids=request.exchange_instrument_ids,
            installed_at_ms=request.installed_at_ms,
        ),
    )
    if existing is None and result.status is UniverseInstallStatus.INSTALLED:
        await uow.owner_controls.add_authorization(
            _universe_authorization(request=request, target_scope=target_scope)
        )
    return result


def _universe_authorization(
    *,
    request: OwnerUniverseConfigurationRequest,
    target_scope: dict[str, JsonValue],
) -> OwnerAuthorization:
    return OwnerAuthorization(
        authorization_id=f"owner-authorization:{uuid4().hex}",
        purpose="universe_configure",
        owner_identity=request.owner_identity,
        authentication_strength="totp_step_up",
        request_digest=_universe_authorization_digest(
            request=request,
            target_scope=target_scope,
        ),
        target_scope=target_scope,
        idempotency_key=request.idempotency_key,
        authorized_at_ms=request.installed_at_ms,
    )


def _universe_authorization_digest(
    *,
    request: OwnerUniverseConfigurationRequest,
    target_scope: dict[str, JsonValue],
) -> str:
    canonical_request = {
        "purpose": "universe_configure",
        "reason": request.reason,
        "idempotency_key": request.idempotency_key,
        "target_scope": target_scope,
    }
    return "sha256:" + sha256(
        json.dumps(
            canonical_request,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def _require_matching_universe_authorization(
    existing: OwnerAuthorization,
    *,
    request: OwnerUniverseConfigurationRequest,
    target_scope: dict[str, JsonValue],
) -> None:
    if (
        existing.purpose != "universe_configure"
        or existing.owner_identity != request.owner_identity
        or existing.target_scope != target_scope
        or existing.request_digest
        != _universe_authorization_digest(
            request=request,
            target_scope=target_scope,
        )
    ):
        raise UniverseControlConflict("idempotency_key_conflict")
