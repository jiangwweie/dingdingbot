"""Run Stage-3.1 after its exact protocol commit is frozen."""

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
    EVALUATION_END_MS,
    EVALUATION_START_MS,
)
from research.semantic_dynamic_selection_stage3_1.analyze import (
    build_block_summary,
    build_period_summary,
    cardinality_summary,
    cpm_revision_verdict,
    hysteresis_summary,
    mpg_discrimination_audit,
    mpg_revision_verdict,
    recommend_cardinalities,
)
from research.semantic_dynamic_selection_stage3_1.replay import (
    classify_baseline_events,
    replay_dynamic_detectors,
)
from research.semantic_dynamic_selection_stage3_1.selection import (
    SELECTION_SPECS,
    build_selection_artifacts,
)

ARTIFACT_NAMES = (
    "STAGE3_1_FINAL_SEMANTIC_REVISION_REPORT.md",
    "stage3_1_strategy_cardinality_summary.csv",
    "stage3_1_period_summary.csv",
    "stage3_1_block_summary.csv",
    "stage3_1_turnover_summary.csv",
    "stage3_1_hysteresis_summary.csv",
    "stage3_1_mpg_discrimination_audit.csv",
    "stage3_1_rank_parity_audit.csv",
    "stage3_1_overall_decision.csv",
    "stage3_1_selection_snapshots.parquet",
    "stage3_1_member_decisions.parquet",
    "stage3_1_baseline_membership_events.parquet",
    "stage3_1_dynamic_detector_evaluations.parquet",
    "stage3_1_dynamic_events.parquet",
    "stage3_1_dynamic_outcomes.parquet",
)
BASELINE_RELATIVE_PATH = (
    "research/multi_strategy_selection/artifacts/replayed_events.parquet"
)


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _is_missing(value: object) -> bool:
    return value is None or (isinstance(value, float) and isnan(value))


