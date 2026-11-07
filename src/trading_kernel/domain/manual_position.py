"""Conservative manual exposure assessment; never emits a venue effect."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from src.trading_kernel.domain.trade_management import OrderTerms


class ManualExposureAssessment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    protected_quantity: Decimal = Field(ge=0, allow_inf_nan=False)
    risk_at_stop: Decimal | None
    reason: str | None
    entry_blocked: bool


def assess_manual_exposure(
    *,
    quantity: Decimal,
    initial_quantity: Decimal,
    initial_risk: Decimal,
    entry_price: Decimal,
    position_side: str,
    orders: tuple[OrderTerms, ...],
    facts_complete: bool,
    fee_rate: Decimal = Decimal(0),
) -> ManualExposureAssessment:
    def blocked(reason, covered=Decimal(0)):
        return ManualExposureAssessment(
            protected_quantity=covered,
            risk_at_stop=None,
            reason=reason,
            entry_blocked=True,
        )

    if not facts_complete:
        return blocked("manual_order_facts_incomplete")
    if (
        any(
            not v.is_finite() or v < 0
            for v in (quantity, initial_quantity, initial_risk, entry_price, fee_rate)
        )
        or initial_quantity <= 0
        or entry_price <= 0
    ):
        return blocked("manual_risk_inputs_invalid")
    if quantity > initial_quantity:
        return blocked("manual_exposure_increased")
    if quantity == 0:
        return ManualExposureAssessment(
            protected_quantity=Decimal(0),
            risk_at_stop=Decimal(0),
            reason=None,
            entry_blocked=False,
        )
    stops = tuple(
        o
        for o in orders
        if o.position_side == position_side
        and o.reduces_position
        and o.order_type == "STOP_MARKET"
        and o.trigger_price is not None
    )
    # Do not add overlapping full-position stops and claim excess coverage.
    if len(stops) != 1:
        return blocked("manual_stop_allocation_unproven")
    stop = stops[0]
    if not stop.close_position and stop.quantity is not None and stop.quantity>quantity:
        return blocked("manual_stop_quantity_exceeds_position")
    covered = (
        quantity if stop.close_position else min(stop.quantity or Decimal(0), quantity)
    )
    if covered < quantity:
        return blocked("manual_stop_coverage_incomplete", covered)
    assert stop.trigger_price is not None
    delta = (
        (entry_price - stop.trigger_price)
        if position_side == "long"
        else (stop.trigger_price - entry_price)
    )
    actual = quantity * (max(delta, Decimal(0)) + entry_price * fee_rate)
    floor = initial_risk * quantity / initial_quantity
    return ManualExposureAssessment(
        protected_quantity=quantity,
        risk_at_stop=max(actual, floor),
        reason=None,
        entry_blocked=False,
    )
