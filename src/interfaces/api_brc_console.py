from __future__ import annotations

import os
import time
from decimal import Decimal
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from src.application.brc_operation_layer import (
    BrcOperationService,
    ConfirmationMismatch,
    OperationCapability,
    OperationConfirmResponse,
    OperationDetailResponse,
    OperationLayerError,
    OperationLayerReaders,
    OperationListResponse,
    OperationPreflightResponse,
)
from src.application.strategy_group_reviewability import (
    StrategyGroupReviewabilityResponse,
    build_strategy_group_reviewability_snapshot,
)
from src.application.strategy_group_live_readonly_observation import (
    StrategyGroupLiveReadOnlyObservationResponse,
    build_strategy_group_live_readonly_observation_v1,
    run_strategy_group_live_readonly_observation_once,
)
from src.application.strategy_group_observation_case_queue import (
    ObservationCaseQueueResponse,
    blocked_observation_case_queue,
    build_observation_case_queue,
)
from src.application.mi001_bnb_trial_readiness_gap import (
    Mi001BnbTrialReadinessGapResponse,
    build_mi001_bnb_trial_readiness_gap,
)
from src.application.strategy_trial_architecture_governance import (
    StrategyTrialArchitectureGovernanceResponse,
    build_bnb_strategy_trial_architecture_governance,
)
from src.application.strategy_trial_carrier_expansion import (
    SecondCarrierExpansionResponse,
    build_second_carrier_expansion_bootstrap,
)
from src.application.multi_carrier_budget_authorization import (
    MultiCarrierBudgetAuthorization,
    MultiCarrierBudgetAuthorizationCreateRequest,
    MultiCarrierBudgetAuthorizationCurrentResponse,
    MultiCarrierBudgetAuthorizationError,
    MultiCarrierBudgetAuthorizationInfrastructureError,
    MultiCarrierBudgetAuthorizationService,
)
from src.application.bnb_live_execution_bridge import (
    BnbLiveExecutionBridgeDryRunRequest,
    BnbLiveExecutionBridgeDryRunResponse,
    BnbLiveExecutionBridgeDryRunService,
)
from src.application.binance_usdt_futures_account_facts import (
    BinanceUsdtFuturesAccountFactsSource,
)
from src.application.owner_trial_flow import (
    BoundedLiveTrialAuthorization,
    BoundedLiveTrialAuthorizationDraft,
    BoundedLiveTrialAuthorizationDraftCreateRequest,
    OwnerLiveAuthorizationActivationRequest,
    OwnerRiskAcknowledgement,
    OwnerRiskAcknowledgementCreateRequest,
    OwnerTrialFlowCurrentResponse,
    OwnerTrialFlowError,
    OwnerTrialFlowInfrastructureError,
    OwnerTrialFlowService,
)
from src.application.owner_bounded_execution import (
    ExchangeGatewayBoundedOrderExecutor,
    OwnerBoundedExecutionError,
    OwnerBoundedExecutionResponse,
    OwnerBoundedExecutionService,
)
from src.application.protection_price_planner import (
    ExchangeGatewayProtectionPriceSource,
    ProtectionPlannerService,
)
from src.application.strategy_trial_readiness import (
    StrategyTrialReadinessResponse,
    build_bnb_strategy_trial_readiness,
)
from src.application.strategy_trial_preflight_facts import TrialPreflightFactCollector
from src.infrastructure.local_sqlite_observation_market_source import LocalSqliteObservationMarketSource
from src.infrastructure.binance_public_kline_market_source import BinancePublicKlineMarketSource
from src.infrastructure.database import get_pg_session_maker, probe_pg_connectivity
from src.infrastructure.exchange_gateway import ExchangeGateway
from src.infrastructure.pg_global_kill_switch_repository import PgGlobalKillSwitchRepository
from src.infrastructure.pg_execution_intent_repository import PgExecutionIntentRepository
from src.infrastructure.pg_order_repository import PgOrderRepository
from src.infrastructure.pg_position_repository import PgPositionRepository
from src.infrastructure.owner_trial_flow_repository import PgOwnerTrialFlowRepository
from src.infrastructure.pg_multi_carrier_budget_authorization_repository import (
    PgMultiCarrierBudgetAuthorizationRepository,
)
from src.infrastructure.pg_protection_price_plan_repository import PgProtectionPricePlanRepository
from src.infrastructure.pg_strategy_group_forward_review_repository import PgStrategyGroupForwardReviewRepository
from src.infrastructure.pg_strategy_group_observation_repository import PgStrategyGroupObservationRepository
from src.application.brc_admission_service import (
    AdmissionRuleViolation,
    BrcAdmissionService,
    OwnerRiskAcceptanceInput,
)
from src.domain.brc_admission import (
    AdmissionDecision,
    AdmissionEvidencePacket,
    AdmissionExecutionMode,
    AdmissionRequest as BrcAdmissionRequestModel,
    AdmissionTrialBinding,
    OwnerMarketRegimeInput,
    OwnerRiskAcceptance,
    StrategyFamily,
    StrategyFamilyStatus,
    StrategyFamilyVersion,
    TrialEnv,
    TrialStage,
)
from src.interfaces.operator_auth import OperatorSessionDependency, require_operator_session
from src.interfaces import api_console_runtime as runtime


router = APIRouter(
    prefix="/api/brc",
    tags=["BRC Console"],
    dependencies=[Depends(require_operator_session)],
)

operator_router = APIRouter(
    prefix="/api/brc/operator",
    tags=["BRC Operator"],
    dependencies=[Depends(require_operator_session)],
)

workflow_router = APIRouter(
    prefix="/api/brc/llm/workflows",
    tags=["BRC LLM Workflows"],
    dependencies=[Depends(require_operator_session)],
)

dev_testnet_router = APIRouter(
    prefix="/api/dev/testnet/brc",
    tags=["BRC Controlled Testnet"],
    dependencies=[Depends(require_operator_session)],
)

_owner_trial_flow_service: OwnerTrialFlowService | None = None
_multi_carrier_budget_authorization_service: MultiCarrierBudgetAuthorizationService | None = None


class BrcDashboardResponse(BaseModel):
    current_stage: str = "BRC-R4 local operator console"
    next_recommended_step: str = "Review runtime safety, create an operator plan, then confirm only the intended action."
    global_planning_stage: str = "Bounded Risk Campaign System mainline; strategy pool, Feishu approval, cloud hardening, and real live remain deferred."
    terminology: dict[str, str] = {
        "Risk Envelope": "风险边界：这轮 campaign 允许承担的最大风险范围。",
        "Loss Lock": "亏损锁定：亏损触发硬停止，不能通过切换 playbook 重置。",
        "Profit Protect": "盈利保护：盈利触发保护/复盘，不自动扩大风险。",
        "Workflow": "操作流程：从 Owner 文本到计划、确认、执行、证据的链路。",
        "Evidence Packet": "证据包：用于复盘和验收的只读事实集合。",
    }
    owner_questions: list[str] = [
        "现在能不能做？",
        "为什么能/不能？",
        "下一步该做什么？",
    ]
    live_ready: bool = False


class BrcActionReadiness(BaseModel):
    action_id: str
    title: str
    description: str
    enabled: bool
    disabled_reason: Optional[str] = None
    route: Optional[str] = None
    button_label: str
    what_happens: str
    what_will_not_happen: str = (
        "不会真实下单、提现、转账、自动调整仓位、启用实盘或执行策略池。"
    )
    account_impact: str = "不会影响真实账户。"
    risk_level: Literal["read_only", "controlled_testnet", "blocked"] = "read_only"


RiskDecision = Literal[
    "ALLOW_READ",
    "ALLOW_MONITOR",
    "BLOCK_TESTNET",
    "ATTENTION_REQUIRED",
    "BLOCK_ALL_STATE_CHANGE",
]
RuntimeState = Literal[
    "observe",
    "monitor",
    "testnet_rehearsal",
    "paused",
    "stopped",
    "flattening",
    "attention_required",
]
AccountFactsSource = Literal["local_pg", "exchange_testnet", "exchange_live", "mixed", "unavailable"]
AccountFactsTruthLevel = Literal["summary", "exchange_read", "reconciled", "unavailable"]
ReconciliationStatusValue = Literal["not_available", "clean", "mismatch", "unknown"]
ActionCardType = Literal[
    "read_status",
    "enter_monitor",
    "testnet_rehearsal",
    "pause_new_entries",
    "emergency_stop_runtime",
    "emergency_flatten",
]


class BrcActionCard(BaseModel):
    action_card_id: str
    title: str
    action_type: ActionCardType
    enabled: bool
    disabled_reason: Optional[str] = None
    route: Optional[str] = None
    button_label: str
    authority_source: Literal["application_preflight"] = "application_preflight"
    fact_snapshot_id: str
    preflight_result_id: str
    idempotency_key: str
    expiry_time: Optional[int] = None
    current_state: RuntimeState
    allowed_next_states: list[RuntimeState] = Field(default_factory=list)
    blocked_next_states: list[str] = Field(default_factory=list)
    reversible: bool = False
    final_state_proof_required: bool = False
    hard_blocks: list[str] = Field(default_factory=list)
    advisory_warnings: list[str] = Field(default_factory=list)
    confirmation_phrase: Optional[str] = None
    account_impact: str = "不会影响真实账户。"
    what_will_change: str
    what_will_not_change: str = "不会启用真实实盘、提现/转账、自动 sizing/leverage 或策略池执行。"


class BrcReadinessResponse(BaseModel):
    mode: Literal[
        "standalone_console",
        "runtime_bound_console",
        "brc_ready",
        "testnet_ready",
        "blocked",
    ]
    current_conclusion: str
    why: list[str] = Field(default_factory=list)
    account_impact: str
    next_step: str
    available_actions: list[BrcActionReadiness] = Field(default_factory=list)
    disabled_actions: list[BrcActionReadiness] = Field(default_factory=list)
    latest_campaign: Optional[dict[str, Any]] = None
    environment_boundary: dict[str, Any] = Field(default_factory=dict)
    runtime_state: RuntimeState = "observe"
    risk_decision: RiskDecision = "ALLOW_READ"
    risk_account_summary: dict[str, Any] = Field(default_factory=dict)
    strategy_playbook_summary: dict[str, Any] = Field(default_factory=dict)
    action_cards: list[BrcActionCard] = Field(default_factory=list)
    global_cutoff_controls: list[BrcActionCard] = Field(default_factory=list)
    latest_audit: Optional[dict[str, Any]] = None
    runtime_summary: dict[str, Any] = Field(default_factory=dict)
    review_summary: dict[str, Any] = Field(default_factory=dict)
    markets_summary: dict[str, Any] = Field(default_factory=dict)
    playbook_summary: dict[str, Any] = Field(default_factory=dict)
    parameter_summary: dict[str, Any] = Field(default_factory=dict)
    audit_summary: dict[str, Any] = Field(default_factory=dict)
    ai_investigator_summary: dict[str, Any] = Field(default_factory=dict)
    developer_details: dict[str, Any] = Field(default_factory=dict)
    live_ready: Literal[False] = False


class StartupGuardReadinessArmRequest(BaseModel):
    reason: str = Field(
        default="MI-001 SOL startup guard readiness preflight",
        min_length=1,
        max_length=256,
    )
    updated_by: str = Field(default="owner_console", min_length=1, max_length=128)


class StartupGuardReadinessArmResponse(BaseModel):
    action: Literal["startup_guard_preflight_arm"] = "startup_guard_preflight_arm"
    status: Literal["armed", "already_armed", "blocked"]
    armed_before: Optional[bool] = None
    armed_after: Optional[bool] = None
    runtime_bound: bool
    runtime_control_api_enabled: bool
    runtime_effect: Literal["startup_guard_process_state_only", "none"]
    execution_permission_granted: Literal[False] = False
    order_permission_granted: Literal[False] = False
    trial_started: Literal[False] = False
    strategy_runtime_started: Literal[False] = False
    execution_intent_created: Literal[False] = False
    order_created: Literal[False] = False
    exchange_write_methods_called: Literal[False] = False
    next_checklist_verdict: str
    notes: list[str] = Field(default_factory=list)
    live_ready: Literal[False] = False


class Mi001SolCandidateView(BaseModel):
    id: str = "MI-001"
    candidate_id: str = "MI-001-SOL-LONG"
    strategy_family: str = "Momentum Impulse"
    variant_label: str = "12h close-to-close momentum impulse"
    symbol: str = "SOL/USDT:USDT"
    side: Literal["long"] = "long"
    status: str = "startup_guard_runtime_coupled_blocked"


class Mi001SolEvidenceView(BaseModel):
    signal_count: int = 8135
    mean_72h: str = "1.9531"
    positive_rate_72h: str = "0.5175"
    mean_7d: str = "4.7372"
    positive_rate_7d: str = "0.5398"
    limitations: list[str] = Field(
        default_factory=lambda: [
            "no cost",
            "no slippage",
            "no funding",
            "no random baseline",
            "no campaign replay",
            "research evidence is not execution permission",
        ]
    )


class Mi001SolRiskPolicyView(BaseModel):
    capital_source: str = "dedicated_subaccount"
    account_equity: str = "4663.39779623"
    available_margin: str = "3652.57096292"
    max_leverage: int = 5
    operation_layer_notional_cap: str = "18262.85481460"
    max_notional_rule: str = (
        "min(current_dedicated_subaccount_equity * 5, "
        "available_margin * 5, Operation Layer notional cap)"
    )
    max_total_loss_rule: str = "current_dedicated_subaccount_equity"
    prohibitions: list[str] = Field(
        default_factory=lambda: [
            "no_auto_top_up",
            "no_transfer",
            "no_withdrawal",
            "no_symbol_expansion",
            "no_side_expansion",
            "no_leverage_expansion_above_5x",
        ]
    )


class Mi001SolCheckView(BaseModel):
    check: str
    status: str
    evidence: str
    blocking: bool = False


class Mi001SolReadinessView(BaseModel):
    verdict: str
    blockers: list[str] = Field(default_factory=list)
    checks: list[Mi001SolCheckView] = Field(default_factory=list)


class Mi001SolOwnerActionView(BaseModel):
    action_id: str
    label: str
    enabled: bool
    endpoint: Optional[str] = None
    disabled_reason: Optional[str] = None
    safety_text: str


class Mi001SolStartupGuardActionView(BaseModel):
    endpoint: str = "/api/brc/readiness/startup-guard/preflight-arm"
    label: str = "Arm startup guard preflight"
    enabled: bool
    enabled_when: list[str] = Field(default_factory=list)
    safety_text: str = (
        "Arms only an existing runtime-owned StartupTradingGuardService; "
        "does not start trial, create execution intent, place orders, or grant permissions."
    )
    does_not_start_trial: Literal[True] = True
    does_not_create_execution_intent: Literal[True] = True
    does_not_place_order: Literal[True] = True


class Mi001SolNonPermissionsView(BaseModel):
    no_execution_permission: Literal[True] = True
    no_order_permission: Literal[True] = True
    no_runtime_start: Literal[True] = True
    no_leverage_change: Literal[True] = True
    no_order_capability: Literal[True] = True
    no_automatic_trial_start: Literal[True] = True


class Mi001SolOwnerConsoleE2EResponse(BaseModel):
    candidate: Mi001SolCandidateView
    evidence: Mi001SolEvidenceView
    risk_policy: Mi001SolRiskPolicyView
    readiness: Mi001SolReadinessView
    owner_actions: dict[str, list[Mi001SolOwnerActionView]]
    non_permissions: Mi001SolNonPermissionsView
    startup_guard_action: Mi001SolStartupGuardActionView
    terminal_state: str
    source_refs: list[str] = Field(default_factory=list)
    live_ready: Literal[False] = False


class BrcMarketsOrdersResponse(BaseModel):
    conclusion: str
    account_impact: str
    source: AccountFactsSource = "local_pg"
    truth_level: AccountFactsTruthLevel = "summary"
    reconciliation_status: dict[str, Any] = Field(default_factory=dict)
    symbols: list[dict[str, Any]] = Field(default_factory=list)
    open_orders: list[dict[str, Any]] = Field(default_factory=list)
    active_positions: list[dict[str, Any]] = Field(default_factory=list)
    recent_orders: list[dict[str, Any]] = Field(default_factory=list)
    recent_fills: list[dict[str, Any]] = Field(default_factory=list)
    exposure_by_symbol: dict[str, dict[str, Any]] = Field(default_factory=dict)
    unknown_or_unmanaged_orders: list[dict[str, Any]] = Field(default_factory=list)
    unknown_or_unmanaged_positions: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    developer_details: dict[str, Any] = Field(default_factory=dict)
    live_ready: Literal[False] = False


class BrcAccountFactsResponse(BaseModel):
    source: AccountFactsSource
    truth_level: AccountFactsTruthLevel
    generated_at_ms: int
    evidence_refs: list[str] = Field(default_factory=list)
    checked_sources: list[str] = Field(default_factory=list)
    source_snapshots: dict[str, Any] = Field(default_factory=dict)
    reconciliation_checked_at_ms: int
    mismatch_count: int = 0
    unknown_unmanaged_counts: dict[str, int] = Field(default_factory=dict)
    account_summary: dict[str, Any] = Field(default_factory=dict)
    positions: list[dict[str, Any]] = Field(default_factory=list)
    open_orders: list[dict[str, Any]] = Field(default_factory=list)
    recent_orders: list[dict[str, Any]] = Field(default_factory=list)
    recent_fills: list[dict[str, Any]] = Field(default_factory=list)
    exposure_by_symbol: dict[str, dict[str, Any]] = Field(default_factory=dict)
    unknown_or_unmanaged_orders: list[dict[str, Any]] = Field(default_factory=list)
    unknown_or_unmanaged_positions: list[dict[str, Any]] = Field(default_factory=list)
    connection_health: dict[str, Any] = Field(default_factory=dict)
    reconciliation_status: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    live_ready: Literal[False] = False


class BrcAuditTrailResponse(BaseModel):
    conclusion: str
    account_impact: str
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    operation_results: list[dict[str, Any]] = Field(default_factory=list)
    operator_actions: list[dict[str, Any]] = Field(default_factory=list)
    workflow_runs: list[dict[str, Any]] = Field(default_factory=list)
    review_decisions: list[dict[str, Any]] = Field(default_factory=list)
    developer_details: dict[str, Any] = Field(default_factory=dict)
    live_ready: Literal[False] = False


class BrcInvestigatorAskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    context_type: Optional[str] = Field(default=None, max_length=64)
    context_id: Optional[str] = Field(default=None, max_length=256)


class BrcInvestigatorAskResponse(BaseModel):
    intent: str
    conclusion: str
    reason: str
    account_impact: str
    evidence_summary: list[str] = Field(default_factory=list)
    trace: list[dict[str, Any]] = Field(default_factory=list)
    next_step: str
    developer_details: dict[str, Any] = Field(default_factory=dict)
    live_ready: Literal[False] = False


class BrcOperationPreflightRequest(BaseModel):
    operation_type: str = Field(min_length=1, max_length=128)
    requested_by: str = Field(default="owner", max_length=128)
    input_params: dict[str, Any] = Field(default_factory=dict)
    source: dict[str, Any] = Field(default_factory=lambda: {"kind": "ui"})


class BrcOperationConfirmRequest(BaseModel):
    preflight_id: str = Field(min_length=1, max_length=128)
    confirmation_phrase: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=1, max_length=128)
    confirmed_by: str = Field(default="owner", max_length=128)


class BrcOperationCancelRequest(BaseModel):
    requested_by: str = Field(default="owner", max_length=128)


class BrcOperationCapabilitiesResponse(BaseModel):
    capabilities: list[OperationCapability]
    live_ready: Literal[False] = False


class BrcStrategyFamilyCreateRequest(BaseModel):
    family_key: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=256)
    description: str = Field(default="", max_length=4096)
    status: StrategyFamilyStatus = StrategyFamilyStatus.INTAKE
    owner: str = Field(default="owner", max_length=128)


class BrcStrategyFamilyVersionCreateRequest(BaseModel):
    version: int = Field(ge=1)
    hypothesis: str = Field(default="", max_length=4096)
    market_structure: str = Field(default="", max_length=4096)
    entry_logic_family: str = Field(default="", max_length=4096)
    exit_logic_family: str = Field(default="", max_length=4096)
    risk_model: str = Field(default="", max_length=4096)
    supported_symbols: list[str] = Field(default_factory=list)
    supported_timeframes: list[str] = Field(default_factory=list)
    required_data: list[str] = Field(default_factory=list)
    required_execution_capabilities: list[str] = Field(default_factory=list)
    known_failure_modes: list[str] = Field(default_factory=list)
    regime_contract_json: dict[str, Any] = Field(default_factory=dict)
    safeguards_json: dict[str, Any] = Field(default_factory=dict)
    degradation_policy_json: dict[str, Any] = Field(default_factory=dict)
    playbook_id: Optional[str] = Field(default=None, max_length=128)
    playbook_catalog_snapshot_json: dict[str, Any] = Field(default_factory=dict)
    created_by: str = Field(default="owner", max_length=128)


class BrcEvidencePacketCreateRequest(BaseModel):
    strategy_family_version_id: str = Field(min_length=1, max_length=128)
    payload_json: dict[str, Any] = Field(default_factory=dict)
    mandatory_complete: bool = False
    created_by: str = Field(default="owner", max_length=128)


class BrcOwnerRegimeInputCreateRequest(BaseModel):
    current_regime: str = Field(min_length=1, max_length=128)
    confidence: str = Field(default="unknown", max_length=64)
    rationale: str = Field(default="", max_length=4096)
    market_facts_snapshot_json: dict[str, Any] = Field(default_factory=dict)
    created_by: str = Field(default="owner", max_length=128)


class BrcAdmissionRequestCreateRequest(BaseModel):
    strategy_family_version_id: str = Field(min_length=1, max_length=128)
    evidence_packet_id: str = Field(min_length=1, max_length=128)
    owner_market_regime_input_id: str = Field(min_length=1, max_length=128)
    trial_env: TrialEnv
    trial_stage: TrialStage
    requested_execution_mode: Optional[AdmissionExecutionMode] = None
    requested_risk_profile: str = Field(default="micro", max_length=64)
    admission_rule_config_id: Optional[str] = Field(default=None, max_length=128)
    account_facts_snapshot_ref: Optional[str] = Field(default=None, max_length=256)
    account_facts_snapshot_json: dict[str, Any] = Field(default_factory=dict)
    playbook_id: Optional[str] = Field(default=None, max_length=128)
    playbook_catalog_snapshot_json: dict[str, Any] = Field(default_factory=dict)
    requested_by: str = Field(default="owner", max_length=128)


class BrcOwnerRiskAcceptanceCreateRequest(BaseModel):
    admission_request_id: str = Field(min_length=1, max_length=128)
    constraint_snapshot_id: str = Field(min_length=1, max_length=128)
    admission_decision_id: Optional[str] = Field(default=None, max_length=128)
    owner_rationale: str = Field(default="", max_length=4096)
    confirmation_phrase: str = Field(min_length=1, max_length=128)
    confirmed_by: str = Field(default="owner", max_length=128)


_CONTROLLED_SYMBOLS: list[dict[str, Any]] = [
    {
        "symbol_key": "eth",
        "display_symbol": "ETHUSDT",
        "exchange_symbol": "ETH/USDT:USDT",
        "allowed_amount": "0.01",
        "max_notional_usdt": "25",
        "leverage_cap": "1x",
    },
    {
        "symbol_key": "btc",
        "display_symbol": "BTCUSDT",
        "exchange_symbol": "BTC/USDT:USDT",
        "allowed_amount": "0.002",
        "max_notional_usdt": "250",
        "leverage_cap": "1x",
    },
]


def _api_module() -> Any:
    from src.interfaces import api as api_module

    return api_module


async def _operation_runtime_summary() -> dict[str, Any]:
    api_module = _api_module()
    profile, testnet, profile_reasons, symbols = _runtime_profile_summary(api_module)
    gks_active, startup_guard_armed = _guard_summary(api_module)
    campaign_state = getattr(api_module, "_campaign_state_service", None)
    current_runtime_state = None
    if campaign_state is not None and hasattr(campaign_state, "get_state"):
        try:
            state = campaign_state.get_state()
            current_runtime_state = getattr(state, "status", None)
            if current_runtime_state is None and isinstance(state, dict):
                current_runtime_state = state.get("status")
        except Exception:
            current_runtime_state = None
    return {
        "runtime_bound": api_module.get_runtime_context() is not None,
        "profile": profile,
        "testnet": testnet,
        "symbols": symbols,
        "profile_reasons": profile_reasons,
        "gks_active": gks_active,
        "startup_guard_armed": startup_guard_armed,
        "runtime_control_api_enabled": _env_enabled("RUNTIME_CONTROL_API_ENABLED"),
        "runtime_test_signal_injection_enabled": _env_enabled("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED"),
        "brc_service_ready": getattr(api_module, "_brc_campaign_service", None) is not None,
        "campaign_state_service_ready": campaign_state is not None,
        "current_runtime_state": current_runtime_state,
        "live_ready": False,
    }


async def _operation_markets_orders_summary() -> dict[str, Any]:
    facts = await _account_facts(_api_module())
    payload = facts.model_dump(mode="json")
    account = dict(payload.get("account_summary") or {})
    unknown_counts = dict(payload.get("unknown_unmanaged_counts") or {})
    payload.update(
        {
            "active_positions": payload.get("positions", []),
            "active_position_count": account.get("active_position_count", 0),
            "open_order_count": account.get("open_order_count", 0),
            "all_local_flat": account.get("all_local_flat", False),
            "data_source": payload.get("source"),
            "reconciliation_status_value": (payload.get("reconciliation_status") or {}).get("status"),
            "unknown_or_unmanaged_order_count": unknown_counts.get(
                "orders",
                len(payload.get("unknown_or_unmanaged_orders") or []),
            ),
            "unknown_or_unmanaged_position_count": unknown_counts.get(
                "positions",
                len(payload.get("unknown_or_unmanaged_positions") or []),
            ),
        }
    )
    return payload


async def _operation_audit_writable() -> bool:
    service = getattr(_api_module(), "_brc_campaign_service", None)
    if service is None:
        return False
    _, errors = await _audit_summary(service, limit=1)
    return not errors


async def _operation_review_packet(input_params: dict[str, Any]) -> dict[str, Any]:
    api_module = _api_module()
    service = getattr(api_module, "_brc_campaign_service", None)
    campaign = await service.get_latest_campaign() if service is not None else None
    audit, audit_errors = await _audit_summary(service, limit=10)
    return {
        "operation_id": input_params.get("operation_id"),
        "preflight_id": input_params.get("preflight_id"),
        "latest_campaign": _campaign_summary(campaign),
        "audit_timeline": list(audit.get("timeline", [])),
        "audit_errors": audit_errors,
        "mutation_executed": False,
        "live_ready": False,
    }


async def _operation_admission_readiness(input_params: dict[str, Any]) -> dict[str, Any]:
    service = await _get_admission_service()
    return await service.build_gated_trial_preflight_readiness(input_params)


async def _operation_admission_binding_reserver(input_params: dict[str, Any]) -> dict[str, Any]:
    service = await _get_admission_service()
    binding = await service.reserve_gated_trial_binding(
        input_params,
        operation_id=str(input_params["operation_id"]),
        preflight_id=str(input_params["preflight_id"]),
        confirmed_by=str(input_params.get("confirmed_by") or "owner"),
    )
    return binding.model_dump(mode="json")


