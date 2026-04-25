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
                .order_by(PGPositionORM.opened_at.asc())
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
                .where(PGPositionORM.is_closed.is_(False))
                .order_by(PGPositionORM.updated_at.desc())
                .limit(limit)
            )
            if symbol:
                stmt = stmt.where(PGPositionORM.symbol == symbol)
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

        payload = {
            "tp_trailing_activated": position.tp_trailing_activated,
            "original_tp_prices": {
                key: str(value) for key, value in position.original_tp_prices.items()
            },
            "trailing_exit_activated": position.trailing_exit_activated,
            "trailing_exit_price": str(position.trailing_exit_price) if position.trailing_exit_price is not None else None,
            "trailing_activation_time": position.trailing_activation_time,
            "total_fees_paid": str(position.total_fees_paid),
            "total_funding_paid": str(position.total_funding_paid),
            "watermark_price": str(position.watermark_price) if position.watermark_price is not None else None,
        }

        opened_at = getattr(position, "opened_at", None) or (existing.opened_at if existing else _now_ms())
        closed_at = getattr(position, "closed_at", None)
        if closed_at is None and existing is not None:
            closed_at = existing.closed_at
        return PGPositionORM(
            id=position.id,
            signal_id=position.signal_id,
            symbol=position.symbol,
            direction=position.direction.value,
            quantity=position.current_qty,
            entry_price=position.entry_price,
            mark_price=getattr(position, "mark_price", None) or (existing.mark_price if existing else None),
            leverage=getattr(position, "leverage", None) or (existing.leverage if existing else None),
            unrealized_pnl=getattr(position, "unrealized_pnl", None) if getattr(position, "unrealized_pnl", None) is not None else (existing.unrealized_pnl if existing else None),
            realized_pnl=position.realized_pnl,
            is_closed=position.is_closed,
            opened_at=opened_at,
            closed_at=closed_at,
            updated_at=_now_ms(),
            position_payload=payload,
        )

    @staticmethod
    def _to_domain(orm: PGPositionORM) -> Position:
        payload = orm.position_payload or {}
        watermark_raw = payload.get("watermark_price")
        trailing_exit_price_raw = payload.get("trailing_exit_price")
        total_fees_raw = payload.get("total_fees_paid", "0")
        total_funding_raw = payload.get("total_funding_paid", "0")
        original_tp_prices_raw = payload.get("original_tp_prices") or {}

        return Position(
            id=orm.id,
            signal_id=orm.signal_id or "",
            symbol=orm.symbol,
            direction=Direction(orm.direction),
            entry_price=orm.entry_price or Decimal("0"),
            current_qty=orm.quantity,
            watermark_price=Decimal(watermark_raw) if watermark_raw is not None else None,
            tp_trailing_activated=bool(payload.get("tp_trailing_activated", False)),
            original_tp_prices={
                key: Decimal(value) for key, value in original_tp_prices_raw.items()
            },
            trailing_exit_activated=bool(payload.get("trailing_exit_activated", False)),
            trailing_exit_price=Decimal(trailing_exit_price_raw) if trailing_exit_price_raw is not None else None,
            trailing_activation_time=payload.get("trailing_activation_time"),
            realized_pnl=orm.realized_pnl or Decimal("0"),
            total_fees_paid=Decimal(total_fees_raw),
            total_funding_paid=Decimal(total_funding_raw),
            is_closed=orm.is_closed,
        )
