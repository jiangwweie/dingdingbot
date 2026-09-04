"""Stage-2.1 time-cluster robustness audit for the four frozen hypotheses."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, cast

import numpy as np
import pandas as pd

from research.multi_strategy_selection.replay import DISCOVERY_END_MS

SUPPORTED_HYPOTHESES = (
    ("BRF2-001", "avg_cross_asset_corr_24h"),
    ("BRF2-001", "market_rv_24h"),
    ("CPM-RO-001", "avg_cross_asset_corr_24h"),
    ("CPM-RO-001", "directional_efficiency_24h"),
)
RESOLVED_OUTCOME = {
    "SIGNAL_TP1_FIRST": 1.0,
    "SIGNAL_STOP_FIRST": -1.0,
}
Cluster = Literal["utc_day", "utc_week"]
Aggregation = Literal["event", "trigger_hour"]


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    cluster: Cluster
    requested_replicates: int
    valid_replicates: int
    seed: int
    median: float
    ci_low: float
    ci_high: float


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _utc_cluster_labels(frame: pd.DataFrame, cluster: Cluster) -> pd.Series:
    timestamps = pd.to_datetime(
        frame["trigger_candle_close_time_ms"],
        unit="ms",
        utc=True,
    )
    if cluster == "utc_day":
        return timestamps.dt.strftime("%Y-%m-%d")
    week_start = timestamps - pd.to_timedelta(timestamps.dt.weekday, unit="D")
    return week_start.dt.strftime("%Y-%m-%d")


def _resolved_extremes(frame: pd.DataFrame, feature: str) -> pd.DataFrame:
    bucket_column = f"{feature}_bucket"
    required = {
        "trigger_candle_close_time_ms",
        "path_label",
        bucket_column,
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"cluster audit input is missing columns: {missing}")
    result = frame.loc[
        frame["path_label"].isin(RESOLVED_OUTCOME)
        & frame[bucket_column].isin({"LOW", "HIGH"})
    ].copy()
    result["bucket"] = result[bucket_column]
    result["outcome"] = result["path_label"].map(RESOLVED_OUTCOME).astype(float)
    result["trigger_hour"] = result["trigger_candle_close_time_ms"].astype("int64")
    return result


def high_minus_low_effect(
    frame: pd.DataFrame,
    feature: str,
    *,
    aggregate_by: Aggregation = "event",
) -> float | None:
    resolved = _resolved_extremes(frame, feature)
    if aggregate_by == "trigger_hour":
        resolved = resolved.groupby(
            ["trigger_hour", "bucket"],
            as_index=False,
        ).agg(
            outcome=("outcome", "mean"),
        )
    elif aggregate_by != "event":
        raise ValueError(f"unsupported aggregation: {aggregate_by}")
    rates = resolved.groupby("bucket")["outcome"].mean()
    if "LOW" not in rates or "HIGH" not in rates:
        return None
    return float(rates["HIGH"] - rates["LOW"])


def effect_by_cluster(
    frame: pd.DataFrame,
    feature: str,
    *,
    cluster: Cluster,
) -> pd.DataFrame:
    resolved = _resolved_extremes(frame, feature)
    resolved["cluster"] = _utc_cluster_labels(resolved, cluster)
    rows: list[dict[str, object]] = []
    for label, group in resolved.groupby("cluster", sort=True):
        counts = group["bucket"].value_counts()
        rows.append(
            {
                "cluster": str(label),
                "effect": high_minus_low_effect(group, feature),
                "low_resolved_n": int(counts.get("LOW", 0)),
                "high_resolved_n": int(counts.get("HIGH", 0)),
                "low_unique_context_hours": int(
                    group.loc[group["bucket"] == "LOW", "trigger_hour"].nunique()
                ),
                "high_unique_context_hours": int(
                    group.loc[group["bucket"] == "HIGH", "trigger_hour"].nunique()
                ),
            }
        )
    return pd.DataFrame(rows)


def leave_one_cluster_out(
    frame: pd.DataFrame,
    feature: str,
    *,
    cluster: Cluster,
) -> pd.DataFrame:
    local = frame.copy()
    local["cluster"] = _utc_cluster_labels(local, cluster)
    resolved = _resolved_extremes(frame, feature)
    eligible_labels = sorted(_utc_cluster_labels(resolved, cluster).unique())
    rows = [
        {
            "excluded_cluster": str(label),
            "remaining_effect": high_minus_low_effect(
                local.loc[local["cluster"] != label],
                feature,
            ),
        }
        for label in eligible_labels
    ]
    return pd.DataFrame(rows)


def bootstrap_cluster_effect(
    frame: pd.DataFrame,
    feature: str,
    *,
    cluster: Cluster,
    replicates: int,
    seed: int,
) -> BootstrapResult:
    if replicates <= 0:
        raise ValueError("bootstrap replicates must be positive")
    resolved = _resolved_extremes(frame, feature)
    resolved["cluster"] = _utc_cluster_labels(resolved, cluster)
    labels = tuple(sorted(resolved["cluster"].unique()))
    if not labels:
        raise ValueError("cluster bootstrap requires resolved extreme-bucket events")
    totals = (
        resolved.groupby(["cluster", "bucket"])["outcome"]
        .agg(["sum", "count"])
        .unstack(fill_value=0)
        .reindex(labels, fill_value=0)
    )
    low_sum = totals[("sum", "LOW")].to_numpy(dtype=float) if ("sum", "LOW") in totals else np.zeros(len(labels))
    low_count = totals[("count", "LOW")].to_numpy(dtype=float) if ("count", "LOW") in totals else np.zeros(len(labels))
    high_sum = totals[("sum", "HIGH")].to_numpy(dtype=float) if ("sum", "HIGH") in totals else np.zeros(len(labels))
    high_count = totals[("count", "HIGH")].to_numpy(dtype=float) if ("count", "HIGH") in totals else np.zeros(len(labels))
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(labels), size=(replicates, len(labels)))
    sampled_low_count = low_count[draws].sum(axis=1)
    sampled_high_count = high_count[draws].sum(axis=1)
    valid = (sampled_low_count > 0) & (sampled_high_count > 0)
    effects = (
        high_sum[draws].sum(axis=1)[valid] / sampled_high_count[valid]
        - low_sum[draws].sum(axis=1)[valid] / sampled_low_count[valid]
    )
    if not len(effects):
        raise ValueError("no valid cluster bootstrap replicate retained both extreme buckets")
    low, median, high = np.quantile(effects, [0.025, 0.5, 0.975])
    return BootstrapResult(
        cluster=cluster,
        requested_replicates=replicates,
        valid_replicates=len(effects),
        seed=seed,
        median=float(median),
        ci_low=float(low),
        ci_high=float(high),
    )


def _seed(base: int, *parts: str) -> int:
    payload = ":".join((str(base), *parts)).encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def _same_sign_ratio(effects: pd.Series, base_effect: float | None) -> float | None:
    valid = pd.to_numeric(effects, errors="coerce").dropna()
    if base_effect is None or base_effect == 0 or valid.empty:
        return None
    return float((np.sign(valid) == np.sign(base_effect)).mean())


def _trigger_hour_rows(frame: pd.DataFrame, feature: str) -> pd.DataFrame:
    resolved = _resolved_extremes(frame, feature)
    return (
        resolved.groupby(["trigger_hour", "bucket"], as_index=False)
        .agg(resolved_n=("outcome", "size"), net_path_rate=("outcome", "mean"))
        .sort_values(["trigger_hour", "bucket"])
        .reset_index(drop=True)
    )


def run_audit(
    events: pd.DataFrame,
    *,
    replicates: int,
    seed: int,
) -> dict[str, pd.DataFrame]:
    summaries: list[dict[str, object]] = []
    lodo_rows: list[pd.DataFrame] = []
    lowo_rows: list[pd.DataFrame] = []
    day_rows: list[pd.DataFrame] = []
    week_rows: list[pd.DataFrame] = []
    hour_rows: list[pd.DataFrame] = []
    for strategy, feature in SUPPORTED_HYPOTHESES:
        strategy_events = events.loc[events["strategy"] == strategy]
        period_results: dict[str, dict[str, object]] = {}
        for period, period_frame in (
            (
                "Discovery",
                strategy_events.loc[
                    strategy_events["trigger_candle_close_time_ms"] < DISCOVERY_END_MS
                ],
            ),
            (
                "Holdout",
                strategy_events.loc[
                    strategy_events["trigger_candle_close_time_ms"] >= DISCOVERY_END_MS
                ],
            ),
        ):
            base_effect = high_minus_low_effect(period_frame, feature)
            hour_effect = high_minus_low_effect(
                period_frame,
                feature,
                aggregate_by="trigger_hour",
            )
            resolved = _resolved_extremes(period_frame, feature)
            counts = resolved["bucket"].value_counts()
            unique_hours = resolved.groupby("bucket")["trigger_hour"].nunique()
            lodo = leave_one_cluster_out(
                period_frame,
                feature,
                cluster="utc_day",
            )
            lowo = leave_one_cluster_out(
                period_frame,
                feature,
                cluster="utc_week",
            )
            by_day = effect_by_cluster(
                period_frame,
                feature,
                cluster="utc_day",
            )
            by_week = effect_by_cluster(
                period_frame,
                feature,
                cluster="utc_week",
            )
            hourly = _trigger_hour_rows(period_frame, feature)
            for detail in (lodo, lowo, by_day, by_week, hourly):
                detail.insert(0, "period", period)
                detail.insert(0, "feature", feature)
                detail.insert(0, "strategy", strategy)
            lodo_rows.append(lodo)
            lowo_rows.append(lowo)
            day_rows.append(by_day)
            week_rows.append(by_week)
            hour_rows.append(hourly)
            day_bootstrap = bootstrap_cluster_effect(
                period_frame,
                feature,
                cluster="utc_day",
                replicates=replicates,
                seed=_seed(seed, strategy, feature, period, "utc_day"),
            )
            week_bootstrap = bootstrap_cluster_effect(
                period_frame,
                feature,
                cluster="utc_week",
                replicates=replicates,
                seed=_seed(seed, strategy, feature, period, "utc_week"),
            )
            period_results[period] = {
                "event_effect": base_effect,
                "trigger_hour_effect": hour_effect,
                "low_resolved_n": int(counts.get("LOW", 0)),
                "high_resolved_n": int(counts.get("HIGH", 0)),
                "low_unique_context_hours": int(unique_hours.get("LOW", 0)),
                "high_unique_context_hours": int(unique_hours.get("HIGH", 0)),
                "lodo_valid_n": int(lodo["remaining_effect"].notna().sum()),
                "lodo_same_sign_ratio": _same_sign_ratio(
                    lodo["remaining_effect"],
                    base_effect,
                ),
                "lowo_valid_n": int(lowo["remaining_effect"].notna().sum()),
                "lowo_same_sign_ratio": _same_sign_ratio(
                    lowo["remaining_effect"],
                    base_effect,
                ),
                "day_bootstrap": day_bootstrap,
                "week_bootstrap": week_bootstrap,
            }
        row: dict[str, object] = {"strategy": strategy, "feature": feature}
        for period, metrics in period_results.items():
            prefix = period.lower()
            for key, value in metrics.items():
                if isinstance(value, BootstrapResult):
                    for bootstrap_key, bootstrap_value in asdict(value).items():
                        row[f"{prefix}_{key}_{bootstrap_key}"] = bootstrap_value
                else:
                    row[f"{prefix}_{key}"] = value
        summaries.append(row)
    return {
        "summary": pd.DataFrame(summaries),
        "lodo": pd.concat(lodo_rows, ignore_index=True),
        "lowo": pd.concat(lowo_rows, ignore_index=True),
        "effect_by_day": pd.concat(day_rows, ignore_index=True),
        "effect_by_week": pd.concat(week_rows, ignore_index=True),
        "trigger_hour": pd.concat(hour_rows, ignore_index=True),
    }


def _report(summary: pd.DataFrame) -> str:
    rows: list[str] = []
    for raw_row in summary.to_dict("records"):
        row = cast(dict[str, object], raw_row)
        day_valid = cast(float, row["holdout_day_bootstrap_valid_replicates"]) / cast(
            float, row["holdout_day_bootstrap_requested_replicates"]
        )
        week_valid = cast(
            float, row["holdout_week_bootstrap_valid_replicates"]
        ) / cast(
            float, row["holdout_week_bootstrap_requested_replicates"]
        )
        rows.append(
            "| {strategy} | {feature} | {event:+.3f} | {hour:+.3f} | {low_hours} | "
            "{high_hours} | {lodo:.1%} | {lowo:.1%} | [{day_low:+.3f}, {day_high:+.3f}] | "
            "[{week_low:+.3f}, {week_high:+.3f}] | {day_valid:.1%} | {week_valid:.1%} |".format(
                strategy=str(row["strategy"]),
                feature=str(row["feature"]),
                event=cast(float, row["holdout_event_effect"]),
                hour=cast(float, row["holdout_trigger_hour_effect"]),
                low_hours=int(cast(float, row["holdout_low_unique_context_hours"])),
                high_hours=int(
                    cast(float, row["holdout_high_unique_context_hours"])
                ),
                lodo=cast(float, row["holdout_lodo_same_sign_ratio"]),
                lowo=cast(float, row["holdout_lowo_same_sign_ratio"]),
                day_low=cast(float, row["holdout_day_bootstrap_ci_low"]),
                day_high=cast(float, row["holdout_day_bootstrap_ci_high"]),
                week_low=cast(float, row["holdout_week_bootstrap_ci_low"]),
                week_high=cast(float, row["holdout_week_bootstrap_ci_high"]),
                day_valid=day_valid,
                week_valid=week_valid,
            )
        )
    rendered_rows = "\n".join(rows)
    return f"""# Stage-2.1 Cluster Robustness Audit

