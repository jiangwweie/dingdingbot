"""Official submit preview artifact for runtime executable readiness.

This preview adapts a ready runtime executable-submit artifact to the existing
Trading Console official submit endpoint. It never calls the endpoint, creates
orders, calls OrderLifecycle, or touches exchange. Its job is to freeze the
fresh authorization and evidence IDs that a later explicit submit action must
use, while preventing consumed authorization replay.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.standing_authorization import (
    OWNER_STANDING_AUTHORIZATION_REFERENCE,
    standing_authorization_metadata,
)
from src.domain.runtime_executable_submit_readiness import (
    RuntimeExecutableSubmitReadinessArtifact,
    RuntimeExecutableSubmitReadinessStatus,
)


class RuntimeOfficialSubmitHandoffModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeOfficialSubmitHandoffStatus(str, Enum):
    BLOCKED = "blocked"
    READY_FOR_OFFICIAL_SUBMIT_CALL = "ready_for_official_submit_call"


class RuntimeOfficialSubmitHandoffMode(str, Enum):
    DISABLED_SMOKE = "disabled_smoke"
    REAL_GATEWAY_ACTION = "real_gateway_action"


class RuntimeOfficialSubmitHandoffArtifact(RuntimeOfficialSubmitHandoffModel):
    handoff_id: str = Field(min_length=1, max_length=840)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    readiness_artifact_id: str = Field(min_length=1, max_length=720)
    source_consumed_authorization_id: str = Field(min_length=1, max_length=220)
    fresh_submit_authorization_id: str | None = Field(default=None, max_length=260)
    mode: RuntimeOfficialSubmitHandoffMode
    status: RuntimeOfficialSubmitHandoffStatus
    official_endpoint_method: Literal["POST"] = "POST"
    official_endpoint_path: str = Field(min_length=1, max_length=520)
    official_query: dict[str, Any] = Field(default_factory=dict)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    readiness_snapshot: dict[str, Any] = Field(default_factory=dict)
    ready_for_official_submit_call: bool = False
    requires_fresh_submit_authorization: Literal[True] = True
    consumed_authorization_replay_allowed: Literal[False] = False
    uses_existing_official_submit_endpoint: Literal[True] = True
    creates_alternate_execution_path: Literal[False] = False
    not_exchange_submit_execution: Literal[True] = True
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
    def _validate_artifact(self) -> "RuntimeOfficialSubmitHandoffArtifact":
        _reject_forbidden_execution_fields(
            "runtime official submit handoff",
            {"metadata": self.metadata, "official_query": self.official_query},
        )
        if (
            self.status
            == RuntimeOfficialSubmitHandoffStatus.READY_FOR_OFFICIAL_SUBMIT_CALL
            and self.blockers
        ):
            raise ValueError("ready official submit handoff cannot have blockers")
        if self.ready_for_official_submit_call != (
            self.status
            == RuntimeOfficialSubmitHandoffStatus.READY_FOR_OFFICIAL_SUBMIT_CALL
        ):
            raise ValueError("ready flag must match handoff status")
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
            raise ValueError("official submit handoff cannot perform execution")
        return self


def build_runtime_official_submit_handoff_artifact(
    *,
    readiness_artifact: RuntimeExecutableSubmitReadinessArtifact,
    fresh_submit_authorization_id: str | None,
    mode: RuntimeOfficialSubmitHandoffMode = (
        RuntimeOfficialSubmitHandoffMode.DISABLED_SMOKE
    ),
    owner_confirmed_for_real_submit_action: bool = True,
    additional_blockers: list[str] | None = None,
    additional_warnings: list[str] | None = None,
    now_ms: int,
) -> RuntimeOfficialSubmitHandoffArtifact:
    blockers: list[str] = []
    warnings: list[str] = list(readiness_artifact.warnings)

    if readiness_artifact.status != (
        RuntimeExecutableSubmitReadinessStatus.READY_FOR_EXECUTABLE_SUBMIT
    ):
        blockers.append("readiness_not_ready_for_executable_submit")
        blockers.extend(f"readiness:{item}" for item in readiness_artifact.blockers)
    _append_side_effect_blockers("readiness", readiness_artifact, blockers)

    fresh_authorization = _optional_str(fresh_submit_authorization_id)
    if not fresh_authorization:
        blockers.append("fresh_submit_authorization_id_missing")
    elif fresh_authorization == readiness_artifact.source_authorization_id:
        blockers.append("fresh_submit_authorization_reuses_consumed_authorization")

    if (
        mode == RuntimeOfficialSubmitHandoffMode.REAL_GATEWAY_ACTION
        and not owner_confirmed_for_real_submit_action
    ):
        warnings.append(
            "real_gateway_action_owner_confirmation_false_ignored_under_"
            "standing_authorization"
        )

    evidence = readiness_artifact.evidence
    query = {
        "trusted_submit_fact_snapshot_id": evidence.trusted_submit_fact_snapshot_id,
        "submit_idempotency_policy_id": evidence.submit_idempotency_policy_id,
        "attempt_outcome_policy_id": evidence.attempt_outcome_policy_id,
        "protection_creation_failure_policy_id": (
            evidence.protection_creation_failure_policy_id
        ),
        "local_registration_enablement_decision_id": (
            evidence.local_registration_enablement_decision_id
        ),
        "owner_real_submit_authorization_id": (
            evidence.owner_real_submit_authorization_id
            or evidence.runtime_grant_authorization_id
        ),
        "order_lifecycle_submit_enablement_id": (
            evidence.order_lifecycle_submit_enablement_id
        ),
        "exchange_submit_adapter_enablement_id": (
            evidence.exchange_submit_adapter_enablement_id
        ),
        "exchange_submit_action_authorization_id": (
            evidence.exchange_submit_action_authorization_id
        ),
        "deployment_readiness_evidence_id": (
            evidence.deployment_readiness_evidence_id
        ),
        "owner_confirmed_for_first_real_submit_action": (
            mode == RuntimeOfficialSubmitHandoffMode.REAL_GATEWAY_ACTION
        ),
    }
    missing_query_keys = [
        key for key, value in query.items()
        if key != "owner_confirmed_for_first_real_submit_action"
        and not _present(str(value) if value is not None else None)
    ]
    blockers.extend(f"official_query_{key}_missing" for key in missing_query_keys)
    blockers.extend(additional_blockers or [])
    warnings.extend(additional_warnings or [])
    blockers = _dedupe(blockers)
    warnings = _dedupe(warnings)
    status = (
        RuntimeOfficialSubmitHandoffStatus.BLOCKED
        if blockers
        else RuntimeOfficialSubmitHandoffStatus.READY_FOR_OFFICIAL_SUBMIT_CALL
    )
    endpoint_path = (
        "/api/trading-console/"
        "runtime-execution-first-real-submit-actions/authorizations/"
        f"{fresh_authorization or 'FRESH_SUBMIT_AUTHORIZATION_REQUIRED'}"
    )
    return RuntimeOfficialSubmitHandoffArtifact(
        handoff_id=(
            "runtime-official-submit-handoff-"
            f"{readiness_artifact.runtime_instance_id}-"
            f"{readiness_artifact.source_strategy_planning_artifact_id}"
        ),
        runtime_instance_id=readiness_artifact.runtime_instance_id,
        readiness_artifact_id=readiness_artifact.artifact_id,
        source_consumed_authorization_id=readiness_artifact.source_authorization_id,
        fresh_submit_authorization_id=fresh_authorization,
        mode=mode,
        status=status,
        official_endpoint_path=endpoint_path,
        official_query={key: value for key, value in query.items() if value is not None},
        blockers=blockers,
        warnings=warnings,
        readiness_snapshot={
            "status": readiness_artifact.status.value,
            "order_candidate_id": readiness_artifact.order_candidate_id,
            "signal_evaluation_id": readiness_artifact.signal_evaluation_id,
            "source_strategy_planning_artifact_id": (
                readiness_artifact.source_strategy_planning_artifact_id
            ),
            "source_release_evidence_id": readiness_artifact.source_release_evidence_id,
            "executable_submit_ready": readiness_artifact.executable_submit_ready,
        },
        ready_for_official_submit_call=(
            status == RuntimeOfficialSubmitHandoffStatus.READY_FOR_OFFICIAL_SUBMIT_CALL
        ),
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_official_submit_handoff",
            "read_only_submit_projection": True,
            "execution_attempt_source": False,
            "lifecycle_authority": False,
            **standing_authorization_metadata(
                scope="runtime_official_submit_handoff"
            ),
            "owner_confirmation_reference": OWNER_STANDING_AUTHORIZATION_REFERENCE,
            "uses_existing_first_real_submit_endpoint": True,
            "does_not_call_official_endpoint": True,
            "does_not_create_execution_intent": True,
            "does_not_create_order": True,
            "does_not_call_order_lifecycle": True,
            "does_not_call_exchange": True,
            "does_not_create_withdrawal_or_transfer": True,
        },
    )


def _append_side_effect_blockers(
    prefix: str,
    artifact: Any,
    blockers: list[str],
) -> None:
    side_effect_flags = {
        "execution_intent_created": "created_execution_intent",
        "executable_execution_intent_created": "created_executable_intent",
        "order_created": "created_order",
        "order_lifecycle_called": "called_order_lifecycle",
        "exchange_called": "called_exchange",
        "exchange_order_submitted": "submitted_exchange_order",
        "runtime_state_mutated": "mutated_runtime_state",
        "withdrawal_or_transfer_created": "created_withdrawal_or_transfer",
    }
    for attr, suffix in side_effect_flags.items():
        if getattr(artifact, attr, False):
            blockers.append(f"{prefix}_{suffix}")


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
