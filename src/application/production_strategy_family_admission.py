"""Production strategy-family admission and action-entry state builder.

This module builds the Owner-facing product backbone for candidate review,
ActionSpec shaping, FinalGate preview inputs, protection/review templates, and
official action-path handoff. It does not create admission requests,
authorizations, execution intents, orders, protection orders, reviews, runtime
transitions, or PG mutations.
"""

from __future__ import annotations

import time
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from src.application.action_spec_final_gate_adapter import (
    ActionCandidateAdapterInput,
    ActionSpecDraftInput,
    ActionSpecFinalGateAdapterResult,
    ActionSpecFinalGateAdapterService,
    FinalGateFactInput,
)
from src.application.owner_action_carrier_catalog import (
    get_owner_action_carrier,
    supported_owner_action_carrier_ids,
)
from src.domain.strategy_family_registry import (
    StrategyFamilyType,
    initial_strategy_family_registry_seed,
)


REQUIRED_OWNER_SCOPE_FIELDS = [
    "symbol",
    "side",
    "quantity",
    "max_notional",
    "leverage",
    "max_attempts",
    "protection_mode",
    "review_requirement",
]

ADMISSION_CHAIN = [
    "StrategyFamily",
    "StrategyGroup",
    "Carrier",
    "RiskDisclosure",
    "AuthorizationDraft",
    "BoundedLiveAuthorization",
    "ExecutionIntent",
    "Entry",
    "TP/SL",
    "Review",
]

BRIDGE_ARTIFACTS = [
    "TrendObservation",
    "StrategyGroupMappingProposal",
    "CarrierCandidate",
    "CarrierReadinessReport",
    "ActionCandidate",
    "RiskDisclosureDraft",
    "AuthorizationDraftProposal",
    "BudgetEnvelopeDraft",
    "FinalGateDryRun",
    "PreExecutionBlockedReview",
    "ProtectionPlanDraft",
    "ReviewContract",
    "AuditChainGapReport",
]

OFFICIAL_ACTION_API_ENDPOINTS = {
    "owner_trial_flow_current": "GET /api/brc/owner-trial-flow/current",
    "risk_acknowledgement": "POST /api/brc/owner-trial-flow/risk-acknowledgement",
    "authorization_draft": "POST /api/brc/owner-trial-flow/authorization-draft",
    "activate_live_authorization": (
        "POST /api/brc/owner-trial-flow/authorization-draft/{draft_id}/activate-live-authorization"
    ),
    "final_gate_dry_run": "POST /api/brc/owner-trial-flow/live-execution-bridge/dry-run",
    "execute_authorization": "POST /api/brc/owner-trial-flow/authorizations/{authorization_id}/execute",
}

CURRENT_OFFICIAL_ACTION_CARRIER_IDS = supported_owner_action_carrier_ids()

API_BACKED_AUTHORIZATION_ENDPOINTS = {
    "create_admission_request": "POST /api/brc/admissions/requests",
    "evaluate_admission_request": "POST /api/brc/admissions/requests/{admission_request_id}/evaluate",
    "create_owner_risk_acceptance": "POST /api/brc/admissions/risk-acceptances",
    "operation_capabilities": "GET /api/brc/operations/capabilities",
    "operation_preflight": "POST /api/brc/operations/preflight",
    "operation_confirm": "POST /api/brc/operations/{operation_id}/confirm",
}

API_BACKED_AUTHORIZATION_OPERATION_CHAIN = [
    (
        "create_gated_trial_from_admission",
        "CONFIRM_RESERVE_ADMISSION_BINDING",
        "reserve admission-trial binding metadata",
    ),
    (
        "create_campaign_from_admission_binding",
        "CONFIRM_CREATE_ADMISSION_CAMPAIGN_SHELL",
        "create admission campaign shell metadata",
    ),
    (
        "install_runtime_constraints_from_admission_campaign",
        "CONFIRM_INSTALL_ADMISSION_CAMPAIGN_CONSTRAINTS",
        "install admission campaign constraints metadata",
    ),
    (
        "prepare_runtime_carrier_from_admission_campaign",
        "CONFIRM_PREPARE_ADMISSION_RUNTIME_CARRIER",
        "prepare runtime carrier readiness metadata",
    ),
    (
        "prepare_runtime_start_from_admission_carrier",
        "CONFIRM_PREPARE_ADMISSION_RUNTIME_START",
        "prepare runtime start readiness metadata",
    ),
    (
        "evaluate_trial_trade_intent",
        "CONFIRM_EVALUATE_TRIAL_TRADE_INTENT",
        "evaluate execution-mode enforcement evidence",
    ),
    (
        "prepare_runtime_handoff_from_admission_campaign",
        "CONFIRM_PREPARE_ADMISSION_RUNTIME_HANDOFF",
        "prepare runtime handoff readiness metadata",
    ),
    (
        "start_runtime_from_admission_handoff",
        "CONFIRM_START_ADMISSION_RUNTIME",
        "start admission-backed runtime state without strategy activation",
    ),
    (
        "prepare_strategy_activation_from_admission_runtime",
        "CONFIRM_PREPARE_STRATEGY_ACTIVATION",
        "prepare strategy activation readiness metadata",
    ),
    (
        "activate_strategy_from_admission_runtime",
        "CONFIRM_ACTIVATE_STRATEGY_NO_EXECUTION",
        "activate strategy metadata without signal loop or execution",
    ),
    (
        "prepare_signal_loop_from_admission_strategy",
        "CONFIRM_PREPARE_SIGNAL_LOOP",
        "prepare signal-loop readiness metadata",
    ),
    (
        "start_signal_loop_from_admission_strategy",
        "CONFIRM_START_SIGNAL_LOOP_NO_SIGNAL",
        "start signal-loop state without signal generation",
    ),
    (
        "evaluate_signal_from_admission_strategy",
        "CONFIRM_EVALUATE_SIGNAL_NO_INTENT",
        "evaluate signal metadata without trade intent",
    ),
    (
        "record_trial_trade_intent_from_signal_evaluation",
        "CONFIRM_RECORD_TRIAL_TRADE_INTENT",
        "record non-executable trial trade intent evidence",
    ),
]

PRE_POST_PG_TABLES = [
    "orders",
    "positions",
    "execution_intents",
    "authorizations",
    "protection_price_plans",
    "recovery_tasks",
    "audit_logs",
    "campaign_events",
]

PRE_POST_EXCHANGE_READS = [
    "account_balance",
    "positions",
    "open_orders",
    "order_detail",
]

AdmissionLevelCode = Literal["L0", "L1", "L2", "L3", "L4"]
ResearchRiskClassification = Literal[
    "warning",
    "fragile_evidence",
    "insufficient_research",
    "owner_risk_acceptance_required",
]

RESEARCH_RISK_CLASSIFICATIONS = [
    "warning",
    "fragile_evidence",
    "insufficient_research",
    "owner_risk_acceptance_required",
]

OWNER_RISK_ACCEPTANCE_MAY_OVERRIDE = [
    "fragile_evidence",
    "insufficient_research",
    "weak strategy evidence",
    "thin sample",
    "incomplete signal markers",
    "historical fragility",
]

OWNER_RISK_ACCEPTANCE_NEVER_OVERRIDES = [
    "Owner authorization",
    "scope match",
    "budget availability",
    "account and reconciliation facts",
    "position or open-order conflicts",
    "mandatory TP/SL protection",
    "FinalGate",
    "Operation Layer",
    "runtime/profile/environment/GKS guards",
]


class ProductionAdmissionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AdmissionLevelSpec(ProductionAdmissionModel):
    level: AdmissionLevelCode
    name: str
    semantics: str
    action_candidate_allowed: bool
    live_action_allowed: bool
    autonomy_allowed: bool = False
    required_artifacts: list[str] = Field(default_factory=list)
    hard_gate_policy: str
    example_status: str
    owner_risk_acceptance_required_for_l3: bool = False


class WarningHardBlockerPolicy(ProductionAdmissionModel):
    weak_strategy_evidence_policy: Literal["warning_not_hard_blocker"] = (
        "warning_not_hard_blocker"
    )
    warning_items: list[str] = Field(default_factory=list)
    research_deficiency_classifications: list[str] = Field(
        default_factory=lambda: list(RESEARCH_RISK_CLASSIFICATIONS)
    )
    owner_risk_acceptance_may_override: list[str] = Field(
        default_factory=lambda: list(OWNER_RISK_ACCEPTANCE_MAY_OVERRIDE)
    )
    owner_risk_acceptance_never_overrides: list[str] = Field(
        default_factory=lambda: list(OWNER_RISK_ACCEPTANCE_NEVER_OVERRIDES)
    )
    l3_requires_owner_risk_acceptance: bool = True
    hard_blockers_for_live_action: list[str] = Field(default_factory=list)
    post_action_acceptance_outputs: list[str] = Field(default_factory=list)
    policy_summary: str


class StrategyFamilySpec(ProductionAdmissionModel):
    family: str
    strategy_family_id: Optional[str] = None
    family_type: Optional[str] = None
    admission_level: AdmissionLevelCode
    hypothesis: str
    supported_symbols: list[str] = Field(default_factory=list)
    evidence_requirements: list[str] = Field(default_factory=list)
    warning_items: list[str] = Field(default_factory=list)
    research_quality_status: ResearchRiskClassification = "warning"
    risk_disclosure_classifications: list[ResearchRiskClassification] = Field(
        default_factory=list
    )
    owner_risk_acceptance_required: bool = True
    owner_risk_acceptance_may_override: list[str] = Field(
        default_factory=lambda: list(OWNER_RISK_ACCEPTANCE_MAY_OVERRIDE)
    )
    owner_risk_acceptance_never_overrides: list[str] = Field(
        default_factory=lambda: list(OWNER_RISK_ACCEPTANCE_NEVER_OVERRIDES)
    )
    hard_blockers_for_live_action: list[str] = Field(default_factory=list)
    not_alpha_proof: bool = True


class StrategyGroupSpec(ProductionAdmissionModel):
    family: str
    strategy_group: str
    owner_input_modes: list[str] = Field(default_factory=list)
    selection_output: str
    maps_to_carrier_id: Optional[str] = None
    read_only: bool = True


class CarrierSpec(ProductionAdmissionModel):
    family: str
    carrier_id: Optional[str] = None
    admission_level: AdmissionLevelCode
    status: str
    proposal_role: Literal["trend_candidate", "range_candidate", "volatility_candidate", "unknown"] = "unknown"
    market_regime: Optional[str] = None
    supported_symbols: list[str] = Field(default_factory=list)
    supported_sides: list[str] = Field(default_factory=list)
    scope_template: dict[str, object] = Field(default_factory=dict)
    default_example: dict[str, object] = Field(default_factory=dict)
    protection_template: dict[str, object] = Field(default_factory=dict)
    review_template_ref: Optional[str] = None
    action_registry_supported: bool = False
    can_produce_action_candidate: bool = False
    blockers: list[str] = Field(default_factory=list)
    research_quality_status: ResearchRiskClassification = "warning"
    risk_disclosure_classifications: list[ResearchRiskClassification] = Field(
        default_factory=list
    )
    owner_risk_acceptance_required: bool = True


class RiskDisclosureSpec(ProductionAdmissionModel):
    family: str
    acknowledgement_required: bool = True
    weak_strategy_evidence_is_warning: bool = True
    research_quality_status: ResearchRiskClassification = "warning"
    risk_disclosure_classifications: list[ResearchRiskClassification] = Field(
        default_factory=list
    )
    owner_risk_acceptance_required: bool = True
    owner_risk_acceptance_may_override: list[str] = Field(
        default_factory=lambda: list(OWNER_RISK_ACCEPTANCE_MAY_OVERRIDE)
    )
    owner_risk_acceptance_never_overrides: list[str] = Field(
        default_factory=lambda: list(OWNER_RISK_ACCEPTANCE_NEVER_OVERRIDES)
    )
    owner_risk_acceptance_cannot_override_execution_safety_gates: bool = True
    warnings: list[str] = Field(default_factory=list)
    hard_blockers_not_included: list[str] = Field(default_factory=list)


class ReviewTemplate(ProductionAdmissionModel):
    family: str
    metrics: list[str] = Field(default_factory=list)
    required_sections: list[str] = Field(default_factory=list)
    post_action_required: bool = True
    pre_action_evidence_required: list[str] = Field(default_factory=list)


class WarningRecord(ProductionAdmissionModel):
    warning_id: str
    family: str
    carrier_id: Optional[str] = None
    classification: Literal[
        "strategy_warning",
        "warning",
        "fragile_evidence",
        "insufficient_research",
        "owner_risk_acceptance_required",
    ] = "strategy_warning"
    description: str
    owner_ack_required: bool = True
    blocks_after_ack: Literal[False] = False


class CandidateActionability(ProductionAdmissionModel):
    family: str
    strategy_family_id: Optional[str] = None
    carrier_id: Optional[str] = None
    admission_level: AdmissionLevelCode
    actionability: Literal[
        "historical_proof_not_current_action",
        "displayable",
        "proposal_review",
        "owner_scope_final_gate_ready",
        "blocked",
    ]
    action_registry_supported: bool
    owner_can_review: bool = True
    owner_authorization_path_available: bool
    final_gate_preview_available: bool
    budget_envelope_compatible: bool = False
    warning_count: int
    hard_blocker_count: int
    disabled_reason: str
    next_hard_gate: str
    may_execute_live: Literal[False] = False
    frontend_action_enabled: Literal[False] = False


class ProtectionTemplateSpec(ProductionAdmissionModel):
    template_id: str
    family: str
    carrier_id: Optional[str] = None
    mode: Literal[
        "single_tp_plus_sl",
        "fixed_percent_tp_sl",
        "atr_based_tp_sl",
        "range_reversion_stop",
        "manual_review_required",
    ]
    required_components: list[str] = Field(default_factory=list)
    parameter_requirements: list[str] = Field(default_factory=list)
    hard_blockers_for_live_action: list[str] = Field(default_factory=list)
    review_template_ref: str
    may_execute_live: Literal[False] = False
    frontend_action_enabled: Literal[False] = False


class FinalGatePreviewInputModel(ProductionAdmissionModel):
    preview_id: str
    candidate_id: Optional[str] = None
    carrier_id: Optional[str] = None
    strategy_family: str
    strategy_family_id: Optional[str] = None
    admission_level: AdmissionLevelCode
    account_scope_ref: str = "pre_action_account_and_subaccount_facts_required"
    symbol: Optional[str] = None
    side: Optional[str] = None
    quantity: Optional[str] = None
    target_notional_usdt: Optional[str] = None
    max_notional: Optional[str] = None
    leverage: Optional[str] = None
    max_attempts: Optional[int] = None
    protection_mode: Optional[str] = None
    protection_template_id: str
    budget_envelope_ref: Optional[str] = None
    owner_authorization_ref: Optional[str] = None
    required_checks: list[str] = Field(default_factory=list)
    warning_refs: list[str] = Field(default_factory=list)
    hard_blocker_refs: list[str] = Field(default_factory=list)
    status: Literal[
        "ready_for_official_final_gate_preview",
        "proposal_only",
        "blocked_invalid_scope",
    ]
    final_gate_endpoint: str = OFFICIAL_ACTION_API_ENDPOINTS["final_gate_dry_run"]
    operation_layer_required: bool = True
    may_execute_live: Literal[False] = False
    frontend_action_enabled: Literal[False] = False


class ProductBackboneCarrierExample(ProductionAdmissionModel):
    example_id: str
    role: Literal[
        "historical_regression_sample",
        "owner_confirmed_candidate",
        "budgeted_autonomy_sample",
        "proposal_dry_run_candidate",
    ]
    family: str
    strategy_family_id: Optional[str] = None
    carrier_id: Optional[str] = None
    admission_level: AdmissionLevelCode
    symbol: Optional[str] = None
    side: Optional[str] = None
    quantity: Optional[str] = None
    target_notional_usdt: Optional[str] = None
    max_notional: Optional[str] = None
    leverage: Optional[str] = None
    protection_template_id: str
    review_template_id: str
    actionability: str
    budgeted_autonomy_compatible: bool = False
    current_status: str
    warnings: list[str] = Field(default_factory=list)
    hard_blockers: list[str] = Field(default_factory=list)
    final_gate_preview_ref: Optional[str] = None
    may_execute_live: Literal[False] = False
    frontend_action_enabled: Literal[False] = False


class ProductBackboneReadModel(ProductionAdmissionModel):
    version: str = "brc_product_backbone_v0_3"
    product_chain: list[str] = Field(
        default_factory=lambda: [
            "StrategyFamily / Carrier",
            "ActionCandidate",
            "Owner risk understanding",
            "Owner authorization or BudgetEnvelope authorization",
            "ActionSpec",
            "FinalGate preview",
            "Operation Layer",
            "bounded live action",
            "Protection",
            "close / TP / SL",
            "Review Ledger",
            "promote / revise / park",
        ]
    )
    principles: list[str] = Field(
        default_factory=lambda: [
            "low-friction admission",
            "medium-friction ActionCandidate generation",
            "few hard execution gates",
            "strategy weakness is warning, execution uncertainty is hard blocker",
            "Review drives iteration",
        ]
    )
    carrier_examples: list[ProductBackboneCarrierExample] = Field(default_factory=list)
    console_flow: list[str] = Field(
        default_factory=lambda: [
            "Owner market input",
            "candidate list",
            "risk disclosure",
            "authorization draft path",
            "FinalGate preview",
            "Owner confirm through official path when actionable",
            "post-action status",
        ]
    )
    official_action_path: list[str] = Field(default_factory=lambda: list(OFFICIAL_ACTION_API_ENDPOINTS.values()))
    execution_policy: str = (
        "Trading Console may present candidates and official-path handoff; live action "
        "requires Owner authorization, FinalGate pass, Operation Layer, protection, and evidence."
    )
    no_action_guarantee: dict[str, bool] = Field(
        default_factory=lambda: {
            "creates_authorization": False,
            "creates_execution_intent": False,
            "places_order": False,
            "starts_runtime": False,
            "mutates_pg": False,
            "exchange_write_action": False,
        }
    )


class TradingConsoleCandidateActionReadModel(ProductionAdmissionModel):
    read_model_id: str = "trading_console_candidate_action_entry_v0_3"
    product_surface: str = "owner_action_entry"
    owner_questions_answered: list[str] = Field(
        default_factory=lambda: [
            "what_candidates_exist",
            "why_this_candidate",
            "symbol_side_suggested_scope",
            "protection_template",
            "warnings_vs_hard_blockers",
            "owner_authorization_path",
            "final_gate_preview_checks",
            "disabled_reason",
        ]
    )
    candidate_output_ref: str = "trading_console_candidate_output"
    action_entry_output_ref: str = "trading_console_action_entry_output"
    product_backbone_ref: str = "product_backbone"
    frontend_policy: str = "operate_as_candidate_action_entry_not_document_or_code_explanation"
    action_enablement_source: Literal["backend_actionable_only"] = "backend_actionable_only"
    official_submit_paths: list[str] = Field(default_factory=lambda: list(OFFICIAL_ACTION_API_ENDPOINTS.values()))
    disabled_action_policy: str = "show exact hard blockers and retry conditions when action is disabled"
    never_show_as: list[str] = Field(
        default_factory=lambda: [
            "documentation_surface",
            "code_explanation",
            "passive_dashboard_only",
        ]
    )


class ActionCandidateSpec(ProductionAdmissionModel):
    family: str
    carrier_id: Optional[str] = None
    admission_level: AdmissionLevelCode
    status: Literal[
        "not_available",
        "proposal",
        "owner_confirmed_candidate_blocked_final_gate",
        "design_only",
    ]
    action_registry_supported: bool = False
    owner_scope_required: list[str] = Field(default_factory=lambda: list(REQUIRED_OWNER_SCOPE_FIELDS))
    hard_blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    research_quality_status: ResearchRiskClassification = "warning"
    risk_disclosure_classifications: list[ResearchRiskClassification] = Field(
        default_factory=list
    )
    owner_risk_acceptance_required: bool = True
    owner_risk_acceptance_may_override: list[str] = Field(
        default_factory=lambda: list(OWNER_RISK_ACCEPTANCE_MAY_OVERRIDE)
    )
    owner_risk_acceptance_never_overrides: list[str] = Field(
        default_factory=lambda: list(OWNER_RISK_ACCEPTANCE_NEVER_OVERRIDES)
    )
    post_action_acceptance_outputs: list[str] = Field(default_factory=list)
    final_gate_required: bool = True
    may_execute_live: Literal[False] = False
    frontend_action_enabled: Literal[False] = False
    creates_authorization: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False


class TradingConsoleCandidateOutput(ProductionAdmissionModel):
    family: str
    strategy_family_id: Optional[str] = None
    carrier_id: Optional[str] = None
    admission_level: AdmissionLevelCode
    candidate_state: Literal["displayable", "proposal", "bounded_live_candidate", "parked"]
    action_candidate_status: str
    action_registry_supported: bool
    warning_count: int
    hard_blocker_count: int
    owner_decision_text: str
    research_quality_status: ResearchRiskClassification = "warning"
    risk_disclosure_classifications: list[ResearchRiskClassification] = Field(
        default_factory=list
    )
    owner_risk_acceptance_required: bool = True
    frontend_action_enabled: Literal[False] = False
    may_execute_live: Literal[False] = False


class GenericActionSpec(ProductionAdmissionModel):
    family: str
    strategy_family_id: Optional[str] = None
    carrier_id: Optional[str] = None
    admission_level: AdmissionLevelCode
    status: Literal["valid_blocked_final_gate", "proposal_non_action", "invalid_blocked"]
    action_registry_supported: bool
    proposal_role: Literal["trend_candidate", "range_candidate", "volatility_candidate", "unknown"] = "unknown"
    market_regime: Optional[str] = None
    sizing_mode: Literal["fixed_quantity", "notional_derived"] = "fixed_quantity"
    action_candidate_ref: Optional[str] = None
    exact_scope_required: bool = True
    supported_symbols: list[str] = Field(default_factory=list)
    supported_sides: list[str] = Field(default_factory=list)
    symbol: Optional[str] = None
    side: Optional[str] = None
    quantity: Optional[str] = None
    target_notional_usdt: Optional[str] = None
    computed_quantity: Optional[str] = None
    estimated_notional_usdt: Optional[str] = None
    market_rule_snapshot: dict[str, object] = Field(default_factory=dict)
    validation_result: dict[str, object] = Field(default_factory=dict)
    suggested_minimum_notional_usdt: Optional[str] = None
    suggested_quantity: Optional[str] = None
    max_notional: Optional[str] = None
    leverage: Optional[str] = None
    max_attempts: Optional[int] = None
    protection_mode: Optional[str] = None
    review_requirement: Optional[str] = None
    budget_envelope_ref: Optional[str] = None
    sizing_source: Optional[str] = None
    recommended_quantity: Optional[str] = None
    recommended_max_notional: Optional[str] = None
    recommended_total_budget: Optional[str] = None
    budget_owner_confirmation_required: bool = True
    budget_recommendation_status: Optional[str] = None
    protection_template: dict[str, object] = Field(default_factory=dict)
    review_template: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    research_quality_status: ResearchRiskClassification = "warning"
    risk_disclosure_classifications: list[ResearchRiskClassification] = Field(
        default_factory=list
    )
    owner_risk_acceptance_required: bool = True
    owner_risk_acceptance_status: Literal["required", "accepted", "not_required"] = (
        "required"
    )
    owner_risk_acceptance_may_override: list[str] = Field(
        default_factory=lambda: list(OWNER_RISK_ACCEPTANCE_MAY_OVERRIDE)
    )
    owner_risk_acceptance_never_overrides: list[str] = Field(
        default_factory=lambda: list(OWNER_RISK_ACCEPTANCE_NEVER_OVERRIDES)
    )
    owner_risk_acceptance_cannot_override_execution_safety_gates: bool = True
    hard_blockers: list[str] = Field(default_factory=list)
    final_gate_adapter_ref: str = "generic_final_gate_adapter_contract"
    action_entry_payload_ref: Optional[str] = None
    may_execute_live: Literal[False] = False
    frontend_action_enabled: Literal[False] = False
    creates_authorization: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False


class ActionEntryPayloadContract(ProductionAdmissionModel):
    family: str
    carrier_id: Optional[str] = None
    payload_id: str
    contract_status: Literal[
        "ready_for_final_gate_adapter",
        "proposal_only",
        "blocked_invalid_scope",
    ]
    official_action_path: list[str] = Field(default_factory=list)
    required_owner_scope: dict[str, object] = Field(default_factory=dict)
    required_pre_action_facts: list[str] = Field(default_factory=list)
    mandatory_protection_mode: str = "single_tp_plus_sl"
    post_action_acceptance_outputs: list[str] = Field(default_factory=list)
    no_action_guarantee: dict[str, bool] = Field(
        default_factory=lambda: {
            "creates_authorization": False,
            "creates_execution_intent": False,
            "places_order": False,
            "starts_runtime": False,
            "mutates_pg": False,
        }
    )
    action_allowed: Literal[False] = False
    may_execute_live: Literal[False] = False
    frontend_action_enabled: Literal[False] = False


class GenericFinalGateAdapterContract(ProductionAdmissionModel):
    adapter_id: str = "generic_final_gate_adapter_contract"
    version: str = "brc_generic_action_final_gate_adapter_v0_1"
    input_contracts: list[str] = Field(
        default_factory=lambda: [
            "GenericActionSpec",
            "OwnerExecuteAuthorization",
            "PGExposureSnapshot",
            "ExchangeExposureSnapshot",
            "ProtectionPlan",
            "RecordingReadiness",
            "RuntimeGuardState",
        ]
    )
    required_pre_action_facts: list[str] = Field(
        default_factory=lambda: [
            "exact Owner execute authorization",
            "symbol/side/quantity/max_notional/leverage/max_attempts/protection_mode scope match",
            "PG and exchange exposure readable and non-conflicting",
            "valid mandatory TP/SL protection plan",
            "ExecutionIntent/order/review/audit recording readiness",
            "runtime/profile/env/credential guards pass",
        ]
    )
    warning_not_blocker: list[str] = Field(
        default_factory=lambda: [
            "weak strategy evidence",
            "fragile_evidence",
            "insufficient_research",
            "incomplete signal markers",
            "fee/funding/slippage gaps",
            "incomplete review UI",
            "non-core read-model degradation",
        ]
    )
    hard_blockers_for_live_action: list[str] = Field(
        default_factory=lambda: [
            "missing Owner execute authorization",
            "scope mismatch",
            "exposure unreadable or conflicting",
            "TP/SL plan unavailable",
            "intent/order/review/audit recording unavailable",
            "runtime/profile/env/credential guard blocks",
            "invalid GenericActionSpec",
        ]
    )
    output_contract: str = (
        "Final gate may return executable=true only through the official bounded "
        "Owner action path after all hard gates pass and evidence can be recorded."
    )
    live_action_policy: str = "fail_closed_until_official_final_gate_passes"
    may_execute_live: Literal[False] = False
    frontend_action_enabled: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False


class TradingConsoleActionEntryOutput(ProductionAdmissionModel):
    family: str
    strategy_family_id: Optional[str] = None
    carrier_id: Optional[str] = None
    admission_level: AdmissionLevelCode
    action_entry_state: Literal[
        "ready_for_owner_scope_final_gate",
        "proposal_only",
        "blocked",
    ]
    generic_action_spec_status: str
    final_gate_adapter_status: Literal["contract_ready_blocked_until_gate_passes"]
    action_registry_supported: bool
    required_owner_scope_fields: list[str] = Field(default_factory=list)
    warning_count: int
    hard_blocker_count: int
    owner_decision_text: str
    research_quality_status: ResearchRiskClassification = "warning"
    risk_disclosure_classifications: list[ResearchRiskClassification] = Field(
        default_factory=list
    )
    owner_risk_acceptance_required: bool = True
    owner_risk_acceptance_cannot_override_execution_safety_gates: bool = True
    may_execute_live: Literal[False] = False
    frontend_action_enabled: Literal[False] = False


class CandidatePipelineStandard(ProductionAdmissionModel):
    version: str = "brc_strategy_family_action_candidate_standard_v0_1"
    principle: str = (
        "Low-friction admission, medium-friction ActionCandidate, few hard execution "
        "gates, risk disclosure instead of over-blocking, and Review-driven iteration."
    )
    admission_levels: list[AdmissionLevelSpec] = Field(default_factory=list)
    warning_hard_blocker_policy: WarningHardBlockerPolicy = Field(
        default_factory=lambda: WarningHardBlockerPolicy(
            warning_items=[
                "weak strategy evidence",
                "fragile_evidence",
                "insufficient_research",
                "owner_risk_acceptance_required",
                "incomplete signal markers",
                "incomplete fee/funding/slippage",
                "incomplete review UI",
                "non-core read-model degradation",
            ],
            hard_blockers_for_live_action=[
                "missing Owner execute authorization",
                "scope mismatch",
                "exposure unreadable or conflicting",
                "TP/SL plan unavailable",
                "intent/order/review/audit recording unavailable",
                "runtime/profile/env/credential guard blocks",
                "Carrier cannot produce valid ActionCandidate",
            ],
            post_action_acceptance_outputs=[
                "ExecutionIntent",
                "Entry",
                "TP/SL",
                "Review",
                "Audit",
            ],
            policy_summary=(
                "Strategy weakness is disclosed as risk and can be accepted by Owner. "
                "Owner risk acceptance never overrides authorization, scope, exposure, "
                "protection, recording, guard, FinalGate, Operation Layer, or "
                "ActionCandidate validity failures."
            ),
        )
    )
    spec_order: list[str] = Field(
        default_factory=lambda: [
            "StrategyFamilySpec",
            "StrategyGroupSpec",
            "CarrierSpec",
            "RiskDisclosureSpec",
            "ReviewTemplate",
            "ActionCandidateSpec",
            "GenericActionSpec",
            "ActionEntryPayloadContract",
            "GenericFinalGateAdapterContract",
        ]
    )
    trading_console_output_contract: str = (
        "GET /api/trading-console/strategy-family-admission-state exposes the "
        "candidate/action-entry product backbone and official action handoff; "
        "the GET itself has no side effects."
    )
    official_action_path: list[str] = Field(default_factory=lambda: list(OFFICIAL_ACTION_API_ENDPOINTS.values()))
    no_action_guarantee: dict[str, bool] = Field(
        default_factory=lambda: {
            "creates_authorization": False,
            "creates_execution_intent": False,
            "places_order": False,
            "starts_runtime": False,
            "mutates_pg": False,
        }
    )


class BlockerRecord(ProductionAdmissionModel):
    id: str
    stage: str
    blocked_path: str
    evidence: str
    severity: Literal["hard_blocker", "warning", "deferred"]
    bridge_method: str
    next_retry_condition: str


