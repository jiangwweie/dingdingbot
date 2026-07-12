"""Adapt production strategy evaluation results into OFC observations."""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.application.runtime_strategy_signal_evaluation_service import (
    RuntimeStrategySignalEvaluationResult,
    RuntimeStrategySignalEvaluationService,
    RuntimeStrategySignalEvaluationStatus,
)
from src.domain.opportunity_feedback_calibration import (
    OpportunityEvaluation,
    OpportunityResult,
    OpportunitySource,
)
from src.domain.strategy_family_signal import SignalType, StrategyFamilySignalInput


class EventSpecCalibrationIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy_group_id: str = Field(min_length=1, max_length=128)
    strategy_group_version_id: str = Field(min_length=1, max_length=160)
    evaluator_version_id: str = Field(min_length=1, max_length=128)
    event_spec_id: str = Field(min_length=1, max_length=192)
    event_spec_version_id: str = Field(min_length=1, max_length=192)
    event_spec_version: str = Field(min_length=1, max_length=32)
    event_id: str = Field(min_length=1, max_length=128)
    side: Literal["long", "short"]
    timeframe: str = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def _validate_current_identity(self) -> "EventSpecCalibrationIdentity":
        expected_spec_id = (
            f"event_spec:{self.strategy_group_id}:{self.event_id}:"
            f"{self.event_spec_version}"
        )
        expected_version_id = f"{expected_spec_id}:{self.event_spec_version}"
        if self.event_spec_id != expected_spec_id:
            raise ValueError("event_spec_identity_mismatch")
        if self.event_spec_version_id != expected_version_id:
            raise ValueError("event_spec_version_identity_mismatch")
        return self

    @classmethod
    def from_pg_event_spec(
        cls,
        row: dict[str, Any],
        *,
        evaluator_version_id: str,
    ) -> "EventSpecCalibrationIdentity":
        event_spec_id = str(row.get("event_spec_id") or "")
        event_spec_version = str(row.get("event_spec_version") or "")
        return cls(
            strategy_group_id=str(row.get("strategy_group_id") or ""),
            strategy_group_version_id=str(
                row.get("strategy_group_version_id") or ""
            ),
            evaluator_version_id=evaluator_version_id,
            event_spec_id=event_spec_id,
            event_spec_version_id=f"{event_spec_id}:{event_spec_version}",
            event_spec_version=event_spec_version,
            event_id=str(row.get("event_id") or ""),
            side=str(row.get("side") or ""),
            timeframe=str(row.get("timeframe") or ""),
        )


class SignalEvaluationService(Protocol):
    def evaluate(
        self,
        signal_input: StrategyFamilySignalInput,
    ) -> RuntimeStrategySignalEvaluationResult:
        ...


def evaluate_calibration_observation(
    *,
    signal_input: StrategyFamilySignalInput,
    event_spec: EventSpecCalibrationIdentity,
    source: OpportunitySource,
    evaluator_service: SignalEvaluationService | None = None,
    parity_expected: bool = False,
) -> OpportunityEvaluation:
    """Evaluate through the production router and map only non-authority facts."""

    if signal_input.strategy_family_id != event_spec.strategy_group_id:
        raise ValueError("event_spec_strategy_group_mismatch")
    if signal_input.strategy_family_version_id != event_spec.evaluator_version_id:
        raise ValueError("event_spec_strategy_version_mismatch")
    if signal_input.primary_timeframe != event_spec.timeframe:
        raise ValueError("event_spec_timeframe_mismatch")
    if signal_input.trigger_candle_close_time_ms is None:
        raise ValueError("trigger_candle_close_time_ms_required")

    service = evaluator_service or RuntimeStrategySignalEvaluationService()
    evaluated = service.evaluate(signal_input)
    output = evaluated.output
    fact_results = (
        {item.fact_key: item.observed_value for item in output.fact_observations}
        if output is not None
        else {}
    )
    failed_facts = sorted(
        key
        for key, value in fact_results.items()
        if value is False or value is None
    )
    result = _opportunity_result(evaluated, failed_facts=failed_facts)
    if result == OpportunityResult.SIGNAL and output is not None:
        if output.side.value != event_spec.side:
            raise ValueError("event_spec_output_side_mismatch")

    return OpportunityEvaluation(
        strategy_group_id=event_spec.strategy_group_id,
        strategy_group_version_id=event_spec.strategy_group_version_id,
        evaluator_version_id=event_spec.evaluator_version_id,
        event_spec_id=event_spec.event_spec_id,
        event_spec_version_id=event_spec.event_spec_version_id,
        event_id=event_spec.event_id,
        symbol=signal_input.symbol,
        side=event_spec.side,
        timeframe=event_spec.timeframe,
        trigger_candle_close_time_ms=signal_input.trigger_candle_close_time_ms,
        observed_at_ms=signal_input.timestamp_ms,
        source=source,
        result=result,
        fact_results=fact_results,
        failed_facts=failed_facts,
        parity_expected=parity_expected,
    )


def _opportunity_result(
    evaluated: RuntimeStrategySignalEvaluationResult,
    *,
    failed_facts: list[str],
) -> OpportunityResult:
    output = evaluated.output
    if output is None or output.signal_type == SignalType.INVALID:
        return OpportunityResult.INVALID
    if evaluated.status == RuntimeStrategySignalEvaluationStatus.BLOCKED:
        return OpportunityResult.INVALID
    if output.signal_type == SignalType.WOULD_ENTER:
        return OpportunityResult.SIGNAL
    if output.signal_type == SignalType.NO_ACTION:
        return OpportunityResult.NEAR_MISS if failed_facts else OpportunityResult.NO_SIGNAL
    return OpportunityResult.INVALID
