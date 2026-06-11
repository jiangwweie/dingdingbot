from __future__ import annotations

import importlib.util
from decimal import Decimal
from pathlib import Path
from time import time
from types import SimpleNamespace

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.application.runtime_execution_intent_adapter_service import (
    RuntimeExecutionIntentAdapterService,
)
from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.execution_intent import ExecutionIntent, ExecutionIntentStatus
from src.domain.models import Direction, OrderRole, OrderStatus, OrderType
from src.domain.models import OrderPlacementResult
from src.domain.runtime_execution_intent_adapter import (
    RuntimeExecutionIntentSourceType,
)
from src.domain.runtime_execution_intent_local_order_binding import (
    RuntimeExecutionIntentLocalOrderBindingStatus,
    build_runtime_execution_intent_local_order_binding,
)
from src.domain.runtime_execution_exchange_submit_packet import (
    RuntimeExecutionExchangeSubmitPacketPreviewStatus,
    build_runtime_execution_exchange_submit_packet_preview,
)
from src.domain.runtime_execution_exchange_submit_enablement import (
    RuntimeExecutionExchangeSubmitGateStatus,
    build_runtime_execution_exchange_submit_enablement_decision,
)
from src.domain.runtime_execution_exchange_submit_adapter_result import (
    RuntimeExecutionExchangeSubmitAdapterResultStatus,
    build_runtime_execution_exchange_submit_adapter_lock_result,
    build_runtime_execution_exchange_submit_adapter_result,
)
from src.domain.runtime_execution_exchange_submit_action_authorization import (
    RuntimeExecutionExchangeSubmitActionAuthorizationStatus,
    build_runtime_execution_exchange_submit_action_authorization,
)
from src.domain.runtime_execution_exchange_submit_execution_result import (
    RuntimeExecutionExchangeSubmitExecutionStatus,
    build_runtime_exchange_submit_execution_lock_result,
    build_runtime_exchange_submit_execution_submitted_result,
    submitted_exchange_order_from_placement,
)
from src.domain.runtime_execution_submit_rehearsal import (
    RuntimeExecutionSubmitRehearsalStatus,
)
from src.domain.runtime_execution_exchange_gateway_readiness import (
    RuntimeExecutionExchangeGatewayReadinessStatus,
)
from src.domain.runtime_execution_local_registration_enablement import (
    build_runtime_execution_local_registration_enablement_decision,
)
from src.domain.runtime_execution_attempt_outcome_policy import (
    RuntimeExecutionAttemptOutcomeKind,
    RuntimeExecutionAttemptOutcomePolicyStatus,
)
from src.domain.runtime_execution_protection_failure_policy import (
    RuntimeExecutionProtectionFailurePolicyStatus,
)
from src.domain.runtime_execution_submit_idempotency import (
    RuntimeExecutionSubmitIdempotencyStatus,
)
from src.domain.runtime_execution_duplicate_submit_replay_proof import (
    RuntimeExecutionDuplicateSubmitReplayProofStatus,
)
from src.domain.runtime_execution_submit_prerequisite_evidence_proof import (
    RuntimeExecutionSubmitPrerequisiteEvidenceProofStatus,
)
from src.domain.runtime_execution_trusted_submit_facts import (
    RuntimeExecutionTrustedSubmitFactsStatus,
)
from src.domain.runtime_execution_order_lifecycle_adapter_result import (
    RuntimeExecutionOrderLifecycleAdapterResultStatus,
    build_runtime_execution_order_lifecycle_adapter_lock_result,
    build_runtime_execution_order_lifecycle_adapter_result,
    build_runtime_execution_orders_for_registration,
)
from src.domain.runtime_execution_order_registration_draft import (
    RuntimeExecutionLocalOrderRegistrationDraft,
    RuntimeExecutionOrderRegistrationDraftPreview,
    RuntimeExecutionOrderRegistrationDraftPreviewStatus,
)
from src.infrastructure.pg_models import (
    PGExecutionRecoveryTaskORM,
    PGRuntimeExecutionExchangeSubmitActionAuthorizationORM,
    PGRuntimeExecutionExchangeSubmitAdapterResultORM,
    PGRuntimeExecutionExchangeSubmitExecutionResultORM,
    PGRuntimeExecutionOrderLifecycleAdapterResultORM,
)
from src.infrastructure.pg_execution_recovery_repository import (
    PgExecutionRecoveryRepository,
)
from src.infrastructure.pg_runtime_execution_exchange_submit_action_authorization_repository import (
    PgRuntimeExecutionExchangeSubmitActionAuthorizationRepository,
)
from src.infrastructure.pg_runtime_execution_exchange_submit_adapter_result_repository import (
    PgRuntimeExecutionExchangeSubmitAdapterResultRepository,
)
from src.infrastructure.pg_runtime_execution_exchange_submit_execution_result_repository import (
    PgRuntimeExecutionExchangeSubmitExecutionResultRepository,
)
from src.infrastructure.pg_runtime_execution_order_lifecycle_adapter_result_repository import (
    PgRuntimeExecutionOrderLifecycleAdapterResultRepository,
)


NOW_MS = 1781090000000


class _DraftRepo:
    async def get(self, draft_id: str):
        raise AssertionError("draft repository should not be used")


class _Lifecycle:
    def __init__(self, *, fail_on_role: OrderRole | None = None) -> None:
        self.calls = []
        self.orders = {}
        self.fail_on_role = fail_on_role

    async def register_created_order(self, order, *, metadata=None):
        self.calls.append({"order": order, "metadata": metadata or {}})
        if order.order_role == self.fail_on_role:
            raise RuntimeError(f"register_failed_for_{order.order_role.value.lower()}")
        self.orders[order.id] = order
        return order

    async def get_order(self, order_id: str):
        return self.orders.get(order_id)

    async def submit_order(self, order_id: str, exchange_order_id=None):
        order = self.orders.get(order_id)
        if order is None:
            raise ValueError(f"missing order {order_id}")
        order.exchange_order_id = exchange_order_id
        order.status = OrderStatus.SUBMITTED
        return order


class _ExchangeGateway:
    def __init__(self, *, fail_on_client_order_id: str | None = None) -> None:
        self.calls = []
        self.fail_on_client_order_id = fail_on_client_order_id

    async def place_order(
        self,
        *,
        symbol,
        order_type,
        side,
        amount,
        price=None,
        trigger_price=None,
        reduce_only=False,
        client_order_id=None,
    ):
        self.calls.append(
            {
                "symbol": symbol,
                "order_type": order_type,
                "side": side,
                "amount": amount,
                "price": price,
                "trigger_price": trigger_price,
                "reduce_only": reduce_only,
                "client_order_id": client_order_id,
            }
        )
        if client_order_id == self.fail_on_client_order_id:
            return OrderPlacementResult(
                order_id=f"failed-{client_order_id}",
                exchange_order_id=None,
                symbol=symbol,
                order_type=OrderType(order_type.upper()),
                direction=Direction.LONG if side == "buy" else Direction.SHORT,
                side=side,
                amount=amount,
                price=price,
                trigger_price=trigger_price,
                reduce_only=reduce_only,
                client_order_id=client_order_id,
                status=OrderStatus.REJECTED,
                error_code="TEST_REJECT",
                error_message=f"rejected {client_order_id}",
            )
        return OrderPlacementResult(
            order_id=f"exchange-placement-{client_order_id}",
            exchange_order_id=f"ex-{client_order_id}",
            symbol=symbol,
            order_type=OrderType(order_type.upper()),
            direction=Direction.LONG if side == "buy" else Direction.SHORT,
            side=side,
            amount=amount,
            price=price,
            trigger_price=trigger_price,
            reduce_only=reduce_only,
            client_order_id=client_order_id,
            status=OrderStatus.OPEN,
        )


class _AdapterResultRepo:
    def __init__(self) -> None:
        self.stored = None
        self.acquire_calls = 0
        self.complete_calls = 0

    async def acquire_registration_lock(self, result):
        self.acquire_calls += 1
        if self.stored is None:
            self.stored = result
            return True, result
        return False, self.stored

    async def complete_registration(self, result):
        self.complete_calls += 1
        self.stored = result
        return result

    async def get_by_authorization_id(self, authorization_id):
        if self.stored and self.stored.authorization_id == authorization_id:
            return self.stored
        return None


class _ExchangeSubmitAdapterResultRepo:
    def __init__(self) -> None:
        self.stored = None
        self.acquire_calls = 0
        self.complete_calls = 0

    async def acquire_exchange_submit_lock(self, result):
        self.acquire_calls += 1
        if self.stored is None:
            self.stored = result
            return True, result
        return False, self.stored

    async def complete_exchange_submit_result(self, result):
        self.complete_calls += 1
        self.stored = result
        return result

    async def get_by_authorization_id(self, authorization_id):
        if self.stored and self.stored.authorization_id == authorization_id:
            return self.stored
        return None


class _ExchangeSubmitExecutionResultRepo:
    def __init__(self) -> None:
        self.stored = None
        self.acquire_calls = 0
        self.complete_calls = 0

    async def acquire_exchange_submit_execution_lock(self, result):
        self.acquire_calls += 1
        if self.stored is None:
            self.stored = result
            return True, result
        return False, self.stored

    async def complete_exchange_submit_execution_result(self, result):
        self.complete_calls += 1
        self.stored = result
        return result

    async def get_by_authorization_id(self, authorization_id):
        if self.stored and self.stored.authorization_id == authorization_id:
            return self.stored
        return None


class _ExecutionRecoveryRepo:
    def __init__(self) -> None:
        self.tasks = {}
        self.create_calls = []

    async def get(self, task_id):
        return self.tasks.get(task_id)

    async def create_task(
        self,
        task_id,
        intent_id,
        symbol,
        recovery_type,
        related_order_id=None,
        related_exchange_order_id=None,
        error_message=None,
        context_payload=None,
    ):
        task = {
            "id": task_id,
            "intent_id": intent_id,
            "symbol": symbol,
            "recovery_type": recovery_type,
            "related_order_id": related_order_id,
            "related_exchange_order_id": related_exchange_order_id,
            "error_message": error_message,
            "context_payload": context_payload or {},
            "status": "pending",
        }
        self.tasks[task_id] = task
        self.create_calls.append(task)

    async def list_blocking(self):
        return [
            task
            for task in self.tasks.values()
            if task.get("status") in {"pending", "retrying"}
        ]


class _ExchangeGatewayReadinessRepo:
    def __init__(
        self,
        *,
        status=(
            RuntimeExecutionExchangeGatewayReadinessStatus
            .READY_FOR_MANUAL_GATEWAY_BINDING
        ),
        blockers=None,
        warnings=None,
        readiness=None,
        not_found=False,
        gateway_injected=False,
        exchange_called=False,
        exchange_order_submitted=False,
        order_lifecycle_submit_called=False,
        execution_intent_status_changed=False,
        created_at_ms=None,
    ) -> None:
        self.status = status
        self.blockers = blockers or []
        self.warnings = warnings or []
        self.readiness = readiness
        self.not_found = not_found
        self.gateway_injected = gateway_injected
        self.exchange_called = exchange_called
        self.exchange_order_submitted = exchange_order_submitted
        self.order_lifecycle_submit_called = order_lifecycle_submit_called
        self.execution_intent_status_changed = execution_intent_status_changed
        self.created_at_ms = created_at_ms

    async def get(self, _readiness_id):
        if self.not_found:
            return None
        if self.readiness is not None:
            return self.readiness
        return SimpleNamespace(
            status=self.status,
            blockers=list(self.blockers),
            warnings=list(self.warnings),
            gateway_injected=self.gateway_injected,
            exchange_called=self.exchange_called,
            exchange_order_submitted=self.exchange_order_submitted,
            order_lifecycle_submit_called=self.order_lifecycle_submit_called,
            execution_intent_status_changed=self.execution_intent_status_changed,
            created_at_ms=(
                self.created_at_ms
                if self.created_at_ms is not None
                else int(time() * 1000)
            ),
        )


class _TrustedSubmitFactsRepo:
    def __init__(
        self,
        *,
        execution_intent_id: str,
        runtime_instance_id: str,
        symbol: str,
        facts_fresh_enough: bool = True,
        read_only_sources_only: bool = True,
        owner_supplied_allow_facts_rejected: bool = True,
        missing_or_stale_facts_block: bool = True,
        not_execution_authority: bool = True,
        order_created: bool = False,
        exchange_called: bool = False,
        order_lifecycle_called: bool = False,
    ) -> None:
        self.execution_intent_id = execution_intent_id
        self.runtime_instance_id = runtime_instance_id
        self.symbol = symbol
        self.facts_fresh_enough = facts_fresh_enough
        self.read_only_sources_only = read_only_sources_only
        self.owner_supplied_allow_facts_rejected = (
            owner_supplied_allow_facts_rejected
        )
        self.missing_or_stale_facts_block = missing_or_stale_facts_block
        self.not_execution_authority = not_execution_authority
        self.order_created = order_created
        self.exchange_called = exchange_called
        self.order_lifecycle_called = order_lifecycle_called

    async def get(self, _snapshot_id):
        return SimpleNamespace(
            status=(
                RuntimeExecutionTrustedSubmitFactsStatus
                .READY_FOR_FIRST_REAL_SUBMIT_CONFIRMATION
            ),
            execution_intent_id=self.execution_intent_id,
            runtime_instance_id=self.runtime_instance_id,
            symbol=self.symbol,
            facts_fresh_enough=self.facts_fresh_enough,
            read_only_sources_only=self.read_only_sources_only,
            owner_supplied_allow_facts_rejected=(
                self.owner_supplied_allow_facts_rejected
            ),
            missing_or_stale_facts_block=self.missing_or_stale_facts_block,
            not_execution_authority=self.not_execution_authority,
            execution_intent_status_changed=False,
            runtime_state_mutated=False,
            order_created=self.order_created,
            exchange_called=self.exchange_called,
            order_lifecycle_called=self.order_lifecycle_called,
            owner_bounded_execution_called=False,
            withdrawal_instruction_created=False,
            transfer_instruction_created=False,
            warnings=[],
        )


class _SubmitIdempotencyRepo:
    def __init__(
        self,
        *,
        authorization_id: str,
        execution_intent_id: str,
        runtime_instance_id: str,
        replay_lock_key: str | None = None,
        status=(
            RuntimeExecutionSubmitIdempotencyStatus
            .READY_FOR_NON_EXECUTING_POLICY_CONFIRMATION
        ),
        missing: bool = False,
    ) -> None:
        self.authorization_id = authorization_id
        self.execution_intent_id = execution_intent_id
        self.runtime_instance_id = runtime_instance_id
        self.replay_lock_key = replay_lock_key or authorization_id
        self.status = status
        self.missing = missing

    async def get(self, _policy_id):
        if self.missing:
            return None
        return SimpleNamespace(
            status=self.status,
            authorization_id=self.authorization_id,
            execution_intent_id=self.execution_intent_id,
            runtime_instance_id=self.runtime_instance_id,
            stable_submit_key=f"runtime-submit:{self.authorization_id}",
            replay_lock_key=self.replay_lock_key,
            retry_uses_same_key=True,
            replay_existing_result_on_duplicate=True,
            blocks_concurrent_submit_without_lock=True,
            adapter_result_store_required=True,
            not_execution_authority=True,
            order_created=False,
            exchange_called=False,
            order_lifecycle_called=False,
            warnings=[],
        )


class _ProtectionFailurePolicyRepo:
    def __init__(self, *, execution_intent_id: str, runtime_instance_id: str) -> None:
        self.execution_intent_id = execution_intent_id
        self.runtime_instance_id = runtime_instance_id

    async def get(self, _policy_id):
        return SimpleNamespace(
            policy_id=_policy_id,
            status=(
                RuntimeExecutionProtectionFailurePolicyStatus
                .READY_FOR_FIRST_REAL_SUBMIT_CONFIRMATION
            ),
            execution_intent_id=self.execution_intent_id,
            runtime_instance_id=self.runtime_instance_id,
            symbol="BNB/USDT:USDT",
            block_new_entries_until_resolved=True,
            mark_position_unprotected_until_verified=True,
            require_owner_recovery_review=True,
            require_reduce_only_recovery_mode=True,
            require_reconciliation_before_retry=True,
            consume_attempt_on_any_fill=True,
            hold_or_reconcile_budget_until_position_resolved=True,
            not_execution_authority=True,
            execution_intent_status_changed=False,
            runtime_state_mutated=False,
            order_created=False,
            order_lifecycle_called=False,
            exchange_called=False,
            exchange_order_submitted=False,
            owner_bounded_execution_called=False,
            withdrawal_instruction_created=False,
            transfer_instruction_created=False,
            recovery_actions=[
                "record_unprotected_position_incident",
                "block_runtime_new_entries",
                "require_owner_recovery_review_before_retry",
                "enter_reduce_only_recovery_mode_until_resolved",
                "reconcile_position_and_open_orders_before_retry",
            ],
            blockers=[],
            warnings=[],
        )


class _AttemptOutcomePolicyRepo:
    def __init__(
        self,
        *,
        authorization_id: str,
        execution_intent_id: str,
        runtime_instance_id: str,
    ) -> None:
        self.authorization_id = authorization_id
        self.execution_intent_id = execution_intent_id
        self.runtime_instance_id = runtime_instance_id

    async def get(self, _policy_id):
        return SimpleNamespace(
            policy_id=_policy_id,
            status=(
                RuntimeExecutionAttemptOutcomePolicyStatus
                .READY_FOR_ATTEMPT_BUDGET_OUTCOME_ACCOUNTING
            ),
            outcome_kind=(
                RuntimeExecutionAttemptOutcomeKind
                .ENTRY_FILLED_PROTECTION_CREATION_FAILED
            ),
            authorization_id=self.authorization_id,
            execution_intent_id=self.execution_intent_id,
            runtime_instance_id=self.runtime_instance_id,
            symbol="BNB/USDT:USDT",
            protection_creation_failed=True,
            blocks_new_entries_until_resolved=True,
            requires_owner_recovery_review=True,
            requires_reduce_only_recovery_mode=True,
            requires_reconciliation_before_retry=True,
            attempt_should_be_consumed=True,
            partial_fill_counts_as_attempt=True,
            reserved_budget_should_remain_held=True,
            not_execution_authority=True,
            execution_intent_status_changed=False,
            runtime_state_mutated=False,
            order_created=False,
            order_lifecycle_called=False,
            exchange_called=False,
            exchange_order_submitted=False,
            owner_bounded_execution_called=False,
            withdrawal_instruction_created=False,
            transfer_instruction_created=False,
            blockers=[],
            warnings=[],
        )


