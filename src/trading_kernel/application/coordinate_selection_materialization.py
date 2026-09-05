"""Plan and coordinate one durable Dynamic Selection materialization step."""

from __future__ import annotations

import json
from collections.abc import Callable
from enum import StrEnum
from hashlib import sha256
from typing import Protocol

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
from src.trading_kernel.application.install_strategy_universe import (
    UniverseInstallRequest,
    UniverseInstallStatus,
    install_strategy_universe,
)
from src.trading_kernel.application.ports import KernelUnitOfWork, UnitOfWorkFactory
from src.trading_kernel.domain.instrument_selection import (
    INTERVAL_MS,
    SOR_LONG_EVENT_SPEC_ID,
    SOR_SHORT_EVENT_SPEC_ID,
    SelectionSnapshot,
)
from src.trading_kernel.domain.owner_control import StrategyEntryState
from src.trading_kernel.domain.selection_authority import (
    AuthorityGapAudit,
    AuthorityGapAuditKind,
    AuthorityGapScope,
    AuthorityGapScopeResult,
    AuthorityGrantProof,
    AuthorityGrantProofKind,
    AuthorityOutcome,
    ContinuitySourceKind,
    CurrentSelectionAuthority,
    MaterializationGeneration,
    MaterializationGenerationState,
    MaterializationTarget,
    SelectionControl,
    SelectionMode,
    SelectionSessionAuthority,
    UniverseAuthorityPair,
    build_pending_authority_gap_audit,
    complete_authority_gap_audit,
    fail_authority_gap_audit,
    next_canonical_eligible_close,
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
    snapshot: SelectionSnapshot | None
    selected_members: tuple[str, ...]
    continuity_exists: bool
    open_vacuum: bool

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
    first_eligible_close = next_canonical_eligible_close(
        session_start_ms=audit.session_start_ms,
        now_ms=now_ms,
    )
    audited_through = first_eligible_close - INTERVAL_MS
    if audited_through < audit.unauthorized_from_close_time_ms:
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

    first_pending_dynamic = (
        facts.selection_mode is SelectionMode.STATIC_BASELINE
        and facts.pending_selection_mode is SelectionMode.DYNAMIC_SELECTION
        and facts.pending_effective_session_start_ms == facts.session_start_ms
    )
    if facts.selection_mode is SelectionMode.STATIC_BASELINE and not first_pending_dynamic:
        return MaterializationPlan(
            disposition=MaterializationDisposition.STATIC_BASELINE
        )
    if facts.open_vacuum:
        return MaterializationPlan(
            disposition=MaterializationDisposition.WAITING_VACUUM
        )
    if first_pending_dynamic and facts.snapshot is None:
        return MaterializationPlan(
            disposition=MaterializationDisposition.KEEP_STATIC_PENDING_DYNAMIC
        )

    if facts.selection_mode is SelectionMode.DYNAMIC_SELECTION and not facts.continuity_exists:
        first_eligible = next_canonical_eligible_close(
            session_start_ms=facts.session_start_ms,
            now_ms=facts.now_ms,
        )
        late = facts.now_ms >= facts.session_start_ms + 5 * INTERVAL_MS
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
            first_eligible_close_time_ms=next_canonical_eligible_close(
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
    request: CoordinateSelectionMaterializationRequest,
    clock_ms: Callable[[], int],
) -> CoordinateSelectionMaterializationResult:
    """Advance exactly one no-network materialization state from PostgreSQL facts."""

    now_ms = clock_ms()
    async with uow_factory() as uow:
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
            SOR_LONG_EVENT_SPEC_ID
        )
        short_current = await uow.strategy_universes.get_current(
            SOR_SHORT_EVENT_SPEC_ID
        )
        if long_current is None or short_current is None:
            return _blocked("CURRENT_UNIVERSE_PAIR_MISSING")
        long_members = await uow.strategy_universes.get_members(
            long_current.universe_version_id
        )
        short_members = await uow.strategy_universes.get_members(
            short_current.universe_version_id
        )
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
        vacuum = await uow.instrument_selection.get_current_entry_vacuum(
            strategy_group_id=request.strategy_group_id,
            selection_spec_id=spec.selection_spec_id,
            for_update=True,
        )
        current_pair = UniverseAuthorityPair(
            long_universe_version_id=long_current.universe_version_id,
            short_universe_version_id=short_current.universe_version_id,
        )
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
                        session_start_ms=request.session_start_ms,
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
            else:
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
                reason_code="OWNER_PAUSE_PRECEDES_MATERIALIZATION",
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
            and vacuum.session_start_ms < request.session_start_ms
            and snapshot is not None
            and selection_control.selection_mode is SelectionMode.STATIC_BASELINE
            and selection_control.pending_selection_mode
            is SelectionMode.DYNAMIC_SELECTION
            and selection_control.pending_effective_session_start_ms
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
                return _blocked("OWNER_PAUSED_VALID_EMPTY_REQUIRES_RESOLUTION")
            replacement, replacement_targets = _build_pending_generation(
                snapshot=snapshot.snapshot,
                selected_members=snapshot.selected_members,
                previous_pair=current_pair,
                created_at_ms=now_ms,
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
            and vacuum.session_start_ms < request.session_start_ms
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
                selection_control.pending_effective_session_start_ms
            ),
            owner_entry_state=owner_control.entry_state,
            current_long_members=long_members,
            current_short_members=short_members,
            snapshot=None if snapshot is None else snapshot.snapshot,
            selected_members=() if snapshot is None else snapshot.selected_members,
            continuity_exists=continuity_exists,
            open_vacuum=bool(vacuum and vacuum.blocks_new_entry),
        )
        plan = plan_selection_materialization(facts)

        if plan.disposition is MaterializationDisposition.PRE_FENCE_CONTINUITY:
            pair = current_pair
            if plan.requires_gap_audit:
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
            first_pending_dynamic = (
                selection_control.selection_mode is SelectionMode.STATIC_BASELINE
                and selection_control.pending_selection_mode
                is SelectionMode.DYNAMIC_SELECTION
            )
            if first_pending_dynamic:
                authority = _build_first_dynamic_no_change_authority(
                    selection_spec_id=spec.selection_spec_id,
                    session_start_ms=request.session_start_ms,
                    selection_snapshot_id=snapshot.snapshot.selection_snapshot_id,
                    pair=pair,
                    owner_control_version=owner_control.control_version,
                    current_projection=current_authority,
                    created_at_ms=now_ms,
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
                    session_start_ms=request.session_start_ms,
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
                generation_vacuum = StrategyEntryVacuum(
                    entry_vacuum_id=(
                        f"vacuum:{request.strategy_group_id}:"
                        f"{request.session_start_ms}:generation"
                    ),
                    strategy_group_id=request.strategy_group_id,
                    selection_spec_id=spec.selection_spec_id,
                    session_start_ms=request.session_start_ms,
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
        if audit.detector_semantic_digest != _sor_detector_semantic_digest():
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
            SOR_LONG_EVENT_SPEC_ID
        )
        short_current = await uow.strategy_universes.get_current(
            SOR_SHORT_EVENT_SPEC_ID
        )
        if long_current is None or short_current is None:
            return _blocked("AUTHORITY_GAP_AUDIT_PAIR_MISSING")
        initial_long_current = long_current
        initial_short_current = short_current
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
    scopes = _pair_scopes(long_members=long_members, short_members=short_members)
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
            await uow.instrument_selection.fail_authority_gap_audit(
                failed,
                failed_at_ms=completed_at_ms,
            )
        return _blocked("AUTHORITY_GAP_AUDIT_INCOMPLETE")
    async with uow_factory() as uow:
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
            SOR_LONG_EVENT_SPEC_ID
        )
        short_current = await uow.strategy_universes.get_current(
            SOR_SHORT_EVENT_SPEC_ID
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
                None if snapshot is None else snapshot.snapshot.selection_snapshot_id
            ),
            created_at_ms=completed_at_ms,
            selection_mode=(
                SelectionMode.STATIC_BASELINE
                if selection_control.selection_mode is SelectionMode.STATIC_BASELINE
                else SelectionMode.DYNAMIC_SELECTION
            ),
            reason_code=(
                vacuum.first_blocker
                if vacuum is not None
                and audit.proposed_authority_outcome
                is AuthorityOutcome.FALLBACK_PREVIOUS
                else None
            ),
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
            await uow.instrument_selection.add_authority_and_set_current(
                authority,
                expected_current_version=(
                    None
                    if current_authority is None
                    else current_authority.projection_version
                ),
            )
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
) -> CoordinateSelectionMaterializationResult:
    audit_id = _gap_audit_id(
        spec_id=spec_id,
        session_start_ms=session_start_ms,
        gap_kind=gap_kind,
        proposed_outcome=proposed_outcome,
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
            unauthorized_from_close_time_ms=session_start_ms + 5 * INTERVAL_MS,
            detector_semantic_digest=_sor_detector_semantic_digest(),
            created_at_ms=now_ms,
            source_entry_vacuum_id=source_entry_vacuum_id,
            source_generation_id=source_generation_id,
        )
        await uow.instrument_selection.add_pending_authority_gap_audit(audit)
    else:
        audit = existing
    scopes = _pair_scopes(long_members=long_members, short_members=short_members)
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
) -> str:
    return (
        f"gap-audit:{spec_id}:{session_start_ms}:"
        f"{gap_kind.value}:{proposed_outcome.value}"
    )


