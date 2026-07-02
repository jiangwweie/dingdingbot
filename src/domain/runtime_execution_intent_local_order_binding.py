"""Runtime ExecutionIntent to local-order binding preview.

This is the explicit read boundary after local CREATED-order registration and
before exchange submit design. It binds a source-native runtime ExecutionIntent
to already registered local order IDs without mutating the intent, creating
orders, or calling an exchange.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.execution_intent import ExecutionIntent, ExecutionIntentStatus
from src.domain.runtime_execution_intent_adapter import (
    RuntimeExecutionIntentSourceType,
)
from src.domain.runtime_execution_order_lifecycle_adapter_result import (
    RuntimeExecutionOrderLifecycleAdapterResult,
    RuntimeExecutionOrderLifecycleAdapterResultStatus,
)


class RuntimeExecutionIntentLocalOrderBindingModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeExecutionIntentLocalOrderBindingStatus(str, Enum):
    BLOCKED = "blocked"
    READY_FOR_EXCHANGE_SUBMIT_DESIGN = "ready_for_exchange_submit_design"


class RuntimeExecutionIntentLocalOrderBinding(
    RuntimeExecutionIntentLocalOrderBindingModel
):
    binding_id: str = Field(min_length=1, max_length=460)
    adapter_result_id: str = Field(min_length=1, max_length=420)
    authorization_id: str = Field(min_length=1, max_length=220)
    execution_intent_id: str = Field(min_length=1, max_length=64)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    source_type: Optional[str] = Field(default=None, max_length=64)
    source_id: Optional[str] = Field(default=None, max_length=128)
    semantic_ids: BrcSemanticIds
    status: RuntimeExecutionIntentLocalOrderBindingStatus
    previous_intent_status: ExecutionIntentStatus
    entry_order_id: Optional[str] = Field(default=None, max_length=260)
    local_order_ids: list[str] = Field(default_factory=list)
    protection_order_ids: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    local_orders_registered: bool = False
    binding_recorded: Literal[False] = False
    execution_intent_status_changed: Literal[False] = False
    order_id_linked_to_intent: Literal[False] = False
    exchange_order_submitted: Literal[False] = False
    exchange_called: Literal[False] = False
    owner_bounded_execution_called: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    withdrawal_or_transfer_created: Literal[False] = False
    not_exchange_submit_authority: Literal[True] = True
    preview_only: Literal[True] = True
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_binding(self) -> "RuntimeExecutionIntentLocalOrderBinding":
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
                    "intent local-order binding contains forbidden execution "
                    f"field: {key}"
                )
        if self.exchange_called or self.exchange_order_submitted:
            raise ValueError("intent local-order binding cannot call exchange")
        if self.owner_bounded_execution_called:
            raise ValueError("intent local-order binding cannot call OwnerBoundedExecution")
        if self.order_lifecycle_called:
            raise ValueError("intent local-order binding cannot call OrderLifecycle")
        if self.withdrawal_or_transfer_created:
            raise ValueError("intent local-order binding cannot create withdrawal/transfer")
        if (
            self.status
            == RuntimeExecutionIntentLocalOrderBindingStatus.READY_FOR_EXCHANGE_SUBMIT_DESIGN
            and self.blockers
        ):
            raise ValueError("ready intent local-order binding cannot have blockers")
        return self


def build_runtime_execution_intent_local_order_binding(
    *,
    intent: ExecutionIntent,
    adapter_result: RuntimeExecutionOrderLifecycleAdapterResult,
    now_ms: int,
) -> RuntimeExecutionIntentLocalOrderBinding:
    blockers: list[str] = []
    warnings = list(adapter_result.warnings)

    if adapter_result.execution_intent_id != intent.id:
        blockers.append("adapter_result_intent_mismatch")
    if (
        adapter_result.status
        != RuntimeExecutionOrderLifecycleAdapterResultStatus.REGISTERED_CREATED_LOCAL_ORDERS
    ):
        blockers.append("local_orders_not_registered")
        blockers.extend(adapter_result.blockers)
    if adapter_result.exchange_called or adapter_result.exchange_order_submitted:
        blockers.append("adapter_result_exchange_artifact_present")
    if adapter_result.execution_intent_status_changed:
        blockers.append("adapter_result_already_changed_intent_status")
    if adapter_result.owner_bounded_execution_called:
        blockers.append("adapter_result_owner_bounded_execution_called")
    if adapter_result.withdrawal_or_transfer_created:
        blockers.append("adapter_result_withdrawal_or_transfer_created")
    if intent.status != ExecutionIntentStatus.RECORDED:
        blockers.append("execution_intent_not_recorded_for_local_order_binding")
    if intent.source_type != RuntimeExecutionIntentSourceType.BRC_RUNTIME_ORDER_CANDIDATE.value:
        blockers.append("execution_intent_source_not_runtime_order_candidate")
    if intent.order_id is not None:
        blockers.append("execution_intent_order_id_already_present")
    if intent.exchange_order_id is not None:
        blockers.append("execution_intent_exchange_order_id_already_present")
    if len(adapter_result.entry_order_ids) != 1:
        blockers.append("entry_order_id_count_invalid")
    if not adapter_result.local_order_ids:
        blockers.append("local_order_ids_missing")
    if not adapter_result.protection_order_ids:
        blockers.append("protection_order_ids_missing")
    if adapter_result.registered_order_count != len(adapter_result.local_order_ids):
        blockers.append("registered_order_count_mismatch")

    entry_order_id = (
        adapter_result.entry_order_ids[0]
        if len(adapter_result.entry_order_ids) == 1
        else None
    )
    status = (
        RuntimeExecutionIntentLocalOrderBindingStatus.BLOCKED
        if blockers
        else RuntimeExecutionIntentLocalOrderBindingStatus.READY_FOR_EXCHANGE_SUBMIT_DESIGN
    )
    return RuntimeExecutionIntentLocalOrderBinding(
        binding_id=(
            "runtime-intent-local-order-binding-"
            f"{adapter_result.authorization_id}"
        ),
        adapter_result_id=adapter_result.adapter_result_id,
        authorization_id=adapter_result.authorization_id,
        execution_intent_id=intent.id,
        runtime_instance_id=adapter_result.runtime_instance_id,
        source_type=intent.source_type,
        source_id=intent.source_id,
        semantic_ids=adapter_result.semantic_ids,
        status=status,
        previous_intent_status=ExecutionIntentStatus(intent.status),
        entry_order_id=entry_order_id,
        local_order_ids=list(adapter_result.local_order_ids),
        protection_order_ids=list(adapter_result.protection_order_ids),
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        local_orders_registered=(
            adapter_result.status
            == RuntimeExecutionOrderLifecycleAdapterResultStatus.REGISTERED_CREATED_LOCAL_ORDERS
        ),
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_intent_local_order_binding",
            "local_order_binding_preview_only": True,
            "adapter_result_id": adapter_result.adapter_result_id,
            "symbol": adapter_result.symbol,
            "side": adapter_result.side,
            "does_not_mutate_execution_intent": True,
            "does_not_register_created_orders": True,
            "does_not_submit_exchange_order": True,
            "does_not_call_exchange": True,
            "does_not_call_owner_bounded_execution": True,
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
