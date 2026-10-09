"""PostgreSQL ownership for Dynamic Selection facts and current Authority."""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from typing import ClassVar, Literal, cast

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

from src.trading_kernel.application.ports import (
    SelectionJobRecord,
    SelectionPersistenceConflict,
)
from src.trading_kernel.application.recover_expired_dynamic_activation import (
    ExpiredDynamicActivationRecoveryBlocked,
    ExpiredDynamicActivationRecoveryStatus,
    RecoverExpiredDynamicActivationRequest,
    RecoverExpiredDynamicActivationResult,
)
from src.trading_kernel.application.runtime import RuntimeReleaseCompatibilityFact
from src.trading_kernel.domain.authority_recovery_rebase import (
    AuthorityRecoveryCheckpoint,
    begin_authority_recovery_rebase,
)
from src.trading_kernel.domain.comparison_universe import ComparisonUniverseBinding
from src.trading_kernel.domain.dynamic_selection_timing import (
    CurrentFinalCloseGrantProof,
    DynamicMembershipState,
    GenericContinuityCloseProof,
    build_dynamic_membership_freshness,
    build_generic_selection_period,
    missed_closes_at_gap_fence,
    plan_hourly_recovery_close,
    record_dynamic_selection_miss,
    require_current_close_commit,
    require_generic_continuity_commit,
    require_hourly_recovery_commit,
    uncovered_close_count_since_gap,
)
from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.exposure_episode import (
    ExposureEpisodeState,
    build_episode_domain_key,
)
from src.trading_kernel.domain.generic_materialization import (
    GenericMaterializationGeneration,
    GenericMaterializationLeaseClaim,
    GenericStaticActivationProof,
    GenericStaticMaterializationGeneration,
    GenericStaticRollbackBaseline,
    GenericStaticRollbackEvent,
    MaterializationEventBaseline,
)
from src.trading_kernel.domain.generic_selection_core import (
    GenericSelectionMemberDecision,
    GenericSelectionSnapshotV1,
)
from src.trading_kernel.domain.generic_selection_jobs import (
    GENERIC_SOURCE_MAX_ATTEMPTS,
    GENERIC_SOURCE_RETRY_BACKOFF_MS,
    GenericSelectionJobClaim,
    SelectionJobLease,
    job_period_anchor,
    job_selection_epoch,
    selection_job_identity,
)
from src.trading_kernel.domain.generic_selection_source import (
    GenericSelectionQualification,
)
from src.trading_kernel.domain.generic_selection_spec import (
    GenericSelectionSpecV1,
    SpecNumericInstallationEvidence,
)
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
from src.trading_kernel.domain.product import InstrumentProductProfile
from src.trading_kernel.domain.selection_authority import (
    AuthorityEventBinding,
    AuthorityEventGrantState,
    AuthorityGapAudit,
    AuthorityGapAuditKind,
    AuthorityGapAuditState,
    AuthorityGapScopeResult,
    AuthorityGrantProof,
    AuthorityGrantProofKind,
    AuthorityOutcome,
    ContinuitySourceKind,
    CurrentGenericSelectionAuthority,
    CurrentSelectionAuthority,
    GenericRecoveryAuthority,
    GenericRecoveryGrantProof,
    GenericSelectionAuthority,
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
    selected_member_set_digest,
)
from src.trading_kernel.domain.strategy_entry_vacuum import (
    StrategyEntryVacuum,
    StrategyEntryVacuumState,
)
from src.trading_kernel.domain.strategy_universe import StrategyUniverseVersion
from src.trading_kernel.infrastructure.pg_models import (
    comparison_binding_current,
    comparison_universe_definitions,
    comparison_universe_members,
    exposure_episode_current,
    generic_dynamic_selection_specs_v1,
    instrument_product_profiles,
    instrument_selection_attempts,
    instrument_selection_jobs_current,
    instrument_selection_member_decisions,
    instrument_selection_snapshots,
    instrument_selection_spec_events,
    instrument_selection_spec_members,
    instrument_selection_specs,
    instruments,
    materialization_generation_event_baselines,
    materialization_generation_projection_columns,
    owner_authorizations,
    owner_policy_current,
    runtime_release_compatibility_facts,
    runtime_scopes_current,
    selection_authority_current,
    selection_authority_event_bindings,
    selection_authority_gap_audit_events,
    selection_authority_gap_audits_current,
    selection_authority_projection_columns,
    selection_rollback_baseline_events,
    selection_session_authorities,
    sor_dynamic_selection_specs_v0,
    strategy_entry_controls_current,
    strategy_entry_vacuum_events,
    strategy_entry_vacuums_current,
    strategy_selection_control_current,
    strategy_selection_rollback_baselines,
    strategy_trigger_suppressions,
    strategy_universe_current,
    strategy_universe_materialization_events,
    strategy_universe_materialization_generations,
    strategy_universe_materialization_targets,
    strategy_universe_members,
    strategy_universe_versions,
    trade_aggregates,
    trade_tickets,
)
from src.trading_kernel.infrastructure.pg_selection_event_bindings import (
    sor_authority_pair_from_bindings,
)