class _ExchangeSubmitActionAuthorizationRepo:
    def __init__(
        self,
        *,
        authorization_id: str,
        execution_intent_id: str,
        runtime_instance_id: str,
        symbol: str,
        local_registration_enablement_decision_id: str,
        status=(
            RuntimeExecutionExchangeSubmitActionAuthorizationStatus
            .APPROVED_FOR_EXCHANGE_SUBMIT_ACTION
        ),
        missing: bool = False,
        expires_at_ms=None,
        deployment_readiness_evidence_id="runtime-exchange-gateway-readiness-1",
    ) -> None:
        self.authorization_id = authorization_id
        self.execution_intent_id = execution_intent_id
        self.runtime_instance_id = runtime_instance_id
        self.symbol = symbol
        self.local_registration_enablement_decision_id = (
            local_registration_enablement_decision_id
        )
        self.status = status
        self.missing = missing
        self.expires_at_ms = expires_at_ms
        self.deployment_readiness_evidence_id = deployment_readiness_evidence_id

    async def create(self, authorization):
        return authorization

    async def get(self, _action_authorization_id):
        if self.missing:
            return None
        return SimpleNamespace(
            status=self.status,
            authorization_id=self.authorization_id,
            execution_intent_id=self.execution_intent_id,
            runtime_instance_id=self.runtime_instance_id,
            symbol=self.symbol,
            local_registration_enablement_decision_id=(
                self.local_registration_enablement_decision_id
            ),
            trusted_submit_fact_snapshot_id="trusted-submit-facts-intent-1",
            submit_idempotency_policy_id="runtime-submit-idempotency-auth-1",
            attempt_outcome_policy_id="runtime-attempt-outcome-policy-auth-1",
            protection_creation_failure_policy_id=(
                "protection-failure-policy-intent-1"
            ),
            owner_real_submit_authorization_id="owner-real-submit-auth-1",
            order_lifecycle_submit_enablement_id=(
                "order-lifecycle-submit-enable-1"
            ),
            exchange_submit_adapter_enablement_id=(
                "exchange-submit-adapter-enable-1"
            ),
            deployment_readiness_evidence_id=self.deployment_readiness_evidence_id,
            owner_confirmed_for_exchange_submit_action=True,
            expires_at_ms=self.expires_at_ms,
            warnings=[],
        )


class _IntentRepo:
    def __init__(self, intent: ExecutionIntent) -> None:
        self.intent = intent
        self.saved = []

    async def get(self, intent_id: str):
        if intent_id == self.intent.id:
            return self.intent
        return None

    async def save(self, intent: ExecutionIntent) -> None:
        self.intent = intent
        self.saved.append(intent)


def _registration_preview() -> RuntimeExecutionOrderRegistrationDraftPreview:
    semantic_ids = BrcSemanticIds(
        runtime_instance_id="runtime-1",
        trial_binding_id="binding-1",
        strategy_family_id="CPM-001",
        strategy_family_version_id="CPM-001-v0",
        signal_evaluation_id="signal-eval-1",
        order_candidate_id="candidate-1",
    )
    entry_id = "runtime-order-draft-auth-1-entry"
    return RuntimeExecutionOrderRegistrationDraftPreview(
        registration_preview_id="registration-preview-1",
        adapter_preview_id="adapter-preview-1",
        handoff_draft_id="handoff-1",
        preflight_id="preflight-1",
        authorization_id="auth-1",
        execution_intent_id="intent-1",
        runtime_instance_id="runtime-1",
        source_type="brc_runtime_order_candidate",
        source_id="candidate-1",
        semantic_ids=semantic_ids,
        status=(
            RuntimeExecutionOrderRegistrationDraftPreviewStatus
            .INPUTS_READY_REGISTRATION_DRAFT_ONLY
        ),
        symbol="BNB/USDT:USDT",
        side="long",
        local_order_registration_drafts=[
            RuntimeExecutionLocalOrderRegistrationDraft(
                local_order_draft_id=entry_id,
                signal_id="signal-eval-1",
                symbol="BNB/USDT:USDT",
                direction=Direction.LONG,
                order_type=OrderType.MARKET,
                order_role=OrderRole.ENTRY,
                requested_qty=Decimal("0.016"),
                status=OrderStatus.CREATED,
                created_at=NOW_MS,
                updated_at=NOW_MS,
                reduce_only=False,
                runtime_instance_id="runtime-1",
                trial_binding_id="binding-1",
                strategy_family_id="CPM-001",
                strategy_family_version_id="CPM-001-v0",
                signal_evaluation_id="signal-eval-1",
                order_candidate_id="candidate-1",
            ),
            RuntimeExecutionLocalOrderRegistrationDraft(
                local_order_draft_id="runtime-order-draft-auth-1-sl",
                signal_id="signal-eval-1",
                symbol="BNB/USDT:USDT",
                direction=Direction.LONG,
                order_type=OrderType.STOP_MARKET,
                order_role=OrderRole.SL,
                trigger_price=Decimal("587.50"),
                requested_qty=Decimal("0.016"),
                status=OrderStatus.CREATED,
                created_at=NOW_MS,
                updated_at=NOW_MS,
                reduce_only=True,
                parent_local_order_draft_id=entry_id,
                runtime_instance_id="runtime-1",
                trial_binding_id="binding-1",
                strategy_family_id="CPM-001",
                strategy_family_version_id="CPM-001-v0",
                signal_evaluation_id="signal-eval-1",
                order_candidate_id="candidate-1",
            ),
        ],
        registration_draft_count=2,
        entry_registration_draft_count=1,
        protection_registration_draft_count=1,
        created_at_ms=NOW_MS,
    )


def _ready_enablement_decision(preview: RuntimeExecutionOrderRegistrationDraftPreview):
    return build_runtime_execution_local_registration_enablement_decision(
        registration_preview=preview,
        trusted_submit_fact_snapshot_id="trusted-submit-facts-intent-1",
        submit_idempotency_policy_id="runtime-submit-idempotency-auth-1",
        attempt_outcome_policy_id="runtime-attempt-outcome-policy-auth-1",
        protection_creation_failure_policy_id="protection-failure-policy-intent-1",
        owner_real_submit_authorization_id="owner-real-submit-auth-1",
        order_lifecycle_adapter_enablement_id="adapter-enablement-1",
        local_order_registration_enablement_id="local-registration-enablement-1",
        local_registration_action_authorization_id="local-registration-action-1",
        now_ms=NOW_MS,
    )


def _runtime_intent(preview: RuntimeExecutionOrderRegistrationDraftPreview) -> ExecutionIntent:
    return ExecutionIntent(
        id=preview.execution_intent_id,
        symbol=preview.symbol,
        status=ExecutionIntentStatus.RECORDED,
        source_type=RuntimeExecutionIntentSourceType.BRC_RUNTIME_ORDER_CANDIDATE.value,
        source_id=preview.source_id,
        source_payload={
            "side": preview.side,
            "candidate_order_type": "market",
            "proposed_quantity": "0.016",
            "intended_notional": "9.60",
            "exchange_called": False,
        },
        runtime_execution_intent_draft_id="draft-1",
        runtime_instance_id=preview.runtime_instance_id,
        trial_binding_id=preview.semantic_ids.trial_binding_id,
        strategy_family_id=preview.semantic_ids.strategy_family_id,
        strategy_family_version_id=preview.semantic_ids.strategy_family_version_id,
        signal_evaluation_id=preview.semantic_ids.signal_evaluation_id,
        order_candidate_id=preview.semantic_ids.order_candidate_id,
    )


def _ready_exchange_submit_enablement_decision(preview):
    orders = build_runtime_execution_orders_for_registration(
        registration_preview=preview
    )
    adapter_result = build_runtime_execution_order_lifecycle_adapter_result(
        registration_preview=preview,
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        duplicate_submit_lock_acquired=True,
        registered_orders=orders,
        now_ms=NOW_MS,
    )
    binding = build_runtime_execution_intent_local_order_binding(
        intent=_runtime_intent(preview),
        adapter_result=adapter_result,
        now_ms=NOW_MS + 1,
    )
    packet = build_runtime_execution_exchange_submit_packet_preview(
        binding=binding,
        local_orders=orders,
        now_ms=NOW_MS + 2,
    )
    return build_runtime_execution_exchange_submit_enablement_decision(
        packet_preview=packet,
        trusted_submit_fact_snapshot_id="trusted-submit-facts-intent-1",
        submit_idempotency_policy_id="runtime-submit-idempotency-auth-1",
        attempt_outcome_policy_id="runtime-attempt-outcome-policy-auth-1",
        protection_creation_failure_policy_id="protection-failure-policy-intent-1",
        local_registration_enablement_decision_id=(
            "runtime-local-registration-enablement-auth-1"
        ),
        owner_real_submit_authorization_id="owner-real-submit-auth-1",
        order_lifecycle_submit_enablement_id="order-lifecycle-submit-enable-1",
        exchange_submit_adapter_enablement_id="exchange-submit-adapter-enable-1",
        exchange_submit_action_authorization_id="exchange-submit-action-1",
        deployment_readiness_evidence_id="runtime-exchange-gateway-readiness-1",
        now_ms=NOW_MS + 3,
    )


def _service_with_preview(
    preview,
    lifecycle=None,
    adapter_result_repo=None,
    exchange_submit_adapter_result_repo=None,
    exchange_submit_action_authorization_repo=None,
    exchange_submit_execution_result_repo=None,
    exchange_gateway_readiness_repo=None,
    execution_recovery_repo=None,
    exchange_gateway=None,
    intent_repo=None,
    submit_idempotency_repo=None,
    trusted_submit_facts_repo=None,
    attempt_outcome_policy_repo=None,
    protection_failure_policy_repo=None,
) -> RuntimeExecutionIntentAdapterService:
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftRepo(),
        intent_repository=intent_repo,
        order_lifecycle_service=lifecycle,
        order_lifecycle_adapter_result_repository=adapter_result_repo,
        trusted_submit_facts_repository=(
            trusted_submit_facts_repo
            or _TrustedSubmitFactsRepo(
                execution_intent_id=preview.execution_intent_id,
                runtime_instance_id=preview.runtime_instance_id,
                symbol=preview.symbol,
            )
        ),
        submit_idempotency_repository=(
            submit_idempotency_repo
            or _SubmitIdempotencyRepo(
                authorization_id=preview.authorization_id,
                execution_intent_id=preview.execution_intent_id,
                runtime_instance_id=preview.runtime_instance_id,
            )
        ),
        attempt_outcome_policy_repository=(
            attempt_outcome_policy_repo
            or _AttemptOutcomePolicyRepo(
                authorization_id=preview.authorization_id,
                execution_intent_id=preview.execution_intent_id,
                runtime_instance_id=preview.runtime_instance_id,
            )
        ),
        protection_failure_policy_repository=(
            protection_failure_policy_repo
            or _ProtectionFailurePolicyRepo(
                execution_intent_id=preview.execution_intent_id,
                runtime_instance_id=preview.runtime_instance_id,
            )
        ),
        exchange_submit_adapter_result_repository=(
            exchange_submit_adapter_result_repo
        ),
        exchange_submit_action_authorization_repository=(
            exchange_submit_action_authorization_repo
            or _ExchangeSubmitActionAuthorizationRepo(
                authorization_id=preview.authorization_id,
                execution_intent_id=preview.execution_intent_id,
                runtime_instance_id=preview.runtime_instance_id,
                symbol=preview.symbol,
                local_registration_enablement_decision_id=(
                    "runtime-local-registration-enablement-auth-1"
                ),
            )
        ),
        exchange_submit_execution_result_repository=(
            exchange_submit_execution_result_repo
        ),
        exchange_gateway_readiness_repository=exchange_gateway_readiness_repo,
        execution_recovery_repository=execution_recovery_repo,
        exchange_gateway=exchange_gateway,
    )

    async def _preview_for_authorization(authorization_id: str):
        assert authorization_id == preview.authorization_id
        return preview

    service.order_registration_draft_preview_for_authorization = (  # type: ignore[method-assign]
        _preview_for_authorization
    )
    return service


_DEFAULT_READINESS_REPO = object()


async def _ready_exchange_submit_execution_context(
    *,
    exchange_gateway_readiness_repo=_DEFAULT_READINESS_REPO,
    deployment_readiness_evidence_id=(
        "runtime-exchange-gateway-readiness-1"
    ),
    exchange_gateway=None,
):
    preview = _registration_preview()
    lifecycle = _Lifecycle()
    adapter_result_repo = _AdapterResultRepo()
    execution_result_repo = _ExchangeSubmitExecutionResultRepo()
    recovery_repo = _ExecutionRecoveryRepo()
    gateway = exchange_gateway or _ExchangeGateway()
    intent_repo = _IntentRepo(_runtime_intent(preview))
    if exchange_gateway_readiness_repo is _DEFAULT_READINESS_REPO:
        exchange_gateway_readiness_repo = _ExchangeGatewayReadinessRepo()
    service = _service_with_preview(
        preview,
        lifecycle=lifecycle,
        adapter_result_repo=adapter_result_repo,
        exchange_submit_execution_result_repo=execution_result_repo,
        execution_recovery_repo=recovery_repo,
        exchange_gateway=gateway,
        exchange_gateway_readiness_repo=exchange_gateway_readiness_repo,
        intent_repo=intent_repo,
    )
    local_decision = _ready_enablement_decision(preview)
    await service.order_lifecycle_adapter_result_for_authorization(
        "auth-1",
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        local_registration_enablement_decision=local_decision,
    )
    exchange_decision = (
        await service.exchange_submit_enablement_decision_for_authorization(
            "auth-1",
            trusted_submit_fact_snapshot_id="trusted-submit-facts-intent-1",
            submit_idempotency_policy_id="runtime-submit-idempotency-auth-1",
            attempt_outcome_policy_id="runtime-attempt-outcome-policy-auth-1",
            protection_creation_failure_policy_id=(
                "protection-failure-policy-intent-1"
            ),
            local_registration_enablement_decision_id=(
                local_decision.decision_id
            ),
            owner_real_submit_authorization_id="owner-real-submit-auth-1",
            order_lifecycle_submit_enablement_id=(
                "order-lifecycle-submit-enable-1"
            ),
            exchange_submit_adapter_enablement_id=(
                "exchange-submit-adapter-enable-1"
            ),
            exchange_submit_action_authorization_id="exchange-submit-action-1",
            deployment_readiness_evidence_id=deployment_readiness_evidence_id,
        )
    )
    return SimpleNamespace(
        service=service,
        gateway=gateway,
        intent_repo=intent_repo,
        exchange_submit_execution_result_repo=execution_result_repo,
        recovery_repo=recovery_repo,
        symbol=preview.symbol,
        exchange_decision=exchange_decision,
    )


def test_registration_preview_maps_to_order_objects_with_runtime_semantics():
    preview = _registration_preview()

    orders = build_runtime_execution_orders_for_registration(
        registration_preview=preview
    )

    assert [order.id for order in orders] == [
        "runtime-order-draft-auth-1-entry",
        "runtime-order-draft-auth-1-sl",
    ]
    assert orders[0].status == OrderStatus.CREATED
    assert orders[0].exchange_order_id is None
    assert orders[0].runtime_instance_id == "runtime-1"
    assert orders[0].strategy_family_version_id == "CPM-001-v0"
    assert orders[0].order_candidate_id == "candidate-1"
    assert orders[1].order_role == OrderRole.SL
    assert orders[1].reduce_only is True
    assert orders[1].parent_order_id == "runtime-order-draft-auth-1-entry"


@pytest.mark.asyncio
async def test_adapter_result_default_disabled_does_not_call_lifecycle():
    preview = _registration_preview()
    lifecycle = _Lifecycle()
    service = _service_with_preview(preview, lifecycle=lifecycle)

    result = await service.order_lifecycle_adapter_result_for_authorization(
        "auth-1"
    )

    assert (
        result.status
        == RuntimeExecutionOrderLifecycleAdapterResultStatus
        .ORDER_LIFECYCLE_ADAPTER_DISABLED
    )
    assert result.blockers == ["order_lifecycle_adapter_disabled"]
    assert result.order_objects_constructed is False
    assert result.local_order_registration_executed is False
    assert result.order_lifecycle_called is False
    assert result.exchange_called is False
    assert lifecycle.calls == []


@pytest.mark.asyncio
async def test_adapter_result_requires_ready_enablement_decision_before_registration():
    preview = _registration_preview()
    lifecycle = _Lifecycle()
    service = _service_with_preview(preview, lifecycle=lifecycle)

    result = await service.order_lifecycle_adapter_result_for_authorization(
        "auth-1",
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
    )

    assert result.status == RuntimeExecutionOrderLifecycleAdapterResultStatus.BLOCKED
    assert (
        "first_real_submit_local_registration_enablement_decision_required"
        in result.blockers
    )
    assert result.order_objects_constructed is False
    assert result.local_order_registration_executed is False
    assert result.order_lifecycle_called is False
    assert result.exchange_called is False
    assert lifecycle.calls == []


