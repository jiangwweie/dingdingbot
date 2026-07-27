"""Deterministic 4h regime and 1h relative-strength universe projection."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from hashlib import sha256
import json

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.domain.market import ClosedCandle
from src.trading_kernel.domain.strategy_universe import StrategyUniverseVersion


class RSRProjectionMember(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_instrument_id: str
    return_24h: Decimal
    return_72h: Decimal
    relative_strength_24h: Decimal
    relative_strength_72h: Decimal
    volume_ratio_24h: Decimal
    trend_eligible: bool
    eligible: bool
    rank: int | None

    @field_validator(
        "return_24h",
        "return_72h",
        "relative_strength_24h",
        "relative_strength_72h",
        "volume_ratio_24h",
    )
    @classmethod
    def _freeze_storage_precision(cls, value: Decimal) -> Decimal:
        with localcontext() as context:
            context.prec = 60
            return value.quantize(
                Decimal("0.000000000000000001"),
                rounding=ROUND_HALF_EVEN,
            )

    @model_validator(mode="after")
    def _validate_rank(self) -> "RSRProjectionMember":
        if self.rank is not None and (not self.eligible or self.rank <= 0):
            raise ValueError("only eligible RSR members may have a positive rank")
        return self


class RSRUniverseProjection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    projection_run_id: str
    event_spec_id: str
    universe_version_id: str
    universe_digest: str
    as_of_close_time_ms: int
    regime_eligible: bool
    reference_digest: str
    members: tuple[RSRProjectionMember, ...]
    input_digest: str

    @property
    def top_two(self) -> tuple[RSRProjectionMember, ...]:
        return tuple(
            sorted(
                (member for member in self.members if member.rank is not None),
                key=lambda member: int(member.rank or 0),
            )[:2]
        )


def compute_reference_regime(
    reference_candles_4h: Mapping[str, Sequence[ClosedCandle]],
) -> bool:
    if len(reference_candles_4h) != 2:
        raise ValueError("reference regime requires exactly two members")
    eligibility: list[bool] = []
    close_times: set[int] = set()
    for candles in reference_candles_4h.values():
        if len(candles) < 200:
            raise ValueError("reference regime requires 200 closed 4h candles")
        window = tuple(candles[-200:])
        _validate_closed_series(window)
        closes = tuple(candle.close for candle in window)
        ema50 = _ema(closes, 50)[-1]
        ema200 = _ema(closes, 200)[-1]
        eligibility.append(closes[-1] > ema50 > ema200)
        close_times.add(window[-1].close_time_ms)
    if len(close_times) != 1:
        raise ValueError("reference regime close times differ")
    return all(eligibility)


def build_rsr_projection(
    *,
    universe: StrategyUniverseVersion,
    candidate_candles_1h: Mapping[str, Sequence[ClosedCandle]],
    reference_candles_1h: Mapping[str, Sequence[ClosedCandle]],
    reference_candles_4h: Mapping[str, Sequence[ClosedCandle]],
) -> RSRUniverseProjection:
    expected_candidates = {
        member.exchange_instrument_id for member in universe.candidate_members
    }
    expected_references = {
        member.exchange_instrument_id for member in universe.reference_members
    }
    if set(candidate_candles_1h) != expected_candidates:
        raise ValueError("RSR candidate inputs differ from Universe membership")
    if (
        set(reference_candles_1h) != expected_references
        or set(reference_candles_4h) != expected_references
        or len(expected_references) != 2
    ):
        raise ValueError("RSR reference inputs differ from Universe membership")

    all_1h = {**candidate_candles_1h, **reference_candles_1h}
    close_times: set[int] = set()
    normalized: dict[str, tuple[ClosedCandle, ...]] = {}
    for instrument_id, candles in all_1h.items():
        if len(candles) < 744:
            raise ValueError("RSR projection requires 744 closed 1h candles")
        window = tuple(candles[-744:])
        _validate_closed_series(window)
        if any(candle.quote_volume is None for candle in window[-48:]):
            raise ValueError("RSR projection requires quote volume")
        close_times.add(window[-1].close_time_ms)
        normalized[instrument_id] = window
    if len(close_times) != 1:
        raise ValueError("RSR projection close times differ")
    as_of_close_time_ms = close_times.pop()

    reference_returns_24h = [
        _return(normalized[instrument_id], 24)
        for instrument_id in sorted(expected_references)
    ]
    reference_returns_72h = [
        _return(normalized[instrument_id], 72)
        for instrument_id in sorted(expected_references)
    ]
    reference_24h = sum(reference_returns_24h, Decimal("0")) / Decimal("2")
    reference_72h = sum(reference_returns_72h, Decimal("0")) / Decimal("2")
    raw_members: list[RSRProjectionMember] = []
    for member in universe.candidate_members:
        candles = normalized[member.exchange_instrument_id]
        return_24h = _return(candles, 24)
        return_72h = _return(candles, 72)
        rs24 = return_24h - reference_24h
        rs72 = return_72h - reference_72h
        recent_volume = sum(
            (candle.quote_volume or Decimal("0") for candle in candles[-24:]),
            Decimal("0"),
        )
        prior_volume = sum(
            (
                candle.quote_volume or Decimal("0")
                for candle in candles[-48:-24]
            ),
            Decimal("0"),
        )
        if prior_volume <= 0:
            raise ValueError("RSR prior quote-volume window must be positive")
        volume_ratio = recent_volume / prior_volume
        closes = tuple(candle.close for candle in candles)
        ema20 = _ema(closes, 20)[-1]
        ema50 = _ema(closes, 50)[-1]
        trend_eligible = closes[-1] > ema20 > ema50
        eligible = (
            trend_eligible
            and rs24 > 0
            and rs72 > 0
            and volume_ratio >= Decimal("1")
        )
        raw_members.append(
            RSRProjectionMember(
                exchange_instrument_id=member.exchange_instrument_id,
                return_24h=return_24h,
                return_72h=return_72h,
                relative_strength_24h=rs24,
                relative_strength_72h=rs72,
                volume_ratio_24h=volume_ratio,
                trend_eligible=trend_eligible,
                eligible=eligible,
                rank=None,
            )
        )
    ranked_ids = [
        member.exchange_instrument_id
        for member in sorted(
            (member for member in raw_members if member.eligible),
            key=lambda member: (
                -member.relative_strength_72h,
                -member.relative_strength_24h,
                -member.volume_ratio_24h,
                member.exchange_instrument_id,
            ),
        )
    ]
    rank_by_id = {
        instrument_id: rank
        for rank, instrument_id in enumerate(ranked_ids, start=1)
    }
    members = tuple(
        member.model_copy(
            update={"rank": rank_by_id.get(member.exchange_instrument_id)}
        )
        for member in sorted(
            raw_members,
            key=lambda member: member.exchange_instrument_id,
        )
    )
    regime_eligible = compute_reference_regime(reference_candles_4h)
    reference_digest = _series_digest(
        {
            instrument_id: normalized[instrument_id]
            for instrument_id in sorted(expected_references)
        }
    )
    input_digest = _series_digest(normalized)
    identity = _digest(
        {
            "event_spec_id": universe.event_spec_id,
            "universe_version_id": universe.universe_version_id,
            "universe_digest": universe.semantic_digest(),
            "as_of_close_time_ms": as_of_close_time_ms,
            "reference_digest": reference_digest,
            "input_digest": input_digest,
        }
    )
    return RSRUniverseProjection(
        projection_run_id=f"projection:{identity.removeprefix('sha256:')}",
        event_spec_id=universe.event_spec_id,
        universe_version_id=universe.universe_version_id,
        universe_digest=universe.semantic_digest(),
        as_of_close_time_ms=as_of_close_time_ms,
        regime_eligible=regime_eligible,
        reference_digest=reference_digest,
        members=members,
        input_digest=input_digest,
    )


def ema(values: Sequence[Decimal], period: int) -> tuple[Decimal, ...]:
    return _ema(values, period)


def linear_quantile(values: Sequence[Decimal], fraction: Decimal) -> Decimal:
    if not values or not Decimal("0") <= fraction <= Decimal("1"):
        raise ValueError("quantile requires values and a fraction in [0, 1]")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = Decimal(len(ordered) - 1) * fraction
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - Decimal(lower)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def sample_stddev(values: Sequence[Decimal]) -> Decimal:
    if len(values) < 2:
        raise ValueError("sample standard deviation requires two values")
    mean = sum(values, Decimal("0")) / Decimal(len(values))
    variance = sum(
        ((value - mean) ** 2 for value in values),
        Decimal("0"),
    ) / Decimal(len(values) - 1)
    return variance.sqrt()


def median(values: Sequence[Decimal]) -> Decimal:
    return linear_quantile(values, Decimal("0.5"))


def _ema(values: Sequence[Decimal], period: int) -> tuple[Decimal, ...]:
    if period <= 0 or len(values) < period:
        raise ValueError("EMA requires a positive complete period")
    seed = sum(values[:period], Decimal("0")) / Decimal(period)
    multiplier = Decimal("2") / Decimal(period + 1)
    output = [seed]
    for value in values[period:]:
        output.append((value - output[-1]) * multiplier + output[-1])
    return tuple(output)


def _return(candles: Sequence[ClosedCandle], bars: int) -> Decimal:
    base = candles[-(bars + 1)].close
    return candles[-1].close / base - Decimal("1")


def _validate_closed_series(candles: Sequence[ClosedCandle]) -> None:
    if not candles:
        raise ValueError("closed-candle series cannot be empty")
    open_times = [candle.open_time_ms for candle in candles]
    close_times = [candle.close_time_ms for candle in candles]
    if open_times != sorted(open_times) or len(open_times) != len(set(open_times)):
        raise ValueError("closed-candle series must be ordered and unique")
    durations = {
        candle.close_time_ms - candle.open_time_ms for candle in candles
    }
    if len(durations) != 1:
        raise ValueError("closed-candle series durations differ")
    duration = durations.pop()
    if any(
        current - previous != duration
        for previous, current in zip(open_times, open_times[1:], strict=False)
    ):
        raise ValueError("closed-candle series contains a gap")
    if close_times != sorted(close_times):
        raise ValueError("closed-candle close times must be ordered")


def _series_digest(
    by_instrument: Mapping[str, Sequence[ClosedCandle]],
) -> str:
    return _digest(
        {
            instrument_id: [
                candle.model_dump(mode="json") for candle in candles
            ]
            for instrument_id, candles in sorted(by_instrument.items())
        }
    )


def _digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"
