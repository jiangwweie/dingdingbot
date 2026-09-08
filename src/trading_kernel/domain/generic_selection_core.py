"""Pure frozen features and Desired hysteresis; no current Universe dependency."""

from __future__ import annotations

from decimal import Decimal, localcontext

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.domain.dynamic_selection_numeric import (
    DYNAMIC_SELECTION_DECIMAL_CONTEXT,
    DynamicSelectionNumericError,
    absolute_directional_efficiency_24h,
    persistent_leadership_score_6h,
    positive_impulse_recency_12h,
    rank_brf2_residual_extension_v0_decimal,
    rank_dynamic_selection_features,
)
from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.generic_selection_source import (
    GenericSelectionMemberWindow,
    GenericSelectionQualification,
    QualificationReason,
)
from src.trading_kernel.domain.generic_selection_spec import (
    GenericSelectionSpecV1,
    generic_selection_spec,
)

HOUR_MS=3600000


class GenericSelectionMemberDecision(BaseModel):
    model_config=ConfigDict(frozen=True,extra="forbid")
    exchange_instrument_id: str
    feature_value: Decimal
    stable_rank: int
    qualified: bool
    selected: bool
    retained: bool
    input_window_digest: str
    qualification: GenericSelectionQualification

    @field_validator("feature_value",mode="before")
    @classmethod
    def _feature_decimal(cls,value: object) -> object:
        if isinstance(value,float):
            raise TypeError("feature cannot enter through binary64")
        return value

    @model_validator(mode="after")
    def _valid_decision(self) -> GenericSelectionMemberDecision:
        if not self.feature_value.is_finite() or not 1<=self.stable_rank<=24:
            raise ValueError("invalid feature/rank")
        _require_digest(self.input_window_digest)
        if self.qualification.product_profile.exchange_instrument_id != self.exchange_instrument_id:
            raise ValueError("member qualification instrument differs")
        if self.qualified != (self.qualification_reason is None):
            raise ValueError("member qualification reason differs")
        if (not self.qualified and (self.selected or self.retained)) or self.retained and not self.selected:
            raise ValueError("invalid member qualification/retention")
        return self

    @property
    def qualification_reason(self) -> QualificationReason | None:
        return self.qualification.reason

    @property
    def qualification_semantic_digest(self) -> str:
        return self.qualification.semantic_digest

    @property
    def semantic_digest(self) -> str:
        with localcontext(DYNAMIC_SELECTION_DECIMAL_CONTEXT):
            return canonical_digest(self.model_dump(mode="python"))


