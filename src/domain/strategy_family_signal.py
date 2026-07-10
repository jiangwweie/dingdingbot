"""Strategy family signal contract domain models.

This module is a pure contract layer for live read-only strategy-family
observation. It does not authorize permission, size risk, create execution
intents, create orders, route orders, or call exchange/runtime services.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.comparative_strength import ComparativeStrengthSnapshot

from src.domain.execution_eligibility import RequiredExecutionMode, SignalGrade


CONTRACT_VERSION = "brc-strategy-family-signal-v1"

FORBIDDEN_EXECUTION_FIELDS = frozenset(
    {
        "amount",
        "cancel_instruction",
        "close_instruction",
        "client_order_id",
        "execution_instruction",
        "execution_intent",
        "execution_intent_id",
        "execution_venue",
        "flatten_instruction",
        "leverage",
        "notional",
        "order_id",
        "order_instruction",
        "order_request",
        "order_type",
        "quantity",
        "qty",
        "reduce-only",
        "reduce_only",
        "route",
        "router",
        "router_target",
        "size",
        "venue",
    }
)


class StrategyFamilySignalModel(BaseModel):
    """Base model for strategy-family signal value objects."""

    model_config = ConfigDict(extra="forbid")


class SignalType(str, Enum):
    NO_ACTION = "no_action"
    WOULD_ENTER = "would_enter"
    WOULD_EXIT = "would_exit"
    WOULD_REDUCE = "would_reduce"
    WOULD_CANCEL = "would_cancel"
    INVALID = "invalid"


class SignalSide(str, Enum):
    LONG = "long"
    SHORT = "short"
    NONE = "none"


class SignalDataQualityStatus(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    INVALID = "invalid"


class ExpectedRiskShape(str, Enum):
    TREND_FOLLOWING_WIDE_STOP = "trend_following_wide_stop"
    BREAKOUT_FALSE_BREAKOUT_PRONE = "breakout_false_breakout_prone"
    PULLBACK_CONTINUATION = "pullback_continuation"
    VOLATILITY_EXPANSION = "volatility_expansion"
    UNKNOWN = "unknown"


class SignalDataQuality(StrategyFamilySignalModel):
    status: SignalDataQualityStatus = SignalDataQualityStatus.OK
    missing_fields: list[str] = Field(default_factory=list)
    stale_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_latency_ms: Optional[int] = Field(default=None, ge=0)
    notes: list[str] = Field(default_factory=list)


class SignalInputRefs(StrategyFamilySignalModel):
    market_snapshot_ref: Optional[str] = Field(default=None, max_length=256)
    account_facts_snapshot_ref: Optional[str] = Field(default=None, max_length=256)
    permission_resolution_ref: Optional[str] = Field(default=None, max_length=256)
    trial_constraints_snapshot_ref: Optional[str] = Field(default=None, max_length=256)
    playbook_snapshot_ref: Optional[str] = Field(default=None, max_length=256)
    runtime_safety_snapshot_ref: Optional[str] = Field(default=None, max_length=256)
    evaluation_ref: Optional[str] = Field(default=None, max_length=256)


class SignalReviewPlan(StrategyFamilySignalModel):
    review_required: bool = True
    review_windows: list[str] = Field(default_factory=lambda: ["4h", "24h", "72h"])
    forward_outcome_metrics: list[str] = Field(
        default_factory=lambda: ["MFE", "MAE", "invalidation_hit", "follow_through"]
    )
    owner_review_status: str = Field(default="pending", max_length=64)


class StrategyFactObservation(StrategyFamilySignalModel):
    """One strategy fact actually observed by a versioned evaluator."""

    fact_key: str = Field(min_length=1, max_length=128)
    observed_value: bool | Decimal | int | str
    observed_at_ms: int = Field(ge=0)
    valid_until_ms: int = Field(gt=0)
    source_ref: str = Field(min_length=1, max_length=256)


class MarketSnapshot(StrategyFamilySignalModel):
    """Read-only market facts used for signal evaluation and later review."""

    symbol: str = Field(min_length=1, max_length=128)
    timestamp_ms: int = Field(ge=0)
    source: str = Field(min_length=1, max_length=128)
    freshness: str = Field(min_length=1, max_length=64)
    last_price: Optional[Decimal] = None
    mark_price: Optional[Decimal] = None
    index_price: Optional[Decimal] = None
    bid: Optional[Decimal] = None
    ask: Optional[Decimal] = None
    bid_ask_spread: Optional[Decimal] = None
    volume: Optional[Decimal] = None
    quote_volume: Optional[Decimal] = None
    funding_rate: Optional[Decimal] = None
    next_funding_time_ms: Optional[int] = Field(default=None, ge=0)
    volatility: Optional[Decimal] = None
    atr: Optional[Decimal] = None
    timeframe: Optional[str] = Field(default=None, max_length=32)
    candle_context: dict[str, Any] = Field(default_factory=dict)
    source_latency_ms: Optional[int] = Field(default=None, ge=0)
    missing_fields: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "MarketSnapshot":
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root="market_snapshot")
        return self


class AccountFactsSnapshot(StrategyFamilySignalModel):
    """Read-only account evidence used for observation context only."""

    source: str = Field(min_length=1, max_length=128)
    truth_level: str = Field(min_length=1, max_length=128)
    timestamp_ms: int = Field(ge=0)
    freshness: str = Field(min_length=1, max_length=64)
    account_status: str = Field(default="unknown", max_length=128)
    available_balance: Optional[Decimal] = None
    positions: list[dict[str, Any]] = Field(default_factory=list)
    open_orders: list[dict[str, Any]] = Field(default_factory=list)
    position_count: int = Field(default=0, ge=0)
    open_order_count: int = Field(default=0, ge=0)
    unknown_unmanaged_counts: dict[str, int] = Field(default_factory=dict)
    reconciliation_status: dict[str, Any] = Field(default_factory=dict)
    read_only_provider: Optional[str] = Field(default=None, max_length=128)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "AccountFactsSnapshot":
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root="account_facts_snapshot")
        return self


class StrategyFamilySignalInput(StrategyFamilySignalModel):
    """Pure input context for a strategy-family signal evaluation."""

    contract_version: str = Field(default=CONTRACT_VERSION, min_length=1, max_length=128)
    evaluation_id: str = Field(min_length=1, max_length=128)
    strategy_family_id: str = Field(min_length=1, max_length=128)
    strategy_family_version_id: str = Field(min_length=1, max_length=128)
    playbook_id: Optional[str] = Field(default=None, max_length=128)
    campaign_id: Optional[str] = Field(default=None, max_length=128)
    binding_id: Optional[str] = Field(default=None, max_length=128)
    symbol: str = Field(min_length=1, max_length=128)
    timestamp_ms: int = Field(ge=0)
    time_authority: Literal["trigger_candle_close_time_ms"] = "trigger_candle_close_time_ms"
    trigger_candle_close_time_ms: Optional[int] = Field(default=None, ge=0)
    primary_timeframe: str = Field(min_length=1, max_length=32)
    context_timeframes: list[str] = Field(default_factory=list)
    market_snapshot: MarketSnapshot
    comparative_strength_snapshot: Optional[ComparativeStrengthSnapshot] = None
    account_facts_snapshot: AccountFactsSnapshot
    position_open_order_summary: dict[str, Any] = Field(default_factory=dict)
    reconciliation_status: dict[str, Any] = Field(default_factory=dict)
    runtime_safety_snapshot: dict[str, Any] = Field(default_factory=dict)
    execution_permission_resolution: dict[str, Any] = Field(default_factory=dict)
    trial_constraints_snapshot: dict[str, Any] = Field(default_factory=dict)
    playbook_snapshot: dict[str, Any] = Field(default_factory=dict)
    strategy_family_metadata: dict[str, Any] = Field(default_factory=dict)
    source: str = Field(min_length=1, max_length=128)
    freshness: str = Field(min_length=1, max_length=64)
    input_quality: SignalDataQuality = Field(default_factory=SignalDataQuality)

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "StrategyFamilySignalInput":
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root="signal_input")
        return self


class StrategyFamilySignalOutput(StrategyFamilySignalModel):
    """Pure strategy-family signal output.

    The output is review evidence only. It is not an order, execution intent,
    sizing instruction, venue decision, cancel instruction, close instruction,
    flatten instruction, or permission grant.
    """

    contract_version: str = Field(default=CONTRACT_VERSION, min_length=1, max_length=128)
    signal_id: str = Field(min_length=1, max_length=128)
    evaluation_id: str = Field(min_length=1, max_length=128)
    strategy_family_id: str = Field(min_length=1, max_length=128)
    strategy_family_version_id: str = Field(min_length=1, max_length=128)
    playbook_id: Optional[str] = Field(default=None, max_length=128)
    symbol: str = Field(min_length=1, max_length=128)
    timestamp_ms: int = Field(ge=0)
    time_authority: Literal["trigger_candle_close_time_ms"] = "trigger_candle_close_time_ms"
    trigger_candle_close_time_ms: Optional[int] = Field(default=None, ge=0)
    timeframe: str = Field(min_length=1, max_length=32)
    signal_type: SignalType
    side: SignalSide = SignalSide.NONE
    confidence: Decimal = Field(default=Decimal("0"), ge=Decimal("0"), le=Decimal("1"))
    confidence_semantics: str = Field(
        default="review_sorting_and_explanation_only_not_win_probability_or_execution_authorization",
        max_length=512,
    )
    reason_codes: list[str] = Field(default_factory=list)
    human_summary: str = Field(default="", max_length=4096)
    signal_grade: SignalGrade = SignalGrade.OBSERVE_ONLY_SIGNAL
    required_execution_mode: RequiredExecutionMode = RequiredExecutionMode.OBSERVE_ONLY
    expected_risk_shape: ExpectedRiskShape | str = ExpectedRiskShape.UNKNOWN
    invalidation_conditions: list[dict[str, Any]] = Field(default_factory=list)
    signal_snapshot: dict[str, Any] = Field(default_factory=dict)
    evidence_payload: dict[str, Any] = Field(default_factory=dict)
    fact_observations: list[StrategyFactObservation] = Field(default_factory=list)
    input_refs: SignalInputRefs = Field(default_factory=SignalInputRefs)
    data_quality: SignalDataQuality = Field(default_factory=SignalDataQuality)
    review_plan: SignalReviewPlan = Field(default_factory=SignalReviewPlan)
    not_order: Literal[True] = True
    not_execution_intent: Literal[True] = True

    @model_validator(mode="after")
    def _enforce_signal_invariants(self) -> "StrategyFamilySignalOutput":
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root="signal_output")
        if (
            self.signal_type == SignalType.WOULD_ENTER
            and self.trigger_candle_close_time_ms is None
        ):
            raise ValueError("would_enter signal requires trigger_candle_close_time_ms")
        if self.signal_type == SignalType.NO_ACTION and self.side != SignalSide.NONE:
            raise ValueError("no_action signal must use side=none")
        return self


def reject_forbidden_execution_fields(value: Any, *, root: str) -> None:
    """Reject execution/order instruction keys anywhere inside serializable data."""

    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).strip().lower()
            if normalized in FORBIDDEN_EXECUTION_FIELDS:
                raise ValueError(f"{root} contains forbidden execution/order field: {key}")
            reject_forbidden_execution_fields(nested, root=f"{root}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            reject_forbidden_execution_fields(item, root=f"{root}[{index}]")
