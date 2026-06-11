"""Non-executing exit-management plan for an active runtime position."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, ROUND_FLOOR
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.runtime_live_position_monitor import (
    RuntimeLivePositionMonitorPacket,
    RuntimeLivePositionMonitorStatus,
)
from src.domain.strategy_runtime import StrategyRuntimeInstance


class RuntimePositionExitPlanModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimePositionExitPlanStatus(str, Enum):
    NOT_APPLICABLE = "not_applicable"
    BLOCKED = "blocked"
    READY_FOR_OWNER_REVIEW = "ready_for_owner_review"


class RuntimePositionExitPlan(RuntimePositionExitPlanModel):
    plan_id: str = Field(min_length=1, max_length=260)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    symbol: str = Field(min_length=1, max_length=128)
    side: str = Field(min_length=1, max_length=32)
    status: RuntimePositionExitPlanStatus
    source_monitor_id: str = Field(min_length=1, max_length=260)
    action_kind: str = Field(default="tp1_partial_plus_runner_review")
    active_position_present: bool
    hard_stop_boundary_present: bool
    existing_tp_protection_present: bool
    current_qty: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    entry_price: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    stop_price_reference: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    risk_per_unit: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    tp1_price_reference: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    tp1_position_ratio: Decimal = Field(default=Decimal("0.5"), ge=Decimal("0"), le=Decimal("1"))
    tp1_quantity_requested: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    tp1_quantity_step_aligned: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    runner_quantity_reference: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    tp1_reduce_only_side: Optional[str] = None
    market_min_qty: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    market_qty_step: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    tp1_quantity_feasible: bool = False
    runner_preserved: bool = True
    recommended_owner_decision: str
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    not_order: Literal[True] = True
    not_execution_intent: Literal[True] = True
    not_execution_authority: Literal[True] = True
    exchange_called: Literal[False] = False
    exchange_order_submitted: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    order_created: Literal[False] = False
    withdrawal_instruction_created: Literal[False] = False
    transfer_instruction_created: Literal[False] = False
    created_at_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def _status_contract(self) -> "RuntimePositionExitPlan":
        if self.status == RuntimePositionExitPlanStatus.BLOCKED and not self.blockers:
            raise ValueError("blocked exit plan requires blockers")
        if (
            self.status == RuntimePositionExitPlanStatus.READY_FOR_OWNER_REVIEW
            and not self.active_position_present
        ):
            raise ValueError("ready exit plan requires active position")
        if self.tp1_quantity_feasible and self.tp1_quantity_step_aligned is None:
            raise ValueError("feasible TP1 quantity requires step-aligned quantity")
        return self


def build_runtime_position_exit_plan(
    *,
    runtime: StrategyRuntimeInstance,
    monitor: RuntimeLivePositionMonitorPacket,
    local_open_orders: list[Any],
    exchange_open_stop_orders: list[Any],
    market_rule: Mapping[str, Any] | None,
    now_ms: int,
) -> RuntimePositionExitPlan:
    """Build a non-executing TP1/runner review plan from already-read facts."""

    blockers: list[str] = []
    warnings: list[str] = []
    if not monitor.active_position_present:
        blockers.append("active_position_missing")
    if not monitor.hard_stop_boundary_present:
        blockers.append("hard_stop_boundary_missing")
    if monitor.reconciliation_severe_count > 0:
        blockers.append("reconciliation_severe_mismatch")

    stop_price = _stop_price(local_open_orders, exchange_open_stop_orders)
    if stop_price is None:
        blockers.append("stop_price_reference_missing")

    entry = monitor.entry_price
    qty = monitor.current_qty
    if entry is None:
        blockers.append("entry_price_missing")
    if qty is None or qty <= Decimal("0"):
        blockers.append("current_quantity_missing")

    risk_per_unit: Decimal | None = None
    tp1_price: Decimal | None = None
    if entry is not None and stop_price is not None:
        risk_per_unit = (
            stop_price - entry
            if runtime.side.lower() == "short"
            else entry - stop_price
        )
        if risk_per_unit <= Decimal("0"):
            blockers.append("invalid_stop_entry_geometry")
            risk_per_unit = None
        elif runtime.side.lower() == "short":
            tp1_price = entry - risk_per_unit
        else:
            tp1_price = entry + risk_per_unit

    min_qty = _decimal_or_none(_first_present(
        _get(market_rule, "min_quantity"),
        _get(market_rule, "min_qty"),
    ))
    qty_step = _decimal_or_none(_first_present(
        _get(market_rule, "step_size"),
        _get(market_rule, "qty_step"),
        _get(market_rule, "quantity_precision"),
    ))
    if market_rule is None:
        warnings.append("market_rule_snapshot_missing")
    if qty_step is None or qty_step <= Decimal("0"):
        warnings.append("market_quantity_step_missing")
    if min_qty is None:
        warnings.append("market_min_qty_missing")

    requested_tp1_qty = qty * Decimal("0.5") if qty is not None else None
    aligned_tp1_qty = (
        _floor_to_step(requested_tp1_qty, qty_step)
        if requested_tp1_qty is not None and qty_step is not None and qty_step > Decimal("0")
        else requested_tp1_qty
    )
    feasible = bool(
        aligned_tp1_qty is not None
        and aligned_tp1_qty > Decimal("0")
        and (min_qty is None or aligned_tp1_qty >= min_qty)
        and (qty is None or aligned_tp1_qty < qty)
    )
    if requested_tp1_qty is not None and not feasible and not blockers:
        warnings.append("tp1_partial_quantity_below_min_qty_or_step")

    reduce_only_side = "buy" if runtime.side.lower() == "short" else "sell"
    status = RuntimePositionExitPlanStatus.READY_FOR_OWNER_REVIEW
    recommended = "review_tp1_partial_plus_runner"
    if blockers:
        status = RuntimePositionExitPlanStatus.BLOCKED
        recommended = "repair_active_position_or_stop_facts_before_exit_management"
    elif monitor.tp_protection_present:
        status = RuntimePositionExitPlanStatus.NOT_APPLICABLE
        recommended = "tp_already_present_continue_monitoring"
    elif not feasible:
        recommended = "keep_hard_stop_only_or_authorize_different_reduce_only_exit_shape"

    return RuntimePositionExitPlan(
        plan_id=f"runtime-position-exit-plan-{runtime.runtime_instance_id}-{now_ms}",
        runtime_instance_id=runtime.runtime_instance_id,
        symbol=runtime.symbol,
        side=runtime.side,
        status=status,
        source_monitor_id=monitor.monitor_id,
        active_position_present=monitor.active_position_present,
        hard_stop_boundary_present=monitor.hard_stop_boundary_present,
        existing_tp_protection_present=monitor.tp_protection_present,
        current_qty=qty,
        entry_price=entry,
        stop_price_reference=stop_price,
        risk_per_unit=risk_per_unit,
        tp1_price_reference=tp1_price,
        tp1_quantity_requested=requested_tp1_qty,
        tp1_quantity_step_aligned=aligned_tp1_qty,
        runner_quantity_reference=(
            qty - aligned_tp1_qty
            if qty is not None and aligned_tp1_qty is not None and aligned_tp1_qty < qty
            else qty
        ),
        tp1_reduce_only_side=reduce_only_side,
        market_min_qty=min_qty,
        market_qty_step=qty_step,
        tp1_quantity_feasible=feasible,
        recommended_owner_decision=recommended,
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        metadata={
            "scope": "runtime_position_exit_management_plan",
            "right_tail_objective": "TP1 is optional only if it preserves a runner; avoid capping all upside.",
            "hard_stop_only_is_holdable_when_reconciliation_clean": (
                monitor.can_continue_holding and monitor.hard_stop_boundary_present
            ),
            "market_rule_source": _get(market_rule, "source", "unknown") if market_rule else None,
        },
        created_at_ms=now_ms,
    )


def _stop_price(local_open_orders: list[Any], exchange_open_stop_orders: list[Any]) -> Decimal | None:
    for order in local_open_orders:
        if _role(order) == "SL":
            value = _decimal_or_none(_first_present(
                _get(order, "trigger_price"),
                _get(order, "price"),
            ))
            if value is not None:
                return value
    for order in exchange_open_stop_orders:
        value = _decimal_or_none(_first_present(
            _get(order, "triggerPrice"),
            _get(order, "stopPrice"),
            _nested(order, "info", "triggerPrice"),
            _nested(order, "info", "stopPrice"),
        ))
        if value is not None:
            return value
    return None


def _role(order: Any) -> str:
    value = _get(order, "order_role")
    if hasattr(value, "value"):
        value = value.value
    return str(value or "").upper()


def _floor_to_step(value: Decimal, step: Decimal) -> Decimal:
    if step <= Decimal("0"):
        return value
    return (value / step).to_integral_value(rounding=ROUND_FLOOR) * step


def _get(item: Any, key: str, default: Any = None) -> Any:
    if item is None:
        return default
    if isinstance(item, Mapping):
        return item.get(key, default)
    return getattr(item, key, default)


def _nested(item: Any, *keys: str) -> Any:
    current = item
    for key in keys:
        current = _get(current, key)
        if current is None:
            return None
    return current


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _dedupe(values: Any) -> list[str]:
    out: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in out:
            out.append(text)
    return out
