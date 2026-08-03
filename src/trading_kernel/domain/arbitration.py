"""Deterministic ordering for fresh StrategySignal candidates."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator

from src.trading_kernel.domain.admission_decision import (
    AdmissionCandidateSummary,
    CandidateSetSnapshot,
)
from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
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


def freeze_candidate_set(
    candidates: tuple[EntryCandidate, ...],
) -> CandidateSetSnapshot:
    ranked = rank_candidates(candidates)
    if not ranked:
        raise ValueError("candidate set cannot be empty")
    summary = tuple(
        AdmissionCandidateSummary(
            rank=index,
            signal_event_id=candidate.signal.signal_event_id,
            exposure_episode_id=candidate.signal.exposure_episode_id,
            strategy_group_id=candidate.signal.strategy_group_id,
            strategy_version_id=candidate.signal.strategy_version_id,
            event_spec_id=candidate.signal.event_spec_id,
            exchange_instrument_id=(
                candidate.signal.exchange_instrument_id
            ),
            position_side=candidate.signal.position_side,
            occurred_at_ms=candidate.signal.occurred_at_ms,
        )
        for index, candidate in enumerate(ranked, start=1)
    )
    return CandidateSetSnapshot(
        ranked_signal_event_ids=tuple(
            item.signal_event_id for item in summary
        ),
        candidate_count=len(summary),
        candidate_set_digest=canonical_digest(
            [item.model_dump(mode="python") for item in summary]
        ),
        candidate_set_summary=summary,
    )
