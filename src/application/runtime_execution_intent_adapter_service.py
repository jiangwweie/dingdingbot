"""Non-executing RuntimeExecutionIntent adapter service."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from decimal import Decimal
from typing import Any, Protocol

from src.domain.execution_intent import ExecutionIntent, ExecutionIntentStatus
from src.domain.models import Order
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
from src.domain.runtime_execution_protection_plan import (
    RuntimeExecutionProtectionPlan,
    RuntimeExecutionProtectionPlanPreview,
    build_runtime_execution_protection_plan,
    build_runtime_execution_protection_plan_preview,
)
from src.domain.runtime_execution_protection_failure_policy import (
    RuntimeExecutionProtectionFailurePolicy,
    RuntimeExecutionProtectionFailurePolicyStatus,
    build_runtime_execution_protection_failure_policy,
)
from src.domain.runtime_execution_submit_idempotency import (
    RuntimeExecutionSubmitIdempotencySnapshot,
    RuntimeExecutionSubmitIdempotencyStatus,
    build_runtime_execution_submit_idempotency_snapshot,
)
from src.domain.runtime_execution_duplicate_submit_replay_proof import (
    RuntimeExecutionDuplicateSubmitReplayProof,
    build_runtime_execution_duplicate_submit_replay_proof,
)
from src.domain.runtime_execution_submit_prerequisite_evidence_proof import (
    RuntimeExecutionSubmitPrerequisiteEvidenceProof,
    build_runtime_execution_submit_prerequisite_evidence_proof,
)
from src.domain.runtime_execution_trusted_submit_facts import (
    RuntimeExecutionTrustedSubmitFactsSnapshot,
    RuntimeExecutionTrustedSubmitFactsStatus,
)
from src.domain.runtime_execution_order_lifecycle_handoff import (
    RuntimeExecutionOrderLifecycleHandoffDraft,
    build_runtime_execution_order_lifecycle_handoff_draft,
)
from src.domain.runtime_execution_order_lifecycle_adapter import (
    RuntimeExecutionOrderLifecycleAdapterPreview,
    build_runtime_execution_order_lifecycle_adapter_preview,
)
from src.domain.runtime_execution_order_registration_draft import (
    RuntimeExecutionOrderRegistrationDraftPreview,
    build_runtime_execution_order_registration_draft_preview,
)
from src.domain.runtime_execution_local_registration_enablement import (
    RuntimeExecutionLocalRegistrationEnablementDecision,
    RuntimeExecutionLocalRegistrationEnablementStatus,
    build_runtime_execution_local_registration_enablement_decision,
)
from src.domain.runtime_execution_local_registration_gate import (
    RuntimeExecutionLocalRegistrationGate,
    RuntimeExecutionLocalRegistrationGateStatus,
)
from src.domain.runtime_execution_local_registration_action_authorization import (
    RuntimeExecutionLocalRegistrationActionAuthorization,
    RuntimeExecutionLocalRegistrationActionAuthorizationStatus,
    build_runtime_execution_local_registration_action_authorization,
)
from src.domain.runtime_execution_order_lifecycle_adapter_result import (
    RuntimeExecutionOrderLifecycleAdapterResult,
    build_runtime_execution_order_lifecycle_adapter_lock_result,
    build_runtime_execution_order_lifecycle_adapter_registration_failure_result,
    build_runtime_execution_order_lifecycle_adapter_result,
    build_runtime_execution_orders_for_registration,
)
from src.domain.runtime_execution_intent_local_order_binding import (
    RuntimeExecutionIntentLocalOrderBinding,
    RuntimeExecutionIntentLocalOrderBindingStatus,
    build_runtime_execution_intent_local_order_binding,
)
from src.domain.runtime_execution_exchange_submit_packet import (
    RuntimeExecutionExchangeSubmitPacketPreview,
    build_runtime_execution_exchange_submit_packet_preview,
)
from src.domain.runtime_execution_exchange_submit_enablement import (
    RuntimeExecutionExchangeSubmitEnablementDecision,
    RuntimeExecutionExchangeSubmitGateStatus,
    build_runtime_execution_exchange_submit_enablement_decision,
)
from src.domain.runtime_execution_exchange_submit_adapter_result import (
    RuntimeExecutionExchangeSubmitAdapterResult,
    RuntimeExecutionExchangeSubmitAdapterResultStatus,
    build_runtime_execution_exchange_submit_adapter_lock_result,
    build_runtime_execution_exchange_submit_adapter_result,
)
from src.domain.runtime_execution_exchange_submit_action_authorization import (
    RuntimeExecutionExchangeSubmitActionAuthorization,
    RuntimeExecutionExchangeSubmitActionAuthorizationStatus,
    build_runtime_execution_exchange_submit_action_authorization,
)
from src.domain.runtime_execution_exchange_submit_execution_result import (
    RuntimeExecutionExchangeSubmitExecutionResult,
    RuntimeExecutionExchangeSubmitExecutionStatus,
    build_runtime_exchange_submit_execution_blocked_result,
    build_runtime_exchange_submit_execution_disabled_result,
    build_runtime_exchange_submit_execution_failed_result,
    build_runtime_exchange_submit_execution_lock_result,
    build_runtime_exchange_submit_execution_submitted_result,
    submitted_exchange_order_from_placement,
)
from src.domain.runtime_execution_submit_outcome_review import (
    RuntimeExecutionSubmitOutcomeReview,
    RuntimeExecutionSubmitOutcomeReviewStatus,
    build_runtime_execution_submit_outcome_review,
)
from src.domain.runtime_execution_exchange_submit_recovery_resolution import (
    RuntimeExecutionExchangeSubmitRecoveryResolution,
    RuntimeExecutionExchangeSubmitRecoveryResolutionStatus,
    build_runtime_execution_exchange_submit_recovery_resolution,
)
from src.domain.runtime_execution_exchange_gateway_readiness import (
    RuntimeExecutionExchangeGatewayReadiness,
    RuntimeExecutionExchangeGatewayReadinessStatus,
)
from src.domain.runtime_execution_submit_rehearsal import (
    RuntimeExecutionSubmitRehearsal,
    build_runtime_execution_submit_rehearsal,
    runtime_gateway_readiness_freshness_blockers,
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
from src.domain.runtime_execution_attempt_outcome_policy import (
    RuntimeExecutionAttemptOutcomeKind,
    RuntimeExecutionAttemptOutcomePolicy,
    RuntimeExecutionAttemptOutcomePolicyStatus,
    build_runtime_execution_attempt_outcome_policy,
)
from src.domain.strategy_runtime import StrategyRuntimeInstance


_EXCHANGE_SUBMIT_PROTECTION_FAILED_RECOVERY_TYPE = (
    "exchange_submit_protection_fail"
)


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


class RuntimeExecutionAttemptOutcomePolicyRepositoryPort(Protocol):
    async def create(
        self,
        policy: RuntimeExecutionAttemptOutcomePolicy,
    ) -> RuntimeExecutionAttemptOutcomePolicy:
        ...

    async def get(
        self,
        policy_id: str,
    ) -> RuntimeExecutionAttemptOutcomePolicy | None:
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


class RuntimeExecutionOrderLifecycleServicePort(Protocol):
    async def register_created_order(
        self,
        order: Order,
        *,
        metadata: dict | None = None,
    ) -> Order:
        ...

    async def get_order(self, order_id: str) -> Order | None:
        ...

    async def submit_order(
        self,
        order_id: str,
        exchange_order_id: str | None = None,
    ) -> Order:
        ...


class RuntimeExecutionOrderLifecycleAdapterResultRepositoryPort(Protocol):
    async def get_by_authorization_id(
        self,
        authorization_id: str,
    ) -> RuntimeExecutionOrderLifecycleAdapterResult | None:
        ...

    async def acquire_registration_lock(
        self,
        result: RuntimeExecutionOrderLifecycleAdapterResult,
    ) -> tuple[bool, RuntimeExecutionOrderLifecycleAdapterResult]:
        ...

    async def complete_registration(
        self,
        result: RuntimeExecutionOrderLifecycleAdapterResult,
    ) -> RuntimeExecutionOrderLifecycleAdapterResult:
        ...


class RuntimeExecutionTrustedSubmitFactsRepositoryPort(Protocol):
    async def create(
        self,
        snapshot: RuntimeExecutionTrustedSubmitFactsSnapshot,
    ) -> RuntimeExecutionTrustedSubmitFactsSnapshot:
        ...

    async def get(
        self,
        trusted_submit_fact_snapshot_id: str,
    ) -> RuntimeExecutionTrustedSubmitFactsSnapshot | None:
        ...


class RuntimeExecutionSubmitIdempotencyRepositoryPort(Protocol):
    async def create(
        self,
        snapshot: RuntimeExecutionSubmitIdempotencySnapshot,
    ) -> RuntimeExecutionSubmitIdempotencySnapshot:
        ...

    async def get(
        self,
        submit_idempotency_policy_id: str,
    ) -> RuntimeExecutionSubmitIdempotencySnapshot | None:
        ...


class RuntimeExecutionProtectionFailurePolicyRepositoryPort(Protocol):
    async def create(
        self,
        policy: RuntimeExecutionProtectionFailurePolicy,
    ) -> RuntimeExecutionProtectionFailurePolicy:
        ...

    async def get(
        self,
        policy_id: str,
    ) -> RuntimeExecutionProtectionFailurePolicy | None:
        ...


class RuntimeExecutionExchangeSubmitAdapterResultRepositoryPort(Protocol):
    async def get_by_authorization_id(
        self,
        authorization_id: str,
    ) -> RuntimeExecutionExchangeSubmitAdapterResult | None:
        ...

    async def acquire_exchange_submit_lock(
        self,
        result: RuntimeExecutionExchangeSubmitAdapterResult,
    ) -> tuple[bool, RuntimeExecutionExchangeSubmitAdapterResult]:
        ...

    async def complete_exchange_submit_result(
        self,
        result: RuntimeExecutionExchangeSubmitAdapterResult,
    ) -> RuntimeExecutionExchangeSubmitAdapterResult:
        ...


class RuntimeExecutionExchangeSubmitExecutionResultRepositoryPort(Protocol):
    async def get_by_authorization_id(
        self,
        authorization_id: str,
    ) -> RuntimeExecutionExchangeSubmitExecutionResult | None:
        ...

    async def acquire_exchange_submit_execution_lock(
        self,
        result: RuntimeExecutionExchangeSubmitExecutionResult,
    ) -> tuple[bool, RuntimeExecutionExchangeSubmitExecutionResult]:
        ...

    async def complete_exchange_submit_execution_result(
        self,
        result: RuntimeExecutionExchangeSubmitExecutionResult,
    ) -> RuntimeExecutionExchangeSubmitExecutionResult:
        ...


class RuntimeExecutionSubmitOutcomeReviewRepositoryPort(Protocol):
    async def create(
        self,
        review: RuntimeExecutionSubmitOutcomeReview,
    ) -> RuntimeExecutionSubmitOutcomeReview:
        ...

    async def get(
        self,
        review_id: str,
    ) -> RuntimeExecutionSubmitOutcomeReview | None:
        ...

    async def get_by_authorization_id(
        self,
        authorization_id: str,
    ) -> RuntimeExecutionSubmitOutcomeReview | None:
        ...


class RuntimeExecutionExchangeSubmitActionAuthorizationRepositoryPort(Protocol):
    async def create(
        self,
        authorization: RuntimeExecutionExchangeSubmitActionAuthorization,
    ) -> RuntimeExecutionExchangeSubmitActionAuthorization:
        ...

    async def get(
        self,
        action_authorization_id: str,
    ) -> RuntimeExecutionExchangeSubmitActionAuthorization | None:
        ...


class RuntimeExecutionLocalRegistrationActionAuthorizationRepositoryPort(Protocol):
    async def create(
        self,
        authorization: RuntimeExecutionLocalRegistrationActionAuthorization,
    ) -> RuntimeExecutionLocalRegistrationActionAuthorization:
        ...

    async def get(
        self,
        action_authorization_id: str,
    ) -> RuntimeExecutionLocalRegistrationActionAuthorization | None:
        ...


class RuntimeExecutionExchangeSubmitRecoveryResolutionRepositoryPort(Protocol):
    async def create(
        self,
        resolution: RuntimeExecutionExchangeSubmitRecoveryResolution,
    ) -> RuntimeExecutionExchangeSubmitRecoveryResolution:
        ...

    async def get_by_recovery_task_id(
        self,
        recovery_task_id: str,
    ) -> RuntimeExecutionExchangeSubmitRecoveryResolution | None:
        ...


class RuntimeExecutionExchangeGatewayReadinessRepositoryPort(Protocol):
    async def get(
        self,
        readiness_id: str,
    ) -> RuntimeExecutionExchangeGatewayReadiness | None:
        ...


class RuntimeExecutionExchangeGatewayPort(Protocol):
    async def place_order(
        self,
        *,
        symbol: str,
        order_type: str,
        side: str,
        amount: Decimal,
        price: Decimal | None = None,
        trigger_price: Decimal | None = None,
        reduce_only: bool = False,
        client_order_id: str | None = None,
    ) -> Any:
        ...


class RuntimeExecutionRecoveryRepositoryPort(Protocol):
    async def get(self, task_id: str) -> dict[str, Any] | None:
        ...

    async def create_task(
        self,
        task_id: str,
        intent_id: str,
        symbol: str,
        recovery_type: str,
        related_order_id: str | None = None,
        related_exchange_order_id: str | None = None,
        error_message: str | None = None,
        context_payload: dict[str, Any] | None = None,
    ) -> None:
        ...

    async def mark_resolved(
        self,
        task_id: str,
        resolved_at: int,
        error_message: str | None = None,
    ) -> None:
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
        attempt_outcome_policy_repository: (
            RuntimeExecutionAttemptOutcomePolicyRepositoryPort | None
        ) = None,
        protection_plan_repository: (
            RuntimeExecutionProtectionPlanRepositoryPort | None
        ) = None,
        order_lifecycle_handoff_repository: (
            RuntimeExecutionOrderLifecycleHandoffRepositoryPort | None
        ) = None,
        order_lifecycle_service: (
            RuntimeExecutionOrderLifecycleServicePort | None
        ) = None,
        order_lifecycle_adapter_result_repository: (
            RuntimeExecutionOrderLifecycleAdapterResultRepositoryPort | None
        ) = None,
        trusted_submit_facts_repository: (
            RuntimeExecutionTrustedSubmitFactsRepositoryPort | None
        ) = None,
        submit_idempotency_repository: (
            RuntimeExecutionSubmitIdempotencyRepositoryPort | None
        ) = None,
        protection_failure_policy_repository: (
            RuntimeExecutionProtectionFailurePolicyRepositoryPort | None
        ) = None,
        exchange_submit_adapter_result_repository: (
            RuntimeExecutionExchangeSubmitAdapterResultRepositoryPort | None
        ) = None,
        exchange_submit_action_authorization_repository: (
            RuntimeExecutionExchangeSubmitActionAuthorizationRepositoryPort | None
        ) = None,
        local_registration_action_authorization_repository: (
            RuntimeExecutionLocalRegistrationActionAuthorizationRepositoryPort | None
        ) = None,
        exchange_submit_execution_result_repository: (
            RuntimeExecutionExchangeSubmitExecutionResultRepositoryPort | None
        ) = None,
        submit_outcome_review_repository: (
            RuntimeExecutionSubmitOutcomeReviewRepositoryPort | None
        ) = None,
        exchange_submit_recovery_resolution_repository: (
            RuntimeExecutionExchangeSubmitRecoveryResolutionRepositoryPort | None
        ) = None,
        exchange_gateway_readiness_repository: (
            RuntimeExecutionExchangeGatewayReadinessRepositoryPort | None
        ) = None,
        execution_recovery_repository: (
            RuntimeExecutionRecoveryRepositoryPort | None
        ) = None,
        exchange_gateway: RuntimeExecutionExchangeGatewayPort | None = None,
        final_gate_preview_service: RuntimeFinalGatePreviewPort | None = None,
        runtime_service: RuntimeExecutionRuntimeServicePort | None = None,
    ) -> None:
        self._draft_repository = draft_repository
        self._intent_repository = intent_repository
        self._submit_authorization_repository = submit_authorization_repository
        self._controlled_submit_result_repository = controlled_submit_result_repository
        self._attempt_reservation_repository = attempt_reservation_repository
        self._attempt_mutation_repository = attempt_mutation_repository
        self._attempt_outcome_policy_repository = attempt_outcome_policy_repository
        self._protection_plan_repository = protection_plan_repository
        self._order_lifecycle_handoff_repository = order_lifecycle_handoff_repository
        self._order_lifecycle_service = order_lifecycle_service
        self._order_lifecycle_adapter_result_repository = (
            order_lifecycle_adapter_result_repository
        )
        self._trusted_submit_facts_repository = trusted_submit_facts_repository
        self._submit_idempotency_repository = submit_idempotency_repository
        self._protection_failure_policy_repository = (
            protection_failure_policy_repository
        )
        self._exchange_submit_adapter_result_repository = (
            exchange_submit_adapter_result_repository
        )
        self._exchange_submit_action_authorization_repository = (
            exchange_submit_action_authorization_repository
        )
        self._local_registration_action_authorization_repository = (
            local_registration_action_authorization_repository
        )
        self._exchange_submit_execution_result_repository = (
            exchange_submit_execution_result_repository
        )
        self._submit_outcome_review_repository = submit_outcome_review_repository
        self._exchange_submit_recovery_resolution_repository = (
            exchange_submit_recovery_resolution_repository
        )
        self._exchange_gateway_readiness_repository = (
            exchange_gateway_readiness_repository
        )
        self._execution_recovery_repository = execution_recovery_repository
        self._exchange_gateway = exchange_gateway
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

    async def protection_failure_policy_for_intent(
        self,
        execution_intent_id: str,
    ) -> RuntimeExecutionProtectionFailurePolicy:
        preview = await self.protection_plan_preview_for_intent(execution_intent_id)
        now_ms = _now_ms()
        plan = build_runtime_execution_protection_plan(
            preview=preview,
            now_ms=now_ms,
        )
        return build_runtime_execution_protection_failure_policy(
            protection_plan=plan,
            now_ms=now_ms,
        )

    async def record_protection_failure_policy_for_intent(
        self,
        execution_intent_id: str,
    ) -> RuntimeExecutionProtectionFailurePolicy:
        if self._protection_failure_policy_repository is None:
            raise RuntimeError(
                "runtime_execution_protection_failure_policy_repository_unavailable"
            )
        policy = await self.protection_failure_policy_for_intent(
            execution_intent_id
        )
        return await self._protection_failure_policy_repository.create(policy)

    async def submit_idempotency_snapshot_for_authorization(
        self,
        authorization_id: str,
        *,
        adapter_result_store_implemented: bool = False,
        real_adapter_boundary_implemented: bool = False,
    ) -> RuntimeExecutionSubmitIdempotencySnapshot:
        if self._intent_repository is None:
            raise RuntimeError("runtime_execution_intent_repository_unavailable")
        preflight = await self.controlled_submit_preflight_for_authorization(
            authorization_id
        )
        intent = await self._intent_repository.get(preflight.execution_intent_id)
        if intent is None:
            raise ValueError("ExecutionIntent not found")
        return build_runtime_execution_submit_idempotency_snapshot(
            preflight=preflight,
            intent=intent,
            adapter_result_store_implemented=adapter_result_store_implemented,
            real_adapter_boundary_implemented=real_adapter_boundary_implemented,
            now_ms=_now_ms(),
        )

    async def record_submit_idempotency_snapshot_for_authorization(
        self,
        authorization_id: str,
        *,
        adapter_result_store_implemented: bool = False,
        real_adapter_boundary_implemented: bool = False,
    ) -> RuntimeExecutionSubmitIdempotencySnapshot:
        if self._submit_idempotency_repository is None:
            raise RuntimeError(
                "runtime_execution_submit_idempotency_repository_unavailable"
            )
        snapshot = await self.submit_idempotency_snapshot_for_authorization(
            authorization_id,
            adapter_result_store_implemented=adapter_result_store_implemented,
            real_adapter_boundary_implemented=real_adapter_boundary_implemented,
        )
        return await self._submit_idempotency_repository.create(snapshot)

    async def record_trusted_submit_facts_snapshot(
        self,
        snapshot: RuntimeExecutionTrustedSubmitFactsSnapshot,
    ) -> RuntimeExecutionTrustedSubmitFactsSnapshot:
        if self._trusted_submit_facts_repository is None:
            raise RuntimeError(
                "runtime_execution_trusted_submit_facts_repository_unavailable"
            )
        return await self._trusted_submit_facts_repository.create(snapshot)

    async def resolve_first_real_submit_evidence_ids_for_authorization(
        self,
        authorization_id: str,
    ) -> dict[str, str]:
        """Resolve already-recorded deterministic evidence IDs for review packets.

        This is a read-only convenience for Owner/Codex review surfaces. It
        does not create evidence, approve missing evidence, mutate runtime
        state, create orders, call OrderLifecycle, or call exchange.
        """

        resolved: dict[str, str] = {}
        execution_intent_id: str | None = None
        if self._submit_authorization_repository is not None:
            authorization = await self._submit_authorization_repository.get(
                authorization_id
            )
            if authorization is not None:
                execution_intent_id = authorization.execution_intent_id

        if self._submit_idempotency_repository is not None:
            submit_idempotency_policy_id = (
                f"runtime-submit-idempotency-{authorization_id}"
            )
            snapshot = await self._submit_idempotency_repository.get(
                submit_idempotency_policy_id
            )
            if snapshot is not None:
                resolved["submit_idempotency_policy_id"] = (
                    submit_idempotency_policy_id
                )
                execution_intent_id = (
                    execution_intent_id or snapshot.execution_intent_id
                )

        if (
            execution_intent_id
            and self._trusted_submit_facts_repository is not None
        ):
            trusted_submit_fact_snapshot_id = (
                f"trusted-submit-facts-{execution_intent_id}"
            )
            snapshot = await self._trusted_submit_facts_repository.get(
                trusted_submit_fact_snapshot_id
            )
            if snapshot is not None:
                resolved["trusted_submit_fact_snapshot_id"] = (
                    trusted_submit_fact_snapshot_id
                )

        if self._attempt_outcome_policy_repository is not None:
            attempt_outcome_policy_id = (
                "runtime-attempt-outcome-policy-"
                f"runtime-attempt-reservation-{authorization_id}-"
                f"{RuntimeExecutionAttemptOutcomeKind.ENTRY_FILLED_PROTECTION_CREATION_FAILED.value}"
            )
            policy = await self._attempt_outcome_policy_repository.get(
                attempt_outcome_policy_id
            )
            if policy is not None:
                resolved["attempt_outcome_policy_id"] = attempt_outcome_policy_id

        if (
            execution_intent_id
            and self._protection_failure_policy_repository is not None
        ):
            protection_creation_failure_policy_id = (
                f"runtime-protection-failure-policy-{execution_intent_id}"
            )
            policy = await self._protection_failure_policy_repository.get(
                protection_creation_failure_policy_id
            )
            if policy is not None:
                resolved["protection_creation_failure_policy_id"] = (
                    protection_creation_failure_policy_id
                )

        return resolved

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

    async def attempt_outcome_policy_for_reservation(
        self,
        reservation_id: str,
        *,
        outcome_kind: RuntimeExecutionAttemptOutcomeKind,
    ) -> RuntimeExecutionAttemptOutcomePolicy:
        if self._attempt_reservation_repository is None:
            raise RuntimeError(
                "runtime_execution_attempt_reservation_repository_unavailable"
            )
        reservation = await self._attempt_reservation_repository.get(reservation_id)
        if reservation is None:
            raise ValueError("RuntimeExecutionAttemptReservation not found")
        mutation = None
        if self._attempt_mutation_repository is not None:
            mutation_id = f"runtime-attempt-mutation-{reservation_id}"
            mutation = await self._attempt_mutation_repository.get(mutation_id)
        return build_runtime_execution_attempt_outcome_policy(
            reservation=reservation,
            mutation=mutation,
            outcome_kind=outcome_kind,
            now_ms=_now_ms(),
        )

    async def record_attempt_outcome_policy_for_reservation(
        self,
        reservation_id: str,
        *,
        outcome_kind: RuntimeExecutionAttemptOutcomeKind,
    ) -> RuntimeExecutionAttemptOutcomePolicy:
        if self._attempt_outcome_policy_repository is None:
            raise RuntimeError(
                "runtime_execution_attempt_outcome_policy_repository_unavailable"
            )
        policy = await self.attempt_outcome_policy_for_reservation(
            reservation_id,
            outcome_kind=outcome_kind,
        )
        return await self._attempt_outcome_policy_repository.create(policy)

    async def record_attempt_outcome_policy_from_submit_outcome_review(
        self,
        reservation_id: str,
        *,
        submit_outcome_review_id: str | None = None,
    ) -> RuntimeExecutionAttemptOutcomePolicy:
        if self._attempt_outcome_policy_repository is None:
            raise RuntimeError(
                "runtime_execution_attempt_outcome_policy_repository_unavailable"
            )
        if self._attempt_reservation_repository is None:
            raise RuntimeError(
                "runtime_execution_attempt_reservation_repository_unavailable"
            )
        if self._submit_outcome_review_repository is None:
            raise RuntimeError(
                "runtime_execution_submit_outcome_review_repository_unavailable"
            )
        reservation = await self._attempt_reservation_repository.get(reservation_id)
        if reservation is None:
            raise ValueError("RuntimeExecutionAttemptReservation not found")
        if submit_outcome_review_id:
            review = await self._submit_outcome_review_repository.get(
                submit_outcome_review_id
            )
        else:
            review = await (
                self._submit_outcome_review_repository
                .get_by_authorization_id(reservation.authorization_id)
            )
        if review is None:
            raise ValueError("RuntimeExecutionSubmitOutcomeReview not found")
        blockers = _submit_outcome_review_policy_blockers(
            reservation=reservation,
            review=review,
        )
        if blockers:
            raise ValueError(
                "RuntimeExecutionSubmitOutcomeReview not ready for attempt "
                f"outcome policy: {','.join(blockers)}"
            )
        assert review.recommended_attempt_outcome_kind is not None
        policy = await self.attempt_outcome_policy_for_reservation(
            reservation_id,
            outcome_kind=review.recommended_attempt_outcome_kind,
        )
        metadata = dict(policy.metadata)
        metadata.update(
            {
                "submit_outcome_review_id": review.review_id,
                "submit_observed_outcome": review.observed_outcome.value,
                "submit_outcome_policy_source": (
                    "runtime_execution_submit_outcome_review"
                ),
            }
        )
        policy = policy.model_copy(
            update={
                "metadata": metadata,
                "warnings": _dedupe(
                    list(policy.warnings)
                    + [f"derived_from_submit_outcome_review:{review.review_id}"]
                ),
            }
        )
        return await self._attempt_outcome_policy_repository.create(policy)

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

    async def order_registration_draft_preview_for_authorization(
        self,
        authorization_id: str,
    ) -> RuntimeExecutionOrderRegistrationDraftPreview:
        adapter_preview = await self.order_lifecycle_adapter_preview_for_authorization(
            authorization_id
        )
        return build_runtime_execution_order_registration_draft_preview(
            adapter_preview=adapter_preview,
            now_ms=_now_ms(),
        )

    async def local_registration_action_authorization_for_authorization(
        self,
        authorization_id: str,
        *,
        trusted_submit_fact_snapshot_id: str | None = None,
        submit_idempotency_policy_id: str | None = None,
        attempt_outcome_policy_id: str | None = None,
        protection_creation_failure_policy_id: str | None = None,
        owner_real_submit_authorization_id: str | None = None,
        order_lifecycle_adapter_enablement_id: str | None = None,
        local_order_registration_enablement_id: str | None = None,
        owner_confirmed_for_local_registration_action: bool = False,
        owner_operator_id: str = "owner",
        reason: str = "owner confirmed scoped local registration action",
        deployment_readiness_evidence_id: str | None = None,
        owner_confirmation_reference: str | None = None,
        expires_at_ms: int | None = None,
    ) -> RuntimeExecutionLocalRegistrationActionAuthorization:
        registration_preview = (
            await self.order_registration_draft_preview_for_authorization(
                authorization_id
            )
        )
        return build_runtime_execution_local_registration_action_authorization(
            registration_preview=registration_preview,
            trusted_submit_fact_snapshot_id=trusted_submit_fact_snapshot_id,
            submit_idempotency_policy_id=submit_idempotency_policy_id,
            attempt_outcome_policy_id=attempt_outcome_policy_id,
            protection_creation_failure_policy_id=(
                protection_creation_failure_policy_id
            ),
            owner_real_submit_authorization_id=owner_real_submit_authorization_id,
            order_lifecycle_adapter_enablement_id=(
                order_lifecycle_adapter_enablement_id
            ),
            local_order_registration_enablement_id=(
                local_order_registration_enablement_id
            ),
            owner_confirmed_for_local_registration_action=(
                owner_confirmed_for_local_registration_action
            ),
            owner_operator_id=owner_operator_id,
            reason=reason,
            deployment_readiness_evidence_id=deployment_readiness_evidence_id,
            owner_confirmation_reference=owner_confirmation_reference,
            expires_at_ms=expires_at_ms,
            now_ms=_now_ms(),
        )

    async def record_local_registration_action_authorization_for_authorization(
        self,
        authorization_id: str,
        *,
        trusted_submit_fact_snapshot_id: str | None = None,
        submit_idempotency_policy_id: str | None = None,
        attempt_outcome_policy_id: str | None = None,
        protection_creation_failure_policy_id: str | None = None,
        owner_real_submit_authorization_id: str | None = None,
        order_lifecycle_adapter_enablement_id: str | None = None,
        local_order_registration_enablement_id: str | None = None,
        owner_confirmed_for_local_registration_action: bool = False,
        owner_operator_id: str = "owner",
        reason: str = "owner confirmed scoped local registration action",
        deployment_readiness_evidence_id: str | None = None,
        owner_confirmation_reference: str | None = None,
        expires_at_ms: int | None = None,
    ) -> RuntimeExecutionLocalRegistrationActionAuthorization:
        if self._local_registration_action_authorization_repository is None:
            raise RuntimeError(
                "runtime_execution_local_registration_action_authorization_"
                "repository_unavailable"
            )
        authorization = (
            await self.local_registration_action_authorization_for_authorization(
                authorization_id,
                trusted_submit_fact_snapshot_id=trusted_submit_fact_snapshot_id,
                submit_idempotency_policy_id=submit_idempotency_policy_id,
                attempt_outcome_policy_id=attempt_outcome_policy_id,
                protection_creation_failure_policy_id=(
                    protection_creation_failure_policy_id
                ),
                owner_real_submit_authorization_id=(
                    owner_real_submit_authorization_id
                ),
                order_lifecycle_adapter_enablement_id=(
                    order_lifecycle_adapter_enablement_id
                ),
                local_order_registration_enablement_id=(
                    local_order_registration_enablement_id
                ),
                owner_confirmed_for_local_registration_action=(
                    owner_confirmed_for_local_registration_action
                ),
                owner_operator_id=owner_operator_id,
                reason=reason,
                deployment_readiness_evidence_id=deployment_readiness_evidence_id,
                owner_confirmation_reference=owner_confirmation_reference,
                expires_at_ms=expires_at_ms,
            )
        )
        return await self._local_registration_action_authorization_repository.create(
            authorization
        )

    async def local_registration_enablement_decision_for_authorization(
        self,
        authorization_id: str,
        *,
        trusted_submit_fact_snapshot_id: str | None = None,
        submit_idempotency_policy_id: str | None = None,
        attempt_outcome_policy_id: str | None = None,
        protection_creation_failure_policy_id: str | None = None,
        owner_real_submit_authorization_id: str | None = None,
        order_lifecycle_adapter_enablement_id: str | None = None,
        local_order_registration_enablement_id: str | None = None,
        local_registration_action_authorization_id: str | None = None,
        deployment_readiness_evidence_id: str | None = None,
    ) -> RuntimeExecutionLocalRegistrationEnablementDecision:
        registration_preview = (
            await self.order_registration_draft_preview_for_authorization(
                authorization_id
            )
        )
        evidence_blockers, evidence_warnings = (
            await self._validate_first_real_submit_prerequisite_evidence(
                authorization_id=authorization_id,
                execution_intent_id=registration_preview.execution_intent_id,
                runtime_instance_id=registration_preview.runtime_instance_id,
                symbol=registration_preview.symbol,
                trusted_submit_fact_snapshot_id=trusted_submit_fact_snapshot_id,
                submit_idempotency_policy_id=submit_idempotency_policy_id,
                attempt_outcome_policy_id=attempt_outcome_policy_id,
                protection_creation_failure_policy_id=(
                    protection_creation_failure_policy_id
                ),
                order_lifecycle_adapter_enablement_id=(
                    order_lifecycle_adapter_enablement_id
                ),
                local_order_registration_enablement_id=(
                    local_order_registration_enablement_id
                ),
                local_registration_action_authorization_id=(
                    local_registration_action_authorization_id
                ),
            )
        )
        return build_runtime_execution_local_registration_enablement_decision(
            registration_preview=registration_preview,
            trusted_submit_fact_snapshot_id=trusted_submit_fact_snapshot_id,
            submit_idempotency_policy_id=submit_idempotency_policy_id,
            attempt_outcome_policy_id=attempt_outcome_policy_id,
            protection_creation_failure_policy_id=protection_creation_failure_policy_id,
            owner_real_submit_authorization_id=owner_real_submit_authorization_id,
            order_lifecycle_adapter_enablement_id=(
                order_lifecycle_adapter_enablement_id
            ),
            local_order_registration_enablement_id=(
                local_order_registration_enablement_id
            ),
            local_registration_action_authorization_id=(
                local_registration_action_authorization_id
            ),
            deployment_readiness_evidence_id=deployment_readiness_evidence_id,
            evidence_validation_blockers=evidence_blockers,
            evidence_validation_warnings=evidence_warnings,
            now_ms=_now_ms(),
        )

    async def order_lifecycle_adapter_result_for_authorization(
        self,
        authorization_id: str,
        *,
        order_lifecycle_adapter_enabled: bool = False,
        local_order_registration_enabled: bool = False,
        local_registration_enablement_decision: (
            RuntimeExecutionLocalRegistrationEnablementDecision | None
        ) = None,
    ) -> RuntimeExecutionOrderLifecycleAdapterResult:
        registration_preview = (
            await self.order_registration_draft_preview_for_authorization(
                authorization_id
            )
        )
        gate_blockers: list[str] = []
        gate_warnings: list[str] = []
        local_registration_gate: RuntimeExecutionLocalRegistrationGate | None = None
        local_registration_gate_id: str | None = None
        local_registration_enablement_decision_id: str | None = None

        if order_lifecycle_adapter_enabled or local_order_registration_enabled:
            if local_registration_enablement_decision is None:
                gate_blockers.append(
                    "first_real_submit_local_registration_enablement_decision_required"
                )
            else:
                local_registration_enablement_decision_id = (
                    local_registration_enablement_decision.decision_id
                )
                if (
                    local_registration_enablement_decision.authorization_id
                    != authorization_id
                ):
                    gate_blockers.append(
                        "local_registration_enablement_decision_authorization_mismatch"
                    )
                local_registration_gate = (
                    local_registration_enablement_decision.local_registration_gate
                )
                if (
                    local_registration_enablement_decision.status
                    != RuntimeExecutionLocalRegistrationEnablementStatus
                    .READY_FOR_LOCAL_REGISTRATION_ACTION
                ):
                    gate_blockers.append(
                        "local_registration_enablement_decision_not_ready"
                    )
                    gate_blockers.extend(
                        local_registration_enablement_decision.blockers
                    )
                gate_warnings.extend(local_registration_enablement_decision.warnings)

            if local_registration_gate is not None:
                local_registration_gate_id = local_registration_gate.gate_id
                if (
                    local_registration_gate.registration_preview_id
                    != registration_preview.registration_preview_id
                ):
                    gate_blockers.append("local_registration_gate_preview_mismatch")
                if (
                    local_registration_gate.status
                    != RuntimeExecutionLocalRegistrationGateStatus
                    .READY_FOR_LOCAL_CREATED_ORDER_REGISTRATION
                ):
                    gate_blockers.append("local_registration_gate_not_ready")
                    gate_blockers.extend(local_registration_gate.blockers)
                gate_warnings.extend(local_registration_gate.warnings)
                if (
                    local_registration_gate.order_lifecycle_adapter_enabled
                    != order_lifecycle_adapter_enabled
                ):
                    gate_blockers.append(
                        "local_registration_gate_adapter_flag_mismatch"
                    )
                if (
                    local_registration_gate.local_order_registration_enabled
                    != local_order_registration_enabled
                ):
                    gate_blockers.append(
                        "local_registration_gate_registration_flag_mismatch"
                    )

        should_register = (
            order_lifecycle_adapter_enabled
            and local_order_registration_enabled
            and not gate_blockers
            and not registration_preview.blockers
        )
        if should_register and self._order_lifecycle_adapter_result_repository is None:
            raise RuntimeError(
                "runtime_execution_order_lifecycle_adapter_result_repository_unavailable"
            )
        if should_register and self._order_lifecycle_service is None:
            raise RuntimeError("order_lifecycle_service_unavailable")

        duplicate_submit_lock_acquired = False
        if should_register:
            lock_result = build_runtime_execution_order_lifecycle_adapter_lock_result(
                registration_preview=registration_preview,
                local_registration_gate_id=local_registration_gate_id,
                local_registration_enablement_decision_id=(
                    local_registration_enablement_decision_id
                ),
                now_ms=_now_ms(),
            )
            acquired, existing = (
                await self._order_lifecycle_adapter_result_repository
                .acquire_registration_lock(lock_result)
            )
            if not acquired:
                return existing
            duplicate_submit_lock_acquired = True

        should_register = should_register and duplicate_submit_lock_acquired
        if not should_register:
            return build_runtime_execution_order_lifecycle_adapter_result(
                registration_preview=registration_preview,
                order_lifecycle_adapter_enabled=order_lifecycle_adapter_enabled,
                local_order_registration_enabled=local_order_registration_enabled,
                duplicate_submit_lock_acquired=duplicate_submit_lock_acquired,
                local_registration_gate_id=local_registration_gate_id,
                local_registration_enablement_decision_id=(
                    local_registration_enablement_decision_id
                ),
                additional_blockers=gate_blockers,
                additional_warnings=gate_warnings,
                now_ms=_now_ms(),
            )

        registered_orders: list[Order] = []
        orders = build_runtime_execution_orders_for_registration(
            registration_preview=registration_preview
        )
        for order in orders:
            try:
                registered = await self._order_lifecycle_service.register_created_order(
                    order,
                    metadata={
                        "scope": (
                            "runtime_order_lifecycle_adapter_local_registration"
                        ),
                        "runtime_instance_id": (
                            registration_preview.runtime_instance_id
                        ),
                        "execution_intent_id": (
                            registration_preview.execution_intent_id
                        ),
                        "authorization_id": registration_preview.authorization_id,
                        "source_type": registration_preview.source_type,
                        "source_id": registration_preview.source_id,
                        "exchange_order_submitted": False,
                        "exchange_called": False,
                        "execution_intent_status_changed": False,
                    },
                )
            except Exception as exc:
                result = (
                    build_runtime_execution_order_lifecycle_adapter_registration_failure_result(
                        registration_preview=registration_preview,
                        attempted_orders=orders,
                        registered_orders=registered_orders,
                        failed_order=order,
                        failure_reason=type(exc).__name__,
                        failure_message=str(exc),
                        local_registration_gate_id=local_registration_gate_id,
                        local_registration_enablement_decision_id=(
                            local_registration_enablement_decision_id
                        ),
                        now_ms=_now_ms(),
                    )
                )
                result = await (
                    self._order_lifecycle_adapter_result_repository
                    .complete_registration(result)
                )
                return result
            registered_orders.append(registered)

        result = build_runtime_execution_order_lifecycle_adapter_result(
            registration_preview=registration_preview,
            order_lifecycle_adapter_enabled=order_lifecycle_adapter_enabled,
            local_order_registration_enabled=local_order_registration_enabled,
            duplicate_submit_lock_acquired=duplicate_submit_lock_acquired,
            registered_orders=registered_orders,
            local_registration_gate_id=local_registration_gate_id,
            local_registration_enablement_decision_id=(
                local_registration_enablement_decision_id
            ),
            additional_warnings=gate_warnings,
            now_ms=_now_ms(),
        )
        return await (
            self._order_lifecycle_adapter_result_repository
            .complete_registration(result)
        )

    async def intent_local_order_binding_for_authorization(
        self,
        authorization_id: str,
    ) -> RuntimeExecutionIntentLocalOrderBinding:
        if self._intent_repository is None:
            raise RuntimeError("runtime_execution_intent_repository_unavailable")
        if self._order_lifecycle_adapter_result_repository is None:
            raise RuntimeError(
                "runtime_execution_order_lifecycle_adapter_result_repository_unavailable"
            )
        adapter_result = await (
            self._order_lifecycle_adapter_result_repository
            .get_by_authorization_id(authorization_id)
        )
        if adapter_result is None:
            raise ValueError("RuntimeExecutionOrderLifecycleAdapterResult not found")
        intent = await self._intent_repository.get(adapter_result.execution_intent_id)
        if intent is None:
            raise ValueError("ExecutionIntent not found")
        return build_runtime_execution_intent_local_order_binding(
            intent=intent,
            adapter_result=adapter_result,
            now_ms=_now_ms(),
        )

    async def exchange_submit_packet_preview_for_authorization(
        self,
        authorization_id: str,
    ) -> RuntimeExecutionExchangeSubmitPacketPreview:
        binding = await self.intent_local_order_binding_for_authorization(
            authorization_id
        )
        local_orders: list[Order] = []
        if self._order_lifecycle_service is None:
            binding = binding.model_copy(
                update={
                    "status": RuntimeExecutionIntentLocalOrderBindingStatus.BLOCKED,
                    "blockers": _dedupe(
                        list(binding.blockers)
                        + ["order_lifecycle_service_unavailable"]
                    ),
                }
            )
        else:
            for order_id in binding.local_order_ids:
                order = await self._order_lifecycle_service.get_order(order_id)
                if order is not None:
                    local_orders.append(order)
        return build_runtime_execution_exchange_submit_packet_preview(
            binding=binding,
            local_orders=local_orders,
            now_ms=_now_ms(),
        )

    async def exchange_submit_action_authorization_for_authorization(
        self,
        authorization_id: str,
        *,
        trusted_submit_fact_snapshot_id: str | None = None,
        submit_idempotency_policy_id: str | None = None,
        attempt_outcome_policy_id: str | None = None,
        protection_creation_failure_policy_id: str | None = None,
        local_registration_enablement_decision_id: str | None = None,
        owner_real_submit_authorization_id: str | None = None,
        order_lifecycle_submit_enablement_id: str | None = None,
        exchange_submit_adapter_enablement_id: str | None = None,
        owner_confirmed_for_exchange_submit_action: bool = False,
        owner_operator_id: str = "owner",
        reason: str = "owner confirmed scoped exchange submit action",
        deployment_readiness_evidence_id: str | None = None,
        owner_confirmation_reference: str | None = None,
        expires_at_ms: int | None = None,
    ) -> RuntimeExecutionExchangeSubmitActionAuthorization:
        packet_preview = await self.exchange_submit_packet_preview_for_authorization(
            authorization_id
        )
        return build_runtime_execution_exchange_submit_action_authorization(
            packet_preview=packet_preview,
            trusted_submit_fact_snapshot_id=trusted_submit_fact_snapshot_id,
            submit_idempotency_policy_id=submit_idempotency_policy_id,
            attempt_outcome_policy_id=attempt_outcome_policy_id,
            protection_creation_failure_policy_id=(
                protection_creation_failure_policy_id
            ),
            local_registration_enablement_decision_id=(
                local_registration_enablement_decision_id
            ),
            owner_real_submit_authorization_id=owner_real_submit_authorization_id,
            order_lifecycle_submit_enablement_id=(
                order_lifecycle_submit_enablement_id
            ),
            exchange_submit_adapter_enablement_id=(
                exchange_submit_adapter_enablement_id
            ),
            owner_confirmed_for_exchange_submit_action=(
                owner_confirmed_for_exchange_submit_action
            ),
            owner_operator_id=owner_operator_id,
            reason=reason,
            deployment_readiness_evidence_id=deployment_readiness_evidence_id,
            owner_confirmation_reference=owner_confirmation_reference,
            expires_at_ms=expires_at_ms,
            now_ms=_now_ms(),
        )

    async def record_exchange_submit_action_authorization_for_authorization(
        self,
        authorization_id: str,
        *,
        trusted_submit_fact_snapshot_id: str | None = None,
        submit_idempotency_policy_id: str | None = None,
        attempt_outcome_policy_id: str | None = None,
        protection_creation_failure_policy_id: str | None = None,
        local_registration_enablement_decision_id: str | None = None,
        owner_real_submit_authorization_id: str | None = None,
        order_lifecycle_submit_enablement_id: str | None = None,
        exchange_submit_adapter_enablement_id: str | None = None,
        owner_confirmed_for_exchange_submit_action: bool = False,
        owner_operator_id: str = "owner",
        reason: str = "owner confirmed scoped exchange submit action",
        deployment_readiness_evidence_id: str | None = None,
        owner_confirmation_reference: str | None = None,
        expires_at_ms: int | None = None,
    ) -> RuntimeExecutionExchangeSubmitActionAuthorization:
        if self._exchange_submit_action_authorization_repository is None:
            raise RuntimeError(
                "runtime_execution_exchange_submit_action_authorization_"
                "repository_unavailable"
            )
        authorization = (
            await self.exchange_submit_action_authorization_for_authorization(
                authorization_id,
                trusted_submit_fact_snapshot_id=trusted_submit_fact_snapshot_id,
                submit_idempotency_policy_id=submit_idempotency_policy_id,
                attempt_outcome_policy_id=attempt_outcome_policy_id,
                protection_creation_failure_policy_id=(
                    protection_creation_failure_policy_id
                ),
                local_registration_enablement_decision_id=(
                    local_registration_enablement_decision_id
                ),
                owner_real_submit_authorization_id=(
                    owner_real_submit_authorization_id
                ),
                order_lifecycle_submit_enablement_id=(
                    order_lifecycle_submit_enablement_id
                ),
                exchange_submit_adapter_enablement_id=(
                    exchange_submit_adapter_enablement_id
                ),
                owner_confirmed_for_exchange_submit_action=(
                    owner_confirmed_for_exchange_submit_action
                ),
                owner_operator_id=owner_operator_id,
                reason=reason,
                deployment_readiness_evidence_id=deployment_readiness_evidence_id,
                owner_confirmation_reference=owner_confirmation_reference,
                expires_at_ms=expires_at_ms,
            )
        )
        return await self._exchange_submit_action_authorization_repository.create(
            authorization
        )

    async def exchange_submit_enablement_decision_for_authorization(
        self,
        authorization_id: str,
        *,
        trusted_submit_fact_snapshot_id: str | None = None,
        submit_idempotency_policy_id: str | None = None,
        attempt_outcome_policy_id: str | None = None,
        protection_creation_failure_policy_id: str | None = None,
        local_registration_enablement_decision_id: str | None = None,
        owner_real_submit_authorization_id: str | None = None,
        order_lifecycle_submit_enablement_id: str | None = None,
        exchange_submit_adapter_enablement_id: str | None = None,
        exchange_submit_action_authorization_id: str | None = None,
        deployment_readiness_evidence_id: str | None = None,
    ) -> RuntimeExecutionExchangeSubmitEnablementDecision:
        packet_preview = await self.exchange_submit_packet_preview_for_authorization(
            authorization_id
        )
        evidence_blockers, evidence_warnings = (
            await self._validate_first_real_submit_prerequisite_evidence(
                authorization_id=authorization_id,
                execution_intent_id=packet_preview.execution_intent_id,
                runtime_instance_id=packet_preview.runtime_instance_id,
                symbol=packet_preview.symbol,
                trusted_submit_fact_snapshot_id=trusted_submit_fact_snapshot_id,
                submit_idempotency_policy_id=submit_idempotency_policy_id,
                attempt_outcome_policy_id=attempt_outcome_policy_id,
                protection_creation_failure_policy_id=(
                    protection_creation_failure_policy_id
                ),
                local_registration_enablement_decision_id=(
                    local_registration_enablement_decision_id
                ),
                owner_real_submit_authorization_id=owner_real_submit_authorization_id,
                order_lifecycle_submit_enablement_id=(
                    order_lifecycle_submit_enablement_id
                ),
                exchange_submit_adapter_enablement_id=(
                    exchange_submit_adapter_enablement_id
                ),
                exchange_submit_action_authorization_id=(
                    exchange_submit_action_authorization_id
                ),
                deployment_readiness_evidence_id=deployment_readiness_evidence_id,
            )
        )
        return build_runtime_execution_exchange_submit_enablement_decision(
            packet_preview=packet_preview,
            trusted_submit_fact_snapshot_id=trusted_submit_fact_snapshot_id,
            submit_idempotency_policy_id=submit_idempotency_policy_id,
            attempt_outcome_policy_id=attempt_outcome_policy_id,
            protection_creation_failure_policy_id=(
                protection_creation_failure_policy_id
            ),
            local_registration_enablement_decision_id=(
                local_registration_enablement_decision_id
            ),
            owner_real_submit_authorization_id=owner_real_submit_authorization_id,
            order_lifecycle_submit_enablement_id=(
                order_lifecycle_submit_enablement_id
            ),
            exchange_submit_adapter_enablement_id=(
                exchange_submit_adapter_enablement_id
            ),
            exchange_submit_action_authorization_id=(
                exchange_submit_action_authorization_id
            ),
            deployment_readiness_evidence_id=deployment_readiness_evidence_id,
            evidence_validation_blockers=evidence_blockers,
            evidence_validation_warnings=evidence_warnings,
            now_ms=_now_ms(),
        )

    async def exchange_submit_adapter_result_for_authorization(
        self,
        authorization_id: str,
        *,
        exchange_submit_adapter_enabled: bool = False,
        exchange_submit_enablement_decision: (
            RuntimeExecutionExchangeSubmitEnablementDecision | None
        ) = None,
    ) -> RuntimeExecutionExchangeSubmitAdapterResult:
        decision = (
            exchange_submit_enablement_decision
            if exchange_submit_enablement_decision is not None
            else await self.exchange_submit_enablement_decision_for_authorization(
                authorization_id
            )
        )
        gate_blockers: list[str] = []
        gate_warnings: list[str] = []
        if decision.authorization_id != authorization_id:
            gate_blockers.append(
                "exchange_submit_enablement_decision_authorization_mismatch"
            )
        if (
            exchange_submit_adapter_enabled
            and decision.status
            != RuntimeExecutionExchangeSubmitGateStatus.READY_FOR_EXCHANGE_SUBMIT_ACTION
        ):
            gate_blockers.append("exchange_submit_enablement_decision_not_ready")
            gate_blockers.extend(decision.blockers)
        gate_warnings.extend(decision.warnings)

        should_lock = (
            exchange_submit_adapter_enabled
            and not gate_blockers
            and decision.status
            == RuntimeExecutionExchangeSubmitGateStatus.READY_FOR_EXCHANGE_SUBMIT_ACTION
        )
        if should_lock and self._exchange_submit_adapter_result_repository is None:
            raise RuntimeError(
                "runtime_execution_exchange_submit_adapter_result_repository_unavailable"
            )

        duplicate_submit_lock_acquired = False
        if should_lock:
            lock_result = build_runtime_execution_exchange_submit_adapter_lock_result(
                enablement_decision=decision,
                now_ms=_now_ms(),
            )
            acquired, existing = (
                await self._exchange_submit_adapter_result_repository
                .acquire_exchange_submit_lock(lock_result)
            )
            if not acquired:
                if (
                    existing.status
                    == RuntimeExecutionExchangeSubmitAdapterResultStatus
                    .EXCHANGE_SUBMIT_LOCK_ACQUIRED
                ):
                    recovered = build_runtime_execution_exchange_submit_adapter_result(
                        enablement_decision=decision,
                        exchange_submit_adapter_enabled=True,
                        duplicate_submit_lock_acquired=True,
                        additional_warnings=[
                            "recovered_exchange_submit_lock_acquired_state"
                        ],
                        now_ms=_now_ms(),
                    )
                    return await (
                        self._exchange_submit_adapter_result_repository
                        .complete_exchange_submit_result(recovered)
                    )
                return existing
            duplicate_submit_lock_acquired = True

        result = build_runtime_execution_exchange_submit_adapter_result(
            enablement_decision=decision,
            exchange_submit_adapter_enabled=exchange_submit_adapter_enabled,
            duplicate_submit_lock_acquired=duplicate_submit_lock_acquired,
            additional_blockers=gate_blockers,
            additional_warnings=gate_warnings,
            now_ms=_now_ms(),
        )
        if duplicate_submit_lock_acquired:
            return await (
                self._exchange_submit_adapter_result_repository
                .complete_exchange_submit_result(result)
            )
        return result

    async def submit_prerequisite_evidence_proof_for_authorization(
        self,
        authorization_id: str,
        *,
        exchange_submit_enablement_decision: (
            RuntimeExecutionExchangeSubmitEnablementDecision | None
        ) = None,
        trusted_submit_fact_snapshot_id: str | None = None,
        attempt_outcome_policy_id: str | None = None,
        protection_creation_failure_policy_id: str | None = None,
    ) -> RuntimeExecutionSubmitPrerequisiteEvidenceProof:
        decision = (
            exchange_submit_enablement_decision
            if exchange_submit_enablement_decision is not None
            else await self.exchange_submit_enablement_decision_for_authorization(
                authorization_id,
                trusted_submit_fact_snapshot_id=trusted_submit_fact_snapshot_id,
                attempt_outcome_policy_id=attempt_outcome_policy_id,
                protection_creation_failure_policy_id=(
                    protection_creation_failure_policy_id
                ),
            )
        )
        blockers: list[str] = []
        warnings: list[str] = []
        if decision.authorization_id != authorization_id:
            blockers.append(
                "exchange_submit_enablement_decision_authorization_mismatch"
            )

        trusted_id = (
            trusted_submit_fact_snapshot_id
            or decision.trusted_submit_fact_snapshot_id
        )
        trusted = None
        trusted_repo_available = self._trusted_submit_facts_repository is not None
        if str(trusted_id or "").strip() and trusted_repo_available:
            trusted = await self._trusted_submit_facts_repository.get(str(trusted_id))

        attempt_policy_id = (
            attempt_outcome_policy_id
            or decision.attempt_outcome_policy_id
        )
        attempt_policy = None
        attempt_repo_available = self._attempt_outcome_policy_repository is not None
        if str(attempt_policy_id or "").strip() and attempt_repo_available:
            attempt_policy = await self._attempt_outcome_policy_repository.get(
                str(attempt_policy_id)
            )

        protection_policy_id = (
            protection_creation_failure_policy_id
            or decision.protection_creation_failure_policy_id
        )
        protection_policy = None
        protection_repo_available = (
            self._protection_failure_policy_repository is not None
        )
        if str(protection_policy_id or "").strip() and protection_repo_available:
            protection_policy = await self._protection_failure_policy_repository.get(
                str(protection_policy_id)
            )

        return build_runtime_execution_submit_prerequisite_evidence_proof(
            enablement_decision=decision,
            trusted_submit_facts=trusted,
            attempt_outcome_policy=attempt_policy,
            protection_failure_policy=protection_policy,
            trusted_submit_facts_repository_available=trusted_repo_available,
            attempt_outcome_policy_repository_available=attempt_repo_available,
            protection_failure_policy_repository_available=protection_repo_available,
            additional_blockers=blockers,
            additional_warnings=warnings,
            now_ms=_now_ms(),
        )

    async def duplicate_submit_replay_proof_for_authorization(
        self,
        authorization_id: str,
        *,
        exchange_submit_enablement_decision: (
            RuntimeExecutionExchangeSubmitEnablementDecision | None
        ) = None,
        submit_idempotency_policy_id: str | None = None,
    ) -> RuntimeExecutionDuplicateSubmitReplayProof:
        decision = (
            exchange_submit_enablement_decision
            if exchange_submit_enablement_decision is not None
            else await self.exchange_submit_enablement_decision_for_authorization(
                authorization_id,
                submit_idempotency_policy_id=submit_idempotency_policy_id,
            )
        )
        blockers: list[str] = []
        warnings: list[str] = []
        if decision.authorization_id != authorization_id:
            blockers.append(
                "exchange_submit_enablement_decision_authorization_mismatch"
            )

        policy_id = submit_idempotency_policy_id or decision.submit_idempotency_policy_id
        idempotency = None
        if not str(policy_id or "").strip():
            blockers.append("submit_idempotency_policy_id_missing")
        elif self._submit_idempotency_repository is None:
            blockers.append("submit_idempotency_repository_unavailable")
        else:
            idempotency = await self._submit_idempotency_repository.get(str(policy_id))

        existing_adapter_result = None
        adapter_result_repository_available = (
            self._exchange_submit_adapter_result_repository is not None
        )
        if adapter_result_repository_available:
            existing_adapter_result = await (
                self._exchange_submit_adapter_result_repository
                .get_by_authorization_id(authorization_id)
            )

        existing_execution_result = None
        execution_result_repository_available = (
            self._exchange_submit_execution_result_repository is not None
        )
        if execution_result_repository_available:
            existing_execution_result = await (
                self._exchange_submit_execution_result_repository
                .get_by_authorization_id(authorization_id)
            )

        return build_runtime_execution_duplicate_submit_replay_proof(
            enablement_decision=decision,
            submit_idempotency_snapshot=idempotency,
            existing_adapter_result=existing_adapter_result,
            existing_execution_result=existing_execution_result,
            adapter_result_repository_available=(
                adapter_result_repository_available
            ),
            execution_result_repository_available=(
                execution_result_repository_available
            ),
            additional_blockers=blockers,
            additional_warnings=warnings,
            now_ms=_now_ms(),
        )

    async def exchange_submit_execution_result_for_authorization(
        self,
        authorization_id: str,
        *,
        exchange_submit_execution_enabled: bool = False,
        exchange_submit_enablement_decision: (
            RuntimeExecutionExchangeSubmitEnablementDecision | None
        ) = None,
    ) -> RuntimeExecutionExchangeSubmitExecutionResult:
        decision = (
            exchange_submit_enablement_decision
            if exchange_submit_enablement_decision is not None
            else await self.exchange_submit_enablement_decision_for_authorization(
                authorization_id
            )
        )
        packet_preview = await self.exchange_submit_packet_preview_for_authorization(
            authorization_id
        )
        warnings = list(decision.warnings)
        blockers: list[str] = []
        if decision.authorization_id != authorization_id:
            blockers.append("exchange_submit_enablement_decision_authorization_mismatch")
        if decision.status != (
            RuntimeExecutionExchangeSubmitGateStatus.READY_FOR_EXCHANGE_SUBMIT_ACTION
        ):
            blockers.append("exchange_submit_enablement_decision_not_ready")
            blockers.extend(decision.blockers)
        if packet_preview.authorization_id != authorization_id:
            blockers.append("exchange_submit_packet_authorization_mismatch")
        if packet_preview.execution_intent_id != decision.execution_intent_id:
            blockers.append("exchange_submit_packet_intent_mismatch")
        if not packet_preview.entry_submit_request_preview:
            blockers.append("entry_exchange_submit_request_preview_missing")
        if not packet_preview.protection_submit_request_previews:
            blockers.append("protection_exchange_submit_request_previews_missing")

        if not exchange_submit_execution_enabled:
            return build_runtime_exchange_submit_execution_disabled_result(
                enablement_decision=decision,
                packet_preview=packet_preview,
                now_ms=_now_ms(),
                additional_blockers=blockers,
                additional_warnings=[
                    f"disabled_with_blocker:{blocker}"
                    for blocker in blockers
                ],
            )

        if self._exchange_gateway is None:
            blockers.append("runtime_exchange_gateway_unavailable")
        if self._order_lifecycle_service is None:
            blockers.append("order_lifecycle_service_unavailable")
        if self._exchange_submit_execution_result_repository is None:
            blockers.append(
                "runtime_exchange_submit_execution_result_repository_unavailable"
            )
        if self._execution_recovery_repository is None:
            blockers.append("execution_recovery_repository_unavailable")
        else:
            recovery_blockers, recovery_warnings = (
                await self._validate_no_blocking_recovery_tasks_for_exchange_submit(
                    symbol=packet_preview.symbol,
                    execution_intent_id=decision.execution_intent_id,
                )
            )
            blockers.extend(recovery_blockers)
            warnings.extend(recovery_warnings)
        readiness_blockers, readiness_warnings = (
            await self._validate_runtime_exchange_gateway_readiness_for_execution(
                decision.deployment_readiness_evidence_id
            )
        )
        blockers.extend(readiness_blockers)
        warnings.extend(readiness_warnings)
        if blockers:
            return build_runtime_exchange_submit_execution_blocked_result(
                enablement_decision=decision,
                packet_preview=packet_preview,
                blockers=blockers,
                warnings=warnings,
                now_ms=_now_ms(),
                exchange_submit_execution_enabled=True,
            )

        lock_result = build_runtime_exchange_submit_execution_lock_result(
            enablement_decision=decision,
            packet_preview=packet_preview,
            now_ms=_now_ms(),
        )
        acquired, existing = await (
            self._exchange_submit_execution_result_repository
            .acquire_exchange_submit_execution_lock(lock_result)
        )
        if not acquired:
            return existing

        submitted_orders = []
        exchange_call_count = 0
        requests = [packet_preview.entry_submit_request_preview] + list(
            packet_preview.protection_submit_request_previews
        )
        for request in requests:
            if request is None:
                continue
            exchange_call_count += 1
            placement_result = await self._exchange_gateway.place_order(
                symbol=request.symbol,
                order_type=request.gateway_order_type,
                side=request.gateway_side,
                amount=request.amount,
                price=request.price,
                trigger_price=request.trigger_price,
                reduce_only=request.reduce_only,
                client_order_id=request.local_order_id,
            )
            if not getattr(placement_result, "is_success", False):
                failed_result = build_runtime_exchange_submit_execution_failed_result(
                    enablement_decision=decision,
                    packet_preview=packet_preview,
                    submitted_orders=submitted_orders,
                    failed_local_order_id=request.local_order_id,
                    failed_order_role=request.order_role.value,
                    failed_reason=(
                        getattr(placement_result, "error_message", None)
                        or getattr(placement_result, "error_code", None)
                        or "exchange_submit_failed"
                    ),
                    exchange_call_count=exchange_call_count,
                    warnings=warnings,
                    now_ms=_now_ms(),
                )
                completed_failed_result = await (
                    self._exchange_submit_execution_result_repository
                    .complete_exchange_submit_execution_result(failed_result)
                )
                if completed_failed_result.status == (
                    RuntimeExecutionExchangeSubmitExecutionStatus
                    .PROTECTION_SUBMIT_FAILED
                ):
                    await self._record_exchange_submit_protection_failed_recovery_task(
                        execution_result=completed_failed_result,
                        enablement_decision=decision,
                    )
                return completed_failed_result
            exchange_order_id = getattr(placement_result, "exchange_order_id", None)
            await self._order_lifecycle_service.submit_order(
                request.local_order_id,
                exchange_order_id=exchange_order_id,
            )
            submitted_orders.append(
                submitted_exchange_order_from_placement(
                    local_order_id=request.local_order_id,
                    order_role=request.order_role.value,
                    reduce_only=request.reduce_only,
                    placement_result=placement_result,
                    order_lifecycle_submit_called=True,
                )
            )

        result = build_runtime_exchange_submit_execution_submitted_result(
            enablement_decision=decision,
            packet_preview=packet_preview,
            submitted_orders=submitted_orders,
            exchange_call_count=exchange_call_count,
            warnings=warnings,
            now_ms=_now_ms(),
        )
        return await (
            self._exchange_submit_execution_result_repository
            .complete_exchange_submit_execution_result(result)
        )

    async def submit_outcome_review_for_authorization(
        self,
        authorization_id: str,
        *,
        exchange_submit_execution_result: (
            RuntimeExecutionExchangeSubmitExecutionResult | None
        ) = None,
    ) -> RuntimeExecutionSubmitOutcomeReview:
        result = exchange_submit_execution_result
        if result is None:
            if self._exchange_submit_execution_result_repository is None:
                raise RuntimeError(
                    "runtime_exchange_submit_execution_result_repository_unavailable"
                )
            result = await (
                self._exchange_submit_execution_result_repository
                .get_by_authorization_id(authorization_id)
            )
        if result is None:
            raise ValueError("RuntimeExecutionExchangeSubmitExecutionResult not found")
        if result.authorization_id != authorization_id:
            return build_runtime_execution_submit_outcome_review(
                exchange_submit_execution_result=result,
                local_orders=[],
                now_ms=_now_ms(),
                additional_blockers=[
                    "exchange_submit_execution_result_authorization_mismatch"
                ],
            )

        local_orders: list[Order] = []
        additional_blockers: list[str] = []
        statuses_requiring_order_facts = {
            RuntimeExecutionExchangeSubmitExecutionStatus
            .EXCHANGE_SUBMIT_ORDERS_SUBMITTED,
            RuntimeExecutionExchangeSubmitExecutionStatus.PROTECTION_SUBMIT_FAILED,
        }
        if result.status in statuses_requiring_order_facts:
            if self._order_lifecycle_service is None:
                additional_blockers.append(
                    "order_lifecycle_service_unavailable_for_submit_outcome_review"
                )
            else:
                order_ids = _dedupe(
                    list(result.local_order_ids)
                    + list(result.submitted_local_order_ids)
                    + ([result.entry_order_id] if result.entry_order_id else [])
                    + list(result.protection_order_ids)
                )
                for order_id in order_ids:
                    order = await self._order_lifecycle_service.get_order(order_id)
                    if order is not None:
                        local_orders.append(order)

        return build_runtime_execution_submit_outcome_review(
            exchange_submit_execution_result=result,
            local_orders=local_orders,
            now_ms=_now_ms(),
            additional_blockers=additional_blockers,
        )

    async def record_submit_outcome_review_for_authorization(
        self,
        authorization_id: str,
        *,
        exchange_submit_execution_result: (
            RuntimeExecutionExchangeSubmitExecutionResult | None
        ) = None,
    ) -> RuntimeExecutionSubmitOutcomeReview:
        if self._submit_outcome_review_repository is None:
            raise RuntimeError(
                "runtime_execution_submit_outcome_review_repository_unavailable"
            )
        review = await self.submit_outcome_review_for_authorization(
            authorization_id,
            exchange_submit_execution_result=exchange_submit_execution_result,
        )
        return await self._submit_outcome_review_repository.create(review)

    async def submit_rehearsal_for_authorization(
        self,
        authorization_id: str,
        *,
        exchange_submit_enablement_decision: (
            RuntimeExecutionExchangeSubmitEnablementDecision | None
        ) = None,
        runtime_exchange_gateway_readiness: (
            RuntimeExecutionExchangeGatewayReadiness | None
        ) = None,
    ) -> RuntimeExecutionSubmitRehearsal:
        decision = (
            exchange_submit_enablement_decision
            if exchange_submit_enablement_decision is not None
            else await self.exchange_submit_enablement_decision_for_authorization(
                authorization_id
            )
        )
        packet_preview = await self.exchange_submit_packet_preview_for_authorization(
            authorization_id
        )
        additional_blockers: list[str] = []
        readiness = runtime_exchange_gateway_readiness
        if readiness is None:
            readiness_id = decision.deployment_readiness_evidence_id
            if readiness_id and self._exchange_gateway_readiness_repository is not None:
                readiness = await self._exchange_gateway_readiness_repository.get(
                    readiness_id
                )
            elif readiness_id and self._exchange_gateway_readiness_repository is None:
                additional_blockers.append(
                    "runtime_exchange_gateway_readiness_repository_unavailable"
                )

        if self._execution_recovery_repository is None:
            additional_blockers.append("execution_recovery_repository_unavailable")
            recovery_task_ids: list[str] = []
        else:
            recovery_task_ids = (
                await self._blocking_recovery_task_ids_for_exchange_submit(
                    symbol=packet_preview.symbol,
                    execution_intent_id=decision.execution_intent_id,
                )
            )
            if "execution_recovery_blocking_check_unavailable" in recovery_task_ids:
                additional_blockers.append(
                    "execution_recovery_blocking_check_unavailable"
                )
                recovery_task_ids = [
                    task_id
                    for task_id in recovery_task_ids
                    if task_id != "execution_recovery_blocking_check_unavailable"
                ]

        if decision.authorization_id != authorization_id:
            additional_blockers.append(
                "exchange_submit_enablement_decision_authorization_mismatch"
            )
        if packet_preview.authorization_id != authorization_id:
            additional_blockers.append("exchange_submit_packet_authorization_mismatch")
        if packet_preview.execution_intent_id != decision.execution_intent_id:
            additional_blockers.append("exchange_submit_packet_intent_mismatch")

        return build_runtime_execution_submit_rehearsal(
            exchange_submit_enablement_decision=decision,
            runtime_exchange_gateway_readiness=readiness,
            blocking_recovery_task_ids=recovery_task_ids,
            additional_blockers=additional_blockers,
            now_ms=_now_ms(),
        )

    async def _validate_runtime_exchange_gateway_readiness_for_execution(
        self,
        readiness_id: str | None,
    ) -> tuple[list[str], list[str]]:
        blockers: list[str] = []
        warnings: list[str] = []
        if not str(readiness_id or "").strip():
            return ["runtime_exchange_gateway_readiness_id_missing"], warnings
        if self._exchange_gateway_readiness_repository is None:
            return [
                "runtime_exchange_gateway_readiness_repository_unavailable"
            ], warnings
        readiness = await self._exchange_gateway_readiness_repository.get(
            str(readiness_id)
        )
        if readiness is None:
            return ["runtime_exchange_gateway_readiness_not_found"], warnings
        if readiness.status != (
            RuntimeExecutionExchangeGatewayReadinessStatus
            .READY_FOR_MANUAL_GATEWAY_BINDING
        ):
            blockers.append("runtime_exchange_gateway_readiness_not_ready")
            blockers.extend(
                f"runtime_exchange_gateway_readiness:{blocker}"
                for blocker in readiness.blockers
            )
        if readiness.gateway_injected:
            blockers.append("runtime_exchange_gateway_readiness_mutated_gateway")
        if readiness.exchange_called:
            blockers.append("runtime_exchange_gateway_readiness_called_exchange")
        if readiness.exchange_order_submitted:
            blockers.append(
                "runtime_exchange_gateway_readiness_submitted_exchange_order"
            )
        if readiness.order_lifecycle_submit_called:
            blockers.append("runtime_exchange_gateway_readiness_called_lifecycle")
        if readiness.execution_intent_status_changed:
            blockers.append(
                "runtime_exchange_gateway_readiness_changed_intent_status"
            )
        freshness_blockers, age_ms = runtime_gateway_readiness_freshness_blockers(
            readiness,
            now_ms=_now_ms(),
        )
        blockers.extend(freshness_blockers)
        if age_ms is not None:
            warnings.append(f"runtime_exchange_gateway_readiness_age_ms:{age_ms}")
        warnings.extend(
            f"runtime_exchange_gateway_readiness:{warning}"
            for warning in readiness.warnings
        )
        return _dedupe(blockers), _dedupe(warnings)

    async def _validate_no_blocking_recovery_tasks_for_exchange_submit(
        self,
        *,
        symbol: str | None,
        execution_intent_id: str | None,
    ) -> tuple[list[str], list[str]]:
        if self._execution_recovery_repository is None:
            return [], []

        task_ids = await self._blocking_recovery_task_ids_for_exchange_submit(
            symbol=symbol,
            execution_intent_id=execution_intent_id,
        )
        blockers: list[str] = []
        warnings: list[str] = []
        for task_id in task_ids:
            if task_id == "execution_recovery_blocking_check_unavailable":
                blockers.append("execution_recovery_blocking_check_unavailable")
            else:
                blockers.append("execution_recovery_blocking_task_open")
                warnings.append(f"execution_recovery_blocking_task:{task_id}")

        return _dedupe(blockers), _dedupe(warnings)

    async def _blocking_recovery_task_ids_for_exchange_submit(
        self,
        *,
        symbol: str | None,
        execution_intent_id: str | None,
    ) -> list[str]:
        if self._execution_recovery_repository is None:
            return []

        list_blocking = getattr(
            self._execution_recovery_repository,
            "list_blocking",
            None,
        )
        list_active = getattr(
            self._execution_recovery_repository,
            "list_active",
            None,
        )
        if callable(list_blocking):
            tasks = await list_blocking()
        elif callable(list_active):
            tasks = await list_active()
        else:
            return ["execution_recovery_blocking_check_unavailable"]

        task_ids: list[str] = []
        for task in tasks:
            context_payload = task.get("context_payload") or {}
            blocks_new_entries = (
                context_payload.get("block_new_entries_until_resolved") is True
                or task.get("recovery_type")
                == _EXCHANGE_SUBMIT_PROTECTION_FAILED_RECOVERY_TYPE
            )
            if not blocks_new_entries:
                continue
            same_symbol = bool(symbol and task.get("symbol") == symbol)
            same_intent = bool(
                execution_intent_id
                and task.get("intent_id") == execution_intent_id
            )
            if not same_symbol and not same_intent:
                continue
            task_id = task.get("id") or "unknown"
            task_ids.append(str(task_id))

        return _dedupe(task_ids)

    async def record_exchange_submit_recovery_resolution(
        self,
        recovery_task_id: str,
        *,
        owner_operator_id: str,
        reason: str,
        owner_confirmed_recovery_resolved: bool = False,
        owner_confirmed_reconciliation_reviewed: bool = False,
        owner_confirmed_no_unprotected_position: bool = False,
        owner_confirmed_no_unresolved_exchange_order: bool = False,
        owner_confirmed_budget_reconciled_or_held: bool = False,
        owner_confirmed_attempt_consumed_or_accounted: bool = False,
        owner_confirmation_reference: str | None = None,
        reconciliation_evidence_id: str | None = None,
    ) -> RuntimeExecutionExchangeSubmitRecoveryResolution:
        if self._execution_recovery_repository is None:
            raise RuntimeError("execution_recovery_repository_unavailable")
        if self._exchange_submit_recovery_resolution_repository is None:
            raise RuntimeError(
                "runtime_exchange_submit_recovery_resolution_repository_unavailable"
            )

        existing_resolution = await (
            self._exchange_submit_recovery_resolution_repository
            .get_by_recovery_task_id(recovery_task_id)
        )
        if (
            existing_resolution is not None
            and existing_resolution.status
            == RuntimeExecutionExchangeSubmitRecoveryResolutionStatus.RESOLVED
        ):
            return existing_resolution

        recovery_task = await self._execution_recovery_repository.get(
            recovery_task_id
        )
        if recovery_task is None:
            raise ValueError("Execution recovery task not found")

        resolution = build_runtime_execution_exchange_submit_recovery_resolution(
            recovery_task=recovery_task,
            owner_operator_id=owner_operator_id,
            reason=reason,
            owner_confirmed_recovery_resolved=(
                owner_confirmed_recovery_resolved
            ),
            owner_confirmed_reconciliation_reviewed=(
                owner_confirmed_reconciliation_reviewed
            ),
            owner_confirmed_no_unprotected_position=(
                owner_confirmed_no_unprotected_position
            ),
            owner_confirmed_no_unresolved_exchange_order=(
                owner_confirmed_no_unresolved_exchange_order
            ),
            owner_confirmed_budget_reconciled_or_held=(
                owner_confirmed_budget_reconciled_or_held
            ),
            owner_confirmed_attempt_consumed_or_accounted=(
                owner_confirmed_attempt_consumed_or_accounted
            ),
            owner_confirmation_reference=owner_confirmation_reference,
            reconciliation_evidence_id=reconciliation_evidence_id,
            recovery_task_marked_resolved=True,
            now_ms=_now_ms(),
        )
        if resolution.status == (
            RuntimeExecutionExchangeSubmitRecoveryResolutionStatus.BLOCKED
        ):
            return await (
                self._exchange_submit_recovery_resolution_repository
                .create(resolution)
            )

        resolved_at = _now_ms()
        await self._execution_recovery_repository.mark_resolved(
            recovery_task_id,
            resolved_at=resolved_at,
            error_message=(
                "owner recovery resolution recorded: "
                f"{resolution.resolution_id}"
            ),
        )
        resolved = build_runtime_execution_exchange_submit_recovery_resolution(
            recovery_task=recovery_task,
            owner_operator_id=owner_operator_id,
            reason=reason,
            owner_confirmed_recovery_resolved=(
                owner_confirmed_recovery_resolved
            ),
            owner_confirmed_reconciliation_reviewed=(
                owner_confirmed_reconciliation_reviewed
            ),
            owner_confirmed_no_unprotected_position=(
                owner_confirmed_no_unprotected_position
            ),
            owner_confirmed_no_unresolved_exchange_order=(
                owner_confirmed_no_unresolved_exchange_order
            ),
            owner_confirmed_budget_reconciled_or_held=(
                owner_confirmed_budget_reconciled_or_held
            ),
            owner_confirmed_attempt_consumed_or_accounted=(
                owner_confirmed_attempt_consumed_or_accounted
            ),
            owner_confirmation_reference=owner_confirmation_reference,
            reconciliation_evidence_id=reconciliation_evidence_id,
            recovery_task_marked_resolved=True,
            now_ms=resolved_at,
        )
        return await (
            self._exchange_submit_recovery_resolution_repository
            .create(resolved)
        )

    async def _record_exchange_submit_protection_failed_recovery_task(
        self,
        *,
        execution_result: RuntimeExecutionExchangeSubmitExecutionResult,
        enablement_decision: RuntimeExecutionExchangeSubmitEnablementDecision,
    ) -> None:
        if self._execution_recovery_repository is None:
            raise RuntimeError("execution_recovery_repository_unavailable")
        task_id = _exchange_submit_recovery_task_id(
            execution_result.authorization_id
        )
        existing = await self._execution_recovery_repository.get(task_id)
        if existing is not None:
            return
        context_payload = {
            "scope": "runtime_exchange_submit_protection_failed_recovery",
            "execution_result_id": execution_result.execution_result_id,
            "authorization_id": execution_result.authorization_id,
            "runtime_instance_id": execution_result.runtime_instance_id,
            "source_type": execution_result.source_type,
            "source_id": execution_result.source_id,
            "exchange_submit_action_authorization_id": (
                execution_result.exchange_submit_action_authorization_id
            ),
            "protection_failure_policy_id": (
                enablement_decision.protection_creation_failure_policy_id
            ),
            "attempt_outcome_policy_id": (
                enablement_decision.attempt_outcome_policy_id
            ),
            "entry_order_id": execution_result.entry_order_id,
            "entry_exchange_order_id": execution_result.entry_exchange_order_id,
            "failed_protection_order_id": execution_result.failed_local_order_id,
            "failed_order_role": execution_result.failed_order_role,
            "failed_reason": execution_result.failed_reason,
            "block_new_entries_until_resolved": True,
            "require_owner_recovery_review": True,
            "require_reduce_only_recovery_mode": True,
            "require_reconciliation_before_retry": True,
            "consume_attempt_on_any_fill": True,
            "hold_or_reconcile_budget_until_position_resolved": True,
            "does_not_create_recovery_order": True,
            "does_not_call_exchange": True,
            "does_not_call_order_lifecycle": True,
        }
        await self._execution_recovery_repository.create_task(
            task_id=task_id,
            intent_id=execution_result.execution_intent_id,
            symbol=execution_result.symbol,
            recovery_type=_EXCHANGE_SUBMIT_PROTECTION_FAILED_RECOVERY_TYPE,
            related_order_id=execution_result.failed_local_order_id,
            related_exchange_order_id=execution_result.entry_exchange_order_id,
            error_message=execution_result.failed_reason,
            context_payload=context_payload,
        )

    async def _validate_first_real_submit_prerequisite_evidence(
        self,
        *,
        authorization_id: str,
        execution_intent_id: str,
        runtime_instance_id: str | None,
        trusted_submit_fact_snapshot_id: str | None,
        submit_idempotency_policy_id: str | None,
        attempt_outcome_policy_id: str | None,
        protection_creation_failure_policy_id: str | None,
        symbol: str | None = None,
        local_registration_enablement_decision_id: str | None = None,
        owner_real_submit_authorization_id: str | None = None,
        order_lifecycle_adapter_enablement_id: str | None = None,
        local_order_registration_enablement_id: str | None = None,
        order_lifecycle_submit_enablement_id: str | None = None,
        exchange_submit_adapter_enablement_id: str | None = None,
        local_registration_action_authorization_id: str | None = None,
        exchange_submit_action_authorization_id: str | None = None,
        deployment_readiness_evidence_id: str | None = None,
    ) -> tuple[list[str], list[str]]:
        blockers: list[str] = []
        warnings: list[str] = []

        if trusted_submit_fact_snapshot_id:
            if self._trusted_submit_facts_repository is None:
                blockers.append("trusted_submit_fact_snapshot_repository_unavailable")
            else:
                trusted = await self._trusted_submit_facts_repository.get(
                    trusted_submit_fact_snapshot_id
                )
                if trusted is None:
                    blockers.append("trusted_submit_fact_snapshot_not_found")
                else:
                    if trusted.status != (
                        RuntimeExecutionTrustedSubmitFactsStatus
                        .READY_FOR_FIRST_REAL_SUBMIT_CONFIRMATION
                    ):
                        blockers.append("trusted_submit_fact_snapshot_not_ready")
                    if trusted.execution_intent_id != execution_intent_id:
                        blockers.append("trusted_submit_fact_snapshot_intent_mismatch")
                    if (
                        runtime_instance_id
                        and trusted.runtime_instance_id
                        and trusted.runtime_instance_id != runtime_instance_id
                    ):
                        blockers.append(
                            "trusted_submit_fact_snapshot_runtime_mismatch"
                        )
                    if symbol and getattr(trusted, "symbol", None) != symbol:
                        blockers.append("trusted_submit_fact_snapshot_symbol_mismatch")
                    if not getattr(trusted, "facts_fresh_enough", False):
                        blockers.append(
                            "trusted_submit_fact_snapshot_not_fresh_enough"
                        )
                    if not getattr(trusted, "read_only_sources_only", False):
                        blockers.append(
                            "trusted_submit_fact_snapshot_sources_not_read_only"
                        )
                    if not getattr(trusted, "owner_supplied_allow_facts_rejected", False):
                        blockers.append(
                            "trusted_submit_fact_snapshot_owner_allow_not_rejected"
                        )
                    if not getattr(trusted, "missing_or_stale_facts_block", False):
                        blockers.append(
                            "trusted_submit_fact_snapshot_missing_stale_not_blocking"
                        )
                    if not getattr(trusted, "not_execution_authority", False):
                        blockers.append(
                            "trusted_submit_fact_snapshot_execution_authority"
                        )
                    if getattr(trusted, "order_created", True):
                        blockers.append("trusted_submit_fact_snapshot_created_order")
                    if getattr(trusted, "exchange_called", True):
                        blockers.append("trusted_submit_fact_snapshot_called_exchange")
                    if getattr(trusted, "order_lifecycle_called", True):
                        blockers.append(
                            "trusted_submit_fact_snapshot_called_order_lifecycle"
                        )
                    warnings.extend(
                        f"trusted_submit_fact_snapshot:{warning}"
                        for warning in trusted.warnings
                    )

        if submit_idempotency_policy_id:
            if self._submit_idempotency_repository is None:
                blockers.append("submit_idempotency_repository_unavailable")
            else:
                idempotency = await self._submit_idempotency_repository.get(
                    submit_idempotency_policy_id
                )
                if idempotency is None:
                    blockers.append("submit_idempotency_policy_not_found")
                else:
                    if idempotency.status != (
                        RuntimeExecutionSubmitIdempotencyStatus
                        .READY_FOR_NON_EXECUTING_POLICY_CONFIRMATION
                    ):
                        blockers.append("submit_idempotency_policy_not_ready")
                    if idempotency.authorization_id != authorization_id:
                        blockers.append("submit_idempotency_authorization_mismatch")
                    if idempotency.execution_intent_id != execution_intent_id:
                        blockers.append("submit_idempotency_intent_mismatch")
                    if (
                        runtime_instance_id
                        and idempotency.runtime_instance_id
                        and idempotency.runtime_instance_id != runtime_instance_id
                    ):
                        blockers.append("submit_idempotency_runtime_mismatch")
                    if idempotency.replay_lock_key != authorization_id:
                        blockers.append("submit_idempotency_replay_key_mismatch")
                    warnings.extend(
                        f"submit_idempotency:{warning}"
                        for warning in idempotency.warnings
                    )

        if attempt_outcome_policy_id:
            if self._attempt_outcome_policy_repository is None:
                blockers.append("attempt_outcome_policy_repository_unavailable")
            else:
                outcome = await self._attempt_outcome_policy_repository.get(
                    attempt_outcome_policy_id
                )
                if outcome is None:
                    blockers.append("attempt_outcome_policy_not_found")
                else:
                    if outcome.status != (
                        RuntimeExecutionAttemptOutcomePolicyStatus
                        .READY_FOR_ATTEMPT_BUDGET_OUTCOME_ACCOUNTING
                    ):
                        blockers.append("attempt_outcome_policy_not_ready")
                    if getattr(outcome, "outcome_kind", None) != (
                        RuntimeExecutionAttemptOutcomeKind
                        .ENTRY_FILLED_PROTECTION_CREATION_FAILED
                    ):
                        blockers.append("attempt_outcome_policy_kind_mismatch")
                    if outcome.authorization_id != authorization_id:
                        blockers.append("attempt_outcome_policy_authorization_mismatch")
                    if outcome.execution_intent_id != execution_intent_id:
                        blockers.append("attempt_outcome_policy_intent_mismatch")
                    if (
                        runtime_instance_id
                        and outcome.runtime_instance_id
                        and outcome.runtime_instance_id != runtime_instance_id
                    ):
                        blockers.append("attempt_outcome_policy_runtime_mismatch")
                    outcome_symbol = getattr(outcome, "symbol", None)
                    if symbol and outcome_symbol and outcome_symbol != symbol:
                        blockers.append("attempt_outcome_policy_symbol_mismatch")
                    if not getattr(outcome, "protection_creation_failed", False):
                        blockers.append(
                            "attempt_outcome_policy_protection_failure_missing"
                        )
                    if not getattr(outcome, "attempt_should_be_consumed", False):
                        blockers.append(
                            "attempt_outcome_policy_attempt_consumption_missing"
                        )
                    if not getattr(outcome, "reserved_budget_should_remain_held", False):
                        blockers.append("attempt_outcome_policy_budget_hold_missing")
                    if not getattr(outcome, "blocks_new_entries_until_resolved", False):
                        blockers.append(
                            "attempt_outcome_policy_blocks_entries_missing"
                        )
                    if not getattr(outcome, "requires_owner_recovery_review", False):
                        blockers.append(
                            "attempt_outcome_policy_owner_recovery_review_missing"
                        )
                    if not getattr(outcome, "requires_reduce_only_recovery_mode", False):
                        blockers.append(
                            "attempt_outcome_policy_reduce_only_recovery_missing"
                        )
                    if not getattr(outcome, "requires_reconciliation_before_retry", False):
                        blockers.append(
                            "attempt_outcome_policy_reconciliation_missing"
                        )
                    warnings.extend(
                        f"attempt_outcome_policy:{warning}"
                        for warning in outcome.warnings
                    )

        if protection_creation_failure_policy_id:
            if self._protection_failure_policy_repository is None:
                blockers.append(
                    "protection_failure_policy_repository_unavailable"
                )
            else:
                policy = await self._protection_failure_policy_repository.get(
                    protection_creation_failure_policy_id
                )
                if policy is None:
                    blockers.append("protection_failure_policy_not_found")
                else:
                    if policy.status != (
                        RuntimeExecutionProtectionFailurePolicyStatus
                        .READY_FOR_FIRST_REAL_SUBMIT_CONFIRMATION
                    ):
                        blockers.append("protection_failure_policy_not_ready")
                    if policy.execution_intent_id != execution_intent_id:
                        blockers.append("protection_failure_policy_intent_mismatch")
                    if (
                        runtime_instance_id
                        and policy.runtime_instance_id
                        and policy.runtime_instance_id != runtime_instance_id
                    ):
                        blockers.append("protection_failure_policy_runtime_mismatch")
                    policy_symbol = getattr(policy, "symbol", None)
                    if symbol and policy_symbol and policy_symbol != symbol:
                        blockers.append("protection_failure_policy_symbol_mismatch")
                    if not getattr(policy, "block_new_entries_until_resolved", False):
                        blockers.append(
                            "protection_failure_policy_blocks_entries_missing"
                        )
                    if not getattr(
                        policy,
                        "mark_position_unprotected_until_verified",
                        False,
                    ):
                        blockers.append(
                            "protection_failure_policy_unprotected_mark_missing"
                        )
                    if not getattr(policy, "require_owner_recovery_review", False):
                        blockers.append(
                            "protection_failure_policy_owner_review_missing"
                        )
                    if not getattr(policy, "require_reduce_only_recovery_mode", False):
                        blockers.append(
                            "protection_failure_policy_reduce_only_missing"
                        )
                    if not getattr(policy, "require_reconciliation_before_retry", False):
                        blockers.append(
                            "protection_failure_policy_reconciliation_missing"
                        )
                    if not getattr(policy, "consume_attempt_on_any_fill", False):
                        blockers.append(
                            "protection_failure_policy_attempt_consumption_missing"
                        )
                    if not getattr(
                        policy,
                        "hold_or_reconcile_budget_until_position_resolved",
                        False,
                    ):
                        blockers.append("protection_failure_policy_budget_hold_missing")
                    warnings.extend(
                        f"protection_failure_policy:{warning}"
                        for warning in policy.warnings
                    )

        if local_registration_action_authorization_id:
            repository = self._local_registration_action_authorization_repository
            if repository is None:
                blockers.append(
                    "local_registration_action_authorization_repository_unavailable"
                )
            else:
                action_authorization = await repository.get(
                    local_registration_action_authorization_id
                )
                if action_authorization is None:
                    blockers.append("local_registration_action_authorization_not_found")
                else:
                    if action_authorization.status != (
                        RuntimeExecutionLocalRegistrationActionAuthorizationStatus
                        .APPROVED_FOR_LOCAL_REGISTRATION_ACTION
                    ):
                        blockers.append(
                            "local_registration_action_authorization_not_approved"
                        )
                    if action_authorization.authorization_id != authorization_id:
                        blockers.append(
                            "local_registration_action_authorization_authorization_"
                            "mismatch"
                        )
                    if action_authorization.execution_intent_id != execution_intent_id:
                        blockers.append(
                            "local_registration_action_authorization_intent_"
                            "mismatch"
                        )
                    if (
                        runtime_instance_id
                        and action_authorization.runtime_instance_id
                        and action_authorization.runtime_instance_id
                        != runtime_instance_id
                    ):
                        blockers.append(
                            "local_registration_action_authorization_runtime_"
                            "mismatch"
                        )
                    if symbol and action_authorization.symbol != symbol:
                        blockers.append(
                            "local_registration_action_authorization_symbol_mismatch"
                        )
                    if (
                        trusted_submit_fact_snapshot_id
                        and action_authorization.trusted_submit_fact_snapshot_id
                        != trusted_submit_fact_snapshot_id
                    ):
                        blockers.append(
                            "local_registration_action_authorization_trusted_facts_"
                            "mismatch"
                        )
                    if (
                        submit_idempotency_policy_id
                        and action_authorization.submit_idempotency_policy_id
                        != submit_idempotency_policy_id
                    ):
                        blockers.append(
                            "local_registration_action_authorization_idempotency_"
                            "mismatch"
                        )
                    if (
                        attempt_outcome_policy_id
                        and action_authorization.attempt_outcome_policy_id
                        != attempt_outcome_policy_id
                    ):
                        blockers.append(
                            "local_registration_action_authorization_attempt_"
                            "outcome_mismatch"
                        )
                    if (
                        protection_creation_failure_policy_id
                        and action_authorization.protection_creation_failure_policy_id
                        != protection_creation_failure_policy_id
                    ):
                        blockers.append(
                            "local_registration_action_authorization_protection_"
                            "failure_mismatch"
                        )
                    if (
                        owner_real_submit_authorization_id
                        and action_authorization.owner_real_submit_authorization_id
                        != owner_real_submit_authorization_id
                    ):
                        blockers.append(
                            "local_registration_action_authorization_owner_submit_"
                            "mismatch"
                        )
                    if (
                        order_lifecycle_adapter_enablement_id
                        and action_authorization.order_lifecycle_adapter_enablement_id
                        != order_lifecycle_adapter_enablement_id
                    ):
                        blockers.append(
                            "local_registration_action_authorization_lifecycle_"
                            "adapter_mismatch"
                        )
                    if (
                        local_order_registration_enablement_id
                        and action_authorization.local_order_registration_enablement_id
                        != local_order_registration_enablement_id
                    ):
                        blockers.append(
                            "local_registration_action_authorization_local_"
                            "registration_enablement_mismatch"
                        )
                    action_deployment_readiness_evidence_id = getattr(
                        action_authorization,
                        "deployment_readiness_evidence_id",
                        None,
                    )
                    if (
                        deployment_readiness_evidence_id
                        and action_deployment_readiness_evidence_id
                        and action_deployment_readiness_evidence_id
                        != deployment_readiness_evidence_id
                    ):
                        blockers.append(
                            "local_registration_action_authorization_deployment_"
                            "readiness_mismatch"
                        )
                    if not action_authorization.owner_confirmed_for_local_registration_action:
                        blockers.append(
                            "local_registration_action_authorization_owner_"
                            "confirmation_missing"
                        )
                    expires_at_ms = getattr(
                        action_authorization,
                        "expires_at_ms",
                        None,
                    )
                    if expires_at_ms is not None and expires_at_ms <= _now_ms():
                        blockers.append(
                            "local_registration_action_authorization_expired"
                        )
                    if getattr(action_authorization, "order_created", False):
                        blockers.append(
                            "local_registration_action_authorization_created_order"
                        )
                    if getattr(action_authorization, "order_lifecycle_called", False):
                        blockers.append(
                            "local_registration_action_authorization_called_"
                            "lifecycle"
                        )
                    if getattr(action_authorization, "exchange_called", False):
                        blockers.append(
                            "local_registration_action_authorization_called_exchange"
                        )
                    warnings.extend(
                        f"local_registration_action_authorization:{warning}"
                        for warning in action_authorization.warnings
                    )

        if exchange_submit_action_authorization_id:
            repository = self._exchange_submit_action_authorization_repository
            if repository is None:
                blockers.append(
                    "exchange_submit_action_authorization_repository_unavailable"
                )
            else:
                action_authorization = await repository.get(
                    exchange_submit_action_authorization_id
                )
                if action_authorization is None:
                    blockers.append("exchange_submit_action_authorization_not_found")
                else:
                    if action_authorization.status != (
                        RuntimeExecutionExchangeSubmitActionAuthorizationStatus
                        .APPROVED_FOR_EXCHANGE_SUBMIT_ACTION
                    ):
                        blockers.append(
                            "exchange_submit_action_authorization_not_approved"
                        )
                    if action_authorization.authorization_id != authorization_id:
                        blockers.append(
                            "exchange_submit_action_authorization_authorization_"
                            "mismatch"
                        )
                    if action_authorization.execution_intent_id != execution_intent_id:
                        blockers.append(
                            "exchange_submit_action_authorization_intent_mismatch"
                        )
                    if (
                        runtime_instance_id
                        and action_authorization.runtime_instance_id
                        and action_authorization.runtime_instance_id
                        != runtime_instance_id
                    ):
                        blockers.append(
                            "exchange_submit_action_authorization_runtime_mismatch"
                        )
                    if symbol and action_authorization.symbol != symbol:
                        blockers.append(
                            "exchange_submit_action_authorization_symbol_mismatch"
                        )
                    if (
                        local_registration_enablement_decision_id
                        and action_authorization.local_registration_enablement_decision_id
                        != local_registration_enablement_decision_id
                    ):
                        blockers.append(
                            "exchange_submit_action_authorization_local_registration_"
                            "mismatch"
                        )
                    if (
                        trusted_submit_fact_snapshot_id
                        and action_authorization.trusted_submit_fact_snapshot_id
                        != trusted_submit_fact_snapshot_id
                    ):
                        blockers.append(
                            "exchange_submit_action_authorization_trusted_facts_"
                            "mismatch"
                        )
                    if (
                        submit_idempotency_policy_id
                        and action_authorization.submit_idempotency_policy_id
                        != submit_idempotency_policy_id
                    ):
                        blockers.append(
                            "exchange_submit_action_authorization_idempotency_"
                            "mismatch"
                        )
                    if (
                        attempt_outcome_policy_id
                        and action_authorization.attempt_outcome_policy_id
                        != attempt_outcome_policy_id
                    ):
                        blockers.append(
                            "exchange_submit_action_authorization_attempt_outcome_"
                            "mismatch"
                        )
                    if (
                        protection_creation_failure_policy_id
                        and action_authorization.protection_creation_failure_policy_id
                        != protection_creation_failure_policy_id
                    ):
                        blockers.append(
                            "exchange_submit_action_authorization_protection_failure_"
                            "mismatch"
                        )
                    if (
                        owner_real_submit_authorization_id
                        and action_authorization.owner_real_submit_authorization_id
                        != owner_real_submit_authorization_id
                    ):
                        blockers.append(
                            "exchange_submit_action_authorization_owner_submit_"
                            "mismatch"
                        )
                    if (
                        order_lifecycle_submit_enablement_id
                        and action_authorization.order_lifecycle_submit_enablement_id
                        != order_lifecycle_submit_enablement_id
                    ):
                        blockers.append(
                            "exchange_submit_action_authorization_lifecycle_submit_"
                            "mismatch"
                        )
                    if (
                        exchange_submit_adapter_enablement_id
                        and action_authorization.exchange_submit_adapter_enablement_id
                        != exchange_submit_adapter_enablement_id
                    ):
                        blockers.append(
                            "exchange_submit_action_authorization_adapter_enablement_"
                            "mismatch"
                        )
                    action_deployment_readiness_evidence_id = getattr(
                        action_authorization,
                        "deployment_readiness_evidence_id",
                        None,
                    )
                    if (
                        deployment_readiness_evidence_id
                        and action_deployment_readiness_evidence_id
                        and action_deployment_readiness_evidence_id
                        != deployment_readiness_evidence_id
                    ):
                        blockers.append(
                            "exchange_submit_action_authorization_deployment_"
                            "readiness_mismatch"
                        )
                    if not action_authorization.owner_confirmed_for_exchange_submit_action:
                        blockers.append(
                            "exchange_submit_action_authorization_owner_confirmation_"
                            "missing"
                        )
                    expires_at_ms = getattr(
                        action_authorization,
                        "expires_at_ms",
                        None,
                    )
                    if expires_at_ms is not None and expires_at_ms <= _now_ms():
                        blockers.append("exchange_submit_action_authorization_expired")
                    warnings.extend(
                        f"exchange_submit_action_authorization:{warning}"
                        for warning in action_authorization.warnings
                    )

        return _dedupe(blockers), _dedupe(warnings)


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _intent_id_for_draft(draft_id: str) -> str:
    digest = sha256(draft_id.encode("utf-8")).hexdigest()[:24]
    return f"intent_rt_{digest}"


def _exchange_submit_recovery_task_id(authorization_id: str) -> str:
    digest = sha256(authorization_id.encode("utf-8")).hexdigest()[:24]
    return f"rt_ex_submit_recovery_{digest}"


def _submit_outcome_review_policy_blockers(
    *,
    reservation: RuntimeExecutionAttemptReservation,
    review: RuntimeExecutionSubmitOutcomeReview,
) -> list[str]:
    blockers: list[str] = []
    if review.status != (
        RuntimeExecutionSubmitOutcomeReviewStatus
        .CLASSIFIED_READY_FOR_ATTEMPT_OUTCOME_POLICY
    ):
        blockers.append("submit_outcome_review_not_policy_ready")
    if not review.attempt_outcome_policy_ready:
        blockers.append("submit_outcome_review_policy_ready_false")
    if review.recommended_attempt_outcome_kind is None:
        blockers.append("submit_outcome_review_recommended_outcome_missing")
    if review.blockers:
        blockers.append("submit_outcome_review_has_blockers")
    if review.authorization_id != reservation.authorization_id:
        blockers.append("submit_outcome_review_authorization_mismatch")
    if review.execution_intent_id != reservation.execution_intent_id:
        blockers.append("submit_outcome_review_intent_mismatch")
    if review.runtime_instance_id != reservation.runtime_instance_id:
        blockers.append("submit_outcome_review_runtime_mismatch")
    if review.symbol != reservation.symbol:
        blockers.append("submit_outcome_review_symbol_mismatch")
    return _dedupe(blockers)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
