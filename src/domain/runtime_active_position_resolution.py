"""Runtime active-position resolution packet.

This packet consolidates the post-submit active-position surfaces:

RuntimeLivePositionMonitorPacket
-> RuntimePositionExitPlan
-> RuntimePostCloseFollowupPacket
-> resolution decision

It is packet-only. It does not create orders, close positions, call
OrderLifecycle, call exchange write APIs, mutate runtime state, transfer funds,
or withdraw funds.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.runtime_live_position_monitor import (
    RuntimeLivePositionMonitorPacket,
    RuntimeLivePositionMonitorStatus,
)
from src.domain.runtime_position_exit_plan import (
    RuntimePositionExitPlan,
    RuntimePositionExitPlanStatus,
)
from src.domain.runtime_post_close_followup import (
    RuntimePostCloseFollowupPacket,
    RuntimePostCloseFollowupStatus,
)


class RuntimeActivePositionResolutionStatus(str, Enum):
    BLOCKED = "blocked"
    HOLD_WITH_HARD_STOP = "hold_with_hard_stop"
    WAITING_FOR_OWNER_CLOSE_AUTHORIZATION = "waiting_for_owner_close_authorization"
    READY_FOR_STANDING_REDUCE_ONLY_RECOVERY = (
        "ready_for_standing_reduce_only_recovery"
    )
    READY_FOR_CLOSED_REVIEW = "ready_for_closed_review"
    READY_FOR_NEXT_ATTEMPT_GATE = "ready_for_next_attempt_gate"


class RuntimeActivePositionResolutionPacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    packet_id: str = Field(min_length=1, max_length=360)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    symbol: str = Field(min_length=1, max_length=128)
    side: str = Field(min_length=1, max_length=32)
    status: RuntimeActivePositionResolutionStatus
    monitor_status: str = Field(min_length=1, max_length=128)
    exit_plan_status: str | None = Field(default=None, max_length=128)
    post_close_followup_status: str | None = Field(default=None, max_length=128)
    active_position_present: bool
    can_continue_holding: bool
    hard_stop_boundary_present: bool
    tp_protection_present: bool
    next_attempt_blocked_by_active_position: bool
    full_reduce_only_close_feasible: bool = False
    full_reduce_only_close_quantity: Decimal | None = Field(default=None, ge=Decimal("0"))
    full_reduce_only_close_requires_owner_authorization: bool = False
    owner_close_approval_env: str | None = None
    owner_close_approval_value: str | None = None
    standing_recovery_authorization_scope: str | None = None
    operation_layer_required: bool = True
    finalgate_required: bool = True
    closed_review_recorded: bool = False
    recommended_next_action: str
    required_steps: list[str] = Field(default_factory=list)
    completed_steps: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
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
    def _status_contract(self) -> "RuntimeActivePositionResolutionPacket":
        if self.status == RuntimeActivePositionResolutionStatus.BLOCKED and not self.blockers:
            raise ValueError("blocked active-position resolution requires blockers")
        if self.status == RuntimeActivePositionResolutionStatus.HOLD_WITH_HARD_STOP:
            if not self.active_position_present:
                raise ValueError("hold_with_hard_stop requires active position")
            if not self.can_continue_holding or not self.hard_stop_boundary_present:
                raise ValueError("hold_with_hard_stop requires holdable hard-stop state")
        if self.status == RuntimeActivePositionResolutionStatus.READY_FOR_NEXT_ATTEMPT_GATE:
            if self.active_position_present:
                raise ValueError("next-attempt gate readiness requires flat runtime")
        return self


def build_runtime_active_position_resolution_packet(
    *,
    monitor: RuntimeLivePositionMonitorPacket,
    exit_plan: RuntimePositionExitPlan | None,
    post_close_followup: RuntimePostCloseFollowupPacket | None,
    now_ms: int,
) -> RuntimeActivePositionResolutionPacket:
    """Build a non-executing resolution packet from already-read facts."""

    warnings = _dedupe([
        *monitor.warnings,
        *(exit_plan.warnings if exit_plan is not None else []),
        *(post_close_followup.warnings if post_close_followup is not None else []),
    ])
    next_attempt_blocked = bool(
        monitor.active_position_present
        and monitor.local_active_position_count >= monitor.max_active_positions
    )
    blockers: list[str] = []
    recommended = "continue_monitoring"
    required_steps: list[str] = []
    completed_steps: list[str] = ["fresh_monitor_read"]

    if monitor.status == RuntimeLivePositionMonitorStatus.BLOCKED:
        blockers.extend(monitor.blockers)
        status = RuntimeActivePositionResolutionStatus.BLOCKED
        recommended = "resolve_monitor_blockers_before_position_resolution"
    elif monitor.active_position_present:
        if monitor.can_continue_holding and monitor.hard_stop_boundary_present:
            status = RuntimeActivePositionResolutionStatus.HOLD_WITH_HARD_STOP
            recommended = "continue_holding_with_hard_stop_or_prepare_official_reduce_only_recovery"
            required_steps = ["continue_live_monitoring", "verify_next_attempt_gate_after_flat"]
            if _full_close_feasible(exit_plan):
                required_steps.append("optional_prepare_official_reduce_only_recovery")
        elif post_close_followup is not None and post_close_followup.status == (
            RuntimePostCloseFollowupStatus.READY_FOR_STANDING_REDUCE_ONLY_RECOVERY
        ):
            status = RuntimeActivePositionResolutionStatus.READY_FOR_STANDING_REDUCE_ONLY_RECOVERY
            recommended = "prepare_official_reduce_only_recovery"
            required_steps = list(post_close_followup.required_steps)
        elif post_close_followup is not None and post_close_followup.status == (
            RuntimePostCloseFollowupStatus.WAITING_FOR_OWNER_CLOSE_AUTHORIZATION
        ):
            status = RuntimeActivePositionResolutionStatus.WAITING_FOR_OWNER_CLOSE_AUTHORIZATION
            recommended = "owner_authorize_reduce_only_close_or_continue_holding"
            required_steps = list(post_close_followup.required_steps)
        else:
            status = RuntimeActivePositionResolutionStatus.BLOCKED
            blockers.extend(monitor.blockers or ["active_position_not_holdable"])
            recommended = "repair_active_position_protection_or_close_plan"
    elif post_close_followup is not None and post_close_followup.status == (
        RuntimePostCloseFollowupStatus.READY_FOR_CLOSED_REVIEW
    ):
        status = RuntimeActivePositionResolutionStatus.READY_FOR_CLOSED_REVIEW
        recommended = post_close_followup.recommended_next_action
        required_steps = list(post_close_followup.required_steps)
        completed_steps.extend(post_close_followup.completed_steps)
    elif post_close_followup is not None and post_close_followup.status == (
        RuntimePostCloseFollowupStatus.POST_CLOSE_COMPLETE
    ):
        status = RuntimeActivePositionResolutionStatus.READY_FOR_NEXT_ATTEMPT_GATE
        recommended = "verify_post_submit_next_attempt_gate"
        required_steps = ["verify_next_attempt_gate"]
        completed_steps.extend(post_close_followup.completed_steps)
    else:
        status = RuntimeActivePositionResolutionStatus.READY_FOR_NEXT_ATTEMPT_GATE
        recommended = "verify_post_submit_next_attempt_gate"
        required_steps = ["verify_next_attempt_gate"]

    if (
        post_close_followup is not None
        and status != RuntimeActivePositionResolutionStatus.HOLD_WITH_HARD_STOP
    ):
        completed_steps.extend(post_close_followup.completed_steps)
    if status == RuntimeActivePositionResolutionStatus.BLOCKED:
        blockers = _dedupe(blockers)

    return RuntimeActivePositionResolutionPacket(
        packet_id=f"runtime-active-position-resolution-{monitor.runtime_instance_id}-{now_ms}",
        runtime_instance_id=monitor.runtime_instance_id,
        symbol=monitor.symbol,
        side=monitor.side,
        status=status,
        monitor_status=monitor.status.value,
        exit_plan_status=exit_plan.status.value if exit_plan is not None else None,
        post_close_followup_status=(
            post_close_followup.status.value
            if post_close_followup is not None
            else None
        ),
        active_position_present=monitor.active_position_present,
        can_continue_holding=monitor.can_continue_holding,
        hard_stop_boundary_present=monitor.hard_stop_boundary_present,
        tp_protection_present=monitor.tp_protection_present,
        next_attempt_blocked_by_active_position=next_attempt_blocked,
        full_reduce_only_close_feasible=_full_close_feasible(exit_plan),
        full_reduce_only_close_quantity=(
            exit_plan.full_reduce_only_close_quantity
            if exit_plan is not None
            else None
        ),
        full_reduce_only_close_requires_owner_authorization=(
            exit_plan.full_reduce_only_close_requires_owner_authorization
            if exit_plan is not None
            else False
        ),
        owner_close_approval_env=(
            post_close_followup.owner_close_approval_env
            if post_close_followup is not None
            else None
        ),
        owner_close_approval_value=(
            post_close_followup.owner_close_approval_value
            if post_close_followup is not None
            else None
        ),
        standing_recovery_authorization_scope=(
            post_close_followup.standing_recovery_authorization_scope
            if post_close_followup is not None
            else None
        ),
        operation_layer_required=(
            post_close_followup.operation_layer_required
            if post_close_followup is not None
            else True
        ),
        finalgate_required=(
            post_close_followup.finalgate_required
            if post_close_followup is not None
            else True
        ),
        closed_review_recorded=(
            post_close_followup.closed_review_recorded
            if post_close_followup is not None
            else False
        ),
        recommended_next_action=recommended,
        required_steps=_dedupe(required_steps),
        completed_steps=_dedupe(completed_steps),
        blockers=blockers,
        warnings=warnings,
        metadata={
            "scope": "runtime_active_position_resolution",
            "right_tail_objective": (
                "A protected active position may be held to preserve right-tail "
                "opportunity; active position usage blocks new attempts."
            ),
            "does_not_execute_reduce_only_close": True,
            "does_not_record_closed_review": True,
        },
        created_at_ms=now_ms,
    )


def _full_close_feasible(exit_plan: RuntimePositionExitPlan | None) -> bool:
    return bool(
        exit_plan is not None
        and exit_plan.status == RuntimePositionExitPlanStatus.READY_FOR_OWNER_REVIEW
        and exit_plan.full_reduce_only_close_feasible
    )


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out
