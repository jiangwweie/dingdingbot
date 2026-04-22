"""
PostgreSQL Position Repository - PG 核心仓位仓储

第一阶段仅提供最小骨架能力，用于后续把 PositionManager / 恢复链逐步切到 PG。

注意：
- 当前实现直接操作 PGPositionORM，不涉及领域模型转换
- 后续迁移时需要添加 _to_domain / _to_orm 转换方法
"""

from __future__ import annotations

from typing import Any, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import PGPositionORM


class PgPositionRepository:
    """PG 版仓位仓储。

    当前阶段：
    - 直接操作 PGPositionORM
    - 不做领域模型转换（Position domain model 有更多字段如 tp_trailing_activated）
    - 调用方需了解 ORM 结构，后续迁移时再收口
    """

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def close(self) -> None:
        return None

    async def save(self, position: Any) -> None:
        """保存仓位。

        Args:
            position: PGPositionORM 实例（当前阶段不自动转换）
        """
        async with self._session_maker() as session:
            if isinstance(position, PGPositionORM):
                await session.merge(position)
            else:
                # 后续可添加领域模型转换逻辑
                raise TypeError(
                    f"Expected PGPositionORM, got {type(position).__name__}. "
                    "Domain model conversion not yet implemented."
                )
            await session.commit()

    async def get(self, position_id: str) -> Optional[PGPositionORM]:
        """获取仓位。

        Returns:
            PGPositionORM 实例（当前阶段不转换为领域模型）
        """
        async with self._session_maker() as session:
            return await session.get(PGPositionORM, position_id)

    async def get_by_signal_id(self, signal_id: str) -> List[PGPositionORM]:
        """按信号 ID 获取仓位列表。

        Returns:
            PGPositionORM 实例列表
        """
        async with self._session_maker() as session:
            stmt = (
                select(PGPositionORM)
                .where(PGPositionORM.signal_id == signal_id)
                .order_by(PGPositionORM.created_at.asc())
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