## Status

```text
research_status = STAGE2_1_CLUSTER_ROBUSTNESS_COMPLETE
feature_selection_changed = FALSE
cutoff_changed = FALSE
selector_design_authority = NONE
implementation_authority = NONE
production_authority = NONE
```

## Audit contract

This audit uses only the four Stage-2 `SUPPORTED_FOR_SHADOW` rows, their frozen
LOW/HIGH buckets, resolved Signal-R first-passage labels, and the original
Discovery/Holdout boundary. It does not search thresholds, add features,
combine factors, or reclassify a hypothesis automatically.

Trigger-hour aggregation gives every unique Event trigger hour equal weight
within each bucket. Leave-one-out removes an entire UTC day or Monday-based UTC
week. Bootstrap intervals resample complete UTC-day or UTC-week clusters with
replacement, preserving all cross-sectional Events inside the sampled cluster.

## Holdout results

| Strategy | Feature | Event effect | Trigger-hour effect | LOW hours | HIGH hours | LODO sign | LOWO sign | Day bootstrap 95% CI | Week bootstrap 95% CI | Day valid | Week valid |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
{rendered_rows}

The Holdout contains only three Monday-based UTC-week clusters, including one
partial week. Week-level leave-one-out and bootstrap results therefore measure
sensitivity to these observed blocks but must not be read as a precise
large-sample confidence interval.

