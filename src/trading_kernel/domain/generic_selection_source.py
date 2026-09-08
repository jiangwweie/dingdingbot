"""Closed hourly source facts and explicit product qualification; no I/O."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.instrument_identity import (
    parse_binance_usdm_instrument_id,
)
from src.trading_kernel.domain.product import (
    InstrumentProductProfile,
    ProductCompatibilityError,
    product_compatibility_for,
    require_product_compatibility,
)

HOUR_MS = 3600000
QualificationReason = Literal["PRODUCT_PROFILE_INCOMPATIBLE", "VENUE_PRODUCT_INCOMPATIBLE", "VENUE_NOT_TRADING"]


class GenericSelectionCandle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    open_time_ms: int
    close_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    base_volume: Decimal
    quote_volume: Decimal

    @field_validator("open", "high", "low", "close", "base_volume", "quote_volume", mode="before")
    @classmethod
    def _exact_decimal(cls, value: object) -> object:
        if not isinstance(value, Decimal):
            raise TypeError("Generic source values must enter directly as Decimal")
        return value

    @model_validator(mode="after")
    def _closed_ohlcv(self) -> "GenericSelectionCandle":
        if self.open_time_ms < 0 or self.open_time_ms % HOUR_MS or self.close_time_ms != self.open_time_ms + HOUR_MS:
            raise ValueError("Generic source requires exclusive hourly boundaries")
        if any(not value.is_finite() or value <= 0 for value in (self.open, self.high, self.low, self.close)):
            raise ValueError("Generic source OHLC must be positive and finite")
        if self.high < max(self.open, self.close, self.low) or self.low > min(self.open, self.close, self.high):
            raise ValueError("Generic source OHLC is inconsistent")
        if any(not value.is_finite() or value < 0 for value in (self.base_volume, self.quote_volume)):
            raise ValueError("Generic source volumes must be finite and nonnegative")
        return self

    @property
    def canonical_values(self) -> tuple[int | str, ...]:
        return (self.open_time_ms, self.close_time_ms, *(exact_decimal_text(value) for value in (
            self.open, self.high, self.low, self.close, self.base_volume, self.quote_volume,
        )))


class GenericSelectionQualification(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_spec_id: str
    product_profile: InstrumentProductProfile
    venue_contract_type: str
    venue_margin_asset: str
    venue_status: Literal["PENDING_TRADING", "TRADING", "PRE_DELIVERING", "DELIVERING", "DELIVERED", "PRE_SETTLE", "SETTLING", "CLOSE"]
    observed_at_ms: int

    @field_validator("venue_contract_type", "venue_margin_asset")
    @classmethod
    def _known_value(cls, value: str) -> str:
        if not value.strip() or value != value.strip() or value in {"UNKNOWN", "UNAVAILABLE"}:
            raise ValueError("Generic qualification requires explicit venue product facts")
        return value

    @model_validator(mode="after")
    def _qualification_identity(self) -> "GenericSelectionQualification":
        if self.observed_at_ms <= 0:
            raise ValueError("Generic qualification requires observation time")
        product_compatibility_for(self.event_spec_id)
        return self

    @property
    def reason(self) -> QualificationReason | None:
        expected = product_compatibility_for(self.event_spec_id)
        try:
            require_product_compatibility(expected, self.product_profile)
        except ProductCompatibilityError:
            return "PRODUCT_PROFILE_INCOMPATIBLE"
        if self.venue_contract_type != expected.contract_type or self.venue_margin_asset != expected.margin_asset:
            return "VENUE_PRODUCT_INCOMPATIBLE"
        return None if self.venue_status == "TRADING" else "VENUE_NOT_TRADING"

    @property
    def semantic_digest(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))


class GenericSelectionMemberWindow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_instrument_id: str
    venue_id: Literal["binance-usdm"] = "binance-usdm"
    normalization_version: Literal["binance-raw-hourly-ohlcv-decimal-v1"] = "binance-raw-hourly-ohlcv-decimal-v1"
    candles: tuple[GenericSelectionCandle, ...]
    qualification: GenericSelectionQualification

    @model_validator(mode="after")
    def _exact_window(self) -> "GenericSelectionMemberWindow":
        parse_binance_usdm_instrument_id(self.exchange_instrument_id)
        if self.qualification.product_profile.exchange_instrument_id != self.exchange_instrument_id:
            raise ValueError("Generic source qualification instrument differs")
        if not self.candles or len(self.candles) > 73:
            raise ValueError("Generic source requires bounded nonempty candles")
        if any(b.open_time_ms != a.close_time_ms for a, b in zip(self.candles, self.candles[1:])):
            raise ValueError("Generic source candles are not contiguous")
        return self

    @property
    def closed_at_ms(self) -> tuple[int, ...]:
        return tuple(candle.close_time_ms for candle in self.candles)

    @property
    def closes(self) -> tuple[Decimal, ...]:
        return tuple(candle.close for candle in self.candles)

    @property
    def qualified(self) -> bool:
        return self.qualification.reason is None

    @property
    def input_window_digest(self) -> str:
        return canonical_digest({
            "venue_id": self.venue_id, "instrument": self.exchange_instrument_id,
            "normalization_version": self.normalization_version,
            "candles": tuple(candle.canonical_values for candle in self.candles),
            "qualification_digest": self.qualification.semantic_digest,
        })


def exact_decimal_text(value: Decimal) -> str:
    """Canonical input text without arithmetic or ambient-context rounding."""
    if value == 0:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text
