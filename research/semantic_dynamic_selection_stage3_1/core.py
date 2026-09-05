"""Pure frozen Stage-3.1 feature, cohort, capture and hysteresis rules."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

CARDINALITIES = (16, 12, 8)
Cohort = Literal["SELECTED", "EXCLUDED"]


@dataclass(frozen=True, slots=True)
class CaptureMetrics:
    good_event_capture: Decimal | None
    bad_event_rejection: Decimal | None
    opportunity_retention: Decimal


def absolute_directional_efficiency_24h(
    closes: tuple[Decimal, ...],
) -> Decimal:
    if len(closes) != 25 or any(value <= 0 for value in closes):
        raise ValueError("absolute directional efficiency requires 25 positive closes")
    path = sum(
        (abs(closes[index] - closes[index - 1]) for index in range(1, 25)),
        Decimal(0),
    )
    if path <= 0:
        raise ValueError("absolute directional efficiency path is zero")
    return abs(closes[-1] - closes[0]) / path


def persistent_leadership_score_6h(ranks: tuple[int, ...]) -> Decimal:
    if len(ranks) != 6 or any(rank < 1 or rank > 24 for rank in ranks):
        raise ValueError("persistent leadership requires six all-24 ranks")
    strengths = tuple(Decimal(25 - rank) / Decimal(24) for rank in ranks)
    return sum(strengths, Decimal(0)) / Decimal(6)


def cohort_for_rank(rank: int, cardinality: int) -> Cohort:
    if cardinality not in CARDINALITIES:
        raise ValueError("only Top16, Top12 and Top8 are authorized")
    if rank < 1 or rank > 24:
        raise ValueError("selection rank must be within the fixed 24")
    return "SELECTED" if rank <= cardinality else "EXCLUDED"


def capture_metrics(
    *,
    all_labels: tuple[str, ...],
    selected_labels: tuple[str, ...],
    excluded_labels: tuple[str, ...],
) -> CaptureMetrics:
    if len(selected_labels) + len(excluded_labels) != len(all_labels):
        raise ValueError("selected and excluded labels must partition all Events")
    all_tp = sum(label == "TP" for label in all_labels)
    all_stop = sum(label == "STOP" for label in all_labels)
    selected_tp = sum(label == "TP" for label in selected_labels)
    excluded_stop = sum(label == "STOP" for label in excluded_labels)
    return CaptureMetrics(
        good_event_capture=(
            None if all_tp == 0 else Decimal(selected_tp) / Decimal(all_tp)
        ),
        bad_event_rejection=(
            None if all_stop == 0 else Decimal(excluded_stop) / Decimal(all_stop)
        ),
        opportunity_retention=Decimal(len(selected_labels)) / Decimal(len(all_labels)),
    )


def simulate_hysteresis(
    *,
    prior_selected: frozenset[str],
    ranks: dict[str, int],
    entry_cardinality: int,
) -> frozenset[str]:
    if entry_cardinality not in CARDINALITIES:
        raise ValueError("hysteresis entry cardinality must be frozen")
    retained = {
        instrument
        for instrument in prior_selected
        if instrument in ranks and ranks[instrument] <= 16
    }
    admitted = {
        instrument for instrument, rank in ranks.items() if rank <= entry_cardinality
    }
    return frozenset(retained | admitted)
