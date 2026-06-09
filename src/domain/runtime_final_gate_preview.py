"""Runtime-aware FinalGate preview models.

These models are inspection and dry-run artifacts only. They do not grant
execution authority, create executable records, place orders, or call exchange.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.signal_evaluation import OrderCandidate
from src.domain.strategy_runtime import StrategyRuntimeInstance


class RuntimeFinalGatePreviewModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeFinalGatePreviewVerdict(str, Enum):
    PASS = "PASS"
    BLOCK = "BLOCK"
    WARN = "WARN"


class RuntimeFinalGateCheck(RuntimeFinalGatePreviewModel):
    name: str = Field(min_length=1, max_length=128)
    verdict: RuntimeFinalGatePreviewVerdict
    code: str = Field(min_length=1, max_length=128)
    message: str = Field(default="", max_length=1024)
    facts: dict[str, Any] = Field(default_factory=dict)


class RuntimeFinalGateBoundarySnapshot(RuntimeFinalGatePreviewModel):
    runtime_instance_id: str
    status: str
    shadow_mode: bool
    execution_enabled: bool
    attempts_remaining: int
    budget_remaining: Optional[Decimal] = None
    max_notional_per_attempt: Optional[Decimal] = None
    allowed_symbols: list[str] = Field(default_factory=list)
    allowed_sides: list[str] = Field(default_factory=list)
    max_leverage: Optional[Decimal] = None
    max_margin_per_attempt: Optional[Decimal] = None
    min_liquidation_stop_buffer: Optional[Decimal] = None
    max_active_positions: int
    requires_protection: bool
    requires_review: bool


class RuntimeFinalGateCandidateSnapshot(RuntimeFinalGatePreviewModel):
    order_candidate_id: str
    signal_evaluation_id: str
    runtime_instance_id: Optional[str] = None
    symbol: str
    side: str
    status: str
    candidate_order_type: str
    proposed_quantity: Optional[Decimal] = None
    intended_notional: Optional[Decimal] = None
    entry_price_reference: Optional[Decimal] = None
    candidate_leverage: Optional[Decimal] = None
    margin_required: Optional[Decimal] = None
    liquidation_price_reference: Optional[Decimal] = None
    liquidation_stop_buffer: Optional[Decimal] = None
    protection_required: bool
    protection_reference_present: bool
    shadow_mode: bool
    execution_enabled: bool
    candidate_executable: bool
    not_order: bool
    not_execution_intent: bool


class RuntimeFinalGateAuditSnapshot(RuntimeFinalGatePreviewModel):
    ids: BrcSemanticIds
    complete: bool
    mismatches: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)


class RuntimeFinalGatePreview(RuntimeFinalGatePreviewModel):
    verdict: RuntimeFinalGatePreviewVerdict
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checks: list[RuntimeFinalGateCheck] = Field(default_factory=list)
    runtime_boundary_snapshot: RuntimeFinalGateBoundarySnapshot
    candidate_snapshot: RuntimeFinalGateCandidateSnapshot
    audit_id_snapshot: RuntimeFinalGateAuditSnapshot
    active_positions_count: Optional[int] = None
    owner_reviewed: bool = False
    dry_run: Literal[True] = True
    preview_only: Literal[True] = True
    shadow_mode: Literal[True] = True
    execution_enabled: Literal[False] = False
    candidate_executable: Literal[False] = False
    not_order: Literal[True] = True
    not_execution_intent: Literal[True] = True
    runtime_state_mutated: Literal[False] = False
    exchange_called: Literal[False] = False
    execution_intent_created: Literal[False] = False
    order_created: Literal[False] = False
    metadata: dict[str, Any] = Field(default_factory=dict)


def build_runtime_boundary_snapshot(
    runtime: StrategyRuntimeInstance,
) -> RuntimeFinalGateBoundarySnapshot:
    boundary = runtime.boundary
    return RuntimeFinalGateBoundarySnapshot(
        runtime_instance_id=runtime.runtime_instance_id,
        status=runtime.status.value,
        shadow_mode=runtime.shadow_mode,
        execution_enabled=runtime.execution_enabled,
        attempts_remaining=runtime.attempts_remaining,
        budget_remaining=runtime.budget_remaining,
        max_notional_per_attempt=boundary.max_notional_per_attempt,
        allowed_symbols=list(boundary.allowed_symbols),
        allowed_sides=list(boundary.allowed_sides),
        max_leverage=boundary.max_leverage,
        max_margin_per_attempt=boundary.max_margin_per_attempt,
        min_liquidation_stop_buffer=boundary.min_liquidation_stop_buffer,
        max_active_positions=boundary.max_active_positions,
        requires_protection=boundary.requires_protection,
        requires_review=boundary.requires_review,
    )


def build_runtime_candidate_snapshot(
    candidate: OrderCandidate,
) -> RuntimeFinalGateCandidateSnapshot:
    candidate_leverage = candidate.risk_preview.leverage
    protection_reference_present = bool(
        candidate.protection_preview.stop_reference
        or candidate.protection_preview.stop_price_reference is not None
        or candidate.protection_preview.take_profit_references
    )
    return RuntimeFinalGateCandidateSnapshot(
        order_candidate_id=candidate.order_candidate_id,
        signal_evaluation_id=candidate.signal_evaluation_id,
        runtime_instance_id=candidate.runtime_instance_id,
        symbol=candidate.symbol,
        side=candidate.side,
        status=candidate.status.value,
        candidate_order_type=candidate.candidate_order_type,
        proposed_quantity=candidate.proposed_quantity,
        intended_notional=candidate.intended_notional,
        entry_price_reference=candidate.entry_price_reference,
        candidate_leverage=candidate_leverage,
        margin_required=candidate.risk_preview.margin_required,
        liquidation_price_reference=candidate.risk_preview.liquidation_price_reference,
        liquidation_stop_buffer=candidate.risk_preview.liquidation_stop_buffer,
        protection_required=candidate.protection_preview.requires_protection,
        protection_reference_present=protection_reference_present,
        shadow_mode=candidate.shadow_mode,
        execution_enabled=candidate.execution_enabled,
        candidate_executable=candidate.candidate_executable,
        not_order=candidate.not_order,
        not_execution_intent=candidate.not_execution_intent,
    )
