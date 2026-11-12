"""Wallet-based initial allocation and live account affordability, in quote units."""

from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

MARGIN_ALLOCATION_CONTRACT = "wallet_allocation_v1"


class EntryMarginCosts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    reference_price: Decimal
    margin_price: Decimal
    taker_fee_rate: Decimal
    opening_loss_per_unit: Decimal

    @model_validator(mode="after")
    def valid_costs(self) -> Self:
        values = (
            self.reference_price,
            self.margin_price,
            self.taker_fee_rate,
            self.opening_loss_per_unit,
        )
        if any(not v.is_finite() for v in values):
            raise ValueError("entry margin costs must be finite")
        if self.reference_price <= 0 or self.margin_price < self.reference_price:
            raise ValueError("entry margin price must cover reference price")
        if not 0 <= self.taker_fee_rate < 1 or self.opening_loss_per_unit < 0:
            raise ValueError("entry margin costs must be nonnegative")
        return self

    @property
    def cash_cost_per_unit(self) -> Decimal:
        return self.margin_price * self.taker_fee_rate + self.opening_loss_per_unit


def entry_margin_costs(
    *,
    reference_price: Decimal,
    best_bid: Decimal,
    best_ask: Decimal,
    mark_price: Decimal,
    position_side: str,
    taker_fee_rate: Decimal,
) -> EntryMarginCosts:
    if (
        position_side not in {"long", "short"}
        or min(best_bid, best_ask, mark_price) <= 0
        or best_bid > best_ask
    ):
        raise ValueError("invalid entry margin quote")
    return EntryMarginCosts(
        reference_price=reference_price,
        margin_price=max(reference_price, best_bid, best_ask, mark_price),
        taker_fee_rate=taker_fee_rate,
        opening_loss_per_unit=max(
            best_ask - mark_price if position_side == "long" else mark_price - best_bid,
            Decimal(0),
        ),
    )


class MarginAllocation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    contract: Literal["wallet_allocation_v1"] = "wallet_allocation_v1"
    wallet_balance: Decimal
    single_margin_fraction: Decimal
    single_margin_limit: Decimal
    costs: EntryMarginCosts

    @model_validator(mode="after")
    def validate_allocation(self) -> Self:
        if not self.wallet_balance.is_finite() or self.wallet_balance < 0:
            raise ValueError("invalid allocation wallet")
        if (
            not self.single_margin_fraction.is_finite()
            or not 0 < self.single_margin_fraction <= 1
        ):
            raise ValueError("invalid allocation fraction")
        if (
            self.single_margin_limit
            != self.wallet_balance * self.single_margin_fraction
        ):
            raise ValueError("allocation limit differs from wallet authority")
        return self


class MarginBudget(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    single_limit: Decimal
    available_limit: Decimal
    gross_remaining: Decimal
    existing_usage: Decimal


def margin_budget(
    *,
    wallet: Decimal,
    equity: Decimal,
    available: Decimal,
    initial_margin: Decimal,
    other_reserved: Decimal,
    single_fraction: Decimal,
    gross_fraction: Decimal,
) -> MarginBudget:
    usage = max(initial_margin, other_reserved)
    return MarginBudget(
        single_limit=wallet * single_fraction,
        available_limit=max(Decimal(0), min(available, equity - usage)),
        gross_remaining=max(Decimal(0), equity * gross_fraction - usage),
        existing_usage=usage,
    )


class MarginCheck(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    constraints: tuple[str, ...]
    costs: EntryMarginCosts
    reason: Literal[
        "allowed",
        "allocation_wallet_changed",
        "available_margin_insufficient",
        "gross_margin_limit",
    ]
    allocation_limit: Decimal
    required_margin: Decimal
    cash_cost: Decimal
    budget: MarginBudget


def check_entry_margin(
    *,
    allocation: MarginAllocation,
    reference_margin: Decimal,
    quantity: Decimal,
    leverage: int,
    wallet: Decimal,
    equity: Decimal,
    available: Decimal,
    initial_margin: Decimal,
    other_reserved: Decimal,
    gross_fraction: Decimal,
    costs: EntryMarginCosts,
) -> MarginCheck:
    budget = margin_budget(
        wallet=wallet,
        equity=equity,
        available=available,
        initial_margin=initial_margin,
        other_reserved=other_reserved,
        single_fraction=allocation.single_margin_fraction,
        gross_fraction=gross_fraction,
    )
    limit = min(allocation.single_margin_limit, budget.single_limit)
    required = max(reference_margin, quantity * costs.margin_price / Decimal(leverage))
    cash = quantity * costs.cash_cost_per_unit
    reason: Literal[
        "allowed",
        "allocation_wallet_changed",
        "available_margin_insufficient",
        "gross_margin_limit",
    ] = "allowed"
    if reference_margin > limit:
        reason = "allocation_wallet_changed"
    elif required + cash > budget.available_limit:
        reason = "available_margin_insufficient"
    elif required + gross_fraction * cash > budget.gross_remaining:
        reason = "gross_margin_limit"
    constraints = tuple(
        name
        for name, failed in (
            ("ticket_margin", reference_margin > limit),
            ("available_margin", required + cash > budget.available_limit),
            ("gross_margin", required + gross_fraction * cash > budget.gross_remaining),
        )
        if failed
    )
    return MarginCheck(
        constraints=constraints,
        costs=costs,
        reason=reason,
        allocation_limit=limit,
        required_margin=required,
        cash_cost=cash,
        budget=budget,
    )
