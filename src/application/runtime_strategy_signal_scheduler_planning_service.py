"""Explicit scheduler handoff into shadow runtime strategy planning.

This service is the non-executing bridge after scheduler readiness. It keeps
``RuntimeStrategySignalSchedulerAssemblyService`` read-only, then calls the B0
shadow planner only when a caller explicitly enables shadow candidate creation.

It does not create ExecutionIntent records, orders, OrderLifecycle calls, or
exchange requests.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from src.application.runtime_strategy_signal_evaluation_service import (
    RuntimeStrategySignalEvaluationResult,
    RuntimeStrategySignalEvaluationService,
    RuntimeStrategySignalEvaluationStatus,
)
from src.application.runtime_strategy_signal_planning_service import (
    RuntimeStrategySignalCandidatePlanningResult,
    RuntimeStrategySignalCandidatePlanningStatus,
)
from src.application.runtime_strategy_signal_scheduler_assembly import (
    RuntimeStrategySignalSchedulerAssemblyService,
    RuntimeStrategySignalSchedulerFactSources,
    RuntimeStrategySignalSchedulerReadiness,
    RuntimeStrategySignalSchedulerReadinessStatus,
)
from src.application.strategy_evaluation_context_builder import (
    StrategyEvaluationContextBuilder,
)
from src.domain.strategy_family_signal import (
    StrategyFamilySignalInput,
    StrategyFamilySignalOutput,
)
from src.domain.strategy_runtime import StrategyRuntimeInstance
from src.domain.strategy_semantics import (
    StrategySemanticsCatalog,
    initial_strategy_semantics_catalog,
)


class RuntimeStrategySignalShadowPlanner(Protocol):
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
        ...


class RuntimeStrategySignalSchedulerPlanningStatus(str, Enum):
    BLOCKED = "blocked"
    OBSERVE_ONLY = "observe_only"
    EXPLICIT_ENABLE_REQUIRED = "explicit_enable_required"
    PLANNER_BLOCKED = "planner_blocked"
    SHADOW_CANDIDATE_CREATED = "shadow_candidate_created"


class RuntimeStrategySignalSchedulerPlanningResult(BaseModel):
    """Scheduler-level result for an explicit non-executing planner handoff."""

    model_config = ConfigDict(extra="forbid")

    planning_id: str = Field(min_length=1, max_length=180)
    runtime_instance_id: str | None = Field(default=None, max_length=128)
    strategy_family_id: str = Field(min_length=1, max_length=128)
    strategy_family_version_id: str = Field(min_length=1, max_length=128)
    symbol: str = Field(min_length=1, max_length=128)
    status: RuntimeStrategySignalSchedulerPlanningStatus
    evaluation_result: RuntimeStrategySignalEvaluationResult | None = None
    readiness: RuntimeStrategySignalSchedulerReadiness
    candidate_planning_result: RuntimeStrategySignalCandidatePlanningResult | None = None
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    planner_call_performed: bool = False
    signal_evaluation_created: bool = False
    order_candidate_created: bool = False
    execution_intent_created: Literal[False] = False
    order_created: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    exchange_called: Literal[False] = False
    not_order: Literal[True] = True
    not_execution_intent: Literal[True] = True
    not_execution_authority: Literal[True] = True
    metadata: dict = Field(default_factory=dict)


class RuntimeStrategySignalSchedulerPlanningService:
    """Gate scheduler-ready signals before calling the shadow planner."""

    def __init__(
        self,
        *,
        planner: RuntimeStrategySignalShadowPlanner,
        semantics_catalog: StrategySemanticsCatalog | None = None,
        fact_sources: RuntimeStrategySignalSchedulerFactSources | None = None,
        signal_evaluation_service: RuntimeStrategySignalEvaluationService | None = None,
    ) -> None:
        self._planner = planner
        self._semantics_catalog = semantics_catalog or initial_strategy_semantics_catalog()
        self._fact_sources = fact_sources or RuntimeStrategySignalSchedulerFactSources()
        self._signal_evaluation_service = signal_evaluation_service or (
            RuntimeStrategySignalEvaluationService(catalog=self._semantics_catalog)
        )

    async def plan_signal_input_if_ready(
        self,
        signal_input: StrategyFamilySignalInput,
        *,
        runtime: StrategyRuntimeInstance,
        candidate_id: str | None = None,
        allow_shadow_candidate_creation: bool = False,
        fact_sources: RuntimeStrategySignalSchedulerFactSources | None = None,
        context_builder: StrategyEvaluationContextBuilder | None = None,
        context_id: str | None = None,
        expires_at_ms: int | None = None,
        metadata: dict | None = None,
    ) -> RuntimeStrategySignalSchedulerPlanningResult:
        evaluation = self._signal_evaluation_service.evaluate(signal_input)
        if (
            evaluation.status
            != RuntimeStrategySignalEvaluationStatus.READY_FOR_SEMANTIC_BINDING
            or evaluation.output is None
        ):
            readiness = _readiness_from_evaluation(
                signal_input,
                evaluation,
                runtime=runtime,
                fact_sources=fact_sources or self._fact_sources,
                candidate_id=candidate_id,
            )
            return self._result(
                signal_input,
                runtime=runtime,
                evaluation_result=evaluation,
                readiness=readiness,
                status=(
                    RuntimeStrategySignalSchedulerPlanningStatus.OBSERVE_ONLY
                    if evaluation.status
                    == RuntimeStrategySignalEvaluationStatus.OBSERVE_ONLY
                    else RuntimeStrategySignalSchedulerPlanningStatus.BLOCKED
                ),
                blockers=evaluation.blockers,
                warnings=evaluation.warnings,
                metadata={
                    "planner_call_suppressed_reason": "evaluation_gate_not_ready",
                    "server_side_evaluation_performed": True,
                    **(metadata or {}),
                },
            )

        return await self.plan_if_ready(
            signal_input,
            evaluation.output,
            runtime=runtime,
            candidate_id=candidate_id,
            allow_shadow_candidate_creation=allow_shadow_candidate_creation,
            fact_sources=fact_sources,
            context_builder=context_builder,
            context_id=context_id,
            expires_at_ms=expires_at_ms,
            metadata={
                "server_side_evaluation_performed": True,
                **(metadata or {}),
            },
            evaluation_result=evaluation,
        )

    async def plan_if_ready(
        self,
        signal_input: StrategyFamilySignalInput,
        output: StrategyFamilySignalOutput,
        *,
        runtime: StrategyRuntimeInstance,
        candidate_id: str | None = None,
        allow_shadow_candidate_creation: bool = False,
        fact_sources: RuntimeStrategySignalSchedulerFactSources | None = None,
        context_builder: StrategyEvaluationContextBuilder | None = None,
        context_id: str | None = None,
        expires_at_ms: int | None = None,
        metadata: dict | None = None,
        evaluation_result: RuntimeStrategySignalEvaluationResult | None = None,
    ) -> RuntimeStrategySignalSchedulerPlanningResult:
        readiness = RuntimeStrategySignalSchedulerAssemblyService(
            semantics_catalog=self._semantics_catalog,
            runtime=runtime,
            fact_sources=fact_sources or self._fact_sources,
        ).preview(
            signal_input,
            output,
            candidate_id=candidate_id,
        )
        if readiness.status in {
            RuntimeStrategySignalSchedulerReadinessStatus.OBSERVE_ONLY,
            RuntimeStrategySignalSchedulerReadinessStatus.LIVE_RUNTIME_HANDOFF_PENDING,
        }:
            suppressed_reason = (
                "operation_layer_handoff_pending"
                if readiness.status
                == RuntimeStrategySignalSchedulerReadinessStatus.LIVE_RUNTIME_HANDOFF_PENDING
                else "scheduler_readiness_observe_only"
            )
            return self._result(
                signal_input,
                runtime=runtime,
                evaluation_result=evaluation_result,
                readiness=readiness,
                status=RuntimeStrategySignalSchedulerPlanningStatus.OBSERVE_ONLY,
                blockers=readiness.blockers,
                warnings=readiness.warnings,
                metadata={
                    "planner_call_suppressed_reason": suppressed_reason,
                },
            )
        if (
            readiness.status
            != RuntimeStrategySignalSchedulerReadinessStatus.READY_FOR_NON_EXECUTING_PLANNER
        ):
            return self._result(
                signal_input,
                runtime=runtime,
                evaluation_result=evaluation_result,
                readiness=readiness,
                status=RuntimeStrategySignalSchedulerPlanningStatus.BLOCKED,
                blockers=readiness.blockers,
                warnings=readiness.warnings,
                metadata={
                    "planner_call_suppressed_reason": "scheduler_readiness_blocked",
                },
            )
        if not allow_shadow_candidate_creation:
            return self._result(
                signal_input,
                runtime=runtime,
                evaluation_result=evaluation_result,
                readiness=readiness,
                status=RuntimeStrategySignalSchedulerPlanningStatus.EXPLICIT_ENABLE_REQUIRED,
                blockers=["shadow_candidate_creation_not_explicitly_enabled"],
                warnings=readiness.warnings,
                metadata={
                    "planner_call_suppressed_reason": "explicit_enable_required",
                },
            )

        planning = await self._planner.plan_shadow_candidate_from_signal_input(
            signal_input,
            runtime=runtime,
            context_builder=context_builder,
            context_id=context_id,
            expires_at_ms=expires_at_ms,
            metadata={
                "scheduler_planning_handoff": True,
                "scheduler_candidate_id": candidate_id,
                **(metadata or {}),
            },
        )
        status = (
            RuntimeStrategySignalSchedulerPlanningStatus.SHADOW_CANDIDATE_CREATED
            if planning.status
            == RuntimeStrategySignalCandidatePlanningStatus.SHADOW_CANDIDATE_CREATED
            else RuntimeStrategySignalSchedulerPlanningStatus.OBSERVE_ONLY
            if planning.status == RuntimeStrategySignalCandidatePlanningStatus.OBSERVE_ONLY
            else RuntimeStrategySignalSchedulerPlanningStatus.PLANNER_BLOCKED
        )
        return self._result(
            signal_input,
            runtime=runtime,
            evaluation_result=evaluation_result,
            readiness=readiness,
            status=status,
            candidate_planning_result=planning,
            blockers=planning.blockers,
            warnings=[*readiness.warnings, *planning.warnings],
            planner_call_performed=True,
            signal_evaluation_created=planning.signal_evaluation_created,
            order_candidate_created=planning.order_candidate_created,
            metadata={
                "planner_call_performed": True,
                "shadow_planner_status": planning.status.value,
            },
        )

    def _result(
        self,
        signal_input: StrategyFamilySignalInput,
        *,
        runtime: StrategyRuntimeInstance,
        evaluation_result: RuntimeStrategySignalEvaluationResult | None = None,
        readiness: RuntimeStrategySignalSchedulerReadiness,
        status: RuntimeStrategySignalSchedulerPlanningStatus,
        candidate_planning_result: RuntimeStrategySignalCandidatePlanningResult | None = None,
        blockers: list[str] | None = None,
        warnings: list[str] | None = None,
        planner_call_performed: bool = False,
        signal_evaluation_created: bool = False,
        order_candidate_created: bool = False,
        metadata: dict | None = None,
    ) -> RuntimeStrategySignalSchedulerPlanningResult:
        return RuntimeStrategySignalSchedulerPlanningResult(
            planning_id=f"scheduler-runtime-signal-plan-{signal_input.evaluation_id}",
            runtime_instance_id=runtime.runtime_instance_id,
            strategy_family_id=signal_input.strategy_family_id,
            strategy_family_version_id=signal_input.strategy_family_version_id,
            symbol=signal_input.symbol,
            status=status,
            evaluation_result=evaluation_result,
            readiness=readiness,
            candidate_planning_result=candidate_planning_result,
            blockers=sorted(dict.fromkeys(blockers or [])),
            warnings=sorted(dict.fromkeys(warnings or [])),
            planner_call_performed=planner_call_performed,
            signal_evaluation_created=signal_evaluation_created,
            order_candidate_created=order_candidate_created,
            metadata={
                "source": "runtime_strategy_signal_scheduler_planning_service",
                "non_executing_scheduler_planner_handoff": True,
                "explicit_shadow_candidate_creation_required": True,
                "does_not_create_execution_intent": True,
                "does_not_call_order_lifecycle": True,
                "does_not_call_exchange": True,
                **(metadata or {}),
            },
        )


def _readiness_from_evaluation(
    signal_input: StrategyFamilySignalInput,
    evaluation: RuntimeStrategySignalEvaluationResult,
    *,
    runtime: StrategyRuntimeInstance,
    fact_sources: RuntimeStrategySignalSchedulerFactSources,
    candidate_id: str | None,
) -> RuntimeStrategySignalSchedulerReadiness:
    output = evaluation.output
    status = (
        RuntimeStrategySignalSchedulerReadinessStatus.OBSERVE_ONLY
        if evaluation.status == RuntimeStrategySignalEvaluationStatus.OBSERVE_ONLY
        else RuntimeStrategySignalSchedulerReadinessStatus.BLOCKED
    )
    return RuntimeStrategySignalSchedulerReadiness(
        candidate_id=candidate_id,
        evaluation_id=signal_input.evaluation_id,
        signal_id=output.signal_id if output is not None else signal_input.evaluation_id,
        strategy_family_id=signal_input.strategy_family_id,
        strategy_family_version_id=signal_input.strategy_family_version_id,
        symbol=signal_input.symbol,
        side=output.side.value if output is not None else "none",
        signal_type=output.signal_type.value if output is not None else "no_output",
        status=status,
        blockers=list(evaluation.blockers),
        warnings=list(evaluation.warnings),
        semantics_binding_found=evaluation.semantics_binding_found,
        strategy_candidate_mode=evaluation.strategy_candidate_mode,
        runtime_instance_id=runtime.runtime_instance_id,
        runtime_bound=True,
        fact_sources=fact_sources,
        scheduler_can_call_runtime_planner=False,
        metadata={
            "source": "runtime_strategy_signal_scheduler_planning_service",
            "server_side_evaluation_gate": True,
            "planner_call_suppressed_reason": "evaluation_gate_not_ready",
            "does_not_call_runtime_planner": True,
            "does_not_create_signal_evaluation": True,
            "does_not_create_order_candidate": True,
            "does_not_create_execution_intent": True,
            "does_not_call_order_lifecycle": True,
            "does_not_call_exchange": True,
        },
    )