@pytest.mark.asyncio
async def test_adapter_result_requires_persistent_repo_before_registration():
    preview = _registration_preview()
    lifecycle = _Lifecycle()
    service = _service_with_preview(preview, lifecycle=lifecycle)
    decision = _ready_enablement_decision(preview)

    with pytest.raises(
        RuntimeError,
        match="runtime_execution_order_lifecycle_adapter_result_repository_unavailable",
    ):
        await service.order_lifecycle_adapter_result_for_authorization(
            "auth-1",
            order_lifecycle_adapter_enabled=True,
            local_order_registration_enabled=True,
            local_registration_enablement_decision=decision,
        )

    assert lifecycle.calls == []


@pytest.mark.asyncio
async def test_adapter_result_registers_created_local_orders_and_replays():
    preview = _registration_preview()
    lifecycle = _Lifecycle()
    adapter_result_repo = _AdapterResultRepo()
    service = _service_with_preview(
        preview,
        lifecycle=lifecycle,
        adapter_result_repo=adapter_result_repo,
    )
    decision = _ready_enablement_decision(preview)

    first = await service.order_lifecycle_adapter_result_for_authorization(
        "auth-1",
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        local_registration_enablement_decision=decision,
    )
    second = await service.order_lifecycle_adapter_result_for_authorization(
        "auth-1",
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        local_registration_enablement_decision=decision,
    )

    assert (
        first.status
        == RuntimeExecutionOrderLifecycleAdapterResultStatus
        .REGISTERED_CREATED_LOCAL_ORDERS
    )
    assert second == first
    assert adapter_result_repo.acquire_calls == 2
    assert adapter_result_repo.complete_calls == 1
    assert [call["order"].id for call in lifecycle.calls] == first.local_order_ids
    assert first.exchange_called is False
    assert first.exchange_order_submitted is False
    assert first.execution_intent_status_changed is False


@pytest.mark.asyncio
async def test_adapter_result_records_protection_registration_failure_and_replays():
    preview = _registration_preview()
    lifecycle = _Lifecycle(fail_on_role=OrderRole.SL)
    adapter_result_repo = _AdapterResultRepo()
    service = _service_with_preview(
        preview,
        lifecycle=lifecycle,
        adapter_result_repo=adapter_result_repo,
    )
    decision = _ready_enablement_decision(preview)

    first = await service.order_lifecycle_adapter_result_for_authorization(
        "auth-1",
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        local_registration_enablement_decision=decision,
    )
    second = await service.order_lifecycle_adapter_result_for_authorization(
        "auth-1",
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        local_registration_enablement_decision=decision,
    )

    assert (
        first.status
        == RuntimeExecutionOrderLifecycleAdapterResultStatus
        .LOCAL_ORDER_REGISTRATION_FAILED
    )
    assert second == first
    assert adapter_result_repo.acquire_calls == 2
    assert adapter_result_repo.complete_calls == 1
    assert [call["order"].id for call in lifecycle.calls] == [
        "runtime-order-draft-auth-1-entry",
        "runtime-order-draft-auth-1-sl",
    ]
    assert first.local_order_ids == ["runtime-order-draft-auth-1-entry"]
    assert first.protection_order_ids == []
    assert "protection_order_registration_failed" in first.blockers
    assert first.exchange_called is False
    assert first.exchange_order_submitted is False
    assert first.execution_intent_status_changed is False


def test_intent_local_order_binding_reaches_submit_design_without_mutating_intent():
    preview = _registration_preview()
    orders = build_runtime_execution_orders_for_registration(
        registration_preview=preview
    )
    adapter_result = build_runtime_execution_order_lifecycle_adapter_result(
        registration_preview=preview,
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        duplicate_submit_lock_acquired=True,
        registered_orders=orders,
        now_ms=NOW_MS,
    )
    intent = _runtime_intent(preview)

    binding = build_runtime_execution_intent_local_order_binding(
        intent=intent,
        adapter_result=adapter_result,
        now_ms=NOW_MS + 1,
    )

    assert (
        binding.status
        == RuntimeExecutionIntentLocalOrderBindingStatus
        .READY_FOR_EXCHANGE_SUBMIT_DESIGN
    )
    assert binding.blockers == []
    assert binding.entry_order_id == "runtime-order-draft-auth-1-entry"
    assert binding.protection_order_ids == ["runtime-order-draft-auth-1-sl"]
    assert binding.previous_intent_status == ExecutionIntentStatus.RECORDED
    assert binding.local_orders_registered is True
    assert binding.execution_intent_status_changed is False
    assert binding.order_id_linked_to_intent is False
    assert binding.exchange_order_submitted is False
    assert binding.exchange_called is False
    assert intent.order_id is None
    assert intent.exchange_order_id is None


def test_intent_local_order_binding_blocks_failed_adapter_result():
    preview = _registration_preview()
    attempted = build_runtime_execution_orders_for_registration(
        registration_preview=preview
    )
    adapter_result = build_runtime_execution_order_lifecycle_adapter_result(
        registration_preview=preview,
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        duplicate_submit_lock_acquired=True,
        registered_orders=[attempted[0]],
        additional_blockers=["local_order_registration_failed"],
        now_ms=NOW_MS,
    )

    binding = build_runtime_execution_intent_local_order_binding(
        intent=_runtime_intent(preview),
        adapter_result=adapter_result,
        now_ms=NOW_MS + 1,
    )

    assert binding.status == RuntimeExecutionIntentLocalOrderBindingStatus.BLOCKED
    assert "local_orders_not_registered" in binding.blockers
    assert "local_order_registration_failed" in binding.blockers
    assert binding.execution_intent_status_changed is False
    assert binding.exchange_called is False


def test_exchange_submit_packet_preview_maps_local_orders_without_submit():
    preview = _registration_preview()
    orders = build_runtime_execution_orders_for_registration(
        registration_preview=preview
    )
    adapter_result = build_runtime_execution_order_lifecycle_adapter_result(
        registration_preview=preview,
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        duplicate_submit_lock_acquired=True,
        registered_orders=orders,
        now_ms=NOW_MS,
    )
    binding = build_runtime_execution_intent_local_order_binding(
        intent=_runtime_intent(preview),
        adapter_result=adapter_result,
        now_ms=NOW_MS + 1,
    )

    packet = build_runtime_execution_exchange_submit_packet_preview(
        binding=binding,
        local_orders=orders,
        now_ms=NOW_MS + 2,
    )

    assert (
        packet.status
        == RuntimeExecutionExchangeSubmitPacketPreviewStatus
        .READY_FOR_EXCHANGE_SUBMIT_ADAPTER_DESIGN
    )
    assert packet.blockers == []
    assert packet.local_orders_resolved is True
    assert packet.local_order_count == 2
    assert packet.entry_submit_request_count == 1
    assert packet.protection_submit_request_count == 1
    assert packet.entry_submit_request_preview is not None
    assert packet.entry_submit_request_preview.gateway_order_type == "market"
    assert packet.entry_submit_request_preview.gateway_side == "buy"
    assert packet.entry_submit_request_preview.reduce_only is False
    assert packet.entry_submit_request_preview.future_client_order_reference == (
        "runtime-order-draft-auth-1-entry"
    )
    protection = packet.protection_submit_request_previews[0]
    assert protection.gateway_order_type == "stop_market"
    assert protection.gateway_side == "sell"
    assert protection.trigger_price == Decimal("587.50")
    assert protection.reduce_only is True
    assert packet.exchange_submit_adapter_enabled is False
    assert packet.exchange_submit_adapter_implemented is False
    assert packet.execution_intent_status_changed is False
    assert packet.order_lifecycle_submit_called is False
    assert packet.exchange_order_submitted is False
    assert packet.exchange_called is False
    assert packet.not_exchange_submit_authority is True


def test_exchange_submit_packet_preview_blocks_unresolved_or_submitted_orders():
    preview = _registration_preview()
    orders = build_runtime_execution_orders_for_registration(
        registration_preview=preview
    )
    orders[0].status = OrderStatus.SUBMITTED
    adapter_result = build_runtime_execution_order_lifecycle_adapter_result(
        registration_preview=preview,
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        duplicate_submit_lock_acquired=True,
        registered_orders=orders,
        now_ms=NOW_MS,
    )
    binding = build_runtime_execution_intent_local_order_binding(
        intent=_runtime_intent(preview),
        adapter_result=adapter_result,
        now_ms=NOW_MS + 1,
    )

    packet = build_runtime_execution_exchange_submit_packet_preview(
        binding=binding,
        local_orders=orders[:1],
        now_ms=NOW_MS + 2,
    )

    assert packet.status == RuntimeExecutionExchangeSubmitPacketPreviewStatus.BLOCKED
    assert "local_order_ids_unresolved" in packet.blockers
    assert "local_order_status_not_created" in packet.blockers
    assert packet.exchange_called is False
    assert packet.order_lifecycle_submit_called is False


def test_exchange_submit_enablement_blocks_missing_evidence_ids():
    preview = _registration_preview()
    orders = build_runtime_execution_orders_for_registration(
        registration_preview=preview
    )
    adapter_result = build_runtime_execution_order_lifecycle_adapter_result(
        registration_preview=preview,
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        duplicate_submit_lock_acquired=True,
        registered_orders=orders,
        now_ms=NOW_MS,
    )
    binding = build_runtime_execution_intent_local_order_binding(
        intent=_runtime_intent(preview),
        adapter_result=adapter_result,
        now_ms=NOW_MS + 1,
    )
    packet = build_runtime_execution_exchange_submit_packet_preview(
        binding=binding,
        local_orders=orders,
        now_ms=NOW_MS + 2,
    )

    decision = build_runtime_execution_exchange_submit_enablement_decision(
        packet_preview=packet,
        now_ms=NOW_MS + 3,
    )

    assert decision.status == RuntimeExecutionExchangeSubmitGateStatus.BLOCKED
    assert "owner_real_submit_authorization_id_missing" in decision.blockers
    assert "exchange_submit_adapter_enablement_id_missing" in decision.blockers
    assert "exchange_submit_action_authorization_id_missing" in decision.blockers
    assert "order_lifecycle_submit_enablement_id_missing" in decision.blockers
    assert "local_registration_enablement_decision_id_missing" in decision.blockers
    assert "attempt_outcome_policy_id_missing" in decision.blockers
    assert decision.exchange_submit_gate.exchange_called is False
    assert decision.exchange_called is False
    assert decision.order_lifecycle_submit_called is False


def test_exchange_submit_enablement_ready_is_still_not_submit_authority():
    preview = _registration_preview()
    orders = build_runtime_execution_orders_for_registration(
        registration_preview=preview
    )
    adapter_result = build_runtime_execution_order_lifecycle_adapter_result(
        registration_preview=preview,
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        duplicate_submit_lock_acquired=True,
        registered_orders=orders,
        now_ms=NOW_MS,
    )
    binding = build_runtime_execution_intent_local_order_binding(
        intent=_runtime_intent(preview),
        adapter_result=adapter_result,
        now_ms=NOW_MS + 1,
    )
    packet = build_runtime_execution_exchange_submit_packet_preview(
        binding=binding,
        local_orders=orders,
        now_ms=NOW_MS + 2,
    )

    decision = build_runtime_execution_exchange_submit_enablement_decision(
        packet_preview=packet,
        trusted_submit_fact_snapshot_id="trusted-submit-facts-intent-1",
        submit_idempotency_policy_id="runtime-submit-idempotency-auth-1",
        attempt_outcome_policy_id="runtime-attempt-outcome-policy-auth-1",
        protection_creation_failure_policy_id="protection-failure-policy-intent-1",
        local_registration_enablement_decision_id=(
            "runtime-local-registration-enablement-auth-1"
        ),
        owner_real_submit_authorization_id="owner-real-submit-auth-1",
        order_lifecycle_submit_enablement_id="order-lifecycle-submit-enable-1",
        exchange_submit_adapter_enablement_id="exchange-submit-adapter-enable-1",
        exchange_submit_action_authorization_id="exchange-submit-action-1",
        now_ms=NOW_MS + 3,
    )

    assert (
        decision.status
        == RuntimeExecutionExchangeSubmitGateStatus.READY_FOR_EXCHANGE_SUBMIT_ACTION
    )
    assert decision.blockers == []
    assert decision.exchange_submit_gate.exchange_submit_adapter_enabled is True
    assert decision.exchange_submit_gate.order_lifecycle_submit_enabled is True
    assert decision.exchange_submit_gate.exchange_submit_action_authorized is True
    assert decision.not_exchange_submit_authority is True
    assert decision.order_lifecycle_submit_called is False
    assert decision.execution_intent_status_changed is False
    assert decision.exchange_order_submitted is False
    assert decision.exchange_called is False


def test_exchange_submit_action_authorization_is_scope_bound_evidence():
    preview = _registration_preview()
    orders = build_runtime_execution_orders_for_registration(
        registration_preview=preview
    )
    adapter_result = build_runtime_execution_order_lifecycle_adapter_result(
        registration_preview=preview,
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        duplicate_submit_lock_acquired=True,
        registered_orders=orders,
        now_ms=NOW_MS,
    )
    binding = build_runtime_execution_intent_local_order_binding(
        intent=_runtime_intent(preview),
        adapter_result=adapter_result,
        now_ms=NOW_MS + 1,
    )
    packet = build_runtime_execution_exchange_submit_packet_preview(
        binding=binding,
        local_orders=orders,
        now_ms=NOW_MS + 2,
    )

    authorization = build_runtime_execution_exchange_submit_action_authorization(
        packet_preview=packet,
        trusted_submit_fact_snapshot_id="trusted-submit-facts-intent-1",
        submit_idempotency_policy_id="runtime-submit-idempotency-auth-1",
        attempt_outcome_policy_id="runtime-attempt-outcome-policy-auth-1",
        protection_creation_failure_policy_id="protection-failure-policy-intent-1",
        local_registration_enablement_decision_id=(
            "runtime-local-registration-enablement-auth-1"
        ),
        owner_real_submit_authorization_id="owner-real-submit-auth-1",
        order_lifecycle_submit_enablement_id="order-lifecycle-submit-enable-1",
        exchange_submit_adapter_enablement_id="exchange-submit-adapter-enable-1",
        owner_confirmed_for_exchange_submit_action=True,
        owner_operator_id="owner",
        reason="scoped first exchange submit action confirmation",
        now_ms=NOW_MS + 3,
    )

    assert (
        authorization.status
        == RuntimeExecutionExchangeSubmitActionAuthorizationStatus
        .APPROVED_FOR_EXCHANGE_SUBMIT_ACTION
    )
    assert authorization.blockers == []
    assert authorization.authorization_id == "auth-1"
    assert authorization.execution_intent_id == "intent-1"
    assert authorization.local_order_ids == [
        "runtime-order-draft-auth-1-entry",
        "runtime-order-draft-auth-1-sl",
    ]
    assert authorization.not_exchange_submit_authority is True
    assert authorization.order_lifecycle_submit_called is False
    assert authorization.execution_intent_status_changed is False
    assert authorization.exchange_order_submitted is False
    assert authorization.exchange_called is False
    assert authorization.owner_bounded_execution_called is False
    assert authorization.withdrawal_or_transfer_created is False


def test_exchange_submit_action_authorization_blocks_without_owner_confirmation():
    preview = _registration_preview()
    orders = build_runtime_execution_orders_for_registration(
        registration_preview=preview
    )
    adapter_result = build_runtime_execution_order_lifecycle_adapter_result(
        registration_preview=preview,
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        duplicate_submit_lock_acquired=True,
        registered_orders=orders,
        now_ms=NOW_MS,
    )
    binding = build_runtime_execution_intent_local_order_binding(
        intent=_runtime_intent(preview),
        adapter_result=adapter_result,
        now_ms=NOW_MS + 1,
    )
    packet = build_runtime_execution_exchange_submit_packet_preview(
        binding=binding,
        local_orders=orders,
        now_ms=NOW_MS + 2,
    )

    authorization = build_runtime_execution_exchange_submit_action_authorization(
        packet_preview=packet,
        trusted_submit_fact_snapshot_id="trusted-submit-facts-intent-1",
        submit_idempotency_policy_id="runtime-submit-idempotency-auth-1",
        attempt_outcome_policy_id="runtime-attempt-outcome-policy-auth-1",
        protection_creation_failure_policy_id="protection-failure-policy-intent-1",
        local_registration_enablement_decision_id=(
            "runtime-local-registration-enablement-auth-1"
        ),
        owner_real_submit_authorization_id="owner-real-submit-auth-1",
        order_lifecycle_submit_enablement_id="order-lifecycle-submit-enable-1",
        exchange_submit_adapter_enablement_id="exchange-submit-adapter-enable-1",
        owner_confirmed_for_exchange_submit_action=False,
        owner_operator_id="owner",
        reason="missing confirmation should block",
        now_ms=NOW_MS + 3,
    )

    assert (
        authorization.status
        == RuntimeExecutionExchangeSubmitActionAuthorizationStatus.BLOCKED
    )
    assert (
        "owner_exchange_submit_action_confirmation_missing"
        in authorization.blockers
    )
    assert authorization.exchange_called is False


def test_exchange_submit_adapter_result_is_disabled_by_default():
    decision = _ready_exchange_submit_enablement_decision(_registration_preview())

    result = build_runtime_execution_exchange_submit_adapter_result(
        enablement_decision=decision,
        exchange_submit_adapter_enabled=False,
        now_ms=NOW_MS + 4,
    )

    assert (
        result.status
        == RuntimeExecutionExchangeSubmitAdapterResultStatus
        .EXCHANGE_SUBMIT_ADAPTER_DISABLED
    )
    assert "exchange_submit_adapter_disabled" in result.blockers
    assert result.duplicate_submit_lock_acquired is False
    assert result.order_lifecycle_submit_called is False
    assert result.exchange_order_submitted is False
    assert result.exchange_called is False


