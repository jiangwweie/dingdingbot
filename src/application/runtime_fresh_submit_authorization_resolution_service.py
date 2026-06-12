"""Application service for resolving fresh submit authorizations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from src.domain.runtime_execution_submit_authorization import (
    RuntimeExecutionSubmitAuthorization,
)
from src.domain.runtime_fresh_submit_authorization_resolution import (
    RuntimeFreshSubmitAuthorizationResolutionPacket,
    RuntimeFreshSubmitAuthorizationResolutionSource,
    build_runtime_fresh_submit_authorization_resolution_packet,
)
from src.domain.runtime_official_submit_handoff import (
    RuntimeOfficialSubmitHandoffPacket,
)


class RuntimeSubmitAuthorizationLookupPort(Protocol):
    async def get(
        self,
        authorization_id: str,
    ) -> RuntimeExecutionSubmitAuthorization | None:
        ...

    async def get_by_order_candidate_id(
        self,
        order_candidate_id: str,
    ) -> RuntimeExecutionSubmitAuthorization | None:
        ...


class RuntimeFreshSubmitAuthorizationResolutionService:
    """Resolve persisted fresh submit authorization evidence for a handoff."""

    def __init__(
        self,
        *,
        submit_authorization_repository: (
            RuntimeSubmitAuthorizationLookupPort | None
        ) = None,
    ) -> None:
        self._submit_authorization_repository = submit_authorization_repository

    async def resolve_for_handoff(
        self,
        *,
        handoff: RuntimeOfficialSubmitHandoffPacket,
        requested_fresh_submit_authorization_id: str | None = None,
        allow_order_candidate_fallback: bool = True,
        additional_blockers: list[str] | None = None,
        additional_warnings: list[str] | None = None,
    ) -> RuntimeFreshSubmitAuthorizationResolutionPacket:
        repository_available = self._submit_authorization_repository is not None
        authorization: RuntimeExecutionSubmitAuthorization | None = None
        source = RuntimeFreshSubmitAuthorizationResolutionSource.UNRESOLVED
        lookup_id = _optional_str(requested_fresh_submit_authorization_id)
        if repository_available and lookup_id:
            authorization = await self._submit_authorization_repository.get(lookup_id)
            source = RuntimeFreshSubmitAuthorizationResolutionSource.EXPLICIT_AUTHORIZATION_ID
        if repository_available and authorization is None and not lookup_id:
            handoff_id = _optional_str(handoff.fresh_submit_authorization_id)
            if handoff_id:
                authorization = await self._submit_authorization_repository.get(
                    handoff_id
                )
                source = (
                    RuntimeFreshSubmitAuthorizationResolutionSource
                    .HANDOFF_AUTHORIZATION_ID
                )
        if (
            repository_available
            and authorization is None
            and allow_order_candidate_fallback
        ):
            order_candidate_id = _optional_str(
                handoff.readiness_snapshot.get("order_candidate_id")
            )
            if order_candidate_id:
                authorization = (
                    await self._submit_authorization_repository
                    .get_by_order_candidate_id(order_candidate_id)
                )
                source = (
                    RuntimeFreshSubmitAuthorizationResolutionSource
                    .ORDER_CANDIDATE_LATEST
                )

        warnings = list(additional_warnings or [])
        if (
            source
            == RuntimeFreshSubmitAuthorizationResolutionSource.ORDER_CANDIDATE_LATEST
            and _optional_str(requested_fresh_submit_authorization_id)
        ):
            warnings.append("explicit_fresh_authorization_not_found_used_candidate_fallback")
        return build_runtime_fresh_submit_authorization_resolution_packet(
            handoff=handoff,
            authorization=authorization,
            resolution_source=source,
            requested_fresh_submit_authorization_id=(
                requested_fresh_submit_authorization_id
                or handoff.fresh_submit_authorization_id
            ),
            repository_available=repository_available,
            additional_blockers=additional_blockers,
            additional_warnings=warnings,
            now_ms=_now_ms(),
        )


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _optional_str(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None
