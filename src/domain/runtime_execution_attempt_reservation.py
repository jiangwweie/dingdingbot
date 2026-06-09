"""Non-mutating runtime attempt/budget reservation preview."""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.execution_intent import ExecutionIntent
from src.domain.runtime_execution_controlled_submit import (
    RuntimeExecutionControlledSubmitPreflight,
    RuntimeExecutionControlledSubmitPreflightStatus,
)
from src.domain.strategy_runtime import (
    StrategyRuntimeInstance,
    StrategyRuntimeInstanceStatus,
)


class RuntimeExecutionAttemptReservationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeExecutionAttemptReservationPreviewStatus(str, Enum):
    BLOCKED = "blocked"
    READY_TO_RESERVE_ATTEMPT = "ready_to_reserve_attempt"


class RuntimeExecutionAttemptReservationStatus(str, Enum):
    BLOCKED = "blocked"
    PENDING_RUNTIME_MUTATION = "pending_runtime_mutation"


class RuntimeExecutionAttemptReservationPreview(RuntimeExecutionAttemptReservationModel):
    reservation_preview_id: str = Field(min_length=1, max_length=260)
    preflight_id: str = Field(min_length=1, max_length=260)
    authorization_id: str = Field(min_length=1, max_length=220)
    execution_intent_id: str = Field(min_length=1, max_length=64)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    source_id: Optional[str] = Field(default=None, max_length=128)
    semantic_ids: BrcSemanticIds
    status: RuntimeExecutionAttemptReservationPreviewStatus
    symbol: str = Field(min_length=1, max_length=128)
    side: Optional[str] = Field(default=None, max_length=32)
    proposed_quantity: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    intended_notional: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    attempts_used_before: int = Field(ge=0)
    attempts_remaining_before: int = Field(ge=0)
    attempts_remaining_after: int = Field(ge=0)
    max_attempts: int = Field(ge=1)
    budget_remaining_before: Optional[Decimal] = None
    budget_remaining_after: Optional[Decimal] = None
    max_notional_per_attempt: Optional[Decimal] = None
    total_budget: Optional[Decimal] = None
    max_active_positions: int = Field(ge=0)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    reservation_recorded: Literal[False] = False
    runtime_budget_mutated: Literal[False] = False
    attempt_consumed: Literal[False] = False
    execution_intent_status_changed: Literal[False] = False
    order_created: Literal[False] = False
    exchange_called: Literal[False] = False
    owner_bounded_execution_called: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    preview_only: Literal[True] = True
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "RuntimeExecutionAttemptReservationPreview":
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
                raise ValueError(f"attempt reservation preview contains forbidden execution field: {key}")
        return self


class RuntimeExecutionAttemptReservation(RuntimeExecutionAttemptReservationModel):
    reservation_id: str = Field(min_length=1, max_length=260)
    reservation_preview_id: str = Field(min_length=1, max_length=260)
    preflight_id: str = Field(min_length=1, max_length=260)
    authorization_id: str = Field(min_length=1, max_length=220)
    execution_intent_id: str = Field(min_length=1, max_length=64)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    source_id: Optional[str] = Field(default=None, max_length=128)
    semantic_ids: BrcSemanticIds
    status: RuntimeExecutionAttemptReservationStatus
    symbol: str = Field(min_length=1, max_length=128)
    side: Optional[str] = Field(default=None, max_length=32)
    proposed_quantity: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    intended_notional: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    attempts_used_before: int = Field(ge=0)
    attempts_remaining_before: int = Field(ge=0)
    attempts_remaining_after: int = Field(ge=0)
    max_attempts: int = Field(ge=1)
    budget_remaining_before: Optional[Decimal] = None
    budget_remaining_after: Optional[Decimal] = None
    max_notional_per_attempt: Optional[Decimal] = None
    total_budget: Optional[Decimal] = None
    max_active_positions: int = Field(ge=0)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    reservation_recorded: Literal[True] = True
    runtime_mutation_pending: Literal[True] = True
    runtime_budget_mutated: Literal[False] = False
    attempt_consumed: Literal[False] = False
    execution_intent_status_changed: Literal[False] = False
    order_created: Literal[False] = False
    exchange_called: Literal[False] = False
    owner_bounded_execution_called: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "RuntimeExecutionAttemptReservation":
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
                raise ValueError(f"attempt reservation contains forbidden execution field: {key}")
        if (
            self.status == RuntimeExecutionAttemptReservationStatus.PENDING_RUNTIME_MUTATION
            and self.blockers
        ):
            raise ValueError("pending runtime mutation reservation cannot have blockers")
        return self


