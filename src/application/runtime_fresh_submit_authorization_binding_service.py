"""Create or bind persisted fresh submit authorization for a handoff."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

from src.application.runtime_execution_intent_adapter_service import (
    RuntimeExecutionIntentAdapterService,
)
from src.application.runtime_fresh_submit_authorization_resolution_service import (
    RuntimeFreshSubmitAuthorizationResolutionService,
)
from src.domain.execution_intent import ExecutionIntent
from src.domain.runtime_execution_plan import (
    RuntimeExecutionIntentDraft,
    RuntimeExecutionIntentDraftStatus,
)
from src.domain.runtime_execution_submit_authorization import (
    RuntimeExecutionSubmitAuthorization,
)
from src.domain.runtime_fresh_submit_authorization_binding import (
    RuntimeFreshSubmitAuthorizationBindingArtifact,
    RuntimeFreshSubmitAuthorizationBindingSource,
    RuntimeFreshSubmitAuthorizationBindingStatus,
    build_runtime_fresh_submit_authorization_binding_artifact,
)
from src.domain.runtime_fresh_submit_authorization_resolution import (
    RuntimeFreshSubmitAuthorizationResolutionArtifact,
    RuntimeFreshSubmitAuthorizationResolutionStatus,
)
from src.domain.runtime_official_submit_handoff import (
    RuntimeOfficialSubmitHandoffArtifact,
)


class RuntimeIntentLookupPort(Protocol):
    async def get_by_order_candidate_id(
        self,
        order_candidate_id: str,
    ) -> ExecutionIntent | None:
        ...


class RuntimeIntentDraftLookupPort(Protocol):
    async def list_for_order_candidate(
        self,
        order_candidate_id: str,
        *,
        limit: int = 20,
    ) -> list[RuntimeExecutionIntentDraft]:
        ...


class RuntimeFreshSubmitAuthorizationBindingService:
    """Bind a ready handoff to an official-path submit authorization."""

    def __init__(
        self,
        *,
        adapter_service: RuntimeExecutionIntentAdapterService,
        resolution_service: RuntimeFreshSubmitAuthorizationResolutionService,
        intent_repository: RuntimeIntentLookupPort | None = None,
        draft_repository: RuntimeIntentDraftLookupPort | None = None,
    ) -> None:
        self._adapter_service = adapter_service
        self._resolution_service = resolution_service
        self._intent_repository = intent_repository
        self._draft_repository = draft_repository

    async def bind_for_handoff(
        self,
        *,
        handoff: RuntimeOfficialSubmitHandoffArtifact,
        requested_fresh_submit_authorization_id: str | None = None,
        allow_create_from_existing_intent: bool = True,
        allow_create_intent_from_latest_draft: bool = True,
        additional_blockers: list[str] | None = None,
        additional_warnings: list[str] | None = None,
    ) -> RuntimeFreshSubmitAuthorizationBindingArtifact:
        warnings = list(additional_warnings or [])
        blockers = list(additional_blockers or [])
        resolution = await self._resolution_service.resolve_for_handoff(
            handoff=handoff,
            requested_fresh_submit_authorization_id=(
                requested_fresh_submit_authorization_id
            ),
        )
        if resolution.status == RuntimeFreshSubmitAuthorizationResolutionStatus.RESOLVED:
            authorization = _authorization_from_resolution(resolution)
            if authorization is None:
                blockers.append("resolved_authorization_snapshot_missing")
                return self._blocked(
                    handoff=handoff,
                    resolution=resolution,
                    blockers=blockers,
                    warnings=warnings,
                )
            return build_runtime_fresh_submit_authorization_binding_artifact(
                handoff=handoff,
                resolution=resolution,
                authorization=authorization,
                status=(
                    RuntimeFreshSubmitAuthorizationBindingStatus
                    .BOUND_EXISTING_AUTHORIZATION
                ),
                binding_source=(
                    RuntimeFreshSubmitAuthorizationBindingSource
                    .EXISTING_RESOLUTION
                ),
                execution_intent_id=authorization.execution_intent_id,
                runtime_execution_intent_draft_id=(
                    authorization.runtime_execution_intent_draft_id
                ),
                creates_execution_intent=False,
                creates_submit_authorization=False,
                additional_warnings=warnings,
                now_ms=_now_ms(),
            )

        order_candidate_id = _optional_str(
            handoff.readiness_snapshot.get("order_candidate_id")
        )
        if not order_candidate_id:
            blockers.append("order_candidate_id_missing_for_fresh_authorization_binding")
            return self._blocked(
                handoff=handoff,
                resolution=resolution,
                blockers=blockers,
                warnings=warnings,
            )

        if allow_create_from_existing_intent:
            intent = await self._latest_intent(order_candidate_id)
            if intent is not None:
                try:
                    authorization = (
                        await self._adapter_service
                        .create_submit_authorization_for_intent(
                            intent.id,
                            owner_confirmed_for_submit=True,
                        )
                    )
                except Exception as exc:
                    blockers.append(_error_code("create_authorization_failed", exc))
                else:
                    return build_runtime_fresh_submit_authorization_binding_artifact(
                        handoff=handoff,
                        resolution=resolution,
                        authorization=authorization,
                        status=(
                            RuntimeFreshSubmitAuthorizationBindingStatus
                            .CREATED_AUTHORIZATION
                        ),
                        binding_source=(
                            RuntimeFreshSubmitAuthorizationBindingSource
                            .EXISTING_INTENT
                        ),
                        execution_intent_id=intent.id,
                        runtime_execution_intent_draft_id=(
                            intent.runtime_execution_intent_draft_id
                        ),
                        creates_execution_intent=False,
                        creates_submit_authorization=True,
                        additional_warnings=warnings,
                        now_ms=_now_ms(),
                    )

        if allow_create_intent_from_latest_draft:
            draft = await self._latest_ready_draft(order_candidate_id)
            if draft is None:
                blockers.append("ready_runtime_execution_intent_draft_not_found")
            else:
                try:
                    intent = (
                        await self._adapter_service.create_recorded_intent_from_draft(
                            draft.draft_id
                        )
                    )
                    authorization = (
                        await self._adapter_service
                        .create_submit_authorization_for_intent(
                            intent.id,
                            owner_confirmed_for_submit=True,
                        )
                    )
                except Exception as exc:
                    blockers.append(
                        _error_code("create_intent_or_authorization_failed", exc)
                    )
                else:
                    return build_runtime_fresh_submit_authorization_binding_artifact(
                        handoff=handoff,
                        resolution=resolution,
                        authorization=authorization,
                        status=(
                            RuntimeFreshSubmitAuthorizationBindingStatus
                            .CREATED_INTENT_AND_AUTHORIZATION
                        ),
                        binding_source=(
                            RuntimeFreshSubmitAuthorizationBindingSource
                            .LATEST_READY_DRAFT
                        ),
                        execution_intent_id=intent.id,
                        runtime_execution_intent_draft_id=draft.draft_id,
                        creates_execution_intent=True,
                        creates_submit_authorization=True,
                        additional_warnings=warnings,
                        now_ms=_now_ms(),
                    )

        return self._blocked(
            handoff=handoff,
            resolution=resolution,
            blockers=[
                *blockers,
                *[f"resolution:{item}" for item in resolution.blockers],
            ],
            warnings=warnings,
        )

    async def _latest_intent(self, order_candidate_id: str) -> ExecutionIntent | None:
        if self._intent_repository is None:
            return None
        return await self._intent_repository.get_by_order_candidate_id(
            order_candidate_id
        )

    async def _latest_ready_draft(
        self,
        order_candidate_id: str,
    ) -> RuntimeExecutionIntentDraft | None:
        if self._draft_repository is None:
            return None
        drafts = await self._draft_repository.list_for_order_candidate(
            order_candidate_id,
            limit=10,
        )
        for draft in drafts:
            if draft.status == (
                RuntimeExecutionIntentDraftStatus.READY_FOR_INTENT_CREATION
            ):
                return draft
        return None

    def _blocked(
        self,
        *,
        handoff: RuntimeOfficialSubmitHandoffArtifact,
        resolution: RuntimeFreshSubmitAuthorizationResolutionArtifact | None,
        blockers: list[str],
        warnings: list[str],
    ) -> RuntimeFreshSubmitAuthorizationBindingArtifact:
        return build_runtime_fresh_submit_authorization_binding_artifact(
            handoff=handoff,
            resolution=resolution,
            authorization=None,
            status=RuntimeFreshSubmitAuthorizationBindingStatus.BLOCKED,
            binding_source=RuntimeFreshSubmitAuthorizationBindingSource.UNRESOLVED,
            execution_intent_id=None,
            runtime_execution_intent_draft_id=None,
            creates_execution_intent=False,
            creates_submit_authorization=False,
            additional_blockers=blockers,
            additional_warnings=warnings,
            now_ms=_now_ms(),
        )


def _authorization_from_resolution(
    resolution: RuntimeFreshSubmitAuthorizationResolutionArtifact,
) -> RuntimeExecutionSubmitAuthorization | None:
    snapshot: dict[str, Any] = dict(resolution.authorization_snapshot or {})
    authorization_id = _optional_str(snapshot.get("authorization_id"))
    execution_intent_id = _optional_str(snapshot.get("execution_intent_id"))
    if not authorization_id or not execution_intent_id:
        return None
    from src.domain.brc_audit_ids import BrcSemanticIds
    from src.domain.runtime_execution_submit_authorization import (
        RuntimeExecutionSubmitAuthorizationStatus,
    )

    return RuntimeExecutionSubmitAuthorization(
        authorization_id=authorization_id,
        execution_intent_id=execution_intent_id,
        runtime_execution_intent_draft_id=_optional_str(
            snapshot.get("runtime_execution_intent_draft_id")
        ),
        source_type="brc_runtime_order_candidate",
        source_id=_optional_str(snapshot.get("order_candidate_id")),
        status=RuntimeExecutionSubmitAuthorizationStatus(
            snapshot.get("status") or "approved_pending_controlled_submit"
        ),
        semantic_ids=BrcSemanticIds(
            runtime_instance_id=str(snapshot.get("runtime_instance_id") or ""),
            trial_binding_id=str(snapshot.get("trial_binding_id") or "unknown"),
            strategy_family_id=str(snapshot.get("strategy_family_id") or "unknown"),
            strategy_family_version_id=str(
                snapshot.get("strategy_family_version_id") or "unknown"
            ),
            signal_evaluation_id=str(snapshot.get("signal_evaluation_id") or ""),
            order_candidate_id=str(snapshot.get("order_candidate_id") or ""),
        ),
        symbol=str(snapshot.get("symbol") or "UNKNOWN"),
        side=_optional_str(snapshot.get("side")),
        created_at_ms=_now_ms(),
    )


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _optional_str(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _error_code(prefix: str, exc: Exception) -> str:
    text = str(exc).strip().lower().replace(" ", "_") or exc.__class__.__name__
    return f"{prefix}:{text}"
