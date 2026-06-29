"""Post-close follow-up lifecycle evidence for runtime reduce-only closes.

The artifact is a non-executing operator checklist. It keeps the post-close
sequence explicit so a real close can be followed by projection,
reconciliation, closed review, and next-attempt gate verification without
inventing steps at runtime.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.runtime_closed_trade_review_facts import (
    RuntimeClosedTradeReviewFactsArtifact,
    RuntimeClosedTradeReviewFactsStatus,
)
from src.domain.runtime_live_position_monitor import RuntimeLivePositionMonitorArtifact
from src.domain.runtime_reduce_only_close_authorization import (
    RuntimeReduceOnlyCloseOwnerEvidence,
    RuntimeReduceOnlyCloseOwnerEvidenceStatus,
)


class RuntimePostCloseFollowupStatus(str, Enum):
    BLOCKED = "blocked"
    WAITING_FOR_OWNER_CLOSE_AUTHORIZATION = "waiting_for_owner_close_authorization"
    READY_FOR_STANDING_REDUCE_ONLY_RECOVERY = (
        "ready_for_standing_reduce_only_recovery"
    )
    READY_FOR_CLOSED_REVIEW = "ready_for_closed_review"
    POST_CLOSE_COMPLETE = "post_close_complete"


class RuntimePostCloseFollowupArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str = Field(min_length=1, max_length=320)
    status: RuntimePostCloseFollowupStatus
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    symbol: str = Field(min_length=1, max_length=128)
    active_position_present: bool
    source_monitor_id: str = Field(min_length=1, max_length=260)
    owner_close_evidence_status: Optional[str] = None
    owner_close_approval_env: Optional[str] = None
    owner_close_approval_value: Optional[str] = None
    standing_recovery_authorization_scope: Optional[str] = None
    operation_layer_required: bool = True
    finalgate_required: bool = True
    closed_review_facts_status: Optional[str] = None
    closed_review_entry_order_id: Optional[str] = None
    closed_review_exit_order_id: Optional[str] = None
    closed_review_recorded: bool = False
    closed_review_id: Optional[str] = None
    closed_review_command_args: list[str] = Field(default_factory=list)
    required_steps: list[str] = Field(default_factory=list)
    completed_steps: list[str] = Field(default_factory=list)
    recommended_review_checkpoint: str
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    post_close_followup_evidence_only: Literal[True] = True
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
    def _status_contract(self) -> "RuntimePostCloseFollowupArtifact":
        if self.status == RuntimePostCloseFollowupStatus.BLOCKED and not self.blockers:
            raise ValueError("blocked post-close follow-up artifact requires blockers")
        if (
            self.status
            == RuntimePostCloseFollowupStatus.WAITING_FOR_OWNER_CLOSE_AUTHORIZATION
            and not self.owner_close_approval_value
        ):
            raise ValueError("waiting for close authorization requires approval value")
        if self.status == RuntimePostCloseFollowupStatus.READY_FOR_STANDING_REDUCE_ONLY_RECOVERY:
            if self.owner_close_approval_value is not None:
                raise ValueError("standing reduce-only recovery must not expose approval value")
            if not self.standing_recovery_authorization_scope:
                raise ValueError("standing reduce-only recovery requires standing scope")
        return self


def build_runtime_post_close_followup_artifact(
    *,
    monitor: RuntimeLivePositionMonitorArtifact,
    owner_close_artifact: RuntimeReduceOnlyCloseOwnerEvidence | None,
    closed_review_facts_artifact: RuntimeClosedTradeReviewFactsArtifact | None = None,
    closed_review_recorded: bool = False,
    closed_review_id: str | None = None,
    now_ms: int,
) -> RuntimePostCloseFollowupArtifact:
    blockers: list[str] = []
    warnings = list(monitor.warnings)
    owner_status = (
        owner_close_artifact.status.value if owner_close_artifact is not None else None
    )
    closed_review_status = (
        closed_review_facts_artifact.status.value
        if closed_review_facts_artifact is not None
        else None
    )

    if monitor.active_position_present:
        if owner_close_artifact is None:
            blockers.append("owner_close_artifact_missing")
        elif (
            owner_close_artifact.status
            not in {
                RuntimeReduceOnlyCloseOwnerEvidenceStatus.READY_FOR_OWNER_AUTHORIZATION,
                RuntimeReduceOnlyCloseOwnerEvidenceStatus.READY_FOR_STANDING_RECOVERY_AUTHORIZATION,
            }
        ):
            blockers.extend(owner_close_artifact.blockers)
            blockers.append("owner_close_artifact_not_ready")
        if blockers:
            status = RuntimePostCloseFollowupStatus.BLOCKED
            recommended = "repair_owner_close_artifact_before_close_followup"
        elif (
            owner_close_artifact is not None
            and owner_close_artifact.status
            == RuntimeReduceOnlyCloseOwnerEvidenceStatus.READY_FOR_STANDING_RECOVERY_AUTHORIZATION
        ):
            status = RuntimePostCloseFollowupStatus.READY_FOR_STANDING_REDUCE_ONLY_RECOVERY
            recommended = "prepare_official_reduce_only_recovery_or_continue_holding"
        else:
            status = RuntimePostCloseFollowupStatus.WAITING_FOR_OWNER_CLOSE_AUTHORIZATION
            recommended = "owner_authorize_reduce_only_close_or_continue_holding"
        if status == RuntimePostCloseFollowupStatus.READY_FOR_STANDING_REDUCE_ONLY_RECOVERY:
            required_steps = [
                "prepare_official_operation_layer_reduce_only_recovery",
                "run_action_time_finalgate_for_reduce_only_recovery",
                "execute_reduce_only_recovery_through_operation_layer",
                "verify_runtime_live_position_monitor_flat",
                "verify_reconciliation_severe_count_zero",
                "record_runtime_closed_trade_review",
                "verify_next_attempt_gate",
            ]
        else:
            required_steps = [
                "owner_authorize_exact_reduce_only_close_value",
                "execute_runtime_owner_reduce_only_close_flow",
                "verify_runtime_live_position_monitor_flat",
                "verify_reconciliation_severe_count_zero",
                "record_runtime_closed_trade_review",
                "verify_next_attempt_gate",
            ]
        completed_steps = ["fresh_monitor_read", "owner_close_artifact_built"]
    elif monitor.review_required_before_next_attempt:
        if closed_review_recorded:
            status = RuntimePostCloseFollowupStatus.POST_CLOSE_COMPLETE
            recommended = "closed_review_recorded_verify_next_attempt_gate"
            completed_steps = ["runtime_flat_observed", "closed_review_recorded"]
            if (
                closed_review_facts_artifact is not None
                and closed_review_facts_artifact.status
                == RuntimeClosedTradeReviewFactsStatus.READY_FOR_CLOSED_REVIEW
            ):
                completed_steps.append("closed_review_facts_resolved")
            required_steps = ["verify_next_attempt_gate"]
        elif (
            closed_review_facts_artifact is not None
            and closed_review_facts_artifact.status
            == RuntimeClosedTradeReviewFactsStatus.READY_FOR_CLOSED_REVIEW
        ):
            status = RuntimePostCloseFollowupStatus.READY_FOR_CLOSED_REVIEW
            recommended = "run_closed_trade_review_from_resolved_order_facts"
            completed_steps = ["runtime_flat_observed", "closed_review_facts_resolved"]
        elif closed_review_facts_artifact is None:
            status = RuntimePostCloseFollowupStatus.READY_FOR_CLOSED_REVIEW
            recommended = "record_runtime_closed_trade_review_before_next_attempt"
            completed_steps = ["runtime_flat_observed"]
        else:
            status = RuntimePostCloseFollowupStatus.BLOCKED
            blockers.extend(closed_review_facts_artifact.blockers)
            blockers.append("closed_review_facts_not_ready")
            recommended = "resolve_closed_review_facts_before_review"
            completed_steps = ["runtime_flat_observed"]
        if not closed_review_recorded:
            required_steps = [
                "identify_entry_and_exit_order_ids"
                if not closed_review_facts_artifact
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

    return RuntimePostCloseFollowupArtifact(
        artifact_id=f"runtime-post-close-followup-{monitor.runtime_instance_id}-{now_ms}",
        status=status,
        runtime_instance_id=monitor.runtime_instance_id,
        symbol=monitor.symbol,
        active_position_present=monitor.active_position_present,
        source_monitor_id=monitor.monitor_id,
        owner_close_evidence_status=owner_status,
        owner_close_approval_env=(
            owner_close_artifact.owner_approval_env
            if owner_close_artifact is not None
            else None
        ),
        owner_close_approval_value=(
            owner_close_artifact.owner_approval_value
            if owner_close_artifact is not None
            else None
        ),
        standing_recovery_authorization_scope=(
            owner_close_artifact.standing_authorization_scope
            if owner_close_artifact is not None
            else None
        ),
        operation_layer_required=(
            owner_close_artifact.operation_layer_required
            if owner_close_artifact is not None
            else True
        ),
        finalgate_required=(
            owner_close_artifact.finalgate_required
            if owner_close_artifact is not None
            else True
        ),
        closed_review_facts_status=closed_review_status,
        closed_review_entry_order_id=(
            closed_review_facts_artifact.entry_order_id
            if closed_review_facts_artifact is not None
            else None
        ),
        closed_review_exit_order_id=(
            closed_review_facts_artifact.exit_order_id
            if closed_review_facts_artifact is not None
            else None
        ),
        closed_review_recorded=closed_review_recorded,
        closed_review_id=closed_review_id,
        closed_review_command_args=(
            list(closed_review_facts_artifact.review_command_args)
            if closed_review_facts_artifact is not None
            else []
        ),
        required_steps=required_steps,
        completed_steps=completed_steps,
        recommended_review_checkpoint=recommended,
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
