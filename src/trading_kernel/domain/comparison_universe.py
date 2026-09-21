"""Immutable comparison membership, independent of tradable Universe capacity."""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.instrument_selection import (
    CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS,
)


def comparative_lookback_bars(event_spec_id: str) -> int | None:
    """Frozen Detector input geometry, not a configurable selection threshold."""
    return {
        "event_spec:MPG-001:MPG-LONG:v3": 8,
        "event_spec:MI-001:MI-LONG:v3": 12,
    }.get(event_spec_id)


class ComparisonObservationSource(BaseModel):
    """Frozen membership and transition token captured before market I/O."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    exchange_instrument_ids: tuple[str, ...]
    comparison_transition_revision: int = Field(ge=0)


class ComparisonUniverseBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    event_spec_id: str
    comparison_universe_id: str
    member_set_digest: str
    exchange_instrument_ids: tuple[str, ...]
    comparison_transition_revision: int
    source_static_universe_version_id: str | None

    @model_validator(mode="after")
    def _exact_comparison(self) -> "ComparisonUniverseBinding":
        if self.event_spec_id not in {"event_spec:MPG-001:MPG-LONG:v3", "event_spec:MI-001:MI-LONG:v3"}:
            raise ValueError("Event has no comparative Detector input")
        members = self.exchange_instrument_ids
        if not members or tuple(sorted(set(members)))!=members or len(members)>24:
            raise ValueError("comparison membership is not canonical")
        digest = canonical_digest({"exchange_instrument_ids":members})
        if self.member_set_digest!=digest or self.comparison_universe_id!="comparison:"+digest[7:]:
            raise ValueError("comparison definition identity differs")
        if self.comparison_transition_revision<0:
            raise ValueError("comparison revision is invalid")
        if self.source_static_universe_version_id is None:
            if members!=CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS or self.comparison_transition_revision<=0:
                raise ValueError("Dynamic comparison requires exact Candidate24 and transition revision")
        elif not self.source_static_universe_version_id.strip() or len(members)>10:
            raise ValueError("Static comparison requires its original bounded Universe")
        return self
