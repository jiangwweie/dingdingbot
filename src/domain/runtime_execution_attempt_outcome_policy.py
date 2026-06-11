"""Non-executing attempt/budget outcome accounting policy.

This model freezes how a future real submit outcome should affect attempt
consumption and reserved budget accounting. It does not release budget, mutate
runtime state, create or cancel orders, close positions, or call an exchange.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.runtime_execution_attempt_mutation import (
    RuntimeExecutionAttemptMutation,
    RuntimeExecutionAttemptMutationStatus,
)
from src.domain.runtime_execution_attempt_reservation import (
    RuntimeExecutionAttemptReservation,
    RuntimeExecutionAttemptReservationStatus,
)


class RuntimeExecutionAttemptOutcomePolicyModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeExecutionAttemptOutcomeKind(str, Enum):
    PREFLIGHT_BLOCKED = "preflight_blocked"
    SUBMIT_REJECTED_BEFORE_EXCHANGE = "submit_rejected_before_exchange"
    SUBMITTED_NO_FILL_CANCELLED = "submitted_no_fill_cancelled"
    SUBMITTED_NO_FILL_EXPIRED = "submitted_no_fill_expired"
    SUBMITTED_PARTIAL_FILL = "submitted_partial_fill"
    SUBMITTED_FULL_FILL = "submitted_full_fill"
    ENTRY_FILLED_PROTECTION_CREATION_FAILED = (
        "entry_filled_protection_creation_failed"
    )
    POSITION_CLOSED_AFTER_FILL = "position_closed_after_fill"
    RECOVERY_RESOLVED = "recovery_resolved"


class RuntimeExecutionAttemptBudgetAction(str, Enum):
    NO_RESERVATION_TO_RELEASE = "no_reservation_to_release"
    RELEASE_RESERVED_BUDGET = "release_reserved_budget"
    CONFIRM_RESERVED_BUDGET_CONSUMED = "confirm_reserved_budget_consumed"
    HOLD_RESERVED_BUDGET_UNTIL_POSITION_RESOLVED = (
        "hold_reserved_budget_until_position_resolved"
    )
    RECONCILE_AND_RELEASE_REMAINDER = "reconcile_and_release_remainder"


class RuntimeExecutionAttemptOutcomePolicyStatus(str, Enum):
    BLOCKED = "blocked"
    READY_FOR_ATTEMPT_BUDGET_OUTCOME_ACCOUNTING = (
        "ready_for_attempt_budget_outcome_accounting"
    )


class RuntimeExecutionAttemptOutcomePolicy(
    RuntimeExecutionAttemptOutcomePolicyModel
):
    policy_id: str = Field(min_length=1, max_length=360)
    reservation_id: str = Field(min_length=1, max_length=260)
    reservation_preview_id: str = Field(min_length=1, max_length=260)
    mutation_id: Optional[str] = Field(default=None, max_length=320)
    authorization_id: str = Field(min_length=1, max_length=220)
    execution_intent_id: str = Field(min_length=1, max_length=64)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    source_id: Optional[str] = Field(default=None, max_length=128)
    semantic_ids: BrcSemanticIds
    status: RuntimeExecutionAttemptOutcomePolicyStatus
    outcome_kind: RuntimeExecutionAttemptOutcomeKind
    budget_action: RuntimeExecutionAttemptBudgetAction
    symbol: str = Field(min_length=1, max_length=128)
    side: Optional[str] = Field(default=None, max_length=32)
    any_fill: bool
    partial_fill: bool = False
    submitted_to_exchange: bool
    protection_creation_failed: bool = False
    attempt_should_be_consumed: bool
    budget_release_allowed: bool
    budget_consumption_confirmed: bool
    reserved_budget_should_remain_held: bool
    requires_reconciliation_before_retry: bool
    requires_owner_recovery_review: bool
    requires_reduce_only_recovery_mode: bool
    blocks_new_entries_until_resolved: bool
    partial_fill_counts_as_attempt: Literal[True] = True
    no_second_free_attempt_after_partial_fill: Literal[True] = True
    preflight_blocked_consumes_attempt: Literal[False] = False
    budget_reservation_basis: Optional[str] = Field(default=None, max_length=96)
    budget_reservation_amount: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    budget_reserved_before: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    budget_reserved_after: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    not_execution_authority: Literal[True] = True
    not_budget_mutation_authority: Literal[True] = True
    runtime_state_mutated: Literal[False] = False
    attempt_counter_mutated: Literal[False] = False
    budget_released: Literal[False] = False
    execution_intent_status_changed: Literal[False] = False
    order_created: Literal[False] = False
    order_cancelled: Literal[False] = False
    position_closed: Literal[False] = False
    exchange_called: Literal[False] = False
    exchange_order_submitted: Literal[False] = False
    owner_bounded_execution_called: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    withdrawal_instruction_created: Literal[False] = False
    transfer_instruction_created: Literal[False] = False
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_policy(self) -> "RuntimeExecutionAttemptOutcomePolicy":
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
                    "attempt outcome policy contains forbidden execution field: "
                    f"{key}"
                )
        if (
            self.status
            == RuntimeExecutionAttemptOutcomePolicyStatus
            .READY_FOR_ATTEMPT_BUDGET_OUTCOME_ACCOUNTING
            and self.blockers
        ):
            raise ValueError("ready attempt outcome policy cannot have blockers")
        if self.any_fill and not self.attempt_should_be_consumed:
            raise ValueError("any fill must consume the attempt")
        if self.partial_fill and not self.any_fill:
            raise ValueError("partial fill requires any_fill")
        if self.protection_creation_failed and not self.any_fill:
            raise ValueError("protection failure outcome requires a fill")
        if self.budget_release_allowed and self.reserved_budget_should_remain_held:
            raise ValueError("budget cannot be released and held at the same time")
        return self


def build_runtime_execution_attempt_outcome_policy(
    *,
    reservation: RuntimeExecutionAttemptReservation,
    outcome_kind: RuntimeExecutionAttemptOutcomeKind,
    now_ms: int,
    mutation: RuntimeExecutionAttemptMutation | None = None,
) -> RuntimeExecutionAttemptOutcomePolicy:
    blockers: list[str] = []
    warnings = list(reservation.warnings)
    if mutation is not None:
        warnings.extend(mutation.warnings)
    if outcome_kind == RuntimeExecutionAttemptOutcomeKind.PREFLIGHT_BLOCKED:
        if reservation.status != RuntimeExecutionAttemptReservationStatus.BLOCKED:
            blockers.append("preflight_blocked_outcome_requires_blocked_reservation")
    else:
        if reservation.status != (
            RuntimeExecutionAttemptReservationStatus.PENDING_RUNTIME_MUTATION
        ):
            blockers.append("outcome_requires_pending_runtime_mutation_reservation")
        if mutation is None:
            blockers.append("attempt_mutation_record_missing")
        elif mutation.status != RuntimeExecutionAttemptMutationStatus.APPLIED:
            blockers.append("attempt_mutation_not_applied")

    if mutation is not None:
        if mutation.reservation_id != reservation.reservation_id:
            blockers.append("attempt_mutation_reservation_mismatch")
        if mutation.authorization_id != reservation.authorization_id:
            blockers.append("attempt_mutation_authorization_mismatch")
        if mutation.execution_intent_id != reservation.execution_intent_id:
            blockers.append("attempt_mutation_intent_mismatch")
        if mutation.runtime_instance_id != reservation.runtime_instance_id:
            blockers.append("attempt_mutation_runtime_mismatch")

    rule = _outcome_rule(outcome_kind)
    status = (
        RuntimeExecutionAttemptOutcomePolicyStatus.BLOCKED
        if blockers
        else RuntimeExecutionAttemptOutcomePolicyStatus
        .READY_FOR_ATTEMPT_BUDGET_OUTCOME_ACCOUNTING
    )
    budget_reservation_amount = _metadata_decimal(
        reservation.metadata.get("budget_reservation_amount")
    )
    budget_reserved_before = (
        mutation.budget_reserved_before if mutation is not None else None
    )
    budget_reserved_after = mutation.budget_reserved_after if mutation is not None else None
    return RuntimeExecutionAttemptOutcomePolicy(
        policy_id=(
            "runtime-attempt-outcome-policy-"
            f"{reservation.reservation_id}-{outcome_kind.value}"
        ),
        reservation_id=reservation.reservation_id,
        reservation_preview_id=reservation.reservation_preview_id,
        mutation_id=mutation.mutation_id if mutation is not None else None,
        authorization_id=reservation.authorization_id,
        execution_intent_id=reservation.execution_intent_id,
        runtime_instance_id=reservation.runtime_instance_id,
        source_id=reservation.source_id,
        semantic_ids=reservation.semantic_ids,
        status=status,
        outcome_kind=outcome_kind,
        budget_action=rule["budget_action"],
        symbol=reservation.symbol,
        side=reservation.side,
        any_fill=rule["any_fill"],
        partial_fill=rule["partial_fill"],
        submitted_to_exchange=rule["submitted_to_exchange"],
        protection_creation_failed=rule["protection_creation_failed"],
        attempt_should_be_consumed=rule["attempt_should_be_consumed"],
        budget_release_allowed=rule["budget_release_allowed"],
        budget_consumption_confirmed=rule["budget_consumption_confirmed"],
        reserved_budget_should_remain_held=rule[
            "reserved_budget_should_remain_held"
        ],
        requires_reconciliation_before_retry=rule[
            "requires_reconciliation_before_retry"
        ],
        requires_owner_recovery_review=rule["requires_owner_recovery_review"],
        requires_reduce_only_recovery_mode=rule[
            "requires_reduce_only_recovery_mode"
        ],
        blocks_new_entries_until_resolved=rule[
            "blocks_new_entries_until_resolved"
        ],
        budget_reservation_basis=_optional_str(
            reservation.metadata.get("budget_reservation_basis")
        ),
        budget_reservation_amount=budget_reservation_amount,
        budget_reserved_before=budget_reserved_before,
        budget_reserved_after=budget_reserved_after,
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_attempt_outcome_policy",
            "non_executing_outcome_accounting_policy": True,
            "release_or_consume_rule_evidence": True,
            "does_not_release_budget": True,
            "does_not_mutate_runtime_state": True,
            "does_not_increment_or_decrement_attempt_counter": True,
            "does_not_change_execution_intent_status": True,
            "does_not_create_cancel_or_close_orders": True,
            "does_not_call_order_lifecycle": True,
            "does_not_call_exchange": True,
            "does_not_create_withdrawal_or_transfer": True,
        },
    )


def _outcome_rule(outcome_kind: RuntimeExecutionAttemptOutcomeKind) -> dict[str, Any]:
    if outcome_kind == RuntimeExecutionAttemptOutcomeKind.PREFLIGHT_BLOCKED:
        return _rule(
            budget_action=RuntimeExecutionAttemptBudgetAction.NO_RESERVATION_TO_RELEASE,
        )
    if outcome_kind == RuntimeExecutionAttemptOutcomeKind.SUBMIT_REJECTED_BEFORE_EXCHANGE:
        return _rule(
            budget_action=RuntimeExecutionAttemptBudgetAction.RELEASE_RESERVED_BUDGET,
            budget_release_allowed=True,
        )
    if outcome_kind in {
        RuntimeExecutionAttemptOutcomeKind.SUBMITTED_NO_FILL_CANCELLED,
        RuntimeExecutionAttemptOutcomeKind.SUBMITTED_NO_FILL_EXPIRED,
    }:
        return _rule(
            budget_action=RuntimeExecutionAttemptBudgetAction.RELEASE_RESERVED_BUDGET,
            submitted_to_exchange=True,
            budget_release_allowed=True,
            requires_reconciliation_before_retry=True,
        )
    if outcome_kind == RuntimeExecutionAttemptOutcomeKind.SUBMITTED_PARTIAL_FILL:
        return _rule(
            budget_action=(
                RuntimeExecutionAttemptBudgetAction
                .HOLD_RESERVED_BUDGET_UNTIL_POSITION_RESOLVED
            ),
            submitted_to_exchange=True,
            any_fill=True,
            partial_fill=True,
            attempt_should_be_consumed=True,
            reserved_budget_should_remain_held=True,
            requires_reconciliation_before_retry=True,
        )
    if outcome_kind == RuntimeExecutionAttemptOutcomeKind.SUBMITTED_FULL_FILL:
        return _rule(
            budget_action=(
                RuntimeExecutionAttemptBudgetAction
                .CONFIRM_RESERVED_BUDGET_CONSUMED
            ),
            submitted_to_exchange=True,
            any_fill=True,
            attempt_should_be_consumed=True,
            budget_consumption_confirmed=True,
        )
    if (
        outcome_kind
        == RuntimeExecutionAttemptOutcomeKind.ENTRY_FILLED_PROTECTION_CREATION_FAILED
    ):
        return _rule(
            budget_action=(
                RuntimeExecutionAttemptBudgetAction
                .HOLD_RESERVED_BUDGET_UNTIL_POSITION_RESOLVED
            ),
            submitted_to_exchange=True,
            any_fill=True,
            attempt_should_be_consumed=True,
            protection_creation_failed=True,
            reserved_budget_should_remain_held=True,
            requires_reconciliation_before_retry=True,
            requires_owner_recovery_review=True,
            requires_reduce_only_recovery_mode=True,
            blocks_new_entries_until_resolved=True,
        )
    return _rule(
        budget_action=(
            RuntimeExecutionAttemptBudgetAction.RECONCILE_AND_RELEASE_REMAINDER
        ),
        submitted_to_exchange=True,
        any_fill=True,
        attempt_should_be_consumed=True,
        requires_reconciliation_before_retry=True,
    )


def _rule(
    *,
    budget_action: RuntimeExecutionAttemptBudgetAction,
    submitted_to_exchange: bool = False,
    any_fill: bool = False,
    partial_fill: bool = False,
    protection_creation_failed: bool = False,
    attempt_should_be_consumed: bool = False,
    budget_release_allowed: bool = False,
    budget_consumption_confirmed: bool = False,
    reserved_budget_should_remain_held: bool = False,
    requires_reconciliation_before_retry: bool = False,
    requires_owner_recovery_review: bool = False,
    requires_reduce_only_recovery_mode: bool = False,
    blocks_new_entries_until_resolved: bool = False,
) -> dict[str, Any]:
    return {
        "budget_action": budget_action,
        "submitted_to_exchange": submitted_to_exchange,
        "any_fill": any_fill,
        "partial_fill": partial_fill,
        "protection_creation_failed": protection_creation_failed,
        "attempt_should_be_consumed": attempt_should_be_consumed,
        "budget_release_allowed": budget_release_allowed,
        "budget_consumption_confirmed": budget_consumption_confirmed,
        "reserved_budget_should_remain_held": reserved_budget_should_remain_held,
        "requires_reconciliation_before_retry": requires_reconciliation_before_retry,
        "requires_owner_recovery_review": requires_owner_recovery_review,
        "requires_reduce_only_recovery_mode": requires_reduce_only_recovery_mode,
        "blocks_new_entries_until_resolved": blocks_new_entries_until_resolved,
    }


def _metadata_decimal(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value)
    return text if text else None


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
