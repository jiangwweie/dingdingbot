"""Runtime-native protection plan preview for controlled submit.

This module validates whether a recorded runtime ExecutionIntent carries enough
candidate protection data for a future submit adapter. It does not place
orders, create exchange payloads, or reuse the one-shot Owner authorization
protection planner.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.execution_intent import ExecutionIntent


class RuntimeExecutionProtectionPlanModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeExecutionProtectionPlanPreviewStatus(str, Enum):
    BLOCKED = "blocked"
    READY_FOR_SUBMIT_ADAPTER = "ready_for_submit_adapter"


class RuntimeExecutionProtectionPlanStatus(str, Enum):
    BLOCKED = "blocked"
    READY_FOR_SUBMIT_ADAPTER = "ready_for_submit_adapter"


class RuntimeExecutionProtectionPlanPreview(RuntimeExecutionProtectionPlanModel):
    protection_plan_preview_id: str = Field(min_length=1, max_length=260)
    execution_intent_id: str = Field(min_length=1, max_length=64)
    runtime_execution_intent_draft_id: Optional[str] = Field(default=None, max_length=180)
    source_type: Optional[str] = Field(default=None, max_length=64)
    source_id: Optional[str] = Field(default=None, max_length=128)
    semantic_ids: BrcSemanticIds
    status: RuntimeExecutionProtectionPlanPreviewStatus
    symbol: str = Field(min_length=1, max_length=128)
    side: Optional[str] = Field(default=None, max_length=32)
    proposed_quantity: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    intended_notional: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    entry_price_reference: Optional[Decimal] = None
    requires_protection: bool = True
    stop_reference: Optional[str] = Field(default=None, max_length=256)
    stop_price_reference: Optional[Decimal] = None
    take_profit_references: list[dict[str, Any]] = Field(default_factory=list)
    risk_preview: dict[str, Any] = Field(default_factory=dict)
    protection_preview: dict[str, Any] = Field(default_factory=dict)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    not_order: Literal[True] = True
    not_exchange_payload: Literal[True] = True
    order_created: Literal[False] = False
    exchange_called: Literal[False] = False
    owner_bounded_execution_called: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    preview_only: Literal[True] = True
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "RuntimeExecutionProtectionPlanPreview":
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
                raise ValueError(f"runtime protection preview contains forbidden execution field: {key}")
        return self


class RuntimeExecutionProtectionPlan(RuntimeExecutionProtectionPlanModel):
    protection_plan_id: str = Field(min_length=1, max_length=260)
    protection_plan_preview_id: str = Field(min_length=1, max_length=260)
    execution_intent_id: str = Field(min_length=1, max_length=64)
    runtime_execution_intent_draft_id: Optional[str] = Field(default=None, max_length=180)
    source_type: Optional[str] = Field(default=None, max_length=64)
    source_id: Optional[str] = Field(default=None, max_length=128)
    semantic_ids: BrcSemanticIds
    status: RuntimeExecutionProtectionPlanStatus
    symbol: str = Field(min_length=1, max_length=128)
    side: Optional[str] = Field(default=None, max_length=32)
    proposed_quantity: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    intended_notional: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    entry_price_reference: Optional[Decimal] = None
    requires_protection: bool = True
    stop_reference: Optional[str] = Field(default=None, max_length=256)
    stop_price_reference: Optional[Decimal] = None
    take_profit_references: list[dict[str, Any]] = Field(default_factory=list)
    risk_preview: dict[str, Any] = Field(default_factory=dict)
    protection_preview: dict[str, Any] = Field(default_factory=dict)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    protection_plan_recorded: Literal[True] = True
    not_order: Literal[True] = True
    not_exchange_payload: Literal[True] = True
    execution_intent_status_changed: Literal[False] = False
    order_created: Literal[False] = False
    exchange_called: Literal[False] = False
    owner_bounded_execution_called: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "RuntimeExecutionProtectionPlan":
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
                raise ValueError(f"runtime protection plan contains forbidden execution field: {key}")
        if self.status == RuntimeExecutionProtectionPlanStatus.READY_FOR_SUBMIT_ADAPTER and self.blockers:
            raise ValueError("ready runtime protection plan cannot have blockers")
        return self


def build_runtime_execution_protection_plan(
    *,
    preview: RuntimeExecutionProtectionPlanPreview,
    now_ms: int,
) -> RuntimeExecutionProtectionPlan:
    return RuntimeExecutionProtectionPlan(
        protection_plan_id=f"runtime-protection-plan-{preview.execution_intent_id}",
        protection_plan_preview_id=preview.protection_plan_preview_id,
        execution_intent_id=preview.execution_intent_id,
        runtime_execution_intent_draft_id=preview.runtime_execution_intent_draft_id,
        source_type=preview.source_type,
        source_id=preview.source_id,
        semantic_ids=preview.semantic_ids,
        status=RuntimeExecutionProtectionPlanStatus(preview.status.value),
        symbol=preview.symbol,
        side=preview.side,
        proposed_quantity=preview.proposed_quantity,
        intended_notional=preview.intended_notional,
        entry_price_reference=preview.entry_price_reference,
        requires_protection=preview.requires_protection,
        stop_reference=preview.stop_reference,
        stop_price_reference=preview.stop_price_reference,
        take_profit_references=list(preview.take_profit_references),
        risk_preview=dict(preview.risk_preview),
        protection_preview=dict(preview.protection_preview),
        blockers=list(preview.blockers),
        warnings=list(preview.warnings),
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_protection_plan",
            "derived_from_preview_id": preview.protection_plan_preview_id,
            "runtime_native": True,
            "does_not_create_exchange_payload": True,
            "does_not_change_execution_intent_status": True,
            "does_not_call_owner_bounded_execution": True,
            "does_not_call_order_lifecycle": True,
            "does_not_call_exchange": True,
        },
    )


def build_runtime_execution_protection_plan_preview(
    *,
    intent: ExecutionIntent,
    now_ms: int,
) -> RuntimeExecutionProtectionPlanPreview:
    payload = intent.source_payload or {}
    risk_preview = _optional_dict(payload.get("risk_preview"))
    protection_preview = _optional_dict(payload.get("protection_preview"))
    blockers: list[str] = []
    warnings: list[str] = []
    if not risk_preview:
        blockers.append("risk_preview_missing")
    if not protection_preview:
        blockers.append("protection_preview_missing")

    side = _optional_str(payload.get("side"))
    proposed_quantity = _optional_decimal(payload.get("proposed_quantity"))
    intended_notional = _optional_decimal(payload.get("intended_notional"))
    entry_price_reference = _optional_decimal(payload.get("entry_price_reference"))
    requires_protection = bool(protection_preview.get("requires_protection", True))
    stop_price_reference = _optional_decimal(protection_preview.get("stop_price_reference"))
    take_profit_references = list(protection_preview.get("take_profit_references") or [])

    if not side:
        blockers.append("side_missing_from_intent_source_payload")
    if proposed_quantity is None and intended_notional is None:
        blockers.append("quantity_or_notional_missing")
    if requires_protection and stop_price_reference is None:
        blockers.append("concrete_stop_price_missing")
    if requires_protection and not take_profit_references:
        warnings.append("take_profit_or_exit_policy_snapshot_missing")

    status = (
        RuntimeExecutionProtectionPlanPreviewStatus.BLOCKED
        if blockers
        else RuntimeExecutionProtectionPlanPreviewStatus.READY_FOR_SUBMIT_ADAPTER
    )
    return RuntimeExecutionProtectionPlanPreview(
        protection_plan_preview_id=f"runtime-protection-preview-{intent.id}",
        execution_intent_id=intent.id,
        runtime_execution_intent_draft_id=intent.runtime_execution_intent_draft_id,
        source_type=intent.source_type,
        source_id=intent.source_id,
        semantic_ids=intent.semantic_ids,
        status=status,
        symbol=intent.symbol or "unknown",
        side=side,
        proposed_quantity=proposed_quantity,
        intended_notional=intended_notional,
        entry_price_reference=entry_price_reference,
        requires_protection=requires_protection,
        stop_reference=_optional_str(protection_preview.get("stop_reference")),
        stop_price_reference=stop_price_reference,
        take_profit_references=take_profit_references,
        risk_preview=risk_preview,
        protection_preview=protection_preview,
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_protection_plan_preview",
            "runtime_native": True,
            "does_not_use_owner_bounded_authorization": True,
            "does_not_create_exchange_payload": True,
            "does_not_call_owner_bounded_execution": True,
            "does_not_call_order_lifecycle": True,
            "does_not_call_exchange": True,
        },
    )


def _optional_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _optional_decimal(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    return Decimal(str(value))


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
