"""ExecutionIntent local-order linkage.

This is the explicit boundary after local CREATED-order registration and before
any exchange submit design. It links a source-native runtime ExecutionIntent to
registered local order IDs without marking it submitted or completed.
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


class RuntimeExecutionIntentLocalOrderLinkageModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeExecutionIntentLocalOrderLinkageStatus(str, Enum):
    BLOCKED = "blocked"
    LOCAL_ORDER_LINKAGE_DISABLED = "local_order_linkage_disabled"
    LINKED_LOCAL_ORDERS = "linked_local_orders"


class RuntimeExecutionIntentLocalOrderLinkage(
    RuntimeExecutionIntentLocalOrderLinkageModel
):
    linkage_id: str = Field(min_length=1, max_length=460)
    adapter_result_id: str = Field(min_length=1, max_length=420)
    authorization_id: str = Field(min_length=1, max_length=220)
    execution_intent_id: str = Field(min_length=1, max_length=64)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    source_type: Optional[str] = Field(default=None, max_length=64)
    source_id: Optional[str] = Field(default=None, max_length=128)
    semantic_ids: BrcSemanticIds
    status: RuntimeExecutionIntentLocalOrderLinkageStatus
    previous_intent_status: ExecutionIntentStatus
    linked_intent_status: ExecutionIntentStatus | None = None
    entry_order_id: Optional[str] = Field(default=None, max_length=260)
    local_order_ids: list[str] = Field(default_factory=list)
    protection_order_ids: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    execution_intent_local_order_linkage_enabled: bool = False
    execution_intent_status_changed: bool = False
    order_id_linked: bool = False
    exchange_order_submitted: Literal[False] = False
    exchange_called: Literal[False] = False
    owner_bounded_execution_called: Literal[False] = False
    withdrawal_or_transfer_created: Literal[False] = False
    not_exchange_submit_authority: Literal[True] = True
    linked_execution_intent_snapshot: ExecutionIntent | None = None
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_linkage(self) -> "RuntimeExecutionIntentLocalOrderLinkage":
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
                    f"intent local-order linkage contains forbidden execution field: {key}"
                )
        if self.exchange_called or self.exchange_order_submitted:
            raise ValueError("intent local-order linkage cannot call exchange")
        if self.owner_bounded_execution_called:
            raise ValueError("intent local-order linkage cannot call OwnerBoundedExecution")
        if self.withdrawal_or_transfer_created:
            raise ValueError("intent local-order linkage cannot create withdrawal/transfer")
        if (
            self.status
            == RuntimeExecutionIntentLocalOrderLinkageStatus.LINKED_LOCAL_ORDERS
        ):
            if self.blockers:
                raise ValueError("linked local-order linkage cannot have blockers")
            if not self.execution_intent_local_order_linkage_enabled:
                raise ValueError("linked local-order linkage requires enablement")
            if not self.execution_intent_status_changed:
                raise ValueError("linked local-order linkage must change intent status")
            if not self.order_id_linked:
                raise ValueError("linked local-order linkage must link order_id")
            if self.linked_intent_status != ExecutionIntentStatus.LOCAL_ORDERS_REGISTERED:
                raise ValueError("linked intent status must be local_orders_registered")
            if self.linked_execution_intent_snapshot is None:
                raise ValueError("linked local-order linkage requires intent snapshot")
            if self.linked_execution_intent_snapshot.exchange_order_id is not None:
                raise ValueError("linked intent cannot have exchange_order_id")
        elif self.execution_intent_status_changed or self.order_id_linked:
            raise ValueError("blocked/disabled linkage cannot change intent")
        return self


def build_runtime_execution_intent_local_order_linkage(
    *,
    intent: ExecutionIntent,
    adapter_result: RuntimeExecutionOrderLifecycleAdapterResult,
    execution_intent_local_order_linkage_enabled: bool = False,
    now_ms: int,
) -> RuntimeExecutionIntentLocalOrderLinkage:
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
        blockers.append("execution_intent_not_recorded_for_local_order_linkage")
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
    if adapter_result.registered_order_count != len(adapter_result.local_order_ids):
        blockers.append("registered_order_count_mismatch")
    if not execution_intent_local_order_linkage_enabled:
        blockers.append("execution_intent_local_order_linkage_disabled")

    linked_intent: ExecutionIntent | None = None
    entry_order_id = adapter_result.entry_order_ids[0] if adapter_result.entry_order_ids else None
    if not blockers and entry_order_id is not None:
        source_payload = dict(intent.source_payload or {})
        source_payload["local_orders_registered"] = True
        source_payload["local_order_ids"] = list(adapter_result.local_order_ids)
        source_payload["entry_order_id"] = entry_order_id
        source_payload["protection_order_ids"] = list(adapter_result.protection_order_ids)
        source_payload["adapter_result_id"] = adapter_result.adapter_result_id
        source_payload["local_order_linkage_id"] = (
            f"runtime-intent-local-order-linkage-{adapter_result.authorization_id}"
        )
        source_payload["exchange_order_submitted"] = False
        source_payload["exchange_called"] = False
        linked_intent = ExecutionIntent.model_validate(
            {
                **intent.model_dump(mode="python"),
                "status": ExecutionIntentStatus.LOCAL_ORDERS_REGISTERED,
                "order_id": entry_order_id,
                "exchange_order_id": None,
                "source_payload": source_payload,
                "updated_at": now_ms,
            }
        )

    status = RuntimeExecutionIntentLocalOrderLinkageStatus.BLOCKED
    if not execution_intent_local_order_linkage_enabled:
        status = (
            RuntimeExecutionIntentLocalOrderLinkageStatus
            .LOCAL_ORDER_LINKAGE_DISABLED
        )
    elif linked_intent is not None and not blockers:
        status = RuntimeExecutionIntentLocalOrderLinkageStatus.LINKED_LOCAL_ORDERS

    return RuntimeExecutionIntentLocalOrderLinkage(
        linkage_id=f"runtime-intent-local-order-linkage-{adapter_result.authorization_id}",
        adapter_result_id=adapter_result.adapter_result_id,
        authorization_id=adapter_result.authorization_id,
        execution_intent_id=intent.id,
        runtime_instance_id=adapter_result.runtime_instance_id,
        source_type=intent.source_type,
        source_id=intent.source_id,
        semantic_ids=adapter_result.semantic_ids,
        status=status,
        previous_intent_status=ExecutionIntentStatus(intent.status),
        linked_intent_status=(
            ExecutionIntentStatus.LOCAL_ORDERS_REGISTERED
            if linked_intent is not None
            else None
        ),
        entry_order_id=entry_order_id,
        local_order_ids=list(adapter_result.local_order_ids),
        protection_order_ids=list(adapter_result.protection_order_ids),
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        execution_intent_local_order_linkage_enabled=(
            execution_intent_local_order_linkage_enabled
        ),
        execution_intent_status_changed=linked_intent is not None,
        order_id_linked=linked_intent is not None,
        linked_execution_intent_snapshot=linked_intent,
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_intent_local_order_linkage",
            "local_order_linkage_only": True,
            "adapter_result_id": adapter_result.adapter_result_id,
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
