"""Unit tests for ResearchRepository: SQLite CRUD + status transitions."""

import pytest
import aiosqlite

from src.domain.research_models import (
    CandidateRecord,
    CandidateStatus,
    ResearchJob,
    ResearchJobStatus,
    ResearchRunResult,
    ResearchSpec,
    utc_now_iso,
)
from src.infrastructure.research_repository import ResearchRepository


# ── helpers ──────────────────────────────────────────────────────────

def _spec(**overrides):
    base = dict(
        name="repo-test",
        start_time_ms=1700000000000,
        end_time_ms=1700086400000,
    )
    base.update(overrides)
    return ResearchSpec(**base)


def _job(job_id="rj_repo1", status=ResearchJobStatus.PENDING, spec=None):
    return ResearchJob(
        id=job_id,
        kind="backtest",
        name="repo-test-job",
        spec_ref=f"reports/{job_id}/spec.json",
        status=status,
        spec=spec or _spec(),
    )


def _run_result(result_id="rr_repo1", job_id="rj_repo1"):
    return ResearchRunResult(
        id=result_id,
        job_id=job_id,
        kind="backtest",
        spec_snapshot={"symbol": "ETH/USDT:USDT"},
        summary_metrics={"total_return": 0.12},
        artifact_index={"result": "/tmp/result.json"},
    )


def _candidate(candidate_id="cand_repo1", run_result_id="rr_repo1"):
    return CandidateRecord(
        id=candidate_id,
        run_result_id=run_result_id,
        candidate_name="test candidate",
    )


# ── fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
async def repo(tmp_path):
    db_path = str(tmp_path / "research_test.db")
    r = ResearchRepository(db_path=db_path)
    await r.initialize()
    yield r
    await r.close()


# ── initialize ───────────────────────────────────────────────────────

class TestInitialize:
    @pytest.mark.asyncio
    async def test_initialize_creates_tables(self, repo):
        cursor = await repo._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row["name"] for row in await cursor.fetchall()]
        assert "research_jobs" in tables
        assert "research_run_results" in tables
        assert "candidate_records" in tables

    @pytest.mark.asyncio
    async def test_initialize_idempotent(self, repo):
        await repo.initialize()
        await repo.initialize()
        job = _job("rj_idempotent")
        await repo.save_job(job)
        fetched = await repo.get_job("rj_idempotent")
        assert fetched is not None

    @pytest.mark.asyncio
    async def test_initialize_with_external_connection(self, tmp_path):
        db_path = str(tmp_path / "ext_conn.db")
        async with aiosqlite.connect(db_path) as conn:
            r = ResearchRepository(connection=conn)
            await r.initialize()
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='research_jobs'"
            )
            row = await cursor.fetchone()
            assert row is not None


# ── save/get job ─────────────────────────────────────────────────────

class TestJobCRUD:
    @pytest.mark.asyncio
    async def test_save_and_get_job(self, repo):
        job = _job("rj_save_get")
        await repo.save_job(job)
        fetched = await repo.get_job("rj_save_get")
        assert fetched is not None
        assert fetched.id == "rj_save_get"
        assert fetched.status == ResearchJobStatus.PENDING
        assert fetched.spec.name == "repo-test"

    @pytest.mark.asyncio
    async def test_get_nonexistent_job(self, repo):
        assert await repo.get_job("nonexistent") is None

    @pytest.mark.asyncio
    async def test_save_job_upsert(self, repo):
        job = _job("rj_upsert")
        await repo.save_job(job)
        updated = job.model_copy(update={"status": ResearchJobStatus.RUNNING})
        await repo.save_job(updated)
        fetched = await repo.get_job("rj_upsert")
        assert fetched.status == ResearchJobStatus.RUNNING


# ── list jobs ────────────────────────────────────────────────────────

class TestListJobs:
    @pytest.mark.asyncio
    async def test_list_empty(self, repo):
        jobs, total = await repo.list_jobs()
        assert jobs == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_list_with_status_filter(self, repo):
        await repo.save_job(_job("rj_list1", status=ResearchJobStatus.PENDING))
        await repo.save_job(_job("rj_list2", status=ResearchJobStatus.PENDING))
        await repo.save_job(_job("rj_list3", status=ResearchJobStatus.SUCCEEDED))

        pending, total = await repo.list_jobs(status=ResearchJobStatus.PENDING)
        assert len(pending) == 2
        assert total == 2

        succeeded, total = await repo.list_jobs(status=ResearchJobStatus.SUCCEEDED)
        assert len(succeeded) == 1
        assert total == 1

    @pytest.mark.asyncio
    async def test_list_pagination(self, repo):
        for i in range(5):
            await repo.save_job(_job(f"rj_page_{i}"))

        jobs, total = await repo.list_jobs(limit=2, offset=0)
        assert len(jobs) == 2
        assert total == 5

        jobs2, _ = await repo.list_jobs(limit=2, offset=2)
        assert len(jobs2) == 2


# ── mark job status ──────────────────────────────────────────────────

