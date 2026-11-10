"""Pure executable TP1/runner sizing, independent of the ENTRY risk budget."""

from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class ExitQuantityRule(BaseModel):
    """Explicit opt-in to raising a target split to venue minimums."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    algorithm: Literal["target_floor_then_minimum_v1"] = "target_floor_then_minimum_v1"
    max_actual_fraction: Decimal

    @field_validator("max_actual_fraction")
    @classmethod
    def _validate_cap(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or not Decimal(0) < value <= Decimal("0.50"):
            raise ValueError("minimum-raised TP1 cap must be finite and in (0, 0.50]")
        return value


class ExitQuantityRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    total_quantity: Decimal
    quantity_step: Decimal
    min_quantity: Decimal
    min_notional: Decimal
    take_profit_price: Decimal
    initial_stop_price: Decimal
    target_fraction: Decimal
    quantity_rule: ExitQuantityRule | None = None
    max_quantity: Decimal | None = None
    frozen_tp1_quantity: Decimal | None = None

    @field_validator(
        "total_quantity",
        "quantity_step",
        "min_quantity",
        "min_notional",
        "take_profit_price",
        "initial_stop_price",
        "max_quantity", "frozen_tp1_quantity",
    )
    @classmethod
    def _positive_finite(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and (not value.is_finite() or value <= 0):
            raise ValueError("exit quantity facts must be finite and positive")
        return value

    @field_validator("target_fraction")
    @classmethod
    def _fraction(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or not Decimal(0) < value < Decimal(1):
            raise ValueError("TP1 target must be finite and in (0, 1)")
        return value

    @model_validator(mode="after")
    def _cap_covers_target(self) -> ExitQuantityRequest:
        if self.frozen_tp1_quantity is not None and self.quantity_rule is not None:
            raise ValueError("frozen TP1 quantity cannot enable minimum raising")
        if (
            self.quantity_rule is not None
            and self.target_fraction > self.quantity_rule.max_actual_fraction
        ):
            raise ValueError("TP1 target exceeds the actual-fraction cap")
        return self


class ExitQuantityStatus(StrEnum):
    SELECTED = "selected"
    TOTAL_NOT_STEP_ALIGNED = "total_not_step_aligned"
    TP_MIN_QUANTITY = "tp_min_quantity"
    TP_NOT_STEP_ALIGNED = "tp_not_step_aligned"
    TP_MIN_NOTIONAL = "tp_min_notional"
    TP_MAX_QUANTITY = "tp_max_quantity"
    FRACTION_CAP_EXCEEDED = "fraction_cap_exceeded"
    RUNNER_MIN_QUANTITY = "runner_min_quantity"
    RUNNER_MIN_NOTIONAL = "runner_min_notional"


class ExitQuantitySelection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    tp1_quantity: Decimal
    runner_quantity: Decimal
    actual_fraction: Decimal
    target_floor_quantity: Decimal
    minimum_executable_quantity: Decimal
    minimum_raised: bool


class ExitQuantityDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ExitQuantityStatus
    selected: ExitQuantitySelection | None = None

    @model_validator(mode="after")
    def _shape(self) -> ExitQuantityDecision:
        if (self.status is ExitQuantityStatus.SELECTED) != (self.selected is not None):
            raise ValueError("selected exit quantity decision requires a selection")
        return self


def select_exit_quantities(request: ExitQuantityRequest) -> ExitQuantityDecision:
    """Keep ENTRY size fixed and validate both conservative exit legs."""

    step = request.quantity_step
    if request.total_quantity % step:
        return ExitQuantityDecision(status=ExitQuantityStatus.TOTAL_NOT_STEP_ALIGNED)
    target_floor = (
        request.total_quantity * request.target_fraction / step
    ).to_integral_value(rounding=ROUND_FLOOR) * step
    if request.frozen_tp1_quantity is not None:
        target_floor = request.frozen_tp1_quantity
        if target_floor % step:
            return ExitQuantityDecision(status=ExitQuantityStatus.TP_NOT_STEP_ALIGNED)
    minimum = (
        max(
            step, request.min_quantity, request.min_notional / request.take_profit_price
        )
        / step
    ).to_integral_value(rounding=ROUND_CEILING) * step
    quantity = target_floor
    if request.quantity_rule is not None:
        quantity = max(quantity, minimum)
        # Multiplication avoids rounding a ratio at the exact cap boundary.
        if (
            quantity
            > request.total_quantity * request.quantity_rule.max_actual_fraction
        ):
            return ExitQuantityDecision(status=ExitQuantityStatus.FRACTION_CAP_EXCEEDED)
    if quantity <= 0 or quantity < request.min_quantity:
        return ExitQuantityDecision(status=ExitQuantityStatus.TP_MIN_QUANTITY)
    if request.max_quantity is not None and quantity > request.max_quantity:
        return ExitQuantityDecision(status=ExitQuantityStatus.TP_MAX_QUANTITY)
    if quantity * request.take_profit_price < request.min_notional:
        return ExitQuantityDecision(status=ExitQuantityStatus.TP_MIN_NOTIONAL)
    runner = request.total_quantity - quantity
    if runner <= 0 or runner < request.min_quantity:
        return ExitQuantityDecision(status=ExitQuantityStatus.RUNNER_MIN_QUANTITY)
    if runner * request.initial_stop_price < request.min_notional:
        return ExitQuantityDecision(status=ExitQuantityStatus.RUNNER_MIN_NOTIONAL)
    return ExitQuantityDecision(
        status=ExitQuantityStatus.SELECTED,
        selected=ExitQuantitySelection(
            tp1_quantity=quantity,
            runner_quantity=runner,
            actual_fraction=quantity / request.total_quantity,
            target_floor_quantity=target_floor,
            minimum_executable_quantity=minimum,
            minimum_raised=quantity > target_floor,
        ),
    )
