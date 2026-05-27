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
    "enter_strategy_or_monitor",
    "pause_new_entries",
    "emergency_stop_runtime",
    "emergency_flatten",
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
    review_packet_reader: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None
    runtime_transition: Optional[Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]] = None
    runtime_stop_executor: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None
    fixed_rehearsal_executor: Optional[Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = None


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

        audit_writable = (
            await self._readers.audit_writable()
            if operation_type == "emergency_stop_runtime"
            else None
        )
        decision, blockers, warnings, summary, before, after = self._preflight_decision(
            policy=policy,
            input_params=input_params,
            runtime_summary=runtime_summary,
            campaign_summary=campaign_summary,
            market_summary=market_summary,
            audit_writable=audit_writable,
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
            "risk": risk_result,
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
            result = await self._persist_result(
                operation=operation,
                preflight=preflight,
                status=status,
                blocked_reason=failure if status == "blocked" else None,
                recheck_result={"passed": False, "reason": failure},
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
        if operation.operation_type == "enter_strategy_or_monitor":
            return await self._execute_monitor_carrier_noop(operation=operation, preflight=preflight)
        if operation.operation_type == "run_fixed_testnet_rehearsal":
            return await self._execute_fixed_testnet_rehearsal(operation=operation, preflight=preflight)
        if operation.operation_type == "emergency_flatten":
            return await self._execute_emergency_flatten_dry_run(operation=operation, preflight=preflight)
        if operation.operation_type == "emergency_stop_runtime":
            return await self._execute_emergency_stop_runtime(operation=operation, preflight=preflight)
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
        return await self._persist_result(
            operation=operation,
            preflight=preflight,
            status="noop" if next_state == preflight.before.get("runtime_state") else "executed",
            recheck_result={"passed": True},
            adapter_result={"runtime_transition": transition},
            result_summary={
                "operation_type": operation.operation_type,
                "message": f"Runtime campaign state transition recorded as {next_state}. No orders were placed, closed, or cancelled.",
                "target_state": target_state,
                "next_state": next_state,
                "mutation_executed": False,
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

    def _effective_policy(self, operation_type: str) -> OperationPolicy:
        policy = self._registry.get_policy(operation_type)
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
                    "places_orders": False,
                    "closes_positions": False,
                    "cancels_orders": False,
                }
            )
            if self._readers.runtime_transition is None:
                blockers.append("runtime transition adapter unavailable")
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
        if blockers:
            return "block", blockers, warnings, "; ".join(blockers), before, after
        summary = _operation_summary(policy.operation_type, after)
        return ("warn" if warnings else "allow"), blockers, warnings, summary, before, after

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
