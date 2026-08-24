"""Plan and coordinate one durable Dynamic Selection materialization step."""

from __future__ import annotations

import json
from collections.abc import Callable
from enum import StrEnum
from hashlib import sha256
from typing import Protocol

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

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
    GENERATION_PENDING = "GENERATION_PENDING"
    GENERATION_DESIRED = "GENERATION_DESIRED"
    GAP_AUDIT_PENDING = "GAP_AUDIT_PENDING"
    GAP_AUDIT_WINDOW_EXPIRED = "GAP_AUDIT_WINDOW_EXPIRED"
    BLOCKED = "BLOCKED"


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


async def complete_pending_authority_gap_audit(
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
            or initial_selection_control.selection_mode
            is not SelectionMode.DYNAMIC_SELECTION
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
    scopes = _pair_scopes(long_members=long_members, short_members=short_members)
    first_eligible_close = next_canonical_eligible_close(
        session_start_ms=audit.session_start_ms,
        now_ms=clock_ms(),
    )
    audited_through = first_eligible_close - INTERVAL_MS
    results = await audit_source.evaluate_authority_gap(
        AuthorityGapAuditEvaluationRequest(
            audit=audit,
            scopes=scopes,
            audited_through_close_time_ms=audited_through,
        )
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
        if (
            selection_control is None
            or selection_control.selection_mode is not SelectionMode.DYNAMIC_SELECTION
            or long_current is None
            or short_current is None
            or owner_control != initial_owner_control
            or selection_control != initial_selection_control
            or current_authority != initial_current_authority
            or long_current != initial_long_current
            or short_current != initial_short_current
            or vacuum != initial_vacuum
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
            pair=UniverseAuthorityPair(
                long_universe_version_id=long_current.universe_version_id,
                short_universe_version_id=short_current.universe_version_id,
            ),
            owner_control_version=owner_control.control_version,
            selection_snapshot_id=(
                None if snapshot is None else snapshot.snapshot.selection_snapshot_id
            ),
            created_at_ms=completed_at_ms,
        )
        await uow.instrument_selection.add_authority_and_set_current(
            authority,
            expected_current_version=(
                None
                if current_authority is None
                else current_authority.projection_version
            ),
        )
    return CoordinateSelectionMaterializationResult(
        disposition=(
            MaterializationDisposition.PRE_FENCE_CONTINUITY
            if audit.proposed_authority_outcome
            is AuthorityOutcome.PRE_FENCE_CONTINUITY
            else MaterializationDisposition.NO_CHANGE
        ),
        selection_authority_id=authority.selection_authority_id,
        authority_gap_audit_id=audit.authority_gap_audit_id,
        reason_code="AUTHORITY_GAP_AUDIT_COMPLETE",
    )


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
) -> CoordinateSelectionMaterializationResult:
    audit_id = (
        f"gap-audit:{spec_id}:{session_start_ms}:"
        f"{gap_kind.value}:{proposed_outcome.value}"
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
        selection_mode=SelectionMode.DYNAMIC_SELECTION,
        selection_snapshot_id=selection_snapshot_id,
        continued_from_selection_authority_id=(
            None
            if current_authority is None
            else current_authority.authority.selection_authority_id
        ),
        continuity_source_kind=ContinuitySourceKind.AUTHORITY_GAP_AUDIT,
        authority_gap_audit_id=audit.authority_gap_audit_id,
        materialization_generation_id=None,
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
        reason_code=f"{audit.gap_kind.value}_COMPLETE",
        created_at_ms=created_at_ms,
    )


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


def _blocked(reason_code: str) -> CoordinateSelectionMaterializationResult:
    return CoordinateSelectionMaterializationResult(
        disposition=MaterializationDisposition.BLOCKED,
        reason_code=reason_code,
    )
