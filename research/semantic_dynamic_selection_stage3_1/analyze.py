"""Frozen Stage-3.1 cardinality, discrimination and hysteresis analysis."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import cast

import numpy as np
import pandas as pd

from research.multi_strategy_selection.replay import DISCOVERY_END_MS
from research.semantic_dynamic_selection_stage3_1.core import (
    CARDINALITIES,
    capture_metrics,
    simulate_hysteresis,
)


@dataclass(frozen=True, slots=True)
class SetSequenceMetrics:
    mean_turnover: float
    p95_turnover: float
    mean_membership_hours: float
    mean_additions: float
    mean_removals: float


def _stats(frame: pd.DataFrame) -> dict[str, object]:
    labels = frame["path_label"]
    tp = int((labels == "SIGNAL_TP1_FIRST").sum())
    stop = int((labels == "SIGNAL_STOP_FIRST").sum())
    resolved = tp + stop
    return {
        "event_count": len(frame),
        "resolved_count": resolved,
        "tp1_first_count": tp,
        "stop_first_count": stop,
        "neither_count": int((labels == "NEITHER").sum()),
        "ambiguous_count": int((labels == "AMBIGUOUS").sum()),
        "tp1_first_rate": None if resolved == 0 else tp / resolved,
        "stop_first_rate": None if resolved == 0 else stop / resolved,
        "net_path_rate": None if resolved == 0 else (tp - stop) / resolved,
    }


def build_period_summary(classified: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for strategy in sorted(classified["strategy"].unique()):
        strategy_frame = classified.loc[classified["strategy"] == strategy]
        for cardinality in CARDINALITIES:
            scoped = strategy_frame.loc[strategy_frame["cardinality"] == cardinality]
            for period, mask in (
                ("Discovery", scoped["trigger_candle_close_time_ms"] < DISCOVERY_END_MS),
                ("Holdout", scoped["trigger_candle_close_time_ms"] >= DISCOVERY_END_MS),
                ("Full", pd.Series(True, index=scoped.index)),
            ):
                period_frame = scoped.loc[mask]
                selected = period_frame.loc[
                    period_frame["selection_cohort"] == "SELECTED"
                ]
                excluded = period_frame.loc[
                    period_frame["selection_cohort"] == "EXCLUDED"
                ]
                all_stats = _stats(period_frame)
                selected_stats = _stats(selected)
                excluded_stats = _stats(excluded)
                metrics = capture_metrics(
                    all_labels=tuple(
                        "TP"
                        if label == "SIGNAL_TP1_FIRST"
                        else "STOP"
                        if label == "SIGNAL_STOP_FIRST"
                        else label
                        for label in period_frame["path_label"]
                    ),
                    selected_labels=tuple(
                        "TP"
                        if label == "SIGNAL_TP1_FIRST"
                        else "STOP"
                        if label == "SIGNAL_STOP_FIRST"
                        else label
                        for label in selected["path_label"]
                    ),
                    excluded_labels=tuple(
                        "TP"
                        if label == "SIGNAL_TP1_FIRST"
                        else "STOP"
                        if label == "SIGNAL_STOP_FIRST"
                        else label
                        for label in excluded["path_label"]
                    ),
                )
                selected_net = selected_stats["net_path_rate"]
                excluded_net = excluded_stats["net_path_rate"]
                rows.append(
                    {
                        "strategy": strategy,
                        "cardinality": cardinality,
                        "period": period,
                        "baseline_event_count": all_stats["event_count"],
                        **{
                            f"selected_{key}": value
                            for key, value in selected_stats.items()
                        },
                        **{
                            f"excluded_{key}": value
                            for key, value in excluded_stats.items()
                        },
                        "operational_effect": (
                            None
                            if selected_net is None or excluded_net is None
                            else cast(float, selected_net)
                            - cast(float, excluded_net)
                        ),
                        "good_event_capture": (
                            None
                            if metrics.good_event_capture is None
                            else float(metrics.good_event_capture)
                        ),
                        "bad_event_rejection": (
                            None
                            if metrics.bad_event_rejection is None
                            else float(metrics.bad_event_rejection)
                        ),
                        "opportunity_retention": float(metrics.opportunity_retention),
                    }
                )
    return pd.DataFrame(rows)


def _clear_adverse(row: pd.Series) -> bool:
    return bool(
        int(row["selected_resolved_count"]) >= 15
        and int(row["excluded_resolved_count"]) >= 15
        and float(row["operational_effect"]) <= -0.20
        and float(row["selected_tp1_first_rate"])
        < float(row["excluded_tp1_first_rate"])
        and float(row["selected_stop_first_rate"])
        > float(row["excluded_stop_first_rate"])
    )


def cardinality_summary(
    periods: pd.DataFrame,
    dynamic_events: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for strategy in sorted(periods["strategy"].unique()):
        for cardinality in CARDINALITIES:
            scoped = periods.loc[
                (periods["strategy"] == strategy)
                & (periods["cardinality"] == cardinality)
            ].set_index("period")
            discovery = cast(pd.Series, scoped.loc["Discovery"])
            holdout = cast(pd.Series, scoped.loc["Holdout"])
            full = cast(pd.Series, scoped.loc["Full"])
            baseline_count = int(full["baseline_event_count"])
            dynamic_count = int(
                (
                    (dynamic_events["strategy"] == strategy)
                    & (dynamic_events["cardinality"] == cardinality)
                ).sum()
            )
            rows.append(
                {
                    "strategy": strategy,
                    "cardinality": cardinality,
                    "full_good_event_capture": full["good_event_capture"],
                    "full_bad_event_rejection": full["bad_event_rejection"],
                    "full_opportunity_retention": full["opportunity_retention"],
                    "dynamic_detector_event_retention": (
                        None if baseline_count == 0 else dynamic_count / baseline_count
                    ),
                    "discovery_operational_effect": discovery["operational_effect"],
                    "holdout_operational_effect": holdout["operational_effect"],
                    "discovery_clear_adverse": _clear_adverse(discovery),
                    "holdout_clear_adverse": _clear_adverse(holdout),
                    "persistent_clear_adverse": (
                        _clear_adverse(discovery) and _clear_adverse(holdout)
                    ),
                }
            )
    return pd.DataFrame(rows)


def recommend_cardinalities(summary: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for strategy in sorted(summary["strategy"].unique()):
        scoped = summary.loc[summary["strategy"] == strategy].set_index("cardinality")
        recommended: int | None = None
        for cardinality in (8, 12, 16):
            row = cast(pd.Series, scoped.loc[cardinality])
            if (
                float(row["full_good_event_capture"]) >= 0.80
                and not bool(row["persistent_clear_adverse"])
            ):
                recommended = cardinality
                break
        rows.append(
            {
                "strategy": strategy,
                "recommended_entry_cardinality": recommended,
                "retention_cardinality": 16 if recommended is not None else None,
                "recommendation_status": (
                    "MINIMUM_COMPATIBLE_CAPTURE_CARDINALITY"
                    if recommended is not None
                    else "NO_COMPATIBLE_CARDINALITY"
                ),
            }
        )
    return pd.DataFrame(rows)


def build_block_summary(classified: pd.DataFrame) -> pd.DataFrame:
    local = classified.copy()
    evaluation_start = int(local["trigger_candle_close_time_ms"].min())
    local["block_index"] = (
        (local["trigger_candle_close_time_ms"] - evaluation_start)
        // (7 * 86_400_000)
    ).astype(int)
    rows: list[dict[str, object]] = []
    for (strategy, cardinality, block), frame in local.groupby(
        ["strategy", "cardinality", "block_index"], sort=True
    ):
        selected = frame.loc[frame["selection_cohort"] == "SELECTED"]
        excluded = frame.loc[frame["selection_cohort"] == "EXCLUDED"]
        selected_stats = _stats(selected)
        excluded_stats = _stats(excluded)
        selected_net = selected_stats["net_path_rate"]
        excluded_net = excluded_stats["net_path_rate"]
        rows.append(
            {
                "strategy": strategy,
                "cardinality": int(str(cardinality)),
                "block_index": int(str(block)),
                "selected_resolved_n": selected_stats["resolved_count"],
                "excluded_resolved_n": excluded_stats["resolved_count"],
                "operational_effect": (
                    None
                    if selected_net is None or excluded_net is None
                    else cast(float, selected_net) - cast(float, excluded_net)
                ),
            }
        )
    return pd.DataFrame(rows)


def cpm_revision_verdict(
    periods: pd.DataFrame,
    blocks: pd.DataFrame,
) -> dict[str, object]:
    scoped = periods.loc[
        (periods["strategy"] == "CPM-RO-001")
        & (periods["cardinality"] == 16)
    ].set_index("period")
    discovery = cast(pd.Series, scoped.loc["Discovery"])
    holdout = cast(pd.Series, scoped.loc["Holdout"])
    both_negative = bool(
        int(discovery["selected_resolved_count"]) >= 15
        and int(discovery["excluded_resolved_count"]) >= 15
        and int(holdout["selected_resolved_count"]) >= 15
        and int(holdout["excluded_resolved_count"]) >= 15
        and float(discovery["operational_effect"]) <= -0.10
        and float(holdout["operational_effect"]) <= -0.10
    )
    comparable = blocks.loc[
        (blocks["strategy"] == "CPM-RO-001")
        & (blocks["cardinality"] == 16)
        & blocks["operational_effect"].notna()
    ]
    adverse_blocks = int((comparable["operational_effect"] <= -0.10).sum())
    adverse_ratio = 0 if comparable.empty else adverse_blocks / len(comparable)
    rejected = both_negative or adverse_ratio >= 0.60
    return {
        "strategy": "CPM-RO-001",
        "revision_removed_stage3_failure": not rejected,
        "comparable_block_count": len(comparable),
        "adverse_block_count": adverse_blocks,
        "adverse_block_ratio": adverse_ratio,
        "verdict": (
            "CPM_SEMANTIC_SELECTOR_REJECTED_V1"
            if rejected
            else "CPM_THEORY_COMPATIBLE_DYNAMIC_V1"
        ),
    }


def mpg_discrimination_audit(
    snapshots: pd.DataFrame,
    decisions: pd.DataFrame,
    classified: pd.DataFrame,
) -> pd.DataFrame:
    mpg_snapshots = snapshots.loc[snapshots["strategy"] == "MPG-001"]
    mpg_decisions = decisions.loc[decisions["strategy"] == "MPG-001"]
    rows: list[dict[str, object]] = []
    for cardinality in CARDINALITIES:
        tie_counts: list[int] = []
        tie_fractions: list[float] = []
        tie_selected_fractions: list[float] = []
        feature_determined_fractions: list[float] = []
        for snapshot_id in mpg_snapshots["selection_snapshot_id"]:
            frame = mpg_decisions.loc[
                mpg_decisions["selection_snapshot_id"] == snapshot_id
            ].sort_values("rank")
            boundary = frame.iloc[cardinality - 1]["feature_value"]
            equal = frame.loc[frame["feature_value"] == boundary]
            strict_above = int(
                (pd.to_numeric(frame["feature_value"]) > float(boundary)).sum()
            )
            tie_count = len(equal)
            tie_selected = cardinality - strict_above if tie_count > 1 else 0
            tie_counts.append(tie_count)
            tie_fractions.append(tie_count / 24)
            tie_selected_fractions.append(tie_selected / cardinality)
            feature_determined_fractions.append(1 - tie_selected / cardinality)
        baseline = classified.loc[
            (classified["strategy"] == "MPG-001")
            & (classified["cardinality"] == cardinality)
        ]
        rows.append(
            {
                "cardinality": cardinality,
                "snapshot_count": len(mpg_snapshots),
                "mean_unique_feature_value_count": float(
                    mpg_snapshots["unique_feature_value_count"].mean()
                ),
                "mean_boundary_tie_count": float(np.mean(tie_counts)),
                "mean_boundary_tie_fraction": float(np.mean(tie_fractions)),
                "mean_tie_break_selected_fraction": float(
                    np.mean(tie_selected_fractions)
                ),
                "mean_feature_determined_fraction": float(
                    np.mean(feature_determined_fractions)
                ),
                "baseline_event_selected_fraction": float(
                    (baseline["selection_cohort"] == "SELECTED").mean()
                ),
            }
        )
    return pd.DataFrame(rows)


def mpg_revision_verdict(
    audit: pd.DataFrame,
    cardinality: pd.DataFrame,
) -> dict[str, object]:
    all_event_coverage_high = bool(
        (audit["baseline_event_selected_fraction"] > 0.95).all()
    )
    all_tie_reliance_high = bool(
        (audit["mean_tie_break_selected_fraction"] > 0.05).all()
    )
    persistent_adverse = bool(
        cardinality.loc[
            cardinality["strategy"] == "MPG-001", "persistent_clear_adverse"
        ].any()
    )
    low_discrimination = all_event_coverage_high and all_tie_reliance_high
    return {
        "strategy": "MPG-001",
        "meaningful_discrimination": not low_discrimination,
        "persistent_clear_adverse": persistent_adverse,
        "verdict": (
            "MPG_SELECTOR_LOW_DISCRIMINATION"
            if low_discrimination
            else "MPG_SEMANTIC_SELECTOR_REJECTED_V1"
            if persistent_adverse
            else "MPG_THEORY_COMPATIBLE_DYNAMIC_V1"
        ),
    }


def _sequence_metrics(
    sequence: list[tuple[int, frozenset[str]]],
    cadence_hours: int,
) -> SetSequenceMetrics:
    prior: frozenset[str] | None = None
    turnovers: list[float] = []
    additions: list[int] = []
    removals: list[int] = []
    active_since: dict[str, int] = {}
    durations: list[int] = []
    for effective, current in sequence:
        if prior is not None:
            added = len(current - prior)
            removed = len(prior - current)
            additions.append(added)
            removals.append(removed)
            turnovers.append(added / max(1, len(prior)))
        for instrument in tuple(active_since):
            if instrument not in current:
                durations.append(effective - active_since.pop(instrument))
        for instrument in current:
            active_since.setdefault(instrument, effective)
        prior = current
    if sequence:
        end = sequence[-1][0] + cadence_hours * 3_600_000
        durations.extend(end - start for start in active_since.values())
    return SetSequenceMetrics(
        mean_turnover=0 if not turnovers else float(np.mean(turnovers)),
        p95_turnover=0 if not turnovers else float(np.quantile(turnovers, 0.95)),
        mean_membership_hours=(
            0 if not durations else float(np.mean(durations)) / 3_600_000
        ),
        mean_additions=0 if not additions else float(np.mean(additions)),
        mean_removals=0 if not removals else float(np.mean(removals)),
    )


def hysteresis_summary(
    snapshots: pd.DataFrame,
    decisions: pd.DataFrame,
    recommendations: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    recommendation_lookup = recommendations.set_index("strategy")[
        "recommended_entry_cardinality"
    ].to_dict()
    for strategy, raw_cardinality in recommendation_lookup.items():
        if pd.isna(raw_cardinality):
            continue
        cardinality = int(raw_cardinality)
        scoped_snapshots = snapshots.loc[snapshots["strategy"] == strategy].sort_values(
            "effective_from_ms"
        )
        fixed_sequence: list[tuple[int, frozenset[str]]] = []
        hysteresis_sequence: list[tuple[int, frozenset[str]]] = []
        prior = frozenset[str]()
        for snapshot in scoped_snapshots.to_dict("records"):
            item = cast(dict[str, object], snapshot)
            frame = decisions.loc[
                decisions["selection_snapshot_id"] == item["selection_snapshot_id"]
            ]
            ranks = {
                str(row["exchange_instrument_id"]): int(str(row["rank"]))
                for row in frame.to_dict("records")
            }
            effective = int(str(item["effective_from_ms"]))
            fixed = frozenset(
                instrument for instrument, rank in ranks.items() if rank <= cardinality
            )
            prior = simulate_hysteresis(
                prior_selected=prior,
                ranks=ranks,
                entry_cardinality=cardinality,
            )
            fixed_sequence.append((effective, fixed))
            hysteresis_sequence.append((effective, prior))
        cadence = 4 if strategy in {"CPM-RO-001", "BRF2-001"} else 1
        for mode, metrics in (
            ("FIXED_TOP_N", _sequence_metrics(fixed_sequence, cadence)),
            ("ENTRY_N_RETAIN_16", _sequence_metrics(hysteresis_sequence, cadence)),
        ):
            rows.append(
                {
                    "strategy": strategy,
                    "entry_cardinality": cardinality,
                    "retention_cardinality": 16,
                    "mode": mode,
                    **asdict(metrics),
                }
            )
    return pd.DataFrame(rows)
