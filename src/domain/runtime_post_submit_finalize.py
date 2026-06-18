"""Runtime-level post-submit finalize packet.

This packet closes the semantic gap after a real submit result exists. It
acknowledges that the consumed authorization is replay-only evidence, gathers
post-submit review / accounting / settlement facts, and produces the next
attempt gate without returning to pre-submit rehearsal.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.runtime_execution_exchange_submit_execution_result import (
    RuntimeExecutionExchangeSubmitExecutionResult,
    RuntimeExecutionExchangeSubmitExecutionStatus,
)
from src.domain.runtime_execution_post_submit_budget_settlement import (
    RuntimeExecutionPostSubmitBudgetSettlement,
    RuntimeExecutionPostSubmitBudgetSettlementStatus,
)
from src.domain.runtime_execution_submit_outcome_review import (
    RuntimeExecutionSubmitOutcomeReview,
    RuntimeExecutionSubmitOutcomeReviewStatus,
)
from src.domain.strategy_runtime import (
    StrategyRuntimeInstance,
    StrategyRuntimeInstanceStatus,
)


class RuntimePostSubmitFinalizeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimePostSubmitFinalizeStatus(str, Enum):
    BLOCKED = "blocked"
    FINALIZED_NEXT_ATTEMPT_BLOCKED = "finalized_next_attempt_blocked"
    FINALIZED_READY_FOR_NEXT_ATTEMPT = "finalized_ready_for_next_attempt"


class RuntimeNextAttemptGateStatus(str, Enum):
    BLOCKED = "blocked"
    READY_FOR_FRESH_SIGNAL = "ready_for_fresh_signal"


class RuntimeNextAttemptGate(RuntimePostSubmitFinalizeModel):
    status: RuntimeNextAttemptGateStatus
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    attempts_remaining: int = Field(ge=0)
    budget_remaining: Optional[str] = Field(default=None, max_length=96)
    active_positions_count: Optional[int] = Field(default=None, ge=0)
    max_active_positions: int = Field(ge=0)
    requires_fresh_strategy_signal: Literal[True] = True
    requires_fresh_authorization: Literal[True] = True
    consumed_authorization_replay_only: Literal[True] = True
    pre_submit_rehearsal_retry_allowed: Literal[False] = False
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_gate(self) -> "RuntimeNextAttemptGate":
        if self.status == RuntimeNextAttemptGateStatus.BLOCKED and not self.blockers:
            raise ValueError("blocked next-attempt gate requires blockers")
        if self.status == RuntimeNextAttemptGateStatus.READY_FOR_FRESH_SIGNAL:
            if self.blockers:
                raise ValueError("ready next-attempt gate cannot have blockers")
            if self.active_positions_count is None:
                raise ValueError("ready next-attempt gate requires active-position fact")
        return self


class RuntimePostSubmitFinalizePacket(RuntimePostSubmitFinalizeModel):
    packet_id: str = Field(min_length=1, max_length=640)
    authorization_id: str = Field(min_length=1, max_length=220)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    execution_intent_id: Optional[str] = Field(default=None, max_length=64)
    exchange_submit_execution_result_id: Optional[str] = Field(
        default=None,
        max_length=540,
    )
    post_submit_reconciliation_evidence_id: Optional[str] = Field(
        default=None,
        max_length=260,
    )
    submit_outcome_review_id: Optional[str] = Field(default=None, max_length=620)
    post_submit_budget_settlement_id: Optional[str] = Field(
        default=None,
        max_length=420,
    )
    status: RuntimePostSubmitFinalizeStatus
    submit_result_status: Optional[str] = Field(default=None, max_length=96)
    submit_outcome_review_status: Optional[str] = Field(default=None, max_length=96)
    post_submit_budget_settlement_status: Optional[str] = Field(
        default=None,
        max_length=96,
    )
    post_submit_finalize_complete: bool
    post_submit_reconciliation_matched: bool
    post_submit_budget_settled: bool
    submit_outcome_review_recorded: bool
    consumed_authorization_replay_only: Literal[True] = True
    old_authorization_submit_retry_allowed: Literal[False] = False
    pre_submit_rehearsal_retry_allowed: Literal[False] = False
    local_created_order_requirement_retired: Literal[True] = True
    next_attempt_gate: RuntimeNextAttemptGate
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    not_execution_authority: Literal[True] = True
    runtime_state_mutated_by_packet: Literal[False] = False
    execution_intent_created: Literal[False] = False
    order_created: Literal[False] = False
    order_cancelled: Literal[False] = False
    position_closed: Literal[False] = False
    exchange_called: Literal[False] = False
    exchange_order_submitted: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    owner_bounded_execution_called: Literal[False] = False
    withdrawal_or_transfer_created: Literal[False] = False
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_packet(self) -> "RuntimePostSubmitFinalizePacket":
        _reject_forbidden_metadata_fields({"metadata": self.metadata})
        if self.status == RuntimePostSubmitFinalizeStatus.BLOCKED:
            if not self.blockers:
                raise ValueError("blocked post-submit finalize packet requires blockers")
        elif self.blockers:
            raise ValueError("finalized post-submit packet cannot have blockers")
        if (
            self.status
            == RuntimePostSubmitFinalizeStatus.FINALIZED_READY_FOR_NEXT_ATTEMPT
            and self.next_attempt_gate.status
            != RuntimeNextAttemptGateStatus.READY_FOR_FRESH_SIGNAL
        ):
            raise ValueError("ready finalize packet requires ready next-attempt gate")
        if (
            self.status
            == RuntimePostSubmitFinalizeStatus.FINALIZED_NEXT_ATTEMPT_BLOCKED
            and self.next_attempt_gate.status != RuntimeNextAttemptGateStatus.BLOCKED
        ):
            raise ValueError("blocked next-attempt finalize packet requires gate block")
        if self.status != RuntimePostSubmitFinalizeStatus.BLOCKED:
            required_truth = {
                "post_submit_finalize_complete": self.post_submit_finalize_complete,
                "post_submit_reconciliation_matched": (
                    self.post_submit_reconciliation_matched
                ),
                "post_submit_budget_settled": self.post_submit_budget_settled,
                "submit_outcome_review_recorded": self.submit_outcome_review_recorded,
            }
            missing_truth = [
                name for name, value in required_truth.items() if value is not True
            ]
            if missing_truth:
                raise ValueError(
                    "finalized post-submit packet requires closed-loop truth: "
                    + ", ".join(missing_truth)
                )
        return self


def build_runtime_post_submit_finalize_packet(
    *,
    authorization_id: str,
    runtime: StrategyRuntimeInstance | None,
    exchange_submit_execution_result: (
        RuntimeExecutionExchangeSubmitExecutionResult | None
    ),
    submit_outcome_review: RuntimeExecutionSubmitOutcomeReview | None,
    post_submit_budget_settlement: RuntimeExecutionPostSubmitBudgetSettlement | None,
    active_positions_count: int | None,
    closed_review_required: bool,
    protection_blockers: list[str] | None = None,
    additional_blockers: list[str] | None = None,
    additional_warnings: list[str] | None = None,
    now_ms: int,
) -> RuntimePostSubmitFinalizePacket:
    blockers = list(additional_blockers or [])
    warnings = list(additional_warnings or [])
    warnings.extend(protection_blockers or [])

    runtime_instance_id = _runtime_id(
        runtime=runtime,
        exchange_submit_execution_result=exchange_submit_execution_result,
        submit_outcome_review=submit_outcome_review,
        post_submit_budget_settlement=post_submit_budget_settlement,
    )
    execution_intent_id = _execution_intent_id(
        exchange_submit_execution_result=exchange_submit_execution_result,
        submit_outcome_review=submit_outcome_review,
        post_submit_budget_settlement=post_submit_budget_settlement,
    )

    if exchange_submit_execution_result is None:
        blockers.append("exchange_submit_execution_result_missing")
    else:
        warnings.extend(exchange_submit_execution_result.warnings)
        if exchange_submit_execution_result.authorization_id != authorization_id:
            blockers.append("exchange_submit_execution_result_authorization_mismatch")
        if exchange_submit_execution_result.status in {
            RuntimeExecutionExchangeSubmitExecutionStatus.BLOCKED,
            RuntimeExecutionExchangeSubmitExecutionStatus
            .EXCHANGE_SUBMIT_EXECUTION_DISABLED,
            RuntimeExecutionExchangeSubmitExecutionStatus
            .EXCHANGE_SUBMIT_EXECUTION_LOCK_ACQUIRED,
        }:
            blockers.append("exchange_submit_execution_result_not_post_submit")
        if exchange_submit_execution_result.blockers:
            blockers.append("exchange_submit_execution_result_has_blockers")

    if submit_outcome_review is None:
        blockers.append("submit_outcome_review_missing")
    else:
        warnings.extend(submit_outcome_review.warnings)
        if submit_outcome_review.authorization_id != authorization_id:
            blockers.append("submit_outcome_review_authorization_mismatch")
        if submit_outcome_review.status != (
            RuntimeExecutionSubmitOutcomeReviewStatus
            .CLASSIFIED_READY_FOR_ATTEMPT_OUTCOME_POLICY
        ):
            blockers.append("submit_outcome_review_not_policy_ready")
        if submit_outcome_review.blockers:
            blockers.append("submit_outcome_review_has_blockers")

    if post_submit_budget_settlement is None:
        blockers.append("post_submit_budget_settlement_missing")
    else:
        warnings.extend(post_submit_budget_settlement.warnings)
        if post_submit_budget_settlement.authorization_id != authorization_id:
            blockers.append("post_submit_budget_settlement_authorization_mismatch")
        if post_submit_budget_settlement.status == (
            RuntimeExecutionPostSubmitBudgetSettlementStatus.BLOCKED
        ):
            blockers.append("post_submit_budget_settlement_blocked")
        if post_submit_budget_settlement.blockers:
            blockers.append("post_submit_budget_settlement_has_blockers")

    next_gate = _build_next_attempt_gate(
        runtime=runtime,
        runtime_instance_id=runtime_instance_id,
        active_positions_count=active_positions_count,
        closed_review_required=closed_review_required,
        settlement=post_submit_budget_settlement,
        protection_blockers=protection_blockers or [],
        prior_blockers=blockers,
    )
    if blockers:
        status = RuntimePostSubmitFinalizeStatus.BLOCKED
    elif next_gate.status == RuntimeNextAttemptGateStatus.BLOCKED:
        status = RuntimePostSubmitFinalizeStatus.FINALIZED_NEXT_ATTEMPT_BLOCKED
    else:
        status = RuntimePostSubmitFinalizeStatus.FINALIZED_READY_FOR_NEXT_ATTEMPT

    return RuntimePostSubmitFinalizePacket(
        packet_id=f"runtime-post-submit-finalize-{authorization_id}",
        authorization_id=authorization_id,
        runtime_instance_id=runtime_instance_id,
        execution_intent_id=execution_intent_id,
        exchange_submit_execution_result_id=(
            exchange_submit_execution_result.execution_result_id
            if exchange_submit_execution_result is not None
            else None
        ),
        post_submit_reconciliation_evidence_id=(
            submit_outcome_review.post_submit_reconciliation_evidence_id
            if submit_outcome_review is not None
            else None
        ),
        submit_outcome_review_id=(
            submit_outcome_review.review_id
            if submit_outcome_review is not None
            else None
        ),
        post_submit_budget_settlement_id=(
            post_submit_budget_settlement.settlement_id
            if post_submit_budget_settlement is not None
            else None
        ),
        status=status,
        submit_result_status=(
            exchange_submit_execution_result.status.value
            if exchange_submit_execution_result is not None
            else None
        ),
        submit_outcome_review_status=(
            submit_outcome_review.status.value
            if submit_outcome_review is not None
            else None
        ),
        post_submit_budget_settlement_status=(
            post_submit_budget_settlement.status.value
            if post_submit_budget_settlement is not None
            else None
        ),
        post_submit_finalize_complete=status
        != RuntimePostSubmitFinalizeStatus.BLOCKED,
        post_submit_reconciliation_matched=_post_submit_reconciliation_matched(
            submit_outcome_review
        ),
        post_submit_budget_settled=_post_submit_budget_settled(
            post_submit_budget_settlement
        ),
        submit_outcome_review_recorded=_submit_outcome_review_recorded(
            submit_outcome_review
        ),
        next_attempt_gate=next_gate,
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_post_submit_finalize",
            "freezes_consumed_authorization_as_replay_only": True,
            "does_not_run_pre_submit_rehearsal": True,
            "does_not_require_local_orders_created": True,
            "requires_fresh_signal_for_next_attempt": True,
        },
    )


def _post_submit_reconciliation_matched(
    review: RuntimeExecutionSubmitOutcomeReview | None,
) -> bool:
    if review is None:
        return False
    if review.status != (
        RuntimeExecutionSubmitOutcomeReviewStatus
        .CLASSIFIED_READY_FOR_ATTEMPT_OUTCOME_POLICY
    ):
        return False
    if review.blockers:
        return False
    if not review.post_submit_reconciliation_required:
        return True
    return (
        bool(review.post_submit_reconciliation_evidence_id)
        and review.post_submit_reconciliation_status == "clean"
        and review.post_submit_reconciliation_severe_count == 0
    )


def _post_submit_budget_settled(
    settlement: RuntimeExecutionPostSubmitBudgetSettlement | None,
) -> bool:
    if settlement is None:
        return False
    return (
        settlement.status != RuntimeExecutionPostSubmitBudgetSettlementStatus.BLOCKED
        and not settlement.blockers
        and (
            settlement.budget_released
            or settlement.budget_consumption_recorded
            or settlement.reserved_budget_remains_held
        )
    )


def _submit_outcome_review_recorded(
    review: RuntimeExecutionSubmitOutcomeReview | None,
) -> bool:
    if review is None:
        return False
    return (
        review.status
        == RuntimeExecutionSubmitOutcomeReviewStatus
        .CLASSIFIED_READY_FOR_ATTEMPT_OUTCOME_POLICY
        and review.attempt_outcome_policy_ready
        and not review.blockers
        and bool(review.review_id)
    )


def _build_next_attempt_gate(
    *,
    runtime: StrategyRuntimeInstance | None,
    runtime_instance_id: str,
    active_positions_count: int | None,
    closed_review_required: bool,
    settlement: RuntimeExecutionPostSubmitBudgetSettlement | None,
    protection_blockers: list[str],
    prior_blockers: list[str],
) -> RuntimeNextAttemptGate:
    blockers: list[str] = []
    warnings: list[str] = []
    attempts_remaining = 0
    budget_remaining: str | None = None
    max_active_positions = 0

    if prior_blockers:
        blockers.append("post_submit_finalize_not_complete")
    if runtime is None:
        blockers.append("runtime_missing")
    else:
        attempts_remaining = runtime.attempts_remaining
        budget_remaining = (
            str(runtime.budget_remaining)
            if runtime.budget_remaining is not None
            else None
        )
        max_active_positions = runtime.boundary.max_active_positions
        if runtime.status != StrategyRuntimeInstanceStatus.ACTIVE:
            blockers.append("runtime_not_active")
        if runtime.attempts_remaining <= 0:
            blockers.append("runtime_attempts_exhausted")
        if (
            runtime.budget_remaining is not None
            and runtime.budget_remaining <= 0
        ):
            blockers.append("runtime_budget_exhausted")

    if active_positions_count is None:
        blockers.append("trusted_active_positions_count_missing")
    elif runtime is not None and active_positions_count >= max_active_positions:
        blockers.append("runtime_active_position_slot_in_use")

    if settlement is not None and settlement.blocks_new_entries_until_resolved:
        blockers.append("post_submit_settlement_blocks_new_entries_until_resolved")
    if closed_review_required:
        blockers.append("closed_trade_review_required")
    blockers.extend(protection_blockers)

    status = (
        RuntimeNextAttemptGateStatus.BLOCKED
        if blockers
        else RuntimeNextAttemptGateStatus.READY_FOR_FRESH_SIGNAL
    )
    return RuntimeNextAttemptGate(
        status=status,
        runtime_instance_id=runtime_instance_id,
        attempts_remaining=attempts_remaining,
        budget_remaining=budget_remaining,
        active_positions_count=active_positions_count,
        max_active_positions=max_active_positions,
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
    )


def _runtime_id(
    *,
    runtime: StrategyRuntimeInstance | None,
    exchange_submit_execution_result: RuntimeExecutionExchangeSubmitExecutionResult | None,
    submit_outcome_review: RuntimeExecutionSubmitOutcomeReview | None,
    post_submit_budget_settlement: RuntimeExecutionPostSubmitBudgetSettlement | None,
) -> str:
    for item in (
        runtime,
        exchange_submit_execution_result,
        submit_outcome_review,
        post_submit_budget_settlement,
    ):
        value = getattr(item, "runtime_instance_id", None)
        if value:
            return str(value)
    return "unknown-runtime"


def _execution_intent_id(
    *,
    exchange_submit_execution_result: RuntimeExecutionExchangeSubmitExecutionResult | None,
    submit_outcome_review: RuntimeExecutionSubmitOutcomeReview | None,
    post_submit_budget_settlement: RuntimeExecutionPostSubmitBudgetSettlement | None,
) -> str | None:
    for item in (
        exchange_submit_execution_result,
        submit_outcome_review,
        post_submit_budget_settlement,
    ):
        value = getattr(item, "execution_intent_id", None)
        if value:
            return str(value)
    return None


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _reject_forbidden_metadata_fields(value: Any) -> None:
    forbidden = {
        "client_order_id",
        "exchange_order_id",
        "exchange_payload",
        "order_id",
        "place_order",
        "submit_order",
        "transfer_payload",
        "withdrawal_payload",
    }
    for key in _walk_keys(value):
        if key.lower() in forbidden:
            raise ValueError(
                "runtime post-submit finalize metadata contains forbidden "
                f"execution field: {key}"
            )


def _walk_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if isinstance(value, dict):
        for key, nested in value.items():
            keys.append(str(key))
            keys.extend(_walk_keys(nested))
    elif isinstance(value, list):
        for item in value:
            keys.extend(_walk_keys(item))
    return keys
