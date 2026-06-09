"""Runtime attempt/budget mutation derived from a pending reservation."""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.runtime_execution_attempt_reservation import (
    RuntimeExecutionAttemptReservation,
    RuntimeExecutionAttemptReservationStatus,
)
from src.domain.strategy_runtime import (
    StrategyRuntimeBoundary,
    StrategyRuntimeInstance,
    StrategyRuntimeInstanceStatus,
)


class RuntimeExecutionAttemptMutationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeExecutionAttemptMutationStatus(str, Enum):
    BLOCKED = "blocked"
    APPLIED = "applied"


class RuntimeExecutionAttemptMutation(RuntimeExecutionAttemptMutationModel):
    mutation_id: str = Field(min_length=1, max_length=320)
    reservation_id: str = Field(min_length=1, max_length=260)
    reservation_preview_id: str = Field(min_length=1, max_length=260)
    authorization_id: str = Field(min_length=1, max_length=220)
    execution_intent_id: str = Field(min_length=1, max_length=64)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    source_id: Optional[str] = Field(default=None, max_length=128)
    semantic_ids: BrcSemanticIds
    status: RuntimeExecutionAttemptMutationStatus
    runtime_status_before: StrategyRuntimeInstanceStatus
    runtime_status_after: StrategyRuntimeInstanceStatus
    symbol: str = Field(min_length=1, max_length=128)
    side: Optional[str] = Field(default=None, max_length=32)
    proposed_quantity: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    intended_notional: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    attempts_used_before: int = Field(ge=0)
    attempts_used_after: int = Field(ge=0)
    attempts_remaining_before: int = Field(ge=0)
    attempts_remaining_after: int = Field(ge=0)
    max_attempts: int = Field(ge=1)
    budget_reserved_before: Decimal = Field(ge=Decimal("0"))
    budget_reserved_after: Decimal = Field(ge=Decimal("0"))
    budget_remaining_before: Optional[Decimal] = None
    budget_remaining_after: Optional[Decimal] = None
    reservation_budget_remaining_after: Optional[Decimal] = None
    max_notional_per_attempt: Optional[Decimal] = None
    total_budget: Optional[Decimal] = None
    max_active_positions: int = Field(ge=0)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    reservation_status: RuntimeExecutionAttemptReservationStatus
    reservation_recorded: Literal[True] = True
    runtime_mutation_pending_before: Literal[True] = True
    runtime_budget_mutated: bool
    attempt_consumed: bool
    execution_intent_status_changed: Literal[False] = False
    order_created: Literal[False] = False
    exchange_called: Literal[False] = False
    owner_bounded_execution_called: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _status_flags_are_consistent(self) -> "RuntimeExecutionAttemptMutation":
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
                raise ValueError(f"attempt mutation contains forbidden execution field: {key}")
        if self.status == RuntimeExecutionAttemptMutationStatus.APPLIED:
            if self.blockers:
                raise ValueError("applied attempt mutation cannot have blockers")
            if not self.runtime_budget_mutated or not self.attempt_consumed:
                raise ValueError("applied attempt mutation must mutate budget and consume attempt")
        if self.status == RuntimeExecutionAttemptMutationStatus.BLOCKED:
            if self.runtime_budget_mutated or self.attempt_consumed:
                raise ValueError("blocked attempt mutation cannot mutate budget or consume attempt")
        return self


