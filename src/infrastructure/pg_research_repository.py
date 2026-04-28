"""PostgreSQL repository for the Research Control Plane."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.research_models import (
    CandidateRecord,
    CandidateStatus,
    ResearchJob,
    ResearchJobStatus,
    ResearchRunResult,
    ResearchSpec,
    utc_now_iso,
)
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.logger import setup_logger
from src.infrastructure.pg_models import (
    PGCandidateRecordORM,
    PGResearchJobORM,
    PGResearchRunResultORM,
)

logger = setup_logger(__name__)


class PgResearchRepository:
    """Persists research jobs/results/candidates in PostgreSQL."""

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()
        logger.info("PG Research control plane repository initialized")

    async def close(self) -> None:
        return None

    async def save_job(self, job: ResearchJob) -> None:
        payload = job.spec.model_dump(mode="json")
        async with self._session_maker() as session:
            stmt = (
                pg_insert(PGResearchJobORM)
                .values(
                    id=job.id,
                    kind=job.kind,
                    name=job.name,
                    spec_ref=job.spec_ref,
                    status=job.status.value,
                    run_result_id=job.run_result_id,
                    created_at=job.created_at,
                    started_at=job.started_at,
                    finished_at=job.finished_at,
                    requested_by=job.requested_by,
                    error_code=job.error_code,
                    error_message=job.error_message,
                    progress_pct=job.progress_pct,
                    spec_payload=payload,
                )
                .on_conflict_do_update(
                    index_elements=[PGResearchJobORM.id],
                    set_={
                        "name": job.name,
                        "status": job.status.value,
                        "run_result_id": job.run_result_id,
                        "started_at": job.started_at,
                        "finished_at": job.finished_at,
                        "error_code": job.error_code,
                        "error_message": job.error_message,
                        "progress_pct": job.progress_pct,
                        "spec_payload": payload,
                    },
                )
            )
            await session.execute(stmt)
            await session.commit()

    async def get_job(self, job_id: str) -> Optional[ResearchJob]:
        async with self._session_maker() as session:
            orm = await session.get(PGResearchJobORM, job_id)
            return self._to_job(orm) if orm else None

    async def list_jobs(
        self,
        status: Optional[ResearchJobStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[ResearchJob], int]:
        async with self._session_maker() as session:
            filters = []
            if status is not None:
                filters.append(PGResearchJobORM.status == status.value)
            count_stmt = select(func.count()).select_from(PGResearchJobORM)
            if filters:
                count_stmt = count_stmt.where(*filters)
            total = int((await session.execute(count_stmt)).scalar_one())

            stmt = select(PGResearchJobORM)
            if filters:
                stmt = stmt.where(*filters)
            stmt = stmt.order_by(PGResearchJobORM.created_at.desc()).limit(limit).offset(offset)
            rows = (await session.execute(stmt)).scalars().all()
            return [self._to_job(row) for row in rows], total

    async def mark_job_running(self, job_id: str) -> None:
        async with self._session_maker() as session:
            await session.execute(
                update(PGResearchJobORM)
                .where(
                    PGResearchJobORM.id == job_id,
                    PGResearchJobORM.status == ResearchJobStatus.PENDING.value,
                )
                .values(
                    status=ResearchJobStatus.RUNNING.value,
                    started_at=utc_now_iso(),
                    progress_pct=0,
                )
            )
            await session.commit()

    async def mark_job_succeeded(self, job_id: str, run_result_id: str) -> None:
        async with self._session_maker() as session:
            await session.execute(
                update(PGResearchJobORM)
                .where(PGResearchJobORM.id == job_id)
                .values(
                    status=ResearchJobStatus.SUCCEEDED.value,
                    run_result_id=run_result_id,
                    finished_at=utc_now_iso(),
                    progress_pct=100,
                    error_code=None,
                    error_message=None,
                )
            )
            await session.commit()

    async def mark_job_failed(self, job_id: str, error_code: str, error_message: str) -> None:
        async with self._session_maker() as session:
            await session.execute(
                update(PGResearchJobORM)
                .where(PGResearchJobORM.id == job_id)
                .values(
                    status=ResearchJobStatus.FAILED.value,
                    finished_at=utc_now_iso(),
                    error_code=error_code,
                    error_message=error_message,
                )
            )
            await session.commit()

    async def save_run_result(self, result: ResearchRunResult) -> None:
        async with self._session_maker() as session:
            stmt = (
                pg_insert(PGResearchRunResultORM)
                .values(
                    id=result.id,
                    job_id=result.job_id,
                    kind=result.kind,
                    spec_snapshot=result.spec_snapshot,
                    summary_metrics=result.summary_metrics,
                    artifact_index=result.artifact_index,
                    source_profile=result.source_profile,
                    generated_at=result.generated_at,
                )
                .on_conflict_do_update(
                    index_elements=[PGResearchRunResultORM.id],
                    set_={
                        "spec_snapshot": result.spec_snapshot,
                        "summary_metrics": result.summary_metrics,
                        "artifact_index": result.artifact_index,
                        "source_profile": result.source_profile,
                        "generated_at": result.generated_at,
                    },
                )
            )
            await session.execute(stmt)
            await session.commit()

    async def get_run_result(self, result_id: str) -> Optional[ResearchRunResult]:
        async with self._session_maker() as session:
            orm = await session.get(PGResearchRunResultORM, result_id)
            return self._to_run_result(orm) if orm else None

    async def list_run_results(
        self,
        job_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[ResearchRunResult], int]:
        async with self._session_maker() as session:
            filters = []
            if job_id is not None:
                filters.append(PGResearchRunResultORM.job_id == job_id)
            count_stmt = select(func.count()).select_from(PGResearchRunResultORM)
            if filters:
                count_stmt = count_stmt.where(*filters)
            total = int((await session.execute(count_stmt)).scalar_one())

            stmt = select(PGResearchRunResultORM)
            if filters:
                stmt = stmt.where(*filters)
            stmt = stmt.order_by(PGResearchRunResultORM.generated_at.desc()).limit(limit).offset(offset)
            rows = (await session.execute(stmt)).scalars().all()
            return [self._to_run_result(row) for row in rows], total

    async def save_candidate(self, candidate: CandidateRecord) -> None:
        async with self._session_maker() as session:
            stmt = (
                pg_insert(PGCandidateRecordORM)
                .values(
                    id=candidate.id,
                    run_result_id=candidate.run_result_id,
                    candidate_name=candidate.candidate_name,
                    status=candidate.status.value,
                    review_notes=candidate.review_notes,
                    applicable_market=candidate.applicable_market,
                    risks=candidate.risks,
                    recommendation=candidate.recommendation,
                    created_at=candidate.created_at,
                    updated_at=candidate.updated_at,
                )
                .on_conflict_do_update(
                    index_elements=[PGCandidateRecordORM.id],
                    set_={
                        "candidate_name": candidate.candidate_name,
                        "status": candidate.status.value,
                        "review_notes": candidate.review_notes,
                        "applicable_market": candidate.applicable_market,
                        "risks": candidate.risks,
                        "recommendation": candidate.recommendation,
                        "updated_at": candidate.updated_at,
                    },
                )
            )
            await session.execute(stmt)
            await session.commit()

    async def get_candidate(self, candidate_id: str) -> Optional[CandidateRecord]:
        async with self._session_maker() as session:
            orm = await session.get(PGCandidateRecordORM, candidate_id)
            return self._to_candidate(orm) if orm else None

    async def list_candidates(
        self,
        status: Optional[CandidateStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[CandidateRecord], int]:
        async with self._session_maker() as session:
            filters = []
            if status is not None:
                filters.append(PGCandidateRecordORM.status == status.value)
            count_stmt = select(func.count()).select_from(PGCandidateRecordORM)
            if filters:
                count_stmt = count_stmt.where(*filters)
            total = int((await session.execute(count_stmt)).scalar_one())

            stmt = select(PGCandidateRecordORM)
            if filters:
                stmt = stmt.where(*filters)
            stmt = stmt.order_by(PGCandidateRecordORM.updated_at.desc()).limit(limit).offset(offset)
            rows = (await session.execute(stmt)).scalars().all()
            return [self._to_candidate(row) for row in rows], total

    def _to_job(self, orm: PGResearchJobORM) -> ResearchJob:
        return ResearchJob(
            id=orm.id,
            kind=orm.kind,
            name=orm.name,
            spec_ref=orm.spec_ref,
            status=ResearchJobStatus(orm.status),
            run_result_id=orm.run_result_id,
            created_at=orm.created_at,
            started_at=orm.started_at,
            finished_at=orm.finished_at,
            requested_by=orm.requested_by,
            error_code=orm.error_code,
            error_message=orm.error_message,
            progress_pct=orm.progress_pct,
            spec=ResearchSpec(**orm.spec_payload),
        )

    def _to_run_result(self, orm: PGResearchRunResultORM) -> ResearchRunResult:
        return ResearchRunResult(
            id=orm.id,
            job_id=orm.job_id,
            kind=orm.kind,
            spec_snapshot=orm.spec_snapshot,
            summary_metrics=orm.summary_metrics,
            artifact_index=orm.artifact_index,
            source_profile=orm.source_profile,
            generated_at=orm.generated_at,
        )

    def _to_candidate(self, orm: PGCandidateRecordORM) -> CandidateRecord:
        return CandidateRecord(
            id=orm.id,
            run_result_id=orm.run_result_id,
            candidate_name=orm.candidate_name,
            status=CandidateStatus(orm.status),
            review_notes=orm.review_notes,
            applicable_market=orm.applicable_market,
            risks=orm.risks,
            recommendation=orm.recommendation,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )
