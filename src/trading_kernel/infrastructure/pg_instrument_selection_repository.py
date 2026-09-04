"""PostgreSQL ownership for Dynamic Selection facts and current Authority."""

from __future__ import annotations

from typing import ClassVar, Literal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

from src.trading_kernel.application.ports import SelectionJobRecord
from src.trading_kernel.application.recover_expired_dynamic_activation import (
    ExpiredDynamicActivationRecoveryBlocked,
    ExpiredDynamicActivationRecoveryStatus,
    RecoverExpiredDynamicActivationRequest,
    RecoverExpiredDynamicActivationResult,
)
from src.trading_kernel.application.runtime import RuntimeReleaseCompatibilityFact
from src.trading_kernel.domain.instrument_selection import (
    SOR_LONG_EVENT_SPEC_ID,
    SOR_SHORT_EVENT_SPEC_ID,
    SelectionAttemptOutcome,
    SelectionComputation,
    SelectionJobClaim,
    SelectionJobFailure,
    SelectionPeriod,
    SelectionSnapshot,
    SorDynamicSelectionSpecV0,
    build_sor_dynamic_selection_spec_v0,
)
from src.trading_kernel.domain.selection_authority import (
    AuthorityGapAudit,
    AuthorityGapAuditKind,
    AuthorityGapAuditState,
    AuthorityGapScopeResult,
    AuthorityGrantProof,
    AuthorityGrantProofKind,
    AuthorityOutcome,
    ContinuitySourceKind,
    CurrentSelectionAuthority,
    MaterializationGeneration,
    MaterializationGenerationClaimStatus,
    MaterializationGenerationLeaseClaim,
    MaterializationGenerationState,
    MaterializationTarget,
    SelectionControl,
    SelectionMode,
    SelectionSessionAuthority,
    SelectionSnapshotDisposition,
    StrategyTriggerSuppression,
    UniverseAuthorityPair,
    selected_member_set_digest,
)
from src.trading_kernel.domain.strategy_entry_vacuum import (
    StrategyEntryVacuum,
    StrategyEntryVacuumState,
)
from src.trading_kernel.infrastructure.pg_models import (
    instrument_selection_attempts,
    instrument_selection_jobs_current,
    instrument_selection_member_decisions,
    instrument_selection_snapshots,
    instrument_selection_spec_events,
    instrument_selection_spec_members,
    instrument_selection_specs,
    runtime_release_compatibility_facts,
    selection_authority_current,
    selection_authority_gap_audit_events,
    selection_authority_gap_audits_current,
    selection_session_authorities,
    sor_dynamic_selection_specs_v0,
    strategy_entry_controls_current,
    strategy_entry_vacuum_events,
    strategy_entry_vacuums_current,
    strategy_selection_control_current,
    strategy_trigger_suppressions,
    strategy_universe_current,
    strategy_universe_materialization_events,
    strategy_universe_materialization_generations,
    strategy_universe_materialization_targets,
    strategy_universe_versions,
    trade_aggregates,
    trade_tickets,
)

LeaseKind = Literal["selection", "materialization", "observation"]
_CURRENT_ENTRY_VACUUM_STATES = (
    "OPEN",
    "DRAINING_ENTRY",
    "RECONFIGURING",
    "OWNER_PAUSED",
    "SUPERSEDED",
    "FAILED_CLOSED",
)
_ENTRY_VACUUM_DRAIN_BLOCKING_STATUSES = (
    "leverage_pending",
    "leverage_confirmed",
    "leverage_outcome_unknown",
    "entry_pending",
    "entry_accepted",
    "entry_outcome_unknown",
    "entry_vacuum_cancel_pending",
    "entry_vacuum_cancel_rejected",
    "entry_vacuum_cancel_outcome_unknown",
    "entry_vacuum_cancelled",
    "partial_fill_incident",
    "partial_fill_cancel_rejected",
    "partial_fill_cancel_outcome_unknown",
    "protection_pending",
    "initial_stop_outcome_unknown",
    "post_fill_risk_pending",
    "controlled_flatten_pending",
    "controlled_flatten_accepted",
    "controlled_flatten_rejected",
    "controlled_flatten_outcome_unknown",
)


class SelectionAuthorityVersionConflict(RuntimeError):
    """The current Authority pointer differs from the caller's locked view."""


class SelectionJobConflict(RuntimeError):
    """The exact Selection Job is already owned or has a conflicting result."""


class PostgresInstrumentSelectionRepository:
    """Persist immutable Selection facts behind exact, bounded projections."""

    _LEASE_NAMESPACES: ClassVar[dict[LeaseKind, str]] = {
        "selection": "selection_job",
        "materialization": "materialization_generation",
        "observation": "runtime_scope_observation",
    }

    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    @classmethod
    def lease_namespace(cls, lease_kind: LeaseKind) -> str:
        return cls._LEASE_NAMESPACES[lease_kind]

    async def get_active_spec(
        self,
        selection_spec_id: str,
    ) -> SorDynamicSelectionSpecV0:
        row = (
            await self._connection.execute(
                sa.select(
                    instrument_selection_specs,
                    sor_dynamic_selection_specs_v0,
                )
                .join(
                    sor_dynamic_selection_specs_v0,
                    sor_dynamic_selection_specs_v0.c.selection_spec_id
                    == instrument_selection_specs.c.selection_spec_id,
                )
                .where(
                    instrument_selection_specs.c.selection_spec_id
                    == selection_spec_id,
                    instrument_selection_specs.c.status == "active",
                )
                .limit(1)
            )
        ).mappings().one_or_none()
        if row is None:
            raise LookupError("active SelectionSpec does not exist")
        events = tuple(
            str(item)
            for item in (
                await self._connection.execute(
                    sa.select(instrument_selection_spec_events.c.event_spec_id)
                    .where(
                        instrument_selection_spec_events.c.selection_spec_id
                        == selection_spec_id
                    )
                    .order_by(instrument_selection_spec_events.c.event_spec_id)
                )
            ).scalars()
        )
        members = tuple(
            str(item)
            for item in (
                await self._connection.execute(
                    sa.select(
                        instrument_selection_spec_members.c.exchange_instrument_id
                    )
                    .where(
                        instrument_selection_spec_members.c.selection_spec_id
                        == selection_spec_id
                    )
                    .order_by(
                        instrument_selection_spec_members.c.exchange_instrument_id
                    )
                )
            ).scalars()
        )
        if (
            int(row["selection_version"]) != 1
            or str(row["selection_kind"]) != "sor_dynamic_v0"
            or int(row["decision_offset_utc_seconds"]) != 3600
            or int(row["feature_cutoff_offset_utc_seconds"]) != 3600
            or int(row["eligibility_not_before_offset_utc_seconds"]) != 4500
            or int(row["valid_until_next_decision_offset_seconds"]) != 86400
            or int(row["candidate_count"]) != 24
            or int(row["selected_count_max"]) != 7
            or int(row["near_count_max"]) != 7
            or int(row["materialization_timeout_seconds"]) != 1800
        ):
            raise ValueError("active SelectionSpec typed extension is not V0")
        spec = build_sor_dynamic_selection_spec_v0(
            selection_spec_id=str(row["selection_spec_id"]),
            strategy_group_id=str(row["strategy_group_id"]),
            strategy_version_id=str(row["strategy_version_id"]),
            event_spec_ids=events,
            candidate_exchange_instrument_ids=members,
            installed_at_ms=int(row["installed_at_ms"]),
        )
        if (
            spec.algorithm_semantic_digest != str(row["algorithm_semantic_digest"])
            or spec.activity_floor_quote_usdt != row["activity_floor_quote_usdt"]
        ):
            raise ValueError("active SelectionSpec semantic identity drifted")
        return spec

    async def claim_selection_job(
        self,
        *,
        spec: SorDynamicSelectionSpecV0,
        period: SelectionPeriod,
        worker_id: str,
        now_ms: int,
        lease_duration_ms: int,
    ) -> SelectionJobClaim | SelectionJobFailure | SelectionSnapshot:
        if now_ms < period.feature_cutoff_at_ms:
            raise ValueError("Selection Job cannot be claimed before feature cutoff")
        if lease_duration_ms <= 0:
            raise ValueError("Selection Job lease duration must be positive")
        job_id = f"selection-job:{spec.selection_spec_id}:{period.session_start_ms}"
        await self._connection.execute(
            pg_insert(instrument_selection_jobs_current)
            .values(
                selection_job_id=job_id,
                selection_spec_id=spec.selection_spec_id,
                session_start_ms=period.session_start_ms,
                scheduled_at_ms=period.decision_boundary_ms,
                feature_cutoff_at_ms=period.feature_cutoff_at_ms,
                state="DUE",
                selection_snapshot_id=None,
                first_blocker=None,
                attempt_count=0,
                next_retry_at_ms=None,
                lease_owner=None,
                lease_expires_at_ms=None,
                projection_version=1,
                updated_at_ms=now_ms,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    instrument_selection_jobs_current.c.selection_spec_id,
                    instrument_selection_jobs_current.c.session_start_ms,
                ]
            )
        )
        row = (
            await self._connection.execute(
                sa.select(instrument_selection_jobs_current)
                .where(
                    instrument_selection_jobs_current.c.selection_spec_id
                    == spec.selection_spec_id,
                    instrument_selection_jobs_current.c.session_start_ms
                    == period.session_start_ms,
                )
                .with_for_update()
            )
        ).mappings().one()
        state = str(row["state"])
        if state == "SNAPSHOT_READY":
            snapshot_id = row["selection_snapshot_id"]
            if snapshot_id is None:
                raise SelectionJobConflict("ready Selection Job has no Snapshot")
            return await self._get_snapshot(str(snapshot_id))
        if state in {"SOURCE_FAILED", "COMPUTE_FAILED"} and row[
            "next_retry_at_ms"
        ] is None:
            failure_outcome: Literal["SOURCE_FAILED", "COMPUTE_FAILED"] = (
                "SOURCE_FAILED" if state == "SOURCE_FAILED" else "COMPUTE_FAILED"
            )
            return SelectionJobFailure(
                selection_job_id=job_id,
                outcome=failure_outcome,
                reason_code=str(row["first_blocker"]),
            )
        lease_expires_at_ms = row["lease_expires_at_ms"]
        if (
            state == "CLAIMED"
            and lease_expires_at_ms is not None
            and int(lease_expires_at_ms) > now_ms
        ):
            raise SelectionJobConflict("Selection Job already has a live lease")
        next_retry_at_ms = row["next_retry_at_ms"]
        if next_retry_at_ms is not None and int(next_retry_at_ms) > now_ms:
            raise SelectionJobConflict("Selection Job retry is not due")
        attempt_number = int(row["attempt_count"]) + 1
        next_version = int(row["projection_version"]) + 1
        lease_expires = now_ms + lease_duration_ms
        result = await self._connection.execute(
            sa.update(instrument_selection_jobs_current)
            .where(
                instrument_selection_jobs_current.c.selection_job_id == job_id,
                instrument_selection_jobs_current.c.projection_version
                == int(row["projection_version"]),
            )
            .values(
                state="CLAIMED",
                selection_snapshot_id=None,
                first_blocker=None,
                attempt_count=attempt_number,
                next_retry_at_ms=None,
                lease_owner=worker_id,
                lease_expires_at_ms=lease_expires,
                projection_version=next_version,
                updated_at_ms=now_ms,
            )
        )
        if result.rowcount != 1:
            raise SelectionJobConflict("Selection Job projection version changed")
        return SelectionJobClaim(
            selection_job_id=job_id,
            selection_spec_id=spec.selection_spec_id,
            session_start_ms=period.session_start_ms,
            worker_id=worker_id,
            attempt_number=attempt_number,
            projection_version=next_version,
            started_at_ms=now_ms,
            lease_expires_at_ms=lease_expires,
        )

    async def complete_selection_snapshot(
        self,
        *,
        claim: SelectionJobClaim,
        computation: SelectionComputation,
        completed_at_ms: int,
    ) -> None:
        row = await self._locked_job(claim)
        if str(row["state"]) == "SNAPSHOT_READY":
            existing = await self._get_snapshot(str(row["selection_snapshot_id"]))
            if (
                existing.selection_semantic_digest
                == computation.snapshot.selection_semantic_digest
            ):
                return
            raise SelectionJobConflict("Selection Snapshot digest conflicts")
        self._require_live_claim(row, claim, completed_at_ms=completed_at_ms)
        snapshot = computation.snapshot
        await self._connection.execute(
            sa.insert(instrument_selection_snapshots).values(
                snapshot.model_dump()
            )
        )
        await self._connection.execute(
            sa.insert(instrument_selection_member_decisions),
            [
                {
                    **decision.model_dump(
                        exclude={"primary_reason", "member_state"}
                    ),
                    "primary_reason": (
                        None
                        if decision.primary_reason is None
                        else decision.primary_reason.value
                    ),
                    "member_state": decision.member_state.value,
                    "secondary_reasons": [
                        reason.value for reason in decision.secondary_reasons
                    ],
                }
                for decision in computation.member_decisions
            ],
        )
        await self._append_attempt(
            claim=claim,
            outcome=SelectionAttemptOutcome.SNAPSHOT_READY,
            reason_code=None,
            source_member_count=len(computation.member_decisions),
            source_digest=snapshot.source_semantic_digest,
            completed_at_ms=completed_at_ms,
        )
        result = await self._connection.execute(
            sa.update(instrument_selection_jobs_current)
            .where(
                instrument_selection_jobs_current.c.selection_job_id
                == claim.selection_job_id,
                instrument_selection_jobs_current.c.projection_version
                == claim.projection_version,
                instrument_selection_jobs_current.c.state == "CLAIMED",
                instrument_selection_jobs_current.c.lease_owner == claim.worker_id,
            )
            .values(
                state="SNAPSHOT_READY",
                selection_snapshot_id=snapshot.selection_snapshot_id,
                first_blocker=None,
                next_retry_at_ms=None,
                lease_owner=None,
                lease_expires_at_ms=None,
                projection_version=claim.projection_version + 1,
                updated_at_ms=completed_at_ms,
            )
        )
        if result.rowcount != 1:
            raise SelectionJobConflict("Selection Job completion lost its lease")

    async def complete_selection_failure(
        self,
        *,
        claim: SelectionJobClaim,
        outcome: SelectionAttemptOutcome,
        reason_code: str,
        source_member_count: int,
        source_digest: str | None,
        completed_at_ms: int,
    ) -> None:
        if outcome is SelectionAttemptOutcome.SNAPSHOT_READY:
            raise ValueError("failure completion requires a failure outcome")
        normalized_reason = reason_code.strip()
        if not normalized_reason:
            raise ValueError("Selection failure requires a reason code")
        row = await self._locked_job(claim)
        self._require_live_claim(row, claim, completed_at_ms=completed_at_ms)
        await self._append_attempt(
            claim=claim,
            outcome=outcome,
            reason_code=normalized_reason,
            source_member_count=source_member_count,
            source_digest=source_digest,
            completed_at_ms=completed_at_ms,
        )
        result = await self._connection.execute(
            sa.update(instrument_selection_jobs_current)
            .where(
                instrument_selection_jobs_current.c.selection_job_id
                == claim.selection_job_id,
                instrument_selection_jobs_current.c.projection_version
                == claim.projection_version,
                instrument_selection_jobs_current.c.state == "CLAIMED",
                instrument_selection_jobs_current.c.lease_owner == claim.worker_id,
            )
            .values(
                state=outcome.value,
                selection_snapshot_id=None,
                first_blocker=normalized_reason,
                next_retry_at_ms=None,
                lease_owner=None,
                lease_expires_at_ms=None,
                projection_version=claim.projection_version + 1,
                updated_at_ms=completed_at_ms,
            )
        )
        if result.rowcount != 1:
            raise SelectionJobConflict("Selection failure completion lost its lease")

    async def get_selection_job(
        self,
        *,
        selection_spec_id: str,
        session_start_ms: int,
    ) -> SelectionJobRecord | None:
        row = (
            await self._connection.execute(
                sa.select(instrument_selection_jobs_current)
                .where(
                    instrument_selection_jobs_current.c.selection_spec_id
                    == selection_spec_id,
                    instrument_selection_jobs_current.c.session_start_ms
                    == session_start_ms,
                )
                .limit(1)
            )
        ).mappings().one_or_none()
        return None if row is None else SelectionJobRecord.model_validate(dict(row))

    async def _locked_job(self, claim: SelectionJobClaim) -> RowMapping:
        row = (
            await self._connection.execute(
                sa.select(instrument_selection_jobs_current)
                .where(
                    instrument_selection_jobs_current.c.selection_job_id
                    == claim.selection_job_id
                )
                .with_for_update()
            )
        ).mappings().one_or_none()
        if row is None:
            raise SelectionJobConflict("Selection Job does not exist")
        return row

    @staticmethod
    def _require_live_claim(
        row: RowMapping,
        claim: SelectionJobClaim,
        *,
        completed_at_ms: int,
    ) -> None:
        if (
            str(row["state"]) != "CLAIMED"
            or str(row["lease_owner"]) != claim.worker_id
            or int(row["projection_version"]) != claim.projection_version
            or int(row["attempt_count"]) != claim.attempt_number
        ):
            raise SelectionJobConflict("Selection Job claim identity changed")
        if completed_at_ms > int(row["lease_expires_at_ms"]):
            raise SelectionJobConflict("Selection Job lease expired before completion")

    async def _append_attempt(
        self,
        *,
        claim: SelectionJobClaim,
        outcome: SelectionAttemptOutcome,
        reason_code: str | None,
        source_member_count: int,
        source_digest: str | None,
        completed_at_ms: int,
    ) -> None:
        await self._connection.execute(
            sa.insert(instrument_selection_attempts).values(
                selection_attempt_id=(
                    f"selection-attempt:{claim.selection_spec_id}:"
                    f"{claim.session_start_ms}:{claim.attempt_number}"
                ),
                selection_job_id=claim.selection_job_id,
                selection_spec_id=claim.selection_spec_id,
                session_start_ms=claim.session_start_ms,
                worker_id=claim.worker_id,
                attempt_number=claim.attempt_number,
                started_at_ms=claim.started_at_ms,
                completed_at_ms=completed_at_ms,
                outcome=outcome.value,
                reason_code=reason_code,
                source_member_count=source_member_count,
                source_digest=source_digest,
            )
        )

    async def _get_snapshot(self, selection_snapshot_id: str) -> SelectionSnapshot:
        row = (
            await self._connection.execute(
                sa.select(instrument_selection_snapshots)
                .where(
                    instrument_selection_snapshots.c.selection_snapshot_id
                    == selection_snapshot_id
                )
                .limit(1)
            )
        ).mappings().one_or_none()
        if row is None:
            raise SelectionJobConflict("Selection Snapshot does not exist")
        return SelectionSnapshot.model_validate(dict(row))

    async def get_selection_control(
        self,
        strategy_group_id: str,
        *,
        for_update: bool = False,
    ) -> SelectionControl | None:
        statement = sa.select(strategy_selection_control_current).where(
            strategy_selection_control_current.c.strategy_group_id
            == strategy_group_id
        )
        if for_update:
            statement = statement.with_for_update(of=strategy_selection_control_current)
        row = (await self._connection.execute(statement)).mappings().one_or_none()
        return None if row is None else _selection_control_from_row(row)

    async def activate_pending_selection_mode(
        self,
        *,
        strategy_group_id: str,
        expected_control_version: int,
        expected_pending_mode: SelectionMode,
        activated_at_ms: int,
    ) -> SelectionControl:
        result = await self._connection.execute(
            sa.update(strategy_selection_control_current)
            .where(
                strategy_selection_control_current.c.strategy_group_id
                == strategy_group_id,
                strategy_selection_control_current.c.control_version
                == expected_control_version,
                strategy_selection_control_current.c.pending_selection_mode
                == expected_pending_mode.value,
            )
            .values(
                selection_mode=expected_pending_mode.value,
                pending_selection_mode=None,
                pending_effective_session_start_ms=None,
                pending_authorization_id=None,
                control_version=expected_control_version + 1,
                updated_at_ms=activated_at_ms,
            )
            .returning(strategy_selection_control_current)
        )
        row = result.mappings().one_or_none()
        if row is None:
            raise SelectionJobConflict("Selection Control pending mode changed")
        return _selection_control_from_row(row)

    async def stage_pending_selection_mode(
        self,
        *,
        strategy_group_id: str,
        expected_control_version: int,
        expected_current_mode: SelectionMode,
        pending_mode: SelectionMode,
        effective_session_start_ms: int,
        authorization_id: str,
        updated_at_ms: int,
    ) -> SelectionControl | None:
        result = await self._connection.execute(
            sa.update(strategy_selection_control_current)
            .where(
                strategy_selection_control_current.c.strategy_group_id
                == strategy_group_id,
                strategy_selection_control_current.c.control_version
                == expected_control_version,
                strategy_selection_control_current.c.selection_mode
                == expected_current_mode.value,
                strategy_selection_control_current.c.pending_selection_mode.is_(None),
            )
            .values(
                pending_selection_mode=pending_mode.value,
                pending_effective_session_start_ms=effective_session_start_ms,
                pending_authorization_id=authorization_id,
                control_version=expected_control_version + 1,
                updated_at_ms=updated_at_ms,
            )
            .returning(strategy_selection_control_current)
        )
        row = result.mappings().one_or_none()
        return None if row is None else _selection_control_from_row(row)

    async def recover_expired_dynamic_activation(
        self,
        request: RecoverExpiredDynamicActivationRequest,
    ) -> RecoverExpiredDynamicActivationResult:
        """Atomically clear one exact expired first-activation transition."""

        generation = (
            await self._connection.execute(
                sa.select(strategy_universe_materialization_generations)
                .where(
                    strategy_universe_materialization_generations.c.materialization_generation_id
                    == request.materialization_generation_id
                )
                .with_for_update(of=strategy_universe_materialization_generations)
            )
        ).mappings().one_or_none()
        vacuum = (
            await self._connection.execute(
                sa.select(strategy_entry_vacuums_current)
                .where(
                    strategy_entry_vacuums_current.c.entry_vacuum_id
                    == request.entry_vacuum_id
                )
                .with_for_update(of=strategy_entry_vacuums_current)
            )
        ).mappings().one_or_none()
        audit = (
            await self._connection.execute(
                sa.select(selection_authority_gap_audits_current)
                .where(
                    selection_authority_gap_audits_current.c.authority_gap_audit_id
                    == request.authority_gap_audit_id
                )
                .with_for_update(of=selection_authority_gap_audits_current)
            )
        ).mappings().one_or_none()
        owner_control = (
            await self._connection.execute(
                sa.select(strategy_entry_controls_current)
                .where(
                    strategy_entry_controls_current.c.strategy_group_id
                    == request.strategy_group_id
                )
                .with_for_update(of=strategy_entry_controls_current)
            )
        ).mappings().one_or_none()
        selection_control = (
            await self._connection.execute(
                sa.select(strategy_selection_control_current)
                .where(
                    strategy_selection_control_current.c.strategy_group_id
                    == request.strategy_group_id
                )
                .with_for_update(of=strategy_selection_control_current)
            )
        ).mappings().one_or_none()
        current_pair = {
            str(row["event_spec_id"]): str(row["universe_version_id"])
            for row in (
                await self._connection.execute(
                    sa.select(strategy_universe_current)
                    .where(
                        strategy_universe_current.c.event_spec_id.in_(
                            (SOR_LONG_EVENT_SPEC_ID, SOR_SHORT_EVENT_SPEC_ID)
                        )
                    )
                    .with_for_update(of=strategy_universe_current)
                )
            ).mappings()
        }
        authority_count = int(
            await self._connection.scalar(
                sa.select(sa.func.count())
                .select_from(selection_session_authorities)
                .where(
                    selection_session_authorities.c.selection_spec_id
                    == request.selection_spec_id,
                    selection_session_authorities.c.session_start_ms
                    == request.session_start_ms,
                )
            )
            or 0
        )
        target_states = tuple(
            await self._connection.scalars(
                sa.select(strategy_universe_materialization_targets.c.event_spec_id)
                .join(
                    strategy_universe_versions,
                    strategy_universe_versions.c.materialization_generation_id
                    == strategy_universe_materialization_targets.c.materialization_generation_id,
                )
                .where(
                    strategy_universe_materialization_targets.c.materialization_generation_id
                    == request.materialization_generation_id,
                    strategy_universe_versions.c.lifecycle_state != "abandoned",
                )
            )
        )
        valid_audit_blockers = {
            "AUTHORITY_GAP_SOURCE_INTEGRITY_FAILED",
            "OWNER_PAUSED",
        }
        if (
            generation is None
            or vacuum is None
            or audit is None
            or owner_control is None
            or selection_control is None
            or generation["strategy_group_id"] != request.strategy_group_id
            or generation["selection_spec_id"] != request.selection_spec_id
            or generation["session_start_ms"] != request.session_start_ms
            or generation["lifecycle_state"] != "ABANDONED"
            or generation["previous_long_universe_version_id"]
            != request.expected_long_universe_version_id
            or generation["previous_short_universe_version_id"]
            != request.expected_short_universe_version_id
            or vacuum["strategy_group_id"] != request.strategy_group_id
            or vacuum["selection_spec_id"] != request.selection_spec_id
            or vacuum["session_start_ms"] != request.session_start_ms
            or vacuum["source_generation_id"]
            != request.materialization_generation_id
            or vacuum["state"] != "OWNER_PAUSED"
            or audit["selection_spec_id"] != request.selection_spec_id
            or audit["session_start_ms"] != request.session_start_ms
            or audit["source_generation_id"]
            != request.materialization_generation_id
            or audit["source_entry_vacuum_id"] != request.entry_vacuum_id
            or audit["state"] != "FAILED"
            or audit["first_blocker"] not in valid_audit_blockers
            or owner_control["entry_state"] != "paused"
            or owner_control["control_version"]
            != request.expected_owner_control_version
            or selection_control["selection_spec_id"] != request.selection_spec_id
            or selection_control["selection_mode"] != "static_baseline"
            or selection_control["pending_selection_mode"] != "dynamic_selection"
            or selection_control["pending_effective_session_start_ms"]
            != request.session_start_ms
            or selection_control["pending_authorization_id"] is None
            or selection_control["control_version"]
            != request.expected_selection_control_version
            or current_pair.get(SOR_LONG_EVENT_SPEC_ID)
            != request.expected_long_universe_version_id
            or current_pair.get(SOR_SHORT_EVENT_SPEC_ID)
            != request.expected_short_universe_version_id
            or authority_count != 0
            or target_states
        ):
            raise ExpiredDynamicActivationRecoveryBlocked(
                "expired_activation_recovery_shape_conflict"
            )

        next_control_version = request.expected_selection_control_version + 1
        control_update = await self._connection.execute(
            sa.update(strategy_selection_control_current)
            .where(
                strategy_selection_control_current.c.strategy_group_id
                == request.strategy_group_id,
                strategy_selection_control_current.c.control_version
                == request.expected_selection_control_version,
                strategy_selection_control_current.c.selection_mode
                == "static_baseline",
                strategy_selection_control_current.c.pending_selection_mode
                == "dynamic_selection",
                strategy_selection_control_current.c.pending_effective_session_start_ms
                == request.session_start_ms,
            )
            .values(
                pending_selection_mode=None,
                pending_effective_session_start_ms=None,
                pending_authorization_id=None,
                control_version=next_control_version,
                updated_at_ms=request.recovered_at_ms,
            )
        )
        if control_update.rowcount != 1:
            raise ExpiredDynamicActivationRecoveryBlocked(
                "selection_control_changed_during_recovery"
            )

        next_generation_version = int(generation["projection_version"]) + 1
        generation_update = await self._connection.execute(
            sa.update(strategy_universe_materialization_generations)
            .where(
                strategy_universe_materialization_generations.c.materialization_generation_id
                == request.materialization_generation_id,
                strategy_universe_materialization_generations.c.lifecycle_state
                == "ABANDONED",
                strategy_universe_materialization_generations.c.projection_version
                == generation["projection_version"],
            )
            .values(
                projection_version=next_generation_version,
            )
        )
        if generation_update.rowcount != 1:
            raise ExpiredDynamicActivationRecoveryBlocked(
                "generation_changed_during_recovery"
            )
        await self._connection.execute(
            sa.insert(strategy_universe_materialization_events).values(
                materialization_event_id=(
                    "materialization-event:"
                    f"{request.materialization_generation_id}:"
                    f"{next_generation_version}"
                ),
                materialization_generation_id=request.materialization_generation_id,
                event_sequence=next_generation_version,
                event_type="EXPIRED_ACTIVATION_RECOVERED",
                payload={
                    "selection_control_version": next_control_version,
                    "owner_control_version": request.expected_owner_control_version,
                    "authority_created": False,
                    "static_pair_preserved": True,
                },
                occurred_at_ms=request.recovered_at_ms,
            )
        )
        return RecoverExpiredDynamicActivationResult(
            status=ExpiredDynamicActivationRecoveryStatus.RECOVERED,
            strategy_group_id=request.strategy_group_id,
            selection_spec_id=request.selection_spec_id,
            session_start_ms=request.session_start_ms,
            materialization_generation_id=request.materialization_generation_id,
            selection_control_version=next_control_version,
            recovered_at_ms=request.recovered_at_ms,
        )

    async def get_snapshot_disposition(
        self,
        *,
        selection_spec_id: str,
        session_start_ms: int,
        for_update: bool = False,
    ) -> SelectionSnapshotDisposition | None:
        statement = sa.select(instrument_selection_snapshots).where(
            instrument_selection_snapshots.c.selection_spec_id == selection_spec_id,
            instrument_selection_snapshots.c.session_start_ms == session_start_ms,
        )
        if for_update:
            statement = statement.with_for_update(of=instrument_selection_snapshots)
        row = (await self._connection.execute(statement)).mappings().one_or_none()
        if row is None:
            return None
        snapshot = SelectionSnapshot.model_validate(dict(row))
        members = tuple(
            str(item)
            for item in (
                await self._connection.execute(
                    sa.select(
                        instrument_selection_member_decisions.c.exchange_instrument_id
                    )
                    .where(
                        instrument_selection_member_decisions.c.selection_snapshot_id
                        == snapshot.selection_snapshot_id,
                        instrument_selection_member_decisions.c.selected.is_(True),
                    )
                    .order_by(
                        instrument_selection_member_decisions.c.exchange_instrument_id
                    )
                    .limit(8)
                )
            ).scalars()
        )
        return SelectionSnapshotDisposition(
            snapshot=snapshot,
            selected_members=members,
            selected_member_set_digest=selected_member_set_digest(members),
        )

    async def add_pending_materialization_generation(
        self,
        generation: MaterializationGeneration,
        *,
        targets: tuple[MaterializationTarget, ...],
    ) -> None:
        if generation.lifecycle_state is not MaterializationGenerationState.PENDING:
            raise ValueError("new Materialization Generation must be PENDING")
        if tuple(item.materialization_order for item in targets) != (1, 2):
            raise ValueError("Materialization Generation requires exact LONG/SHORT targets")
        await self._connection.execute(
            sa.insert(strategy_universe_materialization_generations).values(
                _materialization_generation_values(generation)
            )
        )
        await self._connection.execute(
            sa.insert(strategy_universe_materialization_targets),
            [
                {
                    "materialization_generation_id": (
                        generation.materialization_generation_id
                    ),
                    **target.model_dump(mode="json"),
                }
                for target in targets
            ],
        )
        await self._connection.execute(
            sa.insert(strategy_universe_materialization_events).values(
                materialization_event_id=(
                    f"materialization-event:{generation.materialization_generation_id}:1"
                ),
                materialization_generation_id=generation.materialization_generation_id,
                event_sequence=1,
                event_type="PENDING",
                payload={
                    "selection_snapshot_id": generation.selection_snapshot_id,
                    "desired_member_count": generation.desired_member_count,
                },
                occurred_at_ms=generation.created_at_ms,
            )
        )

    async def get_materialization_generation_for_snapshot(
        self,
        selection_snapshot_id: str,
        *,
        for_update: bool = False,
    ) -> MaterializationGeneration | None:
        statement = sa.select(strategy_universe_materialization_generations).where(
            strategy_universe_materialization_generations.c.selection_snapshot_id
            == selection_snapshot_id
        )
        if for_update:
            statement = statement.with_for_update(
                of=strategy_universe_materialization_generations
            )
        row = (await self._connection.execute(statement)).mappings().one_or_none()
        return None if row is None else _materialization_generation_from_row(row)

    async def get_materialization_generation_for_period(
        self,
        *,
        strategy_group_id: str,
        selection_spec_id: str,
        session_start_ms: int,
    ) -> MaterializationGeneration | None:
        row = (
            await self._connection.execute(
                sa.select(strategy_universe_materialization_generations)
                .where(
                    strategy_universe_materialization_generations.c.strategy_group_id
                    == strategy_group_id,
                    strategy_universe_materialization_generations.c.selection_spec_id
                    == selection_spec_id,
                    strategy_universe_materialization_generations.c.session_start_ms
                    == session_start_ms,
                )
                .limit(1)
            )
        ).mappings().one_or_none()
        return None if row is None else _materialization_generation_from_row(row)

    async def get_materialization_generation(
        self,
        materialization_generation_id: str,
        *,
        for_update: bool = False,
    ) -> MaterializationGeneration | None:
        statement = sa.select(strategy_universe_materialization_generations).where(
            strategy_universe_materialization_generations.c.materialization_generation_id
            == materialization_generation_id
        )
        if for_update:
            statement = statement.with_for_update(
                of=strategy_universe_materialization_generations
            )
        row = (await self._connection.execute(statement)).mappings().one_or_none()
        return None if row is None else _materialization_generation_from_row(row)

    async def get_current_nonterminal_materialization_generation(
        self,
        *,
        strategy_group_id: str,
        selection_spec_id: str,
        for_update: bool = False,
    ) -> MaterializationGeneration | None:
        statement = (
            sa.select(strategy_universe_materialization_generations)
            .where(
                strategy_universe_materialization_generations.c.strategy_group_id
                == strategy_group_id,
                strategy_universe_materialization_generations.c.selection_spec_id
                == selection_spec_id,
                strategy_universe_materialization_generations.c.lifecycle_state.in_(
                    (
                        "PENDING",
                        "DESIRED",
                        "DRAINING_ENTRY",
                        "MATERIALIZING",
                        "STAGED",
                    )
                ),
            )
            .order_by(
                strategy_universe_materialization_generations.c.session_start_ms.desc(),
                strategy_universe_materialization_generations.c.created_at_ms.desc(),
            )
            .limit(2)
        )
        if for_update:
            statement = statement.with_for_update(
                of=strategy_universe_materialization_generations
            )
        rows = (await self._connection.execute(statement)).mappings().all()
        if len(rows) > 1:
            raise SelectionJobConflict(
                "multiple nonterminal Materialization Generations exist"
            )
        return (
            None
            if not rows
            else _materialization_generation_from_row(rows[0])
        )

    async def claim_materialization_generation(
        self,
        *,
        selection_spec_id: str,
        session_start_ms: int,
        worker_id: str,
        now_ms: int,
        lease_duration_ms: int,
    ) -> MaterializationGenerationLeaseClaim:
        normalized_worker_id = str(worker_id or "").strip()
        if not normalized_worker_id:
            raise ValueError("Materialization worker identity must be non-blank")
        if now_ms <= 0 or lease_duration_ms <= 0:
            raise ValueError("Materialization lease timing must be positive")
        row = (
            await self._connection.execute(
                sa.select(strategy_universe_materialization_generations)
                .where(
                    strategy_universe_materialization_generations.c.selection_spec_id
                    == selection_spec_id,
                    strategy_universe_materialization_generations.c.session_start_ms
                    == session_start_ms,
                    strategy_universe_materialization_generations.c.lifecycle_state.in_(
                        (
                            "PENDING",
                            "DESIRED",
                            "DRAINING_ENTRY",
                            "MATERIALIZING",
                            "STAGED",
                        )
                    ),
                )
                .with_for_update(of=strategy_universe_materialization_generations)
            )
        ).mappings().one_or_none()
        if row is None:
            return MaterializationGenerationLeaseClaim(
                status=MaterializationGenerationClaimStatus.NO_GENERATION
            )
        generation = _materialization_generation_from_row(row)
        existing_owner = row["lease_owner"]
        existing_expiry = row["lease_expires_at_ms"]
        if (
            existing_owner is not None
            and str(existing_owner) != normalized_worker_id
            and existing_expiry is not None
            and int(existing_expiry) > now_ms
        ):
            return MaterializationGenerationLeaseClaim(
                status=MaterializationGenerationClaimStatus.LEASE_HELD,
                generation=generation,
                lease_owner=str(existing_owner),
                lease_expires_at_ms=int(existing_expiry),
            )
        lease_expires_at_ms = now_ms + lease_duration_ms
        updated = await self._connection.execute(
            sa.update(strategy_universe_materialization_generations)
            .where(
                strategy_universe_materialization_generations.c.materialization_generation_id
                == generation.materialization_generation_id,
                strategy_universe_materialization_generations.c.lifecycle_state
                == generation.lifecycle_state.value,
                strategy_universe_materialization_generations.c.projection_version
                == generation.projection_version,
            )
            .values(
                lease_owner=normalized_worker_id,
                lease_expires_at_ms=lease_expires_at_ms,
            )
        )
        if updated.rowcount != 1:
            raise SelectionJobConflict("Materialization Generation lease changed")
        return MaterializationGenerationLeaseClaim(
            status=MaterializationGenerationClaimStatus.CLAIMED,
            generation=generation,
            lease_owner=normalized_worker_id,
            lease_expires_at_ms=lease_expires_at_ms,
        )

    async def release_materialization_generation_lease(
        self,
        *,
        materialization_generation_id: str,
        worker_id: str,
    ) -> None:
        normalized_worker_id = str(worker_id or "").strip()
        if not normalized_worker_id:
            raise ValueError("Materialization worker identity must be non-blank")
        await self._connection.execute(
            sa.update(strategy_universe_materialization_generations)
            .where(
                strategy_universe_materialization_generations.c.materialization_generation_id
                == materialization_generation_id,
                strategy_universe_materialization_generations.c.lease_owner
                == normalized_worker_id,
            )
            .values(lease_owner=None, lease_expires_at_ms=None)
        )

    async def mark_materialization_generation_desired(
        self,
        materialization_generation_id: str,
        *,
        expected_projection_version: int,
        desired_at_ms: int,
    ) -> MaterializationGeneration:
        row = (
            await self._connection.execute(
                sa.select(strategy_universe_materialization_generations)
                .where(
                    strategy_universe_materialization_generations.c.materialization_generation_id
                    == materialization_generation_id
                )
                .with_for_update(of=strategy_universe_materialization_generations)
            )
        ).mappings().one_or_none()
        if row is None:
            raise SelectionJobConflict("Materialization Generation does not exist")
        current = _materialization_generation_from_row(row)
        if (
            current.lifecycle_state is not MaterializationGenerationState.PENDING
            or current.projection_version != expected_projection_version
        ):
            raise SelectionJobConflict("Materialization Generation state changed")
        desired = current.model_copy(
            update={
                "lifecycle_state": MaterializationGenerationState.DESIRED,
                "desired_at_ms": desired_at_ms,
                "projection_version": current.projection_version + 1,
            }
        )
        desired = MaterializationGeneration.model_validate(desired.model_dump())
        result = await self._connection.execute(
            sa.update(strategy_universe_materialization_generations)
            .where(
                strategy_universe_materialization_generations.c.materialization_generation_id
                == materialization_generation_id,
                strategy_universe_materialization_generations.c.projection_version
                == expected_projection_version,
                strategy_universe_materialization_generations.c.lifecycle_state
                == "PENDING",
            )
            .values(
                lifecycle_state="DESIRED",
                desired_at_ms=desired_at_ms,
                projection_version=desired.projection_version,
            )
        )
        if result.rowcount != 1:
            raise SelectionJobConflict("Materialization Generation version changed")
        await self._connection.execute(
            sa.insert(strategy_universe_materialization_events).values(
                materialization_event_id=(
                    f"materialization-event:{materialization_generation_id}:2"
                ),
                materialization_generation_id=materialization_generation_id,
                event_sequence=2,
                event_type="DESIRED",
                payload={"projection_version": desired.projection_version},
                occurred_at_ms=desired_at_ms,
            )
        )
        return desired

    async def mark_materialization_generation_abandoned(
        self,
        materialization_generation_id: str,
        *,
        expected_projection_version: int,
        reason_code: str,
        abandoned_at_ms: int,
    ) -> MaterializationGeneration:
        normalized_reason = reason_code.strip()
        if not normalized_reason:
            raise ValueError("abandoned Generation requires reason")
        row = (
            await self._connection.execute(
                sa.select(strategy_universe_materialization_generations)
                .where(
                    strategy_universe_materialization_generations.c.materialization_generation_id
                    == materialization_generation_id
                )
                .with_for_update(of=strategy_universe_materialization_generations)
            )
        ).mappings().one_or_none()
        if row is None:
            raise SelectionJobConflict("Materialization Generation does not exist")
        current = _materialization_generation_from_row(row)
        if (
            current.lifecycle_state is not MaterializationGenerationState.PENDING
            or current.projection_version != expected_projection_version
        ):
            raise SelectionJobConflict("Materialization Generation state changed")
        abandoned = MaterializationGeneration.model_validate(
            current.model_copy(
                update={
                    "lifecycle_state": MaterializationGenerationState.ABANDONED,
                    "projection_version": current.projection_version + 1,
                }
            ).model_dump()
        )
        result = await self._connection.execute(
            sa.update(strategy_universe_materialization_generations)
            .where(
                strategy_universe_materialization_generations.c.materialization_generation_id
                == materialization_generation_id,
                strategy_universe_materialization_generations.c.projection_version
                == expected_projection_version,
                strategy_universe_materialization_generations.c.lifecycle_state
                == "PENDING",
            )
            .values(
                lifecycle_state="ABANDONED",
                terminal_at_ms=abandoned_at_ms,
                projection_version=abandoned.projection_version,
            )
        )
        if result.rowcount != 1:
            raise SelectionJobConflict("Materialization Generation version changed")
        await self._connection.execute(
            sa.insert(strategy_universe_materialization_events).values(
                materialization_event_id=(
                    f"materialization-event:{materialization_generation_id}:2"
                ),
                materialization_generation_id=materialization_generation_id,
                event_sequence=2,
                event_type="ABANDONED",
                payload={
                    "reason_code": normalized_reason,
                    "projection_version": abandoned.projection_version,
                },
                occurred_at_ms=abandoned_at_ms,
            )
        )
        return abandoned

    async def supersede_generation_and_retarget_vacuum(
        self,
        *,
        previous_generation: MaterializationGeneration,
        replacement_generation: MaterializationGeneration,
        replacement_targets: tuple[MaterializationTarget, ...],
        vacuum: StrategyEntryVacuum,
        superseded_at_ms: int,
    ) -> MaterializationGeneration:
        if (
            previous_generation.lifecycle_state
            not in {
                MaterializationGenerationState.MATERIALIZING,
                MaterializationGenerationState.STAGED,
            }
            or replacement_generation.lifecycle_state
            is not MaterializationGenerationState.PENDING
            or replacement_generation.session_start_ms is None
            or previous_generation.session_start_ms is None
            or replacement_generation.session_start_ms
            <= previous_generation.session_start_ms
            or vacuum.state is not StrategyEntryVacuumState.RECONFIGURING
            or vacuum.source_generation_id
            != previous_generation.materialization_generation_id
            or vacuum.drained_at_ms is None
            or vacuum.resolved_at_ms is not None
        ):
            raise ValueError("supersession requires a newer exact drained Generation")
        locked_previous = await self.get_materialization_generation(
            previous_generation.materialization_generation_id,
            for_update=True,
        )
        locked_vacuum = await self.get_current_entry_vacuum(
            strategy_group_id=vacuum.strategy_group_id,
            selection_spec_id=vacuum.selection_spec_id,
            for_update=True,
        )
        if locked_previous != previous_generation or locked_vacuum != vacuum:
            raise SelectionJobConflict("supersession authority changed")
        await self._fail_pending_generation_gap_audits(
            materialization_generation_id=(
                previous_generation.materialization_generation_id
            ),
            first_blocker="SUPERSEDED_BY_NEWER_SELECTION",
            failed_at_ms=superseded_at_ms,
        )
        await self.add_pending_materialization_generation(
            replacement_generation,
            targets=replacement_targets,
        )
        previous_next_version = previous_generation.projection_version + 1
        previous_update = await self._connection.execute(
            sa.update(strategy_universe_materialization_generations)
            .where(
                strategy_universe_materialization_generations.c.materialization_generation_id
                == previous_generation.materialization_generation_id,
                strategy_universe_materialization_generations.c.lifecycle_state
                == previous_generation.lifecycle_state.value,
                strategy_universe_materialization_generations.c.projection_version
                == previous_generation.projection_version,
            )
            .values(
                lifecycle_state="SUPERSEDED",
                terminal_at_ms=superseded_at_ms,
                lease_owner=None,
                lease_expires_at_ms=None,
                projection_version=previous_next_version,
            )
        )
        if previous_update.rowcount != 1:
            raise SelectionJobConflict("previous Generation changed during supersession")
        await self._connection.execute(
            sa.insert(strategy_universe_materialization_events).values(
                materialization_event_id=(
                    "materialization-event:"
                    f"{previous_generation.materialization_generation_id}:"
                    f"{previous_next_version}"
                ),
                materialization_generation_id=(
                    previous_generation.materialization_generation_id
                ),
                event_sequence=previous_next_version,
                event_type="SUPERSEDED",
                payload={
                    "replacement_generation_id": (
                        replacement_generation.materialization_generation_id
                    )
                },
                occurred_at_ms=superseded_at_ms,
            )
        )
        replacement_materializing = MaterializationGeneration.model_validate(
            replacement_generation.model_copy(
                update={
                    "lifecycle_state": MaterializationGenerationState.MATERIALIZING,
                    "desired_at_ms": superseded_at_ms,
                    "projection_version": 4,
                }
            ).model_dump()
        )
        replacement_update = await self._connection.execute(
            sa.update(strategy_universe_materialization_generations)
            .where(
                strategy_universe_materialization_generations.c.materialization_generation_id
                == replacement_generation.materialization_generation_id,
                strategy_universe_materialization_generations.c.lifecycle_state
                == "PENDING",
                strategy_universe_materialization_generations.c.projection_version
                == 1,
            )
            .values(
                lifecycle_state="MATERIALIZING",
                desired_at_ms=superseded_at_ms,
                fenced_at_ms=vacuum.fenced_at_ms,
                projection_version=4,
            )
        )
        if replacement_update.rowcount != 1:
            raise SelectionJobConflict("replacement Generation changed during handoff")
        for sequence, event_type in (
            (2, "DESIRED"),
            (3, "DRAINING_ENTRY"),
            (4, "MATERIALIZING"),
        ):
            await self._connection.execute(
                sa.insert(strategy_universe_materialization_events).values(
                    materialization_event_id=(
                        "materialization-event:"
                        f"{replacement_generation.materialization_generation_id}:"
                        f"{sequence}"
                    ),
                    materialization_generation_id=(
                        replacement_generation.materialization_generation_id
                    ),
                    event_sequence=sequence,
                    event_type=event_type,
                    payload={
                        "supersedes_generation_id": (
                            previous_generation.materialization_generation_id
                        ),
                        "entry_vacuum_id": vacuum.entry_vacuum_id,
                    },
                    occurred_at_ms=superseded_at_ms,
                )
            )
        superseded_vacuum_version = vacuum.projection_version + 1
        retargeted_vacuum_version = vacuum.projection_version + 2
        superseded_vacuum = await self._connection.execute(
            sa.update(strategy_entry_vacuums_current)
            .where(
                strategy_entry_vacuums_current.c.entry_vacuum_id
                == vacuum.entry_vacuum_id,
                strategy_entry_vacuums_current.c.state == "RECONFIGURING",
                strategy_entry_vacuums_current.c.projection_version
                == vacuum.projection_version,
            )
            .values(
                state="SUPERSEDED",
                first_blocker="SUPERSEDED_BY_NEWER_SELECTION",
                projection_version=superseded_vacuum_version,
            )
        )
        if superseded_vacuum.rowcount != 1:
            raise SelectionJobConflict("Vacuum changed during supersession")
        await self._connection.execute(
            sa.insert(strategy_entry_vacuum_events).values(
                entry_vacuum_event_id=(
                    f"vacuum-event:{vacuum.entry_vacuum_id}:"
                    f"{superseded_vacuum_version}"
                ),
                entry_vacuum_id=vacuum.entry_vacuum_id,
                event_sequence=superseded_vacuum_version,
                event_type="SUPERSEDED",
                payload={
                    "previous_generation_id": (
                        previous_generation.materialization_generation_id
                    ),
                    "replacement_generation_id": (
                        replacement_generation.materialization_generation_id
                    ),
                },
                occurred_at_ms=superseded_at_ms,
            )
        )
        retargeted_vacuum = await self._connection.execute(
            sa.update(strategy_entry_vacuums_current)
            .where(
                strategy_entry_vacuums_current.c.entry_vacuum_id
                == vacuum.entry_vacuum_id,
                strategy_entry_vacuums_current.c.state == "SUPERSEDED",
                strategy_entry_vacuums_current.c.projection_version
                == superseded_vacuum_version,
            )
            .values(
                source_generation_id=(
                    replacement_generation.materialization_generation_id
                ),
                state="RECONFIGURING",
                first_blocker="LATEST_VALID_SELECTION",
                projection_version=retargeted_vacuum_version,
            )
        )
        if retargeted_vacuum.rowcount != 1:
            raise SelectionJobConflict("Vacuum retarget failed")
        await self._connection.execute(
            sa.insert(strategy_entry_vacuum_events).values(
                entry_vacuum_event_id=(
                    f"vacuum-event:{vacuum.entry_vacuum_id}:"
                    f"{retargeted_vacuum_version}"
                ),
                entry_vacuum_id=vacuum.entry_vacuum_id,
                event_sequence=retargeted_vacuum_version,
                event_type="RECONFIGURING",
                payload={
                    "source_generation_id": (
                        replacement_generation.materialization_generation_id
                    )
                },
                occurred_at_ms=superseded_at_ms,
            )
        )
        return replacement_materializing

    async def supersede_generation_and_resolve_valid_empty(
        self,
        *,
        previous_generation: MaterializationGeneration,
        snapshot: SelectionSnapshot,
        vacuum: StrategyEntryVacuum,
        superseded_at_ms: int,
    ) -> None:
        if (
            previous_generation.lifecycle_state
            not in {
                MaterializationGenerationState.MATERIALIZING,
                MaterializationGenerationState.STAGED,
            }
            or snapshot.selected_count != 0
            or snapshot.session_start_ms is None
            or previous_generation.session_start_ms is None
            or snapshot.session_start_ms <= previous_generation.session_start_ms
            or vacuum.state is not StrategyEntryVacuumState.RECONFIGURING
            or vacuum.source_generation_id
            != previous_generation.materialization_generation_id
            or vacuum.drained_at_ms is None
            or vacuum.resolved_at_ms is not None
        ):
            raise ValueError(
                "VALID_EMPTY supersession requires a newer zero-member Snapshot "
                "and exact drained Generation Vacuum"
            )
        locked_previous = await self.get_materialization_generation(
            previous_generation.materialization_generation_id,
            for_update=True,
        )
        locked_vacuum = await self.get_current_entry_vacuum(
            strategy_group_id=vacuum.strategy_group_id,
            selection_spec_id=vacuum.selection_spec_id,
            for_update=True,
        )
        if locked_previous != previous_generation or locked_vacuum != vacuum:
            raise SelectionJobConflict("VALID_EMPTY supersession authority changed")
        await self._fail_pending_generation_gap_audits(
            materialization_generation_id=(
                previous_generation.materialization_generation_id
            ),
            first_blocker="SUPERSEDED_BY_NEWER_SELECTION",
            failed_at_ms=superseded_at_ms,
        )

        next_generation_version = previous_generation.projection_version + 1
        generation_update = await self._connection.execute(
            sa.update(strategy_universe_materialization_generations)
            .where(
                strategy_universe_materialization_generations.c.materialization_generation_id
                == previous_generation.materialization_generation_id,
                strategy_universe_materialization_generations.c.lifecycle_state
                == previous_generation.lifecycle_state.value,
                strategy_universe_materialization_generations.c.projection_version
                == previous_generation.projection_version,
            )
            .values(
                lifecycle_state="SUPERSEDED",
                terminal_at_ms=superseded_at_ms,
                lease_owner=None,
                lease_expires_at_ms=None,
                projection_version=next_generation_version,
            )
        )
        if generation_update.rowcount != 1:
            raise SelectionJobConflict(
                "previous Generation changed during VALID_EMPTY supersession"
            )
        await self._connection.execute(
            sa.insert(strategy_universe_materialization_events).values(
                materialization_event_id=(
                    "materialization-event:"
                    f"{previous_generation.materialization_generation_id}:"
                    f"{next_generation_version}"
                ),
                materialization_generation_id=(
                    previous_generation.materialization_generation_id
                ),
                event_sequence=next_generation_version,
                event_type="SUPERSEDED",
                payload={
                    "replacement_selection_snapshot_id": (
                        snapshot.selection_snapshot_id
                    ),
                    "replacement_outcome": AuthorityOutcome.VALID_EMPTY.value,
                },
                occurred_at_ms=superseded_at_ms,
            )
        )

        superseded_vacuum_version = vacuum.projection_version + 1
        resolved_vacuum_version = vacuum.projection_version + 2
        superseded_vacuum = await self._connection.execute(
            sa.update(strategy_entry_vacuums_current)
            .where(
                strategy_entry_vacuums_current.c.entry_vacuum_id
                == vacuum.entry_vacuum_id,
                strategy_entry_vacuums_current.c.state == "RECONFIGURING",
                strategy_entry_vacuums_current.c.projection_version
                == vacuum.projection_version,
            )
            .values(
                state="SUPERSEDED",
                first_blocker="SUPERSEDED_BY_NEWER_VALID_EMPTY",
                projection_version=superseded_vacuum_version,
            )
        )
        if superseded_vacuum.rowcount != 1:
            raise SelectionJobConflict(
                "Vacuum changed during VALID_EMPTY supersession"
            )
        await self._connection.execute(
            sa.insert(strategy_entry_vacuum_events).values(
                entry_vacuum_event_id=(
                    f"vacuum-event:{vacuum.entry_vacuum_id}:"
                    f"{superseded_vacuum_version}"
                ),
                entry_vacuum_id=vacuum.entry_vacuum_id,
                event_sequence=superseded_vacuum_version,
                event_type="SUPERSEDED",
                payload={
                    "previous_generation_id": (
                        previous_generation.materialization_generation_id
                    ),
                    "replacement_selection_snapshot_id": (
                        snapshot.selection_snapshot_id
                    ),
                    "replacement_outcome": AuthorityOutcome.VALID_EMPTY.value,
                },
                occurred_at_ms=superseded_at_ms,
            )
        )
        resolved_vacuum = await self._connection.execute(
            sa.update(strategy_entry_vacuums_current)
            .where(
                strategy_entry_vacuums_current.c.entry_vacuum_id
                == vacuum.entry_vacuum_id,
                strategy_entry_vacuums_current.c.state == "SUPERSEDED",
                strategy_entry_vacuums_current.c.projection_version
                == superseded_vacuum_version,
            )
            .values(
                source_generation_id=None,
                state="VALID_EMPTY",
                first_blocker="NO_SELECTION_READY_MEMBERS",
                resolved_at_ms=superseded_at_ms,
                projection_version=resolved_vacuum_version,
            )
        )
        if resolved_vacuum.rowcount != 1:
            raise SelectionJobConflict("Vacuum VALID_EMPTY resolution failed")
        await self._connection.execute(
            sa.insert(strategy_entry_vacuum_events).values(
                entry_vacuum_event_id=(
                    f"vacuum-event:{vacuum.entry_vacuum_id}:"
                    f"{resolved_vacuum_version}"
                ),
                entry_vacuum_id=vacuum.entry_vacuum_id,
                event_sequence=resolved_vacuum_version,
                event_type="VALID_EMPTY",
                payload={
                    "selection_snapshot_id": snapshot.selection_snapshot_id,
                    "superseded_generation_id": (
                        previous_generation.materialization_generation_id
                    ),
                },
                occurred_at_ms=superseded_at_ms,
            )
        )

    async def mark_generation_fallback_previous_pending(
        self,
        *,
        generation: MaterializationGeneration,
        vacuum: StrategyEntryVacuum,
        reason_code: str,
        marked_at_ms: int,
    ) -> StrategyEntryVacuum:
        normalized_reason = reason_code.strip().lower()
        if not normalized_reason:
            raise ValueError("fallback pending reason must be non-blank")
        if (
            generation.lifecycle_state
            not in {
                MaterializationGenerationState.MATERIALIZING,
                MaterializationGenerationState.STAGED,
            }
            or vacuum.state is not StrategyEntryVacuumState.RECONFIGURING
            or vacuum.source_generation_id
            != generation.materialization_generation_id
            or vacuum.resolved_at_ms is not None
        ):
            raise ValueError("fallback pending requires exact open materialization")
        if vacuum.first_blocker == normalized_reason:
            return vacuum
        locked_generation = await self.get_materialization_generation(
            generation.materialization_generation_id,
            for_update=True,
        )
        locked_vacuum = await self.get_current_entry_vacuum(
            strategy_group_id=vacuum.strategy_group_id,
            selection_spec_id=vacuum.selection_spec_id,
            for_update=True,
        )
        if locked_generation != generation or locked_vacuum != vacuum:
            raise SelectionJobConflict("fallback pending authority changed")
        next_version = vacuum.projection_version + 1
        updated = await self._connection.execute(
            sa.update(strategy_entry_vacuums_current)
            .where(
                strategy_entry_vacuums_current.c.entry_vacuum_id
                == vacuum.entry_vacuum_id,
                strategy_entry_vacuums_current.c.state == "RECONFIGURING",
                strategy_entry_vacuums_current.c.projection_version
                == vacuum.projection_version,
            )
            .values(
                first_blocker=normalized_reason,
                projection_version=next_version,
            )
        )
        if updated.rowcount != 1:
            raise SelectionJobConflict("Vacuum changed before fallback audit")
        await self._connection.execute(
            sa.insert(strategy_entry_vacuum_events).values(
                entry_vacuum_event_id=(
                    f"vacuum-event:{vacuum.entry_vacuum_id}:{next_version}"
                ),
                entry_vacuum_id=vacuum.entry_vacuum_id,
                event_sequence=next_version,
                event_type="FALLBACK_PREVIOUS_PENDING",
                payload={
                    "materialization_generation_id": (
                        generation.materialization_generation_id
                    ),
                    "reason_code": normalized_reason,
                },
                occurred_at_ms=marked_at_ms,
            )
        )
        return StrategyEntryVacuum.model_validate(
            vacuum.model_copy(
                update={
                    "first_blocker": normalized_reason,
                    "projection_version": next_version,
                }
            ).model_dump()
        )

    async def abandon_generation_for_owner_pause(
        self,
        *,
        generation: MaterializationGeneration,
        vacuum: StrategyEntryVacuum,
        paused_at_ms: int,
    ) -> MaterializationGeneration:
        if generation.lifecycle_state not in {
            MaterializationGenerationState.PENDING,
            MaterializationGenerationState.DESIRED,
            MaterializationGenerationState.DRAINING_ENTRY,
            MaterializationGenerationState.MATERIALIZING,
            MaterializationGenerationState.STAGED,
        }:
            raise ValueError("Owner Pause requires a nonterminal Generation")
        if (
            generation.strategy_group_id != vacuum.strategy_group_id
            or generation.selection_spec_id != vacuum.selection_spec_id
            or vacuum.resolved_at_ms is not None
        ):
            raise ValueError("Owner Pause Generation and Vacuum identity differ")
        if generation.lifecycle_state in {
            MaterializationGenerationState.PENDING,
            MaterializationGenerationState.DESIRED,
        }:
            valid_vacuum = bool(
                vacuum.source_generation_id is None
                and vacuum.state
                in {
                    StrategyEntryVacuumState.OPEN,
                    StrategyEntryVacuumState.DRAINING_ENTRY,
                }
                and vacuum.first_blocker == "OWNER_PAUSED"
            )
        elif generation.lifecycle_state is MaterializationGenerationState.DRAINING_ENTRY:
            valid_vacuum = bool(
                vacuum.source_generation_id
                == generation.materialization_generation_id
                and vacuum.state is StrategyEntryVacuumState.DRAINING_ENTRY
            )
        else:
            valid_vacuum = bool(
                vacuum.source_generation_id
                == generation.materialization_generation_id
                and vacuum.state is StrategyEntryVacuumState.RECONFIGURING
            )
        if not valid_vacuum:
            raise ValueError("Owner Pause requires the exact open Generation fence")
        locked_generation = await self.get_materialization_generation(
            generation.materialization_generation_id,
            for_update=True,
        )
        locked_vacuum = await self.get_current_entry_vacuum(
            strategy_group_id=vacuum.strategy_group_id,
            selection_spec_id=vacuum.selection_spec_id,
            for_update=True,
        )
        if locked_generation != generation or locked_vacuum != vacuum:
            raise SelectionJobConflict("Owner Pause materialization authority changed")
        await self._fail_pending_generation_gap_audits(
            materialization_generation_id=generation.materialization_generation_id,
            first_blocker="OWNER_PAUSED",
            failed_at_ms=paused_at_ms,
        )
        abandoned = MaterializationGeneration.model_validate(
            generation.model_copy(
                update={
                    "lifecycle_state": MaterializationGenerationState.ABANDONED,
                    "projection_version": generation.projection_version + 1,
                }
            ).model_dump()
        )
        generation_update = await self._connection.execute(
            sa.update(strategy_universe_materialization_generations)
            .where(
                strategy_universe_materialization_generations.c.materialization_generation_id
                == generation.materialization_generation_id,
                strategy_universe_materialization_generations.c.lifecycle_state
                == generation.lifecycle_state.value,
                strategy_universe_materialization_generations.c.projection_version
                == generation.projection_version,
            )
            .values(
                lifecycle_state="ABANDONED",
                terminal_at_ms=paused_at_ms,
                lease_owner=None,
                lease_expires_at_ms=None,
                projection_version=abandoned.projection_version,
            )
        )
        if generation_update.rowcount != 1:
            raise SelectionJobConflict("Generation changed during Owner Pause")
        await self._connection.execute(
            sa.insert(strategy_universe_materialization_events).values(
                materialization_event_id=(
                    "materialization-event:"
                    f"{generation.materialization_generation_id}:"
                    f"{abandoned.projection_version}"
                ),
                materialization_generation_id=generation.materialization_generation_id,
                event_sequence=abandoned.projection_version,
                event_type="ABANDONED",
                payload={"reason_code": "owner_paused"},
                occurred_at_ms=paused_at_ms,
            )
        )
        if vacuum.source_generation_id is not None:
            vacuum_version = vacuum.projection_version + 1
            target_state = (
                "OWNER_PAUSED"
                if vacuum.state is StrategyEntryVacuumState.RECONFIGURING
                else "DRAINING_ENTRY"
            )
            vacuum_update = await self._connection.execute(
                sa.update(strategy_entry_vacuums_current)
                .where(
                    strategy_entry_vacuums_current.c.entry_vacuum_id
                    == vacuum.entry_vacuum_id,
                    strategy_entry_vacuums_current.c.state == vacuum.state.value,
                    strategy_entry_vacuums_current.c.projection_version
                    == vacuum.projection_version,
                )
                .values(
                    state=target_state,
                    first_blocker="OWNER_PAUSED",
                    projection_version=vacuum_version,
                )
            )
            if vacuum_update.rowcount != 1:
                raise SelectionJobConflict("Vacuum changed during Owner Pause")
            await self._connection.execute(
                sa.insert(strategy_entry_vacuum_events).values(
                    entry_vacuum_event_id=(
                        f"vacuum-event:{vacuum.entry_vacuum_id}:{vacuum_version}"
                    ),
                    entry_vacuum_id=vacuum.entry_vacuum_id,
                    event_sequence=vacuum_version,
                    event_type=(
                        "OWNER_PAUSED"
                        if target_state == "OWNER_PAUSED"
                        else "OWNER_PAUSE_REQUESTED"
                    ),
                    payload={
                        "materialization_generation_id": (
                            generation.materialization_generation_id
                        ),
                        "entry_drain_continues": target_state == "DRAINING_ENTRY",
                    },
                    occurred_at_ms=paused_at_ms,
                )
            )
        return abandoned

    async def get_current_entry_vacuum(
        self,
        *,
        strategy_group_id: str,
        selection_spec_id: str,
        for_update: bool = False,
    ) -> StrategyEntryVacuum | None:
        statement = sa.select(strategy_entry_vacuums_current).where(
            strategy_entry_vacuums_current.c.strategy_group_id == strategy_group_id,
            strategy_entry_vacuums_current.c.selection_spec_id == selection_spec_id,
            strategy_entry_vacuums_current.c.state.in_(_CURRENT_ENTRY_VACUUM_STATES),
        ).order_by(strategy_entry_vacuums_current.c.fenced_at_ms.desc()).limit(1)
        if for_update:
            statement = statement.with_for_update(of=strategy_entry_vacuums_current)
        row = (await self._connection.execute(statement)).mappings().one_or_none()
        return None if row is None else _entry_vacuum_from_row(row)

    async def list_entry_vacuums_for_period(
        self,
        *,
        strategy_group_id: str,
        selection_spec_id: str,
        session_start_ms: int,
        limit: int,
    ) -> tuple[StrategyEntryVacuum, ...]:
        if not 1 <= limit <= 8:
            raise ValueError("Entry Vacuum readonly limit must be between 1 and 8")
        rows = (
            await self._connection.execute(
                sa.select(strategy_entry_vacuums_current)
                .where(
                    strategy_entry_vacuums_current.c.strategy_group_id
                    == strategy_group_id,
                    strategy_entry_vacuums_current.c.selection_spec_id
                    == selection_spec_id,
                    strategy_entry_vacuums_current.c.session_start_ms
                    == session_start_ms,
                )
                .order_by(
                    strategy_entry_vacuums_current.c.fenced_at_ms,
                    strategy_entry_vacuums_current.c.entry_vacuum_id,
                )
                .limit(limit + 1)
            )
        ).mappings().all()
        if len(rows) > limit:
            raise SelectionJobConflict("Entry Vacuum period exceeds readonly bound")
        return tuple(_entry_vacuum_from_row(row) for row in rows)

    async def open_generation_entry_vacuum(
        self,
        vacuum: StrategyEntryVacuum,
        *,
        expected_generation_version: int,
    ) -> None:
        if (
            vacuum.state is not StrategyEntryVacuumState.DRAINING_ENTRY
            or vacuum.source_generation_id is None
            or vacuum.projection_version != 2
        ):
            raise ValueError(
                "Generation Vacuum must include OPEN and DRAINING_ENTRY projections"
            )
        generation = await self.get_materialization_generation(
            vacuum.source_generation_id,
            for_update=True,
        )
        if (
            generation is None
            or generation.lifecycle_state
            is not MaterializationGenerationState.DESIRED
            or generation.projection_version != expected_generation_version
            or generation.strategy_group_id != vacuum.strategy_group_id
            or generation.selection_spec_id != vacuum.selection_spec_id
            or generation.session_start_ms != vacuum.session_start_ms
        ):
            raise SelectionJobConflict("Generation changed before Vacuum fence")
        await self._connection.execute(
            sa.insert(strategy_entry_vacuums_current).values(
                **vacuum.model_dump(mode="json")
            )
        )
        for sequence, event_type in ((1, "OPEN"), (2, "DRAINING_ENTRY")):
            await self._connection.execute(
                sa.insert(strategy_entry_vacuum_events).values(
                    entry_vacuum_event_id=(
                        f"vacuum-event:{vacuum.entry_vacuum_id}:{sequence}"
                    ),
                    entry_vacuum_id=vacuum.entry_vacuum_id,
                    event_sequence=sequence,
                    event_type=event_type,
                    payload={
                        "source_generation_id": vacuum.source_generation_id,
                        "projection_version": vacuum.projection_version,
                    },
                    occurred_at_ms=vacuum.fenced_at_ms,
                )
            )
        updated = await self._connection.execute(
            sa.update(strategy_universe_materialization_generations)
            .where(
                strategy_universe_materialization_generations.c.materialization_generation_id
                == vacuum.source_generation_id,
                strategy_universe_materialization_generations.c.lifecycle_state
                == "DESIRED",
                strategy_universe_materialization_generations.c.projection_version
                == expected_generation_version,
            )
            .values(
                lifecycle_state="DRAINING_ENTRY",
                fenced_at_ms=vacuum.fenced_at_ms,
                projection_version=expected_generation_version + 1,
            )
        )
        if updated.rowcount != 1:
            raise SelectionJobConflict("Generation changed during Vacuum fence")
        await self._connection.execute(
            sa.insert(strategy_universe_materialization_events).values(
                materialization_event_id=(
                    f"materialization-event:{vacuum.source_generation_id}:3"
                ),
                materialization_generation_id=vacuum.source_generation_id,
                event_sequence=3,
                event_type="DRAINING_ENTRY",
                payload={"entry_vacuum_id": vacuum.entry_vacuum_id},
                occurred_at_ms=vacuum.fenced_at_ms,
            )
        )

    async def open_valid_empty_intent_vacuum(
        self,
        vacuum: StrategyEntryVacuum,
        *,
        selection_snapshot_id: str,
    ) -> None:
        if (
            vacuum.state is not StrategyEntryVacuumState.OPEN
            or vacuum.source_generation_id is not None
            or vacuum.first_blocker != "NO_SELECTION_READY_MEMBERS"
        ):
            raise ValueError("VALID_EMPTY intent requires an open generation-free Vacuum")
        await self._connection.execute(
            sa.insert(strategy_entry_vacuums_current).values(
                **vacuum.model_dump(mode="json")
            )
        )
        await self._connection.execute(
            sa.insert(strategy_entry_vacuum_events).values(
                entry_vacuum_event_id=f"vacuum-event:{vacuum.entry_vacuum_id}:1",
                entry_vacuum_id=vacuum.entry_vacuum_id,
                event_sequence=1,
                event_type="OPEN",
                payload={
                    "intended_authority_outcome": AuthorityOutcome.VALID_EMPTY.value,
                    "selection_snapshot_id": selection_snapshot_id,
                },
                occurred_at_ms=vacuum.fenced_at_ms,
            )
        )

    async def open_owner_paused_entry_vacuum(
        self,
        vacuum: StrategyEntryVacuum,
    ) -> StrategyEntryVacuum:
        if (
            vacuum.state is not StrategyEntryVacuumState.OPEN
            or vacuum.source_generation_id is not None
            or vacuum.first_blocker != "OWNER_PAUSED"
        ):
            raise ValueError("Owner Pause requires an open generation-free Vacuum")
        existing = await self.get_current_entry_vacuum(
            strategy_group_id=vacuum.strategy_group_id,
            selection_spec_id=vacuum.selection_spec_id,
            for_update=True,
        )
        if existing is not None:
            return existing
        await self._connection.execute(
            sa.insert(strategy_entry_vacuums_current).values(
                **vacuum.model_dump(mode="json")
            )
        )
        await self._connection.execute(
            sa.insert(strategy_entry_vacuum_events).values(
                entry_vacuum_event_id=f"vacuum-event:{vacuum.entry_vacuum_id}:1",
                entry_vacuum_id=vacuum.entry_vacuum_id,
                event_sequence=1,
                event_type="OPEN",
                payload={"intended_outcome": "OWNER_PAUSED"},
                occurred_at_ms=vacuum.fenced_at_ms,
            )
        )
        return vacuum

    async def mark_entry_vacuum_draining(
        self,
        vacuum: StrategyEntryVacuum,
        *,
        started_at_ms: int,
    ) -> StrategyEntryVacuum:
        if vacuum.state is not StrategyEntryVacuumState.OPEN:
            raise ValueError("only an OPEN Vacuum may start ENTRY drain")
        draining = StrategyEntryVacuum.model_validate(
            vacuum.model_copy(
                update={
                    "state": StrategyEntryVacuumState.DRAINING_ENTRY,
                    "projection_version": vacuum.projection_version + 1,
                }
            ).model_dump()
        )
        updated = await self._connection.execute(
            sa.update(strategy_entry_vacuums_current)
            .where(
                strategy_entry_vacuums_current.c.entry_vacuum_id
                == vacuum.entry_vacuum_id,
                strategy_entry_vacuums_current.c.state == "OPEN",
                strategy_entry_vacuums_current.c.projection_version
                == vacuum.projection_version,
            )
            .values(
                state=draining.state.value,
                projection_version=draining.projection_version,
            )
        )
        if updated.rowcount != 1:
            raise SelectionJobConflict("Vacuum changed before ENTRY drain")
        await self._connection.execute(
            sa.insert(strategy_entry_vacuum_events).values(
                entry_vacuum_event_id=(
                    f"vacuum-event:{vacuum.entry_vacuum_id}:"
                    f"{draining.projection_version}"
                ),
                entry_vacuum_id=vacuum.entry_vacuum_id,
                event_sequence=draining.projection_version,
                event_type="DRAINING_ENTRY",
                payload={"projection_version": draining.projection_version},
                occurred_at_ms=started_at_ms,
            )
        )
        return draining

    async def mark_owner_pause_vacuum_drained(
        self,
        vacuum: StrategyEntryVacuum,
        *,
        drained_at_ms: int,
    ) -> StrategyEntryVacuum:
        if (
            vacuum.state is not StrategyEntryVacuumState.DRAINING_ENTRY
            or vacuum.first_blocker != "OWNER_PAUSED"
        ):
            raise ValueError("Owner Pause drain requires its exact Vacuum")
        if vacuum.source_generation_id is not None:
            generation = await self.get_materialization_generation(
                vacuum.source_generation_id,
                for_update=True,
            )
            if (
                generation is None
                or generation.lifecycle_state
                is not MaterializationGenerationState.ABANDONED
                or generation.strategy_group_id != vacuum.strategy_group_id
                or generation.selection_spec_id != vacuum.selection_spec_id
            ):
                raise SelectionJobConflict(
                    "Owner Pause source Generation is not abandoned"
                )
        paused = StrategyEntryVacuum.model_validate(
            vacuum.model_copy(
                update={
                    "state": StrategyEntryVacuumState.OWNER_PAUSED,
                    "drained_at_ms": drained_at_ms,
                    "projection_version": vacuum.projection_version + 1,
                }
            ).model_dump()
        )
        updated = await self._connection.execute(
            sa.update(strategy_entry_vacuums_current)
            .where(
                strategy_entry_vacuums_current.c.entry_vacuum_id
                == vacuum.entry_vacuum_id,
                strategy_entry_vacuums_current.c.state == "DRAINING_ENTRY",
                strategy_entry_vacuums_current.c.projection_version
                == vacuum.projection_version,
            )
            .values(
                state=paused.state.value,
                drained_at_ms=paused.drained_at_ms,
                projection_version=paused.projection_version,
            )
        )
        if updated.rowcount != 1:
            raise SelectionJobConflict("Owner Pause Vacuum changed during drain")
        await self._connection.execute(
            sa.insert(strategy_entry_vacuum_events).values(
                entry_vacuum_event_id=(
                    f"vacuum-event:{vacuum.entry_vacuum_id}:"
                    f"{paused.projection_version}"
                ),
                entry_vacuum_id=vacuum.entry_vacuum_id,
                event_sequence=paused.projection_version,
                event_type="OWNER_PAUSED",
                payload={"entry_drain_complete": True},
                occurred_at_ms=drained_at_ms,
            )
        )
        return paused

    async def get_next_entry_vacuum_ticket(
        self,
        *,
        strategy_group_id: str,
    ) -> str | None:
        priority = sa.case(
            (trade_aggregates.c.status == "entry_accepted", 1),
            (trade_aggregates.c.status.like("entry_vacuum_%"), 2),
            (trade_aggregates.c.status.like("entry_%"), 3),
            (trade_aggregates.c.status.like("leverage_%"), 4),
            (trade_aggregates.c.status.like("partial_fill_%"), 5),
            (trade_aggregates.c.status == "protection_pending", 6),
            (trade_aggregates.c.status == "initial_stop_outcome_unknown", 7),
            (trade_aggregates.c.status == "post_fill_risk_pending", 8),
            else_=9,
        )
        ticket_id = (
            await self._connection.execute(
                sa.select(trade_aggregates.c.ticket_id)
                .join(
                    trade_tickets,
                    trade_tickets.c.ticket_id == trade_aggregates.c.ticket_id,
                )
                .where(
                    trade_tickets.c.strategy_group_id == strategy_group_id,
                    trade_tickets.c.terminal_at_ms.is_(None),
                    trade_aggregates.c.status.in_(
                        _ENTRY_VACUUM_DRAIN_BLOCKING_STATUSES
                    ),
                )
                .order_by(priority, trade_aggregates.c.updated_at_ms)
                .limit(1)
            )
        ).scalar_one_or_none()
        return None if ticket_id is None else str(ticket_id)

    async def entry_vacuum_has_drain_blockers(
        self,
        *,
        strategy_group_id: str,
    ) -> bool:
        return bool(
            (
                await self._connection.execute(
                    sa.select(
                        sa.exists().where(
                            trade_tickets.c.ticket_id
                            == trade_aggregates.c.ticket_id,
                            trade_tickets.c.strategy_group_id
                            == strategy_group_id,
                            trade_tickets.c.terminal_at_ms.is_(None),
                            trade_aggregates.c.status.in_(
                                _ENTRY_VACUUM_DRAIN_BLOCKING_STATUSES
                            ),
                        )
                    )
                )
            ).scalar_one()
        )

    async def mark_entry_vacuum_drained(
        self,
        vacuum: StrategyEntryVacuum,
        *,
        target_state: Literal["RECONFIGURING", "VALID_EMPTY"],
        drained_at_ms: int,
    ) -> StrategyEntryVacuum:
        if vacuum.state is not StrategyEntryVacuumState.DRAINING_ENTRY:
            raise ValueError("Vacuum drain completion requires DRAINING_ENTRY")
        if await self.entry_vacuum_has_drain_blockers(
            strategy_group_id=vacuum.strategy_group_id
        ):
            raise SelectionJobConflict("Vacuum ENTRY drain still has blockers")
        target = StrategyEntryVacuumState(target_state)
        resolved_at_ms = (
            drained_at_ms
            if target is StrategyEntryVacuumState.VALID_EMPTY
            else None
        )
        drained = StrategyEntryVacuum.model_validate(
            vacuum.model_copy(
                update={
                    "state": target,
                    "drained_at_ms": drained_at_ms,
                    "resolved_at_ms": resolved_at_ms,
                    "projection_version": vacuum.projection_version + 1,
                }
            ).model_dump()
        )
        if (
            target is StrategyEntryVacuumState.RECONFIGURING
            and vacuum.source_generation_id is None
        ):
            raise ValueError("RECONFIGURING requires source Generation")
        updated = await self._connection.execute(
            sa.update(strategy_entry_vacuums_current)
            .where(
                strategy_entry_vacuums_current.c.entry_vacuum_id
                == vacuum.entry_vacuum_id,
                strategy_entry_vacuums_current.c.state == "DRAINING_ENTRY",
                strategy_entry_vacuums_current.c.projection_version
                == vacuum.projection_version,
            )
            .values(
                state=drained.state.value,
                drained_at_ms=drained_at_ms,
                resolved_at_ms=resolved_at_ms,
                projection_version=drained.projection_version,
            )
        )
        if updated.rowcount != 1:
            raise SelectionJobConflict("Vacuum changed before drain completion")
        event_sequence = vacuum.projection_version + 1
        await self._connection.execute(
            sa.insert(strategy_entry_vacuum_events).values(
                entry_vacuum_event_id=(
                    f"vacuum-event:{vacuum.entry_vacuum_id}:{event_sequence}"
                ),
                entry_vacuum_id=vacuum.entry_vacuum_id,
                event_sequence=event_sequence,
                event_type="ENTRY_DRAINED",
                payload={"target_state": target.value},
                occurred_at_ms=drained_at_ms,
            )
        )
        if target is StrategyEntryVacuumState.VALID_EMPTY:
            await self._connection.execute(
                sa.insert(strategy_entry_vacuum_events).values(
                    entry_vacuum_event_id=(
                        f"vacuum-event:{vacuum.entry_vacuum_id}:"
                        f"{event_sequence + 1}"
                    ),
                    entry_vacuum_id=vacuum.entry_vacuum_id,
                    event_sequence=event_sequence + 1,
                    event_type="VALID_EMPTY",
                    payload={"resolved_at_ms": drained_at_ms},
                    occurred_at_ms=drained_at_ms,
                )
            )
            return drained
        assert vacuum.source_generation_id is not None
        generation = await self.get_materialization_generation(
            vacuum.source_generation_id,
            for_update=True,
        )
        if (
            generation is None
            or generation.lifecycle_state
            is not MaterializationGenerationState.DRAINING_ENTRY
        ):
            raise SelectionJobConflict("Generation is not waiting for ENTRY drain")
        generation_update = await self._connection.execute(
            sa.update(strategy_universe_materialization_generations)
            .where(
                strategy_universe_materialization_generations.c.materialization_generation_id
                == generation.materialization_generation_id,
                strategy_universe_materialization_generations.c.lifecycle_state
                == "DRAINING_ENTRY",
                strategy_universe_materialization_generations.c.projection_version
                == generation.projection_version,
            )
            .values(
                lifecycle_state="MATERIALIZING",
                projection_version=generation.projection_version + 1,
            )
        )
        if generation_update.rowcount != 1:
            raise SelectionJobConflict("Generation changed before materialization")
        await self._connection.execute(
            sa.insert(strategy_universe_materialization_events).values(
                materialization_event_id=(
                    f"materialization-event:{generation.materialization_generation_id}:4"
                ),
                materialization_generation_id=(
                    generation.materialization_generation_id
                ),
                event_sequence=4,
                event_type="MATERIALIZING",
                payload={"entry_vacuum_id": vacuum.entry_vacuum_id},
                occurred_at_ms=drained_at_ms,
            )
        )
        return drained

    async def add_pending_authority_gap_audit(
        self,
        audit: AuthorityGapAudit,
    ) -> None:
        if audit.state is not AuthorityGapAuditState.PENDING:
            raise ValueError("new Authority Gap Audit must be PENDING")
        await self._connection.execute(
            sa.insert(selection_authority_gap_audits_current).values(
                **audit.model_dump(mode="json")
            )
        )
        await self._connection.execute(
            sa.insert(selection_authority_gap_audit_events).values(
                authority_gap_audit_event_id=(
                    f"gap-audit-event:{audit.authority_gap_audit_id}:1"
                ),
                authority_gap_audit_id=audit.authority_gap_audit_id,
                event_sequence=1,
                event_type="STARTED",
                payload={
                    "gap_kind": audit.gap_kind.value,
                    "proposed_authority_outcome": (
                        audit.proposed_authority_outcome.value
                    ),
                },
                occurred_at_ms=audit.unauthorized_from_close_time_ms,
            )
        )

    async def get_authority_gap_audit(
        self,
        authority_gap_audit_id: str,
        *,
        for_update: bool = False,
    ) -> AuthorityGapAudit | None:
        statement = sa.select(selection_authority_gap_audits_current).where(
            selection_authority_gap_audits_current.c.authority_gap_audit_id
            == authority_gap_audit_id
        )
        if for_update:
            statement = statement.with_for_update(
                of=selection_authority_gap_audits_current
            )
        row = (await self._connection.execute(statement)).mappings().one_or_none()
        return None if row is None else _authority_gap_audit_from_row(row)

    async def list_authority_gap_audits_for_period(
        self,
        *,
        selection_spec_id: str,
        session_start_ms: int,
        limit: int,
    ) -> tuple[AuthorityGapAudit, ...]:
        if not 1 <= limit <= 8:
            raise ValueError("Authority Gap Audit readonly limit must be between 1 and 8")
        rows = (
            await self._connection.execute(
                sa.select(selection_authority_gap_audits_current)
                .where(
                    selection_authority_gap_audits_current.c.selection_spec_id
                    == selection_spec_id,
                    selection_authority_gap_audits_current.c.session_start_ms
                    == session_start_ms,
                )
                .order_by(
                    selection_authority_gap_audits_current.c.gap_kind,
                    selection_authority_gap_audits_current.c.proposed_authority_outcome,
                    selection_authority_gap_audits_current.c.authority_gap_audit_id,
                )
                .limit(limit + 1)
            )
        ).mappings().all()
        if len(rows) > limit:
            raise SelectionJobConflict("Authority Gap Audit period exceeds readonly bound")
        return tuple(_authority_gap_audit_from_row(row) for row in rows)

    async def add_runtime_release_compatibility_fact(
        self,
        fact: RuntimeReleaseCompatibilityFact,
    ) -> None:
        result = await self._connection.execute(
            pg_insert(runtime_release_compatibility_facts)
            .values(**fact.model_dump(mode="json"))
            .on_conflict_do_nothing()
            .returning(
                runtime_release_compatibility_facts.c.release_compatibility_id
            )
        )
        if result.scalar_one_or_none() is not None:
            return
        existing = await self.get_runtime_release_compatibility_fact(
            fact.release_compatibility_id
        )
        if existing != fact:
            raise SelectionJobConflict("release compatibility fact conflicts")

    async def get_runtime_release_compatibility_fact(
        self,
        release_compatibility_id: str,
    ) -> RuntimeReleaseCompatibilityFact | None:
        row = (
            await self._connection.execute(
                sa.select(runtime_release_compatibility_facts)
                .where(
                    runtime_release_compatibility_facts.c.release_compatibility_id
                    == release_compatibility_id
                )
                .limit(1)
            )
        ).mappings().one_or_none()
        return (
            None
            if row is None
            else RuntimeReleaseCompatibilityFact.model_validate(dict(row))
        )

    async def complete_authority_gap_audit(
        self,
        audit: AuthorityGapAudit,
        *,
        results: tuple[AuthorityGapScopeResult, ...],
        completed_at_ms: int,
    ) -> None:
        if audit.state is not AuthorityGapAuditState.COMPLETE:
            raise ValueError("Authority Gap Audit completion requires COMPLETE proof")
        result = await self._connection.execute(
            sa.update(selection_authority_gap_audits_current)
            .where(
                selection_authority_gap_audits_current.c.authority_gap_audit_id
                == audit.authority_gap_audit_id,
                selection_authority_gap_audits_current.c.state == "PENDING",
                selection_authority_gap_audits_current.c.projection_version
                == audit.projection_version - 1,
            )
            .values(
                audited_through_close_time_ms=audit.audited_through_close_time_ms,
                first_eligible_close_time_ms=audit.first_eligible_close_time_ms,
                audit_scope_digest=audit.audit_scope_digest,
                audit_result_digest=audit.audit_result_digest,
                state=audit.state.value,
                first_blocker=None,
                projection_version=audit.projection_version,
            )
        )
        if result.rowcount != 1:
            raise SelectionJobConflict("Authority Gap Audit version changed")
        sequence = 2
        for item in sorted(
            results,
            key=lambda value: (
                value.scope.event_spec_id,
                value.scope.exchange_instrument_id,
            ),
        ):
            event_type = (
                "TRIGGER_SUPPRESSED" if item.trigger_consumed else "CHECKED_NEGATIVE"
            )
            await self._connection.execute(
                sa.insert(selection_authority_gap_audit_events).values(
                    authority_gap_audit_event_id=(
                        f"gap-audit-event:{audit.authority_gap_audit_id}:{sequence}"
                    ),
                    authority_gap_audit_id=audit.authority_gap_audit_id,
                    event_sequence=sequence,
                    event_type=event_type,
                    payload=item.model_dump(mode="json"),
                    occurred_at_ms=completed_at_ms,
                )
            )
            if item.first_natural_trigger_at_ms is not None:
                suppression = StrategyTriggerSuppression(
                    trigger_suppression_id=(
                        f"trigger-suppression:{audit.authority_gap_audit_id}:"
                        f"{item.scope.event_spec_id}:{item.scope.exchange_instrument_id}"
                    ),
                    authority_gap_audit_id=audit.authority_gap_audit_id,
                    entry_vacuum_id=audit.source_entry_vacuum_id,
                    materialization_generation_id=audit.source_generation_id,
                    event_spec_id=item.scope.event_spec_id,
                    exchange_instrument_id=item.scope.exchange_instrument_id,
                    session_reference=item.session_reference,
                    first_natural_trigger_at_ms=item.first_natural_trigger_at_ms,
                    detector_semantic_digest=audit.detector_semantic_digest,
                    created_at_ms=completed_at_ms,
                )
                await self._connection.execute(
                    sa.insert(strategy_trigger_suppressions).values(
                        **suppression.model_dump(mode="json")
                    )
                )
            sequence += 1
        await self._connection.execute(
            sa.insert(selection_authority_gap_audit_events).values(
                authority_gap_audit_event_id=(
                    f"gap-audit-event:{audit.authority_gap_audit_id}:{sequence}"
                ),
                authority_gap_audit_id=audit.authority_gap_audit_id,
                event_sequence=sequence,
                event_type="COMPLETE",
                payload={
                    "audit_scope_digest": audit.audit_scope_digest,
                    "audit_result_digest": audit.audit_result_digest,
                    "first_eligible_close_time_ms": audit.first_eligible_close_time_ms,
                },
                occurred_at_ms=completed_at_ms,
            )
        )

    async def fail_authority_gap_audit(
        self,
        audit: AuthorityGapAudit,
        *,
        failed_at_ms: int,
    ) -> None:
        if audit.state is not AuthorityGapAuditState.FAILED:
            raise ValueError("Authority Gap Audit failure requires FAILED state")
        result = await self._connection.execute(
            sa.update(selection_authority_gap_audits_current)
            .where(
                selection_authority_gap_audits_current.c.authority_gap_audit_id
                == audit.authority_gap_audit_id,
                selection_authority_gap_audits_current.c.state == "PENDING",
                selection_authority_gap_audits_current.c.projection_version
                == audit.projection_version - 1,
            )
            .values(
                state=audit.state.value,
                first_blocker=audit.first_blocker,
                projection_version=audit.projection_version,
            )
        )
        if result.rowcount != 1:
            raise SelectionJobConflict("Authority Gap Audit version changed")
        await self._connection.execute(
            sa.insert(selection_authority_gap_audit_events).values(
                authority_gap_audit_event_id=(
                    f"gap-audit-event:{audit.authority_gap_audit_id}:2"
                ),
                authority_gap_audit_id=audit.authority_gap_audit_id,
                event_sequence=2,
                event_type="FAILED",
                payload={"first_blocker": audit.first_blocker},
                occurred_at_ms=failed_at_ms,
            )
        )

    async def _fail_pending_generation_gap_audits(
        self,
        *,
        materialization_generation_id: str,
        first_blocker: str,
        failed_at_ms: int,
    ) -> None:
        rows = (
            await self._connection.execute(
                sa.select(selection_authority_gap_audits_current)
                .where(
                    selection_authority_gap_audits_current.c.source_generation_id
                    == materialization_generation_id,
                    selection_authority_gap_audits_current.c.state == "PENDING",
                )
                .order_by(
                    selection_authority_gap_audits_current.c.authority_gap_audit_id
                )
                .limit(3)
                .with_for_update(of=selection_authority_gap_audits_current)
            )
        ).mappings().all()
        if len(rows) > 2:
            raise SelectionJobConflict(
                "Generation owns more pending Gap Audits than approved outcomes"
            )
        for row in rows:
            next_version = int(row["projection_version"]) + 1
            updated = await self._connection.execute(
                sa.update(selection_authority_gap_audits_current)
                .where(
                    selection_authority_gap_audits_current.c.authority_gap_audit_id
                    == row["authority_gap_audit_id"],
                    selection_authority_gap_audits_current.c.state == "PENDING",
                    selection_authority_gap_audits_current.c.projection_version
                    == row["projection_version"],
                )
                .values(
                    state="FAILED",
                    first_blocker=first_blocker,
                    projection_version=next_version,
                )
            )
            if updated.rowcount != 1:
                raise SelectionJobConflict(
                    "Generation Gap Audit changed during terminal transition"
                )
            await self._connection.execute(
                sa.insert(selection_authority_gap_audit_events).values(
                    authority_gap_audit_event_id=(
                        "gap-audit-event:"
                        f"{row['authority_gap_audit_id']}:{next_version}"
                    ),
                    authority_gap_audit_id=row["authority_gap_audit_id"],
                    event_sequence=next_version,
                    event_type="FAILED",
                    payload={"first_blocker": first_blocker},
                    occurred_at_ms=failed_at_ms,
                )
            )

    async def add_authority_and_set_current(
        self,
        authority: SelectionSessionAuthority,
        *,
        expected_current_version: int | None,
    ) -> None:
        """Append one Authority and atomically advance its current pointer."""

        await self._connection.execute(
            sa.insert(selection_session_authorities).values(
                _authority_values(authority)
            )
        )
        if expected_current_version is None:
            result = await self._connection.execute(
                pg_insert(selection_authority_current)
                .values(
                    selection_spec_id=authority.selection_spec_id,
                    selection_authority_id=authority.selection_authority_id,
                    projection_version=1,
                    updated_at_ms=authority.created_at_ms,
                )
                .on_conflict_do_nothing(
                    index_elements=[selection_authority_current.c.selection_spec_id]
                )
            )
        else:
            result = await self._connection.execute(
                sa.update(selection_authority_current)
                .where(
                    selection_authority_current.c.selection_spec_id
                    == authority.selection_spec_id,
                    selection_authority_current.c.projection_version
                    == expected_current_version,
                )
                .values(
                    selection_authority_id=authority.selection_authority_id,
                    projection_version=expected_current_version + 1,
                    updated_at_ms=authority.created_at_ms,
                )
            )
        if result.rowcount != 1:
            raise SelectionAuthorityVersionConflict(
                "Selection Authority current pointer version changed"
            )

    async def get_current_authority(
        self,
        selection_spec_id: str,
        *,
        for_update: bool = False,
    ) -> SelectionSessionAuthority | None:
        projection = await self.get_current_authority_projection(
            selection_spec_id,
            for_update=for_update,
        )
        return None if projection is None else projection.authority

    async def get_current_authority_projection(
        self,
        selection_spec_id: str,
        *,
        for_update: bool = False,
    ) -> CurrentSelectionAuthority | None:
        statement = (
            sa.select(
                selection_session_authorities,
                selection_authority_current.c.projection_version.label(
                    "current_projection_version"
                ),
            )
            .join(
                selection_authority_current,
                selection_authority_current.c.selection_authority_id
                == selection_session_authorities.c.selection_authority_id,
            )
            .where(
                selection_authority_current.c.selection_spec_id
                == selection_spec_id
            )
            .limit(1)
        )
        if for_update:
            statement = statement.with_for_update(of=selection_authority_current)
        row = (await self._connection.execute(statement)).mappings().one_or_none()
        if row is None:
            return None
        return CurrentSelectionAuthority(
            authority=_authority_from_row(row),
            projection_version=int(row["current_projection_version"]),
        )


def _authority_values(authority: SelectionSessionAuthority) -> dict[str, object]:
    pair = authority.authorized_pair
    proof = authority.grant_proof
    return {
        "selection_authority_id": authority.selection_authority_id,
        "selection_spec_id": authority.selection_spec_id,
        "session_start_ms": authority.session_start_ms,
        "decision_boundary_ms": authority.decision_boundary_ms,
        "authority_sequence": authority.authority_sequence,
        "selection_mode": authority.selection_mode.value,
        "selection_job_id": None,
        "selection_attempt_id": None,
        "selection_snapshot_id": authority.selection_snapshot_id,
        "continued_from_selection_authority_id": (
            authority.continued_from_selection_authority_id
        ),
        "continuity_source_kind": authority.continuity_source_kind.value,
        "authority_gap_audit_id": authority.authority_gap_audit_id,
        "materialization_generation_id": authority.materialization_generation_id,
        "owner_control_version": authority.owner_control_version,
        "authority_outcome": authority.authority_outcome.value,
        "authorized_long_universe_version_id": (
            None if pair is None else pair.long_universe_version_id
        ),
        "authorized_short_universe_version_id": (
            None if pair is None else pair.short_universe_version_id
        ),
        "grant_proof_kind": None if proof is None else proof.kind.value,
        "grant_predecessor_authority_id": (
            None if proof is None else proof.predecessor_authority_id
        ),
        "effective_from_ms": authority.effective_from_ms,
        "first_eligible_close_time_ms": authority.first_eligible_close_time_ms,
        "expires_at_ms": authority.expires_at_ms,
        "reason_code": authority.reason_code,
        "semantic_digest": authority.semantic_digest,
        "created_at_ms": authority.created_at_ms,
    }


