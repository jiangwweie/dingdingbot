"""Generic Generation identity and previous Event facts; no execution authority."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.domain.comparison_universe import ComparisonUniverseBinding
from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.generic_selection_core import GenericSelectionSnapshotV1
from src.trading_kernel.domain.generic_selection_spec import generic_selection_spec
from src.trading_kernel.domain.selection_authority import (
    AuthorityEventBinding,
    MaterializationGenerationClaimStatus,
    MaterializationGenerationState,
)


def generic_input_is_unchanged(snapshot: GenericSelectionSnapshotV1, *, current_members: tuple[str, ...],
    comparison: ComparisonUniverseBinding | None) -> bool:
    """Membership equality alone cannot prove comparative Detector input equality."""
    snapshot = GenericSelectionSnapshotV1.model_validate(snapshot.model_dump())
    spec = generic_selection_spec(snapshot.strategy_group_id)
    if not current_members or tuple(sorted(set(current_members))) != current_members:
        raise ValueError("current members must be complete and canonical")
    if snapshot.strategy_group_id in {"MPG-001", "MI-001"}:
        if comparison is None or comparison.event_spec_id != spec.event_spec_id:
            raise ValueError("current comparison identity is missing or differs")
        if comparison.exchange_instrument_ids != spec.candidate_ids:
            return False
    elif comparison is not None:
        raise ValueError("non-comparative Event forbids comparison input")
    return snapshot.selected_members == current_members


class MaterializationEventBaseline(AuthorityEventBinding):
    comparison_universe_id: str | None = None
    comparison_transition_revision: int | None = None

    @model_validator(mode="after")
    def _comparison_identity(self) -> MaterializationEventBaseline:
        if (self.comparison_universe_id is None) != (self.comparison_transition_revision is None):
            raise ValueError("previous comparison identity is incomplete")
        if self.comparison_universe_id is not None and (
            not self.comparison_universe_id.strip() or len(self.comparison_universe_id)>160
            or self.comparison_transition_revision is None or self.comparison_transition_revision<0
        ):
            raise ValueError("previous comparison identity is invalid")
        return self


class GenericMaterializationGeneration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    materialization_generation_id: str
    selection_spec_id: str
    strategy_group_id: str
    strategy_version_id: str
    selection_mode: Literal["dynamic_selection"] = "dynamic_selection"
    selection_snapshot_id: str
    selection_epoch_id: str
    selection_control_version: int
    period_anchor_ms: int
    desired_member_count: int
    previous_events: tuple[MaterializationEventBaseline, ...]
    lifecycle_state: MaterializationGenerationState = MaterializationGenerationState.PENDING
    fallback_reason_code: str | None = None
    projection_version: int = 1
    created_at_ms: int
    desired_at_ms: int | None = None
    fenced_at_ms: int | None = None
    activated_at_ms: int | None = None
    fallback_at_ms: int | None = None
    terminal_at_ms: int | None = None
    lease_owner: str | None = None
    lease_expires_at_ms: int | None = None
    lease_epoch: int = 0

    @field_validator("materialization_generation_id", "selection_spec_id", "selection_snapshot_id", "selection_epoch_id")
    @classmethod
    def _bounded_identity(cls, value: str) -> str:
        if not value.strip() or value!=value.strip() or len(value)>160:
            raise ValueError("Generation identity must be canonical and bounded")
        return value

    @model_validator(mode="after")
    def _generation_contract(self) -> GenericMaterializationGeneration:
        spec = generic_selection_spec(self.strategy_group_id)
        if (self.selection_spec_id!=spec.selection_spec_id or self.strategy_version_id!=spec.strategy_version_id
            or self.selection_epoch_id=="sor-v0" or self.selection_control_version<=0):
            raise ValueError("Generation Spec/epoch/control identity differs")
        t = self.period_anchor_ms
        if t<=0 or t % (spec.cadence_hours*3600000) or not t+3600000<=self.created_at_ms<t+(1+spec.cadence_hours)*3600000:
            raise ValueError("Generation must be created in its effective period")
        expected_snapshot = "selection:"+canonical_digest({"spec":self.selection_spec_id,"epoch":self.selection_epoch_id,"cutoff":t})[7:]
        if self.selection_snapshot_id!=expected_snapshot or self.materialization_generation_id!="generation:"+canonical_digest({"snapshot":expected_snapshot})[7:]:
            raise ValueError("Generation Snapshot identity differs")
        if not 1<=self.desired_member_count<=spec.retain_rank:
            raise ValueError("Generation requires nonempty bounded Desired membership")
        if len(self.previous_events)!=1:
            raise ValueError("Generation requires exact previous Event set")
        prior = self.previous_events[0]
        if prior.event_spec_id!=spec.event_spec_id or prior.position_side!=spec.position_side:
            raise ValueError("Generation previous Event differs from Spec")
        if (self.strategy_group_id in {"MPG-001","MI-001"}) != (prior.comparison_universe_id is not None):
            raise ValueError("Generation comparison scope differs from Spec")
        if self.projection_version<=0 or self.lease_epoch<0 or (self.lease_owner is None)!=(self.lease_expires_at_ms is None):
            raise ValueError("Generation projection/lease shape differs")
        if self.lease_owner is not None and (not self.lease_owner.strip() or self.lease_epoch<=0 or self.lease_expires_at_ms is None or self.lease_expires_at_ms<=self.created_at_ms):
            raise ValueError("Generation lease identity is invalid")
        if self.lifecycle_state is MaterializationGenerationState.PENDING and self.desired_at_ms is not None:
            raise ValueError("pending Generation cannot claim desired time")
        if self.lifecycle_state is MaterializationGenerationState.DESIRED and self.desired_at_ms is None:
            raise ValueError("desired Generation requires desired time")
        for timestamp in (self.desired_at_ms,self.fenced_at_ms,self.activated_at_ms,self.fallback_at_ms,self.terminal_at_ms):
            if timestamp is not None and timestamp<self.created_at_ms:
                raise ValueError("Generation lifecycle time moves backwards")
        if self.lifecycle_state is MaterializationGenerationState.FALLBACK_PREVIOUS:
            if not self.fallback_reason_code or self.fallback_at_ms is None or self.terminal_at_ms is None:
                raise ValueError("fallback Generation requires terminal reason and time")
        elif self.fallback_reason_code is not None:
            raise ValueError("non-fallback Generation cannot claim fallback reason")
        return self

    @property
    def semantic_digest(self) -> str:
        return canonical_digest(self.model_dump(mode="json", include={
            "selection_spec_id","strategy_group_id","strategy_version_id","selection_mode","selection_snapshot_id",
            "selection_epoch_id","selection_control_version","period_anchor_ms","desired_member_count","previous_events",
        }))

    @classmethod
    def build(cls, *, snapshot: GenericSelectionSnapshotV1, previous_events: tuple[MaterializationEventBaseline,...],
              selection_control_version: int, created_at_ms: int) -> GenericMaterializationGeneration:
        snapshot = GenericSelectionSnapshotV1.model_validate(snapshot.model_dump())
        if not snapshot.selected_members:
            raise ValueError("valid empty Selection has no Generation")
        spec = generic_selection_spec(snapshot.strategy_group_id)
        return cls(materialization_generation_id=cls.id_for_snapshot(snapshot.selection_snapshot_id),
            selection_spec_id=spec.selection_spec_id,strategy_group_id=spec.strategy_group_id,strategy_version_id=spec.strategy_version_id,
            selection_snapshot_id=snapshot.selection_snapshot_id,selection_epoch_id=snapshot.selection_epoch_id,
            selection_control_version=selection_control_version,period_anchor_ms=snapshot.feature_cutoff_at_ms,
            desired_member_count=len(snapshot.selected_members),previous_events=previous_events,created_at_ms=created_at_ms)

    @staticmethod
    def id_for_snapshot(selection_snapshot_id: str) -> str:
        return "generation:"+canonical_digest({"snapshot":selection_snapshot_id})[7:]


class GenericMaterializationLeaseClaim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    status: MaterializationGenerationClaimStatus
    generation: GenericMaterializationGeneration | None = None

    @model_validator(mode="after")
    def _shape(self) -> GenericMaterializationLeaseClaim:
        if self.status is MaterializationGenerationClaimStatus.NO_GENERATION:
            if self.generation is not None:
                raise ValueError("absent claim cannot include Generation")
        elif self.generation is None or self.generation.lease_owner is None:
            raise ValueError("Generation lease result requires exact lease identity")
        return self
