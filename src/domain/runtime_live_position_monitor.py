"""Runtime-native live position monitor packet.

This module is pure domain logic. It summarizes post-submit runtime facts for
Owner review and follow-up gating, but it never creates orders, closes
positions, calls an exchange, or mutates runtime state.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.models import Direction, OrderRole, OrderStatus
from src.domain.strategy_runtime import (
    StrategyRuntimeInstance,
    StrategyRuntimeInstanceStatus,
)


class RuntimeLivePositionMonitorModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeLivePositionMonitorStatus(str, Enum):
    BLOCKED = "blocked"
    ACTIVE_PROTECTED = "active_protected"
    ACTIVE_PROTECTION_WARNING = "active_protection_warning"
    ACTIVE_UNPROTECTED = "active_unprotected"
    FLAT_REVIEW_REQUIRED = "flat_review_required"
    FLAT_NO_REVIEW_REQUIRED = "flat_no_review_required"


class RuntimeLiveProtectionStatus(str, Enum):
    HARD_STOP_AND_TP_PRESENT = "hard_stop_and_tp_present"
    HARD_STOP_ONLY = "hard_stop_only"
    HARD_STOP_MISSING = "hard_stop_missing"
    NO_ACTIVE_POSITION = "no_active_position"
    UNKNOWN = "unknown"


class RuntimeLivePositionMonitorPacket(RuntimeLivePositionMonitorModel):
    monitor_id: str = Field(min_length=1, max_length=260)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    symbol: str = Field(min_length=1, max_length=128)
    side: str = Field(min_length=1, max_length=32)
    status: RuntimeLivePositionMonitorStatus
    protection_status: RuntimeLiveProtectionStatus
    runtime_status: StrategyRuntimeInstanceStatus
    runtime_execution_enabled: bool
    runtime_shadow_mode: bool
    active_position_present: bool
    local_active_position_count: int = Field(ge=0)
    exchange_active_position_count: int = Field(ge=0)
    local_open_order_count: int = Field(ge=0)
    exchange_open_stop_order_count: int = Field(ge=0)
    sl_protection_present: bool
    tp_protection_present: bool
    hard_stop_boundary_present: bool
    current_qty: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    entry_price: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    mark_price: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    unrealized_pnl: Optional[Decimal] = None
    liquidation_price: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    attempts_used: int = Field(ge=0)
    attempts_remaining: int = Field(ge=0)
    max_attempts: int = Field(ge=1)
    budget_reserved: Decimal = Field(ge=Decimal("0"))
    budget_remaining: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    max_active_positions: int = Field(ge=0)
    reconciliation_severe_count: int = Field(ge=0)
    reconciliation_warning_count: int = Field(ge=0)
    reconciliation_mismatch_types: list[str] = Field(default_factory=list)
    blocks_new_entries_until_resolved: bool
    can_continue_holding: bool
    review_required_before_next_attempt: bool
    owner_action_required: bool
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    not_execution_authority: Literal[True] = True
    runtime_state_mutated: Literal[False] = False
    order_created: Literal[False] = False
    order_cancelled: Literal[False] = False
    order_amended: Literal[False] = False
    position_closed: Literal[False] = False
    exchange_called_by_domain: Literal[False] = False
    exchange_order_submitted: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    owner_bounded_execution_called: Literal[False] = False
    withdrawal_instruction_created: Literal[False] = False
    transfer_instruction_created: Literal[False] = False
    created_at_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def _status_contract(self) -> "RuntimeLivePositionMonitorPacket":
        if self.status == RuntimeLivePositionMonitorStatus.BLOCKED and not self.blockers:
            raise ValueError("blocked monitor packet requires blockers")
        if self.status == RuntimeLivePositionMonitorStatus.ACTIVE_UNPROTECTED:
            if self.hard_stop_boundary_present:
                raise ValueError("active_unprotected cannot have hard stop boundary")
            if not self.owner_action_required:
                raise ValueError("active_unprotected requires Owner action")
        if self.status in {
            RuntimeLivePositionMonitorStatus.FLAT_REVIEW_REQUIRED,
            RuntimeLivePositionMonitorStatus.FLAT_NO_REVIEW_REQUIRED,
        }:
            if self.active_position_present:
                raise ValueError("flat monitor packet cannot have active position")
        if self.can_continue_holding and not self.active_position_present:
            raise ValueError("can_continue_holding requires active position")
        if self.can_continue_holding and not self.hard_stop_boundary_present:
            raise ValueError("can_continue_holding requires hard stop boundary")
        return self


def build_runtime_live_position_monitor_packet(
    *,
    runtime: StrategyRuntimeInstance,
    local_positions: list[Any],
    local_open_orders: list[Any],
    exchange_positions: list[Any] | None,
    exchange_open_stop_orders: list[Any] | None,
    reconciliation_result: Any | None,
    now_ms: int,
    exchange_facts_available: bool = True,
) -> RuntimeLivePositionMonitorPacket:
    """Build a post-submit monitor packet from already-read facts."""

    local_positions = [
        position
        for position in list(local_positions or [])
        if _matches_symbol(position, runtime.symbol) and not _bool_value(position, "is_closed")
    ]
    local_open_orders = [
        order for order in list(local_open_orders or []) if _matches_symbol(order, runtime.symbol)
    ]
    exchange_positions = [
        position
        for position in list(exchange_positions or [])
        if _matches_symbol(position, runtime.symbol) and _position_size(position) > Decimal("0")
    ]
    exchange_open_stop_orders = [
        order
        for order in list(exchange_open_stop_orders or [])
        if _matches_symbol(order, runtime.symbol)
    ]

    active_position_present = bool(local_positions or exchange_positions)
    sl_present = _has_local_sl(local_open_orders) or _has_exchange_reduce_only_stop(
        exchange_open_stop_orders
    )
    tp_present = _has_local_tp(local_open_orders) or _has_exchange_tp(
        exchange_open_stop_orders
    )
    severe_count, warning_count, mismatch_types = _reconciliation_summary(
        reconciliation_result
    )

    blockers: list[str] = []
    warnings: list[str] = []
    if runtime.status != StrategyRuntimeInstanceStatus.ACTIVE:
        blockers.append("runtime_not_active")
    if severe_count > 0:
        blockers.append("reconciliation_severe_mismatch")
    if not exchange_facts_available:
        blockers.append("exchange_facts_unavailable")
    active_position_slots_used = max(len(local_positions), len(exchange_positions))
    if active_position_present and runtime.boundary.max_active_positions <= active_position_slots_used:
        blockers.append("runtime_max_active_positions_in_use")
    if active_position_present and runtime.boundary.requires_protection and not sl_present:
        blockers.append("active_position_missing_hard_stop")
    if active_position_present and sl_present and not tp_present:
        warnings.append("missing_tp_protection_right_tail_exit_not_mounted")
    if warning_count > 0:
        warnings.append("reconciliation_warning_present")
    if local_positions and exchange_positions and len(local_positions) != len(exchange_positions):
        warnings.append("local_exchange_active_position_count_differs")

    hard_stop_present = bool(sl_present)
    can_continue_holding = (
        active_position_present
        and hard_stop_present
        and severe_count == 0
        and exchange_facts_available
    )
    review_required = (
        runtime.boundary.requires_review
        and not active_position_present
        and runtime.boundary.attempts_used > 0
    )
    owner_action_required = bool(
        "active_position_missing_hard_stop" in blockers
        or "exchange_facts_unavailable" in blockers
        or severe_count > 0
        or review_required
    )

    status = RuntimeLivePositionMonitorStatus.ACTIVE_PROTECTED
    protection_status = RuntimeLiveProtectionStatus.HARD_STOP_AND_TP_PRESENT
    if blockers and any(
        item
        in {
            "runtime_not_active",
            "reconciliation_severe_mismatch",
            "exchange_facts_unavailable",
        }
        for item in blockers
    ):
        status = RuntimeLivePositionMonitorStatus.BLOCKED
        protection_status = (
            RuntimeLiveProtectionStatus.HARD_STOP_ONLY
            if hard_stop_present and active_position_present
            else RuntimeLiveProtectionStatus.UNKNOWN
        )
    elif not active_position_present:
        status = (
            RuntimeLivePositionMonitorStatus.FLAT_REVIEW_REQUIRED
            if review_required
            else RuntimeLivePositionMonitorStatus.FLAT_NO_REVIEW_REQUIRED
        )
        protection_status = RuntimeLiveProtectionStatus.NO_ACTIVE_POSITION
    elif not hard_stop_present:
        status = RuntimeLivePositionMonitorStatus.ACTIVE_UNPROTECTED
        protection_status = RuntimeLiveProtectionStatus.HARD_STOP_MISSING
    elif not tp_present:
        status = RuntimeLivePositionMonitorStatus.ACTIVE_PROTECTION_WARNING
        protection_status = RuntimeLiveProtectionStatus.HARD_STOP_ONLY

    price_facts = _primary_position_facts(
        local_positions=local_positions,
        exchange_positions=exchange_positions,
    )
    return RuntimeLivePositionMonitorPacket(
        monitor_id=f"runtime-live-position-monitor-{runtime.runtime_instance_id}-{now_ms}",
        runtime_instance_id=runtime.runtime_instance_id,
        symbol=runtime.symbol,
        side=runtime.side,
        status=status,
        protection_status=protection_status,
        runtime_status=runtime.status,
        runtime_execution_enabled=runtime.execution_enabled,
        runtime_shadow_mode=runtime.shadow_mode,
        active_position_present=active_position_present,
        local_active_position_count=len(local_positions),
        exchange_active_position_count=len(exchange_positions),
        local_open_order_count=len(local_open_orders),
        exchange_open_stop_order_count=len(exchange_open_stop_orders),
        sl_protection_present=sl_present,
        tp_protection_present=tp_present,
        hard_stop_boundary_present=hard_stop_present,
        current_qty=price_facts["current_qty"],
        entry_price=price_facts["entry_price"],
        mark_price=price_facts["mark_price"],
        unrealized_pnl=price_facts["unrealized_pnl"],
        liquidation_price=price_facts["liquidation_price"],
        attempts_used=runtime.boundary.attempts_used,
        attempts_remaining=runtime.attempts_remaining,
        max_attempts=runtime.boundary.max_attempts,
        budget_reserved=runtime.boundary.budget_reserved,
        budget_remaining=runtime.budget_remaining,
        max_active_positions=runtime.boundary.max_active_positions,
        reconciliation_severe_count=severe_count,
        reconciliation_warning_count=warning_count,
        reconciliation_mismatch_types=mismatch_types,
        blocks_new_entries_until_resolved=bool(blockers or review_required),
        can_continue_holding=can_continue_holding,
        review_required_before_next_attempt=review_required,
        owner_action_required=owner_action_required,
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        metadata={
            "right_tail_risk_capital_semantics": (
                "missing TP is an exit-policy warning when a hard stop is present; "
                "it is not a runaway-risk blocker"
            ),
            "hard_stop_controls_runaway_loss": hard_stop_present,
            "small_loss_within_runtime_boundary_can_be_acceptable": True,
            "active_position_slots_used": active_position_slots_used,
        },
        created_at_ms=now_ms,
    )


def _matches_symbol(item: Any, symbol: str) -> bool:
    return str(_get(item, "symbol") or "") == symbol


def _has_local_sl(orders: list[Any]) -> bool:
    return any(_order_role(order) == "SL" and _order_is_active(order) for order in orders)


def _has_local_tp(orders: list[Any]) -> bool:
    return any(_order_role(order) in {"TP1", "TP2", "TP3", "TP4", "TP5"} and _order_is_active(order) for order in orders)


def _has_exchange_reduce_only_stop(orders: list[Any]) -> bool:
    for order in orders:
        if not _order_is_exchange_open(order):
            continue
        if not _truthy(_nested(order, "reduceOnly")):
            continue
        if _decimal_or_none(_first_present(
            _nested(order, "triggerPrice"),
            _nested(order, "stopPrice"),
            _nested(order, "info", "triggerPrice"),
            _nested(order, "info", "stopPrice"),
        )) is not None:
            return True
    return False


def _has_exchange_tp(orders: list[Any]) -> bool:
    for order in orders:
        if not _order_is_exchange_open(order):
            continue
        order_type = str(_nested(order, "type") or _nested(order, "info", "orderType") or "").upper()
        if "TAKE_PROFIT" in order_type:
            return True
        if _decimal_or_none(_first_present(
            _nested(order, "takeProfitPrice"),
            _nested(order, "info", "takeProfitPrice"),
        )) is not None:
            return True
    return False


def _order_is_active(order: Any) -> bool:
    status = _order_status(order)
    return status in {"SUBMITTED", "OPEN", "PARTIALLY_FILLED"}


def _order_is_exchange_open(order: Any) -> bool:
    status = str(_nested(order, "status") or _nested(order, "info", "algoStatus") or "").upper()
    return status in {"OPEN", "NEW", "PARTIALLY_FILLED", "PARTIALLYFILLED"}


def _order_role(order: Any) -> str:
    value = _get(order, "order_role")
    if isinstance(value, OrderRole):
        return value.value
    return str(value or "").upper()


def _order_status(order: Any) -> str:
    value = _get(order, "status")
    if isinstance(value, OrderStatus):
        return value.value
    return str(value or "").upper()


def _primary_position_facts(
    *,
    local_positions: list[Any],
    exchange_positions: list[Any],
) -> dict[str, Optional[Decimal]]:
    source = exchange_positions[0] if exchange_positions else (local_positions[0] if local_positions else None)
    if source is None:
        return {
            "current_qty": None,
            "entry_price": None,
            "mark_price": None,
            "unrealized_pnl": None,
            "liquidation_price": None,
        }
    return {
        "current_qty": _absolute_decimal(
            _first_decimal(
                _get(source, "size"),
                _get(source, "current_qty"),
                _nested(source, "info", "positionAmt"),
            )
        ),
        "entry_price": _first_decimal(
            _get(source, "entry_price"),
            _get(source, "entryPrice"),
        ),
        "mark_price": _first_decimal(_get(source, "mark_price"), _get(source, "markPrice")),
        "unrealized_pnl": _first_decimal(
            _get(source, "unrealized_pnl"),
            _get(source, "unrealizedPnl"),
        ),
        "liquidation_price": _first_decimal(
            _get(source, "liquidation_price"),
            _get(source, "liquidationPrice"),
        ),
    }


def _reconciliation_summary(result: Any | None) -> tuple[int, int, list[str]]:
    if result is None:
        return 0, 0, []
    mismatches = list(_get(result, "mismatches") or [])
    severe = int(_get(result, "severe_count") or 0)
    warning = int(_get(result, "warning_count") or 0)
    return severe, warning, _dedupe(
        str(_get(item, "mismatch_type") or "") for item in mismatches if _get(item, "mismatch_type")
    )


def _position_size(position: Any) -> Decimal:
    value = _first_decimal(
        _get(position, "size"),
        _get(position, "current_qty"),
        _nested(position, "info", "positionAmt"),
        default=Decimal("0"),
    ) or Decimal("0")
    return abs(value)


def _bool_value(item: Any, key: str) -> bool:
    return bool(_get(item, key))


def _get(item: Any, key: str, default: Any = None) -> Any:
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


def _first_decimal(*values: Any, default: Optional[Decimal] = None) -> Optional[Decimal]:
    for value in values:
        decimal_value = _decimal_or_none(value)
        if decimal_value is not None:
            return decimal_value
    return default


def _decimal_or_none(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _absolute_decimal(value: Optional[Decimal]) -> Optional[Decimal]:
    return abs(value) if value is not None else None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _dedupe(values: Any) -> list[str]:
    out: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in out:
            out.append(text)
    return out
