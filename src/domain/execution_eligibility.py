"""Pure execution-eligibility authority semantics.

This module classifies signal evidence. It does not grant Owner policy,
Runtime Safety, FinalGate, Operation Layer, or exchange-write authority.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class SignalGrade(str, Enum):
    OBSERVE_ONLY_SIGNAL = "observe_only_signal"
    TRIAL_GRADE_SIGNAL = "trial_grade_signal"
    PRODUCTION_GRADE_SIGNAL = "production_grade_signal"
    INVALID_SIGNAL = "invalid_signal"


class RequiredExecutionMode(str, Enum):
    OBSERVE_ONLY = "observe_only"
    TRIAL_LIVE = "trial_live"
    PRODUCTION_LIVE = "production_live"


GRADE_TO_MODE = {
    SignalGrade.OBSERVE_ONLY_SIGNAL: RequiredExecutionMode.OBSERVE_ONLY,
    SignalGrade.TRIAL_GRADE_SIGNAL: RequiredExecutionMode.TRIAL_LIVE,
    SignalGrade.PRODUCTION_GRADE_SIGNAL: RequiredExecutionMode.PRODUCTION_LIVE,
    SignalGrade.INVALID_SIGNAL: RequiredExecutionMode.OBSERVE_ONLY,
}

_GRADE_RANK = {
    SignalGrade.INVALID_SIGNAL: 0,
    SignalGrade.OBSERVE_ONLY_SIGNAL: 1,
    SignalGrade.TRIAL_GRADE_SIGNAL: 2,
    SignalGrade.PRODUCTION_GRADE_SIGNAL: 3,
}


class ExecutionEligibilityEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    signal_grade: SignalGrade
    required_execution_mode: RequiredExecutionMode
    execution_eligible: bool
    authority_source_ref: str = Field(min_length=1, max_length=256)


def resolve_execution_eligibility(
    *,
    declared_signal_grade: SignalGrade | str,
    declared_required_execution_mode: RequiredExecutionMode | str,
    execution_eligibility_enabled: bool,
    evaluator_signal_grade: SignalGrade | str,
    evaluator_required_execution_mode: RequiredExecutionMode | str,
    authority_source_ref: str,
) -> ExecutionEligibilityEnvelope:
    """Resolve evaluator output under a versioned Event Spec upper bound."""

    declared_grade = SignalGrade(declared_signal_grade)
    declared_mode = RequiredExecutionMode(declared_required_execution_mode)
    evaluator_grade = SignalGrade(evaluator_signal_grade)
    evaluator_mode = RequiredExecutionMode(evaluator_required_execution_mode)

    if GRADE_TO_MODE[declared_grade] != declared_mode:
        raise ValueError("declared event-spec signal grade and execution mode mismatch")
    if GRADE_TO_MODE[evaluator_grade] != evaluator_mode:
        raise ValueError("evaluator signal grade and execution mode mismatch")
    if _GRADE_RANK[evaluator_grade] > _GRADE_RANK[declared_grade]:
        raise ValueError("evaluator signal authority exceeds declared event-spec authority")

    exact_eligible_authority = (
        execution_eligibility_enabled
        and evaluator_grade == declared_grade
        and evaluator_mode == declared_mode
        and evaluator_grade
        in {SignalGrade.TRIAL_GRADE_SIGNAL, SignalGrade.PRODUCTION_GRADE_SIGNAL}
    )
    return ExecutionEligibilityEnvelope(
        signal_grade=evaluator_grade,
        required_execution_mode=evaluator_mode,
        execution_eligible=exact_eligible_authority,
        authority_source_ref=authority_source_ref,
    )
