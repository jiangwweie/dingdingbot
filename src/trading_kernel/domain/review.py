"""Pure post-trade economics for one terminal Trade Ticket."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class ReviewEconomicsUnavailable(ValueError):
    """Raised when exact Ticket-bound economics cannot yet be computed."""


class ReviewEconomicsCompleteness(StrEnum):
    COMPLETE = "complete"
    FUNDING_UNAVAILABLE = "funding_unavailable"


class ReviewFill(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_trade_id: str
    venue_client_order_id: str
    quantity: Decimal
    price: Decimal
    fee_quote: Decimal
    occurred_at_ms: int

    @field_validator(
        "exchange_trade_id",
        "venue_client_order_id",
        mode="before",
    )
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("review fill identities must be non-blank")
        return normalized

    @field_validator("quantity", "price")
    @classmethod
    def _require_positive_value(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("review fill quantity and price must be positive")
        return value

    @field_validator("fee_quote")
    @classmethod
    def _require_nonnegative_fee(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("review fill fee cannot be negative")
        return value

    @field_validator("occurred_at_ms")
    @classmethod
    def _require_positive_time(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("review fill time must be positive")
        return value


class ReviewEconomicsFacts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str
    entry_fills: tuple[ReviewFill, ...]
    exit_fills: tuple[ReviewFill, ...]
    funding_quote: Decimal | None
    funding_unavailable_reason: str | None
    observed_at_ms: int

    @field_validator("ticket_id", mode="before")
    @classmethod
    def _require_ticket_id(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("review economics requires Ticket identity")
        return normalized

    @field_validator("observed_at_ms")
    @classmethod
    def _require_positive_time(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("review economics observation time must be positive")
        return value

    @model_validator(mode="after")
    def _validate_funding_shape(self) -> "ReviewEconomicsFacts":
        reason = str(self.funding_unavailable_reason or "").strip()
        if self.funding_quote is None:
            if not reason:
                raise ValueError(
                    "unavailable funding requires an explicit reason"
                )
        elif reason:
            raise ValueError("available funding forbids an unavailable reason")
        return self


class ReviewEconomics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    entry_quantity: Decimal
    entry_average_price: Decimal
    exit_quantity: Decimal
    exit_average_price: Decimal
    gross_realized_pnl_quote: Decimal
    trading_fees_quote: Decimal
    net_pnl_before_funding_quote: Decimal
    funding_quote: Decimal | None
    net_pnl_quote: Decimal | None
    planned_stop_risk: Decimal
    actual_stop_risk: Decimal | None
    risk_variance: Decimal | None
    risk_variance_fraction: Decimal | None
    planned_r_multiple: Decimal | None
    actual_r_multiple: Decimal | None
    economics_completeness: ReviewEconomicsCompleteness
    funding_unavailable_reason: str | None


def calculate_review_economics(
    *,
    facts: ReviewEconomicsFacts,
    expected_entry_quantity: Decimal,
    position_side: Literal["long", "short"],
    planned_risk_at_stop: Decimal,
    actual_risk_at_stop: Decimal | None,
) -> ReviewEconomics:
    if expected_entry_quantity <= 0:
        raise ValueError("expected Ticket quantity must be positive")
    if planned_risk_at_stop <= 0:
        raise ReviewEconomicsUnavailable("planned Ticket risk at stop must be positive")
    if actual_risk_at_stop is not None and actual_risk_at_stop <= 0:
        raise ReviewEconomicsUnavailable("actual stop risk must be positive")
    if not facts.entry_fills:
        raise ReviewEconomicsUnavailable("entry fills are unavailable")
    if not facts.exit_fills:
        raise ReviewEconomicsUnavailable("exit fills are unavailable")

    entry_quantity, entry_average_price = _fill_totals(facts.entry_fills)
    exit_quantity, exit_average_price = _fill_totals(facts.exit_fills)
    if entry_quantity != expected_entry_quantity:
        raise ReviewEconomicsUnavailable(
            "entry fill quantity does not equal Ticket quantity"
        )
    if exit_quantity != expected_entry_quantity:
        raise ReviewEconomicsUnavailable(
            "exit fill quantity does not equal Ticket quantity"
        )

    direction = Decimal("1") if position_side == "long" else Decimal("-1")
    gross_realized_pnl = sum(
        (
            (fill.price - entry_average_price)
            * fill.quantity
            * direction
            for fill in facts.exit_fills
        ),
        Decimal("0"),
    )
    trading_fees = sum(
        (fill.fee_quote for fill in (*facts.entry_fills, *facts.exit_fills)),
        Decimal("0"),
    )
    net_before_funding = gross_realized_pnl - trading_fees
    risk_variance = (
        None
        if actual_risk_at_stop is None
        else actual_risk_at_stop - planned_risk_at_stop
    )
    risk_variance_fraction = (
        None
        if risk_variance is None
        else risk_variance / planned_risk_at_stop
    )
    if facts.funding_quote is None:
        net_pnl = None
        planned_r_multiple = None
        actual_r_multiple = None
        completeness = ReviewEconomicsCompleteness.FUNDING_UNAVAILABLE
    else:
        net_pnl = net_before_funding + facts.funding_quote
        planned_r_multiple = net_pnl / planned_risk_at_stop
        actual_r_multiple = (
            None if actual_risk_at_stop is None else net_pnl / actual_risk_at_stop
        )
        completeness = ReviewEconomicsCompleteness.COMPLETE

    return ReviewEconomics(
        entry_quantity=entry_quantity,
        entry_average_price=entry_average_price,
        exit_quantity=exit_quantity,
        exit_average_price=exit_average_price,
        gross_realized_pnl_quote=gross_realized_pnl,
        trading_fees_quote=trading_fees,
        net_pnl_before_funding_quote=net_before_funding,
        funding_quote=facts.funding_quote,
        net_pnl_quote=net_pnl,
        planned_stop_risk=planned_risk_at_stop,
        actual_stop_risk=actual_risk_at_stop,
        risk_variance=risk_variance,
        risk_variance_fraction=risk_variance_fraction,
        planned_r_multiple=planned_r_multiple,
        actual_r_multiple=actual_r_multiple,
        economics_completeness=completeness,
        funding_unavailable_reason=facts.funding_unavailable_reason,
    )


def _fill_totals(fills: tuple[ReviewFill, ...]) -> tuple[Decimal, Decimal]:
    quantity = sum((fill.quantity for fill in fills), Decimal("0"))
    if quantity <= 0:
        raise ReviewEconomicsUnavailable("fill quantity must be positive")
    notional = sum(
        (fill.quantity * fill.price for fill in fills),
        Decimal("0"),
    )
    return quantity, notional / quantity
