"""Closed BTC 4h SMA50 qualification; independent of Owner direction budgets."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.market import ClosedCandle

FOUR_HOURS_MS = 14_400_000
BTC_REGIME_INSTRUMENT = "binance-usdm:BTCUSDT:perpetual"
REGIME_EVENTS = (
    "event_spec:CPM-RO-001:CPM-LONG:v3",
    "event_spec:MI-001:MI-LONG:v3",
    "event_spec:MPG-001:MPG-LONG:v3",
)


class BtcMa50Snapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_instrument_id: Literal["binance-usdm:BTCUSDT:perpetual"] = (
        "binance-usdm:BTCUSDT:perpetual"
    )
    timeframe: Literal["4h"] = "4h"
    candles: tuple[ClosedCandle, ...]
    observed_at_ms: int

    @model_validator(mode="after")
    def _closed_continuous_window(self) -> BtcMa50Snapshot:
        if len(self.candles) != 50:
            raise ValueError("BTC SMA50 requires exactly fifty closed candles")
        previous = None
        for bar in self.candles:
            if (
                bar.open_time_ms % FOUR_HOURS_MS
                or bar.close_time_ms != bar.open_time_ms + FOUR_HOURS_MS
                or (previous is not None and bar.open_time_ms != previous)
                or bar.close_time_ms > self.observed_at_ms
                or not bar.close.is_finite()
            ):
                raise ValueError("BTC SMA50 requires contiguous aligned closed bars")
            previous = bar.close_time_ms
        if self.latest_close_ms != self.observed_at_ms // FOUR_HOURS_MS * FOUR_HOURS_MS:
            raise ValueError("BTC SMA50 window does not end at latest closed period")
        return self

    @property
    def latest_close_ms(self) -> int:
        return self.candles[-1].close_time_ms

    @property
    def sma50(self) -> Decimal:
        return sum((bar.close for bar in self.candles), Decimal(0)) / Decimal(50)

    def semantic_hash(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))


def evaluate_btc_ma50(snapshot: BtcMa50Snapshot | None, *, now_ms: int) -> str:
    if (
        snapshot is None
        or snapshot.observed_at_ms > now_ms
        or snapshot.latest_close_ms != now_ms // FOUR_HOURS_MS * FOUR_HOURS_MS
    ):
        return "btc4h_facts_unavailable"
    return (
        "allowed"
        if snapshot.candles[-1].close > snapshot.sma50
        else "btc4h_not_above_ma50"
    )


class EntryRegimeControl(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_spec_id: str
    revision: int
    enabled: bool
    rule_id: Literal["btc4h_ma50_long_v1"] = "btc4h_ma50_long_v1"
    authorization_id: str | None = None
    created_at_ms: int

    @model_validator(mode="after")
    def _scope(self) -> EntryRegimeControl:
        if (
            self.event_spec_id not in REGIME_EVENTS
            or self.revision < 1
            or self.created_at_ms < 1
        ):
            raise ValueError("invalid BTC MA50 control identity")
        if self.enabled and self.authorization_id is None:
            raise ValueError("enabled BTC MA50 control requires Owner authorization")
        return self


class EntryRegimeEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_spec_id: str
    control: EntryRegimeControl | None
    snapshot: BtcMa50Snapshot | None
    result: str
    evaluated_at_ms: int

    @model_validator(mode="after")
    def _verify(self) -> EntryRegimeEvidence:
        expected = (
            "entry_regime_control_missing"
            if self.control is None
            else evaluate_btc_ma50(self.snapshot, now_ms=self.evaluated_at_ms)
            if self.control.enabled
            else "disabled"
        )
        if self.event_spec_id not in REGIME_EVENTS or self.result != expected:
            raise ValueError("entry regime evidence differs from source facts")
        if (
            self.control is not None
            and self.control.event_spec_id != self.event_spec_id
        ):
            raise ValueError("entry regime evidence scope mismatch")
        return self

    @property
    def allowed(self) -> bool:
        return self.result in {"disabled", "allowed"}
