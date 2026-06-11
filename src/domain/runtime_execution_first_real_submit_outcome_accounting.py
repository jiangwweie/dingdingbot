"""Post-submit accounting packet for the first real runtime submit.

This packet links a recorded exchange-submit outcome review to the
attempt-outcome policy derived from it. It is accounting evidence only: it does
not mutate runtime state, release budget, create/cancel orders, or call an
exchange.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.runtime_execution_attempt_outcome_policy import (
    RuntimeExecutionAttemptOutcomeKind,
    RuntimeExecutionAttemptOutcomePolicy,
    RuntimeExecutionAttemptOutcomePolicyStatus,
)
from src.domain.runtime_execution_submit_outcome_review import (
    RuntimeExecutionSubmitObservedOutcome,
    RuntimeExecutionSubmitOutcomeReview,
    RuntimeExecutionSubmitOutcomeReviewStatus,
)


class RuntimeExecutionFirstRealSubmitOutcomeAccountingModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeExecutionFirstRealSubmitOutcomeAccountingStatus(str, Enum):
    BLOCKED = "blocked"
    READY_FOR_ATTEMPT_BUDGET_OUTCOME_ACCOUNTING = (
        "ready_for_attempt_budget_outcome_accounting"
    )


class RuntimeExecutionFirstRealSubmitOutcomeAccounting(
    RuntimeExecutionFirstRealSubmitOutcomeAccountingModel
):
    accounting_id: str = Field(min_length=1, max_length=360)
    authorization_id: str = Field(min_length=1, max_length=220)
    execution_intent_id: str = Field(min_length=1, max_length=64)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    reservation_id: str = Field(min_length=1, max_length=260)
    submit_outcome_review_id: str = Field(min_length=1, max_length=620)
    attempt_outcome_policy_id: Optional[str] = Field(default=None, max_length=360)
    status: RuntimeExecutionFirstRealSubmitOutcomeAccountingStatus
    observed_outcome: RuntimeExecutionSubmitObservedOutcome
    outcome_kind: Optional[RuntimeExecutionAttemptOutcomeKind] = None
    submit_outcome_review: RuntimeExecutionSubmitOutcomeReview
    attempt_outcome_policy: Optional[RuntimeExecutionAttemptOutcomePolicy] = None
    attempt_should_be_consumed: bool = False
    budget_release_allowed: bool = False
    budget_consumption_confirmed: bool = False
    reserved_budget_should_remain_held: bool = False
    requires_reconciliation_before_retry: bool = False
    blocks_new_entries_until_resolved: bool = False
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    not_execution_authority: Literal[True] = True
    not_budget_mutation_authority: Literal[True] = True
    runtime_state_mutated: Literal[False] = False
    attempt_counter_mutated: Literal[False] = False
    budget_released: Literal[False] = False
    budget_consumed: Literal[False] = False
    execution_intent_status_changed: Literal[False] = False
    order_created: Literal[False] = False
    order_cancelled: Literal[False] = False
    position_closed: Literal[False] = False
    exchange_called: Literal[False] = False
    exchange_order_submitted: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    owner_bounded_execution_called: Literal[False] = False
    withdrawal_instruction_created: Literal[False] = False
    transfer_instruction_created: Literal[False] = False
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_accounting(
        self,
    ) -> "RuntimeExecutionFirstRealSubmitOutcomeAccounting":
        if (
            self.status
            == RuntimeExecutionFirstRealSubmitOutcomeAccountingStatus
            .READY_FOR_ATTEMPT_BUDGET_OUTCOME_ACCOUNTING
        ):
            if self.blockers:
                raise ValueError("ready submit outcome accounting cannot have blockers")
            if self.attempt_outcome_policy is None:
                raise ValueError("ready submit outcome accounting requires policy")
            if self.attempt_outcome_policy_id is None:
                raise ValueError("ready submit outcome accounting requires policy id")
        if (
            self.status
            == RuntimeExecutionFirstRealSubmitOutcomeAccountingStatus.BLOCKED
            and not self.blockers
        ):
            raise ValueError("blocked submit outcome accounting requires blockers")
        return self


def build_runtime_execution_first_real_submit_outcome_accounting(
    *,
    reservation_id: str,
    submit_outcome_review: RuntimeExecutionSubmitOutcomeReview,
    attempt_outcome_policy: RuntimeExecutionAttemptOutcomePolicy | None,
    now_ms: int,
    additional_blockers: list[str] | None = None,
    additional_warnings: list[str] | None = None,
) -> RuntimeExecutionFirstRealSubmitOutcomeAccounting:
    review = submit_outcome_review
    policy = attempt_outcome_policy
    blockers = list(additional_blockers or [])
    warnings = list(review.warnings)
    warnings.extend(additional_warnings or [])

    if review.status != (
        RuntimeExecutionSubmitOutcomeReviewStatus
        .CLASSIFIED_READY_FOR_ATTEMPT_OUTCOME_POLICY
    ):
        blockers.append("submit_outcome_review_not_policy_ready")
    if not review.attempt_outcome_policy_ready:
        blockers.append("submit_outcome_review_policy_ready_false")
    if review.recommended_attempt_outcome_kind is None:
        blockers.append("submit_outcome_review_recommended_outcome_missing")

    if policy is None:
        blockers.append("attempt_outcome_policy_not_recorded")
    else:
        warnings.extend(policy.warnings)
        if policy.status != (
            RuntimeExecutionAttemptOutcomePolicyStatus
            .READY_FOR_ATTEMPT_BUDGET_OUTCOME_ACCOUNTING
        ):
            blockers.append("attempt_outcome_policy_not_ready")
        if policy.reservation_id != reservation_id:
            blockers.append("attempt_outcome_policy_reservation_mismatch")
        if policy.authorization_id != review.authorization_id:
            blockers.append("attempt_outcome_policy_authorization_mismatch")
        if policy.execution_intent_id != review.execution_intent_id:
            blockers.append("attempt_outcome_policy_intent_mismatch")
        if policy.runtime_instance_id != review.runtime_instance_id:
            blockers.append("attempt_outcome_policy_runtime_mismatch")
        if (
            review.recommended_attempt_outcome_kind is not None
            and policy.outcome_kind != review.recommended_attempt_outcome_kind
        ):
            blockers.append("attempt_outcome_policy_kind_mismatch")

    status = (
        RuntimeExecutionFirstRealSubmitOutcomeAccountingStatus.BLOCKED
        if blockers
        else RuntimeExecutionFirstRealSubmitOutcomeAccountingStatus
        .READY_FOR_ATTEMPT_BUDGET_OUTCOME_ACCOUNTING
    )
    return RuntimeExecutionFirstRealSubmitOutcomeAccounting(
        accounting_id=(
            "runtime-first-real-submit-outcome-accounting-"
            f"{review.authorization_id}"
        ),
        authorization_id=review.authorization_id,
        execution_intent_id=review.execution_intent_id,
        runtime_instance_id=review.runtime_instance_id,
        reservation_id=reservation_id,
        submit_outcome_review_id=review.review_id,
        attempt_outcome_policy_id=policy.policy_id if policy else None,
        status=status,
        observed_outcome=review.observed_outcome,
        outcome_kind=policy.outcome_kind if policy else None,
        submit_outcome_review=review,
        attempt_outcome_policy=policy,
        attempt_should_be_consumed=(
            policy.attempt_should_be_consumed if policy else False
        ),
        budget_release_allowed=policy.budget_release_allowed if policy else False,
        budget_consumption_confirmed=(
            policy.budget_consumption_confirmed if policy else False
        ),
        reserved_budget_should_remain_held=(
            policy.reserved_budget_should_remain_held if policy else False
        ),
        requires_reconciliation_before_retry=(
            policy.requires_reconciliation_before_retry if policy else False
        ),
        blocks_new_entries_until_resolved=(
            policy.blocks_new_entries_until_resolved if policy else False
        ),
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_first_real_submit_outcome_accounting",
            "post_submit_accounting_evidence": True,
            "submit_outcome_review_id": review.review_id,
            "attempt_outcome_policy_id": policy.policy_id if policy else None,
            "does_not_release_budget": True,
            "does_not_mutate_runtime_state": True,
            "does_not_change_execution_intent_status": True,
            "does_not_create_cancel_or_close_orders": True,
            "does_not_call_order_lifecycle": True,
            "does_not_call_exchange": True,
            "does_not_create_withdrawal_or_transfer": True,
        },
    )


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
