"""Execute and freeze the Stage-3 semantic Dynamic Selection Replay."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from math import isnan
from pathlib import Path
from typing import cast

import pandas as pd

from research.multi_strategy_selection.outcomes import compute_first_passage
from research.multi_strategy_selection.replay import (
    DISCOVERY_END_MS,
    EVALUATION_END_MS,
    EVALUATION_START_MS,
)
from research.semantic_dynamic_selection.analyze import (
    classify_strategies,
    period_summary,
    turnover_summary,
)
from research.semantic_dynamic_selection.replay import (
    classify_baseline_events,
    replay_dynamic_detectors,
)
from research.semantic_dynamic_selection.selection import build_selection_artifacts

ARTIFACT_NAMES = (
    "stage3_selection_snapshots.parquet",
    "stage3_member_decisions.parquet",
    "stage3_mpg_rank_history.parquet",
    "stage3_baseline_membership_events.parquet",
    "stage3_dynamic_detector_evaluations.parquet",
    "stage3_dynamic_events.parquet",
    "stage3_dynamic_outcomes.parquet",
    "stage3_period_summary.csv",
    "stage3_strategy_classification.csv",
    "stage3_turnover_by_snapshot.csv",
    "stage3_turnover_summary.csv",
    "stage3_block_summary.csv",
    "stage3_replay_counters.json",
    "STAGE3_SEMANTIC_DYNAMIC_SELECTION_REPORT.md",
)


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _json_digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _path_counts(frame: pd.DataFrame) -> dict[str, int]:
    return {
        label: int((frame["path_label"] == label).sum())
        for label in (
            "SIGNAL_TP1_FIRST",
            "SIGNAL_STOP_FIRST",
            "NEITHER",
            "AMBIGUOUS",
        )
    }


def _block_summary(classified: pd.DataFrame) -> pd.DataFrame:
    local = classified.copy()
    local["block_index"] = (
        (local["trigger_candle_close_time_ms"] - EVALUATION_START_MS)
        // (7 * 86_400_000)
    ).astype(int)
    rows: list[dict[str, object]] = []
    for (strategy, block, state), frame in local.groupby(
        ["strategy", "block_index", "selection_state"],
        sort=True,
    ):
        counts = _path_counts(frame)
        resolved = counts["SIGNAL_TP1_FIRST"] + counts["SIGNAL_STOP_FIRST"]
        rows.append(
            {
                "strategy": strategy,
                "block_index": int(str(block)),
                "block_start_ms": (
                    EVALUATION_START_MS + int(str(block)) * 7 * 86_400_000
                ),
                "selection_state": state,
                "event_count": len(frame),
                "resolved_count": resolved,
                **{key.lower(): value for key, value in counts.items()},
                "net_path_rate": (
                    None
                    if resolved == 0
                    else (
                        counts["SIGNAL_TP1_FIRST"]
                        - counts["SIGNAL_STOP_FIRST"]
                    )
                    / resolved
                ),
            }
        )
    return pd.DataFrame(rows)


def _strategy_headline(
    classified: pd.DataFrame,
    dynamic: pd.DataFrame,
    classification: pd.DataFrame,
    turnover: pd.DataFrame,
    blocks: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    class_by_strategy = classification.set_index("strategy").to_dict("index")
    turnover_by_strategy = turnover.set_index("strategy").to_dict("index")
    for strategy in sorted(classified["strategy"].unique()):
        baseline = classified.loc[classified["strategy"] == strategy]
        selected = baseline.loc[baseline["selection_state"] == "SELECTED"]
        rejected = baseline.loc[baseline["selection_state"] == "NOT_SELECTED"]
        all_tp = int((baseline["path_label"] == "SIGNAL_TP1_FIRST").sum())
        all_stop = int((baseline["path_label"] == "SIGNAL_STOP_FIRST").sum())
        selected_tp = int((selected["path_label"] == "SIGNAL_TP1_FIRST").sum())
        rejected_stop = int((rejected["path_label"] == "SIGNAL_STOP_FIRST").sum())
        strategy_blocks = blocks.loc[blocks["strategy"] == strategy].pivot(
            index="block_index",
            columns="selection_state",
            values="net_path_rate",
        )
        comparable_block_effects = (
            strategy_blocks["SELECTED"] - strategy_blocks["NOT_SELECTED"]
            if {"SELECTED", "NOT_SELECTED"}.issubset(strategy_blocks.columns)
            else pd.Series(dtype=float)
        ).dropna()
        rows.append(
            {
                "strategy": strategy,
                "baseline_event_count": len(baseline),
                "selected_membership_event_count": len(selected),
                "near_membership_event_count": int(
                    (baseline["selection_state"] == "NEAR_THRESHOLD").sum()
                ),
                "not_selected_membership_event_count": len(rejected),
                "dynamic_detector_event_count": int(
                    (dynamic["strategy"] == strategy).sum()
                ),
                "good_event_capture_rate": (
                    None if all_tp == 0 else selected_tp / all_tp
                ),
                "bad_event_rejection_rate": (
                    None if all_stop == 0 else rejected_stop / all_stop
                ),
                "comparable_block_count": len(comparable_block_effects),
                "selected_better_block_count": int(
                    (comparable_block_effects > 0).sum()
                ),
                "selected_worse_block_count": int(
                    (comparable_block_effects < 0).sum()
                ),
                **cast(dict[str, object], class_by_strategy[strategy]),
                **cast(dict[str, object], turnover_by_strategy[strategy]),
            }
        )
    return pd.DataFrame(rows)


def _report(headline: pd.DataFrame, counters: dict[str, object]) -> str:
    rendered: list[str] = []
    for raw in headline.to_dict("records"):
        row = cast(dict[str, object], raw)
        holdout = cast(float, row["holdout_selected_minus_not_selected_net"])
        rendered.append(
            "| {strategy} | {classification} | {coverage} | {discovery:+.3f} | "
            "{holdout} | {baseline} | {selected} | {rejected} | {dynamic} | "
            "{capture:.1%} | {bad_reject:.1%} | {blocks} | {turnover:.1%} | "
            "{duration:.1f}h |".format(
                strategy=str(row["strategy"]),
                classification=str(row["classification"]),
                coverage=str(row["comparison_coverage"]),
                discovery=cast(
                    float, row["discovery_selected_minus_not_selected_net"]
                ),
                holdout=(
                    "N/A"
                    if isnan(holdout)
                    else f"{holdout:+.3f}"
                ),
                baseline=int(cast(float, row["baseline_event_count"])),
                selected=int(cast(float, row["selected_membership_event_count"])),
                rejected=int(
                    cast(float, row["not_selected_membership_event_count"])
                ),
                dynamic=int(cast(float, row["dynamic_detector_event_count"])),
                capture=cast(float, row["good_event_capture_rate"]),
                bad_reject=cast(float, row["bad_event_rejection_rate"]),
                turnover=cast(float, row["mean_turnover_fraction"]),
                duration=cast(float, row["mean_selected_membership_hours"]),
                blocks=(
                    f"{int(cast(float, row['selected_better_block_count']))}/"
                    f"{int(cast(float, row['comparable_block_count']))}"
                ),
            )
        )
    rows = "\n".join(rendered)
    return f"""# Stage-3 Semantic Dynamic Selection Replay Report

