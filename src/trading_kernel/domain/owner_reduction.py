"""Pure, durable-intent decisions for an Owner reduction; never venue I/O.

Actions must be committed by the kernel with their state before dispatch. A
review outcome is not evidence of external Owner takeover. Flatness alone does
not settle a Ticket. No action here grants ENTRY or changes a TP fill history.
"""

from __future__ import annotations

from decimal import ROUND_FLOOR, Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.trading_kernel.domain.aggregate import AggregateStatus, TradeAggregate
from src.trading_kernel.domain.trade_management import ManagementMode


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def exact_decimals(cls, value: object) -> object:
        if isinstance(value, float):
            raise TypeError("financial values must be exact")
        return value


class OwnerReductionPhase(StrEnum):
    PREVIEWED = "previewed"
    TP_CANCELLING = "tp_cancelling"
    REDUCTION_PENDING = "reduction_pending"
    PROTECTION_PENDING = "protection_pending"
    WAIT_PRICE = "wait_price"
    BREAK_EVEN_PENDING = "break_even_pending"
    RUNNER_CONTINUING = "runner_continuing"
    RESTORE_REQUIRED = "restore_required"
    REVIEW_REQUIRED = "review_required"
    CLOSURE_PENDING = "closure_pending"
    REJECTED = "rejected"


class OwnerReductionFacts(_Frozen):
    ticket_id: str = Field(min_length=1)
    management_revision: int = Field(gt=0)
    management_mode: ManagementMode
    observed_at_ms: int = Field(gt=0)
    valid_until_ms: int = Field(gt=0)
    position_quantity: Decimal = Field(ge=0, allow_inf_nan=False)
    current_price: Decimal = Field(gt=0, allow_inf_nan=False)
    protection_order_id: str | None
    protected_quantity: Decimal = Field(ge=0, allow_inf_nan=False)
    stop_price: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    tp_order_id: str | None
    tp_filled_quantity: Decimal = Field(ge=0, allow_inf_nan=False)
    tp_state: Literal["open", "partial", "cancelled", "filled", "unknown", "absent"]
    reduction_state: Literal["not_sent", "working", "terminal", "rejected", "unknown"]
    reduction_filled_quantity: Decimal = Field(ge=0, allow_inf_nan=False)
    reduction_operation_id: str | None = None
    unresolved_other_command: bool
    stop_triggered: bool
    residual_orders: bool

    @model_validator(mode="after")
    def time_order(self) -> OwnerReductionFacts:
        if self.valid_until_ms <= self.observed_at_ms:
            raise ValueError("facts_validity_invalid")
        return self


class OwnerReductionPreview(_Frozen):
    ticket_id: str = Field(min_length=1)
    exit_policy_id: str = Field(min_length=1)
    exit_policy_semantic_hash: str = Field(min_length=1)
    aggregate_version: int = Field(gt=0)
    management_revision: int = Field(gt=0)
    side: Literal["long", "short"]
    source_quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    reduction_quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    remaining_quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    source_tp_filled_quantity: Decimal = Field(ge=0, allow_inf_nan=False)
    cancel_tp_order_id: str | None
    protection_order_id: str = Field(min_length=1)
    stop_price: Decimal = Field(gt=0, allow_inf_nan=False)
    tp_trigger_price: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    continue_runner: bool
    created_at_ms: int = Field(gt=0)
    expires_at_ms: int = Field(gt=0)

    @model_validator(mode="after")
    def conserved(self) -> OwnerReductionPreview:
        if self.source_quantity != self.reduction_quantity + self.remaining_quantity:
            raise ValueError("preview_quantity_mismatch")
        if self.expires_at_ms <= self.created_at_ms:
            raise ValueError("preview_time_invalid")
        if not self.continue_runner and self.tp_trigger_price is None:
            raise ValueError("pre_tp_reduction_requires_exact_target")
        return self


class OwnerReductionState(_Frozen):
    operation_id: str = Field(min_length=1)
    preview: OwnerReductionPreview
    phase: OwnerReductionPhase
    actual_reduction_quantity: Decimal = Field(
        default=Decimal(0), ge=0, allow_inf_nan=False
    )
    reduction_observed_at_ms: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def filled_bounds(self) -> OwnerReductionState:
        if self.actual_reduction_quantity > self.preview.reduction_quantity:
            raise ValueError("reduction_exceeds_owner_request")
        if self.phase in {
            OwnerReductionPhase.WAIT_PRICE,
            OwnerReductionPhase.BREAK_EVEN_PENDING,
            OwnerReductionPhase.RUNNER_CONTINUING,
        } and (
            self.actual_reduction_quantity <= 0 or self.reduction_observed_at_ms is None
        ):
            raise ValueError("continuation_requires_real_reduction")
        return self


