"""Immutable lifecycle facts accepted by the trading kernel reducer."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator

from src.trading_kernel.domain.ticket import TradeTicket


class _Event(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str
    sequence: int
    occurred_at_ms: int

    @field_validator("event_id", mode="before")
    @classmethod
    def _require_event_id(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("event_id must be non-blank")
        return normalized

    @field_validator("sequence", "occurred_at_ms")
    @classmethod
    def _require_positive_integer(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("event sequence and time must be positive")
        return value


class _TicketEvent(_Event):
    ticket_id: str

    @field_validator("ticket_id", mode="before")
    @classmethod
    def _require_ticket_id(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("ticket_id must be non-blank")
        return normalized


class TicketIssued(_Event):
    ticket: TradeTicket


class EntryRejected(_TicketEvent):
    reason: str


class EntryAccepted(_TicketEvent):
    exchange_order_id: str


class EntryOutcomeUnknown(_TicketEvent):
    reason: str


class EntryFilled(_TicketEvent):
    filled_qty: Decimal
    average_fill_price: Decimal


class EntryPartiallyFilled(_TicketEvent):
    filled_qty: Decimal
    requested_qty: Decimal
    average_fill_price: Decimal


class InitialStopConfirmed(_TicketEvent):
    exchange_order_id: str
    protected_qty: Decimal


class ExitRequested(_TicketEvent):
    reason: str


class ExitAccepted(_TicketEvent):
    exchange_order_id: str


class ExitOutcomeUnknown(_TicketEvent):
    reason: str


class PositionFlatConfirmed(_TicketEvent):
    pass


class ExternalFlatDetected(_TicketEvent):
    pass


class OwnedOrphanOrderDetected(_TicketEvent):
    exchange_order_id: str


class UnownedOrderDetected(_TicketEvent):
    exchange_order_id: str


class ProtectionCancelConfirmed(_TicketEvent):
    exchange_order_id: str


class OwnedOrphanCancelConfirmed(_TicketEvent):
    exchange_order_id: str


class ReconciliationMatched(_TicketEvent):
    pass


class BudgetSettled(_TicketEvent):
    pass


class ReviewRecorded(_TicketEvent):
    review_id: str


TradeEvent = (
    TicketIssued
    | EntryAccepted
    | EntryRejected
    | EntryOutcomeUnknown
    | EntryFilled
    | EntryPartiallyFilled
    | InitialStopConfirmed
    | ExitRequested
    | ExitAccepted
    | ExitOutcomeUnknown
    | PositionFlatConfirmed
    | ExternalFlatDetected
    | OwnedOrphanOrderDetected
    | UnownedOrderDetected
    | ProtectionCancelConfirmed
    | OwnedOrphanCancelConfirmed
    | ReconciliationMatched
    | BudgetSettled
    | ReviewRecorded
)
