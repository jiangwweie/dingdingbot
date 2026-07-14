"""Evaluate runtime strategy-family signals behind the B0 semantics gate.

This application service is intentionally non-executing. It routes a
StrategyFamilySignalInput to a configured pure evaluator, verifies the evaluator
output against the StrategyImplementation binding, and reports whether the
output may continue toward the existing shadow semantics binding path.

It does not create SignalEvaluation rows, OrderCandidates, ExecutionIntents,
orders, OrderLifecycle calls, or exchange requests.
"""

from __future__ import annotations

from decimal import Decimal
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
    FBS001PilotReferenceEvaluator,
    LSR001PriceActionEvaluator,
    PMR001PilotReferenceEvaluator,
    RBR001PriceActionEvaluator,
    TEQ001PilotReferenceEvaluator,
    VCB001PriceActionEvaluator,
)
from src.domain.runtime_lane_identity import RuntimeLaneIdentity
from src.domain.sor_session_range_evaluator import SOR001SessionRangeEvaluator
from src.domain.strategy_family_signal import (
    ExpectedRiskShape,
    SignalInputRefs,
    SignalReviewPlan,
    SignalSide,
    SignalType,
    StrategyFactObservation,
    StrategyFamilySignalInput,
    StrategyFamilySignalOutput,
)
from src.domain.execution_eligibility import RequiredExecutionMode, SignalGrade
from src.domain.strategy_semantics import (
    StrategyCandidateMode,
    StrategySemanticsCatalog,
    initial_strategy_semantics_catalog,
)


class RuntimeStrategySignalEvaluationStatus(str, Enum):
    READY_FOR_SEMANTIC_BINDING = "ready_for_semantic_binding"
    OBSERVE_ONLY = "observe_only"
    BLOCKED = "blocked"


class RuntimeLaneEventEvaluationStatus(str, Enum):
    """Event-Spec scoped outcome for one immutable runtime lane."""

    EVENT_SATISFIED = "event_satisfied"
    COMPUTED_NOT_SATISFIED = "computed_not_satisfied"
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