async def _coordinate_generation_materialization(
    *,
    uow: KernelUnitOfWork,
    generation: MaterializationGeneration,
    vacuum: StrategyEntryVacuum,
    snapshot: SelectionSnapshot,
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
        proposed_outcome=AuthorityOutcome.FALLBACK_PREVIOUS,
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
    if now_ms - vacuum.fenced_at_ms >= materialization_timeout_ms:
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
        event_id="SOR-LONG",
    )
    long_request = UniverseInstallRequest(
        event_spec_id=SOR_LONG_EVENT_SPEC_ID,
        runtime_profile_id="tiny-live-v1",
        owner_policy_id=context.owner_policy_id,
        exchange_instrument_ids=selected_members,
        source_kind="dynamic_selection",
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
        event_id="SOR-SHORT",
    )
    short_request = UniverseInstallRequest(
        event_spec_id=SOR_SHORT_EVENT_SPEC_ID,
        runtime_profile_id="tiny-live-v1",
        owner_policy_id=short_context.owner_policy_id,
        exchange_instrument_ids=selected_members,
        source_kind="dynamic_selection",
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
    snapshot: SelectionSnapshot,
    selected_members: tuple[str, ...],
    previous_long_members: tuple[str, ...],
    previous_short_members: tuple[str, ...],
    now_ms: int,
    reason_code: str,
) -> CoordinateSelectionMaterializationResult:
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


