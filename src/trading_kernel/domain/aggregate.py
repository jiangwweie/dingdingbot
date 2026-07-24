"""Current lifecycle projection for one immutable Trade Ticket."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from src.trading_kernel.domain.identities import TicketIdentity
from src.trading_kernel.domain.post_fill_risk import (
    PostFillDisposition,
    PostFillRiskStatus,
)
from src.trading_kernel.domain.ticket import TradeTicket


class AggregateStatus(StrEnum):
    LEVERAGE_PENDING = "leverage_pending"
    LEVERAGE_CONFIRMED = "leverage_confirmed"
    LEVERAGE_REJECTED = "leverage_rejected"
    LEVERAGE_OUTCOME_UNKNOWN = "leverage_outcome_unknown"
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
    TP1_PENDING = "tp1_pending"
    TP1_REJECTED = "tp1_rejected"
    TP1_OUTCOME_UNKNOWN = "tp1_outcome_unknown"
    POSITION_PROTECTED = "position_protected"
    RUNNER_REPLACEMENT_PENDING = "runner_replacement_pending"
    RUNNER_REPLACEMENT_REJECTED = "runner_replacement_rejected"
    RUNNER_REPLACEMENT_OUTCOME_UNKNOWN = "runner_replacement_outcome_unknown"
    RUNNER_OLD_STOP_CANCEL_PENDING = "runner_old_stop_cancel_pending"
    RUNNER_OLD_STOP_CANCEL_REJECTED = "runner_old_stop_cancel_rejected"
    RUNNER_OLD_STOP_CANCEL_OUTCOME_UNKNOWN = (
        "runner_old_stop_cancel_outcome_unknown"
    )
    RUNNER_PROTECTED = "runner_protected"
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
    actual_stop_risk: Decimal | None = None
    actual_liquidation_price: Decimal | None = None
    actual_liquidation_distance: Decimal | None = None
    actual_liquidation_distance_to_stop_distance_ratio: Decimal | None = None
    post_fill_risk_status: PostFillRiskStatus | None = None
    post_fill_disposition: PostFillDisposition | None = None
    protected_qty: Decimal = Decimal("0")
    entry_exchange_order_id: str | None = None
    initial_stop_exchange_order_id: str | None = None
    active_stop_exchange_order_id: str | None = None
    active_stop_price: Decimal | None = None
    tp1_exchange_order_id: str | None = None
    tp1_target_qty: Decimal = Decimal("0")
    tp1_filled_qty: Decimal = Decimal("0")
    break_even_floor_price: Decimal | None = None
    pending_replaced_stop_exchange_order_id: str | None = None
    pending_stop_price: Decimal | None = None
    pending_stop_watermark_ms: int | None = None
    runner_stop_watermark_ms: int | None = None
    pending_cancel_exchange_order_id: str | None = None
    exit_exchange_order_id: str | None = None
    review_id: str | None = None
