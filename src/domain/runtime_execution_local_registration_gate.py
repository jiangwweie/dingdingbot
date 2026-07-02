"""First-real-submit local registration gate.

This gate is narrower than real submit authority. It can prove whether a future
runtime adapter may proceed toward local CREATED-order registration, but it
cannot submit exchange orders, change ExecutionIntent status, or create
withdrawals/transfers.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.runtime_execution_order_registration_draft import (
    RuntimeExecutionOrderRegistrationDraftPreview,
    RuntimeExecutionOrderRegistrationDraftPreviewStatus,
)


class RuntimeExecutionLocalRegistrationGateModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeExecutionLocalRegistrationGateStatus(str, Enum):
    BLOCKED = "blocked"
    READY_FOR_LOCAL_CREATED_ORDER_REGISTRATION = (
        "ready_for_local_created_order_registration"
    )


class RuntimeExecutionLocalRegistrationGate(
    RuntimeExecutionLocalRegistrationGateModel
):
    gate_id: str = Field(min_length=1, max_length=420)
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
    status: RuntimeExecutionLocalRegistrationGateStatus
    symbol: str = Field(min_length=1, max_length=128)
    side: str = Field(min_length=1, max_length=32)
    owner_real_submit_authorized: bool = False
    trusted_submit_facts_ready: bool = False
    submit_idempotency_policy_ready: bool = False
    attempt_outcome_policy_ready: bool = False
    protection_failure_policy_ready: bool = False
    order_lifecycle_adapter_enabled: bool = False
    local_order_registration_enabled: bool = False
    local_registration_action_authorized: bool = False
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    requires_persistent_duplicate_submit_lock: Literal[True] = True
    not_real_submit_authority: Literal[True] = True
    not_exchange_order_authority: Literal[True] = True
    local_order_registration_executed: Literal[False] = False
    execution_intent_status_changed: Literal[False] = False
    exchange_order_submitted: Literal[False] = False
    exchange_called: Literal[False] = False
    owner_bounded_execution_called: Literal[False] = False
    withdrawal_or_transfer_created: Literal[False] = False
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_gate(self) -> "RuntimeExecutionLocalRegistrationGate":
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
                    f"local registration gate contains forbidden execution field: {key}"
                )
        if (
            self.status
            == RuntimeExecutionLocalRegistrationGateStatus.READY_FOR_LOCAL_CREATED_ORDER_REGISTRATION
            and self.blockers
        ):
            raise ValueError("ready local registration gate cannot have blockers")
        if self.exchange_called or self.exchange_order_submitted:
            raise ValueError("local registration gate cannot call exchange")
        if self.execution_intent_status_changed:
            raise ValueError("local registration gate cannot change intent status")
        if self.owner_bounded_execution_called:
            raise ValueError("local registration gate cannot call OwnerBoundedExecution")
        if self.withdrawal_or_transfer_created:
            raise ValueError("local registration gate cannot create withdrawal/transfer")
        return self


def build_runtime_execution_local_registration_gate(
    *,
    registration_preview: RuntimeExecutionOrderRegistrationDraftPreview,
    owner_real_submit_authorized: bool = False,
    trusted_submit_facts_ready: bool = False,
    submit_idempotency_policy_ready: bool = False,
    attempt_outcome_policy_ready: bool = False,
    protection_failure_policy_ready: bool = False,
    order_lifecycle_adapter_enabled: bool = False,
    local_order_registration_enabled: bool = False,
    local_registration_action_authorized: bool = False,
    now_ms: int,
) -> RuntimeExecutionLocalRegistrationGate:
    blockers = list(registration_preview.blockers)
    warnings = list(registration_preview.warnings)
    if (
        registration_preview.status
        != RuntimeExecutionOrderRegistrationDraftPreviewStatus.INPUTS_READY_REGISTRATION_DRAFT_ONLY
    ):
        blockers.append("order_registration_draft_preview_not_ready")
    if not owner_real_submit_authorized:
        blockers.append("owner_real_submit_authorization_missing")
    if not trusted_submit_facts_ready:
        blockers.append("trusted_submit_fact_snapshot_missing")
    if not submit_idempotency_policy_ready:
        blockers.append("submit_idempotency_policy_missing")
    if not attempt_outcome_policy_ready:
        blockers.append("attempt_outcome_policy_missing")
    if not protection_failure_policy_ready:
        blockers.append("protection_failure_policy_missing")
    if not order_lifecycle_adapter_enabled:
        blockers.append("order_lifecycle_adapter_disabled")
    if not local_order_registration_enabled:
        blockers.append("local_order_registration_disabled")
    if not local_registration_action_authorized:
        blockers.append("local_registration_action_authorization_missing")

    status = (
        RuntimeExecutionLocalRegistrationGateStatus.BLOCKED
        if blockers
        else RuntimeExecutionLocalRegistrationGateStatus.READY_FOR_LOCAL_CREATED_ORDER_REGISTRATION
    )
    return RuntimeExecutionLocalRegistrationGate(
        gate_id=(
            "runtime-local-registration-gate-"
            f"{registration_preview.authorization_id}"
        ),
        registration_preview_id=registration_preview.registration_preview_id,
        adapter_preview_id=registration_preview.adapter_preview_id,
        handoff_draft_id=registration_preview.handoff_draft_id,
        preflight_id=registration_preview.preflight_id,
        authorization_id=registration_preview.authorization_id,
        execution_intent_id=registration_preview.execution_intent_id,
        runtime_instance_id=registration_preview.runtime_instance_id,
        source_type=registration_preview.source_type,
        source_id=registration_preview.source_id,
        semantic_ids=registration_preview.semantic_ids,
        status=status,
        symbol=registration_preview.symbol,
        side=registration_preview.side,
        owner_real_submit_authorized=owner_real_submit_authorized,
        trusted_submit_facts_ready=trusted_submit_facts_ready,
        submit_idempotency_policy_ready=submit_idempotency_policy_ready,
        attempt_outcome_policy_ready=attempt_outcome_policy_ready,
        protection_failure_policy_ready=protection_failure_policy_ready,
        order_lifecycle_adapter_enabled=order_lifecycle_adapter_enabled,
        local_order_registration_enabled=local_order_registration_enabled,
        local_registration_action_authorized=local_registration_action_authorized,
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_local_registration_gate",
            "first_real_submit_local_registration_gate": True,
            "local_created_order_registration_only": True,
            "requires_persistent_duplicate_submit_lock": True,
            "does_not_submit_exchange_order": True,
            "does_not_call_exchange": True,
            "does_not_change_execution_intent_status": True,
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
