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

from src.trading_kernel.domain.capacity import FamilyTicketLimits
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
    owner_authorizations,
    owner_policy_current,
    owner_policy_events,
    positions_current,
    runtime_capabilities_current,
    runtime_incidents,
    runtime_profiles,
    schema_metadata,
    strategy_entry_control_events,
    strategy_entry_controls_current,
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
TRADFI_RUNTIME_PROFILE_ID = "tradfi-equity-usdm-v1"
GLOBAL_ENTRY_LANE_ID = "global-entry"
VENUE_ID = "binance-usdm"
POSITION_MODE = "independent_sides"
COMPATIBLE_SOURCE_SCHEMA_REVISION = "0002_sor_v3_strategy_group_capacity"
OWNER_CONTROL_SOURCE_SCHEMA_REVISION = "0003_portfolio_admission_observability"
TRADFI_INSTRUMENT_SOURCE_SCHEMA_REVISION = "0004_owner_control_plane"
DYNAMIC_SELECTION_SOURCE_SCHEMA_REVISION = "0005_tradfi_instrument_center"
_RUNTIME_FENCE_INCIDENT_ID = "incident:runtime-fence"
_RUNTIME_FENCE_INCIDENT_KIND = "runtime_identity_mismatch"
_PRESERVATION_METADATA_KEYS = frozenset(
    {
        "preservation_source_revision",
        "preservation_target_revision",
        "preservation_digest",
        "preservation_database_identity",
        "preservation_proof_digest",
    }
)


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
    family_ticket_limits: FamilyTicketLimits
    max_ticket_stop_risk_fraction: Decimal
    max_gross_stop_risk_fraction: Decimal
    max_ticket_initial_margin_fraction: Decimal
    max_gross_initial_margin_utilization: Decimal
    directional_stop_risk_limit_fraction: Decimal
    min_materialization_ratio: Decimal
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
    family_ticket_limits: FamilyTicketLimits
    max_ticket_stop_risk_fraction: Decimal
    max_gross_stop_risk_fraction: Decimal
    max_ticket_initial_margin_fraction: Decimal
    max_gross_initial_margin_utilization: Decimal
    directional_stop_risk_limit_fraction: Decimal
    min_materialization_ratio: Decimal
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
    family_ticket_limits=FamilyTicketLimits(
        long_continuation=1,
        opening_range=2,
        rally_failure_short=1,
    ),
    max_ticket_stop_risk_fraction=Decimal("0.02"),
    max_gross_stop_risk_fraction=Decimal("0.06"),
    max_ticket_initial_margin_fraction=Decimal("0.30"),
    max_gross_initial_margin_utilization=Decimal("0.90"),
    directional_stop_risk_limit_fraction=Decimal("0.04"),
    min_materialization_ratio=Decimal("0.50"),
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
    "family_ticket_limits",
    "max_ticket_stop_risk_fraction",
    "max_gross_stop_risk_fraction",
    "max_ticket_initial_margin_fraction",
    "max_gross_initial_margin_utilization",
    "directional_stop_risk_limit_fraction",
    "min_materialization_ratio",
    "max_leverage",
    "supported_margin_mode",
    "post_stop_stress_multiple",
    "max_post_fill_stop_risk_overrun_fraction",
    "scope",
)


def build_runtime_seed_identity(request: RuntimeAuthoritySeedRequest) -> str:
    """Compute the exact seed identity before touching PostgreSQL."""

    contracts = _contracts_for_schema(request.schema_revision)
    include_tradfi = _schema_includes_tradfi(request.schema_revision)
    return _seed_identity(
        account_id=request.account_id,
        schema_revision=request.schema_revision,
        registry_semantic_hash=build_registry_semantic_hash(contracts),
        allowed_event_spec_ids=_allowed_event_spec_ids(contracts),
        include_tradfi=include_tradfi,
    )


