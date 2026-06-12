"""Post-submit next-attempt strategy planning orchestration.

This service reconnects the post-submit runtime loop to the B0 strategy signal
planning path:

RuntimePostSubmitFinalizePacket(next gate ready)
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
from src.domain.runtime_post_submit_finalize import (
    RuntimeNextAttemptGateStatus,
    RuntimePostSubmitFinalizePacket,
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
    BLOCKED_BY_STRATEGY_PLANNING = "blocked_by_strategy_planning"


class RuntimeNextAttemptStrategyPlanningPacket(BaseModel):
    """Audit packet for one post-submit next-attempt strategy planning pass."""

    model_config = ConfigDict(extra="forbid")

    packet_id: str = Field(min_length=1, max_length=640)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    source_authorization_id: str = Field(min_length=1, max_length=220)
    post_submit_finalize_packet_id: str = Field(min_length=1, max_length=640)
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
    operator_command_plan: dict = Field(default_factory=dict)
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
        post_submit_finalize_packet: RuntimePostSubmitFinalizePacket,
        signal_input: StrategyFamilySignalInput,
        runtime: StrategyRuntimeInstance,
        context_id: str | None = None,
        expires_at_ms: int | None = None,
        metadata: dict | None = None,
    ) -> RuntimeNextAttemptStrategyPlanningPacket:
        blockers = _post_submit_gate_blockers(
            post_submit_finalize_packet=post_submit_finalize_packet,
            runtime=runtime,
        )
        if blockers:
            return _packet(
                post_submit_finalize_packet=post_submit_finalize_packet,
                runtime=runtime,
                signal_input=signal_input,
                status=(
                    RuntimeNextAttemptStrategyPlanningStatus
                    .BLOCKED_BY_POST_SUBMIT_GATE
                ),
                blockers=blockers,
                warnings=list(post_submit_finalize_packet.warnings),
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
                    "source_post_submit_finalize_packet_id": (
                        post_submit_finalize_packet.packet_id
                    ),
                    "source_authorization_id": (
                        post_submit_finalize_packet.authorization_id
                    ),
                    "consumed_authorization_replay_only": True,
                    "requires_fresh_authorization_before_submit": True,
                    **(metadata or {}),
                },
            )
        )
        return _packet_from_planning_result(
            post_submit_finalize_packet=post_submit_finalize_packet,
            runtime=runtime,
            signal_input=signal_input,
            planning_result=planning_result,
            metadata=metadata,
        )


def _post_submit_gate_blockers(
    *,
    post_submit_finalize_packet: RuntimePostSubmitFinalizePacket,
    runtime: StrategyRuntimeInstance,
) -> list[str]:
    blockers: list[str] = []
    if post_submit_finalize_packet.runtime_instance_id != runtime.runtime_instance_id:
        blockers.append("post_submit_runtime_mismatch")
    if post_submit_finalize_packet.status != (
        RuntimePostSubmitFinalizeStatus.FINALIZED_READY_FOR_NEXT_ATTEMPT
    ):
        blockers.append("post_submit_finalize_not_ready_for_next_attempt")
    if post_submit_finalize_packet.next_attempt_gate.status != (
        RuntimeNextAttemptGateStatus.READY_FOR_FRESH_SIGNAL
    ):
        blockers.append("post_submit_next_attempt_gate_not_ready")
    blockers.extend(post_submit_finalize_packet.blockers)
    blockers.extend(post_submit_finalize_packet.next_attempt_gate.blockers)
    return _dedupe(blockers)


def _packet_from_planning_result(
    *,
    post_submit_finalize_packet: RuntimePostSubmitFinalizePacket,
    runtime: StrategyRuntimeInstance,
    signal_input: StrategyFamilySignalInput,
    planning_result: RuntimeStrategySignalCandidatePlanningResult,
    metadata: dict | None,
) -> RuntimeNextAttemptStrategyPlanningPacket:
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
    return _packet(
        post_submit_finalize_packet=post_submit_finalize_packet,
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
        warnings=list(post_submit_finalize_packet.warnings)
        + list(planning_result.warnings),
        operator_next_step=operator_next_step,
        metadata={
            "strategy_signal_planner_called": True,
            "fresh_signal_evaluation_id": signal_input.evaluation_id,
            "candidate_planning_status": planning_result.status.value,
            **(metadata or {}),
        },
    )


def _packet(
    *,
    post_submit_finalize_packet: RuntimePostSubmitFinalizePacket,
    runtime: StrategyRuntimeInstance,
    signal_input: StrategyFamilySignalInput,
    status: RuntimeNextAttemptStrategyPlanningStatus,
    blockers: list[str] | None = None,
    warnings: list[str] | None = None,
    operator_next_step: str,
    planning_result: RuntimeStrategySignalCandidatePlanningResult | None = None,
    order_candidate_id: str | None = None,
    metadata: dict | None = None,
) -> RuntimeNextAttemptStrategyPlanningPacket:
    return RuntimeNextAttemptStrategyPlanningPacket(
        packet_id=(
            "runtime-next-attempt-strategy-planning-"
            f"{post_submit_finalize_packet.authorization_id}-"
            f"{signal_input.evaluation_id}"
        ),
        runtime_instance_id=runtime.runtime_instance_id,
        source_authorization_id=post_submit_finalize_packet.authorization_id,
        post_submit_finalize_packet_id=post_submit_finalize_packet.packet_id,
        status=status,
        next_attempt_gate_status=post_submit_finalize_packet.next_attempt_gate.status,
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
        operator_command_plan={
            "scope": "runtime_next_attempt_strategy_planning_operator_command_plan",
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


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
