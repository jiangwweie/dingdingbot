"""
PostgreSQL Execution Intent Repository - PG 执行意图仓储

用于把当前内存态 ExecutionIntent 引入 PG 真源。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.execution_intent import ExecutionIntent, ExecutionIntentStatus
from src.domain.models import OrderStrategy, SignalResult
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import PGExecutionIntentORM


class PgExecutionIntentRepository:
    """PG 版执行意图仓储。"""

    _TERMINAL_STATUSES = {
        ExecutionIntentStatus.BLOCKED.value,
        ExecutionIntentStatus.FAILED.value,
        ExecutionIntentStatus.COMPLETED.value,
    }

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def close(self) -> None:
        return None

    async def save(self, intent: ExecutionIntent) -> None:
        async with self._session_maker() as session:
            await session.merge(self._to_orm(intent))
            await session.commit()

    async def get(self, intent_id: str) -> Optional[ExecutionIntent]:
        async with self._session_maker() as session:
            orm = await session.get(PGExecutionIntentORM, intent_id)
            return self._to_domain(orm) if orm else None

    async def get_by_signal_id(self, signal_id: str) -> Optional[ExecutionIntent]:
        async with self._session_maker() as session:
            stmt = select(PGExecutionIntentORM).where(PGExecutionIntentORM.signal_id == signal_id)
            result = await session.execute(stmt)
            orm = result.scalar_one_or_none()
            return self._to_domain(orm) if orm else None

    async def get_by_order_id(self, order_id: str) -> Optional[ExecutionIntent]:
        async with self._session_maker() as session:
            stmt = select(PGExecutionIntentORM).where(PGExecutionIntentORM.order_id == order_id)
            result = await session.execute(stmt)
            orm = result.scalar_one_or_none()
            return self._to_domain(orm) if orm else None

    async def list_unfinished(self) -> List[ExecutionIntent]:
        async with self._session_maker() as session:
            stmt = (
                select(PGExecutionIntentORM)
                .where(PGExecutionIntentORM.status.not_in(self._TERMINAL_STATUSES))
                .order_by(PGExecutionIntentORM.created_at.asc())
            )
            result = await session.execute(stmt)
            return [self._to_domain(orm) for orm in result.scalars().all()]

    async def list(
        self,
        status: Optional[ExecutionIntentStatus] = None,
    ) -> List[ExecutionIntent]:
        async with self._session_maker() as session:
            stmt = select(PGExecutionIntentORM)
            if status is not None:
                stmt = stmt.where(PGExecutionIntentORM.status == status.value)
            stmt = stmt.order_by(PGExecutionIntentORM.created_at.asc())
            result = await session.execute(stmt)
            return [self._to_domain(orm) for orm in result.scalars().all()]

    async def update_status(
        self,
        intent_id: str,
        status: ExecutionIntentStatus,
        *,
        order_id: Optional[str] = None,
        exchange_order_id: Optional[str] = None,
        blocked_reason: Optional[str] = None,
        blocked_message: Optional[str] = None,
        failed_reason: Optional[str] = None,
    ) -> None:
        values = {
            "status": status.value,
            "updated_at": int(datetime.now(timezone.utc).timestamp() * 1000),
        }
        if order_id is not None:
            values["order_id"] = order_id
        if exchange_order_id is not None:
            values["exchange_order_id"] = exchange_order_id
        if blocked_reason is not None:
            values["blocked_reason"] = blocked_reason
        if blocked_message is not None:
            values["blocked_message"] = blocked_message
        if failed_reason is not None:
            values["failed_reason"] = failed_reason

        async with self._session_maker() as session:
            await session.execute(
                update(PGExecutionIntentORM)
                .where(PGExecutionIntentORM.id == intent_id)
                .values(**values)
            )
            await session.commit()

    @staticmethod
    def _to_orm(intent: ExecutionIntent) -> PGExecutionIntentORM:
        return PGExecutionIntentORM(
            id=intent.id,
            signal_id=intent.signal_id,
            symbol=intent.signal.symbol,
            status=str(intent.status),
            signal_payload=intent.signal.model_dump(mode="json"),
            strategy_payload=intent.strategy.model_dump(mode="json") if intent.strategy else None,
            order_id=intent.order_id,
            exchange_order_id=intent.exchange_order_id,
            blocked_reason=intent.blocked_reason,
            blocked_message=intent.blocked_message,
            failed_reason=intent.failed_reason,
            created_at=intent.created_at,
            updated_at=intent.updated_at,
        )

    @staticmethod
    def _to_domain(orm: PGExecutionIntentORM) -> ExecutionIntent:
        signal = SignalResult.model_validate(orm.signal_payload)
        strategy = (
            OrderStrategy.model_validate(orm.strategy_payload)
            if orm.strategy_payload
            else None
        )
        return ExecutionIntent(
            id=orm.id,
            signal_id=orm.signal_id,
            signal=signal,
            status=ExecutionIntentStatus(orm.status),
            strategy=strategy,
            order_id=orm.order_id,
            exchange_order_id=orm.exchange_order_id,
            blocked_reason=orm.blocked_reason,
            blocked_message=orm.blocked_message,
            failed_reason=orm.failed_reason,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )
