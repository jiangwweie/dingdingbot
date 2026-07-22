"""Pure recovery decisions for durable commands with unknown venue outcomes."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.domain.commands import (
    CancelCommandPayload,
    ExchangeCommand,
    ExchangeCommandKind,
    ExchangeCommandStatus,
    OrderCommandPayload,
)


class VenueLookupStatus(StrEnum):
    VISIBLE = "visible"
    ABSENT = "absent"
    LOOKUP_FAILED = "lookup_failed"


class UnknownRecoveryStatus(StrEnum):
    PENDING_VISIBILITY = "pending_visibility"
    RECONCILED_SUBMITTED = "reconciled_submitted"
    RECONCILED_ABSENT = "reconciled_absent"
    IDENTITY_CONTRADICTION = "identity_contradiction"
    LOOKUP_FAILED = "lookup_failed"


class VenueOrderTruth(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_order_id: str
    venue_client_order_id: str
    exchange_instrument_id: str
    position_side: Literal["long", "short"]
    order_side: Literal["buy", "sell"]
    quantity: Decimal
    reduce_only: bool

    @field_validator(
        "exchange_order_id",
        "venue_client_order_id",
        "exchange_instrument_id",
        mode="before",
    )
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("venue order truth identities must be non-blank")
        return normalized

    @field_validator("quantity")
    @classmethod
    def _require_positive_quantity(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("venue order truth quantity must be positive")
        return value


class VenueTruthSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    lookup_status: VenueLookupStatus
    order: VenueOrderTruth | None = None
    position_quantity: Decimal
    matching_fill_quantity: Decimal
    regular_open_client_order_ids: tuple[str, ...]
    conditional_open_client_order_ids: tuple[str, ...]
    observed_at_ms: int
    reason: str | None = None

    @field_validator("position_quantity", "matching_fill_quantity")
    @classmethod
    def _require_nonnegative_quantity(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("venue truth quantities cannot be negative")
        return value

    @field_validator("observed_at_ms")
    @classmethod
    def _require_positive_time(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("venue truth observation time must be positive")
        return value

    @model_validator(mode="after")
    def _validate_lookup_shape(self) -> "VenueTruthSnapshot":
        if self.lookup_status is VenueLookupStatus.VISIBLE:
            if self.order is None or self.reason is not None:
                raise ValueError("visible lookup requires order truth only")
        elif self.lookup_status is VenueLookupStatus.ABSENT:
            if self.order is not None or self.reason is not None:
                raise ValueError("absent lookup forbids order and reason")
        else:
            if self.order is not None or not str(self.reason or "").strip():
                raise ValueError("failed lookup requires one reason and no order")
        return self


class UnknownRecoveryDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: UnknownRecoveryStatus
    observed_at_ms: int
    exchange_order_id: str | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def _validate_decision_shape(self) -> "UnknownRecoveryDecision":
        if self.status is UnknownRecoveryStatus.RECONCILED_SUBMITTED:
            if not str(self.exchange_order_id or "").strip() or self.reason is not None:
                raise ValueError("submitted recovery requires exchange order identity")
        else:
            if self.exchange_order_id is not None or not str(self.reason or "").strip():
                raise ValueError("non-submitted recovery requires one reason")
        return self


def decide_unknown_recovery(
    command: ExchangeCommand,
    truth: VenueTruthSnapshot,
    *,
    visibility_deadline_ms: int,
) -> UnknownRecoveryDecision:
    if command.status is not ExchangeCommandStatus.OUTCOME_UNKNOWN:
        raise ValueError("only unknown commands may enter venue-truth recovery")
    if visibility_deadline_ms <= command.created_at_ms:
        raise ValueError("visibility deadline must follow command creation")
    if truth.lookup_status is VenueLookupStatus.LOOKUP_FAILED:
        return _decision(
            UnknownRecoveryStatus.LOOKUP_FAILED,
            truth,
            reason=str(truth.reason),
        )
    if command.kind is ExchangeCommandKind.CANCEL_ORDER:
        return _decide_cancel_recovery(
            command,
            truth,
            visibility_deadline_ms=visibility_deadline_ms,
        )
    if truth.lookup_status is VenueLookupStatus.VISIBLE:
        order = truth.order
        if order is None:
            raise ValueError("visible venue truth lacks order")
        contradiction = _identity_contradiction(command, order)
        if contradiction is not None:
            return _decision(
                UnknownRecoveryStatus.IDENTITY_CONTRADICTION,
                truth,
                reason=contradiction,
            )
        return UnknownRecoveryDecision(
            status=UnknownRecoveryStatus.RECONCILED_SUBMITTED,
            observed_at_ms=truth.observed_at_ms,
            exchange_order_id=order.exchange_order_id,
        )

    submission_evidence = (
        (
            command.kind is ExchangeCommandKind.ENTRY
            and truth.position_quantity > 0
        )
        or truth.matching_fill_quantity > 0
        or command.venue_client_order_id in truth.regular_open_client_order_ids
        or command.venue_client_order_id
        in truth.conditional_open_client_order_ids
    )
    if submission_evidence:
        return _decision(
            UnknownRecoveryStatus.PENDING_VISIBILITY,
            truth,
            reason="submission_evidence_without_order_identity",
        )
    if truth.observed_at_ms < visibility_deadline_ms:
        return _decision(
            UnknownRecoveryStatus.PENDING_VISIBILITY,
            truth,
            reason="visibility_window_open",
        )
    return _decision(
        UnknownRecoveryStatus.RECONCILED_ABSENT,
        truth,
        reason="authoritative_absence_after_visibility_window",
    )


def _decide_cancel_recovery(
    command: ExchangeCommand,
    truth: VenueTruthSnapshot,
    *,
    visibility_deadline_ms: int,
) -> UnknownRecoveryDecision:
    if not isinstance(command.payload, CancelCommandPayload):
        raise ValueError("cancel recovery requires exact target order identity")
    if truth.lookup_status is VenueLookupStatus.VISIBLE:
        order = truth.order
        if order is None:
            raise ValueError("visible cancel target truth lacks order")
        domain = command.ticket_identity.netting_domain
        comparisons = (
            (
                order.exchange_order_id == command.payload.exchange_order_id,
                "cancel_target_order_id_mismatch",
            ),
            (
                order.exchange_instrument_id == domain.exchange_instrument_id,
                "instrument_mismatch",
            ),
            (order.position_side == domain.position_side, "position_side_mismatch"),
        )
        for matches, reason in comparisons:
            if not matches:
                return _decision(
                    UnknownRecoveryStatus.IDENTITY_CONTRADICTION,
                    truth,
                    reason=reason,
                )
        return _decision(
            UnknownRecoveryStatus.PENDING_VISIBILITY,
            truth,
            reason="cancel_target_still_visible",
        )
    if truth.observed_at_ms < visibility_deadline_ms:
        return _decision(
            UnknownRecoveryStatus.PENDING_VISIBILITY,
            truth,
            reason="visibility_window_open",
        )
    return _decision(
        UnknownRecoveryStatus.RECONCILED_ABSENT,
        truth,
        reason="cancel_target_absent_after_visibility_window",
    )


def _identity_contradiction(
    command: ExchangeCommand,
    order: VenueOrderTruth,
) -> str | None:
    domain = command.ticket_identity.netting_domain
    comparisons = (
        (
            order.venue_client_order_id == command.venue_client_order_id,
            "client_order_id_mismatch",
        ),
        (
            order.exchange_instrument_id == domain.exchange_instrument_id,
            "instrument_mismatch",
        ),
        (order.position_side == domain.position_side, "position_side_mismatch"),
    )
    for matches, reason in comparisons:
        if not matches:
            return reason
    if not isinstance(command.payload, OrderCommandPayload):
        return "command_kind_not_order_lookup"
    if order.order_side != command.payload.side:
        return "order_side_mismatch"
    if order.quantity != command.payload.quantity:
        return "quantity_mismatch"
    if order.reduce_only != command.payload.reduce_only:
        return "reduce_only_mismatch"
    return None


def _decision(
    status: UnknownRecoveryStatus,
    truth: VenueTruthSnapshot,
    *,
    reason: str,
) -> UnknownRecoveryDecision:
    return UnknownRecoveryDecision(
        status=status,
        observed_at_ms=truth.observed_at_ms,
        reason=reason,
    )
