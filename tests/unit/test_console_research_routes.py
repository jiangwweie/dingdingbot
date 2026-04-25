"""Unit tests for Console Research routes (v1 readonly API - third batch).

Covers:
- candidate detail: normal read, missing candidate, corrupt JSON, metadata block
- replay context: normal extraction, missing candidate, metadata block
- review summary: gate calculation, boundary params, missing candidate
- config snapshot: with provider, without provider, provider error, identity/backend/source_of_truth_hints
"""

from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

import pytest

from src.application.readmodels.candidate_service import CandidateArtifactService
from src.application.readmodels.runtime_config_snapshot import RuntimeConfigSnapshotReadModel


def _write_candidate_json(tmpdir: str, name: str, payload: dict) -> Path:
    path = Path(tmpdir) / f"{name}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    return path


def _make_valid_candidate(
    candidate_name: str = "test_candidate_001",
    total_trades: int = 150,
    sharpe_ratio: float = 1.2,
    total_return: str = "0.45",
    max_drawdown: str = "0.20",
    win_rate: float = 0.55,
    sortino_ratio: float | None = 0.8,
    ema_period: int = 50,
) -> dict:
    return {
        "artifact_version": 1,
        "candidate_name": candidate_name,
        "generated_at": "2026-04-24T07:44:44.409134+00:00",
        "status": "candidate_only",
        "promotion_policy": "manual_review_required",
        "reproduce_cmd": f"PYTHONPATH=. python scripts/replay_optuna_candidate.py --candidate reports/optuna_candidates/{candidate_name}.json",
        "source_profile": {"name": "sim1_eth_runtime", "config_hash": "abc123", "version": 1},
        "git": {"branch": "dev", "commit": "41ed2f7e53c8", "is_dirty": False},
        "job": {"job_id": "opt_test", "objective": "sharpe", "n_trials": 30, "status": "completed",
                "symbol": "ETH/USDT:USDT", "timeframe": "1h",
                "start_time": 1704067200000, "end_time": 1735689599000},
        "best_trial": {
            "trial_number": 2,
            "completed_at": "2026-04-24T07:44:42Z",
            "objective_value": 1.2,
            "params": {"ema_period": ema_period, "max_atr_ratio": "0.01", "min_distance_pct": "0.005"},
            "sharpe_ratio": sharpe_ratio,
            "sortino_ratio": sortino_ratio,
            "total_return": total_return,
            "max_drawdown": max_drawdown,
            "total_trades": total_trades,
            "win_rate": win_rate,
            "winning_trades": 80,
            "pnl_dd_ratio": None,
        },
        "top_trials": [
            {
                "trial_number": 1,
                "completed_at": "2026-04-24T07:44:40Z",
                "objective_value": 0.9,
                "params": {"ema_period": 60, "max_atr_ratio": "0.015", "min_distance_pct": "0.008"},
                "sharpe_ratio": 0.9,
                "sortino_ratio": 0.6,
                "total_return": "0.30",
                "max_drawdown": "0.18",
                "total_trades": 120,
                "win_rate": 0.50,
                "winning_trades": 60,
                "pnl_dd_ratio": None,
            }
        ],
        "constraints": {"allowed_directions": ["LONG"], "random_seed": None, "same_bar_policy": "pessimistic"},
        "fixed_params": {},
        "runtime_overrides": {"ema_period": ema_period, "max_atr_ratio": "0.01", "min_distance_pct": "0.005"},
        "resolved_request": {
            "mode": "v3_pms", "symbol": "ETH/USDT:USDT", "timeframe": "1h",
            "initial_balance": "10000", "fee_rate": "0.0004",
        },
    }


# ============================================================
# Candidate Detail Tests
# ============================================================


def test_candidate_detail_normal():
    with TemporaryDirectory() as tmpdir:
        payload = _make_valid_candidate()
        _write_candidate_json(tmpdir, "test_candidate_001", payload)
        service = CandidateArtifactService(artifact_dir=Path(tmpdir))

        result = service.get_candidate_detail("test_candidate_001")

        assert result is not None
        assert result.candidate_name == "test_candidate_001"
        assert result.best_trial is not None
        assert result.best_trial.trial_number == 2
        assert result.best_trial.sharpe_ratio == 1.2
        assert result.best_trial.total_trades == 150
        assert len(result.top_trials) == 1
        assert result.top_trials[0].trial_number == 1
        assert result.reproduce_cmd.startswith("PYTHONPATH=.")
        assert result.constraints["allowed_directions"] == ["LONG"]
        assert result.resolved_request["mode"] == "v3_pms"
        assert result.runtime_overrides["ema_period"] == 50


