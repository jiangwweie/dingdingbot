"""Non-executing adapter preview for runtime candidates to ExecutionIntent.

This module defines adapter preview and binding contracts only. It does not
create ExecutionIntent records and does not project OrderCandidate into legacy
SignalResult.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.execution_intent import ExecutionIntent, ExecutionIntentStatus
from src.domain.runtime_execution_plan import (
    RuntimeExecutionIntentDraft,
    RuntimeExecutionIntentDraftStatus,
)


class RuntimeExecutionIntentAdapterModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeExecutionIntentSourceType(str, Enum):
    BRC_RUNTIME_ORDER_CANDIDATE = "brc_runtime_order_candidate"


class RuntimeExecutionIntentCreationPreviewStatus(str, Enum):
    BLOCKED = "blocked"
    READY_FOR_OWNER_GATED_CREATION = "ready_for_owner_gated_creation"


class RuntimeExecutionSubmitReadinessStatus(str, Enum):
    BLOCKED = "blocked"
    OWNER_SUBMIT_AUTHORIZATION_REQUIRED = "owner_submit_authorization_required"


class RuntimeExecutionIntentCreationPreview(RuntimeExecutionIntentAdapterModel):
    adapter_preview_id: str = Field(min_length=1, max_length=220)
    runtime_execution_intent_draft_id: str = Field(min_length=1, max_length=180)
    source_type: RuntimeExecutionIntentSourceType = (
        RuntimeExecutionIntentSourceType.BRC_RUNTIME_ORDER_CANDIDATE
    )
    source_id: str = Field(min_length=1, max_length=128)
    source_payload: dict[str, Any] = Field(default_factory=dict)
    status: RuntimeExecutionIntentCreationPreviewStatus
    semantic_ids: BrcSemanticIds
    symbol: str = Field(min_length=1, max_length=128)
    side: str = Field(min_length=1, max_length=32)
    candidate_order_type: str = Field(min_length=1, max_length=64)
    proposed_quantity: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    intended_notional: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    requires_owner_gated_creation: Literal[True] = True
    compatibility_signal_result_created: Literal[False] = False
    execution_intent_created: Literal[False] = False
    execution_intent_repository_write_enabled: Literal[False] = False
    order_created: Literal[False] = False
    exchange_called: Literal[False] = False
    not_order: Literal[True] = True
    not_execution_intent: Literal[True] = True
    preview_only: Literal[True] = True
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _reject_legacy_signal_projection(self) -> "RuntimeExecutionIntentCreationPreview":
        forbidden = {
            "legacy_signal_result",
            "signal_result",
            "order_strategy",
            "execution_intent",
            "execution_intent_id",
            "order_id",
            "exchange_order_id",
            "client_order_id",
            "place_order",
        }
        for key in _walk_keys({"source_payload": self.source_payload, "metadata": self.metadata}):
            if key.lower() in forbidden:
                raise ValueError(f"adapter preview contains forbidden execution field: {key}")
        return self


def build_runtime_execution_intent_creation_preview(
    *,
    draft: RuntimeExecutionIntentDraft,
    now_ms: int,
) -> RuntimeExecutionIntentCreationPreview:
    blocked = draft.status != RuntimeExecutionIntentDraftStatus.READY_FOR_INTENT_CREATION
    status = (
        RuntimeExecutionIntentCreationPreviewStatus.BLOCKED
        if blocked
        else RuntimeExecutionIntentCreationPreviewStatus.READY_FOR_OWNER_GATED_CREATION
    )
    return RuntimeExecutionIntentCreationPreview(
        adapter_preview_id=f"runtime-intent-adapter-preview-{draft.draft_id}",
        runtime_execution_intent_draft_id=draft.draft_id,
        source_id=draft.order_candidate_id,
        source_payload={
            "runtime_instance_id": draft.runtime_instance_id,
            "order_candidate_id": draft.order_candidate_id,
            "signal_evaluation_id": draft.signal_evaluation_id,
            "strategy_family_version_id": draft.semantic_ids.strategy_family_version_id,
            "side": draft.side,
            "candidate_order_type": draft.candidate_order_type,
            "entry_price_reference": str(draft.entry_price_reference)
            if draft.entry_price_reference is not None
            else None,
            "proposed_quantity": str(draft.proposed_quantity)
            if draft.proposed_quantity is not None
            else None,
            "intended_notional": str(draft.intended_notional)
            if draft.intended_notional is not None
            else None,
            "risk_preview": draft.risk_preview.model_dump(mode="json"),
            "protection_preview": draft.protection_preview.model_dump(mode="json"),
        },
        status=status,
        semantic_ids=draft.semantic_ids,
        symbol=draft.symbol,
        side=draft.side,
        candidate_order_type=draft.candidate_order_type,
        proposed_quantity=draft.proposed_quantity,
        intended_notional=draft.intended_notional,
        blockers=list(draft.blockers),
        warnings=list(draft.warnings),
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_intent_adapter_preview",
            "non_executing_projection": True,
            "does_not_project_legacy_signal_result": True,
        },
    )


class RuntimeExecutionSubmitReadiness(RuntimeExecutionIntentAdapterModel):
    submit_readiness_id: str = Field(min_length=1, max_length=220)
    execution_intent_id: str = Field(min_length=1, max_length=64)
    runtime_execution_intent_draft_id: Optional[str] = Field(default=None, max_length=180)
    source_type: Optional[str] = Field(default=None, max_length=64)
    source_id: Optional[str] = Field(default=None, max_length=128)
    status: RuntimeExecutionSubmitReadinessStatus
    semantic_ids: BrcSemanticIds
    symbol: str = Field(min_length=1, max_length=128)
    side: Optional[str] = Field(default=None, max_length=32)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    requires_owner_submit_authorization: Literal[True] = True
    submit_authorized: Literal[False] = False
    order_created: Literal[False] = False
    exchange_called: Literal[False] = False
    owner_bounded_execution_called: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    preview_only: Literal[True] = True
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "RuntimeExecutionSubmitReadiness":
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
                raise ValueError(f"submit readiness contains forbidden execution field: {key}")
        return self


def build_runtime_execution_submit_readiness(
    *,
    intent: ExecutionIntent,
    now_ms: int,
) -> RuntimeExecutionSubmitReadiness:
    blockers: list[str] = []
    warnings: list[str] = []
    if intent.status != ExecutionIntentStatus.RECORDED:
        blockers.append("execution_intent_not_recorded")
    if intent.source_type != RuntimeExecutionIntentSourceType.BRC_RUNTIME_ORDER_CANDIDATE.value:
        blockers.append("execution_intent_source_not_runtime_order_candidate")
    if not intent.source_id:
        blockers.append("execution_intent_source_id_missing")
    if not intent.symbol:
        blockers.append("symbol_missing")
    if not intent.runtime_execution_intent_draft_id:
        blockers.append("runtime_execution_intent_draft_id_missing")
    if not intent.runtime_instance_id:
        blockers.append("runtime_instance_id_missing")
    if not intent.signal_evaluation_id:
        blockers.append("signal_evaluation_id_missing")
    if not intent.order_candidate_id:
        blockers.append("order_candidate_id_missing")
    if intent.signal is not None or intent.signal_id is not None:
        blockers.append("legacy_signal_projection_present")
    if intent.order_id is not None or intent.exchange_order_id is not None:
        blockers.append("execution_artifact_already_present")

    source_payload = intent.source_payload or {}
    if source_payload.get("submit_authorized") is True:
        blockers.append("unexpected_submit_authorized_flag")
    if source_payload.get("order_created") is True:
        blockers.append("unexpected_order_created_flag")
    if source_payload.get("exchange_called") is True:
        blockers.append("unexpected_exchange_called_flag")
    side = source_payload.get("side")
    if not side:
        warnings.append("side_missing_from_source_payload")

    status = (
        RuntimeExecutionSubmitReadinessStatus.BLOCKED
        if blockers
        else RuntimeExecutionSubmitReadinessStatus.OWNER_SUBMIT_AUTHORIZATION_REQUIRED
    )
    return RuntimeExecutionSubmitReadiness(
        submit_readiness_id=f"runtime-submit-readiness-{intent.id}",
        execution_intent_id=intent.id,
        runtime_execution_intent_draft_id=intent.runtime_execution_intent_draft_id,
        source_type=intent.source_type,
        source_id=intent.source_id,
        status=status,
        semantic_ids=intent.semantic_ids,
        symbol=intent.symbol or "unknown",
        side=str(side) if side else None,
        blockers=blockers,
        warnings=warnings,
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_submit_readiness",
            "non_submitting_gate": True,
            "does_not_call_owner_bounded_execution": True,
            "does_not_call_order_lifecycle": True,
            "does_not_call_exchange": True,
        },
    )


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
