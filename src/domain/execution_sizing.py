"""Pure dynamic execution sizing from planned Stop risk and account capacity."""

from __future__ import annotations

from decimal import Decimal, ROUND_CEILING
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.instrument_risk_identity import MAX_EXCHANGE_RULE_LEVERAGE


PLANNED_STOP_RISK_BASIS = "wallet_fraction_stop_distance_v1"


class ExecutionInstrumentRules(BaseModel):
    """Fresh executable price and exchange quantity/leverage constraints."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1)
    side: Literal["long", "short"]
    entry_reference_price: Decimal = Field(gt=Decimal("0"))
    min_qty: Decimal = Field(gt=Decimal("0"))
    qty_step: Decimal = Field(gt=Decimal("0"))
    min_notional: Decimal = Field(gt=Decimal("0"))
    exchange_max_leverage: int = Field(ge=1, le=MAX_EXCHANGE_RULE_LEVERAGE)
    source_fact_snapshot_id: str = Field(min_length=1)
    observed_at_ms: int = Field(gt=0)
    valid_until_ms: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_rules(self) -> "ExecutionInstrumentRules":
        values = (
            self.entry_reference_price,
            self.min_qty,
            self.qty_step,
            self.min_notional,
        )
        if not all(value.is_finite() for value in values):
            raise ValueError("instrument rule decimals must be finite")
        if self.valid_until_ms <= self.observed_at_ms:
            raise ValueError("instrument rules must expire after observation")
        return self


class ExecutionAccountCapacity(BaseModel):
    """Fresh account capital used separately for loss and margin capacity."""

    model_config = ConfigDict(frozen=True)

    total_wallet_balance: Decimal = Field(gt=Decimal("0"))
    available_balance: Decimal = Field(ge=Decimal("0"))
    source_fact_snapshot_id: str = Field(min_length=1)
    observed_at_ms: int = Field(gt=0)
    valid_until_ms: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_capacity(self) -> "ExecutionAccountCapacity":
        if not self.total_wallet_balance.is_finite():
            raise ValueError("wallet balance must be finite")
        if not self.available_balance.is_finite():
            raise ValueError("available balance must be finite")
        if self.valid_until_ms <= self.observed_at_ms:
            raise ValueError("account capacity must expire after observation")
        return self


class ExecutionSizingPolicy(BaseModel):
    """Versioned Owner policy for dynamic planned-risk sizing."""

    model_config = ConfigDict(frozen=True)

    planned_stop_risk_fraction: Decimal = Field(
        gt=Decimal("0"), le=Decimal("1")
    )
    max_initial_margin_utilization: Decimal = Field(
        gt=Decimal("0"), le=Decimal("1")
    )
    max_leverage: int = Field(ge=1, le=125)
    policy_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_policy(self) -> "ExecutionSizingPolicy":
        values = (
            self.planned_stop_risk_fraction,
            self.max_initial_margin_utilization,
        )
        if not all(value.is_finite() for value in values):
            raise ValueError("risk policy fractions must be finite")
        return self


class ExecutionSizingDecision(BaseModel):
    """One immutable decision reused by Ticket and every submit boundary."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    side: Literal["long", "short"]
    entry_reference_price: Decimal
    protective_stop_price: Decimal
    intended_qty: Decimal
    effective_notional: Decimal
    selected_leverage: int
    reserved_margin: Decimal
    planned_stop_risk_budget: Decimal
    planned_stop_risk: Decimal
    minimum_executable_quantity: Decimal
    pricing_source_fact_snapshot_id: str
    account_source_fact_snapshot_id: str
    policy_version: str
    risk_reservation_basis: str
    valid_until_ms: int


class ExecutionSizingDecisionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    decision: ExecutionSizingDecision | None = None
    blockers: tuple[str, ...] = ()
    minimum_executable_quantity: Decimal | None = None
    minimum_executable_notional: Decimal | None = None


