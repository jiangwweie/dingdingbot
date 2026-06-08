"""Notional-based sizing for bounded owner actions.

This module is pure application logic. It does not call exchanges, create
authorizations, create execution intents, place orders, or mutate PG.
"""

from __future__ import annotations

import time
from decimal import Decimal, ROUND_CEILING
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


NotionalSizingStatus = Literal["valid", "blocked"]
MarketRuleFreshness = Literal["fresh", "stale", "unavailable"]


class ContractMarketRules(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    min_notional: Decimal = Field(gt=Decimal("0"))
    min_qty: Decimal = Field(gt=Decimal("0"))
    qty_step: Decimal = Field(gt=Decimal("0"))
    price_tick: Decimal | None = Field(default=None, gt=Decimal("0"))
    current_price: Decimal = Field(gt=Decimal("0"))
    freshness: MarketRuleFreshness = "fresh"
    source: str
    observed_at_ms: int = Field(default_factory=lambda: int(time.time() * 1000))


class NotionalSizingValidation(BaseModel):
    model_config = ConfigDict(frozen=True)

    entry_quantity_valid: bool
    entry_notional_valid: bool
    protection_quantity_valid: bool
    protection_notional_valid: bool
    max_notional_valid: bool
    market_rules_fresh: bool


class NotionalSizingResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: NotionalSizingStatus
    symbol: str
    side: Literal["long", "short"]
    target_notional_usdt: Decimal
    computed_quantity: Decimal
    estimated_notional_usdt: Decimal
    estimated_worst_protection_notional_usdt: Decimal
    max_notional_usdt: Decimal | None = None
    suggested_minimum_notional_usdt: Decimal
    suggested_quantity: Decimal
    market_rule_snapshot: ContractMarketRules
    validation: NotionalSizingValidation
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    sizing_source: str = "target_notional_usdt_and_contract_market_rules"


def compute_notional_sizing(
    *,
    symbol: str,
    side: Literal["long", "short"],
    target_notional_usdt: Decimal,
    market_rules: ContractMarketRules,
    max_notional_usdt: Decimal | None = None,
    stop_loss_fraction: Decimal = Decimal("0.01"),
    tp_target_pct: Decimal = Decimal("1.0"),
) -> NotionalSizingResult:
    """Derive an executable contract quantity from a USDT notional target.

    Quantity is rounded upward to the exchange quantity step. The minimum
    quantity is calculated against the most conservative full-size protection
    order price so that entry, TP, and SL can all satisfy min-notional rules.
    """

    target = Decimal(str(target_notional_usdt))
    if target <= 0:
        raise ValueError("target_notional_usdt must be positive")
    if market_rules.symbol != symbol:
        raise ValueError("market rules symbol does not match sizing symbol")
    if stop_loss_fraction <= 0:
        raise ValueError("stop_loss_fraction must be positive")
    if tp_target_pct <= 0:
        raise ValueError("tp_target_pct must be positive")

    price = market_rules.current_price
    worst_protection_price = _worst_full_size_protection_price(
        side=side,
        current_price=price,
        stop_loss_fraction=stop_loss_fraction,
        tp_target_pct=tp_target_pct,
    )
    target_quantity = _round_up_to_step(target / price, market_rules.qty_step)
    min_entry_quantity = _round_up_to_step(
        market_rules.min_notional / price,
        market_rules.qty_step,
    )
    min_protection_quantity = _round_up_to_step(
        market_rules.min_notional / worst_protection_price,
        market_rules.qty_step,
    )
    computed_quantity = max(
        target_quantity,
        min_entry_quantity,
        min_protection_quantity,
        market_rules.min_qty,
    )
    computed_quantity = _round_up_to_step(computed_quantity, market_rules.qty_step)
    estimated_notional = computed_quantity * price
    estimated_protection_notional = computed_quantity * worst_protection_price
    suggested_quantity = max(min_entry_quantity, min_protection_quantity, market_rules.min_qty)
    suggested_quantity = _round_up_to_step(suggested_quantity, market_rules.qty_step)
    suggested_minimum_notional = suggested_quantity * price

    validation = NotionalSizingValidation(
        entry_quantity_valid=computed_quantity >= market_rules.min_qty
        and computed_quantity % market_rules.qty_step == 0,
        entry_notional_valid=estimated_notional >= market_rules.min_notional,
        protection_quantity_valid=computed_quantity >= market_rules.min_qty
        and computed_quantity % market_rules.qty_step == 0,
        protection_notional_valid=estimated_protection_notional >= market_rules.min_notional,
        max_notional_valid=(
            max_notional_usdt is None
            or estimated_notional <= Decimal(str(max_notional_usdt))
        ),
        market_rules_fresh=market_rules.freshness == "fresh",
    )
    blockers: list[str] = []
    warnings: list[str] = []
    if not validation.entry_quantity_valid:
        blockers.append("computed_quantity_below_min_qty_or_not_step_aligned")
    if not validation.entry_notional_valid:
        blockers.append("computed_entry_notional_below_min_notional")
    if not validation.protection_quantity_valid:
        blockers.append("computed_protection_quantity_below_min_qty_or_not_step_aligned")
    if not validation.protection_notional_valid:
        blockers.append("computed_protection_notional_below_min_notional")
    if not validation.max_notional_valid:
        blockers.append("computed_notional_exceeds_owner_max_notional")
    if not validation.market_rules_fresh:
        warnings.append("market_rules_not_fresh")

    return NotionalSizingResult(
        status="blocked" if blockers else "valid",
        symbol=symbol,
        side=side,
        target_notional_usdt=target,
        computed_quantity=computed_quantity,
        estimated_notional_usdt=estimated_notional,
        estimated_worst_protection_notional_usdt=estimated_protection_notional,
        max_notional_usdt=max_notional_usdt,
        suggested_minimum_notional_usdt=suggested_minimum_notional,
        suggested_quantity=suggested_quantity,
        market_rule_snapshot=market_rules,
        validation=validation,
        blockers=blockers,
        warnings=warnings,
    )


def validate_fixed_quantity_scope(
    *,
    symbol: str,
    side: Literal["long", "short"],
    quantity: Decimal,
    market_rules: ContractMarketRules,
    max_notional_usdt: Decimal | None = None,
    stop_loss_fraction: Decimal = Decimal("0.01"),
    tp_target_pct: Decimal = Decimal("1.0"),
) -> NotionalSizingResult:
    """Validate an Owner-provided quantity and return suggested repair values."""

    quantity_value = Decimal(str(quantity))
    target_notional = quantity_value * market_rules.current_price
    result = compute_notional_sizing(
        symbol=symbol,
        side=side,
        target_notional_usdt=target_notional,
        market_rules=market_rules,
        max_notional_usdt=max_notional_usdt,
        stop_loss_fraction=stop_loss_fraction,
        tp_target_pct=tp_target_pct,
    )
    if result.computed_quantity == quantity_value:
        return result
    worst_protection_notional = quantity_value * _worst_full_size_protection_price(
        side=side,
        current_price=market_rules.current_price,
        stop_loss_fraction=stop_loss_fraction,
        tp_target_pct=tp_target_pct,
    )
    fixed_validation = NotionalSizingValidation(
        entry_quantity_valid=quantity_value >= market_rules.min_qty
        and quantity_value % market_rules.qty_step == 0,
        entry_notional_valid=target_notional >= market_rules.min_notional,
        protection_quantity_valid=quantity_value >= market_rules.min_qty
        and quantity_value % market_rules.qty_step == 0,
        protection_notional_valid=worst_protection_notional
        >= market_rules.min_notional,
        max_notional_valid=(
            max_notional_usdt is None
            or target_notional <= Decimal(str(max_notional_usdt))
        ),
        market_rules_fresh=market_rules.freshness == "fresh",
    )
    blockers = [*result.blockers, "requested_quantity_below_market_rule_minimum"]
    if not fixed_validation.entry_quantity_valid:
        blockers.append("requested_quantity_below_min_qty_or_not_step_aligned")
    if not fixed_validation.entry_notional_valid:
        blockers.append("requested_entry_notional_below_min_notional")
    if not fixed_validation.protection_notional_valid:
        blockers.append("requested_protection_notional_below_min_notional")
    if not fixed_validation.max_notional_valid:
        blockers.append("requested_notional_exceeds_owner_max_notional")
    return result.model_copy(
        update={
            "status": "blocked",
            "computed_quantity": quantity_value,
            "estimated_notional_usdt": target_notional,
            "estimated_worst_protection_notional_usdt": worst_protection_notional,
            "validation": fixed_validation,
            "blockers": _dedupe(blockers),
        }
    )


def _round_up_to_step(value: Decimal, step: Decimal) -> Decimal:
    units = (Decimal(str(value)) / step).to_integral_value(rounding=ROUND_CEILING)
    return units * step


def _worst_full_size_protection_price(
    *,
    side: Literal["long", "short"],
    current_price: Decimal,
    stop_loss_fraction: Decimal,
    tp_target_pct: Decimal,
) -> Decimal:
    if side == "long":
        return current_price * (Decimal("1") - stop_loss_fraction)
    return current_price * (Decimal("1") - (tp_target_pct / Decimal("100")))


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