def test_exchange_submit_adapter_result_records_not_implemented_after_lock():
    decision = _ready_exchange_submit_enablement_decision(_registration_preview())

    result = build_runtime_execution_exchange_submit_adapter_result(
        enablement_decision=decision,
        exchange_submit_adapter_enabled=True,
        duplicate_submit_lock_acquired=True,
        now_ms=NOW_MS + 4,
    )

    assert (
        result.status
        == RuntimeExecutionExchangeSubmitAdapterResultStatus
        .EXCHANGE_SUBMIT_ADAPTER_NOT_IMPLEMENTED
    )
    assert "exchange_submit_adapter_not_implemented" in result.blockers
    assert result.local_order_ids == [
        "runtime-order-draft-auth-1-entry",
        "runtime-order-draft-auth-1-sl",
    ]
    assert result.entry_order_id == "runtime-order-draft-auth-1-entry"
    assert result.submit_request_count == 2
    assert result.entry_submit_request_count == 1
    assert result.protection_submit_request_count == 1
    assert result.duplicate_submit_lock_acquired is True
    assert result.exchange_submit_adapter_implemented is False
    assert result.order_lifecycle_submit_called is False
    assert result.execution_intent_status_changed is False
    assert result.exchange_order_submitted is False
    assert result.exchange_called is False


@pytest.mark.asyncio
async def test_service_returns_intent_local_order_binding_without_saving_intent():
    preview = _registration_preview()
    lifecycle = _Lifecycle()
    adapter_result_repo = _AdapterResultRepo()
    intent_repo = _IntentRepo(_runtime_intent(preview))
    service = _service_with_preview(
        preview,
        lifecycle=lifecycle,
        adapter_result_repo=adapter_result_repo,
        intent_repo=intent_repo,
    )
    decision = _ready_enablement_decision(preview)
    await service.order_lifecycle_adapter_result_for_authorization(
        "auth-1",
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        local_registration_enablement_decision=decision,
    )

    binding = await service.intent_local_order_binding_for_authorization("auth-1")

    assert (
        binding.status
        == RuntimeExecutionIntentLocalOrderBindingStatus
        .READY_FOR_EXCHANGE_SUBMIT_DESIGN
    )
    assert binding.entry_order_id == "runtime-order-draft-auth-1-entry"
    assert intent_repo.saved == []
    assert intent_repo.intent.order_id is None
    assert binding.execution_intent_status_changed is False


@pytest.mark.asyncio
async def test_service_returns_exchange_submit_packet_preview_without_submit():
    preview = _registration_preview()
    lifecycle = _Lifecycle()
    adapter_result_repo = _AdapterResultRepo()
    intent_repo = _IntentRepo(_runtime_intent(preview))
    service = _service_with_preview(
        preview,
        lifecycle=lifecycle,
        adapter_result_repo=adapter_result_repo,
        intent_repo=intent_repo,
    )
    decision = _ready_enablement_decision(preview)
    await service.order_lifecycle_adapter_result_for_authorization(
        "auth-1",
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        local_registration_enablement_decision=decision,
    )

    packet = await service.exchange_submit_packet_preview_for_authorization("auth-1")

    assert (
        packet.status
        == RuntimeExecutionExchangeSubmitPacketPreviewStatus
        .READY_FOR_EXCHANGE_SUBMIT_ADAPTER_DESIGN
    )
    assert packet.entry_order_id == "runtime-order-draft-auth-1-entry"
    assert packet.protection_order_ids == ["runtime-order-draft-auth-1-sl"]
    assert len(lifecycle.calls) == 2
    assert intent_repo.saved == []
    assert intent_repo.intent.order_id is None
    assert packet.execution_intent_status_changed is False
    assert packet.order_lifecycle_submit_called is False
    assert packet.exchange_order_submitted is False
    assert packet.exchange_called is False


@pytest.mark.asyncio
async def test_service_returns_exchange_submit_enablement_without_submit():
    preview = _registration_preview()
    lifecycle = _Lifecycle()
    adapter_result_repo = _AdapterResultRepo()
    intent_repo = _IntentRepo(_runtime_intent(preview))
    service = _service_with_preview(
        preview,
        lifecycle=lifecycle,
        adapter_result_repo=adapter_result_repo,
        intent_repo=intent_repo,
    )
    decision = _ready_enablement_decision(preview)
    await service.order_lifecycle_adapter_result_for_authorization(
        "auth-1",
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        local_registration_enablement_decision=decision,
    )

    exchange_decision = (
        await service.exchange_submit_enablement_decision_for_authorization(
            "auth-1",
            trusted_submit_fact_snapshot_id="trusted-submit-facts-intent-1",
            submit_idempotency_policy_id="runtime-submit-idempotency-auth-1",
            attempt_outcome_policy_id="runtime-attempt-outcome-policy-auth-1",
            protection_creation_failure_policy_id=(
                "protection-failure-policy-intent-1"
            ),
            local_registration_enablement_decision_id=decision.decision_id,
            owner_real_submit_authorization_id="owner-real-submit-auth-1",
            order_lifecycle_submit_enablement_id=(
                "order-lifecycle-submit-enable-1"
            ),
            exchange_submit_adapter_enablement_id=(
                "exchange-submit-adapter-enable-1"
            ),
            exchange_submit_action_authorization_id="exchange-submit-action-1",
            deployment_readiness_evidence_id="runtime-exchange-gateway-readiness-1",
        )
    )

    assert (
        exchange_decision.status
        == RuntimeExecutionExchangeSubmitGateStatus.READY_FOR_EXCHANGE_SUBMIT_ACTION
    )
    assert exchange_decision.exchange_called is False
    assert exchange_decision.order_lifecycle_submit_called is False
    assert exchange_decision.execution_intent_status_changed is False
    assert intent_repo.saved == []
    assert len(lifecycle.calls) == 2


@pytest.mark.asyncio
async def test_service_blocks_exchange_submit_enablement_without_action_evidence():
    preview = _registration_preview()
    lifecycle = _Lifecycle()
    adapter_result_repo = _AdapterResultRepo()
    intent_repo = _IntentRepo(_runtime_intent(preview))
    missing_action_repo = _ExchangeSubmitActionAuthorizationRepo(
        authorization_id=preview.authorization_id,
        execution_intent_id=preview.execution_intent_id,
        runtime_instance_id=preview.runtime_instance_id,
        symbol=preview.symbol,
        local_registration_enablement_decision_id=(
            "runtime-local-registration-enablement-auth-1"
        ),
        missing=True,
    )
    service = _service_with_preview(
        preview,
        lifecycle=lifecycle,
        adapter_result_repo=adapter_result_repo,
        intent_repo=intent_repo,
        exchange_submit_action_authorization_repo=missing_action_repo,
    )
    local_decision = _ready_enablement_decision(preview)
    await service.order_lifecycle_adapter_result_for_authorization(
        "auth-1",
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        local_registration_enablement_decision=local_decision,
    )

    exchange_decision = (
        await service.exchange_submit_enablement_decision_for_authorization(
            "auth-1",
            trusted_submit_fact_snapshot_id="trusted-submit-facts-intent-1",
            submit_idempotency_policy_id="runtime-submit-idempotency-auth-1",
            attempt_outcome_policy_id="runtime-attempt-outcome-policy-auth-1",
            protection_creation_failure_policy_id=(
                "protection-failure-policy-intent-1"
            ),
            local_registration_enablement_decision_id=local_decision.decision_id,
            owner_real_submit_authorization_id="owner-real-submit-auth-1",
            order_lifecycle_submit_enablement_id=(
                "order-lifecycle-submit-enable-1"
            ),
            exchange_submit_adapter_enablement_id=(
                "exchange-submit-adapter-enable-1"
            ),
            exchange_submit_action_authorization_id="exchange-submit-action-1",
            deployment_readiness_evidence_id="runtime-exchange-gateway-readiness-1",
        )
    )

    assert exchange_decision.status == RuntimeExecutionExchangeSubmitGateStatus.BLOCKED
    assert "exchange_submit_action_authorization_not_found" in (
        exchange_decision.blockers
    )
    assert exchange_decision.exchange_called is False
    assert intent_repo.saved == []


@pytest.mark.asyncio
async def test_service_blocks_exchange_submit_enablement_with_expired_action_evidence():
    preview = _registration_preview()
    lifecycle = _Lifecycle()
    adapter_result_repo = _AdapterResultRepo()
    intent_repo = _IntentRepo(_runtime_intent(preview))
    expired_action_repo = _ExchangeSubmitActionAuthorizationRepo(
        authorization_id=preview.authorization_id,
        execution_intent_id=preview.execution_intent_id,
        runtime_instance_id=preview.runtime_instance_id,
        symbol=preview.symbol,
        local_registration_enablement_decision_id=(
            "runtime-local-registration-enablement-auth-1"
        ),
        expires_at_ms=1,
    )
    service = _service_with_preview(
        preview,
        lifecycle=lifecycle,
        adapter_result_repo=adapter_result_repo,
        intent_repo=intent_repo,
        exchange_submit_action_authorization_repo=expired_action_repo,
    )
    local_decision = _ready_enablement_decision(preview)
    await service.order_lifecycle_adapter_result_for_authorization(
        "auth-1",
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        local_registration_enablement_decision=local_decision,
    )

    exchange_decision = (
        await service.exchange_submit_enablement_decision_for_authorization(
            "auth-1",
            trusted_submit_fact_snapshot_id="trusted-submit-facts-intent-1",
            submit_idempotency_policy_id="runtime-submit-idempotency-auth-1",
            attempt_outcome_policy_id="runtime-attempt-outcome-policy-auth-1",
            protection_creation_failure_policy_id=(
                "protection-failure-policy-intent-1"
            ),
            local_registration_enablement_decision_id=local_decision.decision_id,
            owner_real_submit_authorization_id="owner-real-submit-auth-1",
            order_lifecycle_submit_enablement_id=(
                "order-lifecycle-submit-enable-1"
            ),
            exchange_submit_adapter_enablement_id=(
                "exchange-submit-adapter-enable-1"
            ),
            exchange_submit_action_authorization_id="exchange-submit-action-1",
            deployment_readiness_evidence_id="runtime-exchange-gateway-readiness-1",
        )
    )

    assert exchange_decision.status == RuntimeExecutionExchangeSubmitGateStatus.BLOCKED
    assert "exchange_submit_action_authorization_expired" in (
        exchange_decision.blockers
    )
    assert exchange_decision.exchange_called is False
    assert exchange_decision.order_lifecycle_submit_called is False
    assert intent_repo.saved == []


@pytest.mark.asyncio
async def test_service_blocks_exchange_submit_enablement_with_readiness_scope_mismatch():
    preview = _registration_preview()
    lifecycle = _Lifecycle()
    adapter_result_repo = _AdapterResultRepo()
    intent_repo = _IntentRepo(_runtime_intent(preview))
    scoped_action_repo = _ExchangeSubmitActionAuthorizationRepo(
        authorization_id=preview.authorization_id,
        execution_intent_id=preview.execution_intent_id,
        runtime_instance_id=preview.runtime_instance_id,
        symbol=preview.symbol,
        local_registration_enablement_decision_id=(
            "runtime-local-registration-enablement-auth-1"
        ),
        deployment_readiness_evidence_id="runtime-exchange-gateway-readiness-A",
    )
    service = _service_with_preview(
        preview,
        lifecycle=lifecycle,
        adapter_result_repo=adapter_result_repo,
        intent_repo=intent_repo,
        exchange_submit_action_authorization_repo=scoped_action_repo,
    )
    local_decision = _ready_enablement_decision(preview)
    await service.order_lifecycle_adapter_result_for_authorization(
        "auth-1",
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        local_registration_enablement_decision=local_decision,
    )

    exchange_decision = (
        await service.exchange_submit_enablement_decision_for_authorization(
            "auth-1",
            trusted_submit_fact_snapshot_id="trusted-submit-facts-intent-1",
            submit_idempotency_policy_id="runtime-submit-idempotency-auth-1",
            attempt_outcome_policy_id="runtime-attempt-outcome-policy-auth-1",
            protection_creation_failure_policy_id=(
                "protection-failure-policy-intent-1"
            ),
            local_registration_enablement_decision_id=local_decision.decision_id,
            owner_real_submit_authorization_id="owner-real-submit-auth-1",
            order_lifecycle_submit_enablement_id=(
                "order-lifecycle-submit-enable-1"
            ),
            exchange_submit_adapter_enablement_id=(
                "exchange-submit-adapter-enable-1"
            ),
            exchange_submit_action_authorization_id="exchange-submit-action-1",
            deployment_readiness_evidence_id="runtime-exchange-gateway-readiness-B",
        )
    )

    assert exchange_decision.status == RuntimeExecutionExchangeSubmitGateStatus.BLOCKED
    assert (
        "exchange_submit_action_authorization_deployment_readiness_mismatch"
        in exchange_decision.blockers
    )
    assert exchange_decision.exchange_called is False
    assert exchange_decision.order_lifecycle_submit_called is False
    assert intent_repo.saved == []


@pytest.mark.asyncio
async def test_service_blocks_exchange_submit_enablement_with_unsafe_trusted_submit_facts():
    preview = _registration_preview()
    lifecycle = _Lifecycle()
    adapter_result_repo = _AdapterResultRepo()
    intent_repo = _IntentRepo(_runtime_intent(preview))
    service = _service_with_preview(
        preview,
        lifecycle=lifecycle,
        adapter_result_repo=adapter_result_repo,
        intent_repo=intent_repo,
    )
    service._trusted_submit_facts_repository = _TrustedSubmitFactsRepo(
        execution_intent_id=preview.execution_intent_id,
        runtime_instance_id=preview.runtime_instance_id,
        symbol="ETH/USDT:USDT",
        facts_fresh_enough=False,
        read_only_sources_only=False,
        owner_supplied_allow_facts_rejected=False,
        missing_or_stale_facts_block=False,
        not_execution_authority=False,
        order_created=True,
        exchange_called=True,
        order_lifecycle_called=True,
    )
    local_decision = _ready_enablement_decision(preview)
    await service.order_lifecycle_adapter_result_for_authorization(
        "auth-1",
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        local_registration_enablement_decision=local_decision,
    )

    exchange_decision = (
        await service.exchange_submit_enablement_decision_for_authorization(
            "auth-1",
            trusted_submit_fact_snapshot_id="trusted-submit-facts-intent-1",
            submit_idempotency_policy_id="runtime-submit-idempotency-auth-1",
            attempt_outcome_policy_id="runtime-attempt-outcome-policy-auth-1",
            protection_creation_failure_policy_id=(
                "protection-failure-policy-intent-1"
            ),
            local_registration_enablement_decision_id=local_decision.decision_id,
            owner_real_submit_authorization_id="owner-real-submit-auth-1",
            order_lifecycle_submit_enablement_id=(
                "order-lifecycle-submit-enable-1"
            ),
            exchange_submit_adapter_enablement_id=(
                "exchange-submit-adapter-enable-1"
            ),
            exchange_submit_action_authorization_id="exchange-submit-action-1",
            deployment_readiness_evidence_id="runtime-exchange-gateway-readiness-1",
        )
    )

    assert exchange_decision.status == RuntimeExecutionExchangeSubmitGateStatus.BLOCKED
    assert "trusted_submit_fact_snapshot_symbol_mismatch" in exchange_decision.blockers
    assert (
        "trusted_submit_fact_snapshot_owner_allow_not_rejected"
        in exchange_decision.blockers
    )
    assert (
        "trusted_submit_fact_snapshot_sources_not_read_only"
        in exchange_decision.blockers
    )
    assert (
        "trusted_submit_fact_snapshot_not_fresh_enough"
        in exchange_decision.blockers
    )
    assert "trusted_submit_fact_snapshot_created_order" in exchange_decision.blockers
    assert "trusted_submit_fact_snapshot_called_exchange" in exchange_decision.blockers
    assert (
        "trusted_submit_fact_snapshot_called_order_lifecycle"
        in exchange_decision.blockers
    )
    assert exchange_decision.exchange_called is False
    assert exchange_decision.order_lifecycle_submit_called is False
    assert intent_repo.saved == []


@pytest.mark.asyncio
async def test_service_exchange_submit_adapter_result_replays_not_implemented():
    preview = _registration_preview()
    lifecycle = _Lifecycle()
    adapter_result_repo = _AdapterResultRepo()
    exchange_result_repo = _ExchangeSubmitAdapterResultRepo()
    intent_repo = _IntentRepo(_runtime_intent(preview))
    service = _service_with_preview(
        preview,
        lifecycle=lifecycle,
        adapter_result_repo=adapter_result_repo,
        exchange_submit_adapter_result_repo=exchange_result_repo,
        intent_repo=intent_repo,
    )
    local_decision = _ready_enablement_decision(preview)
    await service.order_lifecycle_adapter_result_for_authorization(
        "auth-1",
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        local_registration_enablement_decision=local_decision,
    )
    exchange_decision = (
        await service.exchange_submit_enablement_decision_for_authorization(
            "auth-1",
            trusted_submit_fact_snapshot_id="trusted-submit-facts-intent-1",
            submit_idempotency_policy_id="runtime-submit-idempotency-auth-1",
            attempt_outcome_policy_id="runtime-attempt-outcome-policy-auth-1",
            protection_creation_failure_policy_id=(
                "protection-failure-policy-intent-1"
            ),
            local_registration_enablement_decision_id=local_decision.decision_id,
            owner_real_submit_authorization_id="owner-real-submit-auth-1",
            order_lifecycle_submit_enablement_id=(
                "order-lifecycle-submit-enable-1"
            ),
            exchange_submit_adapter_enablement_id=(
                "exchange-submit-adapter-enable-1"
            ),
            exchange_submit_action_authorization_id="exchange-submit-action-1",
            deployment_readiness_evidence_id="runtime-exchange-gateway-readiness-1",
        )
    )

    first = await service.exchange_submit_adapter_result_for_authorization(
        "auth-1",
        exchange_submit_adapter_enabled=True,
        exchange_submit_enablement_decision=exchange_decision,
    )
    second = await service.exchange_submit_adapter_result_for_authorization(
        "auth-1",
        exchange_submit_adapter_enabled=True,
        exchange_submit_enablement_decision=exchange_decision,
    )

    assert (
        first.status
        == RuntimeExecutionExchangeSubmitAdapterResultStatus
        .EXCHANGE_SUBMIT_ADAPTER_NOT_IMPLEMENTED
    )
    assert second == first
    assert exchange_result_repo.acquire_calls == 2
    assert exchange_result_repo.complete_calls == 1
    assert first.duplicate_submit_lock_acquired is True
    assert first.exchange_submit_action_authorization_id == "exchange-submit-action-1"
    assert first.exchange_submit_adapter_implemented is False
    assert first.order_lifecycle_submit_called is False
    assert first.exchange_order_submitted is False
    assert first.exchange_called is False
    assert intent_repo.saved == []
    assert len(lifecycle.calls) == 2


