"""Shadow SignalEvaluation and OrderCandidate domain models.

These models are BRC strategy-runtime governance records only. They do not
create execution intents, call FinalGate, place/cancel orders, or connect to an
exchange.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.brc_audit_ids import BrcSemanticIds


FORBIDDEN_ORDER_CANDIDATE_FIELDS = frozenset(
    {
        "cancel_route",
        "client_order_id",
        "exchange_order_id",
        "exchange_payload",
        "execution_intent",
        "execution_intent_id",
        "order_id",
        "submit_route",
        "venue_order_id",
    }
)


FORBIDDEN_EXECUTION_FIELDS = FORBIDDEN_ORDER_CANDIDATE_FIELDS | frozenset(
    {
        "cancel_instruction",
        "close_instruction",
        "exchange_write",
        "final_gate_result",
        "final_gate_execute",
        "flatten_instruction",
        "order_request",
        "place_order",
        "route",
        "router",
        "router_target",
        "venue",
    }
)


class SignalEvaluationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SignalEvaluationStatus(str, Enum):
    EVALUATED = "evaluated"
    INVALIDATED = "invalidated"
    EXPIRED = "expired"
    PARKED = "parked"


class SignalEvaluationDecision(str, Enum):
    CANDIDATE = "candidate"
    NO_ACTION = "no_action"
    INVALID = "invalid"
    PARK = "park"


class OrderCandidateStatus(str, Enum):
    PROPOSED = "proposed"
    UNDER_REVIEW = "under_review"
    EXPIRED = "expired"
    PARKED = "parked"


class OrderCandidateRiskPreview(SignalEvaluationModel):
    intended_notional: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    proposed_quantity: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    max_loss_reference: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    leverage: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    margin_required: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    liquidation_price_reference: Optional[Decimal] = None
    liquidation_stop_buffer: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    notes: list[str] = Field(default_factory=list)


class OrderCandidateProtectionPreview(SignalEvaluationModel):
    requires_protection: bool = True
    stop_reference: Optional[str] = Field(default=None, max_length=256)
    stop_price_reference: Optional[Decimal] = None
    take_profit_references: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "OrderCandidateProtectionPreview":
        reject_forbidden_execution_fields(
            self.model_dump(mode="python"),
            root="protection_preview",
        )
        return self


class SignalEvaluation(SignalEvaluationModel):
    signal_evaluation_id: str = Field(min_length=1, max_length=128)
    runtime_instance_id: Optional[str] = Field(default=None, max_length=128)
    trial_binding_id: Optional[str] = Field(default=None, max_length=128)
    strategy_family_id: Optional[str] = Field(default=None, max_length=128)
    strategy_family_version_id: Optional[str] = Field(default=None, max_length=128)
    source_signal_id: Optional[str] = Field(default=None, max_length=128)
    symbol: str = Field(min_length=1, max_length=128)
    side: Literal["long", "short", "none"] = "none"
    status: SignalEvaluationStatus = SignalEvaluationStatus.EVALUATED
    decision: SignalEvaluationDecision = SignalEvaluationDecision.NO_ACTION
    reason_codes: list[str] = Field(default_factory=list)
    rationale: str = Field(default="", max_length=4096)
    evidence_snapshot: dict[str, Any] = Field(default_factory=dict)
    policy_snapshot: dict[str, Any] = Field(default_factory=dict)
    evaluated_at_ms: int = Field(ge=0)
    expires_at_ms: Optional[int] = Field(default=None, ge=0)
    shadow_mode: Literal[True] = True
    execution_enabled: Literal[False] = False
    not_order: Literal[True] = True
    not_execution_intent: Literal[True] = True
    created_at_ms: int = Field(ge=0)
    updated_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def semantic_ids(self) -> BrcSemanticIds:
        return BrcSemanticIds(
            runtime_instance_id=self.runtime_instance_id,
            trial_binding_id=self.trial_binding_id,
            strategy_family_id=self.strategy_family_id,
            strategy_family_version_id=self.strategy_family_version_id,
            signal_evaluation_id=self.signal_evaluation_id,
            order_candidate_id=None,
        )

    @model_validator(mode="after")
    def _enforce_shadow_invariants(self) -> "SignalEvaluation":
        if self.execution_enabled:
            raise ValueError("SignalEvaluation shadow path cannot enable execution")
        if not self.shadow_mode:
            raise ValueError("SignalEvaluation must remain shadow_mode")
        reject_forbidden_execution_fields(
            {
                "evidence_snapshot": self.evidence_snapshot,
                "policy_snapshot": self.policy_snapshot,
                "metadata": self.metadata,
            },
            root="signal_evaluation",
        )
        if self.decision == SignalEvaluationDecision.NO_ACTION and self.side != "none":
            raise ValueError("no_action signal evaluation must use side=none")
        return self


class OrderCandidate(SignalEvaluationModel):
    order_candidate_id: str = Field(min_length=1, max_length=128)
    signal_evaluation_id: str = Field(min_length=1, max_length=128)
    runtime_instance_id: Optional[str] = Field(default=None, max_length=128)
    trial_binding_id: Optional[str] = Field(default=None, max_length=128)
    strategy_family_id: Optional[str] = Field(default=None, max_length=128)
    strategy_family_version_id: Optional[str] = Field(default=None, max_length=128)
    symbol: str = Field(min_length=1, max_length=128)
    side: Literal["long", "short"]
    status: OrderCandidateStatus = OrderCandidateStatus.PROPOSED
    candidate_order_type: str = Field(default="market", min_length=1, max_length=64)
    proposed_quantity: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    intended_notional: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    entry_price_reference: Optional[Decimal] = None
    risk_preview: OrderCandidateRiskPreview = Field(default_factory=OrderCandidateRiskPreview)
    protection_preview: OrderCandidateProtectionPreview = Field(
        default_factory=OrderCandidateProtectionPreview
    )
    rationale: str = Field(default="", max_length=4096)
    evidence_refs: list[str] = Field(default_factory=list)
    shadow_mode: Literal[True] = True
    execution_enabled: Literal[False] = False
    candidate_executable: Literal[False] = False
    not_order: Literal[True] = True
    not_execution_intent: Literal[True] = True
    created_at_ms: int = Field(ge=0)
    updated_at_ms: int = Field(ge=0)
    expires_at_ms: Optional[int] = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def semantic_ids(self) -> BrcSemanticIds:
        return BrcSemanticIds(
            runtime_instance_id=self.runtime_instance_id,
            trial_binding_id=self.trial_binding_id,
            strategy_family_id=self.strategy_family_id,
            strategy_family_version_id=self.strategy_family_version_id,
            signal_evaluation_id=self.signal_evaluation_id,
            order_candidate_id=self.order_candidate_id,
        )

    @model_validator(mode="after")
    def _enforce_shadow_invariants(self) -> "OrderCandidate":
        if self.execution_enabled or self.candidate_executable:
            raise ValueError("OrderCandidate shadow path cannot be executable")
        if not self.shadow_mode:
            raise ValueError("OrderCandidate must remain shadow_mode")
        reject_forbidden_execution_fields(
            {
                "risk_preview": self.risk_preview.model_dump(mode="python"),
                "protection_preview": self.protection_preview.model_dump(mode="python"),
                "metadata": self.metadata,
            },
            root="order_candidate",
        )
        return self


def reject_forbidden_execution_fields(value: Any, *, root: str) -> None:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).strip().lower()
            if normalized in FORBIDDEN_EXECUTION_FIELDS:
                raise ValueError(f"{root} contains forbidden execution/order field: {key}")
            reject_forbidden_execution_fields(nested, root=f"{root}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            reject_forbidden_execution_fields(item, root=f"{root}[{index}]")
