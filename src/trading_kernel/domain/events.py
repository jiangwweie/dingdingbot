"""Immutable lifecycle facts accepted by the trading kernel reducer."""

from __future__ import annotations

from decimal import Decimal
import re

from pydantic import BaseModel, ConfigDict, field_validator

from src.trading_kernel.domain.post_fill_risk import PostFillRiskDecision
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


_SHA256_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class LeverageConfirmed(_TicketEvent):
    exchange_configured_leverage: int
    leverage_verified_at_ms: int
    leverage_verification_digest: str

    @field_validator(
        "exchange_configured_leverage",
        "leverage_verified_at_ms",
        mode="before",
    )
    @classmethod
    def _require_positive_integer(cls, value: object) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("leverage confirmation integers must be positive")
        return value

    @field_validator("leverage_verification_digest")
    @classmethod
    def _require_verification_digest(cls, value: str) -> str:
        if _SHA256_DIGEST.fullmatch(value) is None:
            raise ValueError("leverage confirmation requires a sha256 digest")
        return value


class LeverageRejected(_TicketEvent):
    reason: str

    @field_validator("reason", mode="before")
    @classmethod
    def _require_reason(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("leverage rejection requires reason")
        return normalized


class LeverageOutcomeUnknown(_TicketEvent):
    reason: str

    @field_validator("reason", mode="before")
    @classmethod
    def _require_reason(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("unknown leverage outcome requires reason")
        return normalized


class EntryRejected(_TicketEvent):
    reason: str


class EntryAccepted(_TicketEvent):
    exchange_order_id: str


class EntryOutcomeUnknown(_TicketEvent):
    reason: str


class EntryAbsenceConfirmed(_TicketEvent):
    command_id: str


class EntryFilled(_TicketEvent):
    filled_qty: Decimal
    average_fill_price: Decimal
    post_fill_risk: PostFillRiskDecision


class EntryPartiallyFilled(_TicketEvent):
    filled_qty: Decimal
    requested_qty: Decimal
    average_fill_price: Decimal


class EntryRemainderCancelConfirmed(_TicketEvent):
    exchange_order_id: str


class EntryRemainderCancelRejected(_TicketEvent):
    exchange_order_id: str
    reason: str


class EntryRemainderCancelOutcomeUnknown(_TicketEvent):
    exchange_order_id: str
    reason: str


class InitialStopConfirmed(_TicketEvent):
    exchange_order_id: str
    protected_qty: Decimal


class InitialStopRejected(_TicketEvent):
    reason: str


class InitialStopOutcomeUnknown(_TicketEvent):
    reason: str


class InitialStopAbsenceConfirmed(_TicketEvent):
    command_id: str


class TakeProfitConfirmed(_TicketEvent):
    exchange_order_id: str
    target_qty: Decimal


class TakeProfitRejected(_TicketEvent):
    reason: str


class TakeProfitOutcomeUnknown(_TicketEvent):
    reason: str


class TakeProfitAbsenceConfirmed(_TicketEvent):
    command_id: str


class TakeProfitFilled(_TicketEvent):
    filled_qty: Decimal
    average_fill_price: Decimal
    runner_floor_price: Decimal


class RunnerStopRequested(_TicketEvent):
    stop_price: Decimal
    source_watermark_ms: int


class ProtectionReplacementConfirmed(_TicketEvent):
    exchange_order_id: str
    protected_qty: Decimal
    stop_price: Decimal
    replaces_exchange_order_id: str
    source_watermark_ms: int


class ProtectionReplacementRejected(_TicketEvent):
    reason: str


class ProtectionReplacementOutcomeUnknown(_TicketEvent):
    reason: str


class ProtectionReplacementAbsenceConfirmed(_TicketEvent):
    command_id: str


class ExitRequested(_TicketEvent):
    reason: str


class ExitAccepted(_TicketEvent):
    exchange_order_id: str


class ExitRejected(_TicketEvent):
    reason: str


class ExitOutcomeUnknown(_TicketEvent):
    reason: str


class ExitAbsenceConfirmed(_TicketEvent):
    command_id: str


class ControlledFlattenAccepted(_TicketEvent):
    exchange_order_id: str


class ControlledFlattenRejected(_TicketEvent):
    reason: str


class ControlledFlattenOutcomeUnknown(_TicketEvent):
    reason: str


class ControlledFlattenAbsenceConfirmed(_TicketEvent):
    command_id: str


class PositionFlatConfirmed(_TicketEvent):
    pass


class ExternalFlatDetected(_TicketEvent):
    pass


class OwnedOrphanOrderDetected(_TicketEvent):
    exchange_order_id: str


class OwnedOrderAbsenceConfirmed(_TicketEvent):
    exchange_order_id: str


class UnownedOrderDetected(_TicketEvent):
    exchange_order_id: str


class ProtectionCancelConfirmed(_TicketEvent):
    exchange_order_id: str


class ProtectionCancelRejected(_TicketEvent):
    exchange_order_id: str
    reason: str


class ProtectionCancelOutcomeUnknown(_TicketEvent):
    exchange_order_id: str
    reason: str


class ProtectionCancelAbsenceConfirmed(_TicketEvent):
    exchange_order_id: str


class OwnedOrphanCancelConfirmed(_TicketEvent):
    exchange_order_id: str


class CancelOrderRejected(_TicketEvent):
    exchange_order_id: str
    reason: str


class CancelOrderOutcomeUnknown(_TicketEvent):
    exchange_order_id: str
    reason: str


class CancelOrderAbsenceConfirmed(_TicketEvent):
    exchange_order_id: str


class ReconciliationMatched(_TicketEvent):
    resolved_incident_kind: str | None = None


class BudgetSettled(_TicketEvent):
    pass


class ReviewRecorded(_TicketEvent):
    review_id: str


TradeEvent = (
    TicketIssued
    | LeverageConfirmed
    | LeverageRejected
    | LeverageOutcomeUnknown
    | EntryAccepted
    | EntryRejected
    | EntryOutcomeUnknown
    | EntryAbsenceConfirmed
    | EntryFilled
    | EntryPartiallyFilled
    | EntryRemainderCancelConfirmed
    | EntryRemainderCancelRejected
    | EntryRemainderCancelOutcomeUnknown
    | InitialStopConfirmed
    | InitialStopRejected
    | InitialStopOutcomeUnknown
    | InitialStopAbsenceConfirmed
    | TakeProfitConfirmed
    | TakeProfitRejected
    | TakeProfitOutcomeUnknown
    | TakeProfitAbsenceConfirmed
    | TakeProfitFilled
    | RunnerStopRequested
    | ProtectionReplacementConfirmed
    | ProtectionReplacementRejected
    | ProtectionReplacementOutcomeUnknown
    | ProtectionReplacementAbsenceConfirmed
    | ExitRequested
    | ExitAccepted
    | ExitRejected
    | ExitOutcomeUnknown
    | ExitAbsenceConfirmed
    | ControlledFlattenAccepted
    | ControlledFlattenRejected
    | ControlledFlattenOutcomeUnknown
    | ControlledFlattenAbsenceConfirmed
    | PositionFlatConfirmed
    | ExternalFlatDetected
    | OwnedOrphanOrderDetected
    | OwnedOrderAbsenceConfirmed
    | UnownedOrderDetected
    | ProtectionCancelConfirmed
    | ProtectionCancelRejected
    | ProtectionCancelOutcomeUnknown
    | ProtectionCancelAbsenceConfirmed
    | OwnedOrphanCancelConfirmed
    | CancelOrderRejected
    | CancelOrderOutcomeUnknown
    | CancelOrderAbsenceConfirmed
    | ReconciliationMatched
    | BudgetSettled
    | ReviewRecorded
)
