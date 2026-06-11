"""Runtime exchange-submit execution result.

This is the first explicit result model for a future real exchange-submit
adapter. It is separate from the non-executing exchange-submit adapter replay
shell so that preview/lock evidence can keep its no-exchange invariants.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.runtime_execution_exchange_submit_enablement import (
    RuntimeExecutionExchangeSubmitEnablementDecision,
    RuntimeExecutionExchangeSubmitGateStatus,
)
from src.domain.runtime_execution_exchange_submit_packet import (
    RuntimeExecutionExchangeSubmitPacketPreview,
)


class RuntimeExecutionExchangeSubmitExecutionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeExecutionExchangeSubmitExecutionStatus(str, Enum):
    BLOCKED = "blocked"
    EXCHANGE_SUBMIT_EXECUTION_DISABLED = "exchange_submit_execution_disabled"
    EXCHANGE_SUBMIT_EXECUTION_LOCK_ACQUIRED = (
        "exchange_submit_execution_lock_acquired"
    )
    ENTRY_SUBMIT_FAILED = "entry_submit_failed"
    PROTECTION_SUBMIT_FAILED = "protection_submit_failed"
    EXCHANGE_SUBMIT_ORDERS_SUBMITTED = "exchange_submit_orders_submitted"


class RuntimeExecutionSubmittedExchangeOrder(
    RuntimeExecutionExchangeSubmitExecutionModel
):
    local_order_id: str = Field(min_length=1, max_length=260)
    order_role: str = Field(min_length=1, max_length=32)
    exchange_order_id: Optional[str] = Field(default=None, max_length=260)
    exchange_status: Optional[str] = Field(default=None, max_length=64)
    amount: Optional[str] = Field(default=None, max_length=96)
    filled_qty: Optional[str] = Field(default=None, max_length=96)
    average_exec_price: Optional[str] = Field(default=None, max_length=96)
    reduce_only: bool
    order_lifecycle_submit_called: bool


class RuntimeExecutionExchangeSubmitExecutionResult(
    RuntimeExecutionExchangeSubmitExecutionModel
):
    execution_result_id: str = Field(min_length=1, max_length=540)
    enablement_decision_id: str = Field(min_length=1, max_length=500)
    packet_preview_id: str = Field(min_length=1, max_length=460)
    binding_id: str = Field(min_length=1, max_length=460)
    authorization_id: str = Field(min_length=1, max_length=220)
    execution_intent_id: str = Field(min_length=1, max_length=64)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    source_type: Optional[str] = Field(default=None, max_length=64)
    source_id: Optional[str] = Field(default=None, max_length=128)
    semantic_ids: BrcSemanticIds
    status: RuntimeExecutionExchangeSubmitExecutionStatus
    symbol: str = Field(min_length=1, max_length=128)
    exchange_submit_action_authorization_id: Optional[str] = Field(
        default=None,
        max_length=360,
    )
    local_order_ids: list[str] = Field(default_factory=list)
    entry_order_id: Optional[str] = Field(default=None, max_length=260)
    protection_order_ids: list[str] = Field(default_factory=list)
    submitted_orders: list[RuntimeExecutionSubmittedExchangeOrder] = Field(
        default_factory=list,
    )
    submitted_local_order_ids: list[str] = Field(default_factory=list)
    submitted_exchange_order_ids: list[str] = Field(default_factory=list)
    entry_exchange_order_id: Optional[str] = Field(default=None, max_length=260)
    protection_exchange_order_ids: list[str] = Field(default_factory=list)
    failed_local_order_id: Optional[str] = Field(default=None, max_length=260)
    failed_order_role: Optional[str] = Field(default=None, max_length=32)
    failed_reason: Optional[str] = Field(default=None, max_length=500)
    exchange_submit_execution_enabled: bool = False
    exchange_call_count: int = Field(ge=0)
    order_lifecycle_submit_call_count: int = Field(ge=0)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    real_exchange_submit_adapter_executed: bool = False
    exchange_order_submitted: bool = False
    exchange_called: bool = False
    order_lifecycle_submit_called: bool = False
    execution_intent_status_changed: Literal[False] = False
    owner_bounded_execution_called: Literal[False] = False
    withdrawal_or_transfer_created: Literal[False] = False
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_result(self) -> "RuntimeExecutionExchangeSubmitExecutionResult":
        _reject_forbidden_metadata_fields(
            "exchange submit execution result",
            {"metadata": self.metadata},
        )
        if self.status in {
            RuntimeExecutionExchangeSubmitExecutionStatus.BLOCKED,
            RuntimeExecutionExchangeSubmitExecutionStatus
            .EXCHANGE_SUBMIT_EXECUTION_DISABLED,
            RuntimeExecutionExchangeSubmitExecutionStatus
            .EXCHANGE_SUBMIT_EXECUTION_LOCK_ACQUIRED,
        }:
            if self.exchange_called or self.exchange_order_submitted:
                raise ValueError(
                    "blocked/disabled/lock exchange submit cannot call exchange"
                )
            if self.order_lifecycle_submit_called:
                raise ValueError(
                    "blocked/disabled/lock exchange submit cannot call "
                    "OrderLifecycle.submit_order"
                )
            if self.real_exchange_submit_adapter_executed:
                raise ValueError(
                    "blocked/disabled/lock exchange submit cannot execute adapter"
                )
        if self.status == (
            RuntimeExecutionExchangeSubmitExecutionStatus
            .EXCHANGE_SUBMIT_EXECUTION_LOCK_ACQUIRED
        ):
            if not self.exchange_submit_execution_enabled:
                raise ValueError("lock result requires execution enabled")
            if self.exchange_call_count != 0:
                raise ValueError("lock result cannot record exchange calls")
        if self.status == (
            RuntimeExecutionExchangeSubmitExecutionStatus
            .EXCHANGE_SUBMIT_ORDERS_SUBMITTED
        ):
            if self.blockers:
                raise ValueError("submitted exchange result cannot have blockers")
            if not self.exchange_submit_execution_enabled:
                raise ValueError("submitted exchange result requires execution enabled")
            if not self.real_exchange_submit_adapter_executed:
                raise ValueError("submitted exchange result requires adapter executed")
            if not self.exchange_called or not self.exchange_order_submitted:
                raise ValueError("submitted exchange result requires exchange submit")
            if not self.order_lifecycle_submit_called:
                raise ValueError(
                    "submitted exchange result requires OrderLifecycle.submit_order"
                )
            if not self.entry_exchange_order_id:
                raise ValueError("submitted exchange result requires entry exchange id")
            if len(self.protection_exchange_order_ids) != len(
                self.protection_order_ids
            ):
                raise ValueError(
                    "submitted exchange result requires all protection exchange ids"
                )
        if self.status == (
            RuntimeExecutionExchangeSubmitExecutionStatus.ENTRY_SUBMIT_FAILED
        ):
            if self.submitted_orders:
                raise ValueError("entry submit failure cannot have submitted orders")
            if self.order_lifecycle_submit_called:
                raise ValueError(
                    "entry submit failure cannot call OrderLifecycle.submit_order"
                )
        if self.status == (
            RuntimeExecutionExchangeSubmitExecutionStatus.PROTECTION_SUBMIT_FAILED
        ):
            if not self.entry_exchange_order_id:
                raise ValueError(
                    "protection submit failure requires submitted entry evidence"
                )
            if not self.order_lifecycle_submit_called:
                raise ValueError(
                    "protection submit failure requires entry lifecycle submit"
                )
        if self.execution_intent_status_changed:
            raise ValueError("exchange submit execution cannot change intent status")
        if self.owner_bounded_execution_called:
            raise ValueError("exchange submit execution cannot call OwnerBoundedExecution")
        if self.withdrawal_or_transfer_created:
            raise ValueError("exchange submit execution cannot create withdrawal/transfer")
        if self.exchange_call_count < len(self.submitted_orders):
            raise ValueError("exchange_call_count cannot be smaller than submissions")
        if self.order_lifecycle_submit_call_count != len(
            [
                order for order in self.submitted_orders
                if order.order_lifecycle_submit_called
            ]
        ):
            raise ValueError("order_lifecycle_submit_call_count mismatch")
        return self


def build_runtime_exchange_submit_execution_disabled_result(
    *,
    enablement_decision: RuntimeExecutionExchangeSubmitEnablementDecision,
    packet_preview: RuntimeExecutionExchangeSubmitPacketPreview,
    now_ms: int,
    additional_blockers: list[str] | None = None,
    additional_warnings: list[str] | None = None,
) -> RuntimeExecutionExchangeSubmitExecutionResult:
    warnings = list(enablement_decision.warnings)
    warnings.extend(additional_warnings or [])
    warnings.append("exchange_submit_execution_disabled")
    return _execution_result(
        enablement_decision=enablement_decision,
        packet_preview=packet_preview,
        status=(
            RuntimeExecutionExchangeSubmitExecutionStatus
            .EXCHANGE_SUBMIT_EXECUTION_DISABLED
        ),
        submitted_orders=[],
        failed_local_order_id=None,
        failed_order_role=None,
        failed_reason=None,
        exchange_submit_execution_enabled=False,
        exchange_call_count=0,
        now_ms=now_ms,
        blockers=list(enablement_decision.blockers) + list(additional_blockers or []),
        warnings=warnings,
        real_exchange_submit_adapter_executed=False,
    )


def build_runtime_exchange_submit_execution_blocked_result(
    *,
    enablement_decision: RuntimeExecutionExchangeSubmitEnablementDecision,
    packet_preview: RuntimeExecutionExchangeSubmitPacketPreview,
    blockers: list[str],
    warnings: list[str],
    now_ms: int,
    exchange_submit_execution_enabled: bool = False,
) -> RuntimeExecutionExchangeSubmitExecutionResult:
    return _execution_result(
        enablement_decision=enablement_decision,
        packet_preview=packet_preview,
        status=RuntimeExecutionExchangeSubmitExecutionStatus.BLOCKED,
        submitted_orders=[],
        failed_local_order_id=None,
        failed_order_role=None,
        failed_reason=None,
        exchange_submit_execution_enabled=exchange_submit_execution_enabled,
        exchange_call_count=0,
        now_ms=now_ms,
        blockers=blockers,
        warnings=warnings,
        real_exchange_submit_adapter_executed=False,
    )


def build_runtime_exchange_submit_execution_lock_result(
    *,
    enablement_decision: RuntimeExecutionExchangeSubmitEnablementDecision,
    packet_preview: RuntimeExecutionExchangeSubmitPacketPreview,
    now_ms: int,
) -> RuntimeExecutionExchangeSubmitExecutionResult:
    warnings = list(enablement_decision.warnings)
    warnings.append("exchange_submit_execution_lock_acquired")
    return _execution_result(
        enablement_decision=enablement_decision,
        packet_preview=packet_preview,
        status=(
            RuntimeExecutionExchangeSubmitExecutionStatus
            .EXCHANGE_SUBMIT_EXECUTION_LOCK_ACQUIRED
        ),
        submitted_orders=[],
        failed_local_order_id=None,
        failed_order_role=None,
        failed_reason=None,
        exchange_submit_execution_enabled=True,
        exchange_call_count=0,
        now_ms=now_ms,
        blockers=[],
        warnings=warnings,
        real_exchange_submit_adapter_executed=False,
    )


def build_runtime_exchange_submit_execution_submitted_result(
    *,
    enablement_decision: RuntimeExecutionExchangeSubmitEnablementDecision,
    packet_preview: RuntimeExecutionExchangeSubmitPacketPreview,
    submitted_orders: list[RuntimeExecutionSubmittedExchangeOrder],
    exchange_call_count: int,
    now_ms: int,
    warnings: list[str] | None = None,
) -> RuntimeExecutionExchangeSubmitExecutionResult:
    return _execution_result(
        enablement_decision=enablement_decision,
        packet_preview=packet_preview,
        status=(
            RuntimeExecutionExchangeSubmitExecutionStatus
            .EXCHANGE_SUBMIT_ORDERS_SUBMITTED
        ),
        submitted_orders=submitted_orders,
        failed_local_order_id=None,
        failed_order_role=None,
        failed_reason=None,
        exchange_submit_execution_enabled=True,
        exchange_call_count=exchange_call_count,
        now_ms=now_ms,
        blockers=[],
        warnings=list(warnings or []),
        real_exchange_submit_adapter_executed=True,
    )


def build_runtime_exchange_submit_execution_failed_result(
    *,
    enablement_decision: RuntimeExecutionExchangeSubmitEnablementDecision,
    packet_preview: RuntimeExecutionExchangeSubmitPacketPreview,
    submitted_orders: list[RuntimeExecutionSubmittedExchangeOrder],
    failed_local_order_id: str,
    failed_order_role: str,
    failed_reason: str,
    exchange_call_count: int,
    now_ms: int,
    warnings: list[str] | None = None,
) -> RuntimeExecutionExchangeSubmitExecutionResult:
    status = (
        RuntimeExecutionExchangeSubmitExecutionStatus.ENTRY_SUBMIT_FAILED
        if failed_order_role == "ENTRY"
        else RuntimeExecutionExchangeSubmitExecutionStatus.PROTECTION_SUBMIT_FAILED
    )
    blockers = [
        "entry_submit_failed"
        if status == RuntimeExecutionExchangeSubmitExecutionStatus.ENTRY_SUBMIT_FAILED
        else "protection_submit_failed_after_entry_submit"
    ]
    return _execution_result(
        enablement_decision=enablement_decision,
        packet_preview=packet_preview,
        status=status,
        submitted_orders=submitted_orders,
        failed_local_order_id=failed_local_order_id,
        failed_order_role=failed_order_role,
        failed_reason=failed_reason,
        exchange_submit_execution_enabled=True,
        exchange_call_count=exchange_call_count,
        now_ms=now_ms,
        blockers=blockers,
        warnings=list(warnings or []),
        real_exchange_submit_adapter_executed=True,
    )


def _execution_result(
    *,
    enablement_decision: RuntimeExecutionExchangeSubmitEnablementDecision,
    packet_preview: RuntimeExecutionExchangeSubmitPacketPreview,
    status: RuntimeExecutionExchangeSubmitExecutionStatus,
    submitted_orders: list[RuntimeExecutionSubmittedExchangeOrder],
    failed_local_order_id: str | None,
    failed_order_role: str | None,
    failed_reason: str | None,
    exchange_submit_execution_enabled: bool,
    exchange_call_count: int,
    now_ms: int,
    blockers: list[str],
    warnings: list[str],
    real_exchange_submit_adapter_executed: bool,
) -> RuntimeExecutionExchangeSubmitExecutionResult:
    submitted_exchange_ids = [
        order.exchange_order_id
        for order in submitted_orders
        if order.exchange_order_id
    ]
    entry_exchange_id = next(
        (
            order.exchange_order_id
            for order in submitted_orders
            if order.order_role == "ENTRY" and order.exchange_order_id
        ),
        None,
    )
    protection_exchange_ids = [
        order.exchange_order_id
        for order in submitted_orders
        if order.order_role != "ENTRY" and order.exchange_order_id
    ]
    entry_submit_failed = (
        status == RuntimeExecutionExchangeSubmitExecutionStatus.ENTRY_SUBMIT_FAILED
    )
    protection_submit_failed = (
        status == RuntimeExecutionExchangeSubmitExecutionStatus.PROTECTION_SUBMIT_FAILED
    )
    lifecycle_submit_count = sum(
        1 for order in submitted_orders if order.order_lifecycle_submit_called
    )
    exchange_submitted = bool(submitted_orders)
    return RuntimeExecutionExchangeSubmitExecutionResult(
        execution_result_id=(
            "runtime-exchange-submit-execution-result-"
            f"{enablement_decision.authorization_id}"
        ),
        enablement_decision_id=enablement_decision.decision_id,
        packet_preview_id=packet_preview.packet_preview_id,
        binding_id=packet_preview.binding_id,
        authorization_id=enablement_decision.authorization_id,
        execution_intent_id=enablement_decision.execution_intent_id,
        runtime_instance_id=enablement_decision.runtime_instance_id,
        source_type=enablement_decision.source_type,
        source_id=enablement_decision.source_id,
        semantic_ids=enablement_decision.semantic_ids,
        status=status,
        symbol=packet_preview.symbol,
        exchange_submit_action_authorization_id=(
            enablement_decision.exchange_submit_action_authorization_id
        ),
        local_order_ids=list(packet_preview.local_order_ids),
        entry_order_id=packet_preview.entry_order_id,
        protection_order_ids=list(packet_preview.protection_order_ids),
        submitted_orders=submitted_orders,
        submitted_local_order_ids=[order.local_order_id for order in submitted_orders],
        submitted_exchange_order_ids=submitted_exchange_ids,
        entry_exchange_order_id=entry_exchange_id,
        protection_exchange_order_ids=protection_exchange_ids,
        failed_local_order_id=failed_local_order_id,
        failed_order_role=failed_order_role,
        failed_reason=failed_reason,
        exchange_submit_execution_enabled=exchange_submit_execution_enabled,
        exchange_call_count=exchange_call_count,
        order_lifecycle_submit_call_count=lifecycle_submit_count,
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        real_exchange_submit_adapter_executed=real_exchange_submit_adapter_executed,
        exchange_order_submitted=exchange_submitted,
        exchange_called=exchange_call_count > 0,
        order_lifecycle_submit_called=lifecycle_submit_count > 0,
        execution_intent_status_changed=False,
        owner_bounded_execution_called=False,
        withdrawal_or_transfer_created=False,
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_exchange_submit_execution_result",
            "enablement_decision_id": enablement_decision.decision_id,
            "packet_preview_id": packet_preview.packet_preview_id,
            "exchange_submit_action_authorization_id": (
                enablement_decision.exchange_submit_action_authorization_id
            ),
            "does_not_change_execution_intent_status": True,
            "does_not_call_owner_bounded_execution": True,
            "does_not_create_withdrawal_or_transfer": True,
            "entry_submit_failed_before_exchange_acceptance": entry_submit_failed,
            "entry_submit_failure_does_not_create_recovery_task": (
                entry_submit_failed
            ),
            "protection_submit_failed_after_entry_submit": protection_submit_failed,
            "protection_failure_requires_recovery_task": protection_submit_failed,
        },
    )


def submitted_exchange_order_from_placement(
    *,
    local_order_id: str,
    order_role: str,
    reduce_only: bool,
    placement_result: Any,
    order_lifecycle_submit_called: bool,
) -> RuntimeExecutionSubmittedExchangeOrder:
    return RuntimeExecutionSubmittedExchangeOrder(
        local_order_id=local_order_id,
        order_role=order_role,
        exchange_order_id=_optional_str(
            getattr(placement_result, "exchange_order_id", None)
        ),
        exchange_status=_optional_str(getattr(placement_result, "status", None)),
        amount=_optional_str(getattr(placement_result, "amount", None)),
        filled_qty=_optional_str(getattr(placement_result, "filled_qty", None)),
        average_exec_price=_optional_str(
            getattr(placement_result, "average_exec_price", None)
        ),
        reduce_only=reduce_only,
        order_lifecycle_submit_called=order_lifecycle_submit_called,
    )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(getattr(value, "value", value)).strip()
    return text or None


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _reject_forbidden_metadata_fields(scope: str, value: dict[str, Any]) -> None:
    forbidden = {
        "api_key",
        "api_secret",
        "secret",
        "credential",
        "withdrawal_payload",
        "transfer_payload",
    }
    for key in _walk_keys(value):
        if key.lower() in forbidden:
            raise ValueError(f"{scope} contains forbidden sensitive field: {key}")


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