class GenericSelectionSnapshotV1(BaseModel):
    model_config=ConfigDict(frozen=True,extra="forbid")
    selection_snapshot_id: str
    selection_spec_id: str
    spec_semantic_digest: str
    strategy_group_id: str
    selection_epoch_id: str
    feature_cutoff_at_ms: int
    effective_from_ms: int
    expires_at_ms: int
    committed_at_ms: int
    predecessor_snapshot_id: str | None
    predecessor_member_digest: str | None
    members: tuple[GenericSelectionMemberDecision,...]
    source_semantic_digest: str

    @model_validator(mode="after")
    def _snapshot_contract(self) -> GenericSelectionSnapshotV1:
        spec=generic_selection_spec(self.strategy_group_id)
        if self.selection_spec_id!=spec.selection_spec_id or self.spec_semantic_digest!=spec.algorithm_semantic_digest:
            raise ValueError("snapshot Spec identity differs")
        t=self.feature_cutoff_at_ms
        if not self.selection_epoch_id.strip() or t<=0 or t%(spec.cadence_hours*HOUR_MS):
            raise ValueError("invalid snapshot period/epoch")
        if self.effective_from_ms!=t+HOUR_MS or self.expires_at_ms!=t+(spec.cadence_hours+1)*HOUR_MS or self.committed_at_ms<t:
            raise ValueError("invalid snapshot time")
        expected_id="selection:"+canonical_digest({"spec":self.selection_spec_id,"epoch":self.selection_epoch_id,"cutoff":t})[7:]
        if self.selection_snapshot_id!=expected_id:
            raise ValueError("snapshot ID differs from epoch/period")
        if (self.predecessor_snapshot_id is None)!=(self.predecessor_member_digest is None):
            raise ValueError("incomplete predecessor identity")
        if self.predecessor_snapshot_id==self.selection_snapshot_id:
            raise ValueError("snapshot cannot precede itself")
        if self.predecessor_member_digest is not None:
            _require_digest(self.predecessor_member_digest)
        _require_digest(self.source_semantic_digest)
        if tuple(sorted(member.exchange_instrument_id for member in self.members))!=spec.candidate_ids:
            raise ValueError("snapshot requires complete Candidate24")
        ranked=tuple(sorted(self.members,key=lambda member:(member.feature_value.copy_negate(),member.exchange_instrument_id)))
        if self.members!=ranked or tuple(member.stable_rank for member in ranked)!=tuple(range(1,25)):
            raise ValueError("snapshot ranking differs from frozen order")
        for member in ranked:
            if (member.qualification.event_spec_id != spec.event_spec_id
                or not t <= member.qualification.observed_at_ms <= self.committed_at_ms):
                raise ValueError("snapshot qualification Event/time differs")
            expected_selected=member.qualified and (member.stable_rank<=spec.entry_rank or member.retained)
            if (member.selected!=expected_selected or member.selected and member.stable_rank>spec.retain_rank
                or member.retained and self.predecessor_snapshot_id is None):
                raise ValueError("snapshot membership exceeds frozen admission/retention")
        return self

    @property
    def selected_members(self) -> tuple[str,...]:
        return tuple(sorted(member.exchange_instrument_id for member in self.members if member.selected))

    @property
    def ready_count(self) -> int:
        return sum(member.qualified for member in self.members)

    @property
    def member_set_digest(self) -> str:
        return canonical_digest({"selected_exchange_instrument_ids":self.selected_members})

    @property
    def semantic_digest(self) -> str:
        with localcontext(DYNAMIC_SELECTION_DECIMAL_CONTEXT):
            # Decimal semantic value, not driver-specific exponent/negative-zero text.
            return canonical_digest(self.model_dump(mode="python"))


class GenericSelectionInput(BaseModel):
    model_config=ConfigDict(frozen=True,extra="forbid")
    spec: GenericSelectionSpecV1
    selection_epoch_id: str
    feature_cutoff_at_ms: int
    decision_at_ms: int
    source_observed_at_ms: int
    committed_at_ms: int
    member_windows: tuple[GenericSelectionMemberWindow,...]
    predecessor_snapshot: GenericSelectionSnapshotV1 | None

    @property
    def source_semantic_digest(self) -> str:
        windows = {window.exchange_instrument_id: window for window in self.member_windows}
        return canonical_digest(tuple((member, windows[member].input_window_digest) for member in self.spec.candidate_ids))

    @model_validator(mode="after")
    def _exact_source(self) -> GenericSelectionInput:
        t=self.feature_cutoff_at_ms
        if not self.selection_epoch_id.strip() or t<=0 or t%(self.spec.cadence_hours*HOUR_MS):
            raise ValueError("Selection period/epoch identity invalid")
        if not t<=self.decision_at_ms<=self.source_observed_at_ms<=self.committed_at_ms:
            raise ValueError("Selection source/decision/commit timing invalid")
        expected_times=tuple(t-(self.spec.window_bars-1-i)*HOUR_MS for i in range(self.spec.window_bars))
        if tuple(sorted(w.exchange_instrument_id for w in self.member_windows))!=self.spec.candidate_ids:
            raise ValueError("Selection requires exact Candidate24")
        for window in self.member_windows:
            if window.closed_at_ms!=expected_times:
                raise ValueError("Selection source gap, future candle or wrong cutoff")
            if (window.qualification.event_spec_id != self.spec.event_spec_id
                or not t <= window.qualification.observed_at_ms <= self.source_observed_at_ms):
                raise ValueError("Selection qualification is stale or belongs to another Event")
        prior=self.predecessor_snapshot
        if prior is not None and (
            prior.selection_epoch_id!=self.selection_epoch_id or prior.selection_spec_id!=self.spec.selection_spec_id
            or prior.spec_semantic_digest!=self.spec.algorithm_semantic_digest
            or prior.feature_cutoff_at_ms>=t or prior.committed_at_ms>self.committed_at_ms
        ):
            raise ValueError("Selection predecessor epoch/spec/time mismatch")
        return self


