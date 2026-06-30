"""Shared readiness/actionability separation.

This module classifies readiness booleans only. It does not create Execution
Attempt, FinalGate, Operation Layer, exchange-write, or real-order authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


AUTHORITATIVE_SOURCE_FALSE_KEYS = (
    "primary_judgment_source",
    "tradeability_decision_source",
    "execution_attempt_source",
)
NON_EXECUTING_SIDE_EFFECT_FALSE_KEYS = (
    "final_gate_called",
    "operation_layer_called",
    "exchange_write_called",
    "order_created",
    "live_profile_changed",
    "order_sizing_defaults_changed",
    "withdrawal_or_transfer_created",
)
AUTHORITY_ERROR_SUFFIX = {
    "primary_judgment_source": "must_not_be_primary",
    "tradeability_decision_source": "must_not_answer_tradeability",
    "execution_attempt_source": "must_not_open_execution_attempt",
}


@dataclass(frozen=True)
class ReadinessSeparation:
    trial_eligible: bool = False
    tiny_live_ready: bool = False
    pre_live_rehearsal_ready: bool = False
    live_submit_ready: bool = False
    ready_for_finalgate_checkpoint: bool = False
    fresh_signal_state: str = ""
    live_submit_ready_false_reason: str = ""
    source: str = "runtime_safety_state"
    scoped_strategy_group_ids: tuple[str, ...] = ()

    @property
    def can_create_execution_attempt(self) -> bool:
        return self.live_submit_ready and self.ready_for_finalgate_checkpoint

    def scoped_to(self, strategy_group_id: str) -> bool:
        return (
            self.can_create_execution_attempt
            and bool(strategy_group_id)
            and strategy_group_id in self.scoped_strategy_group_ids
        )

    def as_read_model(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "trial_eligible": self.trial_eligible,
            "tiny_live_ready": self.tiny_live_ready,
            "pre_live_rehearsal_ready": self.pre_live_rehearsal_ready,
            "live_submit_ready": self.live_submit_ready,
            "ready_for_finalgate_checkpoint": self.ready_for_finalgate_checkpoint,
            "fresh_signal_state": self.fresh_signal_state,
            "live_submit_ready_false_reason": self.live_submit_ready_false_reason,
            "can_create_execution_attempt": self.can_create_execution_attempt,
            "execution_attempt_required_for_lifecycle_entry": True,
            "scoped_strategy_group_ids": list(self.scoped_strategy_group_ids),
            "trial_eligible_source": "Strategy Asset State / Owner policy",
            "tiny_live_ready_source": "Tradeability Decision / Runtime Safety State",
            "pre_live_rehearsal_ready_source": "Runtime Safety rehearsal",
            "live_submit_ready_source": "Runtime Safety action-time chain",
        }


@dataclass(frozen=True)
class RuntimeSafetyCandidateAuthorization:
    state_source: str
    strategy_group_id: str
    status: str
    primary_judgment_source: bool = False
    shadow_candidate_evidence_ready: bool = False
    authorization_evidence_created: bool = False
    ready_for_finalgate_checkpoint: bool = False
    first_blocker_class: str = ""
    next_runtime_step: str = ""

    def as_read_model(self) -> dict[str, Any]:
        return {
            "state_family": "Runtime Safety State",
            "state_role": "candidate_authorization",
            "state_source": self.state_source,
            "strategy_group_id": self.strategy_group_id,
            "status": self.status,
            "primary_judgment_source": self.primary_judgment_source,
            "shadow_candidate_evidence_ready": self.shadow_candidate_evidence_ready,
            "authorization_evidence_created": self.authorization_evidence_created,
            "ready_for_finalgate_checkpoint": self.ready_for_finalgate_checkpoint,
            "first_blocker_class": self.first_blocker_class,
            "next_runtime_step": self.next_runtime_step,
            "execution_attempt_required_for_lifecycle_entry": True,
        }


def candidate_authorization_state_from_source(
    source: dict[str, Any],
    *,
    default_source: str = "runtime_safety_candidate_authorization",
) -> dict[str, Any]:
    if not isinstance(source, dict) or not source:
        return {}
    return RuntimeSafetyCandidateAuthorization(
        state_source=str(source.get("state_source") or default_source),
        strategy_group_id=str(source.get("strategy_group_id") or ""),
        status=str(source.get("status") or "candidate_authorization_not_reached"),
        primary_judgment_source=False,
        shadow_candidate_evidence_ready=(
            source.get("shadow_candidate_evidence_ready") is True
        ),
        authorization_evidence_created=(
            source.get("authorization_evidence_created") is True
        ),
        ready_for_finalgate_checkpoint=(
            source.get("ready_for_finalgate_checkpoint") is True
        ),
        first_blocker_class=str(source.get("first_blocker_class") or ""),
        next_runtime_step=str(source.get("next_runtime_step") or ""),
    ).as_read_model()


def candidate_authorization_state_from_runtime_safety_artifact(
    artifact: dict[str, Any],
    *,
    strategy_group_id: str | None = None,
) -> dict[str, Any]:
    runtime_safety = runtime_safety_state_from_artifact(artifact)
    state = runtime_safety.get("candidate_authorization_state")
    if (
        not isinstance(state, dict)
        or state.get("state_role") != "candidate_authorization"
    ):
        return {}
    state_strategy_group_id = str(state.get("strategy_group_id") or "")
    if (
        strategy_group_id
        and state_strategy_group_id
        and state_strategy_group_id != strategy_group_id
    ):
        return {}
    return candidate_authorization_state_from_source(state)


def runtime_safety_state_from_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    state = artifact.get("runtime_safety_state")
    return state if isinstance(state, dict) else {}


def scoped_strategy_group_ids_from_artifact(artifact: dict[str, Any]) -> tuple[str, ...]:
    ids: set[str] = set()
    id_keys = {
        "strategy_group_id",
        "selected_strategy_group_id",
        "selected_strategygroup_id",
        "runtime_strategy_group_id",
        "live_strategy_group_id",
    }
    ids_keys = {
        "strategy_group_ids",
        "selected_strategy_group_ids",
        "runtime_strategy_group_ids",
        "live_strategy_group_ids",
    }

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in id_keys and isinstance(item, str) and item:
                    ids.add(item)
                elif key in ids_keys and isinstance(item, list):
                    ids.update(str(entry) for entry in item if str(entry))
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(artifact)
    return tuple(sorted(ids))


def readiness_separation_from_runtime_safety_state(
    state: dict[str, Any],
    *,
    scoped_ids: tuple[str, ...] = (),
    trial_eligible: bool = False,
    tiny_live_ready: bool = False,
    source: str = "runtime_safety_state",
) -> ReadinessSeparation:
    return ReadinessSeparation(
        trial_eligible=trial_eligible,
        tiny_live_ready=tiny_live_ready,
        pre_live_rehearsal_ready=state.get("pre_live_rehearsal_ready") is True,
        live_submit_ready=state.get("live_submit_ready") is True,
        ready_for_finalgate_checkpoint=(
            state.get("ready_for_finalgate_checkpoint") is True
        ),
        fresh_signal_state=str(state.get("fresh_signal_state") or ""),
        live_submit_ready_false_reason=str(
            state.get("live_submit_ready_false_reason") or ""
        ),
        source=source,
        scoped_strategy_group_ids=scoped_ids,
    )


def readiness_separation_from_runtime_safety_artifact(
    artifact: dict[str, Any],
) -> ReadinessSeparation:
    return readiness_separation_from_runtime_safety_state(
        runtime_safety_state_from_artifact(artifact),
        scoped_ids=scoped_strategy_group_ids_from_artifact(artifact),
        source="runtime_safety_state",
    )


def live_submit_ready_for_strategy_artifact(
    *,
    artifact: dict[str, Any],
    strategy_group_id: str,
) -> bool:
    return readiness_separation_from_runtime_safety_artifact(artifact).scoped_to(
        strategy_group_id
    )


def non_authoritative_state_errors(
    state: dict[str, Any],
    *,
    error_prefix: str,
    false_keys: tuple[str, ...],
) -> list[str]:
    errors: list[str] = []
    for key in false_keys:
        if state.get(key) is False:
            continue
        suffix = AUTHORITY_ERROR_SUFFIX.get(key)
        if suffix:
            errors.append(f"{error_prefix}_{suffix}")
        else:
            errors.append(f"{error_prefix}_not_false:{key}")
    return errors


def false_flag_errors(
    flags: dict[str, Any],
    *,
    error_prefix: str,
    false_keys: tuple[str, ...],
) -> list[str]:
    return [
        f"{error_prefix}_not_false:{key}"
        for key in false_keys
        if flags.get(key) is not False
    ]
