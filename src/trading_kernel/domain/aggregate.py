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
    ENTRY_RECONCILED_ABSENT = "entry_reconciled_absent"
    PARTIAL_FILL_INCIDENT = "partial_fill_incident"
    PARTIAL_FILL_CANCEL_REJECTED = "partial_fill_cancel_rejected"
    PARTIAL_FILL_CANCEL_OUTCOME_UNKNOWN = "partial_fill_cancel_outcome_unknown"
    PROTECTION_PENDING = "protection_pending"
    INITIAL_STOP_OUTCOME_UNKNOWN = "initial_stop_outcome_unknown"
    POSITION_PROTECTED = "position_protected"
    EXIT_PENDING = "exit_pending"
    EXIT_ACCEPTED = "exit_accepted"
    EXIT_REJECTED = "exit_rejected"
    EXIT_OUTCOME_UNKNOWN = "exit_outcome_unknown"
    CONTROLLED_FLATTEN_PENDING = "controlled_flatten_pending"
    CONTROLLED_FLATTEN_ACCEPTED = "controlled_flatten_accepted"
    CONTROLLED_FLATTEN_REJECTED = "controlled_flatten_rejected"
    CONTROLLED_FLATTEN_OUTCOME_UNKNOWN = "controlled_flatten_outcome_unknown"
    RECONCILIATION_PENDING = "reconciliation_pending"
    CANCEL_REJECTED = "cancel_rejected"
    CANCEL_OUTCOME_UNKNOWN = "cancel_outcome_unknown"
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
    entry_lane_held: bool = True
    position_qty: Decimal = Decimal("0")
    average_fill_price: Decimal | None = None
    protected_qty: Decimal = Decimal("0")
    entry_exchange_order_id: str | None = None
    initial_stop_exchange_order_id: str | None = None
    pending_cancel_exchange_order_id: str | None = None
    exit_exchange_order_id: str | None = None
    review_id: str | None = None
