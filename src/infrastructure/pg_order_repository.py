"""
PostgreSQL Order Repository - PG 核心订单仓储

这是双轨迁移阶段新增的 PG 实现，不替换现有 SQLite OrderRepository。
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, List, Optional

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
        self._exchange_gateway: Optional[Any] = None  # 依赖注入：交易所网关
        self._audit_logger: Optional[Any] = None  # 依赖注入：审计日志器

    def set_exchange_gateway(self, gateway: Any) -> None:
        """设置交易所网关（依赖注入）。"""
        self._exchange_gateway = gateway

    def set_audit_logger(self, logger_instance: Any) -> None:
        """设置审计日志器（依赖注入）。"""
        self._audit_logger = logger_instance

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

    async def update_status(
        self,
        order_id: str,
        status: OrderStatus,
        filled_qty: Optional[Decimal] = None,
        average_exec_price: Optional[Decimal] = None,
        filled_at: Optional[int] = None,
        exchange_order_id: Optional[str] = None,
        exit_reason: Optional[str] = None,
    ) -> None:
        """
        更新订单状态和可选字段。

        Args:
            order_id: 订单 ID
            status: 新状态
            filled_qty: 成交数量（可选）
            average_exec_price: 平均成交价（可选）
            filled_at: 成交时间戳（可选）
            exchange_order_id: 交易所订单 ID（可选）
            exit_reason: 退出原因（可选）
        """
        async with self._session_maker() as session:
            orm = await session.get(PGOrderORM, order_id)
            if orm is None:
                return

            orm.status = status.value
            orm.updated_at = int(datetime.now(timezone.utc).timestamp() * 1000)

            if filled_qty is not None:
                orm.filled_qty = filled_qty
            if average_exec_price is not None:
                orm.average_exec_price = average_exec_price
            if filled_at is not None:
                orm.filled_at = filled_at
            if exchange_order_id is not None:
                orm.exchange_order_id = exchange_order_id
            if exit_reason is not None:
                orm.exit_reason = exit_reason

            await session.commit()

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
