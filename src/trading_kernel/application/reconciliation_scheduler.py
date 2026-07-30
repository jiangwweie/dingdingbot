"""Pure lane scheduling for one reconciliation process cadence."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class ReconciliationActionKind(StrEnum):
    UNKNOWN_OUTCOME = "unknown_outcome"
    POST_FILL_RISK = "post_fill_risk"
    POSITION_SAFETY = "position_safety"
    SETTLEMENT = "settlement"
    REVIEW = "review"
    CERTIFICATION = "certification"
    FEE_MONITOR = "fee_monitor"


class ReconciliationActionCandidate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: ReconciliationActionKind
    stable_identity: str
    due_at_ms: int
    max_wait_ms: int

    @field_validator("stable_identity", mode="before")
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("reconciliation action identity must be non-blank")
        return normalized

    @model_validator(mode="after")
    def _validate_window(self) -> ReconciliationActionCandidate:
        if self.due_at_ms < 0 or self.max_wait_ms < 0:
            raise ValueError("reconciliation action times must be non-negative")
        return self

    @property
    def deadline_at_ms(self) -> int:
        return self.due_at_ms + self.max_wait_ms


class ReconciliationScheduleInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    now_ms: int
    safety_action: ReconciliationActionCandidate | None = None
    housekeeping_candidates: tuple[ReconciliationActionCandidate, ...] = ()

    @field_validator("now_ms")
    @classmethod
    def _require_now(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("reconciliation schedule time must be positive")
        return value


class ReconciliationScheduleResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    safety_action: ReconciliationActionCandidate | None
    housekeeping_action: ReconciliationActionCandidate | None
    started_at_ms: int
    completed_at_ms: int
    next_due_at_ms: int | None
    deadline_breach: bool


def select_reconciliation_schedule(
    schedule: ReconciliationScheduleInput,
) -> ReconciliationScheduleResult:
    """Select one due housekeeping action by deadline and stable identity."""

    due = tuple(
        candidate
        for candidate in schedule.housekeeping_candidates
        if candidate.due_at_ms <= schedule.now_ms
    )
    selected = min(
        due,
        key=lambda candidate: (
            candidate.deadline_at_ms,
            candidate.stable_identity,
            candidate.kind.value,
        ),
        default=None,
    )
    remaining = tuple(
        candidate
        for candidate in schedule.housekeeping_candidates
        if candidate is not selected
    )

    return ReconciliationScheduleResult(
        safety_action=schedule.safety_action,
        housekeeping_action=selected,
        started_at_ms=schedule.now_ms,
        completed_at_ms=schedule.now_ms,
        next_due_at_ms=(
            None
            if not remaining
            else min(candidate.due_at_ms for candidate in remaining)
        ),
        deadline_breach=(
            selected is not None
            and selected.deadline_at_ms < schedule.now_ms
        ),
    )
