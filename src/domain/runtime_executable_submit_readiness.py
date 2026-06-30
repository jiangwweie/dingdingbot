"""Runtime-level executable submit readiness artifact.

This artifact is the non-executing boundary between a fresh, strategy-driven
runtime attempt and the official auditable submit path. It consolidates current
runtime evidence without pushing consumed or historical pre-submit rehearsal
artifacts back into the main loop.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RuntimeExecutableSubmitReadinessModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeExecutableSubmitReadinessStatus(str, Enum):
    BLOCKED = "blocked"
    READY_FOR_EXECUTABLE_SUBMIT = "ready_for_executable_submit"


class RuntimeExecutableSubmitReadinessEvidence(
    RuntimeExecutableSubmitReadinessModel
):
    """Current runtime evidence required before an executable submit call."""

    final_gate_preview_id: str | None = Field(default=None, max_length=360)
    final_gate_passed: bool = False
    runtime_grant_authorization_id: str | None = Field(default=None, max_length=260)
    owner_real_submit_authorization_id: str | None = Field(default=None, max_length=260)
    trusted_submit_fact_snapshot_id: str | None = Field(default=None, max_length=240)
    submit_idempotency_policy_id: str | None = Field(default=None, max_length=240)
    attempt_outcome_policy_id: str | None = Field(default=None, max_length=360)
    protection_creation_failure_policy_id: str | None = (
        Field(default=None, max_length=300)
    )
    local_registration_enablement_decision_id: str | None = (
        Field(default=None, max_length=300)
    )
    exchange_submit_enablement_decision_id: str | None = (
        Field(default=None, max_length=500)
    )
    exchange_submit_action_authorization_id: str | None = (
        Field(default=None, max_length=360)
    )
    order_lifecycle_submit_enablement_id: str | None = (
        Field(default=None, max_length=220)
    )
    exchange_submit_adapter_enablement_id: str | None = (
        Field(default=None, max_length=220)
    )
    deployment_readiness_evidence_id: str | None = Field(
        default=None,
        max_length=220,
    )
    protection_required_and_ready: bool = False
    active_position_source_trusted: bool = False
    account_facts_fresh: bool = False
    duplicate_submit_guard_ready: bool = False
    legacy_runtime_submit_rehearsal_id: str | None = Field(
        default=None,
        max_length=560,
    )
    durable_exchange_submit_execution_result_id: str | None = Field(
        default=None,
        max_length=540,
    )


class RuntimeExecutableSubmitReadinessArtifact(RuntimeExecutableSubmitReadinessModel):
    artifact_id: str = Field(min_length=1, max_length=720)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    source_release_evidence_id: str | None = Field(default=None, max_length=420)
    source_strategy_planning_artifact_id: str = Field(min_length=1, max_length=640)
    source_authorization_id: str = Field(min_length=1, max_length=220)
    signal_evaluation_id: str | None = Field(default=None, max_length=128)
    order_candidate_id: str | None = Field(default=None, max_length=128)
    strategy_planning_status: str = Field(min_length=1, max_length=128)
    status: RuntimeExecutableSubmitReadinessStatus
    evidence: RuntimeExecutableSubmitReadinessEvidence
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    executable_submit_ready: bool = False
    requires_official_order_lifecycle_path: Literal[True] = True
    requires_current_final_gate_pass: Literal[True] = True
    requires_fresh_strategy_candidate: Literal[True] = True
    legacy_pre_attempt_rehearsal_required: Literal[False] = False
    consumed_authorization_replay_only: Literal[True] = True
    not_exchange_submit_execution: Literal[True] = True
    not_order_lifecycle_authority: Literal[True] = True
    execution_intent_created: Literal[False] = False
    executable_execution_intent_created: Literal[False] = False
    order_created: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    exchange_called: Literal[False] = False
    exchange_order_submitted: Literal[False] = False
    runtime_state_mutated: Literal[False] = False
    withdrawal_or_transfer_created: Literal[False] = False
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_artifact(self) -> "RuntimeExecutableSubmitReadinessArtifact":
        _reject_forbidden_execution_fields(
            "runtime executable submit readiness",
            {"metadata": self.metadata},
        )
        if (
            self.status
            == RuntimeExecutableSubmitReadinessStatus.READY_FOR_EXECUTABLE_SUBMIT
            and self.blockers
        ):
            raise ValueError("ready executable submit readiness cannot have blockers")
        if self.executable_submit_ready != (
            self.status
            == RuntimeExecutableSubmitReadinessStatus.READY_FOR_EXECUTABLE_SUBMIT
        ):
            raise ValueError("executable_submit_ready must match readiness status")
        if (
            self.execution_intent_created
            or self.executable_execution_intent_created
            or self.order_created
            or self.order_lifecycle_called
            or self.exchange_called
            or self.exchange_order_submitted
            or self.runtime_state_mutated
            or self.withdrawal_or_transfer_created
        ):
            raise ValueError("executable submit readiness cannot perform execution")
        return self


def build_runtime_executable_submit_readiness_artifact(
    *,
    runtime_instance_id: str,
    source_strategy_planning_artifact_id: str,
    source_authorization_id: str,
    strategy_planning_status: str,
    evidence: RuntimeExecutableSubmitReadinessEvidence,
    order_candidate_id: str | None = None,
    signal_evaluation_id: str | None = None,
    source_release_evidence_id: str | None = None,
    first_real_submit_source_status: str | None = None,
    first_real_submit_source_blockers: list[str] | None = None,
    additional_blockers: list[str] | None = None,
    additional_warnings: list[str] | None = None,
    now_ms: int,
) -> RuntimeExecutableSubmitReadinessArtifact:
    blockers: list[str] = []
    warnings: list[str] = []

    if strategy_planning_status != "ready_for_final_gate_preflight":
        blockers.append("strategy_planning_not_ready_for_final_gate_preflight")
    if not _present(order_candidate_id):
        blockers.append("order_candidate_id_missing")
    if not _present(signal_evaluation_id):
        warnings.append("signal_evaluation_id_missing")
    if not _present(evidence.final_gate_preview_id):
        blockers.append("final_gate_preview_id_missing")
    if not evidence.final_gate_passed:
        blockers.append("final_gate_not_passed")
    if not (
        _present(evidence.runtime_grant_authorization_id)
        or _present(evidence.owner_real_submit_authorization_id)
    ):
        blockers.append("runtime_grant_or_owner_submit_authorization_missing")

    required_ids = {
        "trusted_submit_fact_snapshot_id": evidence.trusted_submit_fact_snapshot_id,
        "submit_idempotency_policy_id": evidence.submit_idempotency_policy_id,
        "attempt_outcome_policy_id": evidence.attempt_outcome_policy_id,
        "protection_creation_failure_policy_id": (
            evidence.protection_creation_failure_policy_id
        ),
        "local_registration_enablement_decision_id": (
            evidence.local_registration_enablement_decision_id
        ),
        "exchange_submit_enablement_decision_id": (
            evidence.exchange_submit_enablement_decision_id
        ),
        "exchange_submit_action_authorization_id": (
            evidence.exchange_submit_action_authorization_id
        ),
        "order_lifecycle_submit_enablement_id": (
            evidence.order_lifecycle_submit_enablement_id
        ),
        "exchange_submit_adapter_enablement_id": (
            evidence.exchange_submit_adapter_enablement_id
        ),
    }
    for key, value in required_ids.items():
        if not _present(value):
            blockers.append(f"{key}_missing")

    if not evidence.protection_required_and_ready:
        blockers.append("protection_required_not_ready")
    if not evidence.active_position_source_trusted:
        blockers.append("active_position_source_not_trusted")
    if not evidence.account_facts_fresh:
        blockers.append("account_facts_not_fresh")
    if not evidence.duplicate_submit_guard_ready:
        blockers.append("duplicate_submit_guard_not_ready")
    if not _present(evidence.deployment_readiness_evidence_id):
        warnings.append("deployment_readiness_evidence_id_missing")

    if not _present(evidence.legacy_runtime_submit_rehearsal_id):
        warnings.append("legacy_runtime_submit_rehearsal_id_not_required")
    if _present(evidence.durable_exchange_submit_execution_result_id):
        warnings.append("durable_execution_result_is_post_submit_evidence_only")

    first_real_submit_blockers = list(first_real_submit_source_blockers or [])
    if first_real_submit_source_status and first_real_submit_source_status not in {
        "ready_for_owner_final_review",
        "ready_for_executable_submit",
    }:
        if _runtime_grant_path_has_required_evidence(evidence=evidence):
            warnings.append(
                "first_real_submit_source_not_ready_but_runtime_grant_path_used"
            )
            warnings.extend(
                f"first_real_submit_source:{item}"
                for item in first_real_submit_blockers
            )
        else:
            blockers.append("first_real_submit_source_not_ready")
            blockers.extend(
                f"first_real_submit_source:{item}"
                for item in first_real_submit_blockers
            )

    blockers.extend(additional_blockers or [])
    warnings.extend(additional_warnings or [])
    blockers = _dedupe(blockers)
    warnings = _dedupe(warnings)
    status = (
        RuntimeExecutableSubmitReadinessStatus.BLOCKED
        if blockers
        else RuntimeExecutableSubmitReadinessStatus.READY_FOR_EXECUTABLE_SUBMIT
    )
    artifact_id = (
        "runtime-executable-submit-readiness-"
        f"{runtime_instance_id}-{source_strategy_planning_artifact_id}"
    )
    return RuntimeExecutableSubmitReadinessArtifact(
        artifact_id=artifact_id,
        runtime_instance_id=runtime_instance_id,
        source_release_evidence_id=_optional_str(source_release_evidence_id),
        source_strategy_planning_artifact_id=source_strategy_planning_artifact_id,
        source_authorization_id=source_authorization_id,
        signal_evaluation_id=_optional_str(signal_evaluation_id),
        order_candidate_id=_optional_str(order_candidate_id),
        strategy_planning_status=strategy_planning_status,
        status=status,
        evidence=evidence,
        blockers=blockers,
        warnings=warnings,
        executable_submit_ready=(
            status
            == RuntimeExecutableSubmitReadinessStatus.READY_FOR_EXECUTABLE_SUBMIT
        ),
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_executable_submit_readiness",
            "read_only_aggregation": True,
            "runtime_level_bounded_auto_attempt_chain": True,
            "legacy_pre_attempt_rehearsal_is_compatibility_evidence": True,
            "legacy_pre_attempt_rehearsal_required": False,
            "does_not_create_execution_intent": True,
            "does_not_create_order": True,
            "does_not_call_order_lifecycle": True,
            "does_not_call_exchange": True,
            "does_not_create_withdrawal_or_transfer": True,
        },
    )


def _runtime_grant_path_has_required_evidence(
    *,
    evidence: RuntimeExecutableSubmitReadinessEvidence,
) -> bool:
    return all(
        (
            evidence.final_gate_passed,
            _present(evidence.final_gate_preview_id),
            _present(evidence.runtime_grant_authorization_id)
            or _present(evidence.owner_real_submit_authorization_id),
            _present(evidence.trusted_submit_fact_snapshot_id),
            _present(evidence.submit_idempotency_policy_id),
            _present(evidence.attempt_outcome_policy_id),
            _present(evidence.protection_creation_failure_policy_id),
            _present(evidence.local_registration_enablement_decision_id),
            _present(evidence.exchange_submit_enablement_decision_id),
            _present(evidence.exchange_submit_action_authorization_id),
            _present(evidence.order_lifecycle_submit_enablement_id),
            _present(evidence.exchange_submit_adapter_enablement_id),
            evidence.protection_required_and_ready,
            evidence.active_position_source_trusted,
            evidence.account_facts_fresh,
            evidence.duplicate_submit_guard_ready,
        )
    )


def _present(value: str | None) -> bool:
    return bool(str(value or "").strip())


def _optional_str(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _reject_forbidden_execution_fields(context: str, value: Any) -> None:
    forbidden = {
        "client_order_id",
        "exchange_order_id",
        "exchange_payload",
        "order_id",
        "place_order",
        "submit_order",
        "transfer_payload",
        "withdrawal_payload",
    }
    for key in _walk_keys(value):
        if key.lower() in forbidden:
            raise ValueError(f"{context} contains forbidden execution field: {key}")


def _walk_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if isinstance(value, dict):
        for key, nested in value.items():
            keys.append(str(key))
            keys.extend(_walk_keys(nested))
    elif isinstance(value, list):
        for item in value:
            keys.extend(_walk_keys(item))
    return keys
