"""Exact Tokyo runtime authority seed and monotonic policy transitions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator
import sqlalchemy as sa
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

from src.trading_kernel.domain.strategy_registry import (
    build_registry_semantic_hash,
    registered_strategy_contracts,
)
from src.trading_kernel.infrastructure.pg_models import (
    account_exposure_current,
    entry_lane_current,
    owner_policy_current,
    owner_policy_events,
    runtime_capabilities_current,
    runtime_incidents,
    runtime_profiles,
    runtime_scopes_current,
    schema_metadata,
    trade_reviews,
    trade_tickets,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.strategy_registry_seed import (
    seed_strategy_registry,
)


RUNTIME_PROFILE_ID = "tiny-live-v1"
OWNER_POLICY_ID = "policy-main"
GLOBAL_ENTRY_LANE_ID = "global-entry"
VENUE_ID = "binance-usdm"
POSITION_MODE = "independent_sides"


class RuntimeAuthoritySeedConflict(RuntimeError):
    """Existing PostgreSQL authority differs from the committed seed."""


class RuntimeAuthorityTransitionRefused(RuntimeError):
    """A monotonic live-capability transition failed a hard gate."""


class RuntimeAuthoritySeedRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: str
    runtime_commit: str
    schema_revision: Literal["0001_initial"]
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
    real_submit_enabled: bool
    max_concurrent_tickets: int
    max_gross_notional: Decimal
    max_gross_risk_at_stop: Decimal
    max_ticket_risk_at_stop: Decimal
    target_leverage: Decimal


class RuntimeAuthoritySeedResult(RuntimePolicyState):
    registry_semantic_hash: str
    runtime_seed_semantic_hash: str
    runtime_scope_count: int
    registry_inserted_count: int
    runtime_inserted_count: int

    @property
    def total_inserted_count(self) -> int:
        return self.registry_inserted_count + self.runtime_inserted_count


@dataclass(frozen=True)
class _PolicyEnvelope:
    max_concurrent_tickets: int
    max_gross_notional: Decimal
    max_gross_risk_at_stop: Decimal
    max_ticket_risk_at_stop: Decimal
    target_leverage: Decimal = Decimal("2")


@dataclass(frozen=True)
class _ExactRow:
    table: sa.Table
    identity_column: str
    values: Mapping[str, Any]
    compare_keys: tuple[str, ...]


ACCEPTANCE = _PolicyEnvelope(
    max_concurrent_tickets=1,
    max_gross_notional=Decimal("20"),
    max_gross_risk_at_stop=Decimal("10"),
    max_ticket_risk_at_stop=Decimal("10"),
)
FULL = _PolicyEnvelope(
    max_concurrent_tickets=2,
    max_gross_notional=Decimal("40"),
    max_gross_risk_at_stop=Decimal("20"),
    max_ticket_risk_at_stop=Decimal("10"),
)
_POLICY_COMPARE_KEYS = (
    "policy_version",
    "enabled",
    "real_submit_enabled",
    "priority_rank",
    "max_concurrent_tickets",
    "max_gross_notional",
    "max_gross_risk_at_stop",
    "max_ticket_risk_at_stop",
    "target_leverage",
    "scope",
)


def build_runtime_seed_identity(request: RuntimeAuthoritySeedRequest) -> str:
    """Compute the exact seed identity before touching PostgreSQL."""

    contracts = registered_strategy_contracts()
    scope_ids = _scope_ids(_runtime_scope_rows(request.seeded_at_ms))
    return _seed_identity(
        account_id=request.account_id,
        schema_revision=request.schema_revision,
        registry_semantic_hash=build_registry_semantic_hash(contracts),
        scope_ids=scope_ids,
    )


async def seed_runtime_authority(
    uow: PostgresKernelUnitOfWork,
    request: RuntimeAuthoritySeedRequest,
) -> RuntimeAuthoritySeedResult:
    """Install the exact observation-only authority in one transaction."""

    registry = await seed_strategy_registry(uow, seeded_at_ms=request.seeded_at_ms)
    connection = uow._require_connection()
    scope_rows = _runtime_scope_rows(request.seeded_at_ms)
    scope_ids = _scope_ids(scope_rows)
    seed_identity = _seed_identity(
        account_id=request.account_id,
        schema_revision=request.schema_revision,
        registry_semantic_hash=registry.registry_semantic_hash,
        scope_ids=scope_ids,
    )
    policy = _policy_values(
        version=1,
        real_submit_enabled=False,
        envelope=ACCEPTANCE,
        scope_ids=scope_ids,
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
            "account_id",
            {
                "account_id": request.account_id,
                "gross_notional": Decimal("0"),
                "gross_risk_at_stop": Decimal("0"),
                "active_ticket_count": 0,
                "projection_version": 0,
                "updated_at_ms": request.seeded_at_ms,
            },
            (
                "gross_notional",
                "gross_risk_at_stop",
                "active_ticket_count",
                "projection_version",
            ),
        ),
    ]
    rows.extend(
        _ExactRow(
            runtime_scopes_current,
            "runtime_scope_id",
            values,
            (
                "strategy_group_id",
                "strategy_version_id",
                "event_spec_id",
                "runtime_profile_id",
                "owner_policy_id",
                "exchange_instrument_id",
                "position_side",
                "enabled",
                "scope_version",
            ),
        )
        for values in scope_rows
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
        runtime_scopes_current,
        "runtime_scope_id",
        set(scope_ids),
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
        runtime_scope_count=len(scope_rows),
        registry_inserted_count=registry.total_inserted_count,
        runtime_inserted_count=inserted,
    )


async def arm_acceptance_policy(
    uow: PostgresKernelUnitOfWork,
    request: ArmAcceptancePolicyRequest,
) -> RuntimePolicyState:
    return await _transition_policy(
        uow,
        expected_version=1,
        expected_submit=False,
        target_version=2,
        target_envelope=ACCEPTANCE,
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
        expected_version=2,
        expected_submit=True,
        target_version=3,
        target_envelope=FULL,
        operation="promote_full_runtime",
        stage="full_runtime",
        occurred_at_ms=request.promoted_at_ms,
        acceptance_ticket_id=request.acceptance_ticket_id,
    )


async def _transition_policy(
    uow: PostgresKernelUnitOfWork,
    *,
    expected_version: int,
    expected_submit: bool,
    target_version: int,
    target_envelope: _PolicyEnvelope,
    operation: str,
    stage: str,
    occurred_at_ms: int,
    acceptance_ticket_id: str | None = None,
) -> RuntimePolicyState:
    connection = uow._require_connection()
    scope_ids = await _load_scope_ids(connection)
    current = dict(await _lock_policy(connection))
    if _policy_matches(
        current,
        version=target_version,
        real_submit_enabled=True,
        envelope=target_envelope,
        scope_ids=scope_ids,
    ):
        return _policy_state(current)
    if not _policy_matches(
        current,
        version=expected_version,
        real_submit_enabled=expected_submit,
        envelope=ACCEPTANCE,
        scope_ids=scope_ids,
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

    target = _policy_values(
        version=target_version,
        real_submit_enabled=True,
        envelope=target_envelope,
        scope_ids=scope_ids,
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
            owner_policy_current.c.policy_version == expected_version,
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


def _runtime_scope_rows(seeded_at_ms: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = [
        {
            "runtime_scope_id": (
                f"scope:{contract.event_id}:{instrument.venue_symbol}:"
                f"{contract.position_side}"
            ),
            "strategy_group_id": contract.strategy_group_id,
            "strategy_version_id": contract.strategy_version_id,
            "event_spec_id": contract.event_spec_id,
            "runtime_profile_id": RUNTIME_PROFILE_ID,
            "owner_policy_id": OWNER_POLICY_ID,
            "exchange_instrument_id": instrument.exchange_instrument_id,
            "position_side": contract.position_side,
            "enabled": True,
            "scope_version": 1,
            "observation_due_at_ms": seeded_at_ms,
            "observation_lease_until_ms": None,
            "observation_claim_owner": None,
            "updated_at_ms": seeded_at_ms,
        }
        for contract in registered_strategy_contracts()
        for instrument in contract.candidate_instruments
    ]
    rows.sort(key=lambda row: str(row["runtime_scope_id"]))
    if len(rows) != 22:
        raise RuntimeAuthoritySeedConflict("runtime authority requires 22 scopes")
    return rows


def _scope_ids(rows: list[dict[str, object]]) -> tuple[str, ...]:
    return tuple(str(row["runtime_scope_id"]) for row in rows)


async def _load_scope_ids(connection: AsyncConnection) -> tuple[str, ...]:
    rows = (
        await connection.execute(
            sa.select(runtime_scopes_current).where(
                runtime_scopes_current.c.owner_policy_id == OWNER_POLICY_ID,
                runtime_scopes_current.c.runtime_profile_id == RUNTIME_PROFILE_ID,
                runtime_scopes_current.c.enabled.is_(True),
            )
        )
    ).mappings().all()
    if len(rows) != 22:
        raise RuntimeAuthorityTransitionRefused(
            "runtime policy transition requires all 22 enabled scopes"
        )
    return tuple(sorted(str(row["runtime_scope_id"]) for row in rows))


def _policy_values(
    *,
    version: int,
    real_submit_enabled: bool,
    envelope: _PolicyEnvelope,
    scope_ids: tuple[str, ...],
    updated_at_ms: int,
) -> dict[str, object]:
    return {
        "owner_policy_id": OWNER_POLICY_ID,
        "policy_version": version,
        "enabled": True,
        "real_submit_enabled": real_submit_enabled,
        "priority_rank": 1,
        "max_concurrent_tickets": envelope.max_concurrent_tickets,
        "max_gross_notional": envelope.max_gross_notional,
        "max_gross_risk_at_stop": envelope.max_gross_risk_at_stop,
        "max_ticket_risk_at_stop": envelope.max_ticket_risk_at_stop,
        "target_leverage": envelope.target_leverage,
        "scope": {
            "runtime_profile_id": RUNTIME_PROFILE_ID,
            "runtime_scope_ids": list(scope_ids),
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
    scope_ids: tuple[str, ...],
) -> str:
    semantics = _policy_values(
        version=1,
        real_submit_enabled=False,
        envelope=ACCEPTANCE,
        scope_ids=scope_ids,
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
    real_submit_enabled: bool,
    envelope: _PolicyEnvelope,
    scope_ids: tuple[str, ...],
) -> bool:
    expected = _policy_values(
        version=version,
        real_submit_enabled=real_submit_enabled,
        envelope=envelope,
        scope_ids=scope_ids,
        updated_at_ms=int(str(row["updated_at_ms"])),
    )
    return all(row[key] == expected[key] for key in _POLICY_COMPARE_KEYS)


def _policy_state(values: Mapping[str, object]) -> RuntimePolicyState:
    return RuntimePolicyState(
        owner_policy_id=str(values["owner_policy_id"]),
        policy_version=int(str(values["policy_version"])),
        real_submit_enabled=bool(values["real_submit_enabled"]),
        max_concurrent_tickets=int(str(values["max_concurrent_tickets"])),
        max_gross_notional=Decimal(str(values["max_gross_notional"])),
        max_gross_risk_at_stop=Decimal(str(values["max_gross_risk_at_stop"])),
        max_ticket_risk_at_stop=Decimal(str(values["max_ticket_risk_at_stop"])),
        target_leverage=Decimal(str(values["target_leverage"])),
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
    if int(active_tickets or 0) != 0:
        raise RuntimeAuthorityTransitionRefused(
            "runtime transition requires zero active Tickets"
        )
    if int(open_incidents or 0) != 0:
        raise RuntimeAuthorityTransitionRefused(
            "runtime transition requires zero open Incidents"
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
                trade_tickets.c.owner_policy_version == 2,
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
    existing = (
        await connection.execute(
            sa.select(row.table)
            .where(
                row.table.c[row.identity_column]
                == row.values[row.identity_column]
            )
            .limit(1)
        )
    ).mappings().one_or_none()
    if existing is None:
        await connection.execute(sa.insert(row.table).values(dict(row.values)))
        return 1
    if not all(existing[key] == row.values[key] for key in row.compare_keys):
        raise RuntimeAuthoritySeedConflict(
            f"runtime authority conflict for {row.values[row.identity_column]}"
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
