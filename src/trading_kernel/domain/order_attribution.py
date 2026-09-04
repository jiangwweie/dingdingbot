"""Pure exact identities joining durable commands to venue fills."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.domain.commands import ExchangeCommandKind
from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.fee_valuation import ValuedFee


class OrderNamespace(StrEnum):
    REGULAR = "regular"
    CONDITIONAL = "conditional"


class OrderRole(StrEnum):
    ENTRY = "entry"
    EXIT = "exit"


class ConditionalOrderExpectation(BaseModel):
    """Frozen Ticket and Command facts required to verify a Binance algo order."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_instrument_id: str
    position_side: Literal["long", "short"]
    side: Literal["buy", "sell"]
    order_type: Literal["stop_market", "take_profit_market"]
    quantity: Decimal

    @field_validator("exchange_instrument_id", mode="before")
    @classmethod
    def _require_instrument_id(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("conditional expectation requires instrument identity")
        return normalized

    @field_validator("quantity")
    @classmethod
    def _require_positive_quantity(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0:
            raise ValueError(
                "conditional expectation quantity must be finite and positive"
            )
        return value


class TicketOrderReference(BaseModel):
    """Immutable command acceptance identity before trade lookup."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    command_id: str
    command_kind: ExchangeCommandKind
    role: OrderRole
    namespace: OrderNamespace
    venue_client_order_id: str
    submitted_exchange_order_id: str
    command_created_at_ms: int
    conditional_expectation: ConditionalOrderExpectation | None = None

    @field_validator(
        "command_id",
        "venue_client_order_id",
        "submitted_exchange_order_id",
        mode="before",
    )
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("order attribution identities must be non-blank")
        return normalized

    @field_validator("command_created_at_ms")
    @classmethod
    def _require_command_creation_time(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("order reference command creation time must be positive")
        return value

    @model_validator(mode="after")
    def _validate_role(self) -> TicketOrderReference:
        if self.command_kind is ExchangeCommandKind.ENTRY:
            if self.role is not OrderRole.ENTRY:
                raise ValueError("ENTRY command must use the entry attribution role")
        elif self.role is not OrderRole.EXIT:
            raise ValueError("non-ENTRY command must use the exit attribution role")
        if self.namespace is OrderNamespace.CONDITIONAL:
            if self.conditional_expectation is None:
                raise ValueError(
                    "conditional order requires frozen command expectation"
                )
        elif self.conditional_expectation is not None:
            raise ValueError(
                "regular order forbids conditional command expectation"
            )
        return self


class ResolvedOrderIdentity(BaseModel):
    """The exact regular order id that is legal to query for fills."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reference: TicketOrderReference
    resolution_status: Literal["executable", "not_triggered"]
    actual_order_id: str | None
    resolved_at_ms: int

    @field_validator("actual_order_id", mode="before")
    @classmethod
    def _normalize_optional_order_id(cls, value: object) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @model_validator(mode="after")
    def _validate_resolution(self) -> ResolvedOrderIdentity:
        if self.resolved_at_ms <= 0:
            raise ValueError("order identity resolution time must be positive")
        if self.resolution_status == "not_triggered":
            if self.reference.namespace is not OrderNamespace.CONDITIONAL:
                raise ValueError("only conditional orders may be not-triggered")
            if self.actual_order_id is not None:
                raise ValueError("not-triggered order forbids an actual order id")
            return self
        if self.actual_order_id is None:
            raise ValueError("executable order requires an actual order id")
        if (
            self.reference.namespace is OrderNamespace.REGULAR
            and self.actual_order_id != self.reference.submitted_exchange_order_id
        ):
            raise ValueError("regular order identity must equal the submitted order id")
        return self


class AttributedTradeFill(BaseModel):
    """One exact trade row assigned to one durable command role."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_trade_id: str
    exchange_order_id: str
    command_id: str
    role: OrderRole
    quantity: Decimal
    price: Decimal
    fee: ValuedFee
    realized_pnl_quote: Decimal
    occurred_at_ms: int

    @field_validator(
        "exchange_trade_id",
        "exchange_order_id",
        "command_id",
        mode="before",
    )
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("attributed fill identities must be non-blank")
        return normalized

    @field_validator("quantity", "price")
    @classmethod
    def _require_finite_positive_value(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0:
            raise ValueError(
                "attributed fill quantity and price must be finite and positive"
            )
        return value

    @field_validator("realized_pnl_quote")
    @classmethod
    def _require_finite_pnl(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("attributed realized pnl must be finite")
        return value

    @field_validator("occurred_at_ms")
    @classmethod
    def _require_positive_time(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("attributed fill time must be positive")
        return value


def attribution_digest(fills: tuple[AttributedTradeFill, ...]) -> str:
    """Hash canonical, order-independent fill evidence for one Review."""

    return canonical_digest(
        tuple(
            sorted(
                (fill.model_dump(mode="python") for fill in fills),
                key=lambda value: (
                    str(value["exchange_trade_id"]),
                    str(value["exchange_order_id"]),
                    str(value["command_id"]),
                ),
            )
        )
    )
