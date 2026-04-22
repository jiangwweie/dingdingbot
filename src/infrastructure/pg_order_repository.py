"""
PostgreSQL Order Repository - PG 核心订单仓储

这是双轨迁移阶段新增的 PG 实现，不替换现有 SQLite OrderRepository。
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.models import Direction, Order, OrderRole, OrderStatus, OrderType
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import PGOrderORM


class PgOrderRepository:
    """PG 版订单仓储。"""

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def close(self) -> None:
        return None

    async def save(self, order: Order) -> None:
        async with self._session_maker() as session:
            await session.merge(self._to_orm(order))
            await session.commit()

    async def save_batch(self, orders: List[Order]) -> None:
        async with self._session_maker() as session:
            for order in orders:
                await session.merge(self._to_orm(order))
            await session.commit()

    async def get_order(self, order_id: str) -> Optional[Order]:
        async with self._session_maker() as session:
            orm = await session.get(PGOrderORM, order_id)
            return self._to_domain(orm) if orm else None

    async def get_order_by_exchange_id(self, exchange_order_id: str) -> Optional[Order]:
        async with self._session_maker() as session:
            stmt = select(PGOrderORM).where(PGOrderORM.exchange_order_id == exchange_order_id)
            result = await session.execute(stmt)
            orm = result.scalar_one_or_none()
            return self._to_domain(orm) if orm else None

    async def get_orders_by_signal(self, signal_id: str) -> List[Order]:
        async with self._session_maker() as session:
            stmt = (
                select(PGOrderORM)
                .where(PGOrderORM.signal_id == signal_id)
                .order_by(PGOrderORM.created_at.asc())
            )
            result = await session.execute(stmt)
            return [self._to_domain(orm) for orm in result.scalars().all()]

    async def get_orders_by_symbol(self, symbol: str, limit: int = 100) -> List[Order]:
        async with self._session_maker() as session:
            stmt = (
                select(PGOrderORM)
                .where(PGOrderORM.symbol == symbol)
                .order_by(PGOrderORM.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            return [self._to_domain(orm) for orm in result.scalars().all()]

    async def get_orders_by_status(
        self,
        status: OrderStatus,
        symbol: Optional[str] = None,
    ) -> List[Order]:
        async with self._session_maker() as session:
            stmt = select(PGOrderORM).where(PGOrderORM.status == status.value)
            if symbol:
                stmt = stmt.where(PGOrderORM.symbol == symbol)
            stmt = stmt.order_by(PGOrderORM.created_at.desc())
            result = await session.execute(stmt)
            return [self._to_domain(orm) for orm in result.scalars().all()]

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        async with self._session_maker() as session:
            stmt = select(PGOrderORM).where(
                PGOrderORM.status.in_(
                    [OrderStatus.OPEN.value, OrderStatus.PARTIALLY_FILLED.value]
                )
            )
            if symbol:
                stmt = stmt.where(PGOrderORM.symbol == symbol)
            stmt = stmt.order_by(PGOrderORM.created_at.desc())
            result = await session.execute(stmt)
            return [self._to_domain(orm) for orm in result.scalars().all()]

    @staticmethod
    def _to_orm(order: Order) -> PGOrderORM:
        return PGOrderORM(
            id=order.id,
            signal_id=order.signal_id,
            exchange_order_id=order.exchange_order_id,
            symbol=order.symbol,
            direction=order.direction.value,
            order_type=order.order_type.value,
            order_role=order.order_role.value,
            price=order.price,
            trigger_price=order.trigger_price,
            requested_qty=order.requested_qty,
            filled_qty=order.filled_qty,
            average_exec_price=order.average_exec_price,
            status=order.status.value,
            reduce_only=order.reduce_only,
            parent_order_id=order.parent_order_id,
            oco_group_id=order.oco_group_id,
            exit_reason=order.exit_reason,
            filled_at=order.filled_at,
            created_at=order.created_at,
            updated_at=order.updated_at,
        )

    @staticmethod
    def _to_domain(orm: PGOrderORM) -> Order:
        return Order(
            id=orm.id,
            signal_id=orm.signal_id,
            exchange_order_id=orm.exchange_order_id,
            symbol=orm.symbol,
            direction=Direction(orm.direction),
            order_type=OrderType(orm.order_type),
            order_role=OrderRole(orm.order_role),
            price=orm.price,
            trigger_price=orm.trigger_price,
            requested_qty=orm.requested_qty,
            filled_qty=orm.filled_qty,
            average_exec_price=orm.average_exec_price,
            status=OrderStatus(orm.status),
            created_at=orm.created_at,
            updated_at=orm.updated_at,
            exit_reason=orm.exit_reason,
            reduce_only=orm.reduce_only,
            parent_order_id=orm.parent_order_id,
            oco_group_id=orm.oco_group_id,
            filled_at=orm.filled_at,
        )