class BridgeArtifactStatus(ProductionAdmissionModel):
    bridge_method: str
    status: Literal["present", "draft", "blocked", "mixed"]
    families: list[str] = Field(default_factory=list)
    row_statuses: dict[str, str] = Field(default_factory=dict)
    evidence: str
    next_retry_condition: str
    action_allowed: Literal[False] = False
    creates_authorization: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False


class AcceptanceEvidenceItem(ProductionAdmissionModel):
    item: str
    status: Literal["PASS", "PASS_WITH_CONSTRAINT", "DEFERRED", "BLOCKED"]
    families: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    blocker_ids: list[str] = Field(default_factory=list)
    next_retry_condition: str
    action_allowed: Literal[False] = False
    creates_authorization: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False


class ObjectiveAcceptanceAuditRow(ProductionAdmissionModel):
    requirement_id: str
    requirement: str
    status: Literal["PASS", "PASS_WITH_CONSTRAINT", "DEFERRED", "BLOCKED"]
    verification_scope: str
    completion_evidence: Literal[
        "proved_by_read_model_and_targeted_tests",
        "blocked_with_bridge_artifact",
        "deferred_by_scope",
    ]
    evidence_refs: list[str] = Field(default_factory=list)
    blocker_ids: list[str] = Field(default_factory=list)
    next_retry_condition: str
    action_allowed: Literal[False] = False
    creates_authorization: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    starts_runtime: Literal[False] = False
    starts_strategy_execution: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False
    exchange_write_action: Literal[False] = False


class ProductionBaselineContext(ProductionAdmissionModel):
    status: Literal["historical_bnb_context_not_action_permission"] = (
        "historical_bnb_context_not_action_permission"
    )
    source: Literal["current_repo_report_artifacts"] = "current_repo_report_artifacts"
    prior_scoped_carrier_id: Literal["MI-001-BNB-LONG"] = "MI-001-BNB-LONG"
    prior_symbol: Literal["BNB/USDT:USDT"] = "BNB/USDT:USDT"
    prior_side: Literal["LONG"] = "LONG"
    prior_quantity: Literal["0.01"] = "0.01"
    prior_live_evidence_status: str = (
        "owner_authorized_bnb_execute_and_closeout_evidence_present"
    )
    post_close_state_status: str = (
        "reported_flat_requires_fresh_pg_exchange_validation_before_new_action"
    )
    reuse_policy: str = (
        "Prior BNB one-shot execute/closeout evidence is historical context only "
        "and cannot authorize new Trend, Volatility expansion, or Mean reversion actions."
    )
    evidence_refs: list[str] = Field(
        default_factory=lambda: [
            "docs/ops/trading-console-backend-dependency-sync-v0.2.md#TC-BE-DEP-002-06",
            "reports/trading-console-bnb-close-2026-06-04/post-close-trading-console-snapshot.json",
            "reports/trading-console-server-deploy-acceptance-2026-06-04/completion-audit.md",
        ]
    )
    reusable_for_strategy_family_authorization: Literal[False] = False
    grants_execution_permission: Literal[False] = False
    grants_order_permission: Literal[False] = False
    frontend_action_enabled: Literal[False] = False
    requires_fresh_pre_action_pg_evidence: Literal[True] = True
    requires_fresh_pre_action_exchange_evidence: Literal[True] = True
    creates_authorization: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    starts_runtime: Literal[False] = False
    starts_strategy_execution: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False
    exchange_write_action: Literal[False] = False


class ReviewContract(ProductionAdmissionModel):
    status: Literal["draft_no_action_evidence"] = "draft_no_action_evidence"
    bridge_method: Literal["ReviewContract"] = "ReviewContract"
    required: bool = True
    family: Optional[str] = None
    metrics: list[str] = Field(default_factory=list)
    review_requirement: str = "post_action_review_required_before_promotion"
    required_evidence: list[str] = Field(
        default_factory=lambda: [
            "bounded_live_authorization",
            "execution_intent",
            "entry_order",
            "tp_sl_orders",
            "post_action_pg_snapshot",
            "post_action_exchange_snapshot",
            "audit_log_events",
        ]
    )
    missing_evidence: list[str] = Field(default_factory=list)
    promotion_allowed: Literal[False] = False
    records_review: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False


class RiskDisclosureDraft(ProductionAdmissionModel):
    status: Literal["draft_for_owner_review"] = "draft_for_owner_review"
    bridge_method: Literal["RiskDisclosureDraft"] = "RiskDisclosureDraft"
    family: str
    strategy_group: str
    summary: str
    failure_modes: list[str] = Field(default_factory=list)
    research_quality_status: ResearchRiskClassification = "warning"
    risk_disclosure_classifications: list[ResearchRiskClassification] = Field(
        default_factory=list
    )
    owner_acknowledgement_required: Literal[True] = True
    owner_risk_acceptance_required: Literal[True] = True
    acknowledgement_phrase: str = "I ACCEPT BOUNDED PRODUCTION RISK"
    owner_risk_acceptance_may_override: list[str] = Field(
        default_factory=lambda: list(OWNER_RISK_ACCEPTANCE_MAY_OVERRIDE)
    )
    owner_risk_acceptance_never_overrides: list[str] = Field(
        default_factory=lambda: list(OWNER_RISK_ACCEPTANCE_NEVER_OVERRIDES)
    )
    owner_risk_acceptance_cannot_override_execution_safety_gates: Literal[True] = True
    required_before_authorization: list[str] = Field(
        default_factory=lambda: [
            "Owner reviews risk disclosure",
            "Owner supplies complete bounded production scope",
            "Owner accepts mandatory TP/SL and post-action Review",
        ]
    )
    not_authorization: Literal[True] = True
    not_execution_permission: Literal[True] = True
    not_order_permission: Literal[True] = True


class StrategyGroupMappingProposal(ProductionAdmissionModel):
    status: Literal["mapped_proposal"] = "mapped_proposal"
    bridge_method: Literal["StrategyGroupMappingProposal"] = "StrategyGroupMappingProposal"
    family: str
    strategy_family_id: Optional[str] = None
    strategy_family_type: Optional[str] = None
    strategy_group: str
    carrier_id: Optional[str] = None
    admission_level: str
    classification: Literal["actionable", "dry-run-only", "blocked", "deferred"]
    evidence: str
    next_retry_condition: str
    creates_execution_intent: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False


class CarrierCandidate(ProductionAdmissionModel):
    status: Literal[
        "registered_metadata_only",
        "observation_candidate_only",
        "candidate_missing",
    ]
    bridge_method: Literal["CarrierCandidate"] = "CarrierCandidate"
    family: str
    strategy_family_id: Optional[str] = None
    carrier_id: Optional[str] = None
    carrier_status: Optional[str] = None
    supported_symbols: list[str] = Field(default_factory=list)
    primary_timeframe: Optional[str] = None
    context_timeframes: list[str] = Field(default_factory=list)
    source: str = "strategy_family_registry_seed"
    evidence: str
    research_quality_status: ResearchRiskClassification = "warning"
    risk_disclosure_classifications: list[ResearchRiskClassification] = Field(
        default_factory=list
    )
    owner_risk_acceptance_required: bool = True
    blockers: list[str] = Field(default_factory=list)
    next_retry_condition: str
    starts_runner: Literal[False] = False
    creates_signal: Literal[False] = False
    creates_trade_intent: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False


class CarrierReadinessReport(ProductionAdmissionModel):
    status: Literal[
        "observation_ready_not_actionable",
        "candidate_registered_not_actionable",
        "candidate_missing",
    ]
    bridge_method: Literal["CarrierReadinessReport"] = "CarrierReadinessReport"
    family: str
    carrier_id: Optional[str] = None
    carrier_status: Optional[str] = None
    classification: Literal["actionable", "dry-run-only", "blocked", "deferred"]
    supported_symbols: list[str] = Field(default_factory=list)
    primary_timeframe: Optional[str] = None
    context_timeframes: list[str] = Field(default_factory=list)
    readiness_checks: list[dict[str, str]] = Field(default_factory=list)
    research_quality_status: ResearchRiskClassification = "warning"
    risk_disclosure_classifications: list[ResearchRiskClassification] = Field(
        default_factory=list
    )
    owner_risk_acceptance_required: bool = True
    blockers: list[str] = Field(default_factory=list)
    next_retry_condition: str
    backend_actionable: Literal[False] = False
    frontend_action_enabled: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False


class ProtectionPlanDraft(ProductionAdmissionModel):
    status: Literal[
        "draft_required_mandatory_tp_sl",
        "scope_reviewed_draft_only",
    ] = "draft_required_mandatory_tp_sl"
    bridge_method: Literal["ProtectionPlanDraft"] = "ProtectionPlanDraft"
    mandatory: bool = True
    required_components: list[str] = Field(default_factory=lambda: ["TP", "SL"])
    scope: dict[str, object] = Field(default_factory=dict)
    validation_checks: list[dict[str, str]] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    unavailable_fields: dict[str, str] = Field(
        default_factory=lambda: {
            "take_profit_price": "not_fabricated_by_read_model",
            "stop_loss_price": "not_fabricated_by_read_model",
            "exchange_tp_order_id": "not_created_by_read_model",
            "exchange_sl_order_id": "not_created_by_read_model",
        }
    )
    next_retry_condition: str = (
        "Complete Owner scope, official action API support, backend final gate actionable=true, "
        "and validated TP/SL prices from official service."
    )
    not_executable_until_scope_complete: bool = True
    action_allowed: Literal[False] = False
    creates_order: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False


class BudgetEnvelopeDraft(ProductionAdmissionModel):
    status: Literal[
        "scope_incomplete_no_numbers_fabricated",
        "scope_complete_dry_run_only",
    ] = "scope_incomplete_no_numbers_fabricated"
    bridge_method: Literal["BudgetEnvelopeDraft"] = "BudgetEnvelopeDraft"
    required_scope_fields: list[str] = Field(default_factory=lambda: list(REQUIRED_OWNER_SCOPE_FIELDS))
    scope: dict[str, object] = Field(default_factory=dict)
    provided_scope_fields: list[str] = Field(default_factory=list)
    missing_scope_fields: list[str] = Field(default_factory=lambda: list(REQUIRED_OWNER_SCOPE_FIELDS))
    validation_checks: list[dict[str, str]] = Field(default_factory=list)
    symbol: Optional[str] = None
    side: Optional[str] = None
    quantity: Optional[str] = None
    target_notional_usdt: Optional[str] = None
    current_price: Optional[str] = None
    min_notional: Optional[str] = None
    min_qty: Optional[str] = None
    qty_step: Optional[str] = None
    price_tick: Optional[str] = None
    max_notional: Optional[str] = None
    leverage: Optional[str] = None
    max_attempts: Optional[int] = None
    protection_mode: Optional[str] = None
    review_requirement: Optional[str] = None
    numbers_source: Literal["owner_scope_only_no_fabrication"] = (
        "owner_scope_only_no_fabrication"
    )
    next_retry_condition: str = (
        "Owner supplies complete matched bounded production scope and backend final gate "
        "returns actionable=true through an official action path."
    )
    not_authorization: Literal[True] = True
    not_execution_permission: Literal[True] = True
    action_allowed: Literal[False] = False
    creates_authorization: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False


class ProductionCapitalBoundaryRow(ProductionAdmissionModel):
    family: str
    strategy_family_id: Optional[str] = None
    carrier_id: Optional[str] = None
    status: Literal["scope_required", "scope_reviewed_dry_run_only"]
    scope_review_verdict: str
    required_scope_fields: list[str] = Field(default_factory=list)
    provided_scope_fields: list[str] = Field(default_factory=list)
    missing_scope_fields: list[str] = Field(default_factory=list)
    supported_symbols: list[str] = Field(default_factory=list)
    requested_symbol: Optional[str] = None
    requested_side: Optional[str] = None
    requested_quantity: Optional[str] = None
    requested_max_notional: Optional[str] = None
    requested_leverage: Optional[str] = None
    requested_max_attempts: Optional[int] = None
    requested_protection_mode: Optional[str] = None
    requested_review_requirement: Optional[str] = None
    numbers_source: Literal["owner_scope_only_no_fabrication"] = (
        "owner_scope_only_no_fabrication"
    )
    boundary_policy: str = "No symbol/side/quantity/notional/leverage expansion beyond explicit Owner scope."
    next_retry_condition: str
    scope_expansion_allowed: Literal[False] = False
    symbol_expansion_allowed: Literal[False] = False
    side_expansion_allowed: Literal[False] = False
    quantity_expansion_allowed: Literal[False] = False
    notional_expansion_allowed: Literal[False] = False
    leverage_expansion_allowed: Literal[False] = False
    max_attempts_expansion_allowed: Literal[False] = False
    action_allowed: Literal[False] = False
    creates_authorization: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    starts_runtime: Literal[False] = False
    starts_strategy_execution: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False
    exchange_write_action: Literal[False] = False


class FinalGateDryRun(ProductionAdmissionModel):
    status: Literal["blocked"] = "blocked"
    reason: str = "production_scope_incomplete"
    gates: list[dict[str, str]] = Field(default_factory=list)
    creates_execution_intent: Literal[False] = False
    places_order: Literal[False] = False


class PreExecutionBlockedReview(ProductionAdmissionModel):
    status: Literal["blocked"] = "blocked"
    bridge_method: Literal["PreExecutionBlockedReview"] = "PreExecutionBlockedReview"
    family: Optional[str] = None
    carrier_id: Optional[str] = None
    blocked_reason: str
    checks: list[dict[str, str]] = Field(default_factory=list)
    blocking_stages: list[str] = Field(default_factory=list)
    unresolved_blocker_ids: list[str] = Field(default_factory=list)
    next_retry_conditions: list[str] = Field(default_factory=list)
    action_allowed: Literal[False] = False
    frontend_action_enabled: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False


class OfficialApiTransitionPlan(ProductionAdmissionModel):
    status: Literal["proposal_only"] = "proposal_only"
    read_only_review_endpoint: str = "GET /api/trading-console/strategy-family-admission-state"
    authorization_endpoint: str = "deferred_until_backend_action_contract"
    existing_action_endpoints: dict[str, str] = Field(
        default_factory=lambda: dict(OFFICIAL_ACTION_API_ENDPOINTS)
    )
    api_backed_authorization_endpoints: dict[str, str] = Field(
        default_factory=lambda: dict(API_BACKED_AUTHORIZATION_ENDPOINTS)
    )
    current_supported_carrier_ids: list[str] = Field(
        default_factory=lambda: list(CURRENT_OFFICIAL_ACTION_CARRIER_IDS)
    )
    creates_authorization: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    places_order: Literal[False] = False
    required_before_authorization: list[str] = Field(
        default_factory=lambda: [
            "complete Owner scope",
            "backend final gate actionable=true",
            "mandatory TP/SL plan",
            "pre-action PG evidence",
            "pre-action exchange evidence",
            "Owner confirmation phrase",
        ]
    )


class ApiBackedAuthorizationStep(ProductionAdmissionModel):
    order: int
    operation_type: str
    confirmation_phrase: str
    endpoint_preflight: str = "POST /api/brc/operations/preflight"
    endpoint_confirm: str = "POST /api/brc/operations/{operation_id}/confirm"
    result_scope: str
    creates_execution_intent: Literal[False] = False
    places_order: Literal[False] = False
    starts_strategy_execution: Literal[False] = False


class OfficialTransitionReadiness(ProductionAdmissionModel):
    order: int
    transition: str
    stage: str
    status: Literal["metadata_available", "proposal_only", "blocked"]
    endpoint: str
    required_refs: list[str] = Field(default_factory=list)
    evidence: str
    next_retry_condition: str
    owner_confirmation_required: bool = True
    action_allowed: Literal[False] = False
    creates_authorization: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    starts_runtime: Literal[False] = False
    starts_strategy_execution: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False


class ApiBackedAuthorizationFlow(ProductionAdmissionModel):
    status: Literal["operation_layer_metadata_flow_available"] = (
        "operation_layer_metadata_flow_available"
    )
    endpoints: dict[str, str] = Field(default_factory=lambda: dict(API_BACKED_AUTHORIZATION_ENDPOINTS))
    operation_steps: list[ApiBackedAuthorizationStep] = Field(
        default_factory=lambda: [
            ApiBackedAuthorizationStep(
                order=index,
                operation_type=operation_type,
                confirmation_phrase=confirmation_phrase,
                result_scope=result_scope,
            )
            for index, (operation_type, confirmation_phrase, result_scope) in enumerate(
                API_BACKED_AUTHORIZATION_OPERATION_CHAIN,
                start=1,
            )
        ]
    )
    frontend_action_enablement_source: Literal["backend_actionable_only"] = "backend_actionable_only"
    trading_console_direct_action_api: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    places_order: Literal[False] = False
    blockers: list[str] = Field(
        default_factory=lambda: [
            "candidate_admission_request_not_created_by_this_read_model",
            "owner_risk_acceptance_not_created_by_this_read_model",
            "operation_preflight_not_run_by_this_read_model",
            "operation_confirmation_not_submitted_by_this_read_model",
            "official_action_api_candidate_not_supported",
        ]
    )


class OfficialActionApiInventory(ProductionAdmissionModel):
    status: Literal["present_scoped_carriers"] = "present_scoped_carriers"
    owner_trial_flow_supported_carrier_ids: list[str] = Field(
        default_factory=lambda: list(CURRENT_OFFICIAL_ACTION_CARRIER_IDS)
    )
    owner_bounded_execution_supported_carrier_ids: list[str] = Field(
        default_factory=lambda: list(CURRENT_OFFICIAL_ACTION_CARRIER_IDS)
    )
    endpoints: dict[str, str] = Field(default_factory=lambda: dict(OFFICIAL_ACTION_API_ENDPOINTS))
    trading_console_action_api_exposed: Literal[False] = False


class CandidateActionApiCompatibility(ProductionAdmissionModel):
    status: Literal[
        "unsupported_by_current_official_action_api",
        "supported_by_current_official_action_api_but_not_actionable",
    ] = "unsupported_by_current_official_action_api"
    candidate_carrier_id: Optional[str] = None
    compatible: bool = False
    supported_owner_trial_flow_carrier_ids: list[str] = Field(
        default_factory=lambda: list(CURRENT_OFFICIAL_ACTION_CARRIER_IDS)
    )
    supported_execution_adapter_carrier_ids: list[str] = Field(
        default_factory=lambda: list(CURRENT_OFFICIAL_ACTION_CARRIER_IDS)
    )
    blockers: list[str] = Field(default_factory=list)


class ActionCandidate(ProductionAdmissionModel):
    status: Literal[
        "unsupported_by_current_official_action_api",
        "supported_but_backend_not_actionable",
    ] = "unsupported_by_current_official_action_api"
    bridge_method: Literal["ActionCandidate"] = "ActionCandidate"
    family: str
    carrier_id: Optional[str] = None
    candidate_carrier_id: Optional[str] = None
    supported_official_carrier_ids: list[str] = Field(
        default_factory=lambda: list(CURRENT_OFFICIAL_ACTION_CARRIER_IDS)
    )
    official_action_endpoints: dict[str, str] = Field(
        default_factory=lambda: dict(OFFICIAL_ACTION_API_ENDPOINTS)
    )
    research_quality_status: ResearchRiskClassification = "warning"
    risk_disclosure_classifications: list[ResearchRiskClassification] = Field(
        default_factory=list
    )
    owner_risk_acceptance_required: bool = True
    owner_risk_acceptance_may_override: list[str] = Field(
        default_factory=lambda: list(OWNER_RISK_ACCEPTANCE_MAY_OVERRIDE)
    )
    owner_risk_acceptance_never_overrides: list[str] = Field(
        default_factory=lambda: list(OWNER_RISK_ACCEPTANCE_NEVER_OVERRIDES)
    )
    required_before_action: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    next_retry_condition: str
    action_allowed: Literal[False] = False
    backend_actionable: Literal[False] = False
    frontend_action_enabled: Literal[False] = False
    creates_authorization: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False


class ChainStageState(ProductionAdmissionModel):
    stage: str
    status: str
    evidence: str
    bridge_method: Optional[str] = None
    blocker_id: Optional[str] = None
    creates_execution_intent: Literal[False] = False
    places_order: Literal[False] = False


class ObservationBridge(ProductionAdmissionModel):
    family: str
    bridge_method: Literal["TrendObservation", "CarrierReadinessReport", "CarrierCandidate"]
    status: Literal[
        "observation_bridge_only",
        "readiness_report_only",
        "candidate_metadata_only",
        "missing_candidate",
    ]
    source: str = "strategy_family_registry"
    supported_symbols: list[str] = Field(default_factory=list)
    timeframes: list[str] = Field(default_factory=list)
    evidence: str
    required_before_live_action: bool = True
    next_retry_condition: str
    starts_runner: Literal[False] = False
    creates_signal: Literal[False] = False
    creates_trade_intent: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False


class PrePostEvidenceContract(ProductionAdmissionModel):
    status: Literal["required_before_live_action_not_collected_by_read_model"] = (
        "required_before_live_action_not_collected_by_read_model"
    )
    pre_action_pg_tables: list[str] = Field(default_factory=lambda: list(PRE_POST_PG_TABLES))
    post_action_pg_tables: list[str] = Field(default_factory=lambda: list(PRE_POST_PG_TABLES))
    pre_action_exchange_reads: list[str] = Field(default_factory=lambda: list(PRE_POST_EXCHANGE_READS))
    post_action_exchange_reads: list[str] = Field(default_factory=lambda: list(PRE_POST_EXCHANGE_READS))
    audit_sources: list[str] = Field(
        default_factory=lambda: ["audit_logs", "campaign_events", "operation_results"]
    )
    review_required: Literal[True] = True
    live_action_evidence_present: Literal[False] = False
    mutation_allowed_by_read_model: Literal[False] = False
    collection_policy: str = "official_service_or_api_path_only_no_manual_pg_edits"


class AuditChainGapReport(ProductionAdmissionModel):
    status: Literal["gap_open_no_live_action_evidence"] = "gap_open_no_live_action_evidence"
    bridge_method: Literal["AuditChainGapReport"] = "AuditChainGapReport"
    family: Optional[str] = None
    carrier_id: Optional[str] = None
    required_chain: list[str] = Field(
        default_factory=lambda: [
            "AuthorizationDraft",
            "BoundedLiveAuthorization",
            "ExecutionIntent",
            "Entry",
            "TP/SL",
            "Review",
            "Audit",
        ]
    )
    present_evidence: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    audit_sources_required: list[str] = Field(
        default_factory=lambda: ["audit_logs", "campaign_events", "operation_results"]
    )
    reason: str = "No new live action was taken by this read model."
    next_retry_condition: str = (
        "Official action path records pre/post PG evidence, exchange evidence, execution intent, "
        "entry, TP/SL, review, and audit events."
    )
    live_action_evidence_present: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False


class ApiRequestDraft(ProductionAdmissionModel):
    name: str
    method: Literal["GET", "POST"]
    endpoint: str
    payload_template: dict[str, object] = Field(default_factory=dict)
    unresolved_refs: list[str] = Field(default_factory=list)
    required_before_submit: list[str] = Field(default_factory=list)
    not_submitted: Literal[True] = True
    creates_execution_intent: Literal[False] = False
    places_order: Literal[False] = False
    mutates_exchange: Literal[False] = False


class FamilyAdmissionVerdict(ProductionAdmissionModel):
    verdict: Literal[
        "dry_run_only_scope_required",
        "dry_run_only_scope_reviewed",
        "blocked_backend_final_gate",
        "blocked_scope_required",
        "blocked_candidate_mismatch",
    ]
    frontend_summary: str
    completed_stages: list[str] = Field(default_factory=list)
    blocked_stages: list[str] = Field(default_factory=list)
    remaining_requirements: list[str] = Field(default_factory=list)
    next_retry_conditions: list[str] = Field(default_factory=list)
    may_execute_live: Literal[False] = False
    frontend_action_enabled: Literal[False] = False


class FamilyCompletionSummary(ProductionAdmissionModel):
    family: str
    strategy_family_id: Optional[str] = None
    strategy_group: str
    carrier_id: Optional[str] = None
    classification: Literal["actionable", "dry-run-only", "blocked", "deferred"]
    completion_status: Literal["dry_run_only", "blocked", "deferred", "actionable"]
    admission_level: str
    completed_stages: list[str] = Field(default_factory=list)
    blocked_stages: list[str] = Field(default_factory=list)
    blocked_stage_statuses: dict[str, str] = Field(default_factory=dict)
    blocker_ids: list[str] = Field(default_factory=list)
    bridge_methods: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    next_retry_conditions: list[str] = Field(default_factory=list)
    backend_actionable: Literal[False] = False
    frontend_action_enabled: Literal[False] = False
    may_execute_live: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False


class AdmissionRiskControlSummary(ProductionAdmissionModel):
    family: str
    strategy_family_id: Optional[str] = None
    strategy_group: str
    carrier_id: Optional[str] = None
    admission_level: str
    classification: Literal["actionable", "dry-run-only", "blocked", "deferred"]
    scope_review_verdict: str
    risk_disclosure_status: str
    budget_envelope_status: str
    authorization_draft_status: str
    bounded_live_authorization_status: str
    action_api_status: str
    final_gate_status: str
    final_gate_reason: str
    protection_plan_status: str
    review_contract_status: str
    audit_chain_status: str
    blocker_ids: list[str] = Field(default_factory=list)
    next_retry_conditions: list[str] = Field(default_factory=list)
    backend_actionable: Literal[False] = False
    frontend_action_enabled: Literal[False] = False
    may_execute_live: Literal[False] = False
    action_allowed: Literal[False] = False
    creates_authorization: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    starts_runtime: Literal[False] = False
    starts_strategy_execution: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False


class FullChainEvidenceRow(ProductionAdmissionModel):
    family: str
    strategy_family_id: Optional[str] = None
    carrier_id: Optional[str] = None
    stage_order: int
    stage: str
    status: str
    bridge_method: Optional[str] = None
    evidence: str
    required_evidence_refs: list[str] = Field(default_factory=list)
    blocker_ids: list[str] = Field(default_factory=list)
    next_retry_conditions: list[str] = Field(default_factory=list)
    backend_actionable: Literal[False] = False
    frontend_action_enabled: Literal[False] = False
    may_execute_live: Literal[False] = False
    creates_authorization: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    starts_runtime: Literal[False] = False
    starts_strategy_execution: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False


class ProtectionReviewAuditSummary(ProductionAdmissionModel):
    family: str
    strategy_family_id: Optional[str] = None
    carrier_id: Optional[str] = None
    protection_status: str
    required_protection_components: list[str] = Field(default_factory=list)
    missing_protection_fields: list[str] = Field(default_factory=list)
    unavailable_protection_fields: dict[str, str] = Field(default_factory=dict)
    review_status: str
    review_required_evidence: list[str] = Field(default_factory=list)
    review_missing_evidence: list[str] = Field(default_factory=list)
    audit_status: str
    audit_present_evidence: list[str] = Field(default_factory=list)
    audit_missing_evidence: list[str] = Field(default_factory=list)
    audit_sources_required: list[str] = Field(default_factory=list)
    blocker_ids: list[str] = Field(default_factory=list)
    next_retry_conditions: list[str] = Field(default_factory=list)
    action_allowed: Literal[False] = False
    creates_order: Literal[False] = False
    records_review: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False


class BlockerRetryRow(ProductionAdmissionModel):
    family: str
    strategy_family_id: Optional[str] = None
    carrier_id: Optional[str] = None
    blocker_id: str
    stage: str
    blocked_path: str
    severity: Literal["hard_blocker", "warning", "deferred"]
    bridge_method: str
    evidence: str
    next_retry_condition: str
    retry_ready: Literal[False] = False
    retry_requires: list[str] = Field(default_factory=list)
    action_allowed: Literal[False] = False
    creates_authorization: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    starts_runtime: Literal[False] = False
    starts_strategy_execution: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False


class OwnerAuthorizationPacket(ProductionAdmissionModel):
    family: str
    strategy_family_id: Optional[str] = None
    carrier_id: Optional[str] = None
    status: Literal["scope_required", "scope_reviewed_dry_run_only"]
    owner_can_review: Literal[True] = True
    owner_scope_verdict: str
    risk_disclosure_status: str
    budget_envelope_status: str
    authorization_draft_status: str
    confirmation_phrase_required: str
    api_backed_flow_available: Literal[True] = True
    api_request_draft_names: list[str] = Field(default_factory=list)
    draft_endpoints: list[str] = Field(default_factory=list)
    unresolved_refs: list[str] = Field(default_factory=list)
    required_before_submit: list[str] = Field(default_factory=list)
    blocker_ids: list[str] = Field(default_factory=list)
    next_retry_conditions: list[str] = Field(default_factory=list)
    not_authorization: Literal[True] = True
    not_execution_permission: Literal[True] = True
    not_order_permission: Literal[True] = True
    creates_authorization: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    starts_runtime: Literal[False] = False
    starts_strategy_execution: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False


class OwnerReviewHandoffRow(ProductionAdmissionModel):
    family: str
    strategy_family_id: Optional[str] = None
    carrier_id: Optional[str] = None
    status: Literal["review_ready_scope_required", "review_ready_dry_run_only"]
    owner_can_review_risk_scope: Literal[True] = True
    owner_scope_verdict: str
    risk_disclosure_status: str
    risk_failure_modes: list[str] = Field(default_factory=list)
    budget_envelope_status: str
    authorization_draft_status: str
    confirmation_phrase_required: str
    read_only_review_endpoint: str = "GET /api/trading-console/strategy-family-admission-state"
    api_backed_authorization_status: Literal[
        "operation_layer_metadata_flow_available"
    ] = "operation_layer_metadata_flow_available"
    admission_request_endpoint: str = "POST /api/brc/admissions/requests"
    risk_acceptance_endpoint: str = "POST /api/brc/admissions/risk-acceptances"
    operation_preflight_endpoint: str = "POST /api/brc/operations/preflight"
    operation_confirm_endpoint: str = "POST /api/brc/operations/{operation_id}/confirm"
    operation_step_count: int
    first_operation_type: str
    last_operation_type: str
    draft_endpoints: list[str] = Field(default_factory=list)
    unresolved_refs: list[str] = Field(default_factory=list)
    required_before_submit: list[str] = Field(default_factory=list)
    blocker_ids: list[str] = Field(default_factory=list)
    next_retry_conditions: list[str] = Field(default_factory=list)
    frontend_action_enabled: Literal[False] = False
    action_enablement_source: Literal["backend_actionable_only"] = "backend_actionable_only"
    not_authorization: Literal[True] = True
    not_execution_permission: Literal[True] = True
    not_order_permission: Literal[True] = True
    read_model_submits_authorization: Literal[False] = False
    creates_authorization: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    starts_runtime: Literal[False] = False
    starts_strategy_execution: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False
    exchange_write_action: Literal[False] = False


