"""Durable exactly-once command identity for all venue side effects."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

from src.trading_kernel.domain.identities import TicketIdentity


class CommandGenerationError(ValueError):
    """Raised when a new command generation would violate effect identity."""


class ExchangeCommandKind(StrEnum):
    ENTRY = "entry"
    INITIAL_STOP = "initial_stop"
    TAKE_PROFIT = "take_profit"
    EXIT = "exit"
    CANCEL_ORDER = "cancel_order"
    REPLACE_PROTECTION = "replace_protection"
    CONTROLLED_FLATTEN = "controlled_flatten"


class ExchangeCommandStatus(StrEnum):
    PREPARED = "prepared"
    CLAIMED = "claimed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    OUTCOME_UNKNOWN = "outcome_unknown"
    RECONCILED_ABSENT = "reconciled_absent"
    RECONCILED_ACCEPTED = "reconciled_accepted"


class OrderCommandPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    side: Literal["buy", "sell"]
    quantity: Decimal
    order_type: Literal["market", "limit", "stop_market", "take_profit_market"]
    reduce_only: bool
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None

    @field_validator("quantity")
    @classmethod
    def _require_positive_quantity(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("command quantity must be positive")
        return value

    @field_validator("limit_price", "stop_price")
    @classmethod
    def _require_positive_optional_price(
        cls,
        value: Decimal | None,
    ) -> Decimal | None:
        if value is not None and value <= 0:
            raise ValueError("command price must be positive")
        return value

    @model_validator(mode="after")
    def _validate_order_shape(self) -> "OrderCommandPayload":
        if self.order_type == "limit" and self.limit_price is None:
            raise ValueError("limit order requires limit_price")
        if self.order_type != "limit" and self.limit_price is not None:
            raise ValueError("non-limit order forbids limit_price")
        if self.order_type in {"stop_market", "take_profit_market"}:
            if self.stop_price is None:
                raise ValueError("conditional order requires stop_price")
        elif self.stop_price is not None:
            raise ValueError("non-conditional order forbids stop_price")
        return self


class ExchangeCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    command_id: str
    ticket_identity: TicketIdentity
    kind: ExchangeCommandKind
    generation: int
    idempotency_key: str
    venue_client_order_id: str
    payload: OrderCommandPayload
    status: ExchangeCommandStatus
    created_at_ms: int
    deadline_at_ms: int

    @field_validator(
        "command_id",
        "idempotency_key",
        "venue_client_order_id",
        mode="before",
    )
    @classmethod
    def _require_non_blank_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("command identities must be non-blank")
        return normalized

    @field_validator("generation", "created_at_ms", "deadline_at_ms")
    @classmethod
    def _require_positive_integer(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("command generation and time must be positive")
        return value

    @model_validator(mode="after")
    def _validate_command(self) -> "ExchangeCommand":
        if self.kind is ExchangeCommandKind.ENTRY and self.generation != 1:
            raise ValueError("ENTRY command cannot have a retry generation")
        if self.deadline_at_ms <= self.created_at_ms:
            raise ValueError("command deadline must be after creation")
        if len(self.venue_client_order_id) > 36:
            raise ValueError("venue client order id exceeds supported boundary")
        return self


class ExchangeCommandResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ExchangeCommandStatus
    observed_at_ms: int
    exchange_order_id: str | None = None
    reason: str | None = None
    venue_payload: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("observed_at_ms")
    @classmethod
    def _require_positive_time(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("command result time must be positive")
        return value

    @model_validator(mode="after")
    def _validate_result_shape(self) -> "ExchangeCommandResult":
        if self.status not in {
            ExchangeCommandStatus.ACCEPTED,
            ExchangeCommandStatus.REJECTED,
            ExchangeCommandStatus.OUTCOME_UNKNOWN,
        }:
            raise ValueError("command result must be authoritative or unknown")
        if self.status is ExchangeCommandStatus.ACCEPTED:
            if not str(self.exchange_order_id or "").strip():
                raise ValueError("accepted command requires exchange order identity")
            if self.reason is not None:
                raise ValueError("accepted command forbids rejection reason")
        else:
            if not str(self.reason or "").strip():
                raise ValueError("rejected or unknown command requires reason")
            if self.exchange_order_id is not None:
                raise ValueError("non-accepted result forbids exchange order identity")
        return self


def build_command_id(
    *,
    ticket_id: str,
    kind: ExchangeCommandKind,
    generation: int,
) -> str:
    normalized_ticket_id = str(ticket_id or "").strip()
    if not normalized_ticket_id:
        raise ValueError("ticket_id must be non-blank")
    if generation <= 0:
        raise ValueError("generation must be positive")
    payload = f"{normalized_ticket_id}|{kind.value}|{generation}".encode("utf-8")
    return f"command:{sha256(payload).hexdigest()[:32]}"


def build_venue_client_order_id(command_id: str) -> str:
    normalized_command_id = str(command_id or "").strip()
    if not normalized_command_id:
        raise ValueError("command_id must be non-blank")
    digest = sha256(normalized_command_id.encode("utf-8")).hexdigest()[:28]
    return f"brc-{digest}"


def require_next_generation_allowed(
    *,
    kind: ExchangeCommandKind,
    prior_status: ExchangeCommandStatus,
    next_generation: int,
) -> None:
    if next_generation <= 1:
        raise CommandGenerationError("next generation must be greater than one")
    if kind is ExchangeCommandKind.ENTRY:
        raise CommandGenerationError("ENTRY is never retried")
    if prior_status is ExchangeCommandStatus.OUTCOME_UNKNOWN:
        raise CommandGenerationError("unknown outcome must be reconciled first")
    if prior_status not in {
        ExchangeCommandStatus.REJECTED,
        ExchangeCommandStatus.RECONCILED_ABSENT,
    }:
        raise CommandGenerationError(
            f"new generation not allowed after {prior_status.value}"
        )
