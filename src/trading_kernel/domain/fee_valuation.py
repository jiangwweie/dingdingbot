"""Pure native-fee and deterministic USDT valuation boundaries."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


_MAX_BNB_INDEX_CANDLE_STALENESS_MS = 120_000


class NativeFee(BaseModel):
    """The exact commission asset and amount returned by the venue."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    asset: Literal["USDT", "BNB"]
    amount: Decimal

    @field_validator("amount")
    @classmethod
    def _require_finite_nonnegative_amount(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value < 0:
            raise ValueError("native fee amount must be finite and non-negative")
        return value


class FeeValuationEvidence(BaseModel):
    """Immutable price evidence for one native-fee USDT valuation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    method: Literal[
        "native_usdt",
        "binance_usdm_bnbusdt_index_1m_previous_close",
    ]
    rate_usdt_per_asset: Decimal
    price_pair: str | None
    candle_open_time_ms: int | None
    candle_close_time_ms: int | None
    valued_at_ms: int

    @field_validator("rate_usdt_per_asset")
    @classmethod
    def _require_finite_positive_rate(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0:
            raise ValueError("fee valuation rate must be finite and positive")
        return value

    @model_validator(mode="after")
    def _validate_evidence_shape(self) -> "FeeValuationEvidence":
        if self.valued_at_ms <= 0:
            raise ValueError("fee valuation time must be positive")
        candle_fields = (
            self.price_pair,
            self.candle_open_time_ms,
            self.candle_close_time_ms,
        )
        if self.method == "native_usdt":
            if self.rate_usdt_per_asset != Decimal("1"):
                raise ValueError("native USDT valuation rate must equal one")
            if any(value is not None for value in candle_fields):
                raise ValueError("native USDT valuation forbids price candle evidence")
            return self
        if self.price_pair != "BNBUSDT":
            raise ValueError("BNB valuation requires the BNBUSDT price pair")
        if self.candle_open_time_ms is None or self.candle_close_time_ms is None:
            raise ValueError("BNB valuation requires a completed index candle")
        if self.candle_open_time_ms <= 0 or self.candle_close_time_ms <= self.candle_open_time_ms:
            raise ValueError("BNB valuation candle window is invalid")
        if self.candle_close_time_ms > self.valued_at_ms:
            raise ValueError("BNB valuation candle closes after the valued trade")
        if self.valued_at_ms - self.candle_close_time_ms > _MAX_BNB_INDEX_CANDLE_STALENESS_MS:
            raise ValueError("BNB valuation candle is stale")
        return self


class ValuedFee(BaseModel):
    """One native commission plus its reproducible USDT equivalent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    native: NativeFee
    usdt_value: Decimal
    evidence: FeeValuationEvidence

    @field_validator("usdt_value")
    @classmethod
    def _require_finite_nonnegative_value(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value < 0:
            raise ValueError("valued fee must be finite and non-negative")
        return value

    @model_validator(mode="after")
    def _validate_native_asset_and_value(self) -> "ValuedFee":
        required_method = (
            "native_usdt"
            if self.native.asset == "USDT"
            else "binance_usdm_bnbusdt_index_1m_previous_close"
        )
        if self.evidence.method != required_method:
            raise ValueError("native fee asset and valuation method differ")
        expected_value = self.native.amount * self.evidence.rate_usdt_per_asset
        if self.usdt_value != expected_value:
            raise ValueError("valued fee does not equal native amount times evidence rate")
        return self


def value_native_fee(
    *,
    native_fee: NativeFee,
    valuation_evidence: FeeValuationEvidence,
) -> ValuedFee:
    """Construct one validated valuation without reading a clock or venue."""

    return ValuedFee(
        native=native_fee,
        usdt_value=native_fee.amount * valuation_evidence.rate_usdt_per_asset,
        evidence=valuation_evidence,
    )
