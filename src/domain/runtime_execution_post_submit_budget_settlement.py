"""Runtime budget settlement after a recorded exchange-submit outcome.

This model is the first post-submit state transition after outcome accounting.
It can release reserved runtime budget for no-fill/rejected outcomes or record
that the reserved budget remains held/consumed for filled outcomes. It never
creates orders, calls OrderLifecycle, calls an exchange, or changes attempt
counts.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.runtime_execution_attempt_mutation import (
    RuntimeExecutionAttemptMutation,
    RuntimeExecutionAttemptMutationStatus,
)
from src.domain.runtime_execution_attempt_outcome_policy import (
    RuntimeExecutionAttemptBudgetAction,
)
from src.domain.runtime_execution_first_real_submit_outcome_accounting import (
    RuntimeExecutionFirstRealSubmitOutcomeAccounting,
    RuntimeExecutionFirstRealSubmitOutcomeAccountingStatus,
)
from src.domain.strategy_runtime import (
    StrategyRuntimeBoundary,
    StrategyRuntimeInstance,
    StrategyRuntimeInstanceStatus,
)


class RuntimeExecutionPostSubmitBudgetSettlementModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeExecutionPostSubmitBudgetSettlementStatus(str, Enum):
    BLOCKED = "blocked"
    RELEASED_RESERVED_BUDGET = "released_reserved_budget"
    RECORDED_RESERVED_BUDGET_HELD = "recorded_reserved_budget_held"
    RECORDED_RESERVED_BUDGET_CONSUMED = "recorded_reserved_budget_consumed"


class RuntimeExecutionPostSubmitBudgetSettlement(
    RuntimeExecutionPostSubmitBudgetSettlementModel
):
    settlement_id: str = Field(min_length=1, max_length=420)
    accounting_id: str = Field(min_length=1, max_length=360)
    authorization_id: str = Field(min_length=1, max_length=220)
    execution_intent_id: str = Field(min_length=1, max_length=64)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    reservation_id: str = Field(min_length=1, max_length=260)
    mutation_id: Optional[str] = Field(default=None, max_length=320)
    attempt_outcome_policy_id: Optional[str] = Field(default=None, max_length=360)
    status: RuntimeExecutionPostSubmitBudgetSettlementStatus
    runtime_status_before: StrategyRuntimeInstanceStatus
    runtime_status_after: StrategyRuntimeInstanceStatus
    budget_action: Optional[RuntimeExecutionAttemptBudgetAction] = None
    outcome_kind: Optional[str] = Field(default=None, max_length=96)
    budget_reservation_amount: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    budget_release_amount: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    budget_reserved_before: Decimal = Field(ge=Decimal("0"))
    budget_reserved_after: Decimal = Field(ge=Decimal("0"))
    budget_remaining_before: Optional[Decimal] = None
    budget_remaining_after: Optional[Decimal] = None
    attempts_used_before: int = Field(ge=0)
    attempts_used_after: int = Field(ge=0)
    attempts_remaining_before: int = Field(ge=0)
    attempts_remaining_after: int = Field(ge=0)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    runtime_state_mutated: bool
    runtime_budget_mutated: bool
    attempt_counter_mutated: Literal[False] = False
    attempt_already_consumed: bool
    budget_released: bool
    budget_consumption_recorded: bool
    reserved_budget_remains_held: bool
    requires_reconciliation_before_retry: bool
    blocks_new_entries_until_resolved: bool
    not_execution_authority: Literal[True] = True
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
    def _validate_settlement(
        self,
    ) -> "RuntimeExecutionPostSubmitBudgetSettlement":
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
        for key in _walk_keys({"metadata": self.metadata}):
            if key.lower() in forbidden:
                raise ValueError(
                    "post-submit budget settlement contains forbidden execution "
                    f"field: {key}"
                )
        if self.status == RuntimeExecutionPostSubmitBudgetSettlementStatus.BLOCKED:
            if not self.blockers:
                raise ValueError("blocked budget settlement requires blockers")
            if (
                self.runtime_state_mutated
                or self.runtime_budget_mutated
                or self.budget_released
            ):
                raise ValueError("blocked budget settlement cannot mutate or release")
        else:
            if self.blockers:
                raise ValueError("applied budget settlement cannot have blockers")
            if not self.runtime_state_mutated:
                raise ValueError("applied budget settlement records runtime metadata")
        if self.runtime_budget_mutated and not self.budget_released:
            raise ValueError("runtime budget mutation currently means budget release")
        if self.budget_released:
            if self.status != (
                RuntimeExecutionPostSubmitBudgetSettlementStatus
                .RELEASED_RESERVED_BUDGET
            ):
                raise ValueError("budget release status mismatch")
            if self.budget_release_amount <= Decimal("0"):
                raise ValueError("budget release requires positive amount")
            if self.budget_reserved_after >= self.budget_reserved_before:
                raise ValueError("budget release must reduce reserved budget")
        if self.reserved_budget_remains_held and self.budget_released:
            raise ValueError("reserved budget cannot remain held and released")
        return self


def build_runtime_execution_post_submit_budget_settlement(
    *,
    accounting: RuntimeExecutionFirstRealSubmitOutcomeAccounting,
    mutation: RuntimeExecutionAttemptMutation | None,
    runtime: StrategyRuntimeInstance,
    now_ms: int,
) -> tuple[RuntimeExecutionPostSubmitBudgetSettlement, StrategyRuntimeInstance | None]:
    blockers: list[str] = []
    warnings = list(accounting.warnings)
    policy = accounting.attempt_outcome_policy
    action = policy.budget_action if policy is not None else None
    budget_reserved_before = runtime.boundary.budget_reserved
    budget_reserved_after = budget_reserved_before
    budget_remaining_before = runtime.budget_remaining
    budget_remaining_after = runtime.budget_remaining
    budget_release_amount = Decimal("0")
    status = RuntimeExecutionPostSubmitBudgetSettlementStatus.BLOCKED
    updated_runtime: StrategyRuntimeInstance | None = None

    if accounting.status != (
        RuntimeExecutionFirstRealSubmitOutcomeAccountingStatus
        .READY_FOR_ATTEMPT_BUDGET_OUTCOME_ACCOUNTING
    ):
        blockers.append("submit_outcome_accounting_not_ready")
    if policy is None:
        blockers.append("attempt_outcome_policy_missing")
    if accounting.runtime_instance_id != runtime.runtime_instance_id:
        blockers.append("runtime_instance_mismatch")
    if runtime.status != StrategyRuntimeInstanceStatus.ACTIVE:
        blockers.append("runtime_not_active")

    if mutation is None:
        blockers.append("attempt_mutation_missing")
    else:
        warnings.extend(mutation.warnings)
        if mutation.status != RuntimeExecutionAttemptMutationStatus.APPLIED:
            blockers.append("attempt_mutation_not_applied")
        if mutation.reservation_id != accounting.reservation_id:
            blockers.append("attempt_mutation_reservation_mismatch")
        if mutation.authorization_id != accounting.authorization_id:
            blockers.append("attempt_mutation_authorization_mismatch")
        if mutation.execution_intent_id != accounting.execution_intent_id:
            blockers.append("attempt_mutation_intent_mismatch")
        if mutation.runtime_instance_id != accounting.runtime_instance_id:
            blockers.append("attempt_mutation_runtime_mismatch")
        if runtime.boundary.attempts_used != mutation.attempts_used_after:
            blockers.append("runtime_attempt_state_drift")
        if runtime.attempts_remaining != mutation.attempts_remaining_after:
            blockers.append("runtime_attempt_remaining_drift")
        if runtime.boundary.budget_reserved != mutation.budget_reserved_after:
            blockers.append("runtime_budget_reserved_drift")

    if policy is not None:
        if policy.policy_id != accounting.attempt_outcome_policy_id:
            blockers.append("attempt_outcome_policy_id_mismatch")
        if policy.reservation_id != accounting.reservation_id:
            blockers.append("attempt_outcome_policy_reservation_mismatch")
        if action == RuntimeExecutionAttemptBudgetAction.RELEASE_RESERVED_BUDGET:
            if policy.budget_reservation_amount is None:
                blockers.append("budget_reservation_amount_missing")
            else:
                budget_release_amount = policy.budget_reservation_amount
                if budget_release_amount > budget_reserved_before:
                    blockers.append("budget_release_exceeds_reserved_budget")
        elif action == (
            RuntimeExecutionAttemptBudgetAction
            .HOLD_RESERVED_BUDGET_UNTIL_POSITION_RESOLVED
        ):
            pass
        elif action == (
            RuntimeExecutionAttemptBudgetAction
            .CONFIRM_RESERVED_BUDGET_CONSUMED
        ):
            pass
        elif action == (
            RuntimeExecutionAttemptBudgetAction
            .RECONCILE_AND_RELEASE_REMAINDER
        ):
            blockers.append("reconciliation_required_before_budget_settlement")
        elif action == RuntimeExecutionAttemptBudgetAction.NO_RESERVATION_TO_RELEASE:
            blockers.append("no_reserved_budget_settlement_for_preflight_blocked")
        else:
            blockers.append("attempt_outcome_policy_budget_action_missing")

    if not blockers and policy is not None:
        metadata_action = str(policy.budget_action.value)
        if action == RuntimeExecutionAttemptBudgetAction.RELEASE_RESERVED_BUDGET:
            budget_reserved_after = budget_reserved_before - budget_release_amount
            status = (
                RuntimeExecutionPostSubmitBudgetSettlementStatus
                .RELEASED_RESERVED_BUDGET
            )
        elif action == (
            RuntimeExecutionAttemptBudgetAction
            .HOLD_RESERVED_BUDGET_UNTIL_POSITION_RESOLVED
        ):
            status = (
                RuntimeExecutionPostSubmitBudgetSettlementStatus
                .RECORDED_RESERVED_BUDGET_HELD
            )
        elif action == (
            RuntimeExecutionAttemptBudgetAction
            .CONFIRM_RESERVED_BUDGET_CONSUMED
        ):
            status = (
                RuntimeExecutionPostSubmitBudgetSettlementStatus
                .RECORDED_RESERVED_BUDGET_CONSUMED
            )

        next_boundary = StrategyRuntimeBoundary.model_validate(
            {
                **runtime.boundary.model_dump(mode="python"),
                "budget_reserved": budget_reserved_after,
            }
        )
        metadata = dict(runtime.metadata)
        metadata.update(
            {
                "last_post_submit_budget_settlement_id": _settlement_id(
                    accounting.accounting_id
                ),
                "last_post_submit_outcome_accounting_id": accounting.accounting_id,
                "last_post_submit_budget_action": metadata_action,
                "last_post_submit_outcome_kind": (
                    policy.outcome_kind.value if policy.outcome_kind else None
                ),
                "last_post_submit_budget_release_amount": str(budget_release_amount),
                "last_post_submit_reserved_budget_before": str(
                    budget_reserved_before
                ),
                "last_post_submit_reserved_budget_after": str(
                    budget_reserved_after
                ),
            }
        )
        updated_runtime = runtime.model_copy(
            update={
                "boundary": next_boundary,
                "updated_at_ms": now_ms,
                "metadata": metadata,
            }
        )
        budget_remaining_after = updated_runtime.budget_remaining

    return (
        RuntimeExecutionPostSubmitBudgetSettlement(
            settlement_id=_settlement_id(accounting.accounting_id),
            accounting_id=accounting.accounting_id,
            authorization_id=accounting.authorization_id,
            execution_intent_id=accounting.execution_intent_id,
            runtime_instance_id=runtime.runtime_instance_id,
            reservation_id=accounting.reservation_id,
            mutation_id=mutation.mutation_id if mutation is not None else None,
            attempt_outcome_policy_id=accounting.attempt_outcome_policy_id,
            status=status,
            runtime_status_before=runtime.status,
            runtime_status_after=(
                updated_runtime.status if updated_runtime is not None else runtime.status
            ),
            budget_action=action,
            outcome_kind=policy.outcome_kind.value if policy is not None else None,
            budget_reservation_amount=(
                policy.budget_reservation_amount if policy is not None else None
            ),
            budget_release_amount=budget_release_amount,
            budget_reserved_before=budget_reserved_before,
            budget_reserved_after=budget_reserved_after,
            budget_remaining_before=budget_remaining_before,
            budget_remaining_after=budget_remaining_after,
            attempts_used_before=runtime.boundary.attempts_used,
            attempts_used_after=(
                updated_runtime.boundary.attempts_used
                if updated_runtime is not None
                else runtime.boundary.attempts_used
            ),
            attempts_remaining_before=runtime.attempts_remaining,
            attempts_remaining_after=(
                updated_runtime.attempts_remaining
                if updated_runtime is not None
                else runtime.attempts_remaining
            ),
            blockers=_dedupe(blockers),
            warnings=_dedupe(warnings),
            runtime_state_mutated=updated_runtime is not None,
            runtime_budget_mutated=(
                updated_runtime is not None
                and budget_reserved_after != budget_reserved_before
            ),
            attempt_already_consumed=(
                mutation.attempt_consumed if mutation is not None else False
            ),
            budget_released=(
                status
                == RuntimeExecutionPostSubmitBudgetSettlementStatus
                .RELEASED_RESERVED_BUDGET
            ),
            budget_consumption_recorded=(
                action
                == RuntimeExecutionAttemptBudgetAction
                .CONFIRM_RESERVED_BUDGET_CONSUMED
            ),
            reserved_budget_remains_held=(
                action
                == RuntimeExecutionAttemptBudgetAction
                .HOLD_RESERVED_BUDGET_UNTIL_POSITION_RESOLVED
            ),
            requires_reconciliation_before_retry=(
                policy.requires_reconciliation_before_retry
                if policy is not None
                else False
            ),
            blocks_new_entries_until_resolved=(
                policy.blocks_new_entries_until_resolved
                if policy is not None
                else False
            ),
            created_at_ms=now_ms,
            metadata={
                "scope": "runtime_execution_post_submit_budget_settlement",
                "derived_from_accounting_id": accounting.accounting_id,
                "derived_from_attempt_outcome_policy_id": (
                    accounting.attempt_outcome_policy_id
                ),
                "derived_from_attempt_mutation_id": (
                    mutation.mutation_id if mutation is not None else None
                ),
                "budget_action": action.value if action is not None else None,
                "mutates_runtime_metadata": updated_runtime is not None,
                "mutates_runtime_budget_reserved": (
                    updated_runtime is not None
                    and budget_reserved_after != budget_reserved_before
                ),
                "does_not_change_attempt_counter": True,
                "does_not_change_execution_intent_status": True,
                "does_not_create_cancel_or_close_orders": True,
                "does_not_call_order_lifecycle": True,
                "does_not_call_exchange": True,
                "does_not_create_withdrawal_or_transfer": True,
            },
        ),
        updated_runtime,
    )


def _settlement_id(accounting_id: str) -> str:
    return f"runtime-post-submit-budget-settlement-{accounting_id}"


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


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
