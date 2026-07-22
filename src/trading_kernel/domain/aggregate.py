"""Current lifecycle projection for one immutable Trade Ticket."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from src.trading_kernel.domain.identities import TicketIdentity
from src.trading_kernel.domain.ticket import TradeTicket


class AggregateStatus(StrEnum):
    ENTRY_PENDING = "entry_pending"
    ENTRY_ACCEPTED = "entry_accepted"
    ENTRY_REJECTED = "entry_rejected"
    ENTRY_OUTCOME_UNKNOWN = "entry_outcome_unknown"
    PARTIAL_FILL_INCIDENT = "partial_fill_incident"
    PROTECTION_PENDING = "protection_pending"
    POSITION_PROTECTED = "position_protected"
    EXIT_PENDING = "exit_pending"
    EXIT_ACCEPTED = "exit_accepted"
    EXIT_OUTCOME_UNKNOWN = "exit_outcome_unknown"
    RECONCILIATION_PENDING = "reconciliation_pending"
    SETTLEMENT_PENDING = "settlement_pending"
    REVIEW_PENDING = "review_pending"
    TERMINAL = "terminal"


class TradeAggregate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    identity: TicketIdentity
    ticket: TradeTicket
    status: AggregateStatus
    version: int
    last_event_sequence: int
    position_qty: Decimal = Decimal("0")
    average_fill_price: Decimal | None = None
    protected_qty: Decimal = Decimal("0")
    entry_exchange_order_id: str | None = None
    initial_stop_exchange_order_id: str | None = None
    exit_exchange_order_id: str | None = None
    review_id: str | None = None
