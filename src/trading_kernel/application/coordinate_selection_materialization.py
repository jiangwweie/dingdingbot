"""Plan and coordinate one durable Dynamic Selection materialization step."""

from __future__ import annotations

import json
from collections.abc import Callable
from enum import StrEnum
from hashlib import sha256
from typing import Protocol, TypedDict

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.application.abandon_strategy_universe import (
    AbandonStrategyUniverseRequest,
    abandon_strategy_universe,
)
from src.trading_kernel.application.advance_strategy_universe import (
    UniverseActivationOperation,
    UniverseActivationRequest,
    UniverseActivationStatus,
    advance_strategy_universe,
)
from src.trading_kernel.application.drain_strategy_entry_vacuum import (
    DrainStrategyEntryVacuumRequest,
    VacuumDrainStatus,
    drain_strategy_entry_vacuum_once,
)
from src.trading_kernel.application.install_strategy_universe import (
    UniverseInstallRequest,
    UniverseInstallStatus,
    install_strategy_universe,
)
from src.trading_kernel.application.ports import (
    GenericCloseAlreadyConsumed,
    KernelUnitOfWork,
    OwnerPolicySnapshot,
    RuntimeCapabilitySnapshot,
    SelectionPersistenceConflict,
    UnitOfWorkFactory,
)
from src.trading_kernel.domain.dynamic_selection_timing import (
    CurrentFinalCloseGrantProof,
    DynamicMembershipState,
    GenericContinuityCloseProof,
    build_current_final_close_grant_proof,
    build_dynamic_membership_freshness,
    build_generic_selection_period,
    record_dynamic_selection_miss,
)
from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.generic_materialization import (
    GenericMaterializationGeneration,
    GenericStaticMaterializationGeneration,
    MaterializationEventBaseline,
    generic_input_is_unchanged,
)
from src.trading_kernel.domain.generic_selection_core import GenericSelectionSnapshotV1
from src.trading_kernel.domain.instrument_selection import (
    HOUR_MS,
    INTERVAL_MS,
    SelectionSnapshot,
)
from src.trading_kernel.domain.orb_session_selection import (
    ORB_EVENT_SPEC_IDS,
    ORB_SELECTION_SPEC_ID,
    OrbSessionSelectionSnapshot,
    OrbStaticMaterializationSource,
    daily_authority_expires_at,
    daily_entry_interval_ms,
    daily_event_spec_ids,
    daily_first_offset_ms,
    next_daily_eligible_close,
)
from src.trading_kernel.domain.owner_control import StrategyEntryState
from src.trading_kernel.domain.selection_authority import (
    AuthorityEventBinding,
    AuthorityEventGrantState,
    AuthorityGapAudit,
    AuthorityGapAuditKind,
    AuthorityGapScope,
    AuthorityGapScopeResult,
    AuthorityGrantProof,
    AuthorityGrantProofKind,
    AuthorityOutcome,
    ContinuitySourceKind,
    CurrentSelectionAuthority,
    GenericRecoveryAuthority,
    GenericSelectionAuthority,
    MaterializationGeneration,
    MaterializationGenerationClaimStatus,
    MaterializationGenerationState,
    MaterializationTarget,
    SelectionControl,
    SelectionMode,
    SelectionSessionAuthority,
    UniverseAuthorityPair,
    build_pending_authority_gap_audit,
    complete_authority_gap_audit,
    fail_authority_gap_audit,
    selected_member_set_digest,
)
from src.trading_kernel.domain.strategy_entry_vacuum import (
    StrategyEntryVacuum,
    StrategyEntryVacuumState,
)
from src.trading_kernel.domain.strategy_registry import (
    build_registry_semantic_hash,
    strategy_contract_for,
)


class MaterializationDisposition(StrEnum):
    NOT_DUE = "NOT_DUE"
    DISABLED = "DISABLED"
    STATIC_BASELINE = "STATIC_BASELINE"
    KEEP_STATIC_PENDING_DYNAMIC = "KEEP_STATIC_PENDING_DYNAMIC"
    OWNER_PAUSED = "OWNER_PAUSED"
    PRE_FENCE_CONTINUITY = "PRE_FENCE_CONTINUITY"
    WAITING_SELECTION = "WAITING_SELECTION"
    WAITING_VACUUM = "WAITING_VACUUM"
    NO_CHANGE = "NO_CHANGE"
    VALID_EMPTY_INTENT = "VALID_EMPTY_INTENT"
    VALID_EMPTY = "VALID_EMPTY"
    GENERATION_PENDING = "GENERATION_PENDING"
    GENERATION_DESIRED = "GENERATION_DESIRED"
    GENERATION_MATERIALIZING = "GENERATION_MATERIALIZING"
    GENERATION_LEASE_HELD = "GENERATION_LEASE_HELD"
    TARGET_WARMING = "TARGET_WARMING"
    GENERATION_STAGED = "GENERATION_STAGED"
    LONG_WARMING = "LONG_WARMING"
    SHORT_WARMING = "SHORT_WARMING"
    PAIR_STAGED = "PAIR_STAGED"
    ACTIVE_NEW = "ACTIVE_NEW"
    FALLBACK_PREVIOUS = "FALLBACK_PREVIOUS"
    GAP_AUDIT_PENDING = "GAP_AUDIT_PENDING"
    GAP_AUDIT_WINDOW_EXPIRED = "GAP_AUDIT_WINDOW_EXPIRED"
    BLOCKED = "BLOCKED"