class TestMarkJobStatus:
    @pytest.mark.asyncio
    async def test_mark_running(self, repo):
        job = _job("rj_mark_run")
        await repo.save_job(job)
        await repo.mark_job_running("rj_mark_run")
        fetched = await repo.get_job("rj_mark_run")
        assert fetched.status == ResearchJobStatus.RUNNING
        assert fetched.started_at is not None
        assert fetched.progress_pct == 0

    @pytest.mark.asyncio
    async def test_mark_running_only_from_pending(self, repo):
        job = _job("rj_mark_twice", status=ResearchJobStatus.RUNNING)
        await repo.save_job(job)
        await repo.mark_job_running("rj_mark_twice")
        fetched = await repo.get_job("rj_mark_twice")
        assert fetched.status == ResearchJobStatus.RUNNING

    @pytest.mark.asyncio
    async def test_mark_succeeded(self, repo):
        job = _job("rj_mark_ok")
        await repo.save_job(job)
        await repo.mark_job_running("rj_mark_ok")
        await repo.mark_job_succeeded("rj_mark_ok", "rr_success")
        fetched = await repo.get_job("rj_mark_ok")
        assert fetched.status == ResearchJobStatus.SUCCEEDED
        assert fetched.run_result_id == "rr_success"
        assert fetched.finished_at is not None
        assert fetched.progress_pct == 100
        assert fetched.error_code is None

    @pytest.mark.asyncio
    async def test_mark_failed(self, repo):
        job = _job("rj_mark_fail")
        await repo.save_job(job)
        await repo.mark_job_running("rj_mark_fail")
        await repo.mark_job_failed("rj_mark_fail", "R-003", "boom")
        fetched = await repo.get_job("rj_mark_fail")
        assert fetched.status == ResearchJobStatus.FAILED
        assert fetched.error_code == "R-003"
        assert fetched.error_message == "boom"
        assert fetched.finished_at is not None


# ── run result ───────────────────────────────────────────────────────

class TestRunResultCRUD:
    @pytest.mark.asyncio
    async def test_save_and_get_run_result(self, repo):
        job = _job("rj_rr")
        await repo.save_job(job)
        result = _run_result("rr_test", job_id="rj_rr")
        await repo.save_run_result(result)
        fetched = await repo.get_run_result("rr_test")
        assert fetched is not None
        assert fetched.job_id == "rj_rr"
        assert fetched.spec_snapshot == {"symbol": "ETH/USDT:USDT"}

    @pytest.mark.asyncio
    async def test_get_nonexistent_run_result(self, repo):
        assert await repo.get_run_result("nonexistent") is None

    @pytest.mark.asyncio
    async def test_save_run_result_upsert(self, repo):
        job = _job("rj_rr_up")
        await repo.save_job(job)
        result = _run_result("rr_upsert", job_id="rj_rr_up")
        await repo.save_run_result(result)
        updated = result.model_copy(update={"source_profile": "updated_profile"})
        await repo.save_run_result(updated)
        fetched = await repo.get_run_result("rr_upsert")
        assert fetched.source_profile == "updated_profile"


# ── list_run_results ──────────────────────────────────────────────────