async def _operation_admission_campaign_readiness(input_params: dict[str, Any]) -> dict[str, Any]:
    service = await _get_admission_service()
    return await service.build_campaign_carrier_preflight_readiness(input_params)


async def _operation_admission_campaign_creator(input_params: dict[str, Any]) -> dict[str, Any]:
    admission_service = await _get_admission_service()
    api_module = _api_module()
    brc_service = getattr(api_module, "_brc_campaign_service", None)
    if brc_service is None:
        raise RuntimeError("BRC campaign service unavailable")

    readiness = await admission_service.build_campaign_carrier_preflight_readiness(input_params)
    blockers = [str(item) for item in readiness.get("blockers") or []]
    if blockers:
        raise AdmissionRuleViolation("; ".join(blockers))

    binding_id = str(
        input_params.get("admission_binding_id")
        or input_params.get("binding_id")
        or ""
    )
    binding = await admission_service.get_admission_trial_binding(binding_id)
    decision = await admission_service.get_admission_decision(binding.admission_decision_id)
    constraint = await admission_service.get_trial_constraint_snapshot(
        binding.trial_constraint_snapshot_id
    )
    campaign = await brc_service.create_admission_campaign_shell(
        admission_binding_id=binding.binding_id,
        admission_decision_id=binding.admission_decision_id,
        strategy_family_version_id=binding.strategy_family_version_id,
        playbook_id=binding.playbook_id,
        constraint_snapshot_id=binding.trial_constraint_snapshot_id,
        trial_env=binding.trial_env.value,
        trial_stage=binding.trial_stage.value,
        execution_mode=binding.execution_mode.value,
        constraints_json=dict(constraint.constraints_json),
        reason=(
            "BRC-R5-002 admission campaign shell creation from Operation "
            f"{input_params.get('operation_id')}"
        ),
        operation_id=str(input_params["operation_id"]),
        preflight_id=str(input_params["preflight_id"]),
        created_by=str(input_params.get("confirmed_by") or "owner"),
    )
    updated_binding = await admission_service.mark_admission_trial_binding_campaign_created(
        binding_id=binding.binding_id,
        campaign_id=campaign.campaign_id,
        operation_id=str(input_params["operation_id"]),
        preflight_id=str(input_params["preflight_id"]),
        confirmed_by=str(input_params.get("confirmed_by") or "owner"),
    )
    return {
        "campaign": _dump_jsonable(campaign),
        "binding": updated_binding.model_dump(mode="json"),
        "admission_decision_id": decision.admission_decision_id,
        "campaign_created": True,
        "runtime_installed": False,
        "runtime_started": False,
        "strategy_active": False,
        "constraints_installed": False,
        "orders_placed": False,
        "live_ready": False,
    }


async def _resolve_admission_campaign_for_constraints(
    input_params: dict[str, Any],
) -> Any:
    api_module = _api_module()
    brc_service = getattr(api_module, "_brc_campaign_service", None)
    if brc_service is None:
        raise RuntimeError("BRC campaign service unavailable")
    campaign_id = str(input_params.get("campaign_id") or "").strip()
    current = await brc_service.get_current_campaign()
    latest = await brc_service.get_latest_campaign()
    candidates = [item for item in (current, latest) if item is not None]
    if campaign_id:
        for item in candidates:
            if item.campaign_id == campaign_id:
                return item
        raise AdmissionRuleViolation(f"BRC campaign not found: {campaign_id}")
    if current is not None:
        return current
    if latest is not None:
        return latest
    raise AdmissionRuleViolation("BRC campaign not found")


async def _operation_runtime_constraint_install_readiness(input_params: dict[str, Any]) -> dict[str, Any]:
    admission_service = await _get_admission_service()
    campaign = await _resolve_admission_campaign_for_constraints(input_params)
    runtime_summary = await _operation_runtime_summary()
    return await admission_service.build_runtime_constraint_install_preflight_readiness(
        input_params,
        campaign=campaign,
        runtime_summary=runtime_summary,
    )


async def _operation_runtime_constraint_installer(input_params: dict[str, Any]) -> dict[str, Any]:
    admission_service = await _get_admission_service()
    api_module = _api_module()
    brc_service = getattr(api_module, "_brc_campaign_service", None)
    if brc_service is None:
        raise RuntimeError("BRC campaign service unavailable")
    campaign = await _resolve_admission_campaign_for_constraints(input_params)
    readiness = await admission_service.build_runtime_constraint_install_preflight_readiness(
        input_params,
        campaign=campaign,
        runtime_summary=await _operation_runtime_summary(),
    )
    blockers = [str(item) for item in readiness.get("blockers") or []]
    if blockers:
        raise AdmissionRuleViolation("; ".join(blockers))

    binding_id = str(
        input_params.get("admission_binding_id")
        or input_params.get("binding_id")
        or readiness.get("binding_summary", {}).get("binding_id")
        or ""
    )
    binding = await admission_service.get_admission_trial_binding(binding_id)
    constraint = await admission_service.get_trial_constraint_snapshot(
        binding.trial_constraint_snapshot_id
    )
    installed = await brc_service.install_runtime_constraints_from_admission_campaign(
        campaign_id=str(binding.campaign_id),
        admission_binding_id=binding.binding_id,
        admission_decision_id=binding.admission_decision_id,
        strategy_family_version_id=binding.strategy_family_version_id,
        playbook_id=binding.playbook_id,
        constraint_snapshot_id=binding.trial_constraint_snapshot_id,
        constraints_json=dict(constraint.constraints_json),
        operation_id=str(input_params["operation_id"]),
        preflight_id=str(input_params["preflight_id"]),
        installed_by=str(input_params.get("confirmed_by") or "owner"),
    )
    updated_binding = await admission_service.mark_admission_trial_binding_runtime_constraints_installed(
        binding_id=binding.binding_id,
        campaign_id=str(binding.campaign_id),
        operation_id=str(input_params["operation_id"]),
        preflight_id=str(input_params["preflight_id"]),
        confirmed_by=str(input_params.get("confirmed_by") or "owner"),
    )
    installed_campaign = installed["campaign"]
    return {
        "campaign": _dump_jsonable(installed_campaign),
        "binding": updated_binding.model_dump(mode="json"),
        "campaign_id": binding.campaign_id,
        "binding_id": binding.binding_id,
        "installed_constraint_snapshot_id": binding.trial_constraint_snapshot_id,
        "installed_constraints_summary": dict(installed.get("installed_constraints_summary") or {}),
        "idempotent": bool(installed.get("idempotent", False)),
        "event": dict(installed.get("event") or {}),
        "constraints_installed": True,
        "runtime_status": "constraints_installed_not_started",
        "runtime_started": False,
        "runtime_active": False,
        "strategy_active": False,
        "trial_started": False,
        "orders_placed": False,
        "live_ready": False,
    }


async def _operation_runtime_carrier_readiness(input_params: dict[str, Any]) -> dict[str, Any]:
    admission_service = await _get_admission_service()
    campaign = await _resolve_admission_campaign_for_constraints(input_params)
    runtime_summary = await _operation_runtime_summary()
    return await admission_service.build_runtime_carrier_preflight_readiness(
        input_params,
        campaign=campaign,
        runtime_summary=runtime_summary,
    )


async def _operation_runtime_carrier_preparer(input_params: dict[str, Any]) -> dict[str, Any]:
    admission_service = await _get_admission_service()
    api_module = _api_module()
    brc_service = getattr(api_module, "_brc_campaign_service", None)
    if brc_service is None:
        raise RuntimeError("BRC campaign service unavailable")
    campaign = await _resolve_admission_campaign_for_constraints(input_params)
    readiness = await admission_service.build_runtime_carrier_preflight_readiness(
        input_params,
        campaign=campaign,
        runtime_summary=await _operation_runtime_summary(),
    )
    blockers = [str(item) for item in readiness.get("blockers") or []]
    if blockers:
        raise AdmissionRuleViolation("; ".join(blockers))

    binding_id = str(
        input_params.get("admission_binding_id")
        or input_params.get("binding_id")
        or readiness.get("binding_summary", {}).get("binding_id")
        or ""
    )
    binding = await admission_service.get_admission_trial_binding(binding_id)
    prepared = await brc_service.prepare_runtime_carrier_from_admission_campaign(
        campaign_id=str(binding.campaign_id),
        admission_binding_id=binding.binding_id,
        admission_decision_id=binding.admission_decision_id,
        strategy_family_version_id=binding.strategy_family_version_id,
        playbook_id=binding.playbook_id,
        installed_constraint_snapshot_id=binding.trial_constraint_snapshot_id,
        execution_mode=binding.execution_mode.value,
        operation_id=str(input_params["operation_id"]),
        preflight_id=str(input_params["preflight_id"]),
        prepared_by=str(input_params.get("confirmed_by") or "owner"),
    )
    audited_binding = await admission_service.record_admission_runtime_carrier_ready(
        binding_id=binding.binding_id,
        campaign_id=str(binding.campaign_id),
        operation_id=str(input_params["operation_id"]),
        preflight_id=str(input_params["preflight_id"]),
        confirmed_by=str(input_params.get("confirmed_by") or "owner"),
    )
    prepared_campaign = prepared["campaign"]
    return {
        "campaign": _dump_jsonable(prepared_campaign),
        "binding": audited_binding.model_dump(mode="json"),
        "campaign_id": binding.campaign_id,
        "binding_id": binding.binding_id,
        "carrier_ready": True,
        "carrier_readiness_summary": dict(prepared.get("carrier_readiness_summary") or {}),
        "idempotent": bool(prepared.get("idempotent", False)),
        "event": dict(prepared.get("event") or {}),
        "runtime_status": "carrier_ready_not_started",
        "runtime_started": False,
        "runtime_active": False,
        "strategy_active": False,
        "trial_started": False,
        "auto_within_budget_enabled": False,
        "owner_confirm_each_entry_enabled": False,
        "orders_placed": False,
        "live_ready": False,
    }


async def _operation_runtime_start_readiness(input_params: dict[str, Any]) -> dict[str, Any]:
    admission_service = await _get_admission_service()
    campaign = await _resolve_admission_campaign_for_constraints(input_params)
    runtime_summary = await _operation_runtime_summary()
    return await admission_service.build_runtime_start_preflight_readiness(
        input_params,
        campaign=campaign,
        runtime_summary=runtime_summary,
    )


async def _operation_runtime_start_preparer(input_params: dict[str, Any]) -> dict[str, Any]:
    admission_service = await _get_admission_service()
    api_module = _api_module()
    brc_service = getattr(api_module, "_brc_campaign_service", None)
    if brc_service is None:
        raise RuntimeError("BRC campaign service unavailable")
    campaign = await _resolve_admission_campaign_for_constraints(input_params)
    readiness = await admission_service.build_runtime_start_preflight_readiness(
        input_params,
        campaign=campaign,
        runtime_summary=await _operation_runtime_summary(),
    )
    blockers = [str(item) for item in readiness.get("blockers") or []]
    if blockers:
        raise AdmissionRuleViolation("; ".join(blockers))

    binding_id = str(
        input_params.get("admission_binding_id")
        or input_params.get("binding_id")
        or readiness.get("binding_summary", {}).get("binding_id")
        or ""
    )
    binding = await admission_service.get_admission_trial_binding(binding_id)
    prepared = await brc_service.prepare_runtime_start_from_admission_carrier(
        campaign_id=str(binding.campaign_id),
        admission_binding_id=binding.binding_id,
        admission_decision_id=binding.admission_decision_id,
        strategy_family_version_id=binding.strategy_family_version_id,
        playbook_id=binding.playbook_id,
        installed_constraint_snapshot_id=binding.trial_constraint_snapshot_id,
        execution_mode=binding.execution_mode.value,
        operation_id=str(input_params["operation_id"]),
        preflight_id=str(input_params["preflight_id"]),
        prepared_by=str(input_params.get("confirmed_by") or "owner"),
    )
    audited_binding = await admission_service.record_admission_runtime_start_ready(
        binding_id=binding.binding_id,
        campaign_id=str(binding.campaign_id),
        operation_id=str(input_params["operation_id"]),
        preflight_id=str(input_params["preflight_id"]),
        confirmed_by=str(input_params.get("confirmed_by") or "owner"),
    )
    prepared_campaign = prepared["campaign"]
    return {
        "campaign": _dump_jsonable(prepared_campaign),
        "binding": audited_binding.model_dump(mode="json"),
        "campaign_id": binding.campaign_id,
        "binding_id": binding.binding_id,
        "runtime_start_ready": True,
        "runtime_start_readiness_summary": dict(
            prepared.get("runtime_start_readiness_summary") or {}
        ),
        "idempotent": bool(prepared.get("idempotent", False)),
        "event": dict(prepared.get("event") or {}),
        "runtime_status": "runtime_start_ready_not_started",
        "runtime_started": False,
        "runtime_active": False,
        "strategy_active": False,
        "trial_started": False,
        "auto_within_budget_enabled": False,
        "owner_confirm_each_entry_enabled": False,
        "orders_placed": False,
        "live_ready": False,
    }


async def _operation_trial_trade_intent_readiness(input_params: dict[str, Any]) -> dict[str, Any]:
    admission_service = await _get_admission_service()
    campaign = await _resolve_admission_campaign_for_constraints(input_params)
    return await admission_service.build_trial_trade_intent_preflight_readiness(
        input_params,
        campaign=campaign,
    )


async def _operation_trial_trade_intent_evaluator(input_params: dict[str, Any]) -> dict[str, Any]:
    admission_service = await _get_admission_service()
    campaign = await _resolve_admission_campaign_for_constraints(input_params)
    evaluated = await admission_service.evaluate_trial_trade_intent(
        input_params,
        campaign=campaign,
        operation_id=str(input_params["operation_id"]),
        preflight_id=str(input_params["preflight_id"]),
        confirmed_by=str(input_params.get("confirmed_by") or "owner"),
    )
    return {
        **evaluated,
        "campaign_id": input_params.get("campaign_id") or getattr(campaign, "campaign_id", None),
        "trial_trade_intent_is_order": False,
        "order_created": False,
        "execution_intent_created": False,
        "runtime_started": False,
        "strategy_active": False,
        "orders_placed": False,
        "live_ready": False,
    }


async def _operation_signal_trade_intent_readiness(input_params: dict[str, Any]) -> dict[str, Any]:
    admission_service = await _get_admission_service()
    campaign = await _resolve_admission_campaign_for_constraints(input_params)
    return await admission_service.build_signal_trial_trade_intent_preflight_readiness(
        input_params,
        campaign=campaign,
    )


async def _operation_signal_trade_intent_recorder(input_params: dict[str, Any]) -> dict[str, Any]:
    admission_service = await _get_admission_service()
    campaign = await _resolve_admission_campaign_for_constraints(input_params)
    recorded = await admission_service.record_trial_trade_intent_from_signal_evaluation(
        input_params,
        campaign=campaign,
        operation_id=str(input_params["operation_id"]),
        preflight_id=str(input_params["preflight_id"]),
        execution_permission_resolution=dict(input_params.get("execution_permission_resolution") or {}),
        confirmed_by=str(input_params.get("confirmed_by") or "owner"),
    )
    intent = dict(recorded.get("intent") or {})
    brc_service = getattr(_api_module(), "_brc_campaign_service", None)
    if brc_service is None:
        raise RuntimeError("BRC campaign service unavailable")
    metadata_result = await brc_service.record_trial_trade_intent_recorded_no_execution(
        campaign_id=str(recorded.get("campaign_id") or intent.get("campaign_id") or getattr(campaign, "campaign_id")),
        admission_binding_id=str(recorded.get("binding_id") or intent.get("binding_id")),
        admission_decision_id=str(intent.get("admission_decision_id")),
        strategy_family_version_id=str(intent.get("strategy_family_version_id")),
        playbook_id=str(intent.get("playbook_id")),
        installed_constraint_snapshot_id=str(
            (getattr(campaign, "metadata_json", {}) or {}).get("installed_constraint_snapshot_id")
        ),
        execution_mode=str(recorded.get("execution_mode") or intent.get("execution_mode")),
        trial_trade_intent_id=recorded.get("intent_id") or intent.get("intent_id"),
        trial_trade_intent_decision=str(recorded.get("decision") or intent.get("decision")),
        not_executed_reason=str(recorded.get("not_executed_reason") or intent.get("not_executed_reason")),
        execution_permission_resolution=dict(recorded.get("execution_permission_resolution") or {}),
        operation_id=str(input_params["operation_id"]),
        preflight_id=str(input_params["preflight_id"]),
    )
    return {
        **recorded,
        "campaign": _dump_jsonable(metadata_result.get("campaign")),
        "campaign_id": getattr(metadata_result.get("campaign"), "campaign_id", None)
        or recorded.get("campaign_id")
        or intent.get("campaign_id"),
        "trial_trade_intent_summary": dict(metadata_result.get("trial_trade_intent_summary") or {}),
        "metadata_idempotent": bool(metadata_result.get("idempotent", False)),
        "trial_trade_intent_is_order": False,
        "order_created": False,
        "execution_intent_created": False,
        "orders_placed": False,
        "trial_started": False,
        "auto_execution_enabled": False,
        "auto_within_budget_enabled": False,
        "live_ready": False,
    }


async def _operation_runtime_handoff_readiness(input_params: dict[str, Any]) -> dict[str, Any]:
    admission_service = await _get_admission_service()
    campaign = await _resolve_admission_campaign_for_constraints(input_params)
    return await admission_service.build_runtime_handoff_preflight_readiness(
        input_params,
        campaign=campaign,
        runtime_summary=await _operation_runtime_summary(),
        trade_intent_ledger_available=True,
    )


async def _operation_runtime_handoff_preparer(input_params: dict[str, Any]) -> dict[str, Any]:
    admission_service = await _get_admission_service()
    api_module = _api_module()
    brc_service = getattr(api_module, "_brc_campaign_service", None)
    if brc_service is None:
        raise RuntimeError("BRC campaign service unavailable")
    campaign = await _resolve_admission_campaign_for_constraints(input_params)
    readiness = await admission_service.build_runtime_handoff_preflight_readiness(
        input_params,
        campaign=campaign,
        runtime_summary=await _operation_runtime_summary(),
        trade_intent_ledger_available=True,
    )
    blockers = [str(item) for item in readiness.get("blockers") or []]
    if blockers:
        raise AdmissionRuleViolation("; ".join(blockers))
    binding_id = str(
        input_params.get("admission_binding_id")
        or input_params.get("binding_id")
        or readiness.get("binding_summary", {}).get("binding_id")
        or ""
    )
    binding = await admission_service.get_admission_trial_binding(binding_id)
    prepared = await brc_service.prepare_runtime_handoff_from_admission_campaign(
        campaign_id=str(binding.campaign_id),
        admission_binding_id=binding.binding_id,
        admission_decision_id=binding.admission_decision_id,
        strategy_family_version_id=binding.strategy_family_version_id,
        playbook_id=binding.playbook_id,
        installed_constraint_snapshot_id=binding.trial_constraint_snapshot_id,
        execution_mode=binding.execution_mode.value,
        operation_id=str(input_params["operation_id"]),
        preflight_id=str(input_params["preflight_id"]),
        prepared_by=str(input_params.get("confirmed_by") or "owner"),
    )
    audited_binding = await admission_service.record_admission_runtime_handoff_ready(
        binding_id=binding.binding_id,
        campaign_id=str(binding.campaign_id),
        operation_id=str(input_params["operation_id"]),
        preflight_id=str(input_params["preflight_id"]),
        confirmed_by=str(input_params.get("confirmed_by") or "owner"),
    )
    prepared_campaign = prepared["campaign"]
    return {
        "campaign": _dump_jsonable(prepared_campaign),
        "binding": audited_binding.model_dump(mode="json"),
        "campaign_id": binding.campaign_id,
        "binding_id": binding.binding_id,
        "runtime_handoff_ready": True,
        "runtime_handoff_readiness_summary": dict(
            prepared.get("runtime_handoff_readiness_summary") or {}
        ),
        "idempotent": bool(prepared.get("idempotent", False)),
        "event": dict(prepared.get("event") or {}),
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
        "live_ready": False,
    }


async def _operation_runtime_start_from_handoff_readiness(input_params: dict[str, Any]) -> dict[str, Any]:
    admission_service = await _get_admission_service()
    campaign = await _resolve_admission_campaign_for_constraints(input_params)
    return await admission_service.build_start_runtime_from_handoff_preflight_readiness(
        input_params,
        campaign=campaign,
        runtime_summary=await _operation_runtime_summary(),
        trade_intent_ledger_available=True,
    )


async def _operation_runtime_start_from_handoff_starter(input_params: dict[str, Any]) -> dict[str, Any]:
    admission_service = await _get_admission_service()
    api_module = _api_module()
    brc_service = getattr(api_module, "_brc_campaign_service", None)
    if brc_service is None:
        raise RuntimeError("BRC campaign service unavailable")
    campaign = await _resolve_admission_campaign_for_constraints(input_params)
    readiness = await admission_service.build_start_runtime_from_handoff_preflight_readiness(
        input_params,
        campaign=campaign,
        runtime_summary=await _operation_runtime_summary(),
        trade_intent_ledger_available=True,
    )
    blockers = [str(item) for item in readiness.get("blockers") or []]
    if blockers:
        raise AdmissionRuleViolation("; ".join(blockers))
    binding_id = str(
        input_params.get("admission_binding_id")
        or input_params.get("binding_id")
        or readiness.get("binding_summary", {}).get("binding_id")
        or ""
    )
    binding = await admission_service.get_admission_trial_binding(binding_id)
    started = await brc_service.start_runtime_from_admission_handoff(
        campaign_id=str(binding.campaign_id),
        admission_binding_id=binding.binding_id,
        admission_decision_id=binding.admission_decision_id,
        strategy_family_version_id=binding.strategy_family_version_id,
        playbook_id=binding.playbook_id,
        installed_constraint_snapshot_id=binding.trial_constraint_snapshot_id,
        execution_mode=binding.execution_mode.value,
        operation_id=str(input_params["operation_id"]),
        preflight_id=str(input_params["preflight_id"]),
        started_by=str(input_params.get("confirmed_by") or "owner"),
    )
    audited_binding = await admission_service.record_admission_runtime_started(
        binding_id=binding.binding_id,
        campaign_id=str(binding.campaign_id),
        operation_id=str(input_params["operation_id"]),
        preflight_id=str(input_params["preflight_id"]),
        confirmed_by=str(input_params.get("confirmed_by") or "owner"),
    )
    started_campaign = started["campaign"]
    return {
        "campaign": _dump_jsonable(started_campaign),
        "binding": audited_binding.model_dump(mode="json"),
        "campaign_id": binding.campaign_id,
        "binding_id": binding.binding_id,
        "runtime_started": True,
        "runtime_start_summary": dict(started.get("runtime_start_summary") or {}),
        "idempotent": bool(started.get("idempotent", False)),
        "event": dict(started.get("event") or {}),
        "runtime_status": "runtime_started_strategy_inactive",
        "runtime_active": False,
        "strategy_active": False,
        "trial_started": False,
        "auto_within_budget_enabled": False,
        "auto_execution_enabled": False,
        "owner_confirm_each_entry_enabled": False,
        "order_created": False,
        "execution_intent_created": False,
        "orders_placed": False,
        "live_ready": False,
    }


async def _operation_strategy_activation_readiness(input_params: dict[str, Any]) -> dict[str, Any]:
    admission_service = await _get_admission_service()
    campaign = await _resolve_admission_campaign_for_constraints(input_params)
    return await admission_service.build_strategy_activation_preflight_readiness(
        input_params,
        campaign=campaign,
        runtime_summary=await _operation_runtime_summary(),
    )


async def _operation_strategy_activation_preparer(input_params: dict[str, Any]) -> dict[str, Any]:
    admission_service = await _get_admission_service()
    api_module = _api_module()
    brc_service = getattr(api_module, "_brc_campaign_service", None)
    if brc_service is None:
        raise RuntimeError("BRC campaign service unavailable")
    campaign = await _resolve_admission_campaign_for_constraints(input_params)
    readiness = await admission_service.build_strategy_activation_preflight_readiness(
        input_params,
        campaign=campaign,
        runtime_summary=await _operation_runtime_summary(),
    )
    blockers = [str(item) for item in readiness.get("blockers") or []]
    if blockers:
        raise AdmissionRuleViolation("; ".join(blockers))
    binding_id = str(
        input_params.get("admission_binding_id")
        or input_params.get("binding_id")
        or readiness.get("binding_summary", {}).get("binding_id")
        or ""
    )
    binding = await admission_service.get_admission_trial_binding(binding_id)
    prepared = await brc_service.prepare_strategy_activation_from_admission_runtime(
        campaign_id=str(binding.campaign_id),
        admission_binding_id=binding.binding_id,
        admission_decision_id=binding.admission_decision_id,
        strategy_family_version_id=binding.strategy_family_version_id,
        playbook_id=binding.playbook_id,
        installed_constraint_snapshot_id=binding.trial_constraint_snapshot_id,
        execution_mode=binding.execution_mode.value,
        operation_id=str(input_params["operation_id"]),
        preflight_id=str(input_params["preflight_id"]),
        prepared_by=str(input_params.get("confirmed_by") or "owner"),
    )
    audited_binding = await admission_service.record_admission_strategy_activation_ready(
        binding_id=binding.binding_id,
        campaign_id=str(binding.campaign_id),
        operation_id=str(input_params["operation_id"]),
        preflight_id=str(input_params["preflight_id"]),
        confirmed_by=str(input_params.get("confirmed_by") or "owner"),
    )
    prepared_campaign = prepared["campaign"]
    return {
        "campaign": _dump_jsonable(prepared_campaign),
        "binding": audited_binding.model_dump(mode="json"),
        "campaign_id": binding.campaign_id,
        "binding_id": binding.binding_id,
        "strategy_activation_ready": True,
        "strategy_activation_readiness_summary": dict(
            prepared.get("strategy_activation_readiness_summary") or {}
        ),
        "idempotent": bool(prepared.get("idempotent", False)),
        "event": dict(prepared.get("event") or {}),
        "runtime_status": "strategy_activation_ready_not_active",
        "runtime_started": True,
        "runtime_active": False,
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
        "live_ready": False,
    }


async def _operation_strategy_state_activation_readiness(input_params: dict[str, Any]) -> dict[str, Any]:
    admission_service = await _get_admission_service()
    campaign = await _resolve_admission_campaign_for_constraints(input_params)
    return await admission_service.build_strategy_state_activation_preflight_readiness(
        input_params,
        campaign=campaign,
        runtime_summary=await _operation_runtime_summary(),
    )


