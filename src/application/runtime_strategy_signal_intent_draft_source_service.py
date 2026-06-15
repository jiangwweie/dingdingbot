"""Persist strategy signal planning into a ready runtime intent draft source."""

from __future__ import annotations

from enum import Enum
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.application.runtime_strategy_signal_scheduler_planning_service import (
    RuntimeStrategySignalSchedulerPlanningResult,
    RuntimeStrategySignalSchedulerPlanningStatus,
)
from src.domain.runtime_execution_plan import (
    RuntimeExecutionIntentDraft,
    RuntimeExecutionIntentDraftStatus,
)
from src.domain.strategy_family_signal import StrategyFamilySignalInput
from src.domain.strategy_runtime import StrategyRuntimeInstance


class RuntimeStrategySignalIntentDraftSchedulerPort(Protocol):
    async def plan_signal_input_if_ready(
        self,
        signal_input: StrategyFamilySignalInput,
        *,
        runtime: StrategyRuntimeInstance,
        candidate_id: str | None = None,
        allow_shadow_candidate_creation: bool = False,
        context_id: str | None = None,
        expires_at_ms: int | None = None,
        metadata: dict | None = None,
    ) -> RuntimeStrategySignalSchedulerPlanningResult:
        ...


class RuntimeStrategySignalIntentDraftPlanningPort(Protocol):
    async def record_intent_draft_for_order_candidate(
        self,
        *,
        order_candidate_id: str,
        owner_reviewed: bool = True,
        owner_confirmed_for_intent: bool = True,
        active_positions_count: int | None = None,
    ) -> RuntimeExecutionIntentDraft:
        ...


class RuntimeStrategySignalIntentDraftSourceStatus(str, Enum):
    BLOCKED = "blocked"
    PERSISTED_READY_INTENT_DRAFT = "persisted_ready_intent_draft"


class RuntimeStrategySignalIntentDraftSourcePacket(BaseModel):
    """Audit packet for strategy-signal -> shadow candidate -> ready draft."""

    model_config = ConfigDict(extra="forbid")

    packet_id: str = Field(min_length=1, max_length=260)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    strategy_family_id: str = Field(min_length=1, max_length=128)
    strategy_family_version_id: str = Field(min_length=1, max_length=128)
    symbol: str = Field(min_length=1, max_length=128)
    status: RuntimeStrategySignalIntentDraftSourceStatus
    scheduler_planning: RuntimeStrategySignalSchedulerPlanningResult | None = None
    signal_evaluation_id: str | None = Field(default=None, max_length=128)
    order_candidate_id: str | None = Field(default=None, max_length=128)
    runtime_execution_intent_draft_id: str | None = Field(
        default=None,
        max_length=180,
    )
    draft_status: RuntimeExecutionIntentDraftStatus | None = None
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    ready_for_official_handoff_source: bool = False
    allow_shadow_candidate_creation: bool = False
    allow_intent_draft_creation: bool = False
    owner_reviewed: bool = False
    owner_confirmed_for_intent: bool = False
    signal_evaluation_created: bool = False
    order_candidate_created: bool = False
    runtime_execution_intent_draft_created: bool = False
    execution_intent_created: Literal[False] = False
    order_created: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    exchange_called: Literal[False] = False
    exchange_order_submitted: Literal[False] = False
    runtime_state_mutated: Literal[False] = False
    withdrawal_or_transfer_created: Literal[False] = False
    metadata: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_ready_packet(
        self,
    ) -> "RuntimeStrategySignalIntentDraftSourcePacket":
        if self.status == (
            RuntimeStrategySignalIntentDraftSourceStatus
            .PERSISTED_READY_INTENT_DRAFT
        ):
            if self.blockers:
                raise ValueError("ready intent draft source cannot have blockers")
            if not self.signal_evaluation_id:
                raise ValueError("ready intent draft source missing signal evaluation")
            if not self.order_candidate_id:
                raise ValueError("ready intent draft source missing order candidate")
            if not self.runtime_execution_intent_draft_id:
                raise ValueError("ready intent draft source missing intent draft")
            if self.draft_status != (
                RuntimeExecutionIntentDraftStatus.READY_FOR_INTENT_CREATION
            ):
                raise ValueError("intent draft source is not ready")
            if not self.ready_for_official_handoff_source:
                raise ValueError("ready packet flag mismatch")
        return self


