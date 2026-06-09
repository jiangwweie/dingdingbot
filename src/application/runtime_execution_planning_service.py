"""Runtime execution planning service.

This service builds non-executable plans from shadow OrderCandidate records. It
does not persist ExecutionIntent records, submit orders, or call exchange.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Protocol

from src.application.runtime_final_gate_preview_service import (
    RuntimeFinalGatePreviewService,
)
from src.domain.runtime_execution_plan import (
    RuntimeExecutionIntentDraft,
    RuntimeExecutionPlan,
    build_runtime_execution_intent_draft,
    build_runtime_execution_plan,
)
from src.domain.signal_evaluation import OrderCandidate
from src.domain.strategy_runtime import StrategyRuntimeInstance


class RuntimeExecutionRuntimePort(Protocol):
    async def get_runtime(self, runtime_instance_id: str) -> StrategyRuntimeInstance:
        ...


class RuntimeExecutionCandidatePort(Protocol):
    async def get_order_candidate(self, order_candidate_id: str) -> OrderCandidate:
        ...


class RuntimeExecutionIntentDraftRepositoryPort(Protocol):
    async def create(self, draft: RuntimeExecutionIntentDraft) -> RuntimeExecutionIntentDraft:
        ...


class RuntimeExecutionPlanningService:
    """Build Owner-reviewable, non-executable runtime execution plans."""

    def __init__(
        self,
        *,
        runtime_service: RuntimeExecutionRuntimePort,
        signal_evaluation_service: RuntimeExecutionCandidatePort,
        final_gate_preview_service: RuntimeFinalGatePreviewService,
        intent_draft_repository: RuntimeExecutionIntentDraftRepositoryPort | None = None,
    ) -> None:
        self._runtime_service = runtime_service
        self._signal_evaluation_service = signal_evaluation_service
        self._final_gate_preview_service = final_gate_preview_service
        self._intent_draft_repository = intent_draft_repository

    async def plan_order_candidate(
        self,
        *,
        order_candidate_id: str,
        owner_reviewed: bool = False,
        active_positions_count: Optional[int] = None,
    ) -> RuntimeExecutionPlan:
        candidate = await self._signal_evaluation_service.get_order_candidate(
            order_candidate_id
        )
        if not candidate.runtime_instance_id:
            raise ValueError("OrderCandidate is not linked to a runtime instance")
        await self._runtime_service.get_runtime(candidate.runtime_instance_id)
        preview = await self._final_gate_preview_service.preview_order_candidate(
            order_candidate_id=order_candidate_id,
            active_positions_count=active_positions_count,
            owner_reviewed=owner_reviewed,
            metadata={"runtime_execution_plan": True},
        )
        return build_runtime_execution_plan(
            candidate=candidate,
            preview=preview,
            now_ms=_now_ms(),
        )

    async def intent_draft_for_order_candidate(
        self,
        *,
        order_candidate_id: str,
        owner_reviewed: bool = False,
        owner_confirmed_for_intent: bool = False,
        active_positions_count: Optional[int] = None,
    ) -> RuntimeExecutionIntentDraft:
        plan = await self.plan_order_candidate(
            order_candidate_id=order_candidate_id,
            owner_reviewed=owner_reviewed,
            active_positions_count=active_positions_count,
        )
        return build_runtime_execution_intent_draft(
            plan=plan,
            owner_confirmed_for_intent=owner_confirmed_for_intent,
            now_ms=_now_ms(),
        )

    async def record_intent_draft_for_order_candidate(
        self,
        *,
        order_candidate_id: str,
        owner_reviewed: bool = False,
        owner_confirmed_for_intent: bool = False,
        active_positions_count: Optional[int] = None,
    ) -> RuntimeExecutionIntentDraft:
        if self._intent_draft_repository is None:
            raise RuntimeError("runtime_execution_intent_draft_repository_unavailable")
        draft = await self.intent_draft_for_order_candidate(
            order_candidate_id=order_candidate_id,
            owner_reviewed=owner_reviewed,
            owner_confirmed_for_intent=owner_confirmed_for_intent,
            active_positions_count=active_positions_count,
        )
        return await self._intent_draft_repository.create(draft)


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)
