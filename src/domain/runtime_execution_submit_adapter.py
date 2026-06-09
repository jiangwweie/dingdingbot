"""Non-executing controlled-submit adapter readiness preview.

This module describes the facts a future runtime submit adapter would need
before it can hand a recorded runtime ExecutionIntent to order lifecycle code.
It intentionally does not create orders, mutate intents, or call an exchange.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.execution_intent import ExecutionIntent, ExecutionIntentStatus
from src.domain.runtime_execution_controlled_submit import (
    RuntimeExecutionControlledSubmitPreflight,
    RuntimeExecutionControlledSubmitPreflightStatus,
)
from src.domain.runtime_execution_intent_adapter import RuntimeExecutionIntentSourceType
from src.domain.runtime_execution_protection_plan import (
    RuntimeExecutionProtectionPlanPreview,
    RuntimeExecutionProtectionPlanPreviewStatus,
    build_runtime_execution_protection_plan_preview,
)
from src.domain.runtime_execution_attempt_reservation import (
    RuntimeExecutionAttemptReservationPreview,
    RuntimeExecutionAttemptReservationPreviewStatus,
)


class RuntimeExecutionSubmitAdapterModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeExecutionSubmitAdapterPreviewStatus(str, Enum):
    BLOCKED = "blocked"
    INPUTS_READY_ADAPTER_NOT_IMPLEMENTED = "inputs_ready_adapter_not_implemented"


class RuntimeExecutionSubmitAdapterPreview(RuntimeExecutionSubmitAdapterModel):
    adapter_preview_id: str = Field(min_length=1, max_length=260)
    preflight_id: str = Field(min_length=1, max_length=260)
    authorization_id: str = Field(min_length=1, max_length=220)
    execution_intent_id: str = Field(min_length=1, max_length=64)
    source_type: Optional[str] = Field(default=None, max_length=64)
    source_id: Optional[str] = Field(default=None, max_length=128)
    status: RuntimeExecutionSubmitAdapterPreviewStatus
    semantic_ids: BrcSemanticIds
    symbol: str = Field(min_length=1, max_length=128)
    side: Optional[str] = Field(default=None, max_length=32)
    candidate_order_type: Optional[str] = Field(default=None, max_length=64)
    proposed_quantity: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    intended_notional: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    entry_price_reference: Optional[Decimal] = None
    risk_preview: dict[str, Any] = Field(default_factory=dict)
    protection_preview: dict[str, Any] = Field(default_factory=dict)
    protection_plan_preview: RuntimeExecutionProtectionPlanPreview
    attempt_reservation_preview: RuntimeExecutionAttemptReservationPreview
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    requires_runtime_budget_mutation: Literal[True] = True
    requires_order_lifecycle_adapter: Literal[True] = True
    requires_concrete_protection_plan: Literal[True] = True
    submit_adapter_implemented: Literal[False] = False
    runtime_budget_mutated: Literal[False] = False
    attempt_consumed: Literal[False] = False
    execution_intent_status_changed: Literal[False] = False
    order_created: Literal[False] = False
    exchange_called: Literal[False] = False
    owner_bounded_execution_called: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    preview_only: Literal[True] = True
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "RuntimeExecutionSubmitAdapterPreview":
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
                raise ValueError(f"submit adapter preview contains forbidden execution field: {key}")
        return self


def build_runtime_execution_submit_adapter_preview(
    *,
    preflight: RuntimeExecutionControlledSubmitPreflight,
    intent: ExecutionIntent,
    attempt_reservation_preview: RuntimeExecutionAttemptReservationPreview,
    now_ms: int,
) -> RuntimeExecutionSubmitAdapterPreview:
    blockers = list(preflight.blockers)
    warnings = list(preflight.warnings)
    if preflight.status != RuntimeExecutionControlledSubmitPreflightStatus.READY_FOR_CONTROLLED_SUBMIT_ADAPTER:
        blockers.append("controlled_submit_preflight_not_ready")
    if preflight.execution_intent_id != intent.id:
        blockers.append("preflight_intent_mismatch")
    if intent.status != ExecutionIntentStatus.RECORDED:
        blockers.append("execution_intent_not_recorded")
    if intent.source_type != RuntimeExecutionIntentSourceType.BRC_RUNTIME_ORDER_CANDIDATE.value:
        blockers.append("execution_intent_source_not_runtime_order_candidate")
    if intent.signal is not None or intent.signal_id is not None:
        blockers.append("legacy_signal_projection_present")
    if intent.order_id is not None or intent.exchange_order_id is not None:
        blockers.append("execution_artifact_already_present")

    payload = intent.source_payload or {}
    protection_plan_preview = build_runtime_execution_protection_plan_preview(
        intent=intent,
        now_ms=now_ms,
    )
    blockers.extend(protection_plan_preview.blockers)
    warnings.extend(protection_plan_preview.warnings)
    if protection_plan_preview.status != RuntimeExecutionProtectionPlanPreviewStatus.READY_FOR_SUBMIT_ADAPTER:
        blockers.append("runtime_protection_plan_preview_not_ready")
    blockers.extend(attempt_reservation_preview.blockers)
    warnings.extend(attempt_reservation_preview.warnings)
    if (
        attempt_reservation_preview.status
        != RuntimeExecutionAttemptReservationPreviewStatus.READY_TO_RESERVE_ATTEMPT
    ):
        blockers.append("runtime_attempt_reservation_preview_not_ready")
    if attempt_reservation_preview.execution_intent_id != intent.id:
        blockers.append("attempt_reservation_intent_mismatch")
    if attempt_reservation_preview.preflight_id != preflight.preflight_id:
        blockers.append("attempt_reservation_preflight_mismatch")
    if not payload.get("side"):
        blockers.append("side_missing_from_intent_source_payload")
    if not payload.get("candidate_order_type"):
        blockers.append("candidate_order_type_missing_from_intent_source_payload")
    if payload.get("proposed_quantity") in {None, ""} and payload.get("intended_notional") in {None, ""}:
        blockers.append("quantity_or_notional_missing")

    status = (
        RuntimeExecutionSubmitAdapterPreviewStatus.BLOCKED
        if blockers
        else RuntimeExecutionSubmitAdapterPreviewStatus.INPUTS_READY_ADAPTER_NOT_IMPLEMENTED
    )
    return RuntimeExecutionSubmitAdapterPreview(
        adapter_preview_id=f"runtime-submit-adapter-preview-{preflight.authorization_id}",
        preflight_id=preflight.preflight_id,
        authorization_id=preflight.authorization_id,
        execution_intent_id=preflight.execution_intent_id,
        source_type=intent.source_type,
        source_id=intent.source_id,
        status=status,
        semantic_ids=intent.semantic_ids,
        symbol=intent.symbol or preflight.final_gate_preview.symbol,
        side=_optional_str(payload.get("side")),
        candidate_order_type=_optional_str(payload.get("candidate_order_type")),
        proposed_quantity=protection_plan_preview.proposed_quantity,
        intended_notional=protection_plan_preview.intended_notional,
        entry_price_reference=protection_plan_preview.entry_price_reference,
        risk_preview=protection_plan_preview.risk_preview,
        protection_preview=protection_plan_preview.protection_preview,
        protection_plan_preview=protection_plan_preview,
        attempt_reservation_preview=attempt_reservation_preview,
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_submit_adapter_preview",
            "non_executing_adapter_design_boundary": True,
            "does_not_mutate_runtime_budget": True,
            "does_not_change_execution_intent_status": True,
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
