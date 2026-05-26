"""Bounded Risk Campaign domain models.

BRC is the outer business envelope for controlled personal risk campaigns.
It deliberately does not model alpha or exchange execution. Runtime exposure
gates and order placement remain outside this pure domain module.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class BrcCampaignStatus(str, Enum):
    OBSERVE = "observe"
    ACTIVE = "active"
    PROFIT_PROTECT = "profit_protect"
    LOSS_LOCKED = "loss_locked"
    ENDED = "ended"


class BrcAttemptStatus(str, Enum):
    ARMED = "armed"
    ENTRY_FILLED = "entry_filled"
    CLOSED = "closed"
    BLOCKED = "blocked"


class BrcDecisionResult(str, Enum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    REVIEW_REQUIRED = "review_required"


class RiskChangeDirection(str, Enum):
    SAME_RISK = "same_risk"
    INCREASED_RISK = "increased_risk"
    DECREASED_RISK = "decreased_risk"
    UNKNOWN = "unknown"


class MockPnlSource(str, Enum):
    TESTNET_MOCK = "testnet_mock"


class CampaignOutcome(str, Enum):
    ENDED_TESTNET_REHEARSAL_COMPLETE_LOSS_LOCKED = (
        "ended_testnet_rehearsal_complete_loss_locked"
    )
    ENDED_MANUAL_STOP = "ended_manual_stop"
    ENDED_RULE_VIOLATION = "ended_rule_violation"


class BrcNextEligibilityDecision(str, Enum):
    ALLOWED = "allowed"
    OBSERVE_ONLY = "observe_only"
    OWNER_REVIEW_REQUIRED = "owner_review_required"
    COOLDOWN_REQUIRED = "cooldown_required"
    BLOCKED = "blocked"


class BrcOperatorAction(str, Enum):
    READ_REVIEW_PACKET = "read_review_packet"
    READ_NEXT_ELIGIBILITY = "read_next_eligibility"
    READ_EVIDENCE = "read_evidence"
    UNKNOWN = "unknown"


class PlaybookEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    playbook_id: str
    name: str
    status: str = "active"
    evidence_state: str = "paper_only"
    associated_strategy_contract_id: Optional[str] = None
    allows_controlled_testnet: bool = False
    minimum_hold_days: int = Field(default=0, ge=0)


class RiskCapitalBucket(BaseModel):
    model_config = ConfigDict(frozen=True)

    bucket_id: str
    currency: str = "USDT"
    authorized_amount: Decimal = Field(gt=Decimal("0"))
    refill_allowed: bool = False


class RiskEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_campaign_loss: Decimal = Field(gt=Decimal("0"))
    profit_protect_trigger: Decimal = Field(gt=Decimal("0"))
    max_attempts: int = Field(default=2, ge=1)
    max_simultaneous_positions: int = Field(default=1, ge=1)
    max_leverage: int = Field(default=1, ge=1)
    allowed_profile: str = "brc_btc_eth_testnet_runtime"
    allowed_symbols: tuple[str, ...] = ("ETH/USDT:USDT", "BTC/USDT:USDT")
    no_loss_counter_reset_on_switch: bool = True
    no_refill_after_loss: bool = True


class CampaignAttempt(BaseModel):
    attempt_id: str
    symbol: str
    status: BrcAttemptStatus
    armed_at_ms: int
    entry_at_ms: Optional[int] = None
    closed_at_ms: Optional[int] = None
    intent_id: Optional[str] = None
    signal_id: Optional[str] = None
    close_order_id: Optional[str] = None
    exchange_order_id: Optional[str] = None
    amount: Optional[Decimal] = None
    notional: Optional[Decimal] = None


class PlaybookSwitchDecision(BaseModel):
    switch_id: str
    campaign_id: str
    previous_playbook_id: str
    new_playbook_id: str
    switched_at_ms: int
    decided_by: str = "owner"
    reason_category: str
    reason_text: str = Field(min_length=1, max_length=1024)
    evidence_refs: list[str] = Field(default_factory=list)
    risk_change_direction: RiskChangeDirection = RiskChangeDirection.SAME_RISK
    campaign_pnl_at_switch: Decimal
    attempt_count_at_switch: int
    campaign_status_at_switch: BrcCampaignStatus
    decision_result: BrcDecisionResult
    blocked_reason: Optional[str] = None
    inferred_fields: dict[str, Any] = Field(default_factory=dict)


class MockPnlEvent(BaseModel):
    event_id: str
    campaign_id: str
    amount: Decimal
    cumulative_pnl: Decimal
    source: MockPnlSource
    reason: str = Field(min_length=1, max_length=512)
    occurred_at_ms: int
    triggered_state: Optional[BrcCampaignStatus] = None

    @field_validator("amount")
    @classmethod
    def _amount_nonzero(cls, value: Decimal) -> Decimal:
        if value == Decimal("0"):
            raise ValueError("mock pnl amount must be non-zero")
        return value


class BrcInvariantCheck(BaseModel):
    name: str
    passed: bool
    detail: str


class BrcReviewPacket(BaseModel):
    campaign_id: str
    status: BrcCampaignStatus
    outcome: Optional[CampaignOutcome] = None
    current_playbook_id: str
    realized_pnl: Decimal
    authorized_amount: Decimal
    max_campaign_loss: Decimal
    profit_protect_trigger: Decimal
    attempt_count: int
    max_attempts: int
    switch_count: int
    mock_pnl_event_count: int
    profit_protect_triggered: bool
    loss_lock_triggered: bool
    all_attempts_closed: bool
    final_inventory_flat: Optional[bool] = None
    invariant_checks: list[BrcInvariantCheck]
    evidence: dict[str, Any]
    live_ready: bool = False
    withdrawal_executed: bool = False


class BrcNextCampaignEligibility(BaseModel):
    decision: BrcNextEligibilityDecision
    reason: str
    campaign_id: Optional[str] = None
    latest_status: Optional[BrcCampaignStatus] = None
    latest_outcome: Optional[CampaignOutcome] = None
    recommended_playbook_id: str = "PB-000-OBSERVE-ONLY"
    owner_review_required: bool = True
    cooldown_required: bool = False
    next_campaign_allowed: bool = False
    blocked_reasons: list[str] = Field(default_factory=list)
    required_actions: list[str] = Field(default_factory=list)
    live_ready: bool = False


class BrcOperatorIntentDraft(BaseModel):
    source_text: str = Field(min_length=1, max_length=2048)
    action: BrcOperatorAction
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    http_method: str = "GET"
    endpoint_path: Optional[str] = None
    mutation_intended: bool = False
    executable_without_owner_confirmation: bool = False
    owner_confirmation_required: bool = False
    blocked_reason: Optional[str] = None
    live_ready: bool = False


class BoundedRiskCampaign(BaseModel):
    campaign_id: str
    bucket: RiskCapitalBucket
    risk_envelope: RiskEnvelope
    current_playbook_id: str = "PB-000-OBSERVE-ONLY"
    status: BrcCampaignStatus = BrcCampaignStatus.OBSERVE
    realized_pnl: Decimal = Decimal("0")
    attempt_count: int = 0
    attempts: list[CampaignAttempt] = Field(default_factory=list)
    outcome: Optional[CampaignOutcome] = None
    created_at_ms: int
    updated_at_ms: int
    finalized_at_ms: Optional[int] = None

    @model_validator(mode="after")
    def _validate_realized_pnl_state(self) -> "BoundedRiskCampaign":
        if self.status == BrcCampaignStatus.LOSS_LOCKED:
            if self.realized_pnl > -self.risk_envelope.max_campaign_loss:
                raise ValueError("loss_locked requires pnl at or below max_campaign_loss")
        if self.attempt_count > self.risk_envelope.max_attempts:
            raise ValueError("attempt_count exceeds max_attempts")
        return self

    @property
    def last_attempt(self) -> Optional[CampaignAttempt]:
        return self.attempts[-1] if self.attempts else None


def default_playbook_catalog() -> dict[str, PlaybookEntry]:
    entries = [
        PlaybookEntry(
            playbook_id="PB-000-OBSERVE-ONLY",
            name="Observe Only",
            status="active",
            evidence_state="always_available",
        ),
        PlaybookEntry(
            playbook_id="PB-001-DIRECTION-A-PAPER",
            name="Direction A Paper",
            status="observe_only",
            evidence_state="pause_fragile",
        ),
        PlaybookEntry(
            playbook_id="PB-002-SQ02-DOWNSIDE-PAPER",
            name="SQ02 Downside Paper",
            status="observe_only",
            evidence_state="docs_only",
        ),
        PlaybookEntry(
            playbook_id="PB-003-MANUAL-DISCRETIONARY",
            name="Manual Discretionary",
            status="paper_only",
            evidence_state="owner_discretion",
        ),
        PlaybookEntry(
            playbook_id="PB-004-BRC-CONTROLLED-TESTNET",
            name="BRC Controlled Testnet",
            status="active",
            evidence_state="controlled_rehearsal_only",
            allows_controlled_testnet=True,
        ),
    ]
    return {entry.playbook_id: entry for entry in entries}