def _authority_from_row(row: RowMapping) -> SelectionSessionAuthority:
    long_id = row["authorized_long_universe_version_id"]
    short_id = row["authorized_short_universe_version_id"]
    pair = (
        None
        if long_id is None or short_id is None
        else UniverseAuthorityPair(
            long_universe_version_id=str(long_id),
            short_universe_version_id=str(short_id),
        )
    )
    proof_kind = row["grant_proof_kind"]
    proof = (
        None
        if proof_kind is None
        else AuthorityGrantProof(
            kind=AuthorityGrantProofKind(str(proof_kind)),
            predecessor_authority_id=row["grant_predecessor_authority_id"],
            authority_gap_audit_id=row["authority_gap_audit_id"],
        )
    )
    return SelectionSessionAuthority(
        selection_authority_id=str(row["selection_authority_id"]),
        selection_spec_id=str(row["selection_spec_id"]),
        session_start_ms=int(row["session_start_ms"]),
        decision_boundary_ms=int(row["decision_boundary_ms"]),
        authority_sequence=int(row["authority_sequence"]),
        selection_mode=SelectionMode(str(row["selection_mode"])),
        selection_snapshot_id=row["selection_snapshot_id"],
        continued_from_selection_authority_id=row[
            "continued_from_selection_authority_id"
        ],
        continuity_source_kind=ContinuitySourceKind(
            str(row["continuity_source_kind"])
        ),
        authority_gap_audit_id=row["authority_gap_audit_id"],
        materialization_generation_id=row["materialization_generation_id"],
        owner_control_version=int(row["owner_control_version"]),
        authority_outcome=AuthorityOutcome(str(row["authority_outcome"])),
        authorized_pair=pair,
        grant_proof=proof,
        effective_from_ms=int(row["effective_from_ms"]),
        first_eligible_close_time_ms=(
            None
            if row["first_eligible_close_time_ms"] is None
            else int(row["first_eligible_close_time_ms"])
        ),
        expires_at_ms=int(row["expires_at_ms"]),
        reason_code=str(row["reason_code"]),
        created_at_ms=int(row["created_at_ms"]),
    )