class AuthorityGapAuditWindowDisposition(StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    SESSION_EXPIRED = "SESSION_EXPIRED"


class AuthorityGapAuditWindowPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    disposition: AuthorityGapAuditWindowDisposition
    first_eligible_close_time_ms: int | None = None
    audited_through_close_time_ms: int | None = None

    @model_validator(mode="after")
    def _validate_shape(self) -> AuthorityGapAuditWindowPlan:
        times = (
            self.first_eligible_close_time_ms,
            self.audited_through_close_time_ms,
        )
        if self.disposition is AuthorityGapAuditWindowDisposition.READY:
            if any(value is None for value in times):
                raise ValueError("ready Gap Audit window requires exact closes")
        elif any(value is not None for value in times):
            raise ValueError("non-ready Gap Audit window forbids close authority")
        return self


class MaterializationPlanningFacts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    selection_spec_id: str
    strategy_group_id: str
    session_start_ms: int
    now_ms: int
    selection_mode: SelectionMode
    pending_selection_mode: SelectionMode | None
    pending_effective_session_start_ms: int | None
    owner_entry_state: StrategyEntryState
    current_long_members: tuple[str, ...]
    current_short_members: tuple[str, ...]
    snapshot: OrbSessionSelectionSnapshot | SelectionSnapshot | None
    selected_members: tuple[str, ...]
    continuity_exists: bool
    open_vacuum: bool
    previous_entry_authorized: bool = True

    @model_validator(mode="after")
    def _validate_planning_facts(self) -> MaterializationPlanningFacts:
        if not self.selection_spec_id.strip() or not self.strategy_group_id.strip():
            raise ValueError("materialization planning identity must be non-blank")
        if self.now_ms <= 0:
            raise ValueError("materialization planning time must be positive")
        if (self.pending_selection_mode is None) != (
            self.pending_effective_session_start_ms is None
        ):
            raise ValueError("pending Selection mode timing is incomplete")
        if self.snapshot is None and self.selected_members:
            raise ValueError("selected members require a committed Snapshot")
        if self.snapshot is not None and (
            self.snapshot.selection_spec_id != self.selection_spec_id
            or self.snapshot.session_start_ms != self.session_start_ms
            or len(self.selected_members) != self.snapshot.selected_count
        ):
            raise ValueError("Snapshot disposition facts are not exact")
        for members in (
            self.current_long_members,
            self.current_short_members,
            self.selected_members,
        ):
            if tuple(sorted(members)) != members or len(members) != len(set(members)):
                raise ValueError("materialization members must be canonical and unique")
        return self


class MaterializationPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    disposition: MaterializationDisposition
    first_eligible_close_time_ms: int | None = None
    requires_gap_audit: bool = False
    authority_gap_kind: AuthorityGapAuditKind | None = None
    final_authority_outcome: AuthorityOutcome | None = None

    @model_validator(mode="after")
    def _validate_plan(self) -> MaterializationPlan:
        if self.requires_gap_audit != (self.authority_gap_kind is not None):
            raise ValueError("Gap Audit plan shape is incomplete")
        return self


class CoordinateSelectionMaterializationRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    selection_spec_id: str
    strategy_group_id: str
    session_start_ms: int
    worker_id: str

    @field_validator(
        "selection_spec_id",
        "strategy_group_id",
        "worker_id",
        mode="before",
    )
    @classmethod
    def _require_request_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Materialization Coordinator identity must be non-blank")
        return normalized


class CoordinateGenericGenerationRequest(BaseModel):
    """Advance one DB-owned Generic Generation; no caller-supplied membership."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    materialization_generation_id: str
    worker_id: str

    @field_validator("materialization_generation_id", "worker_id")
    @classmethod
    def _identity(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Generic Coordinator identity must be non-blank")
        return value.strip()


class CoordinateGenericStaticRequest(BaseModel):
    """Consume a due DB Owner intent, never a caller-provided member list."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    strategy_group_id: str
    worker_id: str

    @field_validator("strategy_group_id","worker_id")
    @classmethod
    def _identity(cls,value: str) -> str:
        if not value.strip() or value!=value.strip() or len(value)>160:
            raise ValueError("Static Coordinator identity must be bounded")
        return value


class CoordinateGenericSnapshotRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    selection_snapshot_id: str
    worker_id: str

    @field_validator("selection_snapshot_id", "worker_id")
    @classmethod
    def _identity(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Generic Snapshot handoff identity must be non-blank")
        return value.strip()


class CoordinateGenericPeriodRequest(BaseModel):
    """Evaluate current-set continuity before the Selector has an outcome."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    strategy_group_id: str
    selection_spec_id: str
    period_anchor_ms: int
    worker_id: str

    @field_validator("strategy_group_id", "selection_spec_id", "worker_id")
    @classmethod
    def _bounded_identity(cls, value: str) -> str:
        if not value.strip() or value!=value.strip() or len(value)>160:
            raise ValueError("Generic continuity requires exact bounded identity")
        return value


class CoordinateSelectionMaterializationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    disposition: MaterializationDisposition
    selection_authority_id: str | None = None
    selection_snapshot_id: str | None = None
    materialization_generation_id: str | None = None
    entry_vacuum_id: str | None = None
    authority_gap_audit_id: str | None = None
    reason_code: str | None = None


class AuthorityGapAuditEvaluationRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    audit: AuthorityGapAudit
    scopes: tuple[AuthorityGapScope, ...]
    audited_through_close_time_ms: int


class AuthorityGapAuditSource(Protocol):
    async def evaluate_authority_gap(
        self,
        request: AuthorityGapAuditEvaluationRequest,
    ) -> tuple[AuthorityGapScopeResult, ...]: ...


class AuthorityGapAuditSourceIntegrityError(RuntimeError):
    """Public market path cannot prove the exact bounded audit window."""


class AuthorityGapAuditDetectorDriftError(RuntimeError):
    """The certified detector rejects an otherwise canonical audit path."""


_TRANSIENT_WARMING_BLOCKERS = frozenset(
    {
        "CERTIFICATION_MISSING",
        "CERTIFICATION_TEMPORARILY_UNAVAILABLE",
        "CERTIFICATION_STALE",
        "WARM_READINESS_MISSING",
        "WARM_READINESS_STALE",
        "LONG_WARMING",
        "SHORT_WARMING",
    }
)
_MATERIALIZATION_TIMEOUT_MS = 1_800_000
_GENERIC_TRANSIENT_WARMING_BLOCKERS = _TRANSIENT_WARMING_BLOCKERS | {
    "COMPARATIVE_PROJECTION_INCOMPLETE",
}


class OrbGapRuntimeBasis(BaseModel):
    """Current Policy and runtime identity frozen around an hourly Gap Audit."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    policy: OwnerPolicySnapshot
    capability: RuntimeCapabilitySnapshot


async def _orb_gap_runtime_basis(
    uow: KernelUnitOfWork, *, for_update: bool = False
) -> OrbGapRuntimeBasis | None:
    context = await uow.strategy_universes.resolve_install_context(
        runtime_profile_id="tiny-live-v1",
        event_id=strategy_contract_for(ORB_EVENT_SPEC_IDS[0]).event_id,
    )
    policy = await uow.entry_admission.get_owner_policy(
        context.owner_policy_id, for_update=for_update
    )
    capability = await uow.signals.get_runtime_capability(
        "exchange_commands", for_update=for_update
    )
    if policy is None or capability is None:
        return None
    return OrbGapRuntimeBasis(policy=policy, capability=capability)


def _orb_recovery_basis_digest(
    *,
    runtime: OrbGapRuntimeBasis,
    current: CurrentSelectionAuthority,
    control: SelectionControl,
    owner_control_version: int,
    pair: UniverseAuthorityPair,
) -> str:
    return canonical_digest(
        {
            "runtime": runtime.model_dump(mode="json"),
            "predecessor": current.authority.selection_authority_id,
            "selection_control": control.model_dump(mode="json"),
            "owner_control_version": owner_control_version,
            "pair": pair.model_dump(mode="json"),
        }
    )


async def _orb_current_authority_interrupted(
    uow: KernelUnitOfWork,
    *,
    runtime: OrbGapRuntimeBasis,
    current: CurrentSelectionAuthority,
    now_ms: int,
) -> bool:
    return await uow.signals.selection_authority_was_interrupted(
        strategy_group_id="SOR-1H-001",
        selection_spec_id=ORB_SELECTION_SPEC_ID,
        owner_policy_id=runtime.policy.owner_policy_id,
        after_ms=current.authority.created_at_ms,
        through_ms=now_ms,
    )


def _orb_authority_matches_current_control(
    current: CurrentSelectionAuthority,
    control: SelectionControl,
    owner_control_version: int,
    pair: UniverseAuthorityPair,
    now_ms: int,
) -> bool:
    authority = current.authority
    return bool(
        authority.selection_epoch_id == control.selection_epoch_id
        and authority.selection_control_version == control.control_version
        and authority.owner_control_version == owner_control_version
        and authority.selection_mode == control.selection_mode
        and authority.authorized_pair == pair
        and authority.effective_from_ms <= now_ms < authority.expires_at_ms
    )


def plan_authority_gap_audit_window(
    audit: AuthorityGapAudit,
    *,
    now_ms: int,
) -> AuthorityGapAuditWindowPlan:
    """Keep pre-trigger audits pending and forbid cross-session authority."""

    session_end_ms = audit.session_start_ms + 96 * INTERVAL_MS
    if now_ms >= session_end_ms:
        return AuthorityGapAuditWindowPlan(
            disposition=AuthorityGapAuditWindowDisposition.SESSION_EXPIRED
        )
    try:
        first_eligible_close = next_daily_eligible_close(
            selection_spec_id=audit.selection_spec_id,
            session_start_ms=audit.session_start_ms,
            now_ms=now_ms,
        )
    except ValueError as exc:
        if str(exc) != "NO_ELIGIBLE_CLOSE_BEFORE_SESSION_END":
            raise
        return AuthorityGapAuditWindowPlan(
            disposition=AuthorityGapAuditWindowDisposition.SESSION_EXPIRED
        )
    audited_through = first_eligible_close - daily_entry_interval_ms(
        audit.selection_spec_id
    )
    if audited_through < audit.unauthorized_from_close_time_ms and (
        audit.selection_spec_id != ORB_SELECTION_SPEC_ID
        or now_ms < audit.session_start_ms + HOUR_MS
        or first_eligible_close != audit.unauthorized_from_close_time_ms
    ):
        return AuthorityGapAuditWindowPlan(
            disposition=AuthorityGapAuditWindowDisposition.PENDING
        )
    return AuthorityGapAuditWindowPlan(
        disposition=AuthorityGapAuditWindowDisposition.READY,
        first_eligible_close_time_ms=first_eligible_close,
        audited_through_close_time_ms=audited_through,
    )


def plan_selection_materialization(
    facts: MaterializationPlanningFacts,
) -> MaterializationPlan:
    """Return the next legal pre-fence action without mutating authority."""

    decision_boundary_ms = facts.session_start_ms + 4 * INTERVAL_MS
    if facts.now_ms < decision_boundary_ms:
        return MaterializationPlan(disposition=MaterializationDisposition.NOT_DUE)
    if facts.owner_entry_state is StrategyEntryState.PAUSED:
        return MaterializationPlan(disposition=MaterializationDisposition.OWNER_PAUSED)
    if facts.selection_mode is SelectionMode.DISABLED:
        return MaterializationPlan(disposition=MaterializationDisposition.DISABLED)
    if facts.selection_spec_id==ORB_SELECTION_SPEC_ID and facts.now_ms>=facts.session_start_ms+23*HOUR_MS:
        return MaterializationPlan(disposition=MaterializationDisposition.WAITING_SELECTION)

    first_pending_dynamic = (
        facts.selection_mode is SelectionMode.STATIC_BASELINE
        and facts.pending_selection_mode is SelectionMode.DYNAMIC_SELECTION
        and facts.pending_effective_session_start_ms is not None
        and (
            facts.pending_effective_session_start_ms <= facts.session_start_ms
            if facts.selection_spec_id == ORB_SELECTION_SPEC_ID
            else facts.pending_effective_session_start_ms == facts.session_start_ms
        )
    )
    if facts.selection_mode is SelectionMode.STATIC_BASELINE and not first_pending_dynamic:
        return MaterializationPlan(
            disposition=MaterializationDisposition.STATIC_BASELINE
        )
    if facts.open_vacuum:
        return MaterializationPlan(
            disposition=MaterializationDisposition.WAITING_VACUUM
        )
    if facts.selection_spec_id == ORB_SELECTION_SPEC_ID and not facts.previous_entry_authorized:
        if facts.snapshot is None:
            return MaterializationPlan(disposition=MaterializationDisposition.WAITING_SELECTION)
        return MaterializationPlan(disposition=(MaterializationDisposition.VALID_EMPTY_INTENT
            if facts.snapshot.selected_count == 0 else MaterializationDisposition.GENERATION_PENDING))
    if first_pending_dynamic and facts.snapshot is None:
        return MaterializationPlan(
            disposition=MaterializationDisposition.KEEP_STATIC_PENDING_DYNAMIC
        )

    if (
        facts.selection_mode is SelectionMode.DYNAMIC_SELECTION
        and not facts.continuity_exists
    ):
        first_eligible = next_daily_eligible_close(
            selection_spec_id=facts.selection_spec_id,
            session_start_ms=facts.session_start_ms,
            now_ms=facts.now_ms,
        )
        late = facts.now_ms >= facts.session_start_ms + daily_first_offset_ms(
            facts.selection_spec_id
        )
        return MaterializationPlan(
            disposition=MaterializationDisposition.PRE_FENCE_CONTINUITY,
            first_eligible_close_time_ms=first_eligible,
            requires_gap_audit=late,
            authority_gap_kind=(
                AuthorityGapAuditKind.LATE_PRE_FENCE_CONTINUITY if late else None
            ),
            final_authority_outcome=AuthorityOutcome.PRE_FENCE_CONTINUITY,
        )

    if facts.snapshot is None:
        return MaterializationPlan(
            disposition=MaterializationDisposition.WAITING_SELECTION
        )
    if facts.snapshot.selected_count == 0:
        return MaterializationPlan(
            disposition=MaterializationDisposition.VALID_EMPTY_INTENT
        )
    current_pair_matches = (
        facts.current_long_members
        == facts.current_short_members
        == facts.selected_members
    )
    if current_pair_matches:
        return MaterializationPlan(
            disposition=MaterializationDisposition.NO_CHANGE,
            first_eligible_close_time_ms=next_daily_eligible_close(
                selection_spec_id=facts.selection_spec_id,
                session_start_ms=facts.session_start_ms,
                now_ms=facts.now_ms,
            ),
            final_authority_outcome=AuthorityOutcome.NO_CHANGE,
        )
    return MaterializationPlan(
        disposition=MaterializationDisposition.GENERATION_PENDING
    )


async def coordinate_selection_materialization_once(
    *,
    uow_factory: UnitOfWorkFactory,
    request: CoordinateSelectionMaterializationRequest
    | CoordinateGenericGenerationRequest
    | CoordinateGenericSnapshotRequest
    | CoordinateGenericPeriodRequest
    | CoordinateGenericStaticRequest,
    clock_ms: Callable[[], int],
) -> CoordinateSelectionMaterializationResult:
    """Advance exactly one no-network materialization state from PostgreSQL facts."""

    now_ms = clock_ms()
    if isinstance(request,CoordinateGenericStaticRequest):
        async with uow_factory() as uow:
            await uow.strategy_universes.lock_mutation()
            owner = await uow.owner_controls.get_strategy_control(request.strategy_group_id,for_update=True)
            control = await uow.instrument_selection.get_selection_control(request.strategy_group_id,for_update=True)
            if owner is None or owner.entry_state is StrategyEntryState.PAUSED:
                if owner is not None and control is not None and control.pending_selection_mode is SelectionMode.STATIC_BASELINE and control.pending_authorization_id is not None:
                    pending_id = GenericStaticMaterializationGeneration.id_for_authorization(control.pending_authorization_id)
                    paused_static = await uow.instrument_selection.get_generic_static_materialization_generation(pending_id,for_update=True)
                    if paused_static is not None and paused_static.lifecycle_state in {MaterializationGenerationState.PENDING,MaterializationGenerationState.DESIRED,
                        MaterializationGenerationState.DRAINING_ENTRY,MaterializationGenerationState.MATERIALIZING,MaterializationGenerationState.STAGED}:
                        paused_vacuum = await uow.instrument_selection.get_current_entry_vacuum(
                            strategy_group_id=request.strategy_group_id,selection_spec_id=paused_static.selection_spec_id,for_update=True)
                        if paused_vacuum is None and paused_static.lifecycle_state in {MaterializationGenerationState.PENDING,MaterializationGenerationState.DESIRED}:
                            paused_vacuum = await uow.instrument_selection.open_owner_paused_entry_vacuum(StrategyEntryVacuum(
                                entry_vacuum_id="vacuum:owner-pause:"+pending_id,
                                strategy_group_id=request.strategy_group_id,selection_spec_id=paused_static.selection_spec_id,
                                period_anchor_ms=paused_static.effective_period_anchor_ms,source_generation_id=None,
                                state=StrategyEntryVacuumState.OPEN,fenced_at_ms=now_ms,drained_at_ms=None,
                                resolved_at_ms=None,first_blocker="OWNER_PAUSED",projection_version=1))
                        if paused_vacuum is not None and paused_vacuum.state is StrategyEntryVacuumState.OPEN and paused_vacuum.first_blocker=="OWNER_PAUSED":
                            paused_vacuum = await uow.instrument_selection.mark_entry_vacuum_draining(paused_vacuum,started_at_ms=now_ms)
                        if paused_vacuum is None:
                            return _blocked("OWNER_PAUSED_VACUUM_MISSING")
                        await _abandon_generation_targets(uow=uow,generation_id=pending_id,reason_code="owner_paused",attempted_at_ms=now_ms)
                        await uow.instrument_selection.abandon_generation_for_owner_pause(
                            generation=paused_static,vacuum=paused_vacuum,paused_at_ms=now_ms)
                    elif paused_static is not None and paused_static.lifecycle_state is MaterializationGenerationState.ABANDONED:
                        paused_vacuum = await uow.instrument_selection.get_current_entry_vacuum(
                            strategy_group_id=request.strategy_group_id,selection_spec_id=paused_static.selection_spec_id,for_update=True)
                        if paused_vacuum is not None and paused_vacuum.source_generation_id in {None,pending_id} and (
                            paused_vacuum.state is StrategyEntryVacuumState.DRAINING_ENTRY and paused_vacuum.first_blocker=="OWNER_PAUSED"):
                            await drain_strategy_entry_vacuum_once(uow,DrainStrategyEntryVacuumRequest(
                                strategy_group_id=request.strategy_group_id,selection_spec_id=paused_static.selection_spec_id,now_ms=now_ms))
                return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.OWNER_PAUSED)
            if control is not None and control.selection_mode is SelectionMode.STATIC_BASELINE and control.pending_selection_mode is None:
                active_static_spec = await uow.instrument_selection.get_generic_spec(control.selection_spec_id)
                current_static = await uow.strategy_universes.get_current(active_static_spec.event_spec_id)
                if current_static is not None:
                    committed_static = await uow.instrument_selection.get_generic_static_activation_proof_for_universe(current_static.universe_version_id)
                    if committed_static is not None and committed_static.result_selection_control_version==control.control_version:
                        return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.ACTIVE_NEW,
                            materialization_generation_id=committed_static.materialization_generation_id,
                            reason_code="TERMINAL_AUTHORITY_ALREADY_COMMITTED")
            if control is None or control.pending_selection_mode is not SelectionMode.STATIC_BASELINE or (
                control.pending_effective_period_anchor_ms is None):
                return _blocked("GENERIC_STATIC_OWNER_INTENT_MISSING")
            if now_ms<control.pending_effective_period_anchor_ms+HOUR_MS:
                return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.NOT_DUE)
            if control.pending_authorization_id is None:
                return _blocked("GENERIC_STATIC_OWNER_INTENT_MISSING")
            gid = GenericStaticMaterializationGeneration.id_for_authorization(control.pending_authorization_id)
            existing_static = await uow.instrument_selection.get_generic_static_materialization_generation(gid)
            if existing_static is None:
                waiting_vacuum=await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=request.strategy_group_id,
                    selection_spec_id=control.selection_spec_id,for_update=True)
                if waiting_vacuum is not None and not await uow.strategy_universes.materialization_slot_available(gid,
                    replacing_generation_id=waiting_vacuum.source_generation_id):
                    return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.GENERATION_DESIRED,
                        materialization_generation_id=gid,entry_vacuum_id=waiting_vacuum.entry_vacuum_id,reason_code="GLOBAL_WARMING_SLOT_BUSY")
                created_static = await uow.instrument_selection.create_generic_static_materialization_generation(
                    strategy_group_id=request.strategy_group_id,created_at_ms=now_ms)
                return CoordinateSelectionMaterializationResult(disposition=(MaterializationDisposition.GENERATION_MATERIALIZING
                    if created_static.lifecycle_state is MaterializationGenerationState.MATERIALIZING else MaterializationDisposition.GENERATION_PENDING),
                    materialization_generation_id=created_static.materialization_generation_id)
            if existing_static.lifecycle_state in {MaterializationGenerationState.PENDING,MaterializationGenerationState.DESIRED,
                MaterializationGenerationState.DRAINING_ENTRY,MaterializationGenerationState.MATERIALIZING,MaterializationGenerationState.STAGED} and (
                await uow.instrument_selection.generic_generation_owner_pause_pending(gid,checked_at_ms=now_ms)):
                vacuum=await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=request.strategy_group_id,
                    selection_spec_id=existing_static.selection_spec_id,for_update=True)
                if vacuum is None:
                    return _blocked("OWNER_PAUSED_VACUUM_MISSING")
                if vacuum.state is StrategyEntryVacuumState.OPEN and vacuum.first_blocker=="OWNER_PAUSED":
                    vacuum=await uow.instrument_selection.mark_entry_vacuum_draining(vacuum,started_at_ms=now_ms)
                await _abandon_generation_targets(uow=uow,generation_id=gid,reason_code="owner_paused",attempted_at_ms=now_ms)
                await uow.instrument_selection.abandon_generation_for_owner_pause(generation=existing_static,vacuum=vacuum,paused_at_ms=now_ms)
                return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.WAITING_VACUUM,
                    materialization_generation_id=gid,entry_vacuum_id=vacuum.entry_vacuum_id,reason_code="OWNER_PAUSE_DEFERRED_CLEANUP")
            if existing_static.lifecycle_state is MaterializationGenerationState.FAILED_CLOSED:
                failed_static_vacuum = await uow.instrument_selection.get_current_entry_vacuum(
                    strategy_group_id=request.strategy_group_id,selection_spec_id=existing_static.selection_spec_id,for_update=True)
                return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.BLOCKED,
                    materialization_generation_id=gid,entry_vacuum_id=None if failed_static_vacuum is None else failed_static_vacuum.entry_vacuum_id,
                    reason_code=(failed_static_vacuum.first_blocker if failed_static_vacuum is not None
                        and failed_static_vacuum.source_generation_id==gid else "GENERIC_STATIC_RECOVERY_REQUIRED"))
            if existing_static.lifecycle_state is MaterializationGenerationState.ABANDONED:
                vacuum=await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=request.strategy_group_id,
                    selection_spec_id=existing_static.selection_spec_id,for_update=True)
                if vacuum is not None and vacuum.source_generation_id in {None,gid} and (
                    vacuum.state is StrategyEntryVacuumState.DRAINING_ENTRY and vacuum.first_blocker=="OWNER_PAUSED"):
                    drain=await drain_strategy_entry_vacuum_once(uow,DrainStrategyEntryVacuumRequest(
                        strategy_group_id=request.strategy_group_id,selection_spec_id=existing_static.selection_spec_id,now_ms=now_ms))
                    return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.WAITING_VACUUM,
                        materialization_generation_id=gid,entry_vacuum_id=vacuum.entry_vacuum_id,reason_code=drain.reason_code or drain.status.value)
                return _blocked("GENERIC_STATIC_RECOVERY_REQUIRED")
            claimed_static = await uow.instrument_selection.claim_generic_static_materialization_generation(gid,
                worker_id=request.worker_id,now_ms=now_ms,lease_duration_ms=30_000)
            if claimed_static is None:
                return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.GENERATION_LEASE_HELD,
                    materialization_generation_id=gid,reason_code="GENERIC_GENERATION_LEASE_UNAVAILABLE")
            static_failed = False
            try:
                if claimed_static.lifecycle_state in {MaterializationGenerationState.MATERIALIZING,MaterializationGenerationState.STAGED}:
                    static_spec = await uow.instrument_selection.get_generic_spec(claimed_static.selection_spec_id)
                    if claimed_static.fenced_at_ms is not None and now_ms>=claimed_static.fenced_at_ms+static_spec.materialization_timeout_ms:
                        await uow.instrument_selection.fail_generic_static_materialization_generation(gid,
                            worker_id=request.worker_id,lease_epoch=claimed_static.lease_epoch,
                            expected_projection_version=claimed_static.projection_version,reason_code="MATERIALIZATION_TIMEOUT")
                        return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.BLOCKED,
                            materialization_generation_id=gid,reason_code="MATERIALIZATION_TIMEOUT")
                if claimed_static.lifecycle_state is MaterializationGenerationState.PENDING:
                    await uow.instrument_selection.mark_generic_static_materialization_generation_desired(gid,
                        worker_id=request.worker_id,lease_epoch=claimed_static.lease_epoch,
                        expected_projection_version=claimed_static.projection_version,desired_at_ms=now_ms)
                    return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.GENERATION_DESIRED,
                        materialization_generation_id=gid)
                if claimed_static.lifecycle_state is MaterializationGenerationState.STAGED:
                    static_proof = await uow.instrument_selection.prepare_generic_static_activation_proof(gid,
                        worker_id=request.worker_id,lease_epoch=claimed_static.lease_epoch)
                    if static_proof.target_event.universe_version_id is None:
                        return _blocked("GENERIC_STATIC_ACTIVATION_TARGET_MISSING")
                    static_activated = await advance_strategy_universe(uow,UniverseActivationRequest(
                        universe_version_id=static_proof.target_event.universe_version_id,
                        attempted_at_ms=static_proof.prepared_at_ms,operation=UniverseActivationOperation.ACTIVATE_GENERIC_STATIC,
                        materialization_generation_id=gid,materialization_lease_owner=request.worker_id,
                        materialization_lease_epoch=claimed_static.lease_epoch,static_activation_proof=static_proof))
                    return CoordinateSelectionMaterializationResult(disposition=(MaterializationDisposition.ACTIVE_NEW
                        if static_activated.status is UniverseActivationStatus.ACTIVATED else MaterializationDisposition.BLOCKED),
                        materialization_generation_id=gid,reason_code=static_activated.reason_code)
                if claimed_static.lifecycle_state is MaterializationGenerationState.DESIRED:
                    if not await uow.strategy_universes.materialization_slot_available(gid):
                        return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.GENERATION_DESIRED,
                            materialization_generation_id=gid,reason_code="GLOBAL_WARMING_SLOT_BUSY")
                    static_vacuum = StrategyEntryVacuum(entry_vacuum_id="vacuum:"+gid,
                        strategy_group_id=request.strategy_group_id,selection_spec_id=claimed_static.selection_spec_id,
                        period_anchor_ms=claimed_static.effective_period_anchor_ms,source_generation_id=gid,
                        state=StrategyEntryVacuumState.DRAINING_ENTRY,fenced_at_ms=now_ms,drained_at_ms=None,
                        resolved_at_ms=None,first_blocker="ENTRY_DRAIN_REQUIRED",projection_version=2)
                    await uow.instrument_selection.open_generation_entry_vacuum(static_vacuum,
                        expected_generation_version=claimed_static.projection_version,
                        worker_id=request.worker_id,lease_epoch=claimed_static.lease_epoch)
                    return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.WAITING_VACUUM,
                        materialization_generation_id=gid,entry_vacuum_id=static_vacuum.entry_vacuum_id)
                if claimed_static.lifecycle_state is MaterializationGenerationState.DRAINING_ENTRY:
                    static_drain = await drain_strategy_entry_vacuum_once(uow,DrainStrategyEntryVacuumRequest(
                        strategy_group_id=request.strategy_group_id,selection_spec_id=claimed_static.selection_spec_id,now_ms=now_ms))
                    return CoordinateSelectionMaterializationResult(disposition=(MaterializationDisposition.GENERATION_MATERIALIZING
                        if static_drain.status is VacuumDrainStatus.ENTRY_DRAINED else MaterializationDisposition.WAITING_VACUUM),
                        materialization_generation_id=gid,entry_vacuum_id=static_drain.entry_vacuum_id,
                        reason_code=static_drain.reason_code or static_drain.status.value)
                if claimed_static.lifecycle_state is MaterializationGenerationState.MATERIALIZING:
                    materializing_static_vacuum = await uow.instrument_selection.get_current_entry_vacuum(
                        strategy_group_id=request.strategy_group_id,selection_spec_id=claimed_static.selection_spec_id,for_update=True)
                    if materializing_static_vacuum is None or materializing_static_vacuum.source_generation_id!=gid or (
                        materializing_static_vacuum.state is not StrategyEntryVacuumState.RECONFIGURING or materializing_static_vacuum.drained_at_ms is None):
                        return _blocked("GENERIC_STATIC_DRAIN_REQUIRED")
                    baseline = await uow.instrument_selection.get_generic_static_rollback_baseline(claimed_static.rollback_baseline_id)
                    static_members = await uow.strategy_universes.get_members(baseline.source_event.universe_version_id)
                    static_contract = strategy_contract_for(baseline.source_event.event_spec_id)
                    install_context = await uow.strategy_universes.resolve_install_context(runtime_profile_id="tiny-live-v1",
                        event_id=static_contract.event_id)
                    installed_static = await install_strategy_universe(uow,UniverseInstallRequest(
                        event_spec_id=baseline.source_event.event_spec_id,runtime_profile_id="tiny-live-v1",
                        owner_policy_id=install_context.owner_policy_id,exchange_instrument_ids=static_members,
                        source_kind="static_baseline",materialization_generation_id=gid,
                        expected_member_set_digest=baseline.source_event.member_set_digest,installed_at_ms=now_ms))
                    if installed_static.status is UniverseInstallStatus.WARMING_UNIVERSE_ALREADY_EXISTS:
                        return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.TARGET_WARMING,
                            materialization_generation_id=gid,reason_code="GLOBAL_WARMING_SLOT_BUSY")
                    if installed_static.universe is None:
                        return _blocked("GENERIC_STATIC_INSTALLATION_FAILED")
                    static_staged = await advance_strategy_universe(uow,UniverseActivationRequest(
                        universe_version_id=installed_static.universe.universe_version_id,attempted_at_ms=now_ms,
                        operation=UniverseActivationOperation.STAGE_DYNAMIC,materialization_generation_id=gid,
                        materialization_lease_owner=request.worker_id,materialization_lease_epoch=claimed_static.lease_epoch))
                    if static_staged.reason_code in {"CERTIFICATION_OWNER_ACTION_REQUIRED","CERTIFICATION_NOT_ELIGIBLE"}:
                        await uow.instrument_selection.fail_generic_static_materialization_generation(gid,
                            worker_id=request.worker_id,lease_epoch=claimed_static.lease_epoch,
                            expected_projection_version=claimed_static.projection_version,reason_code=static_staged.reason_code)
                        return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.BLOCKED,
                            materialization_generation_id=gid,reason_code=static_staged.reason_code)
                    static_disposition = (MaterializationDisposition.GENERATION_STAGED
                        if static_staged.status is UniverseActivationStatus.STAGED else MaterializationDisposition.TARGET_WARMING
                        if static_staged.reason_code in _GENERIC_TRANSIENT_WARMING_BLOCKERS else MaterializationDisposition.BLOCKED)
                    return CoordinateSelectionMaterializationResult(disposition=static_disposition,
                        materialization_generation_id=gid,reason_code=static_staged.reason_code)
                return _blocked("GENERIC_STATIC_TARGET_MATERIALIZATION_REQUIRED")
            except BaseException:
                static_failed = True
                raise
            finally:
                if not static_failed:
                    await uow.instrument_selection.release_generic_materialization_generation_lease(gid,
                        worker_id=request.worker_id,lease_epoch=claimed_static.lease_epoch)
    if isinstance(request, CoordinateGenericPeriodRequest):
        return await _coordinate_generic_period(uow_factory=uow_factory,request=request,now_ms=now_ms)
    if isinstance(request, CoordinateGenericSnapshotRequest):
        return await _coordinate_generic_snapshot(uow_factory=uow_factory,request=request,now_ms=now_ms)
    if isinstance(request, CoordinateGenericGenerationRequest):
        return await _coordinate_generic_generation(uow_factory=uow_factory,request=request,now_ms=now_ms)
    async with uow_factory() as uow:
        await uow.strategy_universes.lock_mutation()
        spec = await uow.instrument_selection.get_active_spec(
            request.selection_spec_id
        )
        if spec.strategy_group_id != request.strategy_group_id:
            return _blocked("MATERIALIZATION_STRATEGY_GROUP_DRIFT")
        selection_control = await uow.instrument_selection.get_selection_control(
            request.strategy_group_id,
            for_update=True,
        )
        owner_control = await uow.owner_controls.get_strategy_control(
            request.strategy_group_id,
            for_update=True,
        )
        if selection_control is None or owner_control is None:
            return _blocked("MATERIALIZATION_CONTROL_MISSING")
        if selection_control.selection_spec_id != spec.selection_spec_id:
            return _blocked("SELECTION_CONTROL_SPEC_DRIFT")

        long_current = await uow.strategy_universes.get_current(
            daily_event_spec_ids(spec.selection_spec_id)[0]
        )
        short_current = await uow.strategy_universes.get_current(
            daily_event_spec_ids(spec.selection_spec_id)[1]
        )
        if long_current is None or short_current is None:
            return _blocked("CURRENT_UNIVERSE_PAIR_MISSING")
        long_members = await uow.strategy_universes.get_members(
            long_current.universe_version_id
        )
        short_members = await uow.strategy_universes.get_members(
            short_current.universe_version_id
        )
        if (spec.selection_spec_id==ORB_SELECTION_SPEC_ID and selection_control.pending_selection_mode is SelectionMode.STATIC_BASELINE
            and selection_control.pending_effective_period_anchor_ms is not None and request.session_start_ms>=selection_control.pending_effective_period_anchor_ms
            and owner_control.entry_state is StrategyEntryState.ENABLED):
            return await _coordinate_orb_static_selection(uow=uow,request=request,control=selection_control,
                pair=UniverseAuthorityPair(long_universe_version_id=long_current.universe_version_id,short_universe_version_id=short_current.universe_version_id),
                long_members=long_members,short_members=short_members,now_ms=now_ms)
        snapshot = await uow.instrument_selection.get_snapshot_disposition(
            selection_spec_id=spec.selection_spec_id,
            session_start_ms=request.session_start_ms,
            for_update=True,
        )
        if snapshot is not None and now_ms >= snapshot.snapshot.expires_at_ms:
            return _blocked("SELECTION_SNAPSHOT_EXPIRED")
        current_authority = (
            await uow.instrument_selection.get_current_authority_projection(
                spec.selection_spec_id
            )
        )
        vacuum = await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=request.strategy_group_id,
            selection_spec_id=spec.selection_spec_id,for_update=True)
        current_pair = UniverseAuthorityPair(
            long_universe_version_id=long_current.universe_version_id,
            short_universe_version_id=short_current.universe_version_id,
        )
        if (spec.selection_spec_id == ORB_SELECTION_SPEC_ID
            and owner_control.entry_state is StrategyEntryState.ENABLED
            and vacuum is not None and vacuum.state is StrategyEntryVacuumState.OWNER_PAUSED
            and vacuum.source_generation_id is None and vacuum.drained_at_ms is not None
            and selection_control.selection_mode is SelectionMode.DYNAMIC_SELECTION):
            return await _prepare_gap_audit(uow=uow,spec_id=spec.selection_spec_id,
                session_start_ms=request.session_start_ms,long_members=long_members,short_members=short_members,
                now_ms=now_ms,gap_kind=AuthorityGapAuditKind.OWNER_PAUSE,
                source_entry_vacuum_id=vacuum.entry_vacuum_id)
        if owner_control.entry_state is StrategyEntryState.PAUSED:
            if vacuum is None:
                vacuum = await uow.instrument_selection.open_owner_paused_entry_vacuum(
                    StrategyEntryVacuum(
                        entry_vacuum_id=(
                            f"vacuum:{request.strategy_group_id}:"
                            f"{request.session_start_ms}:owner-pause:"
                            f"{owner_control.control_version}"
                        ),
                        strategy_group_id=request.strategy_group_id,
                        selection_spec_id=spec.selection_spec_id,
                        period_anchor_ms=request.session_start_ms,
                        source_generation_id=None,
                        state=StrategyEntryVacuumState.OPEN,
                        fenced_at_ms=now_ms,
                        drained_at_ms=None,
                        resolved_at_ms=None,
                        first_blocker="OWNER_PAUSED",
                        projection_version=1,
                    )
                )
            generation = None
            if vacuum is not None and vacuum.source_generation_id is not None:
                generation = await uow.instrument_selection.get_materialization_generation(
                    vacuum.source_generation_id,
                    for_update=True,
                )
                if generation is None:
                    return _blocked("OWNER_PAUSED_GENERATION_MISSING")
            else:
                generation = (
                    await uow.instrument_selection.get_current_nonterminal_materialization_generation(
                        strategy_group_id=request.strategy_group_id,
                        selection_spec_id=spec.selection_spec_id,
                        for_update=True,
                    )
                )
            if generation is not None:
                if vacuum is None:
                    return _blocked("OWNER_PAUSED_VACUUM_MISSING")
                await _abandon_generation_targets(
                    uow=uow,
                    generation_id=generation.materialization_generation_id,
                    reason_code="owner_paused",
                    attempted_at_ms=now_ms,
                )
                await uow.instrument_selection.abandon_generation_for_owner_pause(
                    generation=generation,
                    vacuum=vacuum,
                    paused_at_ms=now_ms,
                )
            if (
                current_authority is not None
                and current_authority.authority.session_start_ms
                == request.session_start_ms
                and current_authority.authority.authority_outcome
                is AuthorityOutcome.OWNER_PAUSED_NOT_MATERIALIZED
                and current_authority.authority.owner_control_version
                == owner_control.control_version
            ):
                pause_authority = current_authority.authority
                pause_unchanged = generation is None and vacuum is not None and vacuum.state is StrategyEntryVacuumState.OWNER_PAUSED
            else:
                pause_unchanged = False
                pause_authority = _build_owner_paused_authority(
                    selection_spec_id=spec.selection_spec_id,
                    session_start_ms=request.session_start_ms,
                    selection_mode=selection_control.selection_mode,
                    selection_snapshot_id=(
                        None
                        if snapshot is None
                        else snapshot.snapshot.selection_snapshot_id
                    ),
                    current_authority=current_authority,
                    owner_control_version=owner_control.control_version,
                    created_at_ms=now_ms,
                    selection_control=selection_control,
                )
                await uow.instrument_selection.add_authority_and_set_current(
                    pause_authority,
                    expected_current_version=(
                        None
                        if current_authority is None
                        else current_authority.projection_version
                    ),
                )
            return CoordinateSelectionMaterializationResult(
                disposition=MaterializationDisposition.OWNER_PAUSED,
                selection_authority_id=pause_authority.selection_authority_id,
                selection_snapshot_id=(
                    None if snapshot is None else snapshot.snapshot.selection_snapshot_id
                ),
                materialization_generation_id=(
                    None if vacuum is None else vacuum.source_generation_id
                ),
                entry_vacuum_id=None if vacuum is None else vacuum.entry_vacuum_id,
                reason_code="OWNER_PAUSED_NO_CHANGE" if pause_unchanged else "OWNER_PAUSE_PRECEDES_MATERIALIZATION",
            )
        if (
            spec.selection_spec_id == ORB_SELECTION_SPEC_ID
            and vacuum is None
            and current_authority is not None
            and current_authority.authority.session_start_ms == request.session_start_ms
            and current_authority.authority.authorized_pair == current_pair
            and current_authority.authority.authority_outcome in {
                AuthorityOutcome.ACTIVE_NEW,
                AuthorityOutcome.NO_CHANGE,
                AuthorityOutcome.FALLBACK_PREVIOUS,
                AuthorityOutcome.PRE_FENCE_CONTINUITY,
            }
        ):
            runtime = await _orb_gap_runtime_basis(uow)
            if runtime is None:
                return _blocked("ORB_GAP_RUNTIME_AUTHORITY_MISSING")
            if not _orb_authority_matches_current_control(
                current_authority, selection_control, owner_control.control_version,
                current_pair, now_ms,
            ):
                return _blocked("ORB_CURRENT_AUTHORITY_CONTROL_CHANGED")
            if await _orb_current_authority_interrupted(
                uow, runtime=runtime, current=current_authority, now_ms=now_ms
            ):
                if not runtime.policy.enabled or not runtime.policy.new_entry_submit_enabled:
                    return _blocked("GLOBAL_ENTRY_DISABLED")
                return await _prepare_gap_audit(
                    uow=uow,
                    spec_id=spec.selection_spec_id,
                    session_start_ms=request.session_start_ms,
                    long_members=long_members,
                    short_members=short_members,
                    now_ms=now_ms,
                    recovery_basis_digest=_orb_recovery_basis_digest(
                        runtime=runtime,
                        current=current_authority,
                        control=selection_control,
                        owner_control_version=owner_control.control_version,
                        pair=current_pair,
                    ),
                )
        if (
            vacuum is None
            and snapshot is not None
            and current_authority is not None
            and current_authority.authority.session_start_ms
            == request.session_start_ms
            and current_authority.authority.selection_snapshot_id
            == snapshot.snapshot.selection_snapshot_id
            and (
                (
                    current_authority.authority.authority_outcome
                    is AuthorityOutcome.VALID_EMPTY
                    and not snapshot.selected_members
                )
                or (
                    current_authority.authority.authority_outcome
                    in {
                        AuthorityOutcome.ACTIVE_NEW,
                        AuthorityOutcome.NO_CHANGE,
                        AuthorityOutcome.FALLBACK_PREVIOUS,
                    }
                    and current_authority.authority.authorized_pair == current_pair
                )
            )
        ):
            return CoordinateSelectionMaterializationResult(
                disposition=_authority_disposition(
                    current_authority.authority.authority_outcome
                ),
                selection_authority_id=(
                    current_authority.authority.selection_authority_id
                ),
                selection_snapshot_id=snapshot.snapshot.selection_snapshot_id,
                materialization_generation_id=(
                    current_authority.authority.materialization_generation_id
                ),
                reason_code="TERMINAL_AUTHORITY_ALREADY_COMMITTED",
            )
        if (
            vacuum is not None
            and vacuum.state is StrategyEntryVacuumState.OWNER_PAUSED
            and vacuum.source_generation_id is not None
            and vacuum.period_anchor_ms < request.session_start_ms
            and snapshot is not None
            and selection_control.selection_mode is SelectionMode.STATIC_BASELINE
            and selection_control.pending_selection_mode
            is SelectionMode.DYNAMIC_SELECTION
            and selection_control.pending_effective_period_anchor_ms
            == request.session_start_ms
        ):
            previous_generation = (
                await uow.instrument_selection.get_materialization_generation(
                    vacuum.source_generation_id,
                    for_update=True,
                )
            )
            if previous_generation is None:
                return _blocked("OWNER_PAUSED_GENERATION_MISSING")
            if not snapshot.selected_members:
                authority = _build_valid_empty_authority(
                    selection_spec_id=spec.selection_spec_id,
                    snapshot=snapshot.snapshot,
                    current_authority=current_authority,
                    owner_control_version=owner_control.control_version,
                    created_at_ms=now_ms,
                    selection_control=selection_control,
                )
                await uow.instrument_selection.supersede_generation_and_resolve_valid_empty(
                    previous_generation=previous_generation,
                    snapshot=snapshot.snapshot,
                    vacuum=vacuum,
                    superseded_at_ms=now_ms,
                )
                await uow.instrument_selection.add_authority_and_set_current(
                    authority,
                    expected_current_version=(
                        None
                        if current_authority is None
                        else current_authority.projection_version
                    ),
                )
                await uow.instrument_selection.activate_pending_selection_mode(
                    strategy_group_id=request.strategy_group_id,
                    expected_control_version=selection_control.control_version,
                    expected_pending_mode=SelectionMode.DYNAMIC_SELECTION,
                    activated_at_ms=now_ms,
                )
                return CoordinateSelectionMaterializationResult(
                    disposition=MaterializationDisposition.VALID_EMPTY,
                    selection_authority_id=authority.selection_authority_id,
                    selection_snapshot_id=snapshot.snapshot.selection_snapshot_id,
                    entry_vacuum_id=vacuum.entry_vacuum_id,
                    reason_code=authority.reason_code,
                )
            replacement, replacement_targets = _build_pending_generation(
                snapshot=snapshot.snapshot,
                selected_members=snapshot.selected_members,
                previous_pair=current_pair,
                created_at_ms=now_ms,
                selection_control=selection_control,
                previous_authority=None if current_authority is None else current_authority.authority,
)
            materializing = (
                await uow.instrument_selection.supersede_owner_paused_vacuum_with_generation(
                    previous_generation=previous_generation,
                    replacement_generation=replacement,
                    replacement_targets=replacement_targets,
                    vacuum=vacuum,
                    superseded_at_ms=now_ms,
                )
            )
            return CoordinateSelectionMaterializationResult(
                disposition=MaterializationDisposition.GENERATION_DESIRED,
                selection_snapshot_id=snapshot.snapshot.selection_snapshot_id,
                materialization_generation_id=(
                    materializing.materialization_generation_id
                ),
                entry_vacuum_id=vacuum.entry_vacuum_id,
                reason_code="OWNER_PAUSE_VACUUM_SUPERSEDED_BY_NEW_SELECTION",
            )
        if (
            vacuum is not None
            and vacuum.state is StrategyEntryVacuumState.RECONFIGURING
            and vacuum.source_generation_id is not None
            and vacuum.period_anchor_ms < request.session_start_ms
            and snapshot is not None
        ):
            previous_generation = (
                await uow.instrument_selection.get_materialization_generation(
                    vacuum.source_generation_id,
                    for_update=True,
                )
            )
            if previous_generation is None:
                return _blocked("SUPERSEDED_GENERATION_MISSING")
            # The Owner-Pause recovery path retargets the old drained Vacuum
            # directly to this newest Generation.  On its next cadence the
            # Vacuum still belongs to an older Session, but its source is
            # already the exact current Snapshot/Session.  That is ordinary
            # materialization progress, not another supersession.
            if (
                previous_generation.selection_snapshot_id
                == snapshot.snapshot.selection_snapshot_id
                and previous_generation.session_start_ms == request.session_start_ms
            ):
                return await _coordinate_generation_materialization(
                    uow=uow,
                    generation=previous_generation,
                    vacuum=vacuum,
                    snapshot=snapshot.snapshot,
                    selected_members=snapshot.selected_members,
                    previous_long_members=long_members,
                    previous_short_members=short_members,
                    now_ms=now_ms,
                    materialization_timeout_ms=_MATERIALIZATION_TIMEOUT_MS,
                )
            if (
                previous_generation.session_start_ms is None
                or previous_generation.session_start_ms >= request.session_start_ms
            ):
                return _blocked("SUPERSEDED_GENERATION_SESSION_CONFLICT")
            await _abandon_generation_targets(
                uow=uow,
                generation_id=previous_generation.materialization_generation_id,
                reason_code="superseded_by_newer_selection",
                attempted_at_ms=now_ms,
            )
            if not snapshot.selected_members:
                authority = _build_valid_empty_authority(
                    selection_spec_id=spec.selection_spec_id,
                    snapshot=snapshot.snapshot,
                    current_authority=current_authority,
                    owner_control_version=owner_control.control_version,
                    created_at_ms=now_ms,
                    selection_control=selection_control,
                )
                await uow.instrument_selection.supersede_generation_and_resolve_valid_empty(
                    previous_generation=previous_generation,
                    snapshot=snapshot.snapshot,
                    vacuum=vacuum,
                    superseded_at_ms=now_ms,
                )
                await uow.instrument_selection.add_authority_and_set_current(
                    authority,
                    expected_current_version=(
                        None
                        if current_authority is None
                        else current_authority.projection_version
                    ),
                )
                if (
                    selection_control.selection_mode
                    is SelectionMode.STATIC_BASELINE
                    and selection_control.pending_selection_mode
                    is SelectionMode.DYNAMIC_SELECTION
                ):
                    await uow.instrument_selection.activate_pending_selection_mode(
                        strategy_group_id=request.strategy_group_id,
                        expected_control_version=selection_control.control_version,
                        expected_pending_mode=SelectionMode.DYNAMIC_SELECTION,
                        activated_at_ms=now_ms,
                    )
                elif (
                    selection_control.selection_mode
                    is not SelectionMode.DYNAMIC_SELECTION
                ):
                    raise ValueError(
                        "VALID_EMPTY supersession requires current or pending Dynamic mode"
                    )
                return CoordinateSelectionMaterializationResult(
                    disposition=MaterializationDisposition.VALID_EMPTY,
                    selection_authority_id=authority.selection_authority_id,
                    selection_snapshot_id=snapshot.snapshot.selection_snapshot_id,
                    materialization_generation_id=(
                        previous_generation.materialization_generation_id
                    ),
                    entry_vacuum_id=vacuum.entry_vacuum_id,
                    reason_code=authority.reason_code,
                )
            replacement, replacement_targets = _build_pending_generation(
                snapshot=snapshot.snapshot,
                selected_members=snapshot.selected_members,
                previous_pair=current_pair,
                created_at_ms=now_ms,
                selection_control=selection_control,
                previous_authority=None if current_authority is None else current_authority.authority,
)
            materializing = (
                await uow.instrument_selection.supersede_generation_and_retarget_vacuum(
                    previous_generation=previous_generation,
                    replacement_generation=replacement,
                    replacement_targets=replacement_targets,
                    vacuum=vacuum,
                    superseded_at_ms=now_ms,
                )
            )
            return CoordinateSelectionMaterializationResult(
                disposition=MaterializationDisposition.GENERATION_DESIRED,
                selection_snapshot_id=snapshot.snapshot.selection_snapshot_id,
                materialization_generation_id=(
                    materializing.materialization_generation_id
                ),
                entry_vacuum_id=vacuum.entry_vacuum_id,
                reason_code="NEWEST_VALID_SELECTION_SUPERSEDED_PREVIOUS",
            )
        if (
            vacuum is not None
            and vacuum.state is StrategyEntryVacuumState.RECONFIGURING
            and vacuum.source_generation_id is not None
        ):
            generation = await uow.instrument_selection.get_materialization_generation(
                vacuum.source_generation_id,
                for_update=True,
            )
            if generation is None:
                return _blocked("VACUUM_GENERATION_MISSING")
            if snapshot is None:
                return _blocked("GENERATION_SNAPSHOT_MISSING")
            return await _coordinate_generation_materialization(
                uow=uow,
                generation=generation,
                vacuum=vacuum,
                snapshot=snapshot.snapshot,
                selected_members=snapshot.selected_members,
                previous_long_members=long_members,
                previous_short_members=short_members,
                now_ms=now_ms,
                materialization_timeout_ms=_MATERIALIZATION_TIMEOUT_MS,
            )
        continuity_exists = bool(
            current_authority
            and current_authority.authority.session_start_ms
            == request.session_start_ms
            and current_authority.authority.authority_outcome
            is AuthorityOutcome.PRE_FENCE_CONTINUITY
            and current_authority.authority.authorized_pair == current_pair
            and current_authority.authority.owner_control_version
            == owner_control.control_version
        )
        facts = MaterializationPlanningFacts(
            selection_spec_id=spec.selection_spec_id,
            strategy_group_id=spec.strategy_group_id,
            session_start_ms=request.session_start_ms,
            now_ms=now_ms,
            selection_mode=selection_control.selection_mode,
            pending_selection_mode=selection_control.pending_selection_mode,
            pending_effective_session_start_ms=(
                selection_control.pending_effective_period_anchor_ms
            ),
            owner_entry_state=owner_control.entry_state,
            current_long_members=long_members,
            current_short_members=short_members,
            snapshot=None if snapshot is None else snapshot.snapshot,
            selected_members=() if snapshot is None else snapshot.selected_members,
            continuity_exists=continuity_exists,
            open_vacuum=bool(vacuum and vacuum.blocks_new_entry),
            previous_entry_authorized=not (spec.selection_spec_id==ORB_SELECTION_SPEC_ID and current_authority is not None
                and current_authority.authority.authority_outcome is AuthorityOutcome.VALID_EMPTY),
        )
        plan = plan_selection_materialization(facts)

        if plan.disposition is MaterializationDisposition.PRE_FENCE_CONTINUITY:
            pair = current_pair
            if plan.requires_gap_audit or spec.selection_spec_id == ORB_SELECTION_SPEC_ID:
                return await _prepare_gap_audit(
                    uow=uow,
                    spec_id=spec.selection_spec_id,
                    session_start_ms=request.session_start_ms,
                    long_members=long_members,
                    short_members=short_members,
                    now_ms=now_ms,
                )
            if current_authority is None:
                return _blocked("DYNAMIC_PREDECESSOR_AUTHORITY_MISSING")
            if not _predecessor_covers_current_pair(
                predecessor=current_authority.authority,
                pair=pair,
                owner_control_version=owner_control.control_version,
                decision_boundary_ms=request.session_start_ms + 4 * INTERVAL_MS,
            ):
                return _blocked("DYNAMIC_PREDECESSOR_AUTHORITY_DRIFT")
            authority = _build_continuity_authority(
                selection_spec_id=spec.selection_spec_id,
                session_start_ms=request.session_start_ms,
                pair=pair,
                predecessor=current_authority.authority,
                owner_control_version=owner_control.control_version,
                created_at_ms=now_ms,
                selection_control=selection_control,
            )
            await uow.instrument_selection.add_authority_and_set_current(
                authority,
                expected_current_version=current_authority.projection_version,
            )
            return CoordinateSelectionMaterializationResult(
                disposition=MaterializationDisposition.PRE_FENCE_CONTINUITY,
                selection_authority_id=authority.selection_authority_id,
                reason_code=authority.reason_code,
            )

        if plan.disposition is MaterializationDisposition.NO_CHANGE:
            if snapshot is None:
                return _blocked("NO_CHANGE_SNAPSHOT_MISSING")
            pair = current_pair
            if spec.selection_spec_id == ORB_SELECTION_SPEC_ID:
                for uid in (pair.long_universe_version_id,pair.short_universe_version_id):
                    ready=await advance_strategy_universe(uow,UniverseActivationRequest(universe_version_id=uid,
                        attempted_at_ms=now_ms,operation=UniverseActivationOperation.CERTIFY_CURRENT))
                    if ready.status is not UniverseActivationStatus.ALREADY_ACTIVE:
                        return _blocked("ORB_CURRENT_PAIR_"+(ready.reason_code or "NOT_READY"))
            first_pending_dynamic = (
                selection_control.selection_mode is SelectionMode.STATIC_BASELINE
                and selection_control.pending_selection_mode
                is SelectionMode.DYNAMIC_SELECTION
            )
            if first_pending_dynamic:
                if spec.selection_spec_id == ORB_SELECTION_SPEC_ID and now_ms >= request.session_start_ms+2*HOUR_MS:
                    return await _prepare_gap_audit(uow=uow,spec_id=spec.selection_spec_id,
                        session_start_ms=request.session_start_ms,long_members=long_members,short_members=short_members,
                        now_ms=now_ms,proposed_outcome=AuthorityOutcome.NO_CHANGE,gap_kind=AuthorityGapAuditKind.LATE_NO_CHANGE)
                authority = _build_first_dynamic_no_change_authority(
                    selection_spec_id=spec.selection_spec_id,
                    session_start_ms=request.session_start_ms,
                    selection_snapshot_id=snapshot.snapshot.selection_snapshot_id,
                    pair=pair,
                    owner_control_version=owner_control.control_version,
                    current_projection=current_authority,
                    created_at_ms=now_ms,
                    selection_control=selection_control,
                )
                await uow.instrument_selection.add_authority_and_set_current(
                    authority,
                    expected_current_version=(
                        None
                        if current_authority is None
                        else current_authority.projection_version
                    ),
                )
                await uow.instrument_selection.activate_pending_selection_mode(
                    strategy_group_id=request.strategy_group_id,
                    expected_control_version=selection_control.control_version,
                    expected_pending_mode=SelectionMode.DYNAMIC_SELECTION,
                    activated_at_ms=now_ms,
                )
            else:
                if current_authority is None or not continuity_exists:
                    return await _prepare_gap_audit(
                        uow=uow,
                        spec_id=spec.selection_spec_id,
                        session_start_ms=request.session_start_ms,
                        long_members=long_members,
                        short_members=short_members,
                        now_ms=now_ms,
                        proposed_outcome=AuthorityOutcome.NO_CHANGE,
                        gap_kind=AuthorityGapAuditKind.LATE_NO_CHANGE,
                    )
                authority = _build_no_change_successor(
                    predecessor=current_authority.authority,
                    selection_snapshot_id=snapshot.snapshot.selection_snapshot_id,
                    created_at_ms=now_ms,
                )
                await uow.instrument_selection.add_authority_and_set_current(
                    authority,
                    expected_current_version=current_authority.projection_version,
                )
            return CoordinateSelectionMaterializationResult(
                disposition=MaterializationDisposition.NO_CHANGE,
                selection_authority_id=authority.selection_authority_id,
                selection_snapshot_id=snapshot.snapshot.selection_snapshot_id,
                reason_code=authority.reason_code,
            )

        if plan.disposition is MaterializationDisposition.VALID_EMPTY_INTENT:
            if snapshot is None:
                return _blocked("VALID_EMPTY_SNAPSHOT_MISSING")
            if vacuum is None:
                vacuum = StrategyEntryVacuum(
                    entry_vacuum_id=(
                        f"vacuum:{request.strategy_group_id}:"
                        f"{request.session_start_ms}:valid-empty"
                    ),
                    strategy_group_id=request.strategy_group_id,
                    selection_spec_id=spec.selection_spec_id,
                    period_anchor_ms=request.session_start_ms,
                    source_generation_id=None,
                    state=StrategyEntryVacuumState.OPEN,
                    fenced_at_ms=now_ms,
                    drained_at_ms=None,
                    resolved_at_ms=None,
                    first_blocker="NO_SELECTION_READY_MEMBERS",
                    projection_version=1,
                )
                await uow.instrument_selection.open_valid_empty_intent_vacuum(
                    vacuum,
                    selection_snapshot_id=snapshot.snapshot.selection_snapshot_id,
                )
            return CoordinateSelectionMaterializationResult(
                disposition=MaterializationDisposition.VALID_EMPTY_INTENT,
                selection_snapshot_id=snapshot.snapshot.selection_snapshot_id,
                entry_vacuum_id=vacuum.entry_vacuum_id,
                reason_code="VALID_EMPTY_PENDING_ENTRY_DRAIN",
            )

        if plan.disposition is MaterializationDisposition.GENERATION_PENDING:
            if snapshot is None:
                return _blocked("GENERATION_SNAPSHOT_MISSING")
            existing = (
                await uow.instrument_selection.get_materialization_generation_for_snapshot(
                    snapshot.snapshot.selection_snapshot_id,
                    for_update=True,
                )
            )
            if existing is None:
                generation, targets = _build_pending_generation(
                    snapshot=snapshot.snapshot,
                    selected_members=snapshot.selected_members,
                    previous_pair=current_pair,
                    created_at_ms=now_ms,
                    selection_control=selection_control,
                    previous_authority=None if current_authority is None else current_authority.authority,
)
                await uow.instrument_selection.add_pending_materialization_generation(
                    generation,
                    targets=targets,
                )
                return CoordinateSelectionMaterializationResult(
                    disposition=MaterializationDisposition.GENERATION_PENDING,
                    selection_snapshot_id=snapshot.snapshot.selection_snapshot_id,
                    materialization_generation_id=(
                        generation.materialization_generation_id
                    ),
                    reason_code="DESIRED_MEMBERS_CHANGED",
                )
            if existing.lifecycle_state is MaterializationGenerationState.PENDING:
                if (
                    existing.previous_long_universe_version_id
                    != long_current.universe_version_id
                    or existing.previous_short_universe_version_id
                    != short_current.universe_version_id
                ):
                    abandoned = await uow.instrument_selection.mark_materialization_generation_abandoned(
                        existing.materialization_generation_id,
                        expected_projection_version=existing.projection_version,
                        reason_code="GENERATION_PREVIOUS_PAIR_DRIFT",
                        abandoned_at_ms=now_ms,
                    )
                    return CoordinateSelectionMaterializationResult(
                        disposition=MaterializationDisposition.BLOCKED,
                        selection_snapshot_id=(
                            snapshot.snapshot.selection_snapshot_id
                        ),
                        materialization_generation_id=(
                            abandoned.materialization_generation_id
                        ),
                        reason_code="GENERATION_PREVIOUS_PAIR_DRIFT",
                    )
                desired = (
                    await uow.instrument_selection.mark_materialization_generation_desired(
                        existing.materialization_generation_id,
                        expected_projection_version=existing.projection_version,
                        desired_at_ms=now_ms,
                    )
                )
                return CoordinateSelectionMaterializationResult(
                    disposition=MaterializationDisposition.GENERATION_DESIRED,
                    selection_snapshot_id=snapshot.snapshot.selection_snapshot_id,
                    materialization_generation_id=(
                        desired.materialization_generation_id
                    ),
                    reason_code="GENERATION_HANDOFF_DURABLE",
                )
            if existing.lifecycle_state in {
                MaterializationGenerationState.ABANDONED,
                MaterializationGenerationState.SUPERSEDED,
                MaterializationGenerationState.FAILED_CLOSED,
            }:
                return CoordinateSelectionMaterializationResult(
                    disposition=MaterializationDisposition.BLOCKED,
                    selection_snapshot_id=snapshot.snapshot.selection_snapshot_id,
                    materialization_generation_id=(
                        existing.materialization_generation_id
                    ),
                    reason_code=f"GENERATION_{existing.lifecycle_state.value}",
                )
            if existing.lifecycle_state is MaterializationGenerationState.DESIRED:
                if not await uow.strategy_universes.materialization_slot_available(existing.materialization_generation_id):
                    return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.GENERATION_DESIRED,
                        selection_snapshot_id=snapshot.snapshot.selection_snapshot_id,
                        materialization_generation_id=existing.materialization_generation_id,reason_code="GLOBAL_WARMING_SLOT_BUSY")
                generation_vacuum = StrategyEntryVacuum(
                    entry_vacuum_id=(
                        f"vacuum:{request.strategy_group_id}:"
                        f"{request.session_start_ms}:generation"
                    ),
                    strategy_group_id=request.strategy_group_id,
                    selection_spec_id=spec.selection_spec_id,
                    period_anchor_ms=request.session_start_ms,
                    source_generation_id=existing.materialization_generation_id,
                    state=StrategyEntryVacuumState.DRAINING_ENTRY,
                    fenced_at_ms=now_ms,
                    drained_at_ms=None,
                    resolved_at_ms=None,
                    first_blocker="DESIRED_MEMBERS_CHANGED",
                    projection_version=2,
                )
                await uow.instrument_selection.open_generation_entry_vacuum(
                    generation_vacuum,
                    expected_generation_version=existing.projection_version,
                )
                return CoordinateSelectionMaterializationResult(
                    disposition=MaterializationDisposition.WAITING_VACUUM,
                    selection_snapshot_id=snapshot.snapshot.selection_snapshot_id,
                    materialization_generation_id=(
                        existing.materialization_generation_id
                    ),
                    entry_vacuum_id=generation_vacuum.entry_vacuum_id,
                    reason_code="GENERATION_ENTRY_DRAIN_STARTED",
                )
            return CoordinateSelectionMaterializationResult(
                disposition=MaterializationDisposition.GENERATION_DESIRED,
                selection_snapshot_id=snapshot.snapshot.selection_snapshot_id,
                materialization_generation_id=(
                    existing.materialization_generation_id
                ),
                reason_code=f"GENERATION_{existing.lifecycle_state.value}",
            )

        return CoordinateSelectionMaterializationResult(
            disposition=plan.disposition,
            selection_snapshot_id=(
                None if snapshot is None else snapshot.snapshot.selection_snapshot_id
            ),
            entry_vacuum_id=None if vacuum is None else vacuum.entry_vacuum_id,
        )


