"""Runtime OrderLifecycle adapter result.

This module is the first implementation-oriented adapter boundary after the
dry-run registration preview. It can turn typed registration drafts into local
Order objects and report whether they were registered through OrderLifecycle.

It must never submit exchange orders, build exchange payloads, or authorize
live runtime execution by itself.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.models import Order
from src.domain.runtime_execution_order_registration_draft import (
    RuntimeExecutionLocalOrderRegistrationDraft,
    RuntimeExecutionOrderRegistrationDraftPreview,
    RuntimeExecutionOrderRegistrationDraftPreviewStatus,
)


class RuntimeExecutionOrderLifecycleAdapterResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeExecutionOrderLifecycleAdapterResultStatus(str, Enum):
    BLOCKED = "blocked"
    ORDER_LIFECYCLE_ADAPTER_DISABLED = "order_lifecycle_adapter_disabled"
    LOCAL_ORDER_REGISTRATION_DISABLED = "local_order_registration_disabled"
    DUPLICATE_SUBMIT_LOCK_REQUIRED = "duplicate_submit_lock_required"
    LOCAL_REGISTRATION_LOCK_ACQUIRED = "local_registration_lock_acquired"
    LOCAL_ORDER_REGISTRATION_FAILED = "local_order_registration_failed"
    REGISTERED_CREATED_LOCAL_ORDERS = "registered_created_local_orders"


class RuntimeExecutionOrderLifecycleAdapterResult(
    RuntimeExecutionOrderLifecycleAdapterResultModel
):
    adapter_result_id: str = Field(min_length=1, max_length=420)
    registration_preview_id: str = Field(min_length=1, max_length=380)
    adapter_preview_id: str = Field(min_length=1, max_length=360)
    handoff_draft_id: str = Field(min_length=1, max_length=360)
    preflight_id: str = Field(min_length=1, max_length=260)
    authorization_id: str = Field(min_length=1, max_length=220)
    execution_intent_id: str = Field(min_length=1, max_length=64)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    source_type: Optional[str] = Field(default=None, max_length=64)
    source_id: Optional[str] = Field(default=None, max_length=128)
    semantic_ids: BrcSemanticIds
    status: RuntimeExecutionOrderLifecycleAdapterResultStatus
    symbol: str = Field(min_length=1, max_length=128)
    side: str = Field(min_length=1, max_length=32)
    local_order_ids: list[str] = Field(default_factory=list)
    entry_order_ids: list[str] = Field(default_factory=list)
    protection_order_ids: list[str] = Field(default_factory=list)
    registered_order_count: int = Field(ge=0)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    order_lifecycle_adapter_enabled: bool = False
    local_order_registration_enabled: bool = False
    duplicate_submit_lock_acquired: bool = False
    order_objects_constructed: bool = False
    local_order_registration_executed: bool = False
    execution_intent_status_changed: bool = False
    exchange_order_submitted: bool = False
    exchange_called: bool = False
    owner_bounded_execution_called: bool = False
    order_lifecycle_called: bool = False
    withdrawal_or_transfer_created: bool = False
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_result(self) -> "RuntimeExecutionOrderLifecycleAdapterResult":
        forbidden = {
            "client_order_id",
            "exchange_order_id",
            "exchange_payload",
            "place_order",
            "submit_order",
        }
        for key in _walk_keys({"metadata": self.metadata}):
            if key.lower() in forbidden:
                raise ValueError(
                    f"order lifecycle adapter result contains forbidden execution field: {key}"
                )
        if self.exchange_called or self.exchange_order_submitted:
            raise ValueError("runtime OrderLifecycle adapter result cannot call exchange")
        if self.owner_bounded_execution_called:
            raise ValueError("runtime adapter must not call OwnerBoundedExecution")
        if self.withdrawal_or_transfer_created:
            raise ValueError("runtime adapter must not create withdrawal or transfer")
        if self.execution_intent_status_changed:
            raise ValueError("status transition is a later explicit gate")
        success_status = (
            self.status
            == RuntimeExecutionOrderLifecycleAdapterResultStatus.REGISTERED_CREATED_LOCAL_ORDERS
        )
        failure_status = (
            self.status
            == RuntimeExecutionOrderLifecycleAdapterResultStatus.LOCAL_ORDER_REGISTRATION_FAILED
        )
        if success_status:
            if self.blockers:
                raise ValueError("registered adapter result cannot have blockers")
            if not self.order_objects_constructed:
                raise ValueError("registered adapter result must construct orders")
            if not self.local_order_registration_executed:
                raise ValueError("registered adapter result must register local orders")
            if not self.order_lifecycle_called:
                raise ValueError("registered adapter result must call OrderLifecycle")
            if self.registered_order_count != len(self.local_order_ids):
                raise ValueError("registered_order_count mismatch")
        elif failure_status:
            if not self.blockers:
                raise ValueError("failed adapter result must have blockers")
            if not self.order_objects_constructed:
                raise ValueError("failed adapter result must construct orders")
            if not self.local_order_registration_executed:
                raise ValueError("failed adapter result must attempt local registration")
            if not self.order_lifecycle_called:
                raise ValueError("failed adapter result must call OrderLifecycle")
            if self.registered_order_count != len(self.local_order_ids):
                raise ValueError("failed registered_order_count mismatch")
        else:
            if self.order_lifecycle_called or self.local_order_registration_executed:
                raise ValueError("non-registered adapter result cannot call lifecycle")
        if (
            self.status
            == RuntimeExecutionOrderLifecycleAdapterResultStatus.LOCAL_REGISTRATION_LOCK_ACQUIRED
        ):
            if not self.order_lifecycle_adapter_enabled:
                raise ValueError("lock result requires adapter enablement")
            if not self.local_order_registration_enabled:
                raise ValueError("lock result requires local registration enablement")
            if not self.duplicate_submit_lock_acquired:
                raise ValueError("lock result requires duplicate-submit lock")
        return self


def build_runtime_execution_order_lifecycle_adapter_result(
    *,
    registration_preview: RuntimeExecutionOrderRegistrationDraftPreview,
    now_ms: int,
    order_lifecycle_adapter_enabled: bool = False,
    local_order_registration_enabled: bool = False,
    duplicate_submit_lock_acquired: bool = False,
    registered_orders: list[Order] | None = None,
    local_registration_gate_id: str | None = None,
    local_registration_enablement_decision_id: str | None = None,
    additional_blockers: list[str] | None = None,
    additional_warnings: list[str] | None = None,
) -> RuntimeExecutionOrderLifecycleAdapterResult:
    blockers = list(registration_preview.blockers) + list(additional_blockers or [])
    warnings = list(registration_preview.warnings) + list(additional_warnings or [])
    registered_orders = list(registered_orders or [])

    if (
        registration_preview.status
        != RuntimeExecutionOrderRegistrationDraftPreviewStatus.INPUTS_READY_REGISTRATION_DRAFT_ONLY
    ):
        blockers.append("order_registration_draft_preview_not_ready")
    if not order_lifecycle_adapter_enabled:
        blockers.append("order_lifecycle_adapter_disabled")
    if order_lifecycle_adapter_enabled and not local_order_registration_enabled:
        blockers.append("local_order_registration_disabled")
    if (
        order_lifecycle_adapter_enabled
        and local_order_registration_enabled
        and not duplicate_submit_lock_acquired
    ):
        blockers.append("persistent_duplicate_submit_lock_required")

    expected_ids = {
        draft.local_order_draft_id
        for draft in registration_preview.local_order_registration_drafts
    }
    registered_ids = {order.id for order in registered_orders}
    if registered_orders and expected_ids != registered_ids:
        blockers.append("registered_order_ids_mismatch_registration_drafts")

    status = RuntimeExecutionOrderLifecycleAdapterResultStatus.BLOCKED
    if blockers:
        if "order_lifecycle_adapter_disabled" in blockers:
            status = (
                RuntimeExecutionOrderLifecycleAdapterResultStatus
                .ORDER_LIFECYCLE_ADAPTER_DISABLED
            )
        elif "local_order_registration_disabled" in blockers:
            status = (
                RuntimeExecutionOrderLifecycleAdapterResultStatus
                .LOCAL_ORDER_REGISTRATION_DISABLED
            )
        elif blockers == ["persistent_duplicate_submit_lock_required"]:
            status = (
                RuntimeExecutionOrderLifecycleAdapterResultStatus
                .DUPLICATE_SUBMIT_LOCK_REQUIRED
            )
    else:
        status = (
            RuntimeExecutionOrderLifecycleAdapterResultStatus
            .REGISTERED_CREATED_LOCAL_ORDERS
        )

    local_order_ids = [order.id for order in registered_orders]
    entry_ids = [order.id for order in registered_orders if order.order_role.value == "ENTRY"]
    protection_ids = [
        order.id for order in registered_orders if order.order_role.value != "ENTRY"
    ]
    return RuntimeExecutionOrderLifecycleAdapterResult(
        adapter_result_id=(
            "runtime-order-lifecycle-adapter-result-"
            f"{registration_preview.authorization_id}"
        ),
        registration_preview_id=registration_preview.registration_preview_id,
        adapter_preview_id=registration_preview.adapter_preview_id,
        handoff_draft_id=registration_preview.handoff_draft_id,
        preflight_id=registration_preview.preflight_id,
        authorization_id=registration_preview.authorization_id,
        execution_intent_id=registration_preview.execution_intent_id,
        runtime_instance_id=registration_preview.runtime_instance_id,
        source_type=registration_preview.source_type,
        source_id=registration_preview.source_id,
        semantic_ids=registration_preview.semantic_ids,
        status=status,
        symbol=registration_preview.symbol,
        side=registration_preview.side,
        local_order_ids=local_order_ids,
        entry_order_ids=entry_ids,
        protection_order_ids=protection_ids,
        registered_order_count=len(registered_orders),
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        order_lifecycle_adapter_enabled=order_lifecycle_adapter_enabled,
        local_order_registration_enabled=local_order_registration_enabled,
        duplicate_submit_lock_acquired=duplicate_submit_lock_acquired,
        order_objects_constructed=bool(registered_orders),
        local_order_registration_executed=bool(registered_orders),
        order_lifecycle_called=bool(registered_orders),
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_order_lifecycle_adapter_result",
            "local_created_order_registration_only": True,
            "local_registration_gate_id": local_registration_gate_id,
            "local_registration_enablement_decision_id": (
                local_registration_enablement_decision_id
            ),
            "requires_persistent_duplicate_submit_lock": True,
            "does_not_submit_exchange_order": True,
            "does_not_call_exchange": True,
            "does_not_call_owner_bounded_execution": True,
            "does_not_change_execution_intent_status": True,
            "does_not_create_withdrawal_or_transfer": True,
        },
    )


def build_runtime_execution_order_lifecycle_adapter_registration_failure_result(
    *,
    registration_preview: RuntimeExecutionOrderRegistrationDraftPreview,
    now_ms: int,
    attempted_orders: list[Order],
    registered_orders: list[Order],
    failed_order: Order | None,
    failure_reason: str,
    failure_message: str | None = None,
    local_registration_gate_id: str | None = None,
    local_registration_enablement_decision_id: str | None = None,
) -> RuntimeExecutionOrderLifecycleAdapterResult:
    blockers = list(registration_preview.blockers)
    blockers.append("local_order_registration_failed")
    warnings = list(registration_preview.warnings)

    failed_order_role = failed_order.order_role.value if failed_order else None
    if failed_order_role == "ENTRY":
        blockers.append("entry_order_registration_failed")
    elif failed_order is not None:
        blockers.append("protection_order_registration_failed")

    local_order_ids = [order.id for order in registered_orders]
    entry_ids = [order.id for order in registered_orders if order.order_role.value == "ENTRY"]
    protection_ids = [
        order.id for order in registered_orders if order.order_role.value != "ENTRY"
    ]
    attempted_order_ids = [order.id for order in attempted_orders]
    expected_protection_ids = [
        order.id for order in attempted_orders if order.order_role.value != "ENTRY"
    ]
    if entry_ids and not protection_ids and expected_protection_ids:
        warnings.append("entry_order_registered_without_registered_protection_order")

    return RuntimeExecutionOrderLifecycleAdapterResult(
        adapter_result_id=(
            "runtime-order-lifecycle-adapter-result-"
            f"{registration_preview.authorization_id}"
        ),
        registration_preview_id=registration_preview.registration_preview_id,
        adapter_preview_id=registration_preview.adapter_preview_id,
        handoff_draft_id=registration_preview.handoff_draft_id,
        preflight_id=registration_preview.preflight_id,
        authorization_id=registration_preview.authorization_id,
        execution_intent_id=registration_preview.execution_intent_id,
        runtime_instance_id=registration_preview.runtime_instance_id,
        source_type=registration_preview.source_type,
        source_id=registration_preview.source_id,
        semantic_ids=registration_preview.semantic_ids,
        status=(
            RuntimeExecutionOrderLifecycleAdapterResultStatus
            .LOCAL_ORDER_REGISTRATION_FAILED
        ),
        symbol=registration_preview.symbol,
        side=registration_preview.side,
        local_order_ids=local_order_ids,
        entry_order_ids=entry_ids,
        protection_order_ids=protection_ids,
        registered_order_count=len(registered_orders),
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        duplicate_submit_lock_acquired=True,
        order_objects_constructed=bool(attempted_orders),
        local_order_registration_executed=True,
        order_lifecycle_called=True,
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_order_lifecycle_adapter_result",
            "local_created_order_registration_only": True,
            "local_registration_gate_id": local_registration_gate_id,
            "local_registration_enablement_decision_id": (
                local_registration_enablement_decision_id
            ),
            "registration_failure_recorded": True,
            "failure_reason": failure_reason,
            "failure_message": failure_message,
            "failed_local_order_id": failed_order.id if failed_order else None,
            "failed_order_role": failed_order_role,
            "failed_order_type": (
                failed_order.order_type.value if failed_order else None
            ),
            "attempted_local_order_ids": attempted_order_ids,
            "registered_before_failure_local_order_ids": local_order_ids,
            "expected_protection_local_order_ids": expected_protection_ids,
            "recovery_status": "fail_closed_adapter_result_recorded",
            "requires_manual_review_before_retry": True,
            "does_not_submit_exchange_order": True,
            "does_not_call_exchange": True,
            "does_not_call_owner_bounded_execution": True,
            "does_not_change_execution_intent_status": True,
            "does_not_create_withdrawal_or_transfer": True,
        },
    )


def build_runtime_execution_order_lifecycle_adapter_lock_result(
    *,
    registration_preview: RuntimeExecutionOrderRegistrationDraftPreview,
    now_ms: int,
    local_registration_gate_id: str | None = None,
    local_registration_enablement_decision_id: str | None = None,
) -> RuntimeExecutionOrderLifecycleAdapterResult:
    if (
        registration_preview.status
        != RuntimeExecutionOrderRegistrationDraftPreviewStatus.INPUTS_READY_REGISTRATION_DRAFT_ONLY
    ):
        raise ValueError("order_registration_draft_preview_not_ready")
    if registration_preview.blockers:
        raise ValueError("order_registration_draft_preview_has_blockers")
    return RuntimeExecutionOrderLifecycleAdapterResult(
        adapter_result_id=(
            "runtime-order-lifecycle-adapter-result-"
            f"{registration_preview.authorization_id}"
        ),
        registration_preview_id=registration_preview.registration_preview_id,
        adapter_preview_id=registration_preview.adapter_preview_id,
        handoff_draft_id=registration_preview.handoff_draft_id,
        preflight_id=registration_preview.preflight_id,
        authorization_id=registration_preview.authorization_id,
        execution_intent_id=registration_preview.execution_intent_id,
        runtime_instance_id=registration_preview.runtime_instance_id,
        source_type=registration_preview.source_type,
        source_id=registration_preview.source_id,
        semantic_ids=registration_preview.semantic_ids,
        status=(
            RuntimeExecutionOrderLifecycleAdapterResultStatus
            .LOCAL_REGISTRATION_LOCK_ACQUIRED
        ),
        symbol=registration_preview.symbol,
        side=registration_preview.side,
        registered_order_count=0,
        blockers=[],
        warnings=list(registration_preview.warnings),
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        duplicate_submit_lock_acquired=True,
        order_objects_constructed=False,
        local_order_registration_executed=False,
        order_lifecycle_called=False,
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_order_lifecycle_adapter_result",
            "persistent_duplicate_submit_lock": True,
            "local_registration_gate_id": local_registration_gate_id,
            "local_registration_enablement_decision_id": (
                local_registration_enablement_decision_id
            ),
            "local_created_order_registration_pending": True,
            "does_not_submit_exchange_order": True,
            "does_not_call_exchange": True,
            "does_not_call_owner_bounded_execution": True,
            "does_not_change_execution_intent_status": True,
            "does_not_create_withdrawal_or_transfer": True,
        },
    )


def build_runtime_execution_orders_for_registration(
    *,
    registration_preview: RuntimeExecutionOrderRegistrationDraftPreview,
) -> list[Order]:
    if (
        registration_preview.status
        != RuntimeExecutionOrderRegistrationDraftPreviewStatus.INPUTS_READY_REGISTRATION_DRAFT_ONLY
    ):
        raise ValueError("order_registration_draft_preview_not_ready")
    return [
        _order_from_registration_draft(draft)
        for draft in registration_preview.local_order_registration_drafts
    ]


def _order_from_registration_draft(
    draft: RuntimeExecutionLocalOrderRegistrationDraft,
) -> Order:
    return Order(
        id=draft.local_order_draft_id,
        signal_id=draft.signal_id,
        symbol=draft.symbol,
        direction=draft.direction,
        order_type=draft.order_type,
        order_role=draft.order_role,
        price=draft.price,
        trigger_price=draft.trigger_price,
        requested_qty=draft.requested_qty,
        status=draft.status,
        created_at=draft.created_at,
        updated_at=draft.updated_at,
        reduce_only=draft.reduce_only,
        parent_order_id=draft.parent_local_order_draft_id,
        runtime_instance_id=draft.runtime_instance_id,
        trial_binding_id=draft.trial_binding_id,
        strategy_family_id=draft.strategy_family_id,
        strategy_family_version_id=draft.strategy_family_version_id,
        signal_evaluation_id=draft.signal_evaluation_id,
        order_candidate_id=draft.order_candidate_id,
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
