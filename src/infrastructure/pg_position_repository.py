"""
PostgreSQL Position Repository - PG 核心仓位仓储

当前阶段提供 execution projection 所需的最小读写能力：
- 接收 Position domain model 或 PGPositionORM
- 返回 Position domain model
- 提供 active positions 查询，供 runtime console fallback 使用
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.models import Direction, Position
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import PGPositionORM


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _db_timestamp(value: Any) -> int:
    """Store timestamps in the legacy positions int column without overflow."""
    raw = int(value if value is not None else _now_ms())
    return raw // 1000 if raw > 2_147_483_647 else raw


def _domain_timestamp(value: Any) -> int:
    raw = int(value or 0)
    return raw * 1000 if 0 < raw < 10_000_000_000 else raw


def _decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    if value is None:
        return default
    return Decimal(str(value))


def _closed_flag(value: bool) -> int:
    return 1 if value else 0


def _is_closed(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return int(value or 0) != 0


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

    async def save(self, position: Any) -> None:
        """保存仓位。"""
        async with self._session_maker() as session:
            if isinstance(position, Position):
                existing = await session.get(PGPositionORM, position.id)
                orm = self._to_orm(position, existing=existing)
            else:
                orm = self._to_orm(position)
            await session.merge(orm)
            await session.commit()

    async def get(self, position_id: str) -> Optional[Position]:
        """获取仓位。"""
        async with self._session_maker() as session:
            orm = await session.get(PGPositionORM, position_id)
            return self._to_domain(orm) if orm else None

    async def get_by_signal_id(self, signal_id: str) -> List[Position]:
        """按信号 ID 获取仓位列表。"""
        async with self._session_maker() as session:
            stmt = (
                select(PGPositionORM)
                .where(PGPositionORM.signal_id == signal_id)
                .order_by(PGPositionORM.created_at.asc())
            )
            result = await session.execute(stmt)
            return [self._to_domain(orm) for orm in result.scalars().all()]

    async def list_active(
        self,
        *,
        symbol: Optional[str] = None,
        limit: int = 100,
    ) -> List[Position]:
        """列出当前未平仓仓位。"""
        async with self._session_maker() as session:
            stmt = (
                select(PGPositionORM)
                .where(PGPositionORM.is_closed == 0)
                .order_by(PGPositionORM.updated_at.desc())
                .limit(limit)
            )
            if symbol:
                stmt = stmt.where(PGPositionORM.symbol == symbol)
            result = await session.execute(stmt)
            return [self._to_domain(orm) for orm in result.scalars().all()]

    async def list_positions(
        self,
        *,
        symbol: Optional[str] = None,
        is_closed: Optional[bool] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Position]:
        """按条件列出仓位，支持已平/未平过滤。"""
        async with self._session_maker() as session:
            stmt = select(PGPositionORM).order_by(PGPositionORM.updated_at.desc())
            if symbol:
                stmt = stmt.where(PGPositionORM.symbol == symbol)
            if is_closed is not None:
                stmt = stmt.where(PGPositionORM.is_closed == _closed_flag(is_closed))
            stmt = stmt.offset(offset).limit(limit)
            result = await session.execute(stmt)
            return [self._to_domain(orm) for orm in result.scalars().all()]

    @staticmethod
    def _to_orm(
        position: Any,
        *,
        existing: Optional[PGPositionORM] = None,
    ) -> PGPositionORM:
        if isinstance(position, PGPositionORM):
            return position

        if not isinstance(position, Position):
            raise TypeError(
                f"Expected Position or PGPositionORM, got {type(position).__name__}."
            )

        opened_at = getattr(position, "opened_at", None) or (
            existing.created_at if existing else _now_ms()
        )
        watermark_price = position.watermark_price or (
            _decimal(existing.highest_price_since_entry)
            if existing is not None
            else position.entry_price
        )
        return PGPositionORM(
            id=position.id,
            signal_id=position.signal_id,
            symbol=position.symbol,
            direction=position.direction.value,
            entry_price=str(position.entry_price),
            current_qty=str(position.current_qty),
            highest_price_since_entry=str(watermark_price),
            realized_pnl=str(position.realized_pnl),
            total_fees_paid=str(position.total_fees_paid),
            is_closed=_closed_flag(position.is_closed),
            created_at=_db_timestamp(opened_at),
            updated_at=_db_timestamp(_now_ms()),
            runtime_instance_id=position.runtime_instance_id,
            trial_binding_id=position.trial_binding_id,
            strategy_family_id=position.strategy_family_id,
            strategy_family_version_id=position.strategy_family_version_id,
            signal_evaluation_id=position.signal_evaluation_id,
            order_candidate_id=position.order_candidate_id,
        )

    @staticmethod
    def _to_domain(orm: PGPositionORM) -> Position:
        return Position(
            id=orm.id,
            signal_id=orm.signal_id or "",
            symbol=orm.symbol,
            direction=Direction(orm.direction),
            entry_price=_decimal(orm.entry_price),
            current_qty=_decimal(orm.current_qty),
            watermark_price=_decimal(orm.highest_price_since_entry),
            realized_pnl=_decimal(orm.realized_pnl),
            total_fees_paid=_decimal(orm.total_fees_paid),
            opened_at=_domain_timestamp(orm.created_at),
            closed_at=None,
            is_closed=_is_closed(orm.is_closed),
            runtime_instance_id=orm.runtime_instance_id,
            trial_binding_id=orm.trial_binding_id,
            strategy_family_id=orm.strategy_family_id,
            strategy_family_version_id=orm.strategy_family_version_id,
            signal_evaluation_id=orm.signal_evaluation_id,
            order_candidate_id=orm.order_candidate_id,
        )