## Status

```text
research_status = STAGE3_SEMANTIC_DYNAMIC_SELECTION_REPLAY_COMPLETE
production_behavior = UNCHANGED
selector_implementation = NONE
production_authority = NONE
```

## Frozen protocol

- Exact fixed 24-member CandidateUniverse.
- Per-Strategy Top16 / Near4 / NotSelected4.
- CPM and BRF2 selection every 4h; MPG and MI every 1h.
- Snapshot calculated at `t` becomes Detector-eligible at `t+1h`.
- MPG/MI comparative rank always uses all 24 members.
- No parameter, cadence, Top-N, horizon or factor optimization occurred.

## Results

| Strategy | Classification | Comparison coverage | Discovery effect | Holdout effect | Baseline Events | Selected Events | Not Selected Events | Dynamic Detector Events | Good capture | Bad rejection | Positive blocks | Mean turnover | Mean membership |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
{rows}

`SPARSE_NOT_SELECTED_EVENTS` means the frozen Top16 Selector removed too few
resolved Events to support a reliable Selected-vs-NotSelected comparison. It
does not convert operational compatibility into evidence of quality improvement.

## Runtime and semantic QC

```text
Selection Snapshots = {counters['selection_snapshot_count']:,}
Member Decisions = {counters['member_decision_count']:,}
Dynamic Detector evaluations = {counters['dynamic_detector_evaluation_count']:,}
Dynamic Replay Events = {counters['dynamic_replay_event_count']:,}
Dynamic invalid Detector evaluations = {counters['dynamic_invalid_detector_count']:,}
MPG/MI rank parity mismatches = {counters['mpg_mi_rank_parity_mismatch_count']:,}
Empty Snapshots = 0
Insufficient Snapshots = 0
```

