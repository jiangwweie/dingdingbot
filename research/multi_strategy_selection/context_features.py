"""Frozen point-in-time Stage-2 market Context features."""

from dataclasses import dataclass
from decimal import Decimal
from itertools import pairwise
from math import log, sqrt

import numpy as np

HOUR_MS = 3_600_000


class ContextFeatureError(ValueError):
    """One market Context feature cannot be proven point-in-time complete."""


@dataclass(frozen=True, slots=True)
class HourlyClose:
    symbol: str
    close_time_ms: int
    close: Decimal


@dataclass(frozen=True, slots=True)
class MarketContext:
    feature_cutoff_at_ms: int
    cross_sectional_dispersion_24h: Decimal
    avg_cross_asset_corr_24h: Decimal
    market_breadth_24h: Decimal
    market_rv_24h: Decimal
    market_return_24h: Decimal
    valid_candidate_count: int
    valid_pair_count: int
    missing_pair_count: int


def _window(history: tuple[HourlyClose, ...], cutoff_ms: int) -> tuple[HourlyClose, ...]:
    if any(item.close_time_ms > cutoff_ms for item in history):
        raise ContextFeatureError("future hourly close is forbidden")
    selected = tuple(item for item in history if item.close_time_ms <= cutoff_ms)[-25:]
    if len(selected) != 25:
        raise ContextFeatureError("24h feature requires 25 closes")
    expected = tuple(cutoff_ms - offset * HOUR_MS for offset in range(24, -1, -1))
    if tuple(item.close_time_ms for item in selected) != expected:
        raise ContextFeatureError("24h hourly history is not contiguous")
    if any(item.close <= 0 for item in selected):
        raise ContextFeatureError("hourly close must be positive")
    return selected


def compute_market_context(
    histories: dict[str, tuple[HourlyClose, ...]],
    *,
    cutoff_ms: int,
) -> MarketContext:
    if len(histories) != 24:
        raise ContextFeatureError("market Context requires exact 24 candidates")
    windows = {symbol: _window(history, cutoff_ms) for symbol, history in histories.items()}
    simple_returns: list[float] = []
    log_returns: list[list[float]] = []
    for symbol in sorted(windows):
        closes = [float(item.close) for item in windows[symbol]]
        simple_returns.append(closes[-1] / closes[0] - 1.0)
        log_returns.append([log(closes[index] / closes[index - 1]) for index in range(1, 25)])
    matrix = np.asarray(log_returns, dtype=float)
    correlations = np.corrcoef(matrix)
    pair_values = [
        float(correlations[left, right])
        for left in range(24)
        for right in range(left + 1, 24)
        if np.isfinite(correlations[left, right])
    ]
    pair_total = 24 * 23 // 2
    if not pair_values:
        raise ContextFeatureError("cross-asset correlation has no valid pairs")
    rv_values = [sqrt(sum(value * value for value in row)) for row in log_returns]
    hourly_equal_weight = np.mean(matrix, axis=0)
    return MarketContext(
        feature_cutoff_at_ms=cutoff_ms,
        cross_sectional_dispersion_24h=Decimal(str(float(np.std(simple_returns, ddof=0)))),
        avg_cross_asset_corr_24h=Decimal(str(float(np.mean(pair_values)))),
        market_breadth_24h=Decimal(sum(value > 0 for value in simple_returns)) / Decimal(24),
        market_rv_24h=Decimal(str(float(np.median(rv_values)))),
        market_return_24h=Decimal(str(float(np.sum(hourly_equal_weight)))),
        valid_candidate_count=24,
        valid_pair_count=len(pair_values),
        missing_pair_count=pair_total - len(pair_values),
    )


def directional_efficiency_24h(
    history: tuple[HourlyClose, ...],
    *,
    cutoff_ms: int,
) -> Decimal:
    selected = _window(history, cutoff_ms)
    path = sum(
        (
            abs(current.close - previous.close)
            for previous, current in pairwise(selected)
        ),
        Decimal(0),
    )
    if path <= 0:
        raise ContextFeatureError("directional efficiency denominator must be positive")
    return abs(selected[-1].close - selected[0].close) / path