class OfficialApiRequestDraftSummary(ProductionAdmissionModel):
    family: str
    strategy_family_id: Optional[str] = None
    carrier_id: Optional[str] = None
    draft_name: str
    method: Literal["GET", "POST"]
    endpoint: str
    status: Literal["proposal_only_not_submitted"] = "proposal_only_not_submitted"
    owner_scope_verdict: str
    unresolved_refs: list[str] = Field(default_factory=list)
    required_before_submit: list[str] = Field(default_factory=list)
    payload_template_keys: list[str] = Field(default_factory=list)
    not_submitted: Literal[True] = True
    action_allowed: Literal[False] = False
    creates_authorization: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    starts_runtime: Literal[False] = False
    starts_strategy_execution: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False
    mutates_exchange: Literal[False] = False


class LiveActionEligibilityCheck(ProductionAdmissionModel):
    code: str
    status: Literal[
        "pass",
        "block",
        "required_before_live_action",
        "draft_required",
        "not_created",
    ]
    evidence: str
    next_retry_condition: str


class LiveActionEligibilityRow(ProductionAdmissionModel):
    family: str
    strategy_family_id: Optional[str] = None
    carrier_id: Optional[str] = None
    eligibility: Literal["not_eligible"] = "not_eligible"
    decision: str
    checks: list[LiveActionEligibilityCheck] = Field(default_factory=list)
    blocker_ids: list[str] = Field(default_factory=list)
    next_retry_conditions: list[str] = Field(default_factory=list)
    backend_actionable: Literal[False] = False
    frontend_action_enabled: Literal[False] = False
    may_execute_live: Literal[False] = False
    creates_authorization: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    starts_runtime: Literal[False] = False
    starts_strategy_execution: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False


class FinalGateReadinessRow(ProductionAdmissionModel):
    family: str
    strategy_family_id: Optional[str] = None
    carrier_id: Optional[str] = None
    status: Literal["blocked"] = "blocked"
    readiness_level: Literal[
        "scope_required",
        "scope_reviewed_action_api_blocked",
        "scope_reviewed_backend_final_gate_blocked",
    ]
    final_gate_endpoint: str
    execute_endpoint: str
    final_gate_reason: str
    owner_scope_verdict: str
    checks: list[LiveActionEligibilityCheck] = Field(default_factory=list)
    blocking_stages: list[str] = Field(default_factory=list)
    blocker_ids: list[str] = Field(default_factory=list)
    next_retry_conditions: list[str] = Field(default_factory=list)
    backend_actionable: Literal[False] = False
    frontend_action_enabled: Literal[False] = False
    may_execute_live: Literal[False] = False
    creates_authorization: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    starts_runtime: Literal[False] = False
    starts_strategy_execution: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False
    exchange_write_action: Literal[False] = False


class ProductionActionDecisionRow(ProductionAdmissionModel):
    family: str
    strategy_family_id: Optional[str] = None
    carrier_id: Optional[str] = None
    decision: Literal["do_not_execute"] = "do_not_execute"
    selection_status: Literal["not_selected_for_live_action"] = "not_selected_for_live_action"
    reason: str
    owner_scope_verdict: str
    action_api_status: str
    final_gate_reason: str
    missing_evidence: list[str] = Field(default_factory=list)
    blocker_ids: list[str] = Field(default_factory=list)
    next_retry_conditions: list[str] = Field(default_factory=list)
    live_action_taken: Literal[False] = False
    backend_actionable: Literal[False] = False
    frontend_action_enabled: Literal[False] = False
    may_execute_live: Literal[False] = False
    creates_authorization: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    starts_runtime: Literal[False] = False
    starts_strategy_execution: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False
    exchange_write_action: Literal[False] = False


class AuthorizationDraftProposal(ProductionAdmissionModel):
    status: Literal[
        "scope_required",
        "scope_reviewed_dry_run_only",
    ] = "scope_required"
    confirmation_phrase_required: str = "I ACCEPT BOUNDED PRODUCTION RISK"
    scope: dict[str, object] = Field(default_factory=dict)
    risk_disclosure: str
    risk_disclosure_contract: Optional[RiskDisclosureDraft] = None
    budget_envelope: BudgetEnvelopeDraft = Field(default_factory=BudgetEnvelopeDraft)
    protection_plan: ProtectionPlanDraft = Field(default_factory=ProtectionPlanDraft)
    review_contract: ReviewContract = Field(default_factory=ReviewContract)
    official_api_transition_plan: OfficialApiTransitionPlan = Field(default_factory=OfficialApiTransitionPlan)
    not_authorization: Literal[True] = True
    not_execution_permission: Literal[True] = True
    not_order_permission: Literal[True] = True


class OwnerScopeDraft(ProductionAdmissionModel):
    family: Optional[str] = None
    strategy_family_id: Optional[str] = None
    carrier_id: Optional[str] = None
    symbol: Optional[str] = None
    side: Optional[str] = None
    quantity: Optional[str] = None
    target_notional_usdt: Optional[str] = None
    current_price: Optional[str] = None
    min_notional: Optional[str] = None
    min_qty: Optional[str] = None
    qty_step: Optional[str] = None
    price_tick: Optional[str] = None
    max_notional: Optional[str] = None
    leverage: Optional[str] = None
    max_attempts: Optional[int] = None
    protection_mode: Optional[str] = None
    review_requirement: Optional[str] = None


class ScopeReview(ProductionAdmissionModel):
    provided: bool = False
    target_family: Optional[str] = None
    target_strategy_family_id: Optional[str] = None
    target_carrier_id: Optional[str] = None
    complete: bool = False
    matched_candidate: bool = False
    missing_fields: list[str] = Field(default_factory=list)
    mismatches: list[str] = Field(default_factory=list)
    sanitized_scope: dict[str, object] = Field(default_factory=dict)
    verdict: Literal[
        "not_provided",
        "incomplete",
        "candidate_mismatch",
        "complete_dry_run_only",
    ] = "not_provided"
    actionability: Literal["disabled_until_backend_actionable"] = "disabled_until_backend_actionable"


class AdmissionContract(ProductionAdmissionModel):
    chain: list[str] = Field(default_factory=lambda: list(ADMISSION_CHAIN))
    required_owner_scope_fields: list[str] = Field(default_factory=lambda: list(REQUIRED_OWNER_SCOPE_FIELDS))
    backend_action_policy: str = "disabled unless a scoped backend final gate returns actionable=true"


class FamilyAdmissionRow(ProductionAdmissionModel):
    family: str
    strategy_family_id: Optional[str]
    strategy_family_type: Optional[str] = None
    strategy_group: str
    carrier_id: Optional[str]
    carrier_status: Optional[str] = None
    supported_symbols: list[str] = Field(default_factory=list)
    primary_timeframe: Optional[str] = None
    context_timeframes: list[str] = Field(default_factory=list)
    admission_level_code: AdmissionLevelCode = "L0"
    admission_level: str
    classification: Literal["actionable", "dry-run-only", "blocked", "deferred"]
    backend_actionable: bool = False
    frontend_action_enabled: bool = False
    required_scope_missing: list[str] = Field(default_factory=lambda: list(REQUIRED_OWNER_SCOPE_FIELDS))
    research_quality_status: ResearchRiskClassification = "warning"
    risk_disclosure_classifications: list[ResearchRiskClassification] = Field(
        default_factory=list
    )
    owner_risk_acceptance_required: bool = True
    owner_risk_acceptance_may_override: list[str] = Field(
        default_factory=lambda: list(OWNER_RISK_ACCEPTANCE_MAY_OVERRIDE)
    )
    owner_risk_acceptance_never_overrides: list[str] = Field(
        default_factory=lambda: list(OWNER_RISK_ACCEPTANCE_NEVER_OVERRIDES)
    )
    owner_risk_acceptance_cannot_override_execution_safety_gates: bool = True
    risk_disclosure_draft: str
    risk_disclosure_contract: RiskDisclosureDraft
    strategy_group_mapping: StrategyGroupMappingProposal
    carrier_candidate: CarrierCandidate
    carrier_readiness_report: CarrierReadinessReport
    authorization_draft_state: Literal["proposal_only"] = "proposal_only"
    bounded_live_authorization_state: Literal[
        "blocked_scope_incomplete",
        "blocked_candidate_action_api_unsupported",
        "blocked_backend_final_gate",
    ] = "blocked_scope_incomplete"
    execution_intent_state: Literal["not_created"] = "not_created"
    entry_state: Literal["not_executed"] = "not_executed"
    protection_plan_state: Literal["draft_required_mandatory_tp_sl"] = "draft_required_mandatory_tp_sl"
    protection_plan_draft: ProtectionPlanDraft = Field(default_factory=ProtectionPlanDraft)
    review_contract: ReviewContract = Field(default_factory=ReviewContract)
    budget_envelope_draft: BudgetEnvelopeDraft = Field(default_factory=BudgetEnvelopeDraft)
    authorization_draft_proposal: AuthorizationDraftProposal
    action_api_compatibility: CandidateActionApiCompatibility = Field(
        default_factory=CandidateActionApiCompatibility
    )
    action_candidate: ActionCandidate
    observation_bridge: ObservationBridge
    chain_stage_states: list[ChainStageState] = Field(default_factory=list)
    pre_post_evidence_contract: PrePostEvidenceContract = Field(default_factory=PrePostEvidenceContract)
    audit_chain_gap_report: AuditChainGapReport = Field(default_factory=AuditChainGapReport)
    gate_blocker_records: list[BlockerRecord] = Field(default_factory=list)
    api_request_drafts: list[ApiRequestDraft] = Field(default_factory=list)
    admission_verdict: Optional[FamilyAdmissionVerdict] = None
    final_gate_dry_run: FinalGateDryRun = Field(default_factory=FinalGateDryRun)
    pre_execution_blocked_review: PreExecutionBlockedReview
    audit_state: Literal["no_new_action_audit"] = "no_new_action_audit"
    blocker_record: BlockerRecord
    bridge_method: str
    next_retry_condition: str
    scope_review: ScopeReview = Field(default_factory=ScopeReview)


class TradingConsoleAuthorizationReadiness(ProductionAdmissionModel):
    status: Literal["pass_with_constraint"] = "pass_with_constraint"
    owner_can_review_risk_scope: bool = True
    api_backed_authorization_flow_available: str = "deferred_until_complete_scope"
    frontend_action_enabled: bool = False
    action_enablement_source: Literal["backend_actionable_only"] = "backend_actionable_only"
    current_authorization_state: dict = Field(default_factory=dict)


class PgExchangeEvidence(ProductionAdmissionModel):
    live_pg_mutation: bool = False
    exchange_write_action: bool = False
    evidence_level: Literal["repo_read_model_only"] = "repo_read_model_only"


class PgExchangeEvidenceItem(ProductionAdmissionModel):
    phase: Literal["pre_action", "post_action", "audit"]
    source_type: Literal["pg_table", "exchange_read", "audit_source"]
    source: str
    status: Literal["required_not_collected"] = "required_not_collected"
    collection_policy: str = "official_service_or_api_path_only_no_manual_pg_edits"
    evidence_ref: Optional[str] = None
    next_retry_condition: str
    read_only: Literal[True] = True
    mutates_pg: Literal[False] = False
    exchange_write_action: Literal[False] = False
    places_order: Literal[False] = False


class FamilyEvidenceRequirement(ProductionAdmissionModel):
    family: str
    strategy_family_id: Optional[str] = None
    carrier_id: Optional[str] = None
    phase: Literal["pre_action", "post_action", "audit"]
    required_for_stage: Literal["Entry", "Review"]
    source_type: Literal["pg_table", "exchange_read", "audit_source"]
    source: str
    status: Literal["required_not_collected"] = "required_not_collected"
    collection_policy: str = "official_service_or_api_path_only_no_manual_pg_edits"
    evidence_ref: Optional[str] = None
    official_collection_path: str
    next_retry_condition: str
    read_only: Literal[True] = True
    creates_authorization: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    exchange_write_action: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False


class EvidenceCollectionSummary(ProductionAdmissionModel):
    family: str
    strategy_family_id: Optional[str] = None
    carrier_id: Optional[str] = None
    status: Literal["blocked_required_not_collected"] = "blocked_required_not_collected"
    total_required: int
    collected_count: int = 0
    required_not_collected_count: int
    phase_counts: dict[str, int] = Field(default_factory=dict)
    source_type_counts: dict[str, int] = Field(default_factory=dict)
    official_collection_paths: list[str] = Field(default_factory=list)
    missing_sources: list[str] = Field(default_factory=list)
    collection_policy: str = "official_service_or_api_path_only_no_manual_pg_edits"
    next_retry_condition: str
    read_only: Literal[True] = True
    creates_authorization: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    exchange_write_action: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False


class ScopedDryRunExample(ProductionAdmissionModel):
    family: str
    strategy_family_id: str
    carrier_id: str
    strategy_group: str
    classification: Literal["actionable", "dry-run-only", "blocked", "deferred"]
    owner_scope_query: dict[str, object]
    expected_scope_verdict: Literal["complete_dry_run_only"] = "complete_dry_run_only"
    expected_authorization_draft_status: Literal["scope_reviewed_dry_run_only"] = (
        "scope_reviewed_dry_run_only"
    )
    expected_final_gate_reason: Literal[
        "official_action_api_candidate_not_supported",
        "backend_final_gate_requires_authorization_and_live_preflight",
    ] = "official_action_api_candidate_not_supported"
    expected_action_api_status: Literal[
        "unsupported_by_current_official_action_api",
        "supported_by_current_official_action_api_but_not_actionable",
    ] = "unsupported_by_current_official_action_api"
    expected_eligibility_decision: Literal[
        "scope_complete_but_candidate_action_api_unsupported",
        "scope_complete_but_backend_final_gate_blocked",
    ] = "scope_complete_but_candidate_action_api_unsupported"
    evidence: str
    next_retry_condition: str
    not_owner_authorization: Literal[True] = True
    action_allowed: Literal[False] = False
    creates_authorization: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    starts_runtime: Literal[False] = False
    starts_strategy_execution: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False


class SprintAcceptanceVerdict(ProductionAdmissionModel):
    status: Literal["in_progress_pass_with_constraint"] = "in_progress_pass_with_constraint"
    completed_family_count: int = 0
    dry_run_only_family_count: int = 0
    blocked_family_count: int = 0
    actionable_family_count: int = 0
    live_execution_ready: Literal[False] = False
    frontend_action_enabled: Literal[False] = False
    live_actions_taken: Literal[False] = False
    summary: str = (
        "Admission sprint has candidate/action-entry backbone artifacts; no candidate "
        "is live-executable until official authorization and FinalGate pass."
    )
    remaining_global_requirements: list[str] = Field(default_factory=list)


class FinalReportSection(ProductionAdmissionModel):
    section: str
    status: Literal["PASS", "PASS_WITH_CONSTRAINT", "DEFERRED", "BLOCKED"]
    evidence_refs: list[str] = Field(default_factory=list)
    blocker_refs: list[str] = Field(default_factory=list)


class FamilyFinalReportRow(ProductionAdmissionModel):
    family: str
    strategy_family_id: Optional[str] = None
    carrier_id: Optional[str] = None
    status: Literal["PASS_WITH_CONSTRAINT"] = "PASS_WITH_CONSTRAINT"
    completed_work_status: Literal["PASS_WITH_CONSTRAINT"] = "PASS_WITH_CONSTRAINT"
    strategy_group_carrier_mapping_status: Literal["PASS_WITH_CONSTRAINT"] = (
        "PASS_WITH_CONSTRAINT"
    )
    admission_risk_control_status: Literal["PASS_WITH_CONSTRAINT"] = "PASS_WITH_CONSTRAINT"
    trading_console_authorization_status: Literal["PASS_WITH_CONSTRAINT"] = (
        "PASS_WITH_CONSTRAINT"
    )
    live_action_status: Literal["BLOCKED"] = "BLOCKED"
    pg_exchange_evidence_status: Literal["BLOCKED"] = "BLOCKED"
    blocker_count: int
    bridge_methods: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    next_retry_conditions: list[str] = Field(default_factory=list)
    safety_flags: dict[str, bool] = Field(default_factory=dict)
    live_action_taken: Literal[False] = False
    runtime_started: Literal[False] = False
    backend_actionable: Literal[False] = False
    frontend_action_enabled: Literal[False] = False
    may_execute_live: Literal[False] = False
    creates_authorization: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    starts_strategy_execution: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False
    exchange_write_action: Literal[False] = False


class FinalReportPackage(ProductionAdmissionModel):
    status: Literal["PASS_WITH_CONSTRAINT"] = "PASS_WITH_CONSTRAINT"
    report_date: str = "2026-06-04"
    summary: str = (
        "Read-only/proposal admission package is available for Owner review; no "
        "strategy-family candidate is live-executable through the official action path."
    )
    sections: list[FinalReportSection] = Field(default_factory=list)
    required_validation_commands: list[str] = Field(default_factory=list)
    live_actions_taken: Literal[False] = False
    runtime_started: Literal[False] = False
    pg_mutation: Literal[False] = False
    exchange_write_action: Literal[False] = False
    credentials_changed: Literal[False] = False
    deploy_performed: Literal[False] = False
    push_performed: Literal[False] = False


class ProductionStrategyFamilyAdmissionState(ProductionAdmissionModel):
    generated_at_ms: int
    candidate_pipeline_standard: CandidatePipelineStandard = Field(
        default_factory=CandidatePipelineStandard
    )
    admission_contract: AdmissionContract = Field(default_factory=AdmissionContract)
    production_baseline_context: ProductionBaselineContext = Field(
        default_factory=ProductionBaselineContext
    )
    families: list[FamilyAdmissionRow]
    strategy_family_specs: list[StrategyFamilySpec] = Field(default_factory=list)
    strategy_group_specs: list[StrategyGroupSpec] = Field(default_factory=list)
    carrier_specs: list[CarrierSpec] = Field(default_factory=list)
    risk_disclosure_specs: list[RiskDisclosureSpec] = Field(default_factory=list)
    review_templates: list[ReviewTemplate] = Field(default_factory=list)
    protection_templates: list[ProtectionTemplateSpec] = Field(default_factory=list)
    warning_records: list[WarningRecord] = Field(default_factory=list)
    hard_blocker_records: list[BlockerRecord] = Field(default_factory=list)
    candidate_actionability: list[CandidateActionability] = Field(default_factory=list)
    final_gate_preview_inputs: list[FinalGatePreviewInputModel] = Field(default_factory=list)
    final_gate_adapter_results: list[ActionSpecFinalGateAdapterResult] = Field(default_factory=list)
    product_backbone: ProductBackboneReadModel = Field(default_factory=ProductBackboneReadModel)
    trading_console_candidate_action_read_model: TradingConsoleCandidateActionReadModel = Field(
        default_factory=TradingConsoleCandidateActionReadModel
    )
    action_candidate_specs: list[ActionCandidateSpec] = Field(default_factory=list)
    trading_console_candidate_output: list[TradingConsoleCandidateOutput] = Field(
        default_factory=list
    )
    generic_final_gate_adapter_contract: GenericFinalGateAdapterContract = Field(
        default_factory=GenericFinalGateAdapterContract
    )
    generic_action_specs: list[GenericActionSpec] = Field(default_factory=list)
    action_entry_payload_contracts: list[ActionEntryPayloadContract] = Field(
        default_factory=list
    )
    trading_console_action_entry_output: list[TradingConsoleActionEntryOutput] = Field(
        default_factory=list
    )
    family_completion_matrix: list[FamilyCompletionSummary] = Field(default_factory=list)
    admission_risk_control_matrix: list[AdmissionRiskControlSummary] = Field(default_factory=list)
    production_capital_boundary_matrix: list[ProductionCapitalBoundaryRow] = Field(
        default_factory=list
    )
    full_chain_evidence_matrix: list[FullChainEvidenceRow] = Field(default_factory=list)
    protection_review_audit_matrix: list[ProtectionReviewAuditSummary] = Field(
        default_factory=list
    )
    blocker_retry_matrix: list[BlockerRetryRow] = Field(default_factory=list)
    owner_authorization_packet_matrix: list[OwnerAuthorizationPacket] = Field(default_factory=list)
    owner_review_handoff_matrix: list[OwnerReviewHandoffRow] = Field(default_factory=list)
    official_api_request_draft_matrix: list[OfficialApiRequestDraftSummary] = Field(
        default_factory=list
    )
    live_action_eligibility_matrix: list[LiveActionEligibilityRow] = Field(default_factory=list)
    final_gate_readiness_matrix: list[FinalGateReadinessRow] = Field(default_factory=list)
    production_action_decision_matrix: list[ProductionActionDecisionRow] = Field(
        default_factory=list
    )
    classification_counts: dict[str, int]
    trading_console_authorization_readiness: TradingConsoleAuthorizationReadiness
    scope_review: ScopeReview = Field(default_factory=ScopeReview)
    bridge_artifacts: list[str] = Field(default_factory=lambda: list(BRIDGE_ARTIFACTS))
    bridge_artifact_statuses: list[BridgeArtifactStatus] = Field(default_factory=list)
    objective_acceptance_audit_matrix: list[ObjectiveAcceptanceAuditRow] = Field(
        default_factory=list
    )
    acceptance_evidence_matrix: list[AcceptanceEvidenceItem] = Field(default_factory=list)
    blocker_records: list[BlockerRecord]
    pre_execution_blocked_review: PreExecutionBlockedReview
    audit_chain_gap_report: AuditChainGapReport = Field(default_factory=AuditChainGapReport)
    live_actions_taken: list[dict] = Field(default_factory=list)
    pg_exchange_evidence: PgExchangeEvidence = Field(default_factory=PgExchangeEvidence)
    pg_exchange_evidence_matrix: list[PgExchangeEvidenceItem] = Field(default_factory=list)
    family_evidence_collection_matrix: list[FamilyEvidenceRequirement] = Field(
        default_factory=list
    )
    evidence_collection_summary_matrix: list[EvidenceCollectionSummary] = Field(
        default_factory=list
    )
    scoped_dry_run_examples: list[ScopedDryRunExample] = Field(default_factory=list)
    official_api_transition_plan: OfficialApiTransitionPlan = Field(default_factory=OfficialApiTransitionPlan)
    official_action_api_inventory: OfficialActionApiInventory = Field(default_factory=OfficialActionApiInventory)
    api_backed_authorization_flow: ApiBackedAuthorizationFlow = Field(
        default_factory=ApiBackedAuthorizationFlow
    )
    official_transition_readiness_matrix: list[OfficialTransitionReadiness] = Field(
        default_factory=list
    )
    sprint_acceptance_verdict: SprintAcceptanceVerdict = Field(default_factory=SprintAcceptanceVerdict)
    family_final_report_matrix: list[FamilyFinalReportRow] = Field(default_factory=list)
    final_report_package: FinalReportPackage = Field(default_factory=FinalReportPackage)


class _FamilyConfig(ProductionAdmissionModel):
    family_type: StrategyFamilyType
    family_label: str
    strategy_group: str
    classification: Literal["actionable", "dry-run-only", "blocked"]
    admission_level_code: AdmissionLevelCode
    admission_level: str
    risk_disclosure: str
    failure_modes: list[str] = Field(default_factory=list)
    research_quality_status: ResearchRiskClassification = "warning"
    risk_disclosure_classifications: list[ResearchRiskClassification] = Field(
        default_factory=list
    )
    blocker_id: str
    blocker_stage: str
    blocker_evidence: str
    bridge_method: str
    next_retry_condition: str


def build_production_strategy_family_admission_state(
    *,
    current_authorization_state: Optional[dict] = None,
    owner_scope: Optional[OwnerScopeDraft | dict] = None,
    now_ms: Optional[int] = None,
) -> ProductionStrategyFamilyAdmissionState:
    generated_at_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    seed = initial_strategy_family_registry_seed(now_ms=generated_at_ms)
    playbooks_by_family = {item.family_id: item for item in seed.playbooks}
    scope = (
        owner_scope
        if isinstance(owner_scope, OwnerScopeDraft)
        else OwnerScopeDraft.model_validate(owner_scope or {})
    )

    rows: list[FamilyAdmissionRow] = []
    for config in _family_configs():
        family = next((item for item in seed.families if item.family_type == config.family_type), None)
        if family is None:
            scope_review = _scope_review_for_missing_candidate(config=config, scope=scope)
            blocker = BlockerRecord(
                id=config.blocker_id,
                stage="StrategyFamily",
                blocked_path=f"{config.family_label} -> registry",
                evidence="Strategy family registry does not include a concrete candidate.",
                severity="hard_blocker",
                bridge_method="StrategyGroupMappingProposal",
                next_retry_condition="Registry seed includes a concrete candidate for this family.",
            )
            rows.append(
                FamilyAdmissionRow(
                    family=config.family_label,
                    strategy_family_id=None,
                    strategy_group=config.strategy_group,
                    carrier_id=None,
                    admission_level_code="L0",
                    admission_level="not_available",
                    classification="blocked",
                    research_quality_status=config.research_quality_status,
                    risk_disclosure_classifications=_risk_disclosure_classifications(config),
                    risk_disclosure_draft=config.risk_disclosure,
                    risk_disclosure_contract=_risk_disclosure_contract(config),
                    strategy_group_mapping=_strategy_group_mapping(
                        config=config,
                        family_id=None,
                        family_type=None,
                        carrier_id=None,
                    ),
                    carrier_candidate=_carrier_candidate(
                        config=config,
                        family_id=None,
                        carrier_id=None,
                        carrier_status=None,
                        supported_symbols=[],
                        primary_timeframe=None,
                        context_timeframes=[],
                    ),
                    carrier_readiness_report=_carrier_readiness_report(
                        config=config,
                        carrier_id=None,
                        carrier_status=None,
                        supported_symbols=[],
                        primary_timeframe=None,
                        context_timeframes=[],
                    ),
                    protection_plan_draft=_protection_plan_draft(scope_review=scope_review),
                    review_contract=_review_contract(
                        family_label=config.family_label,
                        metrics=[],
                    ),
                    authorization_draft_proposal=_authorization_draft_proposal(
                        scope_review=scope_review,
                        scope=scope,
                        risk_disclosure=config.risk_disclosure,
                        risk_disclosure_contract=_risk_disclosure_contract(config),
                        review_contract=_review_contract(
                            family_label=config.family_label,
                            metrics=[],
                        ),
                    ),
                    action_api_compatibility=_action_api_compatibility(None),
                    action_candidate=_action_candidate(
                        config=config,
                        carrier_id=None,
                        scope_review=scope_review,
                        action_api_compatibility=_action_api_compatibility(None),
                    ),
                    observation_bridge=_observation_bridge(
                        config=config,
                        family_id=None,
                        carrier_id=None,
                        supported_symbols=[],
                        timeframes=[],
                    ),
                    chain_stage_states=_chain_stage_states(
                        family_label=config.family_label,
                        family_id=None,
                        carrier_id=None,
                        classification="blocked",
                        scope_review=scope_review,
                        action_api_compatibility=_action_api_compatibility(None),
                        blocker=blocker,
                    ),
                    audit_chain_gap_report=_audit_chain_gap_report(
                        family_label=config.family_label,
                        carrier_id=None,
                    ),
                    gate_blocker_records=_gate_blocker_records(
                        config=config,
                        family_id=None,
                        carrier_id=None,
                        scope_review=scope_review,
                        action_api_compatibility=_action_api_compatibility(None),
                    ),
                    api_request_drafts=_api_request_drafts(
                        config=config,
                        family_id=None,
                        carrier_id=None,
                        supported_symbols=[],
                        timeframes=[],
                        scope_review=scope_review,
                    ),
                    admission_verdict=_admission_verdict(
                        classification="blocked",
                        scope_review=scope_review,
                        action_api_compatibility=_action_api_compatibility(None),
                        gate_blockers=_gate_blocker_records(
                            config=config,
                            family_id=None,
                            carrier_id=None,
                            scope_review=scope_review,
                            action_api_compatibility=_action_api_compatibility(None),
                        ),
                    ),
                    blocker_record=blocker,
                    bridge_method=blocker.bridge_method,
                    next_retry_condition=blocker.next_retry_condition,
                    final_gate_dry_run=_final_gate_dry_run(action_api_compatible=False),
                    pre_execution_blocked_review=_pre_execution_blocked_review(
                        family_label=config.family_label,
                        carrier_id=None,
                        scope_review=scope_review,
                        action_api_compatibility=_action_api_compatibility(None),
                        gate_blockers=_gate_blocker_records(
                            config=config,
                            family_id=None,
                            carrier_id=None,
                            scope_review=scope_review,
                            action_api_compatibility=_action_api_compatibility(None),
                        ),
                        final_gate_dry_run=_final_gate_dry_run(action_api_compatible=False),
                    ),
                    scope_review=scope_review,
                )
            )
            continue

        playbook = playbooks_by_family.get(family.family_id)
        carrier_id = playbook.playbook_id if playbook is not None else family.family_id
        action_api_compatibility = _action_api_compatibility(carrier_id)
        scope_review = _scope_review_for_candidate(
            family_label=config.family_label,
            family_id=family.family_id,
            carrier_id=carrier_id,
            supported_symbols=list(family.supported_symbols),
            scope=scope,
        )
        blocker = BlockerRecord(
            id=config.blocker_id,
            stage=config.blocker_stage,
            blocked_path=f"{config.family_label} -> {family.family_id} -> production entry",
            evidence=config.blocker_evidence,
            severity="hard_blocker",
            bridge_method=config.bridge_method,
            next_retry_condition=config.next_retry_condition,
        )
        rows.append(
            FamilyAdmissionRow(
                family=config.family_label,
                strategy_family_id=family.family_id,
                strategy_family_type=family.family_type.value,
                strategy_group=config.strategy_group,
                carrier_id=carrier_id,
                carrier_status=(
                    playbook.playbook_status.value if playbook is not None else family.status.value
                ),
                supported_symbols=list(family.supported_symbols),
                primary_timeframe=family.primary_timeframe,
                context_timeframes=list(family.context_timeframes),
                admission_level_code=config.admission_level_code,
                admission_level=config.admission_level,
                classification=config.classification,
                research_quality_status=config.research_quality_status,
                risk_disclosure_classifications=_risk_disclosure_classifications(config),
                bounded_live_authorization_state=_bounded_live_authorization_state(
                    scope_review=scope_review,
                    action_api_compatibility=action_api_compatibility,
                ),
                risk_disclosure_draft=config.risk_disclosure,
                risk_disclosure_contract=_risk_disclosure_contract(config),
                strategy_group_mapping=_strategy_group_mapping(
                    config=config,
                    family_id=family.family_id,
                    family_type=family.family_type.value,
                    carrier_id=carrier_id,
                ),
                carrier_candidate=_carrier_candidate(
                    config=config,
                    family_id=family.family_id,
                    carrier_id=carrier_id,
                    carrier_status=(
                        playbook.playbook_status.value if playbook is not None else family.status.value
                    ),
                    supported_symbols=list(family.supported_symbols),
                    primary_timeframe=family.primary_timeframe,
                    context_timeframes=list(family.context_timeframes),
                ),
                carrier_readiness_report=_carrier_readiness_report(
                    config=config,
                    carrier_id=carrier_id,
                    carrier_status=(
                        playbook.playbook_status.value if playbook is not None else family.status.value
                    ),
                    supported_symbols=list(family.supported_symbols),
                    primary_timeframe=family.primary_timeframe,
                    context_timeframes=list(family.context_timeframes),
                ),
                review_contract=_review_contract(
                    family_label=config.family_label,
                    metrics=list(family.review_metrics),
                ),
                protection_plan_draft=_protection_plan_draft(scope_review=scope_review),
                budget_envelope_draft=_budget_envelope_draft(scope_review=scope_review, scope=scope),
                authorization_draft_proposal=_authorization_draft_proposal(
                    scope_review=scope_review,
                    scope=scope,
                    risk_disclosure=config.risk_disclosure,
                    risk_disclosure_contract=_risk_disclosure_contract(config),
                    review_contract=_review_contract(
                        family_label=config.family_label,
                        metrics=list(family.review_metrics),
                    ),
                ),
                action_api_compatibility=action_api_compatibility,
                action_candidate=_action_candidate(
                    config=config,
                    carrier_id=carrier_id,
                    scope_review=scope_review,
                    action_api_compatibility=action_api_compatibility,
                ),
                observation_bridge=_observation_bridge(
                    config=config,
                    family_id=family.family_id,
                    carrier_id=carrier_id,
                    supported_symbols=list(family.supported_symbols),
                    timeframes=[family.primary_timeframe, *family.context_timeframes],
                ),
                chain_stage_states=_chain_stage_states(
                    family_label=config.family_label,
                    family_id=family.family_id,
                    carrier_id=carrier_id,
                    classification=config.classification,
                    scope_review=scope_review,
                    action_api_compatibility=action_api_compatibility,
                    blocker=blocker,
                ),
                audit_chain_gap_report=_audit_chain_gap_report(
                    family_label=config.family_label,
                    carrier_id=carrier_id,
                ),
                gate_blocker_records=_gate_blocker_records(
                    config=config,
                    family_id=family.family_id,
                    carrier_id=carrier_id,
                    scope_review=scope_review,
                    action_api_compatibility=action_api_compatibility,
                ),
                api_request_drafts=_api_request_drafts(
                    config=config,
                    family_id=family.family_id,
                    carrier_id=carrier_id,
                    supported_symbols=list(family.supported_symbols),
                    timeframes=[family.primary_timeframe, *family.context_timeframes],
                    scope_review=scope_review,
                ),
                admission_verdict=_admission_verdict(
                    classification=config.classification,
                    scope_review=scope_review,
                    action_api_compatibility=action_api_compatibility,
                    gate_blockers=_gate_blocker_records(
                        config=config,
                        family_id=family.family_id,
                        carrier_id=carrier_id,
                        scope_review=scope_review,
                        action_api_compatibility=action_api_compatibility,
                    ),
                ),
                final_gate_dry_run=_final_gate_dry_run(
                    scope_review=scope_review,
                    action_api_compatible=action_api_compatibility.compatible,
                ),
                pre_execution_blocked_review=_pre_execution_blocked_review(
                    family_label=config.family_label,
                    carrier_id=carrier_id,
                    scope_review=scope_review,
                    action_api_compatibility=action_api_compatibility,
                    gate_blockers=_gate_blocker_records(
                        config=config,
                        family_id=family.family_id,
                        carrier_id=carrier_id,
                        scope_review=scope_review,
                        action_api_compatibility=action_api_compatibility,
                    ),
                    final_gate_dry_run=_final_gate_dry_run(
                        scope_review=scope_review,
                        action_api_compatible=action_api_compatibility.compatible,
                    ),
                ),
                blocker_record=blocker,
                bridge_method=config.bridge_method,
                next_retry_condition=config.next_retry_condition,
                scope_review=scope_review,
            )
        )

    aggregate_scope_review = _aggregate_scope_review(rows)
    blocker_records = _aggregate_blocker_records(rows)

    return ProductionStrategyFamilyAdmissionState(
        generated_at_ms=generated_at_ms,
        candidate_pipeline_standard=_candidate_pipeline_standard(),
        families=rows,
        strategy_family_specs=_strategy_family_specs(rows),
        strategy_group_specs=_strategy_group_specs(rows),
        carrier_specs=_carrier_specs(rows),
        risk_disclosure_specs=_risk_disclosure_specs(rows),
        review_templates=_review_templates(rows),
        protection_templates=_protection_templates(rows),
        warning_records=_warning_records(rows),
        hard_blocker_records=blocker_records,
        candidate_actionability=_candidate_actionability(rows),
        final_gate_preview_inputs=_final_gate_preview_inputs(rows),
        final_gate_adapter_results=_final_gate_adapter_results(rows),
        product_backbone=_product_backbone(rows),
        trading_console_candidate_action_read_model=TradingConsoleCandidateActionReadModel(),
        action_candidate_specs=_action_candidate_specs(rows),
        trading_console_candidate_output=_trading_console_candidate_output(rows),
        generic_final_gate_adapter_contract=_generic_final_gate_adapter_contract(),
        generic_action_specs=_generic_action_specs(rows),
        action_entry_payload_contracts=_action_entry_payload_contracts(rows),
        trading_console_action_entry_output=_trading_console_action_entry_output(rows),
        family_completion_matrix=_family_completion_matrix(rows),
        admission_risk_control_matrix=_admission_risk_control_matrix(rows),
        production_capital_boundary_matrix=_production_capital_boundary_matrix(rows),
        full_chain_evidence_matrix=_full_chain_evidence_matrix(rows),
        protection_review_audit_matrix=_protection_review_audit_matrix(rows),
        blocker_retry_matrix=_blocker_retry_matrix(rows),
        owner_authorization_packet_matrix=_owner_authorization_packet_matrix(rows),
        owner_review_handoff_matrix=_owner_review_handoff_matrix(rows),
        official_api_request_draft_matrix=_official_api_request_draft_matrix(rows),
        live_action_eligibility_matrix=_live_action_eligibility_matrix(rows),
        final_gate_readiness_matrix=_final_gate_readiness_matrix(rows),
        production_action_decision_matrix=_production_action_decision_matrix(rows),
        classification_counts=_count_classifications(rows),
        trading_console_authorization_readiness=TradingConsoleAuthorizationReadiness(
            current_authorization_state=current_authorization_state or {}
        ),
        scope_review=aggregate_scope_review,
        bridge_artifact_statuses=_bridge_artifact_statuses(rows),
        objective_acceptance_audit_matrix=_objective_acceptance_audit_matrix(
            rows=rows,
            scope_review=aggregate_scope_review,
            blocker_records=blocker_records,
        ),
        acceptance_evidence_matrix=_acceptance_evidence_matrix(
            rows=rows,
            scope_review=aggregate_scope_review,
            blocker_records=blocker_records,
        ),
        blocker_records=blocker_records,
        pre_execution_blocked_review=_aggregate_pre_execution_blocked_review(rows),
        audit_chain_gap_report=_aggregate_audit_chain_gap_report(rows),
        pg_exchange_evidence_matrix=_pg_exchange_evidence_matrix(),
        family_evidence_collection_matrix=_family_evidence_collection_matrix(rows),
        evidence_collection_summary_matrix=_evidence_collection_summary_matrix(rows),
        scoped_dry_run_examples=_scoped_dry_run_examples(rows),
        official_transition_readiness_matrix=_official_transition_readiness_matrix(rows),
        sprint_acceptance_verdict=_sprint_acceptance_verdict(rows),
        family_final_report_matrix=_family_final_report_matrix(rows),
        final_report_package=_final_report_package(rows),
    )


