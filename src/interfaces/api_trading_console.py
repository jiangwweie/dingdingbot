"""Trading Console Owner action-entry and non-mutating product API namespace."""

from __future__ import annotations

import asyncio
import os
import time
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.application.readmodels.trading_console import (
    TradingConsoleDependencies,
    TradingConsoleReadModelResponse,
    TradingConsoleReadModelService,
)
from src.domain.execution_intent import ExecutionIntent
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
from src.domain.runtime_execution_order_lifecycle_handoff import (
    RuntimeExecutionOrderLifecycleHandoffDraft,
)
from src.domain.runtime_execution_order_lifecycle_adapter import (
    RuntimeExecutionOrderLifecycleAdapterPreview,
)
from src.domain.runtime_execution_attempt_reservation import (
    RuntimeExecutionAttemptReservation,
    RuntimeExecutionAttemptReservationPreview,
)
from src.domain.runtime_execution_attempt_mutation import (
    RuntimeExecutionAttemptMutation,
)
from src.domain.runtime_execution_plan import RuntimeExecutionIntentDraft, RuntimeExecutionPlan
from src.domain.runtime_final_gate_preview import RuntimeFinalGatePreview
from src.domain.strategy_runtime_promotion_gate import (
    FirstRealSubmitConfirmationFacts,
    RuntimeExecutionConfirmationFacts,
    StrategyRuntimePromotionGateResult,
    StrategyRuntimePromotionScope,
    StrategySemanticsConfirmationFacts,
)
from src.domain.strategy_runtime import StrategyRuntimeInstance, StrategyRuntimeInstanceStatus
from src.interfaces.operator_auth import require_operator_session


router = APIRouter(
    prefix="/api/trading-console",
    tags=["Trading Console"],
    dependencies=[Depends(require_operator_session)],
)


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
    decision: str
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
    attempt_consumption_rule_confirmed: bool = False,
    budget_reservation_rule_confirmed: bool = False,
    trusted_active_position_source_confirmed: bool = False,
    trusted_account_fact_source_confirmed: bool = False,
    short_side_conservative_profile_confirmed: bool = False,
    budget_release_or_consume_rule_confirmed: bool = False,
    protection_creation_failure_policy_confirmed: bool = False,
    duplicate_submit_policy_confirmed: bool = False,
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
        protection_creation_failure_policy_confirmed=(
            protection_creation_failure_policy_confirmed
        ),
        duplicate_submit_policy_confirmed=duplicate_submit_policy_confirmed,
        deployment_readiness_confirmed=deployment_readiness_confirmed,
        explicit_owner_real_submit_authorization=(
            explicit_owner_real_submit_authorization
        ),
    )


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
    attempt_consumption_rule_confirmed: bool = False,
    budget_reservation_rule_confirmed: bool = False,
    trusted_active_position_source_confirmed: bool = False,
    trusted_account_fact_source_confirmed: bool = False,
    short_side_conservative_profile_confirmed: bool = False,
    budget_release_or_consume_rule_confirmed: bool = False,
    protection_creation_failure_policy_confirmed: bool = False,
    duplicate_submit_policy_confirmed: bool = False,
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
                protection_creation_failure_policy_confirmed=(
                    protection_creation_failure_policy_confirmed
                ),
                duplicate_submit_policy_confirmed=duplicate_submit_policy_confirmed,
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
    return [_order_candidate_view(item) for item in candidates]


@router.get(
    "/order-candidates/{order_candidate_id}",
    response_model=OrderCandidateInspectionView,
)
async def get_order_candidate(
    order_candidate_id: str,
) -> OrderCandidateInspectionView:
    service = await _signal_evaluation_shadow_service()
    try:
        return _order_candidate_view(await service.get_order_candidate(order_candidate_id))
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
    owner_reviewed: bool = Query(default=False),
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
    owner_reviewed: bool = Query(default=False),
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
    owner_reviewed: bool = Query(default=False),
    owner_confirmed_for_intent: bool = Query(default=False),
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
    owner_reviewed: bool = Query(default=False),
    owner_confirmed_for_intent: bool = Query(default=False),
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


@router.post(
    "/runtime-execution-submit-authorizations/intents/{execution_intent_id}",
    response_model=RuntimeExecutionSubmitAuthorization,
)
async def record_runtime_execution_submit_authorization_for_intent(
    execution_intent_id: str,
    owner_confirmed_for_submit: bool = Query(default=False),
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
    service = RuntimeStrategySignalPlanningService(
        semantics_binding_service=StrategySemanticsShadowBindingService(
            shadow_service=await _signal_evaluation_shadow_service(),
        ),
        runtime_execution_planning_service=await _runtime_execution_planning_service(),
        runtime_fact_overlay_service=StrategyRuntimeFactOverlayService(
            active_position_source=position_source,
            account_facts_source=_TradingConsoleCachedAccountFactsSource(api_module),
            market_fact_source=_trading_console_public_market_fact_source(),
        ),
    )
    setattr(api_module, "_runtime_strategy_signal_planning_service", service)
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


async def _runtime_execution_intent_adapter_service() -> Any:
    from src.interfaces import api as api_module

    injected = getattr(api_module, "_runtime_execution_intent_adapter_service", None)
    if injected is not None:
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
    from src.infrastructure.pg_runtime_execution_protection_plan_repository import (
        PgRuntimeExecutionProtectionPlanRepository,
    )
    from src.infrastructure.pg_runtime_execution_order_lifecycle_handoff_repository import (
        PgRuntimeExecutionOrderLifecycleHandoffRepository,
    )

    service = RuntimeExecutionIntentAdapterService(
        draft_repository=PgRuntimeExecutionIntentDraftRepository(),
        intent_repository=PgExecutionIntentRepository(),
        submit_authorization_repository=PgRuntimeExecutionSubmitAuthorizationRepository(),
        controlled_submit_result_repository=PgRuntimeExecutionControlledSubmitResultRepository(),
        attempt_reservation_repository=PgRuntimeExecutionAttemptReservationRepository(),
        attempt_mutation_repository=PgRuntimeExecutionAttemptMutationRepository(),
        protection_plan_repository=PgRuntimeExecutionProtectionPlanRepository(),
        order_lifecycle_handoff_repository=PgRuntimeExecutionOrderLifecycleHandoffRepository(),
        final_gate_preview_service=await _runtime_final_gate_preview_service(),
        runtime_service=await _strategy_runtime_service(),
    )
    setattr(api_module, "_runtime_execution_intent_adapter_service", service)
    return service


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
        execution_mode="shadow_disabled",
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
        decision=evaluation.decision.value,
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


def _order_candidate_view(candidate: OrderCandidate) -> OrderCandidateInspectionView:
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
        created_at_ms=candidate.created_at_ms,
        updated_at_ms=candidate.updated_at_ms,
        expires_at_ms=candidate.expires_at_ms,
        metadata=dict(candidate.metadata),
    )


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


def _build_pg_execution_recovery_repo() -> Any:
    from src.infrastructure.pg_execution_recovery_repository import PgExecutionRecoveryRepository

    return PgExecutionRecoveryRepository()


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


async def close_trading_console_read_only_exchange_gateway() -> None:
    from src.interfaces import api as api_module

    gateway = getattr(api_module, "_trading_console_read_only_exchange_gateway", None)
    setattr(api_module, "_trading_console_read_only_exchange_gateway", None)
    if gateway is not None and hasattr(gateway, "close"):
        await gateway.close()
