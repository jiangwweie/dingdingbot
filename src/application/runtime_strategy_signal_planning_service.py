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
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.application.runtime_execution_planning_service import (
    RuntimeExecutionPlanningService,
)
from src.application.runtime_strategy_signal_evaluation_service import (
    RuntimeStrategySignalEvaluationResult,
    RuntimeStrategySignalEvaluationService,
    RuntimeStrategySignalEvaluationStatus,
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
    SignalSide,
    StrategyFamilySignalInput,
    StrategyFamilySignalOutput,
)
from src.domain.strategy_runtime import StrategyRuntimeInstance
from src.domain.strategy_semantics import (
    StrategyFactCheckStatus,
    StrategySemanticsCatalog,
    initial_strategy_semantics_catalog,
)


TRUSTED_MARKET_FACT_KEYS = frozenset(
    {
        "funding_rate",
        "open_interest",
        "crowding_proxy",
    }
)


class RuntimeStrategySignalPlanningError(ValueError):
    """Raised when runtime strategy planning cannot stay within B0 gates."""


class RuntimeStrategySignalCandidatePlanningStatus(str, Enum):
    SHADOW_CANDIDATE_CREATED = "shadow_candidate_created"
    OBSERVE_ONLY = "observe_only"
    BLOCKED = "blocked"


class RuntimeStrategySignalCandidatePlanningProposal(BaseModel):
    """Non-executing proposal used to materialize a shadow OrderCandidate."""

    model_config = ConfigDict(extra="forbid")

    entry_price_reference: Decimal | None = None
    stop_price_reference: Decimal | None = None
    stop_source: str | None = Field(default=None, max_length=128)
    proposed_quantity: Decimal | None = None
    intended_notional: Decimal | None = None
    max_loss_reference: Decimal | None = None
    leverage: Decimal | None = None
    margin_required: Decimal | None = None
    liquidation_price_reference: Decimal | None = None
    liquidation_stop_buffer: Decimal | None = None
    take_profit_references: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    not_order: Literal[True] = True
    not_execution_intent: Literal[True] = True
    not_execution_authority: Literal[True] = True