def _sprint_acceptance_verdict(rows: list[FamilyAdmissionRow]) -> SprintAcceptanceVerdict:
    blocked = sum(1 for row in rows if row.classification == "blocked")
    dry_run = sum(1 for row in rows if row.classification == "dry-run-only")
    actionable = sum(1 for row in rows if row.classification == "actionable")
    remaining: list[str] = []
    for requirement in [
        "complete matched Owner scope for a supported candidate",
        "candidate supported by current official action API registry",
        "backend final gate actionable=true",
        "pre-action PG and exchange evidence collected",
        "valid mandatory TP/SL plan",
        "post-action Review contract ready",
    ]:
        if requirement not in remaining:
            remaining.append(requirement)
    return SprintAcceptanceVerdict(
        completed_family_count=0,
        dry_run_only_family_count=dry_run,
        blocked_family_count=blocked,
        actionable_family_count=actionable,
        remaining_global_requirements=remaining,
    )


def _family_final_report_matrix(rows: list[FamilyAdmissionRow]) -> list[FamilyFinalReportRow]:
    completion_by_family = {item.family: item for item in _family_completion_matrix(rows)}
    evidence_summary_by_family = {
        item.family: item for item in _evidence_collection_summary_matrix(rows)
    }
    decision_by_family = {
        item.family: item for item in _production_action_decision_matrix(rows)
    }
    matrix: list[FamilyFinalReportRow] = []
    for row in rows:
        completion = completion_by_family[row.family]
        evidence_summary = evidence_summary_by_family[row.family]
        decision = decision_by_family[row.family]
        blockers = _dedupe(
            [row.blocker_record.id, *[blocker.id for blocker in row.gate_blocker_records]]
        )
        next_retry_conditions = _dedupe(
            [
                *completion.next_retry_conditions,
                *decision.next_retry_conditions,
                evidence_summary.next_retry_condition,
            ]
        )
        matrix.append(
            FamilyFinalReportRow(
                family=row.family,
                strategy_family_id=row.strategy_family_id,
                carrier_id=row.carrier_id,
                blocker_count=len(blockers),
                bridge_methods=list(completion.bridge_methods),
                evidence_refs=[
                    f"family_completion_matrix:{row.family}",
                    f"admission_risk_control_matrix:{row.family}",
                    f"owner_authorization_packet_matrix:{row.family}",
                    f"owner_review_handoff_matrix:{row.family}",
                    f"production_action_decision_matrix:{row.family}",
                    f"evidence_collection_summary_matrix:{row.family}",
                    f"blocker_retry_matrix:{row.family}",
                ],
                next_retry_conditions=next_retry_conditions,
                safety_flags={
                    "live_action_taken": False,
                    "runtime_started": False,
                    "backend_actionable": False,
                    "frontend_action_enabled": False,
                    "places_order": False,
                    "mutates_pg": False,
                    "exchange_write_action": False,
                },
            )
        )
    return matrix


def _final_report_package(rows: list[FamilyAdmissionRow]) -> FinalReportPackage:
    families = [row.family for row in rows]
    hard_blockers = [
        blocker.id
        for row in rows
        for blocker in [row.blocker_record, *row.gate_blocker_records]
        if blocker.severity == "hard_blocker"
    ]
    family_refs = [f"{row.family}:{row.strategy_family_id}:{row.carrier_id}" for row in rows]
    sections = [
        FinalReportSection(
            section="completed_work_by_family",
            status="PASS_WITH_CONSTRAINT",
            evidence_refs=[
                "family_completion_matrix",
                "full_chain_evidence_matrix",
                "family_final_report_matrix",
                *family_refs,
            ],
            blocker_refs=hard_blockers,
        ),
        FinalReportSection(
            section="strategy_group_carrier_mappings",
            status="PASS_WITH_CONSTRAINT",
            evidence_refs=[
                "families[*].strategy_group_mapping",
                "families[*].carrier_candidate",
                "families[*].carrier_readiness_report",
            ],
            blocker_refs=[
                blocker.id
                for row in rows
                for blocker in row.gate_blocker_records
                if blocker.stage == "Carrier"
            ],
        ),
        FinalReportSection(
            section="admission_risk_control_changes",
            status="PASS_WITH_CONSTRAINT",
            evidence_refs=[
                "admission_risk_control_matrix",
                "production_capital_boundary_matrix",
                "owner_authorization_packet_matrix",
                "protection_review_audit_matrix",
            ],
            blocker_refs=hard_blockers,
        ),
        FinalReportSection(
            section="trading_console_authorization_readiness",
            status="PASS_WITH_CONSTRAINT",
            evidence_refs=[
                "trading_console_authorization_readiness",
                "owner_review_handoff_matrix",
                "api_backed_authorization_flow",
                "official_api_request_draft_matrix",
                "final_gate_readiness_matrix",
                "official_transition_readiness_matrix",
            ],
            blocker_refs=[
                blocker.id
                for row in rows
                for blocker in row.gate_blocker_records
                if blocker.stage == "BoundedLiveAuthorization"
            ],
        ),
        FinalReportSection(
            section="live_actions_taken",
            status="BLOCKED",
            evidence_refs=[
                "live_actions_taken=[]",
                "production_baseline_context",
                "production_action_decision_matrix",
                "sprint_acceptance_verdict.live_execution_ready=false",
            ],
            blocker_refs=hard_blockers,
        ),
        FinalReportSection(
            section="pg_exchange_evidence",
            status="BLOCKED",
            evidence_refs=[
                "pg_exchange_evidence_matrix",
                "family_evidence_collection_matrix",
                "evidence_collection_summary_matrix",
                "pg_exchange_evidence.evidence_level=repo_read_model_only",
            ],
            blocker_refs=[
                blocker.id
                for row in rows
                for blocker in row.gate_blocker_records
                if blocker.stage == "PreExecutionBlockedReview"
            ],
        ),
        FinalReportSection(
            section="blocker_records_and_bridge_artifacts",
            status="PASS_WITH_CONSTRAINT",
            evidence_refs=[
                "blocker_records",
                "blocker_retry_matrix",
                "bridge_artifact_statuses",
                "acceptance_evidence_matrix",
                "objective_acceptance_audit_matrix",
            ],
            blocker_refs=hard_blockers,
        ),
        FinalReportSection(
            section="tests_checks",
            status="PASS_WITH_CONSTRAINT",
            evidence_refs=[
                "required_validation_commands",
                "objective_acceptance_audit_matrix",
                "tests/unit/test_production_strategy_family_admission.py",
                "tests/unit/test_trading_console_readmodels.py",
                "tests/unit/test_strategy_family_registry.py",
            ],
            blocker_refs=[],
        ),
        FinalReportSection(
            section="next_retry_conditions",
            status="PASS_WITH_CONSTRAINT",
            evidence_refs=[
                "blocker_retry_matrix",
                "sprint_acceptance_verdict.remaining_global_requirements",
            ],
            blocker_refs=hard_blockers,
        ),
        FinalReportSection(
            section="safety_proof",
            status="PASS",
            evidence_refs=[
                "production_baseline_context",
                "final_report_package.live_actions_taken=false",
                "final_report_package.runtime_started=false",
                "final_report_package.pg_mutation=false",
                "final_report_package.exchange_write_action=false",
                "final_report_package.credentials_changed=false",
                "final_report_package.deploy_performed=false",
                "final_report_package.push_performed=false",
            ],
            blocker_refs=[],
        ),
    ]
    return FinalReportPackage(
        sections=sections,
        required_validation_commands=[
            "python3 -m py_compile src/application/production_strategy_family_admission.py src/application/readmodels/trading_console.py src/interfaces/api_trading_console.py src/domain/strategy_family_registry.py",
            "python3 -m pytest -q tests/unit/test_production_strategy_family_admission.py tests/unit/test_trading_console_readmodels.py tests/unit/test_strategy_family_registry.py",
            "python3 -m alembic heads",
            "git diff --check",
        ],
    )


def _pg_exchange_evidence_matrix() -> list[PgExchangeEvidenceItem]:
    rows: list[PgExchangeEvidenceItem] = []
    for phase in ("pre_action", "post_action"):
        for table in PRE_POST_PG_TABLES:
            rows.append(
                PgExchangeEvidenceItem(
                    phase=phase,
                    source_type="pg_table",
                    source=table,
                    next_retry_condition=(
                        f"Official action service records {phase} PG evidence for {table}."
                    ),
                )
            )
        for read_name in PRE_POST_EXCHANGE_READS:
            rows.append(
                PgExchangeEvidenceItem(
                    phase=phase,
                    source_type="exchange_read",
                    source=read_name,
                    next_retry_condition=(
                        f"Official action service records {phase} exchange read evidence for {read_name}."
                    ),
                )
            )
    for source in ("audit_logs", "campaign_events", "operation_results"):
        rows.append(
            PgExchangeEvidenceItem(
                phase="audit",
                source_type="audit_source",
                source=source,
                next_retry_condition=(
                    f"Official action/review flow records audit evidence in {source}."
                ),
            )
        )
    return rows


def _family_evidence_collection_matrix(
    rows: list[FamilyAdmissionRow],
) -> list[FamilyEvidenceRequirement]:
    matrix: list[FamilyEvidenceRequirement] = []
    for row in rows:
        for phase in ("pre_action", "post_action"):
            required_for_stage: Literal["Entry", "Review"] = (
                "Entry" if phase == "pre_action" else "Review"
            )
            for table in PRE_POST_PG_TABLES:
                matrix.append(
                    FamilyEvidenceRequirement(
                        family=row.family,
                        strategy_family_id=row.strategy_family_id,
                        carrier_id=row.carrier_id,
                        phase=phase,
                        required_for_stage=required_for_stage,
                        source_type="pg_table",
                        source=table,
                        official_collection_path=(
                            "official_action_service_pg_snapshot"
                        ),
                        next_retry_condition=(
                            f"Official action service records {phase} PG evidence for "
                            f"{row.family}/{table}."
                        ),
                    )
                )
            for read_name in PRE_POST_EXCHANGE_READS:
                matrix.append(
                    FamilyEvidenceRequirement(
                        family=row.family,
                        strategy_family_id=row.strategy_family_id,
                        carrier_id=row.carrier_id,
                        phase=phase,
                        required_for_stage=required_for_stage,
                        source_type="exchange_read",
                        source=read_name,
                        official_collection_path=(
                            "official_action_service_exchange_read_snapshot"
                        ),
                        next_retry_condition=(
                            f"Official action service records {phase} exchange read evidence "
                            f"for {row.family}/{read_name}."
                        ),
                    )
                )
        for source in ("audit_logs", "campaign_events", "operation_results"):
            matrix.append(
                FamilyEvidenceRequirement(
                    family=row.family,
                    strategy_family_id=row.strategy_family_id,
                    carrier_id=row.carrier_id,
                    phase="audit",
                    required_for_stage="Review",
                    source_type="audit_source",
                    source=source,
                    official_collection_path="official_action_review_audit_chain",
                    next_retry_condition=(
                        f"Official action/review flow records audit evidence for "
                        f"{row.family}/{source}."
                    ),
                )
            )
    return matrix


def _evidence_collection_summary_matrix(
    rows: list[FamilyAdmissionRow],
) -> list[EvidenceCollectionSummary]:
    detail_rows = _family_evidence_collection_matrix(rows)
    summaries: list[EvidenceCollectionSummary] = []
    for row in rows:
        family_rows = [item for item in detail_rows if item.family == row.family]
        phase_counts: dict[str, int] = {}
        source_type_counts: dict[str, int] = {}
        missing_sources: list[str] = []
        official_paths: list[str] = []
        for item in family_rows:
            phase_counts[item.phase] = phase_counts.get(item.phase, 0) + 1
            source_type_counts[item.source_type] = (
                source_type_counts.get(item.source_type, 0) + 1
            )
            missing_sources.append(f"{item.phase}:{item.source_type}:{item.source}")
            official_paths.append(item.official_collection_path)
        summaries.append(
            EvidenceCollectionSummary(
                family=row.family,
                strategy_family_id=row.strategy_family_id,
                carrier_id=row.carrier_id,
                total_required=len(family_rows),
                required_not_collected_count=sum(
                    1 for item in family_rows if item.status == "required_not_collected"
                ),
                phase_counts=phase_counts,
                source_type_counts=source_type_counts,
                official_collection_paths=_dedupe(official_paths),
                missing_sources=_dedupe(missing_sources),
                next_retry_condition=(
                    "Official action service records pre/post PG snapshots, exchange "
                    f"read snapshots, and audit evidence for {row.family}."
                ),
            )
        )
    return summaries


def _scoped_dry_run_examples(rows: list[FamilyAdmissionRow]) -> list[ScopedDryRunExample]:
    examples: list[ScopedDryRunExample] = []
    for row in rows:
        if not row.strategy_family_id or not row.carrier_id or not row.supported_symbols:
            continue
        carrier = get_owner_action_carrier(row.carrier_id)
        owner_scope_query: dict[str, object] = {
            "family": row.family,
            "strategy_family_id": row.strategy_family_id,
            "carrier_id": row.carrier_id,
            "symbol": carrier.runtime_symbol if carrier is not None else row.supported_symbols[0],
            "side": carrier.side if carrier is not None else "long",
            "quantity": str(carrier.quantity) if carrier is not None else "0.01",
            "max_notional": str(carrier.max_notional) if carrier is not None else "20",
            "leverage": str(carrier.leverage) if carrier is not None else "1",
            "max_attempts": 1,
            "protection_mode": "mandatory_tp_sl",
            "review_requirement": "post_action_review_required_before_promotion",
        }
        action_api_supported = row.action_api_compatibility.compatible
        examples.append(
            ScopedDryRunExample(
                family=row.family,
                strategy_family_id=row.strategy_family_id,
                carrier_id=row.carrier_id,
                strategy_group=row.strategy_group,
                classification=row.classification,
                owner_scope_query=owner_scope_query,
                expected_final_gate_reason=(
                    "backend_final_gate_requires_authorization_and_live_preflight"
                    if action_api_supported
                    else "official_action_api_candidate_not_supported"
                ),
                expected_action_api_status=row.action_api_compatibility.status,
                expected_eligibility_decision=(
                    "scope_complete_but_backend_final_gate_blocked"
                    if action_api_supported
                    else "scope_complete_but_candidate_action_api_unsupported"
                ),
                evidence=(
                    "Complete bounded Owner-scope query example for side-effect-free contract "
                    f"review of {row.family}; this is not an authorization."
                ),
                next_retry_condition=(
                    "Use this scope only to verify dry-run/proposal rendering until the "
                    "candidate is supported by an official action API and backend final "
                    "gate returns actionable=true."
                ),
            )
        )
    return examples


def _official_transition_readiness_matrix(
    rows: list[FamilyAdmissionRow],
) -> list[OfficialTransitionReadiness]:
    candidate_refs = [
        f"{row.family}:{row.strategy_family_id or 'missing'}:{row.carrier_id or 'missing'}"
        for row in rows
    ]
    matrix: list[OfficialTransitionReadiness] = [
        OfficialTransitionReadiness(
            order=1,
            transition="create_admission_request",
            stage="AuthorizationDraft",
            status="proposal_only",
            endpoint=API_BACKED_AUTHORIZATION_ENDPOINTS["create_admission_request"],
            required_refs=[
                "strategy_family_version_id",
                "evidence_packet_id",
                "owner_market_regime_input_id",
                "pre_action_account_facts_snapshot_ref",
                "playbook_id",
            ],
            evidence="Read model provides ApiRequestDraft payload templates only; no request is submitted.",
            next_retry_condition=(
                "Owner submits reviewed evidence/regime/admission request through official /api/brc/admissions API."
            ),
        ),
        OfficialTransitionReadiness(
            order=2,
            transition="create_owner_risk_acceptance",
            stage="RiskDisclosure",
            status="proposal_only",
            endpoint=API_BACKED_AUTHORIZATION_ENDPOINTS["create_owner_risk_acceptance"],
            required_refs=[
                "admission_request_id",
                "constraint_snapshot_id",
                "admission_decision_id",
                "owner_rationale",
            ],
            evidence="RiskDisclosureDraft is present; risk acceptance is not created by this read model.",
            next_retry_condition=(
                "Owner submits risk acceptance through official /api/brc/admissions/risk-acceptances."
            ),
        ),
    ]
    for index, (operation_type, confirmation_phrase, result_scope) in enumerate(
        API_BACKED_AUTHORIZATION_OPERATION_CHAIN,
        start=3,
    ):
        matrix.append(
            OfficialTransitionReadiness(
                order=index,
                transition=operation_type,
                stage="BoundedLiveAuthorization",
                status="metadata_available",
                endpoint=API_BACKED_AUTHORIZATION_ENDPOINTS["operation_preflight"],
                required_refs=[
                    "admission_decision_id",
                    "constraint_snapshot_id",
                    "owner_risk_acceptance_id",
                    "operation_confirmation",
                ],
                evidence=(
                    f"Operation Layer supports preflight/confirm for {operation_type}; "
                    f"confirmation phrase is {confirmation_phrase}; result scope is {result_scope}."
                ),
                next_retry_condition=(
                    "Owner submits Operation Layer preflight and confirmation through official API."
                ),
            )
        )
    final_gate_order = len(matrix) + 1
    matrix.extend(
        [
            OfficialTransitionReadiness(
                order=final_gate_order,
                transition="final_gate_dry_run",
                stage="ExecutionIntent",
                status="blocked",
                endpoint=OFFICIAL_ACTION_API_ENDPOINTS["final_gate_dry_run"],
                required_refs=[
                    "complete_matched_owner_scope",
                    "official_action_api_supported_candidate",
                    "pre_action_pg_snapshot",
                    "pre_action_exchange_snapshot",
                    "mandatory_tp_sl_plan",
                ],
                evidence=(
                    "FinalGateDryRun remains blocked for sprint candidates; candidate refs: "
                    + ", ".join(candidate_refs)
                ),
                next_retry_condition=(
                    "Backend final gate returns actionable=true for an official-action-supported candidate."
                ),
            ),
            OfficialTransitionReadiness(
                order=final_gate_order + 1,
                transition="execute_authorization",
                stage="Entry",
                status="blocked",
                endpoint=OFFICIAL_ACTION_API_ENDPOINTS["execute_authorization"],
                required_refs=[
                    "bounded_live_authorization",
                    "execution_intent",
                    "entry_order",
                    "tp_sl_orders",
                    "post_action_review",
                    "audit_log_events",
                ],
                evidence=(
                    "No sprint candidate is backend_actionable; no execution intent or order is created."
                ),
                next_retry_condition=(
                    "Official execution service records bounded authorization, intent, entry, TP/SL, Review, and audit."
                ),
            ),
        ]
    )
    return matrix


def _family_completion_matrix(rows: list[FamilyAdmissionRow]) -> list[FamilyCompletionSummary]:
    summaries: list[FamilyCompletionSummary] = []
    for row in rows:
        admission_verdict = row.admission_verdict
        completed = list(admission_verdict.completed_stages) if admission_verdict else []
        blocked = list(admission_verdict.blocked_stages) if admission_verdict else []
        stage_statuses = {stage.stage: stage.status for stage in row.chain_stage_states}
        blocked_stage_statuses = {
            stage: stage_statuses.get(stage, "blocked") for stage in blocked
        }
        completion_status: Literal["dry_run_only", "blocked", "deferred", "actionable"]
        if row.classification == "dry-run-only":
            completion_status = "dry_run_only"
        elif row.classification == "deferred":
            completion_status = "deferred"
        elif row.classification == "actionable":
            completion_status = "actionable"
        else:
            completion_status = "blocked"
        summaries.append(
            FamilyCompletionSummary(
                family=row.family,
                strategy_family_id=row.strategy_family_id,
                strategy_group=row.strategy_group,
                carrier_id=row.carrier_id,
                classification=row.classification,
                completion_status=completion_status,
                admission_level=row.admission_level,
                completed_stages=completed,
                blocked_stages=blocked,
                blocked_stage_statuses=blocked_stage_statuses,
                blocker_ids=_dedupe(
                    [
                        row.blocker_record.id,
                        *[blocker.id for blocker in row.gate_blocker_records],
                    ]
                ),
                bridge_methods=_dedupe(
                    [
                        row.strategy_group_mapping.bridge_method,
                        row.carrier_candidate.bridge_method,
                        row.carrier_readiness_report.bridge_method,
                        row.action_candidate.bridge_method,
                        row.risk_disclosure_contract.bridge_method,
                        row.authorization_draft_proposal.budget_envelope.bridge_method,
                        row.protection_plan_draft.bridge_method,
                        row.review_contract.bridge_method,
                        row.final_gate_dry_run.__class__.__name__,
                        row.pre_execution_blocked_review.bridge_method,
                        row.audit_chain_gap_report.bridge_method,
                    ]
                ),
                evidence_refs=[
                    f"classification={row.classification}",
                    f"scope_review={row.scope_review.verdict}",
                    f"action_api={row.action_api_compatibility.status}",
                    f"final_gate={row.final_gate_dry_run.reason}",
                    f"protection={row.protection_plan_draft.status}",
                    f"review={row.review_contract.status}",
                    f"audit={row.audit_chain_gap_report.status}",
                ],
                next_retry_conditions=(
                    list(admission_verdict.next_retry_conditions)
                    if admission_verdict
                    else [row.next_retry_condition]
                ),
            )
        )
    return summaries


def _admission_risk_control_matrix(
    rows: list[FamilyAdmissionRow],
) -> list[AdmissionRiskControlSummary]:
    matrix: list[AdmissionRiskControlSummary] = []
    for row in rows:
        blocker_ids = _dedupe(
            [row.blocker_record.id, *[blocker.id for blocker in row.gate_blocker_records]]
        )
        next_retry_conditions = _dedupe(
            [
                row.next_retry_condition,
                row.authorization_draft_proposal.budget_envelope.next_retry_condition,
                row.protection_plan_draft.next_retry_condition,
                row.review_contract.review_requirement,
                row.final_gate_dry_run.reason,
                row.audit_chain_gap_report.next_retry_condition,
                *[blocker.next_retry_condition for blocker in row.gate_blocker_records],
            ]
        )
        matrix.append(
            AdmissionRiskControlSummary(
                family=row.family,
                strategy_family_id=row.strategy_family_id,
                strategy_group=row.strategy_group,
                carrier_id=row.carrier_id,
                admission_level=row.admission_level,
                classification=row.classification,
                scope_review_verdict=row.scope_review.verdict,
                risk_disclosure_status=row.risk_disclosure_contract.status,
                budget_envelope_status=row.budget_envelope_draft.status,
                authorization_draft_status=row.authorization_draft_proposal.status,
                bounded_live_authorization_status=row.bounded_live_authorization_state,
                action_api_status=row.action_api_compatibility.status,
                final_gate_status=row.final_gate_dry_run.status,
                final_gate_reason=row.final_gate_dry_run.reason,
                protection_plan_status=row.protection_plan_draft.status,
                review_contract_status=row.review_contract.status,
                audit_chain_status=row.audit_chain_gap_report.status,
                blocker_ids=blocker_ids,
                next_retry_conditions=next_retry_conditions,
            )
        )
    return matrix