async def _operation_strategy_state_activator(input_params: dict[str, Any]) -> dict[str, Any]:
    admission_service = await _get_admission_service()
    api_module = _api_module()
    brc_service = getattr(api_module, "_brc_campaign_service", None)
    if brc_service is None:
        raise RuntimeError("BRC campaign service unavailable")
    campaign = await _resolve_admission_campaign_for_constraints(input_params)
    readiness = await admission_service.build_strategy_state_activation_preflight_readiness(
        input_params,
        campaign=campaign,
        runtime_summary=await _operation_runtime_summary(),
    )
    blockers = [str(item) for item in readiness.get("blockers") or []]
    if blockers:
        raise AdmissionRuleViolation("; ".join(blockers))
    binding_id = str(
        input_params.get("admission_binding_id")
        or input_params.get("binding_id")
        or readiness.get("binding_summary", {}).get("binding_id")
        or ""
    )
    binding = await admission_service.get_admission_trial_binding(binding_id)
    activated = await brc_service.activate_strategy_from_admission_runtime(
        campaign_id=str(binding.campaign_id),
        admission_binding_id=binding.binding_id,
        admission_decision_id=binding.admission_decision_id,
        strategy_family_version_id=binding.strategy_family_version_id,
        playbook_id=binding.playbook_id,
        installed_constraint_snapshot_id=binding.trial_constraint_snapshot_id,
        execution_mode=binding.execution_mode.value,
        operation_id=str(input_params["operation_id"]),
        preflight_id=str(input_params["preflight_id"]),
        activated_by=str(input_params.get("confirmed_by") or "owner"),
    )
    audited_binding = await admission_service.record_admission_strategy_activated_no_execution(
        binding_id=binding.binding_id,
        campaign_id=str(binding.campaign_id),
        operation_id=str(input_params["operation_id"]),
        preflight_id=str(input_params["preflight_id"]),
        confirmed_by=str(input_params.get("confirmed_by") or "owner"),
    )
    activated_campaign = activated["campaign"]
    return {
        "campaign": _dump_jsonable(activated_campaign),
        "binding": audited_binding.model_dump(mode="json"),
        "campaign_id": binding.campaign_id,
        "binding_id": binding.binding_id,
        "strategy_state": "strategy_active_no_execution",
        "strategy_activation_state": "active_no_execution",
        "strategy_state_activation_summary": dict(
            activated.get("strategy_state_activation_summary") or {}
        ),
        "idempotent": bool(activated.get("idempotent", False)),
        "event": dict(activated.get("event") or {}),
        "runtime_status": "strategy_active_no_execution",
        "runtime_started": True,
        "runtime_active": False,
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
        "live_ready": False,
    }


async def _operation_signal_loop_readiness(input_params: dict[str, Any]) -> dict[str, Any]:
    admission_service = await _get_admission_service()
    campaign = await _resolve_admission_campaign_for_constraints(input_params)
    return await admission_service.build_signal_loop_preflight_readiness(
        input_params,
        campaign=campaign,
        runtime_summary=await _operation_runtime_summary(),
    )


async def _operation_signal_loop_preparer(input_params: dict[str, Any]) -> dict[str, Any]:
    admission_service = await _get_admission_service()
    api_module = _api_module()
    brc_service = getattr(api_module, "_brc_campaign_service", None)
    if brc_service is None:
        raise RuntimeError("BRC campaign service unavailable")
    campaign = await _resolve_admission_campaign_for_constraints(input_params)
    readiness = await admission_service.build_signal_loop_preflight_readiness(
        input_params,
        campaign=campaign,
        runtime_summary=await _operation_runtime_summary(),
    )
    blockers = [str(item) for item in readiness.get("blockers") or []]
    if blockers:
        raise AdmissionRuleViolation("; ".join(blockers))
    binding_id = str(
        input_params.get("admission_binding_id")
        or input_params.get("binding_id")
        or readiness.get("binding_summary", {}).get("binding_id")
        or ""
    )
    binding = await admission_service.get_admission_trial_binding(binding_id)
    prepared = await brc_service.prepare_signal_loop_from_admission_strategy(
        campaign_id=str(binding.campaign_id),
        admission_binding_id=binding.binding_id,
        admission_decision_id=binding.admission_decision_id,
        strategy_family_version_id=binding.strategy_family_version_id,
        playbook_id=binding.playbook_id,
        installed_constraint_snapshot_id=binding.trial_constraint_snapshot_id,
        execution_mode=binding.execution_mode.value,
        operation_id=str(input_params["operation_id"]),
        preflight_id=str(input_params["preflight_id"]),
        prepared_by=str(input_params.get("confirmed_by") or "owner"),
    )
    audited_binding = await admission_service.record_admission_signal_loop_ready(
        binding_id=binding.binding_id,
        campaign_id=str(binding.campaign_id),
        operation_id=str(input_params["operation_id"]),
        preflight_id=str(input_params["preflight_id"]),
        confirmed_by=str(input_params.get("confirmed_by") or "owner"),
    )
    prepared_campaign = prepared["campaign"]
    return {
        "campaign": _dump_jsonable(prepared_campaign),
        "binding": audited_binding.model_dump(mode="json"),
        "campaign_id": binding.campaign_id,
        "binding_id": binding.binding_id,
        "signal_loop_ready": True,
        "signal_loop_readiness_summary": dict(
            prepared.get("signal_loop_readiness_summary") or {}
        ),
        "idempotent": bool(prepared.get("idempotent", False)),
        "event": dict(prepared.get("event") or {}),
        "runtime_status": "signal_loop_ready_not_started",
        "runtime_started": True,
        "runtime_active": False,
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
        "live_ready": False,
    }


async def _operation_signal_loop_start_readiness(input_params: dict[str, Any]) -> dict[str, Any]:
    admission_service = await _get_admission_service()
    campaign = await _resolve_admission_campaign_for_constraints(input_params)
    return await admission_service.build_signal_loop_start_preflight_readiness(
        input_params,
        campaign=campaign,
        runtime_summary=await _operation_runtime_summary(),
    )


async def _operation_signal_loop_starter(input_params: dict[str, Any]) -> dict[str, Any]:
    admission_service = await _get_admission_service()
    api_module = _api_module()
    brc_service = getattr(api_module, "_brc_campaign_service", None)
    if brc_service is None:
        raise RuntimeError("BRC campaign service unavailable")
    campaign = await _resolve_admission_campaign_for_constraints(input_params)
    readiness = await admission_service.build_signal_loop_start_preflight_readiness(
        input_params,
        campaign=campaign,
        runtime_summary=await _operation_runtime_summary(),
    )
    blockers = [str(item) for item in readiness.get("blockers") or []]
    if blockers:
        raise AdmissionRuleViolation("; ".join(blockers))
    binding_id = str(
        input_params.get("admission_binding_id")
        or input_params.get("binding_id")
        or readiness.get("binding_summary", {}).get("binding_id")
        or ""
    )
    binding = await admission_service.get_admission_trial_binding(binding_id)
    started = await brc_service.start_signal_loop_from_admission_strategy(
        campaign_id=str(binding.campaign_id),
        admission_binding_id=binding.binding_id,
        admission_decision_id=binding.admission_decision_id,
        strategy_family_version_id=binding.strategy_family_version_id,
        playbook_id=binding.playbook_id,
        installed_constraint_snapshot_id=binding.trial_constraint_snapshot_id,
        execution_mode=binding.execution_mode.value,
        operation_id=str(input_params["operation_id"]),
        preflight_id=str(input_params["preflight_id"]),
        started_by=str(input_params.get("confirmed_by") or "owner"),
    )
    audited_binding = await admission_service.record_admission_signal_loop_started_no_signal(
        binding_id=binding.binding_id,
        campaign_id=str(binding.campaign_id),
        operation_id=str(input_params["operation_id"]),
        preflight_id=str(input_params["preflight_id"]),
        confirmed_by=str(input_params.get("confirmed_by") or "owner"),
    )
    started_campaign = started["campaign"]
    return {
        "campaign": _dump_jsonable(started_campaign),
        "binding": audited_binding.model_dump(mode="json"),
        "campaign_id": binding.campaign_id,
        "binding_id": binding.binding_id,
        "signal_loop_start_summary": dict(
            started.get("signal_loop_start_summary") or {}
        ),
        "idempotent": bool(started.get("idempotent", False)),
        "event": dict(started.get("event") or {}),
        "runtime_status": "signal_loop_started_no_signal",
        "runtime_started": True,
        "runtime_active": False,
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
        "live_ready": False,
    }


async def _operation_signal_evaluation_readiness(input_params: dict[str, Any]) -> dict[str, Any]:
    admission_service = await _get_admission_service()
    campaign = await _resolve_admission_campaign_for_constraints(input_params)
    return await admission_service.build_signal_evaluation_preflight_readiness(
        input_params,
        campaign=campaign,
        runtime_summary=await _operation_runtime_summary(),
    )


async def _operation_signal_evaluator(input_params: dict[str, Any]) -> dict[str, Any]:
    admission_service = await _get_admission_service()
    api_module = _api_module()
    brc_service = getattr(api_module, "_brc_campaign_service", None)
    if brc_service is None:
        raise RuntimeError("BRC campaign service unavailable")
    campaign = await _resolve_admission_campaign_for_constraints(input_params)
    readiness = await admission_service.build_signal_evaluation_preflight_readiness(
        input_params,
        campaign=campaign,
        runtime_summary=await _operation_runtime_summary(),
    )
    blockers = [str(item) for item in readiness.get("blockers") or []]
    if blockers:
        raise AdmissionRuleViolation("; ".join(blockers))
    binding_id = str(
        input_params.get("admission_binding_id")
        or input_params.get("binding_id")
        or readiness.get("binding_summary", {}).get("binding_id")
        or ""
    )
    binding = await admission_service.get_admission_trial_binding(binding_id)
    evaluated = await brc_service.evaluate_signal_from_admission_strategy(
        campaign_id=str(binding.campaign_id),
        admission_binding_id=binding.binding_id,
        admission_decision_id=binding.admission_decision_id,
        strategy_family_version_id=binding.strategy_family_version_id,
        playbook_id=binding.playbook_id,
        installed_constraint_snapshot_id=binding.trial_constraint_snapshot_id,
        execution_mode=binding.execution_mode.value,
        operation_id=str(input_params["operation_id"]),
        preflight_id=str(input_params["preflight_id"]),
        signal_snapshot=dict(input_params.get("signal_snapshot") or {}),
        signal_evaluation_input=dict(input_params.get("signal_evaluation_input") or {}),
        evaluated_by=str(input_params.get("confirmed_by") or "owner"),
    )
    audited_binding = await admission_service.record_admission_signal_evaluated_no_intent(
        binding_id=binding.binding_id,
        campaign_id=str(binding.campaign_id),
        operation_id=str(input_params["operation_id"]),
        preflight_id=str(input_params["preflight_id"]),
        confirmed_by=str(input_params.get("confirmed_by") or "owner"),
    )
    evaluated_campaign = evaluated["campaign"]
    return {
        "campaign": _dump_jsonable(evaluated_campaign),
        "binding": audited_binding.model_dump(mode="json"),
        "campaign_id": binding.campaign_id,
        "binding_id": binding.binding_id,
        "signal_evaluation_summary": dict(
            evaluated.get("signal_evaluation_summary") or {}
        ),
        "idempotent": bool(evaluated.get("idempotent", False)),
        "event": dict(evaluated.get("event") or {}),
        "runtime_status": "signal_evaluated_no_intent",
        "runtime_started": True,
        "runtime_active": False,
        "strategy_active": True,
        "strategy_execution_enabled": False,
        "signal_loop_started": True,
        "signal_loop_enabled": True,
        "signal_loop_enabled_scope": "non_trading_loop_state",
        "signal_evaluated": True,
        "signal_generated": True,
        "signal_is_trade_intent": False,
        "trial_started": False,
        "auto_within_budget_enabled": False,
        "auto_execution_enabled": False,
        "owner_confirm_each_entry_enabled": False,
        "trade_intent_created": False,
        "execution_intent_created": False,
        "order_created": False,
        "orders_placed": False,
        "live_ready": False,
    }


async def _operation_runtime_transition(target_state: str, input_params: dict[str, Any]) -> dict[str, Any]:
    api_module = _api_module()
    campaign_state = getattr(api_module, "_campaign_state_service", None)
    if campaign_state is None or not hasattr(campaign_state, "set_state"):
        raise RuntimeError("runtime transition adapter unavailable")
    snapshot = await campaign_state.set_state(
        status=target_state,
        reason=str(input_params.get("reason") or f"BRC Operation transition to {target_state}"),
        updated_by=str(input_params.get("updated_by") or "owner"),
        metadata={
            "operation_id": input_params.get("operation_id"),
            "preflight_id": input_params.get("preflight_id"),
            "authorization_source": "brc_operation_layer",
            "places_orders": False,
            "closes_positions": False,
            "cancels_orders": False,
            "live_ready": False,
        },
    )
    return _dump_jsonable(snapshot)


def _runtime_stop_adapter_available(api_module: Any) -> bool:
    campaign_state = getattr(api_module, "_campaign_state_service", None)
    return campaign_state is not None and hasattr(campaign_state, "get_state") and hasattr(campaign_state, "set_state")


async def _operation_runtime_stop(input_params: dict[str, Any]) -> dict[str, Any]:
    api_module = _api_module()
    campaign_state = getattr(api_module, "_campaign_state_service", None)
    if campaign_state is None or not hasattr(campaign_state, "get_state") or not hasattr(campaign_state, "set_state"):
        raise RuntimeError("runtime stop adapter unavailable")
    from src.application.campaign_state_service import CampaignTransitionTrigger

    current = campaign_state.get_state()
    current_payload = _dump_jsonable(current)
    current_status = str(current_payload.get("status") or "").lower()
    stopped_states = {"stopped", "stopped_by_owner", "emergency_stop", "hard_locked", "closed"}
    if current_status in stopped_states:
        current_payload.update(
            {
                "already_stopped": True,
                "operation_id": input_params.get("operation_id"),
                "preflight_id": input_params.get("preflight_id"),
                "authorization_source": "brc_operation_layer",
                "does_not_flatten": True,
                "does_not_cancel_orders": True,
                "does_not_place_orders": True,
                "live_ready": False,
            }
        )
        return current_payload

    snapshot = await campaign_state.set_state(
        status="hard_locked",
        reason=str(input_params.get("reason") or "BRC Operation emergency stop runtime"),
        updated_by=str(input_params.get("updated_by") or "owner"),
        trigger=CampaignTransitionTrigger.OWNER_HARD_LOCK,
        metadata={
            "operation_id": input_params.get("operation_id"),
            "preflight_id": input_params.get("preflight_id"),
            "authorization_source": "brc_operation_layer",
            "stop_reason": "emergency_stop_runtime",
            "stopped_by_owner": True,
            "flatten_executed": False,
            "orders_cancelled": False,
            "places_orders": False,
            "closes_positions": False,
            "cancels_orders": False,
            "live_ready": False,
        },
    )
    payload = _dump_jsonable(snapshot)
    payload.update(
        {
            "runtime_state": payload.get("status"),
            "stopped_by_owner": True,
            "emergency_stop": True,
            "flatten_executed": False,
            "orders_cancelled": False,
            "places_orders": False,
            "closes_positions": False,
            "cancels_orders": False,
            "live_ready": False,
            "operation_id": input_params.get("operation_id"),
            "preflight_id": input_params.get("preflight_id"),
            "authorization_source": "brc_operation_layer",
        }
    )
    return payload


async def _operation_fixed_testnet_rehearsal(request: Request, input_params: dict[str, Any]) -> dict[str, Any]:
    workflow_run_id = f"op-wf-{input_params['operation_id']}"
    result = await runtime._execute_brc_fixed_testnet_rehearsal(
        request=request,
        workflow_run_id=workflow_run_id,
    )
    result.update(
        {
            "operation_id": input_params.get("operation_id"),
            "preflight_id": input_params.get("preflight_id"),
            "workflow_run_id": result.get("workflow_run_id") or workflow_run_id,
            "authorization_source": "brc_operation_layer",
            "workflow_carrier_role": "internal_ref_only",
            "withdrawal_executed": False,
            "live_ready": False,
        }
    )
    readiness_summary, readiness_errors = await _readiness_summary_for_operation_result()
    result["readiness"] = readiness_summary
    result["readiness_errors"] = readiness_errors
    return result


async def _readiness_summary_for_operation_result() -> tuple[dict[str, Any], list[str]]:
    try:
        readiness = await get_brc_readiness()
        return readiness.model_dump(mode="json"), []
    except Exception as exc:  # pragma: no cover - defensive result enrichment
        return {}, [str(exc)]


async def _get_operation_service(request: Optional[Request] = None) -> BrcOperationService:
    api_module = _api_module()
    existing = getattr(api_module, "_brc_operation_service", None)
    if existing is not None:
        return existing
    brc_service = getattr(api_module, "_brc_campaign_service", None)
    try:
        from src.infrastructure.pg_brc_operation_repository import PgBrcOperationRepository

        repository = PgBrcOperationRepository()
    except Exception as exc:  # pragma: no cover - configuration-specific fail-closed path
        raise HTTPException(
            status_code=503,
            detail="BRC Operation repository unavailable; persistent Operation Layer is required.",
        ) from exc
    service = BrcOperationService(
        repository=repository,
        brc_campaign_service=brc_service,
        readers=OperationLayerReaders(
            runtime_summary=_operation_runtime_summary,
            markets_orders_summary=_operation_markets_orders_summary,
            audit_writable=_operation_audit_writable,
            review_packet_reader=_operation_review_packet,
            runtime_transition=_operation_runtime_transition,
            runtime_stop_executor=(
                _operation_runtime_stop
                if _runtime_stop_adapter_available(api_module)
                else None
            ),
            fixed_rehearsal_executor=(
                (lambda payload: _operation_fixed_testnet_rehearsal(request, payload))
                if request is not None
                else None
            ),
            admission_readiness=_operation_admission_readiness,
            admission_binding_reserver=_operation_admission_binding_reserver,
            admission_campaign_readiness=_operation_admission_campaign_readiness,
            admission_campaign_creator=_operation_admission_campaign_creator,
            admission_runtime_constraint_readiness=_operation_runtime_constraint_install_readiness,
            admission_runtime_constraint_installer=_operation_runtime_constraint_installer,
            admission_runtime_carrier_readiness=_operation_runtime_carrier_readiness,
            admission_runtime_carrier_preparer=_operation_runtime_carrier_preparer,
            admission_runtime_start_readiness=_operation_runtime_start_readiness,
            admission_runtime_start_preparer=_operation_runtime_start_preparer,
            trial_trade_intent_readiness=_operation_trial_trade_intent_readiness,
            trial_trade_intent_evaluator=_operation_trial_trade_intent_evaluator,
            admission_runtime_handoff_readiness=_operation_runtime_handoff_readiness,
            admission_runtime_handoff_preparer=_operation_runtime_handoff_preparer,
            admission_runtime_start_from_handoff_readiness=_operation_runtime_start_from_handoff_readiness,
            admission_runtime_start_from_handoff_starter=_operation_runtime_start_from_handoff_starter,
            admission_strategy_activation_readiness=_operation_strategy_activation_readiness,
            admission_strategy_activation_preparer=_operation_strategy_activation_preparer,
            admission_strategy_state_activation_readiness=_operation_strategy_state_activation_readiness,
            admission_strategy_state_activator=_operation_strategy_state_activator,
            admission_signal_loop_readiness=_operation_signal_loop_readiness,
            admission_signal_loop_preparer=_operation_signal_loop_preparer,
            admission_signal_loop_start_readiness=_operation_signal_loop_start_readiness,
            admission_signal_loop_starter=_operation_signal_loop_starter,
            admission_signal_evaluation_readiness=_operation_signal_evaluation_readiness,
            admission_signal_evaluator=_operation_signal_evaluator,
            signal_trade_intent_readiness=_operation_signal_trade_intent_readiness,
            signal_trade_intent_recorder=_operation_signal_trade_intent_recorder,
        ),
    )
    try:
        await service.initialize()
    except Exception as exc:  # pragma: no cover - configuration-specific fail-closed path
        raise HTTPException(
            status_code=503,
            detail="BRC Operation repository initialization failed; persistent Operation Layer is required.",
        ) from exc
    if request is None:
        setattr(api_module, "_brc_operation_service", service)
    return service


async def _get_admission_service() -> BrcAdmissionService:
    api_module = _api_module()
    existing = getattr(api_module, "_brc_admission_service", None)
    if existing is not None:
        return existing
    try:
        from src.infrastructure.pg_brc_admission_repository import PgBrcAdmissionRepository

        repository = PgBrcAdmissionRepository()
    except Exception as exc:  # pragma: no cover - configuration-specific fail-closed path
        raise HTTPException(
            status_code=503,
            detail="BRC Admission repository unavailable; persistent PG facts are required.",
        ) from exc
    service = BrcAdmissionService(repository=repository)
    try:
        await service.initialize()
    except Exception as exc:  # pragma: no cover - configuration-specific fail-closed path
        raise HTTPException(
            status_code=503,
            detail="BRC Admission repository initialization failed; persistent PG facts are required.",
        ) from exc
    setattr(api_module, "_brc_admission_service", service)
    return service


def _raise_operation_error(exc: Exception) -> None:
    if isinstance(exc, ConfirmationMismatch):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, OperationLayerError):
        message = str(exc)
        if "not found" in message:
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc
    raise HTTPException(status_code=500, detail=str(exc)) from exc


def _raise_admission_error(exc: Exception) -> None:
    if isinstance(exc, AdmissionRuleViolation):
        message = str(exc)
        if "not found" in message:
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc
    raise HTTPException(status_code=500, detail=str(exc)) from exc


def _runtime_profile_summary(api_module: Any) -> tuple[Optional[str], Optional[bool], list[str], list[str]]:
    provider = getattr(api_module, "_runtime_config_provider", None)
    resolved = getattr(provider, "resolved_config", None) if provider is not None else None
    if resolved is None:
        return None, None, ["运行配置 Profile 尚未解析，无法确认是否处于 BRC testnet profile。"], []
    profile = getattr(resolved, "profile_name", None)
    environment = getattr(resolved, "environment", None)
    testnet = getattr(environment, "exchange_testnet", None)
    if testnet is None:
        testnet = getattr(environment, "testnet", None)
    market = getattr(resolved, "market", None)
    symbols = list(getattr(market, "symbols", []) or [])
    reasons = []
    if profile != "brc_btc_eth_testnet_runtime":
        reasons.append("当前运行配置 Profile 不是 brc_btc_eth_testnet_runtime。")
    if testnet is not True:
        reasons.append("当前未确认处于 Exchange Testnet 测试网。")
    if set(symbols) != {"BTC/USDT:USDT", "ETH/USDT:USDT"}:
        reasons.append("当前运行配置没有固定在 BRC BTC/ETH 测试网 symbol scope。")
    return profile, testnet, reasons, symbols


def _guard_summary(api_module: Any) -> tuple[Optional[bool], Optional[bool]]:
    gks_active = None
    gks = getattr(api_module, "_global_kill_switch_service", None)
    if gks is not None and hasattr(gks, "get_state"):
        state = gks.get_state()
        gks_active = bool(getattr(state, "active", state.get("active") if isinstance(state, dict) else None))
    elif gks is not None and hasattr(gks, "is_active"):
        gks_active = bool(gks.is_active())
    startup_guard_armed = None
    guard = getattr(api_module, "_startup_trading_guard_service", None)
    if guard is not None and hasattr(guard, "get_state"):
        state = guard.get_state()
        startup_guard_armed = bool(getattr(state, "armed", state.get("armed") if isinstance(state, dict) else None))
    elif guard is not None and hasattr(guard, "is_armed"):
        startup_guard_armed = bool(guard.is_armed())
    return gks_active, startup_guard_armed


def _startup_guard_armed_state(guard: Any) -> Optional[bool]:
    if guard is None:
        return None
    if hasattr(guard, "get_state"):
        state = guard.get_state()
        return bool(
            getattr(
                state,
                "armed",
                state.get("armed") if isinstance(state, dict) else None,
            )
        )
    if hasattr(guard, "is_armed"):
        return bool(guard.is_armed())
    return None


def _env_enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _dump_jsonable(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "dict"):
        return value.dict()
    if isinstance(value, dict):
        return dict(value)
    payload: dict[str, Any] = {}
    for key in dir(value):
        if key.startswith("_"):
            continue
        attr = getattr(value, key, None)
        if callable(attr):
            continue
        if isinstance(attr, (str, int, float, bool, type(None), list, dict)):
            payload[key] = attr
        else:
            payload[key] = str(attr)
    return payload


def _operation_audit_payload(operation: Any, result: Any = None) -> dict[str, Any]:
    payload = _dump_jsonable(operation)
    result_payload = _dump_jsonable(result) if result is not None else None
    payload["result"] = result_payload
    payload["audit_refs"] = (
        result_payload.get("audit_refs")
        if result_payload is not None
        else payload.get("created_audit_refs", [])
    )
    payload["campaign_refs"] = result_payload.get("campaign_refs", []) if result_payload is not None else []
    payload["review_refs"] = result_payload.get("review_refs", []) if result_payload is not None else []
    payload["occurred_at_ms"] = (
        result_payload.get("occurred_at_ms")
        if result_payload is not None
        else payload.get("executed_at_ms") or payload.get("confirmed_at_ms") or payload.get("requested_at_ms")
    )
    return payload


async def _operation_audit_results(limit: int) -> tuple[list[dict[str, Any]], list[str]]:
    api_module = _api_module()
    errors: list[str] = []
    existing = getattr(api_module, "_brc_operation_service", None)
    try:
        if existing is not None:
            listed = await existing.list(limit=limit)
            payloads = []
            for operation in listed.operations:
                detail = await existing.get(operation.operation_id)
                payloads.append(_operation_audit_payload(detail.operation, detail.result))
            return payloads, errors

        from src.infrastructure.pg_brc_operation_repository import PgBrcOperationRepository

        repository = PgBrcOperationRepository()
        await repository.initialize()
        operations = await repository.list_operations(limit=limit)
        payloads = []
        for operation in operations:
            result = await repository.get_execution_result(operation.operation_id)
            payloads.append(_operation_audit_payload(operation, result))
        return payloads, errors
    except Exception as exc:  # pragma: no cover - defensive audit summary
        if existing is not None:
            errors.append(f"operation results read failed: {exc}")
        return [], errors


def _campaign_summary(campaign: Any) -> Optional[dict[str, Any]]:
    if campaign is None:
        return None
    return {
        "campaign_id": campaign.campaign_id,
        "status": campaign.status.value if hasattr(campaign.status, "value") else str(campaign.status),
        "outcome": campaign.outcome.value if getattr(campaign, "outcome", None) is not None else None,
        "current_playbook_id": campaign.current_playbook_id,
        "realized_pnl": str(campaign.realized_pnl),
        "attempt_count": campaign.attempt_count,
        "max_attempts": campaign.risk_envelope.max_attempts,
        "profit_protect_trigger": str(campaign.risk_envelope.profit_protect_trigger),
        "max_campaign_loss": str(campaign.risk_envelope.max_campaign_loss),
        "finalized_at_ms": campaign.finalized_at_ms,
        "metadata_json": dict(getattr(campaign, "metadata_json", {}) or {}),
    }