class RuntimeStrategySignalIntentDraftSourceService:
    """Create a persisted draft source from current strategy signal planning."""

    def __init__(
        self,
        *,
        scheduler_planning_service: RuntimeStrategySignalIntentDraftSchedulerPort,
        runtime_execution_planning_service: RuntimeStrategySignalIntentDraftPlanningPort,
    ) -> None:
        self._scheduler = scheduler_planning_service
        self._runtime_execution_planning = runtime_execution_planning_service

    async def record_ready_intent_draft_source(
        self,
        signal_input: StrategyFamilySignalInput,
        *,
        runtime: StrategyRuntimeInstance,
        allow_shadow_candidate_creation: bool,
        allow_intent_draft_creation: bool,
        owner_reviewed: bool = True,
        owner_confirmed_for_intent: bool = True,
        candidate_id: str | None = None,
        context_id: str | None = None,
        expires_at_ms: int | None = None,
        active_positions_count: int | None = None,
        metadata: dict | None = None,
    ) -> RuntimeStrategySignalIntentDraftSourcePacket:
        preflight_blockers: list[str] = []
        if not allow_shadow_candidate_creation:
            preflight_blockers.append("shadow_candidate_creation_not_enabled")
        if not allow_intent_draft_creation:
            preflight_blockers.append("intent_draft_creation_not_enabled")
        if not owner_reviewed:
            preflight_blockers.append("owner_reviewed_required_for_ready_draft_source")
        if not owner_confirmed_for_intent:
            preflight_blockers.append(
                "owner_confirmed_for_intent_required_for_ready_draft_source"
            )
        if preflight_blockers:
            return _packet(
                signal_input,
                runtime=runtime,
                scheduler_planning=None,
                draft=None,
                status=RuntimeStrategySignalIntentDraftSourceStatus.BLOCKED,
                blockers=preflight_blockers,
                warnings=[],
                allow_shadow_candidate_creation=allow_shadow_candidate_creation,
                allow_intent_draft_creation=allow_intent_draft_creation,
                owner_reviewed=owner_reviewed,
                owner_confirmed_for_intent=owner_confirmed_for_intent,
                metadata={
                    "blocked_before_scheduler_planning": True,
                    **(metadata or {}),
                },
            )

        scheduler_planning = await self._scheduler.plan_signal_input_if_ready(
            signal_input,
            runtime=runtime,
            candidate_id=candidate_id,
            allow_shadow_candidate_creation=True,
            context_id=context_id,
            expires_at_ms=expires_at_ms,
            metadata={
                "rtf014_persisted_intent_draft_source": True,
                "requires_persisted_signal_evaluation": True,
                "requires_persisted_order_candidate": True,
                **(metadata or {}),
            },
        )
        candidate = (
            scheduler_planning.candidate_planning_result.candidate
            if scheduler_planning.candidate_planning_result is not None
            else None
        )
        if (
            scheduler_planning.status
            != RuntimeStrategySignalSchedulerPlanningStatus.SHADOW_CANDIDATE_CREATED
            or candidate is None
        ):
            return _packet(
                signal_input,
                runtime=runtime,
                scheduler_planning=scheduler_planning,
                draft=None,
                status=RuntimeStrategySignalIntentDraftSourceStatus.BLOCKED,
                blockers=[
                    *scheduler_planning.blockers,
                    "scheduler_shadow_candidate_not_created",
                ],
                warnings=scheduler_planning.warnings,
                allow_shadow_candidate_creation=allow_shadow_candidate_creation,
                allow_intent_draft_creation=allow_intent_draft_creation,
                owner_reviewed=owner_reviewed,
                owner_confirmed_for_intent=owner_confirmed_for_intent,
                metadata={
                    "blocked_before_intent_draft_creation": True,
                    **(metadata or {}),
                },
            )

        try:
            draft = await (
                self._runtime_execution_planning
                .record_intent_draft_for_order_candidate(
                    order_candidate_id=candidate.order_candidate_id,
                    owner_reviewed=owner_reviewed,
                    owner_confirmed_for_intent=owner_confirmed_for_intent,
                    active_positions_count=active_positions_count,
                )
            )
        except Exception as exc:
            return _packet(
                signal_input,
                runtime=runtime,
                scheduler_planning=scheduler_planning,
                draft=None,
                status=RuntimeStrategySignalIntentDraftSourceStatus.BLOCKED,
                blockers=[f"intent_draft_creation_failed:{_error_code(exc)}"],
                warnings=scheduler_planning.warnings,
                allow_shadow_candidate_creation=allow_shadow_candidate_creation,
                allow_intent_draft_creation=allow_intent_draft_creation,
                owner_reviewed=owner_reviewed,
                owner_confirmed_for_intent=owner_confirmed_for_intent,
                metadata=metadata,
            )

        blockers: list[str] = []
        if draft.status != RuntimeExecutionIntentDraftStatus.READY_FOR_INTENT_CREATION:
            blockers.append("runtime_execution_intent_draft_not_ready")
        return _packet(
            signal_input,
            runtime=runtime,
            scheduler_planning=scheduler_planning,
            draft=draft,
            status=(
                RuntimeStrategySignalIntentDraftSourceStatus.BLOCKED
                if blockers
                else (
                    RuntimeStrategySignalIntentDraftSourceStatus
                    .PERSISTED_READY_INTENT_DRAFT
                )
            ),
            blockers=blockers,
            warnings=scheduler_planning.warnings,
            allow_shadow_candidate_creation=allow_shadow_candidate_creation,
            allow_intent_draft_creation=allow_intent_draft_creation,
            owner_reviewed=owner_reviewed,
            owner_confirmed_for_intent=owner_confirmed_for_intent,
            metadata={
                "rtf014_persisted_strategy_signal_intent_draft_source": True,
                "ready_for_rtf013_fresh_authorization_binding": not blockers,
                **(metadata or {}),
            },
        )


