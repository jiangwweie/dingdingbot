"""Exact, read-only attribution of a late fill to one frozen ENTRY Command."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, model_validator

from src.trading_kernel.domain.commands import (
    ExchangeCommand,
    ExchangeCommandKind,
    ExchangeCommandStatus,
    OrderCommandPayload,
)
from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.domain.ticket import TradeTicket
from src.trading_kernel.domain.venue_truth import VenueLookupStatus, VenueTruthSnapshot


class VacuumLateFillAttributionStatus(StrEnum):
    ATTRIBUTED = "attributed"
    NO_FILL_VERIFIED = "no_fill_verified"
    UNVERIFIED = "unverified"


class VacuumLateFillAttributionInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket: TradeTicket
    entry_command: ExchangeCommand
    entry_exchange_order_id: str
    position: PositionSnapshot
    venue_truth: VenueTruthSnapshot
    contradiction_observed_at_ms: int

    @model_validator(mode="after")
    def _validate_source_identity(self) -> VacuumLateFillAttributionInput:
        if not self.entry_exchange_order_id.strip():
            raise ValueError("late fill attribution requires original ENTRY order identity")
        if self.contradiction_observed_at_ms <= 0:
            raise ValueError("late fill attribution requires positive contradiction time")
        return self


class VacuumLateFillAttributionDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: VacuumLateFillAttributionStatus
    reason_code: str
    proof_digest: str | None = None
    filled_qty: Decimal | None = None
    average_fill_price: Decimal | None = None

    @model_validator(mode="after")
    def _validate_decision(self) -> VacuumLateFillAttributionDecision:
        attributed = self.status is VacuumLateFillAttributionStatus.ATTRIBUTED
        no_fill = self.status is VacuumLateFillAttributionStatus.NO_FILL_VERIFIED
        if attributed and not all(value is not None for value in (
            self.proof_digest, self.filled_qty, self.average_fill_price,
        )):
            raise ValueError("late fill attribution decision has incomplete proof")
        if no_fill and (
            self.proof_digest is None
            or self.filled_qty is not None
            or self.average_fill_price is not None
        ):
            raise ValueError("no-fill decision requires only exact proof")
        if not attributed and not no_fill and any(value is not None for value in (
            self.proof_digest, self.filled_qty, self.average_fill_price,
        )):
            raise ValueError("unverified decision cannot carry proof")
        return self


def decide_vacuum_late_fill_attribution(
    facts: VacuumLateFillAttributionInput,
) -> VacuumLateFillAttributionDecision:
    """Only exact closed-order fills can rejoin the existing Ticket lifecycle."""

    ticket = facts.ticket
    command = facts.entry_command
    position = facts.position
    truth = facts.venue_truth
    domain = ticket.identity.netting_domain
    if command.ticket_identity != ticket.identity or command.kind is not ExchangeCommandKind.ENTRY:
        return _unverified("entry_command_identity_mismatch")
    if command.status not in {
        ExchangeCommandStatus.ACCEPTED,
        ExchangeCommandStatus.RECONCILED_ACCEPTED,
    }:
        return _unverified("entry_command_not_authoritatively_accepted")
    payload = command.payload
    if not isinstance(payload, OrderCommandPayload) or command.venue_client_order_id is None:
        return _unverified("entry_command_payload_invalid")
    if payload.quantity != ticket.quantity or payload.reduce_only:
        return _unverified("entry_command_quantity_or_side_invalid")
    if position.netting_domain != domain:
        return _unverified("position_netting_domain_mismatch")
    if position.quantity < 0 or position.quantity > ticket.quantity:
        return _unverified("position_quantity_outside_ticket")
    if position.open_orders:
        return _unverified("position_has_residual_order")
    if position.observed_at_ms <= facts.contradiction_observed_at_ms:
        return _unverified("position_observation_not_newer")
    if truth.lookup_status is not VenueLookupStatus.VISIBLE or truth.order is None:
        return _unverified("entry_order_not_exactly_visible")
    order = truth.order
    if (
        order.exchange_order_id != facts.entry_exchange_order_id
        or order.venue_client_order_id != command.venue_client_order_id
        or order.exchange_instrument_id != domain.exchange_instrument_id
        or order.position_side != domain.position_side
        or order.order_side != payload.side
        or order.quantity != payload.quantity
        or order.reduce_only
        or order.order_namespace != "regular"
    ):
        return _unverified("entry_order_identity_mismatch")
    if order.is_open or command.venue_client_order_id in {
        *truth.regular_open_client_order_ids,
        *truth.conditional_open_client_order_ids,
    }:
        return _unverified("entry_order_still_open")
    if (
        truth.observed_at_ms < position.observed_at_ms
        or truth.position_quantity != position.quantity
        or truth.matching_fill_quantity != position.quantity
        or not truth.matching_fill_complete
    ):
        return _unverified("entry_fill_or_position_truth_mismatch")

    if position.quantity == 0:
        if truth.matching_fill_average_price is not None:
            return _unverified("zero_fill_price_contradiction")
        return VacuumLateFillAttributionDecision(
            status=VacuumLateFillAttributionStatus.NO_FILL_VERIFIED,
            reason_code="exact_closed_entry_no_fill",
            proof_digest=vacuum_no_fill_proof_digest(
                ticket_id=ticket.identity.ticket_id,
                entry_command_id=command.command_id,
                exchange_order_id=order.exchange_order_id,
                venue_client_order_id=order.venue_client_order_id,
                netting_domain_key=domain.key(),
                position_observed_at_ms=position.observed_at_ms,
                venue_observed_at_ms=truth.observed_at_ms,
            ),
        )
    assert position.average_entry_price is not None
    if truth.matching_fill_average_price != position.average_entry_price:
        return _unverified("entry_fill_price_mismatch")
    proof_digest = vacuum_late_fill_proof_digest(
        ticket_id=ticket.identity.ticket_id,
        entry_command_id=command.command_id,
        exchange_order_id=order.exchange_order_id,
        venue_client_order_id=order.venue_client_order_id,
        netting_domain_key=domain.key(),
        filled_qty=position.quantity,
        average_fill_price=position.average_entry_price,
        position_observed_at_ms=position.observed_at_ms,
        venue_observed_at_ms=truth.observed_at_ms,
    )
    return VacuumLateFillAttributionDecision(
        status=VacuumLateFillAttributionStatus.ATTRIBUTED,
        reason_code="exact_closed_entry_fill",
        proof_digest=proof_digest,
        filled_qty=position.quantity,
        average_fill_price=position.average_entry_price,
    )


def _unverified(reason_code: str) -> VacuumLateFillAttributionDecision:
    return VacuumLateFillAttributionDecision(
        status=VacuumLateFillAttributionStatus.UNVERIFIED,
        reason_code=reason_code,
    )


def vacuum_late_fill_proof_digest(
    *,
    ticket_id: str,
    entry_command_id: str,
    exchange_order_id: str,
    venue_client_order_id: str,
    netting_domain_key: str,
    filled_qty: Decimal,
    average_fill_price: Decimal,
    position_observed_at_ms: int,
    venue_observed_at_ms: int,
) -> str:
    return _proof_digest({
        "ticket_id": ticket_id,
        "entry_command_id": entry_command_id,
        "exchange_order_id": exchange_order_id,
        "venue_client_order_id": venue_client_order_id,
        "netting_domain_key": netting_domain_key,
        "filled_qty": filled_qty,
        "average_fill_price": average_fill_price,
        "position_observed_at_ms": position_observed_at_ms,
        "venue_observed_at_ms": venue_observed_at_ms,
    })


def vacuum_no_fill_proof_digest(
    *,
    ticket_id: str,
    entry_command_id: str,
    exchange_order_id: str,
    venue_client_order_id: str,
    netting_domain_key: str,
    position_observed_at_ms: int,
    venue_observed_at_ms: int,
) -> str:
    return _proof_digest({
        "ticket_id": ticket_id,
        "entry_command_id": entry_command_id,
        "exchange_order_id": exchange_order_id,
        "venue_client_order_id": venue_client_order_id,
        "netting_domain_key": netting_domain_key,
        "filled_qty": Decimal(0),
        "position_observed_at_ms": position_observed_at_ms,
        "venue_observed_at_ms": venue_observed_at_ms,
    })


def _proof_digest(payload: dict[str, object]) -> str:
    normalized: dict[str, object] = {}
    for key, value in payload.items():
        if isinstance(value, Decimal):
            rendered = "0" if value == 0 else format(value, "f")
            normalized[key] = rendered.rstrip("0").rstrip(".") if "." in rendered else rendered
        else:
            normalized[key] = value
    return canonical_digest(normalized)
