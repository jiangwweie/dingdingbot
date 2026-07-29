"""Pure slot-aware Cross-margin sizing for one immutable CapacityClaim."""

from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class CapacitySizingStatus(StrEnum):
    SELECTED = "selected"
    COUNT_EXHAUSTED = "count_exhausted"
    MARGIN_EXHAUSTED = "margin_exhausted"
    VENUE_MINIMUM_UNMET = "venue_minimum_unmet"
    EXIT_PLAN_UNEXECUTABLE = "exit_plan_unexecutable"
    INVALID_FACTS = "invalid_facts"


class CapacitySizingRequest(BaseModel):
    """All typed facts used by the deterministic pre-entry sizing decision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    total_wallet_balance: Decimal
    total_margin_balance: Decimal
    total_initial_margin: Decimal
    available_margin: Decimal
    active_ticket_count: int
    max_concurrent_tickets: int
    planned_stop_risk_fraction: Decimal
    max_initial_margin_utilization: Decimal
    permitted_max_leverage: int
    configured_leverage: int
    entry_reference_price: Decimal
    initial_stop_price: Decimal
    quantity_step: Decimal
    min_quantity: Decimal
    min_notional: Decimal
    tp1_quantity_fraction: Decimal

    @field_validator(
        "total_wallet_balance",
        "total_margin_balance",
        "total_initial_margin",
        "available_margin",
    )
    @classmethod
    def _require_finite_nonnegative(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value < 0:
            raise ValueError("account sizing facts must be finite and nonnegative")
        return value

    @field_validator(
        "entry_reference_price",
        "initial_stop_price",
        "quantity_step",
        "min_quantity",
        "min_notional",
    )
    @classmethod
    def _require_finite_positive(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0:
            raise ValueError("sizing prices, rules, and ratios must be finite and positive")
        return value

    @field_validator("planned_stop_risk_fraction", "max_initial_margin_utilization")
    @classmethod
    def _require_fraction(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0 or value > 1:
            raise ValueError("sizing policy fractions must be in (0, 1]")
        return value

    @field_validator("tp1_quantity_fraction")
    @classmethod
    def _require_tp1_fraction(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0 or value >= 1:
            raise ValueError("TP1 quantity fraction must be in (0, 1)")
        return value

    @field_validator(
        "active_ticket_count",
        "max_concurrent_tickets",
        "permitted_max_leverage",
        "configured_leverage",
    )
    @classmethod
    def _require_nonnegative_or_positive_integer(cls, value: int, info: object) -> int:
        if isinstance(value, bool):
            raise ValueError(  # noqa: TRY004 - Pydantic must surface a ValidationError.
                "sizing count and leverage values must be integers"
            )
        field_name = getattr(info, "field_name", "")
        if value < 0 or (field_name != "active_ticket_count" and value <= 0):
            raise ValueError("sizing count and leverage values are invalid")
        return value

    @model_validator(mode="after")
    def _validate_sizing_facts(self) -> CapacitySizingRequest:
        if self.initial_stop_price == self.entry_reference_price:
            raise ValueError("initial stop must differ from entry reference")
        return self


class CapacitySizingSelection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    remaining_slots: int
    planned_stop_risk_budget: Decimal
    remaining_policy_margin: Decimal
    remaining_executable_margin: Decimal
    ticket_margin_budget: Decimal
    risk_quantity: Decimal
    required_leverage: int
    selected_leverage: int
    configured_leverage: int
    leverage_change_required: bool
    quantity: Decimal
    notional: Decimal
    reserved_margin: Decimal
    planned_stop_risk: Decimal
    tp1_quantity: Decimal
    runner_quantity: Decimal


class CapacitySizingDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: CapacitySizingStatus
    selected: CapacitySizingSelection | None

    @model_validator(mode="after")
    def _validate_shape(self) -> CapacitySizingDecision:
        if (self.status is CapacitySizingStatus.SELECTED) != (self.selected is not None):
            raise ValueError("selected sizing decisions require exactly one candidate")
        return self


def select_capacity_candidate(request: CapacitySizingRequest) -> CapacitySizingDecision:
    """Select one safe candidate without I/O, repositories, or mutable state."""

    if request.active_ticket_count >= request.max_concurrent_tickets:
        return _refused(CapacitySizingStatus.COUNT_EXHAUSTED)
    if request.configured_leverage > request.permitted_max_leverage:
        return _refused(CapacitySizingStatus.INVALID_FACTS)

    remaining_slots = request.max_concurrent_tickets - request.active_ticket_count
    planned_stop_risk_budget = (
        request.total_wallet_balance * request.planned_stop_risk_fraction
    )
    account_initial_margin_limit = (
        request.total_margin_balance * request.max_initial_margin_utilization
    )
    remaining_policy_margin = max(
        account_initial_margin_limit - request.total_initial_margin,
        Decimal(0),
    )
    remaining_executable_margin = min(
        request.available_margin,
        remaining_policy_margin,
    )
    if (
        planned_stop_risk_budget <= 0
        or remaining_executable_margin <= 0
    ):
        return _refused(CapacitySizingStatus.MARGIN_EXHAUSTED)
    ticket_margin_budget = remaining_executable_margin
    risk_per_unit = abs(request.entry_reference_price - request.initial_stop_price)
    risk_quantity = _floor_to_step(
        planned_stop_risk_budget / risk_per_unit,
        request.quantity_step,
    )
    if risk_quantity <= 0:
        return _refused(CapacitySizingStatus.VENUE_MINIMUM_UNMET)
    risk_target_notional = risk_quantity * request.entry_reference_price
    required_leverage = int(
        (risk_target_notional / ticket_margin_budget).to_integral_value(
            rounding=ROUND_CEILING
        )
    )
    leverages = (request.configured_leverage,)
    candidates: list[CapacitySizingSelection] = []
    venue_minimum_unmet = False
    exit_plan_unexecutable = False
    for leverage in leverages:
        candidate = _evaluate_candidate(
            request=request,
            remaining_slots=remaining_slots,
            planned_stop_risk_budget=planned_stop_risk_budget,
            remaining_policy_margin=remaining_policy_margin,
            remaining_executable_margin=remaining_executable_margin,
            ticket_margin_budget=ticket_margin_budget,
            risk_quantity=risk_quantity,
            required_leverage=required_leverage,
            leverage=leverage,
        )
        if isinstance(candidate, CapacitySizingSelection):
            candidates.append(candidate)
        elif candidate is CapacitySizingStatus.VENUE_MINIMUM_UNMET:
            venue_minimum_unmet = True
        elif candidate is CapacitySizingStatus.EXIT_PLAN_UNEXECUTABLE:
            exit_plan_unexecutable = True
    if not candidates:
        if exit_plan_unexecutable:
            return _refused(CapacitySizingStatus.EXIT_PLAN_UNEXECUTABLE)
        if venue_minimum_unmet:
            return _refused(CapacitySizingStatus.VENUE_MINIMUM_UNMET)
        return _refused(CapacitySizingStatus.INVALID_FACTS)

    full_target = [candidate for candidate in candidates if candidate.quantity == risk_quantity]
    selected = (
        min(full_target, key=lambda candidate: candidate.selected_leverage)
        if full_target
        else min(
            candidates,
            key=lambda candidate: (
                -candidate.planned_stop_risk,
                candidate.selected_leverage,
            ),
        )
    )
    return CapacitySizingDecision(
        status=CapacitySizingStatus.SELECTED,
        selected=selected,
    )


def _evaluate_candidate(
    *,
    request: CapacitySizingRequest,
    remaining_slots: int,
    planned_stop_risk_budget: Decimal,
    remaining_policy_margin: Decimal,
    remaining_executable_margin: Decimal,
    ticket_margin_budget: Decimal,
    risk_quantity: Decimal,
    required_leverage: int,
    leverage: int,
) -> CapacitySizingSelection | CapacitySizingStatus:
    margin_quantity = _floor_to_step(
        ticket_margin_budget * Decimal(leverage) / request.entry_reference_price,
        request.quantity_step,
    )
    quantity = min(risk_quantity, margin_quantity)
    notional = quantity * request.entry_reference_price
    planned_stop_risk = quantity * abs(
        request.entry_reference_price - request.initial_stop_price
    )
    if (
        quantity < request.min_quantity
        or notional < request.min_notional
        or planned_stop_risk <= 0
    ):
        return CapacitySizingStatus.VENUE_MINIMUM_UNMET
    tp1_quantity = _floor_to_step(
        quantity * request.tp1_quantity_fraction,
        request.quantity_step,
    )
    runner_quantity = quantity - tp1_quantity
    if tp1_quantity <= 0 or runner_quantity < request.min_quantity:
        return CapacitySizingStatus.EXIT_PLAN_UNEXECUTABLE
    return CapacitySizingSelection(
        remaining_slots=remaining_slots,
        planned_stop_risk_budget=planned_stop_risk_budget,
        remaining_policy_margin=remaining_policy_margin,
        remaining_executable_margin=remaining_executable_margin,
        ticket_margin_budget=ticket_margin_budget,
        risk_quantity=risk_quantity,
        required_leverage=required_leverage,
        selected_leverage=leverage,
        configured_leverage=request.configured_leverage,
        leverage_change_required=False,
        quantity=quantity,
        notional=notional,
        reserved_margin=notional / Decimal(leverage),
        planned_stop_risk=planned_stop_risk,
        tp1_quantity=tp1_quantity,
        runner_quantity=runner_quantity,
    )


def _floor_to_step(value: Decimal, step: Decimal) -> Decimal:
    if value <= 0:
        return Decimal(0)
    return (value / step).to_integral_value(rounding=ROUND_FLOOR) * step


def _refused(status: CapacitySizingStatus) -> CapacitySizingDecision:
    return CapacitySizingDecision(status=status, selected=None)
