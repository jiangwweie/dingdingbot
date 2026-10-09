"""Generic Generation identity and previous Event facts; no execution authority."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.domain.comparison_universe import ComparisonUniverseBinding
from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.exposure_episode import (
    LockedObservationCursor,
    build_episode_domain_key,
)
from src.trading_kernel.domain.generic_selection_core import GenericSelectionSnapshotV1
from src.trading_kernel.domain.generic_selection_spec import generic_selection_spec
from src.trading_kernel.domain.selection_authority import (
    AuthorityEventBinding,
    MaterializationGenerationClaimStatus,
    MaterializationGenerationState,
    selected_member_set_digest,
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


class GenericStaticRollbackEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_spec_id: str
    position_side: Literal["long", "short"]
    universe_version_id: str
    universe_semantic_digest: str
    member_set_digest: str
    comparison_universe_id: str | None

    @model_validator(mode="after")
    def _exact_refs(self) -> GenericStaticRollbackEvent:
        if (
            any(not value.strip() or value != value.strip() or len(value)>160
                for value in (self.event_spec_id,self.universe_version_id))
            or any(re.fullmatch(r"sha256:[0-9a-f]{64}",digest) is None
                for digest in (self.universe_semantic_digest,self.member_set_digest))
            or self.comparison_universe_id is not None
            and re.fullmatch(r"comparison:[0-9a-f]{64}",self.comparison_universe_id) is None
        ):
            raise ValueError("Static rollback Event source references are invalid")
        return self


class GenericStaticRollbackBaseline(BaseModel):
    """Frozen source references; immutable Universe rows retain the member list."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rollback_baseline_id: str
    strategy_group_id: str
    strategy_version_id: str
    selection_spec_id: str
    selection_algorithm_digest: str
    source_event: GenericStaticRollbackEvent
    captured_at_ms: int

    @property
    def semantic_digest(self) -> str:
        return canonical_digest(self.model_dump(mode="json",exclude={
            "rollback_baseline_id","captured_at_ms",
        }))

    @model_validator(mode="after")
    def _validate_source(self) -> GenericStaticRollbackBaseline:
        spec = generic_selection_spec(self.strategy_group_id)
        source = self.source_event
        if (
            self.strategy_version_id != spec.strategy_version_id
            or self.selection_spec_id != spec.selection_spec_id
            or self.selection_algorithm_digest != spec.algorithm_semantic_digest
            or source.event_spec_id != spec.event_spec_id
            or source.position_side != spec.position_side
            or not source.universe_version_id.strip()
            or not source.universe_semantic_digest.startswith("sha256:")
            or not source.member_set_digest.startswith("sha256:")
            or (self.strategy_group_id in {"MPG-001","MI-001"})
            != (source.comparison_universe_id is not None)
            or self.captured_at_ms <= 0
            or self.rollback_baseline_id != "rollback-baseline:"+self.semantic_digest[7:]
        ):
            raise ValueError("Static rollback baseline source identity differs")
        return self

    @classmethod
    def build(
        cls, *, strategy_group_id: str, source_event: GenericStaticRollbackEvent,
        captured_at_ms: int,
    ) -> GenericStaticRollbackBaseline:
        spec = generic_selection_spec(strategy_group_id)
        payload = {
            "strategy_group_id":spec.strategy_group_id,
            "strategy_version_id":spec.strategy_version_id,
            "selection_spec_id":spec.selection_spec_id,
            "selection_algorithm_digest":spec.algorithm_semantic_digest,
            "source_event":source_event.model_dump(mode="json"),
        }
        return cls.model_validate({**payload,
            "rollback_baseline_id":"rollback-baseline:"+canonical_digest(payload)[7:],
            "captured_at_ms":captured_at_ms})


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
        if self.lifecycle_state is MaterializationGenerationState.FAILED_CLOSED and (
            self.fenced_at_ms is None or self.terminal_at_ms is None or self.activated_at_ms is not None or self.fallback_at_ms is not None):
            raise ValueError("failed Generic Generation requires terminal fenced failure without a grant")
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


