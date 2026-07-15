"""Pure account-level hard-cap risk and capacity decisions."""

from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AccountRiskPolicy(BaseModel):
    """Versioned account-level limits; strategy scope remains outside this model."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    risk_policy_version: str = Field(min_length=1)
    planned_stop_risk_fraction: Decimal = Field(gt=Decimal("0"), le=Decimal("1"))
    max_concurrent_positions: Literal[1, 2]
    max_portfolio_open_risk_fraction: Decimal = Field(
        gt=Decimal("0"), le=Decimal("1")
    )
    max_cluster_open_risk_fraction: Decimal = Field(gt=Decimal("0"), le=Decimal("1"))
    max_portfolio_initial_margin_fraction: Decimal = Field(
        gt=Decimal("0"), le=Decimal("1")
    )
    max_leverage: int = Field(ge=1, le=125)
    max_new_action_time_lanes: Literal[1]
    automatic_downsize_enabled: bool
    unknown_exposure_policy: Literal["global_fail_closed"]
    activation_state: Literal["shadow", "active"]

    @model_validator(mode="after")
    def _finite_fractions(self) -> "AccountRiskPolicy":
        fractions = (
            self.planned_stop_risk_fraction,
            self.max_portfolio_open_risk_fraction,
            self.max_cluster_open_risk_fraction,
            self.max_portfolio_initial_margin_fraction,
        )
        if not all(value.is_finite() for value in fractions):
            raise ValueError("account risk policy fractions must be finite")
        return self


class RiskClusterMembership(BaseModel):
    """Versioned instrument-to-risk-cluster membership input."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_instrument_id: str = Field(min_length=1)
    risk_cluster_id: str = Field(min_length=1)
    membership_role: Literal["primary", "secondary"] = "primary"