def _selection_control_from_row(row: RowMapping) -> SelectionControl:
    pending_mode = row["pending_selection_mode"]
    return SelectionControl(
        strategy_group_id=str(row["strategy_group_id"]),
        selection_spec_id=str(row["selection_spec_id"]),
        selection_mode=SelectionMode(str(row["selection_mode"])),
        pending_selection_mode=(
            None if pending_mode is None else SelectionMode(str(pending_mode))
        ),
        pending_effective_session_start_ms=(
            None
            if row["pending_effective_session_start_ms"] is None
            else int(row["pending_effective_session_start_ms"])
        ),
        pending_authorization_id=row["pending_authorization_id"],
        control_version=int(row["control_version"]),
        rollback_baseline_id=row["rollback_baseline_id"],
        updated_at_ms=int(row["updated_at_ms"]),
    )


def _materialization_generation_values(
    generation: MaterializationGeneration,
) -> dict[str, object]:
    return {
        "materialization_generation_id": generation.materialization_generation_id,
        "selection_spec_id": generation.selection_spec_id,
        "strategy_group_id": generation.strategy_group_id,
        "strategy_version_id": generation.strategy_version_id,
        "selection_mode": generation.selection_mode.value,
        "selection_snapshot_id": generation.selection_snapshot_id,
        "rollback_baseline_id": generation.rollback_baseline_id,
        "session_start_ms": generation.session_start_ms,
        "previous_long_universe_version_id": (
            generation.previous_long_universe_version_id
        ),
        "previous_short_universe_version_id": (
            generation.previous_short_universe_version_id
        ),
        "desired_member_count": generation.desired_member_count,
        "semantic_digest": generation.semantic_digest,
        "lifecycle_state": generation.lifecycle_state.value,
        "fallback_reason_code": generation.fallback_reason_code,
        "lease_owner": None,
        "lease_expires_at_ms": None,
        "projection_version": generation.projection_version,
        "created_at_ms": generation.created_at_ms,
        "desired_at_ms": generation.desired_at_ms,
        "fenced_at_ms": None,
        "activated_at_ms": None,
        "fallback_at_ms": None,
        "terminal_at_ms": None,
    }