async def seed_runtime_authority(
    uow: PostgresKernelUnitOfWork,
    request: RuntimeAuthoritySeedRequest,
) -> RuntimeAuthoritySeedResult:
    """Install the exact observation-only authority in one transaction."""

    contracts = _contracts_for_schema(request.schema_revision)
    include_tradfi = _schema_includes_tradfi(request.schema_revision)
    registry = await seed_strategy_registry(
        uow,
        seeded_at_ms=request.seeded_at_ms,
        contracts=contracts,
        include_product_compatibility=include_tradfi,
    )
    connection = uow._require_connection()
    control_inserted_count = 0
    if request.schema_revision in {
        "0004_owner_control_plane",
        "0005_tradfi_instrument_center",
        "0006_sor_dynamic_selection_v0",
    }:
        control_inserted_count = await _seed_strategy_entry_controls(
            connection,
            seeded_at_ms=request.seeded_at_ms,
            strategy_group_ids=tuple(
                sorted({contract.strategy_group_id for contract in contracts})
            ),
        )
    allowed_event_spec_ids = _allowed_event_spec_ids(contracts)
    seed_identity = _seed_identity(
        account_id=request.account_id,
        schema_revision=request.schema_revision,
        registry_semantic_hash=registry.registry_semantic_hash,
        allowed_event_spec_ids=allowed_event_spec_ids,
        include_tradfi=include_tradfi,
    )
    policy_builder = _policy_values if include_tradfi else _crypto_source_policy_values
    policy = policy_builder(
        version=1,
        new_entry_submit_enabled=False,
        allowed_event_spec_ids=allowed_event_spec_ids,
        updated_at_ms=request.seeded_at_ms,
    )

    certification = {
        "stage": "entry_paused" if include_tradfi else "observation_only",
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
                operation=(
                    "seed_entry_paused"
                    if include_tradfi
                    else "seed_observation_only"
                ),
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
    if include_tradfi:
        rows.extend(
            _tradfi_runtime_rows(
                account_id=request.account_id,
                seeded_at_ms=request.seeded_at_ms,
            )
        )
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
        (
            {RUNTIME_PROFILE_ID, TRADFI_RUNTIME_PROFILE_ID}
            if include_tradfi
            else {RUNTIME_PROFILE_ID}
        ),
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
        runtime_inserted_count=inserted + control_inserted_count,
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
    """Rotate one exact migrated Policy v4 authority to current identity."""

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
        return await _deploy_runtime_identity(
            uow,
            request,
            allow_compatible_runtime_fence=True,
        )
    source_schema_revision = metadata_rows.get("schema_revision")
    if source_schema_revision == DYNAMIC_SELECTION_SOURCE_SCHEMA_REVISION:
        return await _deploy_dynamic_selection_compatible_identity(
            uow,
            request=request,
            metadata_rows=metadata_rows,
        )
    if source_schema_revision not in {
        COMPATIBLE_SOURCE_SCHEMA_REVISION,
        OWNER_CONTROL_SOURCE_SCHEMA_REVISION,
        TRADFI_INSTRUMENT_SOURCE_SCHEMA_REVISION,
    }:
        raise RuntimeAuthorityTransitionRefused(
            "compatible identity requires an approved flat source authority"
        )

    await _require_flat_compatible_upgrade_activity(
        connection,
        allow_compatible_runtime_fence=True,
    )
    current_policy = dict(await _lock_policy(connection))
    target_event_spec_ids = _allowed_event_spec_ids(registered_strategy_contracts())
    source_event_spec_ids = _allowed_event_spec_ids(_crypto_strategy_contracts())
    current_policy_version = int(str(current_policy["policy_version"]))
    expected_policy_version = (
        4
        if source_schema_revision == COMPATIBLE_SOURCE_SCHEMA_REVISION
        else current_policy_version
    )
    source_entry_enabled = bool(current_policy["new_entry_submit_enabled"])
    expected_source_entry_enabled = (
        False
        if source_schema_revision == COMPATIBLE_SOURCE_SCHEMA_REVISION
        else source_entry_enabled
    )
    if not _crypto_source_policy_matches(
        current_policy,
        version=expected_policy_version,
        new_entry_submit_enabled=expected_source_entry_enabled,
        allowed_event_spec_ids=source_event_spec_ids,
    ) or (
        source_schema_revision == COMPATIBLE_SOURCE_SCHEMA_REVISION
        and current_policy["max_strategy_group_concurrent_tickets"] is not None
    ):
        raise RuntimeAuthorityTransitionRefused(
            "compatible identity requires exact paused source Policy"
        )
    if (
        source_schema_revision == COMPATIBLE_SOURCE_SCHEMA_REVISION
        and source_entry_enabled
    ):
        raise RuntimeAuthorityTransitionRefused(
            "compatible identity cannot re-enable new ENTRY"
        )
    if request.seeded_at_ms <= int(str(current_policy["updated_at_ms"])):
        raise RuntimeAuthorityTransitionRefused(
            "compatible identity time must advance monotonically"
        )

    compatible_registry_hash = build_registry_semantic_hash(
        _crypto_strategy_contracts()
    )
    registry = await seed_strategy_registry(
        uow,
        seeded_at_ms=request.seeded_at_ms,
        compatible_source_registry_semantic_hash=(
            compatible_registry_hash
            if source_schema_revision
            in {
                COMPATIBLE_SOURCE_SCHEMA_REVISION,
                OWNER_CONTROL_SOURCE_SCHEMA_REVISION,
                TRADFI_INSTRUMENT_SOURCE_SCHEMA_REVISION,
            }
            else None
        ),
    )
    if source_schema_revision in {
        COMPATIBLE_SOURCE_SCHEMA_REVISION,
        OWNER_CONTROL_SOURCE_SCHEMA_REVISION,
    }:
        await _seed_strategy_entry_controls(
            connection,
            seeded_at_ms=request.seeded_at_ms,
        )
    else:
        await _seed_strategy_entry_controls(
            connection,
            seeded_at_ms=request.seeded_at_ms,
            strategy_group_ids=("SOR-US-EQ-PERP-001",),
            assert_exact_identity_set=False,
        )
    if source_entry_enabled:
        current_policy = await _pause_entry_for_compatible_upgrade(
            connection,
            current_policy=current_policy,
            occurred_at_ms=request.seeded_at_ms,
            runtime_commit=request.runtime_commit,
            operation=(
                "tradfi_instrument_upgrade_pause_entry"
                if source_schema_revision
                == TRADFI_INSTRUMENT_SOURCE_SCHEMA_REVISION
                else "owner_control_upgrade_pause_entry"
            ),
            event_namespace=(
                "tradfi-instrument-upgrade"
                if source_schema_revision
                == TRADFI_INSTRUMENT_SOURCE_SCHEMA_REVISION
                else "owner-control-upgrade"
            ),
        )
        expected_policy_version = int(str(current_policy["policy_version"]))

    current_policy = await _expand_policy_for_tradfi(
        connection,
        current_policy=current_policy,
        allowed_event_spec_ids=target_event_spec_ids,
        occurred_at_ms=request.seeded_at_ms,
    )
    expected_policy_version = int(str(current_policy["policy_version"]))

    for row in _tradfi_runtime_rows(
        account_id=request.account_id,
        seeded_at_ms=request.seeded_at_ms,
    ):
        await _insert_exact(connection, row)
    await _assert_exact_identity_set(
        connection,
        runtime_profiles,
        "runtime_profile_id",
        {RUNTIME_PROFILE_ID, TRADFI_RUNTIME_PROFILE_ID},
    )
    await _assert_exact_identity_set(
        connection,
        owner_policy_current,
        "owner_policy_id",
        {OWNER_POLICY_ID},
    )
    await _assert_exact_identity_set(
        connection,
        strategy_entry_controls_current,
        "strategy_group_id",
        {
            contract.strategy_group_id
            for contract in registered_strategy_contracts()
        },
    )
    seed_identity = _seed_identity(
        account_id=request.account_id,
        schema_revision=request.schema_revision,
        registry_semantic_hash=registry.registry_semantic_hash,
        allowed_event_spec_ids=target_event_spec_ids,
        include_tradfi=True,
    )
    if not _policy_matches(
        current_policy,
        version=expected_policy_version,
        new_entry_submit_enabled=False,
        allowed_event_spec_ids=target_event_spec_ids,
    ):
        raise RuntimeAuthorityTransitionRefused(
            "compatible identity Registry seed changed migrated Policy authority"
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
    metadata_keys = frozenset(metadata_rows)
    identity_keys = frozenset(metadata_targets)
    if metadata_keys not in {
        identity_keys,
        identity_keys | _PRESERVATION_METADATA_KEYS,
    }:
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

    await _resolve_compatible_runtime_fence(
        connection,
        resolved_at_ms=request.seeded_at_ms,
    )

    return RuntimeDeploymentIdentityResult(
        runtime_commit=request.runtime_commit,
        schema_revision=request.schema_revision,
        runtime_seed_semantic_hash=seed_identity,
        refreshed_existing_authority=True,
    )


async def _deploy_dynamic_selection_compatible_identity(
    uow: PostgresKernelUnitOfWork,
    *,
    request: RuntimeAuthoritySeedRequest,
    metadata_rows: Mapping[str, str],
) -> RuntimeDeploymentIdentityResult:
    """Rotate a flat 0005 authority into 0006 without replacing source facts.

    Dynamic Selection is a capability upgrade: the full Registry, Policy
    scope, RuntimeProfiles and static StrategyUniverse pair are already
    authoritative source facts. The release must only fence new ENTRY and
    rotate the certified runtime identity after the forward migration.
    """

    connection = uow._require_connection()
    await _require_flat_compatible_upgrade_activity(
        connection,
        allow_compatible_runtime_fence=True,
    )
    current_policy = dict(await _lock_policy(connection))
    target_event_spec_ids = _allowed_event_spec_ids(registered_strategy_contracts())
    source_entry_enabled = bool(current_policy["new_entry_submit_enabled"])
    current_policy_version = int(str(current_policy["policy_version"]))
    if not _policy_matches(
        current_policy,
        version=current_policy_version,
        new_entry_submit_enabled=source_entry_enabled,
        allowed_event_spec_ids=target_event_spec_ids,
    ):
        raise RuntimeAuthorityTransitionRefused(
            "Dynamic Selection identity requires exact full source Policy"
        )
    if request.seeded_at_ms <= int(str(current_policy["updated_at_ms"])):
        raise RuntimeAuthorityTransitionRefused(
            "Dynamic Selection identity time must advance monotonically"
        )

    if source_entry_enabled:
        current_policy = await _pause_entry_for_compatible_upgrade(
            connection,
            current_policy=current_policy,
            occurred_at_ms=request.seeded_at_ms,
            runtime_commit=request.runtime_commit,
            operation="dynamic_selection_upgrade_pause_entry",
            event_namespace="dynamic-selection-upgrade",
        )
    else:
        current_policy = dict(current_policy)
    registry = await seed_strategy_registry(
        uow,
        seeded_at_ms=request.seeded_at_ms,
    )
    expected_policy_version = int(str(current_policy["policy_version"]))
    if not _policy_matches(
        current_policy,
        version=expected_policy_version,
        new_entry_submit_enabled=False,
        allowed_event_spec_ids=target_event_spec_ids,
    ):
        raise RuntimeAuthorityTransitionRefused(
            "Dynamic Selection identity changed migrated Policy authority"
        )
    await _assert_exact_identity_set(
        connection,
        runtime_profiles,
        "runtime_profile_id",
        {RUNTIME_PROFILE_ID, TRADFI_RUNTIME_PROFILE_ID},
    )
    await _assert_exact_identity_set(
        connection,
        strategy_entry_controls_current,
        "strategy_group_id",
        {
            contract.strategy_group_id
            for contract in registered_strategy_contracts()
        },
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
            "Dynamic Selection runtime capability identities differ"
        )
    seed_identity = _seed_identity(
        account_id=request.account_id,
        schema_revision=request.schema_revision,
        registry_semantic_hash=registry.registry_semantic_hash,
        allowed_event_spec_ids=target_event_spec_ids,
        include_tradfi=True,
    )
    for capability in capabilities:
        certification = dict(capability["certification"])
        certification.update(
            {
                "deployment_commit": request.runtime_commit,
                "seed_identity": seed_identity,
                "stage": "compatible_dynamic_selection_upgrade",
            }
        )
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
            raise RuntimeAuthorityTransitionRefused(
                "Dynamic Selection runtime capability update was lost"
            )
    metadata_targets = {
        "registry_semantic_hash": registry.registry_semantic_hash,
        "runtime_commit": request.runtime_commit,
        "schema_revision": request.schema_revision,
        "seed_identity": seed_identity,
    }
    metadata_keys = frozenset(metadata_rows)
    identity_keys = frozenset(metadata_targets)
    if metadata_keys not in {
        identity_keys,
        identity_keys | _PRESERVATION_METADATA_KEYS,
    }:
        raise RuntimeAuthorityTransitionRefused(
            "Dynamic Selection runtime metadata identity set differs"
        )
    for key, value in metadata_targets.items():
        updated = await connection.execute(
            sa.update(schema_metadata)
            .where(schema_metadata.c.metadata_key == key)
            .values(metadata_value=value, updated_at_ms=request.seeded_at_ms)
        )
        if updated.rowcount != 1:
            raise RuntimeAuthorityTransitionRefused(
                "Dynamic Selection runtime metadata update was lost"
            )
    await _resolve_compatible_runtime_fence(
        connection,
        resolved_at_ms=request.seeded_at_ms,
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
    allow_compatible_runtime_fence: bool = False,
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
        await _require_zero_runtime_activity(
            connection,
            allow_compatible_runtime_fence=allow_compatible_runtime_fence,
        )
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
    if allow_compatible_runtime_fence:
        await _resolve_compatible_runtime_fence(
            connection,
            resolved_at_ms=request.seeded_at_ms,
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
    schema_revision = await connection.scalar(
        sa.select(schema_metadata.c.metadata_value).where(
            schema_metadata.c.metadata_key == "schema_revision"
        )
    )
    include_tradfi = _schema_includes_tradfi(str(schema_revision))
    allowed_event_spec_ids = _allowed_event_spec_ids(
        registered_strategy_contracts()
        if include_tradfi
        else _crypto_strategy_contracts()
    )
    current = dict(await _lock_policy(connection))
    current_version = int(str(current["policy_version"]))
    matcher = _policy_matches if include_tradfi else _crypto_source_policy_matches
    if not matcher(
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
    policy_builder = _policy_values if include_tradfi else _crypto_source_policy_values
    target = policy_builder(
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
            {str(contract.event_spec_id) for contract in contracts}
        )
    )
    if not event_spec_ids:
        raise RuntimeAuthoritySeedConflict("runtime policy requires registered Events")
    return event_spec_ids


def _crypto_strategy_contracts() -> tuple[RegisteredStrategyContract, ...]:
    return tuple(
        contract
        for contract in registered_strategy_contracts()
        if contract.strategy_group_id != "SOR-US-EQ-PERP-001"
    )


def _contracts_for_schema(
    schema_revision: TradingKernelSchemaRevision,
) -> tuple[RegisteredStrategyContract, ...]:
    if _schema_includes_tradfi(schema_revision):
        return registered_strategy_contracts()
    return _crypto_strategy_contracts()


def _schema_includes_tradfi(schema_revision: str) -> bool:
    return schema_revision in {
        "0005_tradfi_instrument_center",
        "0006_sor_dynamic_selection_v0",
    }


def _tradfi_event_spec_ids() -> tuple[str, ...]:
    event_spec_ids = tuple(
        sorted(
            contract.event_spec_id
            for contract in registered_strategy_contracts()
            if contract.strategy_group_id == "SOR-US-EQ-PERP-001"
        )
    )
    if len(event_spec_ids) != 2:
        raise RuntimeAuthoritySeedConflict(
            "TradFi observation policy requires exactly two Events"
        )
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
        "family_ticket_limits": DYNAMIC_POLICY.family_ticket_limits.model_dump(),
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
        "directional_stop_risk_limit_fraction": (
            DYNAMIC_POLICY.directional_stop_risk_limit_fraction
        ),
        "min_materialization_ratio": DYNAMIC_POLICY.min_materialization_ratio,
        "max_leverage": DYNAMIC_POLICY.max_leverage,
        "supported_margin_mode": DYNAMIC_POLICY.supported_margin_mode,
        "post_stop_stress_multiple": (
            DYNAMIC_POLICY.post_stop_stress_multiple
        ),
        "max_post_fill_stop_risk_overrun_fraction": (
            DYNAMIC_POLICY.max_post_fill_stop_risk_overrun_fraction
        ),
        "scope": {
            "event_runtime_profiles": [
                {
                    "event_spec_id": event_spec_id,
                    "runtime_profile_id": (
                        TRADFI_RUNTIME_PROFILE_ID
                        if event_spec_id in _tradfi_event_spec_ids()
                        else RUNTIME_PROFILE_ID
                    ),
                }
                for event_spec_id in allowed_event_spec_ids
            ]
        },
        "updated_at_ms": updated_at_ms,
    }


def _crypto_source_policy_values(
    *,
    version: int,
    new_entry_submit_enabled: bool,
    allowed_event_spec_ids: tuple[str, ...],
    updated_at_ms: int,
) -> dict[str, object]:
    values = _policy_values(
        version=version,
        new_entry_submit_enabled=new_entry_submit_enabled,
        allowed_event_spec_ids=allowed_event_spec_ids,
        updated_at_ms=updated_at_ms,
    )
    values["scope"] = {
        "runtime_profile_id": RUNTIME_PROFILE_ID,
        "allowed_event_spec_ids": list(allowed_event_spec_ids),
    }
    return values


def _tradfi_runtime_rows(
    *,
    account_id: str,
    seeded_at_ms: int,
) -> tuple[_ExactRow, ...]:
    return (
        _ExactRow(
            runtime_profiles,
            "runtime_profile_id",
            {
                "runtime_profile_id": TRADFI_RUNTIME_PROFILE_ID,
                "venue_id": VENUE_ID,
                "account_id": account_id,
                "environment": "live",
                "position_mode": POSITION_MODE,
                "status": "active",
                "updated_at_ms": seeded_at_ms,
            },
            ("venue_id", "account_id", "environment", "position_mode", "status"),
        ),
    )


def _policy_event(
    *,
    version: int,
    operation: str,
    policy: Mapping[str, object],
    occurred_at_ms: int,
    owner_policy_id: str = OWNER_POLICY_ID,
) -> dict[str, object]:
    return {
        "owner_policy_event_id": f"policy-event:{owner_policy_id}:v{version}",
        "owner_policy_id": owner_policy_id,
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
    include_tradfi: bool,
) -> str:
    policy_builder = _policy_values if include_tradfi else _crypto_source_policy_values
    semantics = policy_builder(
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
            "runtime_profile_ids": [
                RUNTIME_PROFILE_ID,
                *([TRADFI_RUNTIME_PROFILE_ID] if include_tradfi else []),
            ],
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


def _crypto_source_policy_matches(
    row: Mapping[str, object],
    *,
    version: int,
    new_entry_submit_enabled: bool,
    allowed_event_spec_ids: tuple[str, ...],
) -> bool:
    expected = _crypto_source_policy_values(
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
        family_ticket_limits=FamilyTicketLimits.model_validate(
            values["family_ticket_limits"]
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
        directional_stop_risk_limit_fraction=Decimal(
            str(values["directional_stop_risk_limit_fraction"])
        ),
        min_materialization_ratio=Decimal(
            str(values["min_materialization_ratio"])
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


async def _require_zero_runtime_activity(
    connection: AsyncConnection,
    *,
    allow_compatible_runtime_fence: bool = False,
) -> None:
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
    open_incidents = (
        await connection.execute(
            sa.select(runtime_incidents).where(
                runtime_incidents.c.status != "resolved"
            ).with_for_update(of=runtime_incidents)
        )
    ).mappings().all()
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
    exact_runtime_fence = bool(
        len(open_incidents) == 1
        and open_incidents[0]["incident_id"] == _RUNTIME_FENCE_INCIDENT_ID
        and open_incidents[0]["ticket_id"] is None
        and open_incidents[0]["incident_kind"] == _RUNTIME_FENCE_INCIDENT_KIND
        and open_incidents[0]["first_blocker"] == _RUNTIME_FENCE_INCIDENT_KIND
        and open_incidents[0]["entry_block_scope"] == "runtime"
        and open_incidents[0]["entry_block_key"] == "global"
    )
    if open_incidents and not (
        allow_compatible_runtime_fence and exact_runtime_fence
    ):
        raise RuntimeAuthorityTransitionRefused(
            "runtime transition requires zero open Incidents"
        )
    if int(unresolved_commands or 0) != 0:
        raise RuntimeAuthorityTransitionRefused(
            "runtime transition requires zero unresolved Exchange Commands"
        )


async def _require_flat_compatible_upgrade_activity(
    connection: AsyncConnection,
    *,
    allow_compatible_runtime_fence: bool = False,
) -> None:
    await _require_zero_runtime_activity(
        connection,
        allow_compatible_runtime_fence=allow_compatible_runtime_fence,
    )
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
                sa.select(sa.func.count())
                .select_from(
                    trade_tickets.join(
                        trade_aggregates,
                        trade_aggregates.c.ticket_id == trade_tickets.c.ticket_id,
                    )
                )
                .where(
                    trade_tickets.c.terminal_at_ms.is_not(None),
                    trade_tickets.c.status == "terminal",
                    trade_aggregates.c.status == "terminal",
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


async def _resolve_compatible_runtime_fence(
    connection: AsyncConnection,
    *,
    resolved_at_ms: int,
) -> None:
    await connection.execute(
        sa.update(runtime_incidents)
        .where(
            runtime_incidents.c.incident_id == _RUNTIME_FENCE_INCIDENT_ID,
            runtime_incidents.c.incident_kind == _RUNTIME_FENCE_INCIDENT_KIND,
            runtime_incidents.c.status == "open",
            runtime_incidents.c.ticket_id.is_(None),
            runtime_incidents.c.first_blocker == _RUNTIME_FENCE_INCIDENT_KIND,
            runtime_incidents.c.entry_block_scope == "runtime",
            runtime_incidents.c.entry_block_key == "global",
        )
        .values(status="resolved", resolved_at_ms=resolved_at_ms)
    )


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


async def _seed_strategy_entry_controls(
    connection: AsyncConnection,
    *,
    seeded_at_ms: int,
    strategy_group_ids: tuple[str, ...] | None = None,
    assert_exact_identity_set: bool = True,
) -> int:
    """Install controls; TradFi SOR starts paused until postflight resume."""

    selected_group_ids = (
        tuple(
            sorted(
                {item.strategy_group_id for item in registered_strategy_contracts()}
            )
        )
        if strategy_group_ids is None
        else tuple(sorted(strategy_group_ids))
    )
    inserted = 0
    for strategy_group_id in selected_group_ids:
        paused = strategy_group_id == "SOR-US-EQ-PERP-001"
        authorization_id = f"owner-authorization:seed:{strategy_group_id}"
        event_id = f"strategy-control-event:seed:{strategy_group_id}"
        inserted += await _insert_exact(
            connection,
            _ExactRow(
                owner_authorizations,
                "authorization_id",
                {
                    "authorization_id": authorization_id,
                    "purpose": "strategy_pause" if paused else "strategy_resume",
                    "owner_identity": "system-seed",
                    "authentication_strength": "session",
                    "request_digest": "sha256:" + "0" * 64,
                    "target_scope": {"seed": True},
                    "idempotency_key": f"owner-request:seed:{strategy_group_id}",
                    "authorized_at_ms": seeded_at_ms,
                },
                (
                    "purpose",
                    "owner_identity",
                    "authentication_strength",
                    "request_digest",
                    "target_scope",
                    "idempotency_key",
                ),
            ),
        )
        inserted += await _insert_exact(
            connection,
            _ExactRow(
                strategy_entry_control_events,
                "strategy_entry_control_event_id",
                {
                    "strategy_entry_control_event_id": event_id,
                    "strategy_group_id": strategy_group_id,
                    "control_version": 1,
                    "operation": "pause" if paused else "resume",
                    "target_state": "paused" if paused else "enabled",
                    "authorization_id": authorization_id,
                    "reason": "seed_deployment_paused" if paused else "seed_enabled",
                    "payload": {},
                    "created_at_ms": seeded_at_ms,
                },
                (
                    "strategy_group_id",
                    "control_version",
                    "operation",
                    "target_state",
                    "authorization_id",
                    "reason",
                    "payload",
                ),
            ),
        )
        inserted += await _insert_exact(
            connection,
            _ExactRow(
                strategy_entry_controls_current,
                "strategy_group_id",
                {
                    "strategy_group_id": strategy_group_id,
                    "entry_state": "paused" if paused else "enabled",
                    "control_version": 1,
                    "last_event_id": event_id,
                    "reason": "seed_deployment_paused" if paused else "seed_enabled",
                    "updated_at_ms": seeded_at_ms,
                },
                (
                    "entry_state",
                    "control_version",
                    "last_event_id",
                    "reason",
                ),
            ),
        )
    if assert_exact_identity_set:
        await _assert_exact_identity_set(
            connection,
            strategy_entry_controls_current,
            "strategy_group_id",
            set(selected_group_ids),
        )
    return inserted


async def _pause_entry_for_compatible_upgrade(
    connection: AsyncConnection,
    *,
    current_policy: Mapping[str, object],
    occurred_at_ms: int,
    runtime_commit: str,
    operation: str,
    event_namespace: str,
) -> dict[str, object]:
    """Atomically retain a flat upgrade with new ENTRY paused and audited."""

    current_version = int(str(current_policy["policy_version"]))
    target_version = current_version + 1
    event_id = f"owner-policy-event:{event_namespace}:{target_version}"
    await _insert_exact(
        connection,
        _ExactRow(
            owner_policy_events,
            "owner_policy_event_id",
            {
                "owner_policy_event_id": event_id,
                "owner_policy_id": OWNER_POLICY_ID,
                "policy_version": target_version,
                "operation": operation,
                "payload": {
                    "runtime_commit": runtime_commit,
                    "new_entry_submit_enabled": False,
                },
                "created_at_ms": occurred_at_ms,
            },
            (
                "owner_policy_id",
                "policy_version",
                "operation",
                "payload",
            ),
        ),
    )
    updated = await connection.execute(
        sa.update(owner_policy_current)
        .where(
            owner_policy_current.c.owner_policy_id == OWNER_POLICY_ID,
            owner_policy_current.c.policy_version == current_version,
            owner_policy_current.c.new_entry_submit_enabled.is_(True),
        )
        .values(
            policy_version=target_version,
            new_entry_submit_enabled=False,
            updated_at_ms=occurred_at_ms,
        )
        .returning(owner_policy_current)
    )
    row = updated.mappings().one_or_none()
    if row is None:
        raise RuntimeAuthorityTransitionRefused(
            "owner-control upgrade lost the ENTRY pause transition"
        )
    return dict(row)


async def _expand_policy_for_tradfi(
    connection: AsyncConnection,
    *,
    current_policy: Mapping[str, object],
    allowed_event_spec_ids: tuple[str, ...],
    occurred_at_ms: int,
) -> dict[str, object]:
    """Create one new paused Policy version with exact multi-profile scope."""

    current_version = int(str(current_policy["policy_version"]))
    target = _policy_values(
        version=current_version + 1,
        new_entry_submit_enabled=False,
        allowed_event_spec_ids=allowed_event_spec_ids,
        updated_at_ms=occurred_at_ms,
    )
    await _insert_exact(
        connection,
        _ExactRow(
            owner_policy_events,
            "owner_policy_event_id",
            _policy_event(
                version=current_version + 1,
                operation="tradfi_live_policy_scope_expanded",
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
            owner_policy_current.c.new_entry_submit_enabled.is_(False),
        )
        .values(target)
        .returning(owner_policy_current)
    )
    row = updated.mappings().one_or_none()
    if row is None:
        raise RuntimeAuthorityTransitionRefused(
            "TradFi Policy scope expansion lost optimistic authority"
        )
    return dict(row)


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
