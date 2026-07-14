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
    required_fact_keys: tuple[str, ...] = ()
    disable_fact_keys: tuple[str, ...] = ()

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
            required_fact_keys=tuple(sorted(row.get("required_fact_keys") or ())),
            disable_fact_keys=tuple(sorted(row.get("disable_fact_keys") or ())),
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
    raw_fact_results = (
        {item.fact_key: item.observed_value for item in output.fact_observations}
        if output is not None
        else {}
    )
    event_fact_keys = tuple(
        dict.fromkeys(
            (*event_spec.required_fact_keys, *event_spec.disable_fact_keys)
        )
    )
    fact_results = (
        {key: raw_fact_results.get(key) for key in event_fact_keys}
        if event_fact_keys
        else raw_fact_results
    )
    output_side = output.side.value if output is not None else "none"
    event_side_mismatch = (
        output is not None
        and output.signal_type == SignalType.WOULD_ENTER
        and output_side != event_spec.side
    )
    if event_side_mismatch:
        fact_results["event_side_matched"] = False
    failed_facts = sorted(
        key
        for key, value in fact_results.items()
        if _fact_failed(
            key,
            value,
            disable_fact_keys=event_spec.disable_fact_keys,
        )
    )
    result = _opportunity_result(evaluated, failed_facts=failed_facts)
    if event_side_mismatch:
        result = OpportunityResult.NEAR_MISS

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


def _fact_failed(
    fact_key: str,
    value: Any,
    *,
    disable_fact_keys: tuple[str, ...],
) -> bool:
    if fact_key in disable_fact_keys:
        return value is True or value is None
    return value is False or value is None
