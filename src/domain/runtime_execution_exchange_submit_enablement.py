"""Auditable enablement decision for runtime exchange submit.

This is the explicit gate after local CREATED-order registration and exchange
submit packet preview. It can prove whether a future adapter may proceed to an
exchange-submit action, but it still does not call OrderLifecycle.submit_order,
ExchangeGateway, OwnerBoundedExecution, withdrawals, or transfers.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.runtime_execution_exchange_submit_packet import (
    RuntimeExecutionExchangeSubmitPacketPreview,
    RuntimeExecutionExchangeSubmitPacketPreviewStatus,
)


class RuntimeExecutionExchangeSubmitEnablementModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeExecutionExchangeSubmitGateStatus(str, Enum):
    BLOCKED = "blocked"
    READY_FOR_EXCHANGE_SUBMIT_ACTION = "ready_for_exchange_submit_action"


class RuntimeExecutionExchangeSubmitGate(
    RuntimeExecutionExchangeSubmitEnablementModel
):
    gate_id: str = Field(min_length=1, max_length=460)
    packet_preview_id: str = Field(min_length=1, max_length=460)
    binding_id: str = Field(min_length=1, max_length=460)
    adapter_result_id: str = Field(min_length=1, max_length=420)
    authorization_id: str = Field(min_length=1, max_length=220)
    execution_intent_id: str = Field(min_length=1, max_length=64)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    source_type: Optional[str] = Field(default=None, max_length=64)
    source_id: Optional[str] = Field(default=None, max_length=128)
    semantic_ids: BrcSemanticIds
    status: RuntimeExecutionExchangeSubmitGateStatus
    symbol: str = Field(min_length=1, max_length=128)
    owner_real_submit_authorized: bool = False
    trusted_submit_facts_ready: bool = False
    submit_idempotency_policy_ready: bool = False
    attempt_outcome_policy_ready: bool = False
    protection_failure_policy_ready: bool = False
    local_registration_enablement_ready: bool = False
    order_lifecycle_submit_enabled: bool = False
    exchange_submit_adapter_enabled: bool = False
    exchange_submit_action_authorized: bool = False
    deployment_readiness_evidence_ready: bool = False
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    requires_persistent_duplicate_submit_lock: Literal[True] = True
    requires_local_created_orders: Literal[True] = True
    requires_exchange_submit_packet_preview: Literal[True] = True
    not_exchange_submit_authority: Literal[True] = True
    order_lifecycle_submit_called: Literal[False] = False
    execution_intent_status_changed: Literal[False] = False
    exchange_order_submitted: Literal[False] = False
    exchange_called: Literal[False] = False
    owner_bounded_execution_called: Literal[False] = False
    withdrawal_or_transfer_created: Literal[False] = False
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_gate(self) -> "RuntimeExecutionExchangeSubmitGate":
        _reject_forbidden_execution_fields(
            "exchange submit gate",
            {"metadata": self.metadata},
        )
        if (
            self.status
            == RuntimeExecutionExchangeSubmitGateStatus.READY_FOR_EXCHANGE_SUBMIT_ACTION
            and self.blockers
        ):
            raise ValueError("ready exchange submit gate cannot have blockers")
        if self.exchange_called or self.exchange_order_submitted:
            raise ValueError("exchange submit gate cannot call exchange")
        if self.order_lifecycle_submit_called:
            raise ValueError("exchange submit gate cannot call OrderLifecycle submit")
        if self.execution_intent_status_changed:
            raise ValueError("exchange submit gate cannot change intent status")
        if self.owner_bounded_execution_called:
            raise ValueError("exchange submit gate cannot call OwnerBoundedExecution")
        if self.withdrawal_or_transfer_created:
            raise ValueError("exchange submit gate cannot create withdrawal/transfer")
        return self


class RuntimeExecutionExchangeSubmitEnablementDecision(
    RuntimeExecutionExchangeSubmitEnablementModel
):
    decision_id: str = Field(min_length=1, max_length=500)
    authorization_id: str = Field(min_length=1, max_length=220)
    execution_intent_id: str = Field(min_length=1, max_length=64)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    source_type: Optional[str] = Field(default=None, max_length=64)
    source_id: Optional[str] = Field(default=None, max_length=128)
    semantic_ids: BrcSemanticIds
    status: RuntimeExecutionExchangeSubmitGateStatus
    exchange_submit_gate: RuntimeExecutionExchangeSubmitGate
    trusted_submit_fact_snapshot_id: Optional[str] = Field(
        default=None,
        max_length=240,
    )
    submit_idempotency_policy_id: Optional[str] = Field(default=None, max_length=240)
    attempt_outcome_policy_id: Optional[str] = Field(default=None, max_length=360)
    protection_creation_failure_policy_id: Optional[str] = Field(
        default=None,
        max_length=300,
    )
    local_registration_enablement_decision_id: Optional[str] = Field(
        default=None,
        max_length=300,
    )
    owner_real_submit_authorization_id: Optional[str] = Field(
        default=None,
        max_length=220,
    )
    order_lifecycle_submit_enablement_id: Optional[str] = Field(
        default=None,
        max_length=220,
    )
    exchange_submit_adapter_enablement_id: Optional[str] = Field(
        default=None,
        max_length=220,
    )
    exchange_submit_action_authorization_id: Optional[str] = Field(
        default=None,
        max_length=360,
    )
    deployment_readiness_evidence_id: Optional[str] = Field(
        default=None,
        max_length=220,
    )
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    not_exchange_submit_authority: Literal[True] = True
    order_lifecycle_submit_called: Literal[False] = False
    execution_intent_status_changed: Literal[False] = False
    exchange_order_submitted: Literal[False] = False
    exchange_called: Literal[False] = False
    owner_bounded_execution_called: Literal[False] = False
    withdrawal_or_transfer_created: Literal[False] = False
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_decision(
        self,
    ) -> "RuntimeExecutionExchangeSubmitEnablementDecision":
        _reject_forbidden_execution_fields(
            "exchange submit enablement",
            {"metadata": self.metadata},
        )
        if (
            self.status
            == RuntimeExecutionExchangeSubmitGateStatus.READY_FOR_EXCHANGE_SUBMIT_ACTION
            and self.blockers
        ):
            raise ValueError("ready exchange submit enablement cannot have blockers")
        if self.exchange_called or self.exchange_order_submitted:
            raise ValueError("exchange submit enablement cannot call exchange")
        if self.order_lifecycle_submit_called:
            raise ValueError(
                "exchange submit enablement cannot call OrderLifecycle submit"
            )
        if self.execution_intent_status_changed:
            raise ValueError("exchange submit enablement cannot change intent status")
        if self.owner_bounded_execution_called:
            raise ValueError(
                "exchange submit enablement cannot call OwnerBoundedExecution"
            )
        if self.withdrawal_or_transfer_created:
            raise ValueError(
                "exchange submit enablement cannot create withdrawal/transfer"
            )
        return self


def build_runtime_execution_exchange_submit_gate(
    *,
    packet_preview: RuntimeExecutionExchangeSubmitPacketPreview,
    owner_real_submit_authorized: bool = False,
    trusted_submit_facts_ready: bool = False,
    submit_idempotency_policy_ready: bool = False,
    attempt_outcome_policy_ready: bool = False,
    protection_failure_policy_ready: bool = False,
    local_registration_enablement_ready: bool = False,
    order_lifecycle_submit_enabled: bool = False,
    exchange_submit_adapter_enabled: bool = False,
    exchange_submit_action_authorized: bool = False,
    deployment_readiness_evidence_ready: bool = False,
    now_ms: int,
) -> RuntimeExecutionExchangeSubmitGate:
    blockers = list(packet_preview.blockers)
    warnings = list(packet_preview.warnings)
    if (
        packet_preview.status
        != RuntimeExecutionExchangeSubmitPacketPreviewStatus
        .READY_FOR_EXCHANGE_SUBMIT_ADAPTER_DESIGN
    ):
        blockers.append("exchange_submit_packet_preview_not_ready")
    if not packet_preview.entry_submit_request_preview:
        blockers.append("entry_exchange_submit_request_preview_missing")
    if not packet_preview.protection_submit_request_previews:
        blockers.append("protection_exchange_submit_request_previews_missing")
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
    if not local_registration_enablement_ready:
        blockers.append("local_registration_enablement_decision_missing")
    if not order_lifecycle_submit_enabled:
        blockers.append("order_lifecycle_submit_disabled")
    if not exchange_submit_adapter_enabled:
        blockers.append("exchange_submit_adapter_disabled")
    if not exchange_submit_action_authorized:
        blockers.append("exchange_submit_action_authorization_missing")
    if not deployment_readiness_evidence_ready:
        warnings.append("deployment_readiness_evidence_id_missing")

    status = (
        RuntimeExecutionExchangeSubmitGateStatus.BLOCKED
        if blockers
        else RuntimeExecutionExchangeSubmitGateStatus.READY_FOR_EXCHANGE_SUBMIT_ACTION
    )
    return RuntimeExecutionExchangeSubmitGate(
        gate_id=f"runtime-exchange-submit-gate-{packet_preview.authorization_id}",
        packet_preview_id=packet_preview.packet_preview_id,
        binding_id=packet_preview.binding_id,
        adapter_result_id=packet_preview.adapter_result_id,
        authorization_id=packet_preview.authorization_id,
        execution_intent_id=packet_preview.execution_intent_id,
        runtime_instance_id=packet_preview.runtime_instance_id,
        source_type=packet_preview.source_type,
        source_id=packet_preview.source_id,
        semantic_ids=packet_preview.semantic_ids,
        status=status,
        symbol=packet_preview.symbol,
        owner_real_submit_authorized=owner_real_submit_authorized,
        trusted_submit_facts_ready=trusted_submit_facts_ready,
        submit_idempotency_policy_ready=submit_idempotency_policy_ready,
        attempt_outcome_policy_ready=attempt_outcome_policy_ready,
        protection_failure_policy_ready=protection_failure_policy_ready,
        local_registration_enablement_ready=local_registration_enablement_ready,
        order_lifecycle_submit_enabled=order_lifecycle_submit_enabled,
        exchange_submit_adapter_enabled=exchange_submit_adapter_enabled,
        exchange_submit_action_authorized=exchange_submit_action_authorized,
        deployment_readiness_evidence_ready=deployment_readiness_evidence_ready,
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_exchange_submit_gate",
            "first_real_submit_exchange_submit_gate": True,
            "requires_local_created_orders": True,
            "local_order_ids": list(packet_preview.local_order_ids),
            "entry_order_id": packet_preview.entry_order_id,
            "protection_order_ids": list(packet_preview.protection_order_ids),
            "submit_request_previews": [
                request.model_dump(mode="json")
                for request in packet_preview.submit_request_previews
            ],
            "does_not_call_order_lifecycle_submit": True,
            "does_not_change_execution_intent_status": True,
            "does_not_submit_exchange_order": True,
            "does_not_call_exchange": True,
            "does_not_call_owner_bounded_execution": True,
            "does_not_create_withdrawal_or_transfer": True,
        },
    )


def build_runtime_execution_exchange_submit_enablement_decision(
    *,
    packet_preview: RuntimeExecutionExchangeSubmitPacketPreview,
    trusted_submit_fact_snapshot_id: str | None = None,
    submit_idempotency_policy_id: str | None = None,
    attempt_outcome_policy_id: str | None = None,
    protection_creation_failure_policy_id: str | None = None,
    local_registration_enablement_decision_id: str | None = None,
    owner_real_submit_authorization_id: str | None = None,
    order_lifecycle_submit_enablement_id: str | None = None,
    exchange_submit_adapter_enablement_id: str | None = None,
    exchange_submit_action_authorization_id: str | None = None,
    deployment_readiness_evidence_id: str | None = None,
    evidence_validation_blockers: list[str] | None = None,
    evidence_validation_warnings: list[str] | None = None,
    now_ms: int,
) -> RuntimeExecutionExchangeSubmitEnablementDecision:
    gate = build_runtime_execution_exchange_submit_gate(
        packet_preview=packet_preview,
        owner_real_submit_authorized=_present(owner_real_submit_authorization_id),
        trusted_submit_facts_ready=_present(trusted_submit_fact_snapshot_id),
        submit_idempotency_policy_ready=_present(submit_idempotency_policy_id),
        attempt_outcome_policy_ready=_present(attempt_outcome_policy_id),
        protection_failure_policy_ready=_present(
            protection_creation_failure_policy_id
        ),
        local_registration_enablement_ready=_present(
            local_registration_enablement_decision_id
        ),
        order_lifecycle_submit_enabled=_present(
            order_lifecycle_submit_enablement_id
        ),
        exchange_submit_adapter_enabled=_present(
            exchange_submit_adapter_enablement_id
        ),
        exchange_submit_action_authorized=_present(
            exchange_submit_action_authorization_id
        ),
        deployment_readiness_evidence_ready=_present(
            deployment_readiness_evidence_id
        ),
        now_ms=now_ms,
    )

    blockers = list(gate.blockers)
    warnings = list(gate.warnings)
    blockers.extend(evidence_validation_blockers or [])
    warnings.extend(evidence_validation_warnings or [])
    if not _present(trusted_submit_fact_snapshot_id):
        blockers.append("trusted_submit_fact_snapshot_id_missing")
    if not _present(submit_idempotency_policy_id):
        blockers.append("submit_idempotency_policy_id_missing")
    if not _present(attempt_outcome_policy_id):
        blockers.append("attempt_outcome_policy_id_missing")
    if not _present(protection_creation_failure_policy_id):
        blockers.append("protection_creation_failure_policy_id_missing")
    if not _present(local_registration_enablement_decision_id):
        blockers.append("local_registration_enablement_decision_id_missing")
    if not _present(owner_real_submit_authorization_id):
        blockers.append("owner_real_submit_authorization_id_missing")
    if not _present(order_lifecycle_submit_enablement_id):
        blockers.append("order_lifecycle_submit_enablement_id_missing")
    if not _present(exchange_submit_adapter_enablement_id):
        blockers.append("exchange_submit_adapter_enablement_id_missing")
    if not _present(exchange_submit_action_authorization_id):
        blockers.append("exchange_submit_action_authorization_id_missing")
    if not _present(deployment_readiness_evidence_id):
        warnings.append("deployment_readiness_evidence_id_missing")
    if gate.status != RuntimeExecutionExchangeSubmitGateStatus.READY_FOR_EXCHANGE_SUBMIT_ACTION:
        blockers.append("exchange_submit_gate_not_ready")

    status = (
        RuntimeExecutionExchangeSubmitGateStatus.BLOCKED
        if blockers
        else RuntimeExecutionExchangeSubmitGateStatus.READY_FOR_EXCHANGE_SUBMIT_ACTION
    )
    return RuntimeExecutionExchangeSubmitEnablementDecision(
        decision_id=(
            "runtime-exchange-submit-enablement-"
            f"{packet_preview.authorization_id}"
        ),
        authorization_id=packet_preview.authorization_id,
        execution_intent_id=packet_preview.execution_intent_id,
        runtime_instance_id=packet_preview.runtime_instance_id,
        source_type=packet_preview.source_type,
        source_id=packet_preview.source_id,
        semantic_ids=packet_preview.semantic_ids,
        status=status,
        exchange_submit_gate=gate,
        trusted_submit_fact_snapshot_id=_optional_str(
            trusted_submit_fact_snapshot_id
        ),
        submit_idempotency_policy_id=_optional_str(submit_idempotency_policy_id),
        attempt_outcome_policy_id=_optional_str(attempt_outcome_policy_id),
        protection_creation_failure_policy_id=_optional_str(
            protection_creation_failure_policy_id
        ),
        local_registration_enablement_decision_id=_optional_str(
            local_registration_enablement_decision_id
        ),
        owner_real_submit_authorization_id=_optional_str(
            owner_real_submit_authorization_id
        ),
        order_lifecycle_submit_enablement_id=_optional_str(
            order_lifecycle_submit_enablement_id
        ),
        exchange_submit_adapter_enablement_id=_optional_str(
            exchange_submit_adapter_enablement_id
        ),
        exchange_submit_action_authorization_id=_optional_str(
            exchange_submit_action_authorization_id
        ),
        deployment_readiness_evidence_id=_optional_str(
            deployment_readiness_evidence_id
        ),
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_exchange_submit_enablement",
            "first_real_submit_exchange_submit_decision": True,
            "requires_exchange_submit_packet_preview": True,
            "local_order_ids": list(packet_preview.local_order_ids),
            "entry_order_id": packet_preview.entry_order_id,
            "protection_order_ids": list(packet_preview.protection_order_ids),
            "submit_request_previews": [
                request.model_dump(mode="json")
                for request in packet_preview.submit_request_previews
            ],
            "does_not_call_order_lifecycle_submit": True,
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


def _reject_forbidden_execution_fields(
    scope: str,
    value: dict[str, Any],
) -> None:
    forbidden = {
        "client_order_id",
        "exchange_order_id",
        "exchange_payload",
        "order_id",
        "place_order",
        "submit_order",
    }
    for key in _walk_keys(value):
        if key.lower() in forbidden:
            raise ValueError(f"{scope} contains forbidden execution field: {key}")


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