async def _markets_orders_summary(api_module: Any) -> tuple[dict[str, Any], list[str]]:
    """Build a read-only BTC/ETH status summary without exchange mutation."""
    errors: list[str] = []
    position_repo = getattr(api_module, "_position_repo", None)
    order_repo = getattr(api_module, "_order_repo", None)
    symbols: list[dict[str, Any]] = []
    all_positions: list[dict[str, Any]] = []
    all_open_orders: list[dict[str, Any]] = []

    for spec in _CONTROLLED_SYMBOLS:
        exchange_symbol = str(spec["exchange_symbol"])
        positions: list[Any] = []
        orders: list[Any] = []
        if position_repo is not None and hasattr(position_repo, "list_active"):
            try:
                positions = list(await position_repo.list_active(symbol=exchange_symbol, limit=20))
            except Exception as exc:  # pragma: no cover - defensive product summary
                errors.append(f"{exchange_symbol} active position read failed: {exc}")
        if order_repo is not None and hasattr(order_repo, "get_open_orders"):
            try:
                orders = list(await order_repo.get_open_orders(exchange_symbol))
            except TypeError:
                try:
                    orders = list(await order_repo.get_open_orders())
                except Exception as exc:  # pragma: no cover
                    errors.append(f"{exchange_symbol} open order read failed: {exc}")
            except Exception as exc:  # pragma: no cover
                errors.append(f"{exchange_symbol} open order read failed: {exc}")

        position_payloads = [_dump_jsonable(item) for item in positions]
        order_payloads = [_dump_jsonable(item) for item in orders]
        all_positions.extend(position_payloads)
        all_open_orders.extend(order_payloads)
        symbols.append(
            {
                **spec,
                "testnet_only": True,
                "live_enabled": False,
                "strategy_execution_enabled": False,
                "active_position_count": len(position_payloads),
                "open_order_count": len(order_payloads),
                "status_label": "flat" if not position_payloads and not order_payloads else "attention_required",
                "owner_meaning": (
                    "当前未发现本地 active position/open order。"
                    if not position_payloads and not order_payloads
                    else "发现本地 active position 或 open order，请先核对完整链路。"
                ),
            }
        )

    return (
        {
            "symbols": symbols,
            "active_positions": all_positions,
            "open_orders": all_open_orders,
            "active_position_count": len(all_positions),
            "open_order_count": len(all_open_orders),
            "all_local_flat": len(all_positions) == 0 and len(all_open_orders) == 0,
            "data_source": "local_pg",
        },
        errors,
    )


async def _account_facts(api_module: Any) -> BrcAccountFactsResponse:
    generated_at_ms = int(time.time() * 1000)
    position_repo = getattr(api_module, "_position_repo", None)
    order_repo = getattr(api_module, "_order_repo", None)
    equity_snapshot = _cached_account_equity_snapshot(api_module, generated_at_ms=generated_at_ms)
    local_summary, errors = await _markets_orders_summary(api_module)
    local_positions = list(local_summary.get("active_positions", []))
    local_open_orders = list(local_summary.get("open_orders", []))
    repos_wired = position_repo is not None or order_repo is not None
    local_read_failed = bool(errors)
    local_available = repos_wired and not local_read_failed
    exchange = await _exchange_testnet_facts(api_module)
    exchange_available = exchange["available"] is True
    positions = list(exchange["positions"] if exchange_available else local_positions)
    open_orders = list(exchange["open_orders"] if exchange_available else local_open_orders)
    recent_orders = list(exchange["recent_orders"] if exchange_available else [])
    recent_fills = list(exchange["recent_fills"] if exchange_available else [])
    if exchange_available and local_available:
        source: AccountFactsSource = "mixed"
        truth_level: AccountFactsTruthLevel = "reconciled"
    elif exchange_available:
        source = "exchange_testnet"
        truth_level = "exchange_read"
    elif local_available:
        source = "local_pg"
        truth_level = "summary"
    else:
        source = "unavailable"
        truth_level = "unavailable"
    limitations = [
        "Current view is local BRC summary, not complete exchange account truth.",
        "wallet_equity and available_margin are mapped from cached AccountSnapshot only; this endpoint does not fetch balances.",
        "recent_orders is unavailable unless exchange testnet exposes a safe read-only history method.",
        "recent_fills is unavailable unless exchange testnet exposes a safe read-only trade history method.",
        "unknown_or_unmanaged_orders require exchange testnet read plus reconciliation.",
        "No order placement, cancel, close, flatten, withdrawal, transfer, or live enablement is exposed here.",
    ]
    warnings = list(errors)
    warnings.extend(exchange["warnings"])
    blockers: list[str] = []
    if not repos_wired:
        blockers.append("local PG position/order repositories are not available")
        limitations.append("local PG account summary is unavailable in this process.")
    if local_read_failed:
        blockers.append("local PG account facts read failed; account facts are fail-closed")
        limitations.append("local PG account summary failed to read and cannot be treated as account truth.")
    limitations.extend(exchange["limitations"])
    limitations.extend(equity_snapshot["limitations"])
    warnings.extend(equity_snapshot["warnings"])

    reconciliation_status, unknown_orders, unknown_positions = _reconcile_account_facts(
        local_positions=local_positions,
        local_open_orders=local_open_orders,
        exchange_positions=list(exchange["positions"]),
        exchange_open_orders=list(exchange["open_orders"]),
        local_available=local_available,
        exchange_available=exchange_available,
    )
    checked_sources = list(reconciliation_status.get("checked_sources") or [])
    mismatch_count = len(reconciliation_status.get("mismatches") or [])
    unknown_unmanaged_counts = {
        "orders": len(unknown_orders),
        "positions": len(unknown_positions),
    }
    source_snapshots = {
        "local_pg": {
            "available": local_available,
            "position_count": len(local_positions),
            "open_order_count": len(local_open_orders),
            "read_errors": errors,
        },
        "exchange_testnet": {
            "available": exchange_available,
            "position_count": len(exchange["positions"]) if exchange_available else 0,
            "open_order_count": len(exchange["open_orders"]) if exchange_available else 0,
            "recent_order_count": len(exchange["recent_orders"]) if exchange_available else 0,
            "recent_fill_count": len(exchange["recent_fills"]) if exchange_available else 0,
            "reason": exchange["reason"],
            "read_errors": exchange["errors"],
        },
        "exchange_live": {
            "available": False,
            "reason": "forbidden in Owner Console account facts slice",
        },
        "runtime_account_snapshot": equity_snapshot["source_snapshot"],
    }
    evidence_refs = [
        f"account_facts:{source}:{truth_level}:{generated_at_ms}",
        f"reconciliation:{reconciliation_status.get('status', 'unknown')}:{generated_at_ms}",
    ]
    exposure_by_symbol = _exposure_by_symbol_from_facts(
        local_summary=local_summary,
        positions=positions,
        open_orders=open_orders,
        source=source,
        truth_level=truth_level,
    )
    connection_health = {
        "local_pg": {
            "available": local_available,
            "position_repo_available": position_repo is not None,
            "order_repo_available": order_repo is not None,
            "errors": errors,
        },
        "exchange_testnet_read": {
            "available": exchange_available,
            "reason": exchange["reason"],
            "profile": exchange["profile"],
            "testnet": exchange["testnet"],
            "errors": exchange["errors"],
        },
        "exchange_live_read": {
            "available": False,
            "reason": "forbidden in Owner Console account facts slice",
        },
        "account_equity_snapshot": {
            "available": equity_snapshot["available"],
            "source": equity_snapshot["source"],
            "truth_level": equity_snapshot["truth_level"],
            "timestamp_ms": equity_snapshot["timestamp_ms"],
            "freshness": equity_snapshot["freshness"],
            "read_method": equity_snapshot["read_method"],
            "real_account_api_called_by_endpoint": False,
        },
        "mutation_enabled": False,
        "live_ready": False,
    }
    return BrcAccountFactsResponse(
        source=source,
        truth_level=truth_level,
        generated_at_ms=generated_at_ms,
        evidence_refs=evidence_refs,
        checked_sources=checked_sources,
        source_snapshots=source_snapshots,
        reconciliation_checked_at_ms=generated_at_ms,
        mismatch_count=mismatch_count,
        unknown_unmanaged_counts=unknown_unmanaged_counts,
        account_summary={
            "controlled_symbols": _CONTROLLED_SYMBOLS,
            "active_position_count": len(positions),
            "open_order_count": len(open_orders),
            "local_active_position_count": len(local_positions),
            "local_open_order_count": len(local_open_orders),
            "exchange_position_count": len(exchange["positions"]) if exchange_available else "not_available",
            "exchange_open_order_count": len(exchange["open_orders"]) if exchange_available else "not_available",
            "all_local_flat": local_summary.get("all_local_flat", False),
            "all_exchange_flat": exchange["all_flat"] if exchange_available else "not_available",
            "account_equity": equity_snapshot["wallet_equity"],
            "wallet_equity": equity_snapshot["wallet_equity"],
            "available_margin": equity_snapshot["available_margin"],
            "account_equity_available": equity_snapshot["available"],
            "wallet_equity_available": equity_snapshot["available"],
            "available_margin_available": equity_snapshot["available_margin_available"],
            "account_equity_source": equity_snapshot["source"],
            "account_equity_truth_level": equity_snapshot["truth_level"],
            "account_equity_timestamp_ms": equity_snapshot["timestamp_ms"],
            "account_equity_freshness": equity_snapshot["freshness"],
            "account_equity_read_method": equity_snapshot["read_method"],
            "real_account_impact": "none",
            "complete_exchange_account_truth": exchange_available,
        },
        positions=positions,
        open_orders=open_orders,
        recent_orders=recent_orders,
        recent_fills=recent_fills,
        exposure_by_symbol=exposure_by_symbol,
        unknown_or_unmanaged_orders=unknown_orders,
        unknown_or_unmanaged_positions=unknown_positions,
        connection_health=connection_health,
        reconciliation_status=reconciliation_status,
        limitations=limitations,
        warnings=warnings,
        blockers=blockers,
    )


def _cached_account_equity_snapshot(api_module: Any, *, generated_at_ms: int) -> dict[str, Any]:
    gateway = getattr(api_module, "_exchange_gateway", None)
    unavailable = {
        "available": False,
        "available_margin_available": False,
        "wallet_equity": "not_available",
        "available_margin": "not_available",
        "source": "unavailable",
        "truth_level": "unavailable",
        "timestamp_ms": None,
        "freshness": "unavailable",
        "read_method": "none",
        "warnings": [],
        "limitations": [
            "No cached AccountSnapshot is available for ratio-based trial budgeting in this process.",
        ],
        "source_snapshot": {
            "available": False,
            "reason": "cached AccountSnapshot unavailable",
            "read_method": "none",
        },
    }
    if gateway is None:
        unavailable["source_snapshot"]["reason"] = "exchange gateway is not wired"
        return unavailable
    getter = getattr(gateway, "get_account_snapshot", None)
    if not callable(getter):
        unavailable["source_snapshot"]["reason"] = "gateway does not expose get_account_snapshot cache reader"
        unavailable["read_method"] = "missing_get_account_snapshot"
        unavailable["source_snapshot"]["read_method"] = "missing_get_account_snapshot"
        return unavailable
    try:
        snapshot = getter()
    except Exception as exc:  # pragma: no cover - defensive cache read path
        unavailable["source_snapshot"]["reason"] = f"cached AccountSnapshot read failed: {exc}"
        unavailable["read_method"] = "exchange_gateway.get_account_snapshot"
        unavailable["source_snapshot"]["read_method"] = "exchange_gateway.get_account_snapshot"
        unavailable["warnings"].append("Cached AccountSnapshot read failed; account equity remains unavailable.")
        return unavailable
    if snapshot is None:
        unavailable["source_snapshot"]["reason"] = "gateway cache returned no AccountSnapshot"
        unavailable["read_method"] = "exchange_gateway.get_account_snapshot"
        unavailable["source_snapshot"]["read_method"] = "exchange_gateway.get_account_snapshot"
        return unavailable

    total_balance = _snapshot_decimal(snapshot, "total_balance")
    available_balance = _snapshot_decimal(snapshot, "available_balance")
    timestamp_ms = _snapshot_int(snapshot, "timestamp")
    freshness = _snapshot_freshness(timestamp_ms, generated_at_ms=generated_at_ms)
    warnings: list[str] = []
    if freshness == "stale":
        warnings.append("Cached AccountSnapshot is stale; Owner must refresh account facts before trial start.")
    if total_balance is None:
        unavailable["source_snapshot"] = {
            "available": False,
            "reason": "cached AccountSnapshot missing total_balance",
            "read_method": "exchange_gateway.get_account_snapshot",
            "timestamp_ms": timestamp_ms,
            "freshness": freshness,
        }
        unavailable["read_method"] = "exchange_gateway.get_account_snapshot"
        unavailable["timestamp_ms"] = timestamp_ms
        unavailable["freshness"] = freshness
        unavailable["warnings"].extend(warnings)
        return unavailable

    return {
        "available": True,
        "available_margin_available": available_balance is not None,
        "wallet_equity": str(total_balance),
        "available_margin": str(available_balance) if available_balance is not None else "not_available",
        "source": "runtime_cached_account_snapshot",
        "truth_level": "cached_exchange_read",
        "timestamp_ms": timestamp_ms,
        "freshness": freshness,
        "read_method": "exchange_gateway.get_account_snapshot",
        "warnings": warnings,
        "limitations": [
            "Account equity is derived from the runtime cached AccountSnapshot and may require a fresh read-only account poll before trial start.",
            "This endpoint does not call fetch_account_balance, place_order, cancel_order, close, flatten, transfer, or withdrawal methods.",
        ],
        "source_snapshot": {
            "available": True,
            "read_method": "exchange_gateway.get_account_snapshot",
            "timestamp_ms": timestamp_ms,
            "freshness": freshness,
            "has_total_balance": total_balance is not None,
            "has_available_balance": available_balance is not None,
        },
    }


def _snapshot_decimal(snapshot: Any, field_name: str) -> Optional[Decimal]:
    value = getattr(snapshot, field_name, None)
    if value is None and isinstance(snapshot, dict):
        value = snapshot.get(field_name)
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _snapshot_int(snapshot: Any, field_name: str) -> Optional[int]:
    value = getattr(snapshot, field_name, None)
    if value is None and isinstance(snapshot, dict):
        value = snapshot.get(field_name)
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _snapshot_freshness(timestamp_ms: Optional[int], *, generated_at_ms: int) -> str:
    if timestamp_ms is None:
        return "unknown"
    max_age_ms = 5 * 60 * 1000
    if timestamp_ms > generated_at_ms + 60_000:
        return "unknown"
    return "fresh" if generated_at_ms - timestamp_ms <= max_age_ms else "stale"


async def _exchange_testnet_facts(api_module: Any) -> dict[str, Any]:
    gateway = getattr(api_module, "_exchange_gateway", None)
    profile, testnet, profile_reasons, symbols = _runtime_profile_summary(api_module)
    unavailable = {
        "available": False,
        "reason": "exchange testnet read unavailable",
        "profile": profile,
        "testnet": testnet,
        "positions": [],
        "open_orders": [],
        "recent_orders": [],
        "recent_fills": [],
        "all_flat": "not_available",
        "warnings": [],
        "errors": [],
        "limitations": [],
    }
    if gateway is None:
        unavailable["reason"] = "exchange gateway is not wired"
        unavailable["limitations"].append("Exchange testnet read source is not wired in this process.")
        return unavailable
    if profile != "brc_btc_eth_testnet_runtime" or testnet is not True:
        unavailable["reason"] = "runtime profile is not confirmed BRC exchange testnet"
        unavailable["limitations"].extend(profile_reasons or ["Exchange testnet profile is not confirmed."])
        return unavailable
    if not hasattr(gateway, "fetch_positions") or not hasattr(gateway, "fetch_open_orders"):
        unavailable["reason"] = "gateway does not expose required read-only methods"
        unavailable["limitations"].append("Gateway lacks fetch_positions/fetch_open_orders read methods.")
        return unavailable

    errors: list[str] = []
    warnings: list[str] = []
    positions: list[dict[str, Any]] = []
    open_orders: list[dict[str, Any]] = []
    recent_orders: list[dict[str, Any]] = []
    recent_fills: list[dict[str, Any]] = []
    for symbol in [str(item["exchange_symbol"]) for item in _CONTROLLED_SYMBOLS]:
        try:
            fetched_positions = await gateway.fetch_positions(symbol=symbol)
            positions.extend(_dump_jsonable(item) for item in fetched_positions if _position_nonzero(item))
        except TypeError:
            try:
                fetched_positions = await gateway.fetch_positions(symbol)
                positions.extend(_dump_jsonable(item) for item in fetched_positions if _position_nonzero(item))
            except Exception as exc:  # pragma: no cover - defensive read path
                errors.append(f"{symbol} exchange positions read failed: {exc}")
        except Exception as exc:  # pragma: no cover - defensive read path
            errors.append(f"{symbol} exchange positions read failed: {exc}")

        open_orders.extend(await _safe_fetch_exchange_orders(gateway, symbol, errors=errors))
        recent_orders.extend(await _safe_fetch_recent_orders(gateway, symbol, warnings=warnings, errors=errors))
        recent_fills.extend(await _safe_fetch_recent_fills(gateway, symbol, warnings=warnings, errors=errors))

    return {
        "available": not errors,
        "reason": "exchange testnet read available" if not errors else "exchange testnet read partially failed",
        "profile": profile,
        "testnet": testnet,
        "positions": positions,
        "open_orders": open_orders,
        "recent_orders": recent_orders,
        "recent_fills": recent_fills,
        "all_flat": len(positions) == 0 and len(open_orders) == 0,
        "warnings": warnings,
        "errors": errors,
        "limitations": [
            "Exchange read is limited to BRC controlled BTC/ETH symbols.",
            "Exchange live read and every write/mutation capability remain forbidden.",
        ],
    }


async def _safe_fetch_exchange_orders(gateway: Any, symbol: str, *, errors: list[str]) -> list[dict[str, Any]]:
    orders: list[dict[str, Any]] = []
    for params in (None, {"stop": True}):
        try:
            fetched = await _call_fetch_open_orders(gateway, symbol, params=params)
            orders.extend(_dump_jsonable(item) for item in fetched)
        except Exception as exc:  # pragma: no cover - defensive read path
            errors.append(f"{symbol} exchange open orders read failed: {exc}")
    return _dedupe_records(orders, key_fn=_order_key)


async def _safe_fetch_recent_orders(
    gateway: Any,
    symbol: str,
    *,
    warnings: list[str],
    errors: list[str],
) -> list[dict[str, Any]]:
    method = getattr(gateway, "fetch_orders", None)
    if not callable(method):
        warnings.append(f"{symbol} recent order history read method unavailable")
        return []
    try:
        try:
            return [_dump_jsonable(item) for item in await method(symbol=symbol, limit=20)]
        except TypeError:
            return [_dump_jsonable(item) for item in await method(symbol, limit=20)]
    except Exception as exc:  # pragma: no cover - defensive read path
        errors.append(f"{symbol} exchange recent orders read failed: {exc}")
        return []


async def _safe_fetch_recent_fills(
    gateway: Any,
    symbol: str,
    *,
    warnings: list[str],
    errors: list[str],
) -> list[dict[str, Any]]:
    method = getattr(gateway, "fetch_my_trades", None)
    if not callable(method):
        warnings.append(f"{symbol} recent fill history read method unavailable")
        return []
    try:
        try:
            return [_dump_jsonable(item) for item in await method(symbol=symbol, limit=20)]
        except TypeError:
            return [_dump_jsonable(item) for item in await method(symbol, limit=20)]
    except Exception as exc:  # pragma: no cover - defensive read path
        errors.append(f"{symbol} exchange recent fills read failed: {exc}")
        return []


async def _call_fetch_open_orders(gateway: Any, symbol: str, *, params: Optional[dict[str, Any]]) -> list[Any]:
    if params is None:
        return list(await gateway.fetch_open_orders(symbol))
    try:
        return list(await gateway.fetch_open_orders(symbol, params=params))
    except TypeError:
        return []


