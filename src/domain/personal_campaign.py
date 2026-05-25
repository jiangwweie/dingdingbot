"""Personal Leveraged Campaign local-domain contracts.

These objects describe a disabled-by-default local sandbox chain only. They do
not authorize exchange access, runtime wiring, paper/testnet/live trading,
real orders, transfers, or withdrawals.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.models import Direction


class CampaignModel(BaseModel):
    """Base model for local campaign value objects."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")


class CampaignDecision(str, Enum):
    ALLOW = "allow"
    REJECT = "reject"


class ModeDefaultAction(str, Enum):
    OBSERVE = "observe"
    ARM = "arm"
    PAUSE = "pause"
    IGNORE = "ignore"


class HumanArmAction(str, Enum):
    ARM = "arm"
    PAUSE = "pause"
    REJECT = "reject"


class CampaignLifecycleStatus(str, Enum):
    OBSERVE = "observe"
    ARMED = "armed"
    PAUSED = "paused"
    HARD_LOCKED = "hard_locked"


class TradeIntentAction(str, Enum):
    ENTER = "enter"
    EXIT = "exit"
    REDUCE = "reduce"
    NONE = "none"


class ExecutionReceiptStatus(str, Enum):
    NOT_SUBMITTED = "not_submitted"
    SIMULATED_ACCEPTED = "simulated_accepted"
    BLOCKED = "blocked"


class PositionProtectionStatus(str, Enum):
    NONE = "none"
    PROTECTED = "protected"
    PROTECTION_MISSING = "protection_missing"


class PositionLifecycleStatus(str, Enum):
    NO_POSITION = "no_position"
    OPEN_PROTECTED = "open_protected"
    REDUCE_REQUIRED = "reduce_required"
    CLOSE_REQUIRED = "close_required"
    HARD_LOCKED = "hard_locked"


class CampaignInvariantStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"


class ModeAdvice(CampaignModel):
    """System-generated review packet; not a trading decision."""

    mode_id: str
    strategy_contract_id: str
    why: str
    evidence: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    default_action: ModeDefaultAction = ModeDefaultAction.OBSERVE
    llm_role: str = "explain_audit_suggest_only"


class HumanArmDecision(CampaignModel):
    """Owner authority for a bounded strategy session."""

    decision: HumanArmAction
    strategy_contract_id: str
    campaign_id: str
    session_id: str
    allowed_from_ms: int
    allowed_until_ms: int
    decided_by: str
    audit_provenance: str
    reason: str

    @model_validator(mode="after")
    def validate_session_window(self) -> "HumanArmDecision":
        if self.allowed_until_ms <= self.allowed_from_ms:
            raise ValueError("allowed_until_ms must be greater than allowed_from_ms")
        return self


class FeatureSnapshot(CampaignModel):
    """Closed/prior local feature snapshot for deterministic contract evaluation."""

    snapshot_id: str
    strategy_contract_id: str
    source: str = "local_sandbox_closed_or_prior"
    feature_timestamp_ms: int = Field(..., ge=0)
    input_scope: str = "closed_or_prior_inputs_only"
    conditions: dict[str, bool]
    forbidden_data: list[str] = Field(
        default_factory=lambda: [
            "lookahead",
            "llm_trade_decision",
            "real_account_state",
            "exchange_api_state",
        ]
    )
    llm_trade_decision_used: bool = False

    @model_validator(mode="after")
    def validate_feature_boundary(self) -> "FeatureSnapshot":
        if self.input_scope != "closed_or_prior_inputs_only":
            raise ValueError("feature snapshot input_scope must be closed_or_prior_inputs_only")
        required_forbidden = {
            "lookahead",
            "llm_trade_decision",
            "real_account_state",
            "exchange_api_state",
        }
        if not required_forbidden.issubset(set(self.forbidden_data)):
            raise ValueError("feature snapshot must forbid lookahead, LLM, account, and exchange state")
        if self.llm_trade_decision_used:
            raise ValueError("feature snapshot must not use LLM trade decisions")
        return self


class StrategyContract(CampaignModel):
    """Deterministic strategy carrier for local sandbox use."""

    strategy_contract_id: str
    strategy_name: str
    contract_status: str = "frozen"
    disabled_by_default: bool = True
    runtime_label: str = "LOCAL_SANDBOX_ONLY_DISABLED_BY_DEFAULT"
    setup_condition_key: str
    invalidation_condition_key: str
    entry_action: TradeIntentAction = TradeIntentAction.ENTER
    direction: Direction
    required_feature_snapshot: list[str]
    forbidden_data: list[str] = Field(default_factory=lambda: ["lookahead", "llm_trade_decision"])
    no_lookahead_rule: str = "closed_or_prior_inputs_only"


class TradeIntent(CampaignModel):
    """Desired strategy action without exchange side effects."""

    decision: CampaignDecision
    strategy_contract_id: str
    campaign_id: str
    session_id: str
    direction: Optional[Direction] = None
    action: TradeIntentAction = TradeIntentAction.NONE
    trigger_reason: str
    invalidation_reason: Optional[str] = None
    evidence_text: Optional[str] = None
    no_exchange_side_effect: bool = True


class ReadOnlyRuntimeAdapterPreview(CampaignModel):
    """Read-only runtime inspection payload for PLC promotion Phase 1."""

    adapter_version: str = "plc_read_only_runtime_adapter_v1"
    read_only: Literal[True] = True
    authority: Literal["read_only_no_order_authority"] = "read_only_no_order_authority"
    source_snapshot_id: str
    snapshot_feature_timestamp_ms: int = Field(..., ge=0)
    runtime_clock_ms: int = Field(..., ge=0)
    strategy_contract_id: str
    strategy_contract_status: str
    trade_intent: TradeIntent
    rejection_reasons: list[str] = Field(default_factory=list)
    no_exchange_side_effect: Literal[True] = True


class CampaignRiskCaps(CampaignModel):
    """Owner-fixed local sandbox caps used by deterministic checks."""

    risk_capital: Decimal = Field(..., gt=Decimal("0"))
    max_order_loss: Decimal = Field(..., gt=Decimal("0"))
    max_campaign_loss: Decimal = Field(..., gt=Decimal("0"))
    max_notional: Decimal = Field(..., gt=Decimal("0"))
    max_leverage: int = Field(..., ge=1)
    profit_protect_threshold: Decimal = Field(..., gt=Decimal("0"))


class PlannedOrder(CampaignModel):
    """Simulated order structure. It is not an exchange order."""

    symbol: str
    side: Direction
    notional: Decimal = Field(..., gt=Decimal("0"))
    leverage: int = Field(..., ge=1)
    max_loss: Decimal = Field(..., gt=Decimal("0"))
    order_type: str = "simulated_market"


class RiskOrderPlan(CampaignModel):
    """Risk decision boundary between intent and any future execution path."""

    decision: CampaignDecision
    campaign_id: str
    session_id: str
    strategy_contract_id: str
    reasons: list[str] = Field(default_factory=list)
    owner_fixed_caps_used: CampaignRiskCaps
    planned_order: Optional[PlannedOrder] = None
    protection_requirements: list[str] = Field(default_factory=list)
    rollback_and_cancellation: str = "local_plan_only_no_exchange_side_effect"


class ExecutionReceipt(CampaignModel):
    """Local simulated receipt for the sandbox lifecycle."""

    status: ExecutionReceiptStatus
    campaign_id: str
    session_id: str
    strategy_contract_id: str
    simulated_order_id: Optional[str] = None
    acknowledgement: Optional[str] = None
    reconciliation_reference: Optional[str] = None
    protection_status: PositionProtectionStatus = PositionProtectionStatus.NONE
    lifecycle_status: PositionLifecycleStatus = PositionLifecycleStatus.NO_POSITION


