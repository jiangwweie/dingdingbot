"""PostgreSQL ownership for Dynamic Selection facts and current Authority."""

from __future__ import annotations

from typing import ClassVar, Literal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

from src.trading_kernel.domain.instrument_selection import (
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
    AuthorityGrantProof,
    AuthorityGrantProofKind,
    AuthorityOutcome,
    ContinuitySourceKind,
    SelectionMode,
    SelectionSessionAuthority,
    UniverseAuthorityPair,
)
from src.trading_kernel.infrastructure.pg_models import (
    instrument_selection_attempts,
    instrument_selection_jobs_current,
    instrument_selection_member_decisions,
    instrument_selection_snapshots,
    instrument_selection_spec_events,
    instrument_selection_spec_members,
    instrument_selection_specs,
    selection_authority_current,
    selection_session_authorities,
    sor_dynamic_selection_specs_v0,
)

LeaseKind = Literal["selection", "materialization", "observation"]


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
    ) -> SelectionSessionAuthority | None:
        row = (
            await self._connection.execute(
                sa.select(selection_session_authorities)
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
        ).mappings().one_or_none()
        return None if row is None else _authority_from_row(row)


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