async def _coordinate_generic_period(*, uow_factory: UnitOfWorkFactory,
    request: CoordinateGenericPeriodRequest, now_ms: int) -> CoordinateSelectionMaterializationResult:
    async with uow_factory() as uow:
        await uow.strategy_universes.lock_mutation()
        spec = await uow.instrument_selection.get_generic_spec(request.selection_spec_id)
        if spec.strategy_group_id!=request.strategy_group_id:
            return _blocked("GENERIC_CONTINUITY_SPEC_CHANGED")
        period = build_generic_selection_period(feature_cutoff_at_ms=request.period_anchor_ms,
            cadence_hours=spec.cadence_hours)
        if not period.scheduled_effective_at_ms<=now_ms<period.period_expires_at_ms:
            return _blocked("GENERIC_CONTINUITY_NOT_DUE")
        owner = await uow.owner_controls.get_strategy_control(request.strategy_group_id,for_update=True)
        control = await uow.instrument_selection.get_selection_control(request.strategy_group_id,for_update=True)
        if owner is None or owner.entry_state is not StrategyEntryState.ENABLED or control is None or (
            control.selection_mode is not SelectionMode.DYNAMIC_SELECTION
            or control.selection_spec_id!=spec.selection_spec_id or control.selection_epoch_id is None
            or not control.permits_dynamic_period(request.period_anchor_ms)):
            return _blocked("GENERIC_CONTINUITY_OWNER_OR_MODE_BLOCKED")
        vacuum = await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=request.strategy_group_id,
            selection_spec_id=spec.selection_spec_id,for_update=True)
        if vacuum is not None:
            if vacuum.first_blocker != "AUTHORITY_GAP" or vacuum.period_anchor_ms != request.period_anchor_ms:
                return _blocked("GENERIC_CONTINUITY_VACUUM_OPEN")
            if vacuum.state in {StrategyEntryVacuumState.OPEN,StrategyEntryVacuumState.DRAINING_ENTRY}:
                drain = await drain_strategy_entry_vacuum_once(uow,DrainStrategyEntryVacuumRequest(
                    strategy_group_id=request.strategy_group_id,selection_spec_id=spec.selection_spec_id,now_ms=now_ms))
                return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.WAITING_VACUUM,
                    entry_vacuum_id=vacuum.entry_vacuum_id,reason_code=drain.reason_code or drain.status.value)
            if vacuum.state is StrategyEntryVacuumState.RECOVERY_PENDING:
                try:
                    gap_proof = await uow.instrument_selection.prepare_generic_gap_continuity_proof(
                        strategy_group_id=request.strategy_group_id,selection_spec_id=spec.selection_spec_id,
                        period_anchor_ms=request.period_anchor_ms)
                    recovered = await uow.instrument_selection.commit_generic_gap_continuity(gap_proof)
                except (SelectionPersistenceConflict,ValueError) as exc:
                    return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.WAITING_VACUUM,
                        entry_vacuum_id=vacuum.entry_vacuum_id,reason_code=str(exc))
                return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.PRE_FENCE_CONTINUITY,
                    selection_authority_id=recovered.selection_authority_id,entry_vacuum_id=vacuum.entry_vacuum_id)
            return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.WAITING_VACUUM,
                entry_vacuum_id=vacuum.entry_vacuum_id,reason_code="GENERIC_GAP_RECOVERY_PENDING")
        source = await uow.instrument_selection.get_current_generic_authority(spec.selection_spec_id,for_update=True)
        if source is None:
            return _blocked("GENERIC_CONTINUITY_SOURCE_MISSING")
        prior = source.authority
        if prior.period==period:
            if prior.authority_outcome=="PRE_FENCE_CONTINUITY":
                return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.PRE_FENCE_CONTINUITY,
                    selection_authority_id=prior.selection_authority_id,
                    reason_code="TERMINAL_AUTHORITY_ALREADY_COMMITTED")
            return _blocked("GENERIC_CONTINUITY_PERIOD_ALREADY_MATERIALIZED")
        source_fresh = (prior.recovery_proof.membership_freshness if isinstance(prior,GenericRecoveryAuthority)
            else prior.membership_freshness)
        if prior.blocks_new_entry or source_fresh is None or prior.expires_at_ms!=period.scheduled_effective_at_ms or (
            prior.selection_epoch_id!=control.selection_epoch_id
            or prior.selection_control_version!=control.control_version
            or prior.owner_control_version!=owner.control_version
            or prior.event_binding.grant_state is not AuthorityEventGrantState.ACTIVE):
            return _blocked("GENERIC_CONTINUITY_SOURCE_CHANGED")
        try:
            freshness = record_dynamic_selection_miss(current=source_fresh,missed_period=period)
        except ValueError:
            return _blocked("GENERIC_CONTINUITY_MEMBERSHIP_STALE")
        if freshness.state is not DynamicMembershipState.GRACE or not freshness.allows_new_entry_at(now_ms):
            return _blocked("GENERIC_CONTINUITY_MEMBERSHIP_STALE")
        uid = prior.event_binding.universe_version_id
        if uid is None:
            return _blocked("GENERIC_CONTINUITY_SOURCE_UNIVERSE_MISSING")
        active = await uow.strategy_universes.get_current(spec.event_spec_id)
        members = await uow.strategy_universes.get_members(uid)
        if active is None or active.universe_version_id!=uid or selected_member_set_digest(members)!=prior.event_binding.member_set_digest:
            return _blocked("GENERIC_CONTINUITY_SOURCE_UNIVERSE_CHANGED")
        comparison_id = prior.comparison_universe_id
        comparison_revision = prior.comparison_transition_revision
        if comparison_id is not None:
            comparison = await uow.instrument_selection.get_comparison_universe_binding(spec.event_spec_id,for_update=True)
            if comparison is None or comparison.comparison_universe_id!=comparison_id or (
                comparison.comparison_transition_revision!=comparison_revision):
                return _blocked("GENERIC_CONTINUITY_COMPARISON_CHANGED")
        now = await uow.instrument_selection.read_authority_clock_ms()
        certified = await advance_strategy_universe(uow,UniverseActivationRequest(
            universe_version_id=uid,attempted_at_ms=now,operation=UniverseActivationOperation.CERTIFY_CURRENT))
        if certified.status is not UniverseActivationStatus.ALREADY_ACTIVE:
            return _blocked(str(certified.reason_code))
        close = now//HOUR_MS*HOUR_MS
        if close!=period.scheduled_effective_at_ms:
            gap = StrategyEntryVacuum(entry_vacuum_id="vacuum:gap:"+canonical_digest({
                "selection_spec_id":spec.selection_spec_id,"period_anchor_ms":request.period_anchor_ms,
                "source_selection_authority_id":prior.selection_authority_id})[7:],
                strategy_group_id=request.strategy_group_id,selection_spec_id=spec.selection_spec_id,
                period_anchor_ms=request.period_anchor_ms,source_generation_id=None,
                state=StrategyEntryVacuumState.OPEN,fenced_at_ms=now,drained_at_ms=None,
                resolved_at_ms=None,first_blocker="AUTHORITY_GAP",projection_version=1)
            await uow.instrument_selection.open_generic_authority_gap_vacuum(gap,
                source_selection_authority_id=prior.selection_authority_id,
                expected_current_version=source.projection_version)
            return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.WAITING_VACUUM,
                entry_vacuum_id=gap.entry_vacuum_id,reason_code="GENERIC_CONTINUITY_LATE_REQUIRES_RECOVERY")
        origin = (prior.selection_authority_id if isinstance(prior,GenericRecoveryAuthority)
            else prior.continued_from_recovery_authority_id)
        try:
            cursors = await uow.signals.lock_generic_close_coverage(event_spec_id=spec.event_spec_id,
                exchange_instrument_ids=members,closed_at_ms=close)
            proof = GenericContinuityCloseProof(source_selection_authority_id=prior.selection_authority_id,
                source_snapshot_id=freshness.source_snapshot_id,origin_recovery_authority_id=origin,
                period=period,current_final_close_time_ms=close,
                authority_granted_at_ms=now,observation_cursors=cursors)
        except (RuntimeError,ValueError):
            return _blocked("GENERIC_CONTINUITY_CLOSE_NOT_PROVEN")
        authority = GenericSelectionAuthority(selection_authority_id="authority:continuity:"+canonical_digest({
            "selection_spec_id":spec.selection_spec_id,"proof":proof.model_dump(mode="json")})[7:],
            selection_spec_id=spec.selection_spec_id,strategy_group_id=spec.strategy_group_id,
            selection_epoch_id=control.selection_epoch_id,selection_snapshot_id=freshness.source_snapshot_id,
            authority_sequence=1,owner_control_version=owner.control_version,
            selection_control_version=control.control_version,continued_from_recovery_authority_id=origin,
            continuity_source_authority_id=prior.selection_authority_id,period=period,
            authority_outcome="PRE_FENCE_CONTINUITY",event_binding=prior.event_binding,
            current_close_proof=proof,membership_freshness=freshness,comparison_universe_id=comparison_id,
            comparison_transition_revision=comparison_revision,effective_from_ms=now,created_at_ms=now)
        await uow.instrument_selection.commit_generic_continuity(authority,
            expected_current_version=source.projection_version)
        return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.PRE_FENCE_CONTINUITY,
            selection_authority_id=authority.selection_authority_id)