class PositionLifecycleState(CampaignModel):
    """Position lifecycle state derived from simulated receipts and risk rules."""

    campaign_id: str
    session_id: str
    source_of_truth: str = "local_sandbox"
    status: PositionLifecycleStatus
    protection_state: PositionProtectionStatus
    reduce_or_close_required: bool = False
    hard_lock_required: bool = False
    reasons: list[str] = Field(default_factory=list)


class CampaignState(CampaignModel):
    """Campaign-level control state."""

    campaign_id: str
    capital_bucket: Decimal = Field(..., ge=Decimal("0"))
    status: CampaignLifecycleStatus = CampaignLifecycleStatus.OBSERVE
    active_strategy_contract_id: Optional[str] = None
    active_session_id: Optional[str] = None
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    loss_lock: bool = False
    profit_protect_active: bool = False
    hard_lock_reason: Optional[str] = None
    rule_version: str = "personal_campaign_local_v0"
    invariant_checks: list[str] = Field(default_factory=list)

    @property
    def total_pnl(self) -> Decimal:
        return self.realized_pnl + self.unrealized_pnl


class SandboxOrderRequest(CampaignModel):
    """Local-only order planning request derived from a trade intent."""

    symbol: str
    notional: Decimal = Field(..., gt=Decimal("0"))
    leverage: int = Field(..., ge=1)
    max_loss: Decimal = Field(..., gt=Decimal("0"))
    feature_snapshot: dict[str, Any] = Field(default_factory=dict)


class CampaignSandboxSettings(CampaignModel):
    """Explicit local sandbox switch; defaults to disabled."""

    enabled: bool = False
    scenario_id: str = "personal_campaign_local_sandbox"
    runtime_effect: str = "none"
    trading_permission_effect: str = "none"
    external_side_effects_allowed: bool = False

    @model_validator(mode="after")
    def validate_local_only(self) -> "CampaignSandboxSettings":
        if self.external_side_effects_allowed:
            raise ValueError("personal campaign sandbox forbids external side effects")
        if self.runtime_effect != "none":
            raise ValueError("personal campaign sandbox runtime_effect must be none")
        if self.trading_permission_effect != "none":
            raise ValueError("personal campaign sandbox trading_permission_effect must be none")
        return self


class CampaignSandboxScenario(CampaignModel):
    """Named local scenario for repeated sandbox verification."""

    scenario_id: str
    description: str
    settings: CampaignSandboxSettings = Field(default_factory=CampaignSandboxSettings)
    mode_advice: ModeAdvice
    human_arm_decision: HumanArmDecision
    strategy_contract: StrategyContract
    initial_campaign_state: CampaignState
    caps: CampaignRiskCaps
    order_request: SandboxOrderRequest
    feature_snapshot: FeatureSnapshot
    realized_pnl_delta: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    protection_missing: bool = False


class CampaignSandboxTrace(CampaignModel):
    """End-to-end local trace for review and regression tests."""

    settings: CampaignSandboxSettings
    mode_advice: ModeAdvice
    human_arm_decision: HumanArmDecision
    strategy_contract: StrategyContract
    trade_intent: TradeIntent
    risk_order_plan: RiskOrderPlan
    execution_receipt: ExecutionReceipt
    position_lifecycle_state: PositionLifecycleState
    campaign_state: CampaignState
    safety_assertions: list[str] = Field(
        default_factory=lambda: [
            "local_only",
            "no_exchange_api",
            "no_real_account",
            "no_order_side_effect",
            "no_transfer_or_withdrawal_path",
            "owner_handles_withdrawal_outside_system",
            "llm_explain_audit_suggest_only",
        ]
    )


class CampaignTraceInvariantReport(CampaignModel):
    """Local invariant evaluation result for a sandbox trace."""

    status: CampaignInvariantStatus
    scenario_id: str
    checks_passed: list[str] = Field(default_factory=list)
    violations: list[str] = Field(default_factory=list)