def _reconcile_account_facts(
    *,
    local_positions: list[dict[str, Any]],
    local_open_orders: list[dict[str, Any]],
    exchange_positions: list[dict[str, Any]],
    exchange_open_orders: list[dict[str, Any]],
    local_available: bool,
    exchange_available: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    if not local_available and not exchange_available:
        return {
            "status": "unknown",
            "checked_sources": [],
            "mismatches": [],
            "limitations": ["Neither local PG nor exchange testnet read source is available."],
        }, [], []
    if not exchange_available:
        return {
            "status": "not_available",
            "checked_sources": ["local_pg"] if local_available else [],
            "mismatches": [],
            "limitations": [
                "Exchange testnet read source is unavailable; reconciliation cannot prove clean or mismatch.",
            ],
        }, [], []
    if not local_available:
        return {
            "status": "unknown",
            "checked_sources": ["exchange_testnet"],
            "mismatches": [],
            "limitations": [
                "Local PG source is unavailable; exchange facts are read-only but cannot be reconciled.",
            ],
        }, [], []

    mismatches: list[dict[str, Any]] = []
    local_position_keys = {_position_key(item) for item in local_positions}
    exchange_position_by_key = {_position_key(item): item for item in exchange_positions}
    local_order_keys = {_order_key(item) for item in local_open_orders}
    exchange_order_by_key = {_order_key(item): item for item in exchange_open_orders}

    unknown_positions = [
        {"type": "exchange_position_missing_locally", "record": record}
        for key, record in exchange_position_by_key.items()
        if key not in local_position_keys
    ]
    unknown_orders = [
        {"type": "exchange_order_missing_locally", "record": record}
        for key, record in exchange_order_by_key.items()
        if key not in local_order_keys
    ]
    for key in sorted(local_position_keys - set(exchange_position_by_key.keys())):
        mismatches.append({"type": "local_position_missing_on_exchange", "key": key})
    for item in unknown_positions:
        mismatches.append({"type": item["type"], "key": _position_key(item["record"]), "record": item["record"]})
    for key in sorted(local_order_keys - set(exchange_order_by_key.keys())):
        mismatches.append({"type": "local_order_missing_on_exchange", "key": key})
    for item in unknown_orders:
        mismatches.append({"type": item["type"], "key": _order_key(item["record"]), "record": item["record"]})

    return {
        "status": "mismatch" if mismatches else "clean",
        "checked_sources": ["local_pg", "exchange_testnet"],
        "mismatches": mismatches,
        "limitations": [
            "Reconciliation compares BRC local PG active positions/open orders with exchange testnet positions/open orders.",
            "It does not authorize any write action.",
        ],
    }, unknown_orders, unknown_positions


def _exposure_by_symbol_from_facts(
    *,
    local_summary: dict[str, Any],
    positions: list[dict[str, Any]],
    open_orders: list[dict[str, Any]],
    source: str,
    truth_level: str,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for spec in _CONTROLLED_SYMBOLS:
        symbol = str(spec["exchange_symbol"])
        symbol_positions = [item for item in positions if str(item.get("symbol") or "") == symbol]
        symbol_orders = [item for item in open_orders if str(item.get("symbol") or "") == symbol]
        result[symbol] = {
            "display_symbol": spec["display_symbol"],
            "position_count": len(symbol_positions),
            "open_order_count": len(symbol_orders),
            "local_flat": len(symbol_positions) == 0 and len(symbol_orders) == 0,
            "local_position_count": len([item for item in local_summary.get("active_positions", []) if str(item.get("symbol") or "") == symbol]),
            "local_open_order_count": len([item for item in local_summary.get("open_orders", []) if str(item.get("symbol") or "") == symbol]),
            "source": source,
            "truth_level": truth_level,
            "notional": "not_available",
        }
    return result


def _dedupe_records(records: list[dict[str, Any]], *, key_fn: Any) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for record in records:
        deduped[key_fn(record)] = record
    return list(deduped.values())


def _position_nonzero(item: Any) -> bool:
    payload = _dump_jsonable(item)
    for key in ("size", "contracts", "positionAmt", "quantity", "current_qty"):
        if key in payload and _decimal_value(payload.get(key)) != Decimal("0"):
            return True
    return False


def _position_key(item: dict[str, Any]) -> str:
    symbol = str(item.get("symbol") or "unknown")
    side = str(item.get("side") or item.get("direction") or "long").lower()
    if side in {"buy", "long"}:
        side = "long"
    elif side in {"sell", "short"}:
        side = "short"
    return f"{symbol}:{side}"


def _order_key(item: dict[str, Any]) -> str:
    value = (
        item.get("exchange_order_id")
        or item.get("order_id")
        or item.get("id")
        or item.get("clientOrderId")
        or item.get("client_order_id")
    )
    if value is not None:
        return str(value)
    return f"{item.get('symbol', 'unknown')}:{item.get('side', 'unknown')}:{item.get('type', item.get('order_type', 'unknown'))}:{item.get('price', '')}"


def _decimal_value(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except Exception:
        return Decimal("0")


async def _audit_summary(service: Any, *, limit: int = 10) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    actions: list[Any] = []
    workflows: list[Any] = []
    reviews: list[Any] = []
    operation_payloads, operation_errors = await _operation_audit_results(limit)
    errors.extend(operation_errors)
    operation_timeline = [
        {
            "type": "operation",
            "id": item.get("operation_id"),
            "title": "Owner Operation / Operation Layer",
            "result": item.get("result_status") or item.get("status"),
            "occurred_at_ms": item.get("occurred_at_ms"),
            "summary": (item.get("result_summary") or {}).get("message") or item.get("operation_type"),
            "account_impact": "Operation Layer result; no live/mainnet/withdrawal/transfer authority.",
            "raw": item,
        }
        for item in operation_payloads
    ]
    if service is None:
        return {
            "timeline": operation_timeline[:limit],
            "operation_results": operation_payloads,
            "operator_actions": [],
            "workflow_runs": [],
            "review_decisions": [],
            "latest_event": operation_timeline[0] if operation_timeline else None,
        }, errors + ["BRC Campaign service unavailable"]

    for label, method_name, target in [
        ("operator actions", "list_operator_actions", "actions"),
        ("workflow runs", "list_workflow_runs", "workflows"),
        ("review decisions", "list_review_decisions", "reviews"),
    ]:
        method = getattr(service, method_name, None)
        if not callable(method):
            continue
        try:
            items = list(await method(limit=limit))
            if target == "actions":
                actions = items
            elif target == "workflows":
                workflows = items
            else:
                reviews = items
        except Exception as exc:  # pragma: no cover - defensive product summary
            errors.append(f"{label} read failed: {exc}")

    action_payloads = [_dump_jsonable(item) for item in actions]
    workflow_payloads = [_dump_jsonable(item) for item in workflows]
    review_payloads = [_dump_jsonable(item) for item in reviews]
    timeline: list[dict[str, Any]] = []
    timeline.extend(operation_timeline)
    for item in action_payloads:
        timeline.append(
            {
                "type": "operator_action",
                "id": item.get("action_id"),
                "title": "Owner 操作计划 / Operator action",
                "result": item.get("decision_result"),
                "occurred_at_ms": item.get("executed_at_ms") or item.get("created_at_ms"),
                "summary": item.get("source_text") or item.get("draft_action"),
                "account_impact": "不会影响真实账户；mutation/live/withdrawal flags are false.",
                "raw": item,
            }
        )
    for item in workflow_payloads:
        timeline.append(
            {
                "type": "workflow_run",
                "id": item.get("workflow_run_id"),
                "title": "受控流程 / Workflow",
                "result": item.get("status"),
                "occurred_at_ms": item.get("updated_at_ms") or item.get("created_at_ms"),
                "summary": item.get("action") or item.get("normalized_action"),
                "account_impact": "创建 workflow 本身不影响真实账户；执行仍需 Owner confirmation.",
                "raw": item,
            }
        )
    for item in review_payloads:
        timeline.append(
            {
                "type": "review_decision",
                "id": item.get("review_id"),
                "title": "复盘决策 / Review decision",
                "result": item.get("decision"),
                "occurred_at_ms": item.get("created_at_ms"),
                "summary": item.get("reason_text") or item.get("next_recommended_task"),
                "account_impact": "复盘记录只写数据库事实，不创建 campaign 或触发 testnet.",
                "raw": item,
            }
        )
    timeline.sort(key=lambda item: int(item.get("occurred_at_ms") or 0), reverse=True)
    return {
        "timeline": timeline[:limit],
        "operation_results": operation_payloads,
        "operator_actions": action_payloads,
        "workflow_runs": workflow_payloads,
        "review_decisions": review_payloads,
        "latest_event": timeline[0] if timeline else None,
    }, errors


def _parameter_summary(profile: Optional[str], testnet: Optional[bool]) -> dict[str, Any]:
    return {
        "runtime_profile": profile,
        "exchange_testnet": testnet,
        "controlled_symbols": _CONTROLLED_SYMBOLS,
        "risk_envelope": {
            "max_simultaneous_positions": 1,
            "max_attempts": 2,
            "mock_pnl_only": True,
            "loss_counter_resets_on_playbook_switch": False,
        },
        "confirmation_phrases": {
            "read_only": "CONFIRM_READ_ONLY_BRC",
            "controlled_testnet": "CONFIRM_BRC_TESTNET_REHEARSAL",
        },
        "unauthorized_capabilities": [
            "real_live",
            "withdrawal_or_transfer",
            "automatic_strategy_execution",
            "automatic_sizing_or_leverage_override",
            "strategy_pool_execution",
        ],
    }


def _action(
    *,
    action_id: str,
    title: str,
    description: str,
    enabled: bool,
    disabled_reason: Optional[str],
    route: Optional[str],
    button_label: str,
    what_happens: str,
    risk_level: Literal["read_only", "controlled_testnet", "blocked"] = "read_only",
) -> BrcActionReadiness:
    return BrcActionReadiness(
        action_id=action_id,
        title=title,
        description=description,
        enabled=enabled,
        disabled_reason=None if enabled else disabled_reason,
        route=route if enabled else route,
        button_label=button_label,
        what_happens=what_happens,
        risk_level=risk_level if enabled else "blocked",
    )


def _risk_decision(
    *,
    runtime_ready: bool,
    service_error: Optional[str],
    market_errors: list[str],
    audit_errors: list[str],
    markets_summary: dict[str, Any],
    mutation_env_ready: bool,
) -> RiskDecision:
    if service_error:
        return "BLOCK_ALL_STATE_CHANGE"
    if market_errors or audit_errors:
        return "ATTENTION_REQUIRED"
    if not bool(markets_summary.get("all_local_flat", False)):
        return "ATTENTION_REQUIRED"
    if not runtime_ready:
        return "ALLOW_READ"
    if not mutation_env_ready:
        return "ALLOW_MONITOR"
    return "ALLOW_MONITOR"


def _runtime_state(
    *,
    risk_decision: RiskDecision,
    runtime_ready: bool,
    mutation_env_ready: bool,
    gks_active: Optional[bool],
) -> RuntimeState:
    if risk_decision in {"ATTENTION_REQUIRED", "BLOCK_ALL_STATE_CHANGE"}:
        return "attention_required"
    if not runtime_ready:
        return "observe"
    if gks_active is True:
        return "paused"
    if mutation_env_ready:
        return "monitor"
    return "monitor"


def _fact_snapshot_id(
    *,
    runtime_ready: bool,
    profile: Optional[str],
    testnet: Optional[bool],
    markets_summary: dict[str, Any],
    audit_summary: dict[str, Any],
    risk_decision: RiskDecision,
) -> str:
    latest = audit_summary.get("latest_event") or {}
    parts = [
        "brc-v0",
        "runtime" if runtime_ready else "standalone",
        str(profile or "no-profile"),
        "testnet" if testnet is True else "not-testnet",
        f"pos{markets_summary.get('active_position_count', 'x')}",
        f"ord{markets_summary.get('open_order_count', 'x')}",
        str(latest.get("id") or "no-audit"),
        risk_decision,
    ]
    return ":".join(parts)


def _action_card(
    *,
    action_type: ActionCardType,
    title: str,
    enabled: bool,
    disabled_reason: Optional[str],
    route: Optional[str],
    button_label: str,
    fact_snapshot_id: str,
    current_state: RuntimeState,
    allowed_next_states: list[RuntimeState],
    blocked_next_states: Optional[list[str]] = None,
    reversible: bool = False,
    final_state_proof_required: bool = False,
    hard_blocks: Optional[list[str]] = None,
    advisory_warnings: Optional[list[str]] = None,
    confirmation_phrase: Optional[str] = None,
    account_impact: str = "不会影响真实账户。",
    what_will_change: str = "只读取当前系统状态。",
    what_will_not_change: str = "不会启用真实实盘、提现/转账、自动 sizing/leverage 或策略池执行。",
    expiry_seconds: Optional[int] = 300,
) -> BrcActionCard:
    action_card_id = f"brc-card-{action_type}"
    preflight_result_id = f"preflight-{action_type}-{'allow' if enabled else 'block'}"
    expiry_time = int(time.time() * 1000) + expiry_seconds * 1000 if expiry_seconds is not None else None
    blocks = list(hard_blocks or [])
    if not enabled and disabled_reason:
        blocks.append(disabled_reason)
    return BrcActionCard(
        action_card_id=action_card_id,
        title=title,
        action_type=action_type,
        enabled=enabled,
        disabled_reason=None if enabled else disabled_reason,
        route=route,
        button_label=button_label,
        fact_snapshot_id=fact_snapshot_id,
        preflight_result_id=preflight_result_id,
        idempotency_key=f"{fact_snapshot_id}:{action_type}",
        expiry_time=expiry_time,
        current_state=current_state,
        allowed_next_states=allowed_next_states if enabled else [],
        blocked_next_states=list(blocked_next_states or []),
        reversible=reversible,
        final_state_proof_required=final_state_proof_required,
        hard_blocks=blocks,
        advisory_warnings=list(advisory_warnings or []),
        confirmation_phrase=confirmation_phrase,
        account_impact=account_impact,
        what_will_change=what_will_change,
        what_will_not_change=what_will_not_change,
    )


@router.get("/readiness", response_model=BrcReadinessResponse)
async def get_brc_readiness() -> BrcReadinessResponse:
    api_module = _api_module()
    runtime_context = api_module.get_runtime_context()
    service = getattr(api_module, "_brc_campaign_service", None)
    profile, testnet, profile_reasons, symbols = _runtime_profile_summary(api_module)
    gks_active, startup_guard_armed = _guard_summary(api_module)

    latest_campaign = None
    latest_review = None
    latest_operator_action = None
    service_error = None
    if service is not None:
        try:
            latest_campaign = await service.get_latest_campaign()
            latest_review = await service.get_latest_review_decision()
            if hasattr(service, "list_operator_actions"):
                actions = await service.list_operator_actions(limit=1)
                latest_operator_action = actions[0] if actions else None
        except Exception as exc:  # pragma: no cover - defensive product summary
            service_error = str(exc)

    markets_summary, market_errors = await _markets_orders_summary(api_module)
    readiness_generated_at_ms = int(time.time() * 1000)
    equity_snapshot = _cached_account_equity_snapshot(
        api_module,
        generated_at_ms=readiness_generated_at_ms,
    )
    audit_summary, audit_errors = await _audit_summary(service, limit=5)

    reasons: list[str] = []
    if runtime_context is None:
        reasons.append("当前只是 Standalone Console，后端没有绑定运行时 Runtime。")
    if service is None:
        reasons.append("当前没有连接 BRC Campaign 服务，不能读取或写入 campaign 治理数据。")
    if service_error:
        reasons.append("BRC Campaign 服务读取失败，页面只能显示安全说明。")
    reasons.extend(profile_reasons)
    if market_errors:
        reasons.append("交易对/订单摘要只能部分读取，详情见 Developer Detail。")
    if audit_errors and service is not None:
        reasons.append("审计摘要只能部分读取，详情见 Developer Detail。")

    runtime_ready = runtime_context is not None and service is not None and not profile_reasons
    has_campaign = latest_campaign is not None
    mutation_env_ready = _env_enabled("RUNTIME_CONTROL_API_ENABLED") and _env_enabled(
        "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED"
    )
    testnet_ready = runtime_ready and mutation_env_ready
    risk_decision = _risk_decision(
        runtime_ready=runtime_ready,
        service_error=service_error,
        market_errors=market_errors,
        audit_errors=audit_errors if service is not None else [],
        markets_summary=markets_summary,
        mutation_env_ready=mutation_env_ready,
    )
    runtime_state = _runtime_state(
        risk_decision=risk_decision,
        runtime_ready=runtime_ready,
        mutation_env_ready=mutation_env_ready,
        gks_active=gks_active,
    )
    fact_snapshot_id = _fact_snapshot_id(
        runtime_ready=runtime_ready,
        profile=profile,
        testnet=testnet,
        markets_summary=markets_summary,
        audit_summary=audit_summary,
        risk_decision=risk_decision,
    )

    if runtime_context is None:
        mode: Literal["standalone_console", "runtime_bound_console", "brc_ready", "testnet_ready", "blocked"] = "standalone_console"
        conclusion = "当前只能查看，不能执行 BRC campaign 操作。"
        next_step = "启动绑定 BRC runtime 的后端后，回到 Command Center 刷新状态。"
    elif not runtime_ready:
        mode = "runtime_bound_console"
        conclusion = "运行时已连接，但 BRC 操作条件还不完整。"
        next_step = "先检查运行配置 Profile、测试网 Testnet 和 BRC 服务初始化状态。"
    elif testnet_ready:
        mode = "testnet_ready"
        conclusion = "当前满足受控测试网 workflow 的基础门槛。"
        next_step = "主链路已可进入：打开 LLM Copilot，创建 testnet_rehearsal action card，并手动输入确认短语。"
    else:
        mode = "brc_ready"
        conclusion = "当前可以进行 BRC 只读治理操作；testnet 演练仍需额外门槛。"
        next_step = "优先生成只读操作计划或复盘最近 campaign。"

    if not reasons:
        reasons.append("基础 BRC 运行条件已满足；具体动作仍需要 Owner 手动确认。")

    no_runtime_reason = "需要绑定 BRC runtime、解析 BRC testnet profile，并初始化 BRC Campaign 服务。"
    no_campaign_reason = "当前没有可复盘的 campaign，Review decision 需要绑定一轮已存在的 campaign。"
    testnet_missing = []
    if not runtime_ready:
        testnet_missing.append(no_runtime_reason)
    if not _env_enabled("RUNTIME_CONTROL_API_ENABLED"):
        testnet_missing.append("本地 runtime control mutation 开关未开启。")
    if not _env_enabled("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED"):
        testnet_missing.append("本地 test signal injection 开关未开启。")
    no_testnet_reason = " ".join(testnet_missing) or "受控 testnet workflow 需要 BRC profile、Exchange Testnet 和本地 mutation/test-signal 开关同时满足。"

    actions = [
        _action(
            action_id="view_runtime_safety",
            title="查看运行安全 Runtime Safety",
            description="查看运行时 Runtime、测试网 Testnet、全局安全开关 GKS 和启动保护 Startup Guard。",
            enabled=True,
            disabled_reason=None,
            route="/runtime-safety",
            button_label="查看运行安全",
            what_happens="打开只读安全检查页面，不会触发 runtime 或 exchange 动作。",
        ),
        _action(
            action_id="create_read_only_plan",
            title="生成只读计划 Operator Plan",
            description="把 Owner 文本转成 review/evidence/eligibility 等只读操作计划。",
            enabled=runtime_ready,
            disabled_reason=no_runtime_reason,
            route="/operator",
            button_label="生成只读计划",
            what_happens="创建一条 operator action 计划；执行前仍需手动输入确认短语。",
        ),
        _action(
            action_id="create_workflow",
            title="创建受控流程 Workflow",
            description="让 LLM workflow 归一化 Owner 意图，并进入确认前检查。",
            enabled=runtime_ready,
            disabled_reason=no_runtime_reason,
            route="/workflow",
            button_label="创建 Workflow",
            what_happens="创建 workflow run；不会自动执行交易或绕过 Owner confirmation。",
        ),
        _action(
            action_id="write_review_decision",
            title="写入复盘决策 Review",
            description="基于最近 campaign 证据写入 Owner 复盘结论和下一步任务。",
            enabled=runtime_ready and has_campaign,
            disabled_reason=no_campaign_reason if runtime_ready else no_runtime_reason,
            route="/review",
            button_label="写复盘决策",
            what_happens="写入 review decision 记录，不会创建 campaign 或触发 testnet。",
        ),
        _action(
            action_id="view_ledger",
            title="查看操作记录 Ledger",
            description="查看 operator actions、workflow runs 和 review decisions 的审计摘要。",
            enabled=runtime_ready,
            disabled_reason=no_runtime_reason,
            route="/ledger",
            button_label="查看操作记录",
            what_happens="读取数据库事实记录，不会重放或修改任何历史动作。",
        ),
        _action(
            action_id="run_controlled_testnet_workflow",
            title="受控测试网演练 Controlled Testnet",
            description="执行固定 ETH -> mock profit -> BTC -> mock loss -> finalize 的受控 testnet workflow。",
            enabled=testnet_ready,
            disabled_reason=no_testnet_reason,
            route="/workflow",
            button_label="准备 testnet 演练",
            what_happens="只有在专用确认短语输入后，固定 workflow 才会临时打开 entry window，并在结束后恢复 GKS/Startup Guard 保护态。",
            risk_level="controlled_testnet",
        ),
    ]

    available = [action for action in actions if action.enabled]
    disabled = [action for action in actions if not action.enabled]
    campaign_summary = _campaign_summary(latest_campaign)
    review_summary = {
        "latest_review_present": latest_review is not None,
        "latest_review": latest_review.model_dump(mode="json") if latest_review is not None else None,
        "latest_operator_action_present": latest_operator_action is not None,
        "latest_operator_action": latest_operator_action.model_dump(mode="json")
        if latest_operator_action is not None
        else None,
        "review_available": runtime_ready and has_campaign,
    }
    playbook_summary = {
        "current_playbook_id": campaign_summary.get("current_playbook_id") if campaign_summary else "PB-000-OBSERVE-ONLY",
        "current_playbook_meaning": "Playbook 是人工打法/治理框架，不等于可自动执行策略。",
        "strategy_execution_enabled": False,
        "strategy_execution_status": "未启用可执行 Strategy；策略池后续单独建设。",
        "catalog": [
            {"playbook_id": "PB-000-OBSERVE-ONLY", "label": "Observe Only", "status": "available"},
            {"playbook_id": "PB-001-DIRECTION-A-PAPER", "label": "Direction A Paper", "status": "observe_only"},
            {"playbook_id": "PB-002-SQ02-DOWNSIDE-PAPER", "label": "SQ02 Downside Paper", "status": "docs_only"},
            {"playbook_id": "PB-003-MANUAL-DISCRETIONARY", "label": "Manual Discretionary", "status": "governed_only"},
            {"playbook_id": "PB-004-BRC-CONTROLLED-TESTNET", "label": "BRC Controlled Testnet", "status": "testnet_only"},
        ],
    }
    parameter_summary = _parameter_summary(profile, testnet)
    environment_boundary = {
        "trading_env": os.environ.get("TRADING_ENV", "simulation").strip().lower() or "simulation",
        "brc_execution_permission_max": os.environ.get(
            "BRC_EXECUTION_PERMISSION_MAX",
            "read_only",
        ).strip().lower() or "read_only",
        "resolved_permission": "intent_recording"
        if (
            os.environ.get("TRADING_ENV", "simulation").strip().lower() == "live"
            and os.environ.get("BRC_EXECUTION_PERMISSION_MAX", "read_only").strip().lower()
            == "intent_recording"
        )
        else "read_only",
        "live_read_only": (
            os.environ.get("TRADING_ENV", "simulation").strip().lower() == "live"
            and os.environ.get("BRC_EXECUTION_PERMISSION_MAX", "read_only").strip().lower()
            == "intent_recording"
        ),
        "execution_intent_allowed": False,
        "order_allowed": False,
        "current": "simulation",
        "exchange_mode": "binance_testnet" if testnet is True else "unknown_or_not_testnet",
        "executable_modes": ["local", "mock", "binance_testnet"],
        "future_live": {
            "modeled": True,
            "available": False,
            "display": "disabled_boundary",
            "reason": "requires separate Owner production authorization plus cloud/security/secret/replay/permission work",
        },
        "production_authorized": False,
        "real_account_impact": "none",
    }
    risk_account_summary = {
        "risk_decision": risk_decision,
        "account_state": {
            "environment": environment_boundary["current"],
            "exchange_mode": environment_boundary["exchange_mode"],
            "real_account_impact": "none",
            "wallet_equity_available": equity_snapshot["available"],
            "available_margin_available": equity_snapshot["available_margin_available"],
            "wallet_equity": equity_snapshot["wallet_equity"],
            "available_margin": equity_snapshot["available_margin"],
            "account_equity_source": equity_snapshot["source"],
            "account_equity_truth_level": equity_snapshot["truth_level"],
            "account_equity_timestamp_ms": equity_snapshot["timestamp_ms"],
            "account_equity_freshness": equity_snapshot["freshness"],
            "account_equity_read_method": equity_snapshot["read_method"],
            "real_account_api_called_by_readiness": False,
        },
        "exposure_orders": {
            "symbols": markets_summary.get("symbols", []),
            "active_positions": markets_summary.get("active_positions", []),
            "open_orders": markets_summary.get("open_orders", []),
            "active_position_count": markets_summary.get("active_position_count", 0),
            "open_order_count": markets_summary.get("open_order_count", 0),
            "order_source": "local_pg_repositories_only",
            "unknown_exposure": not bool(markets_summary.get("all_local_flat", False)),
            "flatness_proof": {
                "all_local_flat": bool(markets_summary.get("all_local_flat", False)),
                "source": markets_summary.get("data_source"),
                "timestamp_ms": int(time.time() * 1000),
            },
        },
        "risk_envelope": parameter_summary["risk_envelope"],
        "loss_lock_status": campaign_summary.get("status") if campaign_summary else "no_campaign",
        "profit_protect_status": "not_triggered_or_unknown",
        "daily_realized_pnl": "not_available_in_console_v0",
        "daily_trade_count": "not_available_in_console_v0",
        "audit_writable": service is not None and not audit_errors,
        "cutoff_available": runtime_ready,
    }
    strategy_playbook_summary = {
        **playbook_summary,
        "current_strategy_family": "Trend Following" if playbook_summary["current_playbook_id"] == "TF-001" else "BRC Controlled Testnet / Governance",
        "current_mode": runtime_state,
        "r5_carrier": {
            "playbook_id": "TF-001",
            "purpose": "carrier_validation_only",
            "implementation_status": "later_slice",
            "alpha_claim": False,
        },
    }
    read_enabled = True
    monitor_enabled = runtime_ready and risk_decision in {"ALLOW_MONITOR", "BLOCK_TESTNET"}
    testnet_action_enabled = testnet_ready and risk_decision == "ALLOW_MONITOR"
    cutoff_enabled = runtime_ready
    action_cards = [
        _action_card(
            action_type="read_status",
            title="Read current status",
            enabled=read_enabled,
            disabled_reason=None,
            route="/command-center",
            button_label="查看状态",
            fact_snapshot_id=fact_snapshot_id,
            current_state=runtime_state,
            allowed_next_states=[runtime_state],
            reversible=True,
            final_state_proof_required=False,
            what_will_change="只刷新 Command Center / Risk & Account 的只读状态。",
        ),
        _action_card(
            action_type="enter_monitor",
            title="Enter monitor",
            enabled=monitor_enabled,
            disabled_reason="需要绑定 runtime、BRC 服务、可读风险状态，并且不能处于 attention_required。",
            route="/llm-copilot",
            button_label="准备 monitor",
            fact_snapshot_id=fact_snapshot_id,
            current_state=runtime_state,
            allowed_next_states=["monitor"],
            blocked_next_states=["live_trade", "strategy_pool_execution"],
            reversible=True,
            final_state_proof_required=False,
            advisory_warnings=["Monitor 不授予订单权限。"],
            confirmation_phrase="CONFIRM_READ_ONLY_BRC",
            what_will_change="生成进入 monitor 的应用层 action card；不会直接下单。",
        ),
        _action_card(
            action_type="testnet_rehearsal",
            title="Fixed BRC testnet rehearsal",
            enabled=testnet_action_enabled,
            disabled_reason=no_testnet_reason if not testnet_ready else "当前风险判定不允许 testnet_rehearsal。",
            route="/llm-copilot",
            button_label="准备 testnet_rehearsal",
            fact_snapshot_id=fact_snapshot_id,
            current_state=runtime_state,
            allowed_next_states=["testnet_rehearsal", "attention_required"],
            blocked_next_states=["live_trade", "withdrawal", "transfer", "strategy_pool_execution"],
            reversible=False,
            final_state_proof_required=True,
            advisory_warnings=[
                "只允许固定 ETH/BTC BRC 测试网演练。",
                "策略证据是 advisory，不是执行授权。",
            ],
            confirmation_phrase="CONFIRM_BRC_TESTNET_REHEARSAL",
            account_impact="只影响 Binance testnet；不会影响真实账户。",
            what_will_change="Owner 确认后执行固定 BRC ETH/BTC testnet rehearsal 并写入审计和复盘证据。",
        ),
    ]
    global_cutoff_controls = [
        _action_card(
            action_type="pause_new_entries",
            title="Pause new entries",
            enabled=cutoff_enabled,
            disabled_reason=no_runtime_reason,
            route="/runtime-control",
            button_label="Pause",
            fact_snapshot_id=fact_snapshot_id,
            current_state=runtime_state,
            allowed_next_states=["paused"],
            reversible=True,
            final_state_proof_required=False,
            confirmation_phrase="CONFIRM_READ_ONLY_BRC",
            what_will_change="停止新增开仓意图；不主动平掉已有 exposure。",
        ),
        _action_card(
            action_type="emergency_stop_runtime",
            title="Emergency stop runtime",
            enabled=cutoff_enabled,
            disabled_reason=no_runtime_reason,
            route="/runtime-control",
            button_label="Stop runtime",
            fact_snapshot_id=fact_snapshot_id,
            current_state=runtime_state,
            allowed_next_states=["stopped"],
            reversible=False,
            final_state_proof_required=False,
            confirmation_phrase="CONFIRM_READ_ONLY_BRC",
            what_will_change="停止 runtime-driven 活动；不代表交易所残留单已自动消失。",
        ),
        _action_card(
            action_type="emergency_flatten",
            title="Emergency flatten dry-run",
            enabled=cutoff_enabled,
            disabled_reason=no_runtime_reason,
            route="/runtime-control",
            button_label="Dry-run plan",
            fact_snapshot_id=fact_snapshot_id,
            current_state=runtime_state,
            allowed_next_states=["attention_required"],
            reversible=False,
            final_state_proof_required=False,
            confirmation_phrase="CONFIRM_FLATTEN_DRY_RUN",
            account_impact="仅持久化 dry-run plan；不会撤单、平仓、下单或影响真实账户。",
            what_will_change="生成并持久化 emergency flatten dry-run plan；候选项不是可执行交易请求。",
        ),
    ]

    return BrcReadinessResponse(
        mode=mode,
        current_conclusion=conclusion,
        why=reasons,
        account_impact="不会影响真实账户；readiness 只读，不会下单、提现、转账或修改仓位。",
        next_step=next_step,
        available_actions=available,
        disabled_actions=disabled,
        latest_campaign=campaign_summary,
        environment_boundary=environment_boundary,
        runtime_state=runtime_state,
        risk_decision=risk_decision,
        risk_account_summary=risk_account_summary,
        strategy_playbook_summary=strategy_playbook_summary,
        action_cards=action_cards,
        global_cutoff_controls=global_cutoff_controls,
        latest_audit=audit_summary.get("latest_event"),
        runtime_summary={
            "runtime_bound": runtime_context is not None,
            "profile": profile,
            "testnet": testnet,
            "symbols": symbols,
            "gks_active": gks_active,
            "startup_guard_armed": startup_guard_armed,
            "brc_service_ready": service is not None,
            "mutation_env_ready": mutation_env_ready,
        },
        review_summary=review_summary,
        markets_summary=markets_summary,
        playbook_summary=playbook_summary,
        parameter_summary=parameter_summary,
        audit_summary=audit_summary,
        ai_investigator_summary={
            "mode": "controlled_read_only_resolver",
            "free_sql_enabled": False,
            "can_answer": [
                "这个订单怎么触发的？",
                "现在系统能不能继续？",
                "为什么 blocked？",
                "上一轮 campaign 结果是什么？",
                "最近发生了哪些关键操作？",
            ],
            "cannot_do": [
                "下单",
                "改参数",
                "切换 playbook",
                "提现/转账",
                "自由 SQL",
            ],
        },
        developer_details={
            "runtime_context_bound": runtime_context is not None,
            "brc_campaign_service_present": service is not None,
            "service_error": service_error,
            "profile_reasons": profile_reasons,
            "market_errors": market_errors,
            "audit_errors": audit_errors,
            "mutation_env": {
                "runtime_control_api_enabled": _env_enabled("RUNTIME_CONTROL_API_ENABLED"),
                "runtime_test_signal_injection_enabled": _env_enabled("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED"),
            },
            "live_ready": False,
        },
    )


@router.get("/readiness/mi001-sol", response_model=Mi001SolOwnerConsoleE2EResponse)
async def get_mi001_sol_owner_console_e2e() -> Mi001SolOwnerConsoleE2EResponse:
    """Return a read-only Owner Console view for the MI-001 SOL trial chain."""
    api_module = _api_module()
    runtime_bound = api_module.get_runtime_context() is not None
    gks_active, startup_guard_armed = _guard_summary(api_module)
    control_enabled = _env_enabled("RUNTIME_CONTROL_API_ENABLED")
    startup_action_enabled = (
        runtime_bound
        and startup_guard_armed is not True
        and control_enabled
        and getattr(api_module, "_startup_trading_guard_service", None) is not None
    )

    if gks_active is True:
        verdict = "blocked_gks_active"
        blockers = ["GKS active=True blocks new entries"]
    elif startup_guard_armed is True:
        verdict = "ready_for_trial_start_after_owner_approval"
        blockers = []
    else:
        verdict = "blocked_startup_guard_runtime_coupled"
        blockers = [
            "StartupTradingGuardService is runtime-owned and is not armed in this console process"
        ]
    gks_status = "pass" if gks_active is False else "blocked" if gks_active is True else "not_checked"
    gks_evidence = (
        f"active={gks_active}"
        if gks_active is not None
        else "runtime GKS service is not bound in this console process"
    )

    checks = [
        Mi001SolCheckView(
            check="PG registration",
            status="pass",
            evidence="MI-001 registration chain applied to PG metadata/admission records",
        ),
        Mi001SolCheckView(
            check="Owner trial-start metadata approval",
            status="pass",
            evidence="MI-001-SOL-LONG-owner-trial-start-approval-v1",
        ),
        Mi001SolCheckView(
            check="Account facts",
            status="pass",
            evidence="live read-only Binance USDT futures account facts available",
        ),
        Mi001SolCheckView(
            check="Operation Layer notional cap",
            status="pass",
            evidence="18262.85481460",
        ),
        Mi001SolCheckView(
            check="GKS",
            status=gks_status,
            evidence=gks_evidence,
            blocking=gks_active is True,
        ),
        Mi001SolCheckView(
            check="Startup guard",
            status="pass" if startup_guard_armed is True else "blocked",
            evidence=(
                "armed=True"
                if startup_guard_armed is True
                else "runtime-owned guard not armed; use guard-only preflight endpoint"
            ),
            blocking=startup_guard_armed is not True,
        ),
        Mi001SolCheckView(
            check="SOL active position / open orders",
            status="pass",
            evidence="SOL active position=0; SOL open orders=0",
        ),
    ]

    allowed_actions = [
        Mi001SolOwnerActionView(
            action_id="review_mi001_sol",
            label="Review MI-001 SOL readiness",
            enabled=True,
            safety_text="Read-only review of candidate, evidence, policy, and blockers.",
        ),
        Mi001SolOwnerActionView(
            action_id="arm_startup_guard_preflight",
            label="Arm startup guard preflight",
            enabled=startup_action_enabled,
            endpoint="/api/brc/readiness/startup-guard/preflight-arm",
            disabled_reason=(
                None
                if startup_action_enabled
                else "Requires bound runtime context, initialized runtime-owned startup guard, and RUNTIME_CONTROL_API_ENABLED=true."
            ),
            safety_text="Readiness-only guard action; not trial start and not order permission.",
        ),
    ]
    disabled_actions = [
        Mi001SolOwnerActionView(
            action_id="start_trial",
            label="Start trial",
            enabled=False,
            disabled_reason="Not exposed by this Owner Console acceptance view.",
            safety_text="Trial start remains a separate manual control path.",
        ),
        Mi001SolOwnerActionView(
            action_id="place_order",
            label="Place order",
            enabled=False,
            disabled_reason="Order capability is not granted by readiness.",
            safety_text="No order endpoint is exposed here.",
        ),
        Mi001SolOwnerActionView(
            action_id="grant_execution_permission",
            label="Grant execution permission",
            enabled=False,
            disabled_reason="Execution permission is not modified by readiness.",
            safety_text="No execution permission mutation is exposed here.",
        ),
    ]

    return Mi001SolOwnerConsoleE2EResponse(
        candidate=Mi001SolCandidateView(
            status=verdict,
        ),
        evidence=Mi001SolEvidenceView(),
        risk_policy=Mi001SolRiskPolicyView(),
        readiness=Mi001SolReadinessView(
            verdict=verdict,
            blockers=blockers,
            checks=checks,
        ),
        owner_actions={
            "allowed_actions": allowed_actions,
            "disabled_actions": disabled_actions,
        },
        non_permissions=Mi001SolNonPermissionsView(),
        startup_guard_action=Mi001SolStartupGuardActionView(
            enabled=startup_action_enabled,
            enabled_when=[
                "runtime context is bound",
                "_startup_trading_guard_service is initialized",
                "RUNTIME_CONTROL_API_ENABLED=true",
                "BRC operator session is authenticated",
            ],
        ),
        terminal_state=(
            "ready_for_trial_start_after_owner_approval"
            if verdict == "ready_for_trial_start_after_owner_approval"
            else "blocked_until_startup_guard_preflight"
        ),
        source_refs=[
            "brc_strategy_family_registry:MI-001:MI-001-smoke-v0",
            "brc_admission_requests:MI-001-SOL-LONG-admission-request-v1",
            "brc_trial_constraint_snapshots:MI-001-SOL-LONG-trial-constraints-v1",
            "brc_owner_risk_acceptances:MI-001-SOL-LONG-owner-trial-start-approval-v1",
            "reports/directional-opportunity-broad-smoke-20260529/trial_start_checklist_mi001_sol_long.md",
        ],
    )


@router.get(
    "/strategy-groups/reviewability",
    response_model=StrategyGroupReviewabilityResponse,
)
async def get_strategy_group_reviewability() -> StrategyGroupReviewabilityResponse:
    """Return the read-only Owner-reviewable strategy group shelf."""
    return build_strategy_group_reviewability_snapshot()


@router.get(
    "/strategy-groups/live-readonly-observation/v1",
    response_model=StrategyGroupLiveReadOnlyObservationResponse,
)
async def get_strategy_group_live_readonly_observation_v1() -> StrategyGroupLiveReadOnlyObservationResponse:
    """Return MI/CPM read-only observation v1 status without starting runtime."""
    return await _strategy_group_live_readonly_observation_response(
        record_observation=False,
        source_name="local_sqlite_fallback",
    )


@router.post(
    "/strategy-groups/live-readonly-observation/v1/run-once",
    response_model=StrategyGroupLiveReadOnlyObservationResponse,
)
async def run_strategy_group_live_readonly_observation_v1_once(
    source: Literal["local_sqlite_fallback", "live_market"] = Query(default="local_sqlite_fallback"),
) -> StrategyGroupLiveReadOnlyObservationResponse:
    """Record one observe-only MI/CPM signal snapshot without runtime start."""
    return await _strategy_group_live_readonly_observation_response(
        record_observation=True,
        source_name=source,
    )


@router.get(
    "/strategy-groups/observation-cases/v1",
    response_model=ObservationCaseQueueResponse,
)
async def get_strategy_group_observation_cases_v1(
    candidate_id: str | None = Query(default=None),
    strategy_group_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> ObservationCaseQueueResponse:
    """Return the Owner-review case queue for would-enter observations only."""
    try:
        pg_available = await probe_pg_connectivity()
        if not pg_available:
            return blocked_observation_case_queue(reason="pg_unavailable")
        observation_repo = PgStrategyGroupObservationRepository()
        forward_review_repo = PgStrategyGroupForwardReviewRepository()
        observations = await observation_repo.list_recent(limit=200)
        would_enter_ids = [record.record_id for record in observations if record.signal_type == "would_enter"]
        reviews = await forward_review_repo.list_by_observation_ids(would_enter_ids)
        return build_observation_case_queue(
            observations,
            reviews,
            candidate_id=candidate_id,
            strategy_group_id=strategy_group_id,
            status=status,
        )
    except Exception as exc:
        reason = f"pg_read_failed_{type(exc).__name__}"
        response = blocked_observation_case_queue(reason=reason)
        return response.model_copy(
            update={
                "source_refs": response.source_refs
                + [f"error: {type(exc).__name__}: {str(exc)[:160]}"],
            }
        )


@router.get(
    "/readiness/mi001-bnb/trial-gap",
    response_model=Mi001BnbTrialReadinessGapResponse,
)
async def get_mi001_bnb_trial_readiness_gap() -> Mi001BnbTrialReadinessGapResponse:
    """Return BNB trial-readiness gap map without granting execution authority."""
    return build_mi001_bnb_trial_readiness_gap()


@router.get(
    "/strategy-trial-architecture/bnb-first-carrier",
    response_model=StrategyTrialArchitectureGovernanceResponse,
)
async def get_bnb_first_carrier_architecture_governance() -> StrategyTrialArchitectureGovernanceResponse:
    """Return the generic StrategyFamily/Carrier governance state for BNB.

    This endpoint is an Owner-review surface only. It does not create a live
    authorization, execution intent, order, runtime start, or execution
    permission.
    """
    return build_bnb_strategy_trial_architecture_governance()


@router.get(
    "/strategy-trial-architecture/second-carrier-expansion",
    response_model=SecondCarrierExpansionResponse,
)
async def get_second_carrier_expansion_bootstrap() -> SecondCarrierExpansionResponse:
    """Return generic second-carrier bootstrap metadata.

    This endpoint is read-only and non-live. It does not create a live
    authorization, execution intent, order, runtime start, or execution
    permission.
    """
    return build_second_carrier_expansion_bootstrap()


@router.get(
    "/owner-trial-flow/current",
    response_model=OwnerTrialFlowCurrentResponse,
)
async def get_owner_trial_flow_current(
    carrier_id: str = Query(default="MI-001-BNB-LONG"),
) -> OwnerTrialFlowCurrentResponse:
    """Return persisted Owner trial-flow metadata without execution authority."""
    try:
        return await _owner_trial_flow_service_instance().current(carrier_id=carrier_id)
    except OwnerTrialFlowInfrastructureError as exc:
        raise _owner_trial_flow_infrastructure_http_error(exc) from exc
    except OwnerTrialFlowError as exc:
        raise _owner_trial_flow_http_error(exc) from exc


@router.get(
    "/budget-authorizations/current",
    response_model=MultiCarrierBudgetAuthorizationCurrentResponse,
)
async def get_multi_carrier_budget_authorization_current() -> MultiCarrierBudgetAuthorizationCurrentResponse:
    """Return PG-backed disabled multi-carrier budget metadata."""
    try:
        return await _multi_carrier_budget_authorization_service_instance().current()
    except MultiCarrierBudgetAuthorizationInfrastructureError as exc:
        raise _multi_carrier_budget_authorization_infrastructure_http_error(exc) from exc


@router.post(
    "/budget-authorizations/foundation",
    response_model=MultiCarrierBudgetAuthorization,
)
async def create_multi_carrier_budget_authorization_foundation(
    body: MultiCarrierBudgetAuthorizationCreateRequest,
    session: OperatorSessionDependency,
) -> MultiCarrierBudgetAuthorization:
    """Persist disabled multi-carrier budget authorization metadata only."""
    _ = session
    try:
        return await _multi_carrier_budget_authorization_service_instance().create_foundation(body)
    except MultiCarrierBudgetAuthorizationInfrastructureError as exc:
        raise _multi_carrier_budget_authorization_infrastructure_http_error(exc) from exc
    except MultiCarrierBudgetAuthorizationError as exc:
        raise _multi_carrier_budget_authorization_http_error(exc) from exc


@router.post(
    "/owner-trial-flow/risk-acknowledgement",
    response_model=OwnerRiskAcknowledgement,
)
async def create_owner_trial_flow_risk_acknowledgement(
    body: OwnerRiskAcknowledgementCreateRequest,
    session: OperatorSessionDependency,
) -> OwnerRiskAcknowledgement:
    """Persist Owner strategy-risk acknowledgement metadata only."""
    try:
        return await _owner_trial_flow_service_instance().create_risk_acknowledgement(
            body,
            operator_id=session.username,
        )
    except OwnerTrialFlowInfrastructureError as exc:
        raise _owner_trial_flow_infrastructure_http_error(exc) from exc
    except OwnerTrialFlowError as exc:
        raise _owner_trial_flow_http_error(exc) from exc


@router.post(
    "/owner-trial-flow/authorization-draft",
    response_model=BoundedLiveTrialAuthorizationDraft,
)
async def create_owner_trial_flow_authorization_draft(
    body: BoundedLiveTrialAuthorizationDraftCreateRequest,
    session: OperatorSessionDependency,
) -> BoundedLiveTrialAuthorizationDraft:
    """Persist a pending bounded live-trial authorization draft.

    The draft is non-executable and never grants live readiness, execution
    permission, or order permission.
    """
    try:
        return await _owner_trial_flow_service_instance().create_authorization_draft(
            body,
            operator_id=session.username,
        )
    except OwnerTrialFlowInfrastructureError as exc:
        raise _owner_trial_flow_infrastructure_http_error(exc) from exc
    except OwnerTrialFlowError as exc:
        raise _owner_trial_flow_http_error(exc) from exc


@router.get(
    "/owner-trial-flow/authorization-draft/{draft_id}",
    response_model=BoundedLiveTrialAuthorizationDraft,
)
async def get_owner_trial_flow_authorization_draft(
    draft_id: str,
) -> BoundedLiveTrialAuthorizationDraft:
    """Return a persisted non-executable authorization draft."""
    try:
        return await _owner_trial_flow_service_instance().get_draft(draft_id)
    except OwnerTrialFlowInfrastructureError as exc:
        raise _owner_trial_flow_infrastructure_http_error(exc) from exc
    except OwnerTrialFlowError as exc:
        raise _owner_trial_flow_http_error(exc) from exc


@router.post(
    "/owner-trial-flow/authorization-draft/{draft_id}/activate-live-authorization",
    response_model=BoundedLiveTrialAuthorization,
)
async def activate_owner_trial_flow_live_authorization(
    draft_id: str,
    body: OwnerLiveAuthorizationActivationRequest,
    session: OperatorSessionDependency,
) -> BoundedLiveTrialAuthorization:
    """Persist explicit Owner bounded live authorization metadata only.

    This endpoint records Owner authorization for one bounded live trial scope.
    It never creates an execution intent, creates an order, starts runtime, calls
    exchange APIs, or grants global execution/order permission.
    """
    try:
        return await _owner_trial_flow_service_instance().activate_live_authorization(
            draft_id,
            body,
            operator_id=session.username,
        )
    except OwnerTrialFlowInfrastructureError as exc:
        raise _owner_trial_flow_infrastructure_http_error(exc) from exc
    except OwnerTrialFlowError as exc:
        raise _owner_trial_flow_http_error(exc) from exc


@router.post(
    "/owner-trial-flow/live-execution-bridge/dry-run",
    response_model=BnbLiveExecutionBridgeDryRunResponse,
)
async def dry_run_bnb_live_execution_bridge(
    body: BnbLiveExecutionBridgeDryRunRequest | None = None,
) -> BnbLiveExecutionBridgeDryRunResponse:
    """Dry-run the BNB Owner authorization to execution-boundary bridge.

    This endpoint is read-only with respect to execution: it does not create an
    execution intent, create an order, grant permissions, start runtime, or call
    exchange write APIs.
    """
    profile_readiness = build_bnb_strategy_trial_readiness()
    collector = _strategy_trial_preflight_fact_collector(_api_module())
    fact_snapshot = await collector.collect(profile_readiness.strategy_profile)
    service = BnbLiveExecutionBridgeDryRunService(
        owner_trial_flow_service=_owner_trial_flow_service_instance(),
    )
    return await service.run(body, fact_snapshot=fact_snapshot)


@router.post(
    "/owner-trial-flow/authorizations/{authorization_id}/execute",
    response_model=OwnerBoundedExecutionResponse,
)
async def execute_owner_bounded_live_trial_authorization(
    authorization_id: str,
    session: OperatorSessionDependency,
) -> OwnerBoundedExecutionResponse:
    """Owner-operated generic bounded live-trial execution entrypoint.

    This endpoint is intentionally generic and authorization-driven. It reloads
    the PG authorization, reruns the final hard gate, and then delegates to the
    carrier execution registry. It must fail before ExecutionIntent/order
    creation whenever any readiness blocker remains.
    """
    profile_readiness = build_bnb_strategy_trial_readiness()
    collector = _strategy_trial_preflight_fact_collector(_api_module())
    fact_snapshot = await collector.collect(profile_readiness.strategy_profile)
    owner_trial_service = _owner_trial_flow_service_instance()
    injected_session_maker = getattr(
        getattr(owner_trial_service, "_repository", None),
        "_session_maker",
        None,
    )
    final_gate_service = BnbLiveExecutionBridgeDryRunService(
        owner_trial_flow_service=owner_trial_service,
        session_maker=injected_session_maker,
    )
    api_module = _api_module()
    gateway_binding = await _owner_bounded_exchange_gateway_binding(api_module)
    gateway = gateway_binding.get("gateway")
    protection_planner_service = ProtectionPlannerService(
        repository=PgProtectionPricePlanRepository(injected_session_maker),
        price_source=ExchangeGatewayProtectionPriceSource(
            gateway,
        ),
    )
    execute_service = OwnerBoundedExecutionService(
        final_gate_service=final_gate_service,
        session_maker=injected_session_maker,
        protection_planner_service=protection_planner_service,
        order_executor=ExchangeGatewayBoundedOrderExecutor(
            gateway,
        ),
        intent_repository=PgExecutionIntentRepository(injected_session_maker),
        order_repository=PgOrderRepository(injected_session_maker),
    )
    try:
        return await execute_service.execute_authorization(
            authorization_id,
            operator_id=session.username,
            fact_snapshot=fact_snapshot,
        )
    except OwnerTrialFlowInfrastructureError as exc:
        raise _owner_trial_flow_infrastructure_http_error(exc) from exc
    except OwnerTrialFlowError as exc:
        raise _owner_trial_flow_http_error(exc) from exc
    except OwnerBoundedExecutionError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": exc.code,
                "message": exc.message,
                "blockers": exc.blockers,
                "gateway_binding": gateway_binding.get("status"),
                "gateway_binding_blockers": gateway_binding.get("blockers", []),
                "execution_intent_created": exc.execution_intent_created,
                "order_created": exc.order_created,
                "order_permission_granted": exc.order_permission_granted,
                "execution_intent_id": exc.execution_intent_id,
                "entry_order_id": exc.entry_order_id,
                "entry_exchange_order_id": exc.entry_exchange_order_id,
                "execution_intent_status": exc.execution_intent_status,
                "protection_status": exc.protection_status,
                "tp_order_ids": exc.tp_order_ids,
                "sl_order_id": exc.sl_order_id,
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "owner_bounded_execution_unhandled_exception",
                "message": (
                    "Owner bounded execution stopped with an explicit safe failure; "
                    f"phase requires review: {type(exc).__name__}"
                ),
                "blockers": [
                    "owner_bounded_execution_exception",
                    f"exception_type:{type(exc).__name__}",
                    "manual_review_required_before_retry",
                ],
                "gateway_binding": gateway_binding.get("status"),
                "gateway_binding_blockers": gateway_binding.get("blockers", []),
                "execution_intent_created": False,
                "order_created": False,
                "order_permission_granted": False,
            },
        ) from exc


async def _owner_bounded_exchange_gateway_binding(api_module: Any) -> dict[str, Any]:
    """Return the gateway allowed only for Owner-bounded execution.

    This deliberately does not populate the legacy ``_exchange_gateway`` global.
    Other runtime and controlled-testnet paths therefore do not gain a write
    gateway from the Owner Console deployment.
    """
    existing = getattr(api_module, "_owner_bounded_exchange_gateway", None)
    if existing is not None:
        return _owner_bounded_gateway_status(existing)

    blockers = _owner_bounded_gateway_env_blockers()
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

    gateway = ExchangeGateway(
        exchange_name=exchange_name,
        api_key=api_key,
        api_secret=api_secret,
        testnet=False,
    )
    try:
        await gateway.initialize()
    except Exception as exc:
        close = getattr(gateway, "close", None)
        if callable(close):
            try:
                await close()
            except Exception:
                pass
        return {
            "status": "blocked_gateway_initialization_failed",
            "gateway": None,
            "blockers": [f"exchange_gateway_initialization_failed:{type(exc).__name__}"],
        }

    setattr(api_module, "_owner_bounded_exchange_gateway", gateway)
    return _owner_bounded_gateway_status(gateway)


def _owner_bounded_gateway_status(gateway: Any) -> dict[str, Any]:
    required = ["place_order", "fetch_ticker_price", "get_market_info"]
    missing = [f"gateway_missing_{name}" for name in required if not callable(getattr(gateway, name, None))]
    return {
        "status": "ready" if not missing else "blocked_methods_missing",
        "gateway": gateway if not missing else None,
        "blockers": missing,
        "gateway_type": type(gateway).__name__,
    }


def _owner_bounded_gateway_env_blockers() -> list[str]:
    expected = {
        "TRADING_ENV": "live",
        "EXCHANGE_TESTNET": "false",
        "BRC_EXECUTION_PERMISSION_MAX": "read_only",
        "RUNTIME_CONTROL_API_ENABLED": "false",
        "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED": "false",
    }
    blockers: list[str] = []
    for key, expected_value in expected.items():
        actual = os.environ.get(key, "").strip().lower()
        if actual != expected_value:
            blockers.append(f"{key.lower()}_not_{expected_value}")
    return blockers


async def close_owner_bounded_exchange_gateway() -> None:
    api_module = _api_module()
    gateway = getattr(api_module, "_owner_bounded_exchange_gateway", None)
    if gateway is None:
        return
    close = getattr(gateway, "close", None)
    if callable(close):
        try:
            await close()
        finally:
            setattr(api_module, "_owner_bounded_exchange_gateway", None)
    else:
        setattr(api_module, "_owner_bounded_exchange_gateway", None)


@router.get(
    "/strategy-trial-readiness/v1",
    response_model=StrategyTrialReadinessResponse,
)
async def get_strategy_trial_readiness_v1(
    carrier: Literal["mi001-bnb-long"] = Query(default="mi001-bnb-long"),
) -> StrategyTrialReadinessResponse:
    """Return generic trial-readiness state for a strategy carrier.

    This endpoint is read-only and currently exposes BNB as the first carrier
    instance of the generic readiness model.
    """
    if carrier != "mi001-bnb-long":
        # Literal query validation should make this unreachable, but keep a
        # fail-closed branch to avoid accidental carrier expansion.
        raise HTTPException(status_code=400, detail="unsupported strategy trial readiness carrier")
    observation_case = None
    try:
        if await probe_pg_connectivity():
            observation_repo = PgStrategyGroupObservationRepository()
            forward_review_repo = PgStrategyGroupForwardReviewRepository()
            observations = await observation_repo.list_recent(limit=200)
            would_enter_ids = [
                record.record_id
                for record in observations
                if record.signal_type == "would_enter"
            ]
            reviews = await forward_review_repo.list_by_observation_ids(would_enter_ids)
            queue = build_observation_case_queue(
                observations,
                reviews,
                candidate_id="MI-001-BNB-LONG",
            )
            observation_case = queue.cases[0] if queue.cases else None
    except Exception:
        observation_case = None
    profile_readiness = build_bnb_strategy_trial_readiness(observation_case=observation_case)
    collector = _strategy_trial_preflight_fact_collector(_api_module())
    fact_snapshot = await collector.collect(profile_readiness.strategy_profile)
    return build_bnb_strategy_trial_readiness(
        observation_case=observation_case,
        preflight_input=fact_snapshot.to_preflight_input(
            requested_mode=profile_readiness.strategy_profile.execution_mode,
        ),
        fact_checks=fact_snapshot.to_response_dict(),
    )


def _owner_trial_flow_service_instance() -> OwnerTrialFlowService:
    global _owner_trial_flow_service
    if _owner_trial_flow_service is None:
        _owner_trial_flow_service = OwnerTrialFlowService(
            PgOwnerTrialFlowRepository(),
        )
    return _owner_trial_flow_service


def _multi_carrier_budget_authorization_service_instance() -> MultiCarrierBudgetAuthorizationService:
    global _multi_carrier_budget_authorization_service
    if _multi_carrier_budget_authorization_service is None:
        _multi_carrier_budget_authorization_service = MultiCarrierBudgetAuthorizationService(
            PgMultiCarrierBudgetAuthorizationRepository(),
        )
    return _multi_carrier_budget_authorization_service


def _owner_trial_flow_http_error(exc: OwnerTrialFlowError) -> HTTPException:
    status = 404 if exc.code == "draft_not_found" else 400
    return HTTPException(
        status_code=status,
        detail={"code": exc.code, "message": exc.message},
    )


def _owner_trial_flow_infrastructure_http_error(exc: OwnerTrialFlowInfrastructureError) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={"code": exc.code, "message": exc.message},
    )


def _multi_carrier_budget_authorization_http_error(
    exc: MultiCarrierBudgetAuthorizationError,
) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={"code": exc.code, "message": exc.message},
    )


