"""Non-executing submit idempotency policy for runtime execution gates.

This module defines the replay/duplicate-submit policy a future real runtime
submit adapter must obey. It does not reserve locks, write adapter results,
create orders, generate exchange payloads, or call an exchange.
"""

from __future__ import annotations

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


class RuntimeExecutionSubmitIdempotencyModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeExecutionSubmitIdempotencyStatus(str, Enum):
    BLOCKED = "blocked"
    READY_FOR_NON_EXECUTING_POLICY_CONFIRMATION = (
        "ready_for_non_executing_policy_confirmation"
    )


class RuntimeExecutionSubmitIdempotencySnapshot(
    RuntimeExecutionSubmitIdempotencyModel
):
    submit_idempotency_policy_id: str = Field(min_length=1, max_length=240)
    authorization_id: str = Field(min_length=1, max_length=220)
    execution_intent_id: str = Field(min_length=1, max_length=64)
    runtime_execution_intent_draft_id: Optional[str] = Field(default=None, max_length=180)
    runtime_instance_id: Optional[str] = Field(default=None, max_length=128)
    source_type: Optional[str] = Field(default=None, max_length=64)
    source_id: Optional[str] = Field(default=None, max_length=128)
    semantic_ids: BrcSemanticIds
    symbol: str = Field(min_length=1, max_length=128)
    side: Optional[str] = Field(default=None, max_length=32)
    status: RuntimeExecutionSubmitIdempotencyStatus
    stable_submit_key: str = Field(min_length=1, max_length=260)
    replay_lock_key: str = Field(min_length=1, max_length=260)
    duplicate_policy: Literal[
        "authorization_id_unique_replay_existing_result"
    ] = "authorization_id_unique_replay_existing_result"
    retry_policy: Literal[
        "retry_same_key_replay_existing_result"
    ] = "retry_same_key_replay_existing_result"
    concurrent_submit_policy: Literal[
        "single_writer_lock_or_replay_existing_result"
    ] = "single_writer_lock_or_replay_existing_result"
    adapter_result_store_required: Literal[True] = True
    adapter_result_store_implemented: bool = False
    real_adapter_boundary_implemented: bool = False
    replay_existing_result_on_duplicate: bool = True
    retry_uses_same_key: bool = True
    blocks_concurrent_submit_without_lock: bool = True
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    not_execution_authority: Literal[True] = True
    execution_intent_status_changed: Literal[False] = False
    runtime_state_mutated: Literal[False] = False
    order_created: Literal[False] = False
    exchange_called: Literal[False] = False
    owner_bounded_execution_called: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    withdrawal_instruction_created: Literal[False] = False
    transfer_instruction_created: Literal[False] = False
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _reject_execution_metadata(
        self,
    ) -> "RuntimeExecutionSubmitIdempotencySnapshot":
        forbidden = {
            "client_order_id",
            "exchange_order_id",
            "exchange_payload",
            "order_id",
            "place_order",
            "submit_order",
            "transfer_payload",
            "withdrawal_payload",
        }
        for key in _walk_keys({"metadata": self.metadata}):
            if key.lower() in forbidden:
                raise ValueError(
                    "submit idempotency snapshot contains forbidden execution "
                    f"field: {key}"
                )
        return self


def build_runtime_execution_submit_idempotency_snapshot(
    *,
    preflight: RuntimeExecutionControlledSubmitPreflight,
    intent: ExecutionIntent,
    now_ms: int,
    adapter_result_store_implemented: bool = False,
    real_adapter_boundary_implemented: bool = False,
) -> RuntimeExecutionSubmitIdempotencySnapshot:
    blockers: list[str] = []
    warnings: list[str] = []
    if preflight.execution_intent_id != intent.id:
        blockers.append("preflight_intent_mismatch")
    if intent.status != ExecutionIntentStatus.RECORDED:
        blockers.append("execution_intent_not_recorded")
    if intent.source_type != RuntimeExecutionIntentSourceType.BRC_RUNTIME_ORDER_CANDIDATE.value:
        blockers.append("execution_intent_source_not_runtime_order_candidate")
    if preflight.status != RuntimeExecutionControlledSubmitPreflightStatus.READY_FOR_CONTROLLED_SUBMIT_ADAPTER:
        blockers.append("controlled_submit_preflight_not_ready")
    if not preflight.authorization_id:
        blockers.append("authorization_id_missing")
    if not intent.runtime_instance_id:
        blockers.append("runtime_instance_id_missing")
    if not intent.source_id:
        blockers.append("source_id_missing")
    if intent.order_id is not None or intent.exchange_order_id is not None:
        blockers.append("execution_artifact_already_present")
    payload = intent.source_payload or {}
    if payload.get("order_created") is True:
        blockers.append("unexpected_intent_order_created_flag")
    if payload.get("exchange_called") is True:
        blockers.append("unexpected_intent_exchange_called_flag")
    if not adapter_result_store_implemented:
        warnings.append("adapter_result_store_not_implemented_current_boundary")
    if not real_adapter_boundary_implemented:
        warnings.append("real_submit_adapter_boundary_not_implemented")

    policy_id = f"runtime-submit-idempotency-{preflight.authorization_id}"
    stable_submit_key = f"runtime-submit:{preflight.authorization_id}"
    status = (
        RuntimeExecutionSubmitIdempotencyStatus.BLOCKED
        if blockers
        else RuntimeExecutionSubmitIdempotencyStatus.READY_FOR_NON_EXECUTING_POLICY_CONFIRMATION
    )
    return RuntimeExecutionSubmitIdempotencySnapshot(
        submit_idempotency_policy_id=policy_id,
        authorization_id=preflight.authorization_id,
        execution_intent_id=preflight.execution_intent_id,
        runtime_execution_intent_draft_id=intent.runtime_execution_intent_draft_id,
        runtime_instance_id=intent.runtime_instance_id,
        source_type=intent.source_type,
        source_id=intent.source_id,
        semantic_ids=intent.semantic_ids,
        symbol=intent.symbol or preflight.final_gate_preview.symbol,
        side=_optional_str(payload.get("side")),
        status=status,
        stable_submit_key=stable_submit_key,
        replay_lock_key=preflight.authorization_id,
        adapter_result_store_implemented=adapter_result_store_implemented,
        real_adapter_boundary_implemented=real_adapter_boundary_implemented,
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_submit_idempotency",
            "non_executing_policy_snapshot": True,
            "lock_identity": "authorization_id",
            "replay_identity": "authorization_id",
            "does_not_create_adapter_result": True,
            "does_not_call_order_lifecycle": True,
            "does_not_call_exchange": True,
        },
    )


def _optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value)
    return text if text else None


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


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
