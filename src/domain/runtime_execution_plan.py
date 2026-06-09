"""Runtime execution plan draft models.

These models bridge OrderCandidate review toward ExecutionIntent creation, but
remain non-executable. They do not create ExecutionIntent records, orders, or
exchange requests.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.runtime_final_gate_preview import (
    RuntimeFinalGatePreview,
    RuntimeFinalGatePreviewVerdict,
)
from src.domain.signal_evaluation import (
    OrderCandidate,
    OrderCandidateProtectionPreview,
    OrderCandidateRiskPreview,
)


FORBIDDEN_RUNTIME_EXECUTION_PLAN_FIELDS = frozenset(
    {
        "client_order_id",
        "exchange_order_id",
        "exchange_payload",
        "execution_intent",
        "execution_intent_id",
        "order_id",
        "place_order",
        "submit_order",
        "venue_order_id",
    }
)


class RuntimeExecutionPlanModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeExecutionPlanStatus(str, Enum):
    BLOCKED = "blocked"
    OWNER_REVIEW_REQUIRED = "owner_review_required"
    READY_FOR_INTENT_DRAFT = "ready_for_intent_draft"


class RuntimeExecutionIntentDraftStatus(str, Enum):
    BLOCKED = "blocked"
    OWNER_CONFIRMATION_REQUIRED = "owner_confirmation_required"
    READY_FOR_INTENT_CREATION = "ready_for_intent_creation"


class RuntimeExecutionPlan(RuntimeExecutionPlanModel):
    plan_id: str = Field(min_length=1, max_length=160)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    order_candidate_id: str = Field(min_length=1, max_length=128)
    signal_evaluation_id: str = Field(min_length=1, max_length=128)
    semantic_ids: BrcSemanticIds
    status: RuntimeExecutionPlanStatus
    symbol: str = Field(min_length=1, max_length=128)
    side: str = Field(min_length=1, max_length=32)
    candidate_order_type: str = Field(min_length=1, max_length=64)
    proposed_quantity: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    intended_notional: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    entry_price_reference: Optional[Decimal] = None
    risk_preview: OrderCandidateRiskPreview = Field(default_factory=OrderCandidateRiskPreview)
    protection_preview: OrderCandidateProtectionPreview = Field(
        default_factory=OrderCandidateProtectionPreview
    )
    final_gate_preview: RuntimeFinalGatePreview
    owner_confirmation_required: Literal[True] = True
    owner_reviewed: bool = False
    submit_enabled: Literal[False] = False
    dry_run: Literal[True] = True
    preview_only: Literal[True] = True
    not_order: Literal[True] = True
    not_execution_intent: Literal[True] = True
    execution_intent_created: Literal[False] = False
    order_created: Literal[False] = False
    exchange_called: Literal[False] = False
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "RuntimeExecutionPlan":
        reject_forbidden_plan_fields(
            {
                "metadata": self.metadata,
                "final_gate_preview": self.final_gate_preview.model_dump(mode="python"),
            },
            root="runtime_execution_plan",
        )
        return self


class RuntimeExecutionIntentDraft(RuntimeExecutionPlanModel):
    draft_id: str = Field(min_length=1, max_length=180)
    plan_id: str = Field(min_length=1, max_length=160)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    order_candidate_id: str = Field(min_length=1, max_length=128)
    signal_evaluation_id: str = Field(min_length=1, max_length=128)
    semantic_ids: BrcSemanticIds
    status: RuntimeExecutionIntentDraftStatus
    symbol: str = Field(min_length=1, max_length=128)
    side: str = Field(min_length=1, max_length=32)
    candidate_order_type: str = Field(min_length=1, max_length=64)
    proposed_quantity: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    intended_notional: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    entry_price_reference: Optional[Decimal] = None
    risk_preview: OrderCandidateRiskPreview = Field(default_factory=OrderCandidateRiskPreview)
    protection_preview: OrderCandidateProtectionPreview = Field(
        default_factory=OrderCandidateProtectionPreview
    )
    owner_reviewed: bool
    owner_confirmed_for_intent: bool = False
    source_plan_status: RuntimeExecutionPlanStatus
    final_gate_verdict: RuntimeFinalGatePreviewVerdict
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    owner_confirmation_required: Literal[True] = True
    dry_run: Literal[True] = True
    preview_only: Literal[True] = True
    not_order: Literal[True] = True
    not_execution_intent: Literal[True] = True
    execution_intent_repository_write_enabled: Literal[False] = False
    execution_intent_created: Literal[False] = False
    order_created: Literal[False] = False
    exchange_called: Literal[False] = False
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "RuntimeExecutionIntentDraft":
        reject_forbidden_plan_fields(
            {
                "metadata": self.metadata,
                "risk_preview": self.risk_preview.model_dump(mode="python"),
                "protection_preview": self.protection_preview.model_dump(mode="python"),
            },
            root="runtime_execution_intent_draft",
        )
        return self


def build_runtime_execution_plan(
    *,
    candidate: OrderCandidate,
    preview: RuntimeFinalGatePreview,
    now_ms: int,
) -> RuntimeExecutionPlan:
    if not candidate.runtime_instance_id:
        raise ValueError("RuntimeExecutionPlan requires candidate.runtime_instance_id")

    blockers_without_owner_review = [
        blocker for blocker in preview.blockers if blocker != "owner_review_required"
    ]
    if blockers_without_owner_review:
        status = RuntimeExecutionPlanStatus.BLOCKED
    elif "owner_review_required" in preview.blockers:
        status = RuntimeExecutionPlanStatus.OWNER_REVIEW_REQUIRED
    elif preview.verdict == RuntimeFinalGatePreviewVerdict.PASS:
        status = RuntimeExecutionPlanStatus.READY_FOR_INTENT_DRAFT
    else:
        status = RuntimeExecutionPlanStatus.BLOCKED

    return RuntimeExecutionPlan(
        plan_id=f"runtime-plan-{candidate.order_candidate_id}",
        runtime_instance_id=candidate.runtime_instance_id,
        order_candidate_id=candidate.order_candidate_id,
        signal_evaluation_id=candidate.signal_evaluation_id,
        semantic_ids=candidate.semantic_ids,
        status=status,
        symbol=candidate.symbol,
        side=candidate.side,
        candidate_order_type=candidate.candidate_order_type,
        proposed_quantity=candidate.proposed_quantity,
        intended_notional=candidate.intended_notional,
        entry_price_reference=candidate.entry_price_reference,
        risk_preview=candidate.risk_preview,
        protection_preview=candidate.protection_preview,
        final_gate_preview=preview,
        owner_reviewed=preview.owner_reviewed,
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_plan",
            "non_executable": True,
            "final_gate_preview_verdict": preview.verdict.value,
        },
    )


def build_runtime_execution_intent_draft(
    *,
    plan: RuntimeExecutionPlan,
    owner_confirmed_for_intent: bool,
    now_ms: int,
) -> RuntimeExecutionIntentDraft:
    if plan.status == RuntimeExecutionPlanStatus.BLOCKED:
        status = RuntimeExecutionIntentDraftStatus.BLOCKED
    elif not owner_confirmed_for_intent:
        status = RuntimeExecutionIntentDraftStatus.OWNER_CONFIRMATION_REQUIRED
    else:
        status = RuntimeExecutionIntentDraftStatus.READY_FOR_INTENT_CREATION

    return RuntimeExecutionIntentDraft(
        draft_id=f"runtime-intent-draft-{plan.order_candidate_id}",
        plan_id=plan.plan_id,
        runtime_instance_id=plan.runtime_instance_id,
        order_candidate_id=plan.order_candidate_id,
        signal_evaluation_id=plan.signal_evaluation_id,
        semantic_ids=plan.semantic_ids,
        status=status,
        symbol=plan.symbol,
        side=plan.side,
        candidate_order_type=plan.candidate_order_type,
        proposed_quantity=plan.proposed_quantity,
        intended_notional=plan.intended_notional,
        entry_price_reference=plan.entry_price_reference,
        risk_preview=plan.risk_preview,
        protection_preview=plan.protection_preview,
        owner_reviewed=plan.owner_reviewed,
        owner_confirmed_for_intent=owner_confirmed_for_intent,
        source_plan_status=plan.status,
        final_gate_verdict=plan.final_gate_preview.verdict,
        blockers=list(plan.final_gate_preview.blockers),
        warnings=list(plan.final_gate_preview.warnings),
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_intent_draft",
            "non_executable": True,
            "does_not_write_execution_intents": True,
        },
    )


def reject_forbidden_plan_fields(value: Any, *, root: str) -> None:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).strip().lower()
            if normalized in FORBIDDEN_RUNTIME_EXECUTION_PLAN_FIELDS:
                raise ValueError(f"{root} contains forbidden execution field: {key}")
            reject_forbidden_plan_fields(nested, root=f"{root}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            reject_forbidden_plan_fields(item, root=f"{root}[{index}]")
