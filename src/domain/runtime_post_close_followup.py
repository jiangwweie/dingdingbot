"""Post-close follow-up checklist for runtime reduce-only closes.

The packet is a non-executing operator checklist. It keeps the post-close
sequence explicit so a real close can be followed by projection, reconciliation,
closed review, and next-attempt gate verification without inventing steps at
runtime.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.runtime_closed_trade_review_facts import (
    RuntimeClosedTradeReviewFactsPacket,
    RuntimeClosedTradeReviewFactsStatus,
)
from src.domain.runtime_live_position_monitor import RuntimeLivePositionMonitorPacket
from src.domain.runtime_reduce_only_close_authorization import (
    RuntimeReduceOnlyCloseOwnerPacket,
    RuntimeReduceOnlyCloseOwnerPacketStatus,
)


class RuntimePostCloseFollowupStatus(str, Enum):
    BLOCKED = "blocked"
    WAITING_FOR_OWNER_CLOSE_AUTHORIZATION = "waiting_for_owner_close_authorization"
    READY_FOR_CLOSED_REVIEW = "ready_for_closed_review"
    POST_CLOSE_COMPLETE = "post_close_complete"


class RuntimePostCloseFollowupPacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    packet_id: str = Field(min_length=1, max_length=320)
    status: RuntimePostCloseFollowupStatus
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    symbol: str = Field(min_length=1, max_length=128)
    active_position_present: bool
    source_monitor_id: str = Field(min_length=1, max_length=260)
    owner_close_packet_status: Optional[str] = None
    owner_close_approval_env: Optional[str] = None
    owner_close_approval_value: Optional[str] = None
    closed_review_facts_status: Optional[str] = None
    closed_review_entry_order_id: Optional[str] = None
    closed_review_exit_order_id: Optional[str] = None
    closed_review_recorded: bool = False
    closed_review_id: Optional[str] = None
    closed_review_command_args: list[str] = Field(default_factory=list)
    required_steps: list[str] = Field(default_factory=list)
    completed_steps: list[str] = Field(default_factory=list)
    recommended_next_action: str
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
    def _status_contract(self) -> "RuntimePostCloseFollowupPacket":
        if self.status == RuntimePostCloseFollowupStatus.BLOCKED and not self.blockers:
            raise ValueError("blocked post-close follow-up packet requires blockers")
        if (
            self.status
            == RuntimePostCloseFollowupStatus.WAITING_FOR_OWNER_CLOSE_AUTHORIZATION
            and not self.owner_close_approval_value
        ):
            raise ValueError("waiting for close authorization requires approval value")
        return self


def build_runtime_post_close_followup_packet(
    *,
    monitor: RuntimeLivePositionMonitorPacket,
    owner_close_packet: RuntimeReduceOnlyCloseOwnerPacket | None,
    closed_review_facts_packet: RuntimeClosedTradeReviewFactsPacket | None = None,
    closed_review_recorded: bool = False,
    closed_review_id: str | None = None,
    now_ms: int,
) -> RuntimePostCloseFollowupPacket:
    blockers: list[str] = []
    warnings = list(monitor.warnings)
    owner_status = owner_close_packet.status.value if owner_close_packet is not None else None
    closed_review_status = (
        closed_review_facts_packet.status.value
        if closed_review_facts_packet is not None
        else None
    )

    if monitor.active_position_present:
        if owner_close_packet is None:
            blockers.append("owner_close_packet_missing")
        elif (
            owner_close_packet.status
            != RuntimeReduceOnlyCloseOwnerPacketStatus.READY_FOR_OWNER_AUTHORIZATION
        ):
            blockers.extend(owner_close_packet.blockers)
            blockers.append("owner_close_packet_not_ready")
        if blockers:
            status = RuntimePostCloseFollowupStatus.BLOCKED
            recommended = "repair_owner_close_packet_before_close_followup"
        else:
            status = RuntimePostCloseFollowupStatus.WAITING_FOR_OWNER_CLOSE_AUTHORIZATION
            recommended = "owner_authorize_reduce_only_close_or_continue_holding"
        required_steps = [
            "owner_authorize_exact_reduce_only_close_value",
            "execute_runtime_owner_reduce_only_close_flow",
            "verify_runtime_live_position_monitor_flat",
            "verify_reconciliation_severe_count_zero",
            "record_runtime_closed_trade_review",
            "verify_next_attempt_gate",
        ]
        completed_steps = ["fresh_monitor_read", "owner_close_packet_built"]
    elif monitor.review_required_before_next_attempt:
        if closed_review_recorded:
            status = RuntimePostCloseFollowupStatus.POST_CLOSE_COMPLETE
            recommended = "closed_review_recorded_verify_next_attempt_gate"
            completed_steps = ["runtime_flat_observed", "closed_review_recorded"]
            if (
                closed_review_facts_packet is not None
                and closed_review_facts_packet.status
                == RuntimeClosedTradeReviewFactsStatus.READY_FOR_CLOSED_REVIEW
            ):
                completed_steps.append("closed_review_facts_resolved")
            required_steps = ["verify_next_attempt_gate"]
        elif (
            closed_review_facts_packet is not None
            and closed_review_facts_packet.status
            == RuntimeClosedTradeReviewFactsStatus.READY_FOR_CLOSED_REVIEW
        ):
            status = RuntimePostCloseFollowupStatus.READY_FOR_CLOSED_REVIEW
            recommended = "run_closed_trade_review_from_resolved_order_facts"
            completed_steps = ["runtime_flat_observed", "closed_review_facts_resolved"]
        elif closed_review_facts_packet is None:
            status = RuntimePostCloseFollowupStatus.READY_FOR_CLOSED_REVIEW
            recommended = "record_runtime_closed_trade_review_before_next_attempt"
            completed_steps = ["runtime_flat_observed"]
        else:
            status = RuntimePostCloseFollowupStatus.BLOCKED
            blockers.extend(closed_review_facts_packet.blockers)
            blockers.append("closed_review_facts_not_ready")
            recommended = "resolve_closed_review_facts_before_review"
            completed_steps = ["runtime_flat_observed"]
        if not closed_review_recorded:
            required_steps = [
                "identify_entry_and_exit_order_ids"
                if not closed_review_facts_packet
                else "use_resolved_closed_review_order_ids",
                "verify_reconciliation_severe_count_zero",
                "record_runtime_closed_trade_review",
                "verify_next_attempt_gate",
            ]
    else:
        status = RuntimePostCloseFollowupStatus.POST_CLOSE_COMPLETE
        recommended = "post_close_followup_complete_continue_runtime_planning"
        required_steps = []
        completed_steps = ["runtime_flat_observed", "review_gate_not_required"]

    return RuntimePostCloseFollowupPacket(
        packet_id=f"runtime-post-close-followup-{monitor.runtime_instance_id}-{now_ms}",
        status=status,
        runtime_instance_id=monitor.runtime_instance_id,
        symbol=monitor.symbol,
        active_position_present=monitor.active_position_present,
        source_monitor_id=monitor.monitor_id,
        owner_close_packet_status=owner_status,
        owner_close_approval_env=(
            owner_close_packet.owner_approval_env if owner_close_packet is not None else None
        ),
        owner_close_approval_value=(
            owner_close_packet.owner_approval_value if owner_close_packet is not None else None
        ),
        closed_review_facts_status=closed_review_status,
        closed_review_entry_order_id=(
            closed_review_facts_packet.entry_order_id
            if closed_review_facts_packet is not None
            else None
        ),
        closed_review_exit_order_id=(
            closed_review_facts_packet.exit_order_id
            if closed_review_facts_packet is not None
            else None
        ),
        closed_review_recorded=closed_review_recorded,
        closed_review_id=closed_review_id,
        closed_review_command_args=(
            list(closed_review_facts_packet.review_command_args)
            if closed_review_facts_packet is not None
            else []
        ),
        required_steps=required_steps,
        completed_steps=completed_steps,
        recommended_next_action=recommended,
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        metadata={
            "scope": "runtime_post_close_followup",
            "right_tail_objective": "Close follow-up preserves review and attempt learning rather than treating flatness as completion.",
            "closed_review_recorded": closed_review_recorded,
        },
        created_at_ms=now_ms,
    )


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
