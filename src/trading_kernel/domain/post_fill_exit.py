"""Immutable actual-fill exit terms, derived after initial protection is accepted."""

from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, Decimal, localcontext
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.domain.exit_policy import ExitProfile
from src.trading_kernel.domain.exit_quantity import (
    ExitQuantityRequest,
    select_exit_quantities,
)


class PostFillExitRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str
    exit_binding_id: str
    profile: ExitProfile
    quantity: Decimal
    average_fill_price: Decimal
    initial_stop_price: Decimal
    quantity_step: Decimal
    price_tick: Decimal
    min_quantity: Decimal
    min_notional: Decimal
    rules_digest: str
    rules_observed_at_ms: int
    rules_valid_until_ms: int
    created_at_ms: int
    reference_take_profit_price: Decimal | None = None
    reference_tp1_quantity: Decimal | None = None

    @field_validator("ticket_id", "exit_binding_id")
    @classmethod
    def _identity(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("post-fill exit requires exact identities")
        return value

    @field_validator("rules_digest")
    @classmethod
    def _digest(cls, value: str) -> str:
        if len(value) != 71 or not value.startswith("sha256:"):
            raise ValueError("post-fill rules require a sha256 digest")
        try:
            int(value[7:], 16)
        except ValueError as exc:
            raise ValueError("invalid rules digest") from exc
        return value

    @field_validator(
        "quantity",
        "average_fill_price",
        "initial_stop_price",
        "quantity_step",
        "price_tick",
        "min_quantity",
        "min_notional",
    )
    @classmethod
    def _positive(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0:
            raise ValueError(
                "post-fill prices, quantity and rules must be finite and positive"
            )
        return value

    @model_validator(mode="after")
    def _fresh(self) -> PostFillExitRequest:
        if (
            not 0
            < self.rules_observed_at_ms
            <= self.created_at_ms
            < self.rules_valid_until_ms
        ):
            raise ValueError("post-fill exit requires current rule facts")
        return self


class PostFillExitPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    request: PostFillExitRequest
    take_profit_price: Decimal
    tp1_quantity: Decimal
    runner_quantity: Decimal
    actual_fraction: Decimal
    minimum_raised: bool
    risk_quote: Decimal
    effective_reward_multiple: Decimal

    @model_validator(mode="after")
    def _verify_derivation(self) -> PostFillExitPlan:
        status, values = _derive(self.request)
        if status != "selected" or values is None:
            raise ValueError("post-fill plan does not have executable terms")
        actual = self.model_dump(mode="python", exclude={"request"})
        if actual != values:
            raise ValueError("post-fill plan differs from its immutable source facts")
        return self


class PostFillExitDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal[
        "selected",
        "stop_direction_invalid",
        "target_price_invalid",
        "exit_quantity_unexecutable",
    ]
    quantity_rejection: str | None = None
    plan: PostFillExitPlan | None = None

    @model_validator(mode="after")
    def _shape(self) -> PostFillExitDecision:
        if (self.status == "selected") != (self.plan is not None):
            raise ValueError("post-fill exit decision shape differs from status")
        return self


def _derive(request: PostFillExitRequest) -> tuple[str, dict[str, object] | None]:
    with localcontext() as context:
        context.prec = 60
        context.rounding = ROUND_HALF_EVEN
        return _derive_with_fixed_context(request)


def _derive_with_fixed_context(
    request: PostFillExitRequest,
) -> tuple[str, dict[str, object] | None]:
    entry = request.average_fill_price
    stop = request.initial_stop_price
    long = request.profile.position_side == "long"
    if (long and stop >= entry) or (not long and stop <= entry):
        return "stop_direction_invalid", None
    distance = abs(entry - stop)
    if request.profile.tp1.price_basis == "entry_reference":
        target = request.reference_take_profit_price
        reference_qty = request.reference_tp1_quantity
        if (
            target is None
            or reference_qty is None
            or not target.is_finite()
            or not reference_qty.is_finite()
            or reference_qty <= 0
        ):
            return "target_price_invalid", None
        fraction = request.profile.tp1.quantity_fraction
        quantity_rule = None
    else:
        raw = (
            entry
            + (distance if long else -distance) * request.profile.tp1.reward_multiple
        )
        target = (raw / request.price_tick).to_integral_value(
            rounding=ROUND_CEILING if long else ROUND_FLOOR
        ) * request.price_tick
        fraction = request.profile.tp1.quantity_fraction
        quantity_rule = request.profile.tp1.quantity_rule
    if target <= 0 or not Decimal(0) < fraction < Decimal(1):
        return "target_price_invalid", None
    split = select_exit_quantities(
        ExitQuantityRequest(
            total_quantity=request.quantity,
            quantity_step=request.quantity_step,
            min_quantity=request.min_quantity,
            min_notional=request.min_notional,
            take_profit_price=target,
            initial_stop_price=stop,
            target_fraction=fraction,
            quantity_rule=quantity_rule,
            frozen_tp1_quantity=request.reference_tp1_quantity
            if request.profile.tp1.price_basis == "entry_reference"
            else None,
        )
    )
    if split.selected is None:
        return "exit_quantity_unexecutable", {"quantity_rejection": split.status.value}
    return "selected", {
        "take_profit_price": target,
        "tp1_quantity": split.selected.tp1_quantity,
        "runner_quantity": split.selected.runner_quantity,
        "actual_fraction": split.selected.actual_fraction,
        "minimum_raised": split.selected.minimum_raised,
        "risk_quote": request.quantity * distance,
        "effective_reward_multiple": abs(target - entry) / distance,
    }


def build_post_fill_exit_plan(request: PostFillExitRequest) -> PostFillExitDecision:
    status, values = _derive(request)
    if status != "selected":
        if status == "exit_quantity_unexecutable":
            assert values is not None
            return PostFillExitDecision(
                status="exit_quantity_unexecutable",
                quantity_rejection=str(values["quantity_rejection"]),
            )
        if status == "stop_direction_invalid":
            return PostFillExitDecision(status="stop_direction_invalid")
        return PostFillExitDecision(status="target_price_invalid")
    assert values is not None
    return PostFillExitDecision(
        status="selected",
        plan=PostFillExitPlan.model_validate({"request": request, **values}),
    )
