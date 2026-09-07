"""Pure frozen features and Desired hysteresis; no current Universe dependency."""

from __future__ import annotations

from decimal import Decimal, localcontext

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.domain.dynamic_selection_numeric import (
    DYNAMIC_SELECTION_DECIMAL_CONTEXT,
    absolute_directional_efficiency_24h,
    persistent_leadership_score_6h,
    positive_impulse_recency_12h,
    rank_brf2_residual_extension_v0_decimal,
    rank_dynamic_selection_features,
)
from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.generic_selection_spec import GenericSelectionSpecV1

HOUR_MS=3600000


class GenericSelectionMemberWindow(BaseModel):
    model_config=ConfigDict(frozen=True,extra="forbid")
    exchange_instrument_id: str
    closed_at_ms: tuple[int,...]
    closes: tuple[Decimal,...]
    qualified: bool

    @field_validator("closes",mode="before")
    @classmethod
    def _decimal_only(cls,value: object) -> object:
        if not isinstance(value,(tuple,list)) or any(not isinstance(item,Decimal) for item in value):
            raise ValueError("source closes must enter as Decimal")
        return value

    @model_validator(mode="after")
    def _window(self) -> GenericSelectionMemberWindow:
        if not self.closed_at_ms or len(self.closed_at_ms)!=len(self.closes):
            raise ValueError("incomplete Selection window")
        if any(not close.is_finite() or close<=0 for close in self.closes):
            raise ValueError("invalid source price")
        if any(time<=0 or time%HOUR_MS for time in self.closed_at_ms):
            raise ValueError("noncanonical Selection close")
        if any(b-a!=HOUR_MS for a,b in zip(self.closed_at_ms,self.closed_at_ms[1:])):
            raise ValueError("noncontiguous Selection source")
        return self


class GenericSelectionMemberDecision(BaseModel):
    model_config=ConfigDict(frozen=True,extra="forbid")
    exchange_instrument_id: str
    feature_value: Decimal
    stable_rank: int
    qualified: bool
    selected: bool
    retained: bool
    input_window_digest: str


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
            return canonical_digest(self.model_dump(mode="json"))


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
        prior=self.predecessor_snapshot
        if prior is not None and (
            prior.selection_epoch_id!=self.selection_epoch_id or prior.selection_spec_id!=self.spec.selection_spec_id
            or prior.spec_semantic_digest!=self.spec.algorithm_semantic_digest
            or prior.feature_cutoff_at_ms>=t or prior.committed_at_ms>self.committed_at_ms
        ):
            raise ValueError("Selection predecessor epoch/spec/time mismatch")
        return self


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
                values={m:absolute_directional_efficiency_24h(windows[m].closes) for m in spec.candidate_ids}
            else:
                values={m:positive_impulse_recency_12h(tuple(b/a-1 for a,b in zip(windows[m].closes,windows[m].closes[1:]))) for m in spec.candidate_ids}
            ranked=rank_dynamic_selection_features(values)
        decisions=tuple(GenericSelectionMemberDecision(
            exchange_instrument_id=rank.exchange_instrument_id,feature_value=rank.feature_value,stable_rank=rank.rank,
            qualified=windows[rank.exchange_instrument_id].qualified,
            selected=windows[rank.exchange_instrument_id].qualified and (rank.rank<=spec.entry_rank or rank.exchange_instrument_id in previous and rank.rank<=spec.retain_rank),
            retained=windows[rank.exchange_instrument_id].qualified and rank.exchange_instrument_id in previous and rank.rank<=spec.retain_rank,
            input_window_digest=canonical_digest(windows[rank.exchange_instrument_id].model_dump(mode="json")),
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
            source_semantic_digest=canonical_digest(tuple((m,canonical_digest(windows[m].model_dump(mode="json"))) for m in spec.candidate_ids)),
        )
