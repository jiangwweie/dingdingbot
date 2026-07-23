"""Pure slot-aware Cross-margin sizing for one immutable CapacityClaim."""

from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class CapacitySizingStatus(StrEnum):
    SELECTED = "selected"
    COUNT_EXHAUSTED = "count_exhausted"
    MARGIN_EXHAUSTED = "margin_exhausted"
    VENUE_MINIMUM_UNMET = "venue_minimum_unmet"
    EXIT_PLAN_UNEXECUTABLE = "exit_plan_unexecutable"
    LIQUIDATION_PROOF_FAILED = "liquidation_proof_failed"
    INVALID_FACTS = "invalid_facts"


class MaintenanceMarginBracket(BaseModel):
    """One exact venue maintenance bracket, decoded before domain evaluation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    bracket_id: str
    notional_floor: Decimal
    notional_cap: Decimal | None
    maintenance_margin_rate: Decimal
    maintenance_amount: Decimal

    @field_validator("bracket_id", mode="before")
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("maintenance bracket identity must be non-blank")
        return normalized

    @field_validator("notional_floor", "maintenance_amount")
    @classmethod
    def _require_finite_nonnegative(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value < 0:
            raise ValueError("maintenance bracket values must be finite and nonnegative")
        return value

    @field_validator("notional_cap")
    @classmethod
    def _require_finite_cap(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and (not value.is_finite() or value <= 0):
            raise ValueError("maintenance bracket cap must be finite and positive")
        return value

    @field_validator("maintenance_margin_rate")
    @classmethod
    def _require_rate(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value < 0 or value >= 1:
            raise ValueError("maintenance margin rate must be finite in [0, 1)")
        return value

    @model_validator(mode="after")
    def _validate_range(self) -> "MaintenanceMarginBracket":
        if self.notional_cap is not None and self.notional_cap <= self.notional_floor:
            raise ValueError("maintenance bracket cap must exceed its floor")
        return self


class CapacitySizingRequest(BaseModel):
    """All typed facts used by the deterministic pre-entry sizing decision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    total_wallet_balance: Decimal
    total_margin_balance: Decimal
    total_initial_margin: Decimal
    total_maintenance_margin: Decimal
    available_margin: Decimal
    active_ticket_count: int
    max_concurrent_tickets: int
    planned_stop_risk_fraction: Decimal
    max_initial_margin_utilization: Decimal
    permitted_max_leverage: int
    configured_leverage: int
    instrument_has_open_position: bool
    entry_reference_price: Decimal
    initial_stop_price: Decimal
    quantity_step: Decimal
    min_quantity: Decimal
    min_notional: Decimal
    tp1_quantity_fraction: Decimal
    maintenance_margin_brackets: tuple[MaintenanceMarginBracket, ...]
    position_side: Literal["long", "short"]
    mark_price: Decimal
    min_liquidation_distance_to_stop_distance_ratio: Decimal

    @field_validator(
        "total_wallet_balance",
        "total_margin_balance",
        "total_initial_margin",
        "total_maintenance_margin",
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
        "mark_price",
        "min_liquidation_distance_to_stop_distance_ratio",
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
            raise ValueError("sizing count and leverage values must be integers")
        field_name = getattr(info, "field_name", "")
        if value < 0 or (field_name != "active_ticket_count" and value <= 0):
            raise ValueError("sizing count and leverage values are invalid")
        return value

    @model_validator(mode="after")
    def _validate_sizing_facts(self) -> "CapacitySizingRequest":
        if self.initial_stop_price == self.entry_reference_price:
            raise ValueError("initial stop must differ from entry reference")
        if (
            self.position_side == "long"
            and self.initial_stop_price >= self.entry_reference_price
        ) or (
            self.position_side == "short"
            and self.initial_stop_price <= self.entry_reference_price
        ):
            raise ValueError("initial stop must be on the protective side")
        bracket_ids = tuple(item.bracket_id for item in self.maintenance_margin_brackets)
        if not bracket_ids or len(set(bracket_ids)) != len(bracket_ids):
            raise ValueError("maintenance brackets must be non-empty and unique")
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
    maintenance_margin_bracket_id: str
    projected_liquidation_price: Decimal
    projected_liquidation_distance: Decimal
    projected_liquidation_distance_to_stop_distance_ratio: Decimal


class CapacitySizingDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: CapacitySizingStatus
    selected: CapacitySizingSelection | None

    @model_validator(mode="after")
    def _validate_shape(self) -> "CapacitySizingDecision":
        if (self.status is CapacitySizingStatus.SELECTED) != (self.selected is not None):
            raise ValueError("selected sizing decisions require exactly one candidate")
        return self


def select_capacity_candidate(request: CapacitySizingRequest) -> CapacitySizingDecision:
    """Select one safe candidate without I/O, repositories, or mutable state."""

    if request.active_ticket_count >= request.max_concurrent_tickets:
        return _refused(CapacitySizingStatus.COUNT_EXHAUSTED)
    if request.instrument_has_open_position and (
        request.configured_leverage > request.permitted_max_leverage
    ):
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
        Decimal("0"),
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
    ticket_margin_budget = remaining_executable_margin / Decimal(remaining_slots)
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
    leverages = (
        (request.configured_leverage,)
        if request.instrument_has_open_position
        else tuple(range(1, request.permitted_max_leverage + 1))
    )
    candidates: list[CapacitySizingSelection] = []
    venue_minimum_unmet = False
    exit_plan_unexecutable = False
    liquidation_proof_failed = False
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
        elif candidate is CapacitySizingStatus.LIQUIDATION_PROOF_FAILED:
            liquidation_proof_failed = True
    if not candidates:
        if liquidation_proof_failed:
            return _refused(CapacitySizingStatus.LIQUIDATION_PROOF_FAILED)
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
    bracket = _bracket_for_notional(request.maintenance_margin_brackets, notional)
    if bracket is None:
        return CapacitySizingStatus.INVALID_FACTS
    projected_price = _projected_liquidation_price(
        request=request,
        quantity=quantity,
        bracket=bracket,
    )
    if projected_price is None:
        return CapacitySizingStatus.LIQUIDATION_PROOF_FAILED
    stop_distance = abs(request.entry_reference_price - request.initial_stop_price)
    liquidation_distance = (
        request.initial_stop_price - projected_price
        if request.position_side == "long"
        else projected_price - request.initial_stop_price
    )
    ratio = liquidation_distance / stop_distance
    directional = (
        projected_price < request.initial_stop_price < request.entry_reference_price
        if request.position_side == "long"
        else request.entry_reference_price < request.initial_stop_price < projected_price
    )
    if (
        not directional
        or liquidation_distance < 0
        or ratio < request.min_liquidation_distance_to_stop_distance_ratio
    ):
        return CapacitySizingStatus.LIQUIDATION_PROOF_FAILED
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
        leverage_change_required=(
            not request.instrument_has_open_position
            and request.configured_leverage != leverage
        ),
        quantity=quantity,
        notional=notional,
        reserved_margin=notional / Decimal(leverage),
        planned_stop_risk=planned_stop_risk,
        tp1_quantity=tp1_quantity,
        runner_quantity=runner_quantity,
        maintenance_margin_bracket_id=bracket.bracket_id,
        projected_liquidation_price=projected_price,
        projected_liquidation_distance=liquidation_distance,
        projected_liquidation_distance_to_stop_distance_ratio=ratio,
    )


