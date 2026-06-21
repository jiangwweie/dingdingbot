"""Standing-recovery readiness packet for a runtime reduce-only close.

This module is pure domain logic. It turns an already-built active-position
exit plan into a standing-authorization readiness packet. It never closes
positions, creates orders, calls an exchange, or grants execution authority by
itself. Real reduce-only recovery still requires the official action-time
FinalGate and Operation Layer path.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.runtime_position_exit_plan import (
    RuntimePositionExitPlan,
    RuntimePositionExitPlanStatus,
)


OWNER_REDUCE_ONLY_CLOSE_APPROVAL_ENV = "OWNER_APPROVED_RUNTIME_REDUCE_ONLY_CLOSE"
STANDING_REDUCE_ONLY_RECOVERY_SCOPE = (
    "standing-authorization:strategygroup-runtime-pilot:reduce-only-recovery"
)


class RuntimeReduceOnlyCloseOwnerPacketStatus(str, Enum):
    BLOCKED = "blocked"
    READY_FOR_OWNER_AUTHORIZATION = "ready_for_owner_authorization"
    READY_FOR_STANDING_RECOVERY_AUTHORIZATION = (
        "ready_for_standing_recovery_authorization"
    )


class RuntimeReduceOnlyCloseOwnerPacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    packet_id: str = Field(min_length=1, max_length=320)
    status: RuntimeReduceOnlyCloseOwnerPacketStatus
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    symbol: str = Field(min_length=1, max_length=128)
    side: str = Field(min_length=1, max_length=32)
    source_exit_plan_id: str = Field(min_length=1, max_length=260)
    source_monitor_id: str = Field(min_length=1, max_length=260)
    reduce_only_side: Optional[str] = Field(default=None, max_length=16)
    close_quantity: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    close_notional_reference: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    stop_price_reference: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    entry_price: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    owner_approval_env: Optional[str] = None
    owner_approval_value: Optional[str] = Field(default=None, max_length=512)
    owner_approval_required: bool = False
    standing_authorization_scope: Optional[str] = Field(default=None, max_length=256)
    operation_layer_required: Literal[True] = True
    finalgate_required: Literal[True] = True
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommended_owner_decision: str
    packet_only: Literal[True] = True
    not_order: Literal[True] = True
    not_execution_intent: Literal[True] = True
    not_execution_authority: Literal[True] = True
    exchange_called: Literal[False] = False
    exchange_order_submitted: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    order_created: Literal[False] = False
    order_cancelled: Literal[False] = False
    order_amended: Literal[False] = False
    position_closed: Literal[False] = False
    runtime_state_mutated: Literal[False] = False
    withdrawal_instruction_created: Literal[False] = False
    transfer_instruction_created: Literal[False] = False
    created_at_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def _status_contract(self) -> "RuntimeReduceOnlyCloseOwnerPacket":
        if self.status == RuntimeReduceOnlyCloseOwnerPacketStatus.BLOCKED:
            if not self.blockers:
                raise ValueError("blocked reduce-only close packet requires blockers")
            if self.owner_approval_value is not None:
                raise ValueError("blocked reduce-only close packet cannot expose approval value")
        if self.status == RuntimeReduceOnlyCloseOwnerPacketStatus.READY_FOR_OWNER_AUTHORIZATION:
            if not self.owner_approval_value:
                raise ValueError("ready reduce-only close packet requires approval value")
            if self.close_quantity is None or self.close_quantity <= Decimal("0"):
                raise ValueError("ready reduce-only close packet requires positive close quantity")
            if not self.reduce_only_side:
                raise ValueError("ready reduce-only close packet requires reduce-only side")
        if (
            self.status
            == RuntimeReduceOnlyCloseOwnerPacketStatus.READY_FOR_STANDING_RECOVERY_AUTHORIZATION
        ):
            if self.owner_approval_required:
                raise ValueError("standing recovery packet must not require owner approval")
            if self.owner_approval_value is not None:
                raise ValueError("standing recovery packet must not expose owner approval value")
            if not self.standing_authorization_scope:
                raise ValueError("standing recovery packet requires standing scope")
            if self.close_quantity is None or self.close_quantity <= Decimal("0"):
                raise ValueError("standing recovery packet requires positive close quantity")
            if not self.reduce_only_side:
                raise ValueError("standing recovery packet requires reduce-only side")
        return self


def build_runtime_reduce_only_close_owner_packet(
    *,
    exit_plan: RuntimePositionExitPlan,
    now_ms: int,
) -> RuntimeReduceOnlyCloseOwnerPacket:
    blockers = list(exit_plan.blockers)
    warnings = list(exit_plan.warnings)

    if exit_plan.status != RuntimePositionExitPlanStatus.READY_FOR_OWNER_REVIEW:
        blockers.append("exit_plan_not_ready_for_owner_review")
    if not exit_plan.active_position_present:
        blockers.append("active_position_missing")
    if not exit_plan.hard_stop_boundary_present:
        blockers.append("hard_stop_boundary_missing")
    if not exit_plan.full_reduce_only_close_feasible:
        blockers.append("full_reduce_only_close_not_feasible")
    if exit_plan.full_reduce_only_close_quantity is None:
        blockers.append("full_reduce_only_close_quantity_missing")
    if exit_plan.tp1_reduce_only_side is None:
        blockers.append("reduce_only_side_missing")

    ready = not blockers
    return RuntimeReduceOnlyCloseOwnerPacket(
        packet_id=(
            "runtime-reduce-only-close-owner-packet-"
            f"{exit_plan.runtime_instance_id}-{now_ms}"
        ),
        status=(
            RuntimeReduceOnlyCloseOwnerPacketStatus.READY_FOR_STANDING_RECOVERY_AUTHORIZATION
            if ready
            else RuntimeReduceOnlyCloseOwnerPacketStatus.BLOCKED
        ),
        runtime_instance_id=exit_plan.runtime_instance_id,
        symbol=exit_plan.symbol,
        side=exit_plan.side,
        source_exit_plan_id=exit_plan.plan_id,
        source_monitor_id=exit_plan.source_monitor_id,
        reduce_only_side=exit_plan.tp1_reduce_only_side,
        close_quantity=exit_plan.full_reduce_only_close_quantity,
        close_notional_reference=exit_plan.full_reduce_only_close_notional_reference,
        stop_price_reference=exit_plan.stop_price_reference,
        entry_price=exit_plan.entry_price,
        owner_approval_required=False,
        standing_authorization_scope=(
            STANDING_REDUCE_ONLY_RECOVERY_SCOPE if ready else None
        ),
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        recommended_owner_decision=(
            "prepare_official_reduce_only_recovery"
            if ready
            else "repair_exit_plan_before_reduce_only_recovery"
        ),
        created_at_ms=now_ms,
    )


def _approval_value(exit_plan: RuntimePositionExitPlan) -> str:
    qty = exit_plan.full_reduce_only_close_quantity
    return (
        f"runtime-reduce-only-close:{exit_plan.runtime_instance_id}:"
        f"{exit_plan.symbol}:{exit_plan.side}:qty={qty}:owner-authorized"
    )


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