def _rank_parity(rank_rows: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for (strategy, cardinality), frame in rank_rows.groupby(
        ["strategy", "cardinality"], sort=True
    ):
        rows.append(
            {
                "strategy": strategy,
                "cardinality": int(str(cardinality)),
                "checked_count": len(frame),
                "mismatch_count": int((~frame["rank_match"]).sum()),
            }
        )
    return pd.DataFrame(rows)


def _turnover_summary(
    snapshots: pd.DataFrame,
    decisions: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for strategy in sorted(snapshots["strategy"].unique()):
        scoped_snapshots = snapshots.loc[
            (snapshots["strategy"] == strategy)
            & (snapshots["effective_from_ms"] >= EVALUATION_START_MS)
            & (snapshots["effective_from_ms"] < EVALUATION_END_MS)
        ].sort_values("effective_from_ms")
        for cardinality in (16, 12, 8):
            prior: set[str] | None = None
            turnovers: list[float] = []
            additions: list[int] = []
            removals: list[int] = []
            for snapshot_id in scoped_snapshots["selection_snapshot_id"]:
                frame = decisions.loc[
                    decisions["selection_snapshot_id"] == snapshot_id
                ]
                current = set(
                    frame.loc[frame["rank"] <= cardinality, "exchange_instrument_id"]
                )
                if prior is not None:
                    added = len(current - prior)
                    removed = len(prior - current)
                    additions.append(added)
                    removals.append(removed)
                    turnovers.append(added / cardinality)
                prior = current
            rows.append(
                {
                    "strategy": strategy,
                    "cardinality": cardinality,
                    "snapshot_count": len(scoped_snapshots),
                    "mean_turnover": 0 if not turnovers else sum(turnovers) / len(turnovers),
                    "p95_turnover": 0 if not turnovers else float(pd.Series(turnovers).quantile(0.95)),
                    "mean_additions": 0 if not additions else sum(additions) / len(additions),
                    "mean_removals": 0 if not removals else sum(removals) / len(removals),
                }
            )
    return pd.DataFrame(rows)


def _dynamic_outcomes(cache_dir: Path, events: pd.DataFrame) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for cardinality in (16, 12, 8):
        scoped = events.loc[events["cardinality"] == cardinality]
        outcome = compute_first_passage(cache_dir, scoped)
        outcome.insert(4, "cardinality", cardinality)
        rows.append(outcome)
    return pd.concat(rows, ignore_index=True)


def _overall_decisions(
    recommendations: pd.DataFrame,
    cpm: dict[str, object],
    mpg: dict[str, object],
) -> pd.DataFrame:
    recommendation = recommendations.set_index("strategy").to_dict("index")
    rows: list[dict[str, object]] = []
    for strategy in ("CPM-RO-001", "MPG-001", "MI-001", "BRF2-001"):
        item = cast(dict[str, object], recommendation[strategy])
        cardinality = item["recommended_entry_cardinality"]
        missing_cardinality = _is_missing(cardinality)
        evidence_status = str(item["recommendation_status"])
        selector_eligible = not missing_cardinality
        if strategy == "CPM-RO-001" and not bool(cpm["revision_removed_stage3_failure"]):
            cardinality = None
            evidence_status = str(cpm["verdict"])
            selector_eligible = False
        if strategy == "MPG-001" and not bool(mpg["meaningful_discrimination"]):
            cardinality = None
            evidence_status = str(mpg["verdict"])
            selector_eligible = False
        rows.append(
            {
                "strategy": strategy,
                "frozen_selector": SELECTION_SPECS[strategy][0],
                "recommended_entry_cardinality": cardinality,
                "retention_cardinality": (
                    None if _is_missing(cardinality) else 16
                ),
                "evidence_status": evidence_status,
                "generic_implementation_eligible": True,
                "strategy_dynamic_spec_eligible": selector_eligible,
                "production_activation_eligible": False,
            }
        )
    rows.append(
        {
            "strategy": "SOR-001",
            "frozen_selector": "EXISTING_SOR_DYNAMIC_SELECTION_V0",
            "recommended_entry_cardinality": 7,
            "retention_cardinality": 7,
            "evidence_status": "EXISTING_GOLDEN_AUTHORITY",
            "generic_implementation_eligible": True,
            "strategy_dynamic_spec_eligible": True,
            "production_activation_eligible": False,
        }
    )
    return pd.DataFrame(rows)


def _report(
    overall: pd.DataFrame,
    cardinalities: pd.DataFrame,
    cpm: dict[str, object],
    mpg: dict[str, object],
) -> str:
    rendered: list[str] = []
    for raw in overall.to_dict("records"):
        row = cast(dict[str, object], raw)
        entry = row["recommended_entry_cardinality"]
        retention = row["retention_cardinality"]
        rendered.append(
            "| {strategy} | {selector} | {entry} | {retention} | {evidence} | "
            "{eligible} | False |".format(
                strategy=str(row["strategy"]),
                selector=str(row["frozen_selector"]),
                entry="—" if _is_missing(entry) else int(cast(float, entry)),
                retention=(
                    "—" if _is_missing(retention) else int(cast(float, retention))
                ),
                evidence=str(row["evidence_status"]),
                eligible=bool(row["strategy_dynamic_spec_eligible"]),
            )
        )
    rows = "\n".join(rendered)
    sensitivity: list[str] = []
    for raw in cardinalities.to_dict("records"):
        row = cast(dict[str, object], raw)
        holdout = row["holdout_operational_effect"]
        sensitivity.append(
            "| {strategy} | Top{cardinality} | {capture:.1%} | {reject:.1%} | "
            "{retention:.1%} | {dynamic:.1%} | {discovery:+.3f} | {holdout} |".format(
                strategy=str(row["strategy"]),
                cardinality=int(cast(float, row["cardinality"])),
                capture=cast(float, row["full_good_event_capture"]),
                reject=cast(float, row["full_bad_event_rejection"]),
                retention=cast(float, row["full_opportunity_retention"]),
                dynamic=cast(float, row["dynamic_detector_event_retention"]),
                discovery=cast(float, row["discovery_operational_effect"]),
                holdout=(
                    "N/A"
                    if _is_missing(holdout)
                    else f"{cast(float, holdout):+.3f}"
                ),
            )
        )
    sensitivity_rows = "\n".join(sensitivity)
    return f"""# Stage-3.1 Final Semantic Revision Report

## Status

```text
research_status = STAGE3_1_FINAL_SEMANTIC_REVISION_COMPLETE
generic_selection_implementation_authority = NONE
production_dynamic_activation_authority = NONE
```

## Strategy decision

| Strategy | Frozen Selector | Entry N | Retain N | Evidence Status | Dynamic Spec Eligible | Production Activation |
| --- | --- | ---: | ---: | --- | --- | --- |
{rows}

## Cardinality sensitivity

| Strategy | Cardinality | Good Capture | Bad Rejection | Opportunity Retention | Dynamic Event Retention | Discovery Effect | Holdout Effect |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
{sensitivity_rows}

## CPM final revision

```text
removed_stage3_failure = {cpm['revision_removed_stage3_failure']}
verdict = {cpm['verdict']}
adverse_blocks = {cpm['adverse_block_count']} / {cpm['comparable_block_count']}
```

## MPG final revision

```text
meaningful_discrimination = {mpg['meaningful_discrimination']}
verdict = {mpg['verdict']}
```

## Claim boundary

This was the final authorized feature research. Cardinality was selected by the
pre-registered 80% Good Event Capture floor, not by maximizing net-path result.
Generic implementation remains separately gated and every Strategy may remain
Static independently.
"""


def run(
    cache_dir: Path,
    output_dir: Path,
    publish_dir: Path,
    *,
    protocol_commit_sha: str,
    run_commit_sha: str,
) -> dict[str, object]:
    if len(protocol_commit_sha) != 40 or len(run_commit_sha) != 40:
        raise ValueError("protocol and run commit SHAs must be exact")
    output_dir.mkdir(parents=True, exist_ok=True)
    publish_dir.mkdir(parents=True, exist_ok=True)
    selection = build_selection_artifacts(cache_dir)
    repo_root = Path(__file__).resolve().parents[2]
    baseline = pd.read_parquet(repo_root / BASELINE_RELATIVE_PATH)
    classified = classify_baseline_events(baseline, selection.decisions)
    dynamic_events, evaluations, rank_rows = replay_dynamic_detectors(
        cache_dir,
        selection.decisions,
        selection.rank_authority,
    )
    outcomes = _dynamic_outcomes(cache_dir, dynamic_events)
    dynamic = dynamic_events.merge(
        outcomes,
        on=[
            "event_spec_id",
            "strategy",
            "symbol",
            "direction",
            "cardinality",
            "trigger_candle_close_time_ms",
        ],
        validate="one_to_one",
    )
    periods = build_period_summary(classified)
    cardinalities = cardinality_summary(periods, dynamic)
    recommendations = recommend_cardinalities(cardinalities)
    blocks = build_block_summary(classified)
    cpm = cpm_revision_verdict(periods, blocks)
    mpg_audit = mpg_discrimination_audit(
        selection.snapshots,
        selection.decisions,
        classified,
    )
    mpg = mpg_revision_verdict(mpg_audit, cardinalities)
    overall = _overall_decisions(recommendations, cpm, mpg)
    turnover = _turnover_summary(selection.snapshots, selection.decisions)
    hysteresis = hysteresis_summary(
        selection.snapshots,
        selection.decisions,
        recommendations,
    )
    rank_parity = _rank_parity(rank_rows)
    frames = {
        "stage3_1_selection_snapshots.parquet": selection.snapshots,
        "stage3_1_member_decisions.parquet": selection.decisions,
        "stage3_1_baseline_membership_events.parquet": classified,
        "stage3_1_dynamic_detector_evaluations.parquet": evaluations,
        "stage3_1_dynamic_events.parquet": dynamic,
        "stage3_1_dynamic_outcomes.parquet": outcomes,
    }
    for name, frame in frames.items():
        frame.to_parquet(output_dir / name, index=False)
    csv_frames = {
        "stage3_1_strategy_cardinality_summary.csv": cardinalities,
        "stage3_1_period_summary.csv": periods,
        "stage3_1_block_summary.csv": blocks,
        "stage3_1_turnover_summary.csv": turnover,
        "stage3_1_hysteresis_summary.csv": hysteresis,
        "stage3_1_mpg_discrimination_audit.csv": mpg_audit,
        "stage3_1_rank_parity_audit.csv": rank_parity,
        "stage3_1_overall_decision.csv": overall,
    }
    for name, frame in csv_frames.items():
        frame.to_csv(output_dir / name, index=False)
    report_name = "STAGE3_1_FINAL_SEMANTIC_REVISION_REPORT.md"
    (output_dir / report_name).write_text(
        _report(overall, cardinalities, cpm, mpg), encoding="utf-8"
    )
    for name in ARTIFACT_NAMES:
        shutil.copy2(output_dir / name, publish_dir / name)
    source_files = (
        "research/semantic_dynamic_selection_stage3_1/core.py",
        "research/semantic_dynamic_selection_stage3_1/selection.py",
        "research/semantic_dynamic_selection_stage3_1/replay.py",
        "research/semantic_dynamic_selection_stage3_1/analyze.py",
        "research/semantic_dynamic_selection_stage3_1/run_stage3_1.py",
    )
    protocol_path = repo_root / "research/semantic_dynamic_selection_stage3_1/PROTOCOL.md"
    manifest: dict[str, object] = {
        "schema": "brc.research.semantic_dynamic_selection.stage3_1.v1",
        "research_status": "STAGE3_1_FINAL_SEMANTIC_REVISION_COMPLETE",
        "stage3_authority_commit": "28b47e6d219acf2a008aacce92be1bd140b98964",
        "protocol_commit_sha": protocol_commit_sha,
        "pre_result_run_commit_sha": run_commit_sha,
        "protocol_sha256": _sha256(protocol_path),
        "market_data_manifest_sha256": _sha256(
            cache_dir / "market_data_manifest.json"
        ),
        "source_file_sha256": {
            name: _sha256(repo_root / name) for name in source_files
        },
        "cardinalities": [16, 12, 8],
        "recommendations": json.loads(recommendations.to_json(orient="records")),
        "cpm_revision": cpm,
        "mpg_revision": mpg,
        "rank_parity": json.loads(rank_parity.to_json(orient="records")),
        "overall": json.loads(overall.to_json(orient="records")),
        "artifact_sha256": {
            name: _sha256(publish_dir / name) for name in ARTIFACT_NAMES
        },
        "generic_selection_design_authority": (
            "ALLOWED_FOR_ELIGIBLE_STRATEGIES"
        ),
        "generic_selection_implementation_authority": "NONE",
        "production_dynamic_activation_authority": "NONE",
    }
    for target in (
        output_dir / "stage3_1_replay_manifest.json",
        publish_dir / "stage3_1_replay_manifest.json",
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
    parser.add_argument("--protocol-commit-sha", required=True)
    parser.add_argument("--run-commit-sha", required=True)
    args = parser.parse_args()
    manifest = run(
        args.cache_dir.resolve(),
        args.output_dir.resolve(),
        args.publish_dir.resolve(),
        protocol_commit_sha=args.protocol_commit_sha,
        run_commit_sha=args.run_commit_sha,
    )
    print(json.dumps(manifest["overall"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
