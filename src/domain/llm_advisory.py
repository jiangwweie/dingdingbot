"""LLM advisory plane domain models.

The advisory plane consumes typed system events and structured context packets.
It may recommend registered strategy families or summarize audit evidence, but
it never creates execution authority, order parameters, transfers, or
withdrawal instructions.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class LlmAdvisoryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LlmConsumableEventType(str, Enum):
    MARKET_REGIME_CHANGED = "market_regime_changed"
    STRATEGY_CANDIDATE_OBSERVED = "strategy_candidate_observed"
    RUNTIME_BUDGET_CHANGED = "runtime_budget_changed"
    FINAL_GATE_BLOCKED = "final_gate_blocked"
    ORDER_CANDIDATE_CREATED = "order_candidate_created"
    PROTECTION_ANOMALY_DETECTED = "protection_anomaly_detected"
    RECONCILIATION_MISMATCH = "reconciliation_mismatch"
    TRADE_CLOSED = "trade_closed"
    REVIEW_DUE = "review_due"
    DAILY_AUDIT_DIGEST = "daily_audit_digest"
    OWNER_REQUESTED_ANALYSIS = "owner_requested_analysis"


class LlmAdvisoryAllowedAction(str, Enum):
    SUMMARIZE_AUDIT = "summarize_audit"
    RECOMMEND_REGISTERED_STRATEGY_FAMILY = "recommend_registered_strategy_family"
    EXPLAIN_BLOCKER = "explain_blocker"
    REVIEW_CLOSED_TRADE = "review_closed_trade"
    EXPLAIN_MARKET_CONTEXT = "explain_market_context"


class LlmAdvisoryDeliveryChannel(str, Enum):
    LEDGER_ONLY = "ledger_only"
    CONSOLE = "console"
    FEISHU_PUSH = "feishu_push"


class LlmFeishuCardType(str, Enum):
    CANDIDATE_REVIEW = "candidate_review"
    FINAL_GATE_BLOCKED = "final_gate_blocked"
    DAILY_AUDIT_DIGEST = "daily_audit_digest"
    TRADE_CLOSED_REVIEW = "trade_closed_review"
    MARKET_CONTEXT = "market_context"
    GENERIC_ADVISORY = "generic_advisory"


class LlmAdvisoryRecommendationType(str, Enum):
    STRATEGY_FAMILY_CANDIDATE = "strategy_family_candidate"
    AUDIT_DIGEST = "audit_digest"
    BLOCKER_EXPLANATION = "blocker_explanation"
    TRADE_REVIEW = "trade_review"
    MARKET_CONTEXT = "market_context"
    UNKNOWN = "unknown"


class LlmAdvisoryStatus(str, Enum):
    GENERATED = "generated"
    BLOCKED = "blocked"
    PUSHED = "pushed"
    PUSH_FAILED = "push_failed"


class LlmContextPacket(LlmAdvisoryModel):
    packet_id: str = Field(min_length=1, max_length=128)
    packet_type: str = Field(default="llm_advisory_context", max_length=64)
    produced_at_ms: int = Field(ge=0)
    market: dict[str, Any] = Field(default_factory=dict)
    runtime: dict[str, Any] = Field(default_factory=dict)
    strategies: dict[str, Any] = Field(default_factory=dict)
    audit: dict[str, Any] = Field(default_factory=dict)
    external_facts: dict[str, Any] = Field(default_factory=dict)
    review: dict[str, Any] = Field(default_factory=dict)
    safety: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[str] = Field(default_factory=list)


class LlmConsumableEvent(LlmAdvisoryModel):
    event_id: str = Field(min_length=1, max_length=128)
    event_type: LlmConsumableEventType
    source_type: str = Field(min_length=1, max_length=64)
    source_id: str = Field(min_length=1, max_length=128)
    severity: str = Field(default="info", max_length=32)
    symbol: Optional[str] = Field(default=None, max_length=64)
    timeframe: Optional[str] = Field(default=None, max_length=32)
    strategy_family_ids: list[str] = Field(default_factory=list)
    dedupe_key: Optional[str] = Field(default=None, max_length=256)
    occurred_at_ms: int = Field(ge=0)
    context_packet: LlmContextPacket
    allowed_llm_actions: list[LlmAdvisoryAllowedAction] = Field(default_factory=list)
    delivery_policy: list[LlmAdvisoryDeliveryChannel] = Field(
        default_factory=lambda: [LlmAdvisoryDeliveryChannel.LEDGER_ONLY]
    )
    created_at_ms: int = Field(ge=0)
    not_execution_authority: bool = True
    owner_action_enabled: bool = False
    execution_intent_created: bool = False
    order_created: bool = False
    exchange_called: bool = False
    withdrawal_instruction_created: bool = False
    transfer_instruction_created: bool = False
    live_ready: bool = False

    @field_validator("strategy_family_ids")
    @classmethod
    def _unique_strategy_family_ids(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        unique: list[str] = []
        for item in value:
            if item in seen:
                continue
            seen.add(item)
            unique.append(item)
        return unique

    @model_validator(mode="after")
    def _validate_event_boundary(self) -> "LlmConsumableEvent":
        if not self.allowed_llm_actions:
            raise ValueError("LLM advisory event requires at least one allowed action")
        if not self.delivery_policy:
            raise ValueError("LLM advisory event requires a delivery policy")
        if not self.not_execution_authority:
            raise ValueError("LLM advisory event must be marked non-authoritative")
        if self.owner_action_enabled:
            raise ValueError("LLM advisory event cannot enable Owner action")
        if self.execution_intent_created or self.order_created or self.exchange_called:
            raise ValueError("LLM advisory event cannot create execution side effects")
        if self.withdrawal_instruction_created or self.transfer_instruction_created:
            raise ValueError("LLM advisory event cannot create fund movement instructions")
        if self.live_ready:
            raise ValueError("LLM advisory event is never live-ready")
        return self


_FORBIDDEN_LLM_AUTHORITY_KEYS = (
    "live_ready",
    "withdrawal_requested",
    "transfer_requested",
    "strategy_execution_requested",
    "autonomous_order_requested",
    "sizing_override_requested",
    "leverage_override_requested",
    "side_override_requested",
    "execution_intent_requested",
    "order_submit_requested",
)


class LlmAdvisoryRecommendation(LlmAdvisoryModel):
    recommendation_id: str = Field(min_length=1, max_length=128)
    event_id: str = Field(min_length=1, max_length=128)
    event_type: LlmConsumableEventType
    source_type: str = Field(min_length=1, max_length=64)
    source_id: str = Field(min_length=1, max_length=128)
    recommendation_type: LlmAdvisoryRecommendationType
    status: LlmAdvisoryStatus
    summary: str = Field(min_length=1, max_length=4096)
    confidence: Decimal = Field(default=Decimal("0"), ge=Decimal("0"), le=Decimal("1"))
    recommended_strategy_family_ids: list[str] = Field(default_factory=list)
    observe_only_strategy_family_ids: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)
    missing_facts: list[str] = Field(default_factory=list)
    research_idea_notes: list[str] = Field(default_factory=list)
    review_notes: list[str] = Field(default_factory=list)
    feishu_card_type: LlmFeishuCardType = LlmFeishuCardType.GENERIC_ADVISORY
    provider_name: str = Field(min_length=1, max_length=128)
    model_name: Optional[str] = Field(default=None, max_length=128)
    prompt_version: str = Field(default="llm_advisory_plane_v1", max_length=64)
    raw_response_summary: dict[str, Any] = Field(default_factory=dict)
    delivery_channels: list[LlmAdvisoryDeliveryChannel] = Field(default_factory=list)
    owner_action_route: str = Field(default="/console", max_length=256)
    owner_action_enabled: bool = False
    pushed_to_feishu_at_ms: Optional[int] = Field(default=None, ge=0)
    push_error: Optional[str] = Field(default=None, max_length=2048)
    created_at_ms: int = Field(ge=0)
    updated_at_ms: int = Field(ge=0)
    not_execution_authority: bool = True
    strategy_execution_authorized: bool = False
    execution_intent_created: bool = False
    order_created: bool = False
    exchange_called: bool = False
    withdrawal_instruction_created: bool = False
    transfer_instruction_created: bool = False
    live_ready: bool = False

    @field_validator("recommended_strategy_family_ids", "observe_only_strategy_family_ids")
    @classmethod
    def _unique_strategy_lists(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        unique: list[str] = []
        for item in value:
            if item in seen:
                continue
            seen.add(item)
            unique.append(item)
        return unique

    @model_validator(mode="after")
    def _validate_recommendation_boundary(self) -> "LlmAdvisoryRecommendation":
        if any(bool((self.raw_response_summary or {}).get(key)) for key in _FORBIDDEN_LLM_AUTHORITY_KEYS):
            raise ValueError("LLM advisory recommendation cannot carry trading authority")
        if not self.not_execution_authority:
            raise ValueError("LLM advisory recommendation must be non-authoritative")
        if self.owner_action_enabled:
            raise ValueError("LLM advisory recommendation is push-only and cannot enable Owner action")
        if self.strategy_execution_authorized:
            raise ValueError("LLM advisory recommendation cannot authorize strategy execution")
        if self.execution_intent_created or self.order_created or self.exchange_called:
            raise ValueError("LLM advisory recommendation cannot create execution side effects")
        if self.withdrawal_instruction_created or self.transfer_instruction_created:
            raise ValueError("LLM advisory recommendation cannot create fund movement instructions")
        if self.live_ready:
            raise ValueError("LLM advisory recommendation is never live-ready")
        return self


class LlmAdvisoryResult(LlmAdvisoryModel):
    event: LlmConsumableEvent
    recommendation: LlmAdvisoryRecommendation
    live_ready: bool = False


class LlmAdvisoryInboxItem(LlmAdvisoryModel):
    recommendation_id: str
    event_id: str
    event_type: LlmConsumableEventType
    source_type: str
    source_id: str
    status: LlmAdvisoryStatus
    recommendation_type: LlmAdvisoryRecommendationType
    feishu_card_type: LlmFeishuCardType
    summary: str
    recommended_strategy_family_ids: list[str] = Field(default_factory=list)
    missing_facts: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)
    pushed_to_feishu_at_ms: Optional[int] = None
    push_error: Optional[str] = None
    created_at_ms: int
    owner_action_enabled: Literal[False] = False
    live_ready: Literal[False] = False


class LlmAdvisoryInboxSummary(LlmAdvisoryModel):
    status_counts: dict[str, int] = Field(default_factory=dict)
    event_type_counts: dict[str, int] = Field(default_factory=dict)
    pending_push_failure_count: int = 0
    items: list[LlmAdvisoryInboxItem] = Field(default_factory=list)
    push_only: Literal[True] = True
    owner_action_enabled: Literal[False] = False
    live_ready: Literal[False] = False


class LlmFeishuAdvisoryCard(LlmAdvisoryModel):
    card_type: LlmFeishuCardType
    language: Literal["zh_cn", "en"] = "zh_cn"
    title: str = Field(min_length=1, max_length=160)
    subtitle: str = Field(default="", max_length=240)
    lines: list[str] = Field(default_factory=list)
    markdown: str = Field(min_length=1, max_length=4096)
    owner_action_text: str = "Open Console for canonical Owner action"
    push_only: Literal[True] = True
    owner_action_enabled: Literal[False] = False
    execution_intent_created: Literal[False] = False
    order_created: Literal[False] = False
    exchange_called: Literal[False] = False
    withdrawal_instruction_created: Literal[False] = False
    transfer_instruction_created: Literal[False] = False
    live_ready: Literal[False] = False


class LlmAdvisoryOutputSafetyReport(LlmAdvisoryModel):
    status: Literal["pass", "blocked"]
    blocked_keys: list[str] = Field(default_factory=list)
    blocked_reason_codes: list[str] = Field(default_factory=list)
    normalized_payload: dict[str, Any] = Field(default_factory=dict)
    owner_action_enabled: Literal[False] = False
    execution_intent_created: Literal[False] = False
    order_created: Literal[False] = False
    exchange_called: Literal[False] = False
    live_ready: Literal[False] = False


class LlmAdvisoryEvalCase(LlmAdvisoryModel):
    case_id: str = Field(min_length=1, max_length=128)
    event: LlmConsumableEvent
    provider_payload: dict[str, Any] = Field(default_factory=dict)
    expect_status: LlmAdvisoryStatus
    expect_push: bool = False
    expected_reason_codes: list[str] = Field(default_factory=list)


class LlmAdvisoryEvalResult(LlmAdvisoryModel):
    case_id: str
    passed: bool
    status: LlmAdvisoryStatus
    reason_codes: list[str] = Field(default_factory=list)
    pushed_to_feishu: bool = False
    failures: list[str] = Field(default_factory=list)
    live_ready: Literal[False] = False


class LlmAdvisoryEvalSummary(LlmAdvisoryModel):
    status: Literal["passed", "failed"]
    case_count: int = 0
    passed_count: int = 0
    failed_count: int = 0
    results: list[LlmAdvisoryEvalResult] = Field(default_factory=list)
    live_ready: Literal[False] = False