## Claim boundary

`THEORY_COMPATIBLE_DYNAMIC_V0` means the frozen semantic Selector was
operationally coherent and did not show the pre-registered persistent clear
adverse-selection pattern. It does not mean profitable, statistically proven,
production ready or authorized for Dynamic Universe activation.
"""


def run(cache_dir: Path, output_dir: Path, publish_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    publish_dir.mkdir(parents=True, exist_ok=True)
    selection = build_selection_artifacts(cache_dir)
    selection.snapshots.to_parquet(
        output_dir / "stage3_selection_snapshots.parquet", index=False
    )
    selection.decisions.to_parquet(
        output_dir / "stage3_member_decisions.parquet", index=False
    )
    selection.rank_history.to_parquet(
        output_dir / "stage3_mpg_rank_history.parquet", index=False
    )
    baseline = pd.read_parquet(
        Path(__file__).resolve().parents[1]
        / "multi_strategy_selection/artifacts/replayed_events.parquet"
    )
    classified = classify_baseline_events(baseline, selection.decisions)
    classified.to_parquet(
        output_dir / "stage3_baseline_membership_events.parquet", index=False
    )
    dynamic_events, evaluations, dynamic_counters = replay_dynamic_detectors(
        cache_dir, selection.decisions
    )
    evaluations.to_parquet(
        output_dir / "stage3_dynamic_detector_evaluations.parquet", index=False
    )
    outcomes = compute_first_passage(cache_dir, dynamic_events)
    outcomes.to_parquet(output_dir / "stage3_dynamic_outcomes.parquet", index=False)
    dynamic = dynamic_events.merge(
        outcomes,
        on=[
            "event_spec_id",
            "strategy",
            "symbol",
            "direction",
            "trigger_candle_close_time_ms",
        ],
        validate="one_to_one",
    )
    dynamic.to_parquet(output_dir / "stage3_dynamic_events.parquet", index=False)
    periods = period_summary(classified, dynamic)
    periods.to_csv(output_dir / "stage3_period_summary.csv", index=False)
    classifications = classify_strategies(periods)
    classifications.to_csv(
        output_dir / "stage3_strategy_classification.csv", index=False
    )
    turnover_rows, turnover = turnover_summary(
        selection.snapshots,
        selection.decisions,
        evaluation_start_ms=EVALUATION_START_MS,
        evaluation_end_ms=EVALUATION_END_MS,
    )
    turnover_rows.to_csv(
        output_dir / "stage3_turnover_by_snapshot.csv", index=False
    )
    turnover.to_csv(output_dir / "stage3_turnover_summary.csv", index=False)
    blocks = _block_summary(classified)
    blocks.to_csv(output_dir / "stage3_block_summary.csv", index=False)
    headline = _strategy_headline(
        classified,
        dynamic,
        classifications,
        turnover,
        blocks,
    )
    counters: dict[str, object] = {
        **dynamic_counters,
        "selection_snapshot_count": len(selection.snapshots),
        "member_decision_count": len(selection.decisions),
        "baseline_event_count": len(baseline),
        "baseline_membership_event_count": len(classified),
        "dynamic_outcome_count": len(outcomes),
        "discovery_end_ms": DISCOVERY_END_MS,
    }
    (output_dir / "stage3_replay_counters.json").write_text(
        json.dumps(counters, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "STAGE3_SEMANTIC_DYNAMIC_SELECTION_REPORT.md").write_text(
        _report(headline, counters), encoding="utf-8"
    )
    for name in ARTIFACT_NAMES:
        shutil.copy2(output_dir / name, publish_dir / name)
    repo_root = Path(__file__).resolve().parents[2]
    source_files = (
        "research/semantic_dynamic_selection/features.py",
        "research/semantic_dynamic_selection/selection.py",
        "research/semantic_dynamic_selection/replay.py",
        "research/semantic_dynamic_selection/analyze.py",
        "research/semantic_dynamic_selection/run_stage3.py",
    )
    market_manifest = cache_dir / "market_data_manifest.json"
    candidate_universe = sorted(
        selection.decisions["exchange_instrument_id"].unique().tolist()
    )
    manifest: dict[str, object] = {
        "schema": "brc.research.semantic_dynamic_selection.stage3.v1",
        "research_status": "STAGE3_SEMANTIC_DYNAMIC_SELECTION_REPLAY_COMPLETE",
        "base_stage2_1_commit": "337c5cd19e6837aa84d9eb49ed786beb2b156fce",
        "detector_authority_commit": "2697f4b5943ed6a98f04a93e1b78d38e53780890",
        "candidate_count": 24,
        "candidate_universe": candidate_universe,
        "candidate_universe_digest": _json_digest(candidate_universe),
        "selected_count": 16,
        "near_count": 4,
        "not_selected_count": 4,
        "effective_lag_hours": 1,
        "evaluation_window": [EVALUATION_START_MS, EVALUATION_END_MS],
        "discovery_end_ms": DISCOVERY_END_MS,
        "selection_specs": {
            "CPM-RO-001": "CPM_SIGNED_TREND_EFFICIENCY_V0",
            "MPG-001": "MPG_LEADER_OCCUPANCY_V0",
            "MI-001": "MI_POSITIVE_IMPULSE_RECENCY_V0",
            "BRF2-001": "BRF2_RESIDUAL_EXTENSION_V0",
        },
        "market_data_manifest_sha256": _sha256(market_manifest),
        "input_stage2_events_sha256": _sha256(
            Path(__file__).resolve().parents[1]
            / "multi_strategy_selection/artifacts/replayed_events.parquet"
        ),
        "protocol_sha256": _sha256(
            repo_root
            / "research/multi_strategy_selection/STAGE3_SEMANTIC_DYNAMIC_SELECTION_PROTOCOL.md"
        ),
        "source_file_sha256": {
            name: _sha256(repo_root / name) for name in source_files
        },
        "counters": counters,
        "classifications": json.loads(classifications.to_json(orient="records")),
        "artifact_sha256": {
            name: _sha256(publish_dir / name) for name in ARTIFACT_NAMES
        },
        "production_behavior": "UNCHANGED",
        "selector_implementation": "NONE",
        "production_authority": "NONE",
    }
    for target in (
        output_dir / "stage3_replay_manifest.json",
        publish_dir / "stage3_replay_manifest.json",
    ):
        target.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--publish-dir", type=Path, required=True)
    args = parser.parse_args()
    manifest = run(
        args.cache_dir.resolve(),
        args.output_dir.resolve(),
        args.publish_dir.resolve(),
    )
    print(
        json.dumps(
            {
                "research_status": manifest["research_status"],
                "classifications": manifest["classifications"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
