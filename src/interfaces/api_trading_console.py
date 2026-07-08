"""Trading Console Owner action-entry and non-mutating product API namespace."""

from __future__ import annotations

import asyncio
import os
import time
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace
from typing import Any, Literal, Optional

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from src.application.readmodels.trading_console import (
    TradingConsoleDependencies,
    TradingConsoleReadModelResponse,
    TradingConsoleReadModelService,
)
from src.domain.execution_intent import ExecutionIntent
from src.domain.experimental_runtime_profile_proposal import (
    ExperimentalRuntimeProfileProposal,
    build_experimental_runtime_profile_proposal,
)
from src.domain.runtime_execution_controlled_submit import (
    RuntimeExecutionControlledSubmitPlan,
    RuntimeExecutionControlledSubmitPreflight,
    RuntimeExecutionControlledSubmitResult,
)
from src.domain.signal_evaluation import (
    OrderCandidate,
    OrderCandidateStatus,
    SignalEvaluation,
    SignalEvaluationStatus,
)
from src.infrastructure.sync_pg_dsn import (
    is_sync_postgres_dsn,
    normalize_sync_postgres_dsn,
)
from src.domain.runtime_execution_intent_adapter import (
    RuntimeExecutionIntentCreationPreview,
    RuntimeExecutionSubmitReadiness,
)
from src.domain.runtime_execution_submit_authorization import (
    RuntimeExecutionSubmitAuthorization,
)
from src.domain.runtime_execution_submit_adapter import (
    RuntimeExecutionSubmitAdapterPreview,
)
from src.domain.runtime_execution_protection_plan import (
    RuntimeExecutionProtectionPlan,
    RuntimeExecutionProtectionPlanPreview,
)
from src.domain.runtime_execution_protection_failure_policy import (
    RuntimeExecutionProtectionFailurePolicy,
)
from src.domain.runtime_execution_submit_idempotency import (
    RuntimeExecutionSubmitIdempotencySnapshot,
)
from src.domain.runtime_execution_trusted_submit_facts import (
    RuntimeExecutionTrustedSubmitFactsSnapshot,
)
from src.domain.runtime_execution_order_lifecycle_handoff import (
    RuntimeExecutionOrderLifecycleHandoffDraft,
)
from src.domain.runtime_execution_order_lifecycle_adapter import (
    RuntimeExecutionOrderLifecycleAdapterPreview,
)
from src.domain.runtime_execution_order_registration_draft import (
    RuntimeExecutionOrderRegistrationDraftPreview,
)
from src.domain.runtime_execution_local_registration_enablement import (
    RuntimeExecutionLocalRegistrationEnablementDecision,
)
from src.domain.runtime_execution_local_registration_action_authorization import (
    RuntimeExecutionLocalRegistrationActionAuthorization,
)
from src.domain.runtime_execution_order_lifecycle_adapter_result import (
    RuntimeExecutionOrderLifecycleAdapterResult,
)
from src.domain.runtime_execution_intent_local_order_binding import (
    RuntimeExecutionIntentLocalOrderBinding,
)
from src.domain.runtime_execution_exchange_submit_preview import (
    RuntimeExecutionExchangeSubmitPreview,
)
from src.domain.runtime_execution_exchange_submit_enablement import (
    RuntimeExecutionExchangeSubmitEnablementDecision,
)
from src.domain.runtime_execution_exchange_submit_adapter_result import (
    RuntimeExecutionExchangeSubmitAdapterResult,
)
from src.domain.runtime_execution_exchange_submit_action_authorization import (
    RuntimeExecutionExchangeSubmitActionAuthorization,
)
from src.domain.standing_authorization import (
    OWNER_STANDING_AUTHORIZATION_OPERATOR_ID,
    OWNER_STANDING_AUTHORIZATION_REASON,
    OWNER_STANDING_AUTHORIZATION_REFERENCE,
)
from src.domain.runtime_execution_exchange_submit_execution_result import (
    RuntimeExecutionExchangeSubmitExecutionResult,
    RuntimeExecutionExchangeSubmitExecutionStatus,
)
from src.domain.runtime_execution_submit_outcome_review import (
    RuntimeExecutionSubmitOutcomeReview,
)
from src.domain.runtime_execution_first_real_submit_outcome_accounting import (
    RuntimeExecutionFirstRealSubmitOutcomeAccounting,
)
from src.domain.runtime_execution_post_submit_budget_settlement import (
    RuntimeExecutionPostSubmitBudgetSettlement,
)
from src.domain.runtime_execution_submit_rehearsal import (
    RuntimeExecutionSubmitRehearsal,
)
from src.domain.runtime_execution_first_real_submit_enablement_evidence import (
    RuntimeExecutionFirstRealSubmitEnablementEvidence,
)
from src.domain.runtime_executable_submit_readiness import (
    RuntimeExecutableSubmitReadinessEvidence,
    RuntimeExecutableSubmitReadinessArtifact,
)
from src.domain.runtime_official_submit_handoff import (
    RuntimeOfficialSubmitHandoffMode,
    RuntimeOfficialSubmitHandoffArtifact,
)
from src.domain.runtime_fresh_submit_authorization_resolution import (
    RuntimeFreshSubmitAuthorizationResolutionArtifact,
)
from src.domain.runtime_fresh_submit_authorization_binding import (
    RuntimeFreshSubmitAuthorizationBindingArtifact,
)
from src.domain.runtime_execution_first_real_submit_evidence_preparation import (
    RuntimeExecutionFirstRealSubmitEvidencePreparation,
)
from src.domain.runtime_execution_exchange_submit_recovery_resolution import (
    RuntimeExecutionExchangeSubmitRecoveryResolution,
)
from src.domain.runtime_execution_exchange_gateway_readiness import (
    GATEWAY_BINDING_ENABLED_ENV,
    RuntimeExecutionExchangeGatewayReadiness,
)
from src.domain.runtime_execution_attempt_reservation import (
    RuntimeExecutionAttemptReservation,
    RuntimeExecutionAttemptReservationPreview,
)
from src.domain.runtime_execution_attempt_mutation import (
    RuntimeExecutionAttemptMutation,
)
from src.domain.runtime_execution_attempt_outcome_policy import (
    RuntimeExecutionAttemptOutcomeKind,
    RuntimeExecutionAttemptOutcomePolicy,
)
from src.domain.runtime_execution_plan import RuntimeExecutionIntentDraft, RuntimeExecutionPlan
from src.domain.runtime_final_gate_preview import RuntimeFinalGatePreview
from src.domain.runtime_post_submit_finalize import RuntimePostSubmitFinalizePayload
from src.application.runtime_next_attempt_strategy_planning_service import (
    RuntimeNextAttemptStrategyPlanningArtifact,
)
from src.application.runtime_strategy_signal_scheduler_planning_service import (
    RuntimeStrategySignalSchedulerPlanningResult,
)
from src.application.runtime_strategy_signal_intent_draft_source_service import (
    RuntimeStrategySignalIntentDraftSourceArtifact,
)
from src.application.strategy_group_readonly_observation_scheduler import (
    ObservationSourceName,
    ScheduledReadonlyObservationRunResult,
    StrategyRuntimeObservationResolver,
    run_scheduled_readonly_observation_once,
)
from src.domain.strategy_family_signal import StrategyFamilySignalInput
from src.domain.strategy_runtime_promotion_gate import (
    FirstRealSubmitConfirmationFacts,
    RuntimeExecutionConfirmationFacts,
    StrategyRuntimePromotionGateResult,
    StrategyRuntimePromotionScope,
    StrategySemanticsConfirmationFacts,
)
from src.domain.runtime_live_position_monitor import RuntimeLivePositionMonitorArtifact
from src.domain.runtime_position_exit_plan import RuntimePositionExitPlan
from src.domain.runtime_post_close_followup import RuntimePostCloseFollowupArtifact
from src.domain.strategy_runtime_safety_readiness import StrategyRuntimeSafetyReadiness
from src.domain.strategy_runtime import StrategyRuntimeInstance, StrategyRuntimeInstanceStatus
from src.domain.strategy_runtime_live_enablement import (
    StrategyRuntimeLiveEnablementMutation,
    StrategyRuntimeLiveEnablementPreview,
    build_strategy_runtime_live_enablement_preview,
)
from src.interfaces.operator_auth import require_operator_session


router = APIRouter(
    prefix="/api/trading-console",
    tags=["Trading Console"],
    dependencies=[Depends(require_operator_session)],
)


