"""Pure VCB armed structure, closed-15m trigger, and Event detector."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from hashlib import sha256
import json

from pydantic import BaseModel, ConfigDict, model_validator

from src.trading_kernel.domain.detector import (
    DetectorResult,
    StrategyDetector,
    computed_result,
    fact_snapshot,
    invalid_result,
    validate_snapshot_scope,
)
from src.trading_kernel.domain.market import ClosedCandle, MarketSnapshot
from src.trading_kernel.domain.strategy_registry import RegisteredStrategyContract
from src.trading_kernel.domain.universe_projection import (
    RSRProjectionMember,
    RSRUniverseProjection,
    ema,
    linear_quantile,
    median,
    sample_stddev,
)


class VCBArmedStructure(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    armed_structure_id: str
    event_spec_id: str
    universe_version_id: str
    universe_digest: str
    projection_run_id: str
    exchange_instrument_id: str
    rsr_rank: int
    relative_strength_24h: Decimal
    relative_strength_72h: Decimal
    rsr_volume_ratio_24h: Decimal
    compression_ratio: Decimal
    breakout_boundary: Decimal
    armed_at_ms: int
    expires_at_ms: int
    input_digest: str

    @model_validator(mode="after")
    def _validate_armed(self) -> "VCBArmedStructure":
        if (
            self.rsr_rank not in {1, 2}
            or self.compression_ratio < 0
            or self.compression_ratio > Decimal("0.90")
            or self.breakout_boundary <= 0
            or self.armed_at_ms <= 0
            or self.expires_at_ms <= self.armed_at_ms
        ):
            raise ValueError("VCB armed structure values are invalid")
        return self


class RSRVCBTrigger(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    armed_structure: VCBArmedStructure
    trigger_close_time_ms: int
    trigger_close: Decimal
    trigger_volume_ratio: Decimal
    initial_stop_reference: Decimal

    @model_validator(mode="after")
    def _validate_trigger(self) -> "RSRVCBTrigger":
        if (
            self.trigger_close_time_ms <= self.armed_structure.armed_at_ms
            or self.trigger_volume_ratio < Decimal("1.8")
            or not Decimal("0")
            < self.initial_stop_reference
            < self.trigger_close
        ):
            raise ValueError("RSR/VCB trigger values are invalid")
        return self


class RSRVCBDetector(StrategyDetector):
    def __init__(self, contract: RegisteredStrategyContract) -> None:
        self._contract = contract
        self.event_spec_id = contract.event_spec_id

    def evaluate(self, snapshot: MarketSnapshot) -> DetectorResult:
        invalid_scope = validate_snapshot_scope(self._contract, snapshot)
        if invalid_scope is not None:
            return invalid_result(self._contract, invalid_scope)
        context = snapshot.rsr_vcb
        if context is None:
            return invalid_result(
                self._contract,
                "rsr_vcb_ranked_projection_required",
            )
        if context.armed_at_ms >= snapshot.trigger_candle_close_time_ms:
            return invalid_result(
                self._contract,
                "rsr_vcb_trigger_not_after_armed",
            )
        facts = (
            fact_snapshot(
                self._contract,
                snapshot,
                fact_name="regime_eligible",
                value=True,
                satisfied=context.regime_eligible,
            ),
            fact_snapshot(
                self._contract,
                snapshot,
                fact_name="rsr_top2_eligible",
                value=True,
                satisfied=context.rsr_rank in {1, 2},
            ),
            fact_snapshot(
                self._contract,
                snapshot,
                fact_name="vcb_armed",
                value=True,
                satisfied=context.compression_ratio <= Decimal("0.90"),
            ),
            fact_snapshot(
                self._contract,
                snapshot,
                fact_name="breakout_trigger_confirmed",
                value=True,
                satisfied=context.trigger_volume_ratio >= Decimal("1.80"),
            ),
            fact_snapshot(
                self._contract,
                snapshot,
                fact_name="breakout_initial_stop_reference",
                value=str(context.initial_stop_reference),
                satisfied=context.initial_stop_reference > 0,
            ),
        )
        return computed_result(
            self._contract,
            snapshot,
            triggered=all(fact.satisfied for fact in facts),
            reason_code="rsr_vcb_full_trigger_confirmed",
            facts=facts,
        )


def build_vcb_armed_structure(
    *,
    projection: RSRUniverseProjection,
    member: RSRProjectionMember,
    candles_1h: Sequence[ClosedCandle],
) -> VCBArmedStructure | None:
    if (
        not projection.regime_eligible
        or not member.eligible
        or member.rank not in {1, 2}
        or len(candles_1h) < 260
    ):
        return None
    candles = tuple(candles_1h[-260:])
    _validate_series(candles)
    if candles[-1].close_time_ms != projection.as_of_close_time_ms:
        raise ValueError("VCB input and projection close times differ")
    widths: list[Decimal] = []
    for index in range(19, len(candles)):
        closes = tuple(
            candle.close for candle in candles[index - 19 : index + 1]
        )
        mid = sum(closes, Decimal("0")) / Decimal("20")
        width = Decimal("4") * sample_stddev(closes) / mid
        widths.append(width)
    if len(widths) != 241:
        raise ValueError("VCB requires 240 shifted widths plus current width")
    threshold = linear_quantile(widths[:-1], Decimal("0.35"))
    if threshold <= 0:
        raise ValueError("VCB width threshold must be positive")
    compression_ratio = widths[-1] / threshold
    closes = tuple(candle.close for candle in candles)
    ema50 = ema(closes, 50)[-1]
    breakout_boundary = max(candle.high for candle in candles[-73:-1])
    if (
        compression_ratio > Decimal("0.90")
        or closes[-1] <= ema50
        or breakout_boundary <= 0
    ):
        return None
    input_digest = _digest(
        [candle.model_dump(mode="json") for candle in candles]
    )
    identity = _digest(
        {
            "projection_run_id": projection.projection_run_id,
            "exchange_instrument_id": member.exchange_instrument_id,
            "breakout_boundary": str(breakout_boundary),
            "input_digest": input_digest,
        }
    )
    return VCBArmedStructure(
        armed_structure_id=f"armed:{identity.removeprefix('sha256:')}",
        event_spec_id=projection.event_spec_id,
        universe_version_id=projection.universe_version_id,
        universe_digest=projection.universe_digest,
        projection_run_id=projection.projection_run_id,
        exchange_instrument_id=member.exchange_instrument_id,
        rsr_rank=int(member.rank),
        relative_strength_24h=member.relative_strength_24h,
        relative_strength_72h=member.relative_strength_72h,
        rsr_volume_ratio_24h=member.volume_ratio_24h,
        compression_ratio=compression_ratio,
        breakout_boundary=breakout_boundary,
        armed_at_ms=projection.as_of_close_time_ms,
        expires_at_ms=projection.as_of_close_time_ms + 3_600_000,
        input_digest=input_digest,
    )


def evaluate_rsr_vcb_trigger(
    *,
    armed: VCBArmedStructure,
    candles_15m: Sequence[ClosedCandle],
    candles_1h: Sequence[ClosedCandle],
) -> RSRVCBTrigger | None:
    if len(candles_15m) < 22 or len(candles_1h) < 20:
        return None
    trigger_window = tuple(candles_15m[-22:])
    hour_window = tuple(candles_1h)
    _validate_series(trigger_window)
    _validate_series(hour_window)
    current = trigger_window[-1]
    previous = trigger_window[-2]
    if (
        current.close_time_ms <= armed.armed_at_ms
        or current.close_time_ms > armed.expires_at_ms
        or previous.close > armed.breakout_boundary
        or current.close <= armed.breakout_boundary
        or current.close <= current.open
    ):
        return None
    prior_quote_volumes = [
        candle.quote_volume
        for candle in trigger_window[-21:-1]
    ]
    if (
        current.quote_volume is None
        or any(value is None for value in prior_quote_volumes)
    ):
        raise ValueError("RSR/VCB trigger requires quote volume")
    baseline = median(
        tuple(
            value
            for value in prior_quote_volumes
            if value is not None
        )
    )
    if baseline <= 0:
        raise ValueError("RSR/VCB trigger volume baseline must be positive")
    trigger_volume_ratio = current.quote_volume / baseline
    if trigger_volume_ratio < Decimal("1.80"):
        return None
    atr = _atr(hour_window, 14)
    structural_stop = armed.breakout_boundary - atr
    floor_stop = min(candle.low for candle in hour_window[-20:])
    initial_stop = max(structural_stop, floor_stop)
    if not Decimal("0") < initial_stop < current.close:
        return None
    return RSRVCBTrigger(
        armed_structure=armed,
        trigger_close_time_ms=current.close_time_ms,
        trigger_close=current.close,
        trigger_volume_ratio=trigger_volume_ratio,
        initial_stop_reference=initial_stop,
    )


def _atr(candles: Sequence[ClosedCandle], period: int) -> Decimal:
    if len(candles) < period + 1:
        raise ValueError("ATR requires one prior close plus its period")
    sample = candles[-(period + 1) :]
    ranges = [
        max(
            current.high - current.low,
            abs(current.high - previous.close),
            abs(current.low - previous.close),
        )
        for previous, current in zip(sample[:-1], sample[1:], strict=True)
    ]
    return sum(ranges, Decimal("0")) / Decimal(period)


def _validate_series(candles: Sequence[ClosedCandle]) -> None:
    open_times = [candle.open_time_ms for candle in candles]
    if open_times != sorted(open_times) or len(open_times) != len(set(open_times)):
        raise ValueError("RSR/VCB candles must be ordered and unique")


def _digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"