def _bracket_for_notional(
    brackets: tuple[MaintenanceMarginBracket, ...],
    notional: Decimal,
) -> MaintenanceMarginBracket | None:
    matches = tuple(
        bracket
        for bracket in brackets
        if notional >= bracket.notional_floor
        and (bracket.notional_cap is None or notional < bracket.notional_cap)
    )
    return matches[0] if len(matches) == 1 else None


def _projected_liquidation_price(
    *,
    request: CapacitySizingRequest,
    quantity: Decimal,
    bracket: MaintenanceMarginBracket,
) -> Decimal | None:
    maintenance_at_liquidation = (
        quantity * request.entry_reference_price * bracket.maintenance_margin_rate
        + bracket.maintenance_amount
    )
    if request.position_side == "long":
        denominator = quantity * (Decimal("1") - bracket.maintenance_margin_rate)
        numerator = (
            request.total_maintenance_margin
            + maintenance_at_liquidation
            - request.total_margin_balance
            + quantity * request.mark_price
        )
        projected = numerator / denominator
        return max(projected, Decimal("0"))
    denominator = quantity * (Decimal("1") + bracket.maintenance_margin_rate)
    numerator = (
        request.total_margin_balance
        + quantity * request.mark_price
        - request.total_maintenance_margin
        - maintenance_at_liquidation
    )
    if denominator <= 0:
        return None
    projected = numerator / denominator
    return projected if projected.is_finite() and projected > 0 else None


def _floor_to_step(value: Decimal, step: Decimal) -> Decimal:
    if value <= 0:
        return Decimal("0")
    return (value / step).to_integral_value(rounding=ROUND_FLOOR) * step


def _refused(status: CapacitySizingStatus) -> CapacitySizingDecision:
    return CapacitySizingDecision(status=status, selected=None)
