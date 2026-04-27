"""Unit tests for ResearchJobService: create, run (success/failure), candidate."""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.application.research_control_plane import (
    LocalBacktestResearchRunner,
    ResearchJobService,
    ResearchRunnerError,
)
from src.domain.research_models import (
    CandidateStatus,
    CreateCandidateRequest,
    ResearchJobStatus,
    ResearchRunListResponse,
    ResearchSpec,
)
from src.infrastructure.research_repository import ResearchRepository


# ── helpers ──────────────────────────────────────────────────────────

def _spec(**overrides):
    base = dict(
        name="svc-test",
        start_time_ms=1700000000000,
        end_time_ms=1700086400000,
    )
    base.update(overrides)
    return ResearchSpec(**base)


# ── fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
async def repo(tmp_path):
    db_path = str(tmp_path / "research_svc_test.db")
    r = ResearchRepository(db_path=db_path)
    await r.initialize()
    yield r
    await r.close()


@pytest.fixture
def service(repo):
    return ResearchJobService(repository=repo, runner=None)


# ── create_backtest_job ──────────────────────────────────────────────

class TestCreateBacktestJob:
    @pytest.mark.asyncio
    async def test_creates_pending_job(self, service):
        spec = _spec()
        job = await service.create_backtest_job(spec)
        assert job.id.startswith("rj_")
        assert job.kind == "backtest"
        assert job.status == ResearchJobStatus.PENDING
        assert job.name == "svc-test"
        assert job.spec_ref.endswith("spec.json")

    @pytest.mark.asyncio
    async def test_job_persisted(self, service, repo):
        spec = _spec()
        job = await service.create_backtest_job(spec)
        fetched = await repo.get_job(job.id)
        assert fetched is not None
        assert fetched.id == job.id


# ── run_job success ──────────────────────────────────────────────────

