"""Exact-key readonly views for Owner and operations surfaces."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.application.ports import (
    ExitProfileAuthorityRepository,
    KernelUnitOfWork,
    MonitorStateRecord,
    SelectionJobRecord,
)
from src.trading_kernel.application.project_owner_state import (
    owner_ticket_monitor_key,
)
from src.trading_kernel.application.runtime import RuntimeReleaseCompatibilityFact
from src.trading_kernel.domain.exit_policy import (
    CurrentEventExitBinding,
    EventExitBinding,
    EventExitBindingEvent,
    ExitProfileRecord,
    build_exit_profile_catalog_digest,
)
from src.trading_kernel.domain.generic_selection_spec import generic_selection_spec
from src.trading_kernel.domain.instrument_selection import DAY_MS
from src.trading_kernel.domain.selection_authority import (
    AuthorityGapAudit,
    CurrentSelectionAuthority,
    GenericRecoveryAuthority,
    MaterializationGeneration,
    SelectionControl,
    SelectionMode,
    SelectionSnapshotDisposition,
)
from src.trading_kernel.domain.strategy_entry_vacuum import StrategyEntryVacuum

_PERIOD_FACT_LIMIT = 8
_EXIT_PROFILE_LIMIT = 32


class GenericSelectionRuntimeReadonlyRequest(BaseModel):
    model_config=ConfigDict(frozen=True,extra="forbid")
    strategy_group_id: str
    now_ms: int

    @model_validator(mode="after")
    def _validate(self) -> GenericSelectionRuntimeReadonlyRequest:
        generic_selection_spec(self.strategy_group_id)
        if self.now_ms<=0:
            raise ValueError("readonly time must be positive")
        return self


class GenericSelectionRuntimeReadonlyView(BaseModel):
    model_config=ConfigDict(frozen=True,extra="forbid")
    strategy_group_id: str
    selection_spec_id: str
    installed: bool
    selection_mode: SelectionMode | None
    latest_successful_snapshot_id: str | None
    latest_successful_cutoff_at_ms: int | None
    latest_successful_committed_at_ms: int | None
    latest_successful_completion_age_ms: int | None
    latest_successful_selection_age_ms: int | None
    latest_successful_cutoff_age_ms: int | None
    membership_source_snapshot_id: str | None
    membership_source_cutoff_at_ms: int | None
    membership_source_age_ms: int | None
    current_authority_id: str | None
    current_authority_outcome: str | None
    first_blocker: str | None
    observed_at_ms: int


async def get_generic_selection_runtime_view(uow: KernelUnitOfWork,
    request: GenericSelectionRuntimeReadonlyRequest) -> GenericSelectionRuntimeReadonlyView:
    """Display current facts with independent source ages; never grants Entry."""
    family=generic_selection_spec(request.strategy_group_id)
    repo=uow.instrument_selection
    installed=True
    try:
        actual=await repo.get_generic_spec(family.selection_spec_id)
        if actual!=family:
            raise ValueError("Readonly installed Spec differs")
    except LookupError:
        installed=False
    control=await repo.get_selection_control(request.strategy_group_id)
    latest=None
    if installed and control is not None and control.selection_epoch_id is not None:
        latest=await repo.get_latest_generic_snapshot(family.selection_spec_id,selection_epoch_id=control.selection_epoch_id)
    current=await repo.get_current_generic_authority(family.selection_spec_id) if installed else None
    authority=None if current is None else current.authority
    freshness=None if authority is None else (authority.recovery_proof.membership_freshness
        if isinstance(authority,GenericRecoveryAuthority) else authority.membership_freshness)
    vacuum=await repo.get_current_entry_vacuum(strategy_group_id=request.strategy_group_id,selection_spec_id=family.selection_spec_id) if installed else None
    owner=await uow.owner_controls.get_strategy_control(request.strategy_group_id)
    blocker=None
    if not installed:
        blocker="SPEC_NOT_INSTALLED"
    elif control is None or control.selection_spec_id!=family.selection_spec_id:
        blocker="SELECTION_CONTROL_MISSING_OR_DRIFTED"
    elif owner is None or owner.entry_state!="enabled":
        blocker="OWNER_PAUSED"
    elif vacuum is not None and vacuum.blocks_new_entry:
        blocker=vacuum.first_blocker or "ENTRY_VACUUM"
    elif authority is not None and authority.authority_outcome=="VALID_EMPTY":
        blocker="VALID_EMPTY"
    elif freshness is not None and not freshness.allows_new_entry_at(request.now_ms):
        blocker="SELECTION_STALE_PAUSED"
    elif authority is not None and request.now_ms>=authority.expires_at_ms:
        blocker="AUTHORITY_EXPIRED"
    elif authority is not None and request.now_ms<authority.effective_from_ms:
        blocker="AUTHORITY_NOT_EFFECTIVE"
    elif authority is not None and control.selection_mode is SelectionMode.DYNAMIC_SELECTION and (
        authority.selection_epoch_id!=control.selection_epoch_id or authority.selection_control_version!=control.control_version
        or authority.owner_control_version!=owner.control_version):
        blocker="AUTHORITY_CONTROL_CHANGED"
    elif authority is None and control is not None and control.selection_mode is SelectionMode.DYNAMIC_SELECTION:
        blocker="AUTHORITY_MISSING"
    return GenericSelectionRuntimeReadonlyView(strategy_group_id=request.strategy_group_id,
        selection_spec_id=family.selection_spec_id,installed=installed,
        selection_mode=None if control is None else control.selection_mode,
        latest_successful_snapshot_id=None if latest is None else latest.selection_snapshot_id,
        latest_successful_cutoff_at_ms=None if latest is None else latest.feature_cutoff_at_ms,
        latest_successful_committed_at_ms=None if latest is None else latest.committed_at_ms,
        latest_successful_completion_age_ms=None if latest is None else max(0,request.now_ms-latest.committed_at_ms),
        latest_successful_selection_age_ms=None if latest is None else max(0,request.now_ms-latest.committed_at_ms),
        latest_successful_cutoff_age_ms=None if latest is None else max(0,request.now_ms-latest.feature_cutoff_at_ms),
        membership_source_snapshot_id=None if freshness is None else freshness.source_snapshot_id,
        membership_source_cutoff_at_ms=None if freshness is None else freshness.source_snapshot_cutoff_at_ms,
        membership_source_age_ms=None if freshness is None else max(0,request.now_ms-freshness.source_snapshot_cutoff_at_ms),
        current_authority_id=None if authority is None else authority.selection_authority_id,
        current_authority_outcome=None if authority is None else authority.authority_outcome,
        first_blocker=blocker,observed_at_ms=request.now_ms)


class ExitProfileAuthorityReadonlyRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_spec_id: str | None = None
    event_limit: int = 20

    @field_validator("event_spec_id", mode="before")
    @classmethod
    def _normalize_event_spec_id(cls, value: object) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @field_validator("event_limit")
    @classmethod
    def _require_event_limit(cls, value: int) -> int:
        if not 1 <= value <= 50:
            raise ValueError("Binding event limit must be in [1, 50]")
        return value


class ExitProfileAuthorityReadonlyView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_spec_id: str | None
    catalog_digest: str
    profiles: tuple[ExitProfileRecord, ...]
    current_bindings: tuple[CurrentEventExitBinding, ...]
    binding_facts: tuple[EventExitBinding, ...]
    recent_events: tuple[EventExitBindingEvent, ...]

    @model_validator(mode="after")
    def _validate_authority_view(self) -> ExitProfileAuthorityReadonlyView:
        if self.catalog_digest != build_exit_profile_catalog_digest():
            raise ValueError("ExitProfile Catalog digest differs")
        if len({item.profile.exit_profile_id for item in self.profiles}) != len(
            self.profiles
        ):
            raise ValueError("ExitProfile readonly view contains duplicate Profiles")
        facts = {item.exit_binding_id: item for item in self.binding_facts}
        for current in self.current_bindings:
            binding = facts.get(current.exit_binding_id)
            if (
                binding is None
                or binding.event_spec_id != current.event_spec_id
                or binding.binding_semantic_hash != current.binding_semantic_hash
            ):
                raise ValueError("current Binding differs from immutable fact")
        if self.event_spec_id is not None and (
            any(
                item.event_spec_id != self.event_spec_id
                for item in self.current_bindings
            ) or any(
                item.event_spec_id != self.event_spec_id
                for item in self.binding_facts
            ) or any(
                item.event_spec_id != self.event_spec_id
                for item in self.recent_events
            )
        ):
            raise ValueError(
                "ExitProfile readonly facts differ from requested Event"
            )
        return self


class SelectionRuntimeReadonlyRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_group_id: str
    selection_spec_id: str
    session_start_ms: int
    release_compatibility_id: str | None = None

    @field_validator(
        "strategy_group_id",
        "selection_spec_id",
        "release_compatibility_id",
        mode="before",
    )
    @classmethod
    def _normalize_identity(cls, value: object) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized:
            raise ValueError("Selection readonly identities must be non-blank")
        return normalized

    @field_validator("session_start_ms")
    @classmethod
    def _require_session_boundary(cls, value: int) -> int:
        if value <= 0 or value % DAY_MS != 0:
            raise ValueError("Selection readonly Session must be exact 00:00 UTC")
        return value


class SelectionRuntimeReadonlyView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_group_id: str
    selection_spec_id: str
    session_start_ms: int
    selection_control: SelectionControl | None
    selection_job: SelectionJobRecord | None
    snapshot_disposition: SelectionSnapshotDisposition | None
    materialization_generation: MaterializationGeneration | None
    entry_vacuums: tuple[StrategyEntryVacuum, ...]
    authority_gap_audits: tuple[AuthorityGapAudit, ...]
    current_authority: CurrentSelectionAuthority | None
    first_eligible_close_time_ms: int | None
    release_compatibility_fact: RuntimeReleaseCompatibilityFact | None

    @model_validator(mode="after")
    def _validate_exact_scope(self) -> SelectionRuntimeReadonlyView:
        if self.selection_control is not None and (
            self.selection_control.strategy_group_id != self.strategy_group_id
            or self.selection_control.selection_spec_id != self.selection_spec_id
        ):
            raise ValueError("Selection Control differs from readonly scope")
        if self.selection_job is not None and (
            self.selection_job.selection_spec_id != self.selection_spec_id
            or self.selection_job.period_anchor_ms != self.session_start_ms
        ):
            raise ValueError("Selection Job differs from readonly period")
        if self.snapshot_disposition is not None:
            snapshot = self.snapshot_disposition.snapshot
            if (
                snapshot.strategy_group_id != self.strategy_group_id
                or snapshot.selection_spec_id != self.selection_spec_id
                or snapshot.session_start_ms != self.session_start_ms
            ):
                raise ValueError("Selection Snapshot differs from readonly period")
        if self.materialization_generation is not None and (
            self.materialization_generation.strategy_group_id
            != self.strategy_group_id
            or self.materialization_generation.selection_spec_id
            != self.selection_spec_id
            or self.materialization_generation.session_start_ms
            != self.session_start_ms
        ):
            raise ValueError("Materialization Generation differs from readonly period")
        if any(
            vacuum.strategy_group_id != self.strategy_group_id
            or vacuum.selection_spec_id != self.selection_spec_id
            or vacuum.period_anchor_ms != self.session_start_ms
            for vacuum in self.entry_vacuums
        ):
            raise ValueError("Entry Vacuum differs from readonly period")
        if any(
            audit.selection_spec_id != self.selection_spec_id
            or audit.session_start_ms != self.session_start_ms
            for audit in self.authority_gap_audits
        ):
            raise ValueError("Authority Gap Audit differs from readonly period")
        if self.current_authority is None:
            if self.first_eligible_close_time_ms is not None:
                raise ValueError("first eligible close requires current Authority")
        elif (
            self.current_authority.authority.selection_spec_id
            != self.selection_spec_id
            or self.current_authority.authority.session_start_ms
            != self.session_start_ms
            or self.first_eligible_close_time_ms
            != self.current_authority.authority.first_eligible_close_time_ms
        ):
            raise ValueError("current Authority differs from readonly period")
        return self


async def get_monitor_state(
    uow: KernelUnitOfWork,
    monitor_key: str,
) -> MonitorStateRecord | None:
    normalized = str(monitor_key or "").strip()
    if not normalized:
        raise ValueError("monitor_key must be non-blank")
    return await uow.monitors.get(normalized)


async def get_owner_projection(
    uow: KernelUnitOfWork,
    ticket_id: str,
) -> MonitorStateRecord | None:
    return await uow.monitors.get(owner_ticket_monitor_key(ticket_id))


async def get_selection_runtime_view(
    uow: KernelUnitOfWork,
    request: SelectionRuntimeReadonlyRequest,
) -> SelectionRuntimeReadonlyView:
    """Read one exact Selection Period without deriving state from history."""

    repository = uow.instrument_selection
    control = await repository.get_selection_control(request.strategy_group_id)
    job = await repository.get_selection_job(
        selection_spec_id=request.selection_spec_id,
        period_anchor_ms=request.session_start_ms,
    )
    snapshot = await repository.get_snapshot_disposition(
        selection_spec_id=request.selection_spec_id,
        session_start_ms=request.session_start_ms,
    )
    generation = await repository.get_materialization_generation_for_period(
        strategy_group_id=request.strategy_group_id,
        selection_spec_id=request.selection_spec_id,
        session_start_ms=request.session_start_ms,
    )
    vacuums = await repository.list_entry_vacuums_for_period(
        strategy_group_id=request.strategy_group_id,
        selection_spec_id=request.selection_spec_id,
        session_start_ms=request.session_start_ms,
        limit=_PERIOD_FACT_LIMIT,
    )
    audits = await repository.list_authority_gap_audits_for_period(
        selection_spec_id=request.selection_spec_id,
        session_start_ms=request.session_start_ms,
        limit=_PERIOD_FACT_LIMIT,
    )
    current_authority = await repository.get_current_authority_projection(
        request.selection_spec_id
    )
    if (
        current_authority is not None
        and current_authority.authority.session_start_ms != request.session_start_ms
    ):
        current_authority = None
    release_fact = (
        None
        if request.release_compatibility_id is None
        else await repository.get_runtime_release_compatibility_fact(
            request.release_compatibility_id
        )
    )
    return SelectionRuntimeReadonlyView(
        strategy_group_id=request.strategy_group_id,
        selection_spec_id=request.selection_spec_id,
        session_start_ms=request.session_start_ms,
        selection_control=control,
        selection_job=job,
        snapshot_disposition=snapshot,
        materialization_generation=generation,
        entry_vacuums=vacuums,
        authority_gap_audits=audits,
        current_authority=current_authority,
        first_eligible_close_time_ms=(
            None
            if current_authority is None
            else current_authority.authority.first_eligible_close_time_ms
        ),
        release_compatibility_fact=release_fact,
    )


async def get_exit_profile_authority_view(
    repository: ExitProfileAuthorityRepository,
    request: ExitProfileAuthorityReadonlyRequest,
) -> ExitProfileAuthorityReadonlyView:
    profiles = await repository.list_profiles(limit=_EXIT_PROFILE_LIMIT)
    current_bindings = await repository.list_current_bindings(
        event_spec_id=request.event_spec_id,
        limit=_EXIT_PROFILE_LIMIT,
    )
    binding_fact_items = []
    for current in current_bindings:
        binding = await repository.get_binding(current.exit_binding_id)
        if binding is not None:
            binding_fact_items.append(binding)
    binding_facts = tuple(binding_fact_items)
    if len(binding_facts) != len(current_bindings):
        raise ValueError("current ExitProfile Binding fact is missing")
    recent_events = await repository.list_binding_events(
        event_spec_id=request.event_spec_id,
        limit=request.event_limit,
    )
    return ExitProfileAuthorityReadonlyView(
        event_spec_id=request.event_spec_id,
        catalog_digest=build_exit_profile_catalog_digest(),
        profiles=profiles,
        current_bindings=current_bindings,
        binding_facts=binding_facts,
        recent_events=recent_events,
    )
