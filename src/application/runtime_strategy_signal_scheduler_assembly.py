"""Scheduler-level readiness for runtime strategy signal planning.

This module is deliberately non-executing. It lets a scheduler or observation
runner explain whether a strategy signal pair is ready to be handed to the
existing B0 runtime signal planner, without actually calling that planner.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.application.runtime_strategy_signal_planning_service import (
    TRUSTED_MARKET_FACT_KEYS,
)
from src.domain.strategy_family_signal import (
    SignalType,
    StrategyFamilySignalInput,
    StrategyFamilySignalOutput,
)
from src.domain.strategy_runtime import (
    StrategyRuntimeInstance,
    StrategyRuntimeInstanceStatus,
)
from src.domain.strategy_semantics import (
    StrategyCandidateMode,
    StrategySemanticsCatalog,
    initial_strategy_semantics_catalog,
)


class RuntimeStrategySignalSchedulerReadinessStatus(str, Enum):
    OBSERVE_ONLY = "observe_only"
    BLOCKED = "blocked"
    READY_FOR_NON_EXECUTING_PLANNER = "ready_for_non_executing_planner"
    LIVE_RUNTIME_HANDOFF_PENDING = "live_runtime_handoff_pending"


class RuntimeStrategySignalSchedulerFactSources(BaseModel):
    """Trusted source availability visible to a scheduler assembly preview."""

    model_config = ConfigDict(extra="forbid")

    trusted_runtime_fact_overlay_configured: bool = False
    trusted_active_position_source_available: bool = False
    trusted_account_facts_source_available: bool = False
    trusted_market_fact_source_available: bool = False
    source_scope: str = Field(default="not_configured", max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeStrategySignalSchedulerReadiness(BaseModel):
    """Non-executing scheduler readiness for one strategy signal pair."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str | None = Field(default=None, max_length=128)
    evaluation_id: str = Field(min_length=1, max_length=128)
    signal_id: str = Field(min_length=1, max_length=128)
    strategy_family_id: str = Field(min_length=1, max_length=128)
    strategy_family_version_id: str = Field(min_length=1, max_length=128)
    symbol: str = Field(min_length=1, max_length=128)
    side: str = Field(min_length=1, max_length=32)
    signal_type: str = Field(min_length=1, max_length=64)
    status: RuntimeStrategySignalSchedulerReadinessStatus
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    semantics_binding_found: bool = False
    strategy_candidate_mode: str | None = Field(default=None, max_length=128)
    runtime_instance_id: str | None = Field(default=None, max_length=128)
    runtime_bound: bool = False
    fact_sources: RuntimeStrategySignalSchedulerFactSources = Field(
        default_factory=RuntimeStrategySignalSchedulerFactSources
    )
    required_trusted_market_fact_keys: list[str] = Field(default_factory=list)
    scheduler_can_call_runtime_planner: bool = False
    planner_call_performed: Literal[False] = False
    signal_evaluation_created: Literal[False] = False
    order_candidate_created: Literal[False] = False
    execution_intent_created: Literal[False] = False
    order_created: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    exchange_called: Literal[False] = False
    not_order: Literal[True] = True
    not_execution_intent: Literal[True] = True
    not_execution_authority: Literal[True] = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeStrategySignalSchedulerAssemblyService:
    """Preview scheduler readiness without creating candidates or intents."""

    def __init__(
        self,
        *,
        semantics_catalog: StrategySemanticsCatalog | None = None,
        runtime: StrategyRuntimeInstance | None = None,
        fact_sources: RuntimeStrategySignalSchedulerFactSources | None = None,
    ) -> None:
        self._semantics_catalog = semantics_catalog or initial_strategy_semantics_catalog()
        self._runtime = runtime
        self._fact_sources = fact_sources or RuntimeStrategySignalSchedulerFactSources()

    def preview(
        self,
        signal_input: StrategyFamilySignalInput,
        output: StrategyFamilySignalOutput,
        *,
        candidate_id: str | None = None,
    ) -> RuntimeStrategySignalSchedulerReadiness:
        blockers: list[str] = []
        warnings: list[str] = []
        semantics_binding_found = False
        strategy_candidate_mode: str | None = None
        required_market_fact_keys: list[str] = []

        try:
            binding = self._semantics_catalog.get_binding(
                strategy_family_id=output.strategy_family_id or signal_input.strategy_family_id,
                strategy_family_version_id=(
                    output.strategy_family_version_id
                    or signal_input.strategy_family_version_id
                ),
            )
            semantics_binding_found = True
            strategy_candidate_mode = binding.candidate_mode.value
            required_market_fact_keys = [
                requirement.fact_key
                for requirement in binding.required_facts
                if requirement.fact_key in TRUSTED_MARKET_FACT_KEYS
            ]
            if binding.candidate_mode != StrategyCandidateMode.SHADOW_ORDER_CANDIDATE_ALLOWED:
                blockers.append(
                    f"strategy_candidate_mode_not_runtime_candidate:{binding.candidate_mode.value}"
                )
            if output.side.value not in binding.supported_sides:
                blockers.append("strategy_side_not_supported_by_semantics")
        except KeyError:
            blockers.append("strategy_semantics_binding_missing")

        if output.signal_type != SignalType.WOULD_ENTER:
            blockers.append("strategy_signal_not_would_enter")
            status = RuntimeStrategySignalSchedulerReadinessStatus.OBSERVE_ONLY
        elif self._runtime_is_live_operation_layer_handoff(output):
            status = (
                RuntimeStrategySignalSchedulerReadinessStatus.LIVE_RUNTIME_HANDOFF_PENDING
            )
            warnings.append("runtime_live_execution_enabled_operation_layer_handoff")
        else:
            status = RuntimeStrategySignalSchedulerReadinessStatus.BLOCKED
            self._append_runtime_blockers(signal_input, output, blockers)
            self._append_fact_source_blockers(required_market_fact_keys, blockers, warnings)
            if not blockers:
                status = (
                    RuntimeStrategySignalSchedulerReadinessStatus.READY_FOR_NON_EXECUTING_PLANNER
                )

        return RuntimeStrategySignalSchedulerReadiness(
            candidate_id=candidate_id,
            evaluation_id=signal_input.evaluation_id,
            signal_id=output.signal_id,
            strategy_family_id=output.strategy_family_id or signal_input.strategy_family_id,
            strategy_family_version_id=(
                output.strategy_family_version_id
                or signal_input.strategy_family_version_id
            ),
            symbol=output.symbol or signal_input.symbol,
            side=output.side.value,
            signal_type=output.signal_type.value,
            status=status,
            blockers=sorted(dict.fromkeys(blockers)),
            warnings=sorted(dict.fromkeys(warnings)),
            semantics_binding_found=semantics_binding_found,
            strategy_candidate_mode=strategy_candidate_mode,
            runtime_instance_id=(
                self._runtime.runtime_instance_id if self._runtime is not None else None
            ),
            runtime_bound=self._runtime is not None,
            fact_sources=self._fact_sources,
            required_trusted_market_fact_keys=required_market_fact_keys,
            scheduler_can_call_runtime_planner=(
                status
                == RuntimeStrategySignalSchedulerReadinessStatus.READY_FOR_NON_EXECUTING_PLANNER
            ),
            metadata={
                "source": "runtime_strategy_signal_scheduler_assembly",
                "non_executing_scheduler_readiness": True,
                "does_not_call_runtime_planner": True,
                "does_not_create_signal_evaluation": True,
                "does_not_create_order_candidate": True,
                "does_not_create_execution_intent": True,
                "does_not_call_order_lifecycle": True,
                "does_not_call_exchange": True,
            },
        )

    def _append_runtime_blockers(
        self,
        signal_input: StrategyFamilySignalInput,
        output: StrategyFamilySignalOutput,
        blockers: list[str],
    ) -> None:
        runtime = self._runtime
        if runtime is None:
            blockers.append("runtime_instance_required_for_scheduler_planning")
            return
        if runtime.status != StrategyRuntimeInstanceStatus.ACTIVE:
            blockers.append("runtime_instance_not_active")
        if runtime.strategy_family_id != output.strategy_family_id:
            blockers.append("runtime_strategy_family_mismatch")
        if runtime.strategy_family_version_id != output.strategy_family_version_id:
            blockers.append("runtime_strategy_family_version_mismatch")
        if runtime.symbol != output.symbol:
            blockers.append("runtime_symbol_mismatch")
        if runtime.side != output.side.value:
            blockers.append("runtime_side_mismatch")
        if not runtime.shadow_mode:
            blockers.append("runtime_shadow_mode_required_for_b0_scheduler_planning")
        if runtime.execution_enabled:
            blockers.append("runtime_execution_enabled_not_allowed_for_b0_scheduler_planning")
        if signal_input.symbol != output.symbol:
            blockers.append("signal_input_output_symbol_mismatch")

    def _append_fact_source_blockers(
        self,
        required_market_fact_keys: list[str],
        blockers: list[str],
        warnings: list[str],
    ) -> None:
        sources = self._fact_sources
        if not sources.trusted_runtime_fact_overlay_configured:
            blockers.append("trusted_runtime_fact_overlay_not_configured")
        if not sources.trusted_active_position_source_available:
            blockers.append("trusted_active_position_source_unavailable")
        if not sources.trusted_account_facts_source_available:
            blockers.append("trusted_account_facts_source_unavailable")
        if required_market_fact_keys and not sources.trusted_market_fact_source_available:
            blockers.append("trusted_market_fact_source_required_by_strategy_unavailable")
        if (
            not required_market_fact_keys
            and not sources.trusted_market_fact_source_available
        ):
            warnings.append("trusted_market_fact_source_not_configured_optional_only")

    def _runtime_is_live_operation_layer_handoff(
        self,
        output: StrategyFamilySignalOutput,
    ) -> bool:
        runtime = self._runtime
        if runtime is None:
            return False
        return (
            runtime.status == StrategyRuntimeInstanceStatus.ACTIVE
            and runtime.strategy_family_id == output.strategy_family_id
            and runtime.strategy_family_version_id == output.strategy_family_version_id
            and runtime.symbol == output.symbol
            and runtime.side == output.side.value
            and runtime.shadow_mode is False
            and runtime.execution_enabled is True
        )
