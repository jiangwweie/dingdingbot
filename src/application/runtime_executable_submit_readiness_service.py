"""Application service for runtime executable-submit readiness previews."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.runtime_next_attempt_strategy_planning_service import (
    RuntimeNextAttemptStrategyPlanningArtifact,
)
from src.domain.runtime_executable_submit_readiness import (
    RuntimeExecutableSubmitReadinessEvidence,
    RuntimeExecutableSubmitReadinessArtifact,
    build_runtime_executable_submit_readiness_artifact,
)
from src.domain.runtime_execution_first_real_submit_enablement_evidence import (
    RuntimeExecutionFirstRealSubmitEnablementEvidence,
)


class RuntimeExecutableSubmitReadinessService:
    """Build non-executing readiness previews for the official submit path."""

    async def preview_from_strategy_planning_artifact(
        self,
        *,
        strategy_planning_artifact: RuntimeNextAttemptStrategyPlanningArtifact,
        evidence: RuntimeExecutableSubmitReadinessEvidence,
        first_real_submit_evidence: (
            RuntimeExecutionFirstRealSubmitEnablementEvidence | None
        ) = None,
        additional_blockers: list[str] | None = None,
        additional_warnings: list[str] | None = None,
    ) -> RuntimeExecutableSubmitReadinessArtifact:
        source_blockers = [
            f"strategy_planning:{item}"
            for item in strategy_planning_artifact.blockers
        ]
        source_warnings = [
            f"strategy_planning:{item}"
            for item in strategy_planning_artifact.warnings
        ]
        return build_runtime_executable_submit_readiness_artifact(
            runtime_instance_id=strategy_planning_artifact.runtime_instance_id,
            source_release_evidence_id=(
                strategy_planning_artifact.source_release_evidence_id
            ),
            source_strategy_planning_artifact_id=strategy_planning_artifact.artifact_id,
            source_authorization_id=strategy_planning_artifact.source_authorization_id,
            strategy_planning_status=_value(strategy_planning_artifact.status),
            signal_evaluation_id=strategy_planning_artifact.signal_evaluation_id,
            order_candidate_id=strategy_planning_artifact.order_candidate_id,
            evidence=evidence,
            first_real_submit_source_status=(
                _value(first_real_submit_evidence.status)
                if first_real_submit_evidence is not None
                else None
            ),
            first_real_submit_source_blockers=(
                list(first_real_submit_evidence.blockers)
                if first_real_submit_evidence is not None
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
