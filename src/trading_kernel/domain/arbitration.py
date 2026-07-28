"""Deterministic ordering for fresh StrategySignal candidates."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator

from src.trading_kernel.domain.signal import StrategySignal


MAX_CANDIDATES_PER_ARBITRATION = 64


class EntryCandidate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    signal: StrategySignal
    owner_policy_priority: int

    @field_validator("owner_policy_priority")
    @classmethod
    def _require_positive_priority(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("candidate priorities must be positive")
        return value


def rank_candidates(
    candidates: tuple[EntryCandidate, ...],
) -> tuple[EntryCandidate, ...]:
    if len(candidates) > MAX_CANDIDATES_PER_ARBITRATION:
        raise ValueError("candidate arbitration accepts at most 64 candidates")
    identities = [item.signal.signal_event_id for item in candidates]
    if len(identities) != len(set(identities)):
        raise ValueError("candidate arbitration requires unique signal identities")
    return tuple(
        sorted(
            candidates,
            key=lambda item: (
                item.owner_policy_priority,
                item.signal.occurred_at_ms,
                item.signal.observed_at_ms,
                item.signal.signal_event_id,
            ),
        )
    )
