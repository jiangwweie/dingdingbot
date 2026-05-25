"""PG repository for runtime campaign state."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import PGRuntimeCampaignStateORM
from src.infrastructure.repository_ports import CampaignStateSnapshot


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
