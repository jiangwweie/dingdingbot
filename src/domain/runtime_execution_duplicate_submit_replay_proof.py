"""Read-only duplicate-submit replay proof for first-real-submit review."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.runtime_execution_exchange_submit_adapter_result import (
    RuntimeExecutionExchangeSubmitAdapterResult,
    RuntimeExecutionExchangeSubmitAdapterResultStatus,
)
from src.domain.runtime_execution_exchange_submit_enablement import (
    RuntimeExecutionExchangeSubmitEnablementDecision,
)
from src.domain.runtime_execution_exchange_submit_execution_result import (
    RuntimeExecutionExchangeSubmitExecutionResult,
)
from src.domain.runtime_execution_submit_idempotency import (
    RuntimeExecutionSubmitIdempotencySnapshot,
    RuntimeExecutionSubmitIdempotencyStatus,
)


class RuntimeExecutionDuplicateSubmitReplayProofModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeExecutionDuplicateSubmitReplayProofStatus(str, Enum):
    BLOCKED = "blocked"
    READY_FOR_FIRST_REAL_SUBMIT_REPLAY_GUARD = (
        "ready_for_first_real_submit_replay_guard"
    )


class RuntimeExecutionDuplicateSubmitReplayProof(
    RuntimeExecutionDuplicateSubmitReplayProofModel
):
    proof_id: str = Field(min_length=1, max_length=520)
    authorization_id: str = Field(min_length=1, max_length=220)
    execution_intent_id: str = Field(min_length=1, max_length=64)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    source_type: Optional[str] = Field(default=None, max_length=64)
    source_id: Optional[str] = Field(default=None, max_length=128)
    semantic_ids: BrcSemanticIds
    status: RuntimeExecutionDuplicateSubmitReplayProofStatus
    submit_idempotency_policy_id: Optional[str] = Field(default=None, max_length=260)
    stable_submit_key: Optional[str] = Field(default=None, max_length=260)
    replay_lock_key: Optional[str] = Field(default=None, max_length=260)
    duplicate_submit_policy_ready: bool = False
    replay_key_matches_authorization: bool = False
    retry_uses_same_key: bool = False
    replay_existing_result_on_duplicate: bool = False
    blocks_concurrent_submit_without_lock: bool = False
    adapter_result_repository_available: bool = False
    execution_result_repository_available: bool = False
    existing_adapter_result_id: Optional[str] = Field(default=None, max_length=520)
    existing_adapter_result_status: Optional[str] = Field(default=None, max_length=96)
    existing_execution_result_id: Optional[str] = Field(default=None, max_length=540)
    existing_execution_result_status: Optional[str] = Field(default=None, max_length=96)
    adapter_result_replay_safe: bool = False
    execution_result_replay_safe: bool = False
    first_submit_not_already_executed: bool = False
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    not_live_action_authorization: Literal[True] = True
    not_exchange_submit_authority: Literal[True] = True
    not_order_lifecycle_authority: Literal[True] = True
    execution_intent_status_changed: Literal[False] = False
    order_created: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    exchange_called: Literal[False] = False
    exchange_order_submitted: Literal[False] = False
    owner_bounded_execution_called: Literal[False] = False
    runtime_state_mutated: Literal[False] = False
    withdrawal_or_transfer_created: Literal[False] = False
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_proof(self) -> "RuntimeExecutionDuplicateSubmitReplayProof":
        _reject_forbidden_execution_fields(
            "duplicate submit replay proof",
            {"metadata": self.metadata},
        )
        if (
            self.status
            == (
                RuntimeExecutionDuplicateSubmitReplayProofStatus
                .READY_FOR_FIRST_REAL_SUBMIT_REPLAY_GUARD
            )
            and self.blockers
        ):
            raise ValueError("ready duplicate replay proof cannot have blockers")
        if (
            self.execution_intent_status_changed
            or self.order_created
            or self.order_lifecycle_called
            or self.exchange_called
            or self.exchange_order_submitted
            or self.owner_bounded_execution_called
            or self.runtime_state_mutated
            or self.withdrawal_or_transfer_created
        ):
            raise ValueError("duplicate replay proof cannot perform execution")
        return self


def build_runtime_execution_duplicate_submit_replay_proof(
    *,
    enablement_decision: RuntimeExecutionExchangeSubmitEnablementDecision,
    submit_idempotency_snapshot: RuntimeExecutionSubmitIdempotencySnapshot | None,
    existing_adapter_result: RuntimeExecutionExchangeSubmitAdapterResult | None,
    existing_execution_result: RuntimeExecutionExchangeSubmitExecutionResult | None,
    adapter_result_repository_available: bool,
    execution_result_repository_available: bool,
    now_ms: int,
    additional_blockers: list[str] | None = None,
    additional_warnings: list[str] | None = None,
) -> RuntimeExecutionDuplicateSubmitReplayProof:
    blockers = list(additional_blockers or [])
    warnings = list(additional_warnings or [])

    idempotency_ready = False
    replay_key_matches = False
    retry_uses_same_key = False
    replay_existing_result = False
    blocks_concurrent_without_lock = False
    stable_submit_key: str | None = None
    replay_lock_key: str | None = None

    if submit_idempotency_snapshot is None:
        blockers.append("submit_idempotency_policy_not_found")
    else:
        idempotency_ready = submit_idempotency_snapshot.status == (
            RuntimeExecutionSubmitIdempotencyStatus
            .READY_FOR_NON_EXECUTING_POLICY_CONFIRMATION
        )
        stable_submit_key = submit_idempotency_snapshot.stable_submit_key
        replay_lock_key = submit_idempotency_snapshot.replay_lock_key
        replay_key_matches = replay_lock_key == enablement_decision.authorization_id
        retry_uses_same_key = bool(submit_idempotency_snapshot.retry_uses_same_key)
        replay_existing_result = bool(
            submit_idempotency_snapshot.replay_existing_result_on_duplicate
        )
        blocks_concurrent_without_lock = bool(
            submit_idempotency_snapshot.blocks_concurrent_submit_without_lock
        )
        if not idempotency_ready:
            blockers.append("submit_idempotency_policy_not_ready")
        if submit_idempotency_snapshot.authorization_id != (
            enablement_decision.authorization_id
        ):
            blockers.append("submit_idempotency_authorization_mismatch")
        if submit_idempotency_snapshot.execution_intent_id != (
            enablement_decision.execution_intent_id
        ):
            blockers.append("submit_idempotency_intent_mismatch")
        if (
            submit_idempotency_snapshot.runtime_instance_id
            and submit_idempotency_snapshot.runtime_instance_id
            != enablement_decision.runtime_instance_id
        ):
            blockers.append("submit_idempotency_runtime_mismatch")
        if not replay_key_matches:
            blockers.append("submit_idempotency_replay_key_mismatch")
        if not replay_existing_result:
            blockers.append("submit_idempotency_duplicate_replay_not_enabled")
        if not retry_uses_same_key:
            blockers.append("submit_idempotency_retry_same_key_not_enabled")
        if not blocks_concurrent_without_lock:
            blockers.append("submit_idempotency_concurrent_lock_not_required")
        if not submit_idempotency_snapshot.adapter_result_store_required:
            blockers.append("submit_idempotency_adapter_result_store_not_required")
        if not submit_idempotency_snapshot.not_execution_authority:
            blockers.append("submit_idempotency_snapshot_execution_authority")
        if submit_idempotency_snapshot.order_created:
            blockers.append("submit_idempotency_snapshot_created_order")
        if submit_idempotency_snapshot.exchange_called:
            blockers.append("submit_idempotency_snapshot_called_exchange")
        if submit_idempotency_snapshot.order_lifecycle_called:
            blockers.append("submit_idempotency_snapshot_called_order_lifecycle")
        warnings.extend(
            f"submit_idempotency:{warning}"
            for warning in submit_idempotency_snapshot.warnings
        )

    if not adapter_result_repository_available:
        blockers.append("exchange_submit_adapter_result_repository_unavailable")
    adapter_replay_safe = adapter_result_repository_available
    if existing_adapter_result is not None:
        adapter_replay_safe = _adapter_result_replay_safe(
            existing_adapter_result,
            enablement_decision=enablement_decision,
            blockers=blockers,
            warnings=warnings,
        )

    if not execution_result_repository_available:
        blockers.append("runtime_exchange_submit_execution_result_repository_unavailable")
    execution_replay_safe = execution_result_repository_available
    first_submit_not_already_executed = existing_execution_result is None
    if existing_execution_result is not None:
        execution_replay_safe = _execution_result_replay_safe(
            existing_execution_result,
            enablement_decision=enablement_decision,
            blockers=blockers,
            warnings=warnings,
        )
        blockers.append("exchange_submit_execution_result_already_exists_replay_only")

    blockers = _dedupe(blockers)
    warnings = _dedupe(warnings)
    status = (
        RuntimeExecutionDuplicateSubmitReplayProofStatus.BLOCKED
        if blockers
        else (
            RuntimeExecutionDuplicateSubmitReplayProofStatus
            .READY_FOR_FIRST_REAL_SUBMIT_REPLAY_GUARD
        )
    )
    return RuntimeExecutionDuplicateSubmitReplayProof(
        proof_id=(
            "runtime-duplicate-submit-replay-proof-"
            f"{enablement_decision.authorization_id}"
        ),
        authorization_id=enablement_decision.authorization_id,
        execution_intent_id=enablement_decision.execution_intent_id,
        runtime_instance_id=enablement_decision.runtime_instance_id,
        source_type=enablement_decision.source_type,
        source_id=enablement_decision.source_id,
        semantic_ids=enablement_decision.semantic_ids,
        status=status,
        submit_idempotency_policy_id=enablement_decision.submit_idempotency_policy_id,
        stable_submit_key=stable_submit_key,
        replay_lock_key=replay_lock_key,
        duplicate_submit_policy_ready=idempotency_ready,
        replay_key_matches_authorization=replay_key_matches,
        retry_uses_same_key=retry_uses_same_key,
        replay_existing_result_on_duplicate=replay_existing_result,
        blocks_concurrent_submit_without_lock=blocks_concurrent_without_lock,
        adapter_result_repository_available=adapter_result_repository_available,
        execution_result_repository_available=execution_result_repository_available,
        existing_adapter_result_id=(
            existing_adapter_result.adapter_result_id
            if existing_adapter_result is not None
            else None
        ),
        existing_adapter_result_status=(
            existing_adapter_result.status.value
            if existing_adapter_result is not None
            else None
        ),
        existing_execution_result_id=(
            existing_execution_result.execution_result_id
            if existing_execution_result is not None
            else None
        ),
        existing_execution_result_status=(
            existing_execution_result.status.value
            if existing_execution_result is not None
            else None
        ),
        adapter_result_replay_safe=adapter_replay_safe,
        execution_result_replay_safe=execution_replay_safe,
        first_submit_not_already_executed=first_submit_not_already_executed,
        blockers=blockers,
        warnings=warnings,
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_duplicate_submit_replay_proof",
            "read_only_replay_proof": True,
            "lock_identity": "authorization_id",
            "replay_identity": "authorization_id",
            "does_not_acquire_lock": True,
            "does_not_call_order_lifecycle": True,
            "does_not_call_exchange": True,
            "does_not_create_order": True,
        },
    )


def _adapter_result_replay_safe(
    result: RuntimeExecutionExchangeSubmitAdapterResult,
    *,
    enablement_decision: RuntimeExecutionExchangeSubmitEnablementDecision,
    blockers: list[str],
    warnings: list[str],
) -> bool:
    safe = True
    if result.authorization_id != enablement_decision.authorization_id:
        blockers.append("exchange_submit_adapter_result_authorization_mismatch")
        safe = False
    if result.execution_intent_id != enablement_decision.execution_intent_id:
        blockers.append("exchange_submit_adapter_result_intent_mismatch")
        safe = False
    if result.runtime_instance_id != enablement_decision.runtime_instance_id:
        blockers.append("exchange_submit_adapter_result_runtime_mismatch")
        safe = False
    if result.status == (
        RuntimeExecutionExchangeSubmitAdapterResultStatus.EXCHANGE_SUBMIT_LOCK_ACQUIRED
    ):
        blockers.append("exchange_submit_adapter_result_pending_lock")
        safe = False
    if result.exchange_submit_adapter_implemented:
        blockers.append("exchange_submit_adapter_result_implemented_real_adapter")
        safe = False
    if result.order_lifecycle_submit_called:
        blockers.append("exchange_submit_adapter_result_called_order_lifecycle")
        safe = False
    if result.execution_intent_status_changed:
        blockers.append("exchange_submit_adapter_result_changed_intent_status")
        safe = False
    if result.exchange_order_submitted:
        blockers.append("exchange_submit_adapter_result_submitted_exchange_order")
        safe = False
    if result.exchange_called:
        blockers.append("exchange_submit_adapter_result_called_exchange")
        safe = False
    if result.owner_bounded_execution_called:
        blockers.append("exchange_submit_adapter_result_called_owner_bounded_execution")
        safe = False
    if result.withdrawal_or_transfer_created:
        blockers.append("exchange_submit_adapter_result_created_withdrawal_or_transfer")
        safe = False
    if safe:
        warnings.append("existing_exchange_submit_adapter_result_will_replay")
    return safe


def _execution_result_replay_safe(
    result: RuntimeExecutionExchangeSubmitExecutionResult,
    *,
    enablement_decision: RuntimeExecutionExchangeSubmitEnablementDecision,
    blockers: list[str],
    warnings: list[str],
) -> bool:
    safe = True
    if result.authorization_id != enablement_decision.authorization_id:
        blockers.append("exchange_submit_execution_result_authorization_mismatch")
        safe = False
    if result.execution_intent_id != enablement_decision.execution_intent_id:
        blockers.append("exchange_submit_execution_result_intent_mismatch")
        safe = False
    if result.runtime_instance_id != enablement_decision.runtime_instance_id:
        blockers.append("exchange_submit_execution_result_runtime_mismatch")
        safe = False
    if result.execution_intent_status_changed:
        blockers.append("exchange_submit_execution_result_changed_intent_status")
        safe = False
    if result.owner_bounded_execution_called:
        blockers.append("exchange_submit_execution_result_called_owner_bounded_execution")
        safe = False
    if result.withdrawal_or_transfer_created:
        blockers.append("exchange_submit_execution_result_created_withdrawal_or_transfer")
        safe = False
    warnings.append("existing_exchange_submit_execution_result_will_replay")
    return safe


def _reject_forbidden_execution_fields(context: str, value: Any) -> None:
    forbidden = {
        "api_key",
        "api_secret",
        "secret",
        "credential",
        "exchange_payload",
        "place_order",
        "submit_order",
        "withdrawal_payload",
        "transfer_payload",
    }
    for key in _walk_keys(value):
        if key.lower() in forbidden:
            raise ValueError(f"{context} contains forbidden execution field: {key}")


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
