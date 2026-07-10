"""Durable command semantics for ticket-bound exchange writes.

The command is persisted before dispatch and resolved from authoritative
exchange truth after an ambiguous outcome.  This module is pure domain logic;
it does not perform database or exchange I/O.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from hashlib import sha256
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExchangeCommandModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExchangeCommandState(str, Enum):
    PREPARED = "prepared"
    DISPATCHING = "dispatching"
    CONFIRMED_SUBMITTED = "confirmed_submitted"
    CONFIRMED_REJECTED = "confirmed_rejected"
    OUTCOME_UNKNOWN = "outcome_unknown"
    RECONCILED_SUBMITTED = "reconciled_submitted"
    RECONCILED_ABSENT = "reconciled_absent"
    HARD_STOPPED = "hard_stopped"


class ExchangeCommandOutcomeClass(str, Enum):
    PENDING = "pending"
    EXCHANGE_ACCEPTED = "exchange_accepted"
    AUTHORITATIVE_REJECTION = "authoritative_rejection"
    NETWORK_AMBIGUOUS = "network_ambiguous"
    INCOMPLETE_RESPONSE = "incomplete_response"
    RECONCILED_EXCHANGE_TRUTH = "reconciled_exchange_truth"
    RECONCILED_ABSENCE = "reconciled_absence"
    CONTRADICTORY_TRUTH = "contradictory_truth"


class TicketBoundExchangeCommand(ExchangeCommandModel):
    exchange_command_id: str = Field(min_length=1, max_length=192)
    protected_submit_attempt_id: str = Field(min_length=1, max_length=192)
    ticket_id: str = Field(min_length=1, max_length=192)
    operation_submit_command_id: str = Field(min_length=1, max_length=192)
    account_id: str = Field(min_length=1, max_length=128)
    strategy_group_id: str = Field(min_length=1, max_length=128)
    runtime_profile_id: str = Field(min_length=1, max_length=128)
    exchange_instrument_id: str = Field(min_length=1, max_length=192)
    order_role: str = Field(pattern="^(ENTRY|SL|TP1|RUNNER_SL)$")
    side: str = Field(pattern="^(long|short)$")
    gateway_side: str = Field(min_length=1, max_length=32)
    local_order_id: str = Field(min_length=1, max_length=192)
    parent_order_id: Optional[str] = Field(default=None, max_length=192)
    client_order_id: str = Field(min_length=1, max_length=36)
    command_generation: int = Field(ge=1)
    request_fingerprint: str = Field(min_length=1, max_length=192)
    order_type: str = Field(min_length=1, max_length=64)
    amount: Decimal = Field(gt=Decimal("0"))
    price: Optional[Decimal] = Field(default=None, gt=Decimal("0"))
    stop_price: Optional[Decimal] = Field(default=None, gt=Decimal("0"))
    reduce_only: bool = False
    authority_source_ref: str = Field(min_length=1, max_length=256)
    command_state: ExchangeCommandState
    outcome_class: ExchangeCommandOutcomeClass = ExchangeCommandOutcomeClass.PENDING
    exchange_order_id: Optional[str] = Field(default=None, max_length=192)
    exchange_error_code: Optional[str] = Field(default=None, max_length=128)
    exchange_error_message: Optional[str] = Field(default=None, max_length=1000)
    prepared_at_ms: int = Field(ge=0)
    dispatch_started_at_ms: Optional[int] = Field(default=None, ge=0)
    resolved_at_ms: Optional[int] = Field(default=None, ge=0)
    updated_at_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def _validate_resolution(self) -> "TicketBoundExchangeCommand":
        submitted_states = {
            ExchangeCommandState.CONFIRMED_SUBMITTED,
            ExchangeCommandState.RECONCILED_SUBMITTED,
        }
        if self.command_state in submitted_states and not self.exchange_order_id:
            raise ValueError("submitted command requires exchange_order_id")
        if self.command_state == ExchangeCommandState.CONFIRMED_REJECTED and (
            self.outcome_class
            != ExchangeCommandOutcomeClass.AUTHORITATIVE_REJECTION
        ):
            raise ValueError(
                "confirmed rejection requires authoritative rejection"
            )
        return self


_ALLOWED_TRANSITIONS: dict[
    ExchangeCommandState,
    set[ExchangeCommandState],
] = {
    ExchangeCommandState.PREPARED: {ExchangeCommandState.DISPATCHING},
    ExchangeCommandState.DISPATCHING: {
        ExchangeCommandState.CONFIRMED_SUBMITTED,
        ExchangeCommandState.CONFIRMED_REJECTED,
        ExchangeCommandState.OUTCOME_UNKNOWN,
        ExchangeCommandState.HARD_STOPPED,
    },
    ExchangeCommandState.OUTCOME_UNKNOWN: {
        ExchangeCommandState.RECONCILED_SUBMITTED,
        ExchangeCommandState.RECONCILED_ABSENT,
        ExchangeCommandState.HARD_STOPPED,
    },
}


def command_transition_blockers(
    *,
    current: ExchangeCommandState,
    target: ExchangeCommandState,
    outcome_class: ExchangeCommandOutcomeClass,
) -> list[str]:
    """Return fail-closed blockers for a proposed command transition."""

    blockers: list[str] = []
    if target not in _ALLOWED_TRANSITIONS.get(current, set()):
        blockers.append("exchange_command_transition_not_allowed")

    required_outcomes = {
        ExchangeCommandState.CONFIRMED_SUBMITTED: {
            ExchangeCommandOutcomeClass.EXCHANGE_ACCEPTED,
        },
        ExchangeCommandState.CONFIRMED_REJECTED: {
            ExchangeCommandOutcomeClass.AUTHORITATIVE_REJECTION,
        },
        ExchangeCommandState.OUTCOME_UNKNOWN: {
            ExchangeCommandOutcomeClass.NETWORK_AMBIGUOUS,
            ExchangeCommandOutcomeClass.INCOMPLETE_RESPONSE,
        },
        ExchangeCommandState.RECONCILED_SUBMITTED: {
            ExchangeCommandOutcomeClass.RECONCILED_EXCHANGE_TRUTH,
        },
        ExchangeCommandState.RECONCILED_ABSENT: {
            ExchangeCommandOutcomeClass.RECONCILED_ABSENCE,
        },
        ExchangeCommandState.HARD_STOPPED: {
            ExchangeCommandOutcomeClass.CONTRADICTORY_TRUTH,
        },
    }
    accepted = required_outcomes.get(target)
    if accepted is not None and outcome_class not in accepted:
        if target == ExchangeCommandState.CONFIRMED_REJECTED:
            blockers.append(
                "confirmed_rejected_requires_authoritative_rejection"
            )
        else:
            blockers.append("exchange_command_outcome_class_mismatch")
    return blockers


def deterministic_client_order_id(
    ticket_id: str,
    operation_submit_command_id: str,
    order_role: str,
    command_generation: int,
) -> str:
    """Build a stable, venue-safe idempotency key of at most 36 characters."""

    if not ticket_id or not operation_submit_command_id or not order_role:
        raise ValueError("client order id identity fields must be non-empty")
    if command_generation < 1:
        raise ValueError("command_generation must be positive")
    identity = "|".join(
        (
            ticket_id,
            operation_submit_command_id,
            order_role.upper(),
            str(command_generation),
        )
    )
    return f"brc-{sha256(identity.encode('utf-8')).hexdigest()[:32]}"
