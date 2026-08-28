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
from src.trading_kernel.domain.instrument_selection import DAY_MS
from src.trading_kernel.domain.selection_authority import (
    AuthorityGapAudit,
    CurrentSelectionAuthority,
    MaterializationGeneration,
    SelectionControl,
    SelectionSnapshotDisposition,
)
from src.trading_kernel.domain.strategy_entry_vacuum import StrategyEntryVacuum

_PERIOD_FACT_LIMIT = 8
_EXIT_PROFILE_LIMIT = 32


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
            or self.selection_job.session_start_ms != self.session_start_ms
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
            or vacuum.session_start_ms != self.session_start_ms
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
        session_start_ms=request.session_start_ms,
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