class RuntimeLaneEventEvaluationResult(BaseModel):
    """Production-facing evaluator result that cannot redefine its lane."""

    model_config = ConfigDict(extra="forbid")

    lane_identity: RuntimeLaneIdentity
    status: RuntimeLaneEventEvaluationStatus
    signal: StrategyFamilySignalOutput | None = None
    blockers: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    raw_evaluation_status: RuntimeStrategySignalEvaluationStatus
    evaluator_id: str | None = Field(default=None, max_length=128)
    evaluated_at_ms: int = Field(default=0, ge=0)
    valid_until_ms: int = Field(default=0, ge=0)
    can_materialize_live_signal_event: bool = False
    signal_evaluation_created: Literal[False] = False
    order_candidate_created: Literal[False] = False
    execution_intent_created: Literal[False] = False
    order_created: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    exchange_called: Literal[False] = False
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

    def evaluate_for_runtime_lane(
        self,
        signal_input: StrategyFamilySignalInput,
        *,
        lane_identity: RuntimeLaneIdentity,
        freshness_window_ms: int | None = None,
    ) -> RuntimeLaneEventEvaluationResult:
        """Evaluate one input only for the PG-resolved Event-Spec lane.

        Generic evaluators may recognize market patterns outside the registered
        Event-Spec direction. Those patterns are ordinary no-signal evidence for
        this lane, rather than a blocker or authority to create another lane.
        """

        evaluated_at_ms = int(signal_input.timestamp_ms)
        resolved_freshness_window_ms = int(freshness_window_ms or 0)
        if resolved_freshness_window_ms <= 0:
            return self._lane_result(
                lane_identity=lane_identity,
                status=RuntimeLaneEventEvaluationStatus.BLOCKED,
                blockers=["event_spec_freshness_window_missing"],
                reason_codes=[],
                raw_evaluation_status=RuntimeStrategySignalEvaluationStatus.BLOCKED,
                evaluated_at_ms=evaluated_at_ms,
                valid_until_ms=0,
            )
        trigger_candle_close_time_ms = int(signal_input.trigger_candle_close_time_ms or 0)
        valid_until_ms = (
            trigger_candle_close_time_ms + resolved_freshness_window_ms
            if trigger_candle_close_time_ms > 0
            else 0
        )
        input_mismatch = _input_lane_identity_mismatch(
            signal_input=signal_input,
            lane_identity=lane_identity,
        )
        if input_mismatch:
            return self._lane_result(
                lane_identity=lane_identity,
                status=RuntimeLaneEventEvaluationStatus.BLOCKED,
                blockers=[input_mismatch],
                reason_codes=[],
                raw_evaluation_status=RuntimeStrategySignalEvaluationStatus.BLOCKED,
                evaluated_at_ms=evaluated_at_ms,
                valid_until_ms=valid_until_ms,
            )

        evaluation = self.evaluate(signal_input)
        output = evaluation.output
        if output is not None:
            output_mismatch = _output_lane_identity_mismatch(
                output=output,
                lane_identity=lane_identity,
            )
            if output_mismatch:
                return self._lane_result(
                    lane_identity=lane_identity,
                    status=RuntimeLaneEventEvaluationStatus.BLOCKED,
                    blockers=[output_mismatch],
                    reason_codes=[],
                    raw_evaluation_status=evaluation.status,
                    evaluator_id=evaluation.evaluator_id,
                    warnings=evaluation.warnings,
                    evaluated_at_ms=evaluated_at_ms,
                    valid_until_ms=valid_until_ms,
                )

            if output.signal_type == SignalType.WOULD_ENTER:
                if output.side.value != lane_identity.side:
                    return self._lane_result(
                        lane_identity=lane_identity,
                        status=RuntimeLaneEventEvaluationStatus.COMPUTED_NOT_SATISFIED,
                        blockers=[],
                        reason_codes=[
                            "computed_not_satisfied",
                            "event_side_not_satisfied",
                        ],
                        raw_evaluation_status=evaluation.status,
                        evaluator_id=evaluation.evaluator_id,
                        warnings=evaluation.warnings,
                        evaluated_at_ms=evaluated_at_ms,
                        valid_until_ms=valid_until_ms,
                    )
                if (
                    evaluation.status
                    == RuntimeStrategySignalEvaluationStatus.READY_FOR_SEMANTIC_BINDING
                ):
                    return self._lane_result(
                        lane_identity=lane_identity,
                        status=RuntimeLaneEventEvaluationStatus.EVENT_SATISFIED,
                        signal=output,
                        blockers=[],
                        reason_codes=list(output.reason_codes),
                        raw_evaluation_status=evaluation.status,
                        evaluator_id=evaluation.evaluator_id,
                        warnings=evaluation.warnings,
                        can_materialize_live_signal_event=True,
                        evaluated_at_ms=evaluated_at_ms,
                        valid_until_ms=valid_until_ms,
                    )

        if evaluation.status == RuntimeStrategySignalEvaluationStatus.BLOCKED:
            return self._lane_result(
                lane_identity=lane_identity,
                status=RuntimeLaneEventEvaluationStatus.BLOCKED,
                blockers=list(evaluation.blockers),
                reason_codes=[],
                raw_evaluation_status=evaluation.status,
                evaluator_id=evaluation.evaluator_id,
                warnings=evaluation.warnings,
                evaluated_at_ms=evaluated_at_ms,
                valid_until_ms=valid_until_ms,
            )

        return self._lane_result(
            lane_identity=lane_identity,
            status=RuntimeLaneEventEvaluationStatus.COMPUTED_NOT_SATISFIED,
            signal=output,
            blockers=[],
            reason_codes=_dedupe(
                ["computed_not_satisfied", *(output.reason_codes if output else [])]
            ),
            raw_evaluation_status=evaluation.status,
            evaluator_id=evaluation.evaluator_id,
            warnings=evaluation.warnings,
            evaluated_at_ms=evaluated_at_ms,
            valid_until_ms=valid_until_ms,
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

    @staticmethod
    def _lane_result(
        *,
        lane_identity: RuntimeLaneIdentity,
        status: RuntimeLaneEventEvaluationStatus,
        blockers: list[str],
        reason_codes: list[str],
        raw_evaluation_status: RuntimeStrategySignalEvaluationStatus,
        signal: StrategyFamilySignalOutput | None = None,
        evaluator_id: str | None = None,
        warnings: list[str] | None = None,
        can_materialize_live_signal_event: bool = False,
        evaluated_at_ms: int = 0,
        valid_until_ms: int = 0,
    ) -> RuntimeLaneEventEvaluationResult:
        return RuntimeLaneEventEvaluationResult(
            lane_identity=lane_identity,
            status=status,
            signal=signal,
            blockers=_dedupe(blockers),
            reason_codes=_dedupe(reason_codes),
            warnings=_dedupe(warnings or []),
            raw_evaluation_status=raw_evaluation_status,
            evaluator_id=evaluator_id,
            evaluated_at_ms=evaluated_at_ms,
            valid_until_ms=valid_until_ms,
            can_materialize_live_signal_event=can_materialize_live_signal_event,
            metadata={
                "source": "runtime_strategy_signal_evaluation_service",
                "event_spec_scoped": True,
                "identity_key": lane_identity.identity_key,
                "non_executing_evaluator_route": True,
            },
        )

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
        ("TEQ-001", "TEQ-001-v0"): TEQ001PilotReferenceEvaluator(),
        ("FBS-001", "FBS-001-v0"): FBS001PilotReferenceEvaluator(),
        ("PMR-001", "PMR-001-v0"): PMR001PilotReferenceEvaluator(),
        ("SOR-001", "SOR-001-v0"): SOR001SessionRangeEvaluator(),
        ("MI-001", "MI-001-v0"): _MI001RuntimeReferenceEvaluator(),
        ("BRF2-001", "BRF2-001-v0"): _BRF2LiveReferenceEvaluator(),
        ("BRF-001", "BRF-001-v0"): BRF001PriceActionEvaluator(),
        ("BTPC-001", "BTPC-001-v0"): BTPC001PriceActionEvaluator(),
        ("LSR-001", "LSR-001-v0"): LSR001PriceActionEvaluator(),
        ("RBR-001", "RBR-001-v0"): RBR001PriceActionEvaluator(),
        ("VCB-001", "VCB-001-v0"): VCB001PriceActionEvaluator(),
    }


