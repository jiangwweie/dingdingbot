"""Settle released budget and record the terminal Ticket review."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, JsonValue

from src.trading_kernel.application.ports import (
    KernelUnitOfWork,
    TradeReviewRecord,
)
from src.trading_kernel.domain.events import BudgetSettled, ReviewRecorded
from src.trading_kernel.domain.reducer import reduce_event


class SettleTicketStatus(StrEnum):
    BUDGET_SETTLED = "budget_settled"
    REVIEW_RECORDED = "review_recorded"


class SettleTicketRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str
    settled_at_ms: int


class RecordTradeReviewRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str
    review_id: str
    outcome: str
    metrics: dict[str, JsonValue]
    decision_impact: dict[str, JsonValue]
    recorded_at_ms: int


class SettleTicketResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: SettleTicketStatus


async def settle_ticket(
    uow: KernelUnitOfWork,
    request: SettleTicketRequest,
) -> SettleTicketResult:
    aggregate = await uow.aggregates.get(request.ticket_id)
    if aggregate is None:
        raise ValueError("Ticket aggregate does not exist")
    event = BudgetSettled(
        event_id=_event_id(aggregate),
        ticket_id=request.ticket_id,
        sequence=aggregate.last_event_sequence + 1,
        occurred_at_ms=request.settled_at_ms,
    )
    await uow.commit_reduction(
        event=event,
        reduction=reduce_event(aggregate, event),
        expected_version=aggregate.version,
    )
    return SettleTicketResult(status=SettleTicketStatus.BUDGET_SETTLED)


async def record_trade_review(
    uow: KernelUnitOfWork,
    request: RecordTradeReviewRequest,
) -> SettleTicketResult:
    aggregate = await uow.aggregates.get(request.ticket_id)
    if aggregate is None:
        raise ValueError("Ticket aggregate does not exist")
    await uow.reviews.add(
        TradeReviewRecord(
            review_id=request.review_id,
            ticket_id=request.ticket_id,
            outcome=request.outcome,
            metrics=request.metrics,
            decision_impact=request.decision_impact,
            created_at_ms=request.recorded_at_ms,
        )
    )
    event = ReviewRecorded(
        event_id=_event_id(aggregate),
        ticket_id=request.ticket_id,
        sequence=aggregate.last_event_sequence + 1,
        occurred_at_ms=request.recorded_at_ms,
        review_id=request.review_id,
    )
    await uow.commit_reduction(
        event=event,
        reduction=reduce_event(aggregate, event),
        expected_version=aggregate.version,
    )
    return SettleTicketResult(status=SettleTicketStatus.REVIEW_RECORDED)


def _event_id(aggregate) -> str:
    return (
        f"event:{aggregate.identity.ticket_id}:"
        f"{aggregate.last_event_sequence + 1}"
    )
