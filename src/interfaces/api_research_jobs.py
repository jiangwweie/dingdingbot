"""Research Control Plane write/read API."""

from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from src.application.research_control_plane import (
    LocalBacktestResearchRunner,
    ResearchJobService,
    ResearchRunnerError,
)
from src.domain.models import BacktestRequest, BacktestRuntimeOverrides
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
)
from src.infrastructure.research_repository import ResearchRepository
from src.infrastructure.logger import setup_logger

router = APIRouter(prefix="/api/research", tags=["Research Jobs"])
logger = setup_logger(__name__)

_runner_lock = asyncio.Lock()


async def _execute_backtest_request(
    request: BacktestRequest,
    runtime_overrides: Optional[BacktestRuntimeOverrides],
) -> object:
    """Adapter that reuses the existing PMS backtest engine without making it the product API."""
    from src.application.backtester import Backtester
    from src.infrastructure.backtest_repository import BacktestReportRepository
    from src.infrastructure.historical_data_repository import HistoricalDataRepository
    from src.infrastructure.order_repository import OrderRepository
    from src.interfaces import api as api_module

    gateway, gateway_is_temp = await api_module._get_backtest_gateway()
    data_repo = HistoricalDataRepository(exchange_gateway=gateway)
    await data_repo.initialize()
    backtest_repository = BacktestReportRepository()
    await backtest_repository.initialize()
    order_repository = OrderRepository()
    await order_repository.initialize()

    try:
        backtester = Backtester(
            gateway,
            data_repository=data_repo,
            config_manager=getattr(api_module, "_config_manager", None),
        )
        return await backtester.run_backtest(
            request,
            account_snapshot=None,
            repository=None,
            backtest_repository=backtest_repository,
            order_repository=order_repository,
            runtime_overrides=runtime_overrides,
        )
    finally:
        if gateway_is_temp:
            await gateway.close()
        await backtest_repository.close()
        await order_repository.close()
        await data_repo.close()


async def _build_service(with_runner: bool = True) -> ResearchJobService:
    repository = ResearchRepository()
    await repository.initialize()
    runner = None
    if with_runner:
        runner = LocalBacktestResearchRunner(backtest_executor=_execute_backtest_request)
    return ResearchJobService(repository=repository, runner=runner)


async def _run_job_background(job_id: str) -> None:
    service = await _build_service(with_runner=True)
    try:
        async with _runner_lock:
            await service.run_job(job_id)
    except Exception as exc:
        # run_job persists structured failure details; this catch keeps the
        # background task from leaking an unhandled exception into the server log.
        logger.exception("Research background job failed: %s", exc)
    finally:
        await service.repository.close()


@router.post("/jobs/backtest", response_model=ResearchJobAccepted)
async def create_backtest_job(
    spec: ResearchSpec,
    background_tasks: BackgroundTasks,
) -> ResearchJobAccepted:
    service = await _build_service(with_runner=False)
    try:
        job = await service.create_backtest_job(spec)
        background_tasks.add_task(_run_job_background, job.id)
        return ResearchJobAccepted(job_id=job.id, job_status=job.status)
    finally:
        await service.repository.close()


@router.get("/jobs", response_model=ResearchJobListResponse)
async def list_research_jobs(
    status: Optional[ResearchJobStatus] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> ResearchJobListResponse:
    service = await _build_service(with_runner=False)
    try:
        return await service.list_jobs(status=status, limit=limit, offset=offset)
    finally:
        await service.repository.close()


@router.get("/jobs/{job_id}", response_model=ResearchJob)
async def get_research_job(job_id: str) -> ResearchJob:
    service = await _build_service(with_runner=False)
    try:
        job = await service.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Research job not found: {job_id}")
        return job
    finally:
        await service.repository.close()


@router.get("/runs/{run_result_id}", response_model=ResearchRunResult)
async def get_research_run_result(run_result_id: str) -> ResearchRunResult:
    service = await _build_service(with_runner=False)
    try:
        result = await service.get_run_result(run_result_id)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Research run result not found: {run_result_id}")
        return result
    finally:
        await service.repository.close()


@router.get("/runs", response_model=ResearchRunListResponse)
async def list_research_run_results(
    job_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> ResearchRunListResponse:
    service = await _build_service(with_runner=False)
    try:
        return await service.list_run_results(job_id=job_id, limit=limit, offset=offset)
    finally:
        await service.repository.close()


@router.post("/candidates", response_model=CandidateRecord)
async def create_research_candidate(request: CreateCandidateRequest) -> CandidateRecord:
    service = await _build_service(with_runner=False)
    try:
        try:
            return await service.create_candidate(request)
        except ResearchRunnerError as exc:
            raise HTTPException(status_code=404, detail=exc.message)
    finally:
        await service.repository.close()


@router.get("/candidate-records", response_model=list[CandidateRecord])
async def list_research_candidate_records(
    status: Optional[CandidateStatus] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[CandidateRecord]:
    service = await _build_service(with_runner=False)
    try:
        candidates, _ = await service.list_candidates(status=status, limit=limit, offset=offset)
        return candidates
    finally:
        await service.repository.close()


@router.get("/candidate-records/{candidate_id}", response_model=CandidateRecord)
async def get_research_candidate_record(candidate_id: str) -> CandidateRecord:
    service = await _build_service(with_runner=False)
    try:
        candidate = await service.get_candidate(candidate_id)
        if candidate is None:
            raise HTTPException(status_code=404, detail=f"Candidate record not found: {candidate_id}")
        return candidate
    finally:
        await service.repository.close()


@router.post("/candidate-records/{candidate_id}/review", response_model=CandidateRecord)
async def review_research_candidate(
    candidate_id: str,
    request: CandidateReviewRequest,
) -> CandidateRecord:
    service = await _build_service(with_runner=False)
    try:
        candidate = await service.review_candidate(candidate_id, request)
        if candidate is None:
            raise HTTPException(status_code=404, detail=f"Candidate record not found: {candidate_id}")
        return candidate
    finally:
        await service.repository.close()