@pytest.mark.asyncio
async def test_service_exchange_submit_adapter_result_recovers_acquired_lock():
    preview = _registration_preview()
    lifecycle = _Lifecycle()
    adapter_result_repo = _AdapterResultRepo()
    exchange_result_repo = _ExchangeSubmitAdapterResultRepo()
    intent_repo = _IntentRepo(_runtime_intent(preview))
    service = _service_with_preview(
        preview,
        lifecycle=lifecycle,
        adapter_result_repo=adapter_result_repo,
        exchange_submit_adapter_result_repo=exchange_result_repo,
        intent_repo=intent_repo,
    )
    local_decision = _ready_enablement_decision(preview)
    await service.order_lifecycle_adapter_result_for_authorization(
        "auth-1",
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        local_registration_enablement_decision=local_decision,
    )
    exchange_decision = (
        await service.exchange_submit_enablement_decision_for_authorization(
            "auth-1",
            trusted_submit_fact_snapshot_id="trusted-submit-facts-intent-1",
            submit_idempotency_policy_id="runtime-submit-idempotency-auth-1",
            attempt_outcome_policy_id="runtime-attempt-outcome-policy-auth-1",
            protection_creation_failure_policy_id=(
                "protection-failure-policy-intent-1"
            ),
            local_registration_enablement_decision_id=local_decision.decision_id,
            owner_real_submit_authorization_id="owner-real-submit-auth-1",
            order_lifecycle_submit_enablement_id=(
                "order-lifecycle-submit-enable-1"
            ),
            exchange_submit_adapter_enablement_id=(
                "exchange-submit-adapter-enable-1"
            ),
            exchange_submit_action_authorization_id="exchange-submit-action-1",
            deployment_readiness_evidence_id="runtime-exchange-gateway-readiness-1",
        )
    )
    exchange_result_repo.stored = (
        build_runtime_execution_exchange_submit_adapter_lock_result(
            enablement_decision=exchange_decision,
            now_ms=NOW_MS + 4,
        )
    )

    recovered = await service.exchange_submit_adapter_result_for_authorization(
        "auth-1",
        exchange_submit_adapter_enabled=True,
        exchange_submit_enablement_decision=exchange_decision,
    )

    assert (
        recovered.status
        == RuntimeExecutionExchangeSubmitAdapterResultStatus
        .EXCHANGE_SUBMIT_ADAPTER_NOT_IMPLEMENTED
    )
    assert "exchange_submit_adapter_not_implemented" in recovered.blockers
    assert (
        "recovered_exchange_submit_lock_acquired_state"
        in recovered.warnings
    )
    assert exchange_result_repo.acquire_calls == 1
    assert exchange_result_repo.complete_calls == 1
    assert recovered.duplicate_submit_lock_acquired is True
    assert recovered.exchange_submit_adapter_implemented is False
    assert recovered.order_lifecycle_submit_called is False
    assert recovered.exchange_order_submitted is False
    assert recovered.exchange_called is False
    assert intent_repo.saved == []
    assert len(lifecycle.calls) == 2


@pytest.mark.asyncio
async def test_service_duplicate_submit_replay_proof_ready_without_execution():
    preview = _registration_preview()
    lifecycle = _Lifecycle()
    adapter_result_repo = _AdapterResultRepo()
    exchange_result_repo = _ExchangeSubmitAdapterResultRepo()
    execution_result_repo = _ExchangeSubmitExecutionResultRepo()
    intent_repo = _IntentRepo(_runtime_intent(preview))
    service = _service_with_preview(
        preview,
        lifecycle=lifecycle,
        adapter_result_repo=adapter_result_repo,
        exchange_submit_adapter_result_repo=exchange_result_repo,
        exchange_submit_execution_result_repo=execution_result_repo,
        intent_repo=intent_repo,
    )
    local_decision = _ready_enablement_decision(preview)
    await service.order_lifecycle_adapter_result_for_authorization(
        "auth-1",
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        local_registration_enablement_decision=local_decision,
    )
    exchange_decision = (
        await service.exchange_submit_enablement_decision_for_authorization(
            "auth-1",
            trusted_submit_fact_snapshot_id="trusted-submit-facts-intent-1",
            submit_idempotency_policy_id="runtime-submit-idempotency-auth-1",
            attempt_outcome_policy_id="runtime-attempt-outcome-policy-auth-1",
            protection_creation_failure_policy_id=(
                "protection-failure-policy-intent-1"
            ),
            local_registration_enablement_decision_id=local_decision.decision_id,
            owner_real_submit_authorization_id="owner-real-submit-auth-1",
            order_lifecycle_submit_enablement_id=(
                "order-lifecycle-submit-enable-1"
            ),
            exchange_submit_adapter_enablement_id=(
                "exchange-submit-adapter-enable-1"
            ),
            exchange_submit_action_authorization_id="exchange-submit-action-1",
            deployment_readiness_evidence_id="runtime-exchange-gateway-readiness-1",
        )
    )

    proof = await service.duplicate_submit_replay_proof_for_authorization(
        "auth-1",
        exchange_submit_enablement_decision=exchange_decision,
        submit_idempotency_policy_id="runtime-submit-idempotency-auth-1",
    )

    assert proof.status == (
        RuntimeExecutionDuplicateSubmitReplayProofStatus
        .READY_FOR_FIRST_REAL_SUBMIT_REPLAY_GUARD
    )
    assert proof.blockers == []
    assert proof.replay_lock_key == "auth-1"
    assert proof.adapter_result_repository_available is True
    assert proof.execution_result_repository_available is True
    assert proof.first_submit_not_already_executed is True
    assert exchange_result_repo.acquire_calls == 0
    assert execution_result_repo.acquire_calls == 0
    assert proof.exchange_called is False
    assert proof.order_lifecycle_called is False
    assert intent_repo.saved == []


@pytest.mark.asyncio
async def test_service_duplicate_submit_replay_proof_blocks_existing_execution_result():
    preview = _registration_preview()
    lifecycle = _Lifecycle()
    adapter_result_repo = _AdapterResultRepo()
    exchange_result_repo = _ExchangeSubmitAdapterResultRepo()
    execution_result_repo = _ExchangeSubmitExecutionResultRepo()
    intent_repo = _IntentRepo(_runtime_intent(preview))
    service = _service_with_preview(
        preview,
        lifecycle=lifecycle,
        adapter_result_repo=adapter_result_repo,
        exchange_submit_adapter_result_repo=exchange_result_repo,
        exchange_submit_execution_result_repo=execution_result_repo,
        intent_repo=intent_repo,
    )
    local_decision = _ready_enablement_decision(preview)
    await service.order_lifecycle_adapter_result_for_authorization(
        "auth-1",
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        local_registration_enablement_decision=local_decision,
    )
    exchange_decision = (
        await service.exchange_submit_enablement_decision_for_authorization(
            "auth-1",
            trusted_submit_fact_snapshot_id="trusted-submit-facts-intent-1",
            submit_idempotency_policy_id="runtime-submit-idempotency-auth-1",
            attempt_outcome_policy_id="runtime-attempt-outcome-policy-auth-1",
            protection_creation_failure_policy_id=(
                "protection-failure-policy-intent-1"
            ),
            local_registration_enablement_decision_id=local_decision.decision_id,
            owner_real_submit_authorization_id="owner-real-submit-auth-1",
            order_lifecycle_submit_enablement_id=(
                "order-lifecycle-submit-enable-1"
            ),
            exchange_submit_adapter_enablement_id=(
                "exchange-submit-adapter-enable-1"
            ),
            exchange_submit_action_authorization_id="exchange-submit-action-1",
            deployment_readiness_evidence_id="runtime-exchange-gateway-readiness-1",
        )
    )
    packet_preview = await service.exchange_submit_packet_preview_for_authorization(
        "auth-1"
    )
    execution_result_repo.stored = build_runtime_exchange_submit_execution_lock_result(
        enablement_decision=exchange_decision,
        packet_preview=packet_preview,
        now_ms=NOW_MS + 4,
    )

    proof = await service.duplicate_submit_replay_proof_for_authorization(
        "auth-1",
        exchange_submit_enablement_decision=exchange_decision,
        submit_idempotency_policy_id="runtime-submit-idempotency-auth-1",
    )

    assert proof.status == RuntimeExecutionDuplicateSubmitReplayProofStatus.BLOCKED
    assert "exchange_submit_execution_result_already_exists_replay_only" in (
        proof.blockers
    )
    assert proof.existing_execution_result_id == (
        "runtime-exchange-submit-execution-result-auth-1"
    )
    assert proof.first_submit_not_already_executed is False
    assert execution_result_repo.acquire_calls == 0
    assert proof.exchange_called is False
    assert proof.order_lifecycle_called is False
    assert intent_repo.saved == []


@pytest.mark.asyncio
async def test_service_submit_prerequisite_evidence_proof_ready_without_execution():
    preview = _registration_preview()
    lifecycle = _Lifecycle()
    intent_repo = _IntentRepo(_runtime_intent(preview))
    service = _service_with_preview(
        preview,
        lifecycle=lifecycle,
        intent_repo=intent_repo,
    )
    exchange_decision = _ready_exchange_submit_enablement_decision(preview)

    proof = await service.submit_prerequisite_evidence_proof_for_authorization(
        "auth-1",
        exchange_submit_enablement_decision=exchange_decision,
        trusted_submit_fact_snapshot_id="trusted-submit-facts-intent-1",
        attempt_outcome_policy_id="runtime-attempt-outcome-policy-auth-1",
        protection_creation_failure_policy_id="protection-failure-policy-intent-1",
    )

    assert proof.status == (
        RuntimeExecutionSubmitPrerequisiteEvidenceProofStatus
        .READY_FOR_FIRST_REAL_SUBMIT_PREREQUISITE_REVIEW
    )
    assert proof.blockers == []
    assert proof.trusted_submit_facts_ready is True
    assert proof.trusted_submit_facts_fresh_enough is True
    assert proof.attempt_outcome_policy_ready is True
    assert proof.attempt_consumed_on_any_fill is True
    assert proof.budget_held_until_position_resolved is True
    assert proof.protection_failure_policy_ready is True
    assert proof.protection_failure_blocks_new_entries is True
    assert proof.protection_failure_marks_unprotected is True
    assert proof.exchange_called is False
    assert proof.order_lifecycle_called is False
    assert intent_repo.saved == []
    assert lifecycle.calls == []


@pytest.mark.asyncio
async def test_service_submit_prerequisite_evidence_proof_blocks_stale_facts():
    preview = _registration_preview()
    lifecycle = _Lifecycle()
    intent_repo = _IntentRepo(_runtime_intent(preview))
    service = _service_with_preview(
        preview,
        lifecycle=lifecycle,
        intent_repo=intent_repo,
        trusted_submit_facts_repo=_TrustedSubmitFactsRepo(
            execution_intent_id=preview.execution_intent_id,
            runtime_instance_id=preview.runtime_instance_id,
            symbol=preview.symbol,
            facts_fresh_enough=False,
        ),
    )
    exchange_decision = _ready_exchange_submit_enablement_decision(preview)

    proof = await service.submit_prerequisite_evidence_proof_for_authorization(
        "auth-1",
        exchange_submit_enablement_decision=exchange_decision,
        trusted_submit_fact_snapshot_id="trusted-submit-facts-intent-1",
        attempt_outcome_policy_id="runtime-attempt-outcome-policy-auth-1",
        protection_creation_failure_policy_id="protection-failure-policy-intent-1",
    )

    assert proof.status == RuntimeExecutionSubmitPrerequisiteEvidenceProofStatus.BLOCKED
    assert "trusted_submit_fact_snapshot_not_fresh_enough" in proof.blockers
    assert proof.trusted_submit_facts_ready is True
    assert proof.trusted_submit_facts_fresh_enough is False
    assert proof.exchange_called is False
    assert proof.order_lifecycle_called is False
    assert intent_repo.saved == []
    assert lifecycle.calls == []


@pytest.mark.asyncio
async def test_service_submit_rehearsal_is_ready_for_owner_review_without_submit():
    context = await _ready_exchange_submit_execution_context()

    rehearsal = await context.service.submit_rehearsal_for_authorization(
        "auth-1",
        exchange_submit_enablement_decision=context.exchange_decision,
    )

    assert (
        rehearsal.status
        == RuntimeExecutionSubmitRehearsalStatus
        .READY_FOR_OWNER_LIVE_ACTION_REVIEW
    )
    assert rehearsal.exchange_submit_enablement_ready is True
    assert rehearsal.runtime_gateway_readiness_ready is True
    assert rehearsal.no_blocking_recovery_tasks is True
    assert rehearsal.not_live_action_authorization is True
    assert rehearsal.not_exchange_submit_authority is True
    assert rehearsal.not_order_lifecycle_authority is True
    assert rehearsal.exchange_called is False
    assert rehearsal.exchange_order_submitted is False
    assert rehearsal.order_lifecycle_called is False
    assert context.gateway.calls == []
    assert context.intent_repo.saved == []


@pytest.mark.asyncio
async def test_service_submit_rehearsal_blocks_open_recovery_task():
    context = await _ready_exchange_submit_execution_context()
    await context.recovery_repo.create_task(
        task_id="rt-ex-submit-open-recovery",
        intent_id="older-intent",
        symbol=context.symbol,
        recovery_type="exchange_submit_protection_fail",
        related_order_id="runtime-order-draft-old-sl",
        related_exchange_order_id="ex-runtime-order-draft-old-entry",
        error_message="older protection submit failed",
        context_payload={
            "block_new_entries_until_resolved": True,
            "require_owner_recovery_review": True,
        },
    )

    rehearsal = await context.service.submit_rehearsal_for_authorization(
        "auth-1",
        exchange_submit_enablement_decision=context.exchange_decision,
    )

    assert rehearsal.status == RuntimeExecutionSubmitRehearsalStatus.BLOCKED
    assert "execution_recovery_blocking_tasks_open" in rehearsal.blockers
    assert (
        "execution_recovery_blocking_task:rt-ex-submit-open-recovery"
        in rehearsal.warnings
    )
    assert rehearsal.no_blocking_recovery_tasks is False
    assert rehearsal.exchange_called is False
    assert rehearsal.exchange_order_submitted is False
    assert rehearsal.order_lifecycle_called is False
    assert context.gateway.calls == []
    assert context.intent_repo.saved == []


@pytest.mark.asyncio
async def test_service_exchange_submit_execution_disabled_does_not_call_gateway():
    preview = _registration_preview()
    lifecycle = _Lifecycle()
    adapter_result_repo = _AdapterResultRepo()
    gateway = _ExchangeGateway()
    intent_repo = _IntentRepo(_runtime_intent(preview))
    service = _service_with_preview(
        preview,
        lifecycle=lifecycle,
        adapter_result_repo=adapter_result_repo,
        exchange_gateway=gateway,
        exchange_gateway_readiness_repo=_ExchangeGatewayReadinessRepo(),
        intent_repo=intent_repo,
    )
    local_decision = _ready_enablement_decision(preview)
    await service.order_lifecycle_adapter_result_for_authorization(
        "auth-1",
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        local_registration_enablement_decision=local_decision,
    )
    exchange_decision = (
        await service.exchange_submit_enablement_decision_for_authorization(
            "auth-1",
            trusted_submit_fact_snapshot_id="trusted-submit-facts-intent-1",
            submit_idempotency_policy_id="runtime-submit-idempotency-auth-1",
            attempt_outcome_policy_id="runtime-attempt-outcome-policy-auth-1",
            protection_creation_failure_policy_id=(
                "protection-failure-policy-intent-1"
            ),
            local_registration_enablement_decision_id=local_decision.decision_id,
            owner_real_submit_authorization_id="owner-real-submit-auth-1",
            order_lifecycle_submit_enablement_id=(
                "order-lifecycle-submit-enable-1"
            ),
            exchange_submit_adapter_enablement_id=(
                "exchange-submit-adapter-enable-1"
            ),
            exchange_submit_action_authorization_id="exchange-submit-action-1",
            deployment_readiness_evidence_id="runtime-exchange-gateway-readiness-1",
        )
    )

    result = await service.exchange_submit_execution_result_for_authorization(
        "auth-1",
        exchange_submit_execution_enabled=False,
        exchange_submit_enablement_decision=exchange_decision,
    )

    assert result.status == (
        RuntimeExecutionExchangeSubmitExecutionStatus
        .EXCHANGE_SUBMIT_EXECUTION_DISABLED
    )
    assert gateway.calls == []
    assert result.exchange_called is False
    assert result.exchange_order_submitted is False
    assert result.order_lifecycle_submit_called is False
    assert intent_repo.saved == []


