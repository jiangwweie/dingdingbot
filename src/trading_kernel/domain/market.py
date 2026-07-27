"""Immutable closed-market inputs shared by live and replay detectors."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


Timeframe = Literal["15m", "1h", "4h"]


class ClosedCandle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    open_time_ms: int
    close_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    quote_volume: Decimal | None = None

    @model_validator(mode="after")
    def _validate_closed_candle(self) -> "ClosedCandle":
        if self.open_time_ms <= 0 or self.close_time_ms <= self.open_time_ms:
            raise ValueError("closed candle requires a positive time window")
        if min(self.open, self.high, self.low, self.close) <= Decimal("0"):
            raise ValueError("OHLC values must be positive")
        if self.volume < Decimal("0"):
            raise ValueError("candle volume must be nonnegative")
        if self.quote_volume is not None and self.quote_volume < Decimal("0"):
            raise ValueError("candle quote volume must be nonnegative")
        if self.high < max(self.open, self.close) or self.low > min(
            self.open,
            self.close,
        ):
            raise ValueError("candle high/low does not contain open and close")
        return self


class ComparativeStrengthMember(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_instrument_id: str
    return_pct: Decimal
    rank: int

    @field_validator("exchange_instrument_id", mode="before")
    @classmethod
    def _require_instrument_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("comparative member instrument must be non-blank")
        return normalized

    @field_validator("rank")
    @classmethod
    def _require_positive_rank(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("comparative member rank must be positive")
        return value


class ComparativeStrengthSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_group_id: str
    timeframe: Timeframe
    lookback_bars: int
    trigger_candle_close_time_ms: int
    members: tuple[ComparativeStrengthMember, ...]
    observed_at_ms: int
    valid_until_ms: int
    source_ref: str

    @field_validator("strategy_group_id", "source_ref", mode="before")
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("comparative snapshot identity must be non-blank")
        return normalized

    @model_validator(mode="after")
    def _validate_comparative_snapshot(self) -> "ComparativeStrengthSnapshot":
        if self.lookback_bars <= 0 or self.trigger_candle_close_time_ms <= 0:
            raise ValueError("comparative lookback and trigger must be positive")
        if self.observed_at_ms <= 0 or self.valid_until_ms < self.observed_at_ms:
            raise ValueError("comparative observation window is invalid")
        if not self.members:
            raise ValueError("comparative snapshot requires members")
        instruments = [item.exchange_instrument_id for item in self.members]
        ranks = [item.rank for item in self.members]
        if len(instruments) != len(set(instruments)):
            raise ValueError("comparative member instruments must be unique")
        if len(ranks) != len(set(ranks)) or sorted(ranks) != list(
            range(1, len(ranks) + 1)
        ):
            raise ValueError("comparative ranks must be unique and contiguous")
        return self

    def member(self, exchange_instrument_id: str) -> ComparativeStrengthMember:
        for item in self.members:
            if item.exchange_instrument_id == exchange_instrument_id:
                return item
        raise KeyError(exchange_instrument_id)


class RSRVCBContext(BaseModel):
    """Immutable ranked/armed/trigger lineage attached to one market snapshot."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    universe_version_id: str
    universe_digest: str
    projection_run_id: str
    armed_structure_id: str
    rsr_rank: int
    relative_strength_24h: Decimal
    relative_strength_72h: Decimal
    rsr_volume_ratio_24h: Decimal
    regime_eligible: bool
    compression_ratio: Decimal
    breakout_boundary: Decimal
    armed_at_ms: int
    trigger_volume_ratio: Decimal
    initial_stop_reference: Decimal

    @field_validator(
        "universe_version_id",
        "universe_digest",
        "projection_run_id",
        "armed_structure_id",
        mode="before",
    )
    @classmethod
    def _require_context_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("RSR/VCB context identity must be non-blank")
        return normalized

    @model_validator(mode="after")
    def _validate_context(self) -> "RSRVCBContext":
        if self.rsr_rank not in {1, 2}:
            raise ValueError("RSR/VCB context rank must be one or two")
        if (
            self.armed_at_ms <= 0
            or self.relative_strength_24h <= 0
            or self.relative_strength_72h <= 0
            or self.rsr_volume_ratio_24h < Decimal("1")
            or self.compression_ratio < 0
            or self.breakout_boundary <= 0
            or self.trigger_volume_ratio < Decimal("1.8")
            or self.initial_stop_reference <= 0
        ):
            raise ValueError("RSR/VCB context contains invalid trigger values")
        if not self.regime_eligible:
            raise ValueError("RSR/VCB context requires an eligible regime")
        return self


class MarketSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_instrument_id: str
    trigger_candle_close_time_ms: int
    candles_15m: tuple[ClosedCandle, ...] = ()
    candles_1h: tuple[ClosedCandle, ...] = ()
    candles_4h: tuple[ClosedCandle, ...] = ()
    comparative_strength: ComparativeStrengthSnapshot | None = None
    rsr_vcb: RSRVCBContext | None = None

    @field_validator("exchange_instrument_id", mode="before")
    @classmethod
    def _require_instrument_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("market snapshot instrument must be non-blank")
        return normalized

    @model_validator(mode="after")
    def _validate_market_snapshot(self) -> "MarketSnapshot":
        if self.trigger_candle_close_time_ms <= 0:
            raise ValueError("market snapshot trigger must be positive")
        for candles in (self.candles_15m, self.candles_1h, self.candles_4h):
            open_times = [item.open_time_ms for item in candles]
            close_times = [item.close_time_ms for item in candles]
            if open_times != sorted(open_times) or len(open_times) != len(
                set(open_times)
            ):
                raise ValueError("market candles must be ordered and unique")
            if any(
                close_time > self.trigger_candle_close_time_ms
                for close_time in close_times
            ):
                raise ValueError("market snapshot cannot contain open or future candles")
        return self

    def candles(self, timeframe: Timeframe) -> tuple[ClosedCandle, ...]:
        if timeframe == "15m":
            return self.candles_15m
        if timeframe == "1h":
            return self.candles_1h
        return self.candles_4h
