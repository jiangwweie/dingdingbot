from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
ARTIFACTS = ROOT / "research/semantic_dynamic_selection_stage3_1/artifacts"


def _reject_constant(value: str) -> None:
    raise ValueError(value)


def test_manifest_proves_protocol_before_results_and_binds_artifacts() -> None:
    manifest = json.loads(
        (ARTIFACTS / "stage3_1_replay_manifest.json").read_text(),
        parse_constant=_reject_constant,
    )

    assert manifest["research_status"] == (
        "STAGE3_1_FINAL_SEMANTIC_REVISION_COMPLETE"
    )
    assert manifest["stage3_authority_commit"] == (
        "28b47e6d219acf2a008aacce92be1bd140b98964"
    )
    assert manifest["protocol_commit_sha"] == (
        "9907153b94b2603535c9c846611ed90b0a2ea112"
    )
    assert manifest["pre_result_run_commit_sha"] == (
        "46d7fecc9222bbbf1e85308410be2924b34cfdff"
    )
    assert manifest["cardinalities"] == [16, 12, 8]
    assert manifest["generic_selection_implementation_authority"] == "NONE"
    assert manifest["production_dynamic_activation_authority"] == "NONE"
    for name, expected in manifest["artifact_sha256"].items():
        actual = "sha256:" + hashlib.sha256((ARTIFACTS / name).read_bytes()).hexdigest()
        assert actual == expected


def test_artifact_cardinality_and_selected_excluded_partition_are_exact() -> None:
    snapshots = pd.read_parquet(ARTIFACTS / "stage3_1_selection_snapshots.parquet")
    decisions = pd.read_parquet(ARTIFACTS / "stage3_1_member_decisions.parquet")
    baseline = pd.read_parquet(
        ARTIFACTS / "stage3_1_baseline_membership_events.parquet"
    )
    dynamic = pd.read_parquet(ARTIFACTS / "stage3_1_dynamic_events.parquet")
    outcomes = pd.read_parquet(ARTIFACTS / "stage3_1_dynamic_outcomes.parquet")

    assert len(snapshots) == 4_630
    assert len(decisions) == len(snapshots) * 24 == 111_120
    assert len(baseline) == 1_476 * 3 == 4_428
    assert len(dynamic) == len(outcomes) == 2_500
    assert set(baseline["cardinality"]) == {8, 12, 16}
    assert set(baseline["selection_cohort"]) == {"SELECTED", "EXCLUDED"}
    assert (
        baseline["selection_cohort"]
        == baseline.apply(
            lambda row: (
                "SELECTED"
                if row["selection_rank"] <= row["cardinality"]
                else "EXCLUDED"
            ),
            axis=1,
        )
    ).all()


def test_actual_mpg_mi_rank_parity_is_zero_mismatch() -> None:
    parity = pd.read_csv(ARTIFACTS / "stage3_1_rank_parity_audit.csv")

    assert set(parity["strategy"]) == {"MPG-001", "MI-001"}
    assert set(parity["cardinality"]) == {8, 12, 16}
    assert (parity["checked_count"] > 0).all()
    assert (parity["mismatch_count"] == 0).all()


def test_final_strategy_decisions_and_hysteresis_are_frozen() -> None:
    overall = pd.read_csv(ARTIFACTS / "stage3_1_overall_decision.csv").set_index(
        "strategy"
    )
    hysteresis = pd.read_csv(
        ARTIFACTS / "stage3_1_hysteresis_summary.csv"
    )

    assert overall.loc["CPM-RO-001", "recommended_entry_cardinality"] == 16
    assert overall.loc["MPG-001", "recommended_entry_cardinality"] == 12
    assert overall.loc["MI-001", "recommended_entry_cardinality"] == 16
    assert overall.loc["BRF2-001", "recommended_entry_cardinality"] == 16
    assert (overall["production_activation_eligible"] == False).all()
    mpg = hysteresis.loc[hysteresis["strategy"] == "MPG-001"].set_index("mode")
    assert float(str(mpg.loc["ENTRY_N_RETAIN_16", "mean_turnover"])) < float(
        str(mpg.loc["FIXED_TOP_N", "mean_turnover"])
    )


def test_cpm_and_mpg_final_revision_verdicts_are_explicit() -> None:
    manifest = json.loads((ARTIFACTS / "stage3_1_replay_manifest.json").read_text())

    assert manifest["cpm_revision"]["revision_removed_stage3_failure"] is True
    assert manifest["cpm_revision"]["verdict"] == (
        "CPM_THEORY_COMPATIBLE_DYNAMIC_V1"
    )
    assert manifest["mpg_revision"]["meaningful_discrimination"] is True
    assert manifest["mpg_revision"]["verdict"] == (
        "MPG_THEORY_COMPATIBLE_DYNAMIC_V1"
    )
