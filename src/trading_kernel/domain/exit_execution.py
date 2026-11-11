"""Pure, versioned actual-fill pricing and executable TP quantity contracts."""

from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from src.trading_kernel.domain.exit_policy import ExitProfile

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class ExitPlanUnexecutable(ValueError):
    """A specific conservative venue/plan condition failed."""


class TpQuantityPolicy(StrEnum):
    TARGET_FLOOR = "target_floor"
    TARGET_FLOOR_THEN_MINIMUM = "target_floor_then_minimum"


class ExitExecutionPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    price_basis: Literal["complete_entry_vwap"]
    quantity_policy: TpQuantityPolicy
    max_actual_fraction: Decimal

    @model_validator(mode="after")
    def _validate_cap(self) -> ExitExecutionPolicy:
        cap = self.max_actual_fraction
        if not cap.is_finite() or not Decimal(0) < cap <= 1:
            raise ValueError("maximum actual fraction must be in (0, 1]")
        if (
            self.quantity_policy is TpQuantityPolicy.TARGET_FLOOR_THEN_MINIMUM
            and cap > Decimal(".5")
        ):
            raise ValueError("minimum-lift fraction cap cannot exceed 50%")
        return self


class ExitOrderRules(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    quantity_step: Decimal
    min_quantity: Decimal
    min_notional: Decimal
    max_quantity: Decimal
    price_tick: Decimal
    min_price: Decimal
    max_price: Decimal
    runner_quantity_step: Decimal
    runner_min_quantity: Decimal
    runner_max_quantity: Decimal
    observed_at_ms: int
    valid_until_ms: int

    @field_validator(
        "quantity_step",
        "min_quantity",
        "min_notional",
        "max_quantity",
        "price_tick",
        "min_price",
        "max_price",
        "runner_quantity_step",
        "runner_min_quantity",
        "runner_max_quantity",
    )
    @classmethod
    def _positive_finite(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0:
            raise ValueError("exit rules must be finite and positive")
        return value

    @model_validator(mode="after")
    def _valid(self) -> ExitOrderRules:
        if self.observed_at_ms <= 0 or self.valid_until_ms <= self.observed_at_ms:
            raise ValueError("exit rule validity interval is invalid")
        if (
            self.min_price > self.max_price
            or self.min_quantity > self.max_quantity
            or self.runner_min_quantity > self.runner_max_quantity
        ):
            raise ValueError("exit quantity rule range is invalid")
        return self


class ExitQuantities(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    target_floor_quantity: Decimal
    minimum_quantity: Decimal
    tp_quantity: Decimal
    runner_quantity: Decimal
    actual_fraction: Decimal
    minimum_lifted: bool


def calculate_tp_price(
    *,
    side: Literal["long", "short"],
    entry_price: Decimal,
    initial_stop: Decimal,
    multiple: Decimal,
    price_tick: Decimal,
) -> Decimal:
    if any(
        not v.is_finite() or v <= 0
        for v in (entry_price, initial_stop, multiple, price_tick)
    ):
        raise ExitPlanUnexecutable("price_invalid")
    if (side == "long" and initial_stop >= entry_price) or (
        side == "short" and initial_stop <= entry_price
    ):
        raise ExitPlanUnexecutable("initial_r_invalid")
    distance = abs(entry_price - initial_stop) * multiple
    price = entry_price + distance if side == "long" else entry_price - distance
    rounding = ROUND_CEILING if side == "long" else ROUND_FLOOR
    price = (price / price_tick).to_integral_value(rounding=rounding) * price_tick
    if price <= 0:
        raise ExitPlanUnexecutable("price_invalid")
    return price


def calculate_exit_quantities(
    *,
    quantity: Decimal,
    tp_price: Decimal,
    stop_price: Decimal,
    target_fraction: Decimal,
    policy: TpQuantityPolicy,
    max_fraction: Decimal,
    rules: ExitOrderRules,
    now_ms: int,
) -> ExitQuantities:
    if not rules.observed_at_ms <= now_ms < rules.valid_until_ms:
        raise ExitPlanUnexecutable("rule_stale")
    if any(
        not v.is_finite() or v <= 0
        for v in (quantity, tp_price, stop_price, target_fraction, max_fraction)
    ):
        raise ExitPlanUnexecutable("invalid_facts")
    if target_fraction >= 1 or max_fraction > 1:
        raise ExitPlanUnexecutable("fraction_invalid")
    if policy is TpQuantityPolicy.TARGET_FLOOR_THEN_MINIMUM and max_fraction > Decimal(
        ".5"
    ):
        raise ExitPlanUnexecutable("fraction_cap")
    step = rules.quantity_step
    if (
        quantity % step != 0
        or quantity % rules.runner_quantity_step != 0
        or tp_price % rules.price_tick != 0
    ):
        raise ExitPlanUnexecutable("step_or_tick")
    if (
        not rules.min_price <= tp_price <= rules.max_price
        or not rules.min_price <= stop_price <= rules.max_price
    ):
        raise ExitPlanUnexecutable("price_range")
    floor = (quantity * target_fraction / step).to_integral_value(
        rounding=ROUND_FLOOR
    ) * step
    minimum = (
        max(step, rules.min_quantity, rules.min_notional / tp_price) / step
    ).to_integral_value(rounding=ROUND_CEILING) * step
    tp = (
        max(floor, minimum)
        if policy is TpQuantityPolicy.TARGET_FLOOR_THEN_MINIMUM
        else floor
    )
    if tp <= 0:
        raise ExitPlanUnexecutable("zero")
    if tp / quantity > max_fraction:
        raise ExitPlanUnexecutable("fraction_cap")
    if tp < rules.min_quantity or tp * tp_price < rules.min_notional:
        raise ExitPlanUnexecutable("tp_minimum")
    runner = quantity - tp
    if (
        runner <= 0
        or runner < rules.runner_min_quantity
        or runner % rules.runner_quantity_step != 0
        or runner * stop_price < rules.min_notional
    ):
        raise ExitPlanUnexecutable("runner_size")
    if tp > rules.max_quantity or max(quantity, runner) > rules.runner_max_quantity:
        raise ExitPlanUnexecutable("max_quantity")
    return ExitQuantities(
        target_floor_quantity=floor,
        minimum_quantity=minimum,
        tp_quantity=tp,
        runner_quantity=runner,
        actual_fraction=tp / quantity,
        minimum_lifted=tp > floor,
    )


class EntryFill(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    trade_id: str
    quantity: Decimal
    price: Decimal

    @model_validator(mode="after")
    def _validate_fill(self) -> EntryFill:
        if not self.trade_id.strip() or any(
            not v.is_finite() or v <= 0 for v in (self.quantity, self.price)
        ):
            raise ValueError("entry fill requires exact identity and positive values")
        return self


class CompleteEntryFills(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    command_id: str
    exchange_order_id: str
    fills: tuple[EntryFill, ...]
    observed_at_ms: int

    @model_validator(mode="after")
    def _validate_set(self) -> CompleteEntryFills:
        if (
            not self.command_id.strip()
            or not self.exchange_order_id.strip()
            or not self.fills
            or self.observed_at_ms <= 0
        ):
            raise ValueError("complete entry fills require command, order and fills")
        if len({f.trade_id for f in self.fills}) != len(self.fills):
            raise ValueError("complete entry fills must be unique")
        return self

    @property
    def quantity(self) -> Decimal:
        return sum((f.quantity for f in self.fills), Decimal(0))

    @property
    def vwap(self) -> Decimal:
        return (
            sum((f.quantity * f.price for f in self.fills), Decimal(0)) / self.quantity
        )


class PostFillExitPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str
    position_side: Literal["long", "short"]
    entry_price: Decimal
    entry_quantity: Decimal
    initial_stop: Decimal
    initial_r_quote: Decimal
    entry_fills: CompleteEntryFills
    profile_id: str
    profile_hash: str
    binding_id: str
    binding_revision: int
    management_revision: int
    target_multiple: Decimal
    actual_multiple: Decimal
    target_fraction: Decimal
    execution: ExitExecutionPolicy
    tp_price: Decimal
    quantities: ExitQuantities
    rules: ExitOrderRules
    created_at_ms: int

    @model_validator(mode="after")
    def _validate_plan(self) -> PostFillExitPlan:
        if not all(
            s.strip() for s in (self.ticket_id, self.profile_id, self.binding_id)
        ):
            raise ValueError("post-fill plan identities are required")
        if (
            min(self.binding_revision, self.management_revision, self.created_at_ms)
            <= 0
        ):
            raise ValueError("post-fill plan revisions and time must be positive")
        if (
            self.entry_quantity != self.entry_fills.quantity
            or self.entry_price != self.entry_fills.vwap
        ):
            raise ValueError("post-fill plan differs from exact fills")
        if (
            self.initial_r_quote
            != self.entry_quantity * abs(self.entry_price - self.initial_stop)
            or self.initial_r_quote <= 0
        ):
            raise ValueError("post-fill plan initial risk differs")
        if self.tp_price != calculate_tp_price(
            side=self.position_side,
            entry_price=self.entry_price,
            initial_stop=self.initial_stop,
            multiple=self.target_multiple,
            price_tick=self.rules.price_tick,
        ):
            raise ValueError("post-fill plan TP price differs from exact R")
        expected = calculate_exit_quantities(
            quantity=self.entry_quantity,
            tp_price=self.tp_price,
            stop_price=self.initial_stop,
            target_fraction=self.target_fraction,
            policy=self.execution.quantity_policy,
            max_fraction=self.execution.max_actual_fraction,
            rules=self.rules,
            now_ms=self.created_at_ms,
        )
        if self.quantities != expected or self.actual_multiple != abs(
            self.tp_price - self.entry_price
        ) / abs(self.entry_price - self.initial_stop):
            raise ValueError(
                "post-fill quantity or multiple differs from executable plan"
            )
        return self


def build_post_fill_exit_plan(
    *,
    ticket_id: str,
    entry_fills: CompleteEntryFills,
    quantity: Decimal,
    initial_stop: Decimal,
    profile: ExitProfile,
    binding_id: str,
    binding_revision: int,
    management_revision: int,
    rules: ExitOrderRules,
    now_ms: int,
) -> PostFillExitPlan:
    if profile.execution is None:
        raise ExitPlanUnexecutable("explicit_execution_required")
    if entry_fills.quantity != quantity or entry_fills.observed_at_ms > now_ms:
        raise ExitPlanUnexecutable("entry_fill_conflict")
    fills = entry_fills.model_copy(
        update={"fills": tuple(sorted(entry_fills.fills, key=lambda f: f.trade_id))}
    )
    entry = fills.vwap
    tp = calculate_tp_price(
        side=profile.position_side,
        entry_price=entry,
        initial_stop=initial_stop,
        multiple=profile.tp1.reward_multiple,
        price_tick=rules.price_tick,
    )
    quantities = calculate_exit_quantities(
        quantity=quantity,
        tp_price=tp,
        stop_price=initial_stop,
        target_fraction=profile.tp1.quantity_fraction,
        policy=profile.execution.quantity_policy,
        max_fraction=profile.execution.max_actual_fraction,
        rules=rules,
        now_ms=now_ms,
    )
    return PostFillExitPlan(
        ticket_id=ticket_id,
        position_side=profile.position_side,
        entry_price=entry,
        entry_quantity=quantity,
        initial_stop=initial_stop,
        initial_r_quote=quantity * abs(entry - initial_stop),
        entry_fills=fills,
        profile_id=profile.exit_profile_id,
        profile_hash=profile.semantic_hash(),
        binding_id=binding_id,
        binding_revision=binding_revision,
        management_revision=management_revision,
        target_multiple=profile.tp1.reward_multiple,
        actual_multiple=abs(tp - entry) / abs(entry - initial_stop),
        target_fraction=profile.tp1.quantity_fraction,
        execution=profile.execution,
        tp_price=tp,
        quantities=quantities,
        rules=rules,
        created_at_ms=now_ms,
    )


class TpFillEvidence(CompleteEntryFills):
    """Exact cumulative TP trade IDs, distinct from a complete ENTRY certificate."""