async def _coordinate_generic_snapshot(*, uow_factory: UnitOfWorkFactory,
    request: CoordinateGenericSnapshotRequest, now_ms: int) -> CoordinateSelectionMaterializationResult:
    async with uow_factory() as uow:
        await uow.strategy_universes.lock_mutation()
        snapshot = await uow.instrument_selection.get_generic_snapshot(request.selection_snapshot_id)
        generation_id = GenericMaterializationGeneration.id_for_snapshot(snapshot.selection_snapshot_id)
        existing = await uow.instrument_selection.get_generic_materialization_generation(generation_id)
        if existing is None:
            owner = await uow.owner_controls.get_strategy_control(snapshot.strategy_group_id,for_update=True)
            if owner is None:
                return _blocked("MATERIALIZATION_CONTROL_MISSING")
            if owner.entry_state is StrategyEntryState.PAUSED:
                return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.OWNER_PAUSED,
                    selection_snapshot_id=snapshot.selection_snapshot_id,reason_code="OWNER_PAUSED_NO_CHANGE")
            control = await uow.instrument_selection.get_selection_control(snapshot.strategy_group_id,for_update=True)
            if control is None or control.selection_spec_id != snapshot.selection_spec_id:
                return _blocked("GENERIC_SELECTION_CONTROL_CHANGED")
            if control.selection_mode is SelectionMode.DISABLED:
                return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.DISABLED)
            if control.selection_mode is not SelectionMode.DYNAMIC_SELECTION and not (
                control.pending_selection_mode is SelectionMode.DYNAMIC_SELECTION
                and control.pending_effective_period_anchor_ms is not None
                and control.pending_effective_period_anchor_ms <= snapshot.feature_cutoff_at_ms
            ):
                return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.STATIC_BASELINE)
            if control.selection_epoch_id != snapshot.selection_epoch_id:
                return _blocked("GENERIC_SELECTION_EPOCH_CHANGED")
            if control.pending_selection_mode is SelectionMode.STATIC_BASELINE and not control.permits_dynamic_period(
                snapshot.feature_cutoff_at_ms):
                return _blocked("GENERIC_STATIC_ROLLBACK_PENDING")
            if now_ms < snapshot.effective_from_ms:
                return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.NOT_DUE)
            if now_ms >= snapshot.expires_at_ms:
                return _blocked("GENERIC_SNAPSHOT_PERIOD_EXPIRED")
            if now_ms < snapshot.committed_at_ms:
                return _blocked("GENERIC_SNAPSHOT_COMMIT_IS_FUTURE")
            prior_vacuum = await uow.instrument_selection.get_current_entry_vacuum(
                strategy_group_id=snapshot.strategy_group_id,selection_spec_id=snapshot.selection_spec_id,for_update=True)
            if prior_vacuum is None and control.selection_mode is SelectionMode.DYNAMIC_SELECTION:
                prior_authority = await uow.instrument_selection.get_current_generic_authority(
                    snapshot.selection_spec_id,for_update=True)
                if prior_authority is not None and not prior_authority.authority.blocks_new_entry and (
                    prior_authority.authority.expires_at_ms<snapshot.effective_from_ms):
                    missed_anchor = prior_authority.authority.expires_at_ms-HOUR_MS
                    missed_period = build_generic_selection_period(feature_cutoff_at_ms=missed_anchor,
                        cadence_hours=(await uow.instrument_selection.get_generic_spec(snapshot.selection_spec_id)).cadence_hours)
                    if (prior_authority.authority.selection_epoch_id!=snapshot.selection_epoch_id
                        or missed_period.period_expires_at_ms>now_ms):
                        return _blocked("GENERIC_EXPIRED_AUTHORITY_GAP_NOT_PROVEN")
                    fence_at = await uow.instrument_selection.read_authority_clock_ms()
                    gap = StrategyEntryVacuum(entry_vacuum_id="vacuum:gap:"+canonical_digest({
                        "selection_spec_id":snapshot.selection_spec_id,"period_anchor_ms":missed_anchor,
                        "source_selection_authority_id":prior_authority.authority.selection_authority_id})[7:],
                        strategy_group_id=snapshot.strategy_group_id,selection_spec_id=snapshot.selection_spec_id,
                        period_anchor_ms=missed_anchor,source_generation_id=None,state=StrategyEntryVacuumState.OPEN,
                        fenced_at_ms=fence_at,drained_at_ms=None,resolved_at_ms=None,
                        first_blocker="AUTHORITY_GAP",projection_version=1)
                    await uow.instrument_selection.open_generic_authority_gap_vacuum(gap,
                        source_selection_authority_id=prior_authority.authority.selection_authority_id,
                        expected_current_version=prior_authority.projection_version)
                    return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.WAITING_VACUUM,
                        entry_vacuum_id=gap.entry_vacuum_id,reason_code="GENERIC_EXPIRED_AUTHORITY_GAP_FENCED")
            if prior_vacuum is not None and prior_vacuum.first_blocker=="AUTHORITY_GAP" and (
                prior_vacuum.state in {StrategyEntryVacuumState.OPEN,StrategyEntryVacuumState.DRAINING_ENTRY}):
                drain = await drain_strategy_entry_vacuum_once(uow,DrainStrategyEntryVacuumRequest(
                    strategy_group_id=snapshot.strategy_group_id,selection_spec_id=snapshot.selection_spec_id,now_ms=now_ms))
                return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.WAITING_VACUUM,
                    entry_vacuum_id=prior_vacuum.entry_vacuum_id,reason_code=drain.reason_code or drain.status.value)
            if prior_vacuum is not None and prior_vacuum.source_generation_id is not None and (
                prior_vacuum.state in {StrategyEntryVacuumState.OPEN, StrategyEntryVacuumState.DRAINING_ENTRY}
                and prior_vacuum.period_anchor_ms < snapshot.feature_cutoff_at_ms):
                # Latest Desired owns subsequent warming, never the unfinished
                # ENTRY cancellation. Drain the original fence before retargeting.
                drain = await drain_strategy_entry_vacuum_once(uow, DrainStrategyEntryVacuumRequest(
                    strategy_group_id=snapshot.strategy_group_id, selection_spec_id=snapshot.selection_spec_id,
                    now_ms=now_ms))
                return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.WAITING_VACUUM,
                    entry_vacuum_id=prior_vacuum.entry_vacuum_id, reason_code=drain.reason_code or drain.status.value)
            if not snapshot.selected_members:
                return await _coordinate_generic_empty(uow=uow,snapshot=snapshot,control=control,
                    owner_control_version=owner.control_version,now_ms=now_ms)
            gap_handoff = (prior_vacuum is not None and prior_vacuum.source_generation_id is None
                and ((prior_vacuum.state is StrategyEntryVacuumState.RECOVERY_PENDING and prior_vacuum.first_blocker == "AUTHORITY_GAP")
                    or (prior_vacuum.state is StrategyEntryVacuumState.OWNER_PAUSED and prior_vacuum.first_blocker == "OWNER_PAUSED")))
            if prior_vacuum is not None and (not gap_handoff and (prior_vacuum.source_generation_id is None
                or prior_vacuum.state not in {StrategyEntryVacuumState.RECONFIGURING,StrategyEntryVacuumState.OWNER_PAUSED})
                or prior_vacuum.drained_at_ms is None or (
                    prior_vacuum.period_anchor_ms > snapshot.feature_cutoff_at_ms if gap_handoff
                    else prior_vacuum.period_anchor_ms >= snapshot.feature_cutoff_at_ms)):
                return _blocked("GENERIC_PRIOR_VACUUM_REQUIRES_SUPERSESSION")
            spec = await uow.instrument_selection.get_generic_spec(snapshot.selection_spec_id)
            current = await uow.strategy_universes.get_current(spec.event_spec_id)
            if current is None:
                return _blocked("GENERIC_PREVIOUS_UNIVERSE_MISSING")
            members = await uow.signals.get_observation_universe_members(event_spec_id=spec.event_spec_id,
                universe_version_id=current.universe_version_id)
            if members is None or members.semantic_digest != current.semantic_digest:
                return _blocked("GENERIC_PREVIOUS_UNIVERSE_CHANGED")
            comparison = None
            if snapshot.strategy_group_id in {"MPG-001", "MI-001"}:
                comparison = await uow.instrument_selection.get_comparison_universe_binding(spec.event_spec_id,for_update=True)
                if comparison is None:
                    return _blocked("GENERIC_COMPARISON_BASELINE_MISSING")
            if (prior_vacuum is None and not gap_handoff and generic_input_is_unchanged(
                snapshot,current_members=members.exchange_instrument_ids,comparison=comparison)):
                first_activation = control.selection_mode is SelectionMode.STATIC_BASELINE
                prior = await uow.instrument_selection.get_current_generic_authority(snapshot.selection_spec_id,for_update=True)
                now = await uow.instrument_selection.read_authority_clock_ms()
                if prior is not None and prior.authority.selection_snapshot_id == snapshot.selection_snapshot_id and prior.authority.authority_outcome == "NO_CHANGE":
                    if not prior.authority.effective_from_ms <= now < prior.authority.expires_at_ms or (
                        prior.authority.owner_control_version != owner.control_version
                        or prior.authority.selection_control_version != control.control_version):
                        return _blocked("GENERIC_NO_CHANGE_AUTHORITY_STALE")
                    return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.NO_CHANGE,
                        selection_snapshot_id=snapshot.selection_snapshot_id,selection_authority_id=prior.authority.selection_authority_id,
                        reason_code="TERMINAL_AUTHORITY_ALREADY_COMMITTED")
                certified = await advance_strategy_universe(uow,UniverseActivationRequest(universe_version_id=current.universe_version_id,
                    attempted_at_ms=now,operation=UniverseActivationOperation.CERTIFY_CURRENT))
                if certified.status is not UniverseActivationStatus.ALREADY_ACTIVE:
                    return _blocked(str(certified.reason_code))
                try:
                    proof = await prepare_generic_current_close_proof(uow,selection_snapshot_id=snapshot.selection_snapshot_id)
                except GenericCloseAlreadyConsumed:
                    return _blocked("GENERIC_CURRENT_CLOSE_ALREADY_CONSUMED")
                sequence = 1 if prior is None or prior.authority.period.feature_cutoff_at_ms != snapshot.feature_cutoff_at_ms else prior.authority.authority_sequence+1
                authority = GenericSelectionAuthority(selection_authority_id=f"authority:{snapshot.selection_snapshot_id}:{sequence}",
                    selection_spec_id=snapshot.selection_spec_id,strategy_group_id=snapshot.strategy_group_id,
                    selection_epoch_id=snapshot.selection_epoch_id,selection_snapshot_id=snapshot.selection_snapshot_id,
                    authority_sequence=sequence,owner_control_version=owner.control_version,selection_control_version=control.control_version+int(first_activation),
                    activation_authorization_id=control.pending_authorization_id if first_activation else None,
                    continued_from_recovery_authority_id=(None if prior is None or first_activation else
                        prior.authority.selection_authority_id if isinstance(prior.authority,GenericRecoveryAuthority) else
                        prior.authority.continued_from_recovery_authority_id),
                    period=proof.period,authority_outcome="NO_CHANGE",event_binding=AuthorityEventBinding(event_spec_id=spec.event_spec_id,
                        position_side=spec.position_side,grant_state=AuthorityEventGrantState.ACTIVE,universe_version_id=current.universe_version_id,
                        member_set_digest=snapshot.member_set_digest),current_close_proof=proof,
                    membership_freshness=build_dynamic_membership_freshness(source_snapshot_id=snapshot.selection_snapshot_id,
                        source_member_set_digest=snapshot.member_set_digest,period=proof.period),
                    comparison_universe_id=None if comparison is None else comparison.comparison_universe_id,
                    comparison_transition_revision=None if comparison is None else comparison.comparison_transition_revision,
                    effective_from_ms=proof.authority_granted_at_ms,created_at_ms=proof.authority_granted_at_ms)
                await uow.instrument_selection.commit_generic_no_change(authority,expected_current_version=None if prior is None else prior.projection_version)
                return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.NO_CHANGE,
                    selection_snapshot_id=snapshot.selection_snapshot_id,selection_authority_id=authority.selection_authority_id)
            generation = GenericMaterializationGeneration.build(snapshot=snapshot,selection_control_version=control.control_version,
                created_at_ms=now_ms,previous_events=(MaterializationEventBaseline(event_spec_id=spec.event_spec_id,
                    position_side=spec.position_side,grant_state=AuthorityEventGrantState.ACTIVE,universe_version_id=current.universe_version_id,
                    member_set_digest=selected_member_set_digest(members.exchange_instrument_ids),
                    comparison_universe_id=None if comparison is None else comparison.comparison_universe_id,
                    comparison_transition_revision=None if comparison is None else comparison.comparison_transition_revision),))
            if prior_vacuum is not None:
                if not await uow.strategy_universes.materialization_slot_available(generation_id,
                    replacing_generation_id=prior_vacuum.source_generation_id):
                    return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.GENERATION_DESIRED,
                        selection_snapshot_id=snapshot.selection_snapshot_id,entry_vacuum_id=prior_vacuum.entry_vacuum_id,
                        reason_code="GLOBAL_WARMING_SLOT_BUSY")
                if gap_handoff:
                    await uow.instrument_selection.retarget_generic_gap_vacuum_with_generation(generation,
                        entry_vacuum_id=prior_vacuum.entry_vacuum_id)
                else:
                    await uow.instrument_selection.retarget_interrupted_generic_vacuum_with_generation(generation,
                        entry_vacuum_id=prior_vacuum.entry_vacuum_id)
                return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.GENERATION_MATERIALIZING,
                    selection_snapshot_id=snapshot.selection_snapshot_id,materialization_generation_id=generation_id,
                    entry_vacuum_id=prior_vacuum.entry_vacuum_id)
            await uow.instrument_selection.add_generic_pending_materialization_generation(generation)
            return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.GENERATION_PENDING,
                selection_snapshot_id=snapshot.selection_snapshot_id,materialization_generation_id=generation_id)
    return await _coordinate_generic_generation(uow_factory=uow_factory,
        request=CoordinateGenericGenerationRequest(materialization_generation_id=generation_id,worker_id=request.worker_id),now_ms=now_ms)


async def prepare_generic_current_close_proof(uow: KernelUnitOfWork, *, selection_snapshot_id: str) -> CurrentFinalCloseGrantProof:
    """Prepare locked NORMAL coverage, not continuity proof or a trading grant.

    Caller must hold the same transaction through activation and recheck the
    wall clock immediately before commit. Recovery must not call this route.
    """
    snapshot = await uow.instrument_selection.get_generic_snapshot(selection_snapshot_id)
    spec = await uow.instrument_selection.get_generic_spec(snapshot.selection_spec_id)
    period = build_generic_selection_period(feature_cutoff_at_ms=snapshot.feature_cutoff_at_ms,cadence_hours=spec.cadence_hours)
    started = await uow.instrument_selection.read_authority_clock_ms()
    close = started//3_600_000*3_600_000
    if not period.scheduled_effective_at_ms <= close < period.period_expires_at_ms:
        raise ValueError("Generic current-close proof period is not eligible")
    if snapshot.committed_at_ms >= close:
        raise ValueError("Generic current-close proof Snapshot was not precommitted")
    cursors = await uow.signals.lock_generic_close_coverage(event_spec_id=spec.event_spec_id,
        exchange_instrument_ids=snapshot.selected_members,closed_at_ms=close)
    granted = await uow.instrument_selection.read_authority_clock_ms()
    if granted < started:
        raise ValueError("Generic current-close proof clock moved backwards")
    proof = build_current_final_close_grant_proof(selection_snapshot_id=snapshot.selection_snapshot_id,
        selection_committed_at_ms=snapshot.committed_at_ms,source_snapshot_cutoff_at_ms=snapshot.feature_cutoff_at_ms,
        period=period,current_final_close_time_ms=close,authority_granted_at_ms=granted,observation_cursors=cursors)
    await uow.instrument_selection.require_generic_close_proof(proof)
    return proof


async def _coordinate_generic_empty(*, uow: KernelUnitOfWork, snapshot: GenericSelectionSnapshotV1,
    control: SelectionControl, owner_control_version: int, now_ms: int) -> CoordinateSelectionMaterializationResult:
    current = await uow.instrument_selection.get_current_generic_authority(snapshot.selection_spec_id,for_update=True)
    if current is not None and current.authority.selection_snapshot_id == snapshot.selection_snapshot_id and current.authority.blocks_new_entry:
        return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.VALID_EMPTY,
            selection_snapshot_id=snapshot.selection_snapshot_id,selection_authority_id=current.authority.selection_authority_id)
    vacuum = await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=snapshot.strategy_group_id,
        selection_spec_id=snapshot.selection_spec_id,for_update=True)
    vacuum_id = "vacuum:empty:"+snapshot.selection_snapshot_id
    if vacuum is None:
        vacuum = StrategyEntryVacuum(entry_vacuum_id=vacuum_id,strategy_group_id=snapshot.strategy_group_id,
            selection_spec_id=snapshot.selection_spec_id,period_anchor_ms=snapshot.feature_cutoff_at_ms,
            source_generation_id=None,state=StrategyEntryVacuumState.OPEN,fenced_at_ms=now_ms,
            drained_at_ms=None,resolved_at_ms=None,first_blocker="NO_SELECTION_READY_MEMBERS",projection_version=1)
        await uow.instrument_selection.open_valid_empty_intent_vacuum(vacuum,selection_snapshot_id=snapshot.selection_snapshot_id)
    if vacuum.entry_vacuum_id != vacuum_id or vacuum.source_generation_id is not None:
        if vacuum.source_generation_id is not None and vacuum.state is StrategyEntryVacuumState.DRAINING_ENTRY:
            drain = await drain_strategy_entry_vacuum_once(uow,DrainStrategyEntryVacuumRequest(
                strategy_group_id=snapshot.strategy_group_id,selection_spec_id=snapshot.selection_spec_id,now_ms=now_ms))
            return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.WAITING_VACUUM,
                entry_vacuum_id=vacuum.entry_vacuum_id,reason_code=drain.reason_code or drain.status.value)
        if vacuum.state not in {StrategyEntryVacuumState.OPEN,StrategyEntryVacuumState.DRAINING_ENTRY,
            StrategyEntryVacuumState.RECONFIGURING,StrategyEntryVacuumState.RECOVERY_PENDING,StrategyEntryVacuumState.OWNER_PAUSED}:
            return _blocked("GENERIC_EMPTY_REQUIRES_SUPERSESSION")
        vacuum = await uow.instrument_selection.retarget_generic_empty_vacuum(vacuum,selection_snapshot_id=snapshot.selection_snapshot_id,
            expected_owner_version=owner_control_version,expected_control_version=control.control_version)
        vacuum_id = vacuum.entry_vacuum_id
        now_ms = await uow.instrument_selection.read_authority_clock_ms()
    if vacuum.state is StrategyEntryVacuumState.OPEN:
        await uow.instrument_selection.mark_entry_vacuum_draining(vacuum,started_at_ms=now_ms)
        return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.WAITING_VACUUM,
            selection_snapshot_id=snapshot.selection_snapshot_id,entry_vacuum_id=vacuum_id)
    if vacuum.state is not StrategyEntryVacuumState.DRAINING_ENTRY:
        return _blocked("GENERIC_EMPTY_VACUUM_STATE_CHANGED")
    if await uow.instrument_selection.get_next_entry_vacuum_ticket(strategy_group_id=snapshot.strategy_group_id) is not None:
        drain = await drain_strategy_entry_vacuum_once(uow,DrainStrategyEntryVacuumRequest(
            strategy_group_id=snapshot.strategy_group_id,selection_spec_id=snapshot.selection_spec_id,now_ms=now_ms))
        return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.WAITING_VACUUM,
            entry_vacuum_id=vacuum_id,reason_code=drain.reason_code or drain.status.value)
    if await uow.instrument_selection.entry_vacuum_has_drain_blockers(strategy_group_id=snapshot.strategy_group_id):
        return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.WAITING_VACUUM,
            entry_vacuum_id=vacuum_id,reason_code="ENTRY_DRAIN_BLOCKED")
    spec = await uow.instrument_selection.get_generic_spec(snapshot.selection_spec_id)
    sequence = 1 if current is None or current.authority.period.feature_cutoff_at_ms != snapshot.feature_cutoff_at_ms else current.authority.authority_sequence+1
    first_activation = control.selection_mode is SelectionMode.STATIC_BASELINE
    authority = GenericSelectionAuthority(selection_authority_id=f"authority:{snapshot.selection_snapshot_id}:{sequence}",
        selection_spec_id=snapshot.selection_spec_id,strategy_group_id=snapshot.strategy_group_id,
        selection_epoch_id=snapshot.selection_epoch_id,selection_snapshot_id=snapshot.selection_snapshot_id,
        authority_sequence=sequence,owner_control_version=owner_control_version,selection_control_version=control.control_version+int(first_activation),
        activation_authorization_id=control.pending_authorization_id if first_activation else None,
        period=build_generic_selection_period(feature_cutoff_at_ms=snapshot.feature_cutoff_at_ms,cadence_hours=spec.cadence_hours),
        authority_outcome="VALID_EMPTY",event_binding=AuthorityEventBinding.empty(event_spec_id=spec.event_spec_id,position_side=spec.position_side),
        current_close_proof=None,membership_freshness=None,effective_from_ms=now_ms,created_at_ms=now_ms)
    await uow.instrument_selection.commit_generic_valid_empty(authority,entry_vacuum_id=vacuum_id,
        expected_vacuum_version=vacuum.projection_version,expected_current_version=None if current is None else current.projection_version)
    return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.VALID_EMPTY,
        selection_snapshot_id=snapshot.selection_snapshot_id,selection_authority_id=authority.selection_authority_id,entry_vacuum_id=vacuum_id)


