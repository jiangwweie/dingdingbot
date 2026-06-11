#!/usr/bin/env python3
"""Build a local pre-live runtime submit rehearsal packet.

This verifier uses the real runtime execution planning/adapter services with
in-memory repositories. It proves the non-executing chain can reach the submit
adapter boundary while separately reporting first-real-submit blockers such as
current-head deployment and explicit Owner live-submit authorization.

It never connects to a database, mutates Tokyo, starts a runtime, creates an
order, calls OrderLifecycle, or calls exchange APIs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.application.runtime_execution_intent_adapter_service import (
    RuntimeExecutionIntentAdapterService,
)
from src.application.runtime_execution_first_real_submit_evidence_preparation_service import (
    RuntimeExecutionFirstRealSubmitEvidencePreparationService,
)
from src.application.runtime_execution_planning_service import (
    RuntimeExecutionPlanningService,
)
from src.application.runtime_execution_trusted_submit_facts_service import (
    RuntimeExecutionTrustedSubmitFactsAssemblyService,
)
from src.application.runtime_final_gate_preview_service import (
    RuntimeFinalGatePreviewService,
)
from src.domain.execution_intent import ExecutionIntent, ExecutionIntentStatus
from src.domain.runtime_execution_controlled_submit import (
    RuntimeExecutionControlledSubmitPreflightStatus,
)
from src.domain.runtime_execution_attempt_mutation import (
    RuntimeExecutionAttemptMutationStatus,
)
from src.domain.runtime_execution_attempt_outcome_policy import (
    RuntimeExecutionAttemptOutcomeKind,
)
from src.domain.runtime_execution_order_lifecycle_adapter import (
    RuntimeExecutionOrderLifecycleAdapterPreviewStatus,
)
from src.domain.runtime_execution_order_lifecycle_handoff import (
    RuntimeExecutionOrderLifecycleHandoffStatus,
)
from src.domain.runtime_execution_order_registration_draft import (
    RuntimeExecutionOrderRegistrationDraftPreviewStatus,
)
from src.domain.runtime_execution_protection_plan import (
    RuntimeExecutionProtectionPlanStatus,
)
from src.domain.runtime_execution_protection_failure_policy import (
    RuntimeExecutionProtectionFailurePolicyStatus,
    build_runtime_execution_protection_failure_policy,
)
from src.domain.runtime_execution_intent_adapter import (
    RuntimeExecutionSubmitReadinessStatus,
)
from src.domain.runtime_execution_plan import (
    RuntimeExecutionIntentDraft,
    RuntimeExecutionIntentDraftStatus,
    RuntimeExecutionPlanStatus,
)
from src.domain.runtime_execution_submit_authorization import (
    RuntimeExecutionSubmitAuthorization,
    RuntimeExecutionSubmitAuthorizationStatus,
)
from src.domain.runtime_execution_submit_adapter import (
    RuntimeExecutionSubmitAdapterPreviewStatus,
)
from src.domain.signal_evaluation import (
    OrderCandidate,
    OrderCandidateProtectionPreview,
    OrderCandidateRiskPreview,
)
from src.domain.strategy_runtime import (
    StrategyRuntimeBoundary,
    StrategyRuntimeInstance,
    StrategyRuntimeInstanceStatus,
)
from src.domain.strategy_runtime_live_enablement import (
    StrategyRuntimeLiveEnablementPreviewStatus,
    build_strategy_runtime_live_enablement_preview,
)
from src.domain.strategy_runtime_promotion_gate import (
    FirstRealSubmitConfirmationFacts,
    RuntimeExecutionConfirmationFacts,
    StrategyRuntimePromotionGateInput,
    StrategyRuntimePromotionScope,
    StrategySemanticsConfirmationFacts,
    evaluate_strategy_runtime_promotion_gate,
)
from src.domain.strategy_runtime_safety_readiness import (
    evaluate_strategy_runtime_safety_readiness,
)
from src.domain.runtime_execution_trusted_submit_facts import (
    RuntimeExecutionTrustedSubmitFactSource,
)
from src.domain.strategy_semantics import initial_strategy_semantics_catalog


DEFAULT_DEPLOYED_HEAD = "ae9b209e33cd287273491f2e93dfdff3b6a814fd"
DEFAULT_SYMBOL = "BNB/USDT:USDT"
DEFAULT_SIDE = "long"
DEFAULT_RUNTIME_ID = "pre-live-rehearsal-runtime-bnb-long"
DEFAULT_ORDER_CANDIDATE_ID = "pre-live-rehearsal-candidate-bnb-long"
OWNER_AUTHORIZATION_FLAG = "--owner-real-submit-authorized"
OWNER_LIVE_RUNTIME_ENABLEMENT_FLAG = "--owner-live-runtime-enable-authorized"


@dataclass(frozen=True)
class CommandResult:
    stdout: str
    returncode: int


class _RuntimeService:
    def __init__(self, runtime: StrategyRuntimeInstance) -> None:
        self.runtime = runtime
        self.events: list[dict[str, Any]] = []

    async def get_runtime(self, runtime_instance_id: str) -> StrategyRuntimeInstance:
        if runtime_instance_id != self.runtime.runtime_instance_id:
            raise ValueError("runtime_not_found")
        return self.runtime

    async def apply_runtime_attempt_mutation(
        self,
        *,
        previous_runtime: StrategyRuntimeInstance,
        updated_runtime: StrategyRuntimeInstance,
        mutation: Any,
    ) -> None:
        if previous_runtime.runtime_instance_id != self.runtime.runtime_instance_id:
            raise ValueError("runtime_mutation_runtime_mismatch")
        self.runtime = updated_runtime
        self.events.append(
            {
                "event": "in_memory_attempt_mutation_applied",
                "mutation_id": mutation.mutation_id,
            }
        )


class _CandidateService:
    def __init__(self, candidate: OrderCandidate) -> None:
        self.candidate = candidate

    async def get_order_candidate(self, order_candidate_id: str) -> OrderCandidate:
        if order_candidate_id != self.candidate.order_candidate_id:
            raise ValueError("order_candidate_not_found")
        return self.candidate


class _ActivePositionSource:
    def __init__(self, active_positions: int) -> None:
        self.active_positions = active_positions

    async def list_active(self, *, symbol: str | None = None, limit: int = 100):
        return [object() for _ in range(self.active_positions)]


class _DraftRepository:
    def __init__(self) -> None:
        self.records: dict[str, RuntimeExecutionIntentDraft] = {}

    async def create(
        self,
        draft: RuntimeExecutionIntentDraft,
    ) -> RuntimeExecutionIntentDraft:
        self.records[draft.draft_id] = draft
        return draft

    async def get(self, draft_id: str) -> RuntimeExecutionIntentDraft | None:
        return self.records.get(draft_id)


class _IntentRepository:
    def __init__(self) -> None:
        self.records: dict[str, ExecutionIntent] = {}

    async def get(self, intent_id: str) -> ExecutionIntent | None:
        return self.records.get(intent_id)

    async def save(self, intent: ExecutionIntent) -> None:
        self.records[intent.id] = intent


class _SubmitAuthorizationRepository:
    def __init__(self) -> None:
        self.records: dict[str, RuntimeExecutionSubmitAuthorization] = {}

    async def get(
        self,
        authorization_id: str,
    ) -> RuntimeExecutionSubmitAuthorization | None:
        return self.records.get(authorization_id)

    async def create(
        self,
        authorization: RuntimeExecutionSubmitAuthorization,
    ) -> RuntimeExecutionSubmitAuthorization:
        self.records[authorization.authorization_id] = authorization
        return authorization


class _InMemoryRepository:
    def __init__(self, id_attr: str) -> None:
        self.id_attr = id_attr
        self.records: dict[str, Any] = {}

    async def get(self, item_id: str) -> Any | None:
        return self.records.get(item_id)

    async def create(self, item: Any) -> Any:
        self.records[getattr(item, self.id_attr)] = item
        return item


class _OrderLifecycleAdapterResultRepository:
    def __init__(self) -> None:
        self.records: dict[str, Any] = {}

    async def acquire_registration_lock(self, result: Any) -> tuple[bool, Any]:
        existing = self.records.get(result.authorization_id)
        if existing is not None:
            return False, existing
        self.records[result.authorization_id] = result
        return True, result

    async def complete_registration(self, result: Any) -> Any:
        self.records[result.authorization_id] = result
        return result

    async def get_by_authorization_id(self, authorization_id: str) -> Any | None:
        return self.records.get(authorization_id)


class _ExchangeSubmitAdapterResultRepository:
    def __init__(self) -> None:
        self.records: dict[str, Any] = {}

    async def get_by_authorization_id(self, authorization_id: str) -> Any | None:
        return self.records.get(authorization_id)

    async def acquire_exchange_submit_lock(self, result: Any) -> tuple[bool, Any]:
        existing = self.records.get(result.authorization_id)
        if existing is not None:
            return False, existing
        self.records[result.authorization_id] = result
        return True, result

    async def complete_exchange_submit_result(self, result: Any) -> Any:
        self.records[result.authorization_id] = result
        return result


class _ExchangeSubmitExecutionResultRepository:
    def __init__(self) -> None:
        self.records: dict[str, Any] = {}

    async def get_by_authorization_id(self, authorization_id: str) -> Any | None:
        return self.records.get(authorization_id)

    async def acquire_exchange_submit_execution_lock(
        self,
        result: Any,
    ) -> tuple[bool, Any]:
        existing = self.records.get(result.authorization_id)
        if existing is not None:
            return False, existing
        self.records[result.authorization_id] = result
        return True, result

    async def complete_exchange_submit_execution_result(self, result: Any) -> Any:
        self.records[result.authorization_id] = result
        return result


class _TrustedSubmitFactReader:
    async def read_trusted_submit_fact_source(
        self,
        *,
        key: str,
        execution_intent_id: str,
        runtime_instance_id: str | None,
        order_candidate_id: str | None,
        symbol: str,
        side: str | None,
        now_ms: int,
    ) -> RuntimeExecutionTrustedSubmitFactSource:
        return RuntimeExecutionTrustedSubmitFactSource(
            key=key,
            source_id=f"pre-live-{key}-{symbol}",
            source_type=f"pre_live_in_memory_{key}_snapshot",
            observed_at_ms=now_ms - 50,
            max_age_ms=300_000,
            metadata={
                "pre_live_rehearsal": True,
                "execution_intent_id": execution_intent_id,
                "runtime_instance_id": runtime_instance_id,
                "order_candidate_id": order_candidate_id,
                "symbol": symbol,
                "side": side,
            },
        )


async def build_pre_live_packet(
    *,
    deployed_head: str | None,
    owner_real_submit_authorized: bool,
    owner_live_runtime_enablement_authorized: bool = False,
    require_current_head_deployed: bool = True,
    active_positions: int = 0,
    runner: Any | None = None,
) -> dict[str, Any]:
    repo_root = _repo_root(runner=runner)
    local_head = _git(repo_root, "rev-parse", "HEAD", runner=runner).stdout
    short_head = _git(repo_root, "rev-parse", "--short=8", "HEAD", runner=runner).stdout
    runtime = _runtime()
    candidate = _candidate()

    runtime_service = _RuntimeService(runtime)
    candidate_service = _CandidateService(candidate)
    active_position_source = _ActivePositionSource(active_positions)
    final_gate = RuntimeFinalGatePreviewService(
        runtime_service=runtime_service,
        signal_evaluation_service=candidate_service,
        active_position_source=active_position_source,
    )
    draft_repository = _DraftRepository()
    intent_repository = _IntentRepository()
    authorization_repository = _SubmitAuthorizationRepository()
    attempt_reservation_repository = _InMemoryRepository("reservation_id")
    attempt_mutation_repository = _InMemoryRepository("mutation_id")
    protection_plan_repository = _InMemoryRepository("protection_plan_id")
    protection_failure_policy_repository = _InMemoryRepository("policy_id")
    trusted_submit_facts_repository = _InMemoryRepository(
        "trusted_submit_fact_snapshot_id"
    )
    submit_idempotency_repository = _InMemoryRepository(
        "submit_idempotency_policy_id"
    )
    attempt_outcome_policy_repository = _InMemoryRepository("policy_id")
    order_lifecycle_handoff_repository = _InMemoryRepository("handoff_draft_id")
    order_lifecycle_adapter_result_repository = (
        _OrderLifecycleAdapterResultRepository()
    )
    exchange_submit_adapter_result_repository = (
        _ExchangeSubmitAdapterResultRepository()
    )
    exchange_submit_execution_result_repository = (
        _ExchangeSubmitExecutionResultRepository()
    )
    planning_service = RuntimeExecutionPlanningService(
        runtime_service=runtime_service,
        signal_evaluation_service=candidate_service,
        final_gate_preview_service=final_gate,
        intent_draft_repository=draft_repository,
    )
    adapter_service = RuntimeExecutionIntentAdapterService(
        draft_repository=draft_repository,
        intent_repository=intent_repository,
        submit_authorization_repository=authorization_repository,
        attempt_reservation_repository=attempt_reservation_repository,
        attempt_mutation_repository=attempt_mutation_repository,
        attempt_outcome_policy_repository=attempt_outcome_policy_repository,
        protection_plan_repository=protection_plan_repository,
        protection_failure_policy_repository=protection_failure_policy_repository,
        order_lifecycle_handoff_repository=order_lifecycle_handoff_repository,
        order_lifecycle_adapter_result_repository=(
            order_lifecycle_adapter_result_repository
        ),
        trusted_submit_facts_repository=trusted_submit_facts_repository,
        submit_idempotency_repository=submit_idempotency_repository,
        exchange_submit_adapter_result_repository=(
            exchange_submit_adapter_result_repository
        ),
        exchange_submit_execution_result_repository=(
            exchange_submit_execution_result_repository
        ),
        final_gate_preview_service=final_gate,
        runtime_service=runtime_service,
    )

    plan = await planning_service.plan_order_candidate(
        order_candidate_id=candidate.order_candidate_id,
        owner_reviewed=True,
    )
    draft = await planning_service.record_intent_draft_for_order_candidate(
        order_candidate_id=candidate.order_candidate_id,
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    intent_preview = await adapter_service.preview_from_draft(draft.draft_id)
    intent = await adapter_service.create_recorded_intent_from_draft(draft.draft_id)
    submit_readiness = await adapter_service.submit_readiness_for_intent(intent.id)
    authorization = await adapter_service.create_submit_authorization_for_intent(
        intent.id,
        owner_confirmed_for_submit=True,
    )
    controlled_submit_preflight = (
        await adapter_service.controlled_submit_preflight_for_authorization(
            authorization.authorization_id
        )
    )
    attempt_reservation_preview = (
        await adapter_service.attempt_reservation_preview_for_authorization(
            authorization.authorization_id
        )
    )
    protection_plan_preview = await adapter_service.protection_plan_preview_for_intent(
        intent.id
    )
    submit_adapter_preview = (
        await adapter_service.controlled_submit_adapter_preview_for_authorization(
            authorization.authorization_id
        )
    )
    protection_plan = await adapter_service.record_protection_plan_for_intent(intent.id)
    protection_failure_policy = build_runtime_execution_protection_failure_policy(
        protection_plan=protection_plan,
        now_ms=_now_ms(),
    )
    attempt_reservation = await adapter_service.record_attempt_reservation_for_authorization(
        authorization.authorization_id
    )
    attempt_mutation = await adapter_service.apply_attempt_mutation_for_reservation(
        attempt_reservation.reservation_id
    )
    attempt_outcome_policy = (
        await adapter_service.record_attempt_outcome_policy_for_reservation(
            attempt_reservation.reservation_id,
            outcome_kind=(
                RuntimeExecutionAttemptOutcomeKind
                .ENTRY_FILLED_PROTECTION_CREATION_FAILED
            ),
        )
    )
    order_lifecycle_handoff = (
        await adapter_service.record_order_lifecycle_handoff_draft_for_authorization(
            authorization.authorization_id
        )
    )
    order_lifecycle_adapter_preview = (
        await adapter_service.order_lifecycle_adapter_preview_for_authorization(
            authorization.authorization_id
        )
    )
    order_registration_draft_preview = (
        await adapter_service.order_registration_draft_preview_for_authorization(
            authorization.authorization_id
        )
    )
    order_lifecycle_adapter_result = (
        await adapter_service.order_lifecycle_adapter_result_for_authorization(
            authorization.authorization_id
        )
    )
    await order_lifecycle_adapter_result_repository.complete_registration(
        order_lifecycle_adapter_result
    )
    trusted_reader = _TrustedSubmitFactReader()
    evidence_preparation_service = (
        RuntimeExecutionFirstRealSubmitEvidencePreparationService(
            runtime_execution_intent_adapter_service=adapter_service,
            trusted_submit_facts_assembly_service=(
                RuntimeExecutionTrustedSubmitFactsAssemblyService(
                    repository=trusted_submit_facts_repository,
                    account_fact_reader=trusted_reader,
                    active_position_reader=trusted_reader,
                    open_order_reader=trusted_reader,
                    protection_state_reader=trusted_reader,
                    market_rule_reader=trusted_reader,
                    reconciliation_reader=trusted_reader,
                )
            ),
        )
    )
    evidence_preparation = (
        await evidence_preparation_service.prepare_for_authorization(
            authorization.authorization_id,
            adapter_result_store_implemented=True,
            real_adapter_boundary_implemented=False,
        )
    )
    first_real_submit_packet = evidence_preparation.packet
    if first_real_submit_packet is not None:
        rehearsal = first_real_submit_packet.submit_rehearsal
    else:
        rehearsal = await adapter_service.submit_rehearsal_for_authorization(
            authorization.authorization_id
        )

    technical_blockers = _dedupe(
        list(plan.final_gate_preview.blockers)
        + list(draft.blockers)
        + list(intent_preview.blockers)
        + list(submit_readiness.blockers)
        + list(protection_plan.blockers)
        + list(protection_failure_policy.blockers)
        + list(attempt_reservation.blockers)
        + list(attempt_mutation.blockers)
        + list(attempt_outcome_policy.blockers)
        + list(order_lifecycle_handoff.blockers)
        + list(order_lifecycle_adapter_preview.blockers)
        + list(order_registration_draft_preview.blockers)
        + list(evidence_preparation.blockers)
    )
    exchange_submit_rehearsal_blockers = _dedupe(
        list(order_lifecycle_adapter_result.blockers) + list(rehearsal.blockers)
    )
    operational_blockers: list[str] = []
    deployed_head = deployed_head or ""
    current_head_deployed = bool(deployed_head and deployed_head == local_head)
    if require_current_head_deployed and not current_head_deployed:
        operational_blockers.append("current_head_not_deployed_to_tokyo")
    if not owner_real_submit_authorized:
        operational_blockers.append("owner_real_submit_authorization_missing")

    technical_rehearsal_passed = _technical_rehearsal_passed(
        plan=plan,
        draft=draft,
        intent=intent,
        submit_readiness=submit_readiness,
        authorization=authorization,
        controlled_submit_preflight=controlled_submit_preflight,
        submit_adapter_preview=submit_adapter_preview,
    )
    registration_draft_chain_passed = _registration_draft_chain_passed(
        protection_plan=protection_plan,
        attempt_mutation=attempt_mutation,
        order_lifecycle_handoff=order_lifecycle_handoff,
        order_lifecycle_adapter_preview=order_lifecycle_adapter_preview,
        order_registration_draft_preview=order_registration_draft_preview,
    )
    protection_failure_policy_passed = (
        protection_failure_policy.status
        == RuntimeExecutionProtectionFailurePolicyStatus
        .READY_FOR_FIRST_REAL_SUBMIT_CONFIRMATION
        and protection_failure_policy.exchange_called is False
        and protection_failure_policy.order_created is False
        and protection_failure_policy.order_lifecycle_called is False
    )
    forbidden_execution_flags = _forbidden_execution_flags(
        intent=intent,
        authorization=authorization,
        rehearsal=rehearsal,
        protection_plan=protection_plan,
        protection_failure_policy=protection_failure_policy,
        order_lifecycle_handoff=order_lifecycle_handoff,
        order_lifecycle_adapter_preview=order_lifecycle_adapter_preview,
        order_registration_draft_preview=order_registration_draft_preview,
    )
    staged_submit_chain_available = (
        technical_rehearsal_passed
        and registration_draft_chain_passed
        and protection_failure_policy_passed
        and first_real_submit_packet is not None
        and not forbidden_execution_flags
    )
    implementation_blockers: list[str] = []
    if first_real_submit_packet is None:
        implementation_blockers.append("first_real_submit_packet_not_available")

    safety_readiness = evaluate_strategy_runtime_safety_readiness(runtime)
    promotion_gate_result = _promotion_gate_result(
        runtime=runtime,
        current_head_deployed=current_head_deployed,
        owner_real_submit_authorized=owner_real_submit_authorized,
        protection_failure_policy_id=protection_failure_policy.policy_id,
        protection_failure_policy_passed=protection_failure_policy_passed,
        attempt_outcome_policy_id=rehearsal.attempt_outcome_policy_id,
        trusted_submit_fact_snapshot_id=rehearsal.trusted_submit_fact_snapshot_id,
        submit_idempotency_policy_id=rehearsal.submit_idempotency_policy_id,
        local_registration_enablement_decision_id=(
            rehearsal.local_registration_enablement_decision_id
        ),
        exchange_submit_enablement_decision_id=(
            rehearsal.exchange_submit_enablement_decision_id
        ),
        runtime_submit_rehearsal_id=rehearsal.rehearsal_id,
        deployment_readiness_evidence_id=(
            rehearsal.deployment_readiness_evidence_id
        ),
        owner_real_submit_authorization_id=(
            rehearsal.owner_real_submit_authorization_id
        ),
    )
    live_enablement_preview = build_strategy_runtime_live_enablement_preview(
        runtime=runtime,
        safety_readiness=safety_readiness,
        promotion_gate_result=promotion_gate_result,
        current_head_deployed=current_head_deployed,
        owner_live_runtime_enablement_authorized=owner_live_runtime_enablement_authorized,
        owner_real_submit_authorization_present=owner_real_submit_authorized,
        submit_technical_rehearsal_passed=technical_rehearsal_passed,
        submit_adapter_implemented=submit_adapter_preview.submit_adapter_implemented,
        staged_submit_chain_available=staged_submit_chain_available,
        forbidden_execution_flags=forbidden_execution_flags,
    )
    ready_for_live_runtime_enablement = (
        live_enablement_preview.status
        == StrategyRuntimeLiveEnablementPreviewStatus.READY_FOR_LIVE_RUNTIME_ENABLEMENT_MUTATION_DESIGN
    )
    checks = {
        "technical_rehearsal_passed": technical_rehearsal_passed,
        "registration_draft_chain_passed": registration_draft_chain_passed,
        "protection_failure_policy_passed": protection_failure_policy_passed,
        "current_head_deployed": current_head_deployed,
        "owner_real_submit_authorization_present": owner_real_submit_authorized,
        "owner_live_runtime_enablement_authorization_present": (
            owner_live_runtime_enablement_authorized
        ),
        "ready_for_live_runtime_enablement_mutation_design": (
            ready_for_live_runtime_enablement
        ),
        "ready_for_first_real_submit": False,
        "staged_submit_chain_available": staged_submit_chain_available,
        "machine_evidence_preparation_status": _enum_value(
            evidence_preparation.status
        ),
        "machine_evidence_prepared_ids": dict(
            evidence_preparation.prepared_evidence_ids
        ),
        "machine_evidence_available_ids": dict(
            evidence_preparation.available_evidence_ids
        ),
        "machine_evidence_skipped": list(evidence_preparation.skipped_evidence),
        "machine_evidence_blockers": list(evidence_preparation.blockers),
        "technical_blockers": technical_blockers,
        "exchange_submit_rehearsal_blockers": exchange_submit_rehearsal_blockers,
        "protection_failure_policy_blockers": list(
            protection_failure_policy.blockers
        ),
        "operational_blockers": operational_blockers,
        "implementation_blockers": implementation_blockers,
        "live_enablement_blockers": live_enablement_preview.blockers,
        "forbidden_execution_flags": forbidden_execution_flags,
    }
    checks["ready_for_first_real_submit"] = (
        checks["technical_rehearsal_passed"]
        and checks["registration_draft_chain_passed"]
        and checks["protection_failure_policy_passed"]
        and checks["ready_for_live_runtime_enablement_mutation_design"]
        and not technical_blockers
        and not exchange_submit_rehearsal_blockers
        and not operational_blockers
        and not implementation_blockers
        and not checks["forbidden_execution_flags"]
    )

    return {
        "status": (
            "ready_for_owner_controlled_first_real_submit_review"
            if checks["ready_for_first_real_submit"]
            else "blocked_before_first_real_submit"
        ),
        "scope": "runtime_submit_rehearsal_pre_live_packet",
        "repo_root": str(repo_root),
        "local_git": {
            "head": local_head,
            "short_head": short_head,
        },
        "deployment_gate": {
            "deployed_head": deployed_head or None,
            "require_current_head_deployed": require_current_head_deployed,
            "current_head_deployed": current_head_deployed,
        },
        "owner_gate": {
            "owner_real_submit_authorized": owner_real_submit_authorized,
            "owner_live_runtime_enablement_authorized": (
                owner_live_runtime_enablement_authorized
            ),
            "authorization_flag": OWNER_AUTHORIZATION_FLAG,
            "live_runtime_enablement_flag": OWNER_LIVE_RUNTIME_ENABLEMENT_FLAG,
        },
        "pipeline": {
            "plan_status": _enum_value(plan.status),
            "intent_draft_status": _enum_value(draft.status),
            "intent_creation_preview_status": _enum_value(intent_preview.status),
            "recorded_intent_status": _enum_value(intent.status),
            "submit_readiness_status": _enum_value(submit_readiness.status),
            "submit_authorization_status": _enum_value(authorization.status),
            "controlled_submit_preflight_status": (
                _enum_value(controlled_submit_preflight.status)
            ),
            "attempt_reservation_preview_status": (
                _enum_value(attempt_reservation_preview.status)
            ),
            "protection_plan_preview_status": (
                _enum_value(protection_plan_preview.status)
            ),
            "submit_adapter_preview_status": _enum_value(
                submit_adapter_preview.status
            ),
            "submit_rehearsal_status": _enum_value(rehearsal.status),
            "protection_plan_status": _enum_value(protection_plan.status),
            "protection_failure_policy_status": _enum_value(
                protection_failure_policy.status
            ),
            "attempt_mutation_status": _enum_value(attempt_mutation.status),
            "attempt_outcome_policy_status": _enum_value(
                attempt_outcome_policy.status
            ),
            "first_real_submit_evidence_preparation_status": _enum_value(
                evidence_preparation.status
            ),
            "order_lifecycle_handoff_status": _enum_value(
                order_lifecycle_handoff.status
            ),
            "order_lifecycle_adapter_preview_status": _enum_value(
                order_lifecycle_adapter_preview.status
            ),
            "order_registration_draft_preview_status": _enum_value(
                order_registration_draft_preview.status
            ),
            "order_lifecycle_adapter_result_status": _enum_value(
                order_lifecycle_adapter_result.status
            ),
            "safe_stop_stage": getattr(rehearsal, "safe_stop_stage", None),
            "next_required_gate": getattr(rehearsal, "next_required_gate", None),
        },
        "checks": checks,
        "safety_readiness": safety_readiness.model_dump(mode="json"),
        "promotion_gate": promotion_gate_result.model_dump(mode="json"),
        "live_enablement_preview": live_enablement_preview.model_dump(mode="json"),
        "first_real_submit_packet": (
            first_real_submit_packet.model_dump(mode="json")
            if first_real_submit_packet is not None
            else None
        ),
        "evidence_preparation": evidence_preparation.model_dump(mode="json"),
        "rehearsal": rehearsal.model_dump(mode="json"),
        "registration_draft_chain": {
            "scope": "runtime_order_registration_draft_pre_live_evidence",
            "in_memory_runtime_mutation_only": True,
            "runtime_events": list(runtime_service.events),
            "protection_plan": protection_plan.model_dump(mode="json"),
            "protection_failure_policy": (
                protection_failure_policy.model_dump(mode="json")
            ),
            "attempt_reservation": attempt_reservation.model_dump(mode="json"),
            "attempt_mutation": attempt_mutation.model_dump(mode="json"),
            "attempt_outcome_policy": (
                attempt_outcome_policy.model_dump(mode="json")
            ),
            "order_lifecycle_handoff": order_lifecycle_handoff.model_dump(mode="json"),
            "order_lifecycle_adapter_preview": (
                order_lifecycle_adapter_preview.model_dump(mode="json")
            ),
            "order_registration_draft_preview": (
                order_registration_draft_preview.model_dump(mode="json")
            ),
            "order_lifecycle_adapter_result": (
                order_lifecycle_adapter_result.model_dump(mode="json")
            ),
        },
        "safety_invariants": {
            "database_connected": False,
            "remote_files_modified": False,
            "services_restarted": False,
            "migrations_run": False,
            "runtime_started": False,
            "persistent_runtime_budget_mutated": False,
            "runtime_budget_mutated": getattr(
                rehearsal,
                "runtime_budget_mutated",
                False,
            ),
            "attempt_consumed": getattr(rehearsal, "attempt_consumed", False),
            "execution_intent_status_changed": rehearsal.execution_intent_status_changed,
            "order_created": rehearsal.order_created,
            "protection_failure_policy_order_created": (
                protection_failure_policy.order_created
            ),
            "owner_bounded_execution_called": rehearsal.owner_bounded_execution_called,
            "protection_failure_policy_owner_bounded_execution_called": (
                protection_failure_policy.owner_bounded_execution_called
            ),
            "order_lifecycle_called": rehearsal.order_lifecycle_called,
            "protection_failure_policy_order_lifecycle_called": (
                protection_failure_policy.order_lifecycle_called
            ),
            "exchange_called": rehearsal.exchange_called,
            "protection_failure_policy_exchange_called": (
                protection_failure_policy.exchange_called
            ),
            "withdrawal_or_transfer_created": False,
        },
        "notes": [
            "This packet uses in-memory repositories for rehearsal evidence only.",
            "The recorded ExecutionIntent is an in-memory audit artifact, not a persistent executable submit.",
            "The dry-run submit adapter is ready; real order placement remains blocked by OrderLifecycle enablement.",
        ],
    }


def _runtime() -> StrategyRuntimeInstance:
    return StrategyRuntimeInstance(
        runtime_instance_id=DEFAULT_RUNTIME_ID,
        trial_binding_id="pre-live-trial-binding-bnb-long",
        admission_decision_id="pre-live-admission-bnb-long",
        strategy_family_id="CPM-001",
        strategy_family_version_id="CPM-001-v0",
        symbol=DEFAULT_SYMBOL,
        side=DEFAULT_SIDE,
        status=StrategyRuntimeInstanceStatus.ACTIVE,
        boundary=StrategyRuntimeBoundary(
            max_attempts=3,
            attempts_used=0,
            max_active_positions=1,
            max_notional_per_attempt=Decimal("10"),
            total_budget=Decimal("3"),
            budget_reserved=Decimal("0"),
            allowed_symbols=[DEFAULT_SYMBOL],
            allowed_sides=[DEFAULT_SIDE],
            max_leverage=Decimal("1"),
            max_margin_per_attempt=Decimal("10"),
            min_liquidation_stop_buffer=Decimal("25"),
            requires_protection=True,
            requires_review=True,
        ),
        created_at_ms=1781079000000,
        updated_at_ms=1781079000000,
        metadata={
            "scope": "pre_live_submit_rehearsal_packet",
            "small_experimental_risk_capital": True,
            "right_tail_objective": True,
        },
    )


def _candidate() -> OrderCandidate:
    return OrderCandidate(
        order_candidate_id=DEFAULT_ORDER_CANDIDATE_ID,
        signal_evaluation_id="pre-live-rehearsal-signal-evaluation-bnb-long",
        runtime_instance_id=DEFAULT_RUNTIME_ID,
        trial_binding_id="pre-live-trial-binding-bnb-long",
        strategy_family_id="CPM-001",
        strategy_family_version_id="CPM-001-v0",
        symbol=DEFAULT_SYMBOL,
        side=DEFAULT_SIDE,
        candidate_order_type="market",
        proposed_quantity=Decimal("0.016"),
        intended_notional=Decimal("9.60"),
        entry_price_reference=Decimal("600"),
        risk_preview=OrderCandidateRiskPreview(
            intended_notional=Decimal("9.60"),
            proposed_quantity=Decimal("0.016"),
            max_loss_reference=Decimal("0.20"),
            leverage=Decimal("1"),
            margin_required=Decimal("9.60"),
            liquidation_price_reference=Decimal("0"),
            liquidation_stop_buffer=Decimal("100"),
            notes=[
                "loss budget basis is max_loss_reference, not full notional",
                "small bounded loss is acceptable inside runtime boundary",
            ],
        ),
        protection_preview=OrderCandidateProtectionPreview(
            requires_protection=True,
            stop_reference="cpm_pullback_low_or_atr_reference",
            stop_price_reference=Decimal("587.50"),
            take_profit_references=[
                {
                    "kind": "tp1_partial",
                    "rr": "1",
                    "position_ratio": "0.5",
                    "non_executing_preview": True,
                },
                {
                    "kind": "runner",
                    "policy": "trailing_atr_or_structure_invalidation",
                    "right_tail_capture": True,
                    "non_executing_preview": True,
                },
            ],
            notes=[
                "hard stop bounds downside",
                "runner metadata preserves right-tail objective",
            ],
        ),
        rationale="pre-live runtime submit rehearsal packet for bounded CPM long",
        evidence_refs=[
            "pre-live-submit-rehearsal",
            "cpm-reference-semantics",
        ],
        created_at_ms=1781079000000,
        updated_at_ms=1781079000000,
        metadata={
            "scope": "pre_live_submit_rehearsal_candidate",
            "not_proven_alpha": True,
            "non_executing_rehearsal": True,
        },
    )


def _technical_rehearsal_passed(
    *,
    plan: Any,
    draft: RuntimeExecutionIntentDraft,
    intent: ExecutionIntent,
    submit_readiness: Any,
    authorization: RuntimeExecutionSubmitAuthorization,
    controlled_submit_preflight: Any,
    submit_adapter_preview: Any,
) -> bool:
    return (
        plan.status == RuntimeExecutionPlanStatus.READY_FOR_INTENT_DRAFT
        and draft.status == RuntimeExecutionIntentDraftStatus.READY_FOR_INTENT_CREATION
        and intent.status == ExecutionIntentStatus.RECORDED
        and submit_readiness.status
        == RuntimeExecutionSubmitReadinessStatus.OWNER_SUBMIT_AUTHORIZATION_REQUIRED
        and authorization.status
        == RuntimeExecutionSubmitAuthorizationStatus.APPROVED_PENDING_CONTROLLED_SUBMIT
        and controlled_submit_preflight.status
        == RuntimeExecutionControlledSubmitPreflightStatus.READY_FOR_CONTROLLED_SUBMIT_ADAPTER
        and submit_adapter_preview.status
        == RuntimeExecutionSubmitAdapterPreviewStatus.INPUTS_READY_ADAPTER_NOT_IMPLEMENTED
    )


def _registration_draft_chain_passed(
    *,
    protection_plan: Any,
    attempt_mutation: Any,
    order_lifecycle_handoff: Any,
    order_lifecycle_adapter_preview: Any,
    order_registration_draft_preview: Any,
) -> bool:
    return (
        protection_plan.status
        == RuntimeExecutionProtectionPlanStatus.READY_FOR_SUBMIT_ADAPTER
        and attempt_mutation.status == RuntimeExecutionAttemptMutationStatus.APPLIED
        and order_lifecycle_handoff.status
        == RuntimeExecutionOrderLifecycleHandoffStatus.READY_FOR_ORDER_LIFECYCLE_ADAPTER
        and order_lifecycle_adapter_preview.status
        == RuntimeExecutionOrderLifecycleAdapterPreviewStatus.INPUTS_READY_REGISTRATION_NOT_ENABLED
        and order_registration_draft_preview.status
        == (
            RuntimeExecutionOrderRegistrationDraftPreviewStatus
            .INPUTS_READY_REGISTRATION_DRAFT_ONLY
        )
        and order_registration_draft_preview.order_objects_constructed is False
        and order_registration_draft_preview.local_order_registration_executed is False
        and order_registration_draft_preview.order_created is False
        and order_registration_draft_preview.order_lifecycle_called is False
        and order_registration_draft_preview.exchange_called is False
    )


def _promotion_gate_result(
    *,
    runtime: StrategyRuntimeInstance,
    current_head_deployed: bool,
    owner_real_submit_authorized: bool,
    protection_failure_policy_id: str,
    protection_failure_policy_passed: bool,
    attempt_outcome_policy_id: str | None,
    trusted_submit_fact_snapshot_id: str | None,
    submit_idempotency_policy_id: str | None,
    local_registration_enablement_decision_id: str | None,
    exchange_submit_enablement_decision_id: str | None,
    runtime_submit_rehearsal_id: str | None,
    deployment_readiness_evidence_id: str | None,
    owner_real_submit_authorization_id: str | None,
):
    binding = initial_strategy_semantics_catalog().get_binding(
        strategy_family_id=runtime.strategy_family_id,
        strategy_family_version_id=runtime.strategy_family_version_id,
    )
    return evaluate_strategy_runtime_promotion_gate(
        StrategyRuntimePromotionGateInput(
            binding=binding,
            scope=StrategyRuntimePromotionScope.FIRST_REAL_SUBMIT_GATE_REVIEW,
            semantic_confirmations=StrategySemanticsConfirmationFacts(
                strategy_family_confirmed=True,
                implementation_source_confirmed=True,
                required_facts_confirmed=True,
                entry_policy_confirmed=True,
                exit_policy_confirmed=True,
                protection_policy_confirmed=True,
                eligible_for_runtime_execution_confirmed=True,
                right_tail_review_metrics_confirmed=True,
            ),
            runtime_confirmations=RuntimeExecutionConfirmationFacts(
                runtime_profile_confirmed=True,
                owner_confirmation_mode_confirmed=True,
                symbol_side_boundary_confirmed=True,
                max_loss_budget_confirmed=True,
                max_notional_boundary_confirmed=True,
                max_active_positions_boundary_confirmed=True,
                max_leverage_boundary_confirmed=True,
                margin_usage_boundary_confirmed=True,
                liquidation_buffer_boundary_confirmed=True,
                protection_readiness_source_confirmed=True,
                stale_fact_behavior_confirmed=True,
                attempt_consumption_rule_confirmed=True,
                budget_reservation_rule_confirmed=True,
                trusted_active_position_source_confirmed=True,
                trusted_account_fact_source_confirmed=True,
            ),
            first_real_submit_confirmations=FirstRealSubmitConfirmationFacts(
                budget_release_or_consume_rule_confirmed=True,
                protection_creation_failure_policy_confirmed=(
                    protection_failure_policy_passed
                ),
                attempt_outcome_policy_id=attempt_outcome_policy_id,
                trusted_submit_fact_snapshot_id=trusted_submit_fact_snapshot_id,
                submit_idempotency_policy_id=submit_idempotency_policy_id,
                protection_creation_failure_policy_id=protection_failure_policy_id,
                local_registration_enablement_decision_id=(
                    local_registration_enablement_decision_id
                ),
                exchange_submit_enablement_decision_id=(
                    exchange_submit_enablement_decision_id
                ),
                runtime_submit_rehearsal_id=runtime_submit_rehearsal_id,
                deployment_readiness_evidence_id=deployment_readiness_evidence_id,
                owner_real_submit_authorization_id=owner_real_submit_authorization_id,
                duplicate_submit_policy_confirmed=True,
                deployment_readiness_confirmed=current_head_deployed,
                explicit_owner_real_submit_authorization=owner_real_submit_authorized,
            ),
        )
    )


def _forbidden_execution_flags(
    *,
    intent: ExecutionIntent,
    authorization: RuntimeExecutionSubmitAuthorization,
    rehearsal: Any,
    protection_plan: Any,
    protection_failure_policy: Any,
    order_lifecycle_handoff: Any,
    order_lifecycle_adapter_preview: Any,
    order_registration_draft_preview: Any,
) -> list[str]:
    flags: list[str] = []
    if intent.status != ExecutionIntentStatus.RECORDED:
        flags.append("execution_intent_not_recorded_audit_status")
    if intent.order_id is not None or intent.exchange_order_id is not None:
        flags.append("execution_intent_contains_order_artifact")
    checks = {
        "authorization_submit_executed": authorization.submit_executed,
        "authorization_order_created": authorization.order_created,
        "authorization_exchange_called": authorization.exchange_called,
        "authorization_owner_bounded_execution_called": (
            authorization.owner_bounded_execution_called
        ),
        "authorization_order_lifecycle_called": authorization.order_lifecycle_called,
        "rehearsal_submit_executed": getattr(rehearsal, "submit_executed", False),
        "rehearsal_runtime_budget_mutated": getattr(
            rehearsal,
            "runtime_budget_mutated",
            False,
        ),
        "rehearsal_attempt_consumed": getattr(
            rehearsal,
            "attempt_consumed",
            False,
        ),
        "rehearsal_execution_intent_status_changed": (
            rehearsal.execution_intent_status_changed
        ),
        "rehearsal_order_created": rehearsal.order_created,
        "rehearsal_exchange_called": rehearsal.exchange_called,
        "rehearsal_owner_bounded_execution_called": (
            rehearsal.owner_bounded_execution_called
        ),
        "rehearsal_order_lifecycle_called": rehearsal.order_lifecycle_called,
        "protection_plan_order_created": protection_plan.order_created,
        "protection_plan_exchange_called": protection_plan.exchange_called,
        "protection_plan_owner_bounded_execution_called": (
            protection_plan.owner_bounded_execution_called
        ),
        "protection_plan_order_lifecycle_called": (
            protection_plan.order_lifecycle_called
        ),
        "protection_failure_policy_order_created": (
            protection_failure_policy.order_created
        ),
        "protection_failure_policy_exchange_called": (
            protection_failure_policy.exchange_called
        ),
        "protection_failure_policy_owner_bounded_execution_called": (
            protection_failure_policy.owner_bounded_execution_called
        ),
        "protection_failure_policy_order_lifecycle_called": (
            protection_failure_policy.order_lifecycle_called
        ),
        "order_lifecycle_handoff_execution_intent_status_changed": (
            order_lifecycle_handoff.execution_intent_status_changed
        ),
        "order_lifecycle_handoff_order_created": order_lifecycle_handoff.order_created,
        "order_lifecycle_handoff_exchange_called": (
            order_lifecycle_handoff.exchange_called
        ),
        "order_lifecycle_handoff_owner_bounded_execution_called": (
            order_lifecycle_handoff.owner_bounded_execution_called
        ),
        "order_lifecycle_handoff_order_lifecycle_called": (
            order_lifecycle_handoff.order_lifecycle_called
        ),
        "order_lifecycle_adapter_execution_intent_status_changed": (
            order_lifecycle_adapter_preview.execution_intent_status_changed
        ),
        "order_lifecycle_adapter_order_created": (
            order_lifecycle_adapter_preview.order_created
        ),
        "order_lifecycle_adapter_exchange_called": (
            order_lifecycle_adapter_preview.exchange_called
        ),
        "order_lifecycle_adapter_owner_bounded_execution_called": (
            order_lifecycle_adapter_preview.owner_bounded_execution_called
        ),
        "order_lifecycle_adapter_order_lifecycle_called": (
            order_lifecycle_adapter_preview.order_lifecycle_called
        ),
        "order_registration_draft_order_objects_constructed": (
            order_registration_draft_preview.order_objects_constructed
        ),
        "order_registration_draft_local_order_registration_executed": (
            order_registration_draft_preview.local_order_registration_executed
        ),
        "order_registration_draft_execution_intent_status_changed": (
            order_registration_draft_preview.execution_intent_status_changed
        ),
        "order_registration_draft_order_created": (
            order_registration_draft_preview.order_created
        ),
        "order_registration_draft_exchange_called": (
            order_registration_draft_preview.exchange_called
        ),
        "order_registration_draft_owner_bounded_execution_called": (
            order_registration_draft_preview.owner_bounded_execution_called
        ),
        "order_registration_draft_order_lifecycle_called": (
            order_registration_draft_preview.order_lifecycle_called
        ),
    }
    flags.extend(key for key, value in checks.items() if value)
    return flags


def _repo_root(*, runner: Any | None = None) -> Path:
    result = _run(("git", "rev-parse", "--show-toplevel"), cwd=Path.cwd(), runner=runner)
    if result.returncode != 0 or not result.stdout:
        raise RuntimeError("not_inside_git_repository")
    return Path(result.stdout)


def _git(repo_root: Path, *args: str, runner: Any | None = None) -> CommandResult:
    result = _run(("git", *args), cwd=repo_root, runner=runner)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed")
    return result


def _run(
    command: tuple[str, ...],
    *,
    cwd: Path,
    runner: Any | None = None,
) -> CommandResult:
    if runner is not None:
        return runner(command, cwd)
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout = completed.stdout.strip()
    if completed.returncode != 0 and completed.stderr.strip():
        stdout = completed.stderr.strip()
    return CommandResult(stdout=stdout, returncode=completed.returncode)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _now_ms() -> int:
    return int(time.time() * 1000)


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a local non-executing pre-live runtime submit rehearsal packet."
        )
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument(
        "--deployed-head",
        default=DEFAULT_DEPLOYED_HEAD,
        help=(
            "Read-only deployed head used for the current-head deployment gate. "
            "Pass the post-deploy probe head when verifying after deployment."
        ),
    )
    parser.add_argument(
        "--skip-current-head-deployed-check",
        action="store_true",
        help="Do not block when local HEAD differs from --deployed-head.",
    )
    parser.add_argument(
        OWNER_AUTHORIZATION_FLAG,
        action="store_true",
        help=(
            "Mark the Owner first-real-submit authorization gate as present for "
            "readiness accounting only. This script still does not submit."
        ),
    )
    parser.add_argument(
        OWNER_LIVE_RUNTIME_ENABLEMENT_FLAG,
        action="store_true",
        help=(
            "Mark the Owner live-runtime enablement gate as present for readiness "
            "accounting only. This script still does not mutate the runtime."
        ),
    )
    parser.add_argument(
        "--active-positions",
        type=int,
        default=0,
        help="Injected local active-position count for the in-memory rehearsal.",
    )
    return parser.parse_args(argv)


def _print_human(report: dict[str, Any]) -> None:
    checks = report["checks"]
    pipeline = report["pipeline"]
    print(f"status={report['status']}")
    print(f"technical_rehearsal_passed={str(checks['technical_rehearsal_passed']).lower()}")
    print(f"current_head_deployed={str(checks['current_head_deployed']).lower()}")
    print(
        "owner_real_submit_authorization_present="
        + str(checks["owner_real_submit_authorization_present"]).lower()
    )
    print(
        "owner_live_runtime_enablement_authorization_present="
        + str(checks["owner_live_runtime_enablement_authorization_present"]).lower()
    )
    print(
        "ready_for_live_runtime_enablement_mutation_design="
        + str(checks["ready_for_live_runtime_enablement_mutation_design"]).lower()
    )
    print(f"ready_for_first_real_submit={str(checks['ready_for_first_real_submit']).lower()}")
    print(f"submit_rehearsal_status={pipeline['submit_rehearsal_status']}")
    print(f"submit_adapter_preview_status={pipeline['submit_adapter_preview_status']}")
    if checks["technical_blockers"]:
        print("technical_blockers=" + ",".join(checks["technical_blockers"]))
    if checks["operational_blockers"]:
        print("operational_blockers=" + ",".join(checks["operational_blockers"]))
    if checks["implementation_blockers"]:
        print(
            "implementation_blockers="
            + ",".join(checks["implementation_blockers"])
        )
    if checks["live_enablement_blockers"]:
        print(
            "live_enablement_blockers="
            + ",".join(checks["live_enablement_blockers"])
        )
    if checks["forbidden_execution_flags"]:
        print("forbidden_execution_flags=" + ",".join(checks["forbidden_execution_flags"]))


async def _amain(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    report = await build_pre_live_packet(
        deployed_head=args.deployed_head,
        owner_real_submit_authorized=args.owner_real_submit_authorized,
        owner_live_runtime_enablement_authorized=(
            args.owner_live_runtime_enable_authorized
        ),
        require_current_head_deployed=not args.skip_current_head_deployed_check,
        active_positions=args.active_positions,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_human(report)
    return 0 if report["checks"]["technical_rehearsal_passed"] else 2


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_amain(argv))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"pre_live_packet_error={exc}", file=sys.stderr)
        raise SystemExit(2)