def _materialization_generation_from_row(
    row: RowMapping,
) -> MaterializationGeneration:
    return MaterializationGeneration(
        materialization_generation_id=str(row["materialization_generation_id"]),
        selection_spec_id=str(row["selection_spec_id"]),
        strategy_group_id=str(row["strategy_group_id"]),
        strategy_version_id=str(row["strategy_version_id"]),
        selection_mode=SelectionMode(str(row["selection_mode"])),
        selection_snapshot_id=row["selection_snapshot_id"],
        rollback_baseline_id=row["rollback_baseline_id"],
        session_start_ms=(
            None if row["session_start_ms"] is None else int(row["session_start_ms"])
        ),
        previous_long_universe_version_id=str(
            row["previous_long_universe_version_id"]
        ),
        previous_short_universe_version_id=str(
            row["previous_short_universe_version_id"]
        ),
        desired_member_count=int(row["desired_member_count"]),
        semantic_digest=str(row["semantic_digest"]),
        lifecycle_state=MaterializationGenerationState(str(row["lifecycle_state"])),
        fallback_reason_code=row["fallback_reason_code"],
        projection_version=int(row["projection_version"]),
        created_at_ms=int(row["created_at_ms"]),
        desired_at_ms=(
            None if row["desired_at_ms"] is None else int(row["desired_at_ms"])
        ),
    )


def _entry_vacuum_from_row(row: RowMapping) -> StrategyEntryVacuum:
    return StrategyEntryVacuum(
        entry_vacuum_id=str(row["entry_vacuum_id"]),
        strategy_group_id=str(row["strategy_group_id"]),
        selection_spec_id=str(row["selection_spec_id"]),
        session_start_ms=int(row["session_start_ms"]),
        source_generation_id=row["source_generation_id"],
        state=StrategyEntryVacuumState(str(row["state"])),
        fenced_at_ms=int(row["fenced_at_ms"]),
        drained_at_ms=(
            None if row["drained_at_ms"] is None else int(row["drained_at_ms"])
        ),
        resolved_at_ms=(
            None if row["resolved_at_ms"] is None else int(row["resolved_at_ms"])
        ),
        first_blocker=str(row["first_blocker"]),
        projection_version=int(row["projection_version"]),
    )


def _authority_gap_audit_from_row(row: RowMapping) -> AuthorityGapAudit:
    return AuthorityGapAudit(
        authority_gap_audit_id=str(row["authority_gap_audit_id"]),
        selection_spec_id=str(row["selection_spec_id"]),
        session_start_ms=int(row["session_start_ms"]),
        gap_kind=AuthorityGapAuditKind(str(row["gap_kind"])),
        source_entry_vacuum_id=row["source_entry_vacuum_id"],
        source_generation_id=row["source_generation_id"],
        proposed_authority_outcome=AuthorityOutcome(
            str(row["proposed_authority_outcome"])
        ),
        unauthorized_from_close_time_ms=int(
            row["unauthorized_from_close_time_ms"]
        ),
        audited_through_close_time_ms=(
            None
            if row["audited_through_close_time_ms"] is None
            else int(row["audited_through_close_time_ms"])
        ),
        first_eligible_close_time_ms=(
            None
            if row["first_eligible_close_time_ms"] is None
            else int(row["first_eligible_close_time_ms"])
        ),
        audit_scope_digest=row["audit_scope_digest"],
        audit_result_digest=row["audit_result_digest"],
        detector_semantic_digest=str(row["detector_semantic_digest"]),
        state=AuthorityGapAuditState(str(row["state"])),
        first_blocker=row["first_blocker"],
        projection_version=int(row["projection_version"]),
    )