class RuntimeStrategySignalCandidatePlanningResult(BaseModel):
    """Result for raw strategy signal input -> shadow candidate planning."""

    model_config = ConfigDict(extra="forbid")

    planning_id: str = Field(min_length=1, max_length=180)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    strategy_family_id: str = Field(min_length=1, max_length=128)
    strategy_family_version_id: str = Field(min_length=1, max_length=128)
    symbol: str = Field(min_length=1, max_length=128)
    status: RuntimeStrategySignalCandidatePlanningStatus
    evaluation_result: RuntimeStrategySignalEvaluationResult
    candidate: OrderCandidate | None = None
    proposal: RuntimeStrategySignalCandidatePlanningProposal | None = None
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    signal_evaluation_created: bool = False
    order_candidate_created: bool = False
    execution_intent_created: Literal[False] = False
    order_created: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    exchange_called: Literal[False] = False
    not_order: Literal[True] = True
    not_execution_intent: Literal[True] = True
    not_execution_authority: Literal[True] = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeStrategySignalPlanningService:
    """Non-executing strategy-signal to runtime-plan orchestration."""

    def __init__(
        self,
        *,
        semantics_binding_service: StrategySemanticsShadowBindingService,
        runtime_execution_planning_service: RuntimeExecutionPlanningService,
        runtime_fact_overlay_service: StrategyRuntimeFactOverlayService | None = None,
        semantics_catalog: StrategySemanticsCatalog | None = None,
        signal_evaluation_service: RuntimeStrategySignalEvaluationService | None = None,
    ) -> None:
        self._semantics_binding_service = semantics_binding_service
        self._runtime_execution_planning_service = runtime_execution_planning_service
        self._runtime_fact_overlay_service = runtime_fact_overlay_service
        self._semantics_catalog = semantics_catalog or initial_strategy_semantics_catalog()
        self._signal_evaluation_service = signal_evaluation_service or (
            RuntimeStrategySignalEvaluationService(catalog=self._semantics_catalog)
        )

    async def plan_shadow_candidate_from_signal_input(
        self,
        signal_input: StrategyFamilySignalInput,
        *,
        runtime: StrategyRuntimeInstance,
        context_builder: StrategyEvaluationContextBuilder | None = None,
        context_id: str | None = None,
        expires_at_ms: int | None = None,
        metadata: dict | None = None,
    ) -> RuntimeStrategySignalCandidatePlanningResult:
        """Evaluate a raw strategy signal input and create only shadow records.

        This is the v1 Strategy Signal -> Shadow Candidate Planning path. It
        routes through the evaluator semantics gate, overlays trusted runtime
        facts, pre-checks RequiredFacts, generates a bounded proposal, and only
        then materializes a shadow SignalEvaluation + shadow OrderCandidate.
        """

        evaluation = self._signal_evaluation_service.evaluate(signal_input)
        if (
            evaluation.status
            != RuntimeStrategySignalEvaluationStatus.READY_FOR_SEMANTIC_BINDING
            or evaluation.output is None
        ):
            return self._candidate_planning_result(
                signal_input,
                runtime=runtime,
                evaluation=evaluation,
                status=(
                    RuntimeStrategySignalCandidatePlanningStatus.OBSERVE_ONLY
                    if evaluation.status
                    == RuntimeStrategySignalEvaluationStatus.OBSERVE_ONLY
                    else RuntimeStrategySignalCandidatePlanningStatus.BLOCKED
                ),
                blockers=list(evaluation.blockers),
                warnings=list(evaluation.warnings),
                metadata={
                    "blocked_before_shadow_candidate": True,
                    "candidate_not_created_reason": "semantic_evaluator_gate_not_ready",
                },
            )

        output = evaluation.output
        try:
            signal_input, overlay_metadata = await self._apply_runtime_fact_overlay(
                signal_input,
                output,
                runtime=runtime,
                metadata=metadata,
                require_trusted_runtime_overlay=True,
            )
        except RuntimeStrategySignalPlanningError as exc:
            return self._candidate_planning_result(
                signal_input,
                runtime=runtime,
                evaluation=evaluation,
                status=RuntimeStrategySignalCandidatePlanningStatus.BLOCKED,
                blockers=[str(exc)],
                warnings=list(evaluation.warnings),
                metadata={
                    "blocked_before_shadow_candidate": True,
                    "candidate_not_created_reason": "trusted_runtime_fact_overlay_missing",
                },
            )

        overlay_blockers = list(
            overlay_metadata.get("trusted_runtime_fact_overlay", {}).get("blockers", [])
        )
        if overlay_blockers:
            return self._candidate_planning_result(
                signal_input,
                runtime=runtime,
                evaluation=evaluation,
                status=RuntimeStrategySignalCandidatePlanningStatus.BLOCKED,
                blockers=overlay_blockers,
                warnings=list(evaluation.warnings)
                + list(
                    overlay_metadata.get("trusted_runtime_fact_overlay", {}).get(
                        "warnings",
                        [],
                    )
                ),
                metadata={
                    **overlay_metadata,
                    "blocked_before_shadow_candidate": True,
                    "candidate_not_created_reason": "trusted_runtime_fact_overlay_blocked",
                },
            )

        builder = context_builder or StrategyEvaluationContextBuilder()
        context = builder.build(
            signal_input,
            output=output,
            runtime=runtime,
            context_id=context_id,
        )
        binding = self._semantics_catalog.get_binding(
            strategy_family_id=output.strategy_family_id,
            strategy_family_version_id=output.strategy_family_version_id,
        )
        fact_check = binding.fact_check(context)
        if fact_check.status != StrategyFactCheckStatus.PASS:
            return self._candidate_planning_result(
                signal_input,
                runtime=runtime,
                evaluation=evaluation,
                status=RuntimeStrategySignalCandidatePlanningStatus.BLOCKED,
                blockers=[
                    f"strategy_required_facts_not_pass:{fact_check.status.value}",
                    *fact_check.missing_facts,
                    *fact_check.stale_facts,
                ],
                warnings=list(evaluation.warnings) + fact_check.warnings,
                metadata={
                    **overlay_metadata,
                    "blocked_before_shadow_candidate": True,
                    "candidate_not_created_reason": "required_facts_not_pass",
                    "fact_check": fact_check.model_dump(mode="json"),
                },
            )

        try:
            proposal = _build_candidate_planning_proposal(
                signal_input,
                output,
                runtime=runtime,
            )
        except RuntimeStrategySignalPlanningError as exc:
            return self._candidate_planning_result(
                signal_input,
                runtime=runtime,
                evaluation=evaluation,
                status=RuntimeStrategySignalCandidatePlanningStatus.BLOCKED,
                blockers=[str(exc)],
                warnings=list(evaluation.warnings),
                metadata={
                    **overlay_metadata,
                    "blocked_before_shadow_candidate": True,
                    "candidate_not_created_reason": "proposal_generation_blocked",
                },
            )

        binding_service = self._semantics_binding_service
        candidate = await binding_service.create_semantic_order_candidate_from_strategy_output(
            output,
            context=context,
            runtime=runtime,
            proposed_quantity=proposal.proposed_quantity,
            intended_notional=proposal.intended_notional,
            entry_price_reference=proposal.entry_price_reference,
            stop_price_reference=proposal.stop_price_reference,
            max_loss_reference=proposal.max_loss_reference,
            leverage=proposal.leverage,
            margin_required=proposal.margin_required,
            liquidation_price_reference=proposal.liquidation_price_reference,
            liquidation_stop_buffer=proposal.liquidation_stop_buffer,
            take_profit_references=proposal.take_profit_references,
            expires_at_ms=expires_at_ms,
            metadata={
                **overlay_metadata,
                "runtime_strategy_signal_candidate_planning": True,
                "signal_evaluation_gate_status": evaluation.status.value,
                "planning_proposal": proposal.model_dump(mode="json"),
                "does_not_create_recorded_execution_intent": True,
                "does_not_call_order_lifecycle": True,
                "does_not_call_exchange": True,
            },
        )
        return self._candidate_planning_result(
            signal_input,
            runtime=runtime,
            evaluation=evaluation,
            status=RuntimeStrategySignalCandidatePlanningStatus.SHADOW_CANDIDATE_CREATED,
            candidate=candidate,
            proposal=proposal,
            blockers=[],
            warnings=list(evaluation.warnings),
            metadata={
                **overlay_metadata,
                "fact_check": fact_check.model_dump(mode="json"),
                "shadow_only": True,
                "runtime_bounded_auto_attempts_preserved": True,
            },
        )

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
        binding_service = self._semantics_binding_service
        return await binding_service.create_semantic_order_candidate_from_strategy_signal_pair(
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
        require_trusted_runtime_overlay: bool = False,
    ) -> tuple[StrategyFamilySignalInput, dict]:
        required_market_fact_keys = self._required_trusted_market_fact_keys(
            signal_input,
            output,
        )
        overlay = self._runtime_fact_overlay_service
        if overlay is None:
            if require_trusted_runtime_overlay:
                raise RuntimeStrategySignalPlanningError(
                    "trusted_runtime_fact_overlay_required_for_candidate_planning"
                )
            if required_market_fact_keys:
                raise RuntimeStrategySignalPlanningError(
                    "trusted market fact overlay is required by strategy semantics"
                )
            return signal_input, dict(metadata or {})
        result = await overlay.apply(
            signal_input,
            output=output,
            runtime=runtime,
            required_market_fact_keys=required_market_fact_keys or None,
            require_trusted_market_fact_source=bool(required_market_fact_keys),
        )
        return result.signal_input, {
            **(metadata or {}),
            "trusted_runtime_fact_overlay": {
                "applied": result.applied,
                "blockers": result.blockers,
                "warnings": result.warnings,
                "metadata": result.metadata,
            },
            "strategy_required_trusted_market_facts": list(required_market_fact_keys),
        }

    def _candidate_planning_result(
        self,
        signal_input: StrategyFamilySignalInput,
        *,
        runtime: StrategyRuntimeInstance,
        evaluation: RuntimeStrategySignalEvaluationResult,
        status: RuntimeStrategySignalCandidatePlanningStatus,
        candidate: OrderCandidate | None = None,
        proposal: RuntimeStrategySignalCandidatePlanningProposal | None = None,
        blockers: list[str] | None = None,
        warnings: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeStrategySignalCandidatePlanningResult:
        return RuntimeStrategySignalCandidatePlanningResult(
            planning_id=f"runtime-signal-candidate-plan-{signal_input.evaluation_id}",
            runtime_instance_id=runtime.runtime_instance_id,
            strategy_family_id=signal_input.strategy_family_id,
            strategy_family_version_id=signal_input.strategy_family_version_id,
            symbol=signal_input.symbol,
            status=status,
            evaluation_result=evaluation,
            candidate=candidate,
            proposal=proposal,
            blockers=_dedupe(blockers or []),
            warnings=_dedupe(warnings or []),
            signal_evaluation_created=candidate is not None,
            order_candidate_created=candidate is not None,
            metadata={
                "source": "runtime_strategy_signal_planning_service",
                "strategy_signal_to_shadow_candidate_planning_v1": True,
                "non_executing": True,
                **(metadata or {}),
            },
        )

    def _required_trusted_market_fact_keys(
        self,
        signal_input: StrategyFamilySignalInput,
        output: StrategyFamilySignalOutput,
    ) -> tuple[str, ...]:
        try:
            binding = self._semantics_catalog.get_binding(
                strategy_family_id=(
                    output.strategy_family_id
                    or signal_input.strategy_family_id
                ),
                strategy_family_version_id=(
                    output.strategy_family_version_id
                    or signal_input.strategy_family_version_id
                ),
            )
        except KeyError:
            return ()
        return tuple(
            fact.fact_key
            for fact in binding.required_facts
            if fact.fact_key in TRUSTED_MARKET_FACT_KEYS
        )

    async def plan_strategy_signal_pair(
        self,
        signal_input: StrategyFamilySignalInput,
        output: StrategyFamilySignalOutput,
        *,
        runtime: StrategyRuntimeInstance,
        owner_reviewed: bool = True,
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
        owner_reviewed: bool = True,
        owner_confirmed_for_intent: bool = True,
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
        owner_reviewed: bool = True,
        owner_confirmed_for_intent: bool = True,
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
        planning_service = self._runtime_execution_planning_service
        return await planning_service.record_intent_draft_for_order_candidate(
            order_candidate_id=candidate.order_candidate_id,
            owner_reviewed=owner_reviewed,
            owner_confirmed_for_intent=owner_confirmed_for_intent,
        )


def _build_candidate_planning_proposal(
    signal_input: StrategyFamilySignalInput,
    output: StrategyFamilySignalOutput,
    *,
    runtime: StrategyRuntimeInstance,
) -> RuntimeStrategySignalCandidatePlanningProposal:
    blockers = _runtime_boundary_blockers(signal_input, output, runtime=runtime)
    if blockers:
        raise RuntimeStrategySignalPlanningError(",".join(blockers))

    entry_price = _entry_price_reference(signal_input, output)
    if entry_price is None or entry_price <= Decimal("0"):
        raise RuntimeStrategySignalPlanningError("entry_price_reference_unavailable")
    stop_price, stop_source = _stop_price_reference(
        signal_input,
        output,
        entry_price=entry_price,
    )
    risk_per_unit = _risk_per_unit(output.side, entry=entry_price, stop=stop_price)
    if risk_per_unit <= Decimal("0"):
        raise RuntimeStrategySignalPlanningError("structure_stop_not_loss_bounding")

    boundary = runtime.boundary
    max_notional = boundary.max_notional_per_attempt
    max_leverage = boundary.max_leverage
    loss_budget = boundary.budget_remaining
    if max_notional is None:
        raise RuntimeStrategySignalPlanningError("runtime_max_notional_per_attempt_missing")
    if max_leverage is None or max_leverage <= Decimal("0"):
        raise RuntimeStrategySignalPlanningError("runtime_max_leverage_missing")
    if loss_budget is None or loss_budget <= Decimal("0"):
        raise RuntimeStrategySignalPlanningError("runtime_loss_budget_unavailable")

    leverage = min(max_leverage, Decimal("1"))
    intended_notional = max_notional
    if boundary.max_margin_per_attempt is not None:
        intended_notional = min(
            intended_notional,
            boundary.max_margin_per_attempt * leverage,
        )
    if signal_input.account_facts_snapshot.available_balance is not None:
        intended_notional = min(
            intended_notional,
            signal_input.account_facts_snapshot.available_balance * leverage,
        )
    if intended_notional <= Decimal("0"):
        raise RuntimeStrategySignalPlanningError("runtime_notional_budget_unavailable")

    proposed_quantity = _quantize(intended_notional / entry_price)
    max_loss_reference = _quantize_money(risk_per_unit * proposed_quantity)
    if max_loss_reference > loss_budget:
        raise RuntimeStrategySignalPlanningError("runtime_loss_budget_insufficient")
    margin_required = _quantize_money(intended_notional / leverage)
    available_balance = signal_input.account_facts_snapshot.available_balance
    if available_balance is None or margin_required > available_balance:
        raise RuntimeStrategySignalPlanningError("trusted_account_balance_insufficient")

    liquidation_price_reference = _estimated_liquidation_price_reference(
        output.side,
        entry=entry_price,
        leverage=leverage,
    )
    liquidation_stop_buffer = _directional_liquidation_stop_buffer(
        output.side,
        liquidation=liquidation_price_reference,
        stop=stop_price,
    )
    take_profit_references = _take_profit_references(
        output.side,
        entry=entry_price,
        risk_per_unit=risk_per_unit,
        atr=signal_input.market_snapshot.atr,
    )
    return RuntimeStrategySignalCandidatePlanningProposal(
        entry_price_reference=entry_price,
        stop_price_reference=stop_price,
        stop_source=stop_source,
        proposed_quantity=proposed_quantity,
        intended_notional=intended_notional,
        max_loss_reference=max_loss_reference,
        leverage=leverage,
        margin_required=margin_required,
        liquidation_price_reference=liquidation_price_reference,
        liquidation_stop_buffer=liquidation_stop_buffer,
        take_profit_references=take_profit_references,
        metadata={
            "proposal_scope": "shadow_candidate_planning_only",
            "strategy_family_id": output.strategy_family_id,
            "strategy_family_version_id": output.strategy_family_version_id,
            "right_tail_exit_shape": "tp1_1r_partial_plus_runner_trailing_metadata",
            "small_bounded_losses_allowed": True,
            "not_proven_alpha": True,
            "liquidation_reference_source": "conservative_leverage_based_estimate",
        },
    )


def _runtime_boundary_blockers(
    signal_input: StrategyFamilySignalInput,
    output: StrategyFamilySignalOutput,
    *,
    runtime: StrategyRuntimeInstance,
) -> list[str]:
    blockers: list[str] = []
    if runtime.strategy_family_id != output.strategy_family_id:
        blockers.append("runtime_strategy_family_mismatch")
    if runtime.strategy_family_version_id != output.strategy_family_version_id:
        blockers.append("runtime_strategy_family_version_mismatch")
    if runtime.symbol != output.symbol or runtime.symbol != signal_input.symbol:
        blockers.append("runtime_symbol_mismatch")
    if runtime.side != output.side.value:
        blockers.append("runtime_side_mismatch")
    if runtime.attempts_remaining <= 0:
        blockers.append("runtime_attempts_exhausted")
    if runtime.boundary.max_notional_per_attempt is None:
        blockers.append("runtime_max_notional_per_attempt_missing")
    if runtime.boundary.max_leverage is None:
        blockers.append("runtime_max_leverage_missing")
    if runtime.budget_remaining is None:
        blockers.append("runtime_loss_budget_unavailable")

    active_positions_count = _active_positions_count(signal_input)
    if active_positions_count is None:
        blockers.append("trusted_active_positions_count_missing")
    elif active_positions_count >= runtime.boundary.max_active_positions:
        blockers.append("runtime_active_position_limit_reached")

    account = signal_input.account_facts_snapshot
    if account.source == "unavailable" or account.account_status != "normal":
        blockers.append("trusted_account_facts_not_ready")
    if account.available_balance is None:
        blockers.append("trusted_account_available_balance_missing")

    if output.strategy_family_id in {"CPM-001", "CPM-RO-001"} and output.side != SignalSide.LONG:
        blockers.append("cpm_long_only_semantics_mismatch")
    if output.strategy_family_id == "BRF-001" and output.side != SignalSide.SHORT:
        blockers.append("brf_short_only_semantics_mismatch")
    return blockers


def _entry_price_reference(
    signal_input: StrategyFamilySignalInput,
    output: StrategyFamilySignalOutput,
) -> Decimal | None:
    evidence = output.evidence_payload
    for value in (
        _nested(evidence, "candidate_semantics", "entry", "entry_price_reference"),
        evidence.get("latest_1h_close"),
        evidence.get("latest_close"),
        _nested(evidence, "price_action_structure", "latest_close"),
        signal_input.market_snapshot.mark_price,
        signal_input.market_snapshot.last_price,
    ):
        decimal_value = _decimal_or_none(value)
        if decimal_value is not None:
            return decimal_value
    return None


def _stop_price_reference(
    signal_input: StrategyFamilySignalInput,
    output: StrategyFamilySignalOutput,
    *,
    entry_price: Decimal,
) -> tuple[Decimal, str]:
    evidence = output.evidence_payload
    atr = signal_input.market_snapshot.atr
    if output.strategy_family_id in {"CPM-001", "CPM-RO-001"} and output.side == SignalSide.LONG:
        structure_stop = _decimal_or_none(evidence.get("lookback_low"))
        if structure_stop is not None:
            return structure_stop, "cpm_pullback_low"
        if atr is not None and atr > Decimal("0"):
            return entry_price - atr, "cpm_atr_reference"
    if output.strategy_family_id == "BRF-001" and output.side == SignalSide.SHORT:
        structure_stop = _decimal_or_none(
            _nested(evidence, "price_action_structure", "rally_high_reference")
        )
        if structure_stop is not None:
            return structure_stop, "brf_rally_high"
        if atr is not None and atr > Decimal("0"):
            return entry_price + atr, "brf_atr_reference"
    semantics_stop = _decimal_or_none(
        _nested(evidence, "candidate_semantics", "protection", "stop_price_reference")
    )
    if semantics_stop is not None:
        return semantics_stop, "strategy_semantics_protection"
    raise RuntimeStrategySignalPlanningError("strategy_stop_reference_unavailable")


def _take_profit_references(
    side: SignalSide,
    *,
    entry: Decimal,
    risk_per_unit: Decimal,
    atr: Decimal | None,
) -> list[dict[str, Any]]:
    if side == SignalSide.SHORT:
        tp1 = entry - risk_per_unit
    else:
        tp1 = entry + risk_per_unit
    return [
        {
            "kind": "tp1_partial",
            "rr": "1",
            "price_reference": str(_quantize_money(tp1)),
            "position_ratio": "0.5",
            "purpose": "recover_small_loss_attempts_without_capping_runner",
            "non_executing_preview": True,
        },
        {
            "kind": "runner",
            "policy": "trailing_atr_or_structure_invalidation",
            "atr_reference": str(atr) if atr is not None else None,
            "right_tail_capture": True,
            "non_executing_preview": True,
        },
    ]


def _risk_per_unit(side: SignalSide, *, entry: Decimal, stop: Decimal) -> Decimal:
    if side == SignalSide.SHORT:
        return stop - entry
    return entry - stop


def _estimated_liquidation_price_reference(
    side: SignalSide,
    *,
    entry: Decimal,
    leverage: Decimal,
) -> Decimal | None:
    if leverage <= Decimal("0"):
        return None
    if side == SignalSide.SHORT:
        return _quantize_money(entry + (entry / leverage))
    return _quantize_money(max(Decimal("0"), entry - (entry / leverage)))


def _directional_liquidation_stop_buffer(
    side: SignalSide,
    *,
    liquidation: Decimal | None,
    stop: Decimal,
) -> Decimal | None:
    if liquidation is None:
        return None
    if side == SignalSide.SHORT:
        return _quantize_money(liquidation - stop)
    return _quantize_money(stop - liquidation)


def _active_positions_count(signal_input: StrategyFamilySignalInput) -> int | None:
    summary = signal_input.position_open_order_summary or {}
    for key in ("active_positions_count", "position_count"):
        if key in summary and summary[key] is not None:
            return int(summary[key])
    return None


def _nested(value: dict[str, Any], *keys: str) -> Any:
    cursor: Any = value
    for key in keys:
        if not isinstance(cursor, dict) or key not in cursor:
            return None
        cursor = cursor[key]
    return cursor


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.00000001"))


def _quantize_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.00000001"))


def _dedupe(values: list[str]) -> list[str]:
    return sorted(dict.fromkeys(values))