class CapacityDecision(BaseModel):
    """Pure sizing/capacity result for one proposed new Ticket."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    allowed_risk: Decimal = Decimal("0")
    intended_qty: Decimal = Decimal("0")
    selected_leverage: int | None = None
    reserved_margin: Decimal = Decimal("0")
    portfolio_risk_remaining: Decimal = Decimal("0")
    cluster_risk_remaining: Decimal = Decimal("0")
    portfolio_margin_remaining: Decimal = Decimal("0")
    blockers: tuple[str, ...] = ()


def decide_account_capacity(
    *,
    wallet_balance: Decimal,
    available_balance: Decimal,
    exchange_initial_margin: Decimal,
    unreflected_pending_margin: Decimal,
    existing_portfolio_held_risk: Decimal,
    existing_cluster_held_risk: Decimal,
    claimed_position_slots: int,
    instrument_already_claimed: bool,
    per_unit_stop_risk: Decimal,
    entry_reference_price: Decimal,
    min_qty: Decimal,
    qty_step: Decimal,
    min_notional: Decimal,
    exchange_max_leverage: int,
    policy: AccountRiskPolicy,
) -> CapacityDecision:
    """Apply hard caps and choose the smallest leverage sufficient for quantity."""

    values = (
        wallet_balance,
        available_balance,
        exchange_initial_margin,
        unreflected_pending_margin,
        existing_portfolio_held_risk,
        existing_cluster_held_risk,
        per_unit_stop_risk,
        entry_reference_price,
        min_qty,
        qty_step,
        min_notional,
    )
    if (
        not all(value.is_finite() for value in values)
        or wallet_balance <= 0
        or available_balance < 0
        or exchange_initial_margin < 0
        or unreflected_pending_margin < 0
        or existing_portfolio_held_risk < 0
        or existing_cluster_held_risk < 0
        or per_unit_stop_risk <= 0
        or entry_reference_price <= 0
        or min_qty <= 0
        or qty_step <= 0
        or min_notional <= 0
        or exchange_max_leverage < 1
    ):
        return _blocked("account_capacity_input_invalid")
    if instrument_already_claimed:
        return _blocked("account_instrument_already_claimed")
    if claimed_position_slots >= policy.max_concurrent_positions:
        return _blocked("max_concurrent_positions_reached")

    ticket_limit = wallet_balance * policy.planned_stop_risk_fraction
    portfolio_limit = wallet_balance * policy.max_portfolio_open_risk_fraction
    cluster_limit = wallet_balance * policy.max_cluster_open_risk_fraction
    portfolio_remaining = max(
        Decimal("0"), portfolio_limit - existing_portfolio_held_risk
    )
    cluster_remaining = max(Decimal("0"), cluster_limit - existing_cluster_held_risk)
    if portfolio_remaining <= 0:
        return _blocked(
            "portfolio_open_risk_capacity_exhausted",
            portfolio_risk_remaining=portfolio_remaining,
            cluster_risk_remaining=cluster_remaining,
        )
    if cluster_remaining <= 0:
        return _blocked(
            "risk_cluster_open_risk_capacity_exhausted",
            portfolio_risk_remaining=portfolio_remaining,
            cluster_risk_remaining=cluster_remaining,
        )
    allowed_risk = min(ticket_limit, portfolio_remaining, cluster_remaining)

    portfolio_margin_limit = (
        wallet_balance * policy.max_portfolio_initial_margin_fraction
    )
    portfolio_margin_remaining = max(
        Decimal("0"),
        portfolio_margin_limit
        - exchange_initial_margin
        - unreflected_pending_margin,
    )
    action_time_margin_remaining = min(
        available_balance, portfolio_margin_remaining
    )
    minimum_qty = _ceil_to_step(
        max(min_qty, min_notional / entry_reference_price), qty_step
    )
    if minimum_qty * per_unit_stop_risk > allowed_risk:
        return _blocked(
            "minimum_executable_quantity_exceeds_available_stop_risk_capacity",
            allowed_risk=allowed_risk,
            portfolio_risk_remaining=portfolio_remaining,
            cluster_risk_remaining=cluster_remaining,
            portfolio_margin_remaining=portfolio_margin_remaining,
        )

    permitted_leverage = min(policy.max_leverage, exchange_max_leverage)
    minimum_notional = minimum_qty * entry_reference_price
    if (
        action_time_margin_remaining <= 0
        or minimum_notional / Decimal(permitted_leverage)
        > action_time_margin_remaining
    ):
        return _blocked(
            "minimum_executable_quantity_exceeds_available_margin_capacity",
            allowed_risk=allowed_risk,
            portfolio_risk_remaining=portfolio_remaining,
            cluster_risk_remaining=cluster_remaining,
            portfolio_margin_remaining=portfolio_margin_remaining,
        )

    risk_qty = _floor_to_step(allowed_risk / per_unit_stop_risk, qty_step)
    risk_notional = risk_qty * entry_reference_price
    selected_leverage = max(
        1,
        _ceil_integer(risk_notional / action_time_margin_remaining),
    )
    selected_leverage = min(selected_leverage, permitted_leverage)
    margin_qty = _floor_to_step(
        action_time_margin_remaining * Decimal(selected_leverage)
        / entry_reference_price,
        qty_step,
    )
    intended_qty = min(risk_qty, margin_qty)
    if intended_qty < minimum_qty:
        return _blocked(
            "minimum_executable_quantity_exceeds_available_margin_capacity",
            allowed_risk=allowed_risk,
            portfolio_risk_remaining=portfolio_remaining,
            cluster_risk_remaining=cluster_remaining,
            portfolio_margin_remaining=portfolio_margin_remaining,
        )
    return CapacityDecision(
        allowed_risk=allowed_risk,
        intended_qty=intended_qty,
        selected_leverage=selected_leverage,
        reserved_margin=(intended_qty * entry_reference_price)
        / Decimal(selected_leverage),
        portfolio_risk_remaining=portfolio_remaining,
        cluster_risk_remaining=cluster_remaining,
        portfolio_margin_remaining=portfolio_margin_remaining,
    )


def compute_directional_risk(
    *,
    side: Literal["long", "short"],
    actual_average_entry_price: Decimal,
    confirmed_stop_price: Decimal,
    position_qty: Decimal,
) -> Decimal:
    """Calculate downside-only price risk from actual entry to confirmed stop."""

    values = (actual_average_entry_price, confirmed_stop_price, position_qty)
    if not all(value.is_finite() for value in values):
        raise ValueError("directional risk inputs must be finite")
    if actual_average_entry_price <= 0 or confirmed_stop_price <= 0:
        raise ValueError("directional risk prices must be positive")
    qty = abs(position_qty)
    distance = (
        actual_average_entry_price - confirmed_stop_price
        if side == "long"
        else confirmed_stop_price - actual_average_entry_price
    )
    return max(Decimal("0"), distance) * qty


def _blocked(
    blocker: str,
    *,
    allowed_risk: Decimal = Decimal("0"),
    portfolio_risk_remaining: Decimal = Decimal("0"),
    cluster_risk_remaining: Decimal = Decimal("0"),
    portfolio_margin_remaining: Decimal = Decimal("0"),
) -> CapacityDecision:
    return CapacityDecision(
        allowed_risk=allowed_risk,
        portfolio_risk_remaining=portfolio_risk_remaining,
        cluster_risk_remaining=cluster_risk_remaining,
        portfolio_margin_remaining=portfolio_margin_remaining,
        blockers=(blocker,),
    )


def _floor_to_step(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_FLOOR) * step


def _ceil_to_step(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_CEILING) * step


def _ceil_integer(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_CEILING))