def _production_capital_boundary_matrix(
    rows: list[FamilyAdmissionRow],
) -> list[ProductionCapitalBoundaryRow]:
    matrix: list[ProductionCapitalBoundaryRow] = []
    for row in rows:
        budget = row.budget_envelope_draft
        status: Literal["scope_required", "scope_reviewed_dry_run_only"] = (
            "scope_reviewed_dry_run_only"
            if budget.status == "scope_complete_dry_run_only"
            else "scope_required"
        )
        matrix.append(
            ProductionCapitalBoundaryRow(
                family=row.family,
                strategy_family_id=row.strategy_family_id,
                carrier_id=row.carrier_id,
                status=status,
                scope_review_verdict=row.scope_review.verdict,
                required_scope_fields=list(budget.required_scope_fields),
                provided_scope_fields=list(budget.provided_scope_fields),
                missing_scope_fields=list(budget.missing_scope_fields),
                supported_symbols=list(row.supported_symbols),
                requested_symbol=budget.symbol,
                requested_side=budget.side,
                requested_quantity=budget.quantity,
                requested_max_notional=budget.max_notional,
                requested_leverage=budget.leverage,
                requested_max_attempts=budget.max_attempts,
                requested_protection_mode=budget.protection_mode,
                requested_review_requirement=budget.review_requirement,
                next_retry_condition=budget.next_retry_condition,
            )
        )
    return matrix


def _bounded_live_authorization_state(
    *,
    scope_review: ScopeReview,
    action_api_compatibility: CandidateActionApiCompatibility,
) -> Literal[
    "blocked_scope_incomplete",
    "blocked_candidate_action_api_unsupported",
    "blocked_backend_final_gate",
]:
    if scope_review.verdict != "complete_dry_run_only":
        return "blocked_scope_incomplete"
    if not action_api_compatibility.compatible:
        return "blocked_candidate_action_api_unsupported"
    return "blocked_backend_final_gate"


def _full_chain_evidence_matrix(rows: list[FamilyAdmissionRow]) -> list[FullChainEvidenceRow]:
    matrix: list[FullChainEvidenceRow] = []
    for row in rows:
        blockers_by_stage: dict[str, list[BlockerRecord]] = {}
        for blocker in [row.blocker_record, *row.gate_blocker_records]:
            blockers_by_stage.setdefault(blocker.stage, []).append(blocker)
        for order, stage_state in enumerate(row.chain_stage_states, start=1):
            related_blockers = _blockers_for_chain_stage(
                stage=stage_state.stage,
                direct_blocker_id=stage_state.blocker_id,
                blockers_by_stage=blockers_by_stage,
            )
            matrix.append(
                FullChainEvidenceRow(
                    family=row.family,
                    strategy_family_id=row.strategy_family_id,
                    carrier_id=row.carrier_id,
                    stage_order=order,
                    stage=stage_state.stage,
                    status=stage_state.status,
                    bridge_method=stage_state.bridge_method,
                    evidence=stage_state.evidence,
                    required_evidence_refs=_required_evidence_refs_for_stage(stage_state.stage),
                    blocker_ids=_dedupe([blocker.id for blocker in related_blockers]),
                    next_retry_conditions=_dedupe(
                        [blocker.next_retry_condition for blocker in related_blockers]
                    ),
                )
            )
    return matrix


def _blockers_for_chain_stage(
    *,
    stage: str,
    direct_blocker_id: Optional[str],
    blockers_by_stage: dict[str, list[BlockerRecord]],
) -> list[BlockerRecord]:
    related: list[BlockerRecord] = []
    related.extend(blockers_by_stage.get(stage, []))
    if stage in {"ExecutionIntent", "Entry"}:
        related.extend(blockers_by_stage.get("PreExecutionBlockedReview", []))
    if stage == "BoundedLiveAuthorization":
        related.extend(blockers_by_stage.get("ExecutionIntent", []))
    if direct_blocker_id:
        for blockers in blockers_by_stage.values():
            related.extend(blocker for blocker in blockers if blocker.id == direct_blocker_id)
    deduped: dict[str, BlockerRecord] = {}
    for blocker in related:
        deduped[blocker.id] = blocker
    return list(deduped.values())


def _required_evidence_refs_for_stage(stage: str) -> list[str]:
    refs_by_stage = {
        "StrategyFamily": [
            "strategy_family_registry_seed",
            "strategy_family_type",
        ],
        "StrategyGroup": [
            "strategy_group_mapping",
            "strategy_family_id",
        ],
        "Carrier": [
            "carrier_candidate",
            "carrier_readiness_report",
            "official_action_api_compatibility",
        ],
        "RiskDisclosure": [
            "risk_disclosure_contract",
            "owner_acknowledgement_context",
        ],
        "AuthorizationDraft": [
            "complete_owner_scope",
            "budget_envelope_draft",
            "authorization_draft_proposal",
        ],
        "BoundedLiveAuthorization": [
            "official_action_api_supported_candidate",
            "backend_final_gate_actionable_true",
            "operation_layer_confirmation",
        ],
        "ExecutionIntent": [
            "bounded_live_authorization",
            "execution_intent",
            "pre_execution_blocked_review",
        ],
        "Entry": [
            "pre_action_pg_snapshot",
            "pre_action_exchange_snapshot",
            "entry_order",
        ],
        "TP/SL": [
            "mandatory_tp_sl_plan",
            "exchange_tp_order",
            "exchange_sl_order",
        ],
        "Review": [
            "post_action_pg_snapshot",
            "post_action_exchange_snapshot",
            "post_action_review",
            "audit_log_events",
        ],
    }
    return list(refs_by_stage.get(stage, []))


def _protection_review_audit_matrix(
    rows: list[FamilyAdmissionRow],
) -> list[ProtectionReviewAuditSummary]:
    matrix: list[ProtectionReviewAuditSummary] = []
    for row in rows:
        blocker_ids = _dedupe(
            [
                row.blocker_record.id,
                *[
                    blocker.id
                    for blocker in row.gate_blocker_records
                    if blocker.stage in {"TP/SL", "Review"}
                    or blocker.bridge_method in {"ProtectionPlanDraft", "ReviewContract"}
                ],
            ]
        )
        next_retry_conditions = _dedupe(
            [
                row.protection_plan_draft.next_retry_condition,
                row.review_contract.review_requirement,
                row.audit_chain_gap_report.next_retry_condition,
                *[
                    blocker.next_retry_condition
                    for blocker in row.gate_blocker_records
                    if blocker.stage in {"TP/SL", "Review"}
                    or blocker.bridge_method in {"ProtectionPlanDraft", "ReviewContract"}
                ],
            ]
        )
        matrix.append(
            ProtectionReviewAuditSummary(
                family=row.family,
                strategy_family_id=row.strategy_family_id,
                carrier_id=row.carrier_id,
                protection_status=row.protection_plan_draft.status,
                required_protection_components=list(
                    row.protection_plan_draft.required_components
                ),
                missing_protection_fields=list(row.protection_plan_draft.missing_fields),
                unavailable_protection_fields=dict(
                    row.protection_plan_draft.unavailable_fields
                ),
                review_status=row.review_contract.status,
                review_required_evidence=list(row.review_contract.required_evidence),
                review_missing_evidence=list(row.review_contract.missing_evidence),
                audit_status=row.audit_chain_gap_report.status,
                audit_present_evidence=list(row.audit_chain_gap_report.present_evidence),
                audit_missing_evidence=list(row.audit_chain_gap_report.missing_evidence),
                audit_sources_required=list(
                    row.audit_chain_gap_report.audit_sources_required
                ),
                blocker_ids=blocker_ids,
                next_retry_conditions=next_retry_conditions,
            )
        )
    return matrix


def _blocker_retry_matrix(rows: list[FamilyAdmissionRow]) -> list[BlockerRetryRow]:
    matrix: list[BlockerRetryRow] = []
    for row in rows:
        family_blockers = [row.blocker_record, *row.gate_blocker_records]
        seen: set[str] = set()
        for blocker in family_blockers:
            if blocker.id in seen:
                continue
            seen.add(blocker.id)
            matrix.append(
                BlockerRetryRow(
                    family=row.family,
                    strategy_family_id=row.strategy_family_id,
                    carrier_id=row.carrier_id,
                    blocker_id=blocker.id,
                    stage=blocker.stage,
                    blocked_path=blocker.blocked_path,
                    severity=blocker.severity,
                    bridge_method=blocker.bridge_method,
                    evidence=blocker.evidence,
                    next_retry_condition=blocker.next_retry_condition,
                    retry_requires=_retry_requires_for_bridge_method(blocker.bridge_method),
                )
            )
    return matrix


def _retry_requires_for_bridge_method(bridge_method: str) -> list[str]:
    requirements_by_bridge = {
        "TrendObservation": [
            "Owner reviews trend observation",
            "official action API supports the scoped candidate",
            "backend final gate returns actionable=true",
        ],
        "StrategyGroupMappingProposal": [
            "strategy-family candidate exists",
            "strategy group mapping approved",
        ],
        "CarrierCandidate": [
            "concrete carrier candidate exists",
            "candidate has readiness evidence",
            "official action API supports the carrier",
        ],
        "CarrierReadinessReport": [
            "runner/evaluator readiness evidence exists",
            "supported symbol/timeframe evidence exists",
            "backend actionability source is available",
        ],
        "ActionCandidate": [
            "official Owner trial-flow registry supports candidate carrier",
            "bounded execution registry supports candidate carrier",
        ],
        "RiskDisclosureDraft": [
            "Owner reviews risk disclosure",
            "Owner acknowledgement is recorded through official API",
        ],
        "AuthorizationDraftProposal": [
            "complete matched Owner scope",
            "Owner risk acceptance through official API",
            "Operation Layer preflight/confirmation refs resolved",
        ],
        "BudgetEnvelopeDraft": [
            "symbol/side/quantity/max_notional/leverage/max_attempts provided",
            "protection_mode and review_requirement provided",
        ],
        "FinalGateDryRun": [
            "backend final gate returns actionable=true",
            "pre-action PG/exchange evidence exists",
            "mandatory TP/SL plan is validated",
        ],
        "PreExecutionBlockedReview": [
            "pre-action PG snapshot exists",
            "pre-action exchange snapshot exists",
            "execution-intent gate is clear",
        ],
        "ProtectionPlanDraft": [
            "take_profit_price defined by official service",
            "stop_loss_price defined by official service",
            "TP/SL order plan validated",
        ],
        "ReviewContract": [
            "bounded authorization exists",
            "execution intent and entry order evidence exist",
            "TP/SL order evidence exists",
            "post-action PG/exchange evidence exists",
        ],
        "AuditChainGapReport": [
            "audit log events exist",
            "campaign events exist",
            "operation results exist",
            "post-action review is recorded",
        ],
    }
    return list(requirements_by_bridge.get(bridge_method, ["official evidence exists"]))


def _owner_authorization_packet_matrix(
    rows: list[FamilyAdmissionRow],
) -> list[OwnerAuthorizationPacket]:
    matrix: list[OwnerAuthorizationPacket] = []
    for row in rows:
        unresolved_refs = _dedupe(
            [ref for draft in row.api_request_drafts for ref in draft.unresolved_refs]
        )
        required_before_submit = _dedupe(
            [
                requirement
                for draft in row.api_request_drafts
                for requirement in draft.required_before_submit
            ]
        )
        blocker_ids = _dedupe(
            [row.blocker_record.id, *[blocker.id for blocker in row.gate_blocker_records]]
        )
        next_retry_conditions = _dedupe(
            [
                row.next_retry_condition,
                row.authorization_draft_proposal.budget_envelope.next_retry_condition,
                *[blocker.next_retry_condition for blocker in row.gate_blocker_records],
            ]
        )
        matrix.append(
            OwnerAuthorizationPacket(
                family=row.family,
                strategy_family_id=row.strategy_family_id,
                carrier_id=row.carrier_id,
                status=row.authorization_draft_proposal.status,
                owner_scope_verdict=row.scope_review.verdict,
                risk_disclosure_status=row.risk_disclosure_contract.status,
                budget_envelope_status=row.budget_envelope_draft.status,
                authorization_draft_status=row.authorization_draft_proposal.status,
                confirmation_phrase_required=(
                    row.authorization_draft_proposal.confirmation_phrase_required
                ),
                api_request_draft_names=[draft.name for draft in row.api_request_drafts],
                draft_endpoints=[draft.endpoint for draft in row.api_request_drafts],
                unresolved_refs=unresolved_refs,
                required_before_submit=required_before_submit,
                blocker_ids=blocker_ids,
                next_retry_conditions=next_retry_conditions,
            )
        )
    return matrix


def _owner_review_handoff_matrix(
    rows: list[FamilyAdmissionRow],
) -> list[OwnerReviewHandoffRow]:
    matrix: list[OwnerReviewHandoffRow] = []
    first_operation_type = API_BACKED_AUTHORIZATION_OPERATION_CHAIN[0][0]
    last_operation_type = API_BACKED_AUTHORIZATION_OPERATION_CHAIN[-1][0]
    operation_step_count = len(API_BACKED_AUTHORIZATION_OPERATION_CHAIN)
    for row in rows:
        unresolved_refs = _dedupe(
            [ref for draft in row.api_request_drafts for ref in draft.unresolved_refs]
        )
        required_before_submit = _dedupe(
            [
                requirement
                for draft in row.api_request_drafts
                for requirement in draft.required_before_submit
            ]
        )
        blocker_ids = _dedupe(
            [row.blocker_record.id, *[blocker.id for blocker in row.gate_blocker_records]]
        )
        next_retry_conditions = _dedupe(
            [
                row.next_retry_condition,
                row.authorization_draft_proposal.budget_envelope.next_retry_condition,
                *[blocker.next_retry_condition for blocker in row.gate_blocker_records],
            ]
        )
        status: Literal["review_ready_scope_required", "review_ready_dry_run_only"] = (
            "review_ready_dry_run_only"
            if row.scope_review.verdict == "complete_dry_run_only"
            else "review_ready_scope_required"
        )
        matrix.append(
            OwnerReviewHandoffRow(
                family=row.family,
                strategy_family_id=row.strategy_family_id,
                carrier_id=row.carrier_id,
                status=status,
                owner_scope_verdict=row.scope_review.verdict,
                risk_disclosure_status=row.risk_disclosure_contract.status,
                risk_failure_modes=list(row.risk_disclosure_contract.failure_modes),
                budget_envelope_status=row.budget_envelope_draft.status,
                authorization_draft_status=row.authorization_draft_proposal.status,
                confirmation_phrase_required=(
                    row.authorization_draft_proposal.confirmation_phrase_required
                ),
                operation_step_count=operation_step_count,
                first_operation_type=first_operation_type,
                last_operation_type=last_operation_type,
                draft_endpoints=[draft.endpoint for draft in row.api_request_drafts],
                unresolved_refs=unresolved_refs,
                required_before_submit=required_before_submit,
                blocker_ids=blocker_ids,
                next_retry_conditions=next_retry_conditions,
            )
        )
    return matrix


def _official_api_request_draft_matrix(
    rows: list[FamilyAdmissionRow],
) -> list[OfficialApiRequestDraftSummary]:
    matrix: list[OfficialApiRequestDraftSummary] = []
    for row in rows:
        for draft in row.api_request_drafts:
            matrix.append(
                OfficialApiRequestDraftSummary(
                    family=row.family,
                    strategy_family_id=row.strategy_family_id,
                    carrier_id=row.carrier_id,
                    draft_name=draft.name,
                    method=draft.method,
                    endpoint=draft.endpoint,
                    owner_scope_verdict=row.scope_review.verdict,
                    unresolved_refs=list(draft.unresolved_refs),
                    required_before_submit=list(draft.required_before_submit),
                    payload_template_keys=list(draft.payload_template.keys()),
                    not_submitted=draft.not_submitted,
                    creates_execution_intent=draft.creates_execution_intent,
                    places_order=draft.places_order,
                    mutates_exchange=draft.mutates_exchange,
                )
            )
    return matrix


def _live_action_eligibility_matrix(rows: list[FamilyAdmissionRow]) -> list[LiveActionEligibilityRow]:
    matrix: list[LiveActionEligibilityRow] = []
    for row in rows:
        scope_complete = row.scope_review.verdict == "complete_dry_run_only"
        action_api_supported = row.action_api_compatibility.compatible
        blocker_ids = _dedupe(
            [row.blocker_record.id, *[blocker.id for blocker in row.gate_blocker_records]]
        )
        matrix.append(
            LiveActionEligibilityRow(
                family=row.family,
                strategy_family_id=row.strategy_family_id,
                carrier_id=row.carrier_id,
                decision=(
                    "scope_complete_but_candidate_action_api_unsupported"
                    if scope_complete and not action_api_supported
                    else "scope_complete_but_backend_final_gate_blocked"
                    if scope_complete and action_api_supported
                    else "scope_incomplete_or_unmatched"
                ),
                checks=[
                    LiveActionEligibilityCheck(
                        code="owner_scope_complete",
                        status="pass" if scope_complete else "block",
                        evidence=f"scope_review.verdict={row.scope_review.verdict}",
                        next_retry_condition="Owner supplies complete matched bounded production scope.",
                    ),
                    LiveActionEligibilityCheck(
                        code="official_action_api_candidate_supported",
                        status="pass" if action_api_supported else "block",
                        evidence=f"action_api_compatibility.status={row.action_api_compatibility.status}",
                        next_retry_condition=(
                            "Official Owner trial-flow and bounded-execution registries support this candidate."
                        ),
                    ),
                    LiveActionEligibilityCheck(
                        code="backend_final_gate_actionable",
                        status="block",
                        evidence=f"final_gate_dry_run.reason={row.final_gate_dry_run.reason}",
                        next_retry_condition="Backend final gate returns actionable=true.",
                    ),
                    LiveActionEligibilityCheck(
                        code="pre_action_pg_snapshot",
                        status="required_before_live_action",
                        evidence="pre_post_evidence_contract.pre_action_pg_tables required",
                        next_retry_condition="Official service records pre-action PG snapshot.",
                    ),
                    LiveActionEligibilityCheck(
                        code="pre_action_exchange_snapshot",
                        status="required_before_live_action",
                        evidence="pre_post_evidence_contract.pre_action_exchange_reads required",
                        next_retry_condition="Official service records pre-action exchange snapshot.",
                    ),
                    LiveActionEligibilityCheck(
                        code="mandatory_tp_sl_plan",
                        status="draft_required",
                        evidence=f"protection_plan_draft.status={row.protection_plan_draft.status}",
                        next_retry_condition="Official service validates mandatory TP/SL prices and order plan.",
                    ),
                    LiveActionEligibilityCheck(
                        code="execution_intent",
                        status="not_created",
                        evidence=f"execution_intent_state={row.execution_intent_state}",
                        next_retry_condition="Official action path creates execution intent after all gates pass.",
                    ),
                    LiveActionEligibilityCheck(
                        code="review_contract",
                        status="draft_required",
                        evidence=f"review_contract.status={row.review_contract.status}",
                        next_retry_condition="Post-action Review contract receives official evidence.",
                    ),
                    LiveActionEligibilityCheck(
                        code="audit_chain_ready",
                        status="block",
                        evidence=f"audit_chain_gap_report.status={row.audit_chain_gap_report.status}",
                        next_retry_condition="Audit chain has authorization, intent, entry, TP/SL, Review, and audit events.",
                    ),
                ],
                blocker_ids=blocker_ids,
                next_retry_conditions=_dedupe(
                    [
                        *[
                            blocker.next_retry_condition
                            for blocker in row.gate_blocker_records
                        ],
                        row.next_retry_condition,
                    ]
                ),
            )
        )
    return matrix


def _final_gate_readiness_matrix(rows: list[FamilyAdmissionRow]) -> list[FinalGateReadinessRow]:
    eligibility_by_family = {
        item.family: item for item in _live_action_eligibility_matrix(rows)
    }
    matrix: list[FinalGateReadinessRow] = []
    for row in rows:
        eligibility = eligibility_by_family[row.family]
        scope_complete = row.scope_review.verdict == "complete_dry_run_only"
        action_api_supported = row.action_api_compatibility.compatible
        readiness_level: Literal[
            "scope_required",
            "scope_reviewed_action_api_blocked",
            "scope_reviewed_backend_final_gate_blocked",
        ] = (
            "scope_reviewed_action_api_blocked"
            if scope_complete and not action_api_supported
            else "scope_reviewed_backend_final_gate_blocked"
            if scope_complete and action_api_supported
            else "scope_required"
        )
        blocking_stages = [
            stage.stage
            for stage in row.chain_stage_states
            if stage.status
            in {
                "blocked_candidate_action_api_unsupported",
                "blocked_backend_final_gate",
                "blocked_scope_incomplete_or_unmatched",
                "not_created",
                "not_executed",
                "draft_required_mandatory_tp_sl",
                "review_contract_draft",
            }
        ]
        matrix.append(
            FinalGateReadinessRow(
                family=row.family,
                strategy_family_id=row.strategy_family_id,
                carrier_id=row.carrier_id,
                readiness_level=readiness_level,
                final_gate_endpoint=OFFICIAL_ACTION_API_ENDPOINTS["final_gate_dry_run"],
                execute_endpoint=OFFICIAL_ACTION_API_ENDPOINTS["execute_authorization"],
                final_gate_reason=row.final_gate_dry_run.reason,
                owner_scope_verdict=row.scope_review.verdict,
                checks=list(eligibility.checks),
                blocking_stages=_dedupe(blocking_stages),
                blocker_ids=list(eligibility.blocker_ids),
                next_retry_conditions=list(eligibility.next_retry_conditions),
            )
        )
    return matrix


def _production_action_decision_matrix(
    rows: list[FamilyAdmissionRow],
) -> list[ProductionActionDecisionRow]:
    readiness_by_family = {
        item.family: item for item in _final_gate_readiness_matrix(rows)
    }
    matrix: list[ProductionActionDecisionRow] = []
    for row in rows:
        readiness = readiness_by_family[row.family]
        if row.scope_review.verdict != "complete_dry_run_only":
            reason = "owner_scope_incomplete_or_unmatched"
        elif not row.action_api_compatibility.compatible:
            reason = "official_action_api_candidate_not_supported"
        else:
            reason = "backend_final_gate_not_actionable"
        missing_evidence = _dedupe(
            [
                *row.audit_chain_gap_report.missing_evidence,
                "final_gate_actionable_true",
                "live_action_decision",
            ]
        )
        matrix.append(
            ProductionActionDecisionRow(
                family=row.family,
                strategy_family_id=row.strategy_family_id,
                carrier_id=row.carrier_id,
                reason=reason,
                owner_scope_verdict=row.scope_review.verdict,
                action_api_status=row.action_api_compatibility.status,
                final_gate_reason=readiness.final_gate_reason,
                missing_evidence=missing_evidence,
                blocker_ids=list(readiness.blocker_ids),
                next_retry_conditions=list(readiness.next_retry_conditions),
            )
        )
    return matrix


def _acceptance_evidence_matrix(
    *,
    rows: list[FamilyAdmissionRow],
    scope_review: ScopeReview,
    blocker_records: list[BlockerRecord],
) -> list[AcceptanceEvidenceItem]:
    families = [row.family for row in rows]
    blocker_ids = [blocker.id for blocker in blocker_records if blocker.severity == "hard_blocker"]
    mapping_refs = [
        f"{row.family}:{row.strategy_family_id or 'missing'}->{row.strategy_group}->{row.carrier_id or 'missing'}"
        for row in rows
    ]
    return [
        AcceptanceEvidenceItem(
            item="strategy_families_have_concrete_candidates",
            status="PASS",
            families=families,
            evidence_refs=[
                f"{row.family}:{row.strategy_family_id or 'missing'}"
                for row in rows
            ],
            next_retry_condition="No retry required for candidate presence unless registry changes.",
        ),
        AcceptanceEvidenceItem(
            item="strategy_group_carrier_mapping",
            status="PASS_WITH_CONSTRAINT",
            families=families,
            evidence_refs=mapping_refs,
            blocker_ids=[
                blocker.id for blocker in blocker_records if blocker.stage == "Carrier"
            ],
            next_retry_condition=(
                "Owner approves mapping and official action API supports the candidate carrier."
            ),
        ),
        AcceptanceEvidenceItem(
            item="owner_risk_scope_review",
            status=(
                "PASS_WITH_CONSTRAINT"
                if scope_review.verdict == "complete_dry_run_only"
                else "BLOCKED"
            ),
            families=families,
            evidence_refs=[
                "owner_review_handoff_matrix",
                f"scope_review.verdict={scope_review.verdict}",
                f"scope_review.missing_fields={','.join(scope_review.missing_fields) or 'none'}",
            ],
            blocker_ids=[
                blocker.id for blocker in blocker_records if blocker.stage == "BoundedLiveAuthorization"
            ],
            next_retry_condition=(
                "Owner supplies complete matched bounded production scope."
                if scope_review.verdict != "complete_dry_run_only"
                else "Official action API and backend final gate support the scoped candidate."
            ),
        ),
        AcceptanceEvidenceItem(
            item="api_backed_authorization_flow",
            status="PASS_WITH_CONSTRAINT",
            families=families,
            evidence_refs=[
                "owner_review_handoff_matrix",
                "api_backed_authorization_flow.status=operation_layer_metadata_flow_available",
                "trading_console_direct_action_api=false",
                "operation_preflight=POST /api/brc/operations/preflight",
            ],
            blocker_ids=[
                blocker.id
                for blocker in blocker_records
                if blocker.stage in {"BoundedLiveAuthorization", "ExecutionIntent"}
            ],
            next_retry_condition=(
                "Owner risk acceptance and Operation Layer confirmation are submitted through official API."
            ),
        ),
        AcceptanceEvidenceItem(
            item="frontend_action_disabled_until_backend_actionable",
            status="PASS",
            families=families,
            evidence_refs=[
                "families[*].backend_actionable=false",
                "families[*].frontend_action_enabled=false",
                "trading_console_authorization_readiness.action_enablement_source=backend_actionable_only",
            ],
            next_retry_condition="No retry required; frontend action remains disabled.",
        ),
        AcceptanceEvidenceItem(
            item="production_capital_boundary",
            status="PASS_WITH_CONSTRAINT",
            families=families,
            evidence_refs=[
                "budget_envelope_draft.numbers_source=owner_scope_only_no_fabrication",
                "required_scope_fields=symbol,side,quantity,max_notional,leverage,max_attempts,protection_mode,review_requirement",
            ],
            blocker_ids=[
                blocker.id for blocker in blocker_records if blocker.stage == "BoundedLiveAuthorization"
            ],
            next_retry_condition=(
                "Complete matched Owner scope is present and backend final gate accepts it."
            ),
        ),
        AcceptanceEvidenceItem(
            item="official_action_api_candidate_support",
            status="BLOCKED",
            families=families,
            evidence_refs=[
                (
                    "official_action_api_inventory.owner_trial_flow_supported_carrier_ids="
                    f"{','.join(CURRENT_OFFICIAL_ACTION_CARRIER_IDS)}"
                ),
                *[
                    f"{row.family}:{row.action_api_compatibility.status}"
                    for row in rows
                ],
            ],
            blocker_ids=[
                blocker.id for blocker in blocker_records if blocker.stage == "BoundedLiveAuthorization"
            ],
            next_retry_condition=(
                "Official Owner trial-flow and bounded-execution registries support one sprint candidate."
            ),
        ),
        AcceptanceEvidenceItem(
            item="backend_final_gate_preflight",
            status="BLOCKED",
            families=families,
            evidence_refs=[
                f"{row.family}:final_gate_dry_run.reason={row.final_gate_dry_run.reason}"
                for row in rows
            ],
            blocker_ids=[
                blocker.id for blocker in blocker_records if blocker.stage == "ExecutionIntent"
            ],
            next_retry_condition=(
                "Backend final gate returns actionable=true with complete scope, action API support, "
                "pre-evidence, TP/SL, and Review requirements."
            ),
        ),
        AcceptanceEvidenceItem(
            item="pg_exchange_pre_post_evidence",
            status="BLOCKED",
            families=families,
            evidence_refs=[
                "pre_post_evidence_contract.live_action_evidence_present=false",
                "pg_exchange_evidence.evidence_level=repo_read_model_only",
            ],
            blocker_ids=[
                blocker.id for blocker in blocker_records if blocker.stage == "Entry"
            ],
            next_retry_condition=(
                "Official action services collect pre/post PG snapshots and exchange read evidence."
            ),
        ),
        AcceptanceEvidenceItem(
            item="mandatory_tp_sl_protection",
            status="DEFERRED",
            families=families,
            evidence_refs=[
                f"{row.family}:protection_plan_draft.status={row.protection_plan_draft.status}"
                for row in rows
            ],
            blocker_ids=[
                blocker.id for blocker in blocker_records if blocker.stage == "TP/SL"
            ],
            next_retry_condition=(
                "Official service validates TP/SL prices and records protection orders for the scoped action."
            ),
        ),
        AcceptanceEvidenceItem(
            item="review_audit_contract",
            status="BLOCKED",
            families=families,
            evidence_refs=[
                "review_contract.status=draft_no_action_evidence",
                "audit_chain_gap_report.status=gap_open_no_live_action_evidence",
            ],
            blocker_ids=[
                blocker.id for blocker in blocker_records if blocker.stage == "Review"
            ],
            next_retry_condition=(
                "Post-action Review and audit events exist for bounded authorization, intent, entry, TP/SL, "
                "and PG/exchange evidence."
            ),
        ),
        AcceptanceEvidenceItem(
            item="live_action_execution",
            status="BLOCKED",
            families=families,
            evidence_refs=[
                "live_actions_taken=[]",
                "sprint_acceptance_verdict.live_execution_ready=false",
                "sprint_acceptance_verdict.actionable_family_count=0",
            ],
            blocker_ids=blocker_ids,
            next_retry_condition=(
                "A candidate has complete Owner scope, official action API support, actionable backend final gate, "
                "pre/post evidence, mandatory TP/SL, and Review/Audit contract."
            ),
        ),
    ]


