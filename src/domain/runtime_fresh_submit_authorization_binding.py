"""Create or bind a persisted fresh submit authorization for a handoff."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.runtime_execution_submit_authorization import (
    RuntimeExecutionSubmitAuthorization,
)
from src.domain.runtime_fresh_submit_authorization_resolution import (
    RuntimeFreshSubmitAuthorizationResolutionArtifact,
    RuntimeFreshSubmitAuthorizationResolutionStatus,
)
from src.domain.runtime_official_submit_handoff import RuntimeOfficialSubmitHandoffArtifact


class RuntimeFreshSubmitAuthorizationBindingModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeFreshSubmitAuthorizationBindingStatus(str, Enum):
    BLOCKED = "blocked"
    BOUND_EXISTING_AUTHORIZATION = "bound_existing_authorization"
    CREATED_AUTHORIZATION = "created_authorization"
    CREATED_INTENT_AND_AUTHORIZATION = "created_intent_and_authorization"


class RuntimeFreshSubmitAuthorizationBindingSource(str, Enum):
    EXISTING_RESOLUTION = "existing_resolution"
    EXISTING_INTENT = "existing_intent"
    LATEST_READY_DRAFT = "latest_ready_draft"
    UNRESOLVED = "unresolved"


class RuntimeFreshSubmitAuthorizationBindingArtifact(
    RuntimeFreshSubmitAuthorizationBindingModel
):
    binding_id: str = Field(min_length=1, max_length=900)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    handoff_id: str = Field(min_length=1, max_length=840)
    readiness_artifact_id: str = Field(min_length=1, max_length=720)
    status: RuntimeFreshSubmitAuthorizationBindingStatus
    binding_source: RuntimeFreshSubmitAuthorizationBindingSource
    order_candidate_id: str | None = Field(default=None, max_length=128)
    signal_evaluation_id: str | None = Field(default=None, max_length=128)
    execution_intent_id: str | None = Field(default=None, max_length=128)
    runtime_execution_intent_draft_id: str | None = Field(default=None, max_length=180)
    fresh_submit_authorization_id: str | None = Field(default=None, max_length=260)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    resolution_snapshot: dict[str, Any] = Field(default_factory=dict)
    authorization_snapshot: dict[str, Any] = Field(default_factory=dict)
    ready_for_fresh_authorization_resolution: bool = False
    ready_for_disabled_smoke_call: bool = False
    creates_execution_intent: bool = False
    creates_submit_authorization: bool = False
    calls_official_submit_endpoint: Literal[False] = False
    requests_real_gateway_action: Literal[False] = False
    order_created: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    exchange_called: Literal[False] = False
    exchange_order_submitted: Literal[False] = False
    runtime_state_mutated: Literal[False] = False
    withdrawal_or_transfer_created: Literal[False] = False
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_binding(self) -> "RuntimeFreshSubmitAuthorizationBindingArtifact":
        if self.status != RuntimeFreshSubmitAuthorizationBindingStatus.BLOCKED:
            if self.blockers:
                raise ValueError("ready fresh authorization binding cannot have blockers")
            if not self.fresh_submit_authorization_id:
                raise ValueError("fresh submit authorization id missing")
            if not self.execution_intent_id:
                raise ValueError("execution intent id missing")
            if not self.ready_for_fresh_authorization_resolution:
                raise ValueError("binding must be ready for fresh resolution")
            if not self.ready_for_disabled_smoke_call:
                raise ValueError("binding must be ready for disabled smoke")
        return self


def build_runtime_fresh_submit_authorization_binding_artifact(
    *,
    handoff: RuntimeOfficialSubmitHandoffArtifact,
    resolution: RuntimeFreshSubmitAuthorizationResolutionArtifact | None,
    authorization: RuntimeExecutionSubmitAuthorization | None,
    status: RuntimeFreshSubmitAuthorizationBindingStatus,
    binding_source: RuntimeFreshSubmitAuthorizationBindingSource,
    execution_intent_id: str | None,
    runtime_execution_intent_draft_id: str | None,
    creates_execution_intent: bool,
    creates_submit_authorization: bool,
    additional_blockers: list[str] | None = None,
    additional_warnings: list[str] | None = None,
    now_ms: int,
) -> RuntimeFreshSubmitAuthorizationBindingArtifact:
    blockers = _dedupe(additional_blockers or [])
    warnings = _dedupe(list(handoff.warnings) + list(additional_warnings or []))
    if (
        status != RuntimeFreshSubmitAuthorizationBindingStatus.BLOCKED
        and authorization is None
    ):
        blockers.append("fresh_submit_authorization_missing_after_binding")
        status = RuntimeFreshSubmitAuthorizationBindingStatus.BLOCKED
    return RuntimeFreshSubmitAuthorizationBindingArtifact(
        binding_id=(
            "runtime-fresh-submit-authorization-binding-"
            f"{handoff.runtime_instance_id}-{handoff.readiness_artifact_id}"
        ),
        runtime_instance_id=handoff.runtime_instance_id,
        handoff_id=handoff.handoff_id,
        readiness_artifact_id=handoff.readiness_artifact_id,
        status=status,
        binding_source=binding_source,
        order_candidate_id=_optional_str(
            handoff.readiness_snapshot.get("order_candidate_id")
        ),
        signal_evaluation_id=_optional_str(
            handoff.readiness_snapshot.get("signal_evaluation_id")
        ),
        execution_intent_id=execution_intent_id,
        runtime_execution_intent_draft_id=runtime_execution_intent_draft_id,
        fresh_submit_authorization_id=(
            authorization.authorization_id
            if authorization is not None
            and status != RuntimeFreshSubmitAuthorizationBindingStatus.BLOCKED
            else None
        ),
        blockers=_dedupe(blockers),
        warnings=warnings,
        resolution_snapshot=_resolution_snapshot(resolution),
        authorization_snapshot=_authorization_snapshot(authorization),
        ready_for_fresh_authorization_resolution=(
            status != RuntimeFreshSubmitAuthorizationBindingStatus.BLOCKED
        ),
        ready_for_disabled_smoke_call=(
            status != RuntimeFreshSubmitAuthorizationBindingStatus.BLOCKED
        ),
        creates_execution_intent=creates_execution_intent,
        creates_submit_authorization=creates_submit_authorization,
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_fresh_submit_authorization_binding",
            "does_not_call_official_submit_endpoint": True,
            "does_not_call_exchange": True,
            "does_not_call_order_lifecycle": True,
            "does_not_create_order": True,
            "does_not_create_withdrawal_or_transfer": True,
        },
    )


def _resolution_snapshot(
    resolution: RuntimeFreshSubmitAuthorizationResolutionArtifact | None,
) -> dict[str, Any]:
    if resolution is None:
        return {}
    return {
        "resolution_id": resolution.resolution_id,
        "status": resolution.status.value,
        "resolved_fresh_submit_authorization_id": (
            resolution.resolved_fresh_submit_authorization_id
        ),
        "resolution_source": resolution.resolution_source.value,
        "blockers": list(resolution.blockers),
    }


def _authorization_snapshot(
    authorization: RuntimeExecutionSubmitAuthorization | None,
) -> dict[str, Any]:
    if authorization is None:
        return {}
    return {
        "authorization_id": authorization.authorization_id,
        "execution_intent_id": authorization.execution_intent_id,
        "runtime_execution_intent_draft_id": (
            authorization.runtime_execution_intent_draft_id
        ),
        "runtime_instance_id": authorization.semantic_ids.runtime_instance_id,
        "signal_evaluation_id": authorization.semantic_ids.signal_evaluation_id,
        "order_candidate_id": authorization.semantic_ids.order_candidate_id,
        "status": authorization.status.value,
        "submit_executed": authorization.submit_executed,
        "order_created": authorization.order_created,
        "exchange_called": authorization.exchange_called,
        "order_lifecycle_called": authorization.order_lifecycle_called,
    }


def _optional_str(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result