async def _coordinate_generic_generation(*, uow_factory: UnitOfWorkFactory,
    request: CoordinateGenericGenerationRequest, now_ms: int) -> CoordinateSelectionMaterializationResult:
    async with uow_factory() as uow:
        await uow.strategy_universes.lock_mutation()
        initial = await uow.instrument_selection.get_generic_materialization_generation(request.materialization_generation_id)
        if initial is None:
            return _blocked("GENERIC_GENERATION_MISSING")
        owner = await uow.owner_controls.get_strategy_control(initial.strategy_group_id,for_update=True)
        if owner is None:
            return _blocked("MATERIALIZATION_CONTROL_MISSING")
        if owner.entry_state is StrategyEntryState.ENABLED and initial.lifecycle_state in {
            MaterializationGenerationState.PENDING,MaterializationGenerationState.DESIRED,MaterializationGenerationState.DRAINING_ENTRY,
            MaterializationGenerationState.MATERIALIZING,MaterializationGenerationState.STAGED,
        } and await uow.instrument_selection.generic_generation_owner_pause_pending(initial.materialization_generation_id,checked_at_ms=now_ms):
            vacuum=await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=initial.strategy_group_id,selection_spec_id=initial.selection_spec_id,for_update=True)
            if vacuum is None:
                return _blocked("OWNER_PAUSED_VACUUM_MISSING")
            if vacuum.state is StrategyEntryVacuumState.OPEN and vacuum.first_blocker=="OWNER_PAUSED":
                vacuum=await uow.instrument_selection.mark_entry_vacuum_draining(vacuum,started_at_ms=now_ms)
            await _abandon_generation_targets(uow=uow,generation_id=initial.materialization_generation_id,reason_code="owner_paused",attempted_at_ms=now_ms)
            await uow.instrument_selection.abandon_generation_for_owner_pause(generation=initial,vacuum=vacuum,paused_at_ms=now_ms)
            return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.WAITING_VACUUM,
                materialization_generation_id=initial.materialization_generation_id,entry_vacuum_id=vacuum.entry_vacuum_id,reason_code="OWNER_PAUSE_DEFERRED_CLEANUP")
        if owner.entry_state is StrategyEntryState.PAUSED:
            pause_changed = False
            if initial.lifecycle_state in {MaterializationGenerationState.PENDING,MaterializationGenerationState.DESIRED,
                MaterializationGenerationState.DRAINING_ENTRY,MaterializationGenerationState.MATERIALIZING,MaterializationGenerationState.STAGED}:
                pause_changed = True
                vacuum = await uow.instrument_selection.get_current_entry_vacuum(
                    strategy_group_id=initial.strategy_group_id,selection_spec_id=initial.selection_spec_id,for_update=True)
                if vacuum is None and initial.lifecycle_state in {MaterializationGenerationState.PENDING,MaterializationGenerationState.DESIRED}:
                    vacuum = await uow.instrument_selection.open_owner_paused_entry_vacuum(StrategyEntryVacuum(
                        entry_vacuum_id="vacuum:owner-pause:"+initial.materialization_generation_id,
                        strategy_group_id=initial.strategy_group_id,selection_spec_id=initial.selection_spec_id,
                        period_anchor_ms=initial.period_anchor_ms,source_generation_id=None,
                        state=StrategyEntryVacuumState.OPEN,fenced_at_ms=now_ms,drained_at_ms=None,
                        resolved_at_ms=None,first_blocker="OWNER_PAUSED",projection_version=1))
                if vacuum is not None and vacuum.state is StrategyEntryVacuumState.OPEN and vacuum.first_blocker=="OWNER_PAUSED":
                    vacuum = await uow.instrument_selection.mark_entry_vacuum_draining(vacuum,started_at_ms=now_ms)
                if vacuum is None:
                    return _blocked("OWNER_PAUSED_VACUUM_MISSING")
                await _abandon_generation_targets(uow=uow,generation_id=initial.materialization_generation_id,
                    reason_code="owner_paused",attempted_at_ms=now_ms)
                await uow.instrument_selection.abandon_generation_for_owner_pause(
                    generation=initial,vacuum=vacuum,paused_at_ms=now_ms)
            elif initial.lifecycle_state is MaterializationGenerationState.ABANDONED:
                vacuum = await uow.instrument_selection.get_current_entry_vacuum(
                    strategy_group_id=initial.strategy_group_id,selection_spec_id=initial.selection_spec_id,for_update=True)
                if vacuum is not None and vacuum.source_generation_id in {None,initial.materialization_generation_id} and (
                    vacuum.state is StrategyEntryVacuumState.DRAINING_ENTRY and vacuum.first_blocker=="OWNER_PAUSED"):
                    pause_changed = True
                    await drain_strategy_entry_vacuum_once(uow,DrainStrategyEntryVacuumRequest(
                        strategy_group_id=initial.strategy_group_id,selection_spec_id=initial.selection_spec_id,now_ms=now_ms))
            return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.OWNER_PAUSED,
                materialization_generation_id=initial.materialization_generation_id,
                reason_code=None if pause_changed else "OWNER_PAUSED_NO_CHANGE")
        if initial.lifecycle_state is MaterializationGenerationState.ABANDONED:
            vacuum = await uow.instrument_selection.get_current_entry_vacuum(
                strategy_group_id=initial.strategy_group_id,selection_spec_id=initial.selection_spec_id,for_update=True)
            if vacuum is not None and vacuum.source_generation_id in {None,initial.materialization_generation_id} and (
                vacuum.state is StrategyEntryVacuumState.DRAINING_ENTRY and vacuum.first_blocker=="OWNER_PAUSED"):
                drain = await drain_strategy_entry_vacuum_once(uow,DrainStrategyEntryVacuumRequest(
                    strategy_group_id=initial.strategy_group_id,selection_spec_id=initial.selection_spec_id,now_ms=now_ms))
                return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.WAITING_VACUUM,
                    materialization_generation_id=initial.materialization_generation_id,entry_vacuum_id=vacuum.entry_vacuum_id,
                    reason_code=drain.reason_code or drain.status.value)
            control=await uow.instrument_selection.get_selection_control(initial.strategy_group_id,for_update=True)
            current=await uow.instrument_selection.get_current_generic_authority(initial.selection_spec_id,for_update=True)
            if current is not None and isinstance(current.authority,GenericRecoveryAuthority) and current.authority.materialization_generation_id==initial.materialization_generation_id:
                recovered=await uow.instrument_selection.commit_generic_recovery(current.authority.recovery_proof)
                return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.FALLBACK_PREVIOUS,
                    materialization_generation_id=initial.materialization_generation_id,selection_authority_id=recovered.selection_authority_id)
            if control is not None and control.selection_mode is SelectionMode.STATIC_BASELINE and control.pending_selection_mode is SelectionMode.DYNAMIC_SELECTION and (
                current is None or isinstance(current.authority,GenericRecoveryAuthority) and current.authority.selection_mode=="static_baseline"):
                try:
                    first_pause_proof=await uow.instrument_selection.prepare_generic_recovery_grant_proof(initial.materialization_generation_id)
                except SelectionPersistenceConflict as exc:
                    return _blocked(str(exc))
                recovered=await uow.instrument_selection.commit_generic_recovery(first_pause_proof)
                return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.FALLBACK_PREVIOUS,
                    materialization_generation_id=initial.materialization_generation_id,selection_authority_id=recovered.selection_authority_id)
            return _blocked("GENERIC_GENERATION_NOT_ACTIONABLE")
        if initial.lifecycle_state is MaterializationGenerationState.FAILED_CLOSED:
            control = await uow.instrument_selection.get_selection_control(initial.strategy_group_id,for_update=True)
            committed = await uow.instrument_selection.get_current_generic_authority(initial.selection_spec_id,for_update=True)
            if committed is not None and isinstance(committed.authority,GenericRecoveryAuthority) and (
                committed.authority.materialization_generation_id==initial.materialization_generation_id):
                try:
                    recovered = await uow.instrument_selection.commit_generic_recovery(committed.authority.recovery_proof)
                except SelectionPersistenceConflict as exc:
                    return _blocked(str(exc))
                return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.FALLBACK_PREVIOUS,
                    selection_authority_id=recovered.selection_authority_id,materialization_generation_id=initial.materialization_generation_id)
            vacuum = await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=initial.strategy_group_id,
                selection_spec_id=initial.selection_spec_id,for_update=True)
            first_static = (control is not None and control.selection_mode is SelectionMode.STATIC_BASELINE
                and control.pending_selection_mode is SelectionMode.DYNAMIC_SELECTION and (
                    committed is None or isinstance(committed.authority,GenericRecoveryAuthority) and committed.authority.selection_mode=="static_baseline"))
            previous_dynamic = (control is not None and control.selection_mode is SelectionMode.DYNAMIC_SELECTION
                and control.pending_selection_mode is None and committed is not None)
            if (first_static or previous_dynamic) and vacuum is not None and (
                vacuum.source_generation_id==initial.materialization_generation_id):
                try:
                    recovery_proof = await uow.instrument_selection.prepare_generic_recovery_grant_proof(initial.materialization_generation_id)
                except SelectionPersistenceConflict:
                    # Existing failed attempt remains fenced. Retry readiness
                    # later; preparation writes no facts and cannot grant Entry.
                    recovery_proof = None
                if recovery_proof is not None:
                    recovered = await uow.instrument_selection.commit_generic_recovery(recovery_proof)
                    return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.FALLBACK_PREVIOUS,
                        selection_authority_id=recovered.selection_authority_id,materialization_generation_id=initial.materialization_generation_id,
                        entry_vacuum_id=vacuum.entry_vacuum_id)
            return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.BLOCKED,
                materialization_generation_id=initial.materialization_generation_id,selection_snapshot_id=initial.selection_snapshot_id,
                entry_vacuum_id=None if vacuum is None else vacuum.entry_vacuum_id,
                reason_code=vacuum.first_blocker if vacuum is not None and vacuum.source_generation_id==initial.materialization_generation_id else "GENERIC_RECOVERY_REQUIRED")
        if initial.lifecycle_state is MaterializationGenerationState.ACTIVE:
            control = await uow.instrument_selection.get_selection_control(initial.strategy_group_id,for_update=True)
            committed = await uow.instrument_selection.get_current_generic_authority(initial.selection_spec_id,for_update=True)
            checked_at = await uow.instrument_selection.read_authority_clock_ms()
            committed_window_valid = committed is not None and (
                (committed.authority.created_at_ms if isinstance(committed.authority,GenericRecoveryAuthority)
                    else committed.authority.effective_from_ms) <= checked_at < committed.authority.expires_at_ms)
            if committed is None or control is None or committed.authority.materialization_generation_id != initial.materialization_generation_id or (
                committed.authority.selection_control_version != control.control_version
                or control.selection_mode is not SelectionMode.DYNAMIC_SELECTION
                or control.selection_spec_id != initial.selection_spec_id
                or control.selection_epoch_id != initial.selection_epoch_id
                or committed.authority.owner_control_version != owner.control_version
                or not committed_window_valid):
                return _blocked("GENERIC_ACTIVE_AUTHORITY_CHANGED")
            active = await uow.strategy_universes.get_current(committed.authority.event_binding.event_spec_id)
            if active is None or active.universe_version_id != committed.authority.event_binding.universe_version_id:
                return _blocked("GENERIC_ACTIVE_UNIVERSE_CHANGED")
            return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.ACTIVE_NEW,
                selection_authority_id=committed.authority.selection_authority_id,selection_snapshot_id=initial.selection_snapshot_id,
                materialization_generation_id=initial.materialization_generation_id,
                reason_code="TERMINAL_AUTHORITY_ALREADY_COMMITTED")
        if initial.lifecycle_state in {MaterializationGenerationState.PENDING,MaterializationGenerationState.DESIRED}:
            spec=await uow.instrument_selection.get_generic_spec(initial.selection_spec_id)
            if now_ms>=initial.period_anchor_ms+(1+spec.cadence_hours)*HOUR_MS:
                if initial.lease_owner is not None and initial.lease_expires_at_ms is not None and now_ms<initial.lease_expires_at_ms:
                    return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.GENERATION_LEASE_HELD,
                        materialization_generation_id=initial.materialization_generation_id,reason_code="GENERIC_GENERATION_LEASE_UNAVAILABLE")
                await uow.instrument_selection.expire_unfenced_generic_generation(initial.materialization_generation_id)
                return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.BLOCKED,
                    materialization_generation_id=initial.materialization_generation_id,reason_code="MATERIALIZATION_PERIOD_EXPIRED")
            source = await uow.instrument_selection.get_current_generic_authority(
                initial.selection_spec_id, for_update=True
            )
            # A live recovery must retain its observation/rebase window. Once
            # expired it cannot arm old checkpoints, so a newer Desired must
            # inherit a recorded gap fence and a future-close recovery proof.
            if initial.lifecycle_state is MaterializationGenerationState.DESIRED and (
                source is not None and isinstance(source.authority, GenericRecoveryAuthority)
                and source.authority.selection_mode == "dynamic_selection"
                and now_ms >= source.authority.expires_at_ms
                and await uow.instrument_selection.generic_recovery_transition_blocker(
                    selection_spec_id=initial.selection_spec_id,
                    target_members=(await uow.instrument_selection.get_generic_snapshot(
                        initial.selection_snapshot_id)).selected_members,
                ) == "GENERIC_RECOVERY_REBASE_PENDING"
            ):
                vacuum = await uow.instrument_selection.get_current_entry_vacuum(
                    strategy_group_id=initial.strategy_group_id,
                    selection_spec_id=initial.selection_spec_id,
                    for_update=True,
                )
                if vacuum is None:
                    gap_anchor = source.authority.expires_at_ms - HOUR_MS
                    if now_ms < source.authority.expires_at_ms + HOUR_MS:
                        return CoordinateSelectionMaterializationResult(
                            disposition=MaterializationDisposition.GENERATION_DESIRED,
                            materialization_generation_id=initial.materialization_generation_id,
                            reason_code="EXPIRED_RECOVERY_AWAITING_GAP_CLOSE",
                        )
                    fenced = await uow.instrument_selection.read_authority_clock_ms()
                    gap = StrategyEntryVacuum(
                        entry_vacuum_id="vacuum:gap:" + canonical_digest({
                            "selection_spec_id": initial.selection_spec_id,
                            "period_anchor_ms": gap_anchor,
                            "source_selection_authority_id": source.authority.selection_authority_id,
                        })[7:],
                        strategy_group_id=initial.strategy_group_id,
                        selection_spec_id=initial.selection_spec_id,
                        period_anchor_ms=gap_anchor,
                        source_generation_id=None,
                        state=StrategyEntryVacuumState.OPEN,
                        fenced_at_ms=fenced,
                        drained_at_ms=None,
                        resolved_at_ms=None,
                        first_blocker="AUTHORITY_GAP",
                        projection_version=1,
                    )
                    await uow.instrument_selection.open_generic_authority_gap_vacuum(
                        gap,
                        source_selection_authority_id=source.authority.selection_authority_id,
                        expected_current_version=source.projection_version,
                    )
                    return CoordinateSelectionMaterializationResult(
                        disposition=MaterializationDisposition.WAITING_VACUUM,
                        materialization_generation_id=initial.materialization_generation_id,
                        entry_vacuum_id=gap.entry_vacuum_id,
                        reason_code="EXPIRED_RECOVERY_GAP_FENCED",
                    )
                if vacuum.source_generation_id is None and vacuum.first_blocker == "AUTHORITY_GAP":
                    if vacuum.state in {StrategyEntryVacuumState.OPEN, StrategyEntryVacuumState.DRAINING_ENTRY}:
                        drained = await drain_strategy_entry_vacuum_once(
                            uow,
                            DrainStrategyEntryVacuumRequest(
                                strategy_group_id=initial.strategy_group_id,
                                selection_spec_id=initial.selection_spec_id,
                                now_ms=now_ms,
                            ),
                        )
                        return CoordinateSelectionMaterializationResult(
                            disposition=MaterializationDisposition.WAITING_VACUUM,
                            materialization_generation_id=initial.materialization_generation_id,
                            entry_vacuum_id=vacuum.entry_vacuum_id,
                            reason_code=drained.reason_code or drained.status.value,
                        )
                    if vacuum.state is StrategyEntryVacuumState.RECOVERY_PENDING:
                        replacement = await uow.instrument_selection.retarget_generic_gap_vacuum_with_generation(
                            initial, entry_vacuum_id=vacuum.entry_vacuum_id
                        )
                        return CoordinateSelectionMaterializationResult(
                            disposition=MaterializationDisposition.GENERATION_MATERIALIZING,
                            materialization_generation_id=replacement.materialization_generation_id,
                            entry_vacuum_id=vacuum.entry_vacuum_id,
                            reason_code="EXPIRED_RECOVERY_FRESH_TARGET_HANDOFF",
                        )
        claim = await uow.instrument_selection.claim_generic_materialization_generation(
            initial.materialization_generation_id,worker_id=request.worker_id,now_ms=now_ms,lease_duration_ms=30_000)
        if claim.status is MaterializationGenerationClaimStatus.LEASE_HELD:
            return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.GENERATION_LEASE_HELD,
                materialization_generation_id=initial.materialization_generation_id,reason_code="GENERIC_GENERATION_LEASE_UNAVAILABLE")
        if claim.status is not MaterializationGenerationClaimStatus.CLAIMED or claim.generation is None:
            return _blocked("GENERIC_GENERATION_NOT_ACTIONABLE")
        generation = claim.generation
        failed = False
        try:
            identity = {"materialization_generation_id":generation.materialization_generation_id,
                "selection_snapshot_id":generation.selection_snapshot_id}
            if generation.lifecycle_state in {MaterializationGenerationState.MATERIALIZING,MaterializationGenerationState.STAGED}:
                spec = await uow.instrument_selection.get_generic_spec(generation.selection_spec_id)
                expiry = generation.period_anchor_ms+(1+spec.cadence_hours)*3_600_000
                reason = "MATERIALIZATION_PERIOD_EXPIRED" if now_ms>=expiry else (
                    "MATERIALIZATION_TIMEOUT" if generation.fenced_at_ms is not None
                    and now_ms>=generation.fenced_at_ms+spec.materialization_timeout_ms else None)
                if reason is not None:
                    return await _fail_generic_generation(uow,generation,request,reason)
            if generation.lifecycle_state is MaterializationGenerationState.PENDING:
                await uow.instrument_selection.mark_generic_materialization_generation_desired(
                    generation.materialization_generation_id,worker_id=request.worker_id,
                    lease_epoch=generation.lease_epoch,expected_projection_version=generation.projection_version,
                    desired_at_ms=now_ms)
                return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.GENERATION_DESIRED,**identity)
            if generation.lifecycle_state is MaterializationGenerationState.DESIRED:
                snapshot = await uow.instrument_selection.get_generic_snapshot(generation.selection_snapshot_id)
                blocker = await uow.instrument_selection.generic_recovery_transition_blocker(
                    selection_spec_id=generation.selection_spec_id,target_members=snapshot.selected_members)
                if blocker is not None:
                    # Keep the old scopes observable until their authorized
                    # recovery rebase is actually armed. Opening Vacuum first
                    # prevents precisely that observation and causes starvation.
                    return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.GENERATION_DESIRED,
                        reason_code=blocker,**identity)
                spec = await uow.instrument_selection.get_generic_spec(generation.selection_spec_id)
                close = now_ms//HOUR_MS*HOUR_MS
                try:
                    await uow.signals.lock_generic_close_coverage(event_spec_id=spec.event_spec_id,
                        exchange_instrument_ids=snapshot.selected_members,closed_at_ms=close)
                except GenericCloseAlreadyConsumed:
                    # No future eligible close is promised by taking the slot.
                    # Keep this Desired unfenced so a newer due period can
                    # supersede it without starving the old recovery path.
                    return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.GENERATION_DESIRED,
                        reason_code="GENERIC_CURRENT_CLOSE_ALREADY_CONSUMED",**identity)
                if not await uow.strategy_universes.materialization_slot_available(generation.materialization_generation_id):
                    return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.GENERATION_DESIRED,
                        reason_code="GLOBAL_WARMING_SLOT_BUSY",**identity)
                vacuum = await uow.instrument_selection.get_current_entry_vacuum(
                    strategy_group_id=generation.strategy_group_id,selection_spec_id=generation.selection_spec_id,for_update=True)
                if vacuum is None:
                    vacuum = StrategyEntryVacuum(entry_vacuum_id="vacuum:"+generation.materialization_generation_id,
                        strategy_group_id=generation.strategy_group_id,selection_spec_id=generation.selection_spec_id,
                        period_anchor_ms=generation.period_anchor_ms,source_generation_id=generation.materialization_generation_id,
                        state=StrategyEntryVacuumState.DRAINING_ENTRY,fenced_at_ms=now_ms,drained_at_ms=None,resolved_at_ms=None,
                        first_blocker="ENTRY_DRAIN_REQUIRED",projection_version=2)
                    await uow.instrument_selection.open_generation_entry_vacuum(vacuum,
                        expected_generation_version=generation.projection_version,worker_id=request.worker_id,lease_epoch=generation.lease_epoch)
                return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.WAITING_VACUUM,
                    entry_vacuum_id=vacuum.entry_vacuum_id,**identity)
            if generation.lifecycle_state is MaterializationGenerationState.DRAINING_ENTRY:
                result = await drain_strategy_entry_vacuum_once(uow,DrainStrategyEntryVacuumRequest(
                    strategy_group_id=generation.strategy_group_id,selection_spec_id=generation.selection_spec_id,now_ms=now_ms))
                return CoordinateSelectionMaterializationResult(disposition=(MaterializationDisposition.GENERATION_MATERIALIZING
                    if result.status is VacuumDrainStatus.ENTRY_DRAINED else MaterializationDisposition.WAITING_VACUUM),
                    entry_vacuum_id=result.entry_vacuum_id,reason_code=result.reason_code or result.status.value,**identity)
            if generation.lifecycle_state is MaterializationGenerationState.MATERIALIZING:
                vacuum = await uow.instrument_selection.get_current_entry_vacuum(
                    strategy_group_id=generation.strategy_group_id,selection_spec_id=generation.selection_spec_id,for_update=True)
                if vacuum is None or vacuum.source_generation_id != generation.materialization_generation_id or vacuum.state is not StrategyEntryVacuumState.RECONFIGURING:
                    return _blocked("GENERIC_DRAINED_VACUUM_REQUIRED")
                spec = await uow.instrument_selection.get_generic_spec(generation.selection_spec_id)
                snapshot = await uow.instrument_selection.get_generic_snapshot(generation.selection_snapshot_id)
                contract = strategy_contract_for(spec.event_spec_id)
                context = await uow.strategy_universes.resolve_install_context(runtime_profile_id="tiny-live-v1",event_id=contract.event_id)
                if context.event_spec_id != spec.event_spec_id:
                    return _blocked("GENERIC_EVENT_AUTHORITY_CHANGED")
                installed = await install_strategy_universe(uow,UniverseInstallRequest(
                    event_spec_id=spec.event_spec_id,runtime_profile_id="tiny-live-v1",owner_policy_id=context.owner_policy_id,
                    exchange_instrument_ids=snapshot.selected_members,source_kind="dynamic_selection",
                    materialization_generation_id=generation.materialization_generation_id,
                    expected_member_set_digest=snapshot.member_set_digest,installed_at_ms=now_ms))
                if installed.status is UniverseInstallStatus.WARMING_UNIVERSE_ALREADY_EXISTS:
                    return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.TARGET_WARMING,
                        reason_code="GLOBAL_WARMING_SLOT_BUSY",entry_vacuum_id=vacuum.entry_vacuum_id,**identity)
                if installed.universe is None:
                    return _blocked("GENERIC_TARGET_INSTALLATION_FAILED")
                staged = await advance_strategy_universe(uow,UniverseActivationRequest(
                    universe_version_id=installed.universe.universe_version_id,attempted_at_ms=now_ms,
                    operation=UniverseActivationOperation.STAGE_DYNAMIC,materialization_generation_id=generation.materialization_generation_id,
                    materialization_lease_owner=request.worker_id,materialization_lease_epoch=generation.lease_epoch))
                if staged.status is UniverseActivationStatus.STAGED:
                    return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.GENERATION_STAGED,
                        entry_vacuum_id=vacuum.entry_vacuum_id,**identity)
                if staged.reason_code in {"CERTIFICATION_OWNER_ACTION_REQUIRED","CERTIFICATION_NOT_ELIGIBLE"}:
                    return await _fail_generic_generation(uow,generation,request,staged.reason_code)
                if staged.reason_code not in _GENERIC_TRANSIENT_WARMING_BLOCKERS:
                    return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.BLOCKED,
                        reason_code=staged.reason_code,entry_vacuum_id=vacuum.entry_vacuum_id,**identity)
                return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.TARGET_WARMING,
                    reason_code=staged.reason_code,entry_vacuum_id=vacuum.entry_vacuum_id,**identity)
            if generation.lifecycle_state is MaterializationGenerationState.STAGED:
                vacuum = await uow.instrument_selection.get_current_entry_vacuum(
                    strategy_group_id=generation.strategy_group_id,selection_spec_id=generation.selection_spec_id,for_update=True)
                if vacuum is None or vacuum.source_generation_id!=generation.materialization_generation_id:
                    return _blocked("GENERIC_STAGED_VACUUM_CHANGED")
                if generation.fenced_at_ms is None:
                    return _blocked("GENERIC_STAGED_FENCE_MISSING")
                if vacuum.fenced_at_ms!=generation.fenced_at_ms:
                    # A retargeted Vacuum is a real authority gap. Only the
                    # future-close recovery proof may authorize this target.
                    recovery_proof = await uow.instrument_selection.prepare_generic_recovered_activation_proof(
                        generation.materialization_generation_id)
                    prior_recovery = await uow.instrument_selection.get_current_generic_authority(
                        generation.selection_spec_id,for_update=True)
                    sequence = 1 if prior_recovery is None or prior_recovery.authority.period!=recovery_proof.recovery_close_plan.period else (
                        prior_recovery.authority.authority_sequence+1)
                    recovered_authority = GenericRecoveryAuthority.build(proof=recovery_proof,authority_sequence=sequence)
                    target_rows = await uow.strategy_universes.get_generation_universe_targets(
                        generation.materialization_generation_id,for_update=True)
                    if len(target_rows)!=1 or target_rows[0].lifecycle_state.value!="staged":
                        return _blocked("GENERIC_RECOVERY_TARGET_CHANGED")
                    recovered_target = target_rows[0]
                    activated = await advance_strategy_universe(uow,UniverseActivationRequest(
                        universe_version_id=recovered_target.universe_version_id,attempted_at_ms=recovery_proof.committed_at_ms,
                        operation=UniverseActivationOperation.ACTIVATE_GENERIC,
                        materialization_generation_id=generation.materialization_generation_id,
                        materialization_lease_owner=request.worker_id,materialization_lease_epoch=generation.lease_epoch,
                        generic_authority=recovered_authority))
                    if activated.status not in {UniverseActivationStatus.ACTIVATED,UniverseActivationStatus.ALREADY_ACTIVE}:
                        return _blocked(str(activated.reason_code))
                    return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.ACTIVE_NEW,
                        selection_authority_id=recovered_authority.selection_authority_id,
                        materialization_generation_id=generation.materialization_generation_id,
                        selection_snapshot_id=generation.selection_snapshot_id,entry_vacuum_id=vacuum.entry_vacuum_id)
                control = await uow.instrument_selection.get_selection_control(generation.strategy_group_id,for_update=True)
                first_activation = control is not None and control.selection_mode is SelectionMode.STATIC_BASELINE and (
                    control.pending_selection_mode is SelectionMode.DYNAMIC_SELECTION
                    and control.pending_effective_period_anchor_ms is not None
                    and control.pending_effective_period_anchor_ms <= generation.period_anchor_ms
                    and control.pending_authorization_id is not None)
                if control is None or (control.selection_mode is not SelectionMode.DYNAMIC_SELECTION and not first_activation):
                    return _blocked("GENERIC_FIRST_ACTIVATION_REQUIRED")
                targets = await uow.strategy_universes.get_generation_universe_targets(generation.materialization_generation_id,for_update=True)
                spec = await uow.instrument_selection.get_generic_spec(generation.selection_spec_id)
                snapshot = await uow.instrument_selection.get_generic_snapshot(generation.selection_snapshot_id)
                if len(targets)!=1 or targets[0].event_spec_id!=spec.event_spec_id or targets[0].lifecycle_state.value!="staged":
                    return _blocked("GENERIC_STAGED_TARGET_CHANGED")
                target = targets[0]
                now = await uow.instrument_selection.read_authority_clock_ms()
                certified = await advance_strategy_universe(uow,UniverseActivationRequest(universe_version_id=target.universe_version_id,
                    attempted_at_ms=now,operation=UniverseActivationOperation.CERTIFY_STAGED,materialization_generation_id=generation.materialization_generation_id,
                    materialization_lease_owner=request.worker_id,materialization_lease_epoch=generation.lease_epoch))
                if certified.status is not UniverseActivationStatus.STAGED:
                    if certified.reason_code in {"CERTIFICATION_OWNER_ACTION_REQUIRED","CERTIFICATION_NOT_ELIGIBLE"}:
                        return await _fail_generic_generation(uow,generation,request,certified.reason_code)
                    return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.TARGET_WARMING
                        if certified.reason_code in _GENERIC_TRANSIENT_WARMING_BLOCKERS else MaterializationDisposition.BLOCKED,
                        reason_code=certified.reason_code,**identity)
                comparison_id = None
                comparison_revision = None
                if generation.strategy_group_id in {"MPG-001","MI-001"}:
                    comparison = await uow.instrument_selection.get_comparison_universe_binding(spec.event_spec_id,for_update=True)
                    if comparison is None:
                        return _blocked("GENERIC_COMPARISON_BASELINE_MISSING")
                    comparison_id = "comparison:"+canonical_digest({"exchange_instrument_ids":spec.candidate_ids})[7:]
                    comparison_revision = comparison.comparison_transition_revision + (comparison.comparison_universe_id!=comparison_id)
                prior = await uow.instrument_selection.get_current_generic_authority(generation.selection_spec_id,for_update=True)
                blocker = await uow.instrument_selection.generic_recovery_transition_blocker(
                    selection_spec_id=generation.selection_spec_id,target_members=snapshot.selected_members)
                if blocker is not None:
                    return _blocked(blocker)
                try:
                    proof = await prepare_generic_current_close_proof(uow,selection_snapshot_id=snapshot.selection_snapshot_id)
                except GenericCloseAlreadyConsumed:
                    return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.BLOCKED,
                        reason_code="GENERIC_CURRENT_CLOSE_ALREADY_CONSUMED",entry_vacuum_id=vacuum.entry_vacuum_id,**identity)
                sequence = 1 if prior is None or prior.authority.period!=proof.period else prior.authority.authority_sequence+1
                authority = GenericSelectionAuthority(selection_authority_id=f"authority:{snapshot.selection_snapshot_id}:{sequence}",
                    selection_spec_id=generation.selection_spec_id,strategy_group_id=generation.strategy_group_id,selection_epoch_id=generation.selection_epoch_id,
                    selection_snapshot_id=snapshot.selection_snapshot_id,materialization_generation_id=generation.materialization_generation_id,
                    authority_sequence=sequence,owner_control_version=owner.control_version,selection_control_version=control.control_version + int(first_activation),
                    activation_authorization_id=control.pending_authorization_id if first_activation else None,
                    period=proof.period,authority_outcome="ACTIVE_NEW",event_binding=AuthorityEventBinding(event_spec_id=spec.event_spec_id,
                        position_side=spec.position_side,grant_state=AuthorityEventGrantState.ACTIVE,universe_version_id=target.universe_version_id,member_set_digest=snapshot.member_set_digest),
                    current_close_proof=proof,membership_freshness=build_dynamic_membership_freshness(source_snapshot_id=snapshot.selection_snapshot_id,
                        source_member_set_digest=snapshot.member_set_digest,period=proof.period),comparison_universe_id=comparison_id,
                    comparison_transition_revision=comparison_revision,effective_from_ms=proof.authority_granted_at_ms,created_at_ms=proof.authority_granted_at_ms)
                activated = await advance_strategy_universe(uow,UniverseActivationRequest(universe_version_id=target.universe_version_id,
                    attempted_at_ms=authority.created_at_ms,operation=UniverseActivationOperation.ACTIVATE_GENERIC,
                    materialization_generation_id=generation.materialization_generation_id,materialization_lease_owner=request.worker_id,
                    materialization_lease_epoch=generation.lease_epoch,generic_authority=authority))
                if activated.status not in {UniverseActivationStatus.ACTIVATED,UniverseActivationStatus.ALREADY_ACTIVE}:
                    return _blocked(str(activated.reason_code))
                return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.ACTIVE_NEW,
                    selection_authority_id=authority.selection_authority_id,**identity)
            return _blocked("GENERIC_ACTIVATION_REQUIRED")
        except BaseException:
            # The enclosing UoW rolls back the claim and all changes. Do not run
            # more SQL in an aborted transaction and mask the original failure.
            failed = True
            raise
        finally:
            if not failed:
                await uow.instrument_selection.release_generic_materialization_generation_lease(
                    generation.materialization_generation_id,worker_id=request.worker_id,lease_epoch=generation.lease_epoch)