def _objective_acceptance_audit_matrix(
    *,
    rows: list[FamilyAdmissionRow],
    scope_review: ScopeReview,
    blocker_records: list[BlockerRecord],
) -> list[ObjectiveAcceptanceAuditRow]:
    families = [row.family for row in rows]
    hard_blocker_ids = [
        blocker.id for blocker in blocker_records if blocker.severity == "hard_blocker"
    ]
    authorization_blocker_ids = [
        blocker.id for blocker in blocker_records if blocker.stage == "BoundedLiveAuthorization"
    ]
    execution_blocker_ids = [
        blocker.id
        for blocker in blocker_records
        if blocker.stage in {"ExecutionIntent", "Entry"}
    ]
    evidence_blocker_ids = [
        blocker.id
        for blocker in blocker_records
        if blocker.stage in {"PreExecutionBlockedReview", "Audit"}
    ]
    family_refs = [
        f"{row.family}:{row.strategy_family_id or 'missing'}:{row.carrier_id or 'missing'}"
        for row in rows
    ]
    return [
        ObjectiveAcceptanceAuditRow(
            requirement_id="strategy_family_scope",
            requirement="Only Trend, Volatility expansion, and Mean reversion families are processed.",
            status="PASS",
            verification_scope="three configured production admission families",
            completion_evidence="proved_by_read_model_and_targeted_tests",
            evidence_refs=[
                "families",
                "family_completion_matrix",
                *family_refs,
            ],
            next_retry_condition="No retry required unless Owner changes the sprint family scope.",
        ),
        ObjectiveAcceptanceAuditRow(
            requirement_id="production_baseline_context",
            requirement=(
                "Prior BNB execute/closeout evidence and post-close flat context are treated "
                "as historical baseline only, not reusable action permission."
            ),
            status="PASS_WITH_CONSTRAINT",
            verification_scope="current repo report artifacts and read-model safety boundary",
            completion_evidence="proved_by_read_model_and_targeted_tests",
            evidence_refs=[
                "production_baseline_context",
                "production_baseline_context.prior_scoped_carrier_id=MI-001-BNB-LONG",
                "production_baseline_context.post_close_state_status=reported_flat_requires_fresh_pg_exchange_validation_before_new_action",
            ],
            next_retry_condition=(
                "Fresh pre-action PG and exchange evidence is collected through the official action path."
            ),
        ),
        ObjectiveAcceptanceAuditRow(
            requirement_id="full_chain_per_family",
            requirement=(
                "Each family adapts StrategyFamily -> StrategyGroup -> Carrier -> "
                "RiskDisclosure -> AuthorizationDraft -> BoundedLiveAuthorization -> "
                "ExecutionIntent -> Entry -> TP/SL -> Review."
            ),
            status="PASS_WITH_CONSTRAINT",
            verification_scope="candidate/proposal chain rows for each family",
            completion_evidence="blocked_with_bridge_artifact",
            evidence_refs=[
                "full_chain_evidence_matrix",
                "family_completion_matrix",
                "protection_review_audit_matrix",
            ],
            blocker_ids=hard_blocker_ids,
            next_retry_condition=(
                "Official action path supports a scoped candidate and records Entry/TP/SL/Review evidence."
            ),
        ),
        ObjectiveAcceptanceAuditRow(
            requirement_id="trading_console_authorization_path",
            requirement=(
                "Owner can review risk/scope and see API-backed authorization flow while "
                "frontend action remains disabled unless backend says actionable."
            ),
            status="PASS_WITH_CONSTRAINT",
            verification_scope="Trading Console read-model handoff; no action API exposed",
            completion_evidence="blocked_with_bridge_artifact",
            evidence_refs=[
                "owner_review_handoff_matrix",
                "owner_authorization_packet_matrix",
                "api_backed_authorization_flow",
                "trading_console_authorization_readiness",
            ],
            blocker_ids=authorization_blocker_ids,
            next_retry_condition=(
                "Complete scoped Owner authorization and backend actionable=true are present through official APIs."
            ),
        ),
        ObjectiveAcceptanceAuditRow(
            requirement_id="strategy_group_carrier_alignment",
            requirement="Map family/group/carrier, readiness, blockers, and classification.",
            status="PASS_WITH_CONSTRAINT",
            verification_scope="registry-backed mapping and readiness report rows",
            completion_evidence="proved_by_read_model_and_targeted_tests",
            evidence_refs=[
                "families[*].strategy_group_mapping",
                "families[*].carrier_candidate",
                "families[*].carrier_readiness_report",
                "classification_counts",
            ],
            blocker_ids=[
                blocker.id for blocker in blocker_records if blocker.stage == "Carrier"
            ],
            next_retry_condition="Owner approves mapping and official action API supports the carrier.",
        ),
        ObjectiveAcceptanceAuditRow(
            requirement_id="admission_and_risk_control",
            requirement=(
                "Admission levels, risk disclosure, authorization draft/state, final gate, "
                "preflight checks, review, and audit contract are represented."
            ),
            status="PASS_WITH_CONSTRAINT",
            verification_scope="admission/risk-control, final-gate, review, and audit matrices",
            completion_evidence="blocked_with_bridge_artifact",
            evidence_refs=[
                "admission_risk_control_matrix",
                "final_gate_readiness_matrix",
                "protection_review_audit_matrix",
                "audit_chain_gap_report",
            ],
            blocker_ids=hard_blocker_ids,
            next_retry_condition=(
                "Final gate, TP/SL, Review, and audit evidence exist through official action path."
            ),
        ),
        ObjectiveAcceptanceAuditRow(
            requirement_id="production_capital_boundary",
            requirement=(
                "Use only explicit Owner scope and do not expand symbol, side, quantity, "
                "notional, leverage, attempts, protection mode, or review requirement."
            ),
            status="PASS_WITH_CONSTRAINT",
            verification_scope="BudgetEnvelopeDraft and ProductionCapitalBoundary rows",
            completion_evidence="proved_by_read_model_and_targeted_tests",
            evidence_refs=[
                "production_capital_boundary_matrix",
                "budget_envelope_draft.numbers_source=owner_scope_only_no_fabrication",
                f"scope_review.verdict={scope_review.verdict}",
            ],
            blocker_ids=authorization_blocker_ids,
            next_retry_condition=(
                "Complete matched Owner scope is present and backend final gate accepts it."
            ),
        ),
        ObjectiveAcceptanceAuditRow(
            requirement_id="live_action_decision",
            requirement=(
                "Execute full production chain only if scoped Owner authorization and hard gates pass; "
                "otherwise produce dry-run/proposal artifacts."
            ),
            status="BLOCKED",
            verification_scope="per-family live action decision and hard-gate matrices",
            completion_evidence="blocked_with_bridge_artifact",
            evidence_refs=[
                "production_action_decision_matrix",
                "live_action_eligibility_matrix",
                "live_actions_taken=[]",
            ],
            blocker_ids=_dedupe([*authorization_blocker_ids, *execution_blocker_ids]),
            next_retry_condition=(
                "A family candidate is supported by official action API, final gate actionable=true, "
                "and all mandatory evidence/TP/SL/Review checks pass."
            ),
        ),
        ObjectiveAcceptanceAuditRow(
            requirement_id="pg_exchange_evidence",
            requirement="Every live action requires pre/post PG and exchange evidence.",
            status="BLOCKED",
            verification_scope="required evidence contract only; no live action evidence collected",
            completion_evidence="blocked_with_bridge_artifact",
            evidence_refs=[
                "pg_exchange_evidence_matrix",
                "family_evidence_collection_matrix",
                "evidence_collection_summary_matrix",
            ],
            blocker_ids=evidence_blocker_ids,
            next_retry_condition=(
                "Official action service records pre/post PG snapshots, exchange reads, and audit events."
            ),
        ),
        ObjectiveAcceptanceAuditRow(
            requirement_id="blocker_records_and_bridges",
            requirement="Blocked paths are recorded with bridge artifacts and retry conditions.",
            status="PASS_WITH_CONSTRAINT",
            verification_scope="first-class blocker and bridge matrices",
            completion_evidence="proved_by_read_model_and_targeted_tests",
            evidence_refs=[
                "blocker_records",
                "blocker_retry_matrix",
                "bridge_artifact_statuses",
            ],
            blocker_ids=hard_blocker_ids,
            next_retry_condition="Retry each blocker only when its recorded next_retry_condition is satisfied.",
        ),
        ObjectiveAcceptanceAuditRow(
            requirement_id="final_report_package",
            requirement="Final report includes family work, mappings, risk control, readiness, evidence, blockers, tests, retry conditions, and safety proof.",
            status="PASS_WITH_CONSTRAINT",
            verification_scope="final report sections and required validation command list",
            completion_evidence="proved_by_read_model_and_targeted_tests",
            evidence_refs=[
                "final_report_package",
                "family_final_report_matrix",
                "sprint_acceptance_verdict",
            ],
            blocker_ids=hard_blocker_ids,
            next_retry_condition="All BLOCKED objective audit rows become passable through official evidence.",
        ),
        ObjectiveAcceptanceAuditRow(
            requirement_id="safety_proof",
            requirement="No forbidden live action, runtime start, PG mutation, credential change, deploy, or push is performed by the read model.",
            status="PASS",
            verification_scope="read-model safety flags and targeted safe verification",
            completion_evidence="proved_by_read_model_and_targeted_tests",
            evidence_refs=[
                "final_report_package.live_actions_taken=false",
                "final_report_package.runtime_started=false",
                "final_report_package.pg_mutation=false",
                "final_report_package.exchange_write_action=false",
                "final_report_package.credentials_changed=false",
                "final_report_package.deploy_performed=false",
                "final_report_package.push_performed=false",
            ],
            next_retry_condition="No retry required unless action code paths are changed.",
        ),
    ]


def _bridge_artifact_statuses(rows: list[FamilyAdmissionRow]) -> list[BridgeArtifactStatus]:
    families = [row.family for row in rows]
    status_by_method: dict[str, dict[str, str]] = {
        "TrendObservation": {
            row.family: (
                row.observation_bridge.status
                if row.observation_bridge.bridge_method == "TrendObservation"
                else "not_applicable"
            )
            for row in rows
        },
        "StrategyGroupMappingProposal": {
            row.family: row.strategy_group_mapping.status for row in rows
        },
        "CarrierCandidate": {
            row.family: row.carrier_candidate.status for row in rows
        },
        "CarrierReadinessReport": {
            row.family: row.carrier_readiness_report.status for row in rows
        },
        "ActionCandidate": {
            row.family: row.action_candidate.status for row in rows
        },
        "RiskDisclosureDraft": {
            row.family: row.risk_disclosure_contract.status for row in rows
        },
        "AuthorizationDraftProposal": {
            row.family: row.authorization_draft_proposal.status for row in rows
        },
        "BudgetEnvelopeDraft": {
            row.family: row.budget_envelope_draft.status for row in rows
        },
        "FinalGateDryRun": {
            row.family: row.final_gate_dry_run.status for row in rows
        },
        "PreExecutionBlockedReview": {
            row.family: row.pre_execution_blocked_review.status for row in rows
        },
        "ProtectionPlanDraft": {
            row.family: row.protection_plan_draft.status for row in rows
        },
        "ReviewContract": {
            row.family: row.review_contract.status for row in rows
        },
        "AuditChainGapReport": {
            row.family: row.audit_chain_gap_report.status for row in rows
        },
    }
    status_override = {
        "FinalGateDryRun": "blocked",
        "PreExecutionBlockedReview": "blocked",
        "AuditChainGapReport": "blocked",
        "RiskDisclosureDraft": "draft",
        "AuthorizationDraftProposal": "draft",
        "BudgetEnvelopeDraft": "draft",
        "ProtectionPlanDraft": "draft",
        "ReviewContract": "draft",
        "ActionCandidate": "blocked",
    }
    retry_conditions = {
        "TrendObservation": (
            "Trend observation is reviewed with complete Owner scope and official backend final gate support."
        ),
        "StrategyGroupMappingProposal": (
            "Owner approves the family/group/carrier mapping and candidate is supported by official action API."
        ),
        "CarrierCandidate": (
            "Candidate is promoted through official registry and runtime readiness without starting execution."
        ),
        "CarrierReadinessReport": (
            "Official action API supports the carrier and backend final gate returns actionable=true."
        ),
        "ActionCandidate": (
            "Official action API supports this candidate and backend final gate returns actionable=true."
        ),
        "RiskDisclosureDraft": (
            "Owner reviews risk disclosure and submits risk acceptance through official API."
        ),
        "AuthorizationDraftProposal": (
            "Complete matched scope, Owner risk acceptance, and Operation Layer confirmation are recorded."
        ),
        "BudgetEnvelopeDraft": (
            "Owner supplies complete matched bounded production scope; no numeric values are inferred."
        ),
        "FinalGateDryRun": (
            "Backend final gate returns actionable=true with PG/exchange pre-evidence and TP/SL plan."
        ),
        "PreExecutionBlockedReview": (
            "All pre-execution blockers clear through official service/API evidence."
        ),
        "ProtectionPlanDraft": (
            "Official service validates TP/SL prices and records protection order evidence."
        ),
        "ReviewContract": (
            "Post-action review receives execution intent, entry, TP/SL, PG/exchange snapshots, and audit events."
        ),
        "AuditChainGapReport": (
            "Official action path records the complete AuthorizationDraft -> Review/Audit evidence chain."
        ),
    }
    results: list[BridgeArtifactStatus] = []
    for method in BRIDGE_ARTIFACTS:
        row_statuses = status_by_method[method]
        applicable_families = [
            family for family, status in row_statuses.items() if status != "not_applicable"
        ]
        status = status_override.get(method)
        if status is None:
            statuses = {value for value in row_statuses.values() if value != "not_applicable"}
            status = "present" if len(statuses) == 1 else "mixed"
        results.append(
            BridgeArtifactStatus(
                bridge_method=method,
                status=status,
                families=applicable_families or families,
                row_statuses=row_statuses,
                evidence=(
                    f"{method} is represented in strategy-family admission state; this summary "
                    "does not create authorization, execution intent, orders, or PG mutations."
                ),
                next_retry_condition=retry_conditions[method],
            )
        )
    return results


def _admission_verdict(
    *,
    classification: str,
    scope_review: ScopeReview,
    action_api_compatibility: CandidateActionApiCompatibility,
    gate_blockers: list[BlockerRecord],
) -> FamilyAdmissionVerdict:
    if classification == "dry-run-only" and scope_review.verdict == "complete_dry_run_only":
        verdict: Literal[
            "dry_run_only_scope_required",
            "dry_run_only_scope_reviewed",
            "blocked_backend_final_gate",
            "blocked_scope_required",
            "blocked_candidate_mismatch",
        ] = "dry_run_only_scope_reviewed"
        summary = "Owner scope is complete for dry-run review, but live execution remains blocked."
    elif classification == "dry-run-only":
        verdict = "dry_run_only_scope_required"
        summary = "Candidate is dry-run-only and still requires complete matched Owner scope."
    elif scope_review.verdict == "candidate_mismatch":
        verdict = "blocked_candidate_mismatch"
        summary = "Candidate remains blocked because supplied scope does not match this family/carrier."
    elif scope_review.verdict == "complete_dry_run_only" and action_api_compatibility.compatible:
        verdict = "blocked_backend_final_gate"
        summary = (
            "Owner scope is complete and the carrier is supported by the action registry, "
            "but backend final gate and required action evidence remain blocked."
        )
    else:
        verdict = "blocked_scope_required"
        summary = "Candidate remains blocked and requires scope/readiness evidence before retry."

    completed = ["StrategyFamily", "StrategyGroup"]
    if classification == "dry-run-only":
        completed.append("Carrier")
    completed.append("RiskDisclosure")
    if scope_review.verdict == "complete_dry_run_only":
        completed.append("AuthorizationDraft")
    blocked_stages = _dedupe([blocker.stage for blocker in gate_blockers])
    remaining = [
        blocker.next_retry_condition
        for blocker in gate_blockers
        if blocker.severity == "hard_blocker"
    ]
    if not action_api_compatibility.compatible and (
        "candidate supported by official action API registry" not in remaining
    ):
        remaining.append("candidate supported by official action API registry")
    return FamilyAdmissionVerdict(
        verdict=verdict,
        frontend_summary=summary,
        completed_stages=_dedupe(completed),
        blocked_stages=blocked_stages,
        remaining_requirements=_dedupe(remaining),
        next_retry_conditions=_dedupe([blocker.next_retry_condition for blocker in gate_blockers]),
    )


def _aggregate_blocker_records(rows: list[FamilyAdmissionRow]) -> list[BlockerRecord]:
    by_id: dict[str, BlockerRecord] = {}
    for row in rows:
        by_id[row.blocker_record.id] = row.blocker_record
        for blocker in row.gate_blocker_records:
            by_id[blocker.id] = blocker
    return list(by_id.values())


def _pre_execution_blocked_review(
    *,
    family_label: str,
    carrier_id: Optional[str],
    scope_review: ScopeReview,
    action_api_compatibility: CandidateActionApiCompatibility,
    gate_blockers: list[BlockerRecord],
    final_gate_dry_run: FinalGateDryRun,
) -> PreExecutionBlockedReview:
    if scope_review.verdict != "complete_dry_run_only":
        reason = "owner_scope_incomplete_or_unmatched"
    elif not action_api_compatibility.compatible:
        reason = "official_action_api_candidate_not_supported"
    else:
        reason = final_gate_dry_run.reason
    final_gate_by_code = {item["code"]: item["status"] for item in final_gate_dry_run.gates}
    checks = [
        {
            "code": "owner_scope_complete",
            "status": final_gate_by_code.get("owner_scope_complete", "block"),
            "source": "scope_review",
        },
        {
            "code": "official_action_api_candidate_supported",
            "status": "pass" if action_api_compatibility.compatible else "block",
            "source": "official_action_api_inventory",
        },
        {
            "code": "backend_final_gate_actionable",
            "status": "block",
            "source": "final_gate_dry_run",
        },
        {
            "code": "pg_exchange_pre_evidence",
            "status": "required_before_live_action",
            "source": "pre_post_evidence_contract",
        },
        {
            "code": "mandatory_tp_sl_plan",
            "status": "draft_required",
            "source": "protection_plan_draft",
        },
        {
            "code": "review_contract",
            "status": "draft_required",
            "source": "review_contract",
        },
    ]
    return PreExecutionBlockedReview(
        family=family_label,
        carrier_id=carrier_id,
        blocked_reason=reason,
        checks=checks,
        blocking_stages=_dedupe([blocker.stage for blocker in gate_blockers]),
        unresolved_blocker_ids=_dedupe([blocker.id for blocker in gate_blockers]),
        next_retry_conditions=_dedupe(
            [blocker.next_retry_condition for blocker in gate_blockers]
        ),
    )


def _aggregate_pre_execution_blocked_review(rows: list[FamilyAdmissionRow]) -> PreExecutionBlockedReview:
    blocking_stages: list[str] = []
    blocker_ids: list[str] = []
    retry_conditions: list[str] = []
    for row in rows:
        blocking_stages.extend(row.pre_execution_blocked_review.blocking_stages)
        blocker_ids.extend(row.pre_execution_blocked_review.unresolved_blocker_ids)
        retry_conditions.extend(row.pre_execution_blocked_review.next_retry_conditions)
    return PreExecutionBlockedReview(
        family=None,
        carrier_id=None,
        blocked_reason="no_family_candidate_is_pre_execution_actionable",
        checks=[
            {"code": "family_count", "status": str(len(rows)), "source": "families"},
            {
                "code": "actionable_family_count",
                "status": str(sum(1 for row in rows if row.backend_actionable)),
                "source": "families",
            },
            {
                "code": "frontend_action_enabled",
                "status": "false",
                "source": "backend_actionable_only",
            },
            {
                "code": "live_execution_ready",
                "status": "false",
                "source": "sprint_acceptance_verdict",
            },
        ],
        blocking_stages=_dedupe(blocking_stages),
        unresolved_blocker_ids=_dedupe(blocker_ids),
        next_retry_conditions=_dedupe(retry_conditions),
    )


def _audit_chain_gap_report(
    *,
    family_label: str,
    carrier_id: Optional[str],
) -> AuditChainGapReport:
    return AuditChainGapReport(
        family=family_label,
        carrier_id=carrier_id,
        present_evidence=[
            "strategy_family_mapping",
            "carrier_candidate_metadata" if carrier_id else "missing_carrier_candidate",
            "risk_disclosure_draft",
            "authorization_draft_proposal",
            "budget_envelope_draft",
            "protection_plan_draft",
            "review_contract_draft",
        ],
        missing_evidence=[
            "owner_submitted_admission_request",
            "owner_risk_acceptance",
            "bounded_live_authorization",
            "backend_final_gate_actionable_true",
            "pre_action_pg_snapshot",
            "pre_action_exchange_snapshot",
            "execution_intent",
            "entry_order",
            "tp_sl_orders",
            "post_action_pg_snapshot",
            "post_action_exchange_snapshot",
            "post_action_review",
            "audit_log_events",
        ],
    )


def _aggregate_audit_chain_gap_report(rows: list[FamilyAdmissionRow]) -> AuditChainGapReport:
    missing: list[str] = []
    present: list[str] = []
    for row in rows:
        present.extend(row.audit_chain_gap_report.present_evidence)
        missing.extend(row.audit_chain_gap_report.missing_evidence)
    return AuditChainGapReport(
        family=None,
        carrier_id=None,
        present_evidence=_dedupe(present),
        missing_evidence=_dedupe(missing),
        reason=(
            "Sprint read model produced proposal/bridge evidence only; no candidate has "
            "official action evidence or a closed audit chain."
        ),
        next_retry_condition=(
            "A candidate becomes supported by official action API, backend final gate returns "
            "actionable=true, and official action services record the complete pre/post evidence chain."
        ),
    )


def _api_request_drafts(
    *,
    config: _FamilyConfig,
    family_id: Optional[str],
    carrier_id: Optional[str],
    supported_symbols: list[str],
    timeframes: list[str],
    scope_review: ScopeReview,
) -> list[ApiRequestDraft]:
    scope = dict(scope_review.sanitized_scope)
    strategy_family_version_id = family_id or "<required:strategy_family_version_id>"
    playbook_id = carrier_id or "<required:playbook_id>"
    common_required = [
        "strategy family/version exists in BRC admission repository",
        "evidence packet is created through official API",
        "owner regime input is created through official API",
        "complete matched Owner scope",
    ]
    return [
        ApiRequestDraft(
            name="create_admission_evidence_packet",
            method="POST",
            endpoint="POST /api/brc/admissions/evidence-packets",
            payload_template={
                "strategy_family_version_id": strategy_family_version_id,
                "payload_json": {
                    "family": config.family_label,
                    "strategy_group": config.strategy_group,
                    "carrier_id": carrier_id,
                    "supported_symbols": supported_symbols,
                    "timeframes": [item for item in timeframes if item],
                    "risk_disclosure": config.risk_disclosure,
                    "owner_scope": scope,
                    "read_model_source": "strategy_family_admission_state",
                },
                "mandatory_complete": False,
                "created_by": "owner",
            },
            unresolved_refs=[] if family_id else ["strategy_family_version_id"],
            required_before_submit=[
                "BRC admission strategy family/version repository mapping exists",
                "evidence payload is reviewed by Owner",
            ],
        ),
        ApiRequestDraft(
            name="create_owner_regime_input",
            method="POST",
            endpoint="POST /api/brc/admissions/owner-regime-inputs",
            payload_template={
                "current_regime": "<owner_supplied_current_regime>",
                "confidence": "unknown",
                "rationale": "<owner_supplied_rationale>",
                "market_facts_snapshot_json": {
                    "family": config.family_label,
                    "carrier_id": carrier_id,
                    "scope": scope,
                },
                "created_by": "owner",
            },
            unresolved_refs=["owner_current_regime", "owner_rationale"],
            required_before_submit=["Owner supplies current regime interpretation"],
        ),
        ApiRequestDraft(
            name="create_admission_request",
            method="POST",
            endpoint="POST /api/brc/admissions/requests",
            payload_template={
                "strategy_family_version_id": strategy_family_version_id,
                "evidence_packet_id": "<required:evidence_packet_id>",
                "owner_market_regime_input_id": "<required:owner_market_regime_input_id>",
                "trial_env": "live",
                "trial_stage": "funded_validation",
                "requested_execution_mode": "owner_confirm_each_entry",
                "requested_risk_profile": "micro",
                "account_facts_snapshot_ref": "<required:pre_action_account_facts_snapshot_ref>",
                "account_facts_snapshot_json": {
                    "owner_scope": scope,
                    "pre_post_evidence_contract": "required",
                },
                "playbook_id": playbook_id,
                "requested_by": "owner",
            },
            unresolved_refs=[
                "evidence_packet_id",
                "owner_market_regime_input_id",
                "pre_action_account_facts_snapshot_ref",
                *([] if family_id else ["strategy_family_version_id"]),
                *([] if carrier_id else ["playbook_id"]),
            ],
            required_before_submit=common_required,
        ),
        ApiRequestDraft(
            name="create_owner_risk_acceptance",
            method="POST",
            endpoint="POST /api/brc/admissions/risk-acceptances",
            payload_template={
                "admission_request_id": "<required:admission_request_id>",
                "constraint_snapshot_id": "<required:constraint_snapshot_id>",
                "admission_decision_id": "<required:admission_decision_id>",
                "owner_rationale": "<owner_supplied_rationale>",
                "confirmation_phrase": "I ACCEPT BOUNDED FUNDED VALIDATION RISK",
                "confirmed_by": "owner",
            },
            unresolved_refs=[
                "admission_request_id",
                "constraint_snapshot_id",
                "admission_decision_id",
                "owner_rationale",
            ],
            required_before_submit=[
                "admission request is evaluated",
                "constraint snapshot exists",
                "Owner confirms funded validation risk phrase",
            ],
        ),
        ApiRequestDraft(
            name="operation_preflight_create_gated_trial_from_admission",
            method="POST",
            endpoint="POST /api/brc/operations/preflight",
            payload_template={
                "operation_type": "create_gated_trial_from_admission",
                "requested_by": "owner",
                "input_params": {
                    "admission_decision_id": "<required:admission_decision_id>",
                    "constraint_snapshot_id": "<required:constraint_snapshot_id>",
                    "owner_risk_acceptance_id": "<required:owner_risk_acceptance_id>",
                    "family": config.family_label,
                    "carrier_id": carrier_id,
                    "scope": scope,
                },
                "source": {
                    "kind": "trading_console_read_model",
                    "ref": "strategy_family_admission_state",
                },
            },
            unresolved_refs=[
                "admission_decision_id",
                "constraint_snapshot_id",
                "owner_risk_acceptance_id",
            ],
            required_before_submit=[
                "Owner risk acceptance is created through official API",
                "Operation Layer capability is available",
                "backend final gate remains separately required before any live order path",
            ],
        ),
    ]


def _observation_bridge(
    *,
    config: _FamilyConfig,
    family_id: Optional[str],
    carrier_id: Optional[str],
    supported_symbols: list[str],
    timeframes: list[str],
) -> ObservationBridge:
    clean_timeframes = [item for item in timeframes if item]
    if family_id is None:
        return ObservationBridge(
            family=config.family_label,
            bridge_method=(
                "TrendObservation"
                if config.family_type == StrategyFamilyType.TREND_FOLLOWING
                else config.bridge_method
                if config.bridge_method in {"CarrierReadinessReport", "CarrierCandidate"}
                else "CarrierCandidate"
            ),
            status="missing_candidate",
            supported_symbols=[],
            timeframes=[],
            evidence="No registry candidate is available to observe.",
            next_retry_condition="Register a concrete strategy-family candidate before observation.",
        )
    if config.family_type == StrategyFamilyType.TREND_FOLLOWING:
        return ObservationBridge(
            family=config.family_label,
            bridge_method="TrendObservation",
            status="observation_bridge_only",
            supported_symbols=supported_symbols,
            timeframes=clean_timeframes,
            evidence=(
                f"{family_id}/{carrier_id or family_id} is available for Owner-visible "
                "trend observation only; this read model does not start a runner, emit a "
                "signal, create trade intent, create execution intent, or place orders."
            ),
            next_retry_condition=(
                "TrendObservation evidence is reviewed with complete Owner scope and "
                "official backend final gate support."
            ),
        )
    if config.family_type == StrategyFamilyType.VOLATILITY_BREAKOUT:
        return ObservationBridge(
            family=config.family_label,
            bridge_method="CarrierReadinessReport",
            status="readiness_report_only",
            supported_symbols=supported_symbols,
            timeframes=clean_timeframes,
            evidence="Volatility expansion candidate remains a readiness report, not a runner.",
            next_retry_condition=config.next_retry_condition,
        )
    return ObservationBridge(
        family=config.family_label,
        bridge_method="CarrierCandidate",
        status="candidate_metadata_only",
        supported_symbols=supported_symbols,
        timeframes=clean_timeframes,
        evidence="Mean-reversion candidate is metadata-only and has no evaluator activation.",
        next_retry_condition=config.next_retry_condition,
    )


def _gate_blocker_records(
    *,
    config: _FamilyConfig,
    family_id: Optional[str],
    carrier_id: Optional[str],
    scope_review: ScopeReview,
    action_api_compatibility: CandidateActionApiCompatibility,
) -> list[BlockerRecord]:
    blocked_path = f"{config.family_label} -> {family_id or 'missing-family'} -> {carrier_id or 'missing-carrier'}"
    records: list[BlockerRecord] = []
    if family_id is None:
        records.append(
            BlockerRecord(
                id=f"{config.blocker_id}-REGISTRY",
                stage="StrategyFamily",
                blocked_path=blocked_path,
                evidence="Strategy family registry candidate is missing.",
                severity="hard_blocker",
                bridge_method="StrategyGroupMappingProposal",
                next_retry_condition="Register a concrete strategy-family candidate.",
            )
        )
    if carrier_id is None:
        records.append(
            BlockerRecord(
                id=f"{config.blocker_id}-CARRIER",
                stage="Carrier",
                blocked_path=blocked_path,
                evidence="Carrier candidate is missing.",
                severity="hard_blocker",
                bridge_method="CarrierCandidate",
                next_retry_condition="Create a concrete carrier candidate for the family.",
            )
        )
    if scope_review.verdict != "complete_dry_run_only":
        records.append(
            BlockerRecord(
                id=f"{config.blocker_id}-SCOPE",
                stage="AuthorizationDraft",
                blocked_path=blocked_path,
                evidence=(
                    "Owner scope is not complete and matched. "
                    f"verdict={scope_review.verdict}; missing={scope_review.missing_fields}; "
                    f"mismatches={scope_review.mismatches}"
                ),
                severity="hard_blocker",
                bridge_method="AuthorizationDraftProposal",
                next_retry_condition=(
                    "Owner provides complete symbol/side/quantity/max_notional/leverage/"
                    "max_attempts/protection_mode/review_requirement scope for this candidate."
                ),
            )
        )
    if not action_api_compatibility.compatible:
        records.append(
            BlockerRecord(
                id=f"{config.blocker_id}-ACTION-API",
                stage="BoundedLiveAuthorization",
                blocked_path=blocked_path,
                evidence="Candidate carrier is not supported by current official action API registry.",
                severity="hard_blocker",
                bridge_method="ActionCandidate",
                next_retry_condition=(
                    "Owner trial-flow and bounded-execution registries support the exact candidate carrier."
                ),
            )
        )
    records.extend(
        [
            BlockerRecord(
                id=f"{config.blocker_id}-FINAL-GATE",
                stage="BoundedLiveAuthorization",
                blocked_path=blocked_path,
                evidence="Backend final gate has not returned actionable=true for this candidate.",
                severity="hard_blocker",
                bridge_method="FinalGateDryRun",
                next_retry_condition="Official backend final gate returns actionable=true.",
            ),
            BlockerRecord(
                id=f"{config.blocker_id}-EVIDENCE",
                stage="PreExecutionBlockedReview",
                blocked_path=blocked_path,
                evidence="Required pre-action PG and exchange evidence has not been collected.",
                severity="hard_blocker",
                bridge_method="PreExecutionBlockedReview",
                next_retry_condition="Pre-action PG and exchange snapshots are collected through official service/API.",
            ),
            BlockerRecord(
                id=f"{config.blocker_id}-PROTECTION",
                stage="TP/SL",
                blocked_path=blocked_path,
                evidence="Mandatory TP/SL plan is draft-only and not executable.",
                severity="hard_blocker",
                bridge_method="ProtectionPlanDraft",
                next_retry_condition="Mandatory TP/SL plan is valid for the exact candidate scope.",
            ),
            BlockerRecord(
                id=f"{config.blocker_id}-REVIEW",
                stage="Review",
                blocked_path=blocked_path,
                evidence="Post-action review contract is draft-only and has no action evidence to review.",
                severity="deferred",
                bridge_method="ReviewContract",
                next_retry_condition="Live action evidence exists and post-action review is recorded.",
            ),
        ]
    )
    return records


