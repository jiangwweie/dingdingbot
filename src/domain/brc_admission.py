"""BRC admission gate domain models.

These models describe PG-backed admission facts only. They do not create
campaigns, execute runtime actions, place orders, or authorize live trading.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AdmissionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TrialEnv(str, Enum):
    TESTNET = "testnet"
    LIVE = "live"


class TrialStage(str, Enum):
    DEVELOPMENT_VALIDATION = "development_validation"
    FUNDED_VALIDATION = "funded_validation"


class AdmissionExecutionMode(str, Enum):
    AUTO_WITHIN_BUDGET = "auto_within_budget"
    OWNER_CONFIRM_EACH_ENTRY = "owner_confirm_each_entry"
    OBSERVE_ONLY = "observe_only"
    NO_ENTRY = "no_entry"


class AdmissionDecisionValue(str, Enum):
    ADMIT = "admit"
    ADMIT_WITH_CONSTRAINTS = "admit_with_constraints"
    REJECT = "reject"
    PARK = "park"


class TrialConstraintSnapshotStatus(str, Enum):
    PENDING_RISK_CAPITAL_RESOLUTION = "pending_risk_capital_resolution"
    INSTALLABLE = "installable"
    INSTALLED = "installed"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"


class AdmissionTrialBindingStatus(str, Enum):
    PLANNED = "planned"
    BINDING_RESERVED = "binding_reserved"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"
    CAMPAIGN_CREATED = "campaign_created"
    RUNTIME_CONSTRAINTS_INSTALLED = "runtime_constraints_installed"
    RUNTIME_INSTALLED = "runtime_installed"


class StrategyFamilyStatus(str, Enum):
    ACTIVE = "active"
    INTAKE = "intake"
    PARKED = "parked"
    REJECTED = "rejected"


class AdmissionAuditEventType(str, Enum):
    FAMILY_CREATED = "family_created"
    FAMILY_VERSION_CREATED = "family_version_created"
    FAMILY_VERSION_SCOPE_SYNCED = "family_version_scope_synced"
    ADMISSION_EVIDENCE_CREATED = "admission_evidence_created"
    OWNER_REGIME_INPUT_CREATED = "owner_regime_input_created"
    ADMISSION_REQUEST_CREATED = "admission_request_created"
    ADMISSION_EVALUATED = "admission_evaluated"
    OWNER_RISK_ACCEPTANCE_CREATED = "owner_risk_acceptance_created"
    ADMISSION_TRIAL_BINDING_RESERVED = "admission_trial_binding_reserved"
    ADMISSION_TRIAL_CAMPAIGN_CREATED = "admission_trial_campaign_created"
    ADMISSION_RUNTIME_CONSTRAINTS_INSTALLED = "admission_runtime_constraints_installed"
    ADMISSION_RUNTIME_CARRIER_READY = "admission_runtime_carrier_ready"
    ADMISSION_RUNTIME_START_READY = "admission_runtime_start_ready"
    ADMISSION_RUNTIME_HANDOFF_READY = "admission_runtime_handoff_ready"
    ADMISSION_RUNTIME_STARTED = "admission_runtime_started"
    ADMISSION_STRATEGY_ACTIVATION_READY = "admission_strategy_activation_ready"
    ADMISSION_STRATEGY_ACTIVATED_NO_EXECUTION = "admission_strategy_activated_no_execution"
    ADMISSION_SIGNAL_LOOP_READY = "admission_signal_loop_ready"
    ADMISSION_SIGNAL_LOOP_STARTED_NO_SIGNAL = "admission_signal_loop_started_no_signal"
    ADMISSION_SIGNAL_EVALUATED_NO_INTENT = "admission_signal_evaluated_no_intent"
    ADMISSION_TRIAL_TRADE_INTENT_EVALUATED = "admission_trial_trade_intent_evaluated"
    ADMISSION_TRIAL_BINDING_CANCELLED = "admission_trial_binding_cancelled"
    ADMISSION_TRIAL_BINDING_INVALIDATED = "admission_trial_binding_invalidated"


class TrialTradeIntentDecision(str, Enum):
    RECORDED = "recorded"
    BLOCKED = "blocked"
    UNAVAILABLE = "unavailable"


class StrategyFamily(AdmissionModel):
    strategy_family_id: str
    family_key: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=256)
    description: str = Field(default="", max_length=4096)
    status: StrategyFamilyStatus = StrategyFamilyStatus.INTAKE
    owner: str = Field(default="owner", max_length=128)
    created_at_ms: int
    updated_at_ms: int


class StrategyFamilyVersion(AdmissionModel):
    strategy_family_version_id: str
    strategy_family_id: str
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
    created_at_ms: int
    created_by: str = Field(default="owner", max_length=128)
    is_current: bool = True


class AdmissionRuleConfig(AdmissionModel):
    admission_rule_config_id: str
    config_key: str = Field(min_length=1, max_length=128)
    version: int = Field(ge=1)
    status: str = Field(default="active", max_length=32)
    rule_details_json: dict[str, Any] = Field(default_factory=dict)
    system_boundaries_json: dict[str, Any] = Field(default_factory=dict)
    relaxable_safeguards_json: dict[str, Any] = Field(default_factory=dict)
    created_at_ms: int
    created_by: str = Field(default="system", max_length=128)


class AdmissionEvidence(AdmissionModel):
    admission_evidence_id: str
    strategy_family_version_id: str
    payload_json: dict[str, Any] = Field(default_factory=dict)
    mandatory_complete: bool = False
    created_at_ms: int
    created_by: str = Field(default="owner", max_length=128)


class OwnerMarketRegimeInput(AdmissionModel):
    owner_market_regime_input_id: str
    current_regime: str = Field(min_length=1, max_length=128)
    confidence: str = Field(default="unknown", max_length=64)
    rationale: str = Field(default="", max_length=4096)
    market_facts_snapshot_json: dict[str, Any] = Field(default_factory=dict)
    created_at_ms: int
    created_by: str = Field(default="owner", max_length=128)


class AdmissionRequest(AdmissionModel):
    admission_request_id: str
    strategy_family_version_id: str
    admission_evidence_id: str
    owner_market_regime_input_id: str
    trial_env: TrialEnv
    trial_stage: TrialStage
    requested_execution_mode: Optional[AdmissionExecutionMode] = None
    requested_risk_profile: str = Field(default="micro", max_length=64)
    admission_rule_config_id: Optional[str] = Field(default=None, max_length=128)
    account_facts_snapshot_ref: Optional[str] = Field(default=None, max_length=256)
    account_facts_snapshot_json: dict[str, Any] = Field(default_factory=dict)
    playbook_id: Optional[str] = Field(default=None, max_length=128)
    playbook_catalog_snapshot_json: dict[str, Any] = Field(default_factory=dict)
    created_at_ms: int
    requested_by: str = Field(default="owner", max_length=128)


class TrialConstraintSnapshot(AdmissionModel):
    trial_constraint_snapshot_id: str
    admission_request_id: str
    status: TrialConstraintSnapshotStatus
    risk_profile: str = Field(default="micro", max_length=64)
    risk_policy_version: Optional[str] = Field(default=None, max_length=128)
    constraints_json: dict[str, Any] = Field(default_factory=dict)
    risk_policy_snapshot_json: dict[str, Any] = Field(default_factory=dict)
    adapter_result_json: dict[str, Any] = Field(default_factory=dict)
    created_at_ms: int
    expires_at_ms: Optional[int] = None


class AdmissionDecision(AdmissionModel):
    admission_decision_id: str
    admission_request_id: str
    decision: AdmissionDecisionValue
    trial_env: TrialEnv
    trial_stage: TrialStage
    strategy_family_version_id: str
    playbook_id: Optional[str] = None
    playbook_catalog_snapshot_json: dict[str, Any] = Field(default_factory=dict)
    owner_market_regime_input_id: str
    admission_evidence_id: str
    admission_rule_config_id: str
    trial_constraint_snapshot_id: str
    risk_profile: str = Field(default="micro", max_length=64)
    execution_mode: AdmissionExecutionMode
    degradation_applied: bool = False
    risk_intent_json: dict[str, Any] = Field(default_factory=dict)
    degradation_intent_json: dict[str, Any] = Field(default_factory=dict)
    blockers_json: list[str] = Field(default_factory=list)
    warnings_json: list[str] = Field(default_factory=list)
    risk_disclosure_json: dict[str, Any] = Field(default_factory=dict)
    known_gaps_json: dict[str, Any] = Field(default_factory=dict)
    constraints_snapshot_json: dict[str, Any] = Field(default_factory=dict)
    owner_risk_acceptance_id: Optional[str] = None
    expires_at_ms: Optional[int] = None
    created_at_ms: int


class OwnerRiskAcceptance(AdmissionModel):
    owner_risk_acceptance_id: str
    admission_request_id: str
    admission_decision_id: Optional[str] = None
    strategy_family_version_id: str
    trial_env: TrialEnv
    trial_stage: TrialStage
    account_facts_snapshot_ref: Optional[str] = Field(default=None, max_length=256)
    risk_profile: str = Field(max_length=64)
    risk_policy_snapshot_json: dict[str, Any] = Field(default_factory=dict)
    constraint_snapshot_id: str
    risk_disclosure_snapshot_json: dict[str, Any] = Field(default_factory=dict)
    known_gaps_snapshot_json: dict[str, Any] = Field(default_factory=dict)
    owner_rationale: str = Field(default="", max_length=4096)
    confirmation_phrase: str = Field(min_length=1, max_length=128)
    confirmation_marker: str = Field(default="owner_confirmed_risk_acceptance", max_length=128)
    confirmed_at_ms: int
    created_at_ms: int
    created_by: str = Field(default="owner", max_length=128)

    @model_validator(mode="after")
    def _funded_validation_requires_account_ref(self) -> "OwnerRiskAcceptance":
        if self.trial_stage == TrialStage.FUNDED_VALIDATION and not self.account_facts_snapshot_ref:
            raise ValueError("funded_validation risk acceptance requires account_facts_snapshot_ref")
        return self


class AdmissionAuditLog(AdmissionModel):
    audit_id: str
    event_type: AdmissionAuditEventType
    ref_type: str = Field(min_length=1, max_length=128)
    ref_id: str = Field(min_length=1, max_length=128)
    admission_request_id: Optional[str] = Field(default=None, max_length=128)
    admission_decision_id: Optional[str] = Field(default=None, max_length=128)
    actor: str = Field(default="system", max_length=128)
    message: str = Field(default="", max_length=2048)
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at_ms: int


class AdmissionTrialBinding(AdmissionModel):
    binding_id: str
    admission_decision_id: str
    owner_risk_acceptance_id: Optional[str] = None
    trial_constraint_snapshot_id: str
    strategy_family_version_id: str
    playbook_id: str = Field(min_length=1, max_length=128)
    playbook_catalog_snapshot_json: dict[str, Any] = Field(default_factory=dict)
    trial_env: TrialEnv
    trial_stage: TrialStage
    execution_mode: AdmissionExecutionMode
    binding_status: AdmissionTrialBindingStatus
    campaign_id: Optional[str] = Field(default=None, max_length=128)
    runtime_carrier_id: Optional[str] = Field(default=None, max_length=128)
    created_by_operation_id: str = Field(min_length=1, max_length=128)
    created_by_preflight_id: str = Field(min_length=1, max_length=128)
    created_at_ms: int
    updated_at_ms: int
    invalidated_at_ms: Optional[int] = None
    invalidation_reason: Optional[str] = Field(default=None, max_length=2048)

    @model_validator(mode="after")
    def _reserved_binding_is_not_runtime_started(self) -> "AdmissionTrialBinding":
        if self.binding_status in {
            AdmissionTrialBindingStatus.PLANNED,
            AdmissionTrialBindingStatus.BINDING_RESERVED,
        }:
            if self.campaign_id is not None or self.runtime_carrier_id is not None:
                raise ValueError("planned/reserved binding cannot reference a campaign or runtime carrier")
        return self


class TrialTradeIntent(AdmissionModel):
    """Non-executable evidence record for execution-mode enforcement.

    This is not an order, execution intent, or runtime command.
    """

    intent_id: str
    campaign_id: str = Field(min_length=1, max_length=128)
    binding_id: Optional[str] = Field(default=None, max_length=128)
    admission_decision_id: Optional[str] = Field(default=None, max_length=128)
    strategy_family_version_id: Optional[str] = Field(default=None, max_length=128)
    playbook_id: Optional[str] = Field(default=None, max_length=128)
    execution_mode: AdmissionExecutionMode
    intended_action: str = Field(min_length=1, max_length=64)
    symbol: str = Field(min_length=1, max_length=128)
    side: Optional[str] = Field(default=None, max_length=32)
    signal_snapshot_json: dict[str, Any] = Field(default_factory=dict)
    market_snapshot_json: dict[str, Any] = Field(default_factory=dict)
    risk_snapshot_json: dict[str, Any] = Field(default_factory=dict)
    decision: TrialTradeIntentDecision
    not_executed_reason: str = Field(min_length=1, max_length=2048)
    created_at_ms: int
    created_by_operation_id: Optional[str] = Field(default=None, max_length=128)
    audit_refs_json: dict[str, Any] = Field(default_factory=dict)


class RiskCapitalAdapterResult(AdmissionModel):
    status: TrialConstraintSnapshotStatus
    risk_profile: str = Field(default="micro", max_length=64)
    risk_policy_version: Optional[str] = Field(default=None, max_length=128)
    constraints_json: dict[str, Any] = Field(default_factory=dict)
    risk_policy_snapshot_json: dict[str, Any] = Field(default_factory=dict)
    adapter_result_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _phase1_status_is_constraint_status(self) -> "RiskCapitalAdapterResult":
        if self.status == TrialConstraintSnapshotStatus.INSTALLED:
            raise ValueError("RiskCapitalAdapter cannot return installed before Operation confirm")
        return self
