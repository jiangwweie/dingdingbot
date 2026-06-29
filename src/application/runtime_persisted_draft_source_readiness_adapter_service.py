"""Adapt persisted strategy-signal draft sources into submit readiness.

This is the RTF-015 non-executing adapter:

RuntimeStrategySignalIntentDraftSourceArtifact
-> RuntimeNextAttemptStrategyPlanningArtifact typed planning artifact
-> RuntimeExecutableSubmitReadinessArtifact

It does not create ExecutionIntent records, local orders, OrderLifecycle calls,
exchange requests, runtime mutations, withdrawals, or transfers.
"""

from __future__ import annotations

from src.application.runtime_executable_submit_readiness_service import (
    RuntimeExecutableSubmitReadinessService,
)
from src.application.runtime_next_attempt_strategy_planning_service import (
    RuntimeNextAttemptStrategyPlanningArtifact,
    RuntimeNextAttemptStrategyPlanningStatus,
)
from src.application.runtime_strategy_signal_intent_draft_source_service import (
    RuntimeStrategySignalIntentDraftSourceArtifact,
    RuntimeStrategySignalIntentDraftSourceStatus,
)
from src.application.runtime_strategy_signal_planning_service import (
    RuntimeStrategySignalCandidatePlanningStatus,
)
from src.application.runtime_strategy_signal_scheduler_planning_service import (
    RuntimeStrategySignalSchedulerPlanningStatus,
)
from src.domain.runtime_executable_submit_readiness import (
    RuntimeExecutableSubmitReadinessEvidence,
    RuntimeExecutableSubmitReadinessArtifact,
)
from src.domain.runtime_execution_first_real_submit_enablement_evidence import (
    RuntimeExecutionFirstRealSubmitEnablementEvidence,
)
from src.domain.runtime_post_submit_finalize import RuntimeNextAttemptGateStatus


class RuntimePersistedDraftSourceReadinessAdapterService:
    """Build readiness previews from a persisted ready intent draft source."""

    def __init__(
        self,
        *,
        readiness_service: RuntimeExecutableSubmitReadinessService | None = None,
    ) -> None:
        self._readiness = readiness_service or RuntimeExecutableSubmitReadinessService()

    async def preview_from_intent_draft_source(
        self,
        *,
        intent_draft_source_artifact: RuntimeStrategySignalIntentDraftSourceArtifact,
        evidence: RuntimeExecutableSubmitReadinessEvidence,
        first_real_submit_evidence: (
            RuntimeExecutionFirstRealSubmitEnablementEvidence | None
        ) = None,
        additional_blockers: list[str] | None = None,
        additional_warnings: list[str] | None = None,
    ) -> RuntimeExecutableSubmitReadinessArtifact:
        strategy_artifact = strategy_planning_artifact_from_intent_draft_source(
            intent_draft_source_artifact
        )
        return await self._readiness.preview_from_strategy_planning_artifact(
            strategy_planning_artifact=strategy_artifact,
            evidence=evidence,
            first_real_submit_evidence=first_real_submit_evidence,
            additional_blockers=additional_blockers,
            additional_warnings=[
                "readiness_from_persisted_intent_draft_source",
                *(additional_warnings or []),
            ],
        )


