"""Application service for runtime executable-submit readiness previews."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.runtime_next_attempt_strategy_planning_service import (
    RuntimeNextAttemptStrategyPlanningPacket,
)
from src.domain.runtime_executable_submit_readiness import (
    RuntimeExecutableSubmitReadinessEvidence,
    RuntimeExecutableSubmitReadinessPacket,
    build_runtime_executable_submit_readiness_packet,
)
from src.domain.runtime_execution_first_real_submit_enablement_packet import (
    RuntimeExecutionFirstRealSubmitEnablementPacket,
)


class RuntimeExecutableSubmitReadinessService:
    """Build non-executing readiness previews for the official submit path."""

    async def preview_from_strategy_planning_packet(
        self,
        *,
        strategy_planning_packet: RuntimeNextAttemptStrategyPlanningPacket,
        evidence: RuntimeExecutableSubmitReadinessEvidence,
        first_real_submit_packet: (
            RuntimeExecutionFirstRealSubmitEnablementPacket | None
        ) = None,
        additional_blockers: list[str] | None = None,
        additional_warnings: list[str] | None = None,
    ) -> RuntimeExecutableSubmitReadinessPacket:
        source_blockers = [
            f"strategy_planning:{item}"
            for item in strategy_planning_packet.blockers
        ]
        source_warnings = [
            f"strategy_planning:{item}"
            for item in strategy_planning_packet.warnings
        ]
        return build_runtime_executable_submit_readiness_packet(
            runtime_instance_id=strategy_planning_packet.runtime_instance_id,
            source_release_packet_id=(
                strategy_planning_packet.source_release_packet_id
            ),
            source_strategy_planning_packet_id=strategy_planning_packet.packet_id,
            source_authorization_id=strategy_planning_packet.source_authorization_id,
            strategy_planning_status=_value(strategy_planning_packet.status),
            signal_evaluation_id=strategy_planning_packet.signal_evaluation_id,
            order_candidate_id=strategy_planning_packet.order_candidate_id,
            evidence=evidence,
            first_real_submit_packet_status=(
                _value(first_real_submit_packet.status)
                if first_real_submit_packet is not None
                else None
            ),
            first_real_submit_packet_blockers=(
                list(first_real_submit_packet.blockers)
                if first_real_submit_packet is not None
                else None
            ),
            additional_blockers=[
                *source_blockers,
                *(additional_blockers or []),
            ],
            additional_warnings=[
                *source_warnings,
                *(additional_warnings or []),
            ],
            now_ms=_now_ms(),
        )


def _value(value: object) -> str:
    return str(getattr(value, "value", value))


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)