async def _fail_generic_generation(uow: KernelUnitOfWork, generation: GenericMaterializationGeneration,
    request: CoordinateGenericGenerationRequest, reason: str) -> CoordinateSelectionMaterializationResult:
    await uow.instrument_selection.fail_generic_materialization_generation(generation.materialization_generation_id,
        expected_projection_version=generation.projection_version,worker_id=request.worker_id,
        lease_epoch=generation.lease_epoch,reason_code=reason)
    return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.BLOCKED,
        materialization_generation_id=generation.materialization_generation_id,selection_snapshot_id=generation.selection_snapshot_id,
        reason_code=reason)


class _AuthorityGrantWindowExpired(RuntimeError):
    def __init__(self, authority_gap_audit_id: str) -> None:
        super().__init__(authority_gap_audit_id)
        self.authority_gap_audit_id = authority_gap_audit_id


async def complete_pending_authority_gap_audit(
    *,
    uow_factory: UnitOfWorkFactory,
    audit_source: AuthorityGapAuditSource,
    authority_gap_audit_id: str,
    clock_ms: Callable[[], int],
) -> CoordinateSelectionMaterializationResult:
    try:
        return await _complete_pending_authority_gap_audit(
            uow_factory=uow_factory,
            audit_source=audit_source,
            authority_gap_audit_id=authority_gap_audit_id,
            clock_ms=clock_ms,
        )
    except _AuthorityGrantWindowExpired as exc:
        return CoordinateSelectionMaterializationResult(
            disposition=MaterializationDisposition.GAP_AUDIT_WINDOW_EXPIRED,
            authority_gap_audit_id=exc.authority_gap_audit_id,
            reason_code="AUTHORITY_TRANSACTION_CROSSED_FIRST_CLOSE",
        )


async def _complete_pending_authority_gap_audit(
    *,
    uow_factory: UnitOfWorkFactory,
    audit_source: AuthorityGapAuditSource,
    authority_gap_audit_id: str,
    clock_ms: Callable[[], int],
) -> CoordinateSelectionMaterializationResult:
    """Evaluate a staged audit outside PG and commit positive/negative proof."""

    async with uow_factory() as uow:
        await uow.strategy_universes.lock_mutation()
        audit = await uow.instrument_selection.get_authority_gap_audit(
            authority_gap_audit_id
        )
        if audit is None:
            return _blocked("AUTHORITY_GAP_AUDIT_MISSING")
        if audit.state.value != "PENDING":
            current = await uow.instrument_selection.get_current_authority_projection(
                audit.selection_spec_id
            )
            if (
                audit.state.value == "COMPLETE"
                and current is not None
                and current.authority.authority_gap_audit_id
                == audit.authority_gap_audit_id
                and current.authority.authority_outcome
                is audit.proposed_authority_outcome
            ):
                if audit.authority_gap_audit_id.startswith("gap-audit:orb:recovery:"):
                    runtime = await _orb_gap_runtime_basis(uow)
                    if (
                        runtime is None
                        or not runtime.policy.enabled
                        or not runtime.policy.new_entry_submit_enabled
                        or await _orb_current_authority_interrupted(
                            uow, runtime=runtime, current=current, now_ms=clock_ms()
                        )
                    ):
                        return _blocked("ORB_RECOVERY_BASIS_CHANGED")
                return CoordinateSelectionMaterializationResult(
                    disposition=_authority_disposition(
                        audit.proposed_authority_outcome
                    ),
                    selection_authority_id=(
                        current.authority.selection_authority_id
                    ),
                    materialization_generation_id=audit.source_generation_id,
                    entry_vacuum_id=audit.source_entry_vacuum_id,
                    authority_gap_audit_id=audit.authority_gap_audit_id,
                    reason_code="AUTHORITY_GAP_AUDIT_ALREADY_COMMITTED",
                )
            if audit.state.value == "FAILED":
                return _blocked(
                    audit.first_blocker or "AUTHORITY_GAP_AUDIT_FAILED"
                )
            return CoordinateSelectionMaterializationResult(
                disposition=MaterializationDisposition.GAP_AUDIT_PENDING,
                authority_gap_audit_id=audit.authority_gap_audit_id,
                reason_code=f"AUDIT_{audit.state.value}",
            )
        spec = await uow.instrument_selection.get_active_spec(audit.selection_spec_id)
        initial_owner_control = await uow.owner_controls.get_strategy_control(
            spec.strategy_group_id
        )
        initial_selection_control = (
            await uow.instrument_selection.get_selection_control(
                spec.strategy_group_id
            )
        )
        initial_current_authority = (
            await uow.instrument_selection.get_current_authority_projection(
                audit.selection_spec_id
            )
        )
        initial_vacuum = await uow.instrument_selection.get_current_entry_vacuum(
            strategy_group_id=spec.strategy_group_id,
            selection_spec_id=audit.selection_spec_id,
        )
        if (
            initial_owner_control is None
            or initial_owner_control.entry_state is StrategyEntryState.PAUSED
            or initial_selection_control is None
            or not _selection_control_allows_gap_completion(
                initial_selection_control,
                session_start_ms=audit.session_start_ms,
            )
        ):
            return _blocked("AUTHORITY_GAP_AUDIT_RUNTIME_DRIFT")
        if audit.detector_semantic_digest != _sor_detector_semantic_digest(
            audit.selection_spec_id
        ):
            failed = fail_authority_gap_audit(
                audit,
                first_blocker="AUTHORITY_GAP_DETECTOR_IDENTITY_DRIFT",
            )
            await uow.instrument_selection.fail_authority_gap_audit(
                failed,
                failed_at_ms=clock_ms(),
            )
            return _blocked("AUTHORITY_GAP_DETECTOR_IDENTITY_DRIFT")
        long_current = await uow.strategy_universes.get_current(
            daily_event_spec_ids(audit.selection_spec_id)[0]
        )
        short_current = await uow.strategy_universes.get_current(
            daily_event_spec_ids(audit.selection_spec_id)[1]
        )
        if long_current is None or short_current is None:
            return _blocked("AUTHORITY_GAP_AUDIT_PAIR_MISSING")
        initial_long_current = long_current
        initial_short_current = short_current
        initial_orb_runtime = (
            await _orb_gap_runtime_basis(uow)
            if audit.selection_spec_id == ORB_SELECTION_SPEC_ID
            else None
        )
        if audit.authority_gap_audit_id.startswith("gap-audit:orb:recovery:"):
            if (
                initial_orb_runtime is None
                or not initial_orb_runtime.policy.enabled
                or not initial_orb_runtime.policy.new_entry_submit_enabled
                or not initial_orb_runtime.capability.enabled
                or initial_current_authority is None
            ):
                return _blocked("ORB_RECOVERY_POLICY_OR_IDENTITY_BLOCKED")
            expected_id = _gap_audit_id(
                spec_id=audit.selection_spec_id,
                session_start_ms=audit.session_start_ms,
                gap_kind=audit.gap_kind,
                proposed_outcome=audit.proposed_authority_outcome,
                recovery_basis_digest=_orb_recovery_basis_digest(
                    runtime=initial_orb_runtime,
                    current=initial_current_authority,
                    control=initial_selection_control,
                    owner_control_version=initial_owner_control.control_version,
                    pair=UniverseAuthorityPair(
                        long_universe_version_id=long_current.universe_version_id,
                        short_universe_version_id=short_current.universe_version_id,
                    ),
                ),
            )
            if expected_id != audit.authority_gap_audit_id:
                return _blocked("ORB_RECOVERY_BASIS_CHANGED")
            for uid in (long_current.universe_version_id, short_current.universe_version_id):
                ready = await advance_strategy_universe(
                    uow,
                    UniverseActivationRequest(
                        universe_version_id=uid,
                        attempted_at_ms=clock_ms(),
                        operation=UniverseActivationOperation.CERTIFY_CURRENT,
                    ),
                )
                if ready.status is not UniverseActivationStatus.ALREADY_ACTIVE:
                    return _blocked("ORB_CURRENT_PAIR_" + (ready.reason_code or "NOT_READY"))
        long_members = await uow.strategy_universes.get_members(
            long_current.universe_version_id
        )
        short_members = await uow.strategy_universes.get_members(
            short_current.universe_version_id
        )
        initial_target_pair: UniverseAuthorityPair | None = None
        if audit.gap_kind is AuthorityGapAuditKind.ENTRY_VACUUM:
            target = (
                await _resolve_staged_generation_target(
                    uow=uow,
                    audit=audit,
                    now_ms=clock_ms(),
                )
                if audit.proposed_authority_outcome is AuthorityOutcome.ACTIVE_NEW
                else await _resolve_fallback_previous_generation_source(
                    uow=uow,
                    audit=audit,
                )
            )
            if target is None:
                return _blocked("AUTHORITY_GAP_STAGED_PAIR_MISSING")
            initial_target_pair, target_members = target
            long_members = tuple(sorted(set(long_members) | set(target_members)))
            short_members = tuple(sorted(set(short_members) | set(target_members)))
    scopes = _pair_scopes(
        selection_spec_id=audit.selection_spec_id,
        long_members=long_members,
        short_members=short_members,
    )
    window = plan_authority_gap_audit_window(
        audit,
        now_ms=clock_ms(),
    )
    if window.disposition is AuthorityGapAuditWindowDisposition.PENDING:
        return CoordinateSelectionMaterializationResult(
            disposition=MaterializationDisposition.GAP_AUDIT_PENDING,
            authority_gap_audit_id=audit.authority_gap_audit_id,
            reason_code="AUTHORITY_GAP_BEFORE_FIRST_ELIGIBLE_CLOSE",
        )
    if window.disposition is AuthorityGapAuditWindowDisposition.SESSION_EXPIRED:
        return CoordinateSelectionMaterializationResult(
            disposition=MaterializationDisposition.GAP_AUDIT_WINDOW_EXPIRED,
            authority_gap_audit_id=audit.authority_gap_audit_id,
            reason_code="AUTHORITY_GAP_SESSION_EXPIRED",
        )
    first_eligible_close = window.first_eligible_close_time_ms
    audited_through = window.audited_through_close_time_ms
    if first_eligible_close is None or audited_through is None:
        raise RuntimeError("ready Gap Audit window lost exact closes")
    try:
        results = await audit_source.evaluate_authority_gap(
            AuthorityGapAuditEvaluationRequest(
                audit=audit,
                scopes=scopes,
                audited_through_close_time_ms=audited_through,
            )
        )
    except AuthorityGapAuditSourceIntegrityError:
        return await _persist_gap_audit_failure(
            uow_factory=uow_factory,
            audit=audit,
            first_blocker="AUTHORITY_GAP_SOURCE_INTEGRITY_FAILED",
            failed_at_ms=clock_ms(),
        )
    except AuthorityGapAuditDetectorDriftError:
        return await _persist_gap_audit_failure(
            uow_factory=uow_factory,
            audit=audit,
            first_blocker="AUTHORITY_GAP_DETECTOR_DRIFT",
            failed_at_ms=clock_ms(),
        )
    except Exception:  # noqa: BLE001 - persist source failure before retry/monitor.
        return await _persist_gap_audit_failure(
            uow_factory=uow_factory,
            audit=audit,
            first_blocker="AUTHORITY_GAP_SOURCE_UNAVAILABLE",
            failed_at_ms=clock_ms(),
        )
    completed_at_ms = clock_ms()
    if completed_at_ms >= first_eligible_close:
        return CoordinateSelectionMaterializationResult(
            disposition=MaterializationDisposition.GAP_AUDIT_WINDOW_EXPIRED,
            authority_gap_audit_id=audit.authority_gap_audit_id,
            reason_code="AUDIT_FINISHED_AFTER_PROPOSED_FIRST_CLOSE",
        )
    try:
        completed = complete_authority_gap_audit(
            audit,
            audited_through_close_time_ms=audited_through,
            scopes=scopes,
            results=results,
        )
    except ValueError:
        failed = fail_authority_gap_audit(
            audit,
            first_blocker="AUTHORITY_GAP_AUDIT_INCOMPLETE",
        )
        async with uow_factory() as uow:
            await uow.strategy_universes.lock_mutation()
            await uow.instrument_selection.fail_authority_gap_audit(
                failed,
                failed_at_ms=completed_at_ms,
            )
        return _blocked("AUTHORITY_GAP_AUDIT_INCOMPLETE")
    async with uow_factory() as uow:
        await uow.strategy_universes.lock_mutation()
        if audit.selection_spec_id == ORB_SELECTION_SPEC_ID:
            final_runtime = await _orb_gap_runtime_basis(uow, for_update=True)
            if final_runtime is None or final_runtime != initial_orb_runtime:
                return _blocked("AUTHORITY_GAP_AUDIT_POLICY_OR_IDENTITY_DRIFT")
        owner_control = await uow.owner_controls.get_strategy_control(
            spec.strategy_group_id,
            for_update=True,
        )
        if owner_control is None or owner_control.entry_state is StrategyEntryState.PAUSED:
            return _blocked("OWNER_PAUSED_DURING_AUTHORITY_GAP_AUDIT")
        selection_control = await uow.instrument_selection.get_selection_control(
            spec.strategy_group_id,
            for_update=True,
        )
        current_authority = (
            await uow.instrument_selection.get_current_authority_projection(
                audit.selection_spec_id
            )
        )
        long_current = await uow.strategy_universes.get_current(
            daily_event_spec_ids(audit.selection_spec_id)[0]
        )
        short_current = await uow.strategy_universes.get_current(
            daily_event_spec_ids(audit.selection_spec_id)[1]
        )
        vacuum = await uow.instrument_selection.get_current_entry_vacuum(
            strategy_group_id=spec.strategy_group_id,
            selection_spec_id=audit.selection_spec_id,
            for_update=True,
        )
        target_pair: UniverseAuthorityPair | None = None
        if audit.gap_kind is AuthorityGapAuditKind.ENTRY_VACUUM:
            target = (
                await _resolve_staged_generation_target(
                    uow=uow,
                    audit=audit,
                    now_ms=completed_at_ms,
                )
                if audit.proposed_authority_outcome is AuthorityOutcome.ACTIVE_NEW
                else await _resolve_fallback_previous_generation_source(
                    uow=uow,
                    audit=audit,
                )
            )
            if target is None:
                return _blocked("AUTHORITY_GAP_STAGED_PAIR_MISSING")
            target_pair, _ = target
        if (
            selection_control is None
            or not _selection_control_allows_gap_completion(
                selection_control,
                session_start_ms=audit.session_start_ms,
            )
            or long_current is None
            or short_current is None
            or owner_control != initial_owner_control
            or selection_control != initial_selection_control
            or current_authority != initial_current_authority
            or long_current != initial_long_current
            or short_current != initial_short_current
            or vacuum != initial_vacuum
            or target_pair != initial_target_pair
        ):
            return _blocked("AUTHORITY_GAP_AUDIT_RUNTIME_DRIFT")
        await uow.instrument_selection.complete_authority_gap_audit(
            completed,
            results=results,
            completed_at_ms=completed_at_ms,
        )
        snapshot = await uow.instrument_selection.get_snapshot_disposition(
            selection_spec_id=audit.selection_spec_id,
            session_start_ms=audit.session_start_ms,
            for_update=True,
        )
        authority = _build_audited_authority(
            audit=completed,
            current_authority=current_authority,
            pair=(
                target_pair
                or UniverseAuthorityPair(
                    long_universe_version_id=long_current.universe_version_id,
                    short_universe_version_id=short_current.universe_version_id,
                )
            ),
            owner_control_version=owner_control.control_version,
            selection_snapshot_id=(
                None
                if snapshot is None or (
                    audit.selection_spec_id == ORB_SELECTION_SPEC_ID
                    and audit.proposed_authority_outcome is AuthorityOutcome.PRE_FENCE_CONTINUITY
                )
                else snapshot.snapshot.selection_snapshot_id
            ),
            created_at_ms=completed_at_ms,
            selection_mode=(
                SelectionMode.STATIC_BASELINE
                if ((selection_control.pending_selection_mode is SelectionMode.STATIC_BASELINE and audit.proposed_authority_outcome is AuthorityOutcome.ACTIVE_NEW)
                    or (selection_control.selection_mode is SelectionMode.STATIC_BASELINE and audit.proposed_authority_outcome is AuthorityOutcome.FALLBACK_PREVIOUS))
                else SelectionMode.DYNAMIC_SELECTION
            ),
            reason_code=(
                vacuum.first_blocker
                if vacuum is not None
                and audit.proposed_authority_outcome
                is AuthorityOutcome.FALLBACK_PREVIOUS
                else None
            ),
            selection_control=selection_control,
        )
        if authority.authority_outcome is AuthorityOutcome.ACTIVE_NEW:
            assert target_pair is not None
            await advance_strategy_universe(
                uow,
                UniverseActivationRequest(
                    universe_version_id=target_pair.long_universe_version_id,
                    paired_universe_version_id=(
                        target_pair.short_universe_version_id
                    ),
                    attempted_at_ms=completed_at_ms,
                    operation=UniverseActivationOperation.ACTIVATE_DYNAMIC_PAIR,
                    materialization_generation_id=(
                        authority.materialization_generation_id
                    ),
                    selection_authority=authority,
                ),
            )
        elif authority.authority_outcome is AuthorityOutcome.FALLBACK_PREVIOUS:
            assert target_pair is not None
            assert authority.materialization_generation_id is not None
            await _abandon_generation_targets(
                uow=uow,
                generation_id=authority.materialization_generation_id,
                reason_code="fallback_previous",
                attempted_at_ms=completed_at_ms,
            )
            fallback_previous = await advance_strategy_universe(
                uow,
                UniverseActivationRequest(
                    universe_version_id=target_pair.long_universe_version_id,
                    paired_universe_version_id=(
                        target_pair.short_universe_version_id
                    ),
                    attempted_at_ms=completed_at_ms,
                    operation=UniverseActivationOperation.FALLBACK_PREVIOUS,
                    materialization_generation_id=(
                        authority.materialization_generation_id
                    ),
                    selection_authority=authority,
                ),
            )
            if (
                fallback_previous.status
                is not UniverseActivationStatus.FALLBACK_PREVIOUS
            ):
                return _blocked("FALLBACK_PREVIOUS_NOT_COMMITTED")
        else:
            if audit.selection_spec_id == ORB_SELECTION_SPEC_ID and audit.gap_kind is AuthorityGapAuditKind.OWNER_PAUSE:
                if vacuum is None:
                    return _blocked("ORB_OWNER_PAUSE_VACUUM_MISSING")
                await uow.instrument_selection.resolve_orb_owner_pause_vacuum(vacuum,
                    authority=authority,resolved_at_ms=completed_at_ms)
            await uow.instrument_selection.add_authority_and_set_current(
                authority,
                expected_current_version=(
                    None
                    if current_authority is None
                    else current_authority.projection_version
                ),
            )
            if (audit.selection_spec_id == ORB_SELECTION_SPEC_ID and authority.activation_authorization_id is not None):
                await uow.instrument_selection.activate_pending_selection_mode(strategy_group_id=spec.strategy_group_id,
                    expected_control_version=selection_control.control_version,
                    expected_pending_mode=SelectionMode.DYNAMIC_SELECTION,activated_at_ms=completed_at_ms)
        if (
            completed.first_eligible_close_time_ms is None
            or clock_ms() >= completed.first_eligible_close_time_ms
        ):
            raise _AuthorityGrantWindowExpired(audit.authority_gap_audit_id)
    return CoordinateSelectionMaterializationResult(
        disposition=_authority_disposition(audit.proposed_authority_outcome),
        selection_authority_id=authority.selection_authority_id,
        materialization_generation_id=audit.source_generation_id,
        entry_vacuum_id=audit.source_entry_vacuum_id,
        authority_gap_audit_id=audit.authority_gap_audit_id,
        reason_code="AUTHORITY_GAP_AUDIT_COMPLETE",
    )