class OwnerReductionDecision(_Frozen):
    state: OwnerReductionState
    action: Literal[
        "cancel_original_tp",
        "prepare_reduction",
        "reconcile",
        "restore_or_reconcile",
        "verify_protection",
        "record_reduction",
        "request_break_even",
        "review_required",
        "verified_closure_required",
        "rejected",
        "no_change",
    ]
    reason: str
    cancel_order_id: str | None = None


def _reached(side: str, price: Decimal, target: Decimal) -> bool:
    return price >= target if side == "long" else price <= target


def preview_owner_reduction(
    *,
    aggregate: TradeAggregate,
    facts: OwnerReductionFacts,
    requested_quantity: Decimal,
    quantity_step: Decimal,
    minimum_quantity: Decimal,
    minimum_notional: Decimal,
    now_ms: int,
) -> OwnerReductionPreview:
    a, f = aggregate, facts
    if (
        a.management_mode is not ManagementMode.AUTO
        or f.management_mode is not ManagementMode.AUTO
    ):
        raise ValueError("auto_required")
    if a.status not in {
        AggregateStatus.POSITION_PROTECTED,
        AggregateStatus.RUNNER_PROTECTED,
    }:
        raise ValueError("lifecycle_busy")
    if (
        f.ticket_id != a.identity.ticket_id
        or f.management_revision != a.management_revision
    ):
        raise ValueError("management_identity_changed")
    if not f.observed_at_ms <= now_ms < f.valid_until_ms:
        raise ValueError("facts_stale")
    if (
        f.position_quantity != a.position_qty
        or f.tp_filled_quantity != a.tp1_filled_qty
    ):
        raise ValueError("position_changed")
    if (
        f.unresolved_other_command
        or f.stop_triggered
        or f.reduction_state != "not_sent"
        or f.reduction_filled_quantity != 0
    ):
        raise ValueError("execution_busy")
    if (
        f.protection_order_id != a.active_stop_exchange_order_id
        or not f.protection_order_id
        or f.stop_price != a.active_stop_price
        or f.stop_price is None
        or f.protected_quantity != a.position_qty
    ):
        raise ValueError("protection_unproven")
    runner = a.status is AggregateStatus.RUNNER_PROTECTED
    waiting = not runner and a.owner_reduction_context is not None
    target = (
        None
        if runner
        else a.owner_reduction_context.original_tp_price if waiting and a.owner_reduction_context else (
            a.post_fill_exit_plan.tp_price
            if a.post_fill_exit_plan
            else a.ticket.take_profit_prices[0]
        )
    )
    if waiting and (f.tp_order_id is not None or f.tp_state not in {"absent","cancelled"}):
        raise ValueError("retired_tp_reappeared")
    if not runner and (
        (f.tp_state != "open" if not waiting else False)
        or f.tp_order_id != a.tp1_exchange_order_id
        or f.tp_filled_quantity != 0
        or target is None
        or _reached(a.identity.netting_domain.position_side, f.current_price, target)
    ):
        raise ValueError("tp_active_or_price_reached")
    if runner and (
        f.tp_order_id is not None or f.tp_state not in {"absent", "cancelled", "filled"}
    ):
        raise ValueError("independent_profit_plan_active")
    for value in (
        requested_quantity,
        quantity_step,
        minimum_quantity,
        minimum_notional,
    ):
        if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
            raise ValueError("invalid_reduction_quantity_rules")
    stop_crossed = (
        f.current_price <= f.stop_price
        if a.identity.netting_domain.position_side == "long"
        else f.current_price >= f.stop_price
    )
    if stop_crossed:
        raise ValueError("protection_price_crossed")
    if requested_quantity >= a.position_qty:
        raise ValueError("full_close_requires_separate_intent")
    qty = (requested_quantity / quantity_step).to_integral_value(
        rounding=ROUND_FLOOR
    ) * quantity_step
    remainder = a.position_qty - qty
    if any(
        q < minimum_quantity or q * f.current_price < minimum_notional
        for q in (qty, remainder)
    ):
        raise ValueError("reduction_or_remainder_unexecutable")
    return OwnerReductionPreview(
        ticket_id=a.identity.ticket_id,
        exit_policy_id=a.ticket.exit_policy_id,
        exit_policy_semantic_hash=a.ticket.exit_policy_semantic_hash,
        aggregate_version=a.version,
        management_revision=a.management_revision,
        side=a.identity.netting_domain.position_side,
        source_quantity=a.position_qty,
        reduction_quantity=qty,
        remaining_quantity=remainder,
        source_tp_filled_quantity=a.tp1_filled_qty,
        cancel_tp_order_id=None if runner else f.tp_order_id,
        protection_order_id=f.protection_order_id,
        stop_price=f.stop_price,
        tp_trigger_price=target,
        continue_runner=runner,
        created_at_ms=now_ms,
        expires_at_ms=now_ms + 30000,
    )


