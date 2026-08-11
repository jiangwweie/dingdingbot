"""Pure fixed-horizon excursion evidence for rejected portfolio admission."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.domain.market import ClosedCandle

SHADOW_EVALUATION_KIND: Final = "fixed_horizon_excursion_v1"
SOR_PATH_EVALUATION_KIND: Final = "sor_path_observation_v1"
ShadowSourceKind = Literal["portfolio_rejection", "strategy_observation"]
ShadowEvaluationKind = Literal[
    "fixed_horizon_excursion_v1",
    "sor_path_observation_v1",
]
ShadowFirstPath = Literal[
    "tp1_first",
    "initial_stop_first",
    "ambiguous_same_bar",
    "opening_range_failure",
    "time_stop",
    "session_exit",
    "horizon_complete",
]


class ShadowOutcomeStatus(StrEnum):
    PENDING = "pending"
    CLAIMED = "claimed"
    COMPLETED = "completed"
    UNAVAILABLE = "unavailable"


class ShadowOutcomeUnavailable(ValueError):
    """Frozen Shadow evidence cannot produce a valid excursion projection."""


class ShadowOutcomeSpec(BaseModel):
    """Frozen references required to evaluate one read-only opportunity."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    shadow_outcome_id: str
    signal_event_id: str
    admission_decision_id: str | None
    source_kind: ShadowSourceKind = "portfolio_rejection"
    evaluation_kind: ShadowEvaluationKind = SHADOW_EVALUATION_KIND
    exchange_instrument_id: str
    position_side: Literal["long", "short"]
    timeframe: Literal["15m", "1h"]
    entry_reference_price: Decimal | None
    initial_stop_price: Decimal | None
    take_profit_price: Decimal | None = None
    opening_range_boundary_price: Decimal | None = None
    session_exit_deadline_ms: int | None = None
    mark_price: Decimal | None = None
    index_price: Decimal | None = None
    funding_rate: Decimal | None = None
    best_bid_price: Decimal | None = None
    best_ask_price: Decimal | None = None
    best_bid_quantity: Decimal | None = None
    best_ask_quantity: Decimal | None = None
    unavailable_reason: str | None = None
    horizon_start_ms: int
    horizon_end_ms: int
    created_at_ms: int

    @field_validator(
        "shadow_outcome_id",
        "signal_event_id",
        "exchange_instrument_id",
        mode="before",
    )
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("shadow identities must be non-blank")
        return normalized

    @field_validator(
        "entry_reference_price",
        "initial_stop_price",
        "take_profit_price",
        "opening_range_boundary_price",
        "mark_price",
        "index_price",
        "best_bid_price",
        "best_ask_price",
    )
    @classmethod
    def _require_positive_price(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and (not value.is_finite() or value <= 0):
            raise ValueError("shadow reference prices must be finite and positive")
        return value

    @field_validator(
        "best_bid_quantity",
        "best_ask_quantity",
    )
    @classmethod
    def _require_nonnegative_quantity(
        cls,
        value: Decimal | None,
    ) -> Decimal | None:
        if value is not None and (not value.is_finite() or value < 0):
            raise ValueError("shadow quote quantity must be finite and nonnegative")
        return value

    @field_validator("funding_rate")
    @classmethod
    def _require_finite_optional_decimal(
        cls,
        value: Decimal | None,
    ) -> Decimal | None:
        if value is not None and not value.is_finite():
            raise ValueError("shadow funding rate must be finite")
        return value

    @field_validator("admission_decision_id", "unavailable_reason", mode="before")
    @classmethod
    def _normalize_optional_text(cls, value: object) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @model_validator(mode="after")
    def _validate_spec(self) -> ShadowOutcomeSpec:
        if (
            self.horizon_start_ms <= 0
            or self.horizon_end_ms <= self.horizon_start_ms
            or self.created_at_ms <= 0
        ):
            raise ValueError("shadow horizon and creation time must be positive")
        if (
            self.session_exit_deadline_ms is not None
            and self.session_exit_deadline_ms <= self.horizon_start_ms
        ):
            raise ValueError("shadow Session exit must follow its horizon start")
        prices_complete = (
            self.entry_reference_price is not None
            and self.initial_stop_price is not None
        )
        if self.source_kind == "portfolio_rejection":
            if (
                self.admission_decision_id is None
                or self.evaluation_kind != SHADOW_EVALUATION_KIND
                or not prices_complete
                or self.unavailable_reason is not None
            ):
                raise ValueError("portfolio Shadow requires exact Admission inputs")
        else:
            if self.evaluation_kind != SOR_PATH_EVALUATION_KIND:
                raise ValueError("strategy observation requires SOR path evaluation")
            plan_complete = (
                prices_complete
                and self.take_profit_price is not None
                and self.opening_range_boundary_price is not None
                and self.session_exit_deadline_ms is not None
            )
            if plan_complete == (self.unavailable_reason is not None):
                raise ValueError(
                    "strategy observation requires a complete plan or unavailable reason"
                )
        return self

    @property
    def initial_risk_per_unit(self) -> Decimal | None:
        if self.entry_reference_price is None or self.initial_stop_price is None:
            return None
        return abs(self.entry_reference_price - self.initial_stop_price)

    @property
    def spread_bps(self) -> Decimal | None:
        if self.best_bid_price is None or self.best_ask_price is None:
            return None
        midpoint = (self.best_bid_price + self.best_ask_price) / Decimal(2)
        if midpoint <= 0:
            return None
        return (self.best_ask_price - self.best_bid_price) / midpoint * Decimal(10_000)

    @property
    def mark_index_deviation_bps(self) -> Decimal | None:
        if self.mark_price is None or self.index_price is None or self.index_price <= 0:
            return None
        return abs(self.mark_price - self.index_price) / self.index_price * Decimal(10_000)


class ShadowOutcomeClaim(BaseModel):
    """One exact leased attempt to project a frozen Shadow specification."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    spec: ShadowOutcomeSpec
    claim_owner: str
    claim_token: str
    projection_version: int
    lease_until_ms: int

    @field_validator("claim_owner", "claim_token", mode="before")
    @classmethod
    def _require_claim_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Shadow claim identities must be non-blank")
        return normalized

    @model_validator(mode="after")
    def _validate_claim(self) -> ShadowOutcomeClaim:
        if self.projection_version <= 0 or self.lease_until_ms <= 0:
            raise ValueError("Shadow claim version and lease must be positive")
        return self


class ShadowOutcomeProjection(BaseModel):
    """Observed MFE/MAE only; it is never a simulated trade result."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    evaluation_kind: ShadowEvaluationKind
    max_favorable_price: Decimal | None
    max_adverse_price: Decimal | None
    mfe_r: Decimal | None
    mae_r: Decimal | None
    observed_through_ms: int | None
    first_path: ShadowFirstPath | None = None
    first_path_at_ms: int | None = None
    observed_bar_count: int | None = None

    @model_validator(mode="after")
    def _validate_projection_shape(self) -> ShadowOutcomeProjection:
        values = (
            self.max_favorable_price,
            self.max_adverse_price,
            self.mfe_r,
            self.mae_r,
            self.observed_through_ms,
        )
        if any(value is None for value in values):
            raise ValueError("shadow projection values must be complete together")
        if self.mfe_r is not None and self.mfe_r < 0:
            raise ValueError("shadow MFE R must be nonnegative")
        if self.mae_r is not None and self.mae_r < 0:
            raise ValueError("shadow MAE R must be nonnegative")
        if self.evaluation_kind == SHADOW_EVALUATION_KIND:
            if any(
                value is not None
                for value in (
                    self.first_path,
                    self.first_path_at_ms,
                    self.observed_bar_count,
                )
            ):
                raise ValueError("fixed-horizon projection forbids SOR path fields")
        elif (
            self.first_path is None
            or self.first_path_at_ms is None
            or self.observed_bar_count is None
            or self.observed_bar_count <= 0
        ):
            raise ValueError("SOR path projection requires complete path fields")
        return self


def evaluate_fixed_horizon_excursion(
    spec: ShadowOutcomeSpec,
    candles: tuple[ClosedCandle, ...],
) -> ShadowOutcomeProjection:
    """Evaluate MFE/MAE from closed candles in the immutable horizon only."""

    entry_reference_price = spec.entry_reference_price
    initial_risk_per_unit = spec.initial_risk_per_unit
    if (
        entry_reference_price is None
        or initial_risk_per_unit is None
        or initial_risk_per_unit <= 0
    ):
        raise ShadowOutcomeUnavailable("zero_initial_risk_distance")
    selected = tuple(
        candle
        for candle in candles
        if spec.horizon_start_ms < candle.close_time_ms <= spec.horizon_end_ms
    )
    if not selected:
        raise ShadowOutcomeUnavailable("no_closed_candles_in_horizon")
    if spec.position_side == "long":
        favorable = max(candle.high for candle in selected)
        adverse = min(candle.low for candle in selected)
        mfe_r = max(
            Decimal(0),
            (favorable - entry_reference_price) / initial_risk_per_unit,
        )
        mae_r = max(
            Decimal(0),
            (entry_reference_price - adverse) / initial_risk_per_unit,
        )
    else:
        favorable = min(candle.low for candle in selected)
        adverse = max(candle.high for candle in selected)
        mfe_r = max(
            Decimal(0),
            (entry_reference_price - favorable) / initial_risk_per_unit,
        )
        mae_r = max(
            Decimal(0),
            (adverse - entry_reference_price) / initial_risk_per_unit,
        )
    return ShadowOutcomeProjection(
        evaluation_kind=SHADOW_EVALUATION_KIND,
        max_favorable_price=favorable,
        max_adverse_price=adverse,
        mfe_r=mfe_r,
        mae_r=mae_r,
        observed_through_ms=max(candle.close_time_ms for candle in selected),
    )


def evaluate_sor_path_observation(
    spec: ShadowOutcomeSpec,
    candles: tuple[ClosedCandle, ...],
) -> ShadowOutcomeProjection:
    """Evaluate the first observable SOR path without simulating execution."""

    if spec.evaluation_kind != SOR_PATH_EVALUATION_KIND:
        raise ShadowOutcomeUnavailable("unsupported_sor_path_evaluation")
    if spec.unavailable_reason is not None:
        raise ShadowOutcomeUnavailable(spec.unavailable_reason)
    if (
        spec.entry_reference_price is None
        or spec.initial_stop_price is None
        or spec.take_profit_price is None
        or spec.opening_range_boundary_price is None
        or spec.session_exit_deadline_ms is None
        or spec.initial_risk_per_unit is None
        or spec.initial_risk_per_unit <= 0
    ):
        raise ShadowOutcomeUnavailable("incomplete_sor_observation_plan")
    selected = tuple(
        candle
        for candle in candles
        if spec.horizon_start_ms < candle.close_time_ms <= spec.horizon_end_ms
    )
    if not selected:
        raise ShadowOutcomeUnavailable("no_closed_candles_in_horizon")

    first_path: ShadowFirstPath | None = None
    first_path_at_ms: int | None = None
    first_path_bar_count: int | None = None
    for index, candle in enumerate(selected, start=1):
        if spec.position_side == "long":
            tp1_hit = candle.high >= spec.take_profit_price
            stop_hit = candle.low <= spec.initial_stop_price
            opening_range_failed = candle.close <= spec.opening_range_boundary_price
        else:
            tp1_hit = candle.low <= spec.take_profit_price
            stop_hit = candle.high >= spec.initial_stop_price
            opening_range_failed = candle.close >= spec.opening_range_boundary_price
        if tp1_hit and stop_hit:
            first_path = "ambiguous_same_bar"
        elif tp1_hit:
            first_path = "tp1_first"
        elif stop_hit:
            first_path = "initial_stop_first"
        elif opening_range_failed:
            first_path = "opening_range_failure"
        elif index >= 8:
            first_path = "time_stop"
        elif candle.close_time_ms >= spec.session_exit_deadline_ms:
            first_path = "session_exit"
        if first_path is not None:
            first_path_at_ms = candle.close_time_ms
            first_path_bar_count = index
            break
    if first_path is None:
        first_path = "horizon_complete"
        first_path_at_ms = selected[-1].close_time_ms
        first_path_bar_count = len(selected)

    excursion = evaluate_fixed_horizon_excursion(
        spec.model_copy(update={"evaluation_kind": SHADOW_EVALUATION_KIND}),
        selected,
    )
    return ShadowOutcomeProjection(
        evaluation_kind=SOR_PATH_EVALUATION_KIND,
        max_favorable_price=excursion.max_favorable_price,
        max_adverse_price=excursion.max_adverse_price,
        mfe_r=excursion.mfe_r,
        mae_r=excursion.mae_r,
        observed_through_ms=excursion.observed_through_ms,
        first_path=first_path,
        first_path_at_ms=first_path_at_ms,
        observed_bar_count=first_path_bar_count,
    )


def evaluate_shadow_outcome(
    spec: ShadowOutcomeSpec,
    candles: tuple[ClosedCandle, ...],
) -> ShadowOutcomeProjection:
    if spec.evaluation_kind == SOR_PATH_EVALUATION_KIND:
        return evaluate_sor_path_observation(spec, candles)
    return evaluate_fixed_horizon_excursion(spec, candles)


def has_complete_closed_candle_sequence(
    spec: ShadowOutcomeSpec,
    candles: tuple[ClosedCandle, ...],
) -> bool:
    """Require every expected closed bar in the frozen horizon exactly once."""

    duration_ms = 3_600_000 if spec.timeframe == "1h" else 900_000
    if (spec.horizon_end_ms - spec.horizon_start_ms) % duration_ms != 0:
        return False
    expected = tuple(
        range(
            spec.horizon_start_ms + duration_ms,
            spec.horizon_end_ms + 1,
            duration_ms,
        )
    )
    actual = tuple(
        candle.close_time_ms
        for candle in candles
        if spec.horizon_start_ms < candle.close_time_ms <= spec.horizon_end_ms
    )
    return actual == expected
