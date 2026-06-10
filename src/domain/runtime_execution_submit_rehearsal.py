"""Non-mutating controlled-submit rehearsal aggregate.

This model gathers the existing runtime submit previews into one operator-facing
readiness result. It is deliberately not a submit command and cannot mutate
runtime state, create orders, or call exchange.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.execution_intent import ExecutionIntent
from src.domain.runtime_execution_attempt_reservation import (
    RuntimeExecutionAttemptReservationPreview,
)
from src.domain.runtime_execution_controlled_submit import (
    RuntimeExecutionControlledSubmitPlan,
    RuntimeExecutionControlledSubmitPreflight,
)
from src.domain.runtime_execution_intent_adapter import RuntimeExecutionSubmitReadiness
from src.domain.runtime_execution_protection_plan import (
    RuntimeExecutionProtectionPlanPreview,
)
from src.domain.runtime_execution_submit_adapter import (
    RuntimeExecutionSubmitAdapterPreview,
    RuntimeExecutionSubmitAdapterPreviewStatus,
)


class RuntimeExecutionSubmitRehearsalModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeExecutionSubmitRehearsalStatus(str, Enum):
    BLOCKED = "blocked"
    READY_FOR_NON_EXECUTING_SUBMIT_ADAPTER_BOUNDARY = (
        "ready_for_non_executing_submit_adapter_boundary"
    )


class RuntimeExecutionSubmitRehearsal(RuntimeExecutionSubmitRehearsalModel):
    rehearsal_id: str = Field(min_length=1, max_length=260)
    authorization_id: str = Field(min_length=1, max_length=220)
    execution_intent_id: str = Field(min_length=1, max_length=64)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    runtime_execution_intent_draft_id: Optional[str] = Field(
        default=None,
        max_length=180,
    )
    source_type: Optional[str] = Field(default=None, max_length=64)
    source_id: Optional[str] = Field(default=None, max_length=128)
    semantic_ids: BrcSemanticIds
    symbol: str = Field(min_length=1, max_length=128)
    side: Optional[str] = Field(default=None, max_length=32)
    status: RuntimeExecutionSubmitRehearsalStatus
    safe_stop_stage: str = Field(min_length=1, max_length=128)
    next_required_gate: str = Field(min_length=1, max_length=128)
    submit_readiness: RuntimeExecutionSubmitReadiness
    controlled_submit_plan: RuntimeExecutionControlledSubmitPlan
    controlled_submit_preflight: RuntimeExecutionControlledSubmitPreflight
    protection_plan_preview: RuntimeExecutionProtectionPlanPreview
    attempt_reservation_preview: RuntimeExecutionAttemptReservationPreview
    submit_adapter_preview: RuntimeExecutionSubmitAdapterPreview
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    preview_only: Literal[True] = True
    non_mutating_rehearsal: Literal[True] = True
    submit_executed: Literal[False] = False
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
    def _reject_execution_metadata(self) -> "RuntimeExecutionSubmitRehearsal":
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
                    f"submit rehearsal contains forbidden execution field: {key}"
                )
        if (
            self.status
            == RuntimeExecutionSubmitRehearsalStatus.READY_FOR_NON_EXECUTING_SUBMIT_ADAPTER_BOUNDARY
            and self.blockers
        ):
            raise ValueError("ready submit rehearsal cannot have blockers")
        return self


def build_runtime_execution_submit_rehearsal(
    *,
    intent: ExecutionIntent,
    submit_readiness: RuntimeExecutionSubmitReadiness,
    controlled_submit_plan: RuntimeExecutionControlledSubmitPlan,
    controlled_submit_preflight: RuntimeExecutionControlledSubmitPreflight,
    protection_plan_preview: RuntimeExecutionProtectionPlanPreview,
    attempt_reservation_preview: RuntimeExecutionAttemptReservationPreview,
    submit_adapter_preview: RuntimeExecutionSubmitAdapterPreview,
    now_ms: int,
) -> RuntimeExecutionSubmitRehearsal:
    blockers = _dedupe(
        list(submit_readiness.blockers)
        + list(controlled_submit_plan.blockers)
        + list(controlled_submit_preflight.blockers)
        + list(protection_plan_preview.blockers)
        + list(attempt_reservation_preview.blockers)
        + list(submit_adapter_preview.blockers)
    )
    warnings = _dedupe(
        list(submit_readiness.warnings)
        + list(controlled_submit_plan.warnings)
        + list(controlled_submit_preflight.warnings)
        + list(protection_plan_preview.warnings)
        + list(attempt_reservation_preview.warnings)
        + list(submit_adapter_preview.warnings)
    )

    if (
        submit_adapter_preview.status
        != RuntimeExecutionSubmitAdapterPreviewStatus.INPUTS_READY_DRY_RUN_ADAPTER_ONLY
    ):
        blockers.append("submit_adapter_preview_not_ready")
    blockers = _dedupe(blockers)

    ready = not blockers
    return RuntimeExecutionSubmitRehearsal(
        rehearsal_id=f"runtime-submit-rehearsal-{controlled_submit_plan.authorization_id}",
        authorization_id=controlled_submit_plan.authorization_id,
        execution_intent_id=intent.id,
        runtime_instance_id=intent.runtime_instance_id or "unknown-runtime",
        runtime_execution_intent_draft_id=intent.runtime_execution_intent_draft_id,
        source_type=intent.source_type,
        source_id=intent.source_id,
        semantic_ids=intent.semantic_ids,
        symbol=intent.symbol or controlled_submit_plan.symbol,
        side=controlled_submit_plan.side,
        status=(
            RuntimeExecutionSubmitRehearsalStatus.READY_FOR_NON_EXECUTING_SUBMIT_ADAPTER_BOUNDARY
            if ready
            else RuntimeExecutionSubmitRehearsalStatus.BLOCKED
        ),
        safe_stop_stage=(
            "inputs_ready_dry_run_adapter_only"
            if ready
            else "blocked_before_submit_adapter"
        ),
        next_required_gate=(
            "order_lifecycle_adapter_enablement_gate"
            if ready
            else "resolve_rehearsal_blockers"
        ),
        submit_readiness=submit_readiness,
        controlled_submit_plan=controlled_submit_plan,
        controlled_submit_preflight=controlled_submit_preflight,
        protection_plan_preview=protection_plan_preview,
        attempt_reservation_preview=attempt_reservation_preview,
        submit_adapter_preview=submit_adapter_preview,
        blockers=blockers,
        warnings=warnings,
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_submit_rehearsal",
            "aggregates_existing_non_executing_gates": True,
            "dry_run_submit_adapter_ready": True,
            "real_submit_still_disabled": True,
            "does_not_record_attempt_reservation": True,
            "does_not_apply_attempt_mutation": True,
            "does_not_record_protection_plan": True,
            "does_not_record_order_lifecycle_handoff": True,
            "does_not_call_owner_bounded_execution": True,
            "does_not_call_order_lifecycle": True,
            "does_not_call_exchange": True,
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