@pytest.mark.asyncio
async def test_service_exchange_submit_execution_blocks_without_replay_repository():
    preview = _registration_preview()
    lifecycle = _Lifecycle()
    adapter_result_repo = _AdapterResultRepo()
    gateway = _ExchangeGateway()
    intent_repo = _IntentRepo(_runtime_intent(preview))
    service = _service_with_preview(
        preview,
        lifecycle=lifecycle,
        adapter_result_repo=adapter_result_repo,
        exchange_gateway=gateway,
        exchange_gateway_readiness_repo=_ExchangeGatewayReadinessRepo(),
        intent_repo=intent_repo,
    )
    local_decision = _ready_enablement_decision(preview)
    await service.order_lifecycle_adapter_result_for_authorization(
        "auth-1",
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        local_registration_enablement_decision=local_decision,
    )
    exchange_decision = (
        await service.exchange_submit_enablement_decision_for_authorization(
            "auth-1",
            trusted_submit_fact_snapshot_id="trusted-submit-facts-intent-1",
            submit_idempotency_policy_id="runtime-submit-idempotency-auth-1",
            attempt_outcome_policy_id="runtime-attempt-outcome-policy-auth-1",
            protection_creation_failure_policy_id=(
                "protection-failure-policy-intent-1"
            ),
            local_registration_enablement_decision_id=local_decision.decision_id,
            owner_real_submit_authorization_id="owner-real-submit-auth-1",
            order_lifecycle_submit_enablement_id=(
                "order-lifecycle-submit-enable-1"
            ),
            exchange_submit_adapter_enablement_id=(
                "exchange-submit-adapter-enable-1"
            ),
            exchange_submit_action_authorization_id="exchange-submit-action-1",
            deployment_readiness_evidence_id="runtime-exchange-gateway-readiness-1",
        )
    )

    result = await service.exchange_submit_execution_result_for_authorization(
        "auth-1",
        exchange_submit_execution_enabled=True,
        exchange_submit_enablement_decision=exchange_decision,
    )

    assert result.status == RuntimeExecutionExchangeSubmitExecutionStatus.BLOCKED
    assert result.exchange_submit_execution_enabled is True
    assert (
        "runtime_exchange_submit_execution_result_repository_unavailable"
        in result.blockers
    )
    assert "execution_recovery_repository_unavailable" in result.blockers
    assert gateway.calls == []
    assert result.exchange_called is False
    assert result.order_lifecycle_submit_called is False
    assert intent_repo.saved == []


@pytest.mark.asyncio
async def test_service_exchange_submit_execution_blocks_without_readiness_id():
    context = await _ready_exchange_submit_execution_context(
        deployment_readiness_evidence_id=None,
    )

    result = (
        await context.service.exchange_submit_execution_result_for_authorization(
            "auth-1",
            exchange_submit_execution_enabled=True,
            exchange_submit_enablement_decision=context.exchange_decision,
        )
    )

    assert result.status == RuntimeExecutionExchangeSubmitExecutionStatus.BLOCKED
    assert "runtime_exchange_gateway_readiness_id_missing" in result.blockers
    assert "deployment_readiness_evidence_id_missing" in result.warnings
    assert context.gateway.calls == []
    assert result.exchange_called is False
    assert result.order_lifecycle_submit_called is False
    assert context.intent_repo.saved == []


@pytest.mark.asyncio
async def test_service_exchange_submit_execution_blocks_without_readiness_repo():
    context = await _ready_exchange_submit_execution_context(
        exchange_gateway_readiness_repo=None,
    )

    result = (
        await context.service.exchange_submit_execution_result_for_authorization(
            "auth-1",
            exchange_submit_execution_enabled=True,
            exchange_submit_enablement_decision=context.exchange_decision,
        )
    )

    assert result.status == RuntimeExecutionExchangeSubmitExecutionStatus.BLOCKED
    assert (
        "runtime_exchange_gateway_readiness_repository_unavailable"
        in result.blockers
    )
    assert context.gateway.calls == []
    assert result.exchange_called is False
    assert result.order_lifecycle_submit_called is False
    assert context.intent_repo.saved == []


@pytest.mark.asyncio
async def test_service_exchange_submit_execution_blocks_missing_readiness_record():
    context = await _ready_exchange_submit_execution_context(
        exchange_gateway_readiness_repo=_ExchangeGatewayReadinessRepo(
            not_found=True,
        ),
    )

    result = (
        await context.service.exchange_submit_execution_result_for_authorization(
            "auth-1",
            exchange_submit_execution_enabled=True,
            exchange_submit_enablement_decision=context.exchange_decision,
        )
    )

    assert result.status == RuntimeExecutionExchangeSubmitExecutionStatus.BLOCKED
    assert "runtime_exchange_gateway_readiness_not_found" in result.blockers
    assert context.gateway.calls == []
    assert result.exchange_called is False
    assert result.order_lifecycle_submit_called is False
    assert context.intent_repo.saved == []


@pytest.mark.asyncio
async def test_service_exchange_submit_execution_blocks_stale_gateway_readiness():
    context = await _ready_exchange_submit_execution_context(
        exchange_gateway_readiness_repo=_ExchangeGatewayReadinessRepo(
            created_at_ms=1,
        ),
    )

    result = (
        await context.service.exchange_submit_execution_result_for_authorization(
            "auth-1",
            exchange_submit_execution_enabled=True,
            exchange_submit_enablement_decision=context.exchange_decision,
        )
    )

    assert result.status == RuntimeExecutionExchangeSubmitExecutionStatus.BLOCKED
    assert "runtime_exchange_gateway_readiness_stale" in result.blockers
    assert context.gateway.calls == []
    assert result.exchange_called is False
    assert result.order_lifecycle_submit_called is False
    assert context.intent_repo.saved == []


@pytest.mark.asyncio
async def test_service_exchange_submit_execution_blocks_not_ready_readiness_record():
    context = await _ready_exchange_submit_execution_context(
        exchange_gateway_readiness_repo=_ExchangeGatewayReadinessRepo(
            status=RuntimeExecutionExchangeGatewayReadinessStatus.BLOCKED,
            blockers=["runtime_gateway_binding_not_enabled"],
            warnings=["gateway_not_injected_by_readiness_evidence"],
        ),
    )

    result = (
        await context.service.exchange_submit_execution_result_for_authorization(
            "auth-1",
            exchange_submit_execution_enabled=True,
            exchange_submit_enablement_decision=context.exchange_decision,
        )
    )

    assert result.status == RuntimeExecutionExchangeSubmitExecutionStatus.BLOCKED
    assert "runtime_exchange_gateway_readiness_not_ready" in result.blockers
    assert (
        "runtime_exchange_gateway_readiness:runtime_gateway_binding_not_enabled"
        in result.blockers
    )
    assert (
        "runtime_exchange_gateway_readiness:"
        "gateway_not_injected_by_readiness_evidence"
        in result.warnings
    )
    assert context.gateway.calls == []
    assert result.exchange_called is False
    assert result.order_lifecycle_submit_called is False
    assert context.intent_repo.saved == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("readiness_flags", "expected_blocker"),
    [
        (
            {"gateway_injected": True},
            "runtime_exchange_gateway_readiness_mutated_gateway",
        ),
        (
            {"exchange_called": True},
            "runtime_exchange_gateway_readiness_called_exchange",
        ),
        (
            {"exchange_order_submitted": True},
            "runtime_exchange_gateway_readiness_submitted_exchange_order",
        ),
        (
            {"order_lifecycle_submit_called": True},
            "runtime_exchange_gateway_readiness_called_lifecycle",
        ),
        (
            {"execution_intent_status_changed": True},
            "runtime_exchange_gateway_readiness_changed_intent_status",
        ),
    ],
)
async def test_service_exchange_submit_execution_blocks_readiness_side_effects(
    readiness_flags,
    expected_blocker,
):
    context = await _ready_exchange_submit_execution_context(
        exchange_gateway_readiness_repo=_ExchangeGatewayReadinessRepo(
            **readiness_flags,
        ),
    )

    result = (
        await context.service.exchange_submit_execution_result_for_authorization(
            "auth-1",
            exchange_submit_execution_enabled=True,
            exchange_submit_enablement_decision=context.exchange_decision,
        )
    )

    assert result.status == RuntimeExecutionExchangeSubmitExecutionStatus.BLOCKED
    assert expected_blocker in result.blockers
    assert context.gateway.calls == []
    assert result.exchange_called is False
    assert result.order_lifecycle_submit_called is False
    assert context.intent_repo.saved == []


@pytest.mark.asyncio
async def test_service_exchange_submit_execution_blocks_open_recovery_task_before_gateway():
    context = await _ready_exchange_submit_execution_context()
    await context.recovery_repo.create_task(
        task_id="rt-ex-submit-open-recovery",
        intent_id="older-intent",
        symbol=context.symbol,
        recovery_type="exchange_submit_protection_fail",
        related_order_id="runtime-order-draft-old-sl",
        related_exchange_order_id="ex-runtime-order-draft-old-entry",
        error_message="older protection submit failed",
        context_payload={
            "block_new_entries_until_resolved": True,
            "require_owner_recovery_review": True,
        },
    )

    result = await context.service.exchange_submit_execution_result_for_authorization(
        "auth-1",
        exchange_submit_execution_enabled=True,
        exchange_submit_enablement_decision=context.exchange_decision,
    )

    assert result.status == RuntimeExecutionExchangeSubmitExecutionStatus.BLOCKED
    assert "execution_recovery_blocking_task_open" in result.blockers
    assert (
        "execution_recovery_blocking_task:rt-ex-submit-open-recovery"
        in result.warnings
    )
    assert result.exchange_called is False
    assert result.exchange_order_submitted is False
    assert result.order_lifecycle_submit_called is False
    assert context.gateway.calls == []
    assert context.exchange_submit_execution_result_repo.acquire_calls == 0
    assert context.intent_repo.saved == []


@pytest.mark.asyncio
async def test_service_exchange_submit_execution_submits_entry_and_protection():
    preview = _registration_preview()
    lifecycle = _Lifecycle()
    adapter_result_repo = _AdapterResultRepo()
    execution_result_repo = _ExchangeSubmitExecutionResultRepo()
    recovery_repo = _ExecutionRecoveryRepo()
    gateway = _ExchangeGateway()
    intent_repo = _IntentRepo(_runtime_intent(preview))
    service = _service_with_preview(
        preview,
        lifecycle=lifecycle,
        adapter_result_repo=adapter_result_repo,
        exchange_submit_execution_result_repo=execution_result_repo,
        execution_recovery_repo=recovery_repo,
        exchange_gateway=gateway,
        exchange_gateway_readiness_repo=_ExchangeGatewayReadinessRepo(),
        intent_repo=intent_repo,
    )
    local_decision = _ready_enablement_decision(preview)
    await service.order_lifecycle_adapter_result_for_authorization(
        "auth-1",
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        local_registration_enablement_decision=local_decision,
    )
    exchange_decision = (
        await service.exchange_submit_enablement_decision_for_authorization(
            "auth-1",
            trusted_submit_fact_snapshot_id="trusted-submit-facts-intent-1",
            submit_idempotency_policy_id="runtime-submit-idempotency-auth-1",
            attempt_outcome_policy_id="runtime-attempt-outcome-policy-auth-1",
            protection_creation_failure_policy_id=(
                "protection-failure-policy-intent-1"
            ),
            local_registration_enablement_decision_id=local_decision.decision_id,
            owner_real_submit_authorization_id="owner-real-submit-auth-1",
            order_lifecycle_submit_enablement_id=(
                "order-lifecycle-submit-enable-1"
            ),
            exchange_submit_adapter_enablement_id=(
                "exchange-submit-adapter-enable-1"
            ),
            exchange_submit_action_authorization_id="exchange-submit-action-1",
            deployment_readiness_evidence_id="runtime-exchange-gateway-readiness-1",
        )
    )

    result = await service.exchange_submit_execution_result_for_authorization(
        "auth-1",
        exchange_submit_execution_enabled=True,
        exchange_submit_enablement_decision=exchange_decision,
    )

    assert result.status == (
        RuntimeExecutionExchangeSubmitExecutionStatus
        .EXCHANGE_SUBMIT_ORDERS_SUBMITTED
    )
    assert [call["client_order_id"] for call in gateway.calls] == [
        "runtime-order-draft-auth-1-entry",
        "runtime-order-draft-auth-1-sl",
    ]
    assert gateway.calls[0]["reduce_only"] is False
    assert gateway.calls[1]["reduce_only"] is True
    assert result.exchange_called is True
    assert result.exchange_order_submitted is True
    assert result.order_lifecycle_submit_called is True
    assert result.exchange_call_count == 2
    assert result.order_lifecycle_submit_call_count == 2
    assert execution_result_repo.acquire_calls == 1
    assert execution_result_repo.complete_calls == 1
    assert result.entry_exchange_order_id == "ex-runtime-order-draft-auth-1-entry"
    assert result.protection_exchange_order_ids == [
        "ex-runtime-order-draft-auth-1-sl"
    ]
    assert lifecycle.orders[
        "runtime-order-draft-auth-1-entry"
    ].status == OrderStatus.SUBMITTED
    assert lifecycle.orders[
        "runtime-order-draft-auth-1-sl"
    ].status == OrderStatus.SUBMITTED
    assert result.execution_intent_status_changed is False
    assert result.owner_bounded_execution_called is False
    assert result.withdrawal_or_transfer_created is False
    assert recovery_repo.create_calls == []
    assert intent_repo.saved == []


@pytest.mark.asyncio
async def test_service_exchange_submit_execution_reports_entry_failure_without_recovery_task():
    context = await _ready_exchange_submit_execution_context(
        exchange_gateway=_ExchangeGateway(
            fail_on_client_order_id="runtime-order-draft-auth-1-entry",
        ),
    )

    result = await context.service.exchange_submit_execution_result_for_authorization(
        "auth-1",
        exchange_submit_execution_enabled=True,
        exchange_submit_enablement_decision=context.exchange_decision,
    )

    assert (
        result.status
        == RuntimeExecutionExchangeSubmitExecutionStatus.ENTRY_SUBMIT_FAILED
    )
    assert result.failed_local_order_id == "runtime-order-draft-auth-1-entry"
    assert result.failed_order_role == "ENTRY"
    assert "entry_submit_failed" in result.blockers
    assert result.exchange_call_count == 1
    assert result.order_lifecycle_submit_call_count == 0
    assert result.exchange_called is True
    assert result.exchange_order_submitted is False
    assert result.order_lifecycle_submit_called is False
    assert result.entry_exchange_order_id is None
    assert result.submitted_exchange_order_ids == []
    assert result.metadata["entry_submit_failed_before_exchange_acceptance"] is True
    assert result.metadata["entry_submit_failure_does_not_create_recovery_task"] is True
    assert result.metadata["protection_failure_requires_recovery_task"] is False
    assert context.exchange_submit_execution_result_repo.acquire_calls == 1
    assert context.exchange_submit_execution_result_repo.complete_calls == 1
    assert context.recovery_repo.create_calls == []
    assert context.intent_repo.saved == []


@pytest.mark.asyncio
async def test_service_exchange_submit_execution_replays_by_authorization_id():
    preview = _registration_preview()
    lifecycle = _Lifecycle()
    adapter_result_repo = _AdapterResultRepo()
    execution_result_repo = _ExchangeSubmitExecutionResultRepo()
    recovery_repo = _ExecutionRecoveryRepo()
    gateway = _ExchangeGateway()
    intent_repo = _IntentRepo(_runtime_intent(preview))
    service = _service_with_preview(
        preview,
        lifecycle=lifecycle,
        adapter_result_repo=adapter_result_repo,
        exchange_submit_execution_result_repo=execution_result_repo,
        execution_recovery_repo=recovery_repo,
        exchange_gateway=gateway,
        exchange_gateway_readiness_repo=_ExchangeGatewayReadinessRepo(),
        intent_repo=intent_repo,
    )
    local_decision = _ready_enablement_decision(preview)
    await service.order_lifecycle_adapter_result_for_authorization(
        "auth-1",
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        local_registration_enablement_decision=local_decision,
    )
    exchange_decision = (
        await service.exchange_submit_enablement_decision_for_authorization(
            "auth-1",
            trusted_submit_fact_snapshot_id="trusted-submit-facts-intent-1",
            submit_idempotency_policy_id="runtime-submit-idempotency-auth-1",
            attempt_outcome_policy_id="runtime-attempt-outcome-policy-auth-1",
            protection_creation_failure_policy_id=(
                "protection-failure-policy-intent-1"
            ),
            local_registration_enablement_decision_id=local_decision.decision_id,
            owner_real_submit_authorization_id="owner-real-submit-auth-1",
            order_lifecycle_submit_enablement_id=(
                "order-lifecycle-submit-enable-1"
            ),
            exchange_submit_adapter_enablement_id=(
                "exchange-submit-adapter-enable-1"
            ),
            exchange_submit_action_authorization_id="exchange-submit-action-1",
            deployment_readiness_evidence_id="runtime-exchange-gateway-readiness-1",
        )
    )

    first = await service.exchange_submit_execution_result_for_authorization(
        "auth-1",
        exchange_submit_execution_enabled=True,
        exchange_submit_enablement_decision=exchange_decision,
    )
    second = await service.exchange_submit_execution_result_for_authorization(
        "auth-1",
        exchange_submit_execution_enabled=True,
        exchange_submit_enablement_decision=exchange_decision,
    )

    assert (
        first.status
        == RuntimeExecutionExchangeSubmitExecutionStatus
        .EXCHANGE_SUBMIT_ORDERS_SUBMITTED
    )
    assert second.execution_result_id == first.execution_result_id
    assert second.submitted_exchange_order_ids == first.submitted_exchange_order_ids
    assert [call["client_order_id"] for call in gateway.calls] == [
        "runtime-order-draft-auth-1-entry",
        "runtime-order-draft-auth-1-sl",
    ]
    assert execution_result_repo.acquire_calls == 2
    assert execution_result_repo.complete_calls == 1
    assert recovery_repo.create_calls == []
    assert intent_repo.saved == []


