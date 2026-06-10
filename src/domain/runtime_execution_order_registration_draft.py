"""Typed non-registration preview for runtime local order drafts.

This module validates that a runtime OrderLifecycle adapter preview contains
Order-compatible local registration facts. It intentionally does not construct
Order objects, save rows, call OrderLifecycle, or call an exchange.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.models import Direction, OrderRole, OrderStatus, OrderType
from src.domain.runtime_execution_order_lifecycle_adapter import (
    RuntimeExecutionOrderLifecycleAdapterPreview,
    RuntimeExecutionOrderLifecycleAdapterPreviewStatus,
)


class RuntimeExecutionOrderRegistrationDraftModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeExecutionOrderRegistrationDraftPreviewStatus(str, Enum):
    BLOCKED = "blocked"
    INPUTS_READY_REGISTRATION_DRAFT_ONLY = "inputs_ready_registration_draft_only"


class RuntimeExecutionLocalOrderRegistrationDraft(RuntimeExecutionOrderRegistrationDraftModel):
    """Order-shaped registration input that remains a draft, not an Order."""

    local_order_draft_id: str = Field(min_length=1, max_length=260)
    signal_id: str = Field(min_length=1, max_length=260)
    symbol: str = Field(min_length=1, max_length=128)
    direction: Direction
    order_type: OrderType
    order_role: OrderRole
    price: Optional[Decimal] = None
    trigger_price: Optional[Decimal] = None
    requested_qty: Decimal = Field(gt=Decimal("0"))
    status: OrderStatus = OrderStatus.CREATED
    created_at: int = Field(ge=0)
    updated_at: int = Field(ge=0)
    reduce_only: bool = False
    parent_local_order_draft_id: Optional[str] = Field(default=None, max_length=260)
    runtime_instance_id: Optional[str] = Field(default=None, max_length=128)
    trial_binding_id: Optional[str] = Field(default=None, max_length=128)
    strategy_family_id: Optional[str] = Field(default=None, max_length=128)
    strategy_family_version_id: Optional[str] = Field(default=None, max_length=128)
    signal_evaluation_id: Optional[str] = Field(default=None, max_length=128)
    order_candidate_id: Optional[str] = Field(default=None, max_length=128)
    persisted: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    exchange_called: Literal[False] = False
    not_order: Literal[True] = True
    not_persisted: Literal[True] = True

    @model_validator(mode="after")
    def _validate_created_draft(self) -> "RuntimeExecutionLocalOrderRegistrationDraft":
        if self.status != OrderStatus.CREATED:
            raise ValueError("local order registration draft must remain CREATED")
        if self.order_role == OrderRole.ENTRY:
            if self.reduce_only:
                raise ValueError("entry registration draft cannot be reduce_only")
            if self.parent_local_order_draft_id is not None:
                raise ValueError("entry registration draft cannot have parent draft")
        else:
            if not self.reduce_only:
                raise ValueError("protection registration draft must be reduce_only")
            if not self.parent_local_order_draft_id:
                raise ValueError("protection registration draft requires parent draft")
        if self.order_type in {OrderType.STOP_MARKET, OrderType.STOP_LIMIT}:
            if self.trigger_price is None:
                raise ValueError("stop registration draft requires trigger_price")
        if self.order_type in {OrderType.LIMIT, OrderType.STOP_LIMIT}:
            if self.price is None:
                raise ValueError("limit registration draft requires price")
        return self


class RuntimeExecutionOrderRegistrationDraftPreview(
    RuntimeExecutionOrderRegistrationDraftModel
):
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
    status: RuntimeExecutionOrderRegistrationDraftPreviewStatus
    symbol: str = Field(min_length=1, max_length=128)
    side: str = Field(min_length=1, max_length=32)
    local_order_registration_drafts: list[RuntimeExecutionLocalOrderRegistrationDraft] = (
        Field(default_factory=list)
    )
    registration_draft_count: int = Field(ge=0)
    entry_registration_draft_count: int = Field(ge=0)
    protection_registration_draft_count: int = Field(ge=0)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    requires_order_lifecycle_adapter: Literal[True] = True
    requires_local_order_registration: Literal[True] = True
    local_order_registration_enabled: Literal[False] = False
    order_lifecycle_adapter_implemented: Literal[False] = False
    order_objects_constructed: Literal[False] = False
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
    def _reject_execution_fields(self) -> "RuntimeExecutionOrderRegistrationDraftPreview":
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
            "local_order_registration_drafts": self.local_order_registration_drafts,
        }
        for key in _walk_keys(scanned):
            if key.lower() in forbidden:
                raise ValueError(
                    f"order registration draft preview contains forbidden execution field: {key}"
                )
        if (
            self.status
            == RuntimeExecutionOrderRegistrationDraftPreviewStatus.INPUTS_READY_REGISTRATION_DRAFT_ONLY
            and self.blockers
        ):
            raise ValueError("ready order registration draft preview cannot have blockers")
        return self


def build_runtime_execution_order_registration_draft_preview(
    *,
    adapter_preview: RuntimeExecutionOrderLifecycleAdapterPreview,
    now_ms: int,
) -> RuntimeExecutionOrderRegistrationDraftPreview:
    blockers = list(adapter_preview.blockers)
    warnings = list(adapter_preview.warnings)
    if (
        adapter_preview.status
        != RuntimeExecutionOrderLifecycleAdapterPreviewStatus.INPUTS_READY_REGISTRATION_NOT_ENABLED
    ):
        blockers.append("order_lifecycle_adapter_preview_not_ready")
    if adapter_preview.local_order_registration_enabled:
        blockers.append("local_order_registration_enabled_unexpectedly")
    if adapter_preview.order_lifecycle_adapter_implemented:
        blockers.append("order_lifecycle_adapter_implemented_unexpectedly")
    if adapter_preview.local_order_registration_executed:
        blockers.append("local_order_registration_already_executed")
    if adapter_preview.order_created:
        blockers.append("order_already_created")
    if adapter_preview.order_lifecycle_called:
        blockers.append("order_lifecycle_already_called")
    if adapter_preview.exchange_called:
        blockers.append("exchange_already_called")

    registration_drafts: list[RuntimeExecutionLocalOrderRegistrationDraft] = []
    for index, draft in enumerate(adapter_preview.order_model_drafts):
        try:
            registration_drafts.append(
                RuntimeExecutionLocalOrderRegistrationDraft(**draft)
            )
        except ValueError as exc:
            blockers.append(f"local_order_registration_draft_{index}_invalid:{exc}")

    entry_drafts = [
        draft for draft in registration_drafts if draft.order_role == OrderRole.ENTRY
    ]
    protection_drafts = [
        draft for draft in registration_drafts if draft.order_role != OrderRole.ENTRY
    ]
    if len(entry_drafts) != 1:
        blockers.append("entry_registration_draft_count_invalid")
    entry_draft_id = entry_drafts[0].local_order_draft_id if entry_drafts else None
    if entry_draft_id is not None:
        for draft in protection_drafts:
            if draft.parent_local_order_draft_id != entry_draft_id:
                blockers.append("protection_registration_draft_parent_mismatch")

    status = (
        RuntimeExecutionOrderRegistrationDraftPreviewStatus.BLOCKED
        if blockers
        else RuntimeExecutionOrderRegistrationDraftPreviewStatus.INPUTS_READY_REGISTRATION_DRAFT_ONLY
    )
    return RuntimeExecutionOrderRegistrationDraftPreview(
        registration_preview_id=(
            f"runtime-order-registration-draft-preview-{adapter_preview.authorization_id}"
        ),
        adapter_preview_id=adapter_preview.adapter_preview_id,
        handoff_draft_id=adapter_preview.handoff_draft_id,
        preflight_id=adapter_preview.preflight_id,
        authorization_id=adapter_preview.authorization_id,
        execution_intent_id=adapter_preview.execution_intent_id,
        runtime_instance_id=adapter_preview.runtime_instance_id,
        source_type=adapter_preview.source_type,
        source_id=adapter_preview.source_id,
        semantic_ids=adapter_preview.semantic_ids,
        status=status,
        symbol=adapter_preview.symbol,
        side=adapter_preview.side,
        local_order_registration_drafts=registration_drafts,
        registration_draft_count=len(registration_drafts),
        entry_registration_draft_count=len(entry_drafts),
        protection_registration_draft_count=len(protection_drafts),
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_order_registration_draft_preview",
            "typed_order_registration_draft_only": True,
            "does_not_construct_order_objects": True,
            "does_not_register_created_orders": True,
            "does_not_change_execution_intent_status": True,
            "does_not_call_owner_bounded_execution": True,
            "does_not_call_order_lifecycle": True,
            "does_not_call_exchange": True,
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
