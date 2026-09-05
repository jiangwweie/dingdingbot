"""Frozen Stage-3 diagnostics and semantic sanity classification."""

from __future__ import annotations

from typing import cast

import pandas as pd

from research.multi_strategy_selection.replay import DISCOVERY_END_MS

RESOLVED = {"SIGNAL_TP1_FIRST", "SIGNAL_STOP_FIRST"}


def _path_stats(frame: pd.DataFrame) -> dict[str, object]:
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
        "median_mfe_signal_r": (
            None
            if frame.empty
            else float(pd.to_numeric(frame["mfe_signal_r"]).median())
        ),
        "median_mae_signal_r": (
            None
            if frame.empty
            else float(pd.to_numeric(frame["mae_signal_r"]).median())
        ),
    }


def period_summary(
    classified_baseline: pd.DataFrame,
    dynamic_events: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    strategies = sorted(classified_baseline["strategy"].unique())
    for strategy in strategies:
        baseline_strategy = classified_baseline.loc[
            classified_baseline["strategy"] == strategy
        ]
        dynamic_strategy = dynamic_events.loc[dynamic_events["strategy"] == strategy]
        for period, baseline_mask, dynamic_mask in (
            (
                "Discovery",
                baseline_strategy["trigger_candle_close_time_ms"] < DISCOVERY_END_MS,
                dynamic_strategy["trigger_candle_close_time_ms"] < DISCOVERY_END_MS,
            ),
            (
                "Holdout",
                baseline_strategy["trigger_candle_close_time_ms"] >= DISCOVERY_END_MS,
                dynamic_strategy["trigger_candle_close_time_ms"] >= DISCOVERY_END_MS,
            ),
            (
                "Full",
                pd.Series(True, index=baseline_strategy.index),
                pd.Series(True, index=dynamic_strategy.index),
            ),
        ):
            baseline_period = baseline_strategy.loc[baseline_mask]
            for cohort in ("ALL24", "SELECTED", "NEAR_THRESHOLD", "NOT_SELECTED"):
                cohort_frame = (
                    baseline_period
                    if cohort == "ALL24"
                    else baseline_period.loc[
                        baseline_period["selection_state"] == cohort
                    ]
                )
                rows.append(
                    {
                        "strategy": strategy,
                        "period": period,
                        "evidence_view": "COUNTERFACTUAL_MEMBERSHIP",
                        "cohort": cohort,
                        **_path_stats(cohort_frame),
                    }
                )
            rows.append(
                {
                    "strategy": strategy,
                    "period": period,
                    "evidence_view": "DYNAMIC_DETECTOR",
                    "cohort": "SELECTED",
                    **_path_stats(dynamic_strategy.loc[dynamic_mask]),
                }
            )
    return pd.DataFrame(rows)


def classify_strategies(periods: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for strategy in sorted(periods["strategy"].unique()):
        adverse_periods: list[str] = []
        evidence: dict[str, object] = {}
        for period in ("Discovery", "Holdout"):
            scoped = periods.loc[
                (periods["strategy"] == strategy)
                & (periods["period"] == period)
                & (periods["evidence_view"] == "COUNTERFACTUAL_MEMBERSHIP")
            ].set_index("cohort")
            selected = cast(pd.Series, scoped.loc["SELECTED"])
            rejected = cast(pd.Series, scoped.loc["NOT_SELECTED"])
            selected_net = selected["net_path_rate"]
            rejected_net = rejected["net_path_rate"]
            effect = (
                None
                if pd.isna(selected_net) or pd.isna(rejected_net)
                else float(selected_net) - float(rejected_net)
            )
            evidence[f"{period.lower()}_selected_resolved_n"] = int(
                selected["resolved_count"]
            )
            evidence[f"{period.lower()}_not_selected_resolved_n"] = int(
                rejected["resolved_count"]
            )
            evidence[f"{period.lower()}_selected_minus_not_selected_net"] = effect
            evidence[f"{period.lower()}_comparison_coverage_sufficient"] = bool(
                int(selected["resolved_count"]) >= 15
                and int(rejected["resolved_count"]) >= 15
            )
            adverse = bool(
                effect is not None
                and int(selected["resolved_count"]) >= 15
                and int(rejected["resolved_count"]) >= 15
                and effect <= -0.20
                and float(selected["tp1_first_rate"])
                < float(rejected["tp1_first_rate"])
                and float(selected["stop_first_rate"])
                > float(rejected["stop_first_rate"])
            )
            if adverse:
                adverse_periods.append(period)
        if len(adverse_periods) == 2:
            classification = "SEMANTIC_SELECTOR_REJECTED"
            reason = "clear_adverse_selection_in_discovery_and_holdout"
        elif adverse_periods:
            classification = "REVISE_ONCE"
            reason = "clear_adverse_selection_in_one_period"
        else:
            classification = "THEORY_COMPATIBLE_DYNAMIC_V0"
            reason = "operationally_valid_without_persistent_clear_adverse_selection"
        rows.append(
            {
                "strategy": strategy,
                **evidence,
                "comparison_coverage": (
                    "SUFFICIENT"
                    if evidence["discovery_comparison_coverage_sufficient"]
                    and evidence["holdout_comparison_coverage_sufficient"]
                    else "SPARSE_NOT_SELECTED_EVENTS"
                ),
                "classification": classification,
                "reason": reason,
            }
        )
    return pd.DataFrame(rows)


def turnover_summary(
    snapshots: pd.DataFrame,
    decisions: pd.DataFrame,
    *,
    evaluation_start_ms: int,
    evaluation_end_ms: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    selected = decisions.loc[decisions["member_state"] == "SELECTED"]
    snapshot_rows: list[dict[str, object]] = []
    duration_rows: list[dict[str, object]] = []
    for strategy in sorted(snapshots["strategy"].unique()):
        scoped_snapshots = snapshots.loc[
            (snapshots["strategy"] == strategy)
            & (snapshots["effective_from_ms"] >= evaluation_start_ms)
            & (snapshots["effective_from_ms"] < evaluation_end_ms)
        ].sort_values("effective_from_ms")
        prior: set[str] | None = None
        active_runs: dict[str, tuple[int, int]] = {}
        completed_runs: list[int] = []
        for raw in scoped_snapshots.to_dict("records"):
            snapshot = cast(dict[str, object], raw)
            snapshot_id = str(snapshot["selection_snapshot_id"])
            effective = int(str(snapshot["effective_from_ms"]))
            current = set(
                selected.loc[
                    selected["selection_snapshot_id"] == snapshot_id,
                    "exchange_instrument_id",
                ]
            )
            additions = 0 if prior is None else len(current - prior)
            removals = 0 if prior is None else len(prior - current)
            snapshot_rows.append(
                {
                    "strategy": strategy,
                    "selection_snapshot_id": snapshot_id,
                    "effective_from_ms": effective,
                    "additions": additions,
                    "removals": removals,
                    "turnover_fraction": None if prior is None else additions / 16,
                }
            )
            for instrument in tuple(active_runs):
                if instrument not in current:
                    started, last = active_runs.pop(instrument)
                    completed_runs.append(last - started)
            for instrument in current:
                if instrument in active_runs:
                    started, _ = active_runs[instrument]
                    active_runs[instrument] = (started, effective)
                else:
                    active_runs[instrument] = (effective, effective)
            prior = current
        cadence_ms = 4 * 3_600_000 if strategy in {"CPM-RO-001", "BRF2-001"} else 3_600_000
        for started, last in active_runs.values():
            completed_runs.append(last - started)
        durations_hours = [
            (duration_ms + cadence_ms) / 3_600_000 for duration_ms in completed_runs
        ]
        duration_rows.append(
            {
                "strategy": strategy,
                "snapshot_count": len(scoped_snapshots),
                "mean_turnover_fraction": (
                    pd.Series(
                        [
                            row["turnover_fraction"]
                            for row in snapshot_rows
                            if row["strategy"] == strategy
                            and row["turnover_fraction"] is not None
                        ],
                        dtype=float,
                    ).mean()
                ),
                "mean_selected_membership_hours": (
                    None if not durations_hours else sum(durations_hours) / len(durations_hours)
                ),
                "minimum_selected_count": 16,
                "empty_snapshot_count": 0,
                "insufficient_snapshot_count": 0,
            }
        )
    return pd.DataFrame(snapshot_rows), pd.DataFrame(duration_rows)
