"""Append one exact semantic classification to a terminal SOR v2 Review."""

from __future__ import annotations

from enum import StrEnum
from hashlib import sha256

from pydantic import BaseModel, ConfigDict, field_validator

from src.trading_kernel.application.ports import KernelUnitOfWork
from src.trading_kernel.application.settle_ticket import (
    ReviseTradeReviewRequest,
    revise_trade_review,
)
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.review import (
    SorV2HistoryClassification,
    sor_v2_history_decision_impact,
)
from src.trading_kernel.domain.ticket import TicketStatus

_SOR_V2_EVENT_SPEC_IDS = {
    "event_spec:SOR-001:SOR-LONG:v2",
    "event_spec:SOR-001:SOR-SHORT:v2",
}
_CLASSIFICATION_KEYS = {
    "entry_semantics",
    "evidence_scope",
    "entry_alpha_inclusion",
    "execution_evidence",
    "lifecycle_evidence",
    "economics_evidence",
}


class ClassifySorV2HistoryStatus(StrEnum):
    REVISED = "revised"
    ALREADY_CLASSIFIED = "already_classified"


class ClassifySorV2HistoryRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str
    classification: SorV2HistoryClassification
    classified_at_ms: int

    @field_validator("ticket_id", mode="before")
    @classmethod
    def _require_ticket_id(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("SOR v2 classification requires exact Ticket identity")
        return normalized

    @field_validator("classified_at_ms")
    @classmethod
    def _require_positive_time(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("SOR v2 classification time must be positive")
        return value


class ClassifySorV2HistoryResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ClassifySorV2HistoryStatus
    ticket_id: str
    review_id: str
    revision: int


async def classify_sor_v2_history(
    uow: KernelUnitOfWork,
    request: ClassifySorV2HistoryRequest,
) -> ClassifySorV2HistoryResult:
    aggregate = await uow.aggregates.get_for_update(request.ticket_id)
    if aggregate is None:
        raise ValueError("SOR v2 classification Ticket aggregate does not exist")
    runtime = aggregate.ticket.identity.runtime
    if (
        runtime.strategy_group_id != "SOR-001"
        or runtime.strategy_version_id != "sgv:SOR-001:v2"
        or runtime.event_spec_id not in _SOR_V2_EVENT_SPEC_IDS
    ):
        raise ValueError("history classification accepts only exact SOR v2 Tickets")
    if (
        aggregate.status is not AggregateStatus.TERMINAL
        or aggregate.ticket.status is not TicketStatus.TERMINAL
    ):
        raise ValueError("SOR v2 history classification requires terminal Ticket")
    if aggregate.review_id is None:
        raise ValueError("SOR v2 history classification requires current Review")
    current = await uow.reviews.get(aggregate.review_id)
    if current is None or current.ticket_id != request.ticket_id:
        raise ValueError("SOR v2 current Review identity is inconsistent")

    classification_impact = sor_v2_history_decision_impact(
        request.classification
    )
    if all(
        current.decision_impact.get(key) == value
        for key, value in classification_impact.items()
    ):
        return ClassifySorV2HistoryResult(
            status=ClassifySorV2HistoryStatus.ALREADY_CLASSIFIED,
            ticket_id=request.ticket_id,
            review_id=current.review_id,
            revision=current.revision,
        )
    conflicting_keys = {
        key
        for key in _CLASSIFICATION_KEYS
        if key in current.decision_impact
        and not (
            key == "entry_semantics"
            and current.decision_impact[key] == "v2"
        )
    }
    if conflicting_keys:
        raise ValueError("SOR v2 Ticket already has a different classification")
    if request.classified_at_ms <= current.created_at_ms:
        raise ValueError(
            "SOR v2 classification must be later than the current Review"
        )

    decision_impact = dict(current.decision_impact)
    decision_impact.update(classification_impact)
    review_id = _review_id(
        ticket_id=request.ticket_id,
        classification=request.classification,
        supersedes_review_id=current.review_id,
    )
    await revise_trade_review(
        uow,
        ReviseTradeReviewRequest(
            ticket_id=request.ticket_id,
            review_id=review_id,
            supersedes_review_id=current.review_id,
            outcome=current.outcome,
            metrics=current.metrics,
            decision_impact=decision_impact,
            recorded_at_ms=request.classified_at_ms,
        ),
    )
    return ClassifySorV2HistoryResult(
        status=ClassifySorV2HistoryStatus.REVISED,
        ticket_id=request.ticket_id,
        review_id=review_id,
        revision=current.revision + 1,
    )


def _review_id(
    *,
    ticket_id: str,
    classification: SorV2HistoryClassification,
    supersedes_review_id: str,
) -> str:
    canonical = (
        f"{ticket_id}|{classification.value}|{supersedes_review_id}"
    ).encode()
    return f"review:sor-v2-history:{sha256(canonical).hexdigest()}"
