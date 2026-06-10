"""Controlled submit plan preview for authorized runtime intents.

This module describes the last non-submitting plan before a future controlled
submit adapter. It intentionally does not create orders or exchange payloads.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.execution_intent import ExecutionIntent, ExecutionIntentStatus
from src.domain.runtime_execution_intent_adapter import RuntimeExecutionIntentSourceType
from src.domain.runtime_final_gate_preview import (
    RuntimeFinalGatePreview,
    RuntimeFinalGatePreviewVerdict,
)
from src.domain.runtime_execution_submit_authorization import (
    RuntimeExecutionSubmitAuthorization,
    RuntimeExecutionSubmitAuthorizationStatus,
)


class RuntimeExecutionControlledSubmitModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeExecutionControlledSubmitPlanStatus(str, Enum):
    BLOCKED = "blocked"
    READY_FOR_CONTROLLED_SUBMIT_ADAPTER = "ready_for_controlled_submit_adapter"


class RuntimeExecutionControlledSubmitResultStatus(str, Enum):
    BLOCKED = "blocked"
    SUBMIT_ADAPTER_NOT_ENABLED = "submit_adapter_not_enabled"
    ORDER_LIFECYCLE_ADAPTER_DISABLED = "order_lifecycle_adapter_disabled"
    SUBMIT_ADAPTER_NOT_IMPLEMENTED = "submit_adapter_not_implemented"


class RuntimeExecutionControlledSubmitPreflightStatus(str, Enum):
    BLOCKED = "blocked"
    READY_FOR_CONTROLLED_SUBMIT_ADAPTER = "ready_for_controlled_submit_adapter"


class RuntimeExecutionControlledSubmitPlan(RuntimeExecutionControlledSubmitModel):
    plan_id: str = Field(min_length=1, max_length=240)
    authorization_id: str = Field(min_length=1, max_length=220)
    execution_intent_id: str = Field(min_length=1, max_length=64)
    runtime_execution_intent_draft_id: Optional[str] = Field(default=None, max_length=180)
    source_type: Optional[str] = Field(default=None, max_length=64)
    source_id: Optional[str] = Field(default=None, max_length=128)
    status: RuntimeExecutionControlledSubmitPlanStatus
    semantic_ids: BrcSemanticIds
    symbol: str = Field(min_length=1, max_length=128)
    side: Optional[str] = Field(default=None, max_length=32)
    candidate_order_type: Optional[str] = Field(default=None, max_length=64)
    proposed_quantity: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    intended_notional: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    requires_final_gate_execution_check: Literal[True] = True
    requires_owner_submit_authorization: Literal[True] = True
    owner_submit_authorized: Literal[True] = True
    submit_executed: Literal[False] = False
    order_created: Literal[False] = False
    exchange_called: Literal[False] = False
    owner_bounded_execution_called: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    preview_only: Literal[True] = True
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "RuntimeExecutionControlledSubmitPlan":
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
                raise ValueError(f"controlled submit plan contains forbidden execution field: {key}")
        return self


class RuntimeExecutionControlledSubmitResult(RuntimeExecutionControlledSubmitModel):
    result_id: str = Field(min_length=1, max_length=260)
    plan_id: str = Field(min_length=1, max_length=240)
    preflight_id: str = Field(min_length=1, max_length=260)
    authorization_id: str = Field(min_length=1, max_length=220)
    execution_intent_id: str = Field(min_length=1, max_length=64)
    preflight_status: RuntimeExecutionControlledSubmitPreflightStatus
    final_gate_verdict: RuntimeFinalGatePreviewVerdict
    status: RuntimeExecutionControlledSubmitResultStatus
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    submit_enabled: bool = False
    order_lifecycle_adapter_enabled: bool = False
    submit_executed: Literal[False] = False
    order_created: Literal[False] = False
    exchange_called: Literal[False] = False
    owner_bounded_execution_called: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "RuntimeExecutionControlledSubmitResult":
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
                raise ValueError(f"controlled submit result contains forbidden execution field: {key}")
        return self


class RuntimeExecutionControlledSubmitPreflight(RuntimeExecutionControlledSubmitModel):
    preflight_id: str = Field(min_length=1, max_length=260)
    plan_id: str = Field(min_length=1, max_length=240)
    authorization_id: str = Field(min_length=1, max_length=220)
    execution_intent_id: str = Field(min_length=1, max_length=64)
    order_candidate_id: Optional[str] = Field(default=None, max_length=128)
    status: RuntimeExecutionControlledSubmitPreflightStatus
    controlled_submit_plan_status: RuntimeExecutionControlledSubmitPlanStatus
    final_gate_verdict: RuntimeFinalGatePreviewVerdict
    final_gate_preview: RuntimeFinalGatePreview
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    requires_final_gate_execution_check: Literal[True] = True
    submit_executed: Literal[False] = False
    order_created: Literal[False] = False
    exchange_called: Literal[False] = False
    owner_bounded_execution_called: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    preview_only: Literal[True] = True
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "RuntimeExecutionControlledSubmitPreflight":
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
                raise ValueError(f"controlled submit preflight contains forbidden execution field: {key}")
        return self


def build_runtime_execution_controlled_submit_plan(
    *,
    authorization: RuntimeExecutionSubmitAuthorization,
    intent: ExecutionIntent,
    now_ms: int,
) -> RuntimeExecutionControlledSubmitPlan:
    blockers: list[str] = []
    warnings: list[str] = []
    if authorization.status != (
        RuntimeExecutionSubmitAuthorizationStatus.APPROVED_PENDING_CONTROLLED_SUBMIT
    ):
        blockers.append("submit_authorization_not_approved")
    if authorization.submit_executed:
        blockers.append("submit_authorization_already_executed")
    if authorization.order_created:
        blockers.append("submit_authorization_order_created")
    if authorization.exchange_called:
        blockers.append("submit_authorization_exchange_called")
    if authorization.execution_intent_id != intent.id:
        blockers.append("authorization_intent_mismatch")
    if intent.status != ExecutionIntentStatus.RECORDED:
        blockers.append("execution_intent_not_recorded")
    if intent.source_type != RuntimeExecutionIntentSourceType.BRC_RUNTIME_ORDER_CANDIDATE.value:
        blockers.append("execution_intent_source_not_runtime_order_candidate")
    if intent.signal is not None or intent.signal_id is not None:
        blockers.append("legacy_signal_projection_present")
    if intent.order_id is not None or intent.exchange_order_id is not None:
        blockers.append("execution_artifact_already_present")
    if authorization.runtime_execution_intent_draft_id != intent.runtime_execution_intent_draft_id:
        blockers.append("runtime_execution_intent_draft_mismatch")
    if authorization.source_id != intent.source_id:
        blockers.append("source_id_mismatch")
    if authorization.symbol != intent.symbol:
        blockers.append("symbol_mismatch")
    if authorization.semantic_ids != intent.semantic_ids:
        blockers.append("semantic_ids_mismatch")

    source_payload = intent.source_payload or {}
    if source_payload.get("submit_authorized") is True:
        blockers.append("unexpected_intent_submit_authorized_flag")
    if source_payload.get("order_created") is True:
        blockers.append("unexpected_intent_order_created_flag")
    if source_payload.get("exchange_called") is True:
        blockers.append("unexpected_intent_exchange_called_flag")
    if not source_payload.get("side"):
        warnings.append("side_missing_from_intent_source_payload")

    candidate_order_type = _optional_str(source_payload.get("candidate_order_type"))
    proposed_quantity = _optional_decimal(source_payload.get("proposed_quantity"))
    intended_notional = _optional_decimal(source_payload.get("intended_notional"))
    if proposed_quantity is None and intended_notional is None:
        blockers.append("quantity_or_notional_missing")

    status = (
        RuntimeExecutionControlledSubmitPlanStatus.BLOCKED
        if blockers
        else RuntimeExecutionControlledSubmitPlanStatus.READY_FOR_CONTROLLED_SUBMIT_ADAPTER
    )
    return RuntimeExecutionControlledSubmitPlan(
        plan_id=f"runtime-controlled-submit-plan-{authorization.authorization_id}",
        authorization_id=authorization.authorization_id,
        execution_intent_id=intent.id,
        runtime_execution_intent_draft_id=intent.runtime_execution_intent_draft_id,
        source_type=intent.source_type,
        source_id=intent.source_id,
        status=status,
        semantic_ids=intent.semantic_ids,
        symbol=intent.symbol or "unknown",
        side=_optional_str(source_payload.get("side")) or authorization.side,
        candidate_order_type=candidate_order_type,
        proposed_quantity=proposed_quantity,
        intended_notional=intended_notional,
        blockers=blockers,
        warnings=warnings,
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_controlled_submit_plan",
            "non_submitting_plan": True,
            "requires_future_final_gate_execution_check": True,
            "does_not_call_owner_bounded_execution": True,
            "does_not_call_order_lifecycle": True,
            "does_not_call_exchange": True,
        },
    )


def build_runtime_execution_controlled_submit_preflight(
    *,
    plan: RuntimeExecutionControlledSubmitPlan,
    final_gate_preview: RuntimeFinalGatePreview,
    now_ms: int,
) -> RuntimeExecutionControlledSubmitPreflight:
    blockers = list(plan.blockers)
    warnings = list(plan.warnings)
    if plan.status != RuntimeExecutionControlledSubmitPlanStatus.READY_FOR_CONTROLLED_SUBMIT_ADAPTER:
        blockers.append("controlled_submit_plan_not_ready")
    if final_gate_preview.verdict != RuntimeFinalGatePreviewVerdict.PASS:
        blockers.append("runtime_final_gate_execution_check_not_passed")
    blockers.extend(final_gate_preview.blockers)
    warnings.extend(final_gate_preview.warnings)
    status = (
        RuntimeExecutionControlledSubmitPreflightStatus.BLOCKED
        if blockers
        else RuntimeExecutionControlledSubmitPreflightStatus.READY_FOR_CONTROLLED_SUBMIT_ADAPTER
    )
    return RuntimeExecutionControlledSubmitPreflight(
        preflight_id=f"runtime-controlled-submit-preflight-{plan.authorization_id}",
        plan_id=plan.plan_id,
        authorization_id=plan.authorization_id,
        execution_intent_id=plan.execution_intent_id,
        order_candidate_id=plan.source_id,
        status=status,
        controlled_submit_plan_status=plan.status,
        final_gate_verdict=final_gate_preview.verdict,
        final_gate_preview=final_gate_preview,
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_controlled_submit_preflight",
            "non_submitting_final_gate_check": True,
            "does_not_call_owner_bounded_execution": True,
            "does_not_call_order_lifecycle": True,
            "does_not_call_exchange": True,
        },
    )


def build_runtime_execution_controlled_submit_result(
    *,
    preflight: RuntimeExecutionControlledSubmitPreflight,
    submit_enabled: bool,
    order_lifecycle_adapter_enabled: bool = False,
    now_ms: int,
) -> RuntimeExecutionControlledSubmitResult:
    blockers = list(preflight.blockers)
    warnings = list(preflight.warnings)
    if preflight.status != RuntimeExecutionControlledSubmitPreflightStatus.READY_FOR_CONTROLLED_SUBMIT_ADAPTER:
        blockers.append("controlled_submit_preflight_not_ready")
        status = RuntimeExecutionControlledSubmitResultStatus.BLOCKED
    elif not submit_enabled:
        blockers.append("controlled_submit_adapter_disabled")
        status = RuntimeExecutionControlledSubmitResultStatus.SUBMIT_ADAPTER_NOT_ENABLED
    elif not order_lifecycle_adapter_enabled:
        blockers.append("order_lifecycle_adapter_disabled")
        status = RuntimeExecutionControlledSubmitResultStatus.ORDER_LIFECYCLE_ADAPTER_DISABLED
    else:
        blockers.append("controlled_real_submit_path_not_implemented")
        status = RuntimeExecutionControlledSubmitResultStatus.SUBMIT_ADAPTER_NOT_IMPLEMENTED
    return RuntimeExecutionControlledSubmitResult(
        result_id=f"runtime-controlled-submit-result-{preflight.authorization_id}",
        plan_id=preflight.plan_id,
        preflight_id=preflight.preflight_id,
        authorization_id=preflight.authorization_id,
        execution_intent_id=preflight.execution_intent_id,
        preflight_status=preflight.status,
        final_gate_verdict=preflight.final_gate_verdict,
        status=status,
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        submit_enabled=submit_enabled,
        order_lifecycle_adapter_enabled=order_lifecycle_adapter_enabled,
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_controlled_submit_result",
            "controlled_submit_preflight_required": True,
            "controlled_submit_preflight_status": preflight.status.value,
            "final_gate_verdict": preflight.final_gate_verdict.value,
            "dry_run_submit_adapter_ready": True,
            "order_lifecycle_adapter_enabled": order_lifecycle_adapter_enabled,
            "default_no_submit": True,
            "does_not_call_owner_bounded_execution": True,
            "does_not_call_order_lifecycle": True,
            "does_not_call_exchange": True,
        },
    )


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
