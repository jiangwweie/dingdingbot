"""BRC Owner Console Operation Layer.

This layer is the authorization, preflight, confirmation, execution, and audit
boundary for Owner Console actions. It intentionally exposes only explicit
operation adapters; it is not a generic trading or workflow runner.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal, Optional, Protocol

from pydantic import BaseModel, Field

from src.application.execution_permission import (
    ExecutionPermission,
    ExecutionPermissionResolver,
    permission_allows,
)
from src.application.bounded_risk_campaign_service import (
    BoundedRiskCampaignService,
    BrcRuleViolation,
)
from src.domain.bounded_risk_campaign import (
    BrcDecisionResult,
    BrcReviewDecision,
    RiskChangeDirection,
    default_playbook_catalog,
)


OperationType = Literal[
    "switch_playbook",
    "start_review",
    "write_review_decision",
    "run_fixed_testnet_rehearsal",
    "enter_observe",
    "enter_pause",
    "revoke_budget",
    "enter_strategy_or_monitor",
    "pause_new_entries",
    "emergency_stop_runtime",
    "emergency_flatten",
    "create_gated_trial_from_admission",
    "create_campaign_from_admission_binding",
    "install_runtime_constraints_from_admission_campaign",
    "prepare_runtime_carrier_from_admission_campaign",
    "prepare_runtime_start_from_admission_carrier",
    "evaluate_trial_trade_intent",
    "prepare_runtime_handoff_from_admission_campaign",
    "start_runtime_from_admission_handoff",
    "prepare_strategy_activation_from_admission_runtime",
    "activate_strategy_from_admission_runtime",
    "prepare_signal_loop_from_admission_strategy",
    "start_signal_loop_from_admission_strategy",
    "evaluate_signal_from_admission_strategy",
    "record_trial_trade_intent_from_signal_evaluation",
    "live_execution",
    "unrestricted_order_execution",
    "withdrawal",
    "transfer",
    "arbitrary_symbol_order",
    "arbitrary_strategy_router",
    "arbitrary_side_size_order",
    "llm_direct_execution",
]
CapabilityStatus = Literal[
    "enabled",
    "available",
    "binding_reservation_available",
    "campaign_shell_creation_available",
    "operation_preflight_available",
    "preflight_planning_available",
    "preflight_dry_run_available",
    "legacy_dev_path",
    "requires_operation_layer",
    "design_surface_with_preflight",
    "design_surface",
    "unavailable",
    "forbidden",
    "not_implemented",
]
OperationStatus = Literal[
    "draft",
    "awaiting_confirmation",
    "executing",
    "executed",
    "blocked",
    "failed",
    "cancelled",
    "expired",
    "noop",
]
PreflightDecision = Literal["allow", "warn", "block", "unavailable", "expired"]
ExecutionStatus = Literal["executed", "blocked", "failed", "cancelled", "expired", "noop"]


def now_ms() -> int:
    return int(time.time() * 1000)


class OperationLayerError(ValueError):
    """Raised for invalid operation-layer requests."""


class ConfirmationMismatch(OperationLayerError):
    """Raised when a terminal operation cannot accept a new confirmation."""


class OperationCapability(BaseModel):
    operation_type: str
    status: CapabilityStatus
    display_name: str
    risk_level: Literal["read_only", "low", "medium", "high", "forbidden"]
    allowed_env: list[str] = Field(default_factory=list)
    confirmation_required: bool = True
    backend_executor: Optional[str] = None
    current_reason: str
    requires_operation_layer: bool = True
    executable_through_operation: bool = False
    dry_run_only: bool = False


class OperationPolicy(BaseModel):
    operation_type: str
    display_name: str
    risk_level: Literal["read_only", "low", "medium", "high", "forbidden"]
    allowed_env: list[str] = Field(default_factory=list)
    confirmation_phrase: Optional[str] = None
    capability_status: CapabilityStatus
    current_reason: str
    backend_executor: Optional[str] = None
    executable_through_operation: bool = False
    dry_run_only: bool = False

    def capability(self) -> OperationCapability:
        return OperationCapability(
            operation_type=self.operation_type,
            status=self.capability_status,
            display_name=self.display_name,
            risk_level=self.risk_level,
            allowed_env=list(self.allowed_env),
            confirmation_required=(
                self.confirmation_phrase is not None
                and (self.executable_through_operation or self.dry_run_only)
            ),
            backend_executor=self.backend_executor,
            current_reason=self.current_reason,
            executable_through_operation=self.executable_through_operation,
            dry_run_only=self.dry_run_only,
        )


class ConfirmationRequirement(BaseModel):
    required: bool
    phrase: Optional[str] = None
    expires_at_ms: int
    totp_freshness_required: bool = False


class OperationRecord(BaseModel):
    operation_id: str
    operation_type: str
    requested_by: str
    requested_at_ms: int
    source_type: str = "ui"
    source_ref: Optional[str] = None
    input_params: dict[str, Any] = Field(default_factory=dict)
    environment: str = "local"
    risk_level: str
    status: OperationStatus
    current_preflight_id: Optional[str] = None
    confirmed_by: Optional[str] = None
    confirmed_at_ms: Optional[int] = None
    executed_at_ms: Optional[int] = None
    result_status: Optional[ExecutionStatus] = None
    result_summary: dict[str, Any] = Field(default_factory=dict)
    created_audit_refs: list[dict[str, Any]] = Field(default_factory=list)


class PreflightSnapshot(BaseModel):
    preflight_id: str
    operation_id: str
    operation_type: str
    created_at_ms: int
    expires_at_ms: int
    current_state_snapshot: dict[str, Any] = Field(default_factory=dict)
    target_state: dict[str, Any] = Field(default_factory=dict)
    account_snapshot: dict[str, Any] = Field(default_factory=dict)
    order_snapshot: dict[str, Any] = Field(default_factory=dict)
    runtime_snapshot: dict[str, Any] = Field(default_factory=dict)
    campaign_snapshot: dict[str, Any] = Field(default_factory=dict)
    playbook_snapshot: dict[str, Any] = Field(default_factory=dict)
    risk_result: dict[str, Any] = Field(default_factory=dict)
    decision: PreflightDecision
    warnings: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    confirmation_requirement: ConfirmationRequirement
    snapshot_hash: str
    idempotency_key: str
    summary: str
    before: dict[str, Any] = Field(default_factory=dict)
    after: dict[str, Any] = Field(default_factory=dict)


class ExecutionResult(BaseModel):
    operation_id: str
    preflight_id: str
    status: ExecutionStatus
    rechecked: bool = True
    recheck_result: dict[str, Any] = Field(default_factory=dict)
    adapter_result: dict[str, Any] = Field(default_factory=dict)
    blocked_reason: Optional[str] = None
    failed_reason: Optional[str] = None
    result_summary: dict[str, Any] = Field(default_factory=dict)
    audit_refs: list[dict[str, Any]] = Field(default_factory=list)
    campaign_refs: list[dict[str, Any]] = Field(default_factory=list)
    review_refs: list[dict[str, Any]] = Field(default_factory=list)
    final_state_snapshot: dict[str, Any] = Field(default_factory=dict)
    occurred_at_ms: int = Field(default_factory=now_ms)


class OperationPreflightResponse(BaseModel):
    operation_id: str
    preflight_id: str
    operation_type: str
    decision: PreflightDecision
    summary: str
    before: dict[str, Any] = Field(default_factory=dict)
    after: dict[str, Any] = Field(default_factory=dict)
    account_order_summary: dict[str, Any] = Field(default_factory=dict)
    runtime_summary: dict[str, Any] = Field(default_factory=dict)
    campaign_summary: dict[str, Any] = Field(default_factory=dict)
    playbook_summary: dict[str, Any] = Field(default_factory=dict)
    risk_summary: dict[str, Any] = Field(default_factory=dict)
    admission_summary: dict[str, Any] = Field(default_factory=dict)
    strategy_family_summary: dict[str, Any] = Field(default_factory=dict)
    constraints_summary: dict[str, Any] = Field(default_factory=dict)
    owner_risk_acceptance_summary: dict[str, Any] = Field(default_factory=dict)
    binding_summary: dict[str, Any] = Field(default_factory=dict)
    campaign_shell_summary: dict[str, Any] = Field(default_factory=dict)
    runtime_carrier_summary: dict[str, Any] = Field(default_factory=dict)
    runtime_start_summary: dict[str, Any] = Field(default_factory=dict)
    runtime_handoff_summary: dict[str, Any] = Field(default_factory=dict)
    strategy_activation_summary: dict[str, Any] = Field(default_factory=dict)
    signal_loop_summary: dict[str, Any] = Field(default_factory=dict)
    signal_evaluation_summary: dict[str, Any] = Field(default_factory=dict)
    trade_intent_summary: dict[str, Any] = Field(default_factory=dict)
    next_step: Optional[str] = None
    confirmation_requirement: ConfirmationRequirement
    idempotency_key: str
    status: OperationStatus


class OperationConfirmResponse(BaseModel):
    operation_id: str
    preflight_id: str
    status: ExecutionStatus
    rechecked: bool
    result_summary: dict[str, Any] = Field(default_factory=dict)
    audit_refs: list[dict[str, Any]] = Field(default_factory=list)
    campaign_refs: list[dict[str, Any]] = Field(default_factory=list)
    review_refs: list[dict[str, Any]] = Field(default_factory=list)
    next_state: dict[str, Any] = Field(default_factory=dict)


class OperationDetailResponse(BaseModel):
    operation: OperationRecord
    preflight: Optional[PreflightSnapshot] = None
    result: Optional[ExecutionResult] = None
    live_ready: Literal[False] = False


class OperationListResponse(BaseModel):
    operations: list[OperationRecord]
    live_ready: Literal[False] = False


class OperationRepositoryPort(Protocol):
    async def initialize(self) -> None:
        ...

    async def save_operation(self, operation: OperationRecord) -> OperationRecord:
        ...

    async def get_operation(self, operation_id: str) -> Optional[OperationRecord]:
        ...

    async def list_operations(self, *, limit: int = 50) -> list[OperationRecord]:
        ...

    async def save_preflight(self, preflight: PreflightSnapshot) -> PreflightSnapshot:
        ...

    async def get_preflight(self, preflight_id: str) -> Optional[PreflightSnapshot]:
        ...

    async def save_execution_result(self, result: ExecutionResult) -> ExecutionResult:
        ...

    async def get_execution_result(self, operation_id: str) -> Optional[ExecutionResult]:
        ...


class InMemoryOperationRepository:
    """Test and degraded-dev repository; production uses PG."""

    def __init__(self) -> None:
        self.operations: dict[str, OperationRecord] = {}
        self.preflights: dict[str, PreflightSnapshot] = {}
        self.results: dict[str, ExecutionResult] = {}

    async def initialize(self) -> None:
        return None

    async def save_operation(self, operation: OperationRecord) -> OperationRecord:
        self.operations[operation.operation_id] = operation
        return operation

    async def get_operation(self, operation_id: str) -> Optional[OperationRecord]:
        return self.operations.get(operation_id)

    async def list_operations(self, *, limit: int = 50) -> list[OperationRecord]:
        items = sorted(self.operations.values(), key=lambda item: item.requested_at_ms, reverse=True)
        return items[:limit]

    async def save_preflight(self, preflight: PreflightSnapshot) -> PreflightSnapshot:
        self.preflights[preflight.preflight_id] = preflight
        return preflight

    async def get_preflight(self, preflight_id: str) -> Optional[PreflightSnapshot]:
        return self.preflights.get(preflight_id)

    async def save_execution_result(self, result: ExecutionResult) -> ExecutionResult:
        self.results[result.operation_id] = result
        return result

    async def get_execution_result(self, operation_id: str) -> Optional[ExecutionResult]:
        return self.results.get(operation_id)


@dataclass(frozen=True)
class OperationLayerReaders:
    runtime_summary: Callable[[], Awaitable[dict[str, Any]]]
    markets_orders_summary: Callable[[], Awaitable[dict[str, Any]]]
    audit_writable: Callable[[], Awaitable[bool]]
    runtime_safety_readiness: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None
    review_packet_reader: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None
    runtime_transition: Optional[Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]] = None
    budget_authorization_summary: Optional[Callable[[], Awaitable[dict[str, Any]]]] = None
    budget_revoke_executor: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None
    runtime_stop_executor: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None
    fixed_rehearsal_executor: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None
    admission_readiness: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None
    admission_binding_reserver: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None
    admission_campaign_readiness: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None
    admission_campaign_creator: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None
    admission_runtime_constraint_readiness: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None
    admission_runtime_constraint_installer: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None
    admission_runtime_carrier_readiness: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None
    admission_runtime_carrier_preparer: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None
    admission_runtime_start_readiness: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None
    admission_runtime_start_preparer: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None
    trial_trade_intent_readiness: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None
    trial_trade_intent_evaluator: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None
    admission_runtime_handoff_readiness: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None
    admission_runtime_handoff_preparer: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None
    admission_runtime_start_from_handoff_readiness: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None
    admission_runtime_start_from_handoff_starter: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None
    admission_strategy_activation_readiness: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None
    admission_strategy_activation_preparer: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None
    admission_strategy_state_activation_readiness: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None
    admission_strategy_state_activator: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None
    admission_signal_loop_readiness: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None
    admission_signal_loop_preparer: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None
    admission_signal_loop_start_readiness: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None
    admission_signal_loop_starter: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None
    admission_signal_evaluation_readiness: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None
    admission_signal_evaluator: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None
    signal_trade_intent_readiness: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None
    signal_trade_intent_recorder: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None


async def _empty_runtime_summary() -> dict[str, Any]:
    return {"runtime_bound": False, "source": "operation_layer_default"}


async def _empty_markets_orders_summary() -> dict[str, Any]:
    return {
        "active_position_count": 0,
        "open_order_count": 0,
        "all_local_flat": True,
        "data_source": "operation_layer_default",
    }


async def _default_audit_writable() -> bool:
    return True


class OperationRegistry:
    def __init__(self) -> None:
        self._policies = _build_default_policies()

    def list_capabilities(self) -> list[OperationCapability]:
        return [policy.capability() for policy in self._policies.values()]

    def get_policy(self, operation_type: str) -> OperationPolicy:
        policy = self._policies.get(operation_type)
        if policy is None:
            raise OperationLayerError(f"unknown operation_type: {operation_type}")
        return policy


class BrcOperationService:
    def __init__(
        self,
        *,
        repository: OperationRepositoryPort,
        brc_campaign_service: Optional[BoundedRiskCampaignService],
        readers: Optional[OperationLayerReaders] = None,
        registry: Optional[OperationRegistry] = None,
        execution_permission_resolver: Optional[ExecutionPermissionResolver] = None,
        ttl_ms: int = 5 * 60 * 1000,
    ) -> None:
        self._repo = repository
        self._brc = brc_campaign_service
        self._readers = readers or OperationLayerReaders(
            runtime_summary=_empty_runtime_summary,
            markets_orders_summary=_empty_markets_orders_summary,
            audit_writable=_default_audit_writable,
        )
        self._registry = registry or OperationRegistry()
        self._execution_permission_resolver = execution_permission_resolver or ExecutionPermissionResolver()
        self._ttl_ms = ttl_ms
        self._catalog = default_playbook_catalog()

    async def initialize(self) -> None:
        await self._repo.initialize()

    def capabilities(self) -> list[OperationCapability]:
        return [
            self._effective_policy(capability.operation_type).capability()
            for capability in self._registry.list_capabilities()
        ]

    async def preflight(
        self,
        *,
        operation_type: str,
        requested_by: str,
        input_params: dict[str, Any],
        source: Optional[dict[str, Any]] = None,
    ) -> OperationPreflightResponse:
        policy = self._effective_policy(operation_type)
        source_payload = dict(source or {})
        source_type = str(source_payload.get("kind") or "ui")
        source_ref = source_payload.get("ref")
        now = now_ms()
        operation_id = f"op_{uuid.uuid4().hex[:16]}"
        preflight_id = f"pre_{uuid.uuid4().hex[:16]}"
        expires_at_ms = now + self._ttl_ms

        operation = OperationRecord(
            operation_id=operation_id,
            operation_type=operation_type,
            requested_by=requested_by,
            requested_at_ms=now,
            source_type=source_type,
            source_ref=str(source_ref) if source_ref is not None else None,
            input_params=dict(input_params),
            environment="local",
            risk_level=policy.risk_level,
            status="draft",
        )

        runtime_summary = await self._readers.runtime_summary()
        market_summary = await self._readers.markets_orders_summary()
        campaign_summary = await self._campaign_summary()
        playbook_summary = self._playbook_preflight_summary(input_params)
        budget_authorization_summary: Optional[dict[str, Any]] = None
        if operation_type == "revoke_budget":
            budget_authorization_summary = await self._budget_authorization_summary()
        admission_readiness: Optional[dict[str, Any]] = None
        if operation_type == "create_gated_trial_from_admission":
            admission_readiness = await self._admission_readiness(input_params)
        admission_campaign_readiness: Optional[dict[str, Any]] = None
        if operation_type == "create_campaign_from_admission_binding":
            admission_campaign_readiness = await self._admission_campaign_readiness(input_params)
        runtime_constraint_readiness: Optional[dict[str, Any]] = None
        if operation_type == "install_runtime_constraints_from_admission_campaign":
            runtime_constraint_readiness = await self._admission_runtime_constraint_readiness(input_params)
        runtime_carrier_readiness: Optional[dict[str, Any]] = None
        if operation_type == "prepare_runtime_carrier_from_admission_campaign":
            runtime_carrier_readiness = await self._admission_runtime_carrier_readiness(input_params)
        runtime_start_readiness: Optional[dict[str, Any]] = None
        if operation_type == "prepare_runtime_start_from_admission_carrier":
            runtime_start_readiness = await self._admission_runtime_start_readiness(input_params)
        trade_intent_readiness: Optional[dict[str, Any]] = None
        if operation_type == "evaluate_trial_trade_intent":
            trade_intent_readiness = await self._trial_trade_intent_readiness(input_params)
        runtime_handoff_readiness: Optional[dict[str, Any]] = None
        if operation_type == "prepare_runtime_handoff_from_admission_campaign":
            runtime_handoff_readiness = await self._admission_runtime_handoff_readiness(input_params)
        start_runtime_readiness: Optional[dict[str, Any]] = None
        if operation_type == "start_runtime_from_admission_handoff":
            start_runtime_readiness = await self._admission_runtime_start_from_handoff_readiness(input_params)
        strategy_activation_readiness: Optional[dict[str, Any]] = None
        if operation_type == "prepare_strategy_activation_from_admission_runtime":
            strategy_activation_readiness = await self._admission_strategy_activation_readiness(input_params)
        strategy_state_activation_readiness: Optional[dict[str, Any]] = None
        if operation_type == "activate_strategy_from_admission_runtime":
            strategy_state_activation_readiness = await self._admission_strategy_state_activation_readiness(input_params)
        signal_loop_readiness: Optional[dict[str, Any]] = None
        if operation_type == "prepare_signal_loop_from_admission_strategy":
            signal_loop_readiness = await self._admission_signal_loop_readiness(input_params)
        signal_loop_start_readiness: Optional[dict[str, Any]] = None
        if operation_type == "start_signal_loop_from_admission_strategy":
            signal_loop_start_readiness = await self._admission_signal_loop_start_readiness(input_params)
        signal_evaluation_readiness: Optional[dict[str, Any]] = None
        if operation_type == "evaluate_signal_from_admission_strategy":
            signal_evaluation_readiness = await self._admission_signal_evaluation_readiness(input_params)
        signal_trade_intent_readiness: Optional[dict[str, Any]] = None
        if operation_type == "record_trial_trade_intent_from_signal_evaluation":
            runtime_summary = await self._runtime_summary_with_safety_readiness(
                input_params=input_params,
                runtime_summary=runtime_summary,
            )
            signal_trade_intent_readiness = await self._signal_trade_intent_readiness(input_params)
            permission_resolution = self._execution_permission_resolver.resolve(
                requested_permission=ExecutionPermission.INTENT_RECORDING,
                operation_type=operation_type,
                operation_permission=ExecutionPermission.INTENT_RECORDING,
                account_facts=dict(signal_trade_intent_readiness.get("account_facts") or {}),
                constraints_check=dict(signal_trade_intent_readiness.get("constraints_check") or {}),
                campaign_metadata=dict(signal_trade_intent_readiness.get("campaign_metadata") or {}),
                runtime_summary=runtime_summary,
            )
            resolution_summary = permission_resolution.to_summary()
            signal_trade_intent_readiness["execution_permission_resolution"] = resolution_summary
            if not permission_allows(
                permission_resolution.final_permission,
                ExecutionPermission.INTENT_RECORDING,
            ):
                signal_trade_intent_readiness.setdefault("blockers", [])
                signal_trade_intent_readiness["blockers"].extend(permission_resolution.blockers)
            signal_trade_intent_readiness.setdefault("warnings", [])
            signal_trade_intent_readiness["warnings"].extend(permission_resolution.warnings)

        audit_writable = (
            await self._readers.audit_writable()
            if operation_type in {
                "emergency_stop_runtime",
                "create_gated_trial_from_admission",
                "create_campaign_from_admission_binding",
                "install_runtime_constraints_from_admission_campaign",
                "prepare_runtime_carrier_from_admission_campaign",
                "prepare_runtime_start_from_admission_carrier",
                "evaluate_trial_trade_intent",
                "prepare_runtime_handoff_from_admission_campaign",
                "start_runtime_from_admission_handoff",
                "prepare_strategy_activation_from_admission_runtime",
                "activate_strategy_from_admission_runtime",
                "prepare_signal_loop_from_admission_strategy",
                "start_signal_loop_from_admission_strategy",
                "evaluate_signal_from_admission_strategy",
                "record_trial_trade_intent_from_signal_evaluation",
            }
            else None
        )
        decision, blockers, warnings, summary, before, after = self._preflight_decision(
            policy=policy,
            input_params=input_params,
            runtime_summary=runtime_summary,
            campaign_summary=campaign_summary,
            market_summary=market_summary,
            audit_writable=audit_writable,
            admission_readiness=admission_readiness,
            admission_campaign_readiness=admission_campaign_readiness,
            runtime_constraint_readiness=runtime_constraint_readiness,
            runtime_carrier_readiness=runtime_carrier_readiness,
            runtime_start_readiness=runtime_start_readiness,
            trade_intent_readiness=trade_intent_readiness,
            runtime_handoff_readiness=runtime_handoff_readiness,
            start_runtime_readiness=start_runtime_readiness,
            strategy_activation_readiness=strategy_activation_readiness,
            strategy_state_activation_readiness=strategy_state_activation_readiness,
            signal_loop_readiness=signal_loop_readiness,
            signal_loop_start_readiness=signal_loop_start_readiness,
            signal_evaluation_readiness=signal_evaluation_readiness,
            signal_trade_intent_readiness=signal_trade_intent_readiness,
            budget_authorization_summary=budget_authorization_summary,
        )
        dry_run_plan = after.get("dry_run_plan")
        if operation_type == "emergency_flatten" and isinstance(dry_run_plan, dict):
            dry_run_plan["operation_id"] = operation_id
        status: OperationStatus = "awaiting_confirmation" if decision in {"allow", "warn"} else "blocked"
        idempotency_key = f"idem_{uuid.uuid4().hex[:16]}"
        confirmation = ConfirmationRequirement(
            required=policy.confirmation_phrase is not None and status == "awaiting_confirmation",
            phrase=policy.confirmation_phrase if status == "awaiting_confirmation" else None,
            expires_at_ms=expires_at_ms,
            totp_freshness_required=False,
        )
        risk_result = {
            "passed": self._passed_checks(decision=decision, blockers=blockers),
            "warnings": warnings,
            "blockers": blockers,
        }
        snapshot_source = {
            "operation_type": operation_type,
            "input_params": input_params,
            "runtime": runtime_summary,
            "market": market_summary,
            "campaign": campaign_summary,
            "playbook": playbook_summary,
            "budget_authorization": budget_authorization_summary or {},
            "risk": risk_result,
            "admission": admission_readiness or {},
            "admission_campaign": admission_campaign_readiness or {},
            "runtime_constraint_install": runtime_constraint_readiness or {},
            "runtime_carrier_prepare": runtime_carrier_readiness or {},
            "runtime_start_prepare": runtime_start_readiness or {},
            "trial_trade_intent": trade_intent_readiness or {},
            "runtime_handoff_prepare": runtime_handoff_readiness or {},
            "start_runtime_from_handoff": start_runtime_readiness or {},
            "strategy_activation_prepare": strategy_activation_readiness or {},
            "strategy_state_activation": strategy_state_activation_readiness or {},
            "signal_loop_prepare": signal_loop_readiness or {},
            "signal_loop_start": signal_loop_start_readiness or {},
            "signal_evaluation": signal_evaluation_readiness or {},
            "signal_trade_intent": signal_trade_intent_readiness or {},
        }
        snapshot_hash = _stable_hash(snapshot_source)
        preflight = PreflightSnapshot(
            preflight_id=preflight_id,
            operation_id=operation_id,
            operation_type=operation_type,
            created_at_ms=now,
            expires_at_ms=expires_at_ms,
            current_state_snapshot={"campaign": campaign_summary, "runtime": runtime_summary},
            target_state=after,
            account_snapshot=market_summary,
            order_snapshot={"open_order_count": market_summary.get("open_order_count", 0)},
            runtime_snapshot=runtime_summary,
            campaign_snapshot=campaign_summary,
            playbook_snapshot=playbook_summary,
            risk_result=risk_result,
            decision=decision,
            warnings=warnings,
            blockers=blockers,
            confirmation_requirement=confirmation,
            snapshot_hash=snapshot_hash,
            idempotency_key=idempotency_key,
            summary=summary,
            before=before,
            after=after,
        )
        operation.current_preflight_id = preflight_id
        operation.status = status
        await self._repo.save_operation(operation)
        await self._repo.save_preflight(preflight)
        if status == "blocked":
            await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="blocked",
                blocked_reason="; ".join(blockers) or "operation preflight blocked",
                recheck_result={"preflight_blocked": True},
            )
        return self._to_preflight_response(operation, preflight)

    async def confirm(
        self,
        *,
        operation_id: str,
        preflight_id: str,
        confirmation_phrase: str,
        idempotency_key: str,
        confirmed_by: str = "owner",
    ) -> OperationConfirmResponse:
        operation = await self._require_operation(operation_id)
        preflight = await self._require_current_preflight(operation, preflight_id)
        existing = await self._repo.get_execution_result(operation_id)
        if existing is not None and operation.status in _TERMINAL_STATUSES:
            if preflight.idempotency_key == idempotency_key and preflight.preflight_id == preflight_id:
                return self._to_confirm_response(existing)
            raise ConfirmationMismatch(f"operation already terminal: {operation.status}")

        failure = await self._confirm_failure_reason(
            operation=operation,
            preflight=preflight,
            confirmation_phrase=confirmation_phrase,
            idempotency_key=idempotency_key,
        )
        if failure is not None:
            status: ExecutionStatus = "expired" if failure == "preflight expired" else "blocked"
            result_summary = None
            if operation.operation_type == "create_gated_trial_from_admission":
                result_summary = {
                    "operation_type": operation.operation_type,
                    "planned_result_status": "binding_reserved",
                    "message": (
                        "create_gated_trial_from_admission confirmation was blocked before binding reservation. "
                        "No trial, campaign, runtime carrier, runtime constraints, order, live execution, withdrawal, or transfer was created."
                    ),
                    "mutation_executed": False,
                    "binding_persisted": False,
                    "runtime_creation_executed": False,
                    "campaign_creation_executed": False,
                    "runtime_constraints_installed": False,
                    "live_ready": False,
                }
            if operation.operation_type == "create_campaign_from_admission_binding":
                result_summary = {
                    "operation_type": operation.operation_type,
                    "planned_result_status": "campaign_created",
                    "message": (
                        "create_campaign_from_admission_binding confirmation was blocked before campaign shell creation. "
                        "No runtime carrier, runtime constraints, strategy execution, order, live execution, withdrawal, or transfer was created."
                    ),
                    "mutation_executed": False,
                    "campaign_created": False,
                    "runtime_installed": False,
                    "runtime_started": False,
                    "strategy_active": False,
                    "constraints_installed": False,
                    "orders_placed": False,
                    "live_ready": False,
                }
            if operation.operation_type == "install_runtime_constraints_from_admission_campaign":
                result_summary = {
                    "operation_type": operation.operation_type,
                    "planned_result_status": "runtime_constraints_installed",
                    "message": (
                        "install_runtime_constraints_from_admission_campaign confirmation was blocked before "
                        "constraints metadata installation. Runtime was not started; strategy was not activated; "
                        "no order, live execution, withdrawal, transfer, cancel, close, or flatten action occurred."
                    ),
                    "mutation_executed": False,
                    "constraints_installed": False,
                    "runtime_started": False,
                    "strategy_active": False,
                    "trial_started": False,
                    "orders_placed": False,
                    "live_ready": False,
                }
            if operation.operation_type == "prepare_runtime_carrier_from_admission_campaign":
                result_summary = {
                    "operation_type": operation.operation_type,
                    "planned_result_status": "carrier_ready",
                    "message": (
                        "prepare_runtime_carrier_from_admission_campaign confirmation was blocked before "
                        "carrier readiness metadata preparation. Runtime was not started; strategy was not "
                        "activated; auto execution was not enabled; no order, live execution, withdrawal, "
                        "transfer, cancel, close, or flatten action occurred."
                    ),
                    "mutation_executed": False,
                    "carrier_ready": False,
                    "runtime_started": False,
                    "strategy_active": False,
                    "trial_started": False,
                    "auto_within_budget_enabled": False,
                    "orders_placed": False,
                    "live_ready": False,
                }
            if operation.operation_type == "prepare_runtime_start_from_admission_carrier":
                result_summary = {
                    "operation_type": operation.operation_type,
                    "planned_result_status": "runtime_start_ready",
                    "message": (
                        "prepare_runtime_start_from_admission_carrier confirmation was blocked before "
                        "runtime start readiness metadata preparation. Runtime was not started; strategy "
                        "was not activated; auto execution was not enabled; no order, live execution, "
                        "withdrawal, transfer, cancel, close, or flatten action occurred."
                    ),
                    "mutation_executed": False,
                    "runtime_start_ready": False,
                    "runtime_started": False,
                    "strategy_active": False,
                    "trial_started": False,
                    "auto_within_budget_enabled": False,
                    "orders_placed": False,
                    "live_ready": False,
                }
            if operation.operation_type == "evaluate_trial_trade_intent":
                result_summary = {
                    "operation_type": operation.operation_type,
                    "planned_result_status": "trial_trade_intent_evaluated",
                    "message": (
                        "evaluate_trial_trade_intent confirmation was blocked before non-executable "
                        "intent evaluation. Runtime was not started; strategy was not activated; no order, "
                        "execution intent, live execution, withdrawal, transfer, cancel, close, or flatten action occurred."
                    ),
                    "mutation_executed": False,
                    "intent_persisted": False,
                    "trial_trade_intent_is_order": False,
                    "order_created": False,
                    "execution_intent_created": False,
                    "runtime_started": False,
                    "strategy_active": False,
                    "trial_started": False,
                    "auto_within_budget_enabled": False,
                    "orders_placed": False,
                    "live_ready": False,
                }
            if operation.operation_type == "prepare_runtime_handoff_from_admission_campaign":
                result_summary = {
                    "operation_type": operation.operation_type,
                    "planned_result_status": "runtime_handoff_ready",
                    "message": (
                        "prepare_runtime_handoff_from_admission_campaign confirmation was blocked before "
                        "runtime handoff readiness metadata preparation. Runtime was not started; "
                        "runtime_started was not set true; strategy was not activated; no order, "
                        "execution intent, live execution, withdrawal, transfer, cancel, close, or flatten action occurred."
                    ),
                    "mutation_executed": False,
                    "runtime_handoff_ready": False,
                    "runtime_started": False,
                    "strategy_active": False,
                    "trial_started": False,
                    "auto_within_budget_enabled": False,
                    "orders_placed": False,
                    "live_ready": False,
                }
            if operation.operation_type == "start_runtime_from_admission_handoff":
                result_summary = {
                    "operation_type": operation.operation_type,
                    "planned_result_status": "runtime_started_strategy_inactive",
                    "message": (
                        "start_runtime_from_admission_handoff confirmation was blocked before runtime state transition. "
                        "Runtime state was not started; strategy was not activated; no order, execution intent, live execution, withdrawal, transfer, "
                        "cancel, close, or flatten action occurred."
                    ),
                    "mutation_executed": False,
                    "runtime_started": False,
                    "strategy_active": False,
                    "trial_started": False,
                    "auto_within_budget_enabled": False,
                    "auto_execution_enabled": False,
                    "order_created": False,
                    "execution_intent_created": False,
                    "orders_placed": False,
                    "live_ready": False,
                }
            if operation.operation_type == "prepare_strategy_activation_from_admission_runtime":
                result_summary = {
                    "operation_type": operation.operation_type,
                    "planned_result_status": "strategy_activation_ready",
                    "message": (
                        "prepare_strategy_activation_from_admission_runtime confirmation was blocked before "
                        "strategy activation readiness metadata preparation. Strategy was not activated; "
                        "signal loop was not started; auto execution was not enabled; no trade intent, "
                        "execution intent, order, or live execution path was created."
                    ),
                    "mutation_executed": False,
                    "strategy_activation_ready": False,
                    "runtime_started": False,
                    "strategy_active": False,
                    "trial_started": False,
                    "signal_loop_started": False,
                    "auto_within_budget_enabled": False,
                    "auto_execution_enabled": False,
                    "trade_intent_created": False,
                    "execution_intent_created": False,
                    "order_created": False,
                    "orders_placed": False,
                    "live_ready": False,
                }
            if operation.operation_type == "activate_strategy_from_admission_runtime":
                result_summary = {
                    "operation_type": operation.operation_type,
                    "planned_result_status": "strategy_active_no_execution",
                    "message": (
                        "activate_strategy_from_admission_runtime confirmation was blocked before "
                        "strategy state activation metadata transition. Strategy runner was not started; "
                        "signal loop was not started; auto execution was not enabled; no trade intent, "
                        "execution intent, order, or live execution path was created."
                    ),
                    "mutation_executed": False,
                    "strategy_state": None,
                    "strategy_active": False,
                    "strategy_execution_enabled": False,
                    "trial_started": False,
                    "signal_loop_enabled": False,
                    "signal_loop_started": False,
                    "auto_within_budget_enabled": False,
                    "auto_execution_enabled": False,
                    "trade_intent_created": False,
                    "execution_intent_created": False,
                    "order_created": False,
                    "orders_placed": False,
                    "live_ready": False,
                }
            if operation.operation_type == "prepare_signal_loop_from_admission_strategy":
                result_summary = {
                    "operation_type": operation.operation_type,
                    "planned_result_status": "signal_loop_ready_not_started",
                    "message": (
                        "prepare_signal_loop_from_admission_strategy confirmation was blocked before "
                        "signal loop readiness metadata preparation. Signal loop was not started; no signal was generated; "
                        "auto execution was not enabled; no trade intent, execution intent, order, or live execution path was created."
                    ),
                    "mutation_executed": False,
                    "signal_loop_ready": False,
                    "signal_loop_enabled": False,
                    "signal_loop_started": False,
                    "signal_generated": False,
                    "strategy_execution_enabled": False,
                    "trial_started": False,
                    "auto_within_budget_enabled": False,
                    "auto_execution_enabled": False,
                    "trade_intent_created": False,
                    "execution_intent_created": False,
                    "order_created": False,
                    "orders_placed": False,
                    "live_ready": False,
                }
            if operation.operation_type == "start_signal_loop_from_admission_strategy":
                result_summary = {
                    "operation_type": operation.operation_type,
                    "planned_result_status": "signal_loop_started_no_signal",
                    "message": (
                        "start_signal_loop_from_admission_strategy confirmation was blocked before "
                        "signal loop state metadata transition. No signal was generated; auto execution "
                        "was not enabled; no trade intent, execution intent, order, or live execution path was created."
                    ),
                    "mutation_executed": False,
                    "signal_loop_started": False,
                    "signal_loop_enabled": False,
                    "signal_generated": False,
                    "strategy_execution_enabled": False,
                    "trial_started": False,
                    "auto_within_budget_enabled": False,
                    "auto_execution_enabled": False,
                    "trade_intent_created": False,
                    "execution_intent_created": False,
                    "order_created": False,
                    "orders_placed": False,
                    "live_ready": False,
                }
            if operation.operation_type == "evaluate_signal_from_admission_strategy":
                result_summary = {
                    "operation_type": operation.operation_type,
                    "planned_result_status": "signal_evaluated_no_intent",
                    "message": (
                        "evaluate_signal_from_admission_strategy confirmation was blocked before "
                        "signal evaluation metadata recording. No trade intent, execution intent, "
                        "order, auto execution, trial start, or live execution path was created."
                    ),
                    "mutation_executed": False,
                    "signal_evaluated": False,
                    "signal_generated": False,
                    "trade_intent_created": False,
                    "execution_intent_created": False,
                    "order_created": False,
                    "orders_placed": False,
                    "strategy_execution_enabled": False,
                    "trial_started": False,
                    "auto_within_budget_enabled": False,
                    "auto_execution_enabled": False,
                    "live_ready": False,
                }
            result = await self._persist_result(
                operation=operation,
                preflight=preflight,
                status=status,
                blocked_reason=failure if status == "blocked" else None,
                recheck_result={"passed": False, "reason": failure},
                result_summary=result_summary,
                confirmed_by=confirmed_by,
            )
            return self._to_confirm_response(result)

        operation.status = "executing"
        operation.confirmed_by = confirmed_by
        operation.confirmed_at_ms = now_ms()
        await self._repo.save_operation(operation)

        try:
            result = await self._execute(operation=operation, preflight=preflight)
        except Exception as exc:  # pragma: no cover - defensive fail-closed path
            result = await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="failed",
                failed_reason=str(exc),
                recheck_result={"passed": True},
                confirmed_by=confirmed_by,
            )
        return self._to_confirm_response(result)

    async def cancel(
        self,
        *,
        operation_id: str,
        requested_by: str = "owner",
    ) -> OperationConfirmResponse:
        operation = await self._require_operation(operation_id)
        if operation.status in _TERMINAL_STATUSES:
            existing = await self._repo.get_execution_result(operation_id)
            if existing is not None:
                return self._to_confirm_response(existing)
            raise ConfirmationMismatch(f"operation already terminal: {operation.status}")
        if operation.current_preflight_id is None:
            raise OperationLayerError("operation has no current preflight")
        preflight = await self._require_current_preflight(operation, operation.current_preflight_id)
        result = await self._persist_result(
            operation=operation,
            preflight=preflight,
            status="cancelled",
            recheck_result={"cancelled_by": requested_by},
            confirmed_by=requested_by,
        )
        return self._to_confirm_response(result)

    async def get(self, operation_id: str) -> OperationDetailResponse:
        operation = await self._require_operation(operation_id)
        preflight = (
            await self._repo.get_preflight(operation.current_preflight_id)
            if operation.current_preflight_id
            else None
        )
        result = await self._repo.get_execution_result(operation_id)
        return OperationDetailResponse(operation=operation, preflight=preflight, result=result)

    async def list(self, *, limit: int = 50) -> OperationListResponse:
        return OperationListResponse(operations=await self._repo.list_operations(limit=limit))

    async def _execute(
        self,
        *,
        operation: OperationRecord,
        preflight: PreflightSnapshot,
    ) -> ExecutionResult:
        if operation.operation_type == "write_review_decision":
            return await self._execute_write_review_decision(operation=operation, preflight=preflight)
        if operation.operation_type == "start_review":
            return await self._execute_start_review(operation=operation, preflight=preflight)
        if operation.operation_type == "enter_observe":
            return await self._execute_runtime_transition(
                operation=operation,
                preflight=preflight,
                target_state="observe",
            )
        if operation.operation_type == "enter_pause":
            return await self._execute_runtime_transition(
                operation=operation,
                preflight=preflight,
                target_state="paused",
            )
        if operation.operation_type == "revoke_budget":
            return await self._execute_revoke_budget(operation=operation, preflight=preflight)
        if operation.operation_type == "enter_strategy_or_monitor":
            return await self._execute_monitor_carrier_noop(operation=operation, preflight=preflight)
        if operation.operation_type == "run_fixed_testnet_rehearsal":
            return await self._execute_fixed_testnet_rehearsal(operation=operation, preflight=preflight)
        if operation.operation_type == "emergency_flatten":
            return await self._execute_emergency_flatten_dry_run(operation=operation, preflight=preflight)
        if operation.operation_type == "emergency_stop_runtime":
            return await self._execute_emergency_stop_runtime(operation=operation, preflight=preflight)
        if operation.operation_type == "create_gated_trial_from_admission":
            return await self._execute_gated_trial_binding_reservation(
                operation=operation,
                preflight=preflight,
            )
        if operation.operation_type == "create_campaign_from_admission_binding":
            return await self._execute_admission_campaign_shell_creation(
                operation=operation,
                preflight=preflight,
            )
        if operation.operation_type == "install_runtime_constraints_from_admission_campaign":
            return await self._execute_admission_runtime_constraint_installation(
                operation=operation,
                preflight=preflight,
            )
        if operation.operation_type == "prepare_runtime_carrier_from_admission_campaign":
            return await self._execute_admission_runtime_carrier_preparation(
                operation=operation,
                preflight=preflight,
            )
        if operation.operation_type == "prepare_runtime_start_from_admission_carrier":
            return await self._execute_admission_runtime_start_preparation(
                operation=operation,
                preflight=preflight,
            )
        if operation.operation_type == "evaluate_trial_trade_intent":
            return await self._execute_trial_trade_intent_evaluation(
                operation=operation,
                preflight=preflight,
            )
        if operation.operation_type == "prepare_runtime_handoff_from_admission_campaign":
            return await self._execute_admission_runtime_handoff_preparation(
                operation=operation,
                preflight=preflight,
            )
        if operation.operation_type == "start_runtime_from_admission_handoff":
            return await self._execute_admission_runtime_start_from_handoff(
                operation=operation,
                preflight=preflight,
            )
        if operation.operation_type == "prepare_strategy_activation_from_admission_runtime":
            return await self._execute_admission_strategy_activation_preparation(
                operation=operation,
                preflight=preflight,
            )
        if operation.operation_type == "activate_strategy_from_admission_runtime":
            return await self._execute_admission_strategy_state_activation(
                operation=operation,
                preflight=preflight,
            )
        if operation.operation_type == "prepare_signal_loop_from_admission_strategy":
            return await self._execute_admission_signal_loop_preparation(
                operation=operation,
                preflight=preflight,
            )
        if operation.operation_type == "start_signal_loop_from_admission_strategy":
            return await self._execute_admission_signal_loop_start(
                operation=operation,
                preflight=preflight,
            )
        if operation.operation_type == "evaluate_signal_from_admission_strategy":
            return await self._execute_admission_signal_evaluation(
                operation=operation,
                preflight=preflight,
            )
        if operation.operation_type == "record_trial_trade_intent_from_signal_evaluation":
            return await self._execute_signal_trade_intent_recording(
                operation=operation,
                preflight=preflight,
            )
        if operation.operation_type != "switch_playbook":
            return await self._execute_no_safe_executor(operation=operation, preflight=preflight)
        if self._brc is None:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="failed",
                failed_reason="BRC campaign service unavailable",
                recheck_result={"passed": True},
            )
        target_playbook_id = _target_playbook_id(operation.input_params)
        evidence_refs = list(operation.input_params.get("evidence_refs") or [])
        evidence_refs.extend([f"operation:{operation.operation_id}", f"preflight:{preflight.preflight_id}"])
        try:
            decision = await self._brc.switch_playbook(
                new_playbook_id=target_playbook_id,
                reason_category=str(
                    operation.input_params.get("reason_category") or "owner_operation_layer"
                ),
                reason_text=str(
                    operation.input_params.get("reason_text")
                    or f"Owner confirmed Operation Layer switch to {target_playbook_id}"
                ),
                evidence_refs=evidence_refs,
                risk_change_direction=RiskChangeDirection(
                    operation.input_params.get("risk_change_direction")
                    or RiskChangeDirection.SAME_RISK.value
                ),
            )
        except BrcRuleViolation as exc:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="blocked",
                blocked_reason=str(exc),
                recheck_result={"passed": True},
            )

        if decision.decision_result != BrcDecisionResult.ALLOWED:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="blocked",
                blocked_reason=decision.blocked_reason or decision.decision_result.value,
                recheck_result={"passed": True},
                adapter_result={"switch_decision": decision.model_dump(mode="json")},
                campaign_refs=[
                    {
                        "type": "playbook_switch_decision",
                        "campaign_id": decision.campaign_id,
                        "ref_id": decision.switch_id,
                    }
                ],
            )

        final_campaign = await self._campaign_summary()
        result_summary = {
            "operation_type": operation.operation_type,
            "target_playbook_id": target_playbook_id,
            "decision_result": decision.decision_result.value,
            "message": f"Playbook switched to {target_playbook_id}. No orders were placed.",
        }
        return await self._persist_result(
            operation=operation,
            preflight=preflight,
            status="executed",
            recheck_result={"passed": True},
            adapter_result={"switch_decision": decision.model_dump(mode="json")},
            result_summary=result_summary,
            campaign_refs=[
                {
                    "type": "playbook_switch_decision",
                    "campaign_id": decision.campaign_id,
                    "ref_id": decision.switch_id,
                },
                {
                    "type": "campaign",
                    "campaign_id": decision.campaign_id,
                    "ref_id": decision.campaign_id,
                },
            ],
            final_state_snapshot={"campaign": final_campaign},
        )

    async def _execute_write_review_decision(
        self,
        *,
        operation: OperationRecord,
        preflight: PreflightSnapshot,
    ) -> ExecutionResult:
        if self._brc is None:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="failed",
                failed_reason="BRC campaign service unavailable",
                recheck_result={"passed": True},
            )
        campaign_id = str(operation.input_params.get("campaign_id") or "")
        if not campaign_id:
            campaign = await self._brc.get_current_campaign()
            if campaign is None:
                return await self._persist_result(
                    operation=operation,
                    preflight=preflight,
                    status="blocked",
                    blocked_reason="no campaign_id and no active BRC campaign",
                    recheck_result={"passed": True},
                )
            campaign_id = campaign.campaign_id
        metadata = dict(operation.input_params.get("metadata") or {})
        metadata.update(
            {
                "operation_id": operation.operation_id,
                "preflight_id": preflight.preflight_id,
                "authorization_source": "brc_operation_layer",
                "live_ready": False,
                "withdrawal_authorized": False,
                "strategy_execution_authorized": False,
            }
        )
        try:
            record = await self._brc.record_review_decision(
                campaign_id=campaign_id,
                source_action_id=_optional_str(operation.input_params.get("source_action_id")),
                decision=BrcReviewDecision(str(operation.input_params.get("decision") or "")),
                reason_text=str(operation.input_params.get("reason_text") or ""),
                next_recommended_task=str(operation.input_params.get("next_recommended_task") or ""),
                created_by=str(operation.input_params.get("created_by") or operation.requested_by or "owner"),
                metadata=metadata,
            )
        except (BrcRuleViolation, ValueError) as exc:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="blocked",
                blocked_reason=str(exc),
                recheck_result={"passed": True},
            )

        payload = record.model_dump(mode="json")
        return await self._persist_result(
            operation=operation,
            preflight=preflight,
            status="executed",
            recheck_result={"passed": True},
            adapter_result={"review_decision": payload},
            result_summary={
                "operation_type": operation.operation_type,
                "message": "Review decision persisted through Operation Layer. No runtime or exchange action was executed.",
                "review_id": record.review_id,
                "campaign_id": record.campaign_id,
                "decision": record.decision.value,
            },
            review_refs=[
                {
                    "type": "review_decision",
                    "campaign_id": record.campaign_id,
                    "ref_id": record.review_id,
                }
            ],
            campaign_refs=[
                {
                    "type": "campaign",
                    "campaign_id": record.campaign_id,
                    "ref_id": record.campaign_id,
                }
            ],
            final_state_snapshot={"review_decision": payload},
        )

    async def _execute_start_review(
        self,
        *,
        operation: OperationRecord,
        preflight: PreflightSnapshot,
    ) -> ExecutionResult:
        packet: dict[str, Any] = {}
        if self._readers.review_packet_reader is not None:
            packet = await self._readers.review_packet_reader(
                {
                    **operation.input_params,
                    "operation_id": operation.operation_id,
                    "preflight_id": preflight.preflight_id,
                }
            )
            status: ExecutionStatus = "executed"
            message = "Review packet read through Operation Layer. No mutation was executed."
        else:
            status = "noop"
            message = "Review start recorded as noop; no review packet reader is wired."
        return await self._persist_result(
            operation=operation,
            preflight=preflight,
            status=status,
            recheck_result={"passed": True},
            adapter_result={"review_packet": packet} if packet else {"reason": "no review packet reader wired"},
            result_summary={
                "operation_type": operation.operation_type,
                "message": message,
                "mutation_executed": False,
                "live_ready": False,
            },
            review_refs=[
                {
                    "type": "review_packet",
                    "ref_id": operation.operation_id,
                }
            ],
            final_state_snapshot={"review_packet": packet} if packet else {},
        )

    async def _execute_runtime_transition(
        self,
        *,
        operation: OperationRecord,
        preflight: PreflightSnapshot,
        target_state: str,
    ) -> ExecutionResult:
        if self._readers.runtime_transition is None:
            return await self._execute_no_safe_executor(operation=operation, preflight=preflight)
        try:
            transition = await self._readers.runtime_transition(
                target_state,
                {
                    **operation.input_params,
                    "operation_id": operation.operation_id,
                    "preflight_id": preflight.preflight_id,
                    "updated_by": operation.requested_by,
                },
            )
        except Exception as exc:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="blocked",
                blocked_reason=str(exc),
                recheck_result={"passed": True},
            )
        next_state = str(transition.get("status") or transition.get("next_state") or target_state)
        is_noop = next_state == preflight.before.get("runtime_state")
        return await self._persist_result(
            operation=operation,
            preflight=preflight,
            status="noop" if is_noop else "executed",
            recheck_result={"passed": True},
            adapter_result={"runtime_transition": transition},
            result_summary={
                "operation_type": operation.operation_type,
                "message": f"Runtime campaign state transition recorded as {next_state}. No orders were placed, closed, or cancelled.",
                "target_state": target_state,
                "next_state": next_state,
                "mutation_executed": not is_noop,
                "pg_state_mutated": not is_noop,
                "places_orders": False,
                "closes_positions": False,
                "cancels_orders": False,
                "withdrawal_executed": False,
                "transfer_executed": False,
                "live_ready": False,
            },
            audit_refs=[
                {
                    "type": "runtime_transition",
                    "ref_id": operation.operation_id,
                    "target_state": target_state,
                    "next_state": next_state,
                }
            ],
            final_state_snapshot={"runtime_transition": transition},
        )

    async def _execute_revoke_budget(
        self,
        *,
        operation: OperationRecord,
        preflight: PreflightSnapshot,
    ) -> ExecutionResult:
        if self._readers.budget_revoke_executor is None:
            return await self._execute_no_safe_executor(operation=operation, preflight=preflight)
        try:
            revoked = await self._readers.budget_revoke_executor(
                {
                    **operation.input_params,
                    "operation_id": operation.operation_id,
                    "preflight_id": preflight.preflight_id,
                    "revoked_by": operation.requested_by,
                    "authorization_source": "brc_operation_layer",
                    "places_orders": False,
                    "closes_positions": False,
                    "cancels_orders": False,
                    "withdrawal_executed": False,
                    "transfer_executed": False,
                    "live_ready": False,
                }
            )
        except Exception as exc:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="blocked",
                blocked_reason=str(exc),
                recheck_result={"passed": True},
            )
        already_revoked = bool(revoked.get("already_revoked"))
        budget_authorization_id = revoked.get("budget_authorization_id") or preflight.after.get(
            "budget_authorization_id"
        )
        result_status: ExecutionStatus = "noop" if already_revoked else "executed"
        message = (
            "Budget authorization was already revoked; future budgeted autonomy actions remain blocked."
            if already_revoked
            else "Budget authorization revoked. Future budgeted autonomy actions under this envelope are blocked."
        )
        return await self._persist_result(
            operation=operation,
            preflight=preflight,
            status=result_status,
            recheck_result={"passed": True},
            adapter_result={"budget_revoke": revoked},
            result_summary={
                "operation_type": operation.operation_type,
                "message": (
                    f"{message} This does not close active positions, cancel TP/SL orders, "
                    "place orders, transfer funds, or withdraw funds."
                ),
                "budget_authorization_id": budget_authorization_id,
                "budget_effective_state": "revoked",
                "future_budgeted_actions_allowed": False,
                "already_revoked": already_revoked,
                "mutation_executed": not already_revoked,
                "places_orders": False,
                "closes_positions": False,
                "cancels_orders": False,
                "withdrawal_executed": False,
                "transfer_executed": False,
                "live_ready": False,
            },
            audit_refs=[
                {
                    "type": "budget_authorization_revoke",
                    "ref_id": str(budget_authorization_id or operation.operation_id),
                    "operation_id": operation.operation_id,
                }
            ],
            final_state_snapshot={"budget_authorization": revoked},
        )

    async def _execute_monitor_carrier_noop(
        self,
        *,
        operation: OperationRecord,
        preflight: PreflightSnapshot,
    ) -> ExecutionResult:
        return await self._persist_result(
            operation=operation,
            preflight=preflight,
            status="noop",
            recheck_result={"passed": True},
            adapter_result={
                "carrier": "monitor",
                "reason": "enter_strategy_or_monitor is degraded to monitor carrier only",
            },
            result_summary={
                "operation_type": operation.operation_type,
                "message": "Monitor carrier selected. No unrestricted auto trading, order placement, sizing, leverage, or live execution was enabled.",
                "mutation_executed": False,
                "live_ready": False,
            },
            final_state_snapshot={"carrier": "monitor", "runtime_mutation": False},
        )

    async def _execute_fixed_testnet_rehearsal(
        self,
        *,
        operation: OperationRecord,
        preflight: PreflightSnapshot,
    ) -> ExecutionResult:
        if self._readers.fixed_rehearsal_executor is None:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="blocked",
                blocked_reason="fixed rehearsal Operation executor unavailable",
                recheck_result={"passed": False},
            )
        try:
            payload = await self._readers.fixed_rehearsal_executor(
                {
                    **operation.input_params,
                    "operation_id": operation.operation_id,
                    "preflight_id": preflight.preflight_id,
                    "idempotency_key": preflight.idempotency_key,
                    "authorization_source": "brc_operation_layer",
                    "workflow_carrier_role": "internal_ref_only",
                    "allowed_symbols": ["ETH/USDT:USDT", "BTC/USDT:USDT"],
                    "live_ready": False,
                }
            )
        except BrcRuleViolation as exc:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="blocked",
                blocked_reason=str(exc),
                recheck_result={"passed": True},
            )
        except Exception as exc:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="failed",
                failed_reason=str(exc),
                recheck_result={"passed": True},
            )
        if payload.get("withdrawal_executed") is True or payload.get("live_ready") is True:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="failed",
                failed_reason="fixed rehearsal runner returned forbidden live/withdrawal flags",
                recheck_result={"passed": True},
                adapter_result={"fixed_testnet_rehearsal": payload},
            )

        refs = _extract_rehearsal_refs(payload)
        workflow_run_id = refs["workflow_run_id"]
        campaign_id = refs["campaign_id"]
        result_summary = {
            "operation_type": operation.operation_type,
            "message": "Fixed ETH/BTC testnet rehearsal executed through Operation authorization.",
            "workflow_run_id": workflow_run_id,
            "campaign_id": campaign_id,
            "mutation_executed": bool(payload.get("mutation_executed", True)),
            "withdrawal_executed": bool(payload.get("withdrawal_executed", False)),
            "live_ready": False,
        }
        return await self._persist_result(
            operation=operation,
            preflight=preflight,
            status="executed",
            recheck_result={"passed": True},
            adapter_result={"fixed_testnet_rehearsal": payload},
            result_summary=result_summary,
            audit_refs=refs["audit_refs"],
            campaign_refs=refs["campaign_refs"],
            review_refs=refs["review_refs"],
            final_state_snapshot={
                "fixed_testnet_rehearsal": {
                    "workflow_run_id": workflow_run_id,
                    "campaign_id": campaign_id,
                    "final_inventory": payload.get("final_inventory"),
                    "review_packet": payload.get("review_packet"),
                    "evidence": payload.get("evidence"),
                    "readiness": payload.get("readiness"),
                }
            },
        )

    async def _execute_emergency_flatten_dry_run(
        self,
        *,
        operation: OperationRecord,
        preflight: PreflightSnapshot,
    ) -> ExecutionResult:
        dry_run_plan = dict(preflight.after.get("dry_run_plan") or {})
        if not dry_run_plan:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="blocked",
                blocked_reason="flatten dry-run plan unavailable",
                recheck_result={"passed": False},
                result_summary={
                    "operation_type": operation.operation_type,
                    "message": "No flatten dry-run plan was available to persist. No order, cancel, close, or flatten action was executed.",
                    "dry_run_only": True,
                    "actual_execution": False,
                    "mutation_executed": False,
                    "live_ready": False,
                },
            )
        status: ExecutionStatus = (
            "noop"
            if dry_run_plan.get("estimated_actions_count") == 0
            or dry_run_plan.get("plan_status") == "noop"
            else "executed"
        )
        result_summary = {
            "operation_type": operation.operation_type,
            "message": "Flatten dry-run plan persisted through Operation authorization. No orders were cancelled, no positions were closed, and no orders were placed.",
            "dry_run_id": dry_run_plan.get("dry_run_id"),
            "plan_status": dry_run_plan.get("plan_status"),
            "estimated_actions_count": dry_run_plan.get("estimated_actions_count", 0),
            "cancel_order_candidate_count": len(dry_run_plan.get("cancel_order_candidates") or []),
            "close_position_candidate_count": len(dry_run_plan.get("close_position_candidates") or []),
            "dry_run_only": True,
            "actual_execution": False,
            "mutation_executed": False,
            "orders_cancelled": False,
            "positions_closed": False,
            "orders_placed": False,
            "live_ready": False,
        }
        return await self._persist_result(
            operation=operation,
            preflight=preflight,
            status=status,
            recheck_result={"passed": True, "dry_run_only": True},
            adapter_result={"flatten_dry_run_plan": dry_run_plan},
            result_summary=result_summary,
            audit_refs=[
                {
                    "type": "flatten_dry_run",
                    "ref_id": str(dry_run_plan.get("dry_run_id") or operation.operation_id),
                    "operation_id": operation.operation_id,
                    "actual_execution": False,
                }
            ],
            final_state_snapshot={"flatten_dry_run_plan": dry_run_plan},
        )

    async def _execute_emergency_stop_runtime(
        self,
        *,
        operation: OperationRecord,
        preflight: PreflightSnapshot,
    ) -> ExecutionResult:
        if self._readers.runtime_stop_executor is None:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="blocked",
                blocked_reason="emergency stop runtime executor unavailable",
                recheck_result={"passed": False},
                result_summary={
                    "operation_type": operation.operation_type,
                    "message": "No safe runtime stop executor is wired; no runtime mutation was performed.",
                    "mutation_executed": False,
                    "does_not_flatten": True,
                    "does_not_cancel_orders": True,
                    "live_ready": False,
                },
            )
        runtime_summary = await self._readers.runtime_summary()
        current_state = _runtime_state_value(runtime_summary)
        if _runtime_already_stopped(current_state):
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="noop",
                recheck_result={"passed": True, "already_stopped": True},
                adapter_result={"reason": "runtime already stopped", "runtime_state": current_state},
                result_summary={
                    "operation_type": operation.operation_type,
                    "message": "Runtime was already stopped or hard-locked. No flatten, cancel, close, order, withdrawal, transfer, or live action was executed.",
                    "runtime_state": current_state,
                    "mutation_executed": False,
                    "does_not_flatten": True,
                    "does_not_cancel_orders": True,
                    "live_ready": False,
                },
                audit_refs=[
                    {
                        "type": "runtime_stop",
                        "ref_id": operation.operation_id,
                        "runtime_state": current_state,
                        "noop": True,
                    }
                ],
                final_state_snapshot={"runtime_stop": {"runtime_state": current_state, "noop": True}},
            )
        try:
            payload = await self._readers.runtime_stop_executor(
                {
                    **operation.input_params,
                    "operation_id": operation.operation_id,
                    "preflight_id": preflight.preflight_id,
                    "idempotency_key": preflight.idempotency_key,
                    "authorization_source": "brc_operation_layer",
                    "updated_by": operation.requested_by,
                    "does_not_flatten": True,
                    "does_not_cancel_orders": True,
                    "does_not_place_orders": True,
                    "does_not_withdraw_or_transfer": True,
                    "live_ready": False,
                }
            )
        except Exception as exc:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="failed",
                failed_reason=str(exc),
                recheck_result={"passed": True},
                result_summary={
                    "operation_type": operation.operation_type,
                    "message": "Runtime stop adapter failed; no flatten, cancel, close, order, withdrawal, transfer, or live action was executed.",
                    "mutation_executed": False,
                    "does_not_flatten": True,
                    "does_not_cancel_orders": True,
                    "live_ready": False,
                },
            )
        if payload.get("live_ready") is True or payload.get("flatten_executed") is True or payload.get("orders_cancelled") is True:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="failed",
                failed_reason="runtime stop adapter returned forbidden live/flatten/cancel flags",
                recheck_result={"passed": True},
                adapter_result={"runtime_stop": payload},
                result_summary={
                    "operation_type": operation.operation_type,
                    "message": "Runtime stop adapter returned forbidden flags; result was failed closed.",
                    "mutation_executed": False,
                    "does_not_flatten": True,
                    "does_not_cancel_orders": True,
                    "live_ready": False,
                },
            )
        next_state = str(
            payload.get("runtime_state")
            or payload.get("status")
            or payload.get("next_state")
            or "stopped_by_owner"
        )
        runtime_refs = [
            {
                "type": "runtime_stop",
                "ref_id": operation.operation_id,
                "runtime_state": next_state,
            }
        ]
        result_summary = {
            "operation_type": operation.operation_type,
            "message": "Runtime stop executed through Operation authorization. It did not flatten positions, cancel orders, close positions, place orders, withdraw, transfer, or enable live.",
            "runtime_state": next_state,
            "mutation_executed": True,
            "does_not_flatten": True,
            "does_not_cancel_orders": True,
            "does_not_place_orders": True,
            "does_not_withdraw_or_transfer": True,
            "live_ready": False,
            "runtime_refs": runtime_refs,
        }
        return await self._persist_result(
            operation=operation,
            preflight=preflight,
            status="executed",
            recheck_result={"passed": True},
            adapter_result={"runtime_stop": payload},
            result_summary=result_summary,
            audit_refs=runtime_refs,
            final_state_snapshot={"runtime_stop": payload, "runtime_state": next_state},
        )

    async def _execute_no_safe_executor(
        self,
        *,
        operation: OperationRecord,
        preflight: PreflightSnapshot,
    ) -> ExecutionResult:
        return await self._persist_result(
            operation=operation,
            preflight=preflight,
            status="noop",
            recheck_result={"passed": True},
            adapter_result={"reason": "operation has no safe executor"},
            result_summary={
                "operation_type": operation.operation_type,
                "message": "No safe Operation executor is wired; no mutation was performed.",
                "mutation_executed": False,
                "live_ready": False,
            },
        )

    async def _execute_gated_trial_binding_reservation(
        self,
        *,
        operation: OperationRecord,
        preflight: PreflightSnapshot,
    ) -> ExecutionResult:
        if self._readers.admission_binding_reserver is None:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="blocked",
                blocked_reason="admission trial binding reserver unavailable",
                recheck_result={"passed": False, "reason": "binding_reserver_unavailable"},
                result_summary={
                    "operation_type": operation.operation_type,
                    "planned_result_status": "binding_reserved",
                    "message": (
                        "Binding reservation adapter is not wired. No trial, campaign, runtime carrier, "
                        "runtime constraints, order, live execution, withdrawal, or transfer was created."
                    ),
                    "binding_persisted": False,
                    "runtime_mutation_executed": False,
                    "campaign_creation_executed": False,
                    "runtime_constraints_installed": False,
                    "orders_placed": False,
                    "live_ready": False,
                },
                final_state_snapshot={"admission_readiness": preflight.after},
            )

        payload = dict(operation.input_params)
        payload.update(
            {
                "operation_id": operation.operation_id,
                "preflight_id": preflight.preflight_id,
                "confirmed_by": operation.confirmed_by or "owner",
                "authorization_source": "brc_operation_layer",
            }
        )
        try:
            binding = await self._readers.admission_binding_reserver(payload)
        except ValueError as exc:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="blocked",
                blocked_reason=str(exc),
                recheck_result={"passed": False, "reason": str(exc)},
                result_summary={
                    "operation_type": operation.operation_type,
                    "planned_result_status": "binding_reserved",
                    "message": (
                        "Admission-trial binding reservation was blocked. No trial, campaign, runtime carrier, "
                        "runtime constraints, order, live execution, withdrawal, or transfer was created."
                    ),
                    "binding_persisted": False,
                    "runtime_mutation_executed": False,
                    "campaign_creation_executed": False,
                    "runtime_constraints_installed": False,
                    "orders_placed": False,
                    "live_ready": False,
                },
                final_state_snapshot={"admission_readiness": preflight.after},
            )
        binding_id = _optional_str(binding.get("binding_id"))
        binding_ref = {
            "type": "admission_trial_binding",
            "ref_id": binding_id,
            "binding_status": binding.get("binding_status"),
        }
        return await self._persist_result(
            operation=operation,
            preflight=preflight,
            status="executed",
            recheck_result={"passed": True, "binding_reservation_only": True},
            adapter_result={"admission_trial_binding": binding},
            result_summary={
                "operation_type": operation.operation_type,
                "planned_result_status": "binding_reserved",
                "message": (
                    "Admission-trial binding reserved only. Trial not started; campaign not created; "
                    "runtime carrier not created; runtime constraints not installed; no orders placed."
                ),
                "binding_id": binding_id,
                "binding_status": binding.get("binding_status"),
                "binding_persisted": True,
                "runtime_mutation_executed": False,
                "runtime_creation_executed": False,
                "campaign_creation_executed": False,
                "runtime_constraints_installed": False,
                "orders_placed": False,
                "withdrawal_executed": False,
                "transfer_executed": False,
                "live_ready": False,
            },
            audit_refs=[binding_ref],
            campaign_refs=[],
            review_refs=[],
            final_state_snapshot={"admission_trial_binding": binding},
        )

    async def _execute_admission_campaign_shell_creation(
        self,
        *,
        operation: OperationRecord,
        preflight: PreflightSnapshot,
    ) -> ExecutionResult:
        if self._readers.admission_campaign_creator is None:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="blocked",
                blocked_reason="admission campaign shell creator unavailable",
                recheck_result={"passed": False, "reason": "campaign_shell_creator_unavailable"},
                result_summary={
                    "operation_type": operation.operation_type,
                    "planned_result_status": "campaign_created",
                    "message": (
                        "Campaign shell creator is not wired. No campaign, runtime carrier, runtime constraints, "
                        "strategy execution, order, live execution, withdrawal, or transfer was created."
                    ),
                    "campaign_created": False,
                    "runtime_installed": False,
                    "runtime_started": False,
                    "strategy_active": False,
                    "constraints_installed": False,
                    "orders_placed": False,
                    "live_ready": False,
                },
                final_state_snapshot={"campaign_shell_readiness": preflight.after},
            )

        payload = dict(operation.input_params)
        payload.update(
            {
                "operation_id": operation.operation_id,
                "preflight_id": preflight.preflight_id,
                "confirmed_by": operation.confirmed_by or "owner",
                "authorization_source": "brc_operation_layer",
            }
        )
        try:
            created = await self._readers.admission_campaign_creator(payload)
        except ValueError as exc:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="blocked",
                blocked_reason=str(exc),
                recheck_result={"passed": False, "reason": str(exc)},
                result_summary={
                    "operation_type": operation.operation_type,
                    "planned_result_status": "campaign_created",
                    "message": (
                        "Admission campaign shell creation was blocked. No runtime carrier, runtime constraints, "
                        "strategy execution, order, live execution, withdrawal, or transfer was created."
                    ),
                    "campaign_created": False,
                    "runtime_installed": False,
                    "runtime_started": False,
                    "strategy_active": False,
                    "constraints_installed": False,
                    "orders_placed": False,
                    "live_ready": False,
                },
                final_state_snapshot={"campaign_shell_readiness": preflight.after},
            )

        campaign = dict(created.get("campaign") or {})
        binding = dict(created.get("binding") or {})
        campaign_id = _optional_str(campaign.get("campaign_id"))
        binding_id = _optional_str(binding.get("binding_id") or operation.input_params.get("admission_binding_id"))
        campaign_ref = {
            "type": "admission_campaign_shell",
            "campaign_id": campaign_id,
            "ref_id": campaign_id,
            "admission_binding_id": binding_id,
        }
        binding_ref = {
            "type": "admission_trial_binding",
            "ref_id": binding_id,
            "binding_status": binding.get("binding_status"),
            "campaign_id": campaign_id,
        }
        return await self._persist_result(
            operation=operation,
            preflight=preflight,
            status="executed",
            recheck_result={"passed": True, "campaign_shell_creation_only": True},
            adapter_result={"admission_campaign_shell": created},
            result_summary={
                "operation_type": operation.operation_type,
                "planned_result_status": "campaign_created",
                "message": (
                    "Admission campaign shell created. Runtime not installed; strategy not active; "
                    "constraints not installed; no orders placed."
                ),
                "campaign_id": campaign_id,
                "binding_id": binding_id,
                "binding_status": binding.get("binding_status"),
                "campaign_created": True,
                "runtime_installed": False,
                "runtime_started": False,
                "runtime_creation_executed": False,
                "strategy_active": False,
                "constraints_installed": False,
                "orders_placed": False,
                "withdrawal_executed": False,
                "transfer_executed": False,
                "live_ready": False,
            },
            audit_refs=[binding_ref],
            campaign_refs=[campaign_ref],
            review_refs=[],
            final_state_snapshot={
                "campaign": campaign,
                "admission_trial_binding": binding,
                "runtime_installed": False,
                "strategy_active": False,
            },
        )

    async def _execute_admission_runtime_constraint_installation(
        self,
        *,
        operation: OperationRecord,
        preflight: PreflightSnapshot,
    ) -> ExecutionResult:
        if self._readers.admission_runtime_constraint_installer is None:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="blocked",
                blocked_reason="admission runtime constraint installer unavailable",
                recheck_result={"passed": False, "reason": "runtime_constraint_installer_unavailable"},
                result_summary={
                    "operation_type": operation.operation_type,
                    "planned_result_status": "runtime_constraints_installed",
                    "message": (
                        "Runtime constraint installer is not wired. No constraints metadata, runtime start, "
                        "strategy activation, order, live execution, withdrawal, or transfer was created."
                    ),
                    "constraints_installed": False,
                    "runtime_started": False,
                    "strategy_active": False,
                    "trial_started": False,
                    "orders_placed": False,
                    "live_ready": False,
                },
                final_state_snapshot={"runtime_constraint_readiness": preflight.after},
            )

        payload = dict(operation.input_params)
        payload.update(
            {
                "operation_id": operation.operation_id,
                "preflight_id": preflight.preflight_id,
                "confirmed_by": operation.confirmed_by or "owner",
                "authorization_source": "brc_operation_layer",
            }
        )
        try:
            installed = await self._readers.admission_runtime_constraint_installer(payload)
        except ValueError as exc:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="blocked",
                blocked_reason=str(exc),
                recheck_result={"passed": False, "reason": str(exc)},
                result_summary={
                    "operation_type": operation.operation_type,
                    "planned_result_status": "runtime_constraints_installed",
                    "message": (
                        "Runtime constraint metadata installation was blocked. Runtime was not started; "
                        "strategy was not activated; no order, live execution, withdrawal, or transfer occurred."
                    ),
                    "constraints_installed": False,
                    "runtime_started": False,
                    "strategy_active": False,
                    "trial_started": False,
                    "orders_placed": False,
                    "live_ready": False,
                },
                final_state_snapshot={"runtime_constraint_readiness": preflight.after},
            )

        campaign = dict(installed.get("campaign") or {})
        binding = dict(installed.get("binding") or {})
        campaign_id = _optional_str(campaign.get("campaign_id") or operation.input_params.get("campaign_id"))
        binding_id = _optional_str(binding.get("binding_id") or operation.input_params.get("admission_binding_id"))
        idempotent = bool(installed.get("idempotent", False))
        campaign_ref = {
            "type": "admission_runtime_constraints",
            "campaign_id": campaign_id,
            "ref_id": campaign_id,
            "admission_binding_id": binding_id,
        }
        binding_ref = {
            "type": "admission_trial_binding",
            "ref_id": binding_id,
            "binding_status": binding.get("binding_status"),
            "campaign_id": campaign_id,
        }
        return await self._persist_result(
            operation=operation,
            preflight=preflight,
            status="noop" if idempotent else "executed",
            recheck_result={
                "passed": True,
                "constraints_metadata_only": True,
                "idempotent": idempotent,
            },
            adapter_result={"admission_runtime_constraints": installed},
            result_summary={
                "operation_type": operation.operation_type,
                "planned_result_status": "runtime_constraints_installed",
                "message": (
                    "Runtime constraints metadata already installed. Runtime remains not started; "
                    "strategy remains inactive; no orders placed."
                    if idempotent
                    else "Runtime constraints metadata installed. Runtime not started; strategy not active; no orders placed."
                ),
                "campaign_id": campaign_id,
                "binding_id": binding_id,
                "binding_status": binding.get("binding_status"),
                "constraints_installed": True,
                "installed_constraint_snapshot_id": installed.get("installed_constraint_snapshot_id"),
                "installed_constraints_summary": dict(installed.get("installed_constraints_summary") or {}),
                "runtime_status": "constraints_installed_not_started",
                "runtime_started": False,
                "runtime_active": False,
                "strategy_active": False,
                "trial_started": False,
                "auto_within_budget_enabled": False,
                "owner_confirm_each_entry_enabled": False,
                "orders_placed": False,
                "withdrawal_executed": False,
                "transfer_executed": False,
                "live_ready": False,
                "idempotent": idempotent,
            },
            audit_refs=[binding_ref],
            campaign_refs=[campaign_ref],
            review_refs=[],
            final_state_snapshot={
                "campaign": campaign,
                "admission_trial_binding": binding,
                "runtime_status": "constraints_installed_not_started",
                "runtime_started": False,
                "strategy_active": False,
                "trial_started": False,
            },
        )

    async def _execute_admission_runtime_carrier_preparation(
        self,
        *,
        operation: OperationRecord,
        preflight: PreflightSnapshot,
    ) -> ExecutionResult:
        if self._readers.admission_runtime_carrier_preparer is None:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="blocked",
                blocked_reason="admission runtime carrier preparer unavailable",
                recheck_result={"passed": False, "reason": "runtime_carrier_preparer_unavailable"},
                result_summary={
                    "operation_type": operation.operation_type,
                    "planned_result_status": "carrier_ready",
                    "message": (
                        "Runtime carrier preparer is not wired. No carrier readiness metadata, runtime start, "
                        "strategy activation, auto execution, order, live execution, withdrawal, or transfer was created."
                    ),
                    "carrier_ready": False,
                    "runtime_started": False,
                    "strategy_active": False,
                    "trial_started": False,
                    "auto_within_budget_enabled": False,
                    "orders_placed": False,
                    "live_ready": False,
                },
                final_state_snapshot={"runtime_carrier_readiness": preflight.after},
            )

        payload = dict(operation.input_params)
        payload.update(
            {
                "operation_id": operation.operation_id,
                "preflight_id": preflight.preflight_id,
                "confirmed_by": operation.confirmed_by or "owner",
                "authorization_source": "brc_operation_layer",
            }
        )
        try:
            prepared = await self._readers.admission_runtime_carrier_preparer(payload)
        except ValueError as exc:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="blocked",
                blocked_reason=str(exc),
                recheck_result={"passed": False, "reason": str(exc)},
                result_summary={
                    "operation_type": operation.operation_type,
                    "planned_result_status": "carrier_ready",
                    "message": (
                        "Runtime carrier readiness preparation was blocked. Runtime was not started; "
                        "strategy was not activated; auto execution was not enabled; no order, live execution, "
                        "withdrawal, or transfer occurred."
                    ),
                    "carrier_ready": False,
                    "runtime_started": False,
                    "strategy_active": False,
                    "trial_started": False,
                    "auto_within_budget_enabled": False,
                    "orders_placed": False,
                    "live_ready": False,
                },
                final_state_snapshot={"runtime_carrier_readiness": preflight.after},
            )

        campaign = dict(prepared.get("campaign") or {})
        binding = dict(prepared.get("binding") or {})
        campaign_id = _optional_str(campaign.get("campaign_id") or operation.input_params.get("campaign_id"))
        binding_id = _optional_str(binding.get("binding_id") or operation.input_params.get("admission_binding_id"))
        idempotent = bool(prepared.get("idempotent", False))
        campaign_ref = {
            "type": "admission_runtime_carrier_ready",
            "campaign_id": campaign_id,
            "ref_id": campaign_id,
            "admission_binding_id": binding_id,
        }
        binding_ref = {
            "type": "admission_trial_binding",
            "ref_id": binding_id,
            "binding_status": binding.get("binding_status"),
            "campaign_id": campaign_id,
        }
        return await self._persist_result(
            operation=operation,
            preflight=preflight,
            status="noop" if idempotent else "executed",
            recheck_result={
                "passed": True,
                "carrier_readiness_metadata_only": True,
                "idempotent": idempotent,
            },
            adapter_result={"admission_runtime_carrier": prepared},
            result_summary={
                "operation_type": operation.operation_type,
                "planned_result_status": "carrier_ready",
                "message": (
                    "Runtime carrier readiness metadata already prepared. Runtime remains not started; "
                    "strategy remains inactive; auto execution remains disabled; no orders placed."
                    if idempotent
                    else "Runtime carrier readiness metadata prepared. Runtime not started; strategy not active; auto execution disabled; no orders placed."
                ),
                "campaign_id": campaign_id,
                "binding_id": binding_id,
                "binding_status": binding.get("binding_status"),
                "carrier_ready": True,
                "carrier_readiness_summary": dict(prepared.get("carrier_readiness_summary") or {}),
                "runtime_status": "carrier_ready_not_started",
                "runtime_started": False,
                "runtime_active": False,
                "strategy_active": False,
                "trial_started": False,
                "auto_within_budget_enabled": False,
                "owner_confirm_each_entry_enabled": False,
                "orders_placed": False,
                "withdrawal_executed": False,
                "transfer_executed": False,
                "live_ready": False,
                "idempotent": idempotent,
            },
            audit_refs=[binding_ref],
            campaign_refs=[campaign_ref],
            review_refs=[],
            final_state_snapshot={
                "campaign": campaign,
                "admission_trial_binding": binding,
                "runtime_status": "carrier_ready_not_started",
                "runtime_started": False,
                "strategy_active": False,
                "trial_started": False,
            },
        )

    async def _execute_admission_runtime_start_preparation(
        self,
        *,
        operation: OperationRecord,
        preflight: PreflightSnapshot,
    ) -> ExecutionResult:
        if self._readers.admission_runtime_start_preparer is None:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="blocked",
                blocked_reason="admission runtime start preparer unavailable",
                recheck_result={"passed": False, "reason": "runtime_start_preparer_unavailable"},
                result_summary={
                    "operation_type": operation.operation_type,
                    "planned_result_status": "runtime_start_ready",
                    "message": (
                        "Runtime start preparer is not wired. No runtime start readiness metadata, runtime start, "
                        "strategy activation, auto execution, order, live execution, withdrawal, or transfer was created."
                    ),
                    "runtime_start_ready": False,
                    "runtime_started": False,
                    "strategy_active": False,
                    "trial_started": False,
                    "auto_within_budget_enabled": False,
                    "orders_placed": False,
                    "live_ready": False,
                },
                final_state_snapshot={"runtime_start_readiness": preflight.after},
            )

        payload = dict(operation.input_params)
        payload.update(
            {
                "operation_id": operation.operation_id,
                "preflight_id": preflight.preflight_id,
                "confirmed_by": operation.confirmed_by or "owner",
                "authorization_source": "brc_operation_layer",
            }
        )
        try:
            prepared = await self._readers.admission_runtime_start_preparer(payload)
        except ValueError as exc:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="blocked",
                blocked_reason=str(exc),
                recheck_result={"passed": False, "reason": str(exc)},
                result_summary={
                    "operation_type": operation.operation_type,
                    "planned_result_status": "runtime_start_ready",
                    "message": (
                        "Runtime start readiness preparation was blocked. Runtime was not started; "
                        "strategy was not activated; auto execution was not enabled; no order, live execution, "
                        "withdrawal, or transfer occurred."
                    ),
                    "runtime_start_ready": False,
                    "runtime_started": False,
                    "strategy_active": False,
                    "trial_started": False,
                    "auto_within_budget_enabled": False,
                    "orders_placed": False,
                    "live_ready": False,
                },
                final_state_snapshot={"runtime_start_readiness": preflight.after},
            )

        campaign = dict(prepared.get("campaign") or {})
        binding = dict(prepared.get("binding") or {})
        campaign_id = _optional_str(campaign.get("campaign_id") or operation.input_params.get("campaign_id"))
        binding_id = _optional_str(binding.get("binding_id") or operation.input_params.get("admission_binding_id"))
        idempotent = bool(prepared.get("idempotent", False))
        campaign_ref = {
            "type": "admission_runtime_start_ready",
            "campaign_id": campaign_id,
            "ref_id": campaign_id,
            "admission_binding_id": binding_id,
        }
        binding_ref = {
            "type": "admission_trial_binding",
            "ref_id": binding_id,
            "binding_status": binding.get("binding_status"),
            "campaign_id": campaign_id,
        }
        return await self._persist_result(
            operation=operation,
            preflight=preflight,
            status="noop" if idempotent else "executed",
            recheck_result={
                "passed": True,
                "runtime_start_readiness_metadata_only": True,
                "idempotent": idempotent,
            },
            adapter_result={"admission_runtime_start": prepared},
            result_summary={
                "operation_type": operation.operation_type,
                "planned_result_status": "runtime_start_ready",
                "message": (
                    "Runtime start readiness metadata already prepared. Runtime remains not started; "
                    "strategy remains inactive; auto execution remains disabled; no orders placed."
                    if idempotent
                    else "Runtime start readiness metadata prepared. Runtime not started; strategy not active; auto execution disabled; no orders placed."
                ),
                "campaign_id": campaign_id,
                "binding_id": binding_id,
                "binding_status": binding.get("binding_status"),
                "runtime_start_ready": True,
                "runtime_start_readiness_summary": dict(prepared.get("runtime_start_readiness_summary") or {}),
                "runtime_status": "runtime_start_ready_not_started",
                "runtime_started": False,
                "runtime_active": False,
                "strategy_active": False,
                "trial_started": False,
                "auto_within_budget_enabled": False,
                "owner_confirm_each_entry_enabled": False,
                "orders_placed": False,
                "withdrawal_executed": False,
                "transfer_executed": False,
                "live_ready": False,
                "idempotent": idempotent,
            },
            audit_refs=[binding_ref],
            campaign_refs=[campaign_ref],
            review_refs=[],
            final_state_snapshot={
                "campaign": campaign,
                "admission_trial_binding": binding,
                "runtime_status": "runtime_start_ready_not_started",
                "runtime_started": False,
                "strategy_active": False,
                "trial_started": False,
            },
        )

    async def _execute_trial_trade_intent_evaluation(
        self,
        *,
        operation: OperationRecord,
        preflight: PreflightSnapshot,
    ) -> ExecutionResult:
        if self._readers.trial_trade_intent_evaluator is None:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="blocked",
                blocked_reason="trial trade intent evaluator unavailable",
                recheck_result={"passed": False, "reason": "trial_trade_intent_evaluator_unavailable"},
                result_summary={
                    "operation_type": operation.operation_type,
                    "planned_result_status": "trial_trade_intent_evaluated",
                    "message": (
                        "Trial trade intent evaluator is not wired. No runtime, strategy, order, "
                        "execution intent, live action, withdrawal, or transfer was created."
                    ),
                    "intent_persisted": False,
                    "order_created": False,
                    "execution_intent_created": False,
                    "runtime_started": False,
                    "strategy_active": False,
                    "orders_placed": False,
                    "live_ready": False,
                },
                final_state_snapshot={"trade_intent": preflight.after},
            )

        payload = dict(operation.input_params)
        payload.update(
            {
                "operation_id": operation.operation_id,
                "preflight_id": preflight.preflight_id,
                "confirmed_by": operation.confirmed_by or "owner",
                "authorization_source": "brc_operation_layer",
            }
        )
        try:
            evaluated = await self._readers.trial_trade_intent_evaluator(payload)
        except ValueError as exc:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="blocked",
                blocked_reason=str(exc),
                recheck_result={"passed": False, "reason": str(exc)},
                result_summary={
                    "operation_type": operation.operation_type,
                    "planned_result_status": "trial_trade_intent_evaluated",
                    "message": (
                        "Trial trade intent evaluation was blocked. Runtime was not started; strategy was "
                        "not activated; no order or execution intent was created."
                    ),
                    "intent_persisted": False,
                    "order_created": False,
                    "execution_intent_created": False,
                    "runtime_started": False,
                    "strategy_active": False,
                    "orders_placed": False,
                    "live_ready": False,
                },
                final_state_snapshot={"trade_intent": preflight.after},
            )

        intent = dict(evaluated.get("intent") or {})
        intent_id = _optional_str(evaluated.get("intent_id") or intent.get("intent_id"))
        campaign_id = _optional_str(evaluated.get("campaign_id") or operation.input_params.get("campaign_id"))
        intent_ref = (
            {
                "type": "trial_trade_intent",
                "ref_id": intent_id,
                "campaign_id": campaign_id or intent.get("campaign_id"),
                "decision": evaluated.get("decision"),
                "non_executable_evidence_only": True,
            }
            if intent_id is not None
            else {
                "type": "trial_trade_intent_check",
                "ref_id": operation.operation_id,
                "campaign_id": campaign_id,
                "decision": evaluated.get("decision"),
                "non_executable_evidence_only": True,
            }
        )
        return await self._persist_result(
            operation=operation,
            preflight=preflight,
            status="executed",
            recheck_result={
                "passed": True,
                "execution_mode_enforcement_contract_only": True,
                "intent_persisted": bool(evaluated.get("intent_persisted", False)),
            },
            adapter_result={"trial_trade_intent": evaluated},
            result_summary={
                "operation_type": operation.operation_type,
                "planned_result_status": "trial_trade_intent_evaluated",
                "message": (
                    "Trial trade intent evaluated as non-executable evidence. Runtime not started; "
                    "strategy not active; no order or execution intent created."
                ),
                "intent_id": intent_id,
                "intent_persisted": bool(evaluated.get("intent_persisted", False)),
                "decision": evaluated.get("decision"),
                "not_executed_reason": evaluated.get("not_executed_reason"),
                "execution_mode": evaluated.get("execution_mode"),
                "constraints_check": dict(evaluated.get("constraints_check") or {}),
                "would_require_runtime_execution": bool(
                    evaluated.get("would_require_runtime_execution", False)
                ),
                "trial_trade_intent_is_order": False,
                "order_created": False,
                "execution_intent_created": False,
                "runtime_started": False,
                "runtime_active": False,
                "strategy_active": False,
                "trial_started": False,
                "auto_within_budget_enabled": False,
                "owner_confirm_each_entry_enabled": False,
                "orders_placed": False,
                "withdrawal_executed": False,
                "transfer_executed": False,
                "live_ready": False,
            },
            audit_refs=[intent_ref],
            campaign_refs=[intent_ref] if campaign_id is not None else [],
            review_refs=[],
            final_state_snapshot={
                "trial_trade_intent": intent,
                "execution_mode": evaluated.get("execution_mode"),
                "runtime_started": False,
                "strategy_active": False,
                "orders_placed": False,
            },
        )

    async def _execute_admission_runtime_handoff_preparation(
        self,
        *,
        operation: OperationRecord,
        preflight: PreflightSnapshot,
    ) -> ExecutionResult:
        if self._readers.admission_runtime_handoff_preparer is None:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="blocked",
                blocked_reason="admission runtime handoff preparer unavailable",
                recheck_result={"passed": False, "reason": "runtime_handoff_preparer_unavailable"},
                result_summary={
                    "operation_type": operation.operation_type,
                    "planned_result_status": "runtime_handoff_ready",
                    "message": (
                        "Runtime handoff preparer is not wired. No runtime handoff readiness metadata, "
                        "runtime start, strategy activation, auto execution, order, live execution, withdrawal, "
                        "or transfer was created."
                    ),
                    "runtime_handoff_ready": False,
                    "runtime_started": False,
                    "strategy_active": False,
                    "trial_started": False,
                    "auto_within_budget_enabled": False,
                    "orders_placed": False,
                    "live_ready": False,
                },
                final_state_snapshot={"runtime_handoff_readiness": preflight.after},
            )

        payload = dict(operation.input_params)
        payload.update(
            {
                "operation_id": operation.operation_id,
                "preflight_id": preflight.preflight_id,
                "confirmed_by": operation.confirmed_by or "owner",
                "authorization_source": "brc_operation_layer",
            }
        )
        try:
            prepared = await self._readers.admission_runtime_handoff_preparer(payload)
        except ValueError as exc:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="blocked",
                blocked_reason=str(exc),
                recheck_result={"passed": False, "reason": str(exc)},
                result_summary={
                    "operation_type": operation.operation_type,
                    "planned_result_status": "runtime_handoff_ready",
                    "message": (
                        "Runtime handoff readiness preparation was blocked. Runtime was not started; "
                        "runtime_started was not set true; strategy was not activated; auto execution was "
                        "not enabled; no order or execution intent was created."
                    ),
                    "runtime_handoff_ready": False,
                    "runtime_started": False,
                    "strategy_active": False,
                    "trial_started": False,
                    "auto_within_budget_enabled": False,
                    "orders_placed": False,
                    "live_ready": False,
                },
                final_state_snapshot={"runtime_handoff_readiness": preflight.after},
            )

        campaign = dict(prepared.get("campaign") or {})
        binding = dict(prepared.get("binding") or {})
        campaign_id = _optional_str(campaign.get("campaign_id") or operation.input_params.get("campaign_id"))
        binding_id = _optional_str(binding.get("binding_id") or operation.input_params.get("admission_binding_id"))
        idempotent = bool(prepared.get("idempotent", False))
        campaign_ref = {
            "type": "admission_runtime_handoff_ready",
            "campaign_id": campaign_id,
            "ref_id": campaign_id,
            "admission_binding_id": binding_id,
        }
        binding_ref = {
            "type": "admission_trial_binding",
            "ref_id": binding_id,
            "binding_status": binding.get("binding_status"),
            "campaign_id": campaign_id,
        }
        return await self._persist_result(
            operation=operation,
            preflight=preflight,
            status="noop" if idempotent else "executed",
            recheck_result={
                "passed": True,
                "runtime_handoff_readiness_metadata_only": True,
                "idempotent": idempotent,
            },
            adapter_result={"admission_runtime_handoff": prepared},
            result_summary={
                "operation_type": operation.operation_type,
                "planned_result_status": "runtime_handoff_ready",
                "message": (
                    "Runtime handoff readiness metadata already prepared. Runtime remains not started; "
                    "strategy remains inactive; auto execution remains disabled; no orders placed."
                    if idempotent
                    else "Runtime handoff readiness metadata prepared. Runtime not started; runtime_started false; strategy not active; auto execution disabled; no orders placed."
                ),
                "campaign_id": campaign_id,
                "binding_id": binding_id,
                "binding_status": binding.get("binding_status"),
                "runtime_handoff_ready": True,
                "runtime_handoff_readiness_summary": dict(prepared.get("runtime_handoff_readiness_summary") or {}),
                "runtime_status": "runtime_handoff_ready_not_started",
                "runtime_started": False,
                "runtime_active": False,
                "strategy_active": False,
                "trial_started": False,
                "auto_within_budget_enabled": False,
                "owner_confirm_each_entry_enabled": False,
                "order_created": False,
                "execution_intent_created": False,
                "orders_placed": False,
                "withdrawal_executed": False,
                "transfer_executed": False,
                "live_ready": False,
                "idempotent": idempotent,
            },
            audit_refs=[binding_ref],
            campaign_refs=[campaign_ref],
            review_refs=[],
            final_state_snapshot={
                "campaign": campaign,
                "admission_trial_binding": binding,
                "runtime_status": "runtime_handoff_ready_not_started",
                "runtime_started": False,
                "strategy_active": False,
                "trial_started": False,
            },
        )

    async def _execute_admission_runtime_start_from_handoff(
        self,
        *,
        operation: OperationRecord,
        preflight: PreflightSnapshot,
    ) -> ExecutionResult:
        if self._readers.admission_runtime_start_from_handoff_starter is None:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="blocked",
                blocked_reason="admission runtime start from handoff starter unavailable",
                recheck_result={"passed": False, "reason": "runtime_start_starter_unavailable"},
                result_summary={
                    "operation_type": operation.operation_type,
                    "planned_result_status": "runtime_started_strategy_inactive",
                    "message": (
                        "Runtime start was blocked before metadata transition. Strategy was not activated; "
                        "trial was not started; auto execution was not enabled; no order or execution intent was created."
                    ),
                    "runtime_started": False,
                    "strategy_active": False,
                    "trial_started": False,
                    "auto_within_budget_enabled": False,
                    "auto_execution_enabled": False,
                    "orders_placed": False,
                    "live_ready": False,
                },
                final_state_snapshot={"runtime_start": preflight.after},
            )

        payload = dict(operation.input_params)
        payload.update(
            {
                "operation_id": operation.operation_id,
                "preflight_id": preflight.preflight_id,
                "confirmed_by": operation.confirmed_by or "owner",
                "authorization_source": "brc_operation_layer",
            }
        )
        try:
            started = await self._readers.admission_runtime_start_from_handoff_starter(payload)
        except Exception as exc:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="blocked",
                blocked_reason=str(exc),
                recheck_result={"passed": False, "reason": str(exc)},
                result_summary={
                    "operation_type": operation.operation_type,
                    "planned_result_status": "runtime_started_strategy_inactive",
                    "message": (
                        "Runtime start state transition was blocked. Strategy was not activated; "
                        "trial was not started; auto execution was not enabled; no order or execution intent was created."
                    ),
                    "runtime_started": False,
                    "strategy_active": False,
                    "trial_started": False,
                    "auto_within_budget_enabled": False,
                    "auto_execution_enabled": False,
                    "orders_placed": False,
                    "live_ready": False,
                },
                final_state_snapshot={"runtime_start": preflight.after},
            )

        campaign = dict(started.get("campaign") or {})
        binding = dict(started.get("binding") or {})
        campaign_id = _optional_str(campaign.get("campaign_id") or operation.input_params.get("campaign_id"))
        binding_id = _optional_str(binding.get("binding_id") or operation.input_params.get("admission_binding_id"))
        idempotent = bool(started.get("idempotent", False))
        campaign_ref = {
            "type": "admission_runtime_started",
            "campaign_id": campaign_id,
            "ref_id": campaign_id,
            "admission_binding_id": binding_id,
        }
        binding_ref = {
            "type": "admission_trial_binding",
            "ref_id": binding_id,
            "binding_status": binding.get("binding_status"),
            "campaign_id": campaign_id,
        }
        return await self._persist_result(
            operation=operation,
            preflight=preflight,
            status="noop" if idempotent else "executed",
            recheck_result={
                "passed": True,
                "runtime_state_started_only": True,
                "idempotent": idempotent,
            },
            adapter_result={"admission_runtime_start": started},
            result_summary={
                "operation_type": operation.operation_type,
                "planned_result_status": "runtime_started_strategy_inactive",
                "message": (
                    "Runtime state was already started with strategy inactive. No duplicate transition was written; "
                    "strategy remains inactive; trial remains not started; auto execution remains disabled; no orders placed."
                    if idempotent
                    else "Runtime state started from admission handoff. Strategy remains inactive; trial remains not started; auto execution disabled; no orders placed."
                ),
                "campaign_id": campaign_id,
                "binding_id": binding_id,
                "binding_status": binding.get("binding_status"),
                "runtime_start_summary": dict(started.get("runtime_start_summary") or {}),
                "runtime_status": "runtime_started_strategy_inactive",
                "runtime_started": True,
                "runtime_active": False,
                "strategy_active": False,
                "trial_started": False,
                "auto_within_budget_enabled": False,
                "auto_execution_enabled": False,
                "owner_confirm_each_entry_enabled": False,
                "order_created": False,
                "execution_intent_created": False,
                "orders_placed": False,
                "withdrawal_executed": False,
                "transfer_executed": False,
                "live_ready": False,
                "idempotent": idempotent,
            },
            audit_refs=[binding_ref],
            campaign_refs=[campaign_ref],
            review_refs=[],
            final_state_snapshot={
                "campaign": campaign,
                "admission_trial_binding": binding,
                "runtime_status": "runtime_started_strategy_inactive",
                "runtime_started": True,
                "strategy_active": False,
                "trial_started": False,
            },
        )

    async def _execute_admission_strategy_activation_preparation(
        self,
        *,
        operation: OperationRecord,
        preflight: PreflightSnapshot,
    ) -> ExecutionResult:
        if self._readers.admission_strategy_activation_preparer is None:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="blocked",
                blocked_reason="admission strategy activation preparer unavailable",
                recheck_result={"passed": False, "reason": "strategy_activation_preparer_unavailable"},
                result_summary={
                    "operation_type": operation.operation_type,
                    "planned_result_status": "strategy_activation_ready",
                    "message": (
                        "Strategy activation readiness preparation was blocked. Strategy was not activated; "
                        "signal loop was not started; auto execution was not enabled; no execution intent or order was created."
                    ),
                    "strategy_activation_ready": False,
                    "strategy_active": False,
                    "trial_started": False,
                    "signal_loop_started": False,
                    "auto_within_budget_enabled": False,
                    "auto_execution_enabled": False,
                    "execution_intent_created": False,
                    "orders_placed": False,
                    "live_ready": False,
                },
                final_state_snapshot={"strategy_activation_readiness": preflight.after},
            )

        payload = dict(operation.input_params)
        payload.update(
            {
                "operation_id": operation.operation_id,
                "preflight_id": preflight.preflight_id,
                "confirmed_by": operation.confirmed_by or "owner",
                "authorization_source": "brc_operation_layer",
            }
        )
        try:
            prepared = await self._readers.admission_strategy_activation_preparer(payload)
        except Exception as exc:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="blocked",
                blocked_reason=str(exc),
                recheck_result={"passed": False, "reason": str(exc)},
                result_summary={
                    "operation_type": operation.operation_type,
                    "planned_result_status": "strategy_activation_ready",
                    "message": (
                        "Strategy activation readiness metadata preparation was blocked. Strategy was not activated; "
                        "signal loop was not started; auto execution was not enabled; no execution intent or order was created."
                    ),
                    "strategy_activation_ready": False,
                    "strategy_active": False,
                    "trial_started": False,
                    "signal_loop_started": False,
                    "auto_within_budget_enabled": False,
                    "auto_execution_enabled": False,
                    "execution_intent_created": False,
                    "orders_placed": False,
                    "live_ready": False,
                },
                final_state_snapshot={"strategy_activation_readiness": preflight.after},
            )

        campaign = dict(prepared.get("campaign") or {})
        binding = dict(prepared.get("binding") or {})
        campaign_id = _optional_str(campaign.get("campaign_id") or operation.input_params.get("campaign_id"))
        binding_id = _optional_str(binding.get("binding_id") or operation.input_params.get("admission_binding_id"))
        idempotent = bool(prepared.get("idempotent", False))
        campaign_ref = {
            "type": "admission_strategy_activation_ready",
            "campaign_id": campaign_id,
            "ref_id": campaign_id,
            "admission_binding_id": binding_id,
        }
        binding_ref = {
            "type": "admission_trial_binding",
            "ref_id": binding_id,
            "binding_status": binding.get("binding_status"),
            "campaign_id": campaign_id,
        }
        return await self._persist_result(
            operation=operation,
            preflight=preflight,
            status="noop" if idempotent else "executed",
            recheck_result={
                "passed": True,
                "strategy_activation_readiness_metadata_only": True,
                "idempotent": idempotent,
            },
            adapter_result={"admission_strategy_activation": prepared},
            result_summary={
                "operation_type": operation.operation_type,
                "planned_result_status": "strategy_activation_ready",
                "message": (
                    "Strategy activation readiness metadata already prepared. Strategy remains inactive; "
                    "signal loop remains inactive; auto execution remains disabled; no execution intent or order was created."
                    if idempotent
                    else "Strategy activation readiness metadata prepared. Strategy not active; signal loop inactive; auto execution disabled; no execution intent or order created."
                ),
                "campaign_id": campaign_id,
                "binding_id": binding_id,
                "binding_status": binding.get("binding_status"),
                "strategy_activation_ready": True,
                "strategy_activation_readiness_summary": dict(
                    prepared.get("strategy_activation_readiness_summary") or {}
                ),
                "runtime_status": "strategy_activation_ready_not_active",
                "runtime_started": True,
                "strategy_active": False,
                "trial_started": False,
                "signal_loop_started": False,
                "auto_within_budget_enabled": False,
                "auto_execution_enabled": False,
                "owner_confirm_each_entry_enabled": False,
                "trade_intent_created": False,
                "execution_intent_created": False,
                "order_created": False,
                "orders_placed": False,
                "withdrawal_executed": False,
                "transfer_executed": False,
                "live_ready": False,
                "idempotent": idempotent,
            },
            audit_refs=[binding_ref],
            campaign_refs=[campaign_ref],
            review_refs=[],
            final_state_snapshot={
                "campaign": campaign,
                "admission_trial_binding": binding,
                "runtime_status": "strategy_activation_ready_not_active",
                "strategy_active": False,
                "trial_started": False,
                "signal_loop_started": False,
            },
        )

    async def _execute_admission_strategy_state_activation(
        self,
        *,
        operation: OperationRecord,
        preflight: PreflightSnapshot,
    ) -> ExecutionResult:
        if self._readers.admission_strategy_state_activator is None:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="blocked",
                blocked_reason="admission strategy state activator unavailable",
                recheck_result={"passed": False, "reason": "strategy_state_activator_unavailable"},
                result_summary={
                    "operation_type": operation.operation_type,
                    "planned_result_status": "strategy_active_no_execution",
                    "message": (
                        "Strategy state activation was blocked. Strategy runner was not started; "
                        "signal loop was not started; auto execution was not enabled; no execution intent or order was created."
                    ),
                    "strategy_active": False,
                    "strategy_execution_enabled": False,
                    "trial_started": False,
                    "signal_loop_enabled": False,
                    "signal_loop_started": False,
                    "auto_within_budget_enabled": False,
                    "auto_execution_enabled": False,
                    "trade_intent_created": False,
                    "execution_intent_created": False,
                    "order_created": False,
                    "orders_placed": False,
                    "live_ready": False,
                },
                final_state_snapshot={"strategy_state_activation": preflight.after},
            )

        payload = dict(operation.input_params)
        payload.update(
            {
                "operation_id": operation.operation_id,
                "preflight_id": preflight.preflight_id,
                "confirmed_by": operation.confirmed_by or "owner",
                "authorization_source": "brc_operation_layer",
            }
        )
        try:
            activated = await self._readers.admission_strategy_state_activator(payload)
        except Exception as exc:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="blocked",
                blocked_reason=str(exc),
                recheck_result={"passed": False, "reason": str(exc)},
                result_summary={
                    "operation_type": operation.operation_type,
                    "planned_result_status": "strategy_active_no_execution",
                    "message": (
                        "Strategy state activation metadata transition was blocked. Strategy runner was not started; "
                        "signal loop was not started; auto execution was not enabled; no execution intent or order was created."
                    ),
                    "strategy_active": False,
                    "strategy_execution_enabled": False,
                    "trial_started": False,
                    "signal_loop_enabled": False,
                    "signal_loop_started": False,
                    "auto_within_budget_enabled": False,
                    "auto_execution_enabled": False,
                    "trade_intent_created": False,
                    "execution_intent_created": False,
                    "order_created": False,
                    "orders_placed": False,
                    "live_ready": False,
                },
                final_state_snapshot={"strategy_state_activation": preflight.after},
            )

        campaign = dict(activated.get("campaign") or {})
        binding = dict(activated.get("binding") or {})
        campaign_id = _optional_str(campaign.get("campaign_id") or operation.input_params.get("campaign_id"))
        binding_id = _optional_str(binding.get("binding_id") or operation.input_params.get("admission_binding_id"))
        idempotent = bool(activated.get("idempotent", False))
        campaign_ref = {
            "type": "admission_strategy_activated_no_execution",
            "campaign_id": campaign_id,
            "ref_id": campaign_id,
            "admission_binding_id": binding_id,
        }
        binding_ref = {
            "type": "admission_trial_binding",
            "ref_id": binding_id,
            "binding_status": binding.get("binding_status"),
            "campaign_id": campaign_id,
        }
        return await self._persist_result(
            operation=operation,
            preflight=preflight,
            status="noop" if idempotent else "executed",
            recheck_result={
                "passed": True,
                "strategy_state_activation_metadata_only": True,
                "idempotent": idempotent,
            },
            adapter_result={"admission_strategy_state_activation": activated},
            result_summary={
                "operation_type": operation.operation_type,
                "planned_result_status": "strategy_active_no_execution",
                "message": (
                    "Strategy metadata already active in non-execution state. Signal loop remains inactive; "
                    "auto execution remains disabled; no execution intent or order was created."
                    if idempotent
                    else "Strategy metadata activated in non-execution state. Signal loop inactive; auto execution disabled; no execution intent or order created."
                ),
                "campaign_id": campaign_id,
                "binding_id": binding_id,
                "binding_status": binding.get("binding_status"),
                "strategy_state": "strategy_active_no_execution",
                "strategy_activation_state": "active_no_execution",
                "strategy_state_activation_summary": dict(
                    activated.get("strategy_state_activation_summary") or {}
                ),
                "runtime_status": "strategy_active_no_execution",
                "runtime_started": True,
                "strategy_active": True,
                "strategy_execution_enabled": False,
                "trial_started": False,
                "signal_loop_enabled": False,
                "signal_loop_started": False,
                "auto_within_budget_enabled": False,
                "auto_execution_enabled": False,
                "owner_confirm_each_entry_enabled": False,
                "trade_intent_created": False,
                "execution_intent_created": False,
                "order_created": False,
                "orders_placed": False,
                "withdrawal_executed": False,
                "transfer_executed": False,
                "live_ready": False,
                "idempotent": idempotent,
            },
            audit_refs=[binding_ref],
            campaign_refs=[campaign_ref],
            review_refs=[],
            final_state_snapshot={
                "campaign": campaign,
                "admission_trial_binding": binding,
                "runtime_status": "strategy_active_no_execution",
                "strategy_state": "strategy_active_no_execution",
                "strategy_active": True,
                "strategy_execution_enabled": False,
                "trial_started": False,
                "signal_loop_enabled": False,
                "signal_loop_started": False,
            },
        )

    async def _execute_admission_signal_loop_preparation(
        self,
        *,
        operation: OperationRecord,
        preflight: PreflightSnapshot,
    ) -> ExecutionResult:
        if self._readers.admission_signal_loop_preparer is None:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="blocked",
                blocked_reason="admission signal loop preparer unavailable",
                recheck_result={"passed": False, "reason": "signal_loop_preparer_unavailable"},
                result_summary={
                    "operation_type": operation.operation_type,
                    "planned_result_status": "signal_loop_ready_not_started",
                    "message": (
                        "Signal loop readiness preparation was blocked. Signal loop was not started; "
                        "no signal was generated; no trade intent, execution intent, or order was created."
                    ),
                    "signal_loop_ready": False,
                    "signal_loop_enabled": False,
                    "signal_loop_started": False,
                    "signal_generated": False,
                    "strategy_execution_enabled": False,
                    "trial_started": False,
                    "auto_within_budget_enabled": False,
                    "auto_execution_enabled": False,
                    "trade_intent_created": False,
                    "execution_intent_created": False,
                    "order_created": False,
                    "orders_placed": False,
                    "live_ready": False,
                },
                final_state_snapshot={"signal_loop_readiness": preflight.after},
            )

        payload = dict(operation.input_params)
        payload.update(
            {
                "operation_id": operation.operation_id,
                "preflight_id": preflight.preflight_id,
                "confirmed_by": operation.confirmed_by or "owner",
                "authorization_source": "brc_operation_layer",
            }
        )
        try:
            prepared = await self._readers.admission_signal_loop_preparer(payload)
        except Exception as exc:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="blocked",
                blocked_reason=str(exc),
                recheck_result={"passed": False, "reason": str(exc)},
                result_summary={
                    "operation_type": operation.operation_type,
                    "planned_result_status": "signal_loop_ready_not_started",
                    "message": (
                        "Signal loop readiness metadata preparation was blocked. Signal loop was not started; "
                        "no signal was generated; no trade intent, execution intent, or order was created."
                    ),
                    "signal_loop_ready": False,
                    "signal_loop_enabled": False,
                    "signal_loop_started": False,
                    "signal_generated": False,
                    "strategy_execution_enabled": False,
                    "trial_started": False,
                    "auto_within_budget_enabled": False,
                    "auto_execution_enabled": False,
                    "trade_intent_created": False,
                    "execution_intent_created": False,
                    "order_created": False,
                    "orders_placed": False,
                    "live_ready": False,
                },
                final_state_snapshot={"signal_loop_readiness": preflight.after},
            )

        campaign = dict(prepared.get("campaign") or {})
        binding = dict(prepared.get("binding") or {})
        campaign_id = _optional_str(campaign.get("campaign_id") or operation.input_params.get("campaign_id"))
        binding_id = _optional_str(binding.get("binding_id") or operation.input_params.get("admission_binding_id"))
        idempotent = bool(prepared.get("idempotent", False))
        campaign_ref = {
            "type": "admission_signal_loop_ready",
            "campaign_id": campaign_id,
            "ref_id": campaign_id,
            "admission_binding_id": binding_id,
        }
        binding_ref = {
            "type": "admission_trial_binding",
            "ref_id": binding_id,
            "binding_status": binding.get("binding_status"),
            "campaign_id": campaign_id,
        }
        return await self._persist_result(
            operation=operation,
            preflight=preflight,
            status="noop" if idempotent else "executed",
            recheck_result={
                "passed": True,
                "signal_loop_readiness_metadata_only": True,
                "idempotent": idempotent,
            },
            adapter_result={"admission_signal_loop_readiness": prepared},
            result_summary={
                "operation_type": operation.operation_type,
                "planned_result_status": "signal_loop_ready_not_started",
                "message": (
                    "Signal loop readiness metadata already prepared. Signal loop remains not started; "
                    "no signal was generated; no execution intent or order was created."
                    if idempotent
                    else "Signal loop readiness metadata prepared. Signal loop not started; no signal generated; no trade intent, execution intent, or order created."
                ),
                "campaign_id": campaign_id,
                "binding_id": binding_id,
                "binding_status": binding.get("binding_status"),
                "signal_loop_ready": True,
                "signal_loop_readiness_summary": dict(
                    prepared.get("signal_loop_readiness_summary") or {}
                ),
                "runtime_status": "signal_loop_ready_not_started",
                "runtime_started": True,
                "strategy_active": True,
                "strategy_execution_enabled": False,
                "trial_started": False,
                "signal_loop_enabled": False,
                "signal_loop_started": False,
                "signal_generated": False,
                "auto_within_budget_enabled": False,
                "auto_execution_enabled": False,
                "owner_confirm_each_entry_enabled": False,
                "trade_intent_created": False,
                "execution_intent_created": False,
                "order_created": False,
                "orders_placed": False,
                "withdrawal_executed": False,
                "transfer_executed": False,
                "live_ready": False,
                "idempotent": idempotent,
            },
            audit_refs=[binding_ref],
            campaign_refs=[campaign_ref],
            review_refs=[],
            final_state_snapshot={
                "campaign": campaign,
                "admission_trial_binding": binding,
                "runtime_status": "signal_loop_ready_not_started",
                "signal_loop_ready": True,
                "signal_loop_enabled": False,
                "signal_loop_started": False,
                "signal_generated": False,
                "strategy_execution_enabled": False,
            },
        )

    async def _execute_admission_signal_loop_start(
        self,
        *,
        operation: OperationRecord,
        preflight: PreflightSnapshot,
    ) -> ExecutionResult:
        if self._readers.admission_signal_loop_starter is None:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="blocked",
                blocked_reason="admission signal loop starter unavailable",
                recheck_result={"passed": False, "reason": "signal_loop_starter_unavailable"},
                result_summary={
                    "operation_type": operation.operation_type,
                    "planned_result_status": "signal_loop_started_no_signal",
                    "message": (
                        "Signal loop state start was blocked. No signal was generated; "
                        "no trade intent, execution intent, or order was created."
                    ),
                    "signal_loop_started": False,
                    "signal_loop_enabled": False,
                    "signal_generated": False,
                    "strategy_execution_enabled": False,
                    "trial_started": False,
                    "auto_within_budget_enabled": False,
                    "auto_execution_enabled": False,
                    "trade_intent_created": False,
                    "execution_intent_created": False,
                    "order_created": False,
                    "orders_placed": False,
                    "live_ready": False,
                },
                final_state_snapshot={"signal_loop_start": preflight.after},
            )

        payload = dict(operation.input_params)
        payload.update(
            {
                "operation_id": operation.operation_id,
                "preflight_id": preflight.preflight_id,
                "confirmed_by": operation.confirmed_by or "owner",
                "authorization_source": "brc_operation_layer",
            }
        )
        try:
            started = await self._readers.admission_signal_loop_starter(payload)
        except Exception as exc:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="blocked",
                blocked_reason=str(exc),
                recheck_result={"passed": False, "reason": str(exc)},
                result_summary={
                    "operation_type": operation.operation_type,
                    "planned_result_status": "signal_loop_started_no_signal",
                    "message": (
                        "Signal loop state metadata transition was blocked. No signal was generated; "
                        "no trade intent, execution intent, or order was created."
                    ),
                    "signal_loop_started": False,
                    "signal_loop_enabled": False,
                    "signal_generated": False,
                    "strategy_execution_enabled": False,
                    "trial_started": False,
                    "auto_within_budget_enabled": False,
                    "auto_execution_enabled": False,
                    "trade_intent_created": False,
                    "execution_intent_created": False,
                    "order_created": False,
                    "orders_placed": False,
                    "live_ready": False,
                },
                final_state_snapshot={"signal_loop_start": preflight.after},
            )

        campaign = dict(started.get("campaign") or {})
        binding = dict(started.get("binding") or {})
        campaign_id = _optional_str(campaign.get("campaign_id") or operation.input_params.get("campaign_id"))
        binding_id = _optional_str(binding.get("binding_id") or operation.input_params.get("admission_binding_id"))
        idempotent = bool(started.get("idempotent", False))
        campaign_ref = {
            "type": "admission_signal_loop_started_no_signal",
            "campaign_id": campaign_id,
            "ref_id": campaign_id,
            "admission_binding_id": binding_id,
        }
        binding_ref = {
            "type": "admission_trial_binding",
            "ref_id": binding_id,
            "binding_status": binding.get("binding_status"),
            "campaign_id": campaign_id,
        }
        return await self._persist_result(
            operation=operation,
            preflight=preflight,
            status="noop" if idempotent else "executed",
            recheck_result={
                "passed": True,
                "signal_loop_start_state_metadata_only": True,
                "idempotent": idempotent,
            },
            adapter_result={"admission_signal_loop_start": started},
            result_summary={
                "operation_type": operation.operation_type,
                "planned_result_status": "signal_loop_started_no_signal",
                "message": (
                    "Signal loop state metadata already started without signal generation. "
                    "No trade intent, execution intent, or order was created."
                    if idempotent
                    else "Signal loop state metadata started. No signal generated; no trade intent, execution intent, or order created."
                ),
                "campaign_id": campaign_id,
                "binding_id": binding_id,
                "binding_status": binding.get("binding_status"),
                "signal_loop_start_summary": dict(
                    started.get("signal_loop_start_summary") or {}
                ),
                "runtime_status": "signal_loop_started_no_signal",
                "runtime_started": True,
                "strategy_active": True,
                "strategy_execution_enabled": False,
                "signal_loop_ready": True,
                "signal_loop_enabled": True,
                "signal_loop_enabled_scope": "non_trading_loop_state",
                "signal_loop_started": True,
                "signal_generated": False,
                "trial_started": False,
                "auto_within_budget_enabled": False,
                "auto_execution_enabled": False,
                "owner_confirm_each_entry_enabled": False,
                "trade_intent_created": False,
                "execution_intent_created": False,
                "order_created": False,
                "orders_placed": False,
                "withdrawal_executed": False,
                "transfer_executed": False,
                "live_ready": False,
                "idempotent": idempotent,
            },
            audit_refs=[binding_ref],
            campaign_refs=[campaign_ref],
            review_refs=[],
            final_state_snapshot={
                "campaign": campaign,
                "admission_trial_binding": binding,
                "runtime_status": "signal_loop_started_no_signal",
                "signal_loop_enabled": True,
                "signal_loop_enabled_scope": "non_trading_loop_state",
                "signal_loop_started": True,
                "signal_generated": False,
                "trade_intent_created": False,
                "execution_intent_created": False,
                "order_created": False,
                "orders_placed": False,
            },
        )

    async def _execute_admission_signal_evaluation(
        self,
        *,
        operation: OperationRecord,
        preflight: PreflightSnapshot,
    ) -> ExecutionResult:
        if self._readers.admission_signal_evaluator is None:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="blocked",
                blocked_reason="admission signal evaluator unavailable",
                recheck_result={"passed": False, "reason": "signal_evaluator_unavailable"},
                result_summary={
                    "operation_type": operation.operation_type,
                    "planned_result_status": "signal_evaluated_no_intent",
                    "message": (
                        "Signal evaluation recording was blocked. No trade intent, "
                        "execution intent, or order was created."
                    ),
                    "signal_evaluated": False,
                    "signal_generated": False,
                    "trade_intent_created": False,
                    "execution_intent_created": False,
                    "order_created": False,
                    "orders_placed": False,
                    "strategy_execution_enabled": False,
                    "trial_started": False,
                    "auto_within_budget_enabled": False,
                    "auto_execution_enabled": False,
                    "live_ready": False,
                },
                final_state_snapshot={"signal_evaluation": preflight.after},
            )

        payload = dict(operation.input_params)
        payload.update(
            {
                "operation_id": operation.operation_id,
                "preflight_id": preflight.preflight_id,
                "confirmed_by": operation.confirmed_by or "owner",
                "authorization_source": "brc_operation_layer",
            }
        )
        try:
            evaluated = await self._readers.admission_signal_evaluator(payload)
        except Exception as exc:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="blocked",
                blocked_reason=str(exc),
                recheck_result={"passed": False, "reason": str(exc)},
                result_summary={
                    "operation_type": operation.operation_type,
                    "planned_result_status": "signal_evaluated_no_intent",
                    "message": (
                        "Signal evaluation metadata recording was blocked. No trade intent, "
                        "execution intent, or order was created."
                    ),
                    "signal_evaluated": False,
                    "signal_generated": False,
                    "trade_intent_created": False,
                    "execution_intent_created": False,
                    "order_created": False,
                    "orders_placed": False,
                    "strategy_execution_enabled": False,
                    "trial_started": False,
                    "auto_within_budget_enabled": False,
                    "auto_execution_enabled": False,
                    "live_ready": False,
                },
                final_state_snapshot={"signal_evaluation": preflight.after},
            )

        campaign = dict(evaluated.get("campaign") or {})
        binding = dict(evaluated.get("binding") or {})
        campaign_id = _optional_str(campaign.get("campaign_id") or operation.input_params.get("campaign_id"))
        binding_id = _optional_str(binding.get("binding_id") or operation.input_params.get("admission_binding_id"))
        idempotent = bool(evaluated.get("idempotent", False))
        campaign_ref = {
            "type": "admission_signal_evaluated_no_intent",
            "campaign_id": campaign_id,
            "ref_id": campaign_id,
            "admission_binding_id": binding_id,
        }
        binding_ref = {
            "type": "admission_trial_binding",
            "ref_id": binding_id,
            "binding_status": binding.get("binding_status"),
            "campaign_id": campaign_id,
        }
        return await self._persist_result(
            operation=operation,
            preflight=preflight,
            status="noop" if idempotent else "executed",
            recheck_result={
                "passed": True,
                "signal_evaluation_metadata_only": True,
                "idempotent": idempotent,
            },
            adapter_result={"admission_signal_evaluation": evaluated},
            result_summary={
                "operation_type": operation.operation_type,
                "planned_result_status": "signal_evaluated_no_intent",
                "message": (
                    "Signal evaluation metadata already recorded without intent. No trade intent, execution intent, or order was created."
                    if idempotent
                    else "Signal evaluation metadata recorded. No trade intent, execution intent, or order created."
                ),
                "campaign_id": campaign_id,
                "binding_id": binding_id,
                "binding_status": binding.get("binding_status"),
                "signal_evaluation_summary": dict(
                    evaluated.get("signal_evaluation_summary") or {}
                ),
                "runtime_status": "signal_evaluated_no_intent",
                "runtime_started": True,
                "strategy_active": True,
                "strategy_execution_enabled": False,
                "signal_loop_started": True,
                "signal_loop_enabled": True,
                "signal_loop_enabled_scope": "non_trading_loop_state",
                "signal_evaluated": True,
                "signal_generated": True,
                "signal_is_trade_intent": False,
                "trade_intent_created": False,
                "execution_intent_created": False,
                "order_created": False,
                "orders_placed": False,
                "trial_started": False,
                "auto_within_budget_enabled": False,
                "auto_execution_enabled": False,
                "owner_confirm_each_entry_enabled": False,
                "withdrawal_executed": False,
                "transfer_executed": False,
                "live_ready": False,
                "idempotent": idempotent,
            },
            audit_refs=[binding_ref],
            campaign_refs=[campaign_ref],
            review_refs=[],
            final_state_snapshot={
                "campaign": campaign,
                "admission_trial_binding": binding,
                "runtime_status": "signal_evaluated_no_intent",
                "signal_evaluated": True,
                "signal_generated": True,
                "signal_is_trade_intent": False,
                "trade_intent_created": False,
                "execution_intent_created": False,
                "order_created": False,
                "orders_placed": False,
            },
        )

    async def _execute_signal_trade_intent_recording(
        self,
        *,
        operation: OperationRecord,
        preflight: PreflightSnapshot,
    ) -> ExecutionResult:
        if self._readers.signal_trade_intent_recorder is None:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="blocked",
                blocked_reason="signal trade intent recorder unavailable",
                recheck_result={"passed": False, "reason": "signal_trade_intent_recorder_unavailable"},
                result_summary={
                    "operation_type": operation.operation_type,
                    "planned_result_status": "trial_trade_intent_recorded_no_execution",
                    "message": (
                        "Signal-to-trial-trade-intent recorder is not wired. No execution intent, "
                        "order, auto execution, live action, withdrawal, or transfer was created."
                    ),
                    "intent_persisted": False,
                    "execution_intent_created": False,
                    "order_created": False,
                    "orders_placed": False,
                    "trial_started": False,
                    "auto_execution_enabled": False,
                    "auto_within_budget_enabled": False,
                    "live_ready": False,
                },
                final_state_snapshot={"trade_intent": preflight.after},
            )

        payload = dict(operation.input_params)
        payload.update(
            {
                "operation_id": operation.operation_id,
                "preflight_id": preflight.preflight_id,
                "confirmed_by": operation.confirmed_by or "owner",
                "authorization_source": "brc_operation_layer",
                "execution_permission_resolution": dict(
                    preflight.after.get("execution_permission_resolution") or {}
                ),
            }
        )
        try:
            recorded = await self._readers.signal_trade_intent_recorder(payload)
        except Exception as exc:
            return await self._persist_result(
                operation=operation,
                preflight=preflight,
                status="blocked",
                blocked_reason=str(exc),
                recheck_result={"passed": False, "reason": str(exc)},
                result_summary={
                    "operation_type": operation.operation_type,
                    "planned_result_status": "trial_trade_intent_recorded_no_execution",
                    "message": (
                        "Trial trade intent recording was blocked. No execution intent, "
                        "order, auto execution, live action, withdrawal, or transfer was created."
                    ),
                    "intent_persisted": False,
                    "execution_intent_created": False,
                    "order_created": False,
                    "orders_placed": False,
                    "trial_started": False,
                    "auto_execution_enabled": False,
                    "auto_within_budget_enabled": False,
                    "live_ready": False,
                },
                final_state_snapshot={"trade_intent": preflight.after},
            )

        intent = dict(recorded.get("intent") or {})
        intent_id = _optional_str(recorded.get("intent_id") or intent.get("intent_id"))
        campaign = dict(recorded.get("campaign") or {})
        campaign_id = _optional_str(
            recorded.get("campaign_id")
            or campaign.get("campaign_id")
            or operation.input_params.get("campaign_id")
            or preflight.after.get("campaign_id")
        )
        binding_id = _optional_str(recorded.get("binding_id") or preflight.after.get("binding_id"))
        idempotent = bool(recorded.get("idempotent", False))
        intent_ref = {
            "type": "trial_trade_intent",
            "ref_id": intent_id,
            "campaign_id": campaign_id,
            "decision": recorded.get("decision"),
            "non_executable_evidence_only": True,
        }
        campaign_ref = {
            "type": "admission_trial_trade_intent_recorded_no_execution",
            "ref_id": campaign_id,
            "campaign_id": campaign_id,
            "admission_binding_id": binding_id,
        }
        return await self._persist_result(
            operation=operation,
            preflight=preflight,
            status="noop" if idempotent else "executed",
            recheck_result={
                "passed": True,
                "trial_trade_intent_evidence_only": True,
                "intent_persisted": bool(recorded.get("intent_persisted", False)),
                "idempotent": idempotent,
            },
            adapter_result={"signal_trial_trade_intent": recorded},
            result_summary={
                "operation_type": operation.operation_type,
                "planned_result_status": "trial_trade_intent_recorded_no_execution",
                "message": (
                    "Trial trade intent already recorded as non-executable evidence. No execution intent or order was created."
                    if idempotent
                    else "Trial trade intent recorded as non-executable evidence. No execution intent or order created."
                ),
                "campaign_id": campaign_id,
                "binding_id": binding_id,
                "intent_id": intent_id,
                "intent_persisted": bool(recorded.get("intent_persisted", False)),
                "decision": recorded.get("decision"),
                "not_executed_reason": recorded.get("not_executed_reason"),
                "execution_mode": recorded.get("execution_mode"),
                "execution_permission_resolution": dict(
                    recorded.get("execution_permission_resolution") or preflight.after.get("execution_permission_resolution") or {}
                ),
                "runtime_status": "trial_trade_intent_recorded_no_execution",
                "trial_trade_intent_created": bool(recorded.get("intent_persisted", False)),
                "trial_trade_intent_is_order": False,
                "execution_intent_created": False,
                "order_created": False,
                "orders_placed": False,
                "trial_started": False,
                "auto_execution_enabled": False,
                "auto_within_budget_enabled": False,
                "withdrawal_executed": False,
                "transfer_executed": False,
                "live_ready": False,
                "idempotent": idempotent,
            },
            audit_refs=[intent_ref],
            campaign_refs=[campaign_ref],
            review_refs=[],
            final_state_snapshot={
                "trial_trade_intent": intent,
                "campaign": campaign,
                "runtime_status": "trial_trade_intent_recorded_no_execution",
                "execution_intent_created": False,
                "order_created": False,
                "orders_placed": False,
            },
        )

    async def _execute_gated_trial_from_admission_disabled(
        self,
        *,
        operation: OperationRecord,
        preflight: PreflightSnapshot,
    ) -> ExecutionResult:
        return await self._persist_result(
            operation=operation,
            preflight=preflight,
            status="blocked",
            blocked_reason="create_gated_trial_from_admission runtime creation is not implemented",
            recheck_result={"passed": False, "reason": "confirm_disabled"},
            adapter_result={"phase": "BRC-R5-002 Phase 4", "binding_reservation_only": True},
            result_summary={
                "operation_type": operation.operation_type,
                "planned_result_status": "binding_reserved",
                "message": (
                    "Phase 4 only reserves admission-trial bindings. No trial, campaign, runtime carrier, "
                    "runtime constraints, order, live execution, withdrawal, or transfer was created."
                ),
                "mutation_executed": False,
                "runtime_creation_executed": False,
                "campaign_creation_executed": False,
                "runtime_constraints_installed": False,
                "live_ready": False,
            },
            final_state_snapshot={"admission_readiness": preflight.after},
        )

    async def _confirm_failure_reason(
        self,
        *,
        operation: OperationRecord,
        preflight: PreflightSnapshot,
        confirmation_phrase: str,
        idempotency_key: str,
    ) -> Optional[str]:
        policy = self._effective_policy(operation.operation_type)
        if operation.status != "awaiting_confirmation":
            return f"operation status is {operation.status}, not awaiting_confirmation"
        if preflight.expires_at_ms < now_ms():
            return "preflight expired"
        if preflight.idempotency_key != idempotency_key:
            return "idempotency_key mismatch"
        if (
            preflight.confirmation_requirement.phrase is not None
            and preflight.confirmation_requirement.phrase != confirmation_phrase
        ):
            return "confirmation phrase mismatch"
        if operation.operation_type in _FORBIDDEN_OPERATION_TYPES:
            return "operation type is forbidden"
        if not policy.executable_through_operation and not policy.dry_run_only:
            return "operation policy is not executable"
        if not await self._readers.audit_writable():
            return "audit is not writable"
        account_facts_issue = _account_facts_unavailable_reason(await self._readers.markets_orders_summary())
        if account_facts_issue is not None and policy.risk_level in {"medium", "high"}:
            if operation.operation_type == "emergency_flatten" and (
                "unavailable" not in account_facts_issue and "blocked" not in account_facts_issue
            ):
                pass
            else:
                return account_facts_issue
        if operation.operation_type == "switch_playbook":
            target_playbook_id = _target_playbook_id(operation.input_params)
            if target_playbook_id not in self._catalog:
                return f"unknown playbook: {target_playbook_id}"
        if operation.operation_type == "write_review_decision":
            if not str(operation.input_params.get("reason_text") or "").strip():
                return "reason_text required"
            if not str(operation.input_params.get("next_recommended_task") or "").strip():
                return "next_recommended_task required"
            try:
                BrcReviewDecision(str(operation.input_params.get("decision") or ""))
            except ValueError:
                return "unknown review decision"
        if operation.operation_type == "run_fixed_testnet_rehearsal":
            if self._readers.fixed_rehearsal_executor is None:
                return "fixed rehearsal Operation executor unavailable"
            current_runtime = await self._readers.runtime_summary()
            current_market = await self._readers.markets_orders_summary()
            blockers = self._fixed_rehearsal_safety_blockers(
                runtime_summary=current_runtime,
                market_summary=current_market,
                campaign_summary=await self._campaign_summary(),
            )
            if blockers:
                return "; ".join(blockers)
        if operation.operation_type == "emergency_stop_runtime":
            if self._readers.runtime_stop_executor is None:
                return "emergency stop runtime executor unavailable"
            current_runtime = await self._readers.runtime_summary()
            if current_runtime.get("live_ready") is True:
                return "live/mainnet runtime stop execution is forbidden"
        if operation.operation_type == "create_gated_trial_from_admission":
            if self._readers.admission_binding_reserver is None:
                return "admission trial binding reserver unavailable"
            readiness = await self._admission_readiness(operation.input_params)
            readiness_blockers = [str(item) for item in readiness.get("blockers") or []]
            if readiness_blockers:
                return "; ".join(readiness_blockers)
        if operation.operation_type == "create_campaign_from_admission_binding":
            if self._readers.admission_campaign_creator is None:
                return "admission campaign shell creator unavailable"
            readiness = await self._admission_campaign_readiness(operation.input_params)
            readiness_blockers = [str(item) for item in readiness.get("blockers") or []]
            if readiness_blockers:
                return "; ".join(readiness_blockers)
        if operation.operation_type == "install_runtime_constraints_from_admission_campaign":
            if self._readers.admission_runtime_constraint_installer is None:
                return "admission runtime constraint installer unavailable"
            readiness = await self._admission_runtime_constraint_readiness(operation.input_params)
            readiness_blockers = [str(item) for item in readiness.get("blockers") or []]
            if readiness_blockers:
                return "; ".join(readiness_blockers)
        if operation.operation_type == "prepare_runtime_carrier_from_admission_campaign":
            if self._readers.admission_runtime_carrier_preparer is None:
                return "admission runtime carrier preparer unavailable"
            readiness = await self._admission_runtime_carrier_readiness(operation.input_params)
            readiness_blockers = [str(item) for item in readiness.get("blockers") or []]
            if readiness_blockers:
                return "; ".join(readiness_blockers)
        if operation.operation_type == "prepare_runtime_start_from_admission_carrier":
            if self._readers.admission_runtime_start_preparer is None:
                return "admission runtime start preparer unavailable"
            readiness = await self._admission_runtime_start_readiness(operation.input_params)
            readiness_blockers = [str(item) for item in readiness.get("blockers") or []]
            if readiness_blockers:
                return "; ".join(readiness_blockers)
        if operation.operation_type == "evaluate_trial_trade_intent":
            if self._readers.trial_trade_intent_evaluator is None:
                return "trial trade intent evaluator unavailable"
            readiness = await self._trial_trade_intent_readiness(operation.input_params)
            if readiness.get("mode_unavailable") is True:
                return str(
                    readiness.get("enforcement", {}).get("not_executed_reason")
                    or "execution mode unavailable"
                )
            readiness_blockers = [str(item) for item in readiness.get("blockers") or []]
            if readiness_blockers:
                return "; ".join(readiness_blockers)
        if operation.operation_type == "prepare_runtime_handoff_from_admission_campaign":
            if self._readers.admission_runtime_handoff_preparer is None:
                return "admission runtime handoff preparer unavailable"
            readiness = await self._admission_runtime_handoff_readiness(operation.input_params)
            readiness_blockers = [str(item) for item in readiness.get("blockers") or []]
            if readiness_blockers:
                return "; ".join(readiness_blockers)
        if operation.operation_type == "start_runtime_from_admission_handoff":
            if self._readers.admission_runtime_start_from_handoff_starter is None:
                return "admission runtime start from handoff starter unavailable"
            readiness = await self._admission_runtime_start_from_handoff_readiness(operation.input_params)
            readiness_blockers = [str(item) for item in readiness.get("blockers") or []]
            if readiness_blockers:
                return "; ".join(readiness_blockers)
        if operation.operation_type == "prepare_strategy_activation_from_admission_runtime":
            if self._readers.admission_strategy_activation_preparer is None:
                return "admission strategy activation preparer unavailable"
            readiness = await self._admission_strategy_activation_readiness(operation.input_params)
            readiness_blockers = [str(item) for item in readiness.get("blockers") or []]
            if readiness_blockers:
                return "; ".join(readiness_blockers)
        if operation.operation_type == "activate_strategy_from_admission_runtime":
            if self._readers.admission_strategy_state_activator is None:
                return "admission strategy state activator unavailable"
            readiness = await self._admission_strategy_state_activation_readiness(operation.input_params)
            readiness_blockers = [str(item) for item in readiness.get("blockers") or []]
            if readiness_blockers:
                return "; ".join(readiness_blockers)
        if operation.operation_type == "prepare_signal_loop_from_admission_strategy":
            if self._readers.admission_signal_loop_preparer is None:
                return "admission signal loop preparer unavailable"
            readiness = await self._admission_signal_loop_readiness(operation.input_params)
            readiness_blockers = [str(item) for item in readiness.get("blockers") or []]
            if readiness_blockers:
                return "; ".join(readiness_blockers)
        if operation.operation_type == "start_signal_loop_from_admission_strategy":
            if self._readers.admission_signal_loop_starter is None:
                return "admission signal loop starter unavailable"
            readiness = await self._admission_signal_loop_start_readiness(operation.input_params)
            readiness_blockers = [str(item) for item in readiness.get("blockers") or []]
            if readiness_blockers:
                return "; ".join(readiness_blockers)
        if operation.operation_type == "evaluate_signal_from_admission_strategy":
            if self._readers.admission_signal_evaluator is None:
                return "admission signal evaluator unavailable"
            readiness = await self._admission_signal_evaluation_readiness(operation.input_params)
            readiness_blockers = [str(item) for item in readiness.get("blockers") or []]
            if readiness_blockers:
                return "; ".join(readiness_blockers)
        if operation.operation_type == "record_trial_trade_intent_from_signal_evaluation":
            if self._readers.signal_trade_intent_recorder is None:
                return "signal trade intent recorder unavailable"
            readiness = await self._signal_trade_intent_readiness(operation.input_params)
            if readiness.get("mode_unavailable") is True:
                return str(
                    readiness.get("enforcement", {}).get("not_executed_reason")
                    or "execution mode unavailable"
                )
            current_runtime = await self._runtime_summary_with_safety_readiness(
                input_params=operation.input_params,
            )
            permission_resolution = self._execution_permission_resolver.resolve(
                requested_permission=ExecutionPermission.INTENT_RECORDING,
                operation_type=operation.operation_type,
                operation_permission=ExecutionPermission.INTENT_RECORDING,
                account_facts=dict(readiness.get("account_facts") or {}),
                constraints_check=dict(readiness.get("constraints_check") or {}),
                campaign_metadata=dict(readiness.get("campaign_metadata") or {}),
                runtime_summary=current_runtime,
            )
            if not permission_allows(
                permission_resolution.final_permission,
                ExecutionPermission.INTENT_RECORDING,
            ):
                return permission_resolution.downgrade_reason or "execution permission blocks intent recording"
            readiness_blockers = [str(item) for item in readiness.get("blockers") or []]
            if readiness_blockers:
                return "; ".join(readiness_blockers)
        current_market = await self._readers.markets_orders_summary()
        if _critical_market_drift(preflight.account_snapshot, current_market):
            return "account/order facts changed since preflight"
        return None

    async def _persist_result(
        self,
        *,
        operation: OperationRecord,
        preflight: PreflightSnapshot,
        status: ExecutionStatus,
        recheck_result: Optional[dict[str, Any]] = None,
        adapter_result: Optional[dict[str, Any]] = None,
        blocked_reason: Optional[str] = None,
        failed_reason: Optional[str] = None,
        result_summary: Optional[dict[str, Any]] = None,
        audit_refs: Optional[list[dict[str, Any]]] = None,
        campaign_refs: Optional[list[dict[str, Any]]] = None,
        review_refs: Optional[list[dict[str, Any]]] = None,
        final_state_snapshot: Optional[dict[str, Any]] = None,
        confirmed_by: Optional[str] = None,
    ) -> ExecutionResult:
        occurred_at = now_ms()
        result = ExecutionResult(
            operation_id=operation.operation_id,
            preflight_id=preflight.preflight_id,
            status=status,
            rechecked=True,
            recheck_result=dict(recheck_result or {}),
            adapter_result=dict(adapter_result or {}),
            blocked_reason=blocked_reason,
            failed_reason=failed_reason,
            result_summary=dict(result_summary or {}),
            audit_refs=list(audit_refs or []),
            campaign_refs=list(campaign_refs or []),
            review_refs=list(review_refs or []),
            final_state_snapshot=dict(final_state_snapshot or {}),
            occurred_at_ms=occurred_at,
        )
        result.audit_refs.append(
            {
                "type": "operation",
                "ref_id": operation.operation_id,
                "preflight_id": preflight.preflight_id,
                "status": status,
            }
        )
        operation.status = status
        operation.result_status = status
        operation.result_summary = result.result_summary or {
            "status": status,
            "blocked_reason": blocked_reason,
            "failed_reason": failed_reason,
        }
        operation.created_audit_refs = list(result.audit_refs)
        if status in {"executed", "failed", "blocked", "noop"}:
            operation.executed_at_ms = occurred_at
        if confirmed_by is not None and operation.confirmed_by is None:
            operation.confirmed_by = confirmed_by
            operation.confirmed_at_ms = occurred_at
        await self._repo.save_execution_result(result)
        await self._repo.save_operation(operation)
        return result

    async def _require_operation(self, operation_id: str) -> OperationRecord:
        operation = await self._repo.get_operation(operation_id)
        if operation is None:
            raise OperationLayerError(f"operation not found: {operation_id}")
        return operation

    async def _require_current_preflight(
        self,
        operation: OperationRecord,
        preflight_id: str,
    ) -> PreflightSnapshot:
        if operation.current_preflight_id != preflight_id:
            raise OperationLayerError("preflight_id does not match operation current_preflight_id")
        preflight = await self._repo.get_preflight(preflight_id)
        if preflight is None:
            raise OperationLayerError(f"preflight not found: {preflight_id}")
        return preflight

    async def _campaign_summary(self) -> dict[str, Any]:
        if self._brc is None:
            return {"available": False, "reason": "BRC campaign service unavailable"}
        campaign = await self._brc.get_current_campaign()
        if campaign is None:
            return {"available": False, "reason": "no active BRC campaign"}
        return {
            "available": True,
            "campaign_id": campaign.campaign_id,
            "status": campaign.status.value,
            "outcome": campaign.outcome.value if campaign.outcome is not None else None,
            "current_playbook_id": campaign.current_playbook_id,
            "realized_pnl": str(campaign.realized_pnl),
            "attempt_count": campaign.attempt_count,
            "max_attempts": campaign.risk_envelope.max_attempts,
            "loss_counter_resets_on_playbook_switch": False,
        }

    async def _runtime_summary_with_safety_readiness(
        self,
        *,
        input_params: dict[str, Any],
        runtime_summary: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        summary = dict(runtime_summary) if runtime_summary is not None else await self._readers.runtime_summary()
        runtime_instance_id = _explicit_runtime_instance_id(input_params)
        if runtime_instance_id is None:
            return summary

        if self._readers.runtime_safety_readiness is None:
            readiness = _blocked_runtime_safety_readiness(
                runtime_instance_id=runtime_instance_id,
                reason="runtime_safety_readiness_reader_unavailable",
            )
        else:
            try:
                readiness = _runtime_safety_readiness_payload(
                    await self._readers.runtime_safety_readiness(dict(input_params))
                )
            except Exception:
                readiness = _blocked_runtime_safety_readiness(
                    runtime_instance_id=runtime_instance_id,
                    reason="runtime_safety_readiness_source_error",
                )

        readiness_runtime_id = _optional_str(readiness.get("runtime_instance_id"))
        if not readiness:
            readiness = _blocked_runtime_safety_readiness(
                runtime_instance_id=runtime_instance_id,
                reason="runtime_safety_readiness_missing",
            )
        elif readiness_runtime_id is None:
            readiness = _blocked_runtime_safety_readiness(
                runtime_instance_id=runtime_instance_id,
                reason="runtime_safety_readiness_runtime_id_missing",
            )
        elif readiness_runtime_id != runtime_instance_id:
            readiness = _blocked_runtime_safety_readiness(
                runtime_instance_id=runtime_instance_id,
                reason="runtime_safety_readiness_runtime_id_mismatch",
            )

        summary["runtime_safety_readiness"] = readiness
        summary["runtime_safety_readiness_runtime_instance_id"] = runtime_instance_id
        return summary

    async def _admission_readiness(self, input_params: dict[str, Any]) -> dict[str, Any]:
        if self._readers.admission_readiness is None:
            return {
                "available": False,
                "ready": False,
                "blockers": ["BRC admission readiness reader unavailable"],
                "warnings": [],
                "admission_summary": {},
                "strategy_family_summary": {},
                "constraints_summary": {},
                "owner_risk_acceptance_summary": {"required": False, "provided": False, "valid": False},
                "next_step": "Wire BRC admission facts before gated-trial preflight can run.",
            }
        return await self._readers.admission_readiness(input_params)

    async def _admission_campaign_readiness(self, input_params: dict[str, Any]) -> dict[str, Any]:
        if self._readers.admission_campaign_readiness is None:
            return {
                "available": False,
                "ready": False,
                "blockers": ["BRC admission campaign readiness reader unavailable"],
                "warnings": [],
                "admission_summary": {},
                "strategy_family_summary": {},
                "constraints_summary": {},
                "owner_risk_acceptance_summary": {"required": False, "provided": False, "valid": False},
                "binding_summary": {},
                "campaign_shell_summary": {},
                "next_step": "Wire BRC admission binding facts before campaign shell preflight can run.",
            }
        return await self._readers.admission_campaign_readiness(input_params)

    async def _admission_runtime_constraint_readiness(
        self,
        input_params: dict[str, Any],
    ) -> dict[str, Any]:
        if self._readers.admission_runtime_constraint_readiness is None:
            return {
                "available": False,
                "ready": False,
                "blockers": ["BRC admission runtime constraint readiness reader unavailable"],
                "warnings": [],
                "admission_summary": {},
                "strategy_family_summary": {},
                "constraints_summary": {},
                "owner_risk_acceptance_summary": {"required": False, "provided": False, "valid": False},
                "binding_summary": {},
                "campaign_shell_summary": {},
                "next_step": "Wire BRC admission campaign facts before runtime constraint install preflight can run.",
            }
        return await self._readers.admission_runtime_constraint_readiness(input_params)

    async def _admission_runtime_carrier_readiness(
        self,
        input_params: dict[str, Any],
    ) -> dict[str, Any]:
        if self._readers.admission_runtime_carrier_readiness is None:
            return {
                "available": False,
                "ready": False,
                "blockers": ["BRC admission runtime carrier readiness reader unavailable"],
                "warnings": [],
                "admission_summary": {},
                "strategy_family_summary": {},
                "constraints_summary": {},
                "owner_risk_acceptance_summary": {"required": False, "provided": False, "valid": False},
                "binding_summary": {},
                "campaign_shell_summary": {},
                "runtime_carrier_summary": {},
                "next_step": "Wire BRC admission campaign facts before runtime carrier readiness preflight can run.",
            }
        return await self._readers.admission_runtime_carrier_readiness(input_params)

    async def _admission_runtime_start_readiness(
        self,
        input_params: dict[str, Any],
    ) -> dict[str, Any]:
        if self._readers.admission_runtime_start_readiness is None:
            return {
                "available": False,
                "ready": False,
                "blockers": ["BRC admission runtime start readiness reader unavailable"],
                "warnings": [],
                "admission_summary": {},
                "strategy_family_summary": {},
                "constraints_summary": {},
                "owner_risk_acceptance_summary": {"required": False, "provided": False, "valid": False},
                "binding_summary": {},
                "campaign_shell_summary": {},
                "runtime_carrier_summary": {},
                "runtime_start_summary": {},
                "next_step": "Wire BRC admission carrier facts before runtime start readiness preflight can run.",
            }
        return await self._readers.admission_runtime_start_readiness(input_params)

    async def _trial_trade_intent_readiness(
        self,
        input_params: dict[str, Any],
    ) -> dict[str, Any]:
        if self._readers.trial_trade_intent_readiness is None:
            return {
                "available": False,
                "ready": False,
                "blockers": ["BRC trial trade intent readiness reader unavailable"],
                "warnings": [],
                "constraints_check": {},
                "enforcement": {
                    "decision": "unavailable",
                    "not_executed_reason": "trial trade intent readiness reader unavailable",
                    "order_would_be_created": False,
                    "execution_intent_would_be_created": False,
                },
                "trade_intent_summary": {},
                "next_step": "Wire BRC trial trade intent enforcement before evaluation can run.",
            }
        return await self._readers.trial_trade_intent_readiness(input_params)

    async def _admission_runtime_handoff_readiness(
        self,
        input_params: dict[str, Any],
    ) -> dict[str, Any]:
        if self._readers.admission_runtime_handoff_readiness is None:
            return {
                "available": False,
                "ready": False,
                "blockers": ["BRC admission runtime handoff readiness reader unavailable"],
                "warnings": [],
                "admission_summary": {},
                "strategy_family_summary": {},
                "constraints_summary": {},
                "binding_summary": {},
                "campaign_shell_summary": {},
                "runtime_handoff_summary": {},
                "next_step": "Wire BRC admission campaign facts before runtime handoff readiness preflight can run.",
            }
        return await self._readers.admission_runtime_handoff_readiness(input_params)

    async def _admission_runtime_start_from_handoff_readiness(
        self,
        input_params: dict[str, Any],
    ) -> dict[str, Any]:
        if self._readers.admission_runtime_start_from_handoff_readiness is None:
            return {
                "available": False,
                "ready": False,
                "blockers": ["BRC admission runtime start-from-handoff readiness reader unavailable"],
                "warnings": [],
                "admission_summary": {},
                "strategy_family_summary": {},
                "constraints_summary": {},
                "binding_summary": {},
                "campaign_shell_summary": {},
                "runtime_start_summary": {},
                "next_step": "Wire BRC admission handoff facts before runtime start preflight can run.",
            }
        return await self._readers.admission_runtime_start_from_handoff_readiness(input_params)

    async def _admission_strategy_activation_readiness(
        self,
        input_params: dict[str, Any],
    ) -> dict[str, Any]:
        if self._readers.admission_strategy_activation_readiness is None:
            return {
                "available": False,
                "ready": False,
                "blockers": ["BRC admission strategy activation readiness reader unavailable"],
                "warnings": [],
                "admission_summary": {},
                "strategy_family_summary": {},
                "constraints_summary": {},
                "binding_summary": {},
                "campaign_shell_summary": {},
                "strategy_activation_summary": {},
                "next_step": "Wire BRC admission runtime facts before strategy activation readiness preflight can run.",
            }
        return await self._readers.admission_strategy_activation_readiness(input_params)

    async def _admission_strategy_state_activation_readiness(
        self,
        input_params: dict[str, Any],
    ) -> dict[str, Any]:
        if self._readers.admission_strategy_state_activation_readiness is None:
            return {
                "available": False,
                "ready": False,
                "blockers": ["BRC admission strategy state activation readiness reader unavailable"],
                "warnings": [],
                "admission_summary": {},
                "strategy_family_summary": {},
                "constraints_summary": {},
                "binding_summary": {},
                "campaign_shell_summary": {},
                "strategy_activation_summary": {},
                "next_step": "Wire BRC admission strategy activation readiness facts before strategy state activation preflight can run.",
            }
        return await self._readers.admission_strategy_state_activation_readiness(input_params)

    async def _admission_signal_loop_readiness(
        self,
        input_params: dict[str, Any],
    ) -> dict[str, Any]:
        if self._readers.admission_signal_loop_readiness is None:
            return {
                "available": False,
                "ready": False,
                "blockers": ["BRC admission signal loop readiness reader unavailable"],
                "warnings": [],
                "admission_summary": {},
                "strategy_family_summary": {},
                "constraints_summary": {},
                "binding_summary": {},
                "campaign_shell_summary": {},
                "signal_loop_summary": {},
                "next_step": "Wire BRC admission strategy facts before signal loop readiness preflight can run.",
            }
        return await self._readers.admission_signal_loop_readiness(input_params)

    async def _admission_signal_loop_start_readiness(
        self,
        input_params: dict[str, Any],
    ) -> dict[str, Any]:
        if self._readers.admission_signal_loop_start_readiness is None:
            return {
                "available": False,
                "ready": False,
                "blockers": ["BRC admission signal loop start readiness reader unavailable"],
                "warnings": [],
                "admission_summary": {},
                "strategy_family_summary": {},
                "constraints_summary": {},
                "binding_summary": {},
                "campaign_shell_summary": {},
                "signal_loop_summary": {},
                "next_step": "Wire BRC admission signal loop readiness facts before signal loop start preflight can run.",
            }
        return await self._readers.admission_signal_loop_start_readiness(input_params)

    async def _admission_signal_evaluation_readiness(
        self,
        input_params: dict[str, Any],
    ) -> dict[str, Any]:
        if self._readers.admission_signal_evaluation_readiness is None:
            return {
                "available": False,
                "ready": False,
                "blockers": ["BRC admission signal evaluation readiness reader unavailable"],
                "warnings": [],
                "admission_summary": {},
                "strategy_family_summary": {},
                "constraints_summary": {},
                "binding_summary": {},
                "campaign_shell_summary": {},
                "signal_evaluation_summary": {},
                "next_step": "Wire BRC admission signal loop started facts before signal evaluation preflight can run.",
            }
        return await self._readers.admission_signal_evaluation_readiness(input_params)

    async def _signal_trade_intent_readiness(
        self,
        input_params: dict[str, Any],
    ) -> dict[str, Any]:
        if self._readers.signal_trade_intent_readiness is None:
            return {
                "available": False,
                "ready": False,
                "blockers": ["BRC signal trade intent readiness reader unavailable"],
                "warnings": [],
                "trade_intent_summary": {},
                "next_step": "Wire BRC signal evaluation facts before trade intent recording preflight can run.",
            }
        return await self._readers.signal_trade_intent_readiness(input_params)

    async def _budget_authorization_summary(self) -> dict[str, Any]:
        if self._readers.budget_authorization_summary is None:
            return {
                "available": False,
                "ready": False,
                "latest_budget_authorization": None,
                "blockers": ["budget authorization reader unavailable"],
                "warnings": [],
                "source": "operation_layer_reader_unavailable",
            }
        return await self._readers.budget_authorization_summary()

    def _effective_policy(self, operation_type: str) -> OperationPolicy:
        policy = self._registry.get_policy(operation_type)
        if operation_type == "revoke_budget":
            if (
                self._readers.budget_authorization_summary is None
                or self._readers.budget_revoke_executor is None
            ):
                return policy
            return policy.model_copy(
                update={
                    "capability_status": "enabled",
                    "current_reason": (
                        "Operation-backed budget revoke is available. It only terminates future "
                        "budgeted autonomy attempts under the selected envelope."
                    ),
                    "backend_executor": "budget_authorization_revoke",
                    "executable_through_operation": True,
                }
            )
        if operation_type == "run_fixed_testnet_rehearsal":
            if self._readers.fixed_rehearsal_executor is None:
                return policy
            return policy.model_copy(
                update={
                    "confirmation_phrase": "CONFIRM_FIXED_TESTNET_REHEARSAL",
                    "capability_status": "enabled",
                    "current_reason": (
                        "Operation-authorized fixed ETH/BTC testnet rehearsal. "
                        "This is not a generic LLM workflow and does not expose arbitrary symbol/side/size execution."
                    ),
                    "backend_executor": "brc_operation_fixed_testnet_rehearsal",
                    "executable_through_operation": True,
                }
            )
        if operation_type == "emergency_stop_runtime":
            if self._readers.runtime_stop_executor is None:
                return policy
            return policy.model_copy(
                update={
                    "confirmation_phrase": "CONFIRM_STOP_RUNTIME",
                    "capability_status": "enabled",
                    "current_reason": (
                        "Operation-backed runtime stop executor is available. "
                        "Stop Runtime does not flatten positions or cancel orders."
                    ),
                    "backend_executor": "brc_operation_runtime_stop",
                    "executable_through_operation": True,
                }
            )
        return policy

    def _playbook_preflight_summary(self, input_params: dict[str, Any]) -> dict[str, Any]:
        target = _target_playbook_id(input_params)
        entry = self._catalog.get(target)
        return {
            "target_playbook_id": target,
            "known": entry is not None,
            "entry": entry.model_dump(mode="json") if entry is not None else None,
            "allowlisted_ids": sorted(self._catalog.keys()),
        }

    def _preflight_decision(
        self,
        *,
        policy: OperationPolicy,
        input_params: dict[str, Any],
        runtime_summary: dict[str, Any],
        campaign_summary: dict[str, Any],
        market_summary: dict[str, Any],
        audit_writable: Optional[bool] = None,
        admission_readiness: Optional[dict[str, Any]] = None,
        admission_campaign_readiness: Optional[dict[str, Any]] = None,
        runtime_constraint_readiness: Optional[dict[str, Any]] = None,
        runtime_carrier_readiness: Optional[dict[str, Any]] = None,
        runtime_start_readiness: Optional[dict[str, Any]] = None,
        trade_intent_readiness: Optional[dict[str, Any]] = None,
        runtime_handoff_readiness: Optional[dict[str, Any]] = None,
        start_runtime_readiness: Optional[dict[str, Any]] = None,
        strategy_activation_readiness: Optional[dict[str, Any]] = None,
        strategy_state_activation_readiness: Optional[dict[str, Any]] = None,
        signal_loop_readiness: Optional[dict[str, Any]] = None,
        signal_loop_start_readiness: Optional[dict[str, Any]] = None,
        signal_evaluation_readiness: Optional[dict[str, Any]] = None,
        signal_trade_intent_readiness: Optional[dict[str, Any]] = None,
        budget_authorization_summary: Optional[dict[str, Any]] = None,
    ) -> tuple[PreflightDecision, list[str], list[str], str, dict[str, Any], dict[str, Any]]:
        blockers: list[str] = []
        warnings: list[str] = []
        before = {
            "campaign_id": campaign_summary.get("campaign_id"),
            "current_playbook_id": campaign_summary.get("current_playbook_id"),
            "realized_pnl": campaign_summary.get("realized_pnl"),
            "attempt_count": campaign_summary.get("attempt_count"),
            "runtime_state": runtime_summary.get("current_runtime_state") or runtime_summary.get("runtime_state"),
        }
        after: dict[str, Any] = {}
        if not policy.executable_through_operation and not _preflight_planning_available(policy):
            if policy.capability_status == "forbidden":
                blockers.append(policy.current_reason)
                return "block", blockers, warnings, policy.current_reason, before, after
            return (
                "unavailable",
                [policy.current_reason],
                warnings,
                policy.current_reason,
                before,
                after,
            )
        account_facts_issue = _account_facts_unavailable_reason(market_summary)
        if account_facts_issue is not None:
            if policy.risk_level in {"medium", "high"}:
                if policy.operation_type == "emergency_flatten":
                    if "unavailable" in account_facts_issue or "blocked" in account_facts_issue:
                        blockers.append(account_facts_issue)
                    else:
                        warnings.append(
                            account_facts_issue
                            + "; actual flatten execution remains unavailable and this is diagnostic dry-run only"
                        )
                else:
                    blockers.append(account_facts_issue)
            elif policy.risk_level == "low":
                warnings.append(account_facts_issue)
        if policy.operation_type == "switch_playbook":
            target = _target_playbook_id(input_params)
            after["current_playbook_id"] = target
            if self._brc is None:
                blockers.append("BRC campaign service unavailable")
            if not campaign_summary.get("available"):
                blockers.append(str(campaign_summary.get("reason") or "no active BRC campaign"))
            if target not in self._catalog:
                blockers.append(f"unknown playbook: {target}")
            if not input_params.get("evidence_refs"):
                warnings.append("evidence_refs were empty; operation will attach operation/preflight refs")
            if int(market_summary.get("active_position_count") or 0) > 0:
                warnings.append("local active positions exist; switch does not place or close orders")
            if int(market_summary.get("open_order_count") or 0) > 0:
                warnings.append("local open orders exist; switch does not place or cancel orders")
        elif policy.operation_type == "write_review_decision":
            if self._brc is None:
                blockers.append("BRC campaign service unavailable")
            campaign_id = str(input_params.get("campaign_id") or campaign_summary.get("campaign_id") or "")
            if not campaign_id:
                blockers.append("campaign_id required when no active BRC campaign exists")
            if not str(input_params.get("reason_text") or "").strip():
                blockers.append("reason_text required")
            if not str(input_params.get("next_recommended_task") or "").strip():
                blockers.append("next_recommended_task required")
            try:
                BrcReviewDecision(str(input_params.get("decision") or ""))
            except ValueError:
                blockers.append("unknown review decision")
            after.update(
                {
                    "campaign_id": campaign_id,
                    "review_decision": input_params.get("decision"),
                    "mutation_executed": False,
                }
            )
        elif policy.operation_type == "start_review":
            after.update({"review_packet": "read", "mutation_executed": False})
            if self._readers.review_packet_reader is None:
                warnings.append("review packet reader is not wired; confirm will record a noop")
        elif policy.operation_type == "run_fixed_testnet_rehearsal":
            blockers.extend(
                self._fixed_rehearsal_safety_blockers(
                    runtime_summary=runtime_summary,
                    market_summary=market_summary,
                    campaign_summary=campaign_summary,
                )
            )
            after.update(
                {
                    "runner": "fixed_eth_btc_testnet_rehearsal",
                    "workflow_carrier": "internal_ref_only",
                    "symbols": ["ETH/USDT:USDT", "BTC/USDT:USDT"],
                    "arbitrary_symbol": False,
                    "arbitrary_workflow": False,
                    "live_ready": False,
                }
            )
        elif policy.operation_type in {"enter_observe", "enter_pause"}:
            target_state = "observe" if policy.operation_type == "enter_observe" else "paused"
            after.update(
                {
                    "runtime_state": target_state,
                    "autonomy_effective_state": target_state,
                    "future_budgeted_actions_allowed": target_state != "paused",
                    "places_orders": False,
                    "closes_positions": False,
                    "cancels_orders": False,
                }
            )
            if self._readers.runtime_transition is None:
                blockers.append("runtime transition adapter unavailable")
        elif policy.operation_type == "revoke_budget":
            budget_summary = dict(budget_authorization_summary or {})
            latest = dict(budget_summary.get("latest_budget_authorization") or {})
            requested_budget_id = _optional_str(input_params.get("budget_authorization_id"))
            budget_authorization_id = requested_budget_id or _optional_str(
                latest.get("budget_authorization_id")
            )
            budget_status = str(latest.get("status") or "not_available")
            before.update(
                {
                    "budget_authorization_id": latest.get("budget_authorization_id"),
                    "budget_authorization_status": budget_status,
                    "budget_effective_state": (
                        "revoked" if budget_status == "revoked"
                        else "available_metadata_only" if latest
                        else "not_available"
                    ),
                    "future_budgeted_actions_allowed": budget_status != "revoked" and bool(latest),
                }
            )
            after.update(
                {
                    "budget_authorization_id": budget_authorization_id,
                    "budget_authorization_status": "revoked",
                    "budget_effective_state": "revoked",
                    "future_budgeted_actions_allowed": False,
                    "places_orders": False,
                    "closes_positions": False,
                    "cancels_orders": False,
                    "withdrawal_executed": False,
                    "transfer_executed": False,
                }
            )
            if self._readers.budget_authorization_summary is None:
                blockers.append("budget authorization reader unavailable")
            if self._readers.budget_revoke_executor is None:
                blockers.append("budget revoke executor unavailable")
            if not budget_authorization_id:
                blockers.append("current budget authorization unavailable")
            if requested_budget_id and latest and requested_budget_id != latest.get("budget_authorization_id"):
                warnings.append(
                    "requested budget_authorization_id differs from latest budget metadata; executor will target the requested id"
                )
            if budget_status == "revoked":
                after["already_revoked"] = True
                warnings.append("budget authorization is already revoked; confirmation will be idempotent")
            warnings.append(
                "revoke_budget blocks future budgeted autonomy actions only; it does not close positions, cancel TP/SL, transfer, or withdraw"
            )
        elif policy.operation_type == "enter_strategy_or_monitor":
            after.update(
                {
                    "carrier": "monitor",
                    "runtime_state_changed": False,
                    "unrestricted_auto_trading": False,
                    "places_orders": False,
                }
            )
        elif policy.operation_type == "emergency_flatten":
            return self._emergency_flatten_preflight_decision(
                policy=policy,
                runtime_summary=runtime_summary,
                market_summary=market_summary,
                before=before,
                blockers=blockers,
                warnings=warnings,
            )
        elif policy.operation_type == "emergency_stop_runtime":
            return self._emergency_stop_runtime_preflight_decision(
                policy=policy,
                runtime_summary=runtime_summary,
                market_summary=market_summary,
                before=before,
                blockers=blockers,
                warnings=warnings,
                audit_writable=audit_writable,
            )
        elif policy.operation_type == "create_gated_trial_from_admission":
            return self._gated_trial_from_admission_preflight_decision(
                policy=policy,
                admission_readiness=admission_readiness or {},
                campaign_summary=campaign_summary,
                before=before,
                blockers=blockers,
                warnings=warnings,
                audit_writable=audit_writable,
            )
        elif policy.operation_type == "create_campaign_from_admission_binding":
            return self._campaign_from_admission_binding_preflight_decision(
                policy=policy,
                admission_campaign_readiness=admission_campaign_readiness or {},
                campaign_summary=campaign_summary,
                before=before,
                blockers=blockers,
                warnings=warnings,
                audit_writable=audit_writable,
            )
        elif policy.operation_type == "install_runtime_constraints_from_admission_campaign":
            return self._runtime_constraints_from_admission_campaign_preflight_decision(
                policy=policy,
                runtime_constraint_readiness=runtime_constraint_readiness or {},
                before=before,
                blockers=blockers,
                warnings=warnings,
                audit_writable=audit_writable,
            )
        elif policy.operation_type == "prepare_runtime_carrier_from_admission_campaign":
            return self._runtime_carrier_from_admission_campaign_preflight_decision(
                policy=policy,
                runtime_carrier_readiness=runtime_carrier_readiness or {},
                before=before,
                blockers=blockers,
                warnings=warnings,
                audit_writable=audit_writable,
            )
        elif policy.operation_type == "prepare_runtime_start_from_admission_carrier":
            return self._runtime_start_from_admission_carrier_preflight_decision(
                policy=policy,
                runtime_start_readiness=runtime_start_readiness or {},
                before=before,
                blockers=blockers,
                warnings=warnings,
                audit_writable=audit_writable,
            )
        elif policy.operation_type == "evaluate_trial_trade_intent":
            return self._trial_trade_intent_preflight_decision(
                policy=policy,
                trade_intent_readiness=trade_intent_readiness or {},
                before=before,
                blockers=blockers,
                warnings=warnings,
                audit_writable=audit_writable,
            )
        elif policy.operation_type == "prepare_runtime_handoff_from_admission_campaign":
            return self._runtime_handoff_from_admission_campaign_preflight_decision(
                policy=policy,
                runtime_handoff_readiness=runtime_handoff_readiness or {},
                before=before,
                blockers=blockers,
                warnings=warnings,
                audit_writable=audit_writable,
            )
        elif policy.operation_type == "start_runtime_from_admission_handoff":
            return self._start_runtime_from_admission_handoff_preflight_decision(
                policy=policy,
                start_runtime_readiness=start_runtime_readiness or {},
                before=before,
                blockers=blockers,
                warnings=warnings,
                audit_writable=audit_writable,
            )
        elif policy.operation_type == "prepare_strategy_activation_from_admission_runtime":
            return self._strategy_activation_from_admission_runtime_preflight_decision(
                policy=policy,
                strategy_activation_readiness=strategy_activation_readiness or {},
                before=before,
                blockers=blockers,
                warnings=warnings,
                audit_writable=audit_writable,
            )
        elif policy.operation_type == "activate_strategy_from_admission_runtime":
            return self._strategy_state_activation_from_admission_runtime_preflight_decision(
                policy=policy,
                strategy_state_activation_readiness=strategy_state_activation_readiness or {},
                before=before,
                blockers=blockers,
                warnings=warnings,
                audit_writable=audit_writable,
            )
        elif policy.operation_type == "prepare_signal_loop_from_admission_strategy":
            return self._signal_loop_from_admission_strategy_preflight_decision(
                policy=policy,
                signal_loop_readiness=signal_loop_readiness or {},
                before=before,
                blockers=blockers,
                warnings=warnings,
                audit_writable=audit_writable,
            )
        elif policy.operation_type == "start_signal_loop_from_admission_strategy":
            return self._signal_loop_start_from_admission_strategy_preflight_decision(
                policy=policy,
                signal_loop_start_readiness=signal_loop_start_readiness or {},
                before=before,
                blockers=blockers,
                warnings=warnings,
                audit_writable=audit_writable,
            )
        elif policy.operation_type == "evaluate_signal_from_admission_strategy":
            return self._signal_evaluation_from_admission_strategy_preflight_decision(
                policy=policy,
                signal_evaluation_readiness=signal_evaluation_readiness or {},
                before=before,
                blockers=blockers,
                warnings=warnings,
                audit_writable=audit_writable,
            )
        elif policy.operation_type == "record_trial_trade_intent_from_signal_evaluation":
            return self._signal_trade_intent_from_evaluation_preflight_decision(
                policy=policy,
                signal_trade_intent_readiness=signal_trade_intent_readiness or {},
                before=before,
                blockers=blockers,
                warnings=warnings,
                audit_writable=audit_writable,
            )
        if blockers:
            return "block", blockers, warnings, "; ".join(blockers), before, after
        summary = _operation_summary(policy.operation_type, after)
        return ("warn" if warnings else "allow"), blockers, warnings, summary, before, after

    def _gated_trial_from_admission_preflight_decision(
        self,
        *,
        policy: OperationPolicy,
        admission_readiness: dict[str, Any],
        campaign_summary: dict[str, Any],
        before: dict[str, Any],
        blockers: list[str],
        warnings: list[str],
        audit_writable: Optional[bool],
    ) -> tuple[PreflightDecision, list[str], list[str], str, dict[str, Any], dict[str, Any]]:
        if audit_writable is False:
            blockers.append("audit is not writable")
        if not admission_readiness.get("available", False):
            blockers.append("admission readiness unavailable")
        blockers.extend(str(item) for item in admission_readiness.get("blockers") or [])
        warnings.extend(str(item) for item in admission_readiness.get("warnings") or [])
        if campaign_summary.get("available"):
            blockers.append("active BRC campaign already exists")
        after = {
            "phase": "BRC-R5-002 Phase 4",
            "preflight_only": False,
            "binding_reservation_only": True,
            "confirm_disabled": False,
            "actual_execution_available": True,
            "actual_runtime_execution_available": False,
            "binding_reservation_available": not blockers,
            "runtime_creation_implemented": False,
            "campaign_creation_implemented": False,
            "runtime_constraints_installation_implemented": False,
            "planned_result_status": "binding_reserved",
            "admission_summary": dict(admission_readiness.get("admission_summary") or {}),
            "strategy_family_summary": dict(admission_readiness.get("strategy_family_summary") or {}),
            "trial_env": admission_readiness.get("trial_env"),
            "trial_stage": admission_readiness.get("trial_stage"),
            "execution_mode": admission_readiness.get("execution_mode"),
            "constraints_summary": dict(admission_readiness.get("constraints_summary") or {}),
            "owner_risk_acceptance_summary": dict(
                admission_readiness.get("owner_risk_acceptance_summary") or {}
            ),
            "binding_summary": dict(admission_readiness.get("binding_summary") or {}),
            "next_step": admission_readiness.get("next_step")
            or "Confirm can reserve an admission-trial binding only; runtime creation remains future work.",
            "confirmation_requirement": {
                "owner_confirmation_required_for_runtime_creation": False,
                "owner_confirmation_required_for_binding_reservation": not blockers,
                "confirm_disabled": False,
                "reason": (
                    "Confirm reserves an admission-trial binding only. It does not create a campaign, "
                    "runtime carrier, install constraints, place orders, enable live, withdraw, or transfer."
                ),
            },
        }
        if blockers:
            return "block", list(dict.fromkeys(blockers)), list(dict.fromkeys(warnings)), "; ".join(dict.fromkeys(blockers)), before, after
        summary = _operation_summary(policy.operation_type, after)
        return "warn" if warnings else "allow", blockers, list(dict.fromkeys(warnings)), summary, before, after

    def _campaign_from_admission_binding_preflight_decision(
        self,
        *,
        policy: OperationPolicy,
        admission_campaign_readiness: dict[str, Any],
        campaign_summary: dict[str, Any],
        before: dict[str, Any],
        blockers: list[str],
        warnings: list[str],
        audit_writable: Optional[bool],
    ) -> tuple[PreflightDecision, list[str], list[str], str, dict[str, Any], dict[str, Any]]:
        if audit_writable is False:
            blockers.append("audit is not writable")
        if not admission_campaign_readiness.get("available", False):
            blockers.append("admission campaign readiness unavailable")
        blockers.extend(str(item) for item in admission_campaign_readiness.get("blockers") or [])
        warnings.extend(str(item) for item in admission_campaign_readiness.get("warnings") or [])
        if campaign_summary.get("available"):
            blockers.append("active BRC campaign already exists")
        after = {
            "phase": "BRC-R5-002 Phase 5",
            "campaign_shell_creation_only": True,
            "binding_reservation_required": True,
            "actual_execution_available": True,
            "actual_runtime_execution_available": False,
            "campaign_shell_creation_available": not blockers,
            "runtime_creation_implemented": False,
            "runtime_carrier_switch_implemented": False,
            "runtime_constraints_installation_implemented": False,
            "strategy_execution_implemented": False,
            "planned_result_status": "campaign_created",
            "admission_summary": dict(admission_campaign_readiness.get("admission_summary") or {}),
            "strategy_family_summary": dict(admission_campaign_readiness.get("strategy_family_summary") or {}),
            "trial_env": admission_campaign_readiness.get("trial_env"),
            "trial_stage": admission_campaign_readiness.get("trial_stage"),
            "execution_mode": admission_campaign_readiness.get("execution_mode"),
            "constraints_summary": dict(admission_campaign_readiness.get("constraints_summary") or {}),
            "owner_risk_acceptance_summary": dict(
                admission_campaign_readiness.get("owner_risk_acceptance_summary") or {}
            ),
            "binding_summary": dict(admission_campaign_readiness.get("binding_summary") or {}),
            "campaign_shell_summary": dict(
                admission_campaign_readiness.get("campaign_shell_summary") or {}
            ),
            "next_step": admission_campaign_readiness.get("next_step")
            or "Confirm can create a campaign shell only; runtime installation remains future work.",
            "confirmation_requirement": {
                "owner_confirmation_required_for_campaign_shell": not blockers,
                "owner_confirmation_required_for_runtime_creation": False,
                "confirm_disabled": False,
                "reason": (
                    "Confirm creates a campaign carrier shell only. Runtime will not start; "
                    "constraints will not be installed; strategy will not execute; no orders will be placed."
                ),
            },
        }
        if blockers:
            unique_blockers = list(dict.fromkeys(blockers))
            return "block", unique_blockers, list(dict.fromkeys(warnings)), "; ".join(unique_blockers), before, after
        summary = _operation_summary(policy.operation_type, after)
        return "warn" if warnings else "allow", blockers, list(dict.fromkeys(warnings)), summary, before, after

    def _runtime_constraints_from_admission_campaign_preflight_decision(
        self,
        *,
        policy: OperationPolicy,
        runtime_constraint_readiness: dict[str, Any],
        before: dict[str, Any],
        blockers: list[str],
        warnings: list[str],
        audit_writable: Optional[bool],
    ) -> tuple[PreflightDecision, list[str], list[str], str, dict[str, Any], dict[str, Any]]:
        if audit_writable is False:
            blockers.append("audit is not writable")
        if not runtime_constraint_readiness.get("available", False):
            blockers.append("admission runtime constraint readiness unavailable")
        blockers.extend(str(item) for item in runtime_constraint_readiness.get("blockers") or [])
        warnings.extend(str(item) for item in runtime_constraint_readiness.get("warnings") or [])
        idempotent_install = bool(runtime_constraint_readiness.get("idempotent_install", False))
        after = {
            "phase": "BRC-R5-002 Phase 6",
            "runtime_constraint_installation_only": True,
            "admission_campaign_required": True,
            "actual_execution_available": True,
            "actual_runtime_execution_available": False,
            "runtime_constraint_installation_available": not blockers,
            "idempotent_install": idempotent_install,
            "runtime_creation_implemented": False,
            "runtime_carrier_switch_implemented": False,
            "strategy_execution_implemented": False,
            "planned_result_status": "runtime_constraints_installed",
            "admission_summary": dict(runtime_constraint_readiness.get("admission_summary") or {}),
            "strategy_family_summary": dict(
                runtime_constraint_readiness.get("strategy_family_summary") or {}
            ),
            "trial_env": runtime_constraint_readiness.get("trial_env"),
            "trial_stage": runtime_constraint_readiness.get("trial_stage"),
            "execution_mode": runtime_constraint_readiness.get("execution_mode"),
            "constraints_summary": dict(runtime_constraint_readiness.get("constraints_summary") or {}),
            "owner_risk_acceptance_summary": dict(
                runtime_constraint_readiness.get("owner_risk_acceptance_summary") or {}
            ),
            "binding_summary": dict(runtime_constraint_readiness.get("binding_summary") or {}),
            "campaign_shell_summary": dict(
                runtime_constraint_readiness.get("campaign_shell_summary") or {}
            ),
            "safety_statement": {
                "constraints_would_be_installed": not blockers and not idempotent_install,
                "runtime_will_start": False,
                "strategy_will_activate": False,
                "orders_will_be_placed": False,
                "trial_remains_inactive_after_install": True,
                "auto_within_budget_enabled": False,
                "owner_confirm_each_entry_enabled": False,
            },
            "next_step": runtime_constraint_readiness.get("next_step")
            or "Confirm can install constraints metadata only; runtime start remains future work.",
            "confirmation_requirement": {
                "owner_confirmation_required_for_constraints_metadata_install": not blockers,
                "owner_confirmation_required_for_runtime_start": False,
                "confirm_disabled": False,
                "reason": (
                    "Confirm installs constraints metadata only. Runtime will not start; strategy will not "
                    "activate; trial remains inactive; no orders will be placed."
                ),
            },
        }
        if blockers:
            unique_blockers = list(dict.fromkeys(blockers))
            return "block", unique_blockers, list(dict.fromkeys(warnings)), "; ".join(unique_blockers), before, after
        summary = _operation_summary(policy.operation_type, after)
        return "warn" if warnings else "allow", blockers, list(dict.fromkeys(warnings)), summary, before, after

    def _runtime_carrier_from_admission_campaign_preflight_decision(
        self,
        *,
        policy: OperationPolicy,
        runtime_carrier_readiness: dict[str, Any],
        before: dict[str, Any],
        blockers: list[str],
        warnings: list[str],
        audit_writable: Optional[bool],
    ) -> tuple[PreflightDecision, list[str], list[str], str, dict[str, Any], dict[str, Any]]:
        if audit_writable is False:
            blockers.append("audit is not writable")
        if not runtime_carrier_readiness.get("available", False):
            blockers.append("admission runtime carrier readiness unavailable")
        blockers.extend(str(item) for item in runtime_carrier_readiness.get("blockers") or [])
        warnings.extend(str(item) for item in runtime_carrier_readiness.get("warnings") or [])
        idempotent_prepare = bool(runtime_carrier_readiness.get("idempotent_prepare", False))
        after = {
            "phase": "BRC-R5-002 Phase 7",
            "runtime_carrier_readiness_only": True,
            "admission_campaign_required": True,
            "actual_execution_available": True,
            "actual_runtime_execution_available": False,
            "runtime_carrier_readiness_available": not blockers,
            "idempotent_prepare": idempotent_prepare,
            "runtime_start_implemented": False,
            "runtime_carrier_switch_implemented": False,
            "strategy_execution_implemented": False,
            "auto_execution_implemented": False,
            "planned_result_status": "carrier_ready",
            "admission_summary": dict(runtime_carrier_readiness.get("admission_summary") or {}),
            "strategy_family_summary": dict(
                runtime_carrier_readiness.get("strategy_family_summary") or {}
            ),
            "trial_env": runtime_carrier_readiness.get("trial_env"),
            "trial_stage": runtime_carrier_readiness.get("trial_stage"),
            "execution_mode": runtime_carrier_readiness.get("execution_mode"),
            "constraints_summary": dict(runtime_carrier_readiness.get("constraints_summary") or {}),
            "owner_risk_acceptance_summary": dict(
                runtime_carrier_readiness.get("owner_risk_acceptance_summary") or {}
            ),
            "binding_summary": dict(runtime_carrier_readiness.get("binding_summary") or {}),
            "campaign_shell_summary": dict(
                runtime_carrier_readiness.get("campaign_shell_summary") or {}
            ),
            "runtime_carrier_summary": dict(
                runtime_carrier_readiness.get("runtime_carrier_summary") or {}
            ),
            "safety_statement": {
                "carrier_readiness_would_be_prepared": not blockers and not idempotent_prepare,
                "runtime_will_start": False,
                "strategy_will_activate": False,
                "auto_execution_will_be_enabled": False,
                "orders_will_be_placed": False,
                "trial_remains_inactive_after_readiness_preparation": True,
            },
            "next_step": runtime_carrier_readiness.get("next_step")
            or "Confirm can prepare carrier readiness metadata only; runtime start remains future work.",
            "confirmation_requirement": {
                "owner_confirmation_required_for_carrier_readiness_metadata": not blockers,
                "owner_confirmation_required_for_runtime_start": False,
                "confirm_disabled": False,
                "reason": (
                    "Confirm prepares runtime carrier readiness metadata only. Runtime will not start; "
                    "strategy will not activate; auto execution will not be enabled; trial remains inactive; "
                    "no orders will be placed."
                ),
            },
        }
        if blockers:
            unique_blockers = list(dict.fromkeys(blockers))
            return "block", unique_blockers, list(dict.fromkeys(warnings)), "; ".join(unique_blockers), before, after
        summary = _operation_summary(policy.operation_type, after)
        return "warn" if warnings else "allow", blockers, list(dict.fromkeys(warnings)), summary, before, after

    def _runtime_start_from_admission_carrier_preflight_decision(
        self,
        *,
        policy: OperationPolicy,
        runtime_start_readiness: dict[str, Any],
        before: dict[str, Any],
        blockers: list[str],
        warnings: list[str],
        audit_writable: Optional[bool],
    ) -> tuple[PreflightDecision, list[str], list[str], str, dict[str, Any], dict[str, Any]]:
        if audit_writable is False:
            blockers.append("audit is not writable")
        if not runtime_start_readiness.get("available", False):
            blockers.append("admission runtime start readiness unavailable")
        blockers.extend(str(item) for item in runtime_start_readiness.get("blockers") or [])
        warnings.extend(str(item) for item in runtime_start_readiness.get("warnings") or [])
        idempotent_prepare = bool(runtime_start_readiness.get("idempotent_prepare", False))
        after = {
            "phase": "BRC-R5-002 Phase 8",
            "runtime_start_readiness_only": True,
            "admission_carrier_required": True,
            "actual_execution_available": True,
            "actual_runtime_execution_available": False,
            "runtime_start_readiness_available": not blockers,
            "idempotent_prepare": idempotent_prepare,
            "runtime_start_implemented": False,
            "runtime_carrier_switch_implemented": False,
            "strategy_execution_implemented": False,
            "auto_execution_implemented": False,
            "planned_result_status": "runtime_start_ready",
            "admission_summary": dict(runtime_start_readiness.get("admission_summary") or {}),
            "strategy_family_summary": dict(
                runtime_start_readiness.get("strategy_family_summary") or {}
            ),
            "trial_env": runtime_start_readiness.get("trial_env"),
            "trial_stage": runtime_start_readiness.get("trial_stage"),
            "execution_mode": runtime_start_readiness.get("execution_mode"),
            "constraints_summary": dict(runtime_start_readiness.get("constraints_summary") or {}),
            "owner_risk_acceptance_summary": dict(
                runtime_start_readiness.get("owner_risk_acceptance_summary") or {}
            ),
            "binding_summary": dict(runtime_start_readiness.get("binding_summary") or {}),
            "campaign_shell_summary": dict(
                runtime_start_readiness.get("campaign_shell_summary") or {}
            ),
            "runtime_carrier_summary": dict(
                runtime_start_readiness.get("runtime_carrier_summary") or {}
            ),
            "runtime_start_summary": dict(
                runtime_start_readiness.get("runtime_start_summary") or {}
            ),
            "safety_statement": {
                "runtime_start_readiness_would_be_prepared": not blockers and not idempotent_prepare,
                "runtime_will_start": False,
                "strategy_will_activate": False,
                "auto_execution_will_be_enabled": False,
                "orders_will_be_placed": False,
                "next_phase_must_handle_execution_mode_enforcement": True,
            },
            "next_step": runtime_start_readiness.get("next_step")
            or "Confirm can prepare runtime start readiness metadata only; runtime start remains future work.",
            "confirmation_requirement": {
                "owner_confirmation_required_for_runtime_start_readiness_metadata": not blockers,
                "owner_confirmation_required_for_runtime_start": False,
                "confirm_disabled": False,
                "reason": (
                    "Confirm prepares runtime start readiness metadata only. Runtime will not start; "
                    "strategy will not activate; auto execution will not be enabled; no orders will be placed. "
                    "The next phase must handle execution mode enforcement."
                ),
            },
        }
        if blockers:
            unique_blockers = list(dict.fromkeys(blockers))
            return "block", unique_blockers, list(dict.fromkeys(warnings)), "; ".join(unique_blockers), before, after
        summary = _operation_summary(policy.operation_type, after)
        return "warn" if warnings else "allow", blockers, list(dict.fromkeys(warnings)), summary, before, after

    def _trial_trade_intent_preflight_decision(
        self,
        *,
        policy: OperationPolicy,
        trade_intent_readiness: dict[str, Any],
        before: dict[str, Any],
        blockers: list[str],
        warnings: list[str],
        audit_writable: Optional[bool],
    ) -> tuple[PreflightDecision, list[str], list[str], str, dict[str, Any], dict[str, Any]]:
        if audit_writable is False:
            blockers.append("audit is not writable")
        if not trade_intent_readiness.get("available", False):
            blockers.append("trial trade intent enforcement unavailable")
        blockers.extend(str(item) for item in trade_intent_readiness.get("blockers") or [])
        warnings.extend(str(item) for item in trade_intent_readiness.get("warnings") or [])
        enforcement = dict(trade_intent_readiness.get("enforcement") or {})
        mode_unavailable = bool(trade_intent_readiness.get("mode_unavailable", False))
        after = {
            "phase": "BRC-R5-002 Phase 9",
            "execution_mode_enforcement_contract_only": True,
            "actual_runtime_execution_available": False,
            "actual_order_execution_available": False,
            "trial_trade_intent_ledger_only": True,
            "trial_trade_intent_is_order": False,
            "execution_intent_created": False,
            "order_created": False,
            "runtime_started": False,
            "strategy_active": False,
            "orders_placed": False,
            "live_ready": False,
            "campaign_id": trade_intent_readiness.get("campaign_id"),
            "binding_id": trade_intent_readiness.get("binding_id"),
            "execution_mode": trade_intent_readiness.get("execution_mode"),
            "intended_action": trade_intent_readiness.get("intended_action"),
            "symbol": trade_intent_readiness.get("symbol"),
            "side": trade_intent_readiness.get("side"),
            "constraints_check": dict(trade_intent_readiness.get("constraints_check") or {}),
            "enforcement": enforcement,
            "trade_intent_summary": dict(
                trade_intent_readiness.get("trade_intent_summary") or {}
            ),
            "safety_statement": {
                "runtime_will_start": False,
                "strategy_will_activate": False,
                "auto_execution_will_be_enabled": False,
                "orders_will_be_placed": False,
                "trial_trade_intent_is_executable_order": False,
                "auto_within_budget_check_enables_trading": False,
            },
            "next_step": trade_intent_readiness.get("next_step")
            or "Confirm can record non-executable intent evidence only.",
            "confirmation_requirement": {
                "owner_confirmation_required_for_non_executable_evidence": not blockers and not mode_unavailable,
                "owner_confirmation_required_for_order_execution": False,
                "confirm_disabled": mode_unavailable,
                "reason": (
                    "Confirm evaluates execution-mode contract only. It does not start runtime, activate "
                    "strategy, create an order, create an execution intent, enable auto execution, or trade."
                ),
            },
        }
        unique_blockers = list(dict.fromkeys(blockers))
        unique_warnings = list(dict.fromkeys(warnings))
        if mode_unavailable:
            reason = str(enforcement.get("not_executed_reason") or "execution mode unavailable")
            if reason not in unique_blockers:
                unique_blockers.append(reason)
            return "unavailable", unique_blockers, unique_warnings, reason, before, after
        if unique_blockers:
            return "block", unique_blockers, unique_warnings, "; ".join(unique_blockers), before, after
        summary = _operation_summary(policy.operation_type, after)
        return "warn" if unique_warnings else "allow", unique_blockers, unique_warnings, summary, before, after

    def _signal_trade_intent_from_evaluation_preflight_decision(
        self,
        *,
        policy: OperationPolicy,
        signal_trade_intent_readiness: dict[str, Any],
        before: dict[str, Any],
        blockers: list[str],
        warnings: list[str],
        audit_writable: Optional[bool],
    ) -> tuple[PreflightDecision, list[str], list[str], str, dict[str, Any], dict[str, Any]]:
        if audit_writable is False:
            blockers.append("audit is not writable")
        if not signal_trade_intent_readiness.get("available", False):
            blockers.append("signal trade intent recording unavailable")
        blockers.extend(str(item) for item in signal_trade_intent_readiness.get("blockers") or [])
        warnings.extend(str(item) for item in signal_trade_intent_readiness.get("warnings") or [])
        enforcement = dict(signal_trade_intent_readiness.get("enforcement") or {})
        resolution = dict(signal_trade_intent_readiness.get("execution_permission_resolution") or {})
        mode_unavailable = bool(signal_trade_intent_readiness.get("mode_unavailable", False))
        idempotent_intent = bool(signal_trade_intent_readiness.get("idempotent_intent", False))
        after = {
            "phase": "BRC-R5-002 Phase 18",
            "trial_trade_intent_recording_only": True,
            "actual_runtime_execution_available": False,
            "actual_order_execution_available": False,
            "execution_intent_created": False,
            "order_created": False,
            "orders_placed": False,
            "trial_started": False,
            "auto_execution_enabled": False,
            "auto_within_budget_enabled": False,
            "live_ready": False,
            "campaign_id": signal_trade_intent_readiness.get("campaign_id"),
            "binding_id": signal_trade_intent_readiness.get("binding_id"),
            "execution_mode": signal_trade_intent_readiness.get("execution_mode"),
            "intended_action": signal_trade_intent_readiness.get("intended_action"),
            "symbol": signal_trade_intent_readiness.get("symbol"),
            "side": signal_trade_intent_readiness.get("side"),
            "constraints_check": dict(signal_trade_intent_readiness.get("constraints_check") or {}),
            "execution_permission_resolution": resolution,
            "enforcement": enforcement,
            "idempotent_intent": idempotent_intent,
            "trade_intent_summary": dict(
                signal_trade_intent_readiness.get("trade_intent_summary") or {}
            ),
            "safety_statement": {
                "trial_trade_intent_is_evidence_only": True,
                "execution_intent_will_be_created": False,
                "order_will_be_created": False,
                "auto_execution_will_be_enabled": False,
                "owner_confirmation_can_raise_permission": False,
            },
            "next_step": signal_trade_intent_readiness.get("next_step")
            or "Confirm can record non-executable trial trade intent evidence only.",
            "confirmation_requirement": {
                "owner_confirmation_required_for_non_executable_evidence": not blockers and not mode_unavailable,
                "owner_confirmation_required_for_order_execution": False,
                "confirm_disabled": mode_unavailable,
                "reason": (
                    "Confirm records trial trade intent evidence only. It does not create an execution intent, "
                    "create an order, enable auto execution, enable live, or trade."
                ),
            },
        }
        unique_blockers = list(dict.fromkeys(blockers))
        unique_warnings = list(dict.fromkeys(warnings))
        if mode_unavailable:
            reason = str(enforcement.get("not_executed_reason") or "execution mode unavailable")
            if reason not in unique_blockers:
                unique_blockers.append(reason)
            return "unavailable", unique_blockers, unique_warnings, reason, before, after
        if unique_blockers:
            return "block", unique_blockers, unique_warnings, "; ".join(unique_blockers), before, after
        summary = _operation_summary(policy.operation_type, after)
        return "warn" if unique_warnings else "allow", unique_blockers, unique_warnings, summary, before, after

    def _runtime_handoff_from_admission_campaign_preflight_decision(
        self,
        *,
        policy: OperationPolicy,
        runtime_handoff_readiness: dict[str, Any],
        before: dict[str, Any],
        blockers: list[str],
        warnings: list[str],
        audit_writable: Optional[bool],
    ) -> tuple[PreflightDecision, list[str], list[str], str, dict[str, Any], dict[str, Any]]:
        if audit_writable is False:
            blockers.append("audit is not writable")
        if not runtime_handoff_readiness.get("available", False):
            blockers.append("admission runtime handoff readiness unavailable")
        blockers.extend(str(item) for item in runtime_handoff_readiness.get("blockers") or [])
        warnings.extend(str(item) for item in runtime_handoff_readiness.get("warnings") or [])
        idempotent_prepare = bool(runtime_handoff_readiness.get("idempotent_prepare", False))
        after = {
            "phase": "BRC-R5-002 Phase 10",
            "runtime_handoff_readiness_only": True,
            "runtime_start_ready_required": True,
            "actual_execution_available": True,
            "actual_runtime_execution_available": False,
            "actual_order_execution_available": False,
            "runtime_handoff_readiness_available": not blockers,
            "idempotent_prepare": idempotent_prepare,
            "runtime_start_implemented": False,
            "runtime_carrier_switch_implemented": False,
            "strategy_execution_implemented": False,
            "auto_execution_implemented": False,
            "planned_result_status": "runtime_handoff_ready",
            "admission_summary": dict(runtime_handoff_readiness.get("admission_summary") or {}),
            "strategy_family_summary": dict(
                runtime_handoff_readiness.get("strategy_family_summary") or {}
            ),
            "trial_env": runtime_handoff_readiness.get("trial_env"),
            "trial_stage": runtime_handoff_readiness.get("trial_stage"),
            "execution_mode": runtime_handoff_readiness.get("execution_mode"),
            "constraints_summary": dict(runtime_handoff_readiness.get("constraints_summary") or {}),
            "binding_summary": dict(runtime_handoff_readiness.get("binding_summary") or {}),
            "campaign_shell_summary": dict(
                runtime_handoff_readiness.get("campaign_shell_summary") or {}
            ),
            "runtime_handoff_summary": dict(
                runtime_handoff_readiness.get("runtime_handoff_summary") or {}
            ),
            "safety_statement": {
                "runtime_handoff_readiness_would_be_prepared": not blockers and not idempotent_prepare,
                "runtime_will_start": False,
                "runtime_started_will_be_set_true": False,
                "strategy_will_activate": False,
                "strategy_active_will_be_set_true": False,
                "auto_execution_will_be_enabled": False,
                "orders_will_be_placed": False,
                "trial_started_will_be_set_true": False,
                "next_phase_must_explicitly_start_runtime": True,
            },
            "next_step": runtime_handoff_readiness.get("next_step")
            or "Confirm can prepare runtime handoff readiness metadata only; runtime start remains future work.",
            "confirmation_requirement": {
                "owner_confirmation_required_for_runtime_handoff_readiness_metadata": not blockers,
                "owner_confirmation_required_for_runtime_start": False,
                "confirm_disabled": False,
                "reason": (
                    "Confirm prepares runtime handoff readiness metadata only. Runtime will not start; "
                    "runtime_started remains false; strategy will not activate; auto execution will not be enabled; "
                    "no orders will be placed. The next phase must explicitly start runtime through a separate Operation."
                ),
            },
        }
        if blockers:
            unique_blockers = list(dict.fromkeys(blockers))
            return "block", unique_blockers, list(dict.fromkeys(warnings)), "; ".join(unique_blockers), before, after
        summary = _operation_summary(policy.operation_type, after)
        return "warn" if warnings else "allow", blockers, list(dict.fromkeys(warnings)), summary, before, after

    def _start_runtime_from_admission_handoff_preflight_decision(
        self,
        *,
        policy: OperationPolicy,
        start_runtime_readiness: dict[str, Any],
        before: dict[str, Any],
        blockers: list[str],
        warnings: list[str],
        audit_writable: Optional[bool],
    ) -> tuple[PreflightDecision, list[str], list[str], str, dict[str, Any], dict[str, Any]]:
        if audit_writable is False:
            blockers.append("audit is not writable")
        if not start_runtime_readiness.get("available", False):
            blockers.append("admission runtime start handoff readiness unavailable")
        blockers.extend(str(item) for item in start_runtime_readiness.get("blockers") or [])
        warnings.extend(str(item) for item in start_runtime_readiness.get("warnings") or [])
        start_conditions_summary = dict(start_runtime_readiness.get("runtime_start_summary") or {})
        idempotent_start = bool(start_runtime_readiness.get("idempotent_start", False))
        start_would_be_possible = not blockers and bool(start_runtime_readiness.get("ready", False))
        after = {
            "phase": "BRC-R5-002 Phase 12",
            "runtime_start_preflight_only": False,
            "confirm_disabled": False,
            "actual_execution_available": True,
            "actual_runtime_execution_available": True,
            "actual_order_execution_available": False,
            "runtime_state_start_only": True,
            "runtime_start_confirm_implemented": True,
            "idempotent_start": idempotent_start,
            "runtime_start_would_be_possible": start_would_be_possible,
            "planned_result_status": "runtime_started_strategy_inactive",
            "admission_summary": dict(start_runtime_readiness.get("admission_summary") or {}),
            "strategy_family_summary": dict(
                start_runtime_readiness.get("strategy_family_summary") or {}
            ),
            "trial_env": start_runtime_readiness.get("trial_env"),
            "trial_stage": start_runtime_readiness.get("trial_stage"),
            "execution_mode": start_runtime_readiness.get("execution_mode"),
            "constraints_summary": dict(start_runtime_readiness.get("constraints_summary") or {}),
            "binding_summary": dict(start_runtime_readiness.get("binding_summary") or {}),
            "campaign_shell_summary": dict(
                start_runtime_readiness.get("campaign_shell_summary") or {}
            ),
            "runtime_start_summary": start_conditions_summary,
            "safety_statement": {
                "runtime_start_conditions_met": start_would_be_possible,
                "runtime_state_can_be_started": start_would_be_possible and not idempotent_start,
                "runtime_started_will_be_set_true": start_would_be_possible and not idempotent_start,
                "strategy_will_activate": False,
                "strategy_active_will_be_set_true": False,
                "trial_started_will_be_set_true": False,
                "auto_execution_will_be_enabled": False,
                "orders_will_be_placed": False,
                "execution_intent_will_be_created": False,
                "next_required_implementation": "strategy activation / execution mode runtime enforcement Operation",
            },
            "next_step": start_runtime_readiness.get("next_step")
            or "Confirm can start runtime state only; a separate future Operation must activate strategy.",
            "confirmation_requirement": {
                "owner_confirmation_required_for_runtime_start_state": not idempotent_start and start_would_be_possible,
                "confirm_disabled": False,
                "reason": (
                    "Confirm starts runtime state only. It cannot activate strategy, start trial, "
                    "enable auto execution, create orders, or create execution intents."
                ),
            },
        }
        unique_blockers = list(dict.fromkeys(blockers))
        unique_warnings = list(dict.fromkeys(warnings))
        if unique_blockers:
            return "block", unique_blockers, unique_warnings, "; ".join(unique_blockers), before, after
        summary = _operation_summary(policy.operation_type, after)
        return "warn" if unique_warnings else "allow", unique_blockers, unique_warnings, summary, before, after

    def _strategy_activation_from_admission_runtime_preflight_decision(
        self,
        *,
        policy: OperationPolicy,
        strategy_activation_readiness: dict[str, Any],
        before: dict[str, Any],
        blockers: list[str],
        warnings: list[str],
        audit_writable: Optional[bool],
    ) -> tuple[PreflightDecision, list[str], list[str], str, dict[str, Any], dict[str, Any]]:
        if audit_writable is False:
            blockers.append("audit is not writable")
        if not strategy_activation_readiness.get("available", False):
            blockers.append("admission strategy activation readiness unavailable")
        blockers.extend(str(item) for item in strategy_activation_readiness.get("blockers") or [])
        warnings.extend(str(item) for item in strategy_activation_readiness.get("warnings") or [])
        idempotent_prepare = bool(strategy_activation_readiness.get("idempotent_prepare", False))
        after = {
            "phase": "BRC-R5-002 Phase 13",
            "strategy_activation_readiness_only": True,
            "confirm_disabled": False,
            "actual_strategy_activation_available": False,
            "actual_signal_loop_available": False,
            "actual_order_execution_available": False,
            "planned_result_status": "strategy_activation_ready",
            "idempotent_prepare": idempotent_prepare,
            "admission_summary": dict(strategy_activation_readiness.get("admission_summary") or {}),
            "strategy_family_summary": dict(
                strategy_activation_readiness.get("strategy_family_summary") or {}
            ),
            "trial_env": strategy_activation_readiness.get("trial_env"),
            "trial_stage": strategy_activation_readiness.get("trial_stage"),
            "execution_mode": strategy_activation_readiness.get("execution_mode"),
            "constraints_summary": dict(strategy_activation_readiness.get("constraints_summary") or {}),
            "binding_summary": dict(strategy_activation_readiness.get("binding_summary") or {}),
            "campaign_shell_summary": dict(
                strategy_activation_readiness.get("campaign_shell_summary") or {}
            ),
            "strategy_activation_summary": dict(
                strategy_activation_readiness.get("strategy_activation_summary") or {}
            ),
            "safety_statement": {
                "strategy_activation_readiness_would_be_prepared": not blockers and not idempotent_prepare,
                "strategy_will_activate": False,
                "strategy_active_will_be_set_true": False,
                "signal_loop_will_start": False,
                "trial_started_will_be_set_true": False,
                "auto_execution_will_be_enabled": False,
                "auto_within_budget_will_be_enabled": False,
                "execution_intent_will_be_created": False,
                "orders_will_be_placed": False,
                "live_ready_will_be_enabled": False,
                "next_required_implementation": "separate strategy activation Operation",
            },
            "next_step": strategy_activation_readiness.get("next_step")
            or "Confirm can prepare strategy activation readiness metadata only.",
            "confirmation_requirement": {
                "owner_confirmation_required_for_strategy_activation_readiness_metadata": not blockers,
                "confirm_disabled": False,
                "reason": (
                    "Confirm prepares strategy activation readiness metadata only. Strategy will not activate; "
                    "signal loop will not start; auto execution will not be enabled; no execution intent or order will be created."
                ),
            },
        }
        unique_blockers = list(dict.fromkeys(blockers))
        unique_warnings = list(dict.fromkeys(warnings))
        if unique_blockers:
            return "block", unique_blockers, unique_warnings, "; ".join(unique_blockers), before, after
        summary = _operation_summary(policy.operation_type, after)
        return "warn" if unique_warnings else "allow", unique_blockers, unique_warnings, summary, before, after

    def _strategy_state_activation_from_admission_runtime_preflight_decision(
        self,
        *,
        policy: OperationPolicy,
        strategy_state_activation_readiness: dict[str, Any],
        before: dict[str, Any],
        blockers: list[str],
        warnings: list[str],
        audit_writable: Optional[bool],
    ) -> tuple[PreflightDecision, list[str], list[str], str, dict[str, Any], dict[str, Any]]:
        if audit_writable is False:
            blockers.append("audit is not writable")
        if not strategy_state_activation_readiness.get("available", False):
            blockers.append("admission strategy state activation readiness unavailable")
        blockers.extend(str(item) for item in strategy_state_activation_readiness.get("blockers") or [])
        warnings.extend(str(item) for item in strategy_state_activation_readiness.get("warnings") or [])
        idempotent_activate = bool(strategy_state_activation_readiness.get("idempotent_activate", False))
        after = {
            "phase": "BRC-R5-002 Phase 14",
            "strategy_state_activation_only": True,
            "confirm_disabled": False,
            "order_capable_strategy_available": False,
            "actual_signal_loop_available": False,
            "actual_order_execution_available": False,
            "planned_result_status": "strategy_active_no_execution",
            "idempotent_activate": idempotent_activate,
            "admission_summary": dict(strategy_state_activation_readiness.get("admission_summary") or {}),
            "strategy_family_summary": dict(
                strategy_state_activation_readiness.get("strategy_family_summary") or {}
            ),
            "trial_env": strategy_state_activation_readiness.get("trial_env"),
            "trial_stage": strategy_state_activation_readiness.get("trial_stage"),
            "execution_mode": strategy_state_activation_readiness.get("execution_mode"),
            "constraints_summary": dict(strategy_state_activation_readiness.get("constraints_summary") or {}),
            "binding_summary": dict(strategy_state_activation_readiness.get("binding_summary") or {}),
            "campaign_shell_summary": dict(
                strategy_state_activation_readiness.get("campaign_shell_summary") or {}
            ),
            "strategy_activation_summary": dict(
                strategy_state_activation_readiness.get("strategy_activation_summary") or {}
            ),
            "safety_statement": {
                "strategy_metadata_activation_would_occur": not blockers and not idempotent_activate,
                "strategy_active_will_be_set_true": not blockers,
                "strategy_state_after_confirm": "strategy_active_no_execution",
                "strategy_execution_enabled_after_confirm": False,
                "strategy_runner_will_start": False,
                "signal_loop_will_start": False,
                "signal_loop_will_be_enabled": False,
                "trial_started_will_be_set_true": False,
                "auto_execution_will_be_enabled": False,
                "auto_within_budget_will_be_enabled": False,
                "trade_intent_will_be_created": False,
                "execution_intent_will_be_created": False,
                "orders_will_be_placed": False,
                "live_ready_will_be_enabled": False,
                "next_required_implementation": "separate signal loop / observe gate Operation",
            },
            "next_step": strategy_state_activation_readiness.get("next_step")
            or "Confirm can activate strategy metadata in non-execution state only.",
            "confirmation_requirement": {
                "owner_confirmation_required_for_strategy_state_activation_metadata": not blockers,
                "confirm_disabled": False,
                "reason": (
                    "Confirm activates strategy state metadata only. Strategy runner will not start; "
                    "signal loop will not start; auto execution will not be enabled; no execution intent or order will be created."
                ),
            },
        }
        unique_blockers = list(dict.fromkeys(blockers))
        unique_warnings = list(dict.fromkeys(warnings))
        if unique_blockers:
            return "block", unique_blockers, unique_warnings, "; ".join(unique_blockers), before, after
        summary = _operation_summary(policy.operation_type, after)
        return "warn" if unique_warnings else "allow", unique_blockers, unique_warnings, summary, before, after

    def _signal_loop_from_admission_strategy_preflight_decision(
        self,
        *,
        policy: OperationPolicy,
        signal_loop_readiness: dict[str, Any],
        before: dict[str, Any],
        blockers: list[str],
        warnings: list[str],
        audit_writable: Optional[bool],
    ) -> tuple[PreflightDecision, list[str], list[str], str, dict[str, Any], dict[str, Any]]:
        if audit_writable is False:
            blockers.append("audit is not writable")
        if not signal_loop_readiness.get("available", False):
            blockers.append("admission signal loop readiness unavailable")
        blockers.extend(str(item) for item in signal_loop_readiness.get("blockers") or [])
        warnings.extend(str(item) for item in signal_loop_readiness.get("warnings") or [])
        idempotent_prepare = bool(signal_loop_readiness.get("idempotent_prepare", False))
        after = {
            "phase": "BRC-R5-002 Phase 15",
            "signal_loop_readiness_only": True,
            "confirm_disabled": False,
            "actual_signal_loop_available": False,
            "actual_signal_generation_available": False,
            "actual_order_execution_available": False,
            "planned_result_status": "signal_loop_ready_not_started",
            "idempotent_prepare": idempotent_prepare,
            "admission_summary": dict(signal_loop_readiness.get("admission_summary") or {}),
            "strategy_family_summary": dict(signal_loop_readiness.get("strategy_family_summary") or {}),
            "trial_env": signal_loop_readiness.get("trial_env"),
            "trial_stage": signal_loop_readiness.get("trial_stage"),
            "execution_mode": signal_loop_readiness.get("execution_mode"),
            "constraints_summary": dict(signal_loop_readiness.get("constraints_summary") or {}),
            "binding_summary": dict(signal_loop_readiness.get("binding_summary") or {}),
            "campaign_shell_summary": dict(signal_loop_readiness.get("campaign_shell_summary") or {}),
            "signal_loop_summary": dict(signal_loop_readiness.get("signal_loop_summary") or {}),
            "safety_statement": {
                "signal_loop_readiness_would_be_prepared": not blockers and not idempotent_prepare,
                "signal_loop_will_start": False,
                "signal_loop_will_be_enabled": False,
                "signal_will_be_generated": False,
                "trade_intent_will_be_created": False,
                "execution_intent_will_be_created": False,
                "orders_will_be_placed": False,
                "trial_started_will_be_set_true": False,
                "auto_execution_will_be_enabled": False,
                "auto_within_budget_will_be_enabled": False,
                "live_ready_will_be_enabled": False,
                "next_required_implementation": "separate observe gate / signal loop start Operation",
            },
            "next_step": signal_loop_readiness.get("next_step")
            or "Confirm can prepare signal loop readiness metadata only.",
            "confirmation_requirement": {
                "owner_confirmation_required_for_signal_loop_readiness_metadata": not blockers,
                "confirm_disabled": False,
                "reason": (
                    "Confirm prepares signal loop readiness metadata only. Signal loop will not start; "
                    "no signal will be generated; no trade intent, execution intent, or order will be created."
                ),
            },
        }
        unique_blockers = list(dict.fromkeys(blockers))
        unique_warnings = list(dict.fromkeys(warnings))
        if unique_blockers:
            return "block", unique_blockers, unique_warnings, "; ".join(unique_blockers), before, after
        summary = _operation_summary(policy.operation_type, after)
        return "warn" if unique_warnings else "allow", unique_blockers, unique_warnings, summary, before, after

    def _signal_loop_start_from_admission_strategy_preflight_decision(
        self,
        *,
        policy: OperationPolicy,
        signal_loop_start_readiness: dict[str, Any],
        before: dict[str, Any],
        blockers: list[str],
        warnings: list[str],
        audit_writable: Optional[bool],
    ) -> tuple[PreflightDecision, list[str], list[str], str, dict[str, Any], dict[str, Any]]:
        if audit_writable is False:
            blockers.append("audit is not writable")
        if not signal_loop_start_readiness.get("available", False):
            blockers.append("admission signal loop start readiness unavailable")
        blockers.extend(str(item) for item in signal_loop_start_readiness.get("blockers") or [])
        warnings.extend(str(item) for item in signal_loop_start_readiness.get("warnings") or [])
        idempotent_start = bool(signal_loop_start_readiness.get("idempotent_start", False))
        after = {
            "phase": "BRC-R5-002 Phase 16",
            "signal_loop_start_state_only": True,
            "confirm_disabled": False,
            "actual_signal_generation_available": False,
            "actual_trade_intent_available": False,
            "actual_order_execution_available": False,
            "planned_result_status": "signal_loop_started_no_signal",
            "idempotent_start": idempotent_start,
            "admission_summary": dict(signal_loop_start_readiness.get("admission_summary") or {}),
            "strategy_family_summary": dict(signal_loop_start_readiness.get("strategy_family_summary") or {}),
            "trial_env": signal_loop_start_readiness.get("trial_env"),
            "trial_stage": signal_loop_start_readiness.get("trial_stage"),
            "execution_mode": signal_loop_start_readiness.get("execution_mode"),
            "constraints_summary": dict(signal_loop_start_readiness.get("constraints_summary") or {}),
            "binding_summary": dict(signal_loop_start_readiness.get("binding_summary") or {}),
            "campaign_shell_summary": dict(signal_loop_start_readiness.get("campaign_shell_summary") or {}),
            "signal_loop_summary": dict(signal_loop_start_readiness.get("signal_loop_summary") or {}),
            "safety_statement": {
                "signal_loop_state_would_start": not blockers and not idempotent_start,
                "signal_loop_enabled_scope_after_confirm": "non_trading_loop_state",
                "signal_will_be_generated": False,
                "trade_intent_will_be_created": False,
                "execution_intent_will_be_created": False,
                "orders_will_be_placed": False,
                "trial_started_will_be_set_true": False,
                "auto_execution_will_be_enabled": False,
                "auto_within_budget_will_be_enabled": False,
                "live_ready_will_be_enabled": False,
                "next_required_implementation": "separate signal generation / evaluation Operation",
            },
            "next_step": signal_loop_start_readiness.get("next_step")
            or "Confirm can start signal loop state metadata only.",
            "confirmation_requirement": {
                "owner_confirmation_required_for_signal_loop_state_metadata": not blockers,
                "confirm_disabled": False,
                "reason": (
                    "Confirm starts signal loop state metadata only. No signal will be generated; "
                    "no trade intent, execution intent, or order will be created."
                ),
            },
        }
        unique_blockers = list(dict.fromkeys(blockers))
        unique_warnings = list(dict.fromkeys(warnings))
        if unique_blockers:
            return "block", unique_blockers, unique_warnings, "; ".join(unique_blockers), before, after
        summary = _operation_summary(policy.operation_type, after)
        return "warn" if unique_warnings else "allow", unique_blockers, unique_warnings, summary, before, after

    def _signal_evaluation_from_admission_strategy_preflight_decision(
        self,
        *,
        policy: OperationPolicy,
        signal_evaluation_readiness: dict[str, Any],
        before: dict[str, Any],
        blockers: list[str],
        warnings: list[str],
        audit_writable: Optional[bool],
    ) -> tuple[PreflightDecision, list[str], list[str], str, dict[str, Any], dict[str, Any]]:
        if audit_writable is False:
            blockers.append("audit is not writable")
        if not signal_evaluation_readiness.get("available", False):
            blockers.append("admission signal evaluation readiness unavailable")
        blockers.extend(str(item) for item in signal_evaluation_readiness.get("blockers") or [])
        warnings.extend(str(item) for item in signal_evaluation_readiness.get("warnings") or [])
        idempotent_evaluation = bool(signal_evaluation_readiness.get("idempotent_evaluation", False))
        after = {
            "phase": "BRC-R5-002 Phase 17",
            "signal_evaluation_metadata_only": True,
            "confirm_disabled": False,
            "actual_trade_intent_available": False,
            "actual_order_execution_available": False,
            "planned_result_status": "signal_evaluated_no_intent",
            "idempotent_evaluation": idempotent_evaluation,
            "admission_summary": dict(signal_evaluation_readiness.get("admission_summary") or {}),
            "strategy_family_summary": dict(signal_evaluation_readiness.get("strategy_family_summary") or {}),
            "trial_env": signal_evaluation_readiness.get("trial_env"),
            "trial_stage": signal_evaluation_readiness.get("trial_stage"),
            "execution_mode": signal_evaluation_readiness.get("execution_mode"),
            "constraints_summary": dict(signal_evaluation_readiness.get("constraints_summary") or {}),
            "binding_summary": dict(signal_evaluation_readiness.get("binding_summary") or {}),
            "campaign_shell_summary": dict(signal_evaluation_readiness.get("campaign_shell_summary") or {}),
            "signal_evaluation_summary": dict(
                signal_evaluation_readiness.get("signal_evaluation_summary") or {}
            ),
            "safety_statement": {
                "signal_evaluation_would_be_recorded": not blockers and not idempotent_evaluation,
                "signal_is_trade_intent": False,
                "trade_intent_will_be_created": False,
                "execution_intent_will_be_created": False,
                "orders_will_be_placed": False,
                "trial_started_will_be_set_true": False,
                "auto_execution_will_be_enabled": False,
                "auto_within_budget_will_be_enabled": False,
                "live_ready_will_be_enabled": False,
                "next_required_implementation": "separate signal-to-trial-trade-intent Operation",
            },
            "next_step": signal_evaluation_readiness.get("next_step")
            or "Confirm can record signal evaluation metadata only.",
            "confirmation_requirement": {
                "owner_confirmation_required_for_signal_evaluation_metadata": not blockers,
                "confirm_disabled": False,
                "reason": (
                    "Confirm records signal evaluation metadata only. No trade intent, "
                    "execution intent, or order will be created."
                ),
            },
        }
        unique_blockers = list(dict.fromkeys(blockers))
        unique_warnings = list(dict.fromkeys(warnings))
        if unique_blockers:
            return "block", unique_blockers, unique_warnings, "; ".join(unique_blockers), before, after
        summary = _operation_summary(policy.operation_type, after)
        return "warn" if unique_warnings else "allow", unique_blockers, unique_warnings, summary, before, after

    def _emergency_flatten_preflight_decision(
        self,
        *,
        policy: OperationPolicy,
        runtime_summary: dict[str, Any],
        market_summary: dict[str, Any],
        before: dict[str, Any],
        blockers: list[str],
        warnings: list[str],
    ) -> tuple[PreflightDecision, list[str], list[str], str, dict[str, Any], dict[str, Any]]:
        active_positions = _records_from_summary(market_summary, "positions", "active_positions")
        open_orders = _records_from_summary(market_summary, "open_orders", "local_open_orders")
        unmanaged_orders = _records_from_summary(market_summary, "unknown_or_unmanaged_orders")
        unmanaged_positions = _records_from_summary(market_summary, "unknown_or_unmanaged_positions")
        active_position_count = int(market_summary.get("active_position_count") or len(active_positions))
        open_order_count = int(market_summary.get("open_order_count") or len(open_orders))
        no_exposure = active_position_count == 0 and open_order_count == 0
        reconciliation_status = _reconciliation_status_value(market_summary)
        dry_run_inputs_available = not any(
            "account facts unavailable" in item or "account facts blocked" in item
            for item in blockers
        )

        if runtime_summary.get("live_ready") is True or runtime_summary.get("testnet") is False:
            blockers.append("live/mainnet flatten execution is forbidden")
        if unmanaged_orders or unmanaged_positions:
            warnings.append("unknown or unmanaged exchange exposure blocks actual flatten; dry-run is diagnostic only")
        if no_exposure:
            warnings.append("no positions and no open orders were found; dry-run plan is a noop")
        if reconciliation_status == "mismatch":
            warnings.append("account reconciliation mismatch blocks actual flatten; dry-run is diagnostic only")

        dry_run_plan = (
            _flatten_dry_run_plan(
                operation_id="pending",
                active_positions=active_positions,
                open_orders=open_orders,
                unmanaged_orders=unmanaged_orders,
                unmanaged_positions=unmanaged_positions,
                market_summary=market_summary,
                warnings=warnings,
            )
            if dry_run_inputs_available
            else {}
        )

        after = {
            "planning_only": False,
            "dry_run_only": True,
            "actual_execution": False,
            "actual_execution_available": False,
            "required_executor_available": False,
            "executor": policy.backend_executor,
            "source": market_summary.get("source") or market_summary.get("data_source"),
            "truth_level": market_summary.get("truth_level"),
            "reconciliation_status": reconciliation_status,
            "does_not_cancel_orders": True,
            "does_not_close_positions": True,
            "does_not_place_orders": True,
            "does_not_flatten": True,
            "live_ready": False,
            "current_positions": active_positions,
            "open_orders": open_orders,
            "unknown_or_unmanaged_orders": unmanaged_orders,
            "unknown_or_unmanaged_positions": unmanaged_positions,
            "dry_run_plan": dry_run_plan,
            "estimated_flatten_impact": {
                "active_position_count": active_position_count,
                "open_order_count": open_order_count,
                "cancel_order_candidate_count": len(dry_run_plan.get("cancel_order_candidates") or []),
                "close_position_candidate_count": len(dry_run_plan.get("close_position_candidates") or []),
                "estimated_actions_count": dry_run_plan.get("estimated_actions_count", 0),
                "would_cancel_order_count": 0,
                "would_close_position_count": 0,
                "planned_result_status": dry_run_plan.get("plan_status") or ("noop" if no_exposure else "dry_run"),
                "account_source": market_summary.get("source") or market_summary.get("data_source"),
                "truth_level": market_summary.get("truth_level"),
                "reconciliation_status": reconciliation_status,
            },
            "confirmation_requirement": {
                "owner_confirmation_required_for_dry_run_record": dry_run_inputs_available and not blockers,
                "owner_confirmation_required_for_actual_execution": False,
                "current_preflight_is_dry_run_only": True,
            },
        }
        safety_blocked = bool(blockers)
        if not dry_run_inputs_available and not safety_blocked:
            blockers.append("flatten dry-run inputs unavailable")
            decision: PreflightDecision = "unavailable"
        elif safety_blocked:
            decision = "block"
        else:
            decision = "warn" if warnings else "allow"
        return decision, blockers, warnings, _operation_summary(policy.operation_type, after), before, after

    def _emergency_stop_runtime_preflight_decision(
        self,
        *,
        policy: OperationPolicy,
        runtime_summary: dict[str, Any],
        market_summary: dict[str, Any],
        before: dict[str, Any],
        blockers: list[str],
        warnings: list[str],
        audit_writable: Optional[bool],
    ) -> tuple[PreflightDecision, list[str], list[str], str, dict[str, Any], dict[str, Any]]:
        executor_available = bool(policy.backend_executor and policy.executable_through_operation)
        current_state = _runtime_state_value(runtime_summary)
        already_stopped = _runtime_already_stopped(current_state)
        if audit_writable is False:
            blockers.append("audit is not writable")
        if runtime_summary.get("live_ready") is True:
            blockers.append("live/mainnet runtime stop execution is forbidden")
        if already_stopped:
            warnings.append("runtime is already stopped or hard-locked; confirm would record a noop")
        after = {
            "planning_only": not executor_available,
            "actual_execution_available": executor_available,
            "required_executor_available": executor_available,
            "executor": policy.backend_executor,
            "runtime_summary": runtime_summary,
            "runtime_state": current_state,
            "already_stopped": already_stopped,
            "planned_result_status": "noop" if already_stopped else ("executed" if executor_available else "unavailable"),
            "account_order_summary": {
                "source": market_summary.get("source") or market_summary.get("data_source"),
                "truth_level": market_summary.get("truth_level"),
                "reconciliation_status": _reconciliation_status_value(market_summary),
                "unknown_or_unmanaged_order_count": int(market_summary.get("unknown_or_unmanaged_order_count") or 0),
                "unknown_or_unmanaged_position_count": int(market_summary.get("unknown_or_unmanaged_position_count") or 0),
            },
            "expected_stop_behavior": {
                "would_stop_runtime": executor_available,
                "would_pause_new_strategy_actions": executor_available,
                "would_mark_stopped_by_owner": executor_available and not already_stopped,
                "does_not_flatten": True,
                "does_not_cancel_orders": True,
                "does_not_place_orders": True,
                "does_not_withdraw_or_transfer": True,
            },
            "does_not_flatten": True,
            "does_not_cancel_orders": True,
            "does_not_place_orders": True,
            "does_not_withdraw_or_transfer": True,
            "confirmation_requirement": {
                "owner_confirmation_required_for_actual_execution": executor_available,
                "current_preflight_is_planning_only": not executor_available,
            },
        }
        safety_blocked = bool(blockers)
        if not executor_available:
            blockers.append("emergency stop runtime executor unavailable; this preflight is planning only")
            decision: PreflightDecision = "block" if safety_blocked else "unavailable"
        elif safety_blocked:
            decision = "block"
        else:
            decision = "warn" if warnings else "allow"
        return decision, blockers, warnings, _operation_summary(policy.operation_type, after), before, after

    def _fixed_rehearsal_safety_blockers(
        self,
        *,
        runtime_summary: dict[str, Any],
        market_summary: dict[str, Any],
        campaign_summary: dict[str, Any],
    ) -> list[str]:
        blockers: list[str] = []
        if self._readers.fixed_rehearsal_executor is None:
            blockers.append("fixed rehearsal Operation executor unavailable")
        if runtime_summary.get("profile") != "brc_btc_eth_testnet_runtime":
            blockers.append("runtime profile is not brc_btc_eth_testnet_runtime")
        if runtime_summary.get("testnet") is not True:
            blockers.append("exchange testnet is not confirmed")
        if runtime_summary.get("live_ready") is True:
            blockers.append("live/mainnet readiness is forbidden for fixed rehearsal")
        if runtime_summary.get("runtime_control_api_enabled") is not True:
            blockers.append("runtime mutation gate is not enabled")
        if runtime_summary.get("runtime_test_signal_injection_enabled") is not True:
            blockers.append("controlled test signal gate is not enabled")
        if runtime_summary.get("gks_active") is not True:
            blockers.append("global kill switch must be active before rehearsal opens the fixed entry window")
        if runtime_summary.get("startup_guard_armed") is True:
            blockers.append("startup guard must not already be armed before rehearsal")
        if int(market_summary.get("active_position_count") or 0) > 0:
            blockers.append("local active positions exist")
        if int(market_summary.get("open_order_count") or 0) > 0:
            blockers.append("local open orders exist")
        if market_summary.get("all_local_flat") is not True:
            blockers.append("local flatness proof is not true")
        if campaign_summary.get("available"):
            blockers.append("active BRC campaign already exists")
        return blockers

    @staticmethod
    def _passed_checks(*, decision: PreflightDecision, blockers: list[str]) -> list[str]:
        if blockers or decision in {"block", "unavailable", "expired"}:
            return []
        return [
            "operation_id_created",
            "preflight_persisted",
            "operation_policy_enabled",
            "live_mainnet_forbidden",
            "withdrawal_transfer_forbidden",
            "owner_confirmation_required",
        ]

    @staticmethod
    def _to_preflight_response(
        operation: OperationRecord,
        preflight: PreflightSnapshot,
    ) -> OperationPreflightResponse:
        return OperationPreflightResponse(
            operation_id=operation.operation_id,
            preflight_id=preflight.preflight_id,
            operation_type=operation.operation_type,
            decision=preflight.decision,
            summary=preflight.summary,
            before=preflight.before,
            after=preflight.after,
            account_order_summary=preflight.account_snapshot,
            runtime_summary=preflight.runtime_snapshot,
            campaign_summary=preflight.campaign_snapshot,
            playbook_summary=preflight.playbook_snapshot,
            risk_summary=preflight.risk_result,
            admission_summary=dict(preflight.after.get("admission_summary") or {}),
            strategy_family_summary=dict(preflight.after.get("strategy_family_summary") or {}),
            constraints_summary=dict(preflight.after.get("constraints_summary") or {}),
            owner_risk_acceptance_summary=dict(
                preflight.after.get("owner_risk_acceptance_summary") or {}
            ),
            binding_summary=dict(preflight.after.get("binding_summary") or {}),
            campaign_shell_summary=dict(preflight.after.get("campaign_shell_summary") or {}),
            runtime_carrier_summary=dict(preflight.after.get("runtime_carrier_summary") or {}),
            runtime_start_summary=dict(preflight.after.get("runtime_start_summary") or {}),
            runtime_handoff_summary=dict(preflight.after.get("runtime_handoff_summary") or {}),
            strategy_activation_summary=dict(preflight.after.get("strategy_activation_summary") or {}),
            signal_loop_summary=dict(preflight.after.get("signal_loop_summary") or {}),
            signal_evaluation_summary=dict(preflight.after.get("signal_evaluation_summary") or {}),
            trade_intent_summary=dict(preflight.after.get("trade_intent_summary") or {}),
            next_step=_optional_str(preflight.after.get("next_step")),
            confirmation_requirement=preflight.confirmation_requirement,
            idempotency_key=preflight.idempotency_key,
            status=operation.status,
        )

    @staticmethod
    def _to_confirm_response(result: ExecutionResult) -> OperationConfirmResponse:
        return OperationConfirmResponse(
            operation_id=result.operation_id,
            preflight_id=result.preflight_id,
            status=result.status,
            rechecked=result.rechecked,
            result_summary=result.result_summary
            or {
                "status": result.status,
                "blocked_reason": result.blocked_reason,
                "failed_reason": result.failed_reason,
            },
            audit_refs=result.audit_refs,
            campaign_refs=result.campaign_refs,
            review_refs=result.review_refs,
            next_state=result.final_state_snapshot,
        )


def _build_default_policies() -> dict[str, OperationPolicy]:
    policies = [
        OperationPolicy(
            operation_type="switch_playbook",
            display_name="Switch Playbook",
            risk_level="medium",
            allowed_env=["local", "testnet"],
            confirmation_phrase="CONFIRM_SWITCH_PLAYBOOK",
            capability_status="enabled",
            current_reason="Operation Preflight available for allowlisted BRC playbooks.",
            backend_executor="brc_switch_playbook",
            executable_through_operation=True,
        ),
        OperationPolicy(
            operation_type="start_review",
            display_name="Start Review",
            risk_level="read_only",
            allowed_env=["local", "testnet"],
            confirmation_phrase="CONFIRM_START_REVIEW",
            capability_status="enabled",
            current_reason="Operation can start/read the review packet boundary without mutation.",
            backend_executor="brc_start_review_packet",
            executable_through_operation=True,
        ),
        OperationPolicy(
            operation_type="write_review_decision",
            display_name="Write Review Decision",
            risk_level="low",
            allowed_env=["local", "testnet"],
            confirmation_phrase="CONFIRM_WRITE_REVIEW",
            capability_status="enabled",
            current_reason="Operation-backed review decision write is enabled and remains testnet-only/non-execution.",
            backend_executor="brc_write_review_decision",
            executable_through_operation=True,
        ),
        OperationPolicy(
            operation_type="run_fixed_testnet_rehearsal",
            display_name="Fixed Testnet Rehearsal",
            risk_level="high",
            allowed_env=["testnet"],
            confirmation_phrase="CONFIRM_FIXED_TESTNET_REHEARSAL",
            capability_status="unavailable",
            current_reason=(
                "Fixed rehearsal executor is not wired. When wired, Operation confirmation is the only Owner Console "
                "authorization source; workflow ids are internal refs only."
            ),
        ),
        OperationPolicy(
            operation_type="enter_observe",
            display_name="Enter Observe",
            risk_level="read_only",
            allowed_env=["local", "testnet"],
            confirmation_phrase="CONFIRM_ENTER_OBSERVE",
            capability_status="enabled",
            current_reason="Operation-backed runtime transition to observe is available when the campaign state adapter is wired.",
            backend_executor="runtime_state_observe",
            executable_through_operation=True,
        ),
        OperationPolicy(
            operation_type="enter_pause",
            display_name="Enter Pause",
            risk_level="low",
            allowed_env=["local", "testnet"],
            confirmation_phrase="CONFIRM_ENTER_PAUSE",
            capability_status="enabled",
            current_reason="Operation-backed runtime transition to pause is available when the campaign state adapter is wired.",
            backend_executor="runtime_state_pause",
            executable_through_operation=True,
        ),
        OperationPolicy(
            operation_type="revoke_budget",
            display_name="Revoke Budget Authorization",
            risk_level="low",
            allowed_env=["local", "testnet"],
            confirmation_phrase="CONFIRM_REVOKE_BUDGET",
            capability_status="unavailable",
            current_reason="Budget revoke requires the budget authorization reader and revoke executor to be wired.",
            backend_executor=None,
            executable_through_operation=False,
        ),
        OperationPolicy(
            operation_type="enter_strategy_or_monitor",
            display_name="Enter Strategy Or Monitor",
            risk_level="medium",
            allowed_env=["local", "testnet"],
            confirmation_phrase="CONFIRM_ENTER_MONITOR",
            capability_status="enabled",
            current_reason="Operation degrades this to a monitor carrier only; it never enables unrestricted auto trading.",
            backend_executor="monitor_carrier_noop",
            executable_through_operation=True,
        ),
        OperationPolicy(
            operation_type="pause_new_entries",
            display_name="Pause New Entries",
            risk_level="medium",
            allowed_env=["local", "testnet"],
            confirmation_phrase=None,
            capability_status="unavailable",
            current_reason="No Operation-backed runtime cutoff adapter is enabled.",
        ),
        OperationPolicy(
            operation_type="emergency_stop_runtime",
            display_name="Emergency Stop Runtime",
            risk_level="high",
            allowed_env=["local", "testnet"],
            confirmation_phrase=None,
            capability_status="preflight_planning_available",
            current_reason=(
                "Operation-backed preflight planning is available for emergency stop. "
                "Actual stop execution is not enabled because no explicit safe stop executor is wired."
            ),
        ),
        OperationPolicy(
            operation_type="emergency_flatten",
            display_name="Emergency Flatten",
            risk_level="high",
            allowed_env=["testnet"],
            confirmation_phrase="CONFIRM_FLATTEN_DRY_RUN",
            capability_status="preflight_dry_run_available",
            current_reason=(
                "Operation-backed flatten dry-run is available. Dry-run only: no cancel, close, order, "
                "actual flatten, live, withdrawal, or transfer execution is enabled."
            ),
            backend_executor="flatten_dry_run_plan_only",
            dry_run_only=True,
        ),
        OperationPolicy(
            operation_type="create_gated_trial_from_admission",
            display_name="Admission Binding Reservation",
            risk_level="medium",
            allowed_env=["local", "testnet", "live"],
            confirmation_phrase="CONFIRM_RESERVE_ADMISSION_BINDING",
            capability_status="binding_reservation_available",
            current_reason=(
                "Confirm reserves admission-trial binding only. It does not create a campaign or runtime carrier."
            ),
            backend_executor="admission_trial_binding_reservation",
            executable_through_operation=True,
        ),
        OperationPolicy(
            operation_type="create_campaign_from_admission_binding",
            display_name="Admission Campaign Shell",
            risk_level="medium",
            allowed_env=["local", "testnet", "live"],
            confirmation_phrase="CONFIRM_CREATE_ADMISSION_CAMPAIGN_SHELL",
            capability_status="campaign_shell_creation_available",
            current_reason=(
                "Confirm creates a campaign shell from a reserved admission binding only. "
                "It does not install runtime constraints, start a runtime carrier, execute strategy, or place orders."
            ),
            backend_executor="admission_campaign_shell_creation",
            executable_through_operation=True,
        ),
        OperationPolicy(
            operation_type="install_runtime_constraints_from_admission_campaign",
            display_name="Install Admission Campaign Constraints",
            risk_level="medium",
            allowed_env=["local", "testnet", "live"],
            confirmation_phrase="CONFIRM_INSTALL_ADMISSION_CAMPAIGN_CONSTRAINTS",
            capability_status="operation_preflight_available",
            current_reason=(
                "Confirm installs constraints metadata only from an admission-created campaign. "
                "It does not start runtime or strategy and does not place orders."
            ),
            backend_executor="admission_runtime_constraint_metadata_install",
            executable_through_operation=True,
        ),
        OperationPolicy(
            operation_type="prepare_runtime_carrier_from_admission_campaign",
            display_name="Prepare Admission Runtime Carrier",
            risk_level="medium",
            allowed_env=["local", "testnet", "live"],
            confirmation_phrase="CONFIRM_PREPARE_ADMISSION_RUNTIME_CARRIER",
            capability_status="operation_preflight_available",
            current_reason=(
                "Confirm prepares runtime carrier readiness metadata only from an admission campaign. "
                "It does not start runtime, strategy, or trading."
            ),
            backend_executor="admission_runtime_carrier_readiness_metadata_prepare",
            executable_through_operation=True,
        ),
        OperationPolicy(
            operation_type="prepare_runtime_start_from_admission_carrier",
            display_name="Prepare Admission Runtime Start",
            risk_level="medium",
            allowed_env=["local", "testnet", "live"],
            confirmation_phrase="CONFIRM_PREPARE_ADMISSION_RUNTIME_START",
            capability_status="operation_preflight_available",
            current_reason=(
                "Confirm prepares runtime start readiness only from a carrier-ready admission campaign. "
                "It does not start runtime, strategy, or trading."
            ),
            backend_executor="admission_runtime_start_readiness_metadata_prepare",
            executable_through_operation=True,
        ),
        OperationPolicy(
            operation_type="evaluate_trial_trade_intent",
            display_name="Evaluate Trial Trade Intent",
            risk_level="low",
            allowed_env=["local", "testnet", "live"],
            confirmation_phrase="CONFIRM_EVALUATE_TRIAL_TRADE_INTENT",
            capability_status="operation_preflight_available",
            current_reason=(
                "Confirm evaluates execution-mode enforcement and may record non-executable "
                "trial trade intent evidence only. It does not start runtime, strategy, or trading."
            ),
            backend_executor="admission_trial_trade_intent_enforcement_evaluate",
            executable_through_operation=True,
        ),
        OperationPolicy(
            operation_type="prepare_runtime_handoff_from_admission_campaign",
            display_name="Prepare Admission Runtime Handoff",
            risk_level="medium",
            allowed_env=["local", "testnet", "live"],
            confirmation_phrase="CONFIRM_PREPARE_ADMISSION_RUNTIME_HANDOFF",
            capability_status="operation_preflight_available",
            current_reason=(
                "Confirm prepares runtime handoff readiness only from a runtime-start-ready admission campaign. "
                "It does not start runtime, strategy, or trading."
            ),
            backend_executor="admission_runtime_handoff_readiness_metadata_prepare",
            executable_through_operation=True,
        ),
        OperationPolicy(
            operation_type="start_runtime_from_admission_handoff",
            display_name="Start Runtime From Admission Handoff",
            risk_level="medium",
            allowed_env=["local", "testnet", "live"],
            confirmation_phrase="CONFIRM_START_ADMISSION_RUNTIME",
            capability_status="operation_preflight_available",
            current_reason=(
                "Confirm starts admission-backed runtime state only. It does not activate strategy, "
                "enable auto execution, create execution intents, or place orders."
            ),
            backend_executor="admission_runtime_state_start",
            executable_through_operation=True,
        ),
        OperationPolicy(
            operation_type="prepare_strategy_activation_from_admission_runtime",
            display_name="Prepare Strategy Activation From Admission Runtime",
            risk_level="medium",
            allowed_env=["local", "testnet", "live"],
            confirmation_phrase="CONFIRM_PREPARE_STRATEGY_ACTIVATION",
            capability_status="operation_preflight_available",
            current_reason=(
                "Confirm prepares strategy activation readiness metadata only. It does not activate strategy, "
                "start signal loop, enable auto execution, create execution intents, or place orders."
            ),
            backend_executor="admission_strategy_activation_readiness_metadata_prepare",
            executable_through_operation=True,
        ),
        OperationPolicy(
            operation_type="activate_strategy_from_admission_runtime",
            display_name="Activate Strategy From Admission Runtime",
            risk_level="medium",
            allowed_env=["local", "testnet", "live"],
            confirmation_phrase="CONFIRM_ACTIVATE_STRATEGY_NO_EXECUTION",
            capability_status="operation_preflight_available",
            current_reason=(
                "Confirm activates strategy state metadata only. It does not enable signal loop, "
                "auto execution, execution intents, or orders."
            ),
            backend_executor="admission_strategy_state_activation_metadata_only",
            executable_through_operation=True,
        ),
        OperationPolicy(
            operation_type="prepare_signal_loop_from_admission_strategy",
            display_name="Prepare Signal Loop From Admission Strategy",
            risk_level="medium",
            allowed_env=["local", "testnet", "live"],
            confirmation_phrase="CONFIRM_PREPARE_SIGNAL_LOOP",
            capability_status="operation_preflight_available",
            current_reason=(
                "Confirm prepares signal loop readiness metadata only. It does not start signal loop, "
                "generate signals, create trade intents, execution intents, or orders."
            ),
            backend_executor="admission_signal_loop_readiness_metadata_prepare",
            executable_through_operation=True,
        ),
        OperationPolicy(
            operation_type="start_signal_loop_from_admission_strategy",
            display_name="Start Signal Loop From Admission Strategy",
            risk_level="medium",
            allowed_env=["local", "testnet", "live"],
            confirmation_phrase="CONFIRM_START_SIGNAL_LOOP_NO_SIGNAL",
            capability_status="operation_preflight_available",
            current_reason=(
                "Confirm starts signal loop state metadata only. It does not generate signals, "
                "create trade intents, execution intents, or orders."
            ),
            backend_executor="admission_signal_loop_state_start_no_signal",
            executable_through_operation=True,
        ),
        OperationPolicy(
            operation_type="evaluate_signal_from_admission_strategy",
            display_name="Evaluate Signal From Admission Strategy",
            risk_level="medium",
            allowed_env=["local", "testnet", "live"],
            confirmation_phrase="CONFIRM_EVALUATE_SIGNAL_NO_INTENT",
            capability_status="operation_preflight_available",
            current_reason=(
                "Confirm evaluates and records signal snapshot metadata only. It does not create "
                "trade intents, execution intents, or orders."
            ),
            backend_executor="admission_signal_evaluation_metadata_no_intent",
            executable_through_operation=True,
        ),
        OperationPolicy(
            operation_type="record_trial_trade_intent_from_signal_evaluation",
            display_name="Record Trial Trade Intent From Signal Evaluation",
            risk_level="medium",
            allowed_env=["local", "testnet", "live"],
            confirmation_phrase="CONFIRM_RECORD_TRIAL_TRADE_INTENT",
            capability_status="operation_preflight_available",
            current_reason=(
                "Confirm records non-executable trial trade intent evidence only after execution permission "
                "resolution. It does not create execution intents, enable auto execution, or place orders."
            ),
            backend_executor="admission_signal_trial_trade_intent_recording_no_execution",
            executable_through_operation=True,
        ),
    ]
    for op_type in sorted(_FORBIDDEN_OPERATION_TYPES):
        policies.append(
            OperationPolicy(
                operation_type=op_type,
                display_name=op_type.replace("_", " ").title(),
                risk_level="forbidden",
                allowed_env=[],
                confirmation_phrase=None,
                capability_status="forbidden",
                current_reason="Forbidden Owner Console capability: no executable path is exposed.",
            )
        )
    return {policy.operation_type: policy for policy in policies}


def _target_playbook_id(input_params: dict[str, Any]) -> str:
    value = input_params.get("target_playbook_id") or input_params.get("new_playbook_id")
    return str(value or "")


def _optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _explicit_runtime_instance_id(input_params: dict[str, Any]) -> Optional[str]:
    for key in ("runtime_instance_id", "strategy_runtime_instance_id"):
        runtime_instance_id = _optional_str(input_params.get(key))
        if runtime_instance_id is not None:
            return runtime_instance_id
    runtime = input_params.get("runtime")
    if isinstance(runtime, dict):
        return _optional_str(
            runtime.get("runtime_instance_id")
            or runtime.get("strategy_runtime_instance_id")
            or runtime.get("id")
        )
    return None


def _runtime_safety_readiness_payload(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json")
        return dict(dumped) if isinstance(dumped, dict) else {}
    if isinstance(value, dict):
        return dict(value)
    return {}


def _blocked_runtime_safety_readiness(
    *,
    runtime_instance_id: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "runtime_instance_id": runtime_instance_id,
        "status": "blocked",
        "blockers": [reason],
        "warnings": [],
        "missing_boundary_facts": ["runtime_safety_readiness_source"],
        "required_owner_confirmations": [],
        "requirements": [],
        "not_execution_authority": True,
        "execution_intent_created": False,
        "runtime_state_mutated": False,
        "order_created": False,
        "exchange_called": False,
    }


def _operation_summary(operation_type: str, after: dict[str, Any]) -> str:
    if operation_type == "switch_playbook":
        return (
            f"Switch playbook to {after.get('current_playbook_id')} after Owner confirmation. "
            "This does not place orders, reset attempts, reset PnL, or reset loss lock."
        )
    if operation_type == "write_review_decision":
        return (
            f"Write review decision {after.get('review_decision')} after Owner confirmation. "
            "This records review evidence only and cannot authorize live, withdrawal, or strategy execution."
        )
    if operation_type == "start_review":
        return "Start/read review packet after Owner confirmation. This is read-only and may complete as noop."
    if operation_type == "run_fixed_testnet_rehearsal":
        return (
            "Run the fixed ETH/BTC testnet rehearsal after Owner confirmation. "
            "The Operation Layer is the authorization source; no arbitrary workflow, symbol, side, size, live, "
            "withdrawal, or transfer path is exposed."
        )
    if operation_type == "enter_observe":
        return "Enter observe state after Owner confirmation. No order placement, close, or cancellation is performed."
    if operation_type == "enter_pause":
        return "Enter pause state after Owner confirmation. New strategy actions stop; no automatic close or cancel occurs."
    if operation_type == "revoke_budget":
        return (
            "Revoke budget authorization after Owner confirmation. This blocks future budgeted autonomy actions "
            "under the selected envelope and does not close positions, cancel TP/SL, transfer, or withdraw."
        )
    if operation_type == "enter_strategy_or_monitor":
        return (
            "Enter monitor carrier after Owner confirmation. This does not enable unrestricted automatic trading "
            "or direct order execution."
        )
    if operation_type == "emergency_flatten":
        if after.get("dry_run_only"):
            return (
                "Generate and confirm an emergency flatten dry-run record only. "
                "No orders will be cancelled, no positions will be closed, and no orders will be placed."
            )
        return (
            "Emergency flatten preflight planning only. No flatten, close, cancel, order, live, withdrawal, "
            "or transfer execution is available from this operation."
        )
    if operation_type == "emergency_stop_runtime":
        if after.get("actual_execution_available"):
            return "Plan emergency runtime stop through Operation authorization; it does not flatten or cancel orders."
        return (
            "Emergency stop runtime preflight planning only. No actual runtime stop is executed without an explicit "
            "safe backend adapter; it does not flatten or cancel orders."
        )
    if operation_type == "create_gated_trial_from_admission":
        return (
            "Reserve an admission-trial binding after Owner confirmation. This validates admission decision, "
            "installable constraints, risk acceptance, and account facts; it does not create a trial/campaign, "
            "install runtime constraints, or place orders."
        )
    if operation_type == "create_campaign_from_admission_binding":
        return (
            "Create a BRC campaign carrier shell from a reserved admission binding after Owner confirmation. "
            "This does not install runtime constraints, start strategy execution, or place orders."
        )
    if operation_type == "install_runtime_constraints_from_admission_campaign":
        return (
            "Install constraints metadata from an admission-created campaign after Owner confirmation. "
            "Runtime will not start, strategy will not activate, no orders will be placed, and trial remains inactive."
        )
    if operation_type == "prepare_runtime_carrier_from_admission_campaign":
        return (
            "Prepare runtime carrier readiness metadata from an admission campaign after Owner confirmation. "
            "Runtime will not start, strategy will not activate, auto execution will not be enabled, "
            "no orders will be placed, and trial remains inactive."
        )
    if operation_type == "prepare_runtime_start_from_admission_carrier":
        return (
            "Prepare runtime start readiness metadata from a carrier-ready admission campaign after Owner confirmation. "
            "Runtime will not start, strategy will not activate, auto execution will not be enabled, "
            "and no orders will be placed."
        )
    if operation_type == "evaluate_trial_trade_intent":
        return (
            "Evaluate execution-mode enforcement after Owner confirmation. This may record a non-executable "
            "trial trade intent evidence row, but it will not create an order or execution intent."
        )
    if operation_type == "prepare_runtime_handoff_from_admission_campaign":
        return (
            "Prepare runtime handoff readiness metadata from a runtime-start-ready admission campaign after Owner confirmation. "
            "Runtime will not start, runtime_started remains false, strategy will not activate, "
            "auto execution will not be enabled, and no orders will be placed."
        )
    if operation_type == "start_runtime_from_admission_handoff":
        return (
            "Start admission-backed runtime state after Owner confirmation. Strategy stays inactive, "
            "trial remains not started, auto execution stays disabled, and no orders will be placed."
        )
    if operation_type == "prepare_strategy_activation_from_admission_runtime":
        return (
            "Prepare strategy activation readiness metadata from an admission runtime after Owner confirmation. "
            "Strategy will not activate, the signal loop will not start, auto execution stays disabled, "
            "and no execution intent or order will be created."
        )
    if operation_type == "activate_strategy_from_admission_runtime":
        return (
            "Activate strategy metadata into strategy_active_no_execution after Owner confirmation. "
            "No strategy runner, signal loop, auto execution, execution intent, or order capability is enabled."
        )
    if operation_type == "prepare_signal_loop_from_admission_strategy":
        return (
            "Prepare signal loop readiness metadata from an admission strategy after Owner confirmation. "
            "Signal loop will not start, no signal will be generated, auto execution stays disabled, "
            "and no trade intent, execution intent, or order will be created."
        )
    if operation_type == "start_signal_loop_from_admission_strategy":
        return (
            "Start signal loop state metadata from an admission strategy after Owner confirmation. "
            "No signal will be generated, auto execution stays disabled, and no trade intent, "
            "execution intent, or order will be created."
        )
    if operation_type == "evaluate_signal_from_admission_strategy":
        return (
            "Evaluate and record signal metadata from an admission strategy after Owner confirmation. "
            "No trade intent, execution intent, order, trial start, or auto execution is created."
        )
    if operation_type == "record_trial_trade_intent_from_signal_evaluation":
        return (
            "Record a non-executable trial trade intent from signal evaluation after permission resolution. "
            "No execution intent, order, trial start, live enablement, or auto execution is created."
        )
    return "Operation requires Owner confirmation; no live/mainnet/withdrawal/transfer authority is granted."


def _stable_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _extract_rehearsal_refs(payload: dict[str, Any]) -> dict[str, Any]:
    workflow_run_id = _optional_str(payload.get("workflow_run_id"))
    campaign_id = _optional_str(payload.get("campaign_id"))
    audit_refs: list[dict[str, Any]] = []
    campaign_refs: list[dict[str, Any]] = []
    review_refs: list[dict[str, Any]] = []
    if workflow_run_id is not None:
        audit_refs.append({"type": "workflow_run", "ref_id": workflow_run_id})
    if campaign_id is not None:
        campaign_refs.append({"type": "campaign", "campaign_id": campaign_id, "ref_id": campaign_id})
    for step in payload.get("steps") or []:
        if not isinstance(step, dict):
            continue
        name = str(step.get("name") or "")
        step_payload = step.get("payload") if isinstance(step.get("payload"), dict) else {}
        if name == "review_decision":
            review_id = _optional_str(step_payload.get("review_id"))
            if review_id is not None:
                review_refs.append(
                    {
                        "type": "review_decision",
                        "campaign_id": campaign_id,
                        "ref_id": review_id,
                    }
                )
        if name in {"campaign_created", "finalized"}:
            step_campaign_id = _optional_str(step_payload.get("campaign_id"))
            if step_campaign_id is not None:
                campaign_refs.append(
                    {
                        "type": name,
                        "campaign_id": step_campaign_id,
                        "ref_id": step_campaign_id,
                    }
                )
    if payload.get("review_packet") is not None:
        review_refs.append({"type": "review_packet", "campaign_id": campaign_id, "ref_id": workflow_run_id})
    if payload.get("evidence") is not None:
        audit_refs.append({"type": "evidence_packet", "ref_id": workflow_run_id})
    return {
        "workflow_run_id": workflow_run_id,
        "campaign_id": campaign_id,
        "audit_refs": audit_refs,
        "campaign_refs": campaign_refs,
        "review_refs": review_refs,
    }


def _critical_market_drift(before: dict[str, Any], after: dict[str, Any]) -> bool:
    keys = ("active_position_count", "open_order_count", "all_local_flat")
    return any(before.get(key) != after.get(key) for key in keys)


def _preflight_planning_available(policy: OperationPolicy) -> bool:
    return policy.capability_status in {
        "binding_reservation_available",
        "campaign_shell_creation_available",
        "operation_preflight_available",
        "preflight_planning_available",
        "preflight_dry_run_available",
        "design_surface_with_preflight",
    }


def _records_from_summary(summary: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
    for key in keys:
        value = summary.get(key)
        if isinstance(value, list):
            return [dict(item) for item in value if isinstance(item, dict)]
    return []


def _flatten_dry_run_plan(
    *,
    operation_id: str,
    active_positions: list[dict[str, Any]],
    open_orders: list[dict[str, Any]],
    unmanaged_orders: list[dict[str, Any]],
    unmanaged_positions: list[dict[str, Any]],
    market_summary: dict[str, Any],
    warnings: list[str],
) -> dict[str, Any]:
    generated_at = now_ms()
    cancel_candidates = [
        {
            "candidate_id": f"cancel_candidate_{index + 1}",
            "candidate_type": "cancel_open_order",
            "source_order_ref": _candidate_ref(order, fallback=f"open_order_{index + 1}"),
            "symbol": order.get("symbol") or order.get("display_symbol"),
            "side": order.get("side"),
            "order_type": order.get("order_type") or order.get("type"),
            "status": order.get("status"),
            "candidate_only": True,
            "executable_order_request": False,
        }
        for index, order in enumerate(open_orders)
    ]
    close_candidates = [
        {
            "candidate_id": f"close_candidate_{index + 1}",
            "candidate_type": "close_position",
            "source_position_ref": _candidate_ref(position, fallback=f"position_{index + 1}"),
            "symbol": position.get("symbol") or position.get("display_symbol"),
            "side": position.get("side") or position.get("direction"),
            "size": position.get("size") or position.get("quantity") or position.get("amount"),
            "candidate_only": True,
            "executable_order_request": False,
        }
        for index, position in enumerate(active_positions)
    ]
    estimated_actions_count = len(cancel_candidates) + len(close_candidates)
    unsupported_reasons = [
        "actual cancel order execution is not implemented in Owner Console",
        "actual close position execution is not implemented in Owner Console",
        "actual flatten execution is not implemented in Owner Console",
        "dry-run candidates are not executable order requests",
    ]
    if unmanaged_orders:
        unsupported_reasons.append("unknown or unmanaged exchange orders require manual reconciliation before any actual flatten design")
    if unmanaged_positions:
        unsupported_reasons.append("unknown or unmanaged exchange positions require manual reconciliation before any actual flatten design")
    return {
        "dry_run_id": f"flatdry_{uuid.uuid4().hex[:16]}",
        "operation_id": operation_id,
        "generated_at_ms": generated_at,
        "dry_run_only": True,
        "actual_execution": False,
        "cancel_order_candidates": cancel_candidates,
        "close_position_candidates": close_candidates,
        "exposure_summary": {
            "source": market_summary.get("source") or market_summary.get("data_source"),
            "truth_level": market_summary.get("truth_level"),
            "reconciliation_status": _reconciliation_status_value(market_summary),
            "active_position_count": len(active_positions),
            "open_order_count": len(open_orders),
            "unknown_or_unmanaged_order_count": len(unmanaged_orders),
            "unknown_or_unmanaged_position_count": len(unmanaged_positions),
        },
        "estimated_actions_count": estimated_actions_count,
        "plan_status": "noop" if estimated_actions_count == 0 else "diagnostic_candidates",
        "blockers": [
            "actual flatten execution is unavailable by design in this phase",
        ],
        "warnings": list(warnings),
        "unsupported_reasons": unsupported_reasons,
        "required_executor_capabilities": [
            "cancel_open_orders_executor_not_present",
            "close_positions_executor_not_present",
            "final_flatness_verifier_not_present",
        ],
        "partial_failure_considerations": [
            "cancel and close sequencing is not designed in this dry-run",
            "exchange status could change after plan generation",
            "manual reconciliation is required before any future actual executor design",
        ],
    }


def _candidate_ref(record: dict[str, Any], *, fallback: str) -> str:
    value = (
        record.get("order_id")
        or record.get("exchange_order_id")
        or record.get("id")
        or record.get("position_id")
        or record.get("client_order_id")
        or record.get("clientOrderId")
    )
    return str(value or fallback)


def _reconciliation_status_value(summary: dict[str, Any]) -> str:
    reconciliation = summary.get("reconciliation_status")
    if isinstance(reconciliation, dict):
        return str(reconciliation.get("status") or "unknown")
    return str(summary.get("reconciliation_status_value") or "unknown")


def _account_facts_unavailable_reason(summary: dict[str, Any]) -> Optional[str]:
    source = summary.get("source") or summary.get("data_source")
    truth_level = summary.get("truth_level")
    if source == "unavailable" or truth_level == "unavailable":
        return "account facts unavailable; cannot safely preflight this operation"
    blockers = summary.get("blockers")
    if isinstance(blockers, list) and blockers:
        return "account facts blocked: " + "; ".join(str(item) for item in blockers)
    reconciliation = summary.get("reconciliation_status")
    reconciliation_status = (
        reconciliation.get("status")
        if isinstance(reconciliation, dict)
        else summary.get("reconciliation_status_value")
    )
    if reconciliation_status == "mismatch":
        return "account reconciliation mismatch; cannot safely preflight this operation"
    unmanaged_orders = summary.get("unknown_or_unmanaged_orders")
    unmanaged_positions = summary.get("unknown_or_unmanaged_positions")
    unknown_order_count = int(
        summary.get("unknown_or_unmanaged_order_count")
        or (len(unmanaged_orders) if isinstance(unmanaged_orders, list) else 0)
    )
    unknown_position_count = int(
        summary.get("unknown_or_unmanaged_position_count")
        or (len(unmanaged_positions) if isinstance(unmanaged_positions, list) else 0)
    )
    if unknown_order_count > 0 or unknown_position_count > 0:
        return "unknown or unmanaged exchange exposure detected; cannot safely preflight this operation"
    return None


def _runtime_state_value(summary: dict[str, Any]) -> Optional[str]:
    value = summary.get("current_runtime_state") or summary.get("runtime_state") or summary.get("status")
    return str(value).lower() if value is not None else None


def _runtime_already_stopped(state: Optional[str]) -> bool:
    return state in {"stopped", "stopped_by_owner", "emergency_stop", "hard_locked", "closed"}


_TERMINAL_STATUSES = {"executed", "blocked", "failed", "cancelled", "expired", "noop"}
_FORBIDDEN_OPERATION_TYPES = {
    "live_execution",
    "unrestricted_order_execution",
    "withdrawal",
    "transfer",
    "arbitrary_symbol_order",
    "arbitrary_strategy_router",
    "arbitrary_side_size_order",
    "llm_direct_execution",
}
