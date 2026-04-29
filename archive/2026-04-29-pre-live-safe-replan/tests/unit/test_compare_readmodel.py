"""Tests for CompareReadModel — compare candidates side-by-side."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.application.readmodels.compare_readmodel import CompareReadModel


def _write_candidate(tmp: Path, name: str, best_trial: dict[str, Any] | None = None, generated_at: str = "2026-04-27T00:00:00Z") -> Path:
    """Write a candidate JSON artifact to the temp directory."""
    payload: dict[str, Any] = {
        "candidate_name": name,
        "generated_at": generated_at,
        "status": "candidate_only",
        "source_profile": {"name": "optuna_daily"},
        "git": {"commit": "abc123", "branch": "dev"},
        "job": {"objective": "maximize_sharpe"},
    }
    if best_trial is not None:
        payload["best_trial"] = best_trial
    p = tmp / f"{name}.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


TRIAL_A = {
    "trial_number": 1,
    "sharpe_ratio": 2.1,
    "total_return": 0.45,
    "max_drawdown": 0.15,
    "win_rate": 0.54,
    "total_trades": 1250,
}

TRIAL_B = {
    "trial_number": 2,
    "sharpe_ratio": 1.8,
    "total_return": 0.38,
    "max_drawdown": 0.18,
    "win_rate": 0.51,
    "total_trades": 840,
}

TRIAL_C = {
    "trial_number": 3,
    "sharpe_ratio": 1.2,
    "total_return": 0.20,
    "max_drawdown": 0.22,
    "win_rate": 0.48,
    "total_trades": 600,
}


class TestCompareReadModelEmpty:
    def test_no_candidates_returns_empty_rows(self, tmp_path: Path) -> None:
        rm = CompareReadModel(artifact_dir=tmp_path)
        result = rm.build()
        assert result.rows == []
        assert result.baseline_label == ""
        assert result.candidate_a_label == ""


class TestCompareReadModelSingleCandidate:
    def test_single_candidate_uses_as_baseline(self, tmp_path: Path) -> None:
        _write_candidate(tmp_path, "cand_alpha", TRIAL_A)
        rm = CompareReadModel(artifact_dir=tmp_path)
        result = rm.build()
        assert result.baseline_label == "cand_alpha"
        assert result.candidate_a_label == ""
        # All candidate_a values should be None since there's no second candidate
        for row in result.rows:
            assert row.candidate_a is None
            assert row.diff_a is None


class TestCompareReadModelTwoCandidates:
    def test_two_candidates_compare(self, tmp_path: Path) -> None:
        _write_candidate(tmp_path, "cand_alpha", TRIAL_A, "2026-04-27T02:00:00Z")
        _write_candidate(tmp_path, "cand_beta", TRIAL_B, "2026-04-27T01:00:00Z")
        rm = CompareReadModel(artifact_dir=tmp_path)
        result = rm.build()
        assert result.baseline_label == "cand_alpha"
        assert result.candidate_a_label == "cand_beta"
        assert result.candidate_b_label is None

        # Check a specific metric row
        sharpe_row = next(r for r in result.rows if r.metric == "Sharpe")
        assert sharpe_row.baseline == 2.1
        assert sharpe_row.candidate_a == 1.8
        assert sharpe_row.diff_a == pytest.approx(-0.3)
        assert sharpe_row.candidate_b is None
        assert sharpe_row.diff_b is None


class TestCompareReadModelThreeCandidates:
    def test_three_candidates_includes_b(self, tmp_path: Path) -> None:
        _write_candidate(tmp_path, "cand_alpha", TRIAL_A, "2026-04-27T03:00:00Z")
        _write_candidate(tmp_path, "cand_beta", TRIAL_B, "2026-04-27T02:00:00Z")
        _write_candidate(tmp_path, "cand_gamma", TRIAL_C, "2026-04-27T01:00:00Z")
        rm = CompareReadModel(artifact_dir=tmp_path)
        result = rm.build()
        assert result.candidate_b_label == "cand_gamma"

        sharpe_row = next(r for r in result.rows if r.metric == "Sharpe")
        assert sharpe_row.candidate_b == 1.2
        assert sharpe_row.diff_b is not None


class TestCompareReadModelMissingMetrics:
    def test_missing_metrics_are_null(self, tmp_path: Path) -> None:
        trial_partial = {"trial_number": 1, "total_trades": 100}
        _write_candidate(tmp_path, "cand_alpha", TRIAL_A, "2026-04-27T02:00:00Z")
        _write_candidate(tmp_path, "cand_partial", trial_partial, "2026-04-27T01:00:00Z")
        rm = CompareReadModel(artifact_dir=tmp_path)
        result = rm.build()

        sharpe_row = next(r for r in result.rows if r.metric == "Sharpe")
        assert sharpe_row.candidate_a is None
        assert sharpe_row.diff_a is None

        trades_row = next(r for r in result.rows if r.metric == "Trades")
        assert trades_row.candidate_a == 100.0

    def test_no_best_trial_all_null(self, tmp_path: Path) -> None:
        _write_candidate(tmp_path, "cand_alpha", TRIAL_A, "2026-04-27T02:00:00Z")
        _write_candidate(tmp_path, "cand_empty", None, "2026-04-27T01:00:00Z")
        rm = CompareReadModel(artifact_dir=tmp_path)
        result = rm.build()

        for row in result.rows:
            assert row.candidate_a is None
            assert row.diff_a is None


class TestCompareReadModelExplicitRefs:
    def test_explicit_refs_override_defaults(self, tmp_path: Path) -> None:
        _write_candidate(tmp_path, "cand_alpha", TRIAL_A, "2026-04-27T03:00:00Z")
        _write_candidate(tmp_path, "cand_beta", TRIAL_B, "2026-04-27T02:00:00Z")
        _write_candidate(tmp_path, "cand_gamma", TRIAL_C, "2026-04-27T01:00:00Z")
        rm = CompareReadModel(artifact_dir=tmp_path)
        result = rm.build(baseline_ref="cand_beta", candidate_a="cand_gamma")
        assert result.baseline_label == "cand_beta"
        assert result.candidate_a_label == "cand_gamma"

    def test_unknown_ref_falls_back_to_default(self, tmp_path: Path) -> None:
        _write_candidate(tmp_path, "cand_alpha", TRIAL_A, "2026-04-27T02:00:00Z")
        _write_candidate(tmp_path, "cand_beta", TRIAL_B, "2026-04-27T01:00:00Z")
        rm = CompareReadModel(artifact_dir=tmp_path)
        result = rm.build(baseline_ref="nonexistent")
        # Falls back to first candidate (newest) as baseline
        assert result.baseline_label == "cand_alpha"


class TestCompareReadModelRouteContract:
    def test_response_has_five_metric_rows(self, tmp_path: Path) -> None:
        _write_candidate(tmp_path, "cand_alpha", TRIAL_A, "2026-04-27T02:00:00Z")
        _write_candidate(tmp_path, "cand_beta", TRIAL_B, "2026-04-27T01:00:00Z")
        rm = CompareReadModel(artifact_dir=tmp_path)
        result = rm.build()
        metric_names = [r.metric for r in result.rows]
        assert metric_names == ["Total Return", "Sharpe", "Max Drawdown", "Win Rate", "Trades"]

    def test_candidate_b_missing_no_crash(self, tmp_path: Path) -> None:
        _write_candidate(tmp_path, "cand_alpha", TRIAL_A)
        rm = CompareReadModel(artifact_dir=tmp_path)
        result = rm.build()
        assert result.candidate_b_label is None
        for row in result.rows:
            assert row.candidate_b is None
            assert row.diff_b is None


class TestCompareNoSelfComparison:
    """Verify baseline, candidate_a, candidate_b are always distinct."""

    def test_baseline_is_second_candidate_no_self_compare(self, tmp_path: Path) -> None:
        """When baseline_ref points to names[1], candidate_a must not be the same."""
        _write_candidate(tmp_path, "cand_alpha", TRIAL_A, "2026-04-27T03:00:00Z")
        _write_candidate(tmp_path, "cand_beta", TRIAL_B, "2026-04-27T02:00:00Z")
        _write_candidate(tmp_path, "cand_gamma", TRIAL_C, "2026-04-27T01:00:00Z")
        rm = CompareReadModel(artifact_dir=tmp_path)
        result = rm.build(baseline_ref="cand_beta")
        assert result.baseline_label == "cand_beta"
        assert result.candidate_a_label != "cand_beta"
        assert result.candidate_a_label != ""

    def test_candidate_b_never_repeats_baseline_or_a(self, tmp_path: Path) -> None:
        _write_candidate(tmp_path, "cand_alpha", TRIAL_A, "2026-04-27T03:00:00Z")
        _write_candidate(tmp_path, "cand_beta", TRIAL_B, "2026-04-27T02:00:00Z")
        _write_candidate(tmp_path, "cand_gamma", TRIAL_C, "2026-04-27T01:00:00Z")
        rm = CompareReadModel(artifact_dir=tmp_path)
        result = rm.build()
        assert result.candidate_b_label is not None
        assert result.candidate_b_label != result.baseline_label
        assert result.candidate_b_label != result.candidate_a_label

    def test_explicit_candidate_a_same_as_baseline_declined(self, tmp_path: Path) -> None:
        """Explicitly passing candidate_a=baseline should be declined."""
        _write_candidate(tmp_path, "cand_alpha", TRIAL_A, "2026-04-27T02:00:00Z")
        _write_candidate(tmp_path, "cand_beta", TRIAL_B, "2026-04-27T01:00:00Z")
        rm = CompareReadModel(artifact_dir=tmp_path)
        result = rm.build(baseline_ref="cand_alpha", candidate_a="cand_alpha")
        assert result.candidate_a_label != "cand_alpha"

    def test_explicit_candidate_b_same_as_baseline_declined(self, tmp_path: Path) -> None:
        _write_candidate(tmp_path, "cand_alpha", TRIAL_A, "2026-04-27T03:00:00Z")
        _write_candidate(tmp_path, "cand_beta", TRIAL_B, "2026-04-27T02:00:00Z")
        _write_candidate(tmp_path, "cand_gamma", TRIAL_C, "2026-04-27T01:00:00Z")
        rm = CompareReadModel(artifact_dir=tmp_path)
        result = rm.build(baseline_ref="cand_alpha", candidate_b="cand_alpha")
        assert result.candidate_b_label != "cand_alpha"

    def test_explicit_candidate_b_same_as_a_declined(self, tmp_path: Path) -> None:
        _write_candidate(tmp_path, "cand_alpha", TRIAL_A, "2026-04-27T03:00:00Z")
        _write_candidate(tmp_path, "cand_beta", TRIAL_B, "2026-04-27T02:00:00Z")
        _write_candidate(tmp_path, "cand_gamma", TRIAL_C, "2026-04-27T01:00:00Z")
        rm = CompareReadModel(artifact_dir=tmp_path)
        result = rm.build(candidate_a="cand_beta", candidate_b="cand_beta")
        assert result.candidate_b_label != "cand_beta"

    def test_two_candidates_exhausted_no_b(self, tmp_path: Path) -> None:
        """With only 2 candidates, candidate_b should be None after excluding baseline and a."""
        _write_candidate(tmp_path, "cand_alpha", TRIAL_A, "2026-04-27T02:00:00Z")
        _write_candidate(tmp_path, "cand_beta", TRIAL_B, "2026-04-27T01:00:00Z")
        rm = CompareReadModel(artifact_dir=tmp_path)
        result = rm.build()
        assert result.candidate_b_label is None


class TestCompareNonexistentRefs:
    """Verify stable behavior when refs point to nonexistent candidates."""

    def test_nonexistent_baseline_falls_back(self, tmp_path: Path) -> None:
        _write_candidate(tmp_path, "cand_alpha", TRIAL_A, "2026-04-27T02:00:00Z")
        _write_candidate(tmp_path, "cand_beta", TRIAL_B, "2026-04-27T01:00:00Z")
        rm = CompareReadModel(artifact_dir=tmp_path)
        result = rm.build(baseline_ref="ghost", candidate_a="phantom")
        assert result.baseline_label == "cand_alpha"
        assert result.candidate_a_label == "cand_beta"
        assert len(result.rows) == 5

    def test_nonexistent_candidate_b_omitted(self, tmp_path: Path) -> None:
        _write_candidate(tmp_path, "cand_alpha", TRIAL_A, "2026-04-27T02:00:00Z")
        _write_candidate(tmp_path, "cand_beta", TRIAL_B, "2026-04-27T01:00:00Z")
        rm = CompareReadModel(artifact_dir=tmp_path)
        result = rm.build(candidate_b="phantom")
        assert result.candidate_b_label is None

    def test_all_refs_nonexistent_still_returns_valid_structure(self, tmp_path: Path) -> None:
        _write_candidate(tmp_path, "cand_alpha", TRIAL_A, "2026-04-27T02:00:00Z")
        rm = CompareReadModel(artifact_dir=tmp_path)
        result = rm.build(baseline_ref="x", candidate_a="y", candidate_b="z")
        assert result.baseline_label == "cand_alpha"
        assert len(result.rows) == 5
