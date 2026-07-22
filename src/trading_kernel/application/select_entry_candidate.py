"""Select one fresh entry candidate through deterministic arbitration."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator

from src.trading_kernel.application.ports import KernelUnitOfWork
from src.trading_kernel.domain.arbitration import EntryCandidate, rank_candidates


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
    candidates = await uow.signals.list_ready_candidates(
        now_ms=request.now_ms,
        limit=64,
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
