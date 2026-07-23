"""Durable exactly-once command identity for all venue side effects."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

from src.trading_kernel.domain.identities import TicketIdentity


class CommandGenerationError(ValueError):
    """Raised when a new command generation would violate effect identity."""


class ExchangeCommandKind(StrEnum):
    SET_LEVERAGE = "set_leverage"
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
    SUPERSEDED = "superseded"
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
    replaces_exchange_order_id: str | None = None
    source_watermark_ms: int | None = None
    required_configured_leverage: int | None = None
    leverage_verification_digest: str | None = None

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
        replacement_fields = (
            self.replaces_exchange_order_id,
            self.source_watermark_ms,
        )
        if any(value is not None for value in replacement_fields):
            if not str(self.replaces_exchange_order_id or "").strip():
                raise ValueError("replacement payload requires prior order identity")
            if self.source_watermark_ms is None or self.source_watermark_ms <= 0:
                raise ValueError("replacement payload requires a positive watermark")
        leverage_fields = (
            self.required_configured_leverage,
            self.leverage_verification_digest,
        )
        if any(value is not None for value in leverage_fields):
            if (
                isinstance(self.required_configured_leverage, bool)
                or not isinstance(self.required_configured_leverage, int)
                or self.required_configured_leverage <= 0
            ):
                raise ValueError("entry leverage requirement must be a positive integer")
            if not _SHA256_DIGEST.fullmatch(
                str(self.leverage_verification_digest or "")
            ):
                raise ValueError("entry leverage verification requires a sha256 digest")
        return self


class CancelCommandPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_order_id: str

    @field_validator("exchange_order_id", mode="before")
    @classmethod
    def _require_exchange_order_id(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("cancel command requires exchange order identity")
        return normalized


_SHA256_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class SetLeverageCommandPayload(BaseModel):
    """Immutable non-order mutation requested before a new ENTRY."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    desired_leverage: int
    owner_policy_version: int
    entry_admission_snapshot_digest: str
    leverage_fact_digest: str

    @field_validator("desired_leverage", "owner_policy_version", mode="before")
    @classmethod
    def _require_positive_integer(cls, value: object) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("leverage command integers must be positive integers")
        return value

    @field_validator(
        "entry_admission_snapshot_digest",
        "leverage_fact_digest",
    )
    @classmethod
    def _require_digest(cls, value: str) -> str:
        if _SHA256_DIGEST.fullmatch(value) is None:
            raise ValueError("leverage command requires canonical sha256 digests")
        return value


CommandPayload = OrderCommandPayload | CancelCommandPayload | SetLeverageCommandPayload


class ExchangeCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    command_id: str
    ticket_identity: TicketIdentity
    kind: ExchangeCommandKind
    generation: int
    idempotency_key: str
    venue_client_order_id: str | None
    payload: CommandPayload
    status: ExchangeCommandStatus
    created_at_ms: int
    deadline_at_ms: int

    @field_validator(
        "command_id",
        "idempotency_key",
        mode="before",
    )
    @classmethod
    def _require_non_blank_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("command identities must be non-blank")
        return normalized

    @field_validator("venue_client_order_id", mode="before")
    @classmethod
    def _normalize_optional_venue_client_order_id(cls, value: object) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @field_validator("generation", "created_at_ms", "deadline_at_ms")
    @classmethod
    def _require_positive_integer(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("command generation and time must be positive")
        return value

    @model_validator(mode="after")
    def _validate_command(self) -> "ExchangeCommand":
        if self.kind in {
            ExchangeCommandKind.SET_LEVERAGE,
            ExchangeCommandKind.ENTRY,
        } and self.generation != 1:
            raise ValueError(f"{self.kind.value.upper()} command cannot have a retry generation")
        if self.deadline_at_ms <= self.created_at_ms:
            raise ValueError("command deadline must be after creation")
        if (
            self.venue_client_order_id is not None
            and len(self.venue_client_order_id) > 36
        ):
            raise ValueError("venue client order id exceeds supported boundary")
        if self.kind is ExchangeCommandKind.SET_LEVERAGE:
            if self.venue_client_order_id is not None:
                raise ValueError("SET_LEVERAGE command forbids venue_client_order_id")
            if not isinstance(self.payload, SetLeverageCommandPayload):
                raise ValueError("SET_LEVERAGE command requires leverage payload")
            return self
        if self.venue_client_order_id is None:
            raise ValueError("order command requires deterministic venue_client_order_id")
        if self.kind is ExchangeCommandKind.CANCEL_ORDER:
            if not isinstance(self.payload, CancelCommandPayload):
                raise ValueError("cancel command requires cancel payload")
        elif not isinstance(self.payload, OrderCommandPayload):
            raise ValueError("order command requires order payload")
        if isinstance(self.payload, OrderCommandPayload):
            leverage_fields = (
                self.payload.required_configured_leverage,
                self.payload.leverage_verification_digest,
            )
            if self.kind is ExchangeCommandKind.ENTRY:
                if any(value is None for value in leverage_fields):
                    raise ValueError(
                        "ENTRY command requires leverage verification evidence"
                    )
            elif any(value is not None for value in leverage_fields):
                raise ValueError("only ENTRY command allows leverage verification evidence")
            has_replacement_metadata = (
                self.payload.replaces_exchange_order_id is not None
                or self.payload.source_watermark_ms is not None
            )
            if self.kind is ExchangeCommandKind.REPLACE_PROTECTION:
                if not has_replacement_metadata:
                    raise ValueError(
                        "protection replacement command requires replacement metadata"
                    )
            elif has_replacement_metadata:
                raise ValueError(
                    "only protection replacement commands allow replacement metadata"
                )
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


class SetLeverageCommandResult(BaseModel):
    """Authoritative confirmation shape for an exact leverage mutation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

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
            raise ValueError("leverage result integers must be positive integers")
        return value

    @field_validator("leverage_verification_digest")
    @classmethod
    def _require_verification_digest(cls, value: str) -> str:
        if _SHA256_DIGEST.fullmatch(value) is None:
            raise ValueError("leverage result requires a canonical sha256 digest")
        return value


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
    if kind in {ExchangeCommandKind.ENTRY, ExchangeCommandKind.SET_LEVERAGE}:
        raise CommandGenerationError(f"{kind.value.upper()} is never retried")
    if prior_status is ExchangeCommandStatus.OUTCOME_UNKNOWN:
        raise CommandGenerationError("unknown outcome must be reconciled first")
    if (
        kind is ExchangeCommandKind.REPLACE_PROTECTION
        and prior_status
        in {
            ExchangeCommandStatus.ACCEPTED,
            ExchangeCommandStatus.RECONCILED_ACCEPTED,
        }
    ):
        return
    if prior_status not in {
        ExchangeCommandStatus.REJECTED,
        ExchangeCommandStatus.RECONCILED_ABSENT,
    }:
        raise CommandGenerationError(
            f"new generation not allowed after {prior_status.value}"
        )
