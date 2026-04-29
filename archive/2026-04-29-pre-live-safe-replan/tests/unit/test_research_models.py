"""Unit tests for research_models: validation, defaults, enums."""

import pytest
from decimal import Decimal
from pydantic import ValidationError

from src.domain.research_models import (
    CandidateRecord,
    CandidateReviewRequest,
    CandidateStatus,
    CreateCandidateRequest,
    ResearchJob,
    ResearchJobAccepted,
    ResearchJobListResponse,
    ResearchJobStatus,
    ResearchRunListResponse,
    ResearchRunResult,
    ResearchSpec,
    utc_now_iso,
)


# ── helpers ──────────────────────────────────────────────────────────

def _valid_spec_kwargs(**overrides):
    base = dict(
        name="test-backtest",
        start_time_ms=1700000000000,
        end_time_ms=1700086400000,
    )
    base.update(overrides)
    return base


# ── ResearchSpec validation ──────────────────────────────────────────

class TestResearchSpec:
    def test_valid_spec_defaults(self):
        spec = ResearchSpec(**_valid_spec_kwargs())
        assert spec.kind == "backtest"
        assert spec.mode == "v3_pms"
        assert spec.limit == 9000
        assert spec.symbol == "ETH/USDT:USDT"
        assert spec.timeframe == "1h"
        assert spec.profile_name == "backtest_eth_baseline"
        assert spec.costs.initial_balance == Decimal("10000")
        assert spec.costs.slippage_rate == Decimal("0.0001")
        assert spec.costs.tp_slippage_rate == Decimal("0")
        assert spec.costs.fee_rate == Decimal("0.000405")
        assert spec.notes is None
        assert spec.runtime_overrides is None

    def test_end_time_le_start_time_rejected(self):
        with pytest.raises(ValidationError, match="end_time_ms must be greater"):
            ResearchSpec(**_valid_spec_kwargs(end_time_ms=1700000000000))

    def test_end_time_less_than_start_time_rejected(self):
        with pytest.raises(ValidationError, match="end_time_ms must be greater"):
            ResearchSpec(**_valid_spec_kwargs(end_time_ms=1699999999999))

    def test_limit_minimum(self):
        spec = ResearchSpec(**_valid_spec_kwargs(limit=10))
        assert spec.limit == 10

    def test_limit_below_minimum_rejected(self):
        with pytest.raises(ValidationError):
            ResearchSpec(**_valid_spec_kwargs(limit=9))

    def test_limit_maximum(self):
        spec = ResearchSpec(**_valid_spec_kwargs(limit=30000))
        assert spec.limit == 30000

    def test_limit_above_maximum_rejected(self):
        with pytest.raises(ValidationError):
            ResearchSpec(**_valid_spec_kwargs(limit=30001))

    def test_start_time_negative_rejected(self):
        with pytest.raises(ValidationError):
            ResearchSpec(**_valid_spec_kwargs(start_time_ms=-1))

    def test_end_time_negative_rejected(self):
        with pytest.raises(ValidationError):
            ResearchSpec(**_valid_spec_kwargs(end_time_ms=-1))

    def test_name_required(self):
        with pytest.raises(ValidationError):
            ResearchSpec(start_time_ms=100, end_time_ms=200)

    def test_name_empty_rejected(self):
        with pytest.raises(ValidationError):
            ResearchSpec(**_valid_spec_kwargs(name=""))

    def test_name_too_long_rejected(self):
        with pytest.raises(ValidationError):
            ResearchSpec(**_valid_spec_kwargs(name="x" * 121))

    def test_notes_max_length(self):
        spec = ResearchSpec(**_valid_spec_kwargs(notes="x" * 5000))
        assert len(spec.notes) == 5000

    def test_notes_too_long_rejected(self):
        with pytest.raises(ValidationError):
            ResearchSpec(**_valid_spec_kwargs(notes="x" * 5001))

    def test_mode_is_v3_pms_only(self):
        spec = ResearchSpec(**_valid_spec_kwargs())
        assert spec.mode == "v3_pms"
        # Literal["v3_pms"] means only "v3_pms" is valid
        data = spec.model_dump()
        assert data["mode"] == "v3_pms"


# ── Enums ────────────────────────────────────────────────────────────

class TestEnums:
    def test_job_status_values(self):
        assert ResearchJobStatus.PENDING.value == "PENDING"
        assert ResearchJobStatus.RUNNING.value == "RUNNING"
        assert ResearchJobStatus.SUCCEEDED.value == "SUCCEEDED"
        assert ResearchJobStatus.FAILED.value == "FAILED"
        assert ResearchJobStatus.CANCELED.value == "CANCELED"

    def test_candidate_status_values(self):
        assert CandidateStatus.DRAFT.value == "DRAFT"
        assert CandidateStatus.REVIEWED.value == "REVIEWED"
        assert CandidateStatus.REJECTED.value == "REJECTED"
        assert CandidateStatus.RECOMMENDED.value == "RECOMMENDED"


# ── ResearchJob ──────────────────────────────────────────────────────

