"""Immutable lifecycle facts accepted by the trading kernel reducer."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.domain.cross_margin_stress import (
    CrossMarginStressEvidence,
    CrossMarginStressStatus,
)
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
    venue_reported_liquidation_price: Decimal | None
    position_observed_at_ms: int


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


class EntryVacuumSuperseded(_TicketEvent):
    entry_vacuum_id: str
    command_id: str
    reason: Literal["selection_entry_vacuum"] = "selection_entry_vacuum"

    @model_validator(mode="after")
    def _validate_vacuum_supersession(self) -> EntryVacuumSuperseded:
        if not self.entry_vacuum_id.strip() or not self.command_id.strip():
            raise ValueError("Vacuum supersession requires exact identities")
        return self


class EntryVacuumCancelRequested(_TicketEvent):
    entry_vacuum_id: str
    exchange_order_id: str
    observed_qty: Decimal
    average_fill_price: Decimal | None

    @model_validator(mode="after")
    def _validate_vacuum_cancel(self) -> EntryVacuumCancelRequested:
        if not self.entry_vacuum_id.strip() or not self.exchange_order_id.strip():
            raise ValueError("Vacuum ENTRY cancel requires exact identities")
        if self.observed_qty < 0:
            raise ValueError("Vacuum ENTRY observed quantity cannot be negative")
        if (self.observed_qty == 0) != (self.average_fill_price is None):
            raise ValueError("Vacuum ENTRY fill price must match observed exposure")
        if self.average_fill_price is not None and self.average_fill_price <= 0:
            raise ValueError("Vacuum ENTRY fill price must be positive")
        return self


class EntryVacuumCancelConfirmed(_TicketEvent):
    exchange_order_id: str


class EntryVacuumCancelRejected(_TicketEvent):
    exchange_order_id: str
    reason: str


class EntryVacuumCancelOutcomeUnknown(_TicketEvent):
    exchange_order_id: str
    reason: str


class EntryVacuumOrderAbsenceConfirmed(_TicketEvent):
    entry_vacuum_id: str
    exchange_order_id: str
    final_filled_qty: Decimal
    average_fill_price: Decimal | None

    @model_validator(mode="after")
    def _validate_order_absence(self) -> EntryVacuumOrderAbsenceConfirmed:
        if not self.entry_vacuum_id.strip() or not self.exchange_order_id.strip():
            raise ValueError("Vacuum order absence requires exact identities")
        if self.final_filled_qty < 0:
            raise ValueError("Vacuum final filled quantity cannot be negative")
        if (self.final_filled_qty == 0) != (self.average_fill_price is None):
            raise ValueError("Vacuum final fill price must match final quantity")
        if self.average_fill_price is not None and self.average_fill_price <= 0:
            raise ValueError("Vacuum final fill price must be positive")
        return self


class EntryVacuumAbsenceConfirmed(_TicketEvent):
    entry_vacuum_id: str


class VacuumPartialRetained(_TicketEvent):
    entry_vacuum_id: str
    selection_authority_id: str | None
    requested_qty: Decimal
    final_filled_qty: Decimal
    average_fill_price: Decimal
    quantity_step: Decimal
    effective_tp1_qty: Decimal
    effective_runner_qty: Decimal
    materialization_kind: Literal["VACUUM_PARTIAL_RETAINED"] = (
        "VACUUM_PARTIAL_RETAINED"
    )
    post_fill_risk: PostFillRiskDecision

    @model_validator(mode="after")
    def _validate_retained_materialization(self) -> VacuumPartialRetained:
        if not self.entry_vacuum_id.strip():
            raise ValueError("retained partial requires Vacuum identity")
        if self.selection_authority_id is not None and not self.selection_authority_id.strip():
            raise ValueError("retained partial Authority identity cannot be blank")
        if min(
            self.requested_qty,
            self.final_filled_qty,
            self.average_fill_price,
            self.quantity_step,
            self.effective_tp1_qty,
            self.effective_runner_qty,
        ) <= 0:
            raise ValueError("retained partial quantities and price must be positive")
        if not self.final_filled_qty < self.requested_qty:
            raise ValueError("retained partial must be smaller than requested quantity")
        if self.final_filled_qty % self.quantity_step != 0:
            raise ValueError("retained partial must align to certified quantity step")
        if self.effective_tp1_qty + self.effective_runner_qty != self.final_filled_qty:
            raise ValueError("retained partial TP1 and runner must conserve quantity")
        if self.post_fill_risk.actual_stop_risk < 0:
            raise ValueError("retained partial stop risk cannot be negative")
        return self


class VacuumPartialFlattenRequired(_TicketEvent):
    entry_vacuum_id: str
    final_filled_qty: Decimal
    average_fill_price: Decimal
    reason: str

    @model_validator(mode="after")
    def _validate_flatten(self) -> VacuumPartialFlattenRequired:
        if (
            not self.entry_vacuum_id.strip()
            or not self.reason.strip()
            or self.final_filled_qty <= 0
            or self.average_fill_price <= 0
        ):
            raise ValueError("Vacuum partial flatten requires exact positive facts")
        return self


class InitialStopConfirmed(_TicketEvent):
    exchange_order_id: str
    protected_qty: Decimal


class PostFillStressAssessed(_TicketEvent):
    status: Literal["passed", "failed"]
    evidence: CrossMarginStressEvidence
    owner_policy_id: str
    owner_policy_version: int
    filled_qty: Decimal
    average_fill_price: Decimal
    initial_stop_price: Decimal
    initial_stop_exchange_order_id: str

    @model_validator(mode="after")
    def _validate_assessment_identity(self) -> PostFillStressAssessed:
        expected = (
            CrossMarginStressStatus.PASSED
            if self.status == "passed"
            else CrossMarginStressStatus.FAILED
        )
        if self.evidence.proof.status is not expected:
            raise ValueError("post-fill stress status differs from its evidence")
        if (
            self.owner_policy_version <= 0
            or self.filled_qty <= 0
            or self.average_fill_price <= 0
            or self.initial_stop_price <= 0
        ):
            raise ValueError("post-fill stress identities must be positive")
        if not self.owner_policy_id.strip():
            raise ValueError("post-fill stress policy identity must be non-blank")
        if not self.initial_stop_exchange_order_id.strip():
            raise ValueError("post-fill stress Stop identity must be non-blank")
        return self


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
    order_namespace: Literal["regular", "conditional"]


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


class CancelOrderStillOpenConfirmed(_TicketEvent):
    exchange_order_id: str


class ReconciliationMatched(_TicketEvent):
    resolved_incident_kind: str | None = None


class BudgetSettled(_TicketEvent):
    pass


class ReviewRecorded(_TicketEvent):
    review_id: str


class ReviewRevised(_TicketEvent):
    review_id: str
    supersedes_review_id: str


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
    | EntryVacuumSuperseded
    | EntryVacuumCancelRequested
    | EntryVacuumCancelConfirmed
    | EntryVacuumCancelRejected
    | EntryVacuumCancelOutcomeUnknown
    | EntryVacuumOrderAbsenceConfirmed
    | EntryVacuumAbsenceConfirmed
    | VacuumPartialRetained
    | VacuumPartialFlattenRequired
    | InitialStopConfirmed
    | PostFillStressAssessed
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
    | CancelOrderStillOpenConfirmed
    | ReconciliationMatched
    | BudgetSettled
    | ReviewRecorded
    | ReviewRevised
)

PERSISTED_TRADE_EVENT_MODELS = get_args(TradeEvent)
