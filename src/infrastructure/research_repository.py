"""SQLite repository for the research control plane."""

from __future__ import annotations

import json
import os
from typing import Optional

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
from src.infrastructure.logger import setup_logger

logger = setup_logger(__name__)


class ResearchRepository:
    """Persists research jobs/results/candidates outside runtime truth stores."""

    def __init__(
        self,
        db_path: str = "data/research_control_plane.db",
        connection: Optional[aiosqlite.Connection] = None,
    ):
        self.db_path = db_path
        self._db = connection
        self._owns_connection = connection is None

    async def initialize(self) -> None:
        if self._owns_connection and self._db is None:
            db_dir = os.path.dirname(self.db_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)
            self._db = await aiosqlite.connect(self.db_path)

        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA foreign_keys = ON")
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS research_jobs (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL CHECK (kind IN ('backtest')),
                name TEXT NOT NULL,
                spec_ref TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELED')),
                run_result_id TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                requested_by TEXT NOT NULL DEFAULT 'local',
                error_code TEXT,
                error_message TEXT,
                progress_pct INTEGER,
                spec_json TEXT NOT NULL
            )
        """)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS research_run_results (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                kind TEXT NOT NULL CHECK (kind IN ('backtest')),
                spec_snapshot_json TEXT NOT NULL,
                summary_metrics_json TEXT NOT NULL,
                artifact_index_json TEXT NOT NULL,
                source_profile TEXT,
                generated_at TEXT NOT NULL,
                FOREIGN KEY(job_id) REFERENCES research_jobs(id)
            )
        """)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS candidate_records (
                id TEXT PRIMARY KEY,
                run_result_id TEXT NOT NULL,
                candidate_name TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('DRAFT', 'REVIEWED', 'REJECTED', 'RECOMMENDED')),
                review_notes TEXT NOT NULL DEFAULT '',
                applicable_market TEXT,
                risks_json TEXT NOT NULL DEFAULT '[]',
                recommendation TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(run_result_id) REFERENCES research_run_results(id)
            )
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_research_jobs_status_created
            ON research_jobs(status, created_at DESC)
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_research_results_job
            ON research_run_results(job_id)
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_candidate_records_status_updated
            ON candidate_records(status, updated_at DESC)
        """)
        await self._db.commit()
        logger.info("Research control plane repository initialized")

    async def close(self) -> None:
        if self._owns_connection and self._db is not None:
            await self._db.close()
        self._db = None

    async def save_job(self, job: ResearchJob) -> None:
        await self._db.execute(
            """
            INSERT INTO research_jobs (
                id, kind, name, spec_ref, status, run_result_id, created_at,
                started_at, finished_at, requested_by, error_code,
                error_message, progress_pct, spec_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                status=excluded.status,
                run_result_id=excluded.run_result_id,
                started_at=excluded.started_at,
                finished_at=excluded.finished_at,
                error_code=excluded.error_code,
                error_message=excluded.error_message,
                progress_pct=excluded.progress_pct,
                spec_json=excluded.spec_json
            """,
            (
                job.id,
                job.kind,
                job.name,
                job.spec_ref,
                job.status.value,
                job.run_result_id,
                job.created_at,
                job.started_at,
                job.finished_at,
                job.requested_by,
                job.error_code,
                job.error_message,
                job.progress_pct,
                self._to_json(job.spec.model_dump(mode="json")),
            ),
        )
        await self._db.commit()

    async def get_job(self, job_id: str) -> Optional[ResearchJob]:
        cursor = await self._db.execute("SELECT * FROM research_jobs WHERE id = ?", (job_id,))
        row = await cursor.fetchone()
        return self._row_to_job(row) if row else None

    async def list_jobs(
        self,
        status: Optional[ResearchJobStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[ResearchJob], int]:
        params: list[object] = []
        where = ""
        if status is not None:
            where = "WHERE status = ?"
            params.append(status.value)

        count_cursor = await self._db.execute(
            f"SELECT COUNT(*) AS total FROM research_jobs {where}",
            params,
        )
        total_row = await count_cursor.fetchone()
        total = int(total_row["total"]) if total_row else 0

        cursor = await self._db.execute(
            f"""
            SELECT * FROM research_jobs
            {where}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        )
        rows = await cursor.fetchall()
        return [self._row_to_job(row) for row in rows], total

    async def mark_job_running(self, job_id: str) -> None:
        await self._db.execute(
            """
            UPDATE research_jobs
            SET status = ?, started_at = ?, progress_pct = ?
            WHERE id = ? AND status = ?
            """,
            (ResearchJobStatus.RUNNING.value, utc_now_iso(), 0, job_id, ResearchJobStatus.PENDING.value),
        )
        await self._db.commit()

    async def mark_job_succeeded(self, job_id: str, run_result_id: str) -> None:
        await self._db.execute(
            """
            UPDATE research_jobs
            SET status = ?, run_result_id = ?, finished_at = ?, progress_pct = ?,
                error_code = NULL, error_message = NULL
            WHERE id = ?
            """,
            (ResearchJobStatus.SUCCEEDED.value, run_result_id, utc_now_iso(), 100, job_id),
        )
        await self._db.commit()

    async def mark_job_failed(self, job_id: str, error_code: str, error_message: str) -> None:
        await self._db.execute(
            """
            UPDATE research_jobs
            SET status = ?, finished_at = ?, error_code = ?, error_message = ?
            WHERE id = ?
            """,
            (ResearchJobStatus.FAILED.value, utc_now_iso(), error_code, error_message, job_id),
        )
        await self._db.commit()

    async def save_run_result(self, result: ResearchRunResult) -> None:
        await self._db.execute(
            """
            INSERT INTO research_run_results (
                id, job_id, kind, spec_snapshot_json, summary_metrics_json,
                artifact_index_json, source_profile, generated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                spec_snapshot_json=excluded.spec_snapshot_json,
                summary_metrics_json=excluded.summary_metrics_json,
                artifact_index_json=excluded.artifact_index_json,
                source_profile=excluded.source_profile,
                generated_at=excluded.generated_at
            """,
            (
                result.id,
                result.job_id,
                result.kind,
                self._to_json(result.spec_snapshot),
                self._to_json(result.summary_metrics),
                self._to_json(result.artifact_index),
                result.source_profile,
                result.generated_at,
            ),
        )
        await self._db.commit()

    async def get_run_result(self, result_id: str) -> Optional[ResearchRunResult]:
        cursor = await self._db.execute(
            "SELECT * FROM research_run_results WHERE id = ?",
            (result_id,),
        )
        row = await cursor.fetchone()
        return self._row_to_run_result(row) if row else None

    async def list_run_results(
        self,
        job_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[ResearchRunResult], int]:
        params: list[object] = []
        where = ""
        if job_id is not None:
            where = "WHERE job_id = ?"
            params.append(job_id)

        count_cursor = await self._db.execute(
            f"SELECT COUNT(*) AS total FROM research_run_results {where}",
            params,
        )
        total_row = await count_cursor.fetchone()
        total = int(total_row["total"]) if total_row else 0

        cursor = await self._db.execute(
            f"""
            SELECT * FROM research_run_results
            {where}
            ORDER BY generated_at DESC
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        )
        rows = await cursor.fetchall()
        return [self._row_to_run_result(row) for row in rows], total

    async def save_candidate(self, candidate: CandidateRecord) -> None:
        await self._db.execute(
            """
            INSERT INTO candidate_records (
                id, run_result_id, candidate_name, status, review_notes,
                applicable_market, risks_json, recommendation, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                candidate_name=excluded.candidate_name,
                status=excluded.status,
                review_notes=excluded.review_notes,
                applicable_market=excluded.applicable_market,
                risks_json=excluded.risks_json,
                recommendation=excluded.recommendation,
                updated_at=excluded.updated_at
            """,
            (
                candidate.id,
                candidate.run_result_id,
                candidate.candidate_name,
                candidate.status.value,
                candidate.review_notes,
                candidate.applicable_market,
                self._to_json(candidate.risks),
                candidate.recommendation,
                candidate.created_at,
                candidate.updated_at,
            ),
        )
        await self._db.commit()

    async def get_candidate(self, candidate_id: str) -> Optional[CandidateRecord]:
        cursor = await self._db.execute(
            "SELECT * FROM candidate_records WHERE id = ?",
            (candidate_id,),
        )
        row = await cursor.fetchone()
        return self._row_to_candidate(row) if row else None

    async def list_candidates(
        self,
        status: Optional[CandidateStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[CandidateRecord], int]:
        params: list[object] = []
        where = ""
        if status is not None:
            where = "WHERE status = ?"
            params.append(status.value)

        count_cursor = await self._db.execute(
            f"SELECT COUNT(*) AS total FROM candidate_records {where}",
            params,
        )
        total_row = await count_cursor.fetchone()
        total = int(total_row["total"]) if total_row else 0

        cursor = await self._db.execute(
            f"""
            SELECT * FROM candidate_records
            {where}
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        )
        rows = await cursor.fetchall()
        return [self._row_to_candidate(row) for row in rows], total

    def _row_to_job(self, row: aiosqlite.Row) -> ResearchJob:
        return ResearchJob(
            id=row["id"],
            kind=row["kind"],
            name=row["name"],
            spec_ref=row["spec_ref"],
            status=ResearchJobStatus(row["status"]),
            run_result_id=row["run_result_id"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            requested_by=row["requested_by"],
            error_code=row["error_code"],
            error_message=row["error_message"],
            progress_pct=row["progress_pct"],
            spec=ResearchSpec(**json.loads(row["spec_json"])),
        )

    def _row_to_run_result(self, row: aiosqlite.Row) -> ResearchRunResult:
        return ResearchRunResult(
            id=row["id"],
            job_id=row["job_id"],
            kind=row["kind"],
            spec_snapshot=json.loads(row["spec_snapshot_json"]),
            summary_metrics=json.loads(row["summary_metrics_json"]),
            artifact_index=json.loads(row["artifact_index_json"]),
            source_profile=row["source_profile"],
            generated_at=row["generated_at"],
        )

    def _row_to_candidate(self, row: aiosqlite.Row) -> CandidateRecord:
        return CandidateRecord(
            id=row["id"],
            run_result_id=row["run_result_id"],
            candidate_name=row["candidate_name"],
            status=CandidateStatus(row["status"]),
            review_notes=row["review_notes"],
            applicable_market=row["applicable_market"],
            risks=json.loads(row["risks_json"]),
            recommendation=row["recommendation"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _to_json(self, value: object) -> str:
        return json.dumps(value, ensure_ascii=False, default=str)
