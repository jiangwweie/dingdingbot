"""PostgreSQL reconciliation repository."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.models import DiscrepancyType, ReconciliationReport, ReconciliationType
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.logger import setup_logger
from src.infrastructure.pg_models import PGReconciliationDetailORM, PGReconciliationReportORM
from src.infrastructure.reconciliation_repository import ReconciliationRepository

logger = setup_logger(__name__)


class PgReconciliationRepository(ReconciliationRepository):
    """PG implementation for reconciliation report history."""

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def close(self) -> None:
        return None

    async def save_report(
        self,
        report: ReconciliationReport,
        reconciliation_type: ReconciliationType = ReconciliationType.STARTUP,
    ) -> str:
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        report_id = str(report.reconciliation_time)

        actions_taken = []
        for ghost in report.ghost_orders:
            actions_taken.append({"action": "mark_cancelled", "order_id": ghost.order_id, "symbol": ghost.symbol})
        for imported in report.imported_orders:
            actions_taken.append({"action": "import_order", "order_id": imported.order_id, "symbol": imported.symbol})
        for canceled in report.canceled_orphan_orders:
            actions_taken.append({"action": "cancel_order", "order_id": canceled.order_id, "symbol": canceled.symbol})

        async with self._session_maker() as session:
            session.add(
                PGReconciliationReportORM(
                    report_id=report_id,
                    symbol=report.symbol,
                    reconciliation_type=reconciliation_type.value,
                    started_at=report.reconciliation_time,
                    completed_at=current_time,
                    grace_period_seconds=report.grace_period_seconds,
                    is_consistent=report.is_consistent,
                    total_discrepancies=report.total_discrepancies,
                    ghost_orders_count=len(report.ghost_orders),
                    orphan_orders_count=len(report.orphan_orders) + len(report.canceled_orphan_orders),
                    position_mismatch_count=len(report.position_mismatches) + len(report.missing_positions),
                    actions_taken=actions_taken,
                    created_at=current_time,
                    updated_at=current_time,
                )
            )
            for ghost in report.ghost_orders:
                await self._add_detail(
                    session,
                    report_id,
                    DiscrepancyType.GHOST_ORDER,
                    {"order_id": ghost.order_id, "symbol": ghost.symbol, "local_status": ghost.local_status.value},
                    {},
                    "MARKED_CANCELLED",
                    {"action": ghost.action_taken},
                    True,
                )
            for orphan in report.orphan_orders:
                await self._add_detail(
                    session,
                    report_id,
                    DiscrepancyType.ORPHAN_ORDER,
                    None,
                    self._order_to_dict(orphan),
                    "PENDING",
                    None,
                    False,
                )
            for imported in report.imported_orders:
                await self._add_detail(
                    session,
                    report_id,
                    DiscrepancyType.ORPHAN_ORDER,
                    None,
                    self._imported_order_to_dict(imported),
                    "IMPORTED_TO_DB",
                    {"action": imported.action_taken},
                    True,
                )
            for canceled in report.canceled_orphan_orders:
                await self._add_detail(
                    session,
                    report_id,
                    DiscrepancyType.ORPHAN_ORDER,
                    None,
                    self._imported_order_to_dict(canceled),
                    "CANCELLED",
                    {"action": canceled.action_taken},
                    True,
                )
            await session.commit()

        logger.info(f"PG 对账报告已保存：report_id={report_id}, symbol={report.symbol}")
        return report_id

    async def _add_detail(
        self,
        session: AsyncSession,
        report_id: str,
        discrepancy_type: DiscrepancyType,
        local_data: Optional[dict[str, Any]],
        exchange_data: dict[str, Any],
        action_taken: Optional[str],
        action_result: Optional[dict[str, Any]],
        resolved: bool,
    ) -> None:
        session.add(
            PGReconciliationDetailORM(
                report_id=report_id,
                discrepancy_type=discrepancy_type.value,
                local_data=local_data,
                exchange_data=exchange_data,
                action_taken=action_taken,
                action_result=action_result,
                resolved=resolved,
                created_at=int(datetime.now(timezone.utc).timestamp() * 1000),
            )
        )

    async def get_report(self, report_id: str) -> Optional[dict[str, Any]]:
        async with self._session_maker() as session:
            stmt = select(PGReconciliationReportORM).where(PGReconciliationReportORM.report_id == report_id)
            row = (await session.execute(stmt)).scalar_one_or_none()
            return self._report_dict(row) if row else None

    async def get_reports_by_symbol(self, symbol: str, limit: int = 100) -> list[dict[str, Any]]:
        return await self._list_reports(PGReconciliationReportORM.symbol == symbol, limit)

    async def get_reports_by_type(
        self,
        reconciliation_type: ReconciliationType,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return await self._list_reports(PGReconciliationReportORM.reconciliation_type == reconciliation_type.value, limit)

    async def get_recent_reports(self, limit: int = 100) -> list[dict[str, Any]]:
        return await self._list_reports(None, limit)

    async def get_report_details(self, report_id: str) -> list[dict[str, Any]]:
        async with self._session_maker() as session:
            stmt = (
                select(PGReconciliationDetailORM)
                .where(PGReconciliationDetailORM.report_id == report_id)
                .order_by(PGReconciliationDetailORM.created_at.asc())
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [self._detail_dict(row) for row in rows]

    async def get_inconsistent_reports(self, limit: int = 100) -> list[dict[str, Any]]:
        return await self._list_reports(PGReconciliationReportORM.is_consistent.is_(False), limit)

    async def clear_reports(self, symbol: Optional[str] = None) -> int:
        async with self._session_maker() as session:
            if symbol:
                report_ids = list(
                    (
                        await session.execute(
                            select(PGReconciliationReportORM.report_id).where(PGReconciliationReportORM.symbol == symbol)
                        )
                    ).scalars().all()
                )
                if report_ids:
                    await session.execute(
                        delete(PGReconciliationDetailORM).where(PGReconciliationDetailORM.report_id.in_(report_ids))
                    )
                result = await session.execute(
                    delete(PGReconciliationReportORM).where(PGReconciliationReportORM.symbol == symbol)
                )
            else:
                await session.execute(delete(PGReconciliationDetailORM))
                result = await session.execute(delete(PGReconciliationReportORM))
            await session.commit()
            return result.rowcount or 0

    async def _list_reports(self, filter_expr: Any, limit: int) -> list[dict[str, Any]]:
        async with self._session_maker() as session:
            stmt = select(PGReconciliationReportORM)
            if filter_expr is not None:
                stmt = stmt.where(filter_expr)
            stmt = stmt.order_by(PGReconciliationReportORM.started_at.desc()).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return [self._report_dict(row) for row in rows]

    def _report_dict(self, row: PGReconciliationReportORM) -> dict[str, Any]:
        return {
            "id": row.id,
            "report_id": row.report_id,
            "symbol": row.symbol,
            "reconciliation_type": row.reconciliation_type,
            "started_at": row.started_at,
            "completed_at": row.completed_at,
            "grace_period_seconds": row.grace_period_seconds,
            "is_consistent": 1 if row.is_consistent else 0,
            "total_discrepancies": row.total_discrepancies,
            "ghost_orders_count": row.ghost_orders_count,
            "orphan_orders_count": row.orphan_orders_count,
            "position_mismatch_count": row.position_mismatch_count,
            "actions_taken": row.actions_taken,
            "error_code": row.error_code,
            "error_message": row.error_message,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    def _detail_dict(self, row: PGReconciliationDetailORM) -> dict[str, Any]:
        return {
            "id": row.id,
            "report_id": row.report_id,
            "discrepancy_type": row.discrepancy_type,
            "local_data": row.local_data,
            "exchange_data": row.exchange_data,
            "action_taken": row.action_taken,
            "action_result": row.action_result,
            "resolved": 1 if row.resolved else 0,
            "created_at": row.created_at,
        }