class TestResearchJob:
    def test_create_job(self):
        spec = ResearchSpec(**_valid_spec_kwargs())
        job = ResearchJob(
            id="rj_001",
            kind="backtest",
            name="test",
            spec_ref="reports/rj_001/spec.json",
            status=ResearchJobStatus.PENDING,
            spec=spec,
        )
        assert job.id == "rj_001"
        assert job.status == ResearchJobStatus.PENDING
        assert job.run_result_id is None
        assert job.error_code is None
        assert job.progress_pct is None
        assert job.requested_by == "local"

    def test_progress_pct_bounds(self):
        spec = ResearchSpec(**_valid_spec_kwargs())
        job = ResearchJob(
            id="rj_002", kind="backtest", name="t", spec_ref="x",
            status=ResearchJobStatus.PENDING, spec=spec, progress_pct=50,
        )
        assert job.progress_pct == 50

    def test_progress_pct_above_100_rejected(self):
        spec = ResearchSpec(**_valid_spec_kwargs())
        with pytest.raises(ValidationError):
            ResearchJob(
                id="rj_003", kind="backtest", name="t", spec_ref="x",
                status=ResearchJobStatus.PENDING, spec=spec, progress_pct=101,
            )

    def test_progress_pct_negative_rejected(self):
        spec = ResearchSpec(**_valid_spec_kwargs())
        with pytest.raises(ValidationError):
            ResearchJob(
                id="rj_004", kind="backtest", name="t", spec_ref="x",
                status=ResearchJobStatus.PENDING, spec=spec, progress_pct=-1,
            )


# ── ResearchRunResult ────────────────────────────────────────────────

class TestResearchRunResult:
    def test_create_run_result(self):
        r = ResearchRunResult(
            id="rr_001",
            job_id="rj_001",
            kind="backtest",
            spec_snapshot={"symbol": "ETH/USDT:USDT"},
            summary_metrics={"total_return": 0.15},
            artifact_index={"result": "/tmp/result.json"},
        )
        assert r.id == "rr_001"
        assert r.job_id == "rj_001"
        assert r.source_profile is None


# ── CandidateRecord ─────────────────────────────────────────────────

class TestCandidateRecord:
    def test_create_candidate(self):
        c = CandidateRecord(
            id="cand_001",
            run_result_id="rr_001",
            candidate_name="ETH momentum v2",
        )
        assert c.status == CandidateStatus.DRAFT
        assert c.risks == []
        assert c.review_notes == ""

    def test_candidate_name_required(self):
        with pytest.raises(ValidationError):
            CandidateRecord(id="cand_002", run_result_id="rr_001")

    def test_candidate_name_empty_rejected(self):
        with pytest.raises(ValidationError):
            CandidateRecord(id="cand_002", run_result_id="rr_001", candidate_name="")


# ── CreateCandidateRequest / CandidateReviewRequest ──────────────────

class TestRequests:
    def test_create_candidate_request(self):
        req = CreateCandidateRequest(
            run_result_id="rr_001",
            candidate_name="test candidate",
        )
        assert req.review_notes == ""

    def test_review_request(self):
        req = CandidateReviewRequest(
            status=CandidateStatus.RECOMMENDED,
            review_notes="Looks good",
            risks=["drawdown risk"],
        )
        assert req.status == CandidateStatus.RECOMMENDED
        assert len(req.risks) == 1


# ── Response models ──────────────────────────────────────────────────

class TestResponseModels:
    def test_job_accepted(self):
        a = ResearchJobAccepted(job_id="rj_001", job_status=ResearchJobStatus.PENDING)
        assert a.status == "accepted"

    def test_job_list_response(self):
        r = ResearchJobListResponse(jobs=[], total=0, limit=100, offset=0)
        assert r.total == 0

    def test_run_list_response_empty(self):
        r = ResearchRunListResponse(runs=[], total=0, limit=50, offset=0)
        assert r.runs == []
        assert r.total == 0
        assert r.limit == 50
        assert r.offset == 0

    def test_run_list_response_with_items(self):
        run = ResearchRunResult(
            id="rr_001",
            job_id="rj_001",
            kind="backtest",
            spec_snapshot={"symbol": "ETH/USDT:USDT"},
            summary_metrics={"total_return": 0.15},
            artifact_index={"result": "/tmp/result.json"},
        )
        r = ResearchRunListResponse(runs=[run], total=1, limit=100, offset=0)
        assert len(r.runs) == 1
        assert r.runs[0].id == "rr_001"
        assert r.total == 1

    def test_run_list_response_serialization(self):
        run = ResearchRunResult(
            id="rr_ser",
            job_id="rj_ser",
            kind="backtest",
            spec_snapshot={"symbol": "BTC/USDT:USDT"},
            summary_metrics={"total_return": 0.25},
            artifact_index={"result": "/tmp/result.json"},
        )
        r = ResearchRunListResponse(runs=[run], total=1, limit=10, offset=5)
        data = r.model_dump(mode="json")
        assert data["total"] == 1
        assert data["limit"] == 10
        assert data["offset"] == 5
        assert len(data["runs"]) == 1
        assert data["runs"][0]["id"] == "rr_ser"
        assert data["runs"][0]["job_id"] == "rj_ser"


# ── utc_now_iso ──────────────────────────────────────────────────────

class TestHelpers:
    def test_utc_now_iso_returns_string(self):
        result = utc_now_iso()
        assert isinstance(result, str)
        assert "T" in result
