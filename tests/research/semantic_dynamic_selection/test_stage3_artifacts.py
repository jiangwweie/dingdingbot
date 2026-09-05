from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
ARTIFACTS = ROOT / "research/semantic_dynamic_selection/artifacts"


def _reject_non_json_constant(value: str) -> None:
    raise ValueError(f"non-JSON constant: {value}")


def test_stage3_manifest_is_strict_and_binds_all_artifacts() -> None:
    manifest = json.loads(
        (ARTIFACTS / "stage3_replay_manifest.json").read_text(),
        parse_constant=_reject_non_json_constant,
    )

    assert manifest["research_status"] == (
        "STAGE3_SEMANTIC_DYNAMIC_SELECTION_REPLAY_COMPLETE"
    )
    assert manifest["candidate_count"] == 24
    assert len(manifest["candidate_universe"]) == 24
    assert manifest["selected_count"] == 16
    assert manifest["near_count"] == manifest["not_selected_count"] == 4
    assert manifest["effective_lag_hours"] == 1
    assert manifest["production_behavior"] == "UNCHANGED"
    assert manifest["selector_implementation"] == "NONE"
    assert manifest["production_authority"] == "NONE"
    for name, expected in manifest["artifact_sha256"].items():
        actual = "sha256:" + hashlib.sha256((ARTIFACTS / name).read_bytes()).hexdigest()
        assert actual == expected


def test_selection_snapshots_have_exact_16_4_4_cardinality_and_one_hour_lag() -> None:
    snapshots = pd.read_parquet(ARTIFACTS / "stage3_selection_snapshots.parquet")
    decisions = pd.read_parquet(ARTIFACTS / "stage3_member_decisions.parquet")

    assert len(snapshots) == 4_630
    assert len(decisions) == len(snapshots) * 24 == 111_120
    assert (
        snapshots["effective_from_ms"] - snapshots["feature_cutoff_at_ms"]
        == 3_600_000
    ).all()
    counts = (
        decisions.groupby(["selection_snapshot_id", "member_state"])
        .size()
        .unstack(fill_value=0)
    )
    assert (counts["SELECTED"] == 16).all()
    assert (counts["NEAR_THRESHOLD"] == 4).all()
    assert (counts["NOT_SELECTED"] == 4).all()


def test_dynamic_detector_replay_uses_only_previously_selected_members() -> None:
    baseline = pd.read_parquet(
        ARTIFACTS / "stage3_baseline_membership_events.parquet"
    )
    evaluations = pd.read_parquet(
        ARTIFACTS / "stage3_dynamic_detector_evaluations.parquet"
    )
    dynamic = pd.read_parquet(ARTIFACTS / "stage3_dynamic_events.parquet")
    outcomes = pd.read_parquet(ARTIFACTS / "stage3_dynamic_outcomes.parquet")

    assert len(baseline) == 1_476
    assert len(evaluations) == 47_616
    assert len(dynamic) == len(outcomes) == 1_163
    assert (
        baseline["active_selection_cutoff_ms"]
        < baseline["trigger_candle_close_time_ms"]
    ).all()
    assert (evaluations["selection_rank"] <= 16).all()
    assert (dynamic["selection_rank"] <= 16).all()


def test_stage3_classifications_preserve_cpm_revision_and_sparse_mpg_mi_evidence() -> None:
    classification = pd.read_csv(
        ARTIFACTS / "stage3_strategy_classification.csv"
    ).set_index("strategy")

    assert classification.loc["CPM-RO-001", "classification"] == "REVISE_ONCE"
    assert classification.loc["BRF2-001", "classification"] == (
        "THEORY_COMPATIBLE_DYNAMIC_V0"
    )
    assert classification.loc["MPG-001", "comparison_coverage"] == (
        "SPARSE_NOT_SELECTED_EVENTS"
    )
    assert classification.loc["MI-001", "comparison_coverage"] == (
        "SPARSE_NOT_SELECTED_EVENTS"
    )


def test_mpg_mi_comparison_rank_parity_and_detector_geometry_are_clean() -> None:
    counters = json.loads((ARTIFACTS / "stage3_replay_counters.json").read_text())
    dynamic = pd.read_parquet(ARTIFACTS / "stage3_dynamic_events.parquet")

    assert counters["mpg_mi_rank_parity_mismatch_count"] == 0
    assert counters["dynamic_invalid_detector_count"] == 0
    assert (dynamic["event_geometry_status"] == "VALID").all()