def _chain_stage_states(
    *,
    family_label: str,
    family_id: Optional[str],
    carrier_id: Optional[str],
    classification: str,
    scope_review: ScopeReview,
    action_api_compatibility: CandidateActionApiCompatibility,
    blocker: BlockerRecord,
) -> list[ChainStageState]:
    strategy_family_status = "available" if family_id else "missing"
    carrier_status = (
        "dry_run_only"
        if classification == "dry-run-only"
        else "candidate_only"
        if carrier_id
        else "missing"
    )
    authorization_status = (
        "scope_reviewed_dry_run_only"
        if scope_review.verdict == "complete_dry_run_only"
        else "proposal_only_scope_required"
    )
    bounded_authorization_status = (
        "blocked_candidate_action_api_unsupported"
        if scope_review.verdict == "complete_dry_run_only" and not action_api_compatibility.compatible
        else "blocked_backend_final_gate"
        if scope_review.verdict == "complete_dry_run_only" and action_api_compatibility.compatible
        else "blocked_scope_incomplete_or_unmatched"
    )
    return [
        ChainStageState(
            stage="StrategyFamily",
            status=strategy_family_status,
            evidence=family_id or "No registry candidate found.",
            bridge_method="StrategyGroupMappingProposal" if family_id is None else None,
            blocker_id=blocker.id if family_id is None else None,
        ),
        ChainStageState(
            stage="StrategyGroup",
            status="mapped" if family_id else "blocked",
            evidence=f"{family_label} strategy group mapping recorded.",
            bridge_method="StrategyGroupMappingProposal",
            blocker_id=None if family_id else blocker.id,
        ),
        ChainStageState(
            stage="Carrier",
            status=carrier_status,
            evidence=carrier_id or "Carrier candidate missing.",
            bridge_method="CarrierCandidate",
            blocker_id=blocker.id if not carrier_id else None,
        ),
        ChainStageState(
            stage="RiskDisclosure",
            status="draft_required",
            evidence="Risk disclosure draft is present for Owner review.",
            bridge_method="RiskDisclosureDraft",
        ),
        ChainStageState(
            stage="AuthorizationDraft",
            status=authorization_status,
            evidence=f"Owner scope review verdict: {scope_review.verdict}.",
            bridge_method="AuthorizationDraftProposal",
            blocker_id=blocker.id if scope_review.verdict != "complete_dry_run_only" else None,
        ),
        ChainStageState(
            stage="BoundedLiveAuthorization",
            status=bounded_authorization_status,
            evidence=(
                "Candidate is not supported by current official action API registry."
                if not action_api_compatibility.compatible
                else "Candidate action API is supported but backend final gate remains blocked."
            ),
            bridge_method="FinalGateDryRun",
            blocker_id=blocker.id,
        ),
        ChainStageState(
            stage="ExecutionIntent",
            status="not_created",
            evidence="Read model does not create execution intents.",
            bridge_method="PreExecutionBlockedReview",
            blocker_id=blocker.id,
        ),
        ChainStageState(
            stage="Entry",
            status="not_executed",
            evidence="No entry order was submitted.",
            bridge_method="ActionCandidate",
            blocker_id=blocker.id,
        ),
        ChainStageState(
            stage="TP/SL",
            status="draft_required_mandatory_tp_sl",
            evidence="Mandatory TP/SL plan is required before any live action.",
            bridge_method="ProtectionPlanDraft",
            blocker_id=blocker.id,
        ),
        ChainStageState(
            stage="Review",
            status="review_contract_draft",
            evidence="Post-action review is required before promotion.",
            bridge_method="ReviewContract",
        ),
    ]


def _final_gate_dry_run(
    *,
    scope_review: Optional[ScopeReview] = None,
    action_api_compatible: bool = False,
) -> FinalGateDryRun:
    owner_scope_status = "pass" if scope_review and scope_review.verdict == "complete_dry_run_only" else "block"
    reason = (
        "official_action_api_candidate_not_supported"
        if owner_scope_status == "pass" and not action_api_compatible
        else "backend_final_gate_requires_authorization_and_live_preflight"
        if owner_scope_status == "pass" and action_api_compatible
        else "production_scope_incomplete"
    )
    return FinalGateDryRun(
        reason=reason,
        gates=[
            {"code": "owner_scope_complete", "status": owner_scope_status},
            {"code": "backend_final_gate_actionable", "status": "block"},
            {
                "code": "official_action_api_candidate_supported",
                "status": "pass" if action_api_compatible else "block",
            },
            {"code": "mandatory_tp_sl_plan", "status": "draft_required"},
            {"code": "review_contract", "status": "draft_required"},
            {"code": "pg_exchange_pre_evidence", "status": "required_before_live_action"},
        ]
    )


def _budget_envelope_draft(
    *,
    scope_review: ScopeReview,
    scope: OwnerScopeDraft,
) -> BudgetEnvelopeDraft:
    sanitized_scope = dict(scope_review.sanitized_scope)
    missing_fields = (
        list(scope_review.missing_fields)
        if scope_review.provided
        else list(REQUIRED_OWNER_SCOPE_FIELDS)
    )
    provided_fields = [
        field
        for field in REQUIRED_OWNER_SCOPE_FIELDS
        if getattr(scope, field) not in (None, "")
    ]
    validation_checks = [
        {
            "code": "owner_scope_complete",
            "status": "pass" if scope_review.verdict == "complete_dry_run_only" else "block",
            "source": "scope_review",
        },
        {
            "code": "candidate_scope_matched",
            "status": "pass" if scope_review.matched_candidate else "block",
            "source": "scope_review",
        },
        {
            "code": "quantity_provided",
            "status": "pass" if scope.quantity not in (None, "") else "missing",
            "source": "owner_scope",
        },
        {
            "code": "max_notional_provided",
            "status": "pass" if scope.max_notional not in (None, "") else "missing",
            "source": "owner_scope",
        },
        {
            "code": "leverage_provided",
            "status": "pass" if scope.leverage not in (None, "") else "missing",
            "source": "owner_scope",
        },
        {
            "code": "max_attempts_provided",
            "status": "pass" if scope.max_attempts is not None else "missing",
            "source": "owner_scope",
        },
        {
            "code": "protection_mode_defined",
            "status": "pass" if scope.protection_mode not in (None, "") else "missing",
            "source": "owner_scope",
        },
        {
            "code": "review_requirement_defined",
            "status": "pass" if scope.review_requirement not in (None, "") else "missing",
            "source": "owner_scope",
        },
        {
            "code": "numbers_source_owner_supplied",
            "status": "pass" if provided_fields else "missing",
            "source": "read_model_no_fabrication_policy",
        },
    ]
    common = {
        "scope": sanitized_scope,
        "provided_scope_fields": provided_fields,
        "missing_scope_fields": missing_fields,
        "validation_checks": validation_checks,
        "symbol": scope.symbol,
        "side": scope.side,
        "quantity": scope.quantity,
        "max_notional": scope.max_notional,
        "leverage": scope.leverage,
        "max_attempts": scope.max_attempts,
        "protection_mode": scope.protection_mode,
        "review_requirement": scope.review_requirement,
    }
    if scope_review.verdict != "complete_dry_run_only":
        return BudgetEnvelopeDraft(**common)
    return BudgetEnvelopeDraft(
        status="scope_complete_dry_run_only",
        missing_scope_fields=[],
        **{key: value for key, value in common.items() if key != "missing_scope_fields"},
    )


def _risk_disclosure_contract(config: _FamilyConfig) -> RiskDisclosureDraft:
    return RiskDisclosureDraft(
        family=config.family_label,
        strategy_group=config.strategy_group,
        summary=config.risk_disclosure,
        failure_modes=list(config.failure_modes),
        research_quality_status=config.research_quality_status,
        risk_disclosure_classifications=_risk_disclosure_classifications(config),
    )


def _risk_disclosure_classifications(
    config: _FamilyConfig,
) -> list[ResearchRiskClassification]:
    items: list[ResearchRiskClassification] = [
        "warning",
        config.research_quality_status,
        "owner_risk_acceptance_required",
    ]
    items.extend(config.risk_disclosure_classifications)
    return _dedupe(items)  # type: ignore[return-value]


def _protection_plan_draft(*, scope_review: ScopeReview) -> ProtectionPlanDraft:
    scope = dict(scope_review.sanitized_scope)
    missing = [
        "take_profit_price",
        "stop_loss_price",
        *(
            []
            if scope_review.verdict == "complete_dry_run_only"
            else ["complete_matched_owner_scope"]
        ),
    ]
    return ProtectionPlanDraft(
        status=(
            "scope_reviewed_draft_only"
            if scope_review.verdict == "complete_dry_run_only"
            else "draft_required_mandatory_tp_sl"
        ),
        scope=scope,
        validation_checks=[
            {
                "code": "owner_scope_complete",
                "status": "pass"
                if scope_review.verdict == "complete_dry_run_only"
                else "block",
            },
            {"code": "take_profit_defined", "status": "missing"},
            {"code": "stop_loss_defined", "status": "missing"},
            {"code": "official_service_validated_prices", "status": "required_before_action"},
            {"code": "exchange_protection_orders_created", "status": "not_created"},
        ],
        missing_fields=missing,
        not_executable_until_scope_complete=scope_review.verdict != "complete_dry_run_only",
    )


def _review_contract(*, family_label: Optional[str], metrics: list[str]) -> ReviewContract:
    return ReviewContract(
        family=family_label,
        metrics=metrics,
        missing_evidence=[
            "bounded_live_authorization",
            "execution_intent",
            "entry_order",
            "tp_sl_orders",
            "post_action_pg_snapshot",
            "post_action_exchange_snapshot",
            "audit_log_events",
        ],
    )


def _strategy_group_mapping(
    *,
    config: _FamilyConfig,
    family_id: Optional[str],
    family_type: Optional[str],
    carrier_id: Optional[str],
) -> StrategyGroupMappingProposal:
    return StrategyGroupMappingProposal(
        family=config.family_label,
        strategy_family_id=family_id,
        strategy_family_type=family_type,
        strategy_group=config.strategy_group,
        carrier_id=carrier_id,
        admission_level=config.admission_level if family_id else "not_available",
        classification=config.classification if family_id else "blocked",
        evidence=(
            f"{config.family_label} maps to {config.strategy_group}"
            if family_id
            else f"{config.family_label} has no registered strategy-family candidate to map."
        ),
        next_retry_condition=(
            config.next_retry_condition
            if family_id
            else "Register a concrete strategy-family candidate before mapping can advance."
        ),
    )


def _carrier_candidate(
    *,
    config: _FamilyConfig,
    family_id: Optional[str],
    carrier_id: Optional[str],
    carrier_status: Optional[str],
    supported_symbols: list[str],
    primary_timeframe: Optional[str],
    context_timeframes: list[str],
) -> CarrierCandidate:
    if carrier_id is None:
        status: Literal[
            "registered_metadata_only",
            "observation_candidate_only",
            "candidate_missing",
        ] = "candidate_missing"
        blockers = ["carrier_candidate_missing"]
        evidence = "No carrier candidate is available in the registry seed."
    elif config.classification == "dry-run-only":
        status = "observation_candidate_only"
        blockers = [
            "official_action_api_candidate_not_supported",
            "backend_final_gate_not_actionable",
        ]
        evidence = (
            "Carrier candidate is present for Owner review and dry-run proposal; "
            "research-quality weakness is disclosed as risk, while live remains "
            "blocked by execution gates."
        )
    elif config.classification == "actionable":
        status = "registered_metadata_only"
        blockers = [
            "backend_final_gate_not_actionable",
            "complete_owner_scope_required",
            "pre_action_pg_exchange_evidence_required",
            "mandatory_tp_sl_plan_required",
        ]
        evidence = "Carrier candidate is registered in the official action path but still requires live preflight evidence."
    else:
        status = "registered_metadata_only"
        blockers = [
            "carrier_readiness_evidence_required",
            "official_action_api_candidate_not_supported",
            "backend_final_gate_not_actionable",
        ]
        evidence = "Carrier candidate is registered as metadata and is not executable."
    return CarrierCandidate(
        status=status,
        family=config.family_label,
        strategy_family_id=family_id,
        carrier_id=carrier_id,
        carrier_status=carrier_status,
        supported_symbols=supported_symbols,
        primary_timeframe=primary_timeframe,
        context_timeframes=context_timeframes,
        evidence=evidence,
        research_quality_status=config.research_quality_status,
        risk_disclosure_classifications=_risk_disclosure_classifications(config),
        blockers=blockers,
        next_retry_condition=config.next_retry_condition,
    )


def _carrier_readiness_report(
    *,
    config: _FamilyConfig,
    carrier_id: Optional[str],
    carrier_status: Optional[str],
    supported_symbols: list[str],
    primary_timeframe: Optional[str],
    context_timeframes: list[str],
) -> CarrierReadinessReport:
    if carrier_id is None:
        status: Literal[
            "observation_ready_not_actionable",
            "candidate_registered_not_actionable",
            "candidate_missing",
        ] = "candidate_missing"
    elif config.classification == "dry-run-only":
        status = "observation_ready_not_actionable"
    else:
        status = "candidate_registered_not_actionable"
    readiness_checks = [
        {
            "code": "registry_candidate_present",
            "status": "pass" if carrier_id else "block",
        },
        {
            "code": "supported_symbols_present",
            "status": "pass" if supported_symbols else "block",
        },
        {
            "code": "timeframe_present",
            "status": "pass" if primary_timeframe else "block",
        },
        {
            "code": "official_action_api_supported",
            "status": "pass" if carrier_id in CURRENT_OFFICIAL_ACTION_CARRIER_IDS else "block",
        },
        {
            "code": "backend_actionable",
            "status": "block",
        },
        {
            "code": "research_quality_disclosure",
            "status": config.research_quality_status,
        },
        {
            "code": "owner_risk_acceptance",
            "status": "required_before_l3",
        },
    ]
    blockers = [
        "backend_final_gate_not_actionable",
        "complete_owner_scope_required",
    ]
    if carrier_id not in CURRENT_OFFICIAL_ACTION_CARRIER_IDS:
        blockers.insert(0, "official_action_api_candidate_not_supported")
    if carrier_id is None:
        blockers.insert(0, "carrier_candidate_missing")
    return CarrierReadinessReport(
        status=status,
        family=config.family_label,
        carrier_id=carrier_id,
        carrier_status=carrier_status,
        classification=config.classification if carrier_id else "blocked",
        supported_symbols=supported_symbols,
        primary_timeframe=primary_timeframe,
        context_timeframes=context_timeframes,
        readiness_checks=readiness_checks,
        research_quality_status=config.research_quality_status,
        risk_disclosure_classifications=_risk_disclosure_classifications(config),
        blockers=_dedupe(blockers),
        next_retry_condition=config.next_retry_condition,
    )


def _action_candidate(
    *,
    config: _FamilyConfig,
    carrier_id: Optional[str],
    scope_review: ScopeReview,
    action_api_compatibility: CandidateActionApiCompatibility,
) -> ActionCandidate:
    blockers: list[str] = list(action_api_compatibility.blockers)
    if scope_review.verdict != "complete_dry_run_only":
        blockers.append("complete_matched_owner_scope_required")
    blockers.extend(
        [
            "backend_final_gate_actionable_true_required",
            "pre_action_pg_exchange_evidence_required",
            "mandatory_tp_sl_plan_required",
            "post_action_review_contract_required",
        ]
    )
    required_before_action = [
        "Owner accepts disclosed strategy/evidence risk when admission is L3",
        "complete matched Owner scope",
        "candidate carrier supported by official action API registry",
        "backend final gate returns actionable=true",
        "pre-action PG evidence captured",
        "pre-action exchange evidence captured",
        "mandatory TP/SL plan validated",
        "Review and audit recording path available",
        "Owner risk acceptance never overrides execution safety gates",
    ]
    return ActionCandidate(
        status=(
            "supported_but_backend_not_actionable"
            if action_api_compatibility.compatible
            else "unsupported_by_current_official_action_api"
        ),
        family=config.family_label,
        carrier_id=carrier_id,
        candidate_carrier_id=action_api_compatibility.candidate_carrier_id,
        research_quality_status=config.research_quality_status,
        risk_disclosure_classifications=_risk_disclosure_classifications(config),
        required_before_action=required_before_action,
        blockers=_dedupe(blockers),
        next_retry_condition=(
            "Official action API supports this candidate carrier and backend final gate returns actionable=true."
            if not action_api_compatibility.compatible
            else "Backend final gate returns actionable=true with full evidence and TP/SL plan."
        ),
    )


def _authorization_draft_proposal(
    *,
    scope_review: ScopeReview,
    scope: OwnerScopeDraft,
    risk_disclosure: str,
    risk_disclosure_contract: Optional[RiskDisclosureDraft] = None,
    review_contract: Optional[ReviewContract] = None,
) -> AuthorizationDraftProposal:
    budget = _budget_envelope_draft(scope_review=scope_review, scope=scope)
    protection_plan = _protection_plan_draft(scope_review=scope_review)
    return AuthorizationDraftProposal(
        status=(
            "scope_reviewed_dry_run_only"
            if scope_review.verdict == "complete_dry_run_only"
            else "scope_required"
        ),
        scope=scope_review.sanitized_scope,
        risk_disclosure=risk_disclosure,
        risk_disclosure_contract=risk_disclosure_contract,
        budget_envelope=budget,
        protection_plan=protection_plan,
        review_contract=review_contract or _review_contract(family_label=None, metrics=[]),
    )


def _action_api_compatibility(carrier_id: Optional[str]) -> CandidateActionApiCompatibility:
    blockers: list[str] = []
    if not carrier_id:
        blockers.append("candidate_carrier_missing")
    if carrier_id not in CURRENT_OFFICIAL_ACTION_CARRIER_IDS:
        blockers.extend(
            [
                "candidate_carrier_not_supported_by_owner_trial_flow",
                "candidate_carrier_not_supported_by_owner_bounded_execution_registry",
            ]
        )
    compatible = not blockers
    return CandidateActionApiCompatibility(
        status=(
            "supported_by_current_official_action_api_but_not_actionable"
            if compatible
            else "unsupported_by_current_official_action_api"
        ),
        candidate_carrier_id=carrier_id,
        compatible=compatible,
        blockers=_dedupe(blockers),
    )


def _scope_review_for_missing_candidate(
    *,
    config: _FamilyConfig,
    scope: OwnerScopeDraft,
) -> ScopeReview:
    if not _scope_provided(scope):
        return ScopeReview()
    return ScopeReview(
        provided=True,
        target_family=scope.family,
        target_strategy_family_id=scope.strategy_family_id,
        target_carrier_id=scope.carrier_id,
        missing_fields=_missing_scope_fields(scope),
        mismatches=[f"strategy family missing in registry: {config.family_label}"],
        sanitized_scope=_sanitized_scope(scope),
        verdict="candidate_mismatch",
    )


def _scope_review_for_candidate(
    *,
    family_label: str,
    family_id: str,
    carrier_id: str,
    supported_symbols: list[str],
    scope: OwnerScopeDraft,
) -> ScopeReview:
    if not _scope_provided(scope):
        return ScopeReview()
    missing = _missing_scope_fields(scope)
    mismatches: list[str] = []
    if scope.family and _normalize(scope.family) not in {
        _normalize(family_label),
        _normalize(family_id),
    }:
        mismatches.append("family mismatch")
    if scope.strategy_family_id and scope.strategy_family_id != family_id:
        mismatches.append("strategy_family_id mismatch")
    if scope.carrier_id and scope.carrier_id != carrier_id:
        mismatches.append("carrier_id mismatch")
    if scope.symbol and scope.symbol not in supported_symbols:
        mismatches.append("symbol not supported by candidate")
    verdict: Literal["incomplete", "candidate_mismatch", "complete_dry_run_only"]
    if missing:
        verdict = "incomplete"
    elif mismatches:
        verdict = "candidate_mismatch"
    else:
        verdict = "complete_dry_run_only"
    return ScopeReview(
        provided=True,
        target_family=scope.family,
        target_strategy_family_id=scope.strategy_family_id,
        target_carrier_id=scope.carrier_id,
        complete=not missing,
        matched_candidate=verdict == "complete_dry_run_only",
        missing_fields=missing,
        mismatches=mismatches,
        sanitized_scope=_sanitized_scope(scope),
        verdict=verdict,
    )


def _aggregate_scope_review(rows: list[FamilyAdmissionRow]) -> ScopeReview:
    provided = any(row.scope_review.provided for row in rows)
    if not provided:
        return ScopeReview()
    matched = next(
        (row.scope_review for row in rows if row.scope_review.verdict == "complete_dry_run_only"),
        None,
    )
    if matched is not None:
        return matched
    first = next(row.scope_review for row in rows if row.scope_review.provided)
    missing: list[str] = []
    mismatches: list[str] = []
    for row in rows:
        for item in row.scope_review.missing_fields:
            if item not in missing:
                missing.append(item)
        for item in row.scope_review.mismatches:
            if item not in mismatches:
                mismatches.append(item)
    verdict: Literal["incomplete", "candidate_mismatch"] = (
        "incomplete" if missing else "candidate_mismatch"
    )
    return first.model_copy(
        update={
            "complete": not missing,
            "matched_candidate": False,
            "missing_fields": missing,
            "mismatches": mismatches,
            "verdict": verdict,
        }
    )


def _scope_provided(scope: OwnerScopeDraft) -> bool:
    return any(getattr(scope, field) not in (None, "") for field in OwnerScopeDraft.model_fields)


def _missing_scope_fields(scope: OwnerScopeDraft) -> list[str]:
    return [
        field
        for field in REQUIRED_OWNER_SCOPE_FIELDS
        if getattr(scope, field) in (None, "")
    ]


def _sanitized_scope(scope: OwnerScopeDraft) -> dict[str, object]:
    return {
        key: value
        for key, value in scope.model_dump(mode="json").items()
        if value not in (None, "")
    }


def _normalize(value: str) -> str:
    return value.strip().lower().replace("_", "-").replace(" ", "-")


def _count_classifications(rows: list[FamilyAdmissionRow]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.classification] = counts.get(row.classification, 0) + 1
    return counts


def _admission_level_specs() -> list[AdmissionLevelSpec]:
    return [
        AdmissionLevelSpec(
            level="L0",
            name="archive / rejected / parked",
            semantics="Not selectable for current Owner action review.",
            action_candidate_allowed=False,
            live_action_allowed=False,
            required_artifacts=["BlockerRecord"],
            hard_gate_policy="No live path; preserve evidence and retry condition.",
            example_status="parked",
        ),
        AdmissionLevelSpec(
            level="L1",
            name="displayable candidate",
            semantics=(
                "Can appear in Trading Console as a displayable candidate or "
                "candidate shell with risk-disclosure context."
            ),
            action_candidate_allowed=True,
            live_action_allowed=False,
            required_artifacts=["StrategyFamilySpec", "StrategyGroupSpec"],
            hard_gate_policy=(
                "Display/review only; research weakness is warning/risk acceptance, "
                "not a live execution gate."
            ),
            example_status="displayable",
        ),
        AdmissionLevelSpec(
            level="L2",
            name="action-candidate proposal",
            semantics="Can produce a proposal-grade ActionCandidateSpec for Owner review.",
            action_candidate_allowed=True,
            live_action_allowed=False,
            required_artifacts=[
                "StrategyFamilySpec",
                "StrategyGroupSpec",
                "CarrierSpec",
                "RiskDisclosureSpec",
                "ReviewTemplate",
                "ActionCandidateSpec",
            ],
            hard_gate_policy="Proposal only until exact Owner scope and final-gate prerequisites exist.",
            example_status="Volatility/MR proposal",
        ),
        AdmissionLevelSpec(
            level="L3",
            name="Owner-confirmed bounded live candidate",
            semantics=(
                "May enter official Owner-confirmed bounded live path only after exact "
                "scope, explicit Owner risk acceptance, hard execution gates, TP/SL, "
                "recording, and evidence are present."
            ),
            action_candidate_allowed=True,
            live_action_allowed=True,
            required_artifacts=[
                "ActionCandidateSpec",
                "Owner execute authorization",
                "FinalGateDryRun pass",
                "ProtectionPlan",
                "ReviewTemplate",
            ],
            hard_gate_policy=(
                "Owner risk acceptance may override evidence weakness only; execution "
                "safety gates remain hard blockers."
            ),
            example_status="Trend exact-scope candidate",
            owner_risk_acceptance_required_for_l3=True,
        ),
        AdmissionLevelSpec(
            level="L4",
            name="budgeted autonomy candidate",
            semantics="Design-only level for future budgeted autonomy; no current live autonomy.",
            action_candidate_allowed=True,
            live_action_allowed=False,
            autonomy_allowed=True,
            required_artifacts=["BudgetEnvelopeDraft", "Autonomy audit design"],
            hard_gate_policy="Design only unless separately safe and auditable.",
            example_status="deferred design",
        ),
    ]


def _candidate_pipeline_standard() -> CandidatePipelineStandard:
    return CandidatePipelineStandard(admission_levels=_admission_level_specs())


def _strategy_family_specs(rows: list[FamilyAdmissionRow]) -> list[StrategyFamilySpec]:
    return [
        StrategyFamilySpec(
            family=row.family,
            strategy_family_id=row.strategy_family_id,
            family_type=row.strategy_family_type,
            admission_level=row.admission_level_code,
            hypothesis=row.strategy_group_mapping.evidence,
            supported_symbols=list(row.supported_symbols),
            evidence_requirements=[
                "candidate evidence",
                "Owner risk disclosure",
                "review template",
            ],
            warning_items=list(row.risk_disclosure_contract.failure_modes),
            research_quality_status=row.research_quality_status,
            risk_disclosure_classifications=list(row.risk_disclosure_classifications),
            owner_risk_acceptance_required=row.owner_risk_acceptance_required,
            owner_risk_acceptance_may_override=list(row.owner_risk_acceptance_may_override),
            owner_risk_acceptance_never_overrides=list(
                row.owner_risk_acceptance_never_overrides
            ),
            hard_blockers_for_live_action=_row_hard_blockers(row),
        )
        for row in rows
    ]


def _strategy_group_specs(rows: list[FamilyAdmissionRow]) -> list[StrategyGroupSpec]:
    return [
        StrategyGroupSpec(
            family=row.family,
            strategy_group=row.strategy_group,
            owner_input_modes=["market_regime", "direction", "confidence", "note"],
            selection_output="CarrierSpec + RiskDisclosureSpec + ActionCandidateSpec",
            maps_to_carrier_id=row.carrier_id,
        )
        for row in rows
    ]


def _carrier_specs(rows: list[FamilyAdmissionRow]) -> list[CarrierSpec]:
    return [
        CarrierSpec(
            family=row.family,
            carrier_id=row.carrier_id,
            admission_level=row.admission_level_code,
            status=row.carrier_candidate.status,
            proposal_role=_proposal_role(row),
            market_regime=_market_regime_for_family(row.family),
            supported_symbols=list(row.supported_symbols),
            supported_sides=_supported_sides_for_family(row.family),
            scope_template=_carrier_scope_template(row),
            default_example=_carrier_default_example(row),
            protection_template=_protection_template(row),
            review_template_ref=f"review-template:{row.carrier_id or row.family}",
            action_registry_supported=row.action_api_compatibility.compatible,
            can_produce_action_candidate=row.action_candidate.candidate_carrier_id is not None,
            blockers=list(row.carrier_candidate.blockers),
            research_quality_status=row.research_quality_status,
            risk_disclosure_classifications=list(row.risk_disclosure_classifications),
            owner_risk_acceptance_required=row.owner_risk_acceptance_required,
        )
        for row in rows
    ]


def _risk_disclosure_specs(rows: list[FamilyAdmissionRow]) -> list[RiskDisclosureSpec]:
    return [
        RiskDisclosureSpec(
            family=row.family,
            research_quality_status=row.research_quality_status,
            risk_disclosure_classifications=list(row.risk_disclosure_classifications),
            owner_risk_acceptance_required=row.owner_risk_acceptance_required,
            owner_risk_acceptance_may_override=list(row.owner_risk_acceptance_may_override),
            owner_risk_acceptance_never_overrides=list(
                row.owner_risk_acceptance_never_overrides
            ),
            warnings=list(row.risk_disclosure_contract.failure_modes),
            hard_blockers_not_included=[
                "weak strategy evidence",
                "thin sample",
                "incomplete signal markers",
                "fee/funding/slippage unavailable",
                "fragile_evidence",
                "insufficient_research",
                "owner_risk_acceptance_required",
            ],
        )
        for row in rows
    ]


def _review_templates(rows: list[FamilyAdmissionRow]) -> list[ReviewTemplate]:
    return [
        ReviewTemplate(
            family=row.family,
            metrics=list(row.review_contract.metrics),
            required_sections=[
                "entry_result",
                "tp_sl_result",
                "pnl_summary",
                "protection_outcome",
                "failure_mode_notes",
                "next_iteration_decision",
            ],
            pre_action_evidence_required=[
                "recording path available",
                "audit path available",
            ],
        )
        for row in rows
    ]


def _protection_templates(rows: list[FamilyAdmissionRow]) -> list[ProtectionTemplateSpec]:
    templates: list[ProtectionTemplateSpec] = []
    for row in rows:
        template = _protection_template(row)
        templates.append(
            ProtectionTemplateSpec(
                template_id=str(template["template_id"]),
                family=row.family,
                carrier_id=row.carrier_id,
                mode="single_tp_plus_sl",
                required_components=["TP", "SL"],
                parameter_requirements=[
                    "take_profit_price from official service",
                    "stop_loss_price from official service",
                    "reduce-only protection order recording",
                    "post-action protection health check",
                ],
                hard_blockers_for_live_action=[
                    "missing or unknown protection",
                    "TP/SL plan unavailable",
                    "protection recording unavailable",
                ],
                review_template_ref=f"review-template:{row.carrier_id or row.family}",
            )
        )
    return templates