class TestRunJobSuccess:
    @pytest.mark.asyncio
    async def test_runner_succeeds(self, repo):
        mock_report = MagicMock()
        mock_report.model_dump.return_value = {
            "total_return": 0.15,
            "max_drawdown": -0.08,
            "win_rate": 0.6,
            "total_trades": 42,
            "sharpe_ratio": 1.5,
            "sortino_ratio": 2.0,
            "total_pnl": 1500,
            "final_balance": 11500,
        }
        mock_executor = AsyncMock(return_value=mock_report)
        runner = LocalBacktestResearchRunner(
            artifact_root="/tmp/research_test_runs",
            backtest_executor=mock_executor,
        )
        service = ResearchJobService(repository=repo, runner=runner)

        spec = _spec()
        job = await service.create_backtest_job(spec)
        result = await service.run_job(job.id)

        assert result.job_id == job.id
        assert result.kind == "backtest"
        assert result.id.startswith("rr_")

        updated_job = await repo.get_job(job.id)
        assert updated_job.status == ResearchJobStatus.SUCCEEDED
        assert updated_job.run_result_id == result.id
        assert updated_job.progress_pct == 100

    @pytest.mark.asyncio
    async def test_run_result_persisted(self, repo):
        mock_report = MagicMock()
        mock_report.model_dump.return_value = {"total_return": 0.1}
        mock_executor = AsyncMock(return_value=mock_report)
        runner = LocalBacktestResearchRunner(
            artifact_root="/tmp/research_test_runs",
            backtest_executor=mock_executor,
        )
        service = ResearchJobService(repository=repo, runner=runner)

        spec = _spec()
        job = await service.create_backtest_job(spec)
        result = await service.run_job(job.id)

        fetched = await repo.get_run_result(result.id)
        assert fetched is not None
        assert fetched.summary_metrics["total_return"] == 0.1

    @pytest.mark.asyncio
    async def test_default_baseline_profile_resolves_runtime_overrides(self, repo):
        captured = {}

        async def executor(request, overrides):
            captured["request"] = request
            captured["overrides"] = overrides
            return {"total_return": 0.1}

        runner = LocalBacktestResearchRunner(
            artifact_root="/tmp/research_test_runs",
            backtest_executor=executor,
        )
        service = ResearchJobService(repository=repo, runner=runner)

        spec = _spec()
        job = await service.create_backtest_job(spec)
        result = await service.run_job(job.id)

        overrides = captured["overrides"]
        order_strategy = captured["request"].order_strategy
        assert overrides.ema_period == 50
        assert overrides.tp_ratios == [Decimal("0.5"), Decimal("0.5")]
        assert overrides.tp_targets == [Decimal("1.0"), Decimal("3.5")]
        assert overrides.allowed_directions == ["LONG"]
        assert order_strategy is not None
        assert order_strategy.tp_ratios == [Decimal("0.5"), Decimal("0.5")]
        assert order_strategy.tp_targets == [Decimal("1.0"), Decimal("3.5")]
        assert order_strategy.initial_stop_loss_rr == Decimal("-1.0")
        assert result.spec_snapshot["resolved_runtime_overrides"]["ema_period"] == 50
        assert result.spec_snapshot["resolved_runtime_overrides"]["allowed_directions"] == ["LONG"]
        assert result.spec_snapshot["resolved_order_strategy"]["tp_ratios"] == ["0.5", "0.5"]
        assert result.spec_snapshot["resolved_order_strategy"]["tp_targets"] == ["1.0", "3.5"]

    @pytest.mark.asyncio
    async def test_explicit_runtime_overrides_take_precedence(self, repo):
        from src.domain.models import BacktestRuntimeOverrides

        captured = {}

        async def executor(request, overrides):
            captured["request"] = request
            captured["overrides"] = overrides
            return {"total_return": 0.1}

        runner = LocalBacktestResearchRunner(
            artifact_root="/tmp/research_test_runs",
            backtest_executor=executor,
        )
        service = ResearchJobService(repository=repo, runner=runner)

        explicit = BacktestRuntimeOverrides(
            ema_period=111,
            tp_ratios=[Decimal("0.6"), Decimal("0.4")],
            tp_targets=[Decimal("1.0"), Decimal("2.5")],
            allowed_directions=["SHORT"],
        )
        spec = _spec(runtime_overrides=explicit)
        job = await service.create_backtest_job(spec)
        result = await service.run_job(job.id)

        assert captured["overrides"].ema_period == 111
        assert captured["overrides"].allowed_directions == ["SHORT"]
        assert captured["request"].order_strategy.tp_ratios == [Decimal("0.6"), Decimal("0.4")]
        assert captured["request"].order_strategy.tp_targets == [Decimal("1.0"), Decimal("2.5")]
        assert result.spec_snapshot["resolved_runtime_overrides"]["ema_period"] == 111
        assert result.spec_snapshot["resolved_order_strategy"]["tp_targets"] == ["1.0", "2.5"]

    @pytest.mark.asyncio
    async def test_unknown_profile_does_not_invent_runtime_overrides(self, repo):
        captured = {}

        async def executor(request, overrides):
            captured["request"] = request
            captured["overrides"] = overrides
            return {"total_return": 0.1}

        runner = LocalBacktestResearchRunner(
            artifact_root="/tmp/research_test_runs",
            backtest_executor=executor,
        )
        service = ResearchJobService(repository=repo, runner=runner)

        spec = _spec(profile_name="adhoc_experiment")
        job = await service.create_backtest_job(spec)
        result = await service.run_job(job.id)

        assert captured["overrides"] is None
        assert captured["request"].order_strategy is None
        assert "resolved_runtime_overrides" not in result.spec_snapshot
        assert "resolved_order_strategy" not in result.spec_snapshot


# ── run_job failure ──────────────────────────────────────────────────

