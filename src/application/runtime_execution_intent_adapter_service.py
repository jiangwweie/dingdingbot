"""Non-executing RuntimeExecutionIntent adapter service."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from typing import Protocol

from src.domain.execution_intent import ExecutionIntent, ExecutionIntentStatus
from src.domain.runtime_execution_intent_adapter import (
    RuntimeExecutionIntentCreationPreviewStatus,
    RuntimeExecutionIntentSourceType,
    RuntimeExecutionIntentCreationPreview,
    RuntimeExecutionSubmitReadiness,
    build_runtime_execution_intent_creation_preview,
    build_runtime_execution_submit_readiness,
)
from src.domain.runtime_execution_plan import RuntimeExecutionIntentDraft
from src.domain.runtime_execution_controlled_submit import (
    RuntimeExecutionControlledSubmitPlan,
    RuntimeExecutionControlledSubmitPreflight,
    RuntimeExecutionControlledSubmitResult,
    build_runtime_execution_controlled_submit_preflight,
    build_runtime_execution_controlled_submit_result,
    build_runtime_execution_controlled_submit_plan,
)
from src.domain.runtime_execution_submit_authorization import (
    RuntimeExecutionSubmitAuthorization,
    build_runtime_execution_submit_authorization,
)
from src.domain.runtime_execution_submit_adapter import (
    RuntimeExecutionSubmitAdapterPreview,
    build_runtime_execution_submit_adapter_preview,
)
from src.domain.runtime_execution_submit_rehearsal import (
    RuntimeExecutionSubmitRehearsal,
    build_runtime_execution_submit_rehearsal,
)
from src.domain.runtime_execution_protection_plan import (
    RuntimeExecutionProtectionPlan,
    RuntimeExecutionProtectionPlanPreview,
    build_runtime_execution_protection_plan,
    build_runtime_execution_protection_plan_preview,
)
from src.domain.runtime_execution_order_lifecycle_handoff import (
    RuntimeExecutionOrderLifecycleHandoffDraft,
    build_runtime_execution_order_lifecycle_handoff_draft,
)
from src.domain.runtime_execution_order_lifecycle_adapter import (
    RuntimeExecutionOrderLifecycleAdapterPreview,
    build_runtime_execution_order_lifecycle_adapter_preview,
)
from src.domain.runtime_execution_attempt_reservation import (
    RuntimeExecutionAttemptReservation,
    RuntimeExecutionAttemptReservationPreview,
    build_runtime_execution_attempt_reservation,
    build_runtime_execution_attempt_reservation_preview,
)
from src.domain.runtime_execution_attempt_mutation import (
    RuntimeExecutionAttemptMutation,
    build_runtime_execution_attempt_mutation,
)
from src.domain.strategy_runtime import StrategyRuntimeInstance


class RuntimeExecutionIntentDraftPort(Protocol):
    async def get(self, draft_id: str) -> RuntimeExecutionIntentDraft | None:
        ...


class RuntimeExecutionIntentRepositoryPort(Protocol):
    async def get(self, intent_id: str) -> ExecutionIntent | None:
        ...

    async def save(self, intent: ExecutionIntent) -> None:
        ...


class RuntimeExecutionSubmitAuthorizationRepositoryPort(Protocol):
    async def get(
        self,
        authorization_id: str,
    ) -> RuntimeExecutionSubmitAuthorization | None:
        ...

    async def create(
        self,
        authorization: RuntimeExecutionSubmitAuthorization,
    ) -> RuntimeExecutionSubmitAuthorization:
        ...


class RuntimeExecutionControlledSubmitResultRepositoryPort(Protocol):
    async def create(
        self,
        result: RuntimeExecutionControlledSubmitResult,
    ) -> RuntimeExecutionControlledSubmitResult:
        ...


class RuntimeExecutionAttemptReservationRepositoryPort(Protocol):
    async def get(
        self,
        reservation_id: str,
    ) -> RuntimeExecutionAttemptReservation | None:
        ...

    async def create(
        self,
        reservation: RuntimeExecutionAttemptReservation,
    ) -> RuntimeExecutionAttemptReservation:
        ...


class RuntimeExecutionAttemptMutationRepositoryPort(Protocol):
    async def get(
        self,
        mutation_id: str,
    ) -> RuntimeExecutionAttemptMutation | None:
        ...

    async def create(
        self,
        mutation: RuntimeExecutionAttemptMutation,
    ) -> RuntimeExecutionAttemptMutation:
        ...


class RuntimeExecutionProtectionPlanRepositoryPort(Protocol):
    async def get(
        self,
        protection_plan_id: str,
    ) -> RuntimeExecutionProtectionPlan | None:
        ...

    async def create(
        self,
        plan: RuntimeExecutionProtectionPlan,
    ) -> RuntimeExecutionProtectionPlan:
        ...


class RuntimeExecutionOrderLifecycleHandoffRepositoryPort(Protocol):
    async def get(
        self,
        handoff_draft_id: str,
    ) -> RuntimeExecutionOrderLifecycleHandoffDraft | None:
        ...

    async def create(
        self,
        draft: RuntimeExecutionOrderLifecycleHandoffDraft,
    ) -> RuntimeExecutionOrderLifecycleHandoffDraft:
        ...


class RuntimeFinalGatePreviewPort(Protocol):
    async def preview_order_candidate(
        self,
        order_candidate_id: str,
        *,
        active_positions_count: int | None = None,
        owner_reviewed: bool = False,
        metadata: dict | None = None,
    ):
        ...


class RuntimeExecutionRuntimeServicePort(Protocol):
    async def get_runtime(self, runtime_instance_id: str) -> StrategyRuntimeInstance:
        ...

    async def apply_runtime_attempt_mutation(
        self,
        *,
        previous_runtime: StrategyRuntimeInstance,
        updated_runtime: StrategyRuntimeInstance,
        mutation: RuntimeExecutionAttemptMutation,
    ) -> StrategyRuntimeInstance:
        ...


class RuntimeExecutionIntentAdapterService:
    """Build non-executing previews for future ExecutionIntent creation."""

    def __init__(
        self,
        *,
        draft_repository: RuntimeExecutionIntentDraftPort,
        intent_repository: RuntimeExecutionIntentRepositoryPort | None = None,
        submit_authorization_repository: (
            RuntimeExecutionSubmitAuthorizationRepositoryPort | None
        ) = None,
        controlled_submit_result_repository: (
            RuntimeExecutionControlledSubmitResultRepositoryPort | None
        ) = None,
        attempt_reservation_repository: (
            RuntimeExecutionAttemptReservationRepositoryPort | None
        ) = None,
        attempt_mutation_repository: (
            RuntimeExecutionAttemptMutationRepositoryPort | None
        ) = None,
        protection_plan_repository: (
            RuntimeExecutionProtectionPlanRepositoryPort | None
        ) = None,
        order_lifecycle_handoff_repository: (
            RuntimeExecutionOrderLifecycleHandoffRepositoryPort | None
        ) = None,
        final_gate_preview_service: RuntimeFinalGatePreviewPort | None = None,
        runtime_service: RuntimeExecutionRuntimeServicePort | None = None,
    ) -> None:
        self._draft_repository = draft_repository
        self._intent_repository = intent_repository
        self._submit_authorization_repository = submit_authorization_repository
        self._controlled_submit_result_repository = controlled_submit_result_repository
        self._attempt_reservation_repository = attempt_reservation_repository
        self._attempt_mutation_repository = attempt_mutation_repository
        self._protection_plan_repository = protection_plan_repository
        self._order_lifecycle_handoff_repository = order_lifecycle_handoff_repository
        self._final_gate_preview_service = final_gate_preview_service
        self._runtime_service = runtime_service

    async def preview_from_draft(
        self,
        runtime_execution_intent_draft_id: str,
    ) -> RuntimeExecutionIntentCreationPreview:
        draft = await self._draft_repository.get(runtime_execution_intent_draft_id)
        if draft is None:
            raise ValueError("RuntimeExecutionIntentDraft not found")
        return build_runtime_execution_intent_creation_preview(
            draft=draft,
            now_ms=_now_ms(),
        )

    async def create_recorded_intent_from_draft(
        self,
        runtime_execution_intent_draft_id: str,
    ) -> ExecutionIntent:
        if self._intent_repository is None:
            raise RuntimeError("runtime_execution_intent_repository_unavailable")
        draft = await self._draft_repository.get(runtime_execution_intent_draft_id)
        if draft is None:
            raise ValueError("RuntimeExecutionIntentDraft not found")
        preview = build_runtime_execution_intent_creation_preview(
            draft=draft,
            now_ms=_now_ms(),
        )
        if preview.status != RuntimeExecutionIntentCreationPreviewStatus.READY_FOR_OWNER_GATED_CREATION:
            raise ValueError("RuntimeExecutionIntentDraft is not ready for intent creation")

        now_ms = _now_ms()
        intent = ExecutionIntent(
            id=_intent_id_for_draft(draft.draft_id),
            symbol=draft.symbol,
            status=ExecutionIntentStatus.RECORDED,
            source_type=RuntimeExecutionIntentSourceType.BRC_RUNTIME_ORDER_CANDIDATE.value,
            source_id=draft.order_candidate_id,
            source_payload={
                **preview.source_payload,
                "adapter_preview_id": preview.adapter_preview_id,
                "recorded_intent_only": True,
                "submit_authorized": False,
                "order_created": False,
                "exchange_called": False,
            },
            runtime_execution_intent_draft_id=draft.draft_id,
            runtime_instance_id=draft.runtime_instance_id,
            trial_binding_id=draft.semantic_ids.trial_binding_id,
            strategy_family_id=draft.semantic_ids.strategy_family_id,
            strategy_family_version_id=draft.semantic_ids.strategy_family_version_id,
            signal_evaluation_id=draft.signal_evaluation_id,
            order_candidate_id=draft.order_candidate_id,
            created_at=now_ms,
            updated_at=now_ms,
        )
        await self._intent_repository.save(intent)
        return intent

    async def submit_readiness_for_intent(
        self,
        execution_intent_id: str,
    ) -> RuntimeExecutionSubmitReadiness:
        if self._intent_repository is None:
            raise RuntimeError("runtime_execution_intent_repository_unavailable")
        intent = await self._intent_repository.get(execution_intent_id)
        if intent is None:
            raise ValueError("ExecutionIntent not found")
        return build_runtime_execution_submit_readiness(
            intent=intent,
            now_ms=_now_ms(),
        )

    async def protection_plan_preview_for_intent(
        self,
        execution_intent_id: str,
    ) -> RuntimeExecutionProtectionPlanPreview:
        if self._intent_repository is None:
            raise RuntimeError("runtime_execution_intent_repository_unavailable")
        intent = await self._intent_repository.get(execution_intent_id)
        if intent is None:
            raise ValueError("ExecutionIntent not found")
        return build_runtime_execution_protection_plan_preview(
            intent=intent,
            now_ms=_now_ms(),
        )

    async def record_protection_plan_for_intent(
        self,
        execution_intent_id: str,
    ) -> RuntimeExecutionProtectionPlan:
        if self._protection_plan_repository is None:
            raise RuntimeError("runtime_execution_protection_plan_repository_unavailable")
        preview = await self.protection_plan_preview_for_intent(execution_intent_id)
        plan = build_runtime_execution_protection_plan(
            preview=preview,
            now_ms=_now_ms(),
        )
        return await self._protection_plan_repository.create(plan)

    async def create_submit_authorization_for_intent(
        self,
        execution_intent_id: str,
        *,
        owner_confirmed_for_submit: bool,
    ) -> RuntimeExecutionSubmitAuthorization:
        if self._submit_authorization_repository is None:
            raise RuntimeError("runtime_execution_submit_authorization_repository_unavailable")
        readiness = await self.submit_readiness_for_intent(execution_intent_id)
        authorization = build_runtime_execution_submit_authorization(
            readiness=readiness,
            owner_confirmed_for_submit=owner_confirmed_for_submit,
            now_ms=_now_ms(),
        )
        return await self._submit_authorization_repository.create(authorization)

    async def controlled_submit_plan_for_authorization(
        self,
        authorization_id: str,
    ) -> RuntimeExecutionControlledSubmitPlan:
        if self._intent_repository is None:
            raise RuntimeError("runtime_execution_intent_repository_unavailable")
        if self._submit_authorization_repository is None:
            raise RuntimeError("runtime_execution_submit_authorization_repository_unavailable")
        authorization = await self._submit_authorization_repository.get(authorization_id)
        if authorization is None:
            raise ValueError("RuntimeExecutionSubmitAuthorization not found")
        intent = await self._intent_repository.get(authorization.execution_intent_id)
        if intent is None:
            raise ValueError("ExecutionIntent not found")
        return build_runtime_execution_controlled_submit_plan(
            authorization=authorization,
            intent=intent,
            now_ms=_now_ms(),
        )

    async def controlled_submit_for_authorization(
        self,
        authorization_id: str,
        *,
        submit_enabled: bool = False,
    ) -> RuntimeExecutionControlledSubmitResult:
        preflight = await self.controlled_submit_preflight_for_authorization(authorization_id)
        return build_runtime_execution_controlled_submit_result(
            preflight=preflight,
            submit_enabled=submit_enabled,
            now_ms=_now_ms(),
        )

    async def controlled_submit_preflight_for_authorization(
        self,
        authorization_id: str,
    ) -> RuntimeExecutionControlledSubmitPreflight:
        if self._final_gate_preview_service is None:
            raise RuntimeError("runtime_final_gate_preview_service_unavailable")
        plan = await self.controlled_submit_plan_for_authorization(authorization_id)
        if not plan.source_id:
            raise ValueError("OrderCandidate source_id missing")
        final_gate_preview = await self._final_gate_preview_service.preview_order_candidate(
            order_candidate_id=plan.source_id,
            active_positions_count=None,
            owner_reviewed=True,
            metadata={
                "api": "runtime_controlled_submit_preflight",
                "authorization_id": authorization_id,
                "execution_intent_id": plan.execution_intent_id,
            },
        )
        return build_runtime_execution_controlled_submit_preflight(
            plan=plan,
            final_gate_preview=final_gate_preview,
            now_ms=_now_ms(),
        )

    async def controlled_submit_adapter_preview_for_authorization(
        self,
        authorization_id: str,
    ) -> RuntimeExecutionSubmitAdapterPreview:
        if self._intent_repository is None:
            raise RuntimeError("runtime_execution_intent_repository_unavailable")
        preflight = await self.controlled_submit_preflight_for_authorization(
            authorization_id
        )
        intent = await self._intent_repository.get(preflight.execution_intent_id)
        if intent is None:
            raise ValueError("ExecutionIntent not found")
        attempt_reservation_preview = await self.attempt_reservation_preview_for_authorization(
            authorization_id
        )
        return build_runtime_execution_submit_adapter_preview(
            preflight=preflight,
            intent=intent,
            attempt_reservation_preview=attempt_reservation_preview,
            now_ms=_now_ms(),
        )

    async def submit_rehearsal_for_authorization(
        self,
        authorization_id: str,
    ) -> RuntimeExecutionSubmitRehearsal:
        if self._intent_repository is None:
            raise RuntimeError("runtime_execution_intent_repository_unavailable")
        if self._submit_authorization_repository is None:
            raise RuntimeError("runtime_execution_submit_authorization_repository_unavailable")
        authorization = await self._submit_authorization_repository.get(authorization_id)
        if authorization is None:
            raise ValueError("RuntimeExecutionSubmitAuthorization not found")
        intent = await self._intent_repository.get(authorization.execution_intent_id)
        if intent is None:
            raise ValueError("ExecutionIntent not found")

        submit_readiness = build_runtime_execution_submit_readiness(
            intent=intent,
            now_ms=_now_ms(),
        )
        plan = build_runtime_execution_controlled_submit_plan(
            authorization=authorization,
            intent=intent,
            now_ms=_now_ms(),
        )
        preflight = await self.controlled_submit_preflight_for_authorization(
            authorization_id
        )
        protection_plan_preview = build_runtime_execution_protection_plan_preview(
            intent=intent,
            now_ms=_now_ms(),
        )
        if self._runtime_service is None:
            raise RuntimeError("runtime_service_unavailable")
        if not intent.runtime_instance_id:
            raise ValueError("ExecutionIntent runtime_instance_id missing")
        runtime = await self._runtime_service.get_runtime(intent.runtime_instance_id)
        attempt_reservation_preview = build_runtime_execution_attempt_reservation_preview(
            preflight=preflight,
            intent=intent,
            runtime=runtime,
            now_ms=_now_ms(),
        )
        submit_adapter_preview = build_runtime_execution_submit_adapter_preview(
            preflight=preflight,
            intent=intent,
            attempt_reservation_preview=attempt_reservation_preview,
            now_ms=_now_ms(),
        )
        return build_runtime_execution_submit_rehearsal(
            intent=intent,
            submit_readiness=submit_readiness,
            controlled_submit_plan=plan,
            controlled_submit_preflight=preflight,
            protection_plan_preview=protection_plan_preview,
            attempt_reservation_preview=attempt_reservation_preview,
            submit_adapter_preview=submit_adapter_preview,
            now_ms=_now_ms(),
        )

    async def attempt_reservation_preview_for_authorization(
        self,
        authorization_id: str,
    ) -> RuntimeExecutionAttemptReservationPreview:
        if self._intent_repository is None:
            raise RuntimeError("runtime_execution_intent_repository_unavailable")
        if self._runtime_service is None:
            raise RuntimeError("runtime_service_unavailable")
        preflight = await self.controlled_submit_preflight_for_authorization(
            authorization_id
        )
        intent = await self._intent_repository.get(preflight.execution_intent_id)
        if intent is None:
            raise ValueError("ExecutionIntent not found")
        if not intent.runtime_instance_id:
            raise ValueError("ExecutionIntent runtime_instance_id missing")
        runtime = await self._runtime_service.get_runtime(intent.runtime_instance_id)
        return build_runtime_execution_attempt_reservation_preview(
            preflight=preflight,
            intent=intent,
            runtime=runtime,
            now_ms=_now_ms(),
        )

    async def record_controlled_submit_result_for_authorization(
        self,
        authorization_id: str,
        *,
        submit_enabled: bool = False,
    ) -> RuntimeExecutionControlledSubmitResult:
        if self._controlled_submit_result_repository is None:
            raise RuntimeError("runtime_execution_controlled_submit_result_repository_unavailable")
        result = await self.controlled_submit_for_authorization(
            authorization_id,
            submit_enabled=submit_enabled,
        )
        return await self._controlled_submit_result_repository.create(result)

    async def record_attempt_reservation_for_authorization(
        self,
        authorization_id: str,
    ) -> RuntimeExecutionAttemptReservation:
        if self._attempt_reservation_repository is None:
            raise RuntimeError("runtime_execution_attempt_reservation_repository_unavailable")
        preview = await self.attempt_reservation_preview_for_authorization(
            authorization_id
        )
        reservation = build_runtime_execution_attempt_reservation(
            preview=preview,
            now_ms=_now_ms(),
        )
        return await self._attempt_reservation_repository.create(reservation)

    async def apply_attempt_mutation_for_reservation(
        self,
        reservation_id: str,
    ) -> RuntimeExecutionAttemptMutation:
        if self._attempt_reservation_repository is None:
            raise RuntimeError("runtime_execution_attempt_reservation_repository_unavailable")
        if self._attempt_mutation_repository is None:
            raise RuntimeError("runtime_execution_attempt_mutation_repository_unavailable")
        if self._runtime_service is None:
            raise RuntimeError("runtime_service_unavailable")
        reservation = await self._attempt_reservation_repository.get(reservation_id)
        if reservation is None:
            raise ValueError("RuntimeExecutionAttemptReservation not found")
        runtime = await self._runtime_service.get_runtime(reservation.runtime_instance_id)
        mutation, updated_runtime = build_runtime_execution_attempt_mutation(
            reservation=reservation,
            runtime=runtime,
            now_ms=_now_ms(),
        )
        if updated_runtime is not None:
            await self._runtime_service.apply_runtime_attempt_mutation(
                previous_runtime=runtime,
                updated_runtime=updated_runtime,
                mutation=mutation,
            )
        return await self._attempt_mutation_repository.create(mutation)

    async def record_order_lifecycle_handoff_draft_for_authorization(
        self,
        authorization_id: str,
    ) -> RuntimeExecutionOrderLifecycleHandoffDraft:
        if self._intent_repository is None:
            raise RuntimeError("runtime_execution_intent_repository_unavailable")
        if self._attempt_mutation_repository is None:
            raise RuntimeError("runtime_execution_attempt_mutation_repository_unavailable")
        if self._protection_plan_repository is None:
            raise RuntimeError("runtime_execution_protection_plan_repository_unavailable")
        if self._order_lifecycle_handoff_repository is None:
            raise RuntimeError("runtime_execution_order_lifecycle_handoff_repository_unavailable")

        preflight = await self.controlled_submit_preflight_for_authorization(
            authorization_id
        )
        intent = await self._intent_repository.get(preflight.execution_intent_id)
        if intent is None:
            raise ValueError("ExecutionIntent not found")

        attempt_mutation_id = (
            "runtime-attempt-mutation-"
            f"runtime-attempt-reservation-{authorization_id}"
        )
        attempt_mutation = await self._attempt_mutation_repository.get(
            attempt_mutation_id
        )
        if attempt_mutation is None:
            raise ValueError("RuntimeExecutionAttemptMutation not found")

        protection_plan_id = f"runtime-protection-plan-{intent.id}"
        protection_plan = await self._protection_plan_repository.get(
            protection_plan_id
        )
        if protection_plan is None:
            raise ValueError("RuntimeExecutionProtectionPlan not found")

        draft = build_runtime_execution_order_lifecycle_handoff_draft(
            preflight=preflight,
            intent=intent,
            attempt_mutation=attempt_mutation,
            protection_plan=protection_plan,
            now_ms=_now_ms(),
        )
        return await self._order_lifecycle_handoff_repository.create(draft)

    async def order_lifecycle_adapter_preview_for_authorization(
        self,
        authorization_id: str,
    ) -> RuntimeExecutionOrderLifecycleAdapterPreview:
        if self._order_lifecycle_handoff_repository is None:
            raise RuntimeError("runtime_execution_order_lifecycle_handoff_repository_unavailable")
        handoff_draft_id = f"runtime-order-lifecycle-handoff-{authorization_id}"
        handoff = await self._order_lifecycle_handoff_repository.get(
            handoff_draft_id
        )
        if handoff is None:
            raise ValueError("RuntimeExecutionOrderLifecycleHandoffDraft not found")
        return build_runtime_execution_order_lifecycle_adapter_preview(
            handoff=handoff,
            now_ms=_now_ms(),
        )


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _intent_id_for_draft(draft_id: str) -> str:
    digest = sha256(draft_id.encode("utf-8")).hexdigest()[:24]
    return f"intent_rt_{digest}"
