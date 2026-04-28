"""API smoke tests for Research Control Plane endpoints.

Uses FastAPI TestClient with a mocked service layer so no real
exchange/backtest is triggered.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from fastapi.testclient import TestClient

from src.domain.research_models import (
    CandidateRecord,
    CandidateStatus,
    ResearchJob,
    ResearchJobAccepted,
    ResearchJobListResponse,
    ResearchJobStatus,
    ResearchRunListResponse,
    ResearchRunResult,
    ResearchSpec,
)
from src.infrastructure.research_repository import ResearchRepository


# ── helpers ──────────────────────────────────────────────────────────

def _spec_dict(**overrides):
    base = dict(
        name="api-test",
        start_time_ms=1700000000000,
        end_time_ms=1700086400000,
    )
    base.update(overrides)
    return base


def _make_job(job_id="rj_api1", status=ResearchJobStatus.PENDING):
    return ResearchJob(
        id=job_id,
        kind="backtest",
        name="api-test-job",
        spec_ref=f"reports/{job_id}/spec.json",
        status=status,
        spec=ResearchSpec(**_spec_dict()),
    )


def _make_run_result(result_id="rr_api1", job_id="rj_api1"):
    return ResearchRunResult(
        id=result_id,
        job_id=job_id,
        kind="backtest",
        spec_snapshot={"symbol": "ETH/USDT:USDT"},
        summary_metrics={"total_return": 0.12},
        artifact_index={"result": "/tmp/result.json"},
    )


def _make_candidate(candidate_id="cand_api1", run_result_id="rr_api1"):
    return CandidateRecord(
        id=candidate_id,
        run_result_id=run_result_id,
        candidate_name="api test candidate",
    )


# ── fixture: TestClient with mocked _build_service ───────────────────

@pytest.fixture
def client():
    from src.interfaces.api import app
    return TestClient(app, raise_server_exceptions=False)


def _mock_service():
    svc = AsyncMock()
    svc.repository = AsyncMock()
    svc.repository.close = AsyncMock()
    return svc


# ── GET /api/research/jobs ───────────────────────────────────────────

class TestListJobs:
    def test_empty_list(self, client):
        svc = _mock_service()
        svc.list_jobs.return_value = ResearchJobListResponse(
            jobs=[], total=0, limit=100, offset=0,
        )
        with patch("src.interfaces.api_research_jobs._build_service", return_value=svc):
            resp = client.get("/api/research/jobs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["jobs"] == []

    def test_with_status_filter(self, client):
        svc = _mock_service()
        svc.list_jobs.return_value = ResearchJobListResponse(
            jobs=[], total=0, limit=100, offset=0,
        )
        with patch("src.interfaces.api_research_jobs._build_service", return_value=svc):
            resp = client.get("/api/research/jobs?status=PENDING")
        assert resp.status_code == 200
        svc.list_jobs.assert_called_once()


# ── POST /api/research/jobs/backtest ─────────────────────────────────

class TestCreateBacktestJob:
    def test_create_job(self, client):
        svc = _mock_service()
        job = _make_job("rj_create_api")
        svc.create_backtest_job.return_value = job
        with patch("src.interfaces.api_research_jobs._build_service", return_value=svc):
            resp = client.post(
                "/api/research/jobs/backtest",
                json=_spec_dict(),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == "rj_create_api"
        assert data["status"] == "accepted"
        assert data["job_status"] == "PENDING"

    def test_create_job_invalid_spec(self, client):
        resp = client.post(
            "/api/research/jobs/backtest",
            json={"name": "bad", "start_time_ms": 100, "end_time_ms": 50},
        )
        assert resp.status_code == 422


# ── GET /api/research/jobs/{id} ──────────────────────────────────────

class TestGetJob:
    def test_get_existing_job(self, client):
        svc = _mock_service()
        job = _make_job("rj_get_api")
        svc.get_job.return_value = job
        with patch("src.interfaces.api_research_jobs._build_service", return_value=svc):
            resp = client.get("/api/research/jobs/rj_get_api")
        assert resp.status_code == 200
        assert resp.json()["id"] == "rj_get_api"

    def test_get_nonexistent_job_404(self, client):
        svc = _mock_service()
        svc.get_job.return_value = None
        with patch("src.interfaces.api_research_jobs._build_service", return_value=svc):
            resp = client.get("/api/research/jobs/nonexistent")
        assert resp.status_code == 404


# ── GET /api/research/runs/{id} ──────────────────────────────────────

class TestGetRunResult:
    def test_get_existing_result(self, client):
        svc = _mock_service()
        result = _make_run_result("rr_get_api")
        svc.get_run_result.return_value = result
        with patch("src.interfaces.api_research_jobs._build_service", return_value=svc):
            resp = client.get("/api/research/runs/rr_get_api")
        assert resp.status_code == 200
        assert resp.json()["id"] == "rr_get_api"

    def test_get_nonexistent_result_404(self, client):
        svc = _mock_service()
        svc.get_run_result.return_value = None
        with patch("src.interfaces.api_research_jobs._build_service", return_value=svc):
            resp = client.get("/api/research/runs/nonexistent")
        assert resp.status_code == 404


# ── GET /api/research/runs/{id}/report ───────────────────────────────

class TestGetRunReport:
    def test_get_report_success(self, client):
        svc = _mock_service()
        svc.get_run_report_payload.return_value = {"summary": {"total_return": 0.1}}
        with patch("src.interfaces.api_research_jobs._build_service", return_value=svc):
            resp = client.get("/api/research/runs/rr_api1/report")
        assert resp.status_code == 200
        assert resp.json()["summary"]["total_return"] == 0.1

    def test_get_report_run_not_found_404(self, client):
        svc = _mock_service()
        svc.get_run_report_payload.return_value = None
        with patch("src.interfaces.api_research_jobs._build_service", return_value=svc):
            resp = client.get("/api/research/runs/nonexistent/report")
        assert resp.status_code == 404

    def test_get_report_artifact_missing_404(self, client):
        from src.application.research_control_plane import ResearchRunnerError
        svc = _mock_service()
        svc.get_run_report_payload.side_effect = ResearchRunnerError("R-006", "Artifact missing")
        with patch("src.interfaces.api_research_jobs._build_service", return_value=svc):
            resp = client.get("/api/research/runs/rr_missing/report")
        assert resp.status_code == 404
        assert "Artifact missing" in resp.json()["message"]


# ── POST /api/research/candidates ────────────────────────────────────

class TestCreateCandidate:
    def test_create_candidate(self, client):
        svc = _mock_service()
        candidate = _make_candidate("cand_create_api")
        svc.create_candidate.return_value = candidate
        with patch("src.interfaces.api_research_jobs._build_service", return_value=svc):
            resp = client.post(
                "/api/research/candidates",
                json={"run_result_id": "rr_api1", "candidate_name": "test"},
            )
        assert resp.status_code == 200
        assert resp.json()["id"] == "cand_create_api"

    def test_create_candidate_missing_result_404(self, client):
        from src.application.research_control_plane import ResearchRunnerError
        svc = _mock_service()
        svc.create_candidate.side_effect = ResearchRunnerError("R-001", "Run result not found: nonexistent")
        with patch("src.interfaces.api_research_jobs._build_service", return_value=svc):
            resp = client.post(
                "/api/research/candidates",
                json={"run_result_id": "nonexistent", "candidate_name": "ghost"},
            )
        assert resp.status_code == 404


# ── GET /api/research/candidate-records ──────────────────────────────

class TestListCandidateRecords:
    def test_list_candidates(self, client):
        svc = _mock_service()
        svc.list_candidates.return_value = ([_make_candidate("cand_list_api")], 1)
        with patch("src.interfaces.api_research_jobs._build_service", return_value=svc):
            resp = client.get("/api/research/candidate-records")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == "cand_list_api"

    def test_list_with_status_filter(self, client):
        svc = _mock_service()
        svc.list_candidates.return_value = ([], 0)
        with patch("src.interfaces.api_research_jobs._build_service", return_value=svc):
            resp = client.get("/api/research/candidate-records?status=DRAFT")
        assert resp.status_code == 200
        svc.list_candidates.assert_called_once()


# ── GET /api/research/candidate-records/{id} ─────────────────────────

class TestGetCandidateRecord:
    def test_get_existing_candidate(self, client):
        svc = _mock_service()
        candidate = _make_candidate("cand_get_api")
        svc.get_candidate.return_value = candidate
        with patch("src.interfaces.api_research_jobs._build_service", return_value=svc):
            resp = client.get("/api/research/candidate-records/cand_get_api")
        assert resp.status_code == 200
        assert resp.json()["id"] == "cand_get_api"

    def test_get_nonexistent_candidate_404(self, client):
        svc = _mock_service()
        svc.get_candidate.return_value = None
        with patch("src.interfaces.api_research_jobs._build_service", return_value=svc):
            resp = client.get("/api/research/candidate-records/nonexistent")
        assert resp.status_code == 404


# ── POST /api/research/candidate-records/{id}/review ─────────────────

class TestReviewCandidate:
    def test_review_candidate(self, client):
        svc = _mock_service()
        reviewed = _make_candidate("cand_review_api")
        reviewed = reviewed.model_copy(update={"status": CandidateStatus.RECOMMENDED})
        svc.review_candidate.return_value = reviewed
        with patch("src.interfaces.api_research_jobs._build_service", return_value=svc):
            resp = client.post(
                "/api/research/candidate-records/cand_review_api/review",
                json={"status": "RECOMMENDED", "review_notes": "LGTM"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "RECOMMENDED"

    def test_review_nonexistent_candidate_404(self, client):
        svc = _mock_service()
        svc.review_candidate.return_value = None
        with patch("src.interfaces.api_research_jobs._build_service", return_value=svc):
            resp = client.post(
                "/api/research/candidate-records/nonexistent/review",
                json={"status": "REJECTED"},
            )
        assert resp.status_code == 404


# ── GET /api/research/runs ────────────────────────────────────────────

class TestListRunResults:
    def test_empty_list_200(self, client):
        svc = _mock_service()
        svc.list_run_results.return_value = ResearchRunListResponse(
            runs=[], total=0, limit=100, offset=0,
        )
        with patch("src.interfaces.api_research_jobs._build_service", return_value=svc):
            resp = client.get("/api/research/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["runs"] == []
        assert data["total"] == 0

    def test_with_job_id_filter(self, client):
        svc = _mock_service()
        svc.list_run_results.return_value = ResearchRunListResponse(
            runs=[], total=0, limit=100, offset=0,
        )
        with patch("src.interfaces.api_research_jobs._build_service", return_value=svc):
            resp = client.get("/api/research/runs?job_id=rj_filter_test")
        assert resp.status_code == 200
        svc.list_run_results.assert_called_once_with(
            job_id="rj_filter_test", limit=100, offset=0,
        )

    def test_with_limit_and_offset(self, client):
        svc = _mock_service()
        svc.list_run_results.return_value = ResearchRunListResponse(
            runs=[], total=0, limit=10, offset=5,
        )
        with patch("src.interfaces.api_research_jobs._build_service", return_value=svc):
            resp = client.get("/api/research/runs?limit=10&offset=5")
        assert resp.status_code == 200
        svc.list_run_results.assert_called_once_with(
            job_id=None, limit=10, offset=5,
        )

    def test_with_results(self, client):
        svc = _mock_service()
        run = _make_run_result("rr_list_api", job_id="rj_list_api")
        svc.list_run_results.return_value = ResearchRunListResponse(
            runs=[run], total=1, limit=100, offset=0,
        )
        with patch("src.interfaces.api_research_jobs._build_service", return_value=svc):
            resp = client.get("/api/research/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["runs"]) == 1
        assert data["runs"][0]["id"] == "rr_list_api"
        assert data["total"] == 1

    def test_limit_below_minimum_422(self, client):
        resp = client.get("/api/research/runs?limit=0")
        assert resp.status_code == 422

    def test_limit_above_maximum_422(self, client):
        resp = client.get("/api/research/runs?limit=501")
        assert resp.status_code == 422

    def test_offset_negative_422(self, client):
        resp = client.get("/api/research/runs?offset=-1")
        assert resp.status_code == 422