LeaseKind = Literal["selection", "materialization", "observation"]
_CURRENT_ENTRY_VACUUM_STATES = (
    "OPEN",
    "DRAINING_ENTRY",
    "RECONFIGURING",
    "RECOVERY_PENDING",
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


class SelectionJobConflict(SelectionPersistenceConflict):
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

    async def get_generic_snapshot(self, selection_snapshot_id: str) -> GenericSelectionSnapshotV1:
        row = (await self._connection.execute(sa.select(instrument_selection_snapshots).where(
            instrument_selection_snapshots.c.selection_snapshot_id == selection_snapshot_id,
            instrument_selection_snapshots.c.selection_family == "generic_dynamic_v1",
        ))).mappings().one_or_none()
        if row is None:
            raise SelectionJobConflict("Generic Selection Snapshot does not exist")
        spec = await self.get_generic_spec(row["selection_spec_id"])
        rows = (await self._connection.execute(sa.select(instrument_selection_member_decisions).where(
            instrument_selection_member_decisions.c.selection_snapshot_id == selection_snapshot_id,
        ).order_by(instrument_selection_member_decisions.c.stable_rank))).mappings().all()
        members = tuple(GenericSelectionMemberDecision(
            exchange_instrument_id=member["exchange_instrument_id"], feature_value=member["feature_value"],
            stable_rank=member["stable_rank"], qualified=member["selection_ready"], selected=member["selected"],
            retained=member["retained"], input_window_digest=member["input_window_digest"],
            qualification=GenericSelectionQualification.model_validate(member["qualification_fact"]),
        ) for member in rows)
        if any(member.semantic_digest != row["member_semantic_digest"] for member, row in zip(members, rows, strict=True)):
            raise SelectionJobConflict("Generic member semantic digest differs")
        if any(member.qualification_semantic_digest != row["qualification_semantic_digest"] or member.qualification_reason != row["primary_reason"]
               for member, row in zip(members, rows, strict=True)):
            raise SelectionJobConflict("Generic qualification fact digest or reason differs")
        snapshot = GenericSelectionSnapshotV1(
            selection_snapshot_id=selection_snapshot_id, selection_spec_id=spec.selection_spec_id,
            strategy_group_id=spec.strategy_group_id, spec_semantic_digest=spec.algorithm_semantic_digest,
            selection_epoch_id=row["selection_epoch_id"], feature_cutoff_at_ms=row["feature_cutoff_at_ms"],
            effective_from_ms=row["eligibility_not_before_ms"], expires_at_ms=row["expires_at_ms"],
            committed_at_ms=row["created_at_ms"], predecessor_snapshot_id=row["predecessor_snapshot_id"],
            predecessor_member_digest=row["predecessor_member_digest"], members=members,
            source_semantic_digest=row["source_semantic_digest"],
        )
        if snapshot.semantic_digest != row["selection_semantic_digest"]:
            raise SelectionJobConflict("Generic Snapshot semantic digest differs")
        return snapshot

    async def save_generic_snapshot(self, snapshot: GenericSelectionSnapshotV1, *,
                                    decision_at_ms: int, source_observed_at_ms: int) -> None:
        """Commit Desired facts only; caller owns the Selection job transaction."""
        snapshot = GenericSelectionSnapshotV1.model_validate(snapshot.model_dump(mode="python"))
        spec = await self.get_generic_spec(snapshot.selection_spec_id)
        if not snapshot.feature_cutoff_at_ms <= decision_at_ms <= source_observed_at_ms <= snapshot.committed_at_ms:
            raise ValueError("Generic Snapshot decision/source/commit time mismatch")
        # Serialize a Spec's Desired lineage, never a Universe or trading lane.
        await self._connection.execute(sa.select(instrument_selection_specs.c.selection_spec_id).where(
            instrument_selection_specs.c.selection_spec_id == spec.selection_spec_id,
        ).with_for_update())
        existing = (await self._connection.execute(sa.select(instrument_selection_snapshots).where(
            instrument_selection_snapshots.c.selection_spec_id == spec.selection_spec_id,
            instrument_selection_snapshots.c.selection_epoch_id == snapshot.selection_epoch_id,
            instrument_selection_snapshots.c.period_anchor_ms == snapshot.feature_cutoff_at_ms,
        ))).mappings().one_or_none()
        if existing is not None:
            if (await self.get_generic_snapshot(existing["selection_snapshot_id"]) != snapshot
                or existing["decision_at_ms"] != decision_at_ms or existing["source_observed_at_ms"] != source_observed_at_ms):
                raise SelectionJobConflict("Generic Snapshot period already committed with different facts")
            return
        prior_row = (await self._connection.execute(sa.select(instrument_selection_snapshots).where(
            instrument_selection_snapshots.c.selection_spec_id == spec.selection_spec_id,
            instrument_selection_snapshots.c.selection_epoch_id == snapshot.selection_epoch_id,
        ).order_by(instrument_selection_snapshots.c.feature_cutoff_at_ms.desc()).limit(1))).mappings().one_or_none()
        if prior_row is None:
            if snapshot.predecessor_snapshot_id is not None:
                raise SelectionJobConflict("Selection predecessor does not exist")
        else:
            prior = await self.get_generic_snapshot(prior_row["selection_snapshot_id"])
            if (prior.selection_snapshot_id != snapshot.predecessor_snapshot_id
                or prior.member_set_digest != snapshot.predecessor_member_digest
                or prior.feature_cutoff_at_ms >= snapshot.feature_cutoff_at_ms
                or prior.committed_at_ms > snapshot.committed_at_ms):
                raise SelectionJobConflict("Selection predecessor changed or epoch/time differs")
        previous = set() if prior_row is None else set(prior.selected_members)
        for member in snapshot.members:
            expected_retained = member.qualified and member.stable_rank <= spec.retain_rank and member.exchange_instrument_id in previous
            if member.retained != expected_retained:
                raise SelectionJobConflict("Selection retention differs from previous Desired Snapshot")
        await self._connection.execute(sa.insert(instrument_selection_snapshots).values(
            selection_snapshot_id=snapshot.selection_snapshot_id, selection_spec_id=spec.selection_spec_id,
            strategy_group_id=spec.strategy_group_id, strategy_version_id=spec.strategy_version_id,
            selection_family="generic_dynamic_v1", selection_epoch_id=snapshot.selection_epoch_id,
            period_anchor_ms=snapshot.feature_cutoff_at_ms, decision_at_ms=decision_at_ms,
            feature_cutoff_at_ms=snapshot.feature_cutoff_at_ms, eligibility_not_before_ms=snapshot.effective_from_ms,
            expires_at_ms=snapshot.expires_at_ms, candidate_count=24, ready_count=snapshot.ready_count,
            selected_count=len(snapshot.selected_members), source_observed_at_ms=source_observed_at_ms,
            source_semantic_digest=snapshot.source_semantic_digest, selection_semantic_digest=snapshot.semantic_digest,
            created_at_ms=snapshot.committed_at_ms, predecessor_snapshot_id=snapshot.predecessor_snapshot_id,
            predecessor_member_digest=snapshot.predecessor_member_digest,
        ))
        await self._connection.execute(sa.insert(instrument_selection_member_decisions), [{
            "selection_snapshot_id": snapshot.selection_snapshot_id,
            "member_decision_id": "selection-member:" + canonical_digest({"snapshot": snapshot.selection_snapshot_id, "member": member.exchange_instrument_id})[7:],
            "selection_spec_id": spec.selection_spec_id, "period_anchor_ms": snapshot.feature_cutoff_at_ms,
            "feature_cutoff_at_ms": snapshot.feature_cutoff_at_ms,
            "input_window_start_ms": snapshot.feature_cutoff_at_ms - spec.window_bars * 3600000,
            "input_window_end_ms": snapshot.feature_cutoff_at_ms,
            "exchange_instrument_id": member.exchange_instrument_id, "input_window_digest": member.input_window_digest,
            "selection_family": "generic_dynamic_v1", "source_status": "READY",
            "feature_value": member.feature_value, "retained": member.retained,
            "selection_ready": member.qualified, "primary_reason": member.qualification_reason, "secondary_reasons": [],
            "qualification_fact": member.qualification.model_dump(mode="json"),
            "qualification_semantic_digest": member.qualification_semantic_digest,
            "stable_rank": member.stable_rank, "member_state": "SELECTED" if member.selected else "NOT_SELECTED" if member.qualified else "INELIGIBLE",
            "selected": member.selected, "member_semantic_digest": member.semantic_digest,
        } for member in snapshot.members])

    async def get_generic_spec(self, selection_spec_id: str) -> GenericSelectionSpecV1:
        row = (await self._connection.execute(sa.select(instrument_selection_specs, generic_dynamic_selection_specs_v1)
            .join(generic_dynamic_selection_specs_v1, generic_dynamic_selection_specs_v1.c.selection_spec_id == instrument_selection_specs.c.selection_spec_id)
            .where(instrument_selection_specs.c.selection_spec_id == selection_spec_id,
                   instrument_selection_specs.c.status == "active", instrument_selection_specs.c.selection_kind == "generic_dynamic_v1"))).mappings().one_or_none()
        if row is None:
            raise LookupError("Generic Selection Spec is not installed")
        events = (await self._connection.execute(sa.select(instrument_selection_spec_events).where(
            instrument_selection_spec_events.c.selection_spec_id == selection_spec_id))).mappings().all()
        if len(events) != 1:
            raise ValueError("Generic Selection Spec requires exact bound Event")
        members = tuple((await self._connection.execute(sa.select(instrument_selection_spec_members.c.exchange_instrument_id)
            .where(instrument_selection_spec_members.c.selection_spec_id == selection_spec_id)
            .order_by(instrument_selection_spec_members.c.exchange_instrument_id))).scalars())
        spec = GenericSelectionSpecV1.model_validate({
            "selection_spec_id":selection_spec_id,"strategy_group_id":row["strategy_group_id"],
            "strategy_version_id":row["strategy_version_id"],"event_spec_id":events[0]["event_spec_id"],
            "position_side":events[0]["position_side"],"candidate_ids":members,
            **{column.name:row[column.name] for column in generic_dynamic_selection_specs_v1.c if column.name != "selection_spec_id"},
        })
        if spec.algorithm_semantic_digest != row["algorithm_semantic_digest"]:
            raise ValueError("Generic Selection Spec semantic identity differs")
        return spec

    async def get_selection_product_profiles(self, selection_spec_id: str) -> tuple[InstrumentProductProfile, ...]:
        rows = (await self._connection.execute(sa.select(instrument_product_profiles).join(
            instrument_selection_spec_members, instrument_selection_spec_members.c.exchange_instrument_id == instrument_product_profiles.c.exchange_instrument_id,
        ).where(instrument_selection_spec_members.c.selection_spec_id == selection_spec_id)
            .order_by(instrument_product_profiles.c.exchange_instrument_id).limit(24))).mappings().all()
        profiles = tuple(InstrumentProductProfile.model_validate({key: row[key] for key in InstrumentProductProfile.model_fields}) for row in rows)
        if any(profile.semantic_digest != row["semantic_digest"] for profile, row in zip(profiles, rows, strict=True)):
            raise ValueError("Selection Product profile semantic digest differs")
        return profiles

    async def get_comparison_universe_binding(self, event_spec_id: str, *, for_update: bool = False) -> ComparisonUniverseBinding | None:
        statement = sa.select(comparison_binding_current, comparison_universe_definitions.c.member_set_digest,
            comparison_universe_definitions.c.member_count).join(comparison_universe_definitions,
                comparison_universe_definitions.c.comparison_universe_id==comparison_binding_current.c.comparison_universe_id
            ).where(comparison_binding_current.c.event_spec_id==event_spec_id)
        if for_update:
            statement = statement.with_for_update(of=comparison_binding_current)
        row = (await self._connection.execute(statement)).mappings().one_or_none()
        if row is None:
            return None
        members = tuple((await self._connection.execute(sa.select(comparison_universe_members.c.exchange_instrument_id).where(
            comparison_universe_members.c.comparison_universe_id==row["comparison_universe_id"],
        ).order_by(comparison_universe_members.c.exchange_instrument_id).limit(25))).scalars())
        if len(members)!=row["member_count"]:
            raise SelectionJobConflict("comparison definition cardinality differs")
        binding = ComparisonUniverseBinding(event_spec_id=event_spec_id,comparison_universe_id=row["comparison_universe_id"],
            member_set_digest=row["member_set_digest"],exchange_instrument_ids=members,
            comparison_transition_revision=row["comparison_transition_revision"],source_static_universe_version_id=row["source_static_universe_version_id"])
        if binding.source_static_universe_version_id is not None:
            original_members = tuple((await self._connection.execute(sa.select(strategy_universe_members.c.exchange_instrument_id).where(
                strategy_universe_members.c.universe_version_id==binding.source_static_universe_version_id,
            ).order_by(strategy_universe_members.c.exchange_instrument_id).limit(11))).scalars())
            if original_members!=members:
                raise SelectionJobConflict("Static comparison differs from its source Universe")
        return binding

    async def install_generic_spec(self, spec: GenericSelectionSpecV1, *, installed_at_ms: int,
                                   certification: SpecNumericInstallationEvidence) -> None:
        """Release-owned installation; never exposed as a runtime Owner mutation."""
        if installed_at_ms <= 0:
            raise ValueError("invalid Spec installation time")
        certification.require_spec(spec)
        existing = await self._connection.scalar(sa.select(instrument_selection_specs.c.selection_spec_id).where(
            instrument_selection_specs.c.selection_spec_id == spec.selection_spec_id))
        if existing is not None:
            if await self.get_generic_spec(spec.selection_spec_id) != spec:
                raise ValueError("installed Generic Spec differs")
            return
        for member in spec.candidate_ids:
            symbol = member.split(":")[1]
            await self._connection.execute(pg_insert(instruments).values(
                exchange_instrument_id=member,venue_id="binance-usdm",asset_class="crypto",
                venue_symbol=symbol,contract_kind="perpetual",status="pending_certification"
            ).on_conflict_do_nothing())
            profile = InstrumentProductProfile(exchange_instrument_id=member,product_family="crypto_perpetual",
                asset_class="crypto",contract_type="PERPETUAL",underlying_type="CRYPTO",
                entry_session_policy="continuous",status="candidate")
            await self._connection.execute(pg_insert(instrument_product_profiles).values(
                **profile.model_dump(mode="python"),semantic_digest=profile.semantic_digest,updated_at_ms=installed_at_ms
            ).on_conflict_do_nothing())
            identity = (await self._connection.execute(sa.select(instruments).where(instruments.c.exchange_instrument_id==member))).mappings().one()
            if (identity["venue_id"],identity["asset_class"],identity["venue_symbol"],identity["contract_kind"]) != ("binance-usdm","crypto",symbol,"perpetual"):
                raise ValueError("Candidate Instrument identity conflict")
        await self._connection.execute(sa.insert(instrument_selection_specs).values(
            selection_spec_id=spec.selection_spec_id,strategy_group_id=spec.strategy_group_id,
            strategy_version_id=spec.strategy_version_id,selection_version=1,selection_kind="generic_dynamic_v1",
            algorithm_semantic_digest=spec.algorithm_semantic_digest,status="active",installed_at_ms=installed_at_ms))
        payload = spec.model_dump(mode="python")
        await self._connection.execute(sa.insert(generic_dynamic_selection_specs_v1).values(
            **{column.name:payload[column.name] for column in generic_dynamic_selection_specs_v1.c}))
        await self._connection.execute(sa.insert(instrument_selection_spec_events).values(
            selection_spec_id=spec.selection_spec_id,event_spec_id=spec.event_spec_id,position_side=spec.position_side))
        await self._connection.execute(sa.insert(instrument_selection_spec_members), [
            {"selection_spec_id":spec.selection_spec_id,"exchange_instrument_id":member} for member in spec.candidate_ids])
        if spec.strategy_group_id in {"MPG-001","MI-001"}:
            digest = canonical_digest({"exchange_instrument_ids":spec.candidate_ids})
            comparison_id = "comparison:"+digest[7:]
            await self._connection.execute(pg_insert(comparison_universe_definitions).values(
                comparison_universe_id=comparison_id,member_set_digest=digest,member_count=24).on_conflict_do_nothing())
            await self._connection.execute(pg_insert(comparison_universe_members).values([
                {"comparison_universe_id":comparison_id,"exchange_instrument_id":member} for member in spec.candidate_ids
            ]).on_conflict_do_nothing())
        await self._connection.execute(sa.insert(strategy_selection_control_current).values(
            strategy_group_id=spec.strategy_group_id,selection_spec_id=spec.selection_spec_id,
            selection_mode="static_baseline",pending_selection_mode=None,pending_effective_period_anchor_ms=None,
            pending_authorization_id=None,control_version=1,rollback_baseline_id=None,updated_at_ms=installed_at_ms))

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
        result = await self._claim_selection_job_row(
            selection_spec_id=spec.selection_spec_id, period_anchor_ms=period.session_start_ms,
            scheduled_at_ms=period.decision_boundary_ms, feature_cutoff_at_ms=period.feature_cutoff_at_ms,
            worker_id=worker_id, now_ms=now_ms, lease_duration_ms=lease_duration_ms,
        )
        if isinstance(result, GenericSelectionJobClaim):
            raise SelectionJobConflict("SOR cannot consume a Generic claim")
        return await self._get_snapshot(result) if isinstance(result, str) else result

    @staticmethod
    def _generic_control_allows(control: SelectionControl | None, spec_id: str, epoch: str, cutoff: int) -> bool:
        if control is None or control.selection_spec_id != spec_id or control.selection_epoch_id != epoch:
            return False
        return control.permits_dynamic_period(cutoff)

    async def claim_generic_selection_job(
        self, *, selection_spec_id: str, selection_epoch_id: str, feature_cutoff_at_ms: int,
        worker_id: str, now_ms: int, lease_duration_ms: int,
    ) -> GenericSelectionJobClaim | SelectionJobFailure | GenericSelectionSnapshotV1 | None:
        spec = await self.get_generic_spec(selection_spec_id)
        period = build_generic_selection_period(feature_cutoff_at_ms=feature_cutoff_at_ms, cadence_hours=spec.cadence_hours)
        control = await self.get_selection_control(spec.strategy_group_id, for_update=True)
        if not self._generic_control_allows(control, selection_spec_id, selection_epoch_id, feature_cutoff_at_ms):
            return None
        assert control is not None
        if now_ms < feature_cutoff_at_ms or lease_duration_ms <= 0:
            raise ValueError("Generic Selection Job claim timing or lease is invalid")
        prior_epoch_job_id = await self._connection.scalar(
            sa.select(instrument_selection_jobs_current.c.selection_job_id)
            .where(
                instrument_selection_jobs_current.c.selection_spec_id == selection_spec_id,
                instrument_selection_jobs_current.c.selection_epoch_id != selection_epoch_id,
                instrument_selection_jobs_current.c.selection_epoch_id != "sor-v0",
                instrument_selection_jobs_current.c.state.in_(("DUE", "CLAIMED")),
            )
            .order_by(instrument_selection_jobs_current.c.updated_at_ms.desc())
            .limit(1)
            .with_for_update()
        )
        if prior_epoch_job_id is not None:
            await self._connection.execute(
                sa.update(instrument_selection_jobs_current)
                .where(instrument_selection_jobs_current.c.selection_job_id == prior_epoch_job_id)
                .values(
                    state="SUPERSEDED",
                    first_blocker="SUPERSEDED_BY_SELECTION_EPOCH",
                    next_retry_at_ms=None,
                    lease_owner=None,
                    lease_expires_at_ms=None,
                    projection_version=instrument_selection_jobs_current.c.projection_version + 1,
                    updated_at_ms=now_ms,
                )
            )
        older_job_id = await self._connection.scalar(
            sa.select(instrument_selection_jobs_current.c.selection_job_id)
            .where(
                instrument_selection_jobs_current.c.selection_spec_id == selection_spec_id,
                instrument_selection_jobs_current.c.selection_epoch_id == selection_epoch_id,
                instrument_selection_jobs_current.c.period_anchor_ms < feature_cutoff_at_ms,
                instrument_selection_jobs_current.c.state.in_(("DUE", "CLAIMED")),
            )
            .order_by(instrument_selection_jobs_current.c.period_anchor_ms.desc())
            .limit(1)
            .with_for_update()
        )
        if older_job_id is not None:
            await self._connection.execute(
                sa.update(instrument_selection_jobs_current)
                .where(instrument_selection_jobs_current.c.selection_job_id == older_job_id)
                .values(
                    state="SUPERSEDED",
                    first_blocker="SUPERSEDED_BY_NEWER_DUE_PERIOD",
                    next_retry_at_ms=None,
                    lease_owner=None,
                    lease_expires_at_ms=None,
                    projection_version=instrument_selection_jobs_current.c.projection_version + 1,
                    updated_at_ms=now_ms,
                )
            )
        newer_job_exists = await self._connection.scalar(
            sa.select(instrument_selection_jobs_current.c.selection_job_id)
            .where(
                instrument_selection_jobs_current.c.selection_spec_id == selection_spec_id,
                instrument_selection_jobs_current.c.selection_epoch_id == selection_epoch_id,
                instrument_selection_jobs_current.c.period_anchor_ms > feature_cutoff_at_ms,
            )
            .order_by(instrument_selection_jobs_current.c.period_anchor_ms)
            .limit(1)
        )
        if newer_job_exists is not None:
            await self._connection.execute(
                pg_insert(instrument_selection_jobs_current)
                .values(
                    selection_job_id=selection_job_identity(selection_spec_id, feature_cutoff_at_ms, selection_epoch_id),
                    selection_spec_id=selection_spec_id,
                    selection_epoch_id=selection_epoch_id,
                    selection_control_version=control.control_version,
                    period_anchor_ms=feature_cutoff_at_ms,
                    scheduled_at_ms=feature_cutoff_at_ms,
                    feature_cutoff_at_ms=feature_cutoff_at_ms,
                    state="SUPERSEDED",
                    selection_snapshot_id=None,
                    first_blocker="SUPERSEDED_BY_NEWER_DUE_PERIOD",
                    attempt_count=0,
                    next_retry_at_ms=None,
                    lease_owner=None,
                    lease_expires_at_ms=None,
                    projection_version=1,
                    updated_at_ms=now_ms,
                )
                .on_conflict_do_nothing(index_elements=[
                    instrument_selection_jobs_current.c.selection_spec_id,
                    instrument_selection_jobs_current.c.selection_epoch_id,
                    instrument_selection_jobs_current.c.period_anchor_ms,
                ])
            )
            await self._connection.execute(
                sa.update(instrument_selection_jobs_current)
                .where(
                    instrument_selection_jobs_current.c.selection_spec_id == selection_spec_id,
                    instrument_selection_jobs_current.c.selection_epoch_id == selection_epoch_id,
                    instrument_selection_jobs_current.c.period_anchor_ms == feature_cutoff_at_ms,
                    instrument_selection_jobs_current.c.state.in_(("DUE", "CLAIMED")),
                )
                .values(
                    state="SUPERSEDED",
                    first_blocker="SUPERSEDED_BY_NEWER_DUE_PERIOD",
                    next_retry_at_ms=None,
                    lease_owner=None,
                    lease_expires_at_ms=None,
                    projection_version=instrument_selection_jobs_current.c.projection_version + 1,
                    updated_at_ms=now_ms,
                )
            )
            return None
        if now_ms >= period.period_expires_at_ms:
            await self._connection.execute(
                pg_insert(instrument_selection_jobs_current)
                .values(
                    selection_job_id=selection_job_identity(selection_spec_id, feature_cutoff_at_ms, selection_epoch_id),
                    selection_spec_id=selection_spec_id,
                    selection_epoch_id=selection_epoch_id,
                    selection_control_version=control.control_version,
                    predecessor_snapshot_id=None,
                    predecessor_member_digest=None,
                    period_anchor_ms=feature_cutoff_at_ms,
                    scheduled_at_ms=feature_cutoff_at_ms,
                    feature_cutoff_at_ms=feature_cutoff_at_ms,
                    state="EXPIRED",
                    selection_snapshot_id=None,
                    first_blocker="SELECTION_PERIOD_EXPIRED",
                    attempt_count=0,
                    next_retry_at_ms=None,
                    lease_owner=None,
                    lease_expires_at_ms=None,
                    projection_version=1,
                    updated_at_ms=now_ms,
                )
                .on_conflict_do_nothing(index_elements=[
                    instrument_selection_jobs_current.c.selection_spec_id,
                    instrument_selection_jobs_current.c.selection_epoch_id,
                    instrument_selection_jobs_current.c.period_anchor_ms,
                ])
            )
            await self._connection.execute(
                sa.update(instrument_selection_jobs_current)
                .where(
                    instrument_selection_jobs_current.c.selection_spec_id == selection_spec_id,
                    instrument_selection_jobs_current.c.selection_epoch_id == selection_epoch_id,
                    instrument_selection_jobs_current.c.period_anchor_ms == feature_cutoff_at_ms,
                    instrument_selection_jobs_current.c.state.in_(
                        ("DUE", "CLAIMED", "SOURCE_FAILED", "COMPUTE_FAILED")
                    ),
                )
                .values(
                    state="EXPIRED",
                    selection_snapshot_id=None,
                    first_blocker="SELECTION_PERIOD_EXPIRED",
                    next_retry_at_ms=None,
                    lease_owner=None,
                    lease_expires_at_ms=None,
                    projection_version=instrument_selection_jobs_current.c.projection_version + 1,
                    updated_at_ms=now_ms,
                )
            )
            return None
        existing_state = await self._connection.scalar(
            sa.select(instrument_selection_jobs_current.c.state)
            .where(
                instrument_selection_jobs_current.c.selection_spec_id == selection_spec_id,
                instrument_selection_jobs_current.c.selection_epoch_id == selection_epoch_id,
                instrument_selection_jobs_current.c.period_anchor_ms == feature_cutoff_at_ms,
            )
            .limit(1)
        )
        if existing_state in {"EXPIRED", "SUPERSEDED"}:
            return None
        previous_id = await self._connection.scalar(sa.select(instrument_selection_snapshots.c.selection_snapshot_id).where(
            instrument_selection_snapshots.c.selection_spec_id == selection_spec_id,
            instrument_selection_snapshots.c.selection_epoch_id == selection_epoch_id,
            instrument_selection_snapshots.c.feature_cutoff_at_ms < feature_cutoff_at_ms,
        ).order_by(instrument_selection_snapshots.c.feature_cutoff_at_ms.desc()).limit(1))
        previous = None if previous_id is None else await self.get_generic_snapshot(previous_id)
        result = await self._claim_selection_job_row(
            selection_spec_id=selection_spec_id, period_anchor_ms=feature_cutoff_at_ms,
            scheduled_at_ms=feature_cutoff_at_ms, feature_cutoff_at_ms=feature_cutoff_at_ms,
            worker_id=worker_id, now_ms=now_ms, lease_duration_ms=lease_duration_ms,
            selection_epoch_id=selection_epoch_id, selection_control_version=control.control_version,
            predecessor_snapshot_id=None if previous is None else previous.selection_snapshot_id,
            predecessor_member_digest=None if previous is None else previous.member_set_digest,
        )
        if isinstance(result, SelectionJobClaim):
            raise SelectionJobConflict("Generic Selection cannot consume a SOR claim")
        return await self.get_generic_snapshot(result) if isinstance(result, str) else result

    async def complete_generic_selection_snapshot(
        self, *, claim: GenericSelectionJobClaim, snapshot: GenericSelectionSnapshotV1,
        source_observed_at_ms: int, completed_at_ms: int,
    ) -> None:
        claim = GenericSelectionJobClaim.model_validate(claim.model_dump(mode="python"))
        snapshot = GenericSelectionSnapshotV1.model_validate(snapshot.model_dump(mode="python"))
        spec = await self.get_generic_spec(claim.selection_spec_id)
        control = await self.get_selection_control(spec.strategy_group_id, for_update=True)
        if (not self._generic_control_allows(control, claim.selection_spec_id, job_selection_epoch(claim), job_period_anchor(claim))
            or control is None or control.control_version != claim.selection_control_version):
            raise SelectionJobConflict("Selection control or epoch changed during source read")
        if (snapshot.selection_spec_id != claim.selection_spec_id or snapshot.selection_epoch_id != job_selection_epoch(claim)
            or snapshot.feature_cutoff_at_ms != job_period_anchor(claim) or snapshot.committed_at_ms != completed_at_ms
            or snapshot.predecessor_snapshot_id != claim.predecessor_snapshot_id
            or snapshot.predecessor_member_digest != claim.predecessor_member_digest
            or source_observed_at_ms < claim.started_at_ms or completed_at_ms >= snapshot.expires_at_ms):
            raise SelectionJobConflict("Generic Snapshot differs from claimed epoch/period/predecessor/time")
        row = await self._locked_job(claim)
        if row["state"] == "SNAPSHOT_READY":
            newer_ready = await self.get_generic_snapshot(row["selection_snapshot_id"])
            if newer_ready == snapshot:
                return
            raise SelectionJobConflict("Generic Snapshot digest conflicts")
        newer_job_exists = await self._connection.scalar(
            sa.select(instrument_selection_jobs_current.c.selection_job_id)
            .where(
                instrument_selection_jobs_current.c.selection_spec_id == claim.selection_spec_id,
                instrument_selection_jobs_current.c.selection_epoch_id == claim.selection_epoch_id,
                instrument_selection_jobs_current.c.period_anchor_ms > claim.period_anchor_ms,
            )
            .order_by(instrument_selection_jobs_current.c.period_anchor_ms)
            .limit(1)
        )
        if newer_job_exists is not None:
            raise SelectionJobConflict("newer Generic Selection Job supersedes claimed period")
        self._require_live_claim(row, claim, completed_at_ms=completed_at_ms)
        await self.save_generic_snapshot(snapshot, decision_at_ms=job_period_anchor(claim), source_observed_at_ms=source_observed_at_ms)
        await self._append_attempt(claim=claim, outcome=SelectionAttemptOutcome.SNAPSHOT_READY, reason_code=None,
            source_member_count=24, source_digest=snapshot.source_semantic_digest, completed_at_ms=completed_at_ms)
        await self._mark_snapshot_ready(claim, snapshot.selection_snapshot_id, completed_at_ms)

    async def _claim_selection_job_row(
        self, *, selection_spec_id: str, period_anchor_ms: int, scheduled_at_ms: int,
        feature_cutoff_at_ms: int, worker_id: str, now_ms: int, lease_duration_ms: int,
        selection_epoch_id: str = "sor-v0", selection_control_version: int | None = None,
        predecessor_snapshot_id: str | None = None, predecessor_member_digest: str | None = None,
    ) -> SelectionJobLease | SelectionJobFailure | str:
        if now_ms < feature_cutoff_at_ms:
            raise ValueError("Selection Job cannot be claimed before feature cutoff")
        if lease_duration_ms <= 0:
            raise ValueError("Selection Job lease duration must be positive")
        job_id = selection_job_identity(selection_spec_id, period_anchor_ms, selection_epoch_id)
        await self._connection.execute(
            pg_insert(instrument_selection_jobs_current)
            .values(
                selection_job_id=job_id,
                selection_spec_id=selection_spec_id,
                period_anchor_ms=period_anchor_ms,
                scheduled_at_ms=scheduled_at_ms,
                feature_cutoff_at_ms=feature_cutoff_at_ms,
                selection_epoch_id=selection_epoch_id,
                selection_control_version=selection_control_version,
                predecessor_snapshot_id=predecessor_snapshot_id,
                predecessor_member_digest=predecessor_member_digest,
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
                    instrument_selection_jobs_current.c.selection_epoch_id,
                    instrument_selection_jobs_current.c.period_anchor_ms,
                ]
            )
        )
        row = (
            await self._connection.execute(
                sa.select(instrument_selection_jobs_current)
                .where(
                    instrument_selection_jobs_current.c.selection_spec_id
                    == selection_spec_id,
                    instrument_selection_jobs_current.c.selection_epoch_id == selection_epoch_id,
                    instrument_selection_jobs_current.c.period_anchor_ms
                    == period_anchor_ms,
                )
                .with_for_update()
            )
        ).mappings().one()
        state = str(row["state"])
        if state == "SNAPSHOT_READY":
            snapshot_id = row["selection_snapshot_id"]
            if snapshot_id is None:
                raise SelectionJobConflict("ready Selection Job has no Snapshot")
            return str(snapshot_id)
        if state in {"EXPIRED", "SUPERSEDED"}:
            raise SelectionJobConflict("terminal Generic Selection Job cannot be reclaimed")
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
            if selection_epoch_id != "sor-v0" and state in {"SOURCE_FAILED", "COMPUTE_FAILED"}:
                return SelectionJobFailure(
                    selection_job_id=job_id,
                    outcome="SOURCE_FAILED" if state == "SOURCE_FAILED" else "COMPUTE_FAILED",
                    reason_code=str(row["first_blocker"]),
                )
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
                selection_control_version=selection_control_version,
                predecessor_snapshot_id=predecessor_snapshot_id,
                predecessor_member_digest=predecessor_member_digest,
            )
        )
        if result.rowcount != 1:
            raise SelectionJobConflict("Selection Job projection version changed")
        if selection_epoch_id == "sor-v0":
            return SelectionJobClaim(selection_job_id=job_id, selection_spec_id=selection_spec_id,
                session_start_ms=period_anchor_ms, worker_id=worker_id, attempt_number=attempt_number,
                projection_version=next_version, started_at_ms=now_ms, lease_expires_at_ms=lease_expires)
        if selection_control_version is None:
            raise SelectionJobConflict("Generic claim requires control authority")
        return GenericSelectionJobClaim(
            selection_job_id=job_id,
            selection_spec_id=selection_spec_id,
            period_anchor_ms=period_anchor_ms,
            worker_id=worker_id,
            attempt_number=attempt_number,
            projection_version=next_version,
            started_at_ms=now_ms,
            lease_expires_at_ms=lease_expires,
            selection_epoch_id=selection_epoch_id,
            selection_control_version=selection_control_version,
            predecessor_snapshot_id=predecessor_snapshot_id,
            predecessor_member_digest=predecessor_member_digest,
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
                **snapshot.model_dump(exclude={"session_start_ms"}), period_anchor_ms=snapshot.session_start_ms,
            )
        )
        await self._connection.execute(
            sa.insert(instrument_selection_member_decisions),
            [
                {
                    **decision.model_dump(
                        exclude={"primary_reason", "member_state", "session_start_ms"}
                    ),
                    "period_anchor_ms": decision.session_start_ms,
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
        await self._mark_snapshot_ready(claim, snapshot.selection_snapshot_id, completed_at_ms)

    async def _mark_snapshot_ready(self, claim: SelectionJobLease, selection_snapshot_id: str, completed_at_ms: int) -> None:
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
                selection_snapshot_id=selection_snapshot_id,
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
        claim: SelectionJobLease,
        outcome: SelectionAttemptOutcome,
        reason_code: str,
        source_member_count: int,
        source_digest: str | None,
        completed_at_ms: int,
        next_retry_at_ms: int | None = None,
    ) -> None:
        if outcome is SelectionAttemptOutcome.SNAPSHOT_READY:
            raise ValueError("failure completion requires a failure outcome")
        normalized_reason = reason_code.strip()
        if not normalized_reason:
            raise ValueError("Selection failure requires a reason code")
        if isinstance(claim, GenericSelectionJobClaim):
            spec = await self.get_generic_spec(claim.selection_spec_id)
            control = await self.get_selection_control(spec.strategy_group_id, for_update=True)
            if (
                not self._generic_control_allows(
                    control, claim.selection_spec_id, claim.selection_epoch_id,
                    claim.period_anchor_ms,
                )
                or control is None
                or control.control_version != claim.selection_control_version
            ):
                raise SelectionJobConflict("Generic Selection control or epoch changed before failure completion")
            newer_job_exists = await self._connection.scalar(
                sa.select(instrument_selection_jobs_current.c.selection_job_id)
                .where(
                    instrument_selection_jobs_current.c.selection_spec_id == claim.selection_spec_id,
                    instrument_selection_jobs_current.c.selection_epoch_id == claim.selection_epoch_id,
                    instrument_selection_jobs_current.c.period_anchor_ms > claim.period_anchor_ms,
                )
                .order_by(instrument_selection_jobs_current.c.period_anchor_ms)
                .limit(1)
            )
            if newer_job_exists is not None:
                raise SelectionJobConflict("newer Generic Selection Job supersedes failure attempt")
        row = await self._locked_job(claim)
        self._require_live_claim(row, claim, completed_at_ms=completed_at_ms)
        if isinstance(claim, GenericSelectionJobClaim):
            spec = await self.get_generic_spec(claim.selection_spec_id)
            period = build_generic_selection_period(
                feature_cutoff_at_ms=claim.period_anchor_ms,
                cadence_hours=spec.cadence_hours,
            )
            if completed_at_ms >= period.period_expires_at_ms:
                raise SelectionJobConflict("Generic Selection period expired before failure completion")
            if next_retry_at_ms is not None and (
                outcome is not SelectionAttemptOutcome.SOURCE_FAILED
                or claim.attempt_number >= GENERIC_SOURCE_MAX_ATTEMPTS
                or next_retry_at_ms < completed_at_ms + GENERIC_SOURCE_RETRY_BACKOFF_MS
                or next_retry_at_ms >= period.period_expires_at_ms
            ):
                raise SelectionJobConflict("Generic Selection source retry budget is invalid")
        elif next_retry_at_ms is not None:
            raise SelectionJobConflict("SOR failure cannot use Generic source retry")
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
                next_retry_at_ms=next_retry_at_ms,
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
        period_anchor_ms: int,
        selection_epoch_id: str = "sor-v0",
    ) -> SelectionJobRecord | None:
        row = (
            await self._connection.execute(
                sa.select(instrument_selection_jobs_current)
                .where(
                    instrument_selection_jobs_current.c.selection_spec_id
                    == selection_spec_id,
                    instrument_selection_jobs_current.c.selection_epoch_id == selection_epoch_id,
                    instrument_selection_jobs_current.c.period_anchor_ms
                    == period_anchor_ms,
                )
                .limit(1)
            )
        ).mappings().one_or_none()
        return None if row is None else SelectionJobRecord.model_validate(dict(row))

    async def _locked_job(self, claim: SelectionJobLease) -> RowMapping:
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
        claim: SelectionJobLease,
        *,
        completed_at_ms: int,
    ) -> None:
        if (
            str(row["state"]) != "CLAIMED"
            or str(row["lease_owner"]) != claim.worker_id
            or int(row["projection_version"]) != claim.projection_version
            or int(row["attempt_count"]) != claim.attempt_number
            or row["selection_epoch_id"] != job_selection_epoch(claim)
            or row["selection_control_version"] != (claim.selection_control_version if isinstance(claim, GenericSelectionJobClaim) else None)
            or row["predecessor_snapshot_id"] != (claim.predecessor_snapshot_id if isinstance(claim, GenericSelectionJobClaim) else None)
            or row["predecessor_member_digest"] != (claim.predecessor_member_digest if isinstance(claim, GenericSelectionJobClaim) else None)
        ):
            raise SelectionJobConflict("Selection Job claim identity changed")
        if completed_at_ms < claim.started_at_ms or completed_at_ms > int(row["lease_expires_at_ms"]) or (
            job_selection_epoch(claim) != "sor-v0" and completed_at_ms == int(row["lease_expires_at_ms"])
        ):
            raise SelectionJobConflict("Selection Job lease expired before completion")

    async def _append_attempt(
        self,
        *,
        claim: SelectionJobLease,
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
                    f"{job_period_anchor(claim)}:{claim.attempt_number}"
                ) if job_selection_epoch(claim) == "sor-v0" else (
                    "selection-attempt:" + canonical_digest({"job": claim.selection_job_id, "attempt": claim.attempt_number})[7:]
                ),
                selection_job_id=claim.selection_job_id,
                selection_spec_id=claim.selection_spec_id,
                period_anchor_ms=job_period_anchor(claim),
                selection_epoch_id=job_selection_epoch(claim),
                selection_control_version=claim.selection_control_version if isinstance(claim, GenericSelectionJobClaim) else None,
                predecessor_snapshot_id=claim.predecessor_snapshot_id if isinstance(claim, GenericSelectionJobClaim) else None,
                predecessor_member_digest=claim.predecessor_member_digest if isinstance(claim, GenericSelectionJobClaim) else None,
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
        return SelectionSnapshot.model_validate({key:row["period_anchor_ms" if key == "session_start_ms" else key] for key in SelectionSnapshot.model_fields})

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
                pending_effective_period_anchor_ms=None,
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
                pending_effective_period_anchor_ms=effective_session_start_ms,
                pending_authorization_id=authorization_id,
                control_version=expected_control_version + 1,
                updated_at_ms=updated_at_ms,
            )
            .returning(strategy_selection_control_current)
        )
        row = result.mappings().one_or_none()
        return None if row is None else _selection_control_from_row(row)

    async def stage_pending_generic_selection_mode(
        self,
        *,
        strategy_group_id: str,
        selection_spec_id: str,
        expected_control_version: int,
        selection_epoch_id: str,
        effective_period_anchor_ms: int,
        authorization_id: str,
        rollback_baseline_id: str,
        updated_at_ms: int,
    ) -> SelectionControl | None:
        baseline = await self.get_generic_static_rollback_baseline(rollback_baseline_id)
        if baseline.strategy_group_id != strategy_group_id or baseline.selection_spec_id != selection_spec_id:
            raise SelectionJobConflict("Generic rollback baseline does not match Control")
        result = await self._connection.execute(
            sa.update(strategy_selection_control_current)
            .where(
                strategy_selection_control_current.c.strategy_group_id == strategy_group_id,
                strategy_selection_control_current.c.selection_spec_id == selection_spec_id,
                strategy_selection_control_current.c.control_version == expected_control_version,
                strategy_selection_control_current.c.selection_mode == "static_baseline",
                strategy_selection_control_current.c.pending_selection_mode.is_(None),
                strategy_selection_control_current.c.selection_epoch_id.is_(None),
                sa.or_(
                    strategy_selection_control_current.c.rollback_baseline_id.is_(None),
                    strategy_selection_control_current.c.rollback_baseline_id == rollback_baseline_id,
                ),
            )
            .values(
                pending_selection_mode="dynamic_selection",
                pending_effective_period_anchor_ms=effective_period_anchor_ms,
                pending_authorization_id=authorization_id,
                selection_epoch_id=selection_epoch_id,
                rollback_baseline_id=rollback_baseline_id,
                control_version=expected_control_version + 1,
                updated_at_ms=updated_at_ms,
            )
            .returning(strategy_selection_control_current)
        )
        row = result.mappings().one_or_none()
        return None if row is None else _selection_control_from_row(row)

    async def stage_pending_generic_static_mode(self, *, strategy_group_id: str,
        selection_spec_id: str, selection_epoch_id: str, rollback_baseline_id: str,
        expected_control_version: int, effective_period_anchor_ms: int,
        authorization_id: str, updated_at_ms: int,
        expected_pending_authorization_id: str | None = None,
    ) -> SelectionControl | None:
        previous: GenericStaticMaterializationGeneration | None = None
        vacuum: StrategyEntryVacuum | None = None
        if expected_pending_authorization_id is not None:
            owner = (await self._connection.execute(sa.select(strategy_entry_controls_current).where(
                strategy_entry_controls_current.c.strategy_group_id==strategy_group_id).with_for_update())).mappings().one_or_none()
            control = await self.get_selection_control(strategy_group_id,for_update=True)
            previous = await self.get_generic_static_materialization_generation(
                GenericStaticMaterializationGeneration.id_for_authorization(expected_pending_authorization_id),for_update=True)
            vacuum = await self.get_current_entry_vacuum(strategy_group_id=strategy_group_id,selection_spec_id=selection_spec_id,for_update=True)
            if control is None or owner is None or owner["entry_state"]!="enabled" or previous is None or (
                control.pending_selection_mode is not SelectionMode.STATIC_BASELINE
                or control.pending_authorization_id!=expected_pending_authorization_id
                or previous.lifecycle_state not in {MaterializationGenerationState.FAILED_CLOSED,MaterializationGenerationState.ABANDONED}
                or previous.selection_epoch_id!=selection_epoch_id or previous.rollback_baseline_id!=rollback_baseline_id
                or previous.selection_control_version!=expected_control_version or previous.terminal_at_ms is None
                or updated_at_ms<max(previous.terminal_at_ms,control.updated_at_ms)
                or vacuum is None or vacuum.source_generation_id!=previous.materialization_generation_id
                or vacuum.state not in {StrategyEntryVacuumState.RECONFIGURING,StrategyEntryVacuumState.OWNER_PAUSED}
                or vacuum.drained_at_ms is None or vacuum.resolved_at_ms is not None):
                raise SelectionJobConflict("Static reauthorization requires exact terminal fenced intent")
            if await self._connection.scalar(sa.select(sa.exists().where(
                strategy_universe_versions.c.materialization_generation_id==previous.materialization_generation_id,
                strategy_universe_versions.c.lifecycle_state!="abandoned"))):
                raise SelectionJobConflict("Static reauthorization requires abandoned targets")
            prior = previous.previous_events[0]
            active = (await self._connection.execute(sa.select(strategy_universe_current).where(
                strategy_universe_current.c.event_spec_id==prior.event_spec_id).with_for_update())).mappings().one_or_none()
            if active is None or active["lifecycle_state"]!="active" or active["universe_version_id"]!=prior.universe_version_id:
                raise SelectionJobConflict("Static reauthorization previous Universe changed")
            if prior.comparison_universe_id is not None:
                comparison = await self.get_comparison_universe_binding(prior.event_spec_id,for_update=True)
                if comparison is None or (comparison.comparison_universe_id,comparison.comparison_transition_revision)!=(
                    prior.comparison_universe_id,prior.comparison_transition_revision):
                    raise SelectionJobConflict("Static reauthorization previous comparison changed")
            authorization = (await self._connection.execute(sa.select(owner_authorizations).where(
                owner_authorizations.c.authorization_id==authorization_id))).mappings().one_or_none()
            spec = await self.get_generic_spec(selection_spec_id)
            cadence = spec.cadence_hours*3_600_000
            expected_scope = {"strategy_group_id":strategy_group_id,"selection_spec_id":selection_spec_id,
                "target_selection_mode":"static_baseline","rollback_baseline_id":rollback_baseline_id,
                "selection_epoch_id":selection_epoch_id,"effective_period_anchor_ms":effective_period_anchor_ms}
            if authorization_id==expected_pending_authorization_id or authorization is None or (
                authorization["purpose"]!="selection_mode_change" or authorization["authentication_strength"]!="totp_step_up"
                or authorization["authorized_at_ms"]!=updated_at_ms or authorization["target_scope"]!=expected_scope
                or effective_period_anchor_ms!=(updated_at_ms//cadence+1)*cadence):
                raise SelectionJobConflict("Static reauthorization requires new exact Owner proof")
        pending_predicate = (sa.and_(strategy_selection_control_current.c.pending_selection_mode=="static_baseline",
            strategy_selection_control_current.c.pending_authorization_id==expected_pending_authorization_id)
            if expected_pending_authorization_id is not None else strategy_selection_control_current.c.pending_selection_mode.is_(None))
        result = await self._connection.execute(sa.update(strategy_selection_control_current).where(
            strategy_selection_control_current.c.strategy_group_id==strategy_group_id,
            strategy_selection_control_current.c.selection_spec_id==selection_spec_id,
            strategy_selection_control_current.c.selection_epoch_id==selection_epoch_id,
            strategy_selection_control_current.c.rollback_baseline_id==rollback_baseline_id,
            strategy_selection_control_current.c.control_version==expected_control_version,
            strategy_selection_control_current.c.selection_mode=="dynamic_selection",
            pending_predicate,
        ).values(pending_selection_mode="static_baseline",pending_effective_period_anchor_ms=effective_period_anchor_ms,
            pending_authorization_id=authorization_id,updated_at_ms=updated_at_ms).returning(strategy_selection_control_current))
        row = result.mappings().one_or_none()
        if row is not None and expected_pending_authorization_id is not None:
            if previous is None or vacuum is None:
                raise SelectionJobConflict("Static reauthorization source disappeared")
            sequence = int(await self._connection.scalar(sa.select(sa.func.max(strategy_universe_materialization_events.c.event_sequence)).where(
                strategy_universe_materialization_events.c.materialization_generation_id==previous.materialization_generation_id)) or 0)+1
            await self._connection.execute(sa.insert(strategy_universe_materialization_events).values(
                materialization_event_id=f"materialization-event:{previous.materialization_generation_id}:{sequence}",
                materialization_generation_id=previous.materialization_generation_id,event_sequence=sequence,
                event_type="OWNER_REAUTHORIZED",payload={"authorization_id":authorization_id,
                    "effective_period_anchor_ms":effective_period_anchor_ms,"entry_vacuum_id":vacuum.entry_vacuum_id},
                occurred_at_ms=updated_at_ms))
        return None if row is None else _selection_control_from_row(row)

    async def _read_static_baseline_universe(
        self, universe_version_id: str, *, require_active: bool = False,
    ) -> StrategyUniverseVersion:
        row = (await self._connection.execute(sa.select(strategy_universe_versions).where(
            strategy_universe_versions.c.universe_version_id == universe_version_id,
        ))).mappings().one_or_none()
        if row is None or row["materialization_generation_id"] is not None:
            raise SelectionJobConflict("Static rollback source Universe missing or Dynamic")
        if require_active and row["lifecycle_state"] != "active":
            raise SelectionJobConflict("Static rollback source Universe is not Active")
        members = tuple((await self._connection.execute(sa.select(
            strategy_universe_members.c.exchange_instrument_id,
        ).where(strategy_universe_members.c.universe_version_id == universe_version_id)
            .order_by(strategy_universe_members.c.exchange_instrument_id).limit(11))).scalars())
        if not 1 <= len(members) <= 10:
            raise SelectionJobConflict("Static rollback source membership is not bounded")
        return StrategyUniverseVersion(
            universe_version_id=universe_version_id,strategy_group_id=row["strategy_group_id"],
            event_spec_id=row["event_spec_id"],universe_version=row["universe_version"],
            exchange_instrument_ids=members,semantic_digest=row["semantic_digest"],
            installed_at_ms=row["installed_at_ms"],
        )

    async def get_generic_static_rollback_baseline(
        self, rollback_baseline_id: str,
    ) -> GenericStaticRollbackBaseline:
        parent = (await self._connection.execute(sa.select(strategy_selection_rollback_baselines).where(
            strategy_selection_rollback_baselines.c.rollback_baseline_id == rollback_baseline_id,
        ))).mappings().one_or_none()
        if parent is None:
            raise SelectionJobConflict("Generic rollback baseline missing")
        spec_rows = (await self._connection.execute(sa.select(instrument_selection_specs).where(
            instrument_selection_specs.c.strategy_group_id == parent["strategy_group_id"],
            instrument_selection_specs.c.strategy_version_id == parent["strategy_version_id"],
            instrument_selection_specs.c.selection_kind == "generic_dynamic_v1",
        ).limit(2))).mappings().all()
        if len(spec_rows) != 1:
            raise SelectionJobConflict("Generic rollback baseline installed Spec differs")
        spec = await self.get_generic_spec(spec_rows[0]["selection_spec_id"])
        events = (await self._connection.execute(sa.select(selection_rollback_baseline_events).where(
            selection_rollback_baseline_events.c.rollback_baseline_id == rollback_baseline_id,
        ).limit(2))).mappings().all()
        if len(events) != 1:
            raise SelectionJobConflict("Generic rollback baseline requires exact Event set")
        event = events[0]
        universe = await self._read_static_baseline_universe(event["universe_version_id"])
        if universe.strategy_group_id != spec.strategy_group_id or universe.event_spec_id != spec.event_spec_id:
            raise SelectionJobConflict("Generic rollback baseline Universe identity differs")
        comparison_id = event["comparison_universe_id"]
        if comparison_id is not None:
            definition = (await self._connection.execute(sa.select(comparison_universe_definitions).where(
                comparison_universe_definitions.c.comparison_universe_id == comparison_id,
            ))).mappings().one_or_none()
            members = tuple((await self._connection.execute(sa.select(comparison_universe_members.c.exchange_instrument_id).where(
                comparison_universe_members.c.comparison_universe_id == comparison_id,
            ).order_by(comparison_universe_members.c.exchange_instrument_id).limit(11))).scalars())
            digest = canonical_digest({"exchange_instrument_ids":members})
            if definition is None or members != universe.exchange_instrument_ids or (
                definition["member_count"] != len(members) or definition["member_set_digest"] != digest
                or comparison_id != "comparison:"+digest[7:]
            ):
                raise SelectionJobConflict("Generic rollback comparison source differs")
        baseline = GenericStaticRollbackBaseline.build(
            strategy_group_id=spec.strategy_group_id,
            source_event=GenericStaticRollbackEvent(
                event_spec_id=event["event_spec_id"],position_side=event["position_side"],
                universe_version_id=universe.universe_version_id,
                universe_semantic_digest=universe.semantic_digest,
                member_set_digest=selected_member_set_digest(universe.exchange_instrument_ids),
                comparison_universe_id=comparison_id,
            ),captured_at_ms=parent["captured_at_ms"],
        )
        if baseline.rollback_baseline_id != rollback_baseline_id or baseline.semantic_digest != parent["semantic_digest"]:
            raise SelectionJobConflict("Generic rollback baseline semantic identity differs")
        return baseline

    async def capture_generic_static_rollback_baseline(
        self, *, selection_spec_id: str, captured_at_ms: int,
    ) -> GenericStaticRollbackBaseline:
        spec = await self.get_generic_spec(selection_spec_id)
        installed_at = await self._connection.scalar(sa.select(instrument_selection_specs.c.installed_at_ms).where(
            instrument_selection_specs.c.selection_spec_id == selection_spec_id,
        ))
        if installed_at is None or installed_at > captured_at_ms:
            raise SelectionJobConflict("Generic Static baseline capture predates installed Spec")
        control = await self.get_selection_control(spec.strategy_group_id,for_update=True)
        if control is None or control.selection_mode is not SelectionMode.STATIC_BASELINE:
            raise SelectionJobConflict("Generic baseline capture requires current Static Control")
        if control.rollback_baseline_id is not None:
            return await self.get_generic_static_rollback_baseline(control.rollback_baseline_id)
        previous = await self._connection.scalar(sa.select(strategy_selection_rollback_baselines.c.rollback_baseline_id).where(
            strategy_selection_rollback_baselines.c.strategy_group_id == spec.strategy_group_id,
            strategy_selection_rollback_baselines.c.strategy_version_id == spec.strategy_version_id,
        ))
        if previous is not None:
            raise SelectionJobConflict("Generic Static baseline Control linkage is missing")
        current = (await self._connection.execute(sa.select(strategy_universe_current).where(
            strategy_universe_current.c.event_spec_id == spec.event_spec_id,
        ).with_for_update(of=strategy_universe_current))).mappings().one_or_none()
        if current is None or current["lifecycle_state"] != "active" or current["activated_at_ms"] > captured_at_ms:
            raise SelectionJobConflict("Generic Static baseline source is missing or not active")
        universe = await self._read_static_baseline_universe(
            current["universe_version_id"],require_active=True,
        )
        if (universe.strategy_group_id != spec.strategy_group_id
            or universe.semantic_digest != current["semantic_digest"]
            or universe.installed_at_ms > captured_at_ms):
            raise SelectionJobConflict("Generic Static source current pointer differs")
        comparison = await self.get_comparison_universe_binding(spec.event_spec_id,for_update=True)
        if spec.strategy_group_id in {"MPG-001","MI-001"} and (
            comparison is None or comparison.source_static_universe_version_id != universe.universe_version_id
            or comparison.exchange_instrument_ids != universe.exchange_instrument_ids
        ):
            raise SelectionJobConflict("Generic Static comparison source is missing or differs")
        if spec.strategy_group_id not in {"MPG-001","MI-001"} and comparison is not None:
            raise SelectionJobConflict("Generic Static non-comparative source carries comparison")
        baseline = GenericStaticRollbackBaseline.build(
            strategy_group_id=spec.strategy_group_id,
            source_event=GenericStaticRollbackEvent(
                event_spec_id=spec.event_spec_id,position_side=spec.position_side,
                universe_version_id=universe.universe_version_id,
                universe_semantic_digest=universe.semantic_digest,
                member_set_digest=selected_member_set_digest(universe.exchange_instrument_ids),
                comparison_universe_id=None if comparison is None else comparison.comparison_universe_id,
            ),captured_at_ms=captured_at_ms,
        )
        await self._connection.execute(sa.insert(strategy_selection_rollback_baselines).values(
            rollback_baseline_id=baseline.rollback_baseline_id,
            strategy_group_id=baseline.strategy_group_id,strategy_version_id=baseline.strategy_version_id,
            semantic_digest=baseline.semantic_digest,captured_at_ms=baseline.captured_at_ms,
        ))
        await self._connection.execute(sa.insert(selection_rollback_baseline_events).values(
            rollback_baseline_id=baseline.rollback_baseline_id,event_spec_id=spec.event_spec_id,
            position_side=spec.position_side,universe_version_id=universe.universe_version_id,
            comparison_universe_id=baseline.source_event.comparison_universe_id,
        ))
        return baseline

    async def recover_expired_dynamic_activation(
        self,
        request: RecoverExpiredDynamicActivationRequest,
    ) -> RecoverExpiredDynamicActivationResult:
        """Atomically clear one exact expired first-activation transition."""

        generation = (
            await self._connection.execute(
                sa.select(*materialization_generation_projection_columns())
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
                    selection_session_authorities.c.period_anchor_ms
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
            or generation["period_anchor_ms"] != request.session_start_ms
            or generation["lifecycle_state"] != "ABANDONED"
            or generation["previous_long_universe_version_id"]
            != request.expected_long_universe_version_id
            or generation["previous_short_universe_version_id"]
            != request.expected_short_universe_version_id
            or vacuum["strategy_group_id"] != request.strategy_group_id
            or vacuum["selection_spec_id"] != request.selection_spec_id
            or vacuum["period_anchor_ms"] != request.session_start_ms
            or vacuum["source_generation_id"]
            != request.materialization_generation_id
            or vacuum["state"] != "OWNER_PAUSED"
            or audit["selection_spec_id"] != request.selection_spec_id
            or audit["period_anchor_ms"] != request.session_start_ms
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
            or selection_control["pending_effective_period_anchor_ms"]
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
                strategy_selection_control_current.c.pending_effective_period_anchor_ms
                == request.session_start_ms,
            )
            .values(
                pending_selection_mode=None,
                pending_effective_period_anchor_ms=None,
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
            instrument_selection_snapshots.c.period_anchor_ms == session_start_ms,
        )
        if for_update:
            statement = statement.with_for_update(of=instrument_selection_snapshots)
        row = (await self._connection.execute(statement)).mappings().one_or_none()
        if row is None:
            return None
        snapshot = SelectionSnapshot.model_validate({key:row["period_anchor_ms" if key == "session_start_ms" else key] for key in SelectionSnapshot.model_fields})
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
        for event_id, side, universe_id in (
            (SOR_LONG_EVENT_SPEC_ID, "long", generation.previous_long_universe_version_id),
            (SOR_SHORT_EVENT_SPEC_ID, "short", generation.previous_short_universe_version_id),
        ):
            members = tuple((await self._connection.execute(sa.select(strategy_universe_members.c.exchange_instrument_id).where(
                strategy_universe_members.c.universe_version_id == universe_id,
            ).order_by(strategy_universe_members.c.exchange_instrument_id))).scalars())
            await self._connection.execute(sa.insert(materialization_generation_event_baselines).values(
                materialization_generation_id=generation.materialization_generation_id, event_spec_id=event_id,
                position_side=side, grant_state="ACTIVE", universe_version_id=universe_id,
                member_set_digest=selected_member_set_digest(members), comparison_universe_id=None,
            ))
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

    async def get_generic_static_materialization_generation(self, materialization_generation_id: str, *,
        for_update: bool = False,
    ) -> GenericStaticMaterializationGeneration | None:
        query = sa.select(strategy_universe_materialization_generations).where(
            strategy_universe_materialization_generations.c.materialization_generation_id==materialization_generation_id)
        if for_update:
            query = query.with_for_update()
        row = (await self._connection.execute(query)).mappings().one_or_none()
        if row is None:
            return None
        if row["selection_mode"]!="static_baseline" or row["selection_epoch_id"]=="sor-v0":
            raise SelectionJobConflict("Static Generation source kind differs")
        pending = (await self._connection.execute(sa.select(strategy_universe_materialization_events.c.payload).where(
            strategy_universe_materialization_events.c.materialization_generation_id==materialization_generation_id,
            strategy_universe_materialization_events.c.event_sequence==1,
            strategy_universe_materialization_events.c.event_type=="PENDING"))).scalar_one_or_none()
        if pending is None or not isinstance(pending.get("authorization_id"),str):
            raise SelectionJobConflict("Static Generation lacks frozen Owner source")
        previous = (await self._connection.execute(sa.select(materialization_generation_event_baselines).where(
            materialization_generation_event_baselines.c.materialization_generation_id==materialization_generation_id,
        ).limit(2))).mappings().all()
        generation = GenericStaticMaterializationGeneration.model_validate({
            **{key:row[key] for key in GenericStaticMaterializationGeneration.model_fields
                if key not in {"previous_events","authorization_id","effective_period_anchor_ms"}},
            "authorization_id":pending["authorization_id"],"effective_period_anchor_ms":pending.get("effective_period_anchor_ms"),
            "previous_events":tuple(MaterializationEventBaseline.model_validate({key:event[key]
                for key in MaterializationEventBaseline.model_fields}) for event in previous)})
        if generation.semantic_digest!=row["semantic_digest"]:
            raise SelectionJobConflict("Static Generation semantic identity differs")
        return generation

    async def create_generic_static_materialization_generation(self, *, strategy_group_id: str,
        created_at_ms: int,
    ) -> GenericStaticMaterializationGeneration:
        from src.trading_kernel.infrastructure.pg_universe_repository import (
            PostgresStrategyUniverseRepository,
        )
        owner = (await self._connection.execute(sa.select(strategy_entry_controls_current).where(
            strategy_entry_controls_current.c.strategy_group_id==strategy_group_id).with_for_update())).mappings().one_or_none()
        control = await self.get_selection_control(strategy_group_id,for_update=True)
        now = await self.read_authority_clock_ms()
        if owner is None or owner["entry_state"]!="enabled" or control is None or (
            control.selection_mode is not SelectionMode.DYNAMIC_SELECTION
            or control.pending_selection_mode is not SelectionMode.STATIC_BASELINE
            or control.pending_authorization_id is None or control.pending_effective_period_anchor_ms is None
            or control.selection_epoch_id is None or control.rollback_baseline_id is None
            or not control.pending_effective_period_anchor_ms+3_600_000<=created_at_ms<=now):
            raise SelectionJobConflict("Static Generation requires due exact Owner intent")
        spec = await self.get_generic_spec(control.selection_spec_id)
        baseline = await self.get_generic_static_rollback_baseline(control.rollback_baseline_id)
        if baseline.selection_spec_id!=spec.selection_spec_id or baseline.strategy_group_id!=strategy_group_id:
            raise SelectionJobConflict("Static Generation baseline source changed")
        authorization = (await self._connection.execute(sa.select(owner_authorizations).where(
            owner_authorizations.c.authorization_id==control.pending_authorization_id))).mappings().one_or_none()
        expected_scope = {"strategy_group_id":strategy_group_id,"selection_spec_id":spec.selection_spec_id,
            "target_selection_mode":"static_baseline","rollback_baseline_id":baseline.rollback_baseline_id,
            "selection_epoch_id":control.selection_epoch_id,"effective_period_anchor_ms":control.pending_effective_period_anchor_ms}
        if authorization is None or authorization["purpose"]!="selection_mode_change" or (
            authorization["authentication_strength"]!="totp_step_up" or authorization["target_scope"]!=expected_scope
            or authorization["authorized_at_ms"]>created_at_ms):
            raise SelectionJobConflict("Static Generation Owner proof changed")
        generation_id = GenericStaticMaterializationGeneration.id_for_authorization(control.pending_authorization_id)
        existing = await self.get_generic_static_materialization_generation(generation_id,for_update=True)
        if existing is not None:
            if existing.authorization_id!=control.pending_authorization_id or existing.selection_control_version!=control.control_version:
                raise SelectionJobConflict("Static Generation current source changed")
            return existing
        retry_vacuum = await self.get_current_entry_vacuum(strategy_group_id=strategy_group_id,selection_spec_id=spec.selection_spec_id,for_update=True)
        retry_source = None
        if retry_vacuum is not None:
            if retry_vacuum.source_generation_id is None:
                raise SelectionJobConflict("Static retry requires exact terminal source")
            retry_source = await self.get_generic_static_materialization_generation(retry_vacuum.source_generation_id,for_update=True)
            link = await self._connection.scalar(sa.select(strategy_universe_materialization_events.c.materialization_event_id).where(
                strategy_universe_materialization_events.c.materialization_generation_id==retry_vacuum.source_generation_id,
                strategy_universe_materialization_events.c.event_type=="OWNER_REAUTHORIZED",
                strategy_universe_materialization_events.c.payload["authorization_id"].astext==control.pending_authorization_id).limit(1))
            if retry_source is None or retry_source.lifecycle_state not in {MaterializationGenerationState.FAILED_CLOSED,MaterializationGenerationState.ABANDONED} or (
                link is None or retry_source.rollback_baseline_id!=control.rollback_baseline_id
                or retry_source.selection_epoch_id!=control.selection_epoch_id
                or retry_source.selection_control_version!=control.control_version
                or retry_vacuum.state not in {StrategyEntryVacuumState.RECONFIGURING,StrategyEntryVacuumState.OWNER_PAUSED}
                or retry_vacuum.drained_at_ms is None or retry_vacuum.resolved_at_ms is not None
                or await self.entry_vacuum_has_drain_blockers(strategy_group_id=strategy_group_id)
                or await self.get_next_entry_vacuum_ticket(strategy_group_id=strategy_group_id) is not None):
                raise SelectionJobConflict("Static retry requires authorized terminal drained source")
        if await self._connection.scalar(sa.select(sa.exists().where(
                strategy_universe_materialization_generations.c.strategy_group_id==strategy_group_id,
                strategy_universe_materialization_generations.c.lifecycle_state.in_(("PENDING","DESIRED","DRAINING_ENTRY","MATERIALIZING","STAGED"))))):
            raise SelectionJobConflict("Static Generation previous transition requires coordinated handoff")
        universes = PostgresStrategyUniverseRepository(self._connection)
        current = await universes.get_current(spec.event_spec_id)
        if current is None:
            raise SelectionJobConflict("Static Generation previous current Universe missing")
        current_members = await universes.get_members(current.universe_version_id)
        target_members = await universes.get_members(baseline.source_event.universe_version_id)
        if not 1<=len(target_members)<=10 or selected_member_set_digest(target_members)!=baseline.source_event.member_set_digest:
            raise SelectionJobConflict("Static Generation frozen target members changed")
        comparison = await self.get_comparison_universe_binding(spec.event_spec_id,for_update=True) if (
            strategy_group_id in {"MPG-001","MI-001"}) else None
        generation = GenericStaticMaterializationGeneration(
            materialization_generation_id=generation_id,selection_spec_id=spec.selection_spec_id,
            strategy_group_id=strategy_group_id,strategy_version_id=spec.strategy_version_id,
            rollback_baseline_id=baseline.rollback_baseline_id,authorization_id=control.pending_authorization_id,
            effective_period_anchor_ms=control.pending_effective_period_anchor_ms,
            selection_epoch_id=control.selection_epoch_id,selection_control_version=control.control_version,
            desired_member_count=len(target_members),created_at_ms=created_at_ms,
            previous_events=(MaterializationEventBaseline(event_spec_id=spec.event_spec_id,position_side=spec.position_side,
                grant_state=AuthorityEventGrantState.ACTIVE,universe_version_id=current.universe_version_id,
                member_set_digest=selected_member_set_digest(current_members),
                comparison_universe_id=None if comparison is None else comparison.comparison_universe_id,
                comparison_transition_revision=None if comparison is None else comparison.comparison_transition_revision),))
        if retry_source is not None and generation.previous_events!=retry_source.previous_events:
            raise SelectionJobConflict("Static retry previous Active source changed")
        await self._connection.execute(sa.insert(strategy_universe_materialization_generations).values(
            **generation.model_dump(mode="json",exclude={"authorization_id","effective_period_anchor_ms","previous_events"}),
            semantic_digest=generation.semantic_digest))
        await self._connection.execute(sa.insert(materialization_generation_event_baselines).values(
            materialization_generation_id=generation_id,**generation.previous_events[0].model_dump(mode="json")))
        await self._connection.execute(sa.insert(strategy_universe_materialization_targets).values(
            materialization_generation_id=generation_id,event_spec_id=spec.event_spec_id,position_side=spec.position_side,
            materialization_order=1 if spec.position_side=="long" else 2,expected_member_set_digest=baseline.source_event.member_set_digest))
        await self._connection.execute(sa.insert(strategy_universe_materialization_events).values(
            materialization_event_id=f"materialization-event:{generation_id}:1",materialization_generation_id=generation_id,
            event_sequence=1,event_type="PENDING",payload={"authorization_id":control.pending_authorization_id,
                "effective_period_anchor_ms":control.pending_effective_period_anchor_ms,
                **({"previous_static_generation_id":retry_source.materialization_generation_id} if retry_source is not None else {})},occurred_at_ms=created_at_ms))
        if retry_source is not None and retry_vacuum is not None:
            generation = GenericStaticMaterializationGeneration.model_validate({**generation.model_dump(),
                "lifecycle_state":"MATERIALIZING","desired_at_ms":now,"fenced_at_ms":now,"projection_version":4})
            await self._connection.execute(sa.update(strategy_universe_materialization_generations).where(
                strategy_universe_materialization_generations.c.materialization_generation_id==generation_id).values(
                    lifecycle_state="MATERIALIZING",desired_at_ms=now,fenced_at_ms=now,projection_version=4))
            payload = {"entry_vacuum_id":retry_vacuum.entry_vacuum_id,
                "previous_static_generation_id":retry_source.materialization_generation_id,
                "original_fenced_at_ms":retry_vacuum.fenced_at_ms,"original_drained_at_ms":retry_vacuum.drained_at_ms}
            for sequence,event_type in ((2,"DESIRED"),(3,"DRAINING_ENTRY"),(4,"MATERIALIZING")):
                await self._connection.execute(sa.insert(strategy_universe_materialization_events).values(
                    materialization_event_id=f"materialization-event:{generation_id}:{sequence}",materialization_generation_id=generation_id,
                    event_sequence=sequence,event_type=event_type,payload=payload,occurred_at_ms=now))
            await self._connection.execute(sa.insert(strategy_entry_vacuum_events).values(
                entry_vacuum_event_id=f"vacuum-event:{retry_vacuum.entry_vacuum_id}:{retry_vacuum.projection_version+1}",
                entry_vacuum_id=retry_vacuum.entry_vacuum_id,event_sequence=retry_vacuum.projection_version+1,event_type="SUPERSEDED",
                payload={"previous_generation_id":retry_source.materialization_generation_id,
                    "replacement_generation_id":generation_id,"recovery_origin":"STATIC_RETRY"},occurred_at_ms=now))
            changed = await self._connection.execute(sa.update(strategy_entry_vacuums_current).where(
                strategy_entry_vacuums_current.c.entry_vacuum_id==retry_vacuum.entry_vacuum_id,
                strategy_entry_vacuums_current.c.projection_version==retry_vacuum.projection_version).values(
                    source_generation_id=generation_id,period_anchor_ms=generation.effective_period_anchor_ms,
                    state="RECONFIGURING",first_blocker="STATIC_RETRY_RECOVERY",projection_version=retry_vacuum.projection_version+1))
            if changed.rowcount!=1:
                raise SelectionJobConflict("Static retry original Vacuum CAS changed")
        return generation

    async def require_static_materialization_vacuum(self, generation: GenericStaticMaterializationGeneration,
        vacuum: StrategyEntryVacuum,
    ) -> bool:
        """Authenticate preserved drain separately from this operation's timeout."""
        source = (await self._connection.execute(sa.select(strategy_universe_materialization_events.c.payload).where(
            strategy_universe_materialization_events.c.materialization_generation_id==generation.materialization_generation_id,
            strategy_universe_materialization_events.c.event_type=="PENDING",
            strategy_universe_materialization_events.c.event_sequence==1))).scalar_one()
        previous_id = source.get("previous_static_generation_id")
        if previous_id is None:
            if vacuum.fenced_at_ms!=generation.fenced_at_ms:
                raise SelectionJobConflict("Static original fence identity changed")
            return False
        old = await self.get_generic_static_materialization_generation(previous_id)
        handoff = (await self._connection.execute(sa.select(strategy_entry_vacuum_events).where(
            strategy_entry_vacuum_events.c.entry_vacuum_id==vacuum.entry_vacuum_id,
            strategy_entry_vacuum_events.c.event_type=="SUPERSEDED",
            strategy_entry_vacuum_events.c.payload["replacement_generation_id"].astext==generation.materialization_generation_id).limit(1))).mappings().one_or_none()
        if old is None or handoff is None or old.lifecycle_state not in {MaterializationGenerationState.FAILED_CLOSED,MaterializationGenerationState.ABANDONED} or (
            old.previous_events!=generation.previous_events or old.rollback_baseline_id!=generation.rollback_baseline_id
            or old.selection_epoch_id!=generation.selection_epoch_id or old.selection_control_version!=generation.selection_control_version
            or handoff["payload"]!={"previous_generation_id":previous_id,"replacement_generation_id":generation.materialization_generation_id,"recovery_origin":"STATIC_RETRY"}
            or handoff["occurred_at_ms"]!=generation.fenced_at_ms or vacuum.drained_at_ms is None
            or generation.fenced_at_ms is None or not vacuum.fenced_at_ms<=vacuum.drained_at_ms<generation.fenced_at_ms):
            raise SelectionJobConflict("Static retry handoff provenance changed")
        if not await self._connection.scalar(sa.select(sa.exists().where(
            strategy_entry_vacuum_events.c.entry_vacuum_id==vacuum.entry_vacuum_id,
            sa.or_(strategy_entry_vacuum_events.c.event_type=="ENTRY_DRAINED",sa.and_(
                strategy_entry_vacuum_events.c.event_type=="OWNER_PAUSED",
                strategy_entry_vacuum_events.c.payload["entry_drain_complete"]==sa.cast(sa.literal("true"),sa.dialects.postgresql.JSONB))),
            strategy_entry_vacuum_events.c.occurred_at_ms==vacuum.drained_at_ms))):
            raise SelectionJobConflict("Static retry original drain provenance changed")
        return True

    async def _require_current_static_generation(self, materialization_generation_id: str) -> GenericStaticMaterializationGeneration:
        initial = await self.get_generic_static_materialization_generation(materialization_generation_id)
        if initial is None:
            raise SelectionJobConflict("Static Generation missing")
        owner = (await self._connection.execute(sa.select(strategy_entry_controls_current).where(
            strategy_entry_controls_current.c.strategy_group_id==initial.strategy_group_id).with_for_update())).mappings().one_or_none()
        control = await self.get_selection_control(initial.strategy_group_id,for_update=True)
        await self.get_current_entry_vacuum(strategy_group_id=initial.strategy_group_id,
            selection_spec_id=initial.selection_spec_id,for_update=True)
        current = await self.get_generic_static_materialization_generation(materialization_generation_id,for_update=True)
        if owner is None or owner["entry_state"]!="enabled" or current is None or control is None or (
            control.selection_spec_id!=current.selection_spec_id
            or control.selection_mode is not SelectionMode.DYNAMIC_SELECTION
            or control.pending_selection_mode is not SelectionMode.STATIC_BASELINE
            or control.selection_epoch_id!=current.selection_epoch_id or control.control_version!=current.selection_control_version
            or control.pending_authorization_id!=current.authorization_id
            or control.pending_effective_period_anchor_ms!=current.effective_period_anchor_ms
            or control.rollback_baseline_id!=current.rollback_baseline_id):
            raise SelectionJobConflict("Static Generation Owner or Control changed")
        prior = current.previous_events[0]
        active = (await self._connection.execute(sa.select(strategy_universe_current).where(
            strategy_universe_current.c.event_spec_id==prior.event_spec_id))).mappings().one_or_none()
        if active is None or active["lifecycle_state"]!="active" or active["universe_version_id"]!=prior.universe_version_id:
            raise SelectionJobConflict("Static Generation previous current Universe changed")
        if prior.comparison_universe_id is not None:
            comparison = await self.get_comparison_universe_binding(prior.event_spec_id)
            if comparison is None or (comparison.comparison_universe_id,comparison.comparison_transition_revision)!=(
                prior.comparison_universe_id,prior.comparison_transition_revision):
                raise SelectionJobConflict("Static Generation previous comparison changed")
        return current

    async def claim_generic_static_materialization_generation(self, materialization_generation_id: str, *,
        worker_id: str, now_ms: int, lease_duration_ms: int,
    ) -> GenericStaticMaterializationGeneration | None:
        current = await self._require_current_static_generation(materialization_generation_id)
        now = await self.read_authority_clock_ms()
        if not current.created_at_ms<=now_ms<=now or current.lifecycle_state not in {
            MaterializationGenerationState.PENDING,MaterializationGenerationState.DESIRED,MaterializationGenerationState.DRAINING_ENTRY,
            MaterializationGenerationState.MATERIALIZING,MaterializationGenerationState.STAGED}:
            raise SelectionJobConflict("Static Generation is not actionable")
        row = (await self._connection.execute(sa.select(strategy_universe_materialization_generations).where(
            strategy_universe_materialization_generations.c.materialization_generation_id==materialization_generation_id))).mappings().one()
        if not await self._acquire_materialization_lease(row,worker_id=worker_id,now_ms=now_ms,
            lease_duration_ms=lease_duration_ms,strict_owner=True):
            return None
        return await self.get_generic_static_materialization_generation(materialization_generation_id)

    async def mark_generic_static_materialization_generation_desired(self, materialization_generation_id: str, *,
        worker_id: str, lease_epoch: int, expected_projection_version: int, desired_at_ms: int,
    ) -> GenericStaticMaterializationGeneration:
        current = await self._require_current_static_generation(materialization_generation_id)
        now = await self.read_authority_clock_ms()
        if not current.created_at_ms<=desired_at_ms<=now or current.projection_version!=expected_projection_version or (
            current.lease_owner!=worker_id or current.lease_epoch!=lease_epoch or current.lease_expires_at_ms is None
            or now>=current.lease_expires_at_ms):
            raise SelectionJobConflict("Static Generation lease/version changed")
        if current.lifecycle_state is MaterializationGenerationState.DESIRED:
            return current
        if current.lifecycle_state is not MaterializationGenerationState.PENDING:
            raise SelectionJobConflict("Static Generation is not PENDING")
        desired = GenericStaticMaterializationGeneration.model_validate({**current.model_dump(),
            "lifecycle_state":"DESIRED","desired_at_ms":desired_at_ms,"projection_version":current.projection_version+1})
        changed = await self._connection.execute(sa.update(strategy_universe_materialization_generations).where(
            strategy_universe_materialization_generations.c.materialization_generation_id==materialization_generation_id,
            strategy_universe_materialization_generations.c.projection_version==expected_projection_version,
            strategy_universe_materialization_generations.c.lease_epoch==lease_epoch).values(
                lifecycle_state="DESIRED",desired_at_ms=desired_at_ms,projection_version=desired.projection_version))
        if changed.rowcount!=1:
            raise SelectionJobConflict("Static Generation desired CAS changed")
        await self._connection.execute(sa.insert(strategy_universe_materialization_events).values(
            materialization_event_id=f"materialization-event:{materialization_generation_id}:2",
            materialization_generation_id=materialization_generation_id,event_sequence=2,event_type="DESIRED",
            payload={"authorization_id":current.authorization_id},occurred_at_ms=desired_at_ms))
        return desired

    async def fail_generic_static_materialization_generation(self, materialization_generation_id: str, *,
        worker_id: str, lease_epoch: int, expected_projection_version: int, reason_code: str,
    ) -> GenericStaticMaterializationGeneration:
        from src.trading_kernel.application.abandon_strategy_universe import (
            AbandonStrategyUniverseRequest,
        )
        from src.trading_kernel.infrastructure.pg_universe_repository import (
            PostgresStrategyUniverseRepository,
        )

        if reason_code not in {"MATERIALIZATION_TIMEOUT","CERTIFICATION_OWNER_ACTION_REQUIRED","CERTIFICATION_NOT_ELIGIBLE"}:
            raise ValueError("Static Generation requires classified failure")
        current = await self._require_current_static_generation(materialization_generation_id)
        now = await self.read_authority_clock_ms()
        if current.lifecycle_state not in {MaterializationGenerationState.MATERIALIZING,MaterializationGenerationState.STAGED} or (
            current.projection_version!=expected_projection_version or current.lease_owner!=worker_id
            or current.lease_epoch!=lease_epoch or current.lease_expires_at_ms is None or now>=current.lease_expires_at_ms
            or current.fenced_at_ms is None or now<current.fenced_at_ms):
            raise SelectionJobConflict("Static failure Generation lease/state changed")
        spec = await self.get_generic_spec(current.selection_spec_id)
        deadline = current.fenced_at_ms+spec.materialization_timeout_ms
        if reason_code=="MATERIALIZATION_TIMEOUT" and now<deadline:
            raise SelectionJobConflict("Static failure deadline has not elapsed")
        vacuum = await self.get_current_entry_vacuum(strategy_group_id=current.strategy_group_id,
            selection_spec_id=current.selection_spec_id,for_update=True)
        if vacuum is None or vacuum.source_generation_id!=materialization_generation_id or (
            vacuum.state is not StrategyEntryVacuumState.RECONFIGURING or current.fenced_at_ms is None or vacuum.fenced_at_ms>current.fenced_at_ms
            or vacuum.drained_at_ms is None or vacuum.resolved_at_ms is not None
            or await self.entry_vacuum_has_drain_blockers(strategy_group_id=current.strategy_group_id)):
            raise SelectionJobConflict("Static failure requires original drained Vacuum")
        await self.require_static_materialization_vacuum(current,vacuum)
        universes = PostgresStrategyUniverseRepository(self._connection)
        targets = await universes.get_generation_universe_targets(materialization_generation_id,for_update=True)
        if len(targets)>1:
            raise SelectionJobConflict("Static failure target set changed")
        for target in targets:
            if target.lifecycle_state.value not in {"warming","staged","abandoned"}:
                raise SelectionJobConflict("Static failure cannot abandon active target")
            if target.lifecycle_state.value!="abandoned":
                await universes.abandon(AbandonStrategyUniverseRequest(universe_version_id=target.universe_version_id,
                    reason_code=reason_code.lower(),attempted_at_ms=now))
        failed = GenericStaticMaterializationGeneration.model_validate({**current.model_dump(),
            "lifecycle_state":"FAILED_CLOSED","terminal_at_ms":now,"lease_owner":None,
            "lease_expires_at_ms":None,"projection_version":current.projection_version+1})
        changed = await self._connection.execute(sa.update(strategy_universe_materialization_generations).where(
            strategy_universe_materialization_generations.c.materialization_generation_id==materialization_generation_id,
            strategy_universe_materialization_generations.c.projection_version==expected_projection_version,
            strategy_universe_materialization_generations.c.lease_epoch==lease_epoch).values(
                lifecycle_state="FAILED_CLOSED",terminal_at_ms=now,lease_owner=None,lease_expires_at_ms=None,
                projection_version=failed.projection_version))
        if changed.rowcount!=1:
            raise SelectionJobConflict("Static failure Generation CAS changed")
        sequence = int(await self._connection.scalar(sa.select(sa.func.max(strategy_universe_materialization_events.c.event_sequence)).where(
            strategy_universe_materialization_events.c.materialization_generation_id==materialization_generation_id)) or 0)+1
        await self._connection.execute(sa.insert(strategy_universe_materialization_events).values(
            materialization_event_id=f"materialization-event:{materialization_generation_id}:{sequence}",
            materialization_generation_id=materialization_generation_id,event_sequence=sequence,event_type="FAILED_CLOSED",
            payload={"entry_vacuum_id":vacuum.entry_vacuum_id,"reason_code":reason_code,"materialization_deadline_ms":deadline},
            occurred_at_ms=now))
        changed_vacuum = await self._connection.execute(sa.update(strategy_entry_vacuums_current).where(
            strategy_entry_vacuums_current.c.entry_vacuum_id==vacuum.entry_vacuum_id,
            strategy_entry_vacuums_current.c.projection_version==vacuum.projection_version).values(
                first_blocker=reason_code,projection_version=vacuum.projection_version+1))
        if changed_vacuum.rowcount!=1:
            raise SelectionJobConflict("Static failure Vacuum CAS changed")
        await self._connection.execute(sa.insert(strategy_entry_vacuum_events).values(
            entry_vacuum_event_id=f"vacuum-event:{vacuum.entry_vacuum_id}:{vacuum.projection_version+1}",
            entry_vacuum_id=vacuum.entry_vacuum_id,event_sequence=vacuum.projection_version+1,event_type="RECOVERY_REQUIRED",
            payload={"reason_code":reason_code,"source_generation_id":materialization_generation_id},occurred_at_ms=now))
        return failed

    async def prepare_generic_static_activation_proof(self, materialization_generation_id: str, *,
        worker_id: str, lease_epoch: int,
    ) -> GenericStaticActivationProof:
        from src.trading_kernel.application.advance_strategy_universe import (
            UniverseActivationOperation,
            UniverseActivationRequest,
            UniverseActivationStatus,
        )
        from src.trading_kernel.infrastructure.pg_signal_repository import (
            PostgresSignalRepository,
        )
        from src.trading_kernel.infrastructure.pg_universe_repository import (
            PostgresStrategyUniverseRepository,
        )

        generation = await self._require_current_static_generation(materialization_generation_id)
        now = await self.read_authority_clock_ms()
        spec = await self.get_generic_spec(generation.selection_spec_id)
        if generation.lifecycle_state is not MaterializationGenerationState.STAGED or generation.fenced_at_ms is None or (
            generation.lease_owner!=worker_id or generation.lease_epoch!=lease_epoch
            or generation.lease_expires_at_ms is None or now>=generation.lease_expires_at_ms
            or now>=generation.fenced_at_ms+spec.materialization_timeout_ms):
            raise SelectionJobConflict("Static activation requires current staged lease and deadline")
        vacuum = await self.get_current_entry_vacuum(strategy_group_id=generation.strategy_group_id,
            selection_spec_id=generation.selection_spec_id,for_update=True)
        if vacuum is None or vacuum.source_generation_id!=materialization_generation_id or (
            vacuum.state is not StrategyEntryVacuumState.RECONFIGURING or vacuum.drained_at_ms is None
            or vacuum.resolved_at_ms is not None or vacuum.fenced_at_ms>generation.fenced_at_ms
            or await self.entry_vacuum_has_drain_blockers(strategy_group_id=generation.strategy_group_id)):
            raise SelectionJobConflict("Static activation requires exact completed drain")
        retry_handoff = await self.require_static_materialization_vacuum(generation,vacuum)
        source = await self.get_current_generic_authority(generation.selection_spec_id,for_update=True)
        if source is None or source.authority.selection_epoch_id!=generation.selection_epoch_id or (
            source.authority.selection_control_version!=generation.selection_control_version):
            raise SelectionJobConflict("Static activation previous Authority changed")
        previous = generation.previous_events[0]
        if not source.authority.blocks_new_entry and (source.authority.event_binding.event_spec_id!=previous.event_spec_id
            or source.authority.event_binding.position_side!=previous.position_side
            or source.authority.event_binding.universe_version_id!=previous.universe_version_id
            or source.authority.event_binding.member_set_digest!=previous.member_set_digest
            or source.authority.comparison_universe_id!=previous.comparison_universe_id
            or source.authority.comparison_transition_revision!=previous.comparison_transition_revision):
            raise SelectionJobConflict("Static activation previous Authority scope changed")
        baseline = await self.get_generic_static_rollback_baseline(generation.rollback_baseline_id)
        universes = PostgresStrategyUniverseRepository(self._connection)
        targets = await universes.get_generation_universe_targets(materialization_generation_id,for_update=True)
        if len(targets)!=1 or targets[0].lifecycle_state.value!="staged":
            raise SelectionJobConflict("Static activation exact staged target missing")
        target_id = targets[0].universe_version_id
        members = await universes.get_members(target_id)
        if selected_member_set_digest(members)!=baseline.source_event.member_set_digest:
            raise SelectionJobConflict("Static activation target differs from baseline")
        certified = await universes.try_activate(UniverseActivationRequest(universe_version_id=target_id,
            attempted_at_ms=now,operation=UniverseActivationOperation.CERTIFY_STAGED,
            materialization_generation_id=materialization_generation_id,
            materialization_lease_owner=worker_id,materialization_lease_epoch=lease_epoch))
        if certified.status is not UniverseActivationStatus.STAGED:
            raise SelectionJobConflict("Static activation target not ready: "+str(certified.reason_code))
        scopes = (await self._connection.execute(sa.select(runtime_scopes_current.c.owner_policy_id).where(
            runtime_scopes_current.c.universe_version_id==target_id).distinct().limit(2))).scalars().all()
        if len(scopes)!=1:
            raise SelectionJobConflict("Static activation Policy scope changed")
        policy = (await self._connection.execute(sa.select(owner_policy_current).where(
            owner_policy_current.c.owner_policy_id==scopes[0]).with_for_update())).mappings().one_or_none()
        if policy is None or not policy["enabled"] or not policy["new_entry_submit_enabled"]:
            raise SelectionJobConflict("Static activation Policy blocks Entry")
        owner = (await self._connection.execute(sa.select(strategy_entry_controls_current).where(
            strategy_entry_controls_current.c.strategy_group_id==generation.strategy_group_id))).mappings().one()
        authorization = (await self._connection.execute(sa.select(owner_authorizations).where(
            owner_authorizations.c.authorization_id==generation.authorization_id))).mappings().one()
        signals = PostgresSignalRepository(self._connection)
        reason: Literal["AUTHORITY_GAP","OWNER_INTERRUPTION","RECOVERY_PROVENANCE"] | None = None
        if retry_handoff or source.authority.blocks_new_entry or source.authority.expires_at_ms<generation.effective_period_anchor_ms+3600000:
            reason = "AUTHORITY_GAP"
        elif source.authority.owner_control_version!=owner["control_version"] or await signals.selection_authority_was_interrupted(strategy_group_id=generation.strategy_group_id,
            selection_spec_id=generation.selection_spec_id,owner_policy_id=scopes[0],after_ms=source.authority.created_at_ms,
            through_ms=now,excluded_entry_vacuum_id=vacuum.entry_vacuum_id):
            reason = "OWNER_INTERRUPTION"
        elif isinstance(source.authority,GenericRecoveryAuthority) or source.authority.continued_from_recovery_authority_id is not None:
            blocker = await self.generic_recovery_transition_blocker(selection_spec_id=generation.selection_spec_id,target_members=members)
            if blocker=="GENERIC_RECOVERY_REBASE_PENDING":
                reason = "RECOVERY_PROVENANCE"
            elif blocker is not None:
                raise SelectionJobConflict("Static activation recovery source changed: "+blocker)
        cursors = await signals.lock_recovery_close_coverage(event_spec_id=spec.event_spec_id,exchange_instrument_ids=members,
            selection_mode="static_baseline",evaluated_at_ms=now)
        comparison_id = baseline.source_event.comparison_universe_id
        old_comparison = generation.previous_events[0].comparison_universe_id
        old_revision = generation.previous_events[0].comparison_transition_revision
        prepared = await self.read_authority_clock_ms()
        if prepared<now or prepared//3600000!=now//3600000 or prepared>=generation.fenced_at_ms+spec.materialization_timeout_ms or (
            generation.lease_expires_at_ms is None or prepared>=generation.lease_expires_at_ms):
            raise SelectionJobConflict("Static activation preparation crossed close/deadline")
        return GenericStaticActivationProof(selection_spec_id=spec.selection_spec_id,strategy_group_id=spec.strategy_group_id,
            selection_epoch_id=generation.selection_epoch_id,selection_control_version=generation.selection_control_version,
            owner_control_version=owner["control_version"],authorization_id=generation.authorization_id,
            owner_authorized_at_ms=authorization["authorized_at_ms"],rollback_baseline_id=generation.rollback_baseline_id,
            materialization_generation_id=materialization_generation_id,effective_period_anchor_ms=generation.effective_period_anchor_ms,
            entry_vacuum_id=vacuum.entry_vacuum_id,vacuum_version=vacuum.projection_version,
            fenced_at_ms=vacuum.fenced_at_ms,drained_at_ms=vacuum.drained_at_ms,materialization_started_at_ms=generation.fenced_at_ms,
            previous_event=generation.previous_events[0],source_selection_authority_id=source.authority.selection_authority_id,
            target_event=AuthorityEventBinding(event_spec_id=spec.event_spec_id,position_side=spec.position_side,
                grant_state=AuthorityEventGrantState.ACTIVE,universe_version_id=target_id,member_set_digest=baseline.source_event.member_set_digest),
            transition_rule="NORMAL_TRANSITION" if reason is None else "RECOVERY_TRANSITION",recovery_reason=reason,
            first_eligible_close_time_ms=(prepared//3600000+int(reason is not None))*3600000,prepared_at_ms=prepared,
            comparison_universe_id=comparison_id,comparison_transition_revision=None if old_revision is None else (
                old_revision+int(comparison_id!=old_comparison)),observation_cursors=cursors)

    async def require_generic_static_activation_proof(self, proof: GenericStaticActivationProof, *,
        worker_id: str, lease_epoch: int,
    ) -> int:
        """Re-derive locked pre-state; a previously prepared object is not authority."""
        proof = GenericStaticActivationProof.model_validate(proof.model_dump())
        started = await self.read_authority_clock_ms()
        if started<proof.prepared_at_ms or started//3600000!=proof.prepared_at_ms//3600000:
            raise SelectionJobConflict("Static activation proof crossed close boundary")
        current = await self.prepare_generic_static_activation_proof(proof.materialization_generation_id,
            worker_id=worker_id,lease_epoch=lease_epoch)
        # The original preparation timestamp stays immutable. Every other
        # field, including cursors, is freshly derived in this transaction.
        expected = GenericStaticActivationProof.model_validate({**current.model_dump(),"prepared_at_ms":proof.prepared_at_ms})
        if expected!=proof:
            raise SelectionJobConflict("Static activation proof changed")
        checked = await self.read_authority_clock_ms()
        if checked<started or checked//3600000!=started//3600000:
            raise SelectionJobConflict("Static activation proof crossed close boundary")
        return checked

    async def get_generic_static_activation_proof(self, materialization_generation_id: str) -> GenericStaticActivationProof | None:
        generation = await self.get_generic_static_materialization_generation(materialization_generation_id)
        if generation is None or generation.lifecycle_state is not MaterializationGenerationState.ACTIVE:
            return None
        rows = (await self._connection.execute(sa.select(strategy_universe_materialization_events).where(
            strategy_universe_materialization_events.c.materialization_generation_id==materialization_generation_id,
            strategy_universe_materialization_events.c.event_type=="ACTIVE").limit(2))).mappings().all()
        if len(rows)!=1 or "static_activation_proof" not in rows[0]["payload"]:
            raise SelectionJobConflict("Static activation committed proof missing")
        proof = GenericStaticActivationProof.model_validate(rows[0]["payload"]["static_activation_proof"])
        if proof.materialization_generation_id!=generation.materialization_generation_id or proof.authorization_id!=generation.authorization_id or (
            proof.rollback_baseline_id!=generation.rollback_baseline_id or proof.selection_spec_id!=generation.selection_spec_id
            or proof.selection_epoch_id!=generation.selection_epoch_id or proof.selection_control_version!=generation.selection_control_version
            or generation.activated_at_ms!=rows[0]["occurred_at_ms"] or generation.terminal_at_ms!=generation.activated_at_ms
            or generation.activated_at_ms is None or proof.prepared_at_ms>generation.activated_at_ms):
            raise SelectionJobConflict("Static activation committed source changed")
        return proof

    async def get_generic_static_activation_proof_for_universe(self, universe_version_id: str) -> GenericStaticActivationProof | None:
        row = (await self._connection.execute(sa.select(strategy_universe_versions).where(
            strategy_universe_versions.c.universe_version_id==universe_version_id))).mappings().one_or_none()
        if row is None or row["source_kind"]!="static_baseline":
            return None
        if row["lifecycle_state"]!="active" or row["materialization_generation_id"] is None:
            raise SelectionJobConflict("Static activation Universe is not current active source")
        proof = await self.get_generic_static_activation_proof(row["materialization_generation_id"])
        if proof is None or proof.target_event.universe_version_id!=universe_version_id:
            raise SelectionJobConflict("Static activation Universe proof missing")
        return proof

    async def initialize_generic_static_recovery_checkpoints(self, proof: GenericStaticActivationProof) -> None:
        from src.trading_kernel.infrastructure.pg_signal_repository import (
            PostgresSignalRepository,
        )
        if not proof.episode_rebase_required:
            return
        signals = PostgresSignalRepository(self._connection)
        async with self._connection.begin_nested():
            for cursor in proof.observation_cursors:
                current = await signals.lock_exposure_episode(cursor.episode_domain_key)
                prior = await signals.get_authority_recovery_checkpoint(cursor.episode_domain_key)
                if (0 if current is None else current.projection_version)!=cursor.episode_version or (
                    (0 if prior is None else prior.projection_version)!=cursor.authority_recovery_checkpoint_version):
                    raise SelectionJobConflict("Static recovery initialization cursor changed")
                checkpoint = begin_authority_recovery_rebase(current=prior,episode_domain_key=cursor.episode_domain_key,
                    recovery_id=proof.recovery_id,recovery_revision=proof.result_selection_control_version,
                    effective_from_ms=proof.prepared_at_ms,first_eligible_close_time_ms=proof.first_eligible_close_time_ms,
                    latest_consumed_close_time_ms=cursor.last_observed_at_ms)
                values = {"authority_recovery_id":checkpoint.recovery_id,"authority_recovery_revision":checkpoint.recovery_revision,
                    "authority_recovery_effective_from_ms":checkpoint.effective_from_ms,
                    "authority_recovery_first_eligible_close_time_ms":checkpoint.first_eligible_close_time_ms,
                    "authority_recovery_armed_at_ms":None,"authority_recovery_last_observed_at_ms":checkpoint.last_observed_close_time_ms,
                    "authority_recovery_last_detector_status":None,"authority_recovery_checkpoint_version":checkpoint.projection_version}
                if current is None:
                    current = ExposureEpisodeState(episode_domain_key=cursor.episode_domain_key,
                        event_spec_id=proof.target_event.event_spec_id,exchange_instrument_id=cursor.exchange_instrument_id,
                        position_side=proof.target_event.position_side,state="authority_rebase_required",exposure_episode_id=None,
                        triggered_at_ms=None,rearmed_at_ms=None,last_observed_at_ms=cursor.last_observed_at_ms,projection_version=1)
                    await self._connection.execute(sa.insert(exposure_episode_current).values(**current.model_dump(),**values))
                else:
                    await self._connection.execute(sa.update(exposure_episode_current).where(
                        exposure_episode_current.c.episode_domain_key==cursor.episode_domain_key).values(**values))

    async def get_generic_materialization_generation(
        self, materialization_generation_id: str, *, for_update: bool = False,
    ) -> GenericMaterializationGeneration | None:
        statement = sa.select(strategy_universe_materialization_generations).where(
            strategy_universe_materialization_generations.c.materialization_generation_id == materialization_generation_id)
        if for_update:
            statement = statement.with_for_update(of=strategy_universe_materialization_generations)
        row = (await self._connection.execute(statement)).mappings().one_or_none()
        if row is None:
            return None
        if row["rollback_baseline_id"] is not None:
            raise SelectionJobConflict("Dynamic Generation cannot decode a rollback source")
        spec = await self.get_generic_spec(row["selection_spec_id"])
        previous = (await self._connection.execute(sa.select(materialization_generation_event_baselines).where(
            materialization_generation_event_baselines.c.materialization_generation_id == materialization_generation_id,
        ).order_by(materialization_generation_event_baselines.c.event_spec_id))).mappings().all()
        generation = GenericMaterializationGeneration.model_validate({
            **{key:row[key] for key in GenericMaterializationGeneration.model_fields if key!="previous_events"},
            "previous_events":tuple(MaterializationEventBaseline.model_validate({key:event[key] for key in MaterializationEventBaseline.model_fields}) for event in previous),
        })
        if generation.strategy_group_id!=spec.strategy_group_id or generation.semantic_digest!=row["semantic_digest"]:
            raise SelectionJobConflict("Generic Generation semantic identity differs")
        return generation

    async def add_generic_pending_materialization_generation(
        self, generation: GenericMaterializationGeneration,
    ) -> GenericMaterializationGeneration:
        generation = GenericMaterializationGeneration.model_validate(generation.model_dump())
        if generation.lifecycle_state is not MaterializationGenerationState.PENDING or generation.lease_owner is not None or generation.lease_epoch!=0:
            raise SelectionJobConflict("new Generic Generation must be unclaimed PENDING")
        control = await self.get_selection_control(generation.strategy_group_id, for_update=True)
        if (not self._generic_control_allows(control, generation.selection_spec_id, generation.selection_epoch_id, generation.period_anchor_ms)
            or control is None or control.control_version!=generation.selection_control_version):
            raise SelectionJobConflict("Generation Selection control/epoch changed")
        snapshot = await self.get_generic_snapshot(generation.selection_snapshot_id)
        if (len(snapshot.selected_members)!=generation.desired_member_count or snapshot.committed_at_ms>generation.created_at_ms
            or snapshot.selection_epoch_id!=generation.selection_epoch_id or snapshot.feature_cutoff_at_ms!=generation.period_anchor_ms):
            raise SelectionJobConflict("Generation differs from immutable Snapshot")
        existing = await self.get_generic_materialization_generation(generation.materialization_generation_id, for_update=True)
        if existing is not None:
            if existing.semantic_digest!=generation.semantic_digest:
                raise SelectionJobConflict("Generation already exists with different frozen facts")
            return existing
        for previous in generation.previous_events:
            if previous.grant_state.value == "ACTIVE":
                current = (await self._connection.execute(sa.select(strategy_universe_current).where(
                    strategy_universe_current.c.event_spec_id==previous.event_spec_id,
                ).with_for_update(of=strategy_universe_current))).mappings().one_or_none()
                if current is None or current["universe_version_id"]!=previous.universe_version_id:
                    raise SelectionJobConflict("Generation previous current Universe changed")
                members = tuple((await self._connection.execute(sa.select(strategy_universe_members.c.exchange_instrument_id).where(
                    strategy_universe_members.c.universe_version_id==previous.universe_version_id,
                ).order_by(strategy_universe_members.c.exchange_instrument_id).limit(17))).scalars())
                if len(members)>16 or selected_member_set_digest(members)!=previous.member_set_digest:
                    raise SelectionJobConflict("Generation previous members changed")
            else:
                state = await self._connection.scalar(sa.select(selection_authority_event_bindings.c.grant_state).join(
                    selection_authority_current, selection_authority_current.c.selection_authority_id==selection_authority_event_bindings.c.selection_authority_id,
                ).where(selection_authority_current.c.selection_spec_id==generation.selection_spec_id,
                    selection_authority_event_bindings.c.event_spec_id==previous.event_spec_id))
                if state!="EMPTY":
                    raise SelectionJobConflict("Generation previous EMPTY authority is not current")
            if previous.comparison_universe_id is not None:
                comparison = (await self._connection.execute(sa.select(comparison_binding_current).where(
                    comparison_binding_current.c.event_spec_id==previous.event_spec_id,
                ).with_for_update())).mappings().one_or_none()
                if comparison is None or (comparison["comparison_universe_id"],comparison["comparison_transition_revision"])!=(previous.comparison_universe_id,previous.comparison_transition_revision):
                    raise SelectionJobConflict("Generation previous comparison changed")
        # All business validation precedes mutation, including supersession.
        values = generation.model_dump(mode="json",exclude={"previous_events"})
        await self._supersede_unfenced_generic_predecessors(snapshot,
            selection_control_version=generation.selection_control_version,
            superseded_at_ms=generation.created_at_ms,replacement_generation_id=generation.materialization_generation_id)
        await self._connection.execute(sa.insert(strategy_universe_materialization_generations).values(
            **values,rollback_baseline_id=None,semantic_digest=generation.semantic_digest))
        await self._connection.execute(sa.insert(materialization_generation_event_baselines),[
            {"materialization_generation_id":generation.materialization_generation_id,**event.model_dump(mode="json")}
            for event in generation.previous_events])
        await self._connection.execute(sa.insert(strategy_universe_materialization_targets),[
            {"materialization_generation_id":generation.materialization_generation_id,"event_spec_id":event.event_spec_id,
                "position_side":event.position_side,"materialization_order":1 if event.position_side=="long" else 2,
                "expected_member_set_digest":snapshot.member_set_digest}
            for event in generation.previous_events])
        await self._connection.execute(sa.insert(strategy_universe_materialization_events).values(
            materialization_event_id="materialization-event:"+canonical_digest({"generation":generation.materialization_generation_id,"sequence":1})[7:],
            materialization_generation_id=generation.materialization_generation_id,event_sequence=1,event_type="PENDING",
            payload={"selection_snapshot_id":generation.selection_snapshot_id,"selection_epoch_id":generation.selection_epoch_id,
                "desired_member_count":generation.desired_member_count},occurred_at_ms=generation.created_at_ms))
        return generation

    async def _supersede_unfenced_generic_predecessors(self, snapshot: GenericSelectionSnapshotV1, *,
        selection_control_version: int, superseded_at_ms: int, replacement_generation_id: str | None = None,
    ) -> None:
        """Every newer outcome invalidates obsolete unfenced work.

        Called inside the outcome transaction with the Selection Control locked.
        Never releases a fence or supersedes a drain instead of completing it.
        """
        rows = (await self._connection.execute(sa.select(strategy_universe_materialization_generations).where(
            strategy_universe_materialization_generations.c.strategy_group_id==snapshot.strategy_group_id,
            strategy_universe_materialization_generations.c.lifecycle_state.in_(("PENDING","DESIRED","DRAINING_ENTRY","MATERIALIZING","STAGED")),
        ).limit(2).with_for_update())).mappings().all()
        if len(rows)>1:
            raise SelectionJobConflict("multiple actionable Generic Generations")
        for row in rows:
            old = await self.get_generic_materialization_generation(row["materialization_generation_id"])
            if old is None or old.lifecycle_state not in {MaterializationGenerationState.PENDING,MaterializationGenerationState.DESIRED} or (
                old.fenced_at_ms is not None or old.period_anchor_ms>=snapshot.feature_cutoff_at_ms
                or old.selection_spec_id!=snapshot.selection_spec_id or old.selection_epoch_id!=snapshot.selection_epoch_id
                or old.selection_control_version!=selection_control_version or superseded_at_ms<old.created_at_ms):
                raise SelectionJobConflict("existing Generation requires coordinated handoff")
            changed = await self._connection.execute(sa.update(strategy_universe_materialization_generations).where(
                strategy_universe_materialization_generations.c.materialization_generation_id==old.materialization_generation_id,
                strategy_universe_materialization_generations.c.projection_version==old.projection_version).values(
                    lifecycle_state="SUPERSEDED",terminal_at_ms=superseded_at_ms,projection_version=old.projection_version+1,
                    lease_owner=None,lease_expires_at_ms=None))
            if changed.rowcount!=1:
                raise SelectionJobConflict("unfenced Generation changed before supersession")
            seq = int(await self._connection.scalar(sa.select(sa.func.max(strategy_universe_materialization_events.c.event_sequence)).where(
                strategy_universe_materialization_events.c.materialization_generation_id==old.materialization_generation_id)) or 0)+1
            await self._connection.execute(sa.insert(strategy_universe_materialization_events).values(
                materialization_event_id=f"materialization-event:{old.materialization_generation_id}:{seq}",
                materialization_generation_id=old.materialization_generation_id,event_sequence=seq,event_type="SUPERSEDED",
                payload={"replacement_snapshot_id":snapshot.selection_snapshot_id,
                    "replacement_generation_id":replacement_generation_id,"reason_code":"NEWER_EFFECTIVE_SELECTION"},
                occurred_at_ms=superseded_at_ms))

    async def retarget_generic_gap_vacuum_with_generation(self,
        generation: GenericMaterializationGeneration, *, entry_vacuum_id: str,
    ) -> GenericMaterializationGeneration:
        """A fresh nonempty Desired inherits the original drained gap fence."""
        generation = GenericMaterializationGeneration.model_validate(generation.model_dump())
        if generation.lifecycle_state is not MaterializationGenerationState.PENDING:
            raise SelectionJobConflict("Gap replacement Generation must start PENDING")
        owner = (await self._connection.execute(sa.select(strategy_entry_controls_current).where(
            strategy_entry_controls_current.c.strategy_group_id==generation.strategy_group_id).with_for_update())).mappings().one_or_none()
        control = await self.get_selection_control(generation.strategy_group_id,for_update=True)
        if owner is None or owner["entry_state"]!="enabled" or control is None or (
            control.selection_mode is not SelectionMode.DYNAMIC_SELECTION
            or control.control_version!=generation.selection_control_version
            or not self._generic_control_allows(control,generation.selection_spec_id,
                generation.selection_epoch_id,generation.period_anchor_ms)):
            raise SelectionJobConflict("Gap replacement Owner or Control changed")
        await self._connection.execute(sa.select(instrument_selection_specs.c.selection_spec_id).where(
            instrument_selection_specs.c.selection_spec_id==generation.selection_spec_id).with_for_update())
        now = await self.read_authority_clock_ms()
        snapshot = await self.get_generic_snapshot(generation.selection_snapshot_id)
        latest = await self._connection.scalar(sa.select(instrument_selection_snapshots.c.selection_snapshot_id).where(
            instrument_selection_snapshots.c.selection_spec_id==generation.selection_spec_id,
            instrument_selection_snapshots.c.selection_epoch_id==generation.selection_epoch_id,
            instrument_selection_snapshots.c.eligibility_not_before_ms<=now,
        ).order_by(instrument_selection_snapshots.c.period_anchor_ms.desc()).limit(1))
        if (latest!=snapshot.selection_snapshot_id or not snapshot.selected_members
            or not snapshot.effective_from_ms<=now<snapshot.expires_at_ms
            or snapshot.committed_at_ms>now or generation.created_at_ms>now):
            raise SelectionJobConflict("Gap replacement requires latest effective nonempty Snapshot")
        vacuum = await self.get_current_entry_vacuum(strategy_group_id=generation.strategy_group_id,
            selection_spec_id=generation.selection_spec_id,for_update=True)
        paused_origin = vacuum is not None and vacuum.state is StrategyEntryVacuumState.OWNER_PAUSED and vacuum.first_blocker=="OWNER_PAUSED"
        if (vacuum is None or vacuum.entry_vacuum_id!=entry_vacuum_id
            or (not paused_origin and (vacuum.state is not StrategyEntryVacuumState.RECOVERY_PENDING or vacuum.first_blocker!="AUTHORITY_GAP"))
            or vacuum.source_generation_id is not None
            or vacuum.drained_at_ms is None or vacuum.resolved_at_ms is not None
            or vacuum.period_anchor_ms>generation.period_anchor_ms
            or await self.entry_vacuum_has_drain_blockers(strategy_group_id=generation.strategy_group_id)
            or await self.get_next_entry_vacuum_ticket(strategy_group_id=generation.strategy_group_id) is not None):
            raise SelectionJobConflict("Gap replacement requires exact drained original Vacuum")
        origin = (await self._connection.execute(sa.select(strategy_entry_vacuum_events.c.payload).where(
            strategy_entry_vacuum_events.c.entry_vacuum_id==vacuum.entry_vacuum_id,
            strategy_entry_vacuum_events.c.event_type=="OPEN").limit(1))).scalar_one_or_none()
        current = await self.get_current_generic_authority(generation.selection_spec_id,for_update=True)
        if paused_origin and (current is None or not await self._connection.scalar(sa.text(
            "SELECT brc_generic_vacuum_owner_resume_matches(:vid,:source,:at)"),
            {"vid":entry_vacuum_id,"source":current.authority.selection_authority_id,"at":now})):
            raise SelectionJobConflict("Generation-free Owner Pause resume proof missing")
        prior = generation.previous_events[0]
        if (origin is None or origin.get("intended_outcome")!=("OWNER_PAUSED" if paused_origin else "PRE_FENCE_CONTINUITY")
            or current is None or (not paused_origin and origin.get("source_selection_authority_id")!=current.authority.selection_authority_id)
            or current.authority.selection_epoch_id!=generation.selection_epoch_id
            or current.authority.selection_control_version!=control.control_version
            or (not paused_origin and current.authority.owner_control_version!=owner["control_version"])
            or current.authority.event_binding.event_spec_id!=prior.event_spec_id
            or current.authority.event_binding.position_side!=prior.position_side
            or current.authority.event_binding.universe_version_id!=prior.universe_version_id
            or current.authority.event_binding.member_set_digest!=prior.member_set_digest
            or current.authority.comparison_universe_id!=prior.comparison_universe_id
            or current.authority.comparison_transition_revision!=prior.comparison_transition_revision):
            raise SelectionJobConflict("Gap replacement previous Active Authority changed")
        await self.add_generic_pending_materialization_generation(generation)
        moved = await self._connection.execute(sa.update(strategy_universe_materialization_generations).where(
            strategy_universe_materialization_generations.c.materialization_generation_id==generation.materialization_generation_id,
            strategy_universe_materialization_generations.c.lifecycle_state=="PENDING",
            strategy_universe_materialization_generations.c.projection_version==1).values(
                lifecycle_state="MATERIALIZING",desired_at_ms=now,fenced_at_ms=now,projection_version=4))
        if moved.rowcount!=1:
            raise SelectionJobConflict("Gap replacement Generation CAS changed")
        for sequence,event_type in ((2,"DESIRED"),(3,"DRAINING_ENTRY"),(4,"MATERIALIZING")):
            await self._connection.execute(sa.insert(strategy_universe_materialization_events).values(
                materialization_event_id=f"materialization-event:{generation.materialization_generation_id}:{sequence}",
                materialization_generation_id=generation.materialization_generation_id,event_sequence=sequence,
                event_type=event_type,payload={"entry_vacuum_id":vacuum.entry_vacuum_id,
                    "recovery_origin":"OWNER_PAUSE_NO_GENERATION" if paused_origin else "AUTHORITY_GAP","original_fenced_at_ms":vacuum.fenced_at_ms,
                    "original_drained_at_ms":vacuum.drained_at_ms},occurred_at_ms=now))
        next_version = vacuum.projection_version+1
        await self._connection.execute(sa.insert(strategy_entry_vacuum_events).values(
            entry_vacuum_event_id=f"vacuum-event:{vacuum.entry_vacuum_id}:{next_version}",
            entry_vacuum_id=vacuum.entry_vacuum_id,event_sequence=next_version,event_type="SUPERSEDED",
            payload={"recovery_origin":"OWNER_PAUSE_NO_GENERATION" if paused_origin else "AUTHORITY_GAP","previous_generation_id":None,
                "source_selection_authority_id":current.authority.selection_authority_id,
                "replacement_generation_id":generation.materialization_generation_id},occurred_at_ms=now))
        changed = await self._connection.execute(sa.update(strategy_entry_vacuums_current).where(
            strategy_entry_vacuums_current.c.entry_vacuum_id==vacuum.entry_vacuum_id,
            strategy_entry_vacuums_current.c.state==vacuum.state.value,
            strategy_entry_vacuums_current.c.projection_version==vacuum.projection_version).values(
                state="RECONFIGURING",first_blocker="AUTHORITY_GAP",source_generation_id=generation.materialization_generation_id,
                period_anchor_ms=generation.period_anchor_ms,projection_version=next_version))
        if changed.rowcount!=1:
            raise SelectionJobConflict("Gap replacement Vacuum CAS changed")
        return GenericMaterializationGeneration.model_validate({**generation.model_dump(),
            "lifecycle_state":"MATERIALIZING","desired_at_ms":now,"fenced_at_ms":now,
            "projection_version":4})

    async def retarget_interrupted_generic_vacuum_with_generation(self,
        generation: GenericMaterializationGeneration, *, entry_vacuum_id: str,
    ) -> GenericMaterializationGeneration:
        """A newer effective Desired takes over the already-drained fence.

        Failed Generations remain terminal; unfinished targets are abandoned
        and their Generation superseded. The original Vacuum timestamps
        remain immutable evidence; the replacement gets its own timeout clock.
        No Authority is granted by this transaction.
        """
        generation = GenericMaterializationGeneration.model_validate(generation.model_dump())
        if generation.lifecycle_state is not MaterializationGenerationState.PENDING:
            raise SelectionJobConflict("Generic replacement must start PENDING")
        owner = (await self._connection.execute(sa.select(strategy_entry_controls_current).where(
            strategy_entry_controls_current.c.strategy_group_id==generation.strategy_group_id).with_for_update())).mappings().one_or_none()
        control = await self.get_selection_control(generation.strategy_group_id,for_update=True)
        if owner is None or owner["entry_state"]!="enabled" or control is None or (
            control.selection_mode is not SelectionMode.DYNAMIC_SELECTION or control.control_version!=generation.selection_control_version
            or not self._generic_control_allows(control,generation.selection_spec_id,generation.selection_epoch_id,generation.period_anchor_ms)):
            raise SelectionJobConflict("Generic replacement Owner or Control changed")
        await self._connection.execute(sa.select(instrument_selection_specs.c.selection_spec_id).where(
            instrument_selection_specs.c.selection_spec_id==generation.selection_spec_id).with_for_update())
        now = await self.read_authority_clock_ms()
        snapshot = await self.get_generic_snapshot(generation.selection_snapshot_id)
        latest = await self._connection.scalar(sa.select(instrument_selection_snapshots.c.selection_snapshot_id).where(
            instrument_selection_snapshots.c.selection_spec_id==generation.selection_spec_id,
            instrument_selection_snapshots.c.selection_epoch_id==generation.selection_epoch_id,
            instrument_selection_snapshots.c.eligibility_not_before_ms<=now,
        ).order_by(instrument_selection_snapshots.c.period_anchor_ms.desc()).limit(1))
        if latest!=snapshot.selection_snapshot_id or not snapshot.effective_from_ms<=now<snapshot.expires_at_ms or (
            snapshot.committed_at_ms>now or generation.created_at_ms>now):
            raise SelectionJobConflict("Generic replacement requires latest effective Snapshot")
        vacuum = await self.get_current_entry_vacuum(strategy_group_id=generation.strategy_group_id,
            selection_spec_id=generation.selection_spec_id,for_update=True)
        if vacuum is None or vacuum.entry_vacuum_id!=entry_vacuum_id or vacuum.state not in {StrategyEntryVacuumState.RECONFIGURING,StrategyEntryVacuumState.OWNER_PAUSED} or (
            vacuum.source_generation_id is None or vacuum.drained_at_ms is None or vacuum.resolved_at_ms is not None
            or vacuum.period_anchor_ms>=generation.period_anchor_ms):
            raise SelectionJobConflict("Generic replacement requires exact prior drained Vacuum")
        old = await self.get_generic_materialization_generation(vacuum.source_generation_id,for_update=True)
        if old is None or old.lifecycle_state not in {
            MaterializationGenerationState.FAILED_CLOSED, MaterializationGenerationState.MATERIALIZING,
            MaterializationGenerationState.STAGED, MaterializationGenerationState.ABANDONED,
        } or (
            old.fenced_at_ms is None or not vacuum.fenced_at_ms<=old.fenced_at_ms<=now
            or old.period_anchor_ms!=vacuum.period_anchor_ms
            or old.selection_spec_id!=generation.selection_spec_id
            or old.selection_epoch_id!=generation.selection_epoch_id or old.selection_control_version!=generation.selection_control_version
            or old.previous_events!=generation.previous_events):
            raise SelectionJobConflict("Generic replacement previous Generation changed")
        if vacuum.state is StrategyEntryVacuumState.OWNER_PAUSED or old.lifecycle_state is MaterializationGenerationState.ABANDONED:
            source = await self.get_current_generic_authority(generation.selection_spec_id,for_update=True)
            if vacuum.state is not StrategyEntryVacuumState.OWNER_PAUSED or old.lifecycle_state is not MaterializationGenerationState.ABANDONED or (
                source is None or not await self._connection.scalar(sa.text(
                    "SELECT brc_generic_vacuum_owner_resume_matches(:vid,:source,:at)"),
                    {"vid":entry_vacuum_id,"source":source.authority.selection_authority_id,"at":now})):
                raise SelectionJobConflict("Generic replacement Owner resume provenance missing")
        if await self.entry_vacuum_has_drain_blockers(strategy_group_id=generation.strategy_group_id) or (
            await self.get_next_entry_vacuum_ticket(strategy_group_id=generation.strategy_group_id)) is not None:
            raise SelectionJobConflict("Generic replacement ENTRY drain is unresolved")
        from src.trading_kernel.infrastructure.pg_universe_repository import (
            PostgresStrategyUniverseRepository,
        )
        universes = PostgresStrategyUniverseRepository(self._connection)
        targets = await universes.get_generation_universe_targets(
            old.materialization_generation_id,for_update=True)
        if len(targets)>1 or any(target.lifecycle_state.value not in {"abandoned","warming","staged"} for target in targets):
            raise SelectionJobConflict("Generic replacement old target identity changed")
        if old.lifecycle_state in {MaterializationGenerationState.FAILED_CLOSED,MaterializationGenerationState.ABANDONED} and any(
            target.lifecycle_state.value!="abandoned" for target in targets):
            raise SelectionJobConflict("Generic failed replacement targets were not abandoned")
        from src.trading_kernel.application.abandon_strategy_universe import (
            AbandonStrategyUniverseRequest,
        )
        for target in targets:
            if target.lifecycle_state.value!="abandoned":
                await universes.abandon(AbandonStrategyUniverseRequest(
                    universe_version_id=target.universe_version_id,
                    reason_code="superseded_by_newer_selection",attempted_at_ms=now))
        if old.lifecycle_state not in {MaterializationGenerationState.FAILED_CLOSED,MaterializationGenerationState.ABANDONED}:
            superseded = await self._connection.execute(sa.update(strategy_universe_materialization_generations).where(
                strategy_universe_materialization_generations.c.materialization_generation_id==old.materialization_generation_id,
                strategy_universe_materialization_generations.c.projection_version==old.projection_version).values(
                    lifecycle_state="SUPERSEDED",terminal_at_ms=now,projection_version=old.projection_version+1,
                    lease_owner=None,lease_expires_at_ms=None))
            if superseded.rowcount!=1:
                raise SelectionJobConflict("Generic replacement previous Generation CAS changed")
        await self.add_generic_pending_materialization_generation(generation)
        moved = await self._connection.execute(sa.update(strategy_universe_materialization_generations).where(
            strategy_universe_materialization_generations.c.materialization_generation_id==generation.materialization_generation_id,
            strategy_universe_materialization_generations.c.lifecycle_state=="PENDING",
            strategy_universe_materialization_generations.c.projection_version==1).values(
                lifecycle_state="MATERIALIZING",desired_at_ms=now,fenced_at_ms=now,projection_version=4))
        if moved.rowcount!=1:
            raise SelectionJobConflict("Generic replacement Generation CAS changed")
        for sequence,event_type in ((2,"DESIRED"),(3,"DRAINING_ENTRY"),(4,"MATERIALIZING")):
            await self._connection.execute(sa.insert(strategy_universe_materialization_events).values(
                materialization_event_id=f"materialization-event:{generation.materialization_generation_id}:{sequence}",
                materialization_generation_id=generation.materialization_generation_id,event_sequence=sequence,event_type=event_type,
                payload={"entry_vacuum_id":vacuum.entry_vacuum_id,"supersedes_generation_id":old.materialization_generation_id,
                    "vacuum_original_fenced_at_ms":vacuum.fenced_at_ms,"vacuum_original_drained_at_ms":vacuum.drained_at_ms},
                occurred_at_ms=now))
        old_sequence = int(await self._connection.scalar(sa.select(sa.func.max(strategy_universe_materialization_events.c.event_sequence)).where(
            strategy_universe_materialization_events.c.materialization_generation_id==old.materialization_generation_id)) or 0)+1
        await self._connection.execute(sa.insert(strategy_universe_materialization_events).values(
            materialization_event_id=f"materialization-event:{old.materialization_generation_id}:{old_sequence}",
            materialization_generation_id=old.materialization_generation_id,event_sequence=old_sequence,
            event_type="SUPERSEDED_BY_NEWER_SELECTION",payload={
                "replacement_generation_id":generation.materialization_generation_id,
                "entry_vacuum_id":vacuum.entry_vacuum_id,"previous_lifecycle_state":old.lifecycle_state.value,
                "original_fenced_at_ms":vacuum.fenced_at_ms,"original_drained_at_ms":vacuum.drained_at_ms},
            occurred_at_ms=now))
        for offset,state,event_type,source_id in (
            (1,"SUPERSEDED","SUPERSEDED",old.materialization_generation_id),
            (2,"RECONFIGURING","RECONFIGURING",generation.materialization_generation_id),
        ):
            changed = await self._connection.execute(sa.update(strategy_entry_vacuums_current).where(
                strategy_entry_vacuums_current.c.entry_vacuum_id==vacuum.entry_vacuum_id,
                strategy_entry_vacuums_current.c.projection_version==vacuum.projection_version+offset-1).values(
                    state=state,source_generation_id=source_id,period_anchor_ms=generation.period_anchor_ms,
                    first_blocker="SUPERSEDED_BY_NEWER_SELECTION" if offset==1 else "LATEST_VALID_SELECTION",
                    projection_version=vacuum.projection_version+offset))
            if changed.rowcount!=1:
                raise SelectionJobConflict("Generic replacement Vacuum CAS changed")
            await self._connection.execute(sa.insert(strategy_entry_vacuum_events).values(
                entry_vacuum_event_id=f"vacuum-event:{vacuum.entry_vacuum_id}:{vacuum.projection_version+offset}",
                entry_vacuum_id=vacuum.entry_vacuum_id,event_sequence=vacuum.projection_version+offset,event_type=event_type,
                payload={"previous_generation_id":old.materialization_generation_id,
                    "replacement_generation_id":generation.materialization_generation_id,
                    "recovery_origin":("MATERIALIZATION_FAILURE" if old.lifecycle_state is MaterializationGenerationState.FAILED_CLOSED
                        else "OWNER_PAUSE" if old.lifecycle_state is MaterializationGenerationState.ABANDONED
                        else "UNFINISHED_MATERIALIZATION")},occurred_at_ms=now))
        return GenericMaterializationGeneration.model_validate({**generation.model_dump(),"lifecycle_state":"MATERIALIZING",
            "desired_at_ms":now,"fenced_at_ms":now,"projection_version":4})

    async def claim_generic_materialization_generation(
        self, materialization_generation_id: str, *, worker_id: str, now_ms: int, lease_duration_ms: int,
    ) -> GenericMaterializationLeaseClaim:
        initial = await self.get_generic_materialization_generation(materialization_generation_id)
        if initial is None:
            return GenericMaterializationLeaseClaim(status=MaterializationGenerationClaimStatus.NO_GENERATION)
        control = await self.get_selection_control(initial.strategy_group_id, for_update=True)
        generation = await self.get_generic_materialization_generation(materialization_generation_id, for_update=True)
        if generation is None or generation.lifecycle_state not in {
            MaterializationGenerationState.PENDING,MaterializationGenerationState.DESIRED,MaterializationGenerationState.DRAINING_ENTRY,
            MaterializationGenerationState.MATERIALIZING,MaterializationGenerationState.STAGED,
        }:
            return GenericMaterializationLeaseClaim(status=MaterializationGenerationClaimStatus.NO_GENERATION)
        spec = await self.get_generic_spec(generation.selection_spec_id)
        if (not self._generic_control_allows(control,generation.selection_spec_id,generation.selection_epoch_id,generation.period_anchor_ms)
            or control is None or control.control_version!=generation.selection_control_version):
            raise SelectionJobConflict("Generic Generation control/epoch changed")
        cleanup_only = generation.fenced_at_ms is not None and generation.lifecycle_state in {
            MaterializationGenerationState.DRAINING_ENTRY,MaterializationGenerationState.MATERIALIZING,MaterializationGenerationState.STAGED}
        if now_ms < generation.created_at_ms or (now_ms>=generation.period_anchor_ms+(1+spec.cadence_hours)*3600000 and not cleanup_only):
            raise SelectionJobConflict("Generic Generation is outside eligible source period")
        row = (await self._connection.execute(sa.select(strategy_universe_materialization_generations).where(
            strategy_universe_materialization_generations.c.materialization_generation_id==materialization_generation_id))).mappings().one()
        acquired = await self._acquire_materialization_lease(row,worker_id=worker_id,now_ms=now_ms,
            lease_duration_ms=lease_duration_ms,strict_owner=True)
        refreshed = await self.get_generic_materialization_generation(materialization_generation_id)
        return GenericMaterializationLeaseClaim(status=MaterializationGenerationClaimStatus.CLAIMED if acquired else MaterializationGenerationClaimStatus.LEASE_HELD,
            generation=refreshed)

    async def fail_generic_materialization_generation(self, materialization_generation_id: str, *,
        expected_projection_version: int, worker_id: str, lease_epoch: int, reason_code: str,
    ) -> GenericMaterializationGeneration:
        """Release failed targets, preserving the same unresolved recovery Vacuum."""
        from src.trading_kernel.application.abandon_strategy_universe import (
            AbandonStrategyUniverseRequest,
        )
        from src.trading_kernel.infrastructure.pg_universe_repository import (
            PostgresStrategyUniverseRepository,
        )

        if reason_code not in {"MATERIALIZATION_TIMEOUT","MATERIALIZATION_PERIOD_EXPIRED",
            "CERTIFICATION_OWNER_ACTION_REQUIRED","CERTIFICATION_NOT_ELIGIBLE"}:
            raise ValueError("Generic failure requires a classified terminal cause")
        initial = await self.get_generic_materialization_generation(materialization_generation_id)
        if initial is None:
            raise SelectionJobConflict("Generic failure Generation missing")
        owner = (await self._connection.execute(sa.select(strategy_entry_controls_current).where(
            strategy_entry_controls_current.c.strategy_group_id==initial.strategy_group_id).with_for_update())).mappings().one_or_none()
        control = await self.get_selection_control(initial.strategy_group_id,for_update=True)
        generation = await self.get_generic_materialization_generation(materialization_generation_id,for_update=True)
        now = await self.read_authority_clock_ms()
        if owner is None or owner["entry_state"]!="enabled" or generation is None or control is None or (
            control.control_version!=generation.selection_control_version
            or not self._generic_control_allows(control,generation.selection_spec_id,generation.selection_epoch_id,generation.period_anchor_ms)):
            raise SelectionJobConflict("Generic failure Owner or Selection control changed")
        if generation.lifecycle_state not in {MaterializationGenerationState.MATERIALIZING,MaterializationGenerationState.STAGED} or (
            generation.projection_version!=expected_projection_version or generation.lease_owner!=worker_id
            or generation.lease_epoch!=lease_epoch or generation.lease_expires_at_ms is None or now>=generation.lease_expires_at_ms
            or generation.fenced_at_ms is None or now<generation.fenced_at_ms):
            raise SelectionJobConflict("Generic failure Generation lease/state changed")
        spec = await self.get_generic_spec(generation.selection_spec_id)
        deadline = generation.fenced_at_ms+spec.materialization_timeout_ms
        expiry = generation.period_anchor_ms+(1+spec.cadence_hours)*3600000
        next_future_close = (now//3600000+1)*3600000
        if reason_code=="MATERIALIZATION_TIMEOUT" and now<deadline or reason_code=="MATERIALIZATION_PERIOD_EXPIRED" and now<expiry:
            raise SelectionJobConflict("Generic failure deadline has not elapsed")
        vacuum = await self.get_current_entry_vacuum(strategy_group_id=generation.strategy_group_id,
            selection_spec_id=generation.selection_spec_id,for_update=True)
        if vacuum is None or vacuum.source_generation_id!=materialization_generation_id or vacuum.state is not StrategyEntryVacuumState.RECONFIGURING or (
            vacuum.fenced_at_ms>generation.fenced_at_ms or await self.entry_vacuum_has_drain_blockers(strategy_group_id=generation.strategy_group_id)):
            raise SelectionJobConflict("Generic failure requires exact drained Vacuum")
        universes = PostgresStrategyUniverseRepository(self._connection)
        targets = await universes.get_generation_universe_targets(materialization_generation_id,for_update=True)
        if len(targets)>1:
            raise SelectionJobConflict("Generic failure target set differs")
        for target in targets:
            if target.event_spec_id!=spec.event_spec_id:
                raise SelectionJobConflict("Generic failure target Event differs")
            await universes.abandon(AbandonStrategyUniverseRequest(universe_version_id=target.universe_version_id,
                reason_code=reason_code.lower(),attempted_at_ms=now))
        failed = GenericMaterializationGeneration.model_validate({**generation.model_dump(),
            "lifecycle_state":"FAILED_CLOSED","terminal_at_ms":now,"projection_version":generation.projection_version+1,
            "lease_owner":None,"lease_expires_at_ms":None})
        updated = await self._connection.execute(sa.update(strategy_universe_materialization_generations).where(
            strategy_universe_materialization_generations.c.materialization_generation_id==materialization_generation_id,
            strategy_universe_materialization_generations.c.projection_version==expected_projection_version,
            strategy_universe_materialization_generations.c.lease_epoch==lease_epoch).values(
                lifecycle_state="FAILED_CLOSED",terminal_at_ms=now,projection_version=failed.projection_version,lease_owner=None,lease_expires_at_ms=None))
        if updated.rowcount!=1:
            raise SelectionJobConflict("Generic failure Generation CAS changed")
        sequence = int(await self._connection.scalar(sa.select(sa.func.max(strategy_universe_materialization_events.c.event_sequence)).where(
            strategy_universe_materialization_events.c.materialization_generation_id==materialization_generation_id)) or 0)+1
        await self._connection.execute(sa.insert(strategy_universe_materialization_events).values(
            materialization_event_id=f"materialization-event:{materialization_generation_id}:{sequence}",
            materialization_generation_id=materialization_generation_id,event_sequence=sequence,event_type="FAILED_CLOSED",
            payload={"reason_code":reason_code,"entry_vacuum_id":vacuum.entry_vacuum_id,
                "materialization_deadline_ms":deadline,"period_expires_at_ms":expiry,
                "next_future_close_time_ms":next_future_close,
                "no_eligible_close_before_expiry":next_future_close>=expiry},occurred_at_ms=now))
        updated = await self._connection.execute(sa.update(strategy_entry_vacuums_current).where(
            strategy_entry_vacuums_current.c.entry_vacuum_id==vacuum.entry_vacuum_id,
            strategy_entry_vacuums_current.c.projection_version==vacuum.projection_version).values(
                first_blocker=reason_code,projection_version=vacuum.projection_version+1))
        if updated.rowcount!=1:
            raise SelectionJobConflict("Generic failure Vacuum CAS changed")
        await self._connection.execute(sa.insert(strategy_entry_vacuum_events).values(
            entry_vacuum_event_id=f"vacuum-event:{vacuum.entry_vacuum_id}:{vacuum.projection_version+1}",
            entry_vacuum_id=vacuum.entry_vacuum_id,event_sequence=vacuum.projection_version+1,event_type="RECOVERY_REQUIRED",
            payload={"reason_code":reason_code,"source_generation_id":materialization_generation_id},occurred_at_ms=now))
        return failed

    async def release_generic_materialization_generation_lease(
        self, materialization_generation_id: str, *, worker_id: str, lease_epoch: int,
    ) -> bool:
        if not worker_id.strip() or lease_epoch<=0:
            raise ValueError("Generic lease release requires an exact fencing token")
        changed = await self._connection.execute(sa.update(strategy_universe_materialization_generations).where(
            strategy_universe_materialization_generations.c.materialization_generation_id==materialization_generation_id,
            strategy_universe_materialization_generations.c.selection_epoch_id!="sor-v0",
            strategy_universe_materialization_generations.c.lease_owner==worker_id,
            strategy_universe_materialization_generations.c.lease_epoch==lease_epoch,
        ).values(lease_owner=None,lease_expires_at_ms=None))
        return changed.rowcount==1

    async def get_materialization_generation_for_snapshot(
        self,
        selection_snapshot_id: str,
        *,
        for_update: bool = False,
    ) -> MaterializationGeneration | None:
        statement = sa.select(*materialization_generation_projection_columns()).where(
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
                sa.select(*materialization_generation_projection_columns())
                .where(
                    strategy_universe_materialization_generations.c.strategy_group_id
                    == strategy_group_id,
                    strategy_universe_materialization_generations.c.selection_spec_id
                    == selection_spec_id,
                    strategy_universe_materialization_generations.c.period_anchor_ms
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
        statement = sa.select(*materialization_generation_projection_columns()).where(
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
            sa.select(*materialization_generation_projection_columns())
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
                strategy_universe_materialization_generations.c.period_anchor_ms.desc(),
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
                sa.select(*materialization_generation_projection_columns())
                .where(
                    strategy_universe_materialization_generations.c.selection_spec_id
                    == selection_spec_id,
                    strategy_universe_materialization_generations.c.period_anchor_ms
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
        if not await self._acquire_materialization_lease(row,worker_id=normalized_worker_id,now_ms=now_ms,lease_duration_ms=lease_duration_ms,strict_owner=False):
            return MaterializationGenerationLeaseClaim(
                status=MaterializationGenerationClaimStatus.LEASE_HELD,
                generation=generation,
                lease_owner=str(existing_owner),
                lease_expires_at_ms=int(existing_expiry),
            )
        lease_expires_at_ms = now_ms + lease_duration_ms
        return MaterializationGenerationLeaseClaim(
            status=MaterializationGenerationClaimStatus.CLAIMED,
            generation=generation,
            lease_owner=normalized_worker_id,
            lease_expires_at_ms=lease_expires_at_ms,
        )

    async def _acquire_materialization_lease(self, row: RowMapping, *, worker_id: str, now_ms: int,
                                           lease_duration_ms: int, strict_owner: bool) -> bool:
        if not worker_id.strip() or now_ms<=0 or lease_duration_ms<=0:
            raise ValueError("Materialization lease identity/timing is invalid")
        if (row["lease_owner"] is not None and row["lease_expires_at_ms"] is not None and row["lease_expires_at_ms"]>now_ms
            and (strict_owner or row["lease_owner"]!=worker_id)):
            return False
        updated = await self._connection.execute(
            sa.update(strategy_universe_materialization_generations)
            .where(
                strategy_universe_materialization_generations.c.materialization_generation_id
                == row["materialization_generation_id"],
                strategy_universe_materialization_generations.c.lifecycle_state
                == row["lifecycle_state"],
                strategy_universe_materialization_generations.c.projection_version
                == row["projection_version"],
                strategy_universe_materialization_generations.c.lease_epoch==row["lease_epoch"],
            )
            .values(
                lease_owner=worker_id,
                lease_expires_at_ms=now_ms+lease_duration_ms,
                lease_epoch=row["lease_epoch"]+1 if strict_owner else row["lease_epoch"],
            )
        )
        if updated.rowcount != 1:
            raise SelectionJobConflict("Materialization Generation lease changed")
        return True

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
                strategy_universe_materialization_generations.c.selection_epoch_id=="sor-v0",
            )
            .values(lease_owner=None, lease_expires_at_ms=None)
        )

    async def mark_generic_materialization_generation_desired(
        self, materialization_generation_id: str, *, worker_id: str, lease_epoch: int,
        expected_projection_version: int, desired_at_ms: int,
    ) -> GenericMaterializationGeneration:
        initial = await self.get_generic_materialization_generation(materialization_generation_id)
        if initial is None:
            raise SelectionJobConflict("Generic Generation does not exist")
        control = await self.get_selection_control(initial.strategy_group_id, for_update=True)
        current = await self.get_generic_materialization_generation(materialization_generation_id, for_update=True)
        if current is None or control is None or control.control_version != current.selection_control_version or not self._generic_control_allows(
            control,current.selection_spec_id,current.selection_epoch_id,current.period_anchor_ms):
            raise SelectionJobConflict("Generic Generation control/epoch changed")
        spec = await self.get_generic_spec(current.selection_spec_id)
        if not current.created_at_ms <= desired_at_ms < current.period_anchor_ms+(1+spec.cadence_hours)*3600000:
            raise SelectionJobConflict("Generic Generation source period expired")
        if not worker_id.strip() or lease_epoch <= 0 or current.lease_owner != worker_id or current.lease_epoch != lease_epoch or (
            current.lease_expires_at_ms is None or current.lease_expires_at_ms <= desired_at_ms):
            raise SelectionJobConflict("Generic Generation lease changed")
        if current.lifecycle_state is MaterializationGenerationState.DESIRED and current.projection_version in {
            expected_projection_version, expected_projection_version+1}:
            return current
        if current.lifecycle_state is not MaterializationGenerationState.PENDING or current.projection_version != expected_projection_version:
            raise SelectionJobConflict("Generic Generation state/version changed")
        desired = GenericMaterializationGeneration.model_validate({**current.model_dump(),
            "lifecycle_state":"DESIRED","desired_at_ms":desired_at_ms,"projection_version":expected_projection_version+1})
        updated = await self._connection.execute(sa.update(strategy_universe_materialization_generations).where(
            strategy_universe_materialization_generations.c.materialization_generation_id == materialization_generation_id,
            strategy_universe_materialization_generations.c.projection_version == expected_projection_version,
            strategy_universe_materialization_generations.c.lifecycle_state == "PENDING",
        ).values(lifecycle_state="DESIRED",desired_at_ms=desired_at_ms,projection_version=desired.projection_version))
        if updated.rowcount != 1:
            raise SelectionJobConflict("Generic Generation version changed")
        await self._connection.execute(sa.insert(strategy_universe_materialization_events).values(
            materialization_event_id="materialization-event:"+canonical_digest({"generation":materialization_generation_id,"sequence":2})[7:],
            materialization_generation_id=materialization_generation_id,event_sequence=2,event_type="DESIRED",
            payload={"projection_version":desired.projection_version,"lease_epoch":lease_epoch},occurred_at_ms=desired_at_ms))
        return desired

    async def mark_materialization_generation_desired(
        self,
        materialization_generation_id: str,
        *,
        expected_projection_version: int,
        desired_at_ms: int,
    ) -> MaterializationGeneration:
        row = (
            await self._connection.execute(
                sa.select(*materialization_generation_projection_columns())
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
                sa.select(*materialization_generation_projection_columns())
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

    async def supersede_owner_paused_vacuum_with_generation(
        self,
        *,
        previous_generation: MaterializationGeneration,
        replacement_generation: MaterializationGeneration,
        replacement_targets: tuple[MaterializationTarget, ...],
        vacuum: StrategyEntryVacuum,
        superseded_at_ms: int,
    ) -> MaterializationGeneration:
        """Retarget one drained Owner-Pause fence to the next authorized Session."""

        if (
            previous_generation.lifecycle_state
            is not MaterializationGenerationState.ABANDONED
            or replacement_generation.lifecycle_state
            is not MaterializationGenerationState.PENDING
            or replacement_generation.session_start_ms is None
            or previous_generation.session_start_ms is None
            or replacement_generation.session_start_ms
            <= previous_generation.session_start_ms
            or previous_generation.previous_long_universe_version_id
            != replacement_generation.previous_long_universe_version_id
            or previous_generation.previous_short_universe_version_id
            != replacement_generation.previous_short_universe_version_id
            or vacuum.state is not StrategyEntryVacuumState.OWNER_PAUSED
            or vacuum.source_generation_id
            != previous_generation.materialization_generation_id
            or vacuum.drained_at_ms is None
            or vacuum.resolved_at_ms is not None
            or vacuum.first_blocker != "OWNER_PAUSED"
        ):
            raise ValueError(
                "Owner-Pause supersession requires an exact newer Selection"
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
            raise SelectionJobConflict("Owner-Pause supersession authority changed")
        recovered_event_exists = bool(
            await self._connection.scalar(
                sa.select(
                    sa.exists().where(
                        strategy_universe_materialization_events.c.materialization_generation_id
                        == previous_generation.materialization_generation_id,
                        strategy_universe_materialization_events.c.event_sequence
                        == previous_generation.projection_version,
                        strategy_universe_materialization_events.c.event_type
                        == "EXPIRED_ACTIVATION_RECOVERED",
                    )
                )
            )
        )
        if not recovered_event_exists:
            raise SelectionJobConflict(
                "Owner-Pause supersession requires exact expired recovery"
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
                == "ABANDONED",
                strategy_universe_materialization_generations.c.projection_version
                == previous_generation.projection_version,
            )
            .values(projection_version=previous_next_version)
        )
        if previous_update.rowcount != 1:
            raise SelectionJobConflict(
                "abandoned Generation changed during Owner-Pause supersession"
            )
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
                event_type="OWNER_PAUSE_SUPERSEDED",
                payload={
                    "replacement_generation_id": (
                        replacement_generation.materialization_generation_id
                    ),
                    "replacement_session_start_ms": (
                        replacement_generation.session_start_ms
                    ),
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
                strategy_universe_materialization_generations.c.projection_version == 1,
            )
            .values(
                lifecycle_state="MATERIALIZING",
                desired_at_ms=superseded_at_ms,
                fenced_at_ms=vacuum.fenced_at_ms,
                projection_version=4,
            )
        )
        if replacement_update.rowcount != 1:
            raise SelectionJobConflict(
                "replacement Generation changed during Owner-Pause handoff"
            )
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
                        "supersedes_owner_paused_generation_id": (
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
                strategy_entry_vacuums_current.c.state == "OWNER_PAUSED",
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
            raise SelectionJobConflict(
                "Owner-Pause Vacuum changed during supersession"
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
                    "replacement_generation_id": (
                        replacement_generation.materialization_generation_id
                    ),
                    "reason_code": "OWNER_PAUSE_SUPERSEDED_BY_NEW_SELECTION",
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
            raise SelectionJobConflict("Owner-Pause Vacuum retarget failed")
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
                    ),
                    "source_kind": "OWNER_PAUSE_SUPERSESSION",
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
        recovered_owner_pause = (
            previous_generation.lifecycle_state
            is MaterializationGenerationState.ABANDONED
            and vacuum.state is StrategyEntryVacuumState.OWNER_PAUSED
            and vacuum.first_blocker == "OWNER_PAUSED"
        )
        if (
            (
                not recovered_owner_pause
                and previous_generation.lifecycle_state
                not in {
                    MaterializationGenerationState.MATERIALIZING,
                    MaterializationGenerationState.STAGED,
                }
            )
            or snapshot.selected_count != 0
            or snapshot.session_start_ms is None
            or previous_generation.session_start_ms is None
            or snapshot.session_start_ms <= previous_generation.session_start_ms
            or (
                not recovered_owner_pause
                and vacuum.state is not StrategyEntryVacuumState.RECONFIGURING
            )
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
        if recovered_owner_pause:
            recovered_event = await self._connection.scalar(
                sa.select(
                    sa.exists().where(
                        strategy_universe_materialization_events.c.materialization_generation_id
                        == previous_generation.materialization_generation_id,
                        strategy_universe_materialization_events.c.event_sequence
                        == previous_generation.projection_version,
                        strategy_universe_materialization_events.c.event_type
                        == "EXPIRED_ACTIVATION_RECOVERED",
                    )
                )
            )
            if not recovered_event:
                raise SelectionJobConflict(
                    "Owner-Pause VALID_EMPTY requires exact expired recovery"
                )
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
                lifecycle_state="ABANDONED" if recovered_owner_pause else "SUPERSEDED",
                terminal_at_ms=(
                    strategy_universe_materialization_generations.c.terminal_at_ms
                    if recovered_owner_pause
                    else superseded_at_ms
                ),
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
                event_type="OWNER_PAUSE_SUPERSEDED"
                if recovered_owner_pause
                else "SUPERSEDED",
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
                strategy_entry_vacuums_current.c.state == vacuum.state.value,
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
            raise SelectionJobConflict("Vacuum changed during VALID_EMPTY supersession")
        await self._connection.execute(
            sa.insert(strategy_entry_vacuum_events).values(
                entry_vacuum_event_id=(
                    f"vacuum-event:{vacuum.entry_vacuum_id}:{superseded_vacuum_version}"
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
                    f"vacuum-event:{vacuum.entry_vacuum_id}:{resolved_vacuum_version}"
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
        generation: MaterializationGeneration | GenericMaterializationGeneration | GenericStaticMaterializationGeneration,
        vacuum: StrategyEntryVacuum,
        paused_at_ms: int,
    ) -> MaterializationGeneration | GenericMaterializationGeneration | GenericStaticMaterializationGeneration:
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
        locked_generation: MaterializationGeneration | GenericMaterializationGeneration | GenericStaticMaterializationGeneration | None
        if isinstance(generation,(GenericMaterializationGeneration,GenericStaticMaterializationGeneration)):
            owner = (await self._connection.execute(sa.select(strategy_entry_controls_current).where(
                strategy_entry_controls_current.c.strategy_group_id==generation.strategy_group_id).with_for_update())).mappings().one_or_none()
            now = await self.read_authority_clock_ms()
            if owner is None or owner["entry_state"]!="paused" or not generation.created_at_ms<=paused_at_ms<=now:
                raise SelectionJobConflict("Generic abandonment requires current Owner Pause")
            if isinstance(generation,GenericStaticMaterializationGeneration):
                locked_generation = await self.get_generic_static_materialization_generation(generation.materialization_generation_id,for_update=True)
            else:
                locked_generation = await self.get_generic_materialization_generation(generation.materialization_generation_id,for_update=True)
            unfinished_target = await self._connection.scalar(sa.select(strategy_universe_versions.c.universe_version_id).where(
                strategy_universe_versions.c.materialization_generation_id==generation.materialization_generation_id,
                strategy_universe_versions.c.lifecycle_state!="abandoned").limit(1))
            if unfinished_target is not None:
                raise SelectionJobConflict("Generic Owner Pause requires abandoned targets")
        else:
            locked_generation = await self.get_materialization_generation(
                generation.materialization_generation_id,for_update=True)
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
        abandoned = type(generation).model_validate(
            generation.model_copy(
                update={
                    "lifecycle_state": MaterializationGenerationState.ABANDONED,
                    "projection_version": generation.projection_version + 1,
                    **({"terminal_at_ms":paused_at_ms,"lease_owner":None,"lease_expires_at_ms":None}
                        if isinstance(generation,(GenericMaterializationGeneration,GenericStaticMaterializationGeneration)) else {}),
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

    async def get_entry_vacuum_by_id(
        self, entry_vacuum_id: str, *, for_update: bool = False,
    ) -> StrategyEntryVacuum | None:
        statement = sa.select(strategy_entry_vacuums_current).where(
            strategy_entry_vacuums_current.c.entry_vacuum_id == entry_vacuum_id,
        )
        if for_update:
            statement = statement.with_for_update(of=strategy_entry_vacuums_current)
        row = (await self._connection.execute(statement)).mappings().one_or_none()
        return None if row is None else _entry_vacuum_from_row(row)

    async def list_draining_entry_vacuums(
        self, *, limit: int,
    ) -> tuple[StrategyEntryVacuum, ...]:
        """Read the bounded current draining set across installed strategies."""

        if not 1 <= limit <= 8:
            raise ValueError("draining Vacuum read limit must be 1 through 8")
        rows = (
            await self._connection.execute(
                sa.select(strategy_entry_vacuums_current)
                .where(
                    sa.text("brc_strategy_entry_vacuums_current.state='DRAINING_ENTRY'"),
                    sa.exists(
                        sa.select(1).select_from(
                            trade_tickets.join(
                                trade_aggregates,
                                trade_aggregates.c.ticket_id == trade_tickets.c.ticket_id,
                            )
                        ).where(
                            trade_tickets.c.strategy_group_id
                            == strategy_entry_vacuums_current.c.strategy_group_id,
                            trade_tickets.c.terminal_at_ms.is_(None),
                            trade_aggregates.c.status.in_(_ENTRY_VACUUM_DRAIN_BLOCKING_STATUSES),
                        )
                    ),
                )
                .order_by(
                    strategy_entry_vacuums_current.c.fenced_at_ms,
                    strategy_entry_vacuums_current.c.entry_vacuum_id,
                )
                .limit(limit + 1)
            )
        ).mappings().all()
        if len(rows) > limit:
            raise RuntimeError("draining Vacuum scope count exceeds bounded strategy set")
        return tuple(_entry_vacuum_from_row(row) for row in rows)

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
                    strategy_entry_vacuums_current.c.period_anchor_ms
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

    async def prepare_generic_gap_continuity_proof(self, *, strategy_group_id: str,
        selection_spec_id: str, period_anchor_ms: int) -> GenericRecoveryGrantProof:
        """Lock the former Active set and produce a strictly future gap proposal."""
        from src.trading_kernel.application.advance_strategy_universe import (
            UniverseActivationOperation,
            UniverseActivationRequest,
            UniverseActivationStatus,
        )
        from src.trading_kernel.infrastructure.pg_signal_repository import (
            PostgresSignalRepository,
        )
        from src.trading_kernel.infrastructure.pg_universe_repository import (
            PostgresStrategyUniverseRepository,
        )

        spec = await self.get_generic_spec(selection_spec_id)
        if spec.strategy_group_id != strategy_group_id:
            raise SelectionJobConflict("Gap continuity Spec changed")
        owner = (await self._connection.execute(sa.select(strategy_entry_controls_current).where(
            strategy_entry_controls_current.c.strategy_group_id==strategy_group_id).with_for_update())).mappings().one_or_none()
        control = await self.get_selection_control(strategy_group_id,for_update=True)
        vacuum = await self.get_current_entry_vacuum(strategy_group_id=strategy_group_id,
            selection_spec_id=selection_spec_id,for_update=True)
        source = await self.get_current_generic_authority(selection_spec_id,for_update=True)
        if (owner is None or owner["entry_state"]!="enabled" or control is None
            or control.selection_mode is not SelectionMode.DYNAMIC_SELECTION
            or control.selection_spec_id!=selection_spec_id or control.pending_selection_mode is not None
            or source is None or control.selection_epoch_id!=source.authority.selection_epoch_id
            or control.control_version!=source.authority.selection_control_version
            or owner["control_version"]!=source.authority.owner_control_version
            or vacuum is None or vacuum.period_anchor_ms!=period_anchor_ms
            or vacuum.state is not StrategyEntryVacuumState.RECOVERY_PENDING
            or vacuum.source_generation_id is not None or vacuum.first_blocker!="AUTHORITY_GAP"
            or vacuum.drained_at_ms is None or vacuum.resolved_at_ms is not None
            or await self.entry_vacuum_has_drain_blockers(strategy_group_id=strategy_group_id)):
            raise SelectionJobConflict("Gap continuity requires exact drained Owner/Control/Vacuum source")
        origin = (await self._connection.execute(sa.select(strategy_entry_vacuum_events.c.payload).where(
            strategy_entry_vacuum_events.c.entry_vacuum_id==vacuum.entry_vacuum_id,
            strategy_entry_vacuum_events.c.event_type=="OPEN").limit(1))).scalar_one_or_none()
        if origin is None or origin.get("source_selection_authority_id")!=source.authority.selection_authority_id:
            raise SelectionJobConflict("Gap continuity OPEN event source changed")
        period = build_generic_selection_period(feature_cutoff_at_ms=period_anchor_ms,cadence_hours=spec.cadence_hours)
        prior = source.authority
        prior_fresh = prior.recovery_proof.membership_freshness if isinstance(prior,GenericRecoveryAuthority) else prior.membership_freshness
        if (prior_fresh is None or prior.blocks_new_entry or prior.expires_at_ms!=period.scheduled_effective_at_ms
            or prior.event_binding.grant_state is not AuthorityEventGrantState.ACTIVE):
            raise SelectionJobConflict("Gap continuity previous Authority is not continuous")
        try:
            freshness = record_dynamic_selection_miss(current=prior_fresh,missed_period=period)
        except ValueError as exc:
            raise SelectionJobConflict("Gap continuity absolute freshness expired") from exc
        uid = prior.event_binding.universe_version_id
        universes = PostgresStrategyUniverseRepository(self._connection)
        active = await universes.get_current(spec.event_spec_id)
        if uid is None or active is None or active.universe_version_id!=uid:
            raise SelectionJobConflict("Gap continuity previous Active Universe changed")
        ready = await universes.try_activate(UniverseActivationRequest(universe_version_id=uid,
            attempted_at_ms=vacuum.drained_at_ms,operation=UniverseActivationOperation.CERTIFY_CURRENT))
        if ready.status is not UniverseActivationStatus.ALREADY_ACTIVE:
            raise SelectionJobConflict("Gap continuity previous Universe not ready")
        signals = PostgresSignalRepository(self._connection)
        members = await signals.get_observation_universe_members(event_spec_id=spec.event_spec_id,universe_version_id=uid)
        if members is None or members.lifecycle_state!="active" or (
            selected_member_set_digest(members.exchange_instrument_ids)!=prior.event_binding.member_set_digest):
            raise SelectionJobConflict("Gap continuity previous members changed")
        if prior.comparison_universe_id is not None:
            comparison = await self.get_comparison_universe_binding(spec.event_spec_id,for_update=True)
            if comparison is None or comparison.comparison_universe_id!=prior.comparison_universe_id or (
                comparison.comparison_transition_revision!=prior.comparison_transition_revision):
                raise SelectionJobConflict("Gap continuity Comparison changed")
        policies = (await self._connection.execute(sa.text(
            "SELECT DISTINCT p.enabled,p.new_entry_submit_enabled FROM brc_owner_policy_current p "
            "JOIN brc_runtime_scopes_current s USING(owner_policy_id) WHERE s.universe_version_id=:uid LIMIT 2"),
            {"uid":uid})).mappings().all()
        if len(policies)!=1 or not policies[0]["enabled"] or not policies[0]["new_entry_submit_enabled"]:
            raise SelectionJobConflict("Gap continuity Owner Policy blocks ENTRY")
        now = await self.read_authority_clock_ms()
        if now<vacuum.drained_at_ms or now<owner["updated_at_ms"] or now<control.updated_at_ms:
            raise SelectionJobConflict("Gap continuity clock moved backwards")
        coverage = await signals.lock_recovery_close_coverage(event_spec_id=spec.event_spec_id,
            exchange_instrument_ids=members.exchange_instrument_ids,selection_mode="dynamic_selection",evaluated_at_ms=now)
        revision = 1
        for cursor in coverage:
            checkpoint = await signals.get_authority_recovery_checkpoint(cursor.episode_domain_key)
            if checkpoint is not None:
                revision = max(revision,checkpoint.recovery_revision+1)
        plan = plan_hourly_recovery_close(recovery_id="recovery:"+canonical_digest({
            "entry_vacuum_id":vacuum.entry_vacuum_id})[7:],recovery_revision=revision,
            reason="AUTHORITY_GAP",period=period,evaluated_at_ms=now)
        if plan.first_eligible_close_time_ms is None:
            raise SelectionJobConflict("NO_ELIGIBLE_CLOSE_BEFORE_EXPIRY")
        committed = await self.read_authority_clock_ms()
        require_hourly_recovery_commit(plan,committed_at_ms=committed)
        return GenericRecoveryGrantProof(authority_outcome="PRE_FENCE_CONTINUITY",
            selection_spec_id=selection_spec_id,strategy_group_id=strategy_group_id,
            selection_epoch_id=prior.selection_epoch_id,selection_mode="dynamic_selection",
            source_entry_vacuum_id=vacuum.entry_vacuum_id,vacuum_fenced_at_ms=vacuum.fenced_at_ms,
            materialization_generation_id=None,source_selection_authority_id=prior.selection_authority_id,
            failed_activation_authorization_id=None,owner_control_version=owner["control_version"],
            selection_control_version=control.control_version,event_binding=prior.event_binding,
            recovery_close_plan=plan,membership_freshness=freshness,
            comparison_universe_id=prior.comparison_universe_id,
            comparison_transition_revision=prior.comparison_transition_revision,
            observation_cursors=coverage,committed_at_ms=committed)

    async def require_generic_gap_continuity_proof(self, proof: GenericRecoveryGrantProof) -> int:
        proof = GenericRecoveryGrantProof.model_validate(proof.model_dump())
        if proof.authority_outcome != "PRE_FENCE_CONTINUITY":
            raise SelectionJobConflict("Gap continuity requires its exact future-close proof")
        checked_at = await self.read_authority_clock_ms()
        require_hourly_recovery_commit(proof.recovery_close_plan,committed_at_ms=checked_at)
        fresh = await self.prepare_generic_gap_continuity_proof(
            strategy_group_id=proof.strategy_group_id,selection_spec_id=proof.selection_spec_id,
            period_anchor_ms=proof.recovery_close_plan.period.feature_cutoff_at_ms)
        expected = proof.model_dump(mode="json")
        actual = fresh.model_dump(mode="json")
        expected["committed_at_ms"] = actual["committed_at_ms"]
        expected["recovery_close_plan"]["evaluated_at_ms"] = actual["recovery_close_plan"]["evaluated_at_ms"]
        if expected != actual:
            raise SelectionJobConflict("Gap continuity proof changed")
        matches = await self._connection.scalar(sa.text(
            "SELECT brc_generic_gap_continuity_proof_matches(CAST(:proof AS jsonb),:checked_at)"),
            {"proof":proof.model_dump_json(),"checked_at":checked_at})
        if matches is not True:
            raise SelectionJobConflict("Gap continuity PostgreSQL proof changed")
        return checked_at

    async def commit_generic_gap_continuity(self, proof: GenericRecoveryGrantProof) -> GenericRecoveryAuthority:
        """Atomically rebase the previous Event set and resolve its gap Vacuum."""
        proof = GenericRecoveryGrantProof.model_validate(proof.model_dump())
        if proof.authority_outcome != "PRE_FENCE_CONTINUITY":
            raise SelectionJobConflict("Gap continuity recovery outcome differs")
        async with self._connection.begin_nested():
            checked_at = await self.require_generic_gap_continuity_proof(proof)
            proof = GenericRecoveryGrantProof.model_validate({**proof.model_dump(),"committed_at_ms":checked_at})
            current = await self.get_current_generic_authority(proof.selection_spec_id,for_update=True)
            vacuum = await self.get_current_entry_vacuum(strategy_group_id=proof.strategy_group_id,
                selection_spec_id=proof.selection_spec_id,for_update=True)
            if (current is None or current.authority.selection_authority_id!=proof.source_selection_authority_id
                or vacuum is None or vacuum.entry_vacuum_id!=proof.source_entry_vacuum_id
                or vacuum.state is not StrategyEntryVacuumState.RECOVERY_PENDING):
                raise SelectionJobConflict("Gap continuity current or Vacuum changed")
            sequence = int(await self._connection.scalar(sa.select(sa.func.max(
                selection_session_authorities.c.authority_sequence)).where(
                    selection_session_authorities.c.selection_spec_id==proof.selection_spec_id,
                    selection_session_authorities.c.period_anchor_ms==proof.recovery_close_plan.period.feature_cutoff_at_ms)) or 0)+1
            authority = GenericRecoveryAuthority.build(proof=proof,authority_sequence=sequence)
            await self._connection.execute(sa.insert(selection_session_authorities).values(
                **generic_recovery_authority_storage_values(authority)))
            await self._connection.execute(sa.insert(selection_authority_event_bindings).values(
                selection_authority_id=authority.selection_authority_id,
                **authority.event_binding.model_dump(mode="json")))
            await self.initialize_generic_recovery_checkpoints(proof)
            changed = await self._connection.execute(sa.update(strategy_entry_vacuums_current).where(
                strategy_entry_vacuums_current.c.entry_vacuum_id==vacuum.entry_vacuum_id,
                strategy_entry_vacuums_current.c.state=="RECOVERY_PENDING",
                strategy_entry_vacuums_current.c.projection_version==vacuum.projection_version).values(
                    state="RESOLVED_CONTINUITY",resolved_at_ms=checked_at,
                    projection_version=vacuum.projection_version+1))
            if changed.rowcount!=1:
                raise SelectionJobConflict("Gap continuity Vacuum CAS changed")
            changed = await self._connection.execute(sa.update(selection_authority_current).where(
                selection_authority_current.c.selection_spec_id==proof.selection_spec_id,
                selection_authority_current.c.selection_authority_id==proof.source_selection_authority_id,
                selection_authority_current.c.projection_version==current.projection_version).values(
                    selection_authority_id=authority.selection_authority_id,
                    projection_version=current.projection_version+1,updated_at_ms=checked_at))
            if changed.rowcount!=1:
                raise SelectionJobConflict("Gap continuity current CAS changed")
            await self._connection.execute(sa.insert(strategy_entry_vacuum_events).values(
                entry_vacuum_event_id=f"vacuum-event:{vacuum.entry_vacuum_id}:{vacuum.projection_version+1}",
                entry_vacuum_id=vacuum.entry_vacuum_id,event_sequence=vacuum.projection_version+1,
                event_type="RESOLVED_CONTINUITY",
                payload={"selection_authority_id":authority.selection_authority_id,
                    "source_selection_authority_id":proof.source_selection_authority_id},
                occurred_at_ms=checked_at))
            require_hourly_recovery_commit(proof.recovery_close_plan,
                committed_at_ms=await self.read_authority_clock_ms())
        return authority

    async def commit_generic_recovery(self, proof: GenericRecoveryGrantProof) -> GenericRecoveryAuthority:
        """Commit Static-first or Dynamic previous-active recovery atomically.

        ENTRY remains separately gated by the runtime recovery/rebase consumer.
        """
        proof = GenericRecoveryGrantProof.model_validate(proof.model_dump())
        if proof.materialization_generation_id is None:
            raise SelectionJobConflict("Recovery transaction requires failed Generation")
        async with self._connection.begin_nested():
            owner = (await self._connection.execute(sa.select(strategy_entry_controls_current).where(
                strategy_entry_controls_current.c.strategy_group_id==proof.strategy_group_id).with_for_update())).mappings().one_or_none()
            control = await self.get_selection_control(proof.strategy_group_id,for_update=True)
            current = await self.get_current_generic_authority(proof.selection_spec_id,for_update=True)
            if current is not None and current.authority.materialization_generation_id==proof.materialization_generation_id:
                existing = current.authority
                if not isinstance(existing,GenericRecoveryAuthority) or existing.recovery_proof!=proof:
                    raise SelectionJobConflict("Static recovery idempotency identity changed")
                vacuum_row = (await self._connection.execute(sa.select(strategy_entry_vacuums_current).where(
                    strategy_entry_vacuums_current.c.entry_vacuum_id==proof.source_entry_vacuum_id).with_for_update())).mappings().one_or_none()
                checked_at = await self.read_authority_clock_ms()
                if owner is None or owner["entry_state"]!="enabled" or owner["control_version"]!=proof.owner_control_version or (
                    control is None or control.selection_mode.value!=proof.selection_mode
                    or control.control_version!=proof.selection_control_version or control.selection_epoch_id!=(None if proof.selection_mode=="static_baseline" else proof.selection_epoch_id)
                    or control.pending_selection_mode is not None or vacuum_row is None
                    or vacuum_row["state"]!="RESOLVED_FALLBACK" or vacuum_row["resolved_at_ms"]!=existing.created_at_ms
                    or not existing.created_at_ms<=checked_at<existing.expires_at_ms):
                    raise SelectionJobConflict("Static recovery idempotency authority changed")
                previous_current = await self._connection.scalar(sa.select(strategy_universe_current.c.universe_version_id).where(
                    strategy_universe_current.c.event_spec_id==proof.event_binding.event_spec_id))
                if previous_current!=proof.event_binding.universe_version_id:
                    raise SelectionJobConflict("Static recovery idempotency Universe changed")
                if proof.comparison_universe_id is not None:
                    comparison = await self.get_comparison_universe_binding(proof.event_binding.event_spec_id,for_update=True)
                    if comparison is None or comparison.comparison_universe_id!=proof.comparison_universe_id or (
                        comparison.comparison_transition_revision!=proof.comparison_transition_revision
                        or comparison.source_static_universe_version_id!=previous_current):
                        raise SelectionJobConflict("Static recovery idempotency comparison changed")
                return existing
            checked_at = await self.require_generic_recovery_grant_proof(proof)
            # Grant facts freeze the actual verification boundary, not the time
            # a caller prepared the proposal. The immutable origin window stays.
            proof = GenericRecoveryGrantProof.model_validate({**proof.model_dump(),"committed_at_ms":checked_at})
            sequence = int(await self._connection.scalar(sa.select(sa.func.max(selection_session_authorities.c.authority_sequence)).where(
                selection_session_authorities.c.selection_spec_id==proof.selection_spec_id,
                selection_session_authorities.c.period_anchor_ms==proof.recovery_close_plan.period.feature_cutoff_at_ms)) or 0)+1
            authority = GenericRecoveryAuthority.build(proof=proof,authority_sequence=sequence)
            # Pre-state validation belongs to the INSERT trigger, before Control
            # and checkpoints change. Deferred SQL guards verify the final set.
            await self._connection.execute(sa.insert(selection_session_authorities).values(**generic_recovery_authority_storage_values(authority)))
            await self._connection.execute(sa.insert(selection_authority_event_bindings).values(
                selection_authority_id=authority.selection_authority_id,**authority.event_binding.model_dump(mode="json")))
            await self.initialize_generic_recovery_checkpoints(proof)
            if proof.selection_mode=="static_baseline":
                changed = await self._connection.execute(sa.update(strategy_selection_control_current).where(
                    strategy_selection_control_current.c.strategy_group_id==proof.strategy_group_id,
                    strategy_selection_control_current.c.control_version==proof.selection_control_version-1,
                    strategy_selection_control_current.c.selection_mode=="static_baseline",
                    strategy_selection_control_current.c.pending_authorization_id==proof.failed_activation_authorization_id,
                    strategy_selection_control_current.c.selection_epoch_id==proof.selection_epoch_id).values(
                        pending_selection_mode=None,pending_effective_period_anchor_ms=None,pending_authorization_id=None,
                        selection_epoch_id=None,control_version=proof.selection_control_version,updated_at_ms=proof.committed_at_ms))
                if changed.rowcount!=1:
                    raise SelectionJobConflict("Static recovery Control CAS changed")
            vacuum = await self.get_current_entry_vacuum(strategy_group_id=proof.strategy_group_id,selection_spec_id=proof.selection_spec_id,for_update=True)
            if vacuum is None or vacuum.entry_vacuum_id!=proof.source_entry_vacuum_id:
                raise SelectionJobConflict("Static recovery Vacuum changed")
            changed = await self._connection.execute(sa.update(strategy_entry_vacuums_current).where(
                strategy_entry_vacuums_current.c.entry_vacuum_id==vacuum.entry_vacuum_id,
                strategy_entry_vacuums_current.c.projection_version==vacuum.projection_version).values(
                    state="RESOLVED_FALLBACK",resolved_at_ms=proof.committed_at_ms,projection_version=vacuum.projection_version+1))
            if changed.rowcount!=1:
                raise SelectionJobConflict("Static recovery Vacuum CAS changed")
            current_version = 0 if current is None else current.projection_version
            if current is None:
                changed = await self._connection.execute(pg_insert(selection_authority_current).values(selection_spec_id=proof.selection_spec_id,
                    selection_authority_id=authority.selection_authority_id,projection_version=1,updated_at_ms=proof.committed_at_ms).on_conflict_do_nothing())
            else:
                changed = await self._connection.execute(sa.update(selection_authority_current).where(
                    selection_authority_current.c.selection_spec_id==proof.selection_spec_id,
                    selection_authority_current.c.selection_authority_id==proof.source_selection_authority_id,
                    selection_authority_current.c.projection_version==current_version).values(
                    selection_authority_id=authority.selection_authority_id,projection_version=current_version+1,updated_at_ms=proof.committed_at_ms))
            if changed.rowcount!=1:
                raise SelectionJobConflict("Static recovery current CAS changed")
            await self._connection.execute(sa.insert(strategy_entry_vacuum_events).values(
                entry_vacuum_event_id=f"vacuum-event:{vacuum.entry_vacuum_id}:{vacuum.projection_version+1}",entry_vacuum_id=vacuum.entry_vacuum_id,
                event_sequence=vacuum.projection_version+1,event_type="RESOLVED_FALLBACK",
                payload={"selection_authority_id":authority.selection_authority_id,"source_generation_id":proof.materialization_generation_id},occurred_at_ms=proof.committed_at_ms))
            seq = int(await self._connection.scalar(sa.select(sa.func.max(strategy_universe_materialization_events.c.event_sequence)).where(
                strategy_universe_materialization_events.c.materialization_generation_id==proof.materialization_generation_id)) or 0)+1
            await self._connection.execute(sa.insert(strategy_universe_materialization_events).values(
                materialization_event_id=f"materialization-event:{proof.materialization_generation_id}:{seq}",materialization_generation_id=proof.materialization_generation_id,
                event_sequence=seq,event_type="STATIC_RECOVERY_COMMITTED" if proof.selection_mode=="static_baseline" else "DYNAMIC_RECOVERY_COMMITTED",
                payload={"selection_authority_id":authority.selection_authority_id},occurred_at_ms=proof.committed_at_ms))
            require_hourly_recovery_commit(proof.recovery_close_plan,committed_at_ms=await self.read_authority_clock_ms())
        return authority

    async def initialize_generic_recovery_checkpoints(self, proof: GenericRecoveryGrantProof) -> tuple[AuthorityRecoveryCheckpoint, ...]:
        """Atomic component of recovery, not a grant; caller owns the transaction.

        Require the original locked proof before any write. A retry of a final
        recovery commit must load its committed Authority, not rerun this step.
        """
        from src.trading_kernel.infrastructure.pg_signal_repository import (
            PostgresSignalRepository,
        )

        proof = GenericRecoveryGrantProof.model_validate(proof.model_dump())
        if proof.authority_outcome=="ACTIVE_NEW":
            await self.require_generic_recovered_activation_proof(proof)
        elif proof.authority_outcome=="PRE_FENCE_CONTINUITY":
            await self.require_generic_gap_continuity_proof(proof)
        else:
            await self.require_generic_recovery_grant_proof(proof)
        signals = PostgresSignalRepository(self._connection)
        checkpoints = []
        # The proof checker already acquired these advisory/row locks in the
        # canonical member order. A savepoint also protects against callers
        # catching an error and accidentally committing a partial member set.
        async with self._connection.begin_nested():
            for cursor in proof.observation_cursors:
                current = await signals.lock_exposure_episode(cursor.episode_domain_key)
                prior = await signals.get_authority_recovery_checkpoint(cursor.episode_domain_key)
                if (0 if current is None else current.projection_version)!=cursor.episode_version or (
                    (0 if prior is None else prior.projection_version)!=cursor.authority_recovery_checkpoint_version):
                    raise SelectionJobConflict("Recovery initialization cursor changed")
                checkpoint = begin_authority_recovery_rebase(current=prior,episode_domain_key=cursor.episode_domain_key,
                    recovery_id=proof.recovery_close_plan.recovery_id,recovery_revision=proof.recovery_close_plan.recovery_revision,
                    effective_from_ms=proof.committed_at_ms,first_eligible_close_time_ms=proof.first_eligible_close_time_ms,
                    latest_consumed_close_time_ms=cursor.last_observed_at_ms)
                state = current if current is not None else ExposureEpisodeState(episode_domain_key=cursor.episode_domain_key,
                    event_spec_id=proof.event_binding.event_spec_id,exchange_instrument_id=cursor.exchange_instrument_id,
                    position_side=proof.event_binding.position_side,state="authority_rebase_required",exposure_episode_id=None,
                    triggered_at_ms=None,rearmed_at_ms=None,last_observed_at_ms=None,projection_version=1)
                values = {"authority_recovery_id":checkpoint.recovery_id,"authority_recovery_revision":checkpoint.recovery_revision,
                    "authority_recovery_effective_from_ms":checkpoint.effective_from_ms,
                    "authority_recovery_first_eligible_close_time_ms":checkpoint.first_eligible_close_time_ms,
                    "authority_recovery_armed_at_ms":checkpoint.armed_at_close_time_ms,
                    "authority_recovery_last_observed_at_ms":checkpoint.last_observed_close_time_ms,
                    "authority_recovery_last_detector_status":None,"authority_recovery_checkpoint_version":checkpoint.projection_version}
                if current is None:
                    changed = await self._connection.execute(pg_insert(exposure_episode_current).values(**state.model_dump(),**values)
                        .on_conflict_do_nothing(index_elements=[exposure_episode_current.c.episode_domain_key]))
                else:
                    changed = await self._connection.execute(sa.update(exposure_episode_current).where(
                        exposure_episode_current.c.episode_domain_key==cursor.episode_domain_key,
                        exposure_episode_current.c.projection_version==cursor.episode_version,
                        sa.func.coalesce(exposure_episode_current.c.authority_recovery_checkpoint_version,0)==cursor.authority_recovery_checkpoint_version,
                    ).values(**values))
                if changed.rowcount!=1:
                    raise SelectionJobConflict("Recovery initialization Episode CAS changed")
                checkpoints.append(checkpoint)
            require_hourly_recovery_commit(proof.recovery_close_plan,committed_at_ms=await self.read_authority_clock_ms())
        return tuple(checkpoints)

    async def require_generic_recovery_grant_proof(self, proof: GenericRecoveryGrantProof) -> int:
        """Recheck every frozen reference under the preparation locks; grant nothing."""
        proof = GenericRecoveryGrantProof.model_validate(proof.model_dump())
        if proof.materialization_generation_id is None:
            raise SelectionJobConflict("Recovery requires failed Generation")
        now = await self.read_authority_clock_ms()
        if now<proof.committed_at_ms:
            raise ValueError("Recovery verification clock moved backwards")
        require_hourly_recovery_commit(proof.recovery_close_plan,committed_at_ms=now)
        fresh = await self.prepare_generic_recovery_grant_proof(proof.materialization_generation_id)
        # Time may advance inside the same future-close window. Never normalize
        # versions, members, origin, first close, period or source identity.
        expected = proof.model_dump(mode="json")
        actual = fresh.model_dump(mode="json")
        expected["committed_at_ms"] = actual["committed_at_ms"]
        expected["recovery_close_plan"]["evaluated_at_ms"] = actual["recovery_close_plan"]["evaluated_at_ms"]
        if expected!=actual:
            raise SelectionJobConflict("Generic recovery proof changed")
        require_hourly_recovery_commit(proof.recovery_close_plan,committed_at_ms=fresh.committed_at_ms)
        matches = await self._connection.scalar(sa.text(
            "SELECT brc_generic_static_recovery_proof_matches(CAST(:proof AS jsonb),:checked_at)"),
            {"proof":proof.model_dump_json(),"checked_at":fresh.committed_at_ms})
        if matches is not True:
            raise SelectionJobConflict("Generic recovery PostgreSQL proof differs")
        return fresh.committed_at_ms

    async def require_generic_recovered_activation_proof(self, proof: GenericRecoveryGrantProof) -> int:
        """Revalidate every locked reference before any recovered target grant."""
        proof = GenericRecoveryGrantProof.model_validate(proof.model_dump())
        if proof.authority_outcome!="ACTIVE_NEW" or proof.materialization_generation_id is None:
            raise SelectionJobConflict("Recovered activation requires exact target proof")
        checked_at = await self.read_authority_clock_ms()
        require_hourly_recovery_commit(proof.recovery_close_plan,committed_at_ms=checked_at)
        fresh = await self.prepare_generic_recovered_activation_proof(proof.materialization_generation_id)
        expected = proof.model_dump(mode="json")
        actual = fresh.model_dump(mode="json")
        expected["committed_at_ms"] = actual["committed_at_ms"]
        expected["recovery_close_plan"]["evaluated_at_ms"] = actual["recovery_close_plan"]["evaluated_at_ms"]
        if expected!=actual:
            raise SelectionJobConflict("Recovered activation proof changed")
        matches = await self._connection.scalar(sa.text(
            "SELECT brc_generic_recovered_activation_proof_matches(CAST(:proof AS jsonb),:checked_at)"),
            {"proof":proof.model_dump_json(),"checked_at":fresh.committed_at_ms})
        if matches is not True:
            raise SelectionJobConflict("Recovered activation PostgreSQL proof changed")
        return fresh.committed_at_ms

    async def prepare_generic_recovered_activation_proof(self, materialization_generation_id: str) -> GenericRecoveryGrantProof:
        """Freeze a newer staged target's future-close recovery inputs without writing."""
        from src.trading_kernel.infrastructure.pg_signal_repository import (
            PostgresSignalRepository,
        )
        from src.trading_kernel.infrastructure.pg_universe_repository import (
            PostgresStrategyUniverseRepository,
        )

        initial = await self.get_generic_materialization_generation(materialization_generation_id)
        if initial is None:
            raise SelectionJobConflict("Recovered activation Generation missing")
        owner = (await self._connection.execute(sa.select(strategy_entry_controls_current).where(
            strategy_entry_controls_current.c.strategy_group_id==initial.strategy_group_id).with_for_update())).mappings().one_or_none()
        control = await self.get_selection_control(initial.strategy_group_id,for_update=True)
        generation = await self.get_generic_materialization_generation(materialization_generation_id,for_update=True)
        if owner is None or owner["entry_state"]!="enabled" or control is None or generation is None or (
            control.selection_mode is not SelectionMode.DYNAMIC_SELECTION or control.pending_selection_mode is not None
            or control.control_version!=generation.selection_control_version or control.selection_epoch_id!=generation.selection_epoch_id):
            raise SelectionJobConflict("Recovered activation Owner or Control changed")
        now = await self.read_authority_clock_ms()
        spec = await self.get_generic_spec(generation.selection_spec_id)
        if generation.lifecycle_state is not MaterializationGenerationState.STAGED or generation.fenced_at_ms is None or (
            now<generation.fenced_at_ms or now>=generation.fenced_at_ms+spec.materialization_timeout_ms):
            raise SelectionJobConflict("Recovered activation requires unexpired staged Generation")
        snapshot = await self.get_generic_snapshot(generation.selection_snapshot_id)
        if snapshot.selection_epoch_id!=generation.selection_epoch_id or not snapshot.effective_from_ms<=now<snapshot.expires_at_ms:
            raise SelectionJobConflict("Recovered activation Snapshot period changed")
        vacuum = await self.get_current_entry_vacuum(strategy_group_id=generation.strategy_group_id,
            selection_spec_id=generation.selection_spec_id,for_update=True)
        if vacuum is None or vacuum.source_generation_id!=materialization_generation_id or vacuum.state is not StrategyEntryVacuumState.RECONFIGURING or (
            vacuum.drained_at_ms is None or vacuum.resolved_at_ms is not None
            or vacuum.fenced_at_ms>=generation.fenced_at_ms or vacuum.period_anchor_ms!=generation.period_anchor_ms
            or await self.entry_vacuum_has_drain_blockers(strategy_group_id=generation.strategy_group_id)):
            raise SelectionJobConflict("Recovered activation requires exact interrupted drained Vacuum")
        predecessor = (await self._connection.execute(sa.select(strategy_entry_vacuum_events.c.payload).where(
            strategy_entry_vacuum_events.c.entry_vacuum_id==vacuum.entry_vacuum_id,
            strategy_entry_vacuum_events.c.event_type=="SUPERSEDED"
        ).order_by(strategy_entry_vacuum_events.c.event_sequence.desc()).limit(1))).scalar_one_or_none()
        if predecessor is None or predecessor.get("replacement_generation_id")!=materialization_generation_id:
            raise SelectionJobConflict("Recovered activation lacks interrupted predecessor lineage")
        if predecessor.get("recovery_origin") in {"AUTHORITY_GAP","OWNER_PAUSE_NO_GENERATION"}:
            opened = (await self._connection.execute(sa.select(strategy_entry_vacuum_events.c.payload).where(
                strategy_entry_vacuum_events.c.entry_vacuum_id==vacuum.entry_vacuum_id,
                strategy_entry_vacuum_events.c.event_type=="OPEN").limit(1))).scalar_one_or_none()
            if (predecessor.get("previous_generation_id") is not None
                or vacuum.first_blocker!="AUTHORITY_GAP" or opened is None
                or opened.get("intended_outcome")!=("OWNER_PAUSED" if predecessor.get("recovery_origin")=="OWNER_PAUSE_NO_GENERATION" else "PRE_FENCE_CONTINUITY")
                or (predecessor.get("recovery_origin")=="AUTHORITY_GAP" and opened.get("source_selection_authority_id")!=predecessor.get("source_selection_authority_id"))):
                raise SelectionJobConflict("Recovered activation original Authority gap changed")
            recovery_reason: Literal["AUTHORITY_GAP","MATERIALIZATION_FAILURE","MATERIALIZATION_TIMEOUT"] = "AUTHORITY_GAP"
        else:
            interrupted = await self.get_generic_materialization_generation(predecessor["previous_generation_id"],for_update=True)
            unfinished = predecessor.get("recovery_origin")=="UNFINISHED_MATERIALIZATION"
            paused_origin = predecessor.get("recovery_origin")=="OWNER_PAUSE"
            expected_state = (MaterializationGenerationState.ABANDONED if paused_origin else
                MaterializationGenerationState.SUPERSEDED if unfinished else MaterializationGenerationState.FAILED_CLOSED)
            if interrupted is None or interrupted.lifecycle_state is not expected_state or (
                interrupted.terminal_at_ms is None or interrupted.terminal_at_ms>generation.created_at_ms
                or interrupted.fenced_at_ms is None or not vacuum.fenced_at_ms<=interrupted.fenced_at_ms<generation.fenced_at_ms
                or interrupted.selection_epoch_id!=generation.selection_epoch_id
                or interrupted.selection_spec_id!=generation.selection_spec_id
                or interrupted.selection_control_version!=generation.selection_control_version
                or interrupted.period_anchor_ms>=generation.period_anchor_ms
                or interrupted.previous_events!=generation.previous_events):
                raise SelectionJobConflict("Recovered activation interrupted predecessor changed")
            failure = (await self._connection.execute(sa.select(strategy_universe_materialization_events.c.payload).where(
                strategy_universe_materialization_events.c.materialization_generation_id==interrupted.materialization_generation_id,
                strategy_universe_materialization_events.c.event_type==(
                    "SUPERSEDED_BY_NEWER_SELECTION" if unfinished or paused_origin else "FAILED_CLOSED")
            ).order_by(strategy_universe_materialization_events.c.event_sequence.desc()).limit(1))).scalar_one_or_none()
            if unfinished or paused_origin:
                if failure is None or failure.get("entry_vacuum_id")!=vacuum.entry_vacuum_id or (
                    failure.get("replacement_generation_id")!=generation.materialization_generation_id
                    or failure.get("previous_lifecycle_state") not in ({"ABANDONED"} if paused_origin else {"MATERIALIZING","STAGED"})
                    or failure.get("original_fenced_at_ms")!=vacuum.fenced_at_ms
                    or failure.get("original_drained_at_ms")!=vacuum.drained_at_ms):
                    raise SelectionJobConflict("Recovered activation supersession cause changed")
                recovery_reason = "AUTHORITY_GAP"
            elif failure is None or failure.get("entry_vacuum_id")!=vacuum.entry_vacuum_id or failure.get("reason_code") not in {
                "MATERIALIZATION_TIMEOUT","MATERIALIZATION_PERIOD_EXPIRED","CERTIFICATION_OWNER_ACTION_REQUIRED","CERTIFICATION_NOT_ELIGIBLE"}:
                raise SelectionJobConflict("Recovered activation original failure cause changed")
            else:
                recovery_reason = (
                    "MATERIALIZATION_TIMEOUT" if failure["reason_code"] in {"MATERIALIZATION_TIMEOUT","MATERIALIZATION_PERIOD_EXPIRED"}
                    else "MATERIALIZATION_FAILURE")
        source = await self.get_current_generic_authority(generation.selection_spec_id,for_update=True)
        resumed_source = source is not None and bool(await self._connection.scalar(sa.text(
            "SELECT brc_generic_vacuum_owner_resume_matches(:vid,:source,:at)"),
            {"vid":vacuum.entry_vacuum_id,"source":source.authority.selection_authority_id,"at":now}))
        if predecessor.get("recovery_origin") in {"OWNER_PAUSE","OWNER_PAUSE_NO_GENERATION"} and not resumed_source:
            raise SelectionJobConflict("Recovered activation Owner resume provenance changed")
        previous = generation.previous_events[0]
        if source is None or (
            source.authority.selection_spec_id!=generation.selection_spec_id
            or source.authority.selection_epoch_id!=generation.selection_epoch_id
            or source.authority.selection_control_version!=control.control_version
            or (source.authority.owner_control_version!=owner["control_version"] and not resumed_source)
            or source.authority.event_binding.event_spec_id!=previous.event_spec_id
            or source.authority.event_binding.position_side!=previous.position_side
            or source.authority.event_binding.universe_version_id!=previous.universe_version_id
            or source.authority.event_binding.member_set_digest!=previous.member_set_digest
            or source.authority.comparison_universe_id!=previous.comparison_universe_id
            or source.authority.comparison_transition_revision!=previous.comparison_transition_revision):
            raise SelectionJobConflict("Recovered activation source Authority changed")
        if predecessor.get("recovery_origin") in {"AUTHORITY_GAP","OWNER_PAUSE_NO_GENERATION"} and predecessor.get("source_selection_authority_id")!=source.authority.selection_authority_id:
            raise SelectionJobConflict("Recovered activation gap source Authority changed")
        universes = PostgresStrategyUniverseRepository(self._connection)
        active = await universes.get_current(spec.event_spec_id)
        targets = await universes.get_generation_universe_targets(materialization_generation_id,for_update=True)
        if active is None or active.universe_version_id!=previous.universe_version_id or len(targets)!=1 or (
            targets[0].event_spec_id!=spec.event_spec_id or targets[0].lifecycle_state.value!="staged"):
            raise SelectionJobConflict("Recovered activation previous or target Universe changed")
        target = targets[0]
        members = await universes.get_members(target.universe_version_id)
        if members!=snapshot.selected_members or selected_member_set_digest(members)!=snapshot.member_set_digest:
            raise SelectionJobConflict("Recovered activation target membership changed")
        comparison_id = None
        comparison_revision = None
        if generation.strategy_group_id in {"MPG-001","MI-001"}:
            comparison = await self.get_comparison_universe_binding(spec.event_spec_id,for_update=True)
            if comparison is None or comparison.comparison_universe_id!=previous.comparison_universe_id or (
                comparison.comparison_transition_revision!=previous.comparison_transition_revision):
                raise SelectionJobConflict("Recovered activation comparison changed")
            comparison_id = "comparison:"+canonical_digest({"exchange_instrument_ids":spec.candidate_ids})[7:]
            comparison_revision = comparison.comparison_transition_revision+int(comparison.comparison_universe_id!=comparison_id)
        signals = PostgresSignalRepository(self._connection)
        coverage = await signals.lock_recovery_close_coverage(event_spec_id=spec.event_spec_id,
            exchange_instrument_ids=members,selection_mode="dynamic_selection",evaluated_at_ms=now)
        revision = 1
        for cursor in coverage:
            checkpoint = await signals.get_authority_recovery_checkpoint(cursor.episode_domain_key)
            if checkpoint is not None:
                revision = max(revision,checkpoint.recovery_revision+1)
        period = build_generic_selection_period(feature_cutoff_at_ms=snapshot.feature_cutoff_at_ms,cadence_hours=spec.cadence_hours)
        recovery_id = "recovery:"+canonical_digest({"entry_vacuum_id":vacuum.entry_vacuum_id,
            "materialization_generation_id":materialization_generation_id})[7:]
        plan = plan_hourly_recovery_close(recovery_id=recovery_id,recovery_revision=revision,
            reason=recovery_reason,period=period,evaluated_at_ms=now)
        if plan.first_eligible_close_time_ms is None:
            period = build_generic_selection_period(feature_cutoff_at_ms=period.feature_cutoff_at_ms+spec.cadence_hours*3600000,
                cadence_hours=spec.cadence_hours)
            plan = plan_hourly_recovery_close(recovery_id=recovery_id,recovery_revision=revision,
                reason=recovery_reason,period=period,evaluated_at_ms=now)
        committed = await self.read_authority_clock_ms()
        require_hourly_recovery_commit(plan,committed_at_ms=committed)
        source_period = build_generic_selection_period(feature_cutoff_at_ms=snapshot.feature_cutoff_at_ms,
            cadence_hours=spec.cadence_hours)
        freshness = build_dynamic_membership_freshness(source_snapshot_id=snapshot.selection_snapshot_id,
            source_member_set_digest=snapshot.member_set_digest,period=source_period)
        if period!=source_period:
            freshness = record_dynamic_selection_miss(current=freshness,missed_period=period)
        return GenericRecoveryGrantProof(authority_outcome="ACTIVE_NEW",target_snapshot_id=snapshot.selection_snapshot_id,
            selection_spec_id=generation.selection_spec_id,strategy_group_id=generation.strategy_group_id,
            selection_epoch_id=generation.selection_epoch_id,selection_mode="dynamic_selection",
            source_entry_vacuum_id=vacuum.entry_vacuum_id,vacuum_fenced_at_ms=vacuum.fenced_at_ms,
            materialization_generation_id=materialization_generation_id,
            source_selection_authority_id=source.authority.selection_authority_id,failed_activation_authorization_id=None,
            owner_control_version=owner["control_version"],selection_control_version=control.control_version,
            event_binding=AuthorityEventBinding(event_spec_id=spec.event_spec_id,position_side=spec.position_side,
                grant_state=AuthorityEventGrantState.ACTIVE,universe_version_id=target.universe_version_id,member_set_digest=snapshot.member_set_digest),
            recovery_close_plan=plan,membership_freshness=freshness,comparison_universe_id=comparison_id,
            comparison_transition_revision=comparison_revision,observation_cursors=coverage,committed_at_ms=committed)

    async def prepare_generic_recovery_grant_proof(self, materialization_generation_id: str) -> GenericRecoveryGrantProof:
        """Prepare Static-first or Dynamic previous-active recovery; write nothing.

        This is not a grant. The eventual commit must revalidate this evidence
        and atomically install Authority/rebase, resolve Vacuum and clear pending.
        """
        from src.trading_kernel.application.advance_strategy_universe import (
            UniverseActivationOperation,
            UniverseActivationRequest,
            UniverseActivationStatus,
        )
        from src.trading_kernel.infrastructure.pg_signal_repository import (
            PostgresSignalRepository,
        )
        from src.trading_kernel.infrastructure.pg_universe_repository import (
            PostgresStrategyUniverseRepository,
        )

        initial = await self.get_generic_materialization_generation(materialization_generation_id)
        if initial is None:
            raise SelectionJobConflict("Recovery Generation missing")
        owner = (await self._connection.execute(sa.select(strategy_entry_controls_current).where(
            strategy_entry_controls_current.c.strategy_group_id==initial.strategy_group_id).with_for_update())).mappings().one_or_none()
        control = await self.get_selection_control(initial.strategy_group_id,for_update=True)
        generation = await self.get_generic_materialization_generation(materialization_generation_id,for_update=True)
        if owner is None or owner["entry_state"]!="enabled" or generation is None or control is None or (
            generation.lifecycle_state is not MaterializationGenerationState.FAILED_CLOSED
            or generation.fenced_at_ms is None or generation.terminal_at_ms is None
            or control.selection_spec_id!=generation.selection_spec_id or control.selection_epoch_id!=generation.selection_epoch_id
            or control.control_version!=generation.selection_control_version):
            raise SelectionJobConflict("Recovery Owner Control or failed Generation changed")
        static_first = control.selection_mode is SelectionMode.STATIC_BASELINE and (
            control.pending_selection_mode is SelectionMode.DYNAMIC_SELECTION
            and control.pending_effective_period_anchor_ms==generation.period_anchor_ms
            and control.pending_authorization_id is not None)
        dynamic = control.selection_mode is SelectionMode.DYNAMIC_SELECTION and (
            control.pending_selection_mode is None and control.pending_authorization_id is None)
        if not static_first and not dynamic:
            raise SelectionJobConflict("Recovery requires exact Static-first or Dynamic control")
        now = await self.read_authority_clock_ms()
        if now<generation.terminal_at_ms:
            raise SelectionJobConflict("Recovery failure time is in the future")
        if now<owner["updated_at_ms"] or now<control.updated_at_ms:
            raise SelectionJobConflict("Recovery control time is in the future")
        # Share Selection's lineage lock so a newly committed due Snapshot
        # cannot race the decision to recover a displaced failed attempt.
        await self._connection.execute(sa.select(instrument_selection_specs.c.selection_spec_id).where(
            instrument_selection_specs.c.selection_spec_id==generation.selection_spec_id).with_for_update())
        newer = await self._connection.scalar(sa.select(instrument_selection_snapshots.c.selection_snapshot_id).where(
            instrument_selection_snapshots.c.selection_spec_id==generation.selection_spec_id,
            instrument_selection_snapshots.c.selection_epoch_id==generation.selection_epoch_id,
            instrument_selection_snapshots.c.period_anchor_ms>generation.period_anchor_ms,
            instrument_selection_snapshots.c.created_at_ms<=now,
            instrument_selection_snapshots.c.eligibility_not_before_ms<=now,
            instrument_selection_snapshots.c.expires_at_ms>now,
        ).order_by(instrument_selection_snapshots.c.period_anchor_ms.desc()).limit(1))
        if newer is not None:
            raise SelectionJobConflict("Recovery superseded by newer effective Selection")
        if static_first:
            authorization = (await self._connection.execute(sa.text(
                "SELECT purpose,authentication_strength,target_scope,authorized_at_ms FROM brc_owner_authorizations WHERE authorization_id=:id"),
                {"id":control.pending_authorization_id})).mappings().one_or_none()
            expected_scope = {"strategy_group_id":generation.strategy_group_id,
                "selection_spec_id":generation.selection_spec_id,
                "selection_epoch_id":generation.selection_epoch_id,
                "target_selection_mode":"dynamic_selection",
                "effective_period_anchor_ms":generation.period_anchor_ms}
            if authorization is None or authorization["purpose"]!="selection_mode_change" or authorization["authentication_strength"]!="totp_step_up" or (
                authorization["target_scope"]!=expected_scope or authorization["authorized_at_ms"]>generation.created_at_ms):
                raise SelectionJobConflict("Static recovery Owner authorization differs")
        vacuum = await self.get_current_entry_vacuum(strategy_group_id=generation.strategy_group_id,selection_spec_id=generation.selection_spec_id,for_update=True)
        if vacuum is None or vacuum.source_generation_id!=materialization_generation_id or vacuum.state is not StrategyEntryVacuumState.RECONFIGURING or (
            vacuum.fenced_at_ms>generation.fenced_at_ms or vacuum.drained_at_ms is None or vacuum.resolved_at_ms is not None
            or await self.entry_vacuum_has_drain_blockers(strategy_group_id=generation.strategy_group_id)):
            raise SelectionJobConflict("Static recovery requires exact drained Vacuum")
        failure = (await self._connection.execute(sa.select(strategy_entry_vacuum_events.c.payload).where(
            strategy_entry_vacuum_events.c.entry_vacuum_id==vacuum.entry_vacuum_id,
            strategy_entry_vacuum_events.c.event_type=="RECOVERY_REQUIRED"
        ).order_by(strategy_entry_vacuum_events.c.event_sequence.desc()).limit(1))).scalar_one_or_none()
        if failure is None or failure.get("source_generation_id")!=materialization_generation_id or failure.get("reason_code")!=vacuum.first_blocker:
            raise SelectionJobConflict("Static recovery failure provenance differs")
        reason: Literal["MATERIALIZATION_FAILURE", "MATERIALIZATION_TIMEOUT"] = (
            "MATERIALIZATION_TIMEOUT" if vacuum.first_blocker in {"MATERIALIZATION_TIMEOUT","MATERIALIZATION_PERIOD_EXPIRED"} else "MATERIALIZATION_FAILURE")
        source_authority = await self.get_current_generic_authority(generation.selection_spec_id,for_update=True)
        if static_first and source_authority is not None:
            raise SelectionJobConflict("Static recovery cannot replace a Dynamic Authority")
        if dynamic and (source_authority is None or source_authority.authority.selection_epoch_id!=generation.selection_epoch_id
            or source_authority.authority.selection_control_version!=control.control_version
            or source_authority.authority.owner_control_version!=owner["control_version"]):
            raise SelectionJobConflict("Dynamic recovery source Authority changed")
        universes = PostgresStrategyUniverseRepository(self._connection)
        targets = await universes.get_generation_universe_targets(materialization_generation_id,for_update=True)
        if any(target.lifecycle_state.value!="abandoned" for target in targets):
            raise SelectionJobConflict("Static recovery has unfinished targets")
        previous = generation.previous_events[0]
        if dynamic and (source_authority is None or source_authority.authority.event_binding.universe_version_id!=previous.universe_version_id
            or source_authority.authority.event_binding.member_set_digest!=previous.member_set_digest
            or source_authority.authority.event_binding.event_spec_id!=previous.event_spec_id):
            raise SelectionJobConflict("Dynamic recovery previous Authority differs")
        current = await universes.get_current(previous.event_spec_id)
        if current is None or current.universe_version_id!=previous.universe_version_id:
            raise SelectionJobConflict("Static recovery previous current changed")
        signals = PostgresSignalRepository(self._connection)
        members = await signals.get_observation_universe_members(event_spec_id=previous.event_spec_id,universe_version_id=current.universe_version_id)
        if members is None or members.lifecycle_state!="active" or selected_member_set_digest(members.exchange_instrument_ids)!=previous.member_set_digest:
            raise SelectionJobConflict("Static recovery previous members changed")
        if previous.comparison_universe_id is not None:
            comparison = await self.get_comparison_universe_binding(previous.event_spec_id,for_update=True)
            if comparison is None or comparison.comparison_universe_id!=previous.comparison_universe_id or comparison.comparison_transition_revision!=previous.comparison_transition_revision:
                raise SelectionJobConflict("Static recovery comparison changed")
        if dynamic and source_authority is not None and (
            source_authority.authority.comparison_universe_id!=previous.comparison_universe_id or
            source_authority.authority.comparison_transition_revision!=previous.comparison_transition_revision):
            raise SelectionJobConflict("Dynamic recovery source comparison changed")
        ready = await universes.try_activate(UniverseActivationRequest(universe_version_id=current.universe_version_id,
            attempted_at_ms=now,operation=UniverseActivationOperation.CERTIFY_CURRENT))
        if ready.status is not UniverseActivationStatus.ALREADY_ACTIVE:
            raise SelectionJobConflict("Static recovery previous not ready: "+str(ready.reason_code))
        policies = (await self._connection.execute(sa.text("SELECT DISTINCT p.enabled,p.new_entry_submit_enabled FROM brc_owner_policy_current p JOIN brc_runtime_scopes_current s ON s.owner_policy_id=p.owner_policy_id WHERE s.universe_version_id=:uid LIMIT 2"),{"uid":current.universe_version_id})).mappings().all()
        if len(policies)!=1 or not policies[0]["enabled"] or not policies[0]["new_entry_submit_enabled"]:
            raise SelectionJobConflict("Static recovery Policy blocks ENTRY")
        spec = await self.get_generic_spec(generation.selection_spec_id)
        coverage = await signals.lock_recovery_close_coverage(event_spec_id=previous.event_spec_id,
            exchange_instrument_ids=members.exchange_instrument_ids,selection_mode="static_baseline" if static_first else "dynamic_selection",evaluated_at_ms=now)
        revision = 1
        for cursor in coverage:
            checkpoint = await signals.get_authority_recovery_checkpoint(cursor.episode_domain_key)
            if checkpoint is not None:
                revision = max(revision,checkpoint.recovery_revision+1)
        recovery_id = "recovery:"+canonical_digest({"entry_vacuum_id":vacuum.entry_vacuum_id})[7:]
        cadence = spec.cadence_hours*3600000
        cutoff = (now-3600000)//cadence*cadence
        period = build_generic_selection_period(feature_cutoff_at_ms=cutoff,cadence_hours=spec.cadence_hours)
        plan = plan_hourly_recovery_close(recovery_id=recovery_id,recovery_revision=revision,
            reason=reason,period=period,evaluated_at_ms=now)
        if plan.first_eligible_close_time_ms is None:
            period = build_generic_selection_period(feature_cutoff_at_ms=cutoff+cadence,cadence_hours=spec.cadence_hours)
            plan = plan_hourly_recovery_close(recovery_id=recovery_id,recovery_revision=revision,
                reason=reason,period=period,evaluated_at_ms=now)
        committed = await self.read_authority_clock_ms()
        require_hourly_recovery_commit(plan,committed_at_ms=committed)
        freshness = None
        if dynamic:
            assert source_authority is not None
            source_value = source_authority.authority
            source_freshness = (source_value.recovery_proof.membership_freshness
                if isinstance(source_value,GenericRecoveryAuthority) else source_value.membership_freshness)
            if source_freshness is None:
                raise SelectionJobConflict("Dynamic recovery source freshness missing")
            missed = (period.scheduled_effective_at_ms-source_freshness.source_snapshot_effective_at_ms)//cadence
            if missed not in {0,1}:
                raise SelectionJobConflict("Dynamic recovery source membership stale")
            freshness = source_freshness.model_copy(update={
                "consecutive_missed_periods":missed,
                "state":DynamicMembershipState.ACTIVE if missed==0 else DynamicMembershipState.GRACE,
            })
            if plan.first_eligible_close_time_ms is None or not freshness.allows_new_entry_at(plan.first_eligible_close_time_ms):
                raise SelectionJobConflict("Dynamic recovery leaves no eligible close before stale deadline")
        return GenericRecoveryGrantProof(selection_spec_id=generation.selection_spec_id,strategy_group_id=generation.strategy_group_id,
            selection_epoch_id=generation.selection_epoch_id,selection_mode="static_baseline" if static_first else "dynamic_selection",source_entry_vacuum_id=vacuum.entry_vacuum_id,
            vacuum_fenced_at_ms=vacuum.fenced_at_ms,materialization_generation_id=materialization_generation_id,
            source_selection_authority_id=None if source_authority is None else source_authority.authority.selection_authority_id,
            failed_activation_authorization_id=control.pending_authorization_id if static_first else None,
            owner_control_version=owner["control_version"],selection_control_version=control.control_version+int(static_first),
            event_binding=AuthorityEventBinding.model_validate(previous.model_dump(exclude={"comparison_universe_id","comparison_transition_revision"})),
            recovery_close_plan=plan,membership_freshness=freshness,comparison_universe_id=previous.comparison_universe_id,
            comparison_transition_revision=previous.comparison_transition_revision,observation_cursors=coverage,committed_at_ms=committed)

    async def generic_activation_authorization_matches(self, authority: GenericSelectionAuthority) -> bool:
        """Exact immutable Owner proof shared by all first-activation outcomes."""
        authorization = (await self._connection.execute(sa.text(
            "SELECT purpose,authentication_strength,target_scope,authorized_at_ms FROM brc_owner_authorizations WHERE authorization_id=:id"),
            {"id":authority.activation_authorization_id})).mappings().one_or_none()
        expected_scope = {"strategy_group_id":authority.strategy_group_id,
            "selection_spec_id":authority.selection_spec_id,
            "selection_epoch_id":authority.selection_epoch_id,
            "target_selection_mode":"dynamic_selection",
            "effective_period_anchor_ms":authority.period.feature_cutoff_at_ms}
        return authorization is not None and authorization["purpose"]=="selection_mode_change" and authorization["authentication_strength"]=="totp_step_up" and authorization["target_scope"]==expected_scope and authorization["authorized_at_ms"]<=authority.created_at_ms

    async def commit_generic_no_change(self, authority: GenericSelectionAuthority, *, expected_current_version: int | None) -> None:
        from src.trading_kernel.application.advance_strategy_universe import (
            UniverseActivationOperation,
            UniverseActivationRequest,
            UniverseActivationStatus,
        )
        from src.trading_kernel.infrastructure.pg_signal_repository import (
            PostgresSignalRepository,
        )
        from src.trading_kernel.infrastructure.pg_universe_repository import (
            PostgresStrategyUniverseRepository,
        )
        authority = GenericSelectionAuthority.model_validate(authority.model_dump())
        if authority.authority_outcome != "NO_CHANGE" or not isinstance(authority.current_close_proof,CurrentFinalCloseGrantProof):
            raise ValueError("NO_CHANGE commit requires normal proof without Generation")
        owner = (await self._connection.execute(sa.select(strategy_entry_controls_current).where(
            strategy_entry_controls_current.c.strategy_group_id == authority.strategy_group_id).with_for_update())).mappings().one_or_none()
        control = await self.get_selection_control(authority.strategy_group_id,for_update=True)
        if owner is None or owner["entry_state"] != "enabled" or owner["control_version"] != authority.owner_control_version:
            raise SelectionJobConflict("NO_CHANGE Owner control changed")
        first_activation = control is not None and control.selection_mode is SelectionMode.STATIC_BASELINE and (
            control.pending_selection_mode is SelectionMode.DYNAMIC_SELECTION
            and control.pending_effective_period_anchor_ms == authority.period.feature_cutoff_at_ms
            and control.pending_authorization_id == authority.activation_authorization_id
            and authority.activation_authorization_id is not None)
        if control is None or (control.selection_mode is not SelectionMode.DYNAMIC_SELECTION and not first_activation) or (
            control.selection_spec_id != authority.selection_spec_id or control.selection_epoch_id != authority.selection_epoch_id
            or control.control_version+int(first_activation) != authority.selection_control_version
            or not control.permits_dynamic_period(authority.period.feature_cutoff_at_ms)):
            raise SelectionJobConflict("NO_CHANGE Selection control changed")
        if first_activation and not await self.generic_activation_authorization_matches(authority):
            raise SelectionJobConflict("NO_CHANGE activation authorization changed")
        vacuum = await self.get_current_entry_vacuum(strategy_group_id=authority.strategy_group_id,
            selection_spec_id=authority.selection_spec_id,for_update=True)
        if vacuum is not None:
            raise SelectionJobConflict("NO_CHANGE cannot cross an open Vacuum")
        current = await self.get_current_generic_authority(authority.selection_spec_id,for_update=True)
        now = await self.read_authority_clock_ms()
        if current is not None and isinstance(current.authority,GenericRecoveryAuthority):
            if authority.authority_outcome!="NO_CHANGE" or (
                authority.continued_from_recovery_authority_id!=current.authority.selection_authority_id
                or current.authority.authority_outcome not in {"ACTIVE_NEW","FALLBACK_PREVIOUS"}):
                raise SelectionJobConflict("Recovery successor origin changed")
        elif current is not None and isinstance(current.authority,GenericSelectionAuthority):
            if authority.continued_from_recovery_authority_id!=current.authority.continued_from_recovery_authority_id:
                raise SelectionJobConflict("Recovery successor lineage changed")
        elif authority.continued_from_recovery_authority_id is not None:
            raise SelectionJobConflict("Recovery successor source Authority missing")
        if current is not None and current.authority.selection_authority_id == authority.selection_authority_id:
            if current.authority != authority:
                raise SelectionJobConflict("NO_CHANGE idempotency identity differs")
            return
        if authority.activation_authorization_id is not None and not first_activation:
            raise SelectionJobConflict("NO_CHANGE activation pending required")
        if first_activation and current is not None:
            raise SelectionJobConflict("NO_CHANGE first activation Authority exists")
        if (None if current is None else current.projection_version) != expected_current_version:
            raise SelectionJobConflict("NO_CHANGE current version changed")
        sequence = 1
        if current is not None:
            if current.authority.blocks_new_entry or current.authority.expires_at_ms < authority.period.scheduled_effective_at_ms:
                raise SelectionJobConflict("NO_CHANGE cannot recover an Authority gap")
            if (current.authority.event_binding != authority.event_binding
                or current.authority.comparison_universe_id != authority.comparison_universe_id
                or current.authority.comparison_transition_revision != authority.comparison_transition_revision
                or current.authority.selection_epoch_id != authority.selection_epoch_id
                or current.authority.owner_control_version != authority.owner_control_version):
                raise SelectionJobConflict("NO_CHANGE prior authority is not continuous")
            if current.authority.period.feature_cutoff_at_ms > authority.period.feature_cutoff_at_ms:
                raise SelectionJobConflict("NO_CHANGE period is stale")
            if current.authority.period == authority.period:
                sequence = current.authority.authority_sequence+1
        if authority.authority_sequence != sequence:
            raise SelectionJobConflict("NO_CHANGE sequence changed")
        require_current_close_commit(authority.current_close_proof,committed_at_ms=now)
        uid = authority.event_binding.universe_version_id
        if uid is None:
            raise ValueError("NO_CHANGE requires a current Universe")
        universes = PostgresStrategyUniverseRepository(self._connection)
        ready = await universes.try_activate(UniverseActivationRequest(universe_version_id=uid,
            attempted_at_ms=now,operation=UniverseActivationOperation.CERTIFY_CURRENT))
        if ready.status is not UniverseActivationStatus.ALREADY_ACTIVE:
            raise SelectionJobConflict("NO_CHANGE readiness: "+str(ready.reason_code))
        policies = (await self._connection.execute(sa.text(
            "SELECT DISTINCT p.owner_policy_id,p.enabled,p.new_entry_submit_enabled FROM brc_owner_policy_current p "
            "JOIN brc_runtime_scopes_current s ON s.owner_policy_id=p.owner_policy_id WHERE s.universe_version_id=:uid LIMIT 2"),{"uid":uid})).mappings().all()
        if len(policies)!=1 or not policies[0]["enabled"] or not policies[0]["new_entry_submit_enabled"]:
            raise SelectionJobConflict("NO_CHANGE Policy blocks ENTRY")
        snapshot = await self.get_generic_snapshot(authority.selection_snapshot_id)
        if snapshot.member_set_digest != authority.event_binding.member_set_digest or snapshot.selection_epoch_id != authority.selection_epoch_id:
            raise SelectionJobConflict("NO_CHANGE Snapshot membership differs")
        signals = PostgresSignalRepository(self._connection)
        prior_universe = await universes.get_current(authority.event_binding.event_spec_id)
        if prior_universe is None or prior_universe.universe_version_id != uid:
            raise SelectionJobConflict("NO_CHANGE current Universe changed")
        if await signals.selection_authority_was_interrupted(strategy_group_id=authority.strategy_group_id,
            selection_spec_id=authority.selection_spec_id,owner_policy_id=policies[0]["owner_policy_id"],
            after_ms=prior_universe.activated_at_ms if current is None else current.authority.created_at_ms,through_ms=now):
            raise SelectionJobConflict("NO_CHANGE continuity was interrupted")
        cursors = await signals.lock_generic_close_coverage(event_spec_id=authority.event_binding.event_spec_id,
            exchange_instrument_ids=snapshot.selected_members,closed_at_ms=authority.current_close_proof.current_final_close_time_ms)
        if cursors != authority.current_close_proof.observation_cursors:
            raise SelectionJobConflict("NO_CHANGE cursor evidence changed")
        await self.require_generic_close_proof(authority.current_close_proof)
        if authority.comparison_universe_id is not None:
            comparison = await self.get_comparison_universe_binding(authority.event_binding.event_spec_id,for_update=True)
            if comparison is None or comparison.comparison_universe_id != authority.comparison_universe_id or comparison.comparison_transition_revision != authority.comparison_transition_revision:
                raise SelectionJobConflict("NO_CHANGE comparison changed")
        await self._supersede_unfenced_generic_predecessors(snapshot,
            selection_control_version=control.control_version,superseded_at_ms=now)
        if first_activation:
            await self.activate_pending_selection_mode(strategy_group_id=authority.strategy_group_id,
                expected_control_version=control.control_version,expected_pending_mode=SelectionMode.DYNAMIC_SELECTION,
                activated_at_ms=authority.created_at_ms)
        await self._connection.execute(sa.insert(selection_session_authorities).values(**generic_authority_storage_values(authority)))
        await self._connection.execute(sa.insert(selection_authority_event_bindings).values(selection_authority_id=authority.selection_authority_id,
            **authority.event_binding.model_dump(mode="json")))
        if current is None:
            updated = await self._connection.execute(pg_insert(selection_authority_current).values(selection_spec_id=authority.selection_spec_id,
                selection_authority_id=authority.selection_authority_id,projection_version=1,updated_at_ms=authority.created_at_ms).on_conflict_do_nothing())
        else:
            updated = await self._connection.execute(sa.update(selection_authority_current).where(
                selection_authority_current.c.selection_spec_id==authority.selection_spec_id,
                selection_authority_current.c.projection_version==expected_current_version).values(selection_authority_id=authority.selection_authority_id,
                    projection_version=current.projection_version+1,updated_at_ms=authority.created_at_ms))
        if updated.rowcount!=1:
            raise SelectionJobConflict("NO_CHANGE current CAS failed")
        require_current_close_commit(authority.current_close_proof,committed_at_ms=await self.read_authority_clock_ms())

    async def commit_generic_continuity(self, authority: GenericSelectionAuthority, *,
        expected_current_version: int) -> None:
        """Commit a one-miss current-set Authority without a Selection result."""
        authority = GenericSelectionAuthority.model_validate(authority.model_dump())
        proof = authority.current_close_proof
        if authority.authority_outcome!="PRE_FENCE_CONTINUITY" or not isinstance(proof,GenericContinuityCloseProof):
            raise SelectionJobConflict("Generic continuity requires its typed source proof")
        owner = (await self._connection.execute(sa.select(strategy_entry_controls_current).where(
            strategy_entry_controls_current.c.strategy_group_id==authority.strategy_group_id).with_for_update())).mappings().one_or_none()
        control = await self.get_selection_control(authority.strategy_group_id,for_update=True)
        current = await self.get_current_generic_authority(authority.selection_spec_id,for_update=True)
        if owner is None or owner["entry_state"]!="enabled" or owner["control_version"]!=authority.owner_control_version or (
            control is None or control.selection_mode is not SelectionMode.DYNAMIC_SELECTION
            or control.selection_spec_id!=authority.selection_spec_id or control.selection_epoch_id!=authority.selection_epoch_id
            or control.control_version!=authority.selection_control_version
            or not control.permits_dynamic_period(authority.period.feature_cutoff_at_ms)
            or current is None or current.projection_version!=expected_current_version
            or current.authority.selection_authority_id!=proof.source_selection_authority_id):
            raise SelectionJobConflict("Generic continuity Owner, Control or source changed")
        if await self.get_current_entry_vacuum(strategy_group_id=authority.strategy_group_id,
            selection_spec_id=authority.selection_spec_id,for_update=True) is not None:
            raise SelectionJobConflict("Generic continuity cannot cross a Vacuum")
        now = await self.read_authority_clock_ms()
        require_generic_continuity_commit(proof,committed_at_ms=now)
        from src.trading_kernel.infrastructure.pg_signal_repository import (
            PostgresSignalRepository,
        )
        signals = PostgresSignalRepository(self._connection)
        members = tuple(cursor.exchange_instrument_id for cursor in proof.observation_cursors)
        cursors = await signals.lock_generic_close_coverage(event_spec_id=authority.event_binding.event_spec_id,
            exchange_instrument_ids=members,closed_at_ms=proof.current_final_close_time_ms)
        if cursors!=proof.observation_cursors:
            raise SelectionJobConflict("Generic continuity Observation cursor changed")
        await self._connection.execute(sa.insert(selection_session_authorities).values(
            **generic_authority_storage_values(authority)))
        await self._connection.execute(sa.insert(selection_authority_event_bindings).values(
            selection_authority_id=authority.selection_authority_id,**authority.event_binding.model_dump(mode="json")))
        changed = await self._connection.execute(sa.update(selection_authority_current).where(
            selection_authority_current.c.selection_spec_id==authority.selection_spec_id,
            selection_authority_current.c.selection_authority_id==proof.source_selection_authority_id,
            selection_authority_current.c.projection_version==expected_current_version).values(
                selection_authority_id=authority.selection_authority_id,projection_version=expected_current_version+1,
                updated_at_ms=authority.created_at_ms))
        if changed.rowcount!=1:
            raise SelectionJobConflict("Generic continuity current pointer CAS changed")
        require_generic_continuity_commit(proof,committed_at_ms=await self.read_authority_clock_ms())

    async def commit_generic_valid_empty(self, authority: GenericSelectionAuthority, *,
        entry_vacuum_id: str, expected_vacuum_version: int, expected_current_version: int | None) -> None:
        authority = GenericSelectionAuthority.model_validate(authority.model_dump())
        if not authority.blocks_new_entry:
            raise ValueError("empty commit forbids a trading Authority")
        owner = (await self._connection.execute(sa.select(strategy_entry_controls_current).where(
            strategy_entry_controls_current.c.strategy_group_id == authority.strategy_group_id).with_for_update())).mappings().one_or_none()
        control = await self.get_selection_control(authority.strategy_group_id,for_update=True)
        if owner is None or owner["entry_state"] != "enabled" or owner["control_version"] != authority.owner_control_version:
            raise SelectionJobConflict("Generic empty Owner control changed")
        first_activation = control is not None and control.selection_mode is SelectionMode.STATIC_BASELINE and (
            control.pending_selection_mode is SelectionMode.DYNAMIC_SELECTION
            and control.pending_effective_period_anchor_ms == authority.period.feature_cutoff_at_ms
            and control.pending_authorization_id == authority.activation_authorization_id
            and authority.activation_authorization_id is not None)
        if control is None or (control.selection_mode is not SelectionMode.DYNAMIC_SELECTION and not first_activation) or control.control_version+int(first_activation) != authority.selection_control_version or not self._generic_control_allows(
            control,authority.selection_spec_id,authority.selection_epoch_id,authority.period.feature_cutoff_at_ms):
            raise SelectionJobConflict("Generic empty Selection control changed")
        if first_activation and not await self.generic_activation_authorization_matches(authority):
            raise SelectionJobConflict("Generic empty activation authorization changed")
        snapshot = await self.get_generic_snapshot(authority.selection_snapshot_id)
        if snapshot.selected_members or snapshot.selection_epoch_id != authority.selection_epoch_id or (
            snapshot.feature_cutoff_at_ms != authority.period.feature_cutoff_at_ms
            or snapshot.committed_at_ms > authority.created_at_ms):
            raise SelectionJobConflict("Generic empty Snapshot differs")
        vacuum_row = (await self._connection.execute(sa.select(strategy_entry_vacuums_current).where(
            strategy_entry_vacuums_current.c.entry_vacuum_id == entry_vacuum_id).with_for_update())).mappings().one_or_none()
        vacuum = None if vacuum_row is None else _entry_vacuum_from_row(vacuum_row)
        if vacuum is None or vacuum.strategy_group_id != authority.strategy_group_id or vacuum.selection_spec_id != authority.selection_spec_id or vacuum.source_generation_id is not None or (
            vacuum.first_blocker != "NO_SELECTION_READY_MEMBERS" or vacuum.period_anchor_ms != authority.period.feature_cutoff_at_ms):
            raise SelectionJobConflict("Generic empty Vacuum differs")
        intent = (await self._connection.execute(sa.select(strategy_entry_vacuum_events.c.payload).where(
            strategy_entry_vacuum_events.c.entry_vacuum_id == entry_vacuum_id,
            strategy_entry_vacuum_events.c.payload["intended_authority_outcome"].astext == "VALID_EMPTY"
        ).order_by(strategy_entry_vacuum_events.c.event_sequence.desc()).limit(1))).scalar_one_or_none()
        if intent is None or intent.get("selection_snapshot_id") != authority.selection_snapshot_id or intent.get("intended_authority_outcome") != "VALID_EMPTY":
            raise SelectionJobConflict("Generic empty Vacuum Snapshot intent differs")
        current = (await self._connection.execute(sa.select(selection_authority_current).where(
            selection_authority_current.c.selection_spec_id == authority.selection_spec_id).with_for_update())).mappings().one_or_none()
        existing = (await self._connection.execute(sa.select(selection_session_authorities).where(
            selection_session_authorities.c.selection_authority_id == authority.selection_authority_id))).mappings().one_or_none()
        if existing is not None:
            if existing["semantic_digest"] == authority.semantic_digest and current is not None and current["selection_authority_id"] == authority.selection_authority_id and vacuum.state is StrategyEntryVacuumState.VALID_EMPTY:
                return
            raise SelectionJobConflict("Generic empty Authority identity conflict")
        if authority.activation_authorization_id is not None and not first_activation:
            raise SelectionJobConflict("Generic empty activation pending required")
        if first_activation and current is not None:
            raise SelectionJobConflict("Generic empty first activation Authority exists")
        if (None if current is None else current["projection_version"]) != expected_current_version:
            raise SelectionJobConflict("Generic empty current version changed")
        if vacuum.projection_version != expected_vacuum_version or vacuum.state is not StrategyEntryVacuumState.DRAINING_ENTRY:
            raise SelectionJobConflict("Generic empty Vacuum version changed")
        sequence = 1
        if current is not None:
            prior = (await self._connection.execute(sa.select(selection_session_authorities).where(
                selection_session_authorities.c.selection_authority_id == current["selection_authority_id"]))).mappings().one()
            if prior["period_anchor_ms"] == authority.period.feature_cutoff_at_ms:
                sequence = prior["authority_sequence"]+1
            elif prior["period_anchor_ms"] > authority.period.feature_cutoff_at_ms:
                raise SelectionJobConflict("Generic empty period is stale")
        if authority.authority_sequence != sequence:
            raise SelectionJobConflict("Generic empty sequence changed")
        await self._supersede_unfenced_generic_predecessors(snapshot,
            selection_control_version=control.control_version,superseded_at_ms=authority.created_at_ms)
        await self.mark_entry_vacuum_drained(vacuum,target_state="VALID_EMPTY",drained_at_ms=authority.created_at_ms)
        if first_activation:
            await self.activate_pending_selection_mode(strategy_group_id=authority.strategy_group_id,
                expected_control_version=control.control_version,expected_pending_mode=SelectionMode.DYNAMIC_SELECTION,
                activated_at_ms=authority.created_at_ms)
        await self._connection.execute(sa.insert(selection_session_authorities).values(**generic_authority_storage_values(authority)))
        await self._connection.execute(sa.insert(selection_authority_event_bindings).values(
            selection_authority_id=authority.selection_authority_id,**authority.event_binding.model_dump(mode="json")))
        if current is None:
            result = await self._connection.execute(pg_insert(selection_authority_current).values(
                selection_spec_id=authority.selection_spec_id,selection_authority_id=authority.selection_authority_id,
                projection_version=1,updated_at_ms=authority.created_at_ms).on_conflict_do_nothing())
        else:
            result = await self._connection.execute(sa.update(selection_authority_current).where(
                selection_authority_current.c.selection_spec_id == authority.selection_spec_id,
                selection_authority_current.c.projection_version == expected_current_version).values(
                    selection_authority_id=authority.selection_authority_id,projection_version=current["projection_version"]+1,
                    updated_at_ms=authority.created_at_ms))
        if result.rowcount != 1:
            raise SelectionJobConflict("Generic empty current CAS failed")

    async def open_generation_entry_vacuum(
        self,
        vacuum: StrategyEntryVacuum,
        *,
        expected_generation_version: int,
        worker_id: str | None = None,
        lease_epoch: int | None = None,
    ) -> None:
        if (
            vacuum.state is not StrategyEntryVacuumState.DRAINING_ENTRY
            or vacuum.source_generation_id is None
            or vacuum.projection_version != 2
        ):
            raise ValueError(
                "Generation Vacuum must include OPEN and DRAINING_ENTRY projections"
            )
        generation: MaterializationGeneration | GenericMaterializationGeneration | GenericStaticMaterializationGeneration | None
        anchor: int | None
        if vacuum.strategy_group_id != "SOR-001":
            if worker_id is None or lease_epoch is None:
                raise SelectionJobConflict("Generic Generation fence requires lease authority")
            source_mode = await self._connection.scalar(sa.select(strategy_universe_materialization_generations.c.selection_mode).where(
                strategy_universe_materialization_generations.c.materialization_generation_id==vacuum.source_generation_id))
            if source_mode=="static_baseline":
                generation = await self.mark_generic_static_materialization_generation_desired(
                    vacuum.source_generation_id,worker_id=worker_id,lease_epoch=lease_epoch,
                    expected_projection_version=expected_generation_version,desired_at_ms=vacuum.fenced_at_ms)
                anchor = generation.effective_period_anchor_ms
            else:
                initial = await self.get_generic_materialization_generation(vacuum.source_generation_id)
                if initial is None or initial.lifecycle_state is not MaterializationGenerationState.DESIRED:
                    raise SelectionJobConflict("Generic Generation is not DESIRED before fence")
                generation = await self.mark_generic_materialization_generation_desired(
                    vacuum.source_generation_id,worker_id=worker_id,lease_epoch=lease_epoch,
                    expected_projection_version=expected_generation_version,desired_at_ms=vacuum.fenced_at_ms)
                anchor = generation.period_anchor_ms
        else:
            generation = await self.get_materialization_generation(vacuum.source_generation_id,for_update=True)
            anchor = None if generation is None else generation.session_start_ms
        if (
            generation is None
            or generation.lifecycle_state
            is not MaterializationGenerationState.DESIRED
            or generation.projection_version != expected_generation_version
            or generation.strategy_group_id != vacuum.strategy_group_id
            or generation.selection_spec_id != vacuum.selection_spec_id
            or anchor != vacuum.period_anchor_ms
        ):
            raise SelectionJobConflict("Generation changed before Vacuum fence")
        await self._connection.execute(
            sa.insert(strategy_entry_vacuums_current).values(
                **vacuum.model_dump(mode="json"),
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

    async def retarget_generic_empty_vacuum(self, vacuum: StrategyEntryVacuum, *,
        selection_snapshot_id: str, expected_owner_version: int, expected_control_version: int,
    ) -> StrategyEntryVacuum:
        """New empty Desired takes over an uninterrupted fence; never grant fallback."""
        from src.trading_kernel.application.abandon_strategy_universe import (
            AbandonStrategyUniverseRequest,
        )
        from src.trading_kernel.infrastructure.pg_universe_repository import (
            PostgresStrategyUniverseRepository,
        )
        snapshot = await self.get_generic_snapshot(selection_snapshot_id)
        owner = (await self._connection.execute(sa.select(strategy_entry_controls_current).where(
            strategy_entry_controls_current.c.strategy_group_id==snapshot.strategy_group_id).with_for_update())).mappings().one_or_none()
        control = await self.get_selection_control(snapshot.strategy_group_id,for_update=True)
        if owner is None or owner["entry_state"]!="enabled" or owner["control_version"]!=expected_owner_version or (
            control is None or control.control_version!=expected_control_version
            or not self._generic_control_allows(control,snapshot.selection_spec_id,snapshot.selection_epoch_id,snapshot.feature_cutoff_at_ms)):
            raise SelectionJobConflict("Generic empty handoff Owner or Control changed")
        await self._connection.execute(sa.select(instrument_selection_specs.c.selection_spec_id).where(
            instrument_selection_specs.c.selection_spec_id==snapshot.selection_spec_id).with_for_update())
        now = await self.read_authority_clock_ms()
        latest = await self._connection.scalar(sa.select(instrument_selection_snapshots.c.selection_snapshot_id).where(
            instrument_selection_snapshots.c.selection_spec_id==snapshot.selection_spec_id,
            instrument_selection_snapshots.c.selection_epoch_id==snapshot.selection_epoch_id,
            instrument_selection_snapshots.c.eligibility_not_before_ms<=now,
        ).order_by(instrument_selection_snapshots.c.period_anchor_ms.desc()).limit(1))
        if snapshot.selected_members or latest!=selection_snapshot_id or not snapshot.effective_from_ms<=now<snapshot.expires_at_ms or snapshot.committed_at_ms>now:
            raise SelectionJobConflict("Generic empty handoff requires latest effective zero-member Snapshot")
        current = await self.get_current_entry_vacuum(strategy_group_id=snapshot.strategy_group_id,
            selection_spec_id=snapshot.selection_spec_id,for_update=True)
        if current!=vacuum or vacuum.state not in {StrategyEntryVacuumState.OPEN,StrategyEntryVacuumState.DRAINING_ENTRY,
            StrategyEntryVacuumState.RECONFIGURING,StrategyEntryVacuumState.RECOVERY_PENDING,StrategyEntryVacuumState.OWNER_PAUSED}:
            raise SelectionJobConflict("Generic empty handoff Vacuum changed")
        if vacuum.state is StrategyEntryVacuumState.OWNER_PAUSED:
            if vacuum.first_blocker!="OWNER_PAUSED" or (
                vacuum.drained_at_ms is None or vacuum.resolved_at_ms is not None
                or await self.entry_vacuum_has_drain_blockers(strategy_group_id=snapshot.strategy_group_id)
                or await self.get_next_entry_vacuum_ticket(strategy_group_id=snapshot.strategy_group_id) is not None):
                raise SelectionJobConflict("Generic empty handoff requires completed Owner Pause drain")
            complete = await self._connection.scalar(sa.select(sa.exists().where(
                strategy_entry_vacuum_events.c.entry_vacuum_id==vacuum.entry_vacuum_id,
                strategy_entry_vacuum_events.c.event_type=="OWNER_PAUSED",
                strategy_entry_vacuum_events.c.occurred_at_ms==vacuum.drained_at_ms,
                strategy_entry_vacuum_events.c.payload["entry_drain_complete"]==sa.cast(sa.literal("true"),sa.dialects.postgresql.JSONB))))
            if vacuum.source_generation_id is not None:
                complete = await self._connection.scalar(sa.text("""
                    SELECT EXISTS (
                      SELECT 1 FROM brc_strategy_universe_materialization_generations g
                      JOIN brc_strategy_entry_vacuum_events p ON p.entry_vacuum_id=:vacuum_id
                      JOIN brc_strategy_universe_materialization_events a
                        ON a.materialization_generation_id=g.materialization_generation_id
                      WHERE g.materialization_generation_id=:generation_id
                        AND g.selection_mode='dynamic_selection' AND g.lifecycle_state='ABANDONED'
                        AND g.selection_spec_id=:spec AND g.selection_epoch_id=:epoch
                        AND g.strategy_group_id=:group AND g.period_anchor_ms=:period
                        AND g.fenced_at_ms>=:fenced AND g.fenced_at_ms<=g.terminal_at_ms
                        AND g.lease_owner IS NULL AND g.lease_expires_at_ms IS NULL
                        AND p.event_type IN ('OWNER_PAUSED','OWNER_PAUSE_REQUESTED') AND p.occurred_at_ms=g.terminal_at_ms
                        AND p.payload->>'materialization_generation_id'=g.materialization_generation_id
                        AND a.event_type='ABANDONED' AND a.occurred_at_ms=g.terminal_at_ms
                        AND a.payload->>'reason_code'='owner_paused'
                        AND NOT EXISTS (SELECT 1 FROM brc_strategy_universe_versions t
                          WHERE t.materialization_generation_id=g.materialization_generation_id AND t.lifecycle_state<>'abandoned')
                        AND ((p.event_type='OWNER_PAUSED' AND g.terminal_at_ms>=:drained AND EXISTS (SELECT 1 FROM brc_strategy_entry_vacuum_events d
                          WHERE d.entry_vacuum_id=:vacuum_id AND d.event_type='ENTRY_DRAINED'
                            AND d.occurred_at_ms=:drained AND d.payload->>'target_state'='RECONFIGURING'))
                          OR (p.event_type='OWNER_PAUSE_REQUESTED' AND g.terminal_at_ms<=:drained AND EXISTS (SELECT 1 FROM brc_strategy_entry_vacuum_events d
                            WHERE d.entry_vacuum_id=:vacuum_id AND d.event_type='OWNER_PAUSED' AND d.occurred_at_ms=:drained
                              AND d.payload->'entry_drain_complete'='true'::jsonb)))
                    )
                """), {"vacuum_id":vacuum.entry_vacuum_id,"generation_id":vacuum.source_generation_id,
                    "spec":snapshot.selection_spec_id,"epoch":snapshot.selection_epoch_id,"group":snapshot.strategy_group_id,
                    "period":vacuum.period_anchor_ms,"fenced":vacuum.fenced_at_ms,"drained":vacuum.drained_at_ms})
            if not complete:
                raise SelectionJobConflict("Generic empty handoff Owner Pause completion proof missing")
        if vacuum.state is StrategyEntryVacuumState.RECOVERY_PENDING:
            origin = (await self._connection.execute(sa.select(strategy_entry_vacuum_events.c.payload).where(
                strategy_entry_vacuum_events.c.entry_vacuum_id==vacuum.entry_vacuum_id,
                strategy_entry_vacuum_events.c.event_type=="OPEN").limit(1))).scalar_one_or_none()
            prior = await self.get_current_generic_authority(snapshot.selection_spec_id,for_update=True)
            if (vacuum.source_generation_id is not None or vacuum.first_blocker!="AUTHORITY_GAP"
                or vacuum.drained_at_ms is None or vacuum.resolved_at_ms is not None
                or origin is None or origin.get("intended_outcome")!="PRE_FENCE_CONTINUITY"
                or prior is None or origin.get("source_selection_authority_id")!=prior.authority.selection_authority_id
                or prior.authority.selection_epoch_id!=snapshot.selection_epoch_id
                or await self.entry_vacuum_has_drain_blockers(strategy_group_id=snapshot.strategy_group_id)):
                raise SelectionJobConflict("Generic empty handoff gap provenance or drain changed")
        if vacuum.source_generation_id is None and vacuum.period_anchor_ms==snapshot.feature_cutoff_at_ms:
            intent = (await self._connection.execute(sa.select(strategy_entry_vacuum_events.c.payload).where(
                strategy_entry_vacuum_events.c.entry_vacuum_id==vacuum.entry_vacuum_id,
                strategy_entry_vacuum_events.c.payload["intended_authority_outcome"].astext=="VALID_EMPTY"
            ).order_by(strategy_entry_vacuum_events.c.event_sequence.desc()).limit(1))).scalar_one_or_none()
            if intent is None or intent.get("selection_snapshot_id")!=selection_snapshot_id:
                raise SelectionJobConflict("Generic empty handoff intent changed")
            return vacuum
        if snapshot.feature_cutoff_at_ms<=vacuum.period_anchor_ms:
            raise SelectionJobConflict("Generic empty handoff Snapshot is not newer")
        if vacuum.source_generation_id is not None:
            old = await self.get_generic_materialization_generation(vacuum.source_generation_id,for_update=True)
            if old is None or old.selection_spec_id!=snapshot.selection_spec_id or old.selection_epoch_id!=snapshot.selection_epoch_id or (
                old.period_anchor_ms>=snapshot.feature_cutoff_at_ms or old.fenced_at_ms is None or old.fenced_at_ms<vacuum.fenced_at_ms
                or (not (vacuum.state is StrategyEntryVacuumState.OWNER_PAUSED and old.lifecycle_state is MaterializationGenerationState.ABANDONED)
                    and (old.lifecycle_state not in {MaterializationGenerationState.MATERIALIZING,MaterializationGenerationState.STAGED,MaterializationGenerationState.FAILED_CLOSED}
                        or vacuum.state is not StrategyEntryVacuumState.RECONFIGURING)) or vacuum.drained_at_ms is None):
                raise SelectionJobConflict("Generic empty handoff requires exact drained previous Generation")
            universes = PostgresStrategyUniverseRepository(self._connection)
            targets = await universes.get_generation_universe_targets(old.materialization_generation_id,for_update=True)
            if len(targets)>1:
                raise SelectionJobConflict("Generic empty handoff target set differs")
            for target in targets:
                if target.lifecycle_state.value!="abandoned":
                    await universes.abandon(AbandonStrategyUniverseRequest(universe_version_id=target.universe_version_id,
                        reason_code="superseded_by_valid_empty",attempted_at_ms=now))
            if old.lifecycle_state not in {MaterializationGenerationState.FAILED_CLOSED,MaterializationGenerationState.ABANDONED}:
                changed = await self._connection.execute(sa.update(strategy_universe_materialization_generations).where(
                    strategy_universe_materialization_generations.c.materialization_generation_id==old.materialization_generation_id,
                    strategy_universe_materialization_generations.c.projection_version==old.projection_version).values(
                        lifecycle_state="SUPERSEDED",terminal_at_ms=now,projection_version=old.projection_version+1,lease_owner=None,lease_expires_at_ms=None))
                if changed.rowcount!=1:
                    raise SelectionJobConflict("Generic empty handoff Generation CAS changed")
            seq = int(await self._connection.scalar(sa.select(sa.func.max(strategy_universe_materialization_events.c.event_sequence)).where(
                strategy_universe_materialization_events.c.materialization_generation_id==old.materialization_generation_id)) or 0)+1
            await self._connection.execute(sa.insert(strategy_universe_materialization_events).values(
                materialization_event_id=f"materialization-event:{old.materialization_generation_id}:{seq}",materialization_generation_id=old.materialization_generation_id,
                event_sequence=seq,event_type="SUPERSEDED_BY_VALID_EMPTY",payload={"selection_snapshot_id":selection_snapshot_id,"entry_vacuum_id":vacuum.entry_vacuum_id},occurred_at_ms=now))
        retargeted = StrategyEntryVacuum.model_validate({**vacuum.model_dump(),"source_generation_id":None,
            "period_anchor_ms":snapshot.feature_cutoff_at_ms,"state":"DRAINING_ENTRY","first_blocker":"NO_SELECTION_READY_MEMBERS",
            "projection_version":vacuum.projection_version+1})
        if vacuum.state in {StrategyEntryVacuumState.RECOVERY_PENDING,StrategyEntryVacuumState.OWNER_PAUSED}:
            await self._connection.execute(sa.insert(strategy_entry_vacuum_events).values(
                entry_vacuum_event_id=f"vacuum-event:{vacuum.entry_vacuum_id}:{retargeted.projection_version}",
                entry_vacuum_id=vacuum.entry_vacuum_id,event_sequence=retargeted.projection_version,
                event_type="VALID_EMPTY_INTENT",
                payload={"selection_snapshot_id":selection_snapshot_id,
                    "intended_authority_outcome":"VALID_EMPTY","supersedes_gap":vacuum.state is StrategyEntryVacuumState.RECOVERY_PENDING,
                    "supersedes_owner_pause":vacuum.state is StrategyEntryVacuumState.OWNER_PAUSED},occurred_at_ms=now))
        changed = await self._connection.execute(sa.update(strategy_entry_vacuums_current).where(
            strategy_entry_vacuums_current.c.entry_vacuum_id==vacuum.entry_vacuum_id,
            strategy_entry_vacuums_current.c.projection_version==vacuum.projection_version).values(**retargeted.model_dump(mode="json")))
        if changed.rowcount!=1:
            raise SelectionJobConflict("Generic empty handoff Vacuum CAS changed")
        if vacuum.state not in {StrategyEntryVacuumState.RECOVERY_PENDING,StrategyEntryVacuumState.OWNER_PAUSED}:
            await self._connection.execute(sa.insert(strategy_entry_vacuum_events).values(
                entry_vacuum_event_id=f"vacuum-event:{vacuum.entry_vacuum_id}:{retargeted.projection_version}",entry_vacuum_id=vacuum.entry_vacuum_id,
                event_sequence=retargeted.projection_version,event_type="VALID_EMPTY_INTENT",
                payload={"selection_snapshot_id":selection_snapshot_id,"intended_authority_outcome":"VALID_EMPTY","previous_generation_id":vacuum.source_generation_id},occurred_at_ms=now))
        return retargeted

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
                **vacuum.model_dump(mode="json"),
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

    async def open_generic_authority_gap_vacuum(self, vacuum: StrategyEntryVacuum, *,
        source_selection_authority_id: str, expected_current_version: int) -> None:
        """Fence a provably late Generic continuity before any recovery grant."""
        if vacuum.strategy_group_id == "SOR-001" or vacuum.state is not StrategyEntryVacuumState.OPEN or (
            vacuum.source_generation_id is not None or vacuum.first_blocker != "AUTHORITY_GAP"
        ):
            raise SelectionJobConflict("Generic authority gap requires an open scoped Vacuum")
        current = await self.get_current_generic_authority(vacuum.selection_spec_id,for_update=True)
        if current is None or current.projection_version != expected_current_version or (
            current.authority.selection_authority_id != source_selection_authority_id
            or current.authority.period.feature_cutoff_at_ms >= vacuum.period_anchor_ms
            or current.authority.expires_at_ms != vacuum.period_anchor_ms + 3_600_000
        ):
            raise SelectionJobConflict("Generic authority gap source changed")
        control = await self.get_selection_control(vacuum.strategy_group_id,for_update=True)
        owner = (await self._connection.execute(sa.select(strategy_entry_controls_current).where(
            strategy_entry_controls_current.c.strategy_group_id==vacuum.strategy_group_id).with_for_update())).mappings().one_or_none()
        if control is None or control.selection_mode is not SelectionMode.DYNAMIC_SELECTION or (
            control.selection_spec_id != vacuum.selection_spec_id
            or control.selection_epoch_id != current.authority.selection_epoch_id
            or control.control_version != current.authority.selection_control_version
            or control.pending_selection_mode is not None or owner is None
            or owner["entry_state"] != "enabled"
            or owner["control_version"] != current.authority.owner_control_version
        ):
            raise SelectionJobConflict("Generic authority gap Owner or Control changed")
        if await self.get_current_entry_vacuum(strategy_group_id=vacuum.strategy_group_id,
            selection_spec_id=vacuum.selection_spec_id,for_update=True) is not None:
            raise SelectionJobConflict("Generic authority gap Vacuum already exists")
        spec = await self.get_generic_spec(vacuum.selection_spec_id)
        period = build_generic_selection_period(feature_cutoff_at_ms=vacuum.period_anchor_ms,
            cadence_hours=spec.cadence_hours)
        missed = missed_closes_at_gap_fence(period=period,fenced_at_ms=vacuum.fenced_at_ms)
        if not missed or (missed[-1]==period.scheduled_effective_at_ms
            and vacuum.fenced_at_ms<period.period_expires_at_ms):
            raise SelectionJobConflict("Generic authority gap has no missed later close")
        uncovered = uncovered_close_count_since_gap(period=period,fenced_at_ms=vacuum.fenced_at_ms)
        await self._connection.execute(sa.insert(strategy_entry_vacuums_current).values(
            **vacuum.model_dump(mode="json")))
        await self._connection.execute(sa.insert(strategy_entry_vacuum_events).values(
            entry_vacuum_event_id=f"vacuum-event:{vacuum.entry_vacuum_id}:1",
            entry_vacuum_id=vacuum.entry_vacuum_id,event_sequence=1,event_type="OPEN",
            payload={"intended_outcome":"PRE_FENCE_CONTINUITY",
                "source_selection_authority_id":source_selection_authority_id,
                "missed_close_time_ms":missed,"missed_close_count":len(missed),
                "missed_close_reason":"AUTHORITY_GAP","period_expires_at_ms":period.period_expires_at_ms,
                "uncovered_close_count":uncovered,"uncovered_last_close_time_ms":vacuum.fenced_at_ms//3_600_000*3_600_000},
            occurred_at_ms=vacuum.fenced_at_ms))

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
                **vacuum.model_dump(mode="json"),
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
            generation: MaterializationGeneration | GenericMaterializationGeneration | GenericStaticMaterializationGeneration | None
            if vacuum.strategy_group_id=="SOR-001":
                generation = await self.get_materialization_generation(vacuum.source_generation_id,for_update=True)
            else:
                mode = await self._connection.scalar(sa.select(strategy_universe_materialization_generations.c.selection_mode).where(
                    strategy_universe_materialization_generations.c.materialization_generation_id==vacuum.source_generation_id))
                if mode=="static_baseline":
                    generation = await self.get_generic_static_materialization_generation(vacuum.source_generation_id,for_update=True)
                else:
                    generation = await self.get_generic_materialization_generation(vacuum.source_generation_id,for_update=True)
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
        target_state: Literal["RECONFIGURING", "RECOVERY_PENDING", "VALID_EMPTY"],
        drained_at_ms: int,
    ) -> StrategyEntryVacuum:
        if vacuum.state is not StrategyEntryVacuumState.DRAINING_ENTRY:
            raise ValueError("Vacuum drain completion requires DRAINING_ENTRY")
        current_row = (await self._connection.execute(sa.select(strategy_entry_vacuums_current).where(
            strategy_entry_vacuums_current.c.entry_vacuum_id == vacuum.entry_vacuum_id,
        ).with_for_update())).mappings().one_or_none()
        if current_row is None or _entry_vacuum_from_row(current_row) != vacuum:
            raise SelectionJobConflict("Vacuum authority changed before drain completion")
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
                    "drained_at_ms": vacuum.drained_at_ms if vacuum.strategy_group_id!="SOR-001" and vacuum.drained_at_ms is not None else drained_at_ms,
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
        if target is StrategyEntryVacuumState.RECOVERY_PENDING and (
            vacuum.strategy_group_id == "SOR-001" or vacuum.source_generation_id is not None
            or vacuum.first_blocker != "AUTHORITY_GAP"
        ):
            raise ValueError("RECOVERY_PENDING requires generation-free Generic authority gap")
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
                drained_at_ms=drained.drained_at_ms,
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
        if target is StrategyEntryVacuumState.RECOVERY_PENDING:
            return drained
        assert vacuum.source_generation_id is not None
        generation: MaterializationGeneration | GenericMaterializationGeneration | GenericStaticMaterializationGeneration | None
        if vacuum.strategy_group_id == "SOR-001":
            generation = await self.get_materialization_generation(vacuum.source_generation_id,for_update=True)
        else:
            source_mode = await self._connection.scalar(sa.select(strategy_universe_materialization_generations.c.selection_mode).where(
                strategy_universe_materialization_generations.c.materialization_generation_id==vacuum.source_generation_id))
            if source_mode=="static_baseline":
                generation = await self.get_generic_static_materialization_generation(vacuum.source_generation_id,for_update=True)
            else:
                generation = await self.get_generic_materialization_generation(vacuum.source_generation_id,for_update=True)
        if (
            generation is None
            or generation.lifecycle_state
            is not MaterializationGenerationState.DRAINING_ENTRY
            or generation.strategy_group_id != vacuum.strategy_group_id
            or generation.selection_spec_id != vacuum.selection_spec_id
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
                **audit.model_dump(mode="json", exclude={"session_start_ms"}), period_anchor_ms=audit.session_start_ms,
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
                    selection_authority_gap_audits_current.c.period_anchor_ms
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
                    trigger_suppression_id=_trigger_suppression_id(
                        authority_gap_audit_id=audit.authority_gap_audit_id,
                        event_spec_id=item.scope.event_spec_id,
                        exchange_instrument_id=item.scope.exchange_instrument_id,
                        session_reference=item.session_reference,
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
                inserted = await self._connection.execute(
                    pg_insert(strategy_trigger_suppressions).values(
                        **suppression.model_dump(mode="json")
                    ).on_conflict_do_nothing(index_elements=[
                        "event_spec_id", "exchange_instrument_id", "session_reference",
                    ]).returning(strategy_trigger_suppressions.c.trigger_suppression_id)
                )
                if inserted.scalar_one_or_none() is None:
                    existing = (await self._connection.execute(
                        sa.select(strategy_trigger_suppressions).where(
                            strategy_trigger_suppressions.c.event_spec_id == suppression.event_spec_id,
                            strategy_trigger_suppressions.c.exchange_instrument_id == suppression.exchange_instrument_id,
                            strategy_trigger_suppressions.c.session_reference == suppression.session_reference,
                        )
                    )).mappings().one()
                    if (
                        existing["first_natural_trigger_at_ms"] != suppression.first_natural_trigger_at_ms
                        or existing["detector_semantic_digest"] != suppression.detector_semantic_digest
                        or existing["reason_code"] != suppression.reason_code
                    ):
                        raise SelectionJobConflict("trigger suppression evidence conflicts")
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
        events = (await self._connection.execute(sa.select(instrument_selection_spec_events).where(
            instrument_selection_spec_events.c.selection_spec_id == authority.selection_spec_id
        ))).mappings().all()
        pair = authority.authorized_pair
        for event in events:
            uid = None if pair is None else (
                pair.long_universe_version_id if event["position_side"] == "long" else pair.short_universe_version_id
            )
            members = tuple((await self._connection.execute(sa.select(strategy_universe_members.c.exchange_instrument_id).where(
                strategy_universe_members.c.universe_version_id == uid
            ).order_by(strategy_universe_members.c.exchange_instrument_id))).scalars()) if uid is not None else ()
            await self._connection.execute(sa.insert(selection_authority_event_bindings).values(
                selection_authority_id=authority.selection_authority_id,
                event_spec_id=event["event_spec_id"],position_side=event["position_side"],
                grant_state="ACTIVE" if uid is not None else "EMPTY",universe_version_id=uid,
                member_set_digest=selected_member_set_digest(members),
            ))
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

    async def require_generic_close_proof(self, proof: CurrentFinalCloseGrantProof) -> None:
        proof = CurrentFinalCloseGrantProof.model_validate(proof.model_dump())
        matches = await self._connection.scalar(sa.text(
            "SELECT brc_generic_close_proof_matches(:snapshot,CAST(:proof AS jsonb),:granted)"),
            {"snapshot":proof.selection_snapshot_id,"proof":proof.model_dump_json(),"granted":proof.authority_granted_at_ms})
        if matches is not True:
            raise SelectionJobConflict("Generic current-close proof differs from PostgreSQL facts")

    async def read_authority_clock_ms(self) -> int:
        # transaction_timestamp()/now() freeze at BEGIN and cannot catch an
        # activation transaction crossing the next hourly close while blocked.
        value = await self._connection.scalar(sa.text("SELECT floor(extract(epoch FROM clock_timestamp())*1000)::bigint"))
        if value is None or int(value) <= 0:
            raise SelectionJobConflict("Authority database clock is unavailable")
        return int(value)

    async def get_current_generic_authority(self, selection_spec_id: str, *,
        for_update: bool = False) -> CurrentGenericSelectionAuthority | None:
        spec = await self.get_generic_spec(selection_spec_id)
        statement = sa.select(selection_session_authorities,
            selection_authority_current.c.projection_version.label("current_projection_version")).join(
                selection_authority_current,selection_authority_current.c.selection_authority_id == selection_session_authorities.c.selection_authority_id,
            ).where(selection_authority_current.c.selection_spec_id == selection_spec_id).limit(1)
        if for_update:
            statement = statement.with_for_update(of=selection_authority_current)
        row = (await self._connection.execute(statement)).mappings().one_or_none()
        if row is None:
            return None
        bindings = tuple((await self._connection.execute(sa.select(selection_authority_event_bindings).where(
            selection_authority_event_bindings.c.selection_authority_id == row["selection_authority_id"],
        ).order_by(selection_authority_event_bindings.c.event_spec_id).limit(2))).mappings())
        authority: GenericSelectionAuthority | GenericRecoveryAuthority = (generic_authority_from_storage(dict(row),spec=spec,event_bindings=tuple(dict(binding) for binding in bindings))
            if row["recovery_grant_proof"] is None else
            generic_recovery_authority_from_storage(dict(row),spec=spec,event_bindings=tuple(dict(binding) for binding in bindings)))
        return CurrentGenericSelectionAuthority(authority=authority,projection_version=row["current_projection_version"])

    async def get_generic_recovery_authority_by_id(self, selection_authority_id: str) -> GenericRecoveryAuthority | None:
        row = (await self._connection.execute(sa.select(selection_session_authorities).where(
            selection_session_authorities.c.selection_authority_id==selection_authority_id,
            selection_session_authorities.c.recovery_grant_proof.is_not(None)).limit(1))).mappings().one_or_none()
        if row is None:
            return None
        spec = await self.get_generic_spec(row["selection_spec_id"])
        bindings = (await self._connection.execute(sa.select(selection_authority_event_bindings).where(
            selection_authority_event_bindings.c.selection_authority_id==selection_authority_id).limit(2))).mappings().all()
        return generic_recovery_authority_from_storage(dict(row),spec=spec,
            event_bindings=tuple(dict(binding) for binding in bindings))

    async def get_generic_authority_by_id(self, selection_authority_id: str) -> GenericSelectionAuthority | GenericRecoveryAuthority | None:
        row = (await self._connection.execute(sa.select(selection_session_authorities).where(
            selection_session_authorities.c.selection_authority_id==selection_authority_id).limit(1))).mappings().one_or_none()
        if row is None:
            return None
        spec = await self.get_generic_spec(row["selection_spec_id"])
        bindings = tuple((await self._connection.execute(sa.select(selection_authority_event_bindings).where(
            selection_authority_event_bindings.c.selection_authority_id==selection_authority_id).limit(2))).mappings())
        data = tuple(dict(binding) for binding in bindings)
        return (generic_recovery_authority_from_storage(dict(row),spec=spec,event_bindings=data)
            if row["recovery_grant_proof"] is not None else
            generic_authority_from_storage(dict(row),spec=spec,event_bindings=data))

    async def generic_recovery_transition_blocker(self, *, selection_spec_id: str,
        target_members: tuple[str, ...]) -> str | None:
        """Do not abandon an unarmed recovery barrier on overlapping members."""
        from src.trading_kernel.infrastructure.pg_signal_repository import (
            PostgresSignalRepository,
        )
        from src.trading_kernel.infrastructure.pg_universe_repository import (
            PostgresStrategyUniverseRepository,
        )

        current = await self.get_current_generic_authority(selection_spec_id,for_update=True)
        if current is None:
            # The first Static -> Dynamic activation has no Generic parent.
            # Its separate Owner/epoch grant proof remains mandatory.
            return None
        source = current.authority
        origin_id = (source.selection_authority_id if isinstance(source,GenericRecoveryAuthority)
            else source.continued_from_recovery_authority_id)
        if origin_id is None:
            return None
        origin = await self.get_generic_recovery_authority_by_id(origin_id)
        if origin is None or origin.selection_epoch_id!=source.selection_epoch_id or (
            origin.event_binding!=source.event_binding
            or origin.comparison_universe_id!=source.comparison_universe_id
            or origin.comparison_transition_revision!=source.comparison_transition_revision):
            return "GENERIC_RECOVERY_SOURCE_CHANGED"
        uid = source.event_binding.universe_version_id
        if uid is None:
            return "GENERIC_RECOVERY_SOURCE_CHANGED"
        previous_members = await PostgresStrategyUniverseRepository(self._connection).get_members(uid)
        overlap = tuple(sorted(set(previous_members).intersection(target_members)))
        signals = PostgresSignalRepository(self._connection)
        proof = origin.recovery_proof
        for member in overlap:
            key = build_episode_domain_key(event_spec_id=source.event_binding.event_spec_id,
                exchange_instrument_id=member,position_side=source.event_binding.position_side)
            await signals.lock_exposure_episode(key)
            checkpoint = await signals.get_authority_recovery_checkpoint(key)
            if checkpoint is None or (checkpoint.recovery_id,checkpoint.recovery_revision,
                checkpoint.effective_from_ms,checkpoint.first_eligible_close_time_ms)!=(
                proof.recovery_close_plan.recovery_id,proof.recovery_close_plan.recovery_revision,
                proof.committed_at_ms,proof.first_eligible_close_time_ms):
                return "GENERIC_RECOVERY_SOURCE_CHANGED"
            if checkpoint.state!="ARMED":
                return "GENERIC_RECOVERY_REBASE_PENDING"
        return None

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
                *selection_authority_projection_columns(),
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


def generic_authority_storage_values(authority: GenericSelectionAuthority) -> dict[str, object]:
    """Encode the shared parent row, never grant or move a current pointer."""
    authority = GenericSelectionAuthority.model_validate(authority.model_dump())
    return {
        "selection_authority_id":authority.selection_authority_id,
        "selection_spec_id":authority.selection_spec_id,
        "selection_epoch_id":authority.selection_epoch_id,
        "selection_control_version":authority.selection_control_version,
        "activation_authorization_id":authority.activation_authorization_id,
        "period_anchor_ms":authority.period.feature_cutoff_at_ms,
        "decision_boundary_ms":authority.period.scheduled_effective_at_ms,
        "authority_sequence":authority.authority_sequence,
        "selection_mode":authority.selection_mode,
        "selection_job_id":None,"selection_attempt_id":None,
        "selection_snapshot_id":authority.selection_snapshot_id,
        "continued_from_selection_authority_id":authority.continuity_source_authority_id
            if authority.authority_outcome=="PRE_FENCE_CONTINUITY" else authority.continued_from_recovery_authority_id,
        "continuity_source_kind":"SELECTION_AUTHORITY" if authority.authority_outcome=="PRE_FENCE_CONTINUITY"
            or authority.continued_from_recovery_authority_id is not None else "NONE",
        "authority_gap_audit_id":None,"materialization_generation_id":authority.materialization_generation_id,
        "owner_control_version":authority.owner_control_version,"authority_outcome":authority.authority_outcome,
        "grant_proof_kind":None if authority.blocks_new_entry else (
            "PRE_FENCE_CONTINUITY_CURRENT_CLOSE" if authority.authority_outcome=="PRE_FENCE_CONTINUITY"
            else "PRECOMMITTED_SELECTION_CURRENT_CLOSE"),
        "grant_predecessor_authority_id":None,
        "current_close_proof":None if authority.current_close_proof is None else authority.current_close_proof.model_dump(mode="json"),
        "recovery_grant_proof":None,
        "membership_freshness":None if authority.membership_freshness is None else authority.membership_freshness.model_dump(mode="json"),
        "comparison_universe_id":authority.comparison_universe_id,
        "comparison_transition_revision":authority.comparison_transition_revision,
        "effective_from_ms":authority.effective_from_ms,
        "first_eligible_close_time_ms":authority.first_eligible_close_time_ms,
        "expires_at_ms":authority.expires_at_ms,"reason_code":authority.authority_outcome,
        "semantic_digest":authority.semantic_digest,"created_at_ms":authority.created_at_ms,
    }


def generic_recovery_authority_storage_values(authority: GenericRecoveryAuthority) -> dict[str, object]:
    authority = GenericRecoveryAuthority.model_validate(authority.model_dump())
    proof = authority.recovery_proof
    period = proof.recovery_close_plan.period
    return {
        "selection_authority_id":authority.selection_authority_id,"selection_spec_id":proof.selection_spec_id,
        "selection_epoch_id":proof.selection_epoch_id,"selection_control_version":proof.selection_control_version,
        "activation_authorization_id":None,"period_anchor_ms":period.feature_cutoff_at_ms,
        "decision_boundary_ms":period.scheduled_effective_at_ms,"authority_sequence":authority.authority_sequence,
        "selection_mode":proof.selection_mode,"selection_job_id":None,"selection_attempt_id":None,
        "selection_snapshot_id":authority.selection_snapshot_id,
        "continued_from_selection_authority_id":proof.source_selection_authority_id,
        "continuity_source_kind":"STATIC_BASELINE" if proof.selection_mode=="static_baseline" else "SELECTION_AUTHORITY",
        "authority_gap_audit_id":None,"materialization_generation_id":proof.materialization_generation_id,
        "owner_control_version":proof.owner_control_version,"authority_outcome":authority.authority_outcome,
        "grant_proof_kind":"FUTURE_CLOSE_REBASE_REQUIRED","grant_predecessor_authority_id":None,
        "current_close_proof":None,"recovery_grant_proof":proof.model_dump(mode="json"),
        "membership_freshness":None if proof.membership_freshness is None else proof.membership_freshness.model_dump(mode="json"),
        "comparison_universe_id":proof.comparison_universe_id,"comparison_transition_revision":proof.comparison_transition_revision,
        "effective_from_ms":authority.effective_from_ms,"first_eligible_close_time_ms":authority.first_eligible_close_time_ms,
        "expires_at_ms":authority.expires_at_ms,"reason_code":proof.recovery_close_plan.reason,
        "semantic_digest":authority.semantic_digest,"created_at_ms":authority.created_at_ms,
    }


def generic_recovery_authority_from_storage(row: Mapping[str, object], *, spec: GenericSelectionSpecV1,
    event_bindings: tuple[Mapping[str, object], ...]) -> GenericRecoveryAuthority:
    authority = GenericRecoveryAuthority.model_validate({"selection_authority_id":row["selection_authority_id"],
        "authority_sequence":row["authority_sequence"],"authority_outcome":row["authority_outcome"],"recovery_proof":row["recovery_grant_proof"]})
    if authority.selection_spec_id!=spec.selection_spec_id or authority.recovery_proof.strategy_group_id!=spec.strategy_group_id:
        raise ValueError("Recovery Authority installed Spec differs")
    if len(event_bindings)!=1:
        raise ValueError("Recovery Authority requires one exact Event binding")
    binding = event_bindings[0]
    if binding.get("selection_authority_id",authority.selection_authority_id)!=authority.selection_authority_id or any(
        binding.get(key)!=value for key,value in authority.event_binding.model_dump(mode="json").items()):
        raise ValueError("Recovery Authority Event binding differs")
    canonical = generic_recovery_authority_storage_values(authority)
    if any(key not in row or row[key]!=value for key,value in canonical.items()):
        raise ValueError("Recovery Authority storage identity or digest differs")
    return authority


def generic_authority_from_storage(row: Mapping[str, object], *, spec: GenericSelectionSpecV1,
    event_bindings: tuple[Mapping[str, object], ...]) -> GenericSelectionAuthority:
    """Decode all authority fields and fail closed on contradictory provenance."""
    if len(event_bindings) != 1:
        raise ValueError("Generic Authority requires one exact Event binding")
    binding = event_bindings[0]
    if "selection_authority_id" in binding and binding["selection_authority_id"] != row["selection_authority_id"]:
        raise ValueError("Generic Authority Event parent differs")
    authority = GenericSelectionAuthority.model_validate({
        **{name:row[name] for name in (
            "selection_authority_id","selection_spec_id","selection_epoch_id","selection_snapshot_id",
            "materialization_generation_id","authority_sequence","owner_control_version","selection_control_version","activation_authorization_id",
            "selection_mode","authority_outcome","current_close_proof","membership_freshness",
            "comparison_universe_id","comparison_transition_revision","effective_from_ms","created_at_ms")},
        "strategy_group_id":spec.strategy_group_id,
        "continued_from_recovery_authority_id":(cast(Mapping[str, object],row["current_close_proof"]).get("origin_recovery_authority_id")
            if row["authority_outcome"]=="PRE_FENCE_CONTINUITY" else row["continued_from_selection_authority_id"]),
        "continuity_source_authority_id":(row["continued_from_selection_authority_id"]
            if row["authority_outcome"]=="PRE_FENCE_CONTINUITY" else None),
        "period":{"feature_cutoff_at_ms":row["period_anchor_ms"],"cadence_hours":spec.cadence_hours,
            "scheduled_effective_at_ms":row["decision_boundary_ms"],"period_expires_at_ms":row["expires_at_ms"]},
        "event_binding":{name:binding[name] for name in AuthorityEventBinding.model_fields},
    })
    if authority.selection_spec_id != spec.selection_spec_id:
        raise ValueError("Generic Authority installed Spec differs")
    canonical = generic_authority_storage_values(authority)
    if any(row.get(name) != value for name,value in canonical.items()):
        raise ValueError("Generic Authority storage identity or semantic digest differs")
    return authority


def _authority_values(authority: SelectionSessionAuthority) -> dict[str, object]:
    proof = authority.grant_proof
    return {
        "selection_authority_id": authority.selection_authority_id,
        "selection_spec_id": authority.selection_spec_id,
        "period_anchor_ms": authority.session_start_ms,
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
    pair = sor_authority_pair_from_bindings(row["event_bindings"])
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
        session_start_ms=int(row["period_anchor_ms"]),
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
        pending_effective_period_anchor_ms=(
            None
            if row["pending_effective_period_anchor_ms"] is None
            else int(row["pending_effective_period_anchor_ms"])
        ),
        pending_authorization_id=row["pending_authorization_id"],
        control_version=int(row["control_version"]),
        rollback_baseline_id=row["rollback_baseline_id"],
        updated_at_ms=int(row["updated_at_ms"]),
        selection_epoch_id=row["selection_epoch_id"],
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
        "period_anchor_ms": generation.session_start_ms,
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
    if row["strategy_group_id"] != "SOR-001":
        raise SelectionJobConflict("Generic Generation requires Event-set runtime decoding")
    return MaterializationGeneration(
        materialization_generation_id=str(row["materialization_generation_id"]),
        selection_spec_id=str(row["selection_spec_id"]),
        strategy_group_id=str(row["strategy_group_id"]),
        strategy_version_id=str(row["strategy_version_id"]),
        selection_mode=SelectionMode(str(row["selection_mode"])),
        selection_snapshot_id=row["selection_snapshot_id"],
        rollback_baseline_id=row["rollback_baseline_id"],
        session_start_ms=(
            None if row["period_anchor_ms"] is None else int(row["period_anchor_ms"])
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
        period_anchor_ms=int(row["period_anchor_ms"]),
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


def _trigger_suppression_id(
    *,
    authority_gap_audit_id: str,
    event_spec_id: str,
    exchange_instrument_id: str,
    session_reference: str,
) -> str:
    """Build the bounded deterministic identity for one suppressed episode."""

    identity = (
        f"{authority_gap_audit_id}\x1f{event_spec_id}\x1f"
        f"{exchange_instrument_id}\x1f{session_reference}"
    )
    return "trigger-suppression:" + sha256(identity.encode("utf-8")).hexdigest()


def _authority_gap_audit_from_row(row: RowMapping) -> AuthorityGapAudit:
    return AuthorityGapAudit(
        authority_gap_audit_id=str(row["authority_gap_audit_id"]),
        selection_spec_id=str(row["selection_spec_id"]),
        session_start_ms=int(row["period_anchor_ms"]),
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