def _multi_carrier_budget_authorization_infrastructure_http_error(
    exc: MultiCarrierBudgetAuthorizationInfrastructureError,
) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={"code": exc.code, "message": exc.message},
    )


def _strategy_trial_preflight_fact_collector(api_module: Any) -> TrialPreflightFactCollector:
    bnb_live_facts = _BnbFinalGateLiveReadOnlyFacts(api_module)
    return TrialPreflightFactCollector(
        position_reader=_bnb_preflight_position_reader(api_module, bnb_live_facts),
        open_order_reader=_bnb_preflight_open_order_reader(api_module, bnb_live_facts),
        gks_reader=_bnb_preflight_gks_reader(api_module),
        startup_guard_reader=_bnb_preflight_startup_guard_reader(api_module),
        reconciliation_reader=_bnb_preflight_reconciliation_reader(api_module, bnb_live_facts),
        account_facts_reader=_bnb_preflight_account_facts_reader(api_module, bnb_live_facts),
    )


def _bnb_preflight_position_reader(api_module: Any, bnb_live_facts: Any):
    async def _read(profile):
        facts = await bnb_live_facts.read(profile)
        if facts.get("available") is True:
            return list(facts.get("positions") or [])
        raise RuntimeError(str(facts.get("reason") or "bnb_live_position_read_unavailable"))

    return _read


def _bnb_preflight_open_order_reader(api_module: Any, bnb_live_facts: Any):
    async def _read(profile):
        facts = await bnb_live_facts.read(profile)
        if facts.get("available") is True:
            return list(facts.get("open_orders") or [])
        raise RuntimeError(str(facts.get("reason") or "bnb_live_open_order_read_unavailable"))

    return _read


def _bnb_preflight_gks_reader(api_module: Any):
    async def _read(profile):
        service = getattr(api_module, "_global_kill_switch_service", None)
        if service is not None and hasattr(service, "get_state"):
            return await _with_bnb_scoped_gks_clearance(profile, service.get_state())
        if service is not None and hasattr(service, "is_active"):
            return await _with_bnb_scoped_gks_clearance(profile, {
                "active": bool(service.is_active()),
                "source": "runtime_global_kill_switch_service",
            })
        if await probe_pg_connectivity():
            repo = PgGlobalKillSwitchRepository()
            try:
                state = await repo.get_state()
            except Exception as exc:
                return {
                    "state": "unavailable",
                    "status": "unavailable",
                    "source": "pg_global_kill_switch_repository",
                    "reason": f"global_kill_switch_pg_read_failed:{type(exc).__name__}",
                }
            if state is None:
                return {
                    "state": "unavailable",
                    "status": "unavailable",
                    "source": "pg_global_kill_switch_repository",
                    "reason": "global_kill_switch_pg_state_missing",
                }
            return await _with_bnb_scoped_gks_clearance(profile, state)
        return {
            "state": "unavailable",
            "status": "unavailable",
            "source": "pg_global_kill_switch_repository",
            "reason": "pg_connectivity_unavailable",
        }

    return _read