def build_runtime_execution_attempt_reservation(
    *,
    preview: RuntimeExecutionAttemptReservationPreview,
    now_ms: int,
) -> RuntimeExecutionAttemptReservation:
    status = (
        RuntimeExecutionAttemptReservationStatus.PENDING_RUNTIME_MUTATION
        if preview.status == RuntimeExecutionAttemptReservationPreviewStatus.READY_TO_RESERVE_ATTEMPT
        else RuntimeExecutionAttemptReservationStatus.BLOCKED
    )
    return RuntimeExecutionAttemptReservation(
        reservation_id=f"runtime-attempt-reservation-{preview.authorization_id}",
        reservation_preview_id=preview.reservation_preview_id,
        preflight_id=preview.preflight_id,
        authorization_id=preview.authorization_id,
        execution_intent_id=preview.execution_intent_id,
        runtime_instance_id=preview.runtime_instance_id,
        source_id=preview.source_id,
        semantic_ids=preview.semantic_ids,
        status=status,
        symbol=preview.symbol,
        side=preview.side,
        proposed_quantity=preview.proposed_quantity,
        intended_notional=preview.intended_notional,
        attempts_used_before=preview.attempts_used_before,
        attempts_remaining_before=preview.attempts_remaining_before,
        attempts_remaining_after=preview.attempts_remaining_after,
        max_attempts=preview.max_attempts,
        budget_remaining_before=preview.budget_remaining_before,
        budget_remaining_after=preview.budget_remaining_after,
        max_notional_per_attempt=preview.max_notional_per_attempt,
        total_budget=preview.total_budget,
        max_active_positions=preview.max_active_positions,
        blockers=list(preview.blockers),
        warnings=list(preview.warnings),
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_attempt_reservation",
            "pending_runtime_mutation_only": True,
            "derived_from_preview_id": preview.reservation_preview_id,
            "does_not_increment_attempts": True,
            "does_not_mutate_runtime_budget": True,
            "does_not_call_owner_bounded_execution": True,
            "does_not_call_order_lifecycle": True,
            "does_not_call_exchange": True,
        },
    )


def build_runtime_execution_attempt_reservation_preview(
    *,
    preflight: RuntimeExecutionControlledSubmitPreflight,
    intent: ExecutionIntent,
    runtime: StrategyRuntimeInstance,
    now_ms: int,
) -> RuntimeExecutionAttemptReservationPreview:
    blockers = list(preflight.blockers)
    warnings = list(preflight.warnings)
    payload = intent.source_payload or {}
    intended_notional = _optional_decimal(payload.get("intended_notional"))
    proposed_quantity = _optional_decimal(payload.get("proposed_quantity"))

    if preflight.status != RuntimeExecutionControlledSubmitPreflightStatus.READY_FOR_CONTROLLED_SUBMIT_ADAPTER:
        blockers.append("controlled_submit_preflight_not_ready")
    if intent.runtime_instance_id != runtime.runtime_instance_id:
        blockers.append("runtime_instance_mismatch")
    if runtime.status != StrategyRuntimeInstanceStatus.ACTIVE:
        blockers.append("runtime_not_active")
    if runtime.execution_enabled is False:
        warnings.append("runtime_execution_enabled_false_current_shadow_boundary")
    if runtime.shadow_mode is True:
        warnings.append("runtime_shadow_mode_current_boundary")
    if runtime.attempts_remaining <= 0:
        blockers.append("runtime_attempts_exhausted")
    if intended_notional is None:
        blockers.append("intended_notional_missing")
    elif runtime.boundary.max_notional_per_attempt is not None and (
        intended_notional > runtime.boundary.max_notional_per_attempt
    ):
        blockers.append("candidate_exceeds_max_notional_per_attempt")
    if intended_notional is not None and runtime.budget_remaining is not None and (
        intended_notional > runtime.budget_remaining
    ):
        blockers.append("candidate_exceeds_budget_remaining")

    attempts_after = (
        max(runtime.attempts_remaining - 1, 0)
        if runtime.attempts_remaining > 0
        else 0
    )
    budget_after = None
    if runtime.budget_remaining is not None:
        budget_after = runtime.budget_remaining
        if intended_notional is not None:
            budget_after = max(runtime.budget_remaining - intended_notional, Decimal("0"))

    status = (
        RuntimeExecutionAttemptReservationPreviewStatus.BLOCKED
        if blockers
        else RuntimeExecutionAttemptReservationPreviewStatus.READY_TO_RESERVE_ATTEMPT
    )
    return RuntimeExecutionAttemptReservationPreview(
        reservation_preview_id=f"runtime-attempt-reservation-preview-{preflight.authorization_id}",
        preflight_id=preflight.preflight_id,
        authorization_id=preflight.authorization_id,
        execution_intent_id=preflight.execution_intent_id,
        runtime_instance_id=runtime.runtime_instance_id,
        source_id=intent.source_id,
        semantic_ids=intent.semantic_ids,
        status=status,
        symbol=runtime.symbol,
        side=_optional_str(payload.get("side")),
        proposed_quantity=proposed_quantity,
        intended_notional=intended_notional,
        attempts_used_before=runtime.boundary.attempts_used,
        attempts_remaining_before=runtime.attempts_remaining,
        attempts_remaining_after=attempts_after,
        max_attempts=runtime.boundary.max_attempts,
        budget_remaining_before=runtime.budget_remaining,
        budget_remaining_after=budget_after,
        max_notional_per_attempt=runtime.boundary.max_notional_per_attempt,
        total_budget=runtime.boundary.total_budget,
        max_active_positions=runtime.boundary.max_active_positions,
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_attempt_reservation_preview",
            "non_mutating_budget_gate": True,
            "does_not_increment_attempts": True,
            "does_not_mutate_runtime_budget": True,
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
