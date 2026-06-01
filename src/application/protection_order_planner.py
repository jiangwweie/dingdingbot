"""Precision-aware protection order planning for controlled rehearsals.

This module is pure application logic. It does not call exchanges, create
execution intents, or place orders.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field


ProtectionPlanType = Literal[
    "multi_tp_plus_sl",
    "single_tp_plus_sl",
    "sl_only",
    "entry_without_protection_forbidden",
    "blocked_unprotectable_size",
]

ProtectionPlanStatus = Literal["valid", "blocked"]


class ProtectionOrderPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: ProtectionPlanStatus
    plan_type: ProtectionPlanType
    entry_quantity: Decimal
    min_amount: Optional[Decimal] = None
    amount_step: Optional[Decimal] = None
    amount_precision: Optional[int] = None
    min_notional: Optional[Decimal] = None
    min_notional_source: Optional[str] = None
    entry_notional: Optional[Decimal] = None
    intended_tp_ratios: tuple[Decimal, ...] = Field(default_factory=tuple)
    planned_tp_ratios: tuple[Decimal, ...] = Field(default_factory=tuple)
    planned_tp_quantities: tuple[Decimal, ...] = Field(default_factory=tuple)
    planned_sl_quantity: Optional[Decimal] = None
    tp_targets: tuple[Decimal, ...] = Field(default_factory=tuple)
    fallback_reason: Optional[str] = None
    blocked_reason: Optional[str] = None
    degraded_protection: bool = False
    no_entry_without_protection: Literal[True] = True


def _decimal_places(step: Optional[Decimal]) -> Optional[int]:
    if step is None:
        return None
    exponent = step.normalize().as_tuple().exponent
    return abs(exponent) if exponent < 0 else 0


def _meets_quantity_constraints(
    quantity: Decimal,
    *,
    min_amount: Decimal,
    amount_step: Optional[Decimal],
) -> bool:
    if quantity < min_amount:
        return False
    if amount_step is None:
        return True
    if amount_step <= 0:
        return False
    return quantity % amount_step == 0


def plan_precision_aware_protection_orders(
    *,
    entry_quantity: Decimal,
    entry_price: Decimal,
    min_amount: Optional[Decimal],
    amount_step: Optional[Decimal],
    min_notional: Optional[Decimal],
    min_notional_source: Optional[str],
    intended_tp_ratios: Sequence[Decimal] = (Decimal("0.5"), Decimal("0.5")),
    intended_tp_targets: Sequence[Decimal] = (Decimal("1.0"), Decimal("3.5")),
    allow_sl_only: bool = False,
) -> ProtectionOrderPlan:
    """Build an executable protection plan or fail closed before entry.

    The planner validates quantities for all protection orders before the
    controlled entry is submitted. It falls back from multi-TP to single-TP
    when split quantities are below symbol constraints.
    """

    ratios = tuple(Decimal(str(item)) for item in intended_tp_ratios)
    targets = tuple(Decimal(str(item)) for item in intended_tp_targets)
    entry_notional = entry_quantity * entry_price

    if min_amount is None or min_amount <= 0:
        return ProtectionOrderPlan(
            status="blocked",
            plan_type="blocked_unprotectable_size",
            entry_quantity=entry_quantity,
            amount_step=amount_step,
            amount_precision=_decimal_places(amount_step),
            min_notional=min_notional,
            min_notional_source=min_notional_source,
            entry_notional=entry_notional,
            intended_tp_ratios=ratios,
            blocked_reason="protection_min_amount_unavailable",
        )

    amount_precision = _decimal_places(amount_step)
    sl_valid = _meets_quantity_constraints(entry_quantity, min_amount=min_amount, amount_step=amount_step)
    if min_notional is not None and entry_notional < min_notional:
        sl_valid = False
    if not sl_valid:
        return ProtectionOrderPlan(
            status="blocked",
            plan_type="blocked_unprotectable_size",
            entry_quantity=entry_quantity,
            min_amount=min_amount,
            amount_step=amount_step,
            amount_precision=amount_precision,
            min_notional=min_notional,
            min_notional_source=min_notional_source,
            entry_notional=entry_notional,
            intended_tp_ratios=ratios,
            blocked_reason="entry_quantity_cannot_create_valid_sl",
        )

    if not ratios or sum(ratios, Decimal("0")) <= 0:
        if allow_sl_only:
            return ProtectionOrderPlan(
                status="valid",
                plan_type="sl_only",
                entry_quantity=entry_quantity,
                min_amount=min_amount,
                amount_step=amount_step,
                amount_precision=amount_precision,
                min_notional=min_notional,
                min_notional_source=min_notional_source,
                entry_notional=entry_notional,
                planned_sl_quantity=entry_quantity,
                fallback_reason="tp_ratios_unavailable",
                degraded_protection=True,
            )
        return ProtectionOrderPlan(
            status="blocked",
            plan_type="entry_without_protection_forbidden",
            entry_quantity=entry_quantity,
            min_amount=min_amount,
            amount_step=amount_step,
            amount_precision=amount_precision,
            min_notional=min_notional,
            min_notional_source=min_notional_source,
            entry_notional=entry_notional,
            blocked_reason="tp_ratios_unavailable",
        )

    normalized_total = sum(ratios, Decimal("0"))
    normalized_ratios = tuple(ratio / normalized_total for ratio in ratios)
    split_quantities: list[Decimal] = []
    allocated = Decimal("0")
    for index, ratio in enumerate(normalized_ratios):
        if index == len(normalized_ratios) - 1:
            qty = entry_quantity - allocated
        else:
            qty = entry_quantity * ratio
            allocated += qty
        split_quantities.append(qty)

    split_valid = all(
        _meets_quantity_constraints(qty, min_amount=min_amount, amount_step=amount_step)
        for qty in split_quantities
    )
    if split_valid:
        return ProtectionOrderPlan(
            status="valid",
            plan_type="multi_tp_plus_sl",
            entry_quantity=entry_quantity,
            min_amount=min_amount,
            amount_step=amount_step,
            amount_precision=amount_precision,
            min_notional=min_notional,
            min_notional_source=min_notional_source,
            entry_notional=entry_notional,
            intended_tp_ratios=ratios,
            planned_tp_ratios=normalized_ratios,
            planned_tp_quantities=tuple(split_quantities),
            planned_sl_quantity=entry_quantity,
            tp_targets=targets,
        )

    if _meets_quantity_constraints(entry_quantity, min_amount=min_amount, amount_step=amount_step):
        return ProtectionOrderPlan(
            status="valid",
            plan_type="single_tp_plus_sl",
            entry_quantity=entry_quantity,
            min_amount=min_amount,
            amount_step=amount_step,
            amount_precision=amount_precision,
            min_notional=min_notional,
            min_notional_source=min_notional_source,
            entry_notional=entry_notional,
            intended_tp_ratios=ratios,
            planned_tp_ratios=(Decimal("1.0"),),
            planned_tp_quantities=(entry_quantity,),
            planned_sl_quantity=entry_quantity,
            tp_targets=(targets[0] if targets else Decimal("1.0"),),
            fallback_reason="split_tp_quantity_below_min_amount",
        )

    if allow_sl_only and sl_valid:
        return ProtectionOrderPlan(
            status="valid",
            plan_type="sl_only",
            entry_quantity=entry_quantity,
            min_amount=min_amount,
            amount_step=amount_step,
            amount_precision=amount_precision,
            min_notional=min_notional,
            min_notional_source=min_notional_source,
            entry_notional=entry_notional,
            intended_tp_ratios=ratios,
            planned_sl_quantity=entry_quantity,
            fallback_reason="tp_quantity_unprotectable_sl_only_allowed",
            degraded_protection=True,
        )

    return ProtectionOrderPlan(
        status="blocked",
        plan_type="blocked_unprotectable_size",
        entry_quantity=entry_quantity,
        min_amount=min_amount,
        amount_step=amount_step,
        amount_precision=amount_precision,
        min_notional=min_notional,
        min_notional_source=min_notional_source,
        entry_notional=entry_notional,
        intended_tp_ratios=ratios,
        planned_sl_quantity=entry_quantity if sl_valid else None,
        blocked_reason="protection_quantities_below_min_amount",
    )