def strategy_planning_artifact_from_intent_draft_source(
    source: RuntimeStrategySignalIntentDraftSourceArtifact,
) -> RuntimeNextAttemptStrategyPlanningArtifact:
    """Convert RTF-014 source evidence into the existing readiness input shape."""

    blockers = _source_blockers(source)
    scheduler = source.scheduler_planning
    candidate_planning = (
        scheduler.candidate_planning_result if scheduler is not None else None
    )
    candidate_status = (
        candidate_planning.status if candidate_planning is not None else None
    )
    status = (
        RuntimeNextAttemptStrategyPlanningStatus.READY_FOR_FINAL_GATE_PREFLIGHT
        if not blockers
        else RuntimeNextAttemptStrategyPlanningStatus.BLOCKED_BY_STRATEGY_PLANNING
    )
    return RuntimeNextAttemptStrategyPlanningArtifact(
        artifact_id=(
            "runtime-next-attempt-strategy-planning-from-draft-source-"
            f"{source.artifact_id}"
        ),
        runtime_instance_id=source.runtime_instance_id,
        source_authorization_id=_source_authorization_id(source),
        source_post_submit_finalize_payload_id=(
            f"persisted-draft-source:{source.artifact_id}"
        ),
        source_release_evidence_id=f"persisted-draft-source:{source.artifact_id}",
        status=status,
        next_attempt_gate_status=(
            RuntimeNextAttemptGateStatus.READY_FOR_FRESH_SIGNAL
            if not blockers
            else RuntimeNextAttemptGateStatus.BLOCKED
        ),
        signal_evaluation_id=source.signal_evaluation_id,
        strategy_family_id=source.strategy_family_id,
        strategy_family_version_id=source.strategy_family_version_id,
        symbol=source.symbol,
        candidate_planning_status=candidate_status,
        candidate_planning_result=candidate_planning,
        order_candidate_id=source.order_candidate_id,
        blockers=blockers,
        warnings=_dedupe(
            [
                *source.warnings,
                "strategy_planning_materialized_from_persisted_intent_draft_source",
                "source_authorization_id_is_not_submit_authorization",
            ]
        ),
        strategy_planning_plan={
            "scope": "persisted_intent_draft_source_readiness_adapter",
            "next_step": (
                "run_executable_submit_readiness_from_persisted_draft_source"
            ),
            "not_executed": True,
            "uses_persisted_intent_draft_source": True,
            "creates_shadow_candidate": False,
            "creates_executable_execution_intent": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "live_submit_allowed": False,
            "requires_fresh_submit_authorization_before_submit": True,
        },
        metadata={
            "source": "runtime_persisted_draft_source_readiness_adapter_service",
            "rtf015_persisted_draft_source_adapter": True,
            "non_executing": True,
            "does_not_create_execution_intent": True,
            "does_not_create_order": True,
            "does_not_call_order_lifecycle": True,
            "does_not_call_exchange": True,
            "does_not_mutate_runtime_state": True,
            "does_not_create_withdrawal_or_transfer": True,
            "runtime_execution_intent_draft_id": (
                source.runtime_execution_intent_draft_id
            ),
            "ready_for_official_handoff_source": (
                source.ready_for_official_handoff_source
            ),
        },
    )

def _source_blockers(
    source: RuntimeStrategySignalIntentDraftSourceArtifact,
) -> list[str]:
    blockers: list[str] = list(source.blockers)
    if source.status != (
        RuntimeStrategySignalIntentDraftSourceStatus.PERSISTED_READY_INTENT_DRAFT
    ):
        blockers.append("intent_draft_source_not_ready")
    if not source.ready_for_official_handoff_source:
        blockers.append("intent_draft_source_not_ready_for_official_handoff")
    if not source.runtime_execution_intent_draft_id:
        blockers.append("runtime_execution_intent_draft_id_missing")
    if not source.signal_evaluation_id:
        blockers.append("signal_evaluation_id_missing")
    if not source.order_candidate_id:
        blockers.append("order_candidate_id_missing")

    scheduler = source.scheduler_planning
    if scheduler is None:
        blockers.append("scheduler_planning_missing")
    else:
        if scheduler.status != (
            RuntimeStrategySignalSchedulerPlanningStatus.SHADOW_CANDIDATE_CREATED
        ):
            blockers.append("scheduler_shadow_candidate_not_created")
        planning = scheduler.candidate_planning_result
        if planning is None:
            blockers.append("candidate_planning_result_missing")
        else:
            if planning.status != (
                RuntimeStrategySignalCandidatePlanningStatus.SHADOW_CANDIDATE_CREATED
            ):
                blockers.append("candidate_planning_not_shadow_candidate_created")
            candidate = planning.candidate
            if candidate is None:
                blockers.append("candidate_missing")
            elif (
                source.order_candidate_id
                and candidate.order_candidate_id != source.order_candidate_id
            ):
                blockers.append("order_candidate_id_mismatch")
    return _dedupe(blockers)


def _source_authorization_id(
    source: RuntimeStrategySignalIntentDraftSourceArtifact,
) -> str:
    if source.runtime_execution_intent_draft_id:
        return f"persisted-draft-source:{source.runtime_execution_intent_draft_id}"
    if source.order_candidate_id:
        return f"persisted-draft-source:{source.order_candidate_id}"
    return "persisted-draft-source:missing"


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result