class TestListRunResults:
    @pytest.mark.asyncio
    async def test_list_empty(self, repo):
        runs, total = await repo.list_run_results()
        assert runs == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_list_returns_all(self, repo):
        await repo.save_job(_job("rj_lr_all"))
        for i in range(3):
            await repo.save_run_result(
                _run_result(f"rr_all_{i}", job_id="rj_lr_all")
            )
        runs, total = await repo.list_run_results()
        assert len(runs) == 3
        assert total == 3

    @pytest.mark.asyncio
    async def test_list_filter_by_job_id(self, repo):
        await repo.save_job(_job("rj_lr_a"))
        await repo.save_job(_job("rj_lr_b"))
        await repo.save_run_result(_run_result("rr_a1", job_id="rj_lr_a"))
        await repo.save_run_result(_run_result("rr_a2", job_id="rj_lr_a"))
        await repo.save_run_result(_run_result("rr_b1", job_id="rj_lr_b"))

        runs_a, total_a = await repo.list_run_results(job_id="rj_lr_a")
        assert len(runs_a) == 2
        assert total_a == 2
        assert all(r.job_id == "rj_lr_a" for r in runs_a)

        runs_b, total_b = await repo.list_run_results(job_id="rj_lr_b")
        assert len(runs_b) == 1
        assert total_b == 1

    @pytest.mark.asyncio
    async def test_list_filter_by_nonexistent_job_id(self, repo):
        await repo.save_job(_job("rj_lr_none"))
        await repo.save_run_result(_run_result("rr_none1", job_id="rj_lr_none"))

        runs, total = await repo.list_run_results(job_id="ghost_job")
        assert runs == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_list_pagination_limit(self, repo):
        await repo.save_job(_job("rj_lr_page"))
        for i in range(5):
            await repo.save_run_result(
                _run_result(f"rr_page_{i}", job_id="rj_lr_page")
            )

        runs, total = await repo.list_run_results(limit=2, offset=0)
        assert len(runs) == 2
        assert total == 5

    @pytest.mark.asyncio
    async def test_list_pagination_offset(self, repo):
        await repo.save_job(_job("rj_lr_off"))
        for i in range(5):
            await repo.save_run_result(
                _run_result(f"rr_off_{i}", job_id="rj_lr_off")
            )

        runs, total = await repo.list_run_results(limit=100, offset=3)
        assert len(runs) == 2
        assert total == 5

    @pytest.mark.asyncio
    async def test_list_pagination_combined(self, repo):
        await repo.save_job(_job("rj_lr_comb"))
        for i in range(5):
            await repo.save_run_result(
                _run_result(f"rr_comb_{i}", job_id="rj_lr_comb")
            )

        page1, total = await repo.list_run_results(limit=2, offset=0)
        page2, _ = await repo.list_run_results(limit=2, offset=2)
        page3, _ = await repo.list_run_results(limit=2, offset=4)

        assert total == 5
        assert len(page1) == 2
        assert len(page2) == 2
        assert len(page3) == 1
        all_ids = [r.id for r in page1 + page2 + page3]
        assert len(set(all_ids)) == 5

    @pytest.mark.asyncio
    async def test_list_filter_by_job_id_with_pagination(self, repo):
        await repo.save_job(_job("rj_lr_fp"))
        await repo.save_job(_job("rj_lr_fp_other"))
        for i in range(4):
            await repo.save_run_result(
                _run_result(f"rr_fp_{i}", job_id="rj_lr_fp")
            )
        await repo.save_run_result(
            _run_result("rr_fp_other", job_id="rj_lr_fp_other")
        )

        runs, total = await repo.list_run_results(
            job_id="rj_lr_fp", limit=2, offset=0
        )
        assert len(runs) == 2
        assert total == 4
        assert all(r.job_id == "rj_lr_fp" for r in runs)


# ── candidate ────────────────────────────────────────────────────────

class TestCandidateCRUD:
    @pytest.mark.asyncio
    async def test_save_and_get_candidate(self, repo):
        job = _job("rj_cand")
        await repo.save_job(job)
        result = _run_result("rr_cand", job_id="rj_cand")
        await repo.save_run_result(result)
        candidate = _candidate("cand_test", run_result_id="rr_cand")
        await repo.save_candidate(candidate)
        fetched = await repo.get_candidate("cand_test")
        assert fetched is not None
        assert fetched.candidate_name == "test candidate"
        assert fetched.status == CandidateStatus.DRAFT

    @pytest.mark.asyncio
    async def test_get_nonexistent_candidate(self, repo):
        assert await repo.get_candidate("nonexistent") is None

    @pytest.mark.asyncio
    async def test_list_candidates_empty(self, repo):
        candidates, total = await repo.list_candidates()
        assert candidates == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_list_candidates_with_status_filter(self, repo):
        job = _job("rj_cand_f")
        await repo.save_job(job)
        result = _run_result("rr_cand_f", job_id="rj_cand_f")
        await repo.save_run_result(result)

        for i, status in enumerate([CandidateStatus.DRAFT, CandidateStatus.DRAFT, CandidateStatus.REVIEWED]):
            c = CandidateRecord(
                id=f"cand_f_{i}",
                run_result_id="rr_cand_f",
                candidate_name=f"candidate {i}",
                status=status,
            )
            await repo.save_candidate(c)

        drafts, total = await repo.list_candidates(status=CandidateStatus.DRAFT)
        assert len(drafts) == 2
        assert total == 2

        reviewed, total = await repo.list_candidates(status=CandidateStatus.REVIEWED)
        assert len(reviewed) == 1
        assert total == 1

    @pytest.mark.asyncio
    async def test_list_candidates_pagination(self, repo):
        job = _job("rj_cand_p")
        await repo.save_job(job)
        result = _run_result("rr_cand_p", job_id="rj_cand_p")
        await repo.save_run_result(result)

        for i in range(5):
            c = CandidateRecord(
                id=f"cand_p_{i}",
                run_result_id="rr_cand_p",
                candidate_name=f"candidate {i}",
            )
            await repo.save_candidate(c)

        candidates, total = await repo.list_candidates(limit=2, offset=0)
        assert len(candidates) == 2
        assert total == 5

    @pytest.mark.asyncio
    async def test_save_candidate_upsert(self, repo):
        job = _job("rj_cand_up")
        await repo.save_job(job)
        result = _run_result("rr_cand_up", job_id="rj_cand_up")
        await repo.save_run_result(result)
        c = _candidate("cand_up", run_result_id="rr_cand_up")
        await repo.save_candidate(c)
        updated = c.model_copy(update={"status": CandidateStatus.RECOMMENDED, "updated_at": utc_now_iso()})
        await repo.save_candidate(updated)
        fetched = await repo.get_candidate("cand_up")
        assert fetched.status == CandidateStatus.RECOMMENDED
