"""PG repository for LS-002b daily risk stats persistence."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import (
    PGDailyRiskStatsAggregateORM,
    PGDailyRiskStatsEventORM,
)
from src.infrastructure.repository_ports import (
    DailyRiskStatsEvent,
    DailyRiskStatsSnapshot,
    DailyRiskStatsWriteResult,
)


class PgDailyRiskStatsRepository:
    """PG aggregate + event ledger for daily risk stats."""

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def restore_or_create(
        self,
        scope_key: str,
        stats_date: date,
    ) -> DailyRiskStatsSnapshot:
        async with self._session_maker() as session:
            async with session.begin():
                aggregate = await self._get_or_create_aggregate(
                    session=session,
                    scope_key=scope_key,
                    stats_date=stats_date,
                    for_update=False,
                )
                return self._to_snapshot(aggregate)

    async def record_event(
        self,
        event: DailyRiskStatsEvent,
    ) -> DailyRiskStatsWriteResult:
        async with self._session_maker() as session:
            async with session.begin():
                existing_event = await session.get(PGDailyRiskStatsEventORM, event.event_key)
                if existing_event is not None:
                    snapshot = await self._get_or_create_snapshot(
                        session=session,
                        scope_key=event.scope_key,
                        stats_date=event.stats_date,
                    )
                    return DailyRiskStatsWriteResult(snapshot=snapshot, inserted=False)

                aggregate = await self._get_or_create_aggregate(
                    session=session,
                    scope_key=event.scope_key,
                    stats_date=event.stats_date,
                    for_update=True,
                )
                now = datetime.now(timezone.utc)
                try:
                    async with session.begin_nested():
                        session.add(
                            PGDailyRiskStatsEventORM(
                                event_key=event.event_key,
                                scope_key=event.scope_key,
                                stats_date=event.stats_date,
                                source=event.source,
                                position_id=event.position_id,
                                signal_id=event.signal_id,
                                exit_order_id=event.exit_order_id,
                                delta_exit_qty=event.delta_exit_qty,
                                delta_realized_pnl=event.delta_realized_pnl,
                                trade_count_delta=event.trade_count_delta,
                                occurred_at=event.occurred_at,
                                created_at=now,
                            )
                        )
                        await session.flush()
                except IntegrityError:
                    snapshot = await self._get_or_create_snapshot(
                        session=session,
                        scope_key=event.scope_key,
                        stats_date=event.stats_date,
                    )
                    return DailyRiskStatsWriteResult(snapshot=snapshot, inserted=False)
                aggregate.realized_pnl = (
                    Decimal(str(aggregate.realized_pnl or "0"))
                    + event.delta_realized_pnl
                )
                aggregate.trade_count = int(aggregate.trade_count or 0) + event.trade_count_delta
                aggregate.last_event_key = event.event_key
                aggregate.updated_at = now
                await session.flush()
                return DailyRiskStatsWriteResult(
                    snapshot=self._to_snapshot(aggregate),
                    inserted=True,
                )

    async def get(
        self,
        scope_key: str,
        stats_date: date,
    ) -> Optional[DailyRiskStatsSnapshot]:
        async with self._session_maker() as session:
            aggregate = await session.get(
                PGDailyRiskStatsAggregateORM,
                {"scope_key": scope_key, "stats_date": stats_date},
            )
            return self._to_snapshot(aggregate) if aggregate is not None else None

    async def _get_or_create_snapshot(
        self,
        *,
        session: AsyncSession,
        scope_key: str,
        stats_date: date,
    ) -> DailyRiskStatsSnapshot:
        aggregate = await self._get_or_create_aggregate(
            session=session,
            scope_key=scope_key,
            stats_date=stats_date,
            for_update=False,
        )
        return self._to_snapshot(aggregate)

    async def _get_or_create_aggregate(
        self,
        *,
        session: AsyncSession,
        scope_key: str,
        stats_date: date,
        for_update: bool,
    ) -> PGDailyRiskStatsAggregateORM:
        stmt = select(PGDailyRiskStatsAggregateORM).where(
            PGDailyRiskStatsAggregateORM.scope_key == scope_key,
            PGDailyRiskStatsAggregateORM.stats_date == stats_date,
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await session.execute(stmt)
        aggregate = result.scalar_one_or_none()
        if aggregate is not None:
            return aggregate
        now = datetime.now(timezone.utc)
        aggregate = PGDailyRiskStatsAggregateORM(
            scope_key=scope_key,
            stats_date=stats_date,
            realized_pnl=Decimal("0"),
            trade_count=0,
            created_at=now,
            updated_at=now,
        )
        try:
            async with session.begin_nested():
                session.add(aggregate)
                await session.flush()
        except IntegrityError:
            stmt = select(PGDailyRiskStatsAggregateORM).where(
                PGDailyRiskStatsAggregateORM.scope_key == scope_key,
                PGDailyRiskStatsAggregateORM.stats_date == stats_date,
            )
            if for_update:
                stmt = stmt.with_for_update()
            result = await session.execute(stmt)
            aggregate = result.scalar_one()
        return aggregate

    @staticmethod
    def _to_snapshot(aggregate: PGDailyRiskStatsAggregateORM) -> DailyRiskStatsSnapshot:
        return DailyRiskStatsSnapshot(
            scope_key=aggregate.scope_key,
            stats_date=aggregate.stats_date,
            realized_pnl=Decimal(str(aggregate.realized_pnl or "0")),
            trade_count=int(aggregate.trade_count or 0),
        )
