"""Bridge strategy-family signals into runtime execution planning.

This service is a non-executing orchestration layer:

StrategyFamilySignalInput + StrategyFamilySignalOutput
-> B0 StrategySemantics shadow OrderCandidate
-> RuntimeExecutionPlan / RuntimeExecutionIntentDraft

It does not create recorded ExecutionIntent rows, orders, local order
registrations, OrderLifecycle calls, or exchange requests.
"""

from __future__ import annotations

from decimal import Decimal

from src.application.runtime_execution_planning_service import (
    RuntimeExecutionPlanningService,
)
from src.application.strategy_evaluation_context_builder import (
    StrategyEvaluationContextBuilder,
)
from src.application.strategy_semantics_shadow_binding_service import (
    StrategySemanticsShadowBindingService,
)
from src.application.strategy_runtime_fact_overlay_service import (
    StrategyRuntimeFactOverlayService,
)
from src.domain.runtime_execution_plan import (
    RuntimeExecutionIntentDraft,
    RuntimeExecutionPlan,
)
from src.domain.signal_evaluation import OrderCandidate
from src.domain.strategy_family_signal import (
    StrategyFamilySignalInput,
    StrategyFamilySignalOutput,
)
from src.domain.strategy_runtime import StrategyRuntimeInstance


class RuntimeStrategySignalPlanningService:
    """Non-executing strategy-signal to runtime-plan orchestration."""

    def __init__(
        self,
        *,
        semantics_binding_service: StrategySemanticsShadowBindingService,
        runtime_execution_planning_service: RuntimeExecutionPlanningService,
        runtime_fact_overlay_service: StrategyRuntimeFactOverlayService | None = None,
    ) -> None:
        self._semantics_binding_service = semantics_binding_service
        self._runtime_execution_planning_service = runtime_execution_planning_service
        self._runtime_fact_overlay_service = runtime_fact_overlay_service

    async def create_order_candidate_from_strategy_signal_pair(
        self,
        signal_input: StrategyFamilySignalInput,
        output: StrategyFamilySignalOutput,
        *,
        runtime: StrategyRuntimeInstance,
        context_builder: StrategyEvaluationContextBuilder | None = None,
        context_id: str | None = None,
        proposed_quantity: Decimal | None = None,
        intended_notional: Decimal | None = None,
        entry_price_reference: Decimal | None = None,
        stop_price_reference: Decimal | None = None,
        max_loss_reference: Decimal | None = None,
        leverage: Decimal | None = None,
        margin_required: Decimal | None = None,
        liquidation_price_reference: Decimal | None = None,
        liquidation_stop_buffer: Decimal | None = None,
        take_profit_references: list[dict] | None = None,
        expires_at_ms: int | None = None,
        metadata: dict | None = None,
    ) -> OrderCandidate:
        signal_input, metadata = await self._apply_runtime_fact_overlay(
            signal_input,
            output,
            runtime=runtime,
            metadata=metadata,
        )
        return await self._semantics_binding_service.create_semantic_order_candidate_from_strategy_signal_pair(
            signal_input,
            output,
            runtime=runtime,
            context_builder=context_builder,
            context_id=context_id,
            proposed_quantity=proposed_quantity,
            intended_notional=intended_notional,
            entry_price_reference=entry_price_reference,
            stop_price_reference=stop_price_reference,
            max_loss_reference=max_loss_reference,
            leverage=leverage,
            margin_required=margin_required,
            liquidation_price_reference=liquidation_price_reference,
            liquidation_stop_buffer=liquidation_stop_buffer,
            take_profit_references=take_profit_references,
            expires_at_ms=expires_at_ms,
            metadata={
                "runtime_strategy_signal_planning": True,
                "non_executing_orchestration": True,
                "does_not_create_recorded_execution_intent": True,
                "does_not_call_order_lifecycle": True,
                "does_not_call_exchange": True,
                **(metadata or {}),
            },
        )

    async def _apply_runtime_fact_overlay(
        self,
        signal_input: StrategyFamilySignalInput,
        output: StrategyFamilySignalOutput,
        *,
        runtime: StrategyRuntimeInstance,
        metadata: dict | None,
    ) -> tuple[StrategyFamilySignalInput, dict]:
        overlay = self._runtime_fact_overlay_service
        if overlay is None:
            return signal_input, dict(metadata or {})
        result = await overlay.apply(signal_input, output=output, runtime=runtime)
        return result.signal_input, {
            **(metadata or {}),
            "trusted_runtime_fact_overlay": {
                "applied": result.applied,
                "blockers": result.blockers,
                "warnings": result.warnings,
                "metadata": result.metadata,
            },
        }

    async def plan_strategy_signal_pair(
        self,
        signal_input: StrategyFamilySignalInput,
        output: StrategyFamilySignalOutput,
        *,
        runtime: StrategyRuntimeInstance,
        owner_reviewed: bool = False,
        context_builder: StrategyEvaluationContextBuilder | None = None,
        context_id: str | None = None,
        proposed_quantity: Decimal | None = None,
        intended_notional: Decimal | None = None,
        entry_price_reference: Decimal | None = None,
        stop_price_reference: Decimal | None = None,
        max_loss_reference: Decimal | None = None,
        leverage: Decimal | None = None,
        margin_required: Decimal | None = None,
        liquidation_price_reference: Decimal | None = None,
        liquidation_stop_buffer: Decimal | None = None,
        take_profit_references: list[dict] | None = None,
        expires_at_ms: int | None = None,
        metadata: dict | None = None,
    ) -> RuntimeExecutionPlan:
        candidate = await self.create_order_candidate_from_strategy_signal_pair(
            signal_input,
            output,
            runtime=runtime,
            context_builder=context_builder,
            context_id=context_id,
            proposed_quantity=proposed_quantity,
            intended_notional=intended_notional,
            entry_price_reference=entry_price_reference,
            stop_price_reference=stop_price_reference,
            max_loss_reference=max_loss_reference,
            leverage=leverage,
            margin_required=margin_required,
            liquidation_price_reference=liquidation_price_reference,
            liquidation_stop_buffer=liquidation_stop_buffer,
            take_profit_references=take_profit_references,
            expires_at_ms=expires_at_ms,
            metadata=metadata,
        )
        return await self._runtime_execution_planning_service.plan_order_candidate(
            order_candidate_id=candidate.order_candidate_id,
            owner_reviewed=owner_reviewed,
        )

    async def intent_draft_for_strategy_signal_pair(
        self,
        signal_input: StrategyFamilySignalInput,
        output: StrategyFamilySignalOutput,
        *,
        runtime: StrategyRuntimeInstance,
        owner_reviewed: bool = False,
        owner_confirmed_for_intent: bool = False,
        context_builder: StrategyEvaluationContextBuilder | None = None,
        context_id: str | None = None,
        proposed_quantity: Decimal | None = None,
        intended_notional: Decimal | None = None,
        entry_price_reference: Decimal | None = None,
        stop_price_reference: Decimal | None = None,
        max_loss_reference: Decimal | None = None,
        leverage: Decimal | None = None,
        margin_required: Decimal | None = None,
        liquidation_price_reference: Decimal | None = None,
        liquidation_stop_buffer: Decimal | None = None,
        take_profit_references: list[dict] | None = None,
        expires_at_ms: int | None = None,
        metadata: dict | None = None,
    ) -> RuntimeExecutionIntentDraft:
        candidate = await self.create_order_candidate_from_strategy_signal_pair(
            signal_input,
            output,
            runtime=runtime,
            context_builder=context_builder,
            context_id=context_id,
            proposed_quantity=proposed_quantity,
            intended_notional=intended_notional,
            entry_price_reference=entry_price_reference,
            stop_price_reference=stop_price_reference,
            max_loss_reference=max_loss_reference,
            leverage=leverage,
            margin_required=margin_required,
            liquidation_price_reference=liquidation_price_reference,
            liquidation_stop_buffer=liquidation_stop_buffer,
            take_profit_references=take_profit_references,
            expires_at_ms=expires_at_ms,
            metadata=metadata,
        )
        return await self._runtime_execution_planning_service.intent_draft_for_order_candidate(
            order_candidate_id=candidate.order_candidate_id,
            owner_reviewed=owner_reviewed,
            owner_confirmed_for_intent=owner_confirmed_for_intent,
        )

    async def record_intent_draft_for_strategy_signal_pair(
        self,
        signal_input: StrategyFamilySignalInput,
        output: StrategyFamilySignalOutput,
        *,
        runtime: StrategyRuntimeInstance,
        owner_reviewed: bool = False,
        owner_confirmed_for_intent: bool = False,
        context_builder: StrategyEvaluationContextBuilder | None = None,
        context_id: str | None = None,
        proposed_quantity: Decimal | None = None,
        intended_notional: Decimal | None = None,
        entry_price_reference: Decimal | None = None,
        stop_price_reference: Decimal | None = None,
        max_loss_reference: Decimal | None = None,
        leverage: Decimal | None = None,
        margin_required: Decimal | None = None,
        liquidation_price_reference: Decimal | None = None,
        liquidation_stop_buffer: Decimal | None = None,
        take_profit_references: list[dict] | None = None,
        expires_at_ms: int | None = None,
        metadata: dict | None = None,
    ) -> RuntimeExecutionIntentDraft:
        candidate = await self.create_order_candidate_from_strategy_signal_pair(
            signal_input,
            output,
            runtime=runtime,
            context_builder=context_builder,
            context_id=context_id,
            proposed_quantity=proposed_quantity,
            intended_notional=intended_notional,
            entry_price_reference=entry_price_reference,
            stop_price_reference=stop_price_reference,
            max_loss_reference=max_loss_reference,
            leverage=leverage,
            margin_required=margin_required,
            liquidation_price_reference=liquidation_price_reference,
            liquidation_stop_buffer=liquidation_stop_buffer,
            take_profit_references=take_profit_references,
            expires_at_ms=expires_at_ms,
            metadata=metadata,
        )
        return await self._runtime_execution_planning_service.record_intent_draft_for_order_candidate(
            order_candidate_id=candidate.order_candidate_id,
            owner_reviewed=owner_reviewed,
            owner_confirmed_for_intent=owner_confirmed_for_intent,
        )
