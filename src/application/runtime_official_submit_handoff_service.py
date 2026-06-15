"""Application service for official submit handoff previews."""

from __future__ import annotations

from datetime import datetime, timezone

from src.domain.runtime_executable_submit_readiness import (
    RuntimeExecutableSubmitReadinessPacket,
)
from src.domain.runtime_official_submit_handoff import (
    RuntimeOfficialSubmitHandoffMode,
    RuntimeOfficialSubmitHandoffPacket,
    build_runtime_official_submit_handoff_packet,
)


class RuntimeOfficialSubmitHandoffService:
    """Build non-executing handoff previews for the official submit endpoint."""

    async def preview_from_readiness_packet(
        self,
        *,
        readiness_packet: RuntimeExecutableSubmitReadinessPacket,
        fresh_submit_authorization_id: str | None,
        mode: RuntimeOfficialSubmitHandoffMode = (
            RuntimeOfficialSubmitHandoffMode.DISABLED_SMOKE
        ),
        owner_confirmed_for_real_submit_action: bool = True,
        additional_blockers: list[str] | None = None,
        additional_warnings: list[str] | None = None,
    ) -> RuntimeOfficialSubmitHandoffPacket:
        return build_runtime_official_submit_handoff_packet(
            readiness_packet=readiness_packet,
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
