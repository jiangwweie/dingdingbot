"""Pure Phase 5E controlled-symbol cap feasibility checks."""

from __future__ import annotations

from decimal import Decimal, ROUND_CEILING
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


Phase5EFeasibilityReason = Literal[
    "OK",
    "MIN_NOTIONAL_EXCEEDS_CAP",
    "NOTIONAL_BELOW_MIN_NOTIONAL",
    "NOTIONAL_ABOVE_CAP",
]


class Phase5EControlledSymbolFeasibility(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    amount: Decimal
    price: Decimal
    notional: Decimal
    min_notional: Decimal
    min_notional_source: str
    max_notional: Optional[Decimal] = None
    next_viable_amount: Optional[Decimal] = None
    next_viable_notional: Optional[Decimal] = None
    cap_shortfall: Optional[Decimal] = None
    feasible: bool
    reason: Phase5EFeasibilityReason


def _ceil_to_step(value: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        raise ValueError("amount_step must be positive")
    units = (value / step).to_integral_value(rounding=ROUND_CEILING)
    return units * step


def assess_controlled_symbol_feasibility(
    *,
    symbol: str,
    amount: Decimal,
    price: Decimal,
    min_notional: Decimal,
    min_notional_source: str,
    max_notional: Optional[Decimal],
    amount_step: Optional[Decimal] = None,
) -> Phase5EControlledSymbolFeasibility:
    """Assess fixed controlled amount against min-notional and cap constraints."""

    notional = price * amount
    next_viable_amount: Optional[Decimal] = None
    next_viable_notional: Optional[Decimal] = None
    cap_shortfall: Optional[Decimal] = None
    reason: Phase5EFeasibilityReason = "OK"
    feasible = True

    if amount_step is not None and price > 0:
        next_viable_amount = _ceil_to_step(min_notional / price, amount_step)
        if next_viable_amount < amount:
            next_viable_amount = amount
        next_viable_notional = next_viable_amount * price
        if max_notional is not None and next_viable_notional > max_notional:
            cap_shortfall = next_viable_notional - max_notional

    if max_notional is not None and min_notional > max_notional:
        feasible = False
        reason = "MIN_NOTIONAL_EXCEEDS_CAP"
    elif notional < min_notional:
        feasible = False
        reason = "NOTIONAL_BELOW_MIN_NOTIONAL"
    elif max_notional is not None and notional > max_notional:
        feasible = False
        reason = "NOTIONAL_ABOVE_CAP"

    return Phase5EControlledSymbolFeasibility(
        symbol=symbol,
        amount=amount,
        price=price,
        notional=notional,
        min_notional=min_notional,
        min_notional_source=min_notional_source,
        max_notional=max_notional,
        next_viable_amount=next_viable_amount,
        next_viable_notional=next_viable_notional,
        cap_shortfall=cap_shortfall,
        feasible=feasible,
        reason=reason,
    )
