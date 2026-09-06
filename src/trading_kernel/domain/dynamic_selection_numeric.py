"""Pure numeric contracts for Generic Dynamic Selection V1.

These functions evaluate only frozen selector features.  They own neither
market I/O nor SelectionSnapshot persistence, and they never make a trading
decision by themselves.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.domain.instrument_selection import (
    CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS,
)

DYNAMIC_SELECTION_DECIMAL_CONTEXT = Context(prec=38, rounding=ROUND_HALF_EVEN)
_EXPECTED_CANDIDATES = frozenset(CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS)


class DynamicSelectionNumericError(ValueError):
    """Frozen selector input cannot produce a deterministic numeric result."""


class DynamicSelectionFeatureRank(BaseModel):
    """One deterministic, descending feature rank in the fixed Candidate24."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_instrument_id: str
    feature_value: Decimal
    rank: int

    @field_validator("exchange_instrument_id", mode="before")
    @classmethod
    def _require_instrument(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if normalized not in _EXPECTED_CANDIDATES:
            raise DynamicSelectionNumericError("feature rank instrument is not Candidate24")
        return normalized

    @model_validator(mode="after")
    def _validate_rank(self) -> DynamicSelectionFeatureRank:
        if self.rank < 1 or self.rank > len(_EXPECTED_CANDIDATES):
            raise DynamicSelectionNumericError("feature rank is outside Candidate24")
        if not self.feature_value.is_finite():
            raise DynamicSelectionNumericError("feature value must be finite")
        return self


def absolute_directional_efficiency_24h(
    closes: Sequence[Decimal],
) -> Decimal:
    """Return the frozen CPM V1 absolute directional efficiency."""

    values = _positive_decimal_window(closes, expected_count=25, label="CPM closes")
    with localcontext(DYNAMIC_SELECTION_DECIMAL_CONTEXT):
        path = sum(
            (abs(values[index] - values[index - 1]) for index in range(1, 25)),
            Decimal(0),
        )
        if path <= 0:
            raise DynamicSelectionNumericError("CPM path is zero")
        return abs(values[-1] - values[0]) / path


def persistent_leadership_score_6h(ranks: Sequence[int]) -> Decimal:
    """Return the frozen MPG V1 all-24 six-boundary leadership score."""

    values = tuple(ranks)
    if len(values) != 6 or any(rank < 1 or rank > 24 for rank in values):
        raise DynamicSelectionNumericError("MPG ranks require six values within 1..24")
    with localcontext(DYNAMIC_SELECTION_DECIMAL_CONTEXT):
        return sum(
            (Decimal(25 - rank) / Decimal(24) for rank in values),
            Decimal(0),
        ) / Decimal(6)


def positive_impulse_recency_12h(returns: Sequence[Decimal]) -> Decimal:
    """Return the frozen MI V0 positive-return time-centre score."""

    values = tuple(returns)
    if len(values) != 12 or any(not value.is_finite() for value in values):
        raise DynamicSelectionNumericError("MI returns require twelve finite values")
    with localcontext(DYNAMIC_SELECTION_DECIMAL_CONTEXT):
        positive = tuple(max(value, Decimal(0)) for value in values)
        total = sum(positive, Decimal(0))
        if total == 0:
            return Decimal(0)
        return sum(
            (
                (Decimal(index) / Decimal(11)) * value
                for index, value in enumerate(positive)
            ),
            Decimal(0),
        ) / total


def rank_dynamic_selection_features(
    values: Mapping[str, Decimal],
) -> tuple[DynamicSelectionFeatureRank, ...]:
    """Rank a complete Candidate24 feature surface, descending then ID ascending."""

    _require_exact_candidate_values(values)
    ordered = tuple(
        sorted(values.items(), key=lambda item: (-item[1], item[0]))
    )
    return tuple(
        DynamicSelectionFeatureRank(
            exchange_instrument_id=instrument_id,
            feature_value=feature_value,
            rank=rank,
        )
        for rank, (instrument_id, feature_value) in enumerate(ordered, start=1)
    )


def rank_brf2_residual_extension_v0_decimal(
    closes_by_instrument: Mapping[str, Sequence[Decimal]],
) -> tuple[DynamicSelectionFeatureRank, ...]:
    """Rank Candidate24 by the frozen BRF2 residual-extension formula in Decimal.

    The function deliberately has no tolerance or epsilon branch.  A zero
    market variance or residual variance is an undefined selector result and
    must fail the whole Selection attempt upstream.
    """

    if set(closes_by_instrument) != _EXPECTED_CANDIDATES:
        raise DynamicSelectionNumericError("BRF2 requires exact 24 Candidate24 members")
    closes = {
        instrument_id: _positive_decimal_window(
            values,
            expected_count=73,
            label=f"BRF2 closes for {instrument_id}",
        )
        for instrument_id, values in closes_by_instrument.items()
    }
    with localcontext(DYNAMIC_SELECTION_DECIMAL_CONTEXT):
        returns = {
            instrument_id: tuple(
                (values[index] / values[index - 1]).ln()
                for index in range(1, 73)
            )
            for instrument_id, values in closes.items()
        }
        market = tuple(
            sum(
                (returns[instrument_id][index] for instrument_id in _EXPECTED_CANDIDATES),
                Decimal(0),
            )
            / Decimal(24)
            for index in range(72)
        )
        market_mean = sum(market, Decimal(0)) / Decimal(72)
        centered_market = tuple(value - market_mean for value in market)
        market_sum_squares = sum(
            (value * value for value in centered_market),
            Decimal(0),
        )
        if market_sum_squares <= 0:
            raise DynamicSelectionNumericError("BRF2 market variance is zero")

        scores: dict[str, Decimal] = {}
        for instrument_id in _EXPECTED_CANDIDATES:
            candidate_returns = returns[instrument_id]
            candidate_mean = sum(candidate_returns, Decimal(0)) / Decimal(72)
            beta = sum(
                (
                    (candidate_returns[index] - candidate_mean)
                    * centered_market[index]
                    for index in range(72)
                ),
                Decimal(0),
            ) / market_sum_squares
            alpha = candidate_mean - beta * market_mean
            residuals = tuple(
                candidate_returns[index] - alpha - beta * market[index]
                for index in range(72)
            )
            recent = residuals[-24:]
            residual_sum_squares = sum(
                (value * value for value in recent),
                Decimal(0),
            )
            if residual_sum_squares <= 0:
                raise DynamicSelectionNumericError(
                    f"BRF2 residual variance is zero: {instrument_id}"
                )
            scores[instrument_id] = sum(recent, Decimal(0)) / residual_sum_squares.sqrt()
        return rank_dynamic_selection_features(scores)


def _positive_decimal_window(
    values: Sequence[Decimal],
    *,
    expected_count: int,
    label: str,
) -> tuple[Decimal, ...]:
    normalized = tuple(values)
    if len(normalized) != expected_count:
        raise DynamicSelectionNumericError(
            f"{label} requires exactly {expected_count} values"
        )
    if any(not value.is_finite() or value <= 0 for value in normalized):
        raise DynamicSelectionNumericError(f"{label} requires finite positive values")
    return normalized


def _require_exact_candidate_values(values: Mapping[str, Decimal]) -> None:
    if set(values) != _EXPECTED_CANDIDATES:
        raise DynamicSelectionNumericError("feature ranking requires exact 24 Candidate24 members")
    if any(not value.is_finite() for value in values.values()):
        raise DynamicSelectionNumericError("feature ranking requires finite values")