@pytest.mark.asyncio
async def test_service_exchange_submit_execution_reports_protection_failure():
    preview = _registration_preview()
    lifecycle = _Lifecycle()
    adapter_result_repo = _AdapterResultRepo()
    execution_result_repo = _ExchangeSubmitExecutionResultRepo()
    recovery_repo = _ExecutionRecoveryRepo()
    gateway = _ExchangeGateway(
        fail_on_client_order_id="runtime-order-draft-auth-1-sl"
    )
    intent_repo = _IntentRepo(_runtime_intent(preview))
    service = _service_with_preview(
        preview,
        lifecycle=lifecycle,
        adapter_result_repo=adapter_result_repo,
        exchange_submit_execution_result_repo=execution_result_repo,
        execution_recovery_repo=recovery_repo,
        exchange_gateway=gateway,
        exchange_gateway_readiness_repo=_ExchangeGatewayReadinessRepo(),
        intent_repo=intent_repo,
    )
    local_decision = _ready_enablement_decision(preview)
    await service.order_lifecycle_adapter_result_for_authorization(
        "auth-1",
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        local_registration_enablement_decision=local_decision,
    )
    exchange_decision = (
        await service.exchange_submit_enablement_decision_for_authorization(
            "auth-1",
            trusted_submit_fact_snapshot_id="trusted-submit-facts-intent-1",
            submit_idempotency_policy_id="runtime-submit-idempotency-auth-1",
            attempt_outcome_policy_id="runtime-attempt-outcome-policy-auth-1",
            protection_creation_failure_policy_id=(
                "protection-failure-policy-intent-1"
            ),
            local_registration_enablement_decision_id=local_decision.decision_id,
            owner_real_submit_authorization_id="owner-real-submit-auth-1",
            order_lifecycle_submit_enablement_id=(
                "order-lifecycle-submit-enable-1"
            ),
            exchange_submit_adapter_enablement_id=(
                "exchange-submit-adapter-enable-1"
            ),
            exchange_submit_action_authorization_id="exchange-submit-action-1",
            deployment_readiness_evidence_id="runtime-exchange-gateway-readiness-1",
        )
    )

    result = await service.exchange_submit_execution_result_for_authorization(
        "auth-1",
        exchange_submit_execution_enabled=True,
        exchange_submit_enablement_decision=exchange_decision,
    )

    assert (
        result.status
        == RuntimeExecutionExchangeSubmitExecutionStatus.PROTECTION_SUBMIT_FAILED
    )
    assert result.entry_exchange_order_id == "ex-runtime-order-draft-auth-1-entry"
    assert result.failed_local_order_id == "runtime-order-draft-auth-1-sl"
    assert result.failed_order_role == "SL"
    assert "protection_submit_failed_after_entry_submit" in result.blockers
    assert result.exchange_call_count == 2
    assert result.order_lifecycle_submit_call_count == 1
    assert execution_result_repo.acquire_calls == 1
    assert execution_result_repo.complete_calls == 1
    assert result.exchange_called is True
    assert result.exchange_order_submitted is True
    assert result.order_lifecycle_submit_called is True
    assert result.execution_intent_status_changed is False
    assert len(recovery_repo.create_calls) == 1
    recovery_task = recovery_repo.create_calls[0]
    assert recovery_task["recovery_type"] == "exchange_submit_protection_fail"
    assert recovery_task["status"] == "pending"
    assert recovery_task["intent_id"] == result.execution_intent_id
    assert recovery_task["related_order_id"] == "runtime-order-draft-auth-1-sl"
    assert recovery_task["related_exchange_order_id"] == (
        "ex-runtime-order-draft-auth-1-entry"
    )
    assert recovery_task["context_payload"]["execution_result_id"] == (
        result.execution_result_id
    )
    assert recovery_task["context_payload"]["block_new_entries_until_resolved"] is True
    assert recovery_task["context_payload"]["require_owner_recovery_review"] is True
    assert recovery_task["context_payload"]["require_reduce_only_recovery_mode"] is True
    assert (
        recovery_task["context_payload"]["require_reconciliation_before_retry"]
        is True
    )
    assert intent_repo.saved == []


@pytest.mark.asyncio
async def test_pg_adapter_result_repository_acquires_unique_authorization_lock():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(
            PGRuntimeExecutionOrderLifecycleAdapterResultORM.__table__.create
        )
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    repo = PgRuntimeExecutionOrderLifecycleAdapterResultRepository(
        session_maker=session_maker
    )
    preview = _registration_preview()
    lock_result = build_runtime_execution_order_lifecycle_adapter_lock_result(
        registration_preview=preview,
        now_ms=NOW_MS,
    )

    acquired_first, stored_first = await repo.acquire_registration_lock(lock_result)
    acquired_second, stored_second = await repo.acquire_registration_lock(lock_result)
    orders = build_runtime_execution_orders_for_registration(
        registration_preview=preview
    )
    final_result = build_runtime_execution_order_lifecycle_adapter_result(
        registration_preview=preview,
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        duplicate_submit_lock_acquired=True,
        registered_orders=orders,
        now_ms=NOW_MS + 1,
    )
    await repo.complete_registration(final_result)
    loaded = await repo.get_by_authorization_id("auth-1")

    await engine.dispose()

    assert acquired_first is True
    assert stored_first.status == (
        RuntimeExecutionOrderLifecycleAdapterResultStatus
        .LOCAL_REGISTRATION_LOCK_ACQUIRED
    )
    assert acquired_second is False
    assert stored_second.adapter_result_id == lock_result.adapter_result_id
    assert loaded is not None
    assert loaded.status == (
        RuntimeExecutionOrderLifecycleAdapterResultStatus
        .REGISTERED_CREATED_LOCAL_ORDERS
    )
    assert loaded.local_order_ids == [
        "runtime-order-draft-auth-1-entry",
        "runtime-order-draft-auth-1-sl",
    ]
    assert loaded.exchange_called is False
    assert loaded.exchange_order_submitted is False


@pytest.mark.asyncio
async def test_pg_exchange_submit_repository_acquires_unique_authorization_lock():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(
            PGRuntimeExecutionExchangeSubmitAdapterResultORM.__table__.create
        )
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    repo = PgRuntimeExecutionExchangeSubmitAdapterResultRepository(
        session_maker=session_maker
    )
    decision = _ready_exchange_submit_enablement_decision(_registration_preview())
    lock_result = build_runtime_execution_exchange_submit_adapter_lock_result(
        enablement_decision=decision,
        now_ms=NOW_MS,
    )

    acquired_first, stored_first = await repo.acquire_exchange_submit_lock(
        lock_result
    )
    acquired_second, stored_second = await repo.acquire_exchange_submit_lock(
        lock_result
    )
    final_result = build_runtime_execution_exchange_submit_adapter_result(
        enablement_decision=decision,
        exchange_submit_adapter_enabled=True,
        duplicate_submit_lock_acquired=True,
        now_ms=NOW_MS + 1,
    )
    await repo.complete_exchange_submit_result(final_result)
    loaded = await repo.get_by_authorization_id("auth-1")

    await engine.dispose()

    assert acquired_first is True
    assert (
        stored_first.status
        == RuntimeExecutionExchangeSubmitAdapterResultStatus
        .EXCHANGE_SUBMIT_LOCK_ACQUIRED
    )
    assert acquired_second is False
    assert stored_second.adapter_result_id == lock_result.adapter_result_id
    assert loaded is not None
    assert (
        loaded.status
        == RuntimeExecutionExchangeSubmitAdapterResultStatus
        .EXCHANGE_SUBMIT_ADAPTER_NOT_IMPLEMENTED
    )
    assert loaded.local_order_ids == [
        "runtime-order-draft-auth-1-entry",
        "runtime-order-draft-auth-1-sl",
    ]
    assert loaded.exchange_submit_action_authorization_id == "exchange-submit-action-1"
    assert loaded.exchange_submit_adapter_implemented is False
    assert loaded.order_lifecycle_submit_called is False
    assert loaded.exchange_order_submitted is False
    assert loaded.exchange_called is False


@pytest.mark.asyncio
async def test_pg_exchange_submit_execution_repository_replays_by_authorization():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(
            PGRuntimeExecutionExchangeSubmitExecutionResultORM.__table__.create
        )
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    repo = PgRuntimeExecutionExchangeSubmitExecutionResultRepository(
        session_maker=session_maker
    )
    preview = _registration_preview()
    orders = build_runtime_execution_orders_for_registration(
        registration_preview=preview
    )
    adapter_result = build_runtime_execution_order_lifecycle_adapter_result(
        registration_preview=preview,
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        duplicate_submit_lock_acquired=True,
        registered_orders=orders,
        now_ms=NOW_MS,
    )
    binding = build_runtime_execution_intent_local_order_binding(
        intent=_runtime_intent(preview),
        adapter_result=adapter_result,
        now_ms=NOW_MS + 1,
    )
    packet = build_runtime_execution_exchange_submit_packet_preview(
        binding=binding,
        local_orders=orders,
        now_ms=NOW_MS + 2,
    )
    decision = build_runtime_execution_exchange_submit_enablement_decision(
        packet_preview=packet,
        trusted_submit_fact_snapshot_id="trusted-submit-facts-intent-1",
        submit_idempotency_policy_id="runtime-submit-idempotency-auth-1",
        attempt_outcome_policy_id="runtime-attempt-outcome-policy-auth-1",
        protection_creation_failure_policy_id="protection-failure-policy-intent-1",
        local_registration_enablement_decision_id=(
            "runtime-local-registration-enablement-auth-1"
        ),
        owner_real_submit_authorization_id="owner-real-submit-auth-1",
        order_lifecycle_submit_enablement_id="order-lifecycle-submit-enable-1",
        exchange_submit_adapter_enablement_id="exchange-submit-adapter-enable-1",
        exchange_submit_action_authorization_id="exchange-submit-action-1",
        now_ms=NOW_MS + 3,
    )
    lock_result = build_runtime_exchange_submit_execution_lock_result(
        enablement_decision=decision,
        packet_preview=packet,
        now_ms=NOW_MS + 4,
    )

    acquired_first, stored_first = (
        await repo.acquire_exchange_submit_execution_lock(lock_result)
    )
    acquired_second, stored_second = (
        await repo.acquire_exchange_submit_execution_lock(lock_result)
    )
    entry_submit = submitted_exchange_order_from_placement(
        local_order_id="runtime-order-draft-auth-1-entry",
        order_role="ENTRY",
        reduce_only=False,
        placement_result=OrderPlacementResult(
            order_id="placement-entry",
            exchange_order_id="ex-entry",
            symbol=preview.symbol,
            order_type=OrderType.MARKET,
            direction=Direction.LONG,
            side="buy",
            amount=Decimal("0.1"),
            price=None,
            trigger_price=None,
            reduce_only=False,
            client_order_id="runtime-order-draft-auth-1-entry",
            status=OrderStatus.OPEN,
        ),
        order_lifecycle_submit_called=True,
    )
    protection_submit = submitted_exchange_order_from_placement(
        local_order_id="runtime-order-draft-auth-1-sl",
        order_role="SL",
        reduce_only=True,
        placement_result=OrderPlacementResult(
            order_id="placement-sl",
            exchange_order_id="ex-sl",
            symbol=preview.symbol,
            order_type=OrderType.STOP_MARKET,
            direction=Direction.SHORT,
            side="sell",
            amount=Decimal("0.1"),
            price=None,
            trigger_price=Decimal("280"),
            reduce_only=True,
            client_order_id="runtime-order-draft-auth-1-sl",
            status=OrderStatus.OPEN,
        ),
        order_lifecycle_submit_called=True,
    )
    final_result = build_runtime_exchange_submit_execution_submitted_result(
        enablement_decision=decision,
        packet_preview=packet,
        submitted_orders=[entry_submit, protection_submit],
        exchange_call_count=2,
        now_ms=NOW_MS + 5,
    )
    await repo.complete_exchange_submit_execution_result(final_result)
    loaded = await repo.get_by_authorization_id("auth-1")

    await engine.dispose()

    assert acquired_first is True
    assert stored_first.status == (
        RuntimeExecutionExchangeSubmitExecutionStatus
        .EXCHANGE_SUBMIT_EXECUTION_LOCK_ACQUIRED
    )
    assert acquired_second is False
    assert stored_second.execution_result_id == lock_result.execution_result_id
    assert loaded is not None
    assert (
        loaded.status
        == RuntimeExecutionExchangeSubmitExecutionStatus
        .EXCHANGE_SUBMIT_ORDERS_SUBMITTED
    )
    assert loaded.entry_exchange_order_id == "ex-entry"
    assert loaded.protection_exchange_order_ids == ["ex-sl"]
    assert loaded.exchange_called is True
    assert loaded.order_lifecycle_submit_called is True


@pytest.mark.asyncio
async def test_pg_execution_recovery_repository_blocks_exchange_submit_protection_failure():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(PGExecutionRecoveryTaskORM.__table__.create)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    repo = PgExecutionRecoveryRepository(session_maker=session_maker)

    await repo.create_task(
        task_id="rt_ex_submit_recovery_test",
        intent_id="intent-1",
        symbol="BNB/USDT:USDT",
        recovery_type="exchange_submit_protection_fail",
        related_order_id="runtime-order-draft-auth-1-sl",
        related_exchange_order_id="ex-runtime-order-draft-auth-1-entry",
        error_message="rejected runtime-order-draft-auth-1-sl",
        context_payload={
            "authorization_id": "auth-1",
            "block_new_entries_until_resolved": True,
            "require_owner_recovery_review": True,
            "require_reduce_only_recovery_mode": True,
            "require_reconciliation_before_retry": True,
        },
    )
    blocking = await repo.list_blocking()
    active = await repo.list_active()
    loaded = await repo.get("rt_ex_submit_recovery_test")

    await engine.dispose()

    assert len(blocking) == 1
    assert len(active) == 1
    assert loaded is not None
    assert loaded["recovery_type"] == "exchange_submit_protection_fail"
    assert loaded["status"] == "pending"
    assert loaded["context_payload"]["block_new_entries_until_resolved"] is True


@pytest.mark.asyncio
async def test_pg_exchange_submit_action_authorization_repository_round_trips():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(
            PGRuntimeExecutionExchangeSubmitActionAuthorizationORM.__table__.create
        )
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    repo = PgRuntimeExecutionExchangeSubmitActionAuthorizationRepository(
        session_maker=session_maker
    )
    preview = _registration_preview()
    orders = build_runtime_execution_orders_for_registration(
        registration_preview=preview
    )
    adapter_result = build_runtime_execution_order_lifecycle_adapter_result(
        registration_preview=preview,
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        duplicate_submit_lock_acquired=True,
        registered_orders=orders,
        now_ms=NOW_MS,
    )
    binding = build_runtime_execution_intent_local_order_binding(
        intent=_runtime_intent(preview),
        adapter_result=adapter_result,
        now_ms=NOW_MS + 1,
    )
    packet = build_runtime_execution_exchange_submit_packet_preview(
        binding=binding,
        local_orders=orders,
        now_ms=NOW_MS + 2,
    )
    authorization = build_runtime_execution_exchange_submit_action_authorization(
        packet_preview=packet,
        trusted_submit_fact_snapshot_id="trusted-submit-facts-intent-1",
        submit_idempotency_policy_id="runtime-submit-idempotency-auth-1",
        attempt_outcome_policy_id="runtime-attempt-outcome-policy-auth-1",
        protection_creation_failure_policy_id="protection-failure-policy-intent-1",
        local_registration_enablement_decision_id=(
            "runtime-local-registration-enablement-auth-1"
        ),
        owner_real_submit_authorization_id="owner-real-submit-auth-1",
        order_lifecycle_submit_enablement_id="order-lifecycle-submit-enable-1",
        exchange_submit_adapter_enablement_id="exchange-submit-adapter-enable-1",
        owner_confirmed_for_exchange_submit_action=True,
        owner_operator_id="owner",
        reason="repository roundtrip",
        now_ms=NOW_MS + 3,
    )

    await repo.create(authorization)
    loaded = await repo.get(authorization.action_authorization_id)
    missing = await repo.get("missing-action-auth")

    await engine.dispose()

    assert missing is None
    assert loaded is not None
    assert loaded.action_authorization_id == authorization.action_authorization_id
    assert (
        loaded.status
        == RuntimeExecutionExchangeSubmitActionAuthorizationStatus
        .APPROVED_FOR_EXCHANGE_SUBMIT_ACTION
    )
    assert loaded.authorization_id == "auth-1"
    assert loaded.exchange_called is False
    assert loaded.order_lifecycle_submit_called is False