def _build_continuity_authority(
    *,
    selection_spec_id: str,
    session_start_ms: int,
    pair: UniverseAuthorityPair,
    predecessor: SelectionSessionAuthority,
    owner_control_version: int,
    created_at_ms: int,
) -> SelectionSessionAuthority:
    sequence = 1
    first_eligible = session_start_ms + 5 * INTERVAL_MS
    return SelectionSessionAuthority(
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
        effective_from_ms=session_start_ms + 4 * INTERVAL_MS,
        first_eligible_close_time_ms=first_eligible,
        expires_at_ms=session_start_ms + 100 * INTERVAL_MS,
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
            "authority_outcome": AuthorityOutcome.NO_CHANGE,
            "grant_proof": AuthorityGrantProof(
                kind=AuthorityGrantProofKind.CONTINUOUS_ELIGIBLE_CLOSES,
                predecessor_authority_id=predecessor.selection_authority_id,
                authority_gap_audit_id=None,
            ),
            "reason_code": "SELECTED_MEMBERS_UNCHANGED",
            "effective_from_ms": created_at_ms,
            "first_eligible_close_time_ms": next_canonical_eligible_close(
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
        effective_from_ms=session_start_ms + 4 * INTERVAL_MS,
        first_eligible_close_time_ms=next_canonical_eligible_close(
            session_start_ms=session_start_ms,
            now_ms=created_at_ms,
        ),
        expires_at_ms=session_start_ms + 100 * INTERVAL_MS,
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
                audit.proposed_authority_outcome
                is AuthorityOutcome.FALLBACK_PREVIOUS
                and selection_mode is SelectionMode.STATIC_BASELINE
            )
            else current_authority.authority.selection_authority_id
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
        expires_at_ms=audit.session_start_ms + 100 * INTERVAL_MS,
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
) -> SelectionSessionAuthority:
    sequence = (
        1
        if current_authority is None
        or current_authority.authority.session_start_ms != snapshot.session_start_ms
        else current_authority.authority.authority_sequence + 1
    )
    return SelectionSessionAuthority(
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
        expires_at_ms=snapshot.session_start_ms + 100 * INTERVAL_MS,
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
        or generation.selection_snapshot_id is None
    ):
        return None
    snapshot = await uow.instrument_selection.get_snapshot_disposition(
        selection_spec_id=audit.selection_spec_id,
        session_start_ms=audit.session_start_ms,
        for_update=True,
    )
    if (
        snapshot is None
        or snapshot.snapshot.selection_snapshot_id
        != generation.selection_snapshot_id
    ):
        return None
    member_digest = selected_member_set_digest(snapshot.selected_members)
    long_context = await uow.strategy_universes.resolve_install_context(
        runtime_profile_id="tiny-live-v1",
        event_id="SOR-LONG",
    )
    short_context = await uow.strategy_universes.resolve_install_context(
        runtime_profile_id="tiny-live-v1",
        event_id="SOR-SHORT",
    )
    long = await install_strategy_universe(
        uow,
        UniverseInstallRequest(
            event_spec_id=SOR_LONG_EVENT_SPEC_ID,
            runtime_profile_id="tiny-live-v1",
            owner_policy_id=long_context.owner_policy_id,
            exchange_instrument_ids=snapshot.selected_members,
            source_kind="dynamic_selection",
            materialization_generation_id=generation_id,
            expected_member_set_digest=member_digest,
            installed_at_ms=now_ms,
        ),
    )
    short = await install_strategy_universe(
        uow,
        UniverseInstallRequest(
            event_spec_id=SOR_SHORT_EVENT_SPEC_ID,
            runtime_profile_id="tiny-live-v1",
            owner_policy_id=short_context.owner_policy_id,
            exchange_instrument_ids=snapshot.selected_members,
            source_kind="dynamic_selection",
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
        snapshot.selected_members,
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
        or generation.selection_snapshot_id is None
    ):
        return None
    snapshot = await uow.instrument_selection.get_snapshot_disposition(
        selection_spec_id=audit.selection_spec_id,
        session_start_ms=audit.session_start_ms,
        for_update=True,
    )
    if (
        snapshot is None
        or snapshot.snapshot.selection_snapshot_id
        != generation.selection_snapshot_id
    ):
        return None
    return (
        UniverseAuthorityPair(
            long_universe_version_id=(
                generation.previous_long_universe_version_id
            ),
            short_universe_version_id=(
                generation.previous_short_universe_version_id
            ),
        ),
        snapshot.selected_members,
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
            and control.pending_effective_session_start_ms == session_start_ms
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
) -> tuple[MaterializationGeneration, tuple[MaterializationTarget, ...]]:
    member_digest = selected_member_set_digest(selected_members)
    generation_id = f"generation:{snapshot.selection_spec_id}:{snapshot.session_start_ms}"
    payload = {
        "materialization_generation_id": generation_id,
        "selection_snapshot_id": snapshot.selection_snapshot_id,
        "previous_pair": previous_pair.model_dump(mode="json"),
        "selected_member_set_digest": member_digest,
    }
    semantic_digest = "sha256:" + sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    generation = MaterializationGeneration(
        materialization_generation_id=generation_id,
        selection_spec_id=snapshot.selection_spec_id,
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
            event_spec_id=SOR_LONG_EVENT_SPEC_ID,
            position_side="long",
            expected_member_set_digest=member_digest,
            materialization_order=1,
        ),
        MaterializationTarget(
            event_spec_id=SOR_SHORT_EVENT_SPEC_ID,
            position_side="short",
            expected_member_set_digest=member_digest,
            materialization_order=2,
        ),
    )