def test_candidate_detail_metadata_block():
    """Candidate detail must include metadata block per v1 contract."""
    with TemporaryDirectory() as tmpdir:
        payload = _make_valid_candidate()
        _write_candidate_json(tmpdir, "test_candidate_001", payload)
        service = CandidateArtifactService(artifact_dir=Path(tmpdir))

        result = service.get_candidate_detail("test_candidate_001")

        assert result is not None
        meta = result.metadata
        assert meta.candidate_name == "test_candidate_001"
        assert meta.generated_at == "2026-04-24T07:44:44.409134+00:00"
        assert meta.source_profile["name"] == "sim1_eth_runtime"
        assert meta.git["branch"] == "dev"
        assert meta.objective == "sharpe"
        assert meta.status == "candidate_only"


def test_candidate_detail_legacy_compat():
    """Legacy top-level fields should still be populated for backward compat."""
    with TemporaryDirectory() as tmpdir:
        payload = _make_valid_candidate()
        _write_candidate_json(tmpdir, "test_candidate_001", payload)
        service = CandidateArtifactService(artifact_dir=Path(tmpdir))

        result = service.get_candidate_detail("test_candidate_001")

        assert result is not None
        assert result.generated_at == "2026-04-24T07:44:44.409134+00:00"
        assert result.source_profile["name"] == "sim1_eth_runtime"
        assert result.git["branch"] == "dev"
        assert result.objective == "sharpe"
        assert result.status == "candidate_only"


def test_candidate_detail_not_found():
    with TemporaryDirectory() as tmpdir:
        service = CandidateArtifactService(artifact_dir=Path(tmpdir))
        result = service.get_candidate_detail("nonexistent")
        assert result is None


def test_candidate_detail_corrupt_json():
    with TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "bad_candidate.json"
        path.write_text("{invalid json", encoding="utf-8")
        service = CandidateArtifactService(artifact_dir=Path(tmpdir))
        result = service.get_candidate_detail("bad_candidate")
        assert result is None


def test_candidate_detail_missing_directory():
    service = CandidateArtifactService(artifact_dir=Path("/nonexistent/path"))
    result = service.get_candidate_detail("any")
    assert result is None


def test_candidate_detail_null_best_trial():
    with TemporaryDirectory() as tmpdir:
        payload = _make_valid_candidate()
        payload["best_trial"] = None
        _write_candidate_json(tmpdir, "null_trial", payload)
        service = CandidateArtifactService(artifact_dir=Path(tmpdir))

        result = service.get_candidate_detail("null_trial")

        assert result is not None
        assert result.best_trial is None


# ============================================================
# Replay Context Tests
# ============================================================


def test_replay_context_normal():
    with TemporaryDirectory() as tmpdir:
        payload = _make_valid_candidate()
        _write_candidate_json(tmpdir, "test_candidate_001", payload)
        service = CandidateArtifactService(artifact_dir=Path(tmpdir))

        result = service.get_replay_context("test_candidate_001")

        assert result is not None
        assert result.candidate_name == "test_candidate_001"
        assert result.reproduce_cmd.startswith("PYTHONPATH=.")
        assert result.resolved_request["mode"] == "v3_pms"
        assert result.runtime_overrides["ema_period"] == 50


def test_replay_context_metadata_block():
    """Replay context must include metadata block per v1 contract."""
    with TemporaryDirectory() as tmpdir:
        payload = _make_valid_candidate()
        _write_candidate_json(tmpdir, "test_candidate_001", payload)
        service = CandidateArtifactService(artifact_dir=Path(tmpdir))

        result = service.get_replay_context("test_candidate_001")

        assert result is not None
        meta = result.metadata
        assert meta.candidate_name == "test_candidate_001"
        assert meta.generated_at == "2026-04-24T07:44:44.409134+00:00"
        assert meta.source_profile["name"] == "sim1_eth_runtime"
        assert meta.git["branch"] == "dev"
        assert meta.objective == "sharpe"
        assert meta.status == "candidate_only"


