"""Owner submit authorization record for runtime ExecutionIntent.

This artifact records Owner approval for a recorded runtime intent to be
considered by a future controlled submit path. It does not submit orders and
does not call exchange.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.runtime_execution_intent_adapter import (
    RuntimeExecutionSubmitReadiness,
    RuntimeExecutionSubmitReadinessStatus,
)


class RuntimeExecutionSubmitAuthorizationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeExecutionSubmitAuthorizationStatus(str, Enum):
    APPROVED_PENDING_CONTROLLED_SUBMIT = "approved_pending_controlled_submit"


class RuntimeExecutionSubmitAuthorization(RuntimeExecutionSubmitAuthorizationModel):
    authorization_id: str = Field(min_length=1, max_length=220)
    execution_intent_id: str = Field(min_length=1, max_length=64)
    runtime_execution_intent_draft_id: Optional[str] = Field(default=None, max_length=180)
    source_type: Optional[str] = Field(default=None, max_length=64)
    source_id: Optional[str] = Field(default=None, max_length=128)
    status: RuntimeExecutionSubmitAuthorizationStatus
    semantic_ids: BrcSemanticIds
    symbol: str = Field(min_length=1, max_length=128)
    side: Optional[str] = Field(default=None, max_length=32)
    owner_confirmed_for_submit: Literal[True] = True
    owner_submit_authorized: Literal[True] = True
    submit_executed: Literal[False] = False
    order_created: Literal[False] = False
    exchange_called: Literal[False] = False
    owner_bounded_execution_called: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "RuntimeExecutionSubmitAuthorization":
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
                    f"submit authorization contains forbidden execution field: {key}"
                )
        return self


def build_runtime_execution_submit_authorization(
    *,
    readiness: RuntimeExecutionSubmitReadiness,
    owner_confirmed_for_submit: bool,
    now_ms: int,
) -> RuntimeExecutionSubmitAuthorization:
    if readiness.status != RuntimeExecutionSubmitReadinessStatus.OWNER_SUBMIT_AUTHORIZATION_REQUIRED:
        raise ValueError("RuntimeExecutionSubmitReadiness is not ready for Owner submit authorization")
    if not owner_confirmed_for_submit:
        raise ValueError("owner_submit_confirmation_required")
    return RuntimeExecutionSubmitAuthorization(
        authorization_id=f"runtime-submit-authorization-{readiness.execution_intent_id}",
        execution_intent_id=readiness.execution_intent_id,
        runtime_execution_intent_draft_id=readiness.runtime_execution_intent_draft_id,
        source_type=readiness.source_type,
        source_id=readiness.source_id,
        status=RuntimeExecutionSubmitAuthorizationStatus.APPROVED_PENDING_CONTROLLED_SUBMIT,
        semantic_ids=readiness.semantic_ids,
        symbol=readiness.symbol,
        side=readiness.side,
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_submit_authorization",
            "owner_authorized_future_controlled_submit": True,
            "non_submitting_record": True,
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
