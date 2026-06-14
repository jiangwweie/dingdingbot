"""Evaluate runtime strategy-family signals behind the B0 semantics gate.

This application service is intentionally non-executing. It routes a
StrategyFamilySignalInput to a configured pure evaluator, verifies the evaluator
output against the StrategyImplementation binding, and reports whether the
output may continue toward the existing shadow semantics binding path.

It does not create SignalEvaluation rows, OrderCandidates, ExecutionIntents,
orders, OrderLifecycle calls, or exchange requests.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from src.domain.brf_price_action_evaluator import BRF001PriceActionEvaluator
from src.domain.cpm_historical_evaluator import CPM_FAMILY_ID, CPMRO001HistoricalEvaluator
from src.domain.mpg_momentum_persistence_evaluator import (
    MPG001MomentumPersistenceEvaluator,
)
from src.domain.reference_price_action_evaluators import (
    BTPC001PriceActionEvaluator,
    LSR001PriceActionEvaluator,
    RBR001PriceActionEvaluator,
    VCB001PriceActionEvaluator,
)
from src.domain.strategy_family_signal import (
    SignalSide,
    SignalType,
    StrategyFamilySignalInput,
    StrategyFamilySignalOutput,
)
from src.domain.strategy_semantics import (
    StrategyCandidateMode,
    StrategySemanticsCatalog,
    initial_strategy_semantics_catalog,
)


class RuntimeStrategySignalEvaluationStatus(str, Enum):
    READY_FOR_SEMANTIC_BINDING = "ready_for_semantic_binding"
    OBSERVE_ONLY = "observe_only"
    BLOCKED = "blocked"


class RuntimeStrategySignalEvaluator(Protocol):
    def evaluate(
        self,
        signal_input: StrategyFamilySignalInput,
    ) -> StrategyFamilySignalOutput:
        ...


class RuntimeStrategySignalEvaluationResult(BaseModel):
    """Non-executing evaluator route result for one strategy signal input."""

    model_config = ConfigDict(extra="forbid")

    evaluation_id: str = Field(min_length=1, max_length=128)
    strategy_family_id: str = Field(min_length=1, max_length=128)
    strategy_family_version_id: str = Field(min_length=1, max_length=128)
    symbol: str = Field(min_length=1, max_length=128)
    status: RuntimeStrategySignalEvaluationStatus
    output: StrategyFamilySignalOutput | None = None
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    semantics_binding_found: bool = False
    strategy_candidate_mode: str | None = Field(default=None, max_length=128)
    runtime_confirmation_mode: str | None = Field(default=None, max_length=128)
    evaluator_id: str | None = Field(default=None, max_length=128)
    evaluator_called: bool = False
    can_call_semantic_binding: bool = False
    signal_evaluation_created: Literal[False] = False
    order_candidate_created: Literal[False] = False
    execution_intent_created: Literal[False] = False
    order_created: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    exchange_called: Literal[False] = False
    not_order: Literal[True] = True
    not_execution_intent: Literal[True] = True
    not_execution_authority: Literal[True] = True
    metadata: dict = Field(default_factory=dict)


class RuntimeStrategySignalEvaluationService:
    """Route strategy signal inputs to pure evaluators behind semantics checks."""

    def __init__(
        self,
        *,
        catalog: StrategySemanticsCatalog | None = None,
        evaluators: dict[tuple[str, str], RuntimeStrategySignalEvaluator] | None = None,
    ) -> None:
        self._catalog = catalog or initial_strategy_semantics_catalog()
        self._evaluators = evaluators or _default_evaluators()

    def evaluate(
        self,
        signal_input: StrategyFamilySignalInput,
    ) -> RuntimeStrategySignalEvaluationResult:
        blockers: list[str] = []
        warnings: list[str] = []
        binding = None
        output: StrategyFamilySignalOutput | None = None
        evaluator_id: str | None = None
        evaluator_called = False

        try:
            binding = self._catalog.get_binding(
                strategy_family_id=signal_input.strategy_family_id,
                strategy_family_version_id=signal_input.strategy_family_version_id,
            )
        except KeyError:
            blockers.append("strategy_semantics_binding_missing")
            return self._result(
                signal_input,
                status=RuntimeStrategySignalEvaluationStatus.BLOCKED,
                output=None,
                blockers=blockers,
                warnings=warnings,
            )

        if binding.candidate_mode != StrategyCandidateMode.SHADOW_ORDER_CANDIDATE_ALLOWED:
            status = (
                RuntimeStrategySignalEvaluationStatus.OBSERVE_ONLY
                if binding.candidate_mode == StrategyCandidateMode.REGIME_CLASSIFIER_ONLY
                else RuntimeStrategySignalEvaluationStatus.BLOCKED
            )
            blockers.append(
                f"strategy_candidate_mode_not_runtime_candidate:{binding.candidate_mode.value}"
            )
            return self._result(
                signal_input,
                status=status,
                output=None,
                blockers=blockers,
                warnings=warnings,
                semantics_binding_found=True,
                strategy_candidate_mode=binding.candidate_mode.value,
                runtime_confirmation_mode=binding.runtime_confirmation_mode.value,
            )

        evaluator_key = (
            binding.strategy_family_id,
            binding.strategy_family_version_id,
        )
        evaluator = self._evaluators.get(evaluator_key)
        if evaluator is None:
            blockers.append("strategy_evaluator_not_configured")
            return self._result(
                signal_input,
                status=RuntimeStrategySignalEvaluationStatus.BLOCKED,
                output=None,
                blockers=blockers,
                warnings=warnings,
                semantics_binding_found=True,
                strategy_candidate_mode=binding.candidate_mode.value,
                runtime_confirmation_mode=binding.runtime_confirmation_mode.value,
            )

        evaluator_id = evaluator.__class__.__name__
        output = evaluator.evaluate(signal_input)
        evaluator_called = True
        blockers.extend(_output_mismatches(signal_input, output))

        if output.signal_type == SignalType.INVALID:
            blockers.append("strategy_evaluator_output_invalid")
            status = RuntimeStrategySignalEvaluationStatus.BLOCKED
        elif output.signal_type != SignalType.WOULD_ENTER:
            blockers.append("strategy_signal_not_would_enter")
            status = RuntimeStrategySignalEvaluationStatus.OBSERVE_ONLY
        elif output.side == SignalSide.NONE:
            blockers.append("strategy_output_missing_entry_side")
            status = RuntimeStrategySignalEvaluationStatus.BLOCKED
        elif output.side.value not in binding.supported_sides:
            blockers.append("strategy_output_side_not_supported_by_semantics")
            status = RuntimeStrategySignalEvaluationStatus.BLOCKED
        elif blockers:
            status = RuntimeStrategySignalEvaluationStatus.BLOCKED
        else:
            status = RuntimeStrategySignalEvaluationStatus.READY_FOR_SEMANTIC_BINDING

        return self._result(
            signal_input,
            status=status,
            output=output,
            blockers=blockers,
            warnings=warnings,
            semantics_binding_found=True,
            strategy_candidate_mode=binding.candidate_mode.value,
            runtime_confirmation_mode=binding.runtime_confirmation_mode.value,
            evaluator_id=evaluator_id,
            evaluator_called=evaluator_called,
            can_call_semantic_binding=(
                status
                == RuntimeStrategySignalEvaluationStatus.READY_FOR_SEMANTIC_BINDING
            ),
        )

    def route_configured(
        self,
        *,
        strategy_family_id: str,
        strategy_family_version_id: str,
    ) -> bool:
        return (
            strategy_family_id,
            strategy_family_version_id,
        ) in self._evaluators

    def _result(
        self,
        signal_input: StrategyFamilySignalInput,
        *,
        status: RuntimeStrategySignalEvaluationStatus,
        output: StrategyFamilySignalOutput | None,
        blockers: list[str],
        warnings: list[str],
        semantics_binding_found: bool = False,
        strategy_candidate_mode: str | None = None,
        runtime_confirmation_mode: str | None = None,
        evaluator_id: str | None = None,
        evaluator_called: bool = False,
        can_call_semantic_binding: bool = False,
    ) -> RuntimeStrategySignalEvaluationResult:
        return RuntimeStrategySignalEvaluationResult(
            evaluation_id=signal_input.evaluation_id,
            strategy_family_id=signal_input.strategy_family_id,
            strategy_family_version_id=signal_input.strategy_family_version_id,
            symbol=signal_input.symbol,
            status=status,
            output=output,
            blockers=_dedupe(blockers),
            warnings=_dedupe(warnings),
            semantics_binding_found=semantics_binding_found,
            strategy_candidate_mode=strategy_candidate_mode,
            runtime_confirmation_mode=runtime_confirmation_mode,
            evaluator_id=evaluator_id,
            evaluator_called=evaluator_called,
            can_call_semantic_binding=can_call_semantic_binding,
            metadata={
                "source": "runtime_strategy_signal_evaluation_service",
                "non_executing_evaluator_route": True,
                "does_not_create_signal_evaluation": True,
                "does_not_create_order_candidate": True,
                "does_not_create_execution_intent": True,
                "does_not_call_order_lifecycle": True,
                "does_not_call_exchange": True,
            },
        )


def _default_evaluators() -> dict[tuple[str, str], RuntimeStrategySignalEvaluator]:
    return {
        ("CPM-RO-001", "CPM-RO-001-v0"): CPMRO001HistoricalEvaluator(),
        ("CPM-001", "CPM-001-v0"): _CPM001LiveReferenceEvaluator(),
        ("MPG-001", "MPG-001-v0"): MPG001MomentumPersistenceEvaluator(),
        ("BRF-001", "BRF-001-v0"): BRF001PriceActionEvaluator(),
        ("BTPC-001", "BTPC-001-v0"): BTPC001PriceActionEvaluator(),
        ("LSR-001", "LSR-001-v0"): LSR001PriceActionEvaluator(),
        ("RBR-001", "RBR-001-v0"): RBR001PriceActionEvaluator(),
        ("VCB-001", "VCB-001-v0"): VCB001PriceActionEvaluator(),
    }


class _CPM001LiveReferenceEvaluator:
    """Route CPM-001 live-reference inputs through the CPM price-action evaluator."""

    def __init__(self, delegate: CPMRO001HistoricalEvaluator | None = None) -> None:
        self._delegate = delegate or CPMRO001HistoricalEvaluator()

    def evaluate(
        self,
        signal_input: StrategyFamilySignalInput,
    ) -> StrategyFamilySignalOutput:
        mapped_input = signal_input.model_copy(
            update={
                "strategy_family_id": CPM_FAMILY_ID,
                "strategy_family_version_id": "CPM-RO-001-v0",
            },
            deep=True,
        )
        output = self._delegate.evaluate(mapped_input)
        return _retarget_cpm_reference_output(
            output,
            strategy_family_id=signal_input.strategy_family_id,
            strategy_family_version_id=signal_input.strategy_family_version_id,
        )


def _retarget_cpm_reference_output(
    output: StrategyFamilySignalOutput,
    *,
    strategy_family_id: str,
    strategy_family_version_id: str,
) -> StrategyFamilySignalOutput:
    evidence_payload = dict(output.evidence_payload)
    candidate_semantics = evidence_payload.get("candidate_semantics")
    if isinstance(candidate_semantics, dict):
        evidence_payload["candidate_semantics"] = {
            **candidate_semantics,
            "strategy_family_id": strategy_family_id,
            "strategy_family_version_id": strategy_family_version_id,
        }

    signal_snapshot = dict(output.signal_snapshot)
    signal_snapshot["strategy_family"] = strategy_family_id
    signal_snapshot["reference_strategy_family"] = CPM_FAMILY_ID
    signal_snapshot["reference_logic_version"] = signal_snapshot.get("logic_version")

    return output.model_copy(
        update={
            "strategy_family_id": strategy_family_id,
            "strategy_family_version_id": strategy_family_version_id,
            "signal_snapshot": signal_snapshot,
            "evidence_payload": evidence_payload,
        },
        deep=True,
    )


def _output_mismatches(
    signal_input: StrategyFamilySignalInput,
    output: StrategyFamilySignalOutput,
) -> list[str]:
    mismatches: list[str] = []
    if output.evaluation_id != signal_input.evaluation_id:
        mismatches.append("strategy_output_evaluation_id_mismatch")
    if output.strategy_family_id != signal_input.strategy_family_id:
        mismatches.append("strategy_output_family_mismatch")
    if output.strategy_family_version_id != signal_input.strategy_family_version_id:
        mismatches.append("strategy_output_version_mismatch")
    if output.symbol != signal_input.symbol:
        mismatches.append("strategy_output_symbol_mismatch")
    return mismatches


def _dedupe(values: list[str]) -> list[str]:
    return sorted(dict.fromkeys(values))
