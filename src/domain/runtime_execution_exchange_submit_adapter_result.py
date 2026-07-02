"""Runtime exchange-submit adapter result shell.

This is the durable replay boundary immediately before the execution-result
stage. It can acquire a persistent duplicate-submit lock and freeze the
action-scoped exchange-submit request previews. It must not call
OrderLifecycle.submit_order, ExchangeGateway, OwnerBoundedExecution,
withdrawals, or transfers.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.runtime_execution_exchange_submit_enablement import (
    RuntimeExecutionExchangeSubmitEnablementDecision,
    RuntimeExecutionExchangeSubmitGateStatus,
)


class RuntimeExecutionExchangeSubmitAdapterResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeExecutionExchangeSubmitAdapterResultStatus(str, Enum):
    BLOCKED = "blocked"
    EXCHANGE_SUBMIT_ADAPTER_DISABLED = "exchange_submit_adapter_disabled"
    EXCHANGE_SUBMIT_LOCK_REQUIRED = "exchange_submit_lock_required"
    EXCHANGE_SUBMIT_LOCK_ACQUIRED = "exchange_submit_lock_acquired"
    EXCHANGE_SUBMIT_ADAPTER_ARMED = "exchange_submit_adapter_armed"
    EXCHANGE_SUBMIT_ADAPTER_NOT_IMPLEMENTED = (
        "exchange_submit_adapter_not_implemented"
    )


class RuntimeExecutionExchangeSubmitAdapterResult(
    RuntimeExecutionExchangeSubmitAdapterResultModel
):
    adapter_result_id: str = Field(min_length=1, max_length=520)
    enablement_decision_id: str = Field(min_length=1, max_length=500)
    gate_id: str = Field(min_length=1, max_length=460)
    submit_preview_id: str = Field(min_length=1, max_length=460)
    binding_id: str = Field(min_length=1, max_length=460)
    local_registration_adapter_result_id: str = Field(min_length=1, max_length=420)
    authorization_id: str = Field(min_length=1, max_length=220)
    execution_intent_id: str = Field(min_length=1, max_length=64)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    source_type: Optional[str] = Field(default=None, max_length=64)
    source_id: Optional[str] = Field(default=None, max_length=128)
    semantic_ids: BrcSemanticIds
    status: RuntimeExecutionExchangeSubmitAdapterResultStatus
    symbol: str = Field(min_length=1, max_length=128)
    local_order_ids: list[str] = Field(default_factory=list)
    entry_order_id: Optional[str] = Field(default=None, max_length=260)
    protection_order_ids: list[str] = Field(default_factory=list)
    submit_request_previews: list[dict[str, Any]] = Field(default_factory=list)
    submit_request_count: int = Field(ge=0)
    entry_submit_request_count: int = Field(ge=0)
    protection_submit_request_count: int = Field(ge=0)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    order_lifecycle_submit_enabled: bool = False
    exchange_submit_adapter_enabled: bool = False
    exchange_submit_action_authorized: bool = False
    exchange_submit_action_authorization_id: Optional[str] = Field(
        default=None,
        max_length=360,
    )
    duplicate_submit_lock_acquired: bool = False
    exchange_submit_adapter_implemented: bool = False
    order_lifecycle_submit_called: bool = False
    execution_intent_status_changed: bool = False
    exchange_order_submitted: bool = False
    exchange_called: bool = False
    owner_bounded_execution_called: bool = False
    withdrawal_or_transfer_created: bool = False
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_result(self) -> "RuntimeExecutionExchangeSubmitAdapterResult":
        _reject_forbidden_execution_fields(
            "exchange submit adapter result",
            {
                "metadata": self.metadata,
                "submit_request_previews": self.submit_request_previews,
            },
        )
        if self.exchange_called or self.exchange_order_submitted:
            raise ValueError("exchange submit adapter result cannot call exchange")
        if self.order_lifecycle_submit_called:
            raise ValueError(
                "exchange submit adapter result cannot call OrderLifecycle.submit_order"
            )
        if self.execution_intent_status_changed:
            raise ValueError("exchange submit adapter result cannot mutate intent status")
        if self.owner_bounded_execution_called:
            raise ValueError(
                "exchange submit adapter result cannot call OwnerBoundedExecution"
            )
        if self.withdrawal_or_transfer_created:
            raise ValueError(
                "exchange submit adapter result cannot create withdrawal/transfer"
            )
        if self.exchange_submit_adapter_implemented:
            raise ValueError("exchange submit adapter result cannot execute adapter")
        if (
            self.status
            == RuntimeExecutionExchangeSubmitAdapterResultStatus
            .EXCHANGE_SUBMIT_LOCK_ACQUIRED
            and not self.duplicate_submit_lock_acquired
        ):
            raise ValueError("lock-acquired result requires duplicate-submit lock")
        if (
            self.status
            == RuntimeExecutionExchangeSubmitAdapterResultStatus
            .EXCHANGE_SUBMIT_ADAPTER_ARMED
        ):
            if not self.duplicate_submit_lock_acquired:
                raise ValueError("armed result requires duplicate-submit lock")
            if not self.exchange_submit_adapter_enabled:
                raise ValueError("armed result requires adapter enablement")
            if not self.order_lifecycle_submit_enabled:
                raise ValueError("armed result requires lifecycle submit enablement")
            if not self.exchange_submit_action_authorized:
                raise ValueError("armed result requires action authorization")
            if not self.exchange_submit_action_authorization_id:
                raise ValueError(
                    "armed result requires action authorization id"
                )
            if self.blockers:
                raise ValueError("armed result cannot have blockers")
        if self.submit_request_count != len(self.submit_request_previews):
            raise ValueError("submit_request_count mismatch")
        return self


def build_runtime_execution_exchange_submit_adapter_result(
    *,
    enablement_decision: RuntimeExecutionExchangeSubmitEnablementDecision,
    now_ms: int,
    exchange_submit_adapter_enabled: bool = False,
    duplicate_submit_lock_acquired: bool = False,
    additional_blockers: list[str] | None = None,
    additional_warnings: list[str] | None = None,
) -> RuntimeExecutionExchangeSubmitAdapterResult:
    blockers = (
        list(enablement_decision.blockers)
        + list(additional_blockers or [])
    )
    warnings = (
        list(enablement_decision.warnings)
        + list(additional_warnings or [])
    )
    gate = enablement_decision.exchange_submit_gate
    if enablement_decision.status != (
        RuntimeExecutionExchangeSubmitGateStatus.READY_FOR_EXCHANGE_SUBMIT_ACTION
    ):
        blockers.append("exchange_submit_enablement_decision_not_ready")
    if not exchange_submit_adapter_enabled:
        blockers.append("exchange_submit_adapter_disabled")
    if exchange_submit_adapter_enabled and not duplicate_submit_lock_acquired:
        blockers.append("persistent_duplicate_submit_lock_required")

    status = RuntimeExecutionExchangeSubmitAdapterResultStatus.BLOCKED
    if blockers:
        if "exchange_submit_adapter_not_implemented" in blockers:
            status = (
                RuntimeExecutionExchangeSubmitAdapterResultStatus
                .EXCHANGE_SUBMIT_ADAPTER_NOT_IMPLEMENTED
            )
        elif "exchange_submit_adapter_disabled" in blockers:
            status = (
                RuntimeExecutionExchangeSubmitAdapterResultStatus
                .EXCHANGE_SUBMIT_ADAPTER_DISABLED
            )
        elif blockers == ["persistent_duplicate_submit_lock_required"]:
            status = (
                RuntimeExecutionExchangeSubmitAdapterResultStatus
                .EXCHANGE_SUBMIT_LOCK_REQUIRED
            )
    else:
        status = (
            RuntimeExecutionExchangeSubmitAdapterResultStatus
            .EXCHANGE_SUBMIT_ADAPTER_ARMED
        )

    request_previews = _request_previews_from_decision(enablement_decision)
    return RuntimeExecutionExchangeSubmitAdapterResult(
        adapter_result_id=(
            "runtime-exchange-submit-adapter-result-"
            f"{enablement_decision.authorization_id}"
        ),
        enablement_decision_id=enablement_decision.decision_id,
        gate_id=gate.gate_id,
        submit_preview_id=gate.submit_preview_id,
        binding_id=gate.binding_id,
        local_registration_adapter_result_id=gate.adapter_result_id,
        authorization_id=enablement_decision.authorization_id,
        execution_intent_id=enablement_decision.execution_intent_id,
        runtime_instance_id=enablement_decision.runtime_instance_id,
        source_type=enablement_decision.source_type,
        source_id=enablement_decision.source_id,
        semantic_ids=enablement_decision.semantic_ids,
        status=status,
        symbol=gate.symbol,
        local_order_ids=_metadata_list(enablement_decision, "local_order_ids"),
        entry_order_id=_metadata_str(enablement_decision, "entry_order_id"),
        protection_order_ids=_metadata_list(
            enablement_decision,
            "protection_order_ids",
        ),
        submit_request_previews=request_previews,
        submit_request_count=len(request_previews),
        entry_submit_request_count=_request_count(request_previews, "ENTRY"),
        protection_submit_request_count=(
            len(request_previews) - _request_count(request_previews, "ENTRY")
        ),
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        order_lifecycle_submit_enabled=bool(
            gate.order_lifecycle_submit_enabled
        ),
        exchange_submit_adapter_enabled=exchange_submit_adapter_enabled,
        exchange_submit_action_authorized=bool(
            gate.exchange_submit_action_authorized
        ),
        exchange_submit_action_authorization_id=(
            enablement_decision.exchange_submit_action_authorization_id
        ),
        duplicate_submit_lock_acquired=duplicate_submit_lock_acquired,
        exchange_submit_adapter_implemented=False,
        order_lifecycle_submit_called=False,
        execution_intent_status_changed=False,
        exchange_order_submitted=False,
        exchange_called=False,
        owner_bounded_execution_called=False,
        withdrawal_or_transfer_created=False,
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_exchange_submit_adapter_result",
            "persistent_duplicate_submit_lock": duplicate_submit_lock_acquired,
            "exchange_submit_adapter_enabled": exchange_submit_adapter_enabled,
            "exchange_submit_adapter_armed": (
                status
                == (
                    RuntimeExecutionExchangeSubmitAdapterResultStatus
                    .EXCHANGE_SUBMIT_ADAPTER_ARMED
                )
            ),
            "exchange_submit_action_authorization_id": (
                enablement_decision.exchange_submit_action_authorization_id
            ),
            "real_exchange_submit_adapter_executed": False,
            "local_registration_adapter_result_id": gate.adapter_result_id,
            "enablement_decision_id": enablement_decision.decision_id,
            "does_not_call_order_lifecycle_submit": True,
            "does_not_change_execution_intent_status": True,
            "does_not_submit_exchange_order": True,
            "does_not_call_exchange": True,
            "does_not_call_owner_bounded_execution": True,
            "does_not_create_withdrawal_or_transfer": True,
        },
    )


def build_runtime_execution_exchange_submit_adapter_lock_result(
    *,
    enablement_decision: RuntimeExecutionExchangeSubmitEnablementDecision,
    now_ms: int,
) -> RuntimeExecutionExchangeSubmitAdapterResult:
    if enablement_decision.status != (
        RuntimeExecutionExchangeSubmitGateStatus.READY_FOR_EXCHANGE_SUBMIT_ACTION
    ):
        raise ValueError("exchange_submit_enablement_decision_not_ready")
    if enablement_decision.blockers:
        raise ValueError("exchange_submit_enablement_decision_has_blockers")
    gate = enablement_decision.exchange_submit_gate
    request_previews = _request_previews_from_decision(enablement_decision)
    return RuntimeExecutionExchangeSubmitAdapterResult(
        adapter_result_id=(
            "runtime-exchange-submit-adapter-result-"
            f"{enablement_decision.authorization_id}"
        ),
        enablement_decision_id=enablement_decision.decision_id,
        gate_id=gate.gate_id,
        submit_preview_id=gate.submit_preview_id,
        binding_id=gate.binding_id,
        local_registration_adapter_result_id=gate.adapter_result_id,
        authorization_id=enablement_decision.authorization_id,
        execution_intent_id=enablement_decision.execution_intent_id,
        runtime_instance_id=enablement_decision.runtime_instance_id,
        source_type=enablement_decision.source_type,
        source_id=enablement_decision.source_id,
        semantic_ids=enablement_decision.semantic_ids,
        status=(
            RuntimeExecutionExchangeSubmitAdapterResultStatus
            .EXCHANGE_SUBMIT_LOCK_ACQUIRED
        ),
        symbol=gate.symbol,
        local_order_ids=_metadata_list(enablement_decision, "local_order_ids"),
        entry_order_id=_metadata_str(enablement_decision, "entry_order_id"),
        protection_order_ids=_metadata_list(
            enablement_decision,
            "protection_order_ids",
        ),
        submit_request_previews=request_previews,
        submit_request_count=len(request_previews),
        entry_submit_request_count=_request_count(request_previews, "ENTRY"),
        protection_submit_request_count=(
            len(request_previews) - _request_count(request_previews, "ENTRY")
        ),
        blockers=[],
        warnings=list(enablement_decision.warnings),
        order_lifecycle_submit_enabled=True,
        exchange_submit_adapter_enabled=True,
        exchange_submit_action_authorized=True,
        exchange_submit_action_authorization_id=(
            enablement_decision.exchange_submit_action_authorization_id
        ),
        duplicate_submit_lock_acquired=True,
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_exchange_submit_adapter_result",
            "persistent_duplicate_submit_lock": True,
            "exchange_submit_pending": True,
            "exchange_submit_action_authorization_id": (
                enablement_decision.exchange_submit_action_authorization_id
            ),
            "enablement_decision_id": enablement_decision.decision_id,
            "does_not_call_order_lifecycle_submit": True,
            "does_not_change_execution_intent_status": True,
            "does_not_submit_exchange_order": True,
            "does_not_call_exchange": True,
            "does_not_call_owner_bounded_execution": True,
            "does_not_create_withdrawal_or_transfer": True,
        },
    )


def _request_previews_from_decision(
    enablement_decision: RuntimeExecutionExchangeSubmitEnablementDecision,
) -> list[dict[str, Any]]:
    requests = enablement_decision.metadata.get("submit_request_previews")
    if isinstance(requests, list):
        return [dict(item) for item in requests if isinstance(item, dict)]
    gate_requests = enablement_decision.exchange_submit_gate.metadata.get(
        "submit_request_previews"
    )
    if isinstance(gate_requests, list):
        return [dict(item) for item in gate_requests if isinstance(item, dict)]
    return []


def _metadata_list(
    enablement_decision: RuntimeExecutionExchangeSubmitEnablementDecision,
    key: str,
) -> list[str]:
    value = enablement_decision.metadata.get(key)
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def _metadata_str(
    enablement_decision: RuntimeExecutionExchangeSubmitEnablementDecision,
    key: str,
) -> Optional[str]:
    value = enablement_decision.metadata.get(key)
    if value is None:
        return None
    text = str(value)
    return text or None


def _request_count(requests: list[dict[str, Any]], role: str) -> int:
    return sum(1 for request in requests if str(request.get("order_role")) == role)


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
