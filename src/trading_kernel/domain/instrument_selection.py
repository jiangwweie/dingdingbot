"""Pure SOR Dynamic Instrument Selection V0 identities and member decisions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from enum import StrEnum
from hashlib import sha256
from typing import Literal, TypedDict

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.domain.instrument_identity import (
    parse_binance_usdm_instrument_id,
)

INTERVAL_MS = 15 * 60 * 1000
HOUR_MS = 60 * 60 * 1000
DAY_MS = 24 * HOUR_MS
DECIMAL_PRECISION = 38
DECIMAL_ROUNDING = ROUND_HALF_EVEN
DECIMAL_CONTEXT = Context(prec=DECIMAL_PRECISION, rounding=DECIMAL_ROUNDING)
ACTIVITY_FLOOR_QUOTE_USDT = Decimal(20_000_000)

SOR_STRATEGY_GROUP_ID = "SOR-001"
SOR_STRATEGY_VERSION_ID = "sgv:SOR-001:v4"
SOR_LONG_EVENT_SPEC_ID = "event_spec:SOR-001:SOR-LONG:v4"
SOR_SHORT_EVENT_SPEC_ID = "event_spec:SOR-001:SOR-SHORT:v4"
SOR_EVENT_SPEC_IDS = (SOR_LONG_EVENT_SPEC_ID, SOR_SHORT_EVENT_SPEC_ID)

_FROZEN_CANDIDATE_SYMBOLS = (
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "ADAUSDT",
    "AVAXUSDT",
    "LINKUSDT",
    "LTCUSDT",
    "BCHUSDT",
    "DOTUSDT",
    "NEARUSDT",
    "ATOMUSDT",
    "FILUSDT",
    "ETCUSDT",
    "APTUSDT",
    "OPUSDT",
    "ARBUSDT",
    "INJUSDT",
    "SUIUSDT",
    "TRXUSDT",
    "UNIUSDT",
    "RUNEUSDT",
)
FROZEN_CANDIDATE_EXCHANGE_INSTRUMENT_IDS = tuple(
    f"binance-usdm:{symbol}:perpetual" for symbol in _FROZEN_CANDIDATE_SYMBOLS
)
CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS = tuple(
    sorted(FROZEN_CANDIDATE_EXCHANGE_INSTRUMENT_IDS)
)


class SelectionMemberState(StrEnum):
    INELIGIBLE = "INELIGIBLE"
    SELECTED = "SELECTED"
    NEAR_THRESHOLD = "NEAR_THRESHOLD"
    NOT_SELECTED = "NOT_SELECTED"


class SelectionMemberReason(StrEnum):
    INVALID_OR_GEOMETRY = "INVALID_OR_GEOMETRY"
    INVALID_ATR = "INVALID_ATR"
    LOW_ACTIVITY = "LOW_ACTIVITY"


class SelectionAttemptOutcome(StrEnum):
    SNAPSHOT_READY = "SNAPSHOT_READY"
    SOURCE_FAILED = "SOURCE_FAILED"
    COMPUTE_FAILED = "COMPUTE_FAILED"


class SelectionSourceIntegrityError(RuntimeError):
    """The full fixed Candidate Panel cannot be proven from closed source data."""


class SelectionKline(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    open_time_ms: int
    close_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    quote_volume: Decimal

    @field_validator(
        "open",
        "high",
        "low",
        "close",
        "quote_volume",
        mode="before",
    )
    @classmethod
    def _reject_float_market_value(cls, value: object) -> object:
        if isinstance(value, float):
            raise TypeError("Selection market values cannot enter through float")
        return value

    @model_validator(mode="after")
    def _validate_kline(self) -> SelectionKline:
        if self.open_time_ms <= 0 or self.open_time_ms % INTERVAL_MS != 0:
            raise ValueError("Selection Kline open time must be an exact 15m boundary")
        if self.close_time_ms != self.open_time_ms + INTERVAL_MS:
            raise ValueError("Selection Kline close time must use the exclusive boundary")
        prices = (self.open, self.high, self.low, self.close)
        if not all(value.is_finite() and value > 0 for value in prices):
            raise ValueError("Selection Kline OHLC must be finite and positive")
        if not self.quote_volume.is_finite() or self.quote_volume < 0:
            raise ValueError("Selection Kline quote volume must be finite and nonnegative")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("Selection Kline high is inconsistent with OHLC")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("Selection Kline low is inconsistent with OHLC")
        return self


class SelectionSourceWindow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_instrument_id: str
    input_window_start_ms: int
    feature_cutoff_at_ms: int
    klines: tuple[SelectionKline, ...]

    @field_validator("exchange_instrument_id", mode="before")
    @classmethod
    def _require_source_instrument(cls, value: object) -> str:
        normalized = str(value or "").strip()
        parse_binance_usdm_instrument_id(normalized)
        return normalized

    @model_validator(mode="after")
    def _validate_window(self) -> SelectionSourceWindow:
        if len(self.klines) != 96:
            raise SelectionSourceIntegrityError(
                "Selection source requires exact 96 closed 15m Klines"
            )
        expected_times = tuple(
            self.input_window_start_ms + index * INTERVAL_MS for index in range(96)
        )
        actual_times = tuple(item.open_time_ms for item in self.klines)
        if any(item.close_time_ms > self.feature_cutoff_at_ms for item in self.klines):
            raise SelectionSourceIntegrityError(
                "Selection source contains a future or open Kline"
            )
        if actual_times != expected_times or len(set(actual_times)) != 96:
            raise SelectionSourceIntegrityError(
                "Selection source Klines must be unique and continuous"
            )
        if self.klines[-1].close_time_ms != self.feature_cutoff_at_ms:
            raise SelectionSourceIntegrityError(
                "Selection source requires exact closed Klines at feature cutoff"
            )
        return self

    @property
    def input_window_digest(self) -> str:
        return _semantic_digest(
            [
                [
                    item.open_time_ms,
                    _canonical_decimal(item.open),
                    _canonical_decimal(item.high),
                    _canonical_decimal(item.low),
                    _canonical_decimal(item.close),
                    _canonical_decimal(item.quote_volume),
                ]
                for item in self.klines
            ]
        )


class SelectionSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    selection_snapshot_id: str
    selection_spec_id: str
    strategy_group_id: str
    strategy_version_id: str
    session_start_ms: int
    decision_at_ms: int
    feature_cutoff_at_ms: int
    eligibility_not_before_ms: int
    expires_at_ms: int
    candidate_count: int
    ready_count: int
    selected_count: int
    source_observed_at_ms: int
    source_semantic_digest: str
    selection_semantic_digest: str
    created_at_ms: int

    @field_validator("source_semantic_digest", "selection_semantic_digest")
    @classmethod
    def _validate_snapshot_digest(cls, value: str) -> str:
        return _require_sha256(value)

    @model_validator(mode="after")
    def _validate_snapshot(self) -> SelectionSnapshot:
        expected_id = f"selection:{self.selection_spec_id}:{self.session_start_ms}"
        if self.selection_snapshot_id != expected_id:
            raise ValueError("Selection Snapshot identity is not canonical")
        if self.candidate_count != 24:
            raise ValueError("Selection Snapshot requires exact 24 candidates")
        if not 0 <= self.ready_count <= 24:
            raise ValueError("Selection Snapshot ready count is invalid")
        if self.selected_count != min(7, self.ready_count):
            raise ValueError("Selection Snapshot selected count is not canonical")
        if self.feature_cutoff_at_ms != self.session_start_ms + HOUR_MS:
            raise ValueError("Selection Snapshot feature cutoff is invalid")
        if self.eligibility_not_before_ms != self.session_start_ms + 5 * INTERVAL_MS:
            raise ValueError("Selection Snapshot eligibility time is invalid")
        if self.expires_at_ms != self.session_start_ms + DAY_MS + HOUR_MS:
            raise ValueError("Selection Snapshot expiry is invalid")
        if min(
            self.decision_at_ms,
            self.source_observed_at_ms,
            self.created_at_ms,
        ) < self.feature_cutoff_at_ms:
            raise ValueError("Selection Snapshot cannot precede the feature cutoff")
        return self


class SelectionJobClaim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    selection_job_id: str
    selection_spec_id: str
    session_start_ms: int
    worker_id: str
    attempt_number: int
    projection_version: int
    started_at_ms: int
    lease_expires_at_ms: int

    @model_validator(mode="after")
    def _validate_claim(self) -> SelectionJobClaim:
        expected_id = f"selection-job:{self.selection_spec_id}:{self.session_start_ms}"
        if self.selection_job_id != expected_id:
            raise ValueError("Selection Job identity is not canonical")
        if not self.worker_id.strip():
            raise ValueError("Selection Job worker identity must be non-blank")
        if self.attempt_number <= 0 or self.projection_version <= 0:
            raise ValueError("Selection Job versions must be positive")
        if self.lease_expires_at_ms <= self.started_at_ms:
            raise ValueError("Selection Job lease must expire after claim")
        return self


class SelectionJobFailure(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    selection_job_id: str
    outcome: Literal["SOURCE_FAILED", "COMPUTE_FAILED"]
    reason_code: str

    @field_validator("selection_job_id", "reason_code", mode="before")
    @classmethod
    def _require_failure_fact(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Selection terminal failure facts must be non-blank")
        return normalized


class _MemberDigestPayload(TypedDict):
    selection_snapshot_id: str
    member_decision_id: str
    selection_spec_id: str
    session_start_ms: int
    feature_cutoff_at_ms: int
    input_window_start_ms: int
    input_window_end_ms: int
    exchange_instrument_id: str
    input_window_digest: str
    source_status: Literal["READY"]
    or_high: Decimal
    or_low: Decimal
    or_width: Decimal
    pre_or_atr14: Decimal
    pre_or_width_atr14: Decimal
    trailing_24h_quote_volume: Decimal
    or_geometry_valid: bool
    atr_valid: bool
    activity_valid: bool
    selection_ready: bool
    primary_reason: SelectionMemberReason | None
    secondary_reasons: tuple[SelectionMemberReason, ...]
    stable_rank: int | None
    member_state: SelectionMemberState
    selected: bool


class SelectionPeriod(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    session_start_ms: int
    decision_boundary_ms: int
    feature_cutoff_at_ms: int
    eligibility_not_before_ms: int
    expires_at_ms: int

    @model_validator(mode="after")
    def _validate_period(self) -> SelectionPeriod:
        if self.session_start_ms <= 0 or self.session_start_ms % DAY_MS != 0:
            raise ValueError("SOR session identity must be exact 00:00 UTC")
        if self.decision_boundary_ms != self.session_start_ms + HOUR_MS:
            raise ValueError("Selection Period must start at the 01:00 UTC decision boundary")
        if self.feature_cutoff_at_ms != self.decision_boundary_ms:
            raise ValueError("feature cutoff must equal the Selection decision boundary")
        if self.eligibility_not_before_ms != self.session_start_ms + 5 * INTERVAL_MS:
            raise ValueError("first SOR eligibility must be the canonical 01:15 close")
        if self.expires_at_ms != self.session_start_ms + DAY_MS + HOUR_MS:
            raise ValueError("Selection Period must expire at the next decision boundary")
        return self


class SorDynamicSelectionSpecV0(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    selection_spec_id: str
    strategy_group_id: str
    strategy_version_id: str
    event_spec_ids: tuple[str, ...]
    candidate_exchange_instrument_ids: tuple[str, ...]
    decision_offset_utc_seconds: int = 3600
    feature_cutoff_offset_utc_seconds: int = 3600
    eligibility_not_before_offset_utc_seconds: int = 4500
    valid_until_next_decision_offset_seconds: int = 86400
    input_window_bars: int = 96
    opening_range_bars: int = 4
    pre_or_atr_bars: int = 14
    activity_floor_quote_usdt: Decimal = ACTIVITY_FLOOR_QUOTE_USDT
    selected_count_max: int = 7
    near_count_max: int = 7
    decimal_precision: int = DECIMAL_PRECISION
    decimal_rounding: Literal["ROUND_HALF_EVEN"] = "ROUND_HALF_EVEN"
    algorithm_semantic_digest: str
    installed_at_ms: int

    @field_validator(
        "selection_spec_id",
        "strategy_group_id",
        "strategy_version_id",
        mode="before",
    )
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Selection identity must be non-blank")
        return normalized

    @field_validator("activity_floor_quote_usdt", mode="before")
    @classmethod
    def _reject_float_activity_floor(cls, value: object) -> object:
        if isinstance(value, float):
            raise TypeError("Selection financial values cannot enter through float")
        return value

    @model_validator(mode="after")
    def _validate_spec(self) -> SorDynamicSelectionSpecV0:
        if self.strategy_group_id != SOR_STRATEGY_GROUP_ID:
            raise ValueError("SOR Dynamic Selection V0 requires exact StrategyGroup")
        if self.strategy_version_id != SOR_STRATEGY_VERSION_ID:
            raise ValueError("SOR Dynamic Selection V0 requires exact StrategyVersion")
        if self.event_spec_ids != SOR_EVENT_SPEC_IDS:
            raise ValueError("selection spec requires exact LONG and SHORT EventSpecs")
        if (
            len(self.candidate_exchange_instrument_ids) != 24
            or self.candidate_exchange_instrument_ids
            != CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS
        ):
            raise ValueError("selection spec requires exact 24 canonical candidates")
        for exchange_instrument_id in self.candidate_exchange_instrument_ids:
            parse_binance_usdm_instrument_id(exchange_instrument_id)
        if self.activity_floor_quote_usdt != ACTIVITY_FLOOR_QUOTE_USDT:
            raise ValueError("selection activity floor must remain frozen at 20M USDT")
        if (
            self.decision_offset_utc_seconds,
            self.feature_cutoff_offset_utc_seconds,
            self.eligibility_not_before_offset_utc_seconds,
            self.valid_until_next_decision_offset_seconds,
            self.input_window_bars,
            self.opening_range_bars,
            self.pre_or_atr_bars,
            self.selected_count_max,
            self.near_count_max,
            self.decimal_precision,
            self.decimal_rounding,
        ) != (3600, 3600, 4500, 86400, 96, 4, 14, 7, 7, 38, "ROUND_HALF_EVEN"):
            raise ValueError("SOR Dynamic Selection V0 parameters are immutable")
        if self.algorithm_semantic_digest != _algorithm_semantic_digest():
            raise ValueError("selection algorithm semantic digest is not canonical")
        if self.installed_at_ms <= 0:
            raise ValueError("selection spec install time must be positive")
        return self


class SelectionMemberDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    selection_snapshot_id: str
    member_decision_id: str
    selection_spec_id: str
    session_start_ms: int
    feature_cutoff_at_ms: int
    input_window_start_ms: int
    input_window_end_ms: int
    exchange_instrument_id: str
    input_window_digest: str
    source_status: Literal["READY"] = "READY"
    or_high: Decimal
    or_low: Decimal
    or_width: Decimal
    pre_or_atr14: Decimal
    pre_or_width_atr14: Decimal
    trailing_24h_quote_volume: Decimal
    or_geometry_valid: bool
    atr_valid: bool
    activity_valid: bool
    selection_ready: bool
    primary_reason: SelectionMemberReason | None
    secondary_reasons: tuple[SelectionMemberReason, ...] = ()
    stable_rank: int | None
    member_state: SelectionMemberState
    selected: bool
    member_semantic_digest: str

    @field_validator(
        "selection_snapshot_id",
        "member_decision_id",
        "selection_spec_id",
        "exchange_instrument_id",
        mode="before",
    )
    @classmethod
    def _require_member_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Selection member identity must be non-blank")
        return normalized

    @field_validator("input_window_digest", "member_semantic_digest")
    @classmethod
    def _require_digest(cls, value: str) -> str:
        return _require_sha256(value)

    @field_validator(
        "or_high",
        "or_low",
        "or_width",
        "pre_or_atr14",
        "pre_or_width_atr14",
        "trailing_24h_quote_volume",
        mode="before",
    )
    @classmethod
    def _reject_float_financial_input(cls, value: object) -> object:
        if isinstance(value, float):
            raise TypeError("Selection financial values cannot enter through float")
        return value

    @model_validator(mode="after")
    def _validate_decision(self) -> SelectionMemberDecision:
        parse_binance_usdm_instrument_id(self.exchange_instrument_id)
        if self.session_start_ms <= 0 or self.session_start_ms % DAY_MS != 0:
            raise ValueError("Selection member session must be exact 00:00 UTC")
        if self.feature_cutoff_at_ms != self.session_start_ms + HOUR_MS:
            raise ValueError("Selection member cutoff must be exact 01:00 UTC")
        if self.input_window_start_ms != self.session_start_ms - 23 * HOUR_MS:
            raise ValueError("Selection member requires the exact 96-bar input start")
        if self.input_window_end_ms != self.feature_cutoff_at_ms:
            raise ValueError("Selection member input window must end at feature cutoff")
        expected_member_id = f"{self.selection_snapshot_id}:{self.exchange_instrument_id}"
        if self.member_decision_id != expected_member_id:
            raise ValueError("Selection member decision identity is not canonical")
        for value in (
            self.or_high,
            self.or_low,
            self.or_width,
            self.pre_or_atr14,
            self.pre_or_width_atr14,
            self.trailing_24h_quote_volume,
        ):
            if not value.is_finite():
                raise ValueError("Selection member numeric facts must be finite")
        if self.or_high <= 0 or self.or_low <= 0:
            raise ValueError("Selection member OR prices must be positive")
        if self.pre_or_atr14 < 0 or self.trailing_24h_quote_volume < 0:
            raise ValueError("Selection member ATR and activity must be nonnegative")
        with localcontext(DECIMAL_CONTEXT):
            expected_width = self.or_high - self.or_low
            expected_ratio = (
                Decimal(0)
                if self.pre_or_atr14 <= 0
                else expected_width / self.pre_or_atr14
            )
        if self.or_width != expected_width or self.pre_or_width_atr14 != expected_ratio:
            raise ValueError("Selection member Decimal geometry is not canonical")
        expected_geometry_valid = self.or_high > self.or_low
        expected_atr_valid = self.pre_or_atr14 > 0
        expected_activity_valid = (
            self.trailing_24h_quote_volume >= ACTIVITY_FLOOR_QUOTE_USDT
        )
        if (
            self.or_geometry_valid,
            self.atr_valid,
            self.activity_valid,
        ) != (
            expected_geometry_valid,
            expected_atr_valid,
            expected_activity_valid,
        ):
            raise ValueError("Selection member qualification booleans are not canonical")
        if (
            self.member_state is SelectionMemberState.INELIGIBLE
            and self.primary_reason is None
        ):
            raise ValueError("ineligible member requires one reason")
        expected_reason = _primary_reason(
            or_geometry_valid=expected_geometry_valid,
            atr_valid=expected_atr_valid,
            activity_valid=expected_activity_valid,
        )
        if self.primary_reason is not expected_reason:
            raise ValueError("Selection member primary reason is not canonical")
        if self.secondary_reasons:
            raise ValueError("SOR Dynamic Selection V0 has no secondary member reasons")
        expected_ready = expected_reason is None
        if self.selection_ready is not expected_ready:
            raise ValueError("Selection member readiness is not canonical")
        self._validate_rank_state_contract()
        if self.member_semantic_digest != _member_semantic_digest(self):
            raise ValueError("Selection member semantic digest is not canonical")
        return self

    def _validate_rank_state_contract(self) -> None:
        if not self.selection_ready:
            if self.primary_reason is None:
                raise ValueError("ineligible member requires one reason")
            if self.stable_rank is not None:
                raise ValueError("ineligible member cannot have a stable rank")
            if self.member_state is not SelectionMemberState.INELIGIBLE:
                raise ValueError("ineligible member requires INELIGIBLE state")
            if self.selected:
                raise ValueError("ineligible member cannot be selected")
            return
        if self.primary_reason is not None:
            raise ValueError("selection-ready member cannot have an ineligible reason")
        if self.stable_rank is None or not 1 <= self.stable_rank <= 24:
            raise ValueError("selection-ready member requires rank 1 through 24")
        if self.member_state is SelectionMemberState.SELECTED:
            if not 1 <= self.stable_rank <= 7:
                raise ValueError("selected member requires rank 1 through 7")
            if not self.selected:
                raise ValueError("SELECTED state requires selected=true")
            return
        if self.member_state is SelectionMemberState.NEAR_THRESHOLD:
            if not 8 <= self.stable_rank <= 14:
                raise ValueError("near-threshold member requires rank 8 through 14")
        elif self.member_state is SelectionMemberState.NOT_SELECTED:
            if self.stable_rank < 15:
                raise ValueError("not-selected member requires rank 15 or later")
        else:
            raise ValueError("selection-ready member cannot use INELIGIBLE state")
        if self.selected:
            raise ValueError("non-selected rank state requires selected=false")


class SelectionComputation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshot: SelectionSnapshot
    member_decisions: tuple[SelectionMemberDecision, ...]

    @model_validator(mode="after")
    def _validate_computation(self) -> SelectionComputation:
        if len(self.member_decisions) != self.snapshot.candidate_count:
            raise ValueError("Selection computation requires exact member cardinality")
        if tuple(
            item.exchange_instrument_id for item in self.member_decisions
        ) != tuple(
            sorted(item.exchange_instrument_id for item in self.member_decisions)
        ):
            raise ValueError("Selection member decisions must use canonical order")
        if any(
            item.selection_snapshot_id != self.snapshot.selection_snapshot_id
            or item.selection_spec_id != self.snapshot.selection_spec_id
            or item.session_start_ms != self.snapshot.session_start_ms
            for item in self.member_decisions
        ):
            raise ValueError("Selection member lineage differs from Snapshot")
        return self


@dataclass(frozen=True)
class _SelectionFeatures:
    window: SelectionSourceWindow
    or_high: Decimal
    or_low: Decimal
    pre_or_atr14: Decimal
    ratio: Decimal
    trailing_volume: Decimal
    reason: SelectionMemberReason | None


def build_sor_dynamic_selection_period(*, session_start_ms: int) -> SelectionPeriod:
    return SelectionPeriod(
        session_start_ms=session_start_ms,
        decision_boundary_ms=session_start_ms + HOUR_MS,
        feature_cutoff_at_ms=session_start_ms + HOUR_MS,
        eligibility_not_before_ms=session_start_ms + 5 * INTERVAL_MS,
        expires_at_ms=session_start_ms + DAY_MS + HOUR_MS,
    )


def build_sor_dynamic_selection_spec_v0(
    *,
    selection_spec_id: str,
    strategy_group_id: str,
    strategy_version_id: str,
    event_spec_ids: tuple[str, ...],
    candidate_exchange_instrument_ids: tuple[str, ...],
    installed_at_ms: int,
) -> SorDynamicSelectionSpecV0:
    if len(candidate_exchange_instrument_ids) != 24:
        raise ValueError("selection spec requires exact 24 canonical candidates")
    return SorDynamicSelectionSpecV0(
        selection_spec_id=selection_spec_id,
        strategy_group_id=strategy_group_id,
        strategy_version_id=strategy_version_id,
        event_spec_ids=tuple(sorted(event_spec_ids)),
        candidate_exchange_instrument_ids=tuple(
            sorted(candidate_exchange_instrument_ids)
        ),
        algorithm_semantic_digest=_algorithm_semantic_digest(),
        installed_at_ms=installed_at_ms,
    )


def run_sor_dynamic_selection_v0(
    *,
    spec: SorDynamicSelectionSpecV0,
    period: SelectionPeriod,
    source_windows: tuple[SelectionSourceWindow, ...],
    decision_at_ms: int,
    source_observed_at_ms: int,
    created_at_ms: int,
) -> SelectionComputation:
    """Compute one immutable V0 Snapshot from the exact fixed Candidate Panel."""

    expected_candidates = spec.candidate_exchange_instrument_ids
    actual_candidates = tuple(
        sorted(window.exchange_instrument_id for window in source_windows)
    )
    if len(source_windows) != 24 or actual_candidates != expected_candidates:
        raise SelectionSourceIntegrityError(
            "Selection source requires exact 24 canonical Candidate windows"
        )
    if len(set(actual_candidates)) != 24:
        raise SelectionSourceIntegrityError(
            "Selection source requires exact 24 unique Candidate windows"
        )
    expected_start_ms = period.session_start_ms - 23 * HOUR_MS
    for window in source_windows:
        if (
            window.input_window_start_ms != expected_start_ms
            or window.feature_cutoff_at_ms != period.feature_cutoff_at_ms
        ):
            raise SelectionSourceIntegrityError(
                "Selection source window identity differs from Selection Period"
            )

    snapshot_id = f"selection:{spec.selection_spec_id}:{period.session_start_ms}"
    features: dict[str, _SelectionFeatures] = {}
    with localcontext(DECIMAL_CONTEXT):
        for window in source_windows:
            previous_close = window.klines[77].close
            true_ranges: list[Decimal] = []
            for bar in window.klines[78:92]:
                true_ranges.append(
                    max(
                        bar.high - bar.low,
                        abs(bar.high - previous_close),
                        abs(bar.low - previous_close),
                    )
                )
                previous_close = bar.close
            or_bars = window.klines[92:96]
            or_high = max(bar.high for bar in or_bars)
            or_low = min(bar.low for bar in or_bars)
            or_width = or_high - or_low
            pre_or_atr14 = sum(true_ranges, Decimal(0)) / Decimal(14)
            trailing_volume = sum(
                (bar.quote_volume for bar in window.klines), Decimal(0)
            )
            reason = _primary_reason(
                or_geometry_valid=or_high > or_low,
                atr_valid=pre_or_atr14 > 0,
                activity_valid=trailing_volume >= spec.activity_floor_quote_usdt,
            )
            features[window.exchange_instrument_id] = _SelectionFeatures(
                window=window,
                or_high=or_high,
                or_low=or_low,
                pre_or_atr14=pre_or_atr14,
                ratio=(
                    Decimal(0)
                    if pre_or_atr14 <= 0
                    else or_width / pre_or_atr14
                ),
                trailing_volume=trailing_volume,
                reason=reason,
            )

        ready_ids = sorted(
            (
                instrument_id
                for instrument_id, feature in features.items()
                if feature.reason is None
            ),
            key=lambda instrument_id: (
                features[instrument_id].ratio,
                -features[instrument_id].trailing_volume,
                instrument_id,
            ),
        )
    rank_by_instrument = {
        instrument_id: rank for rank, instrument_id in enumerate(ready_ids, start=1)
    }

    decisions: list[SelectionMemberDecision] = []
    for instrument_id in expected_candidates:
        feature = features[instrument_id]
        reason = feature.reason
        rank = rank_by_instrument.get(instrument_id)
        if reason is not None:
            state = SelectionMemberState.INELIGIBLE
        elif rank is not None and rank <= spec.selected_count_max:
            state = SelectionMemberState.SELECTED
        elif rank is not None and rank <= spec.selected_count_max + spec.near_count_max:
            state = SelectionMemberState.NEAR_THRESHOLD
        else:
            state = SelectionMemberState.NOT_SELECTED
        decisions.append(
            build_selection_member_decision(
                selection_snapshot_id=snapshot_id,
                selection_spec_id=spec.selection_spec_id,
                session_start_ms=period.session_start_ms,
                feature_cutoff_at_ms=period.feature_cutoff_at_ms,
                input_window_start_ms=feature.window.input_window_start_ms,
                exchange_instrument_id=instrument_id,
                input_window_digest=feature.window.input_window_digest,
                or_high=feature.or_high,
                or_low=feature.or_low,
                pre_or_atr14=feature.pre_or_atr14,
                trailing_24h_quote_volume=feature.trailing_volume,
                stable_rank=rank,
                member_state=state,
                primary_reason=(
                    reason
                ),
            )
        )

    source_digest = _semantic_digest(
        [
            [decision.exchange_instrument_id, decision.input_window_digest]
            for decision in decisions
        ]
    )
    ready_count = len(ready_ids)
    selected_count = min(spec.selected_count_max, ready_count)
    selection_digest = _semantic_digest(
        {
            "selection_spec_digest": spec.algorithm_semantic_digest,
            "selection_spec_id": spec.selection_spec_id,
            "session_start_ms": period.session_start_ms,
            "feature_cutoff_at_ms": period.feature_cutoff_at_ms,
            "eligibility_not_before_ms": period.eligibility_not_before_ms,
            "expires_at_ms": period.expires_at_ms,
            "candidate_count": len(decisions),
            "ready_count": ready_count,
            "selected_count": selected_count,
            "source_semantic_digest": source_digest,
            "member_semantic_digests": [
                decision.member_semantic_digest for decision in decisions
            ],
        }
    )
    snapshot = SelectionSnapshot(
        selection_snapshot_id=snapshot_id,
        selection_spec_id=spec.selection_spec_id,
        strategy_group_id=spec.strategy_group_id,
        strategy_version_id=spec.strategy_version_id,
        session_start_ms=period.session_start_ms,
        decision_at_ms=decision_at_ms,
        feature_cutoff_at_ms=period.feature_cutoff_at_ms,
        eligibility_not_before_ms=period.eligibility_not_before_ms,
        expires_at_ms=period.expires_at_ms,
        candidate_count=len(decisions),
        ready_count=ready_count,
        selected_count=selected_count,
        source_observed_at_ms=source_observed_at_ms,
        source_semantic_digest=source_digest,
        selection_semantic_digest=selection_digest,
        created_at_ms=created_at_ms,
    )
    return SelectionComputation(
        snapshot=snapshot,
        member_decisions=tuple(decisions),
    )


def build_selection_member_decision(
    *,
    selection_snapshot_id: str,
    selection_spec_id: str,
    session_start_ms: int,
    feature_cutoff_at_ms: int,
    input_window_start_ms: int,
    exchange_instrument_id: str,
    input_window_digest: str,
    or_high: Decimal,
    or_low: Decimal,
    pre_or_atr14: Decimal,
    trailing_24h_quote_volume: Decimal,
    stable_rank: int | None,
    member_state: SelectionMemberState,
    primary_reason: SelectionMemberReason | None,
) -> SelectionMemberDecision:
    if any(
        isinstance(value, float)
        for value in (or_high, or_low, pre_or_atr14, trailing_24h_quote_volume)
    ):
        raise TypeError("Selection financial values cannot enter through float")
    with localcontext(DECIMAL_CONTEXT):
        or_width = or_high - or_low
        pre_or_width_atr14 = (
            Decimal(0) if pre_or_atr14 <= 0 else or_width / pre_or_atr14
        )
    or_geometry_valid = or_high > or_low
    atr_valid = pre_or_atr14 > 0
    activity_valid = trailing_24h_quote_volume >= ACTIVITY_FLOOR_QUOTE_USDT
    selection_ready = or_geometry_valid and atr_valid and activity_valid
    selected = member_state is SelectionMemberState.SELECTED
    member_decision_id = f"{selection_snapshot_id}:{exchange_instrument_id}"
    payload: _MemberDigestPayload = {
        "selection_snapshot_id": selection_snapshot_id,
        "member_decision_id": member_decision_id,
        "selection_spec_id": selection_spec_id,
        "session_start_ms": session_start_ms,
        "feature_cutoff_at_ms": feature_cutoff_at_ms,
        "input_window_start_ms": input_window_start_ms,
        "input_window_end_ms": feature_cutoff_at_ms,
        "exchange_instrument_id": exchange_instrument_id,
        "input_window_digest": input_window_digest,
        "source_status": "READY",
        "or_high": or_high,
        "or_low": or_low,
        "or_width": or_width,
        "pre_or_atr14": pre_or_atr14,
        "pre_or_width_atr14": pre_or_width_atr14,
        "trailing_24h_quote_volume": trailing_24h_quote_volume,
        "or_geometry_valid": or_geometry_valid,
        "atr_valid": atr_valid,
        "activity_valid": activity_valid,
        "selection_ready": selection_ready,
        "primary_reason": primary_reason,
        "secondary_reasons": (),
        "stable_rank": stable_rank,
        "member_state": member_state,
        "selected": selected,
    }
    decision = SelectionMemberDecision(
        selection_snapshot_id=selection_snapshot_id,
        member_decision_id=member_decision_id,
        selection_spec_id=selection_spec_id,
        session_start_ms=session_start_ms,
        feature_cutoff_at_ms=feature_cutoff_at_ms,
        input_window_start_ms=input_window_start_ms,
        input_window_end_ms=feature_cutoff_at_ms,
        exchange_instrument_id=exchange_instrument_id,
        input_window_digest=input_window_digest,
        source_status="READY",
        or_high=or_high,
        or_low=or_low,
        or_width=or_width,
        pre_or_atr14=pre_or_atr14,
        pre_or_width_atr14=pre_or_width_atr14,
        trailing_24h_quote_volume=trailing_24h_quote_volume,
        or_geometry_valid=or_geometry_valid,
        atr_valid=atr_valid,
        activity_valid=activity_valid,
        selection_ready=selection_ready,
        primary_reason=primary_reason,
        secondary_reasons=(),
        stable_rank=stable_rank,
        member_state=member_state,
        selected=selected,
        member_semantic_digest=_member_semantic_digest_payload(payload),
    )
    return decision


def _primary_reason(
    *,
    or_geometry_valid: bool,
    atr_valid: bool,
    activity_valid: bool,
) -> SelectionMemberReason | None:
    if not or_geometry_valid:
        return SelectionMemberReason.INVALID_OR_GEOMETRY
    if not atr_valid:
        return SelectionMemberReason.INVALID_ATR
    if not activity_valid:
        return SelectionMemberReason.LOW_ACTIVITY
    return None


def _algorithm_semantic_digest() -> str:
    return _semantic_digest(
        {
            "research_spec_id": "sor-dynamic-selection-v0",
            "strategy_group_id": SOR_STRATEGY_GROUP_ID,
            "strategy_version_id": SOR_STRATEGY_VERSION_ID,
            "event_spec_ids": list(SOR_EVENT_SPEC_IDS),
            "candidate_exchange_instrument_ids": list(
                FROZEN_CANDIDATE_EXCHANGE_INSTRUMENT_IDS
            ),
            "selection_timezone": "UTC",
            "selection_time": "01:00:00",
            "feature_cutoff_offset_ms": HOUR_MS,
            "eligibility_not_before_offset_ms": 5 * INTERVAL_MS,
            "expires_offset_ms": DAY_MS + HOUR_MS,
            "input_window_bars": 96,
            "or_bars": 4,
            "pre_or_atr_bars": 14,
            "activity_floor_quote_usdt": "20000000",
            "ranking": [
                "pre_or_width_atr14:asc",
                "trailing_24h_quote_volume:desc",
                "exchange_instrument_id:asc",
            ],
            "selected_cap": 7,
            "near_rank_start": 8,
            "near_rank_end": 14,
            "decimal_context": {
                "precision": DECIMAL_PRECISION,
                "rounding": "ROUND_HALF_EVEN",
            },
            "feature_numeric_type": "decimal.Decimal",
            "canonical_decimal": "normalize; zero='0'; fixed-point; no exponent",
            "digest_serialization": "utf8-json; sort_keys=true; separators=(',', ':')",
        }
    )


def _member_semantic_digest(decision: SelectionMemberDecision) -> str:
    return _member_semantic_digest_payload(
        {
            "selection_snapshot_id": decision.selection_snapshot_id,
            "member_decision_id": decision.member_decision_id,
            "selection_spec_id": decision.selection_spec_id,
            "session_start_ms": decision.session_start_ms,
            "feature_cutoff_at_ms": decision.feature_cutoff_at_ms,
            "input_window_start_ms": decision.input_window_start_ms,
            "input_window_end_ms": decision.input_window_end_ms,
            "exchange_instrument_id": decision.exchange_instrument_id,
            "input_window_digest": decision.input_window_digest,
            "source_status": decision.source_status,
            "or_high": decision.or_high,
            "or_low": decision.or_low,
            "or_width": decision.or_width,
            "pre_or_atr14": decision.pre_or_atr14,
            "pre_or_width_atr14": decision.pre_or_width_atr14,
            "trailing_24h_quote_volume": decision.trailing_24h_quote_volume,
            "or_geometry_valid": decision.or_geometry_valid,
            "atr_valid": decision.atr_valid,
            "activity_valid": decision.activity_valid,
            "selection_ready": decision.selection_ready,
            "primary_reason": decision.primary_reason,
            "secondary_reasons": decision.secondary_reasons,
            "stable_rank": decision.stable_rank,
            "member_state": decision.member_state,
            "selected": decision.selected,
        }
    )


def _member_semantic_digest_payload(payload: _MemberDigestPayload) -> str:
    identity = parse_binance_usdm_instrument_id(payload["exchange_instrument_id"])
    primary_reason = payload["primary_reason"]
    member_state = payload["member_state"]
    return _semantic_digest(
        {
            "selection_snapshot_id": str(payload["selection_snapshot_id"]),
            "member_decision_id": str(payload["member_decision_id"]),
            "selection_spec_id": str(payload["selection_spec_id"]),
            "session_start_ms": str(payload["session_start_ms"]),
            "feature_cutoff_at_ms": str(payload["feature_cutoff_at_ms"]),
            "input_window_start_ms": str(payload["input_window_start_ms"]),
            "input_window_end_ms": str(payload["input_window_end_ms"]),
            "exchange_instrument_id": str(payload["exchange_instrument_id"]),
            "symbol": identity.symbol,
            "input_window_digest": str(payload["input_window_digest"]),
            "source_status": str(payload["source_status"]),
            "or_high": _canonical_decimal(payload["or_high"]),
            "or_low": _canonical_decimal(payload["or_low"]),
            "or_width": _canonical_decimal(payload["or_width"]),
            "pre_or_atr14": _canonical_decimal(payload["pre_or_atr14"]),
            "pre_or_width_atr14": _canonical_decimal(
                payload["pre_or_width_atr14"]
            ),
            "trailing_24h_quote_volume": _canonical_decimal(
                payload["trailing_24h_quote_volume"]
            ),
            "or_geometry_valid": str(payload["or_geometry_valid"]).lower(),
            "atr_valid": str(payload["atr_valid"]).lower(),
            "activity_valid": str(payload["activity_valid"]).lower(),
            "selection_ready": str(payload["selection_ready"]).lower(),
            "primary_reason": "" if primary_reason is None else str(primary_reason),
            "secondary_reasons_json": "[]",
            "stable_rank": "" if payload["stable_rank"] is None else str(payload["stable_rank"]),
            "member_state": str(member_state),
            "selected": str(payload["selected"]).lower(),
        }
    )


def _canonical_decimal(value: Decimal) -> str:
    with localcontext(DECIMAL_CONTEXT):
        normalized = value.normalize()
    return "0" if normalized == 0 else format(normalized, "f")


def _semantic_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


def _require_sha256(value: str) -> str:
    if len(value) != 71 or not value.startswith("sha256:"):
        raise ValueError("Selection digest must be canonical sha256")
    try:
        int(value[7:], 16)
    except ValueError as exc:
        raise ValueError("Selection digest must be canonical sha256") from exc
    return value