@pytest.mark.asyncio
async def test_adapter_result_migration_creates_lock_table():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-06-10-068_create_runtime_order_lifecycle_adapter_results.py"
    )
    spec = importlib.util.spec_from_file_location(
        "runtime_order_lifecycle_adapter_result_migration",
        migration_path,
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:

        def upgrade(sync_conn):
            sync_conn.exec_driver_sql(
                """
                CREATE TABLE orders (
                    id VARCHAR PRIMARY KEY,
                    status VARCHAR NOT NULL,
                    CONSTRAINT check_orders_status CHECK (
                        status IN ('PENDING', 'OPEN', 'PARTIALLY_FILLED',
                        'FILLED', 'CANCELED', 'REJECTED', 'EXPIRED')
                    )
                )
                """
            )
            old_op = migration.op
            migration.op = Operations(MigrationContext.configure(sync_conn))
            try:
                migration.upgrade()
                inspector = inspect(sync_conn)
                assert inspector.has_table(
                    "runtime_execution_order_lifecycle_adapter_results"
                )
                columns = {
                    column["name"]
                    for column in inspector.get_columns(
                        "runtime_execution_order_lifecycle_adapter_results"
                    )
                }
                unique_constraints = {
                    constraint["name"]
                    for constraint in inspector.get_unique_constraints(
                        "runtime_execution_order_lifecycle_adapter_results"
                    )
                }
                sync_conn.exec_driver_sql(
                    """
                    INSERT INTO runtime_execution_order_lifecycle_adapter_results (
                        adapter_result_id,
                        registration_preview_id,
                        adapter_preview_id,
                        handoff_draft_id,
                        preflight_id,
                        authorization_id,
                        execution_intent_id,
                        runtime_instance_id,
                        source_type,
                        source_id,
                        status,
                        symbol,
                        side,
                        local_order_ids,
                        entry_order_ids,
                        protection_order_ids,
                        registered_order_count,
                        blockers,
                        warnings,
                        order_lifecycle_adapter_enabled,
                        local_order_registration_enabled,
                        duplicate_submit_lock_acquired,
                        order_objects_constructed,
                        local_order_registration_executed,
                        execution_intent_status_changed,
                        exchange_order_submitted,
                        exchange_called,
                        owner_bounded_execution_called,
                        order_lifecycle_called,
                        withdrawal_or_transfer_created,
                        created_at_ms,
                        metadata
                    ) VALUES (
                        'adapter-result-failure-1',
                        'registration-preview-1',
                        'adapter-preview-1',
                        'handoff-1',
                        'preflight-1',
                        'auth-1',
                        'intent-1',
                        'runtime-1',
                        'brc_runtime_order_candidate',
                        'candidate-1',
                        'registered_created_local_orders',
                        'BNB/USDT:USDT',
                        'long',
                        '["runtime-order-draft-auth-1-entry"]',
                        '["runtime-order-draft-auth-1-entry"]',
                        '[]',
                        1,
                        '[]',
                        '[]',
                        1,
                        1,
                        1,
                        1,
                        1,
                        0,
                        0,
                        0,
                        0,
                        1,
                        0,
                        1781090000000,
                        '{}'
                    )
                    """
                )
                row = sync_conn.exec_driver_sql(
                    "SELECT status, registered_order_count "
                    "FROM runtime_execution_order_lifecycle_adapter_results"
                ).one()
                migration.downgrade()
                inspector = inspect(sync_conn)
                assert not inspector.has_table(
                    "runtime_execution_order_lifecycle_adapter_results"
                )
                return columns, unique_constraints, row
            finally:
                migration.op = old_op

        columns, unique_constraints, row = await conn.run_sync(upgrade)
    await engine.dispose()

    assert "adapter_result_id" in columns
    assert "authorization_id" in columns
    assert "duplicate_submit_lock_acquired" in columns
    assert "order_lifecycle_called" in columns
    assert "exchange_called" in columns
    assert "uq_rt_ol_adapter_result_authorization" in unique_constraints
    assert row[0] == "registered_created_local_orders"
    assert row[1] == 1


@pytest.mark.asyncio
async def test_exchange_submit_execution_result_migration_creates_replay_table():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / (
            "migrations/versions/"
            "2026-06-11-075_create_runtime_exchange_submit_execution_results.py"
        )
    )
    spec = importlib.util.spec_from_file_location(
        "runtime_exchange_submit_execution_result_migration",
        migration_path,
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:

        def upgrade(sync_conn):
            old_op = migration.op
            migration.op = Operations(MigrationContext.configure(sync_conn))
            try:
                migration.upgrade()
                inspector = inspect(sync_conn)
                assert inspector.has_table(
                    "runtime_execution_exchange_submit_execution_results"
                )
                columns = {
                    column["name"]
                    for column in inspector.get_columns(
                        "runtime_execution_exchange_submit_execution_results"
                    )
                }
                unique_constraints = {
                    constraint["name"]
                    for constraint in inspector.get_unique_constraints(
                        "runtime_execution_exchange_submit_execution_results"
                    )
                }
                sync_conn.exec_driver_sql(
                    """
                    INSERT INTO runtime_execution_exchange_submit_execution_results (
                        execution_result_id,
                        enablement_decision_id,
                        packet_preview_id,
                        binding_id,
                        authorization_id,
                        execution_intent_id,
                        runtime_instance_id,
                        source_type,
                        source_id,
                        status,
                        symbol,
                        exchange_submit_action_authorization_id,
                        local_order_ids,
                        entry_order_id,
                        protection_order_ids,
                        submitted_orders,
                        submitted_local_order_ids,
                        submitted_exchange_order_ids,
                        entry_exchange_order_id,
                        protection_exchange_order_ids,
                        failed_local_order_id,
                        failed_order_role,
                        failed_reason,
                        exchange_submit_execution_enabled,
                        exchange_call_count,
                        order_lifecycle_submit_call_count,
                        blockers,
                        warnings,
                        real_exchange_submit_adapter_executed,
                        exchange_order_submitted,
                        exchange_called,
                        order_lifecycle_submit_called,
                        execution_intent_status_changed,
                        owner_bounded_execution_called,
                        withdrawal_or_transfer_created,
                        created_at_ms,
                        metadata,
                        payload
                    ) VALUES (
                        'runtime-exchange-submit-execution-result-auth-1',
                        'runtime-exchange-submit-enable-auth-1',
                        'runtime-exchange-submit-packet-auth-1',
                        'runtime-binding-auth-1',
                        'auth-1',
                        'intent-1',
                        'runtime-1',
                        'brc_runtime_order_candidate',
                        'candidate-1',
                        'exchange_submit_execution_lock_acquired',
                        'BNB/USDT:USDT',
                        'exchange-submit-action-1',
                        '["runtime-order-draft-auth-1-entry"]',
                        'runtime-order-draft-auth-1-entry',
                        '["runtime-order-draft-auth-1-sl"]',
                        '[]',
                        '[]',
                        '[]',
                        NULL,
                        '[]',
                        NULL,
                        NULL,
                        NULL,
                        1,
                        0,
                        0,
                        '[]',
                        '["exchange_submit_execution_lock_acquired"]',
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        1781090000000,
                        '{}',
                        '{}'
                    )
                    """
                )
                row = sync_conn.exec_driver_sql(
                    "SELECT status, exchange_called, "
                    "order_lifecycle_submit_called "
                    "FROM runtime_execution_exchange_submit_execution_results"
                ).one()
                migration.downgrade()
                inspector = inspect(sync_conn)
                assert not inspector.has_table(
                    "runtime_execution_exchange_submit_execution_results"
                )
                return columns, unique_constraints, row
            finally:
                migration.op = old_op

        columns, unique_constraints, row = await conn.run_sync(upgrade)
    await engine.dispose()

    assert "execution_result_id" in columns
    assert "authorization_id" in columns
    assert "exchange_call_count" in columns
    assert "order_lifecycle_submit_call_count" in columns
    assert "payload" in columns
    assert "uq_rt_exchange_exec_result_authorization" in unique_constraints
    assert row[0] == "exchange_submit_execution_lock_acquired"
    assert row[1] == 0
    assert row[2] == 0


@pytest.mark.asyncio
async def test_execution_recovery_task_type_migration_allows_exchange_submit_failure():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-06-11-076_extend_execution_recovery_task_types.py"
    )
    spec = importlib.util.spec_from_file_location(
        "execution_recovery_task_type_migration",
        migration_path,
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:

        def upgrade(sync_conn):
            sync_conn.exec_driver_sql(
                """
                CREATE TABLE execution_recovery_tasks (
                    id VARCHAR(64) PRIMARY KEY,
                    intent_id VARCHAR(64) NOT NULL,
                    related_order_id VARCHAR(64),
                    related_exchange_order_id VARCHAR(128),
                    symbol VARCHAR(64) NOT NULL,
                    recovery_type VARCHAR(32) NOT NULL,
                    status VARCHAR(16) NOT NULL,
                    error_message TEXT,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    next_retry_at BIGINT,
                    context_payload JSON,
                    created_at BIGINT NOT NULL,
                    updated_at BIGINT NOT NULL,
                    resolved_at BIGINT,
                    CONSTRAINT ck_execution_recovery_tasks_recovery_type
                        CHECK (recovery_type IN ('replace_sl_failed')),
                    CONSTRAINT ck_execution_recovery_tasks_status
                        CHECK (status IN ('pending', 'retrying', 'resolved', 'failed')),
                    CONSTRAINT ck_execution_recovery_tasks_retry_count_non_negative
                        CHECK (retry_count >= 0)
                )
                """
            )
            old_op = migration.op
            migration.op = Operations(MigrationContext.configure(sync_conn))
            try:
                migration.upgrade()
                sync_conn.exec_driver_sql(
                    """
                    INSERT INTO execution_recovery_tasks (
                        id,
                        intent_id,
                        symbol,
                        recovery_type,
                        status,
                        retry_count,
                        context_payload,
                        created_at,
                        updated_at
                    ) VALUES (
                        'rt_ex_submit_recovery_test',
                        'intent-1',
                        'BNB/USDT:USDT',
                        'exchange_submit_protection_fail',
                        'pending',
                        0,
                        '{}',
                        1781090000000,
                        1781090000000
                    )
                    """
                )
                row = sync_conn.exec_driver_sql(
                    "SELECT recovery_type, status FROM execution_recovery_tasks"
                ).one()
                sync_conn.exec_driver_sql(
                    "DELETE FROM execution_recovery_tasks "
                    "WHERE id = 'rt_ex_submit_recovery_test'"
                )
                migration.downgrade()
                inspector = inspect(sync_conn)
                assert inspector.has_table("execution_recovery_tasks")
                return row
            finally:
                migration.op = old_op

        row = await conn.run_sync(upgrade)
    await engine.dispose()

    assert row[0] == "exchange_submit_protection_fail"
    assert row[1] == "pending"


@pytest.mark.asyncio
async def test_exchange_submit_adapter_result_migration_creates_lock_table():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-06-11-071_create_runtime_exchange_submit_adapter_results.py"
    )
    spec = importlib.util.spec_from_file_location(
        "runtime_exchange_submit_adapter_result_migration",
        migration_path,
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:

        def upgrade(sync_conn):
            old_op = migration.op
            migration.op = Operations(MigrationContext.configure(sync_conn))
            try:
                migration.upgrade()
                inspector = inspect(sync_conn)
                assert inspector.has_table(
                    "runtime_execution_exchange_submit_adapter_results"
                )
                columns = {
                    column["name"]
                    for column in inspector.get_columns(
                        "runtime_execution_exchange_submit_adapter_results"
                    )
                }
                unique_constraints = {
                    constraint["name"]
                    for constraint in inspector.get_unique_constraints(
                        "runtime_execution_exchange_submit_adapter_results"
                    )
                }
                sync_conn.exec_driver_sql(
                    """
                    INSERT INTO runtime_execution_exchange_submit_adapter_results (
                        adapter_result_id,
                        enablement_decision_id,
                        gate_id,
                        packet_preview_id,
                        binding_id,
                        local_registration_adapter_result_id,
                        authorization_id,
                        execution_intent_id,
                        runtime_instance_id,
                        source_type,
                        source_id,
                        status,
                        symbol,
                        local_order_ids,
                        entry_order_id,
                        protection_order_ids,
                        submit_request_previews,
                        submit_request_count,
                        entry_submit_request_count,
                        protection_submit_request_count,
                        blockers,
                        warnings,
                        order_lifecycle_submit_enabled,
                        exchange_submit_adapter_enabled,
                        exchange_submit_action_authorized,
                        duplicate_submit_lock_acquired,
                        exchange_submit_adapter_implemented,
                        order_lifecycle_submit_called,
                        execution_intent_status_changed,
                        exchange_order_submitted,
                        exchange_called,
                        owner_bounded_execution_called,
                        withdrawal_or_transfer_created,
                        created_at_ms,
                        metadata
                    ) VALUES (
                        'exchange-submit-result-auth-1',
                        'exchange-submit-enablement-auth-1',
                        'exchange-submit-gate-auth-1',
                        'exchange-submit-packet-auth-1',
                        'binding-auth-1',
                        'local-registration-result-auth-1',
                        'auth-1',
                        'intent-1',
                        'runtime-1',
                        'brc_runtime_order_candidate',
                        'candidate-1',
                        'exchange_submit_adapter_not_implemented',
                        'BNB/USDT:USDT',
                        '["runtime-order-draft-auth-1-entry"]',
                        'runtime-order-draft-auth-1-entry',
                        '["runtime-order-draft-auth-1-sl"]',
                        '[]',
                        0,
                        0,
                        0,
                        '["exchange_submit_adapter_not_implemented"]',
                        '[]',
                        1,
                        1,
                        1,
                        1,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        1781090000000,
                        '{}'
                    )
                    """
                )
                row = sync_conn.exec_driver_sql(
                    "SELECT status, exchange_called, exchange_order_submitted "
                    "FROM runtime_execution_exchange_submit_adapter_results"
                ).one()
                migration.downgrade()
                inspector = inspect(sync_conn)
                assert not inspector.has_table(
                    "runtime_execution_exchange_submit_adapter_results"
                )
                return columns, unique_constraints, row
            finally:
                migration.op = old_op

        columns, unique_constraints, row = await conn.run_sync(upgrade)
    await engine.dispose()

    assert "adapter_result_id" in columns
    assert "authorization_id" in columns
    assert "order_lifecycle_submit_called" in columns
    assert "exchange_order_submitted" in columns
    assert "exchange_called" in columns
    assert "uq_rt_exchange_submit_result_authorization" in unique_constraints
    assert row[0] == "exchange_submit_adapter_not_implemented"
    assert row[1] == 0
    assert row[2] == 0


@pytest.mark.asyncio
async def test_exchange_submit_action_authorization_migration_creates_evidence_table():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/"
        "2026-06-11-074_create_runtime_exchange_submit_action_authorizations.py"
    )
    spec = importlib.util.spec_from_file_location(
        "runtime_exchange_submit_action_authorization_migration",
        migration_path,
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:

        def upgrade(sync_conn):
            old_op = migration.op
            migration.op = Operations(MigrationContext.configure(sync_conn))
            try:
                migration.upgrade()
                inspector = inspect(sync_conn)
                assert inspector.has_table(
                    "runtime_execution_exchange_submit_action_authorizations"
                )
                columns = {
                    column["name"]
                    for column in inspector.get_columns(
                        "runtime_execution_exchange_submit_action_authorizations"
                    )
                }
                unique_constraints = {
                    constraint["name"]
                    for constraint in inspector.get_unique_constraints(
                        "runtime_execution_exchange_submit_action_authorizations"
                    )
                }
                sync_conn.exec_driver_sql(
                    """
                    INSERT INTO runtime_execution_exchange_submit_action_authorizations (
                        action_authorization_id,
                        authorization_id,
                        execution_intent_id,
                        runtime_instance_id,
                        source_type,
                        source_id,
                        status,
                        symbol,
                        side,
                        local_registration_enablement_decision_id,
                        trusted_submit_fact_snapshot_id,
                        submit_idempotency_policy_id,
                        attempt_outcome_policy_id,
                        protection_creation_failure_policy_id,
                        owner_real_submit_authorization_id,
                        order_lifecycle_submit_enablement_id,
                        exchange_submit_adapter_enablement_id,
                        deployment_readiness_evidence_id,
                        packet_preview_id,
                        binding_id,
                        local_registration_adapter_result_id,
                        entry_order_id,
                        local_order_ids,
                        protection_order_ids,
                        submit_request_count,
                        entry_submit_request_count,
                        protection_submit_request_count,
                        owner_confirmed_for_exchange_submit_action,
                        owner_operator_id,
                        owner_confirmation_reference,
                        reason,
                        expires_at_ms,
                        blockers,
                        warnings,
                        order_lifecycle_submit_called,
                        execution_intent_status_changed,
                        exchange_order_submitted,
                        exchange_called,
                        owner_bounded_execution_called,
                        withdrawal_or_transfer_created,
                        metadata,
                        payload,
                        created_at_ms
                    ) VALUES (
                        'exchange-submit-action-auth-1',
                        'auth-1',
                        'intent-1',
                        'runtime-1',
                        'brc_runtime_order_candidate',
                        'candidate-1',
                        'approved_for_exchange_submit_action',
                        'BNB/USDT:USDT',
                        'LONG',
                        'runtime-local-registration-enablement-auth-1',
                        'trusted-submit-facts-intent-1',
                        'runtime-submit-idempotency-auth-1',
                        'runtime-attempt-outcome-policy-auth-1',
                        'protection-failure-policy-intent-1',
                        'owner-real-submit-auth-1',
                        'order-lifecycle-submit-enable-1',
                        'exchange-submit-adapter-enable-1',
                        NULL,
                        'packet-preview-auth-1',
                        'binding-auth-1',
                        'local-registration-result-auth-1',
                        'runtime-order-draft-auth-1-entry',
                        '["runtime-order-draft-auth-1-entry"]',
                        '["runtime-order-draft-auth-1-sl"]',
                        2,
                        1,
                        1,
                        1,
                        'owner',
                        NULL,
                        'migration smoke',
                        NULL,
                        '[]',
                        '[]',
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        '{}',
                        '{}',
                        1781090000000
                    )
                    """
                )
                row = sync_conn.exec_driver_sql(
                    "SELECT status, exchange_called, exchange_order_submitted "
                    "FROM runtime_execution_exchange_submit_action_authorizations"
                ).one()
                migration.downgrade()
                inspector = inspect(sync_conn)
                assert not inspector.has_table(
                    "runtime_execution_exchange_submit_action_authorizations"
                )
                return columns, unique_constraints, row
            finally:
                migration.op = old_op

        columns, unique_constraints, row = await conn.run_sync(upgrade)
    await engine.dispose()

    assert "action_authorization_id" in columns
    assert "authorization_id" in columns
    assert "owner_confirmed_for_exchange_submit_action" in columns
    assert "order_lifecycle_submit_called" in columns
    assert "exchange_called" in columns
    assert "uq_rt_exchange_action_auth_authorization" in unique_constraints
    assert row[0] == "approved_for_exchange_submit_action"
    assert row[1] == 0
    assert row[2] == 0
