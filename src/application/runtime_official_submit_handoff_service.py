"""Application service for official submit preview artifacts."""

from __future__ import annotations

from datetime import datetime, timezone

from src.domain.runtime_executable_submit_readiness import (
    RuntimeExecutableSubmitReadinessArtifact,
)
from src.domain.runtime_official_submit_handoff import (
    RuntimeOfficialSubmitHandoffMode,
    RuntimeOfficialSubmitHandoffArtifact,
    build_runtime_official_submit_handoff_artifact,
)


class RuntimeOfficialSubmitHandoffService:
    """Build non-executing submit projections for the official endpoint."""

    async def preview_from_readiness_artifact(
        self,
        *,
        readiness_artifact: RuntimeExecutableSubmitReadinessArtifact,
        fresh_submit_authorization_id: str | None,
        mode: RuntimeOfficialSubmitHandoffMode = (
            RuntimeOfficialSubmitHandoffMode.DISABLED_SMOKE
        ),
        owner_confirmed_for_real_submit_action: bool = True,
        additional_blockers: list[str] | None = None,
        additional_warnings: list[str] | None = None,
    ) -> RuntimeOfficialSubmitHandoffArtifact:
        return build_runtime_official_submit_handoff_artifact(
            readiness_artifact=readiness_artifact,
            fresh_submit_authorization_id=fresh_submit_authorization_id,
            mode=mode,
            owner_confirmed_for_real_submit_action=(
                owner_confirmed_for_real_submit_action
            ),
            additional_blockers=additional_blockers,
            additional_warnings=additional_warnings,
            now_ms=_now_ms(),
        )


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)