def test_replay_context_legacy_compat():
    """Legacy generated_at field should still be populated for backward compat."""
    with TemporaryDirectory() as tmpdir:
        payload = _make_valid_candidate()
        _write_candidate_json(tmpdir, "test_candidate_001", payload)
        service = CandidateArtifactService(artifact_dir=Path(tmpdir))

        result = service.get_replay_context("test_candidate_001")

        assert result is not None
        assert result.generated_at == "2026-04-24T07:44:44.409134+00:00"


def test_replay_context_not_found():
    with TemporaryDirectory() as tmpdir:
        service = CandidateArtifactService(artifact_dir=Path(tmpdir))
        result = service.get_replay_context("nonexistent")
        assert result is None


def test_replay_context_missing_fields():
    with TemporaryDirectory() as tmpdir:
        payload = {"candidate_name": "minimal", "generated_at": "2026-01-01T00:00:00Z"}
        _write_candidate_json(tmpdir, "minimal", payload)
        service = CandidateArtifactService(artifact_dir=Path(tmpdir))

        result = service.get_replay_context("minimal")

        assert result is not None
        assert result.candidate_name == "minimal"
        assert result.reproduce_cmd == ""
        assert result.resolved_request == {}
        assert result.runtime_overrides == {}
        # metadata should still be populated with defaults
        assert result.metadata.candidate_name == "minimal"
        assert result.metadata.generated_at == "2026-01-01T00:00:00Z"


# ============================================================
# Review Summary Tests
# ============================================================


def test_review_summary_pass_strict():
    with TemporaryDirectory() as tmpdir:
        payload = _make_valid_candidate()  # meets all strict thresholds
        _write_candidate_json(tmpdir, "strict_pass", payload)
        service = CandidateArtifactService(artifact_dir=Path(tmpdir))

        result = service.get_review_summary("strict_pass")

        assert result is not None
        assert result.review_status == "PASS_STRICT"
        assert result.strict_gate_result == "PASSED"
        assert len(result.strict_v1_checklist) == 6
        assert all(c.passed for c in result.strict_v1_checklist)
        assert "6/6 strict gates passed" in result.summary


def test_review_summary_reject():
    with TemporaryDirectory() as tmpdir:
        payload = _make_valid_candidate(total_trades=10, sharpe_ratio=0.1, total_return="0.01",
                                        max_drawdown="0.50", win_rate=0.2)
        _write_candidate_json(tmpdir, "reject_candidate", payload)
        service = CandidateArtifactService(artifact_dir=Path(tmpdir))

        result = service.get_review_summary("reject_candidate")

        assert result is not None
        assert result.review_status == "REJECT"
        assert result.strict_gate_result == "FAILED"
        failed_gates = [c for c in result.strict_v1_checklist if not c.passed]
        assert len(failed_gates) > 0


def test_review_summary_boundary_params():
    with TemporaryDirectory() as tmpdir:
        payload = _make_valid_candidate(ema_period=40)
        _write_candidate_json(tmpdir, "boundary_candidate", payload)
        service = CandidateArtifactService(artifact_dir=Path(tmpdir))

        result = service.get_review_summary("boundary_candidate")

        assert result is not None
        assert "parameter_near_boundary" in result.warnings
        assert "ema_period" in result.params_at_boundary
        boundary_gate = [c for c in result.strict_v1_checklist if c.gate == "no_boundary_params"]
        assert len(boundary_gate) == 1
        assert not boundary_gate[0].passed


def test_review_summary_not_found():
    with TemporaryDirectory() as tmpdir:
        service = CandidateArtifactService(artifact_dir=Path(tmpdir))
        result = service.get_review_summary("nonexistent")
        assert result is None


