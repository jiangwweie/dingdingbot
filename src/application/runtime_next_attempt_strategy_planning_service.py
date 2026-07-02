"""Post-submit next-attempt strategy planning orchestration.

This service reconnects the post-submit runtime loop to the B0 strategy signal
planning path:

RuntimePostSubmitFinalizePayload domain payload(next gate ready)
-> fresh StrategyFamilySignalInput
-> RuntimeStrategySignalPlanningService
-> shadow SignalEvaluation / shadow OrderCandidate planning

It does not create executable intents, local orders, OrderLifecycle handoffs,
exchange requests, closes, transfers, or withdrawals.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from src.application.runtime_strategy_signal_planning_service import (
    RuntimeStrategySignalCandidatePlanningResult,
    RuntimeStrategySignalCandidatePlanningStatus,
)
from src.domain.runtime_next_attempt_release import (
    RuntimeNextAttemptReleaseEvidence,
    RuntimeNextAttemptReleaseStatus,
)
from src.domain.runtime_post_submit_finalize import (
    RuntimeNextAttemptGateStatus,
    RuntimePostSubmitFinalizePayload,
    RuntimePostSubmitFinalizeStatus,
)
from src.domain.strategy_family_signal import StrategyFamilySignalInput
from src.domain.strategy_runtime import StrategyRuntimeInstance


class RuntimeStrategySignalPlannerPort(Protocol):
    async def plan_shadow_candidate_from_signal_input(
        self,
        signal_input: StrategyFamilySignalInput,
        *,
        runtime: StrategyRuntimeInstance,
        context_id: str | None = None,
        expires_at_ms: int | None = None,
        metadata: dict | None = None,
    ) -> RuntimeStrategySignalCandidatePlanningResult:
        ...


class RuntimeNextAttemptStrategyPlanningStatus(str, Enum):
    READY_FOR_FINAL_GATE_PREFLIGHT = "ready_for_final_gate_preflight"
    WAITING_FOR_SIGNAL = "waiting_for_signal"
    BLOCKED_BY_POST_SUBMIT_GATE = "blocked_by_post_submit_gate"
    BLOCKED_BY_RELEASE_GATE = "blocked_by_release_gate"
    BLOCKED_BY_STRATEGY_PLANNING = "blocked_by_strategy_planning"


class RuntimeNextAttemptStrategyPlanningArtifact(BaseModel):
    """Audit artifact for one post-submit next-attempt strategy planning pass."""

    model_config = ConfigDict(extra="forbid")

    artifact_id: str = Field(min_length=1, max_length=640)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    source_authorization_id: str = Field(min_length=1, max_length=220)
    source_post_submit_finalize_payload_id: str | None = Field(
        default=None,
        max_length=640,
    )
    source_release_evidence_id: str | None = Field(default=None, max_length=420)
    status: RuntimeNextAttemptStrategyPlanningStatus
    next_attempt_gate_status: RuntimeNextAttemptGateStatus
    signal_evaluation_id: str | None = Field(default=None, max_length=128)
    strategy_family_id: str | None = Field(default=None, max_length=128)
    strategy_family_version_id: str | None = Field(default=None, max_length=128)
    symbol: str | None = Field(default=None, max_length=128)
    candidate_planning_status: RuntimeStrategySignalCandidatePlanningStatus | None = None
    candidate_planning_result: RuntimeStrategySignalCandidatePlanningResult | None = None
    order_candidate_id: str | None = Field(default=None, max_length=128)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    strategy_planning_plan: dict = Field(default_factory=dict)
    consumed_authorization_replay_only: Literal[True] = True
    requires_fresh_strategy_signal: Literal[True] = True
    requires_fresh_authorization_before_submit: Literal[True] = True
    old_authorization_submit_retry_allowed: Literal[False] = False
    pre_submit_rehearsal_retry_allowed: Literal[False] = False
    execution_intent_created: Literal[False] = False
    executable_execution_intent_created: Literal[False] = False
    order_created: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    exchange_called: Literal[False] = False
    exchange_order_submitted: Literal[False] = False
    runtime_state_mutated: Literal[False] = False
    withdrawal_or_transfer_created: Literal[False] = False
    metadata: dict = Field(default_factory=dict)


class RuntimeNextAttemptStrategyPlanningService:
    """Gate fresh strategy signal planning behind post-submit finalize."""

    def __init__(
        self,
        *,
        strategy_signal_planner: RuntimeStrategySignalPlannerPort,
    ) -> None:
        self._strategy_signal_planner = strategy_signal_planner

    async def plan_from_post_submit_gate(
        self,
        *,
        post_submit_finalize_payload: RuntimePostSubmitFinalizePayload,
        signal_input: StrategyFamilySignalInput,
        runtime: StrategyRuntimeInstance,
        context_id: str | None = None,
        expires_at_ms: int | None = None,
        metadata: dict | None = None,
    ) -> RuntimeNextAttemptStrategyPlanningArtifact:
        blockers = _post_submit_gate_blockers(
            post_submit_finalize_payload=post_submit_finalize_payload,
            runtime=runtime,
        )
        if blockers:
            return _planning_artifact(
                post_submit_finalize_payload=post_submit_finalize_payload,
                runtime=runtime,
                signal_input=signal_input,
                status=(
                    RuntimeNextAttemptStrategyPlanningStatus
                    .BLOCKED_BY_POST_SUBMIT_GATE
                ),
                blockers=blockers,
                warnings=list(post_submit_finalize_payload.warnings),
                operator_next_step="resolve_post_submit_next_attempt_gate",
                metadata={
                    "blocked_before_strategy_signal_planning": True,
                    "strategy_signal_planner_called": False,
                    **(metadata or {}),
                },
            )

        planning_result = await (
            self._strategy_signal_planner.plan_shadow_candidate_from_signal_input(
                signal_input,
                runtime=runtime,
                context_id=context_id,
                expires_at_ms=expires_at_ms,
                metadata={
                    "runtime_next_attempt_strategy_planning": True,
                    "source_post_submit_finalize_payload_id": (
                        post_submit_finalize_payload.post_submit_finalize_payload_id
                    ),
                    "source_authorization_id": (
                        post_submit_finalize_payload.authorization_id
                    ),
                    "consumed_authorization_replay_only": True,
                    "requires_fresh_authorization_before_submit": True,
                    **(metadata or {}),
                },
            )
        )
        return _planning_artifact_from_planning_result(
            post_submit_finalize_payload=post_submit_finalize_payload,
            runtime=runtime,
            signal_input=signal_input,
            planning_result=planning_result,
            metadata=metadata,
        )

    async def plan_from_release_gate(
        self,
        *,
        next_attempt_release_evidence: RuntimeNextAttemptReleaseEvidence,
        signal_input: StrategyFamilySignalInput,
        runtime: StrategyRuntimeInstance,
        context_id: str | None = None,
        expires_at_ms: int | None = None,
        metadata: dict | None = None,
    ) -> RuntimeNextAttemptStrategyPlanningArtifact:
        blockers = _release_gate_blockers(
            next_attempt_release_evidence=next_attempt_release_evidence,
            runtime=runtime,
        )
        if blockers:
            return _release_planning_artifact(
                next_attempt_release_evidence=next_attempt_release_evidence,
                runtime=runtime,
                signal_input=signal_input,
                status=(
                    RuntimeNextAttemptStrategyPlanningStatus
                    .BLOCKED_BY_RELEASE_GATE
                ),
                blockers=blockers,
                warnings=list(next_attempt_release_evidence.warnings),
                operator_next_step=(
                    "resolve_next_attempt_release_gate_before_strategy_planning"
                ),
                metadata={
                    "blocked_before_strategy_signal_planning": True,
                    "strategy_signal_planner_called": False,
                    **(metadata or {}),
                },
            )

        planning_result = await (
            self._strategy_signal_planner.plan_shadow_candidate_from_signal_input(
                signal_input,
                runtime=runtime,
                context_id=context_id,
                expires_at_ms=expires_at_ms,
                metadata={
                    "runtime_next_attempt_strategy_planning": True,
                    "source_next_attempt_release_evidence_id": (
                        next_attempt_release_evidence.release_evidence_id
                    ),
                    "release_ready_for_strategy_signal": True,
                    "consumed_authorization_replay_only": True,
                    "requires_fresh_authorization_before_submit": True,
                    **(metadata or {}),
                },
            )
        )
        return _release_planning_artifact_from_planning_result(
            next_attempt_release_evidence=next_attempt_release_evidence,
            runtime=runtime,
            signal_input=signal_input,
            planning_result=planning_result,
            metadata=metadata,
        )


def _post_submit_gate_blockers(
    *,
    post_submit_finalize_payload: RuntimePostSubmitFinalizePayload,
    runtime: StrategyRuntimeInstance,
) -> list[str]:
    blockers: list[str] = []
    if post_submit_finalize_payload.runtime_instance_id != runtime.runtime_instance_id:
        blockers.append("post_submit_runtime_mismatch")
    if post_submit_finalize_payload.status != (
        RuntimePostSubmitFinalizeStatus.FINALIZED_READY_FOR_NEXT_ATTEMPT
    ):
        blockers.append("post_submit_finalize_not_ready_for_next_attempt")
    if post_submit_finalize_payload.next_attempt_gate.status != (
        RuntimeNextAttemptGateStatus.READY_FOR_FRESH_SIGNAL
    ):
        blockers.append("post_submit_next_attempt_gate_not_ready")
    blockers.extend(post_submit_finalize_payload.blockers)
    blockers.extend(post_submit_finalize_payload.next_attempt_gate.blockers)
    return _dedupe(blockers)


def _release_gate_blockers(
    *,
    next_attempt_release_evidence: RuntimeNextAttemptReleaseEvidence,
    runtime: StrategyRuntimeInstance,
) -> list[str]:
    blockers: list[str] = []
    if next_attempt_release_evidence.runtime_instance_id != runtime.runtime_instance_id:
        blockers.append("next_attempt_release_runtime_mismatch")
    if next_attempt_release_evidence.status != (
        RuntimeNextAttemptReleaseStatus.READY_FOR_STRATEGY_SIGNAL
    ):
        blockers.append("next_attempt_release_not_ready_for_strategy_signal")
    if not next_attempt_release_evidence.strategy_signal_observation_allowed:
        blockers.append("strategy_signal_observation_not_allowed_by_release")
    if not next_attempt_release_evidence.shadow_candidate_planning_allowed:
        blockers.append("shadow_candidate_planning_not_allowed_by_release")
    blockers.extend(next_attempt_release_evidence.blockers)
    return _dedupe(blockers)


def _planning_artifact_from_planning_result(
    *,
    post_submit_finalize_payload: RuntimePostSubmitFinalizePayload,
    runtime: StrategyRuntimeInstance,
    signal_input: StrategyFamilySignalInput,
    planning_result: RuntimeStrategySignalCandidatePlanningResult,
    metadata: dict | None,
) -> RuntimeNextAttemptStrategyPlanningArtifact:
    if (
        planning_result.status
        == RuntimeStrategySignalCandidatePlanningStatus.SHADOW_CANDIDATE_CREATED
    ):
        status = (
            RuntimeNextAttemptStrategyPlanningStatus
            .READY_FOR_FINAL_GATE_PREFLIGHT
        )
        operator_next_step = "run_runtime_final_gate_preflight_for_shadow_candidate"
    elif (
        planning_result.status
        == RuntimeStrategySignalCandidatePlanningStatus.OBSERVE_ONLY
    ):
        status = RuntimeNextAttemptStrategyPlanningStatus.WAITING_FOR_SIGNAL
        operator_next_step = "observe_only_or_wait_for_next_closed_bar"
    else:
        status = (
            RuntimeNextAttemptStrategyPlanningStatus
            .BLOCKED_BY_STRATEGY_PLANNING
        )
        operator_next_step = "resolve_strategy_signal_planning_blockers"

    candidate = planning_result.candidate
    return _planning_artifact(
        post_submit_finalize_payload=post_submit_finalize_payload,
        runtime=runtime,
        signal_input=signal_input,
        status=status,
        planning_result=planning_result,
        order_candidate_id=(
            candidate.order_candidate_id
            if candidate is not None
            else None
        ),
        blockers=list(planning_result.blockers),
        warnings=list(post_submit_finalize_payload.warnings)
        + list(planning_result.warnings),
        operator_next_step=operator_next_step,
        metadata={
            "strategy_signal_planner_called": True,
            "fresh_signal_evaluation_id": signal_input.evaluation_id,
            "candidate_planning_status": planning_result.status.value,
            **(metadata or {}),
        },
    )


def _release_planning_artifact_from_planning_result(
    *,
    next_attempt_release_evidence: RuntimeNextAttemptReleaseEvidence,
    runtime: StrategyRuntimeInstance,
    signal_input: StrategyFamilySignalInput,
    planning_result: RuntimeStrategySignalCandidatePlanningResult,
    metadata: dict | None,
) -> RuntimeNextAttemptStrategyPlanningArtifact:
    if (
        planning_result.status
        == RuntimeStrategySignalCandidatePlanningStatus.SHADOW_CANDIDATE_CREATED
    ):
        status = (
            RuntimeNextAttemptStrategyPlanningStatus
            .READY_FOR_FINAL_GATE_PREFLIGHT
        )
        operator_next_step = "run_runtime_final_gate_preflight_for_shadow_candidate"
    elif (
        planning_result.status
        == RuntimeStrategySignalCandidatePlanningStatus.OBSERVE_ONLY
    ):
        status = RuntimeNextAttemptStrategyPlanningStatus.WAITING_FOR_SIGNAL
        operator_next_step = "observe_only_or_wait_for_next_closed_bar"
    else:
        status = (
            RuntimeNextAttemptStrategyPlanningStatus
            .BLOCKED_BY_STRATEGY_PLANNING
        )
        operator_next_step = "resolve_strategy_signal_planning_blockers"

    candidate = planning_result.candidate
    return _release_planning_artifact(
        next_attempt_release_evidence=next_attempt_release_evidence,
        runtime=runtime,
        signal_input=signal_input,
        status=status,
        planning_result=planning_result,
        order_candidate_id=(
            candidate.order_candidate_id
            if candidate is not None
            else None
        ),
        blockers=list(planning_result.blockers),
        warnings=list(next_attempt_release_evidence.warnings)
        + list(planning_result.warnings),
        operator_next_step=operator_next_step,
        metadata={
            "strategy_signal_planner_called": True,
            "fresh_signal_evaluation_id": signal_input.evaluation_id,
            "candidate_planning_status": planning_result.status.value,
            **(metadata or {}),
        },
    )


def _planning_artifact(
    *,
    post_submit_finalize_payload: RuntimePostSubmitFinalizePayload,
    runtime: StrategyRuntimeInstance,
    signal_input: StrategyFamilySignalInput,
    status: RuntimeNextAttemptStrategyPlanningStatus,
    blockers: list[str] | None = None,
    warnings: list[str] | None = None,
    operator_next_step: str,
    planning_result: RuntimeStrategySignalCandidatePlanningResult | None = None,
    order_candidate_id: str | None = None,
    metadata: dict | None = None,
) -> RuntimeNextAttemptStrategyPlanningArtifact:
    return RuntimeNextAttemptStrategyPlanningArtifact(
        artifact_id=(
            "runtime-next-attempt-strategy-planning-"
            f"{post_submit_finalize_payload.authorization_id}-"
            f"{signal_input.evaluation_id}"
        ),
        runtime_instance_id=runtime.runtime_instance_id,
        source_authorization_id=post_submit_finalize_payload.authorization_id,
        source_post_submit_finalize_payload_id=(
            post_submit_finalize_payload.post_submit_finalize_payload_id
        ),
        status=status,
        next_attempt_gate_status=(
            post_submit_finalize_payload.next_attempt_gate.status
        ),
        signal_evaluation_id=signal_input.evaluation_id,
        strategy_family_id=signal_input.strategy_family_id,
        strategy_family_version_id=signal_input.strategy_family_version_id,
        symbol=signal_input.symbol,
        candidate_planning_status=(
            planning_result.status
            if planning_result is not None
            else None
        ),
        candidate_planning_result=planning_result,
        order_candidate_id=order_candidate_id,
        blockers=_dedupe(blockers or []),
        warnings=_dedupe(warnings or []),
        strategy_planning_plan={
            "scope": "runtime_next_attempt_strategy_planning_plan",
            "next_step": operator_next_step,
            "not_executed": True,
            "uses_fresh_signal": True,
            "reuses_consumed_authorization": False,
            "creates_shadow_candidate": bool(order_candidate_id),
            "creates_executable_execution_intent": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "live_submit_allowed": False,
            "requires_official_final_gate": bool(order_candidate_id),
            "requires_fresh_authorization_before_submit": True,
        },
        metadata={
            "source": "runtime_next_attempt_strategy_planning_service",
            "post_submit_finalize_to_fresh_signal_planning": True,
            "right_tail_runtime_objective_preserved": True,
            "small_bounded_losses_allowed": True,
            "old_authorization_is_replay_only": True,
            **(metadata or {}),
        },
    )


def _release_planning_artifact(
    *,
    next_attempt_release_evidence: RuntimeNextAttemptReleaseEvidence,
    runtime: StrategyRuntimeInstance,
    signal_input: StrategyFamilySignalInput,
    status: RuntimeNextAttemptStrategyPlanningStatus,
    blockers: list[str] | None = None,
    warnings: list[str] | None = None,
    operator_next_step: str,
    planning_result: RuntimeStrategySignalCandidatePlanningResult | None = None,
    order_candidate_id: str | None = None,
    metadata: dict | None = None,
) -> RuntimeNextAttemptStrategyPlanningArtifact:
    gate_status = (
        RuntimeNextAttemptGateStatus.READY_FOR_FRESH_SIGNAL
        if next_attempt_release_evidence.status
        == RuntimeNextAttemptReleaseStatus.READY_FOR_STRATEGY_SIGNAL
        else RuntimeNextAttemptGateStatus.BLOCKED
    )
    return RuntimeNextAttemptStrategyPlanningArtifact(
        artifact_id=(
            "runtime-next-attempt-strategy-planning-"
            f"{next_attempt_release_evidence.release_evidence_id}-"
            f"{signal_input.evaluation_id}"
        ),
        runtime_instance_id=runtime.runtime_instance_id,
        source_authorization_id=(
            f"runtime-release:{next_attempt_release_evidence.release_evidence_id}"
        ),
        source_release_evidence_id=next_attempt_release_evidence.release_evidence_id,
        status=status,
        next_attempt_gate_status=gate_status,
        signal_evaluation_id=signal_input.evaluation_id,
        strategy_family_id=signal_input.strategy_family_id,
        strategy_family_version_id=signal_input.strategy_family_version_id,
        symbol=signal_input.symbol,
        candidate_planning_status=(
            planning_result.status
            if planning_result is not None
            else None
        ),
        candidate_planning_result=planning_result,
        order_candidate_id=order_candidate_id,
        blockers=_dedupe(blockers or []),
        warnings=_dedupe(warnings or []),
        strategy_planning_plan={
            "scope": "runtime_next_attempt_strategy_planning_plan",
            "next_step": operator_next_step,
            "not_executed": True,
            "uses_fresh_signal": True,
            "reuses_consumed_authorization": False,
            "creates_shadow_candidate": bool(order_candidate_id),
            "creates_executable_execution_intent": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "live_submit_allowed": False,
            "requires_official_final_gate": bool(order_candidate_id),
            "requires_fresh_authorization_before_submit": True,
        },
        metadata={
            "source": "runtime_next_attempt_strategy_planning_service",
            "next_attempt_release_to_fresh_signal_planning": True,
            "right_tail_runtime_objective_preserved": True,
            "small_bounded_losses_allowed": True,
            "old_authorization_is_replay_only": True,
            **(metadata or {}),
        },
    )


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