async def _persist_gap_audit_failure(
    *,
    uow_factory: UnitOfWorkFactory,
    audit: AuthorityGapAudit,
    first_blocker: str,
    failed_at_ms: int,
) -> CoordinateSelectionMaterializationResult:
    failed = fail_authority_gap_audit(audit, first_blocker=first_blocker)
    async with uow_factory() as uow:
        await uow.strategy_universes.lock_mutation()
        await uow.instrument_selection.fail_authority_gap_audit(
            failed,
            failed_at_ms=failed_at_ms,
        )
    return _blocked(first_blocker)


async def _prepare_gap_audit(
    *,
    uow: KernelUnitOfWork,
    spec_id: str,
    session_start_ms: int,
    long_members: tuple[str, ...],
    short_members: tuple[str, ...],
    now_ms: int,
    proposed_outcome: AuthorityOutcome = AuthorityOutcome.PRE_FENCE_CONTINUITY,
    gap_kind: AuthorityGapAuditKind = AuthorityGapAuditKind.LATE_PRE_FENCE_CONTINUITY,
    source_entry_vacuum_id: str | None = None,
    source_generation_id: str | None = None,
    recovery_basis_digest: str | None = None,
) -> CoordinateSelectionMaterializationResult:
    control=await uow.instrument_selection.get_selection_control("SOR-1H-001") if spec_id==ORB_SELECTION_SPEC_ID else None
    audit_id = _gap_audit_id(
        spec_id=spec_id,
        session_start_ms=session_start_ms,
        gap_kind=gap_kind,
        proposed_outcome=proposed_outcome,
        selection_epoch_id=None if control is None else control.selection_epoch_id,source_generation_id=source_generation_id,source_entry_vacuum_id=source_entry_vacuum_id,
        recovery_basis_digest=recovery_basis_digest,
    )
    existing = await uow.instrument_selection.get_authority_gap_audit(
        audit_id,
        for_update=True,
    )
    if existing is None:
        audit = build_pending_authority_gap_audit(
            authority_gap_audit_id=audit_id,
            selection_spec_id=spec_id,
            session_start_ms=session_start_ms,
            gap_kind=gap_kind,
            proposed_authority_outcome=proposed_outcome,
            unauthorized_from_close_time_ms=session_start_ms
            + daily_first_offset_ms(spec_id),
            detector_semantic_digest=_sor_detector_semantic_digest(spec_id),
            created_at_ms=now_ms,
            source_entry_vacuum_id=source_entry_vacuum_id,
            source_generation_id=source_generation_id,
        )
        await uow.instrument_selection.add_pending_authority_gap_audit(audit)
    else:
        audit = existing
    scopes = _pair_scopes(
        selection_spec_id=spec_id,
        long_members=long_members,
        short_members=short_members,
    )
    return CoordinateSelectionMaterializationResult(
        disposition=MaterializationDisposition.GAP_AUDIT_PENDING,
        authority_gap_audit_id=audit.authority_gap_audit_id,
        reason_code=(
            f"AUDIT_REQUIRED:{len(scopes)}_SCOPES:{audit.gap_kind.value}"
        ),
    )


def _gap_audit_id(
    *,
    spec_id: str,
    session_start_ms: int,
    gap_kind: AuthorityGapAuditKind,
    proposed_outcome: AuthorityOutcome,
    selection_epoch_id: str | None=None,
    source_generation_id: str | None=None,
    source_entry_vacuum_id: str | None=None,
    recovery_basis_digest: str | None = None,
) -> str:
    if spec_id==ORB_SELECTION_SPEC_ID:
        if recovery_basis_digest is not None:
            return "gap-audit:orb:recovery:" + canonical_digest({
                "spec": spec_id, "session": session_start_ms,
                "kind": gap_kind.value, "outcome": proposed_outcome.value,
                "recovery_basis": recovery_basis_digest,
            })[7:]
        return "gap-audit:orb:"+canonical_digest({"spec":spec_id,"session":session_start_ms,"epoch":selection_epoch_id,
            "generation":source_generation_id,"vacuum":source_entry_vacuum_id,"kind":gap_kind.value,"outcome":proposed_outcome.value})[7:]
    return (
        f"gap-audit:{spec_id}:{session_start_ms}:"
        f"{gap_kind.value}:{proposed_outcome.value}"
    )


async def _coordinate_orb_static_selection(*,uow: KernelUnitOfWork,request: CoordinateSelectionMaterializationRequest,
    control: SelectionControl,pair: UniverseAuthorityPair,long_members: tuple[str,...],short_members: tuple[str,...],now_ms: int) -> CoordinateSelectionMaterializationResult:
    if now_ms<request.session_start_ms+HOUR_MS:
        return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.NOT_DUE)
    if control.pending_authorization_id is None or control.rollback_baseline_id is None or control.selection_epoch_id is None:
        return _blocked('ORB_STATIC_SOURCE_MISSING')
    baseline=await uow.instrument_selection.get_orb_static_baseline(control.rollback_baseline_id)
    members=await uow.strategy_universes.get_members(baseline.source_events[0].universe_version_id)
    source=OrbStaticMaterializationSource(session_start_ms=request.session_start_ms,selection_epoch_id=control.selection_epoch_id,rollback_baseline_id=baseline.rollback_baseline_id)
    gid='generation:orb:static:'+canonical_digest({'authorization':control.pending_authorization_id,'session':request.session_start_ms})[7:]
    generation=await uow.instrument_selection.get_materialization_generation(gid,for_update=True)
    if now_ms>=request.session_start_ms+23*HOUR_MS and (generation is None or generation.lifecycle_state in {
        MaterializationGenerationState.PENDING,MaterializationGenerationState.DESIRED}):
        return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.WAITING_SELECTION,
            reason_code='ORB_SESSION_HAS_NO_FUTURE_CLOSE')
    vacuum=await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=control.strategy_group_id,selection_spec_id=control.selection_spec_id,for_update=True)
    if generation is None:
        previous=await uow.instrument_selection.get_current_authority_projection(control.selection_spec_id)
        digest=selected_member_set_digest(members)
        generation=MaterializationGeneration(materialization_generation_id=gid,selection_spec_id=control.selection_spec_id,
            strategy_group_id=control.strategy_group_id,strategy_version_id=baseline.strategy_version_id,selection_mode=SelectionMode.STATIC_BASELINE,
            selection_snapshot_id=None,rollback_baseline_id=baseline.rollback_baseline_id,session_start_ms=request.session_start_ms,
            previous_long_universe_version_id=pair.long_universe_version_id,previous_short_universe_version_id=pair.short_universe_version_id,
            desired_member_count=len(members),semantic_digest=canonical_digest({'static_owner':control.pending_authorization_id,'baseline':baseline.semantic_digest,'session':request.session_start_ms,'previous_pair':pair.model_dump()}),
            lifecycle_state=MaterializationGenerationState.PENDING,fallback_reason_code=None,projection_version=1,created_at_ms=now_ms,desired_at_ms=None,
            selection_epoch_id=control.selection_epoch_id,selection_control_version=control.control_version,activation_authorization_id=control.pending_authorization_id,previous_entry_authorized=previous is None or not previous.authority.blocks_new_entry,
            previous_selection_authority_id=None if previous is None else previous.authority.selection_authority_id)
        targets=tuple(MaterializationTarget(event_spec_id=e,position_side="long" if i==1 else "short",expected_member_set_digest=digest,materialization_order=i)
            for i,e,side in ((1,ORB_EVENT_SPEC_IDS[0],'long'),(2,ORB_EVENT_SPEC_IDS[1],'short')))
        if vacuum is not None:
            if vacuum.state is not StrategyEntryVacuumState.RECONFIGURING or vacuum.source_generation_id is None or vacuum.drained_at_ms is None or vacuum.resolved_at_ms is not None:
                return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.WAITING_VACUUM,
                    entry_vacuum_id=vacuum.entry_vacuum_id,reason_code='ORB_STATIC_PREVIOUS_FENCE_NOT_DRAINED')
            prior=await uow.instrument_selection.get_materialization_generation(vacuum.source_generation_id,for_update=True)
            if prior is None or prior.session_start_ms is None or prior.session_start_ms>=request.session_start_ms:
                return _blocked('ORB_STATIC_PREVIOUS_GENERATION_NOT_OLDER')
            if not await uow.strategy_universes.materialization_slot_available(gid,replacing_generation_id=prior.materialization_generation_id):
                return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.WAITING_VACUUM,
                    entry_vacuum_id=vacuum.entry_vacuum_id,reason_code='GLOBAL_WARMING_SLOT_BUSY')
            if await uow.instrument_selection.entry_vacuum_has_drain_blockers(strategy_group_id=control.strategy_group_id):
                return _blocked('ORB_STATIC_PREVIOUS_ENTRY_DRAIN_REQUIRED')
            await _abandon_generation_targets(uow=uow,generation_id=prior.materialization_generation_id,
                reason_code='superseded_by_owner_static_retry',attempted_at_ms=now_ms)
            continued=await uow.instrument_selection.supersede_generation_and_retarget_vacuum(previous_generation=prior,
                replacement_generation=generation,replacement_targets=targets,vacuum=vacuum,superseded_at_ms=now_ms)
            return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.GENERATION_DESIRED,
                materialization_generation_id=continued.materialization_generation_id,entry_vacuum_id=vacuum.entry_vacuum_id,
                reason_code='ORB_STATIC_RETRY_RETAINED_DRAINED_FENCE')
        await uow.instrument_selection.supersede_unfenced_orb_static_generations(replacement_generation=generation,superseded_at_ms=now_ms)
        await uow.instrument_selection.add_pending_materialization_generation(generation,targets=targets)
        return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.GENERATION_PENDING,materialization_generation_id=gid)
    if generation.lifecycle_state is MaterializationGenerationState.PENDING:
        await uow.instrument_selection.mark_materialization_generation_desired(gid,expected_projection_version=generation.projection_version,desired_at_ms=now_ms)
        return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.GENERATION_DESIRED,materialization_generation_id=gid)
    if generation.lifecycle_state is MaterializationGenerationState.DESIRED and vacuum is None:
        if not await uow.strategy_universes.materialization_slot_available(gid):
            return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.GENERATION_DESIRED,materialization_generation_id=gid,reason_code='GLOBAL_WARMING_SLOT_BUSY')
        vacuum=StrategyEntryVacuum(entry_vacuum_id='vacuum:orb:static:'+gid.rsplit(':',1)[1],strategy_group_id=control.strategy_group_id,
            selection_spec_id=control.selection_spec_id,period_anchor_ms=request.session_start_ms,source_generation_id=gid,state=StrategyEntryVacuumState.DRAINING_ENTRY,
            fenced_at_ms=now_ms,drained_at_ms=None,resolved_at_ms=None,first_blocker='OWNER_STATIC_ROLLBACK',projection_version=2)
        await uow.instrument_selection.open_generation_entry_vacuum(vacuum,expected_generation_version=generation.projection_version)
        return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.WAITING_VACUUM,materialization_generation_id=gid,entry_vacuum_id=vacuum.entry_vacuum_id)
    if vacuum is not None and vacuum.source_generation_id==gid and vacuum.state is StrategyEntryVacuumState.RECONFIGURING:
        return await _coordinate_generation_materialization(uow=uow,generation=generation,vacuum=vacuum,snapshot=source,selected_members=members,
            previous_long_members=long_members,previous_short_members=short_members,now_ms=now_ms,materialization_timeout_ms=_MATERIALIZATION_TIMEOUT_MS)
    return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.WAITING_VACUUM,materialization_generation_id=gid)


async def _coordinate_generation_materialization(
    *,
    uow: KernelUnitOfWork,
    generation: MaterializationGeneration,
    vacuum: StrategyEntryVacuum,
    snapshot: SelectionSnapshot | OrbStaticMaterializationSource,
    selected_members: tuple[str, ...],
    previous_long_members: tuple[str, ...],
    previous_short_members: tuple[str, ...],
    now_ms: int,
    materialization_timeout_ms: int,
) -> CoordinateSelectionMaterializationResult:
    if generation.lifecycle_state not in {
        MaterializationGenerationState.MATERIALIZING,
        MaterializationGenerationState.STAGED,
    }:
        return _blocked(f"GENERATION_{generation.lifecycle_state.value}")
    if (
        generation.selection_snapshot_id != snapshot.selection_snapshot_id
        or generation.session_start_ms != snapshot.session_start_ms
        or generation.desired_member_count != len(selected_members)
    ):
        return _blocked("GENERATION_SNAPSHOT_IDENTITY_CONFLICT")
    fallback_previous_audit_id = _gap_audit_id(
        spec_id=generation.selection_spec_id,
        session_start_ms=snapshot.session_start_ms,
        gap_kind=AuthorityGapAuditKind.ENTRY_VACUUM,
        proposed_outcome=AuthorityOutcome.FALLBACK_PREVIOUS,selection_epoch_id=generation.selection_epoch_id,
        source_generation_id=generation.materialization_generation_id,source_entry_vacuum_id=vacuum.entry_vacuum_id,
    )
    fallback_previous_audit = await uow.instrument_selection.get_authority_gap_audit(
        fallback_previous_audit_id,
        for_update=True,
    )
    if fallback_previous_audit is not None:
        if fallback_previous_audit.state.value == "FAILED":
            return _blocked(
                fallback_previous_audit.first_blocker
                or "FALLBACK_AUTHORITY_GAP_AUDIT_FAILED"
            )
        return CoordinateSelectionMaterializationResult(
            disposition=MaterializationDisposition.GAP_AUDIT_PENDING,
            selection_snapshot_id=snapshot.selection_snapshot_id,
            materialization_generation_id=generation.materialization_generation_id,
            entry_vacuum_id=vacuum.entry_vacuum_id,
            authority_gap_audit_id=(
                fallback_previous_audit.authority_gap_audit_id
            ),
            reason_code=(
                f"FALLBACK_AUDIT_{fallback_previous_audit.state.value}"
            ),
        )
    # Retargeting a continuously open Vacuum does not rewrite its original
    # fence/drain evidence. Each replacement Generation has its own budget.
    materialization_started_at_ms = max(
        vacuum.fenced_at_ms, generation.desired_at_ms or generation.created_at_ms,
    )
    if now_ms - materialization_started_at_ms >= materialization_timeout_ms:
        return await _prepare_generation_fallback_previous(
            uow=uow,
            generation=generation,
            vacuum=vacuum,
            snapshot=snapshot,
            selected_members=selected_members,
            previous_long_members=previous_long_members,
            previous_short_members=previous_short_members,
            now_ms=now_ms,
            reason_code="materialization_timeout",
        )
    member_digest = selected_member_set_digest(selected_members)
    context = await uow.strategy_universes.resolve_install_context(
        runtime_profile_id="tiny-live-v1",
        event_id=strategy_contract_for(
            daily_event_spec_ids(generation.selection_spec_id)[0]
        ).event_id,
    )
    long_request = UniverseInstallRequest(
        event_spec_id=daily_event_spec_ids(generation.selection_spec_id)[0],
        runtime_profile_id="tiny-live-v1",
        owner_policy_id=context.owner_policy_id,
        exchange_instrument_ids=selected_members,
        source_kind="static_baseline" if generation.selection_mode is SelectionMode.STATIC_BASELINE else "dynamic_selection",
        materialization_generation_id=generation.materialization_generation_id,
        expected_member_set_digest=member_digest,
        installed_at_ms=now_ms,
    )
    long_install = await install_strategy_universe(uow, long_request)
    if long_install.status is UniverseInstallStatus.WARMING_UNIVERSE_ALREADY_EXISTS:
        return CoordinateSelectionMaterializationResult(
            disposition=MaterializationDisposition.LONG_WARMING,
            selection_snapshot_id=snapshot.selection_snapshot_id,
            materialization_generation_id=generation.materialization_generation_id,
            entry_vacuum_id=vacuum.entry_vacuum_id,
            reason_code="GLOBAL_WARMING_SLOT_OCCUPIED",
        )
    if long_install.universe is None:
        return _blocked("LONG_TARGET_UNIVERSE_MISSING")
    if long_install.status in {
        UniverseInstallStatus.INSTALLED,
        UniverseInstallStatus.ALREADY_WARMING,
    }:
        long_stage = await advance_strategy_universe(
            uow,
            UniverseActivationRequest(
                universe_version_id=long_install.universe.universe_version_id,
                attempted_at_ms=now_ms,
                operation=UniverseActivationOperation.STAGE_DYNAMIC,
                materialization_generation_id=generation.materialization_generation_id,
            ),
        )
        if long_stage.status is not UniverseActivationStatus.STAGED:
            if (
                long_stage.reason_code is not None
                and long_stage.reason_code not in _TRANSIENT_WARMING_BLOCKERS
            ):
                return await _prepare_generation_fallback_previous(
                    uow=uow,
                    generation=generation,
                    vacuum=vacuum,
                    snapshot=snapshot,
                    selected_members=selected_members,
                    previous_long_members=previous_long_members,
                    previous_short_members=previous_short_members,
                    now_ms=now_ms,
                    reason_code=f"long_{long_stage.reason_code.lower()}",
                )
            return CoordinateSelectionMaterializationResult(
                disposition=MaterializationDisposition.LONG_WARMING,
                selection_snapshot_id=snapshot.selection_snapshot_id,
                materialization_generation_id=generation.materialization_generation_id,
                entry_vacuum_id=vacuum.entry_vacuum_id,
                reason_code=long_stage.reason_code or "LONG_WARMING",
            )

    short_context = await uow.strategy_universes.resolve_install_context(
        runtime_profile_id="tiny-live-v1",
        event_id=strategy_contract_for(
            daily_event_spec_ids(generation.selection_spec_id)[1]
        ).event_id,
    )
    short_request = UniverseInstallRequest(
        event_spec_id=daily_event_spec_ids(generation.selection_spec_id)[1],
        runtime_profile_id="tiny-live-v1",
        owner_policy_id=short_context.owner_policy_id,
        exchange_instrument_ids=selected_members,
        source_kind="static_baseline" if generation.selection_mode is SelectionMode.STATIC_BASELINE else "dynamic_selection",
        materialization_generation_id=generation.materialization_generation_id,
        expected_member_set_digest=member_digest,
        installed_at_ms=now_ms,
    )
    short_install = await install_strategy_universe(uow, short_request)
    if short_install.status is UniverseInstallStatus.WARMING_UNIVERSE_ALREADY_EXISTS:
        return CoordinateSelectionMaterializationResult(
            disposition=MaterializationDisposition.SHORT_WARMING,
            selection_snapshot_id=snapshot.selection_snapshot_id,
            materialization_generation_id=generation.materialization_generation_id,
            entry_vacuum_id=vacuum.entry_vacuum_id,
            reason_code="GLOBAL_WARMING_SLOT_OCCUPIED",
        )
    if short_install.universe is None:
        return _blocked("SHORT_TARGET_UNIVERSE_MISSING")
    if short_install.status in {
        UniverseInstallStatus.INSTALLED,
        UniverseInstallStatus.ALREADY_WARMING,
    }:
        short_stage = await advance_strategy_universe(
            uow,
            UniverseActivationRequest(
                universe_version_id=short_install.universe.universe_version_id,
                attempted_at_ms=now_ms,
                operation=UniverseActivationOperation.STAGE_DYNAMIC,
                materialization_generation_id=generation.materialization_generation_id,
            ),
        )
        if short_stage.status is not UniverseActivationStatus.STAGED:
            if (
                short_stage.reason_code is not None
                and short_stage.reason_code not in _TRANSIENT_WARMING_BLOCKERS
            ):
                return await _prepare_generation_fallback_previous(
                    uow=uow,
                    generation=generation,
                    vacuum=vacuum,
                    snapshot=snapshot,
                    selected_members=selected_members,
                    previous_long_members=previous_long_members,
                    previous_short_members=previous_short_members,
                    now_ms=now_ms,
                    reason_code=f"short_{short_stage.reason_code.lower()}",
                )
            return CoordinateSelectionMaterializationResult(
                disposition=MaterializationDisposition.SHORT_WARMING,
                selection_snapshot_id=snapshot.selection_snapshot_id,
                materialization_generation_id=generation.materialization_generation_id,
                entry_vacuum_id=vacuum.entry_vacuum_id,
                reason_code=short_stage.reason_code or "SHORT_WARMING",
            )

    union_long_members = tuple(sorted(set(previous_long_members) | set(selected_members)))
    union_short_members = tuple(
        sorted(set(previous_short_members) | set(selected_members))
    )
    return await _prepare_gap_audit(
        uow=uow,
        spec_id=generation.selection_spec_id,
        session_start_ms=snapshot.session_start_ms,
        long_members=union_long_members,
        short_members=union_short_members,
        now_ms=now_ms,
        proposed_outcome=AuthorityOutcome.ACTIVE_NEW,
        gap_kind=AuthorityGapAuditKind.ENTRY_VACUUM,
        source_entry_vacuum_id=vacuum.entry_vacuum_id,
        source_generation_id=generation.materialization_generation_id,
    )


async def _prepare_generation_fallback_previous(
    *,
    uow: KernelUnitOfWork,
    generation: MaterializationGeneration,
    vacuum: StrategyEntryVacuum,
    snapshot: SelectionSnapshot | OrbStaticMaterializationSource,
    selected_members: tuple[str, ...],
    previous_long_members: tuple[str, ...],
    previous_short_members: tuple[str, ...],
    now_ms: int,
    reason_code: str,
) -> CoordinateSelectionMaterializationResult:
    if generation.selection_spec_id==ORB_SELECTION_SPEC_ID:
        previous=await uow.instrument_selection.get_current_authority_projection(generation.selection_spec_id)
        if previous is not None and previous.authority.authority_outcome is AuthorityOutcome.VALID_EMPTY:
            await _abandon_generation_targets(uow=uow,generation_id=generation.materialization_generation_id,
                reason_code='no_previous_entry_authority_after_empty',attempted_at_ms=now_ms)
            await uow.instrument_selection.mark_orb_failed_without_previous_authority(generation=generation,vacuum=vacuum,failed_at_ms=now_ms)
            return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition.WAITING_SELECTION,
                materialization_generation_id=generation.materialization_generation_id,entry_vacuum_id=vacuum.entry_vacuum_id,
                reason_code='NO_PREVIOUS_ENTRY_AUTHORITY_AFTER_EMPTY')
    activation_audit = await uow.instrument_selection.get_authority_gap_audit(
        _gap_audit_id(
            spec_id=generation.selection_spec_id,
            session_start_ms=snapshot.session_start_ms,
            gap_kind=AuthorityGapAuditKind.ENTRY_VACUUM,
            proposed_outcome=AuthorityOutcome.ACTIVE_NEW,selection_epoch_id=generation.selection_epoch_id,
            source_generation_id=generation.materialization_generation_id,source_entry_vacuum_id=vacuum.entry_vacuum_id,
        ),
        for_update=True,
    )
    if activation_audit is not None and activation_audit.state.value == "PENDING":
        await uow.instrument_selection.fail_authority_gap_audit(
            fail_authority_gap_audit(
                activation_audit,
                first_blocker="ACTIVATION_REPLACED_BY_FALLBACK",
            ),
            failed_at_ms=now_ms,
        )
    await _abandon_generation_targets(
        uow=uow,
        generation_id=generation.materialization_generation_id,
        reason_code=reason_code,
        attempted_at_ms=now_ms,
    )
    await uow.instrument_selection.mark_generation_fallback_previous_pending(
        generation=generation,
        vacuum=vacuum,
        reason_code=reason_code,
        marked_at_ms=now_ms,
    )
    union_long_members = tuple(sorted(set(previous_long_members) | set(selected_members)))
    union_short_members = tuple(
        sorted(set(previous_short_members) | set(selected_members))
    )
    return await _prepare_gap_audit(
        uow=uow,
        spec_id=generation.selection_spec_id,
        session_start_ms=snapshot.session_start_ms,
        long_members=union_long_members,
        short_members=union_short_members,
        now_ms=now_ms,
        proposed_outcome=AuthorityOutcome.FALLBACK_PREVIOUS,
        gap_kind=AuthorityGapAuditKind.ENTRY_VACUUM,
        source_entry_vacuum_id=vacuum.entry_vacuum_id,
        source_generation_id=generation.materialization_generation_id,
    )


async def _abandon_generation_targets(
    *,
    uow: KernelUnitOfWork,
    generation_id: str,
    reason_code: str,
    attempted_at_ms: int,
) -> None:
    targets = await uow.strategy_universes.get_generation_universe_targets(
        generation_id,
        for_update=True,
    )
    for target in targets:
        if target.lifecycle_state.value == "abandoned":
            continue
        await abandon_strategy_universe(
            uow,
            AbandonStrategyUniverseRequest(
                universe_version_id=target.universe_version_id,
                reason_code=reason_code,
                attempted_at_ms=attempted_at_ms,
            ),
        )


class _DailyControlLineage(TypedDict, total=False):
    selection_epoch_id: str
    selection_control_version: int
    activation_authorization_id: str | None


