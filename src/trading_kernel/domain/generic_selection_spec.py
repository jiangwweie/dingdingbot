"""Frozen strategy-specific parameter schemas, not installation or trade grants."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.instrument_selection import (
    CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS,
)

# Family definition is deliberately separate from installed/approved Spec state.
_FAMILIES: dict[str, tuple[str, str, Literal["long", "short"], int, int, int, int]] = {
    "CPM-RO-001": ("CPM_ABSOLUTE_DIRECTIONAL_EFFICIENCY_V1", "CPM-LONG", "long", 16, 16, 4, 25),
    "MPG-001": ("MPG_PERSISTENT_LEADERSHIP_SCORE_V1", "MPG-LONG", "long", 12, 16, 1, 14),
    "MI-001": ("MI_POSITIVE_IMPULSE_RECENCY_V0", "MI-LONG", "long", 16, 16, 1, 13),
    "BRF2-001": ("BRF2_RESIDUAL_EXTENSION_V0", "BRF2-SHORT", "short", 16, 16, 4, 73),
}


class GenericSelectionSpecV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    selection_spec_id: str
    strategy_group_id: str
    strategy_version_id: str
    event_spec_id: str
    position_side: Literal["long", "short"]
    entry_rank: int
    retain_rank: int
    cadence_hours: int
    window_bars: int
    candidate_ids: tuple[str, ...] = CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS
    delay_ms: Literal[3600000] = 3600000
    decimal_precision: Literal[38] = 38
    decimal_rounding: Literal["ROUND_HALF_EVEN"] = "ROUND_HALF_EVEN"
    max_consecutive_selection_miss: Literal[1] = 1
    materialization_timeout_ms: Literal[1800000] = 1800000
    numeric_contract_version: Literal["decimal38-canonical-order-v1"] = "decimal38-canonical-order-v1"

    @model_validator(mode="after")
    def _frozen_family(self) -> GenericSelectionSpecV1:
        family = _FAMILIES.get(self.strategy_group_id)
        if family is None:
            raise ValueError("unsupported Generic Selection family")
        spec_id, event, side, entry, retain, cadence, bars = family
        expected = (spec_id, f"sgv:{self.strategy_group_id}:v3", f"event_spec:{self.strategy_group_id}:{event}:v3", side, entry, retain, cadence, bars)
        actual = (self.selection_spec_id,self.strategy_version_id,self.event_spec_id,self.position_side,self.entry_rank,self.retain_rank,self.cadence_hours,self.window_bars)
        if actual != expected or self.candidate_ids != CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS:
            raise ValueError("Generic Selection parameters differ from frozen family")
        return self

    @property
    def algorithm_semantic_digest(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))


def generic_selection_spec(strategy_group_id: str) -> GenericSelectionSpecV1:
    family = _FAMILIES.get(strategy_group_id)
    if family is None:
        raise ValueError("unsupported Generic Selection family")
    spec_id,event,side,entry,retain,cadence,bars = family
    return GenericSelectionSpecV1(
        selection_spec_id=str(spec_id), strategy_group_id=strategy_group_id,
        strategy_version_id=f"sgv:{strategy_group_id}:v3",event_spec_id=f"event_spec:{strategy_group_id}:{event}:v3",
        position_side=side, entry_rank=entry,retain_rank=retain,cadence_hours=cadence,window_bars=bars,
    )


class SpecNumericInstallationEvidence(BaseModel):
    """Local release precondition; not an Owner-supplied activation payload."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    selection_spec_id: str
    algorithm_semantic_digest: str
    checked_cutoffs: int
    mismatch_count: Literal[0]
    source_archive_count: Literal[96]
    reference_commit: Literal["f65d72fa92580de4b8c0323f4106d5975b97f4eb"]
    common_numeric_authority: Literal["PASS"]
    sor_golden: Literal["PASS"]
    spec_cert: Literal["PASS"]

    def require_spec(self, spec: GenericSelectionSpecV1) -> None:
        SpecNumericInstallationEvidence.model_validate(self.model_dump(mode="python"))
        GenericSelectionSpecV1.model_validate(spec.model_dump(mode="python"))
        if (self.selection_spec_id != spec.selection_spec_id
            or self.algorithm_semantic_digest != spec.algorithm_semantic_digest
            or self.checked_cutoffs != (463 if spec.cadence_hours == 4 else 1852)):
            raise ValueError("numeric installation evidence does not certify this Spec")