def _pair_scopes(
    *,
    long_members: tuple[str, ...],
    short_members: tuple[str, ...],
) -> tuple[AuthorityGapScope, ...]:
    return tuple(
        sorted(
            (
                *(
                    AuthorityGapScope(
                        event_spec_id=SOR_LONG_EVENT_SPEC_ID,
                        exchange_instrument_id=instrument_id,
                    )
                    for instrument_id in long_members
                ),
                *(
                    AuthorityGapScope(
                        event_spec_id=SOR_SHORT_EVENT_SPEC_ID,
                        exchange_instrument_id=instrument_id,
                    )
                    for instrument_id in short_members
                ),
            ),
            key=lambda item: (item.event_spec_id, item.exchange_instrument_id),
        )
    )


def _sor_detector_semantic_digest() -> str:
    return build_registry_semantic_hash(
        (
            strategy_contract_for(SOR_LONG_EVENT_SPEC_ID),
            strategy_contract_for(SOR_SHORT_EVENT_SPEC_ID),
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
) -> SelectionSessionAuthority:
    sequence = (
        1
        if current_authority is None
        or current_authority.authority.session_start_ms != session_start_ms
        else current_authority.authority.authority_sequence + 1
    )
    return SelectionSessionAuthority(
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
        expires_at_ms=session_start_ms + 100 * INTERVAL_MS,
        reason_code="OWNER_PAUSE_PRECEDES_MATERIALIZATION",
        created_at_ms=created_at_ms,
    )


def _blocked(reason_code: str) -> CoordinateSelectionMaterializationResult:
    return CoordinateSelectionMaterializationResult(
        disposition=MaterializationDisposition.BLOCKED,
        reason_code=reason_code,
    )
