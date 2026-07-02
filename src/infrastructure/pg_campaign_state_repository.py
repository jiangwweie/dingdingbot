"""PG repository for runtime campaign state."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import (
    PGRuntimeCampaignStateORM,
    PGRuntimeCampaignStateTransitionORM,
)
from src.infrastructure.repository_ports import (
    CampaignStateSnapshot,
    CampaignStateTransitionLog,
)


class PgCampaignStateRepository:
    """PG persistence for runtime campaign state machine snapshots."""

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()
        self._uses_injected_session_maker = session_maker is not None

    async def initialize(self) -> None:
        if self._uses_injected_session_maker:
            return
        await init_pg_core_db()

    async def get_state(self, scope_key: str) -> Optional[CampaignStateSnapshot]:
        async with self._session_maker() as session:
            row = await session.get(PGRuntimeCampaignStateORM, scope_key)
            return self._to_snapshot(row) if row is not None else None

    async def set_state(
        self,
        *,
        scope_key: str,
        status: str,
        reason: Optional[str],
        updated_by: str,
        updated_at_ms: int,
        active_strategy_contract_id: Optional[str],
        active_session_id: Optional[str],
    ) -> CampaignStateSnapshot:
        async with self._session_maker() as session:
            async with session.begin():
                row = await session.get(
                    PGRuntimeCampaignStateORM,
                    scope_key,
                    with_for_update=True,
                )
                if row is None:
                    row = PGRuntimeCampaignStateORM(
                        scope_key=scope_key,
                        status=status,
                        reason=reason,
                        updated_by=updated_by,
                        updated_at_ms=updated_at_ms,
                        active_strategy_contract_id=active_strategy_contract_id,
                        active_session_id=active_session_id,
                    )
                    session.add(row)
                else:
                    row.status = status
                    row.reason = reason
                    row.updated_by = updated_by
                    row.updated_at_ms = updated_at_ms
                    row.active_strategy_contract_id = active_strategy_contract_id
                    row.active_session_id = active_session_id
                await session.flush()
                return self._to_snapshot(row)

    async def record_transition(
        self,
        transition: CampaignStateTransitionLog,
    ) -> CampaignStateTransitionLog:
        async with self._session_maker() as session:
            async with session.begin():
                return await self._insert_transition(
                    session=session,
                    transition=transition,
                )

    async def set_state_with_transition(
        self,
        *,
        scope_key: str,
        status: str,
        reason: Optional[str],
        updated_by: str,
        updated_at_ms: int,
        active_strategy_contract_id: Optional[str],
        active_session_id: Optional[str],
        transition: CampaignStateTransitionLog,
    ) -> tuple[CampaignStateSnapshot, CampaignStateTransitionLog]:
        async with self._session_maker() as session:
            async with session.begin():
                row = await session.get(
                    PGRuntimeCampaignStateORM,
                    scope_key,
                    with_for_update=True,
                )
                if row is None:
                    row = PGRuntimeCampaignStateORM(
                        scope_key=scope_key,
                        status=status,
                        reason=reason,
                        updated_by=updated_by,
                        updated_at_ms=updated_at_ms,
                        active_strategy_contract_id=active_strategy_contract_id,
                        active_session_id=active_session_id,
                    )
                    session.add(row)
                else:
                    row.status = status
                    row.reason = reason
                    row.updated_by = updated_by
                    row.updated_at_ms = updated_at_ms
                    row.active_strategy_contract_id = active_strategy_contract_id
                    row.active_session_id = active_session_id
                persisted_transition = await self._insert_transition(
                    session=session,
                    transition=transition,
                )
                await session.flush()
                return self._to_snapshot(row), persisted_transition

    async def list_transitions(
        self,
        scope_key: str,
        *,
        limit: int = 500,
    ) -> list[CampaignStateTransitionLog]:
        safe_limit = max(0, limit)
        async with self._session_maker() as session:
            stmt = (
                select(PGRuntimeCampaignStateTransitionORM)
                .where(PGRuntimeCampaignStateTransitionORM.scope_key == scope_key)
                .order_by(PGRuntimeCampaignStateTransitionORM.sequence_number.asc())
                .limit(safe_limit)
            )
            result = await session.execute(stmt)
            return [self._to_transition(row) for row in result.scalars().all()]

    async def _next_sequence_number(
        self,
        *,
        session: AsyncSession,
        scope_key: str,
    ) -> int:
        stmt = select(func.max(PGRuntimeCampaignStateTransitionORM.sequence_number)).where(
            PGRuntimeCampaignStateTransitionORM.scope_key == scope_key,
        )
        result = await session.execute(stmt)
        current = result.scalar_one_or_none()
        return int(current or 0) + 1

    async def _insert_transition(
        self,
        *,
        session: AsyncSession,
        transition: CampaignStateTransitionLog,
    ) -> CampaignStateTransitionLog:
        sequence_number = await self._next_sequence_number(
            session=session,
            scope_key=transition.scope_key,
        )
        row = PGRuntimeCampaignStateTransitionORM(
            scope_key=transition.scope_key,
            sequence_number=sequence_number,
            previous_status=transition.previous_status,
            target_status=transition.target_status,
            next_status=transition.next_status,
            trigger=transition.trigger,
            reason=transition.reason,
            updated_by=transition.updated_by,
            occurred_at_ms=transition.occurred_at_ms,
            accepted=transition.accepted,
            rule_reason_code=transition.rule_reason_code,
            rejection_reason=transition.rejection_reason,
            active_strategy_contract_id=transition.active_strategy_contract_id,
            active_session_id=transition.active_session_id,
            metadata_json=dict(transition.metadata or {}),
            created_at_ms=transition.occurred_at_ms,
        )
        session.add(row)
        await session.flush()
        return self._to_transition(row)

    @staticmethod
    def _to_snapshot(row: PGRuntimeCampaignStateORM) -> CampaignStateSnapshot:
        return CampaignStateSnapshot(
            scope_key=row.scope_key,
            status=row.status,
            reason=row.reason,
            updated_by=row.updated_by,
            updated_at_ms=int(row.updated_at_ms),
            active_strategy_contract_id=row.active_strategy_contract_id,
            active_session_id=row.active_session_id,
            source="pg",
        )

    @staticmethod
    def _to_transition(
        row: PGRuntimeCampaignStateTransitionORM,
    ) -> CampaignStateTransitionLog:
        return CampaignStateTransitionLog(
            scope_key=row.scope_key,
            sequence_number=int(row.sequence_number),
            previous_status=row.previous_status,
            target_status=row.target_status,
            next_status=row.next_status,
            trigger=row.trigger,
            reason=row.reason,
            updated_by=row.updated_by,
            occurred_at_ms=int(row.occurred_at_ms),
            accepted=bool(row.accepted),
            rule_reason_code=row.rule_reason_code,
            rejection_reason=row.rejection_reason,
            active_strategy_contract_id=row.active_strategy_contract_id,
            active_session_id=row.active_session_id,
            metadata=dict(row.metadata_json or {}),
            source="pg",
        )
