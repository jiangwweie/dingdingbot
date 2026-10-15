"""Independent persistent ticks for Selection and Materialization planes."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from enum import StrEnum
from math import isfinite

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.application.coordinate_selection_materialization import (
    AuthorityGapAuditSource,
    CoordinateGenericGenerationRequest,
    CoordinateGenericPeriodRequest,
    CoordinateGenericSnapshotRequest,
    CoordinateGenericStaticRequest,
    CoordinateSelectionMaterializationRequest,
    MaterializationDisposition,
    complete_pending_authority_gap_audit,
    coordinate_selection_materialization_once,
)
from src.trading_kernel.application.drain_strategy_entry_vacuum import (
    DrainStrategyEntryVacuumRequest,
    VacuumDrainStatus,
    drain_strategy_entry_vacuum_once,
)
from src.trading_kernel.application.market_ports import (
    InstrumentSelectionMarketSource,
    PublicMarketSource,
)
from src.trading_kernel.application.observe_strategy_scope import (
    CurrentFactsRefreshCloseChanged,
    ObservationRequest,
    current_facts_refresh_vacuum_allowed,
    observe_strategy_scope,
)
from src.trading_kernel.application.ports import (
    RuntimeScopeSnapshot,
    SelectionLeaseHeld,
    UnitOfWorkFactory,
)
from src.trading_kernel.application.run_instrument_selection import (
    RunInstrumentSelectionRequest,
    run_instrument_selection_once,
)
from src.trading_kernel.domain.generic_materialization import (
    GenericMaterializationGeneration,
)
from src.trading_kernel.domain.generic_selection_spec import generic_selection_spec
from src.trading_kernel.domain.instrument_selection import DAY_MS, HOUR_MS
from src.trading_kernel.domain.orb_session_selection import (
    ORB_EVENT_SPEC_IDS,
    ORB_SELECTION_SPEC_ID,
    ORB_STRATEGY_GROUP_ID,
)
from src.trading_kernel.domain.selection_authority import (
    MaterializationGenerationClaimStatus,
    MaterializationGenerationState,
    SelectionMode,
)


class SelectionRuntimeStatus(StrEnum):
    NOT_DUE = "not_due"
    BLOCKED = "blocked"
    SNAPSHOT_READY = "snapshot_ready"
    ALREADY_READY = "already_ready"
    SOURCE_FAILED = "source_failed"
    COMPUTE_FAILED = "compute_failed"
    NOT_INSTALLED = "not_installed"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


class MaterializationRuntimeStatus(StrEnum):
    NOT_DUE = "not_due"
    ADVANCED = "advanced"
    UNCHANGED = "unchanged"
    WAITING = "waiting"
    BLOCKED = "blocked"


class SelectionRuntimeRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    selection_spec_id: str
    strategy_group_id: str
    worker_id: str
    now_ms: int
    max_concurrency: int = 6
    lease_duration_ms: int = 30_000

    @field_validator("selection_spec_id", "strategy_group_id", "worker_id", mode="before")
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Selection runtime identities must be non-blank")
        return normalized

    @model_validator(mode="after")
    def _validate_request(self) -> SelectionRuntimeRequest:
        if (
            self.now_ms <= 0
            or not 1 <= self.max_concurrency <= 24
            or self.lease_duration_ms <= 0
        ):
            raise ValueError("Selection runtime bounds are invalid")
        return self


class SelectionRuntimeResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: SelectionRuntimeStatus
    session_start_ms: int | None = None
    period_anchor_ms: int | None = None
    selection_job_id: str | None = None
    selection_snapshot_id: str | None = None
    reason_code: str | None = None


class MaterializationRuntimeResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: MaterializationRuntimeStatus
    session_start_ms: int | None = None
    period_anchor_ms: int | None = None
    disposition: MaterializationDisposition | None = None
    selection_authority_id: str | None = None
    materialization_generation_id: str | None = None
    entry_vacuum_id: str | None = None
    authority_gap_audit_id: str | None = None
    reason_code: str | None = None


class CurrentFactRefreshRuntimeRequest(SelectionRuntimeRequest):
    runtime_commit: str
    schema_revision: str
    timeout_seconds: float = 10.0
    after_runtime_scope_id: str | None = None

    @field_validator("timeout_seconds")
    @classmethod
    def _positive_timeout(cls,value: float) -> float:
        if not isfinite(value) or value<=0:
            raise ValueError("current facts timeout must be finite and positive")
        return value


class CurrentFactRefreshRuntimeResult(BaseModel):
    model_config=ConfigDict(frozen=True,extra="forbid")
    status: str
    reason_code: str | None = None
    runtime_scope_id: str | None = None


async def run_current_fact_refresh_runtime_once(*,uow_factory: UnitOfWorkFactory,market_source: PublicMarketSource,
    request: CurrentFactRefreshRuntimeRequest) -> CurrentFactRefreshRuntimeResult:
    if request.strategy_group_id==ORB_STRATEGY_GROUP_ID:
        return await _run_orb_staged_fact_refresh(uow_factory=uow_factory,market_source=market_source,request=request)
    family=generic_selection_spec(request.strategy_group_id)
    if family.selection_spec_id!=request.selection_spec_id:
        return CurrentFactRefreshRuntimeResult(status="blocked",reason_code="SELECTION_SPEC_DRIFT")
    async with uow_factory() as uow:
        owner=await uow.owner_controls.get_strategy_control(request.strategy_group_id)
        control=await uow.instrument_selection.get_selection_control(request.strategy_group_id)
        eligible_pending=control is not None and control.pending_selection_mode is SelectionMode.DYNAMIC_SELECTION and (
            control.pending_effective_period_anchor_ms is not None and request.now_ms>=control.pending_effective_period_anchor_ms+HOUR_MS)
        if owner is None or owner.entry_state!="enabled" or control is None or (control.selection_mode is not SelectionMode.DYNAMIC_SELECTION and not eligible_pending):
            return CurrentFactRefreshRuntimeResult(status="no_work")
        vacuum=await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=request.strategy_group_id,selection_spec_id=request.selection_spec_id)
        if vacuum is not None and vacuum.blocks_new_entry and not await current_facts_refresh_vacuum_allowed(uow,vacuum=vacuum,control=control):
            return CurrentFactRefreshRuntimeResult(status="no_work",reason_code="ENTRY_VACUUM")
        current=await uow.strategy_universes.get_current(family.event_spec_id)
        if current is None:
            return CurrentFactRefreshRuntimeResult(status="blocked",reason_code="CURRENT_UNIVERSE_MISSING")
        scopes=await uow.signals.list_current_fact_refresh_scopes(event_spec_id=family.event_spec_id,
            universe_version_id=current.universe_version_id,closed_at_ms=request.now_ms//HOUR_MS*HOUR_MS,
            checked_at_ms=request.now_ms,limit=16)
    if not scopes:
        return CurrentFactRefreshRuntimeResult(status="no_work")
    ordered=sorted(scopes,key=lambda item:item.runtime_scope_id)
    scope=next((item for item in ordered if request.after_runtime_scope_id is None or item.runtime_scope_id>request.after_runtime_scope_id),ordered[0])
    try:
        observed=await asyncio.wait_for(observe_strategy_scope(uow_factory,market_source,ObservationRequest(runtime_scope_id=scope.runtime_scope_id,
            runtime_commit=request.runtime_commit,schema_revision=request.schema_revision,
            trigger_candle_close_time_ms=request.now_ms//HOUR_MS*HOUR_MS,attempted_at_ms=request.now_ms,operation="refresh_current_facts")),timeout=request.timeout_seconds)
    except TimeoutError:
        return CurrentFactRefreshRuntimeResult(status="blocked",reason_code="CURRENT_FACT_SOURCE_TIMEOUT",runtime_scope_id=scope.runtime_scope_id)
    except CurrentFactsRefreshCloseChanged:
        return CurrentFactRefreshRuntimeResult(status="blocked",reason_code="CURRENT_FACT_CLOSE_CHANGED",runtime_scope_id=scope.runtime_scope_id)
    return CurrentFactRefreshRuntimeResult(status=observed.status.value,reason_code=observed.detector_reason,runtime_scope_id=scope.runtime_scope_id)


async def _run_orb_staged_fact_refresh(*,uow_factory: UnitOfWorkFactory,market_source: PublicMarketSource,
    request: CurrentFactRefreshRuntimeRequest) -> CurrentFactRefreshRuntimeResult:
    if request.selection_spec_id!=ORB_SELECTION_SPEC_ID:
        return CurrentFactRefreshRuntimeResult(status='blocked',reason_code='SELECTION_SPEC_DRIFT')
    close=request.now_ms//HOUR_MS*HOUR_MS
    async with uow_factory() as uow:
        owner=await uow.owner_controls.get_strategy_control(ORB_STRATEGY_GROUP_ID)
        control=await uow.instrument_selection.get_selection_control(ORB_STRATEGY_GROUP_ID)
        vacuum=await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=ORB_STRATEGY_GROUP_ID,selection_spec_id=ORB_SELECTION_SPEC_ID)
        if owner is None or owner.entry_state!='enabled' or control is None or close<request.now_ms//DAY_MS*DAY_MS+HOUR_MS:
            return CurrentFactRefreshRuntimeResult(status='no_work')
        scopes: list[RuntimeScopeSnapshot]=[]
        for event in ORB_EVENT_SPEC_IDS:
            current=await uow.strategy_universes.get_current(event)
            if current is not None:
                scopes.extend(await uow.signals.list_current_fact_refresh_scopes(event_spec_id=event,
                    universe_version_id=current.universe_version_id,closed_at_ms=close,checked_at_ms=request.now_ms,limit=7))
        if vacuum is not None and vacuum.source_generation_id is not None and vacuum.state=='RECONFIGURING' and vacuum.drained_at_ms is not None:
            targets=await uow.strategy_universes.get_generation_universe_targets(vacuum.source_generation_id)
            for target in targets:
                if target.event_spec_id not in ORB_EVENT_SPEC_IDS or target.lifecycle_state.value!='staged':
                    continue
                scopes.extend(await uow.signals.list_current_fact_refresh_scopes(event_spec_id=target.event_spec_id,
                    universe_version_id=target.universe_version_id,closed_at_ms=close,checked_at_ms=request.now_ms,limit=7,staged=True))
    if not scopes:
        return CurrentFactRefreshRuntimeResult(status='no_work')
    ordered=sorted(scopes,key=lambda item:item.runtime_scope_id)
    scope=next((s for s in ordered if request.after_runtime_scope_id is None or s.runtime_scope_id>request.after_runtime_scope_id),ordered[0])
    try:
        result=await asyncio.wait_for(observe_strategy_scope(uow_factory,market_source,ObservationRequest(runtime_scope_id=scope.runtime_scope_id,
            runtime_commit=request.runtime_commit,schema_revision=request.schema_revision,trigger_candle_close_time_ms=close,
            attempted_at_ms=request.now_ms,operation='refresh_staged_facts' if scope.lifecycle_state=='staged' else 'refresh_orb_facts')),timeout=request.timeout_seconds)
    except TimeoutError:
        return CurrentFactRefreshRuntimeResult(status='blocked',reason_code='CURRENT_FACT_SOURCE_TIMEOUT',runtime_scope_id=scope.runtime_scope_id)
    except CurrentFactsRefreshCloseChanged:
        return CurrentFactRefreshRuntimeResult(status='blocked',reason_code='CURRENT_FACT_CLOSE_CHANGED',runtime_scope_id=scope.runtime_scope_id)
    return CurrentFactRefreshRuntimeResult(status=result.status.value,reason_code=result.detector_reason,runtime_scope_id=scope.runtime_scope_id)


def current_sor_selection_session_start_ms(now_ms: int) -> int | None:
    """Return today's UTC SOR Session only after its 01:00 decision boundary."""

    if now_ms <= 0:
        raise ValueError("Selection runtime time must be positive")
    session_start_ms = (now_ms // DAY_MS) * DAY_MS
    if now_ms < session_start_ms + HOUR_MS:
        return None
    return session_start_ms


async def run_selection_runtime_once(
    *,
    uow_factory: UnitOfWorkFactory,
    market_source: InstrumentSelectionMarketSource,
    request: SelectionRuntimeRequest,
    clock_ms: Callable[[], int],
) -> SelectionRuntimeResult:
    if request.strategy_group_id in {"CPM-RO-001","MPG-001","MI-001","BRF2-001"}:
        return await _run_generic_selection_runtime_once(uow_factory=uow_factory,market_source=market_source,
            request=request,clock_ms=clock_ms)
    session_start_ms = current_sor_selection_session_start_ms(request.now_ms)
    if session_start_ms is None:
        return SelectionRuntimeResult(status=SelectionRuntimeStatus.NOT_DUE)
    async with uow_factory() as uow:
        control = await uow.instrument_selection.get_selection_control(
            request.strategy_group_id
        )
    if request.strategy_group_id == ORB_STRATEGY_GROUP_ID and control is None:
        return SelectionRuntimeResult(status=SelectionRuntimeStatus.NOT_INSTALLED,reason_code='ORB_CONTROL_NOT_INSTALLED')
    if control is None or control.selection_spec_id != request.selection_spec_id:
        return SelectionRuntimeResult(
            status=SelectionRuntimeStatus.BLOCKED,
            session_start_ms=session_start_ms,
            reason_code="SELECTION_CONTROL_MISSING_OR_DRIFTED",
        )
    hourly = request.strategy_group_id == ORB_STRATEGY_GROUP_ID
    if hourly and request.selection_spec_id != ORB_SELECTION_SPEC_ID:
        return SelectionRuntimeResult(status=SelectionRuntimeStatus.BLOCKED,reason_code="ORB_SELECTION_IDENTITY_OR_EPOCH_MISSING")
    if control.selection_mode is SelectionMode.DISABLED:
        return SelectionRuntimeResult(
            status=SelectionRuntimeStatus.NOT_DUE,
            session_start_ms=session_start_ms,
            reason_code="SELECTION_MODE_DISABLED",
        )
    if control.selection_mode is SelectionMode.STATIC_BASELINE:
        if control.pending_selection_mode is None:
            return SelectionRuntimeResult(
                status=SelectionRuntimeStatus.NOT_DUE,
                session_start_ms=session_start_ms,
                reason_code="STATIC_BASELINE_NO_PENDING_DYNAMIC",
            )
        if (
            control.pending_selection_mode is not SelectionMode.DYNAMIC_SELECTION
            or control.pending_effective_period_anchor_ms is None
            or (control.pending_effective_period_anchor_ms > session_start_ms if hourly
                else control.pending_effective_period_anchor_ms != session_start_ms)
        ):
            return SelectionRuntimeResult(
                status=SelectionRuntimeStatus.BLOCKED,
                session_start_ms=session_start_ms,
                reason_code="PENDING_SELECTION_SESSION_MISMATCH",
            )
    async with uow_factory() as uow:
        owner=await uow.owner_controls.get_strategy_control(request.strategy_group_id)
        if owner is None or owner.entry_state!="enabled":
            return SelectionRuntimeResult(status=SelectionRuntimeStatus.NOT_DUE,
                session_start_ms=session_start_ms,reason_code="OWNER_PAUSED")
    if hourly and control.selection_epoch_id is None:
        return SelectionRuntimeResult(status=SelectionRuntimeStatus.BLOCKED,reason_code='ORB_SELECTION_EPOCH_MISSING')
    result = await run_instrument_selection_once(
        uow_factory=uow_factory,
        market_source=market_source,
        request=RunInstrumentSelectionRequest(
            selection_spec_id=request.selection_spec_id,
            selection_epoch_id=(control.selection_epoch_id or "") if hourly else "sor-v0",
            period_anchor_ms=session_start_ms,
            worker_id=request.worker_id,
            max_concurrency=request.max_concurrency,
            lease_duration_ms=max(request.lease_duration_ms,120_000) if hourly else request.lease_duration_ms,
        ),
        clock_ms=clock_ms,
    )
    return SelectionRuntimeResult(
        status=SelectionRuntimeStatus(result.outcome.lower()),
        session_start_ms=session_start_ms,
        selection_job_id=result.selection_job_id,
        selection_snapshot_id=result.selection_snapshot_id,
        reason_code=result.reason_code,
    )


async def _run_generic_selection_runtime_once(
    *, uow_factory: UnitOfWorkFactory, market_source: InstrumentSelectionMarketSource,
    request: SelectionRuntimeRequest, clock_ms: Callable[[], int],
) -> SelectionRuntimeResult:
    family=generic_selection_spec(request.strategy_group_id)
    if request.selection_spec_id!=family.selection_spec_id:
        return SelectionRuntimeResult(status=SelectionRuntimeStatus.BLOCKED,reason_code="SELECTION_SPEC_DRIFT")
    cadence_ms=family.cadence_hours*HOUR_MS
    cutoff=request.now_ms//cadence_ms*cadence_ms
    async with uow_factory() as uow:
        control=await uow.instrument_selection.get_selection_control(request.strategy_group_id)
        if control is None:
            return SelectionRuntimeResult(status=SelectionRuntimeStatus.NOT_INSTALLED,reason_code="GENERIC_CONTROL_NOT_INSTALLED")
        if control.selection_spec_id!=request.selection_spec_id:
            return SelectionRuntimeResult(status=SelectionRuntimeStatus.BLOCKED,reason_code="SELECTION_CONTROL_SPEC_DRIFT")
        if control.selection_mode is SelectionMode.DISABLED or (
            control.selection_mode is SelectionMode.STATIC_BASELINE and control.pending_selection_mode is None):
            return SelectionRuntimeResult(status=SelectionRuntimeStatus.NOT_DUE,reason_code="STATIC_BASELINE_NO_PENDING_DYNAMIC")
        if control.selection_epoch_id is None or not control.permits_dynamic_period(cutoff):
            return SelectionRuntimeResult(status=SelectionRuntimeStatus.NOT_DUE,reason_code="GENERIC_PENDING_PERIOD_NOT_DUE")
        owner=await uow.owner_controls.get_strategy_control(request.strategy_group_id)
        if owner is None or owner.entry_state!="enabled":
            return SelectionRuntimeResult(status=SelectionRuntimeStatus.NOT_DUE,reason_code="OWNER_PAUSED")
        try:
            installed=await uow.instrument_selection.get_generic_spec(request.selection_spec_id)
        except LookupError:
            return SelectionRuntimeResult(status=SelectionRuntimeStatus.NOT_INSTALLED,reason_code="GENERIC_SPEC_NOT_INSTALLED")
        if installed!=family:
            return SelectionRuntimeResult(status=SelectionRuntimeStatus.BLOCKED,reason_code="GENERIC_INSTALLED_SPEC_DRIFT")
    try:
        result=await run_instrument_selection_once(uow_factory=uow_factory,market_source=market_source,
            request=RunInstrumentSelectionRequest(selection_spec_id=request.selection_spec_id,period_anchor_ms=cutoff,
                selection_epoch_id=control.selection_epoch_id,worker_id=request.worker_id,max_concurrency=request.max_concurrency,
                lease_duration_ms=request.lease_duration_ms),clock_ms=clock_ms)
    except SelectionLeaseHeld:
        return SelectionRuntimeResult(status=SelectionRuntimeStatus.NOT_DUE,period_anchor_ms=cutoff,reason_code="SELECTION_JOB_LEASE_HELD")
    return SelectionRuntimeResult(status=SelectionRuntimeStatus(result.outcome.lower()),period_anchor_ms=cutoff,
        selection_job_id=result.selection_job_id,selection_snapshot_id=result.selection_snapshot_id,reason_code=result.reason_code)


async def run_materialization_runtime_once(
    *,
    uow_factory: UnitOfWorkFactory,
    audit_source: AuthorityGapAuditSource,
    request: SelectionRuntimeRequest,
    clock_ms: Callable[[], int],
) -> MaterializationRuntimeResult:
    if request.strategy_group_id in {"CPM-RO-001","MPG-001","MI-001","BRF2-001"}:
        return await _run_generic_materialization_runtime_once(uow_factory=uow_factory,request=request,clock_ms=clock_ms)
    session_start_ms = current_sor_selection_session_start_ms(request.now_ms)
    if session_start_ms is None:
        return MaterializationRuntimeResult(
            status=MaterializationRuntimeStatus.NOT_DUE
        )
    async with uow_factory() as uow:
        if request.strategy_group_id == ORB_STRATEGY_GROUP_ID:
            control=await uow.instrument_selection.get_selection_control(ORB_STRATEGY_GROUP_ID)
            if control is None or (control.selection_mode is SelectionMode.STATIC_BASELINE and control.pending_selection_mode is None):
                return MaterializationRuntimeResult(status=MaterializationRuntimeStatus.NOT_DUE,
                    reason_code='ORB_STATIC_BASELINE_OR_NOT_INSTALLED')
        drain = await drain_strategy_entry_vacuum_once(
            uow,
            DrainStrategyEntryVacuumRequest(
                strategy_group_id=request.strategy_group_id,
                selection_spec_id=request.selection_spec_id,
                now_ms=request.now_ms,
            ),
        )
    if not (
        drain.status is VacuumDrainStatus.NO_VACUUM
        or (
            drain.status is VacuumDrainStatus.WAITING_LIFECYCLE
            and str(drain.reason_code or "").startswith("VACUUM_STATE:")
        )
    ):
        return _runtime_result_from_vacuum_drain(
            session_start_ms=session_start_ms,
            drain_status=drain.status,
            entry_vacuum_id=drain.entry_vacuum_id,
            selection_authority_id=drain.selection_authority_id,
            reason_code=drain.reason_code,
        )
    async with uow_factory() as uow:
        try:
            await uow.instrument_selection.get_active_spec(request.selection_spec_id)
        except LookupError:
            return MaterializationRuntimeResult(status=MaterializationRuntimeStatus.NOT_DUE,
                session_start_ms=session_start_ms,reason_code="SELECTION_SPEC_NOT_INSTALLED")
        generation_claim = (
            await uow.instrument_selection.claim_materialization_generation(
                selection_spec_id=request.selection_spec_id,
                session_start_ms=session_start_ms,
                worker_id=request.worker_id,
                now_ms=request.now_ms,
                lease_duration_ms=request.lease_duration_ms,
            )
        )
    if (
        generation_claim.status
        is MaterializationGenerationClaimStatus.LEASE_HELD
    ):
        return MaterializationRuntimeResult(
            status=MaterializationRuntimeStatus.WAITING,
            session_start_ms=session_start_ms,
            materialization_generation_id=(
                None
                if generation_claim.generation is None
                else generation_claim.generation.materialization_generation_id
            ),
            reason_code="MATERIALIZATION_LEASE_HELD",
        )
    claimed_generation_id = (
        generation_claim.generation.materialization_generation_id
        if generation_claim.status
        is MaterializationGenerationClaimStatus.CLAIMED
        and generation_claim.generation is not None
        else None
    )
    try:
        result = await coordinate_selection_materialization_once(
            uow_factory=uow_factory,
            request=CoordinateSelectionMaterializationRequest(
                selection_spec_id=request.selection_spec_id,
                strategy_group_id=request.strategy_group_id,
                session_start_ms=session_start_ms,
                worker_id=request.worker_id,
            ),
            clock_ms=clock_ms,
        )
    finally:
        if claimed_generation_id is not None:
            async with uow_factory() as uow:
                await uow.instrument_selection.release_materialization_generation_lease(
                    materialization_generation_id=claimed_generation_id,
                    worker_id=request.worker_id,
                )
    if (
        result.disposition is MaterializationDisposition.GAP_AUDIT_PENDING
        and result.authority_gap_audit_id is not None
    ):
        result = await complete_pending_authority_gap_audit(
            uow_factory=uow_factory,
            audit_source=audit_source,
            authority_gap_audit_id=result.authority_gap_audit_id,
            clock_ms=clock_ms,
        )
    if result.reason_code in {"TERMINAL_AUTHORITY_ALREADY_COMMITTED", "OWNER_PAUSED_NO_CHANGE"}:
        status = MaterializationRuntimeStatus.UNCHANGED
    elif result.disposition is MaterializationDisposition.BLOCKED:
        status = MaterializationRuntimeStatus.BLOCKED
    elif result.disposition in {
        MaterializationDisposition.NOT_DUE,
        MaterializationDisposition.WAITING_SELECTION,
        MaterializationDisposition.WAITING_VACUUM,
        MaterializationDisposition.KEEP_STATIC_PENDING_DYNAMIC,
        MaterializationDisposition.LONG_WARMING,
        MaterializationDisposition.SHORT_WARMING,
        MaterializationDisposition.GAP_AUDIT_PENDING,
    }:
        status = MaterializationRuntimeStatus.WAITING
    else:
        status = MaterializationRuntimeStatus.ADVANCED
    return MaterializationRuntimeResult(
        status=status,
        session_start_ms=session_start_ms,
        disposition=result.disposition,
        selection_authority_id=result.selection_authority_id,
        materialization_generation_id=result.materialization_generation_id,
        entry_vacuum_id=result.entry_vacuum_id,
        authority_gap_audit_id=result.authority_gap_audit_id,
        reason_code=result.reason_code,
    )


async def _run_generic_materialization_runtime_once(
    *, uow_factory: UnitOfWorkFactory, request: SelectionRuntimeRequest,
    clock_ms: Callable[[],int],
) -> MaterializationRuntimeResult:
    family=generic_selection_spec(request.strategy_group_id)
    if request.selection_spec_id!=family.selection_spec_id:
        return MaterializationRuntimeResult(status=MaterializationRuntimeStatus.BLOCKED,reason_code="SELECTION_SPEC_DRIFT")
    cadence_ms=family.cadence_hours*HOUR_MS
    cutoff=(request.now_ms-HOUR_MS)//cadence_ms*cadence_ms
    async with uow_factory() as uow:
        control=await uow.instrument_selection.get_selection_control(request.strategy_group_id)
        if control is None or control.selection_mode is SelectionMode.DISABLED:
            return MaterializationRuntimeResult(status=MaterializationRuntimeStatus.NOT_DUE,reason_code="GENERIC_CONTROL_NOT_INSTALLED_OR_DISABLED")
        if control.selection_spec_id!=request.selection_spec_id:
            return MaterializationRuntimeResult(status=MaterializationRuntimeStatus.BLOCKED,reason_code="SELECTION_CONTROL_SPEC_DRIFT")
        if control.selection_mode is SelectionMode.STATIC_BASELINE and control.pending_selection_mode is None:
            return MaterializationRuntimeResult(status=MaterializationRuntimeStatus.NOT_DUE,reason_code="STATIC_BASELINE_NO_PENDING_DYNAMIC")
        try:
            installed=await uow.instrument_selection.get_generic_spec(request.selection_spec_id)
        except LookupError:
            return MaterializationRuntimeResult(status=MaterializationRuntimeStatus.NOT_DUE,reason_code="GENERIC_SPEC_NOT_INSTALLED")
        if installed!=family:
            return MaterializationRuntimeResult(status=MaterializationRuntimeStatus.BLOCKED,reason_code="GENERIC_INSTALLED_SPEC_DRIFT")
        generation=await uow.instrument_selection.get_latest_unfinished_generic_generation(
            strategy_group_id=request.strategy_group_id,selection_spec_id=request.selection_spec_id)
        vacuum=await uow.instrument_selection.get_current_entry_vacuum(
            strategy_group_id=request.strategy_group_id,selection_spec_id=request.selection_spec_id)
        job=None
        first_pending_due=control.selection_mode is SelectionMode.STATIC_BASELINE and (
            control.pending_selection_mode is SelectionMode.DYNAMIC_SELECTION and control.pending_effective_period_anchor_ms is not None and control.pending_effective_period_anchor_ms<=cutoff)
        if cutoff>0 and control.selection_epoch_id is not None and control.permits_dynamic_period(cutoff) and (
            control.selection_mode is SelectionMode.DYNAMIC_SELECTION or first_pending_due):
            job=await uow.instrument_selection.get_selection_job(selection_spec_id=request.selection_spec_id,
                selection_epoch_id=control.selection_epoch_id,period_anchor_ms=cutoff)
    # An exact ACTIVE generation has already crossed this Snapshot's boundary.
    # Its coordinator still rechecks Owner, Control, current Authority, clock and
    # Universe. Avoid the redundant continuity and Snapshot dispatch transactions.
    active_generation_id = None
    if (job is not None and job.state == "SNAPSHOT_READY" and job.selection_snapshot_id is not None
        and vacuum is None and generation is None and control.pending_selection_mode is None):
        candidate_id = GenericMaterializationGeneration.id_for_snapshot(job.selection_snapshot_id)
        async with uow_factory() as uow:
            candidate = await uow.instrument_selection.get_generic_materialization_generation(candidate_id)
        if candidate is not None and candidate.lifecycle_state is MaterializationGenerationState.ACTIVE:
            active_generation_id = candidate_id
    step: CoordinateGenericStaticRequest | CoordinateGenericSnapshotRequest | CoordinateGenericGenerationRequest | CoordinateGenericPeriodRequest
    if control.pending_selection_mode is SelectionMode.STATIC_BASELINE:
        step=CoordinateGenericStaticRequest(strategy_group_id=request.strategy_group_id,worker_id=request.worker_id)
    elif active_generation_id is not None:
        step=CoordinateGenericGenerationRequest(materialization_generation_id=active_generation_id,worker_id=request.worker_id)
    elif job is not None and job.state=="SNAPSHOT_READY" and job.selection_snapshot_id is not None:
        # Continuity is independent of the Selector and precedes disposition.
        if control.selection_mode is SelectionMode.DYNAMIC_SELECTION:
            continuity=await coordinate_selection_materialization_once(uow_factory=uow_factory,
                request=CoordinateGenericPeriodRequest(strategy_group_id=request.strategy_group_id,
                    selection_spec_id=request.selection_spec_id,period_anchor_ms=cutoff,worker_id=request.worker_id),clock_ms=clock_ms)
            if continuity.reason_code in {"WARM_READINESS_STALE","WARM_READINESS_MISSING","CERTIFICATION_STALE",
                "COMPARATIVE_PROJECTION_INCOMPLETE","CERTIFICATION_TEMPORARILY_UNAVAILABLE"}:
                async with uow_factory() as uow:
                    latest=await uow.instrument_selection.get_generic_snapshot(job.selection_snapshot_id)
                if latest.selected_members:
                    return MaterializationRuntimeResult(status=(MaterializationRuntimeStatus.BLOCKED
                        if continuity.reason_code.startswith("CERTIFICATION") else MaterializationRuntimeStatus.WAITING),
                        period_anchor_ms=cutoff,disposition=continuity.disposition,reason_code=continuity.reason_code)
        step=CoordinateGenericSnapshotRequest(selection_snapshot_id=job.selection_snapshot_id,worker_id=request.worker_id)
    elif generation is not None:
        step=CoordinateGenericGenerationRequest(materialization_generation_id=generation.materialization_generation_id,worker_id=request.worker_id)
    elif vacuum is not None and vacuum.source_generation_id is not None:
        step=CoordinateGenericGenerationRequest(materialization_generation_id=vacuum.source_generation_id,worker_id=request.worker_id)
    elif control.selection_mode is SelectionMode.DYNAMIC_SELECTION and cutoff>0:
        step=CoordinateGenericPeriodRequest(strategy_group_id=request.strategy_group_id,
            selection_spec_id=request.selection_spec_id,period_anchor_ms=cutoff,worker_id=request.worker_id)
    else:
        return MaterializationRuntimeResult(status=MaterializationRuntimeStatus.NOT_DUE,reason_code="GENERIC_PENDING_PERIOD_NOT_DUE")
    result=await coordinate_selection_materialization_once(uow_factory=uow_factory,request=step,clock_ms=clock_ms)
    if result.reason_code in {"TERMINAL_AUTHORITY_ALREADY_COMMITTED", "OWNER_PAUSED_NO_CHANGE"}:
        status = MaterializationRuntimeStatus.UNCHANGED
    elif result.disposition is MaterializationDisposition.BLOCKED:
        status=MaterializationRuntimeStatus.BLOCKED
    # Only the unfenced Desired path is ordinary waiting. Snapshot proof and
    # STAGED activation return BLOCKED for this same reason and must stay noisy.
    elif (
        result.disposition is MaterializationDisposition.GENERATION_DESIRED
        and result.reason_code == "GENERIC_CURRENT_CLOSE_ALREADY_CONSUMED"
    ) or result.disposition in {
        MaterializationDisposition.NOT_DUE,
        MaterializationDisposition.WAITING_SELECTION,
        MaterializationDisposition.WAITING_VACUUM,
        MaterializationDisposition.GENERATION_LEASE_HELD,
        MaterializationDisposition.TARGET_WARMING,
        MaterializationDisposition.KEEP_STATIC_PENDING_DYNAMIC,
    }:
        status = MaterializationRuntimeStatus.WAITING
    else:
        status=MaterializationRuntimeStatus.ADVANCED
    return MaterializationRuntimeResult(status=status,period_anchor_ms=cutoff,disposition=result.disposition,
        selection_authority_id=result.selection_authority_id,materialization_generation_id=result.materialization_generation_id,
        entry_vacuum_id=result.entry_vacuum_id,reason_code=result.reason_code)


def _runtime_result_from_vacuum_drain(
    *,
    session_start_ms: int,
    drain_status: VacuumDrainStatus,
    entry_vacuum_id: str | None,
    selection_authority_id: str | None,
    reason_code: str | None,
) -> MaterializationRuntimeResult:
    if drain_status is VacuumDrainStatus.BLOCKED:
        status = MaterializationRuntimeStatus.BLOCKED
    elif drain_status in {
        VacuumDrainStatus.POSITION_FACTS_REQUIRED,
        VacuumDrainStatus.WAITING_COMMAND,
        VacuumDrainStatus.WAITING_UNKNOWN_OUTCOME,
        VacuumDrainStatus.WAITING_LIFECYCLE,
    }:
        status = MaterializationRuntimeStatus.WAITING
    else:
        status = MaterializationRuntimeStatus.ADVANCED
    if drain_status is VacuumDrainStatus.VALID_EMPTY_COMMITTED:
        disposition = MaterializationDisposition.VALID_EMPTY
    elif drain_status is VacuumDrainStatus.OWNER_PAUSED:
        disposition = MaterializationDisposition.OWNER_PAUSED
    else:
        disposition = MaterializationDisposition.WAITING_VACUUM
    return MaterializationRuntimeResult(
        status=status,
        session_start_ms=session_start_ms,
        disposition=disposition,
        selection_authority_id=selection_authority_id,
        entry_vacuum_id=entry_vacuum_id,
        reason_code=reason_code or drain_status.value,
    )
