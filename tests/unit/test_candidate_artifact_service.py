"""Unit tests for CandidateArtifactService (v1 readonly API)."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from src.application.readmodels.candidate_service import CandidateArtifactService


def _write_candidate_json(path: Path, payload: dict) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle)


def _make_valid_candidate() -> dict:
    return {
        "candidate_name": "test_candidate_001",
        "generated_at": "2026-04-25T10:00:00Z",
        "source_profile": {"name": "sim1_eth"},
        "git": {"commit": "abc123def456"},
        "job": {"objective": "sharpe"},
        "best_trial": {
            "total_trades": 120,
            "sharpe_ratio": 1.5,
            "total_return": 0.45,
            "max_drawdown": 0.20,
            "win_rate": 0.50,
            "sortino_ratio": 2.0,
            "params": {
                "ema_period": 60,
                "max_atr_ratio": 0.015,
                "min_distance_pct": 0.008,
            },
        },
    }


# ============================================================
# List Candidates Tests
# ============================================================


def test_list_candidates_normal():
    with TemporaryDirectory() as tmpdir:
        artifact_dir = Path(tmpdir)
        service = CandidateArtifactService(artifact_dir=artifact_dir)

        candidate1 = _make_valid_candidate()
        candidate1["candidate_name"] = "candidate_001"
        _write_candidate_json(artifact_dir / "candidate_001.json", candidate1)

        candidate2 = _make_valid_candidate()
        candidate2["candidate_name"] = "candidate_002"
        candidate2["best_trial"]["sharpe_ratio"] = 0.6
        candidate2["best_trial"]["total_return"] = 0.12
        _write_candidate_json(artifact_dir / "candidate_002.json", candidate2)

        items = service.list_candidates()

        assert len(items) == 2
        # Should be sorted by generated_at descending (both have same timestamp, so order may vary)
        names = {item.candidate_name for item in items}
        assert names == {"candidate_001", "candidate_002"}


def test_list_candidates_empty_directory():
    with TemporaryDirectory() as tmpdir:
        artifact_dir = Path(tmpdir)
        service = CandidateArtifactService(artifact_dir=artifact_dir)

        items = service.list_candidates()

        assert items == []


def test_list_candidates_missing_directory():
    service = CandidateArtifactService(artifact_dir=Path("/nonexistent/path"))

    items = service.list_candidates()

    assert items == []


def test_list_candidates_skips_bad_json():
    with TemporaryDirectory() as tmpdir:
        artifact_dir = Path(tmpdir)
        service = CandidateArtifactService(artifact_dir=artifact_dir)

        # Valid candidate
        candidate = _make_valid_candidate()
        _write_candidate_json(artifact_dir / "good.json", candidate)

        # Corrupted JSON
        bad_path = artifact_dir / "bad.json"
        with bad_path.open("w", encoding="utf-8") as handle:
            handle.write("{ invalid json }")

        items = service.list_candidates()

        assert len(items) == 1
        assert items[0].candidate_name == "test_candidate_001"


def test_list_candidates_skips_non_dict():
    with TemporaryDirectory() as tmpdir:
        artifact_dir = Path(tmpdir)
        service = CandidateArtifactService(artifact_dir=artifact_dir)

        # Valid candidate
        candidate = _make_valid_candidate()
        _write_candidate_json(artifact_dir / "good.json", candidate)

        # Non-dict JSON (array)
        bad_path = artifact_dir / "bad.json"
        with bad_path.open("w", encoding="utf-8") as handle:
            json.dump([1, 2, 3], handle)

        items = service.list_candidates()

        assert len(items) == 1


# ============================================================
# Review Status Tests
# ============================================================


def test_review_status_pass_strict():
    with TemporaryDirectory() as tmpdir:
        artifact_dir = Path(tmpdir)
        service = CandidateArtifactService(artifact_dir=artifact_dir)

        candidate = _make_valid_candidate()
        _write_candidate_json(artifact_dir / "candidate.json", candidate)

        items = service.list_candidates()

        assert len(items) == 1
        assert items[0].review_status == "PASS_STRICT"
        assert items[0].strict_gate_result == "PASSED"
        assert items[0].warnings == []


def test_review_status_pass_strict_with_warnings():
    with TemporaryDirectory() as tmpdir:
        artifact_dir = Path(tmpdir)
        service = CandidateArtifactService(artifact_dir=artifact_dir)

        candidate = _make_valid_candidate()
        candidate["best_trial"]["sortino_ratio"] = 0  # Trigger warning
        _write_candidate_json(artifact_dir / "candidate.json", candidate)

        items = service.list_candidates()

        assert len(items) == 1
        assert items[0].review_status == "PASS_STRICT_WITH_WARNINGS"
        assert items[0].strict_gate_result == "PASSED"
        assert "sortino_missing_or_suspect" in items[0].warnings


def test_review_status_pass_loose():
    with TemporaryDirectory() as tmpdir:
        artifact_dir = Path(tmpdir)
        service = CandidateArtifactService(artifact_dir=artifact_dir)

        candidate = _make_valid_candidate()
        candidate["best_trial"]["sharpe_ratio"] = 0.6
        candidate["best_trial"]["total_return"] = 0.12
        _write_candidate_json(artifact_dir / "candidate.json", candidate)

        items = service.list_candidates()

        assert len(items) == 1
        assert items[0].review_status == "PASS_LOOSE"
        assert items[0].strict_gate_result == "FAILED"


def test_review_status_reject():
    with TemporaryDirectory() as tmpdir:
        artifact_dir = Path(tmpdir)
        service = CandidateArtifactService(artifact_dir=artifact_dir)

        candidate = _make_valid_candidate()
        candidate["best_trial"]["sharpe_ratio"] = 0.3
        candidate["best_trial"]["total_return"] = 0.05
        _write_candidate_json(artifact_dir / "candidate.json", candidate)

        items = service.list_candidates()

        assert len(items) == 1
        assert items[0].review_status == "REJECT"
        assert items[0].strict_gate_result == "FAILED"


def test_parameter_near_boundary_warning():
    with TemporaryDirectory() as tmpdir:
        artifact_dir = Path(tmpdir)
        service = CandidateArtifactService(artifact_dir=artifact_dir)

        candidate = _make_valid_candidate()
        candidate["best_trial"]["params"]["ema_period"] = 40  # Boundary value
        _write_candidate_json(artifact_dir / "candidate.json", candidate)

        items = service.list_candidates()

        assert len(items) == 1
        # Should fail strict gate due to boundary
        assert items[0].review_status == "PASS_LOOSE"
        assert "parameter_near_boundary" in items[0].warnings


def test_missing_fields_graceful_fallback():
    with TemporaryDirectory() as tmpdir:
        artifact_dir = Path(tmpdir)
        service = CandidateArtifactService(artifact_dir=artifact_dir)

        # Minimal candidate with missing optional fields
        candidate = {
            "candidate_name": "minimal",
            "generated_at": "2026-04-25T10:00:00Z",
            "best_trial": {
                "total_trades": 50,
                "sharpe_ratio": 0.6,
                "total_return": 0.12,
                "max_drawdown": 0.25,
                "win_rate": 0.45,
            },
        }
        _write_candidate_json(artifact_dir / "minimal.json", candidate)

        items = service.list_candidates()

        assert len(items) == 1
        assert items[0].candidate_name == "minimal"
        assert items[0].source_profile == "unknown"
        assert items[0].git_commit == ""
        assert items[0].objective == "unknown"


def test_limit_parameter():
    with TemporaryDirectory() as tmpdir:
        artifact_dir = Path(tmpdir)
        service = CandidateArtifactService(artifact_dir=artifact_dir)

        # Create 5 candidates
        for i in range(5):
            candidate = _make_valid_candidate()
            candidate["candidate_name"] = f"candidate_{i:03d}"
            _write_candidate_json(artifact_dir / f"candidate_{i:03d}.json", candidate)

        items = service.list_candidates(limit=3)

        assert len(items) == 3