class GenericStaticMaterializationGeneration(BaseModel):
    """Typed Static source of the existing Generation plane, not a Selector fact."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    materialization_generation_id: str
    selection_spec_id: str
    strategy_group_id: str
    strategy_version_id: str
    selection_mode: Literal["static_baseline"] = "static_baseline"
    selection_snapshot_id: None = None
    period_anchor_ms: None = None
    rollback_baseline_id: str
    authorization_id: str
    effective_period_anchor_ms: int
    selection_epoch_id: str
    selection_control_version: int
    desired_member_count: int
    previous_events: tuple[MaterializationEventBaseline, ...]
    created_at_ms: int
    lifecycle_state: MaterializationGenerationState = MaterializationGenerationState.PENDING
    projection_version: int = 1
    desired_at_ms: int | None = None
    fenced_at_ms: int | None = None
    activated_at_ms: int | None = None
    fallback_at_ms: int | None = None
    terminal_at_ms: int | None = None
    fallback_reason_code: str | None = None
    lease_owner: str | None = None
    lease_expires_at_ms: int | None = None
    lease_epoch: int = 0

    @staticmethod
    def id_for_authorization(authorization_id: str) -> str:
        return "generation:"+canonical_digest({"static_authorization":authorization_id})[7:]

    @property
    def semantic_digest(self) -> str:
        return canonical_digest(self.model_dump(mode="json",include={
            "selection_spec_id","strategy_group_id","strategy_version_id","selection_mode",
            "selection_snapshot_id","period_anchor_ms","rollback_baseline_id","authorization_id",
            "effective_period_anchor_ms","selection_epoch_id","selection_control_version",
            "desired_member_count","previous_events"}))

    @model_validator(mode="after")
    def _source(self) -> GenericStaticMaterializationGeneration:
        spec = generic_selection_spec(self.strategy_group_id)
        identities = (self.materialization_generation_id,self.selection_spec_id,self.rollback_baseline_id,
            self.authorization_id,self.selection_epoch_id)
        if any(not value.strip() or value!=value.strip() or len(value)>160 for value in identities) or (
            self.selection_spec_id!=spec.selection_spec_id or self.strategy_version_id!=spec.strategy_version_id
            or self.selection_epoch_id=="sor-v0" or self.selection_control_version<=0
            or self.materialization_generation_id!=self.id_for_authorization(self.authorization_id)
            or re.fullmatch(r"rollback-baseline:[0-9a-f]{64}",self.rollback_baseline_id) is None
            or self.effective_period_anchor_ms<=0 or self.effective_period_anchor_ms%(spec.cadence_hours*3600000)
            or self.created_at_ms<self.effective_period_anchor_ms+3600000 or not 1<=self.desired_member_count<=10):
            raise ValueError("Static Generation source identity differs")
        if len(self.previous_events)!=1 or self.previous_events[0].event_spec_id!=spec.event_spec_id or (
            self.previous_events[0].position_side!=spec.position_side
            or (self.strategy_group_id in {"MPG-001","MI-001"})!=(self.previous_events[0].comparison_universe_id is not None)):
            raise ValueError("Static Generation previous Event differs")
        if self.projection_version<=0 or self.lease_epoch<0 or (self.lease_owner is None)!=(self.lease_expires_at_ms is None):
            raise ValueError("Static Generation lease shape differs")
        if self.lease_owner is not None and (not self.lease_owner.strip() or self.lease_epoch<=0 or
            self.lease_expires_at_ms is None or self.lease_expires_at_ms<=self.created_at_ms):
            raise ValueError("Static Generation lease identity differs")
        for timestamp in (self.desired_at_ms,self.fenced_at_ms,self.activated_at_ms,self.fallback_at_ms,self.terminal_at_ms):
            if timestamp is not None and timestamp<self.created_at_ms:
                raise ValueError("Static Generation lifecycle time moves backwards")
        if self.lifecycle_state is MaterializationGenerationState.PENDING and self.desired_at_ms is not None:
            raise ValueError("pending Static Generation cannot claim desired time")
        if self.lifecycle_state in {MaterializationGenerationState.DESIRED,MaterializationGenerationState.DRAINING_ENTRY,
            MaterializationGenerationState.MATERIALIZING,MaterializationGenerationState.STAGED,MaterializationGenerationState.ACTIVE} and self.desired_at_ms is None:
            raise ValueError("Static Generation requires desired time")
        if self.lifecycle_state in {MaterializationGenerationState.DRAINING_ENTRY,MaterializationGenerationState.MATERIALIZING,
            MaterializationGenerationState.STAGED,MaterializationGenerationState.ACTIVE,MaterializationGenerationState.FAILED_CLOSED} and self.fenced_at_ms is None:
            raise ValueError("Static Generation requires fenced time")
        if self.lifecycle_state is MaterializationGenerationState.ACTIVE and (
            self.activated_at_ms is None or self.terminal_at_ms!=self.activated_at_ms or self.fallback_at_ms is not None):
            raise ValueError("Static Generation activation must be terminal without fallback")
        if self.lifecycle_state is MaterializationGenerationState.FAILED_CLOSED and (
            self.terminal_at_ms is None or self.activated_at_ms is not None or self.fallback_at_ms is not None):
            raise ValueError("Static Generation failure cannot claim activation")
        if self.lifecycle_state is MaterializationGenerationState.FALLBACK_PREVIOUS:
            if not self.fallback_reason_code or self.fallback_at_ms is None or self.terminal_at_ms!=self.fallback_at_ms:
                raise ValueError("Static Generation fallback requires terminal evidence")
        elif self.fallback_reason_code is not None:
            raise ValueError("Static Generation nonfallback cannot claim reason")
        return self


class GenericStaticActivationProof(BaseModel):
    """Locked handoff evidence only; preparing it grants no Entry authority."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    selection_spec_id: str
    strategy_group_id: str
    selection_epoch_id: str
    selection_control_version: int
    owner_control_version: int
    authorization_id: str
    owner_authorized_at_ms: int
    rollback_baseline_id: str
    materialization_generation_id: str
    effective_period_anchor_ms: int
    entry_vacuum_id: str
    vacuum_version: int
    fenced_at_ms: int
    drained_at_ms: int
    previous_event: MaterializationEventBaseline
    source_selection_authority_id: str
    target_event: AuthorityEventBinding
    transition_rule: Literal["NORMAL_TRANSITION","RECOVERY_TRANSITION"]
    recovery_reason: Literal["AUTHORITY_GAP","OWNER_INTERRUPTION","RECOVERY_PROVENANCE"] | None
    first_eligible_close_time_ms: int
    prepared_at_ms: int
    comparison_universe_id: str | None
    comparison_transition_revision: int | None
    observation_cursors: tuple[LockedObservationCursor,...]

    @property
    def episode_rebase_required(self) -> bool:
        return self.transition_rule=="RECOVERY_TRANSITION"

    @property
    def comparison_rebase_required(self) -> bool:
        return self.comparison_universe_id!=self.previous_event.comparison_universe_id

    @property
    def result_selection_control_version(self) -> int:
        return self.selection_control_version+1

    @property
    def semantic_digest(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))

    @model_validator(mode="after")
    def _contract(self) -> GenericStaticActivationProof:
        spec = generic_selection_spec(self.strategy_group_id)
        ids = (self.selection_spec_id,self.selection_epoch_id,self.authorization_id,self.rollback_baseline_id,
            self.materialization_generation_id,self.entry_vacuum_id,self.source_selection_authority_id)
        if any(not value.strip() or value!=value.strip() or len(value)>160 for value in ids) or (
            self.selection_spec_id!=spec.selection_spec_id or self.selection_epoch_id=="sor-v0"
            or self.materialization_generation_id!=GenericStaticMaterializationGeneration.id_for_authorization(self.authorization_id)
            or re.fullmatch(r"rollback-baseline:[0-9a-f]{64}",self.rollback_baseline_id) is None
            or min(self.selection_control_version,self.owner_control_version,self.vacuum_version)<=0
            or self.effective_period_anchor_ms<=0 or self.effective_period_anchor_ms%(spec.cadence_hours*3600000)
            or not 0<self.owner_authorized_at_ms<self.effective_period_anchor_ms
            or not self.effective_period_anchor_ms+3600000<=self.fenced_at_ms<=self.drained_at_ms<=self.prepared_at_ms):
            raise ValueError("Static activation source/time identity differs")
        for event in (self.previous_event,self.target_event):
            if (event.event_spec_id,event.position_side)!=(spec.event_spec_id,spec.position_side) or event.grant_state.value!="ACTIVE":
                raise ValueError("Static activation Event identity differs")
        if self.target_event.universe_version_id==self.previous_event.universe_version_id:
            raise ValueError("Static activation requires a new Universe")
        members = tuple(cursor.exchange_instrument_id for cursor in self.observation_cursors)
        if not 1<=len(members)<=10 or tuple(sorted(set(members)))!=members or selected_member_set_digest(members)!=self.target_event.member_set_digest:
            raise ValueError("Static activation complete member coverage differs")
        expected_close = self.prepared_at_ms//3600000*3600000
        if self.transition_rule=="RECOVERY_TRANSITION":
            expected_close += 3600000
            if self.recovery_reason is None:
                raise ValueError("Static recovery requires classified provenance")
        elif self.recovery_reason is not None or self.owner_authorized_at_ms>=expected_close or self.prepared_at_ms<=expected_close:
            raise ValueError("Static normal close requires precommitted Owner input")
        if self.first_eligible_close_time_ms!=expected_close or self.first_eligible_close_time_ms<self.effective_period_anchor_ms+3600000:
            raise ValueError("Static activation close identity differs")
        for cursor in self.observation_cursors:
            if cursor.episode_domain_key!=build_episode_domain_key(event_spec_id=spec.event_spec_id,
                exchange_instrument_id=cursor.exchange_instrument_id,position_side=spec.position_side) or (
                cursor.last_observed_at_ms is not None and cursor.last_observed_at_ms>=self.first_eligible_close_time_ms):
                raise ValueError("Static activation close already consumed or scope changed")
        if spec.strategy_group_id in {"MPG-001","MI-001"}:
            expected_comparison = "comparison:"+canonical_digest({"exchange_instrument_ids":members})[7:]
            old_revision = self.previous_event.comparison_transition_revision
            if self.comparison_universe_id!=expected_comparison or old_revision is None or self.comparison_transition_revision!=old_revision+int(
                self.comparison_universe_id!=self.previous_event.comparison_universe_id):
                raise ValueError("Static activation comparison transition differs")
        elif self.comparison_universe_id is not None or self.comparison_transition_revision is not None:
            raise ValueError("Static noncomparative activation cannot claim comparison")
        return self


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