def _packet(
    signal_input: StrategyFamilySignalInput,
    *,
    runtime: StrategyRuntimeInstance,
    scheduler_planning: RuntimeStrategySignalSchedulerPlanningResult | None,
    draft: RuntimeExecutionIntentDraft | None,
    status: RuntimeStrategySignalIntentDraftSourceStatus,
    blockers: list[str],
    warnings: list[str],
    allow_shadow_candidate_creation: bool,
    allow_intent_draft_creation: bool,
    owner_reviewed: bool,
    owner_confirmed_for_intent: bool,
    metadata: dict | None,
) -> RuntimeStrategySignalIntentDraftSourcePacket:
    candidate = (
        scheduler_planning.candidate_planning_result.candidate
        if scheduler_planning is not None
        and scheduler_planning.candidate_planning_result is not None
        else None
    )
    signal_evaluation_id = (
        candidate.signal_evaluation_id
        if candidate is not None
        else (
            draft.signal_evaluation_id
            if draft is not None
            else None
        )
    )
    order_candidate_id = (
        candidate.order_candidate_id
        if candidate is not None
        else (
            draft.order_candidate_id
            if draft is not None
            else None
        )
    )
    ready = (
        status
        == RuntimeStrategySignalIntentDraftSourceStatus.PERSISTED_READY_INTENT_DRAFT
    )
    return RuntimeStrategySignalIntentDraftSourcePacket(
        packet_id=f"runtime-strategy-signal-intent-draft-source-{signal_input.evaluation_id}",
        runtime_instance_id=runtime.runtime_instance_id,
        strategy_family_id=signal_input.strategy_family_id,
        strategy_family_version_id=signal_input.strategy_family_version_id,
        symbol=signal_input.symbol,
        status=status,
        scheduler_planning=scheduler_planning,
        signal_evaluation_id=signal_evaluation_id,
        order_candidate_id=order_candidate_id,
        runtime_execution_intent_draft_id=draft.draft_id if draft else None,
        draft_status=draft.status if draft else None,
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        ready_for_official_handoff_source=ready,
        allow_shadow_candidate_creation=allow_shadow_candidate_creation,
        allow_intent_draft_creation=allow_intent_draft_creation,
        owner_reviewed=owner_reviewed,
        owner_confirmed_for_intent=owner_confirmed_for_intent,
        signal_evaluation_created=(
            scheduler_planning.signal_evaluation_created
            if scheduler_planning is not None
            else False
        ),
        order_candidate_created=(
            scheduler_planning.order_candidate_created
            if scheduler_planning is not None
            else False
        ),
        runtime_execution_intent_draft_created=draft is not None,
        metadata={
            "source": "runtime_strategy_signal_intent_draft_source_service",
            "non_executing": True,
            "does_not_create_recorded_execution_intent": True,
            "does_not_create_order": True,
            "does_not_call_order_lifecycle": True,
            "does_not_call_exchange": True,
            "does_not_mutate_runtime_state": True,
            **(metadata or {}),
        },
    )


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _error_code(exc: Exception) -> str:
    return str(exc).strip().lower().replace(" ", "_") or exc.__class__.__name__
