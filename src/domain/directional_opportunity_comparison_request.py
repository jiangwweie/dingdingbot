"""Pure request model for one Directional Opportunity comparison input."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.directional_opportunity_forward_outcome import pack_forward_outcome_windows
from src.domain.directional_opportunity_pack import (
    DirectionalPackCandidateRole,
    DirectionalOpportunityPackSpec,
)
from src.domain.strategy_family_signal import SignalSide, reject_forbidden_execution_fields


class DirectionalOpportunityComparisonRequest(BaseModel):
    """One non-persistent historical comparison request descriptor."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_family_id: str = Field(min_length=1, max_length=128)
    candidate_role: DirectionalPackCandidateRole
    candidate_roles: list[DirectionalPackCandidateRole]
    symbol: str = Field(min_length=1, max_length=128)
    side: SignalSide
    base_timeframe: str = Field(default="1h", min_length=1, max_length=32)
    forward_windows: dict[str, int] = Field(default_factory=dict)
    non_persistent: Literal[True] = True

    @model_validator(mode="after")
    def _validate_request(self) -> "DirectionalOpportunityComparisonRequest":
        if not self.candidate_roles:
            raise ValueError("candidate_roles must not be empty")
        if self.candidate_role not in self.candidate_roles:
            raise ValueError("candidate_role must be included in candidate_roles")
        if not self.forward_windows:
            raise ValueError("forward_windows must not be empty")
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root="directional_comparison_request")
        return self


def build_directional_opportunity_comparison_request(
    *,
    spec: DirectionalOpportunityPackSpec,
    candidate_family_id: str,
    symbol: str,
    side: str | SignalSide,
    base_timeframe: str = "1h",
) -> DirectionalOpportunityComparisonRequest:
    """Build one validated non-persistent historical comparison request."""

    candidate = _candidate_by_id(spec, candidate_family_id)
    if symbol not in spec.canonical_symbols:
        raise ValueError(f"symbol is not in directional opportunity pack: {symbol}")

    try:
        resolved_side = side if isinstance(side, SignalSide) else SignalSide(side)
    except ValueError as exc:
        raise ValueError(f"side is not supported by directional opportunity pack: {side}") from exc

    if resolved_side not in spec.sides:
        raise ValueError(f"side is not in directional opportunity pack: {resolved_side.value}")
    if resolved_side not in candidate.supported_sides:
        raise ValueError(
            f"side is not supported by candidate family {candidate_family_id}: {resolved_side.value}"
        )

    window_request = pack_forward_outcome_windows(spec, primary_timeframe=base_timeframe)
    return DirectionalOpportunityComparisonRequest(
        candidate_family_id=candidate.family_id,
        candidate_role=candidate.candidate_roles[0],
        candidate_roles=list(candidate.candidate_roles),
        symbol=symbol,
        side=resolved_side,
        base_timeframe=window_request.primary_timeframe,
        forward_windows=dict(window_request.windows),
    )


def _candidate_by_id(spec: DirectionalOpportunityPackSpec, candidate_family_id: str):
    for candidate in spec.candidate_families:
        if candidate.family_id == candidate_family_id:
            return candidate
    raise ValueError(f"candidate_family_id is not in directional opportunity pack: {candidate_family_id}")
