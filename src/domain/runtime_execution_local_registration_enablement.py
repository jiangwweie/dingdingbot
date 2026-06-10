"""Auditable enablement decision for runtime local order registration.

This model freezes the facts needed before a first-real-submit local
registration action may run. It is still not exchange-submit authority.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.runtime_execution_local_registration_gate import (
    RuntimeExecutionLocalRegistrationGate,
    RuntimeExecutionLocalRegistrationGateStatus,
    build_runtime_execution_local_registration_gate,
)
from src.domain.runtime_execution_order_registration_draft import (
    RuntimeExecutionOrderRegistrationDraftPreview,
)


class RuntimeExecutionLocalRegistrationEnablementModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeExecutionLocalRegistrationEnablementStatus(str, Enum):
    BLOCKED = "blocked"
    READY_FOR_LOCAL_REGISTRATION_ACTION = "ready_for_local_registration_action"


class RuntimeExecutionLocalRegistrationEnablementDecision(
    RuntimeExecutionLocalRegistrationEnablementModel
):
    decision_id: str = Field(min_length=1, max_length=460)
    authorization_id: str = Field(min_length=1, max_length=220)
    execution_intent_id: str = Field(min_length=1, max_length=64)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    source_type: Optional[str] = Field(default=None, max_length=64)
    source_id: Optional[str] = Field(default=None, max_length=128)
    semantic_ids: BrcSemanticIds
    status: RuntimeExecutionLocalRegistrationEnablementStatus
    local_registration_gate: RuntimeExecutionLocalRegistrationGate
    deployment_evidence_id: Optional[str] = Field(default=None, max_length=220)
    owner_real_submit_authorization_id: Optional[str] = Field(
        default=None,
        max_length=220,
    )
    owner_live_runtime_enablement_authorization_id: Optional[str] = Field(
        default=None,
        max_length=220,
    )
    order_lifecycle_adapter_enablement_id: Optional[str] = Field(
        default=None,
        max_length=220,
    )
    local_order_registration_enablement_id: Optional[str] = Field(
        default=None,
        max_length=220,
    )
    local_registration_action_authorization_id: Optional[str] = Field(
        default=None,
        max_length=220,
    )
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
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
    def _validate_decision(self) -> "RuntimeExecutionLocalRegistrationEnablementDecision":
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
                    f"local registration enablement contains forbidden execution field: {key}"
                )
        if self.exchange_called or self.exchange_order_submitted:
            raise ValueError("local registration enablement cannot call exchange")
        if self.execution_intent_status_changed:
            raise ValueError("local registration enablement cannot change intent status")
        if self.owner_bounded_execution_called:
            raise ValueError(
                "local registration enablement cannot call OwnerBoundedExecution"
            )
        if self.withdrawal_or_transfer_created:
            raise ValueError(
                "local registration enablement cannot create withdrawal/transfer"
            )
        if (
            self.status
            == RuntimeExecutionLocalRegistrationEnablementStatus.READY_FOR_LOCAL_REGISTRATION_ACTION
            and self.blockers
        ):
            raise ValueError("ready local registration enablement cannot have blockers")
        return self


def build_runtime_execution_local_registration_enablement_decision(
    *,
    registration_preview: RuntimeExecutionOrderRegistrationDraftPreview,
    current_head_deployed: bool = False,
    runtime_live_execution_enabled: bool = False,
    order_lifecycle_adapter_enabled: bool = False,
    local_order_registration_enabled: bool = False,
    deployment_evidence_id: str | None = None,
    owner_real_submit_authorization_id: str | None = None,
    owner_live_runtime_enablement_authorization_id: str | None = None,
    order_lifecycle_adapter_enablement_id: str | None = None,
    local_order_registration_enablement_id: str | None = None,
    local_registration_action_authorization_id: str | None = None,
    now_ms: int,
) -> RuntimeExecutionLocalRegistrationEnablementDecision:
    owner_real_submit_authorized = bool(
        _present(owner_real_submit_authorization_id)
    )
    owner_live_runtime_enablement_authorized = bool(
        _present(owner_live_runtime_enablement_authorization_id)
    )
    local_registration_action_authorized = bool(
        _present(local_registration_action_authorization_id)
    )
    gate = build_runtime_execution_local_registration_gate(
        registration_preview=registration_preview,
        current_head_deployed=current_head_deployed,
        owner_real_submit_authorized=owner_real_submit_authorized,
        owner_live_runtime_enablement_authorized=(
            owner_live_runtime_enablement_authorized
        ),
        runtime_live_execution_enabled=runtime_live_execution_enabled,
        order_lifecycle_adapter_enabled=order_lifecycle_adapter_enabled,
        local_order_registration_enabled=local_order_registration_enabled,
        local_registration_action_authorized=(
            local_registration_action_authorized
        ),
        now_ms=now_ms,
    )

    blockers = list(gate.blockers)
    if not _present(deployment_evidence_id):
        blockers.append("deployment_evidence_id_missing")
    if not _present(owner_real_submit_authorization_id):
        blockers.append("owner_real_submit_authorization_id_missing")
    if not _present(owner_live_runtime_enablement_authorization_id):
        blockers.append("owner_live_runtime_enablement_authorization_id_missing")
    if not _present(order_lifecycle_adapter_enablement_id):
        blockers.append("order_lifecycle_adapter_enablement_id_missing")
    if not _present(local_order_registration_enablement_id):
        blockers.append("local_order_registration_enablement_id_missing")
    if not _present(local_registration_action_authorization_id):
        blockers.append("local_registration_action_authorization_id_missing")
    if (
        gate.status
        != RuntimeExecutionLocalRegistrationGateStatus
        .READY_FOR_LOCAL_CREATED_ORDER_REGISTRATION
    ):
        blockers.append("local_registration_gate_not_ready")

    status = (
        RuntimeExecutionLocalRegistrationEnablementStatus.BLOCKED
        if blockers
        else RuntimeExecutionLocalRegistrationEnablementStatus
        .READY_FOR_LOCAL_REGISTRATION_ACTION
    )
    return RuntimeExecutionLocalRegistrationEnablementDecision(
        decision_id=(
            "runtime-local-registration-enablement-"
            f"{registration_preview.authorization_id}"
        ),
        authorization_id=registration_preview.authorization_id,
        execution_intent_id=registration_preview.execution_intent_id,
        runtime_instance_id=registration_preview.runtime_instance_id,
        source_type=registration_preview.source_type,
        source_id=registration_preview.source_id,
        semantic_ids=registration_preview.semantic_ids,
        status=status,
        local_registration_gate=gate,
        deployment_evidence_id=_optional_str(deployment_evidence_id),
        owner_real_submit_authorization_id=_optional_str(
            owner_real_submit_authorization_id
        ),
        owner_live_runtime_enablement_authorization_id=_optional_str(
            owner_live_runtime_enablement_authorization_id
        ),
        order_lifecycle_adapter_enablement_id=_optional_str(
            order_lifecycle_adapter_enablement_id
        ),
        local_order_registration_enablement_id=_optional_str(
            local_order_registration_enablement_id
        ),
        local_registration_action_authorization_id=_optional_str(
            local_registration_action_authorization_id
        ),
        blockers=_dedupe(blockers),
        warnings=list(gate.warnings),
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_local_registration_enablement",
            "first_real_submit_local_registration_decision": True,
            "local_created_order_registration_only": True,
            "does_not_register_created_orders": True,
            "does_not_change_execution_intent_status": True,
            "does_not_submit_exchange_order": True,
            "does_not_call_exchange": True,
            "does_not_call_owner_bounded_execution": True,
            "does_not_create_withdrawal_or_transfer": True,
        },
    )


def _present(value: str | None) -> bool:
    return bool(str(value or "").strip())


def _optional_str(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


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