class TestRunJobFailure:
    @pytest.mark.asyncio
    async def test_runner_raises_research_runner_error(self, repo):
        async def failing_executor(request, overrides):
            raise ResearchRunnerError("R-100", "Simulated failure")

        runner = LocalBacktestResearchRunner(
            artifact_root="/tmp/research_test_runs",
            backtest_executor=failing_executor,
        )
        service = ResearchJobService(repository=repo, runner=runner)

        spec = _spec()
        job = await service.create_backtest_job(spec)

        with pytest.raises(ResearchRunnerError) as exc_info:
            await service.run_job(job.id)

        assert exc_info.value.error_code == "R-100"

        updated_job = await repo.get_job(job.id)
        assert updated_job.status == ResearchJobStatus.FAILED
        assert updated_job.error_code == "R-100"
        assert updated_job.error_message == "Simulated failure"

    @pytest.mark.asyncio
    async def test_runner_raises_unexpected_exception(self, repo):
        async def crashing_executor(request, overrides):
            raise RuntimeError("Unexpected crash")

        runner = LocalBacktestResearchRunner(
            artifact_root="/tmp/research_test_runs",
            backtest_executor=crashing_executor,
        )
        service = ResearchJobService(repository=repo, runner=runner)

        spec = _spec()
        job = await service.create_backtest_job(spec)

        # Runner wraps generic exceptions as ResearchRunnerError("R-003", ...),
        # then run_job catches that and marks FAILED with the runner's error_code.
        with pytest.raises(ResearchRunnerError) as exc_info:
            await service.run_job(job.id)

        assert exc_info.value.error_code == "R-003"

        updated_job = await repo.get_job(job.id)
        assert updated_job.status == ResearchJobStatus.FAILED
        assert updated_job.error_code == "R-003"
        assert "Unexpected crash" in updated_job.error_message

    @pytest.mark.asyncio
    async def test_no_runner_configured(self, service):
        spec = _spec()
        job = await service.create_backtest_job(spec)
        with pytest.raises(ResearchRunnerError, match="not configured"):
            await service.run_job(job.id)

    @pytest.mark.asyncio
    async def test_run_nonexistent_job(self, repo):
        runner = LocalBacktestResearchRunner(
            artifact_root="/tmp/research_test_runs",
            backtest_executor=AsyncMock(return_value={}),
        )
        service = ResearchJobService(repository=repo, runner=runner)
        with pytest.raises(ResearchRunnerError, match="not found"):
            await service.run_job("nonexistent")

    @pytest.mark.asyncio
    async def test_run_non_pending_job(self, repo):
        runner = LocalBacktestResearchRunner(
            artifact_root="/tmp/research_test_runs",
            backtest_executor=AsyncMock(return_value={}),
        )
        service = ResearchJobService(repository=repo, runner=runner)

        spec = _spec()
        job = await service.create_backtest_job(spec)
        await repo.mark_job_running(job.id)

        with pytest.raises(ResearchRunnerError, match="not pending"):
            await service.run_job(job.id)


# ── create_candidate ─────────────────────────────────────────────────

class TestCreateCandidate:
    @pytest.mark.asyncio
    async def test_create_candidate_for_existing_result(self, repo):
        mock_report = MagicMock()
        mock_report.model_dump.return_value = {"total_return": 0.1}
        mock_executor = AsyncMock(return_value=mock_report)
        runner = LocalBacktestResearchRunner(
            artifact_root="/tmp/research_test_runs",
            backtest_executor=mock_executor,
        )
        service = ResearchJobService(repository=repo, runner=runner)

        spec = _spec()
        job = await service.create_backtest_job(spec)
        result = await service.run_job(job.id)

        candidate = await service.create_candidate(
            CreateCandidateRequest(
                run_result_id=result.id,
                candidate_name="ETH momentum v2",
            )
        )
        assert candidate.id.startswith("cand_")
        assert candidate.run_result_id == result.id
        assert candidate.candidate_name == "ETH momentum v2"
        assert candidate.status == CandidateStatus.DRAFT

    @pytest.mark.asyncio
    async def test_create_candidate_for_nonexistent_result(self, service):
        with pytest.raises(ResearchRunnerError, match="Run result not found"):
            await service.create_candidate(
                CreateCandidateRequest(
                    run_result_id="nonexistent",
                    candidate_name="ghost candidate",
                )
            )


# ── review_candidate ─────────────────────────────────────────────────

