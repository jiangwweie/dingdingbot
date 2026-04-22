"""
PostgreSQL Position Repository - PG 核心仓位仓储

第一阶段仅提供最小骨架能力，用于后续把 PositionManager / 恢复链逐步切到 PG。
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import PGPositionORM


class PgPositionRepository:
    """PG 版仓位仓储。"""

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def close(self) -> None:
        return None

    async def save(self, position: PGPositionORM) -> None:
        async with self._session_maker() as session:
            await session.merge(position)
            await session.commit()

    async def get(self, position_id: str) -> Optional[PGPositionORM]:
        async with self._session_maker() as session:
            return await session.get(PGPositionORM, position_id)

    async def get_by_signal_id(self, signal_id: str) -> List[PGPositionORM]:
        async with self._session_maker() as session:
            stmt = (
                select(PGPositionORM)
                .where(PGPositionORM.signal_id == signal_id)
                .order_by(PGPositionORM.created_at.asc())
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
