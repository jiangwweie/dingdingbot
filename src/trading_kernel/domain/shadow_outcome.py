"""Pure fixed-horizon excursion evidence for rejected portfolio admission."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.domain.market import ClosedCandle

SHADOW_EVALUATION_KIND: Final = "fixed_horizon_excursion_v1"


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
    admission_decision_id: str
    exchange_instrument_id: str
    position_side: Literal["long", "short"]
    timeframe: Literal["15m", "1h"]
    entry_reference_price: Decimal
    initial_stop_price: Decimal
    horizon_start_ms: int
    horizon_end_ms: int
    created_at_ms: int

    @field_validator(
        "shadow_outcome_id",
        "admission_decision_id",
        "exchange_instrument_id",
        mode="before",
    )
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("shadow identities must be non-blank")
        return normalized

    @field_validator("entry_reference_price", "initial_stop_price")
    @classmethod
    def _require_positive_price(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0:
            raise ValueError("shadow reference prices must be finite and positive")
        return value

    @model_validator(mode="after")
    def _validate_spec(self) -> ShadowOutcomeSpec:
        if (
            self.horizon_start_ms <= 0
            or self.horizon_end_ms <= self.horizon_start_ms
            or self.created_at_ms <= 0
        ):
            raise ValueError("shadow horizon and creation time must be positive")
        return self

    @property
    def initial_risk_per_unit(self) -> Decimal:
        return abs(self.entry_reference_price - self.initial_stop_price)


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

    evaluation_kind: Literal["fixed_horizon_excursion_v1"]
    max_favorable_price: Decimal | None
    max_adverse_price: Decimal | None
    mfe_r: Decimal | None
    mae_r: Decimal | None
    observed_through_ms: int | None

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
        return self


def evaluate_fixed_horizon_excursion(
    spec: ShadowOutcomeSpec,
    candles: tuple[ClosedCandle, ...],
) -> ShadowOutcomeProjection:
    """Evaluate MFE/MAE from closed candles in the immutable horizon only."""

    if spec.initial_risk_per_unit <= 0:
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
            (favorable - spec.entry_reference_price) / spec.initial_risk_per_unit,
        )
        mae_r = max(
            Decimal(0),
            (spec.entry_reference_price - adverse) / spec.initial_risk_per_unit,
        )
    else:
        favorable = min(candle.low for candle in selected)
        adverse = max(candle.high for candle in selected)
        mfe_r = max(
            Decimal(0),
            (spec.entry_reference_price - favorable) / spec.initial_risk_per_unit,
        )
        mae_r = max(
            Decimal(0),
            (adverse - spec.entry_reference_price) / spec.initial_risk_per_unit,
        )
    return ShadowOutcomeProjection(
        evaluation_kind=SHADOW_EVALUATION_KIND,
        max_favorable_price=favorable,
        max_adverse_price=adverse,
        mfe_r=mfe_r,
        mae_r=mae_r,
        observed_through_ms=max(candle.close_time_ms for candle in selected),
    )


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