class _MI001RuntimeReferenceEvaluator:
    """Evaluate MI-001 momentum impulse inputs without importing console glue."""

    _lookback_bars = 12
    _return_threshold_pct = Decimal("3")

    def evaluate(
        self,
        signal_input: StrategyFamilySignalInput,
    ) -> StrategyFamilySignalOutput:
        if signal_input.strategy_family_id != "MI-001":
            return self._output(
                signal_input,
                signal_type=SignalType.INVALID,
                side=SignalSide.NONE,
                confidence=Decimal("0"),
                reason_codes=["mi001_invalid_wrong_family"],
                human_summary="Input is not for MI-001.",
                evidence_payload={},
                review_required=False,
            )

        candles = _candles_from_input(signal_input)
        if len(candles) <= self._lookback_bars:
            return self._output(
                signal_input,
                signal_type=SignalType.INVALID,
                side=SignalSide.NONE,
                confidence=Decimal("0"),
                reason_codes=["mi001_invalid_insufficient_candles"],
                human_summary=(
                    "MI-001 requires at least 13 closed 1h candles for the "
                    "12h close-to-close impulse."
                ),
                evidence_payload={
                    "candle_count": len(candles),
                    "min_needed": self._lookback_bars + 1,
                },
                review_required=False,
            )

        latest = candles[-1]
        lookback = candles[-(self._lookback_bars + 1)]
        impulse_return_pct = (
            (latest["close"] - lookback["close"]) / lookback["close"]
        ) * Decimal("100")
        evidence = {
            "logic_version": "mi001-runtime-reference-v1",
            "lookback_bars": self._lookback_bars,
            "return_threshold_pct": str(self._return_threshold_pct),
            "lookback_close": str(lookback["close"]),
            "latest_close": str(latest["close"]),
            "latest_1h_open_time_ms": latest["open_time_ms"],
            "impulse_return_pct": str(impulse_return_pct.quantize(Decimal("0.0001"))),
            "closed_candle_count": len(candles),
        }
        if impulse_return_pct < self._return_threshold_pct:
            trigger_ms = int(signal_input.trigger_candle_close_time_ms or 0)
            valid_until_ms = trigger_ms + 3_600_000
            source_ref = f"closed_ohlcv:{signal_input.symbol}:{trigger_ms}:mi-v1"
            return self._output(
                signal_input,
                signal_type=SignalType.NO_ACTION,
                side=SignalSide.NONE,
                confidence=Decimal("0.20"),
                reason_codes=["mi001_no_action_impulse_below_threshold"],
                human_summary=(
                    "MI-001 no-action observation: 12h close-to-close impulse "
                    "is below threshold."
                ),
                evidence_payload=evidence,
                review_required=False,
                fact_observations=[
                    StrategyFactObservation(
                        fact_key="impulse_confirmed",
                        observed_value=False,
                        observed_at_ms=trigger_ms,
                        valid_until_ms=valid_until_ms,
                        source_ref=source_ref,
                    ),
                    StrategyFactObservation(
                        fact_key="impulse_invalidation_reference",
                        observed_value=lookback["close"],
                        observed_at_ms=trigger_ms,
                        valid_until_ms=valid_until_ms,
                        source_ref=source_ref,
                    ),
                ],
            )

        comparative = signal_input.comparative_strength_snapshot
        if comparative is None:
            return self._output(
                signal_input,
                signal_type=SignalType.INVALID,
                side=SignalSide.NONE,
                confidence=Decimal("0"),
                reason_codes=["mi001_invalid_comparative_strength_missing"],
                human_summary=(
                    "MI-001 requires a fresh PG comparative-strength snapshot "
                    "after the impulse threshold is met."
                ),
                evidence_payload=evidence,
                review_required=False,
            )
        if (
            comparative.strategy_group_id != "MI-001"
            or comparative.timeframe != signal_input.primary_timeframe
            or comparative.lookback_bars != self._lookback_bars
            or comparative.trigger_candle_close_time_ms
            != signal_input.trigger_candle_close_time_ms
        ):
            return self._output(
                signal_input,
                signal_type=SignalType.INVALID,
                side=SignalSide.NONE,
                confidence=Decimal("0"),
                reason_codes=["mi001_invalid_comparative_strength_scope"],
                human_summary="MI-001 comparative-strength scope does not match the signal input.",
                evidence_payload=evidence,
                review_required=False,
            )
        try:
            comparative_member = comparative.member(signal_input.symbol)
        except KeyError:
            return self._output(
                signal_input,
                signal_type=SignalType.INVALID,
                side=SignalSide.NONE,
                confidence=Decimal("0"),
                reason_codes=["mi001_invalid_comparative_strength_member_missing"],
                human_summary="MI-001 candidate is missing from its comparative universe.",
                evidence_payload=evidence,
                review_required=False,
            )
        if comparative_member.return_pct != impulse_return_pct:
            return self._output(
                signal_input,
                signal_type=SignalType.INVALID,
                side=SignalSide.NONE,
                confidence=Decimal("0"),
                reason_codes=["mi001_invalid_comparative_return_mismatch"],
                human_summary="MI-001 own impulse and PG comparative return do not match.",
                evidence_payload={
                    **evidence,
                    "comparative_return_pct": str(comparative_member.return_pct),
                },
                review_required=False,
            )

        relative_strength_confirmed = comparative_member.rank == 1
        evidence["comparative_strength"] = comparative.model_dump(mode="json")
        evidence["relative_strength"] = {
            "candidate_symbol": comparative_member.symbol,
            "rank": comparative_member.rank,
            "return_pct": str(comparative_member.return_pct),
            "relative_strength_confirmed": relative_strength_confirmed,
        }
        fact_observations = self._fact_observations(
            signal_input=signal_input,
            comparative_observed_at_ms=comparative.observed_at_ms,
            comparative_valid_until_ms=comparative.valid_until_ms,
            comparative_source_ref=comparative.source_ref,
            relative_strength_confirmed=relative_strength_confirmed,
            invalidation_reference=lookback["close"],
        )
        if not relative_strength_confirmed:
            return self._output(
                signal_input,
                signal_type=SignalType.NO_ACTION,
                side=SignalSide.NONE,
                confidence=Decimal("0.25"),
                reason_codes=["mi001_no_action_relative_strength_not_confirmed"],
                human_summary=(
                    "MI-001 impulse crossed threshold, but the candidate is not "
                    "the comparison-universe leader."
                ),
                evidence_payload=evidence,
                review_required=False,
                fact_observations=fact_observations,
            )

        return self._output(
            signal_input,
            signal_type=SignalType.WOULD_ENTER,
            side=SignalSide.LONG,
            confidence=Decimal("0.65"),
            reason_codes=[
                "mi001_12h_momentum_impulse",
                "mi001_relative_strength_confirmed",
            ],
            human_summary=(
                "MI-001 would-enter long observation: 12h close-to-close "
                "momentum impulse crossed threshold."
            ),
            evidence_payload=evidence,
            review_required=True,
            fact_observations=fact_observations,
            signal_grade=SignalGrade.TRIAL_GRADE_SIGNAL,
            required_execution_mode=RequiredExecutionMode.TRIAL_LIVE,
        )

    def _fact_observations(
        self,
        *,
        signal_input: StrategyFamilySignalInput,
        comparative_observed_at_ms: int,
        comparative_valid_until_ms: int,
        comparative_source_ref: str,
        relative_strength_confirmed: bool,
        invalidation_reference: Decimal,
    ) -> list[StrategyFactObservation]:
        trigger_ms = int(signal_input.trigger_candle_close_time_ms or 0)
        local_source_ref = f"closed_ohlcv:{signal_input.symbol}:{trigger_ms}:mi-v1"
        local_valid_until_ms = trigger_ms + 3_600_000
        return [
            StrategyFactObservation(
                fact_key="impulse_confirmed",
                observed_value=True,
                observed_at_ms=trigger_ms,
                valid_until_ms=local_valid_until_ms,
                source_ref=local_source_ref,
            ),
            StrategyFactObservation(
                fact_key="relative_strength_confirmed",
                observed_value=relative_strength_confirmed,
                observed_at_ms=comparative_observed_at_ms,
                valid_until_ms=comparative_valid_until_ms,
                source_ref=comparative_source_ref,
            ),
            StrategyFactObservation(
                fact_key="impulse_invalidation_reference",
                observed_value=invalidation_reference,
                observed_at_ms=trigger_ms,
                valid_until_ms=local_valid_until_ms,
                source_ref=local_source_ref,
            ),
        ]

    def _output(
        self,
        signal_input: StrategyFamilySignalInput,
        *,
        signal_type: SignalType,
        side: SignalSide,
        confidence: Decimal,
        reason_codes: list[str],
        human_summary: str,
        evidence_payload: dict,
        review_required: bool,
        fact_observations: list[StrategyFactObservation] | None = None,
        signal_grade: SignalGrade = SignalGrade.OBSERVE_ONLY_SIGNAL,
        required_execution_mode: RequiredExecutionMode = RequiredExecutionMode.OBSERVE_ONLY,
    ) -> StrategyFamilySignalOutput:
        return StrategyFamilySignalOutput(
            signal_id=f"mi001-runtime-{signal_input.evaluation_id}",
            evaluation_id=signal_input.evaluation_id,
            strategy_family_id=signal_input.strategy_family_id,
            strategy_family_version_id=signal_input.strategy_family_version_id,
            playbook_id=signal_input.playbook_id,
            symbol=signal_input.symbol,
            timestamp_ms=signal_input.timestamp_ms,
            trigger_candle_close_time_ms=signal_input.trigger_candle_close_time_ms,
            timeframe=signal_input.primary_timeframe,
            signal_type=signal_type,
            side=side,
            confidence=confidence,
            reason_codes=reason_codes,
            human_summary=human_summary,
            signal_grade=signal_grade,
            required_execution_mode=required_execution_mode,
            expected_risk_shape=ExpectedRiskShape.TREND_FOLLOWING_WIDE_STOP,
            signal_snapshot={
                "strategy_family": signal_input.strategy_family_id,
                "logic_version": "mi001-runtime-reference-v1",
            },
            evidence_payload=evidence_payload,
            fact_observations=fact_observations or [],
            input_refs=SignalInputRefs(
                market_snapshot_ref=(
                    f"closed_ohlcv:{signal_input.symbol}:"
                    f"{signal_input.timestamp_ms}"
                ),
                playbook_snapshot_ref=signal_input.playbook_id,
                evaluation_ref=signal_input.evaluation_id,
            ),
            data_quality=signal_input.input_quality,
            review_plan=SignalReviewPlan(
                review_required=review_required,
                review_windows=["24h", "72h", "7d"],
                forward_outcome_metrics=[
                    "MFE",
                    "MAE",
                    "follow_through",
                    "return_time_curve",
                ],
                owner_review_status=(
                    "strategy_review_pending" if review_required else "not_required"
                ),
            ),
        )


class _BRF2LiveReferenceEvaluator:
    """Route BRF2-001 inputs through the BRF short-side price-action evaluator."""

    def __init__(self, delegate: BRF001PriceActionEvaluator | None = None) -> None:
        self._delegate = delegate or BRF001PriceActionEvaluator()

    def evaluate(
        self,
        signal_input: StrategyFamilySignalInput,
    ) -> StrategyFamilySignalOutput:
        mapped_input = signal_input.model_copy(
            update={
                "strategy_family_id": "BRF-001",
                "strategy_family_version_id": "BRF-001-v0",
            },
            deep=True,
        )
        output = self._delegate.evaluate(mapped_input)
        retargeted = _retarget_reference_output(
            output,
            strategy_family_id=signal_input.strategy_family_id,
            strategy_family_version_id=signal_input.strategy_family_version_id,
            signal_snapshot_updates={
                "reference_strategy_family": "BRF-001",
                "reference_logic_version": output.signal_snapshot.get("logic_version"),
            },
        )
        if retargeted.signal_type == SignalType.NO_ACTION:
            htf_context = retargeted.evidence_payload.get("htf_context")
            price_action = retargeted.evidence_payload.get("price_action_structure")
            structure = price_action if isinstance(price_action, dict) else {}
            rally_high = Decimal(str(structure.get("rally_high_reference") or "0"))
            trigger_ms = int(signal_input.trigger_candle_close_time_ms or 0)
            if trigger_ms > 0 and rally_high > 0:
                source_ref = f"closed_ohlcv:{signal_input.symbol}:{trigger_ms}:brf2-v2"
                valid_until_ms = trigger_ms + 3_600_000
                retargeted = retargeted.model_copy(
                    update={
                        "fact_observations": [
                            StrategyFactObservation(
                                fact_key="rally_failure_confirmed",
                                observed_value=bool(structure.get("bear_rally_failure")),
                                observed_at_ms=trigger_ms,
                                valid_until_ms=valid_until_ms,
                                source_ref=source_ref,
                            ),
                            StrategyFactObservation(
                                fact_key="short_side_not_disabled",
                                observed_value=htf_context != "strong_uptrend",
                                observed_at_ms=trigger_ms,
                                valid_until_ms=valid_until_ms,
                                source_ref=source_ref,
                            ),
                            StrategyFactObservation(
                                fact_key="strong_uptrend_disable",
                                observed_value=htf_context == "strong_uptrend",
                                observed_at_ms=trigger_ms,
                                valid_until_ms=valid_until_ms,
                                source_ref=source_ref,
                            ),
                            StrategyFactObservation(
                                fact_key="rally_high_reference",
                                observed_value=rally_high,
                                observed_at_ms=trigger_ms,
                                valid_until_ms=valid_until_ms,
                                source_ref=source_ref,
                            ),
                        ]
                    },
                    deep=True,
                )
        if retargeted.signal_type != SignalType.WOULD_ENTER:
            return retargeted
        if retargeted.side != SignalSide.SHORT:
            return retargeted.model_copy(
                update={
                    "signal_type": SignalType.INVALID,
                    "side": SignalSide.NONE,
                    "signal_grade": SignalGrade.OBSERVE_ONLY_SIGNAL,
                    "required_execution_mode": RequiredExecutionMode.OBSERVE_ONLY,
                    "reason_codes": [
                        *retargeted.reason_codes,
                        "brf2_invalid_non_short_reference_output",
                    ],
                    "fact_observations": [],
                },
                deep=True,
            )

        htf_context = retargeted.evidence_payload.get("htf_context")
        price_action = retargeted.evidence_payload.get("price_action_structure")
        rally_high = (
            price_action.get("rally_high_reference")
            if isinstance(price_action, dict)
            else None
        )
        if htf_context not in {"trend_down", "mixed"} or rally_high is None:
            return retargeted.model_copy(
                update={
                    "signal_type": SignalType.INVALID,
                    "side": SignalSide.NONE,
                    "signal_grade": SignalGrade.OBSERVE_ONLY_SIGNAL,
                    "required_execution_mode": RequiredExecutionMode.OBSERVE_ONLY,
                    "reason_codes": [
                        *retargeted.reason_codes,
                        "brf2_invalid_disable_or_protection_fact_missing",
                    ],
                    "fact_observations": [],
                },
                deep=True,
            )

        trigger_ms = int(signal_input.trigger_candle_close_time_ms or 0)
        valid_until_ms = trigger_ms + 3_600_000
        source_ref = f"closed_ohlcv:{signal_input.symbol}:{trigger_ms}:brf2-v2"
        return retargeted.model_copy(
            update={
                "signal_grade": SignalGrade.TRIAL_GRADE_SIGNAL,
                "required_execution_mode": RequiredExecutionMode.TRIAL_LIVE,
                "fact_observations": [
                    StrategyFactObservation(
                        fact_key="rally_failure_confirmed",
                        observed_value=True,
                        observed_at_ms=trigger_ms,
                        valid_until_ms=valid_until_ms,
                        source_ref=source_ref,
                    ),
                    StrategyFactObservation(
                        fact_key="short_side_not_disabled",
                        observed_value=True,
                        observed_at_ms=trigger_ms,
                        valid_until_ms=valid_until_ms,
                        source_ref=source_ref,
                    ),
                    StrategyFactObservation(
                        fact_key="strong_uptrend_disable",
                        observed_value=False,
                        observed_at_ms=trigger_ms,
                        valid_until_ms=valid_until_ms,
                        source_ref=source_ref,
                    ),
                    StrategyFactObservation(
                        fact_key="rally_high_reference",
                        observed_value=Decimal(str(rally_high)),
                        observed_at_ms=trigger_ms,
                        valid_until_ms=valid_until_ms,
                        source_ref=source_ref,
                    ),
                ],
            },
            deep=True,
        )


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
        return _retarget_reference_output(
            output,
            strategy_family_id=signal_input.strategy_family_id,
            strategy_family_version_id=signal_input.strategy_family_version_id,
            signal_snapshot_updates={
                "reference_strategy_family": CPM_FAMILY_ID,
                "reference_logic_version": output.signal_snapshot.get("logic_version"),
            },
        )


