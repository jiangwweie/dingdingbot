"""Immutable typed contracts shared by Owner Console read-only surfaces."""

from __future__ import annotations

import base64
import binascii
import json
from decimal import Decimal
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
    decision_status: Literal["admitted", "rejected"] | None = None
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
    review_status: Literal[
        "in_progress",
        "waiting_for_settlement",
        "waiting_for_review",
        "complete",
        "incomplete_evidence",
    ] | None = None
    strategy_group_id: str | None = None


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
    status: Literal["pending", "claimed", "completed", "unavailable"]
    mfe_r: Decimal | None
    mae_r: Decimal | None
    completion_reason: str | None
    observed_through_ms: int | None
    completed_at_ms: int | None
    interpretation: Literal[
        "Observation only; this Shadow Outcome is not execution."
    ] = "Observation only; this Shadow Outcome is not execution."
    evidence: tuple[EvidenceRef, ...]

    @field_validator("mfe_r", "mae_r", mode="before")
    @classmethod
    def _reject_float_decimal(cls, value: object) -> object:
        if isinstance(value, float):
            raise TypeError("shadow decimal values must not be floats")
        return value

    @field_serializer("mfe_r", "mae_r")
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
    admission_decision_id: str
    decision_status: Literal["admitted", "rejected"]
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
    economics_completeness: Literal[
        "complete",
        "funding_unavailable",
        "external_exit_unavailable",
    ] | None
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


class ProgrammaticTradeReview(FrozenModel):
    ticket_id: str
    review_status: Literal[
        "in_progress",
        "waiting_for_settlement",
        "waiting_for_review",
        "complete",
        "incomplete_evidence",
    ]
    execution_chain_classification: Literal[
        "complete",
        "recovered_incident",
        "incomplete_evidence",
        "in_progress",
    ]
    execution_chain_conclusion: str
    economic_conclusion: str | None
    exit_reason: str | None
    exit_conclusion: str | None
    gross_pnl: MoneyMetric
    fees: MoneyMetric
    funding: MoneyMetric
    net_pnl: MoneyMetric
    net_r: MoneyMetric
    attention_items: tuple[str, ...]
    evidence: tuple[EvidenceRef, ...]


class ReviewBreakdownItem(FrozenModel):
    label: str
    ticket_count: int
    evidence: tuple[EvidenceRef, ...]


class StrategyGroupSampleState(FrozenModel):
    strategy_group_id: str
    completed_ticket_count: int
    evidence_state: Literal["observe_only", "no_evidence"]
    evidence: tuple[EvidenceRef, ...]


class ReviewCenterSummary(FrozenModel):
    from_ms: int
    to_ms: int
    completed_ticket_count: int
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
    admission_decision_id: str
    decision_status: Literal["admitted", "rejected"]
    first_blocker: str | None
    binding_constraint: str | None
    ticket_id: str | None
    decided_at_ms: int
    shadow_outcome_id: str | None
    shadow_status: Literal[
        "pending", "claimed", "completed", "unavailable"
    ] | None
    shadow_mfe_r: Decimal | None
    shadow_mae_r: Decimal | None
    shadow_completion_reason: str | None
    shadow_observed_through_ms: int | None
    shadow_completed_at_ms: int | None
    evidence: tuple[EvidenceRef, ...]

    @field_validator("shadow_mfe_r", "shadow_mae_r", mode="before")
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
    evidence: tuple[EvidenceRef, ...]


class TradePageFacts(FrozenModel):
    items: tuple[TradeItemFacts, ...] = Field(max_length=101)
    requested_limit: int = Field(ge=1, le=100)


class TradeCausalityAggregateFacts(FrozenModel):
    ticket_id: str
    aggregate_status: str
    last_event_sequence: int = Field(gt=0)
    review_id: str | None
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
    evidence: tuple[EvidenceRef, ...]
