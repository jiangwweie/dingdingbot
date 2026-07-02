"""Non-executing OrderLifecycle adapter preview for runtime execution.

This checks whether a recorded runtime OrderLifecycle handoff draft has enough
Order-shaped facts for a future local CREATED-order registration step. It does
not construct Order objects, call OrderLifecycle, or call an exchange.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.models import OrderRole, OrderStatus
from src.domain.runtime_execution_order_lifecycle_handoff import (
    RuntimeExecutionOrderLifecycleHandoffDraft,
    RuntimeExecutionOrderLifecycleHandoffStatus,
)


class RuntimeExecutionOrderLifecycleAdapterModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeExecutionOrderLifecycleAdapterPreviewStatus(str, Enum):
    BLOCKED = "blocked"
    INPUTS_READY_REGISTRATION_NOT_ENABLED = "inputs_ready_registration_not_enabled"


class RuntimeExecutionOrderLifecycleAdapterPreview(
    RuntimeExecutionOrderLifecycleAdapterModel
):
    adapter_preview_id: str = Field(min_length=1, max_length=360)
    handoff_draft_id: str = Field(min_length=1, max_length=360)
    preflight_id: str = Field(min_length=1, max_length=260)
    authorization_id: str = Field(min_length=1, max_length=220)
    execution_intent_id: str = Field(min_length=1, max_length=64)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    source_type: Optional[str] = Field(default=None, max_length=64)
    source_id: Optional[str] = Field(default=None, max_length=128)
    semantic_ids: BrcSemanticIds
    status: RuntimeExecutionOrderLifecycleAdapterPreviewStatus
    symbol: str = Field(min_length=1, max_length=128)
    side: str = Field(min_length=1, max_length=32)
    entry_order_draft: dict[str, Any] = Field(default_factory=dict)
    protection_order_drafts: list[dict[str, Any]] = Field(default_factory=list)
    order_model_drafts: list[dict[str, Any]] = Field(default_factory=list)
    order_model_draft_count: int = Field(ge=0)
    entry_order_model_draft_count: int = Field(ge=0)
    protection_order_model_draft_count: int = Field(ge=0)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    requires_order_lifecycle_adapter: Literal[True] = True
    requires_local_order_registration: Literal[True] = True
    local_order_registration_enabled: Literal[False] = False
    order_lifecycle_adapter_implemented: Literal[False] = False
    local_order_registration_executed: Literal[False] = False
    execution_intent_status_changed: Literal[False] = False
    order_created: Literal[False] = False
    exchange_called: Literal[False] = False
    owner_bounded_execution_called: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    preview_only: Literal[True] = True
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "RuntimeExecutionOrderLifecycleAdapterPreview":
        forbidden = {
            "client_order_id",
            "exchange_order_id",
            "exchange_payload",
            "order_id",
            "place_order",
            "submit_order",
        }
        scanned = {
            "metadata": self.metadata,
            "entry_order_draft": self.entry_order_draft,
            "protection_order_drafts": self.protection_order_drafts,
            "order_model_drafts": self.order_model_drafts,
        }
        for key in _walk_keys(scanned):
            if key.lower() in forbidden:
                raise ValueError(
                    f"order lifecycle adapter preview contains forbidden execution field: {key}"
                )
        if (
            self.status
            == RuntimeExecutionOrderLifecycleAdapterPreviewStatus.INPUTS_READY_REGISTRATION_NOT_ENABLED
            and self.blockers
        ):
            raise ValueError("ready order lifecycle adapter preview cannot have blockers")
        return self


def build_runtime_execution_order_lifecycle_adapter_preview(
    *,
    handoff: RuntimeExecutionOrderLifecycleHandoffDraft,
    now_ms: int,
) -> RuntimeExecutionOrderLifecycleAdapterPreview:
    blockers = list(handoff.blockers)
    warnings = list(handoff.warnings)

    if handoff.status != RuntimeExecutionOrderLifecycleHandoffStatus.READY_FOR_ORDER_LIFECYCLE_ADAPTER:
        blockers.append("order_lifecycle_handoff_not_ready")
    if not handoff.requires_order_lifecycle_adapter:
        blockers.append("order_lifecycle_adapter_not_required_unexpectedly")
    if handoff.order_lifecycle_adapter_implemented:
        blockers.append("order_lifecycle_adapter_already_implemented_unexpectedly")
    if handoff.execution_intent_status_changed:
        blockers.append("execution_intent_status_already_changed")
    if handoff.order_created:
        blockers.append("order_already_created")
    if handoff.exchange_called:
        blockers.append("exchange_already_called")
    if handoff.owner_bounded_execution_called:
        blockers.append("owner_bounded_execution_already_called")
    if handoff.order_lifecycle_called:
        blockers.append("order_lifecycle_already_called")

    order_model_drafts = list(handoff.order_model_drafts)
    if not order_model_drafts:
        blockers.append("order_model_drafts_missing")
    entry_drafts = [
        draft
        for draft in order_model_drafts
        if str(draft.get("order_role") or "").upper() == OrderRole.ENTRY.value
    ]
    protection_drafts = [
        draft
        for draft in order_model_drafts
        if str(draft.get("order_role") or "").upper() != OrderRole.ENTRY.value
    ]
    if len(entry_drafts) != 1:
        blockers.append("entry_order_model_draft_count_invalid")

    entry_draft_id = (
        str(entry_drafts[0].get("local_order_draft_id") or "")
        if entry_drafts
        else ""
    )
    for index, draft in enumerate(order_model_drafts):
        blockers.extend(_validate_order_model_draft(draft=draft, index=index))
    for draft in entry_drafts:
        if draft.get("reduce_only") is not False:
            blockers.append("entry_order_model_draft_reduce_only_invalid")
        if draft.get("parent_local_order_draft_id") is not None:
            blockers.append("entry_order_model_draft_parent_invalid")
    for draft in protection_drafts:
        if draft.get("reduce_only") is not True:
            blockers.append("protection_order_model_draft_reduce_only_missing")
        if draft.get("parent_local_order_draft_id") != entry_draft_id:
            blockers.append("protection_order_model_draft_parent_missing")

    status = (
        RuntimeExecutionOrderLifecycleAdapterPreviewStatus.BLOCKED
        if blockers
        else RuntimeExecutionOrderLifecycleAdapterPreviewStatus.INPUTS_READY_REGISTRATION_NOT_ENABLED
    )
    return RuntimeExecutionOrderLifecycleAdapterPreview(
        adapter_preview_id=f"runtime-order-lifecycle-adapter-preview-{handoff.authorization_id}",
        handoff_draft_id=handoff.handoff_draft_id,
        preflight_id=handoff.preflight_id,
        authorization_id=handoff.authorization_id,
        execution_intent_id=handoff.execution_intent_id,
        runtime_instance_id=handoff.runtime_instance_id,
        source_type=handoff.source_type,
        source_id=handoff.source_id,
        semantic_ids=handoff.semantic_ids,
        status=status,
        symbol=handoff.symbol,
        side=handoff.side,
        entry_order_draft=dict(handoff.entry_order_draft),
        protection_order_drafts=list(handoff.protection_order_drafts),
        order_model_drafts=order_model_drafts,
        order_model_draft_count=len(order_model_drafts),
        entry_order_model_draft_count=len(entry_drafts),
        protection_order_model_draft_count=len(protection_drafts),
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_order_lifecycle_adapter_preview",
            "non_executing_order_lifecycle_adapter_gate": True,
            "local_order_registration_enabled": False,
            "does_not_construct_order_objects": True,
            "does_not_register_created_orders": True,
            "does_not_change_execution_intent_status": True,
            "does_not_call_owner_bounded_execution": True,
            "does_not_call_order_lifecycle": True,
            "does_not_call_exchange": True,
        },
    )


def _validate_order_model_draft(*, draft: dict[str, Any], index: int) -> list[str]:
    blockers: list[str] = []
    required = [
        "local_order_draft_id",
        "signal_id",
        "symbol",
        "direction",
        "order_type",
        "order_role",
        "requested_qty",
        "status",
        "created_at",
        "updated_at",
    ]
    for key in required:
        if draft.get(key) in {None, ""}:
            blockers.append(f"order_model_draft_{index}_{key}_missing")
    if draft.get("status") != OrderStatus.CREATED.value:
        blockers.append("order_model_draft_status_not_created")
    if draft.get("persisted") is not False:
        blockers.append("order_model_draft_already_persisted")
    if draft.get("order_lifecycle_called") is not False:
        blockers.append("order_model_draft_order_lifecycle_called")
    if draft.get("exchange_called") is not False:
        blockers.append("order_model_draft_exchange_called")
    return blockers


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