def _require_digest(value: str) -> None:
    if len(value)!=71 or not value.startswith("sha256:") or any(ch not in "0123456789abcdef" for ch in value[7:]):
        raise ValueError("invalid canonical SHA-256 identity")


def compute_generic_selection(source: GenericSelectionInput) -> GenericSelectionSnapshotV1:
    # Revalidate trusted-boundary models, including copies, before numeric work.
    source=GenericSelectionInput.model_validate(source.model_dump(mode="python"))
    spec=source.spec
    windows={w.exchange_instrument_id:w for w in source.member_windows}
    prior=source.predecessor_snapshot
    previous=set() if prior is None else set(prior.selected_members)
    with localcontext(DYNAMIC_SELECTION_DECIMAL_CONTEXT):
        if spec.strategy_group_id=="BRF2-001":
            ranked=rank_brf2_residual_extension_v0_decimal({m:windows[m].closes for m in spec.candidate_ids})
        else:
            if spec.strategy_group_id=="MPG-001":
                histories: dict[str,list[int]]={m:[] for m in spec.candidate_ids}
                for offset in range(5,-1,-1):
                    returns={m:(windows[m].closes[-1-offset]-windows[m].closes[-9-offset])/windows[m].closes[-9-offset]*100 for m in spec.candidate_ids}
                    for rank,member in enumerate(sorted(returns,key=lambda m:(returns[m].copy_negate(),m)),1):
                        histories[member].append(rank)
                values={m:persistent_leadership_score_6h(histories[m]) for m in spec.candidate_ids}
            elif spec.strategy_group_id=="CPM-RO-001":
                values = {}
                for m in spec.candidate_ids:
                    try:
                        values[m] = absolute_directional_efficiency_24h(windows[m].closes)
                    except DynamicSelectionNumericError as exc:
                        raise DynamicSelectionNumericError(f"{m}:{exc}") from exc
            else:
                values={m:positive_impulse_recency_12h(tuple(b/a-1 for a,b in zip(windows[m].closes,windows[m].closes[1:]))) for m in spec.candidate_ids}
            ranked=rank_dynamic_selection_features(values)
        decisions=tuple(GenericSelectionMemberDecision(
            exchange_instrument_id=rank.exchange_instrument_id,feature_value=rank.feature_value,stable_rank=rank.rank,
            qualified=windows[rank.exchange_instrument_id].qualified,
            selected=windows[rank.exchange_instrument_id].qualified and (rank.rank<=spec.entry_rank or rank.exchange_instrument_id in previous and rank.rank<=spec.retain_rank),
            retained=windows[rank.exchange_instrument_id].qualified and rank.exchange_instrument_id in previous and rank.rank<=spec.retain_rank,
            input_window_digest=windows[rank.exchange_instrument_id].input_window_digest,
            qualification=windows[rank.exchange_instrument_id].qualification,
        ) for rank in ranked)
        identity=canonical_digest({"spec":spec.selection_spec_id,"epoch":source.selection_epoch_id,"cutoff":source.feature_cutoff_at_ms})
        return GenericSelectionSnapshotV1(
            selection_snapshot_id="selection:"+identity[7:],selection_spec_id=spec.selection_spec_id,
            spec_semantic_digest=spec.algorithm_semantic_digest,strategy_group_id=spec.strategy_group_id,
            selection_epoch_id=source.selection_epoch_id,feature_cutoff_at_ms=source.feature_cutoff_at_ms,
            effective_from_ms=source.feature_cutoff_at_ms+HOUR_MS,
            expires_at_ms=source.feature_cutoff_at_ms+(1+spec.cadence_hours)*HOUR_MS,
            committed_at_ms=source.committed_at_ms,predecessor_snapshot_id=None if prior is None else prior.selection_snapshot_id,
            predecessor_member_digest=None if prior is None else prior.member_set_digest,members=decisions,
            source_semantic_digest=source.source_semantic_digest,
        )
