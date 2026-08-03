"""Select one fresh entry candidate through deterministic arbitration."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator

from src.trading_kernel.application.ports import KernelUnitOfWork
from src.trading_kernel.domain.arbitration import EntryCandidate, rank_candidates

_CANDIDATE_BATCH_LIMIT = 64


class SelectEntryCandidateStatus(StrEnum):
    SELECTED = "selected"
    NO_CANDIDATE = "no_candidate"


class SelectEntryCandidateRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    now_ms: int

    @field_validator("now_ms")
    @classmethod
    def _require_positive_time(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("candidate selection time must be positive")
        return value


class SelectEntryCandidateResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: SelectEntryCandidateStatus
    candidate: EntryCandidate | None


async def select_entry_candidate(
    uow: KernelUnitOfWork,
    request: SelectEntryCandidateRequest,
) -> SelectEntryCandidateResult:
    for _ in range(_CANDIDATE_BATCH_LIMIT):
        stale = await uow.signals.get_next_stale_ready(now_ms=request.now_ms)
        if stale is None:
            break
        await uow.signals.save_readiness(
            runtime_scope_id=stale.runtime_scope_id,
            readiness_state="blocked",
            first_blocker="signal_invalid_or_stale",
            signal_event_id=stale.signal_event_id,
            fact_summary={
                "fact_count": len(stale.facts),
                "fact_digest": stale.fact_digest,
            },
            updated_at_ms=request.now_ms,
        )
    candidates = await uow.signals.list_ready_candidates(
        now_ms=request.now_ms,
        limit=_CANDIDATE_BATCH_LIMIT,
    )
    ranked = rank_candidates(candidates)
    if not ranked:
        return SelectEntryCandidateResult(
            status=SelectEntryCandidateStatus.NO_CANDIDATE,
            candidate=None,
        )
    return SelectEntryCandidateResult(
        status=SelectEntryCandidateStatus.SELECTED,
        candidate=ranked[0],
    )
