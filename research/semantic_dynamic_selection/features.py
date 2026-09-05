"""Pure frozen features and ranking for Stage-3 semantic selection."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from math import fsum, sqrt
from typing import Literal

HOUR_MS = 3_600_000
MemberState = Literal["SELECTED", "NEAR_THRESHOLD", "NOT_SELECTED"]


@dataclass(frozen=True, slots=True)
class RankedMember:
    exchange_instrument_id: str
    feature_value: Decimal
    rank: int
    state: MemberState


def signed_trend_efficiency_24h(closes: tuple[Decimal, ...]) -> Decimal:
    if len(closes) != 25 or any(value <= 0 for value in closes):
        raise ValueError("signed trend efficiency requires 25 positive closes")
    path = sum(
        (abs(closes[index] - closes[index - 1]) for index in range(1, 25)),
        Decimal(0),
    )
    if path <= 0:
        raise ValueError("signed trend efficiency path is zero")
    return (closes[-1] - closes[0]) / path


def leader_occupancy_6h(ranks: tuple[int, ...]) -> Decimal:
    if len(ranks) != 6 or any(rank < 1 or rank > 24 for rank in ranks):
        raise ValueError("leader occupancy requires six ranks within the fixed 24")
    return Decimal(sum(rank <= 6 for rank in ranks)) / Decimal(6)


def positive_impulse_recency_12h(returns: tuple[Decimal, ...]) -> Decimal:
    if len(returns) != 12 or any(not value.is_finite() for value in returns):
        raise ValueError("impulse recency requires 12 finite returns")
    positive = tuple(max(value, Decimal(0)) for value in returns)
    total = sum(positive, Decimal(0))
    if total == 0:
        return Decimal(0)
    weights = tuple(Decimal(index) / Decimal(11) for index in range(12))
    return sum(
        (weight * value for weight, value in zip(weights, positive, strict=True)),
        Decimal(0),
    ) / total


def residual_extension_z_24h(
    candidate_returns: tuple[float, ...],
    market_returns: tuple[float, ...],
) -> float:
    if len(candidate_returns) != 72 or len(market_returns) != 72:
        raise ValueError("residual extension requires 72 candidate and market returns")
    mean_candidate = fsum(candidate_returns) / 72
    mean_market = fsum(market_returns) / 72
    centered_market = tuple(value - mean_market for value in market_returns)
    market_ss = fsum(value * value for value in centered_market)
    if market_ss <= 0:
        raise ValueError("residual extension market variance is zero")
    beta = fsum(
        (candidate_returns[index] - mean_candidate) * centered_market[index]
        for index in range(72)
    ) / market_ss
    alpha = mean_candidate - beta * mean_market
    residuals = tuple(
        candidate_returns[index] - alpha - beta * market_returns[index]
        for index in range(72)
    )
    recent = residuals[-24:]
    residual_rv = sqrt(fsum(value * value for value in recent))
    if residual_rv <= 0:
        raise ValueError("residual extension residual variance is zero")
    return fsum(recent) / residual_rv


def rank_feature_values(values: dict[str, Decimal]) -> tuple[RankedMember, ...]:
    if len(values) != 24 or len(values) != len(set(values)):
        raise ValueError("semantic selection requires exact 24 unique Instruments")
    ordered = sorted(values.items(), key=lambda item: (-item[1], item[0]))
    return tuple(
        RankedMember(
            exchange_instrument_id=instrument_id,
            feature_value=value,
            rank=rank,
            state=(
                "SELECTED"
                if rank <= 16
                else "NEAR_THRESHOLD"
                if rank <= 20
                else "NOT_SELECTED"
            ),
        )
        for rank, (instrument_id, value) in enumerate(ordered, start=1)
    )


def active_selection_cutoff(event_close_ms: int, *, cadence_hours: int) -> int:
    if event_close_ms <= 0 or cadence_hours not in {1, 4}:
        raise ValueError("selection cutoff requires positive time and 1h/4h cadence")
    latest_eligible_cutoff = event_close_ms - HOUR_MS
    cadence_ms = cadence_hours * HOUR_MS
    return (latest_eligible_cutoff // cadence_ms) * cadence_ms
