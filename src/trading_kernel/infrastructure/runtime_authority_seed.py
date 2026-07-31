"""Exact Tokyo runtime authority seed and monotonic policy transitions."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from typing import Any, Literal, cast

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

from src.trading_kernel.domain.strategy_registry import (
    RegisteredStrategyContract,
    build_registry_semantic_hash,
    registered_strategy_contracts,
)
from src.trading_kernel.infrastructure.pg_models import (
    account_exposure_current,
    budget_reservations,
    entry_lane_current,
    exchange_commands,
    owner_policy_current,
    owner_policy_events,
    positions_current,
    runtime_capabilities_current,
    runtime_incidents,
    runtime_profiles,
    schema_metadata,
    trade_aggregates,
    trade_reviews,
    trade_tickets,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_identity import (
    TradingKernelSchemaRevision,
)
from src.trading_kernel.infrastructure.strategy_registry_seed import (
    seed_strategy_registry,
)

RUNTIME_PROFILE_ID = "tiny-live-v1"
OWNER_POLICY_ID = "policy-main"
GLOBAL_ENTRY_LANE_ID = "global-entry"
VENUE_ID = "binance-usdm"
POSITION_MODE = "independent_sides"
COMPATIBLE_SOURCE_SCHEMA_REVISION = "0001_trading_kernel_baseline_v4"


class RuntimeAuthoritySeedConflict(RuntimeError):
    """Existing PostgreSQL authority differs from the committed seed."""


class RuntimeAuthorityTransitionRefused(RuntimeError):
    """A monotonic live-capability transition failed a hard gate."""


class RuntimeAuthoritySeedRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: str
    runtime_commit: str
    schema_revision: TradingKernelSchemaRevision
    seeded_at_ms: int

    @field_validator("account_id", "runtime_commit", mode="before")
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("runtime authority seed identities must be non-blank")
        return normalized

    @field_validator("seeded_at_ms")
    @classmethod
    def _require_seed_time(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("runtime authority seed time must be positive")
        return value


class ArmAcceptancePolicyRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    armed_at_ms: int

    @field_validator("armed_at_ms")
    @classmethod
    def _require_time(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("acceptance arm time must be positive")
        return value


class PromoteFullPolicyRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    acceptance_ticket_id: str
    promoted_at_ms: int

    @field_validator("acceptance_ticket_id", mode="before")
    @classmethod
    def _require_ticket(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("acceptance Ticket identity must be non-blank")
        return normalized

    @field_validator("promoted_at_ms")
    @classmethod
    def _require_time(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("full policy promotion time must be positive")
        return value


class RuntimePolicyState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    owner_policy_id: str
    policy_version: int
    new_entry_submit_enabled: bool
    max_concurrent_tickets: int
    max_strategy_group_concurrent_tickets: int
    max_ticket_stop_risk_fraction: Decimal
    max_gross_stop_risk_fraction: Decimal
    max_ticket_initial_margin_fraction: Decimal
    max_gross_initial_margin_utilization: Decimal
    max_leverage: int
    supported_margin_mode: Literal["cross"]
    post_stop_stress_multiple: Decimal
    max_post_fill_stop_risk_overrun_fraction: Decimal


class RuntimeAuthoritySeedResult(RuntimePolicyState):
    registry_semantic_hash: str
    runtime_seed_semantic_hash: str
    registry_inserted_count: int
    runtime_inserted_count: int

    @property
    def total_inserted_count(self) -> int:
        return self.registry_inserted_count + self.runtime_inserted_count


class RuntimeDeploymentIdentityResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    runtime_commit: str
    schema_revision: TradingKernelSchemaRevision
    runtime_seed_semantic_hash: str
    refreshed_existing_authority: bool


@dataclass(frozen=True)
class _DynamicPolicy:
    max_concurrent_tickets: int
    max_strategy_group_concurrent_tickets: int
    max_ticket_stop_risk_fraction: Decimal
    max_gross_stop_risk_fraction: Decimal
    max_ticket_initial_margin_fraction: Decimal
    max_gross_initial_margin_utilization: Decimal
    max_leverage: int
    supported_margin_mode: Literal["cross"]
    post_stop_stress_multiple: Decimal
    max_post_fill_stop_risk_overrun_fraction: Decimal


@dataclass(frozen=True)
class _ExactRow:
    table: sa.Table
    identity_columns: str | tuple[str, ...]
    values: Mapping[str, Any]
    compare_keys: tuple[str, ...]


DYNAMIC_POLICY = _DynamicPolicy(
    max_concurrent_tickets=3,
    max_strategy_group_concurrent_tickets=2,
    max_ticket_stop_risk_fraction=Decimal("0.03"),
    max_gross_stop_risk_fraction=Decimal("0.06"),
    max_ticket_initial_margin_fraction=Decimal("0.45"),
    max_gross_initial_margin_utilization=Decimal("0.90"),
    max_leverage=10,
    supported_margin_mode="cross",
    post_stop_stress_multiple=Decimal("2.0"),
    max_post_fill_stop_risk_overrun_fraction=Decimal("0.10"),
)
_POLICY_COMPARE_KEYS = (
    "policy_version",
    "enabled",
    "new_entry_submit_enabled",
    "priority_rank",
    "max_concurrent_tickets",
    "max_strategy_group_concurrent_tickets",
    "max_ticket_stop_risk_fraction",
    "max_gross_stop_risk_fraction",
    "max_ticket_initial_margin_fraction",
    "max_gross_initial_margin_utilization",
    "max_leverage",
    "supported_margin_mode",
    "post_stop_stress_multiple",
    "max_post_fill_stop_risk_overrun_fraction",
    "scope",
)


def build_runtime_seed_identity(request: RuntimeAuthoritySeedRequest) -> str:
    """Compute the exact seed identity before touching PostgreSQL."""

    contracts = registered_strategy_contracts()
    return _seed_identity(
        account_id=request.account_id,
        schema_revision=request.schema_revision,
        registry_semantic_hash=build_registry_semantic_hash(contracts),
        allowed_event_spec_ids=_allowed_event_spec_ids(contracts),
    )


async def seed_runtime_authority(
    uow: PostgresKernelUnitOfWork,
    request: RuntimeAuthoritySeedRequest,
) -> RuntimeAuthoritySeedResult:
    """Install the exact observation-only authority in one transaction."""

    registry = await seed_strategy_registry(uow, seeded_at_ms=request.seeded_at_ms)
    connection = uow._require_connection()
    allowed_event_spec_ids = _allowed_event_spec_ids(registered_strategy_contracts())
    seed_identity = _seed_identity(
        account_id=request.account_id,
        schema_revision=request.schema_revision,
        registry_semantic_hash=registry.registry_semantic_hash,
        allowed_event_spec_ids=allowed_event_spec_ids,
    )
    policy = _policy_values(
        version=1,
        new_entry_submit_enabled=False,
        allowed_event_spec_ids=allowed_event_spec_ids,
        updated_at_ms=request.seeded_at_ms,
    )

    certification = {
        "stage": "observation_only",
        "seed_identity": seed_identity,
        "position_mode": POSITION_MODE,
    }
    rows = [
        _ExactRow(
            runtime_profiles,
            "runtime_profile_id",
            {
                "runtime_profile_id": RUNTIME_PROFILE_ID,
                "venue_id": VENUE_ID,
                "account_id": request.account_id,
                "environment": "live",
                "position_mode": POSITION_MODE,
                "status": "active",
                "updated_at_ms": request.seeded_at_ms,
            },
            ("venue_id", "account_id", "environment", "position_mode", "status"),
        ),
        _ExactRow(
            owner_policy_events,
            "owner_policy_event_id",
            _policy_event(
                version=1,
                operation="seed_observation_only",
                policy=policy,
                occurred_at_ms=request.seeded_at_ms,
            ),
            ("owner_policy_id", "policy_version", "operation", "payload"),
        ),
        _ExactRow(
            owner_policy_current,
            "owner_policy_id",
            policy,
            _POLICY_COMPARE_KEYS,
        ),
        _ExactRow(
            entry_lane_current,
            "lane_id",
            {
                "lane_id": GLOBAL_ENTRY_LANE_ID,
                "ticket_id": None,
                "signal_event_id": None,
                "status": "idle",
                "claimed_at_ms": None,
                "lease_until_ms": None,
                "claim_owner": None,
                "version": 0,
            },
            (
                "ticket_id",
                "signal_event_id",
                "status",
                "claimed_at_ms",
                "lease_until_ms",
                "claim_owner",
                "version",
            ),
        ),
        _ExactRow(
            account_exposure_current,
            ("venue_id", "account_id"),
            {
                "venue_id": VENUE_ID,
                "account_id": request.account_id,
                "gross_notional": Decimal(0),
                "gross_risk_at_stop": Decimal(0),
                "current_reserved_margin": Decimal(0),
                "active_ticket_count": 0,
                "projection_version": 0,
                "updated_at_ms": request.seeded_at_ms,
            },
            (
                "venue_id",
                "gross_notional",
                "gross_risk_at_stop",
                "current_reserved_margin",
                "active_ticket_count",
                "projection_version",
            ),
        ),
    ]
    rows.extend(
        _ExactRow(
            runtime_capabilities_current,
            "capability_key",
            {
                "capability_key": key,
                "enabled": enabled,
                "certified_commit": request.runtime_commit,
                "schema_revision": request.schema_revision,
                "certification": certification,
                "updated_at_ms": request.seeded_at_ms,
            },
            ("enabled", "certified_commit", "schema_revision", "certification"),
        )
        for key, enabled in (
            ("exchange_commands", False),
            ("strategy_signal_ingest", True),
        )
    )
    rows.extend(
        _ExactRow(
            schema_metadata,
            "metadata_key",
            {
                "metadata_key": key,
                "metadata_value": value,
                "updated_at_ms": request.seeded_at_ms,
            },
            ("metadata_value",),
        )
        for key, value in (
            ("registry_semantic_hash", registry.registry_semantic_hash),
            ("runtime_commit", request.runtime_commit),
            ("schema_revision", request.schema_revision),
            ("seed_identity", seed_identity),
        )
    )

    inserted = sum([await _insert_exact(connection, row) for row in rows])
    await _assert_exact_identity_set(
        connection,
        runtime_profiles,
        "runtime_profile_id",
        {RUNTIME_PROFILE_ID},
    )
    await _assert_exact_identity_set(
        connection,
        owner_policy_current,
        "owner_policy_id",
        {OWNER_POLICY_ID},
    )
    await _assert_exact_identity_set(
        connection,
        runtime_capabilities_current,
        "capability_key",
        {"exchange_commands", "strategy_signal_ingest"},
    )

    state = _policy_state(policy)
    return RuntimeAuthoritySeedResult(
        **state.model_dump(mode="python"),
        registry_semantic_hash=registry.registry_semantic_hash,
        runtime_seed_semantic_hash=seed_identity,
        registry_inserted_count=registry.total_inserted_count,
        runtime_inserted_count=inserted,
    )


async def deploy_runtime_identity(
    uow: PostgresKernelUnitOfWork,
    request: RuntimeAuthoritySeedRequest,
) -> RuntimeDeploymentIdentityResult:
    """Install fresh authority or rotate only deployment identity while flat."""

    return await _deploy_runtime_identity(uow, request)


async def deploy_compatible_upgrade_identity(
    uow: PostgresKernelUnitOfWork,
    request: RuntimeAuthoritySeedRequest,
) -> RuntimeDeploymentIdentityResult:
    """Move one exact flat v4 authority to the current Registry and schema."""

    connection = uow._require_connection()
    metadata_rows = {
        str(row["metadata_key"]): str(row["metadata_value"])
        for row in (
            await connection.execute(
                sa.select(schema_metadata).with_for_update(of=schema_metadata)
            )
        ).mappings()
    }
    if metadata_rows.get("schema_revision") == request.schema_revision:
        return await _deploy_runtime_identity(uow, request)
    if metadata_rows.get("schema_revision") != COMPATIBLE_SOURCE_SCHEMA_REVISION:
        raise RuntimeAuthorityTransitionRefused(
            "compatible identity requires the exact v4 source authority"
        )

    await _require_flat_compatible_upgrade_activity(connection)
    current_policy = dict(await _lock_policy(connection))
    current_version = int(str(current_policy["policy_version"]))
    current_submit_enabled = bool(current_policy["new_entry_submit_enabled"])
    target_event_spec_ids = _allowed_event_spec_ids(registered_strategy_contracts())
    source_event_spec_ids = tuple(
        event_spec_id.replace(
            "event_spec:SOR-001:SOR-LONG:v3",
            "event_spec:SOR-001:SOR-LONG:v2",
        ).replace(
            "event_spec:SOR-001:SOR-SHORT:v3",
            "event_spec:SOR-001:SOR-SHORT:v2",
        )
        for event_spec_id in target_event_spec_ids
    )
    if not _policy_matches(
        current_policy,
        version=current_version,
        new_entry_submit_enabled=current_submit_enabled,
        allowed_event_spec_ids=source_event_spec_ids,
    ):
        raise RuntimeAuthorityTransitionRefused(
            "compatible identity source Owner Policy differs from approved capital"
        )
    if request.seeded_at_ms <= int(str(current_policy["updated_at_ms"])):
        raise RuntimeAuthorityTransitionRefused(
            "compatible identity time must advance monotonically"
        )

    registry = await seed_strategy_registry(uow, seeded_at_ms=request.seeded_at_ms)
    seed_identity = _seed_identity(
        account_id=request.account_id,
        schema_revision=request.schema_revision,
        registry_semantic_hash=registry.registry_semantic_hash,
        allowed_event_spec_ids=target_event_spec_ids,
    )
    target_policy_version = current_version + 1
    target_policy = _policy_values(
        version=target_policy_version,
        new_entry_submit_enabled=current_submit_enabled,
        allowed_event_spec_ids=target_event_spec_ids,
        updated_at_ms=request.seeded_at_ms,
    )
    await _insert_exact(
        connection,
        _ExactRow(
            owner_policy_events,
            "owner_policy_event_id",
            _policy_event(
                version=target_policy_version,
                operation="compatible_upgrade_sor_v3",
                policy=target_policy,
                occurred_at_ms=request.seeded_at_ms,
            ),
            ("owner_policy_id", "policy_version", "operation", "payload"),
        ),
    )
    updated_policy = await connection.execute(
        sa.update(owner_policy_current)
        .where(
            owner_policy_current.c.owner_policy_id == OWNER_POLICY_ID,
            owner_policy_current.c.policy_version == current_version,
        )
        .values(target_policy)
    )
    if updated_policy.rowcount != 1:
        raise RuntimeAuthorityTransitionRefused(
            "compatible Owner Policy transition lost optimistic authority"
        )

    profile = (
        await connection.execute(
            sa.select(runtime_profiles)
            .where(runtime_profiles.c.runtime_profile_id == RUNTIME_PROFILE_ID)
            .with_for_update(of=runtime_profiles)
        )
    ).mappings().one_or_none()
    if profile is None or any(
        (
            profile["venue_id"] != VENUE_ID,
            profile["account_id"] != request.account_id,
            profile["environment"] != "live",
            profile["position_mode"] != POSITION_MODE,
            profile["status"] != "active",
        )
    ):
        raise RuntimeAuthorityTransitionRefused(
            "compatible runtime profile differs from approved identity"
        )

    capabilities = (
        await connection.execute(
            sa.select(runtime_capabilities_current).with_for_update(
                of=runtime_capabilities_current
            )
        )
    ).mappings().all()
    if {str(row["capability_key"]) for row in capabilities} != {
        "exchange_commands",
        "strategy_signal_ingest",
    }:
        raise RuntimeAuthorityTransitionRefused(
            "compatible runtime capability identities differ"
        )
    for capability in capabilities:
        certification = dict(capability["certification"])
        certification.update(
            {
                "deployment_commit": request.runtime_commit,
                "seed_identity": seed_identity,
                "stage": "compatible_upgrade",
            }
        )
        updated_capability = await connection.execute(
            sa.update(runtime_capabilities_current)
            .where(
                runtime_capabilities_current.c.capability_key
                == capability["capability_key"]
            )
            .values(
                certified_commit=request.runtime_commit,
                schema_revision=request.schema_revision,
                certification=certification,
                updated_at_ms=request.seeded_at_ms,
            )
        )
        if updated_capability.rowcount != 1:
            raise RuntimeAuthorityTransitionRefused(
                "compatible runtime capability update was lost"
            )

    metadata_targets = {
        "registry_semantic_hash": registry.registry_semantic_hash,
        "runtime_commit": request.runtime_commit,
        "schema_revision": request.schema_revision,
        "seed_identity": seed_identity,
    }
    if set(metadata_rows) != set(metadata_targets):
        raise RuntimeAuthorityTransitionRefused(
            "compatible runtime metadata identity set differs"
        )
    for key, value in metadata_targets.items():
        updated_metadata = await connection.execute(
            sa.update(schema_metadata)
            .where(schema_metadata.c.metadata_key == key)
            .values(metadata_value=value, updated_at_ms=request.seeded_at_ms)
        )
        if updated_metadata.rowcount != 1:
            raise RuntimeAuthorityTransitionRefused(
                "compatible runtime metadata update was lost"
            )

    return RuntimeDeploymentIdentityResult(
        runtime_commit=request.runtime_commit,
        schema_revision=request.schema_revision,
        runtime_seed_semantic_hash=seed_identity,
        refreshed_existing_authority=True,
    )


async def deploy_recovery_identity(
    uow: PostgresKernelUnitOfWork,
    request: RuntimeAuthoritySeedRequest,
    *,
    recovery_ticket_id: str,
) -> RuntimeDeploymentIdentityResult:
    """Rotate identity only to reconcile one zero-exposure leverage unknown."""

    normalized_ticket_id = recovery_ticket_id.strip()
    if not normalized_ticket_id:
        raise ValueError("recovery Ticket identity must be non-blank")
    return await _deploy_runtime_identity(
        uow,
        request,
        recovery_ticket_id=normalized_ticket_id,
    )


async def deploy_closure_identity(
    uow: PostgresKernelUnitOfWork,
    request: RuntimeAuthoritySeedRequest,
    *,
    closure_ticket_id: str,
) -> RuntimeDeploymentIdentityResult:
    """Rotate identity only for one exact zero-exposure pending closure Ticket."""

    normalized_ticket_id = closure_ticket_id.strip()
    if not normalized_ticket_id:
        raise ValueError("closure Ticket identity must be non-blank")
    return await _deploy_runtime_identity(
        uow,
        request,
        closure_ticket_id=normalized_ticket_id,
    )


async def _deploy_runtime_identity(
    uow: PostgresKernelUnitOfWork,
    request: RuntimeAuthoritySeedRequest,
    *,
    recovery_ticket_id: str | None = None,
    closure_ticket_id: str | None = None,
) -> RuntimeDeploymentIdentityResult:
    """Install the exact identity after a flat or narrowly safe recovery gate."""

    if sum(
        value is not None
        for value in (
            recovery_ticket_id,
            closure_ticket_id,
        )
    ) > 1:
        raise ValueError("runtime identity transition mode is ambiguous")
    connection = uow._require_connection()
    metadata_count = int(
        await connection.scalar(
            sa.select(sa.func.count()).select_from(schema_metadata)
        )
        or 0
    )
    if metadata_count == 0:
        if (
            recovery_ticket_id is not None
            or closure_ticket_id is not None
        ):
            raise RuntimeAuthorityTransitionRefused(
                "guarded identity requires an existing runtime authority"
            )
        seeded = await seed_runtime_authority(uow, request)
        return RuntimeDeploymentIdentityResult(
            runtime_commit=request.runtime_commit,
            schema_revision=request.schema_revision,
            runtime_seed_semantic_hash=seeded.runtime_seed_semantic_hash,
            refreshed_existing_authority=False,
        )

    if closure_ticket_id is not None:
        await _require_closure_identity_activity(
            connection,
            closure_ticket_id=closure_ticket_id,
            account_id=request.account_id,
        )
    elif recovery_ticket_id is None:
        await _require_zero_runtime_activity(connection)
    else:
        await _require_recovery_identity_activity(
            connection,
            recovery_ticket_id=recovery_ticket_id,
        )
    expected_registry_hash = build_registry_semantic_hash(
        registered_strategy_contracts()
    )
    expected_seed_identity = build_runtime_seed_identity(request)
    metadata_rows = {
        str(row["metadata_key"]): str(row["metadata_value"])
        for row in (
            await connection.execute(
                sa.select(schema_metadata).with_for_update(of=schema_metadata)
            )
        ).mappings()
    }
    required_metadata = {
        "registry_semantic_hash": expected_registry_hash,
        "schema_revision": request.schema_revision,
        "seed_identity": expected_seed_identity,
    }
    if any(
        metadata_rows.get(key) != value
        for key, value in required_metadata.items()
    ):
        raise RuntimeAuthoritySeedConflict(
            "runtime deployment identity differs from committed semantics"
        )

    profile = (
        await connection.execute(
            sa.select(runtime_profiles)
            .where(runtime_profiles.c.runtime_profile_id == RUNTIME_PROFILE_ID)
            .with_for_update(of=runtime_profiles)
        )
    ).mappings().one_or_none()
    if profile is None or any(
        (
            profile["venue_id"] != VENUE_ID,
            profile["account_id"] != request.account_id,
            profile["environment"] != "live",
            profile["position_mode"] != POSITION_MODE,
            profile["status"] != "active",
        )
    ):
        raise RuntimeAuthoritySeedConflict(
            "runtime profile differs from deployment identity"
        )

    capabilities = (
        await connection.execute(
            sa.select(runtime_capabilities_current).with_for_update(
                of=runtime_capabilities_current
            )
        )
    ).mappings().all()
    if {str(row["capability_key"]) for row in capabilities} != {
        "exchange_commands",
        "strategy_signal_ingest",
    }:
        raise RuntimeAuthoritySeedConflict(
            "runtime capability identities differ from deployment contract"
        )

    updated_metadata = await connection.execute(
        sa.update(schema_metadata)
        .where(schema_metadata.c.metadata_key == "runtime_commit")
        .values(
            metadata_value=request.runtime_commit,
            updated_at_ms=request.seeded_at_ms,
        )
    )
    if updated_metadata.rowcount != 1:
        raise RuntimeAuthoritySeedConflict(
            "runtime commit metadata row is missing"
        )
    for capability in capabilities:
        certification = dict(capability["certification"])
        certification["deployment_commit"] = request.runtime_commit
        updated = await connection.execute(
            sa.update(runtime_capabilities_current)
            .where(
                runtime_capabilities_current.c.capability_key
                == capability["capability_key"]
            )
            .values(
                certified_commit=request.runtime_commit,
                schema_revision=request.schema_revision,
                certification=certification,
                updated_at_ms=request.seeded_at_ms,
            )
        )
        if updated.rowcount != 1:
            raise RuntimeAuthoritySeedConflict(
                "runtime capability deployment identity update was lost"
            )
    return RuntimeDeploymentIdentityResult(
        runtime_commit=request.runtime_commit,
        schema_revision=request.schema_revision,
        runtime_seed_semantic_hash=expected_seed_identity,
        refreshed_existing_authority=True,
    )


async def arm_acceptance_policy(
    uow: PostgresKernelUnitOfWork,
    request: ArmAcceptancePolicyRequest,
) -> RuntimePolicyState:
    return await _transition_policy(
        uow,
        expected_submit=False,
        operation="arm_acceptance_ticket",
        stage="acceptance_armed",
        occurred_at_ms=request.armed_at_ms,
    )


async def promote_full_policy(
    uow: PostgresKernelUnitOfWork,
    request: PromoteFullPolicyRequest,
) -> RuntimePolicyState:
    return await _transition_policy(
        uow,
        expected_submit=True,
        operation="promote_full_runtime",
        stage="full_runtime",
        occurred_at_ms=request.promoted_at_ms,
        acceptance_ticket_id=request.acceptance_ticket_id,
    )


async def _transition_policy(
    uow: PostgresKernelUnitOfWork,
    *,
    expected_submit: bool,
    operation: str,
    stage: str,
    occurred_at_ms: int,
    acceptance_ticket_id: str | None = None,
) -> RuntimePolicyState:
    connection = uow._require_connection()
    allowed_event_spec_ids = _allowed_event_spec_ids(registered_strategy_contracts())
    current = dict(await _lock_policy(connection))
    current_version = int(str(current["policy_version"]))
    if not _policy_matches(
        current,
        version=current_version,
        new_entry_submit_enabled=expected_submit,
        allowed_event_spec_ids=allowed_event_spec_ids,
    ):
        raise RuntimeAuthorityTransitionRefused(
            "runtime policy transition is not monotonic"
        )
    if acceptance_ticket_id is not None and not await _terminal_review_exists(
        connection,
        acceptance_ticket_id,
    ):
        raise RuntimeAuthorityTransitionRefused(
            "full policy requires one terminal reviewed acceptance Ticket"
        )
    await _require_zero_runtime_activity(connection)

    target_version = current_version + 1
    target = _policy_values(
        version=target_version,
        new_entry_submit_enabled=True,
        allowed_event_spec_ids=allowed_event_spec_ids,
        updated_at_ms=occurred_at_ms,
    )
    await _insert_exact(
        connection,
        _ExactRow(
            owner_policy_events,
            "owner_policy_event_id",
            _policy_event(
                version=target_version,
                operation=operation,
                policy=target,
                occurred_at_ms=occurred_at_ms,
            ),
            ("owner_policy_id", "policy_version", "operation", "payload"),
        ),
    )
    updated = await connection.execute(
        sa.update(owner_policy_current)
        .where(
            owner_policy_current.c.owner_policy_id == OWNER_POLICY_ID,
            owner_policy_current.c.policy_version == current_version,
        )
        .values(target)
    )
    if updated.rowcount != 1:
        raise RuntimeAuthorityTransitionRefused(
            "Owner Policy transition lost optimistic authority"
        )
    await _set_exchange_command_capability(
        connection,
        stage=stage,
        updated_at_ms=occurred_at_ms,
    )
    return _policy_state(target)


def _allowed_event_spec_ids(
    contracts: tuple[RegisteredStrategyContract, ...],
) -> tuple[str, ...]:
    event_spec_ids = tuple(
        sorted(
            {
                str(contract.event_spec_id)
                for contract in contracts
            }
        )
    )
    if not event_spec_ids:
        raise RuntimeAuthoritySeedConflict("runtime policy requires registered Events")
    return event_spec_ids


def _policy_values(
    *,
    version: int,
    new_entry_submit_enabled: bool,
    allowed_event_spec_ids: tuple[str, ...],
    updated_at_ms: int,
) -> dict[str, object]:
    return {
        "owner_policy_id": OWNER_POLICY_ID,
        "policy_version": version,
        "enabled": True,
        "new_entry_submit_enabled": new_entry_submit_enabled,
        "priority_rank": 1,
        "max_concurrent_tickets": DYNAMIC_POLICY.max_concurrent_tickets,
        "max_strategy_group_concurrent_tickets": (
            DYNAMIC_POLICY.max_strategy_group_concurrent_tickets
        ),
        "max_ticket_stop_risk_fraction": (
            DYNAMIC_POLICY.max_ticket_stop_risk_fraction
        ),
        "max_gross_stop_risk_fraction": (
            DYNAMIC_POLICY.max_gross_stop_risk_fraction
        ),
        "max_ticket_initial_margin_fraction": (
            DYNAMIC_POLICY.max_ticket_initial_margin_fraction
        ),
        "max_gross_initial_margin_utilization": (
            DYNAMIC_POLICY.max_gross_initial_margin_utilization
        ),
        "max_leverage": DYNAMIC_POLICY.max_leverage,
        "supported_margin_mode": DYNAMIC_POLICY.supported_margin_mode,
        "post_stop_stress_multiple": (
            DYNAMIC_POLICY.post_stop_stress_multiple
        ),
        "max_post_fill_stop_risk_overrun_fraction": (
            DYNAMIC_POLICY.max_post_fill_stop_risk_overrun_fraction
        ),
        "scope": {
            "runtime_profile_id": RUNTIME_PROFILE_ID,
            "allowed_event_spec_ids": list(allowed_event_spec_ids),
        },
        "updated_at_ms": updated_at_ms,
    }


def _policy_event(
    *,
    version: int,
    operation: str,
    policy: Mapping[str, object],
    occurred_at_ms: int,
) -> dict[str, object]:
    return {
        "owner_policy_event_id": f"policy-event:{OWNER_POLICY_ID}:v{version}",
        "owner_policy_id": OWNER_POLICY_ID,
        "policy_version": version,
        "operation": operation,
        "payload": {
            key: str(value) if isinstance(value, Decimal) else value
            for key, value in policy.items()
            if key not in {"owner_policy_id", "updated_at_ms"}
        },
        "created_at_ms": occurred_at_ms,
    }


def _seed_identity(
    *,
    account_id: str,
    schema_revision: str,
    registry_semantic_hash: str,
    allowed_event_spec_ids: tuple[str, ...],
) -> str:
    semantics = _policy_values(
        version=1,
        new_entry_submit_enabled=False,
        allowed_event_spec_ids=allowed_event_spec_ids,
        updated_at_ms=1,
    )
    semantics.pop("updated_at_ms")
    canonical = json.dumps(
        {
            "account_id": account_id,
            "registry_semantic_hash": registry_semantic_hash,
            "runtime_profile_id": RUNTIME_PROFILE_ID,
            "schema_revision": schema_revision,
            "position_mode": POSITION_MODE,
            "acceptance_policy": semantics,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    return f"sha256:{sha256(canonical).hexdigest()}"


def _policy_matches(
    row: Mapping[str, object],
    *,
    version: int,
    new_entry_submit_enabled: bool,
    allowed_event_spec_ids: tuple[str, ...],
) -> bool:
    expected = _policy_values(
        version=version,
        new_entry_submit_enabled=new_entry_submit_enabled,
        allowed_event_spec_ids=allowed_event_spec_ids,
        updated_at_ms=int(str(row["updated_at_ms"])),
    )
    return all(row[key] == expected[key] for key in _POLICY_COMPARE_KEYS)


def _policy_state(values: Mapping[str, object]) -> RuntimePolicyState:
    supported_margin_mode = str(values["supported_margin_mode"])
    if supported_margin_mode != "cross":
        raise RuntimeError("runtime policy has unsupported margin mode")
    return RuntimePolicyState(
        owner_policy_id=str(values["owner_policy_id"]),
        policy_version=int(str(values["policy_version"])),
        new_entry_submit_enabled=bool(values["new_entry_submit_enabled"]),
        max_concurrent_tickets=int(str(values["max_concurrent_tickets"])),
        max_strategy_group_concurrent_tickets=int(
            str(values["max_strategy_group_concurrent_tickets"])
        ),
        max_ticket_stop_risk_fraction=Decimal(
            str(values["max_ticket_stop_risk_fraction"])
        ),
        max_gross_stop_risk_fraction=Decimal(
            str(values["max_gross_stop_risk_fraction"])
        ),
        max_ticket_initial_margin_fraction=Decimal(
            str(values["max_ticket_initial_margin_fraction"])
        ),
        max_gross_initial_margin_utilization=Decimal(
            str(values["max_gross_initial_margin_utilization"])
        ),
        max_leverage=int(str(values["max_leverage"])),
        supported_margin_mode=cast(Literal["cross"], supported_margin_mode),
        post_stop_stress_multiple=Decimal(
            str(values["post_stop_stress_multiple"])
        ),
        max_post_fill_stop_risk_overrun_fraction=Decimal(
            str(values["max_post_fill_stop_risk_overrun_fraction"])
        ),
    )


async def _lock_policy(connection: AsyncConnection) -> RowMapping:
    row = (
        await connection.execute(
            sa.select(owner_policy_current)
            .where(owner_policy_current.c.owner_policy_id == OWNER_POLICY_ID)
            .with_for_update(of=owner_policy_current)
        )
    ).mappings().one_or_none()
    if row is None:
        raise RuntimeAuthorityTransitionRefused("runtime Owner Policy is absent")
    return row


async def _require_zero_runtime_activity(connection: AsyncConnection) -> None:
    exposures = (
        await connection.execute(
            sa.select(account_exposure_current).with_for_update(
                of=account_exposure_current
            )
        )
    ).mappings().all()
    if len(exposures) != 1:
        raise RuntimeAuthorityTransitionRefused(
            "runtime transition requires exactly one account exposure row"
        )
    exposure = exposures[0]
    if (
        Decimal(str(exposure["gross_notional"])) != 0
        or Decimal(str(exposure["gross_risk_at_stop"])) != 0
        or Decimal(str(exposure["current_reserved_margin"])) != 0
        or int(str(exposure["active_ticket_count"])) != 0
    ):
        raise RuntimeAuthorityTransitionRefused(
            "runtime transition requires zero account exposure"
        )
    lane = (
        await connection.execute(
            sa.select(entry_lane_current)
            .where(entry_lane_current.c.lane_id == GLOBAL_ENTRY_LANE_ID)
            .with_for_update(of=entry_lane_current)
        )
    ).mappings().one_or_none()
    if (
        lane is None
        or lane["status"] != "idle"
        or lane["ticket_id"] is not None
        or lane["signal_event_id"] is not None
    ):
        raise RuntimeAuthorityTransitionRefused(
            "runtime transition requires an idle global ENTRY lane"
        )
    active_tickets = await connection.scalar(
        sa.select(sa.func.count()).select_from(trade_tickets).where(
            trade_tickets.c.terminal_at_ms.is_(None)
        )
    )
    open_incidents = await connection.scalar(
        sa.select(sa.func.count()).select_from(runtime_incidents).where(
            runtime_incidents.c.status != "resolved"
        )
    )
    unresolved_commands = await connection.scalar(
        sa.select(sa.func.count()).select_from(exchange_commands).where(
            exchange_commands.c.status.in_(
                ("prepared", "claimed", "dispatch_started", "outcome_unknown")
            )
        )
    )
    if int(active_tickets or 0) != 0:
        raise RuntimeAuthorityTransitionRefused(
            "runtime transition requires zero active Tickets"
        )
    if int(open_incidents or 0) != 0:
        raise RuntimeAuthorityTransitionRefused(
            "runtime transition requires zero open Incidents"
        )
    if int(unresolved_commands or 0) != 0:
        raise RuntimeAuthorityTransitionRefused(
            "runtime transition requires zero unresolved Exchange Commands"
        )


async def _require_flat_compatible_upgrade_activity(
    connection: AsyncConnection,
) -> None:
    await _require_zero_runtime_activity(connection)
    checks = (
        (
            await connection.scalar(
                sa.select(sa.func.count()).select_from(positions_current).where(
                    positions_current.c.quantity != 0
                )
            ),
            "compatible identity requires zero projected positions",
        ),
        (
            await connection.scalar(
                sa.select(sa.func.count()).select_from(budget_reservations).where(
                    budget_reservations.c.status == "active"
                )
            ),
            "compatible identity requires zero active Budget Reservations",
        ),
        (
            await connection.scalar(
                sa.select(sa.func.count()).select_from(trade_tickets).where(
                    trade_tickets.c.active_netting_domain_key.is_not(None)
                )
            ),
            "compatible identity requires every Netting Domain released",
        ),
        (
            await connection.scalar(
                sa.select(sa.func.count()).select_from(trade_tickets).where(
                    trade_tickets.c.terminal_at_ms.is_not(None),
                    ~sa.exists(
                        sa.select(trade_reviews.c.review_id).where(
                            trade_reviews.c.ticket_id == trade_tickets.c.ticket_id
                        )
                    ),
                )
            ),
            "compatible identity requires every terminal Ticket reviewed",
        ),
    )
    for count, message in checks:
        if int(count or 0) != 0:
            raise RuntimeAuthorityTransitionRefused(message)


async def _require_closure_identity_activity(
    connection: AsyncConnection,
    *,
    closure_ticket_id: str,
    account_id: str,
) -> None:
    active_tickets = (
        await connection.execute(
            sa.select(trade_tickets)
            .where(trade_tickets.c.terminal_at_ms.is_(None))
            .with_for_update(of=trade_tickets)
        )
    ).mappings().all()
    if {str(row["ticket_id"]) for row in active_tickets} != {closure_ticket_id}:
        raise RuntimeAuthorityTransitionRefused(
            "closure identity requires exactly one exact pending Ticket"
        )
    ticket = active_tickets[0]
    if ticket["active_netting_domain_key"] is not None:
        raise RuntimeAuthorityTransitionRefused(
            "closure identity requires a released Netting Domain"
        )

    aggregate = (
        await connection.execute(
            sa.select(trade_aggregates)
            .where(trade_aggregates.c.ticket_id == closure_ticket_id)
            .with_for_update(of=trade_aggregates)
        )
    ).mappings().one_or_none()
    if aggregate is None or any(
        (
            aggregate["status"] not in {"settlement_pending", "review_pending"},
            Decimal(str(aggregate["position_qty"])) != 0,
            Decimal(str(aggregate["protected_qty"])) != 0,
            aggregate["initial_stop_exchange_order_id"] is not None,
            aggregate["active_stop_exchange_order_id"] is not None,
            aggregate["tp1_exchange_order_id"] is not None,
            aggregate["pending_replaced_stop_exchange_order_id"] is not None,
            aggregate["pending_cancel_exchange_order_id"] is not None,
            aggregate["review_id"] is not None,
        )
    ):
        raise RuntimeAuthorityTransitionRefused(
            "closure identity requires a zero-exposure pending aggregate"
        )

    non_flat_positions = await connection.scalar(
        sa.select(sa.func.count()).select_from(positions_current).where(
            positions_current.c.quantity != 0
        )
    )
    if int(non_flat_positions or 0) != 0:
        raise RuntimeAuthorityTransitionRefused(
            "closure identity requires zero projected positions"
        )

    reservations = (
        await connection.execute(
            sa.select(budget_reservations)
            .where(budget_reservations.c.ticket_id == closure_ticket_id)
            .with_for_update(of=budget_reservations)
        )
    ).mappings().all()
    if len(reservations) != 1 or any(
        (
            reservations[0]["status"] != "released",
            reservations[0]["released_at_ms"] is None,
        )
    ):
        raise RuntimeAuthorityTransitionRefused(
            "closure identity requires a released Budget Reservation"
        )
    active_reservation_count = await connection.scalar(
        sa.select(sa.func.count()).select_from(budget_reservations).where(
            budget_reservations.c.status == "active"
        )
    )
    if int(active_reservation_count or 0) != 0:
        raise RuntimeAuthorityTransitionRefused(
            "closure identity requires zero active Budget Reservations"
        )

    exposures = (
        await connection.execute(
            sa.select(account_exposure_current).with_for_update(
                of=account_exposure_current
            )
        )
    ).mappings().all()
    if (
        len(exposures) != 1
        or exposures[0]["venue_id"] != VENUE_ID
        or exposures[0]["account_id"] != account_id
        or Decimal(str(exposures[0]["gross_notional"])) != 0
        or Decimal(str(exposures[0]["gross_risk_at_stop"])) != 0
        or Decimal(str(exposures[0]["current_reserved_margin"])) != 0
        or int(str(exposures[0]["active_ticket_count"])) != 0
    ):
        raise RuntimeAuthorityTransitionRefused(
            "closure identity requires released account capacity"
        )

    lane = (
        await connection.execute(
            sa.select(entry_lane_current)
            .where(entry_lane_current.c.lane_id == GLOBAL_ENTRY_LANE_ID)
            .with_for_update(of=entry_lane_current)
        )
    ).mappings().one_or_none()
    if (
        lane is None
        or lane["status"] != "idle"
        or lane["ticket_id"] is not None
        or lane["signal_event_id"] is not None
    ):
        raise RuntimeAuthorityTransitionRefused(
            "closure identity requires an idle global ENTRY lane"
        )

    unresolved_commands = await connection.scalar(
        sa.select(sa.func.count()).select_from(exchange_commands).where(
            exchange_commands.c.status.in_(
                ("prepared", "claimed", "dispatch_started", "outcome_unknown")
            )
        )
    )
    if int(unresolved_commands or 0) != 0:
        raise RuntimeAuthorityTransitionRefused(
            "closure identity requires zero unresolved Exchange Commands"
        )
    open_incidents = await connection.scalar(
        sa.select(sa.func.count()).select_from(runtime_incidents).where(
            runtime_incidents.c.status != "resolved"
        )
    )
    if int(open_incidents or 0) != 0:
        raise RuntimeAuthorityTransitionRefused(
            "closure identity requires zero open Incidents"
        )


async def _require_recovery_identity_activity(
    connection: AsyncConnection,
    *,
    recovery_ticket_id: str,
) -> None:
    active_ticket_count = await connection.scalar(
        sa.select(sa.func.count()).select_from(trade_tickets).where(
            trade_tickets.c.terminal_at_ms.is_(None)
        )
    )
    if int(active_ticket_count or 0) != 1:
        raise RuntimeAuthorityTransitionRefused(
            "recovery identity requires exactly one active Ticket"
        )

    ticket = (
        await connection.execute(
            sa.select(trade_tickets)
            .where(
                trade_tickets.c.ticket_id == recovery_ticket_id,
                trade_tickets.c.terminal_at_ms.is_(None),
            )
            .with_for_update(of=trade_tickets)
        )
    ).mappings().one_or_none()
    if ticket is None:
        raise RuntimeAuthorityTransitionRefused(
            "recovery identity Ticket is not the active Ticket"
        )

    aggregate = (
        await connection.execute(
            sa.select(trade_aggregates)
            .where(trade_aggregates.c.ticket_id == recovery_ticket_id)
            .with_for_update(of=trade_aggregates)
        )
    ).mappings().one_or_none()
    if aggregate is None or any(
        (
            aggregate["status"] != "leverage_outcome_unknown",
            Decimal(str(aggregate["position_qty"])) != 0,
            Decimal(str(aggregate["protected_qty"])) != 0,
            aggregate["entry_exchange_order_id"] is not None,
            aggregate["initial_stop_exchange_order_id"] is not None,
            aggregate["active_stop_exchange_order_id"] is not None,
            aggregate["tp1_exchange_order_id"] is not None,
            aggregate["exit_exchange_order_id"] is not None,
        )
    ):
        raise RuntimeAuthorityTransitionRefused(
            "recovery identity requires a zero-exposure leverage unknown"
        )

    commands = (
        await connection.execute(
            sa.select(exchange_commands)
            .where(exchange_commands.c.ticket_id == recovery_ticket_id)
            .with_for_update(of=exchange_commands)
        )
    ).mappings().all()
    if len(commands) != 1 or any(
        (
            commands[0]["command_kind"] != "set_leverage",
            commands[0]["status"] != "outcome_unknown",
            commands[0]["venue_client_order_id"] is not None,
        )
    ):
        raise RuntimeAuthorityTransitionRefused(
            "recovery identity requires one unknown SET_LEVERAGE command"
        )

    unresolved_command_count = await connection.scalar(
        sa.select(sa.func.count()).select_from(exchange_commands).where(
            exchange_commands.c.status.in_(
                ("prepared", "claimed", "dispatch_started", "outcome_unknown")
            )
        )
    )
    if int(unresolved_command_count or 0) != 1:
        raise RuntimeAuthorityTransitionRefused(
            "recovery identity permits no other unresolved Exchange Command"
        )

    incidents = (
        await connection.execute(
            sa.select(runtime_incidents)
            .where(runtime_incidents.c.status != "resolved")
            .with_for_update(of=runtime_incidents)
        )
    ).mappings().all()
    if len(incidents) != 1 or any(
        (
            incidents[0]["ticket_id"] != recovery_ticket_id,
            incidents[0]["incident_kind"] != "leverage_outcome_unknown",
            incidents[0]["entry_block_scope"] != "leverage_domain",
        )
    ):
        raise RuntimeAuthorityTransitionRefused(
            "recovery identity requires one leverage-outcome Incident"
        )

    projected_position_count = await connection.scalar(
        sa.select(sa.func.count()).select_from(positions_current).where(
            positions_current.c.ticket_id == recovery_ticket_id,
            positions_current.c.quantity != 0,
        )
    )
    if int(projected_position_count or 0) != 0:
        raise RuntimeAuthorityTransitionRefused(
            "recovery identity requires zero projected position quantity"
        )


async def _terminal_review_exists(
    connection: AsyncConnection,
    ticket_id: str,
) -> bool:
    ticket = (
        await connection.execute(
            sa.select(trade_tickets.c.ticket_id).where(
                trade_tickets.c.ticket_id == ticket_id,
                trade_tickets.c.owner_policy_id == OWNER_POLICY_ID,
                trade_tickets.c.status == "terminal",
                trade_tickets.c.terminal_at_ms.is_not(None),
                trade_tickets.c.active_netting_domain_key.is_(None),
            )
        )
    ).scalar_one_or_none()
    if ticket is None:
        return False
    review = await connection.scalar(
        sa.select(trade_reviews.c.review_id).where(
            trade_reviews.c.ticket_id == ticket_id
        )
    )
    return review is not None


async def _set_exchange_command_capability(
    connection: AsyncConnection,
    *,
    stage: str,
    updated_at_ms: int,
) -> None:
    current = (
        await connection.execute(
            sa.select(runtime_capabilities_current)
            .where(
                runtime_capabilities_current.c.capability_key
                == "exchange_commands"
            )
            .with_for_update(of=runtime_capabilities_current)
        )
    ).mappings().one_or_none()
    if current is None:
        raise RuntimeAuthorityTransitionRefused(
            "exchange command capability is absent"
        )
    certification = dict(current["certification"])
    certification["stage"] = stage
    updated = await connection.execute(
        sa.update(runtime_capabilities_current)
        .where(
            runtime_capabilities_current.c.capability_key == "exchange_commands"
        )
        .values(
            enabled=True,
            certification=certification,
            updated_at_ms=updated_at_ms,
        )
    )
    if updated.rowcount != 1:
        raise RuntimeAuthorityTransitionRefused(
            "exchange command capability update lost authority"
        )


async def _insert_exact(connection: AsyncConnection, row: _ExactRow) -> int:
    identity_columns = (
        (row.identity_columns,)
        if isinstance(row.identity_columns, str)
        else row.identity_columns
    )
    predicate = sa.and_(
        *(row.table.c[column] == row.values[column] for column in identity_columns)
    )
    existing = (
        await connection.execute(
            sa.select(row.table)
            .where(predicate)
            .limit(1)
        )
    ).mappings().one_or_none()
    if existing is None:
        await connection.execute(sa.insert(row.table).values(dict(row.values)))
        return 1
    if not all(existing[key] == row.values[key] for key in row.compare_keys):
        raise RuntimeAuthoritySeedConflict(
            "runtime authority conflict for "
            + ":".join(str(row.values[column]) for column in identity_columns)
        )
    return 0


async def _assert_exact_identity_set(
    connection: AsyncConnection,
    table: sa.Table,
    identity_column: str,
    expected: set[str],
) -> None:
    actual = {
        str(value)
        for value in (
            await connection.execute(sa.select(table.c[identity_column]))
        ).scalars()
    }
    if actual != expected:
        raise RuntimeAuthoritySeedConflict(
            f"runtime authority identity set differs for {table.name}"
        )