def _retarget_reference_output(
    output: StrategyFamilySignalOutput,
    *,
    strategy_family_id: str,
    strategy_family_version_id: str,
    signal_snapshot_updates: dict[str, str | None] | None = None,
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
    if signal_snapshot_updates:
        signal_snapshot.update(signal_snapshot_updates)

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


def _input_lane_identity_mismatch(
    *,
    signal_input: StrategyFamilySignalInput,
    lane_identity: RuntimeLaneIdentity,
) -> str | None:
    if signal_input.strategy_family_id != lane_identity.strategy_group_id:
        return "runtime_lane_identity_mismatch:strategy_group_id"
    if _normalized_symbol(signal_input.symbol) != lane_identity.symbol:
        return "runtime_lane_identity_mismatch:symbol"
    if signal_input.primary_timeframe != lane_identity.timeframe:
        return "runtime_lane_identity_mismatch:primary_timeframe"
    return None


def _output_lane_identity_mismatch(
    *,
    output: StrategyFamilySignalOutput,
    lane_identity: RuntimeLaneIdentity,
) -> str | None:
    if output.strategy_family_id != lane_identity.strategy_group_id:
        return "runtime_lane_identity_mismatch:output_strategy_group_id"
    if _normalized_symbol(output.symbol) != lane_identity.symbol:
        return "runtime_lane_identity_mismatch:output_symbol"
    if output.timeframe != lane_identity.timeframe:
        return "runtime_lane_identity_mismatch:output_timeframe"
    return None


def _normalized_symbol(value: str) -> str:
    return str(value or "").upper().split(":", 1)[0].replace("/", "")


def _candles_from_input(signal_input: StrategyFamilySignalInput) -> list[dict]:
    windows = dict(signal_input.market_snapshot.candle_context.get("windows") or {})
    raw_candles = windows.get("1h") or windows.get(signal_input.primary_timeframe) or []
    candles: list[dict] = []
    for item in raw_candles:
        try:
            close = Decimal(str(item["close"]))
        except (KeyError, TypeError, ValueError):
            continue
        if close <= Decimal("0"):
            continue
        candles.append(
            {
                "open_time_ms": int(item.get("open_time_ms") or 0),
                "close": close,
            }
        )
    return candles


def _dedupe(values: list[str]) -> list[str]:
    return sorted(dict.fromkeys(values))