def advance_owner_reduction(
    state: OwnerReductionState, facts: OwnerReductionFacts, *, now_ms: int
) -> OwnerReductionDecision:
    p, f = state.preview, facts

    def result(action, reason, phase=None, **updates):
        values = state.model_dump()
        values.update(updates)
        if phase is not None:
            values["phase"] = phase
        return OwnerReductionDecision(
            state=OwnerReductionState.model_validate(values),
            action=action,
            reason=reason,
            cancel_order_id=p.cancel_tp_order_id
            if action == "cancel_original_tp"
            else None,
        )

    if state.phase is OwnerReductionPhase.REJECTED:
        return result("no_change", "terminal_operation")
    if f.ticket_id != p.ticket_id:
        raise ValueError("ticket_identity_mismatch")
    if not f.observed_at_ms <= now_ms < f.valid_until_ms:
        return result("reconcile", "facts_stale")
    if (
        f.management_revision != p.management_revision
        or f.management_mode is not ManagementMode.AUTO
    ):
        return result(
            "reconcile",
            "management_authority_changed",
            OwnerReductionPhase.REVIEW_REQUIRED,
        )
    if f.position_quantity == 0:
        unresolved = (
            f.unresolved_other_command
            or f.reduction_state in {"unknown", "working"}
            or f.residual_orders
        )
        return result(
            "reconcile" if unresolved else "verified_closure_required",
            "flat_requires_order_truth",
            OwnerReductionPhase.CLOSURE_PENDING,
        )
    if f.stop_triggered:
        return result(
            "review_required",
            "stop_race_requires_readonly_truth",
            OwnerReductionPhase.REVIEW_REQUIRED,
        )
    if state.phase in {
        OwnerReductionPhase.REVIEW_REQUIRED,
        OwnerReductionPhase.CLOSURE_PENDING,
    }:
        return result("reconcile", "explicit_resolution_required")
    if f.unresolved_other_command:
        return result("reconcile", "other_command_unresolved")
    if state.phase in {
        OwnerReductionPhase.PREVIEWED,
        OwnerReductionPhase.TP_CANCELLING,
    }:
        if (
            f.current_price <= p.stop_price
            if p.side == "long"
            else f.current_price >= p.stop_price
        ):
            return result(
                "review_required",
                "protection_price_crossed",
                OwnerReductionPhase.REVIEW_REQUIRED,
            )
        if f.reduction_state != "not_sent" or f.reduction_filled_quantity != 0:
            return result("reconcile", "reduction_already_started")
        if now_ms >= p.expires_at_ms:
            return result(
                "rejected"
                if state.phase is OwnerReductionPhase.PREVIEWED
                else "restore_or_reconcile",
                "preview_expired",
                OwnerReductionPhase.REJECTED
                if state.phase is OwnerReductionPhase.PREVIEWED
                else OwnerReductionPhase.RESTORE_REQUIRED,
            )
        if (
            f.position_quantity != p.source_quantity
            or f.tp_filled_quantity != p.source_tp_filled_quantity
            or f.protection_order_id != p.protection_order_id
            or f.stop_price != p.stop_price
            or f.protected_quantity != p.source_quantity
        ):
            return result(
                "restore_or_reconcile",
                "preview_changed",
                OwnerReductionPhase.RESTORE_REQUIRED,
            )
        if p.tp_trigger_price is not None and _reached(
            p.side, f.current_price, p.tp_trigger_price
        ):
            return result(
                "restore_or_reconcile",
                "tp_price_reached",
                OwnerReductionPhase.RESTORE_REQUIRED,
            )
        if not p.continue_runner and f.tp_order_id != p.cancel_tp_order_id:
            return result(
                "restore_or_reconcile",
                "tp_identity_changed",
                OwnerReductionPhase.RESTORE_REQUIRED,
            )
        if state.phase is OwnerReductionPhase.PREVIEWED and p.cancel_tp_order_id:
            if f.tp_state != "open":
                return result(
                    "restore_or_reconcile",
                    "tp_state_changed",
                    OwnerReductionPhase.RESTORE_REQUIRED,
                )
            return result(
                "cancel_original_tp",
                "cancel_exact_tp_before_reduce",
                OwnerReductionPhase.TP_CANCELLING,
            )
        if p.cancel_tp_order_id and f.tp_state != "cancelled":
            return result("reconcile", "tp_cancel_not_proven")
        return result(
            "prepare_reduction",
            "preview_revalidated",
            OwnerReductionPhase.REDUCTION_PENDING,
        )
    if state.phase in {
        OwnerReductionPhase.REDUCTION_PENDING,
        OwnerReductionPhase.PROTECTION_PENDING,
    }:
        if f.reduction_state not in {"terminal", "rejected"}:
            return result("reconcile", "reduction_outcome_unresolved")
        fill = f.reduction_filled_quantity
        if fill < state.actual_reduction_quantity:
            return result("reconcile", "reduction_evidence_regressed")
        if f.reduction_operation_id != state.operation_id:
            return result(
                "review_required",
                "reduction_evidence_identity_mismatch",
                OwnerReductionPhase.REVIEW_REQUIRED,
            )
        if f.tp_filled_quantity != p.source_tp_filled_quantity:
            return result(
                "review_required",
                "tp_fill_during_reduction",
                OwnerReductionPhase.REVIEW_REQUIRED,
            )
        if fill == 0:
            return result(
                "restore_or_reconcile",
                "no_reduction_executed",
                OwnerReductionPhase.RESTORE_REQUIRED,
            )
        if (
            fill > p.reduction_quantity
            or f.position_quantity != p.source_quantity - fill
        ):
            return result(
                "review_required",
                "quantity_not_conserved",
                OwnerReductionPhase.REVIEW_REQUIRED,
            )
        if (
            f.protected_quantity != f.position_quantity
            or not f.protection_order_id
            or f.stop_price is None
            or (
                f.stop_price < p.stop_price
                if p.side == "long"
                else f.stop_price > p.stop_price
            )
        ):
            return result(
                "verify_protection",
                "remaining_protection_unproven",
                OwnerReductionPhase.PROTECTION_PENDING,
                actual_reduction_quantity=fill,
                reduction_observed_at_ms=f.observed_at_ms,
            )
        return result(
            "record_reduction",
            "actual_reduction_verified",
            OwnerReductionPhase.RUNNER_CONTINUING
            if p.continue_runner
            else OwnerReductionPhase.WAIT_PRICE,
            actual_reduction_quantity=fill,
            reduction_observed_at_ms=f.observed_at_ms,
        )
    if state.phase is OwnerReductionPhase.WAIT_PRICE:
        if f.tp_filled_quantity != p.source_tp_filled_quantity or f.tp_state in {
            "open",
            "partial",
            "unknown",
        }:
            return result(
                "review_required",
                "retired_tp_not_terminal",
                OwnerReductionPhase.REVIEW_REQUIRED,
            )
        if f.position_quantity != p.source_quantity - state.actual_reduction_quantity:
            return result(
                "review_required",
                "continuation_position_changed",
                OwnerReductionPhase.REVIEW_REQUIRED,
            )
        if (
            state.reduction_observed_at_ms is None
            or f.observed_at_ms <= state.reduction_observed_at_ms
        ):
            return result("reconcile", "price_fact_precedes_reduction")
        if (
            f.protected_quantity != f.position_quantity
            or not f.protection_order_id
            or f.stop_price is None
            or (
                f.stop_price < p.stop_price
                if p.side == "long"
                else f.stop_price > p.stop_price
            )
        ):
            return result("reconcile", "price_condition_protection_unproven")
        if p.tp_trigger_price is not None and _reached(
            p.side, f.current_price, p.tp_trigger_price
        ):
            return result(
                "request_break_even",
                "original_price_condition_satisfied",
                OwnerReductionPhase.BREAK_EVEN_PENDING,
            )
        return result("no_change", "waiting_original_tp_price")
    return result("reconcile", "awaiting_explicit_completion")