class TestReviewCandidate:
    @pytest.mark.asyncio
    async def test_review_candidate(self, repo):
        mock_report = MagicMock()
        mock_report.model_dump.return_value = {"total_return": 0.1}
        mock_executor = AsyncMock(return_value=mock_report)
        runner = LocalBacktestResearchRunner(
            artifact_root="/tmp/research_test_runs",
            backtest_executor=mock_executor,
        )
        service = ResearchJobService(repository=repo, runner=runner)

        spec = _spec()
        job = await service.create_backtest_job(spec)
        result = await service.run_job(job.id)
        candidate = await service.create_candidate(
            CreateCandidateRequest(
                run_result_id=result.id,
                candidate_name="review me",
            )
        )

        from src.domain.research_models import CandidateReviewRequest
        reviewed = await service.review_candidate(
            candidate.id,
            CandidateReviewRequest(
                status=CandidateStatus.RECOMMENDED,
                review_notes="Strong candidate",
                risks=["drawdown"],
            ),
        )
        assert reviewed.status == CandidateStatus.RECOMMENDED
        assert reviewed.review_notes == "Strong candidate"
        assert "drawdown" in reviewed.risks

    @pytest.mark.asyncio
    async def test_review_nonexistent_candidate(self, service):
        from src.domain.research_models import CandidateReviewRequest
        result = await service.review_candidate(
            "nonexistent",
            CandidateReviewRequest(status=CandidateStatus.REJECTED),
        )
        assert result is None


# ── list/get helpers ─────────────────────────────────────────────────

class TestListAndGet:
    @pytest.mark.asyncio
    async def test_list_jobs(self, service):
        spec1 = _spec(name="job1")
        spec2 = _spec(name="job2")
        await service.create_backtest_job(spec1)
        await service.create_backtest_job(spec2)

        resp = await service.list_jobs(status=None, limit=10, offset=0)
        assert resp.total == 2
        assert len(resp.jobs) == 2

    @pytest.mark.asyncio
    async def test_get_job(self, service):
        spec = _spec()
        job = await service.create_backtest_job(spec)
        fetched = await service.get_job(job.id)
        assert fetched is not None
        assert fetched.id == job.id

    @pytest.mark.asyncio
    async def test_get_run_result(self, repo):
        mock_report = MagicMock()
        mock_report.model_dump.return_value = {"total_return": 0.1}
        mock_executor = AsyncMock(return_value=mock_report)
        runner = LocalBacktestResearchRunner(
            artifact_root="/tmp/research_test_runs",
            backtest_executor=mock_executor,
        )
        service = ResearchJobService(repository=repo, runner=runner)

        spec = _spec()
        job = await service.create_backtest_job(spec)
        result = await service.run_job(job.id)

        fetched = await service.get_run_result(result.id)
        assert fetched is not None
        assert fetched.id == result.id


# ── list_run_results ─────────────────────────────────────────────────

class TestListRunResults:
    @pytest.mark.asyncio
    async def test_list_run_results_empty(self, service):
        resp = await service.list_run_results(job_id=None, limit=100, offset=0)
        assert isinstance(resp, ResearchRunListResponse)
        assert resp.runs == []
        assert resp.total == 0
        assert resp.limit == 100
        assert resp.offset == 0

    @pytest.mark.asyncio
    async def test_list_run_results_returns_repository_data(self, repo):
        mock_report = MagicMock()
        mock_report.model_dump.return_value = {"total_return": 0.1}
        mock_executor = AsyncMock(return_value=mock_report)
        runner = LocalBacktestResearchRunner(
            artifact_root="/tmp/research_test_runs",
            backtest_executor=mock_executor,
        )
        service = ResearchJobService(repository=repo, runner=runner)

        spec = _spec()
        job = await service.create_backtest_job(spec)
        result = await service.run_job(job.id)

        resp = await service.list_run_results(job_id=job.id, limit=10, offset=0)
        assert isinstance(resp, ResearchRunListResponse)
        assert resp.total == 1
        assert len(resp.runs) == 1
        assert resp.runs[0].id == result.id
        assert resp.limit == 10
        assert resp.offset == 0

    @pytest.mark.asyncio
    async def test_list_run_results_with_pagination(self, repo):
        mock_report = MagicMock()
        mock_report.model_dump.return_value = {"total_return": 0.1}
        mock_executor = AsyncMock(return_value=mock_report)
        runner = LocalBacktestResearchRunner(
            artifact_root="/tmp/research_test_runs",
            backtest_executor=mock_executor,
        )
        service = ResearchJobService(repository=repo, runner=runner)

        for i in range(3):
            spec = _spec(name=f"run-{i}")
            job = await service.create_backtest_job(spec)
            await service.run_job(job.id)

        resp = await service.list_run_results(job_id=None, limit=2, offset=0)
        assert resp.total == 3
        assert len(resp.runs) == 2

        resp2 = await service.list_run_results(job_id=None, limit=2, offset=2)
        assert len(resp2.runs) == 1
