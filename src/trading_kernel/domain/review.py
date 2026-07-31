"""Pure post-trade economics for one terminal Trade Ticket."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, JsonValue, field_validator, model_validator

from src.trading_kernel.domain.fee_valuation import ValuedFee
from src.trading_kernel.domain.order_attribution import (
    AttributedTradeFill,
    OrderRole,
)


class ReviewEconomicsUnavailable(ValueError):
    """Raised when exact Ticket-bound economics cannot yet be computed."""


class ReviewEconomicsCompleteness(StrEnum):
    COMPLETE = "complete"
    FUNDING_UNAVAILABLE = "funding_unavailable"
    EXTERNAL_EXIT_UNAVAILABLE = "external_exit_unavailable"


class SorV2HistoryClassification(StrEnum):
    RIGHT_TAIL_UNVERIFIED = "right_tail_unverified"
    INVALID_PERSISTENT_STATE = "invalid_persistent_state"


def sor_v2_history_decision_impact(
    classification: SorV2HistoryClassification,
) -> dict[str, JsonValue]:
    """Return the exact append-only evidence classification for one v2 Ticket."""

    if classification is SorV2HistoryClassification.RIGHT_TAIL_UNVERIFIED:
        return {
            "entry_semantics": "unverified_against_sor_v3_edge",
            "evidence_scope": [
                "lifecycle",
                "tp1_transition",
                "break_even",
                "structural_runner",
                "right_tail",
            ],
            "entry_alpha_inclusion": (
                "excluded_until_candle_reconstruction"
            ),
        }
    return {
        "entry_semantics": "invalid_sor_v2_persistent_state",
        "entry_alpha_inclusion": "excluded",
        "execution_evidence": "retained",
        "lifecycle_evidence": "retained",
        "economics_evidence": "retained",
    }


class ReviewFill(BaseModel):
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
            raise ValueError("review fill identities must be non-blank")
        return normalized

    @field_validator("quantity", "price")
    @classmethod
    def _require_positive_value(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("review fill quantity and price must be positive")
        return value

    @field_validator("occurred_at_ms")
    @classmethod
    def _require_positive_time(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("review fill time must be positive")
        return value

    @field_validator("realized_pnl_quote")
    @classmethod
    def _require_finite_realized_pnl(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("review fill realized pnl must be finite")
        return value

    @property
    def fee_quote(self) -> Decimal:
        return self.fee.usdt_value

    def to_attributed_trade_fill(self) -> AttributedTradeFill:
        return AttributedTradeFill(
            exchange_trade_id=self.exchange_trade_id,
            exchange_order_id=self.exchange_order_id,
            command_id=self.command_id,
            role=self.role,
            quantity=self.quantity,
            price=self.price,
            fee=self.fee,
            realized_pnl_quote=self.realized_pnl_quote,
            occurred_at_ms=self.occurred_at_ms,
        )


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
    def _validate_funding_shape(self) -> ReviewEconomicsFacts:
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


class ExternalExitUnavailableReview(BaseModel):
    """Explicitly records an externally closed position without invented PnL."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    economics_completeness: Literal[
        ReviewEconomicsCompleteness.EXTERNAL_EXIT_UNAVAILABLE
    ]
    unavailable_reason: Literal["external_flat_exit_fills_unavailable"]
    entry_quantity: Decimal
    entry_time_ms: int
    external_flat_detected_at_ms: int
    visibility_grace_ms: int

    @field_validator("entry_quantity")
    @classmethod
    def _require_positive_entry_quantity(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("external review entry quantity must be positive")
        return value

    @field_validator(
        "entry_time_ms",
        "external_flat_detected_at_ms",
        "visibility_grace_ms",
    )
    @classmethod
    def _require_positive_window(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("external review window values must be positive")
        return value


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

    direction = Decimal(1) if position_side == "long" else Decimal(-1)
    gross_realized_pnl = sum(
        (
            (fill.price - entry_average_price)
            * fill.quantity
            * direction
            for fill in facts.exit_fills
        ),
        Decimal(0),
    )
    trading_fees = sum(
        (fill.fee_quote for fill in (*facts.entry_fills, *facts.exit_fills)),
        Decimal(0),
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
    quantity = sum((fill.quantity for fill in fills), Decimal(0))
    if quantity <= 0:
        raise ReviewEconomicsUnavailable("fill quantity must be positive")
    notional = sum(
        (fill.quantity * fill.price for fill in fills),
        Decimal(0),
    )
    return quantity, notional / quantity
