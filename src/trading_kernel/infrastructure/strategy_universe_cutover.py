"""Guarded forward-only DML for the Strategy-Universe cutover."""

from __future__ import annotations

from hashlib import sha256
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.trading_kernel.infrastructure.pg_models import (
    account_exposure_current,
    armed_structures,
    budget_reservations,
    entry_lane_current,
    exchange_commands,
    facts_current,
    instrument_rules_current,
    monitor_current,
    owner_policy_current,
    owner_policy_events,
    positions_current,
    readiness_current,
    runtime_capabilities_current,
    runtime_incidents,
    runtime_profiles,
    runtime_scopes_current,
    schema_metadata,
    scope_warm_readiness,
    strategy_candidate_scopes,
    strategy_universe_cutovers,
    trade_aggregates,
    trade_events,
    trade_reviews,
    trade_tickets,
    universe_projection_leases,
    universe_projection_members,
    universe_projection_runs,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    GLOBAL_ENTRY_LANE_ID,
    OWNER_POLICY_ID,
    RUNTIME_PROFILE_ID,
    RuntimeAuthoritySeedRequest,
    build_runtime_seed_identity,
    runtime_policy_event,
    runtime_policy_values,
    runtime_scope_seed_rows,
)
from src.trading_kernel.infrastructure.strategy_registry_seed import (
    seed_strategy_registry,
)
from src.trading_kernel.infrastructure.strategy_universe_seed import (
    seed_strategy_universes,
)


_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_UNRESOLVED_COMMAND_STATUSES = (
    "prepared",
    "claimed",
    "dispatch_started",
    "outcome_unknown",
)


class StrategyUniverseCutoverBlocked(RuntimeError):
    """The exact internal preconditions for forward DML are not satisfied."""


class StrategyUniverseCutoverRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    cutover_id: str
    account_id: str
    target_runtime_commit: str
    target_schema_revision: Literal["0002_strategy_universe_us_equity"]
    target_seed_identity: str
    external_flat_verification_digest: str
    terminal_ticket_ids: tuple[str, ...] = ()
    resolved_incident_ids: tuple[str, ...] = ()
    applied_at_ms: int

    @field_validator("cutover_id", "account_id", mode="before")
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("cutover identity must be non-blank")
        return normalized

    @field_validator("target_runtime_commit")
    @classmethod
    def _require_commit(cls, value: str) -> str:
        if _COMMIT.fullmatch(value) is None:
            raise ValueError("cutover commit must be an exact git SHA")
        return value

    @field_validator(
        "target_seed_identity",
        "external_flat_verification_digest",
    )
    @classmethod
    def _require_digest(cls, value: str) -> str:
        if _DIGEST.fullmatch(value) is None:
            raise ValueError("cutover digest must be an exact sha256 identity")
        return value

    @field_validator("terminal_ticket_ids", "resolved_incident_ids")
    @classmethod
    def _require_exact_id_set(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted(str(item or "").strip() for item in value))
        if any(not item for item in normalized) or len(normalized) != len(
            set(normalized)
        ):
            raise ValueError("cutover identity set must be non-blank and unique")
        return normalized

    @field_validator("applied_at_ms")
    @classmethod
    def _require_time(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("cutover time must be positive")
        return value


class StrategyUniverseCutoverCounts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    runtime_scope_count: int
    active_ticket_count: int
    unresolved_command_count: int
    nonzero_position_count: int
    open_incident_count: int
    current_fact_count: int
    current_readiness_count: int
    projection_run_count: int


class StrategyUniverseCutoverInspection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    cutover_id: str
    status: Literal["ready", "blocked", "applied"]
    blockers: tuple[str, ...]
    before_counts: StrategyUniverseCutoverCounts
    after_counts: StrategyUniverseCutoverCounts | None = None

    @model_validator(mode="after")
    def _validate_status(self) -> "StrategyUniverseCutoverInspection":
        if self.status == "blocked" and not self.blockers:
            raise ValueError("blocked cutover requires blockers")
        if self.status != "blocked" and self.blockers:
            raise ValueError("non-blocked cutover forbids blockers")
        if self.status == "applied" and self.after_counts is None:
            raise ValueError("applied cutover requires after counts")
        return self


async def inspect_strategy_universe_cutover(
    uow: PostgresKernelUnitOfWork,
    request: StrategyUniverseCutoverRequest,
    *,
    lock: bool = False,
) -> StrategyUniverseCutoverInspection:
    connection = uow._require_connection()
    if lock:
        await connection.execute(
            sa.select(
                sa.func.pg_advisory_xact_lock(
                    sa.func.hashtext("brc-strategy-universe-cutover")
                )
            )
        )

    prior = (
        await connection.execute(
            sa.select(strategy_universe_cutovers).where(
                strategy_universe_cutovers.c.cutover_id == request.cutover_id
            )
        )
    ).mappings().one_or_none()
    if prior is not None:
        _assert_prior_matches(prior, request)
        return StrategyUniverseCutoverInspection(
            cutover_id=request.cutover_id,
            status="applied",
            blockers=(),
            before_counts=StrategyUniverseCutoverCounts.model_validate(
                prior["before_counts"]
            ),
            after_counts=StrategyUniverseCutoverCounts.model_validate(
                prior["after_counts"]
            ),
        )

    before = await _counts(connection)
    blockers: list[str] = []
    metadata_rows = {
        str(row["metadata_key"]): str(row["metadata_value"])
        for row in (
            await connection.execute(sa.select(schema_metadata))
        ).mappings()
    }
    if metadata_rows.get("runtime_commit") != request.target_runtime_commit:
        blockers.append("target_runtime_commit_mismatch")
    if (
        metadata_rows.get("schema_revision")
        != request.target_schema_revision
    ):
        blockers.append("target_schema_revision_mismatch")

    seed_request = RuntimeAuthoritySeedRequest(
        account_id=request.account_id,
        runtime_commit=request.target_runtime_commit,
        schema_revision=request.target_schema_revision,
        seeded_at_ms=request.applied_at_ms,
    )
    if build_runtime_seed_identity(seed_request) != request.target_seed_identity:
        blockers.append("target_seed_identity_mismatch")

    profile = (
        await connection.execute(
            sa.select(runtime_profiles).where(
                runtime_profiles.c.runtime_profile_id == RUNTIME_PROFILE_ID
            )
        )
    ).mappings().one_or_none()
    if (
        profile is None
        or str(profile["account_id"]) != request.account_id
        or str(profile["position_mode"]) != "independent_sides"
        or str(profile["status"]) != "active"
    ):
        blockers.append("runtime_profile_identity_mismatch")

    policy = (
        await connection.execute(
            sa.select(owner_policy_current).where(
                owner_policy_current.c.owner_policy_id == OWNER_POLICY_ID
            )
        )
    ).mappings().one_or_none()
    if (
        policy is None
        or not bool(policy["enabled"])
        or bool(policy["new_entry_submit_enabled"])
    ):
        blockers.append("new_entry_not_fenced")

    exchange_capability = (
        await connection.execute(
            sa.select(runtime_capabilities_current).where(
                runtime_capabilities_current.c.capability_key
                == "exchange_commands"
            )
        )
    ).mappings().one_or_none()
    if exchange_capability is None or bool(exchange_capability["enabled"]):
        blockers.append("exchange_commands_not_fenced")

    active_ticket_ids = await _active_ticket_ids(connection)
    if active_ticket_ids != request.terminal_ticket_ids:
        blockers.append("active_ticket_identity_mismatch")
    aggregate_ids = tuple(
        sorted(
            str(item)
            for item in (
                await connection.execute(
                    sa.select(trade_aggregates.c.ticket_id).where(
                        trade_aggregates.c.ticket_id.in_(
                            request.terminal_ticket_ids
                        )
                    )
                )
            ).scalars()
        )
    )
    if aggregate_ids != request.terminal_ticket_ids:
        blockers.append("active_ticket_aggregate_missing")

    if before.unresolved_command_count:
        blockers.append("unresolved_exchange_command")

    nonzero_position_ticket_ids = tuple(
        sorted(
            str(item)
            for item in (
                await connection.execute(
                    sa.select(positions_current.c.ticket_id).where(
                        positions_current.c.quantity > 0
                    )
                )
            ).scalars()
            if item is not None
        )
    )
    anonymous_nonzero_position_count = int(
        await connection.scalar(
            sa.select(sa.func.count())
            .select_from(positions_current)
            .where(
                positions_current.c.quantity > 0,
                positions_current.c.ticket_id.is_(None),
            )
        )
        or 0
    )
    if (
        anonymous_nonzero_position_count
        or tuple(sorted(set(nonzero_position_ticket_ids)))
        not in {(), request.terminal_ticket_ids}
    ):
        blockers.append("position_identity_mismatch")

    open_incident_ids = await _open_incident_ids(connection)
    if open_incident_ids != request.resolved_incident_ids:
        blockers.append("open_incident_identity_mismatch")

    lane = (
        await connection.execute(
            sa.select(entry_lane_current).where(
                entry_lane_current.c.lane_id == GLOBAL_ENTRY_LANE_ID
            )
        )
    ).mappings().one_or_none()
    if lane is None or (
        lane["ticket_id"] is not None
        and str(lane["ticket_id"]) not in request.terminal_ticket_ids
    ):
        blockers.append("entry_lane_identity_mismatch")

    exposure = (
        await connection.execute(
            sa.select(account_exposure_current).where(
                account_exposure_current.c.venue_id == "binance-usdm",
                account_exposure_current.c.account_id == request.account_id,
            )
        )
    ).mappings().one_or_none()
    if exposure is None:
        blockers.append("account_exposure_identity_mismatch")

    return StrategyUniverseCutoverInspection(
        cutover_id=request.cutover_id,
        status="blocked" if blockers else "ready",
        blockers=tuple(blockers),
        before_counts=before,
    )


async def apply_strategy_universe_cutover(
    uow: PostgresKernelUnitOfWork,
    request: StrategyUniverseCutoverRequest,
) -> StrategyUniverseCutoverInspection:
    inspection = await inspect_strategy_universe_cutover(
        uow,
        request,
        lock=True,
    )
    if inspection.status == "applied":
        return inspection
    if inspection.status != "ready":
        raise StrategyUniverseCutoverBlocked(
            "strategy Universe cutover blocked: "
            + ",".join(inspection.blockers)
        )

    connection = uow._require_connection()
    await seed_strategy_registry(uow, seeded_at_ms=request.applied_at_ms)
    await seed_strategy_universes(uow, seeded_at_ms=request.applied_at_ms)

    for ticket_id in request.terminal_ticket_ids:
        aggregate = (
            await connection.execute(
                sa.select(trade_aggregates)
                .where(trade_aggregates.c.ticket_id == ticket_id)
                .with_for_update(of=trade_aggregates)
            )
        ).mappings().one()
        next_sequence = int(aggregate["last_event_sequence"]) + 1
        event_id = _cutover_event_id(request.cutover_id, ticket_id)
        review_id = _cutover_review_id(request.cutover_id, ticket_id)
        await connection.execute(
            sa.insert(trade_events).values(
                event_id=event_id,
                ticket_id=ticket_id,
                sequence=next_sequence,
                event_type="CutoverTerminalized",
                payload={
                    "cutover_id": request.cutover_id,
                    "external_flat_verification_digest": (
                        request.external_flat_verification_digest
                    ),
                    "economics_status": "unavailable",
                    "reason": "owner_manual_flat_before_forward_cutover",
                },
                occurred_at_ms=request.applied_at_ms,
            )
        )
        await connection.execute(
            pg_insert(trade_reviews)
            .values(
                review_id=review_id,
                ticket_id=ticket_id,
                outcome="external_flat_cutover",
                metrics={
                    "economics_status": "unavailable",
                    "unavailable_reason": "manual_flat_cutover",
                },
                decision_impact={
                    "cutover_id": request.cutover_id,
                    "future_policy_effect": "none",
                },
                created_at_ms=request.applied_at_ms,
            )
            .on_conflict_do_nothing(index_elements=[trade_reviews.c.ticket_id])
        )
        persisted_review_id = await connection.scalar(
            sa.select(trade_reviews.c.review_id).where(
                trade_reviews.c.ticket_id == ticket_id
            )
        )
        await connection.execute(
            sa.update(trade_aggregates)
            .where(trade_aggregates.c.ticket_id == ticket_id)
            .values(
                status="terminal",
                version=int(aggregate["version"]) + 1,
                last_event_sequence=next_sequence,
                entry_lane_held=False,
                position_qty=0,
                protected_qty=0,
                review_id=persisted_review_id,
                lifecycle_due_at_ms=None,
                reconciliation_due_at_ms=None,
                updated_at_ms=request.applied_at_ms,
            )
        )
        await connection.execute(
            sa.update(trade_tickets)
            .where(trade_tickets.c.ticket_id == ticket_id)
            .values(
                status="cutover_terminal",
                active_netting_domain_key=None,
                terminal_at_ms=request.applied_at_ms,
            )
        )
        await connection.execute(
            sa.update(budget_reservations)
            .where(budget_reservations.c.ticket_id == ticket_id)
            .values(status="released", released_at_ms=request.applied_at_ms)
        )
        await connection.execute(
            sa.update(positions_current)
            .where(positions_current.c.ticket_id == ticket_id)
            .values(
                ticket_id=None,
                quantity=0,
                average_entry_price=None,
                observed_at_ms=request.applied_at_ms,
                projection_version=positions_current.c.projection_version + 1,
            )
        )

    if request.resolved_incident_ids:
        await connection.execute(
            sa.update(runtime_incidents)
            .where(
                runtime_incidents.c.incident_id.in_(
                    request.resolved_incident_ids
                ),
                runtime_incidents.c.resolved_at_ms.is_(None),
            )
            .values(status="resolved", resolved_at_ms=request.applied_at_ms)
        )

    await connection.execute(sa.delete(universe_projection_members))
    await connection.execute(sa.delete(armed_structures))
    await connection.execute(sa.delete(universe_projection_runs))
    await connection.execute(sa.delete(universe_projection_leases))
    await connection.execute(sa.delete(scope_warm_readiness))
    await connection.execute(sa.delete(facts_current))
    await connection.execute(sa.delete(readiness_current))
    await connection.execute(sa.delete(instrument_rules_current))
    await connection.execute(sa.delete(monitor_current))
    await connection.execute(sa.delete(runtime_scopes_current))
    await connection.execute(
        sa.delete(strategy_candidate_scopes).where(
            strategy_candidate_scopes.c.universe_version_id.is_(None)
        )
    )

    scope_rows = runtime_scope_seed_rows(request.applied_at_ms)
    await connection.execute(sa.insert(runtime_scopes_current), scope_rows)
    scope_ids = tuple(
        str(row["runtime_scope_id"]) for row in scope_rows
    )
    policy = (
        await connection.execute(
            sa.select(owner_policy_current)
            .where(owner_policy_current.c.owner_policy_id == OWNER_POLICY_ID)
            .with_for_update(of=owner_policy_current)
        )
    ).mappings().one()
    next_policy_version = int(policy["policy_version"]) + 1
    target_policy = runtime_policy_values(
        version=next_policy_version,
        new_entry_submit_enabled=True,
        scope_ids=scope_ids,
        updated_at_ms=request.applied_at_ms,
    )
    await connection.execute(
        sa.insert(owner_policy_events).values(
            runtime_policy_event(
                version=next_policy_version,
                operation="strategy_universe_cutover_full",
                policy=target_policy,
                occurred_at_ms=request.applied_at_ms,
            )
        )
    )
    await connection.execute(
        sa.update(owner_policy_current)
        .where(
            owner_policy_current.c.owner_policy_id == OWNER_POLICY_ID,
            owner_policy_current.c.policy_version == policy["policy_version"],
        )
        .values(target_policy)
    )

    await connection.execute(
        sa.update(entry_lane_current)
        .where(entry_lane_current.c.lane_id == GLOBAL_ENTRY_LANE_ID)
        .values(
            ticket_id=None,
            signal_event_id=None,
            status="idle",
            claimed_at_ms=None,
            lease_until_ms=None,
            claim_owner=None,
            version=entry_lane_current.c.version + 1,
        )
    )
    await connection.execute(
        sa.update(account_exposure_current)
        .where(
            account_exposure_current.c.venue_id == "binance-usdm",
            account_exposure_current.c.account_id == request.account_id,
        )
        .values(
            gross_notional=0,
            gross_risk_at_stop=0,
            active_ticket_count=0,
            projection_version=(
                account_exposure_current.c.projection_version + 1
            ),
            updated_at_ms=request.applied_at_ms,
        )
    )
    certification = {
        "stage": "full_strategy_universe_cutover",
        "cutover_id": request.cutover_id,
        "seed_identity": request.target_seed_identity,
        "external_flat_verification_digest": (
            request.external_flat_verification_digest
        ),
    }
    await connection.execute(
        sa.update(runtime_capabilities_current).values(
            enabled=True,
            certified_commit=request.target_runtime_commit,
            schema_revision=request.target_schema_revision,
            certification=certification,
            updated_at_ms=request.applied_at_ms,
        )
    )
    for key, value in (
        ("runtime_commit", request.target_runtime_commit),
        ("schema_revision", request.target_schema_revision),
        ("seed_identity", request.target_seed_identity),
    ):
        await connection.execute(
            sa.update(schema_metadata)
            .where(schema_metadata.c.metadata_key == key)
            .values(
                metadata_value=value,
                updated_at_ms=request.applied_at_ms,
            )
        )

    after = await _counts(connection)
    if (
        after.runtime_scope_count != 49
        or after.active_ticket_count
        or after.unresolved_command_count
        or after.nonzero_position_count
        or after.open_incident_count
        or after.current_fact_count
        or after.current_readiness_count
        or after.projection_run_count
    ):
        raise StrategyUniverseCutoverBlocked(
            "strategy Universe cutover postcondition failed"
        )
    await connection.execute(
        sa.insert(strategy_universe_cutovers).values(
            cutover_id=request.cutover_id,
            target_runtime_commit=request.target_runtime_commit,
            target_schema_revision=request.target_schema_revision,
            target_seed_identity=request.target_seed_identity,
            external_flat_verification_digest=(
                request.external_flat_verification_digest
            ),
            terminal_ticket_ids=list(request.terminal_ticket_ids),
            resolved_incident_ids=list(request.resolved_incident_ids),
            before_counts=inspection.before_counts.model_dump(mode="json"),
            after_counts=after.model_dump(mode="json"),
            status="applied",
            applied_at_ms=request.applied_at_ms,
        )
    )
    return StrategyUniverseCutoverInspection(
        cutover_id=request.cutover_id,
        status="applied",
        blockers=(),
        before_counts=inspection.before_counts,
        after_counts=after,
    )


async def _counts(connection) -> StrategyUniverseCutoverCounts:
    async def count(table: sa.Table, *criteria) -> int:
        return int(
            await connection.scalar(
                sa.select(sa.func.count()).select_from(table).where(*criteria)
            )
            or 0
        )

    return StrategyUniverseCutoverCounts(
        runtime_scope_count=await count(runtime_scopes_current),
        active_ticket_count=len(await _active_ticket_ids(connection)),
        unresolved_command_count=await count(
            exchange_commands,
            exchange_commands.c.status.in_(_UNRESOLVED_COMMAND_STATUSES),
        ),
        nonzero_position_count=await count(
            positions_current,
            positions_current.c.quantity > 0,
        ),
        open_incident_count=len(await _open_incident_ids(connection)),
        current_fact_count=await count(facts_current),
        current_readiness_count=await count(readiness_current),
        projection_run_count=await count(universe_projection_runs),
    )


async def _active_ticket_ids(connection) -> tuple[str, ...]:
    return tuple(
        sorted(
            str(item)
            for item in (
                await connection.execute(
                    sa.select(trade_tickets.c.ticket_id).where(
                        sa.or_(
                            trade_tickets.c.active_netting_domain_key.is_not(
                                None
                            ),
                            trade_tickets.c.terminal_at_ms.is_(None),
                        )
                    )
                )
            ).scalars()
        )
    )


async def _open_incident_ids(connection) -> tuple[str, ...]:
    return tuple(
        sorted(
            str(item)
            for item in (
                await connection.execute(
                    sa.select(runtime_incidents.c.incident_id).where(
                        runtime_incidents.c.resolved_at_ms.is_(None)
                    )
                )
            ).scalars()
        )
    )


def _assert_prior_matches(prior, request: StrategyUniverseCutoverRequest) -> None:
    expected = {
        "target_runtime_commit": request.target_runtime_commit,
        "target_schema_revision": request.target_schema_revision,
        "target_seed_identity": request.target_seed_identity,
        "external_flat_verification_digest": (
            request.external_flat_verification_digest
        ),
        "terminal_ticket_ids": list(request.terminal_ticket_ids),
        "resolved_incident_ids": list(request.resolved_incident_ids),
        "status": "applied",
    }
    if any(prior[key] != value for key, value in expected.items()):
        raise StrategyUniverseCutoverBlocked(
            "cutover replay identity differs from applied audit"
        )


def _cutover_event_id(cutover_id: str, ticket_id: str) -> str:
    digest = sha256(f"{cutover_id}:{ticket_id}:event".encode()).hexdigest()
    return f"event:cutover:{digest}"


def _cutover_review_id(cutover_id: str, ticket_id: str) -> str:
    digest = sha256(f"{cutover_id}:{ticket_id}:review".encode()).hexdigest()
    return f"review:cutover:{digest}"
