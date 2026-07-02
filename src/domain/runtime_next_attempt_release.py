"""Runtime next-attempt release evidence.

This evidence object joins the post-close evidence surfaces:

RuntimeActivePositionResolutionArtifact
-> optional next-attempt gate evidence
-> release decision for strategy signal observation / shadow planning

It is lifecycle evidence only. It does not create ExecutionIntents, create orders, call
OrderLifecycle, call exchange write APIs, close positions, mutate runtime state,
transfer funds, or withdraw funds.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.runtime_active_position_resolution import (
    RuntimeActivePositionResolutionArtifact,
    RuntimeActivePositionResolutionStatus,
)


class RuntimeNextAttemptReleaseStatus(str, Enum):
    BLOCKED = "blocked"
    WAITING_FOR_POSITION_RESOLUTION = "waiting_for_position_resolution"
    WAITING_FOR_CLOSED_REVIEW = "waiting_for_closed_review"
    WAITING_FOR_NEXT_ATTEMPT_GATE = "waiting_for_next_attempt_gate"
    READY_FOR_STRATEGY_SIGNAL = "ready_for_strategy_signal"


class RuntimeNextAttemptReleaseEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    release_evidence_id: str = Field(min_length=1, max_length=420)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    symbol: str = Field(min_length=1, max_length=128)
    side: str = Field(min_length=1, max_length=32)
    status: RuntimeNextAttemptReleaseStatus
    active_position_resolution_status: str = Field(min_length=1, max_length=128)
    next_attempt_gate_status: str | None = Field(default=None, max_length=128)
    next_attempt_gate_name: str | None = Field(default=None, max_length=128)
    active_position_present: bool
    closed_review_recorded: bool
    next_attempt_blocked_by_active_position: bool
    strategy_signal_observation_allowed: bool
    shadow_candidate_planning_allowed: bool
    executable_submit_allowed: Literal[False] = False
    requires_fresh_strategy_signal: Literal[True] = True
    requires_fresh_authorization: Literal[True] = True
    requires_official_final_gate: Literal[True] = True
    consumed_authorization_replay_only: Literal[True] = True
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    required_steps: list[str] = Field(default_factory=list)
    completed_steps: list[str] = Field(default_factory=list)
    recommended_review_checkpoint: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    next_attempt_release_evidence_only: Literal[True] = True
    not_order: Literal[True] = True
    not_execution_intent: Literal[True] = True
    not_execution_authority: Literal[True] = True
    exchange_called: Literal[False] = False
    exchange_write_called: Literal[False] = False
    exchange_order_submitted: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    order_created: Literal[False] = False
    order_cancelled: Literal[False] = False
    position_closed: Literal[False] = False
    runtime_state_mutated: Literal[False] = False
    withdrawal_instruction_created: Literal[False] = False
    transfer_instruction_created: Literal[False] = False
    created_at_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def _status_contract(self) -> "RuntimeNextAttemptReleaseEvidence":
        if self.status == RuntimeNextAttemptReleaseStatus.BLOCKED and not self.blockers:
            raise ValueError("blocked release evidence requires blockers")
        if self.status == RuntimeNextAttemptReleaseStatus.READY_FOR_STRATEGY_SIGNAL:
            if self.blockers:
                raise ValueError("ready release evidence cannot have blockers")
            if not self.strategy_signal_observation_allowed:
                raise ValueError("ready release evidence must allow strategy observation")
            if not self.shadow_candidate_planning_allowed:
                raise ValueError("ready release evidence must allow shadow planning")
        return self


def build_runtime_next_attempt_release_evidence(
    *,
    active_position_resolution: RuntimeActivePositionResolutionArtifact,
    next_attempt_gate_evidence: dict[str, Any] | None,
    now_ms: int,
) -> RuntimeNextAttemptReleaseEvidence:
    """Build non-executing release evidence from already-generated evidence."""

    resolution = active_position_resolution
    gate = _extract_gate(next_attempt_gate_evidence)
    gate_status = _gate_status(next_attempt_gate_evidence, gate)
    gate_name = _gate_name(gate)
    warnings = _dedupe([
        *resolution.warnings,
        *_gate_warnings(next_attempt_gate_evidence, gate),
    ])
    blockers: list[str] = []
    required_steps: list[str] = []
    completed_steps = ["active_position_resolution_read"]
    status: RuntimeNextAttemptReleaseStatus
    recommended: str

    if resolution.status == RuntimeActivePositionResolutionStatus.BLOCKED:
        status = RuntimeNextAttemptReleaseStatus.BLOCKED
        blockers.extend(resolution.blockers or ["active_position_resolution_blocked"])
        recommended = "resolve_active_position_resolution_blockers"
        required_steps = list(resolution.required_steps)
    elif resolution.status in {
        RuntimeActivePositionResolutionStatus.HOLD_WITH_HARD_STOP,
        RuntimeActivePositionResolutionStatus.WAITING_FOR_OWNER_CLOSE_AUTHORIZATION,
    }:
        status = RuntimeNextAttemptReleaseStatus.WAITING_FOR_POSITION_RESOLUTION
        recommended = resolution.recommended_review_checkpoint
        required_steps = list(resolution.required_steps)
    elif resolution.status == RuntimeActivePositionResolutionStatus.READY_FOR_CLOSED_REVIEW:
        status = RuntimeNextAttemptReleaseStatus.WAITING_FOR_CLOSED_REVIEW
        recommended = "record_runtime_closed_trade_review_before_next_attempt_release"
        required_steps = list(resolution.required_steps)
        completed_steps.extend(resolution.completed_steps)
    elif next_attempt_gate_evidence is None:
        status = RuntimeNextAttemptReleaseStatus.WAITING_FOR_NEXT_ATTEMPT_GATE
        recommended = "run_non_executing_next_attempt_gate_evidence"
        required_steps = ["verify_next_attempt_gate"]
        completed_steps.extend(resolution.completed_steps)
    elif _gate_clear(next_attempt_gate_evidence, gate):
        status = RuntimeNextAttemptReleaseStatus.READY_FOR_STRATEGY_SIGNAL
        recommended = "resume_strategy_signal_observation_and_shadow_planning"
        required_steps = [
            "wait_for_fresh_strategy_signal",
            "run_semantic_gate",
            "plan_shadow_order_candidate",
            "run_official_final_gate_before_any_submit",
        ]
        completed_steps.extend([
            *resolution.completed_steps,
            "next_attempt_gate_clear",
        ])
    else:
        status = RuntimeNextAttemptReleaseStatus.BLOCKED
        blockers.extend(_gate_blockers(next_attempt_gate_evidence, gate))
        if not blockers:
            blockers.append("next_attempt_gate_not_clear")
        recommended = (
            _required_next_step(next_attempt_gate_evidence)
            or "resolve_next_attempt_gate_blocker"
        )
        required_steps = ["verify_next_attempt_gate_after_blocker_resolution"]
        completed_steps.extend(resolution.completed_steps)

    ready = status == RuntimeNextAttemptReleaseStatus.READY_FOR_STRATEGY_SIGNAL
    return RuntimeNextAttemptReleaseEvidence(
        release_evidence_id=(
            f"runtime-next-attempt-release-"
            f"{resolution.runtime_instance_id}-{now_ms}"
        ),
        runtime_instance_id=resolution.runtime_instance_id,
        symbol=resolution.symbol,
        side=resolution.side,
        status=status,
        active_position_resolution_status=resolution.status.value,
        next_attempt_gate_status=gate_status,
        next_attempt_gate_name=gate_name,
        active_position_present=resolution.active_position_present,
        closed_review_recorded=resolution.closed_review_recorded,
        next_attempt_blocked_by_active_position=(
            resolution.next_attempt_blocked_by_active_position
        ),
        strategy_signal_observation_allowed=ready,
        shadow_candidate_planning_allowed=ready,
        blockers=_dedupe(blockers),
        warnings=warnings,
        required_steps=_dedupe(required_steps),
        completed_steps=_dedupe(completed_steps),
        recommended_review_checkpoint=recommended,
        metadata={
            "scope": "runtime_next_attempt_release",
            "right_tail_objective": (
                "Release resumes bounded strategy observation after flat/review/gate "
                "proof; it does not authorize executable submit."
            ),
            "does_not_submit_order": True,
            "does_not_create_execution_intent": True,
        },
        created_at_ms=now_ms,
    )


def _extract_gate(artifact: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(artifact, dict):
        return {}
    gate = artifact.get("next_attempt_gate")
    return gate if isinstance(gate, dict) else {}


def _gate_clear(artifact: dict[str, Any], gate: dict[str, Any]) -> bool:
    return bool(
        artifact.get("status") == "clear_for_next_attempt_preflight"
        or (
            gate.get("status") == "clear_for_preflight"
            and gate.get("next_attempt_allowed_by_lifecycle") is True
        )
    )


def _gate_status(artifact: dict[str, Any] | None, gate: dict[str, Any]) -> str | None:
    if not isinstance(artifact, dict):
        return None
    value = gate.get("status") or artifact.get("status")
    return str(value) if value else None


def _gate_name(gate: dict[str, Any]) -> str | None:
    value = gate.get("gate")
    return str(value) if value else None


def _gate_warnings(artifact: dict[str, Any] | None, gate: dict[str, Any]) -> list[str]:
    if not isinstance(artifact, dict):
        return []
    values: list[Any] = []
    values.extend(artifact.get("warnings") or [])
    values.extend(gate.get("warnings") or [])
    return [str(value) for value in values if value]


def _gate_blockers(artifact: dict[str, Any] | None, gate: dict[str, Any]) -> list[str]:
    if not isinstance(artifact, dict):
        return ["next_attempt_gate_evidence_missing"]
    blockers: list[str] = []
    for item in artifact.get("blockers") or []:
        blockers.append(_blocker_id(item))
    for item in gate.get("blockers") or []:
        blockers.append(_blocker_id(item))
    return [item for item in blockers if item]


def _blocker_id(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("id") or value.get("code") or value)
    return str(value)


def _required_next_step(artifact: dict[str, Any] | None) -> str | None:
    if not isinstance(artifact, dict):
        return None
    value = artifact.get("required_next_step")
    return str(value) if value else None


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result