def decide_execution_sizing(
    *,
    rules: ExecutionInstrumentRules,
    account: ExecutionAccountCapacity,
    policy: ExecutionSizingPolicy,
    protective_stop_price: Decimal,
    now_ms: int,
) -> ExecutionSizingDecisionResult:
    """Choose quantity and the lowest sufficient leverage inside Owner policy."""

    if account.valid_until_ms <= now_ms:
        return _blocked("execution_account_capacity_stale")
    if rules.valid_until_ms <= now_ms:
        return _blocked("execution_instrument_rules_stale")
    if not protective_stop_price.is_finite() or protective_stop_price <= 0:
        return _blocked("protective_stop_price_invalid")
    if rules.side == "long" and protective_stop_price >= rules.entry_reference_price:
        return _blocked("protective_stop_side_not_valid")
    if rules.side == "short" and protective_stop_price <= rules.entry_reference_price:
        return _blocked("protective_stop_side_not_valid")

    price = rules.entry_reference_price
    per_unit_stop_risk = abs(price - protective_stop_price)
    risk_budget = (
        account.total_wallet_balance * policy.planned_stop_risk_fraction
    )
    margin_capacity = (
        account.available_balance * policy.max_initial_margin_utilization
    )
    minimum_qty = _ceil_to_step(
        max(rules.min_qty, rules.min_notional / price), rules.qty_step
    )
    minimum_notional = minimum_qty * price
    minimum_risk = minimum_qty * per_unit_stop_risk

    if minimum_risk > risk_budget:
        return _blocked(
            "minimum_executable_quantity_exceeds_planned_stop_risk_budget",
            minimum_qty=minimum_qty,
            minimum_notional=minimum_notional,
        )

    permitted_max_leverage = min(
        policy.max_leverage, rules.exchange_max_leverage
    )
    if minimum_notional / Decimal(permitted_max_leverage) > margin_capacity:
        return _blocked(
            "minimum_executable_quantity_exceeds_margin_capacity",
            minimum_qty=minimum_qty,
            minimum_notional=minimum_notional,
        )

    risk_qty = _floor_to_step(
        risk_budget / per_unit_stop_risk, rules.qty_step
    )
    risk_notional = risk_qty * price
    required_leverage = max(
        1,
        _ceil_integer(risk_notional / margin_capacity)
        if margin_capacity > 0
        else permitted_max_leverage,
    )
    selected_leverage = min(required_leverage, permitted_max_leverage)
    margin_qty = _floor_to_step(
        margin_capacity * Decimal(selected_leverage) / price,
        rules.qty_step,
    )
    intended_qty = min(risk_qty, margin_qty)
    if intended_qty < minimum_qty:
        return _blocked(
            "minimum_executable_quantity_exceeds_margin_capacity",
            minimum_qty=minimum_qty,
            minimum_notional=minimum_notional,
        )

    effective_notional = intended_qty * price
    reserved_margin = effective_notional / Decimal(selected_leverage)
    planned_stop_risk = intended_qty * per_unit_stop_risk
    decision = ExecutionSizingDecision(
        symbol=rules.symbol,
        side=rules.side,
        entry_reference_price=price,
        protective_stop_price=protective_stop_price,
        intended_qty=intended_qty,
        effective_notional=effective_notional,
        selected_leverage=selected_leverage,
        reserved_margin=reserved_margin,
        planned_stop_risk_budget=risk_budget,
        planned_stop_risk=planned_stop_risk,
        minimum_executable_quantity=minimum_qty,
        pricing_source_fact_snapshot_id=rules.source_fact_snapshot_id,
        account_source_fact_snapshot_id=account.source_fact_snapshot_id,
        policy_version=policy.policy_version,
        risk_reservation_basis=PLANNED_STOP_RISK_BASIS,
        valid_until_ms=min(rules.valid_until_ms, account.valid_until_ms),
    )
    return ExecutionSizingDecisionResult(
        decision=decision,
        minimum_executable_quantity=minimum_qty,
        minimum_executable_notional=minimum_notional,
    )


def _blocked(
    blocker: str,
    *,
    minimum_qty: Decimal | None = None,
    minimum_notional: Decimal | None = None,
) -> ExecutionSizingDecisionResult:
    return ExecutionSizingDecisionResult(
        blockers=(blocker,),
        minimum_executable_quantity=minimum_qty,
        minimum_executable_notional=minimum_notional,
    )


def _floor_to_step(value: Decimal, step: Decimal) -> Decimal:
    if value <= 0 or step <= 0:
        return Decimal("0")
    return (value // step) * step


def _ceil_to_step(value: Decimal, step: Decimal) -> Decimal:
    if value <= 0 or step <= 0:
        return Decimal("0")
    units = (value / step).to_integral_value(rounding=ROUND_CEILING)
    return units * step


def _ceil_integer(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_CEILING))