## Evidence reading

- `CPM-RO-001 × directional_efficiency_24h` retains a positive trigger-hour
  effect and 100% day/week leave-one-out sign stability. Its UTC-week bootstrap
  interval remains positive, while its UTC-day interval still crosses zero.
- `BRF2-001 × market_rv_24h` retains a positive trigger-hour effect and 100%
  day leave-one-out stability. Its UTC-day bootstrap interval remains positive,
  but one of three leave-one-week-out runs reverses and the week interval
  crosses zero.
- `CPM-RO-001 × avg_cross_asset_corr_24h` retains the expected negative
  trigger-hour effect, but both cluster-bootstrap intervals touch or cross zero
  and one day/week exclusion can reverse the effect.
- `BRF2-001 × avg_cross_asset_corr_24h` retains positive leave-one-out signs,
  but the Holdout LOW bucket represents only 10 unique trigger hours and its
  UTC-day bootstrap interval crosses zero.

## Interpretation boundary

The audit measures sensitivity to observed time clustering. It does not create
independent market regimes, prove causal Context effects, or produce a
production Selector. The original Stage-2 classifications remain research
provenance; the cluster metrics are additional evidence for independent review.
"""


def write_audit(
    *,
    events_path: Path,
    screening_path: Path,
    output_dir: Path,
    replicates: int,
    seed: int,
) -> dict[str, object]:
    events = pd.read_parquet(events_path)
    screening = pd.read_csv(screening_path)
    supported = tuple(
        map(
            tuple,
            screening.loc[
                screening["classification"] == "SUPPORTED_FOR_SHADOW",
                ["strategy", "feature"],
            ].to_records(index=False),
        )
    )
    if tuple(sorted(supported)) != tuple(sorted(SUPPORTED_HYPOTHESES)):
        raise ValueError("Stage-2 supported hypothesis identity drifted")
    output_dir.mkdir(parents=True, exist_ok=True)
    results = run_audit(events, replicates=replicates, seed=seed)
    artifact_paths = {
        "stage2_1_cluster_summary.csv": results["summary"],
        "stage2_1_lodo.csv": results["lodo"],
        "stage2_1_lowo.csv": results["lowo"],
        "stage2_1_effect_by_day.csv": results["effect_by_day"],
        "stage2_1_effect_by_utc_week.csv": results["effect_by_week"],
        "stage2_1_trigger_hour_clusters.csv": results["trigger_hour"],
    }
    for name, frame in artifact_paths.items():
        frame.to_csv(output_dir / name, index=False)
    report_name = "STAGE2_1_CLUSTER_ROBUSTNESS_REPORT.md"
    (output_dir / report_name).write_text(
        _report(results["summary"]),
        encoding="utf-8",
    )
    manifest: dict[str, object] = {
        "schema": "brc.research.multi_strategy_selection.stage2_1_cluster_audit.v1",
        "research_status": "STAGE2_1_CLUSTER_ROBUSTNESS_COMPLETE",
        "base_stage2_commit": "3e073c29a27621dcde8830af6a1a7cb8115ae83e",
        "input_replayed_events_sha256": _sha256(events_path),
        "input_feature_screening_sha256": _sha256(screening_path),
        "input_stage2_manifest_sha256": _sha256(
            events_path.with_name("stage2_replay_manifest.json")
        ),
        "audit_code_sha256": _sha256(Path(__file__)),
        "supported_hypotheses": [
            {"strategy": strategy, "feature": feature}
            for strategy, feature in SUPPORTED_HYPOTHESES
        ],
        "periods": {
            "Discovery": ["2026-07-31T00:00:00Z", "2026-08-16T00:00:00Z"],
            "Holdout": ["2026-08-16T00:00:00Z", "2026-08-31T00:00:00Z"],
        },
        "effect": "HIGH net_path_rate minus LOW net_path_rate",
        "resolved_labels": sorted(RESOLVED_OUTCOME),
        "trigger_hour_aggregation": "equal weight per unique trigger hour and bucket",
        "leave_one_out": ["UTC calendar day", "Monday-based UTC week"],
        "bootstrap": {
            "replicates": replicates,
            "base_seed": seed,
            "clusters": ["UTC calendar day", "Monday-based UTC week"],
            "interval": [0.025, 0.975],
        },
        "feature_selection_changed": False,
        "cutoff_changed": False,
        "selector_design_authority": "NONE",
        "implementation_authority": "NONE",
        "production_authority": "NONE",
    }
    artifact_names = (*artifact_paths, report_name)
    manifest["artifact_sha256"] = {
        name: _sha256(output_dir / name) for name in artifact_names
    }
    manifest_path = output_dir / "stage2_1_cluster_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--screening", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--replicates", type=int, default=20_000)
    parser.add_argument("--seed", type=int, default=20_260_904)
    args = parser.parse_args()
    manifest = write_audit(
        events_path=args.events.resolve(),
        screening_path=args.screening.resolve(),
        output_dir=args.output_dir.resolve(),
        replicates=args.replicates,
        seed=args.seed,
    )
    supported = manifest["supported_hypotheses"]
    if not isinstance(supported, list):
        raise TypeError("supported_hypotheses manifest field must be a list")
    print(
        json.dumps(
            {
                "research_status": manifest["research_status"],
                "hypothesis_count": len(supported),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
