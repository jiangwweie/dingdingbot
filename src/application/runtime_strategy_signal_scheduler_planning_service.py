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
    ) -> None:
        self._planner = planner
        self._semantics_catalog = semantics_catalog or initial_strategy_semantics_catalog()
        self._fact_sources = fact_sources or RuntimeStrategySignalSchedulerFactSources()

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
        if readiness.status == RuntimeStrategySignalSchedulerReadinessStatus.OBSERVE_ONLY:
            return self._result(
                signal_input,
                runtime=runtime,
                readiness=readiness,
                status=RuntimeStrategySignalSchedulerPlanningStatus.OBSERVE_ONLY,
                blockers=readiness.blockers,
                warnings=readiness.warnings,
                metadata={
                    "planner_call_suppressed_reason": "scheduler_readiness_observe_only",
                },
            )
        if (
            readiness.status
            != RuntimeStrategySignalSchedulerReadinessStatus.READY_FOR_NON_EXECUTING_PLANNER
        ):
            return self._result(
                signal_input,
                runtime=runtime,
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