def test_review_summary_checklist_structure():
    with TemporaryDirectory() as tmpdir:
        payload = _make_valid_candidate()
        _write_candidate_json(tmpdir, "checklist_test", payload)
        service = CandidateArtifactService(artifact_dir=Path(tmpdir))

        result = service.get_review_summary("checklist_test")

        assert result is not None
        gates = [c.gate for c in result.strict_v1_checklist]
        assert gates == ["total_trades", "sharpe_ratio", "total_return", "max_drawdown", "win_rate", "no_boundary_params"]
        for c in result.strict_v1_checklist:
            assert c.threshold is not None
            assert c.actual is not None


# ============================================================
# Config Snapshot Tests
# ============================================================


def test_config_snapshot_with_provider():
    read_model = RuntimeConfigSnapshotReadModel()
    provider = MagicMock()
    provider.to_safe_summary.return_value = {
        "profile_name": "sim1_eth_runtime",
        "version": 3,
        "config_hash": "abc123def",
        "environment": {"exchange_name": "binance", "exchange_testnet": True},
        "market": {"primary_symbol": "ETH/USDT:USDT"},
        "strategy": {"allowed_directions": ["LONG"]},
        "risk": {"max_loss_percent": "0.01"},
        "execution": {"order_strategy": {}},
    }

    result = read_model.build(runtime_config_provider=provider)

    # v1 contract: identity block
    assert result.identity.profile == "sim1_eth_runtime"
    assert result.identity.version == 3
    assert result.identity.hash == "abc123def"
    # v1 contract: backend block
    assert result.backend["exchange_name"] == "binance"
    assert result.backend["exchange_testnet"] is True
    # v1 contract: source_of_truth_hints
    assert len(result.source_of_truth_hints) > 0
    assert any("config_provider" in h for h in result.source_of_truth_hints)
    # market/strategy/risk/execution still present
    assert result.market["primary_symbol"] == "ETH/USDT:USDT"
    assert result.strategy["allowed_directions"] == ["LONG"]
    # Legacy compat fields
    assert result.profile == "sim1_eth_runtime"
    assert result.version == 3
    assert result.hash == "abc123def"
    assert result.environment["exchange_name"] == "binance"


def test_config_snapshot_identity_backend_hints():
    """Verify all v1 contract fields: identity, backend, source_of_truth_hints."""
    read_model = RuntimeConfigSnapshotReadModel()
    provider = MagicMock()
    provider.to_safe_summary.return_value = {
        "profile_name": "sim1_eth_runtime",
        "version": 3,
        "config_hash": "abc123def",
        "environment": {"exchange_name": "binance", "exchange_testnet": False},
        "market": {},
        "strategy": {"allowed_directions": ["LONG"]},
        "risk": {"max_loss_percent": "0.01"},
        "execution": {"order_strategy": {}},
    }

    result = read_model.build(runtime_config_provider=provider)

    # identity
    assert result.identity.profile == "sim1_eth_runtime"
    assert result.identity.version == 3
    assert result.identity.hash == "abc123def"
    # backend
    assert result.backend["exchange_name"] == "binance"
    assert result.backend["exchange_testnet"] is False
    # source_of_truth_hints
    hints = result.source_of_truth_hints
    assert "config_provider:runtime_profile:sim1_eth_runtime" in hints
    assert "strategy:resolved_from_profile" in hints
    assert "risk:resolved_from_profile" in hints
    assert "execution:resolved_from_profile" in hints


def test_config_snapshot_no_provider():
    read_model = RuntimeConfigSnapshotReadModel()
    result = read_model.build(runtime_config_provider=None)

    # identity block must exist even without provider
    assert result.identity.profile == "unavailable"
    assert result.identity.version == 0
    assert result.identity.hash == ""
    assert result.source_of_truth_hints == ["no_provider"]
    # Legacy compat
    assert result.profile == "unavailable"
    assert result.version == 0
    assert result.hash == ""


def test_config_snapshot_provider_error():
    read_model = RuntimeConfigSnapshotReadModel()
    provider = MagicMock()
    provider.to_safe_summary.side_effect = RuntimeError("broken")

    result = read_model.build(runtime_config_provider=provider)

    # identity block must exist even on error
    assert result.identity.profile == "error"
    assert result.identity.version == 0
    assert result.source_of_truth_hints == ["provider_error"]
    # Legacy compat
    assert result.profile == "error"
    assert result.version == 0
