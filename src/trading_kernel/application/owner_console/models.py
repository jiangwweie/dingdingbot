"""Immutable typed contracts shared by Owner Console read-only surfaces."""

from __future__ import annotations

import base64
import binascii
import json
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Generic, Literal, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    ValidationError,
    field_serializer,
    field_validator,
    model_validator,
)

from src.trading_kernel.domain.ticket import TradeTicket


class FrozenModel(BaseModel):
    """Base contract for immutable read models and their input facts."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Freshness(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    UNAVAILABLE = "unavailable"
    CONTRADICTORY = "contradictory"


class MoneyMetric(FrozenModel):
    value: Decimal | None
    unit: Literal["USDT", "R", "count", "fraction"]
    unavailable_reason: str | None = None

    @field_serializer("value")
    def _serialize_decimal(self, value: Decimal | None) -> str | None:
        return None if value is None else str(value)


class EvidenceRef(FrozenModel):
    kind: Literal[
        "signal",
        "admission",
        "ticket",
        "aggregate",
        "event",
        "command",
        "incident",
        "settlement",
        "review",
        "shadow",
        "fact",
    ]
    identity: str
    occurred_at_ms: int


class OverviewEvidenceGap(FrozenModel):
    reason: str
    evidence: EvidenceRef


LifecycleStageKey = Literal[
    "signal",
    "admission",
    "entry",
    "protection",
    "tp_runner",
    "exit",
    "reconciliation",
    "review",
]


class PageCursor(FrozenModel):
    sort_ms: int = Field(ge=0, le=9_223_372_036_854_775_807)
    identity: str = Field(min_length=1, max_length=160)


DataT = TypeVar("DataT")


class ApiEnvelope(FrozenModel, Generic[DataT]):
    snapshot_id: str
    generated_at: str
    source_watermark: str | None
    freshness: Freshness
    data: DataT


class PageFacts(FrozenModel, Generic[DataT]):
    items: tuple[DataT, ...] = Field(max_length=100)
    next_cursor: str | None


def encode_cursor(cursor: PageCursor) -> str:
    """Encode an exact stable keyset cursor without Base64 padding."""

    payload = json.dumps(
        cursor.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def decode_cursor(encoded: str) -> PageCursor:
    """Decode and validate a keyset cursor through its frozen model."""

    try:
        if len(encoded) > 2048:
            raise ValueError("encoded page cursor exceeds 2048 characters")
        raw = encoded.encode("ascii")
        padding = b"=" * (-len(raw) % 4)
        payload = base64.b64decode(raw + padding, altchars=b"-_", validate=True)
        document = json.loads(payload.decode("utf-8"))
        return PageCursor.model_validate(document)
    except (
        binascii.Error,
        UnicodeDecodeError,
        json.JSONDecodeError,
        TypeError,
        ValidationError,
        ValueError,
    ) as exc:
        raise ValueError("invalid page cursor") from exc


class BoundedWindowQuery(FrozenModel):
    from_ms: int
    to_ms: int
    limit: int = Field(default=50, ge=1, le=100)
    cursor: str | None = None

    @model_validator(mode="after")
    def _validate_window(self) -> BoundedWindowQuery:
        if self.to_ms <= self.from_ms:
            raise ValueError("time window must be increasing")
        if self.to_ms - self.from_ms > 90 * 86_400_000:
            raise ValueError("time window exceeds 90 days")
        return self


class SignalListQuery(BoundedWindowQuery):
    decision_status: Literal["admitted", "rejected", "not_evaluated"] | None = None
    strategy_group_id: str | None = None
    exchange_instrument_id: str | None = None
    position_side: Literal["long", "short"] | None = None


class TradeListQuery(BoundedWindowQuery):
    aggregate_status: str | None = None
    strategy_group_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=160,
    )
    exchange_instrument_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=160,
    )
    position_side: Literal["long", "short"] | None = None


class ReviewListQuery(BoundedWindowQuery):
    review_status: (
        Literal[
            "in_progress",
            "waiting_for_settlement",
            "waiting_for_review",
            "complete",
            "incomplete_evidence",
        ]
        | None
    ) = None
    strategy_group_id: str | None = None


class StrategySummaryQuery(BoundedWindowQuery):
    """Bounded version-isolated strategy evaluation query."""

    view: Literal["current", "all"] = "current"


class StrategyTicketQuery(BoundedWindowQuery):
    """Bounded Ticket query opened from one StrategyVersion evidence path."""

    strategy_version_id: str = Field(min_length=1, max_length=160)
    scope: Literal["natural", "all"] = "natural"
    exit_path: (
        Literal[
            "tp1_reached",
            "tp1_not_reached",
            "controlled_exit",
        ]
        | None
    ) = None

    @model_validator(mode="after")
    def _validate_scope_and_path(self) -> StrategyTicketQuery:
        if self.scope == "natural" and self.exit_path == "controlled_exit":
            raise ValueError("controlled exit path requires all scope")
        return self


class StrategyObservationQuery(BoundedWindowQuery):
    """Bounded Signal-owned Observation query for one StrategyVersion."""

    strategy_version_id: str = Field(min_length=1, max_length=160)
    first_path: (
        Literal[
            "tp1_first",
            "initial_stop_first",
            "ambiguous_same_bar",
            "opening_range_failure",
            "time_stop",
            "session_exit",
            "horizon_complete",
        ]
        | None
    ) = None


class CandleQuery(FrozenModel):
    exchange_instrument_id: str
    timeframe: Literal["15m", "1h"]
    limit: int = Field(default=300, ge=1, le=500)
    closed_at_ms: int = Field(gt=0)

    @field_validator("exchange_instrument_id", mode="before")
    @classmethod
    def _require_instrument_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("candle query instrument must be non-blank")
        return normalized


class CandleView(FrozenModel):
    open_time_ms: int = Field(gt=0)
    close_time_ms: int = Field(gt=0)
    open: str
    high: str
    low: str
    close: str
    volume: str

    @field_validator("open", "high", "low", "close", "volume", mode="before")
    @classmethod
    def _require_exact_decimal_text(cls, value: object) -> str:
        if not isinstance(value, str):
            raise TypeError("candle values must be exact strings")
        try:
            decimal_value = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("candle values must be valid decimals") from exc
        if not decimal_value.is_finite():
            raise ValueError("candle values must be finite")
        return value

    @model_validator(mode="after")
    def _validate_candle(self) -> CandleView:
        if self.close_time_ms <= self.open_time_ms:
            raise ValueError("candle requires an increasing time window")
        open_value = Decimal(self.open)
        high_value = Decimal(self.high)
        low_value = Decimal(self.low)
        close_value = Decimal(self.close)
        volume_value = Decimal(self.volume)
        if min(open_value, high_value, low_value, close_value) <= 0:
            raise ValueError("candle OHLC values must be positive")
        if volume_value < 0:
            raise ValueError("candle volume must be nonnegative")
        if high_value < max(open_value, close_value) or low_value > min(
            open_value,
            close_value,
        ):
            raise ValueError("candle high/low does not contain open and close")
        return self


class CandleSeries(FrozenModel):
    candles: tuple[CandleView, ...] = Field(max_length=500)

    @model_validator(mode="after")
    def _validate_chronological_candles(self) -> CandleSeries:
        open_times = [candle.open_time_ms for candle in self.candles]
        if open_times != sorted(open_times) or len(open_times) != len(set(open_times)):
            raise ValueError("candle series must be ordered and unique")
        return self


class InstrumentCenterQuery(FrozenModel):
    product_family: Literal[
        "crypto_perpetual",
        "tradfi_equity_perpetual",
    ] | None = None
    session_state: Literal[
        "pre_market",
        "regular",
        "after_market",
        "overnight",
        "no_trading",
        "unavailable",
    ] | None = None
    limit: int = Field(default=50, ge=1, le=100)


class InstrumentUniverseMembership(FrozenModel):
    strategy_group_id: str
    strategy_group_display_name: str
    strategy_version_id: str
    event_spec_id: str
    event_id: str
    position_side: Literal["long", "short"]
    runtime_profile_id: str
    owner_policy_id: str
    universe_version_id: str
    lifecycle_state: Literal["warming", "active"]


class InstrumentCenterItem(FrozenModel):
    exchange_instrument_id: str
    venue_symbol: str
    product_family: Literal[
        "crypto_perpetual",
        "tradfi_equity_perpetual",
    ]
    asset_class: Literal["crypto", "equity"]
    contract_type: Literal["PERPETUAL", "TRADIFI_PERPETUAL"]
    underlying_type: Literal["CRYPTO", "EQUITY"]
    margin_asset: Literal["USDT"]
    entry_session_policy: Literal[
        "continuous",
        "regular_only",
        "reference_only",
    ]
    profile_status: Literal["candidate", "reference", "active", "retired"]
    max_entry_spread_bps: str | None
    max_mark_index_deviation_bps: str | None
    product_status: Literal[
        "active",
        "inactive",
        "temporarily_unavailable",
    ] | None
    session_state: Literal[
        "pre_market",
        "regular",
        "after_market",
        "overnight",
        "no_trading",
        "unavailable",
    ] | None
    regular_session_open_ms: int | None
    regular_session_close_ms: int | None
    mark_price: str | None
    index_price: str | None
    funding_rate: str | None
    best_bid: str | None
    best_ask: str | None
    corporate_event_status: Literal["clear", "blocked", "unavailable"] | None
    observed_at_ms: int | None
    valid_until_ms: int | None
    source_ref: str | None
    memberships: tuple[InstrumentUniverseMembership, ...]


class InstrumentUniverseView(FrozenModel):
    strategy_group_id: str
    strategy_group_display_name: str
    strategy_version_id: str
    event_spec_id: str
    event_id: str
    position_side: Literal["long", "short"]
    product_family: Literal[
        "crypto_perpetual",
        "tradfi_equity_perpetual",
    ]
    runtime_profile_id: str
    owner_policy_id: str
    universe_version_id: str | None
    lifecycle_state: Literal["warming", "active"] | None
    exchange_instrument_ids: tuple[str, ...]


class InstrumentCenterPage(FrozenModel):
    items: tuple[InstrumentCenterItem, ...] = Field(max_length=100)
    universes: tuple[InstrumentUniverseView, ...] = Field(max_length=100)
    candidate_count: int = Field(ge=0)
    reference_count: int = Field(ge=0)
    unavailable_count: int = Field(ge=0)
    regular_session_count: int = Field(ge=0)
    source_watermark_ms: int | None


class EntryScopeFacts(FrozenModel):
    """One bounded current scope before effective Entry gates are evaluated."""

    runtime_scope_id: str
    strategy_group_id: str
    strategy_version_id: str
    event_spec_id: str
    timeframe: str
    exchange_instrument_id: str
    position_side: Literal["long", "short"]
    lifecycle_state: str
    entry_enabled: bool
    strategy_entry_state: str | None
    runtime_profile_status: str
    readiness_state: str | None
    readiness_first_blocker: str | None
    product_profile_status: str | None
    entry_session_policy: str | None
    product_status: str | None
    session_state: str | None
    product_valid_until_ms: int | None
    scope_updated_at_ms: int
    readiness_updated_at_ms: int | None
    product_observed_at_ms: int | None


class EffectiveEntryScopeItem(FrozenModel):
    runtime_scope_id: str
    strategy_group_id: str
    strategy_version_id: str
    event_spec_id: str
    timeframe: str
    exchange_instrument_id: str
    position_side: Literal["long", "short"]
    readiness_state: str | None
    can_issue_ticket_now: bool
    first_blocker: str | None
    evidence: tuple[EvidenceRef, ...]


class EffectiveEntryScopeFacts(FrozenModel):
    owner_policy_id: str
    policy_version: int
    policy_enabled: bool
    new_entry_submit_enabled: bool
    runtime_capability_enabled: bool
    max_concurrent_tickets: int
    active_ticket_count: int
    scopes: tuple[EntryScopeFacts, ...] = Field(max_length=100)


class EffectiveEntryScope(FrozenModel):
    owner_policy_id: str
    policy_version: int
    can_issue_ticket_now: bool
    first_blocker: str | None
    remaining_ticket_slots: int = Field(ge=0)
    eligible_scope_count: int = Field(ge=0)
    scopes: tuple[EffectiveEntryScopeItem, ...] = Field(max_length=100)
    evidence: tuple[EvidenceRef, ...]


class AdmissionAccountSnapshot(FrozenModel):
    label: Literal["Latest Admission Snapshot"]
    is_realtime: Literal[False] = False
    captured_at_ms: int | None
    wallet_balance: MoneyMetric
    available_margin: MoneyMetric


class OwnerConclusion(FrozenModel):
    level: Literal["intervention", "attention", "no_action"]
    summary: str
    owner_action: str | None
    evidence: tuple[EvidenceRef, ...]


class OwnerOverview(FrozenModel):
    observed_at_ms: int
    conclusion: OwnerConclusion
    account_snapshot: AdmissionAccountSnapshot
    ticket_capacity: int | None
    active_ticket_count: int | None
    active_ticket_ids: tuple[str, ...]
    today_net_pnl: MoneyMetric
    today_net_r: MoneyMetric
    today_signal_count: int
    admitted_signal_count: int
    rejected_signal_count: int
    execution_incident_count: int | None
    attention_summary: tuple[str, ...]
    evidence: tuple[EvidenceRef, ...]


class ShadowOutcomeSummary(FrozenModel):
    shadow_outcome_id: str
    source_kind: Literal["portfolio_rejection", "strategy_observation"]
    evaluation_kind: Literal[
        "fixed_horizon_excursion_v1",
        "sor_path_observation_v1",
    ]
    status: Literal["pending", "claimed", "completed", "unavailable"]
    mfe_r: Decimal | None
    mae_r: Decimal | None
    first_path: (
        Literal[
            "tp1_first",
            "initial_stop_first",
            "ambiguous_same_bar",
            "opening_range_failure",
            "time_stop",
            "session_exit",
            "horizon_complete",
        ]
        | None
    ) = None
    first_path_at_ms: int | None = None
    observed_bar_count: int | None = None
    spread_bps: Decimal | None = None
    mark_index_deviation_bps: Decimal | None = None
    completion_reason: str | None
    observed_through_ms: int | None
    completed_at_ms: int | None
    interpretation: Literal[
        "Observation only; this Shadow Outcome is not execution."
    ] = "Observation only; this Shadow Outcome is not execution."
    evidence: tuple[EvidenceRef, ...]

    @field_validator(
        "mfe_r",
        "mae_r",
        "spread_bps",
        "mark_index_deviation_bps",
        mode="before",
    )
    @classmethod
    def _reject_float_decimal(cls, value: object) -> object:
        if isinstance(value, float):
            raise TypeError("shadow decimal values must not be floats")
        return value

    @field_serializer(
        "mfe_r",
        "mae_r",
        "spread_bps",
        "mark_index_deviation_bps",
    )
    def _serialize_decimal(self, value: Decimal | None) -> str | None:
        return None if value is None else str(value)


class SignalListItem(FrozenModel):
    signal_event_id: str
    exposure_episode_id: str
    strategy_group_id: str
    strategy_version_id: str
    event_spec_id: str
    exchange_instrument_id: str
    position_side: Literal["long", "short"]
    occurred_at_ms: int
    expires_at_ms: int
    admission_decision_id: str | None
    decision_status: Literal["admitted", "rejected", "not_evaluated"]
    first_blocker: str | None
    binding_constraint: str | None
    ticket_id: str | None
    shadow_summary: ShadowOutcomeSummary | None
    evidence: tuple[EvidenceRef, ...]


class SignalListPage(FrozenModel):
    items: tuple[SignalListItem, ...] = Field(max_length=100)
    next_cursor: str | None


class SignalAdmissionDetail(FrozenModel):
    signal: SignalListItem
    what_happened: str
    why_no_ticket: str | None
    fact_snapshots: tuple[SignalFactSnapshotFacts, ...] = Field(max_length=256)
    shadow_summary: ShadowOutcomeSummary | None
    evidence: tuple[EvidenceRef, ...]


class TradeListItem(FrozenModel):
    ticket_id: str
    strategy_group_id: str
    event_spec_id: str
    exchange_instrument_id: str
    position_side: Literal["long", "short"]
    ticket_status: str
    aggregate_status: str
    lifecycle_stage: LifecycleStageKey
    issued_at_ms: int
    terminal_at_ms: int | None
    review_id: str | None
    review_revision: int | None
    economics_completeness: (
        Literal[
            "complete",
            "funding_unavailable",
            "external_exit_unavailable",
        ]
        | None
    )
    completed_stage_count: int
    total_stage_count: Literal[8]
    exit_reason: str | None
    exit_reason_unavailable_reason: str | None
    gross_pnl: MoneyMetric
    fees: MoneyMetric
    funding: MoneyMetric
    net_pnl: MoneyMetric
    net_r: MoneyMetric
    attention_items: tuple[str, ...]
    evidence: tuple[EvidenceRef, ...]


class TradeListPage(FrozenModel):
    items: tuple[TradeListItem, ...] = Field(max_length=100)
    next_cursor: str | None


class LifecycleStageView(FrozenModel):
    key: LifecycleStageKey
    label: str
    status: Literal[
        "pending",
        "current",
        "complete",
        "unavailable",
        "skipped",
    ]
    started_at_ms: int | None
    completed_at_ms: int | None
    duration_ms: int | None
    summary: str
    evidence: tuple[EvidenceRef, ...]


class ChartAnnotation(FrozenModel):
    kind: Literal["signal", "entry", "stop", "take_profit", "exit"]
    occurred_at_ms: int
    price: Decimal
    label: str
    evidence: tuple[EvidenceRef, ...]

    @field_validator("price", mode="before")
    @classmethod
    def _reject_float_price(cls, value: object) -> object:
        if isinstance(value, float):
            raise TypeError("chart annotation price must not be a float")
        return value

    @field_validator("price")
    @classmethod
    def _require_finite_price(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("chart annotation price must be finite")
        return value

    @field_serializer("price")
    def _serialize_price(self, value: Decimal) -> str:
        return str(value)


class TradePricePlanView(FrozenModel):
    """Frozen Ticket price plan and observed execution for one causality view."""

    strategy_timeframe: Literal["15m", "1h"] | None
    entry_reference_price: Decimal
    entry_limit_price: Decimal | None
    actual_entry_price: Decimal | None
    initial_stop_price: Decimal
    active_stop_price: Decimal | None
    tp1_price: Decimal | None
    ticket_quantity: Decimal
    tp1_target_quantity: Decimal | None
    tp1_filled_quantity: Decimal
    initial_stop_distance_percent: Decimal | None
    tp1_distance_percent: Decimal | None
    tp1_reward_r: Decimal | None


class CausalityExitReason(FrozenModel):
    code: str
    label: str
    evidence: tuple[EvidenceRef, ...]


class RawTradeEventView(FrozenModel):
    event_id: str
    ticket_id: str
    sequence: int
    event_type: str
    payload: dict[str, JsonValue]
    occurred_at_ms: int
    stage: LifecycleStageKey
    classification: Literal["mapped", "unmapped"]
    evidence: tuple[EvidenceRef, ...]


class RawExchangeCommandView(FrozenModel):
    command_id: str
    ticket_id: str
    command_kind: str
    generation: int
    status: str
    request_payload: dict[str, JsonValue]
    result_payload: dict[str, JsonValue] | None
    created_at_ms: int
    completed_at_ms: int | None
    evidence: tuple[EvidenceRef, ...]


class RawIncidentView(FrozenModel):
    incident_id: str
    ticket_id: str
    incident_kind: str
    status: str
    first_blocker: str
    details: dict[str, JsonValue]
    opened_at_ms: int
    resolved_at_ms: int | None
    evidence: tuple[EvidenceRef, ...]


class TradeCausalityDetail(FrozenModel):
    trade: TradeListItem
    price_plan: TradePricePlanView
    current_stage: LifecycleStageKey
    current_stage_summary: str
    stages: tuple[LifecycleStageView, ...]
    annotations: tuple[ChartAnnotation, ...]
    exit_reason: CausalityExitReason | None
    raw_events: tuple[RawTradeEventView, ...] = Field(max_length=512)
    raw_commands: tuple[RawExchangeCommandView, ...] = Field(max_length=128)
    raw_incidents: tuple[RawIncidentView, ...] = Field(max_length=64)
    signal_evidence: tuple[EvidenceRef, ...]
    order_evidence: tuple[EvidenceRef, ...]
    incident_evidence: tuple[EvidenceRef, ...]
    event_evidence: tuple[EvidenceRef, ...]
    settlement_evidence: tuple[EvidenceRef, ...]
    review_evidence: tuple[EvidenceRef, ...]
    evidence: tuple[EvidenceRef, ...]


ExecutionClassification = Literal[
    "complete",
    "recovered_incident",
    "evidence_incomplete",
    "in_progress",
    "waiting_review",
]


class ReviewSentence(FrozenModel):
    template_id: Literal[
        "execution_complete",
        "execution_recovered",
        "economics_complete",
        "economics_incomplete",
        "review_waiting",
        "ticket_in_progress",
    ]
    text: str
    evidence: tuple[EvidenceRef, ...] = Field(min_length=1)


class ReviewEconomicSummary(FrozenModel):
    gross_pnl: MoneyMetric
    fees: MoneyMetric
    funding: MoneyMetric
    net_pnl: MoneyMetric
    net_r: MoneyMetric


class ProgrammaticTradeReview(FrozenModel):
    ticket_id: str
    review_status: Literal[
        "in_progress",
        "waiting_review",
        "complete",
        "incomplete_evidence",
    ]
    execution_classification: ExecutionClassification
    economic_summary: ReviewEconomicSummary
    exit_reason: str | None
    attention_items: tuple[str, ...]
    sentences: tuple[ReviewSentence, ...] = Field(min_length=1)
    final_conclusion: str | None
    evidence: tuple[EvidenceRef, ...] = Field(min_length=1)


class ReviewBreakdownItem(FrozenModel):
    label: str
    ticket_count: int
    evidence: tuple[EvidenceRef, ...]


class StrategyGroupSampleState(FrozenModel):
    strategy_group_id: str
    sample_count: int
    evidence_state: Literal["observe_only", "no_evidence"]
    evidence: tuple[EvidenceRef, ...]


class ReviewCenterItem(FrozenModel):
    ticket_id: str
    strategy_group_id: str
    exchange_instrument_id: str
    position_side: Literal["long", "short"]
    terminal_at_ms: int
    review: ProgrammaticTradeReview


class ReviewCenterSummary(FrozenModel):
    from_ms: int
    to_ms: int
    sample_count: int
    next_cursor: str | None
    items: tuple[ReviewCenterItem, ...]
    net_pnl: MoneyMetric
    net_r: MoneyMetric
    fees: MoneyMetric
    funding: MoneyMetric
    exit_reason_breakdown: tuple[ReviewBreakdownItem, ...]
    execution_quality_breakdown: tuple[ReviewBreakdownItem, ...]
    complete_review_count: int
    incomplete_review_count: int
    strategy_group_samples: tuple[StrategyGroupSampleState, ...]
    evidence: tuple[EvidenceRef, ...]


class StrategyTicketFacts(FrozenModel):
    """One exact Ticket outcome used only for a StrategyVersion summary."""

    ticket_id: str
    issued_at_ms: int
    terminal_at_ms: int | None
    ticket_status: str
    aggregate_status: str
    review_id: str | None
    review_created_at_ms: int | None
    economics_completeness: (
        Literal[
            "complete",
            "funding_unavailable",
            "external_exit_unavailable",
            "incomplete_evidence",
        ]
        | None
    )
    net_pnl: MoneyMetric
    net_r: MoneyMetric
    exit_reason: str | None
    tp1_reached: bool
    evidence: tuple[EvidenceRef, ...]


class StrategyObservationFacts(FrozenModel):
    """One exact Signal-owned Observation used by summary and sample reads."""

    shadow_outcome_id: str
    signal_event_id: str
    ticket_id: str | None
    strategy_version_id: str
    exchange_instrument_id: str
    position_side: Literal["long", "short"]
    occurred_at_ms: int
    horizon_start_ms: int
    horizon_end_ms: int
    status: Literal["pending", "claimed", "completed", "unavailable"]
    entry_reference_price: Decimal | None
    initial_stop_price: Decimal | None
    take_profit_price: Decimal | None
    opening_range_boundary_price: Decimal | None
    session_exit_deadline_ms: int | None
    best_bid_price: Decimal | None
    best_ask_price: Decimal | None
    best_bid_quantity: Decimal | None
    best_ask_quantity: Decimal | None
    spread_bps: Decimal | None
    mark_index_deviation_bps: Decimal | None
    max_favorable_price: Decimal | None
    max_adverse_price: Decimal | None
    mfe_r: Decimal | None
    mae_r: Decimal | None
    completion_reason: str | None
    first_path: (
        Literal[
            "tp1_first",
            "initial_stop_first",
            "ambiguous_same_bar",
            "opening_range_failure",
            "time_stop",
            "session_exit",
            "horizon_complete",
        ]
        | None
    )
    first_path_at_ms: int | None
    observed_bar_count: int | None
    completed_at_ms: int | None
    evidence: tuple[EvidenceRef, ...]

    @field_validator(
        "entry_reference_price",
        "initial_stop_price",
        "take_profit_price",
        "opening_range_boundary_price",
        "best_bid_price",
        "best_ask_price",
        "best_bid_quantity",
        "best_ask_quantity",
        "spread_bps",
        "mark_index_deviation_bps",
        "max_favorable_price",
        "max_adverse_price",
        "mfe_r",
        "mae_r",
        mode="before",
    )
    @classmethod
    def _reject_float_observation_decimal(cls, value: object) -> object:
        if isinstance(value, float):
            raise TypeError("observation decimal values must not be floats")
        return value


class StrategyProductEventFacts(FrozenModel):
    """Compact Event-to-product and Universe authority for strategy display."""

    event_spec_id: str
    event_id: str
    position_side: Literal["long", "short"]
    timeframe: str
    venue_id: str | None
    product_family: Literal[
        "crypto_perpetual",
        "tradfi_equity_perpetual",
    ]
    runtime_profile_id: str | None
    owner_policy_id: str | None
    active_universe_version_id: str | None
    active_exchange_instrument_ids: tuple[str, ...]
    warming_universe_version_id: str | None
    warming_exchange_instrument_ids: tuple[str, ...]


class StrategyVersionFacts(FrozenModel):
    """Persisted strategy identity plus bounded Ticket facts for one version."""

    strategy_group_id: str
    strategy_group_display_name: str
    strategy_version_id: str
    version: int = Field(gt=0)
    strategy_version_status: str
    is_current: bool
    tickets: tuple[StrategyTicketFacts, ...] = Field(max_length=5_000)
    observations: tuple[StrategyObservationFacts, ...] = Field(
        default=(),
        max_length=5_000,
    )
    evidence: tuple[EvidenceRef, ...]
    product_events: tuple[StrategyProductEventFacts, ...] = Field(
        default=(),
        max_length=32,
    )


class StrategyPageFacts(FrozenModel):
    from_ms: int
    to_ms: int
    view: Literal["current", "all"]
    versions: tuple[StrategyVersionFacts, ...] = Field(max_length=100)


class StrategyVersionSummary(FrozenModel):
    strategy_group_id: str
    strategy_group_display_name: str
    strategy_version_id: str
    version: int = Field(gt=0)
    strategy_version_status: str
    is_current: bool
    ticket_count: int = Field(ge=0)
    natural_terminal_count: int = Field(ge=0)
    confirmed_natural_review_count: int = Field(ge=0)
    pending_natural_review_count: int = Field(ge=0)
    controlled_exit_count: int = Field(ge=0)
    tp1_reached_count: int = Field(ge=0)
    tp1_not_reached_count: int = Field(ge=0)
    win_count: int = Field(ge=0)
    loss_count: int = Field(ge=0)
    net_pnl: MoneyMetric
    net_r: MoneyMetric
    observation_count: int = Field(ge=0)
    completed_observation_count: int = Field(ge=0)
    unavailable_observation_count: int = Field(ge=0)
    tp1_first_count: int = Field(ge=0)
    initial_stop_first_count: int = Field(ge=0)
    opening_range_failure_count: int = Field(ge=0)
    ambiguous_observation_count: int = Field(ge=0)
    time_stop_count: int = Field(ge=0)
    session_exit_count: int = Field(ge=0)
    median_mfe_r: Decimal | None
    median_mae_r: Decimal | None
    median_spread_bps: Decimal | None
    evidence: tuple[EvidenceRef, ...]
    product_events: tuple[StrategyProductEventFacts, ...] = Field(
        default=(),
        max_length=32,
    )

    @field_serializer("median_mfe_r", "median_mae_r", "median_spread_bps")
    def _serialize_observation_decimal(self, value: Decimal | None) -> str | None:
        return None if value is None else str(value)


class StrategySummaryPage(FrozenModel):
    from_ms: int
    to_ms: int
    view: Literal["current", "all"]
    items: tuple[StrategyVersionSummary, ...] = Field(max_length=100)
    evidence: tuple[EvidenceRef, ...]


class StrategyTicketListItem(TradeListItem):
    evaluation_path: Literal[
        "tp1_reached",
        "tp1_not_reached",
        "controlled_exit",
        "not_terminal",
    ]


class StrategyTicketListPage(FrozenModel):
    items: tuple[StrategyTicketListItem, ...] = Field(max_length=100)
    next_cursor: str | None


class StrategyObservationListItem(StrategyObservationFacts):
    annotations: tuple[ChartAnnotation, ...]


class StrategyObservationPageFacts(FrozenModel):
    items: tuple[StrategyObservationFacts, ...] = Field(max_length=101)
    requested_limit: int = Field(ge=1, le=100)


class StrategyObservationListPage(FrozenModel):
    items: tuple[StrategyObservationListItem, ...] = Field(max_length=100)
    next_cursor: str | None


class OverviewFacts(FrozenModel):
    observed_at_ms: int
    runtime_freshness: Freshness
    freshness_evidence_identity: str
    freshness_evidence_at_ms: int
    max_concurrent_tickets: int | None
    active_ticket_count: int | None
    active_ticket_ids: tuple[str, ...]
    latest_capacity_claim_id: str | None
    latest_wallet_balance_at_claim: Decimal | None
    latest_available_margin_at_claim: Decimal | None
    latest_claim_created_at_ms: int | None
    open_owner_incident_id: str | None
    open_owner_incident_opened_at_ms: int | None
    attention_incident_ids: tuple[str, ...]
    attention_incident_opened_at_ms: tuple[int, ...]
    monitor_statuses: tuple[str, ...]
    monitor_keys: tuple[str, ...]
    monitor_updated_at_ms: tuple[int, ...]
    needs_intervention_monitor_key: str | None
    needs_intervention_monitor_updated_at_ms: int | None
    contradictory_fact_reasons: tuple[str, ...]
    contradictory_evidence_identity: str | None
    evidence_gaps: tuple[OverviewEvidenceGap, ...]
    today_net_pnl: MoneyMetric
    today_net_r: MoneyMetric
    today_signal_count: int
    admitted_signal_count: int
    rejected_signal_count: int
    execution_incident_count: int | None
    evidence: tuple[EvidenceRef, ...]


class SignalItemFacts(FrozenModel):
    signal_event_id: str
    exposure_episode_id: str
    strategy_group_id: str
    strategy_version_id: str
    event_spec_id: str
    exchange_instrument_id: str
    position_side: Literal["long", "short"]
    occurred_at_ms: int
    expires_at_ms: int
    admission_decision_id: str | None
    decision_status: Literal["admitted", "rejected", "not_evaluated"]
    first_blocker: str | None
    binding_constraint: str | None
    ticket_id: str | None
    decided_at_ms: int | None
    shadow_outcome_id: str | None
    shadow_source_kind: Literal[
        "portfolio_rejection",
        "strategy_observation",
    ] | None = None
    shadow_evaluation_kind: Literal[
        "fixed_horizon_excursion_v1",
        "sor_path_observation_v1",
    ] | None = None
    shadow_status: Literal["pending", "claimed", "completed", "unavailable"] | None
    shadow_mfe_r: Decimal | None
    shadow_mae_r: Decimal | None
    shadow_completion_reason: str | None
    shadow_observed_through_ms: int | None
    shadow_completed_at_ms: int | None
    shadow_first_path: (
        Literal[
            "tp1_first",
            "initial_stop_first",
            "ambiguous_same_bar",
            "opening_range_failure",
            "time_stop",
            "session_exit",
            "horizon_complete",
        ]
        | None
    ) = None
    shadow_first_path_at_ms: int | None = None
    shadow_observed_bar_count: int | None = None
    shadow_spread_bps: Decimal | None = None
    shadow_mark_index_deviation_bps: Decimal | None = None
    evidence: tuple[EvidenceRef, ...]

    @field_validator(
        "shadow_mfe_r",
        "shadow_mae_r",
        "shadow_spread_bps",
        "shadow_mark_index_deviation_bps",
        mode="before",
    )
    @classmethod
    def _reject_float_decimal(cls, value: object) -> object:
        if isinstance(value, float):
            raise TypeError("shadow decimal values must not be floats")
        return value


SignalFactRole = Literal[
    "condition",
    "protection_reference",
    "identity_reference",
    "lifecycle_reference",
    "disable",
]


class SignalFactSnapshotFacts(FrozenModel):
    signal_event_id: str
    fact_definition_id: str
    role: SignalFactRole
    value: JsonValue
    satisfied: bool
    observed_at_ms: int
    valid_until_ms: int
    projection_version: int


class SignalPageFacts(FrozenModel):
    items: tuple[SignalItemFacts, ...] = Field(max_length=101)
    requested_limit: int = Field(ge=1, le=100)


class SignalDetailFacts(FrozenModel):
    signal: SignalItemFacts
    fact_snapshots: tuple[SignalFactSnapshotFacts, ...] = Field(max_length=256)


class TradeItemFacts(FrozenModel):
    ticket_id: str
    strategy_group_id: str
    event_spec_id: str
    exchange_instrument_id: str
    position_side: Literal["long", "short"]
    ticket_status: str
    aggregate_status: str
    issued_at_ms: int
    terminal_at_ms: int | None
    aggregate_review_id: str | None
    review_id: str | None
    review_ticket_id: str | None
    review_revision: int | None
    review_created_at_ms: int | None
    review_metrics: dict[str, JsonValue] | None
    exit_event_id: str | None
    exit_event_type: str | None
    exit_event_payload: dict[str, JsonValue] | None
    exit_event_occurred_at_ms: int | None
    open_incident_id: str | None
    open_incident_opened_at_ms: int | None
    latest_incident_id: str | None
    latest_incident_opened_at_ms: int | None
    tp1_reached: bool = False
    evidence: tuple[EvidenceRef, ...]


class TradePageFacts(FrozenModel):
    items: tuple[TradeItemFacts, ...] = Field(max_length=101)
    requested_limit: int = Field(ge=1, le=100)


class StrategyTicketPageFacts(FrozenModel):
    items: tuple[TradeItemFacts, ...] = Field(max_length=101)
    requested_limit: int = Field(ge=1, le=100)


class TradeCausalityAggregateFacts(FrozenModel):
    ticket_id: str
    aggregate_status: str
    last_event_sequence: int = Field(gt=0)
    review_id: str | None
    position_qty: Decimal
    average_fill_price: Decimal | None
    active_stop_price: Decimal | None
    tp1_target_qty: Decimal
    tp1_filled_qty: Decimal
    updated_at_ms: int


class TradeCausalitySignalFacts(FrozenModel):
    signal_event_id: str
    exposure_episode_id: str
    runtime_scope_id: str
    runtime_scope_version: int
    strategy_group_id: str
    strategy_version_id: str
    event_spec_id: str
    universe_version_id: str
    universe_semantic_digest: str
    exchange_instrument_id: str
    position_side: Literal["long", "short"]
    occurred_at_ms: int


class TradeCausalityAdmissionFacts(FrozenModel):
    admission_decision_id: str
    signal_event_id: str
    exposure_episode_id: str
    strategy_group_id: str
    strategy_version_id: str
    event_spec_id: str
    universe_version_id: str
    universe_semantic_digest: str
    runtime_profile_id: str
    runtime_scope_id: str
    runtime_scope_version: int
    owner_policy_id: str
    owner_policy_version: int
    venue_id: str
    account_id: str
    exchange_instrument_id: str
    position_side: Literal["long", "short"]
    decision_status: Literal["admitted", "rejected"]
    capacity_claim_id: str | None
    ticket_id: str | None
    decided_at_ms: int


class TradeCausalityEventFacts(FrozenModel):
    event_id: str
    ticket_id: str
    sequence: int = Field(gt=0)
    event_type: str
    payload: dict[str, JsonValue]
    occurred_at_ms: int


class TradeCausalityCommandFacts(FrozenModel):
    command_id: str
    ticket_id: str
    command_kind: str
    generation: int = Field(gt=0)
    status: str
    request_payload: dict[str, JsonValue]
    result_payload: dict[str, JsonValue] | None
    created_at_ms: int
    completed_at_ms: int | None


class TradeCausalityIncidentFacts(FrozenModel):
    incident_id: str
    ticket_id: str
    incident_kind: str
    status: str
    first_blocker: str
    details: dict[str, JsonValue]
    opened_at_ms: int
    resolved_at_ms: int | None


class TradeCausalityReviewFacts(FrozenModel):
    review_id: str
    ticket_id: str
    revision: int = Field(gt=0)
    metrics: dict[str, JsonValue]
    created_at_ms: int


class TradeCausalityFacts(FrozenModel):
    trade: TradeItemFacts
    ticket: TradeTicket
    aggregate: TradeCausalityAggregateFacts
    signal: TradeCausalitySignalFacts
    admission: TradeCausalityAdmissionFacts
    events: tuple[TradeCausalityEventFacts, ...] = Field(max_length=512)
    commands: tuple[TradeCausalityCommandFacts, ...] = Field(max_length=128)
    incidents: tuple[TradeCausalityIncidentFacts, ...] = Field(max_length=64)
    review: TradeCausalityReviewFacts | None


class ProgrammaticReviewFacts(FrozenModel):
    ticket_id: str
    ticket_status: str
    aggregate_status: str = "terminal"
    lifecycle_stage: LifecycleStageKey = "review"
    settlement_completed: bool
    current_review_id: str | None
    entry_complete: bool
    protection_complete: bool
    exit_complete: bool
    reconciliation_complete: bool
    review_complete: bool
    incident_ids: tuple[str, ...]
    recovered_incident_ids: tuple[str, ...]
    economics_completeness: Literal[
        "complete",
        "funding_unavailable",
        "external_exit_unavailable",
        "incomplete_evidence",
    ]
    gross_pnl: MoneyMetric
    fees: MoneyMetric
    funding: MoneyMetric
    net_pnl: MoneyMetric
    net_r: MoneyMetric
    frozen_initial_stop_risk: MoneyMetric
    actual_stop_risk: MoneyMetric
    exit_reason: str | None
    runner_net_contribution: MoneyMetric
    ticket_evidence: EvidenceRef | None = None
    aggregate_evidence: EvidenceRef | None = None
    entry_fill_evidence: EvidenceRef | None = None
    protection_confirmed_evidence: EvidenceRef | None = None
    exit_trigger_evidence: EvidenceRef | None = None
    flat_evidence: EvidenceRef | None = None
    reconciliation_matched_evidence: EvidenceRef | None = None
    settlement_evidence: EvidenceRef | None = None
    current_review_evidence: EvidenceRef | None = None
    incident_evidence: tuple[EvidenceRef, ...] = ()
    evidence: tuple[EvidenceRef, ...]


class ReviewCenterItemFacts(FrozenModel):
    strategy_group_id: str
    exchange_instrument_id: str
    position_side: Literal["long", "short"]
    terminal_at_ms: int
    review: ProgrammaticReviewFacts


class ReviewCenterFacts(FrozenModel):
    from_ms: int
    to_ms: int
    items: tuple[ReviewCenterItemFacts, ...] = Field(max_length=101)
    requested_limit: int = Field(ge=1, le=100)
    requested_strategy_group_id: str | None