class RuntimeActionTimeFinalGatePreflight(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    schema_name: str = Field(alias="schema", serialization_alias="schema")
    status: str
    controlled_submit_plan_status: str
    final_gate_verdict: str
    ticket_preflight_status: str
    ticket_id: str | None = None
    finalgate_pass_id: str | None = None
    action_time_lane_input_id: str | None = None
    strategy_group_id: str | None = None
    symbol: str | None = None
    side: str | None = None
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    next_action: str
    authority_boundary: str
    submit_executed: bool = False
    order_created: bool = False
    exchange_called: bool = False
    owner_bounded_execution_called: bool = False
    order_lifecycle_called: bool = False
    operation_layer_called: bool = False
    exchange_write_called: bool = False
    withdrawal_or_transfer_created: bool = False
    live_profile_changed: bool = False
    order_sizing_changed: bool = False


class RuntimeOperationLayerHandoff(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    schema_name: str = Field(alias="schema", serialization_alias="schema")
    status: str
    operation_layer_verdict: str
    ticket_id: str | None = None
    finalgate_pass_id: str | None = None
    operation_layer_handoff_id: str | None = None
    operation_submit_command_id: str | None = None
    action_time_lane_input_id: str | None = None
    strategy_group_id: str | None = None
    symbol: str | None = None
    side: str | None = None
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    command_plan: dict[str, Any] = Field(default_factory=dict)
    next_action: str
    authority_boundary: str
    submit_executed: bool = False
    operation_layer_submit_called: bool = False
    order_created: bool = False
    exchange_called: bool = False
    exchange_write_called: bool = False
    owner_bounded_execution_called: bool = False
    order_lifecycle_called: bool = False
    withdrawal_or_transfer_created: bool = False
    live_profile_changed: bool = False
    order_sizing_changed: bool = False


class RuntimeTicketBoundProtectedSubmit(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    schema_name: str = Field(alias="schema", serialization_alias="schema")
    status: str
    protected_submit_attempt_id: str | None = None
    ticket_id: str | None = None
    finalgate_pass_id: str | None = None
    operation_layer_handoff_id: str | None = None
    operation_submit_command_id: str | None = None
    runtime_safety_snapshot_id: str | None = None
    action_time_lane_input_id: str | None = None
    strategy_group_id: str | None = None
    symbol: str | None = None
    side: str | None = None
    submit_mode: str | None = None
    submit_allowed: bool = False
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    submit_request: dict[str, Any] = Field(default_factory=dict)
    submit_result: dict[str, Any] = Field(default_factory=dict)
    identity_evidence: dict[str, Any] = Field(default_factory=dict)
    next_action: str
    authority_boundary: str
    official_operation_layer_submit_called: bool = False
    exchange_write_called: bool = False
    order_created: bool = False
    order_lifecycle_called: bool = False
    withdrawal_or_transfer_created: bool = False
    live_profile_changed: bool = False
    order_sizing_changed: bool = False


class RuntimeTicketBoundPostSubmitClosure(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    schema_name: str = Field(alias="schema", serialization_alias="schema")
    status: str
    post_submit_closure_id: str | None = None
    protected_submit_attempt_id: str | None = None
    ticket_id: str | None = None
    operation_submit_command_id: str | None = None
    strategy_group_id: str | None = None
    symbol: str | None = None
    side: str | None = None
    protection_state: str | None = None
    reconciliation_state: str | None = None
    settlement_state: str | None = None
    review_state: str | None = None
    first_blocker: str | None = None
    blockers: list[str] = Field(default_factory=list)
    submitted_order_refs: list[dict[str, Any]] = Field(default_factory=list)
    next_action: str
    authority_boundary: str
    finalgate_called: bool = False
    operation_layer_called: bool = False
    exchange_write_called: bool = False
    order_created: bool = False
    order_lifecycle_called: bool = False
    withdrawal_or_transfer_created: bool = False
    live_profile_changed: bool = False
    order_sizing_changed: bool = False
    runtime_budget_mutated: bool = False


class _TradingConsoleLiveReadOnlyGateway:
    """Lazy, per-event-loop read-only exchange adapter for Trading Console GETs."""

    def __init__(self) -> None:
        self._gateway: Optional[Any] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def _gateway_for_current_loop(self) -> Any:
        loop = asyncio.get_running_loop()
        if self._gateway is not None and self._loop is loop and not loop.is_closed():
            return self._gateway
        if self._gateway is not None:
            await self.close()

        if not _live_read_only_exchange_env_safe():
            raise RuntimeError("trading_console_live_read_only_env_not_safe")

        from src.infrastructure.exchange_gateway import ExchangeGateway

        gateway = ExchangeGateway(
            os.environ.get("EXCHANGE_NAME", "binance"),
            os.environ["EXCHANGE_API_KEY"],
            os.environ["EXCHANGE_API_SECRET"],
            testnet=False,
        )
        await gateway.initialize()
        await gateway.check_api_key_permissions()
        self._gateway = gateway
        self._loop = loop
        return gateway

    def get_account_snapshot(self) -> Optional[Any]:
        if self._gateway is None:
            return None
        return self._gateway.get_account_snapshot()

    async def fetch_account_balance(self) -> Optional[Any]:
        gateway = await self._gateway_for_current_loop()
        return await gateway.fetch_account_balance()

    async def fetch_positions(self, symbol: Optional[str] = None) -> list[Any]:
        gateway = await self._gateway_for_current_loop()
        return await gateway.fetch_positions(symbol)

    async def fetch_open_orders(self, symbol: str, params: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
        gateway = await self._gateway_for_current_loop()
        return await gateway.fetch_open_orders(symbol, params=params)

    async def close(self) -> None:
        gateway = self._gateway
        self._gateway = None
        self._loop = None
        if gateway is not None:
            await gateway.close()


def _live_read_only_exchange_env_safe() -> bool:
    permission_max = os.environ.get("BRC_EXECUTION_PERMISSION_MAX", "").strip().lower()
    return (
        os.environ.get("TRADING_ENV") == "live"
        and os.environ.get("EXCHANGE_TESTNET", "").lower() == "false"
        and permission_max in {"read_only", "order_allowed"}
        and os.environ.get("RUNTIME_CONTROL_API_ENABLED", "").lower() == "false"
        and os.environ.get("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "").lower() == "false"
        and bool(os.environ.get("EXCHANGE_API_KEY"))
        and bool(os.environ.get("EXCHANGE_API_SECRET"))
    )


class StrategyRuntimeBoundaryView(BaseModel):
    max_attempts: int
    attempts_used: int
    attempts_remaining: int
    max_active_positions: int
    budget_reserved: str | None = None
    max_notional_per_attempt: str | None = None
    total_budget: str | None = None
    budget_remaining: str | None = None
    allowed_symbols: list[str] = Field(default_factory=list)
    allowed_sides: list[str] = Field(default_factory=list)
    max_leverage: str | None = None
    requires_protection: bool
    requires_review: bool


class StrategyRuntimeInspectionView(BaseModel):
    runtime_instance_id: str
    trial_binding_id: str
    admission_decision_id: str
    strategy_family_id: str
    strategy_family_version_id: str
    signal_evaluation_id: str | None = None
    order_candidate_id: str | None = None
    owner_risk_acceptance_id: str | None = None
    carrier_id: str | None = None
    symbol: str
    side: str
    status: StrategyRuntimeInstanceStatus
    boundary: StrategyRuntimeBoundaryView
    policy_snapshot: dict[str, Any] = Field(default_factory=dict)
    review_requirement: str
    execution_enabled: bool
    execution_mode: str
    shadow_mode: bool
    created_at_ms: int
    updated_at_ms: int
    activated_at_ms: int | None = None
    expires_at_ms: int | None = None
    revoked_at_ms: int | None = None
    closed_at_ms: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeStrategySignalShadowPlanningRequest(BaseModel):
    signal_input: StrategyFamilySignalInput
    allow_shadow_candidate_creation: bool = False
    allow_live_runtime_handoff_prepare: bool = False
    candidate_id: str | None = None
    context_id: str | None = None
    expires_at_ms: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeStrategySignalIntentDraftSourceRequest(BaseModel):
    signal_input: StrategyFamilySignalInput
    allow_shadow_candidate_creation: Literal[True] = True
    allow_intent_draft_creation: Literal[True] = True
    allow_live_runtime_handoff_prepare: bool = False
    owner_reviewed: Literal[True] = True
    owner_confirmed_for_intent: Literal[True] = True
    candidate_id: str | None = None
    context_id: str | None = None
    expires_at_ms: int | None = Field(default=None, ge=0)
    active_positions_count: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)
    non_executing: Literal[True] = True


class RuntimeNextAttemptStrategyPlanningRequest(BaseModel):
    post_submit_finalize_payload: RuntimePostSubmitFinalizePayload
    signal_input: StrategyFamilySignalInput
    context_id: str | None = None
    expires_at_ms: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)
    non_executing: Literal[True] = True


class RuntimePostSubmitFinalizeRequest(BaseModel):
    authorization_id: str | None = Field(default=None, min_length=1, max_length=220)
    reservation_id: str | None = Field(default=None, min_length=1, max_length=260)
    closed_review_required: bool = False
    protection_blockers: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    non_executing: Literal[True] = True


class RuntimeExecutableSubmitReadinessPreviewRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    strategy_planning_artifact: RuntimeNextAttemptStrategyPlanningArtifact = Field(
        validation_alias=AliasChoices(
            "strategy_planning_artifact",
        )
    )
    evidence: RuntimeExecutableSubmitReadinessEvidence
    first_real_submit_evidence: (
        RuntimeExecutionFirstRealSubmitEnablementEvidence | None
    ) = None
    additional_blockers: list[str] = Field(default_factory=list)
    additional_warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    non_executing: Literal[True] = True


class RuntimePersistedDraftSourceReadinessPreviewRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    intent_draft_source_artifact: RuntimeStrategySignalIntentDraftSourceArtifact
    evidence: RuntimeExecutableSubmitReadinessEvidence
    first_real_submit_evidence: (
        RuntimeExecutionFirstRealSubmitEnablementEvidence | None
    ) = None
    additional_blockers: list[str] = Field(default_factory=list)
    additional_warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    non_executing: Literal[True] = True


class RuntimeOfficialSubmitHandoffPreviewRequest(BaseModel):
    readiness_artifact: RuntimeExecutableSubmitReadinessArtifact
    fresh_submit_authorization_id: str | None = Field(
        default=None,
        max_length=260,
    )
    mode: RuntimeOfficialSubmitHandoffMode = (
        RuntimeOfficialSubmitHandoffMode.DISABLED_SMOKE
    )
    owner_confirmed_for_real_submit_action: bool = True
    additional_blockers: list[str] = Field(default_factory=list)
    additional_warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    non_executing: Literal[True] = True


class RuntimeFreshSubmitAuthorizationResolutionRequest(BaseModel):
    handoff_artifact: RuntimeOfficialSubmitHandoffArtifact
    requested_fresh_submit_authorization_id: str | None = Field(
        default=None,
        max_length=260,
    )
    additional_blockers: list[str] = Field(default_factory=list)
    additional_warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    non_executing: Literal[True] = True


class RuntimeFreshSubmitAuthorizationBindingRequest(BaseModel):
    handoff_artifact: RuntimeOfficialSubmitHandoffArtifact
    requested_fresh_submit_authorization_id: str | None = Field(
        default=None,
        max_length=260,
    )
    allow_create_from_existing_intent: bool = True
    allow_create_intent_from_latest_draft: bool = True
    additional_blockers: list[str] = Field(default_factory=list)
    additional_warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    no_exchange_side_effects: Literal[True] = True


class StrategyRuntimeLiveEnablementMutationRequest(BaseModel):
    preview: StrategyRuntimeLiveEnablementPreview
    owner_live_runtime_enablement_authorization_id: str = Field(
        min_length=1,
        max_length=180,
    )
    owner_real_submit_authorization_id: str = Field(
        min_length=1,
        max_length=180,
    )
    actor: str = Field(default="owner", min_length=1, max_length=128)


class ScheduledReadonlyObservationRunRequest(BaseModel):
    source_name: ObservationSourceName = "live_market"
    shadow_plan: bool = False
    allow_shadow_candidate_creation: bool = False
    non_executing: Literal[True] = True


class RuntimeNextAttemptObservationCycleRequest(BaseModel):
    source: Literal["live_market", "sample"] = "live_market"
    include_exchange: bool = True
    allow_action_time_ticket_materialization: bool = False
    symbol: str | None = None
    side: str | None = None
    family: str | None = None
    strategy_family_id: str | None = None
    carrier_id: str | None = None
    quantity: str | None = None
    target_notional_usdt: str | None = None
    max_notional: str | None = None
    leverage: str | None = None
    max_attempts: int | None = Field(default=None, ge=1, le=10)
    protection_mode: str | None = None
    review_requirement: str | None = None
    evaluation_id: str | None = None
    playbook_id: str | None = None
    one_hour_limit: int = Field(default=25, ge=5, le=200)
    four_hour_limit: int = Field(default=25, ge=2, le=100)
    timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    non_executing: Literal[True] = True


class SignalEvaluationInspectionView(BaseModel):
    signal_evaluation_id: str
    runtime_instance_id: str | None = None
    trial_binding_id: str | None = None
    strategy_family_id: str | None = None
    strategy_family_version_id: str | None = None
    source_signal_id: str | None = None
    symbol: str
    side: str
    status: SignalEvaluationStatus
    signal_observation_result: str
    reason_codes: list[str] = Field(default_factory=list)
    rationale: str
    evidence_snapshot: dict[str, Any] = Field(default_factory=dict)
    policy_snapshot: dict[str, Any] = Field(default_factory=dict)
    evaluated_at_ms: int
    expires_at_ms: int | None = None
    shadow_mode: bool
    execution_enabled: bool
    not_order: bool
    not_execution_intent: bool
    created_at_ms: int
    updated_at_ms: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class OrderCandidateInspectionView(BaseModel):
    order_candidate_id: str
    signal_evaluation_id: str
    runtime_instance_id: str | None = None
    trial_binding_id: str | None = None
    strategy_family_id: str | None = None
    strategy_family_version_id: str | None = None
    symbol: str
    side: str
    status: OrderCandidateStatus
    candidate_order_type: str
    proposed_quantity: str | None = None
    intended_notional: str | None = None
    entry_price_reference: str | None = None
    risk_preview: dict[str, Any] = Field(default_factory=dict)
    protection_preview: dict[str, Any] = Field(default_factory=dict)
    rationale: str
    evidence_refs: list[str] = Field(default_factory=list)
    shadow_mode: bool
    execution_enabled: bool
    candidate_executable: bool
    not_order: bool
    not_execution_intent: bool
    execution_intent_id: str | None = None
    execution_intent_status: str | None = None
    submit_authorization_id: str | None = None
    submit_authorization_status: str | None = None
    candidate_usage_status: str = "usage_lookup_unavailable"
    candidate_reusable_for_new_attempt: bool = False
    reuse_blocker: str | None = None
    created_at_ms: int
    updated_at_ms: int
    expires_at_ms: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.get("/dashboard-state", response_model=TradingConsoleReadModelResponse)
async def dashboard_state(
    symbol: Optional[str] = Query(default=None),
    include_exchange: bool = Query(default=False),
) -> TradingConsoleReadModelResponse:
    return await _service(include_exchange=include_exchange).dashboard_state(
        symbol=symbol,
        include_exchange=include_exchange,
    )


@router.get(
    "/strategy-runtimes",
    response_model=list[StrategyRuntimeInspectionView],
)
async def list_strategy_runtimes(
    status: Optional[StrategyRuntimeInstanceStatus] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[StrategyRuntimeInspectionView]:
    service = await _strategy_runtime_service()
    runtimes = await service.list_runtimes(status=status, limit=limit)
    return [_runtime_view(runtime) for runtime in runtimes]


@router.get(
    "/strategy-runtimes/{runtime_instance_id}",
    response_model=StrategyRuntimeInspectionView,
)
async def get_strategy_runtime(
    runtime_instance_id: str,
) -> StrategyRuntimeInspectionView:
    service = await _strategy_runtime_service()
    try:
        return _runtime_view(await service.get_runtime(runtime_instance_id))
    except Exception as exc:
        message = str(exc)
        if "not found" in message:
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.get(
    "/strategy-runtimes/{runtime_instance_id}/promotion-gate",
    response_model=StrategyRuntimePromotionGateResult,
)
async def runtime_strategy_promotion_gate_preview_for_runtime(
    runtime_instance_id: str,
    scope: StrategyRuntimePromotionScope = (
        StrategyRuntimePromotionScope.CONTROLLED_RUNTIME_EXECUTION
    ),
    strategy_family_confirmed: bool = False,
    implementation_source_confirmed: bool = False,
    required_facts_confirmed: bool = False,
    entry_policy_confirmed: bool = False,
    exit_policy_confirmed: bool = False,
    protection_policy_confirmed: bool = False,
    eligible_for_runtime_execution_confirmed: bool = False,
    right_tail_review_metrics_confirmed: bool = False,
    runtime_profile_confirmed: bool = False,
    owner_confirmation_mode_confirmed: bool = False,
    symbol_side_boundary_confirmed: bool = False,
    max_loss_budget_confirmed: bool = False,
    max_notional_boundary_confirmed: bool = False,
    max_active_positions_boundary_confirmed: bool = False,
    max_leverage_boundary_confirmed: bool = False,
    margin_usage_boundary_confirmed: bool = False,
    liquidation_buffer_boundary_confirmed: bool = False,
    protection_readiness_source_confirmed: bool = False,
    stale_fact_behavior_confirmed: bool = False,
    attempt_consumption_rule_confirmed: bool = False,
    budget_reservation_rule_confirmed: bool = False,
    trusted_active_position_source_confirmed: bool = False,
    trusted_account_fact_source_confirmed: bool = False,
    short_side_conservative_profile_confirmed: bool = False,
    budget_release_or_consume_rule_confirmed: bool = False,
    post_submit_budget_settlement_persistence_evidence_id: Optional[str] = None,
    attempt_outcome_policy_id: Optional[str] = None,
    protection_creation_failure_policy_confirmed: bool = False,
    protection_creation_failure_policy_id: Optional[str] = None,
    duplicate_submit_policy_confirmed: bool = False,
    submit_idempotency_policy_id: Optional[str] = None,
    trusted_submit_fact_snapshot_id: Optional[str] = None,
    local_registration_enablement_decision_id: Optional[str] = None,
    exchange_submit_enablement_decision_id: Optional[str] = None,
    exchange_submit_execution_result_id: Optional[str] = None,
    runtime_submit_rehearsal_id: Optional[str] = None,
    deployment_readiness_evidence_id: Optional[str] = None,
    owner_real_submit_authorization_id: Optional[str] = None,
    deployment_readiness_confirmed: bool = False,
    explicit_owner_real_submit_authorization: bool = False,
) -> StrategyRuntimePromotionGateResult:
    runtime_service = await _strategy_runtime_service()
    try:
        runtime = await runtime_service.get_runtime(runtime_instance_id)
    except Exception as exc:
        message = str(exc)
        if "not found" in message:
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc
    return await runtime_strategy_promotion_gate_preview(
        strategy_family_id=runtime.strategy_family_id,
        strategy_family_version_id=runtime.strategy_family_version_id,
        scope=scope,
        strategy_family_confirmed=strategy_family_confirmed,
        implementation_source_confirmed=implementation_source_confirmed,
        required_facts_confirmed=required_facts_confirmed,
        entry_policy_confirmed=entry_policy_confirmed,
        exit_policy_confirmed=exit_policy_confirmed,
        protection_policy_confirmed=protection_policy_confirmed,
        eligible_for_runtime_execution_confirmed=(
            eligible_for_runtime_execution_confirmed
        ),
        right_tail_review_metrics_confirmed=right_tail_review_metrics_confirmed,
        runtime_profile_confirmed=runtime_profile_confirmed,
        owner_confirmation_mode_confirmed=owner_confirmation_mode_confirmed,
        symbol_side_boundary_confirmed=symbol_side_boundary_confirmed,
        max_loss_budget_confirmed=max_loss_budget_confirmed,
        max_notional_boundary_confirmed=max_notional_boundary_confirmed,
        max_active_positions_boundary_confirmed=(
            max_active_positions_boundary_confirmed
        ),
        max_leverage_boundary_confirmed=max_leverage_boundary_confirmed,
        margin_usage_boundary_confirmed=margin_usage_boundary_confirmed,
        liquidation_buffer_boundary_confirmed=liquidation_buffer_boundary_confirmed,
        protection_readiness_source_confirmed=(
            protection_readiness_source_confirmed
        ),
        stale_fact_behavior_confirmed=stale_fact_behavior_confirmed,
        attempt_consumption_rule_confirmed=attempt_consumption_rule_confirmed,
        budget_reservation_rule_confirmed=budget_reservation_rule_confirmed,
        trusted_active_position_source_confirmed=(
            trusted_active_position_source_confirmed
        ),
        trusted_account_fact_source_confirmed=trusted_account_fact_source_confirmed,
        short_side_conservative_profile_confirmed=(
            short_side_conservative_profile_confirmed
        ),
        budget_release_or_consume_rule_confirmed=(
            budget_release_or_consume_rule_confirmed
        ),
        post_submit_budget_settlement_persistence_evidence_id=(
            post_submit_budget_settlement_persistence_evidence_id
        ),
        attempt_outcome_policy_id=attempt_outcome_policy_id,
        protection_creation_failure_policy_confirmed=(
            protection_creation_failure_policy_confirmed
        ),
        protection_creation_failure_policy_id=protection_creation_failure_policy_id,
        duplicate_submit_policy_confirmed=duplicate_submit_policy_confirmed,
        submit_idempotency_policy_id=submit_idempotency_policy_id,
        trusted_submit_fact_snapshot_id=trusted_submit_fact_snapshot_id,
        local_registration_enablement_decision_id=(
            local_registration_enablement_decision_id
        ),
        exchange_submit_enablement_decision_id=(
            exchange_submit_enablement_decision_id
        ),
        exchange_submit_execution_result_id=exchange_submit_execution_result_id,
        runtime_submit_rehearsal_id=runtime_submit_rehearsal_id,
        deployment_readiness_evidence_id=deployment_readiness_evidence_id,
        owner_real_submit_authorization_id=owner_real_submit_authorization_id,
        deployment_readiness_confirmed=deployment_readiness_confirmed,
        explicit_owner_real_submit_authorization=(
            explicit_owner_real_submit_authorization
        ),
    )


@router.get(
    "/strategy-runtimes/{runtime_instance_id}/safety-readiness",
    response_model=StrategyRuntimeSafetyReadiness,
)
async def runtime_strategy_safety_readiness_preview(
    runtime_instance_id: str,
) -> StrategyRuntimeSafetyReadiness:
    try:
        from src.application.strategy_runtime_safety_readiness_service import (
            StrategyRuntimeSafetyReadinessService,
        )

        service = StrategyRuntimeSafetyReadinessService(
            runtime_service=await _strategy_runtime_service(),
        )
        return await service.preview(runtime_instance_id=runtime_instance_id)
    except Exception as exc:
        message = str(exc)
        if "not found" in message:
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.get(
    "/strategy-runtimes/{runtime_instance_id}/live-enablement-preview",
    response_model=StrategyRuntimeLiveEnablementPreview,
)
async def runtime_strategy_live_enablement_preview(
    runtime_instance_id: str,
    strategy_family_confirmed: bool = False,
    implementation_source_confirmed: bool = False,
    required_facts_confirmed: bool = False,
    entry_policy_confirmed: bool = False,
    exit_policy_confirmed: bool = False,
    protection_policy_confirmed: bool = False,
    eligible_for_runtime_execution_confirmed: bool = False,
    right_tail_review_metrics_confirmed: bool = False,
    runtime_profile_confirmed: bool = False,
    owner_confirmation_mode_confirmed: bool = False,
    symbol_side_boundary_confirmed: bool = False,
    max_loss_budget_confirmed: bool = False,
    max_notional_boundary_confirmed: bool = False,
    max_active_positions_boundary_confirmed: bool = False,
    max_leverage_boundary_confirmed: bool = False,
    margin_usage_boundary_confirmed: bool = False,
    liquidation_buffer_boundary_confirmed: bool = False,
    protection_readiness_source_confirmed: bool = False,
    stale_fact_behavior_confirmed: bool = False,
    attempt_consumption_rule_confirmed: bool = False,
    budget_reservation_rule_confirmed: bool = False,
    trusted_active_position_source_confirmed: bool = False,
    trusted_account_fact_source_confirmed: bool = False,
    short_side_conservative_profile_confirmed: bool = False,
    budget_release_or_consume_rule_confirmed: bool = False,
    post_submit_budget_settlement_persistence_evidence_id: Optional[str] = None,
    attempt_outcome_policy_id: Optional[str] = None,
    protection_creation_failure_policy_confirmed: bool = False,
    protection_creation_failure_policy_id: Optional[str] = None,
    duplicate_submit_policy_confirmed: bool = False,
    submit_idempotency_policy_id: Optional[str] = None,
    trusted_submit_fact_snapshot_id: Optional[str] = None,
    local_registration_enablement_decision_id: Optional[str] = None,
    exchange_submit_enablement_decision_id: Optional[str] = None,
    exchange_submit_execution_result_id: Optional[str] = None,
    runtime_submit_rehearsal_id: Optional[str] = None,
    deployment_readiness_evidence_id: Optional[str] = None,
    owner_real_submit_authorization_id: Optional[str] = None,
    deployment_readiness_confirmed: bool = False,
    explicit_owner_real_submit_authorization: bool = False,
    current_head_deployed: bool = False,
    owner_live_runtime_enablement_authorized: bool = False,
    owner_real_submit_authorization_present: bool = False,
    submit_technical_rehearsal_passed: bool = False,
    submit_adapter_implemented: bool = False,
    staged_submit_chain_available: bool = False,
    forbidden_execution_flags: Optional[list[str]] = None,
) -> StrategyRuntimeLiveEnablementPreview:
    runtime_service = await _strategy_runtime_service()
    try:
        runtime = await runtime_service.get_runtime(runtime_instance_id)
    except Exception as exc:
        message = str(exc)
        if "not found" in message:
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc

    safety_readiness = await runtime_strategy_safety_readiness_preview(
        runtime_instance_id=runtime_instance_id,
    )
    promotion_gate_result = await runtime_strategy_promotion_gate_preview_for_runtime(
        runtime_instance_id=runtime_instance_id,
        scope=StrategyRuntimePromotionScope.FIRST_REAL_SUBMIT_GATE_REVIEW,
        strategy_family_confirmed=strategy_family_confirmed,
        implementation_source_confirmed=implementation_source_confirmed,
        required_facts_confirmed=required_facts_confirmed,
        entry_policy_confirmed=entry_policy_confirmed,
        exit_policy_confirmed=exit_policy_confirmed,
        protection_policy_confirmed=protection_policy_confirmed,
        eligible_for_runtime_execution_confirmed=(
            eligible_for_runtime_execution_confirmed
        ),
        right_tail_review_metrics_confirmed=right_tail_review_metrics_confirmed,
        runtime_profile_confirmed=runtime_profile_confirmed,
        owner_confirmation_mode_confirmed=owner_confirmation_mode_confirmed,
        symbol_side_boundary_confirmed=symbol_side_boundary_confirmed,
        max_loss_budget_confirmed=max_loss_budget_confirmed,
        max_notional_boundary_confirmed=max_notional_boundary_confirmed,
        max_active_positions_boundary_confirmed=(
            max_active_positions_boundary_confirmed
        ),
        max_leverage_boundary_confirmed=max_leverage_boundary_confirmed,
        margin_usage_boundary_confirmed=margin_usage_boundary_confirmed,
        liquidation_buffer_boundary_confirmed=liquidation_buffer_boundary_confirmed,
        protection_readiness_source_confirmed=(
            protection_readiness_source_confirmed
        ),
        stale_fact_behavior_confirmed=stale_fact_behavior_confirmed,
        attempt_consumption_rule_confirmed=attempt_consumption_rule_confirmed,
        budget_reservation_rule_confirmed=budget_reservation_rule_confirmed,
        trusted_active_position_source_confirmed=(
            trusted_active_position_source_confirmed
        ),
        trusted_account_fact_source_confirmed=trusted_account_fact_source_confirmed,
        short_side_conservative_profile_confirmed=(
            short_side_conservative_profile_confirmed
        ),
        budget_release_or_consume_rule_confirmed=(
            budget_release_or_consume_rule_confirmed
        ),
        post_submit_budget_settlement_persistence_evidence_id=(
            post_submit_budget_settlement_persistence_evidence_id
        ),
        attempt_outcome_policy_id=attempt_outcome_policy_id,
        protection_creation_failure_policy_confirmed=(
            protection_creation_failure_policy_confirmed
        ),
        protection_creation_failure_policy_id=protection_creation_failure_policy_id,
        duplicate_submit_policy_confirmed=duplicate_submit_policy_confirmed,
        submit_idempotency_policy_id=submit_idempotency_policy_id,
        trusted_submit_fact_snapshot_id=trusted_submit_fact_snapshot_id,
        local_registration_enablement_decision_id=(
            local_registration_enablement_decision_id
        ),
        exchange_submit_enablement_decision_id=(
            exchange_submit_enablement_decision_id
        ),
        exchange_submit_execution_result_id=exchange_submit_execution_result_id,
        runtime_submit_rehearsal_id=runtime_submit_rehearsal_id,
        deployment_readiness_evidence_id=deployment_readiness_evidence_id,
        owner_real_submit_authorization_id=owner_real_submit_authorization_id,
        deployment_readiness_confirmed=deployment_readiness_confirmed,
        explicit_owner_real_submit_authorization=(
            explicit_owner_real_submit_authorization
        ),
    )
    (
        execution_result_proves_submit,
        execution_result_blockers,
        execution_result_warnings,
    ) = await _validate_exchange_submit_execution_result_proof(
        runtime_instance_id=runtime_instance_id,
        exchange_submit_execution_result_id=exchange_submit_execution_result_id,
    )
    return build_strategy_runtime_live_enablement_preview(
        runtime=runtime,
        safety_readiness=safety_readiness,
        promotion_gate_result=promotion_gate_result,
        current_head_deployed=current_head_deployed,
        owner_live_runtime_enablement_authorized=(
            owner_live_runtime_enablement_authorized
        ),
        owner_real_submit_authorization_present=(
            owner_real_submit_authorization_present
        ),
        submit_technical_rehearsal_passed=(
            submit_technical_rehearsal_passed or execution_result_proves_submit
        ),
        submit_adapter_implemented=submit_adapter_implemented,
        staged_submit_chain_available=staged_submit_chain_available,
        forbidden_execution_flags=forbidden_execution_flags or [],
        additional_blockers=execution_result_blockers,
        additional_warnings=execution_result_warnings,
    )


@router.get(
    "/strategy-runtimes/{runtime_instance_id}/live-position-monitor",
    response_model=RuntimeLivePositionMonitorArtifact,
)
async def runtime_live_position_monitor(
    runtime_instance_id: str,
) -> RuntimeLivePositionMonitorArtifact:
    try:
        service = await _runtime_live_position_monitor_service()
        return await service.build_monitor_artifact(
            runtime_instance_id=runtime_instance_id,
        )
    except HTTPException:
        raise
    except Exception as exc:
        message = str(exc)
        if "not found" in message:
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.get(
    "/strategy-runtimes/{runtime_instance_id}/active-position-exit-plan",
    response_model=RuntimePositionExitPlan,
)
async def runtime_active_position_exit_plan(
    runtime_instance_id: str,
) -> RuntimePositionExitPlan:
    try:
        service = await _runtime_position_exit_plan_service()
        return await service.build_exit_plan(
            runtime_instance_id=runtime_instance_id,
        )
    except HTTPException:
        raise
    except Exception as exc:
        message = str(exc)
        if "not found" in message:
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.get(
    "/strategy-runtimes/{runtime_instance_id}/post-close-follow-up",
)
async def runtime_post_close_follow_up(
    runtime_instance_id: str,
) -> dict[str, Any]:
    try:
        return await _runtime_post_close_followup_payload(
            runtime_instance_id=runtime_instance_id,
            env_file=None,
        )
    except HTTPException:
        raise
    except Exception as exc:
        message = str(exc)
        if "not found" in message:
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.get(
    "/strategy-runtime-profile-proposals",
    response_model=ExperimentalRuntimeProfileProposal,
)
async def experimental_runtime_profile_proposal_preview(
    strategy_family_id: str = Query(..., min_length=1, max_length=128),
    strategy_family_version_id: str = Query(..., min_length=1, max_length=128),
    symbol: str = Query(default="BNB/USDT:USDT", min_length=1, max_length=128),
    side: str = Query(default="long", min_length=1, max_length=32),
    capital_base: Decimal = Query(default=Decimal("30"), gt=Decimal("0")),
) -> ExperimentalRuntimeProfileProposal:
    return build_experimental_runtime_profile_proposal(
        strategy_family_id=strategy_family_id,
        strategy_family_version_id=strategy_family_version_id,
        symbol=symbol,
        side=side,
        capital_base=capital_base,
    )


@router.post(
    "/strategy-runtimes/{runtime_instance_id}/strategy-signal-shadow-plans",
    response_model=RuntimeStrategySignalSchedulerPlanningResult,
)
async def runtime_strategy_signal_shadow_plan_for_signal_input(
    runtime_instance_id: str,
    request: RuntimeStrategySignalShadowPlanningRequest,
) -> RuntimeStrategySignalSchedulerPlanningResult:
    runtime_service = await _strategy_runtime_service()
    try:
        runtime = await runtime_service.get_runtime(runtime_instance_id)
    except Exception as exc:
        message = str(exc)
        if "not found" in message:
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc

    service = await _runtime_strategy_signal_scheduler_planning_service()
    try:
        return await service.plan_signal_input_if_ready(
            request.signal_input,
            runtime=runtime,
            candidate_id=request.candidate_id,
            allow_shadow_candidate_creation=request.allow_shadow_candidate_creation,
            allow_live_runtime_handoff_prepare=(
                request.allow_live_runtime_handoff_prepare
            ),
            context_id=request.context_id,
            expires_at_ms=request.expires_at_ms,
            metadata={
                "trading_console_api": True,
                "runtime_instance_id": runtime_instance_id,
                **request.metadata,
            },
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.post(
    "/strategy-runtimes/{runtime_instance_id}/strategy-signal-intent-draft-sources",
    response_model=RuntimeStrategySignalIntentDraftSourceArtifact,
)
async def runtime_strategy_signal_intent_draft_source_for_signal_input(
    runtime_instance_id: str,
    request: RuntimeStrategySignalIntentDraftSourceRequest,
) -> RuntimeStrategySignalIntentDraftSourceArtifact:
    runtime_service = await _strategy_runtime_service()
    try:
        runtime = await runtime_service.get_runtime(runtime_instance_id)
    except Exception as exc:
        message = str(exc)
        if "not found" in message:
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc
    if runtime.runtime_instance_id != runtime_instance_id:
        raise HTTPException(
            status_code=400,
            detail="runtime_instance_id_mismatch",
        )

    service = await _runtime_strategy_signal_intent_draft_source_service()
    try:
        return await service.record_ready_intent_draft_source(
            request.signal_input,
            runtime=runtime,
            allow_shadow_candidate_creation=request.allow_shadow_candidate_creation,
            allow_intent_draft_creation=request.allow_intent_draft_creation,
            allow_live_runtime_handoff_prepare=(
                request.allow_live_runtime_handoff_prepare
            ),
            owner_reviewed=request.owner_reviewed,
            owner_confirmed_for_intent=request.owner_confirmed_for_intent,
            candidate_id=request.candidate_id,
            context_id=request.context_id,
            expires_at_ms=request.expires_at_ms,
            active_positions_count=request.active_positions_count,
            metadata={
                "trading_console_api": True,
                "runtime_instance_id": runtime_instance_id,
                "non_executing": True,
                **request.metadata,
            },
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.post(
    "/strategy-runtimes/{runtime_instance_id}/live-enablement-mutations",
    response_model=StrategyRuntimeLiveEnablementMutation,
)
async def apply_strategy_runtime_live_enablement_mutation(
    runtime_instance_id: str,
    request: StrategyRuntimeLiveEnablementMutationRequest,
) -> StrategyRuntimeLiveEnablementMutation:
    service = await _strategy_runtime_service()
    try:
        return await service.enable_live_runtime_from_preview(
            runtime_instance_id,
            preview=request.preview,
            owner_live_runtime_enablement_authorization_id=(
                request.owner_live_runtime_enablement_authorization_id
            ),
            owner_real_submit_authorization_id=(
                request.owner_real_submit_authorization_id
            ),
            actor=request.actor,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.post(
    "/strategy-runtimes/{runtime_instance_id}/post-submit-finalize-payloads",
    response_model=RuntimePostSubmitFinalizePayload,
)
async def runtime_post_submit_finalize_payload_for_runtime(
    runtime_instance_id: str,
    request: RuntimePostSubmitFinalizeRequest,
) -> RuntimePostSubmitFinalizePayload:
    service = await _runtime_post_submit_finalize_service()
    result = await _runtime_exchange_submit_execution_result_for_finalize(
        runtime_instance_id=runtime_instance_id,
        authorization_id=request.authorization_id,
    )
    active_positions_count = await _runtime_active_positions_count_for_submit_result(
        result,
        expected_runtime_instance_id=runtime_instance_id,
    )
    try:
        if request.authorization_id:
            return await service.finalize_authorization(
                request.authorization_id,
                reservation_id=request.reservation_id,
                active_positions_count=active_positions_count,
                expected_runtime_instance_id=runtime_instance_id,
                closed_review_required=request.closed_review_required,
                protection_blockers=request.protection_blockers,
            )
        return await service.finalize_latest_for_runtime(
            runtime_instance_id,
            reservation_id=request.reservation_id,
            active_positions_count=active_positions_count,
            closed_review_required=request.closed_review_required,
            protection_blockers=request.protection_blockers,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.post(
    "/strategy-runtimes/{runtime_instance_id}/next-attempt-strategy-plans",
    response_model=RuntimeNextAttemptStrategyPlanningArtifact,
)
async def runtime_next_attempt_strategy_plan_from_post_submit_payload(
    runtime_instance_id: str,
    request: RuntimeNextAttemptStrategyPlanningRequest,
) -> RuntimeNextAttemptStrategyPlanningArtifact:
    runtime_service = await _strategy_runtime_service()
    try:
        runtime = await runtime_service.get_runtime(runtime_instance_id)
    except Exception as exc:
        message = str(exc)
        if "not found" in message:
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc

    service = await _runtime_next_attempt_strategy_planning_service()
    try:
        return await service.plan_from_post_submit_gate(
            post_submit_finalize_payload=request.post_submit_finalize_payload,
            signal_input=request.signal_input,
            runtime=runtime,
            context_id=request.context_id,
            expires_at_ms=request.expires_at_ms,
            metadata={
                "trading_console_api": True,
                "runtime_instance_id": runtime_instance_id,
                "non_executing": True,
                **request.metadata,
            },
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.post(
    "/strategy-observations/scheduled-runs",
    response_model=ScheduledReadonlyObservationRunResult,
)
async def run_scheduled_strategy_observation(
    request: ScheduledReadonlyObservationRunRequest,
) -> ScheduledReadonlyObservationRunResult:
    if request.allow_shadow_candidate_creation and not request.shadow_plan:
        raise HTTPException(
            status_code=400,
            detail="allow_shadow_candidate_creation requires shadow_plan=true",
        )

    kwargs: dict[str, Any] = {"source_name": request.source_name}
    if request.shadow_plan:
        kwargs.update(
            {
                "runtime_resolver": StrategyRuntimeObservationResolver(
                    runtime_service=await _strategy_runtime_service(),
                ),
                "runtime_signal_planning_service": (
                    await _runtime_strategy_signal_scheduler_planning_service()
                ),
                "allow_shadow_candidate_creation": (
                    request.allow_shadow_candidate_creation
                ),
            }
        )
    try:
        return await run_scheduled_readonly_observation_once(**kwargs)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/strategy-runtimes/{runtime_instance_id}/next-attempt-observation-cycle",
)
async def runtime_next_attempt_observation_cycle(
    runtime_instance_id: str,
    request: RuntimeNextAttemptObservationCycleRequest,
) -> dict[str, Any]:
    if request.allow_action_time_ticket_materialization:
        raise HTTPException(
            status_code=400,
            detail=(
                "next-attempt observation API is non-executing; materialize "
                "PG promotion candidates and Action-Time Ticket after "
                "ready_for_action_time_ticket_materialization"
            ),
        )
    try:
        return await _runtime_next_attempt_observation_cycle_payload(
            runtime_instance_id=runtime_instance_id,
            request=request,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.post(
    "/strategy-runtimes/{runtime_instance_id}/executable-submit-readiness-previews",
    response_model=RuntimeExecutableSubmitReadinessArtifact,
)
async def runtime_executable_submit_readiness_preview(
    runtime_instance_id: str,
    request: RuntimeExecutableSubmitReadinessPreviewRequest,
) -> RuntimeExecutableSubmitReadinessArtifact:
    if request.strategy_planning_artifact.runtime_instance_id != runtime_instance_id:
        raise HTTPException(
            status_code=400,
            detail="strategy_planning_artifact_runtime_mismatch",
        )
    from src.application.runtime_executable_submit_readiness_service import (
        RuntimeExecutableSubmitReadinessService,
    )

    service = RuntimeExecutableSubmitReadinessService()
    try:
        return await service.preview_from_strategy_planning_artifact(
            strategy_planning_artifact=request.strategy_planning_artifact,
            evidence=request.evidence,
            first_real_submit_evidence=request.first_real_submit_evidence,
            additional_blockers=request.additional_blockers,
            additional_warnings=[
                *request.additional_warnings,
                "trading_console_api_non_executing_preview",
            ],
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/strategy-runtimes/{runtime_instance_id}/persisted-draft-source-readiness-previews",
    response_model=RuntimeExecutableSubmitReadinessArtifact,
)
async def runtime_persisted_draft_source_readiness_preview(
    runtime_instance_id: str,
    request: RuntimePersistedDraftSourceReadinessPreviewRequest,
) -> RuntimeExecutableSubmitReadinessArtifact:
    if request.intent_draft_source_artifact.runtime_instance_id != runtime_instance_id:
        raise HTTPException(
            status_code=400,
            detail="intent_draft_source_artifact_runtime_mismatch",
        )
    from src.application.runtime_persisted_draft_source_readiness_adapter_service import (
        RuntimePersistedDraftSourceReadinessAdapterService,
    )

    service = RuntimePersistedDraftSourceReadinessAdapterService()
    try:
        return await service.preview_from_intent_draft_source(
            intent_draft_source_artifact=request.intent_draft_source_artifact,
            evidence=request.evidence,
            first_real_submit_evidence=request.first_real_submit_evidence,
            additional_blockers=request.additional_blockers,
            additional_warnings=[
                *request.additional_warnings,
                "trading_console_api_non_executing_persisted_draft_source_readiness_preview",
            ],
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/strategy-runtimes/{runtime_instance_id}/official-submit-handoff-previews",
    response_model=RuntimeOfficialSubmitHandoffArtifact,
)
async def runtime_official_submit_handoff_preview(
    runtime_instance_id: str,
    request: RuntimeOfficialSubmitHandoffPreviewRequest,
) -> RuntimeOfficialSubmitHandoffArtifact:
    if request.readiness_artifact.runtime_instance_id != runtime_instance_id:
        raise HTTPException(
            status_code=400,
            detail="readiness_artifact_runtime_mismatch",
        )
    from src.application.runtime_official_submit_handoff_service import (
        RuntimeOfficialSubmitHandoffService,
    )

    service = RuntimeOfficialSubmitHandoffService()
    try:
        return await service.preview_from_readiness_artifact(
            readiness_artifact=request.readiness_artifact,
            fresh_submit_authorization_id=request.fresh_submit_authorization_id,
            mode=request.mode,
            owner_confirmed_for_real_submit_action=(
                request.owner_confirmed_for_real_submit_action
            ),
            additional_blockers=request.additional_blockers,
            additional_warnings=[
                *request.additional_warnings,
                "trading_console_api_non_executing_handoff_preview",
            ],
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/strategy-runtimes/{runtime_instance_id}/official-submit-handoff-"
    "fresh-authorizations/resolve",
    response_model=RuntimeFreshSubmitAuthorizationResolutionArtifact,
)
async def runtime_official_submit_handoff_fresh_authorization_resolution(
    runtime_instance_id: str,
    request: RuntimeFreshSubmitAuthorizationResolutionRequest,
) -> RuntimeFreshSubmitAuthorizationResolutionArtifact:
    if request.handoff_artifact.runtime_instance_id != runtime_instance_id:
        raise HTTPException(
            status_code=400,
            detail="handoff_artifact_runtime_mismatch",
        )
    from src.application.runtime_fresh_submit_authorization_resolution_service import (
        RuntimeFreshSubmitAuthorizationResolutionService,
    )

    service = RuntimeFreshSubmitAuthorizationResolutionService(
        submit_authorization_repository=_build_pg_runtime_submit_authorization_repo(),
    )
    try:
        return await service.resolve_for_handoff(
            handoff=request.handoff_artifact,
            requested_fresh_submit_authorization_id=(
                request.requested_fresh_submit_authorization_id
            ),
            additional_blockers=request.additional_blockers,
            additional_warnings=[
                *request.additional_warnings,
                "trading_console_api_non_executing_fresh_authorization_resolution",
            ],
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/strategy-runtimes/{runtime_instance_id}/official-submit-handoff-"
    "fresh-authorizations/bind",
    response_model=RuntimeFreshSubmitAuthorizationBindingArtifact,
)
async def runtime_official_submit_handoff_fresh_authorization_binding(
    runtime_instance_id: str,
    request: RuntimeFreshSubmitAuthorizationBindingRequest,
) -> RuntimeFreshSubmitAuthorizationBindingArtifact:
    if request.handoff_artifact.runtime_instance_id != runtime_instance_id:
        raise HTTPException(
            status_code=400,
            detail="handoff_artifact_runtime_mismatch",
        )
    from src.application.runtime_fresh_submit_authorization_binding_service import (
        RuntimeFreshSubmitAuthorizationBindingService,
    )
    from src.application.runtime_fresh_submit_authorization_resolution_service import (
        RuntimeFreshSubmitAuthorizationResolutionService,
    )
    from src.infrastructure.pg_runtime_execution_intent_draft_repository import (
        PgRuntimeExecutionIntentDraftRepository,
    )

    submit_authorization_repo = _build_pg_runtime_submit_authorization_repo()
    intent_repo = _build_pg_execution_intent_repo()
    draft_repo = PgRuntimeExecutionIntentDraftRepository()
    adapter_service = await _runtime_execution_intent_adapter_service()
    resolution_service = RuntimeFreshSubmitAuthorizationResolutionService(
        submit_authorization_repository=submit_authorization_repo,
    )
    service = RuntimeFreshSubmitAuthorizationBindingService(
        adapter_service=adapter_service,
        resolution_service=resolution_service,
        intent_repository=intent_repo,
        draft_repository=draft_repo,
    )
    try:
        return await service.bind_for_handoff(
            handoff=request.handoff_artifact,
            requested_fresh_submit_authorization_id=(
                request.requested_fresh_submit_authorization_id
            ),
            allow_create_from_existing_intent=(
                request.allow_create_from_existing_intent
            ),
            allow_create_intent_from_latest_draft=(
                request.allow_create_intent_from_latest_draft
            ),
            additional_blockers=request.additional_blockers,
            additional_warnings=[
                *request.additional_warnings,
                "trading_console_api_fresh_authorization_binding_no_exchange_side_effects",
            ],
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/strategy-runtime-promotion-gate",
    response_model=StrategyRuntimePromotionGateResult,
)
async def runtime_strategy_promotion_gate_preview(
    strategy_family_id: str = Query(..., min_length=1, max_length=128),
    strategy_family_version_id: str = Query(..., min_length=1, max_length=128),
    scope: StrategyRuntimePromotionScope = (
        StrategyRuntimePromotionScope.CONTROLLED_RUNTIME_EXECUTION
    ),
    strategy_family_confirmed: bool = False,
    implementation_source_confirmed: bool = False,
    required_facts_confirmed: bool = False,
    entry_policy_confirmed: bool = False,
    exit_policy_confirmed: bool = False,
    protection_policy_confirmed: bool = False,
    eligible_for_runtime_execution_confirmed: bool = False,
    right_tail_review_metrics_confirmed: bool = False,
    runtime_profile_confirmed: bool = False,
    owner_confirmation_mode_confirmed: bool = False,
    symbol_side_boundary_confirmed: bool = False,
    max_loss_budget_confirmed: bool = False,
    max_notional_boundary_confirmed: bool = False,
    max_active_positions_boundary_confirmed: bool = False,
    max_leverage_boundary_confirmed: bool = False,
    margin_usage_boundary_confirmed: bool = False,
    liquidation_buffer_boundary_confirmed: bool = False,
    protection_readiness_source_confirmed: bool = False,
    stale_fact_behavior_confirmed: bool = False,
    attempt_consumption_rule_confirmed: bool = False,
    budget_reservation_rule_confirmed: bool = False,
    trusted_active_position_source_confirmed: bool = False,
    trusted_account_fact_source_confirmed: bool = False,
    short_side_conservative_profile_confirmed: bool = False,
    budget_release_or_consume_rule_confirmed: bool = False,
    post_submit_budget_settlement_persistence_evidence_id: Optional[str] = None,
    attempt_outcome_policy_id: Optional[str] = None,
    protection_creation_failure_policy_confirmed: bool = False,
    protection_creation_failure_policy_id: Optional[str] = None,
    duplicate_submit_policy_confirmed: bool = False,
    submit_idempotency_policy_id: Optional[str] = None,
    trusted_submit_fact_snapshot_id: Optional[str] = None,
    local_registration_enablement_decision_id: Optional[str] = None,
    exchange_submit_enablement_decision_id: Optional[str] = None,
    exchange_submit_execution_result_id: Optional[str] = None,
    runtime_submit_rehearsal_id: Optional[str] = None,
    deployment_readiness_evidence_id: Optional[str] = None,
    owner_real_submit_authorization_id: Optional[str] = None,
    deployment_readiness_confirmed: bool = False,
    explicit_owner_real_submit_authorization: bool = False,
) -> StrategyRuntimePromotionGateResult:
    service = await _strategy_runtime_promotion_gate_service()
    try:
        return service.preview(
            strategy_family_id=strategy_family_id,
            strategy_family_version_id=strategy_family_version_id,
            scope=scope,
            semantic_confirmations=StrategySemanticsConfirmationFacts(
                strategy_family_confirmed=strategy_family_confirmed,
                implementation_source_confirmed=implementation_source_confirmed,
                required_facts_confirmed=required_facts_confirmed,
                entry_policy_confirmed=entry_policy_confirmed,
                exit_policy_confirmed=exit_policy_confirmed,
                protection_policy_confirmed=protection_policy_confirmed,
                eligible_for_runtime_execution_confirmed=(
                    eligible_for_runtime_execution_confirmed
                ),
                right_tail_review_metrics_confirmed=(
                    right_tail_review_metrics_confirmed
                ),
            ),
            runtime_confirmations=RuntimeExecutionConfirmationFacts(
                runtime_profile_confirmed=runtime_profile_confirmed,
                owner_confirmation_mode_confirmed=owner_confirmation_mode_confirmed,
                symbol_side_boundary_confirmed=symbol_side_boundary_confirmed,
                max_loss_budget_confirmed=max_loss_budget_confirmed,
                max_notional_boundary_confirmed=max_notional_boundary_confirmed,
                max_active_positions_boundary_confirmed=(
                    max_active_positions_boundary_confirmed
                ),
                max_leverage_boundary_confirmed=max_leverage_boundary_confirmed,
                margin_usage_boundary_confirmed=margin_usage_boundary_confirmed,
                liquidation_buffer_boundary_confirmed=(
                    liquidation_buffer_boundary_confirmed
                ),
                protection_readiness_source_confirmed=(
                    protection_readiness_source_confirmed
                ),
                stale_fact_behavior_confirmed=stale_fact_behavior_confirmed,
                attempt_consumption_rule_confirmed=attempt_consumption_rule_confirmed,
                budget_reservation_rule_confirmed=budget_reservation_rule_confirmed,
                trusted_active_position_source_confirmed=(
                    trusted_active_position_source_confirmed
                ),
                trusted_account_fact_source_confirmed=(
                    trusted_account_fact_source_confirmed
                ),
                short_side_conservative_profile_confirmed=(
                    short_side_conservative_profile_confirmed
                ),
            ),
            first_real_submit_confirmations=FirstRealSubmitConfirmationFacts(
                budget_release_or_consume_rule_confirmed=(
                    budget_release_or_consume_rule_confirmed
                ),
                post_submit_budget_settlement_persistence_confirmed=bool(
                    post_submit_budget_settlement_persistence_evidence_id
                ),
                post_submit_budget_settlement_persistence_evidence_id=(
                    post_submit_budget_settlement_persistence_evidence_id
                ),
                attempt_outcome_policy_id=attempt_outcome_policy_id,
                protection_creation_failure_policy_confirmed=(
                    protection_creation_failure_policy_confirmed
                ),
                protection_creation_failure_policy_id=(
                    protection_creation_failure_policy_id
                ),
                duplicate_submit_policy_confirmed=duplicate_submit_policy_confirmed,
                submit_idempotency_policy_id=submit_idempotency_policy_id,
                trusted_submit_fact_snapshot_id=trusted_submit_fact_snapshot_id,
                local_registration_enablement_decision_id=(
                    local_registration_enablement_decision_id
                ),
                exchange_submit_enablement_decision_id=(
                    exchange_submit_enablement_decision_id
                ),
                exchange_submit_execution_result_id=(
                    exchange_submit_execution_result_id
                ),
                runtime_submit_rehearsal_id=runtime_submit_rehearsal_id,
                deployment_readiness_evidence_id=deployment_readiness_evidence_id,
                owner_real_submit_authorization_id=(
                    owner_real_submit_authorization_id
                ),
                deployment_readiness_confirmed=deployment_readiness_confirmed,
                explicit_owner_real_submit_authorization=(
                    explicit_owner_real_submit_authorization
                ),
            ),
        )
    except Exception as exc:
        message = str(exc)
        if "not found" in message:
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.get(
    "/signal-evaluations",
    response_model=list[SignalEvaluationInspectionView],
)
async def list_signal_evaluations(
    runtime_instance_id: Optional[str] = Query(default=None),
    trial_binding_id: Optional[str] = Query(default=None),
    strategy_family_id: Optional[str] = Query(default=None),
    strategy_family_version_id: Optional[str] = Query(default=None),
    status: Optional[SignalEvaluationStatus] = Query(default=None),
    symbol: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[SignalEvaluationInspectionView]:
    service = await _signal_evaluation_shadow_service()
    evaluations = await service.list_signal_evaluations(
        runtime_instance_id=runtime_instance_id,
        trial_binding_id=trial_binding_id,
        strategy_family_id=strategy_family_id,
        strategy_family_version_id=strategy_family_version_id,
        status=status,
        symbol=symbol,
        limit=limit,
    )
    return [_signal_evaluation_view(item) for item in evaluations]


@router.get(
    "/signal-evaluations/{signal_evaluation_id}",
    response_model=SignalEvaluationInspectionView,
)
async def get_signal_evaluation(
    signal_evaluation_id: str,
) -> SignalEvaluationInspectionView:
    service = await _signal_evaluation_shadow_service()
    try:
        return _signal_evaluation_view(await service.get_signal_evaluation(signal_evaluation_id))
    except Exception as exc:
        message = str(exc)
        if "not found" in message:
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.get(
    "/order-candidates",
    response_model=list[OrderCandidateInspectionView],
)
async def list_order_candidates(
    runtime_instance_id: Optional[str] = Query(default=None),
    trial_binding_id: Optional[str] = Query(default=None),
    strategy_family_id: Optional[str] = Query(default=None),
    strategy_family_version_id: Optional[str] = Query(default=None),
    signal_evaluation_id: Optional[str] = Query(default=None),
    status: Optional[OrderCandidateStatus] = Query(default=None),
    symbol: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[OrderCandidateInspectionView]:
    service = await _signal_evaluation_shadow_service()
    candidates = await service.list_order_candidates(
        runtime_instance_id=runtime_instance_id,
        trial_binding_id=trial_binding_id,
        strategy_family_id=strategy_family_id,
        strategy_family_version_id=strategy_family_version_id,
        signal_evaluation_id=signal_evaluation_id,
        status=status,
        symbol=symbol,
        limit=limit,
    )
    return [await _order_candidate_view(item) for item in candidates]


@router.get(
    "/order-candidates/{order_candidate_id}",
    response_model=OrderCandidateInspectionView,
)
async def get_order_candidate(
    order_candidate_id: str,
) -> OrderCandidateInspectionView:
    service = await _signal_evaluation_shadow_service()
    try:
        return await _order_candidate_view(await service.get_order_candidate(order_candidate_id))
    except Exception as exc:
        message = str(exc)
        if "not found" in message:
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.get(
    "/runtime-final-gate-preview/order-candidates/{order_candidate_id}",
    response_model=RuntimeFinalGatePreview,
)
async def runtime_final_gate_preview_for_order_candidate(
    order_candidate_id: str,
    active_positions_count: Optional[int] = Query(default=None, ge=0),
    owner_reviewed: bool = Query(default=True),
) -> RuntimeFinalGatePreview:
    service = await _runtime_final_gate_preview_service()
    try:
        return await service.preview_order_candidate(
            order_candidate_id=order_candidate_id,
            active_positions_count=active_positions_count,
            owner_reviewed=owner_reviewed,
            metadata={"api": "trading_console_get"},
        )
    except Exception as exc:
        message = str(exc)
        if "not found" in message:
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.get(
    "/runtime-execution-plans/order-candidates/{order_candidate_id}",
    response_model=RuntimeExecutionPlan,
)
async def runtime_execution_plan_for_order_candidate(
    order_candidate_id: str,
    active_positions_count: Optional[int] = Query(default=None, ge=0),
    owner_reviewed: bool = Query(default=True),
) -> RuntimeExecutionPlan:
    service = await _runtime_execution_planning_service()
    try:
        return await service.plan_order_candidate(
            order_candidate_id=order_candidate_id,
            active_positions_count=active_positions_count,
            owner_reviewed=owner_reviewed,
        )
    except Exception as exc:
        message = str(exc)
        if "not found" in message:
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.get(
    "/runtime-execution-intent-drafts/order-candidates/{order_candidate_id}",
    response_model=RuntimeExecutionIntentDraft,
)
async def runtime_execution_intent_draft_for_order_candidate(
    order_candidate_id: str,
    active_positions_count: Optional[int] = Query(default=None, ge=0),
    owner_reviewed: bool = Query(default=True),
    owner_confirmed_for_intent: bool = Query(default=True),
) -> RuntimeExecutionIntentDraft:
    service = await _runtime_execution_planning_service()
    try:
        return await service.intent_draft_for_order_candidate(
            order_candidate_id=order_candidate_id,
            active_positions_count=active_positions_count,
            owner_reviewed=owner_reviewed,
            owner_confirmed_for_intent=owner_confirmed_for_intent,
        )
    except Exception as exc:
        message = str(exc)
        if "not found" in message:
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.post(
    "/runtime-execution-intent-drafts/order-candidates/{order_candidate_id}",
    response_model=RuntimeExecutionIntentDraft,
)
async def record_runtime_execution_intent_draft_for_order_candidate(
    order_candidate_id: str,
    active_positions_count: Optional[int] = Query(default=None, ge=0),
    owner_reviewed: bool = Query(default=True),
    owner_confirmed_for_intent: bool = Query(default=True),
) -> RuntimeExecutionIntentDraft:
    service = await _runtime_execution_planning_service()
    try:
        return await service.record_intent_draft_for_order_candidate(
            order_candidate_id=order_candidate_id,
            active_positions_count=active_positions_count,
            owner_reviewed=owner_reviewed,
            owner_confirmed_for_intent=owner_confirmed_for_intent,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message:
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.get(
    "/runtime-execution-intent-adapter-preview/drafts/{runtime_execution_intent_draft_id}",
    response_model=RuntimeExecutionIntentCreationPreview,
)
async def runtime_execution_intent_adapter_preview_for_draft(
    runtime_execution_intent_draft_id: str,
) -> RuntimeExecutionIntentCreationPreview:
    service = await _runtime_execution_intent_adapter_service()
    try:
        return await service.preview_from_draft(runtime_execution_intent_draft_id)
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.post(
    "/runtime-execution-intents/drafts/{runtime_execution_intent_draft_id}",
    response_model=ExecutionIntent,
)
async def record_runtime_execution_intent_for_draft(
    runtime_execution_intent_draft_id: str,
) -> ExecutionIntent:
    service = await _runtime_execution_intent_adapter_service()
    try:
        return await service.create_recorded_intent_from_draft(
            runtime_execution_intent_draft_id
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.get(
    "/runtime-execution-submit-readiness/intents/{execution_intent_id}",
    response_model=RuntimeExecutionSubmitReadiness,
)
async def runtime_execution_submit_readiness_for_intent(
    execution_intent_id: str,
) -> RuntimeExecutionSubmitReadiness:
    service = await _runtime_execution_intent_adapter_service()
    try:
        return await service.submit_readiness_for_intent(execution_intent_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.get(
    "/runtime-execution-protection-plan-previews/intents/{execution_intent_id}",
    response_model=RuntimeExecutionProtectionPlanPreview,
)
async def runtime_execution_protection_plan_preview_for_intent(
    execution_intent_id: str,
) -> RuntimeExecutionProtectionPlanPreview:
    service = await _runtime_execution_intent_adapter_service()
    try:
        return await service.protection_plan_preview_for_intent(execution_intent_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.post(
    "/runtime-execution-protection-plans/intents/{execution_intent_id}",
    response_model=RuntimeExecutionProtectionPlan,
)
async def record_runtime_execution_protection_plan_for_intent(
    execution_intent_id: str,
) -> RuntimeExecutionProtectionPlan:
    service = await _runtime_execution_intent_adapter_service()
    try:
        return await service.record_protection_plan_for_intent(execution_intent_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.get(
    "/runtime-execution-protection-failure-policies/intents/{execution_intent_id}",
    response_model=RuntimeExecutionProtectionFailurePolicy,
)
async def runtime_execution_protection_failure_policy_for_intent(
    execution_intent_id: str,
) -> RuntimeExecutionProtectionFailurePolicy:
    service = await _runtime_execution_intent_adapter_service()
    try:
        return await service.protection_failure_policy_for_intent(
            execution_intent_id
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.post(
    "/runtime-execution-protection-failure-policies/intents/{execution_intent_id}",
    response_model=RuntimeExecutionProtectionFailurePolicy,
)
async def record_runtime_execution_protection_failure_policy_for_intent(
    execution_intent_id: str,
) -> RuntimeExecutionProtectionFailurePolicy:
    service = await _runtime_execution_intent_adapter_service()
    try:
        return await service.record_protection_failure_policy_for_intent(
            execution_intent_id
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.post(
    "/runtime-execution-submit-idempotency/authorizations/{authorization_id}",
    response_model=RuntimeExecutionSubmitIdempotencySnapshot,
)
async def record_runtime_execution_submit_idempotency_for_authorization(
    authorization_id: str,
    adapter_result_store_implemented: bool = False,
    real_adapter_boundary_implemented: bool = False,
) -> RuntimeExecutionSubmitIdempotencySnapshot:
    service = await _runtime_execution_intent_adapter_service()
    try:
        return await service.record_submit_idempotency_snapshot_for_authorization(
            authorization_id,
            adapter_result_store_implemented=adapter_result_store_implemented,
            real_adapter_boundary_implemented=real_adapter_boundary_implemented,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.post(
    "/runtime-execution-trusted-submit-facts",
    response_model=RuntimeExecutionTrustedSubmitFactsSnapshot,
)
async def record_runtime_execution_trusted_submit_facts_snapshot(
    snapshot: RuntimeExecutionTrustedSubmitFactsSnapshot,
) -> RuntimeExecutionTrustedSubmitFactsSnapshot:
    service = await _runtime_execution_intent_adapter_service()
    try:
        return await service.record_trusted_submit_facts_snapshot(snapshot)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/runtime-execution-trusted-submit-facts/authorizations/{authorization_id}",
    response_model=RuntimeExecutionTrustedSubmitFactsSnapshot,
)
async def record_runtime_execution_trusted_submit_facts_for_authorization(
    authorization_id: str,
    trusted_submit_fact_snapshot_id: Optional[str] = None,
) -> RuntimeExecutionTrustedSubmitFactsSnapshot:
    adapter_service = await _runtime_execution_intent_adapter_service()
    assembly_service = _runtime_execution_trusted_submit_facts_assembly_service()
    try:
        plan = await adapter_service.controlled_submit_plan_for_authorization(
            authorization_id
        )
        return await (
            assembly_service
            .assemble_and_record_snapshot_for_controlled_submit_plan(
                plan=plan,
                trusted_submit_fact_snapshot_id=trusted_submit_fact_snapshot_id,
                now_ms=int(time.time() * 1000),
                metadata={
                    "api": (
                        "runtime_execution_trusted_submit_facts_for_authorization"
                    ),
                    "authorization_id": authorization_id,
                    "owner_supplied_allow_facts_accepted": False,
                },
            )
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.post(
    "/runtime-execution-submit-authorizations/intents/{execution_intent_id}",
    response_model=RuntimeExecutionSubmitAuthorization,
)
async def record_runtime_execution_submit_authorization_for_intent(
    execution_intent_id: str,
    owner_confirmed_for_submit: bool = Query(default=True),
) -> RuntimeExecutionSubmitAuthorization:
    service = await _runtime_execution_intent_adapter_service()
    try:
        return await service.create_submit_authorization_for_intent(
            execution_intent_id,
            owner_confirmed_for_submit=owner_confirmed_for_submit,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.get(
    "/runtime-execution-controlled-submit-plans/authorizations/{authorization_id}",
    response_model=RuntimeExecutionControlledSubmitPlan,
)
async def runtime_execution_controlled_submit_plan_for_authorization(
    authorization_id: str,
) -> RuntimeExecutionControlledSubmitPlan:
    service = await _runtime_execution_intent_adapter_service()
    try:
        return await service.controlled_submit_plan_for_authorization(authorization_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.get(
    "/runtime-execution-controlled-submit-preflights/authorizations/{authorization_id}",
    response_model=RuntimeExecutionControlledSubmitPreflight,
)
async def runtime_execution_controlled_submit_preflight_for_authorization(
    authorization_id: str,
) -> RuntimeExecutionControlledSubmitPreflight:
    service = await _runtime_execution_intent_adapter_service()
    try:
        return await service.controlled_submit_preflight_for_authorization(authorization_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.get(
    "/runtime-action-time-finalgate-preflights/tickets/{ticket_id}",
    response_model=RuntimeActionTimeFinalGatePreflight,
)
async def runtime_action_time_finalgate_preflight_for_ticket(
    ticket_id: str,
) -> RuntimeActionTimeFinalGatePreflight:
    ticket_id = str(ticket_id or "").strip()
    if not ticket_id:
        raise HTTPException(status_code=400, detail="ticket_id_required")
    try:
        report = _run_ticket_bound_action_time_finalgate_preflight(ticket_id)
        return RuntimeActionTimeFinalGatePreflight(
            **_ticket_bound_finalgate_api_body(report)
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except sa.exc.SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post(
    "/runtime-operation-layer-handoffs/tickets/{ticket_id}/finalgate-passes/{finalgate_pass_id}",
    response_model=RuntimeOperationLayerHandoff,
)
async def runtime_operation_layer_handoff_for_ticket(
    ticket_id: str,
    finalgate_pass_id: str,
) -> RuntimeOperationLayerHandoff:
    ticket_id = str(ticket_id or "").strip()
    finalgate_pass_id = str(finalgate_pass_id or "").strip()
    if not ticket_id:
        raise HTTPException(status_code=400, detail="ticket_id_required")
    if not finalgate_pass_id:
        raise HTTPException(status_code=400, detail="finalgate_pass_id_required")
    try:
        report = _run_ticket_bound_operation_layer_handoff(
            ticket_id=ticket_id,
            finalgate_pass_id=finalgate_pass_id,
        )
        return RuntimeOperationLayerHandoff(
            **_ticket_bound_operation_layer_handoff_api_body(report)
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except sa.exc.SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post(
    "/runtime-protected-submits/tickets/{ticket_id}/operation-submit-commands/"
    "{operation_submit_command_id}",
    response_model=RuntimeTicketBoundProtectedSubmit,
)
async def runtime_ticket_bound_protected_submit_for_ticket(
    ticket_id: str,
    operation_submit_command_id: str,
    submit_mode: str = Query(default="disabled_smoke"),
) -> RuntimeTicketBoundProtectedSubmit:
    ticket_id = str(ticket_id or "").strip()
    operation_submit_command_id = str(operation_submit_command_id or "").strip()
    submit_mode = str(submit_mode or "").strip()
    if not ticket_id:
        raise HTTPException(status_code=400, detail="ticket_id_required")
    if not operation_submit_command_id:
        raise HTTPException(status_code=400, detail="operation_submit_command_id_required")
    try:
        report = await _run_ticket_bound_protected_submit(
            ticket_id=ticket_id,
            operation_submit_command_id=operation_submit_command_id,
            submit_mode=submit_mode,
        )
        return RuntimeTicketBoundProtectedSubmit(
            **_ticket_bound_protected_submit_api_body(report)
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except sa.exc.SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post(
    "/runtime-post-submit-closures/protected-submit-attempts/"
    "{protected_submit_attempt_id}",
    response_model=RuntimeTicketBoundPostSubmitClosure,
)
async def runtime_ticket_bound_post_submit_closure_for_attempt(
    protected_submit_attempt_id: str,
) -> RuntimeTicketBoundPostSubmitClosure:
    protected_submit_attempt_id = str(protected_submit_attempt_id or "").strip()
    if not protected_submit_attempt_id:
        raise HTTPException(status_code=400, detail="protected_submit_attempt_id_required")
    try:
        report = _run_ticket_bound_post_submit_closure(
            protected_submit_attempt_id=protected_submit_attempt_id,
        )
        return RuntimeTicketBoundPostSubmitClosure(
            **_ticket_bound_post_submit_closure_api_body(report)
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except sa.exc.SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _run_ticket_bound_action_time_finalgate_preflight(ticket_id: str) -> dict[str, Any]:
    database_url = normalize_sync_postgres_dsn(os.getenv("PG_DATABASE_URL") or "")
    if not database_url:
        raise RuntimeError("PG_DATABASE_URL is required for ticket-bound FinalGate")
    if not is_sync_postgres_dsn(database_url):
        raise RuntimeError("ticket-bound FinalGate requires PostgreSQL DSN")

    from src.application.action_time.finalgate_preflight import (
        materialize_action_time_finalgate_preflight,
    )

    engine = sa.create_engine(database_url)
    try:
        with engine.begin() as conn:
            return materialize_action_time_finalgate_preflight(
                conn,
                ticket_id=ticket_id,
            )
    finally:
        engine.dispose()


def _run_ticket_bound_operation_layer_handoff(
    *,
    ticket_id: str,
    finalgate_pass_id: str,
) -> dict[str, Any]:
    database_url = normalize_sync_postgres_dsn(os.getenv("PG_DATABASE_URL") or "")
    if not database_url:
        raise RuntimeError("PG_DATABASE_URL is required for ticket-bound Operation Layer handoff")
    if not is_sync_postgres_dsn(database_url):
        raise RuntimeError("ticket-bound Operation Layer handoff requires PostgreSQL DSN")

    from src.application.action_time.operation_layer_handoff import (
        materialize_action_time_operation_layer_handoff,
    )

    engine = sa.create_engine(database_url)
    try:
        with engine.begin() as conn:
            return materialize_action_time_operation_layer_handoff(
                conn,
                ticket_id=ticket_id,
                finalgate_pass_id=finalgate_pass_id,
            )
    finally:
        engine.dispose()


async def _run_ticket_bound_protected_submit(
    *,
    ticket_id: str,
    operation_submit_command_id: str,
    submit_mode: str,
) -> dict[str, Any]:
    database_url = normalize_sync_postgres_dsn(os.getenv("PG_DATABASE_URL") or "")
    if not database_url:
        raise RuntimeError("PG_DATABASE_URL is required for ticket-bound protected submit")
    if not is_sync_postgres_dsn(database_url):
        raise RuntimeError("ticket-bound protected submit requires PostgreSQL DSN")

    from src.application.action_time.protected_submit_attempt import (
        LIVE_EXCHANGE_WRITE_SUBMIT_MODES,
        SUBMIT_MODE_REAL_GATEWAY_ACTION,
        SUBMIT_MODE_TEMP_TINY_LIVE_PROTECTED,
        prepare_ticket_bound_protected_submit_attempt,
        record_ticket_bound_protected_submit_result,
    )

    engine = sa.create_engine(database_url)
    try:
        with engine.begin() as conn:
            report = prepare_ticket_bound_protected_submit_attempt(
                conn,
                ticket_id=ticket_id,
                operation_submit_command_id=operation_submit_command_id,
                submit_mode=submit_mode,
            )
        if report.get("status") != "submit_prepared":
            return report
        if submit_mode not in LIVE_EXCHANGE_WRITE_SUBMIT_MODES:
            return report
        if submit_mode == SUBMIT_MODE_TEMP_TINY_LIVE_PROTECTED:
            # TODO(L2-L9-closure): remove this temporary live aperture once the
            # normal real-submit, protection, reconciliation, settlement, and
            # review chain is fully closed. Until then it only allows the
            # ticket-bound ENTRY + SL + TP1 order set prepared by PG.
            report = {
                **report,
                "temporary_live_aperture": "remove_after_l2_l9_closure",
            }

        submit_result = await _execute_ticket_bound_real_gateway_submit(report)
        with engine.begin() as conn:
            return record_ticket_bound_protected_submit_result(
                conn,
                protected_submit_attempt_id=str(
                    report.get("protected_submit_attempt_id") or ""
                ),
                submit_result=submit_result,
            )
    finally:
        engine.dispose()


def _run_ticket_bound_post_submit_closure(
    *,
    protected_submit_attempt_id: str,
) -> dict[str, Any]:
    database_url = normalize_sync_postgres_dsn(os.getenv("PG_DATABASE_URL") or "")
    if not database_url:
        raise RuntimeError("PG_DATABASE_URL is required for ticket-bound post-submit closure")
    if not is_sync_postgres_dsn(database_url):
        raise RuntimeError("ticket-bound post-submit closure requires PostgreSQL DSN")

    from src.application.action_time.post_submit_closure import (
        materialize_ticket_bound_post_submit_closure,
    )

    engine = sa.create_engine(database_url)
    try:
        with engine.begin() as conn:
            return materialize_ticket_bound_post_submit_closure(
                conn,
                protected_submit_attempt_id=protected_submit_attempt_id,
            )
    finally:
        engine.dispose()


async def _execute_ticket_bound_real_gateway_submit(
    report: dict[str, Any],
) -> dict[str, Any]:
    from src.application.order_lifecycle_service import OrderLifecycleService
    from src.interfaces import api as api_module

    gateway_binding = await _runtime_exchange_submit_gateway_binding(api_module)
    gateway = gateway_binding.get("gateway")
    if gateway is None:
        return _ticket_bound_submit_blocked_result(
            report,
            status="runtime_exchange_gateway_unavailable",
            blockers=list(gateway_binding.get("blockers") or []),
        )
    order_repository = _cached_pg_repo(
        api_module,
        "_trading_console_pg_order_repo",
        _build_pg_order_repo,
    )
    if order_repository is None:
        return _ticket_bound_submit_blocked_result(
            report,
            status="order_lifecycle_repository_unavailable",
            blockers=["order_lifecycle_repository_unavailable"],
        )
    order_lifecycle_service = OrderLifecycleService(repository=order_repository)
    return await _submit_ticket_bound_orders(
        report,
        gateway=gateway,
        order_lifecycle_service=order_lifecycle_service,
    )


async def _submit_ticket_bound_orders(
    report: dict[str, Any],
    *,
    gateway: Any,
    order_lifecycle_service: Any,
) -> dict[str, Any]:
    from src.domain.models import Direction, Order, OrderRole, OrderStatus

    submit_request = dict(report.get("submit_request") or {})
    identity_blockers = _ticket_bound_submit_request_identity_blockers(
        report,
        submit_request,
    )
    if identity_blockers:
        return _ticket_bound_submit_blocked_result(
            report,
            status="submit_request_identity_mismatch",
            blockers=identity_blockers,
        )
    orders = [
        dict(item)
        for item in submit_request.get("orders", [])
        if isinstance(item, dict)
    ]
    if not orders:
        return _ticket_bound_submit_blocked_result(
            report,
            status="submit_request_orders_missing",
            blockers=["submit_request_orders_missing"],
        )
    temporary_order_blockers = _temporary_tiny_live_submit_order_blockers(
        report,
        orders,
    )
    if temporary_order_blockers:
        return _ticket_bound_submit_blocked_result(
            report,
            status="temporary_tiny_live_order_set_invalid",
            blockers=temporary_order_blockers,
        )
    now_ms = int(time.time() * 1000)
    registered_orders: list[Any] = []
    submitted_orders: list[dict[str, Any]] = []
    exchange_call_count = 0
    try:
        direction = Direction(str(submit_request.get("direction") or ""))
    except Exception as exc:
        return _ticket_bound_submit_blocked_result(
            report,
            status="submit_request_direction_invalid",
            blockers=[f"submit_request_direction_invalid:{type(exc).__name__}"],
        )
    for order_request in orders:
        local_order_id = str(order_request.get("local_order_id") or "")
        try:
            order_type = _ticket_bound_order_type(
                order_request.get("gateway_order_type")
            )
            order_role = OrderRole(str(order_request.get("order_role") or ""))
            amount = Decimal(str(order_request.get("amount") or "0"))
            order = Order(
                id=local_order_id,
                signal_id=str(report.get("ticket_id") or ""),
                symbol=str(
                    order_request.get("symbol")
                    or submit_request.get("exchange_symbol")
                    or ""
                ),
                direction=direction,
                order_type=order_type,
                order_role=order_role,
                price=_optional_decimal(order_request.get("price")),
                trigger_price=_optional_decimal(order_request.get("trigger_price")),
                requested_qty=amount,
                status=OrderStatus.CREATED,
                created_at=now_ms,
                updated_at=now_ms,
                reduce_only=order_request.get("reduce_only") is True,
                parent_order_id=order_request.get("parent_order_id"),
                signal_evaluation_id=str(report.get("ticket_id") or ""),
            )
        except Exception as exc:
            return _ticket_bound_submit_blocked_result(
                report,
                status="submit_request_order_invalid",
                blockers=[
                    "submit_request_order_invalid:"
                    f"{local_order_id or 'missing'}:{type(exc).__name__}"
                ],
                order_created=bool(registered_orders),
                order_lifecycle_called=bool(registered_orders),
                submitted_orders=submitted_orders,
            )
        try:
            registered = await order_lifecycle_service.register_created_order(
                order,
                metadata={
                    "scope": "ticket_bound_protected_submit",
                    "ticket_id": report.get("ticket_id"),
                    "operation_submit_command_id": (
                        report.get("operation_submit_command_id")
                    ),
                    "runtime_safety_snapshot_id": (
                        report.get("runtime_safety_snapshot_id")
                    ),
                    "exchange_order_submitted": False,
                    "exchange_called": False,
                },
            )
        except Exception as exc:
            return _ticket_bound_submit_blocked_result(
                report,
                status="local_order_registration_failed",
                blockers=[
                    "local_order_registration_failed:"
                    f"{local_order_id}:{type(exc).__name__}"
                ],
                order_created=bool(registered_orders),
                order_lifecycle_called=bool(registered_orders),
                submitted_orders=submitted_orders,
            )
        registered_orders.append(registered)

        exchange_call_count += 1
        try:
            placement_result = await gateway.place_order(
                symbol=order.symbol,
                order_type=str(order_request.get("gateway_order_type") or ""),
                side=str(order_request.get("gateway_side") or ""),
                amount=amount,
                price=_optional_decimal(order_request.get("price")),
                trigger_price=_optional_decimal(order_request.get("trigger_price")),
                reduce_only=order_request.get("reduce_only") is True,
                client_order_id=str(
                    order_request.get("client_order_id") or local_order_id
                ),
            )
        except Exception as exc:
            return _ticket_bound_submit_blocked_result(
                report,
                status="exchange_submit_failed",
                blockers=[
                    "exchange_submit_failed:"
                    f"{local_order_id}:{type(exc).__name__}"
                ],
                order_created=True,
                order_lifecycle_called=True,
                exchange_write_called=True,
                submitted_orders=submitted_orders,
            )
        if not getattr(placement_result, "is_success", False):
            return _ticket_bound_submit_blocked_result(
                report,
                status=(
                    "protection_submit_failed"
                    if order_role != OrderRole.ENTRY
                    else "entry_submit_failed"
                ),
                blockers=[
                    getattr(placement_result, "error_message", None)
                    or getattr(placement_result, "error_code", None)
                    or f"exchange_submit_failed:{local_order_id}"
                ],
                order_created=True,
                order_lifecycle_called=True,
                exchange_write_called=True,
                submitted_orders=submitted_orders,
            )
        exchange_order_id = getattr(placement_result, "exchange_order_id", None)
        try:
            await order_lifecycle_service.submit_order(
                local_order_id,
                exchange_order_id=exchange_order_id,
            )
            filled_qty = getattr(placement_result, "filled_qty", None)
            average_exec_price = getattr(placement_result, "average_exec_price", None)
            parsed_filled_qty = _decimal_or_zero(filled_qty)
            if (
                str(getattr(placement_result, "status", "")).split(".")[-1].lower()
                == "filled"
                or parsed_filled_qty > Decimal("0")
            ):
                await order_lifecycle_service.update_order_filled(
                    local_order_id,
                    filled_qty=parsed_filled_qty if parsed_filled_qty > 0 else amount,
                    average_exec_price=Decimal(
                        str(
                            average_exec_price
                            or order_request.get("price")
                            or order_request.get("trigger_price")
                            or submit_request.get("reference_price")
                            or "0"
                        )
                    ),
                )
            else:
                await order_lifecycle_service.confirm_order(
                    local_order_id,
                    exchange_order_id=exchange_order_id,
                )
        except Exception as exc:
            return _ticket_bound_submit_blocked_result(
                report,
                status="order_lifecycle_update_failed",
                blockers=[
                    "order_lifecycle_update_failed:"
                    f"{local_order_id}:{type(exc).__name__}"
                ],
                order_created=True,
                order_lifecycle_called=True,
                exchange_write_called=True,
                submitted_orders=submitted_orders,
            )
        submitted_orders.append(
            {
                "local_order_id": local_order_id,
                "exchange_order_id": exchange_order_id,
                "order_role": str(order_role.value),
                "reduce_only": order_request.get("reduce_only") is True,
                "amount": str(order_request.get("amount") or ""),
                "price": str(order_request.get("price") or ""),
                "trigger_price": str(order_request.get("trigger_price") or ""),
                "status": str(getattr(placement_result, "status", "")).split(".")[-1],
                "filled_qty": str(getattr(placement_result, "filled_qty", "") or ""),
                "average_exec_price": str(
                    getattr(placement_result, "average_exec_price", "") or ""
                ),
            }
        )

    return {
        "schema": "brc.ticket_bound_protected_submit_result.v1",
        "status": "exchange_submit_orders_submitted",
        "ticket_id": report.get("ticket_id"),
        "operation_submit_command_id": report.get("operation_submit_command_id"),
        "strategy_group_id": report.get("strategy_group_id"),
        "symbol": report.get("symbol"),
        "side": report.get("side"),
        "exchange_call_count": exchange_call_count,
        "submitted_orders": submitted_orders,
        "exchange_write_called": True,
        "order_created": True,
        "order_lifecycle_called": True,
        "withdrawal_or_transfer_created": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
    }


def _temporary_tiny_live_submit_order_blockers(
    report: dict[str, Any],
    orders: list[dict[str, Any]],
) -> list[str]:
    """Second exchange-write guard for the temporary ENTRY + SL + TP1 aperture."""

    if str(report.get("submit_mode") or "") != "temp_tiny_live_protected_submit":
        return []
    roles = [str(order.get("order_role") or "") for order in orders]
    blockers: list[str] = []
    if roles != ["ENTRY", "SL", "TP1"]:
        return [
            "temporary_tiny_live_order_roles_must_be_entry_sl_tp1:"
            + ",".join(roles)
        ]
    entry, stop_loss, tp1 = orders
    if str(entry.get("gateway_order_type") or "") != "market":
        blockers.append("temporary_tiny_live_entry_must_be_market")
    if entry.get("reduce_only") is not False:
        blockers.append("temporary_tiny_live_entry_must_not_be_reduce_only")
    if str(stop_loss.get("gateway_order_type") or "") != "stop_market":
        blockers.append("temporary_tiny_live_sl_must_be_stop_market")
    if stop_loss.get("reduce_only") is not True:
        blockers.append("temporary_tiny_live_sl_must_be_reduce_only")
    if not stop_loss.get("trigger_price"):
        blockers.append("temporary_tiny_live_sl_trigger_price_missing")
    if str(tp1.get("gateway_order_type") or "") != "limit":
        blockers.append("temporary_tiny_live_tp1_must_be_limit")
    if tp1.get("reduce_only") is not True:
        blockers.append("temporary_tiny_live_tp1_must_be_reduce_only")
    if not tp1.get("price"):
        blockers.append("temporary_tiny_live_tp1_price_missing")
    for child in (stop_loss, tp1):
        if str(child.get("parent_order_id") or "") != str(
            entry.get("local_order_id") or ""
        ):
            blockers.append(
                "temporary_tiny_live_child_parent_order_mismatch:"
                f"{child.get('order_role') or 'unknown'}"
            )
    return blockers


def _ticket_bound_submit_request_identity_blockers(
    report: dict[str, Any],
    submit_request: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    for key in (
        "ticket_id",
        "operation_submit_command_id",
        "strategy_group_id",
        "symbol",
        "side",
    ):
        expected = str(report.get(key) or "").strip()
        actual = str(submit_request.get(key) or "").strip()
        if not expected:
            blockers.append(f"submit_report_identity_missing:{key}")
        elif not actual:
            blockers.append(f"submit_request_identity_missing:{key}")
        elif actual != expected:
            blockers.append(
                f"submit_request_identity_mismatch:{key}:"
                f"expected={expected}:actual={actual}"
            )
    return blockers


def _ticket_bound_submit_blocked_result(
    report: dict[str, Any],
    *,
    status: str,
    blockers: list[str],
    order_created: bool = False,
    order_lifecycle_called: bool = False,
    exchange_write_called: bool = False,
    submitted_orders: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    submitted_orders = submitted_orders or []
    protection_gap = _temporary_tiny_live_unprotected_position_gap(
        report,
        submitted_orders,
    )
    if protection_gap:
        blockers = [*blockers, *protection_gap["blockers"]]
    return {
        "schema": "brc.ticket_bound_protected_submit_result.v1",
        "status": status,
        "ticket_id": report.get("ticket_id"),
        "operation_submit_command_id": report.get("operation_submit_command_id"),
        "strategy_group_id": report.get("strategy_group_id"),
        "symbol": report.get("symbol"),
        "side": report.get("side"),
        "blockers": blockers,
        "submitted_orders": submitted_orders,
        "unprotected_position_risk": bool(protection_gap),
        "protection_gap": protection_gap,
        "exchange_write_called": exchange_write_called,
        "order_created": order_created,
        "order_lifecycle_called": order_lifecycle_called,
        "withdrawal_or_transfer_created": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
    }


def _temporary_tiny_live_unprotected_position_gap(
    report: dict[str, Any],
    submitted_orders: list[dict[str, Any]],
) -> dict[str, Any]:
    if str(report.get("submit_mode") or "") != "temp_tiny_live_protected_submit":
        return {}
    submitted_roles = {
        str(order.get("order_role") or "")
        for order in submitted_orders
        if isinstance(order, dict)
    }
    if "ENTRY" not in submitted_roles:
        return {}
    missing_protection = sorted({"SL", "TP1"} - submitted_roles)
    if not missing_protection:
        return {}
    return {
        "status": "temporary_tiny_live_unprotected_position_risk",
        "missing_protection_roles": missing_protection,
        "blockers": [
            "temporary_tiny_live_unprotected_position_risk:"
            + ",".join(missing_protection)
        ],
        "next_action": (
            "run_reconciliation_and_manual_or_automated_protection_repair_before_retry"
        ),
    }


def _ticket_bound_order_type(value: Any) -> Any:
    from src.domain.models import OrderType

    normalized = str(value or "").strip().lower()
    if normalized == "market":
        return OrderType.MARKET
    if normalized == "limit":
        return OrderType.LIMIT
    if normalized == "stop_market":
        return OrderType.STOP_MARKET
    if normalized == "stop_limit":
        return OrderType.STOP_LIMIT
    raise ValueError(f"unsupported_ticket_bound_order_type:{normalized or 'missing'}")


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _decimal_or_zero(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _ticket_bound_finalgate_api_body(report: dict[str, Any]) -> dict[str, Any]:
    preflight_status = str(report.get("status") or "")
    passed = preflight_status in {"finalgate_ready", "finalgate_already_ready"}
    blockers = [
        str(item)
        for item in (report.get("blockers") or [])
        if str(item).strip()
    ]
    return {
        "schema": "brc.runtime_action_time_finalgate_preflight_api.v1",
        "status": (
            "ready_for_controlled_submit_adapter" if passed else "blocked"
        ),
        "controlled_submit_plan_status": (
            "ready_for_controlled_submit_adapter" if passed else "blocked"
        ),
        "final_gate_verdict": "pass" if passed else "block",
        "ticket_preflight_status": preflight_status,
        "ticket_id": report.get("ticket_id"),
        "finalgate_pass_id": report.get("finalgate_pass_id"),
        "action_time_lane_input_id": report.get("action_time_lane_input_id"),
        "strategy_group_id": report.get("strategy_group_id"),
        "symbol": report.get("symbol"),
        "side": report.get("side"),
        "blockers": blockers,
        "warnings": [],
        "next_action": str(report.get("next_action") or ""),
        "authority_boundary": str(report.get("authority_boundary") or ""),
        "submit_executed": False,
        "order_created": False,
        "exchange_called": False,
        "owner_bounded_execution_called": False,
        "order_lifecycle_called": False,
        "operation_layer_called": False,
        "exchange_write_called": False,
        "withdrawal_or_transfer_created": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
        "source_report": report,
    }


def _ticket_bound_operation_layer_handoff_api_body(report: dict[str, Any]) -> dict[str, Any]:
    handoff_status = str(report.get("status") or "")
    ready = handoff_status in {
        "operation_layer_handoff_ready",
        "operation_layer_handoff_already_exists",
    }
    blockers = [
        str(item)
        for item in (report.get("blockers") or [])
        if str(item).strip()
    ]
    return {
        "schema": "brc.runtime_operation_layer_handoff_api.v1",
        "status": "operation_layer_handoff_ready" if ready else "blocked",
        "operation_layer_verdict": "ready" if ready else "block",
        "ticket_id": report.get("ticket_id"),
        "finalgate_pass_id": report.get("finalgate_pass_id"),
        "operation_layer_handoff_id": report.get("operation_layer_handoff_id"),
        "operation_submit_command_id": report.get("operation_submit_command_id"),
        "action_time_lane_input_id": report.get("action_time_lane_input_id"),
        "strategy_group_id": report.get("strategy_group_id"),
        "symbol": report.get("symbol"),
        "side": report.get("side"),
        "blockers": blockers,
        "warnings": [],
        "command_plan": dict(report.get("command_plan") or {}),
        "next_action": str(report.get("next_action") or ""),
        "authority_boundary": str(report.get("authority_boundary") or ""),
        "submit_executed": False,
        "operation_layer_submit_called": False,
        "order_created": False,
        "exchange_called": False,
        "exchange_write_called": False,
        "owner_bounded_execution_called": False,
        "order_lifecycle_called": False,
        "withdrawal_or_transfer_created": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
        "source_report": report,
    }


def _ticket_bound_protected_submit_api_body(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "brc.runtime_ticket_bound_protected_submit_api.v1",
        "status": str(report.get("status") or "blocked"),
        "protected_submit_attempt_id": report.get("protected_submit_attempt_id"),
        "ticket_id": report.get("ticket_id"),
        "finalgate_pass_id": report.get("finalgate_pass_id"),
        "operation_layer_handoff_id": report.get("operation_layer_handoff_id"),
        "operation_submit_command_id": report.get("operation_submit_command_id"),
        "runtime_safety_snapshot_id": report.get("runtime_safety_snapshot_id"),
        "action_time_lane_input_id": report.get("action_time_lane_input_id"),
        "strategy_group_id": report.get("strategy_group_id"),
        "symbol": report.get("symbol"),
        "side": report.get("side"),
        "submit_mode": report.get("submit_mode"),
        "submit_allowed": report.get("submit_allowed") is True,
        "blockers": [
            str(item)
            for item in (report.get("blockers") or [])
            if str(item).strip()
        ],
        "warnings": [
            str(item)
            for item in (report.get("warnings") or [])
            if str(item).strip()
        ],
        "submit_request": dict(report.get("submit_request") or {}),
        "submit_result": dict(report.get("submit_result") or {}),
        "identity_evidence": dict(report.get("identity_evidence") or {}),
        "next_action": str(report.get("next_action") or ""),
        "authority_boundary": str(report.get("authority_boundary") or ""),
        "official_operation_layer_submit_called": (
            report.get("official_operation_layer_submit_called") is True
        ),
        "exchange_write_called": report.get("exchange_write_called") is True,
        "order_created": report.get("order_created") is True,
        "order_lifecycle_called": report.get("order_lifecycle_called") is True,
        "withdrawal_or_transfer_created": (
            report.get("withdrawal_or_transfer_created") is True
        ),
        "live_profile_changed": report.get("live_profile_changed") is True,
        "order_sizing_changed": report.get("order_sizing_changed") is True,
        "source_report": report,
    }


def _ticket_bound_post_submit_closure_api_body(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "brc.runtime_ticket_bound_post_submit_closure_api.v1",
        "status": str(report.get("status") or "blocked"),
        "post_submit_closure_id": report.get("post_submit_closure_id"),
        "protected_submit_attempt_id": report.get("protected_submit_attempt_id"),
        "ticket_id": report.get("ticket_id"),
        "operation_submit_command_id": report.get("operation_submit_command_id"),
        "strategy_group_id": report.get("strategy_group_id"),
        "symbol": report.get("symbol"),
        "side": report.get("side"),
        "protection_state": report.get("protection_state"),
        "reconciliation_state": report.get("reconciliation_state"),
        "settlement_state": report.get("settlement_state"),
        "review_state": report.get("review_state"),
        "first_blocker": report.get("first_blocker"),
        "blockers": [
            str(item)
            for item in (report.get("blockers") or [])
            if str(item).strip()
        ],
        "submitted_order_refs": [
            dict(item)
            for item in (report.get("submitted_order_refs") or [])
            if isinstance(item, dict)
        ],
        "next_action": str(report.get("next_action") or ""),
        "authority_boundary": str(report.get("authority_boundary") or ""),
        "finalgate_called": report.get("finalgate_called") is True,
        "operation_layer_called": report.get("operation_layer_called") is True,
        "exchange_write_called": report.get("exchange_write_called") is True,
        "order_created": report.get("order_created") is True,
        "order_lifecycle_called": report.get("order_lifecycle_called") is True,
        "withdrawal_or_transfer_created": (
            report.get("withdrawal_or_transfer_created") is True
        ),
        "live_profile_changed": report.get("live_profile_changed") is True,
        "order_sizing_changed": report.get("order_sizing_changed") is True,
        "runtime_budget_mutated": report.get("runtime_budget_mutated") is True,
        "source_report": report,
    }


@router.get(
    "/runtime-execution-submit-adapter-previews/authorizations/{authorization_id}",
    response_model=RuntimeExecutionSubmitAdapterPreview,
)
async def runtime_execution_submit_adapter_preview_for_authorization(
    authorization_id: str,
) -> RuntimeExecutionSubmitAdapterPreview:
    service = await _runtime_execution_intent_adapter_service()
    try:
        return await service.controlled_submit_adapter_preview_for_authorization(
            authorization_id
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.get(
    "/runtime-execution-attempt-reservation-previews/authorizations/{authorization_id}",
    response_model=RuntimeExecutionAttemptReservationPreview,
)
async def runtime_execution_attempt_reservation_preview_for_authorization(
    authorization_id: str,
) -> RuntimeExecutionAttemptReservationPreview:
    service = await _runtime_execution_intent_adapter_service()
    try:
        return await service.attempt_reservation_preview_for_authorization(
            authorization_id
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.post(
    "/runtime-execution-attempt-reservations/authorizations/{authorization_id}",
    response_model=RuntimeExecutionAttemptReservation,
)
async def record_runtime_execution_attempt_reservation_for_authorization(
    authorization_id: str,
) -> RuntimeExecutionAttemptReservation:
    service = await _runtime_execution_intent_adapter_service()
    try:
        return await service.record_attempt_reservation_for_authorization(
            authorization_id
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.post(
    "/runtime-execution-attempt-mutations/reservations/{reservation_id}",
    response_model=RuntimeExecutionAttemptMutation,
)
async def apply_runtime_execution_attempt_mutation_for_reservation(
    reservation_id: str,
) -> RuntimeExecutionAttemptMutation:
    service = await _runtime_execution_intent_adapter_service()
    try:
        return await service.apply_attempt_mutation_for_reservation(
            reservation_id
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.post(
    "/runtime-execution-attempt-outcome-policies/reservations/{reservation_id}",
    response_model=RuntimeExecutionAttemptOutcomePolicy,
)
async def record_runtime_execution_attempt_outcome_policy_for_reservation(
    reservation_id: str,
    outcome_kind: RuntimeExecutionAttemptOutcomeKind,
) -> RuntimeExecutionAttemptOutcomePolicy:
    service = await _runtime_execution_intent_adapter_service()
    try:
        return await service.record_attempt_outcome_policy_for_reservation(
            reservation_id,
            outcome_kind=outcome_kind,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.post(
    "/runtime-execution-attempt-outcome-policies/reservations/"
    "{reservation_id}/from-submit-outcome-review",
    response_model=RuntimeExecutionAttemptOutcomePolicy,
)
async def record_runtime_execution_attempt_outcome_policy_from_submit_outcome_review(
    reservation_id: str,
    submit_outcome_review_id: Optional[str] = None,
) -> RuntimeExecutionAttemptOutcomePolicy:
    service = await _runtime_execution_intent_adapter_service()
    try:
        return await service.record_attempt_outcome_policy_from_submit_outcome_review(
            reservation_id,
            submit_outcome_review_id=submit_outcome_review_id,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.post(
    "/runtime-execution-order-lifecycle-handoff-drafts/authorizations/{authorization_id}",
    response_model=RuntimeExecutionOrderLifecycleHandoffDraft,
)
async def record_runtime_execution_order_lifecycle_handoff_draft_for_authorization(
    authorization_id: str,
) -> RuntimeExecutionOrderLifecycleHandoffDraft:
    service = await _runtime_execution_intent_adapter_service()
    try:
        return await service.record_order_lifecycle_handoff_draft_for_authorization(
            authorization_id
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.get(
    "/runtime-execution-order-lifecycle-adapter-previews/authorizations/{authorization_id}",
    response_model=RuntimeExecutionOrderLifecycleAdapterPreview,
)
async def runtime_execution_order_lifecycle_adapter_preview_for_authorization(
    authorization_id: str,
) -> RuntimeExecutionOrderLifecycleAdapterPreview:
    service = await _runtime_execution_intent_adapter_service()
    try:
        return await service.order_lifecycle_adapter_preview_for_authorization(
            authorization_id
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.get(
    "/runtime-execution-order-registration-draft-previews/authorizations/{authorization_id}",
    response_model=RuntimeExecutionOrderRegistrationDraftPreview,
)
async def runtime_execution_order_registration_draft_preview_for_authorization(
    authorization_id: str,
) -> RuntimeExecutionOrderRegistrationDraftPreview:
    service = await _runtime_execution_intent_adapter_service()
    try:
        return await service.order_registration_draft_preview_for_authorization(
            authorization_id
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.get(
    "/runtime-execution-local-registration-enablements/authorizations/{authorization_id}",
    response_model=RuntimeExecutionLocalRegistrationEnablementDecision,
)
async def runtime_execution_local_registration_enablement_for_authorization(
    authorization_id: str,
    trusted_submit_fact_snapshot_id: Optional[str] = None,
    submit_idempotency_policy_id: Optional[str] = None,
    attempt_outcome_policy_id: Optional[str] = None,
    protection_creation_failure_policy_id: Optional[str] = None,
    owner_real_submit_authorization_id: Optional[str] = None,
    order_lifecycle_adapter_enablement_id: Optional[str] = None,
    local_order_registration_enablement_id: Optional[str] = None,
    local_registration_action_authorization_id: Optional[str] = None,
    deployment_readiness_evidence_id: Optional[str] = None,
) -> RuntimeExecutionLocalRegistrationEnablementDecision:
    service = await _runtime_execution_intent_adapter_service()
    try:
        return await service.local_registration_enablement_decision_for_authorization(
            authorization_id,
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
            local_registration_action_authorization_id=(
                local_registration_action_authorization_id
            ),
            deployment_readiness_evidence_id=deployment_readiness_evidence_id,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.post(
    "/runtime-execution-local-registration-action-authorizations/"
    "authorizations/{authorization_id}",
    response_model=RuntimeExecutionLocalRegistrationActionAuthorization,
)
async def record_runtime_execution_local_registration_action_authorization(
    authorization_id: str,
    trusted_submit_fact_snapshot_id: Optional[str] = None,
    submit_idempotency_policy_id: Optional[str] = None,
    attempt_outcome_policy_id: Optional[str] = None,
    protection_creation_failure_policy_id: Optional[str] = None,
    owner_real_submit_authorization_id: Optional[str] = None,
    order_lifecycle_adapter_enablement_id: Optional[str] = None,
    local_order_registration_enablement_id: Optional[str] = None,
    owner_confirmed_for_local_registration_action: bool = False,
    owner_operator_id: str = "owner",
    reason: str = "owner confirmed scoped local registration action",
    deployment_readiness_evidence_id: Optional[str] = None,
    owner_confirmation_reference: Optional[str] = None,
    expires_at_ms: Optional[int] = None,
) -> RuntimeExecutionLocalRegistrationActionAuthorization:
    service = await _runtime_execution_intent_adapter_service()
    try:
        return await (
            service.record_local_registration_action_authorization_for_authorization(
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
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.post(
    "/runtime-execution-order-lifecycle-adapter-results/authorizations/{authorization_id}",
    response_model=RuntimeExecutionOrderLifecycleAdapterResult,
)
async def runtime_execution_order_lifecycle_adapter_result_for_authorization(
    authorization_id: str,
    order_lifecycle_adapter_enabled: bool = False,
    local_order_registration_enabled: bool = False,
    trusted_submit_fact_snapshot_id: Optional[str] = None,
    submit_idempotency_policy_id: Optional[str] = None,
    attempt_outcome_policy_id: Optional[str] = None,
    protection_creation_failure_policy_id: Optional[str] = None,
    owner_real_submit_authorization_id: Optional[str] = None,
    order_lifecycle_adapter_enablement_id: Optional[str] = None,
    local_order_registration_enablement_id: Optional[str] = None,
    local_registration_action_authorization_id: Optional[str] = None,
    deployment_readiness_evidence_id: Optional[str] = None,
) -> RuntimeExecutionOrderLifecycleAdapterResult:
    service = await _runtime_execution_intent_adapter_service()
    try:
        enablement = None
        if order_lifecycle_adapter_enabled or local_order_registration_enabled:
            enablement = (
                await service.local_registration_enablement_decision_for_authorization(
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
                    local_registration_action_authorization_id=(
                        local_registration_action_authorization_id
                    ),
                    deployment_readiness_evidence_id=deployment_readiness_evidence_id,
                )
            )
        return await service.order_lifecycle_adapter_result_for_authorization(
            authorization_id,
            order_lifecycle_adapter_enabled=order_lifecycle_adapter_enabled,
            local_order_registration_enabled=local_order_registration_enabled,
            local_registration_enablement_decision=enablement,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.get(
    "/runtime-execution-intent-local-order-bindings/authorizations/{authorization_id}",
    response_model=RuntimeExecutionIntentLocalOrderBinding,
)
async def runtime_execution_intent_local_order_binding_for_authorization(
    authorization_id: str,
) -> RuntimeExecutionIntentLocalOrderBinding:
    service = await _runtime_execution_intent_adapter_service()
    try:
        return await service.intent_local_order_binding_for_authorization(
            authorization_id
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.get(
    "/runtime-execution-exchange-submit-previews/authorizations/{authorization_id}",
    response_model=RuntimeExecutionExchangeSubmitPreview,
)
async def runtime_execution_exchange_submit_preview_for_authorization(
    authorization_id: str,
) -> RuntimeExecutionExchangeSubmitPreview:
    service = await _runtime_execution_intent_adapter_service()
    try:
        return await service.exchange_submit_preview_for_authorization(
            authorization_id
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.get(
    "/runtime-execution-exchange-submit-enablements/authorizations/{authorization_id}",
    response_model=RuntimeExecutionExchangeSubmitEnablementDecision,
)
async def runtime_execution_exchange_submit_enablement_for_authorization(
    authorization_id: str,
    trusted_submit_fact_snapshot_id: Optional[str] = None,
    submit_idempotency_policy_id: Optional[str] = None,
    attempt_outcome_policy_id: Optional[str] = None,
    protection_creation_failure_policy_id: Optional[str] = None,
    local_registration_enablement_decision_id: Optional[str] = None,
    owner_real_submit_authorization_id: Optional[str] = None,
    order_lifecycle_submit_enablement_id: Optional[str] = None,
    exchange_submit_adapter_enablement_id: Optional[str] = None,
    exchange_submit_action_authorization_id: Optional[str] = None,
    deployment_readiness_evidence_id: Optional[str] = None,
) -> RuntimeExecutionExchangeSubmitEnablementDecision:
    service = await _runtime_execution_intent_adapter_service()
    try:
        return await service.exchange_submit_enablement_decision_for_authorization(
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
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.get(
    "/runtime-execution-submit-rehearsals/authorizations/{authorization_id}",
    response_model=RuntimeExecutionSubmitRehearsal,
)
async def runtime_execution_submit_rehearsal_for_authorization(
    authorization_id: str,
    trusted_submit_fact_snapshot_id: Optional[str] = None,
    submit_idempotency_policy_id: Optional[str] = None,
    attempt_outcome_policy_id: Optional[str] = None,
    protection_creation_failure_policy_id: Optional[str] = None,
    local_registration_enablement_decision_id: Optional[str] = None,
    owner_real_submit_authorization_id: Optional[str] = None,
    order_lifecycle_submit_enablement_id: Optional[str] = None,
    exchange_submit_adapter_enablement_id: Optional[str] = None,
    exchange_submit_action_authorization_id: Optional[str] = None,
    deployment_readiness_evidence_id: Optional[str] = None,
) -> RuntimeExecutionSubmitRehearsal:
    service = await _runtime_execution_intent_adapter_service()
    try:
        enablement = (
            await service.exchange_submit_enablement_decision_for_authorization(
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
        return await service.submit_rehearsal_for_authorization(
            authorization_id,
            exchange_submit_enablement_decision=enablement,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.get(
    "/runtime-execution-first-real-submit-enablement-evidence/authorizations/"
    "{authorization_id}",
    response_model=RuntimeExecutionFirstRealSubmitEnablementEvidence,
)
async def runtime_execution_first_real_submit_enablement_evidence_for_authorization(
    authorization_id: str,
    strategy_family_confirmed: bool = False,
    implementation_source_confirmed: bool = False,
    required_facts_confirmed: bool = False,
    entry_policy_confirmed: bool = False,
    exit_policy_confirmed: bool = False,
    protection_policy_confirmed: bool = False,
    eligible_for_runtime_execution_confirmed: bool = False,
    right_tail_review_metrics_confirmed: bool = False,
    runtime_profile_confirmed: bool = False,
    owner_confirmation_mode_confirmed: bool = False,
    symbol_side_boundary_confirmed: bool = False,
    max_loss_budget_confirmed: bool = False,
    max_notional_boundary_confirmed: bool = False,
    max_active_positions_boundary_confirmed: bool = False,
    max_leverage_boundary_confirmed: bool = False,
    margin_usage_boundary_confirmed: bool = False,
    liquidation_buffer_boundary_confirmed: bool = False,
    protection_readiness_source_confirmed: bool = False,
    stale_fact_behavior_confirmed: bool = False,
    attempt_consumption_rule_confirmed: bool = False,
    budget_reservation_rule_confirmed: bool = False,
    trusted_active_position_source_confirmed: bool = False,
    trusted_account_fact_source_confirmed: bool = False,
    short_side_conservative_profile_confirmed: bool = False,
    budget_release_or_consume_rule_confirmed: bool = False,
    post_submit_budget_settlement_persistence_evidence_id: Optional[str] = None,
    attempt_outcome_policy_id: Optional[str] = None,
    protection_creation_failure_policy_confirmed: bool = False,
    protection_creation_failure_policy_id: Optional[str] = None,
    duplicate_submit_policy_confirmed: bool = False,
    submit_idempotency_policy_id: Optional[str] = None,
    trusted_submit_fact_snapshot_id: Optional[str] = None,
    local_registration_enablement_decision_id: Optional[str] = None,
    exchange_submit_enablement_decision_id: Optional[str] = None,
    owner_real_submit_authorization_id: Optional[str] = None,
    order_lifecycle_submit_enablement_id: Optional[str] = None,
    exchange_submit_adapter_enablement_id: Optional[str] = None,
    exchange_submit_action_authorization_id: Optional[str] = None,
    runtime_submit_rehearsal_id: Optional[str] = None,
    deployment_readiness_evidence_id: Optional[str] = None,
    deployment_readiness_confirmed: bool = False,
    explicit_owner_real_submit_authorization: bool = False,
) -> RuntimeExecutionFirstRealSubmitEnablementEvidence:
    from src.application.runtime_execution_first_real_submit_enablement_evidence_service import (
        RuntimeExecutionFirstRealSubmitEnablementEvidenceService,
    )

    try:
        service = RuntimeExecutionFirstRealSubmitEnablementEvidenceService(
            runtime_execution_intent_adapter_service=(
                await _runtime_execution_intent_adapter_service()
            ),
            promotion_gate_service=(
                await _strategy_runtime_promotion_gate_service()
            ),
        )
        return await service.preview_for_authorization(
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
            exchange_submit_enablement_decision_id=(
                exchange_submit_enablement_decision_id
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
            runtime_submit_rehearsal_id=runtime_submit_rehearsal_id,
            deployment_readiness_evidence_id=deployment_readiness_evidence_id,
            budget_release_or_consume_rule_confirmed=(
                budget_release_or_consume_rule_confirmed
            ),
            post_submit_budget_settlement_persistence_evidence_id=(
                post_submit_budget_settlement_persistence_evidence_id
            ),
            protection_creation_failure_policy_confirmed=(
                protection_creation_failure_policy_confirmed
            ),
            duplicate_submit_policy_confirmed=duplicate_submit_policy_confirmed,
            deployment_readiness_confirmed=deployment_readiness_confirmed,
            explicit_owner_real_submit_authorization=(
                explicit_owner_real_submit_authorization
            ),
            semantic_confirmations=StrategySemanticsConfirmationFacts(
                strategy_family_confirmed=strategy_family_confirmed,
                implementation_source_confirmed=implementation_source_confirmed,
                required_facts_confirmed=required_facts_confirmed,
                entry_policy_confirmed=entry_policy_confirmed,
                exit_policy_confirmed=exit_policy_confirmed,
                protection_policy_confirmed=protection_policy_confirmed,
                eligible_for_runtime_execution_confirmed=(
                    eligible_for_runtime_execution_confirmed
                ),
                right_tail_review_metrics_confirmed=(
                    right_tail_review_metrics_confirmed
                ),
            ),
            runtime_confirmations=RuntimeExecutionConfirmationFacts(
                runtime_profile_confirmed=runtime_profile_confirmed,
                owner_confirmation_mode_confirmed=(
                    owner_confirmation_mode_confirmed
                ),
                symbol_side_boundary_confirmed=symbol_side_boundary_confirmed,
                max_loss_budget_confirmed=max_loss_budget_confirmed,
                max_notional_boundary_confirmed=max_notional_boundary_confirmed,
                max_active_positions_boundary_confirmed=(
                    max_active_positions_boundary_confirmed
                ),
                max_leverage_boundary_confirmed=max_leverage_boundary_confirmed,
                margin_usage_boundary_confirmed=margin_usage_boundary_confirmed,
                liquidation_buffer_boundary_confirmed=(
                    liquidation_buffer_boundary_confirmed
                ),
                protection_readiness_source_confirmed=(
                    protection_readiness_source_confirmed
                ),
                stale_fact_behavior_confirmed=stale_fact_behavior_confirmed,
                attempt_consumption_rule_confirmed=(
                    attempt_consumption_rule_confirmed
                ),
                budget_reservation_rule_confirmed=(
                    budget_reservation_rule_confirmed
                ),
                trusted_active_position_source_confirmed=(
                    trusted_active_position_source_confirmed
                ),
                trusted_account_fact_source_confirmed=(
                    trusted_account_fact_source_confirmed
                ),
                short_side_conservative_profile_confirmed=(
                    short_side_conservative_profile_confirmed
                ),
            ),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.post(
    "/runtime-execution-exchange-submit-action-authorizations/authorizations/"
    "{authorization_id}",
    response_model=RuntimeExecutionExchangeSubmitActionAuthorization,
)
async def record_runtime_execution_exchange_submit_action_authorization(
    authorization_id: str,
    trusted_submit_fact_snapshot_id: Optional[str] = None,
    submit_idempotency_policy_id: Optional[str] = None,
    attempt_outcome_policy_id: Optional[str] = None,
    protection_creation_failure_policy_id: Optional[str] = None,
    local_registration_enablement_decision_id: Optional[str] = None,
    owner_real_submit_authorization_id: Optional[str] = None,
    order_lifecycle_submit_enablement_id: Optional[str] = None,
    exchange_submit_adapter_enablement_id: Optional[str] = None,
    owner_confirmed_for_exchange_submit_action: bool = True,
    owner_operator_id: str = OWNER_STANDING_AUTHORIZATION_OPERATOR_ID,
    reason: str = OWNER_STANDING_AUTHORIZATION_REASON,
    deployment_readiness_evidence_id: Optional[str] = None,
    owner_confirmation_reference: Optional[str] = (
        OWNER_STANDING_AUTHORIZATION_REFERENCE
    ),
    expires_at_ms: Optional[int] = None,
) -> RuntimeExecutionExchangeSubmitActionAuthorization:
    service = await _runtime_execution_intent_adapter_service()
    try:
        return await (
            service.record_exchange_submit_action_authorization_for_authorization(
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
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.post(
    "/runtime-execution-exchange-submit-adapter-results/authorizations/{authorization_id}",
    response_model=RuntimeExecutionExchangeSubmitAdapterResult,
)
async def runtime_execution_exchange_submit_adapter_result_for_authorization(
    authorization_id: str,
    exchange_submit_adapter_enabled: bool = False,
    trusted_submit_fact_snapshot_id: Optional[str] = None,
    submit_idempotency_policy_id: Optional[str] = None,
    attempt_outcome_policy_id: Optional[str] = None,
    protection_creation_failure_policy_id: Optional[str] = None,
    local_registration_enablement_decision_id: Optional[str] = None,
    owner_real_submit_authorization_id: Optional[str] = None,
    order_lifecycle_submit_enablement_id: Optional[str] = None,
    exchange_submit_adapter_enablement_id: Optional[str] = None,
    exchange_submit_action_authorization_id: Optional[str] = None,
    deployment_readiness_evidence_id: Optional[str] = None,
) -> RuntimeExecutionExchangeSubmitAdapterResult:
    service = await _runtime_execution_intent_adapter_service()
    try:
        enablement = (
            await service.exchange_submit_enablement_decision_for_authorization(
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
        return await service.exchange_submit_adapter_result_for_authorization(
            authorization_id,
            exchange_submit_adapter_enabled=exchange_submit_adapter_enabled,
            exchange_submit_enablement_decision=enablement,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.post(
    "/runtime-execution-exchange-submit-execution-results/authorizations/"
    "{authorization_id}",
    response_model=RuntimeExecutionExchangeSubmitExecutionResult,
)
async def runtime_execution_exchange_submit_execution_result_for_authorization(
    authorization_id: str,
    exchange_submit_execution_enabled: bool = False,
    exchange_submit_execution_mode: str = "disabled",
    trusted_submit_fact_snapshot_id: Optional[str] = None,
    submit_idempotency_policy_id: Optional[str] = None,
    attempt_outcome_policy_id: Optional[str] = None,
    protection_creation_failure_policy_id: Optional[str] = None,
    local_registration_enablement_decision_id: Optional[str] = None,
    owner_real_submit_authorization_id: Optional[str] = None,
    order_lifecycle_submit_enablement_id: Optional[str] = None,
    exchange_submit_adapter_enablement_id: Optional[str] = None,
    exchange_submit_action_authorization_id: Optional[str] = None,
    deployment_readiness_evidence_id: Optional[str] = None,
) -> RuntimeExecutionExchangeSubmitExecutionResult:
    service = await _runtime_execution_intent_adapter_service(
        include_runtime_exchange_gateway=(
            exchange_submit_execution_enabled
            and exchange_submit_execution_mode == "real_gateway_action"
        ),
    )
    try:
        enablement = (
            await service.exchange_submit_enablement_decision_for_authorization(
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
        return await service.exchange_submit_execution_result_for_authorization(
            authorization_id,
            exchange_submit_execution_enabled=exchange_submit_execution_enabled,
            exchange_submit_execution_mode=exchange_submit_execution_mode,
            exchange_submit_enablement_decision=enablement,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.post(
    "/runtime-execution-first-real-submit-actions/authorizations/"
    "{authorization_id}",
    response_model=RuntimeExecutionExchangeSubmitExecutionResult,
)
async def runtime_execution_first_real_submit_action_for_authorization(
    authorization_id: str,
    owner_confirmed_for_first_real_submit_action: bool = True,
    trusted_submit_fact_snapshot_id: Optional[str] = None,
    submit_idempotency_policy_id: Optional[str] = None,
    attempt_outcome_policy_id: Optional[str] = None,
    protection_creation_failure_policy_id: Optional[str] = None,
    local_registration_enablement_decision_id: Optional[str] = None,
    owner_real_submit_authorization_id: Optional[str] = None,
    order_lifecycle_submit_enablement_id: Optional[str] = None,
    exchange_submit_adapter_enablement_id: Optional[str] = None,
    exchange_submit_action_authorization_id: Optional[str] = None,
    deployment_readiness_evidence_id: Optional[str] = None,
) -> RuntimeExecutionExchangeSubmitExecutionResult:
    service = await _runtime_execution_intent_adapter_service(
        include_runtime_exchange_gateway=(
            owner_confirmed_for_first_real_submit_action
        ),
    )
    try:
        return await service.first_real_submit_action_for_authorization(
            authorization_id,
            owner_confirmed_for_first_real_submit_action=(
                owner_confirmed_for_first_real_submit_action
            ),
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
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.post(
    "/runtime-execution-submit-outcome-reviews/authorizations/{authorization_id}",
    response_model=RuntimeExecutionSubmitOutcomeReview,
)
async def record_runtime_execution_submit_outcome_review_for_authorization(
    authorization_id: str,
) -> RuntimeExecutionSubmitOutcomeReview:
    service = await _runtime_execution_intent_adapter_service()
    try:
        return await service.record_submit_outcome_review_for_authorization(
            authorization_id
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.post(
    "/runtime-execution-first-real-submit-outcome-accounting/"
    "authorizations/{authorization_id}",
    response_model=RuntimeExecutionFirstRealSubmitOutcomeAccounting,
)
async def record_runtime_execution_first_real_submit_outcome_accounting(
    authorization_id: str,
    reservation_id: str,
) -> RuntimeExecutionFirstRealSubmitOutcomeAccounting:
    service = await _runtime_execution_intent_adapter_service()
    try:
        return await (
            service
            .record_first_real_submit_outcome_accounting_for_authorization(
                authorization_id,
                reservation_id=reservation_id,
            )
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.post(
    "/runtime-execution-post-submit-budget-settlements/"
    "authorizations/{authorization_id}",
    response_model=RuntimeExecutionPostSubmitBudgetSettlement,
)
async def settle_runtime_execution_post_submit_budget_for_authorization(
    authorization_id: str,
    reservation_id: str,
) -> RuntimeExecutionPostSubmitBudgetSettlement:
    service = await _runtime_execution_intent_adapter_service()
    try:
        return await service.settle_first_real_submit_budget_for_authorization(
            authorization_id,
            reservation_id=reservation_id,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.post(
    "/runtime-execution-exchange-submit-recovery-resolutions/"
    "recovery-tasks/{recovery_task_id}",
    response_model=RuntimeExecutionExchangeSubmitRecoveryResolution,
)
async def record_runtime_execution_exchange_submit_recovery_resolution(
    recovery_task_id: str,
    owner_confirmed_recovery_resolved: bool = False,
    owner_confirmed_reconciliation_reviewed: bool = False,
    owner_confirmed_no_unprotected_position: bool = False,
    owner_confirmed_no_unresolved_exchange_order: bool = False,
    owner_confirmed_budget_reconciled_or_held: bool = False,
    owner_confirmed_attempt_consumed_or_accounted: bool = False,
    owner_operator_id: str = "owner",
    reason: str = "owner reviewed exchange submit recovery block",
    owner_confirmation_reference: Optional[str] = None,
    reconciliation_evidence_id: Optional[str] = None,
) -> RuntimeExecutionExchangeSubmitRecoveryResolution:
    service = await _runtime_execution_intent_adapter_service()
    try:
        return await service.record_exchange_submit_recovery_resolution(
            recovery_task_id,
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
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.post(
    "/runtime-execution-first-real-submit-evidence-preparations/"
    "authorizations/{authorization_id}",
    response_model=RuntimeExecutionFirstRealSubmitEvidencePreparation,
)
async def runtime_execution_first_real_submit_evidence_preparation_for_authorization(
    authorization_id: str,
    adapter_result_store_implemented: bool = False,
    real_adapter_boundary_implemented: bool = False,
) -> RuntimeExecutionFirstRealSubmitEvidencePreparation:
    from src.application.runtime_execution_first_real_submit_evidence_preparation_service import (
        RuntimeExecutionFirstRealSubmitEvidencePreparationService,
    )
    from src.application.runtime_execution_first_real_submit_enablement_evidence_service import (
        RuntimeExecutionFirstRealSubmitEnablementEvidenceService,
    )

    try:
        adapter_service = await _runtime_execution_intent_adapter_service()
        evidence_service = RuntimeExecutionFirstRealSubmitEnablementEvidenceService(
            runtime_execution_intent_adapter_service=adapter_service,
            promotion_gate_service=(
                await _strategy_runtime_promotion_gate_service()
            ),
        )
        service = RuntimeExecutionFirstRealSubmitEvidencePreparationService(
            runtime_execution_intent_adapter_service=adapter_service,
            trusted_submit_facts_assembly_service=(
                _runtime_execution_trusted_submit_facts_assembly_service()
            ),
            enablement_evidence_service=evidence_service,
        )
        return await service.prepare_for_authorization(
            authorization_id,
            adapter_result_store_implemented=adapter_result_store_implemented,
            real_adapter_boundary_implemented=real_adapter_boundary_implemented,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.post(
    "/runtime-execution-exchange-gateway-readiness",
    response_model=RuntimeExecutionExchangeGatewayReadiness,
)
async def record_runtime_execution_exchange_gateway_readiness(
    owner_confirmed_gateway_readiness_review: bool = False,
    owner_operator_id: str = "owner",
    reason: str = "owner reviewed runtime exchange gateway readiness",
    owner_confirmation_reference: Optional[str] = None,
) -> RuntimeExecutionExchangeGatewayReadiness:
    service = _runtime_exchange_gateway_readiness_service()
    try:
        return await service.record_readiness(
            owner_confirmed_gateway_readiness_review=(
                owner_confirmed_gateway_readiness_review
            ),
            owner_operator_id=owner_operator_id,
            reason=reason,
            owner_confirmation_reference=owner_confirmation_reference,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/runtime-execution-controlled-submit/authorizations/{authorization_id}",
    response_model=RuntimeExecutionControlledSubmitResult,
)
async def runtime_execution_controlled_submit_for_authorization(
    authorization_id: str,
    submit_enabled: bool = False,
) -> RuntimeExecutionControlledSubmitResult:
    service = await _runtime_execution_intent_adapter_service()
    try:
        return await service.record_controlled_submit_result_for_authorization(
            authorization_id,
            submit_enabled=submit_enabled,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc


@router.get("/operations-cockpit", response_model=TradingConsoleReadModelResponse)
async def operations_cockpit(
    symbol: Optional[str] = Query(default=None),
    include_exchange: bool = Query(default=True),
) -> TradingConsoleReadModelResponse:
    return await _service(include_exchange=include_exchange).operations_cockpit(
        symbol=symbol,
        include_exchange=include_exchange,
    )


@router.get("/account-risk", response_model=TradingConsoleReadModelResponse)
async def account_risk(
    symbol: Optional[str] = Query(default=None),
    include_exchange: bool = Query(default=False),
) -> TradingConsoleReadModelResponse:
    return await _service(include_exchange=include_exchange).account_risk(
        symbol=symbol,
        include_exchange=include_exchange,
    )


@router.get("/order-ledger", response_model=TradingConsoleReadModelResponse)
async def order_ledger(
    symbol: Optional[str] = Query(default=None),
    include_exchange: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
) -> TradingConsoleReadModelResponse:
    return await _service(include_exchange=include_exchange).order_ledger(
        symbol=symbol,
        include_exchange=include_exchange,
        limit=limit,
    )


@router.get("/protection-health", response_model=TradingConsoleReadModelResponse)
async def protection_health(
    symbol: Optional[str] = Query(default=None),
    include_exchange: bool = Query(default=False),
) -> TradingConsoleReadModelResponse:
    return await _service(include_exchange=include_exchange).protection_health(
        symbol=symbol,
        include_exchange=include_exchange,
    )


@router.get("/recovery-exception-state", response_model=TradingConsoleReadModelResponse)
async def recovery_exception_state(
    symbol: Optional[str] = Query(default=None),
    include_exchange: bool = Query(default=False),
) -> TradingConsoleReadModelResponse:
    return await _service(include_exchange=include_exchange).recovery_exception_state(
        symbol=symbol,
        include_exchange=include_exchange,
    )


@router.get("/authorization-state", response_model=TradingConsoleReadModelResponse)
async def authorization_state(
    symbol: Optional[str] = Query(default=None),
) -> TradingConsoleReadModelResponse:
    return await _service(include_exchange=False).authorization_state(symbol=symbol)


@router.get("/execution-control-state", response_model=TradingConsoleReadModelResponse)
async def execution_control_state(
    symbol: Optional[str] = Query(default=None),
    include_exchange: bool = Query(default=False),
) -> TradingConsoleReadModelResponse:
    return await _service(include_exchange=include_exchange).execution_control_state(
        symbol=symbol,
        include_exchange=include_exchange,
    )


@router.get("/review-state", response_model=TradingConsoleReadModelResponse)
async def review_state(
    symbol: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    include_exchange: bool = Query(default=False),
    previous_account_equity: Optional[Decimal] = Query(default=None, ge=Decimal("0")),
    current_account_equity: Optional[Decimal] = Query(default=None, ge=Decimal("0")),
    starting_capital_base: Optional[Decimal] = Query(default=None, ge=Decimal("0")),
    realized_trading_pnl: Decimal = Query(default=Decimal("0")),
    tolerance: Decimal = Query(default=Decimal("0"), ge=Decimal("0")),
    owner_capital_currency: str = Query(default="USDT", min_length=1, max_length=16),
) -> TradingConsoleReadModelResponse:
    return await _service(include_exchange=include_exchange).review_state(
        symbol=symbol,
        limit=limit,
        include_exchange=include_exchange,
        previous_account_equity=previous_account_equity,
        current_account_equity=current_account_equity,
        starting_capital_base=starting_capital_base,
        realized_trading_pnl=realized_trading_pnl,
        tolerance=tolerance,
        owner_capital_currency=owner_capital_currency,
    )


@router.get("/owner-capital-review", response_model=TradingConsoleReadModelResponse)
async def owner_capital_review(
    symbol: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    include_exchange: bool = Query(default=False),
    previous_account_equity: Optional[Decimal] = Query(default=None, ge=Decimal("0")),
    current_account_equity: Optional[Decimal] = Query(default=None, ge=Decimal("0")),
    starting_capital_base: Optional[Decimal] = Query(default=None, ge=Decimal("0")),
    realized_trading_pnl: Decimal = Query(default=Decimal("0")),
    tolerance: Decimal = Query(default=Decimal("0"), ge=Decimal("0")),
    owner_capital_currency: str = Query(default="USDT", min_length=1, max_length=16),
) -> TradingConsoleReadModelResponse:
    return await _service(include_exchange=include_exchange).owner_capital_review(
        symbol=symbol,
        limit=limit,
        include_exchange=include_exchange,
        previous_account_equity=previous_account_equity,
        current_account_equity=current_account_equity,
        starting_capital_base=starting_capital_base,
        realized_trading_pnl=realized_trading_pnl,
        tolerance=tolerance,
        owner_capital_currency=owner_capital_currency,
    )


@router.get("/right-tail-review", response_model=TradingConsoleReadModelResponse)
async def right_tail_review(
    symbol: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    include_exchange: bool = Query(default=False),
) -> TradingConsoleReadModelResponse:
    return await _service(include_exchange=include_exchange).right_tail_review(
        symbol=symbol,
        limit=limit,
        include_exchange=include_exchange,
    )


@router.get("/audit-chain", response_model=TradingConsoleReadModelResponse)
async def audit_chain(
    authorization_id: Optional[str] = Query(default=None),
    runtime_instance_id: Optional[str] = Query(default=None),
    trial_binding_id: Optional[str] = Query(default=None),
    strategy_family_id: Optional[str] = Query(default=None),
    strategy_family_version_id: Optional[str] = Query(default=None),
    signal_evaluation_id: Optional[str] = Query(default=None),
    order_candidate_id: Optional[str] = Query(default=None),
    intent_id: Optional[str] = Query(default=None),
    order_id: Optional[str] = Query(default=None),
    exchange_order_id: Optional[str] = Query(default=None),
    symbol: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> TradingConsoleReadModelResponse:
    return await _service(include_exchange=False).audit_chain(
        authorization_id=authorization_id,
        runtime_instance_id=runtime_instance_id,
        trial_binding_id=trial_binding_id,
        strategy_family_id=strategy_family_id,
        strategy_family_version_id=strategy_family_version_id,
        signal_evaluation_id=signal_evaluation_id,
        order_candidate_id=order_candidate_id,
        intent_id=intent_id,
        order_id=order_id,
        exchange_order_id=exchange_order_id,
        symbol=symbol,
        limit=limit,
    )


@router.get("/carrier-availability", response_model=TradingConsoleReadModelResponse)
async def carrier_availability(
    include_exchange: bool = Query(default=False),
) -> TradingConsoleReadModelResponse:
    return await _service(include_exchange=include_exchange).carrier_availability(include_exchange=include_exchange)


@router.get("/strategy-family-admission-state", response_model=TradingConsoleReadModelResponse)
async def strategy_family_admission_state(
    family: Optional[str] = Query(default=None),
    strategy_family_id: Optional[str] = Query(default=None),
    carrier_id: Optional[str] = Query(default=None),
    symbol: Optional[str] = Query(default=None),
    side: Optional[str] = Query(default=None),
    quantity: Optional[str] = Query(default=None),
    target_notional_usdt: Optional[str] = Query(default=None),
    current_price: Optional[str] = Query(default=None),
    min_notional: Optional[str] = Query(default=None),
    min_qty: Optional[str] = Query(default=None),
    qty_step: Optional[str] = Query(default=None),
    price_tick: Optional[str] = Query(default=None),
    max_notional: Optional[str] = Query(default=None),
    leverage: Optional[str] = Query(default=None),
    max_attempts: Optional[int] = Query(default=None, ge=1, le=10),
    protection_mode: Optional[str] = Query(default=None),
    review_requirement: Optional[str] = Query(default=None),
) -> TradingConsoleReadModelResponse:
    return await _service(include_exchange=False).strategy_family_admission_state(
        owner_scope={
            "family": family,
            "strategy_family_id": strategy_family_id,
            "carrier_id": carrier_id,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "target_notional_usdt": target_notional_usdt,
            "current_price": current_price,
            "min_notional": min_notional,
            "min_qty": min_qty,
            "qty_step": qty_step,
            "price_tick": price_tick,
            "max_notional": max_notional,
            "leverage": leverage,
            "max_attempts": max_attempts,
            "protection_mode": protection_mode,
            "review_requirement": review_requirement,
        }
    )


@router.get("/action-entry-readiness", response_model=TradingConsoleReadModelResponse)
async def action_entry_readiness(
    market_regime: Optional[str] = Query(default=None),
    symbol_preference: Optional[str] = Query(default=None),
    preferred_strategy_family: Optional[str] = Query(default=None),
    risk_tier: Optional[str] = Query(default=None),
    owner_risk_acceptance: Optional[str] = Query(default=None),
    note: Optional[str] = Query(default=None),
    family: Optional[str] = Query(default=None),
    strategy_family_id: Optional[str] = Query(default=None),
    carrier_id: Optional[str] = Query(default=None),
    symbol: Optional[str] = Query(default=None),
    side: Optional[str] = Query(default=None),
    quantity: Optional[str] = Query(default=None),
    target_notional_usdt: Optional[str] = Query(default=None),
    current_price: Optional[str] = Query(default=None),
    min_notional: Optional[str] = Query(default=None),
    min_qty: Optional[str] = Query(default=None),
    qty_step: Optional[str] = Query(default=None),
    price_tick: Optional[str] = Query(default=None),
    max_notional: Optional[str] = Query(default=None),
    leverage: Optional[str] = Query(default=None),
    max_attempts: Optional[int] = Query(default=None, ge=1, le=10),
    protection_mode: Optional[str] = Query(default=None),
    review_requirement: Optional[str] = Query(default=None),
) -> TradingConsoleReadModelResponse:
    return await _service(include_exchange=False).action_entry_readiness(
        owner_scope={
            "family": family,
            "strategy_family_id": strategy_family_id,
            "carrier_id": carrier_id,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "target_notional_usdt": target_notional_usdt,
            "current_price": current_price,
            "min_notional": min_notional,
            "min_qty": min_qty,
            "qty_step": qty_step,
            "price_tick": price_tick,
            "max_notional": max_notional,
            "leverage": leverage,
            "max_attempts": max_attempts,
            "protection_mode": protection_mode,
            "review_requirement": review_requirement,
        },
        market_input={
            "regime": market_regime,
            "symbol_preference": symbol_preference,
            "preferred_strategy_family": preferred_strategy_family,
            "side": side,
            "risk_tier": risk_tier,
            "owner_risk_acceptance": owner_risk_acceptance,
            "note": note,
        },
    )


@router.get("/owner-action-flow", response_model=TradingConsoleReadModelResponse)
async def owner_action_flow(
    include_exchange: bool = Query(default=False),
    market_regime: Optional[str] = Query(default=None),
    symbol_preference: Optional[str] = Query(default=None),
    preferred_strategy_family: Optional[str] = Query(default=None),
    risk_tier: Optional[str] = Query(default=None),
    owner_risk_acceptance: Optional[str] = Query(default=None),
    note: Optional[str] = Query(default=None),
    family: Optional[str] = Query(default=None),
    strategy_family_id: Optional[str] = Query(default=None),
    carrier_id: Optional[str] = Query(default=None),
    symbol: Optional[str] = Query(default=None),
    side: Optional[str] = Query(default=None),
    quantity: Optional[str] = Query(default=None),
    target_notional_usdt: Optional[str] = Query(default=None),
    current_price: Optional[str] = Query(default=None),
    min_notional: Optional[str] = Query(default=None),
    min_qty: Optional[str] = Query(default=None),
    qty_step: Optional[str] = Query(default=None),
    price_tick: Optional[str] = Query(default=None),
    max_notional: Optional[str] = Query(default=None),
    leverage: Optional[str] = Query(default=None),
    max_attempts: Optional[int] = Query(default=None, ge=1, le=10),
    protection_mode: Optional[str] = Query(default=None),
    review_requirement: Optional[str] = Query(default=None),
    custom_total_budget: Optional[str] = Query(default=None),
    custom_max_notional_per_action: Optional[str] = Query(default=None),
    custom_max_daily_loss: Optional[str] = Query(default=None),
    custom_capacity_fraction: Optional[str] = Query(default=None),
    custom_max_active_positions: Optional[int] = Query(default=None, ge=1, le=3),
    custom_max_attempts: Optional[int] = Query(default=None, ge=1, le=3),
    custom_max_leverage: Optional[str] = Query(default=None),
    custom_budget_authorization_id: Optional[str] = Query(default=None),
    custom_attempt_window_start_ms: Optional[int] = Query(default=None, ge=0),
) -> TradingConsoleReadModelResponse:
    return await _service(include_exchange=include_exchange).owner_action_flow(
        owner_scope={
            "family": family,
            "strategy_family_id": strategy_family_id,
            "carrier_id": carrier_id,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "target_notional_usdt": target_notional_usdt,
            "current_price": current_price,
            "min_notional": min_notional,
            "min_qty": min_qty,
            "qty_step": qty_step,
            "price_tick": price_tick,
            "max_notional": max_notional,
            "leverage": leverage,
            "max_attempts": max_attempts,
            "protection_mode": protection_mode,
            "review_requirement": review_requirement,
        },
        market_input={
            "regime": market_regime,
            "symbol_preference": symbol_preference,
            "preferred_strategy_family": preferred_strategy_family,
            "side": side,
            "risk_tier": risk_tier,
            "owner_risk_acceptance": owner_risk_acceptance,
            "note": note,
        },
        custom_budget={
            "total_budget": custom_total_budget,
            "max_notional_per_action": custom_max_notional_per_action,
            "max_daily_loss": custom_max_daily_loss,
            "capacity_fraction": custom_capacity_fraction,
            "max_active_positions": custom_max_active_positions,
            "max_attempts": custom_max_attempts,
            "max_leverage": custom_max_leverage,
            "budget_authorization_id": custom_budget_authorization_id,
            "attempt_window_start_ms": custom_attempt_window_start_ms,
        },
        include_exchange=include_exchange,
    )


@router.get("/budget-recommendation", response_model=TradingConsoleReadModelResponse)
async def budget_recommendation(
    include_exchange: bool = Query(default=False),
    risk_tier: str = Query(default="tiny"),
    symbol_preference: Optional[str] = Query(default=None),
    symbol: Optional[str] = Query(default=None),
    side: Optional[str] = Query(default=None),
    quantity: Optional[str] = Query(default=None),
    target_notional_usdt: Optional[str] = Query(default=None),
    current_price: Optional[str] = Query(default=None),
    min_notional: Optional[str] = Query(default=None),
    min_qty: Optional[str] = Query(default=None),
    qty_step: Optional[str] = Query(default=None),
    price_tick: Optional[str] = Query(default=None),
    max_notional: Optional[str] = Query(default=None),
    leverage: Optional[str] = Query(default=None),
    max_attempts: Optional[int] = Query(default=None, ge=1, le=10),
    protection_mode: Optional[str] = Query(default=None),
    review_requirement: Optional[str] = Query(default=None),
    custom_total_budget: Optional[str] = Query(default=None),
    custom_max_notional_per_action: Optional[str] = Query(default=None),
    custom_max_daily_loss: Optional[str] = Query(default=None),
    custom_capacity_fraction: Optional[str] = Query(default=None),
    custom_max_active_positions: Optional[int] = Query(default=None, ge=1, le=3),
    custom_max_attempts: Optional[int] = Query(default=None, ge=1, le=3),
    custom_max_leverage: Optional[str] = Query(default=None),
    custom_budget_authorization_id: Optional[str] = Query(default=None),
    custom_attempt_window_start_ms: Optional[int] = Query(default=None, ge=0),
) -> TradingConsoleReadModelResponse:
    return await _service(include_exchange=include_exchange).budget_recommendation(
        include_exchange=include_exchange,
        risk_tier=risk_tier,
        custom={
            "total_budget": custom_total_budget,
            "max_notional_per_action": custom_max_notional_per_action,
            "max_daily_loss": custom_max_daily_loss,
            "capacity_fraction": custom_capacity_fraction,
            "max_active_positions": custom_max_active_positions,
            "max_attempts": custom_max_attempts,
            "max_leverage": custom_max_leverage,
            "budget_authorization_id": custom_budget_authorization_id,
            "attempt_window_start_ms": custom_attempt_window_start_ms,
        },
        owner_selection={
            "symbol": symbol,
            "symbol_preference": symbol_preference,
            "side": side,
            "quantity": quantity,
            "target_notional_usdt": target_notional_usdt,
            "current_price": current_price,
            "min_notional": min_notional,
            "min_qty": min_qty,
            "qty_step": qty_step,
            "price_tick": price_tick,
            "max_notional": max_notional,
            "leverage": leverage,
            "max_attempts": max_attempts,
            "protection_mode": protection_mode,
            "review_requirement": review_requirement,
        },
    )


@router.get("/signal-marker-feed", response_model=TradingConsoleReadModelResponse)
async def signal_marker_feed(
    symbol: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> TradingConsoleReadModelResponse:
    return await _service(include_exchange=False).signal_marker_feed(symbol=symbol, limit=limit)


@router.get("/runtime-signal-watcher-status", response_model=TradingConsoleReadModelResponse)
async def runtime_signal_watcher_status(
    stale_after_seconds: int = Query(default=180, ge=30, le=3600),
) -> TradingConsoleReadModelResponse:
    return _service(include_exchange=False).runtime_signal_watcher_status(
        stale_after_seconds=stale_after_seconds,
    )


@router.get("/owner-console-source-readiness", response_model=TradingConsoleReadModelResponse)
async def owner_console_source_readiness(
    selected_strategy_group_id: Optional[str] = Query(default=None),
    max_symbols: int = Query(default=3, ge=1, le=3),
    stale_after_seconds: int = Query(default=180, ge=30, le=3600),
) -> TradingConsoleReadModelResponse:
    return _service(include_exchange=False).owner_console_source_readiness(
        selected_strategy_group_id=selected_strategy_group_id,
        max_symbols=max_symbols,
        stale_after_seconds=stale_after_seconds,
    )


@router.get("/strategygroup-runtime-pilot-status", response_model=TradingConsoleReadModelResponse)
async def strategygroup_runtime_pilot_status(
    selected_strategy_group_id: Optional[str] = Query(default=None),
    max_symbols: int = Query(default=3, ge=1, le=3),
    stale_after_seconds: int = Query(default=180, ge=30, le=3600),
) -> TradingConsoleReadModelResponse:
    return _service(include_exchange=False).strategygroup_runtime_pilot_status(
        selected_strategy_group_id=selected_strategy_group_id,
        max_symbols=max_symbols,
        stale_after_seconds=stale_after_seconds,
    )


@router.get("/strategy-group-handoff-intake", response_model=TradingConsoleReadModelResponse)
async def strategy_group_handoff_intake() -> TradingConsoleReadModelResponse:
    return _service(include_exchange=False).strategy_group_handoff_intake()


@router.get("/strategy-group-live-facts-readiness", response_model=TradingConsoleReadModelResponse)
async def strategy_group_live_facts_readiness() -> TradingConsoleReadModelResponse:
    return _service(include_exchange=False).strategy_group_live_facts_readiness()


@router.get("/api-classification", response_model=TradingConsoleReadModelResponse)
async def api_classification() -> TradingConsoleReadModelResponse:
    return _service(include_exchange=False).api_classification()


def _service(*, include_exchange: bool = False) -> TradingConsoleReadModelService:
    return TradingConsoleReadModelService(_dependencies(include_exchange=include_exchange))


def _dependencies(*, include_exchange: bool = False) -> TradingConsoleDependencies:
    from src.interfaces import api as api_module

    account_snapshot = None
    read_only_gateway = getattr(api_module, "_trading_console_read_only_exchange_gateway", None)
    if include_exchange and read_only_gateway is None and getattr(api_module, "_exchange_gateway", None) is None:
        read_only_gateway = _TradingConsoleLiveReadOnlyGateway()
        setattr(api_module, "_trading_console_read_only_exchange_gateway", read_only_gateway)
    if include_exchange:
        account_getter = getattr(api_module, "_account_getter", None)
        if callable(account_getter):
            try:
                account_snapshot = account_getter()
            except Exception:
                account_snapshot = None
        if account_snapshot is None:
            gateway = getattr(api_module, "_exchange_gateway", None)
            if gateway is None:
                gateway = read_only_gateway
            if gateway is not None and hasattr(gateway, "get_account_snapshot"):
                try:
                    account_snapshot = gateway.get_account_snapshot()
                except Exception:
                    account_snapshot = None

    order_repo = getattr(api_module, "_order_repo", None)
    position_repo = getattr(api_module, "_position_repo", None)
    execution_intent_repo = getattr(api_module, "_execution_intent_repo", None)
    execution_recovery_repo = getattr(api_module, "_execution_recovery_repo", None)
    live_lifecycle_review_repo = getattr(api_module, "_live_lifecycle_review_repo", None)
    if order_repo is None:
        order_repo = _cached_pg_repo(api_module, "_trading_console_pg_order_repo", _build_pg_order_repo)
    if position_repo is None:
        position_repo = _cached_pg_repo(api_module, "_trading_console_pg_position_repo", _build_pg_position_repo)
    if execution_intent_repo is None:
        execution_intent_repo = _cached_pg_repo(api_module, "_trading_console_pg_execution_intent_repo", _build_pg_execution_intent_repo)
    if execution_recovery_repo is None:
        execution_recovery_repo = _cached_pg_repo(api_module, "_trading_console_pg_execution_recovery_repo", _build_pg_execution_recovery_repo)
    if live_lifecycle_review_repo is None:
        live_lifecycle_review_repo = _cached_pg_repo(api_module, "_trading_console_pg_live_lifecycle_review_repo", _build_pg_live_lifecycle_review_repo)
    owner_capital_adjustment_repo = getattr(api_module, "_owner_capital_adjustment_repo", None)
    if owner_capital_adjustment_repo is None:
        owner_capital_adjustment_repo = _cached_pg_repo(
            api_module,
            "_trading_console_pg_owner_capital_adjustment_repo",
            _build_pg_owner_capital_adjustment_repo,
        )
    owner_capital_baseline_snapshot_repo = getattr(
        api_module,
        "_owner_capital_baseline_snapshot_repo",
        None,
    )
    if owner_capital_baseline_snapshot_repo is None:
        owner_capital_baseline_snapshot_repo = _cached_pg_repo(
            api_module,
            "_trading_console_pg_owner_capital_baseline_snapshot_repo",
            _build_pg_owner_capital_baseline_snapshot_repo,
        )

    return TradingConsoleDependencies(
        runtime_bound=bool(api_module.get_runtime_context() is not None),
        runtime_config_provider=getattr(api_module, "_runtime_config_provider", None),
        account_snapshot=account_snapshot,
        exchange_gateway=(
            getattr(api_module, "_exchange_gateway", None)
            or read_only_gateway
        ),
        order_repo=order_repo,
        position_repo=position_repo,
        execution_intent_repo=execution_intent_repo,
        execution_recovery_repo=execution_recovery_repo,
        audit_logger=getattr(api_module, "_audit_logger", None),
        signal_repo=getattr(api_module, "_signal_repo", None),
        brc_campaign_service=getattr(api_module, "_brc_campaign_service", None),
        live_lifecycle_review_repo=live_lifecycle_review_repo,
        owner_trial_flow_service=_owner_trial_flow_service(),
        campaign_state_service=getattr(api_module, "_campaign_state_service", None),
        multi_carrier_budget_authorization_service=_multi_carrier_budget_authorization_service(),
        owner_capital_adjustment_repo=owner_capital_adjustment_repo,
        owner_capital_baseline_snapshot_repo=owner_capital_baseline_snapshot_repo,
        global_kill_switch_service=getattr(api_module, "_global_kill_switch_service", None),
        startup_trading_guard_service=getattr(api_module, "_startup_trading_guard_service", None),
        startup_reconciliation_summary=getattr(api_module, "_startup_reconciliation_summary", None),
        execution_orchestrator=getattr(api_module, "_execution_orchestrator", None),
    )


async def _strategy_runtime_service() -> Any:
    from src.interfaces import api as api_module

    injected = getattr(api_module, "_strategy_runtime_service", None)
    if injected is not None:
        return injected
    try:
        from src.application.strategy_runtime_service import StrategyRuntimeInstanceService
        from src.infrastructure.pg_brc_admission_repository import PgBrcAdmissionRepository
        from src.infrastructure.pg_strategy_runtime_repository import (
            PgStrategyRuntimeRepository,
        )

        service = StrategyRuntimeInstanceService(
            runtime_repository=PgStrategyRuntimeRepository(),
            admission_repository=PgBrcAdmissionRepository(),
        )
        await service.initialize()
    except Exception as exc:  # pragma: no cover - configuration-specific fail-closed path
        raise HTTPException(
            status_code=503,
            detail="Strategy runtime repository unavailable; persistent PG facts are required.",
        ) from exc
    setattr(api_module, "_strategy_runtime_service", service)
    return service


async def _runtime_live_position_monitor_service() -> Any:
    from src.interfaces import api as api_module

    injected = getattr(api_module, "_runtime_live_position_monitor_service", None)
    if injected is not None:
        return injected

    position_repo = getattr(api_module, "_position_repo", None)
    if position_repo is None:
        position_repo = _cached_pg_repo(
            api_module,
            "_trading_console_pg_position_repo",
            _build_pg_position_repo,
        )
    order_repo = getattr(api_module, "_order_repo", None)
    if order_repo is None:
        order_repo = _cached_pg_repo(
            api_module,
            "_trading_console_pg_order_repo",
            _build_pg_order_repo,
        )
    if position_repo is None or order_repo is None:
        raise HTTPException(
            status_code=503,
            detail="Runtime live monitor requires persistent position and order facts.",
        )

    gateway = getattr(api_module, "_exchange_gateway", None)
    if gateway is None and _live_read_only_exchange_env_safe():
        gateway = getattr(
            api_module,
            "_trading_console_read_only_exchange_gateway",
            None,
        )
        if gateway is None:
            gateway = _TradingConsoleLiveReadOnlyGateway()
            setattr(
                api_module,
                "_trading_console_read_only_exchange_gateway",
                gateway,
            )

    reconciliation_service = None
    if gateway is not None:
        from src.application.reconciliation import ReconciliationService

        reconciliation_service = ReconciliationService(
            gateway=gateway,
            position_mgr=position_repo,
            order_repository=order_repo,
        )

    from src.application.runtime_live_position_monitor_service import (
        RuntimeLivePositionMonitorService,
    )

    service = RuntimeLivePositionMonitorService(
        runtime_repository=await _strategy_runtime_service(),
        position_repository=position_repo,
        order_repository=order_repo,
        exchange_gateway=gateway,
        reconciliation_service=reconciliation_service,
    )
    setattr(api_module, "_runtime_live_position_monitor_service", service)
    return service


async def _runtime_position_exit_plan_service() -> Any:
    from src.interfaces import api as api_module

    injected = getattr(api_module, "_runtime_position_exit_plan_service", None)
    if injected is not None:
        return injected

    position_repo = getattr(api_module, "_position_repo", None)
    if position_repo is None:
        position_repo = _cached_pg_repo(
            api_module,
            "_trading_console_pg_position_repo",
            _build_pg_position_repo,
        )
    order_repo = getattr(api_module, "_order_repo", None)
    if order_repo is None:
        order_repo = _cached_pg_repo(
            api_module,
            "_trading_console_pg_order_repo",
            _build_pg_order_repo,
        )
    if position_repo is None or order_repo is None:
        raise HTTPException(
            status_code=503,
            detail="Runtime exit plan requires persistent position and order facts.",
        )

    gateway = getattr(api_module, "_exchange_gateway", None)
    if gateway is None and _live_read_only_exchange_env_safe():
        gateway = getattr(
            api_module,
            "_trading_console_read_only_exchange_gateway",
            None,
        )
        if gateway is None:
            gateway = _TradingConsoleLiveReadOnlyGateway()
            setattr(
                api_module,
                "_trading_console_read_only_exchange_gateway",
                gateway,
            )

    reconciliation_service = None
    if gateway is not None:
        from src.application.reconciliation import ReconciliationService

        reconciliation_service = ReconciliationService(
            gateway=gateway,
            position_mgr=position_repo,
            order_repository=order_repo,
        )

    from src.application.runtime_position_exit_plan_service import (
        RuntimePositionExitPlanService,
    )

    service = RuntimePositionExitPlanService(
        runtime_repository=await _strategy_runtime_service(),
        position_repository=position_repo,
        order_repository=order_repo,
        exchange_gateway=gateway,
        reconciliation_service=reconciliation_service,
    )
    setattr(api_module, "_runtime_position_exit_plan_service", service)
    return service


async def _runtime_closed_trade_review_facts_service() -> Any:
    from src.interfaces import api as api_module

    injected = getattr(api_module, "_runtime_closed_trade_review_facts_service", None)
    if injected is not None:
        return injected

    position_repo = getattr(api_module, "_position_repo", None)
    if position_repo is None:
        position_repo = _cached_pg_repo(
            api_module,
            "_trading_console_pg_position_repo",
            _build_pg_position_repo,
        )
    order_repo = getattr(api_module, "_order_repo", None)
    if order_repo is None:
        order_repo = _cached_pg_repo(
            api_module,
            "_trading_console_pg_order_repo",
            _build_pg_order_repo,
        )
    if position_repo is None or order_repo is None:
        raise HTTPException(
            status_code=503,
            detail="Runtime closed-review facts require persistent position and order facts.",
        )

    from src.application.runtime_closed_trade_review_facts_service import (
        RuntimeClosedTradeReviewFactsService,
    )

    runtime_service = await _strategy_runtime_service()
    runtime_repository = (
        runtime_service
        if hasattr(runtime_service, "get")
        else _RuntimeRepositoryGetAdapter(runtime_service)
    )
    service = RuntimeClosedTradeReviewFactsService(
        runtime_repository=runtime_repository,
        position_repository=position_repo,
        order_repository=order_repo,
    )
    setattr(api_module, "_runtime_closed_trade_review_facts_service", service)
    return service


class _RuntimeRepositoryGetAdapter:
    def __init__(self, runtime_service: Any) -> None:
        self._runtime_service = runtime_service

    async def get(self, runtime_instance_id: str) -> Any:
        return await self._runtime_service.get_runtime(runtime_instance_id)


async def _runtime_post_close_followup_payload(
    *,
    runtime_instance_id: str,
    env_file: str | None,
) -> dict[str, Any]:
    from src.domain.runtime_post_close_followup import (
        build_runtime_post_close_followup_artifact,
    )
    from src.domain.runtime_reduce_only_close_authorization import (
        build_runtime_reduce_only_close_owner_evidence,
    )

    monitor_service = await _runtime_live_position_monitor_service()
    monitor = await monitor_service.build_monitor_artifact(
        runtime_instance_id=runtime_instance_id,
    )
    review_facts_service = await _runtime_closed_trade_review_facts_service()
    closed_review_facts_evidence = await review_facts_service.build_artifact(
        runtime_instance_id=runtime_instance_id,
    )
    owner_close_evidence = None
    if monitor.active_position_present:
        exit_plan_service = await _runtime_position_exit_plan_service()
        exit_plan = await exit_plan_service.build_exit_plan(
            runtime_instance_id=runtime_instance_id,
        )
        owner_close_evidence = build_runtime_reduce_only_close_owner_evidence(
            exit_plan=exit_plan,
            now_ms=int(time.time() * 1000),
        )
    closed_review = (
        None
        if monitor.active_position_present
        else await _runtime_latest_closed_lifecycle_review(
            runtime_instance_id=runtime_instance_id,
            symbol=monitor.symbol,
        )
    )
    closed_review_recorded = _runtime_lifecycle_review_is_closed_reviewed(
        closed_review
    )
    followup_evidence = build_runtime_post_close_followup_artifact(
        monitor=monitor,
        owner_close_artifact=owner_close_evidence,
        closed_review_facts_artifact=closed_review_facts_evidence,
        closed_review_recorded=closed_review_recorded,
        closed_review_id=(
            getattr(closed_review, "review_id", None)
            if closed_review_recorded
            else None
        ),
        now_ms=int(time.time() * 1000),
    )
    return {
        "scope": "runtime_post_close_followup_evidence",
        "status": followup_evidence.status.value,
        "followup_evidence": followup_evidence.model_dump(mode="json"),
        "source_monitor": monitor.model_dump(mode="json"),
        "owner_close_evidence": (
            owner_close_evidence.model_dump(mode="json")
            if owner_close_evidence is not None
            else None
        ),
        "closed_review_facts_evidence": closed_review_facts_evidence.model_dump(mode="json"),
        "closed_lifecycle_review": (
            closed_review.model_dump(mode="json")
            if closed_review is not None and hasattr(closed_review, "model_dump")
            else (
                dict(closed_review.__dict__)
                if closed_review is not None and hasattr(closed_review, "__dict__")
                else None
            )
        ),
        "post_close_followup_plan": _runtime_post_close_followup_plan(
            runtime_instance_id=runtime_instance_id,
            env_file=env_file,
            followup_evidence=followup_evidence,
        ),
        "safety_invariants": {
            "evidence_only": True,
            "api_read_only": True,
            "exchange_write_called": False,
            "review_record_created": False,
            "order_created": False,
            "order_cancelled": False,
            "order_amended": False,
            "position_closed": False,
            "runtime_state_mutated": False,
            "withdrawal_or_transfer_created": False,
        },
    }


async def _runtime_latest_closed_lifecycle_review(
    *,
    runtime_instance_id: str,
    symbol: str,
) -> Any | None:
    from src.interfaces import api as api_module

    repo = getattr(api_module, "_live_lifecycle_review_repo", None)
    if repo is None:
        repo = _cached_pg_repo(
            api_module,
            "_trading_console_pg_live_lifecycle_review_repo",
            _build_pg_live_lifecycle_review_repo,
        )
    if hasattr(repo, "initialize"):
        await repo.initialize()
    authorization_id = f"runtime-review:{runtime_instance_id}"
    if hasattr(repo, "get_latest"):
        return await repo.get_latest(authorization_id=authorization_id, symbol=symbol)
    if hasattr(repo, "list"):
        records = await repo.list(
            authorization_id=authorization_id,
            symbol=symbol,
            limit=1,
        )
        return records[0] if records else None
    return None


def _runtime_lifecycle_review_is_closed_reviewed(review: Any | None) -> bool:
    if review is None:
        return False
    return (
        str(getattr(review, "review_status", "") or "").lower() == "closed_reviewed"
        and str(getattr(review, "lifecycle_status", "") or "").lower()
        == "closed_reviewed"
    )


def _runtime_post_close_followup_plan(
    *,
    runtime_instance_id: str,
    env_file: str | None,
    followup_evidence: RuntimePostCloseFollowupArtifact,
) -> dict[str, Any]:
    def with_env_file(args: list[str]) -> list[str]:
        return [*args, "--env-file", env_file] if env_file else args

    followup_status = str(followup_evidence.status.value)
    post_close_complete = followup_status == "post_close_complete"
    standing_recovery_ready = (
        followup_status == "ready_for_standing_reduce_only_recovery"
    )
    close_args = with_env_file(
        [
            "scripts/runtime_owner_reduce_only_close_flow.py",
            "--runtime-instance-id",
            runtime_instance_id,
        ]
    )
    return {
        "scope": "runtime_post_close_followup_plan",
        "not_executed": True,
        "requires_explicit_owner_approval_before_execute": bool(
            followup_evidence.owner_close_approval_value
        ),
        "requires_official_operation_layer": standing_recovery_ready,
        "standing_recovery_authorization_scope": (
            followup_evidence.standing_recovery_authorization_scope
        ),
        "owner_close_approval_env": followup_evidence.owner_close_approval_env,
        "owner_close_approval_value": followup_evidence.owner_close_approval_value,
        "refresh_followup_command_args": [],
        "owner_close_dry_run_command_args": (
            close_args if followup_evidence.owner_close_approval_value else []
        ),
        "owner_close_execute_command_args": (
            []
            if standing_recovery_ready
            else [*close_args, "--execute-real-close"]
            if followup_evidence.owner_close_approval_value
            else []
        ),
        "operation_layer_reduce_only_recovery_args": (
            [
                "official_operation_layer",
                "prepare_reduce_only_recovery",
                "--runtime-instance-id",
                runtime_instance_id,
                "--standing-authorization-scope",
                str(followup_evidence.standing_recovery_authorization_scope),
            ]
            if standing_recovery_ready
            else []
        ),
        "closed_review_facts_refresh_command_args": [],
        "closed_review_command_args": (
            [] if post_close_complete else list(followup_evidence.closed_review_command_args)
        ),
        "post_close_required_sequence": (
            list(followup_evidence.required_steps)
            if post_close_complete
            else [
                "refresh_followup",
                *(
                    [
                        "prepare_official_operation_layer_reduce_only_recovery",
                        "run_action_time_finalgate_for_reduce_only_recovery",
                        "execute_reduce_only_recovery_through_operation_layer",
                    ]
                    if standing_recovery_ready
                    else [
                        "owner_authorize_exact_reduce_only_close_value",
                        "run_owner_close_execute_command",
                    ]
                ),
                "refresh_followup_until_flat",
                "run_closed_review_dry_run",
                "run_closed_review_apply_if_ready",
                "verify_next_attempt_gate",
            ]
        ),
        "safety_invariants": {
            "evidence_only": True,
            "command_plan_only": True,
            "exchange_write_called": False,
            "review_record_created": False,
            "order_created": False,
            "position_closed": False,
            "runtime_state_mutated": False,
            "withdrawal_or_transfer_created": False,
        },
    }


async def _runtime_next_attempt_observation_cycle_payload(
    *,
    runtime_instance_id: str,
    request: RuntimeNextAttemptObservationCycleRequest,
) -> dict[str, Any]:
    from src.application.readmodels import runtime_strategy_signal_input as signal_builder
    from src.application.runtime_strategy_signal_evaluation_service import (
        RuntimeStrategySignalEvaluationService,
        RuntimeStrategySignalEvaluationStatus,
    )

    runtime = await (await _strategy_runtime_service()).get_runtime(runtime_instance_id)
    if request.symbol and request.symbol != runtime.symbol:
        raise ValueError("signal symbol override must match runtime symbol")
    owner_scope = _runtime_next_attempt_owner_scope(runtime, request)
    owner_flow_response = await _service(
        include_exchange=request.include_exchange,
    ).owner_action_flow(
        owner_scope=owner_scope,
        include_exchange=request.include_exchange,
    )
    owner_flow_data = dict(owner_flow_response.data or {})
    owner_action_flow = dict(owner_flow_data.get("owner_action_flow") or {})
    post_action_state = dict(owner_flow_data.get("post_action_state") or {})
    next_attempt_gate = dict(
        owner_action_flow.get("next_attempt_gate")
        or post_action_state.get("next_attempt_gate")
        or {}
    )
    jit_audit = dict(owner_action_flow.get("just_in_time_lifecycle_audit") or {})
    gate_clear = (
        next_attempt_gate.get("status") == "clear_for_preflight"
        and next_attempt_gate.get("next_attempt_allowed_by_lifecycle") is True
        and jit_audit.get("can_execute_live") is not True
    )
    if not gate_clear:
        return {
            "scope": "runtime_next_attempt_observation_cycle_api",
            "status": "blocked",
            "blocked_stage": "next_attempt_gate",
            "runtime_instance_id": runtime_instance_id,
            "owner_action_scope": owner_scope,
            "include_exchange": request.include_exchange,
            "next_attempt_gate": next_attempt_gate,
            "just_in_time_lifecycle_audit": jit_audit,
            "signal_artifact": None,
            "action_time_ticket": None,
            "blockers": list(next_attempt_gate.get("blockers") or ["next_attempt_gate_blocked"]),
            "warnings": list(next_attempt_gate.get("warnings") or []),
            "observation_cycle_plan": {
                "next_step": next_attempt_gate.get("required_next_step")
                or "resolve_next_attempt_gate_blocker",
                "not_executed": True,
                "creates_action_time_ticket": False,
                "creates_execution_intent": False,
                "places_order": False,
                "calls_order_lifecycle": False,
            },
            "safety_invariants": _runtime_next_attempt_observation_safety(),
        }

    source = signal_builder.market_source(
        SimpleNamespace(
            source=request.source,
            timeout_seconds=request.timeout_seconds,
        )
    )
    one_hour = source.latest_closed_candles(
        symbol=runtime.symbol,
        timeframe="1h",
        limit=request.one_hour_limit,
    )
    four_hour = source.latest_closed_candles(
        symbol=runtime.symbol,
        timeframe="4h",
        limit=request.four_hour_limit,
    )
    now_ms = int(time.time() * 1000)
    signal_input = signal_builder.build_signal_input(
        runtime=runtime,
        one_hour=one_hour,
        four_hour=four_hour,
        source_id=getattr(source, "source_id", "unknown_read_only_market_source"),
        source_type=getattr(source, "source_type", "read_only_market_source"),
        evaluation_id=request.evaluation_id,
        playbook_id=request.playbook_id,
        now_ms=now_ms,
    )
    evaluation = RuntimeStrategySignalEvaluationService().evaluate(signal_input)
    signal_artifact = {
        "scope": "runtime_next_attempt_observation_cycle_signal_artifact",
        "status": (
            "ready_for_action_time_ticket_materialization"
            if evaluation.status
            == RuntimeStrategySignalEvaluationStatus.READY_FOR_SEMANTIC_BINDING
            else evaluation.status.value
        ),
        "runtime_instance_id": runtime.runtime_instance_id,
        "strategy_family_id": runtime.strategy_family_id,
        "strategy_family_version_id": runtime.strategy_family_version_id,
        "symbol": runtime.symbol,
        "side": runtime.side,
        "source": getattr(source, "source_id", "unknown_read_only_market_source"),
        "source_type": getattr(source, "source_type", "read_only_market_source"),
        "signal_input": signal_input.model_dump(mode="json"),
        "evaluation_result": evaluation.model_dump(mode="json"),
        "safety_invariants": {
            "market_data_read_only": True,
            "signal_evaluation_created": False,
            "order_candidate_created": False,
            "execution_intent_created": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_write_called": False,
            "runtime_state_mutated": False,
            "withdrawal_or_transfer_created": False,
        },
    }
    ready = (
        evaluation.status
        == RuntimeStrategySignalEvaluationStatus.READY_FOR_SEMANTIC_BINDING
    )
    if not ready:
        return {
            "scope": "runtime_next_attempt_observation_cycle_api",
            "status": "waiting_for_signal",
            "blocked_stage": "strategy_signal",
            "runtime_instance_id": runtime_instance_id,
            "owner_action_scope": owner_scope,
            "include_exchange": request.include_exchange,
            "next_attempt_gate": next_attempt_gate,
            "just_in_time_lifecycle_audit": jit_audit,
            "signal_artifact": signal_artifact,
            "action_time_ticket": None,
            "blockers": ["strategy_signal_not_ready_for_action_time_ticket"],
            "warnings": list(evaluation.warnings),
            "observation_cycle_plan": {
                "next_step": "observe_only_or_wait_for_next_closed_bar",
                "not_executed": True,
                "creates_action_time_ticket": False,
                "creates_execution_intent": False,
                "places_order": False,
                "calls_order_lifecycle": False,
            },
            "safety_invariants": _runtime_next_attempt_observation_safety(),
        }

    return {
        "scope": "runtime_next_attempt_observation_cycle_api",
        "status": "ready_for_action_time_ticket_materialization",
        "runtime_instance_id": runtime_instance_id,
        "owner_action_scope": owner_scope,
        "include_exchange": request.include_exchange,
        "next_attempt_gate": next_attempt_gate,
        "just_in_time_lifecycle_audit": jit_audit,
        "signal_artifact": signal_artifact,
        "action_time_ticket": None,
        "blockers": [],
        "warnings": list(evaluation.warnings),
        "observation_cycle_plan": {
            "next_step": "materialize_pg_promotion_action_time_lane",
            "api_action_time_ticket_endpoint": None,
            "pg_materialization_steps": [
                "materialize_pg_promotion_action_time_lane",
                "materialize_action_time_ticket",
            ],
            "cli_action_time_ticket_command_args": [],
            "signal_input_embedded": True,
            "not_executed": True,
            "creates_action_time_ticket": False,
            "creates_execution_intent": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "live_submit_allowed": False,
            "requires_official_final_gate": True,
            "uses_standing_runtime_authorization": True,
            "requires_explicit_owner_real_submit_authorization": False,
            "requires_official_operation_layer": True,
        },
        "safety_invariants": _runtime_next_attempt_observation_safety(),
    }


def _runtime_next_attempt_owner_scope(
    runtime: StrategyRuntimeInstance,
    request: RuntimeNextAttemptObservationCycleRequest,
) -> dict[str, Any]:
    boundary = runtime.boundary
    return {
        key: value
        for key, value in {
            "symbol": request.symbol or runtime.symbol,
            "side": request.side or runtime.side,
            "family": request.family,
            "strategy_family_id": request.strategy_family_id
            or runtime.strategy_family_id,
            "carrier_id": request.carrier_id
            or runtime.carrier_id
            or runtime.strategy_family_version_id,
            "quantity": request.quantity,
            "target_notional_usdt": request.target_notional_usdt,
            "max_notional": request.max_notional
            or _decimal_string(boundary.max_notional_per_attempt),
            "leverage": request.leverage or _decimal_string(boundary.max_leverage),
            "max_attempts": request.max_attempts or boundary.max_attempts,
            "protection_mode": request.protection_mode,
            "review_requirement": request.review_requirement
            or runtime.review_requirement.value,
        }.items()
        if value not in (None, "")
    }


def _runtime_next_attempt_observation_safety() -> dict[str, bool]:
    return {
        "api_non_executing": True,
        "allow_action_time_ticket_materialization": False,
        "local_registration_armed": False,
        "exchange_submit_armed": False,
        "execute_real_submit": False,
        "exchange_write_called": False,
        "signal_evaluation_created": False,
        "order_candidate_created": False,
        "execution_intent_created": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "attempt_counter_mutated": False,
        "runtime_budget_mutated": False,
        "position_opened": False,
        "position_closed": False,
        "withdrawal_or_transfer_created": False,
    }


async def _signal_evaluation_shadow_service() -> Any:
    from src.interfaces import api as api_module

    injected = getattr(api_module, "_signal_evaluation_shadow_service", None)
    if injected is not None:
        return injected
    try:
        from src.application.signal_evaluation_shadow_service import (
            SignalEvaluationShadowService,
        )
        from src.infrastructure.pg_signal_evaluation_repository import (
            PgSignalEvaluationRepository,
        )

        service = SignalEvaluationShadowService(
            repository=PgSignalEvaluationRepository(),
        )
        await service.initialize()
    except Exception as exc:  # pragma: no cover - configuration-specific fail-closed path
        raise HTTPException(
            status_code=503,
            detail="Signal evaluation repository unavailable; persistent PG facts are required.",
        ) from exc
    setattr(api_module, "_signal_evaluation_shadow_service", service)
    return service


async def _runtime_final_gate_preview_service() -> Any:
    from src.interfaces import api as api_module

    injected = getattr(api_module, "_runtime_final_gate_preview_service", None)
    if injected is not None:
        return injected
    from src.application.runtime_final_gate_preview_service import (
        RuntimeFinalGatePreviewService,
    )

    service = RuntimeFinalGatePreviewService(
        runtime_service=await _strategy_runtime_service(),
        signal_evaluation_service=await _signal_evaluation_shadow_service(),
        active_position_source=_cached_pg_repo(
            api_module,
            "_trading_console_pg_position_repo",
            _build_pg_position_repo,
        ),
    )
    setattr(api_module, "_runtime_final_gate_preview_service", service)
    return service


async def _runtime_execution_planning_service() -> Any:
    from src.interfaces import api as api_module

    injected = getattr(api_module, "_runtime_execution_planning_service", None)
    if injected is not None:
        return injected
    from src.application.runtime_execution_planning_service import (
        RuntimeExecutionPlanningService,
    )
    from src.infrastructure.pg_runtime_execution_intent_draft_repository import (
        PgRuntimeExecutionIntentDraftRepository,
    )

    service = RuntimeExecutionPlanningService(
        runtime_service=await _strategy_runtime_service(),
        signal_evaluation_service=await _signal_evaluation_shadow_service(),
        final_gate_preview_service=await _runtime_final_gate_preview_service(),
        intent_draft_repository=PgRuntimeExecutionIntentDraftRepository(),
    )
    setattr(api_module, "_runtime_execution_planning_service", service)
    return service


async def _runtime_strategy_signal_planning_service() -> Any:
    from src.interfaces import api as api_module

    injected = getattr(api_module, "_runtime_strategy_signal_planning_service", None)
    if injected is not None:
        return injected
    from src.application.runtime_strategy_signal_planning_service import (
        RuntimeStrategySignalPlanningService,
    )
    from src.application.strategy_runtime_fact_overlay_service import (
        StrategyRuntimeFactOverlayService,
    )
    from src.application.strategy_semantics_shadow_binding_service import (
        StrategySemanticsShadowBindingService,
    )

    position_source = getattr(api_module, "_position_repo", None)
    if position_source is None:
        position_source = _cached_pg_repo(
            api_module,
            "_trading_console_pg_position_repo",
            _build_pg_position_repo,
        )
    account_facts_source = _trading_console_runtime_account_facts_source(api_module)
    service = RuntimeStrategySignalPlanningService(
        semantics_binding_service=StrategySemanticsShadowBindingService(
            shadow_service=await _signal_evaluation_shadow_service(),
        ),
        runtime_execution_planning_service=await _runtime_execution_planning_service(),
        runtime_fact_overlay_service=StrategyRuntimeFactOverlayService(
            active_position_source=position_source,
            account_facts_source=account_facts_source,
            market_fact_source=_trading_console_public_market_fact_source(),
        ),
    )
    setattr(api_module, "_runtime_strategy_signal_planning_service", service)
    return service


async def _runtime_next_attempt_strategy_planning_service() -> Any:
    from src.interfaces import api as api_module

    injected = getattr(
        api_module,
        "_runtime_next_attempt_strategy_planning_service",
        None,
    )
    if injected is not None:
        return injected
    from src.application.runtime_next_attempt_strategy_planning_service import (
        RuntimeNextAttemptStrategyPlanningService,
    )

    service = RuntimeNextAttemptStrategyPlanningService(
        strategy_signal_planner=await _runtime_strategy_signal_planning_service(),
    )
    setattr(api_module, "_runtime_next_attempt_strategy_planning_service", service)
    return service


async def _runtime_post_submit_finalize_service() -> Any:
    from src.interfaces import api as api_module

    injected = getattr(api_module, "_runtime_post_submit_finalize_service", None)
    if injected is not None:
        return injected
    from src.application.runtime_post_submit_finalize_service import (
        RuntimePostSubmitFinalizeService,
    )
    from src.infrastructure.pg_runtime_execution_post_submit_budget_settlement_repository import (
        PgRuntimeExecutionPostSubmitBudgetSettlementRepository,
    )
    from src.infrastructure.pg_runtime_execution_submit_outcome_review_repository import (
        PgRuntimeExecutionSubmitOutcomeReviewRepository,
    )
    from src.infrastructure.pg_runtime_execution_attempt_reservation_repository import (
        PgRuntimeExecutionAttemptReservationRepository,
    )

    service = RuntimePostSubmitFinalizeService(
        adapter_service=await _runtime_execution_intent_adapter_service(),
        exchange_submit_execution_result_repository=(
            _runtime_exchange_submit_execution_result_repository()
        ),
        submit_outcome_review_repository=(
            PgRuntimeExecutionSubmitOutcomeReviewRepository()
        ),
        post_submit_budget_settlement_repository=(
            PgRuntimeExecutionPostSubmitBudgetSettlementRepository()
        ),
        attempt_reservation_repository=(
            PgRuntimeExecutionAttemptReservationRepository()
        ),
        runtime_service=await _strategy_runtime_service(),
    )
    setattr(api_module, "_runtime_post_submit_finalize_service", service)
    return service


def _runtime_exchange_submit_execution_result_repository() -> Any:
    from src.interfaces import api as api_module

    repo = getattr(
        api_module,
        "_runtime_exchange_submit_execution_result_repository",
        None,
    )
    if repo is not None:
        return repo
    from src.infrastructure.pg_runtime_execution_exchange_submit_execution_result_repository import (
        PgRuntimeExecutionExchangeSubmitExecutionResultRepository,
    )

    repo = PgRuntimeExecutionExchangeSubmitExecutionResultRepository()
    setattr(
        api_module,
        "_runtime_exchange_submit_execution_result_repository",
        repo,
    )
    return repo


async def _runtime_exchange_submit_execution_result_for_finalize(
    *,
    runtime_instance_id: str,
    authorization_id: str | None,
) -> RuntimeExecutionExchangeSubmitExecutionResult | None:
    repo = _runtime_exchange_submit_execution_result_repository()
    if authorization_id:
        return await repo.get_by_authorization_id(authorization_id)
    getter = getattr(repo, "get_latest_by_runtime_instance_id", None)
    if not callable(getter):
        return None
    return await getter(runtime_instance_id)


async def _runtime_active_positions_count_for_submit_result(
    result: RuntimeExecutionExchangeSubmitExecutionResult | None,
    *,
    expected_runtime_instance_id: str,
) -> int | None:
    if result is None:
        return None
    if result.runtime_instance_id != expected_runtime_instance_id:
        return None
    from src.interfaces import api as api_module

    position_repository = _cached_pg_repo(
        api_module,
        "_trading_console_pg_position_repo",
        _build_pg_position_repo,
    )
    if position_repository is None:
        return None
    positions = await position_repository.list_active(
        symbol=result.symbol,
        limit=200,
    )
    return len(positions)


async def _runtime_strategy_signal_scheduler_planning_service() -> Any:
    from src.interfaces import api as api_module

    injected = getattr(
        api_module,
        "_runtime_strategy_signal_scheduler_planning_service",
        None,
    )
    if injected is not None:
        return injected
    from src.application.runtime_strategy_signal_scheduler_assembly import (
        RuntimeStrategySignalSchedulerFactSources,
    )
    from src.application.runtime_strategy_signal_scheduler_planning_service import (
        RuntimeStrategySignalSchedulerPlanningService,
    )

    position_source = getattr(api_module, "_position_repo", None)
    if position_source is None:
        position_source = _cached_pg_repo(
            api_module,
            "_trading_console_pg_position_repo",
            _build_pg_position_repo,
        )
    market_fact_source = _trading_console_public_market_fact_source()
    service = RuntimeStrategySignalSchedulerPlanningService(
        planner=await _runtime_strategy_signal_planning_service(),
        fact_sources=RuntimeStrategySignalSchedulerFactSources(
            trusted_runtime_fact_overlay_configured=True,
            trusted_active_position_source_available=position_source is not None,
            trusted_account_facts_source_available=True,
            trusted_market_fact_source_available=market_fact_source is not None,
            source_scope="trading_console_internal_non_endpoint_sources",
            metadata={
                "pg_position_source_configured": position_source is not None,
                "cached_account_facts_source_configured": True,
                "public_market_fact_source_configured": market_fact_source is not None,
                "non_executing": True,
            },
        ),
    )
    setattr(api_module, "_runtime_strategy_signal_scheduler_planning_service", service)
    return service


async def _runtime_strategy_signal_intent_draft_source_service() -> Any:
    from src.interfaces import api as api_module

    injected = getattr(
        api_module,
        "_runtime_strategy_signal_intent_draft_source_service",
        None,
    )
    if injected is not None:
        return injected
    from src.application.runtime_strategy_signal_intent_draft_source_service import (
        RuntimeStrategySignalIntentDraftSourceService,
    )

    service = RuntimeStrategySignalIntentDraftSourceService(
        scheduler_planning_service=(
            await _runtime_strategy_signal_scheduler_planning_service()
        ),
        runtime_execution_planning_service=await _runtime_execution_planning_service(),
    )
    setattr(api_module, "_runtime_strategy_signal_intent_draft_source_service", service)
    return service


def _trading_console_public_market_fact_source() -> Any | None:
    """Return the optional public market fact source for B0 semantics.

    Disabled by default so normal Console reads do not acquire a new network
    dependency. When enabled, the source remains public/read-only and has no
    API key, account, order, withdrawal, transfer, or ExchangeGateway dependency.
    """

    enabled = os.environ.get("TRADING_CONSOLE_PUBLIC_MARKET_FACTS_ENABLED", "").strip().lower()
    if enabled not in {"1", "true", "yes"}:
        return None
    from src.infrastructure.binance_usdm_derivative_market_fact_source import (
        BinanceUsdmDerivativeMarketFactSource,
    )

    return BinanceUsdmDerivativeMarketFactSource()


async def _strategy_runtime_promotion_gate_service() -> Any:
    from src.interfaces import api as api_module

    injected = getattr(api_module, "_strategy_runtime_promotion_gate_service", None)
    if injected is not None:
        return injected
    from src.application.strategy_runtime_promotion_gate_service import (
        StrategyRuntimePromotionGateService,
    )

    service = StrategyRuntimePromotionGateService()
    setattr(api_module, "_strategy_runtime_promotion_gate_service", service)
    return service


async def _validate_exchange_submit_execution_result_proof(
    *,
    runtime_instance_id: str,
    exchange_submit_execution_result_id: str | None,
) -> tuple[bool, list[str], list[str]]:
    """Validate a durable first-real-submit result as submit technical proof.

    This is deliberately stricter than checking an id string. A consumed
    authorization cannot be rehearsed again because its local orders may now be
    FILLED/CANCELED with exchange artifacts. The durable execution-result row
    is the replay-safe proof for that path.
    """

    result_id = str(exchange_submit_execution_result_id or "").strip()
    if not result_id:
        return False, [], []

    from src.interfaces import api as api_module

    repo = getattr(
        api_module,
        "_runtime_exchange_submit_execution_result_repository",
        None,
    )
    if repo is None:
        from src.infrastructure.pg_runtime_execution_exchange_submit_execution_result_repository import (
            PgRuntimeExecutionExchangeSubmitExecutionResultRepository,
        )

        repo = PgRuntimeExecutionExchangeSubmitExecutionResultRepository()
        setattr(
            api_module,
            "_runtime_exchange_submit_execution_result_repository",
            repo,
        )

    result = await repo.get(result_id)
    if result is None:
        return False, ["exchange_submit_execution_result_not_found"], []

    blockers: list[str] = []
    warnings: list[str] = []
    if result.runtime_instance_id != runtime_instance_id:
        blockers.append("exchange_submit_execution_result_runtime_mismatch")
    if result.status != (
        RuntimeExecutionExchangeSubmitExecutionStatus
        .EXCHANGE_SUBMIT_ORDERS_SUBMITTED
    ):
        blockers.append("exchange_submit_execution_result_not_submitted")
    if result.blockers:
        blockers.append("exchange_submit_execution_result_has_blockers")
    if not result.exchange_submit_execution_enabled:
        blockers.append("exchange_submit_execution_result_execution_not_enabled")
    if not result.real_exchange_submit_adapter_executed:
        blockers.append("exchange_submit_execution_result_adapter_not_executed")
    if not result.exchange_called or not result.exchange_order_submitted:
        blockers.append("exchange_submit_execution_result_exchange_not_called")
    if not result.order_lifecycle_submit_called:
        blockers.append("exchange_submit_execution_result_lifecycle_not_called")
    if result.execution_intent_status_changed:
        blockers.append("exchange_submit_execution_result_changed_intent_status")
    if result.owner_bounded_execution_called:
        blockers.append("exchange_submit_execution_result_called_owner_bounded_execution")
    if result.withdrawal_or_transfer_created:
        blockers.append("exchange_submit_execution_result_created_withdrawal_or_transfer")
    if not result.entry_exchange_order_id:
        blockers.append("exchange_submit_execution_result_entry_exchange_id_missing")
    if not result.protection_exchange_order_ids:
        blockers.append(
            "exchange_submit_execution_result_protection_exchange_ids_missing"
        )
    if blockers:
        return False, _dedupe_text(blockers), warnings

    warnings.append("exchange_submit_execution_result_used_as_submit_proof")
    return True, [], warnings


def _dedupe_text(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


async def _runtime_execution_intent_adapter_service(
    *,
    include_runtime_exchange_gateway: bool = False,
) -> Any:
    from src.interfaces import api as api_module

    injected = getattr(api_module, "_runtime_execution_intent_adapter_service", None)
    if injected is not None:
        if include_runtime_exchange_gateway and getattr(
            injected,
            "_exchange_gateway",
            None,
        ) is None:
            gateway_binding = await _runtime_exchange_submit_gateway_binding(
                api_module,
            )
            injected._exchange_gateway = gateway_binding.get("gateway")
        return injected
    from src.application.runtime_execution_intent_adapter_service import (
        RuntimeExecutionIntentAdapterService,
    )
    from src.infrastructure.pg_execution_intent_repository import (
        PgExecutionIntentRepository,
    )
    from src.infrastructure.pg_runtime_execution_intent_draft_repository import (
        PgRuntimeExecutionIntentDraftRepository,
    )
    from src.infrastructure.pg_runtime_execution_submit_authorization_repository import (
        PgRuntimeExecutionSubmitAuthorizationRepository,
    )
    from src.infrastructure.pg_runtime_execution_controlled_submit_result_repository import (
        PgRuntimeExecutionControlledSubmitResultRepository,
    )
    from src.infrastructure.pg_runtime_execution_attempt_reservation_repository import (
        PgRuntimeExecutionAttemptReservationRepository,
    )
    from src.infrastructure.pg_runtime_execution_attempt_mutation_repository import (
        PgRuntimeExecutionAttemptMutationRepository,
    )
    from src.infrastructure.pg_runtime_execution_attempt_outcome_policy_repository import (
        PgRuntimeExecutionAttemptOutcomePolicyRepository,
    )
    from src.infrastructure.pg_runtime_execution_post_submit_budget_settlement_repository import (
        PgRuntimeExecutionPostSubmitBudgetSettlementRepository,
    )
    from src.infrastructure.pg_runtime_execution_protection_plan_repository import (
        PgRuntimeExecutionProtectionPlanRepository,
    )
    from src.infrastructure.pg_runtime_execution_order_lifecycle_handoff_repository import (
        PgRuntimeExecutionOrderLifecycleHandoffRepository,
    )
    from src.infrastructure.pg_runtime_execution_order_lifecycle_adapter_result_repository import (
        PgRuntimeExecutionOrderLifecycleAdapterResultRepository,
    )
    from src.infrastructure.pg_runtime_execution_submit_prerequisite_repositories import (
        PgRuntimeExecutionProtectionFailurePolicyRepository,
        PgRuntimeExecutionSubmitIdempotencyRepository,
        PgRuntimeExecutionTrustedSubmitFactsRepository,
    )
    from src.infrastructure.pg_runtime_execution_exchange_submit_adapter_result_repository import (
        PgRuntimeExecutionExchangeSubmitAdapterResultRepository,
    )
    from src.infrastructure.pg_runtime_execution_local_registration_action_authorization_repository import (
        PgRuntimeExecutionLocalRegistrationActionAuthorizationRepository,
    )
    from src.infrastructure.pg_runtime_execution_exchange_submit_action_authorization_repository import (
        PgRuntimeExecutionExchangeSubmitActionAuthorizationRepository,
    )
    from src.infrastructure.pg_runtime_execution_exchange_submit_execution_result_repository import (
        PgRuntimeExecutionExchangeSubmitExecutionResultRepository,
    )
    from src.infrastructure.pg_runtime_execution_submit_outcome_review_repository import (
        PgRuntimeExecutionSubmitOutcomeReviewRepository,
    )
    from src.infrastructure.pg_reconciliation_read_model_repository import (
        PgReconciliationReadModelRepository,
    )
    from src.infrastructure.pg_runtime_execution_exchange_submit_recovery_resolution_repository import (
        PgRuntimeExecutionExchangeSubmitRecoveryResolutionRepository,
    )
    from src.application.order_lifecycle_service import OrderLifecycleService
    from src.application.position_projection_service import PositionProjectionService

    order_repository = _cached_pg_repo(
        api_module,
        "_trading_console_pg_order_repo",
        _build_pg_order_repo,
    )
    position_repository = _cached_pg_repo(
        api_module,
        "_trading_console_pg_position_repo",
        _build_pg_position_repo,
    )
    exchange_gateway = None
    if include_runtime_exchange_gateway:
        gateway_binding = await _runtime_exchange_submit_gateway_binding(
            api_module,
        )
        exchange_gateway = gateway_binding.get("gateway")
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=PgRuntimeExecutionIntentDraftRepository(),
        intent_repository=PgExecutionIntentRepository(),
        submit_authorization_repository=PgRuntimeExecutionSubmitAuthorizationRepository(),
        controlled_submit_result_repository=PgRuntimeExecutionControlledSubmitResultRepository(),
        attempt_reservation_repository=PgRuntimeExecutionAttemptReservationRepository(),
        attempt_mutation_repository=PgRuntimeExecutionAttemptMutationRepository(),
        attempt_outcome_policy_repository=(
            PgRuntimeExecutionAttemptOutcomePolicyRepository()
        ),
        post_submit_budget_settlement_repository=(
            PgRuntimeExecutionPostSubmitBudgetSettlementRepository()
        ),
        protection_plan_repository=PgRuntimeExecutionProtectionPlanRepository(),
        order_lifecycle_handoff_repository=PgRuntimeExecutionOrderLifecycleHandoffRepository(),
        order_lifecycle_service=(
            OrderLifecycleService(repository=order_repository)
            if order_repository is not None
            else None
        ),
        order_lifecycle_adapter_result_repository=(
            PgRuntimeExecutionOrderLifecycleAdapterResultRepository()
        ),
        trusted_submit_facts_repository=PgRuntimeExecutionTrustedSubmitFactsRepository(),
        submit_idempotency_repository=PgRuntimeExecutionSubmitIdempotencyRepository(),
        protection_failure_policy_repository=(
            PgRuntimeExecutionProtectionFailurePolicyRepository()
        ),
        exchange_submit_adapter_result_repository=(
            PgRuntimeExecutionExchangeSubmitAdapterResultRepository()
        ),
        local_registration_action_authorization_repository=(
            PgRuntimeExecutionLocalRegistrationActionAuthorizationRepository()
        ),
        exchange_submit_action_authorization_repository=(
            PgRuntimeExecutionExchangeSubmitActionAuthorizationRepository()
        ),
        exchange_submit_execution_result_repository=(
            PgRuntimeExecutionExchangeSubmitExecutionResultRepository()
        ),
        submit_outcome_review_repository=(
            PgRuntimeExecutionSubmitOutcomeReviewRepository()
        ),
        reconciliation_read_model_repository=PgReconciliationReadModelRepository(),
        exchange_submit_recovery_resolution_repository=(
            PgRuntimeExecutionExchangeSubmitRecoveryResolutionRepository()
        ),
        exchange_gateway_readiness_repository=(
            _build_pg_runtime_exchange_gateway_readiness_repo()
        ),
        execution_recovery_repository=_cached_pg_repo(
            api_module,
            "_trading_console_pg_execution_recovery_repo",
            _build_pg_execution_recovery_repo,
        ),
        exchange_gateway=exchange_gateway,
        final_gate_preview_service=await _runtime_final_gate_preview_service(),
        runtime_service=await _strategy_runtime_service(),
        position_projection_service=(
            PositionProjectionService(position_repository)
            if position_repository is not None
            else None
        ),
    )
    setattr(api_module, "_runtime_execution_intent_adapter_service", service)
    return service


def _runtime_execution_trusted_submit_facts_assembly_service() -> Any:
    from src.application.runtime_execution_trusted_submit_fact_readers import (
        ConfiguredMarketRuleTrustedSubmitFactReader,
        ExchangeMarketRuleTrustedSubmitFactReader,
        LocalActivePositionTrustedSubmitFactReader,
        LocalOpenOrderTrustedSubmitFactReader,
        ReconciliationReadModelTrustedSubmitFactReader,
        RuntimeProtectionPlanTrustedSubmitFactReader,
        TrialReadinessAccountTrustedSubmitFactReader,
    )
    from src.application.runtime_execution_trusted_submit_facts_service import (
        RuntimeExecutionTrustedSubmitFactsAssemblyService,
    )
    from src.infrastructure.pg_runtime_execution_protection_plan_repository import (
        PgRuntimeExecutionProtectionPlanRepository,
    )
    from src.infrastructure.pg_runtime_execution_submit_prerequisite_repositories import (
        PgRuntimeExecutionTrustedSubmitFactsRepository,
    )
    from src.infrastructure.pg_reconciliation_read_model_repository import (
        PgReconciliationReadModelRepository,
    )
    from src.interfaces import api as api_module

    order_source = getattr(api_module, "_order_repo", None)
    if order_source is None:
        order_source = _cached_pg_repo(
            api_module,
            "_trading_console_pg_order_repo",
            _build_pg_order_repo,
        )
    position_source = getattr(api_module, "_position_repo", None)
    if position_source is None:
        position_source = _cached_pg_repo(
            api_module,
            "_trading_console_pg_position_repo",
            _build_pg_position_repo,
        )
    market_rule_provider = (
        getattr(api_module, "_trading_console_market_rule_snapshot_provider", None)
        or getattr(api_module, "_trading_console_market_rules", None)
    )
    market_rule_reader = (
        ConfiguredMarketRuleTrustedSubmitFactReader(market_rule_provider)
        if market_rule_provider is not None
        else ExchangeMarketRuleTrustedSubmitFactReader(
            getattr(api_module, "_exchange_gateway", None),
        )
    )

    return RuntimeExecutionTrustedSubmitFactsAssemblyService(
        repository=PgRuntimeExecutionTrustedSubmitFactsRepository(),
        account_fact_reader=TrialReadinessAccountTrustedSubmitFactReader(
            _TradingConsoleCachedAccountFactsSource(api_module),
        ),
        active_position_reader=LocalActivePositionTrustedSubmitFactReader(
            position_source,
        ),
        open_order_reader=LocalOpenOrderTrustedSubmitFactReader(order_source),
        protection_state_reader=RuntimeProtectionPlanTrustedSubmitFactReader(
            PgRuntimeExecutionProtectionPlanRepository(),
        ),
        market_rule_reader=market_rule_reader,
        reconciliation_reader=ReconciliationReadModelTrustedSubmitFactReader(
            PgReconciliationReadModelRepository(),
        ),
    )


def _runtime_exchange_gateway_readiness_service() -> Any:
    from src.application.runtime_exchange_gateway_readiness_service import (
        RuntimeExchangeGatewayReadinessService,
    )

    return RuntimeExchangeGatewayReadinessService(
        repository=_build_pg_runtime_exchange_gateway_readiness_repo(),
    )


async def _runtime_exchange_submit_gateway_binding(
    api_module: Any,
    *,
    gateway_factory: Any = None,
) -> dict[str, Any]:
    """Return the independent runtime-submit gateway only when explicitly enabled.

    This deliberately does not populate the legacy ``_exchange_gateway`` global
    or the one-shot ``_owner_bounded_exchange_gateway`` cache.
    """
    existing = getattr(api_module, "_runtime_exchange_submit_gateway", None)
    if existing is not None:
        return _runtime_exchange_submit_gateway_status(existing)

    blockers = _runtime_exchange_submit_gateway_env_blockers()
    if blockers:
        return {"status": "blocked_env", "gateway": None, "blockers": blockers}

    api_key = os.environ.get("EXCHANGE_API_KEY", "").strip()
    api_secret = os.environ.get("EXCHANGE_API_SECRET", "").strip()
    if not api_key or not api_secret:
        return {
            "status": "blocked_credentials_missing",
            "gateway": None,
            "blockers": ["exchange_credentials_missing"],
        }

    exchange_name = os.environ.get("EXCHANGE_NAME", "binance").strip() or "binance"
    if exchange_name.lower() != "binance":
        return {
            "status": "blocked_unsupported_exchange",
            "gateway": None,
            "blockers": [f"unsupported_exchange:{exchange_name}"],
        }

    if gateway_factory is None:
        from src.infrastructure.exchange_gateway import ExchangeGateway

        gateway_factory = ExchangeGateway
    gateway = gateway_factory(
        exchange_name=exchange_name,
        api_key=api_key,
        api_secret=api_secret,
        testnet=False,
    )
    try:
        await gateway.initialize()
        permission_check = getattr(gateway, "check_api_key_permissions", None)
        if callable(permission_check):
            await permission_check()
    except Exception as exc:
        close = getattr(gateway, "close", None)
        if callable(close):
            try:
                await close()
            except Exception:
                pass
        error_code = getattr(exc, "error_code", None)
        blockers = [
            f"runtime_exchange_gateway_initialization_failed:{type(exc).__name__}"
        ]
        if error_code:
            blockers.append(
                f"runtime_exchange_gateway_initialization_failed:{error_code}"
            )
        return {
            "status": "blocked_gateway_initialization_failed",
            "gateway": None,
            "blockers": blockers,
            "error_code": error_code,
            "error_type": type(exc).__name__,
        }

    setattr(api_module, "_runtime_exchange_submit_gateway", gateway)
    return _runtime_exchange_submit_gateway_status(gateway)


def _runtime_exchange_submit_gateway_env_blockers() -> list[str]:
    expected = {
        "TRADING_ENV": "live",
        "EXCHANGE_TESTNET": "false",
        "BRC_EXECUTION_PERMISSION_MAX": "order_allowed",
        "RUNTIME_CONTROL_API_ENABLED": "false",
        "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED": "false",
        GATEWAY_BINDING_ENABLED_ENV: "true",
    }
    blockers: list[str] = []
    for key, expected_value in expected.items():
        actual = os.environ.get(key, "").strip().lower()
        if actual != expected_value:
            blockers.append(f"{key.lower()}_not_{expected_value}")
    return blockers


def _runtime_exchange_submit_gateway_status(gateway: Any) -> dict[str, Any]:
    required = ["place_order", "fetch_ticker_price", "get_market_info"]
    missing = [
        f"runtime_gateway_missing_{name}"
        for name in required
        if not callable(getattr(gateway, name, None))
    ]
    return {
        "status": "ready" if not missing else "blocked_methods_missing",
        "gateway": gateway if not missing else None,
        "blockers": missing,
        "gateway_type": type(gateway).__name__,
    }


class _TradingConsoleCachedAccountFactsSource:
    """Trial-readiness account facts source from already-cached account state."""

    def __init__(self, api_module: Any) -> None:
        self._api_module = api_module

    async def read_trial_readiness_account_facts(
        self,
        *,
        candidate_id: str,
        symbol: str,
        side: str,
        generated_at_ms: int,
    ) -> Any:
        from src.application.trial_readiness_account_facts import (
            AccountFactsFreshnessStatus,
            AccountFactsReconciliationStatus,
            AccountFactsSourceType,
            TrialReadinessAccountFacts,
        )

        snapshot = _trading_console_cached_account_snapshot(self._api_module)
        if snapshot is None:
            return TrialReadinessAccountFacts(
                source_id="trading_console_cached_account_snapshot_unavailable",
                source_type=AccountFactsSourceType.UNAVAILABLE,
                freshness_status=AccountFactsFreshnessStatus.MISSING,
                reconciliation_status=AccountFactsReconciliationStatus.UNKNOWN,
                read_only_guarantee=True,
                external_call_performed=False,
                external_call_type="none",
                notes=(
                    f"candidate={candidate_id}",
                    f"symbol={symbol}",
                    f"side={side}",
                    "cached account snapshot unavailable",
                ),
            )

        timestamp_ms = _int_or_none(_read_snapshot_value(snapshot, "timestamp"))
        freshness = _cached_account_snapshot_freshness(
            timestamp_ms,
            generated_at_ms=generated_at_ms,
        )
        return TrialReadinessAccountFacts(
            account_id="trading_console_cached_account",
            account_type="cached_account_snapshot",
            source_id="trading_console_cached_account_snapshot",
            source_type=AccountFactsSourceType.CACHED_SNAPSHOT,
            account_equity=_decimal_or_none(
                _read_snapshot_value(snapshot, "total_balance")
            ),
            available_margin=_decimal_or_none(
                _read_snapshot_value(snapshot, "available_balance")
            ),
            timestamp_ms=timestamp_ms,
            freshness_status=freshness,
            reconciliation_status=AccountFactsReconciliationStatus.UNKNOWN,
            read_only_guarantee=True,
            external_call_performed=False,
            external_call_type="none",
            notes=(
                f"candidate={candidate_id}",
                f"symbol={symbol}",
                f"side={side}",
                "source=Trading Console cached account snapshot",
                "no account API call performed by this source",
            ),
        )


class _TradingConsoleLiveReadOnlyAccountFactsSource:
    """Trial-readiness account facts from the Trading Console read-only gateway."""

    def __init__(self, api_module: Any) -> None:
        self._api_module = api_module

    async def read_trial_readiness_account_facts(
        self,
        *,
        candidate_id: str,
        symbol: str,
        side: str,
        generated_at_ms: int,
    ) -> Any:
        from src.application.trial_readiness_account_facts import (
            AccountFactsFreshnessStatus,
            AccountFactsReconciliationStatus,
            AccountFactsSourceType,
            TrialReadinessAccountFacts,
        )

        if not _live_read_only_exchange_env_safe():
            return TrialReadinessAccountFacts(
                source_id="trading_console_live_read_only_env_not_safe",
                source_type=AccountFactsSourceType.UNAVAILABLE,
                freshness_status=AccountFactsFreshnessStatus.MISSING,
                reconciliation_status=AccountFactsReconciliationStatus.UNKNOWN,
                read_only_guarantee=True,
                external_call_performed=False,
                external_call_type="none",
                notes=(
                    f"candidate={candidate_id}",
                    f"symbol={symbol}",
                    f"side={side}",
                    "live read-only account facts env is not safe",
                ),
            )

        gateway = getattr(
            self._api_module,
            "_trading_console_read_only_exchange_gateway",
            None,
        )
        if gateway is None:
            gateway = _TradingConsoleLiveReadOnlyGateway()
            setattr(
                self._api_module,
                "_trading_console_read_only_exchange_gateway",
                gateway,
            )

        try:
            snapshot = await gateway.fetch_account_balance()
        except Exception as exc:
            return TrialReadinessAccountFacts(
                source_id="trading_console_live_read_only_account_read_failed",
                source_type=AccountFactsSourceType.UNAVAILABLE,
                freshness_status=AccountFactsFreshnessStatus.MISSING,
                reconciliation_status=AccountFactsReconciliationStatus.UNKNOWN,
                read_only_guarantee=True,
                external_call_performed=True,
                external_call_type="read_only_account_query",
                notes=(
                    f"candidate={candidate_id}",
                    f"symbol={symbol}",
                    f"side={side}",
                    f"read failed: {type(exc).__name__}",
                ),
            )

        if snapshot is None:
            return TrialReadinessAccountFacts(
                source_id="trading_console_live_read_only_account_snapshot_missing",
                source_type=AccountFactsSourceType.UNAVAILABLE,
                freshness_status=AccountFactsFreshnessStatus.MISSING,
                reconciliation_status=AccountFactsReconciliationStatus.UNKNOWN,
                read_only_guarantee=True,
                external_call_performed=True,
                external_call_type="read_only_account_query",
                notes=(
                    f"candidate={candidate_id}",
                    f"symbol={symbol}",
                    f"side={side}",
                    "read-only gateway returned no account snapshot",
                ),
            )

        timestamp_ms = (
            _int_or_none(_read_snapshot_value(snapshot, "timestamp"))
            or generated_at_ms
        )
        return TrialReadinessAccountFacts(
            account_id="trading_console_live_read_only_account",
            account_type="binance_usdt_futures",
            source_id="trading_console_live_read_only_exchange_gateway",
            source_type=AccountFactsSourceType.BINANCE_USDT_FUTURES_READ_ONLY,
            account_equity=_decimal_or_none(
                _read_snapshot_value(snapshot, "total_balance")
            ),
            available_margin=_decimal_or_none(
                _read_snapshot_value(snapshot, "available_balance")
            ),
            timestamp_ms=timestamp_ms,
            freshness_status=AccountFactsFreshnessStatus.FRESH,
            reconciliation_status=AccountFactsReconciliationStatus.CLEAN,
            read_only_guarantee=True,
            external_call_performed=True,
            external_call_type="read_only_account_query",
            notes=(
                f"candidate={candidate_id}",
                f"symbol={symbol}",
                f"side={side}",
                "source=Trading Console live read-only exchange gateway",
                "no order, transfer, withdrawal, or submit method is exposed",
            ),
        )


class _TradingConsoleUnavailableAccountFactsSource:
    """Fail-closed source for unsupported account fact source configuration."""

    def __init__(self, reason: str) -> None:
        self._reason = reason

    async def read_trial_readiness_account_facts(
        self,
        *,
        candidate_id: str,
        symbol: str,
        side: str,
        generated_at_ms: int,
    ) -> Any:
        from src.application.trial_readiness_account_facts import (
            AccountFactsFreshnessStatus,
            AccountFactsReconciliationStatus,
            AccountFactsSourceType,
            TrialReadinessAccountFacts,
        )

        return TrialReadinessAccountFacts(
            source_id="trading_console_account_facts_source_unavailable",
            source_type=AccountFactsSourceType.UNAVAILABLE,
            freshness_status=AccountFactsFreshnessStatus.MISSING,
            reconciliation_status=AccountFactsReconciliationStatus.UNKNOWN,
            read_only_guarantee=True,
            external_call_performed=False,
            external_call_type="none",
            notes=(
                f"candidate={candidate_id}",
                f"symbol={symbol}",
                f"side={side}",
                self._reason,
            ),
        )


def _trading_console_runtime_account_facts_source(api_module: Any) -> Any:
    mode = (
        os.environ.get("TRADING_CONSOLE_RUNTIME_ACCOUNT_FACTS_SOURCE", "")
        .strip()
        .lower()
    )
    if mode in {"", "cached", "cached_snapshot"}:
        return _TradingConsoleCachedAccountFactsSource(api_module)
    if mode in {"live_read_only", "exchange_read_only"}:
        return _TradingConsoleLiveReadOnlyAccountFactsSource(api_module)
    return _TradingConsoleUnavailableAccountFactsSource(
        f"unsupported account facts source mode: {mode}"
    )


def _runtime_view(runtime: StrategyRuntimeInstance) -> StrategyRuntimeInspectionView:
    boundary = runtime.boundary
    return StrategyRuntimeInspectionView(
        runtime_instance_id=runtime.runtime_instance_id,
        trial_binding_id=runtime.trial_binding_id,
        admission_decision_id=runtime.admission_decision_id,
        strategy_family_id=runtime.strategy_family_id,
        strategy_family_version_id=runtime.strategy_family_version_id,
        signal_evaluation_id=None,
        order_candidate_id=None,
        owner_risk_acceptance_id=runtime.owner_risk_acceptance_id,
        carrier_id=runtime.carrier_id,
        symbol=runtime.symbol,
        side=runtime.side,
        status=runtime.status,
        boundary=StrategyRuntimeBoundaryView(
            max_attempts=boundary.max_attempts,
            attempts_used=boundary.attempts_used,
            attempts_remaining=boundary.attempts_remaining,
            max_active_positions=boundary.max_active_positions,
            budget_reserved=_decimal_string(boundary.budget_reserved),
            max_notional_per_attempt=_decimal_string(boundary.max_notional_per_attempt),
            total_budget=_decimal_string(boundary.total_budget),
            budget_remaining=_decimal_string(boundary.budget_remaining),
            allowed_symbols=list(boundary.allowed_symbols),
            allowed_sides=list(boundary.allowed_sides),
            max_leverage=_decimal_string(boundary.max_leverage),
            requires_protection=boundary.requires_protection,
            requires_review=boundary.requires_review,
        ),
        policy_snapshot=runtime.policy_snapshot.model_dump(mode="json"),
        review_requirement=runtime.review_requirement.value,
        execution_enabled=runtime.execution_enabled,
        execution_mode=(
            "runtime_live_enabled"
            if runtime.execution_enabled and not runtime.shadow_mode
            else "shadow_disabled"
        ),
        shadow_mode=runtime.shadow_mode,
        created_at_ms=runtime.created_at_ms,
        updated_at_ms=runtime.updated_at_ms,
        activated_at_ms=runtime.activated_at_ms,
        expires_at_ms=runtime.expires_at_ms,
        revoked_at_ms=runtime.revoked_at_ms,
        closed_at_ms=runtime.closed_at_ms,
        metadata=dict(runtime.metadata),
    )


def _signal_evaluation_view(evaluation: SignalEvaluation) -> SignalEvaluationInspectionView:
    return SignalEvaluationInspectionView(
        signal_evaluation_id=evaluation.signal_evaluation_id,
        runtime_instance_id=evaluation.runtime_instance_id,
        trial_binding_id=evaluation.trial_binding_id,
        strategy_family_id=evaluation.strategy_family_id,
        strategy_family_version_id=evaluation.strategy_family_version_id,
        source_signal_id=evaluation.source_signal_id,
        symbol=evaluation.symbol,
        side=evaluation.side,
        status=evaluation.status,
        signal_observation_result=evaluation.decision.value,
        reason_codes=list(evaluation.reason_codes),
        rationale=evaluation.rationale,
        evidence_snapshot=dict(evaluation.evidence_snapshot),
        policy_snapshot=dict(evaluation.policy_snapshot),
        evaluated_at_ms=evaluation.evaluated_at_ms,
        expires_at_ms=evaluation.expires_at_ms,
        shadow_mode=evaluation.shadow_mode,
        execution_enabled=evaluation.execution_enabled,
        not_order=evaluation.not_order,
        not_execution_intent=evaluation.not_execution_intent,
        created_at_ms=evaluation.created_at_ms,
        updated_at_ms=evaluation.updated_at_ms,
        metadata=dict(evaluation.metadata),
    )


async def _order_candidate_view(candidate: OrderCandidate) -> OrderCandidateInspectionView:
    usage = await _order_candidate_usage(candidate.order_candidate_id)
    return OrderCandidateInspectionView(
        order_candidate_id=candidate.order_candidate_id,
        signal_evaluation_id=candidate.signal_evaluation_id,
        runtime_instance_id=candidate.runtime_instance_id,
        trial_binding_id=candidate.trial_binding_id,
        strategy_family_id=candidate.strategy_family_id,
        strategy_family_version_id=candidate.strategy_family_version_id,
        symbol=candidate.symbol,
        side=candidate.side,
        status=candidate.status,
        candidate_order_type=candidate.candidate_order_type,
        proposed_quantity=_decimal_string(candidate.proposed_quantity),
        intended_notional=_decimal_string(candidate.intended_notional),
        entry_price_reference=_decimal_string(candidate.entry_price_reference),
        risk_preview=candidate.risk_preview.model_dump(mode="json"),
        protection_preview=candidate.protection_preview.model_dump(mode="json"),
        rationale=candidate.rationale,
        evidence_refs=list(candidate.evidence_refs),
        shadow_mode=candidate.shadow_mode,
        execution_enabled=candidate.execution_enabled,
        candidate_executable=candidate.candidate_executable,
        not_order=candidate.not_order,
        not_execution_intent=candidate.not_execution_intent,
        **usage,
        created_at_ms=candidate.created_at_ms,
        updated_at_ms=candidate.updated_at_ms,
        expires_at_ms=candidate.expires_at_ms,
        metadata=dict(candidate.metadata),
    )


async def _order_candidate_usage(order_candidate_id: str) -> dict[str, Any]:
    from src.interfaces import api as api_module

    intent_repo = _cached_pg_repo(
        api_module,
        "_trading_console_pg_execution_intent_repo",
        _build_pg_execution_intent_repo,
    )
    auth_repo = _cached_pg_repo(
        api_module,
        "_trading_console_pg_runtime_submit_authorization_repo",
        _build_pg_runtime_submit_authorization_repo,
    )
    if intent_repo is None or auth_repo is None:
        return {
            "candidate_usage_status": "usage_lookup_unavailable",
            "candidate_reusable_for_new_attempt": False,
            "reuse_blocker": "candidate_usage_lookup_repository_unavailable",
        }
    try:
        intent = await intent_repo.get_by_order_candidate_id(order_candidate_id)
        authorization = await auth_repo.get_by_order_candidate_id(order_candidate_id)
    except Exception as exc:
        return {
            "candidate_usage_status": "usage_lookup_unavailable",
            "candidate_reusable_for_new_attempt": False,
            "reuse_blocker": f"candidate_usage_lookup_failed:{type(exc).__name__}",
        }

    if authorization is not None:
        return {
            "execution_intent_id": authorization.execution_intent_id,
            "execution_intent_status": (
                _status_value(intent.status) if intent is not None else None
            ),
            "submit_authorization_id": authorization.authorization_id,
            "submit_authorization_status": _status_value(authorization.status),
            "candidate_usage_status": "submit_authorization_recorded",
            "candidate_reusable_for_new_attempt": False,
            "reuse_blocker": "order_candidate_already_has_submit_authorization",
        }
    if intent is not None:
        return {
            "execution_intent_id": intent.id,
            "execution_intent_status": _status_value(intent.status),
            "candidate_usage_status": "execution_intent_recorded",
            "candidate_reusable_for_new_attempt": False,
            "reuse_blocker": "order_candidate_already_has_execution_intent",
        }
    return {
        "candidate_usage_status": "unused",
        "candidate_reusable_for_new_attempt": True,
        "reuse_blocker": None,
    }


def _status_value(value: Any) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))


def _decimal_string(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _trading_console_cached_account_snapshot(api_module: Any) -> Any:
    account_getter = getattr(api_module, "_account_getter", None)
    if callable(account_getter):
        try:
            return account_getter()
        except Exception:
            return None
    gateway = getattr(api_module, "_exchange_gateway", None)
    if gateway is not None and hasattr(gateway, "get_account_snapshot"):
        try:
            return gateway.get_account_snapshot()
        except Exception:
            return None
    read_only_gateway = getattr(api_module, "_trading_console_read_only_exchange_gateway", None)
    if read_only_gateway is not None and hasattr(read_only_gateway, "get_account_snapshot"):
        try:
            return read_only_gateway.get_account_snapshot()
        except Exception:
            return None
    return None


def _cached_account_snapshot_freshness(
    timestamp_ms: int | None,
    *,
    generated_at_ms: int,
) -> Any:
    from src.application.trial_readiness_account_facts import (
        AccountFactsFreshnessStatus,
    )

    if timestamp_ms is None:
        return AccountFactsFreshnessStatus.MISSING
    if timestamp_ms > generated_at_ms + 60_000:
        return AccountFactsFreshnessStatus.UNKNOWN
    if generated_at_ms - timestamp_ms <= 5 * 60 * 1000:
        return AccountFactsFreshnessStatus.FRESH
    return AccountFactsFreshnessStatus.STALE


def _read_snapshot_value(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _decimal_or_none(value: Any) -> Any:
    if value is None:
        return None
    from decimal import Decimal, InvalidOperation

    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _cached_pg_repo(api_module: Any, attr_name: str, factory: Any) -> Optional[Any]:
    repo = getattr(api_module, attr_name, None)
    if repo is not None:
        return repo
    try:
        repo = factory()
    except Exception:
        return None
    setattr(api_module, attr_name, repo)
    return repo


def _build_pg_order_repo() -> Any:
    from src.infrastructure.pg_order_repository import PgOrderRepository

    return PgOrderRepository()


def _build_pg_position_repo() -> Any:
    from src.infrastructure.pg_position_repository import PgPositionRepository

    return PgPositionRepository()


def _build_pg_execution_intent_repo() -> Any:
    from src.infrastructure.pg_execution_intent_repository import PgExecutionIntentRepository

    return PgExecutionIntentRepository()


def _build_pg_runtime_submit_authorization_repo() -> Any:
    from src.infrastructure.pg_runtime_execution_submit_authorization_repository import (
        PgRuntimeExecutionSubmitAuthorizationRepository,
    )

    return PgRuntimeExecutionSubmitAuthorizationRepository()


def _build_pg_execution_recovery_repo() -> Any:
    from src.infrastructure.pg_execution_recovery_repository import PgExecutionRecoveryRepository

    return PgExecutionRecoveryRepository()


def _build_pg_runtime_exchange_gateway_readiness_repo() -> Any:
    from src.infrastructure.pg_runtime_execution_exchange_gateway_readiness_repository import (
        PgRuntimeExecutionExchangeGatewayReadinessRepository,
    )

    return PgRuntimeExecutionExchangeGatewayReadinessRepository()


def _build_pg_runtime_exchange_submit_recovery_resolution_repo() -> Any:
    from src.infrastructure.pg_runtime_execution_exchange_submit_recovery_resolution_repository import (
        PgRuntimeExecutionExchangeSubmitRecoveryResolutionRepository,
    )

    return PgRuntimeExecutionExchangeSubmitRecoveryResolutionRepository()


def _build_pg_live_lifecycle_review_repo() -> Any:
    from src.infrastructure.pg_live_lifecycle_review_repository import PgLiveLifecycleReviewRepository

    return PgLiveLifecycleReviewRepository()


def _build_pg_owner_capital_adjustment_repo() -> Any:
    from src.infrastructure.pg_owner_capital_adjustment_repository import (
        PgOwnerCapitalAdjustmentRepository,
    )

    return PgOwnerCapitalAdjustmentRepository()


def _build_pg_owner_capital_baseline_snapshot_repo() -> Any:
    from src.infrastructure.pg_owner_capital_baseline_snapshot_repository import (
        PgOwnerCapitalBaselineSnapshotRepository,
    )

    return PgOwnerCapitalBaselineSnapshotRepository()


def _owner_trial_flow_service() -> Optional[Any]:
    from src.interfaces import api as api_module

    injected = getattr(api_module, "_owner_trial_flow_service", None)
    if injected is not None:
        return injected
    try:
        from src.interfaces.api_brc_console import _owner_trial_flow_service_instance

        return _owner_trial_flow_service_instance()
    except Exception:
        return None


def _multi_carrier_budget_authorization_service() -> Optional[Any]:
    from src.interfaces import api as api_module

    injected = getattr(api_module, "_multi_carrier_budget_authorization_service", None)
    if injected is not None:
        return injected
    try:
        from src.interfaces.api_brc_console import _multi_carrier_budget_authorization_service_instance

        return _multi_carrier_budget_authorization_service_instance()
    except Exception:
        return None


async def close_runtime_exchange_submit_gateway(api_module: Any | None = None) -> None:
    if api_module is None:
        from src.interfaces import api as api_module

    gateway = getattr(api_module, "_runtime_exchange_submit_gateway", None)
    setattr(api_module, "_runtime_exchange_submit_gateway", None)
    service = getattr(api_module, "_runtime_execution_intent_adapter_service", None)
    if service is not None and hasattr(service, "_exchange_gateway"):
        service._exchange_gateway = None
    if gateway is not None and hasattr(gateway, "close"):
        await gateway.close()


async def close_trading_console_read_only_exchange_gateway() -> None:
    from src.interfaces import api as api_module

    gateway = getattr(api_module, "_trading_console_read_only_exchange_gateway", None)
    setattr(api_module, "_trading_console_read_only_exchange_gateway", None)
    if gateway is not None and hasattr(gateway, "close"):
        await gateway.close()