def build_runtime_execution_attempt_mutation(
    *,
    reservation: RuntimeExecutionAttemptReservation,
    runtime: StrategyRuntimeInstance,
    now_ms: int,
) -> tuple[RuntimeExecutionAttemptMutation, StrategyRuntimeInstance | None]:
    blockers: list[str] = []
    warnings = list(reservation.warnings)
    budget_reserved_before = runtime.boundary.budget_reserved
    budget_reserved_after = budget_reserved_before
    attempts_used_after = runtime.boundary.attempts_used
    attempts_remaining_after = runtime.attempts_remaining
    budget_remaining_after = runtime.budget_remaining
    updated_runtime: StrategyRuntimeInstance | None = None

    if reservation.status != RuntimeExecutionAttemptReservationStatus.PENDING_RUNTIME_MUTATION:
        blockers.append("reservation_not_pending_runtime_mutation")
    if reservation.runtime_instance_id != runtime.runtime_instance_id:
        blockers.append("runtime_instance_mismatch")
    if runtime.status != StrategyRuntimeInstanceStatus.ACTIVE:
        blockers.append("runtime_not_active")
    if runtime.boundary.attempts_used != reservation.attempts_used_before:
        blockers.append("runtime_attempt_state_drift")
    if runtime.attempts_remaining != reservation.attempts_remaining_before:
        blockers.append("runtime_attempt_remaining_drift")
    if runtime.budget_remaining != reservation.budget_remaining_before:
        blockers.append("runtime_budget_state_drift")
    if runtime.attempts_remaining <= 0:
        blockers.append("runtime_attempts_exhausted")
    if reservation.intended_notional is None:
        blockers.append("intended_notional_missing")
    elif (
        runtime.boundary.max_notional_per_attempt is not None
        and reservation.intended_notional > runtime.boundary.max_notional_per_attempt
    ):
        blockers.append("reservation_exceeds_max_notional_per_attempt")
    if (
        reservation.intended_notional is not None
        and runtime.budget_remaining is not None
        and reservation.intended_notional > runtime.budget_remaining
    ):
        blockers.append("reservation_exceeds_budget_remaining")

    if not blockers:
        assert reservation.intended_notional is not None
        attempts_used_after = runtime.boundary.attempts_used + 1
        budget_reserved_after = budget_reserved_before + reservation.intended_notional
        next_boundary = StrategyRuntimeBoundary.model_validate(
            {
                **runtime.boundary.model_dump(mode="python"),
                "attempts_used": attempts_used_after,
                "budget_reserved": budget_reserved_after,
            }
        )
        metadata = dict(runtime.metadata)
        metadata.update(
            {
                "last_attempt_mutation_id": _mutation_id(reservation.reservation_id),
                "last_attempt_reservation_id": reservation.reservation_id,
                "last_attempt_authorization_id": reservation.authorization_id,
            }
        )
        updated_runtime = runtime.model_copy(
            update={
                "boundary": next_boundary,
                "updated_at_ms": now_ms,
                "metadata": metadata,
            }
        )
        attempts_remaining_after = updated_runtime.attempts_remaining
        budget_remaining_after = updated_runtime.budget_remaining

    status = (
        RuntimeExecutionAttemptMutationStatus.BLOCKED
        if blockers
        else RuntimeExecutionAttemptMutationStatus.APPLIED
    )
    return (
        RuntimeExecutionAttemptMutation(
            mutation_id=_mutation_id(reservation.reservation_id),
            reservation_id=reservation.reservation_id,
            reservation_preview_id=reservation.reservation_preview_id,
            authorization_id=reservation.authorization_id,
            execution_intent_id=reservation.execution_intent_id,
            runtime_instance_id=runtime.runtime_instance_id,
            source_id=reservation.source_id,
            semantic_ids=reservation.semantic_ids,
            status=status,
            runtime_status_before=runtime.status,
            runtime_status_after=updated_runtime.status if updated_runtime else runtime.status,
            symbol=runtime.symbol,
            side=reservation.side,
            proposed_quantity=reservation.proposed_quantity,
            intended_notional=reservation.intended_notional,
            attempts_used_before=runtime.boundary.attempts_used,
            attempts_used_after=attempts_used_after,
            attempts_remaining_before=runtime.attempts_remaining,
            attempts_remaining_after=attempts_remaining_after,
            max_attempts=runtime.boundary.max_attempts,
            budget_reserved_before=budget_reserved_before,
            budget_reserved_after=budget_reserved_after,
            budget_remaining_before=runtime.budget_remaining,
            budget_remaining_after=budget_remaining_after,
            reservation_budget_remaining_after=reservation.budget_remaining_after,
            max_notional_per_attempt=runtime.boundary.max_notional_per_attempt,
            total_budget=runtime.boundary.total_budget,
            max_active_positions=runtime.boundary.max_active_positions,
            blockers=_dedupe(blockers),
            warnings=_dedupe(warnings),
            reservation_status=reservation.status,
            runtime_budget_mutated=status == RuntimeExecutionAttemptMutationStatus.APPLIED,
            attempt_consumed=status == RuntimeExecutionAttemptMutationStatus.APPLIED,
            created_at_ms=now_ms,
            metadata={
                "scope": "runtime_execution_attempt_mutation",
                "derived_from_reservation_id": reservation.reservation_id,
                "mutates_runtime_attempt_budget_only": status
                == RuntimeExecutionAttemptMutationStatus.APPLIED,
                "does_not_change_execution_intent_status": True,
                "does_not_call_owner_bounded_execution": True,
                "does_not_call_order_lifecycle": True,
                "does_not_call_exchange": True,
            },
        ),
        updated_runtime,
    )


def _mutation_id(reservation_id: str) -> str:
    return f"runtime-attempt-mutation-{reservation_id}"


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
