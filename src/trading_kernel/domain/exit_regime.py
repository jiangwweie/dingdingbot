"""Exact closed BTC four-hour SMA50 eligibility, independent of Owner bias."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.market import ClosedCandle

FOUR_HOURS_MS = 14_400_000
BTC_USDM = "binance-usdm:BTCUSDT:perpetual"


class BtcMa50Snapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    venue_id: Literal["binance-usdm"] = "binance-usdm"
    exchange_instrument_id: Literal["binance-usdm:BTCUSDT:perpetual"] = (
        "binance-usdm:BTCUSDT:perpetual"
    )
    latest_close_time_ms: int
    latest_close: Decimal
    sma50: Decimal
    window_digest: str
    observed_at_ms: int
    valid_until_ms: int

    @model_validator(mode="after")
    def _validate_snapshot(self) -> BtcMa50Snapshot:
        if self.latest_close_time_ms <= 0 or self.latest_close_time_ms % FOUR_HOURS_MS:
            raise ValueError("regime must use native UTC four-hour boundary")
        if (
            not self.latest_close_time_ms <= self.observed_at_ms < self.valid_until_ms
            or self.valid_until_ms != self.latest_close_time_ms + FOUR_HOURS_MS
        ):
            raise ValueError("regime has stale or future latest close")
        if any(not v.is_finite() or v <= 0 for v in (self.latest_close, self.sma50)):
            raise ValueError("regime prices must be finite and positive")
        if (
            not self.window_digest.startswith("sha256:")
            or len(self.window_digest) != 71
        ):
            raise ValueError("regime requires window digest")
        return self

    @classmethod
    def create(
        cls, *, candles: tuple[ClosedCandle, ...], observed_at_ms: int
    ) -> BtcMa50Snapshot:
        if len(candles) != 50:
            raise ValueError("regime requires exactly 50 closed bars")
        latest = observed_at_ms // FOUR_HOURS_MS * FOUR_HOURS_MS
        for index, bar in enumerate(candles):
            expected_close = latest - (49 - index) * FOUR_HOURS_MS
            if (
                bar.close_time_ms != expected_close
                or bar.open_time_ms != expected_close - FOUR_HOURS_MS
            ):
                raise ValueError(
                    "regime window has missing duplicate future or unclosed bars"
                )
        return cls(
            latest_close_time_ms=latest,
            latest_close=candles[-1].close,
            sma50=sum((b.close for b in candles), Decimal(0)) / 50,
            window_digest=canonical_digest(
                [b.model_dump(mode="json") for b in candles]
            ),
            observed_at_ms=observed_at_ms,
            valid_until_ms=latest + FOUR_HOURS_MS,
        )

    def allowed_at(self, now_ms: int) -> bool:
        return (
            self.observed_at_ms <= now_ms < self.valid_until_ms
            and self.latest_close > self.sma50
        )


class RegimeAdmissionProof(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    configuration_id: str
    configuration_revision: int
    event_spec_id: str
    enabled: bool
    snapshot: BtcMa50Snapshot | None
