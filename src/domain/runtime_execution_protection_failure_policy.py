"""Non-executing policy for entry-filled/protection-create-failed incidents.

This model defines what must be true before a future real submit adapter may
approach the exchange stage. It does not create recovery orders, flatten
positions, call OrderLifecycle, or call an exchange.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.runtime_execution_protection_plan import (
    RuntimeExecutionProtectionPlan,
    RuntimeExecutionProtectionPlanStatus,
)


class RuntimeExecutionProtectionFailurePolicyModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeExecutionProtectionFailurePolicyStatus(str, Enum):
    BLOCKED = "blocked"
    READY_FOR_FIRST_REAL_SUBMIT_CONFIRMATION = (
        "ready_for_first_real_submit_confirmation"
    )


class RuntimeExecutionProtectionFailurePolicy(
    RuntimeExecutionProtectionFailurePolicyModel
):
    policy_id: str = Field(min_length=1, max_length=300)
    protection_plan_id: str = Field(min_length=1, max_length=260)
    execution_intent_id: str = Field(min_length=1, max_length=64)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    source_type: Optional[str] = Field(default=None, max_length=64)
    source_id: Optional[str] = Field(default=None, max_length=128)
    semantic_ids: BrcSemanticIds
    status: RuntimeExecutionProtectionFailurePolicyStatus
    symbol: str = Field(min_length=1, max_length=128)
    side: Optional[str] = Field(default=None, max_length=32)
    incident_kind: Literal["entry_filled_protection_creation_failed"] = (
        "entry_filled_protection_creation_failed"
    )
    response_mode: Literal["fail_closed_unprotected_position_recovery"] = (
        "fail_closed_unprotected_position_recovery"
    )
    block_new_entries_until_resolved: bool = True
    mark_position_unprotected_until_verified: bool = True
    require_owner_recovery_review: bool = True
    require_reduce_only_recovery_mode: bool = True
    require_reconciliation_before_retry: bool = True
    consume_attempt_on_any_fill: bool = True
    hold_or_reconcile_budget_until_position_resolved: bool = True
    must_not_mark_unprotected_position_as_protected: bool = True
    recovery_actions: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    not_execution_authority: Literal[True] = True
    not_exchange_order_authority: Literal[True] = True
    order_created: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    exchange_called: Literal[False] = False
    exchange_order_submitted: Literal[False] = False
    owner_bounded_execution_called: Literal[False] = False
    execution_intent_status_changed: Literal[False] = False
    withdrawal_or_transfer_created: Literal[False] = False
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_policy(self) -> "RuntimeExecutionProtectionFailurePolicy":
        forbidden = {
            "client_order_id",
            "exchange_order_id",
            "exchange_payload",
            "order_id",
            "place_order",
            "submit_order",
        }
        for key in _walk_keys({"metadata": self.metadata}):
            if key.lower() in forbidden:
                raise ValueError(
                    f"protection failure policy contains forbidden execution field: {key}"
                )
        if self.exchange_called or self.exchange_order_submitted:
            raise ValueError("protection failure policy cannot call exchange")
        if self.order_created or self.order_lifecycle_called:
            raise ValueError(
                "protection failure policy cannot create/register orders"
            )
        if self.owner_bounded_execution_called:
            raise ValueError(
                "protection failure policy cannot call OwnerBoundedExecution"
            )
        if self.execution_intent_status_changed:
            raise ValueError(
                "protection failure policy cannot change ExecutionIntent status"
            )
        if self.withdrawal_or_transfer_created:
            raise ValueError(
                "protection failure policy cannot create withdrawal/transfer"
            )
        if (
            self.status
            == RuntimeExecutionProtectionFailurePolicyStatus
            .READY_FOR_FIRST_REAL_SUBMIT_CONFIRMATION
            and self.blockers
        ):
            raise ValueError("ready protection failure policy cannot have blockers")
        return self


def build_runtime_execution_protection_failure_policy(
    *,
    protection_plan: RuntimeExecutionProtectionPlan,
    block_new_entries_until_resolved: bool = True,
    mark_position_unprotected_until_verified: bool = True,
    require_owner_recovery_review: bool = True,
    require_reduce_only_recovery_mode: bool = True,
    require_reconciliation_before_retry: bool = True,
    consume_attempt_on_any_fill: bool = True,
    hold_or_reconcile_budget_until_position_resolved: bool = True,
    must_not_mark_unprotected_position_as_protected: bool = True,
    now_ms: int,
) -> RuntimeExecutionProtectionFailurePolicy:
    blockers = list(protection_plan.blockers)
    warnings = list(protection_plan.warnings)
    if protection_plan.status != RuntimeExecutionProtectionPlanStatus.READY_FOR_SUBMIT_ADAPTER:
        blockers.append("runtime_protection_plan_not_ready")
    if not protection_plan.requires_protection:
        blockers.append("runtime_protection_not_required_unexpectedly")
    if protection_plan.stop_price_reference is None:
        blockers.append("hard_stop_reference_missing")

    required = {
        "block_new_entries_until_resolved": block_new_entries_until_resolved,
        "mark_position_unprotected_until_verified": (
            mark_position_unprotected_until_verified
        ),
        "require_owner_recovery_review": require_owner_recovery_review,
        "require_reduce_only_recovery_mode": require_reduce_only_recovery_mode,
        "require_reconciliation_before_retry": require_reconciliation_before_retry,
        "consume_attempt_on_any_fill": consume_attempt_on_any_fill,
        "hold_or_reconcile_budget_until_position_resolved": (
            hold_or_reconcile_budget_until_position_resolved
        ),
        "must_not_mark_unprotected_position_as_protected": (
            must_not_mark_unprotected_position_as_protected
        ),
    }
    for key, enabled in required.items():
        if not enabled:
            blockers.append(f"{key}_missing")

    recovery_actions = [
        "record_unprotected_position_incident",
        "block_runtime_new_entries",
        "mark_position_unprotected_until_exchange_protection_verified",
        "require_owner_recovery_review_before_retry",
        "enter_reduce_only_recovery_mode_until_resolved",
        "reconcile_position_and_open_orders_before_retry",
    ]
    status = (
        RuntimeExecutionProtectionFailurePolicyStatus.BLOCKED
        if blockers
        else RuntimeExecutionProtectionFailurePolicyStatus
        .READY_FOR_FIRST_REAL_SUBMIT_CONFIRMATION
    )
    return RuntimeExecutionProtectionFailurePolicy(
        policy_id=(
            "runtime-protection-failure-policy-"
            f"{protection_plan.execution_intent_id}"
        ),
        protection_plan_id=protection_plan.protection_plan_id,
        execution_intent_id=protection_plan.execution_intent_id,
        runtime_instance_id=(
            protection_plan.semantic_ids.runtime_instance_id
            or "runtime-instance-unset"
        ),
        source_type=protection_plan.source_type,
        source_id=protection_plan.source_id,
        semantic_ids=protection_plan.semantic_ids,
        status=status,
        symbol=protection_plan.symbol,
        side=protection_plan.side,
        block_new_entries_until_resolved=block_new_entries_until_resolved,
        mark_position_unprotected_until_verified=(
            mark_position_unprotected_until_verified
        ),
        require_owner_recovery_review=require_owner_recovery_review,
        require_reduce_only_recovery_mode=require_reduce_only_recovery_mode,
        require_reconciliation_before_retry=require_reconciliation_before_retry,
        consume_attempt_on_any_fill=consume_attempt_on_any_fill,
        hold_or_reconcile_budget_until_position_resolved=(
            hold_or_reconcile_budget_until_position_resolved
        ),
        must_not_mark_unprotected_position_as_protected=(
            must_not_mark_unprotected_position_as_protected
        ),
        recovery_actions=recovery_actions,
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_protection_failure_policy",
            "first_real_submit_prerequisite": True,
            "entry_filled_without_verified_protection_is_incident": True,
            "does_not_create_recovery_order": True,
            "does_not_call_order_lifecycle": True,
            "does_not_call_exchange": True,
            "does_not_call_owner_bounded_execution": True,
            "does_not_change_execution_intent_status": True,
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
