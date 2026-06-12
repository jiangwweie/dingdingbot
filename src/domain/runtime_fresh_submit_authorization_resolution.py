"""Resolve a persisted fresh submit authorization for official handoff.

The resolver is a non-executing bridge between a ready official-submit handoff
and the existing persisted RuntimeExecutionSubmitAuthorization record. It never
creates an authorization, calls the official submit endpoint, creates orders, or
touches exchange.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.runtime_execution_submit_authorization import (
    RuntimeExecutionSubmitAuthorization,
    RuntimeExecutionSubmitAuthorizationStatus,
)
from src.domain.runtime_official_submit_handoff import (
    RuntimeOfficialSubmitHandoffMode,
    RuntimeOfficialSubmitHandoffPacket,
    RuntimeOfficialSubmitHandoffStatus,
)


class RuntimeFreshSubmitAuthorizationResolutionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeFreshSubmitAuthorizationResolutionStatus(str, Enum):
    BLOCKED = "blocked"
    RESOLVED = "resolved"


class RuntimeFreshSubmitAuthorizationResolutionSource(str, Enum):
    EXPLICIT_AUTHORIZATION_ID = "explicit_authorization_id"
    HANDOFF_AUTHORIZATION_ID = "handoff_authorization_id"
    ORDER_CANDIDATE_LATEST = "order_candidate_latest"
    UNRESOLVED = "unresolved"


class RuntimeFreshSubmitAuthorizationResolutionPacket(
    RuntimeFreshSubmitAuthorizationResolutionModel
):
    resolution_id: str = Field(min_length=1, max_length=900)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    handoff_id: str = Field(min_length=1, max_length=840)
    readiness_packet_id: str = Field(min_length=1, max_length=720)
    source_consumed_authorization_id: str = Field(min_length=1, max_length=220)
    requested_fresh_submit_authorization_id: str | None = Field(
        default=None,
        max_length=260,
    )
    resolved_fresh_submit_authorization_id: str | None = Field(
        default=None,
        max_length=260,
    )
    resolution_source: RuntimeFreshSubmitAuthorizationResolutionSource
    status: RuntimeFreshSubmitAuthorizationResolutionStatus
    official_endpoint_method: Literal["POST"] = "POST"
    official_endpoint_path: str | None = Field(default=None, max_length=520)
    official_query: dict[str, Any] = Field(default_factory=dict)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    handoff_snapshot: dict[str, Any] = Field(default_factory=dict)
    authorization_snapshot: dict[str, Any] = Field(default_factory=dict)
    ready_for_disabled_smoke_call: bool = False
    repository_available: bool
    creates_authorization: Literal[False] = False
    calls_official_submit_endpoint: Literal[False] = False
    requests_real_gateway_action: Literal[False] = False
    execution_intent_created: Literal[False] = False
    order_created: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    exchange_called: Literal[False] = False
    exchange_order_submitted: Literal[False] = False
    runtime_state_mutated: Literal[False] = False
    withdrawal_or_transfer_created: Literal[False] = False
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_resolution(
        self,
    ) -> "RuntimeFreshSubmitAuthorizationResolutionPacket":
        if (
            self.status == RuntimeFreshSubmitAuthorizationResolutionStatus.RESOLVED
            and self.blockers
        ):
            raise ValueError("resolved fresh submit authorization cannot have blockers")
        if self.ready_for_disabled_smoke_call != (
            self.status == RuntimeFreshSubmitAuthorizationResolutionStatus.RESOLVED
        ):
            raise ValueError("ready flag must match fresh authorization resolution")
        if self.status == RuntimeFreshSubmitAuthorizationResolutionStatus.RESOLVED:
            if not self.resolved_fresh_submit_authorization_id:
                raise ValueError("resolved fresh submit authorization id missing")
            if not self.official_endpoint_path:
                raise ValueError("resolved official endpoint path missing")
        if self.resolved_fresh_submit_authorization_id == (
            self.source_consumed_authorization_id
        ):
            raise ValueError("fresh submit authorization cannot reuse consumed id")
        return self


def build_runtime_fresh_submit_authorization_resolution_packet(
    *,
    handoff: RuntimeOfficialSubmitHandoffPacket,
    authorization: RuntimeExecutionSubmitAuthorization | None,
    resolution_source: RuntimeFreshSubmitAuthorizationResolutionSource,
    requested_fresh_submit_authorization_id: str | None,
    repository_available: bool,
    additional_blockers: list[str] | None = None,
    additional_warnings: list[str] | None = None,
    now_ms: int,
) -> RuntimeFreshSubmitAuthorizationResolutionPacket:
    blockers: list[str] = []
    warnings: list[str] = list(handoff.warnings)

    if not repository_available:
        blockers.append("submit_authorization_repository_unavailable")
    if handoff.status != RuntimeOfficialSubmitHandoffStatus.READY_FOR_OFFICIAL_SUBMIT_CALL:
        blockers.append("handoff_not_ready_for_official_submit_call")
        blockers.extend(f"handoff:{item}" for item in handoff.blockers)
    if not handoff.ready_for_official_submit_call:
        blockers.append("handoff_ready_flag_false")
    if handoff.mode != RuntimeOfficialSubmitHandoffMode.DISABLED_SMOKE:
        blockers.append("fresh_authorization_resolution_requires_disabled_smoke_handoff")
    if handoff.official_query.get("owner_confirmed_for_first_real_submit_action") is True:
        blockers.append("handoff_query_requests_real_submit_action")

    if authorization is None:
        blockers.append("fresh_submit_authorization_not_found")
    else:
        blockers.extend(_authorization_blockers(handoff, authorization))

    blockers.extend(additional_blockers or [])
    warnings.extend(additional_warnings or [])
    blockers = _dedupe(blockers)
    warnings = _dedupe(warnings)
    status = (
        RuntimeFreshSubmitAuthorizationResolutionStatus.BLOCKED
        if blockers
        else RuntimeFreshSubmitAuthorizationResolutionStatus.RESOLVED
    )
    resolved_id = authorization.authorization_id if authorization else None
    official_path = (
        _official_endpoint_path(resolved_id)
        if status == RuntimeFreshSubmitAuthorizationResolutionStatus.RESOLVED
        else None
    )
    official_query = dict(handoff.official_query)
    official_query["owner_confirmed_for_first_real_submit_action"] = False
    return RuntimeFreshSubmitAuthorizationResolutionPacket(
        resolution_id=(
            "runtime-fresh-submit-authorization-resolution-"
            f"{handoff.runtime_instance_id}-{handoff.readiness_packet_id}"
        ),
        runtime_instance_id=handoff.runtime_instance_id,
        handoff_id=handoff.handoff_id,
        readiness_packet_id=handoff.readiness_packet_id,
        source_consumed_authorization_id=handoff.source_consumed_authorization_id,
        requested_fresh_submit_authorization_id=_optional_str(
            requested_fresh_submit_authorization_id
        ),
        resolved_fresh_submit_authorization_id=(
            resolved_id
            if status == RuntimeFreshSubmitAuthorizationResolutionStatus.RESOLVED
            else None
        ),
        resolution_source=resolution_source,
        status=status,
        official_endpoint_path=official_path,
        official_query=official_query if official_path else {},
        blockers=blockers,
        warnings=warnings,
        handoff_snapshot={
            "status": handoff.status.value,
            "mode": handoff.mode.value,
            "fresh_submit_authorization_id": handoff.fresh_submit_authorization_id,
            "ready_for_official_submit_call": (
                handoff.ready_for_official_submit_call
            ),
            "order_candidate_id": handoff.readiness_snapshot.get(
                "order_candidate_id"
            ),
            "signal_evaluation_id": handoff.readiness_snapshot.get(
                "signal_evaluation_id"
            ),
        },
        authorization_snapshot=_authorization_snapshot(authorization),
        ready_for_disabled_smoke_call=(
            status == RuntimeFreshSubmitAuthorizationResolutionStatus.RESOLVED
        ),
        repository_available=repository_available,
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_fresh_submit_authorization_resolution",
            "non_executing_resolution": True,
            "does_not_create_authorization": True,
            "does_not_call_official_submit_endpoint": True,
            "does_not_call_exchange": True,
            "does_not_call_order_lifecycle": True,
            "does_not_create_withdrawal_or_transfer": True,
        },
    )


def _authorization_blockers(
    handoff: RuntimeOfficialSubmitHandoffPacket,
    authorization: RuntimeExecutionSubmitAuthorization,
) -> list[str]:
    blockers: list[str] = []
    if authorization.authorization_id == handoff.source_consumed_authorization_id:
        blockers.append("fresh_submit_authorization_reuses_consumed_authorization")
    if authorization.status != (
        RuntimeExecutionSubmitAuthorizationStatus.APPROVED_PENDING_CONTROLLED_SUBMIT
    ):
        blockers.append("fresh_submit_authorization_not_pending_controlled_submit")
    if authorization.semantic_ids.runtime_instance_id != handoff.runtime_instance_id:
        blockers.append("fresh_submit_authorization_runtime_mismatch")
    expected_order_candidate_id = _optional_str(
        handoff.readiness_snapshot.get("order_candidate_id")
    )
    if expected_order_candidate_id and (
        authorization.semantic_ids.order_candidate_id != expected_order_candidate_id
    ):
        blockers.append("fresh_submit_authorization_order_candidate_mismatch")
    expected_signal_evaluation_id = _optional_str(
        handoff.readiness_snapshot.get("signal_evaluation_id")
    )
    if expected_signal_evaluation_id and (
        authorization.semantic_ids.signal_evaluation_id
        != expected_signal_evaluation_id
    ):
        blockers.append("fresh_submit_authorization_signal_evaluation_mismatch")
    if authorization.submit_executed:
        blockers.append("fresh_submit_authorization_already_executed")
    if authorization.order_created:
        blockers.append("fresh_submit_authorization_already_created_order")
    if authorization.exchange_called:
        blockers.append("fresh_submit_authorization_already_called_exchange")
    if authorization.order_lifecycle_called:
        blockers.append("fresh_submit_authorization_already_called_order_lifecycle")
    if authorization.owner_bounded_execution_called:
        blockers.append("fresh_submit_authorization_called_owner_bounded_execution")
    return blockers


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
        "trial_binding_id": authorization.semantic_ids.trial_binding_id,
        "strategy_family_id": authorization.semantic_ids.strategy_family_id,
        "strategy_family_version_id": (
            authorization.semantic_ids.strategy_family_version_id
        ),
        "runtime_instance_id": authorization.semantic_ids.runtime_instance_id,
        "signal_evaluation_id": authorization.semantic_ids.signal_evaluation_id,
        "order_candidate_id": authorization.semantic_ids.order_candidate_id,
        "status": authorization.status.value,
        "symbol": authorization.symbol,
        "side": authorization.side,
        "owner_submit_authorized": authorization.owner_submit_authorized,
        "submit_executed": authorization.submit_executed,
        "order_created": authorization.order_created,
        "exchange_called": authorization.exchange_called,
        "order_lifecycle_called": authorization.order_lifecycle_called,
    }


def _official_endpoint_path(authorization_id: str | None) -> str | None:
    if not authorization_id:
        return None
    return (
        "/api/trading-console/"
        "runtime-execution-first-real-submit-actions/authorizations/"
        f"{authorization_id}"
    )


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