def _warning_records(rows: list[FamilyAdmissionRow]) -> list[WarningRecord]:
    records: list[WarningRecord] = []
    for row in rows:
        for classification in row.risk_disclosure_classifications:
            records.append(
                WarningRecord(
                    warning_id=(
                        f"warning:{row.carrier_id or row.family}:"
                        f"research:{classification}"
                    ),
                    family=row.family,
                    carrier_id=row.carrier_id,
                    classification=classification,
                    description=_research_risk_description(row, classification),
                    owner_ack_required=True,
                    blocks_after_ack=False,
                )
            )
        for index, warning in enumerate(row.risk_disclosure_contract.failure_modes, start=1):
            records.append(
                WarningRecord(
                    warning_id=(
                        f"warning:{row.carrier_id or row.family}:"
                        f"{index}:{_normalize(warning)}"
                    ),
                    family=row.family,
                    carrier_id=row.carrier_id,
                    description=warning,
                )
            )
    return records


def _research_risk_description(
    row: FamilyAdmissionRow,
    classification: ResearchRiskClassification,
) -> str:
    if classification == "owner_risk_acceptance_required":
        return (
            "Owner must explicitly accept disclosed strategy/evidence risk before "
            "any L3 bounded-live path; this never bypasses execution safety gates."
        )
    if classification == "fragile_evidence":
        return (
            "Research evidence is fragile and must remain visible as Owner-accepted "
            "risk rather than a silent rejection."
        )
    if classification == "insufficient_research":
        return (
            "Research-quality evidence is insufficient for confidence claims; the "
            "candidate remains reviewable as L1/L2 with explicit risk disclosure."
        )
    return (
        f"{row.family} has strategy/evidence warnings that require Owner review "
        "but are not execution hard blockers after acceptance."
    )


def _candidate_actionability(rows: list[FamilyAdmissionRow]) -> list[CandidateActionability]:
    actionability: list[CandidateActionability] = []
    for row in rows:
        generic_status = _generic_action_spec_status(row, _carrier_scope_template(row))
        if generic_status == "valid_blocked_final_gate":
            status: Literal[
                "historical_proof_not_current_action",
                "displayable",
                "proposal_review",
                "owner_scope_final_gate_ready",
                "blocked",
            ] = "owner_scope_final_gate_ready"
            disabled_reason = "FinalGate, Owner authorization, protection, and audit evidence are still required."
            next_hard_gate = "FinalGate"
        elif row.admission_level_code == "L2":
            status = "proposal_review"
            disabled_reason = "Candidate is reviewable but not live-enabled."
            next_hard_gate = "official_action_api_or_readiness"
        elif row.admission_level_code == "L1":
            status = "displayable"
            disabled_reason = "Candidate is displayable only."
            next_hard_gate = "ActionCandidate"
        else:
            status = "blocked"
            disabled_reason = row.next_retry_condition
            next_hard_gate = row.blocker_record.stage
        actionability.append(
            CandidateActionability(
                family=row.family,
                strategy_family_id=row.strategy_family_id,
                carrier_id=row.carrier_id,
                admission_level=row.admission_level_code,
                actionability=status,
                action_registry_supported=row.action_api_compatibility.compatible,
                owner_authorization_path_available=row.action_api_compatibility.compatible,
                final_gate_preview_available=generic_status == "valid_blocked_final_gate",
                budget_envelope_compatible=(
                    row.family == "Mean reversion"
                    or row.admission_level_code in {"L3", "L4"}
                ),
                warning_count=len(row.risk_disclosure_contract.failure_modes),
                hard_blocker_count=len(_row_hard_blockers(row)),
                disabled_reason=disabled_reason,
                next_hard_gate=next_hard_gate,
            )
        )
    return actionability


def _final_gate_adapter_results(
    rows: list[FamilyAdmissionRow],
) -> list[ActionSpecFinalGateAdapterResult]:
    adapter = ActionSpecFinalGateAdapterService()
    results = [_bnb_final_gate_adapter_result(adapter)]
    for row, action_spec in zip(rows, _generic_action_specs(rows)):
        spec_payload = action_spec.model_dump(mode="json")
        spec_payload["action_spec_id"] = f"action-spec:{row.carrier_id or row.family}"
        if row.family == "Mean reversion" and row.carrier_id:
            spec_payload["budget_envelope_ref"] = f"budget-envelope:{row.carrier_id}"
            spec_payload["status"] = "valid_blocked_final_gate"
        results.append(
            adapter.adapt(
                candidate=ActionCandidateAdapterInput(
                    candidate_id=f"action-candidate:{row.carrier_id or row.family}",
                    family=row.family,
                    strategy_family_id=row.strategy_family_id,
                    carrier_id=row.carrier_id,
                    admission_level=row.admission_level_code,
                    candidate_status=row.action_candidate.status,
                    action_registry_supported=row.action_api_compatibility.compatible,
                    proposal_role=_proposal_role(row),
                    warnings=_dedupe(
                        [
                            *list(row.risk_disclosure_contract.failure_modes),
                            *list(row.risk_disclosure_classifications),
                        ]
                    ),
                    hard_blockers=_row_hard_blockers(row),
                    evidence=[
                        row.strategy_group_mapping.evidence,
                        row.carrier_candidate.evidence,
                    ],
                ),
                action_spec=ActionSpecDraftInput.model_validate(spec_payload),
                facts=FinalGateFactInput(),
            )
        )
    return results


def _bnb_final_gate_adapter_result(
    adapter: ActionSpecFinalGateAdapterService,
) -> ActionSpecFinalGateAdapterResult:
    candidate_id = "action-candidate:MI-001-BNB-LONG"
    return adapter.adapt(
        candidate=ActionCandidateAdapterInput(
            candidate_id=candidate_id,
            family="BNB manual bounded live proof",
            strategy_family_id="MI-001",
            carrier_id="MI-001-BNB-LONG",
            admission_level="L0",
            candidate_status="historical_proof_not_current_authorization",
            action_registry_supported=True,
            proposal_role="historical_regression_sample",
            dry_run_only=True,
            warnings=[],
            hard_blockers=[
                "fresh Owner authorization required",
                "fresh PG/exchange validation required",
                "FinalGate pass required",
            ],
            evidence=["historical BNB execute/close proof only"],
        ),
        action_spec=ActionSpecDraftInput(
            action_spec_id="action-spec:MI-001-BNB-LONG",
            status="historical_proof_not_current_authorization",
            family="BNB manual bounded live proof",
            strategy_family_id="MI-001",
            carrier_id="MI-001-BNB-LONG",
            admission_level="L0",
            action_registry_supported=True,
            proposal_role="historical_regression_sample",
            symbol="BNB/USDT:USDT",
            side="long",
            quantity="0.01",
            max_notional="20",
            leverage="1",
            max_attempts=1,
            protection_mode="single_tp_plus_sl",
            review_requirement="post_action_review_required",
            protection_template={
                "template_id": "protection-template:MI-001-BNB-LONG",
                "mode": "single_tp_plus_sl",
                "mandatory": True,
                "hard_blockers": ["fresh protection price plan required"],
            },
            review_template={
                "template_id": "review-template:MI-001-BNB-LONG",
                "post_action_required": True,
            },
            hard_blockers=[
                "fresh Owner authorization required",
                "fresh PG/exchange validation required",
                "FinalGate pass required",
            ],
        ),
        facts=FinalGateFactInput(),
    )


def _final_gate_preview_inputs(rows: list[FamilyAdmissionRow]) -> list[FinalGatePreviewInputModel]:
    previews: list[FinalGatePreviewInputModel] = []
    for row in rows:
        scope_template = _carrier_scope_template(row)
        generic_status = _generic_action_spec_status(row, scope_template)
        hard_blockers = _row_hard_blockers(row)
        previews.append(
            FinalGatePreviewInputModel(
                preview_id=f"final-gate-preview:{row.carrier_id or row.family}",
                candidate_id=row.action_candidate.candidate_carrier_id or row.carrier_id,
                carrier_id=row.carrier_id,
                strategy_family=row.family,
                strategy_family_id=row.strategy_family_id,
                admission_level=row.admission_level_code,
                symbol=_optional_str(scope_template.get("symbol")),
                side=_optional_str(scope_template.get("side")),
                quantity=_optional_str(scope_template.get("quantity")),
                target_notional_usdt=_optional_str(scope_template.get("target_notional_usdt")),
                max_notional=_optional_str(scope_template.get("max_notional")),
                leverage=_optional_str(scope_template.get("leverage")),
                max_attempts=_optional_int(scope_template.get("max_attempts")),
                protection_mode=_optional_str(scope_template.get("protection_mode")),
                protection_template_id=f"protection-template:{row.carrier_id or row.family}",
                budget_envelope_ref=(
                    f"budget-envelope:{row.carrier_id}"
                    if row.family == "Mean reversion" and row.carrier_id
                    else None
                ),
                owner_authorization_ref=(
                    f"owner-authorization:{row.carrier_id}"
                    if row.action_api_compatibility.compatible and row.carrier_id
                    else None
                ),
                required_checks=list(
                    GenericFinalGateAdapterContract().required_pre_action_facts
                ),
                warning_refs=[
                    (
                        f"warning:{row.carrier_id or row.family}:"
                        f"{index}:{_normalize(warning)}"
                    )
                    for index, warning in enumerate(row.risk_disclosure_contract.failure_modes, start=1)
                ],
                hard_blocker_refs=hard_blockers,
                status=_final_gate_preview_status(generic_status),
            )
        )
    return previews


def _product_backbone(rows: list[FamilyAdmissionRow]) -> ProductBackboneReadModel:
    examples = [_bnb_backbone_example()]
    for row in rows:
        examples.append(_row_backbone_example(row))
    return ProductBackboneReadModel(carrier_examples=examples)


def _action_candidate_specs(rows: list[FamilyAdmissionRow]) -> list[ActionCandidateSpec]:
    return [
        ActionCandidateSpec(
            family=row.family,
            carrier_id=row.carrier_id,
            admission_level=row.admission_level_code,
            status=_action_candidate_spec_status(row),
            action_registry_supported=row.action_api_compatibility.compatible,
            hard_blockers=_row_hard_blockers(row),
            warnings=list(row.risk_disclosure_contract.failure_modes),
            research_quality_status=row.research_quality_status,
            risk_disclosure_classifications=list(row.risk_disclosure_classifications),
            owner_risk_acceptance_required=row.owner_risk_acceptance_required,
            owner_risk_acceptance_may_override=list(row.owner_risk_acceptance_may_override),
            owner_risk_acceptance_never_overrides=list(
                row.owner_risk_acceptance_never_overrides
            ),
            post_action_acceptance_outputs=[
                "ExecutionIntent",
                "Entry",
                "TP/SL",
                "Review",
                "Audit",
            ],
        )
        for row in rows
    ]


def _generic_final_gate_adapter_contract() -> GenericFinalGateAdapterContract:
    return GenericFinalGateAdapterContract()


def _generic_action_specs(rows: list[FamilyAdmissionRow]) -> list[GenericActionSpec]:
    specs: list[GenericActionSpec] = []
    for row in rows:
        scope_template = _carrier_scope_template(row)
        status = _generic_action_spec_status(row, scope_template)
        hard_blockers = list(_row_hard_blockers(row))
        if status == "invalid_blocked":
            hard_blockers = _dedupe([*hard_blockers, "invalid GenericActionSpec"])
        payload_id = f"action-entry:{row.carrier_id or row.family}"
        specs.append(
            GenericActionSpec(
                family=row.family,
                strategy_family_id=row.strategy_family_id,
                carrier_id=row.carrier_id,
                admission_level=row.admission_level_code,
                status=status,
                action_registry_supported=row.action_api_compatibility.compatible,
                proposal_role=_proposal_role(row),
                market_regime=_market_regime_for_family(row.family),
                sizing_mode=_optional_str(scope_template.get("sizing_mode")) or "fixed_quantity",
                action_candidate_ref=f"action-candidate:{row.carrier_id or row.family}",
                supported_symbols=list(row.supported_symbols),
                supported_sides=_supported_sides_for_family(row.family),
                symbol=_optional_str(scope_template.get("symbol")),
                side=_optional_str(scope_template.get("side")),
                quantity=_optional_str(scope_template.get("quantity")),
                target_notional_usdt=_optional_str(scope_template.get("target_notional_usdt")),
                computed_quantity=_optional_str(scope_template.get("computed_quantity")),
                estimated_notional_usdt=_optional_str(scope_template.get("estimated_notional_usdt")),
                market_rule_snapshot=dict(scope_template.get("market_rule_snapshot") or {}),
                validation_result=dict(scope_template.get("validation_result") or {}),
                suggested_minimum_notional_usdt=_optional_str(scope_template.get("suggested_minimum_notional_usdt")),
                suggested_quantity=_optional_str(scope_template.get("suggested_quantity")),
                max_notional=_optional_str(scope_template.get("max_notional")),
                leverage=_optional_str(scope_template.get("leverage")),
                max_attempts=_optional_int(scope_template.get("max_attempts")),
                protection_mode=_optional_str(scope_template.get("protection_mode")),
                review_requirement=_optional_str(scope_template.get("review_requirement")),
                protection_template=_protection_template(row),
                review_template=_review_template_payload(row),
                warnings=list(row.risk_disclosure_contract.failure_modes),
                research_quality_status=row.research_quality_status,
                risk_disclosure_classifications=list(row.risk_disclosure_classifications),
                owner_risk_acceptance_required=row.owner_risk_acceptance_required,
                owner_risk_acceptance_status="required",
                owner_risk_acceptance_may_override=list(
                    row.owner_risk_acceptance_may_override
                ),
                owner_risk_acceptance_never_overrides=list(
                    row.owner_risk_acceptance_never_overrides
                ),
                owner_risk_acceptance_cannot_override_execution_safety_gates=(
                    row.owner_risk_acceptance_cannot_override_execution_safety_gates
                ),
                hard_blockers=hard_blockers,
                action_entry_payload_ref=payload_id,
            )
        )
    return specs


def _action_entry_payload_contracts(rows: list[FamilyAdmissionRow]) -> list[ActionEntryPayloadContract]:
    contracts: list[ActionEntryPayloadContract] = []
    for row in rows:
        scope_template = _carrier_scope_template(row)
        status = _generic_action_spec_status(row, scope_template)
        contracts.append(
            ActionEntryPayloadContract(
                family=row.family,
                carrier_id=row.carrier_id,
                payload_id=f"action-entry:{row.carrier_id or row.family}",
                contract_status=_action_entry_contract_status(status),
                official_action_path=list(OFFICIAL_ACTION_API_ENDPOINTS.values()),
                required_owner_scope=dict(scope_template),
                required_pre_action_facts=[
                    "exact Owner execute authorization",
                    "PG and exchange exposure snapshot",
                    "TP/SL protection plan",
                    "ExecutionIntent/order/review/audit recording readiness",
                    "runtime/profile/env/credential guard status",
                ],
                mandatory_protection_mode="single_tp_plus_sl",
                post_action_acceptance_outputs=[
                    "ExecutionIntent",
                    "Entry",
                    "TP/SL",
                    "Review",
                    "Audit",
                ],
            )
        )
    return contracts


def _trading_console_action_entry_output(
    rows: list[FamilyAdmissionRow],
) -> list[TradingConsoleActionEntryOutput]:
    output: list[TradingConsoleActionEntryOutput] = []
    for row in rows:
        scope_template = _carrier_scope_template(row)
        generic_status = _generic_action_spec_status(row, scope_template)
        output.append(
            TradingConsoleActionEntryOutput(
                family=row.family,
                strategy_family_id=row.strategy_family_id,
                carrier_id=row.carrier_id,
                admission_level=row.admission_level_code,
                action_entry_state=_action_entry_state(generic_status),
                generic_action_spec_status=generic_status,
                final_gate_adapter_status="contract_ready_blocked_until_gate_passes",
                action_registry_supported=row.action_api_compatibility.compatible,
                required_owner_scope_fields=list(REQUIRED_OWNER_SCOPE_FIELDS),
                warning_count=len(row.risk_disclosure_contract.failure_modes),
                hard_blocker_count=len(_row_hard_blockers(row)),
                owner_decision_text=_action_entry_owner_decision_text(row, generic_status),
                research_quality_status=row.research_quality_status,
                risk_disclosure_classifications=list(row.risk_disclosure_classifications),
                owner_risk_acceptance_required=row.owner_risk_acceptance_required,
                owner_risk_acceptance_cannot_override_execution_safety_gates=(
                    row.owner_risk_acceptance_cannot_override_execution_safety_gates
                ),
            )
        )
    return output


def _trading_console_candidate_output(rows: list[FamilyAdmissionRow]) -> list[TradingConsoleCandidateOutput]:
    return [
        TradingConsoleCandidateOutput(
            family=row.family,
            strategy_family_id=row.strategy_family_id,
            carrier_id=row.carrier_id,
            admission_level=row.admission_level_code,
            candidate_state=_candidate_state(row),
            action_candidate_status=row.action_candidate.status,
            action_registry_supported=row.action_api_compatibility.compatible,
            warning_count=len(row.risk_disclosure_contract.failure_modes),
            hard_blocker_count=len(_row_hard_blockers(row)),
            owner_decision_text=_owner_decision_text(row),
            research_quality_status=row.research_quality_status,
            risk_disclosure_classifications=list(row.risk_disclosure_classifications),
            owner_risk_acceptance_required=row.owner_risk_acceptance_required,
        )
        for row in rows
    ]


def _generic_action_spec_status(
    row: FamilyAdmissionRow,
    scope_template: dict[str, object],
) -> Literal["valid_blocked_final_gate", "proposal_non_action", "invalid_blocked"]:
    if row.action_api_compatibility.compatible and _scope_template_complete(scope_template):
        return "valid_blocked_final_gate"
    if row.carrier_id is not None and row.admission_level_code in {"L2", "L3"}:
        return "proposal_non_action"
    return "invalid_blocked"


def _scope_template_complete(scope_template: dict[str, object]) -> bool:
    required = [
        "symbol",
        "side",
        "quantity",
        "max_notional",
        "leverage",
        "max_attempts",
        "protection_mode",
        "review_requirement",
    ]
    return all(scope_template.get(field) not in (None, "") for field in required)


def _action_entry_contract_status(
    status: str,
) -> Literal["ready_for_final_gate_adapter", "proposal_only", "blocked_invalid_scope"]:
    if status == "valid_blocked_final_gate":
        return "ready_for_final_gate_adapter"
    if status == "proposal_non_action":
        return "proposal_only"
    return "blocked_invalid_scope"


def _action_entry_state(
    status: str,
) -> Literal["ready_for_owner_scope_final_gate", "proposal_only", "blocked"]:
    if status == "valid_blocked_final_gate":
        return "ready_for_owner_scope_final_gate"
    if status == "proposal_non_action":
        return "proposal_only"
    return "blocked"


def _action_entry_owner_decision_text(row: FamilyAdmissionRow, status: str) -> str:
    if status == "valid_blocked_final_gate":
        return (
            "Owner may review exact action-entry payload, but execution remains blocked "
            "until final gate facts, authorization, protection, review, and audit are ready."
        )
    if status == "proposal_non_action":
        return "Proposal only; this carrier is not action-registry-supported."
    return f"Blocked until {row.next_retry_condition}"


def _final_gate_preview_status(
    generic_status: str,
) -> Literal[
    "ready_for_official_final_gate_preview",
    "proposal_only",
    "blocked_invalid_scope",
]:
    if generic_status == "valid_blocked_final_gate":
        return "ready_for_official_final_gate_preview"
    if generic_status == "proposal_non_action":
        return "proposal_only"
    return "blocked_invalid_scope"


def _bnb_backbone_example() -> ProductBackboneCarrierExample:
    return ProductBackboneCarrierExample(
        example_id="backbone-example:MI-001-BNB-LONG",
        role="historical_regression_sample",
        family="BNB manual bounded live proof",
        strategy_family_id="MI-001",
        carrier_id="MI-001-BNB-LONG",
        admission_level="L0",
        symbol="BNB/USDT:USDT",
        side="long",
        quantity="0.01",
        max_notional="20",
        leverage="1",
        protection_template_id="protection-template:MI-001-BNB-LONG",
        review_template_id="review-template:MI-001-BNB-LONG",
        actionability="historical_proof_not_current_authorization",
        current_status="regression_sample_requires_fresh_scope_before_new_action",
        warnings=[],
        hard_blockers=[
            "fresh Owner authorization required",
            "fresh PG/exchange validation required",
            "FinalGate pass required",
        ],
        final_gate_preview_ref="final-gate-preview:MI-001-BNB-LONG",
    )


def _row_backbone_example(row: FamilyAdmissionRow) -> ProductBackboneCarrierExample:
    scope_template = _carrier_scope_template(row)
    if row.family == "Trend":
        role: Literal[
            "historical_regression_sample",
            "owner_confirmed_candidate",
            "budgeted_autonomy_sample",
            "proposal_dry_run_candidate",
        ] = "owner_confirmed_candidate"
        current_status = "l3_owner_scope_candidate_blocked_until_final_gate"
    elif row.family == "Mean reversion":
        role = "budgeted_autonomy_sample"
        current_status = "budget_envelope_compatible_proposal_blocked_until_scope_and_gate"
    else:
        role = "proposal_dry_run_candidate"
        current_status = "proposal_dry_run_not_live_enabled"
    return ProductBackboneCarrierExample(
        example_id=f"backbone-example:{row.carrier_id or row.family}",
        role=role,
        family=row.family,
        strategy_family_id=row.strategy_family_id,
        carrier_id=row.carrier_id,
        admission_level=row.admission_level_code,
        symbol=_optional_str(scope_template.get("symbol")),
        side=_optional_str(scope_template.get("side")),
        quantity=_optional_str(scope_template.get("quantity")),
        target_notional_usdt=_optional_str(scope_template.get("target_notional_usdt")),
        max_notional=_optional_str(scope_template.get("max_notional")),
        leverage=_optional_str(scope_template.get("leverage")),
        protection_template_id=f"protection-template:{row.carrier_id or row.family}",
        review_template_id=f"review-template:{row.carrier_id or row.family}",
        actionability=_action_candidate_spec_status(row),
        budgeted_autonomy_compatible=row.family == "Mean reversion",
        current_status=current_status,
        warnings=list(row.risk_disclosure_contract.failure_modes),
        hard_blockers=_row_hard_blockers(row),
        final_gate_preview_ref=f"final-gate-preview:{row.carrier_id or row.family}",
    )


def _optional_str(value: object) -> Optional[str]:
    if value in (None, ""):
        return None
    return str(value)


def _optional_int(value: object) -> Optional[int]:
    if value in (None, ""):
        return None
    return int(value)


def _carrier_scope_template(row: FamilyAdmissionRow) -> dict[str, object]:
    if row.carrier_id == "TF-001-live-readonly-v0":
        return {
            "symbol": "SOL/USDT:USDT",
            "side": "long",
            "sizing_mode": "fixed_quantity",
            "quantity": "0.1",
            "max_notional": "20",
            "leverage": "1",
            "max_attempts": 1,
            "protection_mode": "single_tp_plus_sl",
            "review_requirement": "post_action_review_required",
        }
    if row.carrier_id == "MR-001-live-readonly-v0":
        return {
            "symbol": "ETH/USDT:USDT",
            "side": "long",
            "sizing_mode": "notional_derived",
            "quantity": None,
            "target_notional_usdt": "22",
            "computed_quantity": None,
            "estimated_notional_usdt": None,
            "max_notional": "25",
            "leverage": "1",
            "max_attempts": 1,
            "protection_mode": "single_tp_plus_sl",
            "review_requirement": "post_action_review_required",
        }
    return {
        "symbol": row.supported_symbols[0] if row.supported_symbols else None,
        "side": "long",
        "quantity": None,
        "max_notional": None,
        "leverage": "1",
        "max_attempts": 1,
        "protection_mode": "single_tp_plus_sl",
        "review_requirement": "post_action_review_required",
    }


def _supported_sides_for_family(family: str) -> list[str]:
    return ["long"] if family in {"Trend", "Volatility expansion", "Mean reversion"} else []


def _proposal_role(
    row: FamilyAdmissionRow,
) -> Literal["trend_candidate", "range_candidate", "volatility_candidate", "unknown"]:
    if row.family == "Trend":
        return "trend_candidate"
    if row.family == "Mean reversion":
        return "range_candidate"
    if row.family == "Volatility expansion":
        return "volatility_candidate"
    return "unknown"


def _market_regime_for_family(family: str) -> Optional[str]:
    return {
        "Trend": "trend",
        "Mean reversion": "mean_reversion",
        "Volatility expansion": "volatility_expansion",
    }.get(family)


def _carrier_default_example(row: FamilyAdmissionRow) -> dict[str, object]:
    scope_template = _carrier_scope_template(row)
    return {
        "strategy_family_id": row.strategy_family_id,
        "carrier_id": row.carrier_id,
        "symbol": scope_template.get("symbol"),
        "side": scope_template.get("side"),
        "quantity": scope_template.get("quantity"),
        "target_notional_usdt": scope_template.get("target_notional_usdt"),
        "computed_quantity": scope_template.get("computed_quantity"),
        "estimated_notional_usdt": scope_template.get("estimated_notional_usdt"),
        "max_notional": scope_template.get("max_notional"),
        "leverage": scope_template.get("leverage"),
        "max_attempts": scope_template.get("max_attempts"),
        "protection_mode": scope_template.get("protection_mode"),
        "review_requirement": scope_template.get("review_requirement"),
        "may_execute_live": False,
        "places_order": False,
    }


def _protection_template(row: FamilyAdmissionRow) -> dict[str, object]:
    return {
        "template_id": f"protection-template:{row.carrier_id or row.family}",
        "mode": "single_tp_plus_sl",
        "mandatory": True,
        "requires_owner_confirmation": True,
        "hard_blockers": [
            "TP/SL plan unavailable",
            "protection price source unavailable",
            "reduce-only protection recording unavailable",
        ],
        "may_execute_live": False,
        "places_order": False,
    }


def _review_template_payload(row: FamilyAdmissionRow) -> dict[str, object]:
    return {
        "template_id": f"review-template:{row.carrier_id or row.family}",
        "metrics": list(row.review_contract.metrics),
        "required_sections": [
            "entry_result",
            "tp_sl_result",
            "pnl_summary",
            "protection_outcome",
            "failure_mode_notes",
            "next_iteration_decision",
        ],
        "pre_action_evidence_required": [
            "recording path available",
            "audit path available",
        ],
        "post_action_required": True,
    }


def _action_candidate_spec_status(row: FamilyAdmissionRow) -> str:
    if row.admission_level_code == "L0":
        return "not_available"
    if row.admission_level_code == "L3":
        return "owner_confirmed_candidate_blocked_final_gate"
    if row.admission_level_code == "L4":
        return "design_only"
    return "proposal"


def _candidate_state(row: FamilyAdmissionRow) -> str:
    if row.admission_level_code == "L3":
        return "bounded_live_candidate"
    if row.admission_level_code == "L2":
        return "proposal"
    if row.admission_level_code == "L1":
        return "displayable"
    return "parked"


def _owner_decision_text(row: FamilyAdmissionRow) -> str:
    if row.admission_level_code == "L3":
        return (
            "Owner may review exact bounded live scope; proceed only after explicit "
            "risk acceptance and all execution safety gates pass."
        )
    if row.admission_level_code == "L2":
        return (
            "Owner may review ActionCandidate proposal and accept disclosed evidence "
            "risk; no live action path until execution gates are available."
        )
    if row.admission_level_code == "L1":
        return "Owner may inspect a displayable candidate with risk-disclosure context."
    return "Parked or rejected candidate."


def _row_hard_blockers(row: FamilyAdmissionRow) -> list[str]:
    blockers: list[str] = []
    for record in row.gate_blocker_records:
        if record.severity == "hard_blocker":
            blockers.append(record.id)
    return _dedupe(blockers)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _family_configs() -> list[_FamilyConfig]:
    return [
        _FamilyConfig(
            family_type=StrategyFamilyType.TREND_FOLLOWING,
            family_label="Trend",
            strategy_group="Major trend continuation / trend following",
            classification="actionable",
            admission_level_code="L3",
            admission_level="Owner-confirmed action-capable carrier",
            risk_disclosure=(
                "Strategy warnings: weak current alpha proof, regime uncertainty, false continuation."
            ),
            failure_modes=[
                "weak current alpha proof",
                "regime uncertainty",
                "false continuation",
            ],
            research_quality_status="fragile_evidence",
            blocker_id="BRC-PROD-ADMIT-20260604-TREND-001",
            blocker_stage="BoundedLiveAuthorization",
            blocker_evidence=(
                "Trend carrier is in the official action registry, but no current explicit "
                "Owner authorization/live preflight evidence is attached to this read model."
            ),
            bridge_method="AuthorizationDraftProposal",
            next_retry_condition=(
                "Owner provides exact Trend scope, acknowledges risk, creates live authorization, "
                "and backend final gate passes with PG/exchange evidence plus TP/SL readiness."
            ),
        ),
        _FamilyConfig(
            family_type=StrategyFamilyType.VOLATILITY_BREAKOUT,
            family_label="Volatility expansion",
            strategy_group="Volatility contraction followed by breakout / release",
            classification="dry-run-only",
            admission_level_code="L2",
            admission_level="ActionCandidate proposal intake",
            risk_disclosure="Failure modes: fake breakout, news wick, low-volume breakout.",
            failure_modes=[
                "fake breakout",
                "news wick",
                "low-volume breakout",
            ],
            research_quality_status="insufficient_research",
            blocker_id="BRC-PROD-ADMIT-20260604-VOL-001",
            blocker_stage="BoundedLiveAuthorization",
            blocker_evidence=(
                "Volatility expansion is reviewable as an L2 ActionCandidate proposal, "
                "but it is not supported by the current official action API / FinalGate "
                "execution path for bounded live action."
            ),
            bridge_method="ActionCandidate",
            next_retry_condition=(
                "Official action API and FinalGate support the exact carrier, Owner accepts "
                "disclosed research risk, and all execution safety gates pass."
            ),
        ),
        _FamilyConfig(
            family_type=StrategyFamilyType.MEAN_REVERSION,
            family_label="Mean reversion",
            strategy_group="Range stretch / snapback",
            classification="dry-run-only",
            admission_level_code="L2",
            admission_level="ActionCandidate proposal intake",
            risk_disclosure=(
                "Failure modes: catching falling knife, range break into trend, liquidity wick."
            ),
            failure_modes=[
                "catching falling knife",
                "range break into trend",
                "liquidity wick",
            ],
            research_quality_status="insufficient_research",
            blocker_id="BRC-PROD-ADMIT-20260604-MR-001",
            blocker_stage="BoundedLiveAuthorization",
            blocker_evidence=(
                "Mean-reversion is reviewable as an L2 ActionCandidate proposal, "
                "but it is not supported by the current official action API / FinalGate "
                "execution path for bounded live action."
            ),
            bridge_method="ActionCandidate",
            next_retry_condition=(
                "Official action API and FinalGate support the exact carrier, Owner accepts "
                "disclosed research risk, and all execution safety gates pass."
            ),
        ),
    ]