def _bnb_preflight_startup_guard_reader(api_module: Any):
    service = getattr(api_module, "_startup_trading_guard_service", None)
    if service is None or not (hasattr(service, "get_state") or hasattr(service, "is_armed")):
        async def _runtime_not_started(profile):
            try:
                scoped_arm = await _read_active_bnb_scoped_runtime_safety_clearance(
                    "startup_guard",
                    profile,
                )
            except Exception:
                scoped_arm = None
            if scoped_arm is not None:
                return {
                    "armed": True,
                    "runtime_started": False,
                    "runtime_safety_context_bound": True,
                    "runtime_state": "scoped_safety_context_bound",
                    "source": "pg_scoped_startup_guard_arm",
                    "reason": scoped_arm.get("reason"),
                    "scoped_arm_valid": True,
                    "authorization_id": scoped_arm.get("authorization_id"),
                    "clearance_id": scoped_arm.get("clearance_id"),
                    "expires_at_ms": scoped_arm.get("expires_at_ms"),
                    "scope_match": True,
                    "updated_at_ms": scoped_arm.get("updated_at_ms"),
                }
            return {
                "armed": False,
                "runtime_started": False,
                "runtime_state": "not_started",
                "source": "console_api_runtime_context_absent",
                "reason": "startup_guard_runtime_not_started",
            }

        return _runtime_not_started

    async def _read(_profile):
        if hasattr(service, "get_state"):
            return service.get_state()
        return {
            "armed": bool(service.is_armed()),
            "source": "runtime_startup_trading_guard_service",
        }

    return _read


async def _with_bnb_scoped_gks_clearance(profile: Any, state: Any) -> Any:
    active = _value_from_state(state, "active")
    if active is not True:
        return state
    try:
        scoped_clearance = await _read_active_bnb_scoped_runtime_safety_clearance("gks", profile)
    except Exception:
        scoped_clearance = None
    if scoped_clearance is None:
        return state
    return {
        "active": False,
        "global_active": True,
        "source": "pg_scoped_gks_clearance",
        "reason": scoped_clearance.get("reason"),
        "scoped_clearance_valid": True,
        "authorization_id": scoped_clearance.get("authorization_id"),
        "clearance_id": scoped_clearance.get("clearance_id"),
        "expires_at_ms": scoped_clearance.get("expires_at_ms"),
        "scope_match": True,
        "updated_at_ms": scoped_clearance.get("updated_at_ms"),
    }


def _value_from_state(state: Any, key: str) -> Any:
    if isinstance(state, dict):
        return state.get(key)
    return getattr(state, key, None)


async def _read_active_bnb_scoped_runtime_safety_clearance(
    clearance_type: str,
    profile: Any,
) -> dict[str, Any] | None:
    if clearance_type not in {"gks", "startup_guard"}:
        return None
    carrier = build_bnb_strategy_trial_architecture_governance().owner_review_packet.carrier
    if str(getattr(profile, "candidate_id", "")) != carrier.carrier_id:
        return None
    if str(getattr(profile, "side", "")) != carrier.side:
        return None
    if str(getattr(profile, "symbol", "")) not in {carrier.symbol, carrier.runtime_symbol}:
        return None
    session_maker = get_pg_session_maker()
    async with session_maker() as session:
        if not await _pg_table_exists(session, "brc_scoped_runtime_safety_clearances"):
            return None
        now_ms = int(time.time() * 1000)
        result = await session.execute(
            text(
                """
                SELECT
                    c.clearance_id,
                    c.clearance_type,
                    c.authorization_id,
                    c.carrier_id,
                    c.symbol,
                    c.side,
                    c.max_notional,
                    c.quantity,
                    c.leverage,
                    c.protection_plan_type,
                    c.expires_at_ms,
                    c.actor,
                    c.source,
                    c.reason,
                    c.created_at_ms,
                    c.updated_at_ms
                FROM brc_scoped_runtime_safety_clearances c
                JOIN brc_bounded_live_trial_authorizations a
                  ON a.authorization_id = c.authorization_id
                WHERE c.clearance_type = :clearance_type
                  AND c.status = 'active'
                  AND c.expires_at_ms > :now_ms
                  AND a.carrier_id = :carrier_id
                  AND a.symbol IN (:symbol, :runtime_symbol)
                  AND a.side = :side
                  AND a.max_notional = :max_notional
                  AND a.quantity = :quantity
                  AND a.leverage = :leverage
                  AND a.protection_plan_type = :protection_plan_type
                  AND a.single_use = :true_value
                  AND a.consumed = :false_value
                  AND a.live_authorized = :true_value
                  AND a.live_ready = :false_value
                  AND a.order_permission_granted = :false_value
                  AND a.execution_permission_granted = :false_value
                  AND a.execution_intent_created = :false_value
                  AND a.order_created = :false_value
                  AND a.auto_execution_enabled = :false_value
                  AND c.carrier_id = a.carrier_id
                  AND c.symbol = a.symbol
                  AND c.side = a.side
                  AND c.max_notional = a.max_notional
                  AND c.quantity = a.quantity
                  AND c.leverage = a.leverage
                  AND c.protection_plan_type = a.protection_plan_type
                ORDER BY c.created_at_ms DESC
                LIMIT 1
                """
            ),
            {
                "clearance_type": clearance_type,
                "now_ms": now_ms,
                "carrier_id": carrier.carrier_id,
                "symbol": carrier.symbol,
                "runtime_symbol": carrier.runtime_symbol,
                "side": carrier.side,
                "max_notional": carrier.max_notional,
                "quantity": carrier.quantity,
                "leverage": carrier.leverage,
                "protection_plan_type": carrier.protection_plan_type,
                "true_value": True,
                "false_value": False,
            },
        )
        row = result.mappings().first()
        return dict(row) if row is not None else None


async def _pg_table_exists(session: Any, table_name: str) -> bool:
    bind = session.get_bind()
    dialect_name = bind.dialect.name if bind is not None else ""
    if dialect_name == "sqlite":
        exists = await session.scalar(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name = :table_name"),
            {"table_name": table_name},
        )
        return exists is not None
    exists = await session.scalar(
        text("SELECT to_regclass(:table_name)"),
        {"table_name": f"public.{table_name}"},
    )
    return exists is not None


def _bnb_preflight_reconciliation_reader(api_module: Any, bnb_live_facts: Any):
    summary = getattr(api_module, "_startup_reconciliation_summary", None)
    if summary is None:
        async def _read_final_gate_reconciliation(profile):
            facts = await bnb_live_facts.read(profile)
            if facts.get("available") is not True:
                return {
                    "status": "unavailable",
                    "source": "bnb_final_gate_read_only_reconciliation",
                    "reason": str(facts.get("reason") or "bnb_live_facts_unavailable"),
                }
            try:
                pg_counts = await _bnb_final_gate_pg_reconciliation_counts(str(profile.symbol))
            except Exception as exc:  # pragma: no cover - defensive PG read path
                return {
                    "status": "unavailable",
                    "source": "bnb_final_gate_read_only_reconciliation",
                    "reason": f"pg_reconciliation_read_failed:{type(exc).__name__}",
                }
            exchange_position_count = len(list(facts.get("positions") or []))
            exchange_open_order_count = len(list(facts.get("open_orders") or []))
            blocking_execution_intents = int(
                pg_counts.get("blocking_execution_intents", pg_counts["execution_intents"]) or 0
            )
            retryable_failed_intents = int(pg_counts.get("retryable_failed_execution_intents", 0) or 0)
            mismatch_count = sum(
                1
                for value in [
                    blocking_execution_intents,
                    pg_counts["orders"],
                    pg_counts["pg_bnb_active_positions"],
                    pg_counts["pg_bnb_open_orders"],
                    exchange_position_count,
                    exchange_open_order_count,
                ]
                if int(value or 0) != 0
            )
            reconciliation_status = "clean" if mismatch_count == 0 else "mismatch"
            if reconciliation_status == "clean" and retryable_failed_intents > 0:
                reconciliation_status = "clean_for_retry"
            return {
                "status": reconciliation_status,
                "source": "bnb_final_gate_read_only_reconciliation",
                "failed_reconciliations_count": mismatch_count,
                "pg_execution_intents_count": pg_counts["execution_intents"],
                "pg_blocking_execution_intents_count": blocking_execution_intents,
                "pg_closed_execution_intents_count": pg_counts.get(
                    "closed_execution_intents",
                    0,
                ),
                "retryable_failed_execution_intents_count": retryable_failed_intents,
                "retry_classification": pg_counts.get("retry_classification"),
                "pg_orders_count": pg_counts["orders"],
                "pg_historical_closed_orders_count": pg_counts.get(
                    "historical_closed_orders",
                    0,
                ),
                "pg_bnb_active_position_count": pg_counts["pg_bnb_active_positions"],
                "pg_bnb_open_order_count": pg_counts["pg_bnb_open_orders"],
                "exchange_bnb_active_position_count": exchange_position_count,
                "exchange_bnb_open_order_count": exchange_open_order_count,
                "read_only": True,
            }

        return _read_final_gate_reconciliation

    async def _read(_profile):
        return summary

    return _read


def _bnb_preflight_account_facts_reader(api_module: Any, bnb_live_facts: Any):
    async def _read(_profile):
        facts = await bnb_live_facts.read(_profile)
        account = dict(facts.get("account_facts") or {})
        return {
            "source": account.get("source_id") or facts.get("source") or "unavailable",
            "account_equity_source": account.get("source_id") or facts.get("source") or "unavailable",
            "truth_level": facts.get("truth_level") or "unavailable",
            "timestamp_ms": account.get("timestamp_ms"),
            "freshness": account.get("freshness_status") or "unavailable",
            "account_equity_freshness": account.get("freshness_status") or "unavailable",
            "account_equity_available": account.get("account_equity") is not None,
            "wallet_equity_available": account.get("account_equity") is not None,
            "available_margin_available": account.get("available_margin") is not None,
            "account_equity": account.get("account_equity") or "not_available",
            "wallet_equity": account.get("account_equity") or "not_available",
            "available_margin": account.get("available_margin") or "not_available",
            "read_method": facts.get("read_method") or "none",
            "read_only_guarantee": True,
            "external_call_performed": bool(account.get("external_call_performed")),
            "real_account_api_called_by_endpoint": bool(account.get("external_call_performed")),
            "reconciliation_status": account.get("reconciliation_status") or "unknown",
        }

    return _read


class _BnbFinalGateLiveReadOnlyFacts:
    """BNB final-gate facts from live read-only exchange calls.

    This class is deliberately scoped to the Owner-authorized BNB final gate. It
    exposes no order, cancel, runtime, permission, or execution methods.
    """

    def __init__(self, api_module: Any) -> None:
        self._api_module = api_module
        self._cache: dict[str, Any] | None = None

    async def read(self, profile: Any) -> dict[str, Any]:
        if self._cache is not None:
            return self._cache
        self._cache = await self._read(profile)
        return self._cache

    async def _read(self, profile: Any) -> dict[str, Any]:
        generated_at_ms = int(time.time() * 1000)
        env_status = _bnb_final_gate_live_read_env_status()
        if env_status["safe"] is not True:
            return _bnb_live_read_unavailable(
                generated_at_ms=generated_at_ms,
                reason="live_read_only_env_not_safe",
                env_status=env_status,
            )

        client_info = _bnb_final_gate_read_only_client(self._api_module)
        client = client_info.get("client")
        if client is None:
            return _bnb_live_read_unavailable(
                generated_at_ms=generated_at_ms,
                reason=str(client_info.get("reason") or "live_read_only_client_unavailable"),
                env_status=env_status,
            )

        should_close = bool(client_info.get("close_after_read"))
        errors: list[str] = []
        positions: list[dict[str, Any]] = []
        open_orders: list[dict[str, Any]] = []
        try:
            account_source = BinanceUsdtFuturesAccountFactsSource(
                balance_client=client,
                source_id="binance_usdt_futures_live_read_only_final_gate",
                account_id="configured_bnb_final_gate_account",
            )
            account_facts = await account_source.read_trial_readiness_account_facts(
                candidate_id=str(getattr(profile, "candidate_id", "MI-001-BNB-LONG")),
                symbol=str(getattr(profile, "symbol", "BNB/USDT:USDT")),
                side=str(getattr(profile, "side", "long")),
                generated_at_ms=generated_at_ms,
            )
            try:
                fetched_positions = await _call_fetch_positions(client, str(profile.symbol))
                positions = [
                    _dump_jsonable(item)
                    for item in fetched_positions
                    if _position_nonzero(item)
                ]
            except Exception as exc:  # pragma: no cover - defensive live read path
                errors.append(f"BNB live position read failed: {type(exc).__name__}")
            open_orders = await _safe_fetch_exchange_orders(
                client,
                str(profile.symbol),
                errors=errors,
            )
            account_payload = account_facts.model_dump(mode="json")
            available = account_facts.is_ready and not errors
            return {
                "available": available,
                "reason": (
                    "bnb_live_read_only_facts_available"
                    if available
                    else "bnb_live_read_only_facts_partially_unavailable"
                ),
                "source": str(client_info.get("source") or "live_read_only_client"),
                "truth_level": "exchange_read" if available else "unavailable",
                "read_method": "ccxt_read_only_fetch_balance_positions_open_orders",
                "generated_at_ms": generated_at_ms,
                "account_facts": account_payload,
                "positions": positions,
                "open_orders": open_orders,
                "errors": errors,
                "env_status": env_status,
            }
        finally:
            if should_close and hasattr(client, "close"):
                await client.close()


class _GatewayBnbReadOnlyClient:
    def __init__(self, gateway: Any) -> None:
        self._gateway = gateway

    async def fetch_balance(self, params: Optional[dict[str, Any]] = None) -> Any:
        rest_exchange = getattr(self._gateway, "rest_exchange", None)
        if rest_exchange is None or not hasattr(rest_exchange, "fetch_balance"):
            raise RuntimeError("gateway_balance_reader_unavailable")
        return await rest_exchange.fetch_balance(params or {"type": "future"})

    async def fetch_positions(self, symbol: Optional[str] = None) -> list[Any]:
        if not hasattr(self._gateway, "fetch_positions"):
            raise RuntimeError("gateway_position_reader_unavailable")
        try:
            return list(await self._gateway.fetch_positions(symbol=symbol))
        except TypeError:
            return list(await self._gateway.fetch_positions(symbol))

    async def fetch_open_orders(
        self,
        symbol: str,
        params: Optional[dict[str, Any]] = None,
    ) -> list[Any]:
        if not hasattr(self._gateway, "fetch_open_orders"):
            raise RuntimeError("gateway_open_order_reader_unavailable")
        try:
            return list(await self._gateway.fetch_open_orders(symbol, params=params or {}))
        except TypeError:
            return list(await self._gateway.fetch_open_orders(symbol=symbol, params=params or {}))

    async def close(self) -> None:
        return None


class _CcxtBnbFinalGateReadOnlyClient:
    def __init__(
        self,
        *,
        exchange_name: str,
        api_key: str,
        api_secret: str,
        testnet: bool,
    ) -> None:
        import ccxt.async_support as ccxt_async

        exchange_class = getattr(ccxt_async, exchange_name)
        self._exchange = exchange_class(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "enableRateLimit": True,
                "timeout": 30000,
                "options": {
                    "defaultType": "future",
                    "adjustForTimeDifference": True,
                    "recvWindow": 30000,
                    "warnOnFetchOpenOrdersWithoutSymbol": False,
                },
            }
        )
        if testnet:
            self._exchange.enable_demo_trading(True)

    async def fetch_balance(self, params: Optional[dict[str, Any]] = None) -> Any:
        return await self._exchange.fetch_balance(params or {"type": "future"})

    async def fetch_positions(self, symbol: Optional[str] = None) -> list[Any]:
        if symbol:
            try:
                return list(await self._exchange.fetch_positions([symbol]))
            except TypeError:
                return list(await self._exchange.fetch_positions(symbol))
        return list(await self._exchange.fetch_positions())

    async def fetch_open_orders(
        self,
        symbol: str,
        params: Optional[dict[str, Any]] = None,
    ) -> list[Any]:
        return list(await self._exchange.fetch_open_orders(symbol, params=params or {}))

    async def close(self) -> None:
        await self._exchange.close()


def _bnb_final_gate_read_only_client(api_module: Any) -> dict[str, Any]:
    gateway = getattr(api_module, "_exchange_gateway", None)
    if gateway is not None:
        return {
            "client": _GatewayBnbReadOnlyClient(gateway),
            "source": "bound_exchange_gateway_read_only_methods",
            "close_after_read": False,
        }
    api_key = os.environ.get("EXCHANGE_API_KEY", "").strip()
    api_secret = os.environ.get("EXCHANGE_API_SECRET", "").strip()
    if not api_key or not api_secret:
        return {
            "client": None,
            "reason": "exchange_credentials_not_present_in_api_process",
        }
    exchange_name = os.environ.get("EXCHANGE_NAME", "binance").strip() or "binance"
    if exchange_name != "binance":
        return {
            "client": None,
            "reason": "unsupported_exchange_for_bnb_final_gate_read_only",
        }
    return {
        "client": _CcxtBnbFinalGateReadOnlyClient(
            exchange_name=exchange_name,
            api_key=api_key,
            api_secret=api_secret,
            testnet=False,
        ),
        "source": "ccxt_binance_usdt_futures_read_only_client",
        "close_after_read": True,
    }


def _bnb_final_gate_live_read_env_status() -> dict[str, Any]:
    trading_env = os.environ.get("TRADING_ENV", "").strip().lower()
    exchange_testnet = os.environ.get("EXCHANGE_TESTNET", "").strip().lower()
    permission_max = os.environ.get("BRC_EXECUTION_PERMISSION_MAX", "read_only").strip().lower()
    runtime_control = os.environ.get("RUNTIME_CONTROL_API_ENABLED", "false").strip().lower()
    test_injection = os.environ.get("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "false").strip().lower()
    safe = (
        trading_env == "live"
        and exchange_testnet == "false"
        and permission_max == "read_only"
        and runtime_control not in {"1", "true", "yes", "on"}
        and test_injection not in {"1", "true", "yes", "on"}
    )
    return {
        "safe": safe,
        "trading_env_live": trading_env == "live",
        "exchange_testnet_false": exchange_testnet == "false",
        "permission_read_only": permission_max == "read_only",
        "runtime_control_disabled": runtime_control not in {"1", "true", "yes", "on"},
        "test_signal_injection_disabled": test_injection not in {"1", "true", "yes", "on"},
    }


def _bnb_live_read_unavailable(
    *,
    generated_at_ms: int,
    reason: str,
    env_status: dict[str, Any],
) -> dict[str, Any]:
    return {
        "available": False,
        "reason": reason,
        "source": "unavailable",
        "truth_level": "unavailable",
        "read_method": "none",
        "generated_at_ms": generated_at_ms,
        "account_facts": {
            "source_id": "unavailable",
            "source_type": "unavailable",
            "account_equity": None,
            "available_margin": None,
            "timestamp_ms": generated_at_ms,
            "freshness_status": "unavailable",
            "reconciliation_status": "unknown",
            "read_only_guarantee": True,
            "external_call_performed": False,
        },
        "positions": [],
        "open_orders": [],
        "errors": [reason],
        "env_status": env_status,
    }


async def _call_fetch_positions(client: Any, symbol: str) -> list[Any]:
    try:
        return list(await client.fetch_positions(symbol=symbol))
    except TypeError:
        return list(await client.fetch_positions(symbol))


async def _bnb_final_gate_pg_reconciliation_counts(symbol: str) -> dict[str, int]:
    session_maker = get_pg_session_maker()
    async with session_maker() as session:
        required_tables = [
            "execution_intents",
            "orders",
            "positions",
        ]
        existing: dict[str, bool] = {}
        for table_name in required_tables:
            exists = await session.scalar(
                text("SELECT to_regclass(:table_name)"),
                {"table_name": f"public.{table_name}"},
            )
            existing[table_name] = exists is not None
        missing = [table_name for table_name, present in existing.items() if not present]
        if missing:
            raise RuntimeError(f"pg_reconciliation_tables_missing:{','.join(missing)}")
        intent_rows = (
            await session.execute(
                text(
                    """
                    SELECT
                        i.id,
                        i.signal_id,
                        i.symbol,
                        i.status,
                        i.order_id,
                        i.exchange_order_id,
                        i.failed_reason,
                        i.authorization_id,
                        a.consumed AS authorization_consumed,
                        a.metadata AS authorization_metadata
                    FROM execution_intents i
                    LEFT JOIN brc_bounded_live_trial_authorizations a
                      ON a.authorization_id = i.authorization_id
                    """
                )
            )
        ).mappings().all()
        execution_intents = len(intent_rows)
        retryable_failed_execution_intents = 0
        blocking_execution_intents = 0
        closed_execution_intents = 0
        retry_classification = "no_previous_intent"
        for row in intent_rows:
            local_order_count = await session.scalar(
                text("SELECT count(*) FROM orders WHERE signal_id = :signal_id"),
                {"signal_id": row["signal_id"]},
            )
            if _is_closed_owner_trial_intent_row(row):
                closed_execution_intents += 1
                retry_classification = "closed_owner_trial_intent_present"
                continue
            classification = _classify_retryable_pre_order_intent_row(
                row,
                local_order_count=int(local_order_count or 0),
            )
            if classification["retry_allowed"]:
                retryable_failed_execution_intents += 1
                retry_classification = "retryable_failed_intent_present"
            else:
                blocking_execution_intents += 1
                retry_classification = str(classification["reason"])
        order_rows = (
            await session.execute(
                text(
                    """
                    SELECT status
                    FROM orders
                    WHERE symbol = :symbol
                    """
                ),
                {"symbol": symbol},
            )
        ).mappings().all()
        blocking_orders = sum(
            1 for row in order_rows if _is_blocking_pg_order_status(row.get("status"))
        )
        historical_closed_orders = len(order_rows) - blocking_orders
        pg_bnb_active_positions = await session.scalar(
            text(
                """
                SELECT count(*)
                FROM positions
                WHERE symbol = :symbol
                  AND CAST(is_closed AS text) IN ('false', '0', 'f')
                """
            ),
            {"symbol": symbol},
        )
        pg_bnb_open_orders = await session.scalar(
            text(
                """
                SELECT count(*)
                FROM orders
                WHERE symbol = :symbol
                  AND status IN ('OPEN', 'PARTIALLY_FILLED')
                """
            ),
            {"symbol": symbol},
        )
    return {
        "execution_intents": int(execution_intents or 0),
        "retryable_failed_execution_intents": retryable_failed_execution_intents,
        "blocking_execution_intents": blocking_execution_intents,
        "closed_execution_intents": closed_execution_intents,
        "retry_classification": retry_classification,
        "orders": int(blocking_orders or 0),
        "historical_closed_orders": int(historical_closed_orders or 0),
        "pg_bnb_active_positions": int(pg_bnb_active_positions or 0),
        "pg_bnb_open_orders": int(pg_bnb_open_orders or 0),
    }


def _is_closed_owner_trial_intent_row(row: Any) -> bool:
    metadata = row.get("authorization_metadata") or {}
    if not isinstance(metadata, dict):
        return False
    if row.get("authorization_consumed") is not True:
        return False
    if metadata.get("next_trade_requires_new_owner_authorization") is not True:
        return False
    if metadata.get("trial_final_state") not in {
        "completed_with_recovery_flat",
        "completed_protected",
        "completed_flat",
    }:
        return False
    return True


def _is_blocking_pg_order_status(status: Any) -> bool:
    return str(status or "").upper() in {
        "CREATED",
        "SUBMITTED",
        "PENDING",
        "OPEN",
        "PARTIALLY_FILLED",
    }


def _classify_retryable_pre_order_intent_row(row: Any, *, local_order_count: int) -> dict[str, Any]:
    status = str(row["status"]).lower()
    if status not in {"failed", "rejected"}:
        return {"retry_allowed": False, "reason": f"previous_intent_status_not_retryable:{status}"}
    if row.get("order_id"):
        return {"retry_allowed": False, "reason": "previous_intent_has_order_id"}
    if row.get("exchange_order_id"):
        return {"retry_allowed": False, "reason": "previous_intent_has_exchange_order_id"}
    if local_order_count > 0:
        return {"retry_allowed": False, "reason": "previous_intent_has_local_order"}
    failed_reason = str(row.get("failed_reason") or "").lower()
    if not any(
        marker in failed_reason
        for marker in [
            "pre_order",
            "before_order",
            "before order",
            "position_side_mismatch",
            "position side mismatch",
        ]
    ):
        return {"retry_allowed": False, "reason": "previous_intent_failure_phase_ambiguous"}
    return {
        "retry_allowed": True,
        "reason": "retryable_pre_order_failure",
        "failure_phase": "pre_order_rejected",
        "previous_intent_id": row.get("id"),
    }


async def _strategy_group_live_readonly_observation_response(
    *,
    record_observation: bool,
    source_name: Literal["local_sqlite_fallback", "live_market"] = "local_sqlite_fallback",
) -> StrategyGroupLiveReadOnlyObservationResponse:
    try:
        source = _observation_market_source(source_name)
        preview = build_strategy_group_live_readonly_observation_v1(market_source=source)
        repo = PgStrategyGroupObservationRepository()
        pg_available = await probe_pg_connectivity()
        if not pg_available:
            raise RuntimeError("PG observation repository unavailable")
        if record_observation:
            recorded = [await repo.record(record) for record in preview.current_signals]
            current = recorded
        else:
            candidate_ids = [candidate.candidate_id for candidate in preview.candidates]
            current = await repo.list_current_by_candidate(candidate_ids=candidate_ids)
            if not current:
                current = preview.current_signals
        history = await repo.list_recent(limit=50)
        review_repo = PgStrategyGroupForwardReviewRepository()
        reviews = await review_repo.list_by_observation_ids(
            [record.record_id for record in current + history]
        )
        return _with_pg_observation_payload(
            preview,
            current_signals=current,
            signal_history=history,
            forward_reviews=reviews,
            record_observation=record_observation,
        )
    except Exception as exc:
        fallback_source = LocalSqliteObservationMarketSource()
        preview = build_strategy_group_live_readonly_observation_v1(market_source=fallback_source)
        sink_summary = dict(preview.sink_summary)
        sink_summary.update(
            {
                "sink_id": "pg_brc_strategy_group_observations",
                "sink_status": "blocked_pg_observation_unavailable",
                "pg_observation_sink": "unavailable",
                "pg_error": f"{type(exc).__name__}: {str(exc)[:240]}",
                "fallback_sink_id": "process_local_in_memory_strategy_group_observation_sink",
            }
        )
        input_source_summary = dict(preview.input_source_summary)
        input_source_summary["source_type"] = "local_sqlite_fallback"
        input_source_summary["fallback_used"] = True
        input_source_summary["requested_source"] = source_name
        input_source_summary["source_error"] = f"{type(exc).__name__}: {str(exc)[:240]}"
        return preview.model_copy(
            update={
                "sink_summary": sink_summary,
                "input_source_summary": input_source_summary,
            }
        )


def _observation_market_source(
    source_name: Literal["local_sqlite_fallback", "live_market"],
):
    if source_name == "live_market":
        return BinancePublicKlineMarketSource()
    return LocalSqliteObservationMarketSource()


def _with_pg_observation_payload(
    response: StrategyGroupLiveReadOnlyObservationResponse,
    *,
    current_signals: list,
    signal_history: list,
    forward_reviews: list | None = None,
    record_observation: bool,
) -> StrategyGroupLiveReadOnlyObservationResponse:
    sink_summary = dict(response.sink_summary)
    sink_summary.update(
        {
            "sink_id": "pg_brc_strategy_group_observations",
            "sink_status": "recorded_pg" if record_observation else "read_pg_history",
            "pg_observation_sink": "brc_strategy_group_observations",
            "record_count": len(signal_history),
            "writes_execution_or_order_tables": False,
            "runtime_effect": "none",
        }
    )
    observation_chain_summary = dict(response.observation_chain_summary)
    observation_chain_summary.update(
        {
            "signal_history_available": bool(signal_history),
            "main_blocker": "true_live_market_source_missing"
            if response.input_source_summary.get("source_id") == "local_sqlite_v3_dev_closed_klines_read_only"
            else "none_for_pg_observation_sink",
        }
    )
    input_source_summary = dict(response.input_source_summary)
    reviews = forward_reviews or []
    review_summary = {
        "sink_id": "pg_brc_strategy_group_forward_reviews",
        "review_count": len(reviews),
        "by_observation_id": {},
        "writes_execution_or_order_tables": False,
        "runtime_effect": "none",
    }
    for review in reviews:
        review_summary["by_observation_id"].setdefault(review.observation_id, []).append(
            review.model_dump(mode="json")
        )
    return response.model_copy(
        update={
            "current_signals": current_signals,
            "signal_history": signal_history,
            "forward_review_summary": review_summary,
            "sink_summary": sink_summary,
            "input_source_summary": input_source_summary,
            "observation_chain_summary": observation_chain_summary,
        }
    )


@router.post(
    "/readiness/startup-guard/preflight-arm",
    response_model=StartupGuardReadinessArmResponse,
)
async def arm_startup_guard_readiness(
    body: StartupGuardReadinessArmRequest,
) -> StartupGuardReadinessArmResponse:
    """Arm only the runtime-owned startup guard for readiness preflight.

    This is not trial start and does not touch execution/order/exchange-write
    paths. It fails closed unless a runtime-owned guard object already exists.
    """
    api_module = _api_module()
    runtime_bound = api_module.get_runtime_context() is not None
    control_enabled = _env_enabled("RUNTIME_CONTROL_API_ENABLED")
    guard = getattr(api_module, "_startup_trading_guard_service", None)
    armed_before = _startup_guard_armed_state(guard)

    base_notes = [
        "readiness_action_only",
        "does_not_start_trial",
        "does_not_create_execution_intent",
        "does_not_create_order",
        "does_not_grant_execution_permission",
        "does_not_call_exchange_write_methods",
    ]

    if not runtime_bound or guard is None:
        return StartupGuardReadinessArmResponse(
            status="blocked",
            armed_before=armed_before,
            armed_after=armed_before,
            runtime_bound=runtime_bound,
            runtime_control_api_enabled=control_enabled,
            runtime_effect="none",
            next_checklist_verdict="blocked_runtime_start_required",
            notes=[
                *base_notes,
                "runtime_owned_startup_guard_unavailable",
                "no_runtime_started_by_this_endpoint",
            ],
        )

    if not control_enabled:
        return StartupGuardReadinessArmResponse(
            status="blocked",
            armed_before=armed_before,
            armed_after=armed_before,
            runtime_bound=runtime_bound,
            runtime_control_api_enabled=False,
            runtime_effect="none",
            next_checklist_verdict="blocked_startup_guard_runtime_coupled",
            notes=[
                *base_notes,
                "runtime_control_api_disabled",
                "set_RUNTIME_CONTROL_API_ENABLED_true_for_local_owner_control",
            ],
        )

    if armed_before is True:
        return StartupGuardReadinessArmResponse(
            status="already_armed",
            armed_before=True,
            armed_after=True,
            runtime_bound=True,
            runtime_control_api_enabled=True,
            runtime_effect="none",
            next_checklist_verdict="ready_for_trial_start_after_owner_approval",
            notes=[*base_notes, "startup_guard_already_armed"],
        )

    manual_arm = getattr(guard, "manual_arm", None)
    if not callable(manual_arm):
        return StartupGuardReadinessArmResponse(
            status="blocked",
            armed_before=armed_before,
            armed_after=armed_before,
            runtime_bound=True,
            runtime_control_api_enabled=True,
            runtime_effect="none",
            next_checklist_verdict="blocked_boundary_risk",
            notes=[*base_notes, "startup_guard_manual_arm_unavailable"],
        )

    manual_arm(reason=body.reason, updated_by=body.updated_by)
    armed_after = _startup_guard_armed_state(guard)
    return StartupGuardReadinessArmResponse(
        status="armed" if armed_after is True else "blocked",
        armed_before=armed_before,
        armed_after=armed_after,
        runtime_bound=True,
        runtime_control_api_enabled=True,
        runtime_effect="startup_guard_process_state_only" if armed_after is True else "none",
        next_checklist_verdict=(
            "ready_for_trial_start_after_owner_approval"
            if armed_after is True
            else "blocked_startup_guard_runtime_coupled"
        ),
        notes=[
            *base_notes,
            "armed_actual_runtime_owned_startup_guard",
            "checklist_must_be_regenerated_from_runtime_safety_state",
        ],
    )


@router.get("/operations/capabilities", response_model=BrcOperationCapabilitiesResponse)
async def get_brc_operation_capabilities(request: Request) -> BrcOperationCapabilitiesResponse:
    service = await _get_operation_service(request)
    return BrcOperationCapabilitiesResponse(capabilities=service.capabilities())


@router.get("/strategy-families", response_model=list[StrategyFamily])
async def list_brc_strategy_families(
    limit: int = Query(default=100, ge=1, le=200),
) -> list[StrategyFamily]:
    service = await _get_admission_service()
    return await service.list_strategy_families(limit=limit)


@router.post("/strategy-families", response_model=StrategyFamily)
async def create_brc_strategy_family(
    body: BrcStrategyFamilyCreateRequest,
) -> StrategyFamily:
    service = await _get_admission_service()
    try:
        return await service.create_strategy_family(**body.model_dump())
    except Exception as exc:
        _raise_admission_error(exc)
        raise


@router.get("/strategy-families/{strategy_family_id}", response_model=StrategyFamily)
async def get_brc_strategy_family(strategy_family_id: str) -> StrategyFamily:
    service = await _get_admission_service()
    try:
        return await service.get_strategy_family(strategy_family_id)
    except Exception as exc:
        _raise_admission_error(exc)
        raise


@router.post(
    "/strategy-families/{strategy_family_id}/versions",
    response_model=StrategyFamilyVersion,
)
async def create_brc_strategy_family_version(
    strategy_family_id: str,
    body: BrcStrategyFamilyVersionCreateRequest,
) -> StrategyFamilyVersion:
    service = await _get_admission_service()
    try:
        return await service.create_strategy_family_version(
            strategy_family_id=strategy_family_id,
            **body.model_dump(),
        )
    except Exception as exc:
        _raise_admission_error(exc)
        raise


@router.post(
    "/admissions/evidence-packets",
    response_model=AdmissionEvidencePacket,
)
async def create_brc_admission_evidence_packet(
    body: BrcEvidencePacketCreateRequest,
) -> AdmissionEvidencePacket:
    service = await _get_admission_service()
    try:
        return await service.create_evidence_packet(**body.model_dump())
    except Exception as exc:
        _raise_admission_error(exc)
        raise


@router.post(
    "/admissions/owner-regime-inputs",
    response_model=OwnerMarketRegimeInput,
)
async def create_brc_owner_regime_input(
    body: BrcOwnerRegimeInputCreateRequest,
) -> OwnerMarketRegimeInput:
    service = await _get_admission_service()
    try:
        return await service.create_owner_regime_input(**body.model_dump())
    except Exception as exc:
        _raise_admission_error(exc)
        raise


@router.post("/admissions/requests", response_model=BrcAdmissionRequestModel)
async def create_brc_admission_request(
    body: BrcAdmissionRequestCreateRequest,
) -> BrcAdmissionRequestModel:
    service = await _get_admission_service()
    try:
        return await service.create_admission_request(**body.model_dump())
    except Exception as exc:
        _raise_admission_error(exc)
        raise


@router.get("/admissions/requests/{admission_request_id}", response_model=BrcAdmissionRequestModel)
async def get_brc_admission_request(admission_request_id: str) -> BrcAdmissionRequestModel:
    service = await _get_admission_service()
    try:
        return await service.get_admission_request(admission_request_id)
    except Exception as exc:
        _raise_admission_error(exc)
        raise


@router.post("/admissions/requests/{admission_request_id}/evaluate", response_model=AdmissionDecision)
async def evaluate_brc_admission_request(admission_request_id: str) -> AdmissionDecision:
    service = await _get_admission_service()
    try:
        return await service.evaluate(admission_request_id)
    except Exception as exc:
        _raise_admission_error(exc)
        raise


@router.get("/admissions/decisions", response_model=list[AdmissionDecision])
async def list_brc_admission_decisions(
    limit: int = Query(default=100, ge=1, le=200),
) -> list[AdmissionDecision]:
    service = await _get_admission_service()
    return await service.list_admission_decisions(limit=limit)


@router.get("/admissions/decisions/{admission_decision_id}", response_model=AdmissionDecision)
async def get_brc_admission_decision(admission_decision_id: str) -> AdmissionDecision:
    service = await _get_admission_service()
    try:
        return await service.get_admission_decision(admission_decision_id)
    except Exception as exc:
        _raise_admission_error(exc)
        raise


@router.post("/admissions/risk-acceptances", response_model=OwnerRiskAcceptance)
async def create_brc_owner_risk_acceptance(
    body: BrcOwnerRiskAcceptanceCreateRequest,
) -> OwnerRiskAcceptance:
    service = await _get_admission_service()
    try:
        return await service.create_owner_risk_acceptance(
            OwnerRiskAcceptanceInput(**body.model_dump())
        )
    except Exception as exc:
        _raise_admission_error(exc)
        raise


@router.get("/admissions/trial-bindings", response_model=list[AdmissionTrialBinding])
async def list_brc_admission_trial_bindings(
    limit: int = Query(default=100, ge=1, le=200),
) -> list[AdmissionTrialBinding]:
    service = await _get_admission_service()
    return await service.list_admission_trial_bindings(limit=limit)


@router.get("/admissions/trial-bindings/{binding_id}", response_model=AdmissionTrialBinding)
async def get_brc_admission_trial_binding(binding_id: str) -> AdmissionTrialBinding:
    service = await _get_admission_service()
    try:
        return await service.get_admission_trial_binding(binding_id)
    except Exception as exc:
        _raise_admission_error(exc)
        raise


@router.post("/operations/preflight", response_model=OperationPreflightResponse)
async def preflight_brc_operation(
    request: Request,
    body: BrcOperationPreflightRequest,
) -> OperationPreflightResponse:
    service = await _get_operation_service(request)
    try:
        return await service.preflight(
            operation_type=body.operation_type,
            requested_by=body.requested_by,
            input_params=body.input_params,
            source=body.source,
        )
    except Exception as exc:
        _raise_operation_error(exc)
        raise


@router.post("/operations/{operation_id}/confirm", response_model=OperationConfirmResponse)
async def confirm_brc_operation(
    request: Request,
    operation_id: str,
    body: BrcOperationConfirmRequest,
) -> OperationConfirmResponse:
    service = await _get_operation_service(request)
    try:
        return await service.confirm(
            operation_id=operation_id,
            preflight_id=body.preflight_id,
            confirmation_phrase=body.confirmation_phrase,
            idempotency_key=body.idempotency_key,
            confirmed_by=body.confirmed_by,
        )
    except Exception as exc:
        _raise_operation_error(exc)
        raise


@router.post("/operations/{operation_id}/cancel", response_model=OperationConfirmResponse)
async def cancel_brc_operation(
    request: Request,
    operation_id: str,
    body: BrcOperationCancelRequest,
) -> OperationConfirmResponse:
    service = await _get_operation_service(request)
    try:
        return await service.cancel(operation_id=operation_id, requested_by=body.requested_by)
    except Exception as exc:
        _raise_operation_error(exc)
        raise


@router.get("/operations/{operation_id}", response_model=OperationDetailResponse)
async def get_brc_operation(request: Request, operation_id: str) -> OperationDetailResponse:
    service = await _get_operation_service(request)
    try:
        return await service.get(operation_id)
    except Exception as exc:
        _raise_operation_error(exc)
        raise


@router.get("/operations", response_model=OperationListResponse)
async def list_brc_operations(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
) -> OperationListResponse:
    service = await _get_operation_service(request)
    return await service.list(limit=limit)


@router.get("/dashboard", response_model=BrcDashboardResponse)
async def get_brc_dashboard() -> BrcDashboardResponse:
    return BrcDashboardResponse()


@router.get("/account/facts", response_model=BrcAccountFactsResponse)
async def get_brc_account_facts() -> BrcAccountFactsResponse:
    return await _account_facts(_api_module())


@router.get("/markets-orders", response_model=BrcMarketsOrdersResponse)
async def get_brc_markets_orders() -> BrcMarketsOrdersResponse:
    api_module = _api_module()
    facts = await _account_facts(api_module)
    all_flat = bool(facts.account_summary.get("all_local_flat"))
    return BrcMarketsOrdersResponse(
        conclusion=(
            "当前本地 PG 摘要未发现 BRC BTC/ETH active position/open order。"
            if all_flat
            else "当前本地 PG 摘要发现 active position 或 open order，需要核对订单触发链路。"
        ),
        account_impact="只读查询，不会下单、平仓、提现、转账或修改仓位。",
        source=facts.source,
        truth_level=facts.truth_level,
        reconciliation_status=facts.reconciliation_status,
        symbols=list(facts.account_summary.get("controlled_symbols", [])),
        open_orders=facts.open_orders,
        active_positions=facts.positions,
        recent_orders=facts.recent_orders,
        recent_fills=facts.recent_fills,
        exposure_by_symbol=facts.exposure_by_symbol,
        unknown_or_unmanaged_orders=facts.unknown_or_unmanaged_orders,
        unknown_or_unmanaged_positions=facts.unknown_or_unmanaged_positions,
        limitations=facts.limitations,
        warnings=facts.warnings,
        blockers=facts.blockers,
        developer_details={
            "connection_health": facts.connection_health,
            "account_summary": facts.account_summary,
            "generated_at_ms": facts.generated_at_ms,
        },
    )


@router.get("/audit-trail", response_model=BrcAuditTrailResponse)
async def get_brc_audit_trail(limit: int = Query(default=50, ge=1, le=200)) -> BrcAuditTrailResponse:
    service = getattr(_api_module(), "_brc_campaign_service", None)
    summary, errors = await _audit_summary(service, limit=limit)
    timeline = list(summary.get("timeline", []))
    return BrcAuditTrailResponse(
        conclusion=(
            "已读取最近 BRC 操作审计记录。"
            if timeline
            else "当前没有可展示的 BRC 操作审计记录。"
        ),
        account_impact="只读审计查询，不会重放、修改或执行任何历史动作。",
        timeline=timeline,
        operation_results=list(summary.get("operation_results", [])),
        operator_actions=list(summary.get("operator_actions", [])),
        workflow_runs=list(summary.get("workflow_runs", [])),
        review_decisions=list(summary.get("review_decisions", [])),
        developer_details={"errors": errors},
    )


@router.post("/investigator/ask", response_model=BrcInvestigatorAskResponse)
async def ask_brc_investigator(body: BrcInvestigatorAskRequest) -> BrcInvestigatorAskResponse:
    api_module = _api_module()
    readiness = await get_brc_readiness()
    markets, market_errors = await _markets_orders_summary(api_module)
    audit, audit_errors = await _audit_summary(getattr(api_module, "_brc_campaign_service", None), limit=10)
    question = body.question.strip()
    lower = question.lower()

    if any(token in lower for token in ["order", "订单"]):
        intent = "order_trace"
        orders = list(markets.get("open_orders", []))
        conclusion = (
            "当前没有可追踪的本地 open order；如果你问的是历史成交，需要后续接入历史订单 trace。"
            if not orders
            else "当前发现本地 open order，需通过 operator/workflow/campaign 证据继续核对来源。"
        )
        evidence = [
            f"本地 open orders: {len(orders)}",
            f"本地 active positions: {markets.get('active_position_count', 0)}",
            "订单解释只读取本地 PG/order repository 摘要，不访问实盘账户。",
        ]
        trace = [
            {"step": "Owner question", "evidence": question},
            {"step": "Markets/orders resolver", "evidence": {"open_order_count": len(orders)}},
            {"step": "Audit resolver", "evidence": audit.get("latest_event")},
        ]
        next_step = "如果页面上有具体 order_id，后续版本会按 order_id 展开 workflow/action/campaign 完整链路。"
    elif any(token in lower for token in ["blocked", "block", "不能", "为什么"]):
        intent = "blocked_reason"
        conclusion = readiness.current_conclusion
        evidence = readiness.why
        trace = [
            {"step": "Readiness mode", "evidence": readiness.mode},
            {"step": "Disabled actions", "evidence": [item.model_dump(mode="json") for item in readiness.disabled_actions]},
        ]
        next_step = readiness.next_step
    elif any(token in lower for token in ["campaign", "轮", "亏损", "盈利", "loss", "profit"]):
        intent = "campaign_review"
        campaign = readiness.latest_campaign
        conclusion = (
            f"最近 campaign 状态是 {campaign.get('status')}，结果是 {campaign.get('outcome') or '未结束'}。"
            if campaign
            else "当前没有 latest campaign，无法进行 campaign 复盘解释。"
        )
        evidence = [
            f"latest_campaign_present: {campaign is not None}",
            f"review_available: {readiness.review_summary.get('review_available')}",
        ]
        trace = [
            {"step": "Latest campaign", "evidence": campaign},
            {"step": "Review summary", "evidence": readiness.review_summary},
        ]
        next_step = "有 campaign 时先看 Campaigns 页面和 Review 页面；没有 campaign 时不要手填 ID。"
    elif any(token in lower for token in ["最近", "发生", "日志", "审计", "audit"]):
        intent = "recent_audit"
        timeline = list(audit.get("timeline", []))
        conclusion = "已读取最近关键操作。" if timeline else "当前没有最近关键操作记录。"
        evidence = [f"timeline events: {len(timeline)}"]
        trace = timeline[:5]
        next_step = "进入 Audit Trail 查看完整时间线和对象链路。"
    else:
        intent = "runtime_status"
        conclusion = readiness.current_conclusion
        evidence = readiness.why
        trace = [
            {"step": "Runtime summary", "evidence": readiness.runtime_summary},
            {"step": "Markets summary", "evidence": markets},
        ]
        next_step = readiness.next_step

    return BrcInvestigatorAskResponse(
        intent=intent,
        conclusion=conclusion,
        reason="AI Investigator MVP 使用受控只读 resolver，不使用自由 SQL，也不会把模型输出当作事实源。",
        account_impact="不会影响真实账户；不会下单、提现、转账、改参数或切换 playbook。",
        evidence_summary=[str(item) for item in evidence],
        trace=trace,
        next_step=next_step,
        developer_details={
            "context_type": body.context_type,
            "context_id": body.context_id,
            "market_errors": market_errors,
            "audit_errors": audit_errors,
            "free_sql_enabled": False,
        },
    )


@router.get("/campaigns/current", response_model=runtime.BrcCampaignResponse)
async def get_current_campaign(request: Request) -> runtime.BrcCampaignResponse:
    return await runtime.get_current_brc_campaign(request)


@router.get("/evidence", response_model=runtime.BrcEvidenceResponse)
async def get_evidence(request: Request) -> runtime.BrcEvidenceResponse:
    return await runtime.get_brc_evidence(request)


@router.get("/review-packet", response_model=runtime.BrcReviewPacketResponse)
async def get_review_packet(request: Request) -> runtime.BrcReviewPacketResponse:
    return await runtime.get_brc_review_packet(request)


@router.get("/next-eligibility", response_model=runtime.BrcNextEligibilityResponse)
async def get_next_eligibility(request: Request) -> runtime.BrcNextEligibilityResponse:
    return await runtime.get_brc_next_eligibility(request)


@router.post("/review-decisions", response_model=runtime.BrcReviewDecisionResponse)
async def create_review_decision(
    request: Request,
    body: runtime.BrcReviewDecisionRequest,
) -> runtime.BrcReviewDecisionResponse:
    return await runtime.create_brc_review_decision(request, body)


@router.get("/review-decisions/latest", response_model=runtime.BrcReviewDecisionResponse)
async def get_latest_review_decision(request: Request) -> runtime.BrcReviewDecisionResponse:
    return await runtime.get_latest_brc_review_decision(request)


@router.get("/review-decisions", response_model=runtime.BrcReviewDecisionListResponse)
async def list_review_decisions(
    request: Request,
    campaign_id: Optional[str] = Query(default=None, max_length=128),
    limit: int = Query(default=50, ge=1, le=200),
) -> runtime.BrcReviewDecisionListResponse:
    return await runtime.list_brc_review_decisions(request, campaign_id=campaign_id, limit=limit)


@operator_router.post("/draft", response_model=runtime.BrcOperatorIntentDraftResponse)
async def draft_operator_intent(
    request: Request,
    body: runtime.BrcOperatorIntentDraftRequest,
) -> runtime.BrcOperatorIntentDraftResponse:
    return await runtime.draft_brc_operator_intent(request, body)


@operator_router.post("/plan", response_model=runtime.BrcOperatorPlanResponse)
async def plan_operator_action(
    request: Request,
    body: runtime.BrcOperatorIntentDraftRequest,
) -> runtime.BrcOperatorPlanResponse:
    return await runtime.plan_brc_operator_action(request, body)


@operator_router.get("/actions", response_model=runtime.BrcOperatorActionListResponse)
async def list_operator_actions(
    request: Request,
    campaign_id: Optional[str] = Query(default=None, max_length=128),
    limit: int = Query(default=50, ge=1, le=200),
) -> runtime.BrcOperatorActionListResponse:
    return await runtime.list_brc_operator_actions(request, campaign_id=campaign_id, limit=limit)


@operator_router.get("/actions/{action_id}", response_model=runtime.BrcOperatorActionResponse)
async def get_operator_action(
    action_id: str,
    request: Request,
) -> runtime.BrcOperatorActionResponse:
    return await runtime.get_brc_operator_action(action_id, request)


@operator_router.post("/actions/{action_id}/run", response_model=runtime.BrcOperatorRunResponse)
async def run_operator_action_by_id(
    action_id: str,
    request: Request,
    body: runtime.BrcOperatorActionRunRequest,
) -> runtime.BrcOperatorRunResponse:
    return await runtime.run_brc_operator_action_by_id(action_id, request, body)


@operator_router.post("/run", response_model=runtime.BrcOperatorRunResponse)
async def run_operator_action(
    request: Request,
    body: runtime.BrcOperatorRunRequest,
) -> runtime.BrcOperatorRunResponse:
    return await runtime.run_brc_operator_action(request, body)


@workflow_router.post("", response_model=runtime.BrcLlmWorkflowResponse)
async def create_llm_workflow(
    request: Request,
    body: runtime.BrcLlmWorkflowCreateRequest,
) -> runtime.BrcLlmWorkflowResponse:
    return await runtime.create_brc_llm_workflow(request, body)


@workflow_router.get("", response_model=runtime.BrcLlmWorkflowListResponse)
async def list_llm_workflows(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    status: Optional[runtime.BrcWorkflowStatus] = Query(default=None),
) -> runtime.BrcLlmWorkflowListResponse:
    return await runtime.list_brc_llm_workflows(request, limit=limit, status=status)


@workflow_router.get("/{workflow_run_id}", response_model=runtime.BrcLlmWorkflowResponse)
async def get_llm_workflow(
    workflow_run_id: str,
    request: Request,
) -> runtime.BrcLlmWorkflowResponse:
    return await runtime.get_brc_llm_workflow(workflow_run_id, request)


@workflow_router.post("/{workflow_run_id}/confirm", response_model=runtime.BrcLlmWorkflowResponse)
async def confirm_llm_workflow(
    workflow_run_id: str,
    request: Request,
    body: runtime.BrcLlmWorkflowConfirmRequest,
) -> runtime.BrcLlmWorkflowResponse:
    return await runtime.confirm_brc_llm_workflow(workflow_run_id, request, body)


@dev_testnet_router.post("/campaigns", response_model=runtime.BrcCampaignResponse)
async def create_testnet_campaign(
    request: Request,
    body: runtime.BrcCreateCampaignRequest,
) -> runtime.BrcCampaignResponse:
    return await runtime.create_brc_campaign(request, body)


@dev_testnet_router.post("/switch-playbook", response_model=runtime.BrcSwitchPlaybookResponse)
async def switch_testnet_playbook(
    request: Request,
    body: runtime.BrcSwitchPlaybookRequest,
) -> runtime.BrcSwitchPlaybookResponse:
    return await runtime.switch_brc_playbook(request, body)


@dev_testnet_router.post("/{symbol_key}/arm-attempt", response_model=runtime.BrcAttemptResponse)
async def arm_testnet_attempt(
    symbol_key: str,
    request: Request,
    body: runtime.BrcArmAttemptRequest,
) -> runtime.BrcAttemptResponse:
    return await runtime.arm_brc_attempt(symbol_key, request, body)


@dev_testnet_router.post("/{symbol_key}/execute-controlled-entry", response_model=runtime.ControlledEntryResponse)
async def execute_testnet_entry(symbol_key: str, request: Request) -> runtime.ControlledEntryResponse:
    return await runtime.execute_brc_controlled_entry(symbol_key, request)


@dev_testnet_router.post("/{symbol_key}/execute-controlled-close", response_model=runtime.ControlledCloseResponse)
async def execute_testnet_close(symbol_key: str, request: Request) -> runtime.ControlledCloseResponse:
    return await runtime.execute_brc_controlled_close(symbol_key, request)


@dev_testnet_router.get("/carriers", response_model=runtime.StrategyTrialCarrierListResponse)
async def list_strategy_trial_testnet_carriers(request: Request) -> runtime.StrategyTrialCarrierListResponse:
    return await runtime.list_strategy_trial_controlled_testnet_carriers(request)


@dev_testnet_router.post(
    "/carriers/{carrier_id}/execute-controlled-entry",
    response_model=runtime.StrategyTrialCarrierEntryResponse,
)
async def execute_strategy_trial_testnet_carrier_entry(
    carrier_id: str,
    request: Request,
    body: runtime.StrategyTrialCarrierEntryRequest = runtime.StrategyTrialCarrierEntryRequest(),
) -> runtime.StrategyTrialCarrierEntryResponse:
    return await runtime.execute_strategy_trial_carrier_controlled_entry(carrier_id, request, body)


@dev_testnet_router.post(
    "/carriers/{carrier_id}/execute-controlled-close",
    response_model=runtime.StrategyTrialCarrierCloseResponse,
)
async def execute_strategy_trial_testnet_carrier_close(
    carrier_id: str,
    request: Request,
) -> runtime.StrategyTrialCarrierCloseResponse:
    return await runtime.execute_strategy_trial_carrier_controlled_close(carrier_id, request)


@dev_testnet_router.post("/mock-pnl", response_model=runtime.BrcMockPnlResponse)
async def inject_testnet_mock_pnl(
    request: Request,
    body: runtime.BrcMockPnlRequest,
) -> runtime.BrcMockPnlResponse:
    return await runtime.inject_brc_mock_pnl(request, body)


@dev_testnet_router.post("/finalize", response_model=runtime.BrcCampaignResponse)
async def finalize_testnet_campaign(
    request: Request,
    body: runtime.BrcFinalizeRequest,
) -> runtime.BrcCampaignResponse:
    return await runtime.finalize_brc_campaign(request, body)