def _daily_control_lineage(
    *,
    selection_spec_id: str,
    control: SelectionControl | None,
    outcome: AuthorityOutcome,
) -> _DailyControlLineage:
    if selection_spec_id != ORB_SELECTION_SPEC_ID:
        return {}
    if (
        control is None
        or control.selection_spec_id != selection_spec_id
        or control.selection_epoch_id is None
    ):
        raise ValueError(
            "hourly ORB Authority requires current exact Selection control"
        )
    activates = (
        control.pending_selection_mode is SelectionMode.DYNAMIC_SELECTION
        and outcome
        in {
            AuthorityOutcome.ACTIVE_NEW,
            AuthorityOutcome.NO_CHANGE,
            AuthorityOutcome.VALID_EMPTY,
        }
    )
    static_activates=control.pending_selection_mode is SelectionMode.STATIC_BASELINE and outcome is AuthorityOutcome.ACTIVE_NEW
    return {
        "selection_epoch_id": control.selection_epoch_id,
        "selection_control_version": control.control_version + int(activates or static_activates),
        "activation_authorization_id": control.pending_authorization_id
        if activates or static_activates
        else None,
    }


def _build_continuity_authority(
    *,
    selection_spec_id: str,
    session_start_ms: int,
    pair: UniverseAuthorityPair,
    predecessor: SelectionSessionAuthority,
    owner_control_version: int,
    created_at_ms: int,
    selection_control: SelectionControl | None = None,
) -> SelectionSessionAuthority:
    sequence = 1
    first_eligible = session_start_ms + daily_first_offset_ms(selection_spec_id)
    return SelectionSessionAuthority(
        **_daily_control_lineage(
            selection_spec_id=selection_spec_id,
            control=selection_control,
            outcome=AuthorityOutcome.PRE_FENCE_CONTINUITY,
        ),
        selection_authority_id=(
            f"selection-authority:{selection_spec_id}:{session_start_ms}:{sequence}"
        ),
        selection_spec_id=selection_spec_id,
        session_start_ms=session_start_ms,
        decision_boundary_ms=session_start_ms + 4 * INTERVAL_MS,
        authority_sequence=sequence,
        selection_mode=SelectionMode.DYNAMIC_SELECTION,
        selection_snapshot_id=None,
        continued_from_selection_authority_id=predecessor.selection_authority_id,
        continuity_source_kind=ContinuitySourceKind.SELECTION_AUTHORITY,
        authority_gap_audit_id=None,
        materialization_generation_id=None,
        owner_control_version=owner_control_version,
        authority_outcome=AuthorityOutcome.PRE_FENCE_CONTINUITY,
        authorized_pair=pair,
        grant_proof=AuthorityGrantProof(
            kind=AuthorityGrantProofKind.CONTINUOUS_ELIGIBLE_CLOSES,
            predecessor_authority_id=predecessor.selection_authority_id,
            authority_gap_audit_id=None,
        ),
        effective_from_ms=(created_at_ms if selection_spec_id == ORB_SELECTION_SPEC_ID else session_start_ms + 4 * INTERVAL_MS),
        first_eligible_close_time_ms=first_eligible,
        expires_at_ms=daily_authority_expires_at(selection_spec_id, session_start_ms),
        reason_code="AWAITING_SELECTION",
        created_at_ms=created_at_ms,
    )


def _predecessor_covers_current_pair(
    *,
    predecessor: SelectionSessionAuthority,
    pair: UniverseAuthorityPair,
    owner_control_version: int,
    decision_boundary_ms: int,
) -> bool:
    return bool(
        predecessor.authority_outcome
        in {
            AuthorityOutcome.PRE_FENCE_CONTINUITY,
            AuthorityOutcome.ACTIVE_NEW,
            AuthorityOutcome.NO_CHANGE,
            AuthorityOutcome.FALLBACK_PREVIOUS,
        }
        and predecessor.authorized_pair == pair
        and predecessor.owner_control_version == owner_control_version
        and predecessor.expires_at_ms == decision_boundary_ms
    )


def _build_no_change_successor(
    *,
    predecessor: SelectionSessionAuthority,
    selection_snapshot_id: str,
    created_at_ms: int,
) -> SelectionSessionAuthority:
    values = predecessor.model_dump()
    values.update(
        {
            "selection_authority_id": (
                f"selection-authority:{predecessor.selection_spec_id}:"
                f"{predecessor.session_start_ms}:"
                f"{predecessor.authority_sequence + 1}"
            ),
            "authority_sequence": predecessor.authority_sequence + 1,
            "selection_snapshot_id": selection_snapshot_id,
            "continued_from_selection_authority_id": (
                predecessor.selection_authority_id
            ),
            "continuity_source_kind": ContinuitySourceKind.SELECTION_AUTHORITY,
            "authority_gap_audit_id": None,
            "authority_outcome": AuthorityOutcome.NO_CHANGE,
            "grant_proof": AuthorityGrantProof(
                kind=AuthorityGrantProofKind.CONTINUOUS_ELIGIBLE_CLOSES,
                predecessor_authority_id=predecessor.selection_authority_id,
                authority_gap_audit_id=None,
            ),
            "reason_code": "SELECTED_MEMBERS_UNCHANGED",
            "effective_from_ms": created_at_ms,
            "first_eligible_close_time_ms": next_daily_eligible_close(
                selection_spec_id=predecessor.selection_spec_id,
                session_start_ms=predecessor.session_start_ms,
                now_ms=created_at_ms,
            ),
            "created_at_ms": created_at_ms,
        }
    )
    return SelectionSessionAuthority.model_validate(values)


def _build_first_dynamic_no_change_authority(
    *,
    selection_spec_id: str,
    session_start_ms: int,
    selection_snapshot_id: str,
    pair: UniverseAuthorityPair,
    owner_control_version: int,
    current_projection: CurrentSelectionAuthority | None,
    created_at_ms: int,
    selection_control: SelectionControl | None = None,
) -> SelectionSessionAuthority:
    sequence = (
        1
        if current_projection is None
        or current_projection.authority.session_start_ms != session_start_ms
        else current_projection.authority.authority_sequence + 1
    )
    static_identity = (
        f"static-baseline:{pair.long_universe_version_id}:"
        f"{pair.short_universe_version_id}"
    )
    return SelectionSessionAuthority(
        **_daily_control_lineage(
            selection_spec_id=selection_spec_id,
            control=selection_control,
            outcome=AuthorityOutcome.NO_CHANGE,
        ),
        selection_authority_id=(
            f"selection-authority:{selection_spec_id}:{session_start_ms}:{sequence}"
        ),
        selection_spec_id=selection_spec_id,
        session_start_ms=session_start_ms,
        decision_boundary_ms=session_start_ms + 4 * INTERVAL_MS,
        authority_sequence=sequence,
        selection_mode=SelectionMode.DYNAMIC_SELECTION,
        selection_snapshot_id=selection_snapshot_id,
        continued_from_selection_authority_id=None,
        continuity_source_kind=ContinuitySourceKind.STATIC_BASELINE,
        authority_gap_audit_id=None,
        materialization_generation_id=None,
        owner_control_version=owner_control_version,
        authority_outcome=AuthorityOutcome.NO_CHANGE,
        authorized_pair=pair,
        grant_proof=AuthorityGrantProof(
            kind=AuthorityGrantProofKind.CONTINUOUS_ELIGIBLE_CLOSES,
            predecessor_authority_id=static_identity,
            authority_gap_audit_id=None,
        ),
        effective_from_ms=(created_at_ms if selection_spec_id == ORB_SELECTION_SPEC_ID else session_start_ms + 4 * INTERVAL_MS),
        first_eligible_close_time_ms=next_daily_eligible_close(
            selection_spec_id=selection_spec_id,
            session_start_ms=session_start_ms,
            now_ms=created_at_ms,
        ),
        expires_at_ms=daily_authority_expires_at(selection_spec_id, session_start_ms),
        reason_code="FIRST_DYNAMIC_MEMBERS_UNCHANGED",
        created_at_ms=created_at_ms,
    )


def _build_audited_authority(
    *,
    audit: AuthorityGapAudit,
    current_authority: CurrentSelectionAuthority | None,
    pair: UniverseAuthorityPair,
    owner_control_version: int,
    selection_snapshot_id: str | None,
    created_at_ms: int,
    selection_mode: SelectionMode = SelectionMode.DYNAMIC_SELECTION,
    reason_code: str | None = None,
    selection_control: SelectionControl | None = None,
) -> SelectionSessionAuthority:
    sequence = (
        1
        if current_authority is None
        or current_authority.authority.session_start_ms != audit.session_start_ms
        else current_authority.authority.authority_sequence + 1
    )
    if audit.first_eligible_close_time_ms is None:
        raise ValueError("complete Authority Gap Audit lacks first eligible close")
    return SelectionSessionAuthority(
        **_daily_control_lineage(
            selection_spec_id=audit.selection_spec_id,
            control=selection_control,
            outcome=audit.proposed_authority_outcome,
        ),
        selection_authority_id=(
            f"selection-authority:{audit.selection_spec_id}:"
            f"{audit.session_start_ms}:{sequence}"
        ),
        selection_spec_id=audit.selection_spec_id,
        session_start_ms=audit.session_start_ms,
        decision_boundary_ms=audit.session_start_ms + 4 * INTERVAL_MS,
        authority_sequence=sequence,
        selection_mode=selection_mode,
        selection_snapshot_id=selection_snapshot_id,
        continued_from_selection_authority_id=(
            None
            if current_authority is None
            or (
                audit.proposed_authority_outcome is AuthorityOutcome.FALLBACK_PREVIOUS
                and selection_mode is SelectionMode.STATIC_BASELINE
            )
            else (current_authority.authority.continued_from_selection_authority_id
                  if audit.selection_spec_id == ORB_SELECTION_SPEC_ID and audit.gap_kind is AuthorityGapAuditKind.OWNER_PAUSE
                  else current_authority.authority.selection_authority_id)
        ),
        continuity_source_kind=(
            ContinuitySourceKind.STATIC_BASELINE
            if audit.proposed_authority_outcome is AuthorityOutcome.FALLBACK_PREVIOUS
            and selection_mode is SelectionMode.STATIC_BASELINE
            else ContinuitySourceKind.AUTHORITY_GAP_AUDIT
        ),
        authority_gap_audit_id=audit.authority_gap_audit_id,
        materialization_generation_id=(
            audit.source_generation_id
            if audit.proposed_authority_outcome
            in {AuthorityOutcome.ACTIVE_NEW, AuthorityOutcome.FALLBACK_PREVIOUS}
            else None
        ),
        owner_control_version=owner_control_version,
        authority_outcome=audit.proposed_authority_outcome,
        authorized_pair=pair,
        grant_proof=AuthorityGrantProof(
            kind=AuthorityGrantProofKind.AUDITED_AUTHORITY_GAP,
            predecessor_authority_id=None,
            authority_gap_audit_id=audit.authority_gap_audit_id,
        ),
        effective_from_ms=created_at_ms,
        first_eligible_close_time_ms=audit.first_eligible_close_time_ms,
        expires_at_ms=daily_authority_expires_at(
            audit.selection_spec_id, audit.session_start_ms
        ),
        reason_code=reason_code or f"{audit.gap_kind.value}_COMPLETE",
        created_at_ms=created_at_ms,
    )


def _build_valid_empty_authority(
    *,
    selection_spec_id: str,
    snapshot: SelectionSnapshot,
    current_authority: CurrentSelectionAuthority | None,
    owner_control_version: int,
    created_at_ms: int,
    selection_control: SelectionControl | None = None,
) -> SelectionSessionAuthority:
    sequence = (
        1
        if current_authority is None
        or current_authority.authority.session_start_ms != snapshot.session_start_ms
        else current_authority.authority.authority_sequence + 1
    )
    return SelectionSessionAuthority(
        **_daily_control_lineage(
            selection_spec_id=selection_spec_id,
            control=selection_control,
            outcome=AuthorityOutcome.VALID_EMPTY,
        ),
        selection_authority_id=(
            f"selection-authority:{selection_spec_id}:"
            f"{snapshot.session_start_ms}:{sequence}"
        ),
        selection_spec_id=selection_spec_id,
        session_start_ms=snapshot.session_start_ms,
        decision_boundary_ms=snapshot.session_start_ms + 4 * INTERVAL_MS,
        authority_sequence=sequence,
        selection_mode=SelectionMode.DYNAMIC_SELECTION,
        selection_snapshot_id=snapshot.selection_snapshot_id,
        continued_from_selection_authority_id=(
            None
            if current_authority is None
            else current_authority.authority.selection_authority_id
        ),
        continuity_source_kind=ContinuitySourceKind.NONE,
        authority_gap_audit_id=None,
        materialization_generation_id=None,
        owner_control_version=owner_control_version,
        authority_outcome=AuthorityOutcome.VALID_EMPTY,
        authorized_pair=None,
        grant_proof=None,
        effective_from_ms=created_at_ms,
        first_eligible_close_time_ms=None,
        expires_at_ms=daily_authority_expires_at(
            selection_spec_id, snapshot.session_start_ms
        ),
        reason_code="NO_SELECTION_READY_MEMBERS",
        created_at_ms=created_at_ms,
    )


async def _resolve_staged_generation_target(
    *,
    uow: KernelUnitOfWork,
    audit: AuthorityGapAudit,
    now_ms: int,
) -> tuple[UniverseAuthorityPair, tuple[str, ...]] | None:
    generation_id = audit.source_generation_id
    if generation_id is None:
        return None
    generation = await uow.instrument_selection.get_materialization_generation(
        generation_id,
        for_update=True,
    )
    if (
        generation is None
        or generation.lifecycle_state is not MaterializationGenerationState.STAGED
        or generation.session_start_ms != audit.session_start_ms
        or (generation.selection_snapshot_id is None and generation.selection_mode is not SelectionMode.STATIC_BASELINE)
    ):
        return None
    if generation.selection_mode is SelectionMode.STATIC_BASELINE:
        if generation.rollback_baseline_id is None:return None
        baseline=await uow.instrument_selection.get_orb_static_baseline(generation.rollback_baseline_id)
        members=await uow.strategy_universes.get_members(baseline.source_events[0].universe_version_id)
    else:
        snapshot=await uow.instrument_selection.get_snapshot_disposition(selection_spec_id=audit.selection_spec_id,session_start_ms=audit.session_start_ms,for_update=True)
        if snapshot is None or snapshot.snapshot.selection_snapshot_id!=generation.selection_snapshot_id:return None
        members=snapshot.selected_members
    member_digest=selected_member_set_digest(members)
    long_context = await uow.strategy_universes.resolve_install_context(
        runtime_profile_id="tiny-live-v1",
        event_id=strategy_contract_for(
            daily_event_spec_ids(audit.selection_spec_id)[0]
        ).event_id,
    )
    short_context = await uow.strategy_universes.resolve_install_context(
        runtime_profile_id="tiny-live-v1",
        event_id=strategy_contract_for(
            daily_event_spec_ids(audit.selection_spec_id)[1]
        ).event_id,
    )
    long = await install_strategy_universe(
        uow,
        UniverseInstallRequest(
            event_spec_id=daily_event_spec_ids(audit.selection_spec_id)[0],
            runtime_profile_id="tiny-live-v1",
            owner_policy_id=long_context.owner_policy_id,
            exchange_instrument_ids=members,
            source_kind="static_baseline" if generation.selection_mode is SelectionMode.STATIC_BASELINE else "dynamic_selection",
            materialization_generation_id=generation_id,
            expected_member_set_digest=member_digest,
            installed_at_ms=now_ms,
        ),
    )
    short = await install_strategy_universe(
        uow,
        UniverseInstallRequest(
            event_spec_id=daily_event_spec_ids(audit.selection_spec_id)[1],
            runtime_profile_id="tiny-live-v1",
            owner_policy_id=short_context.owner_policy_id,
            exchange_instrument_ids=members,
            source_kind="static_baseline" if generation.selection_mode is SelectionMode.STATIC_BASELINE else "dynamic_selection",
            materialization_generation_id=generation_id,
            expected_member_set_digest=member_digest,
            installed_at_ms=now_ms,
        ),
    )
    if (
        long.status is not UniverseInstallStatus.ALREADY_STAGED
        or short.status is not UniverseInstallStatus.ALREADY_STAGED
        or long.universe is None
        or short.universe is None
    ):
        return None
    return (
        UniverseAuthorityPair(
            long_universe_version_id=long.universe.universe_version_id,
            short_universe_version_id=short.universe.universe_version_id,
        ),
        members,
    )


async def _resolve_fallback_previous_generation_source(
    *,
    uow: KernelUnitOfWork,
    audit: AuthorityGapAudit,
) -> tuple[UniverseAuthorityPair, tuple[str, ...]] | None:
    generation_id = audit.source_generation_id
    if generation_id is None:
        return None
    generation = await uow.instrument_selection.get_materialization_generation(
        generation_id,
        for_update=True,
    )
    if (
        generation is None
        or generation.lifecycle_state
        not in {
            MaterializationGenerationState.MATERIALIZING,
            MaterializationGenerationState.STAGED,
        }
        or generation.session_start_ms != audit.session_start_ms
        or (generation.selection_snapshot_id is None and generation.selection_mode is not SelectionMode.STATIC_BASELINE)
    ):
        return None
    if generation.selection_mode is SelectionMode.STATIC_BASELINE:
        if generation.rollback_baseline_id is None:return None
        baseline=await uow.instrument_selection.get_orb_static_baseline(generation.rollback_baseline_id)
        members=await uow.strategy_universes.get_members(baseline.source_events[0].universe_version_id)
    else:
        snapshot=await uow.instrument_selection.get_snapshot_disposition(selection_spec_id=audit.selection_spec_id,session_start_ms=audit.session_start_ms,for_update=True)
        if snapshot is None or snapshot.snapshot.selection_snapshot_id!=generation.selection_snapshot_id:return None
        members=snapshot.selected_members
    return (
        UniverseAuthorityPair(
            long_universe_version_id=(
                generation.previous_long_universe_version_id
            ),
            short_universe_version_id=(
                generation.previous_short_universe_version_id
            ),
        ),
        members,
    )


def _selection_control_allows_gap_completion(
    control: SelectionControl,
    *,
    session_start_ms: int,
) -> bool:
    return bool(
        control.selection_mode is SelectionMode.DYNAMIC_SELECTION
        or (
            control.selection_mode is SelectionMode.STATIC_BASELINE
            and control.pending_selection_mode is SelectionMode.DYNAMIC_SELECTION
            and control.pending_effective_period_anchor_ms is not None
            and (
                control.pending_effective_period_anchor_ms <= session_start_ms
                if control.selection_spec_id == ORB_SELECTION_SPEC_ID
                else control.pending_effective_period_anchor_ms == session_start_ms
            )
            and control.pending_authorization_id is not None
        )
    )


def _authority_disposition(
    outcome: AuthorityOutcome,
) -> MaterializationDisposition:
    return {
        AuthorityOutcome.ACTIVE_NEW: MaterializationDisposition.ACTIVE_NEW,
        AuthorityOutcome.FALLBACK_PREVIOUS: (
            MaterializationDisposition.FALLBACK_PREVIOUS
        ),
        AuthorityOutcome.PRE_FENCE_CONTINUITY: (
            MaterializationDisposition.PRE_FENCE_CONTINUITY
        ),
        AuthorityOutcome.NO_CHANGE: MaterializationDisposition.NO_CHANGE,
        AuthorityOutcome.VALID_EMPTY: MaterializationDisposition.VALID_EMPTY,
    }.get(outcome, MaterializationDisposition.BLOCKED)


def _build_pending_generation(
    *,
    snapshot: SelectionSnapshot,
    selected_members: tuple[str, ...],
    previous_pair: UniverseAuthorityPair,
    created_at_ms: int,
    selection_control: SelectionControl | None = None,
    previous_authority: SelectionSessionAuthority | None = None,
) -> tuple[MaterializationGeneration, tuple[MaterializationTarget, ...]]:
    member_digest = selected_member_set_digest(selected_members)
    generation_id = f"generation:{snapshot.selection_spec_id}:{snapshot.session_start_ms}"
    if isinstance(snapshot, OrbSessionSelectionSnapshot):
        generation_id = "generation:orb:" + canonical_digest({"snapshot": snapshot.selection_snapshot_id})[7:]
        if selection_control is None or selection_control.selection_epoch_id != snapshot.selection_epoch_id:
            raise ValueError("hourly ORB Generation requires exact current epoch")
    payload: dict[str,object] = {
        "materialization_generation_id": generation_id,
        "selection_snapshot_id": snapshot.selection_snapshot_id,
        "previous_pair": previous_pair.model_dump(mode="json"),
        "selected_member_set_digest": member_digest,
    }
    if snapshot.selection_spec_id==ORB_SELECTION_SPEC_ID:
        payload.update({"previous_entry_authorized":previous_authority is None or not previous_authority.blocks_new_entry,
            "previous_selection_authority_id":None if previous_authority is None else previous_authority.selection_authority_id})
    semantic_digest = "sha256:" + sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    generation = MaterializationGeneration(
        materialization_generation_id=generation_id,
        previous_entry_authorized=previous_authority is None or not previous_authority.blocks_new_entry,
        previous_selection_authority_id=None if previous_authority is None else previous_authority.selection_authority_id,
        selection_spec_id=snapshot.selection_spec_id,
        selection_epoch_id=snapshot.selection_epoch_id if isinstance(snapshot, OrbSessionSelectionSnapshot) else None,
        selection_control_version=selection_control.control_version if isinstance(snapshot, OrbSessionSelectionSnapshot) and selection_control is not None else None,
        strategy_group_id=snapshot.strategy_group_id,
        strategy_version_id=snapshot.strategy_version_id,
        selection_mode=SelectionMode.DYNAMIC_SELECTION,
        selection_snapshot_id=snapshot.selection_snapshot_id,
        rollback_baseline_id=None,
        session_start_ms=snapshot.session_start_ms,
        previous_long_universe_version_id=previous_pair.long_universe_version_id,
        previous_short_universe_version_id=previous_pair.short_universe_version_id,
        desired_member_count=len(selected_members),
        semantic_digest=semantic_digest,
        lifecycle_state=MaterializationGenerationState.PENDING,
        fallback_reason_code=None,
        projection_version=1,
        created_at_ms=created_at_ms,
        desired_at_ms=None,
    )
    return generation, (
        MaterializationTarget(
            event_spec_id=daily_event_spec_ids(snapshot.selection_spec_id)[0],
            position_side="long",
            expected_member_set_digest=member_digest,
            materialization_order=1,
        ),
        MaterializationTarget(
            event_spec_id=daily_event_spec_ids(snapshot.selection_spec_id)[1],
            position_side="short",
            expected_member_set_digest=member_digest,
            materialization_order=2,
        ),
    )


def _pair_scopes(
    *,
    selection_spec_id: str = "sor-dynamic-selection-v0",
    long_members: tuple[str, ...],
    short_members: tuple[str, ...],
) -> tuple[AuthorityGapScope, ...]:
    return tuple(
        sorted(
            (
                *(
                    AuthorityGapScope(
                        event_spec_id=daily_event_spec_ids(selection_spec_id)[0],
                        exchange_instrument_id=instrument_id,
                    )
                    for instrument_id in long_members
                ),
                *(
                    AuthorityGapScope(
                        event_spec_id=daily_event_spec_ids(selection_spec_id)[1],
                        exchange_instrument_id=instrument_id,
                    )
                    for instrument_id in short_members
                ),
            ),
            key=lambda item: (item.event_spec_id, item.exchange_instrument_id),
        )
    )


def _sor_detector_semantic_digest(
    selection_spec_id: str = "sor-dynamic-selection-v0",
) -> str:
    return build_registry_semantic_hash(
        (
            strategy_contract_for(daily_event_spec_ids(selection_spec_id)[0]),
            strategy_contract_for(daily_event_spec_ids(selection_spec_id)[1]),
        )
    )


def _build_owner_paused_authority(
    *,
    selection_spec_id: str,
    session_start_ms: int,
    selection_mode: SelectionMode,
    selection_snapshot_id: str | None,
    current_authority: CurrentSelectionAuthority | None,
    owner_control_version: int,
    created_at_ms: int,
    selection_control: SelectionControl | None = None,
) -> SelectionSessionAuthority:
    sequence = (
        1
        if current_authority is None
        or current_authority.authority.session_start_ms != session_start_ms
        else current_authority.authority.authority_sequence + 1
    )
    return SelectionSessionAuthority(
        **_daily_control_lineage(
            selection_spec_id=selection_spec_id,
            control=selection_control,
            outcome=AuthorityOutcome.OWNER_PAUSED_NOT_MATERIALIZED,
        ),
        selection_authority_id=(
            f"selection-authority:{selection_spec_id}:{session_start_ms}:{sequence}"
        ),
        selection_spec_id=selection_spec_id,
        session_start_ms=session_start_ms,
        decision_boundary_ms=session_start_ms + 4 * INTERVAL_MS,
        authority_sequence=sequence,
        selection_mode=selection_mode,
        selection_snapshot_id=selection_snapshot_id,
        continued_from_selection_authority_id=(
            None
            if current_authority is None
            else current_authority.authority.selection_authority_id
        ),
        continuity_source_kind=ContinuitySourceKind.NONE,
        authority_gap_audit_id=None,
        materialization_generation_id=None,
        owner_control_version=owner_control_version,
        authority_outcome=AuthorityOutcome.OWNER_PAUSED_NOT_MATERIALIZED,
        authorized_pair=None,
        grant_proof=None,
        effective_from_ms=created_at_ms,
        first_eligible_close_time_ms=None,
        expires_at_ms=daily_authority_expires_at(selection_spec_id, session_start_ms),
        reason_code="OWNER_PAUSE_PRECEDES_MATERIALIZATION",
        created_at_ms=created_at_ms,
    )


def _blocked(reason_code: str) -> CoordinateSelectionMaterializationResult:
    return CoordinateSelectionMaterializationResult(
        disposition=MaterializationDisposition.BLOCKED,
        reason_code=reason_code,
    )
