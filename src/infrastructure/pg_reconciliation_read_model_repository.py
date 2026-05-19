"""PG repository for periodic reconciliation read model persistence."""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import (
    PGReconciliationReadModelMismatchORM,
    PGReconciliationReadModelReportORM,
)
from src.infrastructure.repository_ports import (
    ReconciliationReadModelMismatch,
    ReconciliationReadModelReport,
)


class PgReconciliationReadModelRepository:
    """PG-backed persistence for report-only runtime reconciliation observations."""

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def save_report(
        self,
        report: ReconciliationReadModelReport,
        mismatches: List[ReconciliationReadModelMismatch],
    ) -> None:
        async with self._session_maker() as session:
            async with session.begin():
                report_row = PGReconciliationReadModelReportORM(
                    report_id=report.report_id,
                    symbol=report.symbol,
                    checked_at_ms=report.checked_at_ms,
                    is_consistent=report.is_consistent,
                    total_count=report.total_count,
                    severe_count=report.severe_count,
                    warning_count=report.warning_count,
                    is_fetch_failure=report.is_fetch_failure,
                    fetch_failure_reason=report.fetch_failure_reason,
                    created_at=report.created_at,
                )
                session.add(report_row)
                await session.flush()
                for mismatch in mismatches:
                    session.add(
                        PGReconciliationReadModelMismatchORM(
                            report_id=mismatch.report_id,
                            symbol=mismatch.symbol,
                            mismatch_type=mismatch.mismatch_type,
                            severity=mismatch.severity,
                            reason=mismatch.reason,
                            local_ref=mismatch.local_ref,
                            exchange_ref=mismatch.exchange_ref,
                            metadata_json=mismatch.metadata,
                            created_at=mismatch.created_at,
                        )
                    )

    async def get_recent_reports(
        self,
        symbol: Optional[str] = None,
        limit: int = 100,
    ) -> List[ReconciliationReadModelReport]:
        safe_limit = max(0, limit)
        async with self._session_maker() as session:
            stmt = select(PGReconciliationReadModelReportORM)
            if symbol is not None:
                stmt = stmt.where(PGReconciliationReadModelReportORM.symbol == symbol)
            stmt = (
                stmt.order_by(PGReconciliationReadModelReportORM.checked_at_ms.desc())
                .limit(safe_limit)
            )
            result = await session.execute(stmt)
            return [self._to_report(row) for row in result.scalars().all()]

    async def get_mismatches(
        self,
        report_id: str,
    ) -> List[ReconciliationReadModelMismatch]:
        async with self._session_maker() as session:
            stmt = (
                select(PGReconciliationReadModelMismatchORM)
                .where(PGReconciliationReadModelMismatchORM.report_id == report_id)
                .order_by(PGReconciliationReadModelMismatchORM.id.asc())
            )
            result = await session.execute(stmt)
            return [self._to_mismatch(row) for row in result.scalars().all()]

    @staticmethod
    def _to_report(row: PGReconciliationReadModelReportORM) -> ReconciliationReadModelReport:
        return ReconciliationReadModelReport(
            report_id=row.report_id,
            symbol=row.symbol,
            checked_at_ms=row.checked_at_ms,
            is_consistent=row.is_consistent,
            total_count=row.total_count,
            severe_count=row.severe_count,
            warning_count=row.warning_count,
            is_fetch_failure=row.is_fetch_failure,
            fetch_failure_reason=row.fetch_failure_reason,
            created_at=row.created_at,
        )

    @staticmethod
    def _to_mismatch(
        row: PGReconciliationReadModelMismatchORM,
    ) -> ReconciliationReadModelMismatch:
        return ReconciliationReadModelMismatch(
            report_id=row.report_id,
            symbol=row.symbol,
            mismatch_type=row.mismatch_type,
            severity=row.severity,
            reason=row.reason,
            local_ref=row.local_ref,
            exchange_ref=row.exchange_ref,
            metadata=row.metadata_json,
            created_at=row.created_at,
        )
